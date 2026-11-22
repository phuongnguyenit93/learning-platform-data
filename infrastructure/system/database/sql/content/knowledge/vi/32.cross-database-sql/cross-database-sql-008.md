# UPSERT, MERGE, RETURNING và OUTPUT

Trong ứng dụng dữ liệu, ta thường cần **ghi một bản ghi nếu chưa tồn tại, hoặc cập nhật bản ghi hiện có nếu đã tồn tại**. Mẫu này thường được gọi là **UPSERT** (*UPDATE + INSERT*). Nó xuất hiện trong đồng bộ dữ liệu, nhập sự kiện, cập nhật tồn kho, ghi trạng thái thanh toán, đồng bộ cache và xử lý dữ liệu đến lặp lại.

Các hệ quản trị SQL cung cấp những cơ chế khác nhau:

- **PostgreSQL:** `INSERT ... ON CONFLICT DO UPDATE`, `MERGE` và `RETURNING`.
- **MySQL:** `INSERT ... ON DUPLICATE KEY UPDATE`; không có câu lệnh `MERGE` tương đương trong MySQL.
- **SQL Server:** `MERGE` hoặc mô hình `UPDATE` rồi `INSERT` trong transaction; `OUTPUT` trả các hàng đã bị tác động.
- **Oracle Database:** `MERGE`; `RETURNING INTO` dùng với một số câu DML riêng, nhưng không phải mệnh đề trả hàng của `MERGE`.
- **SQLite:** `INSERT ... ON CONFLICT DO UPDATE` và `RETURNING` ở phiên bản hỗ trợ.

Các từ khóa này giải quyết những vấn đề liên quan nhưng không đồng nghĩa:

- **UPSERT/MERGE** xác định cách áp dụng dữ liệu mới lên dữ liệu đích.
- **RETURNING/OUTPUT** trả lại thông tin về những hàng bị tác động.
- **Unique constraint/index** là cơ chế quan trọng để xác định hai bản ghi có cùng danh tính và ngăn dữ liệu trùng.
- **Transaction và concurrency control** bảo đảm các thao tác đồng thời không phá vỡ invariant.

Bài thuộc **Database SQL → SQL đa hệ quản trị → UPSERT, MERGE, RETURNING và OUTPUT**. Mục tiêu là hiểu đúng ngữ nghĩa từng phương ngữ, lựa chọn cách ghi an toàn, trả kết quả cho ứng dụng và xử lý cạnh tranh giữa nhiều transaction.

---

## 1. Bài toán UPSERT

Giả sử có bảng tồn kho với mỗi SKU chỉ được xuất hiện một lần:

```sql
CREATE TABLE inventory (
    sku       VARCHAR(40) PRIMARY KEY,
    quantity  INTEGER NOT NULL CHECK (quantity >= 0),
    updated_at TIMESTAMP NOT NULL
);
```

Ứng dụng nhận dữ liệu:

```text
sku = "BK-01"
quantity = 25
```

Mong muốn:

- Nếu `BK-01` chưa có: INSERT một hàng mới.
- Nếu `BK-01` đã có: UPDATE quantity theo quy tắc nghiệp vụ.

Đây là một thao tác UPSERT.

### 1.1. Vì sao không nên viết SELECT rồi INSERT/UPDATE đơn giản?

Một cách dễ nghĩ:

```text
SELECT xem SKU đã tồn tại chưa
       │
       ├── Có    → UPDATE
       │
       └── Chưa  → INSERT
```

Khi chỉ có một client, cách này có vẻ hoạt động. Nhưng hai transaction có thể chạy đồng thời:

```text
Transaction A                    Transaction B
-------------                    -------------
SELECT SKU X: chưa có            SELECT SKU X: chưa có
                                 
INSERT SKU X                     INSERT SKU X
COMMIT                           lỗi UNIQUE
```

Nếu không có unique constraint, cả hai có thể chèn bản ghi trùng. Nếu có constraint, một transaction nhận lỗi; ứng dụng phải xử lý retry hoặc dùng cơ chế UPSERT nguyên tử của DBMS.

**Kiểm tra tồn tại trước rồi mới ghi không tự tạo tính nguyên tử.** Unique constraint vẫn cần thiết kể cả khi đã dùng UPSERT.

### 1.2. Xác định khóa xung đột

UPSERT cần một quy tắc nhận diện hàng đích:

- Khóa chính như `sku`.
- Unique key như `(tenant_id, external_id)`.
- Unique index có điều kiện nếu nghiệp vụ cần phạm vi duy nhất đặc biệt.

Ví dụ:

```sql
CREATE UNIQUE INDEX uq_customer_external
ON customer_import (tenant_id, external_id);
```

Khi dữ liệu mới có cùng cặp khóa, DBMS có thể coi đó là một xung đột cần cập nhật.

Không nên chọn một cột tình cờ giống nhau làm khóa UPSERT. Khóa phải thể hiện **danh tính nghiệp vụ** của hàng.

---

## 2. UPSERT có thể có nhiều chính sách cập nhật

Cùng một khóa xung đột nhưng cách cập nhật có thể khác:

| Chính sách | Hành vi khi đã tồn tại |
| --- | --- |
| Replace | Thay các cột được chỉ định bằng giá trị mới |
| Increment | Cộng số lượng mới vào số lượng cũ |
| Update if newer | Chỉ cập nhật nếu phiên bản/thời gian mới hơn |
| Update non-null | Chỉ ghi đè những cột đầu vào có giá trị |
| Ignore | Giữ hàng cũ, không cập nhật |
| Compare-and-set | Chỉ cập nhật khi version hiện tại khớp giá trị kỳ vọng |

Ví dụ tồn kho:

```sql
-- Chính sách replace:
quantity = incoming_quantity

-- Chính sách increment:
quantity = current_quantity + incoming_quantity
```

Hai quy tắc khác nhau về nghiệp vụ. Không được thay thế một quy tắc bằng quy tắc kia chỉ vì cú pháp UPSERT giống nhau.

### 2.1. NULL có nghĩa gì?

Giả sử nguồn gửi:

```json
{"sku":"BK-01","quantity":null}
```

Có thể hiểu là:

- Ghi đè quantity thành NULL (nếu schema cho phép).
- Không thay đổi quantity hiện tại.
- Dữ liệu không hợp lệ và cần từ chối.

Đừng tự dùng `COALESCE(incoming.quantity, current.quantity)` nếu chưa xác định hợp đồng của NULL. Cần phân biệt **không gửi thuộc tính**, **gửi JSON null** và **gửi một giá trị SQL NULL** nếu pipeline có ý nghĩa khác nhau.

---

## 3. RETURNING và OUTPUT là gì?

Sau khi ghi, ứng dụng có thể cần biết:

- Hàng vừa INSERT hay UPDATE?
- Khóa chính do database tạo là gì?
- Giá trị cuối cùng sau DEFAULT, trigger hoặc phép cập nhật?
- Version mới là bao nhiêu?
- Hàng nào trong batch được chấp nhận?
- Giá trị trước và sau thay đổi là gì?

Đây là mục đích của **RETURNING** và **OUTPUT**.

### 3.1. RETURNING

Một số DBMS có mệnh đề `RETURNING`:

```sql
INSERT INTO products (sku, name)
VALUES ('BK-01', 'Notebook')
RETURNING product_id, sku, name;
```

Câu lệnh ghi dữ liệu và trả lại các cột của hàng được tác động trong cùng statement.

### 3.2. OUTPUT

SQL Server dùng `OUTPUT`:

```sql
INSERT INTO dbo.Products (sku, name)
OUTPUT inserted.product_id, inserted.sku, inserted.name
VALUES (N'BK-01', N'Notebook');
```

SQL Server còn có thể truy cập hình ảnh trước/sau qua `deleted` và `inserted` trong các DML có hỗ trợ.

### 3.3. Không phải mọi hệ có cả hai

| DBMS | UPSERT/MERGE | Trả hàng đã tác động |
| --- | --- | --- |
| PostgreSQL | ON CONFLICT; MERGE từ v15 | RETURNING; MERGE RETURNING từ v17 |
| MySQL | ON DUPLICATE KEY UPDATE | MySQL không có DML RETURNING tổng quát tương đương trong dòng 8.0/8.4 |
| SQL Server | MERGE hoặc UPDATE/INSERT | OUTPUT |
| Oracle | MERGE | RETURNING INTO cho INSERT/UPDATE/DELETE phù hợp; MERGE không có RETURNING clause tương đương |
| SQLite | ON CONFLICT DO UPDATE | RETURNING từ 3.35.0 |

**Phiên bản rất quan trọng.** PostgreSQL MERGE được giới thiệu ở v15; RETURNING cho MERGE có từ v17. SQLite RETURNING có từ 3.35.0. Kiểm tra phiên bản engine và compatibility/runtime thực tế trước khi dùng.

---

## 4. PostgreSQL: INSERT ... ON CONFLICT

PostgreSQL hỗ trợ UPSERT bằng `ON CONFLICT`, dựa trên unique constraint hoặc unique index làm arbiter.

Cú pháp khái quát:

```sql
INSERT INTO target_table (...)
VALUES (...)
ON CONFLICT (conflict_column [, ...])
DO UPDATE SET
    column = expression
[WHERE condition]
RETURNING ...;
```

Hoặc:

```sql
ON CONFLICT (...) DO NOTHING
```

### 4.1. Tạo bảng thử nghiệm

Dùng schema/database lab riêng:

```sql
CREATE TABLE lab_inventory_406 (
    sku        TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity >= 0),
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Thêm hàng ban đầu:

```sql
INSERT INTO lab_inventory_406 (
    sku, product_name, quantity
)
VALUES
    ('BK-01', 'Notebook', 10),
    ('PEN-02', 'Blue pen', 30);
```

### 4.2. INSERT nếu chưa có, UPDATE nếu trùng

```sql
INSERT INTO lab_inventory_406 (
    sku, product_name, quantity
)
VALUES (
    'BK-01', 'Notebook', 25
)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    product_name = EXCLUDED.product_name,
    version = lab_inventory_406.version + 1,
    updated_at = CURRENT_TIMESTAMP
RETURNING sku, product_name, quantity, version, updated_at;
```

Giải thích:

- `ON CONFLICT (sku)` chọn unique key gây xung đột.
- `EXCLUDED` là hàng đề xuất INSERT nhưng không được chèn theo nhánh thông thường vì conflict.
- `lab_inventory_406.quantity` là giá trị hiện tại trong hàng đích.
- `EXCLUDED.quantity` là giá trị từ input.
- `RETURNING` trả hàng được INSERT hoặc UPDATE.

Khi chạy với SKU BK-01, quantity thành 25 và version tăng từ 1 lên 2.

### 4.3. DO NOTHING

Nếu chỉ muốn bỏ qua bản ghi trùng:

```sql
INSERT INTO lab_inventory_406 (
    sku, product_name, quantity
)
VALUES ('BK-01', 'Notebook', 99)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, quantity;
```

Vì SKU đã tồn tại, không có hàng được INSERT; kết quả RETURNING là **0 hàng**.

Đừng giả định DO NOTHING sẽ trả hàng cũ. Nó chỉ trả những hàng thực sự được thao tác và đủ điều kiện RETURNING.

### 4.4. RETURNING sau UPSERT

```sql
INSERT INTO lab_inventory_406 (sku, product_name, quantity)
VALUES ('PEN-02', 'Blue pen', 35)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity
RETURNING sku, quantity, version;
```

Với nhánh UPDATE, RETURNING trả hình ảnh hàng sau khi update theo ngữ nghĩa PostgreSQL.

Nếu có trigger BEFORE làm thay đổi giá trị hàng, kết quả trả về phản ánh hàng đã được xử lý theo quy tắc RETURNING của PostgreSQL.

### 4.5. WHERE trong DO UPDATE

Có thể chỉ update nếu điều kiện đúng:

```sql
INSERT INTO lab_inventory_406 (sku, product_name, quantity, version)
VALUES ('BK-01', 'Notebook', 20, 5)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    version = EXCLUDED.version
WHERE EXCLUDED.version > lab_inventory_406.version
RETURNING sku, quantity, version;
```

Nếu version incoming không lớn hơn version hiện tại, hàng xung đột bị khóa để kiểm tra nhưng **không được UPDATE và không xuất hiện trong RETURNING**.

Đây là mẫu “chỉ nhận phiên bản mới hơn”. Trong hệ đồng bộ, version hoặc sequence cần có nguồn tin cậy và định nghĩa thứ tự rõ ràng.

### 4.6. Chọn conflict target

PostgreSQL có thể chỉ rõ:

```sql
ON CONFLICT (tenant_id, external_id) DO UPDATE ...
```

hoặc tham chiếu constraint:

```sql
ON CONFLICT ON CONSTRAINT uq_external_record DO UPDATE ...
```

Conflict target phải phù hợp unique index/constraint. PostgreSQL có cơ chế index inference; không phải mọi loại constraint đều có thể làm arbiter cho DO UPDATE. Ví dụ exclusion constraint có các giới hạn riêng.

Nếu không chỉ conflict target, `ON CONFLICT DO NOTHING` có thể bỏ qua xung đột từ bất kỳ unique/exclusion constraint phù hợp nào; điều này có thể rộng hơn ý định nghiệp vụ.

---

## 5. PostgreSQL: concurrency và atomic UPSERT

Một ưu điểm quan trọng của `INSERT ... ON CONFLICT DO UPDATE` là PostgreSQL cung cấp cơ chế xử lý xung đột nguyên tử với unique index/constraint. Hai transaction đồng thời ghi cùng khóa sẽ được điều phối bởi unique index và lock; một thao tác có thể phải chờ thao tác kia.

Tuy nhiên, vẫn cần xem xét:

- Unique key có đúng danh tính nghiệp vụ không?
- Các cột được cập nhật có tạo invariant nhiều hàng không?
- Có trigger hoặc foreign key gây thêm lock không?
- Có thể deadlock khi nhiều transaction cập nhật nhiều khóa theo thứ tự khác nhau không?
- Ứng dụng có retry lỗi serialization/deadlock theo chính sách không?

### 5.1. Increment nguyên tử

Ví dụ tăng số lượng:

```sql
INSERT INTO lab_inventory_406 (sku, product_name, quantity)
VALUES ('BK-01', 'Notebook', 5)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = lab_inventory_406.quantity + EXCLUDED.quantity
RETURNING sku, quantity;
```

Nếu tồn kho đang là 25, kết quả là 30. Phép cộng được thực hiện bên trong câu UPDATE, tránh kiểu ứng dụng đọc 25 rồi gửi lại 30 trong khi một transaction khác cũng đang tăng.

### 5.2. Không tự động bảo đảm mọi invariant nghiệp vụ

Ví dụ tổng tồn kho không được vượt hạn mức ở một bảng khác. Một điều kiện kiểm tra độc lập trước UPSERT có thể bị race giữa hai transaction. Cần ràng buộc, lock, isolation hoặc transaction thiết kế phù hợp cho toàn bộ invariant.

### 5.3. INSERT ... ON CONFLICT không phải MERGE tổng quát

ON CONFLICT tập trung xử lý xung đột unique/exclusion của INSERT. Nó không phải công cụ tổng quát để áp dụng nhiều nhánh UPDATE/DELETE/INSERT theo một source relation. Khi cần đối chiếu hai tập dữ liệu và nhiều hành động, MERGE có thể phù hợp hơn.

---

## 6. PostgreSQL: MERGE

PostgreSQL có `MERGE` từ phiên bản 15. Câu lệnh so sánh tập source với target, rồi chạy các nhánh khi khớp hoặc không khớp.

Mẫu:

```sql
MERGE INTO target AS t
USING source AS s
ON (t.key = s.key)
WHEN MATCHED THEN
    UPDATE SET ...
WHEN NOT MATCHED THEN
    INSERT (...) VALUES (...);
```

### 6.1. Ví dụ

Tạo nguồn dữ liệu:

```sql
CREATE TEMP TABLE incoming_inventory_406 (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

INSERT INTO incoming_inventory_406
VALUES
    ('BK-01', 'Notebook', 40),
    ('MUG-01', 'Coffee mug', 12);
```

MERGE:

```sql
MERGE INTO lab_inventory_406 AS t
USING incoming_inventory_406 AS s
ON (t.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET
        product_name = s.product_name,
        quantity = s.quantity,
        version = t.version + 1,
        updated_at = CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, quantity)
    VALUES (s.sku, s.product_name, s.quantity);
```

Kết quả:

- BK-01 đã có: UPDATE quantity thành 40.
- MUG-01 chưa có: INSERT hàng mới.

### 6.2. Nhiều nhánh WHEN

PostgreSQL MERGE cho phép nhiều nhánh có điều kiện:

```sql
MERGE INTO lab_inventory_406 AS t
USING incoming_inventory_406 AS s
ON (t.sku = s.sku)
WHEN MATCHED AND s.quantity = 0 THEN
    DELETE
WHEN MATCHED AND s.quantity > 0 THEN
    UPDATE SET quantity = s.quantity
WHEN NOT MATCHED AND s.quantity > 0 THEN
    INSERT (sku, product_name, quantity)
    VALUES (s.sku, s.product_name, s.quantity)
WHEN NOT MATCHED THEN
    DO NOTHING;
```

Các nhánh được xét theo thứ tự trong nhóm tương ứng; khi một hành động đã được chọn cho hàng source, các nhánh sau không tiếp tục áp dụng cho cùng hàng đó. Thiết kế điều kiện sao cho không có nhánh chồng lấn ngoài ý muốn.

### 6.3. RETURNING trên MERGE

PostgreSQL hỗ trợ RETURNING cho MERGE từ **PostgreSQL 17**:

```sql
MERGE INTO lab_inventory_406 AS t
USING incoming_inventory_406 AS s
ON (t.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET quantity = s.quantity
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, quantity)
    VALUES (s.sku, s.product_name, s.quantity)
RETURNING t.sku, t.quantity;
```

Câu lệnh trả thông tin hàng bị tác động theo khả năng RETURNING của phiên bản. PostgreSQL 15/16 có MERGE nhưng không có MERGE RETURNING như phiên bản 17+.

Khi triển khai trên hệ có nhiều major version, hãy kiểm tra version target và chạy migration/query test trên chính engine đó.

### 6.4. Source trùng khóa

Nếu source có nhiều hàng cùng match một hàng target, PostgreSQL MERGE có thể báo lỗi cardinality vì một hàng target không thể bị tác động nhiều lần trong cùng MERGE. Hãy deduplicate source theo khóa nghiệp vụ trước.

Ví dụ:

```sql
SELECT DISTINCT ON (sku)
    sku, product_name, quantity
FROM incoming_raw
ORDER BY sku, received_at DESC;
```

Đây là một cách chọn bản ghi mới nhất trong PostgreSQL; tiêu chí tie-break phải rõ ràng và ổn định.

### 6.5. MERGE và concurrency

PostgreSQL MERGE không có cùng đảm bảo xử lý concurrent unique conflict như INSERT ... ON CONFLICT DO UPDATE. Một transaction khác có thể chèn hàng sau khi MERGE xác định nhánh NOT MATCHED; thao tác INSERT có thể gặp unique violation. Với bài toán đơn giản “insert hoặc update theo unique key”, ON CONFLICT thường là lựa chọn trực tiếp hơn.

MERGE phù hợp khi cần nhiều nhánh hành động dựa trên source-target match, nhưng vẫn phải thiết kế unique constraint, isolation, retry và nguồn dữ liệu.

---

## 7. MySQL: INSERT ... ON DUPLICATE KEY UPDATE

MySQL không có câu lệnh MERGE theo cú pháp SQL Server/Oracle/PostgreSQL. Cách UPSERT thường dùng:

```sql
INSERT INTO target (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    column = value;
```

Nó được kích hoạt khi INSERT gặp xung đột PRIMARY KEY hoặc UNIQUE KEY.

### 7.1. Ví dụ

```sql
CREATE TABLE lab_inventory_mysql_406 (
    sku VARCHAR(40) NOT NULL PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    version INT NOT NULL DEFAULT 1
) ENGINE = InnoDB;

INSERT INTO lab_inventory_mysql_406
    (sku, product_name, quantity)
VALUES
    ('BK-01', 'Notebook', 10);
```

UPSERT:

```sql
INSERT INTO lab_inventory_mysql_406 (
    sku, product_name, quantity
)
VALUES (
    'BK-01', 'Notebook', 25
) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity,
    product_name = incoming.product_name,
    version = lab_inventory_mysql_406.version + 1;
```

Cú pháp row alias sau VALUES được hỗ trợ trong MySQL 8.0.19 trở lên. Nó giúp tham chiếu hàng đề xuất INSERT trong phần UPDATE.

### 7.2. VALUES(column) cũ và row alias

Một mẫu cũ:

```sql
ON DUPLICATE KEY UPDATE
    quantity = VALUES(quantity);
```

Hàm `VALUES(column)` trong ngữ cảnh ON DUPLICATE KEY UPDATE đã bị deprecated từ MySQL 8.0.20. Với MySQL hiện đại, ưu tiên row alias:

```sql
INSERT INTO lab_inventory_mysql_406 (sku, quantity, product_name)
VALUES ('BK-01', 25, 'Notebook') AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity,
    product_name = incoming.product_name;
```

Kiểm tra cú pháp và phiên bản MySQL đang triển khai, nhất là khi code cần tương thích nhiều nhánh cũ.

### 7.3. Không có conflict target tường minh như PostgreSQL

MySQL không viết `ON DUPLICATE KEY UPDATE(sku)` để chọn một unique constraint cụ thể. Xung đột từ PRIMARY KEY hoặc UNIQUE KEY có thể kích hoạt nhánh update.

Nếu bảng có nhiều unique index, một INSERT có thể xung đột với nhiều quy tắc duy nhất; MySQL có thể cập nhật hàng phù hợp theo cơ chế index được phát hiện. Tài liệu MySQL cảnh báo cần cẩn trọng với bảng có nhiều unique key khi dùng ON DUPLICATE KEY UPDATE.

Hãy thiết kế unique key rõ ràng và không giả định câu lệnh chỉ xung đột với cột mà bạn đang nghĩ đến.

### 7.4. Increment

```sql
INSERT INTO lab_inventory_mysql_406 (sku, product_name, quantity)
VALUES ('BK-01', 'Notebook', 5) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = lab_inventory_mysql_406.quantity + incoming.quantity;
```

Phép cộng thực hiện trong database, tránh read-modify-write ở ứng dụng.

### 7.5. Điều kiện update

Có thể dùng biểu thức điều kiện trong nhánh UPDATE, nhưng cú pháp MySQL không giống PostgreSQL DO UPDATE WHERE. Thường biểu diễn bằng CASE/IF trong biểu thức SET hoặc thiết kế DML riêng. Phải hiểu thứ tự gán cột và ngữ nghĩa biểu thức theo MySQL.

---

## 8. MySQL: số hàng bị ảnh hưởng và trả khóa

MySQL không có RETURNING tổng quát cho INSERT ... ON DUPLICATE KEY UPDATE trong MySQL 8.0/8.4 như PostgreSQL/SQLite. Ứng dụng thường dựa vào affected rows hoặc query lại theo khóa nghiệp vụ.

### 8.1. Affected rows

Với một hàng INSERT ... ON DUPLICATE KEY UPDATE, giá trị affected rows thông thường:

- 1 nếu INSERT hàng mới.
- 2 nếu UPDATE hàng đã tồn tại và thực sự thay đổi.
- 0 nếu hàng đã tồn tại và được gán lại giá trị hiện tại.

Nếu client dùng cờ `CLIENT_FOUND_ROWS`, trường hợp không đổi có thể được báo là 1. Vì vậy không nên coi affected rows là một hợp đồng “1=insert, 2=update” bất biến qua mọi driver/configuration.

### 8.2. LAST_INSERT_ID

Với bảng có AUTO_INCREMENT, MySQL có thể cung cấp ID được tạo thông qua `LAST_INSERT_ID()` trong một số trường hợp. Một kỹ thuật hay gặp là:

```sql
INSERT INTO lab_customer_mysql_406 (
    external_key, display_name
)
VALUES (
    'EXT-101', 'An'
) AS incoming
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    display_name = incoming.display_name;

SELECT LAST_INSERT_ID();
```

Khi conflict, phép gán `id = LAST_INSERT_ID(id)` làm giá trị ID hiện tại được đặt thành giá trị LAST_INSERT_ID của session để ứng dụng lấy lại. Đây là kỹ thuật MySQL đặc thù; phải test với driver, multi-row upsert và connection pooling.

Nó không phải một RETURNING clause và không nên dùng như cơ chế trả mọi cột trước/sau.

### 8.3. Query lại theo unique key

Nếu cần giá trị cuối cùng:

1. Thực hiện UPSERT.
2. SELECT theo unique key trong cùng transaction/connection theo isolation phù hợp.
3. Trả hàng đã lưu.

Không SELECT theo một cột không unique, vì có thể lấy sai bản ghi. Nếu có trigger hoặc thao tác đồng thời, hãy thiết kế transaction và khóa phù hợp.

---

## 9. SQL Server: MERGE

SQL Server hỗ trợ MERGE để so khớp source với target và thực hiện INSERT/UPDATE/DELETE theo nhánh.

Ví dụ:

```sql
CREATE TABLE dbo.lab_inventory_406 (
    sku NVARCHAR(40) NOT NULL PRIMARY KEY,
    product_name NVARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    version INT NOT NULL DEFAULT 1
);
```

```sql
MERGE dbo.lab_inventory_406 WITH (HOLDLOCK) AS target
USING (
    VALUES
        (N'BK-01', N'Notebook', 25),
        (N'MUG-01', N'Coffee mug', 12)
) AS source (sku, product_name, quantity)
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET
        product_name = source.product_name,
        quantity = source.quantity,
        version = target.version + 1
WHEN NOT MATCHED BY TARGET THEN
    INSERT (sku, product_name, quantity, version)
    VALUES (source.sku, source.product_name, source.quantity, 1)
OUTPUT
    $action AS action_name,
    inserted.sku,
    deleted.quantity AS old_quantity,
    inserted.quantity AS new_quantity;
```

Giải thích:

- `USING` định nghĩa source relation.
- `ON` xác định điều kiện match.
- `WHEN MATCHED` xử lý hàng target có source tương ứng.
- `WHEN NOT MATCHED BY TARGET` xử lý source chưa có target.
- `OUTPUT` trả hành động và hình ảnh hàng.

SQL Server yêu cầu kết thúc MERGE bằng dấu chấm phẩy.

### 9.1. OUTPUT $action

Trong MERGE, `$action` trả loại hành động được thực hiện, thường là `INSERT`, `UPDATE` hoặc `DELETE`.

`inserted` là hình ảnh sau thao tác (hoặc hàng mới); `deleted` là hình ảnh trước thao tác (hoặc hàng bị xóa). Với INSERT, deleted thường NULL; với DELETE, inserted thường NULL.

### 9.2. Source phải có khóa duy nhất theo match

Nếu nhiều hàng source cùng match một hàng target để UPDATE/DELETE, SQL Server có thể báo lỗi vì cùng hàng target bị tác động nhiều lần. Hãy deduplicate source theo khóa match trước MERGE.

Nếu source có hai hàng cùng SKU và target có một SKU, cần quyết định bản nào thắng hoặc tổng hợp chúng trước khi MERGE.

### 9.3. HOLDLOCK và concurrency

`HOLDLOCK` tương đương mức SERIALIZABLE trên bảng mục tiêu trong ngữ cảnh statement. Nó thường được dùng trong mẫu MERGE UPSERT để giảm race khi hai session cùng thấy khóa chưa tồn tại rồi cùng INSERT. Unique constraint vẫn là bảo vệ cuối cùng; lock có thể tăng contention và deadlock.

Không thêm HOLDLOCK theo thói quen mà không hiểu access path, index và transaction workload. Kiểm tra deadlock, blocking và retry.

---

## 10. SQL Server: OUTPUT trong INSERT, UPDATE và DELETE

OUTPUT không chỉ dành cho MERGE.

### 10.1. INSERT OUTPUT

```sql
INSERT INTO dbo.lab_inventory_406 (
    sku, product_name, quantity
)
OUTPUT
    inserted.sku,
    inserted.quantity
VALUES (
    N'PEN-02', N'Blue pen', 30
);
```

### 10.2. UPDATE OUTPUT

```sql
UPDATE dbo.lab_inventory_406
SET quantity = quantity + 5
OUTPUT
    deleted.sku,
    deleted.quantity AS old_quantity,
    inserted.quantity AS new_quantity
WHERE sku = N'BK-01';
```

### 10.3. DELETE OUTPUT

```sql
DELETE FROM dbo.lab_inventory_406
OUTPUT
    deleted.sku,
    deleted.quantity AS deleted_quantity
WHERE sku = N'PEN-02';
```

### 10.4. OUTPUT INTO

Có thể ghi kết quả vào bảng audit/staging:

```sql
DECLARE @changes TABLE (
    action_name NVARCHAR(10),
    sku NVARCHAR(40),
    old_quantity INT NULL,
    new_quantity INT NULL
);

UPDATE dbo.lab_inventory_406
SET quantity = quantity + 1
OUTPUT
    N'UPDATE',
    inserted.sku,
    deleted.quantity,
    inserted.quantity
INTO @changes (
    action_name, sku, old_quantity, new_quantity
)
WHERE sku = N'BK-01';

SELECT * FROM @changes;
```

OUTPUT INTO hữu ích khi cần tiếp tục JOIN, tổng hợp hoặc ghi log. Có các giới hạn về target, trigger và constraint của OUTPUT INTO; cần kiểm tra cú pháp cụ thể khi ghi vào bảng có trigger hoặc ràng buộc đặc biệt.

### 10.5. OUTPUT không phải bằng chứng COMMIT

SQL Server có thể trả hàng OUTPUT cho client hoặc table variable ngay cả khi statement sau đó gặp lỗi và bị rollback. Do đó không thực hiện side effect ngoài database chỉ vì đã nhận được một hàng OUTPUT.

Ứng dụng cần kiểm tra statement thành công, transaction commit thành công rồi mới gửi email, gọi API hoặc phát sự kiện. Transactional outbox là lựa chọn phù hợp cho sự kiện cần phát sau commit.

---

## 11. SQL Server: UPSERT bằng UPDATE rồi INSERT

Một số hệ thống chọn tránh MERGE và viết hai thao tác trong transaction, với lock phù hợp:

```sql
CREATE OR ALTER PROCEDURE dbo.lab_upsert_inventory_406
    @sku NVARCHAR(40),
    @product_name NVARCHAR(100),
    @quantity INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE dbo.lab_inventory_406 WITH (UPDLOCK, SERIALIZABLE)
        SET product_name = @product_name,
            quantity = @quantity,
            version = version + 1
        WHERE sku = @sku;

        IF @@ROWCOUNT = 0
        BEGIN
            INSERT INTO dbo.lab_inventory_406 (
                sku, product_name, quantity, version
            )
            VALUES (
                @sku, @product_name, @quantity, 1
            );
        END;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
```

Giải thích:

- `UPDLOCK` yêu cầu lấy update lock khi tìm hàng.
- `SERIALIZABLE` giữ khóa/range lock cần thiết tới transaction end để bảo vệ khoảng khóa chưa tồn tại khi có index phù hợp.
- Unique key trên sku vẫn bắt buộc.
- `@@ROWCOUNT` phải được đọc ngay sau UPDATE; statement khác có thể làm thay đổi giá trị này.
- `XACT_ABORT ON` và TRY/CATCH giúp quản lý lỗi transaction rõ hơn.

Đây là một mẫu cần đánh giá với index và workload cụ thể; không phải công thức bỏ qua việc đo deadlock/blocking. Nếu cần trả hàng, có thể dùng OUTPUT trong UPDATE và INSERT theo từng nhánh, hoặc SELECT lại sau thao tác trong transaction.

---

## 12. Oracle: MERGE

Oracle hỗ trợ MERGE để kết hợp UPDATE và INSERT dựa trên điều kiện match.

Ví dụ:

```sql
MERGE INTO lab_inventory_406 t
USING (
    SELECT
        'BK-01' AS sku,
        'Notebook' AS product_name,
        25 AS quantity
    FROM dual
) s
ON (t.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET
        t.product_name = s.product_name,
        t.quantity = s.quantity,
        t.version = t.version + 1
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, quantity, version)
    VALUES (s.sku, s.product_name, s.quantity, 1);
```

Bảng Oracle phải được tạo trong schema Oracle với các kiểu dữ liệu tương ứng; ví dụ này minh họa cú pháp MERGE, không chạy trên bảng PostgreSQL/SQL Server.

### 12.1. Nhiều nhánh và DELETE WHERE

Oracle MERGE có thể cập nhật hàng match, chèn hàng not match và trong một số cấu hình xóa những hàng được UPDATE thỏa điều kiện `DELETE WHERE`:

```sql
MERGE INTO inventory t
USING incoming_inventory s
ON (t.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET
        t.quantity = s.quantity
    DELETE WHERE (s.quantity = 0)
WHEN NOT MATCHED THEN
    INSERT (sku, quantity)
    VALUES (s.sku, s.quantity);
```

Điểm cần chú ý: DELETE WHERE trong Oracle MERGE áp dụng cho những hàng đã được nhánh UPDATE xử lý, dựa trên giá trị sau update theo ngữ nghĩa Oracle; nó không phải một nhánh xóa tùy ý cho mọi hàng not matched.

### 12.2. Source trùng match

Nếu source khiến một hàng target bị cập nhật nhiều lần trong cùng MERGE, Oracle có thể báo `ORA-30926: unable to get a stable set of rows in the source tables`. Hãy đảm bảo source có một hàng cho mỗi khóa match hoặc xác định quy tắc deduplicate/tổng hợp.

### 12.3. MERGE không có RETURNING clause tương đương

Oracle hỗ trợ `RETURNING INTO` với một số câu INSERT/UPDATE/DELETE, nhưng MERGE không cung cấp một mệnh đề RETURNING theo hàng tương tự PostgreSQL/SQLite. Sau MERGE, có thể dùng `SQL%ROWCOUNT` để lấy tổng số hàng bị tác động:

```sql
MERGE INTO inventory t
USING incoming_inventory s
ON (t.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET t.quantity = s.quantity
WHEN NOT MATCHED THEN
    INSERT (sku, quantity)
    VALUES (s.sku, s.quantity);

DBMS_OUTPUT.PUT_LINE('Affected rows: ' || SQL%ROWCOUNT);
```

SQL%ROWCOUNT cho tổng số hàng, không cho biết từng hàng là INSERT hay UPDATE và không trả toàn bộ old/new values.

Nếu cần chi tiết từng hàng, cân nhắc:
- Ghi audit bằng trigger phù hợp.
- Dùng staging và các câu INSERT/UPDATE riêng có RETURNING INTO trong ngữ cảnh thích hợp.
- Query lại theo khóa nghiệp vụ sau MERGE.
- Dùng một API xử lý từng hàng nếu khối lượng và hiệu năng cho phép.

---

## 13. Oracle: RETURNING INTO cho DML riêng

Ví dụ INSERT:

```sql
DECLARE
    v_id inventory.id%TYPE;
BEGIN
    INSERT INTO inventory (sku, quantity)
    VALUES ('BK-01', 25)
    RETURNING id INTO v_id;

    DBMS_OUTPUT.PUT_LINE(v_id);
END;
/
```

Ví dụ UPDATE:

```sql
DECLARE
    v_new_quantity inventory.quantity%TYPE;
BEGIN
    UPDATE inventory
    SET quantity = quantity + 5
    WHERE sku = 'BK-01'
    RETURNING quantity INTO v_new_quantity;

    DBMS_OUTPUT.PUT_LINE(v_new_quantity);
END;
/
```

RETURNING INTO trong PL/SQL có các giới hạn theo loại DML, số hàng và biến nhận kết quả. Với nhiều hàng, dùng collection/bulk binding phù hợp thay vì giả định scalar variable có thể nhận mọi hàng.

### SQL%ROWCOUNT và RETURNING là hai việc khác nhau

- SQL%ROWCOUNT: số hàng statement vừa tác động.
- RETURNING INTO: nhận giá trị cột được chỉ định.
- MERGE: có thể xem tổng số hàng tác động bằng SQL%ROWCOUNT nhưng không có MERGE RETURNING theo hàng như một số hệ khác.

---

## 14. SQLite: UPSERT và RETURNING

SQLite hỗ trợ UPSERT theo cú pháp gần PostgreSQL:

```sql
CREATE TABLE lab_inventory_sqlite_406 (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    version INTEGER NOT NULL DEFAULT 1
);
```

UPSERT:

```sql
INSERT INTO lab_inventory_sqlite_406 (
    sku, product_name, quantity
)
VALUES (
    'BK-01', 'Notebook', 25
)
ON CONFLICT(sku)
DO UPDATE SET
    product_name = excluded.product_name,
    quantity = excluded.quantity,
    version = lab_inventory_sqlite_406.version + 1
RETURNING sku, product_name, quantity, version;
```

- `ON CONFLICT(sku)` xác định unique key.
- `excluded` là hàng đề xuất INSERT.
- `RETURNING` trả hàng được INSERT hoặc UPDATE.

SQLite UPSERT được hỗ trợ từ SQLite 3.24.0. RETURNING được hỗ trợ từ 3.35.0. Nếu ứng dụng dùng runtime SQLite cũ hơn, câu có RETURNING có thể không chạy.

### 14.1. DO NOTHING

```sql
INSERT INTO lab_inventory_sqlite_406 (sku, product_name, quantity)
VALUES ('BK-01', 'Notebook', 99)
ON CONFLICT(sku) DO NOTHING
RETURNING sku, quantity;
```

Nếu conflict khiến không có INSERT, RETURNING trả 0 hàng.

### 14.2. REPLACE không phải UPSERT tương đương

SQLite có `INSERT OR REPLACE`/`REPLACE`, nhưng REPLACE có thể xóa hàng xung đột rồi chèn hàng mới theo ngữ nghĩa riêng. Điều này có thể ảnh hưởng:

- Foreign key.
- Trigger.
- Rowid/identity.
- Default và cột không được nêu trong INSERT.
- Audit và quan hệ phụ thuộc.

Khi muốn UPDATE hàng hiện có, ưu tiên UPSERT `ON CONFLICT DO UPDATE` thay vì xem REPLACE như một cách viết ngắn tương đương.

### 14.3. RETURNING của SQLite có giới hạn

RETURNING trả dữ liệu về ứng dụng, không phải một subquery tổng quát để dùng trực tiếp như CTE nguồn trong cùng statement. Thứ tự các hàng RETURNING không được bảo đảm. SQLite cũng có các giới hạn về việc sử dụng RETURNING trong trigger và với một số kiểu statement.

Ứng dụng không nên phụ thuộc vào thứ tự trả về; nếu cần thứ tự, truy vấn lại với ORDER BY theo khóa phù hợp.

---

## 15. RETURNING/OUTPUT và dữ liệu được trigger thay đổi

Một hàng có thể bị trigger hoặc DEFAULT tác động trong lúc DML chạy. Kết quả RETURNING/OUTPUT phụ thuộc ngữ nghĩa của từng DBMS:

- PostgreSQL RETURNING thường phản ánh hàng sau khi trigger BEFORE đã biến đổi dữ liệu; trigger AFTER có thể thực hiện thêm thao tác phụ.
- SQLite RETURNING có các giới hạn và không phản ánh mọi thay đổi gián tiếp do trigger thực hiện như thể chúng là chính hàng được statement gốc trả về.
- SQL Server OUTPUT lấy hình ảnh inserted/deleted theo ngữ nghĩa của statement và có các giới hạn liên quan trigger trên bảng đích.
- Oracle RETURNING INTO nhận các cột được chỉ định từ DML; cần xét loại trigger và loại statement.
- MySQL không có RETURNING tổng quát trong dòng MySQL 8.0/8.4; thường query lại hoặc dùng cơ chế ID riêng.

Đừng suy ra rằng kết quả RETURNING/OUTPUT luôn là ảnh chụp toàn bộ trạng thái cuối cùng của mọi bảng bị trigger thay đổi. Nếu cần xác nhận dữ liệu phụ thuộc, phải query rõ hoặc thiết kế API trả về riêng.

---

## 16. UPSERT, version và chống ghi đè dữ liệu cũ

Một hệ thống đồng bộ thường nhận bản ghi từ nhiều nguồn hoặc message queue. Cùng một khóa có thể đến nhiều lần, thậm chí đến sai thứ tự.

Ví dụ:

```text
external_id = X
version 10 arrives
version 9 arrives later
```

Nếu UPSERT luôn replace, version 9 có thể ghi đè version 10.

### 16.1. PostgreSQL có điều kiện version

```sql
INSERT INTO synced_records (
    external_id, payload, source_version
)
VALUES (
    'X', '{"state":"new"}', 10
)
ON CONFLICT (external_id)
DO UPDATE SET
    payload = EXCLUDED.payload,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > synced_records.source_version
RETURNING external_id, source_version;
```

Nếu incoming version nhỏ hơn hoặc bằng hiện tại, không update và không có hàng trong RETURNING.

### 16.2. Compare-and-set

Một cách khác là cập nhật khi version hiện tại khớp version mà client đọc:

```sql
UPDATE documents
SET payload = :new_payload,
    version = version + 1
WHERE document_id = :id
  AND version = :expected_version;
```

Nếu affected rows = 0, có thể dữ liệu đã thay đổi hoặc không tồn tại. Ứng dụng cần phân biệt hai trường hợp bằng query hoặc API phù hợp.

### 16.3. Idempotency key

Với request thanh toán hoặc sự kiện có thể retry, dùng idempotency key unique để cùng một request không tạo hiệu ứng lặp. UPSERT một trạng thái theo khóa là một phần của thiết kế, nhưng không tự giải quyết mọi side effect ngoài database.

---

## 17. UPSERT nhiều hàng và source deduplication

Một batch có thể chứa:

```text
BK-01, quantity=10
BK-02, quantity=5
BK-01, quantity=12
```

Hai hàng source cùng SKU BK-01. Các hệ có thể xử lý khác nhau hoặc báo lỗi tùy câu lệnh. Không nên dựa vào thứ tự input để đoán hàng nào thắng.

Trước khi UPSERT/MERGE, quyết định chính sách:

- Chọn bản mới nhất theo timestamp/sequence.
- Tổng hợp quantity nếu mỗi hàng là delta.
- Từ chối batch có khóa trùng.
- Xử lý từng event theo thứ tự đã định.

Ví dụ PostgreSQL chọn bản mới nhất:

```sql
WITH source_dedup AS (
    SELECT DISTINCT ON (sku)
        sku, product_name, quantity, received_at
    FROM incoming_inventory
    ORDER BY sku, received_at DESC, source_event_id DESC
)
INSERT INTO inventory (sku, product_name, quantity)
SELECT sku, product_name, quantity
FROM source_dedup
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    quantity = EXCLUDED.quantity;
```

Tie-breaker `source_event_id` làm thứ tự lựa chọn ổn định khi received_at bằng nhau. Cần khóa nghiệp vụ và tiêu chí dedup phù hợp với nguồn dữ liệu thực tế.

### PostgreSQL MERGE và SQL Server/Oracle MERGE

Các hệ có thể báo lỗi khi nhiều hàng source cùng match một hàng target. Deduplicate source trước MERGE là nguyên tắc an toàn và dễ dự đoán.

---

## 18. UPSERT không thay thế transaction design

Một câu UPSERT đơn lẻ thường nguyên tử theo statement, nhưng một quy trình có thể gồm:

1. Ghi trạng thái đơn hàng.
2. Giảm tồn kho.
3. Ghi payment record.
4. Tạo outbox event.

Nếu mỗi bước là một câu riêng, cần transaction bao quanh để bảo đảm tất cả cùng thành công hoặc rollback theo yêu cầu.

### 18.1. Không phát event ngoài database trước COMMIT

Nếu OUTPUT/RETURNING đã trả một hàng nhưng transaction sau đó rollback, ứng dụng không nên đã gửi email hoặc gọi API bên ngoài dựa trên hàng đó.

Một thiết kế transactional outbox:

```text
BEGIN
  UPSERT business row
  INSERT outbox event
COMMIT
        │
        ▼
Worker đọc event đã commit
        │
        ▼
Gửi message / gọi service
        │
        ▼
Đánh dấu event đã xử lý
```

Outbox row được ghi cùng transaction với dữ liệu nghiệp vụ. Worker chỉ đọc event đã commit và có retry/idempotency.

### 18.2. RETURNING/OUTPUT không phải commit hook

Nó báo kết quả statement, không khẳng định transaction đã commit thành công. Chỉ thực hiện side effect ngoài database sau khi transaction commit được xác nhận.

---

## 19. So sánh cú pháp tổng hợp

| Hệ | Insert-if-new/update-if-exists | No-op on conflict | Trả hàng |
| --- | --- | --- | --- |
| PostgreSQL | ON CONFLICT DO UPDATE | DO NOTHING | RETURNING |
| MySQL | ON DUPLICATE KEY UPDATE | Không có nhánh DO NOTHING riêng; có thể thiết kế update không đổi nhưng cần hiểu affected rows | Query lại/ID technique; không có DML RETURNING tổng quát |
| SQL Server | MERGE hoặc UPDATE/INSERT transaction | WHEN MATCHED/NOT MATCHED với điều kiện phù hợp | OUTPUT |
| Oracle | MERGE | Bỏ qua nhánh không cần bằng điều kiện/nhánh phù hợp | SQL%ROWCOUNT; RETURNING INTO cho DML riêng, không phải MERGE |
| SQLite | ON CONFLICT DO UPDATE | DO NOTHING | RETURNING |

### Tên hàng đề xuất

| DBMS | Cách tham chiếu dữ liệu đầu vào trong nhánh UPDATE |
| --- | --- |
| PostgreSQL | `EXCLUDED.column` |
| MySQL | Row alias sau VALUES, ví dụ `incoming.column`; VALUES(column) cũ đã deprecated trong MySQL 8.0.20 |
| SQL Server MERGE | Alias source, ví dụ `source.column` |
| Oracle MERGE | Alias source, ví dụ `s.column` |
| SQLite | `excluded.column` |

Không dùng một từ khóa như EXCLUDED cho mọi hệ.

---

## 20. Quy tắc lựa chọn

| Yêu cầu | Lựa chọn thường hợp lý |
| --- | --- |
| INSERT theo unique key, nếu trùng thì UPDATE | PostgreSQL ON CONFLICT; MySQL ON DUPLICATE KEY; SQLite ON CONFLICT |
| Đối chiếu source relation với target, nhiều nhánh UPDATE/INSERT/DELETE | MERGE nếu DBMS hỗ trợ và semantics phù hợp |
| SQL Server cần trả action và old/new values | OUTPUT, có thể kết hợp MERGE hoặc DML riêng |
| PostgreSQL cần trả hàng sau UPSERT | RETURNING |
| SQLite cần lấy hàng được ghi | RETURNING từ 3.35.0 |
| MySQL cần lấy ID mới | AUTO_INCREMENT/LAST_INSERT_ID theo thiết kế, hoặc query lại theo unique key |
| Oracle cần tổng số hàng sau MERGE | SQL%ROWCOUNT |
| Oracle cần giá trị từ INSERT/UPDATE/DELETE riêng | RETURNING INTO khi loại DML hỗ trợ |
| Ghi sự kiện sau commit | Transactional outbox |
| Chống ghi đè phiên bản cũ | Điều kiện version trong nhánh update |
| Xử lý batch có khóa trùng | Deduplicate hoặc reject source trước |

---

## 21. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| SELECT trước rồi INSERT mà không transaction/lock | Race condition | UPSERT nguyên tử hoặc khóa/range lock phù hợp |
| Không có UNIQUE constraint | Hàng trùng vẫn có thể xuất hiện | Tạo PK/UNIQUE đúng khóa nghiệp vụ |
| Chọn nhầm conflict key | Cập nhật nhầm đối tượng | Xác định identity và unique index |
| PostgreSQL dùng EXCLUDED ở MySQL | Sai phương ngữ | MySQL dùng alias hàng incoming |
| Dùng VALUES(column) trong MySQL mới | Deprecated | Dùng row alias theo phiên bản |
| Nghĩ MySQL có conflict target như PostgreSQL | Không kiểm soát được unique key xung đột như mong muốn | Thiết kế unique indexes và kiểm tra mọi conflict |
| Dùng MERGE với source trùng khóa | Nhiều source match cùng target, lỗi hoặc kết quả không mong muốn | Deduplicate source |
| Nghĩ PostgreSQL MERGE luôn thay ON CONFLICT | Khác concurrency/unique-conflict semantics | Chọn ON CONFLICT cho atomic unique-key UPSERT đơn giản |
| Nghĩ SQL Server MERGE luôn an toàn không cần lock | Race và lỗi unique dưới concurrency | Unique constraint, HOLDLOCK/transaction hoặc UPDATE-INSERT pattern có lock |
| Dùng OUTPUT làm bằng chứng commit | Side effect có thể phát dù transaction rollback | Chờ commit; dùng outbox |
| Nghĩ Oracle MERGE có RETURNING | Sai cú pháp/khả năng | SQL%ROWCOUNT, audit/query lại hoặc DML riêng RETURNING INTO |
| Dùng SQL%ROWCOUNT để biết từng action Oracle MERGE | Chỉ có tổng số hàng | Thiết kế audit/staging/nhánh DML riêng |
| Nghĩ DO NOTHING RETURNING trả hàng cũ | Không có hàng được insert nên trả 0 hàng | SELECT theo unique key nếu cần hàng hiện tại |
| Dùng SQLite REPLACE thay UPSERT UPDATE | Có thể xóa rồi chèn, ảnh hưởng FK/trigger/rowid | ON CONFLICT DO UPDATE |
| Dựa vào affected rows MySQL để phân biệt tuyệt đối | Driver flag và no-op update thay đổi số báo | Dùng logic ứng dụng/SELECT hoặc contract driver rõ |
| UPDATE version không có điều kiện | Bản cũ ghi đè bản mới | So sánh version/sequence |
| UPSERT batch không deduplicate | Một khóa có nhiều bản trong cùng source | Chọn latest/aggregate/reject |
| Không xử lý danh sách source rỗng | Query sai hoặc xóa nhầm dữ liệu | Định nghĩa semantics empty input |
| Trigger làm thay đổi hàng nhưng không hiểu RETURNING | Trả dữ liệu không như kỳ vọng | Kiểm tra timing/DBMS và query rõ |
| Phát email từ OUTPUT/RETURNING trước commit | Gửi thông báo cho thay đổi rollback | Transactional outbox |
| Chỉ test một client | Race condition chưa lộ | Test nhiều session đồng thời |
| Không kiểm tra version engine | Cú pháp RETURNING/MERGE không được hỗ trợ | Pin/test DBMS version |

---

## 22. Bài tập thực hành

Các bài 1–8 dùng PostgreSQL và bảng lab ở mục 4. Các bài còn lại kiểm tra khả năng chuyển phương ngữ. Hãy xác định hành động và số hàng RETURNING/OUTPUT trước khi xem lời giải.

### Bài 1. PostgreSQL UPSERT

Bảng lab_inventory_406 đã có BK-01 quantity 10. Viết INSERT quantity 25, ON CONFLICT sku DO UPDATE, trả sku và quantity.

### Bài 2. EXCLUDED

Trong PostgreSQL DO UPDATE, EXCLUDED.quantity và lab_inventory_406.quantity đại diện cho hai giá trị nào?

### Bài 3. DO NOTHING RETURNING

Nếu BK-01 đã tồn tại và câu INSERT dùng ON CONFLICT DO NOTHING RETURNING sku, câu lệnh trả mấy hàng? Vì sao không trả hàng cũ?

### Bài 4. Version gate

Viết điều kiện PostgreSQL chỉ update khi EXCLUDED.version lớn hơn version hiện tại. Nếu điều kiện false, RETURNING có hàng không?

### Bài 5. Increment atomically

Viết PostgreSQL UPSERT cộng quantity incoming vào quantity hiện tại. Vì sao cách này tốt hơn SELECT quantity rồi cộng ở ứng dụng?

### Bài 6. MERGE source duplicate

Một source có hai hàng cùng sku BK-01 và target có một hàng BK-01. Vì sao cần deduplicate trước MERGE? Nêu một tiêu chí lựa chọn bản ghi.

### Bài 7. PostgreSQL version

PostgreSQL có MERGE từ phiên bản nào? MERGE RETURNING có từ phiên bản nào? Vì sao phải kiểm tra version target?

### Bài 8. MERGE hay ON CONFLICT

Một API chỉ cần insert theo unique key, nếu trùng thì update một số cột. Nên chọn cơ chế nào trong PostgreSQL và vì sao?

### Bài 9. MySQL alias

Viết MySQL 8.0.19+ INSERT ... ON DUPLICATE KEY UPDATE dùng row alias incoming để cập nhật quantity. Vì sao nên tránh VALUES(quantity) trong MySQL 8.0.20+?

### Bài 10. MySQL affected rows

Nêu các giá trị affected rows thường gặp khi INSERT, UPDATE có thay đổi và UPDATE không thay đổi trong ON DUPLICATE KEY UPDATE. Yếu tố client nào có thể làm thay đổi cách báo no-op?

### Bài 11. MySQL nhiều unique key

Một bảng có UNIQUE(email) và UNIQUE(external_id). Vì sao cần thận trọng khi dùng ON DUPLICATE KEY UPDATE? Nó có conflict target chỉ định rõ như PostgreSQL không?

### Bài 12. SQL Server OUTPUT

Viết UPDATE tăng quantity 5 và OUTPUT sku, quantity cũ từ deleted, quantity mới từ inserted.

### Bài 13. SQL Server MERGE

Viết MERGE với source gồm BK-01 quantity 20; nếu match thì UPDATE, nếu chưa match thì INSERT, và OUTPUT $action.

### Bài 14. SQL Server source duplicate

Điều gì xảy ra nếu nhiều hàng source match cùng một hàng target để UPDATE trong MERGE? Cần làm gì trước đó?

### Bài 15. SQL Server concurrency

Giải thích mục đích HOLDLOCK trong MERGE UPSERT và vì sao unique constraint vẫn bắt buộc.

### Bài 16. SQL Server OUTPUT rollback

Vì sao ứng dụng không nên gửi email ngay khi nhận một hàng OUTPUT từ statement trong transaction?

### Bài 17. SQL Server UPDATE-INSERT

Nêu vai trò UPDLOCK, SERIALIZABLE, @@ROWCOUNT và unique index trong mẫu UPDATE rồi INSERT.

### Bài 18. Oracle MERGE

Viết Oracle MERGE cập nhật quantity nếu match và insert nếu not match.

### Bài 19. Oracle RETURNING

Oracle MERGE có RETURNING INTO như INSERT/UPDATE riêng không? Nếu chỉ cần tổng số hàng MERGE tác động, dùng thuộc tính nào?

### Bài 20. Oracle ORA-30926

Nguyên nhân thường gặp của ORA-30926 trong MERGE và cách xử lý source?

### Bài 21. SQLite UPSERT

Viết SQLite INSERT ON CONFLICT(sku) DO UPDATE dùng excluded.quantity và RETURNING sku, quantity. Nêu version tối thiểu cho RETURNING.

### Bài 22. SQLite REPLACE

Vì sao REPLACE không tương đương ON CONFLICT DO UPDATE? Nêu ít nhất hai tác động có thể có.

### Bài 23. MySQL lấy ID

Mô tả kỹ thuật LAST_INSERT_ID(id) trong nhánh duplicate update và một giới hạn của nó.

### Bài 24. Batch deduplication

Một batch có BK-01 xuất hiện hai lần với timestamp khác nhau. Nêu hai chính sách hợp lệ và vì sao không dựa vào thứ tự input ngẫu nhiên.

### Bài 25. Outbox

Thiết kế flow UPSERT một order và ghi outbox event trong cùng transaction. Worker nên gửi event ở thời điểm nào?

### Bài 26. So sánh kết quả trả hàng

Lập bảng nêu PostgreSQL RETURNING, SQL Server OUTPUT, Oracle SQL%ROWCOUNT/RETURNING INTO và MySQL query lại/ID technique trả được loại thông tin gì.

### Bài 27. Concurrency test

Đề xuất một bài test hai session cùng UPSERT một SKU chưa tồn tại. Những invariant và kết quả cần kiểm tra là gì?

---

## 23. Gợi ý lời giải

### Bài 1

```sql
INSERT INTO lab_inventory_406 (sku, product_name, quantity)
VALUES ('BK-01', 'Notebook', 25)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity
RETURNING sku, quantity;
```

Nếu BK-01 tồn tại, trả một hàng với quantity 25.

### Bài 2

`EXCLUDED.quantity` là giá trị từ hàng INSERT đề xuất nhưng gặp conflict; `lab_inventory_406.quantity` là giá trị hiện tại trong hàng đích.

### Bài 3

Trả **0 hàng**. DO NOTHING không INSERT và RETURNING không tự đọc hàng đang tồn tại.

### Bài 4

```sql
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    version = EXCLUDED.version
WHERE EXCLUDED.version > lab_inventory_406.version
RETURNING sku, version;
```

Nếu điều kiện false, hàng không UPDATE và không xuất hiện trong RETURNING.

### Bài 5

```sql
INSERT INTO lab_inventory_406 (sku, product_name, quantity)
VALUES ('BK-01', 'Notebook', 5)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = lab_inventory_406.quantity + EXCLUDED.quantity
RETURNING sku, quantity;
```

Phép cộng diễn ra trong database dưới cơ chế khóa của statement, tránh read-modify-write ở client có thể ghi đè thay đổi đồng thời.

### Bài 6

Nhiều source row có thể match cùng target row, làm MERGE báo cardinality/unstable source hoặc không có kết quả xác định theo mong muốn. Deduplicate theo khóa, ví dụ chọn received_at mới nhất rồi tie-break bằng event ID.

### Bài 7

PostgreSQL MERGE từ **v15**; MERGE RETURNING từ **v17**. Target version quyết định parser/feature có hỗ trợ; code chạy trên v15/v16 không thể giả định có RETURNING của MERGE.

### Bài 8

Chọn **INSERT ... ON CONFLICT DO UPDATE**. Đây là bài toán UPSERT theo unique key, cú pháp trực tiếp và cơ chế xử lý concurrent unique conflict được thiết kế cho mục đích đó. MERGE dành cho đối chiếu source-target với nhiều nhánh hơn.

### Bài 9

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('BK-01', 25) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity;
```

VALUES(column) deprecated từ MySQL 8.0.20; row alias là cú pháp hiện đại để tham chiếu hàng incoming.

### Bài 10

Thông thường: 1 khi insert, 2 khi update có thay đổi, 0 khi update không thay đổi. Client flag CLIENT_FOUND_ROWS có thể làm trường hợp no-op được báo là 1. Driver và cấu hình phải được xét.

### Bài 11

MySQL kích hoạt duplicate branch khi xung đột PRIMARY KEY hoặc UNIQUE KEY; không có conflict target chỉ định như PostgreSQL. Nếu nhiều unique key có thể trỏ tới các hàng khác nhau, hành vi có thể không phù hợp ý định. Thiết kế key rõ và tránh pattern mơ hồ.

### Bài 12

```sql
UPDATE dbo.Inventory
SET quantity = quantity + 5
OUTPUT
    inserted.sku,
    deleted.quantity AS old_quantity,
    inserted.quantity AS new_quantity
WHERE sku = N'BK-01';
```

### Bài 13

```sql
MERGE dbo.Inventory AS target
USING (VALUES (N'BK-01', 20))
    AS source(sku, quantity)
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET quantity = source.quantity
WHEN NOT MATCHED BY TARGET THEN
    INSERT (sku, quantity)
    VALUES (source.sku, source.quantity)
OUTPUT $action, inserted.sku, deleted.quantity, inserted.quantity;
```

Trong bảng thật cần có các cột khác như product_name theo schema.

### Bài 14

SQL Server có thể báo lỗi nếu nhiều hàng source cùng cố UPDATE một target row trong cùng MERGE. Deduplicate/aggregate source để mỗi target key có tối đa một source row.

### Bài 15

HOLDLOCK áp dụng semantics SERIALIZABLE cho target trong ngữ cảnh; giúp bảo vệ khoảng khóa khi chưa tồn tại row. Unique constraint vẫn là bảo vệ dữ liệu cuối cùng và hỗ trợ xác định identity; lock không thay constraint.

### Bài 16

OUTPUT có thể phát hàng trước khi transaction cuối cùng commit; statement/transaction có thể rollback sau đó. Email là side effect ngoài database không tự rollback. Ghi outbox trong transaction, gửi sau commit.

### Bài 17

UPDLOCK lấy update lock khi tìm row; SERIALIZABLE giữ range lock để bảo vệ khoảng chưa có key; @@ROWCOUNT xác định UPDATE có hàng hay không; unique index ngăn duplicate key cuối cùng.

### Bài 18

```sql
MERGE INTO inventory t
USING (
    SELECT 'BK-01' AS sku, 20 AS quantity
    FROM dual
) s
ON (t.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET t.quantity = s.quantity
WHEN NOT MATCHED THEN
    INSERT (sku, quantity)
    VALUES (s.sku, s.quantity);
```

### Bài 19

Oracle MERGE không có RETURNING INTO theo hàng như một số DML riêng. Dùng `SQL%ROWCOUNT` để lấy tổng số hàng bị tác động; muốn từng hàng cần audit/query/staging hoặc thiết kế DML riêng.

### Bài 20

Một hàng target bị nhiều source rows match để update, khiến Oracle không có một tập source ổn định; có thể báo ORA-30926. Deduplicate/aggregate source để mỗi khóa target chỉ match một hàng.

### Bài 21

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('BK-01', 25)
ON CONFLICT(sku)
DO UPDATE SET quantity = excluded.quantity
RETURNING sku, quantity;
```

SQLite RETURNING từ **3.35.0**; UPSERT có từ 3.24.0.

### Bài 22

REPLACE có thể xóa hàng xung đột rồi insert hàng mới. Điều này có thể tác động foreign key, trigger, rowid/identity và default/cột không được cung cấp. ON CONFLICT DO UPDATE cập nhật hàng hiện có theo nhánh UPDATE.

### Bài 23

```sql
INSERT INTO customer (external_key, display_name)
VALUES ('EXT-101', 'An') AS incoming
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    display_name = incoming.display_name;

SELECT LAST_INSERT_ID();
```

Nó đặt ID của hàng đã tồn tại vào LAST_INSERT_ID của session khi duplicate branch chạy. Cần chú ý session/connection pooling và multi-row behavior; đây không phải RETURNING mọi cột.

### Bài 24

Chọn bản ghi có timestamp mới nhất, tie-break bằng event ID; hoặc cộng quantity nếu mỗi hàng là delta. Không dựa vào thứ tự input vì batch/order có thể thay đổi giữa lần chạy và các DBMS không đảm bảo thứ tự tác động như hợp đồng nghiệp vụ.

### Bài 25

Trong một transaction: UPSERT order; INSERT outbox event có event ID/idempotency key; COMMIT. Worker chỉ đọc event đã commit, gửi message, retry an toàn và đánh dấu processed. Không gửi trước commit.

### Bài 26

| Cơ chế | Thông tin |
| --- | --- |
| PostgreSQL RETURNING | Các cột được chọn của hàng INSERT/UPDATE/DELETE; MERGE RETURNING từ v17 |
| SQL Server OUTPUT | Hình ảnh inserted/deleted, $action cho MERGE |
| Oracle SQL%ROWCOUNT | Tổng hàng tác động; RETURNING INTO cho một số DML riêng |
| MySQL | Affected rows và ID technique/query lại; không có DML RETURNING tổng quát trong MySQL 8.0/8.4 |

### Bài 27

Chạy hai connection cùng UPSERT một SKU chưa tồn tại, đồng thời hoặc dùng barrier. Kiểm tra:
- Cuối cùng chỉ có một hàng theo SKU (unique constraint).
- Không mất increment nếu chính sách là cộng delta.
- Không ghi đè version mới bằng version cũ.
- Transaction thành công/lỗi được xử lý và retry đúng.
- Không phát hai side effect ngoài database cho cùng idempotency key.
- Quan sát deadlock/blocking và thời gian chờ.

---

## 24. Quy trình triển khai UPSERT/MERGE an toàn

Trước khi phát hành, xác định:

1. **Identity:** unique key nào xác định một hàng nghiệp vụ?
2. **Source cardinality:** mỗi key có tối đa một hàng nguồn hay cần deduplicate?
3. **Update policy:** replace, increment, update-if-newer, ignore hay compare-and-set?
4. **NULL semantics:** NULL có nghĩa xóa, bỏ qua hay lỗi?
5. **Atomicity:** thao tác có cần một statement hay transaction nhiều bước?
6. **Concurrency:** hai session cùng ghi một key sẽ được xử lý thế nào?
7. **Returned data:** cần key, giá trị mới, giá trị cũ, action hay chỉ row count?
8. **Version:** có chống ghi đè dữ liệu cũ hoặc event lặp không?
9. **Side effects:** có cần outbox để gửi sau commit không?
10. **DBMS/version:** cú pháp và feature có tồn tại trên engine thực tế không?
11. **Performance:** source có được deduplicate/index, lock có gây contention không?
12. **Observability:** log action, row count, conflict/retry và lỗi ra sao?

## 25. Tổng kết

UPSERT, MERGE, RETURNING và OUTPUT giải quyết các phần khác nhau của một luồng ghi dữ liệu:

- **UPSERT** phù hợp khi ghi theo unique key: PostgreSQL và SQLite dùng ON CONFLICT; MySQL dùng ON DUPLICATE KEY UPDATE.
- **MERGE** phù hợp khi đối chiếu source relation với target và có nhiều nhánh INSERT/UPDATE/DELETE. PostgreSQL có từ v15; SQL Server và Oracle có cú pháp riêng.
- **RETURNING** trả các cột của hàng được tác động ở PostgreSQL và SQLite; MySQL không có DML RETURNING tổng quát trong các dòng được nêu.
- **OUTPUT** của SQL Server có thể trả action và hình ảnh inserted/deleted; Oracle thường dùng SQL%ROWCOUNT hoặc RETURNING INTO cho DML riêng.
- **Unique constraint, source deduplication, transaction và concurrency control** vẫn là nền tảng để bảo vệ dữ liệu.
- **Không coi RETURNING/OUTPUT là bằng chứng COMMIT**; side effect ngoài database nên được phát qua transactional outbox sau commit.

Khi chuyển SQL giữa các hệ, hãy giữ nguyên hợp đồng nghiệp vụ trước: khóa nào định danh hàng, xung đột cập nhật ra sao, batch trùng được xử lý thế nào và ứng dụng cần nhận kết quả gì. Sau đó mới chọn cú pháp UPSERT/MERGE và RETURNING/OUTPUT phù hợp với DBMS cùng phiên bản triển khai.
