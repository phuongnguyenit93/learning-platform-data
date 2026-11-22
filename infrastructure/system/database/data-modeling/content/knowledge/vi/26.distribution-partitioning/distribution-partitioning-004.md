# Khóa nóng, khách hàng quá lớn và nguy cơ phân bố lệch

Chia dữ liệu thành nhiều **phân vùng (partition)** hoặc **shard** không bảo đảm hệ thống tự động cân bằng. Nếu một khách hàng tạo phần lớn giao dịch, hoặc hàng nghìn yêu cầu đồng thời cùng sửa một bản ghi, một phân vùng có thể quá tải trong khi những phân vùng khác vẫn nhàn rỗi. Đây là vấn đề **khóa nóng (hot key)**, **khách hàng quá lớn (whale tenant)** và **phân bố lệch (data/workload skew)**.

Một ví dụ dễ gặp trong nền tảng SaaS đa khách hàng: hệ thống đặt **tenant_id** làm khóa phân phối để mọi dữ liệu của một khách hàng nằm gần nhau. Cách này giúp truy vấn và giao dịch trong một tenant đơn giản. Nhưng khi một tenant chiếm 40% lưu lượng, **HASH(tenant_id)** vẫn đưa toàn bộ lưu lượng tenant ấy về cùng một nơi. Số shard tăng từ 8 lên 32 chưa chắc giải quyết được nút thắt nếu cả 40% vẫn nằm trên một shard.

Bài thuộc chương **Phân tán và phân vùng** của mô-đun **DATABASE_DATA_MODELING**. Mục tiêu là kết nối yêu cầu nghiệp vụ với grain, khóa, chỉ mục, lược đồ vật lý và cách phân phối; nhận diện các loại điểm nóng; đo độ lệch; chọn giữa đổi khóa phân phối, chia bucket, tách tenant lớn, tối ưu truy cập hoặc định tuyến riêng. Những lựa chọn này phải được kiểm chứng bằng **tính đúng đắn của dữ liệu** và **tải thực tế**, không chỉ bằng số lượng partition tạo ra.

## 1. Các khái niệm cần phân biệt

### 1.1. Partition, shard và partition key

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Partition** | Một phần của bảng hoặc tập dữ liệu theo quy tắc phân vùng | Các partition PostgreSQL theo tháng hoặc theo hash |
| **Sharding** | Phân phối dữ liệu qua nhiều đơn vị lưu trữ/nút hoặc nhóm tài nguyên có thể mở rộng độc lập | Đơn hàng tenant A ở shard 1, tenant B ở shard 2 |
| **Partition key / shard key** | Thuộc tính dùng xác định nơi dữ liệu được đặt | tenant_id, order_id, occurred_at hoặc tổ hợp khóa |
| **Logical shard** | Đơn vị định tuyến logic, có thể ánh xạ sang máy vật lý | 64 bucket logic trên 8 cụm lưu trữ |
| **Physical shard/node** | Nơi tài nguyên CPU, RAM, I/O, network thực sự bị tiêu thụ | Một máy chủ lưu nhiều bucket logic |
| **Rebalancing** | Di chuyển hoặc gán lại dữ liệu/tải giữa các đơn vị | Đưa bucket của tenant lớn sang nhóm máy khác |

**Cảnh báo quan trọng:** tạo 8 partition trong **một** PostgreSQL instance **không tự tạo 8 máy chủ** hoặc tăng tám lần năng lực phần cứng. Partitioning cục bộ giúp quản lý dữ liệu và có thể cải thiện một số kế hoạch truy vấn; sharding thực sự cần cơ chế định tuyến và phân phối tài nguyên vật lý.

### 1.2. Hot key, hot partition và whale tenant

- **Hot key:** một khóa hoặc bản ghi nhận số lượng đọc/ghi quá lớn. Ví dụ mọi giao dịch của tenant A cùng cập nhật hàng **tenant_usage(tenant_id = A)**.
- **Hot partition:** một phân vùng/shard chịu lượng truy cập, dung lượng, CPU hoặc I/O cao hơn nhiều so với các phân vùng khác. Nó có thể bị nóng vì **một** khóa lớn hoặc vì **nhiều** khóa tình cờ được phân phối chung.
- **Whale tenant:** một khách hàng có lưu lượng hoặc kích thước dữ liệu vượt xa khách hàng thông thường. “Quá lớn” là tương đối với giới hạn hệ thống: lớn về dung lượng, QPS, số kết nối hoặc truy vấn nặng đều có thể gây vấn đề.
- **Data skew:** phân bố **số hàng hoặc dung lượng lưu trữ** không đều.
- **Traffic/workload skew:** phân bố **yêu cầu, CPU, IOPS, thời gian khóa hoặc băng thông** không đều.

Một shard có 1 TB dữ liệu cũ ít được đọc có thể không nóng, trong khi shard có 20 GB dữ liệu hiện hành nhưng nhận 50.000 cập nhật/giây lại bị nghẽn. Vì vậy **data skew và workload skew không phải một đại lượng**.

### 1.3. Khóa nóng không nhất thiết là shard nóng

Xét:

~~~sql
UPDATE tenant_usage
SET events_processed = events_processed + 1
WHERE tenant_id = 42;
~~~

Nếu hàng **tenant_id = 42** bị nhiều transaction cập nhật đồng thời, những transaction cần chờ khóa hàng hoặc cạnh tranh ghi. Ngay cả khi bảng trải trên nhiều shard, **một hàng duy nhất vẫn là điểm tuần tự hóa**. Tách partition theo ngày của bảng sự kiện không sửa được nút thắt cập nhật hàng tenant_usage.

Để xử lý đúng, phải xác định điểm nóng nằm ở **bản ghi**, **khóa truy vấn**, **index page**, **partition** hay **máy vật lý**; mỗi loại có phương án khác nhau.

## 2. Ví dụ định lượng: 8 shard và một khách hàng chiếm 40%

Giả sử một nền tảng có **100 tenant** và nhận **1.000.000 sự kiện/ngày**:

- Tenant **W** phát sinh **400.000 sự kiện/ngày**.
- **99 tenant còn lại** tạo tổng cộng **600.000 sự kiện/ngày**, trung bình khoảng **6.061 sự kiện/ngày mỗi tenant**.
- Tất cả sự kiện được gán tới **8 shard** theo **HASH(tenant_id)**.

Mức lý tưởng nếu cân bằng hoàn hảo:

\[
\text{Tải trung bình mỗi shard}
= \frac{1.000.000}{8}
= 125.000\ \text{sự kiện/ngày}.
\]

Nhưng toàn bộ 400.000 sự kiện của W ở **một shard**. Do đó:

\[
\text{Tải shard chứa W} \ge 400.000
\quad \Rightarrow \quad
\frac{\text{tải shard nóng}}{\text{tải trung bình}} \ge 3{,}2.
\]

Tỷ lệ **3,2 lần** chỉ là **giới hạn dưới**; các tenant khác cùng hash vào shard này còn làm nó lớn hơn. Thêm shard có thể giảm khả năng tenant nhỏ cùng va chạm, nhưng **không phân tách lưu lượng của W** khi chỉ hash tenant_id.

### 2.1. Dữ liệu không đồng nghĩa với năng lực xử lý

Nếu 1.000.000 sự kiện/ngày được phát đều, tổng trung bình chỉ khoảng 11,6 sự kiện/giây, nhưng thực tế có thể dồn 70% vào giờ cao điểm. Tenant W còn có thể chạy truy vấn tổng hợp nặng trong cùng khoảng thời gian. Do đó số **hàng/ngày** không trực tiếp cho biết **CPU, I/O hoặc độ trễ**.

Mô hình tải phải xét:

~~~text
Tải ghi ≈ số thao tác ghi × chi phí mỗi thao tác
Tải đọc ≈ số truy vấn × số hàng quét × chi phí truy vấn
Tải khóa ≈ mức độ tranh chấp cùng hàng / cùng tài nguyên
Tải lưu trữ ≈ dung lượng dữ liệu + chỉ mục + phiên bản/nhật ký
~~~

Đây là cách suy luận về nguồn gốc tải, **không phải công thức ước lượng công suất chính xác**. Để ra quyết định, phải đo workload và kế hoạch truy vấn thực.

### 2.2. Minh họa phân bố bằng biểu đồ

~~~mermaid
flowchart LR
    EVENTS["1.000.000 sự kiện/ngày"]
    ROUTER["Định tuyến HASH(tenant_id)"]
    WHALE["Tenant W: 400.000/ngày"]
    SMALL["99 tenant: 600.000/ngày"]
    HOT["Shard chứa W: ít nhất 400.000/ngày"]
    REST["7 shard còn lại và các tenant khác"]
    EVENTS --> ROUTER
    WHALE --> ROUTER
    SMALL --> ROUTER
    ROUTER --> HOT
    ROUTER --> REST
~~~

Sơ đồ mô tả **nguyên lý phân phối**, không phải kết quả dự báo chính xác của một hàm hash cụ thể.

## 3. Các nguyên nhân gây lệch phân bố

### 3.1. Khóa có cardinality thấp

Nếu chia theo **status** chỉ gồm PENDING, PAID, CANCELLED, dữ liệu không thể chia tự nhiên thành hàng chục phần độc lập. Trong thực tế, status còn có thể lệch mạnh về một giá trị. Chọn khóa dựa trên trường ít giá trị chỉ vì dễ đọc thường tạo điểm nóng.

### 3.2. Phân vùng theo thời gian và ghi tập trung vào thời điểm hiện tại

Với partition tháng:

~~~text
orders_2026_09
orders_2026_10
orders_2026_11  <- hầu hết ghi mới trong tháng 11
~~~

Partition theo thời gian thuận tiện cho truy vấn theo kỳ và xóa dữ liệu hết hạn, nhưng **mọi ghi hiện tại có thể tập trung vào partition tháng này**. Nếu partition nằm trên cùng máy, vấn đề còn có thể là tài nguyên chung hoặc trang chỉ mục nóng, không chỉ số lượng hàng trong partition.

Một chỉ mục B-tree theo khóa tăng đơn điệu như **created_at** hoặc ID cấp tuần tự cũng có thể tập trung thao tác ghi vào một vùng chỉ mục nhất định. Không thể kết luận mọi khóa tăng đều gây nghẽn; tác động phụ thuộc engine, cấu trúc index, tốc độ ghi và cơ chế đồng thời.

### 3.3. Một tenant quá lớn

Khi khóa là **tenant_id**, hệ thống có thể tận dụng locality cho các truy vấn:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

Nhưng mọi đơn, sự kiện hoặc yêu cầu của tenant 42 có thể cùng đến một shard. Một khách hàng ký hợp đồng lớn, thực hiện nhập dữ liệu hàng loạt hoặc chạy báo cáo liên tục có thể ảnh hưởng các tenant nhỏ cùng shard: **noisy neighbor**.

### 3.4. Một khóa được đọc cực nhiều

Một sản phẩm nổi tiếng hoặc một livestream có cùng **product_id** có thể nhận hàng chục nghìn lượt đọc/giây. Hash đều các product_id khác không phân chia số yêu cầu dành cho **một product_id cụ thể**.

Nếu dữ liệu có thể cache hoặc nhân bản đọc, **cache/read replica** có thể xử lý hiệu quả hơn việc thay đổi mô hình khóa. Phải xét dữ liệu thay đổi nhanh hay chậm và yêu cầu nhất quán của màn hình.

### 3.5. Điểm nóng do cập nhật cùng bản ghi tổng

Ví dụ mỗi sự kiện tăng một counter:

~~~text
tenant_usage(tenant_id, total_events)
~~~

Hàng **tenant_id = 42** bị cập nhật liên tục, bất kể sự kiện đã được chia đều vào các partition của bảng sự kiện. Tắc nghẽn này là **write contention theo hàng**, cần thiết kế counter hoặc cơ chế tổng hợp khác.

### 3.6. Hash collision và lệch ngay cả khi không có whale

Hàm hash phân phối các **giá trị khóa khác nhau** lên số shard hữu hạn; nhiều khóa vẫn có thể cùng vào một shard. Khi số khóa ít, chênh lệch giữa shard là chuyện bình thường. Hash tốt giúp giảm lệch kỳ vọng với nhiều khóa có tải tương tự, **không hứa** cân bằng khi trọng số của các khóa rất khác nhau.

## 4. Những câu hỏi phải trả lời trước khi chọn shard key

Một khóa phân phối tốt không chỉ có số giá trị riêng lớn. Nó phải hỗ trợ **truy vấn và giao dịch quan trọng nhất**.

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Một hàng biểu diễn thực thể/sự kiện gì (*grain*)? | Không nhầm một tenant với một đơn, một event hay một dòng đơn |
| Tải ghi chủ yếu tạo bản ghi mới hay cập nhật cùng bản ghi? | Chia event mới không tự giải quyết counter nóng |
| Những truy vấn chủ yếu lọc theo cột nào? | Chọn khóa không xuất hiện trong truy vấn có thể gây scatter-gather |
| Có cần giao dịch nhiều hàng trong cùng tenant? | Đặt các hàng gần nhau có thể giảm giao dịch phân tán |
| Khóa có nhiều giá trị và phân bố tải có đều không? | Tránh cardinality thấp và whale keys |
| Tenant nào đang có dữ liệu hoặc QPS vượt trội? | Quyết định tenant phải chia nhỏ hoặc cô lập |
| Có yêu cầu duy nhất toàn hệ thống không? | UNIQUE/FK xuyên shard thường khó hơn |
| Có dữ liệu cần giữ tại vùng địa lý cụ thể không? | Residency và compliance có thể giới hạn nơi đặt shard |
| Dữ liệu thay đổi thời gian và cần retention thế nào? | Có thể cần phân vùng theo thời gian độc lập với shard key |
| Phương án cân bằng lại khi tenant tăng đột biến là gì? | Khóa khó thay có thể dẫn đến migration phức tạp |

**Phân vùng theo thời gian, hash tenant và phân phối tenant lên node là ba quyết định có thể kết hợp**, không phải những lựa chọn hoàn toàn thay thế nhau.

## 5. Phát hiện lệch phân bố bằng số liệu, không đoán từ sơ đồ

Đánh giá phải kết hợp **phân bố hàng/dung lượng** với **phân bố truy cập và độ trễ theo thời gian**. Chỉ nhìn bảng nào lớn nhất chưa đủ để phát hiện nút thắt.

### 5.1. Những chỉ số nên thu thập

| Chỉ số | Chiều phân tích | Tín hiệu rủi ro |
| --- | --- | --- |
| Số hàng, byte dữ liệu, byte chỉ mục | Theo tenant, partition, node | Một tenant hoặc partition lớn vượt trội |
| Writes/second và reads/second | Theo shard, tenant, API, khung thời gian | Một shard nhận phần lớn tải ở giờ cao điểm |
| CPU, IOPS, băng thông, hàng đợi | Theo node vật lý | Node nóng trong khi node khác rảnh |
| Thời gian chờ khóa, deadlock, retry | Theo bảng, khóa truy vấn, thao tác | Cùng hàng counter hoặc index bị tranh chấp |
| p50/p95/p99 latency | Theo API và tenant, không chỉ toàn hệ thống | Một tenant có đuôi độ trễ cao hoặc timeout |
| Query rows scanned/returned | Theo kiểu truy vấn | Truy vấn tenant lớn quét quá nhiều hàng |
| Cache hit/miss, replication lag | Theo partition/replica | Cache miss storm hoặc replica đọc trễ |
| Rebalance backlog, storage growth | Theo shard | Shard vượt ngưỡng dung lượng, việc di chuyển không theo kịp |

**Số liệu bình quân toàn hệ thống có thể che vấn đề.** Nếu 99 tenant nhỏ chạy nhanh và một tenant lớn gặp timeout, p95 toàn hệ thống có thể vẫn đẹp. Cần dashboard hoặc tracing theo tenant, shard, khung giờ và kiểu thao tác, nhưng phải tránh đưa PII hoặc mã nhạy cảm ra hệ giám sát không được phân quyền.

### 5.2. Phân tích dữ liệu theo tenant

Giả sử có bảng sự kiện quan hệ:

~~~text
tenant_events(
    tenant_id,
    event_id,
    order_id,
    occurred_at,
    payload
)
~~~

Đếm số hàng và ngày gần nhất cho từng tenant:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS event_rows,
    MIN(occurred_at) AS first_event_at,
    MAX(occurred_at) AS last_event_at
FROM tenant_events
GROUP BY tenant_id
ORDER BY event_rows DESC
LIMIT 20;
~~~

Để xem khách hàng nào chiếm nhiều ghi mới trong một cửa sổ thời gian:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS events_last_day
FROM tenant_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-21 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-22 00:00:00+07'
GROUP BY tenant_id
ORDER BY events_last_day DESC;
~~~

Khoảng ngày cố định ở đây **chỉ để minh họa cửa sổ một ngày theo múi giờ +07**, không phải truy vấn “hôm nay” tự động. Khi làm báo cáo liên tục, dùng tham số thời gian bắt đầu/kết thúc với múi giờ đã thống nhất.

Tính tỷ trọng của từng tenant trong phạm vi một cửa sổ:

~~~sql
WITH per_tenant AS (
    SELECT tenant_id, COUNT(*) AS event_count
    FROM tenant_events
    GROUP BY tenant_id
)
SELECT
    tenant_id,
    event_count,
    ROUND(
        100.0 * event_count / NULLIF(SUM(event_count) OVER (), 0),
        2
    ) AS pct_of_total
FROM per_tenant
ORDER BY event_count DESC
LIMIT 20;
~~~

Điều kiện **NULLIF(..., 0)** bảo vệ phép chia nếu toàn bộ tập rỗng; trong tập rỗng, truy vấn không trả tenant nào. Thống kê này đo **tỷ lệ số bản ghi**, không tự đo QPS tức thời, tải CPU hoặc mức tranh chấp khóa.

### 5.3. Kiểm tra phân bố trên partition PostgreSQL

Với bảng PostgreSQL được phân vùng và truy vấn từ bảng cha:

~~~sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS event_rows
FROM tenant_events
GROUP BY tableoid
ORDER BY event_rows DESC;
~~~

**tableoid** chỉ ra bảng vật lý thực sự chứa hàng. Nếu bảng không partition thì kết quả chỉ có một bảng. Truy vấn này đếm hàng nên **có thể tốn tài nguyên trên bảng rất lớn**; trong vận hành có thể lấy thống kê/catalog xấp xỉ, telemetry hoặc thực hiện ngoài giờ cao điểm tùy nhu cầu.

Hệ số lệch số hàng giữa partition lớn nhất và mức trung bình của các partition có hàng:

~~~sql
WITH partition_rows AS (
    SELECT tableoid, COUNT(*)::numeric AS row_count
    FROM tenant_events
    GROUP BY tableoid
)
SELECT
    MAX(row_count) AS max_rows,
    ROUND(AVG(row_count), 1) AS avg_rows_nonempty,
    ROUND(MAX(row_count) / NULLIF(AVG(row_count), 0), 2)
        AS max_to_avg_nonempty
FROM partition_rows;
~~~

**Giới hạn:** truy vấn này **không tính partition rỗng** vào trung bình; muốn so toàn bộ số partition cấu hình phải lấy danh sách đầy đủ từ metadata rồi LEFT JOIN thống kê. Nó cũng đo **row count**, không đo byte, QPS hay năng lực node.

### 5.4. Dấu hiệu điểm nóng không thấy trong COUNT(*)

Một bảng **tenant_usage** có đúng một hàng cho mỗi tenant vẫn có thể nóng nghiêm trọng nếu tất cả luồng cùng cập nhật một hàng. Khi đó cần xem:

- Transaction chờ hàng nào, thời gian chờ khóa và retry.
- Số lần UPDATE trên khóa ấy trong cửa sổ ngắn.
- p95/p99 latency riêng của thao tác UPDATE counter.
- Thời gian WAL/flush, CPU và tài nguyên chung của node.

**Không thể suy hot key từ số hàng theo tenant mà thôi.** Một tenant có hàng trăm triệu sự kiện nhưng không có cập nhật counter nóng; tenant khác có 100 hàng nhưng nhận hàng nghìn UPDATE/giây vào một bản ghi có thể là điểm nghẽn chính.

## 6. Thử partition theo HASH(tenant_id) bằng PostgreSQL

Ví dụ dưới đây minh họa **partitioning cục bộ** và tính chất cố hữu của khóa tenant. Nó **không tạo một hệ thống sharding phân tán thực sự**.

### 6.1. Tạo bảng, khóa và 8 partition

~~~sql
CREATE TABLE tenant_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_events_p0 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 0);
CREATE TABLE tenant_events_p1 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 1);
CREATE TABLE tenant_events_p2 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 2);
CREATE TABLE tenant_events_p3 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 3);
CREATE TABLE tenant_events_p4 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 4);
CREATE TABLE tenant_events_p5 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 5);
CREATE TABLE tenant_events_p6 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 6);
CREATE TABLE tenant_events_p7 PARTITION OF tenant_events
    FOR VALUES WITH (MODULUS 8, REMAINDER 7);

CREATE INDEX idx_tenant_events_tenant_time
ON tenant_events (tenant_id, occurred_at DESC);
~~~

Trong PostgreSQL, **PRIMARY KEY/UNIQUE khai báo trên bảng partitioned phải tuân thủ các yêu cầu về cột partition key**; ví dụ khóa chính **(tenant_id, event_id)** có chứa tenant_id. Nếu yêu cầu **event_id duy nhất toàn hệ thống mà không xét tenant_id**, khai báo khóa ghép này **không tự bảo vệ** tính duy nhất toàn cục của event_id. Cần thiết kế ID và cơ chế kiểm soát đúng với yêu cầu.

Chỉ mục được khai báo trên bảng cha partitioned sẽ được quản lý theo các partition liên quan, không phải một “chỉ mục toàn cục” độc lập bảo đảm uniqueness xuyên mọi partition.

### 6.2. Nạp dữ liệu tổng hợp có lệch rõ rệt

Để đọc được kết quả nhanh hơn một bảng hàng triệu hàng, ta nạp **10.000 sự kiện**:

- Tenant 42 chiếm **4.000 sự kiện (40%)**.
- 99 tenant có mã 100–198 chia nhau **6.000 sự kiện**.

~~~sql
INSERT INTO tenant_events
    (tenant_id, event_id, order_id, occurred_at, payload)
SELECT
    CASE
        WHEN i <= 4000 THEN 42
        ELSE 100 + ((i - 4001) % 99)
    END AS tenant_id,
    i::BIGINT AS event_id,
    ((i - 1) / 5 + 1)::BIGINT AS order_id,
    TIMESTAMPTZ '2026-11-21 00:00:00+07'
        + (i * INTERVAL '1 second') AS occurred_at,
    jsonb_build_object('event_type', 'ORDER_EVENT') AS payload
FROM generate_series(1, 10000) AS g(i);
~~~

Kiểm tra:

~~~sql
SELECT
    COUNT(*) AS all_events,
    COUNT(*) FILTER (WHERE tenant_id = 42) AS whale_events
FROM tenant_events;
-- all_events = 10000; whale_events = 4000.
~~~

Trong ví dụ này, các tenant khác mỗi tenant có khoảng 60–61 sự kiện. Dù hàm hash cụ thể gán tenant 42 tới partition nào, **4.000 hàng của tenant 42 phải nằm chung một partition** vì partition key chỉ là tenant_id.

Do đó mức trung bình của 8 partition là **1.250 hàng**, partition của whale có **ít nhất 4.000 hàng**, tức tối thiểu **3,2 lần trung bình**. Sau đó chạy các truy vấn ở mục 5 để xem phân bố **thực tế** trên từng partition.

### 6.3. Partition pruning có lợi nhưng không cứu whale

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, order_id, occurred_at
FROM tenant_events
WHERE tenant_id = 42
ORDER BY occurred_at DESC
LIMIT 20;
~~~

Khi planner có đủ thông tin và điều kiện phù hợp, PostgreSQL có thể **partition prune** để chỉ truy cập partition chứa tenant 42, thay vì tất cả. Đây là lợi ích của việc lấy tenant_id làm partition key.

Nhưng cùng lúc, những truy vấn tenant 42 vẫn tập trung lên **một partition** và, trong ví dụ PostgreSQL đơn máy, vẫn dùng tài nguyên chung của máy ấy. **Partition pruning** cải thiện phạm vi truy vấn; nó **không tự phân tán một tenant lớn qua nhiều máy**.

**Lưu ý vận hành:** EXPLAIN ANALYZE thực sự chạy truy vấn. Chỉ dùng trên dữ liệu kiểm thử hoặc với giới hạn an toàn khi truy vấn có thể gây tải lớn.

### 6.4. Thêm partition không tự giải quyết khóa whale

Nếu mở rộng từ 8 lên nhiều hash partition, tenant 42 **vẫn gắn với một giá trị tenant_id**. Dữ liệu của tenant có thể được tái phân phối sang một partition khác theo quy tắc mới, nhưng **không được chia nhỏ chỉ vì tăng số partition**.

Đổi số hash partition còn cần **kế hoạch chuyển dữ liệu phù hợp với cơ chế của hệ quản trị**; không giả định chỉ thay MODULUS trên các partition hiện hữu là có thể mở rộng tức thì mà không di chuyển hoặc kiểm tra dữ liệu.

## 7. Chẩn đoán trước khi chọn biện pháp sửa

| Triệu chứng đo được | Nguyên nhân có thể | Biện pháp nên thử trước |
| --- | --- | --- |
| Một record được UPDATE liên tục, nhiều lock wait | Hot row/counter | Gom batch, bucket counter, thiết kế bất biến giao dịch |
| Một tenant chiếm phần lớn insert/query trên shard | Whale tenant | Tách tenant hoặc chia dữ liệu tenant theo bucket/đơn |
| Hầu hết ghi vào partition tháng hiện tại | Temporal hot partition | Kết hợp thời gian với hash/bucket, tùy truy vấn và retention |
| Một khóa được đọc lặp lại rất nhiều | Read hot key | Cache, replica đọc, giảm lượng query không cần thiết |
| Một tenant chạy báo cáo quét hàng triệu sự kiện | Query hot spot | Chỉ mục phù hợp, phân trang/keyset, aggregate/read model |
| Các tenant tương đương nhưng một shard vẫn nóng | Hash collision, bố trí vật lý, uneven routing | Di chuyển virtual shard hoặc cân bằng lại routing |
| p99 tăng mạnh trong giờ nạp dữ liệu | Bulk ingestion tranh tài nguyên | Batch, queue, rate limiting, phân lập workload |
| Một máy nóng trong khi các partition local phân bố đều | Tài nguyên vật lý chung | Nâng tài nguyên hoặc tách sang node/cụm độc lập |

Không nhất thiết **đổi shard key** khi nguyên nhân là một câu SQL thiếu index hoặc một API gọi lặp cùng query. Thay shard key thường kéo theo migration và ảnh hưởng truy vấn, nên cần chứng minh phương án nhẹ hơn không đáp ứng được nhu cầu.
