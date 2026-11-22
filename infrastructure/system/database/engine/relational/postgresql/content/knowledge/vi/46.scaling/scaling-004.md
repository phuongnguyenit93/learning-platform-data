# hstore, ltree và các mô hình dữ liệu chuyên biệt trong PostgreSQL

PostgreSQL hỗ trợ nhiều kiểu dữ liệu và extension chuyên biệt để biểu diễn dữ liệu theo đúng cấu trúc nghiệp vụ. Không phải mọi dữ liệu đều phù hợp với một tập columns quan hệ cố định. Một sản phẩm có thể có tập thuộc tính linh hoạt; một danh mục có thể có cấu trúc cây nhiều cấp; một hệ thống đặt lịch cần biểu diễn khoảng thời gian; một ứng dụng mạng cần lưu địa chỉ IP/CIDR; một hệ thống địa lý cần geometry/geography.

Hai extension tiêu biểu là **hstore** và **ltree**. hstore biểu diễn một tập key/value phẳng, hữu ích khi mỗi row có các thuộc tính mở rộng dạng text. ltree biểu diễn một đường dẫn phân cấp gồm nhiều labels, hữu ích cho cây danh mục, tổ chức, phân loại hoặc cấu trúc thư mục. Cả hai đều có operators và index support để truy vấn hiệu quả.

Chọn kiểu dữ liệu chuyên biệt không chỉ là quyết định cú pháp. Cần xét cấu trúc dữ liệu, tính toàn vẹn, cách truy vấn, index, khả năng cập nhật, migration, extension availability và portability. Bài học này giải thích hstore, ltree, các mô hình dữ liệu cây/đồ thị và những lựa chọn chuyên biệt khác của PostgreSQL.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khi nào nên dùng hstore cho key/value attributes.
2. Cài và kiểm tra extension hstore.
3. Tạo, truy vấn, cập nhật, xóa và chuyển đổi hstore values.
4. Sử dụng hstore operators, functions và GIN indexes.
5. Phân biệt hstore với JSONB.
6. Giải thích ltree và cách biểu diễn hierarchy bằng path labels.
7. Cài extension ltree và sử dụng các path operators/functions.
8. Tạo GiST indexes cho truy vấn ancestor/descendant.
9. So sánh adjacency list, materialized path, closure table và nested sets.
10. Xác định khi nào ltree không phù hợp, đặc biệt với DAG hoặc graph nhiều parent.
11. Chọn arrays, ranges, multiranges, network, full-text và spatial types khi phù hợp.
12. Thiết kế constraints, indexes và migration cho specialized data.
13. Đánh giá trade-offs về storage, update cost, query complexity và portability.
14. Xây dựng 80 bài tập thực hành với các mô hình dữ liệu PostgreSQL.

## 2. Vì sao cần mô hình dữ liệu chuyên biệt?

Mô hình quan hệ với columns có kiểu rõ ràng là lựa chọn mặc định tốt cho phần lớn dữ liệu nghiệp vụ. Tuy nhiên, một số miền dữ liệu có cấu trúc đặc thù:
- Attributes thay đổi theo loại sản phẩm.
- Hierarchy nhiều cấp.
- Khoảng thời gian hoặc khoảng số.
- Địa chỉ mạng và subnet.
- Tài liệu cần full-text search.
- Dữ liệu không gian.
- Tập hợp giá trị có cùng kiểu.

PostgreSQL cung cấp types, operators, index operator classes và extensions cho các trường hợp này.

### 2.1. Dùng type đúng giúp truy vấn rõ hơn

Một tstzrange biểu diễn khoảng thời gian với semantics về inclusive/exclusive bounds. Một inet biểu diễn địa chỉ mạng với operators về subnet. Một ltree biểu diễn path hierarchy với operators ancestor/descendant. Nếu lưu tất cả dưới dạng text, application phải tự parse và kiểm tra nhiều quy tắc.

### 2.2. Specialized type không thay thế data modeling

Một type tốt không tự quyết định:
- Ai được tạo/sửa dữ liệu.
- Cách kiểm soát uniqueness.
- Cách bảo đảm foreign keys.
- Cách version schema.
- Cách phân quyền.
- Cách replicate/backup/restore.

Những yêu cầu đó vẫn cần được thiết kế trong schema và application.

### 2.3. Extension là dependency vận hành

hstore và ltree được cung cấp qua PostgreSQL contrib/extension packaging trong nhiều bản phân phối. Server cần package tương thích, sau đó extension được tạo trong từng database. Backup/restore target và HA nodes cũng cần các files tương thích.

## 3. hstore là gì?

hstore là một extension cung cấp kiểu dữ liệu lưu một tập cặp key/value, trong đó key và value là text. Một key có thể có value SQL NULL. hstore là cấu trúc phẳng, không phải document tree lồng nhau.

Ví dụ một product có các thuộc tính tùy chọn:

~~~text
color => blue
size  => medium
material => cotton
~~~

Một row có thể lưu những keys khác nhau mà không cần thêm một column cho mỗi thuộc tính.

### 3.1. Khi nào hstore phù hợp?

- Thuộc tính mở rộng có dạng key/value đơn giản.
- Keys và values chủ yếu là text.
- Cấu trúc phẳng, không cần nested arrays/objects.
- Truy vấn thường kiểm tra key existence hoặc containment.
- Hệ thống đã có hstore và cần tương thích schema hiện tại.

### 3.2. Khi nào không phù hợp?

- Cần nested documents hoặc arrays.
- Cần lưu number/boolean/timestamp với kiểu JSON rõ ràng.
- Cần schema validation phức tạp.
- Attributes có quan hệ nghiệp vụ hoặc cần foreign keys.
- Một số keys thường xuyên được filter/join/sort và nên là columns typed.
- Cần portability sang database không hỗ trợ hstore.

### 3.3. Cài extension

~~~sql
CREATE EXTENSION hstore;
~~~

Kiểm tra:

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
WHERE extname = 'hstore';
~~~

Extension được cài trong database hiện tại. Nếu nhiều databases cần dùng hstore, tạo extension trong từng database.

### 3.4. Kiểm tra package

~~~sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'hstore';
~~~

Nếu không có kết quả, server có thể thiếu extension package hoặc provider không hỗ trợ. CREATE EXTENSION không tự tải package từ internet.

## 4. Tạo bảng có cột hstore

~~~sql
CREATE TABLE app.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    name text NOT NULL,
    attributes hstore NOT NULL DEFAULT ''::hstore
);
~~~

''::hstore là một hstore rỗng, khác với SQL NULL.

### 4.1. Chèn dữ liệu

~~~sql
INSERT INTO app.products (sku, name, attributes)
VALUES
(
    'TSHIRT-001',
    'Basic T-shirt',
    '"color"=>"blue", "size"=>"M", "material"=>"cotton"'::hstore
),
(
    'MUG-001',
    'Ceramic mug',
    '"color"=>"white", "capacity"=>"350ml"'::hstore
);
~~~

### 4.2. Cú pháp literal

hstore text representation dùng cặp key => value, phân tách bằng dấu phẩy. Keys/values có thể cần quote/escape nếu chứa dấu câu, dấu quote hoặc whitespace đặc biệt.

Trong ứng dụng, ưu tiên bind parameters và driver hỗ trợ hstore thay vì ghép chuỗi SQL thủ công.

### 4.3. Tạo bằng constructor

~~~sql
SELECT hstore(
    ARRAY['color', 'size', 'material'],
    ARRAY['blue', 'M', 'cotton']
);
~~~

Các arrays cần có cấu trúc phù hợp; keys/values được chuyển thành text theo function signature.

### 4.4. Empty hstore và NULL

~~~sql
SELECT
    ''::hstore AS empty_attributes,
    NULL::hstore AS missing_attributes;
~~~

Empty hstore là một tập không có pairs. SQL NULL có nghĩa toàn bộ attributes value chưa biết/không có. Chọn semantics phù hợp với domain và dùng NOT NULL/default khi cần.

## 5. Đọc giá trị từ hstore

Operator -> lấy value theo key và trả về text.

~~~sql
SELECT
    sku,
    attributes -> 'color' AS color,
    attributes -> 'size' AS size
FROM app.products;
~~~

### 5.1. Key không tồn tại

Nếu key không tồn tại, -> trả SQL NULL. Nếu key tồn tại nhưng value của nó là SQL NULL, kết quả cũng là SQL NULL. Dùng ? hoặc defined() nếu cần phân biệt.

### 5.2. Dùng trong filter

~~~sql
SELECT product_id, sku, name
FROM app.products
WHERE attributes -> 'color' = 'blue';
~~~

### 5.3. Cast value sang kiểu cần thiết

hstore lưu values dạng text, nên cast tường minh khi cần numeric/date/boolean:

~~~sql
SELECT
    sku,
    (attributes -> 'weight_grams')::integer AS weight_grams
FROM app.products
WHERE attributes ? 'weight_grams';
~~~

Cast có thể lỗi nếu dữ liệu không đúng định dạng. Validate khi ghi hoặc dùng một migration chuẩn hóa trước khi cast trong query quan trọng.

### 5.4. NULL semantics

attributes ? 'key' kiểm tra key có tồn tại. defined(attributes, 'key') kiểm tra key tồn tại và value không phải NULL. Hai điều kiện này khác nhau.

## 6. Kiểm tra key existence

Operator ? kiểm tra một key có tồn tại trong hstore hay không.

~~~sql
SELECT sku
FROM app.products
WHERE attributes ? 'material';
~~~

### 6.1. Kiểm tra tất cả keys

?& kiểm tra tất cả keys trong array có tồn tại:

~~~sql
SELECT sku
FROM app.products
WHERE attributes ?& ARRAY['color', 'size'];
~~~

### 6.2. Kiểm tra ít nhất một key

?| kiểm tra ít nhất một key trong array có tồn tại:

~~~sql
SELECT sku
FROM app.products
WHERE attributes ?| ARRAY['capacity', 'volume', 'size'];
~~~

### 6.3. Key tồn tại với value khác NULL

~~~sql
SELECT sku
FROM app.products
WHERE defined(attributes, 'color');
~~~

### 6.4. Key existence không phải validation

Một row có key weight_grams chưa chắc value là integer hợp lệ. Dùng constraints, application validation hoặc bảng attributes typed nếu cần bảo đảm dữ liệu.

## 7. Containment và equality

Operator @> kiểm tra hstore bên trái có chứa tất cả pairs của hstore bên phải hay không.

~~~sql
SELECT sku
FROM app.products
WHERE attributes @> '"color"=>"blue"'::hstore;
~~~

### 7.1. Nhiều pairs

~~~sql
SELECT sku
FROM app.products
WHERE attributes @> '"color"=>"blue", "size"=>"M"'::hstore;
~~~

Row cần chứa các key/value pairs được yêu cầu.

### 7.2. Contained by

<@ kiểm tra hstore bên trái có phải subset của hstore bên phải hay không.

~~~sql
SELECT *
FROM app.products
WHERE attributes <@ '"color"=>"blue", "size"=>"M", "material"=>"cotton"'::hstore;
~~~

### 7.3. Equality

Có thể so sánh hai hstore values bằng =. Equality xét nội dung key/value, không phụ thuộc thứ tự hiển thị của pairs.

~~~sql
SELECT *
FROM app.products
WHERE attributes = '"color"=>"white", "capacity"=>"350ml"'::hstore;
~~~

### 7.4. Chọn operator theo câu hỏi

- Key có tồn tại? Dùng ?.
- Tất cả keys có tồn tại? Dùng ?&.
- Có ít nhất một key? Dùng ?|.
- Có các pairs cụ thể? Dùng @>.
- Value của một key? Dùng ->.
- Cần tập con? Dùng <@.

## 8. Thêm và cập nhật hstore pairs

Operator || nối hai hstore values.

~~~sql
UPDATE app.products
SET attributes = attributes || '"season"=>"summer"'::hstore
WHERE sku = 'TSHIRT-001';
~~~

### 8.1. Cập nhật key hiện có

Khi hai hstore values có cùng key, pair ở phía phải ghi đè pair cùng key ở phía trái:

~~~sql
UPDATE app.products
SET attributes = attributes || '"color"=>"navy"'::hstore
WHERE sku = 'TSHIRT-001';
~~~

### 8.2. Thêm nhiều keys

~~~sql
UPDATE app.products
SET attributes = attributes ||
    '"color"=>"black", "size"=>"L"'::hstore
WHERE sku = 'TSHIRT-001';
~~~

### 8.3. Constructor trong update

~~~sql
UPDATE app.products
SET attributes = attributes ||
    hstore(ARRAY['material', 'care'], ARRAY['linen', 'hand wash'])
WHERE sku = 'TSHIRT-001';
~~~

### 8.4. Lost update

Nếu nhiều sessions cùng đọc-sửa-ghi toàn bộ hstore trong application, một update có thể ghi đè thay đổi của session khác nếu không có concurrency control. Dùng atomic SQL updates, row locks hoặc optimistic concurrency/version columns theo yêu cầu.

### 8.5. Kiểm tra giá trị trước khi ghi

Nếu key là một phần của business logic, validate allowed values. hstore không tự áp dụng kiểu dữ liệu cho từng key.

## 9. Xóa keys và pairs

Operator - có thể xóa key hoặc các pairs.

~~~sql
UPDATE app.products
SET attributes = attributes - 'season'
WHERE sku = 'TSHIRT-001';
~~~

Xóa nhiều keys:

~~~sql
UPDATE app.products
SET attributes = attributes - ARRAY['color', 'size']
WHERE sku = 'TSHIRT-001';
~~~

Xóa các pairs có trong hstore khác:

~~~sql
SELECT
    attributes - '"color"=>"blue"'::hstore
FROM app.products;
~~~

### 9.1. Xóa theo policy

Trước khi xóa attributes, xác định key còn được application version nào sử dụng không. Trong rolling deployments, schema/attribute changes cần tương thích ngược trong giai đoạn chuyển tiếp.

### 9.2. Không thay thế NULL bằng delete một cách tùy tiện

Key absent và key present with NULL có thể có semantics khác. Chọn representation rõ ràng.

## 10. Các hstore functions hữu ích

### 10.1. akeys và avals

~~~sql
SELECT
    akeys(attributes) AS keys,
    avals(attributes) AS values
FROM app.products;
~~~

akeys trả array các keys; avals trả array values.

### 10.2. each

~~~sql
SELECT
    p.sku,
    kv.key,
    kv.value
FROM app.products AS p
CROSS JOIN LATERAL each(p.attributes) AS kv(key, value);
~~~

each trả từng pair thành rows. Đây là cách hữu ích để thống kê attributes và tìm keys không đồng nhất.

### 10.3. slice

~~~sql
SELECT
    slice(attributes, ARRAY['color', 'size']) AS selected_attributes
FROM app.products;
~~~

slice trả hstore chỉ gồm các keys được yêu cầu.

### 10.4. exist và defined

~~~sql
SELECT
    exist(attributes, 'color') AS color_key_exists,
    defined(attributes, 'color') AS color_value_is_defined
FROM app.products;
~~~

exist tương ứng kiểm tra key tồn tại; defined kiểm tra value tồn tại và không NULL.

### 10.5. delete

Có thể dùng function delete(hstore, key) hoặc các operators tương ứng để xóa keys. Dùng function/operator theo nhu cầu đọc dễ hiểu.

### 10.6. Chuyển sang arrays

~~~sql
SELECT
    hstore_to_array(attributes) AS flat_array,
    hstore_to_matrix(attributes) AS key_value_matrix
FROM app.products;
~~~

Kết quả là representation dạng arrays, phù hợp export hoặc xử lý trong SQL. Không giả định thứ tự keys là thứ tự nghiệp vụ.

### 10.7. Chuyển sang JSON

~~~sql
SELECT hstore_to_jsonb(attributes)
FROM app.products;
~~~

Các hstore values được chuyển sang JSON representation; vì hstore lưu text, values thông thường trở thành JSON strings, còn hstore NULL được chuyển thành JSON null. Nếu cần JSON numbers/booleans, cần chuẩn hóa/cast có chủ đích.

## 11. GIN và GiST indexes cho hstore

Khi query key existence hoặc containment trên bảng lớn, sequential scan có thể tốn kém. hstore cung cấp operator classes cho GIN và GiST.

### 11.1. GIN index

~~~sql
CREATE INDEX products_attributes_gin_idx
    ON app.products
    USING GIN (attributes);
~~~

GIN phù hợp với truy vấn tìm keys và containment trên hstore.

### 11.2. Key existence

~~~sql
SELECT *
FROM app.products
WHERE attributes ? 'material';
~~~

### 11.3. Containment

~~~sql
SELECT *
FROM app.products
WHERE attributes @> '"color"=>"blue"'::hstore;
~~~

### 11.4. GiST index

~~~sql
CREATE INDEX products_attributes_gist_idx
    ON app.products
    USING GIST (attributes);
~~~

GiST là lựa chọn khác có thể hỗ trợ hstore operators. GIN/GiST có trade-offs về index size, build time, update cost và query patterns. Benchmark trên workload thực tế.

### 11.5. Expression B-tree index

Nếu một key cụ thể được filter/sort thường xuyên, expression index có thể phù hợp:

~~~sql
CREATE INDEX products_color_idx
    ON app.products ((attributes -> 'color'));
~~~

Query cần dùng expression tương thích:

~~~sql
SELECT *
FROM app.products
WHERE attributes -> 'color' = 'blue';
~~~

### 11.6. Index maintenance cost

Mỗi update hstore có thể yêu cầu cập nhật GIN/GiST index. Nếu attributes thay đổi liên tục và query ít dùng, index có thể làm write amplification lớn hơn lợi ích.

### 11.7. Partial expression index

~~~sql
CREATE INDEX products_weight_idx
    ON app.products (((attributes -> 'weight_grams')::integer))
    WHERE attributes ? 'weight_grams';
~~~

Đảm bảo mọi values của key đều có thể cast an toàn. Nếu có dữ liệu sai định dạng, index build có thể thất bại.

## 12. hstore và JSONB

JSONB là lựa chọn phổ biến cho flexible documents. hstore đơn giản hơn và có thể phù hợp với legacy schema hoặc attributes phẳng.

| Tiêu chí | hstore | JSONB |
| --- | --- | --- |
| Cấu trúc | Flat key/value | Nested objects/arrays/scalars |
| Value model | Text hoặc SQL NULL | JSON strings, numbers, booleans, null, arrays, objects |
| Nested data | Không | Có |
| Operators | Key existence, containment, concatenation, deletion | Rich path, containment, existence, mutation operators |
| Indexing | GIN/GiST operator classes | GIN và expression indexes, nhiều operator classes |
| Schema validation | Chủ yếu tự thiết kế | Có thể dùng constraints/functions, vẫn cần validation |
| Portability | Extension-specific | JSONB là built-in PostgreSQL type |
| Best fit | Simple text attributes | Flexible documents |

### 12.1. Khi nào giữ hstore?

- Existing application đã dùng hstore ổn định.
- Attributes phẳng, text-only.
- Query pattern dùng operators hstore hiệu quả.
- Không cần nested JSON.
- Migration cost lớn hơn lợi ích chuyển đổi.

### 12.2. Khi nào chọn JSONB?

- Attributes cần nested objects/arrays.
- Values có type JSON.
- Cần JSON path/query features.
- Dữ liệu đến từ API documents.
- Muốn dùng built-in type không cần cài hstore extension.

### 12.3. Không lưu mọi thứ vào JSONB/hstore

Các thuộc tính có semantics nghiệp vụ ổn định như price, status, tenant_id, created_at thường nên là columns typed có constraints/indexes rõ ràng. Flexible fields chỉ dành cho phần thực sự linh hoạt.

## 13. Migration từ hstore sang JSONB

Một migration có thể dùng function hstore_to_jsonb:

~~~sql
ALTER TABLE app.products
ADD COLUMN attributes_jsonb jsonb;
~~~

Backfill:

~~~sql
UPDATE app.products
SET attributes_jsonb = hstore_to_jsonb(attributes)
WHERE attributes_jsonb IS NULL;
~~~

### 13.1. Kiểm tra conversion

So sánh số rows, keys và values trên sample. Vì hstore values là text, conversion không tự suy luận numeric/boolean types cho mọi keys.

### 13.2. Typed conversion

Nếu weight_grams phải là number, cần cast rõ ràng khi xây JSONB hoặc chuẩn hóa trong application:

~~~sql
UPDATE app.products
SET attributes_jsonb =
    jsonb_set(
        hstore_to_jsonb(attributes),
        '{weight_grams}',
        to_jsonb((attributes -> 'weight_grams')::integer),
        true
    )
WHERE attributes ? 'weight_grams';
~~~

Chỉ chạy khi values đã validate là integer hợp lệ.

### 13.3. Dual write

Trong quá trình chuyển ứng dụng, có thể cần dual write hoặc compatibility layer. Phải tránh hai representations drift. Chọn source of truth và quy trình reconciliation.

### 13.4. Index migration

Tạo JSONB GIN/expression indexes theo query patterns mới. Không giả định index hstore có thể dùng cho JSONB column.

### 13.5. Cutover

So query results, constraints, performance và application behavior. Chỉ drop hstore column/extension dependency sau khi mọi consumers đã chuyển.

## 14. ltree là gì?

ltree là extension cung cấp kiểu dữ liệu để biểu diễn một đường dẫn phân cấp bằng chuỗi labels phân tách bởi dấu chấm. Mỗi path mô tả vị trí của một node trong một hierarchy.

Ví dụ:

~~~text
Top
Top.Science
Top.Science.Astronomy
Top.Science.Physics
Top.Arts
Top.Arts.Music
~~~

Top.Science.Astronomy có ancestors Top và Top.Science; nó là descendant của Top.Science.

### 14.1. Cài extension

~~~sql
CREATE EXTENSION ltree;
~~~

Kiểm tra:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'ltree';
~~~

### 14.2. Kiểu dữ liệu

- ltree: path gồm labels.
- lquery: pattern để match labels/path.
- ltxtquery: text-search-like query trên labels.

### 14.3. Label design

Dùng labels ổn định, không phụ thuộc display name của người dùng. Một label nên có canonical form rõ ràng; chuẩn hóa dấu cách/ký tự đặc biệt thành ID hoặc slug an toàn. Lưu display name trong column riêng.

### 14.4. Không phải mọi string đều là ltree hợp lệ

Path có grammar riêng. Dùng text2ltree hoặc cast sau khi normalize/validate. Không ghép user input trực tiếp vào SQL literal.

## 15. Tạo bảng hierarchy với ltree

~~~sql
CREATE TABLE app.categories (
    category_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    path ltree NOT NULL UNIQUE,
    label text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Chèn một hierarchy:

~~~sql
INSERT INTO app.categories (path, label)
VALUES
    ('Top'::ltree, 'Top'),
    ('Top.Science'::ltree, 'Science'),
    ('Top.Science.Astronomy'::ltree, 'Astronomy'),
    ('Top.Science.Physics'::ltree, 'Physics'),
    ('Top.Arts'::ltree, 'Arts'),
    ('Top.Arts.Music'::ltree, 'Music');
~~~

### 15.1. Unique path

UNIQUE(path) bảo đảm mỗi path chỉ xuất hiện một lần. Điều này không tự bảo đảm mọi ancestor rows đều tồn tại. Nếu cần referential integrity cho parent, thiết kế thêm parent relation/trigger hoặc quản lý hierarchy qua controlled procedures.

### 15.2. Node identity và path

category_id là identity ổn định cho foreign keys. path là representation vị trí trong hierarchy. Nếu node chuyển parent, path của nó và descendants phải thay đổi.

### 15.3. Display labels

Không dùng display name trực tiếp làm path nếu người dùng có thể đổi tên, nhập dấu chấm hoặc ký tự không hợp lệ. Dùng slug/immutable code hoặc encoded ID.

### 15.4. Root path

Chọn quy ước root rõ ràng, ví dụ Top, Company, hoặc một root token theo domain. Tránh nhiều root không liên quan nếu business model yêu cầu một tree duy nhất.

## 16. Truy vấn ancestors và descendants

Operator @> kiểm tra path bên trái là ancestor (hoặc bằng) path bên phải.

~~~sql
SELECT path, label
FROM app.categories
WHERE path @> 'Top.Science.Astronomy'::ltree
ORDER BY nlevel(path);
~~~

Kết quả là node và các ancestors của nó.

### 16.1. Tìm descendants

Operator <@ kiểm tra path bên trái là descendant (hoặc bằng) path bên phải.

~~~sql
SELECT path, label
FROM app.categories
WHERE path <@ 'Top.Science'::ltree
ORDER BY path;
~~~

Kết quả gồm Top.Science và các descendants.

### 16.2. Tìm descendants không bao gồm node hiện tại

~~~sql
SELECT path, label
FROM app.categories
WHERE path <@ 'Top.Science'::ltree
  AND path <> 'Top.Science'::ltree;
~~~

### 16.3. Độ sâu

~~~sql
SELECT
    path,
    nlevel(path) AS depth
FROM app.categories
ORDER BY depth, path;
~~~

nlevel trả số labels trong path.

### 16.4. Lấy prefix

~~~sql
SELECT subpath(
    'Top.Science.Astronomy'::ltree,
    0,
    2
);
~~~

subpath lấy một phần path theo offset/length. Offset tính từ đầu path; đọc function documentation để xử lý negative offsets và boundaries.

### 16.5. Tìm vị trí subpath

~~~sql
SELECT index(
    'Top.Science.Astronomy'::ltree,
    'Science'::ltree
);
~~~

Hàm index tìm vị trí subpath trong path; nếu không tìm thấy, kết quả thể hiện không có match theo function semantics.

### 16.6. Lowest common ancestor

~~~sql
SELECT lca(
    'Top.Science.Astronomy'::ltree,
    'Top.Science.Physics'::ltree
);
~~~

Kết quả là path ancestor chung thấp nhất, ở ví dụ này là Top.Science.

## 17. lquery patterns

lquery cho phép match paths theo labels và wildcard patterns.

~~~sql
SELECT path, label
FROM app.categories
WHERE path ~ 'Top.*.Astronomy'::lquery;
~~~

### 17.1. Wildcard

* có thể match một label theo lquery semantics. Dùng pattern phù hợp với độ sâu hierarchy.

### 17.2. Match nhiều levels

~~~sql
SELECT path
FROM app.categories
WHERE path ~ 'Top.*{1,2}.Music'::lquery;
~~~

Quantifier điều khiển số labels được match bởi pattern component theo grammar của lquery.

### 17.3. Exact path vs pattern

So sánh path = 'Top.Arts.Music'::ltree là equality. path ~ 'Top.*.Music'::lquery là pattern matching. Chọn operator đơn giản nhất đáp ứng truy vấn.

### 17.4. User-generated patterns

Không nối pattern từ input chưa validate. lquery có grammar và wildcard/quantifier semantics; parameterize query và validate business input.

## 18. Các ltree functions thường dùng

### 18.1. text2ltree và ltree2text

~~~sql
SELECT text2ltree('Top.Science.Astronomy');
SELECT ltree2text('Top.Science.Astronomy'::ltree);
~~~

### 18.2. nlevel

~~~sql
SELECT nlevel('Top.Science.Astronomy'::ltree);
~~~

### 18.3. subpath

~~~sql
SELECT subpath('Top.Science.Astronomy'::ltree, 1, 2);
~~~

### 18.4. lca

~~~sql
SELECT lca(
    'Top.Arts.Music'::ltree,
    'Top.Arts.Painting'::ltree
);
~~~

### 18.5. Concatenation

Operator || nối hai ltree paths:

~~~sql
SELECT
    'Top.Science'::ltree || 'Astronomy.Stars'::ltree;
~~~

### 18.6. Chuẩn hóa input

Chuyển từ application slug sang ltree path qua validation layer. Không coi cast text thành ltree là validation đầy đủ cho business hierarchy.

## 19. Indexing ltree

GiST là index thường dùng cho các truy vấn hierarchy và pattern matching của ltree.

~~~sql
CREATE INDEX categories_path_gist_idx
    ON app.categories
    USING GIST (path);
~~~

### 19.1. Ancestor/descendant queries

~~~sql
SELECT *
FROM app.categories
WHERE path <@ 'Top.Science'::ltree;
~~~

GiST index có thể hỗ trợ các ltree operators phù hợp.

### 19.2. Pattern queries

~~~sql
SELECT *
FROM app.categories
WHERE path ~ 'Top.*.Astronomy'::lquery;
~~~

Kiểm tra operator class và query plan trên version đang chạy.

### 19.3. B-tree index

Nếu workload chủ yếu equality/order theo path, B-tree index có thể phù hợp:

~~~sql
CREATE INDEX categories_path_btree_idx
    ON app.categories USING BTREE (path);
~~~

B-tree và GiST phục vụ operator families/query patterns khác nhau. Không tạo cả hai nếu chưa có nhu cầu đo được.

### 19.4. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM app.categories
WHERE path <@ 'Top.Science'::ltree;
~~~

Table nhỏ có thể khiến planner chọn sequential scan dù index tồn tại. Kiểm tra estimated/actual rows và table size trước khi kết luận index không hoạt động.

### 19.5. Index write cost

Mỗi thay đổi path phải cập nhật index. Khi di chuyển một subtree lớn, nhiều rows và index entries có thể thay đổi. Tính WAL, lock duration và replication impact.

## 20. Cập nhật và di chuyển subtree

Materialized path lưu toàn bộ ancestor path trong mỗi row. Khi một node chuyển sang parent khác, path của node và descendants cần được thay đổi.

Giả sử chuyển subtree Top.Science sang Top.Knowledge.

### 20.1. Update root node

~~~sql
UPDATE app.categories
SET path = 'Top.Knowledge'::ltree
WHERE path = 'Top.Science'::ltree;
~~~

### 20.2. Update descendants

Với descendants nằm dưới old parent, lấy suffix sau prefix cũ rồi ghép prefix mới:

~~~sql
UPDATE app.categories
SET path =
    'Top.Knowledge'::ltree
    || subpath(path, nlevel('Top.Science'::ltree))
WHERE path <@ 'Top.Science'::ltree
  AND path <> 'Top.Science'::ltree;
~~~

Hai updates phải được điều phối để không tạo trạng thái hierarchy không nhất quán cho readers. Trong production, thực hiện trong transaction phù hợp, khóa các rows cần thiết và bảo đảm UNIQUE(path) không bị conflict.

### 20.3. Unique conflict

Nếu destination path đã tồn tại, update có thể vi phạm UNIQUE(path). Preflight kiểm tra destination subtree và thiết kế conflict handling.

### 20.4. Atomic move

Nếu application yêu cầu không ai nhìn thấy hierarchy ở trạng thái nửa chuyển, dùng một transaction để update root và descendants cùng nhau, với locking strategy phù hợp.

### 20.5. Large subtree

Một subtree lớn có thể tạo lượng WAL và row/index updates đáng kể. Cân nhắc batch/chunk migration, maintenance window hoặc model khác nếu moves thường xuyên.

## 21. ltree và adjacency list

Adjacency list lưu mỗi node cùng parent_id. Đây là mô hình cây đơn giản và rất phổ biến.

~~~sql
CREATE TABLE app.category_nodes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id bigint REFERENCES app.category_nodes(id),
    name text NOT NULL
);
~~~

### 21.1. Lấy children trực tiếp

~~~sql
SELECT *
FROM app.category_nodes
WHERE parent_id = $1;
~~~

Index parent_id:

~~~sql
CREATE INDEX category_nodes_parent_idx
    ON app.category_nodes (parent_id);
~~~

### 21.2. Recursive CTE để lấy descendants

~~~sql
WITH RECURSIVE descendants AS (
    SELECT
        id,
        parent_id,
        name,
        0 AS depth
    FROM app.category_nodes
    WHERE id = $1

    UNION ALL

    SELECT
        child.id,
        child.parent_id,
        child.name,
        parent.depth + 1
    FROM app.category_nodes AS child
    JOIN descendants AS parent
      ON child.parent_id = parent.id
)
SELECT *
FROM descendants
ORDER BY depth, id;
~~~

### 21.3. Ưu điểm

- Một row đại diện một node.
- parent_id có foreign key.
- Di chuyển node thường chỉ đổi parent_id.
- Không cần cập nhật path cho mọi descendants.
- Phù hợp khi hierarchy thay đổi thường xuyên.

### 21.4. Nhược điểm

- Truy vấn toàn subtree cần recursive CTE.
- Depth lớn có thể làm query phức tạp.
- Cần ngăn cycles bằng business logic/trigger hoặc controlled procedure; foreign key không tự cấm node trở thành ancestor của chính nó.

### 21.5. Khi chọn adjacency list

Chọn khi tree có nhiều updates/moves, cần parent relationship đơn giản và recursive queries vẫn đáp ứng hiệu năng.

## 22. ltree/materialized path so với adjacency list

| Tiêu chí | Adjacency list | ltree/materialized path |
| --- | --- | --- |
| Parent lookup | Trực tiếp qua parent_id | Lấy prefix hoặc lưu parent_id bổ sung |
| Subtree lookup | Recursive CTE | Path containment |
| Move subtree | Thường đổi parent_id của node | Cập nhật paths của descendants |
| Referential integrity | FK tới parent row | Path uniqueness không bảo đảm parent tồn tại |
| Index | B-tree parent_id | GiST/B-tree trên path |
| Write cost khi move | Thường thấp | Có thể cao nếu subtree lớn |
| Read hierarchy | Recursive query | Path operators |
| DAG/multiple parents | Có thể dùng edge table | Một path đơn không biểu diễn đầy đủ |

### 22.1. Hybrid model

Có thể lưu cả parent_id và path:
- parent_id là quan hệ chuẩn cho referential integrity.
- path hỗ trợ subtree queries nhanh.
- Một transaction/procedure chịu trách nhiệm giữ hai representation đồng bộ.

Hybrid model tăng write complexity. Cần invariant và reconciliation job.

### 22.2. Không lưu redundant data tùy tiện

Nếu path có thể được tính từ parent relationships nhưng được lưu để tăng tốc, phải xác định source of truth và cách sửa khi hierarchy thay đổi.

## 23. Closure table

Closure table lưu mọi ancestor-descendant pair cùng depth.

~~~sql
CREATE TABLE app.category_closure (
    ancestor_id bigint NOT NULL REFERENCES app.category_nodes(id),
    descendant_id bigint NOT NULL REFERENCES app.category_nodes(id),
    depth integer NOT NULL CHECK (depth >= 0),
    PRIMARY KEY (ancestor_id, descendant_id)
);

CREATE INDEX category_closure_descendant_idx
    ON app.category_closure (descendant_id, ancestor_id);
~~~

Một node thường có self-row với depth 0; node con có pair với parent depth 1 và các ancestors xa hơn với depth tương ứng.

### 23.1. Subtree query

~~~sql
SELECT n.*, c.depth
FROM app.category_closure AS c
JOIN app.category_nodes AS n
  ON n.id = c.descendant_id
WHERE c.ancestor_id = $1
ORDER BY c.depth, n.id;
~~~

### 23.2. Ancestor query

~~~sql
SELECT n.*, c.depth
FROM app.category_closure AS c
JOIN app.category_nodes AS n
  ON n.id = c.ancestor_id
WHERE c.descendant_id = $1
ORDER BY c.depth DESC;
~~~

### 23.3. Ưu điểm

- Ancestor/descendant lookups đơn giản.
- Có thể dùng foreign keys cho cả hai ends.
- Hỗ trợ hierarchy query nhanh bằng B-tree.
- Có thể mở rộng cho graph edges nếu cho phép nhiều parents, nhưng semantics cần được định nghĩa riêng.

### 23.4. Nhược điểm

- Số rows có thể tăng theo số ancestor-descendant pairs.
- Insert/move cần cập nhật nhiều closure rows.
- Dễ sai nếu không cập nhật closure và node table cùng transaction.

### 23.5. Khi chọn closure table

Chọn khi subtree/ancestor queries rất thường xuyên, hierarchy updates ít hơn reads và cần relational integrity rõ.

## 24. Nested sets

Nested sets gán mỗi node hai giá trị left/right (hoặc lft/rgt) để biểu diễn vị trí trong traversal.

~~~sql
CREATE TABLE app.category_nested (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    lft bigint NOT NULL,
    rgt bigint NOT NULL,
    CHECK (lft < rgt),
    UNIQUE (lft),
    UNIQUE (rgt)
);
~~~

### 24.1. Subtree query

~~~sql
SELECT child.*
FROM app.category_nested AS parent
JOIN app.category_nested AS child
  ON child.lft >= parent.lft
 AND child.rgt <= parent.rgt
WHERE parent.id = $1
ORDER BY child.lft;
~~~

### 24.2. Ancestor query

~~~sql
SELECT parent.*
FROM app.category_nested AS node
JOIN app.category_nested AS parent
  ON parent.lft <= node.lft
 AND parent.rgt >= node.rgt
WHERE node.id = $1
ORDER BY parent.lft;
~~~

### 24.3. Ưu điểm

Subtree reads có thể đơn giản và hiệu quả.

### 24.4. Nhược điểm

Insert/move có thể yêu cầu thay đổi nhiều left/right values. Với hierarchy thay đổi thường xuyên, write amplification và locking có thể lớn.

### 24.5. Khi chọn nested sets

Phù hợp với taxonomy gần như tĩnh, đọc subtree nhiều và update hiếm. Cần một transaction/procedure quản lý numbering nhất quán.

## 25. Graph và DAG: khi hierarchy có nhiều parent

ltree biểu diễn một path đơn. Một node trong tree có một ancestor chain. Nếu một node có nhiều parents hoặc relationships tạo cycles, một path đơn không thể biểu diễn toàn bộ graph.

### 25.1. Edge table

~~~sql
CREATE TABLE app.graph_nodes (
    node_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label text NOT NULL
);

CREATE TABLE app.graph_edges (
    source_id bigint NOT NULL REFERENCES app.graph_nodes(node_id),
    target_id bigint NOT NULL REFERENCES app.graph_nodes(node_id),
    edge_type text NOT NULL,
    PRIMARY KEY (source_id, target_id, edge_type)
);

CREATE INDEX graph_edges_target_idx
    ON app.graph_edges (target_id, source_id);
~~~

### 25.2. Recursive traversal

Dùng recursive CTE để duyệt edges. Với graph có cycles, cần cycle detection/path tracking hoặc cơ chế CYCLE của PostgreSQL versions hỗ trợ.

### 25.3. Không dùng ltree cho mọi graph

Nếu một entity có nhiều parents, relationships có loại, hoặc cycles được phép, edge table là representation phù hợp hơn. Có thể dùng ltree cho một materialized traversal/path cụ thể nhưng phải xác định path nào là canonical.

## 26. Specialized data model: JSONB

JSONB là built-in type cho JSON documents ở dạng binary representation.

~~~sql
CREATE TABLE app.api_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
~~~

### 26.1. Truy cập fields

~~~sql
SELECT
    payload ->> 'event_type' AS event_type,
    payload #>> '{customer,address,city}' AS city
FROM app.api_events;
~~~

-> trả JSON/JSONB; ->> trả text. #>/#>> truy cập theo path array.

### 26.2. Containment

~~~sql
SELECT *
FROM app.api_events
WHERE payload @> '{"event_type":"order.created"}'::jsonb;
~~~

### 26.3. GIN index

~~~sql
CREATE INDEX api_events_payload_gin_idx
    ON app.api_events USING GIN (payload);
~~~

Có các operator classes JSONB khác nhau với trade-offs. Chọn jsonb_ops hoặc jsonb_path_ops theo operators và query patterns cần hỗ trợ.

### 26.4. Typed columns vẫn quan trọng

Các keys được filter/sort/join thường xuyên hoặc có constraints mạnh nên cân nhắc tách thành columns typed. JSONB không tự thay foreign keys hoặc domain constraints.

## 27. Specialized data model: arrays

Arrays lưu tập hợp values cùng element type.

~~~sql
CREATE TABLE app.articles (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    tags text[] NOT NULL DEFAULT '{}'
);
~~~

### 27.1. Containment và overlap

~~~sql
SELECT *
FROM app.articles
WHERE tags @> ARRAY['postgresql'];

SELECT *
FROM app.articles
WHERE tags && ARRAY['database', 'sql'];
~~~

### 27.2. GIN index

~~~sql
CREATE INDEX articles_tags_gin_idx
    ON app.articles USING GIN (tags);
~~~

### 27.3. Array vs child table

Arrays tiện cho collection nhỏ, không cần per-element foreign key/metadata. Nếu mỗi tag cần owner, status, description, join, uniqueness hoặc independent lifecycle, dùng normalized child table.

### 27.4. Array update

Array operations có thể rewrite value và update GIN index. Với arrays lớn hoặc thay đổi từng element thường xuyên, cân nhắc relational model.

## 28. Specialized data model: range và multirange

Range types biểu diễn một khoảng liên tục, chẳng hạn khoảng ngày hoặc thời gian.

Các built-in range types phổ biến:
- int4range.
- int8range.
- numrange.
- tsrange.
- tstzrange.
- daterange.

### 28.1. Tạo range

~~~sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)') AS billing_period;
~~~

[) có nghĩa include lower bound, exclude upper bound. Đây là convention hữu ích để tránh overlap giữa các periods liền nhau.

### 28.2. Overlap

Operator && kiểm tra hai ranges có overlap hay không.

~~~sql
SELECT *
FROM app.bookings
WHERE during && tstzrange($1, $2, '[)');
~~~

### 28.3. Contains

~~~sql
SELECT *
FROM app.bookings
WHERE during @> now();
~~~

### 28.4. Exclusion constraint

~~~sql
CREATE EXTENSION btree_gist;

CREATE TABLE app.room_reservations (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING GIST (
        room_id WITH =,
        during WITH &&
    )
);
~~~

Constraint ngăn cùng room có hai reservations overlap. btree_gist cung cấp GiST operator classes cho nhiều scalar types để kết hợp equality với range overlap.

### 28.5. Multirange

Multirange biểu diễn tập hợp các ranges không liên tục và được hỗ trợ từ PostgreSQL 14. Dùng khi một entity có nhiều time windows rời nhau.

### 28.6. Boundary semantics

Phân biệt inclusive/exclusive, unbounded bounds và empty ranges. Chuẩn hóa convention trước khi xây query/constraint.

## 29. Specialized data model: network types

PostgreSQL có các types:
- inet: IPv4 hoặc IPv6 host/address, có thể kèm netmask.
- cidr: IPv4/IPv6 network.
- macaddr và macaddr8: hardware addresses.

### 29.1. Tạo columns

~~~sql
CREATE TABLE app.network_assets (
    asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host_ip inet NOT NULL,
    subnet cidr
);
~~~

### 29.2. Subnet containment

~~~sql
SELECT *
FROM app.network_assets
WHERE host_ip <<= '10.20.0.0/16'::inet;
~~~

Các network operators cho phép kiểm tra subnet relationships thay vì parse strings thủ công.

### 29.3. Host/network distinction

Dùng inet cho địa chỉ host có thể có mask; dùng cidr cho network canonical. Validate domain semantics trước khi ghi.

### 29.4. Indexing

B-tree có thể hữu ích cho equality/order; các operator classes GiST/SP-GiST được hỗ trợ tùy type/version cho một số network operations. Kiểm tra documentation và EXPLAIN cho operator cụ thể.

## 30. Specialized data model: full-text search

PostgreSQL full-text search dùng tsvector và tsquery.

~~~sql
ALTER TABLE app.documents
ADD COLUMN search_vector tsvector;
~~~

Tạo vector:

~~~sql
UPDATE app.documents
SET search_vector =
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''));
~~~

### 30.1. GIN index

~~~sql
CREATE INDEX documents_search_gin_idx
    ON app.documents USING GIN (search_vector);
~~~

### 30.2. Query

~~~sql
SELECT *
FROM app.documents
WHERE search_vector @@ plainto_tsquery('english', 'postgres database');
~~~

### 30.3. Configuration

Language configuration ảnh hưởng stemming, stop words và tokenization. Chọn configuration phù hợp nội dung, có thể dùng simple cho tokenization không stemming theo ngôn ngữ.

### 30.4. Maintenance

Nếu dùng generated column/trigger hoặc application-managed vector, bảo đảm search_vector được cập nhật khi source text thay đổi. GIN index tăng write cost.

## 31. Specialized data model: trigram similarity

Extension pg_trgm cung cấp trigram-based similarity và operators cho fuzzy text search.

~~~sql
CREATE EXTENSION pg_trgm;

CREATE INDEX customers_name_trgm_idx
    ON app.customers USING GIN (name gin_trgm_ops);
~~~

### 31.1. Similarity

~~~sql
SELECT
    name,
    similarity(name, 'Postgres') AS score
FROM app.customers
ORDER BY score DESC
LIMIT 20;
~~~

### 31.2. LIKE/ILIKE

pg_trgm có thể hỗ trợ một số LIKE/ILIKE patterns có đủ trigrams. Pattern quá ngắn có thể không hiệu quả.

### 31.3. Threshold

Các similarity thresholds ảnh hưởng operator results. Quản lý thresholds theo session/application nếu dùng operators dựa trên similarity.

### 31.4. Không thay full-text search

Trigram hữu ích cho typo/fuzzy matching và substring-like search; full-text search phù hợp hơn với tokenization, stemming và document search semantics.

## 32. Specialized data model: spatial types

PostGIS bổ sung geometry/geography types, spatial functions và spatial indexes.

### 32.1. Geometry vs geography

- geometry dùng planar coordinate system; đơn vị/phép đo phụ thuộc SRID.
- geography hỗ trợ các phép toán trên bề mặt Trái Đất với semantics phù hợp cho global coordinates, nhưng có trade-offs về performance/function support.

### 32.2. Extension

~~~sql
CREATE EXTENSION postgis;
~~~

Package phải có trên server và provider phải hỗ trợ.

### 32.3. Spatial index

~~~sql
CREATE INDEX places_geom_gist_idx
    ON app.places USING GIST (geom);
~~~

### 32.4. Spatial query

~~~sql
SELECT *
FROM app.places
WHERE ST_DWithin(
    geom,
    ST_SetSRID(ST_MakePoint($1, $2), 4326),
    $3
);
~~~

Ví dụ cần đảm bảo SRID, geometry/geography type và distance units tương thích. Với geometry, distance units phụ thuộc coordinate system; không dùng degrees như meters.

### 32.5. Spatial modeling

Lưu SRID rõ ràng, validate geometry type/dimensions và chọn GiST/SP-GiST/operator support theo truy vấn thực tế.

## 33. Specialized data model: UUID và identifiers

UUID là built-in type dùng cho identifiers phân tán hoặc cần tránh sequence coordination giữa systems.

~~~sql
CREATE TABLE app.external_events (
    event_id uuid PRIMARY KEY,
    payload jsonb NOT NULL
);
~~~

### 33.1. Trade-offs

Random UUID values có thể làm B-tree insertion locality kém hơn sequential integer keys. UUID variants có locality/time ordering khác nhau; chọn theo generator/version và privacy requirements.

### 33.2. Không dùng UUID vì mọi thứ đều cần phân tán

BIGINT identity thường nhỏ hơn và index-friendly cho hệ thống single-writer. Chọn theo integration, generation và data lifecycle.

## 34. Specialized data model: XML và composite types

### 34.1. XML

PostgreSQL có xml type và các functions để parse/query XML. Dùng khi integration bắt buộc XML hoặc cần lưu/kiểm tra XML documents. Với document APIs mới, JSONB thường phổ biến hơn.

### 34.2. Composite types

Composite types biểu diễn record gồm nhiều fields có kiểu. Chúng có thể hữu ích cho function arguments/results hoặc domain-specific structured values.

~~~sql
CREATE TYPE app.address_type AS (
    street text,
    city text,
    postal_code text
);
~~~

### 34.3. Domain types

DOMAIN tạo type dựa trên base type với constraints dùng lại:

~~~sql
CREATE DOMAIN app.nonnegative_amount AS numeric(14,2)
CHECK (VALUE >= 0);
~~~

### 34.4. Khi nào tách bảng?

Nếu một structured value cần foreign keys, independent updates, indexing từng child hoặc nhiều rows, normalized tables thường phù hợp hơn composite/JSON-like storage.

## 35. Chọn mô hình cho hierarchy

| Mô hình | Read subtree | Move node | Integrity | Phù hợp |
| --- | --- | --- | --- | --- |
| Adjacency list | Recursive CTE | Rẻ hơn | Parent FK trực tiếp | Tree thay đổi thường xuyên |
| ltree/materialized path | Path containment | Cập nhật descendants | Cần quản lý parent/path consistency | Subtree reads thường xuyên |
| Closure table | Join ancestor-descendant | Cập nhật nhiều pairs | FK cho endpoints | Ancestor queries thường xuyên |
| Nested sets | Range predicate | Có thể tốn nhiều updates | Cần quản lý left/right | Hierarchy gần như tĩnh |
| Edge table | Recursive graph traversal | Thêm/xóa edges | FK trên endpoints | DAG/graph nhiều parent |

### 35.1. Chọn theo read/write ratio

Nếu subtree reads chiếm đa số và hierarchy ít thay đổi, ltree/closure table có thể có lợi. Nếu moves thường xuyên, adjacency list có thể đơn giản hơn.

### 35.2. Chọn theo relationship cardinality

Nếu mỗi node có tối đa một parent, tree models phù hợp. Nếu node có nhiều parents, cần DAG/graph representation hoặc quan hệ edges.

### 35.3. Chọn theo integrity needs

Foreign keys và constraints nên bảo đảm invariants quan trọng. Một materialized path có thể cần trigger/procedure để bảo đảm parent path tồn tại và descendants đồng bộ.

### 35.4. Chọn theo query patterns

Liệt kê query quan trọng trước khi chọn type:
- Get direct children.
- Get all descendants.
- Get ancestors.
- Find lowest common ancestor.
- Move subtree.
- Search by label.
- Traverse multiple relationship types.
- Find cycles/reachability.

## 36. Constraints cho flexible attributes

hstore/JSONB cho phép fields linh hoạt nhưng không tự bảo đảm domain validity.

### 36.1. Required keys

Có thể dùng CHECK:

~~~sql
ALTER TABLE app.products
ADD CONSTRAINT products_color_required
CHECK (attributes ? 'color');
~~~

### 36.2. Allowed values

~~~sql
ALTER TABLE app.products
ADD CONSTRAINT products_color_allowed
CHECK (
    NOT (attributes ? 'color')
    OR attributes -> 'color' IN ('black', 'white', 'blue')
);
~~~

Nếu key có thể chứa SQL NULL, xác định behavior của CHECK với NULL. PostgreSQL CHECK chỉ loại row khi expression FALSE; UNKNOWN/NULL không được xem là FALSE. Dùng IS TRUE/IS NOT FALSE theo logic mong muốn.

### 36.3. Typed attributes

Nếu weight_grams là numeric, một CHECK có thể validate format nhưng cast sai format có thể raise error. Với nhiều attributes typed, normalized table hoặc JSONB schema validation function có thể dễ quản lý hơn.

### 36.4. Flexible schema không có nghĩa schema-less

Ghi lại allowed keys, value formats, defaults, owners, deprecation process và data retention. Versioning của attribute definitions vẫn cần được quản lý.

## 37. Indexing specialized types

Index cần hỗ trợ đúng operators được query sử dụng.

| Data model | Index thường gặp | Query pattern |
| --- | --- | --- |
| hstore | GIN/GiST; expression B-tree | Key existence, containment, selected key |
| ltree | GiST; B-tree equality/order | Ancestor/descendant, lquery, equality |
| JSONB | GIN/expression B-tree | Containment, path/key filters |
| Arrays | GIN | Contains/overlap |
| Ranges | GiST/SP-GiST tùy type/operator | Overlap/contains |
| inet/cidr | B-tree và supported GiST/SP-GiST ops | Equality/subnet |
| tsvector | GIN/GiST | Full-text match |
| PostGIS | GiST/SP-GiST tùy geometry/operator | Spatial predicates |
| pg_trgm text | GIN/GiST trigram opclass | Similarity/LIKE/ILIKE |

### 37.1. Operator class

Một index chỉ hỗ trợ những operators mà operator class của nó cung cấp. Đừng giả định mọi operators trên type đều dùng được với mọi index method.

### 37.2. Query expression

Expression index cần query expression tương thích. Ví dụ index trên attributes -> color phục vụ expression đó, không tự động phục vụ mọi JSON conversion.

### 37.3. Selectivity

Index có thể không hữu ích nếu predicate match phần lớn rows. Planner có thể chọn sequential scan là đúng.

### 37.4. Index maintenance

Specialized types có thể tạo index lớn và write overhead cao. Đo index size, build duration, WAL rate và update cost.

## 38. Data migration giữa mô hình

Migration giữa hstore, JSONB, ltree và relational tables nên có kế hoạch rõ ràng.

### 38.1. Expand

Thêm representation mới hoặc columns mới, tạo indexes/constraints cần thiết và deploy code tương thích.

### 38.2. Backfill

Backfill theo batches nếu bảng lớn. Theo dõi WAL, locks, replica lag và disk capacity.

### 38.3. Validate

So sánh row counts, values, hierarchy relationships, duplicate keys, orphan nodes và query results.

### 38.4. Dual write/cutover

Xác định source of truth. Nếu dual write, có reconciliation để phát hiện drift. Cutover bằng feature flag hoặc release step.

### 38.5. Contract

Sau thời gian quan sát, dừng writes representation cũ, archive nếu cần rồi drop column/extension dependency theo change plan.

### 38.6. Rollback

Rollback schema không nhất thiết khôi phục dữ liệu đã transform. Giữ backup và migration mapping đủ để phục hồi theo business requirement.

## 39. Performance và storage trade-offs

### 39.1. Flexible columns

hstore/JSONB giảm số columns thay đổi liên tục nhưng có thể làm query typed values phức tạp hơn. Attributes filter thường xuyên nên cân nhắc expression indexes hoặc columns riêng.

### 39.2. Path denormalization

ltree lưu ancestor path trong mỗi row. Subtree reads nhanh, nhưng move subtree cập nhật nhiều rows.

### 39.3. GIN indexes

GIN phù hợp inverted lookup nhưng có thể tốn storage và update work. Với write-heavy tables, cân nhắc fastupdate/pending list behavior theo operator class và version; không tuning nếu chưa có evidence.

### 39.4. GiST indexes

GiST hỗ trợ nhiều specialized operators như hierarchy/range/spatial. Hiệu quả phụ thuộc operator class, data distribution và query.

### 39.5. TOAST

hstore/JSONB values lớn có thể được TOAST. Theo dõi pg_column_size, pg_total_relation_size và table/index growth. Đừng giả định flexible values luôn nhỏ.

### 39.6. Cache locality

Một JSONB/hstore column chứa nhiều fields có thể đọc nhiều bytes hơn khi query chỉ cần một thuộc tính. Tách hot attributes thành columns có thể cải thiện selectivity/cache behavior.

## 40. Bảo mật và vận hành extension

### 40.1. Package availability

Cài package extension trên mọi nodes cần chạy database. Physical replication không đồng bộ server binaries.

### 40.2. Trusted/superuser

Kiểm tra extension control metadata và provider policy. Không cấp superuser cho application runtime chỉ để CREATE EXTENSION.

### 40.3. Schema/search_path

Đặt extension objects trong schema được quản lý. Tránh untrusted roles có CREATE privilege trên schema đứng trước schema chứa functions đáng tin cậy.

### 40.4. Upgrade lifecycle

Kiểm tra available versions, update paths, release notes và compatibility với PostgreSQL major version.

### 40.5. Backup/restore

pg_dump có thể lưu CREATE EXTENSION và dữ liệu config theo extension metadata, nhưng không đóng gói shared libraries/control files. Target cần package tương thích.

### 40.6. Managed services

Provider có thể giới hạn extension allowlist và role privileges. Xác minh supported versions và required parameters trước khi thiết kế.

## 41. Troubleshooting hstore

### 41.1. Type hstore không tồn tại

Nguyên nhân thường là extension chưa cài trong database hiện tại hoặc package không có trên server.

~~~sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'hstore';

CREATE EXTENSION hstore;
~~~

Nếu package không có, cài package phù hợp hoặc kiểm tra managed-service allowlist.

### 41.2. Query không dùng GIN index

Kiểm tra:
- Predicate có dùng operator được opclass hỗ trợ không?
- Index có valid không?
- Statistics có cập nhật không?
- Predicate có selectivity đủ tốt không?
- Table có quá nhỏ không?
- Query expression có khớp index expression không?

Dùng EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp.

### 41.3. Cast lỗi

Nếu cast hstore text value sang integer/date thất bại, xác định rows có malformed values. Validate và clean dữ liệu trước khi tạo expression index hoặc generated expression phụ thuộc cast.

### 41.4. Attribute drift

Tạo report keys/values bằng each() và xác định keys cũ, typo, value formats không thống nhất. Chuẩn hóa definitions và deprecate theo rollout plan.

## 42. Troubleshooting ltree

### 42.1. Invalid path label

Path không tuân grammar ltree. Normalize input và dùng text2ltree/cast sau validation. Lưu display label riêng.

### 42.2. Subtree query không trả đúng

Kiểm tra operator direction:
- ancestor @> descendant.
- descendant <@ ancestor.

Đây là nguồn nhầm phổ biến.

### 42.3. GiST không được dùng

Kiểm tra operator, index validity, statistics, selectivity và EXPLAIN plan. Query equality đơn giản có thể phù hợp B-tree hơn.

### 42.4. Path move conflict

Destination path có thể trùng với node khác. Preflight kiểm tra path uniqueness và descendants trước khi update.

### 42.5. Orphan path

UNIQUE(path) không bảo đảm ancestor row tồn tại. Tạo validation procedure/trigger hoặc giữ parent_id với FK nếu invariant đó quan trọng.

### 42.6. Graph không phù hợp

Nếu node có nhiều parents, cycles hoặc edges có types, chuyển sang edge table/graph model. Không cố nhồi nhiều paths vào một cột ltree mà không định nghĩa semantics.

## 43. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng hstore cho nested documents | Query/validation khó | Chọn JSONB |
| Lưu numeric/boolean như text mà không validate | Cast lỗi và so sánh sai | Typed columns hoặc validation |
| Đưa mọi attributes vào hstore | Business columns khó enforce | Tách attributes ổn định |
| Coi empty hstore và NULL giống nhau | Semantics không rõ | Quy định rõ default/null |
| Dùng -> để kiểm tra key | Không phân biệt missing và NULL | Dùng ?/defined |
| Không index hstore filters | Sequential scan trên bảng lớn | GIN/GiST/expression index theo query |
| Tạo GIN cho mọi hstore column | Write/storage overhead | Index theo workload |
| Dùng ltree cho DAG nhiều parent | Mô hình không biểu diễn đúng graph | Edge table |
| Dùng display names làm labels | Rename/path grammar issues | Stable IDs/slugs |
| Chỉ UNIQUE(path) rồi coi hierarchy integrity hoàn chỉnh | Có thể thiếu ancestor row | Parent FK/trigger/procedure |
| Nhầm hướng @> và <@ | Trả ancestor/descendant sai | Nhớ left ancestor @> right |
| Di chuyển node nhưng không update descendants | Paths không nhất quán | Subtree migration có transaction |
| Dùng nested sets cho hierarchy thay đổi liên tục | Nhiều rows phải update | Adjacency list/ltree/closure |
| Dùng adjacency list cho mọi deep subtree query | Recursive query phức tạp | Benchmark ltree/closure |
| Không đo GIN/GiST overhead | Tăng WAL và write latency | Đo trước/sau |
| Dùng JSONB cho mọi typed fields | Constraints/indexing khó hơn | Tách hot typed columns |
| Dùng range mà không chuẩn hóa bounds | Overlap/off-by-one bugs | Chọn convention [) |
| Dùng geometry SRID sai | Distance/area sai | Validate SRID/units |
| Coi extension đã cài ở primary là đủ | Failover node thiếu package | Provision mọi HA nodes |
| Không test restore | Target thiếu extension binaries | Restore rehearsal |

## 44. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging. Cài extension cần package/quyền phù hợp; không thay đổi schema production chỉ để thử nghiệm.

1. **Install hstore:** cài extension trong database lab.
2. **Inventory:** kiểm tra pg_available_extensions và pg_extension.
3. **Create table:** tạo products với attributes hstore.
4. **Insert literal:** chèn một hstore literal có ba pairs.
5. **Constructor:** tạo hstore bằng hstore(text[], text[]).
6. **Read value:** lấy một key bằng ->.
7. **Missing key:** so sánh key không tồn tại với SQL NULL.
8. **Key exists:** lọc bằng ?.
9. **All keys:** lọc bằng ?&.
10. **Any key:** lọc bằng ?|.
11. **Defined:** phân biệt exist và defined.
12. **Containment:** query bằng @>.
13. **Contained by:** query bằng <@.
14. **Equality:** so sánh hai hstore values.
15. **Update:** thêm một pair bằng ||.
16. **Overwrite:** ghi đè một key đã tồn tại.
17. **Delete key:** xóa một key bằng -.
18. **Delete array:** xóa nhiều keys.
19. **Delete pairs:** thử xóa các pairs theo hstore value.
20. **akeys:** liệt kê keys.
21. **avals:** liệt kê values.
22. **each:** unnest pairs thành rows.
23. **slice:** lấy một subset keys.
24. **Array conversion:** chuyển hstore sang array/matrix.
25. **JSON conversion:** dùng hstore_to_jsonb.
26. **Typed cast:** cast weight_grams sang integer.
27. **Invalid value:** tạo malformed numeric và quan sát cast error.
28. **GIN:** tạo GIN index trên attributes.
29. **Containment plan:** EXPLAIN query @>.
30. **Key plan:** EXPLAIN query ?.
31. **GiST:** benchmark GiST index trên hstore.
32. **Expression index:** tạo B-tree index cho attributes -> color.
33. **Write overhead:** so sánh inserts/updates trước và sau GIN.
34. **JSONB comparison:** lưu cùng sample trong JSONB và so query.
35. **Migration:** backfill hstore sang JSONB.
36. **Typed JSON:** chuyển một key text thành JSON number có validation.
37. **Dual write:** thiết kế source-of-truth trong migration.
38. **Attribute audit:** thống kê keys bằng each().
39. **Key policy:** xây bảng định nghĩa allowed keys.
40. **Install ltree:** cài extension ltree trong lab.
41. **Path table:** tạo categories với path ltree.
42. **Insert tree:** tạo hierarchy ba cấp.
43. **Ancestors:** query bằng @>.
44. **Descendants:** query bằng <@.
45. **Exclude self:** lấy descendants mà không lấy node gốc.
46. **Depth:** tính nlevel.
47. **Subpath:** lấy prefix/suffix.
48. **Index function:** tìm subpath bằng index().
49. **LCA:** tính lowest common ancestor.
50. **Concatenate:** ghép paths bằng ||.
51. **lquery:** tìm paths theo wildcard.
52. **Quantifier:** thử lquery với nhiều levels.
53. **GiST:** tạo GiST index trên path.
54. **B-tree:** tạo B-tree index cho equality và so sánh.
55. **EXPLAIN:** so query plans ancestor/descendant.
56. **Move subtree:** chuyển một subtree và cập nhật descendants.
57. **Unique conflict:** tạo destination path trùng và xử lý.
58. **Orphan check:** tìm paths có ancestor row bị thiếu.
59. **Stable labels:** thiết kế slug/ID thay display name.
60. **Adjacency list:** tạo nodes với parent_id.
61. **Recursive CTE:** lấy descendants từ một node.
62. **Cycle:** mô phỏng cycle và thiết kế prevention.
63. **Closure table:** tạo ancestor-descendant pairs.
64. **Closure query:** lấy ancestors và descendants.
65. **Closure move:** cập nhật closure rows khi chuyển subtree.
66. **Nested sets:** tạo lft/rgt model.
67. **Nested subtree:** query descendants bằng interval.
68. **Nested move:** phân tích chi phí move node.
69. **DAG:** tạo graph_nodes và graph_edges.
70. **Multi-parent:** mô hình node có hai parents.
71. **JSONB:** tạo document table và GIN index.
72. **Arrays:** tạo tags array và GIN index.
73. **Ranges:** tạo tstzrange cho booking periods.
74. **Exclusion:** dùng btree_gist để ngăn overlap.
75. **Network:** lưu inet/cidr và query subnet.
76. **Full-text:** tạo tsvector và GIN index.
77. **Trigram:** cài pg_trgm và fuzzy search.
78. **Spatial:** tìm hiểu geometry/geography và PostGIS GiST.
79. **Model choice:** chọn data model cho taxonomy, product attributes và dependency graph.
80. **Thiết kế tổng hợp:** xây schema PostgreSQL cho catalog có attributes linh hoạt, hierarchy nhiều cấp, search, constraints, indexes, migration, extension provisioning và capacity/performance plan.

## 45. Checklist chọn mô hình dữ liệu

### hstore/JSONB

- [ ] Attributes có thực sự linh hoạt không?
- [ ] Values có chỉ là text hay cần JSON types?
- [ ] Có cần nested arrays/objects không?
- [ ] Keys nào cần typed columns?
- [ ] Có allowed-key/value policy không?
- [ ] Có index phù hợp query patterns không?
- [ ] Có migration/extension dependency không?

### Hierarchy

- [ ] Cấu trúc là tree, DAG hay graph?
- [ ] Một node có tối đa một parent không?
- [ ] Subtree reads hay moves thường xuyên hơn?
- [ ] Có cần FK đảm bảo parent tồn tại không?
- [ ] Path có stable labels không?
- [ ] Có cycle prevention không?
- [ ] Index và path update cost đã benchmark chưa?

### Specialized types

- [ ] Range boundaries được chuẩn hóa?
- [ ] Network host/subnet semantics rõ?
- [ ] Full-text language configuration phù hợp?
- [ ] Spatial SRID/units đúng?
- [ ] Array elements có cần foreign keys/metadata?
- [ ] Index operator class hỗ trợ query?
- [ ] Extension package có trên mọi HA/restore nodes?

### Production readiness

- [ ] Backup/restore đã thử?
- [ ] Extension version/provenance được pin?
- [ ] Permissions/search_path an toàn?
- [ ] Query plans và write overhead được benchmark?
- [ ] Migration/rollback được rehearsal?
- [ ] Monitoring và capacity alerts sẵn sàng?

## 46. Tổng kết

PostgreSQL có thể biểu diễn nhiều mô hình dữ liệu ngoài các scalar columns thông thường. hstore phù hợp với key/value attributes phẳng; ltree phù hợp với materialized paths cho tree hierarchy; JSONB, arrays, ranges, network, full-text và spatial types phục vụ các cấu trúc chuyên biệt khác.

~~~text
FLEXIBLE ATTRIBUTES
  hstore (flat text key/value)
  JSONB (nested typed document)
             |
             v
HIERARCHY / RELATIONSHIPS
  ltree (materialized tree path)
  adjacency list
  closure table
  nested sets
  edge table (DAG/graph)
             |
             v
DOMAIN-SPECIFIC TYPES
  arrays / ranges / inet / tsvector
  UUID / XML / PostGIS
             |
             v
OPERATORS + INDEXES + CONSTRAINTS
  GIN / GiST / B-tree / SP-GiST
             |
             v
MIGRATION / MONITORING / OPERATIONS
~~~

Những nguyên tắc quan trọng:

- **hstore là key/value phẳng và text-oriented.** Dùng khi attributes đơn giản; chọn JSONB khi cần nested structure và typed JSON values.
- **Giữ các business attributes ổn định thành typed columns.** Flexible storage không thay thế constraints, foreign keys và relational design.
- **Dùng đúng hstore operators.** ?, ?&, ?|, @>, <@, -> và || diễn đạt các query patterns khác nhau.
- **Index theo operators được sử dụng.** GIN/GiST phục vụ hstore containment/key queries; expression B-tree phù hợp khi filter một key cụ thể.
- **ltree biểu diễn một path trong hierarchy.** ancestor @> descendant; descendant <@ ancestor.
- **Path cần labels ổn định.** Giữ display names riêng và chuẩn hóa identifiers.
- **ltree làm subtree reads thuận tiện nhưng move subtree tốn writes.** Cập nhật path của node và descendants nhất quán.
- **UNIQUE(path) chưa đủ bảo đảm hierarchy integrity.** Nếu cần parent tồn tại, dùng parent FK hoặc controlled procedures/triggers.
- **DAG/graph cần edge model.** Một path ltree đơn không biểu diễn đầy đủ nhiều parents hoặc cycles.
- **Chọn adjacency list, closure table, nested sets hay ltree theo read/write pattern.** Không có một hierarchy model tối ưu cho mọi workload.
- **Ranges, network, full-text và spatial types có operators chuyên biệt.** Dùng types/indexes tương ứng thay vì parse text thủ công.
- **Extension là dependency production.** Cài packages trên mọi HA/restore nodes, pin versions và test backup/restore.
- **Đo hiệu năng cả reads và writes.** Specialized indexes có thể tăng query speed nhưng cũng tăng storage, WAL và update cost.

Một data model tốt biểu diễn đúng semantics nghiệp vụ, giúp PostgreSQL kiểm tra tính hợp lệ và dùng operators/indexes phù hợp. Chọn hstore, ltree hoặc specialized types khi cấu trúc dữ liệu thực sự cần chúng, rồi quản lý constraints, migrations và vận hành như một phần của schema production.

