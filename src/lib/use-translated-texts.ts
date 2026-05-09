"use client";

import { useEffect, useMemo, useState } from "react";
import { translateTexts } from "@/lib/api";
import { Language } from "@/lib/i18n";

export function useTranslatedTexts(texts: string[], language: Language) {
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const stableTexts = useMemo(() => {
    const unique = Array.from(new Set(texts.map((text) => text.trim()).filter(Boolean)));
    return unique.slice(0, 120);
  }, [texts]);
  const key = stableTexts.join("\n---\n");

  useEffect(() => {
    if (language !== "zh" || stableTexts.length === 0) {
      setTranslations({});
      return;
    }

    let cancelled = false;
    translateTexts(stableTexts)
      .then((response) => {
        if (cancelled || !response.enabled) return;
        const next: Record<string, string> = {};
        stableTexts.forEach((text, index) => {
          next[text] = response.translations[index] ?? text;
        });
        setTranslations(next);
      })
      .catch(() => {
        if (!cancelled) setTranslations({});
      });

    return () => {
      cancelled = true;
    };
  }, [key, language]);

  return (text: string | null | undefined) => {
    if (!text) return "";
    return language === "zh" ? translations[text] ?? text : text;
  };
}
