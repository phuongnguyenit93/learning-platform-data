# Kiểu dữ liệu, toán tử, operator class và access method mở rộng

PostgreSQL cho phép mở rộng hệ thống kiểu dữ liệu, toán tử và cơ chế lập chỉ mục. Một kiểu dữ liệu mới có thể định nghĩa cách lưu trữ, nhập/xuất và so sánh giá trị. Toán tử cung cấp cú pháp để ứng dụng và planner biểu diễn các phép so sánh hoặc thao tác trên kiểu đó. Operator class mô tả cách một index access method hiểu các toán tử và gọi support functions tương ứng. Access method cung cấp thuật toán và cấu trúc index hoặc table thực tế.

Bốn thành phần này liên quan chặt chẽ nhưng có vai trò khác nhau:

```text
       Data type
       Representation, input/output, semantics
             |
             v
       Operators
       =, <, @>, &&, <->, ...
             |
             v
       Operator class / operator family
       Strategies + support functions
             |
             v
       Access method
       B-tree / Hash / GiST / SP-GiST / GIN / BRIN
             |
             v
       Index structure and query execution
```

Bài thuộc chương **Mở rộng** của module *Database Engine Relational PostgreSQL*. Nội dung đi từ các kiểu dữ liệu có sẵn, cách tạo type và operator, tới hợp đồng của operator class/family, các index access methods và API để extension bổ sung access method mới.

Sau bài học, bạn có thể:

1. Phân biệt type, operator, operator class, operator family và access method.
2. Chọn giữa domain, enum, composite, range và custom base type.
3. Khai báo operator cùng commutator, negator, selectivity estimators và join estimators.
4. Hiểu strategy numbers và support functions của operator classes.
5. Dùng operator families cho nhiều input types và cross-type operators.
6. Chọn B-tree, Hash, GiST, SP-GiST, GIN hoặc BRIN theo access pattern.
7. Hiểu vai trò của GiST/GIN/SP-GiST/BRIN support functions.
8. Đọc và tạo index với operator class tường minh.
9. Nhận biết extension cung cấp operator classes hoặc access methods mới.
10. Hiểu ranh giới giữa SQL DDL và C-level access method API.

---

## 1. Bức tranh tổng thể về extensibility

### 1.1. Kiểu dữ liệu trả lời câu hỏi gì?

Type định nghĩa tập giá trị hợp lệ và cách PostgreSQL biểu diễn giá trị. Ví dụ:

- **integer, numeric, text, timestamp** là built-in types.
- **enum** biểu diễn một tập nhãn hữu hạn.
- **composite** gom nhiều fields thành một giá trị có cấu trúc.
- **range** biểu diễn khoảng có lower/upper bounds.
- **domain** áp dụng constraint và tên miền nghiệp vụ lên một type hiện có.
- Custom base type có thể định nghĩa representation và I/O functions riêng.

Type quyết định type checking, casting, storage layout, input/output, equality semantics và các operations có thể thực hiện.

### 1.2. Operator trả lời câu hỏi gì?

Operator cung cấp cú pháp như **=**, **<**, **@>**, **&&**, **||** hoặc **<->**. Một operator gắn với:

- Tên operator.
- Kiểu dữ liệu bên trái và bên phải.
- Function thực thi phép toán.
- Các thuộc tính như commutator, negator, restriction/join selectivity estimators và hash/merge capability.

Operator không tự tạo index. Nó chỉ cung cấp semantics cho biểu thức; index có thể hỗ trợ operator đó nếu access method có operator class phù hợp.

### 1.3. Operator class trả lời câu hỏi gì?

Operator class (opclass) là hợp đồng giữa một index access method và một data type. Nó nói cho access method biết:

- Các operator strategy nào có thể được index hỗ trợ.
- Support functions nào thực hiện compare, consistency, distance, extract keys hoặc thao tác cấu trúc.
- Cách xử lý giá trị của type khi tạo và truy vấn index.

Một type có thể có nhiều operator classes cho cùng một access method, tùy semantics và workload.

### 1.4. Operator family trả lời câu hỏi gì?

Operator family (opfamily) gom các operator classes và các operators/support functions liên quan. Nó cho phép access method hiểu các phép toán giữa nhiều types, ví dụ so sánh **integer** với **bigint**, khi semantics được định nghĩa nhất quán.

Opclass là interface mà người tạo index chọn; opfamily là nhóm rộng hơn mà planner/access method có thể dùng để suy luận quan hệ giữa các kiểu.

### 1.5. Access method trả lời câu hỏi gì?

Access method là thuật toán và cơ chế vật lý dùng để tạo, lưu, tìm và cập nhật index hoặc table. PostgreSQL có nhiều index access methods:

| Access method | Cấu trúc/ý tưởng | Workload điển hình |
|---|---|---|
| B-tree | Cây cân bằng, ordered keys | Equality, range, sort, min/max |
| Hash | Hash buckets | Equality |
| GiST | Balanced search tree với generalized predicates | Spatial, ranges, nearest-neighbor tùy opclass |
| SP-GiST | Space-partitioned search tree | Trie, radix tree, partitioned spatial data |
| GIN | Inverted index trên các thành phần của item | Arrays, JSONB, full-text, trigrams |
| BRIN | Tóm tắt theo block ranges | Bảng lớn có correlation theo physical order |

Access method không tự quyết định semantics của mọi type. Operator class kết nối semantics của type với thuật toán của access method.

### 1.6. Hai lớp access method

PostgreSQL có **index access methods** và **table access methods**. Index AM phục vụ câu lệnh CREATE INDEX USING; table AM quản lý cách heap/table lưu và truy cập rows. Hai API khác nhau và được đăng ký bằng CREATE ACCESS METHOD với type tương ứng.

Trong phần lớn ứng dụng SQL, bạn dùng index AM có sẵn hoặc extension cung cấp. Viết một AM mới là công việc ở mức C, đòi hỏi hiểu storage, concurrency, WAL, vacuum và recovery.

---

## 2. Các kiểu dữ liệu mở rộng trong PostgreSQL

### 2.1. Chọn loại type đúng trước khi viết C

Không phải mọi nhu cầu đều cần custom base type. Ưu tiên built-in types và SQL-level types khi chúng biểu diễn đúng domain:

| Nhu cầu | Type phù hợp |
|---|---|
| Giá trị số có precision cố định | numeric(p,s) hoặc integer minor units |
| Tập nhãn nhỏ, ổn định | enum |
| Ràng buộc bổ sung cho type có sẵn | domain |
| Một record gồm nhiều fields | composite |
| Khoảng liên tục | range |
| Khoảng nhiều đoạn | multirange |
| Cấu trúc key/value linh hoạt | jsonb hoặc extension phù hợp |
| Representation và semantics hoàn toàn riêng | Custom base type |

Custom base type thường cần C functions để kiểm soát representation, I/O và các support functions hiệu quả.

### 2.2. Domain

Domain tạo một type nghiệp vụ dựa trên type khác, có thể thêm NOT NULL và CHECK constraints:

```sql
CREATE DOMAIN app.email_address AS text
    CHECK (VALUE = lower(VALUE))
    CHECK (position('@' IN VALUE) > 1);

CREATE TABLE app.users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email app.email_address NOT NULL
);
```

Domain giúp tái sử dụng validation và làm rõ ý nghĩa cột. Domain không tạo một representation vật lý hoàn toàn mới; nó dựa trên base type.

### 2.3. Enum

Enum thích hợp cho tập nhãn nhỏ, ít thay đổi:

```sql
CREATE TYPE app.order_state AS ENUM (
    'pending',
    'paid',
    'shipped',
    'cancelled'
);

CREATE TABLE app.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state app.order_state NOT NULL DEFAULT 'pending'
);
```

Enum có thứ tự theo thứ tự các labels được khai báo. Thêm label có thể dùng ALTER TYPE ADD VALUE; xóa hoặc sắp xếp lại labels không đơn giản như thay một dòng dữ liệu. Nếu tập trạng thái thay đổi thường xuyên hoặc có metadata, bảng lookup với foreign key có thể phù hợp hơn.

### 2.4. Composite type

Composite type gom nhiều fields:

```sql
CREATE TYPE app.address AS (
    street text,
    city text,
    postal_code text,
    country_code char(2)
);

CREATE TABLE app.customer_contacts (
    customer_id bigint PRIMARY KEY,
    billing_address app.address
);
```

Truy cập field bằng cú pháp (billing_address).city. Composite types hữu ích cho API và function return values; chúng không thay thế normalized relational tables khi cần constraint, joins và lifecycle độc lập cho từng field.

### 2.5. Range và multirange

Range type biểu diễn một khoảng với lower/upper bounds và tính inclusive/exclusive:

```sql
CREATE TABLE app.reservations (
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

Toán tử && kiểm tra overlap. Toán tử @> kiểm tra range/element containment. PostgreSQL cung cấp range types như int4range, int8range, numrange, daterange, tsrange và tstzrange; các range types được hỗ trợ bởi GiST/SP-GiST operator classes phù hợp.

Multirange biểu diễn một tập các khoảng không liên tục, hữu ích khi lịch làm việc hoặc availability có nhiều đoạn.

### 2.6. Custom base type

Khi cần một representation riêng, có thể tạo base type bằng CREATE TYPE với I/O functions:

- Input function chuyển cstring thành internal Datum.
- Output function chuyển Datum thành text.
- Receive/send functions xử lý binary protocol.
- Typmod input/output xử lý modifier nếu type có cú pháp như precision.
- Analyze function có thể cung cấp statistics riêng cho planner.

Khai báo base type có thể gồm INTERNALLENGTH, PASSEDBYVALUE, ALIGNMENT, STORAGE, CATEGORY, PREFERRED, COLLATABLE, INPUT, OUTPUT, RECEIVE, SEND và các thuộc tính khác. Các khai báo này phải khớp chính xác representation trong C.

### 2.7. Shell type và bootstrap

Khi C I/O function cần khai báo return type mà type chưa tồn tại, extension thường tạo shell type trước, khai báo functions, rồi hoàn thiện type definition:

```sql
CREATE TYPE app.temperature;

CREATE FUNCTION app.temperature_in(cstring)
RETURNS app.temperature
AS 'MODULE_PATHNAME', 'temperature_in'
LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE FUNCTION app.temperature_out(app.temperature)
RETURNS cstring
AS 'MODULE_PATHNAME', 'temperature_out'
LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE TYPE app.temperature (
    INPUT = app.temperature_in,
    OUTPUT = app.temperature_out,
    INTERNALLENGTH = 8,
    PASSEDBYVALUE,
    ALIGNMENT = double,
    STORAGE = plain
);
```

Đây là skeleton minh họa cho một representation 8-byte phù hợp với cách C code xử lý Datum. Không dùng INTERNALLENGTH, PASSEDBYVALUE hoặc ALIGNMENT tùy ý: khai báo sai có thể làm hỏng memory access hoặc dữ liệu lưu trên disk. Thực tế cần cài C functions, header declarations và kiểm tra binary compatibility trên mọi platform hỗ trợ.

### 2.8. Input/output và binary protocol

Text input/output là giao diện SQL/client nhìn thấy. Binary send/receive là giao diện wire protocol; chúng phải dùng định dạng ổn định và đúng network byte order theo convention của PostgreSQL.

Nếu không định nghĩa receive/send, PostgreSQL có thể không hỗ trợ binary I/O cho type theo cách ứng dụng mong muốn. Driver có thể fallback sang text, nhưng không nên giả định mọi driver đều xử lý giống nhau.

### 2.9. Typmod và collation

Typmod cho phép type có modifier như numeric(12,2) hoặc varchar(80). Type có semantics phụ thuộc collation cần khai báo collatable và xử lý collation trong comparison functions/index support.

Không khai báo collatable chỉ vì type chứa text. Chỉ bật khi ordering/equality thực sự phụ thuộc collation và support functions xử lý đúng collation được truyền.

### 2.10. Type statistics

Planner cần statistics để ước lượng selectivity và cardinality. Với custom types có distribution đặc biệt, có thể cần analyze function hoặc operator restriction/join estimators thích hợp. Nếu planner ước lượng sai, index đúng vẫn có thể không được chọn.

---

## 3. Định nghĩa toán tử

### 3.1. Operator gắn với function

Một operator là metadata SQL gọi function có signature tương ứng. Function làm công việc thực tế; operator cho phép viết biểu thức theo dạng toán tử:

```sql
CREATE FUNCTION app.temperature_equal(
    app.temperature,
    app.temperature
)
RETURNS boolean
AS 'MODULE_PATHNAME', 'temperature_equal'
LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE OPERATOR app.=== (
    LEFTARG = app.temperature,
    RIGHTARG = app.temperature,
    FUNCTION = app.temperature_equal
);
```

Tên === chỉ là ví dụ minh họa. Chọn operator name không gây xung đột với parser hoặc operator hiện có. User-defined operators không có quyền tự định nghĩa precedence tùy ý; parser áp dụng precedence rules của PostgreSQL.

### 3.2. Schema-qualified operator

Nếu operator nằm trong schema không có trong search_path, có thể gọi rõ schema:

```sql
SELECT *
FROM app.readings
WHERE value OPERATOR(app.===) '21.5'::app.temperature;
```

Trong ví dụ thực tế, temperature_in là hàm input minh họa hoặc dùng literal cast phù hợp với type.

### 3.3. Commutator

Commutator là operator có thể đảo hai operands mà vẫn giữ kết quả tương đương. Ví dụ a < b tương đương b > a. Khai báo commutator giúp planner biến đổi biểu thức và tận dụng index ở phía còn lại khi semantics cho phép.

### 3.4. Negator

Negator là operator biểu diễn phép phủ định. Ví dụ = và <>, < và >=. Khai báo sai commutator/negator làm planner suy luận sai, nên chỉ khai báo khi equivalence thực sự đúng với mọi giá trị hợp lệ, kể cả edge cases.

### 3.5. Restriction và join selectivity

Operator có thể chỉ định:

- RESTRICT: function ước lượng selectivity khi so sánh một cột với constant/expression.
- JOIN: function ước lượng selectivity khi so sánh hai relations.

PostgreSQL có estimator built-in như eqsel, neqsel, scalarltsel, scalargtsel, eqjoinsel, neqjoinsel, scalarltjoinsel và scalargtjoinsel. Chỉ dùng estimator phù hợp với semantics. Custom type/distribution có thể cần estimator riêng.

### 3.6. HASHES và MERGES

HASHES cho planner biết operator phù hợp với hash join/hash-based operations khi hash function và equality semantics nhất quán.

MERGES cho planner biết operator phù hợp với merge join khi ordering semantics và operator family hỗ trợ yêu cầu đó.

Không gắn các flags này chỉ để planner thử một plan. Hash function phải tạo cùng hash value cho mọi giá trị bằng nhau; comparator/operator phải tuân theo quy tắc ordering/equality chính xác.

### 3.7. Strictness, volatility và parallel safety

Các thuộc tính function ảnh hưởng execution:

- STRICT: nếu có argument NULL, function trả NULL mà không gọi body; chỉ dùng khi semantics đúng.
- IMMUTABLE: output chỉ phụ thuộc inputs và không đổi theo thời gian/config/session.
- STABLE: ổn định trong một statement nhưng có thể phụ thuộc snapshot/session.
- VOLATILE: có thể thay đổi mỗi lần gọi hoặc có side effects.
- PARALLEL SAFE/RESTRICTED/UNSAFE: xác định khả năng chạy trong parallel worker.

Khai báo quá mạnh có thể cho planner phép biến đổi không an toàn. Operator function dùng trong index expressions/opclasses cần immutable semantics phù hợp.

### 3.8. Ví dụ khai báo đầy đủ hơn

Khi khai báo operator ngay từ đầu, có thể đưa các thuộc tính planner vào cùng declaration thay cho bản tối giản ở mục 3.1:

```sql
CREATE OPERATOR app.=== (
    LEFTARG = app.temperature,
    RIGHTARG = app.temperature,
    FUNCTION = app.temperature_equal,
    COMMUTATOR = OPERATOR(app.===),
    RESTRICT = eqsel,
    JOIN = eqjoinsel
);
```

Ví dụ này minh họa cách khai báo thuộc tính; operator tự-commutator chỉ hợp lệ nếu phép toán thực sự đối xứng. Với operator < hoặc > cần commutator khác. Không sao chép ví dụ mà không đối chiếu function/operator semantics.

### 3.9. NULL semantics

SQL có three-valued logic: comparison với NULL thường trả NULL/unknown, không phải true hoặc false. STRICT function thường phù hợp với phép toán thông thường, nhưng operator như IS DISTINCT FROM có semantics NULL-aware riêng và không phải user-defined operator thông thường.

Test NULL behavior cùng empty values, boundary values, NaN/infinity nếu type có, và invalid representations.

### 3.10. Operator families và planner transformations

Planner có thể dùng commutator, negator, selectivity estimator và opfamily relationships để suy luận điều kiện, chọn join strategy hoặc dùng index. Khai báo metadata không nhất quán với thực thi sẽ gây kết quả sai hoặc query plan không chính xác.

---

## 4. Operator class và operator family

### 4.1. Vì sao index cần operator class?

Index access method không thể tự hiểu mọi kiểu dữ liệu và mọi toán tử. Ví dụ B-tree cần một total ordering; GIN cần trích xuất keys từ một value và query; GiST cần consistency/penalty/picksplit behavior.

Operator class cung cấp các quy tắc đó cho một type cụ thể.

### 4.2. Default operator class

Mỗi access method có thể có default opclass cho một data type. Khi tạo:

```sql
CREATE INDEX readings_value_idx
ON app.readings USING btree (value);
```

PostgreSQL chọn default B-tree opclass của type value. Nếu cần semantics khác hoặc type có nhiều opclasses, chỉ định tường minh:

```sql
CREATE INDEX readings_value_idx
ON app.readings USING btree (value app.temperature_btree_ops);
```

### 4.3. Strategy numbers

Trong B-tree, strategy numbers tiêu chuẩn:

| Strategy | Operator | Ý nghĩa |
|---:|---|---|
| 1 | < | Nhỏ hơn |
| 2 | <= | Nhỏ hơn hoặc bằng |
| 3 | = | Bằng |
| 4 | >= | Lớn hơn hoặc bằng |
| 5 | > | Lớn hơn |

Strategy numbers khác nhau giữa access methods. Không áp dụng số B-tree cho GIN/GiST/BRIN.

### 4.4. Support functions

Support functions là callbacks mà access method gọi để thao tác với type/index. Ý nghĩa và function numbers phụ thuộc AM.

Ví dụ B-tree support function số 1 là comparator trả về số âm, 0 hoặc số dương theo thứ tự hai giá trị. B-tree có thêm support functions cho sort support, in_range, equal image và các tối ưu khác tùy version.

### 4.5. Khai báo B-tree opclass

Một opclass B-tree custom có dạng khái niệm:

```sql
CREATE OPERATOR CLASS app.temperature_btree_ops
DEFAULT FOR TYPE app.temperature USING btree AS
    OPERATOR 1 app.<  (app.temperature, app.temperature),
    OPERATOR 2 app.<= (app.temperature, app.temperature),
    OPERATOR 3 app.=== (app.temperature, app.temperature),
    OPERATOR 4 app.>= (app.temperature, app.temperature),
    OPERATOR 5 app.>  (app.temperature, app.temperature),
    FUNCTION 1 app.temperature_cmp(
        app.temperature, app.temperature
    );
```

Đây là skeleton minh họa: trước khi tạo opclass, cần định nghĩa đầy đủ các operators và comparator functions tương ứng. Equality operator phải tương thích với comparator trả 0. Operator name/schema syntax có thể cần điều chỉnh theo các operator đã khai báo trong extension. Không đăng ký opclass nếu <, =, > và comparator không tạo cùng một total ordering.

### 4.6. Comparator contract

Comparator B-tree cần có các tính chất:

- Reflexive equality: compare(a,a) = 0.
- Antisymmetry: sign(compare(a,b)) = -sign(compare(b,a)).
- Transitivity: a < b và b < c thì a < c.
- Consistency: compare(a,b) = 0 khi và chỉ khi equality operator trả true.
- Determinism: kết quả không đổi tùy session state hoặc mutable external data.

Nếu vi phạm, index scan, uniqueness checks và ordering có thể cho kết quả sai.

### 4.7. Unique index và equality semantics

Unique B-tree index dùng opclass/equality semantics để xác định hai keys có trùng hay không. Nếu comparator coi hai giá trị bằng nhau nhưng operator = lại trả false (hoặc ngược lại), behavior sẽ không nhất quán.

Với collation-sensitive types, thay đổi collation version cũng có thể làm ordering cũ không còn phù hợp; cần theo dõi collation version và reindex khi được yêu cầu.

### 4.8. Operator family

Tạo family:

```sql
CREATE OPERATOR FAMILY app.temperature_ops USING btree;
```

Opclass có thể tham gia family này:

```sql
CREATE OPERATOR CLASS app.temperature_btree_ops
DEFAULT FOR TYPE app.temperature USING btree
FAMILY app.temperature_ops AS
    OPERATOR 1 app.<  (app.temperature, app.temperature),
    OPERATOR 2 app.<= (app.temperature, app.temperature),
    OPERATOR 3 app.=== (app.temperature, app.temperature),
    OPERATOR 4 app.>= (app.temperature, app.temperature),
    OPERATOR 5 app.>  (app.temperature, app.temperature),
    FUNCTION 1 app.temperature_cmp(
        app.temperature, app.temperature
    );
```

Một family có thể chứa nhiều opclasses cho nhiều types. Family chỉ có ý nghĩa khi operators/support functions giữa các types có semantics tương thích.

### 4.9. Cross-type operators

Một family có thể chứa operator so sánh giữa hai input types khác nhau. Ví dụ B-tree integer family có các phép so sánh integer với bigint để planner có thể dùng index mà không cần cast làm mất khả năng index.

Cross-type comparator/operators phải nhất quán theo một ordering chung. Không thêm operator vào family chỉ vì hai type có thể cast qua lại.

### 4.10. ALTER OPERATOR FAMILY

Có thể thêm operators/support functions vào family sau khi tạo:

```sql
ALTER OPERATOR FAMILY app.temperature_ops USING btree
    ADD OPERATOR 3 app.=== (
        app.temperature, app.temperature
    );
```

Chỉ dùng khi opclass/family design và support functions đã được kiểm chứng. Thay đổi family có thể ảnh hưởng planner/index behavior; quản lý nó như schema-level change.

### 4.11. Inspect catalog

Các catalog hữu ích:

- pg_opclass: opclasses, access method, input type, default flag.
- pg_opfamily: operator families.
- pg_am: access methods.
- pg_amop: operators thuộc opfamily và strategy.
- pg_amproc: support procedures thuộc opfamily.
- pg_operator: operator definitions.

Ví dụ:

```sql
SELECT
    am.amname,
    ns.nspname AS opclass_schema,
    opc.opcname,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault,
    opf.opfname
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
JOIN pg_namespace AS ns ON ns.oid = opc.opcnamespace
JOIN pg_opfamily AS opf ON opf.oid = opc.opcfamily
ORDER BY am.amname, ns.nspname, opc.opcname;
```

Catalog columns có thể thay đổi giữa major versions; query này minh họa các mối liên kết chính.

---

## 5. B-tree và Hash access methods

### 5.1. B-tree

B-tree là lựa chọn mặc định cho phần lớn scalar types. Nó hỗ trợ equality, range predicates, ordering và sort. B-tree opclass cần một ordering nhất quán; với built-in types, PostgreSQL đã cung cấp các default opclasses.

Ví dụ:

```sql
CREATE INDEX events_created_at_idx
ON app.events USING btree (created_at);

SELECT *
FROM app.events
WHERE created_at >= timestamptz '2026-01-01 00:00:00+00'
  AND created_at <  timestamptz '2026-02-01 00:00:00+00'
ORDER BY created_at;
```

B-tree có thể hỗ trợ ORDER BY nếu ordering của query khớp với opclass, collation và direction. Index scan không được đảm bảo: planner so sánh chi phí với sequential scan và các phương án khác.

### 5.2. Multicolumn B-tree

Với index nhiều cột, thứ tự columns rất quan trọng. B-tree thường hiệu quả nhất khi điều kiện equality áp dụng cho các cột bên trái, sau đó là range condition trên cột kế tiếp:

```sql
CREATE INDEX orders_customer_created_idx
ON app.orders (customer_id, created_at DESC);

SELECT *
FROM app.orders
WHERE customer_id = 42
  AND created_at >= now() - interval '7 days'
ORDER BY created_at DESC
LIMIT 20;
```

Không mặc định đảo thứ tự columns hoặc tạo index cho mọi permutation. Dựa vào query workload, selectivity, write overhead và index size.

### 5.3. Sort support và collation

B-tree có thể dùng support functions bổ sung để sort nhanh hơn comparator từng cặp. Text ordering còn phụ thuộc collation; index được tạo với một collation cụ thể. Query dùng collation khác có thể không dùng cùng ordering index.

Khi collation provider/version thay đổi, kiểm tra collation version mismatch và thực hiện REINDEX theo hướng dẫn. Nếu không, ordering trong index có thể không còn khớp comparator hiện tại.

### 5.4. Hash

Hash index hỗ trợ equality operations. Hash access method yêu cầu hash function nhất quán: hai giá trị bằng nhau phải có cùng hash code. Hash collision là bình thường và cần được kiểm tra lại bằng equality semantics.

Ví dụ:

```sql
CREATE INDEX sessions_token_hash_idx
ON app.sessions USING hash (token);

SELECT *
FROM app.sessions
WHERE token = 'opaque-token';
```

Hash index không hỗ trợ range scan hoặc ORDER BY. B-tree thường là lựa chọn linh hoạt hơn trừ khi workload equality-only và có lý do cụ thể để chọn Hash.

### 5.5. Hash opclass contract

Một custom hash opclass cần support function tạo hash code từ giá trị. Function phải:

- Deterministic với cùng input.
- Trả cùng hash cho các giá trị bằng nhau.
- Không phụ thuộc mutable session state.
- Có phân phối tốt để tránh quá nhiều collisions.

Hash code không cần duy nhất. Hash index lưu đủ thông tin để recheck equality khi cần.

### 5.6. Khi nào chọn B-tree hay Hash?

| Câu hỏi | B-tree | Hash |
|---|---|---|
| Equality | Có | Có |
| Range | Có | Không |
| ORDER BY | Có | Không |
| Prefix/range traversal | Có | Không |
| Default choice cho scalar | Thường là có | Thường không |
| Custom ordering semantics | Qua opclass | Không cần ordering |

---

## 6. GiST — Generalized Search Tree

### 6.1. GiST là framework, không phải một kiểu dữ liệu

GiST là balanced tree framework cho các predicates tổng quát. Nó không áp đặt một total ordering như B-tree. Operator class định nghĩa cách biểu diễn keys, kiểm tra một subtree có thể chứa kết quả, chia page và đánh giá chi phí insert.

GiST phù hợp cho spatial data, ranges, geometric predicates, nearest-neighbor và nhiều loại dữ liệu khác khi có opclass phù hợp.

### 6.2. Support functions quan trọng

Một GiST opclass có thể cần các support functions:

- **consistent:** kiểm tra một index key/subtree có thể thỏa query predicate hay không.
- **union:** tạo bounding key đại diện cho các entries trong một page.
- **compress/decompress:** chuyển đổi giữa indexed representation và stored representation.
- **penalty:** ước lượng mức mở rộng của bounding key nếu thêm entry.
- **picksplit:** chia entries khi page đầy.
- **same:** kiểm tra hai keys có tương đương.
- **distance:** tính lower-bound distance cho nearest-neighbor search.
- **fetch:** trả lại original datum khi opclass có thể hỗ trợ index-only scan theo contract.

Không phải opclass nào cũng cần mọi function; yêu cầu phụ thuộc capabilities và PostgreSQL version.

### 6.3. Consistent function và false positives

GiST thường dùng bounding keys. Một bounding key có thể bao phủ vùng lớn hơn object thật; consistent function có thể trả lời rằng subtree có khả năng chứa match. Khi index không thể chứng minh kết quả chính xác, PostgreSQL recheck condition trên heap tuple.

Vì vậy, GiST scan có thể tạo false positives trong bước index filtering nhưng không được trả kết quả sai sau recheck. EXPLAIN có thể hiển thị Rows Removed by Index Recheck.

### 6.4. Ví dụ range và exclusion constraint

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE app.room_booking (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

GiST index bảo đảm không có hai rows cùng room_id với khoảng thời gian overlap. Extension btree_gist cung cấp GiST operator classes cho nhiều scalar types để có thể kết hợp equality với range overlap trong một exclusion constraint.

### 6.5. Nearest-neighbor

Một số GiST opclasses hỗ trợ distance operator và ORDER BY distance:

```sql
SELECT place_id, location
FROM app.places
ORDER BY location <-> point(106.7, 10.8)
LIMIT 10;
```

Đây là ví dụ minh họa cho type/operator class có distance support. GiST distance function cần trả lower bound hợp lệ cho subtree; nếu lower bound không đúng, nearest-neighbor result có thể sai.

### 6.6. Penalty và picksplit

Penalty ảnh hưởng nơi một new key được thêm vào tree. Picksplit chia entries khi page overflow. Hai functions ảnh hưởng tree shape, overlap giữa bounding keys, index size và query cost.

Một split strategy tốt giảm overlap nhưng cũng cần tránh tạo pages mất cân bằng hoặc quá nhiều empty space. Đây là một trong các phần khó nhất khi thiết kế GiST opclass mới.

---

## 7. SP-GiST — Space-Partitioned GiST

### 7.1. Khác biệt với GiST

SP-GiST hỗ trợ space-partitioned trees như trie, radix tree, quad-tree và k-d tree. GiST thường tổ chức theo bounding predicates có thể overlap; SP-GiST partition không gian thành các regions/nodes theo quy tắc của opclass.

SP-GiST hữu ích khi dữ liệu có cấu trúc phân cấp hoặc phân vùng tự nhiên, ví dụ prefix strings, IP ranges và một số spatial datasets.

### 7.2. Support functions

SP-GiST opclass có thể định nghĩa:

- **config:** mô tả type/storage options và leaf representation.
- **choose:** quyết định insert tuple vào node/partition nào.
- **picksplit:** phân chia leaf tuples thành inner node và partitions.
- **inner_consistent:** xác định child nodes nào có thể thỏa query.
- **leaf_consistent:** kiểm tra leaf value với query predicate.
- **compress:** chuyển đổi input thành representation phù hợp.

Các functions phải nhất quán với partitioning rules; inner_consistent không được loại bỏ nhánh có thể chứa match.

### 7.3. Ví dụ built-in

PostgreSQL có SP-GiST opclasses cho một số types như point, box, range và text prefix theo version. Có thể tạo index với:

```sql
CREATE INDEX points_location_spgist_idx
ON app.points USING spgist (location);
```

Kiểm tra opclass có sẵn trên major version đang dùng trước khi chọn. Không phải mọi type đều có default SP-GiST opclass.

### 7.4. Khi nào chọn SP-GiST?

Chọn khi access pattern phù hợp với partitioning semantics của opclass. So sánh với GiST/B-tree bằng cùng dataset và query workload. Một cấu trúc phù hợp lý thuyết chưa chắc nhanh hơn trên phân phối dữ liệu thực tế.

---

## 8. GIN — Generalized Inverted Index

### 8.1. Inverted index

GIN lưu mapping từ một key component tới các heap rows chứa component đó. Một row có thể đóng góp nhiều keys. Điều này phù hợp với arrays, JSONB, full-text lexemes và trigrams.

Ví dụ một JSONB document có nhiều keys/values; GIN có thể index các components để tìm documents chứa một key hoặc path/value phù hợp.

### 8.2. GIN support functions

GIN opclass định nghĩa cách trích xuất keys từ indexed value và query:

- **compare:** so sánh extracted keys trong index.
- **extractValue:** trích xuất keys từ một indexed datum.
- **extractQuery:** trích xuất keys từ query operand và cung cấp search mode/flags.
- **consistent:** xác định candidate tuple có thể thỏa query hay không.
- **triConsistent:** trả TRUE/FALSE/MAYBE để đánh giá nhiều keys hiệu quả.
- **comparePartial:** hỗ trợ partial-match search trong những opclasses cần.

GIN có thể recheck vì các keys riêng lẻ không luôn đủ để chứng minh toàn bộ predicate.

### 8.3. Array operators

GIN có opclass cho arrays, hỗ trợ các operations như contains, contained-by và overlap:

```sql
CREATE INDEX products_tags_gin_idx
ON app.products USING gin (tags);

SELECT *
FROM app.products
WHERE tags @> ARRAY['database', 'postgresql'];

SELECT *
FROM app.products
WHERE tags && ARRAY['cloud', 'database'];
```

GIN giúp tìm rows chứa elements phù hợp. Với arrays rất lớn hoặc writes thường xuyên, index maintenance có thể tốn kém.

### 8.4. JSONB opclasses

PostgreSQL cung cấp hai opclasses GIN phổ biến:

- **jsonb_ops:** hỗ trợ nhiều key-existence và containment operations; index biểu diễn keys và values theo cách tổng quát.
- **jsonb_path_ops:** tập trung vào containment/jsonpath matching phù hợp; thường tạo index gọn hơn nhưng hỗ trợ ít operator classes/operations hơn.

Ví dụ:

```sql
CREATE INDEX events_payload_ops_idx
ON app.events USING gin (payload jsonb_ops);

CREATE INDEX events_payload_path_idx
ON app.events USING gin (payload jsonb_path_ops);

SELECT *
FROM app.events
WHERE payload @> '{"kind":"payment","status":"ok"}';
```

Chọn opclass theo operators thực tế. Nếu query cần key-existence operators như ?, ?| hoặc ?&, xác nhận opclass hỗ trợ chúng; jsonb_path_ops không thay thế jsonb_ops cho mọi predicate.

### 8.5. Full-text search

GIN thường được dùng cho tsvector:

```sql
CREATE INDEX documents_search_idx
ON app.documents USING gin (search_vector);

SELECT document_id
FROM app.documents
WHERE search_vector @@ plainto_tsquery('english', 'query planning');
```

GIN hỗ trợ tìm lexemes; ranking vẫn cần tính toán trên candidates phù hợp. Cập nhật document có thể phải cập nhật nhiều index entries.

### 8.6. Pending list và fast update

GIN có cơ chế fast update dùng pending list để gom index entries trước khi merge vào main index. Điều này có thể làm insert nhanh hơn trong một số workload nhưng pending list cần được cleanup; vacuum/autovacuum và gin_clean_pending_list có thể ảnh hưởng latency.

Theo dõi GIN index size, pending list behavior và write latency. Không tắt fastupdate hoặc đổi gin_pending_list_limit chỉ dựa trên một benchmark ngắn.

---

## 9. BRIN — Block Range Index

### 9.1. Ý tưởng summary theo block ranges

BRIN lưu summary cho các nhóm physical blocks thay vì một index entry cho từng row. Với cột có correlation cao với physical row order, summary min/max hoặc inclusion có thể loại bỏ phần lớn block ranges không liên quan.

BRIN nhỏ và rẻ để maintain hơn B-tree trong một số bảng rất lớn, append-oriented. Nó thường yêu cầu heap recheck và có thể trả nhiều candidates hơn B-tree.

### 9.2. Ví dụ time-series append-only

```sql
CREATE INDEX measurements_time_brin_idx
ON app.measurements USING brin (measured_at);

SELECT *
FROM app.measurements
WHERE measured_at >= timestamptz '2026-03-01 00:00:00+00'
  AND measured_at <  timestamptz '2026-03-02 00:00:00+00';
```

Nếu rows được insert gần theo thứ tự measured_at, minmax summary có thể loại bỏ nhiều block ranges.

### 9.3. Pages per range

BRIN index option pages_per_range quyết định số heap pages được tóm tắt trong mỗi range. Giá trị nhỏ hơn tạo nhiều summaries và index lớn hơn nhưng có thể lọc chính xác hơn. Giá trị lớn hơn tạo index nhỏ hơn nhưng có thể tăng false positives/rechecks.

Chọn bằng benchmark trên data distribution thực tế, không dựa vào một giá trị mặc định cho mọi bảng.

### 9.4. Summarize và unsummarized ranges

Các block ranges mới có thể chưa được summarize. Autosummarize hoặc brin_summarize_new_values có thể được dùng để cập nhật summaries. Kiểm tra trạng thái và đảm bảo maintenance phù hợp với tốc độ ingest.

### 9.5. BRIN opclass families

PostgreSQL có các opclass BRIN như minmax, minmax-multi, inclusion và bloom cho các kiểu dữ liệu được hỗ trợ. Mỗi loại summary có cách lọc và storage trade-off khác nhau. Chọn opclass cụ thể nếu workload cần semantics khác default.

### 9.6. Khi BRIN không phù hợp

Nếu dữ liệu được insert/update ngẫu nhiên và correlation với physical order thấp, minmax summaries có thể bao phủ dải quá rộng, khiến index loại bỏ ít pages. Khi đó B-tree, GIN/GiST hoặc partition pruning có thể phù hợp hơn.

---

## 10. So sánh các index access methods

### 10.1. Bảng lựa chọn nhanh

| Predicate/workload | Access method thường xem xét | Điều cần xác nhận |
|---|---|---|
| Equality, range, BETWEEN, ORDER BY | B-tree | Ordering và leading columns |
| Equality-only trên hashable type | Hash hoặc B-tree | Hash distribution và query mix |
| Overlap/containment/spatial | GiST hoặc SP-GiST | Opclass và recheck behavior |
| Array/JSONB/full-text/trigram components | GIN | Supported operators, write cost |
| Range filter trên dữ liệu correlated | BRIN | Physical correlation, pages_per_range |
| Nearest-neighbor | GiST hoặc extension-specific AM | Distance operator và ordering semantics |
| Approximate vector search | Extension AM như HNSW/IVFFlat | Recall, latency, memory, build/update cost |

Đây là điểm bắt đầu, không phải luật cứng. Một type có thể có nhiều opclasses và một AM có thể hỗ trợ nhiều operator families.

### 10.2. Một cột có thể có nhiều indexes

Cùng một cột có thể cần nhiều indexes cho workloads khác nhau:

```sql
CREATE INDEX documents_title_btree_idx
ON app.documents USING btree (title);

CREATE INDEX documents_title_trgm_idx
ON app.documents USING gin (title gin_trgm_ops);
```

B-tree có thể hỗ trợ equality/prefix/order; trigram GIN có thể hỗ trợ substring/similarity. Đổi lại, mỗi index tăng disk, WAL, write latency và vacuum work. Chỉ giữ indexes có workload chứng minh được giá trị.

### 10.3. Index condition và recheck

Một index AM có thể lọc candidate rows rồi để executor recheck predicate trên heap. EXPLAIN có thể hiển thị Index Cond, Recheck Cond và Rows Removed by Index Recheck.

Recheck không tự động là lỗi; đó là một phần thiết kế của các generalized/inverted indexes. Tuy nhiên, recheck quá nhiều có thể làm giảm hiệu quả.

### 10.4. Planner chọn index

PostgreSQL dùng cost model, statistics, selectivity, correlation, table size, random_page_cost, effective_cache_size và các yếu tố khác. Việc opclass hỗ trợ một operator không đảm bảo planner sẽ chọn index.

Khi index không được dùng, kiểm tra:

- Query operator có nằm trong opclass strategy không.
- Operand types có khớp hoặc có cross-type family support không.
- Có cast/function quanh indexed column làm mất indexability không.
- Collation có khớp không.
- Statistics có cập nhật không.
- Selectivity và estimated rows có hợp lý không.
- Sequential scan có thực sự rẻ hơn không.

---

## 11. Operator classes từ các extension phổ biến

### 11.1. pg_trgm

Extension pg_trgm cung cấp functions/operators làm việc với trigrams của text và opclasses cho GIN/GiST:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX customers_name_trgm_gin_idx
ON app.customers USING gin (name gin_trgm_ops);

SELECT customer_id, name
FROM app.customers
WHERE name ILIKE '%postgres%';
```

GIN trigram index phù hợp cho LIKE/ILIKE substring search và similarity operations được extension hỗ trợ.

GiST trigram opclass có thể hỗ trợ distance ordering:

```sql
CREATE INDEX customers_name_trgm_gist_idx
ON app.customers USING gist (name gist_trgm_ops);

SELECT customer_id, name, name <-> 'postgress' AS distance
FROM app.customers
ORDER BY name <-> 'postgress'
LIMIT 10;
```

GIN và GiST có trade-offs khác nhau: GIN thường phù hợp candidate filtering; GiST có thể hỗ trợ nearest-neighbor ordering theo distance. Chọn theo query workload và đo trên dữ liệu thật.

### 11.2. btree_gist

btree_gist cung cấp GiST operator classes cho nhiều scalar types, cho phép kết hợp equality/order-like predicates với range/spatial conditions trong cùng GiST index hoặc exclusion constraint:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE app.resource_schedule (
    resource_id bigint NOT NULL,
    reserved_at tstzrange NOT NULL,
    EXCLUDE USING gist (
        resource_id WITH =,
        reserved_at WITH &&
    )
);
```

btree_gist không biến GiST thành B-tree đầy đủ. Một số B-tree capabilities/performance characteristics không giống nhau; nếu cần ordinary scalar equality/range/sort, B-tree thường vẫn là lựa chọn tự nhiên.

### 11.3. vector extensions

Extensions như pgvector cung cấp vector data type, distance operators và index access methods riêng, thường gồm HNSW và IVFFlat tùy extension version:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE app.items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    embedding vector(3)
);

CREATE INDEX items_embedding_hnsw_idx
ON app.items USING hnsw (embedding vector_l2_ops);

SELECT item_id
FROM app.items
ORDER BY embedding <-> '[1,2,3]'
LIMIT 10;
```

HNSW/IVFFlat là approximate nearest-neighbor indexes; recall và latency phụ thuộc index parameters, query settings, dataset size và build strategy. Opclass xác định metric semantics như L2, inner product hoặc cosine distance. Đảm bảo query operator khớp opclass; chọn metric khác có thể yêu cầu index khác.

### 11.4. jsonb_ops và jsonb_path_ops

Ví dụ GIN JSONB:

```sql
CREATE INDEX api_payload_gin_idx
ON app.api_events USING gin (payload jsonb_ops);

CREATE INDEX api_payload_path_idx
ON app.api_events USING gin (payload jsonb_path_ops);
```

Trước khi tạo cả hai, xác định các query operators cần dùng. Hai indexes cùng cột có thể tốn storage và write overhead lớn mà không đem lại lợi ích tương xứng.

### 11.5. Extension có thể thêm operator mà không thêm access method

Không phải extension nào cũng cài AM mới. Một extension có thể chỉ bổ sung:

- Data type mới.
- Operators và functions.
- Operator classes cho AM đã có.
- Casts, aggregates hoặc statistics functions.

Ví dụ pg_trgm thêm type-independent functions/operators và opclasses GIN/GiST nhưng dùng các AM có sẵn. btree_gist thêm opclasses GiST cho scalar types. Ngược lại pgvector cung cấp các AM riêng cùng opclasses của nó.

---

## 12. Tạo access method mới bằng extension

### 12.1. SQL DDL đăng ký access method

PostgreSQL cho phép đăng ký một access method với CREATE ACCESS METHOD:

```sql
CREATE FUNCTION app.my_index_handler(internal)
RETURNS index_am_handler
AS 'MODULE_PATHNAME', 'my_index_handler'
LANGUAGE C STRICT;

CREATE ACCESS METHOD app_my_index
TYPE INDEX
HANDLER app.my_index_handler;
```

Handler function là C function trả về IndexAmRoutine do PostgreSQL backend sử dụng. Đây chỉ là skeleton đăng ký; nếu routine không cung cấp các callbacks bắt buộc và semantics nhất quán, AM không thể hoạt động an toàn.

### 12.2. IndexAmRoutine

Handler khởi tạo một IndexAmRoutine và điền các flags/callbacks mà AM hỗ trợ. Tùy capabilities, routine có thể cần triển khai:

- Build/build-empty.
- Insert và bulk delete.
- Vacuum cleanup.
- Index scan hoặc bitmap scan.
- Cost estimation.
- Options/property validation.
- Parallel build/scan nếu hỗ trợ.
- Backward scan, ordering, uniqueness hoặc included columns nếu khai báo capability tương ứng.

Tên fields và callback signatures là C API theo major version. Extension phải build/test với PostgreSQL headers của target major; không sao chép routine struct từ một major khác mà không đối chiếu source/header hiện tại.

### 12.3. Index AM không chỉ là thuật toán tìm kiếm

Một index AM production cần phối hợp với:

- MVCC và snapshot visibility.
- Concurrent inserts/deletes.
- WAL logging và crash recovery.
- Vacuum và dead index entries.
- Locking/latches và concurrent scans.
- HOT updates và heap TIDs.
- Parallel workers và maintenance memory.
- Backup/restore và replication.

Thiếu một phần có thể gây index corruption hoặc kết quả không nhất quán sau crash/concurrency.

### 12.4. Table access method

Table AM dùng API riêng:

```sql
CREATE FUNCTION app.my_table_handler(internal)
RETURNS table_am_handler
AS 'MODULE_PATHNAME', 'my_table_handler'
LANGUAGE C STRICT;

CREATE ACCESS METHOD app_my_table
TYPE TABLE
HANDLER app.my_table_handler;
```

TableAmRoutine định nghĩa cách insert/fetch/update/delete/scan rows, vacuum, analyze, relation size, tuple locking, toast và các operations liên quan. Table AM không phải index AM và không dùng operator classes.

### 12.5. Ai nên viết custom access method?

Chỉ viết custom AM khi có một cấu trúc storage/search khác biệt thực sự và đã đánh giá extension hiện có. Với nhiều nhu cầu, tạo type/operator/opclass cho B-tree/GiST/GIN/BRIN sẵn có sẽ đơn giản, an toàn và dễ bảo trì hơn.

### 12.6. Quyền và bảo mật

Đăng ký access method và cài C shared library là thao tác đặc quyền. C code chạy trong backend process; lỗi memory safety có thể làm crash server hoặc ảnh hưởng dữ liệu. Chỉ cài extension đã review, build từ nguồn tin cậy và kiểm tra package/signature theo chính sách hệ thống.

### 12.7. SQL operator class vẫn cần cho custom AM

Sau khi AM được đăng ký, type vẫn cần opclass/opfamily để mô tả operators và support procedures cho AM đó. AM handler và opclass là hai phần khác nhau:

- Handler đăng ký thuật toán/callbacks vật lý.
- Opclass định nghĩa cách một type và operators sử dụng thuật toán đó.

### 12.8. Version compatibility

Index AM API là C API nội bộ có thể thay đổi giữa major versions. Build extension cho từng PostgreSQL major được hỗ trợ, kiểm tra compile warnings, regression tests, upgrade scripts và recovery behavior. Không tuyên bố extension tương thích chỉ vì SQL DDL cài được.

---

## 13. Extension packaging và lifecycle

### 13.1. Các thành phần thường có

Một extension C/SQL thường gồm:

- Control file: metadata như default_version, module_pathname, relocatable, requires và comment.
- Install SQL script: tạo types, functions, operators, opclasses, opfamilies hoặc access methods.
- Shared library: C functions/handler/support functions.
- Upgrade scripts: thay đổi catalog objects giữa extension versions.
- Regression tests: kiểm tra semantics, index results và upgrade behavior.

### 13.2. MODULE_PATHNAME

Trong extension SQL, MODULE_PATHNAME thường được thay bằng library path do control file cung cấp. Dùng symbol names ổn định và khai báo C functions đúng signature.

### 13.3. CREATE EXTENSION

Người dùng cài extension:

```sql
CREATE EXTENSION my_extension;
```

Nếu extension phụ thuộc extension khác, khai báo requires trong control file để dependency được cài theo đúng thứ tự.

### 13.4. Extension version upgrades

Thay đổi extension nên được đóng gói bằng versioned SQL upgrade scripts và ALTER EXTENSION UPDATE. Cần xử lý catalog dependencies, function signatures, operator/opclass/family objects và mọi indexes hiện có.

Nếu semantics của operator class hoặc support function thay đổi, index đã build có thể không còn đúng. Extension upgrade phải nêu rõ khi nào cần REINDEX và cung cấp quy trình migration an toàn.

### 13.5. Không thay semantics âm thầm

Một comparator/hash/consistent function được index sử dụng phải có semantics ổn định. Nếu phiên bản mới đổi ordering hoặc equality, các indexes cũ có thể chứa entries theo semantics cũ. Reindex trước khi dựa vào semantics mới.

### 13.6. Relocatable và schema

Extension có thể được thiết kế relocatable hoặc gắn schema cụ thể. Operators/types/opclasses thường có namespace; đảm bảo object names và search_path không tạo ambiguity. Với extension security-sensitive, schema ownership và CREATE privileges cần được giới hạn.

---

## 14. Chẩn đoán index và planner

### 14.1. Xác nhận access method/opclass của index

```sql
SELECT
    idx.relname AS index_name,
    am.amname AS access_method,
    opc_ns.nspname AS opclass_schema,
    opc.opcname AS operator_class,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_am AS am ON am.oid = idx.relam
JOIN LATERAL unnest(i.indclass) WITH ORDINALITY AS c(opclass_oid, ord) ON true
JOIN pg_opclass AS opc ON opc.oid = c.opclass_oid
JOIN pg_namespace AS opc_ns ON opc_ns.oid = opc.opcnamespace
ORDER BY idx.relname, c.ord;
```

Query này minh họa cách xem AM và opclass từng index column; cần điều chỉnh theo version nếu catalog representation thay đổi.

### 14.2. EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT *
FROM app.documents
WHERE title ILIKE '%postgres%';
```

Đọc:

- Scan node và index name.
- Index Cond/Filter/Recheck Cond.
- Estimated rows so với actual rows.
- Shared hit/read blocks.
- Rows Removed by Index Recheck.
- Planning/execution time.

Nếu query dùng Seq Scan, có thể planner đánh giá sequential scan rẻ hơn; đó không nhất thiết là lỗi của opclass.

### 14.3. Kiểm tra operator có nằm trong opfamily

pg_amop liên kết operator family với operators và strategy. Ví dụ:

```sql
SELECT
    am.amname,
    ns.nspname AS family_schema,
    opf.opfname,
    amop.amopstrategy,
    amop.amoppurpose,
    amop.amoplefttype::regtype AS left_type,
    amop.amoprighttype::regtype AS right_type,
    amop.amopopr::regoperator AS operator
FROM pg_amop AS amop
JOIN pg_opfamily AS opf ON opf.oid = amop.amopfamily
JOIN pg_namespace AS ns ON ns.oid = opf.opfnamespace
JOIN pg_am AS am ON am.oid = opf.opfmethod
ORDER BY am.amname, opf.opfname, amop.amopstrategy;
```

Kiểm tra strategy number và operand types khi query operator không dùng index như mong đợi.

### 14.4. Kiểm tra support procedures

```sql
SELECT
    am.amname,
    ns.nspname AS family_schema,
    opf.opfname,
    amproc.amprocnum,
    amproc.amproclefttype::regtype AS left_type,
    amproc.amprocrighttype::regtype AS right_type,
    amproc.amproc::regprocedure AS support_function
FROM pg_amproc AS amproc
JOIN pg_opfamily AS opf ON opf.oid = amproc.amprocfamily
JOIN pg_namespace AS ns ON ns.oid = opf.opfnamespace
JOIN pg_am AS am ON am.oid = opf.opfmethod
ORDER BY am.amname, opf.opfname, amproc.amprocnum;
```

### 14.5. Diagnostic settings

Trong môi trường thử nghiệm, có thể tạm đặt enable_seqscan = off để kiểm tra planner có đường index path hay không. Đây chỉ là diagnostic; không dùng setting này để benchmark hoặc cấu hình production thay cho việc sửa statistics/opclass/query.

### 14.6. Reindex khi semantics thay đổi

Nếu comparator, hash function, collation behavior hoặc opclass support semantics thay đổi, đánh giá indexes phụ thuộc. Rebuild index bằng REINDEX theo kế hoạch; với production lớn, cân nhắc CONCURRENTLY và kiểm tra locks/storage.

### 14.7. Kiểm tra kết quả bằng sequential reference

Với custom opclass, so sánh kết quả query có index và kết quả buộc sequential scan trong test database. Kiểm tra boundary cases, NULLs, duplicates, collisions, ordering, range endpoints và concurrent modifications. Index phải trả đúng rows; nhanh nhưng sai semantics là lỗi nghiêm trọng.

---

## 15. Thiết kế custom type và opclass: ví dụ theo từng lớp

### 15.1. Bắt đầu từ domain semantics

Giả sử cần lưu một giá trị nhiệt độ và hỗ trợ:

- Parse từ text như 21.5 C.
- So sánh bằng nhau và theo thứ tự.
- Range predicates như nhỏ hơn 18 độ.
- Sort và unique constraints.

Trước khi tạo custom base type, cân nhắc numeric cộng domain/check constraint. Chỉ cần base type riêng nếu representation, validation, operators hoặc performance có yêu cầu đặc thù.

### 15.2. Định nghĩa representation

Chọn representation rõ ràng, ví dụ double precision lưu độ C. Quyết định:

- Có chấp nhận NaN/infinity không?
- Có chuẩn hóa đơn vị khi input không?
- Equality là bitwise hay numeric equality?
- Có cần preserve original scale/format không?
- Có collatable không? Với nhiệt độ số thì không.

Nếu chọn double, cần xác định behavior của NaN, signed zero và rounding. Nếu nghiệp vụ yêu cầu decimal exact, numeric hoặc integer fixed-point có thể phù hợp hơn.

### 15.3. I/O và validation

Input function phải parse toàn bộ chuỗi hợp lệ, reject malformed values và kiểm tra overflow/range. Không chỉ parse prefix rồi bỏ qua suffix. Output function cần tạo representation canonical ổn định.

Ví dụ input hợp lệ:

- 21.5
- -10.0
- 0

Ví dụ cần reject nếu grammar không cho phép:

- empty string
- 12abc
- giá trị vượt domain limit
- đơn vị không được hỗ trợ

### 15.4. Equality và ordering

Triển khai equality và comparator từ cùng một semantic rule. Nếu type lưu double, phải quyết định cách so sánh NaN và signed zero. Không để equality function và comparator tự xử lý edge cases theo hai cách khác nhau.

### 15.5. Hash support

Nếu muốn Hash index hoặc hash join, hash function phải tương thích với equality. Với mọi a,b:

```text
a = b  =>  hash(a) = hash(b)
```

Không yêu cầu hai giá trị khác nhau phải có hash khác nhau. Cần kiểm tra distribution để giảm collisions và đảm bảo kết quả không thay đổi sau upgrade nếu index chưa được rebuild.

### 15.6. Đăng ký operators

Tạo các operators equality/ordering với function, commutator, negator và estimators phù hợp. Các operators dùng trong B-tree opclass phải có operand types và semantics khớp với comparator.

### 15.7. Đăng ký B-tree opclass

Khai báo strategy operators 1–5 và support function comparator. Nếu cần cross-type comparisons, thêm các operators/support functions vào operator family với semantics tương thích.

### 15.8. Tạo index và kiểm tra

```sql
CREATE TABLE app.readings (
    reading_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    value app.temperature NOT NULL
);

CREATE INDEX readings_temperature_idx
ON app.readings USING btree (value app.temperature_btree_ops);

SELECT *
FROM app.readings
WHERE value OPERATOR(app.<) '18'::app.temperature;

SELECT *
FROM app.readings
ORDER BY value;
```

Đây là flow minh họa; type input function, operators và opclass phải được cài trước. Kiểm tra kết quả sort và range scan có khớp sort reference trong application/test harness.

### 15.9. Kiểm tra uniqueness

Thử insert duplicate values theo semantic equality. Nếu type canonicalizes equivalent values, xác nhận unique index từ chối duplicate đúng như business rule. Thử các edge cases như signed zero, NaN, rounding boundaries hoặc case-folding nếu semantics có.

### 15.10. Reindex và upgrade

Nếu comparator/equality/hash behavior thay đổi, coi đó là thay đổi index semantics. Lập migration có REINDEX và kiểm tra unique violations trước khi bật version mới. Không thay function implementation âm thầm rồi để indexes cũ tồn tại.

---

## 16. Thực hành: chọn opclass cho từng query

### 16.1. Text exact match và sort

Query:

```sql
SELECT customer_id
FROM app.customers
WHERE email = 'user@example.test'
ORDER BY email;
```

B-tree thường phù hợp vì cần equality và ordering.

### 16.2. Substring search

Query:

```sql
SELECT customer_id, name
FROM app.customers
WHERE name ILIKE '%nguyen%';
```

Xem xét pg_trgm với GIN/GiST. B-tree thông thường không hiệu quả với wildcard ở đầu pattern.

### 16.3. JSONB containment

Query:

```sql
SELECT event_id
FROM app.events
WHERE payload @> '{"status":"paid"}';
```

Xem xét GIN và lựa chọn jsonb_ops/jsonb_path_ops theo operators thực tế.

### 16.4. Array overlap

Query:

```sql
SELECT product_id
FROM app.products
WHERE tags && ARRAY['sale', 'featured'];
```

GIN array opclass thường là điểm bắt đầu.

### 16.5. Range overlap

Query:

```sql
SELECT booking_id
FROM app.room_booking
WHERE during && tstzrange(now(), now() + interval '1 hour');
```

GiST range opclass thường phù hợp.

### 16.6. Time-series range scan

Query:

```sql
SELECT count(*)
FROM app.measurements
WHERE measured_at >= now() - interval '1 day';
```

Nếu dữ liệu append theo thời gian và có correlation cao với physical order, thử BRIN; nếu cần truy vấn point/range rất chọn lọc và sort, B-tree cũng đáng xem xét.

### 16.7. Nearest-neighbor vector search

Query:

```sql
SELECT item_id
FROM app.items
ORDER BY embedding <=> '[0.1, 0.2, 0.3]'
LIMIT 20;
```

Chọn vector opclass tương ứng cosine distance và AM extension phù hợp. Không dùng L2 opclass cho query operator khác metric.

### 16.8. Exclusion constraint

Nếu nghiệp vụ cấm hai reservations cùng resource bị overlap, dùng GiST exclusion constraint thay vì chỉ query kiểm tra trước khi insert. Constraint thực thi invariant ngay cả khi có concurrent transactions.

### 16.9. Đo write overhead

Với mỗi index, đo:

- Insert/update/delete throughput.
- WAL volume.
- Index size.
- Vacuum work.
- Lock/latency khi concurrent writes.

Một index làm SELECT nhanh hơn nhưng tăng write latency đáng kể có thể không phù hợp với write-heavy workload.

---

## 17. Những lỗi thiết kế thường gặp

1. **Chọn custom base type quá sớm:** domain, enum, composite hoặc range type có thể đáp ứng nhu cầu với ít code hơn.
2. **Comparator không transitive:** B-tree ordering không còn hợp lệ.
3. **Equality không khớp comparator:** unique index và scans có behavior sai.
4. **Hash không khớp equality:** hash joins/indexes có thể bỏ sót kết quả.
5. **Khai báo HASHES/MERGES sai:** planner có thể chọn join algorithm không đúng semantics.
6. **Commutator/negator sai:** planner transformations có thể thay đổi kết quả.
7. **Không cung cấp selectivity estimator phù hợp:** planner ước lượng cardinality sai.
8. **Chọn sai strategy number:** query operator không được index hỗ trợ như mong đợi.
9. **Dùng opclass của AM khác:** opclass không thể hoán đổi giữa B-tree, GIN, GiST, SP-GiST và BRIN.
10. **GiST consistent quá lỏng:** recheck quá nhiều; consistent quá chặt có thể loại bỏ rows đúng.
11. **GIN extract functions không nhất quán:** query keys không khớp keys lúc index build.
12. **BRIN trên cột không correlated:** summaries loại bỏ rất ít pages.
13. **Bỏ qua collation:** ordering index không khớp comparison semantics.
14. **Đổi opclass function mà không REINDEX:** index chứa entries được tạo theo semantics cũ.
15. **Giả định extension chỉ cần SQL script:** C shared library và version-specific build có thể là bắt buộc.
16. **Nhầm table AM với index AM:** hai API và responsibilities khác nhau.
17. **Tự viết AM quá sớm:** WAL, vacuum, MVCC và recovery làm phạm vi lớn hơn thuật toán tìm kiếm.
18. **Ép planner dùng index trong production:** enable_seqscan=off không sửa được index design hoặc statistics.

---

## 18. Bài tập thực hành và đáp án

### Bài 1 — Phân biệt các khái niệm

**Câu hỏi:** Type, operator, opclass và access method khác nhau thế nào?

**Đáp án:** Type định nghĩa representation/semantics; operator diễn đạt phép toán; opclass nối operator/type với một AM; AM cung cấp thuật toán và cấu trúc index/table.

### Bài 2 — Domain hay base type

**Câu hỏi:** Một email chỉ cần validation lowercase và format đơn giản. Có cần custom base type C không?

**Đáp án:** Thường không. Domain trên text với CHECK constraint là đủ.

### Bài 3 — Enum

**Câu hỏi:** Vì sao enum không lý tưởng cho danh mục thay đổi liên tục có metadata?

**Đáp án:** Enum labels có lifecycle thay đổi hạn chế; bảng lookup dễ quản lý metadata và cập nhật hơn.

### Bài 4 — Range

**Câu hỏi:** Operator && trên range làm gì?

**Đáp án:** Kiểm tra hai ranges có overlap.

### Bài 5 — Operator function

**Câu hỏi:** Operator có tự chứa implementation không?

**Đáp án:** Không. Operator gắn với function có signature phù hợp.

### Bài 6 — Commutator

**Câu hỏi:** Commutator của a < b là gì?

**Đáp án:** Operator tương đương khi đảo operands, thông thường b > a.

### Bài 7 — Selectivity

**Câu hỏi:** RESTRICT estimator phục vụ việc gì?

**Đáp án:** Ước lượng tỷ lệ rows thỏa một restriction predicate để planner tính chi phí.

### Bài 8 — HASHES

**Câu hỏi:** Điều kiện quan trọng của hash function là gì?

**Đáp án:** Hai giá trị bằng nhau phải có cùng hash value.

### Bài 9 — B-tree strategies

**Câu hỏi:** Strategy 3 của B-tree là gì?

**Đáp án:** Equality.

### Bài 10 — B-tree comparator

**Câu hỏi:** Comparator trả 0 nhưng equality operator trả false có hợp lệ không?

**Đáp án:** Không. Ordering và equality phải nhất quán.

### Bài 11 — Operator family

**Câu hỏi:** Vì sao cần operator family?

**Đáp án:** Để gom opclasses và operators/support functions liên quan, bao gồm cross-type comparisons có semantics chung.

### Bài 12 — GiST

**Câu hỏi:** GiST consistent function làm gì?

**Đáp án:** Kiểm tra index key/subtree có thể chứa kết quả của predicate hay không.

### Bài 13 — GIN

**Câu hỏi:** GIN phù hợp với kiểu dữ liệu nào?

**Đáp án:** Các values chứa nhiều components như arrays, JSONB, tsvector và trigrams.

### Bài 14 — BRIN

**Câu hỏi:** Điều kiện dữ liệu nào giúp BRIN minmax hiệu quả?

**Đáp án:** Cột có correlation cao với physical row order để min/max summaries loại bỏ block ranges.

### Bài 15 — SP-GiST

**Câu hỏi:** SP-GiST khác GiST ở ý tưởng chính nào?

**Đáp án:** SP-GiST partition không gian thành nodes/regions; GiST thường dùng generalized bounding predicates có thể overlap.

### Bài 16 — pg_trgm

**Câu hỏi:** pg_trgm cung cấp opclasses cho những AM nào?

**Đáp án:** GIN và GiST.

### Bài 17 — btree_gist

**Câu hỏi:** btree_gist có thay thế B-tree cho mọi workload không?

**Đáp án:** Không. Nó cung cấp GiST opclasses cho scalar types, hữu ích khi kết hợp với predicates khác như range overlap.

### Bài 18 — Custom AM

**Câu hỏi:** Handler của index access method trả về routine nào?

**Đáp án:** IndexAmRoutine.

### Bài 19 — Table AM

**Câu hỏi:** Table AM có dùng operator classes không?

**Đáp án:** Không. Table AM và index AM là hai APIs khác nhau.

### Bài 20 — Reindex

**Câu hỏi:** Vì sao cần REINDEX nếu comparator semantics thay đổi?

**Đáp án:** Index entries cũ được sắp xếp theo semantics cũ và có thể không còn đúng với comparator mới.

### Bài 21 — Planner

**Câu hỏi:** Opclass hỗ trợ operator có bảo đảm planner chọn index không?

**Đáp án:** Không. Planner vẫn so sánh cost và statistics.

### Bài 22 — JSONB

**Câu hỏi:** jsonb_ops và jsonb_path_ops có giống nhau không?

**Đáp án:** Không. Chúng hỗ trợ tập operators khác nhau và có storage/query trade-offs khác nhau.

### Bài 23 — Vector

**Câu hỏi:** Vì sao query distance operator phải khớp vector opclass?

**Đáp án:** Opclass định nghĩa metric/search semantics mà index hỗ trợ; metric khác cần opclass phù hợp.

### Bài 24 — Extension lifecycle

**Câu hỏi:** Extension đổi comparator hoặc opclass support function có thể cần thao tác gì?

**Đáp án:** Migration script và REINDEX để các indexes được xây lại theo semantics mới.

---

## 19. Checklist và tổng kết

### Khi thiết kế type/operator

1. Xác định semantics và representation trước khi viết code.
2. Ưu tiên built-in/domain/enum/composite/range nếu đáp ứng được.
3. Định nghĩa input/output và binary protocol rõ ràng.
4. Xử lý NULL, boundary values, NaN và collation theo contract.
5. Giữ equality, comparator và hash semantics nhất quán.
6. Khai báo commutator/negator/estimators chỉ khi đúng.

### Khi thiết kế opclass/opfamily

7. Chọn đúng access method cho workload.
8. Ghi rõ strategy operators và operand types.
9. Implement support functions đúng AM contract.
10. Đảm bảo comparator transitive và deterministic.
11. Đảm bảo hash values nhất quán với equality.
12. Dùng opfamily cho cross-type operations chỉ khi có common semantics.
13. Chỉ đánh dấu HASHES/MERGES khi thực sự hỗ trợ.
14. Kiểm tra catalog entries và planner paths.

### Khi triển khai extension/access method

15. Tách index AM và table AM.
16. Dùng version-specific PostgreSQL headers/API.
17. Kiểm tra MVCC, WAL, vacuum, locking và crash recovery.
18. Đóng gói control/install/upgrade scripts và shared library.
19. Test CREATE INDEX, INSERT/UPDATE/DELETE, REINDEX và concurrent workload.
20. Test upgrade/restore và ghi rõ khi nào cần REINDEX.

### Khi vận hành

21. Dùng EXPLAIN (ANALYZE, BUFFERS) để xem index path và recheck.
22. Theo dõi index size, write overhead, vacuum và bloat.
23. Không ép planner dùng index làm giải pháp production.
24. Giữ semantics ổn định hoặc có migration/reindex rõ ràng khi thay đổi.

PostgreSQL extensibility hoạt động theo các hợp đồng tách biệt. Type xác định dữ liệu; operator xác định phép toán; opclass/family nói cho index AM cách hỗ trợ phép toán; access method quyết định cấu trúc và thuật toán. Khi các hợp đồng này nhất quán, PostgreSQL có thể dùng planner, indexes và executor để làm việc với types/extensions mới như với các thành phần built-in.

**Câu hỏi tự kiểm tra:** Bạn có một custom type với equality operator và comparator. Muốn tạo B-tree index, chỉ khai báo operator là đủ không? Không. Cần một B-tree operator class có strategy operators phù hợp và support comparator nhất quán; planner cũng cần statistics/selectivity phù hợp để chọn index.

### Tài liệu PostgreSQL chính thức

- [Extensibility Overview](https://www.postgresql.org/docs/current/extend.html).
- [User-Defined Types](https://www.postgresql.org/docs/current/xtypes.html).
- [User-Defined Operators](https://www.postgresql.org/docs/current/xoper.html).
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/xindex.html).
- [Index Access Method Interface](https://www.postgresql.org/docs/current/indexam.html).
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html).
- [CREATE OPERATOR](https://www.postgresql.org/docs/current/sql-createoperator.html).
- [CREATE OPERATOR CLASS](https://www.postgresql.org/docs/current/sql-createopclass.html).
- [CREATE ACCESS METHOD](https://www.postgresql.org/docs/current/sql-createaccessmethod.html).
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html).
- [btree_gist](https://www.postgresql.org/docs/current/btree-gist.html).
- [Table Access Method Interface](https://www.postgresql.org/docs/current/tableam.html).
