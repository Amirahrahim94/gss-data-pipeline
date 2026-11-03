-- Every label that ref_codes defines more than once must be flagged wherever it appears,
-- so the check follows the seed rather than a hard-coded list.
select l.variable_name, l.answer_label
from {{ ref('int_gss__responses_long') }} as l
inner join (
    select variable_name, label
    from {{ ref('ref_codes') }}
    group by variable_name, label
    having count(*) > 1
) as a
    on a.variable_name = l.variable_name and a.label = l.answer_label
where not l.code_is_ambiguous
