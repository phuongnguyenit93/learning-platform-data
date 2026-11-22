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

## 8. Phân tách whale tenant bằng khóa ghép hoặc bucket

Khi một tenant quá lớn, **tenant_id đơn lẻ không còn đủ để phân phối tải ghi**. Một cách là chọn **đơn vị con có cardinality lớn hơn**, chẳng hạn:

~~~text
tenant_id + order_id
tenant_id + customer_id
tenant_id + entity_bucket
tenant_id + time_bucket + hash_bucket
~~~

Không thể tùy tiện chọn trường thứ hai: nó phải có nghĩa đối với **cách truy vấn và giao dịch cần được đặt gần nhau**.

### 8.1. Giữ dữ liệu của một đơn gần nhau

Giả sử một tenant có hàng trăm nghìn đơn. Mỗi đơn có nhiều sự kiện; các sự kiện của cùng đơn cần được xử lý theo thứ tự và truy vấn cùng nhau.

Chọn:

~~~text
bucket = order_id MOD 4

Phân phối logic theo (tenant_id, bucket).
~~~

Khi đó:

- Các đơn khác nhau có thể nằm ở bucket khác nhau, giúp tenant lớn **trải qua tối đa 4 đơn vị logic**.
- Các sự kiện của **cùng order_id** vẫn ở **cùng bucket**, thuận lợi cho đọc/ghi theo đơn.
- Truy vấn **mọi đơn của một tenant** phải thu dữ liệu từ cả bốn bucket rồi tổng hợp/sắp xếp.
- Nếu một **đơn duy nhất** là điểm nóng, phép chia theo order_id vẫn giữ toàn bộ tải của đơn đó tại một bucket. Cần biện pháp khác cho khóa đơn nóng.

### 8.2. Lược đồ PostgreSQL minh họa bucket có thể kiểm tra được

Để tránh nhầm **partitioning trên một server** với sharding nhiều máy, ví dụ này chỉ mô tả **4 partition logic** theo bucket. Một tầng định tuyến phân tán riêng có thể ánh xạ các cặp **(tenant_id, bucket)** đến các nút vật lý, nhưng ví dụ DDL **không triển khai định tuyến đó**.

~~~sql
CREATE TABLE tenant_order_events_bucketed (
    tenant_id BIGINT NOT NULL,
    bucket SMALLINT NOT NULL CHECK (bucket BETWEEN 0 AND 3),
    order_id BIGINT NOT NULL CHECK (order_id >= 0),
    event_seq INTEGER NOT NULL CHECK (event_seq > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    CHECK (bucket = (order_id % 4)::SMALLINT),
    PRIMARY KEY (tenant_id, bucket, order_id, event_seq)
) PARTITION BY LIST (bucket);

CREATE TABLE tenant_order_events_b0
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (0);
CREATE TABLE tenant_order_events_b1
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (1);
CREATE TABLE tenant_order_events_b2
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (2);
CREATE TABLE tenant_order_events_b3
    PARTITION OF tenant_order_events_bucketed FOR VALUES IN (3);

CREATE INDEX idx_bucketed_tenant_time
ON tenant_order_events_bucketed (tenant_id, occurred_at DESC);
~~~

**event_seq** được giả định duy nhất **trong một đơn**. Vì vậy, khóa **(tenant_id, bucket, order_id, event_seq)** phản ánh đúng grain là **một sự kiện của một đơn**. Trong hệ thống thật, nếu các event có **source_event_id** riêng, phải bổ sung chính sách idempotency và duy nhất theo nguồn.

Thử hai đơn cùng tenant thuộc các bucket khác nhau:

~~~sql
INSERT INTO tenant_order_events_bucketed
    (tenant_id, bucket, order_id, event_seq, occurred_at, payload)
VALUES
    (42, 0, 100, 1, TIMESTAMPTZ '2026-11-21 09:00:00+07',
     '{"type":"ORDER_CREATED"}'),
    (42, 1, 101, 1, TIMESTAMPTZ '2026-11-21 09:01:00+07',
     '{"type":"ORDER_CREATED"}'),
    (42, 0, 100, 2, TIMESTAMPTZ '2026-11-21 09:02:00+07',
     '{"type":"ORDER_CONFIRMED"}');
~~~

Nếu cố chèn **order_id = 100 nhưng bucket = 1**, **CHECK** từ chối. Điều này giúp ứng dụng không gán ngẫu nhiên cùng một đơn vào các bucket khác nhau.

Lấy dữ liệu của đúng một đơn:

~~~sql
SELECT event_seq, occurred_at, payload
FROM tenant_order_events_bucketed
WHERE tenant_id = 42
  AND bucket = (100 % 4)
  AND order_id = 100
ORDER BY event_seq;
~~~

Do query có bucket, PostgreSQL có thể prune để tìm đúng partition. Trong hệ phân tán, bộ định tuyến cũng có đủ thông tin **(tenant_id, bucket)** nếu cùng sử dụng một quy tắc ánh xạ đã xác nhận.

Lấy 50 sự kiện mới nhất của cả tenant:

~~~sql
SELECT order_id, event_seq, occurred_at, payload
FROM tenant_order_events_bucketed
WHERE tenant_id = 42
ORDER BY occurred_at DESC, order_id DESC, event_seq DESC
LIMIT 50;
~~~

Truy vấn này **có thể phải đọc tất cả bốn bucket** và kết hợp kết quả. Nếu chúng ở nhiều node, hệ phân tán cần **fan-out, merge kết quả và phân trang**. Có thể cần read model hoặc bảng tổng hợp riêng cho trang “hoạt động mới nhất của tenant” khi lưu lượng lớn.

### 8.3. Bucket theo order_id khác bucket theo event_id

| Cách tính bucket | Điều được đặt cùng nhau | Nhược điểm |
| --- | --- | --- |
| **order_id MOD B** | Sự kiện thuộc cùng đơn | Một đơn siêu nóng không được chia nhỏ |
| **event_id MOD B** | Các sự kiện riêng được chia theo ID | Sự kiện cùng đơn phân tán; đọc một đơn phải fan-out |
| **HASH(tenant_id, order_id)** | Đơn khác nhau có thể đi shard khác nhau | Truy vấn toàn tenant thường phân tán |
| **tenant_id** | Tất cả dữ liệu tenant gần nhau | Whale tenant vẫn chỉ có một vị trí định tuyến |
| **occurred_at** theo thời gian | Dữ liệu theo kỳ gần nhau | Ghi hiện tại vẫn dồn vào phân vùng đang mở |

Nếu dùng **B bucket**, không thể tự kết luận tải whale giảm đúng **B lần**: các đơn có thể không đều tải, các bucket có thể cùng ánh xạ tới một node, và một truy vấn lớn của tenant có thể chạm tất cả bucket.

### 8.4. Chia theo số shard vật lý không nên gắn cứng trong dữ liệu

Nếu ứng dụng ghi **bucket = hash(key) % 8** và mặc định bucket 0 là node A, việc tăng lên 16 node có thể buộc đổi khóa định tuyến hoặc di chuyển nhiều dữ liệu.

Thường hữu ích hơn là tách:

~~~text
Business key → logical bucket → placement map → physical node
~~~

Logical bucket có thể giữ ổn định trong khi **placement map** đổi vị trí bucket. Việc dùng **virtual shard/virtual bucket** hoặc consistent hashing là cách giảm chi phí tái cân bằng theo một số hệ thống, nhưng vẫn phải có kế hoạch chuyển dữ liệu, kiểm soát cấu hình và rollback. **Consistent hashing không chữa được hot key có tải vượt sức chịu đựng của một đơn vị** nếu toàn bộ khóa vẫn nằm ở một đơn vị.

## 9. Hot row: bucket hóa counter và xử lý tính đúng đắn

Phân tán bảng sự kiện chưa chắc giảm tranh chấp trên một hàng tổng:

~~~sql
CREATE TABLE tenant_usage (
    tenant_id BIGINT PRIMARY KEY,
    total_events BIGINT NOT NULL DEFAULT 0
);

-- Nhiều luồng cùng thực hiện:
UPDATE tenant_usage
SET total_events = total_events + 1
WHERE tenant_id = 42;
~~~

Một phương án cho **counter phân tích, telemetry hoặc thống kê có thể tổng hợp** là chia tổng thành nhiều **counter bucket**.

### 9.1. Lược đồ counter phân mảnh

~~~sql
CREATE TABLE tenant_counter_buckets (
    tenant_id BIGINT NOT NULL,
    bucket SMALLINT NOT NULL CHECK (bucket BETWEEN 0 AND 15),
    event_count BIGINT NOT NULL DEFAULT 0
        CHECK (event_count >= 0),
    PRIMARY KEY (tenant_id, bucket)
);
~~~

Mỗi sự kiện mới được định tuyến tới một bucket theo một hàm ổn định từ ID sự kiện hoặc phương án phân bổ có kiểm soát, rồi cập nhật một hàng:

~~~sql
INSERT INTO tenant_counter_buckets
    (tenant_id, bucket, event_count)
VALUES (42, 7, 1)
ON CONFLICT (tenant_id, bucket)
DO UPDATE SET
    event_count = tenant_counter_buckets.event_count + 1;
~~~

Tổng:

~~~sql
SELECT
    tenant_id,
    SUM(event_count) AS total_events
FROM tenant_counter_buckets
WHERE tenant_id = 42
GROUP BY tenant_id;
~~~

Nếu 16 bucket được lựa chọn đủ đều, cập nhật của tenant có thể tranh chấp **nhiều hàng thay vì một hàng**. Đổi lại, truy vấn tổng phải đọc/ghép kết quả; đồng thời cần một chính sách xác định bucket và tái xử lý khi job thất bại.

### 9.2. Những điều counter bucket không tự bảo đảm

- **Idempotency:** cùng một sự kiện được retry hai lần có thể làm tăng counter hai lần. Cần định danh sự kiện và quy tắc khử trùng, có thể đặt insert sự kiện và tăng counter trong cùng transaction phù hợp.
- **Tính nhất quán tức thời:** tổng đọc từ các bucket đang được cập nhật có thể cần snapshot transaction hoặc cơ chế đọc thích hợp để có một góc nhìn nhất quán.
- **Giới hạn nghiêm ngặt:** nếu tenant chỉ được dùng **tối đa 10.000 lượt**, hai luồng kiểm tra tổng đồng thời rồi ghi ở hai bucket có thể **cùng vượt hạn mức**. Phải có cơ chế đặt giữ/quota được đồng bộ chặt hoặc giao dịch có ràng buộc tương đương.
- **Trả lại/điều chỉnh:** counter không tự giải thích trường hợp hủy sự kiện, trừ điểm hoặc sửa số liệu lịch sử; cần định nghĩa event và luồng đảo.
- **Hot shard vật lý:** 16 hàng counter vẫn có thể nằm trên cùng một máy nếu schema không có cơ chế phân phối; bucket hóa hàng không đồng nghĩa tăng năng lực vật lý.

Khi yêu cầu **kiểm toán chính xác và có thể tái tính**, một lựa chọn là lưu **append-only event fact có khóa duy nhất**, sau đó tính tổng hoặc xây bảng tổng hợp theo batch/stream. Với quota nghiêm ngặt, phải thiết kế kiểm soát tài nguyên riêng; không nên dùng một counter eventual để thực thi hạn mức cứng.

## 10. Cô lập khách hàng quá lớn: tenant placement và dedicated shard

Không phải mọi whale cần bị chia ra hàng chục bucket. Nếu khách hàng W có **hàng triệu giao dịch nhưng truy vấn phần lớn toàn tenant**, chia bucket có thể làm mọi dashboard fan-out nhiều nơi, tăng độ phức tạp và chi phí mạng. Một phương án khác là **đưa W sang shard hoặc cụm riêng**.

### 10.1. Khi dedicated shard có lợi

- Khách hàng lớn cần lượng CPU/RAM/IOPS ổn định, có SLA khác nhóm còn lại.
- Workload có nhiều truy vấn/tổng hợp theo tenant và cần locality.
- Dữ liệu khách hàng có yêu cầu lưu tại vùng địa lý hoặc mức cô lập riêng.
- Cần tránh **noisy neighbor** giữa tenant lớn và tenant nhỏ.
- Dung lượng lớn nhưng vẫn **nằm trong khả năng phục vụ của một cụm dành riêng**.

Dedicated shard **không** giải quyết được mọi điểm nóng bên trong tenant: một hàng counter có thể tiếp tục gây tranh chấp; một truy vấn không có chỉ mục vẫn có thể chậm. Cô lập chỉ tránh ảnh hưởng tenant khác và tạo điều kiện cấp tài nguyên riêng.

### 10.2. Bảng điều phối tenant

Một dịch vụ điều phối có thể lưu:

~~~text
tenant_placement(
    tenant_id,
    placement_group,
    routing_version,
    migration_state
)

tenant 42  -> dedicated_group_W
tenant 101 -> shared_group_2
tenant 102 -> shared_group_5
~~~

Ứng dụng **tra placement** để định tuyến thay vì tính một hàm hash tenant cố định không thay được. Những bản ghi routing phải được cache có thời hạn và thay đổi bằng quy trình nhất quán; **routing_version** giúp phát hiện client còn sử dụng thông tin cũ.

Hệ thống có thể đặt:

~~~mermaid
flowchart TD
    REQ["Yêu cầu có tenant_id"]
    DIRECTORY["Tenant placement directory"]
    SHARED1[("Shared group A")]
    SHARED2[("Shared group B")]
    WHALE[("Dedicated group W")]
    REQ --> DIRECTORY
    DIRECTORY -->|"tenant nhỏ"| SHARED1
    DIRECTORY -->|"tenant nhỏ"| SHARED2
    DIRECTORY -->|"tenant W"| WHALE
~~~

Đây là sơ đồ kiến trúc logic. Cách triển khai thực tế phụ thuộc vào router, database và khả năng chuyển dữ liệu mà hệ thống hỗ trợ.

### 10.3. Di chuyển tenant cần kiểm soát tính nhất quán

Một cuộc chuyển tenant giữa các shard có thể bao gồm:

1. **Lập phạm vi dữ liệu:** bảng đơn, dòng, sự kiện, chỉ mục, file đính kèm, cache, báo cáo và các tham chiếu liên quan.
2. **Tạo đích:** schema, version migration, khóa, ràng buộc và cấu hình tại nhóm mới.
3. **Sao chép dữ liệu ban đầu:** theo snapshot nhất quán hoặc chiến lược được engine hỗ trợ.
4. **Bắt kịp thay đổi:** CDC/log-based replication hoặc một quy trình ghi có điều phối để không mất dữ liệu phát sinh trong lúc sao chép.
5. **Đối soát:** số hàng, khóa, tổng giao dịch, checksum hoặc phép so sánh tập bộ theo từng phạm vi phù hợp.
6. **Chuyển định tuyến có kiểm soát:** cập nhật placement phiên bản mới, xử lý yêu cầu đang chạy và tránh ghi đồng thời vào hai nơi như hai nguồn chuẩn.
7. **Giám sát và rollback:** theo dõi lỗi, độ trễ, lag, hướng rollback; không xóa nguồn ngay khi chưa đủ điều kiện xác nhận.

**Không nên mô tả dual-write “ghi cả hai nơi” là bảo đảm exactly-once.** Nếu một trong hai ghi lỗi, hai nơi có thể lệch. Cần giao thức cutover rõ, idempotency, xử lý thay đổi thứ tự và kế hoạch phục hồi. Migration tenant là một hoạt động dữ liệu có rủi ro, không chỉ thao tác đổi một dòng trong bảng routing.

## 11. Xử lý read hot key mà không làm lệch mô hình dữ liệu

Một số hot key chủ yếu bị **đọc rất nhiều**, không bị cập nhật cạnh tranh. Ví dụ một catalog sản phẩm phổ biến hoặc một cấu hình công khai của tenant.

### 11.1. Cache, read replica và tổng hợp trước

| Biện pháp | Phù hợp khi | Cần kiểm soát |
| --- | --- | --- |
| **Cache ở ứng dụng hoặc cache phân tán** | Giá trị đọc lặp lại, có thể phục vụ dữ liệu lưu trong thời gian ngắn | TTL, invalidation, stampede, cache key theo tenant |
| **CDN/edge cache** | Nội dung công khai, ít thay đổi | Quyền riêng tư, cache-control, không trộn dữ liệu tenant |
| **Read replica** | Tải đọc cao, có thể chấp nhận độ trễ đồng bộ | Replication lag, read-after-write consistency, định tuyến đọc |
| **Materialized view / read model** | Truy vấn tổng hợp hoặc dashboard nặng lặp lại | Làm mới, dữ liệu đến trễ, độ lệch với nguồn chuẩn |
| **Giảm truy vấn thừa** | API gọi lặp hoặc N+1 query | Batching, pagination, query plan, data loading |

Một cache key không có tenant_id có thể **rò dữ liệu xuyên tenant** dù cơ sở dữ liệu đã phân phối đúng. Trong hệ đa khách hàng, định danh cache, phân quyền và chính sách chia sẻ dữ liệu là một phần của thiết kế.

### 11.2. Tình huống cache stampede

Nếu 10.000 request cùng đọc một bản ghi, cache hết hạn đồng thời có thể khiến cả 10.000 request dồn vào database. Các chiến lược như **staggered TTL**, **single-flight/request coalescing**, **stale-while-revalidate** hoặc chủ động làm mới cache có thể giúp giảm đột biến, nếu yêu cầu nhất quán cho phép.

Không dùng dữ liệu **stale** để ra quyết định ghi quan trọng như trừ tiền hoặc xác định hạn mức còn lại mà không kiểm tra nguồn chuẩn theo giao thức phù hợp.

## 12. Thiết kế phân phối phải bảo vệ khóa, quan hệ và giao dịch

### 12.1. Khóa duy nhất theo tenant khác duy nhất toàn hệ thống

Giả sử mỗi tenant tự cấp **order_number = "001"**. Lược đồ hợp lý:

~~~sql
CREATE TABLE orders_multi_tenant (
    tenant_id BIGINT NOT NULL,
    order_number VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_number)
);
~~~

Ở đây **(tenant_id, order_number)** là khóa nghiệp vụ duy nhất; **order_number một mình không duy nhất**. Khi phân phối theo tenant_id, hệ thống có thể kiểm tra tính duy nhất cặp trong shard chứa tenant.

Nếu nghiệp vụ yêu cầu **external_reference duy nhất trên mọi tenant**, chỉ dùng UNIQUE trong từng shard **không đủ** để bảo đảm điều đó trên toàn hệ thống. Có thể cần ID được phát theo một chiến lược toàn cục, dịch vụ cấp phát/đăng ký tham chiếu hoặc giao thức nhất quán phù hợp. Một UUID giảm xác suất va chạm nhưng **không tự thay thế** ràng buộc duy nhất hoặc quy trình giải quyết xung đột.

### 12.2. Đặt những dữ liệu thường giao dịch cùng nhau gần nhau

Trong hệ đơn hàng:

~~~text
orders(tenant_id, order_id, ...)
order_lines(tenant_id, order_id, line_no, ...)
payments(tenant_id, order_id, payment_id, ...)
~~~

Nếu một giao dịch cần cập nhật đơn và dòng một cách nguyên tử, đặt các hàng liên quan trên cùng đơn vị phân phối có thể tránh giao dịch xuyên shard. Một chiến lược dùng **HASH(tenant_id, order_id)** có thể giữ hàng theo đơn gần nhau, nhưng sẽ rải các đơn của cùng tenant.

Muốn co-locate, **tất cả bảng liên quan phải dùng khóa định tuyến tương thích**. Chỉ thêm cột tenant_id vào một bảng không bảo đảm một engine phân tán tự đặt hàng theo cùng shard, và PostgreSQL một instance không tự trở thành hệ phân tán.

### 12.3. Foreign key xuyên shard và thay đổi tenant placement

Khóa ngoại giữa order_lines và orders là quy tắc nghiệp vụ có ý nghĩa dù dữ liệu phân phối. Tuy nhiên, **khả năng thực thi FK xuyên shard** phụ thuộc engine và kiến trúc. Có hệ hỗ trợ ràng buộc khi co-locate, có hệ giới hạn hoặc không cung cấp FK xuyên node.

Nếu không thể dùng FK trực tiếp, cần xác định:

- Đường ghi nào xác minh order tồn tại và thuộc đúng tenant?
- Khi xóa/hủy order, làm sao tránh orphan lines?
- Nếu có ghi thất bại giữa nhiều shard, cơ chế bù trừ/khôi phục là gì?
- Những tác vụ đối soát nào phát hiện thiếu quan hệ?

**Không được suy “cơ sở dữ liệu phân tán nên không cần toàn vẹn tham chiếu”.** Ràng buộc vẫn là yêu cầu nghiệp vụ; có thể phải thực thi bằng cơ chế khác và chấp nhận chi phí.

### 12.4. Sự kiện có thứ tự và dữ liệu đến trễ

Khi chia một tenant thành nhiều bucket, các sự kiện từ các bucket có thể đến bộ xử lý theo thứ tự khác nhau. Nếu nghiệp vụ cần **thứ tự trong từng order**, định tuyến theo order_id giữ cùng một khóa thứ tự dễ hơn; nếu cần **thứ tự toàn tenant**, việc chia tenant có thể làm yêu cầu này tốn kém hơn nhiều.

Không lấy thứ tự tăng của ID ở các shard riêng rồi kết luận có **một thứ tự toàn cục**. Thiết kế event cần phân biệt:

- **Event time:** khi sự kiện xảy ra.
- **Ingestion/commit time:** khi hệ thống nhận và lưu.
- **Sequence:** phạm vi nào phải có thứ tự, ví dụ mỗi order.
- **Idempotency key:** cách nhận diện sự kiện được retry.

Nếu báo cáo hoặc workflow yêu cầu trạng thái nhất quán xuyên bucket, phải có quy tắc hợp nhất theo thứ tự và xử lý dữ liệu đến trễ.

### 12.5. Tránh scatter-gather vô hạn

Truy vấn:

~~~sql
SELECT *
FROM tenant_order_events_bucketed
WHERE tenant_id = 42
ORDER BY occurred_at DESC
LIMIT 50;
~~~

trong mô hình bucket có thể chạm nhiều nơi. Với 4 bucket, đây có thể chấp nhận được; với 1.024 bucket trải trên nhiều cụm, phát 1.024 truy vấn cho mỗi trang API có thể gây độ trễ và chi phí mạng lớn.

Những biện pháp thường cần phối hợp:

- **Giới hạn số bucket mỗi tenant** theo nhu cầu, không mặc định một số khổng lồ.
- **Keyset pagination** với thứ tự ổn định và tie-breaker rõ.
- **Đẩy điều kiện lọc và LIMIT phù hợp** xuống từng bucket, merge toàn cục một cách chính xác.
- **Read model theo tenant** cho giao diện cần dòng thời gian thống nhất.
- **Budget truy vấn** theo tenant: thời gian, số hàng quét, mức song song và rate limit.

Lựa chọn shard key là bài toán cân bằng giữa **độ đồng vị trí (locality)** và **mức phân tán tải**, không phải cuộc thi tìm khóa có nhiều giá trị nhất.

## 13. Phối hợp phân vùng thời gian với phân phối theo tenant

Hệ thống sự kiện thường cần cả **retention theo thời gian** và **chịu tải tenant lớn**. Có thể kết hợp hai trục:

~~~text
logical route = (tenant_id, entity_bucket)
storage partition = month(occurred_at)

Ví dụ:
  Tenant 42, bucket 0 -> node A -> events_2026_11
  Tenant 42, bucket 1 -> node B -> events_2026_11
  Tenant 42, bucket 2 -> node C -> events_2026_11
  Tenant 42, bucket 3 -> node D -> events_2026_11
~~~

Đây là **một sơ đồ logic giả định**, không phải cấu hình PostgreSQL chạy tự động từ DDL trước. Ý tưởng là:

- **Bucket** giúp phân phối sự kiện của một tenant lớn giữa các nhóm tài nguyên.
- **Thời gian** giúp prune khi query theo kỳ và quản lý xóa dữ liệu hết hạn theo partition.
- **Định tuyến** cần biết khóa và mapping của tenant/bucket.
- **Truy vấn lịch sử cả tenant** có thể vẫn phải chạm nhiều bucket và nhiều partition thời gian.

Nếu chỉ phân theo tháng, giờ ghi hiện tại vẫn có thể nóng. Nếu chỉ hash theo tenant, whale vẫn có thể bị dồn. Nếu chia bucket mà không xét thời gian, xóa dữ liệu hết hạn có thể phải xóa hàng loạt trên mọi bucket. **Nhiều trục phân phối giải quyết những nhu cầu khác nhau và làm tăng độ phức tạp quản trị.**

### 13.1. Không dùng thời gian như khóa thay thế cho danh tính sự kiện

Hai sự kiện có thể xảy ra cùng timestamp; cùng order có thể có nhiều event trong một mili giây. Khóa nhận diện cần một **event_id hoặc sequence ổn định** theo phạm vi đúng; occurred_at chủ yếu phục vụ thời gian, lọc và sắp xếp. Nếu dùng timestamp làm toàn bộ khóa duy nhất khi nghiệp vụ cho phép trùng thời điểm, sẽ làm mất sự kiện hợp lệ.

### 13.2. TTL và việc xóa cả partition

Trong kho dữ liệu theo kỳ, xóa/drop một partition cũ có thể hiệu quả hơn xóa từng hàng; nhưng phải bảo đảm:

- Không còn dữ liệu cần giữ vì hợp đồng hoặc kiểm toán.
- Phân vùng thực sự **tách đúng phạm vi ngày hết hạn**.
- Các bảng liên quan, index, sao lưu và các bản sao/read model được xử lý theo quy trình.
- Không vô tình xóa dữ liệu tenant khác có chính sách lưu lâu hơn.

Một whale tenant có thể cần retention hoặc vùng lưu trữ riêng; **đừng đặt chính sách TTL duy nhất theo toàn bảng** nếu các khách hàng có nghĩa vụ khác nhau.

## 14. Kiểm chứng bằng tải thực tế và thử tình huống mất cân bằng

Một kiến trúc có sơ đồ phân phối đẹp vẫn có thể thất bại khi chịu **đợt tải lớn từ một tenant duy nhất**. Benchmark nên tái hiện đúng kiểu truy vấn, mẫu thời gian và tính cạnh tranh của nghiệp vụ, thay vì chỉ tạo nhiều khóa ngẫu nhiên đều nhau.

### 14.1. Bộ kịch bản tải tối thiểu

| Kịch bản | Cách tạo tải | Cần đo |
| --- | --- | --- |
| **A. Bình thường** | Nhiều tenant nhỏ, tải gần đều | QPS, CPU/node, p95/p99 và số truy vấn |
| **B. Whale** | Một tenant chiếm 40–70% yêu cầu trong giờ cao điểm | Hot shard, tenant latency, ảnh hưởng tenant nhỏ |
| **C. Burst** | Tenant lớn nhập một batch trong vài phút | Queue depth, write latency, lag và backpressure |
| **D. Hot counter** | Nhiều worker cùng cập nhật một tenant_usage row | Lock wait, retry, thông lượng cập nhật |
| **E. Hot read key** | Nhiều request cùng đọc một giá trị | Cache hit, miss storm, replica lag |
| **F. Cross-bucket query** | Trang hoạt động mới nhất của tenant lớn | Số shard chạm, bytes chuyển, merge latency |
| **G. Rebalance/failover** | Di chuyển bucket hoặc chuyển routing | Mất/trùng dữ liệu, thời gian gián đoạn, phiên bản route |
| **H. Query nặng đồng thời** | Tenant lớn chạy báo cáo cùng luồng ghi | p99 của giao dịch thường, CPU/IO và timeout |

Không chỉ đo throughput tối đa. Kiểm tra **fairness**: khi W chạy batch lớn, các tenant nhỏ có còn đạt SLO bình thường không? Dedicated shard có thể cải thiện fairness dù tổng QPS toàn hệ thống không thay đổi đáng kể.

### 14.2. Các phép đo định lượng nên có

Đặt:

\[
\text{Skew ratio} =
\frac{\max(\text{tải trên các shard})}
{\text{trung bình tải trên tất cả shard}}.
\]

Mẫu số phải tính **tất cả shard đang hoạt động**, kể cả shard không có hàng hoặc không nhận yêu cầu. Chọn **tải** cụ thể trước khi tính: request/giây, CPU, byte ghi, IOPS hay số hàng là những trục khác nhau.

Ngoài skew ratio, theo dõi:

- **Top-1/Top-10 tenant share** của request, CPU hoặc số hàng.
- **p95/p99 latency theo tenant và tuyến API**, tránh che tenant bị chậm.
- **Busy/idle ratio** giữa các node.
- **Thời gian chờ lock** trên khóa/record nóng.
- **Fan-out count** và dữ liệu truyền giữa shard trên một truy vấn.
- **Recovery time**, số bản ghi sai lệch trước/sau migration và số retry idempotent.

Ví dụ một SLO kiểm thử **được đặt giả định**, không phải ngưỡng chuẩn chung:

~~~text
Khi tenant W tạo 40% tổng số request:
  p99 của API đọc đơn với tenant nhỏ < 200 ms;
  tỷ lệ lỗi ghi toàn hệ thống < 0,1%;
  không mất hoặc nhân đôi event khi chuyển routing;
  có thể đối soát toàn bộ khóa sự kiện sau chuyển.
~~~

Các ngưỡng cụ thể phải dựa trên hợp đồng, hệ quản trị và năng lực hạ tầng của dự án. Dùng một bài test tải đồng đều không đủ để nghiệm thu xử lý whale.

### 14.3. Đánh giá trước và sau tối ưu

| Chỉ số | Trước tối ưu | Sau tối ưu | Câu hỏi |
| --- | --- | --- | --- |
| Max-to-avg writes | Đo theo shard | Đo cùng cửa sổ | Tải đã đều hơn chưa? |
| p99 tenant W | Theo request quan trọng | Theo cùng request | Whale có được phục vụ nhanh hơn không? |
| p99 các tenant nhỏ | Khi W bùng tải | Khi W bùng tải | Có giảm noisy-neighbor không? |
| Số shard cho truy vấn toàn tenant | Thường 1 | Có thể B | Chi phí fan-out tăng bao nhiêu? |
| Thời gian cập nhật một counter | Lock wait cũ | Cơ chế mới | Đã xử lý hot row chưa? |
| Độ đúng số lượng/quota | Đối soát nguồn | Đối soát nguồn | Có phát sinh ghi trùng, thiếu hoặc vượt hạn mức không? |

Tối ưu được xem là thành công khi **đáp ứng mục tiêu nghiệp vụ với chi phí tổng thể chấp nhận được**, không chỉ vì biểu đồ số hàng giữa partition trông đều.

## 15. Bảng quyết định theo loại vấn đề

| Bối cảnh | Hướng xử lý đáng cân nhắc | Đánh đổi quan trọng |
| --- | --- | --- |
| Nhiều tenant nhỏ, truy vấn theo tenant, không có whale | **Hash theo tenant_id** | Co-location tốt; cần giám sát tăng trưởng |
| Một tenant lớn nhưng vẫn vừa năng lực một cụm riêng | **Dedicated shard / tenant placement** | Migration và vận hành riêng, nhưng giữ truy vấn tenant gần nhau |
| Một tenant có nhiều đơn độc lập, write QPS vượt một shard | **Hash theo tenant + order/bucket** | Truy vấn toàn tenant fan-out; giao dịch theo order dễ hơn theo tenant |
| Một order hoặc một record tự nó cực nóng | **Hot-key-specific design**: cache, queue, serialized owner, batching, read replica, counter sharding tùy loại | Không thể chữa chỉ bằng bucket theo order_id |
| Ghi dồn vào partition tháng hiện tại | **Hash/bucket trong từng kỳ, hoặc sharding độc lập theo entity** | Cần hai chiều phân vùng, routing và query plan phức tạp hơn |
| Một hàng đếm sự kiện bị update liên tục | **Append event + aggregate** hoặc **counter buckets** | Đọc tổng/tính chính xác và idempotency cần thiết kế |
| Chủ yếu đọc cùng một khóa | **Cache, replica, giảm query thừa** | Invalidation, stale read, quyền truy cập |
| Báo cáo toàn tenant rất nặng | **Read model, pre-aggregation, warehouse** | Làm mới, đối soát, tách nguồn chuẩn |
| Tenant có yêu cầu residency hoặc isolation riêng | **Tenant placement theo vùng/cụm** | Định tuyến, vận hành, sao lưu và migration |

Không cần áp dụng mọi kỹ thuật cùng lúc. Chọn phương án dựa trên **điểm nóng đã đo** và câu hỏi nào hệ thống phải trả lời nhanh nhất.

### 15.1. Quy trình ra quyết định

1. **Chốt grain và khóa:** một hàng là đơn, sự kiện của đơn, snapshot theo ngày hay counter tổng hợp?
2. **Xem workload:** phân bố tenant, key, đọc/ghi, kích thước hàng, truy vấn, giờ cao điểm.
3. **Xác định loại nóng:** hot row, hot read key, hot partition, hot node hay hot query.
4. **Tìm biện pháp nhỏ nhất có hiệu lực:** index/caching/batch/rate limit trước khi quyết định migration toàn bộ shard key.
5. **Đánh giá locality và giao dịch:** cần kết hợp những bảng/khóa nào trong cùng transaction?
6. **Đánh giá ảnh hưởng khóa duy nhất và tham chiếu:** có cần global uniqueness, FK/cascade hay thứ tự sự kiện toàn tenant?
7. **Chọn routing và partitioning:** tenant, composite key, bucket, time, dedicated placement hoặc tổ hợp có kiểm soát.
8. **Thiết kế kiểm thử lệch:** mô phỏng tenant W, burst, hot counter, failover, query fan-out.
9. **Lập phương án chuyển và rollback:** đối soát dữ liệu, cập nhật mapping, xử lý yêu cầu trong lúc di chuyển.
10. **Đánh giá lại theo chu kỳ:** một tenant nhỏ hôm nay có thể thành whale sau ba tháng.

## 16. Bài tập vận dụng

### Bài 1. Hash đều khóa nhưng không đều tải

Một hệ thống có **8 shard**, tổng **2.000.000 thao tác ghi/ngày**. Tenant A chiếm **600.000 thao tác**; phần còn lại đến từ nhiều tenant nhỏ. Mỗi tenant được gán nguyên vẹn vào một shard bằng HASH(tenant_id).

**Yêu cầu:**

1. Tính tải trung bình lý tưởng trên mỗi shard.
2. Chứng minh giới hạn dưới cho tải shard chứa A và tỷ lệ so với trung bình.
3. Nếu tăng lên **16 shard** nhưng vẫn phân theo tenant_id và tổng tải không đổi, kết luận có chắc A bớt nóng không?
4. Nêu hai cách giải quyết phù hợp nếu thao tác của A phân theo nhiều đơn độc lập.

<details>
<summary>Gợi ý lời giải bài 1</summary>

Trung bình lý tưởng với 8 shard: **2.000.000 / 8 = 250.000 thao tác/ngày/shard**. Shard chứa A có ít nhất **600.000**, nên lệch ít nhất **600.000 / 250.000 = 2,4 lần**.

Nếu là 16 shard, mức trung bình giảm xuống **125.000** nhưng tenant A vẫn tối thiểu **600.000** ở một shard, nên tỷ lệ max/avg tối thiểu **4,8 lần**. Điều này không có nghĩa tải tuyệt đối shard A tăng; nó cho thấy **thêm shard không tự chia nhỏ A**.

Hai hướng: **đưa A sang cụm riêng** nếu một cụm đủ phục vụ, hoặc **bucket theo order_id** để phân tải các đơn độc lập của A qua nhiều nơi, chấp nhận fan-out khi xem toàn tenant.

</details>

### Bài 2. Đổi shard key có đánh đổi gì?

Nền tảng lưu ba loại dữ liệu:

~~~text
orders(tenant_id, order_id, created_at)
order_lines(tenant_id, order_id, line_no, product_id)
order_events(tenant_id, order_id, event_seq, occurred_at)
~~~

Yêu cầu:

- Xem chi tiết một order phải nhanh và nhất quán.
- Một tenant lớn tạo rất nhiều order độc lập.
- Dashboard “50 hoạt động mới nhất của mọi order thuộc tenant” được mở thường xuyên.

**Yêu cầu:** so sánh shard key **tenant_id** và **(tenant_id, order_id)** về ghi, locality, giao dịch và dashboard; đề xuất một phương án đáp ứng cả hai kiểu truy vấn.

<details>
<summary>Gợi ý lời giải bài 2</summary>

Theo **tenant_id**, một tenant dễ truy vấn toàn bộ dữ liệu tại một nơi, nhưng whale bị dồn. Theo **(tenant_id, order_id)**, các hàng của một order có thể co-locate và các order của whale phân tán, nhưng dashboard toàn tenant phải fan-out, merge và phân trang.

Có thể dùng các shard theo order để phục vụ ghi/chi tiết order, đồng thời duy trì **read model hoặc bảng tổng hợp hoạt động theo tenant** cho dashboard. Read model phải có thứ tự, idempotency, độ trễ làm mới và nguồn sự thật rõ.

</details>

### Bài 3. Nút thắt là một hàng counter

Các event của tenant B đã được chia khá đều giữa 8 partition, nhưng API vẫn chậm ở bước:

~~~sql
UPDATE tenant_usage
SET used_events = used_events + 1
WHERE tenant_id = 99;
~~~

Tại sao đổi partition key của bảng event có thể không giúp? Đề xuất cách cải thiện khi counter chỉ phục vụ dashboard, và giải thích vì sao cách đó không tự phù hợp với **quota cứng 100.000 lượt**.

<details>
<summary>Gợi ý lời giải bài 3</summary>

Điểm nghẽn là **một hàng tenant_usage** bị nhiều giao dịch cập nhật; các event phân đều không thay đổi nơi hàng counter được cập nhật. Nếu chỉ để thống kê, có thể **append event rồi tổng hợp theo kỳ** hoặc chia counter thành nhiều hàng **(tenant_id,bucket)**, sau đó SUM khi đọc.

Với quota cứng, hai giao dịch có thể cùng nhìn tổng còn chỗ rồi cùng tăng ở các bucket khác nhau, dẫn tới vượt hạn mức. Cần **cơ chế đặt giữ/quyết định quota được đồng bộ chặt**, idempotency và xử lý cạnh tranh; không dựa vào counter eventual thông thường.

</details>

### Bài 4. Chọn thuật toán bucket đúng grain

Một tenant có 80.000 đơn, mỗi đơn phát 5–20 event. Đơn số 100 chứa một chuỗi sự kiện phải được xử lý theo **event_seq** tăng dần.

**Yêu cầu:**

1. So sánh **bucket = order_id MOD 4** và **bucket = event_id MOD 4**.
2. Với order_id = 100, bucket nào được chọn theo phương án đầu?
3. Một truy vấn lấy toàn bộ event của order 100 nên có điều kiện lọc gì?
4. Nếu chính order 100 nhận 90% event toàn tenant, phương án đầu có giải quyết điểm nóng không?

<details>
<summary>Gợi ý lời giải bài 4</summary>

**Bucket theo order_id** đặt mọi event một order cùng nơi, thuận tiện giữ thứ tự theo event_seq và cập nhật nhất quán trong phạm vi order. **Bucket theo event_id** có thể trải event cùng order ra nhiều nơi, khiến truy vấn và kiểm soát thứ tự khó hơn.

Với 100 MOD 4 = **0**. Truy vấn nên lọc **tenant_id**, **bucket = 0**, **order_id = 100** rồi ORDER BY **event_seq**. Nếu một order chiếm 90% tải, bucket theo order_id vẫn dồn nó vào một bucket; cần xử lý hot order riêng, batch/queue/caching tùy đọc/ghi và yêu cầu thứ tự.

</details>

### Bài 5. Phân vùng theo tháng không phải tự động cân bằng

Hệ thống lưu ba partition theo tháng. Mọi thao tác ghi của tháng 11 vào partition **events_2026_11**; dữ liệu tháng 9 và 10 chỉ phục vụ tra cứu lịch sử.

**Yêu cầu:** nêu vì sao số hàng trải đều trên ba partition không chứng minh ghi cân bằng; đề xuất cách kết hợp hash/bucket và thời gian khi cần vừa chịu ghi lớn vừa xóa dữ liệu theo kỳ.

<details>
<summary>Gợi ý lời giải bài 5</summary>

Tổng hàng có thể đều nhưng **tải ghi hiện tại tập trung vào một partition tháng 11**. Cần đo QPS/CPU/IOPS/index contention trên thời gian ngắn, không chỉ row count.

Có thể chia dữ liệu theo **nhiều bucket entity/tenant bên trong từng tháng**, hoặc phân phối theo khóa sự kiện/đơn tới node rồi partition theo thời gian ở từng node. Phải giữ khả năng prune theo ngày và định tuyến theo bucket; truy vấn nhiều kỳ/toàn tenant có thể phải fan-out.

</details>

### Bài 6. Di chuyển tenant lớn có an toàn không?

Tenant W chuyển từ **shared_group_A** sang **dedicated_group_W**. Job đã sao chép một snapshot và cập nhật routing, nhưng trong lúc sao chép vẫn có các yêu cầu ghi mới vào shared_group_A.

**Yêu cầu:**

1. Chỉ ra nguy cơ mất dữ liệu.
2. Nêu phương án bắt kịp thay đổi trước khi cutover.
3. Cần xác minh gì để tránh duplicate hoặc thiếu event?
4. Nếu có hai ứng dụng đang cache hai phiên bản routing khác nhau, phải xử lý ra sao?

<details>
<summary>Gợi ý lời giải bài 6</summary>

Snapshot không chứa những thay đổi sau thời điểm chụp, nên nếu đổi routing ngay mà không bắt kịp log, đích có thể **thiếu event**. Có thể dùng CDC theo vị trí log hoặc chiến lược migration có chặn/chuyển ghi trong cửa sổ cutover. Cần đối soát khóa định danh, row count, phiên bản event, kết quả tổng hợp và tính duy nhất theo phạm vi.

Routing phải có **phiên bản/epoch** và quy tắc xử lý client cũ; không để cả nguồn và đích cùng nhận ghi như hai nguồn chuẩn vô hạn định. Cần lập kế hoạch rollback, retry idempotent và kiểm thử trường hợp yêu cầu đang chạy.

</details>

### Bài 7. Thống kê lệch theo hàng chưa đủ

Một shard chỉ có **5% số hàng** nhưng lại tiêu thụ **65% CPU**, trong khi một shard khác giữ **40% số hàng** và hầu như không có truy cập.

**Yêu cầu:** có thể kết luận shard nhiều hàng là điểm nóng không? Nêu ba số liệu khác cần thu và hai nguyên nhân tiềm năng khiến shard ít hàng lại nóng.

**Hướng giải:** không. Số hàng là **data skew**, CPU và latency phản ánh **workload skew**. Nên đo request/giây, loại truy vấn và số hàng quét, IOPS, lock wait, p99 latency và cache hit. Shard ít hàng có thể chứa **một hot key bị đọc/cập nhật liên tục**, hoặc một truy vấn thiếu index quét nhiều dữ liệu trong mỗi request; cũng có thể có batch ghi hoặc tranh chấp CPU với tác vụ nền.

## 17. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Hash đều tenant_id sẽ luôn cân bằng QPS.” | Hash cân bằng phân bố khóa tốt hơn khi tải từng khóa tương đương; whale tenant vẫn nóng. |
| “Thêm shard sẽ tự tách tenant lớn.” | Nếu định tuyến nguyên tenant theo tenant_id, toàn bộ tenant vẫn ở một shard. |
| “Partition PostgreSQL tức là sharding đa máy.” | Partition cục bộ không tự sinh node hay tài nguyên riêng. |
| “Bảng lớn nhất chắc chắn là hot partition.” | Cần xem tải đọc/ghi, CPU, I/O, thời gian chờ và độ trễ. |
| “Đã chia event nên counter không thể nóng.” | Hàng counter có thể là điểm tuần tự hóa riêng. |
| “Bucket càng nhiều càng tốt.” | Nhiều bucket tăng fan-out, chỉ mục, routing và chi phí quản lý. |
| “Bucket theo order_id cũng chia một order nóng.” | Mọi event của order vẫn vào một bucket theo thiết kế ấy. |
| “Có consistent hashing thì không còn hot key.” | Consistent hashing hỗ trợ định tuyến/tái cân bằng, không phân nhỏ tải của một khóa đơn. |
| “Cache giải quyết mọi hot key.” | Cache chủ yếu giúp đọc; ghi đồng thời và tính nhất quán vẫn cần cơ chế riêng. |
| “ON CONFLICT trên từng shard bảo vệ UNIQUE toàn hệ thống.” | Duy nhất toàn cục cần cơ chế phù hợp với phạm vi khóa và phân phối. |
| “Số event bucket cộng lại tự động đúng.” | Retry, ghi trùng, late event và điều chỉnh cần idempotency/đối soát. |
| “Chuyển tenant chỉ là sửa routing table.” | Phải chuyển dữ liệu, bắt kịp thay đổi, cutover, kiểm tra và có rollback. |
| “p95 toàn hệ thống thấp nghĩa là mọi tenant ổn.” | Số liệu tổng có thể che một whale hoặc nhóm tenant bị chậm. |

## 18. Ghi nhớ

**Khóa nóng** là vấn đề lượng truy cập/ghi tập trung vào một khóa, một hàng hoặc một vùng tài nguyên. **Whale tenant** là khách hàng có tải hoặc dung lượng rất lớn so với phần còn lại. **Phân bố lệch** có thể xuất hiện theo số hàng, số byte, CPU, QPS, IOPS, lock wait hoặc độ trễ; **phân bố đều số bản ghi không bảo đảm cân bằng tải**.

Chọn **HASH(tenant_id)** có lợi cho locality của dữ liệu cùng khách hàng, nhưng không chia được một whale tenant. Chia tiếp theo **order_id/bucket** có thể phân phối các đơn độc lập, đổi lại truy vấn toàn tenant phải fan-out. **Dedicated shard** giúp cô lập noisy neighbor và giữ dữ liệu tenant gần nhau nhưng cần migration cẩn thận; **counter buckets** xử lý một số hot row nhưng không tự giải quyết quota cứng; **cache và read model** có thể thích hợp hơn khi nút thắt là đọc.

Quy trình đáng tin cậy là **định nghĩa grain và bất biến → đo hot key/tenant/shard/node → phân loại nguyên nhân → chọn giải pháp nhỏ nhất hiệu quả → kiểm tra khóa, toàn vẹn, transaction và routing → thử tải lệch và migration → giám sát theo tenant liên tục**. Mô hình phân tán tốt phải vừa phân phối tài nguyên hợp lý, vừa giữ đúng nghĩa và tính nhất quán của dữ liệu.
