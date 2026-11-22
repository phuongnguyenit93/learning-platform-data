# Kết nối công cụ BI, ETL và hệ thống phân tích với PostgreSQL

PostgreSQL thường là nguồn dữ liệu giao dịch cho các ứng dụng nghiệp vụ. Công cụ Business Intelligence (BI), nền tảng Extract, Transform, Load (ETL), kho dữ liệu và hệ thống phân tích cần đọc dữ liệu từ PostgreSQL để tạo báo cáo, mô hình dữ liệu và luồng phân tích. Một tích hợp tốt phải giữ được tính nhất quán của dữ liệu, kiểm soát tải lên hệ thống giao dịch, bảo vệ thông tin nhạy cảm và có cách phát hiện khi luồng dữ liệu bị chậm hoặc dừng.

Bài này trình bày các cách kết nối phổ biến, từ truy vấn trực tiếp và xuất dữ liệu theo lô đến đồng bộ thay đổi bằng logical replication hoặc Change Data Capture (CDC). Các ví dụ dùng PostgreSQL SQL và những thành phần có thể gặp trong hệ thống BI/ETL. Tên menu và cấu hình cụ thể của từng sản phẩm có thể khác nhau, nhưng các nguyên tắc về kết nối, quyền, giao dịch, đồng bộ và vận hành vẫn áp dụng tương tự.

## 1. Vai trò của PostgreSQL trong kiến trúc phân tích

Trong một hệ thống điển hình, PostgreSQL phục vụ các giao dịch của ứng dụng: tạo đơn hàng, cập nhật khách hàng, ghi nhận thanh toán và lưu trạng thái xử lý. Hệ thống BI cần tổng hợp dữ liệu theo ngày, khu vực, sản phẩm hoặc nhóm khách hàng. Công cụ ETL/ELT chuyển dữ liệu từ nguồn sang vùng lưu trữ phân tích, sau đó chuẩn hóa và xây dựng các bảng phục vụ báo cáo.

Các thành phần thường gặp gồm:

- **Nguồn giao dịch (OLTP):** PostgreSQL lưu dữ liệu chuẩn hóa và xử lý các thao tác đọc/ghi ngắn của ứng dụng.
- **Công cụ trích xuất:** JDBC, ODBC, libpq, `COPY`, truy vấn SQL, logical replication hoặc một CDC connector đọc thay đổi từ WAL.
- **Vùng staging:** nơi lưu bản sao thô hoặc dữ liệu trung gian trước khi làm sạch và hợp nhất.
- **Kho dữ liệu/lakehouse:** nơi lưu lịch sử và dữ liệu đã chuẩn hóa để phân tích trên phạm vi rộng.
- **Lớp mô hình BI:** định nghĩa chỉ số, chiều phân tích, quan hệ và quyền xem dữ liệu.
- **Công cụ BI:** tạo dashboard, báo cáo, truy vấn ad hoc và lịch gửi báo cáo.
- **Bộ điều phối:** chạy lịch, quản lý phụ thuộc, retry, cảnh báo và theo dõi trạng thái pipeline.

Một luồng đơn giản có thể biểu diễn như sau:

```text
Ứng dụng nghiệp vụ
        |
        v
PostgreSQL OLTP
   |         |
   |         +----> Read replica ----> BI truy vấn trực tiếp
   |
   +----> ETL theo lô / CDC connector
                    |
                    v
              Staging / Raw
                    |
                    v
             Transform / ELT
                    |
                    v
             Data warehouse
                    |
                    v
             Mô hình BI / Dashboard
```

Không phải hệ thống nào cũng cần tất cả thành phần. Một nhóm nhỏ có thể bắt đầu với read replica và công cụ BI. Khi số lượng báo cáo, nguồn dữ liệu và nhu cầu lưu lịch sử tăng, việc đưa dữ liệu sang kho phân tích riêng thường giúp tách tải và quản lý mô hình tốt hơn.

## 2. Phân biệt BI, ETL, ELT và CDC

Các khái niệm này liên quan nhưng giải quyết những phần khác nhau của bài toán.

| Khái niệm | Vai trò | Ví dụ công việc |
|---|---|---|
| BI | Khai thác và trình bày dữ liệu để hỗ trợ quyết định | Dashboard doanh thu, báo cáo tồn kho |
| ETL | Trích xuất, biến đổi rồi nạp dữ liệu vào đích | Đọc đơn hàng, chuẩn hóa mã tiền tệ, ghi vào kho dữ liệu |
| ELT | Nạp dữ liệu thô trước, sau đó biến đổi trong hệ thống đích | Nạp bảng nguồn vào schema `raw`, chạy SQL tạo bảng `mart` |
| CDC | Ghi nhận các thay đổi phát sinh ở nguồn | Phát sự kiện insert/update/delete từ WAL sang Kafka hoặc đích khác |
| Orchestration | Điều phối lịch chạy, phụ thuộc, retry và giám sát | Chạy đồng bộ nguồn trước khi làm mới dashboard |

ETL và ELT mô tả thứ tự biến đổi và nạp. CDC mô tả cách phát hiện thay đổi ở nguồn; CDC có thể cung cấp dữ liệu cho cả ETL lẫn ELT. BI là lớp sử dụng dữ liệu đã được tổ chức để truy vấn và trình bày.

## 3. Chọn phương thức kết nối phù hợp

### Truy vấn trực tiếp qua JDBC hoặc ODBC

Nhiều công cụ BI có PostgreSQL connector tích hợp hoặc hỗ trợ JDBC/ODBC. Công cụ mở kết nối, gửi SQL và nhận tập kết quả. Cách này dễ bắt đầu, phù hợp với dashboard có truy vấn vừa phải và dữ liệu gần thời gian thực.

Ưu điểm là không cần xây dựng pipeline sao chép riêng, dữ liệu được đọc trực tiếp từ PostgreSQL và có thể dùng SQL để kiểm soát phép nối hoặc tổng hợp. Hạn chế là dashboard có thể tạo nhiều truy vấn đồng thời, truy vấn nặng cạnh tranh tài nguyên với ứng dụng giao dịch, và mỗi lần đọc thường chỉ phản ánh trạng thái tại thời điểm truy vấn.

### Read replica

PostgreSQL có thể duy trì standby ở chế độ hot standby để phục vụ truy vấn chỉ đọc. BI kết nối tới replica, nhờ đó giảm tải đọc trên primary. Cần theo dõi replication lag vì báo cáo có thể nhìn thấy dữ liệu chậm hơn primary. Một truy vấn dài trên standby cũng có thể xung đột với việc áp dụng WAL; tùy cấu hình, PostgreSQL có thể hủy truy vấn để tiếp tục recovery hoặc trì hoãn recovery trong giới hạn cấu hình.

### ETL theo lô bằng SQL, `COPY` hoặc connector

Pipeline định kỳ đọc dữ liệu theo khoảng thời gian hoặc khóa tăng dần, ghi vào staging rồi biến đổi ở đích. Cách này phù hợp khi độ trễ vài phút hoặc vài giờ được chấp nhận, hoặc khi cần kiểm soát rõ từng đợt nạp.

### Logical replication và CDC

Logical replication của PostgreSQL phát các thay đổi logic của bảng thông qua publication/subscription. CDC connector cũng có thể đọc logical decoding từ WAL và chuyển sự kiện sang hệ thống khác. Cách này phù hợp với đồng bộ liên tục, nhưng cần quản lý replication slot, quyền, schema evolution và khả năng xử lý lại sự kiện.

### Xuất/nhập dữ liệu theo snapshot

`pg_dump`, `COPY` hoặc export từ công cụ ETL có thể tạo một lần trích xuất nhất quán cho tải ban đầu, di chuyển dữ liệu hoặc báo cáo định kỳ. Với tập dữ liệu lớn, cần lập kế hoạch dung lượng lưu trữ, thời gian chạy và ảnh hưởng I/O.

| Nhu cầu | Phương án thường phù hợp | Điểm cần theo dõi |
|---|---|---|
| Dashboard nhỏ, độ trễ thấp | JDBC/ODBC tới PostgreSQL hoặc read replica | Số kết nối, truy vấn nặng, cache |
| Dashboard nhiều người dùng | Read replica hoặc kho dữ liệu | Lag, tải truy vấn, chi phí hạ tầng |
| Báo cáo theo giờ/ngày | ETL theo lô | Watermark, retry, dữ liệu đến muộn |
| Đồng bộ thay đổi liên tục | Logical replication hoặc CDC | Slot, WAL retention, lag, thứ tự sự kiện |
| Tải ban đầu rất lớn | Snapshot bằng `COPY`/`pg_dump`/connector bulk load | Snapshot nhất quán, dung lượng và thời gian |

## 4. Chuẩn bị PostgreSQL cho kết nối BI và ETL

Trước khi cấu hình công cụ bên ngoài, cần xác định database, schema, bảng được phép đọc, phương thức xác thực, giới hạn kết nối và yêu cầu mạng. Tài khoản BI thường chỉ cần quyền đọc. Tài khoản ETL có thể cần quyền đọc nguồn và quyền ghi ở database đích; không nên dùng một tài khoản superuser cho cả hai vai trò.

### Tạo role chỉ đọc

Ví dụ sau tạo role đăng nhập dành cho công cụ BI. Hãy thay tên database, schema và mật khẩu theo môi trường thực tế; nên cấp mật khẩu qua secret manager hoặc cơ chế xác thực được tổ chức hỗ trợ thay vì lưu trong mã nguồn.

```sql
CREATE ROLE bi_reader LOGIN;

GRANT CONNECT ON DATABASE sales TO bi_reader;

GRANT USAGE ON SCHEMA reporting TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO bi_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA reporting
    GRANT SELECT ON TABLES TO bi_reader;
```

`GRANT SELECT ON ALL TABLES` áp dụng cho các bảng đã tồn tại tại thời điểm chạy. `ALTER DEFAULT PRIVILEGES` ảnh hưởng đến đối tượng được tạo trong tương lai bởi role sở hữu các default privileges đó. Nếu bảng do nhiều role khác nhau tạo, cần cấu hình default privileges tương ứng cho từng role tạo bảng.

Nếu BI cần đọc view, materialized view hoặc sequence metadata, hãy kiểm tra quyền cụ thể của loại đối tượng. Với view, quyền truy cập dữ liệu cơ sở còn phụ thuộc cách định nghĩa view và cơ chế bảo mật áp dụng. Không cấp quyền rộng trên schema ứng dụng chỉ vì công cụ BI cần đọc một vài bảng báo cáo.

### Tách schema phục vụ báo cáo

Có thể tạo schema riêng chứa view và materialized view dành cho BI:

```sql
CREATE SCHEMA reporting AUTHORIZATION reporting_owner;

CREATE VIEW reporting.daily_sales AS
SELECT
    date_trunc('day', created_at)::date AS sales_date,
    count(*) AS order_count,
    sum(total_amount) AS gross_amount
FROM public.orders
WHERE status = 'paid'
GROUP BY date_trunc('day', created_at)::date;
```

Schema báo cáo giúp ổn định hợp đồng dữ liệu cho công cụ BI. Ứng dụng có thể thay đổi bảng nội bộ trong khi view báo cáo duy trì tên cột và ý nghĩa dữ liệu đã thống nhất. Cần quản lý thay đổi view như một phần của migration, vì dashboard và pipeline có thể phụ thuộc vào tên cột, kiểu dữ liệu và ngữ nghĩa của chúng.

### Kiểm soát kết nối mạng và TLS

`listen_addresses` xác định địa chỉ PostgreSQL lắng nghe. `pg_hba.conf` xác định client, database, role và phương thức xác thực được phép. Chỉ mở mạng từ các máy chủ BI/ETL cần thiết; không công khai cổng database ra Internet nếu không có lớp bảo vệ phù hợp.

Ví dụ một dòng `pg_hba.conf` minh họa yêu cầu TLS và SCRAM cho một dải mạng riêng:

```text
hostssl  sales  bi_reader  10.20.30.0/24  scram-sha-256
```

Địa chỉ mạng trên chỉ là ví dụ. Cấu hình thực tế cần khớp subnet của máy chủ công cụ. Với kết nối qua mạng không tin cậy, cấu hình chứng thư TLS và xác minh danh tính máy chủ ở client. Tránh dùng `trust` cho kết nối từ các hệ thống bên ngoài.

### Cấu hình kết nối trong công cụ

Một URI kết nối PostgreSQL có dạng:

```text
postgresql://bi_reader@db-reporting.internal:5432/sales?sslmode=verify-full
```

Mật khẩu có thể được yêu cầu riêng trong giao diện công cụ hoặc lấy từ secret manager. `verify-full` yêu cầu client xác minh chứng thư và hostname; máy chủ phải có chứng thư hợp lệ và tên khớp. Nếu dùng JDBC, các thuộc tính SSL được cấu hình theo driver và công cụ BI.

Các thông số cần cung cấp thường gồm hostname, port, database, username, authentication, SSL mode, schema mặc định và giới hạn timeout. Kiểm tra phiên bản driver tương thích với phiên bản PostgreSQL và môi trường chạy của công cụ.

## 5. Kết nối BI trực tiếp và thiết kế lớp dữ liệu báo cáo

Kết nối thành công mới chỉ là bước đầu. Công cụ BI cần biết bảng nào là fact, bảng nào là dimension, quan hệ giữa chúng, múi giờ báo cáo và định nghĩa các chỉ số.

### Dùng view làm hợp đồng dữ liệu

Thay vì để mỗi dashboard tự nối nhiều bảng nghiệp vụ, có thể tạo view với tên và kiểu dữ liệu ổn định:

```sql
CREATE VIEW reporting.order_metrics AS
SELECT
    o.id AS order_id,
    o.created_at,
    o.customer_id,
    c.region_code,
    o.total_amount,
    o.currency_code
FROM public.orders AS o
JOIN public.customers AS c
  ON c.id = o.customer_id
WHERE o.status = 'paid';
```

View trên là một ví dụ đơn giản. Trong hệ thống lớn, nên cân nhắc việc join và tổng hợp có thể gây tải cao, đồng thời xác định rõ cách xử lý đơn hàng bị hoàn tiền, hủy hoặc đổi trạng thái sau khi đã thanh toán.

### Materialized view cho phép tổng hợp định kỳ

Materialized view lưu kết quả truy vấn trên đĩa và được làm mới theo lịch hoặc khi cần:

```sql
CREATE MATERIALIZED VIEW reporting.sales_by_day AS
SELECT
    created_at::date AS sales_date,
    currency_code,
    count(*) AS order_count,
    sum(total_amount) AS total_amount
FROM public.orders
WHERE status = 'paid'
GROUP BY created_at::date, currency_code;

CREATE UNIQUE INDEX sales_by_day_key
    ON reporting.sales_by_day (sales_date, currency_code);
```

Có thể dùng `REFRESH MATERIALIZED VIEW` để làm mới. `REFRESH MATERIALIZED VIEW CONCURRENTLY` cho phép truy vấn tiếp tục đọc materialized view trong quá trình refresh, nhưng yêu cầu unique index phù hợp bao phủ các hàng và có những giới hạn riêng. Refresh vẫn tiêu thụ tài nguyên và cần kế hoạch lịch chạy.

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.sales_by_day;
```

Materialized view không tự cập nhật theo từng thay đổi nguồn. Dashboard cần hiển thị thời điểm dữ liệu được làm mới để người dùng hiểu độ mới của số liệu.

### Chuẩn hóa thời gian, tiền tệ và định nghĩa chỉ số

`timestamp with time zone` (`timestamptz`) lưu một thời điểm tuyệt đối; khi hiển thị, PostgreSQL chuyển đổi theo timezone của session. Nên thống nhất quy tắc lưu và hiển thị thời gian, ví dụ lưu thời điểm giao dịch bằng `timestamptz` rồi quy đổi sang múi giờ báo cáo trong mô hình BI.

Tiền tệ cần đi kèm mã tiền tệ. Không cộng trực tiếp số tiền thuộc nhiều đồng tiền nếu chưa quy đổi theo tỷ giá và thời điểm quy đổi đã xác định. Với số liệu tài chính, `numeric` thường phù hợp hơn kiểu dấu phẩy động nhị phân khi cần phép tính thập phân chính xác.

Định nghĩa chỉ số phải được thống nhất. Ví dụ “doanh thu” có thể là tổng giá trị đơn đã thanh toán, doanh thu sau hoàn tiền, hay doanh thu chưa bao gồm thuế. Nếu mỗi dashboard dùng điều kiện lọc khác nhau, số liệu giữa các bộ phận sẽ không khớp dù kết nối kỹ thuật đều hoạt động.

## 6. ETL theo lô: trích xuất dữ liệu nhất quán

Một pipeline theo lô thường có các bước: xác định phạm vi dữ liệu, đọc từ PostgreSQL, ghi vào staging, kiểm tra số lượng và chất lượng, biến đổi, rồi commit dữ liệu vào đích. Pipeline cần lưu trạng thái tiến độ để có thể chạy lại an toàn khi gặp lỗi.

### Trích xuất bằng `COPY`

`COPY` có thể xuất dữ liệu hiệu quả hơn việc ứng dụng đọc từng hàng riêng lẻ. Ví dụ xuất một tập dữ liệu đã lọc:

```sql
COPY (
    SELECT id, customer_id, created_at, total_amount, currency_code
    FROM public.orders
    WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
      AND created_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
) TO STDOUT WITH (FORMAT csv, HEADER true);
```

`COPY TO STDOUT` gửi dữ liệu qua kết nối client; chương trình ETL hoặc driver chịu trách nhiệm lưu luồng dữ liệu. `COPY ... TO '/path/file.csv'` ghi file trên máy chủ PostgreSQL và yêu cầu quyền hệ điều hành cùng quyền PostgreSQL phù hợp, vì vậy không nên dùng cú pháp file server-side khi không kiểm soát được máy chủ.

Khi nạp dữ liệu, có thể dùng `COPY ... FROM STDIN` vào bảng staging. Nên nạp vào bảng staging có kiểu dữ liệu và quy tắc kiểm tra phù hợp, sau đó mới merge vào bảng đích.

### Incremental load bằng watermark

Để tránh đọc lại toàn bộ bảng trong mỗi lần chạy, pipeline có thể lưu watermark, chẳng hạn giá trị `updated_at` lớn nhất đã xử lý. Lần tiếp theo đọc các hàng có `updated_at` lớn hơn watermark.

```sql
SELECT
    id,
    customer_id,
    status,
    total_amount,
    updated_at
FROM public.orders
WHERE updated_at >= :window_start
  AND updated_at <  :window_end
ORDER BY updated_at, id;
```

Khoảng thời gian có thể chồng lấn một chút để thu nhận bản ghi đến muộn hoặc cập nhật có timestamp gần ranh giới. Đích phải xử lý trùng lặp bằng khóa tự nhiên/khóa chính và thao tác upsert. Không nên chỉ dựa vào timestamp nếu hệ thống có thể cập nhật dữ liệu mà không đổi `updated_at`, đồng hồ giữa các hệ thống lệch nhau, hoặc nhiều hàng có cùng timestamp.

Watermark cần được cập nhật sau khi dữ liệu đã được ghi và xác nhận thành công ở đích. Nếu ghi watermark trước khi commit dữ liệu, một lỗi ở bước nạp có thể khiến pipeline bỏ qua một khoảng dữ liệu trong lần chạy sau.

### Upsert vào staging hoặc bảng đích

`INSERT ... ON CONFLICT` giúp hợp nhất dữ liệu lặp lại theo khóa duy nhất:

```sql
INSERT INTO analytics.orders (
    order_id,
    customer_id,
    status,
    total_amount,
    source_updated_at
)
VALUES (
    :order_id,
    :customer_id,
    :status,
    :total_amount,
    :source_updated_at
)
ON CONFLICT (order_id) DO UPDATE
SET customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    total_amount = EXCLUDED.total_amount,
    source_updated_at = EXCLUDED.source_updated_at
WHERE analytics.orders.source_updated_at
      <= EXCLUDED.source_updated_at;
```

Điều kiện so sánh timestamp giúp tránh ghi đè một phiên bản mới hơn bằng sự kiện cũ đến trễ. Nếu nguồn không có phiên bản hoặc timestamp đáng tin cậy, cần thiết kế quy tắc thứ tự khác. Đích cũng nên lưu thông tin nguồn và thời điểm nạp để hỗ trợ điều tra.

### Xử lý xóa

Incremental load chỉ dựa trên `updated_at` thường không phát hiện được hàng đã bị xóa vật lý khỏi nguồn. Có thể dùng cột trạng thái xóa mềm (`deleted_at`, `is_deleted`), bảng nhật ký thay đổi hoặc CDC để truyền sự kiện delete. Nếu không có cơ chế này, dữ liệu đã xóa ở nguồn có thể tiếp tục tồn tại ở kho dữ liệu.

### Snapshot nhất quán và nhiều truy vấn

Nếu pipeline trích xuất nhiều bảng có quan hệ và cần cùng một điểm nhìn dữ liệu, cần cân nhắc transaction isolation. `REPEATABLE READ` cung cấp snapshot ổn định trong một transaction trên cùng database:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM public.orders;
SELECT count(*) FROM public.order_items;

COMMIT;
```

Các truy vấn trong transaction nhìn thấy cùng snapshot. Giữ transaction đọc mở quá lâu có thể cản trở vacuum thu hồi phiên bản hàng cũ và làm tăng nguy cơ phình bảng, vì vậy cần giới hạn thời gian trích xuất hoặc sử dụng cơ chế snapshot phù hợp của connector.

## 7. Dùng logical replication cho đồng bộ liên tục

Logical replication cho phép sao chép thay đổi ở mức bảng từ publisher sang subscriber. Publisher định nghĩa publication gồm các bảng cần phát. Subscriber tạo subscription để nhận dữ liệu và áp dụng thay đổi.

### Chuẩn bị publisher

Logical replication cần cấu hình WAL phù hợp, bao gồm `wal_level = logical`, cùng giới hạn cho replication slots và WAL senders theo quy mô hệ thống. Một số thay đổi cấu hình cần restart PostgreSQL. Kiểm tra tài liệu phiên bản đang chạy trước khi thay đổi tham số.

Tạo publication:

```sql
CREATE PUBLICATION analytics_pub
FOR TABLE public.customers, public.orders, public.order_items;
```

Publication có thể giới hạn danh sách bảng. Quyền tạo publication và quyền truy cập bảng phụ thuộc cấu hình, phiên bản và mô hình quyền. Nên tạo publication bằng role quản trị dữ liệu phù hợp và kiểm soát rõ bảng được công bố.

### Chuẩn bị subscriber

Trên database subscriber, tạo subscription trỏ đến publisher:

```sql
CREATE SUBSCRIPTION analytics_sub
CONNECTION 'host=pg-primary.internal port=5432 dbname=sales user=replicator sslmode=verify-full'
PUBLICATION analytics_pub;
```

Thông tin kết nối trên là ví dụ; mật khẩu nên được cung cấp qua phương thức quản lý secret của môi trường. Khi tạo subscription, PostgreSQL có thể tạo replication slot và thực hiện initial table synchronization theo tùy chọn. Cần bảo đảm schema và các bảng đích ở subscriber tương thích với bảng nguồn trước khi đồng bộ.

Logical replication thường yêu cầu role phía publisher có quyền đăng nhập, quyền `REPLICATION` và quyền `SELECT` trên các bảng được đồng bộ theo cơ chế của phiên bản PostgreSQL. Cần cấu hình `pg_hba.conf` để cho phép kết nối replication từ subscriber với xác thực và TLS phù hợp.

### Kiểm tra trạng thái replication

Trên publisher, có thể xem các kết nối gửi WAL:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Trên subscriber, xem trạng thái subscription:

```sql
SELECT
    subname,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

Tên và trường trong các view thống kê có thể thay đổi theo phiên bản. Kiểm tra catalog trên phiên bản đang dùng trước khi xây dựng dashboard giám sát.

### Các giới hạn cần biết

Logical replication tích hợp của PostgreSQL sao chép thay đổi dữ liệu cho các bảng đã đăng ký, nhưng không tự đồng bộ toàn bộ DDL. Khi thêm cột, đổi kiểu hoặc thay đổi schema, cần triển khai tương ứng ở subscriber theo thứ tự an toàn. Sequence state và large objects không được đồng bộ như các thay đổi hàng thông thường. Các thao tác DDL, role, quyền và cấu hình cũng cần quản lý riêng.

Mặc định, bảng được publish cần replica identity để xác định hàng khi cập nhật hoặc xóa; khóa chính thường là lựa chọn phù hợp. Nếu bảng không có khóa chính, có thể cân nhắc `REPLICA IDENTITY FULL`, nhưng điều này có thể tăng lượng dữ liệu WAL và chi phí xử lý vì PostgreSQL cần dùng toàn bộ hàng làm định danh.

Logical replication không tự giải quyết xung đột nếu nhiều bên cùng ghi vào dữ liệu subscriber. Thiết kế phổ biến là publisher là nguồn ghi chính, subscriber chỉ nhận dữ liệu. Nếu subscriber cần cho phép ghi, phải thiết kế cơ chế phân vùng quyền sở hữu dữ liệu và xử lý xung đột riêng.

## 8. CDC connector và luồng sự kiện

Một CDC connector có thể đọc logical decoding từ WAL, chuyển thay đổi thành sự kiện và gửi đến hệ thống trung gian như message broker hoặc đích phân tích. Công cụ downstream có thể lưu sự kiện thô, cập nhật bảng hiện tại hoặc xây dựng lịch sử thay đổi.

Một sự kiện CDC thường mang thông tin:

- Schema và tên bảng nguồn.
- Loại thao tác: insert, update hoặc delete.
- Khóa định danh hàng.
- Giá trị trước/sau nếu connector và cấu hình cung cấp.
- Vị trí log hoặc metadata thứ tự như LSN.
- Thời điểm sự kiện và thông tin transaction nếu được hỗ trợ.

Không nên giả định mọi connector đều phát cùng cấu trúc sự kiện hoặc cùng semantics. Hãy xác định rõ cách connector xử lý snapshot ban đầu, transaction lớn, schema changes, tombstone, retry và offset commit.

### Snapshot ban đầu và tiếp tục đọc WAL

Khi bắt đầu CDC trên một bảng đã có dữ liệu, connector thường cần snapshot để nạp trạng thái hiện tại, đồng thời thiết lập vị trí WAL để tiếp tục nhận thay đổi sau snapshot. Cơ chế phối hợp snapshot và WAL rất quan trọng để tránh mất hoặc nhân đôi thay đổi ở ranh giới. Dùng quy trình snapshot được connector hỗ trợ; không tự ghép một lần `SELECT` tùy ý với một vị trí WAL không liên quan.

### Idempotency và xử lý sự kiện lặp

Consumer có thể nhận lại sự kiện khi retry hoặc sau khi khởi động lại. Hệ thống đích nên xử lý idempotent, ví dụ lưu khóa sự kiện/LSN hoặc upsert theo khóa hàng và phiên bản. Đừng dựa vào giả định “exactly once” xuyên suốt PostgreSQL, broker, connector và kho dữ liệu nếu toàn bộ chuỗi không có giao thức giao dịch chung.

Một mô hình thường dùng là:

1. Ghi sự kiện vào bảng raw kèm source, table, key và metadata vị trí.
2. Dùng transaction ở đích để cập nhật bảng hiện tại và đánh dấu sự kiện đã áp dụng.
3. Dùng khóa duy nhất để ngăn áp dụng lại cùng sự kiện.
4. Lưu tombstone hoặc trạng thái xóa để downstream hiểu hàng đã bị xóa.
5. Có quy trình replay từ offset/LSN đã lưu khi cần khôi phục.

### Replication slot và nguy cơ giữ WAL

Replication slot giữ lại WAL mà consumer chưa xác nhận đã xử lý. Nếu connector dừng lâu, slot không tiến lên và WAL có thể tích tụ trên publisher, làm đầy đĩa. Cần giám sát slot, lượng WAL được giữ, thời gian consumer không hoạt động và dung lượng filesystem.

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal
FROM pg_replication_slots;
```

`restart_lsn` cho biết vị trí WAL sớm nhất slot còn cần giữ. Biểu thức trên ước lượng khoảng WAL tính từ vị trí hiện tại đến `restart_lsn`; hãy kiểm tra kiểu dữ liệu và tính khả dụng của các cột theo phiên bản. Không xóa slot đang được sử dụng để giải phóng dung lượng một cách tùy tiện: việc đó có thể làm consumer không thể tiếp tục từ vị trí cũ và buộc phải tạo lại snapshot.

## 9. Tích hợp qua Foreign Data Wrapper

Foreign Data Wrapper (FDW) cho phép PostgreSQL truy vấn dữ liệu ở hệ thống bên ngoài thông qua foreign table. `postgres_fdw` thường được dùng để truy cập một PostgreSQL server khác.

Ví dụ tạo extension, server và user mapping:

```sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER source_sales
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (host 'pg-source.internal', port '5432', dbname 'sales');

CREATE USER MAPPING FOR bi_reader
    SERVER source_sales
    OPTIONS (user 'report_reader', password 'managed-outside-source');

CREATE SCHEMA source_sales_fdw;

IMPORT FOREIGN SCHEMA reporting
    FROM SERVER source_sales
    INTO source_sales_fdw;
```

Chuỗi password trong ví dụ chỉ minh họa vị trí cấu hình; môi trường thực tế cần dùng cơ chế lưu secret phù hợp và giới hạn quyền truy cập user mapping. Foreign table cho phép truy vấn dữ liệu từ xa nhưng không tự biến nguồn thành kho dữ liệu. Hiệu năng phụ thuộc khả năng pushdown điều kiện, số hàng truyền qua mạng, thống kê và tải của server từ xa.

FDW phù hợp với truy vấn liên kết có kiểm soát hoặc tích hợp nguồn nhỏ. Nếu dashboard chạy nhiều truy vấn nặng qua FDW, có thể tạo tải lên cả hai database và phụ thuộc vào độ ổn định mạng. Với phân tích khối lượng lớn hoặc cần lịch sử, sao chép dữ liệu sang kho phân tích thường dễ kiểm soát hơn.

## 10. Tối ưu hiệu năng cho workload phân tích

Truy vấn BI thường đọc nhiều hàng, join nhiều bảng và tổng hợp theo nhóm. Điều này khác với truy vấn OLTP thường truy cập ít hàng qua index. Cần thiết kế để workload phân tích không làm suy giảm độ trễ giao dịch.

### Tạo index theo bộ lọc và phép nối thực tế

Ví dụ dashboard lọc đơn hàng đã thanh toán theo thời gian:

```sql
CREATE INDEX orders_paid_created_at_idx
    ON public.orders (created_at)
    WHERE status = 'paid';
```

Partial index chỉ lưu các hàng thỏa điều kiện. Nó có thể hữu ích khi dashboard thường lọc đúng `status = 'paid'` và điều kiện truy vấn tương thích với predicate. Không nên tạo index cho mọi cột được BI kéo vào báo cáo; mỗi index làm tăng chi phí ghi và bảo trì.

### Đọc kế hoạch thực thi

Sử dụng `EXPLAIN` để hiểu kế hoạch. `EXPLAIN ANALYZE` thực thi truy vấn thật, vì vậy hãy cẩn trọng với truy vấn nặng hoặc có tác dụng phụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    date_trunc('day', created_at)::date AS sales_date,
    sum(total_amount)
FROM public.orders
WHERE status = 'paid'
  AND created_at >= now() - interval '30 days'
GROUP BY 1
ORDER BY 1;
```

Kiểm tra số hàng ước tính so với thực tế, loại scan, join strategy, buffer hit/read và thời gian từng node. Nếu thống kê lỗi thời hoặc dữ liệu lệch phân bố, `ANALYZE` có thể giúp planner ước lượng tốt hơn.

### Giới hạn truy vấn và kết nối

Đặt timeout phù hợp cho role BI để truy vấn bất thường không chiếm tài nguyên quá lâu:

```sql
ALTER ROLE bi_reader SET statement_timeout = '2min';
ALTER ROLE bi_reader SET idle_in_transaction_session_timeout = '1min';
```

Các giá trị trên chỉ là ví dụ; hãy căn cứ SLA dashboard và đặc điểm truy vấn. `statement_timeout` giới hạn thời gian một câu lệnh. `idle_in_transaction_session_timeout` ngắt session ở trạng thái idle trong transaction; điều này giúp tránh transaction mở lâu nhưng cần kiểm tra khả năng tương thích với client.

Dùng connection pool hoặc giới hạn concurrency của công cụ BI để tránh tạo hàng trăm kết nối đồng thời. Pooler ở transaction pooling mode có một số hạn chế với session state, temporary table, prepared statement và các tính năng phụ thuộc session; cần xác nhận chế độ pooling tương thích với driver và BI tool.

### Theo dõi truy vấn và tài nguyên

`pg_stat_activity` cho biết session và truy vấn đang chạy. `pg_stat_database` cung cấp số liệu tổng hợp theo database. `pg_stat_statements` (khi được cài và cấu hình) giúp tổng hợp truy vấn theo mẫu để tìm workload tốn thời gian. Kết hợp các số liệu này với CPU, RAM, I/O, dung lượng đĩa, WAL và replication lag để tìm nguyên nhân đầy đủ.

Không nên chỉ tăng `work_mem` toàn cục để cải thiện một dashboard. `work_mem` có thể được dùng cho nhiều node sort/hash trong một truy vấn và nhiều session cùng lúc, nên tổng mức tiêu thụ bộ nhớ có thể tăng nhanh. Có thể điều chỉnh theo role hoặc session cho workload đã đo đạc.

## 11. Bảo mật và quản trị dữ liệu phân tích

Kho dữ liệu thường tập trung thông tin từ nhiều hệ thống, khiến tác động của việc lộ dữ liệu có thể lớn. Phải phân loại dữ liệu và xác định ai được xem từng nhóm thông tin.

### Nguyên tắc quyền tối thiểu

- BI reader chỉ có quyền đọc các view hoặc bảng báo cáo cần thiết.
- ETL reader chỉ đọc schema nguồn được chỉ định.
- ETL writer chỉ ghi vào schema staging hoặc database đích cần thiết.
- Role quản trị migration tách khỏi tài khoản runtime của pipeline.
- Tài khoản ứng dụng, BI và CDC không dùng chung mật khẩu hoặc quyền.

### Row-Level Security

Row-Level Security (RLS) có thể giới hạn hàng mà role được phép xem:

```sql
ALTER TABLE reporting.customer_sales ENABLE ROW LEVEL SECURITY;

CREATE POLICY customer_sales_region_policy
ON reporting.customer_sales
FOR SELECT
TO regional_bi_reader
USING (region_code = current_setting('app.region_code', true));
```

Ví dụ này cần được triển khai cẩn thận. Người dùng có quyền tự đặt session variable có thể thay đổi `app.region_code`; vì vậy không được xem custom setting là danh tính đáng tin cậy nếu client có thể tùy ý điều khiển. Cần dùng cơ chế ánh xạ danh tính an toàn, role riêng theo vùng hoặc lớp truy cập kiểm soát. Table owner, superuser và role có `BYPASSRLS` có thể bỏ qua RLS trong các trường hợp tương ứng; hãy kiểm tra quyền thực tế của tài khoản kết nối.

### Ẩn danh và giảm dữ liệu

Nếu dashboard chỉ cần nhóm tuổi, khu vực hoặc số lượng khách hàng, không nên trích xuất email, số điện thoại, địa chỉ chi tiết hoặc thông tin định danh không cần thiết. Có thể tạo view đã loại bỏ hoặc che dữ liệu nhạy cảm trước khi cấp quyền cho BI. Dữ liệu ở staging, file export, log và bản sao lưu cũng cần được bảo vệ như dữ liệu nguồn.

### Quản lý secret và audit

Không commit password, private key hoặc connection string có thông tin xác thực vào Git, notebook, file cấu hình chia sẻ hay log pipeline. Dùng secret manager, xoay vòng thông tin xác thực và giới hạn người có quyền đọc secret. Ghi nhận lịch sử tạo role, thay đổi quyền, publication, subscription và cấu hình kết nối theo quy trình quản trị.

## 12. Schema evolution và hợp đồng dữ liệu

Pipeline phụ thuộc vào tên bảng, tên cột, kiểu dữ liệu, nullability và ý nghĩa nghiệp vụ. Một migration có thể làm pipeline lỗi dù ứng dụng vẫn hoạt động bình thường.

### Thay đổi schema có kiểm soát

Khi thêm cột mới, hãy cân nhắc triển khai theo giai đoạn: tạo cột có thể nullable hoặc có default phù hợp, cập nhật producer, backfill dữ liệu cũ, cập nhật pipeline và BI model, rồi mới áp dụng constraint chặt hơn. Với logical replication, cần triển khai schema tương ứng ở subscriber theo thứ tự phù hợp vì DDL không tự được phát như thay đổi hàng thông thường.

### Dùng view để ổn định interface

View báo cáo có thể che giấu thay đổi cấu trúc bảng nguồn. Nếu cần đổi tên hoặc kiểu cột đầu ra, nên tạo phiên bản view mới hoặc phối hợp thay đổi consumer trước khi bỏ cột cũ. Đừng đổi ngữ nghĩa một cột mà vẫn giữ tên nếu downstream sẽ hiểu sai số liệu.

### Kiểm tra hợp đồng dữ liệu

Pipeline nên kiểm tra các điều kiện như:

- Cột bắt buộc không có `NULL` ngoài dự kiến.
- Khóa chính hoặc khóa nghiệp vụ không bị trùng.
- Mã trạng thái thuộc tập giá trị hợp lệ.
- Khóa ngoại có tỷ lệ match phù hợp.
- Tổng số hàng và tổng tiền nằm trong khoảng hợp lý so với kỳ trước.
- Timestamp nằm trong khoảng thời gian mong đợi.

Các kiểm tra này là kiểm soát dữ liệu của pipeline, không thay thế constraint ở PostgreSQL. Constraint bảo vệ dữ liệu tại nguồn; kiểm tra pipeline bảo vệ tính đúng đắn của bản sao và mô hình phân tích.

## 13. Điều phối pipeline, retry và phục hồi

Một pipeline sản xuất cần có trạng thái chạy, log, metric, retry có giới hạn và cơ chế cảnh báo. Mỗi lần chạy nên lưu `run_id`, thời điểm bắt đầu/kết thúc, watermark đầu/cuối, số hàng đọc/ghi, số lỗi và phiên bản mã pipeline.

### Thiết kế bước chạy có thể lặp lại

Một pipeline có thể thất bại sau khi đã ghi một phần dữ liệu vào đích. Nếu chạy lại tạo bản ghi trùng hoặc cộng dồn chỉ số lần thứ hai, kết quả sẽ sai. Thiết kế idempotent bằng khóa duy nhất, upsert, staging theo `run_id` và transaction publish kết quả sau khi kiểm tra.

Một mẫu xử lý theo lô:

1. Tạo bản ghi điều phối cho `run_id` và lưu watermark đầu vào.
2. Trích xuất vào staging gắn với `run_id`.
3. Kiểm tra số hàng, kiểu dữ liệu, khóa và phạm vi thời gian.
4. Merge/upsert staging vào bảng đích trong transaction phù hợp.
5. Chỉ cập nhật watermark sau khi merge thành công.
6. Ghi metric và đánh dấu lần chạy hoàn tất.

### Retry và dead-letter

Retry hữu ích với lỗi mạng tạm thời, timeout hoặc dịch vụ đích gián đoạn. Không retry vô hạn các lỗi dữ liệu cố định như vi phạm kiểu hoặc khóa duy nhất. Sự kiện không thể xử lý có thể được đưa vào dead-letter queue hoặc bảng lỗi kèm payload, mã lỗi và thời điểm; cần kiểm soát quyền truy cập vì payload có thể chứa dữ liệu nhạy cảm.

### Đối soát nguồn và đích

Đối soát không chỉ đếm tổng số hàng. Có thể so sánh theo phân vùng ngày, trạng thái, tenant hoặc checksum theo nhóm. Với dữ liệu giao dịch, đối chiếu cả số lượng và tổng giá trị theo mã tiền tệ. Chênh lệch cần được phân loại: độ trễ bình thường, dữ liệu đến muộn, xóa chưa được truyền, lỗi transform hay mất sự kiện.

## 14. Giám sát vận hành

Nên xây dashboard vận hành cho cả PostgreSQL và pipeline. Các tín hiệu quan trọng gồm:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Kết nối | Số session, session chờ, lỗi đăng nhập | Phát hiện cạn connection hoặc cấu hình xác thực sai |
| Truy vấn | Thời gian p95/p99, truy vấn chậm, buffer read | Phát hiện dashboard gây tải cao |
| Pipeline batch | Thời gian chạy, số hàng đọc/ghi, watermark | Phát hiện job chậm hoặc bỏ lỡ khoảng dữ liệu |
| CDC | Consumer lag, offset/LSN, tuổi slot, WAL giữ lại | Phát hiện luồng thay đổi bị đình trệ |
| Replica | Replay lag, trạng thái standby, conflict | Đánh giá độ mới của dữ liệu đọc |
| Chất lượng | Số hàng lỗi, khóa trùng, tỷ lệ null, chênh lệch đối soát | Phát hiện dữ liệu không hợp lệ |
| Hạ tầng | CPU, RAM, I/O, dung lượng filesystem | Phát hiện nghẽn hoặc nguy cơ hết đĩa |

Một cảnh báo hữu ích phải gắn với hành động cụ thể. Ví dụ, cảnh báo replication slot giữ WAL vượt ngưỡng cần chỉ rõ slot nào, consumer nào và dung lượng còn trống. Cảnh báo pipeline trễ cần nêu watermark kỳ vọng, watermark thực tế và lần chạy gần nhất.

### Một số truy vấn giám sát hữu ích

Đếm kết nối theo trạng thái:

```sql
SELECT
    datname,
    usename,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY sessions DESC;
```

Tìm truy vấn chạy lâu:

```sql
SELECT
    pid,
    usename,
    application_name,
    now() - query_start AS duration,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start < now() - interval '1 minute'
ORDER BY query_start;
```

Kiểm tra tiến độ COPY khi phiên bản PostgreSQL cung cấp view thống kê tương ứng:

```sql
SELECT *
FROM pg_stat_progress_copy;
```

Các truy vấn thống kê có thể cần quyền quan sát session khác, chẳng hạn quyền thành viên role giám sát hoặc quyền quản trị phù hợp. Không cấp quyền superuser chỉ để hiển thị dashboard vận hành.

## 15. Xử lý lỗi kết nối thường gặp

### `connection refused`

Kiểm tra PostgreSQL đang chạy, đúng port, `listen_addresses`, firewall, routing và hostname. Nếu client chạy trong container, `localhost` thường trỏ về chính container client chứ không phải container database.

### `no pg_hba.conf entry`

Kiểm tra địa chỉ IP client mà server thực sự nhìn thấy, database, username, thứ tự rule trong `pg_hba.conf` và việc kết nối có dùng TLS hay không. Sau khi sửa file, thực hiện reload cấu hình nếu thay đổi đó hỗ trợ reload.

### Lỗi chứng thư TLS

Kiểm tra CA mà client tin cậy, thời hạn chứng thư, hostname/SAN và chế độ SSL. Không giải quyết lỗi chứng thư bằng cách hạ xuống chế độ không xác minh trong môi trường production.

### `password authentication failed`

Xác nhận role tồn tại, password/secret đúng, secret có được xoay vòng hay không và client có đang đọc nhầm biến môi trường hoặc secret version cũ không. Kiểm tra phương thức xác thực được chọn trong `pg_hba.conf`.

### `too many connections`

Xem `max_connections`, số session theo role/database và hành vi đóng kết nối của công cụ. Cân nhắc connection pool, giới hạn concurrency, giảm số worker và tách workload. Tăng `max_connections` đơn thuần có thể làm tăng bộ nhớ và tranh chấp tài nguyên.

### BI đọc dữ liệu cũ

Kiểm tra công cụ có cache kết quả hay không, thời điểm refresh, timezone, transaction snapshot, replica lag và watermark pipeline. Phân biệt cache ở BI với độ trễ ở database hoặc kho dữ liệu.

### CDC không tiến triển

Kiểm tra connector còn chạy, quyền replication, slot có active hay không, LSN/offset có tiến lên không, lỗi schema và dung lượng WAL. Không xóa slot trước khi xác định khả năng khôi phục consumer.

## 16. Quy trình triển khai tích hợp mới

Một quy trình triển khai có thể thực hiện theo thứ tự sau:

1. **Xác định mục tiêu dữ liệu:** dashboard cần bảng nào, độ trễ tối đa, thời gian lưu lịch sử và định nghĩa chỉ số.
2. **Chọn kiến trúc:** truy vấn trực tiếp, read replica, ETL theo lô, logical replication, CDC hoặc FDW.
3. **Thiết kế quyền:** tạo role riêng, giới hạn schema/bảng, cấu hình TLS và mạng.
4. **Chuẩn hóa hợp đồng:** thống nhất tên cột, kiểu dữ liệu, timezone, currency, khóa và ngữ nghĩa chỉ số.
5. **Kiểm thử tải:** chạy truy vấn đại diện, đo concurrency, latency, I/O và ảnh hưởng đến workload giao dịch.
6. **Thiết lập pipeline:** snapshot ban đầu, incremental load hoặc CDC; lưu watermark/offset và thiết kế idempotency.
7. **Kiểm tra chất lượng:** kiểm tra khóa, null, số lượng, tổng hợp và đối soát nguồn/đích.
8. **Thiết lập giám sát:** dashboard, cảnh báo lag, WAL retention, lỗi job, truy vấn chậm và dung lượng.
9. **Diễn tập phục hồi:** dừng connector, chạy lại job, replay sự kiện, khôi phục từ snapshot và xác nhận không mất dữ liệu.
10. **Bàn giao vận hành:** ghi rõ owner, SLA, quy trình xoay secret, thay đổi schema và xử lý sự cố.

## 17. Ví dụ thiết kế pipeline đơn hàng từ PostgreSQL sang kho dữ liệu

Giả sử ứng dụng lưu `orders` trong PostgreSQL. Kho dữ liệu cần bảng `fact_orders` để phân tích số đơn, doanh thu và tỷ lệ hủy theo ngày, khu vực và tiền tệ.

### Bảng đích và metadata nạp

```sql
CREATE TABLE analytics.fact_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint,
    order_status text NOT NULL,
    created_at timestamptz NOT NULL,
    total_amount numeric(14, 2),
    currency_code char(3) NOT NULL,
    source_updated_at timestamptz NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analytics.etl_watermark (
    pipeline_name text PRIMARY KEY,
    last_updated_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

`fact_orders` giữ trạng thái hiện tại của đơn hàng. Nếu cần phân tích lịch sử mọi lần đổi trạng thái, cần thêm bảng lịch sử dạng event hoặc Slowly Changing Dimension (SCD) thay vì chỉ ghi đè hàng hiện tại.

### Trích xuất khoảng dữ liệu

Giả sử lần chạy đọc khoảng `[window_start, window_end)`. Nên chọn `window_start` có chồng lấn so với watermark trước để giảm nguy cơ bỏ sót sự kiện đến muộn. Đích upsert theo `order_id` và chỉ áp dụng phiên bản có `source_updated_at` mới hơn hoặc bằng.

```sql
SELECT
    id,
    customer_id,
    status,
    created_at,
    total_amount,
    currency_code,
    updated_at
FROM public.orders
WHERE updated_at >= :window_start
  AND updated_at < :window_end
ORDER BY updated_at, id;
```

Nếu nguồn có xóa vật lý, cần bổ sung bảng tombstone hoặc chuyển sang CDC để đích biết hàng đã bị xóa. Nếu nguồn có nhiều giao dịch cập nhật cùng một đơn, timestamp độ phân giải thấp có thể không đủ để phân định thứ tự; cân nhắc version hoặc LSN.

### Kiểm tra và publish

Sau khi nạp staging, kiểm tra khóa trùng, trường bắt buộc, giá trị tiền tệ và phạm vi timestamp. Sau đó merge vào `fact_orders`, cập nhật watermark trong transaction đích và đánh dấu `run_id` hoàn tất. Nếu merge thất bại, watermark không được tiến lên.

### Dashboard

Dashboard có thể tổng hợp theo ngày và tiền tệ:

```sql
SELECT
    created_at::date AS order_date,
    currency_code,
    count(*) FILTER (WHERE order_status = 'paid') AS paid_orders,
    sum(total_amount) FILTER (WHERE order_status = 'paid') AS paid_amount,
    count(*) FILTER (WHERE order_status = 'cancelled') AS cancelled_orders
FROM analytics.fact_orders
GROUP BY created_at::date, currency_code
ORDER BY order_date, currency_code;
```

Trước khi đưa dashboard vào sử dụng, cần thống nhất liệu `paid_amount` có bao gồm thuế, phí giao hàng, giảm giá và hoàn tiền hay không. Định nghĩa này thuộc hợp đồng dữ liệu nghiệp vụ, không thể suy ra chỉ từ kiểu dữ liệu SQL.

## 18. Các lỗi thiết kế nên tránh

- Cho công cụ BI kết nối bằng superuser hoặc role ứng dụng có quyền ghi toàn bộ database.
- Để nhiều dashboard chạy truy vấn tổng hợp nặng trực tiếp trên primary mà không giới hạn concurrency.
- Dùng timestamp làm watermark nhưng không xử lý bản ghi đến muộn, timestamp trùng hoặc xóa dữ liệu.
- Cập nhật watermark trước khi dữ liệu đã được commit ở đích.
- Giả định CDC đảm bảo exactly-once xuyên mọi thành phần mà không có idempotency.
- Bỏ qua replication slot và để WAL tăng đến khi đầy đĩa.
- Cho rằng logical replication tự đồng bộ DDL, sequence hoặc large objects.
- Để BI tự định nghĩa chỉ số khác nhau ở từng dashboard.
- Không kiểm tra timezone và currency khi tổng hợp dữ liệu.
- Lưu password trong repository, notebook hoặc log.
- Thay đổi schema nguồn mà không thông báo cho pipeline và chủ sở hữu dashboard.
- Không có đối soát nguồn/đích hoặc quy trình replay sau sự cố.

## 19. Bài tập thực hành

### Bài 1: Tạo tài khoản BI chỉ đọc

Tạo role `bi_reader`, cấp quyền kết nối database `sales`, quyền sử dụng schema `reporting` và quyền `SELECT` trên các bảng báo cáo hiện tại. Cấu hình default privileges cho role sở hữu bảng báo cáo. Kiểm tra rằng `bi_reader` đọc được view báo cáo nhưng không thể `INSERT`, `UPDATE` hoặc `DELETE` bảng nghiệp vụ.

### Bài 2: Tạo view phục vụ dashboard

Tạo view `reporting.daily_sales` tổng hợp số đơn đã thanh toán theo ngày và mã tiền tệ. Kết nối một BI tool bằng role chỉ đọc và xây dựng biểu đồ theo thời gian. Hiển thị rõ timezone và định nghĩa doanh thu.

### Bài 3: Xây incremental load

Tạo bảng staging ở đích. Trích xuất `orders` theo `updated_at` với khoảng thời gian chồng lấn. Dùng `INSERT ... ON CONFLICT` để upsert. Chạy pipeline hai lần với cùng khoảng dữ liệu và chứng minh kết quả không bị nhân đôi.

### Bài 4: Xử lý xóa ở nguồn

Mô phỏng xóa mềm bằng `deleted_at`. Cập nhật pipeline để truyền trạng thái xóa sang đích. Sau đó mô tả cách thiết kế sẽ thay đổi nếu nguồn xóa vật lý và không có bảng nhật ký.

### Bài 5: Theo dõi logical replication

Tạo publication trên môi trường thử nghiệm, subscription ở database subscriber và đồng bộ một bảng có khóa chính. Chèn, cập nhật và xóa một số hàng; quan sát kết quả ở subscriber và các view thống kê replication. Ghi nhận hành vi khi subscriber tạm dừng.

### Bài 6: Mô phỏng CDC bị chậm

Trong môi trường thử nghiệm, dừng consumer nhưng giữ replication slot. Theo dõi `restart_lsn`, dung lượng WAL được giữ và cảnh báo. Khởi động lại consumer, xác nhận offset tiến lên và WAL được giải phóng theo khả năng của hệ thống.

### Bài 7: Kiểm tra tác động truy vấn BI

Chạy truy vấn tổng hợp đại diện với `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường dữ liệu thử nghiệm. So sánh trước và sau khi tạo index phù hợp. Đo ảnh hưởng đến một thao tác ghi đại diện để hiểu chi phí bảo trì index.

### Bài 8: Kiểm tra hợp đồng dữ liệu

Viết các truy vấn phát hiện khóa trùng, giá trị bắt buộc bị `NULL`, mã tiền tệ không hợp lệ và tổng tiền bất thường. Đưa các truy vấn vào bước kiểm tra pipeline trước khi publish dữ liệu cho BI.

## 20. Câu hỏi ôn tập

**1. Khi nào nên dùng BI truy vấn trực tiếp PostgreSQL?**

Khi số lượng truy vấn và người dùng còn kiểm soát được, độ trễ thấp quan trọng và truy vấn không gây ảnh hưởng đáng kể đến workload giao dịch. Khi tải tăng, nên xem xét read replica hoặc kho phân tích.

**2. Read replica có bảo đảm dashboard luôn thấy dữ liệu mới nhất không?**

Không. Standby có thể có replication lag. Dashboard cần chấp nhận và hiển thị độ trễ hoặc đọc từ nguồn có mức nhất quán phù hợp với yêu cầu nghiệp vụ.

**3. Vì sao phải dùng role chỉ đọc riêng cho BI?**

Để giới hạn phạm vi dữ liệu và giảm nguy cơ dashboard hoặc truy vấn ad hoc làm thay đổi dữ liệu nghiệp vụ. Role riêng cũng giúp audit và xoay vòng thông tin xác thực độc lập.

**4. Watermark theo `updated_at` có thể bỏ sót dữ liệu trong trường hợp nào?**

Khi cập nhật không đổi timestamp, bản ghi đến muộn nằm trước watermark, đồng hồ lệch, timestamp trùng ở ranh giới hoặc hàng bị xóa vật lý mà không có tombstone. Có thể giảm rủi ro bằng overlap, upsert, version và CDC.

**5. Vì sao ETL phải idempotent?**

Pipeline có thể retry sau lỗi hoặc nhận lại dữ liệu. Idempotency giúp chạy lại mà không nhân đôi, ghi đè dữ liệu mới bằng dữ liệu cũ hoặc làm sai chỉ số.

**6. Logical replication có đồng bộ DDL không?**

Không tự đồng bộ toàn bộ DDL. Cần triển khai schema ở subscriber theo quy trình riêng. Sequence state và large objects cũng cần xử lý riêng.

**7. Replication slot có thể gây đầy đĩa như thế nào?**

Slot giữ WAL mà consumer chưa xác nhận. Nếu consumer dừng hoặc lag lâu, WAL không được tái sử dụng và dung lượng `pg_wal` có thể tăng mạnh.

**8. Khi nào nên dùng materialized view?**

Khi truy vấn tổng hợp tốn kém và có thể chấp nhận dữ liệu chỉ cập nhật theo lịch. Cần lập kế hoạch refresh và thông báo thời điểm dữ liệu được làm mới.

**9. Vì sao cần chuẩn hóa timezone và currency?**

Nếu không thống nhất timezone, số liệu có thể rơi vào ngày báo cáo khác nhau. Nếu cộng các đồng tiền trực tiếp, tổng doanh thu không có ý nghĩa khi chưa quy đổi theo quy tắc tỷ giá xác định.

**10. Cần giám sát những gì ngoài trạng thái job thành công?**

Watermark, số hàng đọc/ghi, độ trễ, replication slot, WAL retention, truy vấn chậm, dung lượng, chất lượng dữ liệu và chênh lệch đối soát. Job báo thành công vẫn có thể tạo ra dữ liệu thiếu hoặc sai.

## 21. Tài liệu tham khảo PostgreSQL

- PostgreSQL Documentation — Client Authentication (`pg_hba.conf`): https://www.postgresql.org/docs/current/client-authentication.html
- PostgreSQL Documentation — Database Roles: https://www.postgresql.org/docs/current/user-manag.html
- PostgreSQL Documentation — `GRANT`: https://www.postgresql.org/docs/current/sql-grant.html
- PostgreSQL Documentation — `ALTER DEFAULT PRIVILEGES`: https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html
- PostgreSQL Documentation — `COPY`: https://www.postgresql.org/docs/current/sql-copy.html
- PostgreSQL Documentation — `CREATE PUBLICATION`: https://www.postgresql.org/docs/current/sql-createpublication.html
- PostgreSQL Documentation — `CREATE SUBSCRIPTION`: https://www.postgresql.org/docs/current/sql-createsubscription.html
- PostgreSQL Documentation — Logical Replication: https://www.postgresql.org/docs/current/logical-replication.html
- PostgreSQL Documentation — Logical Decoding: https://www.postgresql.org/docs/current/logicaldecoding.html
- PostgreSQL Documentation — Replication Progress Reporting: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — `postgres_fdw`: https://www.postgresql.org/docs/current/postgres-fdw.html
- PostgreSQL Documentation — Materialized Views: https://www.postgresql.org/docs/current/rules-materializedviews.html
- PostgreSQL Documentation — `EXPLAIN`: https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL Documentation — Row Security Policies: https://www.postgresql.org/docs/current/ddl-rowsecurity.html

Kết nối BI, ETL và hệ thống phân tích là một phần của thiết kế dữ liệu tổng thể. Chọn đúng phương thức trích xuất, tạo role tối thiểu, chuẩn hóa hợp đồng dữ liệu, xử lý incremental load/CDC có khả năng chạy lại và giám sát độ trễ sẽ giúp hệ thống phân tích đáng tin cậy mà vẫn bảo vệ PostgreSQL đang phục vụ giao dịch.
