-- A respondent-year present in more than one extract must have identical answers.
-- Returns the offending respondent-years; the test passes when there are none.
select "year", id_
from {{ source('raw', 'gss_responses') }}
group by "year", id_
having count(distinct record_sha256) > 1
