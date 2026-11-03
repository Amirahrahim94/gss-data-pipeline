-- A label defined under several codes must not be given one of them.
select variable_name, answer_label
from {{ ref('int_gss__responses_long') }}
where code_is_ambiguous and answer_code is not null
