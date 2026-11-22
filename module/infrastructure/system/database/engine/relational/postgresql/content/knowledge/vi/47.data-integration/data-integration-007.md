# So sánh postgres_fdw, dblink và sao chép dữ liệu

PostgreSQL có nhiều cách để làm việc với dữ liệu nằm ở database khác. Ba hướng thường gặp là dùng `postgres_fdw` để truy vấn bảng từ xa như bảng trong database hiện tại, dùng `dblink` để gửi câu SQL tới một kết nối PostgreSQL khác, hoặc sao chép dữ liệu về database đích bằng replication hay một quy trình ETL.

Các cách này giải quyết những nhu cầu khác nhau. `postgres_fdw` phù hợp khi ứng dụng cần truy cập dữ liệu nguồn trực tiếp bằng SQL và muốn PostgreSQL tham gia lập kế hoạch truy vấn. `dblink` hữu ích khi cần gọi một câu lệnh từ xa theo cách tường minh hoặc tích hợp một đoạn SQL từ xa trong function. Sao chép dữ liệu phù hợp khi hệ thống cần một bản dữ liệu cục bộ để đọc, phân tích, giảm phụ thuộc vào kết nối trực tiếp hoặc phục vụ dự phòng.

## 1. Phân biệt ba cách tích hợp

Giả sử có database `sales` trên máy chủ nguồn và database `analytics` trên máy chủ phân tích. Hệ thống phân tích cần đọc bảng `public.orders` từ `sales`.

### 1.1. postgres_fdw: truy cập bảng từ xa qua foreign table

`postgres_fdw` là Foreign Data Wrapper (FDW) dành cho PostgreSQL. Ta khai báo một foreign server, user mapping và foreign table trong database đích. Foreign table có cấu trúc cột tương ứng với đối tượng từ xa, vì vậy truy vấn có thể dùng tên bảng như đối tượng SQL bình thường:

```sql
SELECT order_id, customer_id, total_amount
FROM ext_sales.orders
WHERE order_date >= DATE '2026-01-01';
```

Dữ liệu vẫn được lưu ở database nguồn. Khi truy vấn chạy, PostgreSQL kết nối tới nguồn và lấy dữ liệu cần thiết. Database đích lưu metadata của foreign table chứ không tự lưu một bản sao các hàng dữ liệu.

### 1.2. dblink: gửi câu SQL qua kết nối từ xa

`dblink` cung cấp các hàm để mở kết nối PostgreSQL khác, gửi SQL và nhận kết quả. Câu SQL từ xa được viết rõ trong lời gọi hàm:

```sql
SELECT *
FROM dblink(
    'host=db.example.net port=5432 dbname=sales user=sales_reader',
    'SELECT order_id, customer_id, total_amount FROM public.orders'
) AS remote_orders(
    order_id bigint,
    customer_id bigint,
    total_amount numeric(12, 2)
);
```

Kết quả của `dblink` được khai báo kiểu cột ở phía gọi bằng `AS ...`. PostgreSQL không tự xem câu SQL bên trong như một quan hệ foreign table để lập kế hoạch kết hợp với các bảng khác. Người viết truy vấn phải chủ động chọn câu SQL từ xa và định nghĩa hình dạng kết quả.

### 1.3. Sao chép dữ liệu: tạo bản dữ liệu ở nơi nhận

Replication hoặc ETL chuyển dữ liệu từ nguồn sang một database đích. Sau khi dữ liệu được chuyển, ứng dụng đọc bản cục bộ ở `analytics`:

```sql
SELECT order_id, customer_id, total_amount
FROM reporting.orders;
```

Truy vấn không cần kết nối tới database nguồn ở thời điểm đọc. Đổi lại, bản dữ liệu đích có thể chậm hơn nguồn một khoảng thời gian và cần quy trình cập nhật, giám sát độ trễ, xử lý thay đổi cấu trúc.

Có nhiều kiểu sao chép. Một lần xuất/nhập hoặc ETL theo lịch tạo snapshot hay bản dữ liệu được làm mới theo chu kỳ. Logical replication truyền các thay đổi dữ liệu của những bảng được chọn. Physical streaming replication truyền WAL để duy trì một standby của cả PostgreSQL cluster.

## 2. Bảng so sánh tổng quan

| Tiêu chí | `postgres_fdw` | `dblink` | Sao chép dữ liệu |
|---|---|---|---|
| Mô hình | Truy vấn dữ liệu từ xa qua foreign table | Gọi câu SQL từ xa bằng hàm | Chuyển dữ liệu thành bản sao ở đích |
| Dữ liệu được lưu ở đâu? | Chủ yếu ở nguồn | Chủ yếu ở nguồn, trừ khi kết quả được ghi lại | Có bản dữ liệu tại đích |
| Cách truy vấn | SQL trên foreign table | SQL nằm trong chuỗi truyền cho hàm | SQL trên bảng cục bộ đã sao chép |
| Tích hợp với query planner | Có; FDW có thể đẩy một số thao tác xuống nguồn | Hạn chế; câu SQL từ xa do người viết kiểm soát | Truy vấn cục bộ, không cần planner truy cập nguồn |
| Độ mới của dữ liệu | Đọc từ nguồn tại thời điểm truy vấn, theo snapshot giao dịch từ xa | Đọc hoặc ghi từ xa khi hàm được gọi | Phụ thuộc độ trễ replication hoặc lịch ETL |
| Phụ thuộc mạng lúc đọc | Có | Có | Không đối với truy vấn trên bản sao đã cập nhật |
| Ghi dữ liệu | Hỗ trợ một số thao tác ghi qua FDW khi nguồn cho phép | Có thể gửi lệnh ghi bằng `dblink_exec` | Ghi theo cơ chế replication hoặc pipeline; không tương đương ghi trực tiếp vào nguồn |
| Phạm vi | Theo foreign table và server | Theo từng lời gọi SQL và kết nối | Theo publication, cluster hoặc phạm vi ETL |
| Phù hợp | Federation, tích hợp truy vấn trực tiếp | Lệnh từ xa có chủ đích, function hoặc thao tác đặc biệt | Phân tích, giảm tải nguồn, đọc cục bộ, HA/DR tùy loại replication |

Không có lựa chọn nào luôn tốt nhất. Cần xác định hệ thống ưu tiên dữ liệu mới nhất, khả năng truy vấn cục bộ, độ độc lập với nguồn, phạm vi dữ liệu, độ trễ chấp nhận được và cách vận hành.

## 3. postgres_fdw

### 3.1. Thành phần và cách hoạt động

Một cấu hình `postgres_fdw` thường có các thành phần:

- **Foreign data wrapper**: thành phần giao tiếp với hệ thống dữ liệu từ xa. Trong trường hợp này là `postgres_fdw`.
- **Foreign server**: lưu thông tin về máy chủ và database nguồn.
- **User mapping**: ánh xạ role cục bộ sang tài khoản truy cập database nguồn.
- **Foreign table**: định nghĩa cục bộ về bảng hoặc view từ xa.

Luồng truy cập:

```text
Ứng dụng / câu SQL
        |
        v
Database đích: ext_sales.orders (foreign table)
        |
        v
postgres_fdw
        |
        | kết nối bằng foreign server và user mapping
        v
Database nguồn: sales.public.orders
        |
        v
Dữ liệu thực tế
```

PostgreSQL có thể chuyển một số điều kiện lọc, danh sách cột, phép sắp xếp, giới hạn dòng, phép nối và phép tổng hợp sang máy chủ từ xa khi biểu thức và cấu hình đáp ứng điều kiện pushdown. Điều này giúp tránh truyền toàn bộ dữ liệu về database đích. Tuy nhiên, không phải mọi biểu thức hay mọi phép nối đều được đẩy xuống nguồn.

### 3.2. Cấu hình cơ bản

Thực hiện các lệnh sau ở database đích:

```sql
-- Cài extension.
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- Khai báo máy chủ nguồn.
CREATE SERVER sales_source
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'db.example.net',
    port '5432',
    dbname 'sales'
);

-- Ánh xạ role hiện tại sang tài khoản đọc ở nguồn.
CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_source
OPTIONS (
    user 'sales_reader',
    password '<secret-managed-outside-source-control>'
);

-- Chuẩn bị schema chứa foreign table.
CREATE SCHEMA IF NOT EXISTS ext_sales;

-- Import một số bảng cần dùng.
IMPORT FOREIGN SCHEMA public
    LIMIT TO (orders, customers)
    FROM SERVER sales_source
    INTO ext_sales;
```

Role ở database nguồn phải có quyền kết nối, quyền `USAGE` trên schema và quyền cần thiết trên các bảng hoặc view. Role cục bộ cần quyền sử dụng foreign server, schema và foreign table. Thông tin xác thực cần được quản lý an toàn; không đưa mật khẩu thật vào script được commit vào repository.

Sau khi import, có thể truy vấn và kết hợp foreign table với bảng cục bộ:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    SUM(o.total_amount) AS revenue
FROM ext_sales.customers AS c
JOIN ext_sales.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_date >= DATE '2026-01-01'
GROUP BY c.customer_id, c.customer_name
ORDER BY revenue DESC;
```

### 3.3. Ghi dữ liệu qua postgres_fdw

`postgres_fdw` hỗ trợ `INSERT`, `UPDATE`, `DELETE` và `TRUNCATE` trong những điều kiện phù hợp. Khả năng ghi phụ thuộc vào loại đối tượng từ xa, định nghĩa foreign table, tùy chọn FDW và quyền của tài khoản từ xa.

Ví dụ cập nhật một foreign table:

```sql
UPDATE ext_sales.orders
SET total_amount = 125.50
WHERE order_id = 9001;
```

Lệnh trên tác động đến dữ liệu ở database nguồn nếu thao tác được hỗ trợ và tài khoản từ xa có quyền. Vì vậy, nếu mục tiêu chỉ là đọc dữ liệu, nên dùng tài khoản nguồn chỉ có quyền đọc. Có thể cấu hình foreign table hoặc foreign server để hạn chế thao tác ghi theo chính sách của hệ thống.

### 3.4. Giao dịch và hiệu năng

`postgres_fdw` quản lý giao dịch từ xa gắn với giao dịch cục bộ. Khi truy vấn cần dữ liệu từ server, FDW mở giao dịch từ xa tương ứng và giữ kết nối theo vòng đời phù hợp với phiên làm việc. Điều này giúp các thao tác từ xa tham gia vào ngữ cảnh giao dịch của PostgreSQL.

Tuy vậy, khi một giao dịch làm việc với nhiều máy chủ từ xa, không nên giả định có một cơ chế commit phân tán nguyên tử hoàn chỉnh bao trùm mọi server. Sự cố mạng hoặc lỗi khi commit ở một server có thể khiến kết quả giữa các nguồn không đồng nhất. Nếu cần cập nhật nhiều hệ thống, phải thiết kế xử lý lỗi, đối soát và khả năng chạy lại.

Một số yếu tố hiệu năng cần quan tâm:

- Đặt điều kiện lọc có thể thực thi từ xa và chỉ chọn các cột cần thiết để giảm lượng dữ liệu truyền qua mạng.
- Dùng `EXPLAIN (VERBOSE)` để xem phần `Remote SQL` và xác định thao tác nào được đẩy xuống nguồn.
- Đảm bảo bảng nguồn có index phù hợp với điều kiện lọc và phép nối.
- Cân nhắc tùy chọn `use_remote_estimate` nếu ước lượng chi phí từ thống kê cục bộ không phù hợp; việc lấy ước lượng từ xa cũng có chi phí.
- Điều chỉnh `fetch_size` khi truy vấn trả về nhiều dòng để cân bằng số lần trao đổi mạng và lượng dữ liệu đệm.
- Đánh giá độ trễ, băng thông và tải của máy chủ nguồn; một truy vấn tổng hợp lớn vẫn có thể gây tải đáng kể ở nguồn.

Ví dụ kiểm tra kế hoạch:

```sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, total_amount
FROM ext_sales.orders
WHERE customer_id = 1001;
```

`postgres_fdw` phù hợp khi cần một lớp truy cập SQL tương đối tự nhiên, có nhiều truy vấn cần dùng lại và muốn planner tối ưu một phần thao tác từ xa. Nó không tạo bản sao dữ liệu để truy vấn độc lập khi nguồn mất kết nối.

## 4. dblink

### 4.1. Cách hoạt động

`dblink` là extension cung cấp các hàm kết nối tới PostgreSQL khác và thực thi SQL ở đó. Người viết kiểm soát câu lệnh từ xa, sau đó khai báo cấu trúc kết quả ở truy vấn cục bộ nếu câu lệnh trả về dữ liệu.

Cài extension trong database cần gọi hàm:

```sql
CREATE EXTENSION IF NOT EXISTS dblink;
```

### 4.2. Truy vấn từ xa một lần

```sql
SELECT *
FROM dblink(
    'host=db.example.net port=5432 dbname=sales user=sales_reader password=<secret>',
    'SELECT order_id, customer_id, total_amount
     FROM public.orders
     WHERE order_date >= DATE ''2026-01-01'''
) AS r(
    order_id bigint,
    customer_id bigint,
    total_amount numeric(12, 2)
);
```

Lời gọi `dblink` có hai phần quan trọng: thông tin kết nối và chuỗi SQL gửi tới nguồn. Vì kết quả hàm được PostgreSQL xem như record, phần `AS r(...)` phải khai báo tên và kiểu dữ liệu của các cột trả về. Kiểu dữ liệu khai báo cần tương thích với kết quả thực tế.

Khi dùng chuỗi kết nối trực tiếp, cần bảo vệ thông tin xác thực. Không lưu mật khẩu thật trong mã nguồn, log hoặc lịch sử lệnh. Có thể quản lý kết nối bằng foreign server và user mapping thông qua `dblink_fdw` thay vì nhúng thông tin đăng nhập trong từng câu SQL.

### 4.3. Kết nối có tên và tái sử dụng

Nếu cần thực hiện nhiều lời gọi tới cùng một nguồn trong một phiên, có thể mở kết nối có tên:

```sql
SELECT dblink_connect(
    'sales_conn',
    'host=db.example.net port=5432 dbname=sales user=sales_reader'
);

SELECT *
FROM dblink(
    'sales_conn',
    'SELECT order_id, total_amount FROM public.orders LIMIT 10'
) AS r(
    order_id bigint,
    total_amount numeric(12, 2)
);

SELECT dblink_disconnect('sales_conn');
```

Kết nối có tên tồn tại trong phiên database cục bộ cho đến khi được ngắt hoặc phiên kết thúc. Cần đóng kết nối khi hoàn tất và xử lý trường hợp function lỗi giữa chừng để tránh giữ tài nguyên không cần thiết. Một lời gọi `dblink` dùng trực tiếp chuỗi kết nối có thể mở kết nối cho lần gọi đó; kết nối có tên hữu ích khi muốn tái sử dụng.

### 4.4. Gửi lệnh không trả về tập dòng

`dblink_exec` thường dùng cho lệnh từ xa không cần trả về tập kết quả, chẳng hạn `INSERT`, `UPDATE`, `DELETE` hoặc một số lệnh quản trị:

```sql
SELECT dblink_exec(
    'sales_conn',
    'UPDATE public.orders
     SET total_amount = 125.50
     WHERE order_id = 9001'
);
```

Hàm trả về trạng thái thực thi của câu lệnh từ xa. Tài khoản trong kết nối phải có quyền tương ứng ở nguồn.

### 4.5. Giao dịch từ xa và giới hạn

Kết nối `dblink` có ngữ cảnh giao dịch riêng ở máy chủ từ xa. Một lệnh ghi được gửi qua kết nối đang ở chế độ tự động commit có thể được commit ở nguồn ngay cả khi giao dịch cục bộ sau đó rollback. Nếu cần điều khiển giao dịch từ xa, có thể gửi các lệnh `BEGIN`, `COMMIT` và `ROLLBACK` qua chính kết nối có tên:

```sql
SELECT dblink_exec('sales_conn', 'BEGIN');

SELECT dblink_exec(
    'sales_conn',
    'UPDATE public.orders
     SET total_amount = 125.50
     WHERE order_id = 9001'
);

SELECT dblink_exec('sales_conn', 'COMMIT');
```

Việc quản lý giao dịch từ xa theo cách này do ứng dụng hoặc function chịu trách nhiệm. `ROLLBACK` ở database cục bộ không tự động rollback một giao dịch từ xa đã commit. Ngược lại, nếu giao dịch từ xa vẫn đang mở, phải chủ động rollback hoặc xử lý kết nối bị lỗi. Không nên coi nhiều lời gọi `dblink` là một giao dịch phân tán nguyên tử.

Một hạn chế quan trọng là câu SQL được truyền dưới dạng chuỗi. `dblink` không cung cấp trải nghiệm bind parameter như truy vấn SQL thông thường trên bảng cục bộ. Khi cần ghép giá trị vào SQL động, phải dùng cơ chế quote an toàn như `format('%L', value)` cho literal và `format('%I', identifier)` cho tên đối tượng; không nối trực tiếp dữ liệu đầu vào không tin cậy vào câu SQL. Nếu logic truy vấn phức tạp, nhiều consumer cần dùng lại cùng cấu trúc, hoặc cần planner xử lý join và filter từ xa, `postgres_fdw` thường dễ quản lý hơn.

`dblink` phù hợp cho một thao tác từ xa cụ thể, một function điều phối, hoặc trường hợp cần thực thi câu SQL mà mô hình foreign table không diễn đạt thuận tiện. Nó thường đòi hỏi người viết tự quản lý kết nối, kiểu kết quả, SQL động, giao dịch và xử lý lỗi.

## 5. Sao chép dữ liệu

Sao chép dữ liệu tạo một bản dữ liệu ở database nhận. Khi truy vấn bản sao, ứng dụng không phải kết nối tới database nguồn. Cần phân biệt ba nhóm cách làm vì cơ chế, độ trễ và phạm vi khác nhau.

### 5.1. Snapshot hoặc ETL theo lịch

Snapshot là bản chụp dữ liệu tại một thời điểm. ETL (Extract, Transform, Load) có thể đọc dữ liệu từ nguồn, chuyển đổi và ghi vào bảng đích. Quy trình có thể chạy một lần, theo giờ, theo ngày hoặc theo lịch nghiệp vụ.

Ví dụ, nếu đã cấu hình `postgres_fdw`, có thể tạo snapshot trong database đích:

```sql
CREATE TABLE reporting.orders_snapshot AS
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM ext_sales.orders;
```

Hoặc nạp dữ liệu vào bảng đã tồn tại:

```sql
INSERT INTO reporting.orders_snapshot (
    order_id,
    customer_id,
    order_date,
    total_amount
)
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM ext_sales.orders;
```

Ví dụ trên minh họa việc materialize kết quả truy vấn thành dữ liệu cục bộ. Nó không tự tạo cơ chế đồng bộ liên tục. Nếu chạy lặp lại, cần xác định cách xử lý bản ghi trùng, bản ghi đã thay đổi và bản ghi bị xóa. Có thể dùng chiến lược truncate-and-load, upsert theo khóa, watermark theo thời gian cập nhật hoặc công cụ ETL/CDC chuyên dụng tùy khối lượng và yêu cầu nhất quán.

`COPY` và `\copy` cũng có thể dùng để xuất/nhập dữ liệu qua file. `COPY` làm việc với file ở phía máy chủ PostgreSQL; `\copy` là lệnh của `psql` đọc/ghi file ở máy chạy client. Chúng hữu ích cho tải dữ liệu hàng loạt, nhưng bản thân chúng không phải cơ chế đồng bộ thay đổi liên tục giữa hai database.

### 5.2. Logical replication

Logical replication truyền các thay đổi dữ liệu ở mức logic từ publisher sang subscriber. Có thể chọn những bảng cần phát hành thay vì sao chép toàn bộ cluster. Subscriber có bảng riêng để nhận thay đổi và có thể phục vụ truy vấn cục bộ.

Các khái niệm chính:

- **Publisher**: database nguồn có publication.
- **Publication**: tập bảng và loại thao tác được phát hành.
- **Subscriber**: database đích đăng ký nhận thay đổi.
- **Subscription**: cấu hình kết nối và nhận dữ liệu từ một publication.
- **Replication slot**: giữ vị trí WAL cần thiết để subscriber có thể tiếp tục nhận thay đổi.

Luồng cơ bản:

```text
Publisher (database nguồn)
       |
       | Publication: orders_pub
       | WAL + logical decoding
       v
Kết nối replication
       |
       v
Subscriber (database đích)
       |
       | Subscription: orders_sub
       v
Bảng cục bộ reporting.orders
```

#### Chuẩn bị publisher

Publisher cần được cấu hình cho logical replication, trong đó `wal_level` phải là `logical`. Các tham số liên quan tới replication slot và WAL sender cần đủ cho số subscriber dự kiến. Cấu hình `pg_hba.conf` phải cho phép role replication kết nối từ subscriber. Thay đổi tham số yêu cầu restart hay reload tùy tham số cụ thể.

Tạo role dùng cho kết nối replication và cấp quyền đọc các bảng được phát hành:

```sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD '<secret-managed-outside-source-control>';

GRANT CONNECT ON DATABASE sales TO replicator;
GRANT USAGE ON SCHEMA public TO replicator;
GRANT SELECT ON TABLE public.orders, public.order_items TO replicator;
```

Tạo publication:

```sql
CREATE PUBLICATION orders_pub
FOR TABLE public.orders, public.order_items;
```

Publication có thể giới hạn theo bảng và cấu hình loại thao tác được phát hành. Với thao tác `UPDATE` hoặc `DELETE`, bảng nguồn cần có replica identity phù hợp, thường là primary key. Nếu không có khóa phù hợp, cần xem xét cấu hình `REPLICA IDENTITY` và chi phí của lựa chọn đó.

#### Chuẩn bị subscriber

Trên database đích, tạo các bảng nhận dữ liệu với cấu trúc tương thích. Logical replication không tự sao chép DDL tạo bảng từ publisher; schema phải được chuẩn bị và quản lý riêng.

Sau đó tạo subscription:

```sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=db.example.net port=5432 dbname=sales user=replicator password=<secret> sslmode=verify-full'
PUBLICATION orders_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
```

Với `copy_data = true`, PostgreSQL thực hiện đồng bộ dữ liệu ban đầu cho các bảng được đăng ký, sau đó tiếp tục áp dụng thay đổi mới. Subscription mặc định được bật và tạo replication slot ở publisher khi dùng cấu hình mặc định tương ứng. Cần lập kế hoạch dung lượng WAL, số slot và khả năng phục hồi nếu subscriber ngừng hoạt động lâu.

Logical replication thường hoạt động bất đồng bộ, vì vậy subscriber có thể trễ so với publisher. Độ trễ phụ thuộc tốc độ phát sinh thay đổi, mạng, tốc độ apply và tải của subscriber. Nên giám sát trạng thái subscription và replication slot, đồng thời cảnh báo khi lag hoặc WAL tích tụ vượt ngưỡng vận hành.

#### Những gì logical replication không tự làm

- Không tự sao chép DDL như `CREATE TABLE`, `ALTER TABLE` hoặc thay đổi index. Phải triển khai schema ở subscriber theo quy trình riêng.
- Không đồng bộ trạng thái sequence như một phần dữ liệu bảng. Khi chuyển quyền ghi hoặc cutover, cần đồng bộ giá trị sequence phù hợp.
- Không tự giải quyết mọi xung đột nếu có ghi độc lập trên subscriber. Thiết kế thông thường là publisher sở hữu dữ liệu được replicate; tránh cập nhật trực tiếp các hàng đó ở subscriber nếu chưa có chiến lược xử lý xung đột.
- Không phải giải pháp multi-master tự động. PostgreSQL logical replication cơ bản truyền theo hướng publisher tới subscriber; việc ghi hai chiều cần kiến trúc và cơ chế giải quyết xung đột riêng.
- Không thay thế backup. Replication có thể truyền cả thao tác xóa hoặc cập nhật nhầm, vì vậy vẫn cần backup và khả năng phục hồi theo thời điểm.

Logical replication phù hợp khi cần một bản dữ liệu chọn lọc, cập nhật liên tục, phục vụ đọc cục bộ hoặc tích hợp dữ liệu giữa các hệ thống. Nó đặc biệt hữu ích khi subscriber cần giữ một phần dữ liệu của publisher và có thể chấp nhận độ trễ replication.

### 5.3. Physical streaming replication

Physical replication truyền WAL ở mức vật lý để duy trì standby của PostgreSQL cluster. Standby là bản sao của toàn bộ cluster ở mức storage/WAL, không chọn riêng một vài bảng như logical replication.

Đặc điểm chính:

- Thường dùng cho high availability (HA), disaster recovery (DR) và standby phục vụ truy vấn đọc.
- Standby replay WAL để tiến gần trạng thái của primary. Streaming replication có thể bất đồng bộ hoặc cấu hình đồng bộ tùy yêu cầu.
- Hot standby có thể phục vụ truy vấn đọc trong khi nhận và replay WAL.
- Khi cần chuyển vai trò, standby được promote thành primary theo quy trình failover.
- Physical standby phải tương thích về major version và các yêu cầu vật lý của PostgreSQL; đây không phải công cụ chọn một nhóm bảng để tích hợp vào database độc lập.

Physical replication thích hợp khi mục tiêu là duy trì một bản sao toàn cluster để dự phòng hoặc chuyển đổi dự phòng. Nếu mục tiêu là đưa riêng bảng `orders` vào một database phân tích có schema và workload riêng, logical replication hoặc ETL thường phù hợp hơn.

## 6. So sánh sâu theo tiêu chí vận hành

### 6.1. Độ mới và tính sẵn sàng dữ liệu

| Tình huống | postgres_fdw | dblink | Bản sao dữ liệu |
|---|---|---|---|
| Cần đọc dữ liệu mới nhất từ nguồn | Truy vấn trực tiếp nguồn | Gọi SQL trực tiếp nguồn | Có thể trễ theo replication hoặc lịch ETL |
| Nguồn tạm mất kết nối | Truy vấn phụ thuộc nguồn sẽ lỗi | Lời gọi phụ thuộc nguồn sẽ lỗi | Bản sao cục bộ vẫn có thể đọc |
| Cần đọc khối lượng lớn thường xuyên | Có thể tốn mạng và tải nguồn; cần pushdown | Có thể tốn mạng; người viết phải tối ưu SQL từ xa | Đọc cục bộ thường phù hợp hơn sau khi dữ liệu đã được nạp |
| Cần bản chụp tại thời điểm xác định | Có thể tạo snapshot từ kết quả truy vấn | Có thể lấy kết quả rồi ghi thành bảng | Là mục tiêu tự nhiên của snapshot/ETL |

`postgres_fdw` và `dblink` cho phép truy cập dữ liệu ở nguồn khi truy vấn chạy, nhưng điều đó cũng khiến hoạt động đọc phụ thuộc mạng và trạng thái nguồn. Bản sao cục bộ tăng khả năng đọc độc lập, đổi lại phải chấp nhận và quản lý độ trễ dữ liệu.

### 6.2. Giao dịch và tính nhất quán

Với `postgres_fdw`, thao tác từ xa được quản lý trong ngữ cảnh giao dịch của FDW. Đây là lựa chọn thuận tiện khi cần truy vấn và cập nhật foreign table bằng SQL. Tuy nhiên, không nên giả định các thay đổi trên nhiều server từ xa được commit như một giao dịch phân tán nguyên tử duy nhất.

Với `dblink`, kết nối từ xa có giao dịch riêng. Người viết cần điều khiển rõ `BEGIN`, `COMMIT`, `ROLLBACK` nếu muốn gom nhiều lệnh từ xa vào một giao dịch. Giao dịch cục bộ và giao dịch từ xa không tự động có cùng kết quả commit/rollback.

Với logical replication, publisher commit thay đổi trước rồi subscriber nhận và apply sau. Đây là luồng bất đồng bộ thông thường; tại một thời điểm, subscriber có thể chưa áp dụng hết thay đổi đã commit ở publisher. Với physical synchronous replication, cấu hình đồng bộ có thể yêu cầu xác nhận từ standby theo chính sách đã chọn, nhưng cần đánh giá trade-off giữa độ bền dữ liệu và độ trễ commit.

Với ETL theo lịch, mức nhất quán phụ thuộc cách pipeline lấy snapshot và đánh dấu tiến độ. Một lần nạp nên có điểm cắt rõ ràng, xử lý lỗi có thể chạy lại và cơ chế tránh bỏ sót hoặc nhân đôi bản ghi.

### 6.3. Hiệu năng và khả năng mở rộng

`postgres_fdw` giảm công sức viết SQL nhưng truy vấn vẫn chịu chi phí mạng và tải máy chủ nguồn. Cần đẩy điều kiện lọc và phép tổng hợp xuống nguồn khi có thể. Nếu báo cáo lặp lại nhiều lần trên dữ liệu lớn, một bản sao cục bộ thường giảm tải nguồn và giảm chi phí mạng ở thời điểm đọc.

`dblink` trao quyền kiểm soát câu SQL từ xa cho người viết. Điều đó hữu ích cho thao tác chuyên biệt, nhưng làm tăng trách nhiệm xây dựng SQL an toàn, quản lý kiểu kết quả và theo dõi kế hoạch ở cả hai phía. Planner cục bộ không tối ưu toàn bộ nội dung SQL được gửi qua hàm `dblink`.

Logical replication tạo tải truyền và apply thay đổi liên tục. Nó tránh phải đọc lại toàn bộ bảng ở mỗi lần đồng bộ sau giai đoạn initial copy, nhưng có chi phí WAL, slot, mạng và worker apply. ETL theo lô có thể tối ưu cho khối lượng lớn nhưng tạo đỉnh tải vào thời điểm chạy. Physical replication truyền WAL cho toàn cluster và thường là lựa chọn hiệu quả cho standby vật lý, nhưng không tạo bản sao chọn lọc theo bảng.

### 6.4. Bảo mật và quyền truy cập

Với cả ba phương án, cần giới hạn quyền theo nguyên tắc tối thiểu:

- Dùng tài khoản riêng cho tích hợp, chỉ cấp quyền trên database, schema và bảng cần thiết.
- Bảo vệ thông tin xác thực; ưu tiên cơ chế quản lý secret, xác thực và TLS phù hợp với môi trường.
- Kiểm soát kết nối bằng `pg_hba.conf`, firewall và quyền `CONNECT` ở nguồn.
- Với `postgres_fdw`, quản lý `USAGE` trên foreign server, user mapping, schema và foreign table ở database đích.
- Với `dblink`, tránh đưa thông tin nhạy cảm vào SQL động, log hoặc script; quote literal và identifier đúng cách.
- Với logical replication, cấp quyền replication và quyền đọc bảng cần thiết; giới hạn nguồn kết nối subscriber.
- Không dùng tài khoản superuser chỉ để đơn giản hóa cấu hình tích hợp.

## 7. Khi nào nên chọn phương án nào?

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Truy vấn bảng PostgreSQL từ xa bằng SQL thông thường | `postgres_fdw` | Foreign table tích hợp với truy vấn và planner của PostgreSQL. |
| Join bảng từ xa với bảng cục bộ | `postgres_fdw` | Có thể pushdown một số phép join/filter khi đủ điều kiện; cú pháp truy vấn dễ dùng lại. |
| Chạy một câu lệnh từ xa trong function hoặc quy trình điều phối | `dblink` | Lời gọi hàm thể hiện rõ câu SQL cần gửi. |
| Cần kiểm soát thủ công một chuỗi lệnh hoặc giao dịch từ xa | `dblink` | Có thể gửi các lệnh SQL từ xa theo trình tự cụ thể, nhưng phải tự quản lý lỗi và commit. |
| Báo cáo lớn cần đọc thường xuyên, giảm tải nguồn | Logical replication hoặc ETL | Dữ liệu được lưu cục bộ để truy vấn mà không gọi nguồn mỗi lần. |
| Chỉ cần snapshot dữ liệu theo giờ/ngày | ETL hoặc batch load | Không cần duy trì kết nối và luồng thay đổi liên tục. |
| Duy trì bản sao chọn lọc của một số bảng | Logical replication | Có publication/subscription và đồng bộ thay đổi liên tục. |
| Dự phòng hoặc failover cho cả PostgreSQL cluster | Physical streaming replication | Duy trì standby vật lý của cluster. |
| Cần đọc dữ liệu ngay cả khi nguồn đang mất kết nối | Bản sao cục bộ | Truy vấn không phụ thuộc kết nối tới nguồn tại thời điểm đọc. |

Có thể kết hợp các phương án. Ví dụ, `postgres_fdw` có thể dùng để đọc dữ liệu nguồn trong pipeline ETL, sau đó pipeline ghi kết quả đã biến đổi vào bảng cục bộ. Logical replication có thể đưa thay đổi sang database staging, còn view và bảng tổng hợp cục bộ phục vụ báo cáo. Điều quan trọng là mỗi lớp cần có chủ sở hữu, cách cập nhật và quy tắc xử lý lỗi rõ ràng.

## 8. Ví dụ thiết kế theo tình huống

### 8.1. Ứng dụng cần tra cứu trạng thái đơn hàng hiện tại

Ứng dụng đặt hàng cần xem trạng thái hiện tại từ database `sales`, nhưng không cần lưu bản sao riêng. `postgres_fdw` là lựa chọn hợp lý nếu số lượng truy vấn và tải nguồn được kiểm soát. Có thể import bảng cần thiết, cấp quyền đọc và tạo view cục bộ làm giao diện ổn định.

Nếu chỉ có một function quản trị cần gửi một lệnh cập nhật từ xa với quy trình được kiểm soát chặt, `dblink` có thể phù hợp. Cần lưu ý giao dịch từ xa không tự động rollback theo giao dịch cục bộ.

### 8.2. Kho phân tích cần dữ liệu đơn hàng lớn

Kho phân tích chạy nhiều báo cáo tổng hợp trên hàng triệu đơn hàng. Nếu mỗi báo cáo đều đọc trực tiếp qua FDW, nguồn có thể chịu tải truy vấn và chi phí truyền dữ liệu lớn. Logical replication có thể chuyển bảng đơn hàng sang database phân tích, hoặc ETL có thể chỉ nạp các trường đã chuẩn hóa cần cho báo cáo.

Subscriber hoặc bảng đích cho phép tạo index, partition và cấu trúc phục vụ truy vấn phân tích. Đổi lại, nhóm vận hành cần theo dõi replication lag hoặc lịch ETL và quản lý thay đổi schema.

### 8.3. Hệ thống cần standby để khôi phục sau sự cố

Nếu mục tiêu là khôi phục cả database cluster khi primary gặp sự cố, physical streaming replication là hướng phù hợp. FDW và `dblink` không tạo standby vật lý và không thay thế quy trình backup/restore.

Nếu chỉ cần một số bảng nghiệp vụ sẵn sàng ở một database khác, logical replication có thể đáp ứng. Tuy nhiên, logical subscriber không tự trở thành bản standby HA có thể promote tương đương physical standby.

## 9. Các lỗi và rủi ro thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Foreign table truy vấn chậm | Lọc hoặc join không được pushdown; mạng chậm; nguồn thiếu index | Dùng `EXPLAIN (VERBOSE)`, giảm cột/dòng truyền, kiểm tra index và ước lượng chi phí. |
| `postgres_fdw` không kết nối được | Sai server option, user mapping, xác thực, TLS hoặc `pg_hba.conf` | Kiểm tra từng lớp kết nối và quyền ở cả hai database. |
| `dblink` báo lỗi kiểu record | Thiếu hoặc khai báo sai danh sách cột trong `AS record(...)` | Định nghĩa đúng tên và kiểu của kết quả từ xa. |
| SQL truyền qua `dblink` lỗi dấu nháy | Chuỗi SQL lồng nhiều cấp quote hoặc ghép literal không an toàn | Dùng dollar quoting khi phù hợp và `format('%L', ...)`, `format('%I', ...)` cho SQL động. |
| Lệnh từ xa đã ghi dù giao dịch cục bộ rollback | Kết nối `dblink` có giao dịch độc lập và lệnh từ xa đã commit | Quản lý giao dịch từ xa rõ ràng; thiết kế đối soát và xử lý bù khi có lỗi. |
| Subscriber không nhận được thay đổi | Subscription lỗi, quyền replication thiếu, mạng lỗi hoặc slot không hoạt động | Kiểm tra trạng thái subscription, log apply worker, replication slot và cấu hình kết nối. |
| Logical replication bị dừng khi update/delete | Bảng nguồn thiếu replica identity phù hợp hoặc subscriber gặp xung đột | Kiểm tra primary key/replica identity và dữ liệu tại subscriber. |
| Subscriber thiếu cột mới | DDL không được logical replication tự truyền | Triển khai migration schema ở subscriber theo thứ tự tương thích. |
| WAL tăng mạnh ở publisher | Replication slot giữ WAL vì subscriber ngừng nhận hoặc apply chậm | Theo dõi slot và lag, khôi phục subscriber hoặc xử lý slot theo quy trình an toàn. |
| Snapshot ETL có dữ liệu trùng hoặc thiếu | Pipeline chạy lại nhưng không có khóa idempotent hoặc watermark đáng tin cậy | Thiết kế upsert, staging, checkpoint và xử lý xóa rõ ràng. |

## 10. Quy trình triển khai và vận hành

Trước khi chọn giải pháp, cần trả lời các câu hỏi sau:

1. Dữ liệu cần mới đến mức nào: tức thời, trễ vài giây/phút hay cập nhật theo lịch?
2. Hệ thống có cần truy vấn được khi nguồn mất kết nối không?
3. Cần truy cập vài bảng hay toàn bộ cluster?
4. Có cần ghi dữ liệu về nguồn hay chỉ đọc?
5. Khối lượng truy vấn và dữ liệu truyền qua mạng dự kiến là bao nhiêu?
6. Có thể chấp nhận schema ở đích trễ hơn nguồn không? Ai quản lý DDL?
7. Cần xử lý thế nào khi kết nối, apply hoặc ETL thất bại?

Sau khi chọn phương án, nên chuẩn bị quy trình vận hành tương ứng:

- **Với `postgres_fdw`**: quản lý foreign server và user mapping bằng migration; kiểm tra quyền; theo dõi thời gian truy vấn, Remote SQL, tải nguồn và lỗi kết nối; cập nhật foreign table khi schema nguồn đổi.
- **Với `dblink`**: kiểm soát danh sách câu SQL từ xa; quản lý vòng đời kết nối; quote dữ liệu đầu vào an toàn; định nghĩa kiểu kết quả; xử lý transaction và lỗi từ xa một cách tường minh.
- **Với logical replication**: quản lý publication/subscription; giám sát replication slot, WAL và lag; triển khai DDL riêng ở subscriber; đồng bộ sequence khi cutover; kiểm tra xung đột và khả năng khôi phục.
- **Với physical replication**: giám sát trạng thái WAL receiver/replay và độ trễ; diễn tập failover/failback; kiểm tra backup và quy trình khôi phục.
- **Với ETL/snapshot**: thiết kế job idempotent; quản lý checkpoint và watermark; ghi nhận số hàng, thời điểm dữ liệu và lỗi; có thể chạy lại mà không nhân đôi hoặc bỏ sót dữ liệu.

Mọi phương án đều cần kiểm thử trong môi trường gần với production về kích thước dữ liệu, quyền, mạng, workload và hành vi khi lỗi. Với tích hợp dữ liệu quan trọng, nên có đối soát định kỳ giữa nguồn và đích, chẳng hạn so sánh số lượng bản ghi, khoảng thời gian cập nhật hoặc tổng kiểm tra theo nhóm dữ liệu.

## 11. Kết luận

`postgres_fdw` cung cấp cách truy vấn bảng từ xa tự nhiên bằng foreign table và có thể tận dụng pushdown của query planner. `dblink` cung cấp cách gửi câu SQL từ xa tường minh, linh hoạt cho các thao tác đặc biệt nhưng đòi hỏi tự quản lý nhiều chi tiết hơn. Sao chép dữ liệu tạo bản dữ liệu cục bộ: ETL phù hợp với snapshot hoặc pipeline biến đổi, logical replication phù hợp với đồng bộ chọn lọc liên tục, còn physical replication phù hợp với standby của toàn cluster.

Quyết định nên dựa trên độ mới dữ liệu, tính sẵn sàng khi nguồn gián đoạn, tải truy vấn, phạm vi cần sao chép, yêu cầu giao dịch và khả năng vận hành. Cũng cần nhớ rằng replication không thay thế backup, FDW không tạo bản sao độc lập và `dblink` không tự kết hợp giao dịch từ xa với giao dịch cục bộ.

## Tài liệu tham khảo

- [PostgreSQL — postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html)
- [PostgreSQL — dblink](https://www.postgresql.org/docs/current/dblink.html)
- [PostgreSQL — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html)
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [PostgreSQL — COPY](https://www.postgresql.org/docs/current/sql-copy.html)
