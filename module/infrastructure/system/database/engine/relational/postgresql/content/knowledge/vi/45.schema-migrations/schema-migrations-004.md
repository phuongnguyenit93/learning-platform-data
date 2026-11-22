# Thêm cột, giá trị mặc định và kiểm tra hành vi theo phiên bản

Thêm một cột vào bảng PostgreSQL có thể là thao tác rất nhẹ hoặc có thể làm database phải đọc/ghi lại toàn bộ bảng. Kết quả phụ thuộc vào phiên bản PostgreSQL, biểu thức DEFAULT, yêu cầu NOT NULL, loại cột và trạng thái của bảng. Sự khác biệt quan trọng nhất là từ PostgreSQL 11: thêm cột với default expression không volatile có thể dùng **fast default**, lưu giá trị mặc định trong metadata để rows cũ đọc được giá trị mới mà không rewrite toàn bộ heap.

Fast default không có nghĩa ALTER TABLE không cần lock, mọi default đều nhanh, hay thay đổi schema không ảnh hưởng ứng dụng. Migration an toàn cần kiểm tra server version, volatility, kích thước bảng, lock behavior, constraints, replication và cách ứng dụng triển khai code.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Thêm cột bằng ALTER TABLE ... ADD COLUMN.
- Phân biệt default của row hiện có với default áp dụng cho INSERT sau này.
- Giải thích khác biệt quan trọng giữa PostgreSQL 10 và PostgreSQL 11 trở lên.
- Phân biệt biểu thức default volatile và non-volatile.
- Nhận biết khi nào ADD COLUMN có thể tránh table rewrite.
- Hiểu tác động của NOT NULL, CHECK và DEFAULT.
- Đánh giá lock, thời gian chờ và tác động tới ứng dụng.
- Triển khai schema changes theo nhiều bước để giảm rủi ro.
- Kiểm tra catalog metadata và xác nhận kết quả trên dữ liệu cũ/mới.
- Thiết kế migration tương thích với nhiều phiên bản PostgreSQL.

## 2. Cú pháp ADD COLUMN

### 2.1. Cú pháp cơ bản

ALTER TABLE dùng để thêm một column:

```sql
ALTER TABLE customers
ADD COLUMN loyalty_level text;
```

Nếu không chỉ định DEFAULT, giá trị của cột mới trên rows đã tồn tại là NULL. INSERT sau đó cũng nhận NULL nếu ứng dụng không cung cấp giá trị và cột không có default hoặc constraint khác.

### 2.2. Thêm cột với default

```sql
ALTER TABLE customers
ADD COLUMN is_active boolean DEFAULT true;
```

Với row hiện có, PostgreSQL bảo đảm truy vấn nhìn thấy true cho cột mới. Với INSERT về sau, nếu câu lệnh bỏ qua is_active, default true được áp dụng.

### 2.3. Thêm cột NOT NULL

```sql
ALTER TABLE customers
ADD COLUMN status text NOT NULL DEFAULT 'active';
```

Mọi row phải có giá trị không NULL. Default non-NULL cung cấp giá trị cho rows cũ và INSERT mới. Nếu không có default, thêm cột NOT NULL vào bảng đang có rows thường thất bại vì rows cũ sẽ có giá trị NULL.

### 2.4. Thêm cột có kiểu cụ thể

```sql
ALTER TABLE orders
ADD COLUMN submitted_at timestamptz;
```

Kiểu dữ liệu ảnh hưởng storage, operators, casts, index design và client mapping. Chọn kiểu theo semantics; không dùng text cho mọi thứ nếu ứng dụng cần date/time, numeric hoặc enum semantics.

### 2.5. Thêm nhiều cột trong một ALTER TABLE

```sql
ALTER TABLE orders
    ADD COLUMN source text,
    ADD COLUMN priority smallint DEFAULT 0,
    ADD COLUMN reviewed_at timestamptz;
```

Một ALTER TABLE có thể thực hiện nhiều subcommands. Gộp thay đổi có thể giảm số lần lock acquisition nhưng nếu có subcommand nặng thì toàn command vẫn có thể kéo dài.

### 2.6. IF NOT EXISTS

```sql
ALTER TABLE customers
ADD COLUMN IF NOT EXISTS loyalty_level text;
```

IF NOT EXISTS tránh lỗi nếu column cùng tên đã tồn tại. Nó không xác nhận column hiện có đúng kiểu, default, nullability hoặc collation. Migration idempotent vẫn cần kiểm tra schema drift.

### 2.7. Đặt schema rõ ràng

```sql
ALTER TABLE public.customers
ADD COLUMN external_reference text;
```

Dùng schema-qualified table name trong migration để tránh search_path khiến command tác động nhầm bảng.

### 2.8. Xác minh sau khi thêm cột

```sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customers'
ORDER BY ordinal_position;
```

Đây là cách kiểm tra schema dễ đọc. Với thông tin PostgreSQL-specific như missing-value metadata, cần xem catalog pg_attribute ở phần sau.

## 3. DEFAULT có nghĩa gì?

### 3.1. Default áp dụng khi INSERT bỏ qua cột

```sql
ALTER TABLE invoices
ADD COLUMN currency text DEFAULT 'VND';

INSERT INTO invoices (invoice_number, total_amount)
VALUES ('INV-1001', 250000);
```

Row mới nhận currency = 'VND' vì INSERT không chỉ định column này.

### 3.2. DEFAULT không ghi đè giá trị do ứng dụng gửi

```sql
INSERT INTO invoices (invoice_number, total_amount, currency)
VALUES ('INV-1002', 90000, 'USD');
```

Giá trị tường minh USD được dùng. Default chỉ áp dụng khi column bị bỏ qua hoặc chỉ định từ khóa DEFAULT.

### 3.3. DEFAULT trong INSERT tường minh

```sql
INSERT INTO invoices (invoice_number, total_amount, currency)
VALUES ('INV-1003', 120000, DEFAULT);
```

DEFAULT yêu cầu PostgreSQL dùng default expression hiện tại của cột. Nếu cột không có default, kết quả là NULL (trừ các trường hợp identity/generated có semantics riêng).

### 3.4. DEFAULT không tự cập nhật rows cũ sau SET DEFAULT

```sql
ALTER TABLE invoices
ALTER COLUMN currency SET DEFAULT 'VND';
```

Lệnh trên thay đổi default cho INSERT/UPDATE tương lai mà không cung cấp giá trị. Nó không chạy UPDATE trên mọi row hiện có. Muốn backfill rows cũ, phải thực hiện DML riêng.

### 3.5. DROP DEFAULT không xóa giá trị đã lưu

```sql
ALTER TABLE invoices
ALTER COLUMN currency DROP DEFAULT;
```

Lệnh này bỏ default cho thao tác tương lai. Giá trị hiện có trong rows không bị xóa hay đổi thành NULL.

### 3.6. NULL và không chỉ định column

Hai câu lệnh sau khác nhau:

```sql
INSERT INTO invoices (invoice_number, currency)
VALUES ('INV-2001', DEFAULT);

INSERT INTO invoices (invoice_number, currency)
VALUES ('INV-2002', NULL);
```

DEFAULT yêu cầu dùng default expression; NULL yêu cầu lưu NULL và không kích hoạt default. Nếu column có NOT NULL, câu lệnh thứ hai bị từ chối.

### 3.7. Default expression được đánh giá lúc nào?

Default expression được tính khi cần tạo giá trị cho row mới. Với ADD COLUMN trên bảng đã có dữ liệu, PostgreSQL version và volatility của expression quyết định giá trị cho rows cũ được materialize bằng table rewrite hay được lưu như missing value metadata.

### 3.8. Một default cho mọi rows cũ

Khi ADD COLUMN dùng default non-volatile, PostgreSQL 11+ có thể đánh giá biểu thức một lần tại thời điểm ALTER TABLE và dùng cùng kết quả đó làm giá trị mặc định logic cho rows đã tồn tại. Đây là điểm khác với việc đánh giá một volatile expression riêng cho từng row.

### 3.9. Default có thể phụ thuộc session/transaction

Các biểu thức như CURRENT_USER, CURRENT_TIMESTAMP hoặc current_setting(...) có semantics phụ thuộc transaction/session. Cần hiểu volatility classification và giá trị mà migration session đang có trước khi dùng làm default.

### 3.10. Không nhầm default với generated column

Default chỉ cung cấp giá trị khi INSERT/UPDATE không chỉ định column. Generated column được tính từ biểu thức dựa trên các columns khác theo rules của PostgreSQL. Hai cơ chế có semantics và giới hạn khác nhau.

## 4. Volatility của biểu thức DEFAULT

### 4.1. Ba mức volatility

PostgreSQL phân loại functions thành:

| Volatility | Ý nghĩa tổng quát | Ví dụ |
| --- | --- | --- |
| IMMUTABLE | Cùng arguments luôn cho cùng kết quả; không phụ thuộc database/session/time. | lower(text), phép toán số học thuần. |
| STABLE | Kết quả ổn định trong một statement theo contract của function, nhưng có thể khác giữa statements. | CURRENT_TIMESTAMP, now(). |
| VOLATILE | Có thể thay đổi giữa các lần gọi, có side effects hoặc phụ thuộc trạng thái thay đổi. | clock_timestamp(), random(), nextval(). |

Đây là contract mà planner và executor dựa vào. Không khai báo function sai volatility chỉ để làm migration nhanh hơn.

### 4.2. Non-volatile default

PostgreSQL 11+ có thể dùng fast default nếu biểu thức default không volatile. Điều này bao gồm biểu thức immutable và stable theo catalog semantics. PostgreSQL đánh giá expression khi ALTER TABLE và lưu một missing value cho rows cũ.

Ví dụ:

```sql
ALTER TABLE events
ADD COLUMN imported_at timestamptz DEFAULT now();
```

now() trả transaction timestamp và là stable. Khi ALTER TABLE được thực hiện, rows cũ nhìn thấy một timestamp chung được đánh giá cho migration transaction; INSERT sau đó nhận default timestamp theo transaction của chúng.

### 4.3. Volatile default

Biểu thức volatile có thể cần giá trị khác nhau cho từng row cũ. PostgreSQL phải tính và lưu giá trị cho từng row bằng table rewrite khi thêm cột có volatile default.

Ví dụ:

```sql
ALTER TABLE sample_data
ADD COLUMN random_key double precision DEFAULT random();
```

Mỗi row cũ cần một kết quả riêng. Với bảng lớn, thao tác có thể đọc/ghi toàn bộ table, tạo I/O lớn và giữ lock mạnh trong thời gian dài.

### 4.4. clock_timestamp và now khác nhau

```sql
SELECT now(), transaction_timestamp(), statement_timestamp(), clock_timestamp();
```

- now() và transaction_timestamp() trả thời điểm bắt đầu transaction.
- statement_timestamp() trả thời điểm bắt đầu statement.
- clock_timestamp() trả thời gian thực tại lúc function được gọi và có thể thay đổi ngay trong một statement.

clock_timestamp() là volatile; now() là stable. Vì vậy hai default trông tương tự về ý nghĩa “thời gian hiện tại” có thể có chi phí ADD COLUMN khác nhau.

### 4.5. random và sequence

random() tạo kết quả thay đổi qua mỗi lần gọi. nextval() thay đổi sequence state và là volatile. Dùng chúng làm default khi ADD COLUMN trên bảng lớn có thể buộc rewrite, đồng thời sequence side effects cần được tính đến.

### 4.6. User-defined functions

PostgreSQL dựa vào volatility marker của function. Nếu function được đánh dấu STABLE nhưng thực tế phụ thuộc trạng thái thay đổi theo từng row/call, khai báo đó là sai và có thể dẫn tới kết quả không đúng. Không đổi VOLATILE thành STABLE chỉ để tránh rewrite.

### 4.7. Xem volatility trong catalog

```sql
SELECT
    p.oid::regprocedure AS function_name,
    p.provolatile,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_proc AS p
WHERE p.proname IN ('now', 'clock_timestamp', 'random', 'nextval')
ORDER BY 1;
```

provolatile là catalog flag: i, s hoặc v.

### 4.8. Biểu thức literal

```sql
ALTER TABLE accounts
ADD COLUMN region_code text DEFAULT 'VN';
```

Literal không phụ thuộc row/session và là trường hợp điển hình cho fast default từ PostgreSQL 11 trở lên.

### 4.9. Biểu thức cast

```sql
ALTER TABLE products
ADD COLUMN enabled boolean DEFAULT true;

ALTER TABLE products
ADD COLUMN created_on date DEFAULT DATE '2026-01-01';
```

Các constant expressions có thể được xử lý bằng fast default. Với casts hoặc operators do extension/user-defined types cung cấp, kiểm tra volatility và behavior thực tế.

### 4.10. Kiểm tra trước migration

Trước khi dùng function trong default, xác định:

1. Function built-in hay user-defined?
2. pg_proc.provolatile là gì?
3. Kết quả có cần khác nhau cho từng row cũ không?
4. Giá trị cho rows cũ phải đại diện thời điểm migration hay thời điểm từng row được tạo?
5. Migration chạy trên version nào?

Chọn biểu thức theo business semantics trước, sau đó mới đánh giá chi phí.

## 5. Fast default từ PostgreSQL 11

### 5.1. Hành vi trước PostgreSQL 11

Trong PostgreSQL 10 và các phiên bản trước, ADD COLUMN có non-NULL DEFAULT trên bảng đã có dữ liệu thường phải rewrite table để ghi default vào từng row. Với bảng lớn, điều này có thể tốn nhiều thời gian, I/O và lock.

Ví dụ:

```sql
ALTER TABLE large_orders
ADD COLUMN source text DEFAULT 'legacy';
```

Trên PostgreSQL 10 trở về trước, không nên giả định câu lệnh này là metadata-only; việc thêm default có thể rewrite heap.

### 5.2. PostgreSQL 11: fast default

PostgreSQL 11 giới thiệu tối ưu cho ADD COLUMN với non-volatile default. Thay vì ghi giá trị vào tất cả rows cũ, server lưu giá trị missing trong catalog metadata. Khi đọc một tuple cũ chưa có physical attribute này, executor trả về missing value.

Với bảng lớn, câu lệnh có thể hoàn tất rất nhanh so với rewrite toàn bộ heap.

### 5.3. Điều kiện chính

Fast default áp dụng khi:

- PostgreSQL version có hỗ trợ (11 trở lên).
- Câu lệnh là ADD COLUMN có default expression không volatile.
- Không có một yếu tố khác trong cùng ALTER TABLE buộc table rewrite.

Không áp dụng kết luận “PostgreSQL 11+ thì ADD COLUMN luôn nhanh” cho mọi DDL. Kiểm tra toàn bộ subcommands và kiểu column.

### 5.4. attmissingval và atthasmissing

PostgreSQL lưu thông tin missing value trong catalog pg_attribute:

- atthasmissing: cho biết attribute có missing value metadata.
- attmissingval: giá trị dùng khi tuple cũ chưa có physical attribute.

Đây là chi tiết implementation hữu ích để hiểu fast default. Ứng dụng không nên phụ thuộc trực tiếp vào catalog internals như một API ổn định.

### 5.5. Đọc rows cũ

Với fast default, row cũ chưa được rewrite vẫn trả về giá trị default logic khi SELECT. Người dùng SQL nhìn thấy column như đã có giá trị, dù giá trị chưa được ghi thành datum riêng trong từng tuple cũ.

### 5.6. INSERT rows mới

Rows được INSERT sau khi column được thêm sẽ nhận giá trị default và lưu dữ liệu theo tuple layout hiện hành. Missing value metadata chủ yếu hỗ trợ rows cũ được tạo trước khi column tồn tại.

### 5.7. UPDATE rows cũ

Khi row cũ được UPDATE và tuple được ghi lại theo layout mới, giá trị missing logic có thể được materialize vào tuple mới. Không nên dựa vào việc mọi row sẽ giữ nguyên atthasmissing sau các hoạt động rewrite/maintenance.

### 5.8. DROP DEFAULT sau fast default

```sql
ALTER TABLE large_orders
ALTER COLUMN source DROP DEFAULT;
```

Thao tác này chỉ bỏ default cho các rows mới. Các rows cũ vẫn phải đọc được giá trị missing đã lưu trong metadata. DROP DEFAULT không làm chúng trở thành NULL.

### 5.9. Table rewrite về sau

Một operation khác buộc rewrite table có thể materialize missing values vào tuple mới và xóa nhu cầu metadata missing cho các rows đó. Vì thế atthasmissing có thể thay đổi sau rewrite/rewriting operations.

### 5.10. Lợi ích và giới hạn

Fast default giảm mạnh chi phí ghi dữ liệu cho một số ADD COLUMN, nhưng:

- ALTER TABLE vẫn cần lock.
- DDL có thể chờ lock lâu nếu transactions khác đang giữ relation lock.
- Volatile default vẫn có thể rewrite.
- Một subcommand khác trong cùng ALTER có thể làm thao tác nặng.
- Indexes, constraints, partitioning và replication vẫn cần được tính đến.

## 6. Ma trận hành vi theo phiên bản

### 6.1. Ma trận khái quát

| Phiên bản | ADD COLUMN không default | ADD COLUMN với constant/non-volatile DEFAULT | ADD COLUMN với volatile DEFAULT |
| --- | --- | --- | --- |
| PostgreSQL 10 trở về trước | Thường metadata-only, không cần heap rewrite chỉ vì thêm nullable column. | Trên bảng có rows thường rewrite để materialize default. | Rewrite để tính giá trị cho từng row. |
| PostgreSQL 11 trở lên | Metadata-only đối với thao tác thêm nullable column đơn giản. | Fast default: lưu missing value metadata, tránh rewrite heap chỉ vì default. | Cần rewrite để tính giá trị volatile cho các rows cũ. |

Đây là ma trận cho trường hợp ADD COLUMN cơ bản. Các yếu tố khác như generated stored columns, type conversion, constraints, partitioning hoặc nhiều subcommands có thể thay đổi kết quả.

### 6.2. PostgreSQL 9.6 và 10

Với các phiên bản này, thêm column nullable không default thường là thao tác metadata. Khi có default non-NULL trên bảng có dữ liệu, server phải rewrite để mọi tuple có giá trị cột mới.

Nếu migration cần hỗ trợ các phiên bản này, cân nhắc thêm column nullable không default trước, rồi backfill theo batch, sau đó đặt default cho INSERT mới.

### 6.3. PostgreSQL 11

Đây là mốc fast default. Một constant hoặc non-volatile expression có thể được lưu trong metadata thay vì rewrite toàn bộ bảng.

### 6.4. PostgreSQL 12–18

Fast default tiếp tục là hành vi chuẩn cho non-volatile default. Tuy nhiên, các tính năng khác của ALTER TABLE, generated columns, partitioning và constraint validation đã phát triển qua các releases. Đọc documentation đúng major version, nhất là khi migration dùng nhiều subcommands.

### 6.5. Kiểm tra server version

```sql
SHOW server_version;
SHOW server_version_num;
```

server_version_num là integer thuận tiện cho migration logic. Không dựa vào version của psql client để suy ra server behavior.

### 6.6. Version của primary và replicas

Trong physical streaming replication, primary và standby thuộc cùng PostgreSQL major version trong một cluster thông thường. Trong quá trình major upgrade/migration, xác định rõ node nào đang phục vụ và version nào thực sự thực thi DDL.

### 6.7. Version-specific migration

Nếu ứng dụng hỗ trợ nhiều major versions, có thể:

- Dùng chiến lược nullable-add + batched backfill + SET DEFAULT chung cho mọi version.
- Dùng fast default trực tiếp trên PostgreSQL 11+ nếu semantics phù hợp.
- Có migration branch riêng khi lợi ích performance đủ lớn và deployment system quản lý version rõ ràng.

### 6.8. Không dựa vào version string của môi trường dev

Migration chạy trên production server version thực tế. Kiểm tra version ở pipeline/deployment target và staging. Một dev database PostgreSQL 16 không chứng minh migration an toàn trên production PostgreSQL 10.

### 6.9. Kiểm tra documentation theo major

Các trang documentation theo major version phản ánh behavior tương ứng. Dùng tài liệu current chỉ khi target version thực sự là release đang hỗ trợ.

### 6.10. Compatibility test

Tạo disposable databases cho từng major cần hỗ trợ, nạp dữ liệu đủ lớn, chạy migration và ghi thời gian, lock waits, table size, WAL volume và kết quả SELECT. Đây là cách xác minh hành vi thực tế tốt hơn chỉ dựa vào tên migration.

## 7. Table rewrite và chi phí vật lý

### 7.1. Table rewrite là gì?

Table rewrite tạo lại physical representation của table, thường đọc các tuples cũ và ghi tuples mới theo schema/values mới. Với bảng lớn, operation có thể:

- Đọc và ghi lượng dữ liệu gần bằng kích thước heap.
- Sinh nhiều WAL tùy operation/recovery settings.
- Cần thêm disk space tạm thời.
- Giữ lock mạnh và chặn concurrent DML.
- Làm replication lag hoặc backup workload tăng.

### 7.2. Metadata-only change

Một metadata-only change cập nhật catalog mà không phải ghi lại toàn bộ heap. Fast default là ví dụ. Nhưng metadata-only không đồng nghĩa zero-cost: vẫn có catalog updates, lock acquisition, WAL/catalog work và invalidation.

### 7.3. Ước lượng disk headroom

Trước một rewrite, kiểm tra:

- Heap size và TOAST size.
- Index sizes.
- Available disk trên tablespace/filesystem.
- WAL filesystem capacity và archive throughput.
- Replication slots có giữ WAL lâu không.
- Backup/replica lag.

Không giả định cần đúng gấp đôi disk size; nhu cầu phụ thuộc operation, index handling, tablespace và concurrent writes.

### 7.4. WAL và replicas

DDL rewrite có thể tạo lượng WAL đáng kể. Physical replicas phải replay WAL; logical subscribers có behavior riêng theo DDL management. Theo dõi WAL generation, archive backlog và replay lag trong migration.

### 7.5. Lock duration

Một rewrite lớn thường giữ lock ngăn DML trong thời gian thực thi. Một ALTER TABLE metadata-only có thể thực hiện rất nhanh sau khi lấy được lock, nhưng nếu transaction khác giữ lock lâu, ALTER vẫn phải chờ.

### 7.6. Table rewrite trong cùng transaction

DDL nằm trong transaction có thể giữ locks đến khi transaction kết thúc. Tránh để application migration transaction tiếp tục chạy các bước chậm sau ALTER TABLE; điều đó kéo dài thời gian lock được giữ.

### 7.7. VACUUM và rewrite không giống nhau

VACUUM thường thu hồi/reuse dead tuple space trong relation; nó không tương đương với table rewrite để materialize cột mới. VACUUM FULL, CLUSTER hoặc một số ALTER TYPE có thể rewrite. Hiểu đúng operation thay vì dùng từ “vacuum” cho mọi cleanup.

### 7.8. TOAST

Rows có values lớn có thể lưu out-of-line trong TOAST relation. Rewrite hoặc data transformation có thể ảnh hưởng cả heap và TOAST storage. Ước lượng dựa trên toàn bộ relation set, không chỉ heap file.

### 7.9. Indexes

ADD COLUMN nullable hoặc fast default không tự động cần rebuild mọi index hiện có vì index không chứa column mới. Nếu migration tạo index trên column mới, đó là operation riêng có chi phí scan/build và lock riêng.

### 7.10. Đo trước production

Thử migration trên bản staging có kích thước và data distribution gần production. Ghi duration, lock wait, WAL bytes, replica lag và disk usage. Bảng nhỏ trong dev không mô phỏng được chi phí của bảng hàng trăm GB.

## 8. Lock khi thay đổi schema

### 8.1. ADD COLUMN thường cần ACCESS EXCLUSIVE

ALTER TABLE ADD COLUMN thông thường lấy ACCESS EXCLUSIVE lock trên table. Đây là lock mạnh, xung đột với hầu hết table-level locks khác, bao gồm locks được dùng bởi SELECT thông thường.

Ngay cả khi fast default làm phần catalog update rất nhanh, câu lệnh vẫn phải chờ lấy lock. Nếu một transaction dài đang giữ lock trên bảng, migration có thể nằm chờ và tạo hàng đợi cho các sessions khác.

### 8.2. Lock wait nguy hiểm hơn thời gian thực thi

Một ALTER TABLE có thể chỉ cần vài milliseconds sau khi lấy lock, nhưng chờ nhiều phút vì transaction khác chưa commit. Khi ALTER TABLE đang chờ ACCESS EXCLUSIVE, các requests mới cũng có thể xếp hàng phía sau tùy lock queue và workload.

Vì vậy cần theo dõi cả thời gian lock acquisition lẫn thời gian command chạy.

### 8.3. Transaction dài

Một session có thể mở transaction, đọc bảng rồi để idle trước khi commit. Lock relation mà transaction giữ có thể ngăn DDL lấy ACCESS EXCLUSIVE.

Kiểm tra sessions idle in transaction và long-running transactions trước migration. Không chỉ nhìn active queries.

### 8.4. lock_timeout

Đặt giới hạn thời gian chờ lock để migration fail nhanh nếu không lấy được lock:

```sql
SET lock_timeout = '3s';
SET statement_timeout = '2min';

ALTER TABLE public.customers
ADD COLUMN preferred_language text;
```

Nếu không lấy được lock trong 3 giây, statement bị hủy và transaction trở thành aborted nếu đang ở transaction block. Client migration phải xử lý rollback/retry có backoff.

### 8.5. statement_timeout

statement_timeout giới hạn thời gian statement chạy tổng thể, bao gồm cả thời gian chờ lock. Đặt giá trị phù hợp với migration. Với table rewrite lớn, timeout quá ngắn có thể hủy operation giữa chừng; timeout quá dài có thể giữ lock quá lâu.

### 8.6. Kiểm tra lock waits

```sql
SELECT
    a.pid,
    a.usename,
    a.state,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS query_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 160) AS query_text
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

Query này tìm sessions đang bị block và liệt kê PIDs có thể đang chặn chúng. Cần kiểm tra blocker trước khi cancel/terminate; không kill transaction tùy tiện.

### 8.7. Xem relation locks

```sql
SELECT
    a.pid,
    a.state,
    l.mode,
    l.granted,
    c.relname,
    a.query
FROM pg_locks AS l
JOIN pg_class AS c ON c.oid = l.relation
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE c.relname = 'customers'
ORDER BY l.granted, a.pid;
```

Tên bảng có thể tồn tại trong nhiều schemas; bổ sung schema filter khi cần. Catalog query là snapshot và cần quyền xem sessions liên quan.

### 8.8. Migration transaction ngắn

Giữ DDL transaction ngắn. Không chạy data backfill hàng triệu rows trong cùng transaction với ADD COLUMN nếu có thể tách ra. Commit ngay sau metadata change để giải phóng lock.

### 8.9. Retry có kiểm soát

Nếu migration thất bại do lock timeout:

1. Xác nhận transaction đã rollback.
2. Tìm blocker và thời điểm workload thấp hơn.
3. Retry với backoff/jitter.
4. Đặt số lần retry hữu hạn.
5. Ghi log và alert nếu không hoàn thành.

Không lặp tight loop khiến lock queue càng tệ.

### 8.10. DDL vẫn cần change plan

Fast default giảm rewrite nhưng không loại bỏ lock risk. Với bảng critical, migration cần maintenance/change window, lock timeout ngắn, observability và rollback/forward-fix plan.

## 9. NOT NULL và CHECK constraints

### 9.1. Thêm NOT NULL khi table đã có rows

Lệnh sau thường thất bại nếu bảng có dữ liệu và không có default non-NULL:

```sql
ALTER TABLE customers
ADD COLUMN customer_tier text NOT NULL;
```

Các rows hiện tại không có giá trị cho column mới nên sẽ nhận NULL. Cần cung cấp default phù hợp hoặc dùng migration nhiều bước để backfill trước khi đặt NOT NULL.

### 9.2. ADD COLUMN NOT NULL DEFAULT trên PostgreSQL 11+

Trên PostgreSQL 11+, nếu default non-volatile, fast default có thể cung cấp giá trị cho rows cũ mà không rewrite heap chỉ vì default. Column có thể được thêm cùng NOT NULL vì missing value không NULL.

```sql
ALTER TABLE customers
ADD COLUMN customer_tier text NOT NULL DEFAULT 'standard';
```

Điều này không xóa lock requirement. Trên PostgreSQL 10 trở về trước, cùng thao tác trên bảng có dữ liệu có thể rewrite table.

### 9.3. SET NOT NULL sau khi backfill

Nếu column đã tồn tại nullable, cần bảo đảm không còn NULL trước khi đặt NOT NULL:

```sql
SELECT count(*)
FROM customers
WHERE customer_tier IS NULL;

ALTER TABLE customers
ALTER COLUMN customer_tier SET NOT NULL;
```

Nếu còn NULL, SET NOT NULL thất bại. Với bảng lớn, validation scan có thể tốn thời gian; có cách dùng CHECK constraint đã validate để tránh scan lặp lại.

### 9.4. CHECK constraint

CHECK constraint đảm bảo mỗi row được INSERT/UPDATE thỏa biểu thức:

```sql
ALTER TABLE orders
ADD CONSTRAINT orders_total_nonnegative
CHECK (total_amount >= 0);
```

Mặc định, PostgreSQL kiểm tra rows hiện có khi thêm CHECK constraint. Trên bảng lớn, validation scan có thể kéo dài.

### 9.5. NOT VALID

Có thể thêm CHECK constraint bằng NOT VALID:

```sql
ALTER TABLE customers
ADD CONSTRAINT customers_tier_present
CHECK (customer_tier IS NOT NULL) NOT VALID;
```

NOT VALID bỏ qua việc quét và xác nhận toàn bộ rows hiện có tại thời điểm ADD CONSTRAINT. Constraint vẫn được thực thi đối với rows mới và rows được UPDATE sau khi constraint được thêm.

### 9.6. VALIDATE CONSTRAINT

Sau khi backfill và đảm bảo dữ liệu cũ thỏa điều kiện:

```sql
ALTER TABLE customers
VALIDATE CONSTRAINT customers_tier_present;
```

VALIDATE CONSTRAINT quét dữ liệu hiện có để xác nhận constraint. Nó dùng lock nhẹ hơn ADD CONSTRAINT thông thường và cho phép DML thông thường tiếp tục trong quá trình validation theo lock semantics của PostgreSQL.

### 9.7. Dùng CHECK để hỗ trợ SET NOT NULL

PostgreSQL có thể bỏ qua full table scan khi SET NOT NULL nếu đã có CHECK constraint hợp lệ chứng minh column không thể chứa NULL và constraint đó không bị drop trong cùng command:

```sql
ALTER TABLE customers
ADD CONSTRAINT customers_tier_not_null_check
CHECK (customer_tier IS NOT NULL) NOT VALID;

ALTER TABLE customers
VALIDATE CONSTRAINT customers_tier_not_null_check;

ALTER TABLE customers
ALTER COLUMN customer_tier SET NOT NULL;

ALTER TABLE customers
DROP CONSTRAINT customers_tier_not_null_check;
```

Đây là kỹ thuật giảm scan lặp lại. SET NOT NULL vẫn cần lock; kiểm tra PostgreSQL version và behavior cụ thể của constraint trước production.

### 9.8. Backfill trước validation

Nếu rows cũ còn NULL, VALIDATE CONSTRAINT sẽ thất bại. Thực hiện backfill theo batch, kiểm tra NULL count về 0, sau đó mới validate.

### 9.9. CHECK có thể trả NULL

CHECK constraint pass nếu expression trả TRUE hoặc NULL; nó chỉ reject FALSE. Vì vậy CHECK (amount > 0) không thay thế NOT NULL nếu amount có thể NULL. Muốn cấm NULL, dùng NOT NULL hoặc CHECK có điều kiện rõ ràng.

### 9.10. Foreign key cũng hỗ trợ NOT VALID

Foreign key có thể được thêm NOT VALID để tránh kiểm tra toàn bộ historical rows ngay lúc ADD CONSTRAINT; các rows mới/updated vẫn bị enforce. Sau đó VALIDATE CONSTRAINT kiểm tra dữ liệu hiện có. Foreign key có lock behavior và chi phí riêng trên cả referencing/referenced tables; đọc documentation đúng version.

## 10. Backfill dữ liệu theo batch

### 10.1. Vì sao không UPDATE toàn bảng một lần?

Một UPDATE lớn có thể:

- Tạo lượng WAL lớn.
- Tạo nhiều dead tuples và tăng autovacuum work.
- Giữ row locks và transaction snapshot lâu.
- Tăng replication lag.
- Làm phình table/index.
- Gây latency cho ứng dụng.

Với bảng lớn, chia backfill thành batches có commit độc lập giúp kiểm soát tải và có thể pause/resume.

### 10.2. Thêm nullable column trước

```sql
ALTER TABLE customers
ADD COLUMN customer_tier text;
```

Đây thường là metadata change trên các phiên bản PostgreSQL hỗ trợ ADD COLUMN cơ bản, không cần default. DDL vẫn cần ACCESS EXCLUSIVE lock trong thời gian ngắn.

### 10.3. Đặt default cho INSERT mới

```sql
ALTER TABLE customers
ALTER COLUMN customer_tier SET DEFAULT 'standard';
```

Sau bước này, INSERT bỏ qua customer_tier nhận standard. Rows cũ vẫn NULL cho đến khi backfill.

### 10.4. Backfill theo batch bằng khóa chính

Ví dụ dùng id tăng dần và batch size giới hạn:

```sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE customer_tier IS NULL
    ORDER BY id
    LIMIT 5000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET customer_tier = 'standard'
FROM batch
WHERE c.id = batch.id;
```

Chạy statement trong transaction riêng và lặp đến khi không còn rows phù hợp. SKIP LOCKED hữu ích khi nhiều workers backfill song song hoặc tránh chờ rows đang bị ứng dụng khóa; cần thiết kế vòng lặp để không bỏ sót rows bị skip.

### 10.5. Commit mỗi batch

Không bọc toàn bộ vòng lặp trong một transaction khổng lồ. Commit từng batch để giải phóng row locks, giảm thời gian giữ snapshot và cho vacuum xử lý dead tuples dần.

### 10.6. Chọn batch size

Batch 5.000 rows chỉ là ví dụ. Điều chỉnh dựa trên row width, index count, WAL rate, storage throughput, replication lag và application latency. Bắt đầu nhỏ, tăng dần khi có headroom.

### 10.7. Batch theo key range

Nếu có khóa chính tăng dần, có thể chia range:

```sql
UPDATE customers
SET customer_tier = 'standard'
WHERE id > 100000
  AND id <= 105000
  AND customer_tier IS NULL;
```

Lưu checkpoint range đã hoàn thành. Cách này dễ resume nhưng cần xử lý rows mới hoặc rows có IDs nằm ngoài range đã quét.

### 10.8. Backfill từ dữ liệu nghiệp vụ

Không phải mọi row đều có cùng giá trị. Có thể backfill bằng join hoặc mapping:

```sql
UPDATE orders AS o
SET fulfillment_region = c.region_code
FROM customers AS c
WHERE c.id = o.customer_id
  AND o.fulfillment_region IS NULL;
```

Với bảng lớn, chia theo orders primary key và kiểm tra cardinality/uniqueness của join để không tạo kết quả không xác định.

### 10.9. Giảm tác động tới replica

Theo dõi replay lag và WAL archive. Tạm dừng hoặc giảm batch size nếu replica lag vượt ngưỡng vận hành. Không để replication slots giữ WAL đến khi đầy disk.

### 10.10. Hoàn tất backfill

```sql
SELECT count(*) AS remaining_nulls
FROM customers
WHERE customer_tier IS NULL;
```

Chỉ chuyển sang validation/NOT NULL khi kết quả bằng 0 và ứng dụng đã ghi giá trị hợp lệ cho mọi row mới.

## 11. Expand-contract migration cho ứng dụng

### 11.1. Vì sao cần expand-contract?

Trong rolling deployment, phiên bản ứng dụng cũ và mới có thể cùng chạy trong một khoảng thời gian. Nếu DDL ngay lập tức yêu cầu column mới NOT NULL hoặc xóa column cũ, instance cũ có thể lỗi.

Expand-contract thêm schema tương thích trước, triển khai code có khả năng dùng schema mới, backfill/verify, rồi mới siết constraint hoặc bỏ schema cũ.

### 11.2. Giai đoạn expand

1. ADD COLUMN nullable, thường không default nếu cần hỗ trợ nhiều server versions.
2. Đặt default cho INSERT mới nếu phù hợp.
3. Deploy code đọc/ghi column mới nhưng vẫn tương thích với rows chưa backfill.
4. Theo dõi lỗi và đảm bảo mọi app instances đã nâng cấp.

### 11.3. Giai đoạn backfill

Backfill historical rows theo batches. Kiểm tra dữ liệu, null count, uniqueness/business rules và replica lag. Không siết NOT NULL trước khi tất cả writers đã gửi giá trị hợp lệ.

### 11.4. Giai đoạn validate

Thêm CHECK NOT VALID, validate sau khi backfill và sau đó SET NOT NULL nếu yêu cầu schema cần. Giữ CHECK tạm nếu cần chứng minh điều kiện trong quá trình chuyển đổi.

### 11.5. Giai đoạn contract

Khi tất cả application versions đã dùng schema mới và không còn đọc/ghi legacy column, mới bỏ compatibility code hoặc drop column cũ trong migration riêng.

### 11.6. Backward compatibility

Code mới nên chịu được:

- Column chưa có ở một số environments trong quá trình rollout.
- Historical rows còn NULL trong giai đoạn backfill.
- Default chưa được deploy trên mọi database.
- Một số app instances cũ vẫn INSERT không cung cấp column mới.

Định nghĩa chính xác contract giữa code và schema ở từng bước.

### 11.7. Không dùng DEFAULT để che dữ liệu sai

Default chỉ là giá trị mặc định hợp lệ theo business semantics. Không đặt một placeholder như unknown hoặc 0 chỉ để migration qua NOT NULL nếu ứng dụng coi nó là dữ liệu thật.

### 11.8. Feature flags

Có thể bật đọc/ghi column mới bằng feature flag sau khi schema đã được expand và backfill đủ. Giữ flag rollback để quay về behavior cũ nếu validation phát hiện lỗi.

### 11.9. Migration độc lập

Tách DDL nhanh, backfill dài và constraint validation thành các migration/jobs riêng. Điều này giúp retry, observability và rollback dễ hơn.

### 11.10. Contract chỉ sau khi quan sát

Không drop legacy column ngay sau khi deploy code mới. Đợi đủ thời gian để xác nhận không còn old binaries, scheduled jobs, reports, integrations hoặc ad hoc SQL phụ thuộc schema cũ.

## 12. Các trường hợp cột đặc biệt và cấu trúc bảng

### 12.1. Generated stored columns

Generated stored column lưu kết quả của biểu thức generated trong row. Khi thêm một stored generated column vào bảng đã có rows, PostgreSQL phải tính giá trị cho dữ liệu hiện có; thao tác này có thể cần table rewrite và có chi phí lớn.

```sql
ALTER TABLE products
ADD COLUMN normalized_sku text
GENERATED ALWAYS AS (upper(trim(sku))) STORED;
```

Generated columns được giới thiệu ở PostgreSQL 12 dưới dạng stored. Các phiên bản mới có thể có thêm generated-column modes; kiểm tra documentation của đúng major version. Không áp dụng fast-default assumption cho generated stored column.

### 12.2. Identity columns

Identity column dùng sequence nội bộ để tự sinh giá trị khi INSERT:

```sql
CREATE TABLE shipment_items (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description text
);
```

Thêm identity vào một column đã tồn tại có semantics khác với thêm default constant thông thường. Nếu bảng đã có rows và cần gán identity values cho chúng, hãy thiết kế backfill/sequence alignment rõ ràng, kiểm tra version và test trên bản sao dữ liệu trước khi chạy.

Không giả định việc thêm identity tự động giải quyết mọi historical NULLs hoặc sequence collision.

### 12.3. Serial-style sequence default

Một cột có default gọi nextval là volatile:

```sql
ALTER TABLE legacy_events
ADD COLUMN generated_id bigint DEFAULT nextval('legacy_events_id_seq');
```

Trên bảng lớn, volatile default có thể buộc rewrite để tạo giá trị riêng cho từng row cũ. Ngoài ra cần bảo đảm sequence tồn tại, ownership/permissions đúng và sequence được đặt sau giá trị lớn nhất đã backfill.

### 12.4. Default phụ thuộc extension hoặc user-defined type

Default có thể gọi function/operator/cast do extension cung cấp. Volatility và behavior của function/type ảnh hưởng fast-default eligibility. Kiểm tra extension version trên mọi môi trường và không giả định cùng một cast có semantics giống nhau giữa major versions.

### 12.5. Partitioned tables

Khi thêm column vào partitioned parent table, PostgreSQL áp dụng thay đổi tới partitions theo rules của version. Số lượng partitions lớn có thể làm DDL phải lấy locks trên nhiều relations và kéo dài lock acquisition.

Kiểm tra:

- Partition count và nesting.
- Detached/attached partitions.
- Partition-specific defaults hoặc constraints.
- Có partition nào đã drift schema không.
- Lock conflicts trên child relations.

### 12.6. Thêm cột cho một partition

Nếu thay đổi chỉ nhắm vào một partition, phải cân nhắc schema consistency với parent và các partitions khác. Một partition riêng có column khác có thể gây khó khăn cho queries qua parent và các thao tác attach/detach.

Đừng dùng ALTER TABLE ONLY trên parent hoặc child nếu chưa hiểu inheritance/partition semantics của command.

### 12.7. Inheritance

Với traditional table inheritance, ALTER TABLE trên parent thường có thể tác động tới descendants trừ khi dùng ONLY cho operation hỗ trợ. Column có thể inherited; việc thêm cùng tên/kiểu vào child có thể gây conflict.

### 12.8. Foreign tables và partitioned foreign tables

Foreign tables/FDW có capability và DDL behavior phụ thuộc FDW. ALTER TABLE metadata ở local catalog không nhất thiết tạo column ở remote system. Kiểm tra remote schema và FDW support trước khi migrate.

### 12.9. Temporary và unlogged tables

Temporary tables thuộc session và unlogged tables có WAL/recovery semantics khác ordinary logged tables. DDL trên chúng có chi phí và persistence khác; đừng dùng benchmark trên temp/unlogged table để suy ra production logged table behavior.

### 12.10. Table type changes đi kèm ADD COLUMN

Nếu cùng migration vừa thêm cột vừa đổi type/cast một cột hiện có, phần type change có thể buộc rewrite dù ADD COLUMN mới đủ điều kiện fast default. Tách các thay đổi để xác định rõ operation nào tạo chi phí và lock.

## 13. Migration recipes theo phiên bản

### 13.1. Recipe A: PostgreSQL 11+ và constant default phù hợp

Nếu tất cả rows cũ có thể nhận cùng một giá trị business hợp lệ:

```sql
ALTER TABLE public.orders
ADD COLUMN source_system text NOT NULL DEFAULT 'legacy';
```

Đây là trường hợp fast default điển hình từ PostgreSQL 11. Dù không rewrite heap chỉ vì default, câu lệnh vẫn cần ACCESS EXCLUSIVE lock và cần lock timeout/monitoring.

### 13.2. Recipe B: hỗ trợ PostgreSQL 10 trở về trước

Dùng nullable-add, đặt default riêng, backfill theo batch và sau đó đặt NOT NULL:

```sql
-- Migration 1: quick schema expansion
ALTER TABLE public.orders
ADD COLUMN source_system text;

-- Migration 2: default for future inserts
ALTER TABLE public.orders
ALTER COLUMN source_system SET DEFAULT 'legacy';
```

Tiếp theo deploy application code tương thích, backfill rows cũ theo batch, validate không còn NULL rồi mới SET NOT NULL. Chiến lược này tránh table rewrite lớn ngay tại thời điểm ADD COLUMN có default trên các server cũ.

### 13.3. Recipe C: giá trị khác nhau cho từng historical row

Nếu cần derive giá trị từ dữ liệu từng row, thêm column nullable trước:

```sql
ALTER TABLE public.events
ADD COLUMN event_day date;
```

Backfill theo batch từ timestamp hiện có:

```sql
UPDATE public.events
SET event_day = created_at::date
WHERE id > 100000
  AND id <= 105000
  AND event_day IS NULL;
```

Đừng dùng một constant default nếu business rule yêu cầu mỗi row có giá trị riêng theo historical data.

### 13.4. Recipe D: default now cho rows cũ

Nếu yêu cầu là mọi historical row có cùng mốc migration timestamp, trên PostgreSQL 11+:

```sql
ALTER TABLE audit_events
ADD COLUMN migrated_at timestamptz NOT NULL DEFAULT now();
```

now() là stable, không volatile. Rows cũ nhìn thấy cùng transaction timestamp của migration; INSERT sau đó nhận timestamp của transaction insert. Nếu cần timestamp thực tế riêng cho từng historical row, đây không phải semantics đúng.

### 13.5. Recipe E: volatile default nhưng cần unique/random per row

Không chạy volatile ADD COLUMN trực tiếp trên bảng rất lớn nếu chưa chấp nhận rewrite. Thay vào đó:

1. Thêm column nullable không default.
2. Deploy writers tạo giá trị cho rows mới.
3. Backfill historical rows theo batch bằng function/sequence có semantics mong muốn.
4. Kiểm tra uniqueness/distribution.
5. Đặt constraint/default cần thiết.

### 13.6. Recipe F: cột NOT NULL nhưng không có giá trị mặc định nghiệp vụ

Nếu ứng dụng phải cung cấp giá trị thật cho mỗi row:

1. Add nullable column.
2. Deploy code mới ghi giá trị.
3. Backfill historical rows từ nguồn dữ liệu nghiệp vụ.
4. Validate CHECK NOT VALID.
5. SET NOT NULL.

Không đặt giá trị placeholder chỉ để thỏa constraint.

### 13.7. Recipe G: đổi default nhưng giữ historical values

```sql
ALTER TABLE orders
ALTER COLUMN priority SET DEFAULT 10;
```

Các rows hiện tại không đổi. Nếu muốn nâng priority cho một nhóm historical rows, chạy UPDATE có WHERE cụ thể và kiểm tra business rule riêng.

### 13.8. Recipe H: bỏ default nhưng giữ historical values

```sql
ALTER TABLE orders
ALTER COLUMN priority DROP DEFAULT;
```

Các rows đã có priority vẫn giữ nguyên. Ứng dụng mới phải gửi giá trị tường minh hoặc chấp nhận NULL nếu column nullable.

### 13.9. Recipe I: nhiều cột có semantics khác nhau

Không nhất thiết gộp tất cả columns vào một ALTER:

- Cột constant default phù hợp có thể thêm trực tiếp trên PG11+.
- Cột cần per-row derivation nên add nullable và backfill.
- Cột NOT NULL cần data validation.
- Cột generated stored có thể cần rewrite.

Tách migration giúp đánh giá lock và rollback từng phần.

### 13.10. Recipe J: migration phải chạy lại được

IF NOT EXISTS có thể tránh duplicate-column error, nhưng pipeline cần kiểm tra schema state sau mỗi lần chạy. Nếu migration bị dừng giữa nhiều bước, xác định step đã commit và resume từ checkpoint; không giả định cả file migration atomic nếu tool chia transaction.

## 14. Kiểm tra catalog và dữ liệu sau migration

### 14.1. Kiểm tra column metadata

```sql
SELECT
    a.attname,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull,
    a.atthasdef,
    a.atthasmissing,
    a.attmissingval
FROM pg_attribute AS a
WHERE a.attrelid = 'public.orders'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

atthasmissing/attmissingval giúp quan sát fast-default metadata trên các versions có catalog fields này. Catalog internals có thể thay đổi; query này dùng cho diagnosis, không làm application contract.

### 14.2. Kiểm tra default expression

```sql
SELECT
    column_name,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_system';
```

Column default mô tả expression dùng cho rows mới; nó không nhất thiết hiển thị missing-value metadata của historical rows.

### 14.3. Kiểm tra null count

```sql
SELECT
    count(*) FILTER (WHERE source_system IS NULL) AS null_rows,
    count(*) AS total_rows
FROM public.orders;
```

Với bảng rất lớn, COUNT(*) có thể tốn scan. Chạy trong thời điểm phù hợp hoặc dùng validation constraint đã được PostgreSQL xác nhận. Không dùng ước lượng statistics làm bằng chứng tuyệt đối cho NOT NULL.

### 14.4. Kiểm tra constraints

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
```

convalidated cho biết constraint đã được validate historical rows hay vẫn ở trạng thái NOT VALID.

### 14.5. Kiểm tra kích thước relation

```sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders')) AS heap_size,
    pg_size_pretty(pg_table_size('public.orders')) AS table_size,
    pg_size_pretty(pg_total_relation_size('public.orders')) AS total_size;
```

So sánh trước/sau để tìm dấu hiệu rewrite hoặc growth bất thường. Kích thước có thể thay đổi vì concurrent DML, vacuum và index changes; cần đo trong điều kiện tương đương.

### 14.6. Kiểm tra migration đang chờ lock

Xem pg_stat_activity, pg_locks, wait events và blocking PIDs. Ghi lại transaction start time của blocker. Không kết luận migration đã treo chỉ từ thời gian statement dài; có thể nó đang chờ lock.

### 14.7. Kiểm tra replica

Trên primary, kiểm tra pg_stat_replication; trên standby, kiểm tra pg_stat_wal_receiver và replay LSN. Sau DDL rewrite/backfill, xác nhận replicas đã replay WAL và không có lag vượt SLA.

### 14.8. Kiểm tra application behavior

Thử INSERT bỏ qua column, INSERT chỉ định DEFAULT, INSERT gửi giá trị tường minh và UPDATE row cũ. Kiểm tra ORM/schema cache, prepared statements, serializers và report queries.

### 14.9. Kiểm tra quyền

ALTER TABLE yêu cầu quyền phù hợp trên relation; default expression có thể gọi functions/sequences mà migration role cần quyền truy cập. Kiểm tra ownership và grants trên sequence/extension objects.

### 14.10. Lưu migration evidence

Ghi server_version_num, migration command, start/end time, lock wait, relation sizes, WAL/archive lag, constraint state và null count. Đây là bằng chứng để so sánh giữa staging và production.

## 15. Chẩn đoán các tình huống thường gặp

### 15.1. ADD COLUMN chạy lâu

Kiểm tra:

1. Server major version.
2. Default expression có volatile không.
3. Có generated stored column hoặc type change trong cùng ALTER không.
4. Có nhiều partitions/descendants cần lock không.
5. Statement đang chờ lock hay đang thực hiện rewrite.

Xem wait_event, pg_locks và blocking PIDs để phân biệt lock wait với I/O-heavy rewrite.

### 15.2. ADD COLUMN fast default nhưng vẫn bị block

Fast default tránh heap rewrite cho trường hợp phù hợp, nhưng ALTER TABLE vẫn cần ACCESS EXCLUSIVE. Tìm transaction giữ relation lock, idle-in-transaction sessions và prepared transactions chưa kết thúc.

### 15.3. Migration nhanh ở staging nhưng chậm production

Staging có thể ít rows, ít concurrent sessions và không có transaction dài. So sánh table/TOAST/index sizes, partition count, lock queue, workload và storage. Không chỉ so server CPU/RAM.

### 15.4. Migration trên PostgreSQL 10 tốn hàng giờ

Nếu ADD COLUMN có non-NULL DEFAULT trên bảng lớn, rewrite là lời giải thích khả dĩ. Xác nhận bằng server version, I/O, relation size và lock state. Với lần triển khai tiếp theo, dùng nullable-add + backfill batches + SET DEFAULT/NOT NULL.

### 15.5. Default now cho rows cũ không giống thời điểm tạo row

now() trong fast default cung cấp một timestamp chung tại transaction migration cho historical rows. Nếu business cần thời gian thật của từng row, derive từ column lịch sử hoặc nguồn audit rồi backfill.

### 15.6. Đổi default nhưng giá trị cũ không đổi

Đây là behavior đúng. SET DEFAULT chỉ thay default cho rows được tạo/updated về sau khi column bị bỏ qua. UPDATE historical rows riêng nếu yêu cầu business cần thay dữ liệu hiện có.

### 15.7. DROP DEFAULT khiến INSERT lỗi

Sau DROP DEFAULT, INSERT bỏ qua column nullable sẽ nhận NULL; nếu column NOT NULL, INSERT đó lỗi. Kiểm tra application writers và deploy code gửi giá trị trước khi bỏ default.

### 15.8. SET NOT NULL thất bại

Kiểm tra NULL count, concurrent writers, CHECK constraint state và backfill completeness. Có thể backfill đã hoàn tất một lần nhưng ứng dụng cũ vẫn tạo NULL sau đó. Đặt default hoặc deploy writers trước khi validate.

### 15.9. VALIDATE CONSTRAINT thất bại

Constraint có thể không thỏa trên một số historical rows. Tìm rows vi phạm bằng query tương ứng, sửa dữ liệu theo business rules rồi validate lại. Không xóa constraint chỉ để migration xanh nếu nó bảo vệ invariant quan trọng.

### 15.10. Backfill chạy mãi

Kiểm tra index cho predicate/range, batch size, rows bị SKIP LOCKED, deadlocks, WAL rate và autovacuum. Nếu mỗi batch scan lại toàn bảng vì thiếu index hoặc key range không hiệu quả, tối ưu cách chọn rows.

### 15.11. Replica lag tăng

Backfill/rewrites tạo WAL và workload replay. Giảm batch size, thêm pause giữa batches, kiểm tra standby I/O/CPU và archive throughput. Đừng để slots giữ WAL làm đầy filesystem.

### 15.12. Disk tăng sau backfill

UPDATE tạo dead tuples và index churn. Kiểm tra autovacuum progress, table bloat, index size và long-running snapshots ngăn vacuum cleanup. VACUUM thường có thể tái sử dụng space; VACUUM FULL cần rewrite và lock mạnh.

### 15.13. Ứng dụng lỗi sau ADD COLUMN

Một số ORM/driver cache schema, dùng SELECT * với mapping theo ordinal, hoặc INSERT positional không liệt kê columns. Kiểm tra generated SQL, prepared statements, row decoders và code assumptions về column count/order.

### 15.14. IF NOT EXISTS che schema drift

Nếu column đã tồn tại với kiểu/default sai, IF NOT EXISTS không sửa nó. So sánh catalog với desired schema và viết migration reconciliation rõ ràng.

### 15.15. Partition attach thất bại sau migration

Kiểm tra column definitions, constraints và defaults của partition. Một child table có schema không khớp hoặc dữ liệu vi phạm partition constraints có thể không attach được. Kiểm tra trước bằng validation queries trên child.

### 15.16. Generated column không dùng fast default

Stored generated columns cần tính giá trị cho historical rows. Tách operation, ước lượng rewrite cost và cân nhắc backfill vào ordinary column nếu cần triển khai online theo nhiều bước.

### 15.17. Sequence collision sau backfill

Nếu backfill ID bằng sequence hoặc gán ID thủ công, đặt sequence ở giá trị an toàn sau maximum existing ID và kiểm tra concurrent inserts. Tránh để sequence phát ra ID đã tồn tại.

### 15.18. Migration rollback khó

ADD COLUMN có thể rollback bằng DROP COLUMN trong một số trường hợp, nhưng sau khi ứng dụng ghi dữ liệu mới, drop column sẽ mất dữ liệu đó. Lập kế hoạch forward-fix và backup/recovery trước khi destructive contract changes.

## 16. Những sai lầm thường gặp

### 16.1. Nghĩ ADD COLUMN luôn metadata-only

Default volatile, generated stored columns, type conversions hoặc subcommands khác có thể buộc rewrite. Xác định version và expression trước khi chạy.

### 16.2. Nghĩ PostgreSQL 11+ làm mọi ADD COLUMN nhanh

Fast default chỉ áp dụng cho non-volatile defaults trong điều kiện phù hợp. Nó không xóa lock requirement và không loại bỏ rewrite do các thao tác khác.

### 16.3. Dùng clock_timestamp vì muốn “thời gian hiện tại”

clock_timestamp volatile và có thể buộc tính riêng từng row cũ. Nếu muốn một mốc chung của migration, cân nhắc now() sau khi xác nhận business semantics.

### 16.4. Đánh dấu user-defined function STABLE để tránh rewrite

Volatility là correctness contract. Khai báo sai có thể làm PostgreSQL đánh giá biểu thức sai và tạo dữ liệu không đúng.

### 16.5. Nghĩ SET DEFAULT backfill historical rows

SET DEFAULT chỉ ảnh hưởng INSERT/UPDATE về sau. Historical rows cần UPDATE/backfill riêng.

### 16.6. Nghĩ DROP DEFAULT xóa giá trị cũ

DROP DEFAULT chỉ bỏ expression cho tương lai; dữ liệu đã có vẫn giữ nguyên.

### 16.7. Gửi NULL thay vì DEFAULT

INSERT explicit NULL không kích hoạt default. Nếu column NOT NULL, statement bị từ chối.

### 16.8. Thêm NOT NULL trước khi backfill

Historical NULLs hoặc writers cũ có thể làm migration thất bại. Expand schema, deploy writers, backfill, validate rồi mới SET NOT NULL.

### 16.9. UPDATE toàn bảng trong một transaction

Có thể tạo WAL/dead tuples lớn, giữ locks/snapshot lâu và gây replica lag. Chia batches có commit độc lập.

### 16.10. Quên lock timeout

Một DDL metadata-only vẫn có thể chờ ACCESS EXCLUSIVE và tạo lock queue. Đặt lock_timeout hợp lý và kiểm tra blockers.

### 16.11. Gộp DDL nhanh với rewrite nặng

Một subcommand nặng trong ALTER TABLE nhiều subcommands có thể khiến cả command mang chi phí lớn. Tách operations để quản lý lock/rewrite.

### 16.12. Test trên bảng nhỏ

Bảng vài nghìn rows không mô phỏng lock contention, rewrite duration, WAL, TOAST và replica lag của production. Test trên dataset gần thực tế.

### 16.13. Dựa vào psql version

Client version không quyết định server DDL behavior. Dùng SHOW server_version/server_version_num trên target.

### 16.14. Quên application compatibility

Schema có thể đúng nhưng ứng dụng lỗi vì SELECT *, ORM metadata cache, positional INSERT hoặc old binaries. Dùng expand-contract rollout.

### 16.15. Tin IF NOT EXISTS là migration idempotent hoàn chỉnh

Nó chỉ bỏ qua duplicate column name, không xác nhận type/default/constraints. Kiểm tra schema state sau mỗi bước.

### 16.16. Dùng placeholder default sai nghiệp vụ

Giá trị mặc định giả có thể trở thành dữ liệu thật và làm báo cáo sai. Chọn semantics hoặc backfill từ nguồn nghiệp vụ.

### 16.17. Không theo dõi replication

DDL rewrite/backfill có thể tạo WAL backlog. Theo dõi replicas, archive và slot retention trong toàn bộ migration.

### 16.18. Drop CHECK quá sớm

Nếu CHECK đang là bằng chứng để SET NOT NULL bỏ scan hoặc bảo vệ writers trong rollout, chỉ drop khi constraint NOT NULL đã được áp dụng và mọi writers tuân thủ.

### 16.19. Không kiểm tra partitions

Parent/child schema drift có thể gây attach failures hoặc query errors. Kiểm tra tất cả partitions và inheritance descendants.

### 16.20. Không lưu evidence

Không ghi version, command, lock wait, duration và data checks thì khó giải thích khác biệt giữa staging và production. Lưu đầy đủ migration evidence.

## 17. Labs thực hành

Các lab nên chạy trên database disposable. Tạo dữ liệu lớn vừa đủ để thấy khác biệt; không chạy table rewrite hoặc backfill stress trên production.

### Lab 1. Thêm cột không default

#### Bước 1. Tạo bảng

```sql
CREATE TABLE add_column_lab AS
SELECT
    g::bigint AS id,
    md5(g::text) AS payload
FROM generate_series(1, 1000000) AS g;

ALTER TABLE add_column_lab ADD PRIMARY KEY (id);
```

#### Bước 2. Ghi kích thước

```sql
SELECT
    pg_relation_size('add_column_lab') AS heap_bytes,
    pg_total_relation_size('add_column_lab') AS total_bytes;
```

#### Bước 3. Thêm column nullable

```sql
ALTER TABLE add_column_lab
ADD COLUMN note text;
```

#### Bước 4. Kiểm tra

```sql
SELECT count(*) AS rows,
       count(note) AS nonnull_notes
FROM add_column_lab;
```

Kỳ vọng rows hiện tại vẫn có note NULL.

### Lab 2. So sánh default non-volatile

#### Bước 1. Tạo bảng mới

```sql
CREATE TABLE fast_default_lab AS
SELECT g::bigint AS id
FROM generate_series(1, 1000000) AS g;
```

#### Bước 2. Ghi thời gian và size

Ghi thời gian bắt đầu, relation size và server_version_num.

#### Bước 3. Thêm constant default

```sql
ALTER TABLE fast_default_lab
ADD COLUMN source text DEFAULT 'import';
```

#### Bước 4. Đọc historical rows

```sql
SELECT source, count(*)
FROM fast_default_lab
GROUP BY source;
```

Trên PostgreSQL 11+, đây là fast-default candidate. Quan sát duration và atthasmissing nếu catalog hỗ trợ.

### Lab 3. Volatile default trên disposable table

#### Bước 1. Tạo bảng thử riêng

```sql
CREATE TABLE volatile_default_lab AS
SELECT g::bigint AS id
FROM generate_series(1, 100000) AS g;
```

#### Bước 2. Thêm random default

```sql
ALTER TABLE volatile_default_lab
ADD COLUMN random_value double precision DEFAULT random();
```

#### Bước 3. Kiểm tra kết quả

```sql
SELECT count(*), count(DISTINCT random_value)
FROM volatile_default_lab;
```

Các rows historical được gán giá trị khi rewrite. Dùng bảng disposable vì thao tác có thể đọc/ghi toàn bộ heap.

### Lab 4. DEFAULT khác với UPDATE

#### Bước 1. Thêm column

```sql
ALTER TABLE add_column_lab
ADD COLUMN source_code text;
```

#### Bước 2. Set default

```sql
ALTER TABLE add_column_lab
ALTER COLUMN source_code SET DEFAULT 'legacy';
```

#### Bước 3. So sánh historical và new row

```sql
INSERT INTO add_column_lab (id, payload)
VALUES (2000001, 'new-row');

SELECT id, source_code
FROM add_column_lab
WHERE id IN (1, 2000001);
```

Historical row vẫn NULL; row mới nhận legacy.

### Lab 5. CHECK NOT VALID và validation

#### Bước 1. Thêm constraint chưa validate

```sql
ALTER TABLE add_column_lab
ADD CONSTRAINT add_column_lab_note_nonempty
CHECK (note IS NOT NULL) NOT VALID;
```

#### Bước 2. Quan sát enforcement

Thử INSERT/UPDATE row mới với note NULL; constraint sẽ reject. Constraint chưa validate historical rows.

#### Bước 3. Backfill

```sql
UPDATE add_column_lab
SET note = 'filled'
WHERE note IS NULL;
```

Trên bảng lớn thực tế, thay UPDATE toàn bảng bằng batch loop.

#### Bước 4. Validate

```sql
ALTER TABLE add_column_lab
VALIDATE CONSTRAINT add_column_lab_note_nonempty;
```

#### Bước 5. SET NOT NULL

```sql
ALTER TABLE add_column_lab
ALTER COLUMN note SET NOT NULL;
```

### Lab 6. Kiểm tra lock wait

#### Bước 1. Session A

```sql
BEGIN;
SELECT * FROM add_column_lab WHERE id = 1;
-- Keep transaction open for the exercise.
```

#### Bước 2. Session B

Thử ADD COLUMN trên cùng table với lock_timeout ngắn. Quan sát timeout.

#### Bước 3. Quan sát blocker

Dùng pg_stat_activity, pg_locks và pg_blocking_pids để xác định session đang giữ lock.

#### Bước 4. Kết thúc Session A

COMMIT hoặc ROLLBACK Session A, sau đó retry DDL trong Session B.

### Lab 7. Dọn dữ liệu lab

```sql
DROP TABLE IF EXISTS add_column_lab;
DROP TABLE IF EXISTS fast_default_lab;
DROP TABLE IF EXISTS volatile_default_lab;
```

Chỉ chạy cleanup trong database lab và xác nhận các bảng trên do chính lab tạo.

## 18. Bài tập thực hành

### Bài 1. ADD COLUMN cơ bản

Viết câu lệnh thêm cột preferred_name kiểu text, nullable và không có default vào bảng customers.

### Bài 2. Default

Thêm cột is_enabled kiểu boolean với default true. Giải thích giá trị mà historical rows và INSERT mới nhìn thấy.

### Bài 3. NULL và DEFAULT

Phân biệt INSERT bỏ qua column, INSERT dùng từ khóa DEFAULT và INSERT gửi explicit NULL.

### Bài 4. SET DEFAULT

Nếu chạy ALTER COLUMN SET DEFAULT 'VN', historical rows có tự đổi sang VN không? Vì sao?

### Bài 5. Volatility

Phân loại now(), clock_timestamp(), random() và nextval() theo volatility.

### Bài 6. Fast default

Fast default được giới thiệu trong PostgreSQL major version nào? Điều kiện quan trọng của default expression là gì?

### Bài 7. Version behavior

Một bảng có 500 triệu rows. ADD COLUMN region text DEFAULT 'APAC' trên PostgreSQL 10 và PostgreSQL 16 có thể khác nhau như thế nào?

### Bài 8. Volatile default

Vì sao ADD COLUMN random_key double precision DEFAULT random() có thể rewrite table ngay cả trên PostgreSQL 16?

### Bài 9. now và clock_timestamp

Vì sao default now() có thể dùng fast default nhưng clock_timestamp() không?

### Bài 10. Catalog

atthasmissing và attmissingval cung cấp thông tin gì?

### Bài 11. Lock

Vì sao ADD COLUMN fast default vẫn có thể chờ lâu trong production?

### Bài 12. Lock timeout

Viết ví dụ đặt lock_timeout 2 giây và statement_timeout 1 phút trước ALTER TABLE.

### Bài 13. NOT NULL

Vì sao thêm cột NOT NULL không default vào bảng đang có rows thường thất bại?

### Bài 14. NOT VALID

CHECK NOT VALID có kiểm tra rows cũ ngay khi ADD CONSTRAINT không? Nó có enforce rows mới không?

### Bài 15. VALIDATE

Sau backfill, dùng command nào để validate historical rows?

### Bài 16. CHECK NULL

Vì sao CHECK (amount > 0) không thay thế NOT NULL?

### Bài 17. Backfill

Nêu ba lý do nên chia UPDATE backfill thành batches có commit độc lập.

### Bài 18. Expand-contract

Mô tả thứ tự expand, deploy, backfill, validate và contract khi thêm một cột bắt buộc cho ứng dụng.

### Bài 19. Generated column

Vì sao không áp dụng giả định fast default cho generated stored column?

### Bài 20. Partitioning

Khi thêm column vào partitioned parent, cần kiểm tra những gì ở child partitions?

### Bài 21. Replication

Một table rewrite lớn có thể ảnh hưởng standby và WAL archive như thế nào?

### Bài 22. Schema drift

Vì sao ADD COLUMN IF NOT EXISTS không đủ để bảo đảm migration idempotent?

### Bài 23. Compatibility

Thiết kế cách thêm một cột source_system có default 'legacy' trên ứng dụng hỗ trợ cả PostgreSQL 10 và 16.

### Bài 24. Historical value

Nếu mỗi row cần một giá trị mới được derive từ created_at, vì sao không nên dùng một constant default?

### Bài 25. Production evidence

Liệt kê ít nhất tám thông tin cần lưu khi triển khai ADD COLUMN trên bảng lớn.

## 19. Gợi ý lời giải

### Đáp án 1

```sql
ALTER TABLE public.customers
ADD COLUMN preferred_name text;
```

### Đáp án 2

```sql
ALTER TABLE public.customers
ADD COLUMN is_enabled boolean DEFAULT true;
```

Historical rows nhìn thấy true. INSERT mới bỏ qua is_enabled cũng nhận true; explicit NULL vẫn là NULL nếu column nullable.

### Đáp án 3

- Bỏ qua column: PostgreSQL dùng default nếu có, nếu không thì NULL.
- Gửi DEFAULT: yêu cầu dùng default expression.
- Gửi NULL: lưu NULL, không kích hoạt default.

### Đáp án 4

Không. SET DEFAULT chỉ thay expression cho các INSERT/UPDATE tương lai khi column bị bỏ qua hoặc dùng DEFAULT. Historical rows không bị UPDATE.

### Đáp án 5

- now(): STABLE.
- clock_timestamp(): VOLATILE.
- random(): VOLATILE.
- nextval(): VOLATILE.

### Đáp án 6

PostgreSQL 11 giới thiệu fast default cho ADD COLUMN với default expression không volatile.

### Đáp án 7

PostgreSQL 10 thường rewrite heap để materialize default trên historical rows. PostgreSQL 16 có thể lưu missing-value metadata và tránh rewrite heap chỉ vì constant default. Cả hai vẫn cần lock.

### Đáp án 8

random() là volatile; mỗi historical row cần một giá trị riêng nên PostgreSQL phải tính và lưu các values trong quá trình rewrite.

### Đáp án 9

now() là stable, cho cùng transaction timestamp; clock_timestamp() volatile, có thể thay đổi giữa các lần gọi. Fast default chỉ áp dụng với non-volatile expression.

### Đáp án 10

atthasmissing cho biết column có missing-value metadata; attmissingval lưu giá trị logic cho tuples cũ chưa có physical attribute.

### Đáp án 11

ALTER TABLE vẫn cần ACCESS EXCLUSIVE. Transaction dài hoặc lock holder khác có thể ngăn migration lấy lock dù phần catalog update rất nhanh.

### Đáp án 12

```sql
SET lock_timeout = '2s';
SET statement_timeout = '1min';
ALTER TABLE public.customers ADD COLUMN source text;
```

### Đáp án 13

Rows cũ không có giá trị cho column mới và sẽ nhận NULL. NOT NULL không cho phép NULL nên PostgreSQL từ chối nếu không có default phù hợp hoặc quy trình backfill.

### Đáp án 14

NOT VALID bỏ qua validation của historical rows lúc ADD CONSTRAINT, nhưng constraint vẫn được enforce cho rows mới và rows được UPDATE sau đó.

### Đáp án 15

```sql
ALTER TABLE public.customers
VALIDATE CONSTRAINT customers_tier_present;
```

### Đáp án 16

CHECK chỉ reject expression FALSE; nếu expression trả NULL, row vẫn pass. NOT NULL phải được đặt riêng nếu cần cấm NULL.

### Đáp án 17

Batch commits giải phóng row locks, tránh transaction/snapshot quá dài và giúp kiểm soát WAL, replica lag, autovacuum và application latency.

### Đáp án 18

1. Expand: thêm nullable column và default tương thích.
2. Deploy: ứng dụng mới đọc/ghi column và vẫn xử lý historical NULL.
3. Backfill: cập nhật rows cũ theo batches.
4. Validate: CHECK NOT VALID, VALIDATE, SET NOT NULL.
5. Contract: bỏ compatibility code/legacy columns sau khi mọi writers đã chuyển.

### Đáp án 19

Generated stored column phải tính giá trị dựa trên dữ liệu từng row và lưu kết quả. Thêm nó vào bảng có dữ liệu có thể yêu cầu rewrite; nó không phải một constant missing value.

### Đáp án 20

Kiểm tra partition count, child schemas, defaults/constraints, attached/detached partitions, schema drift và locks trên mọi child.

### Đáp án 21

Rewrite/backfill có thể sinh nhiều WAL. Standby cần replay WAL nên lag có thể tăng; archive backlog và replication slot retention cũng có thể làm WAL disk tăng.

### Đáp án 22

IF NOT EXISTS chỉ bỏ qua lỗi duplicate name; nó không kiểm tra type, default, nullability, collation hay constraint của column đã tồn tại.

### Đáp án 23

Dùng chiến lược tương thích mọi version: ADD COLUMN nullable không default, SET DEFAULT 'legacy' cho INSERT mới, deploy writers tương thích, backfill historical rows theo batch, validate rồi SET NOT NULL nếu cần. PostgreSQL 16 có thể dùng fast default trực tiếp nếu giá trị legacy phù hợp cho tất cả historical rows, nhưng shared migration recipe dễ quản lý hơn.

### Đáp án 24

Constant default cho cùng một giá trị mọi historical row; business rule cần giá trị dựa trên từng created_at nên phải backfill bằng expression từ dữ liệu từng row.

### Đáp án 25

Ví dụ: server_version_num, migration command, table/TOAST/index sizes, start/end time, lock wait, transaction blockers, WAL bytes, archive lag, replica lag, null count, constraint validation state và application errors.

## 20. Checklist triển khai ADD COLUMN

### 20.1. Trước migration

1. Đọc server_version_num trên target.
2. Xác định table size, TOAST size, index size và partition count.
3. Xác định default expression và volatility.
4. Quyết định historical rows cần cùng giá trị hay giá trị per-row.
5. Xác định column có cần NOT NULL không.
6. Kiểm tra application versions và rolling deployment compatibility.
7. Kiểm tra long-running transactions/lock holders.
8. Đánh giá disk, WAL, archive và replica headroom.
9. Test trên staging có dữ liệu tương đương.
10. Chuẩn bị lock_timeout, statement_timeout và rollback/forward-fix.

### 20.2. Trong migration

11. Dùng schema-qualified table name.
12. Giữ DDL transaction ngắn.
13. Tách DDL khỏi batch backfill dài.
14. Theo dõi lock waits và blockers.
15. Theo dõi WAL, replica lag và disk.
16. Không retry tight loop khi lock timeout.
17. Ghi command, duration và server version.

### 20.3. Sau migration

18. Xác minh column type/default/nullability.
19. Kiểm tra historical và new rows.
20. Xác minh constraint state/validation.
21. Kiểm tra application INSERT/UPDATE/SELECT.
22. Kiểm tra replicas và WAL archive.
23. Ghi lại relation sizes và evidence.
24. Chỉ contract/drop legacy schema khi không còn consumers cũ.

## 21. Runbook xử lý migration chậm hoặc thất bại

### Bước 1. Xác định trạng thái

Kiểm tra migration session còn chạy, đang chờ lock hay đã fail. Đọc error, wait_event, query age và transaction state.

### Bước 2. Kiểm tra version và operation

Xác nhận server major version, default volatility và có subcommand nào buộc rewrite. Đối chiếu với migration plan.

### Bước 3. Tìm blockers

Dùng pg_stat_activity, pg_locks và pg_blocking_pids. Xác định transaction owner, tuổi transaction và tác động khi cancel.

### Bước 4. Đánh giá resource pressure

Nếu đang rewrite/backfill, kiểm tra CPU, I/O, disk, WAL, archive và replication lag. Tạm dừng batch jobs nếu vượt ngưỡng.

### Bước 5. Chọn hành động

- Lock wait: cancel migration có kiểm soát, xử lý blocker, retry với backoff.
- Rewrite quá nặng: hủy nếu chưa thể chấp nhận impact; lập lại plan theo version và staged backfill.
- Backfill lag: giảm batch size/pause, đợi replica catch up.
- Constraint validation fail: tìm và sửa violating rows theo business rules.
- Application errors: rollback feature flag/code rollout hoặc forward-fix schema tương thích.

### Bước 6. Xác minh

Kiểm tra schema/catalog, null count, constraints, application behavior và replicas sau khi retry.

### Bước 7. Ghi incident

Lưu timeline, version, lock blockers, DDL, WAL/replica metrics, dữ liệu đã backfill và corrective actions.

## 22. Tổng kết

Thêm cột trong PostgreSQL là một thay đổi schema có semantics và chi phí phụ thuộc phiên bản. PostgreSQL 11 đưa vào fast default cho ADD COLUMN với default expression không volatile: historical rows có thể đọc giá trị missing từ catalog metadata mà không cần rewrite heap chỉ vì default. PostgreSQL 10 trở về trước thường rewrite bảng khi thêm non-NULL default trên bảng có dữ liệu.

Các nguyên tắc cần nhớ:

- DEFAULT áp dụng khi INSERT bỏ qua column hoặc chỉ định DEFAULT; explicit NULL không dùng default.
- SET DEFAULT không cập nhật historical rows; DROP DEFAULT không xóa giá trị đã có.
- now() là stable, clock_timestamp(), random() và nextval() là volatile.
- Volatile default cần tính riêng cho historical rows và có thể buộc table rewrite ngay cả trên PostgreSQL 11+.
- Fast default vẫn cần ACCESS EXCLUSIVE lock; lock wait có thể là rủi ro lớn hơn execution time.
- NOT NULL cần mọi historical/new rows có giá trị không NULL.
- CHECK NOT VALID cho phép hoãn validation historical rows; VALIDATE CONSTRAINT xác nhận sau backfill.
- CHECK đã validate có thể giúp SET NOT NULL tránh một table scan lặp lại trên các versions hỗ trợ.
- Backfill bảng lớn nên chia batches, commit độc lập và theo dõi WAL/replica lag.
- Expand-contract giúp rolling deployment tương thích giữa code cũ và schema mới.
- Generated stored columns, identity, partitions, type changes và extensions cần kiểm tra behavior riêng theo version.
- Kiểm tra server_version_num trên target; psql client version không quyết định DDL behavior.
- Test trên dataset gần production và lưu lock/resource evidence.

Nguyên tắc thực hành:

> **Trước khi thêm cột, hãy xác định giá trị của historical rows, volatility của default, version server và lock impact; sau đó chọn migration phù hợp với dữ liệu và rollout của ứng dụng.**

## 23. Tài liệu tham khảo

Ưu tiên documentation đúng major version đang chạy:

- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): ADD COLUMN, SET/DROP DEFAULT, SET NOT NULL, CHECK và NOT VALID.
- [PostgreSQL 11 Release Notes](https://www.postgresql.org/docs/11/release-11.html): fast default optimization cho ADD COLUMN.
- [PostgreSQL 10 ALTER TABLE](https://www.postgresql.org/docs/10/sql-altertable.html): behavior của ALTER TABLE trước fast default.
- [PostgreSQL 11 ALTER TABLE](https://www.postgresql.org/docs/11/sql-altertable.html): version có fast default.
- [PostgreSQL 12 ALTER TABLE](https://www.postgresql.org/docs/12/sql-altertable.html): generated columns và constraint behavior theo version.
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): IMMUTABLE, STABLE và VOLATILE.
- [System Catalogs — pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html): column metadata.
- [System Catalogs — pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html): constraint validation metadata.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): table-level lock modes và conflicts.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity, pg_locks và wait events.
- [PostgreSQL Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): generated-column semantics và restrictions.
- [PostgreSQL Identity Columns](https://www.postgresql.org/docs/current/ddl-identity-columns.html): identity/sequence behavior.
- [PostgreSQL Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partitioned tables và partitions.
- [PostgreSQL Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): dead tuples, autovacuum và table maintenance.
