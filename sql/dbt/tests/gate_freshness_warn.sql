{{ config(tags=['gate'], severity='warn') }}
-- F10: stale input (no shipdate in 1998 or later, where the generated data
-- runs to December 1998) warns and flags the run; it does not block.
SELECT 1 AS stale_data
WHERE CAST((SELECT MAX(l_shipdate) FROM {{ ref('stg_lineitem') }}) AS VARCHAR) < '1998-01-01'
