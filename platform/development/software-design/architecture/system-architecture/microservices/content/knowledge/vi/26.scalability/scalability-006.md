# Xử lý điểm nóng và phân bố không đều theo khóa nghiệp vụ

Một hệ thống microservices có thể chạy hàng chục instance, nhiều partition và nhiều shard nhưng vẫn chậm khi một **khóa nghiệp vụ** nhận phần lớn lưu lượng. Ví dụ: hàng triệu người xem cùng một sản phẩm giảm giá, một người bán lớn tạo phần lớn đơn hàng, một tenant gửi đa số request, hoặc mọi sự kiện cho một tài khoản cùng đi vào một partition của message broker. Đây là hiện tượng **hot key / hot partition / skewed workload**: tải không chia đều trên các đơn vị xử lý, nên tăng tài nguyên tổng thể chưa chắc tăng được thông lượng hữu dụng.

Bài học này tập trung vào cách nhận diện, đo lường và xử lý điểm nóng theo khóa nghiệp vụ trong kiến trúc microservices. Trọng tâm không chỉ là phân tán thêm request, mà còn bảo vệ những bất biến như **không bán vượt tồn kho, không nhân đôi thanh toán, giữ thứ tự sự kiện khi cần, không để một tenant gây nghẽn các tenant khác**.

Các ví dụ mô phỏng nền tảng thương mại điện tử gồm Catalog, Inventory, Order, Payment và Analytics. Mọi số liệu về tải và ngưỡng bên dưới mang tính minh họa; khi áp dụng thật phải dựa trên SLO, benchmark và ranh giới nhất quán của hệ thống.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích tại sao hashing đều trên số lượng khóa **không đồng nghĩa** tải đều khi tần suất truy cập mỗi khóa khác nhau.
- Phân biệt **hot read**, **hot write**, **hot row**, **hot tenant**, **hot shard**, **hot partition** và nghẽn do thứ tự xử lý.
- Chọn metric và cách phân tích phân bố lưu lượng theo key, partition, shard, consumer và tenant.
- Xác định giới hạn của autoscaling/horizontal scaling khi mọi request của một key phải đi qua một đơn vị tuần tự.
- So sánh caching, replication, request coalescing, rate limiting, batching, bucketing, salting, virtual shards và thiết kế lại aggregate boundary.
- Thiết kế phương án tách điểm nóng mà vẫn duy trì idempotency, ordering, transaction và reconciliation.
- Viết kiểm thử phân bố tải có skew, kiểm tra dữ liệu cuối và vận hành migration/rollback an toàn.

## 2. Điểm nóng là gì?

Một **khóa nghiệp vụ** (business key) là giá trị dùng để định tuyến hoặc nhóm dữ liệu theo nghiệp vụ: `productId`, `orderId`, `merchantId`, `accountId`, `tenantId`, `campaignId` hoặc `customerId`.

Trong hệ thống phân tán, khóa đó có thể quyết định nơi xử lý:

~~~text
HTTP requests ------------> route theo tenantId
Cache get -----------------> cache key productId
DB queries ----------------> shard theo merchantId
Message events ------------> Kafka partition theo orderId
Counter updates -----------> row theo productId
~~~

**Điểm nóng** xuất hiện khi một khóa hoặc một nhóm khóa nhỏ gây tải vượt khả năng của nơi đang giữ/trực tiếp xử lý chúng. Không phải điểm nóng nào cũng có lượng request lớn; một key thực hiện thao tác rất đắt (lock lâu, truy vấn nặng, payload lớn) cũng có thể làm nghẽn tài nguyên.

Ví dụ Catalog có 10.000 sản phẩm nhưng 60% lượt xem tập trung vào một sản phẩm đang livestream. Một thuật toán hash có thể chia 10.000 mã sản phẩm tương đối đều trên 16 shard, nhưng **60% lưu lượng đọc** vẫn đổ vào đúng shard chứa sản phẩm đó nếu hệ thống chỉ dùng `hash(productId)` để chọn shard.

~~~text
Product A (60% requests) ----> Shard 03 [HOT]
Product B (5%) -------------> Shard 09
Product C (4%) -------------> Shard 11
... nhiều sản phẩm nhỏ -----> Các shard còn lại
~~~

Chia khóa đều về **số lượng** không bảo đảm chia đều về **trọng số công việc**.

## 3. Phân bố đều lý tưởng và phân bố thực tế

Giả sử dịch vụ nhận 12.000 request/giây và có 12 partition. Nếu mọi partition có công việc tương đương, mỗi partition nhận khoảng:

~~~text
12.000 / 12 = 1.000 request/giây
~~~

Nhưng khi một key chiếm 50% tổng request và được map về partition số 4:

~~~text
Partition 4:
  6.000 request/giây từ hot key
  + một phần request khác

11 partition còn lại:
  chia phần tải còn lại theo phân bố tương ứng
~~~

Ngay cả khi mỗi partition chỉ xử lý ổn định được 2.000 request/giây, partition số 4 vẫn quá tải; các partition khác có thể nhàn rỗi. Đó là lý do tăng từ 12 lên 24 partition chưa chắc khắc phục được: **tất cả message có cùng key vẫn đi tới một partition theo chính sách partitioner**.

Trong thực tế, tần suất truy cập thường có đuôi dài (heavy-tail): một số rất ít key chiếm tỉ lệ lưu lượng lớn, rất nhiều key chỉ được truy cập ít lần. Đôi khi mô hình Zipf được dùng để sinh workload thử nghiệm, nhưng không nên giả định dữ liệu production luôn tuân theo một phân phối lý thuyết cố định.

### Các khái niệm cần phân biệt

| Thuật ngữ | Diễn giải | Ví dụ |
|---|---|---|
| Hot key | Một key phát sinh tải cao bất thường | `productId=flash-sale-42` |
| Hot row | Một dòng DB bị cập nhật/lock dồn dập | Hàng `inventory(product_id=42)` |
| Hot partition | Một partition nhận quá nhiều dữ liệu hoặc công việc | Kafka partition giữ mọi event của shop lớn |
| Hot shard | Một database/cache shard có tải lệch | Shard chứa tenant lớn |
| Noisy neighbor | Một bên tiêu thụ tài nguyên làm ảnh hưởng bên khác | Tenant A làm latency Tenant B tăng |
| Key skew | Lệch phân bố tần suất hoặc chi phí theo key | 1% key tạo 80% truy vấn |
| Head-of-line blocking | Công việc chậm phía trước làm hàng đợi phía sau bị chặn | Event của shop lớn làm chậm event khác cùng partition |

Không chỉ nhìn CPU trung bình toàn cluster. Một node CPU 100% trong khi 19 node 15% CPU vẫn có thể làm SLO của khách hàng vi phạm.

## 4. Mô hình công suất tối thiểu

Gọi:

- `λ_i`: tốc độ công việc đến đơn vị xử lý i, ví dụ request/giây.
- `μ_i`: thông lượng xử lý ổn định của đơn vị i, với giả định công việc có chi phí tương ứng.
- `ρ_i = λ_i / μ_i`: tỉ lệ sử dụng công suất theo mô hình đơn giản.

Nếu `λ_i >= μ_i` kéo dài, backlog của đơn vị i có xu hướng tăng. Với traffic burst, queue vẫn có thể tăng mạnh ngay cả khi trung bình dài hạn nhỏ hơn công suất. Nếu thời gian xử lý mỗi key khác nhau, cần đo **work units** (CPU time, DB time, bytes, thao tác lock) thay vì chỉ so số request.

Ví dụ:

~~~text
Worker A: λ=1.800 msg/s, μ=1.000 msg/s -> backlog tăng
Worker B: λ=200 msg/s,   μ=1.000 msg/s -> còn dư công suất
Worker C: λ=250 msg/s,   μ=1.000 msg/s -> còn dư công suất
~~~

Thêm Worker D có thể vô ích nếu mọi message của hot key vẫn được ràng buộc vào một partition do Worker A xử lý. Bài toán cần giải quyết **phân phối công việc hoặc độ đắt của mỗi công việc**, chứ không chỉ tăng số worker.

### Độ lệch tải

Có thể theo dõi một số thước đo:

- `max(partition_load) / mean(partition_load)`: một chỉ số đơn giản cho biết partition nóng nhất cao hơn mức trung bình bao nhiêu.
- `p95(partition_load)`, `p99(partition_load)`, `max(partition_load)`: tránh trung bình che đỉnh.
- Phần trăm request/bytes/CPU time thuộc **top 1, top 10, top 1% key**.
- Khoảng cách backlog/lượt xử lý lớn nhất và trung bình giữa các partition.
- `p95/p99` latency **theo tenant hoặc nhóm key**, so với latency toàn hệ thống.

Chỉ số max/mean giúp phát hiện skew nhưng chưa đủ để kết luận nguyên nhân: một partition có thể nhận ít message hơn mà vẫn nóng do xử lý đắt hơn hoặc lock contention.

## 5. Đừng chẩn đoán nhầm điểm nóng với lỗi khác

Một service có latency tăng không có nghĩa chắc chắn là hot key. Cần phân biệt:

| Hiện tượng | Dấu hiệu gợi ý | Cần kiểm tra |
|---|---|---|
| Hot read key | Cache miss/DB read bùng tại một product | Top key truy cập, cache hit, request coalescing |
| Hot write row | DB lock wait, deadlock/retry cao ở một row | Transaction duration, row lock, update frequency |
| Hot Kafka partition | Một consumer có lag tăng, consumer khác nhàn | Lag và input rate theo partition, message processing time |
| Slow dependency | Nhiều key cùng tăng latency | Timeouts, upstream/downstream saturation |
| Connection pool nhỏ | Queue wait tăng trên mọi key | Pool utilization, active/idle/wait |
| GC hoặc memory pressure | Pause và allocation tăng | JVM heap, native memory, GC metrics |
| Query thiếu index | Một loại query chậm, không nhất thiết do một key | Query plan, scanned rows, DB CPU |
| Network hotspot | Băng thông/mạng trên một node bão hòa | Bytes, retransmit, NIC/network metrics |
| Tenant noisy neighbor | Tenant khác bị chậm khi một tenant tăng tải | Per-tenant quota, concurrency, queue |

Quy trình điều tra nên bắt đầu từ bề mặt SLO bị ảnh hưởng, truy ngược qua trace, queue, DB và key distribution. Không được thấy một partition lag cao rồi kết luận rằng chỉ cần tăng partition count.

## 6. Nhận diện hot key bằng quan sát có kiểm soát

Dữ liệu theo key dễ gây **cardinality explosion**. Nếu gắn `productId` cho mọi metric series trong Prometheus, hàng triệu sản phẩm có thể tạo số lượng time series lớn. Hướng tiếp cận khả thi:

1. Metric tổng: request rate, latency, error rate, queue depth theo service/partition/shard.
2. Metric theo nhóm ít cardinality: tenant tier, route, shard ID, partition ID hoặc nhóm nghiệp vụ.
3. Thu thập top-N heavy hitters qua cơ chế đếm/bộ lấy mẫu/stream aggregation phù hợp.
4. Trace/log có ID key khi được phép, giới hạn quyền và chính sách dữ liệu; không đưa payload nhạy cảm hoặc secret vào log.
5. So sánh trước và sau flash sale, campaign, batch job hoặc sự kiện tải đặc biệt.

Ví dụ report top key:

~~~text
Window: 5 phút
Total requests: 3.600.000

product:flash-42    1.800.000 (50.0%)
product:normal-7      108.000 (3.0%)
product:normal-3       72.000 (2.0%)
top 10 keys          2.400.000 (66.7%)
all remaining        1.200.000 (33.3%)
~~~

Với security và privacy, cần cân nhắc mã hóa băm/ẩn danh ID người dùng trong dữ liệu phân tích và giới hạn retention. Mục tiêu là xác định độ lệch của tải, không phải thu thập dữ liệu nhận dạng vượt nhu cầu.

### Theo dõi trong message broker

Đối với Kafka hoặc broker có phân vùng, nên quan sát:

- Records in/bytes in theo topic và partition.
- Consumer lag và tốc độ xử lý theo partition.
- Processing latency, failure rate và retry theo handler.
- Số message của top-N business key theo khoảng thời gian.
- Tốc độ commit offset; record bị retry hoặc chuyển DLQ.
- Consumer assignment/rebalance và số partition trên mỗi consumer.

Nếu lag của một partition tăng mà CPU consumer không cao, có thể xảy ra lock, I/O, dependency timeout hoặc một message lỗi cản đường. Phân bố không đều chỉ là một giả thuyết cần kiểm chứng.

## 7. Xác định hotspot là đọc, ghi hay điều phối

Ba tình huống có hướng giải quyết khác nhau.

### 7.1. Hot read

Nhiều người đọc cùng dữ liệu ít thay đổi (giá, mô tả, trạng thái campaign). Có thể nhân bản/caching kết quả đọc vì nhiều lần đọc không nhất thiết phải lần nào cũng vào một database row.

### 7.2. Hot write

Nhiều yêu cầu cùng cập nhật một đối tượng có invariant mạnh (số lượng vé còn, số dư tài khoản, tổng tồn kho). Tách dữ liệu ra nhiều bucket có thể tăng thông lượng nhưng làm việc đọc hợp nhất và giữ tính đúng đắn phức tạp.

### 7.3. Hot workflow hoặc hot ordered stream

Tất cả công việc của một merchant/tenant/order được gửi theo một key để giữ thứ tự. Một partition duy nhất trở thành nút cổ chai. Nếu tự ý thay key để chia đều, consumer có thể thấy các sự kiện cùng nghiệp vụ sai thứ tự.

Một giải pháp tốt luôn trả lời trước ba câu hỏi:

1. Điều gì thực sự **cần được xử lý tuần tự**?
2. Điều gì có thể đọc từ bản sao hoặc xử lý song song?
3. Thông tin nào phải được gom/hòa giải để bảo đảm trạng thái nghiệp vụ cuối?

## 8. Hot read: cache, nhân bản và giảm số request đánh vào nguồn

Giả sử Catalog DB đọc thông tin sản phẩm P với 8.000 request/giây, phần lớn cùng một response. Nếu 95% request được phục vụ từ cache, DB chỉ còn nhận khoảng 400 request/giây (bỏ qua prefetch và các luồng khác).

~~~text
Client requests
       |
       v
API / Cache layer
       |            cache hit -> trả kết quả
       |
       +-- cache miss --> database
       |                    |
       +<-- populate cache -+
~~~

### 8.1. Những kỹ thuật phổ biến

| Kỹ thuật | Lợi ích | Rủi ro/cần cân nhắc |
|---|---|---|
| Local in-process cache | Giảm cả network hop cho dữ liệu rất nóng | Bản sao mỗi pod, stale data, khó invalidate đồng bộ |
| Distributed cache | Chia tải khỏi DB, hỗ trợ nhiều pod | Bản thân một cache key có thể trở thành hotspot ở một node |
| CDN/edge cache | Phù hợp dữ liệu công khai hoặc static | Header, quyền truy cập và invalidation |
| Read replica | Tăng công suất đọc DB | Replication lag, không phục vụ yêu cầu read-after-write nếu không thiết kế |
| Request coalescing/single-flight | Gom nhiều cache miss cùng key thành một lần tải nguồn | Phải xử lý timeout, memory và lỗi của request gốc |
| TTL + jitter | Giảm việc nhiều key hết hạn cùng lúc | Không đảm bảo tránh được hot-key stampede |
| Stale-while-revalidate | Giữ khả dụng với dữ liệu có thể cũ ngắn hạn | Không phù hợp mọi trạng thái bảo mật/tài chính/tồn kho |
| Negative caching | Tránh DB liên tục trả “không tồn tại” | Có thể che mất dữ liệu vừa được tạo nếu TTL dài |

Cần phân biệt **hot read** với dữ liệu cần độ mới rất cao. Dữ liệu mô tả sản phẩm có thể cache vài giây/phút theo contract; số dư hay inventory cuối cùng có thể cần logic chặt hơn.

### 8.2. Cache stampede

Giả sử tất cả request của `productId=P42` đều dùng một cache key TTL 60 giây. Tại giây 60, key hết hạn; 20.000 request cùng bỏ qua cache và tải database.

~~~text
T=59s: cache hit, DB nhẹ
T=60s: cache expired
       -> 20.000 cache misses
       -> DB quá tải
~~~

Cách xử lý:

- Single-flight hoặc per-key lock có timeout để một request refresh còn các request khác chờ/đọc stale nếu được phép.
- Chủ động refresh trước TTL cho hot key đã biết.
- TTL jitter để tránh nhiều **key khác nhau** cùng hết hạn; với một key đơn lẻ, jitter không giải quyết việc mọi caller cùng thấy key hết hạn.
- Giới hạn số request miss được phép chạm nguồn.
- Cho phép stale data trong khoảng được business contract chấp nhận.
- Theo dõi cache miss và DB QPS sau khi đổi chính sách.

**Không dùng một distributed lock vô thời hạn** cho mọi request đọc, vì lock đó có thể trở thành hotspot mới và gây deadlock khi holder chết. Lock cần TTL, ownership, giới hạn wait và đường fallback.

### 8.3. Cache key bị nóng

Một Redis-like cache có thể lưu mỗi key ở một shard cụ thể. Nếu một key nhận quá nhiều read, shard chứa key nóng dù tổng số key đã phân đều. Có thể nhân bản bản đọc tới nhiều node/local cache nếu dữ liệu cho phép, hoặc dùng nhiều cache key đại diện cùng một phiên bản dữ liệu và phân phối read giữa các bản sao. Tuy nhiên mỗi bản sao phải có cách invalidation và tránh stale vượt ngưỡng.

Ví dụ mô hình đọc phân tán:

~~~text
product:P42:v18:replica:0
product:P42:v18:replica:1
product:P42:v18:replica:2
product:P42:v18:replica:3
~~~

Key có `v18` chỉ là ví dụ version logic; phải được kiểm soát từ nguồn có thẩm quyền. Nếu tạo bản sao ngẫu nhiên mà không quản lý cập nhật, người dùng có thể thấy thông tin mâu thuẫn giữa các lần đọc.

## 9. Hot write: vì sao một hàng DB khó scale ngang?

Ví dụ bảng inventory:

~~~sql
CREATE TABLE inventory (
    product_id VARCHAR(100) PRIMARY KEY,
    available_quantity BIGINT NOT NULL
);
~~~

Một cách bán hàng là:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = :productId
  AND available_quantity > 0;
~~~

Dưới điều kiện transaction thích hợp, số dòng được update giúp biết còn tồn hay không. Nhưng khi 20.000 request/giây cùng cập nhật `productId=P42`, mọi transaction tranh chấp lock trên cùng một row. Tăng từ 2 lên 20 application instance **không làm 20 transaction update một row đồng thời một cách độc lập**; điểm tuần tự vẫn ở database.

Một số dấu hiệu:

- Transaction lock wait time tăng.
- Deadlock/serialization failure/optimistic conflict tăng.
- p99 update latency cao dù CPU trung bình DB chưa đạt 100%.
- Connection pool bị chiếm vì transaction chờ lock.
- Số retries do conflict tăng, làm tải ghi nặng thêm.

### 9.1. Giải pháp đầu tiên không nhất thiết là sharding

Trước khi tạo kiến trúc phức tạp, thử:

- Rút ngắn transaction, không gọi network API khi đang giữ DB lock.
- Đảm bảo index và query plan hợp lý; giảm update thừa.
- Dùng atomic conditional update thay read-modify-write tách rời.
- Gom nhiều lệnh nếu hợp đồng cho phép, giảm số lần đụng row.
- Tách read-heavy khỏi write-heavy bằng cache/replica.
- Giới hạn admission và xếp hàng có độ dài hữu hạn khi một mặt hàng flash-sale đạt công suất tối đa.
- Dùng pre-reservation/queue token nếu nghiệp vụ có thể chấp nhận xử lý bất đồng bộ.

Tối ưu đơn giản thường giảm hotspot đáng kể mà không làm logic nghiệp vụ phức tạp hơn.

## 10. Phân mảnh key: bucketing, salting và striped counters

**Key salting/bucketing** là gắn một thành phần phụ vào business key để tạo nhiều đơn vị định tuyến:

~~~text
Trước:
  key = productId
  "P42" -> partition 7

Sau:
  key = productId + ":" + bucket
  "P42:0" -> partition 2
  "P42:1" -> partition 9
  "P42:2" -> partition 4
  "P42:3" -> partition 12
~~~

Nếu mỗi request có thể chọn một bucket độc lập mà vẫn đúng nghiệp vụ, tải trên một key nóng được chia cho nhiều partition/shard. Nhưng vấn đề quan trọng là **chọn bucket từ dữ liệu ổn định** và **hợp nhất kết quả**.

### 10.1. Chọn bucket bằng khóa có tính ổn định

Một công thức minh họa:

~~~text
bucket = floorMod(hash(operationId), bucketCount)
partitionKey = businessKey + ":" + bucket
~~~

`operationId` phải ổn định qua retry và redelivery. Nếu mỗi lần retry sinh random bucket mới, cùng một operation có thể đi tới nhiều nơi, làm tăng nguy cơ xử lý trùng và khó deduplicate.

Ví dụ logic Java:

~~~java
import java.util.Objects;

public final class BucketKey {
    private BucketKey() {}

    public static String forOperation(
            String businessKey,
            String operationId,
            int bucketCount) {
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("bucketCount must be positive");
        }
        int hash = Objects.requireNonNull(operationId).hashCode();
        int bucket = Math.floorMod(hash, bucketCount);
        return Objects.requireNonNull(businessKey) + ":" + bucket;
    }
}
~~~

Đây là hàm minh họa cho việc ánh xạ xác định, không phải cơ chế phân quyền hoặc giao thức hashing phân tán hoàn chỉnh. `String.hashCode()` của Java ổn định cho cùng chuỗi trong JVM, nhưng khi giao tiếp nhiều ngôn ngữ hoặc cần duy trì mapping dài hạn, nên định nghĩa thuật toán/encoding hashing độc lập ngôn ngữ và có version.

### 10.2. Vì sao không luôn dùng random?

Random bucket có thể phù hợp cho **đọc bản sao giống nhau**, vì có thể đọc bất cứ replica nào. Với ghi cần idempotency hoặc event ordering, random bucket tại mỗi lần gửi có thể phá ràng buộc. Một số key ổn định như `orderId`, `paymentAttemptId` hoặc `eventId` cho phép cùng operation giữ cùng bucket qua retry.

Mặt khác, hash `businessKey` rồi thêm bucket cố định không giúp ích nếu mọi operation có cùng businessKey cũng cho ra **một bucket**. Thành phần được hash phải tạo được sự khác biệt giữa những operation được phép xử lý song song.

### 10.3. Cái giá của bucketing

- Read aggregate phải xem nhiều bucket hoặc có bảng tổng hợp.
- Chọn bucket count ảnh hưởng mapping và migration.
- Ordering tổng thể theo businessKey không còn tự nhiên được giữ nếu chia nhiều bucket.
- Mỗi bucket cần dedup và checkpoint đúng.
- Một bucket có thể vẫn nóng nếu operationId phân bố không đều.
- Không phải mọi side effect có thể cập nhật song song mà vẫn giữ invariant.

Vì vậy salting là **một kỹ thuật điều phối**, không tự tạo ra tính nhất quán.

## 11. Ví dụ 1: striped counter cho lượt xem

Một trường hợp thuận lợi để phân tán write là số lượt xem sản phẩm. Nếu chấp nhận kết quả tổng hợp eventual consistency, có thể chia counter:

~~~text
product_views[P42][bucket=0] = 1203
product_views[P42][bucket=1] = 1188
product_views[P42][bucket=2] = 1235
product_views[P42][bucket=3] = 1196

Total views = SUM(all buckets)
~~~

Mỗi event view có `viewEventId` ổn định; bucket được chọn bằng hash của eventId để phân phối ghi. Với độ chính xác cần thiết, consumer phải deduplicate sự kiện và xử lý replay. Nếu thống kê chỉ yêu cầu xấp xỉ, có thể dùng sampling/approximate counters với sai số được định nghĩa.

**Không nhầm tính cộng gộp với idempotency.** Phép cộng là giao hoán theo thứ tự, nhưng cùng một event cộng hai lần vẫn làm tăng kết quả. At-least-once processing vẫn cần dedup theo eventId hoặc thiết kế chấp nhận sai số.

Một schema minh họa:

~~~sql
CREATE TABLE product_view_bucket (
    product_id VARCHAR(100) NOT NULL,
    bucket_no INTEGER NOT NULL,
    view_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, bucket_no)
);
~~~

Cập nhật atomic trên một bucket:

~~~sql
UPDATE product_view_bucket
SET view_count = view_count + :delta
WHERE product_id = :productId AND bucket_no = :bucketNo;
~~~

Nếu chọn `bucketNo = hash(viewEventId) mod 16`, 16 bucket giúp giảm tranh chấp so với một row; cần benchmark để biết mức cải thiện thực tế. Việc tổng hợp có thể dùng batch hoặc materialized view, với độ trễ rõ ràng.

## 12. Ví dụ 2: tồn kho flash sale cần bất biến mạnh

Số lượt xem có thể eventual; **tồn kho** không thể tự ý phân tán counter mà bỏ ràng buộc tổng số hàng.

Giả sử Inventory có 1.000 đơn vị sản phẩm P42, chia thành 4 bucket mỗi bucket cấp quyền bán tối đa 250 đơn vị:

~~~text
Bucket 0: 250 token bán
Bucket 1: 250 token bán
Bucket 2: 250 token bán
Bucket 3: 250 token bán
Tổng token đã cấp = 1.000
~~~

Mỗi bucket có thể giảm token cục bộ bằng atomic conditional update. Khi một bucket hết token, request có thể thử bucket khác theo chính sách rõ ràng; **không được tự nhân thêm token**. Có thể điều chuyển token giữa bucket, nhưng việc điều chuyển phải bảo đảm bảo toàn tổng và tránh phát đồng thời hai lần.

### Các bất biến cần bảo vệ

1. `sold + reserved + available <= initialInventory`, với các trạng thái và quy tắc hủy/hoàn được định nghĩa rõ.
2. Mỗi `reservationId` chỉ tạo một reservation dù request retry.
3. Token chuyển từ bucket A sang B không được tính ở cả hai bucket cùng lúc.
4. Reservation hết hạn/được hủy phải hoàn token đúng một lần.
5. Hệ thống có thể đối soát tổng token và số order đã được xác nhận.

Ví dụ transaction cho một bucket:

~~~sql
UPDATE inventory_bucket
SET available = available - 1
WHERE product_id = :productId
  AND bucket_no = :bucketNo
  AND available > 0;
~~~

Chỉ khi update thành công và reservation record được ghi trong một ranh giới transaction phù hợp, yêu cầu mới được xác nhận. Nếu DB và service thanh toán nằm ở hai hệ thống khác nhau, cần saga/outbox, idempotency key hoặc reconciliation; một transaction DB cục bộ không khiến hai hệ thống bên ngoài trở thành atomic.

### Khi nào không nên chia bucket?

Nếu mọi lệnh bắt buộc được chấp nhận theo một thứ tự toàn cục rất nghiêm ngặt (ví dụ đấu giá với các ràng buộc liên quan mọi giá), việc chia bucket có thể phá semantics. Khi đó có thể giữ một **single writer** có kiểm soát, queue giới hạn, admission control và công suất đã đo, thay vì giả vờ mọi operation có thể chạy song song.

## 13. Message broker: partition key có thể trở thành nút cổ chai

Một cách phổ biến để bảo đảm thứ tự theo aggregate là dùng `aggregateId` làm message key.

~~~text
Producer: OrderEvent(orderId="O-17")
             |
             v
         hash(orderId)
             |
             v
      Kafka partition 4
             |
             v
       Một consumer xử lý
~~~

Kafka thường bảo toàn thứ tự records trong một partition, và trong consumer group thông thường một partition tại một thời điểm được gán cho một consumer của group. Điều này **không tạo ra thứ tự toàn hệ thống** giữa các partition; event reordering vẫn có thể phát sinh ở tầng retry topic, nhiều producer, xử lý bất đồng bộ hoặc code ứng dụng.

Nếu tất cả event của một `merchantId=BIG-SHOP` được gửi vào cùng partition, một shop có thể dùng hết công suất partition dù cluster có nhiều consumer. Tăng số consumer hơn số partition không giúp partition đó có nhiều consumer cùng xử lý thứ tự chính xác.

### 13.1. Không thay message key một cách tùy tiện

Giả sử luồng cũ:

~~~text
Merchant=BIG-SHOP:
    OrderCreated -> PaymentAuthorized -> OrderShipped
~~~

Nếu gắn salt vào `merchantId` mà không giữ key theo một order, event cùng Order có thể đi tới các partition khác và được xử lý ngược thứ tự.

Một thiết kế tốt hơn có thể dùng `orderId` thay vì `merchantId` làm key nếu invariant ordering chỉ cần **theo order**, không cần theo toàn shop. Một merchant có hàng nghìn order độc lập; khi đổi aggregate boundary từ shop sang order, workload có thể phân tán tự nhiên mà vẫn giữ order per order.

Đây là điểm mấu chốt: **thay đổi phạm vi cần tuần tự** có thể hiệu quả và an toàn hơn salting ngẫu nhiên.

### 13.2. Khi nào dùng bucket ở stream?

Nếu event của một merchant là các thao tác độc lập, có thể định tuyến theo `merchantId + bucket(orderId)`. Khi consumer cần báo cáo tổng merchant, có thể hợp nhất kết quả theo phiên bản hoặc dùng aggregation job.

Nếu nghiệp vụ bắt buộc áp dụng một dãy sự kiện có `merchantSequence` duy nhất, chia nhiều partition đòi consumer:

- Nhận sequence number từ nơi có thẩm quyền.
- Giữ hoặc phát hiện gap nếu sự kiện đến chưa theo thứ tự.
- Không áp dụng event cũ làm ghi lùi state.
- Có cửa sổ buffer giới hạn, timeout và cơ chế lấy lại sự kiện thiếu.
- Dedup theo eventId và business key.
- Có kế hoạch xử lý missing event, DLQ và reconciliation.

Nếu không có chiến lược này, không nên hứa “chia nhiều partition mà vẫn giữ thứ tự tuyệt đối”.

## 14. Một số lựa chọn cho hot Kafka partition

| Phương án | Điều kiện phù hợp | Giới hạn |
|---|---|---|
| Tối ưu handler của partition nóng | Công việc có CPU/I/O thừa | Có giới hạn khi một partition vẫn cần xử lý tuần tự |
| Giảm blocking I/O và xử lý batch | Event có thể gom, tối ưu connection pool | Có thể tăng latency hoặc phá thứ tự khi concurrency không kiểm soát |
| Đổi key từ tenantId sang aggregateId nhỏ hơn | Ordering chỉ cần ở aggregate nhỏ | Cần chứng minh consumer contract và migration |
| Salting key theo sub-entity ổn định | Operations độc lập trong các bucket | Phải xử lý tổng hợp và version |
| Split topic theo class công việc | Hot keys và normal keys có SLO khác | Tăng phức tạp route, consumer và vận hành |
| Dedicated partition/topic/consumer cho hot tenant | Tenant lớn có thể được cô lập | Phải quản trị onboarding/migration và công suất riêng |
| Throttle/admission control | Không thể tăng công suất ngay | Một phần request phải chờ/bị từ chối theo hợp đồng |
| Queue per key với scheduler công bằng | Muốn cô lập tải và tránh starvation | Tốn memory/quản lý backlog, cần fairness |
| Tăng partition count | Tải đến từ nhiều key và mapping thực sự cần dàn đều | Một key nóng đơn lẻ vẫn có thể chỉ vào một partition |

Việc thay số partition của Kafka topic có thể ảnh hưởng mapping key→partition (tùy partitioner và thời điểm), khiến event cùng key mới và cũ nằm ở các partition khác nhau trong giai đoạn chuyển. Với yêu cầu ordering nghiêm ngặt, cần migration/cutover có kiểm soát và kiểm chứng bằng dữ liệu thực.

## 15. Database sharding và hot tenant

Nếu dữ liệu được shard theo `tenantId`, một khách hàng enterprise lớn có thể chiếm 70% ghi và 50% dung lượng của một shard:

~~~text
Shard A: Tenant BIG (70%) + nhiều tenant nhỏ
Shard B: Tenants nhỏ
Shard C: Tenants nhỏ
~~~

Thêm shard D rồi hash lại **có thể** chuyển các tenant nhỏ nhưng không chia được tải nội bộ của tenant BIG nếu toàn bộ tenant luôn phải nằm cùng shard.

Những hướng xử lý:

1. **Cô lập tenant lớn:** đặt riêng shard/cluster để tránh làm ảnh hưởng tenant khác.
2. **Chia sub-key:** dữ liệu của tenant lớn tách theo project, account, workspace hoặc domain entity nếu có ranh giới độc lập.
3. **Giảm chi phí truy vấn:** index, query shape, caching, batch, partition pruning.
4. **Tách read khỏi write:** replica hoặc materialized read model khi cho phép.
5. **Áp quota và scheduling công bằng:** ngăn một tenant chiếm hết pool.
6. **Theo dõi hot index/row:** dù tách shard, một sequence row hoặc unique index vẫn có thể trở thành contention point.

### 15.1. Dedicated shard không có nghĩa vô hạn

Cô lập tenant lớn giúp giảm noisy-neighbor, nhưng hot tenant vẫn có thể quá tải trên shard riêng. Phải đo sức chứa và có lộ trình tiếp theo: split theo sub-entity, read replicas, queue/async workflow hoặc thay data model. Một người thuê lớn không nhất thiết phù hợp cho mô hình chia đều theo tenant hash.

### 15.2. Index hotspot

Ví dụ tất cả ghi vào một index có leading key giống nhau hoặc tăng đơn điệu có thể gây contention ở một vùng cấu trúc index tùy database engine. Không nên quy mọi tình huống thành “row lock”. Cần xem execution plan, index maintenance, WAL/redo, page contention và behavior thực tế của engine. Giải pháp có thể là sửa khóa/index, partitioning hoặc giảm tần suất ghi; lựa chọn phụ thuộc công nghệ.

## 16. Redis/cache cluster cũng có điểm nóng

Trong cluster key-value, một key có thể map tới một slot/shard. Nếu `stock:P42` nhận 100.000 phép `GET`/giây, việc bổ sung nhiều shard có thể không giúp vì vẫn là **một key**.

Các hướng cân nhắc:

- Local cache ở application layer cho read-only/stale-acceptable fields.
- Replica hoặc phân phối read theo cơ chế được cache system hỗ trợ, có lưu ý consistency.
- Nhân bản value thành nhiều key và dùng routing ổn định cho read; cập nhật phải đồng bộ theo policy.
- Gom request trùng, xử lý hit trước khi chạm Redis.
- Thay thao tác ghi từng request bằng batch hoặc stream nếu hợp đồng cho phép.
- Rate limit/circuit breaker khi cache shard đạt ngưỡng.
- Chuyển hot key sang kiến trúc chuyên biệt với giới hạn và bộ đo riêng.

Không dùng cache để che giấu một hot write có invariant mà không có thiết kế bền vững. Ví dụ tăng tồn kho chỉ trong cache rồi flush muộn có thể mất dữ liệu khi node chết nếu không có nguồn bền vững và quy trình recovery.

## 17. Công bằng đa tenant: tránh noisy neighbor

Một bài toán khác của phân bố lệch là workload của Tenant A chiếm queue, worker và connection pool, khiến Tenant B chậm dù B chỉ gửi ít request.

Có thể thiết kế:

- **Per-tenant rate limit:** mỗi tenant có tốc độ tối đa hoặc ngân sách request.
- **Per-tenant concurrency limit:** một tenant không chiếm hết thread, connection hoặc worker slot.
- **Weighted fair queuing:** dành suất xử lý theo mức dịch vụ/hợp đồng, có giới hạn toàn hệ thống.
- **Bulkhead:** pool hoặc queue riêng cho nhóm workload, giảm lan truyền lỗi.
- **Hot tenant isolation:** chuyển tenant lớn sang worker pool/shard chuyên dụng.
- **Backpressure:** trả 429/503 theo hợp đồng hoặc đưa vào queue hữu hạn, không âm thầm nhận vô hạn.

Ví dụ policy minh họa:

~~~text
Tenant GOLD:   800 requests/second, max 120 concurrent
Tenant BASIC:  100 requests/second, max  20 concurrent
Global:      3.000 requests/second, max 500 concurrent
~~~

Con số chỉ là minh họa và phải dựa trên kế hoạch dung lượng/SLAs. Rate limit per-instance không tự bảo đảm quota per-tenant **toàn hệ thống** nếu traffic của một tenant trải qua nhiều instance. Cần thiết kế cơ chế chia ngân sách/phối hợp hoặc chấp nhận sai số được công bố.

### Rate limit là cơ chế bảo vệ, không phải giải pháp duy nhất

Nếu một tenant hợp lệ cần 2.000 request/giây theo hợp đồng, giảm quota xuống 100 để che vấn đề công suất là không phù hợp. Cần đánh giá cách tăng công suất hoặc phân tán tải; rate limiting dùng để bảo đảm giới hạn và công bằng, không thay thế capacity planning.

## 18. Thay đổi số bucket và version của hàm định tuyến

Ban đầu `P42` có 4 bucket. Khi tăng lên 16 bucket, công thức `hash(operationId) mod bucketCount` sẽ thay đổi ánh xạ của nhiều operation. Retry của operation cũ có thể vào bucket mới, gây duplicate hoặc mất khả năng tìm trạng thái trước đó.

Cần thiết kế **mapping version**:

~~~text
Routing policy v1:
  bucketCount=4
  operation P-17 -> P42:v1:b2

Routing policy v2:
  bucketCount=16
  operation P-18 -> P42:v2:b11
~~~

Một operation phải giữ mapping được ghi khi nó được tạo. Có thể lưu `routingVersion` và `bucketId` trong command/event hoặc operation ledger. Khi retry, đọc lại routing decision cũ thay vì tính theo config mới.

### Quy trình migration an toàn

1. **Quan sát:** xác định hot key, công suất, backlog và tính đúng đắn cần giữ.
2. **Chuẩn bị schema:** hỗ trợ cả routing version cũ và mới, cùng cơ chế đọc/hợp nhất tương ứng.
3. **Deploy reader tương thích:** consumer có thể xử lý dữ liệu từ cả hai version.
4. **Chuyển writer có kiểm soát:** operation mới dùng v2; operation cũ dùng mapping đã ghi.
5. **Kiểm tra dữ liệu:** count, checksum, ledger, reconciliation, lag và các bất biến.
6. **Theo dõi hỗn hợp:** chạy khi hai routing version cùng tồn tại theo chính sách.
7. **Đóng phiên bản cũ:** chỉ sau khi không còn operation cần retry, dữ liệu lịch sử được xử lý và cửa sổ rollback kết thúc.

Không mặc định **dual-write** vào cả hai bucket là vô hại. Nếu cả hai writer tạo side effect độc lập, có thể nhân đôi doanh thu hoặc tồn kho. Nếu cần dual-write để migration, phải xác định một nguồn có thẩm quyền, idempotency và cách kiểm tra thống nhất.

## 19. Hot key được phát hiện động: detection và xử lý tự động

Đôi khi điểm nóng thay đổi liên tục theo thời gian: phút này sản phẩm A viral, phút sau chiến dịch B bắt đầu. Có thể xây cơ chế tự phát hiện, nhưng cần tránh hệ thống tự đảo cấu hình vô hạn.

Một vòng điều khiển:

~~~text
Per-key / per-partition telemetry
               |
               v
  Hot-key detector (cửa sổ thời gian)
               |
               v
 Đánh giá mức tải, SLO, confidence
               |
               v
  Chọn hành động có thể rollback
      /       |        \
   Cache    Isolate   Change routing
      \       |        /
               v
  Giám sát kết quả + cooldown
~~~

### Thiết kế tránh dao động

- Dùng ngưỡng bật và tắt khác nhau (hysteresis) để không chuyển đổi liên tục.
- Có cửa sổ tối thiểu, điều kiện phát hiện kéo dài, và cooldown sau hành động.
- Giới hạn số key có thể được tự động tách và số bucket tối đa.
- Dừng tự động khi thiếu telemetry, có lỗi dữ liệu, lag bất thường hoặc không chắc ranh giới consistency.
- Lưu mapping version, thời điểm đổi, người/automation thực hiện và kế hoạch rollback.
- Ưu tiên cơ chế **read caching** có thể đảo ngược trước khi thay routing write với dữ liệu quan trọng.

Đừng tự động salt mọi key có CPU cao: có thể CPU do query sai hoặc một operation cực đắt, không phải lưu lượng có thể phân tán.

## 20. Ví dụ kiến trúc từ đầu đến cuối: flash sale sản phẩm P42

Hệ thống thương mại điện tử có:

~~~text
Users -> Gateway -> Catalog API -> Cache -> Catalog DB
                 |
                 +-> Order API -> Inventory -> Inventory DB
                                    |
                                    +-> Inventory events -> Broker
                                                |
                                                v
                                         Analytics Consumer
~~~

Trong flash sale, P42 nhận:

- 15.000 view request/giây.
- 1.500 reservation request/giây.
- 1.500 inventory events/giây.
- Đa số event có `productId=P42`.

Nếu định tuyến tất cả theo productId, có thể gặp đồng thời hot cache key, hot inventory row và hot Kafka partition.

### 20.1. Lớp Catalog: giải quyết hot read

Cache trang/metadata sản phẩm bằng version hoặc TTL có kiểm soát. Dùng single-flight khi cache miss; có thể dùng CDN cho nội dung công khai ổn định. Nếu giá có thể đổi, cần chính sách độ mới và invalidation rõ. Mục tiêu giảm số request thật đánh Catalog DB, không làm mất khả năng cập nhật giá.

### 20.2. Lớp Inventory: giải quyết hot write

Đo lock wait, DB CPU và reservation latency. Trước tiên tối ưu atomic update, transaction duration và giới hạn admission. Nếu vẫn không đáp ứng, xem xét phân bổ inventory quota thành bucket/escrow với invariant tổng tồn kho và xử lý chuyển token.

### 20.3. Lớp Event: chọn khóa đúng phạm vi

Nếu event phục vụ analytics lượt xem/số lượng đơn, chúng có thể dùng `orderId` hoặc eventId để phân tán rồi tổng hợp theo productId. Nếu event phục vụ xử lý trạng thái một reservation, nên giữ ordering theo `reservationId`/aggregate tương ứng. Không ép tất cả event liên quan P42 vào cùng một partition nếu chúng không cần một hàng đợi tuần tự duy nhất.

### 20.4. Lớp Tenant fairness

Nếu flash sale thuộc Merchant A, cần quota và bulkhead để request của Merchant B/C không bị nghẽn ở pool chung. Có thể dành capacity riêng cho campaign lớn, nhưng phải đo và kiểm soát chi phí.

### 20.5. Tính đúng đắn sau khi tách tải

Các assertion quan trọng:

- `reserved + sold + available` không vượt lượng hàng hợp lệ theo mô hình.
- Một `orderId/reservationId` không chiếm hai token qua retry.
- Event phát lại không cộng/trừ thống kê hoặc tồn kho hai lần.
- Trạng thái order/reservation không ghi lùi bởi event đến trễ.
- Phân bố request theo bucket được cải thiện; backlog có thể tiêu hết khi tải giảm.
- Merchant khác không chịu vi phạm SLO do một campaign.

## 21. Thiết kế kiểm thử tải với skew

Nếu load test gửi 10.000 request/giây nhưng chọn key đều ngẫu nhiên trên một triệu key, nó có thể không tái tạo hotspot có thật. Cần sinh dữ liệu theo phân bố phù hợp.

### 21.1. Ba hồ sơ tải

| Hồ sơ | Phân bố key | Mục tiêu |
|---|---|---|
| Uniform | Request gần như đều giữa nhiều key | Baseline hệ thống |
| Single hot key | Một key nhận phần lớn traffic, ví dụ 60% | Kiểm tra nút thắt một partition/row |
| Multi-hot heavy tail | Top vài key chiếm phần lớn traffic | Kiểm tra hash, cache, fairness và scaling |
| Moving hotspot | Key nóng chuyển đổi theo từng cửa sổ | Kiểm tra detection, cooldown và migration |
| Bursty campaign | Tốc độ tăng nhanh rồi giảm | Kiểm tra queue, backpressure, recovery |

Ví dụ luồng test với 100.000 logical requests:

~~~text
60.000 requests  -> product P42
10.000 requests  -> product P17
30.000 requests  -> 1.000 products khác
~~~

Nếu một request chọn P42 nhưng phải có idempotency key riêng, tạo ID ổn định theo logical operation. Đối với retry test, gửi lại **cùng** operation ID chứ không tạo một ID mới mỗi lần.

### 21.2. Mã giả sinh skew

~~~text
function chooseBusinessKey(rng):
    p = rng.nextDouble()

    if p < 0.60:
        return "P42"

    if p < 0.70:
        return "P17"

    return "P" + chooseOneOfOtherProducts(rng)
~~~

Đây là phân phối cụ thể do bài test đặt ra, không phải giả định dữ liệu thực tế có đúng 60/10/30. Dùng seed cho generator để tái lập; kết hợp metric theo key/partition và data correctness assertions.

### 21.3. Các chỉ số test

- Request throughput tổng và theo hot key.
- p50/p95/p99 latency theo hot/normal key hoặc tenant.
- Rate timeout, 429/503, retries và queue rejection.
- Partition/shard load max/mean, p95 và backlog.
- Lock wait, DB contention, consumer lag, connection pool saturation.
- Cache hit/miss và số read thật đánh DB.
- Số bản ghi/side effect cuối đúng với số operation duy nhất.
- Thời gian hồi phục backlog sau khi ngừng burst.
- Chi phí CPU/memory/network và số replica/bucket thực tế cần dùng.

Test không đạt nếu aggregate throughput tăng nhưng một tenant nhỏ vẫn bị nghẽn hoặc tồn kho bị bán vượt.

## 22. Kiểm thử tính đúng đắn của bucketing

Cần tách phép đo hiệu suất và kiểm tra invariant.

### 22.1. Deterministic routing

Với cùng `operationId`, routing phải trả cùng bucket khi `routingVersion` không đổi. Retry và redelivery phải dùng mapping đã ghi. Có thể property-test hàng nghìn operationId để xác nhận bucket nằm trong `[0, bucketCount-1]` và mapping deterministic.

### 22.2. Phân bố tương đối đều

Với nhiều operation IDs phân bố tốt, histogram bucket được kỳ vọng không quá lệch trong ngưỡng test. Không nên đòi mỗi bucket có **chính xác** cùng số event; hashing không bảo đảm phân phối tuyệt đối bằng nhau trên mẫu hữu hạn.

### 22.3. Concurrent writes

Cho nhiều worker cùng đặt reservation cho P42 trong các bucket khác nhau. Test tại DB thật để xác nhận atomic conditional update, unique idempotency record, và tổng token không bị âm.

### 22.4. Crash, timeout, replay

Tạo crash sau DB commit nhưng trước khi ACK event; redelivery không được trừ token lần thứ hai. Gây timeout sau khi provider nhận lệnh rồi retry cùng key; xác nhận side effect không nhân đôi.

### 22.5. Migration routing version

Tạo operation khi bucketCount=4, nâng cấu hình lên 16 rồi retry operation cũ. Hệ thống phải xử lý qua mapping v1 hoặc cơ chế lookup tương đương. Nếu operation mới dùng v2, aggregator vẫn tính đúng tổng.

### 22.6. Ordering và gap

Gửi các event cùng reservation theo lịch phiên bản `[2,1,3,2]`. Hệ thống cần phản ứng theo hợp đồng: hold gap, áp dụng lần lượt, bỏ replay; không làm state version giảm. Với event độc lập như page view, có thể dùng phép cộng giao hoán nhưng vẫn xử lý duplicate theo mức chính xác yêu cầu.

## 23. Kế hoạch vận hành khi điểm nóng bùng phát

Một playbook ngắn giúp nhóm không đổi partition/shard trong hoảng loạn:

**Bước 1 — Xác minh tác động.** Xác định service, tenant, key và SLO bị ảnh hưởng. Kiểm tra đây là vấn đề một key hay dependency chung.

**Bước 2 — Đo bottleneck.** Đọc top key distribution, shard/partition load, queue lag, DB lock wait và saturation. Xác định critical path trước khi scale.

**Bước 3 — Giảm áp lực tạm thời.** Với read, tăng cache/coalescing có kiểm soát; với write, dùng admission control/queue hữu hạn; với tenant, áp quota theo hợp đồng. Tránh retry storm làm nặng thêm.

**Bước 4 — Chọn biện pháp cấu trúc.** Nếu ordering chỉ cần theo order, đổi key từ merchant sang order; nếu hot row giữ invariant, cân nhắc quota buckets hoặc single-writer có công suất rõ; nếu hot read, nhân bản/cache.

**Bước 5 — Thử trên staging với skew thật.** Không chỉ benchmark uniform. Có lỗi retry, duplicate, out-of-order và kiểm tra invariants.

**Bước 6 — Triển khai có kiểm soát.** Canary theo nhóm key/tenant; theo dõi mapping version và sức chứa. Có lộ trình rollback không nhân đôi effect.

**Bước 7 — Đo sau thay đổi.** So sánh p99 latency, max/mean partition load, backlog drain, fairness và chi phí. Nếu tải chỉ chuyển sang một bottleneck mới, cần điều chỉnh kế hoạch.

**Bước 8 — Hoàn thiện tài liệu.** Lưu nguyên nhân, key distribution, ngưỡng cảnh báo, owner của routing policy và quy trình tăng số bucket cho tương lai.

## 24. Các sai lầm kiến trúc thường gặp

**Tăng số pod nhưng không đổi phân phối key.** Nếu tất cả request cùng hash tới một partition/row, pod mới có thể nhàn rỗi. Phải đo bottleneck trước.

**Đo CPU trung bình thay vì phân vị và top partition.** Một node bão hòa bị che bởi cluster trung bình 25%. Cần max/mean và per-key/per-shard telemetry.

**Hash business key rồi kỳ vọng hot key được tách.** Hash của một key cố định luôn ra một kết quả trong cùng routing policy. Cần sub-key/bucket hoặc thay ranh giới aggregate khi cho phép.

**Salt random mỗi lần retry.** Operation có thể vào bucket khác và gây duplicate. Dùng ID ổn định, version mapping và idempotency.

**Chia nhỏ write nhưng không thiết kế tổng hợp/nhất quán.** Striped counter cho page view khác escrow inventory; không thể áp dụng cùng semantics.

**Thay partition key mà quên thứ tự sự kiện.** Nếu consumer cần strict order, salting có thể phá workflow. Chọn đúng aggregate boundary và giữ version/gap handling.

**Tự động đổi số bucket khi tải tăng mà không versioning.** Operation cũ có thể được route khác khi retry. Cần ghi mapping version, đặc biệt khi side effect không idempotent.

**Đưa mọi business key vào metric label.** Cardinality tăng không kiểm soát. Sử dụng top-N/aggregation/trace có bảo vệ.

**Dùng cache vô hạn cho dữ liệu nhạy cảm với độ mới.** Giá, inventory và quyền truy cập phải có consistency/freshness contract riêng.

**Để một tenant dùng hết connection pool chung.** Thêm shard không giải quyết fairness trong application. Dùng quota, bulkhead và scheduling phù hợp.

**Scale dựa trên một metric gây loop.** Hot-key detection tự chuyển routing liên tục có thể gây mất ổn định; cần hysteresis và cooldown.

**Quên reconciliation sau sự cố.** Dù throughput tốt, reservation trùng hoặc event mất vẫn khiến hệ thống thất bại về nghiệp vụ.

## 25. Checklist thiết kế

Khi xuất hiện hot key, hãy trả lời:

1. Khóa đang dùng để route là gì: product, merchant, tenant, order hay account?
2. Lưu lượng của top 1/top 10 key chiếm bao nhiêu phần trăm trong giờ cao điểm?
3. Nút thắt nằm ở cache, DB row, index, shard, broker partition, consumer hay worker pool?
4. Tác vụ có chi phí tương đương không, hay có key thực hiện thao tác nặng hơn hẳn?
5. Có thể giảm tải nguồn bằng cache, batch, coalescing hoặc xử lý bất đồng bộ không?
6. Điều gì phải giữ thứ tự: mọi event của merchant hay chỉ một order/reservation?
7. Có thể chia key theo sub-entity mà không vi phạm aggregate invariant không?
8. Nếu dùng bucket, phép tính hợp nhất và phân bổ quota có đúng khi concurrent/replay không?
9. Retry có giữ cùng routing version và idempotency key không?
10. Khi thay bucket count, có đọc/migrate dữ liệu cũ an toàn không?
11. Tenant không liên quan có được bảo vệ bằng quota/bulkhead không?
12. Hệ thống quan sát được partition/shard load và backlog theo đúng chiều cần thiết không?
13. Đã chạy benchmark với skew, burst và moving hotspot thay vì chỉ uniform chưa?
14. Có kế hoạch rollback không làm mất dữ liệu hoặc nhân đôi side effect không?
15. Có owner chịu trách nhiệm thuật toán routing, version mapping và vận hành hot tenant không?

Các câu hỏi này giúp xác định **giải pháp đơn giản nhất còn đáp ứng đúng nghiệp vụ**. Không cần mọi service dùng sharding/salting nếu phần lớn tải đã được giải quyết bằng cache hoặc tối ưu truy vấn.

## 26. Bài tập thực hành

### Bài A — Đọc top-key distribution

Một hệ thống có 24.000 read request/giây, trong đó một sản phẩm chiếm 14.400 request/giây. Có 24 shard, hashing theo productId. Mỗi shard đọc tối đa 2.000 request/giây trước khi latency tăng mạnh. Hãy giải thích vì sao thêm shard không đủ, và đề xuất cache/single-flight/read-replica với test xác nhận QPS thật đánh DB giảm.

### Bài B — Kafka partition nóng

Một merchant lớn tạo 80% event, toàn bộ event dùng merchantId làm key. Mỗi order có state machine riêng, nhưng không cần total order giữa các order. Hãy chọn key thay thế, giải thích bảo toàn ordering theo order, cách xử lý retry topic, và lập test để đo lag/độ đều theo partition.

### Bài C — Counter phân tán

Thiết kế 16 bucket đếm lượt xem của P42. Viết hàm chọn bucket từ eventId ổn định; mô tả cách tổng hợp, duplicate handling, thay bucket count và thử crash sau commit trước ACK.

### Bài D — Tồn kho có giới hạn

Sản phẩm có 800 đơn vị, chia thành 8 bucket ban đầu. Thiết kế allocation và atomic reservation sao cho không oversell, không giữ token trùng qua retry và có cách hoàn token khi order bị hủy. Liệt kê tình huống cần DB transaction và reconciliation.

### Bài E — Tenant noisy neighbor

Tenant A tạo 3.000 request/giây, Tenant B/C mỗi bên chỉ 50 request/giây. Cả ba dùng chung 100 worker slots. Hãy xây chính sách quota/concurrency/fair queue và kiểm chứng p99 của B/C không vi phạm SLO khi A tăng tải, không chỉ dựa vào throughput tổng.

### Bài F — Migration từ 4 sang 16 bucket

Khi đổi routing policy từ v1 sang v2, một payment operation từ trước được retry sau 30 phút. Hãy chỉ ra vì sao tính lại `hash(operationId) mod 16` có thể sai, và đề xuất schema lưu routingVersion cùng strategy đọc lại operation ledger. Kiểm thử operation cũ và mới cùng tồn tại.

### Bài G — Chẩn đoán hot row

Một Inventory DB có CPU trung bình 35% nhưng p99 reservation tăng tới nhiều giây. Quan sát thấy lock wait ở một row cao và connection pool gần đầy. Hãy mô tả thứ tự điều tra, tối ưu transaction, cách xử lý admission trước khi cân nhắc bucketing, và điều kiện quyết định dùng escrow quota.

## 27. Kết luận

Điểm nóng không chỉ là vấn đề thiếu máy; đó là **sự không tương xứng giữa cách phân phối công việc và ranh giới dữ liệu/nghiệp vụ**. Một khóa duy nhất có thể tạo phần lớn request, lock một row, làm nghẽn partition hoặc chiếm tài nguyên của cả tenant khác. Hash đều về số lượng khóa chưa chắc hash đều về tải thực tế.

Cách xử lý bắt đầu bằng **đo top key và bottleneck**, sau đó giảm số lần chạm nguồn bằng cache/coalescing, tăng công suất xử lý hợp lệ, đổi phạm vi key khi nghiệp vụ cho phép, hoặc phân mảnh bằng bucket/salt có version. Với read-mostly workload, nhân bản có thể rất hiệu quả; với hot write và event có thứ tự, phải thiết kế thêm idempotency, quota, version, transaction và reconciliation.

Tiêu chí thành công không phải chỉ là biểu đồ CPU đẹp hơn. Một hệ thống đã xử lý đúng điểm nóng khi **latency và backlog cải thiện**, các tenant không liên quan được bảo vệ, và **mọi bất biến dữ liệu vẫn đúng** qua concurrency, retry, crash, redelivery và migration.
