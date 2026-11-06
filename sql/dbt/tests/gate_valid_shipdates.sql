{{ config(tags=['gate']) }}
-- F05: a shipdate that does not parse as a date must block promotion.
-- The cast through VARCHAR normalizes DATE and VARCHAR storage, so the
-- test checks the stored values, not the storage type.
SELECT l_orderkey, l_linenumber, CAST(l_shipdate AS VARCHAR) AS shipdate_text
FROM {{ ref('stg_lineitem') }}
WHERE l_shipdate IS NOT NULL
  AND TRY_CAST(CAST(l_shipdate AS VARCHAR) AS DATE) IS NULL
