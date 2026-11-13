# IPEDS college directory

`ipeds_2024_directory.csv` is derived from the U.S. Department of Education
IPEDS `HD2024.csv` directory file:

https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip

The build script is `scripts/build_ipeds_directory.py`. It keeps active,
degree-granting, four-year public and private nonprofit institutions. It does
not contain rankings, admissions rates, tuition, or proprietary data. Names,
locations, ownership, and websites reflect the IPEDS 2024 collection and may
have changed. The website labels the year and links to the source.

## Curated school profiles

`school_profiles.json` is a 56-school editorial data snapshot. School IDs,
locations, ownership, and official websites are joined to the IPEDS 2024
directory above. The other numerical facts were extracted from the MHTML
archives supplied by the site owner on 2026-11-13. The archives label those
admissions, enrollment, costs, and major-completion figures as 2025; they have
not been independently checked against each school's latest disclosures.
The website states this limitation and does not treat an overall admission
rate as an international applicant's probability.
The cost field is only archived undergraduate tuition/fees plus archived
housing/living costs, not a current comprehensive cost of attendance. A spot
check found Harvard's archived $82,866 equals its official 2024-25 billed
subtotal, despite the archive's "2025" label. The public copy therefore
uses "archive labeled 2025" rather than equating it with 2025-26, and directs
families to school-level current cost information.

The offline extraction script is `scripts/build_school_profiles.py`. It needs
`lxml` in the build environment but adds no website runtime dependency. Run
`python scripts/build_school_profiles.py /path/to/archives` to regenerate the
JSON from the supplied MHTML files. The build validates school IDs, missing
fields, and duplicates. The committed JSON contains factual fields only:
no copied editorial prose, rankings, images, CSS, or external brand names.
The public directory is alphabetical and does not imply a U.S. News order.
Historical SAT/ACT ranges are present for 48 of the 56 archives. They describe
reported admitted-student distributions, not current testing policies; the
remaining eight schools show an explicit no-data state.
