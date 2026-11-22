# Chia bucket, thêm phần phân tán vào khóa và chi phí đọc hợp nhất trong NoSQL

Một ứng dụng có hàng triệu người dùng có thể vẫn nghẽn tại **một partition nóng** nếu mọi giao dịch cùng ghi vào khóa `event-42` hoặc mọi sự kiện của một thiết bị được đẩy vào cùng một partition. Thêm máy và tăng tổng dung lượng cụm không bảo đảm điểm nóng biến mất: dữ liệu cùng một khóa thường vẫn bị định tuyến vào một phạm vi chịu trách nhiệm hữu hạn. Một kỹ thuật phổ biến là **chia bucket** và **thêm phần phân tán (suffix/salt/shard number) vào khóa** để chia luồng ghi ra nhiều logical keys/partitions.

Nhưng đổi lại, truy vấn “xem tất cả dữ liệu của event-42 theo thời gian” có thể phải đọc **nhiều bucket**, kết hợp kết quả, khử trùng, sắp xếp toàn cục và phân trang. Thậm chí có những bất biến nghiệp vụ như không bán quá số vé cuối cùng **không thể** được bảo vệ chỉ bằng cách cộng thêm suffix vào khóa.

Bài học **“Chia bucket, thêm phần phân tán vào khóa và chi phí đọc hợp nhất”** thuộc chương *Cân bằng và điểm nóng* của Database No SQL. Bài phân tích cách tạo bucket theo thời gian/định danh, suffix bằng hash hoặc ngẫu nhiên, cách tính số bucket, thiết kế đọc hợp nhất, áp dụng trên DynamoDB, Cassandra/ScyllaDB, MongoDB, Redis và những tình huống cần tránh.

Các số liệu throughput, dung lượng, độ trễ trong ví dụ đều là **giả định để học và thiết kế thí nghiệm**, không phải giới hạn chính thức của một sản phẩm. Khả năng tách partition, placement, indexing và chi phí đọc phụ thuộc engine, phiên bản, throughput mode, replication, topology và workload. Mọi quyết định cần được kiểm chứng bằng metric của hệ đang sử dụng.

## 1. Điểm nóng là gì và vì sao thêm máy không luôn giải được?

**Hot key/hot partition** là khóa hoặc phạm vi dữ liệu nhận lượng công việc vượt năng lực xử lý của đơn vị sở hữu nó, dù cluster còn nhiều tài nguyên trống.

Ví dụ:

~~~text
Cluster có 8 nodes:

Node 1: 90% requests tới partition event-42
Node 2:  2%
Node 3:  2%
Node 4:  1%
Node 5:  1%
Node 6:  1%
Node 7:  1%
Node 8:  2%
~~~

Nếu engine định tuyến cùng partition key về một nơi sở hữu hoặc một replica group, tất cả những writes tới `event-42` có thể tranh tài nguyên trong phạm vi đó. Node còn lại nhàn rỗi không giúp partition nóng tự biến thành tám phần độc lập.

Điểm nóng có thể xuất hiện ở nhiều tầng:

| Tầng | Điểm nóng điển hình | Chỉ tăng bucket có đủ không? |
|---|---|---|
| Partition/key ownership | Nhiều writes vào cùng key/partition | Có thể giúp nếu tạo nhiều partition keys thật |
| Một document/item | Cùng sửa một counter hoặc mảng lớn | Cần thay đổi data model và invariant |
| Index range | Insert liên tục vào một vùng chỉ mục | Có thể cần đổi thứ tự/index/partitioning |
| Shard leader/replica group | Tất cả traffic tới cùng group | Cần phân phối ownership phù hợp |
| Global lock/quorum | Nhiều giao dịch tranh cùng quota | Bucket không tự xóa bất biến cần đồng bộ |
| Network/CPU/disk | Toàn cụm đã bão hòa | Bucket có thể không giúp, thậm chí tăng tải |
| Một tenant “cá voi” | Một tenant chiếm phần lớn traffic | Cần cô lập/định tuyến theo tenant và sub-key |

**Bước đầu tiên phải là xác định bottleneck**, không áp dụng bucketing theo cảm tính. Một truy vấn scan quá nhiều dữ liệu có thể tốn CPU dù partitions phân phối đều. Ngược lại, cùng một key quá nóng có thể gây throttling trong khi CPU trung bình toàn cluster thấp.

## 2. Phân biệt bucket, partition và shard

Ba từ thường được dùng lẫn nhau nhưng không đồng nghĩa:

- **Bucket:** nhóm dữ liệu được ứng dụng chủ động tạo bằng một quy tắc, ví dụ `deviceId + ngày` hoặc `eventId + bucketNo`.
- **Partition:** đơn vị phân bố/định tuyến hoặc phạm vi lưu trữ theo mô hình database; có engine dùng hash partition key, có engine còn có physical partitions riêng.
- **Shard:** một vùng dữ liệu thuộc một shard owner/replica group; chi tiết phụ thuộc công nghệ và topology.

Một bucket ứng dụng **không bảo đảm tương ứng một physical partition**. Engine có thể đặt nhiều logical bucket trên cùng physical node; ngược lại một số hệ có thể tách dữ liệu vật lý theo cơ chế riêng. Kỹ thuật chỉ hiệu quả nếu **quy tắc khóa mới làm luồng ghi phân tán thực sự** trong engine và nếu hệ có đủ capacity ở nhiều ownership units.

Ví dụ:

~~~text
Không bucket:
  PK = "event-42"

Bucket theo thời gian:
  PK = "event-42#2026-11-14"

Bucket có suffix:
  PK = "event-42#2026-11-14#s03"
  PK = "event-42#2026-11-14#s11"
  ...
~~~

Hai cách có thể kết hợp: bucket theo **thời gian** kiểm soát kích thước dữ liệu, suffix theo **phân tán** kiểm soát write concentration.

## 3. Mô hình truy vấn phải được viết trước khi chọn khóa

Giả sử hệ nhận activity events:

~~~json
{
  "eventId": "evt-9d82",
  "tenantId": "t01",
  "deviceId": "device-42",
  "occurredAt": "2026-11-14T10:20:31Z",
  "type": "CLICK",
  "payload": {
    "page": "/products/1001"
  }
}
~~~

Các truy vấn thường gặp:

1. Ghi một event theo `deviceId`, timestamp và `eventId`.
2. Đọc 100 events gần nhất của một device.
3. Đọc sự kiện trong khoảng `[start, end)`.
4. Tìm event theo chính xác `eventId`.
5. Tổng hợp lượt click theo giờ/ngày.
6. Xóa dữ liệu cũ theo retention.
7. Đọc mọi events của một tenant trong ngày để xuất báo cáo.

Nếu 90% request là write và 10% đọc theo device/time, suffix có thể đáng giá. Nếu 90% là “đọc toàn lịch sử thiết bị theo một lần gọi”, quá nhiều suffix có thể làm ứng dụng phải fan-out lớn. Thiết kế phải tối ưu **workload thực**, không chỉ benchmark insert.

### 3.1. Bảng access pattern trước khi chọn model

| Operation | Predicate | Order cần giữ | SLO | Số bucket có thể đọc |
|---|---|---|---|---|
| Ingest event | device, event ID | Không | p99 write | 1 |
| Latest 100 | device | occurredAt giảm dần | p95 GET | Tất cả suffix liên quan |
| Range query | device, [T1,T2) | occurredAt tăng dần | p99 GET | Time buckets × suffix |
| Lookup by ID | eventId | Không | p95 GET | 1 nếu có directory/index |
| Daily aggregate | device/day | Không cần global sort | Batch SLA | Tất cả buckets của ngày |
| Export tenant | tenant/date | Có thể theo key | Batch SLA | Có thể rất nhiều |

Cùng data model có thể phục vụ không tốt mọi operation. Khi lookup by ID phổ biến, cần **directory mapping** hoặc projection/index phù hợp thay vì buộc tìm trong tất cả suffix.

## 4. Chia bucket theo thời gian: giảm độ lớn và cô lập retention

Không bucket:

~~~text
Partition key: deviceId
Sort key: occurredAt#eventId

device-42:
  events từ nhiều năm liên tiếp
~~~

Bucket theo ngày:

~~~text
Partition key: deviceId#YYYY-MM-DD
Sort key: occurredAt#eventId

device-42#2026-11-13
device-42#2026-11-14
device-42#2026-11-15
~~~

Lợi ích:

- Giới hạn lượng dữ liệu của một logical partition theo khoảng thời gian.
- Quét một khoảng thời gian ngắn chỉ chạm buckets liên quan.
- Retention có thể xử lý theo mốc thời gian, tùy engine.
- Dữ liệu lịch sử ít làm nặng truy vấn dữ liệu mới.
- Có thể giới hạn range scan bằng khóa phân vùng + sort order.

Hạn chế:

- Nếu một thiết bị phát **100.000 events/giây**, bucket một ngày vẫn là một hot key.
- “Ngày” theo timezone nào? Nếu client tự chọn local time, bucket có thể lệch; cần chuẩn hóa UTC hoặc rõ policy.
- Event đến muộn phải đặt vào bucket nào: theo `occurredAt` hay thời điểm nhận?
- Cửa sổ truy vấn vượt nhiều ngày phải đọc nhiều buckets.
- Nếu bucket ngày tạo ra partition quá lớn, cần bucket giờ hoặc suffix bổ sung.

**Time bucketing chủ yếu giải kích thước và phạm vi truy vấn; không bảo đảm giải một điểm nóng ghi xảy ra ngay trong một time bucket.**

## 5. Chia bucket theo số lượng hoặc kích thước

Ngoài thời gian, có thể chia theo số bản ghi hoặc dung lượng:

~~~text
order-history#customer-42#bucket-000
order-history#customer-42#bucket-001
order-history#customer-42#bucket-002
~~~

Khi bucket đạt ngưỡng (ví dụ dung lượng ước lượng hoặc số records), tạo bucket mới. Cần một **directory/meta record** cho biết bucket hiện hành.

Nhưng mô hình “ghi tất cả vào bucket mới nhất” vẫn có **một hot current bucket** nếu writes dồn đến rất nhanh. Để phân tán write đồng thời, có thể cần nhiều **active buckets**.

Các vấn đề vận hành:

- Ai quyết định rollover và update directory atomically?
- Hai writers có thể cùng tạo bucket mới không?
- Bucket number có ổn định sau resharding không?
- Một event duplicate có thể rơi vào hai buckets nếu retry không cố định routing?
- Query historical range phải tìm những buckets nào?

Bảng metadata bucket giúp tránh quét vô hạn, nhưng bản thân metadata nóng cũng cần được bảo vệ bằng CAS/atomic update hoặc caching hợp lý.

## 6. Suffix/salt để phân tán luồng ghi

Với một hot logical key `event-42`, chọn `B` số bucket/suffix:

~~~text
PK = event-42#b00
PK = event-42#b01
...
PK = event-42#b15
~~~

Mỗi write được gửi tới một suffix theo quy tắc. Nếu phân bố cân bằng và engine thực sự phân tán ownership, điểm nóng có thể được chia trên nhiều phần.

Các cách chọn suffix:

| Quy tắc | Cách tính | Ưu điểm | Hạn chế |
|---|---|---|---|
| Random | Số ngẫu nhiên trong [0,B) | Phân tán khi IDs thiên lệch | Retry phải biết lại bucket đã chọn |
| Deterministic hash | hash(eventId) modulo B | Cùng event ID luôn cùng bucket | B thay đổi gây đổi mapping |
| Hash theo sub-entity | hash(userId/deviceId) modulo B | Hợp các truy vấn theo sub-entity | Một sub-entity nóng vẫn dồn một bucket |
| Round robin | counter tăng rồi modulo B | Khá đều trên một sequencer | Sequencer có thể trở thành hot key |
| Time slot | phút/giây modulo B | Dễ giải thích theo thời gian | Có thể dồn traffic/khó xử lý burst |
| Adaptive placement | Directory chọn bucket còn capacity | Có thể cân bằng linh hoạt | Metadata/coordination và route lookup phức tạp |

**Random không phải lựa chọn “luôn tốt nhất”**; với idempotency, lookup theo ID và retry sau timeout, deterministic hash từ business/event ID thường dễ quản lý hơn.

## 7. Suffix deterministic từ event ID

Quy tắc khái niệm:

\[
b = H(\mathrm{eventId})\bmod B
\]

Trong đó `H` là hash có phân bố đủ đều và ổn định giữa các phiên bản ứng dụng; `B` là số suffix.

Ví dụ Java (mang tính minh họa):

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class BucketRouter {
    public static int bucket(String eventId, int count) {
        if (count <= 0) throw new IllegalArgumentException("count");
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(
                eventId.getBytes(StandardCharsets.UTF_8)
            );
            long positive = ((long) (hash[0] & 0xff) << 24)
                | ((long) (hash[1] & 0xff) << 16)
                | ((long) (hash[2] & 0xff) << 8)
                | (long) (hash[3] & 0xff);
            return (int) (positive % count);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

Với cùng `eventId` và `count`, cách tính ở trên trả cùng bucket. Đây là lựa chọn **ổn định về mapping** trong phạm vi quy tắc hash đã nêu, không phải giải pháp bảo mật hoặc cryptographic signing. Hash có thể phân bố không hoàn toàn đều, nhưng mục tiêu là tránh lệch nghiêm trọng ở workload thông thường.

Khi thay số bucket từ 16 sang 32, nhiều events cũ sẽ đổi bucket theo công thức mới. **Không tự đọc dữ liệu cũ bằng B=32** nếu chúng được ghi khi B=16. Cần ghi version/epoch/bucketCount hoặc directory để phân biệt.

### 7.1. Đừng hash một giá trị giống nhau cho mọi write

Nếu mọi request tới cùng event pool đều dùng `H(eventId = "event-42")`, tất cả vẫn rơi một bucket. Suffix phải dựa vào **phần khác nhau giữa các write**, như immutable activityEventId, reservationId hoặc client-generated request ID.

Nếu use case là “một counter toàn cục luôn cập nhật cùng record”, việc thêm suffix theo event ID dẫn tới **nhiều counters con** và cần truy vấn sum/aggregation; nó không còn là một counter đơn nguyên tử.

## 8. Random suffix và vấn đề retry

Một writer tạo suffix ngẫu nhiên:

~~~text
POST event(evt-123)
  random bucket = b07
  write event-42#b07/evt-123
  server commit
  response lost

Retry event(evt-123)
  random bucket = b12
  write event-42#b12/evt-123
~~~

Một event có thể xuất hiện hai nơi, dù mỗi bucket có unique event ID cục bộ. Cách an toàn hơn:

- Sử dụng hash deterministic của `eventId`.
- Hoặc lưu mapping `eventId → bucketId` trong một directory có uniqueness/transaction phù hợp.
- Hoặc yêu cầu client gửi **stable idempotency key** và giữ nguyên bucket đã chọn qua các lần thử.
- Nếu dùng random bucket bất biến khi tạo intent, phải lưu lựa chọn trước/đúng consistency boundary với effect để tránh crash window.

Không tự khẳng định uniqueness theo event ID trên toàn hệ chỉ vì từng physical partition ngăn key trùng. Khi suffix nằm trong primary key, hai suffix khác nhau có thể chấp nhận hai records cùng business ID nếu không có cơ chế global uniqueness.

## 9. Đọc một key đã thêm suffix: từ một query thành fan-out

Không suffix:

~~~text
Query partitionKey = event-42
  -> một đường đọc theo owner/partition
~~~

Có 16 suffix:

~~~text
Read event-42:
  -> Query event-42#b00
  -> Query event-42#b01
  ...
  -> Query event-42#b15
  -> Merge results
~~~

Một logical query có thể tạo **B physical queries**. Nếu người dùng yêu cầu tất cả dữ liệu, hệ cần tập kết/hợp nhất từ từng bucket.

Những chi phí phát sinh:

1. Nhiều request RPC/SDK calls và kết nối.
2. Nhiều reads/RCU hoặc CPU per bucket, kể cả buckets rỗng.
3. Truy vấn phân tán qua nhiều replica owners/shards.
4. Bộ nhớ giữ kết quả trung gian.
5. Sắp xếp toàn cục nếu cần theo timestamp/score.
6. Khử trùng khi replay hoặc dual-write migration.
7. Pagination cursor phức tạp hơn.
8. Thời gian xử lý chịu ảnh hưởng **bucket chậm nhất**.
9. Retry partial failures có thể gây reads trùng hoặc tốn thêm bandwidth.
10. Rate limiting và concurrency budget phải tính cả fan-out.

**Phân tán ghi thường đẩy phức tạp sang đọc.** Đây là đánh đổi chủ đạo của bài.

## 10. Mô hình chi phí đọc hợp nhất

Gọi:

- `B`: số buckets cần đọc cho một logical query.
- `Q`: số logical read requests/giây.
- `k`: số items cần trả.
- `L_i`: latency của bucket `i`.
- `c_i`: chi phí đọc bucket `i` theo đơn vị engine.
- `M`: số items phải materialize trước khi trả.

Mô hình lý tưởng khi tất cả bucket queries chạy **song song**:

\[
T_{\mathrm{read}}\gtrsim
\max_{i\in[1,B]} L_i + T_{\mathrm{merge}}
\]

Nếu chia thành từng batch giới hạn concurrency hoặc các calls phụ thuộc nhau, thời gian có thể cao hơn. Tổng chi phí đọc sơ bộ:

\[
C_{\mathrm{read}} = \sum_{i=1}^{B} c_i + C_{\mathrm{merge}}
\]

Nếu mỗi bucket có overhead request cố định, thêm bucket có thể tăng chi phí ngay cả khi tổng dữ liệu đọc không tăng. Nếu chỉ cần `k` record mới nhất, thiết kế cursor/top-k merge tốt có thể giảm số items tải về, nhưng **không tự loại bỏ chi phí mở nhiều streams**.

### 10.1. Ví dụ số giả định

Một endpoint cần latest 50 events. Có 16 suffix; để đảm bảo đủ ứng viên cho global top-50, thuật toán đơn giản lấy tối đa 50 đầu mỗi suffix:

~~~text
16 bucket queries × tối đa 50 items
=> Có thể fetch 800 candidates
=> Global merge và trả 50
~~~

Đây là **upper bound đơn giản về số candidate items cho một vòng**, không có nghĩa mọi bucket luôn có đủ 50, hoặc engine tính phí 800 records giống hệt trong mọi triển khai. Với streaming k-way merge, có thể giảm số lượng thực sự materialize, nhưng request/round trips và pagination của từng bucket vẫn phải được xử lý.

## 11. Điểm chậm nhất có thể chi phối p99

Nếu 16 truy vấn con chạy song song và response cần kết quả từ tất cả buckets, một bucket bị compaction, throttling, GC hay network jitter có thể kéo toàn query chậm.

Trực giác:

~~~text
Bucket b00:  8 ms
Bucket b01: 10 ms
Bucket b02: 11 ms
...
Bucket b15: 320 ms

Global result cannot be complete before slow b15 resolves,
unless API allows partial results with explicit semantics.
~~~

Trong một mô hình đơn giản, tăng số bucket làm tăng khả năng **ít nhất một** truy vấn con chậm. Nhưng không có công thức p99 chung nếu không biết phân phối latency, tương quan lỗi, cơ chế hedging/retry và giới hạn concurrency.

Cần đo **logical request p95/p99**, không chỉ latency trung bình từng physical query. Không được dùng p99 của một bucket để đại diện p99 của kết quả hợp nhất.

## 12. Số buckets tối ưu là bài toán cân bằng hai loại chi phí

Tăng `B` có thể làm mỗi partition giảm write pressure, nhưng tăng read fan-out. Một mô hình mang tính định hướng:

\[
C_{\mathrm{total}}(B) \approx
C_{\mathrm{writes}}(B) +
\alpha\cdot C_{\mathrm{reads}}(B) +
C_{\mathrm{metadata}}(B) +
C_{\mathrm{ops}}(B)
\]

Trong đó `α` phản ánh tần suất và tầm quan trọng của đọc. Đây không phải một hàm có thể tối ưu chính xác khi chưa đo engine.

Ví dụ:

| Bucket count | Tình huống có thể xuất hiện |
|---:|---|
| 1 | Đọc đơn giản, write key có thể nóng |
| 4 | Giảm write concentration vừa phải, fan-out nhỏ |
| 16 | Ghi phân tán hơn, read phải merge nhiều |
| 64 | Cần giới hạn read concurrency, scan nhiều streams |
| 256 | Metadata, empty queries và tail latency có thể đáng kể |

**Không chọn 256 chỉ vì nhiều hơn 16.** Nếu engine thực tế vẫn đặt các buckets vào cùng hot physical partition, lợi ích có thể ít; nếu read-heavy, phần chi phí đọc có thể vượt lợi ích của phân tán ghi.

## 13. Chọn bucket count từ lưu lượng ghi và năng lực thực đo

Giả sử hot logical key nhận `λ_hot` writes/giây, và một physical ownership unit phục vụ bền vững `μ_safe` writes/giây ở payload, index và SLO hiện tại. Nếu chia đều:

\[
B_{\min}\approx \left\lceil\frac{\lambda_{\mathrm{hot}}}{\mu_{\mathrm{safe}}}\right\rceil
\]

Ví dụ giả định `λ_hot=12.000` writes/s, mức **an toàn đã đo** là `μ_safe=600` writes/s cho mỗi bucket được định tuyến độc lập:

\[
B_{\min}=\lceil12.000/600\rceil=20.
\]

Có thể thử `B=24` hoặc `B=32` để có headroom; đây **không phải cam kết 32 buckets sẽ đạt 12.000 writes/s**. Bởi vì:

- Hash có thể lệch khi một vài sub-entities chiếm phần lớn traffic.
- Nhiều logical buckets vẫn có thể được đặt trên một physical partition/leader.
- Ghi có indexes, transactions, replication, journal, compression và rate limits.
- Quota áp ở table/account/node có thể giới hạn tổng throughput.
- Hot item conflict không biến mất nếu mỗi write còn phải cập nhật một record tổng.
- Các burst 1 giây có thể lớn hơn traffic trung bình 1 phút.

### 13.1. Bổ sung headroom

Nếu muốn mỗi bucket chỉ dùng tỷ lệ `u` của khả năng đã đo, ví dụ `u=0,7`:

\[
B \gtrsim \left\lceil
\frac{\lambda_{\mathrm{peak}}}
{u\cdot\mu_{\mathrm{measured}}}
\right\rceil.
\]

Phải đo `μ_measured` với đúng kích thước item, index count, replication mode và concurrency; không áp một con số marketing tối đa cho mọi workload. Tăng B từng nấc, đo write p99, throttling và bucket skew có giá trị hơn một công thức đơn độc.

## 14. Kích thước bucket và write rate là hai ràng buộc khác nhau

Ví dụ giả định:

- Một thiết bị phát 2.000 events/giây.
- Trung bình 1 KiB payload logic mỗi event.
- Bucket theo giờ, không có suffix.

Số events một giờ:

\[
2.000\times 3.600=7.200.000.
\]

Dung lượng payload xấp xỉ 7,2 GiB thập phân, **chưa tính index, metadata, replication, compression, logs hoặc overhead engine**. Bucket ngày có thể lớn hơn 24 lần.

Có thể kết hợp time bucket và suffix:

~~~text
PK = deviceId#UTC-hour#salt
SK = occurredAt#eventId

device-42#2026-11-14T10#b00
device-42#2026-11-14T10#b01
...
device-42#2026-11-14T10#b15
~~~

Query 3 giờ phải xét tối đa `3×16=48` bucket keys nếu cả 16 suffix đều hoạt động. Directory metadata có thể giúp bỏ qua những bucket chưa hề được tạo.

## 15. Sort key giúp hợp nhất hiệu quả

Để merge không cần tải toàn bộ rồi sort, từng bucket nên có thứ tự phục vụ truy vấn:

~~~text
Partition key: tenantId#deviceId#hour#salt
Sort key:      occurredAt#eventId
~~~

Nếu engine hỗ trợ range/ordered scan theo sort key, truy vấn trên từng bucket trả stream sorted theo thời gian. Ứng dụng hợp nhất streams thay vì global in-memory sort toàn bộ dữ liệu.

Chú ý:

- Dùng timestamp UTC và kiểu/format sortable ổn định.
- Nhiều events có thể cùng timestamp; `eventId` làm tie-breaker.
- “Mới nhất được nhận” có thể cần `ingestedAt` thay vì `occurredAt`.
- Late events có `occurredAt` cũ; cần định nghĩa cách chúng xuất hiện trong pagination.
- Nếu update event sort key, engine có thể cần delete/insert lại.
- Order key phải là **thứ tự toàn phần**, nhất quán ở từng stream và merge.

## 16. K-way merge cho các streams đã sorted

Giả sử từng bucket trả events theo thời gian giảm dần:

~~~text
Bucket b00: 10:08/E8, 10:06/E6, 10:02/E2
Bucket b01: 10:07/E7, 10:05/E5
Bucket b02: 10:09/E9, 10:04/E4, 10:01/E1
~~~

Kết quả:

~~~text
10:09/E9, 10:08/E8, 10:07/E7, 10:06/E6,
10:05/E5, 10:04/E4, 10:02/E2, 10:01/E1
~~~

Một **priority queue/heap** giữ phần tử đầu của từng stream. Mỗi lần lấy phần tử mới nhất ra, đưa phần tử tiếp theo từ đúng stream đó vào heap.

Với `B` streams và `k` phần tử trả ra, heap work:

\[
T_{\mathrm{merge}}=O(k\log B)
\]

chưa tính DB I/O, network, decompression, pagination và dedup. Heap giữ O(B) stream heads; các page buffers cần thêm bộ nhớ.

### 16.1. Python ví dụ với các streams trong RAM

~~~python
from heapq import heappush, heappop
from datetime import datetime


def microseconds(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone required")
    return int(dt.timestamp() * 1_000_000)


def merge_newest(streams, limit):
    # Giả định từng stream được sort DESC theo occurredAt.
    heap = []
    result = []

    for bucket, items in streams.items():
        if items:
            heappush(
                heap,
                (-microseconds(items[0]["occurredAt"]), bucket, 0)
            )

    while heap and len(result) < limit:
        _, bucket, index = heappop(heap)
        result.append(streams[bucket][index])
        following = index + 1
        if following < len(streams[bucket]):
            item = streams[bucket][following]
            heappush(
                heap,
                (-microseconds(item["occurredAt"]), bucket, following)
            )
    return result


streams = {
    "b00": [
        {"eventId": "E8", "occurredAt": "2026-11-14T10:08:00Z"},
        {"eventId": "E6", "occurredAt": "2026-11-14T10:06:00Z"},
    ],
    "b01": [
        {"eventId": "E7", "occurredAt": "2026-11-14T10:07:00Z"},
        {"eventId": "E5", "occurredAt": "2026-11-14T10:05:00Z"},
    ]
}
print([r["eventId"] for r in merge_newest(streams, 3)])
# ['E8', 'E7', 'E6']
~~~

Đây là ví dụ **minh họa thuật toán merge**, chưa kết nối database. Với timestamps trùng, code trên sử dụng bucket name làm tie-breaker; sản phẩm thật nên dùng **global composite key** như `(occurredAt,eventId)` và thực hiện cùng thứ tự tại query, heap và cursor. Để giảm memory khi database trả phân trang, thêm lazy fetch per-stream và trạng thái continuation.

## 17. Vì sao LIMIT K/B không đảm bảo top-K toàn cục?

Một ý tưởng sai: cần latest 100, có 10 buckets, vậy mỗi bucket chỉ lấy 10 records.

Phản ví dụ:

~~~text
Bucket b00 chứa 100 events mới nhất toàn hệ.
Các bucket khác chứa toàn events cũ.

Đọc 10 từ b00 và 10 từ 9 bucket còn lại
=> Thiếu 90 events mới của b00.
~~~

Khi không biết ranh giới của mỗi stream, lấy **tối đa K từ mỗi bucket** rồi top-K toàn cục là một baseline dễ suy luận cho dữ liệu snapshot cố định, nhưng có thể tải đến `B×K` candidates.

Chiến lược tốt hơn là **lazy k-way merge**:

1. Lấy một page nhỏ từ mỗi bucket.
2. Đưa phần tử đầu mỗi stream vào heap.
3. Mỗi lần emit một item, chỉ fetch thêm từ stream đã cạn.
4. Dừng khi đủ K kết quả hợp lệ.
5. Lưu cursor có khả năng resume.

Nó giảm data transfer trong nhiều workload, nhưng vẫn phải trả chi phí fan-out và không tự tạo snapshot toàn cục.

## 18. Prune time buckets trước khi merge

Ví dụ request:

~~~text
GET events?device=device-42
  &start=2026-11-14T10:20:00Z
  &end=2026-11-14T12:05:00Z
~~~

Với `PK=deviceId#hour#salt` và `B=16`, cần xét các giờ 10, 11, 12, tối đa 48 partition keys. Loại tất cả giờ ngoài query window, sau đó dùng sort-key range predicate trong mỗi bucket nếu engine hỗ trợ.

Cần xác định:

- Timezone chung có phải UTC?
- Truy vấn sử dụng khoảng nửa mở `[start,end)` để tránh trùng boundary?
- Event đến muộn được bucket theo event time hay ingestion time?
- TTL/retention có khiến bucket cũ rỗng không?
- Directory có thể xác định bucket nào chưa từng được tạo không?
- Query mới nhất có thể ngừng sớm khi một watermark đáng tin chứng minh các bucket cũ không chứa record cạnh tranh không?

## 19. Fan-out read có thể nhân tải hệ thống

Nếu endpoint nhận `Q` logical requests/s và mỗi request chạm trung bình `B_touched` buckets:

\[
\text{Subqueries/s}\approx Q\cdot E[B_{\mathrm{touched}}].
\]

Ví dụ giả định 300 GET/s, 24 bucket queries/GET:

\[
300\times24=7.200\ \text{subqueries/s}.
\]

Đây là số calls logic, **không mặc định là số physical connections hay read capacity units**; SDK có thể multiplex, batch, cache, và engine có unit accounting riêng.

Giải pháp giới hạn overhead:

- Prune time buckets và không query buckets rỗng.
- Giới hạn range, result size và page size.
- Bounded concurrency, connection pool và deadline tổng.
- Tránh per-bucket retry vô hạn.
- Dùng cached latest-K hoặc materialized read projection cho hot reads.
- Đẩy các báo cáo nặng sang async jobs/analytical store.
- Khi có hot tenant, áp quota và read fan-out budget theo tenant.

## 20. Scatter–gather với backpressure

~~~mermaid
flowchart TD
    A["GET latest events"] --> B["Resolve bucket keys và routing epochs"]
    B --> C["Fan-out với concurrency limit"]
    C --> D["Fetch sorted pages"]
    D --> E["Heap merge + dedupe"]
    E --> F{"Đủ K hợp lệ?"}
    F -->|Chưa| G["Fetch next page từ stream cần"]
    G --> D
    F -->|Rồi| H["Return items + opaque cursor"]
~~~

Nếu một bucket timeout:

- **Fail toàn request** nếu caller yêu cầu kết quả chính xác đầy đủ.
- **Partial response** khi API contract cho phép, phải báo `partial=true` và missing buckets.
- **Retry bucket** với budget giới hạn; không kéo dài deadline vô hạn.
- **Stale fallback** khi ứng dụng cho phép, phải công bố tuổi dữ liệu.

Không được âm thầm trả “50 mới nhất” khi bucket đang lỗi có thể chứa event mới nhất. Khi ấy kết quả **không đầy đủ**, dù HTTP vẫn có thể trả 200 theo một API contract khác.

## 21. Pagination toàn cục phức tạp hơn từng bucket

Một cursor cho multi-bucket query thường cần:

- Query filters, sort order và tenant identity.
- Routing epoch/bucket count áp dụng cho dữ liệu đang đọc.
- Composite global last-emitted key với tie-breaker.
- Continuation token/last consumed key của từng bucket.
- **Các fetched items chưa emit**, hoặc một quy tắc refetch tương đương.
- Snapshot/commit cutoff nếu API hứa consistency theo một thời điểm.
- Query hash/version tránh dùng cursor sai filter.
- Expiry, signature và authorization.

Ví dụ cấu trúc khái niệm:

~~~json
{
  "cursorVersion": 2,
  "tenantId": "t01",
  "queryHash": "sha256:...",
  "routingEpochs": [4, 5],
  "lastEmitted": ["2026-11-14T10:07:00Z", "evt-007"],
  "streams": {
    "hour10#b00": {"nextToken": "...", "bufferOffset": 3},
    "hour10#b01": {"nextToken": "...", "bufferOffset": 1}
  },
  "expiresAt": "2026-11-14T10:25:00Z"
}
~~~

Đây chỉ là một **mẫu trạng thái phân trang**. Đừng truyền nguyên tokens SDK hoặc metadata nhạy cảm cho client không bảo vệ. Có thể dùng encrypted/signed opaque cursor hoặc server-side cursor state với handle và TTL.

Kích thước cursor có thể tăng theo B; hàng trăm streams có thể khiến cursor URL quá lớn. Chọn server-side state khi phù hợp, đồng thời tính chi phí storage, cleanup và cursor expiry.

## 22. Cursor phải giữ items đã fetch nhưng chưa emit

Giả sử bucket b00 trả page 20 records, global merge chỉ dùng 3 records từ b00 trước khi đủ page user. Nếu lưu **SDK next-page token sau record thứ 20** mà không giữ 17 records chưa emit, lần tiếp theo sẽ bỏ qua 17 records.

Ba hướng xử lý:

1. Giữ buffer chưa dùng trong cursor state.
2. Advance position theo **record cuối đã tiêu thụ**, không theo cuối page đã tải, nếu engine cho phép.
3. Refetch từ composite last-emitted key bằng predicate phù hợp, chấp nhận chi phí đọc lặp nhưng không bỏ sót.

Phải chứng minh correctness khi pagination theo nhiều streams, gồm trường hợp một bucket hết page, token bị timeout và route epoch đổi giữa chừng.

## 23. Snapshot và live feed thay đổi giữa các trang

~~~text
Page 1 được đọc lúc 10:00:00.
Event E101 mới được ghi lúc 10:00:01.
Page 2 được đọc lúc 10:00:02.
~~~

Nếu page 2 dùng offset như `skip=50`, E101 có thể đẩy các record cũ sang vị trí khác, dẫn tới duplicate hoặc missing. Keyset/cursor theo composite key giảm một số vấn đề, nhưng cần nêu rõ:

- API hứa **snapshot cố định** hay **live feed**?
- Event mới sau page 1 có được xuất hiện ở page 2 không?
- Late events có occurredAt cũ hơn cursor có xuất hiện không?
- Delete/tombstone giữa pages được xử lý thế nào?
- Reads từ nhiều buckets có cùng consistency mode không?
- Nếu engine không hỗ trợ global snapshot, có chấp nhận **best effort** không?

Một high-water mark/commit cutoff đáng tin có thể giúp giới hạn dữ liệu đã tồn tại ở thời điểm page 1, nhưng timestamp do client tự phát **không tự tạo một global snapshot** nếu database không cung cấp các bảo đảm tương ứng.

## 24. Dedupe và uniqueness khi cùng một event có thể vào nhiều bucket

Khi mỗi bucket là một key space khác nhau, constraint uniqueness của `(partitionKey, sortKey)` thường chỉ bảo vệ **bản ghi ở đúng partition đó**. Nếu cùng business ID có thể xuất hiện ở hai suffix, rất dễ nhân đôi data.

~~~text
event-42#b03 / evt-1001
event-42#b11 / evt-1001
~~~

Ở tầng đọc, một `seenEventIds` set có thể loại duplicate khỏi response. Nhưng **dedupe khi đọc không sửa được toàn bộ hậu quả của double-write** nếu event đó đã kích hoạt counter, payment, webhook hoặc alert hai lần.

Phân biệt:

| Mục tiêu | Biện pháp thường dùng |
|---|---|
| Retry một event không tạo 2 records | Routing suffix deterministic theo stable eventId |
| Hai writers cùng eventId chỉ một được nhận | Unique key/conditional insert trong phạm vi bảo đảm |
| Same eventId có thể đã chuyển bucket qua epoch | Global ID mapping hoặc transaction/dedup ledger |
| Response không trùng trong lúc migration | Dedupe theo business/event ID |
| Projection/counter không cộng hai lần | Consumer idempotency theo eventId |
| Payload khác nhưng cùng ID | Fingerprint conflict, không lấy last-write-wins mù |

**Bucket key và business key không luôn là một.** Một record có thể dùng `(timeBucket,salt,eventId)` để trải tải, nhưng ứng dụng còn cần cách tìm/khóa `eventId` duy nhất ở cấp nghiệp vụ.

## 25. Lookup theo ID: cần một đường định tuyến khác

Nếu người dùng biết `eventId` nhưng không biết `hourBucket` hoặc `salt`, query toàn bộ data có thể đắt.

Ba thiết kế:

### 25.1. Định tuyến được tính lại từ ID

Nếu `salt=hash(eventId)%B` và time bucket được chứa trong business ID hoặc request metadata bất biến, lookup có thể tính lại khóa.

Điều kiện: phải biết **routing epoch/bucket count đã dùng khi write** và time bucket. Nếu event ID không mã hóa thời gian và record không có metadata sẵn, không thể tự tính được hour.

### 25.2. Directory mapping

Một map:

~~~json
{
  "eventId": "evt-1001",
  "tenantId": "t01",
  "routingEpoch": 4,
  "partitionKey": "t01#device-42#2026-11-14T10#b07",
  "sortKey": "2026-11-14T10:20:31Z#evt-1001"
}
~~~

Lookup: `Get directory by eventId → Get event by full primary key`. Chi phí thêm một lookup/metadata record, đổi lại tránh scan nhiều buckets.

Cần bảo đảm directory và record không rơi vào trạng thái bất nhất khi worker crash. Nếu engine hỗ trợ transaction phù hợp, có thể ghi chúng atomically; nếu không, cần repair/reconciliation và idempotency policy.

### 25.3. Secondary index hoặc projection

Có thể dùng index theo eventId. Nhưng index cập nhật bất đồng bộ (nếu công nghệ/chế độ đó như vậy) có thể lag. Với một API cần read-your-writes hoặc dùng ID làm quyết định quan trọng, phải xem read consistency của đường index, không suy index luôn authoritative.

## 26. Counter phân tán: nhiều ô đếm nhỏ thay một ô nóng

Giả sử mọi lượt view cập nhật một counter:

~~~text
counter:product-1001 = 1_000_000
~~~

Để tránh tranh một item, dùng `B` counters:

~~~text
counter:product-1001#b00 = 100_100
counter:product-1001#b01 =  99_940
...
counter:product-1001#b09 =  99_960
~~~

Mỗi event chọn suffix. Kết quả cuối:

\[
\text{views(product)}=\sum_{b=0}^{B-1}\text{counter}(product,b).
\]

Ưu điểm: ghi có thể phân tán theo nhiều counters. Đánh đổi: một logical read cần đọc/sum nhiều counters, và kết quả có thể stale hoặc thiếu nếu một bucket lỗi.

**Quan trọng:** một counter phân tán không tự idempotent. Một `viewEventId` retry có thể tăng hai lần. Nếu metric cần count chính xác, phải có dedup event log hoặc cơ chế idempotency phù hợp. Nếu metric là thống kê xấp xỉ, API cần công bố error/aggregation policy.

### 26.1. Vì sao không dùng phân tán counter cho quota cứng một cách ngây thơ?

Nếu chỉ kiểm tra:

~~~text
SUM(available across buckets) >= requestedQuantity
~~~

rồi cập nhật một bucket riêng, hai clients có thể cùng nhìn tổng đủ và cùng cấp vượt capacity nếu thiếu giao thức atomic toàn cục. **Sum nhiều counters** không bảo vệ một invariant mạnh dưới concurrent writes.

Có thể cân nhắc:

- Một authoritative quota owner với conditional update.
- Escrow/quota rights được phân bổ trước cho mỗi bucket/region.
- Transaction/consensus phù hợp với scope.
- Reservation ledger và state machine có compensation.

Một bài toán cộng “views” khác hoàn toàn bán **một chiếc vé cuối**. Bản chất business invariant quyết định có thể chia write độc lập tới đâu.

## 27. Escrow quota: làm cho bucket thật sự có quyền cấp phát riêng

Một phương án cho quota tổng 1.000:

~~~text
Total capacity: 1000
Escrow rights:
  b00 = 150
  b01 = 150
  b02 = 150
  b03 = 150
  b04 = 150
  b05 = 150
  unallocated = 100
~~~

Mỗi bucket chỉ được cấp trong hạn mức quyền nó sở hữu. Tổng quyền đã cấp cộng chưa cấp phải bằng capacity theo invariant được công bố.

Việc phân quyền/điều chuyển cần:

1. Một nguồn có thẩm quyền xác nhận transfer rights.
2. Bucket nguồn không tiếp tục cấp phần đã chuyển.
3. Bucket đích không cấp quyền trước khi nhận transfer hợp lệ.
4. Mỗi transfer ID được xử lý idempotent dù client timeout.
5. Khi một bucket hết quyền còn bucket khác dư, rebalancing không gây oversell.
6. Nếu mạng partition, có thể tạm từ chối ở một bucket dù nơi khác còn quota: đây là đánh đổi.

Escrow làm giảm nhu cầu đồng bộ **trên từng request** bằng cách đồng bộ **theo lô chuyển quyền**, nhưng không xóa bài toán bảo toàn quota.

## 28. DynamoDB: write sharding bằng suffix và chi phí Query

Một mô hình DynamoDB cho event log theo device/day:

~~~text
PK = "TENANT#t01#DEVICE#device-42#DAY#2026-11-14#SALT#07"
SK = "AT#2026-11-14T10:20:31Z#EVENT#evt-1001"
~~~

Router có thể chọn `salt=hash(eventId)%B`. Khi ghi, `PutItem` vào đúng PK/SK, có thể dùng conditional create-only nếu cần tránh overwriting cùng PK/SK.

Đọc tất cả events của ngày bằng Query:

~~~text
for salt in 0 .. B-1:
    Query(
      PK = makePk(tenant, device, day, salt),
      sortKeyRange = [start, end)
    )
merge results by (occurredAt, eventId)
~~~

Đây là pseudocode vì SDK có cấu trúc request và expression riêng. Ưu điểm so với table scan là đã biết đầy đủ các partition keys cần query. Nhưng mỗi suffix có thể phát sinh một Query/Read capacity và pagination riêng; còn phải tính projection, consumed capacity, item size, throttling và max logical concurrency.

DynamoDB có physical partitioning, adaptive capacity, partition key distribution và các giới hạn cụ thể của dịch vụ. **Không khẳng định một suffix luôn đồng nghĩa một physical partition**, hoặc B buckets làm write throughput tăng tuyến tính. Nếu đọc qua GSI, cần lưu ý consistency/lag của GSI và khả năng tạo hot index key mới.

### 28.1. Counter phân tán trong DynamoDB

Một thiết kế counter gồm các items:

~~~text
PK = COUNTER#product-1001
SK = BUCKET#00
...
SK = BUCKET#15
~~~

Nếu DynamoDB partitioning dựa chủ yếu trên cùng một partition key như schema này, những items cùng PK có thể vẫn dồn về một logical partition key, **không đạt mục tiêu phân tán write sharding**. Để salt ảnh hưởng routing, nên đặt nó trong **partition key**, ví dụ:

~~~text
PK = COUNTER#product-1001#B#00
SK = STATE
~~~

Sau đó GET tổng cần đọc các PK khác nhau và sum. Sự khác biệt giữa suffix ở **sort key** và suffix trong **partition key** là cốt lõi.

## 29. Cassandra/ScyllaDB: time bucket kết hợp salt trong partition key

Ví dụ CQL schema:

~~~sql
CREATE TABLE events_by_device_hour_salt (
    tenant_id text,
    device_id text,
    hour_bucket text,
    salt int,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket, salt),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id DESC
);
~~~

Trong model này, partition key là **bộ bốn** `(tenant_id,device_id,hour_bucket,salt)`. Khi query:

~~~sql
SELECT occurred_at, event_id, event_type
FROM events_by_device_hour_salt
WHERE tenant_id = 't01'
  AND device_id = 'device-42'
  AND hour_bucket = '2026-11-14T10'
  AND salt = 7
  AND occurred_at >= '2026-11-14T10:15:00Z'
  AND occurred_at <  '2026-11-14T11:00:00Z'
LIMIT 50;
~~~

Cần query các `salt` phù hợp rồi merge ở application nếu muốn toàn bộ device/hour. Không suy rằng CQL sẽ tự đọc **mọi partition keys** chỉ vì một số trường prefix đã được cung cấp. Hạn chế của `IN`, `ALLOW FILTERING`, clustering order và server paging thay đổi theo schema/phiên bản; tránh dùng full scan để thay fan-out có kiểm soát.

### 29.1. TTL, tombstones và đọc nhiều buckets

Nếu dùng TTL/retention, mỗi bucket có thể tích lũy tombstones và compaction costs. Quét 16 buckets nhiều tombstones có thể đọc nặng hơn một danh sách ít records sống. Một workload write-heavy với TTL ngắn cần đo cả read latency, tombstone warnings và disk/compaction backlog.

Khi chọn time bucket lớn để giảm số partitions, có thể tạo partition quá lớn. Khi chọn quá nhỏ, metadata/bucket fan-out tăng. Mức hợp lý phụ thuộc volume per key, item size, query window và repair/retention policy.

## 30. MongoDB: bucket trong document và suffix trong shard key là hai kỹ thuật khác

MongoDB có thể dùng “bucket pattern” theo nghĩa **gộp nhiều events vào một document** để giảm số documents/index entries khi hợp lý:

~~~javascript
{
  _id: "device-42#2026-11-14T10#batch-001",
  deviceId: "device-42",
  hour: "2026-11-14T10",
  items: [
    {eventId: "e1", occurredAt: ISODate("2026-11-14T10:01:00Z")},
    {eventId: "e2", occurredAt: ISODate("2026-11-14T10:02:00Z")}
  ],
  count: 2
}
~~~

Đây là **gộp dữ liệu vào documents**; nó có thể làm giảm overhead index/metadata, nhưng nếu mọi writer cập nhật cùng document `$push` thì chính document bucket trở thành **hot document** và lớn dần. Cần giới hạn document size, rollover, concurrency control và quy tắc update.

Kỹ thuật **thêm suffix vào partition/shard key** khác:

~~~javascript
{
  tenantId: "t01",
  deviceId: "device-42",
  hourBucket: "2026-11-14T10",
  salt: 7,
  eventId: "evt-1001",
  occurredAt: ISODate("2026-11-14T10:20:31Z")
}
~~~

Một index phục vụ đọc theo bucket:

~~~javascript
db.events.createIndex({
  tenantId: 1,
  deviceId: 1,
  hourBucket: 1,
  salt: 1,
  occurredAt: -1,
  eventId: -1
});
~~~

Đây là **ví dụ query index**, không tự cấu hình collection sharding. Muốn writes phân tán qua shards, **shard key thực tế phải giúp tách các values nóng**; nếu shard key chỉ gồm `tenantId+deviceId` mà không bao gồm thành phần phân tán có tác dụng, ghi cùng device có thể vẫn dồn một shard dù field `salt` được lưu trong document.

MongoDB hashed sharding cũng không tự giải quyết một giá trị shard key cực nóng: băm cùng một giá trị vẫn tạo cùng kết quả. Phải kiểm tra range/hashed/compound shard-key semantics và targetability của các queries trên phiên bản MongoDB đang dùng.

## 31. Redis Cluster: hash tags có thể vô tình gom mọi suffix về một slot

Redis Cluster dùng hash slots để phân phối keys. Với keys:

~~~text
events:{event-42}:b00
events:{event-42}:b01
events:{event-42}:b02
~~~

Phần nằm trong dấu ngoặc nhọn dùng làm hash tag; cùng `{event-42}` sẽ khiến các keys được định tuyến về **cùng hash slot**. Dù có suffix ngoài tag, ta có thể **không phân tán ghi theo mục tiêu**.

Một layout phân tán slots có thể dùng salt bên trong tag:

~~~text
events:{event-42-b00}:data
events:{event-42-b01}:data
events:{event-42-b02}:data
~~~

Nhưng khi keys nằm ở nhiều slots, các thao tác nhiều key/script/transaction của Redis Cluster có giới hạn khác; không thể tùy tiện thực hiện một Lua script atomically trên tất cả suffix khác slots.

Với counter:

~~~text
INCR views:{product-1001-b03}:count
INCR views:{product-1001-b10}:count
~~~

Đọc total phải GET các buckets rồi sum. Nếu muốn exact total cùng lúc có nhiều writes, cần xem snapshot/read consistency/atomicity, không tự xem tổng các replies ở những thời điểm khác nhau là một transaction toàn cục.

### 31.1. Redis phù hợp hơn với counter nào?

Các counters như page views, hit metrics hoặc approximate analytics thường phù hợp phân tán và đọc tổng eventual. Quota không được vượt (coupon cuối cùng, ticket cuối) cần invariant mạnh hơn, không thể tự đảm bảo bằng cách sum counters từ nhiều Redis slots không có protocol điều phối.

## 32. Search engine: routing và time-based indices

Ở các search engines có cơ chế index partitioning/shard routing, một hot routing key có thể tập trung ghi vào một shard. Nếu thêm suffix routing để trải writes, tìm toàn bộ dữ liệu theo user/event có thể phải truy vấn nhiều shard/routing values.

Ví dụ khái niệm:

~~~text
index = events-2026-11-14
routing = device-42#salt-07
documentId = evt-1001
~~~

Nếu tìm bằng `documentId` mà không biết routing, có thể phải mở rộng phạm vi truy vấn hoặc lookup directory. Một index thời gian theo ngày giảm phạm vi lịch sử, nhưng không tự giải hot routing value trong ngày hiện tại.

Search engine thường có refresh/segment merge và indexing visibility khác source transactional DB. Không dùng index search có thể stale làm nguồn quyết định giữ hàng hoặc thanh toán. Một kết quả search top-K tổng hợp có thể dùng coordinator merge với chi phí shard fan-out và heap/sort riêng; cần đọc hướng dẫn routing và shard count của sản phẩm thực tế.

## 33. Multi-tenant: bucket không thay thế tenant isolation

Một tenant rất lớn có thể tạo hot keys dù các tenants khác bình thường. Một key:

~~~text
PK = tenantId#deviceId#hour#salt
~~~

giúp phạm vi data rõ, nhưng cần thêm:

- Quota writes/reads theo tenant, tránh một tenant chiếm hết capacity.
- Giới hạn fan-out per logical request và concurrency per tenant.
- TTL/retention và data access control theo tenant.
- Tenant-specific bucket count nếu workload rất khác nhau, kèm routing metadata.
- Tránh thông tin tenant khác lọt qua directory, cursor, cache hoặc result merge.
- Shard placement thực tế: các tenants nóng có đổ về cùng physical node không?
- Không lấy salt làm công cụ bảo mật hoặc cơ chế phân quyền.

Nếu mỗi tenant có bucket count riêng, toàn bộ writers/readers phải biết chính xác `B(tenant,epoch)`; nếu metadata stale, có thể ghi sai bucket hoặc không đọc đủ dữ liệu.

## 34. Thay đổi số bucket: không thể chỉ sửa biến cấu hình

Ban đầu:

~~~text
Routing epoch 1:
  B = 8
  salt = hash(eventId) % 8

Sau nâng cấp:
  Routing epoch 2:
  B = 32
  salt = hash(eventId) % 32
~~~

Nếu chỉ đổi B từ 8 sang 32, event đã ghi với B=8 có thể nằm ở địa chỉ khác địa chỉ tính lại khi B=32. **Không được mất đường đọc dữ liệu cũ**.

Các mô hình migration:

1. **New writes dùng epoch mới, old writes giữ epoch cũ.** Reader biết query cả hai epochs cho time ranges còn dữ liệu.
2. **Backfill dần dữ liệu cũ** sang bucket mới, có dedup theo event ID và checkpoint.
3. **Directory mapping** lưu epoch và bucket thực của từng event.
4. **Dual-write có kiểm soát** chỉ khi đã có idempotency, reconciliation và quy tắc chọn một nguồn; nếu không có thể tăng writes, nhân đôi counters và tạo kết quả lặp.
5. **Rebuild read projection** cho các truy vấn thường xuyên, thay vì ép toàn bộ readers đọc cả hai layouts mãi mãi.

### 34.1. Routing epoch và các client cũ

Với dịch vụ có nhiều phiên bản cùng chạy, phải xác định:

- Writers cũ có được viết epoch 1 nữa không?
- Lúc chuyển epoch, cần fence/disable writers cũ thế nào?
- Readers mới có query mọi epochs còn data không?
- Cursor đã phát theo epoch 1 có còn dùng được?
- Nếu backfill đang chạy, có chống duplicate qua hai epochs không?
- Khi cắt epoch cũ, có bằng chứng mọi records đã chuyển hoặc đã hết retention không?

Migration không chỉ là vấn đề performance; nó liên quan correctness của lookup, retry và visibility.

## 35. Dual-read trong giai đoạn chuyển đổi

Một thời gian hệ có thể phải đọc cả old và new layouts:

~~~text
Old layout (epoch 1): B=8
New layout (epoch 2): B=32

Logical query:
  Query 8 old buckets
  Query 32 new buckets
  Merge + dedupe by eventId
~~~

Fan-out tăng từ 8 hoặc 32 lên **tối đa 40** trong thời gian chuyển tiếp. Đây là chi phí cần tính vào capacity budget/migration rollout. Cần pruning theo time/epoch để không mở 40 queries cho mọi read nếu dữ liệu epoch 1 đã kết thúc ở một thời điểm xác định.

Một event có thể xuất hiện ở cả hai layouts khi backfill/dual-write. **Dedupe response** cần business ID, nhưng với aggregate sums phải tránh cộng cả hai bản. Chọn một nguồn theo epoch/version, hoặc ghi movement/aggregate theo idempotent process.

## 36. Kết thúc migration phải có điều kiện rõ

Không xóa old buckets ngay sau khi hệ “chạy có vẻ ổn”. Cần có bằng chứng:

- Mọi writers đã chuyển sang epoch mới hoặc được fence.
- Backfill đã hoàn tất theo checkpoint, counts và payload digests.
- Data mới ghi trong migration không có gaps.
- Readers không còn phụ thuộc old epoch theo active cursors.
- Retry requests dùng business IDs cũ vẫn tìm được outcome.
- Projection/search/analytics đã hội tụ.
- Backup/PITR và restore runbook hiểu layout mới.
- TTL/retention của old data được thực thi an toàn.
- Old buckets có thể bị xóa sau khi xác nhận business obligations đã hoàn tất.

Với dữ liệu chỉ append-only và retention ngắn, có thể cho old buckets tự hết hạn thay vì backfill toàn bộ. Với dữ liệu giao dịch tồn tại lâu, cần directory hoặc migration có kiểm chứng.

## 37. Đo độ lệch giữa các bucket (bucket skew)

“Có 32 buckets” không chứng minh traffic chia đều. Cần đo `writesPerBucket` và `bytesPerBucket` theo khoảng thời gian ngắn (ví dụ một phút và các cửa sổ peak ngắn hơn).

Một vài metric định hướng:

\[
\text{Skew ratio} =
\frac{\max_i(\mathrm{writesPerBucket}_i)}
{\frac{1}{B}\sum_i \mathrm{writesPerBucket}_i}
\]

Nếu 16 buckets có trung bình 500 writes/s nhưng bucket nóng nhất 2.000 writes/s:

\[
\text{Skew ratio}=2.000/500=4.
\]

Điều này gợi ý một bucket tải gấp 4 lần trung bình. Nhưng chưa thể kết luận nguyên nhân chỉ từ con số:

- Hash input có giá trị đủ phân tán không?
- Random function/seed có lỗi hoặc bị cắt bớt entropy không?
- Một số bucket có được tạo/định tuyến ít hơn do rollout không?
- Hai bucket logic có bị đặt cùng node/shard leader không?
- Có retry storm tới một vài business IDs?
- Thước đo `writesPerBucket` có bị lấy mẫu thiếu hoặc có double-count không?
- Một nhóm tenant/hot event có tạo traffic nặng bất đối xứng không?

### 37.1. Báo cáo cả skew vật lý và logic

| Mức đo | Ví dụ metric | Điều phản ánh |
|---|---|---|
| Logical buckets | Requests/s theo suffix | Thuật toán routing có cân không? |
| Partition keys | Requests/s theo full partition key | Key nào đang hot? |
| Physical owners | CPU/disk/network/request p99 theo node/shard | Capacity có thực sự phân bố không? |
| Tenant | Writes/reads theo tenant | Hot tenant ảnh hưởng ai? |
| Query fan-out | Buckets touched / logical GET | Chi phí read path |
| Business result | Missing/duplicate events | Tính đúng đắn còn không? |

Nếu suffix phân phối đều 32 buckets nhưng tất cả được engine đặt vào cùng một physical owner, skew logic đẹp mà physical hot spot chưa biến mất. Cần quan sát **cả hai tầng**.

## 38. Cẩn thận với hash input và phân phối không đều

Một số quy tắc nhìn có vẻ hợp lý nhưng gây lệch:

~~~text
Bad idea A:
  salt = hash(deviceId) % 16
  -> mọi events của một hot device cùng suffix

Bad idea B:
  salt = (timestampSecond % 16)
  -> một nguồn phát burst trong cùng giây dồn một bucket

Bad idea C:
  salt = random() nhưng mỗi process restart cùng seed
  -> phân bố có thể trùng nếu random generator cấu hình sai

Safer candidate:
  salt = stableHash(immutableEventId) % 16
  -> cùng event retry trở lại một bucket
~~~

Nếu eventId có cấu trúc tuần tự, chọn một hash ổn định phân tán tốt sẽ hữu ích hơn chỉ lấy chữ số cuối; nhưng không nhất thiết phải dùng cryptographic hash mạnh cho mục đích load balancing.

Một điều kiện quan trọng: **hash input phải khác nhau giữa những writes cần tách**. Đối với một counters, bạn có thể dùng business event ID; đối với nghiệp vụ update một authoritative item, không thể tạo “nhiều item độc lập” mà vẫn tự giữ nguyên semantics một item.

## 39. Observability tối thiểu cho hệ có bucket/suffix

| Nhóm | Metric cần quan sát |
|---|---|
| Write distribution | Writes/s, throttles, conflicts theo bucket |
| Physical balance | CPU/memory/disk/IOPS theo node/shard |
| Query expansion | Số buckets/query, số requests con/query |
| Read cost | Reads capacity, bytes returned, records examined |
| Tail latency | p50/p95/p99 write và **logical GET** |
| Merge | Merge CPU time, heap/buffer memory, candidate/result ratio |
| Pagination | Cursor size, expiry, retries, pages per stream |
| Consistency | Duplicate IDs, missing data, out-of-order events |
| Routing | Bucket epoch, config drift, hash algorithm version |
| Migration | Old/new reads, backfill progress, dual-write conflicts |
| Tenant fairness | Hot tenants, read fan-out per tenant, rate limiting |
| Storage lifecycle | Bucket sizes, TTL backlog, tombstones/compaction |
| Failure | Partial query failures, slow buckets, per-bucket timeout |

Một tracing span cho logical GET có thể bao gồm:

~~~text
GET latest events for device-42 (requested K=100)
  routing lookup            2 ms
  bucket count              16
  scatter bucket queries   19 ms (max child)
  extra page fetches        8 ms
  merge + dedupe            4 ms
  serialization             2 ms
  total observed           35 ms
~~~

Số liệu minh họa. Phải đo thời gian thật và quan hệ chạy song song; không cộng các child spans chồng lấp như thể toàn bộ là tuần tự.

## 40. Benchmark phải so cả write lẫn read trên cùng workload

Một thí nghiệm chỉ đo insert throughput của B=1 và B=16 có thể kết luận “B=16 tốt hơn”, trong khi đọc latest-100 chậm gấp nhiều lần hoặc tiêu thụ read capacity ngoài budget.

Thiết kế các kịch bản:

| Phương án | Key layout | Kỳ vọng |
|---|---|---|
| A | Một partition key, không bucket | Read đơn giản, dễ hot key |
| B | Theo ngày, không suffix | Giới hạn lịch sử, current-day key vẫn nóng |
| C | Theo giờ, 8 suffix | Tách hot writes, fan-out 8/hour |
| D | Theo giờ, 32 suffix | Tách ghi hơn, fan-out 32/hour |
| E | Theo giờ, 16 suffix + latest-K projection | Ghi vào buckets, GET nhanh qua projection |

Với mỗi phương án, dùng:

1. Cùng payload và business event IDs.
2. Cùng số tenant/devices, với một **hot device** khác nhóm thường.
3. Cùng read/write ratio và range queries.
4. Cùng durability/replication/consistency mode.
5. Cùng retention/indexing settings trong khả năng tương đương.
6. Tải tăng dần và một khoảng burst cao.
7. Các lượt đo cache nóng/cold và sau TTL/compaction nếu liên quan.
8. Các runs đủ dài để thấy ảnh hưởng operations nền, không chỉ 10 giây đầu.
9. Đo cả technical failures và business duplicates/missing records.
10. Ghi config/version/topology để có thể tái hiện.

### 40.1. Bảng kết quả cần thu

| Chỉ số | A | B | C | D | E |
|---|---|---|---|---|---|
| Achieved writes/s | Đo | Đo | Đo | Đo | Đo |
| Write p99 | Đo | Đo | Đo | Đo | Đo |
| Throttled writes | Đo | Đo | Đo | Đo | Đo |
| Logical GET p99 | Đo | Đo | Đo | Đo | Đo |
| Subqueries/GET | Đo | Đo | Đo | Đo | Đo |
| Read capacity/GET | Đo | Đo | Đo | Đo | Đo |
| Max bucket skew | Đo | Đo | Đo | Đo | Đo |
| Merge CPU/memory | Đo | Đo | Đo | Đo | Đo |
| Duplicate/missing IDs | Đo | Đo | Đo | Đo | Đo |
| Disk/index/storage footprint | Đo | Đo | Đo | Đo | Đo |

Không điền con số giả làm benchmark. Kết luận cần nêu **khi nào mỗi thiết kế tốt hơn**, không chỉ tên “chiến thắng”.

## 41. Query correctness khi bucket lỗi hoặc event đến trễ

Một test:

~~~text
Bucket b00: E1 at 10:09
Bucket b01: E2 at 10:08
Bucket b02: E3 at 10:10
Bucket b03: TIMEOUT
Request latest 2.
~~~

Nếu b03 có event 10:11, trả E3/E1 như “global latest 2” là sai. API có thể chọn:

- Fail query và trả lỗi với retryable metadata.
- Trả partial results kèm dấu hiệu thiếu dữ liệu, không gọi là “complete newest”.
- Dùng một cached materialized result với freshness/coverage contract khác.
- Chờ b03 trong global deadline rồi retry có giới hạn.

**Partial success là một tính năng phải được thiết kế**, không là hệ quả bị che giấu của timeout.

Test late event:

~~~text
10:15 ingestion: E100 occurredAt=10:02
User đã đọc page 1 (cutoff occurredAt=10:10)
User đọc page 2 lúc 10:16
~~~

Tùy keyset cursor và snapshot contract, E100 có thể xuất hiện ở page 2, bị bỏ qua hoặc được đưa vào một refresh/new query. Không thể vừa hứa snapshot cố định vừa đọc live events tùy ý nếu thiếu transaction snapshot/cutoff hợp lệ.

## 42. Tối ưu đọc bằng materialized view/projection

Khi write-heavy events nhưng GET latest-100 rất phổ biến, một hướng:

~~~mermaid
flowchart LR
    A["Event writes tới nhiều suffix buckets"] --> B["Event log / CDC / Outbox"]
    B --> C["Latest-K materialized projection"]
    C --> D["Fast GET latest K"]
    A --> E["Historical range queries"]
~~~

Read projection có thể duy trì top-K theo device hoặc per tenant/time window. Lợi ích: không cần fan-out B buckets cho mỗi request đọc latest.

Nhưng có đánh đổi:

- Projection update có thể lag so với writes mới.
- Event duplicate phải dedupe theo event ID.
- Event sai thứ tự phải được merge theo stable sort key/sequence.
- Nếu projection key quá nóng, bản thân nó có thể thành hot item.
- Rebuild từ nguồn cần RTO, source/CDC retention và version control.
- API phải quy định đó là *eventual latest* hay có guarantee read-your-writes.
- Projection có thể mất khi failure; có thể rebuild nhưng GET không sẵn sàng trong lúc đó.

Chọn projection khi **read volume × fan-out cost** vượt chi phí duy trì projection, hoặc SLO đọc không thể đáp ứng bằng scatter–gather.

## 43. Tối ưu đọc bằng hierarchical buckets

Thay vì query 256 suffix trên một time period, có thể dùng cấu trúc phân cấp:

~~~text
Raw event buckets:
  device#hour#salt (64 suffixes)

Read summaries:
  device#minute -> count/min/max / top items
  device#hour   -> compact ordered digest
  device#day    -> aggregate statistics
~~~

API đọc overview từ summaries, chỉ fan-out raw buckets khi drill-down. Nhưng summary không tự là nguồn đầy đủ cho một query chi tiết:

- Một count summary không trả được toàn bộ event payload.
- Global latest-K summary cần biết đã được cập nhật tới mốc nào.
- Aggregation có thể bị trùng khi event replay nếu không idempotent.
- Recompute/backfill khi source event bị sửa/xóa cần policy.

**Hierarchical bucket** khác tạo thêm một index tùy tiện: mỗi tầng phải có semantics và freshness contract rõ.

## 44. Hotspot chuyển sang metadata/cursor service

Khi chia một hot data key thành nhiều buckets, ứng dụng thường thêm directory:

~~~text
device-42 -> active bucket list, routing epoch, next bucket
~~~

Nếu mọi write lại **update directory trên mỗi request**, directory trở thành hot key mới. Một thiết kế tốt hơn thường giữ routing epoch/config **ít thay đổi** và cho writers tính salt deterministic, chỉ truy cập directory khi đổi epoch hoặc lookup cần thiết.

Các vấn đề:

- Directory stale ở một writer khiến ghi sai epoch.
- Cache routing metadata không được hết hạn lâu hơn rollout chính sách.
- Một global sequence counter cho round-robin salt tạo contention mới.
- Cursor server-side state có thể bùng nổ RAM nếu mỗi GET giữ hàng trăm stream buffers.
- Một coordinator đọc không có bounded concurrency có thể DDoS chính database.

Mọi thao tác “thêm một tầng metadata để giải vấn đề” cần kiểm tra xem có **dời điểm nóng** sang tầng mới hay không.

## 45. Bucket count theo tenant: adaptive nhưng phức tạp

Một ứng dụng nhiều tenant:

~~~text
Tenant nhỏ: 1 bucket/time period
Tenant vừa: 8 buckets/time period
Tenant lớn: 64 buckets/time period
~~~

Lợi ích: tenant nhỏ đọc đơn giản, tenant lớn chịu tải ghi cao hơn. Nhưng routing không còn là một hằng số toàn cục.

Cần:

- Metadata `(tenant, time period, epoch, B, hashAlgorithmVersion)`.
- Writer/readers dùng cùng routing contract.
- Tránh đổi B liên tục theo traffic ngắn hạn (thrashing).
- Chính sách tăng bucket tại ranh giới thời gian hợp lý.
- Đo số bucket đang hoạt động và physical placement.
- Khả năng migrate key và cursor an toàn.
- Giới hạn `B_max` để tránh tenant có 10.000 bucket khiến GET quá đắt.

Adaptive bucketization có ích khi workload theo tenant khác biệt lớn, nhưng không nên triển khai trước khi **simple fixed B** được benchmark và chỉ rõ giới hạn.

## 46. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách tiếp cận |
|---|---|---|
| “Thêm suffix vào bất kỳ field nào cũng phân tán write” | Engine có thể chỉ route theo partition/shard key | Xác nhận key ownership thực |
| “Hash cùng deviceId giúp phân tán events của device đó” | Hash input không thay đổi | Hash eventId/intentId |
| “Time bucket theo ngày tự giải hot write” | Tất cả writes hôm nay vẫn vào một key | Thêm salt nếu current bucket nóng |
| “Bucket ứng dụng = physical partition” | Engine có thể đặt nhiều buckets chung owner | Đo physical placement |
| “Random suffix chắc chắn idempotent” | Retry có thể vào bucket khác | Stable hash/directory |
| “Unique key trong từng bucket đảm bảo unique toàn hệ” | Business ID có thể ở bucket khác | Global ledger/mapping |
| “B=32 luôn cho throughput gấp đôi B=16” | Throttle/shared resources/skew | Benchmark |
| “Read latest K: lấy K/B mỗi bucket” | Một bucket có thể chứa toàn top-K | Heap merge đúng |
| “Có cursor SDK của từng bucket là đủ” | Fetched-but-unemitted items có thể mất | Buffer/refetch logic |
| “Offset pagination ổn định dưới concurrent writes” | Insert làm dịch vị trí | Keyset/snapshot contract |
| “Một bucket timeout vẫn là global latest” | Bucket lỗi có thể chứa item mới nhất | Partial/fail contract |
| “Cứ tăng buckets là read nhanh hơn” | Fan-out/candidate/merge tăng | Theo dõi logical GET p99 |
| “Redis hash tag chỉ là nhãn text” | Hash tag có thể gom keys về cùng slot | Kiểm tra slot routing |
| “$push vào document bucket luôn tối ưu” | Hot document/giới hạn size | Rollover/concurrency |
| “DynamoDB suffix ở sort key đã giúp phân tán partition key” | PK vẫn giữ nguyên | Đặt suffix ở partition key phù hợp |
| “CQL WHERE thiếu salt vẫn đọc tốt mọi salts” | Partition key chưa đủ | Fan-out có kiểm soát |
| “GSI/search luôn fresh như nguồn chính” | Projection có thể lag | Revalidate khi business quyết định |
| “Đổi B trong config là xong” | Old items còn ở epoch cũ | Versioned routing/migration |
| “Dedupe khi đọc đủ cho counter” | Aggregates vẫn double-count | Idempotent effect/aggregation |
| “Bucket counter đủ bảo vệ vé cuối” | Sum nhiều key không atomic | Escrow/conditional quota owner |
| “Average CPU thấp nghĩa không hot key” | Có thể một owner bão hòa | Per-key/per-node metrics |
| “Nhiều buckets không có chi phí storage” | Index/metadata/empty reads tăng | Cost model |

## 47. Bài tập A — Chọn khóa cho một thiết bị rất nóng

**Bối cảnh:** một nền tảng IoT nhận 2.000 events/giây từ `device-42`, mỗi event khoảng 1 KiB logic, retention 30 ngày. API có hai đường:

- Ghi event theo ID, lưu event time.
- Đọc latest 100 events trong vòng 2 giờ gần đây.

Nhiệm vụ:

1. Tính số events và dung lượng logic của bucket 1 giờ, chưa kể index/replication.
2. Giải thích vì sao `PK=deviceId#day` có thể vẫn là hot key.
3. Thiết kế `PK=tenantId#deviceId#hour#salt` với 8 và 32 salts.
4. Mô tả stable hash input và cách retry của cùng event vào đúng bucket.
5. Với query 2 giờ, tính số bucket keys tối đa phải xét.
6. Đề xuất thuật toán global latest-100 không bị sai khi bucket nào đó chứa nhiều hơn 100 events mới nhất.
7. Nêu state cần lưu trong cursor.
8. Nếu B tăng 8→32 khi hour thay đổi, readers cần biết epoch nào?
9. Cho một metric để phát hiện bucket skew và một metric cho read cost.
10. Nếu một bucket timeout, API được phép trả loại response nào?

## 48. Bài tập B — Lựa chọn giữa fixed bucket và adaptive bucket

Một hệ analytics có:

~~~text
Tenant A: 100 events/giây
Tenant B: 1.000 events/giây
Tenant C: 50.000 events/giây
~~~

Giả sử benchmark minh họa cho thấy một bucket xử lý an toàn 800 writes/giây ở SLO yêu cầu. Hãy:

1. Tính lower-bound bucket count của từng tenant.
2. Chọn headroom và giải thích vì sao không lấy kết quả đó làm cam kết capacity.
3. Xem read-heavy tenant A có nên dùng 64 buckets không.
4. Đề xuất metadata layout cho tenant-specific bucket count.
5. Nêu phương án nâng bucket count mà vẫn đọc được old data.
6. Tính số subqueries khi tenant C có 64 buckets và 400 GET/s.
7. So fan-out read với một materialized latest-100 projection.
8. Giải thích vì sao hash tenantId một mình không giải điểm nóng của Tenant C.

## 49. Bài tập C — Counter và quota không giống nhau

Cho hai loại dữ liệu:

~~~text
views:product-1001 = số lượt xem (có thể eventually consistent)
tickets:event-42 = số vé còn lại (không được bán vượt)
~~~

Nhiệm vụ:

1. Thiết kế 16 counters cho views và cách hợp nhất khi GET.
2. Làm sao chống double-count khi một event được gửi lại?
3. Nếu chỉ dùng `SUM(available buckets)` rồi trừ một bucket, vẽ race dẫn tới oversell.
4. Thiết kế escrow rights hoặc một authoritative conditional update.
5. Khi một bucket hết quyền nhưng bucket khác còn, hệ sẽ phản hồi thế nào?
6. Khi phải chuyển quota giữa buckets, transferId cần đảm bảo gì?
7. Nếu một bucket mất dữ liệu, có thể rebuild counter từ event ledger không?
8. RPO của views và tickets có được phép khác nhau không?

## 50. Bài tập D — Đọc hợp nhất và cursor

Ba streams sorted DESC theo timestamp:

~~~text
b00: (9,A), (8,B), (3,C)
b01: (10,D), (7,E), (4,F)
b02: (9,G), (6,H), (2,I)
~~~

Giả sử tie-breaker là event ID theo thứ tự giảm dần.

1. Tự viết global top-5.
2. Dùng heap mô phỏng từng lần pop/push.
3. Vì sao lấy 2 items/bucket chưa chắc đủ top-5 trong trường hợp tổng quát?
4. Nếu b00 đã fetch 3 items nhưng chỉ emit 1, cursor phải giữ gì?
5. Nếu event mới (11,J) được ghi trước page 2, offset pagination có thể sai ra sao?
6. Nếu b02 timeout, có được gọi result “top-5 đầy đủ” không?
7. Tính độ phức tạp heap merge cho B streams và K results.
8. Nếu phải đọc 24 buckets và có 400 logical GET/s, tính subquery rate lý thuyết.
9. Nêu hai cách giảm fan-out mà không bỏ correctness.
10. Khi B thay đổi giữa hai trang, làm sao cursor còn resume an toàn?

## 51. Câu hỏi tự kiểm tra

1. Hot key và hot node khác nhau như thế nào?
2. Khi nào thêm machine không giải hot partition?
3. Bucket ứng dụng có luôn trùng physical partition không?
4. Time bucket giải vấn đề gì và chưa giải vấn đề gì?
5. Bucket theo số record cần metadata rollover ra sao?
6. Suffix random và deterministic khác nhau thế nào khi retry?
7. Hash cố định deviceId có phân tán events của device đó không?
8. Số bucket tối thiểu theo write throughput chỉ là ước lượng vì sao?
9. Vì sao bucket count cần xét cả dữ liệu tích lũy lẫn peak write rate?
10. Sort key toàn phần giúp merge điều gì?
11. K-way merge có heap complexity như thế nào?
12. Vì sao LIMIT K/B per bucket có thể sai?
13. Có thể đọc nhiều time buckets mà không query toàn bộ lịch sử bằng cách nào?
14. Fan-out ảnh hưởng read p99 và capacity ra sao?
15. Khi nào partial results được phép trả?
16. Cursor đa bucket cần những thông tin gì?
17. Fetched-but-unemitted items bị bỏ qua gây lỗi gì?
18. Keyset pagination có tự cung cấp snapshot toàn cục không?
19. Một event ID ở hai suffix khác nhau cần dedup ở đâu?
20. Directory mapping giải lookup problem nhưng tạo chi phí gì?
21. Sharded counter có bảo đảm quota cứng không?
22. Escrow rights bảo vệ invariant trong tình huống nào?
23. Vì sao DynamoDB suffix phải ảnh hưởng partition key để giúp phân tán?
24. Vì sao CQL query thường cần đầy đủ partition key gồm salt?
25. MongoDB document bucket khác suffix shard key thế nào?
26. Redis Cluster hash tags có thể vô tình gom suffixes vào một slot không?
27. Khi thay B=8 sang B=32, dữ liệu cũ được tìm bằng cách nào?
28. Dual-read migration tăng fan-out tạm thời ra sao?
29. Hash skew và physical placement skew cần được đo riêng vì sao?
30. Materialized latest-K projection tiết kiệm chi phí nào và thêm rủi ro nào?

## 52. Tổng kết: giảm ghi nóng nhưng phải trả được giá đọc hợp nhất

**Chia bucket theo thời gian** giúp quản lý kích thước và phạm vi lịch sử. **Thêm salt/suffix vào partition hoặc shard key** có thể phân tán write-heavy workload ra nhiều đơn vị sở hữu dữ liệu. Hai cách thường cần kết hợp khi một device/tenant/event vừa có nhiều dữ liệu tích lũy vừa có lưu lượng ghi rất cao.

Tuy nhiên, mỗi suffix mới có thể biến một logical read thành nhiều physical reads, làm tăng **scatter–gather RPCs, read capacity, merge CPU, tail latency, độ phức tạp cursor, dedup và migration**. Chọn B chỉ dựa trên throughput ghi là chưa đủ; phải đo cả logical GET p95/p99, fan-out, skew, cost và correctness.

Phương pháp áp dụng:

~~~text
1. Đo đúng hot key và physical owner.
2. Liệt kê write/read access patterns và business invariants.
3. Chọn time/size buckets để giới hạn dữ liệu.
4. Chọn suffix từ stable event/intent ID nếu cần phân tán write.
5. Xác minh suffix thực sự ảnh hưởng routing/partition ownership.
6. Ước lượng số buckets theo peak write, headroom và skew.
7. Thiết kế ordered per-bucket streams, k-way merge và pagination.
8. Định nghĩa partial failure, snapshot/visibility và idempotency.
9. Benchmark cả write throughput và read fan-out.
10. Giữ routing epochs và migration/recovery plan khi đổi số buckets.
~~~

Không có một số bucket “tốt nhất” cho mọi hệ NoSQL. Một thiết kế thành công là thiết kế **phân tán được điểm nóng thực sự, không phá bất biến nghiệp vụ, và vẫn trả được kết quả đọc đầy đủ, đúng thứ tự, đúng SLO với chi phí có thể kiểm soát**.




