# Làm mới dữ liệu, độ trễ và yêu cầu theo hệ quản trị

Một báo cáo SQL có thể tính tổng doanh thu trong vài mili giây dù bảng giao dịch gốc chứa hàng chục triệu bản ghi. Thay vì mỗi lần người dùng mở dashboard lại quét và tổng hợp toàn bộ giao dịch, hệ thống thường chuẩn bị sẵn kết quả trong **materialized view**, **bảng tổng hợp** hoặc **bảng trung gian** (*intermediate/staging table*).

Nhưng khi dữ liệu được lưu trước, một vấn đề mới xuất hiện: **kết quả đó mới đến thời điểm nào?** Nếu người dùng vừa tạo đơn hàng nhưng dashboard chưa hiển thị, có thể truy vấn không sai: dữ liệu nguồn đã thay đổi còn bản tổng hợp chưa được làm mới.

Bài học thuộc **Database SQL → View và bảng trung gian → Làm mới dữ liệu, độ trễ và yêu cầu theo hệ quản trị**. Nội dung giúp phân biệt view thường với kết quả được vật hóa, thiết kế chu kỳ refresh, đo độ trễ, chọn làm mới toàn phần hay tăng dần, xử lý giao dịch đồng thời, và hiểu những khác biệt giữa **PostgreSQL, Oracle, SQL Server, MySQL, SQLite** cùng một số hệ phân tích dữ liệu.

Mục tiêu không chỉ là biết viết một câu `REFRESH`. Bạn cần trả lời được **dữ liệu nào được đọc, khi nào được tính, khi nào được công bố, ai được phép làm mới, kết quả có thể trễ bao lâu và điều gì xảy ra khi refresh lỗi**.

## 1. View thường, materialized view và bảng trung gian khác nhau thế nào?

Giả sử bảng `orders` lưu từng đơn hàng, còn dashboard muốn tổng số đơn đã thanh toán và doanh thu mỗi ngày theo khu vực.

Có ít nhất ba cách:

| Cách tổ chức | Kết quả được lưu riêng? | Khi nguồn đổi | Ai chịu trách nhiệm làm mới? |
| --- | --- | --- | --- |
| **View thường** | Thông thường **không** lưu riêng kết quả truy vấn | Lần đọc sau thực hiện định nghĩa view trên dữ liệu nhìn thấy được | DBMS thực thi truy vấn khi đọc; không có lịch refresh dữ liệu riêng |
| **Materialized view** | **Có**, lưu kết quả vật hóa | Kết quả có thể **cũ** tới khi được duy trì hoặc refresh | Tùy DBMS: thủ công, lịch tự động, on commit hoặc cơ chế bảo trì khác |
| **Bảng trung gian / bảng tổng hợp** | **Có**, do ứng dụng hoặc pipeline tạo | Không tự đổi trừ khi có trigger/job/SQL cập nhật bảng này | Ứng dụng, ETL/ELT, scheduler hoặc cơ chế được thiết kế riêng |

### 1.1. View thường là định nghĩa truy vấn

Ví dụ PostgreSQL:

```sql
CREATE VIEW v_daily_sales AS
SELECT
    region,
    order_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS total_amount
FROM orders
WHERE status = 'PAID'
GROUP BY region, order_day;
```

View này cung cấp một tên đối tượng cho truy vấn. Khi `SELECT ... FROM v_daily_sales`, hệ quản trị thực hiện logic đọc các bảng nguồn theo ngữ nghĩa và snapshot của câu lệnh đang chạy. Kết quả **không có chu kỳ refresh riêng**.

Không nên diễn đạt rằng “view luôn real-time tuyệt đối”: một view có thể đọc từ **replica chậm**, bảng nguồn đã được đồng bộ trễ, hoặc transaction đang giữ snapshot cũ. Nó chỉ không tạo **một bản sao kết quả vật hóa cần refresh** theo đúng định nghĩa view thông thường.

### 1.2. Materialized view lưu lại kết quả

Ví dụ ý tưởng:

```text
orders (hàng giao dịch)
        │
        │ Tổng hợp theo region, order_day
        ▼
mv_daily_sales (kết quả đã lưu)
        │
        ▼
Dashboard đọc nhanh
```

Nếu một đơn đã thanh toán được chèn sau lần refresh cuối, materialized view có thể **chưa phản ánh đơn đó**.

### 1.3. Bảng trung gian tự quản

Một bảng như:

```sql
CREATE TABLE daily_sales_snapshot (
    region       TEXT NOT NULL,
    order_day    DATE NOT NULL,
    paid_orders  BIGINT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (region, order_day)
);
```

không tự biết phải cập nhật khi `orders` đổi. Hệ thống cần job chạy `INSERT`, `UPDATE`, `DELETE`, `MERGE` hoặc upsert để bảo trì nó.

**Từ khóa cần nhớ:** *View thường là lớp truy vấn; materialized view và bảng tổng hợp là dữ liệu đã lưu với một hợp đồng về độ mới.*

## 2. “Độ mới” và “độ trễ” không phải cùng một timestamp

Một đơn hàng có thể đi qua nhiều mốc thời gian:

```text
10:00:00  Khách đặt hàng tại ứng dụng
10:00:02  Transaction tạo đơn COMMIT ở database nguồn
10:00:07  Pipeline nhận được thay đổi nguồn
10:01:00  Job refresh bắt đầu đọc snapshot nguồn
10:01:25  Job tính toán hoàn tất
10:01:30  Bản tổng hợp mới được công bố
10:01:34  Dashboard chạy SELECT và hiển thị kết quả
```

Các mốc trên không hoán đổi được.

| Thời điểm | Ý nghĩa |
| --- | --- |
| `event_time` | Khi sự kiện nghiệp vụ xảy ra |
| `source_commit_time` | Khi thay đổi được xác nhận ở database nguồn |
| `ingested_at` | Khi pipeline nhận được sự kiện |
| `refresh_started_at` | Khi phiên làm mới bắt đầu |
| `source_cutoff` / `source_watermark` | Mốc nguồn hoặc phiên bản thay đổi **thực sự được bao phủ** |
| `published_at` | Khi bộ kết quả mới trở nên khả dụng cho reader |
| `query_time` | Khi người dùng/ứng dụng đọc kết quả |

Ví dụ trên, thời gian từ **source commit đến khi công bố** là khoảng **88 giây**; từ source commit tới lúc dashboard đọc là khoảng **92 giây**. Con số đó không bằng đơn giản thời gian chạy job refresh (30 giây).

### Độ trễ dữ liệu (*freshness lag*)

Một cách đo hữu ích là:

```text
visibility_latency(event)
  = thời điểm event được phản ánh ở kết quả đọc
    − thời điểm event commit ở nguồn
```

Đo từ **commit nguồn** phù hợp khi đánh giá lời hứa “đơn đã xác nhận sẽ xuất hiện trên dashboard trong tối đa N phút”.

Nhưng thực tế nhiều hệ thống không lưu được timestamp commit chính xác cho từng sự kiện. Có thể phải dùng **commit LSN**, sequence, offset nguồn, CDC cursor hoặc một phương án đo được định nghĩa rõ.

### Tuổi của lần refresh gần nhất không phải độ trễ chính xác

```text
now − last_successful_refresh_at
```

chỉ là thời gian từ khi có một lần refresh thành công, **không chứng minh mọi thay đổi nguồn trước thời điểm đó đã được bao phủ**.

Một job có thể chạy thành công nhưng vẫn đọc replica trễ 10 phút; hoặc job chỉ xử lý một phần partition. Ngược lại, nếu nguồn không có dữ liệu mới, dashboard có thể hoàn toàn đúng dù lần refresh gần nhất đã lâu.

Vì vậy nên theo dõi **cả nhịp làm mới và tiến độ nguồn đã xử lý**.

## 3. Độ mới của báo cáo là một yêu cầu nghiệp vụ

Hãy xác định độ trễ được chấp nhận trước khi chọn công nghệ:

| Nhu cầu | Mục tiêu độ mới minh họa | Gợi ý cách thiết kế |
| --- | --- | --- |
| Số dư để xác nhận giao dịch | Gần như ngay tại thao tác quyết định | Đọc/ghi trực tiếp nguồn có tính nhất quán phù hợp; không dựa vào snapshot trễ |
| Dashboard bán hàng vận hành | Vài phút | Refresh định kỳ hoặc pipeline tăng dần |
| Tổng hợp báo cáo ngày | Sau khi khóa sổ hoặc vài giờ | Snapshot theo kỳ, ghi rõ `as_of` |
| Dữ liệu huấn luyện mô hình | Theo phiên bản hoặc chu kỳ đã định | Snapshot có version, reproducibility |
| Danh sách sản phẩm tham khảo | Có thể chấp nhận vài phút | Cache/view vật hóa với chính sách invalidation |

Các khoảng trên **chỉ là ví dụ**, không phải mặc định bắt buộc.

Một yêu cầu nên ghi thành hợp đồng:

> “95% đơn hàng đã commit ở nguồn phải xuất hiện trong báo cáo bán hàng trong vòng 3 phút; tối đa 10 phút khi có sự cố, và dashboard phải hiển thị mốc dữ liệu đã công bố.”

Đây là ví dụ về **SLO** (*Service Level Objective*) cho độ mới. Nếu nghiệp vụ yêu cầu không bao giờ vượt 10 phút, cần thiết kế và kiểm chứng chặt hơn một chỉ tiêu p95.

## 4. Chu kỳ làm mới tạo ra độ trễ như thế nào?

Giả sử job bắt đầu mỗi **5 phút**, chạy khoảng **2 phút**, và đọc dữ liệu tại một snapshot được chốt khi job bắt đầu:

```text
00:00 Job #1 bắt đầu (snapshot t=00)
00:02 Job #1 công bố
00:05 Job #2 bắt đầu (snapshot t=05)
00:07 Job #2 công bố
00:10 Job #3 bắt đầu (snapshot t=10)
00:12 Job #3 công bố
```

Nếu một giao dịch commit **ngay sau snapshot t=00**, nó chưa được #1 lấy; #2 mới đọc thấy và công bố khoảng t=07. Độ trễ trong ví dụ xấp xỉ **7 phút**, dù cứ 5 phút có một lần chạy.

### Công thức ước lượng, không phải bảo đảm

Khi lịch bắt đầu đều đặn cách nhau `S`, thời gian từ snapshot tới công bố khoảng `R`, không có sự cố, không có trễ nguồn và không có job chồng lấn:

```text
Độ trễ xấu nhất gần đúng ≈ S + R
```

Ví dụ `S=5 phút` và `R=2 phút` → gần **7 phút**.

Thực tế cần cộng thêm yếu tố: độ trễ từ nguồn tới nơi đọc, hàng đợi scheduler, khóa/contension, retry, độ dài transaction nguồn, công bố metadata và cache bên ngoài.

Nếu job kéo dài hơn khoảng cách lịch, hai job có thể chồng lấn hoặc một job bị bỏ qua. Khi đó không thể dùng công thức đơn giản trên để tuyên bố SLA.

### Query đọc lúc job đang chạy

Ở materialized view kiểu làm mới theo đợt, dữ liệu mới thường chỉ được reader thấy **sau khi lần refresh công bố hoàn tất**. Một câu `REFRESH` đã bắt đầu không có nghĩa dashboard đang nhìn một phần dữ liệu mới.

Nhưng khả năng reader có **bị chặn** hay không và cách giữ snapshot cũ phụ thuộc DBMS/cách refresh.

---

## 5. Chuẩn bị dữ liệu thực hành PostgreSQL

Phần thực hành chính dùng PostgreSQL, nơi có `CREATE MATERIALIZED VIEW` và `REFRESH MATERIALIZED VIEW`.

**Cần dùng database/schema thử nghiệm riêng:** bảng thường và materialized view có thể được nhiều session nhìn thấy. Không chạy các câu `DROP` hoặc `UPDATE` bên dưới trên đối tượng sản xuất.

Tạo bảng nguồn:

```sql
CREATE TABLE lab_orders_318 (
    order_id    INTEGER PRIMARY KEY,
    region      TEXT NOT NULL,
    paid_at     TIMESTAMPTZ NOT NULL,
    amount      NUMERIC(12, 2) NOT NULL,
    status      TEXT NOT NULL
);

INSERT INTO lab_orders_318 (
    order_id, region, paid_at, amount, status
)
VALUES
    (1, 'North', TIMESTAMPTZ '2026-08-01 09:00:00+00', 100.00, 'PAID'),
    (2, 'North', TIMESTAMPTZ '2026-08-01 10:00:00+00',  50.00, 'PAID'),
    (3, 'North', TIMESTAMPTZ '2026-08-02 11:00:00+00',  80.00, 'PAID'),
    (4, 'South', TIMESTAMPTZ '2026-08-01 12:00:00+00',  60.00, 'PAID'),
    (5, 'South', TIMESTAMPTZ '2026-08-02 13:00:00+00',  30.00, 'DRAFT');

SELECT order_id, region, paid_at, amount, status
FROM lab_orders_318
ORDER BY order_id;
```

Bảng có năm đơn: bốn `PAID` và một `DRAFT`. Các đơn `DRAFT` chưa được tính vào doanh thu đã thanh toán.

### Vì sao phải cố định múi giờ báo cáo?

`paid_at` dùng `TIMESTAMPTZ`. Ngày nghiệp vụ có thể khác nhau theo múi giờ. Ở bài này ta chọn **ngày UTC**, không phụ thuộc setting múi giờ của connection:

```sql
(paid_at AT TIME ZONE 'UTC')::DATE
```

Trong ứng dụng thật, phải thống nhất giờ báo cáo: UTC, múi giờ cửa hàng, hay múi giờ khách hàng. Thay đổi múi giờ sau khi đã vật hóa có thể làm các hàng rơi vào ngày khác dù giá trị timestamp nguồn không đổi.

## 6. View thường trong PostgreSQL: không cần lệnh REFRESH

Tạo view:

```sql
CREATE VIEW lab_daily_sales_view_318 AS
SELECT
    region,
    (paid_at AT TIME ZONE 'UTC')::DATE AS business_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS total_amount
FROM lab_orders_318
WHERE status = 'PAID'
GROUP BY region, (paid_at AT TIME ZONE 'UTC')::DATE;
```

Đọc kết quả:

```sql
SELECT region, business_day, paid_orders, total_amount
FROM lab_daily_sales_view_318
ORDER BY region, business_day;
```

Ban đầu:

| region | business_day | paid_orders | total_amount |
| --- | --- | ---: | ---: |
| North | 2026-08-01 | 2 | 150.00 |
| North | 2026-08-02 | 1 | 80.00 |
| South | 2026-08-01 | 1 | 60.00 |

`DRAFT` không được tính.

### Từ bảng gốc tới view

Khi một transaction khác commit một đơn `PAID` mới, lần truy vấn tiếp theo vào view thường được thực hiện trên dữ liệu nguồn mà transaction đọc được ở snapshot tương ứng. Không cần chạy `REFRESH VIEW`; PostgreSQL không có lệnh như vậy cho view thường.

Điều này không hứa hẹn truy vấn nhanh: nếu tổng hợp cần quét lượng dữ liệu lớn, mỗi lần sử dụng view có thể tiêu tốn CPU, I/O và công việc nhóm.

## 7. PostgreSQL materialized view: lưu kết quả tại thời điểm tạo hoặc refresh

Tạo materialized view với định nghĩa tổng hợp tương tự:

```sql
CREATE MATERIALIZED VIEW lab_daily_sales_mv_318 AS
SELECT
    region,
    (paid_at AT TIME ZONE 'UTC')::DATE AS business_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS total_amount
FROM lab_orders_318
WHERE status = 'PAID'
GROUP BY region, (paid_at AT TIME ZONE 'UTC')::DATE
WITH DATA;
```

`WITH DATA` yêu cầu PostgreSQL chạy truy vấn lúc tạo để điền dữ liệu ban đầu vào materialized view.

```sql
SELECT region, business_day, paid_orders, total_amount
FROM lab_daily_sales_mv_318
ORDER BY region, business_day;
```

Ở thời điểm khởi tạo, kết quả trùng view thường.

### Bản chất của materialized view PostgreSQL

- Định nghĩa dựa vào truy vấn nguồn.
- Lưu **các hàng kết quả** như một quan hệ vật hóa.
- Có thể có index trên kết quả vật hóa.
- **Không tự cập nhật** chỉ vì bảng `lab_orders_318` thay đổi.
- Muốn cập nhật kết quả, cần chạy `REFRESH MATERIALIZED VIEW` (hoặc cơ chế orchestration được thiết kế riêng).

**Không có nghĩa materialized view luôn nhanh hơn trong mọi thao tác.** Reader có thể nhanh, nhưng việc refresh tốn tài nguyên, duy trì index và chiếm dung lượng; tổng chi phí cần được đo.

## 8. Quan sát sự khác nhau khi nguồn đổi

Bây giờ thêm một đơn North đã thanh toán. Đây là thao tác thật trên **bảng thực hành**; không dùng trên dữ liệu khác.

```sql
INSERT INTO lab_orders_318 (
    order_id, region, paid_at, amount, status
)
VALUES (
    6, 'North', TIMESTAMPTZ '2026-08-01 14:00:00+00',
    25.00, 'PAID'
);
```

So sánh:

```sql
SELECT 'ordinary_view' AS source_type,
       region, business_day, paid_orders, total_amount
FROM lab_daily_sales_view_318
WHERE region = 'North'
  AND business_day = DATE '2026-08-01'

UNION ALL

SELECT 'materialized_view' AS source_type,
       region, business_day, paid_orders, total_amount
FROM lab_daily_sales_mv_318
WHERE region = 'North'
  AND business_day = DATE '2026-08-01'
ORDER BY source_type;
```

Dự kiến:

| source_type | region | business_day | paid_orders | total_amount |
| --- | --- | --- | ---: | ---: |
| materialized_view | North | 2026-08-01 | 2 | 150.00 |
| ordinary_view | North | 2026-08-01 | 3 | 175.00 |

Cả hai đối tượng đều dùng **cùng công thức tổng hợp**. Khác biệt xuất phát từ **thời điểm dữ liệu được tính và lưu**.

### Làm mới materialized view

```sql
REFRESH MATERIALIZED VIEW lab_daily_sales_mv_318;
```

Sau khi refresh thành công, đọc lại:

```sql
SELECT region, business_day, paid_orders, total_amount
FROM lab_daily_sales_mv_318
WHERE region = 'North'
  AND business_day = DATE '2026-08-01';
```

Kết quả thành **3 đơn / 175.00**.

### Refresh không phải chỉ chèn thêm đơn mới

Nếu bảng nguồn có:

- `INSERT` đơn mới,
- `UPDATE` chuyển `DRAFT` thành `PAID`,
- `UPDATE` sửa số tiền,
- `DELETE` một đơn đã thanh toán,

thì lần refresh đầy đủ sẽ **tính lại kết quả theo trạng thái nguồn được đọc**, không chỉ thêm số tiền giao dịch mới.

Điều đó giúp tránh nhiều lỗi của một pipeline tăng dần tự viết, nhưng đổi lại có thể cần đọc và tổng hợp toàn bộ dữ liệu nguồn.

## 9. PostgreSQL REFRESH và khả năng truy cập đồng thời

PostgreSQL có hai cách gọi đáng chú ý:

```sql
REFRESH MATERIALIZED VIEW lab_daily_sales_mv_318;
```

và:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY lab_daily_sales_mv_318;
```

### 9.1. REFRESH thông thường

Trong quá trình refresh không dùng `CONCURRENTLY`, PostgreSQL dùng cơ chế khóa trên materialized view khiến các truy vấn đọc trực tiếp materialized view có thể **phải chờ** cho đến khi refresh hoàn tất.

Ưu điểm thường là đường thực thi làm mới đơn giản hơn; nhược điểm là thời gian chặn reader có thể không phù hợp với dashboard cần luôn sẵn sàng.

### 9.2. REFRESH CONCURRENTLY

`CONCURRENTLY` được thiết kế để cho phép nhiều `SELECT` vẫn truy cập materialized view trong lúc refresh đang diễn ra, bằng cách duy trì tính nhất quán và công bố kết quả sau quá trình làm mới.

Nhưng nó có các điều kiện bắt buộc. Không phải chỉ thêm một từ khóa là câu lệnh sẽ chạy.

### 9.3. Tạo UNIQUE index đáp ứng yêu cầu

Materialized view thực hành có **mỗi cặp `(region,business_day)` tối đa một hàng** do `GROUP BY`. Hãy tạo một index duy nhất trên hai cột kết quả:

```sql
CREATE UNIQUE INDEX lab_daily_sales_mv_318_uq
ON lab_daily_sales_mv_318 (region, business_day);
```

Sau đó:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY lab_daily_sales_mv_318;
```

Với PostgreSQL, `CONCURRENTLY` cần ít nhất **một UNIQUE index sử dụng tên cột thông thường**, bao phủ **tất cả các hàng**, **không** phải index biểu thức và **không** phải partial index có `WHERE`.

Ví dụ index **không đủ** điều kiện để dựa vào khi làm mới đồng thời:

```sql
-- Partial unique index: không bao phủ tất cả các hàng
-- CREATE UNIQUE INDEX ... ON mv(region, business_day)
-- WHERE region = 'North';

-- Expression unique index: không phải chỉ gồm cột đơn giản
-- CREATE UNIQUE INDEX ... ON mv(lower(region), business_day);
```

Một primary key trên bảng nguồn **không thay thế** UNIQUE index cần có trên **materialized view**.

### 9.4. Tại sao CONCURRENTLY không đồng nghĩa tăng dần?

Trong PostgreSQL core, `REFRESH MATERIALIZED VIEW CONCURRENTLY` vẫn phải tính lại truy vấn định nghĩa và xác định thay đổi cần công bố. Nó **không phải** cơ chế chỉ xử lý các giao dịch mới từ lần refresh trước theo một watermark nghiệp vụ.

Một refresh đồng thời có thể tốn tài nguyên hơn refresh thông thường ở một số tình huống. Hãy đo thời gian và tài nguyên thay vì mặc định `CONCURRENTLY` luôn nhanh hơn.

## 10. PostgreSQL WITH NO DATA và lần khởi tạo đầu tiên

Có thể tạo materialized view chưa điền dữ liệu:

```sql
-- Ví dụ cấu trúc; không tạo lại cùng tên khi đối tượng đã tồn tại.
CREATE MATERIALIZED VIEW some_unpopulated_mv AS
SELECT ...
WITH NO DATA;
```

Khi dùng `WITH NO DATA`:

- Materialized view được tạo nhưng **chưa ở trạng thái có thể truy vấn dữ liệu như một bản đã được nạp**.
- Cần lần đầu chạy `REFRESH MATERIALIZED VIEW ... WITH DATA` để điền dữ liệu.
- Không thể dùng `REFRESH MATERIALIZED VIEW CONCURRENTLY` khi materialized view **chưa được populate**.

Ví dụ trong schema lab riêng, nếu thật sự cần thực hành đối tượng thứ hai:

```sql
CREATE MATERIALIZED VIEW lab_empty_mv_318 AS
SELECT
    region,
    COUNT(*) AS order_count
FROM lab_orders_318
GROUP BY region
WITH NO DATA;

REFRESH MATERIALIZED VIEW lab_empty_mv_318 WITH DATA;

SELECT region, order_count
FROM lab_empty_mv_318
ORDER BY region;
```

Việc tạo view chưa có dữ liệu hữu ích khi muốn chuẩn bị schema hoặc trì hoãn lần chạy truy vấn nguồn tốn kém. Nhưng không được coi đối tượng chưa populate là một bảng rỗng hợp lệ cho dashboard.

### Không làm mới đồng thời nhiều lần trên cùng một materialized view

PostgreSQL chỉ cho phép **một refresh tại một thời điểm đối với cùng một materialized view**. Nếu scheduler phát động job mới khi job cũ còn chạy, có thể xảy ra chờ khóa hoặc tích tụ công việc.

Nên thiết kế **single-flight**: một job đang làm mới thì job cùng mục tiêu không mở thêm lượt không cần thiết; đồng thời giám sát các job chờ hoặc chạy quá lâu.

---

## 11. Xóa/sửa dữ liệu nguồn và kiểm tra refresh đầy đủ

Giả sử đơn `order_id=5` của South từ `DRAFT` chuyển sang `PAID`:

```sql
UPDATE lab_orders_318
SET status = 'PAID'
WHERE order_id = 5;
```

Bảng nguồn giờ có thêm một đơn `PAID` cho `South / 2026-08-02`, với tổng 30.

Trước refresh, materialized view có thể **chưa có hàng South–2026-08-02**. Sau:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY lab_daily_sales_mv_318;
```

truy vấn:

```sql
SELECT region, business_day, paid_orders, total_amount
FROM lab_daily_sales_mv_318
WHERE region = 'South'
ORDER BY business_day;
```

sẽ bao gồm `2026-08-02 / 1 đơn / 30`.

Tiếp theo, nếu xóa một đơn `PAID` khỏi nguồn:

```sql
DELETE FROM lab_orders_318
WHERE order_id = 4;
```

và refresh đầy đủ, nhóm `South / 2026-08-01` có thể **biến mất** vì không còn đơn PAID cho nhóm đó.

Đây là một điểm quan trọng: refresh đầy đủ không chỉ thêm/sửa hàng tổng hợp, mà còn phải **loại những hàng kết quả đã không còn đúng**.

Bảng tổng hợp tự quản cần thực hiện chính sách xóa tương ứng. Nếu chỉ upsert nhóm có trong batch mới và không xóa nhóm đã hết dữ liệu, báo cáo có thể giữ “hàng ma” từ quá khứ.

## 12. Full refresh và incremental refresh

Có hai họ chiến lược chính.

### Làm mới toàn phần (*full refresh*)

Ý tưởng:

```text
Đọc trạng thái nguồn hiện tại
     ↓
Chạy lại toàn bộ truy vấn tổng hợp
     ↓
Thay/công bố bản kết quả mới
```

Ưu điểm:

- Dễ hiểu và đối chiếu với bảng nguồn.
- Bao phủ cả INSERT, UPDATE, DELETE nếu truy vấn nguồn trả đúng trạng thái.
- Không phụ thuộc quá nhiều vào logic bù trừ thay đổi.
- Phù hợp với nguồn vừa/nhỏ, lịch refresh không quá thường xuyên.

Nhược điểm:

- Có thể tốn CPU/I/O trên toàn bộ dữ liệu.
- Thời gian chạy có thể tăng theo kích thước nguồn.
- Có thể gây tranh chấp tài nguyên hoặc chặn reader tùy DBMS.
- Nếu job quá lâu, kết quả có thể mới vừa công bố nhưng đã bỏ lỡ các commit sau snapshot lúc job bắt đầu.

### Làm mới tăng dần (*incremental refresh*)

Ý tưởng:

```text
Nguồn từ checkpoint trước đến checkpoint mới
                 ↓
          Chọn các thay đổi
                 ↓
         Tính tác động delta
                 ↓
        Cập nhật các nhóm bị ảnh hưởng
                 ↓
      Lưu checkpoint cùng kết quả
```

Ưu điểm:

- Không phải quét toàn bộ lịch sử mỗi lần nếu nguồn có thay đổi nhỏ.
- Có thể đạt độ trễ thấp hơn và giảm chi phí tính lại.
- Hữu ích cho bảng lớn hoặc luồng sự kiện liên tục.

Nhược điểm:

- Khó xử lý UPDATE, DELETE, dữ liệu đến muộn, đảo thứ tự và thay đổi lại quá khứ.
- Cần watermark/checkpoint đáng tin cậy.
- Phải tránh áp dụng cùng một sự kiện nhiều lần hoặc bỏ sót sự kiện.
- Cần đối chiếu và khả năng **rebuild toàn phần** khi phát hiện lệch.

**Làm mới tăng dần không phải bản tối ưu cơ học của mọi truy vấn.** Một số phép tổng hợp như `MIN`, `MAX`, `COUNT(DISTINCT)` hoặc logic JOIN phức tạp khó cập nhật đúng chỉ bằng một delta đơn giản khi có xóa/sửa.

---

## 13. Bảng trung gian cập nhật toàn phần bằng transaction

Nếu DBMS không có materialized view gốc hoặc ứng dụng cần kiểm soát quy trình công bố, có thể lưu kết quả ở bảng thường.

Tạo bảng riêng trong PostgreSQL lab:

```sql
CREATE TABLE lab_daily_sales_table_318 (
    region       TEXT NOT NULL,
    business_day DATE NOT NULL,
    paid_orders  BIGINT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (region, business_day)
);
```

Một cách làm mới đơn giản:

```sql
BEGIN;

DELETE FROM lab_daily_sales_table_318;

INSERT INTO lab_daily_sales_table_318 (
    region, business_day, paid_orders, total_amount
)
SELECT
    region,
    (paid_at AT TIME ZONE 'UTC')::DATE,
    COUNT(*),
    SUM(amount)
FROM lab_orders_318
WHERE status = 'PAID'
GROUP BY region, (paid_at AT TIME ZONE 'UTC')::DATE;

COMMIT;
```

Với PostgreSQL MVCC, các thay đổi do transaction trên chưa commit không được reader `READ COMMITTED` khác nhìn thấy như một kết quả đã công bố một phần. Một truy vấn reader với snapshot phù hợp thấy trạng thái đã commit trước hoặc sau giao dịch, không phải trạng thái trung gian `DELETE` hết rồi mới `INSERT` một phần.

### Giới hạn của cách DELETE + INSERT

- Xóa/chèn toàn bộ bảng có chi phí ghi và tạo nhiều phiên bản hàng.
- Có thể gây bloat và tạo công việc cho `VACUUM`.
- Cần khóa và theo dõi tranh chấp với những job đọc/ghi khác.
- Không phải chiến lược tốt nhất cho bảng rất lớn hoặc tần suất cao.
- Một số DBMS có khác biệt về transactional DDL, `TRUNCATE` và cơ chế reader.

**Đặc biệt trong PostgreSQL, `TRUNCATE` không MVCC-safe theo cách tương đương `DELETE` trong một số tình huống snapshot cũ.** Không nên tự đổi `DELETE` thành `TRUNCATE` rồi mặc định mọi reader snapshot vẫn thấy bản trước nguyên vẹn. Việc chọn cách làm mới phải xét cơ chế transaction/locking của DBMS.

### Vì sao phải giữ DELETE và INSERT trong cùng transaction?

Nếu job chạy:

```sql
DELETE FROM lab_daily_sales_table_318;
COMMIT;

-- Mất kết nối hoặc lỗi xảy ra ở đây.

INSERT INTO lab_daily_sales_table_318 ...
COMMIT;
```

thì reader có thể thấy **bảng trống đã commit** trong khoảng giữa hoặc sau khi job lỗi. Đó là lỗi công bố bản kết quả chưa hoàn chỉnh, không chỉ là “dữ liệu hơi trễ”.

---

## 14. Công bố bằng phiên bản snapshot: tránh làm hỏng bản đang phục vụ

Một chiến lược an toàn cho bảng trung gian là **ghi bản mới với một snapshot ID khác**, xác nhận bản mới đầy đủ, rồi đổi một con trỏ “bản đang hoạt động” trong transaction.

Mô hình:

```text
report_rows
  snapshot_id=41  ← bản cũ, còn reader sử dụng
  snapshot_id=42  ← bản mới đang được tính, chưa công bố

report_active
  report_name='daily_sales', active_snapshot_id=41

Sau kiểm tra và COMMIT:
  report_active.active_snapshot_id=42
```

### Schema minh họa PostgreSQL

```sql
CREATE TABLE lab_report_rows_318 (
    snapshot_id  BIGINT NOT NULL,
    region       TEXT NOT NULL,
    business_day DATE NOT NULL,
    paid_orders  BIGINT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (snapshot_id, region, business_day)
);

CREATE TABLE lab_report_active_318 (
    report_name        TEXT PRIMARY KEY,
    active_snapshot_id BIGINT NOT NULL,
    published_at       TIMESTAMPTZ NOT NULL
);
```

Giả sử đang có snapshot 41 và cần tạo snapshot 42:

```sql
-- Trong database lab, snapshot_id phải được cấp không trùng
-- và một job chịu trách nhiệm công bố.
INSERT INTO lab_report_rows_318 (
    snapshot_id, region, business_day, paid_orders, total_amount
)
SELECT
    42,
    region,
    (paid_at AT TIME ZONE 'UTC')::DATE,
    COUNT(*),
    SUM(amount)
FROM lab_orders_318
WHERE status = 'PAID'
GROUP BY region, (paid_at AT TIME ZONE 'UTC')::DATE;
```

Khi snapshot 42 đã đầy đủ và được phép công bố, cập nhật con trỏ trong một transaction:

```sql
BEGIN;

INSERT INTO lab_report_active_318 (
    report_name, active_snapshot_id, published_at
)
VALUES ('daily_sales', 42, CURRENT_TIMESTAMP)
ON CONFLICT (report_name) DO UPDATE
SET active_snapshot_id = EXCLUDED.active_snapshot_id,
    published_at = EXCLUDED.published_at;

COMMIT;
```

Đọc bản đang hoạt động:

```sql
SELECT
    r.region, r.business_day, r.paid_orders, r.total_amount,
    a.active_snapshot_id, a.published_at
FROM lab_report_active_318 AS a
JOIN lab_report_rows_318 AS r
  ON r.snapshot_id = a.active_snapshot_id
WHERE a.report_name = 'daily_sales'
ORDER BY r.region, r.business_day;
```

Ưu điểm: công bố bản mới chủ yếu là **đổi một con trỏ**, không phải xóa bản đang phục vụ.

### Những điều vẫn phải thiết kế

- Cấp snapshot ID không trùng, có owner/job lock và thứ tự công bố rõ.
- Không chuyển con trỏ tới snapshot **chưa đầy đủ**.
- Job cũ kết thúc muộn không được ghi đè con trỏ của job mới hơn.
- Cleanup snapshot cũ phải tính đến reader còn đang dùng bản cũ và retention.
- Metadata như `source_watermark` nên đi cùng snapshot để biết nội dung đã bao phủ tới đâu.
- Một transaction đọc nhiều statement có thể thấy con trỏ đổi theo isolation; nếu muốn toàn báo cáo dùng một version, đọc và **giữ snapshot ID cố định** cho phiên báo cáo.

Đừng coi `UPDATE active_snapshot_id = 42` là đủ cho mọi hệ nếu chưa có quy tắc cấp phiên bản và ngăn publish ngược.

---

## 15. Làm mới tăng dần bằng các sự kiện có delta

Một bài toán tăng dần đơn giản là **luồng cộng dồn bất biến**. Mỗi sự kiện mới có giá trị tăng thêm vào một nhóm.

Ví dụ nguồn sự kiện:

```text
event_id | region | day        | amount_delta
---------+--------+------------+-------------
1        | North  | 2026-08-01 | 100
2        | North  | 2026-08-01 |  50
3        | South  | 2026-08-01 |  60
4        | North  | 2026-08-02 |  80
```

Bảng tổng hợp chỉ cần cộng những delta **chưa xử lý**:

```sql
-- PostgreSQL: mẫu upsert delta; batch phải gồm các sự kiện
-- chưa từng áp dụng, được gom về tối đa một hàng mỗi group key.
INSERT INTO daily_totals (region, business_day, total_amount)
SELECT
    region,
    event_day,
    SUM(amount_delta)
FROM new_events
GROUP BY region, event_day
ON CONFLICT (region, business_day) DO UPDATE
SET total_amount =
    daily_totals.total_amount + EXCLUDED.total_amount;
```

Đây là **mẫu minh họa**; `daily_totals` và `new_events` là tên đối tượng giả định của một pipeline tăng dần, không phải bảng được tạo trong lab ở mục 5.

### Tại sao dễ tính sai khi retry?

Nếu batch gồm delta +100 được áp dụng **hai lần**, tổng sẽ tăng +200. `ON CONFLICT DO UPDATE` giải quyết trùng **khóa tổng hợp**, không giải quyết trùng **danh tính sự kiện**.

Muốn an toàn hơn, cần xác định những sự kiện đã xử lý, ghi dấu `event_id` hoặc checkpoint và cập nhật tổng trong **cùng transaction** theo cơ chế thích hợp.

### Tại sao GROUP BY trước ON CONFLICT?

Nếu một lệnh `INSERT ... ON CONFLICT DO UPDATE` của PostgreSQL chứa **nhiều hàng nguồn cùng khóa `(region,business_day)`**, nó có thể không thể tác động một hàng đích nhiều lần trong cùng statement và báo lỗi cardinality. Tổng hợp nguồn theo khóa đích trước là một cách tạo **một delta trên mỗi nhóm**.

### Dùng sự kiện delta khác với bảng trạng thái đơn hàng

Bảng `lab_orders_318` lưu trạng thái **hiện tại** của đơn. Nếu đơn `DRAFT` thành `PAID`, hoặc đơn đã thanh toán bị hủy, phải tính delta tương ứng của **trạng thái cũ và mới**. Chỉ chọn “đơn có thời gian cập nhật mới” rồi `SUM(amount)` có thể cộng lại doanh thu đã tính từ trước.

**Định nghĩa đúng sự kiện delta** thường khó hơn câu `UPSERT`.

---

## 16. Watermark và checkpoint: làm sao biết đã xử lý tới đâu?

Một pipeline tăng dần cần lưu mốc nguồn đã xử lý:

```text
last_processed_event_id = 5000
new events = 5001..5050
sau xử lý thành công:
last_processed_event_id = 5050
```

Nếu checkpoint tăng lên 5050 **trước khi** ghi các tổng hợp tương ứng, rồi tiến trình lỗi, lần chạy sau sẽ bỏ qua một phần dữ liệu: **mất thay đổi**.

Nếu đã ghi tổng hợp nhưng checkpoint chưa tăng, rồi job retry, các delta có thể được áp dụng **lần nữa**: **đếm trùng**.

### Ghi tổng hợp và checkpoint trong một transaction

Mẫu nguyên tắc:

```sql
BEGIN;

-- 1. Khóa hoặc xác định độc quyền phần việc của pipeline.
-- 2. Chọn một tập sự kiện xác định.
-- 3. Áp dụng delta vào bảng tổng hợp.
-- 4. Ghi checkpoint cùng với sự kiện vừa xử lý.

COMMIT;
```

Khi mọi thay đổi nằm trong cùng database/transaction, chúng có thể cùng commit hoặc cùng rollback.

Nhưng một hệ thống dùng **message broker + database + external API** cần chiến lược phù hợp hơn; transaction của database không tự bao trùm broker hoặc lời gọi HTTP. Có thể sử dụng **inbox/outbox**, CDC offset và xử lý idempotent.

### Bẫy ID tăng không đồng nghĩa thứ tự COMMIT

Giả sử transaction A lấy `event_id=5001` nhưng **chưa commit**. Transaction B lấy `event_id=5002` và commit trước. Job nhìn thấy 5002 rồi lưu watermark 5002. Sau đó A mới commit 5001; lần sau truy vấn `event_id > 5002` sẽ **bỏ sót 5001**.

Do đó không được mặc định rằng `BIGSERIAL`, `AUTO_INCREMENT` hay timestamp tạo bản ghi tạo ra thứ tự **commit** đầy đủ khi có transaction đồng thời.

Nếu checkpoint dựa trên sequence, cần có điều kiện đảm bảo sự kiện được công bố theo thứ tự thích hợp, hoặc dùng cơ chế CDC/commit log mang thứ tự xác nhận, hoặc thiết kế chống bỏ sót khác.

---

## 17. Late-arriving data: dữ liệu đến muộn và sửa quá khứ

Một cửa hàng gửi đơn hàng ngày 01-08, nhưng kết nối bị gián đoạn và hệ thống nhận được vào ngày 03-08. Nếu job chỉ refresh “ngày hôm nay”, đơn này sẽ **không bao giờ xuất hiện** ở tổng ngày 01-08.

Cần phân biệt:

- **Event time:** thời điểm nghiệp vụ trên đơn.
- **Ingestion time:** thời điểm pipeline nhận đơn.
- **Update/commit time:** thời điểm dữ liệu được sửa/commit trong nguồn.

### Cửa sổ nhìn lại (*lookback window*)

Một cách xử lý thực tế là mỗi lần job tính lại **N ngày gần nhất**, thay vì chỉ hôm nay:

```sql
-- PostgreSQL: ví dụ lọc kỳ được tính lại, không phải
-- câu lệnh refresh materialized view toàn phần có WHERE.
SELECT
    region,
    (paid_at AT TIME ZONE 'UTC')::DATE AS business_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS total_amount
FROM lab_orders_318
WHERE status = 'PAID'
  AND paid_at >= TIMESTAMPTZ '2026-07-26 00:00:00+00'
  AND paid_at <  TIMESTAMPTZ '2026-08-03 00:00:00+00'
GROUP BY region, (paid_at AT TIME ZONE 'UTC')::DATE;
```

Một pipeline bảng trung gian có thể **thay thế kết quả cho các ngày trong lookback** bằng dữ liệu nguồn hiện tại.

### Lookback không phải lời giải đầy đủ

Nếu một đơn bị sửa sau **30 ngày**, lookback 7 ngày vẫn bỏ sót. Cần biết hợp đồng nguồn:

- Đơn có thể bị hoàn tiền hoặc hủy sau bao lâu?
- Có cơ chế phát hiện thay đổi quá khứ không?
- Có nên dùng CDC để nhận cả old/new values?
- Có quy trình rebuild định kỳ để đối chiếu?
- Khi điều chỉnh kỳ đã khóa sổ, báo cáo có được phép hồi tố không?

Độ dài lookback phải dựa trên **phân bố dữ liệu đến muộn và quy tắc nghiệp vụ**, không chọn ngẫu nhiên.

---

## 18. UPDATE và DELETE gây khó cho incremental refresh

Hãy xét một đơn đã `PAID` với số tiền 100, đã cộng vào tổng tháng.

### UPDATE số tiền 100 → 130

Nếu job thấy hàng đã sửa và cộng thêm **130**, tổng tăng sai. Cần bù **+30** (new − old), hoặc tính lại nhóm thời gian bị ảnh hưởng.

### Hủy đơn PAID → CANCELLED

Nếu nghiệp vụ loại đơn bị hủy khỏi doanh thu, tổng phải **trừ 100**, không phải bỏ qua thay đổi vì trạng thái hiện tại không còn `PAID`.

### Đổi ngày hoặc khu vực

Nếu đơn chuyển từ `North/01-08` sang `South/02-08`, cần:

- Trừ đóng góp khỏi nhóm cũ.
- Cộng vào nhóm mới.

Chỉ cập nhật nhóm mới mà không sửa nhóm cũ sẽ để lại doanh thu ma.

### DELETE

Nếu bản ghi bị xóa hẳn, một bộ đọc chỉ quét các hàng **đang tồn tại** không còn thấy dấu vết của hàng đã mất. Cần **CDC delete event, tombstone**, bảng log thay đổi hoặc recompute phạm vi liên quan.

### Một bảng so sánh

| Thay đổi nguồn | Full refresh | Incremental refresh |
| --- | --- | --- |
| INSERT một đơn PAID mới | Tính lại, bao gồm đơn mới | Cộng đóng góp mới |
| UPDATE tiền 100 → 130 | Tính lại thành tiền mới | Bù +30 hoặc recompute nhóm |
| PAID → CANCELLED | Tính lại, loại đơn | Trừ đóng góp cũ |
| Đổi ngày hoặc khu vực | Tính lại cả các nhóm đúng | Sửa nhóm cũ và nhóm mới |
| DELETE đơn | Kết quả không còn đơn | Phải biết trước có hàng bị xóa |
| Thay đổi công thức tính tổng | Tính lại theo truy vấn mới | Có thể phải rebuild toàn bộ lịch sử |

Vì vậy, nếu **dữ liệu có thể sửa/xóa tùy ý**, incremental refresh cần thiết kế phức tạp hơn nhiều so với “lấy các hàng có `created_at` mới hơn lần trước”.

## 19. Chỉ dùng MAX(updated_at) có đủ không?

Một pipeline có thể thử:

```sql
SELECT *
FROM source_table
WHERE updated_at > :last_watermark
ORDER BY updated_at;
```

Mẫu trên có những rủi ro:

1. **Trùng timestamp:** hai hàng có cùng `updated_at`, checkpoint ở timestamp đó có thể khiến một hàng xử lý muộn bị bỏ qua.
2. **Đồng hồ lệch:** timestamp ứng dụng không nhất thiết theo thứ tự commit.
3. **DELETE:** hàng đã xóa không còn để truy vấn.
4. **Không cập nhật timestamp:** một số đường ghi có thể sửa dữ liệu nhưng quên đổi `updated_at`.
5. **Transaction commit muộn:** một hàng có timestamp thấp có thể chỉ trở nên visible sau khi checkpoint đã đi qua mốc đó.
6. **Đổi giá trị khóa nhóm:** cần biết nhóm trước và sau.

### Composite cursor có thể giúp nhưng không giải quyết mọi concurrency

Dùng cặp `(updated_at, id)` với thứ tự toàn phần giảm rủi ro bỏ sót do cùng timestamp:

```sql
WHERE (updated_at, id) > (:last_updated_at, :last_id)
ORDER BY updated_at, id
```

Tuy nhiên, nếu một giao dịch có timestamp cũ **commit muộn**, composite cursor theo timestamp vẫn có thể bỏ sót nó. Cần thêm bảo đảm về thứ tự xuất bản hoặc một cơ chế CDC đáng tin cậy.

### Khuyến nghị thực tế

- Dùng **commit log/CDC offset** nếu bài toán yêu cầu bao phủ mọi thay đổi theo commit.
- Nếu phải quét timestamp, dùng overlap/lookback, upsert theo định danh và có đối chiếu; thừa nhận giới hạn rõ.
- Lưu checkpoint chỉ sau khi kết quả tương ứng đã được công bố an toàn.
- Có thể chạy **full reconciliation** định kỳ để phát hiện drift.
- Theo dõi tuổi sự kiện chưa xử lý lâu nhất thay vì chỉ `MAX(updated_at)` đã xử lý.

---

## 20. Làm mới thất bại: giữ bản cũ hay công bố bản lỗi?

Giả sử dashboard đọc materialized view cho 1.000 khu vực; job refresh chạy được 700 khu vực rồi lỗi.

Hai cách công bố có rủi ro rất khác nhau:

### Công bố từng phần ngoài transaction

```text
Xóa dữ liệu cũ
  → ghi 700 khu vực
  → lỗi
  → dashboard thấy thiếu 300 khu vực
```

Đây là lỗi **tính toàn vẹn của bản tổng hợp**. Không chỉ là dữ liệu chậm.

### Công bố nguyên tử sau khi bản mới hoàn tất

```text
Giữ bản đang phục vụ
  → xây bản mới riêng
  → kiểm tra điều kiện tối thiểu
  → công bố trong transaction
  → nếu lỗi, giữ bản trước và báo stale
```

Cách thứ hai thường phù hợp cho báo cáo: **bản cũ nhưng hoàn chỉnh** tốt hơn **bản mới nhưng thiếu ngẫu nhiên**, miễn dashboard hiển thị rõ mốc dữ liệu và có cảnh báo.

### Không được coi lần refresh lỗi là thành công

Metadata nên lưu được:

- `last_successful_refresh_at`.
- `last_attempt_at`.
- `last_error` / mã lỗi.
- `source_watermark` đã công bố.
- `refresh_duration`.
- Phiên bản câu SQL/schema đã được dùng.
- `row_count` hoặc tổng checksum đối chiếu nếu cần.

Nếu job lỗi, **đừng cập nhật watermark công bố** và đừng hiển thị timestamp “làm mới gần đây” như thể bản dữ liệu đã thành công.

---

## 21. Giám sát độ mới: kiểm tra nhiều lớp

Một dashboard vận hành nên theo dõi ít nhất bốn nhóm tín hiệu:

| Nhóm | Ví dụ chỉ số | Mục đích |
| --- | --- | --- |
| **Scheduler/job** | Thời gian từ lần refresh thành công, thời lượng chạy, số lỗi liên tiếp | Job có chạy đều không? |
| **Nguồn → pipeline** | CDC lag, backlog, offset nguồn mới nhất so với offset đã xử lý | Có thay đổi nào đang chờ không? |
| **Pipeline → bản công bố** | Source watermark của snapshot, `published_at`, snapshot version | Bản đang phục vụ bao phủ tới đâu? |
| **Chất lượng dữ liệu** | Số hàng, doanh thu theo ngày, số key trùng, đối chiếu với nguồn | Dù refresh thành công, kết quả có đúng không? |

### Trường hợp báo động khác nhau

**Trường hợp A:** refresh chạy đúng lịch nhưng source watermark đứng yên dù nguồn có đơn mới → nghi pipeline bỏ sót, nguồn replica trễ hoặc cursor sai.

**Trường hợp B:** watermark tiến nhưng công bố bản mới thất bại → không được đánh dấu dữ liệu đã hiển thị mới.

**Trường hợp C:** bản công bố mới và job thành công nhưng số lượng đối chiếu giảm bất thường → nghi logic tổng hợp, JOIN nhân bản, thay đổi schema, hoặc xóa nguồn ngoài dự kiến.

**Trường hợp D:** không có đơn mới hai ngày, refresh đã lâu → dữ liệu có thể vẫn đúng; cần kiểm tra **hoạt động nguồn** trước khi diễn giải chỉ số “tuổi refresh” thành độ trễ.

### Ví dụ metadata bảng job

```sql
-- PostgreSQL: cấu trúc tham khảo cho bảng theo dõi,
-- không tự động được REFRESH MATERIALIZED VIEW điền thông tin.
CREATE TABLE lab_refresh_runs_318 (
    run_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name    TEXT NOT NULL,
    started_at       TIMESTAMPTZ NOT NULL,
    finished_at      TIMESTAMPTZ,
    published_at     TIMESTAMPTZ,
    source_watermark TEXT,
    status           TEXT NOT NULL,
    error_message    TEXT
);
```

Job ứng dụng phải chủ động ghi start/success/failure và metadata đúng sự thật. Không tự cập nhật `published_at` nếu refresh thất bại.

---

## 22. Scheduling: cơ sở dữ liệu không nhất thiết tự lên lịch refresh

Một materialized view có câu `REFRESH` không có nghĩa DBMS tự chạy nó mỗi 5 phút.

### PostgreSQL

PostgreSQL core có lệnh `REFRESH MATERIALIZED VIEW`, nhưng không có tùy chọn chuẩn kiểu:

```sql
-- Không phải cú pháp PostgreSQL core:
-- CREATE MATERIALIZED VIEW ... REFRESH EVERY 5 MINUTES;
```

Lịch refresh thường được giao cho:

- Scheduler bên ngoài (cron, Airflow, Dagster, orchestration service).
- PostgreSQL extension dành cho lập lịch như `pg_cron` nếu môi trường hỗ trợ.
- Một service/job của ứng dụng.

Scheduler cần xác định **tần suất**, **tránh job chồng lấn**, **retry**, **timeout**, **alert** và **mốc công bố**.

### Tránh hai job cùng refresh

Nếu lịch mỗi 5 phút nhưng lần refresh trước kéo dài 8 phút, job tiếp theo không nên được phép tự động tạo thêm một refresh độc lập và tranh chấp.

Một số chiến lược:

- Chỉ chạy một instance cho mỗi materialized view.
- Bỏ qua lần kích hoạt mới nếu job cũ đang chạy, rồi đánh dấu tình trạng trễ.
- Xếp hàng có giới hạn, không backlog vô tận.
- Dùng cơ chế job lease/advisory lock phù hợp để chống hai scheduler chạy cùng mục tiêu.
- Theo dõi thời gian chờ và refresh lag.

**Lịch đúng không đồng nghĩa dữ liệu đúng:** phải đo cả trạng thái nguồn được bao phủ và thời gian công bố.

---

## 23. Oracle Database: materialized view có nhiều cơ chế refresh

Oracle Database hỗ trợ materialized view với các chế độ duy trì khác PostgreSQL.

Những khái niệm thường gặp:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `REFRESH COMPLETE` | Tính lại toàn bộ kết quả |
| `REFRESH FAST` | Làm mới tăng dần **khi định nghĩa và metadata đáp ứng điều kiện** |
| `REFRESH FORCE` | Thử phương pháp FAST khi đủ điều kiện, nếu không có thể dùng COMPLETE |
| `ON DEMAND` | Làm mới theo lời gọi/lịch bên ngoài |
| `ON COMMIT` | Làm mới khi transaction nguồn commit, trong những trường hợp được hỗ trợ |
| Materialized view log | Ghi thông tin thay đổi nguồn cần cho một số dạng FAST refresh |

### Ví dụ Oracle: tạo materialized view làm mới theo yêu cầu

```sql
-- Oracle Database: ví dụ khái niệm với bảng orders đã tồn tại.
CREATE MATERIALIZED VIEW mv_daily_sales
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT
    region,
    order_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS total_amount
FROM orders
WHERE status = 'PAID'
GROUP BY region, order_day;
```

Làm mới bằng package Oracle:

```sql
-- Oracle Database
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_DAILY_SALES',
        method => 'C'
    );
END;
/
```

`method => 'C'` yêu cầu kiểu complete refresh theo tham số Oracle tương ứng.

### FAST refresh có yêu cầu, không phải tùy chọn bật tùy ý

`REFRESH FAST` cần dữ liệu thay đổi và định nghĩa view **đủ điều kiện**; thường phải có materialized view log với thông tin phù hợp ở bảng nguồn, và những hạn chế riêng về aggregate, JOIN, hàm và metadata.

Ví dụ về log, **chỉ để minh họa ý tưởng**:

```sql
-- Oracle: cấu trúc minh họa; yêu cầu thực tế của FAST
-- phụ thuộc dạng materialized view, khóa và câu truy vấn.
CREATE MATERIALIZED VIEW LOG ON orders
WITH ROWID, SEQUENCE (region, order_day, amount, status)
INCLUDING NEW VALUES;
```

Việc tạo log như trên **không bảo đảm** mọi materialized view trên bảng `orders` sẽ FAST refresh được. Cần xem điều kiện cụ thể, công cụ phân tích eligibility và tài liệu phiên bản Oracle.

### ON COMMIT đổi độ mới lấy chi phí ghi

Một materialized view đủ điều kiện `REFRESH ... ON COMMIT` có thể được duy trì khi transaction thay đổi bảng nguồn commit. Điều này giảm khoảng cách giữa dữ liệu nguồn đã commit và dữ liệu vật hóa, nhưng thêm **chi phí lên transaction ghi**, và không phải mọi truy vấn materialized view đều cho phép chế độ đó.

**Đừng coi ON COMMIT là một scheduler tách biệt hoàn toàn khỏi đường ghi:** độ trễ và contention có thể chuyển từ background job sang thời gian commit của ứng dụng.

### Query rewrite và dữ liệu stale

Oracle có các cơ chế query rewrite để bộ tối ưu sử dụng materialized view khi phù hợp. Việc có cho phép dùng bản stale hay không phụ thuộc cấu hình và quy tắc freshness/query rewrite của môi trường.

Cần quản lý **tính mới và mức độ chấp nhận stale** khi cho phép truy vấn được rewrite, thay vì chỉ quan sát câu SQL của người dùng.

---

## 24. SQL Server: indexed view thay vì REFRESH thủ công kiểu PostgreSQL

SQL Server có khái niệm **indexed view**: một view thỏa yêu cầu nhất định và được tạo **unique clustered index** để lưu/duy trì kết quả.

Đây **không phải** cùng quy trình với PostgreSQL `REFRESH MATERIALIZED VIEW`.

### Ví dụ ý tưởng SQL Server

Giả sử bảng `dbo.Sales` đã có các cột `customer_id` và `amount` phù hợp:

```sql
-- SQL Server: ví dụ cú pháp, cần đáp ứng thêm các yêu cầu
-- về schema, kiểu dữ liệu, SET options và tính xác định.
CREATE VIEW dbo.v_SalesTotals
WITH SCHEMABINDING
AS
SELECT
    customer_id,
    COUNT_BIG(*) AS sale_count,
    SUM(amount) AS total_amount
FROM dbo.Sales
GROUP BY customer_id;
GO

CREATE UNIQUE CLUSTERED INDEX IX_v_SalesTotals
ON dbo.v_SalesTotals (customer_id);
GO
```

Một số điểm quan trọng:

- `SCHEMABINDING` ràng buộc view với schema của đối tượng nguồn theo quy tắc SQL Server.
- Tham chiếu bảng bằng tên đủ schema như `dbo.Sales`.
- Với view có `GROUP BY`, thường phải có `COUNT_BIG(*)` theo yêu cầu indexed view.
- Unique clustered index cần khóa duy nhất trên hàng view.
- Có các hạn chế về hàm, tính xác định (*determinism*), loại câu lệnh, biểu thức và `SET` options bắt buộc.

### Duy trì tự động khi nguồn đổi

Khi indexed view được tạo và duy trì đúng, các thay đổi dữ liệu nguồn kéo theo việc bảo trì index/view theo cơ chế của SQL Server. Người dùng không gọi một lệnh `REFRESH MATERIALIZED VIEW` giống PostgreSQL sau mỗi UPDATE.

**Chi phí không biến mất:** nó chuyển thành overhead trong thao tác ghi lên bảng nguồn, chi phí index và khả năng tranh chấp tài nguyên.

### Khi có phiên bản/cấu hình SQL Server khác nhau

Việc bộ tối ưu có tự động chọn indexed view cho một truy vấn cụ thể hay cần hint như `NOEXPAND` trong một số ngữ cảnh phụ thuộc phiên bản, edition, cấu hình và hình dạng câu truy vấn. Đừng chỉ dựa trên việc view đã có index để khẳng định mọi truy vấn đều sẽ dùng nó.

**Cách chọn indexed view cần dựa trên write workload, độ trễ đọc và yêu cầu schema**, không nên dùng như một bản dịch từng từ của câu PostgreSQL `REFRESH`.

---

## 25. MySQL: không có materialized view gốc như PostgreSQL

Trong MySQL phổ biến, `CREATE VIEW` định nghĩa truy vấn nhưng không tạo một bảng kết quả vật hóa với lệnh `REFRESH MATERIALIZED VIEW` tương tự PostgreSQL.

Nếu muốn kết quả được lưu trước, các phương án thường gặp gồm:

1. **Bảng tổng hợp** cập nhật bằng job định kỳ.
2. **Bảng snapshot** được xây lại và công bố theo version.
3. **Trigger** cập nhật bảng tổng hợp theo DML nguồn nếu phù hợp.
4. **ETL/CDC pipeline** với checkpoint và upsert.
5. Cache/reporting service hoặc hệ phân tích ngoài MySQL.

### Mẫu bảng tổng hợp MySQL

```sql
-- MySQL: ví dụ bảng đích vật hóa tự quản
CREATE TABLE daily_sales_summary (
    region       VARCHAR(60) NOT NULL,
    business_day DATE NOT NULL,
    paid_orders  BIGINT NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (region, business_day)
);
```

Khi pipeline đã tính một tập **một hàng mỗi khóa**, có thể upsert:

```sql
-- MySQL 8.0.19+ (mẫu VALUES row alias).
INSERT INTO daily_sales_summary (
    region, business_day, paid_orders, total_amount
)
VALUES (
    'North', '2026-08-01', 3, 175.00
) AS incoming
ON DUPLICATE KEY UPDATE
    paid_orders  = incoming.paid_orders,
    total_amount = incoming.total_amount;
```

Đây là **thay thế giá trị tổng hợp của nhóm** bằng bản tính lại, không phải cộng thêm 175 vào giá trị cũ. Nếu muốn incremental delta, phép gán khác và phải chống retry/đếm trùng.

### Lịch chạy trong MySQL

MySQL có **Event Scheduler** ở những phiên bản/cấu hình phù hợp. Ứng dụng cũng có thể dùng scheduler bên ngoài.

Một event job có thể thực hiện logic refresh ở tần suất cố định, nhưng cần kiểm tra quyền, trạng thái scheduler, transaction, thời gian chạy và việc job chồng lấn. Không nên kết luận chỉ cần tạo event là pipeline đã có exactly-once, atomic publish và monitoring đầy đủ.

### Trigger có bảo đảm luôn phù hợp không?

Trigger có thể duy trì tổng theo từng INSERT/UPDATE/DELETE, giảm độ trễ sau commit. Nhưng:

- Chi phí ghi tăng.
- Phải bù các thay đổi tiền, trạng thái, ngày/khu vực.
- Không phải truy vấn tổng hợp nào cũng dễ duy trì theo delta.
- Trigger lỗi có thể làm ảnh hưởng transaction nghiệp vụ.
- Khối lượng dữ liệu lớn có thể gây contention lên cùng hàng tổng.

Hãy chọn trigger cho phép tổng hợp đơn giản và yêu cầu đồng bộ phù hợp, không dùng nó như giải pháp mặc định cho mọi báo cáo phức tạp.

---

## 26. SQLite: view thường và bảng snapshot tự quản

SQLite hỗ trợ `CREATE VIEW`, nhưng không có cùng mô hình PostgreSQL `CREATE MATERIALIZED VIEW`/`REFRESH MATERIALIZED VIEW` trong cú pháp SQLite core.

Một ứng dụng SQLite có thể lưu bảng tổng hợp:

```sql
-- SQLite: bảng tổng hợp tự quản
CREATE TABLE daily_sales_summary (
    region       TEXT NOT NULL,
    business_day TEXT NOT NULL,
    paid_orders  INTEGER NOT NULL,
    total_amount NUMERIC NOT NULL,
    PRIMARY KEY (region, business_day)
);
```

Dữ liệu trong bảng này được cập nhật bằng SQL do ứng dụng gọi hoặc trigger. Khi dùng `CREATE TABLE ... AS SELECT ...`, kết quả ban đầu chỉ là **một bản sao tại thời điểm tạo**; nó không tự chạy lại SELECT mỗi khi nguồn đổi.

Vì SQLite thường được dùng trong ứng dụng nhúng/local, lịch làm mới có thể do **ứng dụng chính** phụ trách thay vì một scheduler chạy thường trực trong server.

### Transaction và concurrency

SQLite có quy tắc locking, journal mode và WAL riêng. Một job xây snapshot lớn có thể ảnh hưởng writer/reader theo cấu hình; không nên sao chép giả định về `REFRESH CONCURRENTLY` của PostgreSQL sang SQLite.

Nếu ứng dụng dùng nhiều connection và WAL, hãy kiểm tra hành vi snapshot và `SQLITE_BUSY`/`SQLITE_BUSY_SNAPSHOT` trong tình huống có ghi đồng thời.

---

## 27. Hệ phân tích dữ liệu: refresh có thể được quản lý tự động

Các nền tảng phân tích như **BigQuery** và một số hệ cloud warehouse cung cấp cơ chế vật hóa/duy trì kết quả khác với database OLTP truyền thống. Ví dụ BigQuery có **materialized views** được hệ thống hỗ trợ làm mới theo quy tắc của sản phẩm, với các giới hạn về loại truy vấn và cách chọn dữ liệu mới hoặc dữ liệu vật hóa.

Điều quan trọng khi chuyển hệ:

- Không giả định một lệnh `REFRESH MATERIALIZED VIEW CONCURRENTLY` của PostgreSQL tồn tại trên BigQuery.
- Không giả định mọi biểu thức tổng hợp/JOIN đều đủ điều kiện materialized view.
- Cấu hình cache, tối ưu hóa truy vấn, giới hạn stale và lịch bảo trì có thể ảnh hưởng dữ liệu thực sự được đọc.
- Giá dịch vụ, tài nguyên quét, chi phí cập nhật và quota có thể chi phối thiết kế.

**Tên tính năng giống nhau không bảo đảm cơ chế refresh giống nhau.** Hãy kiểm tra tài liệu của phiên bản/edition đang sử dụng khi thiết kế SLO độ mới.

## 28. Bảng so sánh theo hệ quản trị

| Hệ quản trị | Đối tượng lưu kết quả thường gặp | Làm mới dữ liệu | Lưu ý về độ trễ/điều kiện |
| --- | --- | --- | --- |
| **PostgreSQL** | `MATERIALIZED VIEW` hoặc bảng tổng hợp | `REFRESH MATERIALIZED VIEW` bằng job; `CONCURRENTLY` nếu đủ index/đã populate | Core không tự refresh theo lịch và không có FAST refresh tăng dần built-in cho mọi view |
| **Oracle Database** | Materialized view | `COMPLETE`, `FAST`, `FORCE`; `ON DEMAND`/`ON COMMIT` theo eligibility | FAST thường cần materialized view logs; ON COMMIT thêm overhead ghi |
| **SQL Server** | Indexed view hoặc bảng tổng hợp | Indexed view được duy trì khi nguồn thay đổi; bảng tổng hợp cần pipeline | Yêu cầu SCHEMABINDING, unique clustered index, SET options và hạn chế định nghĩa |
| **MySQL/InnoDB** | Bảng tổng hợp/snapshot hoặc view thường | Job/trigger/CDC/Event Scheduler tùy thiết kế | Không có cú pháp materialized view refresh như PostgreSQL; quản lý transaction và khóa |
| **SQLite** | Bảng snapshot/aggregate hoặc view thường | Ứng dụng/trigger/SQL thủ công | Cơ chế WAL/locking khác server database; không có native PostgreSQL-style MV |
| **BigQuery** | Materialized view có cơ chế cloud-managed | Bảo trì/làm mới theo tính năng và giới hạn nền tảng | Chi phí, query shape, freshness controls khác DBMS OLTP |

Bảng chỉ mô tả **hướng tiếp cận phổ biến**, không phải danh sách đầy đủ mọi tính năng của mọi phiên bản.

---

## 29. Index trên dữ liệu nguồn và dữ liệu vật hóa

Một materialized view hoặc bảng summary cần tối ưu ở **hai phía**.

### Đọc/tổng hợp nguồn

Với truy vấn:

```sql
SELECT region, business_day, SUM(amount)
FROM orders
WHERE status='PAID'
GROUP BY region, business_day;
```

index hữu ích hay không phụ thuộc kích thước, độ chọn lọc, phạm vi thời gian và kế hoạch. Nếu full refresh phải đọc phần lớn bảng, quét tuần tự và aggregate có thể hợp lý hơn truy cập index từng hàng.

### Đọc kết quả vật hóa

Dashboard thường lọc một khu vực và một khoảng ngày:

```sql
SELECT *
FROM lab_daily_sales_mv_318
WHERE region = 'North'
  AND business_day BETWEEN DATE '2026-08-01'
                       AND DATE '2026-08-31';
```

Index `(region,business_day)` có thể giúp tìm dữ liệu theo mẫu này và cũng đáp ứng điều kiện `CONCURRENTLY` của PostgreSQL trong ví dụ.

### Giá của index

Mỗi index trên kết quả vật hóa thêm chi phí dung lượng, tạo index, refresh/ghi và bảo trì. Index quá nhiều có thể làm refresh chậm.

**Lưu ý:** UNIQUE index cần cho `REFRESH CONCURRENTLY` có **vai trò tính đúng về điều kiện kỹ thuật**, không chỉ là một tối ưu tùy chọn.

---

## 30. Thay đổi schema và công thức tổng hợp

Một báo cáo không chỉ cũ vì dữ liệu nguồn đổi. Nó có thể lỗi thời vì **định nghĩa tính toán thay đổi**.

Ví dụ trước đây doanh thu chỉ tính `PAID`, nhưng nghiệp vụ bổ sung trạng thái `SETTLED`. Nếu materialized view vẫn có:

```sql
WHERE status = 'PAID'
```

thì refresh bao nhiêu lần cũng **không tính `SETTLED`**. Vấn đề lúc này không phải lịch refresh; đó là **công thức/định nghĩa chưa được cập nhật**.

### Quản lý phiên bản logic

Nên ghi nhận:

- Version của truy vấn tổng hợp.
- Version schema nguồn/đích.
- Thời điểm công bố định nghĩa mới.
- Các kỳ lịch sử cần rebuild.
- Cách đối chiếu số liệu giữa version cũ và mới.
- Chính sách giữ hoặc loại dữ liệu vật hóa cũ.

Trong PostgreSQL, việc thay đổi định nghĩa materialized view không đơn giản giống thay text của view thường trong mọi trường hợp; có thể cần tạo đối tượng mới và chuyển dịch vụ sang nó, với kế hoạch index và phụ thuộc tương ứng.

Không nên **DROP và CREATE lại materialized view sản xuất** tùy ý khi có dashboard, quyền truy cập và object dependencies đang trỏ tới nó.

### Backfill

Nếu đổi công thức tính doanh thu từ tháng trước, việc refresh chỉ “7 ngày gần nhất” không đủ. Cần **backfill** những partition lịch sử có ảnh hưởng hoặc rebuild toàn phần theo hợp đồng dữ liệu.

---

## 31. Data retention và bảng phân vùng

Một bảng nguồn nhiều năm có thể được phân vùng theo tháng. Một snapshot đầy đủ trong báo cáo đôi khi chỉ cần 12 tháng gần nhất.

Có thể chọn:

- **Full refresh trên toàn phạm vi báo cáo** nếu dữ liệu và khối lượng cho phép.
- **Refresh theo partition** khi bảng tổng hợp được quản lý chủ động và kiến trúc hỗ trợ.
- **Đóng băng các kỳ đã khóa sổ**, chỉ cập nhật kỳ gần hiện tại, nhưng phải xử lý điều chỉnh hồi tố.
- Lưu **versioned snapshots** cho các kỳ cần tái hiện chính xác.

### Cẩn trọng với retention nguồn

Nếu bảng nguồn xóa giao dịch cũ do chính sách retention, một lần full refresh toàn bộ materialized view có thể **mất kết quả lịch sử**, trừ khi dữ liệu đã được lưu ở nơi khác hoặc truy vấn có nguồn lưu trữ lịch sử phù hợp.

Ngược lại, nếu bảng vật hóa giữ dữ liệu lịch sử lâu hơn nguồn, cần xem nó có thuộc phạm vi bảo mật và retention tương ứng không.

Đừng tự coi vật hóa là cách “lưu trữ dữ liệu vĩnh viễn” nếu chính sách quản trị dữ liệu không cho phép.

---

## 32. Phân quyền và bảo mật dữ liệu vật hóa

Kết quả được lưu trước có thể thay đổi phạm vi truy cập dữ liệu:

- View thường có thể dùng các quy tắc quyền/RLS và ngữ nghĩa security theo DBMS.
- Materialized view là **đối tượng lưu kết quả riêng**, có owner, quyền đọc và cấu hình index riêng.
- Bảng summary có thể lưu thông tin nhạy cảm đã tổng hợp từ bảng nguồn; tổng hợp không tự bảo đảm ẩn danh.
- Quyền chạy refresh thường phải đủ để đọc nguồn và ghi/cập nhật đối tượng đích theo cơ chế DBMS.

### Một rủi ro thường gặp

Một người không có quyền xem bảng giao dịch chi tiết vẫn được cấp quyền `SELECT` trên materialized view tổng hợp toàn doanh nghiệp. Điều đó có thể hợp lệ cho báo cáo công khai, hoặc có thể lộ dữ liệu của tenant khác nếu thiết kế thiếu phân tách.

Khi dữ liệu đa tenant:

- Xác định khóa `tenant_id` trong grain của bảng tổng hợp.
- Kiểm tra điều kiện lọc và quyền truy cập trên đối tượng vật hóa.
- Không dựa trên việc source có RLS để suy rằng mọi cấu trúc vật hóa downstream tự thực thi y hệt chính sách đó.
- Quản lý quyền của job refresh và các bản snapshot tạm.

**Dữ liệu vật hóa vẫn là dữ liệu thật cần bảo vệ**, không chỉ là “cache vô hại”.

---

## 33. Chạy refresh đồng thời với ghi dữ liệu nguồn

Một tình huống quan trọng:

```text
10:00:00 Refresh bắt đầu và chọn snapshot nguồn
10:00:05 Writer INSERT đơn mới nhưng chưa commit
10:00:10 Writer COMMIT
10:00:30 Refresh hoàn tất và công bố
```

Nếu refresh tính theo snapshot từ 10:00:00, đơn commit lúc 10:00:10 **không có** trong bản vừa công bố lúc 10:00:30. Điều này có thể hoàn toàn đúng theo semantics snapshot.

### Công bố mới không có nghĩa chứa mọi commit ngay trước công bố

Do đó câu:

> “Bản này được làm mới lúc 10:00:30”

có thể gây hiểu nhầm. Người dùng có thể tưởng nó phản ánh **mọi giao dịch commit trước 10:00:30**, trong khi snapshot nguồn chỉ bao phủ tới **10:00:00**.

Metadata tốt hơn:

```text
refresh_started_at = 10:00:00
source_snapshot_as_of ≈ 10:00:00
published_at = 10:00:30
```

Với nguồn CDC, nên ghi watermark chính xác của log/offset để biết phần thay đổi đã được bao phủ. Với full refresh từ snapshot, cần hiểu ngữ nghĩa snapshot thực tế, thay vì ghi một thời điểm tùy ý làm “source cutoff”.

### Reader đang đọc bản cũ thì sao?

Cơ chế của database quyết định snapshot reader và cách refresh/ghi tương tác:

- Một PostgreSQL `REFRESH` thường có thể chặn reader.
- `REFRESH ... CONCURRENTLY` hướng tới cho reader tiếp tục truy vấn khi refresh.
- Reader trong transaction snapshot có thể tiếp tục thấy bản nhất quán phù hợp với snapshot.
- Cách quản lý snapshot ID của bảng trung gian cho phép ứng dụng **chủ động giữ một version** xuyên nhiều truy vấn.

Yêu cầu “dashboard không gián đoạn khi làm mới” phải được thiết kế và đo, không chỉ dựa vào tên đối tượng.

---

## 34. Kịch bản kiểm tra chức năng làm mới

Sau khi xây cơ chế refresh, hãy mô tả các kịch bản cần kiểm tra ở môi trường thử nghiệm.

| Tình huống | Điều cần quan sát |
| --- | --- |
| Chèn một hàng mới thỏa điều kiện | Kết quả chỉ thay đổi khi theo đúng cơ chế refresh |
| Chèn hàng không thỏa điều kiện | Không làm thay đổi nhóm tổng hợp ngoài ý muốn |
| Sửa giá trị tiền của hàng đã tính | Tổng phản ánh chênh lệch đúng, không cộng cả giá mới lần nữa |
| Đổi trạng thái PAID → CANCELLED | Giảm đóng góp của hàng nếu nghiệp vụ yêu cầu |
| Xóa nguồn | Kết quả cũ biến mất hoặc điều chỉnh phù hợp |
| Dữ liệu đến muộn | Nhóm ngày trong quá khứ được cập nhật khi nằm trong chính sách |
| Job thất bại giữa chừng | Bản đang phục vụ không trở thành bản thiếu tùy ý |
| Job chạy trùng/overlap | Không publish ngược version hoặc ghi đè checkpoint |
| Nguồn không có sự kiện mới | Chỉ số lag không báo sai chỉ vì event time cũ |
| Thêm category/khu vực mới | Có hàng summary mới và index/phân quyền đúng |
| Thay đổi công thức | Những partition cần rebuild được xử lý đúng |
| Reader đang chạy khi refresh | Chặn/không chặn, snapshot và độ trễ theo thiết kế |

Bảng trên mô tả **kịch bản nghiệp vụ cần chuẩn bị**. Bài học ở STEP 4 chỉ cung cấp nội dung và ví dụ, không yêu cầu chạy QA thực tế trên hệ thống.

---

## 35. Những sai lầm phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Dashboard không có đơn vừa tạo | Materialized view chưa refresh | Xác định SLO, lịch refresh và hiển thị `as_of` |
| View thường bị bảo là “stale cache” | Nhầm view với materialized view | Xác định đối tượng có lưu riêng kết quả hay không; kiểm tra replica/cache |
| Job refresh thành công nhưng số liệu vẫn cũ | Nguồn đọc trễ, checkpoint sai hoặc query sai | Theo dõi source watermark và đối chiếu nguồn |
| Báo cáo bị trống khi refresh lỗi | DELETE commit rồi INSERT lỗi | Dùng transaction hoặc versioned snapshot publish |
| PostgreSQL CONCURRENTLY báo lỗi | Thiếu UNIQUE index phù hợp hoặc MV chưa populate | Tạo index toàn hàng trên cột đơn giản, populate trước |
| CONCURRENTLY vẫn tốn tài nguyên lớn | Nó không phải incremental FAST refresh tự động | Đo và cân nhắc pipeline delta nếu cần |
| Refresh chạy chậm dần theo thời gian | Full scan tăng theo nguồn hoặc index/IO/locking | Phân tích kế hoạch và phạm vi dữ liệu |
| Hai refresh cùng mục tiêu tranh khóa | Scheduler cho job overlap | Dùng single-flight, giới hạn queue/retry |
| Bảng summary cộng doanh số hai lần | Retry áp dụng delta hai lần | Dedup event và checkpoint nguyên tử |
| Sửa đơn từ 100 thành 130 nhưng summary tăng 130 | Dùng giá trị mới như một delta mới | Bù +30 hoặc recompute nhóm |
| Xóa nguồn nhưng vẫn còn nhóm tổng hợp | Pipeline chỉ upsert, không xử lý DELETE | CDC tombstone hoặc thay thế nhóm |
| Late order không hiện trên ngày cũ | Chỉ refresh ngày hiện tại | Lookback/backfill/CDC theo hợp đồng |
| MAX(updated_at) bỏ sót commit muộn | Timestamp không theo thứ tự commit | CDC commit offset hoặc thiết kế chống bỏ sót |
| Metadata refresh mới nhưng source lag lâu | `published_at` bị nhầm với `source_watermark` | Lưu cả hai |
| Kỳ cũ thay đổi sau khi khóa sổ | Chính sách hồi tố không rõ | Versioning và quy tắc điều chỉnh |
| MySQL không nhận `REFRESH MATERIALIZED VIEW` | Không có lệnh PostgreSQL-style trong MySQL | Tạo bảng summary và job tự quản |
| SQL Server indexed view không tạo index được | Thiếu SCHEMABINDING/COUNT_BIG/SET options hoặc định nghĩa không đủ điều kiện | Theo yêu cầu cụ thể của SQL Server |
| Oracle FAST refresh không áp dụng được | Thiếu log hoặc query không eligible | Kiểm tra eligibility; dùng COMPLETE khi thích hợp |
| Reader thấy dữ liệu tenant khác | Vật hóa thiếu phân tách/permission | Thiết kế grain và quyền truy cập riêng |
| Truy vấn kết quả vật hóa nhanh nhưng job ghi rất chậm | Đẩy chi phí sang refresh/index/commit | Đo tổng chi phí đọc và ghi |

## 36. Bài tập thực hành

Các bài từ 1 đến 12 dùng PostgreSQL và các bảng `lab_orders_318`, `lab_daily_sales_view_318`, `lab_daily_sales_mv_318` của phần thực hành. Những bài khác là câu hỏi thiết kế theo hệ quản trị.

### Bài 1. Phân loại đối tượng

Một đối tượng chỉ lưu định nghĩa truy vấn và tính từ bảng nguồn khi được đọc. Một đối tượng khác lưu các hàng tổng hợp và chỉ đổi sau job refresh. Hãy gọi tên hai loại và nêu hệ quả đối với dữ liệu mới.

### Bài 2. So sánh view với materialized view

Ban đầu North–2026-08-01 có 2 đơn PAID, tổng 150. Chèn thêm đơn PAID số tiền 25 vào cùng ngày. Trước refresh, `SELECT` trên view thường và materialized view trả kết quả gì?

### Bài 3. Refresh đầy đủ

Viết câu PostgreSQL làm mới materialized view và câu `SELECT` kiểm tra nhóm North–2026-08-01.

### Bài 4. Refresh đồng thời

Viết UNIQUE index cần thiết cho `REFRESH MATERIALIZED VIEW CONCURRENTLY` trên materialized view có các cột `region,business_day,paid_orders,total_amount` với mỗi cặp `(region,business_day)` là duy nhất. Vì sao index có điều kiện `WHERE region='North'` không đáp ứng?

### Bài 5. WITH NO DATA

Nếu tạo MV bằng `WITH NO DATA`, có thể gọi ngay `REFRESH ... CONCURRENTLY` không? Cần làm gì trước?

### Bài 6. DRAFT trở thành PAID

Đơn 5 là `South / 2026-08-02 / 30` đang `DRAFT`. Sau `UPDATE status='PAID'` và refresh đầy đủ, kết quả MV phải thay đổi ra sao?

### Bài 7. Xóa đơn đã thanh toán

Nếu đơn PAID duy nhất của `South / 2026-08-01` bị xóa, full refresh có nên giữ hàng tổng hợp cũ ở ngày đó không? Vì sao?

### Bài 8. Tính độ trễ theo lịch

Một job refresh bắt đầu mỗi 5 phút, mỗi lượt mất 2 phút và snapshot được chốt khi bắt đầu. Một đơn commit ngay sau snapshot của lượt đầu. Nếu không có trễ nguồn hay lỗi, độ trễ gần bao lâu tới lúc được công bố?

### Bài 9. Metadata refresh

Một pipeline có `last_successful_refresh_at=10:30` nhưng `source_watermark` mới tới 10:05 vì đọc từ replica trễ. Dashboard có thể được coi là mới tới 10:30 không? Bạn sẽ hiển thị metadata nào?

### Bài 10. Bảng trung gian làm mới toàn phần

Viết transaction PostgreSQL dùng `DELETE` rồi `INSERT ... SELECT ... GROUP BY` để xây lại bảng `lab_daily_sales_table_318`. Vì sao cần commit hai phần cùng nhau?

### Bài 11. Snapshot version

Giả sử snapshot đang hoạt động là 41. Job đã tạo đầy đủ dữ liệu snapshot 42 trong bảng `lab_report_rows_318`. Viết câu upsert con trỏ `lab_report_active_318` sang 42 và giải thích lợi ích so với xóa toàn bộ bản đang phục vụ.

### Bài 12. Hiệu chỉnh doanh thu tăng dần

Một giao dịch đã đóng góp 100 vào tổng, sau đó sửa thành 130. Nếu không full refresh, phải điều chỉnh tổng thế nào? Nếu giao dịch bị hủy hoàn toàn, phải làm gì?

### Bài 13. Watermark bỏ sót commit muộn

Transaction A có event ID 5001 nhưng chưa commit; B có ID 5002 và commit sớm; pipeline lưu checkpoint 5002; sau đó A commit. Vì sao cách đọc `WHERE id > 5002` bỏ sót dữ liệu?

### Bài 14. Nhiều UNIQUE trong pipeline

Bảng tổng hợp theo `(tenant_id,region,day)` nhưng người viết tạo `UNIQUE(region,day)`. Điều gì có thể xảy ra khi hai tenant có cùng region và ngày?

### Bài 15. So sánh PostgreSQL với Oracle

Nêu khác biệt giữa PostgreSQL `REFRESH MATERIALIZED VIEW` và Oracle `REFRESH FAST / COMPLETE / ON COMMIT`. Tại sao không thể thêm một từ khóa `FAST` vào PostgreSQL rồi kỳ vọng incremental maintenance gốc?

### Bài 16. SQL Server indexed view

Nêu ít nhất ba yêu cầu/đặc điểm của indexed view và vì sao nó không giống việc chạy cron `REFRESH` mỗi 5 phút.

### Bài 17. MySQL và SQLite

Nếu DBMS không có native PostgreSQL-style materialized view, đề xuất một cách lưu trước tổng doanh thu theo ngày. Ai chạy refresh? Làm sao tránh công bố bảng trống nếu job lỗi?

### Bài 18. Dữ liệu đến muộn

Một đơn thuộc ngày 01-08 được commit hoặc nhận vào ngày 15-08. Pipeline chỉ xử lý 7 ngày gần nhất. Điều gì xảy ra? Đề xuất hai cách giảm rủi ro.

### Bài 19. Monitoring

Chọn ít nhất bốn metric giúp chẩn đoán tình trạng dashboard chậm dữ liệu: một metric về lịch job, một về tiến độ nguồn, một về bản công bố và một về kết quả đối chiếu.

### Bài 20. Thiết kế SLO

Dashboard yêu cầu p95 thay đổi nguồn hiển thị trong 3 phút. Lịch refresh mỗi 5 phút, thời gian chạy 2 phút và snapshot lấy lúc bắt đầu. Có thể cam kết SLO này chỉ dựa vào lịch như vậy không? Đề xuất cải tiến.

---

## 37. Gợi ý lời giải

### Bài 1

Đối tượng chỉ lưu câu truy vấn là **view thường**; khi đọc lại, nó tính trên dữ liệu nguồn phù hợp snapshot. Đối tượng lưu hàng kết quả là **materialized view** hoặc bảng snapshot; dữ liệu có thể trễ nếu chưa được duy trì/làm mới.

### Bài 2

Trước refresh: view thường trả **3 đơn / 175**, materialized view vẫn **2 đơn / 150**. Nếu có transaction snapshot lâu hoặc nguồn đọc trễ, kết quả cụ thể còn phụ thuộc trạng thái đọc; bài giả định lần SELECT mới trên cùng PostgreSQL database sau commit.

### Bài 3

```sql
REFRESH MATERIALIZED VIEW lab_daily_sales_mv_318;

SELECT region, business_day, paid_orders, total_amount
FROM lab_daily_sales_mv_318
WHERE region = 'North'
  AND business_day = DATE '2026-08-01';
```

Sau refresh, số đơn là 3 và tổng 175 nếu dữ liệu nguồn là trạng thái sau khi chèn đơn 6.

### Bài 4

```sql
CREATE UNIQUE INDEX lab_daily_sales_mv_318_uq
ON lab_daily_sales_mv_318 (region, business_day);

REFRESH MATERIALIZED VIEW CONCURRENTLY lab_daily_sales_mv_318;
```

Một partial index chỉ có hàng North không bao phủ **toàn bộ** MV; PostgreSQL không dùng nó làm điều kiện đủ cho `CONCURRENTLY`.

### Bài 5

Không. MV `WITH NO DATA` chưa được populate, nên phải refresh **không đồng thời** để nạp dữ liệu trước:

```sql
REFRESH MATERIALIZED VIEW lab_empty_mv_318 WITH DATA;
```

Sau khi populated và có UNIQUE index phù hợp, MV mới đủ các điều kiện cần để cân nhắc `CONCURRENTLY`.

### Bài 6

Sau khi đơn 5 thành PAID và refresh, MV sẽ có **một hàng mới `South / 2026-08-02 / 1 đơn / 30`**, nếu trước đó nhóm này chưa có đơn PAID.

### Bài 7

Không. Full refresh phải phản ánh truy vấn nguồn hiện tại. Nếu không còn hàng nào ở nhóm `South / 2026-08-01` thỏa điều kiện, nhóm đó phải biến mất khỏi kết quả tổng hợp.

### Bài 8

Gần **7 phút**: sự kiện vừa lỡ snapshot đầu chờ khoảng 5 phút tới snapshot kế tiếp, rồi khoảng 2 phút để kết quả được công bố. Đây là mô hình gần đúng, chưa tính scheduler lag, dữ liệu nguồn trễ, job overlap hay lỗi.

### Bài 9

Không thể tuyên bố dữ liệu đã bao phủ tới 10:30. Cần hiển thị ít nhất **`published_at` và `source_watermark`**; đi kèm trạng thái job và tình trạng replica/CDC lag.

### Bài 10

```sql
BEGIN;

DELETE FROM lab_daily_sales_table_318;

INSERT INTO lab_daily_sales_table_318 (
    region, business_day, paid_orders, total_amount
)
SELECT
    region,
    (paid_at AT TIME ZONE 'UTC')::DATE,
    COUNT(*),
    SUM(amount)
FROM lab_orders_318
WHERE status = 'PAID'
GROUP BY region, (paid_at AT TIME ZONE 'UTC')::DATE;

COMMIT;
```

Giữ cùng transaction để reader không nhận một trạng thái bảng đã commit nhưng mới được xóa hoặc mới nạp một phần.

### Bài 11

```sql
BEGIN;

INSERT INTO lab_report_active_318 (
    report_name, active_snapshot_id, published_at
)
VALUES ('daily_sales', 42, CURRENT_TIMESTAMP)
ON CONFLICT (report_name) DO UPDATE
SET active_snapshot_id = EXCLUDED.active_snapshot_id,
    published_at = EXCLUDED.published_at;

COMMIT;
```

Bản 41 vẫn có thể được giữ tới khi hoàn toàn hết nhu cầu đọc. Job có thể xây 42 mà không xóa/ghi đè bản 41 đang phục vụ; việc công bố là chuyển con trỏ sau khi 42 đầy đủ.

### Bài 12

UPDATE 100 → 130 cần bù **+30** nếu bản cũ 100 đã được cộng. Khi hủy, cần **trừ đóng góp hiện đang được tính** hoặc recompute nhóm. Nếu đơn đổi ngày/khu vực, còn phải sửa cả nhóm cũ và nhóm mới.

### Bài 13

Sequence ID **không đồng nghĩa commit order**. 5002 có thể visible trước 5001; checkpoint 5002 rồi truy vấn `id > 5002` sẽ không bao giờ chọn 5001, dù A commit sau đó. Cần cơ chế cursor theo commit hoặc phòng tránh bỏ sót bằng thiết kế thích hợp.

### Bài 14

`UNIQUE(region,day)` đánh đồng các tenant có cùng khu vực/ngày; có thể từ chối hàng hợp lệ hoặc cập nhật nhầm tổng tenant khác. Khóa đúng cần bao gồm `tenant_id` nếu dữ liệu có phân tách theo tenant.

### Bài 15

PostgreSQL core thực hiện `REFRESH MATERIALIZED VIEW` theo truy vấn định nghĩa, có tùy chọn `CONCURRENTLY` nếu đủ điều kiện index/populated nhưng không có FAST refresh tự động tổng quát. Oracle có những chế độ `FAST`, `COMPLETE`, `FORCE`, `ON DEMAND` và `ON COMMIT` với yêu cầu về eligibility, logs và chi phí ghi. Cú pháp và cơ chế không tương đương.

### Bài 16

Indexed view SQL Server thường đòi hỏi `SCHEMABINDING`, **unique clustered index**, các biểu thức thỏa tính xác định/quy tắc cú pháp và `SET options` phù hợp; view có nhóm cần `COUNT_BIG(*)` theo quy tắc. Kết quả được bảo trì trong hoạt động ghi nguồn, thay vì chỉ làm mới định kỳ bằng cron.

### Bài 17

Tạo bảng summary theo `(region,day)` có khóa duy nhất, dùng job ứng dụng/scheduler hoặc trigger cập nhật. Muốn full refresh an toàn, xây trong transaction hoặc dùng snapshot ID + con trỏ công bố, không commit trạng thái xóa sạch trước khi bản mới sẵn sàng.

### Bài 18

Lookback 7 ngày sẽ bỏ sót thay đổi ngày 01-08 khi pipeline nhận vào ngày 15-08. Có thể dùng **CDC theo commit** để xác định partition quá khứ cần recompute và/hoặc **backfill/full reconciliation định kỳ**; đồng thời xác định giới hạn chậm dữ liệu trong hợp đồng nguồn.

### Bài 19

Ví dụ bốn nhóm:

- `now - last_successful_refresh_at` hoặc thời lượng chạy job.
- CDC offset backlog hoặc tuổi sự kiện chưa xử lý lâu nhất.
- `source_watermark` và `published_at` của snapshot đang phục vụ.
- Sai lệch `SUM(amount)`/`COUNT(*)` giữa nguồn và bản tổng hợp theo các nhóm kiểm tra.

### Bài 20

Không thể chỉ dựa lịch 5 phút + chạy 2 phút để cam kết p95 dưới 3 phút: ngay một sự kiện rơi sau snapshot có thể chờ gần 7 phút. Có thể giảm chu kỳ và thời gian refresh, chuyển sang incremental/CDC, hoặc dùng view thường/truy vấn nguồn trực tiếp cho chỉ tiêu cần rất mới. Phải đo **source-to-visible latency thực tế**, không chỉ thống kê job thành công.

---

## 38. Dọn dữ liệu thực hành

Chỉ xóa những đối tượng do **bài thực hành này tạo** trong database/schema riêng, khi không còn session khác dùng chúng.

```sql
-- PostgreSQL: xóa theo quan hệ phụ thuộc của lab.
DROP MATERIALIZED VIEW IF EXISTS lab_daily_sales_mv_318;
DROP MATERIALIZED VIEW IF EXISTS lab_empty_mv_318;
DROP VIEW IF EXISTS lab_daily_sales_view_318;

DROP TABLE IF EXISTS lab_report_active_318;
DROP TABLE IF EXISTS lab_report_rows_318;
DROP TABLE IF EXISTS lab_refresh_runs_318;
DROP TABLE IF EXISTS lab_daily_sales_table_318;
DROP TABLE IF EXISTS lab_orders_318;
```

Không dùng `CASCADE` một cách tùy tiện trên schema dùng chung: nó có thể xóa thêm đối tượng phụ thuộc ngoài dự kiến.

## 39. Tổng kết

**Làm mới dữ liệu** không chỉ là thực thi lại một câu truy vấn; đó là toàn bộ quy trình xác định **trạng thái nguồn được bao phủ**, **tính toán kết quả**, **công bố một bản hoàn chỉnh** và **đo thời gian cho đến khi reader thấy kết quả**.

Các nguyên tắc quan trọng nhất:

1. **View thường** thực thi truy vấn trên nguồn khi đọc, không có bản kết quả vật hóa riêng để refresh.
2. **Materialized view** lưu kết quả; trong PostgreSQL cần gọi `REFRESH MATERIALIZED VIEW`, và `CONCURRENTLY` chỉ dùng khi đáp ứng điều kiện index/đã populate.
3. **Bảng trung gian** có thể đóng vai trò snapshot hoặc aggregate nhưng phải tự thiết kế cập nhật, transaction, phiên bản và lịch.
4. **Độ mới không bằng thời gian hoàn thành job.** Phân biệt source commit, source watermark, thời điểm snapshot và published time.
5. **Full refresh** dễ đối chiếu với nguồn nhưng tốn tài nguyên; **incremental refresh** tiết kiệm hơn khi thay đổi ít, nhưng phải xử lý retry, UPDATE, DELETE, late data, checkpoint và thay đổi công thức.
6. **Không công bố kết quả dang dở.** Dùng transaction hoặc snapshot version để giữ một bản hoàn chỉnh khi job lỗi.
7. **Không áp một cú pháp cho mọi DBMS.** Oracle có FAST/COMPLETE/ON COMMIT khi đủ điều kiện, SQL Server có indexed view được bảo trì khi ghi, còn MySQL/SQLite thường dùng bảng tổng hợp tự quản.
8. **Đặt SLO và đo lag thật.** Kết hợp tiến độ nguồn, trạng thái công bố, thời gian refresh và kiểm tra chất lượng dữ liệu.

Khi hiểu rõ mối liên hệ giữa **view, dữ liệu vật hóa, refresh strategy, source watermark và mức độ chấp nhận độ trễ**, bạn có thể chọn giải pháp SQL phù hợp với quy mô, chi phí và yêu cầu độ mới của từng hệ quản trị mà không đánh đổi âm thầm tính đúng đắn của báo cáo.
