
-- postgres backend notes

-- all tables handled by the SQL, generated by SqliteQueryGenerator
-- have the following definition

create table if not exists mytable (data jsonb unique not null);

-- let's add some test data
insert into mytable values (
    '{
        "x": 0,
        "y": 1,
        "z": null,
        "b":[1, 2, 5, 1],
        "c": null,
        "d": "string1"
    }'
);
insert into mytable values (
    '
    {
        "y": 11,
        "z": 1,
        "c": [
            {
                "h": 3,
                "p": 99,
                "w": false
            },
            {
                "h": 32,
                "p": false,
                "w": true,
                "i": {
                    "t": [1,2,3]
                }
            },
            {
                "h": 0
            }
        ],
        "d": "string2"
    }'
);
insert into mytable values (
    '{
        "a": {
            "k1": {
                "r1": [1, 2],
                "r2": 2
            },
            "k2": ["val", 9]
        },
        "z": 0,
        "x": 88,
        "d": "string3"
    }'
);
insert into mytable values (
    '{
        "a": {
            "k1": {
                "r1": [33, 200],
                "r2": 90
            },
            "k2": ["val222", 90],
            "k3": [{"h": 0}]
        },
        "z": 10,
        "x": 107
    }'
);
insert into mytable values (
    '{
        "x": 10
    }'
);

-- now let's do some basic JSON selections to see what kind of SQL code
-- is generated

select data#>'{x}' from mytable;

-- to reconstruct it
select jsonb_build_object('x', data#>'{x}') from mytable;

-- for selecting specific entries in an array like key2[0] we can rely on array
-- functionality in postgres

select jsonb_build_object('b',
    case when data#>'{b}'->0 is not null then
    array[data#>'{b}'->0]
    else null end)
from mytable;

-- when array elements are maps, instead of single elements like strings, or scalars
-- then one typically wants to perform key selection inside the array elements
-- and then typically, one wants those selections to apply to all elements
-- just like it does on the uppper level

-- postgres does not have rich enough json processing functions
-- to be able to do key selection in arrays

drop function if exists filter_array_elements(jsonb, text[]);
create or replace function filter_array_elements(data jsonb, keys text[])
    returns jsonb as $$
    declare key text;
    declare element jsonb;
    declare filtered jsonb;
    declare out jsonb;
    begin
        for element in select jsonb_array_elements(data) loop
            for key in select unnest(keys) loop
                if filtered is not null then
                    filtered := filtered || jsonb_build_object(key, jsonb_extract_path(element, key));
                else
                    filtered := jsonb_build_object(key, jsonb_extract_path(element, key));
                end if;
            end loop;
            if out is not null then
                out := out || jsonb_build_array(filtered)::jsonb;
            else
                out := jsonb_build_array(filtered)::jsonb;
            end if;
        end loop;
        return out;
    end;
$$ language plpgsql;

-- one can then use this in combination with the provided functions

select jsonb_build_object(
    'c',
    case when data#>'{c}' is not null
    and jsonb_typeof(data#>'{c}') = 'array'
    then filter_array_elements(data#>'{c}', '{h,p}')
    else null end)
from mytable;

-- when selecting a specific array element, the filter_array_elements call is refined

select jsonb_build_object(
    'c',
    case when data#>'{c}' is not null
    and jsonb_typeof(data#>'{c}') = 'array'
    then array[filter_array_elements(data#>'{c}', '{h,p}')->0]
    else null end)
from mytable;


-- ensuring unique rows without running into index size constraints
-- e.g.:
drop table d1;
create table if not exists d1 (data jsonb not null, uniq text unique not null);

create or replace function unique_data()
    returns trigger as $$
    begin
        NEW.uniq := md5(NEW.data::text);
        return new;
    end;
$$ language plpgsql;

create trigger ensure_unique_data before insert on d1
    for each row execute procedure unique_data();

insert into d1 (data) values ('{"d": 9}');
