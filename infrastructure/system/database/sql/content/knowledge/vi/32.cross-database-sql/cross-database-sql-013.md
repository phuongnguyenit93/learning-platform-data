# Ma trận đối chiếu PostgreSQL, MySQL, SQL Server, Oracle và SQLite

SQL có một nền tảng chung, nhưng mỗi hệ quản trị cơ sở dữ liệu (DBMS) bổ sung kiểu dữ liệu, cú pháp, hàm, cơ chế transaction và cách tối ưu riêng. Một câu SELECT đơn giản thường có thể chuyển giữa các hệ thống với ít thay đổi; một migration tạo khóa tự tăng, một lệnh UPSERT, một truy vấn phân trang hoặc một thủ tục lưu trữ thì có thể cần viết lại đáng kể.

Bài này xây dựng ma trận đối chiếu năm hệ quản trị thường gặp:

- **PostgreSQL**: hệ quản trị quan hệ mã nguồn mở, có nhiều kiểu dữ liệu và extension.
- **MySQL**: hệ quản trị quan hệ phổ biến trong ứng dụng web; cần chú ý storage engine, đặc biệt InnoDB.
- **Microsoft SQL Server**: hệ quản trị của Microsoft, sử dụng T-SQL và các kiểu dữ liệu/hàm riêng.
- **Oracle Database**: hệ quản trị doanh nghiệp với SQL và PL/SQL, nhiều cơ chế quản trị chuyên sâu.
- **SQLite**: cơ sở dữ liệu nhúng, lưu trong một tệp, có mô hình triển khai và concurrency khác server DBMS.

Mục tiêu không phải học thuộc năm bộ cú pháp tách rời. Mục tiêu là biết **điểm nào tương đồng, điểm nào khác, phần nào có thể viết portable, và phần nào cần adapter hoặc migration riêng**.

> Một câu SQL chạy được trên năm hệ quản trị chưa chắc có cùng semantics, độ chính xác, khả năng transaction hoặc hiệu năng trên cả năm. Khi đối chiếu, hãy kiểm tra cả **kết quả lẫn hành vi**.

## 1. Bản đồ tổng quan

| Chủ đề | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Ngôn ngữ mở rộng | PL/pgSQL và ngôn ngữ khác | SQL/PSM gần với stored program syntax riêng | T-SQL | PL/SQL | Không có stored procedure native |
| Khóa tự tăng | IDENTITY, sequence | AUTO_INCREMENT | IDENTITY | IDENTITY hoặc sequence | INTEGER PRIMARY KEY / rowid |
| Boolean | BOOLEAN | BOOLEAN là alias của TINYINT(1) | BIT | BOOLEAN trong SQL từ 23c/23ai; bản cũ dùng kiểu thay thế | Không có storage class BOOLEAN riêng |
| Nối chuỗi | ||, concat | CONCAT; || thường là OR trừ SQL mode | +, CONCAT | ||, CONCAT | || |
| Phân trang | LIMIT/OFFSET, FETCH | LIMIT/OFFSET | ORDER BY + OFFSET/FETCH, TOP | OFFSET/FETCH từ 12c; ROWNUM ở bản cũ | LIMIT/OFFSET |
| UPSERT | ON CONFLICT | ON DUPLICATE KEY UPDATE | MERGE hoặc mẫu UPDATE/INSERT | MERGE | ON CONFLICT từ 3.24 |
| Trả dòng vừa ghi | RETURNING | Không có RETURNING DML tổng quát như PostgreSQL | OUTPUT | RETURNING INTO | RETURNING từ 3.35 |
| JSON | json, jsonb | JSON native | JSON thường lưu trong kiểu chuỗi; hàm JSON | JSON; native JSON từ 21c | JSON functions; JSONB nội bộ từ 3.45 |
| Transaction | Hỗ trợ mạnh; nhiều DDL transactional | InnoDB; nhiều DDL implicit commit | Transaction explicit/implicit | DDL thường implicit commit | Transaction; một writer tại một thời điểm |
| Stored procedure | Có | Có | Có | Có | Không có native |
| Index nổi bật | B-tree, GIN, GiST, BRIN | B-tree, FULLTEXT, SPATIAL | Clustered/nonclustered, columnstore, filtered | B-tree, bitmap, function-based, domain | B-tree, partial, expression |
| Định danh có quote | "name" | \`name\` | [name] hoặc "name" khi cấu hình phù hợp | "name" | "name", cùng một số dạng tương thích |

Các ô trong bảng là định hướng. Phiên bản, edition, extension, cấu hình và storage engine có thể làm thay đổi khả năng cụ thể.

## 2. Phiên bản và phạm vi cần xác định trước

Không nên nói “Oracle hỗ trợ kiểu này” hoặc “MySQL có cú pháp kia” mà bỏ qua phiên bản.

Một số mốc đáng nhớ:

| Hệ quản trị | Mốc cần chú ý |
|---|---|
| PostgreSQL | Tính năng thay đổi theo major version; extension có phiên bản riêng |
| MySQL | Ví dụ trong bài hướng tới MySQL 8.0/8.4; một số cú pháp alias UPSERT cần 8.0.19+ |
| SQL Server | T-SQL và tính năng phụ thuộc phiên bản/compatibility level |
| Oracle | IDENTITY từ 12c; native SQL BOOLEAN và native JSON phụ thuộc thế hệ mới hơn |
| SQLite | UPSERT từ 3.24; generated columns từ 3.31; RETURNING từ 3.35; JSONB từ 3.45 |

Trước khi viết SQL production, ghi nhận tối thiểu:

- DBMS và phiên bản server.
- Phiên bản driver/ORM.
- SQL mode, collation và timezone.
- Storage engine của MySQL.
- Compatibility level của SQL Server.
- Extension được cài trên PostgreSQL/SQLite.
- Edition và feature availability của Oracle.

Không dùng phiên bản client thay cho phiên bản server khi kiểm tra tính năng.

## 3. Kiểu dữ liệu và quy tắc lưu trữ

### 3.1. Số nguyên và số thập phân

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Số nguyên nhỏ | SMALLINT | SMALLINT | SMALLINT | NUMBER(p,0) | INTEGER storage class |
| Số nguyên phổ biến | INTEGER | INT | INT | NUMBER(p,0) | INTEGER |
| Số nguyên lớn | BIGINT | BIGINT | BIGINT | NUMBER(19,0) thường dùng | INTEGER 64-bit |
| Số thập phân chính xác | NUMERIC/DECIMAL | DECIMAL | DECIMAL/NUMERIC | NUMBER(p,s) | NUMERIC affinity, lưu trữ linh hoạt |
| Số gần đúng | REAL/DOUBLE PRECISION | FLOAT/DOUBLE | REAL/FLOAT | BINARY_FLOAT/BINARY_DOUBLE | REAL |

**Tiền tệ nên dùng số thập phân chính xác**, không dùng floating point nếu yêu cầu kế toán cần phép tính thập phân chính xác. SQLite có type affinity và storage class linh hoạt; khai báo DECIMAL không tạo cùng bảo đảm lưu trữ cố định như DECIMAL của các server DBMS.

Ví dụ PostgreSQL:

```sql
CREATE TABLE invoice_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity NUMERIC(12, 3) NOT NULL,
    unit_price NUMERIC(18, 2) NOT NULL
);
```

Trong SQLite, nếu cần tiền chính xác, có thể cân nhắc lưu **đơn vị nhỏ nhất dưới dạng INTEGER** (ví dụ đồng hoặc cent) và quy định rõ scale ở tầng ứng dụng, thay vì kỳ vọng DECIMAL affinity hoạt động như một decimal engine.

### 3.2. Kiểu chuỗi

| DBMS | Chuỗi biến độ dài | Chuỗi Unicode/đa byte | Ghi chú |
|---|---|---|---|
| PostgreSQL | TEXT, VARCHAR(n) | Database encoding, thường UTF-8 | TEXT không cần giới hạn n nếu nghiệp vụ không yêu cầu |
| MySQL | VARCHAR(n), TEXT | Charset/collation như utf8mb4 | Chọn charset/collation rõ ràng |
| SQL Server | VARCHAR(n), NVARCHAR(n) | NVARCHAR dùng Unicode | VARCHAR hỗ trợ UTF-8 khi collation/code page phù hợp |
| Oracle | VARCHAR2(n), CLOB | Charset database/national charset | Quy tắc n có thể là BYTE hoặc CHAR |
| SQLite | TEXT | UTF-8/UTF-16 nội bộ theo cấu hình | Kiểu khai báo không áp dụng giới hạn độ dài như server DBMS |

Không mặc định VARCHAR(100) có cùng ý nghĩa về byte/ký tự trên mọi hệ. Oracle có thể khai báo semantics BYTE hoặc CHAR; SQL Server NVARCHAR(n) dùng n đơn vị UTF-16 code unit; MySQL phụ thuộc character set; SQLite không cưỡng chế độ dài VARCHAR(n) theo cách server DBMS thường làm.

### 3.3. Boolean

PostgreSQL có kiểu BOOLEAN thật:

```sql
CREATE TABLE feature_flags (
    flag_name TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE
);
```

MySQL chấp nhận BOOLEAN/BOOL như alias của TINYINT(1); đây không phải một kiểu Boolean storage độc lập tương tự PostgreSQL.

SQL Server dùng BIT cho giá trị 0/1/NULL.

Oracle có kiểu BOOLEAN trong PL/SQL từ lâu, nhưng cột SQL BOOLEAN chỉ có ở các thế hệ mới như Oracle Database 23c/23ai. Với hệ cũ như 19c, thường dùng NUMBER(1) hoặc CHAR(1) cùng CHECK constraint.

SQLite không có storage class BOOLEAN riêng; thường lưu 0/1 trong INTEGER. Có thể viết:

```sql
CREATE TABLE settings (
    setting_name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1))
);
```

Khi chuyển hệ, kiểm tra cả giá trị NULL, default và cách driver ánh xạ Boolean.

### 3.4. Ngày và thời gian

| DBMS | Kiểu phổ biến | Đặc điểm |
|---|---|---|
| PostgreSQL | DATE, TIME, TIMESTAMP, TIMESTAMPTZ | TIMESTAMPTZ biểu diễn thời điểm tuyệt đối; hiển thị theo timezone session |
| MySQL | DATE, TIME, DATETIME, TIMESTAMP | TIMESTAMP có chuyển đổi theo session timezone; DATETIME không tự mang timezone |
| SQL Server | DATE, TIME, DATETIME2, DATETIMEOFFSET | DATETIMEOFFSET giữ offset; DATETIME2 có độ chính xác cao |
| Oracle | DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE, LOCAL TIME ZONE | DATE có cả ngày và giờ tới giây |
| SQLite | TEXT, REAL, INTEGER | Không có kiểu date/time storage riêng; dùng quy ước và hàm date/time |

SQLite có thể lưu thời điểm dưới dạng ISO-8601 text, Julian day REAL hoặc Unix time INTEGER. Ứng dụng cần thống nhất một chuẩn lưu trữ và timezone.

Đối với hệ thống đa vùng:

- Lưu thời điểm theo UTC hoặc kiểu có semantics thời điểm rõ ràng.
- Giữ timezone IANA riêng nếu cần biết múi giờ địa phương, vì offset không chứa toàn bộ lịch sử DST.
- Không giả định mọi kiểu có tên TIMESTAMP đều có timezone.
- Test chuyển đổi khi đọc/ghi qua driver.

### 3.5. JSON

| DBMS | Cách lưu/đặc điểm |
|---|---|
| PostgreSQL | json lưu văn bản đã parse; jsonb lưu dạng nhị phân tối ưu truy vấn/index |
| MySQL | JSON native, có validation và biểu diễn nội bộ |
| SQL Server | JSON thường lưu trong NVARCHAR; dùng ISJSON, JSON_VALUE, OPENJSON và hàm liên quan |
| Oracle | Hỗ trợ JSON trong các kiểu ký tự/binary; native JSON data type ở thế hệ mới như 21c |
| SQLite | JSON functions; dữ liệu thường là TEXT, SQLite JSONB từ 3.45 là định dạng riêng |

**JSONB của PostgreSQL và JSONB của SQLite không phải định dạng nhị phân tương thích để trao đổi trực tiếp.** JSON trong SQL Server cũng không đồng nghĩa có cùng kiểu cột JSON native như PostgreSQL/MySQL.

Khi chuyển JSON, nên trao đổi bằng văn bản JSON chuẩn hoặc giao thức ứng dụng, không copy raw binary JSON giữa DBMS.

## 4. Khóa chính tự tăng và sequence

### 4.1. Cú pháp identity

PostgreSQL:

```sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL
);
```

MySQL:

```sql
CREATE TABLE customers (
    customer_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
) ENGINE = InnoDB;
```

SQL Server:

```sql
CREATE TABLE dbo.customers (
    customer_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    customer_name NVARCHAR(200) NOT NULL
);
```

Oracle 12c+:

```sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL
);
```

SQLite:

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);
```

Trong SQLite, INTEGER PRIMARY KEY thường là alias cho ROWID. Từ khóa AUTOINCREMENT có semantics riêng để ngăn tái sử dụng một số ROWID đã dùng, nhưng có overhead và không cần cho phần lớn trường hợp. AUTOINCREMENT chỉ áp dụng theo dạng khai báo INTEGER PRIMARY KEY phù hợp.

### 4.2. ALWAYS và BY DEFAULT trong PostgreSQL/Oracle

PostgreSQL:

- GENERATED ALWAYS AS IDENTITY: không cho ứng dụng tự đưa giá trị vào theo cách thông thường, trừ cú pháp override được phép.
- GENERATED BY DEFAULT AS IDENTITY: cho phép cung cấp giá trị tường minh.

Oracle có các lựa chọn identity tương tự về mục tiêu, nhưng chi tiết cú pháp/override khác. Khi import dữ liệu có ID sẵn, phải lên kế hoạch đồng bộ sequence/identity sau khi nạp.

### 4.3. Sequence riêng

PostgreSQL:

```sql
CREATE SEQUENCE order_number_seq START WITH 1000;

SELECT nextval('order_number_seq');
```

Oracle:

```sql
CREATE SEQUENCE order_number_seq START WITH 1000 INCREMENT BY 1;

SELECT order_number_seq.NEXTVAL FROM dual;
```

SQL Server có SEQUENCE object:

```sql
CREATE SEQUENCE dbo.order_number_seq
    AS BIGINT
    START WITH 1000
    INCREMENT BY 1;

SELECT NEXT VALUE FOR dbo.order_number_seq;
```

MySQL thường dùng AUTO_INCREMENT thay vì sequence object tương đương theo cách này. SQLite thường dùng INTEGER PRIMARY KEY/ROWID.

Sequence/identity không bảo đảm số liên tục. Rollback, cache, lỗi hoặc cấp ID trước khi commit có thể tạo khoảng trống. Không dùng ID tăng liên tục làm bằng chứng rằng không có giao dịch thất bại.

## 5. Nối chuỗi và xử lý NULL

### 5.1. Nối chuỗi

| DBMS | Cách thường dùng |
|---|---|
| PostgreSQL | a || b hoặc concat(a,b) |
| MySQL | CONCAT(a,b); || mặc định là logical OR trừ SQL mode đặc biệt |
| SQL Server | a + b hoặc CONCAT(a,b) |
| Oracle | a || b hoặc CONCAT(a,b) |
| SQLite | a || b |

Ví dụ PostgreSQL/Oracle/SQLite:

```sql
SELECT first_name || ' ' || last_name AS full_name
FROM people;
```

MySQL:

```sql
SELECT CONCAT(first_name, ' ', last_name) AS full_name
FROM people;
```

SQL Server:

```sql
SELECT CONCAT(first_name, ' ', last_name) AS full_name
FROM dbo.people;
```

### 5.2. NULL khi nối chuỗi

Không giả định quy tắc giống nhau:

- PostgreSQL toán tử || trả NULL nếu một toán hạng NULL; hàm concat có quy tắc riêng và bỏ qua đối số NULL.
- MySQL CONCAT trả NULL nếu có đối số NULL; CONCAT_WS có quy tắc bỏ qua giá trị NULL.
- SQL Server phép + phụ thuộc thiết lập CONCAT_NULL_YIELDS_NULL; trong các phiên bản hiện đại setting này luôn ON. CONCAT xử lý NULL như chuỗi rỗng.
- Oracle coi chuỗi rỗng là NULL trong SQL; phép nối có quy tắc đặc biệt khiến nối NULL với chuỗi thường trả chuỗi còn lại.
- SQLite toán tử || trả NULL nếu toán hạng NULL.

Nếu muốn quy tắc rõ ràng, viết tường minh:

```sql
SELECT
    COALESCE(first_name, '') || ' ' ||
    COALESCE(last_name, '') AS full_name
FROM people;
```

Đây là dạng PostgreSQL/Oracle/SQLite; MySQL và SQL Server có thể dùng CONCAT/CONCAT_WS theo semantics mong muốn. Nếu dữ liệu rỗng và NULL cần phân biệt, đừng chuẩn hóa chúng thành cùng một giá trị.

## 6. Định danh, dấu quote và chữ hoa/thường

Tên bảng/cột có thể được quote, nhưng cách viết và cách DBMS lưu tên khác nhau.

| DBMS | Cách quote phổ biến | Quy tắc tên không quote |
|---|---|---|
| PostgreSQL | "order" | Fold về chữ thường |
| MySQL | \`order\` | Tên bảng có thể phụ thuộc OS và lower_case_table_names |
| SQL Server | [order] hoặc "order" khi QUOTED_IDENTIFIER ON | Thường phụ thuộc collation |
| Oracle | "Order" | Fold về chữ hoa |
| SQLite | "order" | Không phân biệt hoa/thường trong so khớp identifier |

Ví dụ:

```sql
SELECT "customerName"
FROM customers;
```

Không nên tạo identifier có phân biệt hoa/thường bằng quoted name nếu không có nhu cầu mạnh. Tên như "CustomerName" có thể khiến mọi câu truy vấn phải quote chính xác trên PostgreSQL/Oracle.

### 6.1. Reserved words

Không đặt tên cột là ORDER, USER, GROUP, KEY hoặc một từ khóa phổ biến nếu có thể tránh. Dùng tên miền rõ ràng như order_status, user_id, group_code.

Quote identifier không thay thế allowlist trong dynamic SQL. Nếu người dùng được chọn tên cột, map từ giá trị đầu vào sang identifier cố định được phép.

### 6.2. Tên schema

PostgreSQL thường dùng schema như public; SQL Server dùng dbo; Oracle schema gắn với user; MySQL dùng database/schema gần như đồng nghĩa; SQLite có main/temp và attached database.

Không giả định mô hình phân cấp schema/database đồng nhất khi viết migration hoặc phân quyền.

## 7. Phân trang: LIMIT, OFFSET, FETCH và TOP

PostgreSQL, MySQL và SQLite hỗ trợ LIMIT/OFFSET:

```sql
SELECT product_id, product_name
FROM products
ORDER BY product_id
LIMIT 20 OFFSET 40;
```

SQL Server:

```sql
SELECT product_id, product_name
FROM dbo.products
ORDER BY product_id
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
```

SQL Server yêu cầu ORDER BY khi dùng OFFSET/FETCH.

Oracle 12c+:

```sql
SELECT product_id, product_name
FROM products
ORDER BY product_id
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
```

Oracle bản cũ thường dùng ROWNUM hoặc analytic functions để phân trang.

### 7.1. Luôn có ORDER BY ổn định

Phân trang không có ORDER BY không bảo đảm thứ tự. ORDER BY trên cột không duy nhất cũng có thể làm các dòng đổi vị trí giữa các trang khi dữ liệu thay đổi.

Nên thêm khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, product_id DESC
```

### 7.2. OFFSET lớn có thể tốn kém

Để lấy trang rất sâu, DBMS có thể phải đi qua nhiều dòng rồi bỏ qua. Với dữ liệu lớn và thứ tự ổn định, cân nhắc keyset pagination:

```sql
SELECT product_id, created_at, product_name
FROM products
WHERE
    created_at < :last_created_at
    OR (
        created_at = :last_created_at
        AND product_id < :last_product_id
    )
ORDER BY created_at DESC, product_id DESC
FETCH FIRST 20 ROWS ONLY;
```

FETCH FIRST ở ví dụ phù hợp PostgreSQL/Oracle hiện đại; thay cú pháp giới hạn dòng cho MySQL/SQLite/SQL Server. Điều kiện keyset và index mới là phần cốt lõi.

## 8. UPSERT: chèn hoặc cập nhật

UPSERT là thao tác thường gặp nhưng cú pháp khác rõ giữa DBMS.

### 8.1. PostgreSQL: ON CONFLICT

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('A-001', 'Phone Alpha', 120.00)
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price
RETURNING product_id, sku, unit_price;
```

EXCLUDED đại diện dòng đề xuất insert nhưng không được chèn vì conflict. PostgreSQL có RETURNING để lấy dòng sau thao tác.

### 8.2. MySQL: ON DUPLICATE KEY UPDATE

MySQL 8.0.19+ hỗ trợ row alias trong INSERT:

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('A-001', 'Phone Alpha', 120.00) AS incoming
ON DUPLICATE KEY UPDATE
    product_name = incoming.product_name,
    unit_price = incoming.unit_price;
```

Cú pháp cũ dùng VALUES(column) trong phần UPDATE đã bị deprecated ở MySQL 8.0.20, dù còn tồn tại trong nhiều phiên bản. Chọn cú pháp theo phiên bản mục tiêu.

MySQL conflict có thể xảy ra trên bất kỳ unique key phù hợp; cần hiểu bảng có bao nhiêu unique index và xác định đúng hành vi mong muốn.

### 8.3. SQL Server: MERGE hoặc mẫu UPDATE/INSERT

Ví dụ MERGE:

```sql
MERGE dbo.products AS target
USING (
    SELECT
        N'A-001' AS sku,
        N'Phone Alpha' AS product_name,
        CAST(120.00 AS DECIMAL(12,2)) AS unit_price
) AS source
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET
        product_name = source.product_name,
        unit_price = source.unit_price
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, unit_price)
    VALUES (source.sku, source.product_name, source.unit_price);
```

MERGE có semantics và lịch sử các tình huống concurrency/phức tạp cần đánh giá kỹ. Với hệ thống nhiều writer, có thể dùng transaction và mẫu UPDATE rồi INSERT có khóa/unique constraint phù hợp; không copy MERGE mà bỏ qua race condition.

### 8.4. Oracle: MERGE

```sql
MERGE INTO products target
USING (
    SELECT
        'A-001' AS sku,
        'Phone Alpha' AS product_name,
        120.00 AS unit_price
    FROM dual
) source
ON (target.sku = source.sku)
WHEN MATCHED THEN
    UPDATE SET
        target.product_name = source.product_name,
        target.unit_price = source.unit_price
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, unit_price)
    VALUES (source.sku, source.product_name, source.unit_price);
```

Oracle dùng DUAL cho một SELECT giá trị đơn trong ví dụ. MERGE của Oracle có quy tắc riêng, chẳng hạn một dòng target không được update nhiều lần trong cùng thao tác MERGE.

### 8.5. SQLite: ON CONFLICT

SQLite 3.24+ hỗ trợ UPSERT:

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('A-001', 'Phone Alpha', 120.00)
ON CONFLICT(sku) DO UPDATE SET
    product_name = excluded.product_name,
    unit_price = excluded.unit_price;
```

excluded là dòng đề xuất insert. Đừng nhầm UPSERT ON CONFLICT với INSERT OR REPLACE: REPLACE có thể xóa dòng cũ rồi chèn dòng mới theo semantics conflict resolution, ảnh hưởng trigger, foreign key và row identity.

### 8.6. UPSERT không thay thế unique constraint

Cần có unique constraint/index thể hiện khóa nghiệp vụ. Nếu không có uniqueness phù hợp, DBMS không thể biết hai dòng nào là cùng một thực thể.

UPSERT đồng thời cũng cần xem xét concurrency, trigger, audit và side effect. Không giả định “một lệnh” luôn có cùng hành vi trong mọi hệ.

## 9. Trả về dữ liệu vừa INSERT/UPDATE/DELETE

| DBMS | Cơ chế |
|---|---|
| PostgreSQL | RETURNING |
| MySQL | Không có RETURNING DML tổng quát tương đương trong MySQL 8.x; dùng generated key/SELECT theo transaction |
| SQL Server | OUTPUT inserted/deleted |
| Oracle | RETURNING INTO trong PL/SQL/DML |
| SQLite | RETURNING từ 3.35 |

PostgreSQL:

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('B-002', 'Tablet', 300.00)
RETURNING product_id, sku;
```

SQL Server:

```sql
INSERT INTO dbo.products (sku, product_name, unit_price)
OUTPUT inserted.product_id, inserted.sku
VALUES ('B-002', N'Tablet', 300.00);
```

Oracle PL/SQL:

```sql
DECLARE
    v_id products.product_id%TYPE;
BEGIN
    INSERT INTO products (sku, product_name, unit_price)
    VALUES ('B-002', 'Tablet', 300.00)
    RETURNING product_id INTO v_id;

    DBMS_OUTPUT.PUT_LINE(v_id);
END;
/
```

SQLite:

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('B-002', 'Tablet', 300.00)
RETURNING product_id, sku;
```

MySQL thường dùng JDBC getGeneratedKeys() hoặc LAST_INSERT_ID() trong cùng connection khi phù hợp. Với update phức tạp, cần đọc lại dòng theo khóa duy nhất trong transaction/consistency model thích hợp.

Không thay SELECT theo khóa bằng một biến global hoặc connection khác; generated key thường gắn với session/connection hiện tại.

## 10. Transaction và DDL: khác biệt rất quan trọng

### 10.1. Transaction DML

Các hệ quản trị đều có cơ chế transaction, nhưng khả năng phụ thuộc engine/cấu hình:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Cú pháp mở transaction thay đổi: SQL Server thường dùng BEGIN TRANSACTION; Oracle bắt đầu transaction ngầm từ DML và dùng COMMIT/ROLLBACK; MySQL dùng START TRANSACTION hoặc BEGIN; SQLite có BEGIN [DEFERRED|IMMEDIATE|EXCLUSIVE].

### 10.2. DDL và implicit commit

| DBMS | Đặc điểm cần nhớ |
|---|---|
| PostgreSQL | Nhiều DDL có thể chạy trong transaction và rollback; có ngoại lệ/giới hạn theo lệnh |
| MySQL | Nhiều DDL gây implicit commit; không giả định rollback phục hồi schema |
| SQL Server | Nhiều DDL hỗ trợ transaction, nhưng không phải mọi thao tác quản trị/DDL đều transactional như nhau |
| Oracle | DDL thường commit ngầm trước và sau thao tác |
| SQLite | DDL có thể tham gia transaction; hành vi còn phụ thuộc lệnh và connection |

Ví dụ MySQL/Oracle không nên được xử lý như PostgreSQL khi viết migration:

```sql
BEGIN;

ALTER TABLE products ADD COLUMN note VARCHAR(100);

ROLLBACK;
```

Không giả định câu ROLLBACK sẽ xóa cột vừa thêm trên MySQL/Oracle. Hãy đọc tài liệu đúng DBMS cho lệnh cụ thể.

### 10.3. Savepoint

Cả năm hệ có cơ chế savepoint ở các mức hỗ trợ khác nhau:

```sql
SAVEPOINT before_optional_step;

-- Thao tác phụ

ROLLBACK TO SAVEPOINT before_optional_step;
```

Cú pháp rollback to savepoint, release savepoint và hành vi khi lỗi khác nhau. SQL Server dùng SAVE TRANSACTION và ROLLBACK TRANSACTION savepoint_name; Oracle không có RELEASE SAVEPOINT theo cùng cách phổ quát; SQLite/PostgreSQL/MySQL có cú pháp SAVEPOINT/ROLLBACK TO tương tự nhưng semantics transaction riêng.

### 10.4. Isolation level

Các mức READ COMMITTED, REPEATABLE READ, SERIALIZABLE có mặt dưới nhiều dạng, nhưng semantics triển khai không đồng nhất.

- PostgreSQL dùng MVCC và có snapshot semantics riêng.
- MySQL InnoDB dùng MVCC, gap/next-key locking trong một số truy vấn.
- SQL Server có locking isolation và các chế độ row-versioning như READ_COMMITTED_SNAPSHOT/SNAPSHOT.
- Oracle dùng read consistency/MVCC với semantics riêng.
- SQLite có transaction và snapshot/read locking theo journal mode, chỉ một writer tại một thời điểm.

Không suy rằng cùng tên isolation level đồng nghĩa cùng anomaly, lock footprint hoặc concurrency.

## 11. Stored procedure, function và trigger

| DBMS | Ngôn ngữ/khả năng |
|---|---|
| PostgreSQL | Function và procedure; PL/pgSQL; procedure có transaction control trong điều kiện phù hợp |
| MySQL | Stored procedure, function, trigger; routine restrictions |
| SQL Server | Stored procedure, function, trigger bằng T-SQL |
| Oracle | Procedure, function, package, trigger bằng PL/SQL |
| SQLite | Không có stored procedure native; có trigger, view và function do ứng dụng/extension đăng ký |

### 11.1. Procedure và function không giống nhau

Một procedure thường được gọi để thực hiện thao tác; function thường trả giá trị và có thể tham gia biểu thức truy vấn. Ranh giới và quy tắc chính xác khác nhau giữa DBMS.

PostgreSQL:

```sql
CREATE OR REPLACE FUNCTION add_tax(amount NUMERIC)
RETURNS NUMERIC
LANGUAGE SQL
AS $$
    SELECT amount * 1.1;
$$;

SELECT add_tax(100);
```

SQL Server:

```sql
CREATE FUNCTION dbo.add_tax(@amount DECIMAL(12,2))
RETURNS DECIMAL(12,2)
AS
BEGIN
    RETURN @amount * 1.1;
END;
```

Oracle:

```sql
CREATE OR REPLACE FUNCTION add_tax(p_amount NUMBER)
RETURN NUMBER
IS
BEGIN
    RETURN p_amount * 1.1;
END;
/
```

Không thể copy nguyên function body giữa các hệ vì khác ngôn ngữ procedural, cách khai báo biến, xử lý exception và transaction.

### 11.2. SQLite không có stored procedure native

Có thể dùng trigger và user-defined function do ứng dụng đăng ký, nhưng đó không phải stored procedure được lưu và gọi trong database theo mô hình PL/SQL/T-SQL.

Nếu ứng dụng chuyển từ Oracle/SQL Server sang SQLite, logic procedure thường cần chuyển lên tầng application/service hoặc thiết kế lại bằng trigger/view có giới hạn phù hợp.

## 12. Hàm ngày giờ và lấy thời điểm hiện tại

Tên hàm khác nhau:

| Mục tiêu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Thời điểm hiện tại | CURRENT_TIMESTAMP, now() | CURRENT_TIMESTAMP, NOW() | CURRENT_TIMESTAMP, SYSDATETIME() | CURRENT_TIMESTAMP, SYSTIMESTAMP | datetime('now'), CURRENT_TIMESTAMP |
| Cộng ngày | interval | DATE_ADD | DATEADD | date + number hoặc INTERVAL | date()/datetime() modifier |
| Lấy năm | EXTRACT(YEAR FROM d) | YEAR(d) | YEAR(d) | EXTRACT(YEAR FROM d) | strftime('%Y', d) |
| Chuyển kiểu | CAST | CAST/CONVERT | CAST/CONVERT | CAST/TO_DATE/TO_TIMESTAMP | CAST hạn chế theo storage class |

Ví dụ PostgreSQL:

```sql
SELECT CURRENT_TIMESTAMP,
       CURRENT_TIMESTAMP + INTERVAL '7 days';
```

MySQL:

```sql
SELECT CURRENT_TIMESTAMP,
       DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY);
```

SQL Server:

```sql
SELECT SYSDATETIME(),
       DATEADD(day, 7, SYSDATETIME());
```

Oracle:

```sql
SELECT SYSTIMESTAMP,
       SYSTIMESTAMP + INTERVAL '7' DAY
FROM dual;
```

SQLite:

```sql
SELECT CURRENT_TIMESTAMP,
       datetime('now', '+7 days');
```

Cẩn thận với precision, timezone và kiểu trả về. CURRENT_TIMESTAMP không nhất thiết có cùng precision hoặc timezone semantics giữa DBMS.

## 13. Hàm xử lý NULL và điều kiện

Các hàm thường gặp:

| Ý nghĩa | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Giá trị thay thế khi NULL | COALESCE | COALESCE, IFNULL | COALESCE, ISNULL | COALESCE, NVL | COALESCE, IFNULL |
| Điều kiện nhánh | CASE | CASE, IF() | CASE, IIF() | CASE, DECODE | CASE, iif() theo phiên bản |
| Chuyển kiểu | CAST, :: | CAST, CONVERT | CAST, CONVERT | CAST, TO_CHAR/TO_NUMBER | CAST với affinity |

COALESCE là lựa chọn tương đối portable:

```sql
SELECT COALESCE(phone_number, 'Not provided')
FROM customers;
```

Tránh dùng hàm vendor-specific nếu biểu thức portable đã đáp ứng yêu cầu. Tuy nhiên, ISNULL/IFNULL/NVL có thể có semantics kiểu dữ liệu, số đối số hoặc implicit conversion khác.

### 13.1. NULL và phép so sánh

Trong SQL, NULL biểu thị thiếu/không xác định, không bằng 0 và cũng không bằng chuỗi rỗng trong mọi DBMS. Dùng IS NULL/IS NOT NULL:

```sql
SELECT *
FROM customers
WHERE phone_number IS NULL;
```

Không viết phone_number = NULL. Oracle có quy tắc chuỗi rỗng được coi là NULL, đây là một khác biệt quan trọng khi port dữ liệu.

## 14. CTE, window functions và cú pháp truy vấn hiện đại

CTE thường có cú pháp gần nhau:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT *
FROM customer_totals
WHERE total_amount > 1000;
```

Window function:

```sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY order_date DESC, order_id DESC
    ) AS row_num
FROM orders;
```

Năm DBMS hiện đại đều hỗ trợ nhiều CTE/window functions, nhưng phiên bản cũ có thể thiếu một số khả năng. SQL Server hỗ trợ CTE và window functions; Oracle/PostgreSQL/MySQL/SQLite cũng có nhưng cú pháp giới hạn dòng, recursive CTE, materialization hint và function details khác nhau.

Đừng coi CTE luôn là bảng tạm vật lý. Planner có thể inline hoặc materialize tùy DBMS/phiên bản/cấu trúc.

## 15. Index và chiến lược tối ưu

| DBMS | Một số index nổi bật | Dùng khi |
|---|---|---|
| PostgreSQL | B-tree, GIN, GiST, BRIN, hash, partial/expression | Equality/range, JSON/array, spatial, dữ liệu lớn theo thứ tự vật lý |
| MySQL InnoDB | B-tree, FULLTEXT, SPATIAL, functional key parts | Equality/range, text search, spatial |
| SQL Server | Clustered/nonclustered, filtered, included columns, columnstore, spatial | OLTP, covering, analytics, spatial |
| Oracle | B-tree, bitmap, function-based, domain, partitioned indexes | OLTP, analytic/warehouse, expression, specialized domain |
| SQLite | B-tree, partial, expression, covering | Ứng dụng nhúng, lọc/sắp xếp theo schema |

### 15.1. Index không phải nút tăng tốc miễn phí

Index làm tăng:

- Dung lượng lưu trữ.
- Chi phí INSERT/UPDATE/DELETE.
- Công việc bảo trì và vacuum/rebuild tùy DBMS.
- Độ phức tạp của planner.

Chỉ tạo index theo workload và kế hoạch truy vấn thực tế.

### 15.2. Partial/filtered index

PostgreSQL:

```sql
CREATE INDEX active_users_email_idx
ON users(email)
WHERE is_active = TRUE;
```

SQL Server filtered index:

```sql
CREATE INDEX active_users_email_idx
ON dbo.users(email)
WHERE is_active = 1;
```

SQLite cũng hỗ trợ partial index:

```sql
CREATE INDEX active_users_email_idx
ON users(email)
WHERE is_active = 1;
```

MySQL và Oracle không có partial index tổng quát cùng cú pháp này; có thể dùng generated/function-based column hoặc thiết kế index khác tùy yêu cầu.

### 15.3. Index expression/function-based

PostgreSQL:

```sql
CREATE INDEX users_lower_email_idx
ON users (LOWER(email));
```

Oracle:

```sql
CREATE INDEX users_lower_email_idx
ON users (LOWER(email));
```

SQLite hỗ trợ expression index; SQL Server có thể dùng computed column được index theo điều kiện; MySQL có functional index trong các phiên bản hiện đại. Chi tiết deterministic function, collation và precision khác nhau.

## 16. Kiểu JOIN và khóa ngoại

INNER JOIN, LEFT JOIN, RIGHT JOIN và FULL OUTER JOIN có mức hỗ trợ khác nhau theo DBMS/phiên bản. SQLite hiện đại hỗ trợ RIGHT/FULL OUTER JOIN từ các phiên bản mới hơn; hệ cũ có thể không.

Một truy vấn LEFT JOIN tương đối portable:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Khóa ngoại và ON DELETE/UPDATE CASCADE phổ biến ở các hệ quản trị, nhưng cần xác nhận storage engine/cấu hình. Trong MySQL, dùng InnoDB để có transaction và foreign key như kỳ vọng; không suy hành vi từ engine cũ không hỗ trợ đầy đủ.

SQLite có PRAGMA foreign_keys; ứng dụng cần đảm bảo enforcement được bật cho connection theo cách triển khai. Không chỉ nhìn DDL khai báo FOREIGN KEY mà kết luận mọi connection đều đang enforce.

## 17. Placeholder tham số theo driver

SQL server-side và placeholder của thư viện ứng dụng không phải lúc nào cũng giống nhau.

| Môi trường | Placeholder thường gặp |
|---|---|
| PostgreSQL native prepared statement | $1, $2 |
| JDBC PreparedStatement | ? |
| MySQL prepared statement protocol/driver | ? |
| SQL Server T-SQL procedure/sp_executesql | @parameter |
| Oracle SQL/PLSQL bind | :parameter |
| SQLite DB-API/driver | ?, ?1, :name hoặc dạng driver hỗ trợ |

Ví dụ Python DB-API có nhiều paramstyle: qmark, named, format, pyformat, numeric. Không copy placeholder từ một driver sang driver khác nếu chưa kiểm tra adapter.

**Không nối giá trị vào SQL để né khác biệt placeholder.** Hãy để driver/ORM quản lý binding và viết adapter theo DBMS.

## 18. Error handling và mã lỗi

Mỗi DBMS có mô hình exception riêng:

- PostgreSQL: SQLSTATE, EXCEPTION trong PL/pgSQL.
- MySQL: handler trong stored program, SIGNAL/RESIGNAL.
- SQL Server: TRY/CATCH, THROW, ERROR_* functions.
- Oracle: EXCEPTION, RAISE, SQLCODE/SQLERRM.
- SQLite: result code/extended result code qua API; không có stored PL/SQL-like exception block.

Không viết ứng dụng dựa vào việc parse chuỗi thông báo lỗi. Dùng SQLSTATE/vendor code hoặc exception type do driver cung cấp, rồi ánh xạ sang lỗi nghiệp vụ.

Ví dụ PostgreSQL:

```sql
DO $$
BEGIN
    INSERT INTO products(sku, product_name)
    VALUES ('A-001', 'Duplicate');
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'SKU already exists';
END;
$$;
```

SQL Server:

```sql
BEGIN TRY
    INSERT INTO dbo.products(sku, product_name)
    VALUES ('A-001', N'Duplicate');
END TRY
BEGIN CATCH
    SELECT
        ERROR_NUMBER() AS error_number,
        ERROR_MESSAGE() AS error_message;
    THROW;
END CATCH;
```

Oracle:

```sql
BEGIN
    INSERT INTO products(sku, product_name)
    VALUES ('A-001', 'Duplicate');
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('SKU already exists');
END;
/
```

Không nuốt lỗi transaction mà không biết trạng thái transaction sau lỗi. Một số DBMS đánh dấu transaction/subtransaction vào trạng thái lỗi và yêu cầu rollback trước khi tiếp tục.

## 19. Ma trận cú pháp cho cùng một thao tác

Phần này đặt các ví dụ cạnh nhau để thấy điểm cần adapter.

### 19.1. Lấy 10 dòng đầu

PostgreSQL/MySQL/SQLite:

```sql
SELECT product_id, product_name
FROM products
ORDER BY product_id
LIMIT 10;
```

SQL Server:

```sql
SELECT TOP (10) product_id, product_name
FROM dbo.products
ORDER BY product_id;
```

Oracle 12c+:

```sql
SELECT product_id, product_name
FROM products
ORDER BY product_id
FETCH FIRST 10 ROWS ONLY;
```

### 19.2. Giá trị hiện tại

PostgreSQL:

```sql
SELECT CURRENT_TIMESTAMP;
```

MySQL:

```sql
SELECT CURRENT_TIMESTAMP;
```

SQL Server:

```sql
SELECT SYSDATETIME();
```

Oracle:

```sql
SELECT SYSTIMESTAMP FROM dual;
```

SQLite:

```sql
SELECT CURRENT_TIMESTAMP;
```

Cùng ý tưởng “thời điểm hiện tại” nhưng kiểu trả về, precision và timezone semantics khác.

### 19.3. Giá trị NULL thay thế

Portable:

```sql
SELECT COALESCE(phone, 'Unknown')
FROM customers;
```

Đây là ví dụ tốt về cú pháp chung có thể dùng ở cả năm hệ quản trị, với điều kiện kiểu dữ liệu tương thích.

### 19.4. Chèn một dòng và lấy ID

Không có một câu DML duy nhất tương thích nguyên văn trên cả năm hệ:

- PostgreSQL: INSERT ... RETURNING.
- MySQL: generated keys qua driver hoặc LAST_INSERT_ID() cùng connection.
- SQL Server: INSERT ... OUTPUT inserted.id.
- Oracle: INSERT ... RETURNING id INTO biến.
- SQLite 3.35+: INSERT ... RETURNING.

Hãy tạo interface ở tầng repository, ví dụ createProduct trả Product có ID, rồi triển khai adapter theo DBMS. Business service không cần biết cú pháp SQL khác nhau.

## 20. Những khác biệt đặc biệt cần nhớ

### 20.1. Oracle coi chuỗi rỗng là NULL

Đây là khác biệt có ảnh hưởng lớn. Một ứng dụng gửi chuỗi rỗng vào cột VARCHAR2 Oracle có thể nhận semantics NULL, trong khi PostgreSQL/MySQL/SQL Server/SQLite có thể lưu chuỗi rỗng như một giá trị khác NULL.

Migration cần quyết định:

- Chuỗi rỗng có phải dữ liệu hợp lệ?
- Có cần chuẩn hóa thành NULL?
- Unique constraint có hành xử khác khi NULL?
- Điều kiện tìm kiếm có cần thay đổi?

### 20.2. SQLite có type affinity

SQLite không cưỡng chế kiểu cột chặt chẽ như nhiều server DBMS trong bảng thông thường. Một cột khai báo VARCHAR(20) vẫn có thể chứa giá trị có storage class khác hoặc chuỗi dài hơn 20 ký tự.

SQLite có STRICT tables từ 3.37, nhưng tập kiểu dữ liệu và quy tắc vẫn khác các hệ quan hệ server. Nếu ứng dụng dựa vào CHECK/STRICT/validation, hãy kiểm tra trên phiên bản triển khai.

### 20.3. MySQL engine ảnh hưởng semantics

InnoDB hỗ trợ transaction và foreign key. Một số engine khác có khả năng khác. Vì vậy câu CREATE TABLE trên MySQL nên chỉ rõ ENGINE=InnoDB nếu ứng dụng phụ thuộc vào transactional DML và FK.

### 20.4. SQL Server collation có thể phân biệt hoa/thường

Tên cột, dữ liệu chuỗi và LIKE có thể chịu ảnh hưởng collation. Đừng mặc định SQL Server không phân biệt hoa/thường chỉ vì một instance phổ biến được cấu hình như vậy.

### 20.5. PostgreSQL extension mở rộng SQL mạnh

PostgreSQL có extension như PostGIS, pg_trgm, hstore và nhiều module khác. Extension cần được cài/enable và có phiên bản tương thích; không phải mọi database PostgreSQL đều có sẵn.

## 21. Thiết kế SQL portable và ranh giới vendor-specific

Không cần ép mọi truy vấn thành cú pháp tối thiểu chung. Hãy chia thành ba lớp.

### 21.1. Lớp SQL portable

Ưu tiên cho logic phổ biến:

- SELECT, INSERT, UPDATE, DELETE.
- INNER/LEFT JOIN.
- GROUP BY, HAVING.
- CASE, COALESCE.
- EXISTS, subquery, CTE cơ bản.
- Window functions phổ biến nếu baseline phiên bản đáp ứng.
- Primary key, unique, foreign key, CHECK ở mức hỗ trợ.

### 21.2. Lớp adapter theo DBMS

Đặt trong repository/dialect:

- Identity và generated key.
- UPSERT.
- RETURNING/OUTPUT.
- Pagination.
- JSON operators.
- Date arithmetic.
- Bulk insert.
- Locking syntax.
- Error code mapping.

Ví dụ interface:

```java
public interface ProductRepository {
    Product create(ProductInput input);
    Product findBySku(String sku);
    Product upsert(ProductInput input);
    List<Product> search(String text, PageRequest page);
}
```

Các implementation có thể dùng SQL riêng theo DBMS nhưng giữ cùng hợp đồng nghiệp vụ.

### 21.3. Lớp đặc thù không nên giả vờ portable

Các tính năng như:

- PostgreSQL GIN/GiST/PostGIS.
- SQL Server columnstore, temporal tables, specific T-SQL.
- Oracle packages, partitioning và advanced features.
- MySQL full-text/spatial engine behavior.
- SQLite FTS5, R-tree và embedded deployment.

nên được coi là năng lực vendor-specific. Khi chuyển DBMS, có thể cần thay thế chức năng chứ không chỉ thay câu SQL.

## 22. Chiến lược migration giữa các hệ quản trị

Một kế hoạch migration tốt cần làm rõ cả schema, dữ liệu và runtime.

### 22.1. Kiểm kê schema

Thu thập:

- Tables, columns và data types.
- Primary/foreign/unique/check constraints.
- Default và generated expressions.
- Identity/sequence.
- Indexes và partial/functional indexes.
- Views, procedures, functions, triggers.
- Grants, roles, policies.
- Extensions và vendor-specific objects.

### 22.2. Mapping kiểu dữ liệu

Tạo bảng mapping có chủ sở hữu quyết định:

| Nguồn | Đích | Câu hỏi phải giải quyết |
|---|---|---|
| BOOLEAN | TINYINT/BIT/NUMBER/INTEGER | Giá trị NULL/default có giữ nguyên? |
| NUMERIC(p,s) | DECIMAL/NUMBER/INTEGER cents | Precision/rounding có tương đương? |
| TIMESTAMPTZ | DATETIMEOFFSET/TIMESTAMP WITH TZ/TEXT | Thời điểm và timezone được bảo toàn? |
| JSONB | JSON/TEXT/JSON native | Index và operator nào phải viết lại? |
| ARRAY | JSON/join table/vendor type | Quan hệ và truy vấn có thay đổi? |
| UUID | UUID/BINARY/CHAR/TEXT | Byte order, canonical format và index? |
| ENUM | CHECK/lookup table/native enum | Cách thêm giá trị và migration? |

### 22.3. Migration dữ liệu

- Chốt encoding và collation.
- Chuyển timezone có kiểm soát.
- Chuẩn hóa chuỗi rỗng/NULL nếu cần.
- Xử lý precision và overflow.
- Đồng bộ sequence/identity sau import.
- Kiểm tra khóa ngoại và uniqueness.
- Chuyển JSON theo văn bản chuẩn.
- Đối chiếu số dòng, checksum hoặc aggregate nghiệp vụ.

### 22.4. Chuyển logic database

Procedure/trigger/view không tự dịch được bằng đổi tên hàm. Cần phân tích:

- Side effect.
- Transaction boundary.
- Exception behavior.
- Locking/concurrency.
- Security context/definer rights.
- Dynamic SQL.
- Generated keys.
- Trigger firing order và multi-row semantics.

### 22.5. Chạy song song và đối soát

Nếu hệ thống cho phép, có thể chạy read-only comparison hoặc dual-run trong thời gian chuyển đổi:

- So kết quả truy vấn nghiệp vụ.
- So số liệu aggregate.
- So thời điểm/rounding.
- So xử lý NULL.
- So thứ tự phân trang.
- So unique conflict.
- So rollback/failure path.

Không chuyển traffic production chỉ vì schema đã tạo thành công.

## 23. Kiểm thử đa DBMS

Một bộ test portable nên tách test semantics khỏi test syntax.

### 23.1. Contract test

Cùng một hợp đồng nghiệp vụ chạy trên từng backend:

- Tạo bản ghi và lấy ID.
- Tìm theo unique key.
- UPSERT khi có conflict.
- Phân trang có thứ tự ổn định.
- Transaction chuyển tiền: cả hai cập nhật cùng commit/rollback.
- NULL và chuỗi rỗng.
- Timestamp và timezone.
- Unique constraint khi có hai writer.
- Foreign key và cascade.

### 23.2. Test version và feature

Không chỉ test “PostgreSQL”, test version PostgreSQL được hỗ trợ. Tương tự MySQL, SQL Server, Oracle và SQLite.

Một feature matrix nội bộ có thể ghi:

| Feature | PostgreSQL baseline | MySQL baseline | SQL Server baseline | Oracle baseline | SQLite baseline |
|---|---|---|---|---|---|
| UPSERT | ON CONFLICT | ON DUPLICATE KEY | MERGE/adapter | MERGE | ON CONFLICT |
| RETURNING | Có | Không tổng quát | OUTPUT | RETURNING INTO | 3.35+ |
| JSON | json/jsonb | JSON | functions trên text | version-dependent native | JSON functions |
| Partial index | Có | Không tổng quát | Filtered index | Không cùng cú pháp | Có |

Điền version cụ thể của dự án trước khi dùng bảng này như tiêu chuẩn release.

### 23.3. Integration test cần DBMS thật

SQLite không phải bản thay thế hoàn hảo cho PostgreSQL/MySQL/SQL Server trong test nếu production dùng các hệ đó. Type affinity, locking, SQL syntax, JSON, collation và transaction behavior khác nhau.

Dùng test container hoặc database service đúng engine/version cho integration test quan trọng. SQLite in-memory rất hữu ích cho test nhanh, nhưng không chứng minh SQL portable.

### 23.4. Kiểm tra concurrency

Các bài test có hai transaction đồng thời:

- Cùng INSERT một unique key.
- Cùng cập nhật số dư.
- Đọc rồi ghi theo optimistic/pessimistic locking.
- UPSERT cùng khóa.
- Deadlock và retry.
- Phân trang khi dữ liệu đang được thêm.

Một câu SQL chạy đúng tuần tự có thể thất bại khi nhiều writer cạnh tranh.

## 24. Bảng lựa chọn nhanh theo nhu cầu

| Nhu cầu | Điểm cần ưu tiên |
|---|---|
| Ứng dụng server nhiều transaction | PostgreSQL/MySQL InnoDB/SQL Server/Oracle theo workload |
| Database nhúng trong app | SQLite |
| SQL portable qua nhiều DBMS | Giữ core SQL đơn giản, dialect adapter cho phần khác |
| JSON query/index phức tạp | Đánh giá operator, index và version cụ thể |
| Tìm kiếm văn bản | Full-text/trigram theo engine |
| Dữ liệu không gian | PostGIS, MySQL Spatial, SQL Server geography, Oracle Spatial, SpatiaLite |
| Stored procedure nhiều logic | PL/pgSQL, T-SQL, PL/SQL hoặc MySQL routine; SQLite chuyển logic lên app |
| Workload phân tích | Đánh giá columnstore/bitmap/BRIN/partitioning theo DBMS |
| App offline/local-first | SQLite thường phù hợp, cần đồng bộ ở tầng ứng dụng |
| Migration lâu dài | Mapping type, transaction, identity, collation và feature matrix |

Không có DBMS “tốt nhất” cho mọi ứng dụng. Lựa chọn phải dựa vào workload, đội vận hành, hệ sinh thái, license, HA/backup, yêu cầu dữ liệu và chi phí.

## 25. Các sai lầm khi port SQL

1. **Đổi LIMIT thành TOP nhưng quên ORDER BY.** Kết quả không ổn định.
2. **Đổi AUTO_INCREMENT thành IDENTITY mà không đồng bộ sequence.** Có thể va chạm khóa sau import.
3. **Đổi BOOLEAN thành INT nhưng không thêm CHECK.** Dữ liệu có thể nhận giá trị ngoài 0/1.
4. **Đổi JSONB sang TEXT nhưng bỏ index/operator.** Truy vấn có thể chậm hoặc đổi semantics.
5. **Coi DATETIME và TIMESTAMPTZ tương đương.** Có thể làm lệch thời điểm khi qua timezone.
6. **Giả định DDL rollback được ở mọi hệ.** MySQL/Oracle thường implicit commit.
7. **Dùng REPLACE như UPSERT.** Có thể có delete/insert side effect thay vì update.
8. **Dùng MERGE mà không xem concurrency.** Có thể phát sinh race/duplicate hoặc semantics ngoài mong đợi.
9. **Dùng LAST_INSERT_ID trên connection khác.** Giá trị generated key gắn với session/connection.
10. **Copy function PL/SQL sang T-SQL.** Ngôn ngữ và exception/transaction khác.
11. **Dùng SQLite test rồi kết luận production SQL chạy trên server DBMS.** SQLite có type affinity và locking khác.
12. **Coi chuỗi rỗng giống nhau trên Oracle và PostgreSQL.** Oracle SQL xử lý chuỗi rỗng như NULL.
13. **Quote tên cột không nhất quán.** Có thể làm identifier case-sensitive hoặc khó port.
14. **Dùng || nối chuỗi trên MySQL mặc định.** Có thể được hiểu là logical OR.
15. **Không kiểm tra collation.** LIKE, equality và sort có thể đổi kết quả.
16. **Cho rằng mọi index đều B-tree.** Các engine có GIN/GiST/bitmap/columnstore/R-tree và chiến lược khác.
17. **Chỉ test syntax, không test kết quả.** Cùng câu lệnh có thể khác semantics.
18. **Dùng ORM và nghĩ không còn khác biệt DBMS.** ORM vẫn có dialect, generated SQL và giới hạn portability.
19. **Không test concurrency.** UPSERT và transaction có thể khác khi nhiều writer.
20. **Dùng SQL injection escaping thay parameterization.** Ghép chuỗi vẫn có rủi ro.

## 26. Bài tập có lời giải

### Bài 1. Hệ nào dùng AUTO_INCREMENT?

**Đáp án:** MySQL. SQL Server thường dùng IDENTITY, PostgreSQL/Oracle có identity/sequence, SQLite thường dùng INTEGER PRIMARY KEY/ROWID.

### Bài 2. SQLite có kiểu BOOLEAN riêng không?

**Đáp án:** Không có storage class Boolean riêng. Thường lưu 0/1 và thêm CHECK nếu cần cưỡng chế.

### Bài 3. Oracle 19c có SQL column BOOLEAN như PostgreSQL không?

**Đáp án:** Không. Oracle 19c có BOOLEAN trong PL/SQL nhưng không dùng BOOLEAN làm kiểu cột SQL thông thường; thường dùng NUMBER(1)/CHAR(1). Native SQL BOOLEAN thuộc thế hệ mới hơn như 23c/23ai.

### Bài 4. MySQL nối chuỗi bằng || có portable không?

**Đáp án:** Không. MySQL mặc định hiểu || là logical OR, trừ khi SQL mode thay đổi. Dùng CONCAT.

### Bài 5. PostgreSQL lấy 20 dòng từ offset 40?

```sql
SELECT *
FROM products
ORDER BY product_id
LIMIT 20 OFFSET 40;
```

**Đáp án:** dùng LIMIT/OFFSET.

### Bài 6. SQL Server phân trang?

**Đáp án:** ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY, hoặc TOP cho số dòng đầu.

### Bài 7. PostgreSQL UPSERT?

```sql
INSERT INTO products(sku, product_name)
VALUES ('A-001', 'Phone')
ON CONFLICT(sku)
DO UPDATE SET product_name = EXCLUDED.product_name;
```

**Đáp án:** ON CONFLICT với EXCLUDED đại diện dòng đề xuất insert.

### Bài 8. MySQL UPSERT?

**Đáp án:** INSERT ... ON DUPLICATE KEY UPDATE. Chú ý row alias từ MySQL 8.0.19+ và VALUES(column) deprecated từ 8.0.20.

### Bài 9. SQLite ON CONFLICT DO UPDATE có từ khi nào?

**Đáp án:** SQLite 3.24.0 trở lên.

### Bài 10. SQL Server lấy dòng vừa INSERT bằng gì?

**Đáp án:** OUTPUT inserted.column.

### Bài 11. Oracle lấy giá trị vừa INSERT trong PL/SQL?

**Đáp án:** RETURNING column INTO variable.

### Bài 12. SQLite RETURNING có từ phiên bản nào?

**Đáp án:** SQLite 3.35.0 trở lên.

### Bài 13. MySQL có RETURNING tổng quát giống PostgreSQL không?

**Đáp án:** Không trong MySQL 8.x. Dùng generated keys/LAST_INSERT_ID hoặc SELECT theo khóa phù hợp.

### Bài 14. DDL PostgreSQL có thể rollback không?

**Đáp án:** Nhiều DDL PostgreSQL có thể nằm trong transaction và rollback, nhưng có ngoại lệ theo lệnh. Phải kiểm tra lệnh cụ thể.

### Bài 15. DDL Oracle thường có implicit commit không?

**Đáp án:** Có. Không giả định ROLLBACK sau DDL khôi phục mọi thay đổi trước đó.

### Bài 16. MySQL InnoDB có transaction không?

**Đáp án:** Có. Không suy từ đó rằng mọi engine MySQL đều có cùng transactional behavior.

### Bài 17. SQLite có stored procedure native không?

**Đáp án:** Không. Thường đặt logic ở ứng dụng hoặc dùng trigger/view/user-defined function theo giới hạn.

### Bài 18. JSONB PostgreSQL có thể copy binary sang SQLite JSONB?

**Đáp án:** Không. Đây là định dạng nội bộ khác nhau. Trao đổi bằng JSON text chuẩn hoặc giao thức ứng dụng.

### Bài 19. Oracle chuỗi rỗng có giống PostgreSQL không?

**Đáp án:** Không. Oracle SQL coi chuỗi rỗng như NULL; PostgreSQL lưu chuỗi rỗng như giá trị chuỗi.

### Bài 20. SQLite có cưỡng chế VARCHAR(20) như SQL Server không?

**Đáp án:** Không theo cách thông thường. SQLite dùng type affinity; cần CHECK hoặc STRICT/schema validation nếu muốn giới hạn.

### Bài 21. SQL Server BIT và PostgreSQL BOOLEAN có hoàn toàn giống nhau?

**Đáp án:** Không. Cần xem mapping driver, NULL, literal và constraint. BIT của SQL Server có thể biểu diễn 0/1/NULL.

### Bài 22. MySQL DATETIME tự chuyển timezone như TIMESTAMP?

**Đáp án:** Không. DATETIME không tự mang timezone; TIMESTAMP có chuyển đổi theo session timezone.

### Bài 23. PostgreSQL TIMESTAMPTZ giữ tên timezone ban đầu?

**Đáp án:** Không. Nó lưu thời điểm tuyệt đối và hiển thị theo timezone session; nếu cần tên timezone gốc, lưu riêng.

### Bài 24. SQLite lưu ngày giờ bằng kiểu nào?

**Đáp án:** Không có date/time storage class riêng; thường TEXT, REAL hoặc INTEGER theo quy ước.

### Bài 25. Identifier quote trong MySQL?

**Đáp án:** Backtick phổ biến. Double quote có ý nghĩa phụ thuộc SQL mode ANSI_QUOTES.

### Bài 26. Identifier không quote trong PostgreSQL được fold ra sao?

**Đáp án:** Về chữ thường. Oracle fold identifier không quote thành chữ hoa.

### Bài 27. Partial index có trên PostgreSQL và SQLite không?

**Đáp án:** Có. SQL Server có filtered index với cú pháp riêng. MySQL/Oracle không có cú pháp partial index tổng quát tương tự.

### Bài 28. Vì sao OFFSET lớn có thể chậm?

**Đáp án:** DBMS có thể phải đi qua nhiều dòng rồi bỏ qua. Keyset pagination có thể phù hợp hơn với trang sâu.

### Bài 29. SQLite có thể thay PostgreSQL trong mọi integration test không?

**Đáp án:** Không. Type affinity, locking, SQL dialect, JSON, collation và transaction khác nhau. Cần test trên engine production.

### Bài 30. Ba nguyên tắc khi viết ứng dụng hỗ trợ nhiều DBMS?

**Đáp án:**
1. Giữ SQL core portable ở nơi có thể.
2. Đưa cú pháp đặc thù vào dialect/repository adapter.
3. Chạy contract/integration tests trên đúng DBMS và version được hỗ trợ.

## 27. Checklist trước khi tuyên bố SQL portable

- [ ] Ghi rõ DBMS và version baseline.
- [ ] Kiểm tra type mapping và precision.
- [ ] Kiểm tra Boolean, NULL và chuỗi rỗng.
- [ ] Kiểm tra timezone và date arithmetic.
- [ ] Kiểm tra identity/sequence và generated key.
- [ ] Kiểm tra UPSERT, conflict và concurrency.
- [ ] Kiểm tra RETURNING/OUTPUT và driver behavior.
- [ ] Kiểm tra LIMIT/OFFSET/FETCH và ORDER BY ổn định.
- [ ] Kiểm tra DDL transaction/implicit commit.
- [ ] Kiểm tra stored procedure, function và trigger.
- [ ] Kiểm tra JSON representation và index.
- [ ] Kiểm tra identifier quoting/case/collation.
- [ ] Kiểm tra index và execution plan.
- [ ] Kiểm tra foreign key enforcement và engine.
- [ ] Kiểm tra error codes và retry logic.
- [ ] Chạy integration tests trên đúng engine/version.
- [ ] Test concurrency, rollback và failure path.
- [ ] Đối soát dữ liệu sau migration.

## 28. Kết luận

Năm hệ quản trị đều triển khai SQL, nhưng chúng không phải năm cách viết cú pháp thay thế trực tiếp cho nhau. Sự khác biệt quan trọng nằm ở **kiểu dữ liệu, identity, NULL, chuỗi, thời gian, JSON, UPSERT, trả dữ liệu vừa ghi, transaction/DDL, procedural language, index và concurrency**.

Cách thiết kế bền vững là:

1. Dùng SQL portable cho logic quan hệ cơ bản khi có thể.
2. Ghi rõ phiên bản và semantics cần hỗ trợ.
3. Đặt cú pháp đặc thù trong adapter/repository hoặc migration theo DBMS.
4. Không dùng SQLite test để thay thế integration test của server DBMS.
5. Kiểm tra dữ liệu, transaction và concurrency sau khi port, không chỉ kiểm tra câu SQL có parse được.

Một ma trận đối chiếu tốt giúp nhóm biết **cái gì có thể chia sẻ, cái gì phải viết riêng, và nơi nào cần test chuyên biệt**. Đó là nền tảng để phát triển ứng dụng đa DBMS mà không đánh đổi tính đúng đắn của dữ liệu.

## Tài liệu tham khảo

- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/): SQL syntax, data types, transactions, indexes, JSON và procedural languages.
- [MySQL 8.4 Reference Manual](https://dev.mysql.com/doc/refman/8.4/en/): data types, InnoDB, SQL statements, transactions và JSON.
- [Microsoft SQL Server Documentation](https://learn.microsoft.com/en-us/sql/sql-server/): T-SQL, data types, transactions, indexing và JSON.
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): SQL syntax, data types, DML, MERGE và transaction-related statements.
- [Oracle Database 23ai Documentation](https://docs.oracle.com/en/database/oracle/oracle-database/23/): các khả năng SQL thế hệ mới như Boolean và JSON.
- [SQLite Documentation](https://www.sqlite.org/docs.html): SQL syntax, datatypes, transactions, UPSERT, RETURNING và JSON.
- [SQLite Datatypes](https://www.sqlite.org/datatype3.html): storage classes, affinity và STRICT tables.
- [SQLite UPSERT](https://www.sqlite.org/lang_upsert.html): cú pháp và semantics ON CONFLICT.
- [SQLite RETURNING](https://www.sqlite.org/lang_returning.html): RETURNING clause và giới hạn.
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries và dynamic SQL an toàn.

