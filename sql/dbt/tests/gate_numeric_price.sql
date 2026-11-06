{{ config(tags=['gate']) }}
-- F06: a price stored as text must block promotion. Schema check on the
-- staging column type: l_extendedprice must be a DECIMAL type.
SELECT DISTINCT typeof(l_extendedprice) AS bad_type
FROM {{ ref('stg_lineitem') }}
WHERE typeof(l_extendedprice) NOT LIKE 'DECIMAL%'
