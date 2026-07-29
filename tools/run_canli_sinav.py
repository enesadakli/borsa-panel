"""Canlı sınav test çalıştırıcısı — LM Studio API veya GUI üzerinden test.

Kullanım:
    python tools/run_canli_sinav.py [--filtered]

LM Studio local server açık ise (http://localhost:1234/v1), otomatik olarak isteği atar
ve cevabı doğrular. Kapalı ise prompt metnini dosyaya yazar.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import llm_rapor as LLM
from core.yahoo import YahooClient

SYSTEM_PROMPT = (
    "Sana verilen şirket raporunu dikkatlice oku. Raporun ardından gelen soruları "
    "numaralandırarak (1., 2., 3., 4., 5.) ve YALNIZCA rapordaki bilgilere dayanarak "
    "cevapla. Raporu yeniden özetleme, doğrudan ve net yanıt ver."
)

SORULAR = """SORULAR:
1. F-Skoru kaç, sektöre göre nerede?
2. Kaç kırmızı bayrak var, hangileri?
3. Gelir reel olarak büyüdü mü küçüldü mü?
4. Son mali tablo ne kadar eski?
5. Net borç/FAVÖK son 4 yılda nasıl değişti?"""

CEVAP_ANAHTARI = """==================================================
DOĞRU CEVAP ANAHTARI (SISE.IS):
1. F-Skoru: 7/9 — Sektör medyanı 5/9, %96'lık dilimde (medyanın üstünde).
2. Kırmızı Bayrak: 1 adet kırmızı bayrak var -> R4_REEL_DARALMA (Sürekli ve belirgin reel daralma).
3. Reel Gelir Büyümesi: Küçüldü (%-31,5 daralma).
4. Tazelik: 2026-03-31 dönemi (4 ay önce).
5. Net Borç/FAVÖK Değişimi: 2022'de 0,80 -> 2023'te 1,11 -> 2024'te 1,89 -> 2025'te 2,15 (sürekli arttı).
=================================================="""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    filtered = "--filtered" in sys.argv
    print(f"Canlı sınav hazırlanıyor (SISE.IS, mode={'Filtered' if filtered else 'Full'})...")

    client = YahooClient()
    if filtered:
        rapor_text = LLM.olustur(client, "SISE.IS", bolumler=["ozet", "bayraklar", "fskor", "borc", "tazelik", "metrikler"])
    else:
        rapor_text = LLM.olustur(client, "SISE.IS")

    user_content = f"RAPOR:\n\n{rapor_text}\n\n---\n\n{SORULAR}"

    # Try calling LM Studio API
    api_url = "http://localhost:1234/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "max_tokens": 1000,
    }

    print(CEVAP_ANAHTARI)
    print("\nLM Studio API (http://localhost:1234/v1) kontrol ediliyor...")

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
            print("\n================ MODEL CEVABI ================")
            print(answer)
            print("==============================================")
    except Exception as e:
        # Sunucu kapalıysa GUI'ye yapıştırılacak promptu diske yaz. Dosya adı
        # moda göre değişiyor; ikisi de .gitignore'da (yeniden üretilebilir).
        ad = f"sinav_prompt_{'filtered' if filtered else 'full'}.txt"
        with open(ad, "w", encoding="utf-8") as f:
            f.write(user_content)

        print(f"\n[!] LM Studio API erişilemedi ({e}).")
        print("LM Studio GUI üzerinden manuel test etmek için:")
        print("1. System Prompt kutusuna şunu yazın:")
        print("----------------------------------------")
        print(SYSTEM_PROMPT)
        print("----------------------------------------")
        print(f"2. Kullanıcı mesajı (User Message) kutusuna `{ad}` içeriğini yapıştırın.")


if __name__ == "__main__":
    main()
