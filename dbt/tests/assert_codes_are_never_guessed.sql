-- A label that ref_codes defines under several codes must be flagged and must not carry one.
-- The check reads the seed, so it follows the metadata rather than a hard-coded list.
select 'ambiguous label carries a code' as problem, variable_name, answer_label
from {{ ref('int_gss__responses_long') }}
where code_is_ambiguous and answer_code is not null

union all

select 'ambiguous label is not flagged' as problem, answers.variable_name, answers.answer_label
from {{ ref('int_gss__responses_long') }} as answers
inner join (
    select variable_name, label
    from {{ ref('ref_codes') }}
    group by variable_name, label
    having count(*) > 1
) as ambiguous
    on ambiguous.variable_name = answers.variable_name
   and ambiguous.label = answers.answer_label
where not answers.code_is_ambiguous
