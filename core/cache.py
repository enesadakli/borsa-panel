"""Disk önbelleği.

Yahoo'ya gereksiz istek atmamak için çekilen her şey diske yazılır. İki ayrı
saklama biçimi var:

  kayıt (record) : TTL'li tek bir JSON değeri. Oran tabloları, mali tablolar,
                   şirket profili, TÜFE serileri burada durur.
  seri (series)  : tarih -> OHLCV sözlüğü. TTL yoktur, üzerine eklenerek
                   büyür; böylece ikinci çalıştırmada yalnızca eksik günler
                   çekilir.

Yazma işlemleri geçici dosya + os.replace ile atomiktir: yarıda kesilen bir
çalıştırma bozuk JSON bırakmaz.
"""

from __future__ import annotations

import json
import os
import re
import time

# Bir sembolü dosya adına çevirirken güvenli olmayan her şeyi alt çizgi yapar.
# "USDTRY=X" -> "USDTRY_X", "^XU100" -> "_XU100"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

SANIYE = 1
DAKIKA = 60
SAAT = 3600
GUN = 86400


def slug(text: str) -> str:
    """Sembol veya anahtarı dosya adı olarak kullanılabilir hale getirir."""
    return _UNSAFE.sub("_", str(text))


class Cache:
    """data/cache altında namespace'lere ayrılmış basit bir JSON önbelleği."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = os.path.abspath(str(root))

    # ------------------------------------------------------------------ yollar

    def _ns_dir(self, namespace: str) -> str:
        path = os.path.join(self.root, slug(namespace))
        os.makedirs(path, exist_ok=True)
        return path

    def record_path(self, namespace: str, key: str) -> str:
        return os.path.join(self._ns_dir(namespace), slug(key) + ".json")

    # ------------------------------------------------------------- kayıt (TTL)

    def get_record(self, namespace: str, key: str, ttl: float | None = None):
        """Kayıtlı değeri döndürür; yoksa veya bayatlamışsa None.

        ttl None ise kayıt hiç bayatlamaz (mali tablolar gibi geçmişi
        değişmeyen veriler için).
        """
        path = self.record_path(namespace, key)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                envelope = json.load(handle)
        except (OSError, ValueError):
            return None

        if ttl is not None:
            cached_at = envelope.get("_cached_at", 0)
            if time.time() - cached_at > ttl:
                return None
        return envelope.get("data")

    def set_record(self, namespace: str, key: str, value) -> None:
        envelope = {"_cached_at": time.time(), "data": value}
        self._atomic_write(self.record_path(namespace, key), envelope)

    def record_age(self, namespace: str, key: str) -> float | None:
        """Kaydın kaç saniye önce yazıldığını döndürür; yoksa None.

        Ekranda duran "veriler X saat önce güncellendi" notu bunu kullanır.
        """
        path = self.record_path(namespace, key)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                envelope = json.load(handle)
        except (OSError, ValueError):
            return None
        cached_at = envelope.get("_cached_at")
        return None if cached_at is None else time.time() - cached_at

    def has_record(self, namespace: str, key: str, ttl: float | None = None) -> bool:
        return self.get_record(namespace, key, ttl) is not None

    def drop_record(self, namespace: str, key: str) -> None:
        try:
            os.remove(self.record_path(namespace, key))
        except OSError:
            pass

    # ------------------------------------------------------- fiyat serisi (kalıcı)
    #
    # Nokta biçimi: {"2026-07-23": [open, high, low, close, volume]}
    # Liste kullanmak sözlüğe göre yaklaşık %40 daha küçük dosya veriyor;
    # 1000 sembolde bu fark hissedilir.

    def get_series(self, symbol: str) -> dict:
        """Sembolün kayıtlı fiyat serisini zarfıyla birlikte döndürür."""
        stored = self.get_record("series", symbol, ttl=None)
        if not isinstance(stored, dict):
            return {"symbol": symbol, "currency": None, "points": {}}
        stored.setdefault("symbol", symbol)
        stored.setdefault("currency", None)
        stored.setdefault("points", {})
        return stored

    def merge_series(self, symbol: str, points: dict, currency: str | None = None) -> dict:
        """Yeni günleri kayıtlı seriye ekler ve birleşmiş seriyi döndürür.

        Aynı tarih tekrar gelirse yenisi eskisini ezer — gün içi çekilen bir bar,
        gün kapandıktan sonra düzeltilmiş barla değiştirilebilsin diye.
        """
        stored = self.get_series(symbol)
        stored["points"].update(points)
        if currency:
            stored["currency"] = currency
        stored["symbol"] = symbol
        self.set_record("series", symbol, stored)
        return stored

    def series_last_date(self, symbol: str) -> str | None:
        """Kayıtlı serideki en son tarih (ISO), seri boşsa None."""
        points = self.get_series(symbol)["points"]
        return max(points) if points else None

    def closes(self, symbol: str) -> list[tuple[str, float]]:
        """(tarih, kapanış) çiftlerini tarihe göre sıralı döndürür.

        Kapanışı None olan barlar (tatil/veri boşluğu) atlanır — hesaplarda
        None ile karşılaşmamak için filtre burada, çağıran tarafta değil.
        """
        points = self.get_series(symbol)["points"]
        out = []
        for date in sorted(points):
            row = points[date]
            close = row[3] if isinstance(row, (list, tuple)) and len(row) > 3 else None
            if close is not None:
                out.append((date, float(close)))
        return out

    # ------------------------------------------------------------------ yardımcı

    @staticmethod
    def _atomic_write(path: str, payload) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)


def default_cache() -> Cache:
    """Proje kökündeki data/cache dizinini kullanan önbellek."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Cache(os.path.join(project_root, "data", "cache"))
