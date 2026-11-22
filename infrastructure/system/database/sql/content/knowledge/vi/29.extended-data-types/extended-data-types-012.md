# Giới hạn tính khả chuyển của kiểu và hàm mở rộng trong SQL

> **Module:** Database SQL  
> **Chương:** Dữ liệu mở rộng  
> **Bài học:** Giới hạn tính khả chuyển của kiểu và hàm mở rộng

SQL có những khả năng tương đối phổ biến như SELECT, JOIN, WHERE, GROUP BY, các kiểu số và chuỗi. Nhưng khi ứng dụng bắt đầu lưu **JSON, mảng, UUID, tọa độ địa lý, văn bản tìm kiếm, dữ liệu thời gian có múi giờ, cấu trúc phân cấp hoặc kiểu tự định nghĩa**, sự tương đồng giữa các hệ quản trị giảm rất nhanh.

Một câu SQL hợp lệ trên PostgreSQL chưa chắc phân tích cú pháp được trên MySQL; một biểu thức JSON chạy được ở MySQL và SQLite vẫn có thể **trả về kiểu khác nhau**; hai hàm cùng tên ST_Distance có thể tính khoảng cách trong **đơn vị khác nhau**; hai cơ chế full-text đều dùng MATCH/CONTAINS nhưng lại có cách tách từ, xếp hạng, đánh chỉ mục và xử lý tiếng Việt khác nhau.

Vì vậy, **tính khả chuyển (portability) không chỉ là câu lệnh có chạy được ở hệ khác hay không**. Một giải pháp thực sự khả chuyển phải giữ được **nghĩa dữ liệu, kiểu kết quả, quy tắc NULL, độ chính xác, hành vi lỗi, quyền truy cập, hiệu năng và ràng buộc** trong hệ đích.

Bài học này trình bày những giới hạn thường gặp của kiểu/hàm mở rộng trong **PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite**, đồng thời hướng dẫn cách thiết kế schema, truy vấn và quy trình migration có kiểm thử để không đánh mất dữ liệu hoặc thay đổi nghiệp vụ ngoài ý muốn.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt SQL chuẩn và **dialect/extension** của từng DBMS.
2. Nhận diện năm mức tương thích: cú pháp, kiểu dữ liệu, ngữ nghĩa, tích hợp ứng dụng và hiệu năng.
3. Giải thích vì sao tên kiểu **JSON**, **UUID**, **BOOLEAN**, **TIMESTAMP**, **ARRAY** hoặc **GEOMETRY** không luôn có cùng khả năng lưu/truy vấn/chỉ mục.
4. So sánh cách lưu và truy vấn JSON bằng PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
5. Phân biệt **SQL NULL**, **JSON null**, **thuộc tính JSON vắng mặt** và giá trị chuỗi "null".
6. Biết các khác biệt khi lấy scalar JSON, lọc array, phân rã JSON thành hàng và cập nhật JSON.
7. Biết khi nào dùng bảng quan hệ trung gian thay cho mảng hoặc JSON.
8. So sánh UUID, ENUM, BOOLEAN, chuỗi, binary và ngày giờ qua các hệ.
9. Phân biệt timezone, offset, local timestamp và **instant**, nhất là ở ranh giới DST.
10. Hiểu giới hạn khả chuyển của các hàm **regular expression**, xử lý Unicode/collation và tìm kiếm full-text.
11. Nhận diện khác biệt lớn của kiểu dữ liệu không gian, **SRID**, đơn vị tọa độ và hàm tính khoảng cách.
12. Phân biệt index B-tree thông thường với GIN, spatial, full-text, expression/generated indexes.
13. Nhận diện rủi ro khi JDBC/ORM ánh xạ kiểu mở rộng sang Java.
14. Lập ma trận khả năng theo **DBMS và phiên bản**, không dựa vào một tên tính năng chung.
15. Thiết kế lớp tương thích hoặc cô lập truy vấn theo dialect.
16. Xây dựng bộ kiểm thử dữ liệu biên, round-trip và kết quả tương đương giữa các hệ.

## 2. Khả chuyển nghĩa là gì?

Một giải pháp được gọi là khả chuyển khi có thể triển khai trên DBMS khác với **chi phí điều chỉnh chấp nhận được** và vẫn đáp ứng hợp đồng dữ liệu/nghiệp vụ đã xác định.

Cần phân biệt các mức:

| Mức | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Cú pháp | DBMS có parse/execute câu SQL không? | Toán tử PostgreSQL @> không phải toán tử JSON chung |
| Kiểu lưu trữ | DBMS có lưu cùng miền và cấu trúc không? | Native JSONB so với TEXT chứa JSON |
| Ngữ nghĩa | Cùng dữ liệu có cho kết quả tương đương không? | JSON null, missing path, timezone |
| Giao diện ứng dụng | Driver/ORM ánh xạ giá trị cùng cách không? | UUID object so với String/byte[] |
| Hiệu năng/vận hành | Có index/optimizer/tính năng bảo trì tương ứng không? | GIN, FTS5, FULLTEXT, spatial index |

**Cú pháp chạy được là điều kiện yếu nhất.**

### 2.1. Ba ví dụ về kết quả “cùng tên nhưng khác nghĩa”

- Hàm JSON_EXTRACT ở MySQL trả một giá trị thuộc ngữ nghĩa JSON của MySQL; json_extract ở SQLite có thể trả trực tiếp SQL INTEGER/TEXT/NULL khi chỉ có một path và scalar phù hợp.
- TIMESTAMP trên PostgreSQL, MySQL, Oracle và SQL Server không tự đồng nghĩa về timezone, độ chính xác và cách bind.
- Hàm xử lý geometry có thể dựa trên hệ tọa độ phẳng hay mô hình địa cầu; cùng cặp tọa độ và cùng tên hàm chưa đủ để biết kết quả tính bằng mét.

### 2.2. Khả chuyển không có nghĩa phải tránh mọi tính năng mở rộng

Nếu ứng dụng chỉ chạy PostgreSQL và cần tìm kiếm containment JSONB quy mô lớn, dùng JSONB + GIN có thể là quyết định tốt. Vấn đề là **phải coi đây là phụ thuộc có chủ đích**, ghi tài liệu, kiểm thử và chuẩn bị đường thay thế nếu có kế hoạch chuyển DBMS.

## 3. Chuẩn SQL và phần mở rộng của nhà cung cấp

Chuẩn SQL trải qua nhiều phiên bản và có các tính năng tùy chọn. Các DBMS hỗ trợ các phần khác nhau, vào những thời điểm khác nhau, với cú pháp riêng.

Ví dụ:
- JSON có những khả năng được chuẩn hóa một phần, nhưng các hệ bổ sung toán tử, JSON path, JSON_TABLE, JSON_VALUE và cơ chế lưu riêng.
- Spatial SQL có các chuẩn/khuôn khổ liên quan, nhưng các DBMS triển khai geometry, geography và hàm theo cách khác.
- MERGE, UPSERT, regex và generated columns có những biến thể theo sản phẩm/phiên bản.
- Một hàm của chuẩn cũng có thể có giới hạn kiểu đối số hoặc kiểu kết quả khác.

**Câu hỏi đúng không phải “SQL chuẩn có JSON không?” mà là “DBMS A phiên bản X và DBMS B phiên bản Y hỗ trợ những thao tác JSON nào, với ngữ nghĩa nào?”**

### 3.1. Tính năng có thể phụ thuộc phiên bản

Ví dụ:
- PostgreSQL có JSON và JSONB với các khả năng khác nhau; SQL/JSON path và các tính năng liên quan được bổ sung qua các phiên bản.
- MySQL có native JSON và các hàm JSON; cần phân biệt MySQL với MariaDB vì kiểu JSON và thực thi có thể khác.
- SQL Server truyền thống dùng các hàm JSON trên NVARCHAR; các phiên bản mới có thêm khả năng kiểu native JSON và hàm/mở rộng mới với điều kiện triển khai riêng.
- Oracle có hỗ trợ JSON qua kiểu cột truyền thống và native JSON ở những phiên bản hỗ trợ.
- SQLite JSON functions phụ thuộc khả năng JSON được tích hợp/biên dịch, còn binary JSONB của SQLite không tương thích định dạng với PostgreSQL JSONB.

Không nên viết một bảng “Có/Không” mà bỏ mất **phiên bản tối thiểu và điều kiện build/edition/extension**.

## 4. Chuẩn bị mô hình dữ liệu mở rộng

Giả sử hệ bán hàng có một đơn hàng:

~~~json
{
  "orderId": "O1001",
  "customer": {
    "id": "C001",
    "displayName": "Hòa"
  },
  "items": [
    {"sku": "P01", "qty": 2, "price": 100000},
    {"sku": "P02", "qty": 1, "price": 50000}
  ],
  "tags": ["mobile", "promotion"],
  "shipping": {
    "lat": 10.776,
    "lon": 106.701
  },
  "coupon": null,
  "createdAt": "2026-10-03T09:15:00+07:00"
}
~~~

Nhu cầu:
- Lưu payload gốc và đọc các trường.
- Tìm đơn chứa sản phẩm P01.
- Lọc tags.
- Truy vấn tọa độ giao hàng.
- Xác định ngày lập đơn theo giờ Việt Nam.
- Tìm đơn theo văn bản mô tả.
- Đánh chỉ mục để không phải parse toàn bộ JSON mỗi lần.

Có thể lưu một phần trong bảng quan hệ:

~~~sql
CREATE TABLE don_hang (
    order_id VARCHAR(40) PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL
);
~~~

và chi tiết:

~~~sql
CREATE TABLE chi_tiet_don (
    order_id VARCHAR(40) NOT NULL,
    sku VARCHAR(40) NOT NULL,
    qty INTEGER NOT NULL,
    price DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id, sku),
    FOREIGN KEY (order_id) REFERENCES don_hang(order_id)
);
~~~

Phần payload JSON có thể giữ cho các thuộc tính biến động. **Không phải vì DBMS có JSON mà phải đưa mọi quan hệ, khóa và ràng buộc vào JSON.**

## 5. JSON: cùng tên nhưng kiểu lưu không giống nhau

| Hệ | Cách tiếp cận tiêu biểu |
|---|---|
| PostgreSQL | JSON (giữ văn bản JSON theo dạng riêng) và JSONB (dạng nhị phân xử lý/index khác) |
| MySQL | Native JSON với cơ chế lưu và validation của MySQL |
| SQL Server | Các hàm JSON trên chuỗi NVARCHAR ở nhiều phiên bản; native JSON ở phiên bản/khả năng hỗ trợ mới |
| Oracle | JSON trong các kiểu lưu được hỗ trợ và native JSON ở phiên bản phù hợp, có SQL/JSON functions |
| SQLite | JSON xử lý qua các hàm với giá trị thường lưu ở TEXT hoặc định dạng JSONB riêng của SQLite, tùy cách dùng |

Từ **JSONB** đặc biệt dễ gây ngộ nhận: PostgreSQL JSONB và SQLite JSONB **không cùng wire format**, không copy bytes trực tiếp từ hệ này sang hệ kia và mong sử dụng được.

### 5.1. JSON có còn giữ nguyên văn bản đầu vào không?

Các hệ có thể:
- Chuẩn hóa khoảng trắng.
- Chuẩn hóa cách viết số.
- Thay đổi thứ tự key của object.
- Xử lý duplicate object keys theo quy tắc riêng.
- Duy trì hay không duy trì dạng chuỗi escape ban đầu.
- Cung cấp một representation nội bộ không phản ánh JSON văn bản gốc.

Nếu **cần lưu chứng cứ nguyên văn** phục vụ chữ ký, đối soát hoặc audit, nên giữ bản raw payload riêng và tách phần JSON dùng cho truy vấn. Không dùng serialize(parse(payload)) như phép bảo toàn byte-for-byte.

### 5.2. JSON syntax hợp lệ chưa đủ để bảo đảm schema

Một JSON object có thể hợp lệ nhưng thiếu customer.id, chứa qty âm, giá kiểu chuỗi hoặc sai timezone. Cần validation bằng:
- JSON schema ở tầng ingest hoặc cơ chế kiểm tra DBMS phù hợp.
- NOT NULL/CHECK/UNIQUE ở các cột quan hệ.
- API contract được version hóa.
- Quarantine đối với payload không đáp ứng hợp đồng.

Không coi JSON_VALID hoặc IS JSON là kiểm tra toàn bộ nghiệp vụ.

## 6. Lấy scalar JSON: năm cách viết khác nhau

Giả định bảng don_hang_payload có khóa order_id và cột payload lưu JSON bằng kiểu thích hợp cho từng DBMS. Muốn lấy customer.id.

**PostgreSQL** (payload kiểu jsonb):

~~~sql
SELECT payload -> 'customer' ->> 'id' AS customer_id
FROM don_hang_payload;
~~~

Toán tử **->** truy cập JSON value, còn **->>** lấy dạng text tương ứng theo PostgreSQL.

**MySQL:**

~~~sql
SELECT JSON_UNQUOTE(
    JSON_EXTRACT(payload, '$.customer.id')
) AS customer_id
FROM don_hang_payload;
~~~

Có thể có toán tử rút gọn ->/->> trong ngữ cảnh MySQL hỗ trợ; vẫn phải hiểu kiểu kết quả và phiên bản.

**SQL Server** với dữ liệu JSON ở cột thích hợp:

~~~sql
SELECT JSON_VALUE(payload, '$.customer.id') AS customer_id
FROM dbo.don_hang_payload;
~~~

**Oracle:**

~~~sql
SELECT JSON_VALUE(
    payload, '$.customer.id'
    RETURNING VARCHAR2(40)
) AS customer_id
FROM don_hang_payload;
~~~

**SQLite:**

~~~sql
SELECT json_extract(payload, '$.customer.id') AS customer_id
FROM don_hang_payload;
~~~

### 6.1. Không thể thay tên hàm một cách máy móc

Các hàm có thể khác:
- Kiểu của giá trị trả về.
- Độ dài tối đa khi lấy scalar.
- Chế độ nghiêm ngặt khi path không tồn tại.
- Cách xử lý JSON null và SQL NULL.
- Cách nhận path có dấu chấm/khoảng trắng/Unicode.
- Quy tắc với array/object thay vì scalar.
- Chi phí truy vấn và chỉ mục.

Một chương trình trả dữ liệu qua API phải biết **mình muốn String, số hay JSON fragment**, không dựa vào tên cột alias.

## 7. SQL NULL, JSON null và thuộc tính vắng mặt

Đây là một trong những lỗi di chuyển hệ quản trị khó phát hiện nhất.

Ba JSON object:

~~~json
{"coupon": null}
~~~

~~~json
{}
~~~

~~~json
{"coupon": "null"}
~~~

khác nhau:

1. **JSON null**: trường coupon có tồn tại nhưng mang giá trị null của JSON.
2. **Missing key**: coupon không có trong object.
3. **String "null"**: coupon tồn tại và chứa bốn ký tự n-u-l-l.

Ngoài ra, cả cột payload trong SQL có thể là **SQL NULL**, nghĩa là không có JSON document ở cột đó.

### 7.1. Hai câu hỏi tách biệt

- Path này **có tồn tại** không?
- Nếu có, giá trị của nó **bằng gì và thuộc kiểu nào**?

Một hàm lấy scalar có thể trả SQL NULL cho cả missing path và JSON null trong chế độ mặc định. Khi đó không thể phân biệt hai trạng thái chỉ bằng biểu thức lấy scalar.

### 7.2. PostgreSQL

Với jsonb:
- Toán tử path có thể trả SQL NULL nếu cấu trúc không khớp.
- Giá trị JSON null có ngữ nghĩa JSON riêng.
- Có các toán tử kiểm tra sự tồn tại của key như **?** và cơ chế jsonb_typeof.
- Toán tử ->> chuyển JSON value sang text theo quy tắc; JSON null và missing có thể đều tạo SQL NULL ở kết quả text trong trường hợp tương ứng.

Ví dụ:

~~~sql
SELECT
    payload ? 'coupon' AS has_coupon,
    jsonb_typeof(payload -> 'coupon') AS coupon_json_type
FROM don_hang_payload;
~~~

### 7.3. MySQL

Sử dụng các hàm như JSON_CONTAINS_PATH, JSON_TYPE và JSON_EXTRACT để phân biệt tồn tại/path/type theo quy tắc MySQL:

~~~sql
SELECT
    JSON_CONTAINS_PATH(payload, 'one', '$.coupon') AS has_coupon,
    JSON_TYPE(JSON_EXTRACT(payload, '$.coupon')) AS coupon_json_type
FROM don_hang_payload;
~~~

### 7.4. SQL Server

JSON_VALUE không tự là một bộ phân biệt mọi loại missing/JSON null; có thể phải dùng OPENJSON, JSON_QUERY, JSON_PATH_EXISTS trong những phiên bản hỗ trợ hoặc logic nghiêm ngặt/kiểm tra path riêng.

### 7.5. Oracle

SQL/JSON functions có các chế độ **ON EMPTY/ON ERROR**, path existence và các lựa chọn RETURNING; cần chọn rõ để không trộn “vắng mặt” với “sai kiểu” hoặc “JSON null”.

### 7.6. SQLite

json_type và json_extract cho phép kiểm tra khác biệt:

~~~sql
SELECT
    json_type(payload, '$.coupon') AS coupon_type,
    json_extract(payload, '$.coupon') AS coupon_value
FROM don_hang_payload;
~~~

json_type cho path tồn tại có JSON null trả tên kiểu JSON **null**, trong khi path vắng mặt có thể trả SQL NULL theo quy tắc SQLite.

### 7.7. Bài học chuyển hệ

Không viết logic nghiệp vụ:

~~~text
Nếu JSON_VALUE(...) IS NULL thì coupon không được gửi.
~~~

nếu hợp đồng phân biệt **“không gửi coupon”** với **“gửi coupon=null để xóa coupon”**. Đó là hai sự kiện khác nhau trong một API PATCH.

## 8. Kiểu trả về của json_extract: MySQL và SQLite

Một khác biệt rõ:

~~~sql
-- MySQL
SELECT JSON_EXTRACT('{"x": 7}', '$.x');
~~~

và:

~~~sql
-- SQLite
SELECT json_extract('{"x": 7}', '$.x');
~~~

Tên hàm tương tự nhưng kiểu biểu diễn kết quả không nhất thiết giống nhau:
- MySQL JSON_EXTRACT trả giá trị theo ngữ nghĩa JSON của MySQL, với biểu diễn có thể là JSON number/string/null.
- SQLite json_extract với **một path** trỏ tới scalar thường trả **SQL INTEGER/REAL/TEXT/NULL** tương ứng, không nhất thiết trả JSON text.

Điều này ảnh hưởng:
- JDBC ResultSet.getObject/getString.
- So sánh JSON number với chuỗi "7".
- Ghép chuỗi/serialize API.
- Kết quả xử lý JSON null.
- Kết quả khi path trỏ array/object hoặc có nhiều path.

**Không lấy một test JSON_EXTRACT trả 7 trên MySQL và giả định SQLite trả cùng SQL type.**

## 9. JSON path cũng có dialect

Các path đơn giản như **$.customer.id** có vẻ giống nhau. Nhưng những trường hợp sau khó chuyển hơn:

- Key chứa dấu chấm như "a.b".
- Key chứa khoảng trắng, dấu quote hoặc Unicode.
- Array indexes và index từ cuối.
- Wildcard trên object/array.
- Predicate/filter trong path.
- Recursive descent.
- Biến path truyền vào query.
- Strict/lax path modes.
- Truy cập key khi document đang là array/scalar.

Ví dụ object:

~~~json
{
  "customer.name": "An",
  "customer": {"name": "Bình"}
}
~~~

Hai đường truy cập này **không giống nhau**. Nếu chuyển từ biểu thức PostgreSQL dạng mảng đường dẫn sang SQL/JSON path, cần escape key đúng cú pháp của hệ đích. Không nối path từ input không tin cậy vào SQL mà bỏ qua injection/escaping.

### 9.1. Path không tồn tại: NULL hay lỗi?

Một số hàm/path mode trả NULL khi missing, một số có lựa chọn báo lỗi. Một pipeline muốn phát hiện dữ liệu sai schema phải quyết định:
- Missing key hợp lệ hay invalid?
- Sai kiểu object/array xử lý thế nào?
- JSON text không hợp lệ sẽ reject hay bỏ qua?
- Có cần phân biệt missing vs null?

Không dùng behavior mặc định làm hợp đồng dữ liệu mà không ghi tài liệu.

## 10. JSON array: lấy hàng từ mảng

Với items:

~~~json
[
  {"sku": "P01", "qty": 2},
  {"sku": "P02", "qty": 1}
]
~~~

Bài toán là biến mỗi phần tử thành một dòng quan hệ.

### 10.1. PostgreSQL

~~~sql
SELECT
    p.order_id,
    item ->> 'sku' AS sku,
    (item ->> 'qty')::integer AS qty
FROM don_hang_payload AS p
CROSS JOIN LATERAL
    jsonb_array_elements(p.payload -> 'items') AS item;
~~~

Điều kiện giả định payload là jsonb, items có kiểu array và qty là số nguyên hợp lệ. CAST sẽ lỗi nếu đầu vào sai kiểu/không chuyển được; cần validation trước hoặc xử lý ngoại lệ.

### 10.2. MySQL

Ở phiên bản có **JSON_TABLE**:

~~~sql
SELECT
    p.order_id,
    j.sku,
    j.qty
FROM don_hang_payload AS p
JOIN JSON_TABLE(
    p.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS j;
~~~

Ngữ nghĩa DEFAULT/ON EMPTY/ON ERROR và mức hỗ trợ JSON_TABLE phụ thuộc phiên bản MySQL.

### 10.3. SQL Server

~~~sql
SELECT
    p.order_id,
    j.sku,
    j.qty
FROM dbo.don_hang_payload AS p
CROSS APPLY OPENJSON(p.payload, '$.items')
WITH (
    sku NVARCHAR(40) '$.sku',
    qty INT '$.qty'
) AS j;
~~~

### 10.4. Oracle

~~~sql
SELECT
    p.order_id,
    j.sku,
    j.qty
FROM don_hang_payload p,
     JSON_TABLE(
         p.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(40) PATH '$.sku',
             qty NUMBER PATH '$.qty'
         )
     ) j;
~~~

### 10.5. SQLite

~~~sql
SELECT
    p.order_id,
    json_extract(j.value, '$.sku') AS sku,
    json_extract(j.value, '$.qty') AS qty
FROM don_hang_payload AS p
JOIN json_each(p.payload, '$.items') AS j;
~~~

### 10.6. Cùng ý tưởng nhưng khác cú pháp và kiểu

Cả năm giải pháp đều có thể tạo tập hàng cho array, nhưng:
- Kiểu của qty và quy tắc cast khác.
- Nếu items thiếu/NULL/không phải array, hành vi có thể khác.
- Cách dùng LATERAL, APPLY, JSON_TABLE, json_each khác.
- Hàng bị nhân theo số phần tử; cần kiểm soát nếu JOIN tiếp bảng khác.
- Thứ tự phần tử array không phải **thứ tự kết quả SQL** nếu thiếu ORDER BY. Muốn giữ ordinality, phải lấy vị trí phần tử theo cơ chế DBMS và ORDER BY rõ.

## 11. JSON updates: cú pháp là một phần, merge semantics là phần khó

Nhu cầu sửa qty của một item hoặc cập nhật trường coupon có các cách:

- PostgreSQL: jsonb_set, toán tử JSONB, JSONB path/functions phù hợp.
- MySQL: JSON_SET, JSON_REPLACE, JSON_REMOVE và hàm JSON khác.
- SQL Server: JSON_MODIFY và khả năng cập nhật JSON tùy phiên bản.
- Oracle: JSON_TRANSFORM ở các phiên bản hỗ trợ và giải pháp SQL/JSON khác.
- SQLite: json_set, json_replace, json_remove hoặc các biến thể JSONB.

Ví dụ đơn giản cập nhật trạng thái:

**PostgreSQL jsonb:**

~~~sql
UPDATE don_hang_payload
SET payload = jsonb_set(
    payload,
    '{status}',
    '"PAID"'::jsonb
)
WHERE order_id = 'O1001';
~~~

**MySQL:**

~~~sql
UPDATE don_hang_payload
SET payload = JSON_SET(payload, '$.status', 'PAID')
WHERE order_id = 'O1001';
~~~

**SQL Server:**

~~~sql
UPDATE dbo.don_hang_payload
SET payload = JSON_MODIFY(payload, '$.status', 'PAID')
WHERE order_id = 'O1001';
~~~

**SQLite:**

~~~sql
UPDATE don_hang_payload
SET payload = json_set(payload, '$.status', 'PAID')
WHERE order_id = 'O1001';
~~~

Các câu trên minh họa ý định thêm/sửa một thuộc tính, **không phải một migration script chung**.

### 11.1. JSON merge không phải SQL MERGE

- JSON Merge Patch thường có quy tắc riêng cho null và object fields.
- JSON_SET ghi vào path theo ngữ nghĩa DBMS.
- SQL MERGE là câu DML xử lý khớp khóa nguồn–đích.
- JSONB concatenation/merge ở PostgreSQL không có nghĩa merge sâu tùy ý.

Không lấy từ “merge” làm chứng cứ các thao tác có cùng semantics.

### 11.2. PATCH với JSON null

Giả sử API gửi:

~~~json
{"coupon": null}
~~~

Có nghĩa là đặt coupon thành JSON null hay xóa key coupon? Hai cách có thể có hiệu ứng khác nhau. Khi port JSON updates, hãy viết hợp đồng rõ cho **set-null**, **remove-key** và **skip-field**; kiểm thử missing vs null.

## 12. JSON index không khả chuyển nguyên văn

Lưu JSON mới là một nửa câu chuyện. Để query theo trường sâu hiệu quả cần chỉ mục tương thích.

### 12.1. PostgreSQL JSONB

Có thể dùng **GIN index** trên JSONB và toán tử hỗ trợ:

~~~sql
CREATE INDEX idx_payload_gin
ON don_hang_payload
USING GIN (payload);
~~~

Ví dụ lọc containment:

~~~sql
SELECT order_id
FROM don_hang_payload
WHERE payload @> '{"customer":{"id":"C001"}}'::jsonb;
~~~

GIN và toán tử @> là cơ chế PostgreSQL, **không copy-paste sang MySQL/SQL Server**.

### 12.2. MySQL

Có thể tạo generated column/index hoặc functional index trong những trường hợp được hỗ trợ, và một số cấu trúc index chuyên biệt cho mảng JSON trên những phiên bản phù hợp. Cần biết kiểu/độ dài của biểu thức, collation, optimizer matching và bản MySQL.

### 12.3. SQL Server

Thường dùng computed columns dựa trên JSON_VALUE kèm index, hoặc các khả năng JSON index mới trên những phiên bản/edition hỗ trợ. Hàm JSON_VALUE có giới hạn kiểu/độ dài trong chế độ nhất định, nên không giả định mọi JSON string đều index được bằng cùng cú pháp.

### 12.4. Oracle

Có JSON search index, function-based indexes và các kiểu index phù hợp với SQL/JSON, tùy phiên bản và nhu cầu truy vấn.

### 12.5. SQLite

Có expression index hoặc generated column dựa trên json_extract khi biểu thức hợp lệ:

~~~sql
CREATE INDEX idx_customer_json_sqlite
ON don_hang_payload (
    json_extract(payload, '$.customer.id')
);
~~~

### 12.6. Không chỉ “có index”

Khi chuyển sang DBMS mới cần xác minh:
- Query có dùng index hay scan không?
- Loại predicate và path nào được hỗ trợ?
- NULL/missing có vào index không?
- String comparison/collation có đổi không?
- Chi phí INSERT/UPDATE payload thay đổi thế nào?
- Query planner có nhận expression index tương ứng không?

**Một phương án đúng về chức năng nhưng chậm hơn hàng trăm lần trên dữ liệu lớn vẫn là rủi ro vận hành khi chuyển hệ.**

## 13. JSON và ràng buộc dữ liệu

JSON document có thể chứa duplicate items, quantity âm, cấu trúc không hợp lệ hoặc thiếu trường. Một số ràng buộc cần ở bảng quan hệ thay vì chỉ nằm trong JSON:

~~~sql
CREATE TABLE chi_tiet_don (
    order_id VARCHAR(40) NOT NULL,
    sku VARCHAR(40) NOT NULL,
    qty INTEGER NOT NULL,
    price DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id, sku),
    CHECK (qty > 0),
    CHECK (price >= 0)
);
~~~

Một JSON array có hai phần tử cùng sku không bị một PRIMARY KEY của bảng JSON tự ngăn. Nếu cần enforce uniqueness bên trong array hoặc FK từ JSON scalar sang bảng khác, có thể cần validation ứng dụng/trigger/chuyển dữ liệu sang bảng quan hệ.

### 13.1. Khi nào nên dùng cột quan hệ?

Dùng cột/bảng quan hệ cho:
- Khóa nghiệp vụ và JOIN thường xuyên.
- Cột cần UNIQUE/FK/NOT NULL/CHECK mạnh.
- Dữ liệu thường xuyên lọc/sắp xếp/tổng hợp.
- Giá trị tài chính cần decimal chính xác.
- Dữ liệu cần cập nhật riêng từng phần tử có concurrency control.

Dùng JSON cho:
- Payload bán cấu trúc thực sự biến động.
- Thuộc tính bổ sung không phải lõi truy vấn.
- Event ingestion cần giữ raw payload.
- Dữ liệu ít cần ràng buộc liên bảng.

Có thể kết hợp cả hai, nhưng tránh lưu **hai nguồn sự thật** không đồng bộ.

## 14. ARRAY: native array không có trên mọi hệ

PostgreSQL hỗ trợ native array types:

~~~sql
CREATE TABLE bai_viet_pg (
    id BIGINT PRIMARY KEY,
    tags TEXT[] NOT NULL
);
~~~

Lọc một tag:

~~~sql
SELECT id
FROM bai_viet_pg
WHERE 'sql' = ANY(tags);
~~~

Lọc một số điều kiện containment/overlap có thể dùng các toán tử array PostgreSQL như **@>**, **&&** với index phù hợp.

Không thể lấy nguyên:

~~~sql
tags TEXT[]
~~~

và giả định MySQL, SQL Server, Oracle và SQLite có kiểu ARRAY cùng semantics, index và toán tử.

### 14.1. Cách thay thế phổ biến

- JSON array.
- Bảng liên kết nhiều–nhiều **bai_viet_tag(post_id,tag)**.
- Oracle collections trong trường hợp mô hình Oracle yêu cầu.
- Kiểu/extension tùy DBMS.

### 14.2. Bảng liên kết thường khả chuyển hơn

~~~sql
CREATE TABLE bai_viet_tag (
    post_id BIGINT NOT NULL,
    tag VARCHAR(60) NOT NULL,
    PRIMARY KEY (post_id, tag)
);
~~~

Tìm bài chứa tag:

~~~sql
SELECT post_id
FROM bai_viet_tag
WHERE tag = 'sql';
~~~

Ưu điểm:
- Dùng PRIMARY KEY/FOREIGN KEY/INDEX phổ biến.
- Không phụ thuộc toán tử mảng.
- Kiểm soát duplicate tag rõ.
- JOIN và phân trang dễ quan sát.

Nhược điểm:
- Thêm bảng và JOIN.
- Nếu vị trí phần tử có ý nghĩa, phải lưu **position**.
- Muốn giữ nguyên payload array từ nguồn cần cơ chế round-trip.

### 14.3. Mảng là danh sách có thứ tự hay một tập?

JSON array **có thứ tự** và có thể chứa duplicate. Một bảng liên kết với PRIMARY KEY(post_id,tag) lại có semantics **tập không trùng**. Nếu chuyển từ array sang bảng, cần quyết định:
- Có cho cùng tag lặp lại không?
- Vị trí có ý nghĩa không?
- NULL elements được phép không?
- Phần tử có mang object payload riêng không?

Không tự gộp duplicates vì “nó chỉ là tags” nếu hợp đồng dữ liệu không cho phép.

## 15. UUID/GUID: cùng ý tưởng, nhiều cách lưu

UUID là định danh 128-bit thường biểu diễn bằng chuỗi dạng:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Nhưng cách lưu/generate khác nhau:

| DBMS | Kiểu/cách phổ biến |
|---|---|
| PostgreSQL | Native uuid |
| MySQL | CHAR(36), BINARY(16) hoặc cấu trúc ứng dụng lựa chọn |
| SQL Server | uniqueidentifier |
| Oracle | RAW(16) hoặc VARCHAR2, có hàm tạo RAW dạng GUID |
| SQLite | TEXT hoặc BLOB |

Ví dụ tạo UUID mới:

**PostgreSQL:**

~~~sql
SELECT gen_random_uuid();
~~~

Khả năng có sẵn/hàm liên quan phụ thuộc phiên bản, extension và cấu hình.

**MySQL:**

~~~sql
SELECT UUID();
~~~

**SQL Server:**

~~~sql
SELECT NEWID();
~~~

**Oracle:**

~~~sql
SELECT SYS_GUID() FROM dual;
~~~

**SQLite:** thường ứng dụng sinh UUID rồi bind TEXT/BLOB, hoặc dùng extension/hàm tự định nghĩa; không mặc định có một built-in UUID generator giống các hệ trên.

### 15.1. SYS_GUID không tự là chuỗi RFC có dấu gạch

Oracle SYS_GUID trả RAW và format khác cách in chuỗi của PostgreSQL/SQL Server. Phải chuẩn hóa **16 bytes và cách biểu diễn**; nếu chỉ sao chép TO_CHAR của RAW, có thể được chuỗi hex khác format UUID có dấu gạch.

### 15.2. Byte order và binary storage

Một số API/DBMS có quy ước byte-order hoặc binary layout khác khi chuyển GUID/UUID sang byte[]. Khi di chuyển sang BINARY(16), không đảo thứ tự các nhóm bytes mà không có tiêu chuẩn dữ liệu cụ thể và test round-trip.

### 15.3. UUID version và thứ tự index

UUID v4 ngẫu nhiên và các dạng UUID có tính sắp xếp thời gian khác nhau ảnh hưởng locality của B-tree và hiệu năng INSERT. Hàm UUID() của một DBMS không bảo đảm tạo cùng version với NEWID()/gen_random_uuid() của hệ khác. Hãy định nghĩa version mong muốn ở tầng ứng dụng nếu cần tính nhất quán.

## 16. BOOLEAN: câu chuyện không chỉ TRUE/FALSE

| DBMS | Biểu diễn thường gặp |
|---|---|
| PostgreSQL | Native BOOLEAN |
| MySQL | BOOLEAN/BOOL thường là alias cho TINYINT(1) |
| SQL Server | BIT |
| Oracle | SQL BOOLEAN có điều kiện theo phiên bản mới; bản trước thường dùng NUMBER/CHAR cho bảng |
| SQLite | Không có storage class BOOLEAN riêng theo nghĩa hệ kiểu tĩnh; thường lưu 0/1 theo affinity |

Ví dụ PostgreSQL:

~~~sql
SELECT *
FROM don_hang
WHERE is_paid IS TRUE;
~~~

Một hệ khác có thể yêu cầu:

~~~sql
WHERE is_paid = 1
~~~

nhưng không thể mặc định **mọi số khác 0 đều có nghĩa TRUE** trong mô hình nghiệp vụ, nhất là MySQL nếu cột không được kiểm soát.

### 16.1. Ba trạng thái

Nếu cột nullable, có thể có TRUE, FALSE, SQL NULL. Chuyển sang tinyint/bit/int mà ứng dụng map boolean primitive có thể đánh mất ý nghĩa **“chưa biết/chưa xác nhận”**.

### 16.2. CHECK khi dùng cột số

Nếu dùng NUMBER/INTEGER thay Boolean native:

~~~sql
CHECK (is_paid IN (0, 1))
~~~

có thể ngăn giá trị 2/7/99 ở các hệ thực thi CHECK theo quy tắc phiên bản. Với nullable, cần thêm NOT NULL nếu nghiệp vụ không cho phép trạng thái chưa biết.

## 17. ENUM và kiểu tùy biến

PostgreSQL có ENUM types, ví dụ:

~~~sql
CREATE TYPE order_status AS ENUM (
    'NEW', 'PAID', 'SHIPPED', 'CANCELLED'
);
~~~

MySQL có ENUM với quy tắc lưu/thứ tự/sắp xếp và chuyển kiểu riêng. SQL Server, Oracle và SQLite thường dùng VARCHAR/CHAR có CHECK hoặc bảng tra cứu, thay vì một cú pháp ENUM thống nhất.

### 17.1. ENUM thay đổi thế nào khi thêm trạng thái?

Nếu thêm 'REFUNDED', quá trình ALTER ENUM và quản lý version/schema khác nhau. Một hệ có thể bổ sung giá trị thuận lợi, hệ khác phải sửa CHECK constraint hoặc bảng lookup.

### 17.2. Thứ tự ENUM không phải thứ tự từ điển

MySQL ENUM có thứ tự nội bộ theo danh sách khai báo; PostgreSQL ENUM cũng có thứ tự theo định nghĩa enum, không tự đồng nghĩa so chuỗi ASCII. Nếu chuyển thành VARCHAR mà vẫn ORDER BY status, thứ tự có thể đổi.

### 17.3. Lựa chọn khả chuyển

Một bảng tra cứu:

~~~sql
CREATE TABLE trang_thai_don (
    ma_trang_thai VARCHAR(20) PRIMARY KEY,
    thu_tu_hien_thi INTEGER NOT NULL
);
~~~

và FK trong bảng đơn thường dễ chuyển hệ, có thể thay đổi danh sách bằng DML và kiểm soát thứ tự trình bày độc lập. Đổi lại có thêm JOIN và migration seed data.

## 18. TIMESTAMP, timezone, offset và instant

Tên kiểu thời gian là nguồn sai khác lớn:

- **Date:** ngày lịch không nhất thiết có giờ/múi giờ.
- **Local timestamp:** ngày + giờ trên đồng hồ, nhưng không tự xác định một instant toàn cầu.
- **Instant/UTC:** một thời điểm tuyệt đối.
- **Offset datetime:** ngày giờ cùng offset, nhưng offset **không phải tên vùng timezone**.
- **Zoned datetime:** ngữ nghĩa có thể cần timezone database, quy tắc DST và vùng IANA.

### 18.1. Kiểu của các DBMS

**PostgreSQL:** TIMESTAMP WITHOUT TIME ZONE và TIMESTAMP WITH TIME ZONE (thường gọi timestamptz) có ngữ nghĩa khác nhau; timestamptz biểu diễn instant và cách hiển thị phụ thuộc timezone session, không lưu nguyên văn tên timezone nguồn.

**MySQL:** TIMESTAMP và DATETIME khác nhau về xử lý session timezone, phạm vi và lưu trữ; không coi DATETIME là UTC tự động.

**SQL Server:** DATETIME/DATETIME2/DATETIMEOFFSET khác nhau về độ chính xác và lưu offset.

**Oracle:** DATE chứa thành phần thời gian; TIMESTAMP, TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE có ngữ nghĩa khác nhau.

**SQLite:** thường lưu timestamp dưới dạng TEXT, REAL hoặc INTEGER và xử lý bằng hàm thời gian với quy tắc riêng; không có một kiểu TIMESTAMPTZ native tương đương PostgreSQL.

### 18.2. Bẫy ngày theo timezone

Giả sử sự kiện:

~~~text
2026-10-03T00:30:00+07:00
~~~

Instant UTC tương ứng là:

~~~text
2026-10-02T17:30:00Z
~~~

Nếu query thống kê “đơn ngày 03/10 theo giờ Việt Nam” nhưng cột lưu UTC, WHERE DATE(utc_time)='2026-10-03' có thể bỏ sự kiện này. Hãy tính **mốc đầu ngày/ngày kế tiếp theo timezone nghiệp vụ**, đổi sang UTC instant rồi so khoảng nửa mở.

### 18.3. DST không phải cộng cố định 24 giờ

Ở vùng có daylight saving time, một ngày lịch có thể dài 23 hoặc 25 giờ. Muốn lọc ngày địa phương, tính hai ranh giới lịch theo timezone rules rồi chuyển về instant, không đơn giản cộng 24 giờ UTC vào một timestamp.

### 18.4. Precision, rounding và khoảng nửa mở

Hệ có precision khác nhau cho giây/phần giây. Khi chuyển từ nanosecond sang millisecond có thể mất chính xác; khi lọc ngày dùng:

~~~sql
WHERE created_at >= :start_instant
  AND created_at < :next_day_start_instant
~~~

thường rõ hơn BETWEEN kết thúc 23:59:59.999 vì độ chính xác thay đổi giữa các DBMS.

### 18.5. CURRENT_TIMESTAMP không luôn giữ cùng dữ liệu

Các hàm NOW, CURRENT_TIMESTAMP, GETDATE, SYSDATE, SYSTIMESTAMP, datetime('now') có:
- Kiểu trả về khác.
- Precision khác.
- Nguồn timezone khác.
- Thời điểm đánh giá khác (đầu transaction, statement hoặc lúc gọi, tùy DBMS).

Nếu nghiệp vụ cần “thời gian sự kiện từ nguồn”, không nên thay bừa bằng thời điểm DB nhận event.

## 19. INTERVAL và phép toán ngày giờ

PostgreSQL có kiểu INTERVAL phong phú và phép cộng kiểu:

~~~sql
SELECT CURRENT_TIMESTAMP + INTERVAL '7 days';
~~~

MySQL có cú pháp như DATE_ADD và INTERVAL theo quy tắc hệ:

~~~sql
SELECT DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY);
~~~

SQL Server dùng DATEADD:

~~~sql
SELECT DATEADD(day, 7, SYSDATETIME());
~~~

Oracle:

~~~sql
SELECT SYSTIMESTAMP + INTERVAL '7' DAY FROM dual;
~~~

SQLite dùng time modifiers như:

~~~sql
SELECT datetime('now', '+7 days');
~~~

**Cùng mục tiêu cộng bảy ngày** nhưng kiểu kết quả, timezone và quy tắc thời gian có thể khác. Cộng một tháng còn phức tạp hơn vì tháng không có cùng độ dài; ngày 31 ở cuối tháng phải có policy.

### 19.1. DATE difference cũng khác

DATEDIFF ở SQL Server đếm các ranh giới đơn vị đi qua theo semantics riêng, không mặc định bằng số ngày thực dưới dạng thời lượng. PostgreSQL có phép trừ timestamp cho interval, Oracle có các dạng number/interval tùy kiểu, MySQL TIMESTAMPDIFF, SQLite dùng julianday/unixepoch để tính toán theo kiểu lưu.

Không lấy một con số “1 ngày” từ hai DBMS là bằng nhau nếu chưa thống nhất **duration thực** hay **calendar day difference**.

## 20. Binary/BLOB, text encoding và độ dài

Với dữ liệu binary:
- PostgreSQL có BYTEA.
- MySQL có BINARY/VARBINARY/BLOB.
- SQL Server có VARBINARY.
- Oracle có RAW/BLOB.
- SQLite có BLOB storage class.

Những khác biệt gồm:
- Giới hạn độ dài.
- Streaming LOB qua driver.
- Encoding/decoding hex/base64.
- Thứ tự bytes khi map UUID/GUID.
- Khác biệt giữa chuỗi rỗng và NULL trong một số hệ.
- Phương thức hash/encryption/extension.

### 20.1. Không dùng CAST binary sang text không có encoding

Một byte array bất kỳ không nhất thiết là UTF-8 hợp lệ. Muốn chuyển binary qua JSON/API nên dùng **Base64** hoặc **hex** với contract rõ, thay vì ép dữ liệu trực tiếp thành VARCHAR rồi hy vọng khôi phục nguyên vẹn.

### 20.2. CHAR, VARCHAR, NVARCHAR, TEXT và Unicode

Số ký tự, số byte, collation, case sensitivity và quy tắc trimming khác nhau. SQL Server NVARCHAR và VARCHAR khác encoding/collation; MySQL charset/collation ảnh hưởng so sánh; Oracle có CHAR/VARCHAR2/NVARCHAR2 cùng quy tắc độ dài BYTE/CHAR; PostgreSQL và SQLite có ngữ nghĩa riêng.

Đặc biệt:
- Chữ tiếng Việt UTF-8 có thể chiếm nhiều bytes.
- Một ký tự hiển thị có thể gồm nhiều Unicode code points.
- LOWER/UPPER không tự thực hiện đầy đủ Unicode normalization.
- Tra cứu bằng dấu bằng dưới collation accent-insensitive có thể gộp những tên khác nhau.

Một migration dữ liệu mở rộng phải kiểm tra **round-trip Unicode**, không chỉ đếm chiều dài VARCHAR giống nhau.

## 21. Các hàm REGEXP không khả chuyển nguyên văn

Regular expression dùng để kiểm tra mẫu, nhưng cú pháp/operator và engine regex khác nhau.

**PostgreSQL** hỗ trợ toán tử regex như:

~~~sql
SELECT *
FROM khach_hang
WHERE email ~ '^[^@]+@[^@]+$';
~~~

**MySQL** có REGEXP_LIKE trong các phiên bản hỗ trợ:

~~~sql
SELECT *
FROM khach_hang
WHERE REGEXP_LIKE(email, '^[^@]+@[^@]+$');
~~~

**Oracle**:

~~~sql
SELECT *
FROM khach_hang
WHERE REGEXP_LIKE(email, '^[^@]+@[^@]+$');
~~~

**SQL Server** truyền thống thường dùng LIKE/PATINDEX hoặc giải pháp khác; hỗ trợ regex mới có thể phụ thuộc phiên bản/compatibility/preview và không nên giả định REGEXP_LIKE phổ biến trên mọi SQL Server.

**SQLite** có cú pháp toán tử REGEXP nhưng mặc định cần một function do ứng dụng/extension cung cấp để thực thi. Không phải môi trường SQLite nào cũng sẵn regex engine.

### 21.1. Cùng pattern không bảo đảm cùng match

Regex engine có thể khác:
- Các lớp ký tự \w, \d, Unicode property escapes.
- Biên từ.
- Case folding.
- Capturing/noncapturing groups.
- Lookbehind, backreference.
- Collation và normalization.
- Quy tắc matching newline.
- Hiệu năng với pattern có catastrophic backtracking.

Không dùng một regex rất đơn giản để khẳng định cả bộ regex của hai DBMS tương thích.

### 21.2. Regex không thay kiểm tra email chuyên dụng

Ví dụ pattern minh họa ở trên **không phải kiểm tra đầy đủ tiêu chuẩn email**. Với dữ liệu sản xuất, validation nên được xác định theo nghiệp vụ và chuẩn hiện hành, đồng thời không quên ràng buộc độ dài, Unicode domain và normalization.

## 22. Hàm text/NULL có cùng ý tưởng nhưng khác cú pháp

Một số ví dụ:

| Ý nghĩa | Các biến thể phổ biến |
|---|---|
| Ghép chuỗi | CONCAT, toán tử \|\|, toán tử + theo hệ |
| Lấy chuỗi con | SUBSTRING, SUBSTR |
| Xử lý NULL | COALESCE, IFNULL, ISNULL, NVL |
| Chuyển kiểu | CAST, CONVERT, TO_CHAR, TO_NUMBER |
| Độ dài | LENGTH, CHAR_LENGTH, LEN, DATALENGTH |
| Làm tròn | ROUND/TRUNC/TRUNCATE với quy tắc kiểu |
| Giá trị hiện tại | NOW, CURRENT_TIMESTAMP, GETDATE, SYSDATE |

### 22.1. CONCAT và NULL

Một số hàm/operator ghép chuỗi xử lý NULL theo cách khác hoặc tùy cài đặt. Nếu business contract quy định họ + tên lót vắng mặt phải trả chuỗi có một dấu cách thay vì NULL, hãy viết COALESCE/NULL handling rõ. Đừng chỉ thay CONCAT bằng \|\| hoặc + mà không test.

### 22.2. Độ dài ký tự so với byte

LENGTH ở một DBMS có thể đếm byte, ở hệ khác đếm ký tự trong một ngữ cảnh. Với tiếng Việt, hai kết quả không luôn bằng. Muốn giới hạn 100 bytes, cần đo bytes; muốn 100 ký tự Unicode theo định nghĩa nghiệp vụ, cần xác định số code points hay grapheme clusters.

### 22.3. CAST lỗi và silent conversion

Có hệ báo lỗi khi chuyển '12x' sang số; hệ khác trả warning/0/NULL theo chế độ hoặc function. Một chương trình migration không được dùng CAST rồi coi mọi bản ghi dữ liệu bẩn đều chuyển đúng. Nên validate/reject trước khi đổi kiểu.
## 23. Full-text search: tên gần giống, mô hình khác nhau

Tìm kiếm toàn văn khác lọc bằng LIKE '%từ%'. Full-text thường cần:
- Phân tách văn bản thành token.
- Quy tắc chuyển chữ hoa/thường, dấu và từ dừng (stop words).
- Stemming hoặc phân tích ngôn ngữ.
- Đánh chỉ mục đảo (inverted index) hay cấu trúc chuyên biệt.
- Phân tích câu query theo cú pháp text search.
- Xếp hạng kết quả (ranking/relevance).

Những thành phần này không có nghĩa thống nhất ở mọi DBMS.

### 23.1. PostgreSQL

PostgreSQL có **tsvector** và **tsquery**:

~~~sql
SELECT id, noi_dung
FROM tai_lieu
WHERE to_tsvector('simple', noi_dung)
      @@ plainto_tsquery('simple', 'SQL database');
~~~

Có thể tạo chỉ mục GIN trên biểu thức:

~~~sql
CREATE INDEX idx_tai_lieu_fts_pg
ON tai_lieu
USING GIN (to_tsvector('simple', noi_dung));
~~~

Config 'simple' là một lựa chọn minh họa, không bảo đảm phân tách từ tiếng Việt đủ tốt. PostgreSQL còn có rank functions và text search configurations khác nhau. Nếu dùng ngôn ngữ tự nhiên, cần xác định dictionary/tokenizer.

### 23.2. MySQL

Với FULLTEXT index phù hợp:

~~~sql
CREATE FULLTEXT INDEX idx_tai_lieu_fts_mysql
ON tai_lieu (noi_dung);
~~~

Query:

~~~sql
SELECT id, noi_dung
FROM tai_lieu
WHERE MATCH(noi_dung)
      AGAINST ('database SQL' IN BOOLEAN MODE);
~~~

Các token, minimum token size, stopwords, parser, storage engine và chế độ natural language/boolean ảnh hưởng kết quả. Dấu +, -, *, dấu quote có thể mang nghĩa trong boolean mode; không coi đó là cùng cú pháp với PostgreSQL tsquery.

### 23.3. SQL Server

SQL Server có full-text index/catalog và các điều kiện **CONTAINS**, **FREETEXT**, cùng các hàm/table-valued functions chuyên biệt.

Ví dụ khái niệm sau khi cấu hình full-text index:

~~~sql
SELECT id, noi_dung
FROM dbo.tai_lieu
WHERE CONTAINS(noi_dung, '"database" AND "SQL"');
~~~

Ngữ pháp query, word breakers, language identifier và stoplist phải được kiểm soát. Hệ thống cần cấu hình full-text search; không chỉ tạo B-tree index trên noi_dung.

### 23.4. Oracle

Oracle Text hỗ trợ index và toán tử CONTAINS theo cú pháp/lexer/section group riêng. Ví dụ sau khi có Oracle Text index phù hợp:

~~~sql
SELECT id, noi_dung
FROM tai_lieu
WHERE CONTAINS(noi_dung, 'database AND SQL', 1) > 0;
~~~

Điều kiện CONTAINS của Oracle không tương đương nguyên văn cú pháp CONTAINS ở SQL Server, dù cùng tên.

### 23.5. SQLite

Khi bản build hỗ trợ **FTS5**:

~~~sql
CREATE VIRTUAL TABLE tai_lieu_fts
USING fts5(noi_dung);
~~~

~~~sql
SELECT rowid, noi_dung
FROM tai_lieu_fts
WHERE tai_lieu_fts MATCH 'database SQL';
~~~

FTS5 có tokenizer, query syntax và ranking riêng; bảng FTS là virtual table với quy tắc đồng bộ dữ liệu khác bảng thường.

### 23.6. Không so số kết quả/rank một cách ngây thơ

Cùng chuỗi “học SQL ở Việt Nam”:
- DBMS A có thể tách “Việt Nam” thành hai token.
- DBMS B có thể dùng tokenizer tiếng Việt xác định đây là một cụm.
- Stopwords/stemming làm khác tập match.
- Accent normalization làm “Hoa” và “Hòa” có thể bị xử lý khác.
- Ranking BM25/tf-idf/heuristics không cùng thang điểm.
- Một hệ cần index build/refresh trước khi query thấy dữ liệu mới.

**Một API tìm kiếm khả chuyển nên xác định kỳ vọng chức năng, không đòi các điểm rank số học của hai engine phải giống hệt nếu không có cùng thuật toán.**

## 24. Không gian địa lý: geometry, geography và SRID

Dữ liệu vị trí có thể lưu dưới dạng:
- **GEOMETRY:** hình học trong hệ tọa độ xác định (phẳng hoặc geographic coordinates tùy SRID/DBMS).
- **GEOGRAPHY:** kiểu chuyên biệt của một số hệ để xử lý trên bề mặt Trái Đất.
- **Latitude/Longitude** dưới dạng số.
- GeoJSON/WKT/WKB.
- Cấu trúc spatial như Oracle SDO_GEOMETRY.

Tên **ST_Distance**, **ST_Within**, **ST_Contains** xuất hiện ở nhiều hệ, nhưng vẫn cần quan tâm:
- Kiểu dữ liệu của đối số.
- SRID và đơn vị.
- Trật tự tọa độ.
- Hình học hợp lệ hay không.
- Thuật toán geodesic/phẳng.
- Chính sách transform/reprojection.
- Index spatial được hỗ trợ.

### 24.1. SRID là gì?

**Spatial Reference System Identifier (SRID)** giúp xác định hệ quy chiếu tọa độ.

SRID 4326 thường liên quan tọa độ kinh độ/vĩ độ WGS84. Nhưng chỉ gắn nhãn SRID=4326 **không biến** dữ liệu đo bằng mét thành kinh/vĩ độ, cũng không tự thực hiện biến đổi tọa độ.

Ví dụ địa điểm:

~~~text
latitude  = 10.776
longitude = 106.701
~~~

Trong nhiều API hình học dạng x/y, **x là kinh độ** và **y là vĩ độ**. Truyền ST_MakePoint(10.776,106.701) thay vì ST_MakePoint(106.701,10.776) sẽ đảo hai trục, cho vị trí hoàn toàn khác.

Một số SQL constructors/WKT/SRS có quy tắc axis order riêng; không dựa hoàn toàn vào tên tham số của hàm khác DBMS.

### 24.2. PostgreSQL với PostGIS

PostGIS là extension không gian phổ biến của PostgreSQL, **không phải toàn bộ PostGIS built-in trong mọi database PostgreSQL mặc định**.

Ví dụ biểu diễn một điểm kiểu geography:

~~~sql
SELECT ST_SetSRID(
    ST_MakePoint(106.701, 10.776),
    4326
)::geography;
~~~

Với geography, nhiều hàm khoảng cách của PostGIS có thể làm việc theo mét theo quy tắc chức năng. Ví dụ truy vấn gần điểm có thể dùng **ST_DWithin(geography, geography, radius_meters)** khi dữ liệu và index phù hợp.

Một geometry mang SRID 4326 mà dùng ST_Distance geometry có thể trả khoảng cách theo **đơn vị tọa độ** (thường là độ), không tự là mét.

### 24.3. MySQL Spatial

MySQL hỗ trợ spatial types và các hàm ST_... theo phiên bản/SRS. Có ST_Distance, ST_Distance_Sphere và spatial indexes, nhưng:
- Hành vi theo SRID khác.
- Geometry có hệ tọa độ không được coi mặc nhiên là geography.
- Axis order trong các thao tác WKT/constructor cần được xác định theo SRS/cú pháp.
- Không mọi hàm/loại hình học dùng cùng thuật toán hoặc index.

### 24.4. SQL Server geometry và geography

SQL Server có hai kiểu riêng **geometry** và **geography**. Các phương thức như **STDistance()** được gọi theo ngữ nghĩa kiểu UDT:

~~~sql
-- Minh họa cú pháp T-SQL:
SELECT geography::Point(10.776, 106.701, 4326);
~~~

Ở geography::Point, cú pháp nhận **latitude rồi longitude**, trái với nhiều hàm tạo điểm x/y. Đây là ví dụ thực tế về lỗi đảo tọa độ khi port code.

### 24.5. Oracle Spatial

Oracle có SDO_GEOMETRY và bộ công cụ SDO_* để xử lý dữ liệu không gian, cùng spatial indexes. Ví dụ các phép đo có thể dùng **SDO_GEOM.SDO_DISTANCE** với tham số tolerance/đơn vị phù hợp.

Không thay SDO_DISTANCE bằng ST_Distance từ hệ khác mà bỏ cấu hình SRID, tolerance, unit và kiểu đối số.

### 24.6. SQLite và SpatiaLite

SQLite thuần không tự cung cấp toàn bộ API geospatial tương đương PostGIS. **SpatiaLite** hoặc extension khác có thể bổ sung geometry, spatial index và các hàm ST_..., nhưng phải xác minh extension có được cài/bật trong môi trường phát hành hay không.

## 25. GeoJSON, WKT, WKB: định dạng chung chưa đủ

Ba dạng trao đổi phổ biến:

- **GeoJSON:** cấu trúc JSON mô tả Point/LineString/Polygon.
- **WKT:** biểu diễn geometry dưới dạng text.
- **WKB:** biểu diễn binary.

Ví dụ WKT:

~~~text
POINT (106.701 10.776)
~~~

Ví dụ GeoJSON:

~~~json
{"type":"Point","coordinates":[106.701,10.776]}
~~~

Điều cần kiểm tra khi chuyển:
- SRID được lưu trong format nào và truyền ở đâu?
- Geometry dimension Z/M có được bảo toàn?
- Ring orientation và polygon validity có được kiểm tra?
- Coordinate precision có bị giảm?
- Geometry rỗng, invalid geometry, multipolygon có xử lý được?
- Hệ đích có nhận EWKB/EWKT của PostGIS không?
- Có cần transform sang hệ tọa độ khác không?

### 25.1. ST_SetSRID khác ST_Transform

Trong PostGIS:
- ST_SetSRID chủ yếu **gắn nhãn SRID** cho geometry đã có tọa độ.
- ST_Transform **biến đổi tọa độ** sang hệ quy chiếu khác khi có hỗ trợ.

Nếu dữ liệu đang là tọa độ mét trong một projection, không được chỉ ST_SetSRID(...,4326) rồi coi nó là kinh/vĩ độ.

### 25.2. Khoảng cách có thể sai đến mức nào?

Một độ kinh độ không có độ dài mét cố định trên toàn Trái Đất. Vì vậy lấy **ST_Distance trên geometry 4326** (đơn vị độ) rồi so với 5000 với ý nghĩa 5 km là sai nghiêm trọng. Phải chọn geography, transform sang projection có đơn vị phù hợp hoặc hàm geodesic chuyên biệt.

## 26. Spatial indexes và topological predicates

Spatial index khác B-tree trên latitude/longitude:
- R-tree, GiST, SP-GiST, grid/spatial indexes hoặc các cấu trúc tùy DBMS.
- Bounding box filtering thường là bước sơ bộ.
- Một predicate chính xác có thể cần **recheck** trên hình học thật.
- Một số hàm dùng index, một số không hoặc chỉ dùng trong cấu hình riêng.
- Invalid geometry có thể gây lỗi/false result tùy hệ.

Ví dụ ý tưởng:
1. Dùng bounding box/index tìm ứng viên gần.
2. Dùng phép tính khoảng cách chính xác kiểm tra bán kính.
3. Lọc đúng SRID/đơn vị.
4. ORDER BY khoảng cách theo policy.

Không thay mọi phép lọc không gian bằng điều kiện:

~~~sql
WHERE latitude BETWEEN ...
  AND longitude BETWEEN ...
~~~

rồi coi đó là “trong bán kính”. Bounding box chỉ là **vùng ứng viên**, có thể chứa nhiều điểm ngoài hình tròn.

## 27. Vector embeddings và tìm kiếm gần đúng

Một số DBMS/extension hỗ trợ kiểu **VECTOR** hoặc toán tử khoảng cách cho embeddings. Ví dụ hệ có thể cung cấp:
- PostgreSQL với **pgvector** extension.
- Oracle AI Vector Search trên những phiên bản hỗ trợ.
- SQL Server hoặc hệ liên quan có khả năng vector ở những phiên bản/dịch vụ mới.
- MySQL/HeatWave hoặc các sản phẩm liên quan có cơ chế vector khác.
- SQLite qua extension vector phù hợp, không có một API phổ quát mặc định.

**Không có một cú pháp SQL VECTOR và bộ ANN index thống nhất mà có thể chạy nguyên văn trên mọi DBMS.**

### 27.1. Những khác biệt bắt buộc ghi hợp đồng

- Số chiều embedding: 384, 768, 1536...
- Kiểu phần tử: float32, float16, int8/quantized...
- Distance metric: cosine distance/similarity, L2/Euclidean, inner product.
- Chính sách normalization của vector.
- Top-k và tie-breaking.
- Index approximate nearest neighbor (HNSW, IVF hoặc thuật toán khác).
- Tính ổn định/recall so với brute-force exact search.
- Null/empty/zero vector, vector khác dimension.
- Phiên bản model sinh embeddings.

### 27.2. Cosine similarity khác distance

Một API có thể trả **cosine similarity** (càng lớn càng gần), hệ khác trả **cosine distance** (càng nhỏ càng gần). Nếu chuyển truy vấn ORDER BY từ ASC sang DESC không đúng, top-k có thể đảo ngược hoàn toàn.

Không so điểm của hai DBMS nếu metric/normalization/quantization khác nhau.

### 27.3. ANN không bảo đảm cùng top-k

Approximate indexes có thể trả tập láng giềng gần nhất khác nhau tùy cấu hình, dữ liệu, concurrency và thuật toán. Nếu nghiệp vụ đòi tập kết quả chính xác, phải kiểm tra khả năng exact search hoặc định nghĩa tolerance/recall.

### 27.4. Khả chuyển nằm ở contract hơn là câu SQL

Một lớp search API có thể định nghĩa:

~~~text
search_similar(model_version, embedding, metric, top_k, filters)
-> ranked list of entity_id + score + index_version
~~~

Câu SQL/extension thực thi được cô lập theo adapter. Kiểm thử đánh giá recall/ranking/latency và semantics đồng nhất ở mức ứng dụng.

## 28. XML, hstore, range, inet và hierarchy types

Những kiểu dữ liệu mở rộng khác cũng có hạn chế khả chuyển:

| Nhu cầu | Ví dụ cơ chế đặc thù |
|---|---|
| XML query | XMLTABLE, XQuery/XML functions, XMLTYPE tùy DBMS |
| Key/value map | PostgreSQL hstore extension, JSON object, bảng quan hệ |
| IP addresses | PostgreSQL inet/cidr và toán tử mạng |
| Date/time ranges | PostgreSQL range/multirange với operators |
| Hierarchical identifiers | SQL Server hierarchyid, Oracle hierarchical queries, recursive CTE |
| Money | Kiểu MONEY đặc thù hoặc DECIMAL với currency code |
| Enum/domain | PostgreSQL enum/domain, MySQL ENUM, CHECK/lookup table |
| Cryptographic functions | pgcrypto, DBMS_CRYPTO, AES functions, extension |
| Graph | SQL/PGQ, graph extensions hoặc các ngôn ngữ truy vấn riêng |

### 28.1. PostgreSQL range type

PostgreSQL có thể lưu khoảng như:

~~~text
[2026-10-01,2026-11-01)
~~~

và cung cấp toán tử containment/overlap, exclusion constraints, GiST/SP-GiST index trong trường hợp phù hợp.

Nếu chuyển sang DBMS không có cùng range type:
- Có thể dùng **start_at, end_at**.
- Ràng buộc **start < end**.
- Dùng khoảng nửa mở.
- Kiểm soát không chồng lấn bằng constraint/transaction hoặc logic phù hợp.
- Kiểm tra truy vấn overlap/containment.

Không chỉ tách range thành hai cột mà bỏ mất invariant không chồng lấn khi đó là yêu cầu nghiệp vụ.

### 28.2. Inet/cidr

PostgreSQL inet/cidr xử lý địa chỉ IP/subnet với toán tử chuyên biệt. Nếu chuyển thành VARCHAR:
- Địa chỉ IPv6 có nhiều cách biểu diễn tương đương.
- So chuỗi từ điển không phải so địa chỉ mạng.
- Subnet containment khó index bằng B-tree chuỗi.
- Cần parse/canonicalization và loại dữ liệu phù hợp.

### 28.3. XML

Cùng tên XMLTABLE có thể xuất hiện ở nhiều hệ nhưng XPath/XQuery dialect, XML namespaces, typing, schema validation, handling empty sequences và XML indexes khác nhau. Nếu XML là contract bắt buộc, cần các fixture có namespace, attribute, CDATA, empty element và dữ liệu lớn.

### 28.4. Hierarchy

Một hierarchyid trong SQL Server không phải số thứ tự đường dẫn phổ thông. Khi port sang recursive CTE hoặc adjacency list, cần kiểm tra:
- Parent-child integrity.
- Phát hiện vòng.
- Thứ tự siblings.
- Di chuyển một subtree.
- Path encoding và độ sâu.
- Hiệu năng tìm descendants.

## 29. Những hàm mở rộng khác: kiểm tra trước khi dựa vào

Có nhiều hàm trông quen nhưng không phổ quát:

- **JSON_OBJECT, JSON_ARRAYAGG, JSON_TABLE, JSON_TRANSFORM**: tính năng, cú pháp và xử lý NULL khác.
- **STRING_AGG, GROUP_CONCAT, LISTAGG**: cú pháp aggregate strings và giới hạn độ dài khác.
- **REGEXP_REPLACE**: engine regex, flags và thay thế groups khác.
- **DATE_TRUNC, TRUNC, DATETRUNC**: cú pháp và thời gian/type khác.
- **GENERATE_SERIES**: PostgreSQL có tập hàm; SQL Server và các hệ khác có giải pháp/phiên bản khác.
- **UNNEST**: native arrays, JSON arrays và lateral queries không đồng nhất.
- **PERCENTILE_CONT / PERCENTILE_DISC**: cách dùng ordered-set/window và kiểu trả về khác.
- **HASH/crypto**: thuật toán, encoding bytes, key management và output type khác.
- **UUID/GUID generators**: version và entropy/order khác.
- **Vector distance functions**: metric/score direction khác.

### 29.1. LISTAGG và STRING_AGG

Bài toán gom các mã SKU thành một chuỗi:
- PostgreSQL thường dùng string_agg.
- MySQL dùng group_concat.
- SQL Server dùng string_agg ở phiên bản hỗ trợ.
- Oracle dùng listagg.
- SQLite dùng group_concat/string_agg ở những phiên bản hỗ trợ theo ngữ nghĩa riêng.

Các điểm cần kiểm tra:
- Có ORDER BY bên trong aggregate để cố định thứ tự không?
- NULL bị bỏ qua hay chuyển chuỗi?
- Separator/escape có làm mất khả năng phân rã?
- Độ dài tối đa; overflow báo lỗi hay truncate?
- DISTINCT có hỗ trợ cùng cách không?

Nếu cần chuyển dữ liệu, một **array kết quả có cấu trúc** thường an toàn hơn ghép các chuỗi rồi split theo dấu phẩy khi giá trị cũng có thể chứa dấu phẩy.

## 30. Cùng hàm có thể khác cả kiểu kết quả

| Bài toán | Khác biệt cần thử |
|---|---|
| JSON scalar | JSON value vs SQL scalar; NULL/missing |
| DATE arithmetic | DATE, DATETIME, TIMESTAMP, STRING, number, INTERVAL |
| EXTRACT epoch | Seconds, fractions, precision/type |
| CAST sang INT | Overflow, truncate/round/error |
| ROUND money | Tie rounding mode, precision |
| String length | Byte, code point hoặc ký tự theo quy tắc |
| String comparison | Case/accent/trailing spaces |
| Boolean comparison | Native bool, BIT, tinyint |
| UUID stringify | Hyphens, case, byte order |
| Spatial distance | Degrees, projected units, meters |
| Full-text rank | Score scale, rank direction |
| Vector metric | Distance vs similarity, exact vs approximate |

**Tương đương kiểu** phải được test bằng dữ liệu round-trip và truy vấn, không chỉ nhìn tên trong DDL.

## 31. Bẫy Unicode, collation và trường hợp tiếng Việt

Hãy xét:

~~~text
Hoa
Hòa
Hoà
HOA
Hòa<space>
~~~

Có những cách mã hóa Unicode khác nhau cho ký tự nhìn giống nhau (composed/decomposed). Một số collation:
- Không phân biệt chữ hoa.
- Không phân biệt dấu.
- Bỏ qua khoảng trắng cuối.
- Có quy tắc ngôn ngữ/vùng.
- Có thứ tự sắp xếp khác.

### 31.1. Tác động tới UNIQUE

Trên hệ A, UNIQUE(email) có thể coi hai chuỗi chỉ khác hoa thường là trùng, hệ B có thể cho hai hàng. Khi migration, một bảng hợp lệ trên nguồn có thể **vi phạm UNIQUE trên đích** hoặc ngược lại.

### 31.2. Tác động tới JSON keys

JSON object keys thường có cách so chính xác tùy hàm/engine, không mặc định tuân theo collation của cột quan hệ. Path tìm key "Name" khác "name" ở nhiều trường hợp. Không để canonicalization ở lớp ứng dụng và DB tạo hai nghĩa khác nhau.

### 31.3. Tác động tới full-text và regex

Regex \w, case-insensitive matching và full-text tokenizer có thể xử lý tiếng Việt khác nhau. Phải có fixture chứa:
- Dấu thanh.
- Ký tự kết hợp Unicode.
- Chữ Đ/đ.
- Từ nhiều âm tiết.
- Ký tự emoji và dấu cách không chuẩn.

## 32. Tính khả chuyển của NULL và kiểu đặc thù

Một vài trường hợp:

**Oracle và chuỗi rỗng:** Oracle truyền thống có cách xem chuỗi ký tự rỗng như NULL trong các ngữ cảnh VARCHAR2. Khi chuyển từ PostgreSQL/SQL Server/MySQL/SQLite có phân biệt '' và NULL, dữ liệu có thể mất phân biệt.

**JSON null vs SQL NULL:** nhiều hàm lấy scalar có thể trả NULL cho cả missing và JSON null theo mode.

**Array NULL vs empty array:** PostgreSQL native array và JSON arrays có biểu diễn riêng. Không cho rằng NULL = [].

**Geometry EMPTY vs NULL:** geometry rỗng là một giá trị hợp lệ khác với SQL NULL trong nhiều hệ, có thể tác động hàm distance và index.

**Zero vector vs NULL vector:** cosine similarity với zero vector có thể không xác định theo metric hoặc bị xử lý đặc biệt; phải test.

**Timestamp không offset:** 2026-10-03 10:00 là wall-clock time, không tự xác định một instant nếu thiếu timezone.

**Không được biến những trạng thái khác nhau thành một giá trị mặc định** chỉ để migration thành công mà chưa có quyết định nghiệp vụ.

## 33. Hàm và kiểu mở rộng ảnh hưởng execution plan

Cùng truy vấn logic có thể chạy nhanh ở hệ nguồn và chậm ở hệ đích do:
- Chỉ mục PostgreSQL GIN không có cấu trúc tương đương trực tiếp.
- SQL Server dùng computed column index cho JSON_VALUE.
- MySQL dùng generated/functional indexes cho path.
- Oracle dùng JSON search index/spatial index.
- SQLite dùng expression index hoặc FTS5 virtual table.
- Hàm trên cột có thể làm B-tree index thường khó dùng để seek.
- Một DBMS có thống kê tốt về JSON path, hệ khác không.
- ANN vector search có chỉ số recall/latency khác.
- Spatial predicate có index bounding-box recheck.

### 33.1. EXPLAIN là phần của migration

Một kế hoạch migration không nên chỉ chạy SELECT rồi so row count. Cần:
1. Chạy truy vấn trên dữ liệu mẫu và dữ liệu lớn.
2. Đọc plan tương ứng DBMS.
3. Đo rows read/returned, logical reads, CPU và latency.
4. So hiệu năng với workload thật, không phải ví dụ 10 dòng.
5. Xác định chỉ mục mới, chi phí ghi và bảo trì.

### 33.2. Không tạo index ồ ạt

JSON/path/spatial/FTS/vector indexes có chi phí bảo trì đáng kể. Một index tăng tốc truy vấn có thể làm INSERT/UPDATE chậm hoặc tốn dung lượng. Tối ưu dựa vào tần suất truy vấn và SLA thật.

## 34. JDBC/ORM: lỗi ở ranh giới kiểu

Ngay cả khi SQL chạy được, Java có thể gặp vấn đề:
- PostgreSQL UUID có thể được driver trả theo kiểu UUID.
- MySQL UUID CHAR(36) thường là String, BINARY(16) là byte[].
- JSONB PostgreSQL có thể được driver/ORM ánh xạ qua kiểu chuyên biệt hoặc String theo cấu hình.
- SQL Server JSON truyền thống là NVARCHAR nên ResultSet có thể trả String.
- Oracle JSON, XMLTYPE, SDO_GEOMETRY có driver-specific types.
- SQLite dynamic typing dẫn tới getObject() có thể khác kỳ vọng dựa trên cột khai báo.

### 34.1. Dùng contract Java rõ ràng

Ví dụ domain:

~~~java
public record OrderMetadata(
    String orderId,
    String customerId,
    java.time.Instant createdAt,
    java.math.BigDecimal amount,
    java.util.List<String> tags
) {}
~~~

Tầng persistence adapter chịu trách nhiệm:
- Đọc/ghi JSON theo dialect.
- Parse UUID thành java.util.UUID khi đó là contract.
- Đổi timestamp sang Instant đúng timezone.
- Ánh xạ DECIMAL sang BigDecimal, không tùy tiện double.
- Kiểm tra tags không null, thứ tự, duplicates.
- Xác nhận invalid JSON/loại sai bị reject.

### 34.2. PreparedStatement và extension type

Không ghép JSON path hoặc WKT từ input vào SQL bằng string concatenation thiếu escape. Bind giá trị đúng kiểu khi driver hỗ trợ; với kiểu native/UDT, có thể cần API/PGobject/SQLData/struct riêng theo driver.

### 34.3. ORM abstraction có giới hạn

JPA/Hibernate hay query builder không tự biến mọi toán tử JSONB, spatial predicate, FTS query hoặc vector distance thành SQL tương đương trên năm DBMS. Một số hàm yêu cầu custom dialect/function registration/native SQL.

Một kiến trúc tốt nên **cô lập phần DB-specific ở repository/adapter**, tránh rải cú pháp extension trong logic nghiệp vụ.

## 35. Thiết kế chiến lược đa DBMS

Ba lựa chọn phổ biến:

### 35.1. Chọn mẫu số chung nhỏ nhất

Dùng:
- VARCHAR/NUMERIC/DATE hoặc kiểu phổ biến có kiểm tra.
- Bảng liên kết thay native array.
- Bảng lookup thay enum proprietary.
- Cột quan hệ cho key/constraint.
- SQL chuẩn trong phần lớn truy vấn.

Ưu điểm: dễ chuyển.
Nhược điểm: có thể mất các tính năng index/search đặc thù và cần nhiều mã ứng dụng.

### 35.2. Dùng adapter theo dialect

Định nghĩa interface nghiệp vụ:

~~~java
interface OrderSearchRepository {
    java.util.List<String> findOrderIdsBySku(String sku);
    java.util.List<String> findNearby(double latitude, double longitude,
                                      double radiusMeters);
}
~~~

Triển khai khác nhau:
- PostgreSQL adapter với JSONB/PostGIS.
- MySQL adapter với JSON_TABLE/spatial.
- SQL Server adapter với OPENJSON/geography.
- Oracle adapter với JSON_TABLE/SDO_*.
- SQLite adapter với json_each/extension nếu có.

**Điều chung là contract kết quả, không phải câu SQL.**

### 35.3. Chấp nhận vendor lock-in có kiểm soát

Nếu toàn bộ sản phẩm cam kết PostgreSQL:
- Dùng JSONB, GIN, PostGIS, pgvector khi thật sự hữu ích.
- Ghi rõ extension và version tối thiểu.
- Viết integration tests cho tính năng mở rộng.
- Chuẩn bị định dạng export chuẩn như JSON text, WKT/GeoJSON, UUID canonical.
- Đừng tuyên bố code khả chuyển hoàn toàn.

Có thể dễ bảo trì hơn một “hệ SQL giả lập phổ thông” phải hỗ trợ năm DBMS trong khi chỉ chạy một hệ.

## 36. Ma trận khả năng theo DBMS và phiên bản

Trước khi phát triển, lập bảng từ dữ liệu đã xác minh trên môi trường đích:

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| JSON extraction | ->/->>, SQL/JSON funcs | JSON_EXTRACT/-> | JSON_VALUE/OPENJSON | JSON_VALUE/JSON_TABLE | json_extract/json_each |
| JSON indexing | GIN/expression | generated/functional/index khác | computed/index theo version | JSON search/function index | expression/generated |
| Native arrays | Có | Không cùng dạng | Không cùng dạng | Collections đặc thù | JSON/text/BLOB/extension |
| UUID type | uuid | CHAR/BINARY phổ biến | uniqueidentifier | RAW phổ biến | TEXT/BLOB |
| Boolean | boolean | BOOL/TINYINT | BIT | Theo version | Affinity/0/1 |
| Regex | ~, regex funcs | REGEXP_LIKE | Theo version/khả năng | REGEXP_LIKE | REGEXP cần function |
| Full-text | tsvector/tsquery | FULLTEXT/MATCH | FTS/CONTAINS | Oracle Text | FTS5 extension/build |
| Spatial | PostGIS extension | Spatial functions | geometry/geography | SDO_GEOMETRY | SpatiaLite extension |
| Vector | pgvector extension | Theo product/version | Theo version/product | AI Vector Search | Extensions |
| Timezone type | timestamptz | TIMESTAMP/DATETIME semantics | datetimeoffset | TIMESTAMP WITH TIME ZONE | TEXT/REAL/INTEGER |
| Generated/computed | Có theo phiên bản | Có | Computed columns | Virtual/generated features | Có theo phiên bản |

Đây chỉ là **ma trận định hướng**. Trong dự án thật, phải thêm:
- Phiên bản server cụ thể.
- Edition/license.
- Extensions đã cài/bật.
- Storage engine/build flags.
- Kiểu dữ liệu thực dùng.
- Path/function/operator cần thiết.
- Kết quả kiểm thử.
- Phương án thay thế.
- Chi phí index/performance.

## 37. Phân loại code theo mức phụ thuộc

Có thể phân loại để kiểm soát migration:

| Mức | Ví dụ | Chiến lược |
|---|---|---|
| Thấp | SELECT, JOIN cơ bản, NUMERIC, VARCHAR | Viết gần chuẩn SQL |
| Trung bình | Date functions, string aggregation, generated columns | Adapter nhỏ + test |
| Cao | JSON path, native arrays, full-text | Query adapters, index theo DB |
| Rất cao | Spatial units/SRID, range constraints, vector ANN | Thiết kế contract + tests đặc biệt |
| Đặc thù | Binary vendor format, proprietary UDT, extension internals | Export chuẩn, migration chuyên dụng |

Mức phụ thuộc không cố định; một ứng dụng dùng JSON chỉ để lưu/đọc text có thể ít phụ thuộc hơn ứng dụng truy vấn sâu vào JSONB với nhiều toán tử và GIN indexes.

## 38. Kiến trúc chống lan truyền cú pháp extension

Một sơ đồ gợi ý:

~~~text
API / Business service
         |
         v
Domain contract
- OrderId, CustomerId
- Instant, BigDecimal
- SearchFilter, Location
         |
         v
Repository interface
         |
         +-- PostgreSQL adapter
         |      JSONB, GIN, PostGIS
         |
         +-- MySQL adapter
         |      JSON_TABLE, generated index
         |
         +-- SQL Server adapter
         |      OPENJSON, geography
         |
         +-- Oracle adapter
         |      JSON_TABLE, SDO_*
         |
         +-- SQLite adapter
                json_each, FTS5/SpatiaLite if installed
~~~

Các adapter trả **cùng domain type**. Không cho business code phụ thuộc PostgreSQL jsonb operators hoặc Java class riêng của vendor nếu mục tiêu thực sự là đa DBMS.

### 38.1. Feature flags/capability detection

Ở startup hoặc trong migration:
- Xác định engine và version.
- Xác định extension/feature có sẵn.
- Từ chối khởi động nếu thiếu tính năng bắt buộc.
- Hoặc chọn fallback đã được kiểm thử.
- Log capability profile để quan sát.

Không dùng chuỗi tên DBMS đơn giản làm đủ bằng chứng: cùng tên sản phẩm nhưng phiên bản/edition/build có thể khác đáng kể.

### 38.2. Không để fallback tự hạ chất lượng mà không báo

Nếu spatial extension không có, fallback “so gần bằng bbox” có thể trả kết quả ngoài bán kính. Nếu full-text không có, fallback LIKE '%term%' có thể cho semantics khác và latency cao hơn. Phải mô tả **degradation** rõ, không giả vờ tương đương.

## 39. Migration schema và dữ liệu: quy trình có kiểm tra

### Bước 1 — Inventory

Liệt kê:
- Kiểu cột mở rộng.
- Hàm/toán tử trong view, procedure, trigger, index, query.
- Ràng buộc CHECK, generated columns, partial/expression indexes.
- Extensions/UDTs.
- JDBC/ORM custom mappings.
- Các job search, sync, audit và reporting phụ thuộc.

### Bước 2 — Định nghĩa hợp đồng nghiệp vụ

Ví dụ:
- JSON coupon missing khác JSON null.
- OrderId là String, giữ số 0 đầu.
- createdAt là instant UTC.
- Amount là DECIMAL chính xác.
- Vị trí là WGS84 lon/lat, khoảng cách tính mét.
- Full-text tìm tiếng Việt với accent policy rõ.
- Tags có thứ tự và cho phép duplicate hay không.
- Vector metric là cosine distance và model_version cố định.

### Bước 3 — Mapping schema

Tạo bảng:

~~~text
source_type -> domain_type -> target_type
source_null_semantics -> target_null_semantics
source_function -> target_function/query
source_index -> target_index
source_constraint -> target_constraint/validation
~~~

Không port trực tiếp từng cột mà bỏ qua domain model.

### Bước 4 — Chuẩn hóa export

Ưu tiên định dạng trao đổi có contract:
- JSON text UTF-8 và schema version.
- UUID canonical string, có kiểm soát binary conversion.
- ISO 8601 instant kèm offset/UTC.
- WKT/GeoJSON/WKB kèm SRID metadata.
- Decimal dưới dạng decimal text khi đường truyền JSON có nguy cơ mất precision.
- Bảng liên kết cho multi-valued fields khi phù hợp.

### Bước 5 — Transform và validate

- Phát hiện invalid JSON.
- Phát hiện duplicate keys.
- Kiểm tra string length theo bytes/chars.
- Kiểm tra truncation decimal/timestamp.
- Kiểm tra unique collisions do collation.
- Kiểm tra array order/duplicates.
- Kiểm tra geometry validity/SRID.
- Kiểm tra regex/FTS semantics.
- Quarantine dữ liệu không thể chuyển an toàn.

### Bước 6 — Nạp target trong transaction/batch phù hợp

Dùng staging + validation + import với idempotency. Không biến migration nhiều giờ thành một câu UPDATE có thể rollback dễ dàng nếu hệ vận hành không hỗ trợ yêu cầu đó.

### Bước 7 — Đối soát round-trip

- Row count.
- Distinct business key count.
- Hash/so sánh dữ liệu canonical.
- NULL/missing counts.
- Sum DECIMAL.
- Giá trị timestamp instant.
- JSON field/path equivalence.
- Array elements/ordering.
- Spatial location distance.
- Full-text query results theo fixture.
- Index usability/performance.

### Bước 8 — Cutover và rollback plan

Cần xác định:
- Dữ liệu thay đổi giữa snapshot và cutover.
- CDC/delta replay và idempotency.
- Tính tương thích hai chiều khi rollback.
- Feature chỉ có ở target sẽ được biểu diễn thế nào nếu quay về source.
- Thời gian freeze, monitoring và cách xử lý drift.

## 40. Differential testing: chạy cùng dữ liệu trên hai hệ

Một chương trình kiểm thử nên đưa cùng **logical fixtures** vào A và B, chạy các thao tác tương đương theo adapter rồi so kết quả **đã chuẩn hóa**.

Ví dụ các fixture:

~~~json
{"x": 7}
{"x": "7"}
{"x": null}
{}
{"x": [7]}
{"x": {"y": 7}}
{"x": true}
{"x": ""}
~~~

Các kỳ vọng khác nhau ở loại dữ liệu, nhưng domain contract phải xác định trước.

### 40.1. Không so chuỗi JSON serialization một cách mù quáng

Hai object:

~~~json
{"a":1,"b":2}
~~~

và:

~~~json
{"b":2,"a":1}
~~~

có thể tương đương theo semantics JSON object nhưng khác byte serialization. Nếu contract yêu cầu canonical JSON/signature, phải dùng canonicalization chuẩn xác và version hóa, không chỉ so output mặc định của DBMS.

### 40.2. Numeric precision

JSON number có thể đi qua client JavaScript/double và mất độ chính xác đối với số nguyên lớn hoặc decimal nhiều chữ số. Kiểm thử:
- Các số nguyên vượt miền biểu diễn chính xác của binary floating point.
- Giá trị decimal tiền tệ.
- Số âm, 0, số rất nhỏ/rất lớn.
- Biểu diễn 1, 1.0, 1e0 nếu format quan trọng.

### 40.3. Timestamp

Test:
- Đầu/cuối ngày UTC.
- Đầu/cuối ngày địa phương.
- DST gap/fold.
- Precision microsecond/nanosecond.
- Offset +07:00 và UTC cùng instant.
- Ngày xa trong quá khứ/tương lai theo miền hỗ trợ.

### 40.4. Spatial

Test:
- Đảo lat/lon.
- Hai điểm cùng tọa độ.
- Hai điểm cách nhau khoảng 5 km.
- Đường kinh tuyến 180 độ.
- Polygon rỗng/không hợp lệ.
- SRID khác nhau.
- Mốc ngay trên ranh giới bán kính.

### 40.5. Full-text/vector

Không chỉ so top-1; dùng expected relevance set, precision/recall và tolerance theo contract. Với ANN vector search, ghi index/version/model và mức recall chấp nhận.

## 41. Khả chuyển không đồng nghĩa kết quả không đổi khi đổi collation

Một query:

~~~sql
SELECT customer_id
FROM khach_hang
ORDER BY display_name;
~~~

không bảo đảm cùng thứ tự trên hai DBMS nếu collation khác. Một quy tắc thứ tự ổn định có thể cần:
- Collation/case/accent policy rõ.
- Tie-break bằng ID duy nhất.
- Canonical sort key được duy trì.
- Không dựa vào thứ tự vật lý nếu thiếu ORDER BY.

### 41.1. Unique collision khi import

Nếu source cho phép hai username **Hoa** và **hoa** nhưng target dùng case-insensitive unique collation, import có thể lỗi hoặc gộp nhầm. Cần **báo conflict và xử lý dữ liệu nghiệp vụ**, không tự đổi chữ hoa rồi bỏ một tài khoản.

### 41.2. LIKE prefix và regex

Khi thay đổi collation, LIKE 'ha%' có thể match tập khác. Regex engine có thể không tuân theo collation theo cùng cách; full-text tokenizer lại là lớp khác. Không dùng một phép kiểm tra LIKE làm bằng chứng cho regex/FTS equivalence.

## 42. Những phép chuyển kiểu rủi ro

| Chuyển từ | Chuyển sang | Rủi ro |
|---|---|---|
| JSONB | JSON text | Mất representation, thứ tự key/duplicate key |
| VARCHAR mã | INTEGER | Mất số 0 đầu, mã có chữ lỗi |
| UUID binary | GUID string | Byte order/format/case |
| Array | Bảng liên kết | Mất thứ tự/duplicate elements |
| TIMESTAMPTZ | Local datetime | Mất instant/timezone |
| DECIMAL | FLOAT | Mất chính xác |
| Geometry 4326 | Điểm x/y không SRID | Mất hệ quy chiếu/đơn vị |
| Geography distance | Geometry distance | Mét thành độ |
| FTS rank | LIKE matching | Thay semantics/relevance |
| Vector distance | Similarity | Đảo chiều xếp hạng |
| ENUM | VARCHAR | Mất constraint/thứ tự |
| Oracle VARCHAR2 '' | Text khác DB | Empty string vs NULL |
| XMLTYPE | TEXT XML | Mất schema typing/index |
| Inet/cidr | VARCHAR | Mất mạng/subnet semantics |
| Range type | Hai timestamp | Mất exclusivity/overlap invariants |

Mỗi hàng cần có **một quy tắc chuyển đổi và một test**, thay vì sửa lỗi sau cutover.
## 43. Tình huống thực tế: chuyển hệ thống đơn hàng có JSON và vị trí

Giả sử một doanh nghiệp đang chạy PostgreSQL và chuẩn bị chuyển một phần ứng dụng sang SQL Server. Bảng nguồn dùng:

~~~sql
-- PostgreSQL với PostGIS extension:
CREATE TABLE order_event_pg (
    event_id UUID PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL,
    payload JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    location GEOGRAPHY(Point, 4326)
);
~~~

Kiểu GEOGRAPHY(Point,4326) là của **PostGIS**, không phải core PostgreSQL mặc định.

Truy vấn hiện tại:
1. Lấy customer.id bằng payload -> 'customer' ->> 'id'.
2. Tìm event có payload @> '{"status":"PAID"}'.
3. Lọc event theo ngày lịch tại Asia/Ho_Chi_Minh.
4. Tìm điểm nằm trong vòng 5 km từ kho.
5. Gửi event qua Java JDBC và API JSON.

### 43.1. Không bắt đầu bằng thay tên kiểu

Một mapping hời hợt:

~~~text
UUID        -> UNIQUEIDENTIFIER
JSONB       -> NVARCHAR(MAX)
TIMESTAMPTZ -> DATETIMEOFFSET
GEOGRAPHY   -> GEOGRAPHY
~~~

vẫn bỏ ngỏ:
- UUID bytes/string format có cùng không?
- JSONB có giữ nguyên văn bản JSON nguồn không?
- Toán tử ->/->>/@> được chuyển thế nào?
- JSON có CHECK ISJSON hoặc native type phù hợp không?
- JSON null và missing ở JSON_VALUE có bị gộp không?
- DATETIMEOFFSET có giữ timezone tên vùng không?
- SQL Server geography::Point nhận lat/lon theo thứ tự nào?
- STDistance có trả mét với SRID đã chọn không?
- Index nào thay GIN JSONB và GiST/PostGIS?
- JDBC getObject/getString xử lý kiểu mới ra sao?

### 43.2. Xác định hợp đồng dữ liệu độc lập DB

~~~text
event_id: UUID canonical, unique, stable
order_id: opaque string
payload: JSON document, schema_version=3
customerId: required nonblank string
status: one of NEW, PAID, CANCELLED
recordedAt: UTC instant, microsecond precision target
location: WGS84 [longitude,latitude], SRID 4326
nearbyRadius: meters
~~~

Precision microsecond chỉ là ví dụ hợp đồng; phải xác minh nguồn, đích và driver có bảo toàn được, nếu không cần policy rounding/truncation.

### 43.3. Adapter JSON query

Nguồn PostgreSQL:

~~~sql
SELECT event_id
FROM order_event_pg
WHERE payload @> '{"status":"PAID"}'::jsonb;
~~~

Đích SQL Server (mô hình lưu JSON với JSON_VALUE):

~~~sql
SELECT event_id
FROM dbo.order_event
WHERE JSON_VALUE(payload, '$.status') = 'PAID';
~~~

Hai truy vấn tương ứng **trong trường hợp status là scalar string hợp lệ**; không chứng minh JSONB containment và JSON_VALUE tương đương nói chung. Cần test khi status là array/object, null, missing, hoặc sai kiểu; cần thiết kế lại index.

### 43.4. Adapter spatial

Nguồn PostGIS:

~~~sql
SELECT event_id
FROM order_event_pg
WHERE ST_DWithin(
    location,
    ST_SetSRID(ST_MakePoint(106.701, 10.776), 4326)::geography,
    5000
);
~~~

Đích SQL Server cần kiểu geography và STDistance với point tạo đúng thứ tự **latitude,longitude**, rồi so trong phạm vi 5000 theo đơn vị phù hợp của SRID. Kiểm tra spatial index và plan trên target.

### 43.5. Đối soát trước cutover

- Số event và distinct event_id.
- JSON schema/required keys, null/missing.
- UUID canonical round-trip.
- Instant UTC trước/sau chuyển kiểu.
- Hàng thuộc ngày 03/10 theo giờ Việt Nam.
- Tập điểm gần/xa ở ranh giới 5 km.
- Driver type và API JSON response.
- Query plan/latency theo dữ liệu thật.

**Một migration chạy không báo lỗi vẫn có thể sai báo cáo theo ngày hoặc sai vùng giao hàng** nếu thiếu kiểm tra timezone và đơn vị khoảng cách.

## 44. Tình huống thực tế: chuyển native array sang bảng quan hệ

Giả sử PostgreSQL có:

~~~sql
CREATE TABLE bai_viet (
    id BIGINT PRIMARY KEY,
    tags TEXT[] NOT NULL
);
~~~

Dữ liệu:

~~~text
id=1, tags=['sql','json','sql']
id=2, tags=[]
id=3, tags=['database',NULL]
~~~

Nếu chuyển sang bảng PRIMARY KEY(post_id,tag), không thể bảo toàn **hai phần tử 'sql'** của bài 1; cũng không bảo toàn NULL element nếu tag NOT NULL.

### 44.1. Bảo toàn thứ tự và duplicates bằng position

~~~sql
CREATE TABLE bai_viet_tag_item (
    post_id BIGINT NOT NULL,
    vi_tri INTEGER NOT NULL,
    tag VARCHAR(60),
    PRIMARY KEY (post_id, vi_tri)
);
~~~

Sau đó:
- (1,0,'sql'), (1,1,'json'), (1,2,'sql').
- Bài 2 có 0 tag rows nhưng vẫn có bai_viet.
- Bài 3 có (3,0,'database'), (3,1,NULL) nếu contract cho phép.

Khi đọc:

~~~sql
SELECT vi_tri, tag
FROM bai_viet_tag_item
WHERE post_id = :post_id
ORDER BY vi_tri;
~~~

Ứng dụng ghép lại thành array đúng thứ tự. Nếu cột nguồn cho phép NULL array, còn phải phân biệt NULL array với empty array; có thể cần metadata/flag bổ sung.

### 44.2. Khi chỉ cần tập tag duy nhất

Nếu tags thực sự là tập không trùng, thứ tự không quan trọng, bảng PRIMARY KEY(post_id,tag) là lựa chọn hợp lý và dễ chuyển DBMS. Quyết định phải dựa trên **nghĩa dữ liệu**, không chỉ tên kiểu nguồn.

## 45. Tình huống thực tế: full-text tiếng Việt qua hai engine

Yêu cầu: tìm “học cơ sở dữ liệu” và nhận bài liên quan. Nguồn dùng PostgreSQL text search, đích dùng MySQL FULLTEXT hoặc SQLite FTS5.

### 45.1. Vì sao không chỉ thay @@ bằng MATCH?

- Tokenizer có thể tách tiếng Việt khác nhau.
- Quy tắc dấu/hoa thường khác.
- Stopwords có thể loại từ khác nhau.
- Ranking algorithm và thang điểm không giống nhau.
- Quote có thể biểu thị phrase search nhưng cú pháp khác.
- Minimum token length có thể loại từ ngắn.
- Index build/refresh/update visibility khác.

### 45.2. Contract của API tìm kiếm

- Query là từ khóa, phrase hay boolean?
- Có bỏ dấu không?
- Có phân biệt chữ hoa không?
- Cần chứa toàn bộ tokens hay chỉ một số?
- Rank có tie-break bằng ID/recency không?
- Mức relevance/precision/recall yêu cầu?
- SLA latency tối đa?
- Các trường được index là gì?

### 45.3. Fixture mẫu

~~~text
A: Học SQL cơ bản và cơ sở dữ liệu
B: Cơ sở dữ liệu quan hệ và chỉ mục
C: Học tiếng Việt cho người mới
D: Hướng dẫn SQL nâng cao
E: hoc co so du lieu khong dau
~~~

Dựa trên yêu cầu, định nghĩa expected set/rank, không so tuyệt đối một con số relevance score thô của hai engines.

### 45.4. Fallback LIKE không luôn tương đương

WHERE noi_dung LIKE '%cơ sở dữ liệu%' đòi chuỗi con liên tiếp, có thể bỏ tài liệu chứa cùng từ nhưng thứ tự khác, không có ranking full-text và khó dùng B-tree bình thường với wildcard đầu. Nếu dùng fallback, cần ghi rõ chức năng và hiệu năng suy giảm.

## 46. Bảng lỗi phổ biến và hướng xử lý

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Tên kiểu JSON giống nhau nên tương đương | Kiểu lưu/kết quả khác | Mapping và round-trip |
| Copy PostgreSQL JSONB bytes sang SQLite JSONB | Format không tương thích | Export JSON text chuẩn |
| Đánh đồng missing với JSON null | Sai PATCH business logic | Path existence + type |
| json_extract MySQL/SQLite cùng kiểu | Client mapping sai | Test scalar/null/object |
| Copy toán tử PostgreSQL @> sang MySQL | Syntax/semantics sai | Adapter theo DB |
| Lọc array không xét thứ tự | Mất nghĩa | Ordinality/position |
| Array sang bảng set unique | Mất duplicate elements | Model đúng contract |
| UUID RAW/BINARY/String map mù | Đảo bytes/sai ID | UUID canonical round-trip |
| UUID generator coi cùng version | Khác locality/order | Chọn version có chủ đích |
| BOOLEAN = TINYINT không CHECK | Nhận 2/7/99 như TRUE | CHECK hoặc native bool |
| ENUM thành VARCHAR không constraint | Giá trị ngoài danh sách | CHECK/FK lookup |
| ORDER BY enum thành VARCHAR | Thứ tự thay đổi | Sort rank riêng |
| TIMESTAMP luôn UTC | Báo cáo sai ngày | Instant/timezone mapping |
| Offset là timezone đầy đủ | Mất DST rules | Lưu zone ID nếu cần |
| Cộng 24 giờ cho ngày DST | Sai khoảng ngày | Calendar boundaries |
| Oracle DATE date-only | Mất thành phần giờ | Map chính xác |
| Regex cùng tên là cùng engine | Match khác | Fixtures Unicode |
| SQLite REGEXP mặc định có sẵn | Runtime lỗi | Đăng ký function |
| LIKE thay full-text | Sai relevance/chậm | Search adapter |
| FTS rank so tuyệt đối | Kết quả khác | Acceptance tests |
| ST_Distance luôn mét | Nhầm độ/met | Kiểm tra SRID/type |
| Đảo lat/lon | Vị trí sai | Contract tọa độ |
| ST_SetSRID như ST_Transform | Tọa độ không chuyển | Reprojection đúng |
| Spatial bbox là bán kính | False positives | Recheck distance |
| VECTOR ASC/DESC không kiểm tra | Xếp ngược hàng gần | Distance vs similarity |
| ANN coi như exact | Thiếu top-k | Recall tolerance |
| JSON index copy nguyên văn | Query scan | Index theo DBMS |
| Chỉ test 10 dòng | Không thấy vấn đề hiệu năng | Large fixtures/EXPLAIN |
| ORM tự xử lý mọi extension | Type/query lỗi | Custom adapter |
| Chỉ so row count import | Mất giá trị/collation | Canonical comparison |
| Unicode cùng hiển thị là bằng bytes | UNIQUE collisions | Normalization/collation tests |
| Dùng CAST chữa dữ liệu bẩn | Silent coercion | Validate/quarantine |
| Hai nguồn sự thật JSON+cột | Dữ liệu lệch | Ownership/sync rõ |
| Fallback không thông báo | Chức năng suy giảm âm thầm | Feature gates |
| Không pin extension version | Deploy thất bại | Capability matrix |
| Không có rollback path | Cutover khó phục hồi | Export/CDC/runbook |

## 47. Bộ kiểm thử khả chuyển tối thiểu

| Chủ đề | Ca cần kiểm tra |
|---|---|
| JSON | Object/array/scalar, valid/invalid |
| JSON | Missing key, JSON null, SQL NULL |
| JSON | Quoted keys, escaped text, Unicode |
| JSON | Duplicate keys, integer lớn, decimal |
| JSON | Set null vs remove key |
| Array | Empty, NULL array, NULL element |
| Array | Duplicate elements, thứ tự |
| UUID | Canonical string/binary round-trip |
| UUID | Hyphens/case/byte order |
| Boolean | True/false/null, invalid numeric |
| Enum | Unknown value, thêm trạng thái |
| Time | UTC/offset/local, DST, precision |
| Time | Leap day, end-of-month |
| String | Vietnamese Unicode normalization |
| String | Collation UNIQUE/case/accent |
| Regex | Flags, anchors, Unicode |
| Full-text | Tokenizer, stopwords, phrase |
| Full-text | Ranking và tie-breaking |
| Spatial | SRID, coordinate order |
| Spatial | 5 km boundary, distance unit |
| Spatial | Empty/invalid geometry |
| Vector | Dimension, metric, normalization |
| Vector | ANN recall, zero vector |
| XML | Namespaces, attributes, empty node |
| Range | Inclusive/exclusive, overlap |
| JDBC | getObject type, bind mapping |
| Performance | Explain, index, large fixtures |
| Operational | Extension/version/edition |
| Migration | Row count, distinct keys |
| Migration | Canonical values, invalid data |
| Migration | Idempotency, rollback, CDC |
| Security | Permission, untrusted paths |
## 48. Bài tập thực hành có gợi ý đáp án

Các câu hỏi độc lập, dựa trên ví dụ và nguyên tắc trong bài. Mục tiêu là lập luận đúng **ngữ nghĩa và mức phụ thuộc**, không phải ghi nhớ một danh sách hàm mà không hiểu.

### Bài 1 — Tính khả chuyển

Một câu SELECT dùng JSON_VALUE chạy được ở cả hai DBMS. Có đủ kết luận chúng tương đương không?

<details>
<summary>Đáp án</summary>

**Không.** Cần so kiểu trả về, missing/null behavior, path mode, lỗi, giới hạn độ dài, collation, index và phiên bản.

</details>

### Bài 2 — Năm mức tương thích

Nêu năm mức cần kiểm tra khi port kiểu/hàm mở rộng.

<details>
<summary>Đáp án</summary>

**Cú pháp, kiểu lưu trữ, ngữ nghĩa, tích hợp ứng dụng, hiệu năng/vận hành.**

</details>

### Bài 3 — JSONB

PostgreSQL JSONB và SQLite JSONB có trao đổi trực tiếp cùng binary bytes được không?

<details>
<summary>Đáp án</summary>

**Không.** Chúng là các format nội bộ khác nhau. Dùng JSON text/định dạng trao đổi được xác định rồi parse ở đích.

</details>

### Bài 4 — SQL NULL

Payload SQL NULL khác JSON object có coupon=null thế nào?

<details>
<summary>Đáp án</summary>

SQL NULL nghĩa là cột không có JSON document; JSON object vẫn tồn tại và có key coupon với JSON null.

</details>

### Bài 5 — Missing key

JSON có coupon=null và JSON không có coupon có cùng nghĩa trong PATCH không?

<details>
<summary>Đáp án</summary>

**Không mặc định.** Cần contract: null có thể mang nghĩa xóa/đặt null, missing có thể là không thay đổi. Muốn phân biệt cần kiểm tra path existence.

</details>

### Bài 6 — Chuỗi "null"

Giá trị JSON coupon="null" có phải JSON null không?

<details>
<summary>Đáp án</summary>

**Không.** Đây là JSON string chứa bốn ký tự n-u-l-l, không phải literal JSON null.

</details>

### Bài 7 — PostgreSQL JSON scalar

Cú pháp nào lấy customer.id dưới dạng text từ jsonb payload?

<details>
<summary>Đáp án</summary>

~~~sql
SELECT payload -> 'customer' ->> 'id'
FROM don_hang_payload;
~~~

</details>

### Bài 8 — MySQL JSON scalar

Muốn lấy customer.id thành chuỗi, viết một mẫu MySQL.

<details>
<summary>Đáp án</summary>

~~~sql
SELECT JSON_UNQUOTE(
    JSON_EXTRACT(payload, '$.customer.id')
)
FROM don_hang_payload;
~~~

</details>

### Bài 9 — SQL Server JSON scalar

Hàm nào thường dùng lấy scalar từ JSON ở SQL Server?

<details>
<summary>Đáp án</summary>

**JSON_VALUE(payload, '$.customer.id')** khi kiểu/cấu hình phù hợp.

</details>

### Bài 10 — SQLite json_extract

Vì sao không thể mặc định SQLite json_extract trả cùng JSON type như MySQL JSON_EXTRACT?

<details>
<summary>Đáp án</summary>

SQLite có thể trả SQL scalar INTEGER/TEXT/REAL/NULL khi một path trỏ tới scalar; MySQL trả giá trị theo JSON semantics của nó. Điều này ảnh hưởng kiểu đọc ở driver và phép so sánh.

</details>

### Bài 11 — JSON array thành hàng

Một JSON array items có ba phần tử. jsonb_array_elements hoặc json_each có thể tạo bao nhiêu hàng?

<details>
<summary>Đáp án</summary>

**Ba hàng** cho document đó nếu path là array hợp lệ và không có thêm điều kiện lọc. Khi JOIN tiếp với bảng khác, cardinality có thể nhân tiếp.

</details>

### Bài 12 — JSON path có dấu chấm

Key "customer.name" có luôn truy cập bằng $.customer.name không?

<details>
<summary>Đáp án</summary>

**Không.** Đường dẫn đó thường chỉ key name bên trong object customer. Key chứa dấu chấm cần cú pháp escape/quoted key của DBMS.

</details>

### Bài 13 — JSON update

JSON_SET/JSON_MODIFY/jsonb_set đều cập nhật JSON. Có thể dùng cùng tham số/cú pháp không?

<details>
<summary>Đáp án</summary>

**Không.** Path syntax, value representation, null/remove semantics, returning type và mức hỗ trợ đều khác.

</details>

### Bài 14 — JSON index

PostgreSQL GIN index trên JSONB có thể CREATE nguyên văn trong SQL Server không?

<details>
<summary>Đáp án</summary>

**Không.** SQL Server có cơ chế chỉ mục khác, ví dụ computed columns/index và những tính năng JSON index theo phiên bản.

</details>

### Bài 15 — Array native

Một cột PostgreSQL TEXT[] có thể đổi trực tiếp thành cùng loại cột trên MySQL không?

<details>
<summary>Đáp án</summary>

**Không có kiểu native array SQL chung cùng semantics.** Có thể dùng JSON array hoặc bảng liên kết, sau khi xác định tính thứ tự, duplicate và NULL.

</details>

### Bài 16 — Array duplicates

Array ['sql','sql'] chuyển sang bảng PRIMARY KEY(post_id,tag) có bảo toàn không?

<details>
<summary>Đáp án</summary>

**Không.** PRIMARY KEY(post_id,tag) không cho duplicate tag. Nếu phải giữ cả hai phần tử, dùng position với khóa (post_id,position).

</details>

### Bài 17 — Empty vs NULL array

[] và NULL có nên mặc định quy về một giá trị không?

<details>
<summary>Đáp án</summary>

**Không.** [] là mảng có không phần tử; NULL có thể mang nghĩa không biết/không được gửi. Contract quyết định.

</details>

### Bài 18 — UUID native

Kể tên một kiểu/cách lưu UUID ở PostgreSQL, SQL Server và SQLite.

<details>
<summary>Đáp án</summary>

PostgreSQL **uuid**, SQL Server **uniqueidentifier**, SQLite thường dùng **TEXT/BLOB** hoặc giải pháp ứng dụng.

</details>

### Bài 19 — Oracle SYS_GUID

SYS_GUID() trả chuỗi UUID có dấu gạch cùng format PostgreSQL không?

<details>
<summary>Đáp án</summary>

**Không mặc định.** SYS_GUID trả RAW; phải format/parse theo contract UUID canonical và test byte order.

</details>

### Bài 20 — UUID binary

Vì sao không nên chuyển UUID thành BINARY(16) bằng thao tác copy bytes không kiểm tra?

<details>
<summary>Đáp án</summary>

Có thể khác byte order/representation giữa API/DBMS, khiến cùng logical UUID thành bytes khác. Cần round-trip fixtures.

</details>

### Bài 21 — Boolean

MySQL BOOLEAN có đồng nhất native Boolean PostgreSQL không?

<details>
<summary>Đáp án</summary>

**Không.** MySQL BOOLEAN/BOOL thường alias TINYINT(1); có thể cần CHECK/validation để chỉ nhận 0/1 và NULL theo nghiệp vụ.

</details>

### Bài 22 — ENUM

Chuyển PostgreSQL ENUM sang VARCHAR có thể mất điều gì?

<details>
<summary>Đáp án</summary>

Có thể mất **tập giá trị hợp lệ**, thứ tự so sánh và ràng buộc kiểu. Dùng CHECK/FK lookup và sort order rõ.

</details>

### Bài 23 — Timezone

2026-10-03T00:30:00+07:00 là ngày mấy theo UTC?

<details>
<summary>Đáp án</summary>

Là **2026-10-02 17:30:00 UTC**. Ngày theo timezone địa phương có thể khác ngày UTC.

</details>

### Bài 24 — Offset và zone

Lưu +07:00 có đủ để biết timezone IANA của một địa điểm trong mọi mùa không?

<details>
<summary>Đáp án</summary>

**Không.** Offset là độ lệch tại thời điểm; tên vùng và quy tắc DST/lịch sử cần zone ID riêng nếu nghiệp vụ yêu cầu.

</details>

### Bài 25 — DST

Tại sao lọc ngày địa phương bằng cách lấy UTC start + 24 giờ có thể sai?

<details>
<summary>Đáp án</summary>

Ngày có DST có thể dài 23 hoặc 25 giờ. Tính đầu ngày và đầu ngày kế tiếp trong timezone địa phương, rồi đổi sang UTC instants.

</details>

### Bài 26 — Oracle DATE

Oracle DATE có phải chỉ chứa ngày không?

<details>
<summary>Đáp án</summary>

**Không.** Oracle DATE có cả thành phần giờ/phút/giây, khác cách một số hệ/ứng dụng hiểu kiểu DATE.

</details>

### Bài 27 — INTERVAL

DATEADD(day,7,...) của SQL Server có chạy nguyên trên SQLite không?

<details>
<summary>Đáp án</summary>

**Không.** SQLite có hàm và time modifiers như datetime('now','+7 days'); kiểu kết quả và timezone cần kiểm thử.

</details>

### Bài 28 — REGEXP SQLite

SQLite REGEXP có luôn hoạt động trên mọi bản build không?

<details>
<summary>Đáp án</summary>

**Không.** Thường cần application-defined function hoặc extension cung cấp logic REGEXP.

</details>

### Bài 29 — Regex flags

Hai engine đều có REGEXP_LIKE có bảo đảm \w và Unicode classes như nhau không?

<details>
<summary>Đáp án</summary>

**Không.** Cần test character classes, Unicode, flags, anchors, case/diacritics và các tính năng regex.

</details>

### Bài 30 — Full-text

Có thể thay PostgreSQL @@ tsquery bằng MySQL MATCH AGAINST mà giữ nguyên rank không?

<details>
<summary>Đáp án</summary>

**Không bảo đảm.** Khác tokenization, stemming, stopword, query syntax, ranking và index.

</details>

### Bài 31 — Tiếng Việt

Tại sao full-text search “cơ sở dữ liệu” cần fixture riêng?

<details>
<summary>Đáp án</summary>

Phân tách từ tiếng Việt, dấu thanh, Unicode normalization và stopwords khác nhau giữa engines; kết quả/relevance có thể khác.

</details>

### Bài 32 — SRID

ST_SetSRID(geometry,4326) có tự chuyển tọa độ projection sang WGS84 không?

<details>
<summary>Đáp án</summary>

**Không.** Nó chủ yếu gắn nhãn SRID; cần transformation thực sự như ST_Transform với định nghĩa SRS phù hợp.

</details>

### Bài 33 — Geometry distance

ST_Distance giữa hai geometry ở SRID 4326 có chắc trả mét không?

<details>
<summary>Đáp án</summary>

**Không.** Geometry khoảng cách có thể trả đơn vị tọa độ (thường độ). Muốn mét dùng geography/geodesic hoặc projection đúng.

</details>

### Bài 34 — Lat/lon

PostGIS ST_MakePoint và SQL Server geography::Point nhận cùng thứ tự tọa độ không?

<details>
<summary>Đáp án</summary>

**Không.** ST_MakePoint thường nhận x=longitude,y=latitude; geography::Point của SQL Server nhận latitude,longitude.

</details>

### Bài 35 — Spatial bbox

Lọc bounding box có tương đương “trong vòng 5 km” không?

<details>
<summary>Đáp án</summary>

**Không.** Bounding box chỉ tìm ứng viên trong hình chữ nhật; phải recheck khoảng cách chính xác để có bán kính.

</details>

### Bài 36 — PostGIS

PostGIS có phải chức năng built-in được bật ở mọi database PostgreSQL không?

<details>
<summary>Đáp án</summary>

**Không.** Là extension cần cài/bật theo môi trường và chính sách quyền/phiên bản.

</details>

### Bài 37 — SQLite spatial

SQLite thuần có đầy đủ hàm SpatiaLite không?

<details>
<summary>Đáp án</summary>

**Không.** Cần extension hoặc build hỗ trợ; phải kiểm tra môi trường thật.

</details>

### Bài 38 — Vector search

Một DB trả cosine similarity càng cao càng gần, DB khác trả cosine distance càng thấp càng gần. Nếu giữ ORDER BY DESC ở cả hai thì sao?

<details>
<summary>Đáp án</summary>

Có thể **đảo kết quả**, đưa điểm xa lên trước. Contract phải chỉ rõ metric và hướng sort.

</details>

### Bài 39 — ANN

Approximate nearest neighbor index có cam kết exact top-k không?

<details>
<summary>Đáp án</summary>

**Không mặc định.** Cần đo recall/tolerance và xác định có cần exact search không.

</details>

### Bài 40 — Embedding dimension

Một ứng dụng chuyển model từ 768 chiều sang 1536 chiều. Có thể giữ nguyên cột/index vector cũ không?

<details>
<summary>Đáp án</summary>

Không thể mặc định. Kiểu/index có thể yêu cầu dimension cố định; phải version model, migrate/re-embed và test metric.

</details>

### Bài 41 — Range type

Đổi PostgreSQL range sang start_at,end_at có đủ giữ ràng buộc không chồng lấn không?

<details>
<summary>Đáp án</summary>

**Không.** Cần interval boundary semantics và constraint/transaction đảm bảo overlap invariants nếu nghiệp vụ yêu cầu.

</details>

### Bài 42 — IP address

Lưu inet/cidr thành VARCHAR rồi so chuỗi có bảo toàn subnet containment không?

<details>
<summary>Đáp án</summary>

**Không.** So chuỗi không tương đương kiểm tra IP/subnet; cần parse/canonicalization và logic mạng.

</details>

### Bài 43 — JSON và equality

Hai JSON objects khác thứ tự key có bắt buộc khác nhau về ngữ nghĩa không?

<details>
<summary>Đáp án</summary>

Không nhất thiết. JSON object key order thường không mang ngữ nghĩa, nhưng nếu cần byte-for-byte signature/raw audit thì khác thứ tự key là khác bytes. Cần phân biệt semantic equality và raw equality.

</details>

### Bài 44 — Unicode UNIQUE

Source cho phép 'Hoa' và 'hoa', target dùng case-insensitive UNIQUE. Migration có thể gặp gì?

<details>
<summary>Đáp án</summary>

**Unique collision**. Cần báo mâu thuẫn và giải quyết theo nghiệp vụ; không tự xóa một hàng.

</details>

### Bài 45 — JDBC

UUID từ PostgreSQL được getObject() thành UUID nhưng MySQL CHAR(36) thành String. Có nên để domain code phụ thuộc getObject() trực tiếp không?

<details>
<summary>Đáp án</summary>

Không nếu cần khả chuyển. Tầng persistence adapter nên parse cả hai thành domain type java.util.UUID theo contract.

</details>

### Bài 46 — Tiền tệ

DECIMAL(14,2) chuyển sang DOUBLE có thể gây rủi ro gì?

<details>
<summary>Đáp án</summary>

Mất độ chính xác decimal, sai ranh giới so sánh/tổng tiền. Java nên dùng BigDecimal và kiểu NUMERIC/DECIMAL tương đương.

</details>

### Bài 47 — Index migration

Có GIN index JSONB trên PostgreSQL. Sau khi chuyển MySQL, SQL tương đương chạy chậm. Bước xử lý?

<details>
<summary>Đáp án</summary>

Xác định path/predicate trọng yếu; xem EXPLAIN; thiết kế generated/functional index hoặc cơ chế MySQL phù hợp, đo trên dữ liệu thật và cân đối chi phí ghi.

</details>

### Bài 48 — Capability detection

Cùng một bản ứng dụng chạy SQL Server nhiều phiên bản. Có nên giả định native JSON/vector features đều sẵn không?

<details>
<summary>Đáp án</summary>

**Không.** Phải kiểm tra version/edition/compatibility/features, dùng adapter/fallback đã kiểm thử hoặc từ chối startup khi thiếu tính năng bắt buộc.

</details>

### Bài 49 — Migration schema

Vì sao không chỉ thay tên cột JSONB thành NVARCHAR(MAX) là xong?

<details>
<summary>Đáp án</summary>

Vì còn validation, JSON path, null semantics, indexes, client mapping, constraints, hiệu năng và dữ liệu JSON đã canonicalize.

</details>

### Bài 50 — Round-trip

Nêu ba nhóm dữ liệu biên tối thiểu khi port JSON + timestamp + UUID.

<details>
<summary>Đáp án</summary>

JSON missing/null/numeric precision; timestamp UTC offset và phần giây; UUID binary/string/byte order. Thực tế nên thêm Unicode và invalid input.

</details>

### Bài 51 — Phương án khả chuyển

Ứng dụng cần danh sách tags không trùng, không quan tâm thứ tự, chạy trên năm DBMS. Nên cân nhắc mô hình nào?

<details>
<summary>Đáp án</summary>

Bảng liên kết **(post_id,tag)** với PRIMARY KEY/FOREIGN KEY phù hợp hơn phụ thuộc native array. Vẫn phải kiểm tra charset/collation và uniqueness.

</details>

### Bài 52 — Vendor lock-in có chủ đích

Ứng dụng cố định PostgreSQL, cần truy vấn JSON containment rất nhiều. Có phải tuyệt đối tránh JSONB/GIN không?

<details>
<summary>Đáp án</summary>

**Không.** Có thể dùng JSONB+GIN như lựa chọn có chủ đích; ghi phụ thuộc, pin version/extension, test và có đường export tương thích nếu sau này chuyển DB.

</details>

### Bài 53 — Fallback không tương đương

Nếu PostGIS không có và ứng dụng thay bán kính 5 km bằng bounding box rồi trả thẳng tất cả hàng, lỗi gì?

<details>
<summary>Đáp án</summary>

Có thể trả **false positives** trong hình chữ nhật nhưng ngoài bán kính. Fallback phải recheck distance hoặc thông báo mức suy giảm rõ.

</details>

### Bài 54 — Tổng hợp

Di chuyển PostgreSQL JSONB, UUID, TIMESTAMPTZ, TEXT[], PostGIS sang SQLite trên thiết bị. Đề xuất quy trình.

<details>
<summary>Đáp án</summary>

1. Kiểm tra SQLite version/build, JSON functions, FTS5 và spatial extension.
2. Xác định contract JSON null/missing, UUID, instant, array order, SRID.
3. Export JSON text, UUID canonical, UTC instant, GeoJSON/WKT kèm SRID và tags đúng cấu trúc.
4. Map schema SQLite TEXT/BLOB/INTEGER, bảng liên kết hoặc JSON array, expression index, SpatiaLite nếu hỗ trợ.
5. Viết query adapters, không copy JSONB/PostGIS operators.
6. Test round-trip null/Unicode/precision/lat-lon/5km/array.
7. Đối soát khóa, số hàng, giá trị, plan và latency.
8. Chuẩn bị cutover, retry/idempotency và rollback.

</details>

## 49. Bài tập tình huống mở rộng

### Tình huống A — API PATCH dữ liệu bán cấu trúc

Hệ nhận hai payload:

~~~json
{"customer":{"phone":null}}
~~~

và:

~~~json
{"customer":{}}
~~~

Yêu cầu: object đầu phải xóa số điện thoại, object sau không đổi số điện thoại.

**Thách thức:** Nếu adapter chỉ dùng JSON_VALUE(phone) rồi kiểm tra IS NULL, nó có thể trộn hai trạng thái. Cần **path existence** và quy tắc JSON null rõ ràng.

<details>
<summary>Gợi ý giải pháp</summary>

- Kiểm tra key phone có xuất hiện không.
- Không xuất hiện → không sửa.
- Xuất hiện với JSON null → xóa/set null theo contract.
- Xuất hiện với string → validate rồi cập nhật.
- Tách semantic PATCH khỏi SQL; adapter thực thi theo dialect.
- Test missing, null, string rỗng, string "null", invalid type và concurrency.

</details>

### Tình huống B — Thứ tự tọa độ

Ứng dụng dùng WGS84 để tìm địa điểm trong 5 km quanh kho. PostGIS ST_MakePoint nhận x/y, còn SQL Server geography::Point nhận latitude/longitude.

<details>
<summary>Gợi ý giải pháp</summary>

- Domain type Location(latitude,longitude) có tên rõ.
- PostGIS ST_MakePoint(longitude,latitude).
- SQL Server geography::Point(latitude,longitude,4326).
- Kiểm tra SRID và đơn vị mét.
- Dùng fixture điểm đúng vị trí và gần biên 5 km.
- So tập IDs được trả, index plan và latency.

</details>

### Tình huống C — Ngày địa phương

Nguồn PostgreSQL timestamptz, đích MySQL DATETIME. Báo cáo nhóm đơn theo ngày Asia/Ho_Chi_Minh.

<details>
<summary>Gợi ý giải pháp</summary>

- Domain value là Instant.
- Lưu UTC có quy ước rõ khi dùng DATETIME.
- Tính hai mốc start/end theo calendar Asia/Ho_Chi_Minh.
- Đổi mốc sang UTC instants rồi dùng khoảng nửa mở.
- Test đầu/cuối ngày, phần giây và khác biệt ngày UTC/địa phương.
- Kiểm tra precision và driver mapping.

</details>

### Tình huống D — Tìm kiếm tiếng Việt

Ứng dụng có API:

~~~text
searchArticles(query, language, limit) -> ranked article IDs
~~~

Nguồn PostgreSQL text search, đích SQLite FTS5.

<details>
<summary>Gợi ý giải pháp</summary>

- Xác định tokenizer/ngôn ngữ mong muốn hoặc ghi rõ khác biệt.
- Fixtures dấu tiếng Việt, không dấu, case, phrase, từ ngắn.
- Adapter PostgreSQL/SQLite.
- Rank direction và tie-break ổn định.
- Đánh giá relevance bằng expected set và latency, không so score thô.
- Bảo đảm FTS virtual table đồng bộ khi bài viết đổi.

</details>

### Tình huống E — Vector ranking

API hiện trả cosine similarity. Engine mới chỉ trả cosine distance và có HNSW approximate index.

<details>
<summary>Gợi ý giải pháp</summary>

- Chuẩn hóa metric/hướng điểm ở domain.
- Truy vấn distance ORDER BY ASC.
- Kiểm tra dimension, model version, normalization, NULL và zero vectors.
- Đo ANN recall so exact baseline, latency và tie-break.
- Ghi index/version để theo dõi độ lệch sau rebuild.
- Không coi kết quả approximate là exact equality.

</details>

## 50. Checklist triển khai trước khi cam kết đa DBMS

- [ ] Biết DBMS, edition, version, build và extensions.
- [ ] Đã ghi contract null/missing, precision, collation và kiểu.
- [ ] Liệt kê tất cả kiểu/hàm mở rộng trong schema và query.
- [ ] Có fixture giá trị bình thường, biên và dữ liệu lỗi.
- [ ] Có mapping source → domain → target.
- [ ] Có adapter cho JSON/spatial/full-text/vector nếu dùng.
- [ ] Có ràng buộc UNIQUE/FK/CHECK tương đương.
- [ ] Có index design và EXPLAIN theo DBMS.
- [ ] Có JDBC/ORM round-trip tests.
- [ ] Có Unicode/timezone/UUID tests.
- [ ] Có benchmark trên dữ liệu đủ lớn.
- [ ] Có transaction/concurrency/idempotency tests.
- [ ] Có kế hoạch export/cutover/rollback.
- [ ] Có giám sát latency, errors và data drift.
- [ ] Mọi fallback giảm chất lượng đều được mô tả.

## 51. Tổng kết cần ghi nhớ

1. **SQL chuẩn không làm mọi kiểu và hàm mở rộng trở nên khả chuyển tự động.**
2. Cùng tên kiểu có thể khác **format lưu, ngữ nghĩa, kiểu kết quả, NULL behavior, chỉ mục và driver mapping**.
3. **PostgreSQL JSONB và SQLite JSONB không tương thích dạng binary**; dùng định dạng trao đổi được xác định khi chuyển hệ.
4. **SQL NULL, JSON null, missing key và string "null" khác nhau**; dùng path-existence/type check khi cần.
5. JSON_EXTRACT/JSON_VALUE/JSON_TABLE/OPENJSON/json_each có cú pháp/kiểu kết quả khác.
6. Native ARRAY, ENUM, range, inet, hstore, hierarchyid và các kiểu tùy biến không có tương đương một–một phổ quát.
7. **UUID/GUID** cần kiểm tra bytes, format, version, byte order và index locality.
8. **BOOLEAN/ENUM** có thể cần CHECK hoặc lookup table để bảo toàn dữ liệu hợp lệ.
9. **TIMESTAMP có timezone** đòi xác định instant, offset, zone ID, precision và DST.
10. **Regex, collation, full-text** có thể trả kết quả khác, nhất là tiếng Việt và Unicode.
11. **Spatial** cần SRID, trật tự lat/lon, đơn vị và type geometry/geography; khoảng cách tính bằng độ không phải mét.
12. **Vector search** cần hợp đồng metric, score direction, dimension và ANN recall.
13. **Có feature không đồng nghĩa có index tương ứng**: phải đo execution plan và dữ liệu thật.
14. **JDBC/ORM không che hết khác biệt**: cần persistence adapters và domain types rõ.
15. Khả chuyển bắt đầu từ **contract dữ liệu và kiểm thử ngữ nghĩa**, không phải đổi tên datatype.
16. Có thể chấp nhận **extension vendor-specific có chủ đích** nếu được version hóa và có export/test path.
17. Mỗi migration cần round-trip fixtures, reconciliation, performance checks và rollback plan.
18. Trước mỗi kiểu/hàm mở rộng hãy hỏi: **“Nó biểu diễn nghĩa gì, hệ đích hiểu giống không và điều gì xảy ra ở NULL, giá trị biên, index cùng client?”**

### Tài liệu chính thức nên tham khảo

Khi triển khai, đối chiếu **đúng hệ quản trị và phiên bản**:

- **PostgreSQL Documentation:** JSON Types and Functions; Arrays; UUID; Date/Time Types; Text Search; Expression Indexes; Range Types; Type Conversion.
- **PostGIS Documentation:** Geometry/Geography; SRID; ST_Distance; ST_DWithin; ST_SetSRID; ST_Transform.
- **MySQL Reference Manual:** JSON Data Type and Functions; JSON_TABLE; Spatial Types and Functions; Collations; FULLTEXT; Date/Time Types.
- **Microsoft Learn — SQL Server:** JSON Data; JSON_VALUE/OPENJSON/JSON_MODIFY; uniqueidentifier; geometry/geography; Full-Text Search; datetimeoffset; Collation.
- **Oracle SQL Language Reference:** SQL/JSON; JSON Data Type; Datetime; XMLTABLE; Collection Types; Regular Expressions; Conversion.
- **Oracle Spatial and Oracle Text Documentation:** SDO_*; Spatial Indexes; CONTAINS.
- **SQLite Documentation:** JSON Functions; JSONB; Datatypes; FTS5; Expression Indexes; Date/Time Functions; Application-Defined SQL Functions.
- **Java/JDBC Documentation:** PreparedStatement; ResultSet; java.time; UUID; BigDecimal; Vendor-specific mappings.

**Thông điệp cuối cùng:** Muốn SQL khả chuyển, hãy **bảo toàn nghĩa dữ liệu trước, chuyển cú pháp sau và đo hiệu năng cuối cùng**. Một câu lệnh chạy không báo lỗi trên hệ mới chỉ là bước đầu; khi NULL, timezone, Unicode, kiểu trả về, chỉ mục và ứng dụng đều đã được kiểm chứng, migration mới có cơ sở để được coi là đúng.



