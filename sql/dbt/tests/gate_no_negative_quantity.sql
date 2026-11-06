{{ config(tags=['gate']) }}
-- F04: a negative quantity must block promotion.
SELECT l_orderkey, l_linenumber, l_quantity
FROM {{ ref('stg_lineitem') }}
WHERE l_quantity < 0
