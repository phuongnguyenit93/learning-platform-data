# Bắt đầu từ mục tiêu độ trễ, thông lượng và truy vấn đại diện trong PostgreSQL

Khi một hệ thống PostgreSQL “chạy chậm”, phản ứng phổ biến là tìm một câu `SELECT` rồi thêm index, thay đổi `JOIN` hoặc tăng bộ nhớ. Nhưng **tối ưu truy vấn không bắt đầu bằng việc chỉnh SQL**. Nó bắt đầu bằng việc hiểu hệ thống đang phải thực hiện công việc gì, yêu cầu phục vụ người dùng nhanh đến mức nào và cần xử lý bao nhiêu công việc đồng thời.

Một thay đổi có thể giảm thời gian thực thi của một câu SQL từ 50 ms xuống 5 ms, nhưng lại làm tăng chi phí `INSERT`, khiến các request khác chờ khóa lâu hơn hoặc không giúp trang người dùng nhanh lên vì phần lớn thời gian nằm ở mạng và ứng dụng. Ngược lại, một câu SQL 200 ms có thể hoàn toàn chấp nhận được trong báo cáo chạy mỗi đêm nhưng không thể chấp nhận ở endpoint kiểm tra tồn kho phải phục vụ hàng nghìn request mỗi giây.

Vì vậy, một dự án tối ưu hiệu năng PostgreSQL nên mở đầu bằng ba câu hỏi:

1. **Mục tiêu độ trễ (latency) là gì?** Người dùng hay hệ thống gọi API phải đợi bao lâu, đo ở đâu, và áp dụng cho bao nhiêu phần trăm request?
2. **Mục tiêu thông lượng (throughput) là gì?** Hệ thống phải xử lý bao nhiêu truy vấn, transaction hoặc thao tác nghiệp vụ mỗi giây, dưới mức đồng thời và tỷ lệ đọc–ghi nào?
3. **Truy vấn đại diện (representative queries) là gì?** Những mẫu SQL, kiểu tham số, phân bố dữ liệu và transaction nào thực sự tạo thành khối lượng công việc của ứng dụng?

Bài học thuộc chương **Tối ưu truy vấn**, module **Database Engine Relational PostgreSQL**. Bạn sẽ xây một quy trình đo có thể tái lập, dùng `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, `pgbench`, thống kê từ PostgreSQL và telemetry của ứng dụng để ưu tiên tối ưu đúng chỗ.

## 1. “Nhanh hơn” chưa phải một mục tiêu đủ rõ

Hai câu mô tả sau rất khác nhau:

> “Trang đơn hàng chậm, cần tối ưu PostgreSQL.”

> “Trong giờ cao điểm 600 request/giây, endpoint liệt kê 20 đơn gần nhất của một tenant phải có p95 dưới 120 ms và p99 dưới 350 ms, tỷ lệ thành công tối thiểu 99,9%; đồng thời không làm p95 tạo đơn vượt 250 ms.”

Câu thứ nhất không cho biết:

- Độ trễ được tính từ trình duyệt, từ gateway hay từ phía PostgreSQL?
- Một request chạy mấy câu SQL?
- Tải hiện tại là 5 hay 5.000 request/giây?
- Chậm ở tất cả tenant hay chỉ tenant rất lớn?
- Lỗi timeout có được tính hay bị bỏ khỏi số liệu?
- Việc “tối ưu” có được phép làm chậm luồng ghi không?

Câu thứ hai có **mục tiêu có thể đo**, bao gồm tốc độ, tải và giới hạn tác động phụ.

### Từ vấn đề tới giả thuyết kiểm chứng

Một giả thuyết tốt:

> Truy vấn liệt kê đơn gần nhất hiện phải quét và sắp xếp quá nhiều hàng theo từng tenant. Index `(tenant_id, status, created_at DESC, order_id DESC)` có thể giảm số block phải đọc và loại bỏ một bước sort. Cần đo lại với cả tenant nhỏ lẫn tenant lớn, đồng thời kiểm tra chi phí cập nhật `status`.

Giả thuyết chỉ đáng được chấp nhận khi có bằng chứng, không phải khi query planner xuất hiện chữ `Index Scan`.

## 2. Phân biệt latency, throughput và concurrency

Ba khái niệm liên quan nhưng **không đồng nghĩa**:

| Khái niệm | Câu hỏi | Đơn vị thường dùng |
| --- | --- | --- |
| **Latency** | Một thao tác mất bao lâu để hoàn tất? | ms, giây |
| **Throughput** | Bao nhiêu thao tác hoàn tất trong một đơn vị thời gian? | requests/s, queries/s, transactions/s |
| **Concurrency** | Có bao nhiêu thao tác cùng tồn tại/đang xử lý hoặc chờ? | số request/connection/transaction đồng thời |

Ví dụ minh họa:

- Một endpoint có p95 latency **180 ms**.
- Trong giờ cao điểm nhận **400 requests/s**.
- Có khoảng **80 request đang tồn tại đồng thời** ở một thời điểm.

Ba con số mô tả những mặt khác nhau. Một hệ thống có thể xử lý nhiều request/giây nhưng vẫn có tail latency cao; một hệ thống có thể phản hồi từng request rất nhanh khi tải thấp nhưng suy sụp khi nhiều request cùng đến.

### QPS, TPS và RPS

- **RPS** (*requests per second*): thường đo ở tầng API/gateway.
- **QPS** (*queries per second*): số câu SQL được thực thi mỗi giây; cần làm rõ có tính những câu lệnh chuẩn bị, SELECT, DML hay không.
- **TPS** (*transactions per second*): số transaction hoàn tất mỗi giây; PostgreSQL và công cụ benchmark có những cách tính/nguồn thống kê khác nhau.

Một request HTTP có thể gọi **8 truy vấn SQL** trong **2 transaction**. Vì vậy 1.000 RPS không tự tương đương 1.000 QPS hay 1.000 TPS.

**Luôn ghi rõ đơn vị, ranh giới phép đo và điều kiện tải** khi báo cáo kết quả.

## 3. Độ trễ ở tầng nào?

Một request lấy danh sách đơn hàng có thể trải qua:

~~~mermaid
flowchart LR
    U["Người dùng"] --> G["Gateway / mạng"]
    G --> A["Ứng dụng"]
    A --> P["Chờ connection pool"]
    P --> D["PostgreSQL"]
    D --> R["Đọc kết quả / truyền dữ liệu"]
    R --> S["Ứng dụng xử lý và serialize"]
    S --> U
~~~

Độ trễ đầu-cuối của request bao gồm nhiều thành phần:

\[
L_{\mathrm{request}} \approx
L_{\mathrm{network}}+
L_{\mathrm{gateway}}+
L_{\mathrm{pool}}+
L_{\mathrm{database}}+
L_{\mathrm{application}}+
L_{\mathrm{response}}
\]

Đây là sơ đồ tư duy để phân bổ thời gian, không phải bảo đảm mọi thành phần đều hoàn toàn độc lập hay có thể cộng trực tiếp từ các biểu đồ đo ở các tầng khác nhau.

Ví dụ minh họa:

| Thành phần | Thời gian |
| --- | ---: |
| Gateway và mạng | 20 ms |
| Đợi connection từ pool | 65 ms |
| SQL trên PostgreSQL | 8 ms |
| Đọc kết quả, xử lý và serialize | 27 ms |
| **Tổng** | **120 ms** |

Nếu SQL giảm từ 8 ms còn 2 ms, request có thể chỉ cải thiện khoảng 6 ms. Lúc này tối ưu index không giải quyết nguyên nhân chính là **chờ connection pool**.

**Không dùng `EXPLAIN ANALYZE Execution Time` làm số đo độ trễ của toàn API.** Nó chỉ phản ánh một phần công việc trên server, không bao gồm mọi bước của client và mạng.

## 4. Latency trung bình không phản ánh trải nghiệm đuôi chậm

Một API có 100 request:

- 95 request trả trong 20 ms.
- 5 request trả trong 3 giây.

Trung bình có thể trông không quá tệ so với một số hệ thống, nhưng 5 người dùng vẫn phải chờ rất lâu.

Các percentile thường dùng:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **p50 / median** | Khoảng 50% các giá trị đo không vượt quá mức này |
| **p90** | Khoảng 90% các giá trị đo không vượt quá mức này |
| **p95** | Khoảng 95% các giá trị đo không vượt quá mức này |
| **p99** | Khoảng 99% các giá trị đo không vượt quá mức này |
| **max** | Giá trị lớn nhất quan sát được trong mẫu |
| **mean** | Trung bình cộng; có thể bị kéo lệch bởi số ít request rất chậm |

Percentile phải đi kèm **khoảng đo, kích thước mẫu, số lỗi/timeout và cách thu thập**. Nếu chỉ có 30 request, kết quả p99 không đủ ổn định để kết luận về tail latency ở quy mô lớn.

### Ví dụ SLO

> “Trong cửa sổ 1 giờ, ít nhất 95% request thành công của `GET /orders` phải hoàn thành dưới 150 ms; đồng thời tỷ lệ request thành công tối thiểu 99,9%.”

Ở đây ta đã xác định một tiêu chí latency **và** một tiêu chí availability. Khi tính các percentile, cần ghi rõ cách xử lý request lỗi/timeout để không vô tình tạo một báo cáo đẹp bằng cách loại bỏ các request tệ nhất.

### Mean của PostgreSQL khác p95 API

`pg_stat_statements.mean_exec_time` là thống kê tổng hợp **thời gian thực thi SQL**, không tự cung cấp p95 của request HTTP. Muốn p95/p99 đầu-cuối, dùng application tracing, metrics từ gateway hoặc client-side benchmark đủ chi tiết.

## 5. SLI, SLO và SLA khác nhau

Ba thuật ngữ hay gặp trong tối ưu hiệu năng:

- **SLI — Service Level Indicator:** chỉ số được đo, ví dụ tỷ lệ request có latency dưới 150 ms.
- **SLO — Service Level Objective:** mục tiêu nội bộ cho SLI trong một cửa sổ, ví dụ 95% request dưới 150 ms.
- **SLA — Service Level Agreement:** cam kết với bên ngoài, có thể gắn điều kiện/hệ quả pháp lý hoặc thương mại.

Ví dụ SLI có thể được định nghĩa:

\[
SLI_{\mathrm{latency}} =
\frac{\text{số request hợp lệ có latency }\leq150\ \mathrm{ms}}
{\text{tổng request hợp lệ trong cửa sổ}}
\]

Muốn sử dụng công thức cần **định nghĩa “request hợp lệ”**: có bao gồm client hủy request, retry, timeout, health check, request lỗi 5xx và request 4xx hay không?

Một SLO tốt cần:

1. Chỉ số.
2. Điểm đo.
3. Đơn vị.
4. Phạm vi endpoint/workflow.
5. Điều kiện tải.
6. Cửa sổ thời gian.
7. Chính sách tính lỗi/timeout.

**Không tối ưu một query để đạt mục tiêu không được đo ở nơi sử dụng thật.**

## 6. Mục tiêu thông lượng phải có điều kiện tải

Thông lượng 5.000 QPS tự nó không nói lên nhiều điều. Cần biết:

- Bao nhiêu connection đang mở?
- Tỷ lệ đọc/ghi?
- Truy vấn trả một hàng hay một triệu hàng?
- Dữ liệu nằm trong cache hay trên disk?
- Transaction dài hay ngắn?
- Có bao nhiêu truy vấn cùng một hàng nóng?
- Tỷ lệ lỗi, timeout và rollback?
- Mức sử dụng CPU, I/O, WAL và replica lag?

Một hệ thống đạt 5.000 QPS với truy vấn `SELECT 1` không chứng minh xử lý được 5.000 QPS của báo cáo `JOIN` lớn và `UPDATE` có trigger.

### Goodput khác throughput tổng

Nếu client retry mạnh khi timeout, tổng số request được nhận có thể tăng, nhưng số **nghiệp vụ hoàn thành thành công** lại giảm. Hãy phân biệt:

- Requests attempted/s.
- Requests completed/s.
- Successful business operations/s (*goodput*).
- Failed/timeouts/s.
- Retries/s.

Không quảng cáo một benchmark tăng TPS nếu phần lớn transaction đó là lỗi bị bỏ qua hoặc `ON CONFLICT DO NOTHING` trên dữ liệu trùng.

## 7. Concurrency và Little's Law

Một trực giác hữu ích từ lý thuyết hàng đợi là **Little's Law**:

\[
N=\lambda\times W
\]

Trong trạng thái ổn định và với ranh giới hệ thống được định nghĩa nhất quán:

- `N`: số công việc trung bình cùng tồn tại trong hệ thống.
- `\lambda`: tốc độ công việc hoàn thành/đến ở trạng thái ổn định.
- `W`: thời gian trung bình một công việc ở trong hệ thống.

Ví dụ: nếu hệ thống hoàn thành ổn định **200 request/s**, thời gian trung bình một request là **0,25 giây**, thì trung bình có khoảng:

\[
N=200\times0{,}25=50
\]

request đang tồn tại trong phạm vi được đo.

**Đừng suy rằng “50 concurrent requests” nghĩa là cần đúng 50 connection PostgreSQL.** Một request có thể đợi ở gateway/queue, làm việc CPU hoặc gọi dịch vụ khác mà không giữ DB connection. Ngược lại, một request có thể mở nhiều query/connection tùy kiến trúc.

### Khi tăng tải, độ trễ không nhất thiết tăng tuyến tính

Lúc server còn dư năng lực, tăng request rate có thể làm throughput tăng mà latency thay đổi ít. Gần mức bão hòa, queue bắt đầu dồn, tail latency tăng nhanh và timeout xuất hiện.

~~~text
Throughput
   ^
   |                 ________ gần bão hòa
   |              __/
   |           __/
   |        __/
   |     __/
   |  __/
   +--------------------------> Offered load

Latency p95/p99 có thể tăng rất mạnh gần vùng bão hòa.
~~~

Vì vậy phải đo latency ở **mức tải mục tiêu**, không chỉ đo một query khi server rảnh.

## 8. Một truy vấn nhanh hơn chưa chắc cải thiện TPS

Giả sử truy vấn A từ 15 ms giảm xuống 3 ms. Nếu transaction còn:

- 90 ms gọi dịch vụ ngoài.
- 35 ms chờ lock.
- 20 ms ghi WAL/commit.
- 12 ms xử lý ứng dụng.

thì tổng transaction chỉ giảm một phần nhỏ.

Trong tình huống khác, A là query chiếm 80% CPU PostgreSQL và được thực thi 20.000 lần/giây. Giảm CPU của A có thể tăng đáng kể tổng thông lượng.

Do đó cần đánh giá:

1. Query đang chiếm bao nhiêu **tổng tài nguyên và tổng thời gian**?
2. Query có nằm trên **critical path** của request quan trọng không?
3. Có bottleneck khác không?
4. Nếu tối ưu thành công, bottleneck có chuyển sang nơi khác không?
5. SLO đầu-cuối có được cải thiện không?

Đừng coi mọi millisecond ở mọi query có giá trị kinh doanh bằng nhau.

## 9. Truy vấn đại diện là gì?

Một **representative query** không chỉ là câu SQL ngắn gọn trông giống truy vấn thật. Nó là một mẫu thực thi có:

- SQL shape: `WHERE`, `JOIN`, `ORDER BY`, `LIMIT`, aggregate, subquery...
- Loại tham số và giá trị cụ thể.
- Phân bố tham số thường gặp và trường hợp xấu.
- Số hàng và phân bố dữ liệu hiện tại.
- Isolation/transaction boundary.
- Cách gọi: literal, bind parameters hay server-side prepared.
- Tần suất, số concurrent clients và tỷ trọng trong workload.
- Số hàng/bộ dữ liệu trả cho ứng dụng.
- SLO của workflow mà query phục vụ.

Hai statement cùng template:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;
~~~

nhưng một lần `$1 = 1` (tenant có 5 triệu đơn), một lần `$1 = 99` (tenant có 500 đơn) có thể có plan và chi phí rất khác.

**Một template không đồng nghĩa một phép đo đại diện cho mọi tham số.**

## 10. Cách nhóm workload thành các lớp truy vấn

Trong một hệ thống bán hàng, có thể phân loại:

| Nhóm | Workload | Điều quan trọng |
| --- | --- | --- |
| **Point lookup** | Tìm đơn theo PK | Độ chọn lọc rất cao, index lookup |
| **Top-N listing** | 20 đơn gần nhất theo tenant/status | Filter, order, limit, pagination |
| **Detail + JOIN** | Đơn + khách + items | Join cardinality, N+1, data transfer |
| **Aggregation** | Tổng doanh thu theo ngày | Số hàng phải đọc, grouping, memory/temp I/O |
| **Insert path** | Tạo đơn và items | Unique/FK/index maintenance, WAL |
| **State transition** | Pending → paid | Row lock, indexed columns, contention |
| **Maintenance** | Xóa/archive dữ liệu cũ | Batch size, WAL, vacuum, locks |

Chỉ chọn query dễ tối ưu như point lookup sẽ tạo bộ benchmark thiếu đại diện. Cần có cả các truy vấn **tốn tài nguyên** và các câu **ghi** có thể chịu chi phí từ index mới.

## 11. Tần suất và độ đắt cần được xem cùng nhau

Giả sử thu thập được:

| Query | Calls/phút | Mean SQL time | Tổng SQL time/phút (minh họa) |
| --- | ---: | ---: | ---: |
| Q1 — List orders | 30.000 | 8 ms | 240.000 ms |
| Q2 — Order detail | 10.000 | 4 ms | 40.000 ms |
| Q3 — Report | 10 | 500 ms | 5.000 ms |
| Q4 — Update status | 6.000 | 12 ms | 72.000 ms |

Bảng số chỉ minh họa cách ưu tiên, không phải số liệu đã chạy.

Q3 chậm nhất trên **một lần gọi**, nhưng Q1 tiêu tốn tổng thời gian thực thi SQL cao nhất. Q4 cũng quan trọng vì là luồng ghi. Nếu Q3 là báo cáo điều hành cần xong trước deadline, nó vẫn có thể đáng ưu tiên dù tổng thời gian nhỏ.

### Một mô hình ưu tiên

Xem xét đồng thời:

- Tần suất.
- p95/p99 và SLO.
- Tổng CPU/I/O.
- Mức độ ảnh hưởng nghiệp vụ.
- Rủi ro lỗi/timeout.
- Chi phí sửa và triển khai.
- Tác động lên workload khác.

Không chỉ sắp danh sách query theo `mean_exec_time DESC`.

## 12. Dữ liệu giả đều có thể đánh lừa query planner

Giả sử production có 10 tenant:

- Tenant 1 chiếm **60% tổng đơn**.
- Chín tenant còn lại chia nhau 40%.

Nếu tạo seed chia đều, mỗi tenant có 10% đơn; planner sẽ gặp một phân bố khác hoàn toàn.

Những yếu tố cần phản ánh khi tạo dữ liệu thử:

| Yếu tố | Vì sao quan trọng |
| --- | --- |
| Số hàng, kích thước bảng/index | Ảnh hưởng seq scan vs index scan |
| Tenant skew | Mỗi tham số có selectivity khác |
| Trạng thái phổ biến/hiếm | Index có thể có ích cho failed nhưng không cho pending |
| NULL distribution | Điều kiện `IS NULL`/partial index |
| Tương quan với vị trí heap | Range scan, BRIN, random I/O |
| Độ rộng hàng | Cache/heap page và data transfer |
| Tần suất thay đổi cột | HOT, WAL và index maintenance |
| Bloat/visibility map | Index-only scan và heap fetch |
| Thời gian/chu kỳ | Peak tháng, ngày, giờ, dữ liệu gần đây |
| Khóa ngoại và trigger | Giá phải trả khi DML thực thi |

Không cần một bản sao chính xác từng giá trị nhạy cảm để benchmark; có thể tạo dữ liệu tổng hợp dựa trên **phân bố đã đo và được phép sử dụng**.

## 13. Chuẩn bị lab PostgreSQL có thể tái lập

Toàn bộ ví dụ dùng schema `perf_goal_lab` trong **database chỉ để thực hành**.

**Cảnh báo:** script bắt đầu bằng `DROP SCHEMA IF EXISTS ... CASCADE`, có thể xóa toàn bộ đối tượng trong schema đó. Không thực hiện trên production hoặc một schema chứa dữ liệu cần giữ.

Bộ dữ liệu mô phỏng:

- 6.000 khách hàng, phân theo 10 tenant.
- 240.000 đơn hàng, trong đó tenant 1 chiếm khoảng 60%.
- 480.000 dòng chi tiết, hai dòng mỗi đơn.
- Trạng thái có phân bố không đều, có nhóm hiếm.
- Thời gian tạo trải dài nhiều ngày.
- Một số index bắt buộc do primary key/foreign key và một số index ứng viên sẽ được tạo sau.

### 13.1. Tạo schema và bảng

~~~sql
-- CHỈ CHẠY TRONG DATABASE LAB.
DROP SCHEMA IF EXISTS perf_goal_lab CASCADE;
CREATE SCHEMA perf_goal_lab;

CREATE TABLE perf_goal_lab.customers (
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL,
    display_name text NOT NULL,
    email text NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email)
);

CREATE TABLE perf_goal_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'failed')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    total_amount numeric(12,2) NOT NULL CHECK (total_amount >= 0),
    note text,
    payload text NOT NULL,

    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES perf_goal_lab.customers(tenant_id, customer_id)
);

CREATE TABLE perf_goal_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES perf_goal_lab.orders(order_id),
    line_no smallint NOT NULL CHECK (line_no IN (1,2)),
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Bảng đã có index từ những ràng buộc:

- `orders(order_id)`: primary key.
- `customers(tenant_id, customer_id)`: primary key.
- `customers(tenant_id, email)`: unique.
- `order_items(order_id, line_no)`: primary key.

**PostgreSQL không tự tạo index cho mọi cột FK ở phía bảng con.** Chúng ta sẽ đo lợi ích của index mới trên `orders(tenant_id,status,created_at,order_id)`, không xóa các index phục vụ ràng buộc.

### 13.2. Nạp 6.000 khách hàng

~~~sql
INSERT INTO perf_goal_lab.customers (
    tenant_id, customer_id, display_name, email
)
SELECT
    CASE
        WHEN g <= 3000 THEN 1
        ELSE 2 + ((g - 3001) % 9)
    END,
    g,
    'Customer ' || g,
    'customer' || g || '@example.test'
FROM generate_series(1, 6000) AS s(g);
~~~

Tenant 1 có 3.000 khách hàng. Chín tenant còn lại có khoảng 333–334 khách hàng mỗi tenant.

### 13.3. Nạp 240.000 đơn có tenant skew

~~~sql
INSERT INTO perf_goal_lab.orders (
    order_id, tenant_id, customer_id, status,
    created_at, updated_at, total_amount, note, payload
)
SELECT
    g::bigint,
    t.tenant_id,
    CASE
        WHEN t.tenant_id = 1 THEN 1 + (g % 3000)
        ELSE 3001 + (t.tenant_id - 2) + 9 * (g % 333)
    END,
    CASE
        WHEN (g * 17) % 101 = 0 THEN 'failed'
        WHEN (g * 17) % 101 < 21 THEN 'paid'
        ELSE 'pending'
    END,
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '30 seconds',
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '30 seconds',
    (20 + (g % 300))::numeric(12,2),
    CASE
        WHEN g % 50 = 0 THEN 'Manual review'
        ELSE NULL
    END,
    repeat('x', 100)
FROM generate_series(1, 240000) AS s(g)
CROSS JOIN LATERAL (
    VALUES (
        CASE
            WHEN g % 10 < 6 THEN 1
            ELSE 2 + (g % 9)
        END
    )
) AS t(tenant_id);
~~~

Cách sinh này có chủ đích:

- `g % 10 < 6` tạo khoảng 60% đơn cho tenant 1.
- Các tenant khác chia phần còn lại.
- Phân loại trạng thái theo modulo 101 thay vì chỉ modulo 5/10 để tránh trạng thái tương quan quá trực tiếp với tenant.
- Thứ tự `created_at` gần với thứ tự chèn, giúp minh họa correlation.
- Payload có độ rộng 100 ký tự để bảng không quá nhỏ.

### 13.4. Nạp hai dòng chi tiết cho mỗi đơn

~~~sql
INSERT INTO perf_goal_lab.order_items (
    order_id, line_no, product_code, quantity, unit_price
)
SELECT
    o.order_id,
    line_no::smallint,
    CASE line_no
        WHEN 1 THEN 'SKU-A'
        ELSE 'SKU-B'
    END,
    1,
    CASE line_no
        WHEN 1 THEN 10 + (o.order_id % 100)
        ELSE 10 + ((o.order_id % 300) / 100) * 100
    END::numeric(12,2)
FROM perf_goal_lab.orders AS o
CROSS JOIN generate_series(1, 2) AS s(line_no);
~~~

Vì `quantity = 1` và hai `unit_price` được xây từ phần chục/trăm của `order_id % 300`, tổng hai dòng tương ứng `total_amount = 20 + (order_id % 300)` theo seed này.

### 13.5. Cập nhật thống kê

~~~sql
ANALYZE perf_goal_lab.customers;
ANALYZE perf_goal_lab.orders;
ANALYZE perf_goal_lab.order_items;
~~~

`ANALYZE` giúp planner có thống kê về số hàng, phân bố và độ chọn lọc. Khi làm benchmark nghiêm túc, cần giữ thống kê tương đương giữa baseline và phương án mới.

### 13.6. Xác nhận dataset

~~~sql
SELECT
    COUNT(*) AS orders_count,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_count,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_count
FROM perf_goal_lab.orders;

SELECT tenant_id, COUNT(*) AS orders_count
FROM perf_goal_lab.orders
GROUP BY tenant_id
ORDER BY orders_count DESC, tenant_id;

SELECT COUNT(*) AS items_count
FROM perf_goal_lab.order_items;
~~~

Dự kiến:

- `orders_count = 240000`.
- `items_count = 480000`.
- Tenant 1 có khoảng `144000` đơn.
- `failed` khoảng 1%, `paid` khoảng 20%, còn lại `pending`.

Giá trị chính xác của những phân loại modulo nên được lấy từ truy vấn kiểm tra, không phải từ giả định tỷ lệ xấp xỉ.

## 14. Chọn truy vấn đại diện cho lab

Không đo mỗi một câu `SELECT` thuận lợi cho index. Bộ truy vấn cần nhiều kiểu truy cập và cả luồng ghi.

### Q1 — Danh sách 20 đơn pending mới nhất của tenant nhỏ

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Đây là một API dạng **top-N listing**: lọc theo tenant/trạng thái, trả ít hàng theo thứ tự mới nhất.

### Q2 — Cùng API nhưng tenant rất lớn

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Cùng template nhưng số hàng ứng viên khác lớn. Đây là ví dụ về **parameter skew** mà không thể bỏ qua.

### Q3 — Chi tiết đơn và các dòng hàng

~~~sql
SELECT
    o.order_id,
    o.status,
    o.total_amount,
    c.display_name,
    i.line_no,
    i.product_code,
    i.quantity,
    i.unit_price
FROM perf_goal_lab.orders AS o
JOIN perf_goal_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
JOIN perf_goal_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.tenant_id = 7
  AND o.order_id = 123456
ORDER BY i.line_no;
~~~

Query này minh họa đọc một đơn qua primary key và JOIN tới bảng con. Nếu đơn 123456 thuộc tenant khác, truy vấn trả 0 hàng — đây là một tình huống kiểm thử **đúng ngữ nghĩa phân quyền tenant**.

Khi đo throughput Q3, đừng chọn cố định ID không thuộc tenant rồi benchmark hàng loạt những lần trả 0 hàng. Hãy dùng cặp `tenant_id, order_id` có thật theo tập tham số.

### Q4 — Tổng hợp doanh thu trong một khoảng thời gian cố định

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM perf_goal_lab.orders
WHERE status = 'paid'
  AND created_at >= timestamptz '2026-02-01 00:00:00+00'
  AND created_at <  timestamptz '2026-03-01 00:00:00+00'
GROUP BY tenant_id
ORDER BY paid_amount DESC;
~~~

Đây là truy vấn aggregate đọc nhiều hàng hơn. Nó có thể phù hợp scan/parallel aggregate hoặc một phương án khác tùy thống kê.

**Đừng thay mốc cố định bằng `now() - interval '7 days'` khi seed nằm trong quá khứ**: trong lab vào thời điểm hiện tại, query có thể trả 0 hàng và kết quả đo không còn đại diện.

### W1 — Chuyển trạng thái có điều kiện

~~~sql
BEGIN;

UPDATE perf_goal_lab.orders
SET
    status = 'paid',
    updated_at = clock_timestamp()
WHERE order_id BETWEEN 50001 AND 50500
  AND status = 'pending'
RETURNING order_id;

ROLLBACK;
~~~

Ví dụ rollback để giữ lab. Khi benchmark write workload thật, dùng database disposable và transaction commit tương đương production, không dùng mãi một kịch bản rollback-only.

### W2 — INSERT đơn mới

Một hệ thống tạo đơn cần duy trì primary key, foreign key, các index ứng viên và WAL. Chỉ đo Q1/Q2 mà không đo W2 sẽ bỏ qua chi phí ghi bổ sung khi thêm index.

Bộ benchmark write bên dưới sẽ mô tả một chiến lược cấp ID tránh trùng và dùng dữ liệu hợp lệ.

## 15. Đặt trọng số cho workload đại diện

Một ví dụ tỷ lệ ở giờ cao điểm:

| Nhóm | Tỷ trọng transaction ứng dụng | SLO minh họa |
| --- | ---: | --- |
| Q1 — top-N tenant nhỏ | 35% | p95 API dưới 150 ms |
| Q2 — top-N tenant lớn | 10% | p95 API dưới 250 ms |
| Q3 — chi tiết đơn | 25% | p95 API dưới 120 ms |
| Q4 — báo cáo | 5% | 99% dưới 5 giây |
| W1 — đổi trạng thái | 15% | p95 dưới 200 ms |
| W2 — tạo đơn | 10% | p95 dưới 250 ms |

Các số liệu này **chỉ là yêu cầu giả định của bài học**, không phải SLO khuyến nghị cho mọi hệ thống.

Tại sao phải lưu tỷ trọng?

Một index phục vụ Q1/Q2 chiếm tổng 45% request có thể đáng đầu tư hơn một index chỉ phục vụ Q4 chiếm 5%, ngay cả khi Q4 trên một lần chạy chậm hơn. Nhưng Q4 vẫn có thể là nghiệp vụ then chốt nên cần SLO riêng.

### Không cộng trực tiếp p95 của từng nhóm

Nếu Q1 p95 = 80 ms và Q2 p95 = 300 ms, p95 của hỗn hợp toàn hệ thống **không** tính bằng 35%×80 + 10%×300 rồi cộng các nhóm khác. Percentile của hỗn hợp phải được tính từ **phân bố thời gian của tất cả request trong hỗn hợp** hoặc một cách tổng hợp histogram thích hợp.

Công thức trung bình có trọng số dùng cho **mean**, không thay thế percentile.

## 16. Baseline: đo trước khi sửa SQL hoặc tạo index

Khi chưa có index `(tenant_id,status,created_at,order_id)`:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT
    order_id,
    created_at,
    total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Lặp với Q2 và Q4. Lưu ít nhất:

- Query text và tham số.
- PostgreSQL major version.
- Tổng số hàng/table/index size.
- Kế hoạch: `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Sort`, `Limit`...
- `actual rows`, `Rows Removed by Filter` và estimate.
- `Buffers: shared hit/read`, local/temp nếu có.
- `Execution Time`.
- Trạng thái cache, đồng thời và số lần thử.

### Vì sao TIMING OFF?

`TIMING OFF` giảm overhead đo thời gian riêng lẻ ở từng node, nhưng `EXPLAIN ANALYZE` vẫn thực thi truy vấn và báo tổng thời gian. Khi cần tìm node cụ thể bị chậm, có thể chạy một phép thử chẩn đoán bật timing.

**Không cam kết một plan cố định từ bài học**. Planner chọn phương án theo cost, thống kê, version, cấu hình, cache, số hàng và độ phân bố thực tế.

## 17. Đọc plan: Index Cond khác Filter

Một plan có thể chứa:

~~~text
Index Cond: (tenant_id = 7)
Filter: (status = 'pending')
Rows Removed by Filter: ...
~~~

Điều này gợi ý index chỉ giúp tìm hàng theo tenant, còn `status` được áp như bộ lọc sau khi đọc dữ liệu ứng viên.

Với index đa cột đúng thứ tự:

~~~text
Index Cond: ((tenant_id = 7) AND (status = 'pending'))
~~~

PostgreSQL có thể tìm phần index tương ứng, duyệt theo `created_at DESC, order_id DESC` và lấy đủ 20 hàng mà không cần sort toàn bộ.

### Thấy Index Scan không có nghĩa đã tối ưu

Phải hỏi:

1. Số buffer có giảm không?
2. Có giảm số hàng đọc/loại bằng Filter không?
3. Có còn phải Sort tập lớn không?
4. Có cải thiện p95 dưới mức tải thật không?
5. Có làm các luồng INSERT/UPDATE chậm hơn không?

Một query đổi từ Seq Scan 4,0 ms sang Index Scan 3,8 ms chưa chắc đáng đánh đổi thêm một index lớn.

## 18. Thử một thay đổi index rồi đo lại

Ứng viên cho Q1/Q2:

~~~sql
CREATE INDEX idx_perf_orders_tenant_status_latest
ON perf_goal_lab.orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);

ANALYZE perf_goal_lab.orders;
~~~

Đo lại cùng SQL và tham số:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Tương tự với tenant 1.

### Cơ chế kỳ vọng

Khi hai cột đầu là so sánh bằng, index B-tree có thể cung cấp thứ tự theo các cột tiếp theo. Với `LIMIT 20`, PostgreSQL có thể dừng sau khi lấy đủ số hàng cần thiết thay vì quét và sort hàng nghìn/hàng trăm nghìn bản ghi.

### Phải đo các truy vấn không phải mục tiêu

Sau khi tạo index, cũng chạy Q3, Q4, W1 và W2.

- Q3 có thể vẫn dùng primary key của `orders` và `order_items`.
- Q4 có thể vẫn dùng Seq Scan vì cần đọc/tổng hợp rất nhiều hàng.
- W1 có thể tốn thêm công việc khi sửa `status` là một thành phần khóa index.
- W2 cần chèn entry vào index bổ sung.

**Một index tăng tốc Q1/Q2 nhưng làm W1/W2 xấu đi là một trade-off, không phải thất bại hay thành công tự động.**

## 19. Bảng báo cáo trước/sau nên như thế nào?

Ví dụ **số liệu giả định**:

| Chỉ số | Baseline | Có index |
| --- | ---: | ---: |
| Q1 p95 SQL (ms) | 45 | 5 |
| Q2 p95 SQL (ms) | 120 | 8 |
| Q3 p95 SQL (ms) | 9 | 9 |
| Q4 p95 SQL (ms) | 180 | 178 |
| W1 UPDATE p95 (ms) | 14 | 17 |
| W2 INSERT p95 (ms) | 8 | 10 |
| Write TPS ở 16 clients | 2.800 | 2.650 |
| Index storage bổ sung | 0 | 20 MB |

**Đây là ví dụ cách ghi kết quả, không phải con số đã benchmark.** Cần thay bằng số đo thực, kèm độ phân tán và cấu hình thử nghiệm.

### Công thức giảm latency

\[
\text{Tỷ lệ giảm latency} =
\frac{L_{\mathrm{before}}-L_{\mathrm{after}}}
{L_{\mathrm{before}}}\times100\%
\]

Ví dụ Q1 từ 45 xuống 5 ms là giảm khoảng 88,9%. Không nên ghi “tăng throughput 88,9%” vì throughput có mẫu số và cơ chế khác.

### Công thức tăng throughput

\[
\text{Tỷ lệ tăng throughput} =
\frac{X_{\mathrm{after}}-X_{\mathrm{before}}}
{X_{\mathrm{before}}}\times100\%
\]

Nếu throughput giảm từ 2.800 còn 2.650 TPS, đây là **giảm** khoảng 5,36%, dù truy vấn đọc mục tiêu tốt lên.

## 20. Query latency và transaction latency khác nhau

Một transaction tạo đơn có thể chạy:

~~~text
BEGIN
  INSERT orders
  INSERT order_items
  UPDATE inventory
  INSERT outbox
COMMIT
~~~

Nếu bốn câu SQL riêng lẻ mỗi câu 3 ms, transaction **không nhất thiết** mất đúng 12 ms. Nó còn có:

- Chờ lock.
- Chờ kết nối/network round trip.
- Trigger/FK checks.
- WAL flush tại commit theo cấu hình.
- Thời gian ứng dụng tính toán giữa các statement.
- Serialization/retry khi tranh chấp.

Một thay đổi index có thể làm `INSERT orders` chậm thêm 1 ms nhưng giảm 20 ms ở một câu `SELECT` trong transaction khác. Để đánh giá hệ thống, cần đo **từng SQL, transaction và API workflow**.

### Đo cùng một ranh giới

Khi so baseline/candidate:

- Nếu baseline dùng p95 API, candidate cũng phải dùng p95 API.
- Nếu baseline dùng execution time server, candidate cũng phải đo theo đó.
- Nếu benchmark chạy transaction COMMIT, không so với bên kia chỉ chạy SELECT hoặc ROLLBACK.
- Không trộn độ trễ được ghi ở client với `Execution Time` server rồi gọi là chênh lệch index.

## 21. Đọc thống kê thật từ pg_stat_statements

`pg_stat_statements` là extension có thể tổng hợp số lần gọi và thời gian thực thi của những SQL statement đã được PostgreSQL ghi nhận.

### Điều kiện

Thông thường cần được cấu hình trong `shared_preload_libraries` và restart server trước khi dùng. Sau khi preload, người có quyền phù hợp tạo extension trong database:

~~~sql
-- Chỉ chạy nếu môi trường đã cấu hình extension và cho phép.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

**Không tự sửa cấu hình hoặc restart production chỉ để làm một bài thực hành.** Nếu extension chưa sẵn sàng, dùng application tracing, logs và EXPLAIN để thu thập bằng chứng trước.

### Truy vấn top SQL theo tổng execution time

~~~sql
SELECT
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 2) AS mean_exec_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_exec_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 180) AS query_template
FROM pg_stat_statements
WHERE dbid = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Các tên cột phù hợp với nhiều phiên bản PostgreSQL hiện đại; cần đối chiếu version extension. Quyền xem query text/thống kê của user khác có thể bị giới hạn.

### Diễn giải

- `calls`: số lần được ghi nhận.
- `total_exec_time`: tổng thời gian thực thi server cho query template.
- `mean_exec_time`: trung bình thực thi.
- `stddev_exec_time`: mức phân tán thời gian thực thi.
- `rows`: tổng số hàng báo cáo trong thống kê.
- `shared_blks_hit/read`: hoạt động buffer tích lũy.

`pg_stat_statements` **không tự cho biết đầy đủ p95/p99 của từng request API**. Nó cũng có thể gộp tenant 1 và tenant 7 vào cùng query template, khiến mean che khuất parameter skew.

## 22. Chọn truy vấn theo tổng chi phí thay vì câu chậm nhất

Ví dụ:

~~~text
Q1: mean 2 ms × 100.000 calls = 200.000 ms tổng
Q2: mean 200 ms × 100 calls = 20.000 ms tổng
~~~

Q2 chậm hơn **100 lần trên một call**, nhưng Q1 tiêu thụ tổng execution time lớn hơn gấp **10 lần** trong khoảng quan sát.

Khi ưu tiên, cần xem:

- Q1 có CPU/I/O nhiều và lặp rất thường xuyên?
- Q2 có deadline riêng, là thao tác quan trọng hay gây lock?
- Một query chậm hơn có nằm trên critical path của request người dùng?
- Tối ưu Q1 có ảnh hưởng write path hay không?
- Có N+1 query từ ORM làm một endpoint phát hàng trăm SQL nhỏ?

**Đừng tối ưu ngẫu nhiên query lâu nhất trong log** mà không biết tần suất và ảnh hưởng.

## 23. N+1 queries: một request có thể chậm dù mỗi SQL nhanh

Giả sử API tải 100 đơn:

~~~text
SELECT * FROM orders WHERE tenant_id = ? LIMIT 100;
Sau đó lặp 100 lần:
  SELECT * FROM order_items WHERE order_id = ?;
~~~

Mỗi query con chỉ 1 ms, nhưng 100 round trip có thể khiến API chậm đáng kể.

Cần đo:

- Số SQL/request.
- Tổng DB time/request.
- Thời gian chờ network/connection.
- Số lượng hàng trả về.
- Có thể batch query hoặc dùng JOIN/aggregation phù hợp hay không.

Một index trên `order_items(order_id)` giúp mỗi query con, nhưng **giảm từ 101 query xuống 1–2 query** có thể mang lợi ích lớn hơn. Tuy nhiên JOIN một-nhiều có thể nhân bản dữ liệu header, nên cần kiểm tra kích thước kết quả và các kiểu fetch.

**Tối ưu truy vấn bắt đầu bằng workflow**, không chỉ một câu SQL.

## 24. Dữ liệu skew và thống kê most-common values

Dữ liệu lab có tenant 1 lớn vượt trội. Kiểm tra:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    correlation,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'perf_goal_lab'
  AND tablename = 'orders'
  AND attname IN (
      'tenant_id',
      'status',
      'created_at',
      'customer_id'
  )
ORDER BY attname;
~~~

Những thông tin quan trọng:

- `n_distinct`: ước lượng số giá trị phân biệt.
- `most_common_vals` và `most_common_freqs`: giá trị phổ biến và tần suất tương ứng.
- `correlation`: tương quan thứ tự giá trị với thứ tự vật lý của heap theo thống kê.
- `null_frac`: tỷ lệ NULL.

Chỉ biết có 10 tenant không giúp ước lượng đúng số hàng tenant 1. Giá trị phổ biến và skew ảnh hưởng lớn đến planner.

### Khi thống kê thiếu chính xác

Nếu đã bulk INSERT hàng triệu dòng, chạy `ANALYZE` để cập nhật. Nếu nhiều cột có mối quan hệ chặt, có thể cân nhắc extended statistics để cải thiện estimate.

~~~sql
CREATE STATISTICS st_orders_tenant_status (
    dependencies,
    mcv
)
ON tenant_id, status
FROM perf_goal_lab.orders;

ANALYZE perf_goal_lab.orders;
~~~

Extended statistics giúp planner hiểu một số kiểu quan hệ giữa cột, **không tự tạo đường truy cập như index**. Hãy đo plan và estimate trước/sau để xác nhận có hữu ích.

## 25. Prepared statement: literal query có thể khác ứng dụng

Ứng dụng JDBC thường dùng bind parameters:

~~~sql
WHERE tenant_id = $1
  AND status = $2
~~~

PostgreSQL có thể chọn **custom plan** dựa trên tham số cụ thể hoặc **generic plan** dùng lại cho nhiều lần, tùy cơ chế plan cache và cost.

Thử trong lab:

~~~sql
PREPARE latest_orders(integer, text) AS
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(7, 'pending');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE latest_orders(1, 'pending');

DEALLOCATE latest_orders;
~~~

Hai tham số tenant có thể nhận kế hoạch khác trong custom-plan mode, nhưng generic plan không luôn phản ánh skew theo từng giá trị.

### Thử generic và custom có chủ đích

Ở phiên bản hỗ trợ `plan_cache_mode`:

~~~sql
SET plan_cache_mode = force_custom_plan;

PREPARE p(integer, text) AS
SELECT order_id, created_at
FROM perf_goal_lab.orders
WHERE tenant_id = $1 AND status = $2
ORDER BY created_at DESC
LIMIT 20;

EXPLAIN EXECUTE p(1, 'pending');
EXPLAIN EXECUTE p(7, 'pending');

SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE p(1, 'pending');
EXPLAIN EXECUTE p(7, 'pending');

DEALLOCATE p;
RESET plan_cache_mode;
~~~

Đây là **phép thử chẩn đoán**, không phải lời khuyên buộc toàn instance dùng custom/generic plan. Khi so benchmark, hãy dùng giao thức giống ứng dụng thật.

### Vì sao kiểu dữ liệu tham số cũng quan trọng?

Nếu cột là `integer` nhưng ứng dụng truyền text rồi cast không đúng cách, biểu thức có thể khác với SQL literal bạn thử. Kiểm tra SQL do ORM/JDBC sinh, bind types và cast, không suy từ câu query viết tay.

## 26. Thông lượng dưới concurrency: đừng chỉ đo SQL đơn lẻ

Để biết PostgreSQL xử lý được bao nhiêu request dưới tải, cần công cụ phát các request đồng thời theo mô hình workload.

`pgbench` là lựa chọn thuận tiện cho benchmark PostgreSQL với custom scripts. Nó có thể mô phỏng nhiều client, threads, prepared protocol và tỷ trọng những loại transaction.

### Chuẩn bị script read-only

Tạo file ví dụ `latest-small.sql` trên máy chạy benchmark:

~~~text
\set tenant_id random(2, 10)
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = :tenant_id
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

File `latest-hot.sql`:

~~~text
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Chạy trên database lab:

~~~bash
pgbench -n -c 12 -j 4 -T 120 -P 10 -M prepared \
  -f latest-small.sql@7 \
  -f latest-hot.sql@3 \
  "postgresql://bench_user@localhost:5432/benchmark_db"
~~~

Ý nghĩa:

| Tham số | Ý nghĩa |
| --- | --- |
| `-n` | Không chạy bước vacuum khởi tạo của benchmark built-in |
| `-c 12` | 12 client connections đồng thời |
| `-j 4` | 4 worker threads |
| `-T 120` | Chạy khoảng 120 giây |
| `-P 10` | Báo tiến độ theo khoảng 10 giây |
| `-M prepared` | Prepared protocol |
| `-f script@weight` | Tỷ trọng tương đối giữa các script |
| URI | Chỉ kết nối tới database benchmark riêng |

**Không tự chạy benchmark tải cao trên production.** Trước khi chạy, kiểm tra hostname, database, quyền và tài nguyên theo quy trình của tổ chức.

### Vì sao cần cả tenant lớn?

Nếu chỉ dùng `random(2,10)`, benchmark loại toàn bộ tenant 1. Trong một hệ thống có 60% dữ liệu của tenant lớn, workload có thể bị đo quá lạc quan.

Tỷ lệ 7:3 trong ví dụ là giả định. Thực tế phải lấy từ telemetry.

## 27. Kiểm thử tải cố định và tải bão hòa

Có hai câu hỏi khác nhau.

### A. Với tải mục tiêu, độ trễ là bao nhiêu?

Dùng một offered load được kiểm soát, ví dụ 250 transaction/s nếu môi trường hỗ trợ:

~~~bash
pgbench -n -c 12 -j 4 -T 120 -R 250 \
  -M prepared -P 10 \
  -f latest-small.sql@7 \
  -f latest-hot.sql@3 \
  "postgresql://bench_user@localhost:5432/benchmark_db"
~~~

`-R` đặt mục tiêu rate theo cơ chế của pgbench. Khi server quá tải, transaction có thể phải đợi lịch và một số có thể bị bỏ/không đáp ứng đúng giờ tùy cấu hình; cần xem throughput thực, latency và các thống kê đi kèm.

**Điều cần so sánh:** Ở cùng offered load, p95/p99 và error rate trước/sau có tốt hơn không?

### B. Năng lực tối đa tới đâu?

Tăng dần client/rate để xác định vùng throughput bão hòa và điểm latency bắt đầu tăng mạnh.

**Điều cần so sánh:** Candidate có tăng goodput cực đại mà vẫn giữ SLO không? Nếu chỉ tăng số request thử nhưng lỗi nhiều hơn, không phải cải thiện hữu ích.

### Closed-loop và open-loop

Một benchmark kiểu “client gửi request tiếp theo sau khi request trước xong” có thể tự giảm offered load khi hệ thống chậm. Điều đó gây **coordinated omission** trong một số phương pháp đo tail latency.

Khi cần đánh giá SLO dưới arrival rate cố định, nên có một bài thử đặt offered load độc lập với thời gian phản hồi và ghi nhận request trễ/bị bỏ. Hãy ghi rõ mô hình load generator được dùng thay vì so các percentile từ hai kiểu benchmark khác nhau.

## 28. Muốn đo p95/p99 thì cần dữ liệu latency phù hợp

`pgbench` báo thông tin về TPS và latency, nhưng để phân tích từng transaction và phân phối đuôi có thể bật logging:

~~~bash
pgbench -n -c 12 -j 4 -T 120 -l \
  -M prepared \
  -f latest-small.sql@7 \
  -f latest-hot.sql@3 \
  "postgresql://bench_user@localhost:5432/benchmark_db"
~~~

File log có thể rất lớn. Nội dung và định dạng tùy phiên bản/option; cần bảo vệ dữ liệu nhạy cảm và tránh ghi log quá nhiều làm benchmark tự bị ảnh hưởng.

Với application API, ưu tiên latency histograms/distributed traces từ công cụ giám sát đang có để đo đầu-cuối. Có thể kết hợp số liệu client-side benchmark và server-side EXPLAIN để lý giải nguyên nhân.

### Không suy p95 từ mean và standard deviation một cách máy móc

Phân phối latency thường không chuẩn, có đuôi dài do lock wait, I/O, GC, checkpoint hoặc burst traffic. Mean và stddev không đủ để tính chính xác p95/p99 trong mọi workload.

## 29. Kiểm tra thời gian chờ khóa thay vì vội tạo index

Một statement `UPDATE` có thể mất 2 giây **không phải vì truy vấn không có index**, mà vì đang chờ transaction khác giữ khóa hàng.

Dùng một connection được phép xem hoạt động:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    pg_blocking_pids(pid) AS blockers,
    left(query, 180) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

Nếu `wait_event_type = 'Lock'` và có blocking PIDs, cần tìm nguyên nhân:

- Transaction đang mở quá lâu?
- Hai worker cập nhật cùng hàng nóng?
- Migration DDL giữ table-level lock?
- FK/trigger gây chờ?
- Có deadlock/retry storm?
- Connection pool quá lớn làm tăng tranh chấp?

Một index có thể giúp **giảm thời gian tìm hàng** trước khi khóa, nhưng không xóa được mọi lock conflict.

### Không nhầm thời gian CPU với thời gian chờ

Một query có execution time 2 giây nhưng phần lớn chờ lock có giải pháp khác query dùng 2 giây CPU để sort/aggregate. Cần đo wait events và truy vấn bị chặn để chọn hướng tối ưu đúng.

## 30. Kiểm tra I/O và bộ nhớ trước khi “tăng work_mem”

Một aggregate có thể chậm vì sort/hash spilling ra temporary files:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    status,
    SUM(total_amount)
FROM perf_goal_lab.orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

Kế hoạch có thể cho biết:

- `Sort Method` và bộ nhớ hoặc dung lượng đĩa sử dụng.
- `HashAggregate`/`GroupAggregate`.
- `temp read/write`.
- `Buffers`.
- Thời gian ở từng node nếu timing bật.

Nếu một node spilling vì dữ liệu lớn, `work_mem` có thể ảnh hưởng. Nhưng **không tăng work_mem toàn server bừa bãi**: mỗi query có thể có nhiều operator sử dụng bộ nhớ, và nhiều query chạy đồng thời.

Tương tự, một query I/O nặng có thể cần thay đổi plan/index/partition, hoặc cần xem cache và disk throughput trước khi chỉnh SQL.

## 31. Tối ưu theo thứ tự ưu tiên của hệ thống

Một thứ tự thực dụng:

1. **Xác nhận đúng SLO và điểm đo.**
2. **Xem telemetry:** đâu là API/workload vi phạm SLO hoặc chiếm nhiều tài nguyên?
3. **Xác định thời gian chờ** (pool, lock, I/O, network) và thời gian thực thi.
4. **Lấy query template và tham số đại diện.**
5. **Đọc plan và số hàng ước lượng/thực tế.**
6. **Kiểm tra index/statistics hiện có.**
7. **Đặt một giả thuyết tối ưu đơn lẻ.**
8. **Đo baseline, thay đổi, đo lại.**
9. **Đo toàn hỗn hợp đọc–ghi ở cùng offered load.**
10. **Chỉ triển khai khi lợi ích vượt chi phí, có rollback và giám sát.**

Không nhảy thẳng đến bước 7 khi chưa biết workload thực sự bị nghẽn ở đâu.

## 32. Index tốt cho đọc có thể gây tác dụng phụ lên ghi

Index ứng viên:

~~~sql
CREATE INDEX idx_perf_orders_tenant_status_latest
ON perf_goal_lab.orders (
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

có thể phục vụ Q1/Q2. Nhưng câu:

~~~sql
UPDATE perf_goal_lab.orders
SET status = 'paid'
WHERE order_id = 10001
  AND status = 'pending';
~~~

đụng `status` — một cột nằm trong index. PostgreSQL có thể phải duy trì entry của index, ghi WAL và giảm cơ hội dùng **HOT update**.

Vì vậy cần đo:

- p95/p99 W1 UPDATE.
- W2 INSERT throughput.
- `n_tup_upd`, `n_tup_hot_upd`.
- WAL bytes trong cùng cửa sổ thử.
- Index size.
- CPU/I/O và replica lag nếu có.

### HOT ratio

Trong `pg_stat_user_tables`:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'perf_goal_lab';
~~~

Tỷ lệ HOT tham khảo:

\[
\text{HOT ratio} =
\frac{\text{HOT updates}}{\text{total updates}}
\]

Nên dùng **delta bộ đếm trước/sau một khoảng benchmark**, không dùng tỷ lệ lũy kế từ rất lâu trước đó để suy hiệu ứng của đúng một thay đổi.

### Không coi một index luôn làm UPDATE chậm

Chi phí thực phụ thuộc cột được sửa, khả năng HOT, page fill, cache, số index hiện có, số hàng và concurrency. Cần đo thay vì áp một hệ số nhân cố định.

## 33. EXPLAIN ANALYZE với DML phải được xử lý an toàn

Để xem plan cập nhật trong lab:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE perf_goal_lab.orders
SET
    status = 'paid',
    updated_at = clock_timestamp()
WHERE order_id BETWEEN 50001 AND 50500
  AND status = 'pending';

ROLLBACK;
~~~

**`EXPLAIN ANALYZE` thực thi DML thật.** `BEGIN ... ROLLBACK` giúp giữ dữ liệu lab, nhưng vẫn có thể tạo WAL/tuple versions và công việc cleanup. Đừng dùng mô hình luôn rollback để tự nhận là đã đo được chi phí commit/vacuum thực tế của production.

Tùy chọn `WAL` của `EXPLAIN` được hỗ trợ từ PostgreSQL 13. Trên server cũ hơn, dùng tùy chọn thích hợp với phiên bản hoặc công cụ quan sát khác.

## 34. Đo WAL và dung lượng trong phép thử ghi

Nếu PostgreSQL version hỗ trợ:

~~~sql
-- PostgreSQL 14+, số liệu cấp instance.
SELECT
    wal_records,
    wal_fpi,
    wal_bytes
FROM pg_stat_wal;
~~~

Dùng chênh lệch trước–sau workload, đồng thời ghi nhận hoạt động nền của database khác. `pg_stat_wal` là **thống kê toàn instance**, không tự phân tách WAL cho query hoặc schema trong một cluster bận.

Dung lượng:

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size('perf_goal_lab.orders'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('perf_goal_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('perf_goal_lab.orders'::regclass)
    ) AS total_size;
~~~

Một index tăng tốc API nhưng chiếm hàng GB vẫn có thể xứng đáng; một index chỉ 10 MB vẫn có thể không cần nếu nó làm write path thường xuyên trả chi phí mà không đem lợi ích rõ ràng.

## 35. Benchmark đọc phải giống cách ứng dụng đọc

Ứng dụng có thể dùng:

- JDBC `PreparedStatement`.
- ORM tạo nhiều câu SELECT với `LIMIT/OFFSET`.
- Keyset pagination theo `(created_at, order_id)`.
- Truy vấn đọc danh sách rồi gọi thêm chi tiết từng hàng.
- Cùng query template nhưng param types khác nhau.
- Connection pool với statement caching.

Một benchmark chỉ dùng literal SQL trong psql có thể cho plan khác.

### Offset pagination vs keyset

Với danh sách mới nhất:

~~~sql
SELECT order_id, created_at
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
OFFSET 10000
LIMIT 20;
~~~

PostgreSQL có thể phải đi qua rất nhiều hàng trước khi bỏ qua 10.000 hàng. Index phù hợp giúp tìm/sắp nhanh nhưng không làm offset sâu miễn phí.

Nếu API hỗ trợ cursor/keyset pagination:

~~~sql
SELECT order_id, created_at
FROM perf_goal_lab.orders
WHERE tenant_id = 7
  AND status = 'pending'
  AND (created_at, order_id)
      < (
          timestamptz '2026-03-01 00:00:00+00',
          175000::bigint
        )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Điều kiện tuple so sánh theo thứ tự phù hợp với cặp sắp xếp; các giá trị cursor phải lấy từ **hàng cuối của trang trước** trong workflow thật. Sử dụng timestamp/ID tùy ý ở ví dụ chỉ để minh họa cú pháp, không phải một cursor đã được phát hành.

### So cả kết quả nghiệp vụ

Keyset giúp giảm công việc với nhiều pagination sâu, nhưng có khác biệt về khả năng nhảy thẳng tới trang N, xử lý dữ liệu thêm/xóa và sự ổn định của cursor. Không tối ưu performance bằng cách đổi contract API mà không cân nhắc người dùng.

## 36. Đừng chỉ benchmark top-N với tenant nhỏ

Một index:

~~~sql
(tenant_id, status, created_at DESC, order_id DESC)
~~~

có thể trả 20 đơn mới nhất rất nhanh cho cả tenant nhỏ/lớn. Nhưng những query khác không có `LIMIT` hoặc dùng `ORDER BY total_amount` có thể ứng xử hoàn toàn khác.

Bộ tham số kiểm thử cần bao phủ:

1. Tenant nhiều đơn.
2. Tenant ít đơn.
3. Status `pending` phổ biến.
4. Status `failed` hiếm.
5. Khoảng ngày ngắn.
6. Khoảng ngày dài.
7. Kết quả 0 hàng.
8. Kết quả 1 hàng.
9. Kết quả rất nhiều hàng.
10. Dữ liệu gần hiện tại/đầu lịch sử.
11. Query có `LIMIT` nhỏ.
12. Query aggregate không `LIMIT`.

Không cần mô phỏng vô hạn giá trị tham số; chọn **các lớp có tính chất chi phí khác nhau** rồi cân trọng số theo telemetry thực.

## 37. Điều kiện giả định với index và selectivity

Nếu có index chỉ theo `status`:

~~~sql
CREATE INDEX idx_perf_orders_status
ON perf_goal_lab.orders(status);
~~~

Query:

~~~sql
SELECT COUNT(*)
FROM perf_goal_lab.orders
WHERE status = 'pending';
~~~

cần xử lý khoảng 79% hàng trong lab. Planner có thể chọn Seq Scan/Parallel Seq Scan vì phù hợp chi phí, dù index tồn tại.

Cùng index đó, query `status = 'failed'` chỉ khớp khoảng 1% hàng có thể nhận được lợi ích khác. Tuy vậy không có ngưỡng selectivity chung mà dưới ngưỡng đó PostgreSQL bắt buộc chọn index.

**Truy vấn đại diện phải có cả giá trị phổ biến và hiếm**, không chỉ mẫu thuận lợi cho giả thuyết của người tối ưu.

## 38. Một thay đổi có thể chuyển bottleneck

Trước index, Q1 tiêu thụ phần lớn CPU để lọc và sort. Sau index, Q1 rất nhanh, nhưng hệ thống vẫn chưa tăng throughput vì:

- Connection pool bị giới hạn.
- API serialization chiếm CPU.
- WAL flush thành bottleneck của write path.
- Một hàng inventory nóng gây lock contention.
- Đọc từ replica bị lag.
- Network bão hòa do trả quá nhiều dữ liệu.

Đây là hiện tượng **bottleneck migration**: giải quyết một giới hạn khiến giới hạn tiếp theo trở nên rõ ràng.

Vì vậy sau mỗi lần tối ưu phải:

1. Đo lại đầu-cuối.
2. Quan sát thành phần chiếm thời gian mới.
3. Xác định có đạt SLO không.
4. Dừng tối ưu khi mục tiêu đã đạt và chi phí thay đổi tiếp không xứng đáng.
5. Không tiếp tục tạo index chỉ vì còn một query có thể nhanh hơn vài microsecond.

## 39. Khi nào nên tối ưu query trước, khi nào cần thay kiến trúc?

Một query chậm có thể giải quyết bằng:

- Index phù hợp.
- Sửa điều kiện lọc để không dùng biểu thức cản đường index.
- JOIN đúng khóa và tránh Cartesian product.
- Loại bỏ N+1.
- Pagination/giảm số cột trả.
- Cập nhật `ANALYZE`/extended statistics.
- Chia batch đối với DML.
- Điều chỉnh transaction để giảm lock wait.

Nhưng một số bài toán cần giải pháp lớn hơn:

- Dashboard tính tổng từ hàng tỷ hàng mỗi lần người dùng mở → cân nhắc aggregate table/materialized view hoặc pipeline phù hợp.
- Dữ liệu lịch sử cực lớn cần truy vấn theo khoảng thời gian → cân nhắc partitioning/BRIN theo đặc điểm dữ liệu.
- Đọc nhiều hơn khả năng một node đáp ứng → cân nhắc caching/read replicas và tính nhất quán.
- Workload ghi vượt năng lực WAL/storage → tối ưu batching, schema, storage/architecture.

**Đừng chuyển sang kiến trúc phức tạp khi chưa đo rõ bottleneck; cũng đừng cố dùng một index để giải quyết giới hạn thuộc bản chất workload.**

## 40. Thiết kế A/B test công bằng

Quy trình tối thiểu:

~~~text
1. Tạo dataset D và thống kê nhất quán.
2. Baseline A: các index bắt buộc + workload W.
3. Warm-up A, đo A nhiều lượt.
4. Khôi phục về trạng thái D.
5. Candidate B: thêm đúng index ứng viên.
6. Warm-up B tương đương, đo B cùng W.
7. So sánh latency, throughput, buffers, WAL, HOT, size.
8. Nếu nghi cache/time drift, chạy thêm A/B luân phiên.
~~~

### Những sai lệch cần tránh

- A chạy khi cache lạnh, B chạy khi cache nóng.
- A có 240.000 hàng, B có 500.000 hàng sau INSERT.
- A dùng tenant 1, B dùng tenant 7.
- A dùng prepared generic plan, B dùng literal.
- A là 1 concurrent client, B là 16.
- A `ANALYZE` mới, B không.
- A chạy cùng autovacuum, B chạy khi host rảnh.
- A chỉ đọc, B bao gồm ghi.
- A commit, B rollback.
- B tích lũy nhiều index mới thay vì chỉ một candidate.

Những thay đổi này khiến ta không phân biệt được **hiệu ứng của index** với **hiệu ứng của điều kiện thử**.

## 41. Vì sao thử nhiều lần chưa đủ nếu dữ liệu không giống production?

Giả sử benchmark chạy 100 lượt và có độ lệch chuẩn rất thấp, nhưng:

- Chỉ có 10.000 hàng.
- Toàn bộ bảng nằm trong RAM.
- Không có writer.
- Không có tenant skew.
- Không có transaction dài.
- Không có index bloat.
- Query luôn trả đúng một hàng.

Kết quả có thể rất **ổn định** nhưng vẫn **không đại diện** cho production có hàng chục triệu đơn và hàng trăm worker đồng thời.

Hai thuộc tính khác nhau:

- **Repeatability:** chạy lại cùng điều kiện có kết quả tương tự.
- **Representativeness:** điều kiện mô phỏng phản ánh hệ thống cần tối ưu.

Một bài đo tốt cần cả hai. Đo chính xác một workload không liên quan cũng không giúp ra quyết định đúng.

## 42. Đo commit workload thay vì chỉ rollback

Trong các ví dụ lab, `BEGIN ... ROLLBACK` giúp học SQL mà không thay đổi kết quả seed lâu dài. Nhưng benchmark ghi production cần xem:

- Commit WAL và độ bền theo cấu hình.
- Bảng/index phát triển.
- Tỷ lệ dead tuple sau UPDATE/DELETE.
- Autovacuum.
- Lock contention.
- Thay đổi visibility map.
- Replica replay.

Một benchmark toàn rollback **không mô phỏng đầy đủ** các điều kiện này.

Nên dùng một **database clone/disposable**, nạp dữ liệu ban đầu giống nhau, chạy các giao dịch commit thật trên môi trường đó, rồi reset trước candidate kế tiếp.

**Không áp cách này trực tiếp lên database sản xuất.**

## 43. Gợi ý đo từ nhiều tầng

| Tầng | Công cụ | Thu được gì? |
| --- | --- | --- |
| Trình duyệt / client | Browser/app telemetry | Độ trễ người dùng thực sự |
| Gateway/API | Tracing, request histograms | RPS, p50/p95/p99, error/timeout |
| Connection pool | Pool metrics | Wait time, active/idle connections, queue |
| SQL tổng hợp | `pg_stat_statements` | Calls, tổng/mean exec time, blocks |
| Plan SQL | `EXPLAIN (ANALYZE, BUFFERS)` | Operator, rows, buffer accesses |
| PostgreSQL activity | `pg_stat_activity` | Wait events, transaction age, blockers |
| Bảng/index | `pg_stat_user_tables/indexes` | DML/HOT/scan statistics |
| WAL | `pg_stat_wal` theo version | WAL records/bytes cấp instance |
| Host | OS monitoring | CPU, memory, disk IOPS/latency |
| Replica | Replication monitoring | Lag, replay health |
| Load generation | `pgbench`/load testing | Offered load, TPS, client latency |

Không phải hệ thống nào cũng cần mọi công cụ. Hãy chọn nguồn số liệu để **trả lời một giả thuyết** chứ không mở hàng chục dashboard mà không biết cần xem gì.

## 44. Theo dõi transaction dài và idle in transaction

Một query đơn lẻ có thể chậm vì tác động của transaction khác:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 120) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Các transaction giữ snapshot hoặc khóa lâu có thể:

- Làm writer khác chờ.
- Giữ phiên bản hàng cũ, ảnh hưởng vacuum.
- Tăng bloat về lâu dài.
- Khiến một index-only scan có nhiều heap fetch hơn.

Nếu phát hiện `idle in transaction`, cần điều tra chủ sở hữu/caller và thời lượng hợp lý; không tự terminate PID trên production khi chưa hiểu hệ quả.

**Tối ưu query còn bao gồm quản lý transaction**, không chỉ thêm index.

## 45. Đo công việc định kỳ và đường đi ít gặp

Một workload representative phải bao phủ:

- Giờ cao điểm.
- Ban đêm chạy batch.
- Báo cáo đầu/cuối tháng.
- Các đợt import lớn.
- Cleanup/retention.
- Tình huống retry khi hệ thống ngoài gián đoạn.
- Truy vấn của tenant lớn nhất.
- Query vận hành cần thực thi nhanh khi có sự cố.

Một index có `idx_scan = 0` sau một ngày chưa chắc vô ích nếu nó giúp công việc cuối tháng hoặc bảo vệ UNIQUE/PRIMARY KEY. Không dùng một khoảng quan sát quá ngắn để quyết định xóa index.

## 46. Một mẫu báo cáo tối ưu truy vấn

Một báo cáo có khả năng bàn giao nên ghi:

| Nhóm | Thông tin |
| --- | --- |
| **Mục tiêu** | Endpoint/workflow, p95/p99, RPS/TPS, error/timeout |
| **Phạm vi** | Thời gian đo, peak/normal, tenant, dữ liệu |
| **Môi trường** | PostgreSQL version, CPU, RAM, disk, config, replica |
| **Query đại diện** | SQL templates, bind types, tham số và tỷ trọng |
| **Baseline** | Latency API/SQL, plans, buffers, locks, TPS |
| **Giả thuyết** | Vì sao thay đổi được kỳ vọng giúp |
| **Candidate** | DDL/query change cụ thể |
| **Cách đo** | Warm-up, số lượt, offered load, concurrency, reset |
| **Kết quả đọc** | p50/p95/p99, rows, buffers, sorts |
| **Kết quả ghi** | W1/W2 latency, throughput, WAL, HOT |
| **Trade-off** | Index size, vacuum, replica lag, cost |
| **Quyết định** | Giữ/sửa/bỏ, lý do và rủi ro |
| **Triển khai** | Kế hoạch DDL, giám sát, ngưỡng rollback |

Tính minh bạch quan trọng hơn việc có một biểu đồ đẹp. Nếu dữ liệu chưa đủ để kết luận, báo rõ **điều còn thiếu** và phép đo cần bổ sung.

## 47. Ví dụ quyết định có điều kiện

Giả sử sau benchmark đại diện, kết quả minh họa:

- Q1/Q2 giảm p95 rõ rệt và đạt SLO.
- Q3 không thay đổi đáng kể.
- Q4 không được cải thiện.
- W1 p95 tăng 10%.
- W2 TPS giảm 3%.
- Index thêm 80 MB.
- Replica lag không vượt ngưỡng.
- Mức tải 600 requests/s được đáp ứng với error rate trong SLO.

Nếu giới hạn chi phí ghi của hệ thống là **tăng p95 không quá 15%**, dung lượng còn dư và Q1/Q2 là critical path, index có thể đáng triển khai.

Nếu thực tế W1 là thao tác thanh toán đòi p99 cực thấp, việc tăng p95 10% vẫn chưa đủ chứng minh an toàn. Cần đo p99, lỗi, lock waits và tải cao nhất.

**Một quyết định tốt là quyết định theo mục tiêu và ràng buộc đã xác định trước**, không phải chọn phương án có số lượng metric “màu xanh” nhiều nhất.

## 48. Những sai lầm thường gặp

### 48.1. Tối ưu trước khi xác định SLO

Không biết mục tiêu nên dễ mất thời gian tối ưu query đã đủ nhanh.

### 48.2. Chỉ nhìn latency trung bình

Mean có thể che p99 rất xấu hoặc các request timeout.

### 48.3. Coi execution time của một SQL là latency API

Bỏ qua pool, network, application và nhiều SQL khác.

### 48.4. Chỉ đo ở tải thấp

Query 5 ms khi không có concurrent traffic không bảo đảm p95 tốt ở 600 RPS.

### 48.5. Không phân biệt RPS, QPS và TPS

Một request có thể chạy nhiều statement và transaction.

### 48.6. Đo query thuận lợi thay vì query đại diện

Chọn một tenant nhỏ và một key chắc chắn có index, bỏ qua tenant lớn và query aggregate.

### 48.7. Tạo seed chia đều khi production skew mạnh

Planner và workload thực tế có thể khác.

### 48.8. Không kiểm tra tỷ lệ ghi

Một index tốt cho Q1 có thể làm W1/W2 chậm.

### 48.9. Lấy p95 từng nhóm rồi tính trung bình có trọng số

Percentile của hỗn hợp không được tính bằng phép cộng các percentile.

### 48.10. Lấy p95 từ mean và stddev không có giả định

Latency thường có đuôi dài; phải đo phân bố thực.

### 48.11. Bỏ lỗi/timeout khỏi báo cáo

Chỉ tính request thành công có thể làm p95 nhìn đẹp khi hệ thống đang quá tải.

### 48.12. Không có baseline

Không thể biết index thay đổi điều gì nếu không có số liệu trước.

### 48.13. Chạy EXPLAIN một lần với cache khác nhau

Kết quả có thể bị thiên lệch bởi cache hoặc background work.

### 48.14. Nghĩ shared read nghĩa là physical disk read

Block được đọc vào shared buffers có thể đến từ OS cache.

### 48.15. Dùng literal query khi ứng dụng dùng prepared statements

Custom/generic plan và bind types có thể khác.

### 48.16. Không xem lock waits

Query chậm vì bị chặn không nhất thiết cần index.

### 48.17. Tăng work_mem toàn server để giải quyết một sort

Có thể làm nhiều query đồng thời tiêu thụ bộ nhớ lớn.

### 48.18. Thêm nhiều index cùng lúc

Không thể tách ảnh hưởng riêng từng candidate.

### 48.19. Chỉ benchmark với transaction rollback

Không mô phỏng đầy đủ commit, WAL và vòng đời bloat/vacuum.

### 48.20. Dùng `EXPLAIN ANALYZE UPDATE` trên production như dry-run

ANALYZE thực thi DML thật và có thể tạo tác động.

### 48.21. Chỉ benchmark throughput, bỏ p95/p99 và error rate

Tăng TPS nhưng latency đuôi và retry xấu hơn có thể làm trải nghiệm giảm.

### 48.22. Ghi `idx_scan=0` rồi drop index

Quên constraint, query hiếm và thời gian quan sát.

### 48.23. Không ghi phiên bản PostgreSQL và config

Kết quả khó tái lập, khác biệt planner/feature có thể quan trọng.

### 48.24. Không kiểm tra tính đúng nghiệp vụ

Benchmark nhanh vì mọi INSERT bị `ON CONFLICT DO NOTHING` không phải chiến thắng.

### 48.25. Không đo sau triển khai

Staging có thể khác production về cache, data distribution, peak load và replication.

### 48.26. Không dừng khi mục tiêu đã đạt

Tối ưu thêm có thể làm tăng rủi ro/chi phí mà giá trị mang lại nhỏ.

## 49. Bài tập thực hành có đáp án

Dùng schema `perf_goal_lab` từ mục 13. Các câu có tác động DML được bọc `BEGIN ... ROLLBACK` nếu chỉ minh họa. Những câu tạo index dùng trong database lab và cần cân nhắc index đã có để tránh tạo trùng.

### Bài 1. Phân biệt mục tiêu mơ hồ và có thể đo

**Câu hỏi:** “Database phải nhanh hơn” thiếu những gì?

**Đáp án:** Thiếu endpoint/workload, điểm đo latency, p95/p99, throughput và mức đồng thời, điều kiện tải, cửa sổ đo, tỷ lệ lỗi và giới hạn tác động lên ghi/storage.

### Bài 2. RPS và QPS

Một API nhận 500 request/s, mỗi request thực thi trung bình 4 SQL.

**Đáp án:** Nếu tất cả request hoàn thành và trung bình đúng 4 statement được thực thi, khoảng **2.000 SQL executions/s**. Không suy ra TPS khi chưa biết transaction boundary.

### Bài 3. Little's Law

Một hệ thống ổn định hoàn tất 200 request/s, mean response time 250 ms.

**Đáp án:** Số request trung bình trong ranh giới đo khoảng `200 × 0.25 = 50`. Không suy ra cần đúng 50 DB connections.

### Bài 4. Phân biệt mean và p99

**Câu hỏi:** Vì sao mean 20 ms không đảm bảo mọi người dùng dưới 100 ms?

**Đáp án:** Một số ít request có thể mất vài giây nhưng mean vẫn thấp. Cần xem percentile, errors và timeout.

### Bài 5. Từ SLO API tới mục tiêu SQL

API p95 dưới 150 ms, SQL chỉ chiếm 8 ms trong một request 120 ms.

**Đáp án:** Giảm SQL từ 8 ms xuống 2 ms có thể không giải quyết phần pool/network chiếm phần lớn; cần phân bổ thời gian để chọn đúng bottleneck.

### Bài 6. Ghi baseline Q1

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT order_id, created_at, total_amount
FROM perf_goal_lab.orders
WHERE tenant_id = 7 AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

**Đáp án:** Lưu plan, actual/estimated rows, buffers, sort và execution time trước khi tạo index; không tự điền thời gian chưa đo.

### Bài 7. Tenant skew

**Câu hỏi:** Vì sao đo chỉ tenant 7 là chưa đủ?

**Đáp án:** Tenant 1 có khoảng 60% số đơn, nên query cùng template có số hàng ứng viên và selectivity khác nhiều. Phải đo cả tenant lớn.

### Bài 8. Đề xuất index cho top-N

~~~sql
CREATE INDEX idx_exercise_latest
ON perf_goal_lab.orders(
    tenant_id, status, created_at DESC, order_id DESC
);
~~~

**Đáp án:** Phù hợp điều kiện equality theo tenant/status và thứ tự top-N. Nếu đã có `idx_perf_orders_tenant_status_latest` tương đương, không nên giữ cả hai index ngoài mục đích thử nghiệm.

### Bài 9. Vì sao không kết luận chỉ từ Index Scan?

**Đáp án:** Cần xem buffers, rows, sorts, latency dưới tải, write overhead và storage; một plan có Index Scan vẫn có thể kém hiệu quả tổng thể.

### Bài 10. Query nào cần xử lý nhiều hàng?

So Q1 `LIMIT 20` với Q4 tổng hợp doanh thu trong tháng.

**Đáp án:** Q4 có thể phải đọc và nhóm nhiều hàng; index top-N không tự làm nó nhanh, còn Seq Scan có thể là plan hợp lý.

### Bài 11. Tính phần trăm giảm latency

Q1 p95 từ 120 ms còn 30 ms.

**Đáp án:** Giảm `(120-30)/120 = 75%`.

### Bài 12. Tính throughput gain

Write TPS từ 2.000 lên 2.200.

**Đáp án:** Tăng `(2200-2000)/2000 = 10%` nếu số đo cùng workload và điều kiện.

### Bài 13. Tại sao không cộng p95 theo trọng số?

**Đáp án:** Percentile của hỗn hợp phụ thuộc toàn bộ phân phối các request, không phải tuyến tính theo percentile từng nhóm. Phải tính từ dữ liệu/histogram tổng hợp đúng.

### Bài 14. Cách phát hiện query thường xuyên

**Đáp án:** Xem `pg_stat_statements.calls`, `total_exec_time` và telemetry ứng dụng; query trung bình rất ngắn nhưng gọi hàng triệu lần vẫn có thể đáng ưu tiên.

### Bài 15. Thử query tham số hóa

~~~sql
PREPARE p(integer, text) AS
SELECT order_id
FROM perf_goal_lab.orders
WHERE tenant_id=$1 AND status=$2
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

EXPLAIN EXECUTE p(1, 'pending');
EXPLAIN EXECUTE p(7, 'pending');
DEALLOCATE p;
~~~

**Đáp án:** Cho phép xem plan trong hình thức gần với prepared statements của ứng dụng; vẫn cần kiểm tra custom/generic plan và protocol thật.

### Bài 16. Phân biệt lock wait và CPU work

**Đáp án:** `pg_stat_activity.wait_event_type='Lock'`, `pg_blocking_pids` và transaction age giúp nhận diện chờ khóa; không tự kết luận thiếu index.

### Bài 17. Vì sao EXPLAIN ANALYZE UPDATE cần rollback trong lab?

**Đáp án:** Vì `ANALYZE` thực sự thực thi UPDATE. Rollback giúp tránh lưu thay đổi nghiệp vụ nhưng vẫn có chi phí tuple/WAL; không phải benchmark commit thực.

### Bài 18. Giải thích `shared hit/read`

**Đáp án:** `hit` là block đã có trong shared buffers; `read` là block đưa vào shared buffers, có thể từ OS page cache chứ không nhất thiết physical disk.

### Bài 19. Đo read/write trade-off

Một index giảm Q1 p95 80% nhưng làm UPDATE p95 tăng 25%.

**Đáp án:** Chưa thể chọn chỉ theo Q1. So với SLO của UPDATE, tỷ trọng Q1/W1, write TPS, WAL, storage, tail latency và mục tiêu kinh doanh.

### Bài 20. Khi nào cần nhiều phiên benchmark?

**Đáp án:** Khi đánh giá p95/p99, saturation, cache, checkpoint/autovacuum hoặc workload thay đổi theo thời gian. Một lần chạy vài giây thường không đại diện.

### Bài 21. Vì sao phải đo API thay vì chỉ SQL?

**Đáp án:** SQL chỉ là một phần của request; network, pool, serialization, N+1 và service calls có thể chi phối latency đầu-cuối.

### Bài 22. Query trả 0 hàng có phải benchmark tốt?

**Đáp án:** Chỉ nếu đó là tình huống thật có tần suất tương ứng. Nếu workload thường trả hàng nhưng benchmark luôn miss, kết quả quá lạc quan.

### Bài 23. Tại sao 1.000 RPS toàn lỗi không phải thành tích?

**Đáp án:** Throughput tổng không đo thành công nghiệp vụ. Cần goodput, tỷ lệ lỗi, timeout và số transaction thực sự commit.

### Bài 24. Khi nào dừng tối ưu?

**Đáp án:** Khi SLO/throughput đạt mục tiêu dưới tải đại diện, write/storage cost trong giới hạn và cải thiện thêm không còn đáng rủi ro/chi phí.

## 50. Checklist bắt đầu một nhiệm vụ tối ưu PostgreSQL

- [ ] Xác định endpoint/workflow hoặc truy vấn cần cải thiện.
- [ ] Ghi rõ điểm đo latency: client, API, transaction hay SQL.
- [ ] Đặt SLO p95/p99 và điều kiện tải/cửa sổ đo.
- [ ] Định nghĩa throughput (RPS/QPS/TPS) và goodput.
- [ ] Ghi error rate, timeout và retry policy.
- [ ] Thu thập query templates từ telemetry.
- [ ] Chọn các nhóm point lookup, top-N, JOIN, aggregate, INSERT và UPDATE.
- [ ] Xác định tenant skew, trạng thái phổ biến/hiếm và kích thước kết quả.
- [ ] Kiểm tra SQL/bind types/prepared plans giống ứng dụng.
- [ ] Chuẩn bị dữ liệu đại diện, không dùng bảng quá nhỏ.
- [ ] Đo baseline trước khi tạo index hoặc sửa SQL.
- [ ] Dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường an toàn.
- [ ] Xem estimated/actual rows, Index Cond, Filter, Sort, Heap Fetches.
- [ ] Kiểm tra lock waits, pool wait, CPU và I/O.
- [ ] Chỉ thay đổi một yếu tố chính trong từng lượt A/B.
- [ ] Warm-up, số lượt đo và concurrency tương đương.
- [ ] Đo p50/p95/p99, TPS và errors ở mức offered load mục tiêu.
- [ ] Đo thêm write latency, WAL, HOT, index size và replica lag nếu có.
- [ ] Không làm benchmark gây tải hoặc DML phá hoại trên production.
- [ ] Ghi rõ số liệu giả định so với số liệu đã đo thực.
- [ ] Có kế hoạch rollback/migration và giám sát sau rollout.
- [ ] Chỉ kết luận khi lợi ích vượt trade-off và phù hợp SLO.

## 51. Tài liệu PostgreSQL chính thức

Khi áp dụng vào hệ thống thật, hãy đối chiếu **đúng major version PostgreSQL và pgbench** đang chạy:

- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — cách đọc plan, row estimates, scans và costs.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — `ANALYZE`, `BUFFERS`, `WAL` và caveat DML.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html) — histograms, most-common values, extended stats.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — thống kê query calls và execution time.
- [pgbench](https://www.postgresql.org/docs/current/pgbench.html) — custom scripts, weights, concurrency, rate limiting và logging.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_wal`, `pg_stat_progress_create_index`.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html) — vai trò/chi phí của index.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — B-tree, GIN, GiST, BRIN và kiểu truy cập.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) — composite key order và tối ưu điều kiện.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, autovacuum và ảnh hưởng tới kế hoạch.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — MVCC, snapshot và concurrency.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock waits, deadlocks và transaction coordination.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html) — generic/custom plans.

`/current/` dẫn tới tài liệu phiên bản hiện hành trên website PostgreSQL. Với server hoặc công cụ chạy phiên bản khác, tra tài liệu của version tương ứng trước khi sử dụng tùy chọn đo mới.

## 52. Tổng kết

**Tối ưu truy vấn PostgreSQL phải bắt đầu từ mục tiêu và khối lượng công việc, không bắt đầu từ index hay SQL syntax.**

Những nguyên tắc quan trọng nhất:

1. **Định nghĩa latency theo điểm đo và percentile.** Mean hoặc thời gian của một `EXPLAIN` không đại diện cho p95/p99 đầu-cuối.
2. **Đặt throughput dưới điều kiện tải cụ thể.** QPS, TPS, RPS, goodput và concurrency không phải một con số duy nhất.
3. **Chọn các truy vấn đại diện cho workload thực.** Cần SQL templates, tham số skew, tập dữ liệu đúng phân bố, JOIN/aggregate và cả thao tác ghi.
4. **Bắt đầu bằng baseline.** Nếu chưa có số liệu trước thay đổi, không thể chứng minh hiệu quả của index mới.
5. **Dùng EXPLAIN, thống kê và load test như các bằng chứng bổ sung cho nhau.** Mỗi công cụ chỉ quan sát một phần hệ thống.
6. **Đo trade-off đọc–ghi dưới cùng offered load.** Một index giúp top-N nhưng làm W1/W2 tăng WAL/latency có thể đáng hoặc không đáng, tùy SLO.
7. **Quyết định và triển khai có kiểm soát.** Ghi cách thử, giữ khả năng rollback và đo lại ở production theo chính những SLO đã xác định.

Câu hỏi kết thúc một lượt tối ưu không phải “PostgreSQL đã sử dụng index chưa?”, mà là **“Hệ thống có phục vụ đúng workload với độ trễ, thông lượng, tỷ lệ thành công và chi phí vận hành đã cam kết hay chưa?”**. Khi trả lời được câu này bằng dữ liệu đo, việc tối ưu mới thực sự có ý nghĩa.
