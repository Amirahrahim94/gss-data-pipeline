-- Staging must keep every distinct respondent-year in raw: no more, no fewer.
-- Returns one row if the two counts differ; the test passes when it returns nothing.
with raw_count as (
    select count(*) as n
    from (select distinct "year", id_ from {{ source('raw', 'gss_responses') }})
),

staging_count as (
    select count(*) as n from {{ ref('stg_gss__respondents') }}
)

select raw_count.n as raw_respondent_years, staging_count.n as staging_respondent_years
from raw_count
cross join staging_count
where raw_count.n <> staging_count.n
