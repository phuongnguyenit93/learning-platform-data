# Thiết kế lại khi mẫu truy cập thay đổi

## Mục tiêu bài học

Apache Cassandra thường được thiết kế **từ truy vấn cần phục vụ**: partition key định vị dữ liệu trên cụm phân tán, còn clustering column sắp xếp các hàng trong một partition. Vì vậy, schema đang đáp ứng tốt một ứng dụng hôm nay chưa chắc phù hợp khi xuất hiện màn hình mới, khách hàng lớn hơn, lưu lượng đỉnh đổi hướng hoặc chính sách lưu trữ thay đổi.

Đặc điểm quan trọng là **không thể sửa một partition key đã chọn bằng vài câu `ALTER TABLE` rồi mong các dữ liệu cũ tự được phân bố lại**. Khi mẫu truy cập thật sự thay đổi, ta thường cần bảng query-driven mới, quy tắc đồng bộ dữ liệu, backfill, đối soát và kế hoạch chuyển đường đọc có kiểm soát.

Bài học thuộc chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung kết nối khóa phân vùng, clustering, CQL, replication, consistency đọc/ghi, compaction, repair, lỗi từng phần và cách ứng dụng Java triển khai chuyển đổi schema.

Sau khi học, bạn có thể:

- Phát hiện thay đổi mẫu truy cập bằng query inventory, tần suất, độ trễ p95/p99, fan-out và phân bố dữ liệu.
- Phân biệt trường hợp chỉ cần thêm cột thường hoặc index phù hợp với trường hợp **bắt buộc đổi đường truy cập**.
- Thiết kế bảng **v2** theo partition/clustering key mới mà không ghi đè hoặc phá hỏng đường đọc v1.
- Tổ chức live changes, backfill, revision, deduplication, shadow read và kiểm chứng dữ liệu trước khi chuyển traffic.
- Xử lý trạng thái thay đổi khóa, sự kiện đến muộn, TTL, tombstone, sự cố giữa các mutation và rollback.
- Lập kế hoạch di trú kèm điều kiện chuyển giai đoạn, chỉ số quan sát và giới hạn tài nguyên.

## 1. Một schema tốt có thể trở thành schema không phù hợp

Giả sử một hệ thống đơn hàng đa tenant ban đầu chỉ có yêu cầu:

> Xem 50 đơn gần nhất của một khách hàng trong tháng UTC.

Bảng cũ được thiết kế với partition theo tenant/khách hàng/tháng và clustering theo thời điểm tạo:

```sql
CREATE TABLE orders_by_customer_month_v1 (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Truy vấn v1:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month_v1
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

Trong truy vấn này, caller đưa đủ partition key. Cassandra có thể định tuyến đến tập replica chứa partition cần đọc, rồi lấy phần đầu theo clustering order. Đây là một lựa chọn hợp lý đối với **mẫu truy cập ban đầu**.

Vài tháng sau, sản phẩm thêm màn hình cho đội vận hành:

> Xem 50 đơn **đang PENDING**, được tạo trong **ngày UTC X**, trên **toàn tenant**, mới nhất trước.

Truy vấn mới chỉ biết `tenant_id`, `status` và `created_day`. Nó **không biết `customer_id`** của từng đơn. Nếu cố dùng bảng v1, ứng dụng có thể phải lấy danh sách rất nhiều khách hàng, truy vấn nhiều partition rồi lọc/sắp xếp ở Java. Cassandra không tự có một phép `JOIN` hay `ORDER BY` toàn cục hiệu quả trên mọi partition như một SQL database phục vụ quét.

Schema v1 **không sai**; nó phục vụ một hợp đồng truy vấn khác. Yêu cầu mới khiến kiến trúc cần thêm đường truy cập.

## 2. Nhận diện thay đổi bằng dữ liệu thay vì cảm giác

Không phải mọi thay đổi về UI hoặc tăng traffic đều cần đổi schema. Trước hết, ghi lại **khác biệt giữa workload trước và sau**.

| Khía cạnh | Trước thay đổi | Sau thay đổi | Hệ quả thiết kế |
| --- | --- | --- | --- |
| Khóa caller có | Tenant, customer, tháng | Tenant, status, ngày | Thiếu khóa định vị của bảng cũ |
| Thứ tự | `created_at DESC` của một khách | `created_at DESC` toàn tenant/trạng thái/ngày | Muốn một trục thời gian khác |
| Phạm vi | Một partition khách/tháng | Nhiều khách trong tenant | Fan-out có thể rất lớn |
| Tần suất | Màn hình khách được đọc thường xuyên | Hàng đợi PENDING cũng được đọc thường xuyên | Truy vấn mới đáng có đường truy cập riêng |
| Tải ghi | Chủ yếu thêm đơn | Đơn chuyển status nhiều lần | Projection theo status cần xóa/ghi khi đổi khóa |
| Độ mới | Danh sách khách có thể hơi trễ | Hàng đợi cần phản ánh thay đổi trong SLO rõ | Phải thiết kế đồng bộ projection |

### 2.1. Sổ theo dõi query shape

Ví dụ:

| ID | Truy vấn | Input bắt buộc | Mục tiêu giả định | Giải pháp đang có |
| --- | --- | --- | --- | --- |
| Q01 | Tra đơn theo ID | Tenant, order ID | Một hàng, độ trễ thấp | Bảng `orders_by_id` |
| Q02 | Đơn của khách trong tháng | Tenant, customer ID, tháng | 50 hàng, mới nhất trước | Bảng v1 |
| Q03 | Đơn PENDING theo ngày tạo | Tenant, status, ngày | 50 hàng, p95 thấp | **Chưa có đường đọc phù hợp** |
| Q04 | Đơn của khách trong 2 tháng | Tenant, customer ID, khoảng tháng | Có thể chậm hơn Q02 | Fan-out hữu hạn qua 2 bucket |
| Q05 | Tìm từ khóa, giá, status tùy chọn | Tenant và filter động | Sort linh hoạt | Có thể cần search |

Các mức “50 hàng” và SLO trong bài là **giả định minh họa**, không phải cấu hình mặc định của Cassandra.

### 2.2. Metric dùng để quyết định có cần thiết kế lại

- **Read path:** request/s theo query shape, số partition trung bình/đỉnh mỗi request, byte/hàng trả về và byte/hàng đọc trung gian, p50/p95/p99 latency, timeout.
- **Write path:** mutation/s, tỷ lệ update/xóa, số bảng projection, write latency, retry, hotspot trên một partition.
- **Storage:** kích thước partition lớn nhất, số hàng/partition, SSTable mỗi lượt đọc, tombstone scanned, compaction backlog, disk usage.
- **Dữ liệu/khách hàng:** tenant lớn nhất, phân bố số đơn theo trạng thái, mức lệch tải giữa các khóa, retention và tốc độ tăng trưởng.
- **Độ đúng:** projection lag, tỷ lệ dữ liệu thiếu/thừa/cũ, phiên bản nguồn và các sự kiện chưa được xử lý.

Một tenant có 10 khách hàng không giống một tenant có 100.000 khách hàng. Quyết định chỉ dựa trên query chạy nhanh ở dữ liệu mẫu dễ bỏ qua fan-out và hot partition ở quy mô thật.

## 3. Những thay đổi nào đòi cách xử lý khác nhau?

| Dạng thay đổi | Ví dụ | Phương án cần khảo sát |
| --- | --- | --- |
| Thêm cột cần hiển thị | Thêm `delivery_note` cho chi tiết đơn | Có thể thêm regular column, cập nhật writer/reader |
| Thêm filter trên tập đã giới hạn | Lọc severity trong một partition nhỏ | Có thể lọc có chặn, index tương thích hoặc projection |
| Thay partition key truy vấn | Đọc theo tenant/status thay vì customer/tháng | **Bảng mới theo truy vấn**, backfill |
| Thay thứ tự sắp xếp chính | Sort theo thời gian thanh toán thay vì tạo | Bảng/projection mới theo trục tương ứng |
| Partition cũ quá lớn/nóng | Một thiết bị/ngày có hàng triệu event | Bucket nhỏ hơn hoặc shard, rồi di trú |
| Retention thay đổi | Giữ sự kiện 90 thay vì 30 ngày | Xác định tác động TTL cũ, capacity và backfill |
| Truy vấn trở thành tìm kiếm tùy ý | Full-text, nhiều bộ lọc, relevance | Đánh giá search/analytics thay vì vô hạn bảng |
| Tăng số datacenter/RF | Có thêm vùng vận hành | Thiết kế replication/placement/consistency và năng lực cụm, chưa chắc đổi data model |

Không biến mỗi tính năng mới thành một bảng Cassandra mới. Nếu fan-out chỉ qua hai bucket đã biết và ít gọi, đôi khi đọc hai partition rồi hợp nhất là hợp lý hơn. Ngược lại, nếu Q03 là hàng đợi được gọi liên tục, việc quét toàn tenant dù ít hàng trả về vẫn có thể vượt SLA.

### 3.1. Khi `ALTER TABLE` là đủ, và khi không

Thêm một cột **regular column** thường là thay đổi schema khác với đổi primary key:

```sql
-- Ví dụ nếu ứng dụng cần lưu thêm cột hiển thị.
ALTER TABLE orders_by_customer_month_v1
ADD delivery_note text;
```

Tuy nhiên, việc thêm cột **không tạo index mới và không đổi vị trí partition**. Câu sau không tự nhiên trở thành một truy vấn hiệu quả chỉ vì có `delivery_note`:

```sql
-- Minh họa ý định KHÔNG có đường đọc phù hợp từ khóa:
-- SELECT ... FROM orders_by_customer_month_v1
-- WHERE delivery_note = ? AND tenant_id = ?;
```

Quan trọng hơn, **không thể ALTER trực tiếp partition key/clustering key của bảng đã có dữ liệu như đổi một cột thường**. Với thay đổi khóa truy cập, tạo bảng v2 với primary key đúng, chuyển dữ liệu có kiểm chứng và đổi đường đọc; không cập nhật v1 “tại chỗ” rồi kỳ vọng Cassandra tự sắp xếp lại dữ liệu.

## 4. Thiết kế bảng v2 cho mẫu truy cập mới

Với Q03, một ứng viên là:

```sql
CREATE TABLE orders_by_status_created_day_v2 (
    tenant_id text,
    status text,
    created_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, created_day),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Truy vấn mới:

```sql
SELECT created_at, order_id, customer_id, total_amount, revision
FROM orders_by_status_created_day_v2
WHERE tenant_id = ?
  AND status = ?
  AND created_day = ?
LIMIT 50;
```

Đây là một **partition** theo tenant, trạng thái và ngày tạo; clustering cho phép đọc mới nhất trước theo `created_at`, dùng `order_id` làm tie-breaker khi có nhiều đơn cùng millisecond. Không cần tìm customer ID trước và không cần `ALLOW FILTERING`.

### 4.1. Định nghĩa bucket không được mơ hồ

`created_day` trong ví dụ là **ngày UTC của `created_at`**, không phải ngày đơn đổi sang trạng thái hiện tại. Nếu đơn được tạo ngày 21/11 và chuyển `PENDING → PAID` ngày 22/11, hàng `PAID` mới vẫn thuộc partition **ngày tạo 21/11**.

Nếu nghiệp vụ thực sự muốn “các đơn **đã chuyển sang PAID trong ngày 22/11**”, đường truy vấn khác cần dựa trên `status_changed_at` hoặc bảng sự kiện trạng thái, không dùng lại bucket ngày tạo mà bỏ qua khác biệt nghĩa.

Các trường thời gian phải được chuẩn hóa nhất quán trên mọi producer/consumer. `LocalDate` trong Java không mang múi giờ, nên khi suy từ `Instant createdAt` phải chuyển sang **UTC** trước.

### 4.2. Tính chi phí mới trước khi nhận v2

| Phương diện | V1 khách/tháng | V2 status/ngày tạo |
| --- | --- | --- |
| Đường đọc ưu tiên | Một khách và một tháng | Một tenant, một status, một ngày |
| Mỗi đơn mới | Ghi vào v1 | Ghi thêm vào v2 |
| Khi status thay đổi | Cập nhật regular column `status` | Xóa khóa status cũ, ghi khóa status mới |
| Partition có nguy cơ quá lớn | Khách rất nhiều đơn/tháng | Tenant lớn với status phổ biến/ngày |
| Đọc nhiều bucket | Nhiều tháng | Nhiều ngày hoặc shard |
| Nhất quán nghiệp vụ | Cần nguồn trạng thái rõ | Cần duy trì projection, phát hiện stale/orphan |

Nên đo số đơn/tenant/ngày, tỷ lệ thuộc từng status và số lần đổi trạng thái. Nếu `PENDING` chứa hàng triệu đơn của một tenant trong ngày, một partition v2 có thể trở thành điểm nóng dù Q03 chỉ đọc một partition.

### 4.3. Nếu v2 tạo hot partition

Có thể cân nhắc thêm `shard_id`, được tính ổn định từ `order_id`, vào partition key:

```sql
CREATE TABLE orders_by_status_created_day_sharded_v2 (
    tenant_id text,
    status text,
    created_day date,
    shard_id int,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, created_day, shard_id),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Giả sử 16 shard, writer dùng một hàm hash/phiên bản nhất quán để tính `shard_id` từ `order_id`. Q03 cần đọc **tối đa 16 partition**, hợp nhất theo `(created_at DESC, order_id DESC)` và quản lý vị trí phân trang từng shard.

Sharding **giảm tải trên mỗi partition** nhưng tăng fan-out và độ phức tạp. Không chọn số shard theo cảm giác; đo dữ liệu lớn nhất và cân bằng write throughput với SLO đọc. Nếu chưa có hotspot, bảng v2 không shard đơn giản hơn.

## 5. Đừng thay đường đọc trước khi xây được đường ghi mới

Cassandra không tự biết hàng trong v1, bảng theo ID và v2 là các biểu diễn của cùng một order. Muốn thêm v2, cần định nghĩa **nguồn sự thật**, cách phát thay đổi và cơ chế sửa lỗi.

Trong ví dụ, một hàng tra cứu theo ID có thể được ứng dụng dùng làm trạng thái hiện tại đã được chấp nhận:

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    updated_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Đây là **giả định kiến trúc của ví dụ**, không phải Cassandra tự đảm bảo trạng thái nguồn có một writer. Ứng dụng phải quy định ai được cấp `revision`, transition nào hợp lệ, xử lý cập nhật cạnh tranh ra sao và làm thế nào phát lại sự kiện đã chấp nhận.

### 5.1. Khi tạo một đơn

Một order mới được tạo ra có thể tạo ba biểu diễn:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    current_status, total_amount, updated_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month_v1 (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_created_day_v2 (
    tenant_id, status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

`month_bucket` và `created_day` phải được suy từ **cùng `created_at` UTC đã được công nhận**, không phải lấy “thời điểm hiện tại” ở mỗi consumer. Nếu một thao tác thất bại ở giữa, các bảng có thể không khớp cho tới khi retry hoặc đối soát.

### 5.2. Khi order đổi trạng thái

Với transition `PENDING → PAID` đã được nguồn chấp nhận:

1. Lưu trạng thái/revision mới ở nguồn theo quy tắc kiểm soát cạnh tranh.
2. Cập nhật `status` và `revision` trong v1 vì đó là regular column.
3. **Xóa hàng** v2 ở partition `(tenant,PENDING,created_day)` với đầy đủ khóa.
4. **Ghi hàng** v2 ở partition `(tenant,PAID,created_day)` với đầy đủ khóa.

Hai mutation v2:

```sql
DELETE FROM orders_by_status_created_day_v2
WHERE tenant_id = ?
  AND status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;

INSERT INTO orders_by_status_created_day_v2 (
    tenant_id, status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

Giá trị `status` trong `DELETE` là **status cũ**, trong `INSERT` là **status mới**. Một lần đổi status thực sự làm hàng **di chuyển giữa partition keys**. Xóa thường tạo tombstone, làm tăng công việc compaction và chi phí đọc khi có nhiều lần chuyển trạng thái.

Các mutation này **không tạo một transaction SQL xuyên bảng/partition**. API có thể nhìn thấy một phần thay đổi trong thời gian đồng bộ. Cần SLO độ trễ projection và quy trình phục hồi khi một thao tác thất bại.

## 6. Phiên bản, thứ tự sự kiện và nguồn thay đổi bền vững

Chỉ ghi v1 và v2 song song rồi giả định chúng luôn nhất quán là rủi ro. Hãy xem trường hợp:

```text
Order O-1, revision 11: PENDING
Order O-1, revision 12: PAID

Consumer xử lý rev 12 trước:
  xóa PENDING, thêm PAID ở v2.

Sau đó retry rev 11 đến muộn:
  nếu ghi vô điều kiện có thể tái tạo PENDING,
  hoặc làm trạng thái ở bảng nguồn/v1 lùi về bản cũ.
```

Việc có cột `revision` trong mỗi row **không tự ngăn** Cassandra chấp nhận mutation cũ. Các giá trị cell thông thường tuân theo quy tắc giải quyết xung đột theo timestamp ghi; revision là dữ liệu nghiệp vụ phải được **kiểm tra và áp dụng bằng một thuật toán riêng**.

Một thiết kế có thể kết hợp:

- **Một nguồn quyết định transition:** chỉ có thay đổi đã được chấp nhận mới phát sang projection.
- **Revision/sequence tăng theo mỗi order:** dùng để nhận diện trạng thái mới nhất, phát hiện retry và xử lý tranh chấp.
- **Sự kiện có ID ổn định:** cùng một transition dùng cùng `event_id` khi replay.
- **Luồng sự kiện bền vững:** event log/outbox/CDC với hợp đồng rõ, có checkpoint và khả năng replay khi consumer chết.
- **Xử lý tuần tự theo order ID** hoặc cơ chế kiểm tra version đủ mạnh khi đồng bộ các projection; không để job backfill rev cũ ghi đè live rev mới.
- **Đối soát định kỳ:** phát hiện hàng thiếu, cũ, thừa và sửa theo nguồn.

### 6.1. LWT kiểm soát gì?

Nếu hàng nguồn có `revision`, ứng dụng có thể dùng lightweight transaction (LWT/CAS) cho **một hàng nguồn** trong tình huống cần điều kiện:

```sql
-- Chỉ minh họa cho hàng nguồn đã tồn tại.
UPDATE orders_by_id
SET current_status = ?,
    updated_at = ?,
    revision = ?
WHERE tenant_id = ?
  AND order_id = ?
IF revision = ?;
```

Caller phải kiểm tra `[applied]`, xác nhận `nextRevision` hợp lệ và xử lý tranh chấp. LWT có thêm chi phí điều phối; không dùng mặc định nếu không cần. **LWT của bảng nguồn không tự tạo giao dịch cách ly qua các partition v1/v2**.

### 6.2. Logged batch không thay thế pipeline

Logged batch có thể giúp các mutation trong batch cuối cùng được áp dụng theo ngữ nghĩa batch khi phục hồi lỗi, nhưng **không bảo đảm cách ly đọc xuyên partition như transaction quan hệ** và không kiểm tra revision cũ/mới. Batch nhiều partition còn có thể tăng tải coordinator/batchlog; không dùng nó làm mẹo tăng throughput hoặc thay thế sự kiện bền vững/reconciliation.

Replication factor và consistency level như `LOCAL_QUORUM` (với topology phù hợp) liên quan đến **số replica xác nhận mỗi mutation**. Nếu event chưa được consumer gửi sang v2 thì tăng consistency level khi đọc v2 không thể tự sinh ra hàng bị thiếu.

## 7. Kế hoạch migration nhiều giai đoạn

Một kế hoạch chuyển đổi an toàn thường phải đảm bảo **v1 vẫn phục vụ query cũ** trong lúc v2 được tạo và làm đầy. Tên bảng v2 giúp triển khai song song, kiểm thử và rollback dễ hơn so với sửa dữ liệu tại chỗ.

| Giai đoạn | Công việc | Điều kiện hoàn thành |
| --- | --- | --- |
| P0. Đo và xác định hợp đồng | Ghi query shapes, SLO, tải, dữ liệu lớn nhất | Biết rõ vấn đề cần giải quyết |
| P1. Thiết kế v2 | Chốt partition/clustering, TTL, bucket, sharding và schema | Test CQL hợp lệ và mô hình tải chấp nhận được |
| P2. Bảo đảm live changes | Xây nguồn sự kiện bền vững, writer/consumer v2 và retry | Không bỏ mất mutation đã chấp nhận |
| P3. Backfill | Nạp dữ liệu cũ theo lô có checkpoint, không làm hỏng dữ liệu mới | Có độ bao phủ và watermark rõ |
| P4. Đối soát/shadow-read | So kết quả với nguồn, đo sai lệch và độ trễ | Invariant đúng trong SLO |
| P5. Canary và chuyển traffic | Bật v2 cho ít người/tenant rồi tăng dần | KPI lỗi/latency/correctness đạt ngưỡng |
| P6. Quan sát ổn định | Giữ v1 và khả năng rollback trong cửa sổ đã định | Không có sai lệch, lag hoặc chi phí bất thường |
| P7. Ngừng dùng v1 | Dừng đường ghi cũ khi hết consumer, lưu/chuyển dữ liệu theo chính sách | Có phê duyệt dọn dữ liệu và phương án phục hồi |

Không bỏ qua P2 rồi làm P3: nếu backfill kéo dài nhiều giờ trong khi đơn mới tiếp tục được ghi, v2 sẽ thiếu thay đổi phát sinh trong thời gian đó nếu không có cách bắt và phát lại chúng.

### 7.1. Giữ trạng thái migration rõ ràng

Ví dụ các trạng thái vận hành cho **đường đọc mới Q03**:

```text
SCHEMA_CREATED
  -> LIVE_SYNC_ENABLED
  -> BACKFILL_RUNNING
  -> RECONCILED
  -> SHADOW_READ
  -> CANARY
  -> V2_PRIMARY_READ
  -> V1_RETIRE_ELIGIBLE
```

Đây là các **trạng thái quy trình**, không phải bảng CQL bắt buộc. Nên ghi trạng thái rollout theo tenant hoặc phạm vi đã chọn, cùng thời điểm, người chịu trách nhiệm, metric và cách rollback. Một hệ thống nhiều tenant có thể canary theo tenant, nhưng **không** bật v2 cho tenant chưa được backfill/đối soát đủ.

## 8. Backfill mà không ghi đè dữ liệu mới

Backfill là quá trình tạo projection v2 cho dữ liệu đã tồn tại trước khi v2 nhận lưu lượng. Bài toán khó là dữ liệu nguồn vẫn thay đổi đồng thời.

### 8.1. Chọn nguồn có thể duyệt

Trong ví dụ, `orders_by_id` cho phép tra từng order khi biết `(tenant_id, order_id)`, nhưng bản thân bảng đó **không tạo một API rẻ để lấy toàn bộ order ID của tenant**. Vì vậy, backfill cần nguồn có thể duyệt đã được thiết kế: durable event log đủ lịch sử, export/snapshot/manifest tạo bằng công cụ bảo trì có kiểm soát hoặc hệ ETL sẵn có.

Không thực hiện `SELECT * FROM orders_by_id` trên API sản xuất rồi kỳ vọng đó là đường truy cập theo tenant rẻ. Với dataset lớn, việc scan/export có thể cần tooling và kế hoạch riêng, có quota để không ảnh hưởng tải giao dịch.

### 8.2. Cửa sổ thay đổi đang diễn ra

Ví dụ timeline:

```text
10:00:00  Bắt đầu ghi thay đổi live vào durable log.
10:00:10  Chốt checkpoint/watermark để backfill.
10:00:20  Nạp bản ghi cũ theo các manifest có giới hạn.
10:05:00  Một order đang backfill chuyển PENDING -> PAID.
10:10:00  Consumer live đã ghi PAID rev 20 vào v2.
10:11:00  Job backfill cũ còn giữ snapshot PENDING rev 18.
```

Nếu job backfill ghi PENDING rev 18 vào v2 lúc 10:11, nó có thể **tái tạo hàng trạng thái cũ** sau khi consumer đã áp dụng rev 20. Chỉ lưu cột `revision=18` trong hàng cũ không tự ngăn việc đó.

Cần một **giao thức có thể chứng minh thứ tự**, chẳng hạn:

1. Thu thập thay đổi bền vững từ trước checkpoint đủ bao phủ.
2. Nạp snapshot có watermark xác định.
3. Áp dụng lại những thay đổi sau watermark theo thứ tự **mỗi order** và dedupe bằng event ID/revision.
4. Bảo đảm worker backfill và live consumer không đồng thời ghi một phiên bản cũ vào những khóa trạng thái đã được phiên bản mới xử lý.
5. Đối soát bản cuối với nguồn hiện hành trước khi cho phép đọc sản xuất.

Tùy kiến trúc, có thể dùng **hàng đợi tuần tự theo order**, barrier/cutover watermark, một executor sở hữu order hoặc chiến lược chuyển quyền writer sau snapshot. Một snapshot không nhất quán cộng với replay thiếu watermark có thể để lại khoảng mất dữ liệu; phải kiểm chứng cơ chế ở hệ thống thực tế.

### 8.3. Tại sao chỉ dùng COUNT(*) là chưa đủ?

Giả sử v2 có cùng số đơn với nguồn nhưng thiếu order A và thừa order B. Tổng số lượng bằng nhau vẫn không chứng minh dữ liệu đúng. Hãy so:

- Tập khóa `(tenant, order_id)` được kỳ vọng theo manifest.
- `status`, `customer_id`, `created_at`, `revision` và giá trị hiển thị.
- Khóa partition mới được tính đúng theo UTC.
- Hàng trạng thái cũ đã bị xóa khi status chuyển.
- Dữ liệu nằm trong/ngoài retention theo chính sách.

Đối soát nên dùng batch ID có giới hạn và query theo **đầy đủ primary key**, không dựa vào full table scan ở request người dùng.

### 8.4. Retention khi backfill

Nếu một bảng v2 lưu lịch sử với TTL, đừng ghi lại toàn bộ dữ liệu cũ bằng TTL cố định mới rồi vô tình **kéo dài thời hạn lưu**. Ví dụ retention là 30 ngày từ `event_time`: event đã 28 ngày tuổi chỉ còn khoảng 2 ngày; event đã quá hạn cần được xử lý theo chính sách, không nhập lại với 30 ngày mới.

Nếu v2 là bảng trạng thái hiện tại của đơn, retention có thể khác lịch sử sự kiện; cần chốt riêng vòng đời của từng bảng. Những bảng có TTL/xóa nhiều còn tạo tombstone và ảnh hưởng compaction. Backfill có thể tạo tải ghi/SSTable lớn, cần giới hạn QPS và disk headroom.

## 9. Đối soát theo invariant, không chỉ theo cảm tính

Trong kịch bản này, chọn `orders_by_id` là nguồn trạng thái cuối cùng đã được chấp nhận, còn v1/v2 là các projection. Với một order `O`, các invariant **sau khi đã hội tụ** có thể là:

| ID | Bất biến |
| --- | --- |
| I1 | `orders_by_id` có revision và current status theo nguồn nghiệp vụ |
| I2 | V1 có đúng hàng khách/tháng của O và regular column `status/revision` khớp nguồn |
| I3 | V2 có đúng hàng trong partition `(tenant,current_status,created_day)` và revision khớp nguồn |
| I4 | Hàng ở partition **status cũ** của O không còn tồn tại sau khi transition đã hội tụ |
| I5 | Những hàng đã hết retention không bị job backfill/repair tạo lại trái chính sách |

Để so I4, không thể tra `order_id` trên toàn bộ mọi partition status/day một cách rẻ trong schema v2. Cần có **old_status** từ durable event, manifest hoặc tập khóa cũ được ghi có chủ đích.

### 9.1. CQL đối chiếu một hàng v2 bằng đầy đủ khóa

```sql
SELECT customer_id, total_amount, revision
FROM orders_by_status_created_day_v2
WHERE tenant_id = ?
  AND status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;
```

Với nguồn:

```sql
SELECT customer_id, created_at, current_status,
       total_amount, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

Job đối soát phải tính `created_day` từ `created_at` UTC và dùng status hiện tại được chấp nhận. Khi phát hiện revision ở v2 thấp hơn nguồn, không tự ghi một mutation cũ: cần xác minh nguồn vẫn hiện hành và dùng cơ chế ghi tuần tự/kiểm soát version. Nếu trong lúc job xử lý nguồn chuyển revision mới, chính job cũ có thể gây lỗi nếu không có barrier hoặc cơ chế phát hiện tranh chấp.

### 9.2. Phân loại và khắc phục sai lệch

| Loại | Triệu chứng | Hành động |
| --- | --- | --- |
| `MISSING` | Nguồn PAID nhưng v2 thiếu hàng PAID | Tạo lại hàng đúng khóa và version hiện hành |
| `STALE` | V2 có PAID nhưng revision thấp, cột hiển thị cũ | Cập nhật theo nguồn mới, tránh ghi lùi |
| `ORPHAN` | V2 còn PENDING sau khi nguồn PAID | Xác minh old key từ event log rồi xóa |
| `DUPLICATE_LOGICAL` | Cùng order có hàng ở nhiều status do replay | Dựa trên source/manifest để giữ hàng hiện hành, dọn hàng cũ |
| `IN_FLIGHT` | Event vừa chấp nhận, chưa hết SLO cập nhật | Chờ trong cửa sổ cho phép và theo dõi lag |
| `EXPIRED_EXPECTED` | Không có hàng vì đã hết TTL đúng chính sách | Không khôi phục trái chính sách lưu trữ |

**Repair của Cassandra** giúp đồng bộ dữ liệu giữa các replica, không biết rằng ứng dụng bỏ sót lệnh xóa PENDING trong một bảng khác. Reconciliation nghiệp vụ là lớp riêng, cần retry và khả năng tái chạy an toàn.

## 10. Shadow read, canary và chuyển đường đọc

Sau khi backfill và đối soát, vẫn nên thử trên lưu lượng thực tế có giới hạn trước khi chuyển toàn bộ.

### 10.1. Shadow read có mục đích

Đối với Q03, **v1 không có đường đọc tương đương** để so trực tiếp trong một request. Không nên tạo hàng nghìn truy vấn v1 chỉ để “đối chứng”. Có thể:

- Chạy Q03 trên v2 nhưng **không trả kết quả đó cho người dùng** trong giai đoạn shadow.
- Chọn mẫu ID từ kết quả và đọc `orders_by_id` để xác nhận status, customer, ngày tạo, revision.
- Đối chiếu danh sách expected keys từ manifest/event log đối với tenant/ngày mục tiêu.
- Đo latency, số partition, số hàng trả về, tỷ lệ stale/missing và tài nguyên của v2.

Nếu có một query shape mà cả v1 và v2 cùng hỗ trợ, có thể so hai kết quả sau khi chuẩn hóa thứ tự, giới hạn và độ mới; nhưng **không giả định** chúng tương đương khi partition key/ý nghĩa bucket khác nhau.

### 10.2. Canary có tiêu chí dừng

Ví dụ quy trình:

1. Cho phép Q03 đọc từ v2 ở tenant nội bộ hoặc một nhóm tenant đã được xác minh đầy đủ.
2. Giới hạn concurrency, page size và thời gian truy vấn; bật cảnh báo p95/p99 và timeout.
3. Kiểm tra tỷ lệ bản ghi sai, lag v2, tombstone và node nóng.
4. Nếu vượt ngưỡng, **tắt đường đọc v2** bằng cấu hình/feature flag; không tự fallback thành scan v1 trên toàn tenant.
5. Khi các ngưỡng ổn định qua khoảng quan sát đã thống nhất, mở rộng tỉ lệ tenant.

Đối với các truy vấn cũ Q01/Q02, tiếp tục dùng bảng đã phục vụ tốt chúng cho tới khi có lý do và kế hoạch di trú riêng. Bổ sung v2 cho Q03 **không có nghĩa phải bỏ v1 ngay**.

### 10.3. Theo dõi metric trong giai đoạn chuyển

| Nhóm | Metric |
| --- | --- |
| Trải nghiệm API | p50/p95/p99, timeout, tỷ lệ lỗi, page size thực tế |
| Độ mới | Projection lag, tuổi event chưa áp dụng, backlog và dead-letter |
| Đúng dữ liệu | Missing/stale/orphan, revision mismatch, tỷ lệ đối soát thành công |
| Tải Cassandra | Read/write QPS per table, tombstone scanned, hot partition, SSTables per read |
| Lưu trữ | Disk used, compaction backlog, headroom cho repair/streaming/backfill |
| Rollout | Tỷ lệ tenant bật v2, tenant đã reconcile, số request bị giới hạn |

Khi đánh giá, xem **node nóng nhất** và **tenant lớn nhất**, không chỉ trung bình cluster. Một partition status/day của tenant lớn có thể làm chậm một số replica dù toàn cụm còn nhiều tài nguyên.

## 11. Java: tách đường đọc cũ và mới bằng hợp đồng rõ ràng

Ví dụ dùng **DataStax Java Driver 4.x**. Ứng dụng giữ query cũ theo customer/month, thêm query mới theo status/day. Router hoặc feature flag ở tầng service chỉ bật Q03 sau khi tenant đã hoàn thành backfill/đối soát; đoạn code không tự bật v2 cho mọi tenant.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.UUID;

public final class MigratingOrderQueries {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement customerMonthV1;
    private final PreparedStatement statusDayV2;

    public MigratingOrderQueries(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, current_status, total_amount, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.customerMonthV1 = session.prepare(
            "SELECT order_id, created_at, status, total_amount, revision " +
            "FROM orders_by_customer_month_v1 " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "LIMIT 50"
        );
        this.statusDayV2 = session.prepare(
            "SELECT order_id, created_at, customer_id, total_amount, revision " +
            "FROM orders_by_status_created_day_v2 " +
            "WHERE tenant_id = ? AND status = ? AND created_day = ? " +
            "LIMIT 50"
        );
    }

    public Row getById(String tenantId, UUID orderId) {
        return session.execute(byId.bind(tenantId, orderId)).one();
    }

    public ResultSet customerOrders(
        String tenantId, UUID customerId, YearMonth utcMonth
    ) {
        return session.execute(
            customerMonthV1.bind(tenantId, customerId, utcMonth.toString())
        );
    }

    // Gọi khi tenant đã được cấp phép đọc v2 trong quy trình rollout.
    public ResultSet ordersByStatusForCreatedDay(
        String tenantId, String status, LocalDate utcCreatedDay
    ) {
        BoundStatement bound = statusDayV2.bind(
            tenantId, status, utcCreatedDay
        ).setPageSize(50);
        return session.execute(bound);
    }

    public static LocalDate createdDayUtc(Instant createdAt) {
        return createdAt.atZone(ZoneOffset.UTC).toLocalDate();
    }
}
```

Những giới hạn phải xử lý ngoài ví dụ:

- `tenantId` phải đến từ ngữ cảnh được xác thực/ủy quyền, không tin một giá trị do client tự khai. Mỗi lần shadow read/reconcile cũng phải kiểm soát tenant.
- `YearMonth` không có múi giờ; chỉ tạo từ `Instant` đã quy đổi UTC. `LocalDate` ánh xạ CQL `date`, `Instant` ánh xạ `timestamp` và `UUID` ánh xạ `uuid`.
- `LIMIT 50` là **giới hạn tổng số hàng** của câu CQL. `setPageSize(50)` là mục tiêu trang của driver, không cung cấp vô hạn trang mới nếu câu truy vấn đã bị giới hạn 50 hàng.
- Để hỗ trợ “tải thêm” không giới hạn một trang preview, dùng câu CQL phù hợp **không cố định `LIMIT 50`**, cùng paging state opaque gắn với query shape và bind values. Không tái sử dụng cursor cho tenant, status hoặc ngày khác.
- `ResultSet` đồng bộ có thể tải trang tiếp theo khi lặp toàn bộ; endpoint chỉ trả một trang phải giới hạn việc tiêu thụ dữ liệu.
- API Q03 **không nên** fallback sang quét v1 khi v2 chưa sẵn sàng: thay vào đó tạm thời ẩn chức năng, giới hạn tenant, hoặc cung cấp hành vi suy giảm đã được sản phẩm phê duyệt.

### 11.1. Tính byte và giới hạn tải trong Java

Khi bật v2, Java service cần hạn mức rõ: status hợp lệ, ngày không vượt retention, kích thước trang và concurrency. Ví dụ logic khái niệm:

```text
authorize(tenant, user)
validate(status, createdDay)
assert rolloutState(tenant) >= RECONCILED
assert request.pageSize <= configuredMax
execute v2 prepared query
record: latency, returnedRows, tenant, status, createdDay, projectionLag
```

Các phép kiểm này là trách nhiệm của service, không được thực thi chỉ nhờ định nghĩa partition key. Với yêu cầu nhiều ngày, cần fan-out có giới hạn và hợp nhất; một truy vấn một ngày không tự tạo thứ tự toàn cục.

## 12. Rollback và dọn bảng cũ

Rollback cần được thiết kế **trước canary**:

- Nếu Q03 lỗi, tắt tính năng Q03/v2 cho tenant bị ảnh hưởng; **không phá v1** chỉ vì v2 chưa đạt.
- Nếu writer v2 lỗi, giữ sự kiện bền vững và backpressure/retry; có thể dừng consumer v2, nhưng không xóa nguồn sự thật.
- Nếu phát hiện backfill sai, có thể làm sạch/rebuild **v2 theo kế hoạch**, không dùng thao tác phá dữ liệu trực tiếp trên v1.
- Nếu đã ngừng ghi v1 rồi muốn rollback Q02, cần có **kế hoạch bắt kịp v1** trước khi trả traffic cũ; một bảng đã bị bỏ cập nhật không thể tự trở thành nguồn đọc đúng chỉ vì bật feature flag.

### 12.1. Khi nào được bỏ v1?

Chỉ xem xét sau khi:

1. Đã xác nhận mọi query shape phụ thuộc v1 có đường thay thế hoặc đã bị loại bỏ có chủ đích.
2. Các client/service, job export, dashboard và consumer được kiểm kê không còn đọc v1.
3. Rollback window đã hết, dữ liệu cần giữ và chính sách backup/retention được phê duyệt.
4. Ngừng writer v1 có kiểm soát, giám sát lỗi và chứng minh không còn traffic hợp lệ.
5. Có kế hoạch thao tác xóa với dung lượng/compaction/snapshot phù hợp.

Không tự coi `DROP TABLE` là một bước luôn an toàn hoặc ngay lập tức giải phóng toàn bộ dung lượng. Cần thực hiện theo chính sách backup, quyền truy cập, replication và quy trình vận hành của cụm.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đổi màn hình nhưng không đo query shape | Tạo thêm bảng vô ích hoặc bỏ sót truy vấn chủ đạo | Inventory + tần suất/SLO/fan-out trước |
| Cố `ALTER` partition key của bảng v1 | Không có cơ chế chuyển khóa hiện có tự động | Tạo v2 và di trú có kiểm chứng |
| Tạo v2 rồi chuyển read ngay | Thiếu dữ liệu trước thời điểm v2 nhận live changes | Backfill, đối soát, shadow/canary |
| Chạy backfill trong lúc live update nhưng không có watermark | Bản cũ ghi đè mới hoặc thiếu event trong khoảng chuyển | Durable log, checkpoint/barrier và per-key ordering |
| Chỉ lưu cột `revision` mà không kiểm tra | Retry revision cũ vẫn có thể tạo hàng sai | Sequencer/CAS phù hợp và reconciliation |
| Chỉ ghi status mới, quên xóa status cũ | Order có mặt ở hai hàng đợi | Lưu old key và xóa với đầy đủ primary key |
| Dùng `LOCAL_QUORUM` để giải quyết v2 chưa cập nhật | Mutation chưa gửi thì replica không biết | Theo dõi projection lag và retry pipeline |
| Dùng logged batch như transaction SQL | Độc giả có thể thấy cập nhật từng phần | Hiểu giới hạn atomicity/isolation |
| V2 key theo tenant/status/day không đo tải tenant lớn | Hot partition, latency bất thường | Benchmark max partition, bucket/shard nếu cần |
| Di trú TTL bằng TTL mới đầy đủ | Dữ liệu cũ được kéo dài retention | Tính TTL còn lại theo hợp đồng |
| Shadow read bằng quét hàng nghìn partition v1 | Tăng tải trên production | So với nguồn/manifest theo mẫu có giới hạn |
| Canary không có đường rollback | Sự cố ảnh hưởng tất cả tenant | Feature flag, tiêu chí dừng, giữ đường cũ đúng |
| Xóa v1 trước khi kiểm kê consumer | API cũ hỏng, khó khôi phục | Kiểm kê, dừng ghi/đọc và dọn theo giai đoạn |
| Tưởng repair tự sửa projection sai | V2 vẫn thiếu mutation do ứng dụng | Reconciliation nghiệp vụ riêng |

## 14. Checklist hoàn thành một lần thiết kế lại

| Câu hỏi | Bằng chứng đạt |
| --- | --- |
| Lý do đổi schema là gì? | Có query shape mới hoặc metric chứng minh schema cũ không đáp ứng |
| Mẫu cũ vẫn cần không? | Đã liệt kê các API/consumer v1 và chiến lược tiếp tục hỗ trợ |
| V2 có key đúng không? | CQL chạy với toàn bộ partition key và clustering phục vụ sort/range |
| Có hot partition không? | Kiểm thử tenant/device lớn nhất, byte/hàng, p95/p99 và peak write |
| Chi phí ghi mới là bao nhiêu? | Có số mutation tạo/sửa/xóa, RF, index, tombstone và headroom |
| Có source of truth không? | Revision và transition được chấp nhận theo quy tắc rõ |
| Có durable changes không? | Có log/CDC/outbox với khả năng replay, checkpoint, dedupe |
| Backfill có thể tiếp tục khi lỗi không? | Lô nhỏ, quota, watermark, idempotency, không ghi lùi |
| Có invariant đối soát không? | So source, v1, v2 và old status keys theo manifest |
| Có chính sách TTL đúng không? | Dữ liệu cũ không bị tái tạo quá thời hạn, compaction được tính |
| Shadow/canary có đo đủ không? | Độ trễ, lag, sai lệch, hotspot, timeout và ngưỡng dừng |
| Rollback có khả thi không? | Feature flag và đường dữ liệu còn đúng khi quay lại |
| Có kế hoạch dọn v1 không? | Kiểm kê consumer, retention, backup và phê duyệt vận hành |

## 15. Bài tập thực hành

Một dịch vụ Java ghi lịch sử quét mã kiện hàng trong Cassandra. Ban đầu API chỉ hỏi “50 lần quét mới nhất của một kiện trong một ngày UTC”, nên bảng:

```sql
CREATE TABLE parcel_scans_by_parcel_day_v1 (
    tenant_id text,
    parcel_id uuid,
    day_bucket date,
    scanned_at timestamp,
    scan_id uuid,
    location_id uuid,
    scan_status text,
    PRIMARY KEY ((tenant_id, parcel_id, day_bucket),
                 scanned_at, scan_id)
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id DESC);
```

Sau sáu tháng, đội vận hành cần thêm:

- **R1:** 100 lần quét gần nhất tại **một địa điểm trong một giờ UTC**, trên mọi kiện hàng.
- **R2:** Vẫn đọc lịch sử một kiện/ngày từ v1.
- **R3:** Một thiết bị quét cực nóng tạo 80 event/giây, và địa điểm lớn nhất có rất nhiều kiện.
- **R4:** Sự kiện có thể đến muộn một ngày; dữ liệu được giữ 14 ngày tính từ `scanned_at`.
- **R5:** API mới phải được triển khai dần, không ảnh hưởng màn hình cũ.

**Yêu cầu:**

1. Giải thích vì sao v1 không trực tiếp phục vụ R1 dù chứa `location_id`, và vì sao `LIMIT 100` không giải quyết việc thiếu partition key.
2. Đề xuất tên bảng v2, partition key/clustering key cho `(tenant, location, hour_bucket)`; viết CQL `CREATE TABLE` và `SELECT` cho R1.
3. Với một địa điểm cực lớn, khi nào cần bucket ngắn hơn hoặc shard? Nếu có 8 shard, reader cần thay đổi thế nào?
4. Xác định cách tính `hour_bucket` UTC từ `scanned_at` và TTL còn lại khi một event đến muộn một ngày.
5. Trình bày ít nhất **bảy bước** chuyển từ v1 sang v2: live changes, nguồn backfill, watermark, replay, shadow read, canary, rollback và đối soát.
6. Nếu event revision 5 đã được ghi ở v2 rồi job backfill ghi revision 4, rủi ro là gì? Việc có cột `revision` có tự chặn lỗi không?
7. Nêu ba invariant để kiểm tra v2 theo nguồn sự kiện, và hai metric để quyết định có thể chuyển traffic.

**Gợi ý đối chiếu:** R1 cần đường đọc theo địa điểm/giờ, ví dụ `PRIMARY KEY ((tenant_id, location_id, hour_bucket), scanned_at, scan_id)`, clustering giảm dần. V1 theo kiện/ngày vẫn được giữ cho R2. Với địa điểm nóng, đo partition lớn nhất và peak writes rồi cân nhắc shard có số lượng cố định; đọc tất cả shard cần merge theo `scanned_at DESC, scan_id DESC`. Bucket theo `scanned_at` UTC, retention 14 ngày từ thời điểm xảy ra, nên event đến muộn một ngày chỉ còn khoảng **13 ngày TTL** khi ghi. Để di trú, cần nguồn sự kiện có thể duyệt, đồng bộ live bền vững, checkpoint/watermark, backfill có giới hạn, chặn revision cũ, đối soát khóa/giá trị, shadow và canary theo tenant/địa điểm. Chỉ cột revision không tự ngăn update sai thứ tự; consumer/worker phải áp dụng quy tắc version thực sự.

## Kết luận

Trong Cassandra, thay đổi mẫu truy cập là tín hiệu **đánh giá lại đường định vị partition và thứ tự clustering**, không chỉ tối ưu một câu `SELECT`. Khi khóa truy cập cũ không phục vụ yêu cầu mới, cách tiếp cận an toàn thường là **thiết kế bảng v2 theo query shape, duy trì nguồn thay đổi bền vững, backfill có kiểm soát, đối soát và chuyển đường đọc từng bước**. Đồng thời phải giữ được truy vấn cũ, xử lý đúng TTL, sự kiện đến sai thứ tự, hot partition và lỗi từng phần. Một lần thiết kế lại thành công không chỉ là CQL v2 chạy được, mà là dữ liệu đúng sau hội tụ, SLA được đo trên tải thật và có đường rollback rõ ràng.
