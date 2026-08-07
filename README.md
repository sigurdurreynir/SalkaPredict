Þetta er mín tilraun til að spá fyrir um úrslit leikja í ensku úrvalsdeildinni
með hjálp vélnáms (Machine Learning).

Gögnum er safnað með vefskrapi af mismunandi síðum og heilstætt gagnasett smíðað
út frá því. Notast er við gögn frá premierleague.com fyrir ítarlega tölfræði,
understat.com fyrir tölfræðibreytur eins og xG, PPDA og football-data.co.uk (veðbankastuðla),
Þessi gögn eru svo sameinuð í eitt gagnasett sem nær yfir átta tímabil (2017/18–2025/26).

## Ferlið

- **Vefskröpun**: Sérsmíðaðir skraparar sækja tölfræði hvers leiks af þremur
  heimildum. Selenium er notað fyrir premierleague.com, og létt requests-lausn
  fyrir understat. Passað er að skrapa af heillindum og ekki drekkja síðunum í requests
  svo þetta ferli er frekar hægt.
  Eftir tímabilið 2024/2025 uppfærði premierleague.com html kóðann á síðunni svo til að skrapa 
  hana fyrir tímabilið 2025/2026 þurfti að breyta skröpunarkóðanum
  
- **Gagnahreinsun og sameining**: Gögnin eru hreinsuð, liðanöfn samræmd milli
  heimilda, og leikir paraðir saman eftir dagsetningu og liðum.
- **Feature engineering**: Búnar eru til spábreytur sem lýsa
  nýlegu gengi og styrk liða fyrir hvern leik — Glicko-styrkleikamat, rúllandi meðaltöl
  (EMA) á breytunum, stigasöfnun og gengi liða í síðustu leikjum. Öll gildi eru færð um 1 (shifted)
  þannig að líkanið sér aldrei úrslit leiksins sem verið er að spá fyrir um.
- **Líkanagerð**: Nokkur líkön prófuð (Random Forest, XGBoost, KNN) og borin
  saman við grunnviðmið — bæði einfalda spá (heimasigur alltaf) og veðbankastuðla.

## Staða

Ath verkefnið er í vinnslu. Ítlarlegra read me kemur bráðlega.

---

*Höfundur: Sigurður Reynir Karlsson*
