# Tách khóa nóng hoặc tổng hợp bộ đếm theo nhiều phần

Một video có thể có hàng triệu lượt xem, nhưng hệ thống chỉ dùng một khóa:

~~~text
video:77:views = 12000000
~~~

Mỗi lượt xem lại chạy một thao tác tăng:

~~~text
INCREMENT video:77:views BY 1
~~~

Tưởng như đây là thiết kế tối ưu: dữ liệu nhỏ, lệnh cập nhật nguyên tử, đọc tổng lượt xem rất dễ. Nhưng khi có hàng chục nghìn request mỗi giây cùng truy cập **một khóa**, phần lớn tải vẫn dồn vào **một điểm thực thi/partition/leader hoặc nhóm replica chịu trách nhiệm khóa đó**. Thêm mười máy chủ hoặc tăng số shard của cả cluster chưa chắc thay đổi được nơi ghi vào khóa này.

Đó là hiện tượng **khóa nóng (hot key)**. Một cách xử lý quan trọng là **tách khóa nóng thành nhiều khóa con (striped/sharded counters)**, phân tán các lần tăng lên nhiều bucket, rồi cộng các bucket lại khi cần tổng:

~~~text
video:77:views:bucket:00 = 1500000
video:77:views:bucket:01 = 1500001
video:77:views:bucket:02 = 1499998
...
video:77:views:bucket:07 = 1500001

Tổng lượt xem = tổng giá trị của 8 bucket
~~~

Tuy nhiên, kỹ thuật này có đánh đổi: **ghi rẻ hơn trên từng khóa nhưng đọc tổng có thể phải đọc nhiều khóa**; tổng không nhất thiết là một **snapshot nguyên tử**; retry có thể làm tăng hai lần; đổi số bucket có thể gây mất/đếm trùng nếu migration thiếu quy tắc. Đặc biệt, không thể lấy một bộ đếm phân tán kiểu eventual rồi mặc định dùng nó làm nguồn duy nhất để quyết định **còn bao nhiêu vé hoặc tồn kho được phép bán**.

Bài học thuộc chương **Cân bằng và điểm nóng** của Database No SQL. Ta sẽ phân biệt hot key với hot partition, giải thích nguyên nhân và phép đo, thiết kế bộ đếm nhiều phần, chọn bucket, phân tán đọc/ghi, ví dụ Redis, DynamoDB, MongoDB và Cassandra, xử lý idempotency, tính chính xác, TTL, migration, reconciliation và vận hành.

## 1. Khóa nóng là gì?

**Hot key** là khóa nhận lưu lượng hoặc tài nguyên sử dụng **cao vượt trội** so với các khóa khác, đến mức đường phục vụ khóa đó trở thành giới hạn hiệu năng.

Ví dụ:

~~~text
Cluster gồm 32 nodes.

100.000 keys nhỏ:
  mỗi key trung bình 2 writes/giây.

Key video:77:views:
  40.000 increments/giây.
~~~

Ngay cả khi 100.000 khóa nhỏ được rải khá đều, **video:77:views** vẫn tập trung 40.000 updates vào một đơn vị trách nhiệm theo cơ chế lưu trữ. Khả năng tăng throughput không còn tỉ lệ thuận với số máy được thêm vào.

Một khóa có thể nóng do:

- Một video, bài đăng hoặc sản phẩm lan truyền đột ngột.
- Bộ đếm tổng toàn hệ: **global:pageviews**, **online-users**, **total-orders**.
- Một tài khoản/tenant lớn có lượng yêu cầu vượt xa các tenant khác.
- Một record cấu hình hoặc metadata bị mọi request đọc.
- Một khóa khóa phân tán, leader-election metadata hoặc queue head bị tranh chấp.
- Một session hoặc tài nguyên duy nhất có nhiều request sửa trạng thái.

**Hot không đồng nghĩa lớn về dung lượng.** Một integer 8 byte có thể là key nóng hơn một document vài megabyte nếu nó bị cập nhật liên tục.

## 2. Phân biệt hot key, hot partition, hot node và hot range

| Hiện tượng | Phạm vi quá tải | Ví dụ | Hướng điều tra |
|---|---|---|---|
| **Hot key** | Một logical key/item/document | Counter tổng lượt xem | Tách hiệu ứng, giảm ghi hoặc cache read |
| **Hot partition** | Một partition chứa nhiều key/row | Tất cả event của tenant cực lớn trong một partition | Chọn lại partition key/bucket |
| **Hot range** | Dải key liên tục nhận ghi | Timestamp tăng dần, insert vào range cuối | Hash/bucket hoặc split range |
| **Hot shard/node** | Một shard hoặc node bận hơn hẳn | Nhiều hot keys cùng được đặt trên một node | Rebalance/đổi placement, capacity |
| **Hot leader/coordinator** | Nút quyết định/điều phối bị nghẽn | Mọi update đi qua một leader | Phân tán ownership/requests |
| **Hot read path** | Rất nhiều read cùng dữ liệu | Config được mỗi request đọc lại | Cache, replica read, batching |

Những hiện tượng có thể chồng lên nhau. **Một hot key** có thể làm **một partition** nóng, rồi **một node** nóng; nhưng tăng số partition có thể chưa xử lý nếu tất cả update vẫn cùng một logical key.

### Không chẩn đoán chỉ bằng CPU trung bình cluster

~~~text
Node A: 98% CPU, p99 write 950 ms
Node B: 22% CPU
Node C: 18% CPU
Node D: 25% CPU

Cluster CPU trung bình: 40,75%
~~~

Cluster trông còn tài nguyên, nhưng các request đi qua node A vẫn chậm. Cần quan sát **top keys, top partitions, throughput theo shard, hàng chờ và p95/p99 theo key nhóm** thay vì chỉ nhìn trung bình toàn cụm.

## 3. Vì sao thêm replica hoặc shard chưa đủ?

Giả sử partition function:

\[
\operatorname{shard}(K)=H(K)\bmod P
\]

Mọi request tăng **cùng K** đều có cùng giá trị hash. Khi số shard tăng từ 4 lên 16, **K vẫn là một logical key** và thường được phục vụ tại một partition/shard có trách nhiệm, dù vị trí vật lý có thể thay đổi.

~~~mermaid
flowchart LR
    U["40.000 increments/s"] --> H["key video:77:views"]
    H --> P["Một partition / owner"]
    P --> N["Node hoặc replica group"]
~~~

Replica có thể tăng **khả năng đọc**, nhưng với những cơ chế ghi phải đi qua primary hoặc được phối hợp trên cùng item, nhiều replica **không biến một update đơn thành N update độc lập có thể xử lý song song**.

Muốn chia đường ghi, cần thay đổi **mô hình dữ liệu hoặc cách diễn đạt hiệu ứng**:

~~~text
Một key:
  video:77:views

Thành nhiều key:
  video:77:views:bucket:00
  video:77:views:bucket:01
  ...
  video:77:views:bucket:63
~~~

Nếu các bucket được phân bố tới nhiều partition vật lý và mỗi bucket nhận một phần request, tải mỗi điểm có thể giảm đáng kể.

## 4. Đo đúng điểm nóng trước khi thay schema

Trước khi tách counter, hãy hỏi:

1. Tải chủ yếu là **read** hay **write**?
2. Hotspot xuất hiện ở **key**, **partition**, **shard** hay **coordinator**?
3. Có một request đắt do **large payload** thay vì QPS cao không?
4. Lệnh ghi là **SET**, **increment**, **conditional update** hay transaction?
5. Tắc ở **CPU, network, disk, lock/contention, write units, replica coordination** hay connection pool?
6. Lỗi chỉ xuất hiện trong giờ cao điểm hay liên tục?
7. Ghi có thể gộp/batch không, hay mỗi event phải tồn tại riêng?
8. Sản phẩm cần **tổng chính xác ngay lập tức** hay chấp nhận trễ vài giây?

Những metric hữu ích:

| Metric | Giải thích |
|---|---|
| Writes/s theo logical key hoặc nhóm key | Xác định heavy hitters |
| Reads/s theo key | Xem tách write có thật sự cần |
| p50/p95/p99 latency theo operation | Đo ảnh hưởng với người dùng |
| Partition/node CPU, I/O, network | Xem tài nguyên bão hòa |
| Throttling/timeout/retry | Phát hiện vượt giới hạn |
| CAS/transaction conflict rate | Đo tranh chấp update |
| Queue length, pool wait | Xác định nghẽn trước database |
| Replica lag | Phân biệt đọc trễ với ghi chậm |
| Counter drift so với event ledger | Đo tính đúng sau tách |
| Fan-out đọc tổng | Đo chi phí đọc do nhiều bucket |

Tránh xuất **key/tenantId có cardinality cực lớn** thành label mặc định của mọi time-series metric. Có thể dùng top-K sampling, tracing có kiểm soát hoặc thống kê tại database.

## 5. Tách khóa nóng có phải lúc nào cũng đúng?

Không. Cần phân loại ngữ nghĩa:

| Tác động | Có thể chia thành các hiệu ứng độc lập? | Ghi chú |
|---|---|---|
| Đếm số lượt xem | Thường có | Sum các increments |
| Đếm số click theo phút | Thường có | Có thể bucket theo thời gian |
| Đếm request theo tenant | Thường có | Cần xác định event trùng |
| Tăng lượt thích | Có điều kiện | Like/unlike cần uniqueness theo user |
| Tổng số tiền giao dịch | Không nên chỉ dùng increment | Cần ledger, tiền tệ, đối soát |
| Tồn kho không được âm | Không thể tách tùy ý | Cần owner, escrow/quota hoặc transaction |
| Một username duy nhất | Không tự chia được | Unique constraint/authority |
| Một ghế chỉ một chủ | Không tự chia được | CAS/conditional claim |
| Số phiên đang hoạt động | Có thể, nếu có lifecycle đúng | Join/leave/TTL cần chống đếm trùng |

**Đúng về mặt đại số không tự đúng về mặt nghiệp vụ.** Phép cộng các lượt xem độc lập có thể gom lại; quyết định “chỉ bán thêm khi tổng stock còn dương” không thể thực hiện bằng cách đọc đại một bucket.

## 6. Thiết kế bộ đếm phân mảnh (sharded counter)

Giả sử metric **views** của video-77 có **B = 8** bucket:

~~~text
views:video-77:bucket:0 = 14
views:video-77:bucket:1 = 18
views:video-77:bucket:2 = 16
views:video-77:bucket:3 = 15
views:video-77:bucket:4 = 20
views:video-77:bucket:5 = 12
views:video-77:bucket:6 = 19
views:video-77:bucket:7 = 16
~~~

Tổng:

\[
C=\sum_{i=0}^{B-1}C_i
\]

Ví dụ trên:

\[
C = 14+18+16+15+20+12+19+16=130
\]

Một event chỉ tăng **một bucket**:

~~~text
Receive view(eventId)
  -> bucket = chooseBucket(eventId, B)
  -> atomicIncrement(bucket, +1)
~~~

Khi đọc:

~~~text
Read bucket 0..7
  -> sum values
  -> return total
~~~

Sơ đồ:

~~~mermaid
flowchart TD
    E["Nhiều view events"] --> SELECT["Chọn bucket 0..7"]
    SELECT --> B0["Bucket 0"]
    SELECT --> B1["Bucket 1"]
    SELECT --> B2["Bucket 2"]
    SELECT --> B3["Bucket 3"]
    SELECT --> B4["Bucket 4"]
    SELECT --> B5["Bucket 5"]
    SELECT --> B6["Bucket 6"]
    SELECT --> B7["Bucket 7"]
    B0 --> SUM["Sum / aggregate"]
    B1 --> SUM
    B2 --> SUM
    B3 --> SUM
    B4 --> SUM
    B5 --> SUM
    B6 --> SUM
    B7 --> SUM
~~~

Mỗi bucket vẫn cần **atomic increment** trong phạm vi key/item/document mà engine hỗ trợ. Tách nhiều bucket không sửa được một phép cập nhật **GET rồi SET** bị lost update bên trong từng bucket.

## 7. Tại sao cách này giảm điểm nóng?

Giả sử tổng tải là:

\[
\lambda=48\,000\ \mathrm{updates/s}
\]

Với **B = 32** bucket và phân bố đều lý tưởng:

\[
\lambda_{\mathrm{bucket}}\approx \frac{48\,000}{32}
=1\,500\ \mathrm{updates/s}
\]

Không còn một key nhận 48.000 update/s; mỗi key nhận khoảng 1.500 update/s.

Nhưng cần nhớ:

- Đây là **ước lượng trung bình**, không phải cam kết cứng.
- Bucket assignment có thể lệch; event ID kém phân bố có thể khiến một bucket nóng hơn.
- Nhiều bucket vẫn có thể rơi vào **cùng partition vật lý**.
- Coordinator, replica quorum, proxy hoặc log chung có thể vẫn nghẽn.
- Đọc tổng phải chạm nhiều bucket, tạo thêm chi phí.
- Hệ lưu trữ có thể có giới hạn throughput riêng theo partition và loại ghi.

**Tách logical key chỉ tạo cơ hội phân tán tải**; cần kiểm tra placement thực tế và đo sau triển khai.

## 8. Chọn bucket bằng random hay hash ổn định?

### Random bucket

~~~text
bucket = randomInteger(0, B-1)
~~~

Ưu điểm:

- Cân bằng tải thống kê khi random đủ tốt.
- Đơn giản cho những event thật sự độc lập.

Nhược điểm:

- Retry một event có thể được đưa sang **bucket khác**.
- Nếu cần dedup, phải có một cơ chế lookup/dedup khác đáng tin.
- Khó truy vết event gốc chỉ bằng bucket.

### Hash ổn định theo eventId

~~~text
bucket = stableHash(eventId) mod B
~~~

Ưu điểm:

- Retry của **cùng eventId** chọn cùng bucket nếu B và hash version không đổi.
- Dễ đặt dedup marker cạnh bucket trong một số hệ.
- Dễ tái hiện/đối soát routing.

Nhược điểm:

- Phải có **eventId ổn định**, không sinh ID mới mỗi lần retry.
- Hash input/encoding và B phải nhất quán giữa mọi client.
- Thay B sẽ làm nhiều event cũ chọn bucket mới nếu không có versioning.
- Nếu eventId có phân bố xấu hoặc bị chọn có chủ đích, cần hàm hash phù hợp.

**Hash ổn định không tự chống đếm trùng**. Nó chỉ đưa hai lần gửi cùng event vào cùng bucket; nếu vẫn INCR hai lần thì tổng vẫn sai.

## 9. Chọn bucket theo worker hoặc region

Một cách khác là mỗi worker/region có phần riêng:

~~~text
views:video-77:region:apac
views:video-77:region:eu
views:video-77:region:us
~~~

Lợi ích:

- Có thể giảm write latency qua WAN.
- Dễ theo dõi nguồn sự kiện theo region.
- Phù hợp cách tổng hợp theo vùng nếu các update độc lập.

Nhược điểm:

- Một region đang lan truyền mạnh có thể trở thành **hot bucket**.
- Khi worker tăng/giảm số lượng, quản lý bucket lifecycle phức tạp.
- Một event chuyển vùng hoặc retry qua region khác có thể bị đếm hai lần.
- Nếu region offline, tổng toàn cầu có thể chưa đầy đủ.

Thường cần **hai cấp**:

~~~text
metricId
  -> region
  -> bucketNumber
~~~

Ví dụ mỗi region có 16 bucket; tổng toàn cầu cộng tất cả buckets của các regions đã tham gia. Cần quy định thời điểm region mới được thêm và cách discover buckets để không bỏ sót.

## 10. Chọn số bucket theo tải và ngân sách đọc

Giả sử qua benchmark, một bucket có thể xử lý **tối đa mục tiêu vận hành** khoảng 1.500 updates/s trước khi p99 vượt SLO. Đây là số đo minh họa, **không phải quota của Redis/DynamoDB/MongoDB/Cassandra**.

Với tổng peak dự kiến 48.000 updates/s:

\[
B_{\min}=
\left\lceil\frac{\lambda_{\mathrm{peak}}}
{\lambda_{\mathrm{bucket,target}}}\right\rceil
=\left\lceil \frac{48000}{1500}\right\rceil=32
\]

Có thể cân nhắc **64 buckets** để có headroom, nhưng nếu read tổng xảy ra rất thường xuyên, 64 reads hoặc một query đọc 64 records có thể đắt hơn 16 bucket.

| B | Tải mỗi bucket khi 48.000/s, lý tưởng | Số bucket phải tổng hợp |
|---:|---:|---:|
| 1 | 48.000/s | 1 |
| 8 | 6.000/s | 8 |
| 16 | 3.000/s | 16 |
| 32 | 1.500/s | 32 |
| 64 | 750/s | 64 |
| 128 | 375/s | 128 |

Con số trong bảng chỉ giúp suy luận. Thiết kế cuối phải đo throughput thực tế, overhead ghi, physical placement, hotness skew, throttling và p99 đọc tổng.

**Không cần nhân bucket vô hạn**. Số bucket vượt nhu cầu có thể làm tăng storage metadata, số query, chi phí cache và complexity của migration.

## 11. Phân biệt B buckets với N physical shards

Ví dụ có **B=64 logical counter buckets**, nhưng database chỉ có **4 physical shards**.

~~~text
64 logical buckets
       |
       v
4 physical shards
~~~

Nếu hash placement tương đối đều, mỗi physical shard có thể giữ khoảng 16 buckets; tải có thể được chia giữa bốn shard. Nhưng nếu shard key chỉ dùng **videoId**, mọi bucket của video-77 có thể vẫn bị đặt cùng một shard:

~~~text
Shard key sai cho mục tiêu phân tán:
  videoId = "video-77"

Bucket 00..63:
  tất cả cùng partition theo videoId
~~~

Thiết kế shard key phải bao gồm thành phần **bucket/partition token** theo cách engine hỗ trợ:

~~~text
logicalBucketKey =
  metricId + timeWindow + bucketId
~~~

Sau đó chọn partition/shard mapping để các logical bucket có cơ hội được đặt trên nhiều physical units.

**Không đồng nhất “64 records” với “64 hot partitions được phân tán”**. Kiểm tra routing key, token/slot, query plan và phân bố thực tế.

## 12. Dữ liệu nào phù hợp với phép cộng?

Phép cộng thông thường có tính:

\[
(a+b)+c=a+(b+c)
\]

và:

\[
a+b=b+a
\]

Do đó các delta độc lập có thể được gộp theo nhiều thứ tự mà vẫn ra một tổng **nếu mỗi delta được áp dụng đúng số lần cần thiết**.

Ví dụ:

~~~text
Event E1: +1 view
Event E2: +1 view
Event E3: +1 view

Bucket 3: +2
Bucket 7: +1

Tổng delta = +3
~~~

Nhưng hai điểm khác biệt:

- **Commutative** không có nghĩa **idempotent**. Tính hai lần +1 tạo +2, không phải +1.
- Một tổng hợp có thể đúng về mặt cộng số nhưng sai **định nghĩa metric**. Số lượt xem, số người xem duy nhất và số session đang hoạt động là ba khái niệm khác nhau.

Trước khi tách, phải định nghĩa chính xác **một event hợp lệ là gì** và event có thể xuất hiện bao nhiêu lần.

## 13. Lượt xem, lượt thích và người dùng duy nhất khác nhau

### Lượt xem

Một event được chấp nhận có thể cộng +1. Cần quy định lọc bot, xem tối thiểu bao lâu và dedup trong thời gian nào.

### Lượt thích

Một người dùng chỉ được thích một video một lần:

~~~text
Like(user-1, video-77) -> +1
Like(user-1, video-77) lần thứ hai -> +0
Unlike(user-1, video-77) -> -1
~~~

Chỉ dùng INCR trên bucket ngẫu nhiên sẽ đếm trùng. Phải có **trạng thái quan hệ user–video** hoặc event lifecycle đáng tin để bảo vệ uniqueness và chuyển trạng thái.

### Số người dùng duy nhất

Nếu user-1 xuất hiện ở bucket 2 và bucket 5, cộng **số distinct của từng bucket** sẽ tính user-1 hai lần.

~~~text
Bucket 2 distinct users: {A, B}
Bucket 5 distinct users: {B, C}

Sum per-bucket distinct = 4
True union distinct = 3
~~~

Để tính unique, cần **set union/mergeable distinct sketch** hoặc một pipeline dedup toàn metric. Với HyperLogLog, cần **merge các sketch đúng thuật toán**, không cộng các ước lượng distinct riêng lẻ.

## 14. Một mô hình dữ liệu tổng quát

Ví dụ counter nhiều bucket theo ngày:

~~~json
{
  "tenantId": "shop-a",
  "metricId": "video-77:views",
  "windowStart": "2026-11-14T00:00:00Z",
  "routingEpoch": 3,
  "bucketId": 17,
  "value": 85142,
  "updatedAt": "2026-11-14T09:10:00Z"
}
~~~

Logical identity nên có:

~~~text
tenantId
metricId
timeWindow
routingEpoch (nếu dùng version để thay bucket layout)
bucketId
~~~

**Counter bucket** có trách nhiệm lưu một phần tổng. **Metric definition/config** lưu số bucket, routing epoch, event semantics, retention và version của schema.

Ví dụ:

~~~yaml
metric: "video-77:views"
tenant: "shop-a"
unit: "accepted-view-event"
window: "daily-UTC"
bucketLayout:
  epoch: 3
  count: 64
bucketSelection: "stableHash(eventId) mod 64"
aggregation: "sum"
authoritativeEventSource: "view-event-ledger"
servingFreshnessSLO: "5 seconds"
~~~

Đây là cấu trúc mô tả, không phải cấu hình tự chạy của một database cụ thể.

## 15. Pseudocode đường ghi và đường đọc

~~~typescript
type CounterConfig = {
  epoch: number;
  bucketCount: number;
};

async function recordView(
  tenantId: string,
  metricId: string,
  eventId: string,
  eventTimeUtc: string
) {
  const config: CounterConfig = await getCounterConfig(metricId);
  const window = toUtcWindow(eventTimeUtc);
  const bucketId = stableHash(eventId) % config.bucketCount;

  // Hàm này phải có idempotency/atomicity được thiết kế riêng.
  await applyOnceToBucket({
    tenantId,
    metricId,
    window,
    epoch: config.epoch,
    bucketId,
    eventId,
    delta: 1
  });
}

async function readTotal(
  tenantId: string,
  metricId: string,
  window: string
) {
  const activeLayouts = await getLayoutsNeededForWindow(metricId, window);
  const bucketValues = await readAllParticipatingBuckets(
    tenantId,
    metricId,
    window,
    activeLayouts
  );

  return bucketValues.reduce((sum, value) => sum + value, 0);
}
~~~

Các hàm **stableHash**, **applyOnceToBucket** và **readAllParticipatingBuckets** là hợp đồng khái niệm. Chúng phải được triển khai theo driver, schema, retry và consistency của database cụ thể.

Điểm cần chú ý: **số bucket không được tự động đổi giữa retry của cùng event** nếu không có metadata/epoch để giữ quyết định định tuyến ổn định.

## 16. Redis: một counter key và lệnh INCRBY

Trường hợp cơ bản:

~~~redis
SET views:video-77 0
INCRBY views:video-77 1
GET views:video-77
~~~

Trên một Redis instance, **INCRBY** tránh lost update kiểu client tự GET, cộng rồi SET. Tuy nhiên, một key vẫn tập trung nhiều write vào nơi giữ key.

Chuyển sang bucket:

~~~redis
INCRBY views:video-77:bucket:00 1
INCRBY views:video-77:bucket:01 1
INCRBY views:video-77:bucket:02 1
~~~

Ứng dụng chọn một bucket cho mỗi view, không tăng cả ba. Để đọc tổng, có thể dùng **MGET** trong cấu hình Redis phù hợp hoặc pipeline nhiều GET, rồi cộng ở client.

Trong **Redis Cluster**, multi-key commands có ràng buộc **cùng hash slot**. Nếu buckets trải trên nhiều slots, không nên mặc định một MGET xuyên tất cả buckets hoạt động. Cluster-aware client có thể phát nhiều GET/pipeline được phân nhóm theo node/slot, hoặc xây một read model tổng hợp riêng.

## 17. Redis Cluster: cẩn thận hash tag gom các bucket về một slot

Redis Cluster tính **16.384 hash slots**; hash tag giữa ngoặc nhọn quyết định phần key được hash nếu dùng đúng cú pháp của Redis.

Thiết kế dễ sai:

~~~text
views:{video-77}:bucket:00
views:{video-77}:bucket:01
views:{video-77}:bucket:02
~~~

Vì cả ba có cùng hash tag **video-77**, chúng **nằm cùng slot**. Dù tạo nhiều keys, **mục tiêu phân tán tải viết giữa slots không đạt được**.

Một lựa chọn có thể phân bố hơn:

~~~text
views:{video-77:00}:counter
views:{video-77:01}:counter
views:{video-77:02}:counter
~~~

Mỗi bucket có hash tag riêng, tạo điều kiện được map tới các slots khác nhau. **Không bảo đảm mọi tag khác nhau luôn ở slot khác nhau** vì hash có thể va chạm; cần kiểm tra placement thực tế, chẳng hạn bằng lệnh công cụ Redis Cluster tương ứng.

Đánh đổi: các bucket trên không còn trong cùng slot, nên không thể dùng một script/MULTI để cập nhật hoặc đọc nhất quán tất cả buckets như một đơn vị cross-slot.

**Cùng hash slot hữu ích cho atomic multi-key cục bộ; khác hash slot hữu ích cho phân tán hot writes.** Hai mục tiêu có thể xung đột và cần lựa chọn rõ.

## 18. Redis: chống retry trùng trong phạm vi một bucket

Giả sử nhận eventId **view-e1001** hai lần:

~~~text
Lần 1:
  INCRBY bucket 1

Timeout sau khi server đã tăng.

Lần 2:
  INCRBY bucket 1

Kết quả:
  Event được tính 2 lần.
~~~

**INCRBY nguyên tử nhưng không idempotent theo eventId**.

Một ý tưởng là ghi dấu event đã xử lý và tăng counter trong cùng một script Lua trên **một Redis instance/slot**:

~~~lua
-- KEYS[1] = views:{video-77:07}:counter
-- KEYS[2] = views:{video-77:07}:seen
-- ARGV[1] = eventId

-- Ví dụ giáo dục, chưa đủ để thay nguồn ledger bền vững.
local eventId = ARGV[1]
if not eventId or string.len(eventId) == 0 then
  return {err = "MISSING_EVENT_ID"}
end

-- Trong Redis Cluster, KEYS[1] và KEYS[2] phải cùng slot.
local inserted = redis.call("SADD", KEYS[2], eventId)
if inserted == 0 then
  return 0  -- Event đã gặp trong dedup set của bucket.
end

redis.call("INCRBY", KEYS[1], 1)
return 1
~~~

**Giới hạn quan trọng:**

- Lua script trong Redis có thực thi không bị lệnh khác chen vào theo cơ chế server, nhưng **không có rollback kiểu SQL khi một lệnh trong script bị lỗi runtime sau khi những lệnh trước đã ghi**. Ví dụ SADD thành công rồi INCRBY gặp lỗi kiểu dữ liệu có thể để trạng thái không nhất quán. Cần tiền kiểm kiểu dữ liệu, xử lý lỗi và đối soát; script trên chỉ minh họa.
- Dedup set tăng theo số event và có thể **tốn bộ nhớ hơn counter rất nhiều**.
- Hết TTL của dedup quá sớm có thể khiến event cũ bị tính lại.
- Replication/failover/persistence có thể ảnh hưởng tính bền của cả counter và marker.
- Script giữa nhiều hash slots không được Redis Cluster hỗ trợ như một transaction toàn cluster.

Nếu cần **exactly-once effect bền vững**, thường cần lưu sự kiện/marker trong nguồn có transaction/unique key phù hợp, rồi materialize counter theo một quy trình có thể replay và reconcile.

## 19. DynamoDB: write sharding cho counter item

Trong DynamoDB, một item nóng có thể gặp giới hạn khả năng phục vụ theo item/partition và bị throttling tùy workload/cấu hình. Thay vì cập nhật một item:

~~~text
PK = COUNTER#video-77#views
value = ...
~~~

có thể phân thành nhiều items:

~~~text
PK = COUNTER#video-77#2026-11-14#B00
PK = COUNTER#video-77#2026-11-14#B01
...
PK = COUNTER#video-77#2026-11-14#B31
~~~

Một **UpdateItem** minh họa dùng phép tăng nguyên tử:

~~~text
Key:
  PK = "COUNTER#video-77#2026-11-14#B07"

UpdateExpression:
  ADD #value :one

ExpressionAttributeNames:
  #value = "value"

ExpressionAttributeValues:
  :one = Number(1)
~~~

Đây là mô tả API, không phải payload JSON SDK trực tiếp. Trong SDK thật, typed AttributeValues/biểu thức và cấu hình capacity phải đúng.

### Đọc tổng

Ứng dụng biết danh sách B buckets, sử dụng **GetItem/BatchGetItem hoặc query theo schema thực tế** rồi cộng các giá trị. Nếu chọn thiết kế khóa cho phép Query theo một partition key chung:

~~~text
PK = COUNTER#video-77
SK = WINDOW#2026-11-14#B07
~~~

thì các bucket có thể vẫn tập trung cùng **partition key logical** và không đạt mục đích write sharding vật lý như mong muốn. Cần cân bằng **khóa giúp đọc tổng thuận tiện** với **khả năng phân tán write throughput**, tùy cơ chế adaptive capacity và partition placement của DynamoDB.

Một pattern tách **physical bucket key** để phân tán writes thường khiến read tổng phải thực hiện nhiều GetItem/BatchGetItem.

## 20. DynamoDB: idempotency và transaction marker

Nếu mỗi event được tính đúng một lần, một kiến trúc có thể dùng:

~~~text
Counter item:
  PK = COUNTER#video-77#B07

Event marker:
  PK = VIEW_EVENT#view-e1001
  metricId = video-77
  bucket = 07
~~~

Một giao dịch minh họa:

~~~text
TransactWriteItems:
  1. Put event marker
     Condition: marker chưa tồn tại.

  2. Update counter item
     ADD value +1.
~~~

Nếu hai thao tác nằm trong cùng transaction theo bảo đảm DynamoDB và marker có unique identity ổn định, retry của event đã ghi có thể bị điều kiện chặn hiệu ứng tăng lần nữa.

Những vấn đề còn lại:

- **Transaction có chi phí và giới hạn về số item, kích thước, vùng, contention** theo tài liệu dịch vụ hiện hành.
- Một marker trên mỗi view có thể tạo **khối lượng dữ liệu rất lớn**.
- Nếu marker được TTL xóa sớm, replay event cũ có thể tăng lại.
- Idempotency token của API có thể có **cửa sổ thời gian**; cần logical marker bền nếu workflow/replay dài hơn.
- Khi hệ có nhiều region, hợp đồng transaction/replication/merge phải được kiểm tra riêng.

Chỉ định bucket theo eventId và ghi bucket vào marker giúp quá trình retry hoặc đối soát không tự chuyển event sang một layout khác.

## 21. MongoDB: một document counter được chia thành nhiều documents

Thiết kế một document:

~~~javascript
{
  _id: "video-77:views",
  value: 12000000
}
~~~

Ứng dụng cập nhật:

~~~javascript
db.viewCounters.updateOne(
  { _id: "video-77:views" },
  { $inc: { value: 1 } }
);
~~~

MongoDB thực hiện cập nhật một document nguyên tử trong phạm vi được hỗ trợ, nhưng document/owner của nó vẫn có thể thành điểm contention khi ghi rất nhiều.

Thiết kế bucket:

~~~javascript
{
  _id: "shop-a:video-77:2026-11-14:B07",
  tenantId: "shop-a",
  metricId: "video-77:views",
  window: "2026-11-14",
  bucket: 7,
  value: 15321
}
~~~

Increment một bucket:

~~~javascript
db.viewCounterBuckets.updateOne(
  { _id: "shop-a:video-77:2026-11-14:B07" },
  {
    $inc: { value: 1 },
    $setOnInsert: {
      tenantId: "shop-a",
      metricId: "video-77:views",
      window: "2026-11-14",
      bucket: 7
    }
  },
  { upsert: true }
);
~~~

Nếu dùng upsert đồng thời, cần thiết kế **unique identity/index** và xử lý duplicate-key retry đúng phạm vi sharding; đừng giả định mọi dạng unique index hoạt động giống nhau trên mọi sharded collection.

### Đọc tổng bằng aggregation

~~~javascript
db.viewCounterBuckets.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      metricId: "video-77:views",
      window: "2026-11-14"
    }
  },
  {
    $group: {
      _id: null,
      total: { $sum: "$value" }
    }
  }
]);
~~~

Trong sharded cluster, aggregation có thể cần **fan-out và merge** trên nhiều shards. Cần kiểm tra query plan, index, number of buckets và consistency/read concern thực tế. Một aggregation gồm nhiều reads **không mặc nhiên là snapshot toàn bộ buckets nguyên tử**.

**Quan trọng:** nếu shard key chỉ có metricId=video-77, các bucket có thể vẫn cùng shard. Phải thiết kế shard key/placement để bucketId hoặc bucketKey thực sự hỗ trợ phân tán, đồng thời bảo toàn khả năng target mỗi update.

## 22. MongoDB: idempotency không tự sinh ra từ $inc

Một request tăng:

~~~text
updateOne({bucketId:7}, {$inc:{value:1}})
~~~

bị timeout sau khi commit. Retry lặp chính lệnh đó có thể cộng lần nữa.

Với yêu cầu exact, có thể lưu **event marker duy nhất** và tăng bucket trong một transaction nhiều document thuộc deployment hỗ trợ:

~~~text
Transaction:
  Insert processedEvent(eventId, metricId, bucketId)
    -> chỉ thành công nếu eventId chưa tồn tại.

  Update counter bucket:
    $inc value +1.

Commit.
~~~

Nếu insert duplicate, ứng dụng cần phân biệt **replay cùng payload** với **reuse eventId cho nội dung khác**. Nếu transaction commit outcome không rõ, phải kiểm chứng marker/ID trước khi gửi hiệu ứng mới.

Nhưng transaction mỗi lượt xem có thể quá đắt ở tải cực cao. Có thể thay bằng một **durable event log** và pipeline tổng hợp idempotent theo batch; lựa chọn đúng phụ thuộc latency và độ chính xác cần thiết.

## 23. Cassandra: counter columns và bucketed partitions

Cassandra có kiểu dữ liệu **counter** dành cho các thao tác tăng/giảm theo model được hỗ trợ.

Ví dụ bảng counter tách theo metric, ngày và bucket:

~~~sql
CREATE TABLE views_by_bucket (
    tenant_id text,
    metric_id text,
    window_date date,
    bucket_id int,
    value counter,
    PRIMARY KEY ((tenant_id, metric_id, window_date, bucket_id))
);
~~~

Increment:

~~~sql
UPDATE views_by_bucket
SET value = value + 1
WHERE tenant_id = 'shop-a'
  AND metric_id = 'video-77:views'
  AND window_date = '2026-11-14'
  AND bucket_id = 7;
~~~

Các bucket với partition key ghép đầy đủ có thể được đặt trên nhiều token ranges theo partitioner của cluster, tạo cơ hội phân tán cập nhật.

### Giới hạn của Cassandra counters

- Increment counter **không idempotent** khi retry sau kết quả UNKNOWN; có thể áp dụng hai lần.
- Counter columns có **hạn chế schema và thao tác**; không xử lý như integer column thông thường, không trộn tùy tiện cùng non-counter columns.
- TTL và một số dạng update/transaction không hỗ trợ như ordinary row; cần thiết kế window lifecycle riêng thay vì giả định counter tự hết hạn theo TTL.
- Consistency level và replica repair liên quan đến cách đọc/ghi counter, nhưng **QUORUM không thay thế dedup event**.
- Một logical partition vẫn có thể nóng nếu chỉ partition theo tenantId/metricId rồi đặt mọi bucket thành clustering rows trong cùng partition.

Schema trên tạo **mỗi bucket là một partition key logical khác nhau**. Nếu muốn query tổng theo ngày, ứng dụng có thể phải đọc nhiều partitions rồi cộng, hoặc dùng bảng rollup riêng.

## 24. Cassandra: không lấy counter làm nguồn quyết định chống oversell

Giả sử tồn kho có available=3. Hai checkout cùng muốn mua 2 đơn vị:

~~~text
Checkout A đọc tổng = 3.
Checkout B đọc tổng = 3.

A giảm counter theo bucket A: -2.
B giảm counter theo bucket B: -2.

Tổng sau đó = -1.
~~~

Mọi increment/decrement có thể được ghi nhận theo cơ chế của counter, nhưng business invariant **available >= 0** đã bị phá.

Không thể đặt một điều kiện **global sum >= 2** bằng một lệnh update counter trên một bucket độc lập rồi coi nó tương đương transaction.

Các hướng bảo vệ:

- Một authoritative item/row cho stock với conditional write.
- Reservation/escrow theo quota đã cấp cho từng shard/region.
- Transaction/conditional protocol trong phạm vi engine hỗ trợ.
- Một inventory ledger và reconciliation, không chỉ read model count.

**Bộ đếm chia bucket là kỹ thuật tăng throughput của các delta được phép cộng**, không phải kỹ thuật tự cấp quyền tiêu thụ tài nguyên hữu hạn.

## 25. Đếm chính xác nghĩa là gì?

Trước khi chọn database, cần định nghĩa ba mức:

### 25.1. Exact theo event identity

Mỗi event hợp lệ được tính **đúng một lần** theo ID và nghiệp vụ:

~~~text
eventId E1 được nhận 3 lần -> effect +1
eventId E2 được nhận 1 lần -> effect +1
Tổng cần tăng = +2
~~~

Cần uniqueness/dedup bền vững hoặc pipeline tương đương.

### 25.2. Exact tại một snapshot

Khi đọc tổng, tất cả bucket values tương ứng một **trạng thái nhất quán tại một mốc logic**. Đòi hỏi snapshot/transaction hoặc cơ chế version/watermark có thể chứng minh.

### 25.3. Eventually correct / bounded staleness

Ứng dụng chấp nhận tổng tạm thời chậm và sẽ hội tụ sau khi ingest/aggregation hoàn tất. Ví dụ UI hiển thị lượt xem cập nhật trong vài giây.

Ba yêu cầu không đồng nhất:

- Dedup giúp **không nhân đôi effect**.
- Snapshot giúp **đọc nhất quán tại một mốc**.
- Staleness SLO giúp **giới hạn độ trễ quan sát**.

Một hệ có thể dedup chính xác nhưng read total eventual; hoặc sum tại snapshot chính xác dữ liệu đã ingest nhưng còn thiếu event đến muộn.

## 26. Đọc tất cả buckets không tự là một snapshot

Giả sử có hai buckets A, B và một thao tác **chuyển số lượng** giữa hai buckets:

~~~text
Ban đầu:
  A=10, B=0, tổng=10.

Read tổng:
  đọc A=10.

Transfer:
  A=0, B=10.

Read tổng:
  đọc B=10.

Kết quả cộng:
  10 + 10 = 20.
~~~

Tổng thực tế luôn là 10 trước và sau transfer, nhưng đọc hai bucket ở hai thời điểm đã cho tổng 20.

Đây là ví dụ chứng minh **mỗi read bucket đúng riêng lẻ không làm phép cộng nhiều bucket trở thành một snapshot nguyên tử**.

Với counter chỉ **tăng không âm**, phép cộng các bucket đọc lệch thời điểm thường cho giá trị nằm giữa các trạng thái trong cửa sổ đọc theo một số giả thiết, nhưng vẫn **không chứng minh nó là tổng tại một thời điểm duy nhất được bảo đảm bởi API**, nhất là khi có retry, mất ghi, correction hoặc replication lag.

Nếu cần tổng exact-at-time, xem transaction/snapshot hoặc checkpoint đã được xác nhận, không chỉ đọc B keys bằng nhiều GET.

## 27. Tăng giảm, sửa số liệu và tính nhất quán

Không phải counter nào cũng đơn điệu tăng.

Ví dụ:

~~~text
+1 khi like
-1 khi unlike
+1 khi hoàn tác unlike
~~~

Cần đảm bảo từng transition hợp lệ:

~~~text
NOT_LIKED -> LIKED: +1
LIKED -> NOT_LIKED: -1

Replay LIKE khi đã LIKED: +0
Replay UNLIKE khi đã NOT_LIKED: +0
~~~

State transition của **(userId, objectId)** có thể được bảo vệ trong một item/document có điều kiện; sau đó phát **delta event** để cập nhật counters.

Nếu chỉ tin event đến đúng thứ tự:

~~~text
UNLIKE trước LIKE
LIKE bị replay
~~~

tổng có thể sai. Cần version của quan hệ, dedup event ID và cách xử lý out-of-order.

Một **read model counter** có thể tạm trễ trong khi **source-of-truth relation state** vẫn đúng; cần công bố eventual consistency nếu đó là thiết kế.

## 28. Ledger sự kiện và bộ đếm materialized

Một kiến trúc vững khi cần audit:

~~~mermaid
flowchart LR
    E["Event ingress"] --> L["Durable event ledger / log"]
    L --> D["Dedup / validate / partition"]
    D --> B0["Bucket 0"]
    D --> B1["Bucket 1"]
    D --> B2["Bucket 2"]
    D --> BN["Bucket N"]
    B0 --> AG["Rollup / total"]
    B1 --> AG
    B2 --> AG
    BN --> AG
    AG --> API["Read API"]
~~~

**Ledger** lưu các event có ý nghĩa nghiệp vụ:

~~~json
{
  "eventId": "view-e1001",
  "tenantId": "shop-a",
  "metricId": "video-77:views",
  "eventTime": "2026-11-14T09:10:00Z",
  "delta": 1,
  "schemaVersion": 1
}
~~~

**Bucket counters** là materialized view của ledger, cho phép ghi nhanh và đọc tổng theo chính sách.

Ưu điểm:

- Có nguồn đối soát khi counter lệch.
- Có thể rebuild theo partition/window.
- Có thể thêm/đổi số bucket theo epoch.
- Có thể phát hiện event không hợp lệ và backfill event muộn.

Đánh đổi:

- Tốn lưu trữ/throughput cho ledger.
- Cần xử lý at-least-once delivery và checkpoint.
- Event log cũng có thể **hot partition** nếu partition key chọn sai.
- Event retention và quy định xóa dữ liệu phải được thiết kế rõ.

## 29. At-least-once delivery và idempotent effects

Một message broker/worker có thể giao một event nhiều lần:

~~~text
Event E1 -> Worker A.
Worker A cập nhật bucket.
Worker A crash trước khi ACK message.
Broker redeliver E1 -> Worker B.
~~~

Nếu B cứ increment, E1 được tính hai lần.

Một pattern là **inbox/event marker**:

~~~text
Atomic unit:
  nếu eventId chưa xử lý:
    ghi marker eventId
    áp dụng +1
  nếu đã xử lý:
    không cộng nữa
~~~

Điều quan trọng là **ghi marker và effect phải có cùng phạm vi atomicity hoặc cơ chế phục hồi tương đương**:

- Ghi marker rồi crash trước increment → event bị bỏ sót.
- Increment rồi crash trước marker → event bị đếm hai lần.

Nếu không thể transaction hai nơi, cần **workflow có trạng thái/ledger và reconcile**. Không nên gọi một bộ đếm “exactly once” chỉ vì handler có điều kiện:

~~~text
if (!seen(eventId)) {
  increment();
  markSeen();
}
~~~

Ba lệnh độc lập ở trên có race và crash window.

## 30. Một bucket có thể dùng batch delta thay vì per-event increment

Nếu traffic rất lớn, ngay cả 64 bucket và một lệnh mỗi event vẫn có thể quá tải hoặc quá đắt.

Một worker có thể gom:

~~~text
Trong 1 giây:
  Event E1..E400 trên bucket 07

Ghi:
  increment bucket 07 by 400
~~~

Lợi ích:

- Giảm số write operations và network round-trips.
- Có thể tận dụng batch pipeline và backpressure.

Đánh đổi:

- Có độ trễ giữa event và counter.
- Crash trước flush có thể mất batch nếu chỉ giữ RAM.
- Retry batch sau flush timeout có thể cộng lại 400 lần.
- Các event của batch cần checkpoint/batchId ổn định.

Một thiết kế tốt dùng **durable log offset/transactional checkpoint** hoặc **batch marker** để xác định chính xác một batch đã áp dụng chưa. Nếu broker partition/event log không có stable offset, phải dùng event IDs và trạng thái xử lý.

## 31. BatchId và offset không được dùng sai

Giả sử một batch:

~~~text
metricId = video-77:views
bucketId = 7
sourcePartition = p03
firstOffset = 900
lastOffset = 1299
delta = 400
batchId = "p03:900-1299:bucket07"
~~~

Muốn retry an toàn, **batchId** phải trùng khi gửi lại cùng batch và không trùng batch khác.

Không thể chỉ lưu **lastOffset=1299** nếu có hai worker xử lý out-of-order mà không có quy tắc xác định:

- Ai sở hữu source partition?
- Gaps trong offsets có được chấp nhận không?
- Một event được gửi sang nhiều buckets thế nào?
- Checkpoint được commit **cùng effect** hay có thể lệch?
- Rebalance consumer làm worker cũ vẫn tiếp tục không?

Khi có ownership change, lease/fencing hoặc conditional checkpoint giúp tránh worker cũ ghi đè trạng thái mới.

## 32. Chia bucket theo cửa sổ thời gian

Một video có thể tích lũy nhiều năm. Nếu chỉ có 64 bucket tồn tại mãi:

~~~text
views:video-77:bucket:00..63
~~~

thì write hotness vẫn được phân tán, nhưng việc giữ lịch sử theo ngày/tháng và retention khó hơn.

Có thể tạo **time buckets**:

~~~text
views:video-77:2026-11-14:bucket:00..63
views:video-77:2026-11-15:bucket:00..63
...
~~~

Tổng trong một ngày:

\[
C_{\mathrm{day}}=\sum_{b=0}^{B-1} C_{\mathrm{day},b}
\]

Tổng trong nhiều ngày:

\[
C_{\mathrm{range}}=
\sum_{d\in\mathrm{days}}
\sum_{b=0}^{B_d-1} C_{d,b}
\]

Ưu điểm:

- Truy vấn theo thời gian thuận tiện.
- Có thể đóng cửa sổ cũ để rollup.
- Retention/xóa theo window dễ lập kế hoạch hơn.
- Điều chỉnh B riêng từng window/epoch.

Nhược điểm:

- Query 90 ngày × 64 bucket có thể cần tới 5.760 bucket values nếu không có rollup.
- Event đến muộn có thể cập nhật cửa sổ đã tưởng đóng.
- Timezone và day boundary cần chuẩn hóa.

## 33. Event time, processing time và late events

Một view event xảy ra:

~~~text
eventTime:      23:59:59 UTC ngày 14
processingTime: 00:00:05 UTC ngày 15
~~~

Nếu bucket theo **processingTime**, event được cộng vào ngày 15. Nếu nghiệp vụ yêu cầu đếm theo **eventTime**, nó thuộc ngày 14.

Định nghĩa:

- **Event time:** khi sự kiện thực sự xảy ra theo nguồn dữ liệu.
- **Processing time:** khi hệ thống nhận/xử lý sự kiện.
- **Watermark:** mốc hỗ trợ xác định dữ liệu trễ có thể còn đến, theo mô hình stream processing.

Để không đếm sai ngày, cần:

1. Chọn time semantics trong metric contract.
2. Chuẩn hóa timestamp/UTC, xử lý đồng hồ client không đáng tin.
3. Định nghĩa cửa sổ được nhận late events bao lâu.
4. Khi window đã finalized, tạo **correction/version mới** nếu sự kiện hợp lệ xuất hiện muộn.
5. Đảm bảo rollup và cache được cập nhật idempotent.

**Không dùng UTC day và local midnight lẫn lộn** giữa các worker; việc đổi ngày theo timezone khác có thể khiến cùng event được đặt hai window khác nhau.

## 34. TTL, dữ liệu cũ và khả năng replay

TTL có thể giúp dọn các bucket tạm:

~~~text
metrics per minute giữ 7 ngày
daily rollup giữ 1 năm
raw event ledger giữ theo chính sách nghiệp vụ
~~~

Nhưng:

- TTL xóa bucket **không tự bảo đảm daily rollup đã nhận đủ event**.
- TTL xóa dedup marker có thể khiến event cũ được replay và đếm lại.
- Một cửa sổ đã xóa nhưng có late event cần policy bỏ qua, ghi correction hoặc lưu ở nơi riêng.
- Counter types và TTL support khác nhau theo engine; ví dụ Cassandra counter columns không được dùng TTL như ordinary columns.
- TTL trong Redis/MongoDB/DynamoDB có thời điểm và cơ chế xóa khác nhau; không nên xem deadline là thời điểm bản ghi biến mất tức thì.

Quy tắc an toàn: **rollup/verification checkpoint đã hoàn tất trước khi dọn nguồn cần thiết**, có buffer cho late events và recovery.

## 35. Tổng hợp theo tầng: minute → hour → day → lifetime

Nếu phải đọc một lifetime total từ hàng nghìn windows, cộng trực tiếp mọi bucket không còn hiệu quả.

Một thiết kế rollup:

~~~mermaid
flowchart TD
    E["View events"] --> M["Minute buckets × B"]
    M --> H["Hourly rollup"]
    H --> D["Daily rollup"]
    D --> L["Lifetime total"]
    M --> NOW["Current window delta"]
    L --> READ["Read API"]
    NOW --> READ
~~~

Khi UI cần tổng hiện tại:

~~~text
completed daily/hourly totals
+ active minute/day deltas
= displayed lifetime count
~~~

Vấn đề lớn là **không tính trùng các phần đã rollup**:

~~~text
Minute M đã cộng vào hourly H.
Nếu read tổng vừa lấy H vừa lấy M
  -> M bị tính hai lần.
~~~

Cần lưu:

- Rollup watermark/covered interval.
- Version/epoch và trạng thái finalized.
- Source offsets/IDs đã được tính.
- Quy tắc không đọc chồng các khoảng đã covered.
- Reconciliation với ledger hoặc source buckets.

Không nên chỉ chạy mỗi phút:

~~~text
hourly += sum(minuteBuckets)
~~~

mà không có cơ chế **idempotent rollup**; retry job có thể cộng một khoảng nhiều lần.

## 36. Rollup idempotent: thay thế snapshot hoặc ghi delta một lần

Có hai cách khái niệm:

### Ghi giá trị tổng của khoảng bằng replace/version

~~~text
hour:2026-11-14T09
  sourceRange: 09:00..09:59
  sourceVersion: 42
  value: 115000
~~~

Nếu job tính lại cùng sourceVersion, nó **replace** cùng kết quả thay vì cộng lặp.

### Ghi delta theo batchId duy nhất

~~~text
batchId: minute:09:03:v3
delta: 4200
~~~

Rollup nhận delta một lần nếu batchId chưa được áp dụng. Cần transaction/marker hoặc cơ chế idempotent effect tương đương.

Đổi nguồn từ 4200 thành 4210 vì late event cần:

~~~text
Correction delta: +10
hoặc replace snapshot version mới: 4210
~~~

Không thể phát lại toàn bộ 4210 như một delta cộng mới vào rollup đã có 4200.

## 37. Khi read tổng trở thành hot key mới

Sau khi tách write thành 64 buckets, ứng dụng có thể nhận **100.000 reads/s** hỏi tổng lifetime. Nếu mỗi read phải lấy 64 buckets:

\[
100000 \times 64 =
6400000\ \text{bucket reads/s}
\]

Đây là phép tính minh họa để thấy **read amplification**, chưa tính cache, batching hoặc cách database thực thi truy vấn.

Có thể dùng:

- **Cached total** cập nhật theo chu kỳ.
- **Materialized rollup** làm đường đọc chính.
- **Cache TTL ngắn** phù hợp staleness SLO.
- **Push/stream aggregate updates** cho dashboard.
- **Read replicas** nếu engine cho phép và độ mới chấp nhận được.
- **Throttling hoặc coalescing** nhiều yêu cầu cùng đọc tổng.

Đừng chỉ chuyển hot write key thành **hot aggregate read query**. Đo cả hai đường sau khi cải tiến.

## 38. Cache total và độ mới của kết quả

Ví dụ API hiển thị:

~~~json
{
  "videoId": "video-77",
  "viewCount": 12850000,
  "computedAt": "2026-11-14T09:10:00Z",
  "freshness": "eventual"
}
~~~

Giá trị được tổng hợp có thể trễ vài giây so với những events vừa nhận. Điều này thường chấp nhận cho lượt xem, nhưng phải được ghi rõ trong hợp đồng.

Một API quan trọng hơn có thể cung cấp:

~~~text
GET /metrics/video-77/views?consistency=authoritative
~~~

nhưng không được tự gắn nhãn **authoritative** nếu thực tế nó chỉ cộng một nhóm replica eventual mà không có snapshot/verification.

Hãy phân biệt:

- **Event ingestion acknowledged**.
- **Bucket update applied**.
- **Rollup committed**.
- **Cached total refreshed**.
- **Response delivered**.

Mỗi mốc có độ trễ và bảo đảm khác nhau.

## 39. Thay số bucket: vấn đề modulo và layout epoch

Giả sử trước đây:

~~~text
epoch 1:
  B=8
  bucket=hash(eventId) mod 8
~~~

Sau tăng tải, muốn:

~~~text
epoch 2:
  B=32
  bucket=hash(eventId) mod 32
~~~

Với nhiều event, **bucket mới khác bucket cũ**. Nếu một request đã được xử lý ở epoch 1 nhưng retry dưới epoch 2, nó có thể được đưa sang bucket khác; dedup marker cũ không nhìn thấy.

Giải pháp không phải chỉ đổi constant **BUCKET_COUNT=32** trên mọi service và hy vọng tự đúng.

Một contract cần có:

~~~yaml
metricId: "video-77:views"
layouts:
  - epoch: 1
    bucketCount: 8
    state: "DRAINING"
  - epoch: 2
    bucketCount: 32
    state: "ACTIVE"
assignment:
  identity: "eventId"
  useLayoutRecordedAtIngestion: true
~~~

Nếu không lưu epoch từng event hoặc có một quy tắc cutover chắc chắn, retry sau đổi cấu hình có thể đếm trùng.

## 40. Migration từ 8 lên 32 buckets

Một chiến lược có chủ đích:

~~~mermaid
flowchart TD
    A["Epoch 1: 8 buckets"] --> B["Lưu layout/epoch mới"]
    B --> C["Đặt cutover barrier/ingestion assignment"]
    C --> D["Sự kiện mới dùng epoch 2: 32 buckets"]
    D --> E["Sự kiện cũ/retry giữ epoch đã ghi"]
    E --> F["Read tổng từ cả hai epoch, không đếm bản copy hai lần"]
    F --> G["Drain, reconcile, finalize epoch 1"]
    G --> H["Rollup/archive và dọn khi an toàn"]
~~~

Trọng tâm:

1. Có một **nguồn quyết định epoch** có thẩm quyền.
2. Event/operationId được gắn **epoch ổn định** khi vào hệ.
3. Các workers cũ và mới có thể chạy đồng thời nhưng không tự đổi routing của cùng event.
4. Đường đọc biết những epochs nào vẫn chứa effect hợp lệ.
5. Nếu copy/backfill dữ liệu cũ sang buckets mới, không được sum **cả bản copy lẫn nguồn** như hai hiệu ứng độc lập.
6. Cần checkpoint/verification và rollback plan nếu cutover thất bại.
7. Chỉ dọn epoch cũ sau khi window và replay policy đã đóng an toàn.

Trong các hệ có event ledger, có thể **rebuild toàn bộ counter ở layout mới** từ events rồi cutover read sang version mới khi kiểm chứng xong, thay vì trộn các bản copy không kiểm soát.

## 41. Không dùng dual-write mù quáng khi migration

Một chiến thuật sai:

~~~text
Mỗi view event mới:
  increment bucket epoch 1
  increment bucket epoch 2

Read:
  sum tất cả epoch 1 và epoch 2
~~~

Kết quả: event bị tính hai lần.

Nếu dual-write được dùng như một phần migration, cần **quy tắc rõ ràng về nguồn được đọc, phiên bản nào là shadow, checkpoint của từng event, và thời điểm chuyển read authority**.

Ví dụ:

~~~text
Epoch 1: authoritative until cutover
Epoch 2: shadow/backfill for verification

Trước cutover:
  read chỉ epoch 1

Sau cutover có barrier đáng tin:
  read chỉ epoch 2
~~~

Nếu không chứng minh được sự nhất quán của shadow và write in-flight, không được cắt đổi chỉ bằng một flag đơn giản.

## 42. Tách bộ đếm theo nhiều phần và khả năng chịu lỗi

Khi có 64 buckets:

~~~text
Bucket 0..31: phục vụ bình thường.
Bucket 32: replica không sẵn sàng.
Bucket 33..63: phục vụ bình thường.
~~~

Read tổng sẽ làm gì?

| Chính sách | Kết quả | Khi nào hợp lý? |
|---|---|---|
| **Fail closed** | Trả lỗi/không xác nhận tổng | Cần tính chính xác, không chấp nhận thiếu bucket |
| **Partial total** | Trả tổng tạm + đánh dấu partial | Dashboard/analytics chấp nhận thiếu dữ liệu có công bố |
| **Last known bucket** | Dùng giá trị đã cache + stale metadata | UI eventual có freshness SLO |
| **Retry/fallback** | Đọc replica khác theo protocol | Khi có lựa chọn hợp lệ, trong deadline |
| **Ledger recomputation** | Tính lại theo event source | Khi cần khôi phục/đối soát, có thể chậm |

**Không trả một tổng thiếu bucket dưới nhãn exact**. Response có thể có:

~~~json
{
  "total": 12850000,
  "complete": false,
  "missingBuckets": 1,
  "asOf": "2026-11-14T09:10:00Z"
}
~~~

Nhãn và cấu trúc chỉ minh họa; nếu không thể xác định chính xác bucket nào thiếu, không được bịa độ tin cậy.

## 43. Counter vượt giới hạn kiểu số

Một counter có thể vượt phạm vi **32-bit signed integer**, hoặc nhiều buckets cộng lại vượt phạm vi của type dùng để tổng hợp.

Các điểm cần kiểm tra:

- Integer width của storage engine.
- Kiểu số của SDK/driver và JSON serializer.
- JavaScript Number chỉ biểu diễn chính xác các số nguyên trong phạm vi an toàn nhất định.
- Overflow khi cộng các bucket trước khi convert sang kiểu rộng.
- Negative values/corrections có được phép không?
- Chuyển đổi đơn vị: views, cents, milliseconds không được trộn.

Ví dụ Java:

~~~java
long total = 0L;
for (long bucketValue : bucketValues) {
    total = Math.addExact(total, bucketValue);
}
~~~

**Math.addExact** sẽ ném lỗi khi overflow long thay vì âm thầm tạo tổng sai. Với số lớn hơn khả năng kiểu primitive hoặc trường hợp cần số thập phân, chọn kiểu thích hợp như **BigInteger/BigDecimal** theo ý nghĩa metric.

Nếu metric là số tiền, không dùng float không kiểm soát và không bỏ qua ledger/audit chỉ vì có BigInteger.

## 44. Hot read key: đôi khi không cần sharded counter

Giả sử một key cấu hình được đọc 50.000 lần/giây nhưng chỉ ghi một lần/ngày.

~~~text
config:pricing-rules
  reads/s = 50.000
  writes/day = 1
~~~

Tách nó thành 64 counters **không phù hợp**. Các phương án tốt hơn:

- Cache local/application memory với version hoặc TTL.
- CDN/cache nếu dữ liệu phù hợp.
- Read replicas hoặc fan-out cache.
- Coalescing nhiều request cùng đợi một lookup.
- Push invalidation hoặc event-based config update.
- Nhóm các field được đọc cùng nhau theo cấu trúc phù hợp.

**Giải pháp phụ thuộc loại hotspot**: read-heavy, write-heavy, large key, lock contention và cross-shard fan-out không cùng một bài toán.

## 45. Read amplification và write amplification

Tách từ một counter thành B buckets tạo một đánh đổi:

~~~text
Trước:
  Mỗi event = 1 write vào một key nóng.
  Mỗi total read = 1 read.

Sau:
  Mỗi event = 1 write vào một trong B keys.
  Mỗi total read = tối đa B reads/aggregation.
~~~

Nếu thêm dedup marker:

~~~text
Mỗi event = counter effect + marker/ledger/checkpoint.
~~~

Nếu thêm rollups:

~~~text
Mỗi event = bucket update,
định kỳ rollup/update cache,
thỉnh thoảng reconciliation.
~~~

Do đó, tách counter giảm **contention trên từng hot write key** nhưng có thể tăng tổng số operations, bytes, metadata hoặc background jobs. Không nên so chỉ số **single-key QPS** mà bỏ qua **tổng cost per accepted event**.

## 46. Shard-aware batching và phân bố tải

Giả sử một worker gom 1.000 events:

~~~text
Bucket 0: 120 events
Bucket 1: 145 events
Bucket 2: 110 events
...
Bucket 7: 125 events
~~~

Thay vì 1.000 increments, worker có thể gửi tối đa B bucket deltas trong một batch **nếu** nguồn event được checkpoint bền, hiệu ứng theo batchId idempotent và timeout được xử lý an toàn.

Nhưng:

- Một batch quá lớn có thể gây thắt cổ chai và làm tăng mất mát nếu buffer chỉ ở RAM.
- Batch gửi tới một physical shard không nên vượt resource budget.
- Các APIs bulk write có thể trả **partial success**, cần theo dõi từng item.
- Ghi event marker/dedup có thể vẫn chiếm nhiều work.
- Không nên làm batch ảnh hưởng latency SLO của sự kiện cần phản hồi tức thì.

Benchmark phải đo cả **độ trễ ingestion→visibility**, không chỉ throughput ghi buckets.

## 47. Bài toán đếm lượt xem khác bài toán rate limiting

Rate limiting có vẻ giống counter:

~~~text
user-1 API calls in current minute
~~~

Nhưng mục tiêu thường là **từ chối ngay khi vượt ngưỡng**, không chỉ hiển thị tổng.

Nếu mỗi request chọn một bucket ngẫu nhiên và chỉ kiểm tra bucket đó:

~~~text
Limit toàn cục: 100 requests/min.
10 buckets, mỗi bucket thấy <= 100.
~~~

Client có thể vượt xa giới hạn thật.

Các cách có thể dùng:

- Một authoritative atomic counter/token bucket cho mỗi principal nếu tải cho phép.
- Phân bổ quota/escrow tới nhiều workers, sau đó trừ quota cục bộ.
- Rate limiting phân tầng (local + global) với mức overshoot được định nghĩa.
- Sliding-window log/counter hoặc approximate enforcement theo hợp đồng.

**Sharded counter phục vụ analytics không tự trở thành distributed rate limiter chính xác.** Với quota hard limit, cần cơ chế cấp quyền tiêu thụ và phối hợp phù hợp.

## 48. Escrow/quota: tách ghi mà vẫn giữ tổng ngân sách

Giả sử có 100 vé còn được phép cấp, cần xử lý tại bốn vùng.

Một chiến lược:

~~~text
Global stock authority phân bổ:
  Region A quota = 25
  Region B quota = 25
  Region C quota = 25
  Region D quota = 25

Tổng quota được cấp = 100.
~~~

Mỗi vùng chỉ được xác nhận giữ ghế trong **quota cục bộ còn lại**. Khi hết quota, nó phải xin cấp thêm từ nguồn thẩm quyền, không tự trừ sang quota của vùng khác.

Bất biến:

\[
\sum_{\mathrm{regions}}Q_{\mathrm{allocated}}
\leq \mathrm{AvailableGlobal}
\]

Với escrow đúng thiết kế, có thể phân tán quyết định ghi mà không cho tổng quyền đã cấp vượt tài nguyên thật.

Nhưng cần:

- Atomic transfer quota giữa vùng.
- Chống double allocation và retry.
- Lease/expiry/return unused quota đúng cách.
- Sổ reservation và reconciliation.
- Xử lý một vùng offline giữ quota lâu.

**Không được cộng các sharded counters rồi dùng kết quả eventual làm điều kiện cấp thêm quota trong cùng thời điểm**.

## 49. Không phải mọi CRDT counter đều bảo vệ invariant

**G-counter** và **PN-counter** có thể hội tụ theo phép gộp thích hợp, giúp các increments/decrements độc lập được tính đầy đủ.

Ví dụ:

~~~text
Region A tăng +5.
Region B tăng +7.
State merge -> total +12.
~~~

Nhưng nếu cùng có:

~~~text
Global stock = 10.
Region A trừ 8.
Region B trừ 8.
~~~

một counter hội tụ có thể cho tổng -6. Nó đã ghi nhận đầy đủ hai hành động nhưng **business invariant không được bảo vệ**.

CRDT phù hợp cho một số metrics và quan hệ có merge semantics; hard constraints như **nonnegative inventory** cần escrow, authority hoặc một protocol khác.

## 50. Multi-tenant hot keys và công bằng tài nguyên

Một tenant rất lớn có thể chiếm phần lớn throughput:

~~~text
shop-a views/s = 50.000
shop-b views/s = 500
shop-c views/s = 350
~~~

Nếu chỉ có một global queue/worker pool, shop-a có thể làm shop-b/c bị trễ dù các tenant dùng bucket keys khác nhau.

Thiết kế nên xét:

- Partition key gồm tenantId để định danh rõ.
- Per-tenant quotas hoặc weighted fair scheduling.
- Hot tenant riêng pool/shard/cluster nếu cần.
- Không dùng cùng bucket key cho hai tenant do key collision.
- Phân quyền và validation cho eventId/metricId.
- Dashboard latency và backlog theo nhóm tenant, không lộ PII.

**Phân tán counter keys không tự bảo đảm fairness của pipeline ingest**. Một bottleneck upstream (queue partition, worker pool hoặc broker) vẫn có thể làm dữ liệu của tenant nhỏ chậm.

## 51. Tránh counter key bị tấn công tạo tải

Nếu user có thể tự chọn metricId hoặc eventId, họ có thể cố:

- Gửi nhiều request tới một metric nổi tiếng.
- Chọn IDs có hash va chạm để dồn tải vào một bucket.
- Gửi trùng eventId để làm dedup store phình to.
- Tạo hàng triệu metric IDs để vượt giới hạn storage.
- Gửi delta âm/lớn gây lỗi kiểu số hoặc phá bất biến.

Các biện pháp:

1. Xác thực user/tenant và quyền ghi metric.
2. Validate event type, delta range, size và timestamp.
3. Dùng hash phù hợp với đầu vào có thể bị điều khiển đối kháng nếu cần.
4. Rate limit theo principal/tenant và áp dụng quota.
5. Không để client ngoài quyết định bucketId tùy ý khi điều đó có thể gây hot bucket.
6. Dùng operation IDs có scope và dedup policy đúng.
7. Chống event replay vượt retention theo nghiệp vụ.

Không nên tin rằng bucket count lớn sẽ tự giảm mọi dạng abuse.

## 52. Một kịch bản đo hiệu năng trước và sau

Giả sử trong một thử nghiệm có kiểm soát:

~~~text
Trước:
  Một counter key
  20.000 increments/s
  p99 increment = 600 ms
  throttling = 12%

Sau:
  32 buckets
  20.000 increments/s
  p99 increment = 35 ms
  throttling = 0,3%
  total read cần aggregate 32 buckets
~~~

Số liệu trên là **giả định minh họa**, không phải benchmark thực của một sản phẩm. Kết luận chưa đầy đủ nếu không đo:

- Tỷ lệ event bị đếm trùng hoặc bị bỏ sót.
- Độ trễ từ ingest đến khi total read nhìn thấy event.
- Chi phí mỗi 1.000 accepted events.
- p99 total read.
- Phân bố tải trên physical partitions.
- Thời gian recovery khi một bucket/node lỗi.
- Tính đúng của daily/lifetime rollup.

Một tối ưu chỉ giảm p99 ghi nhưng làm tổng đếm sai **không phải cải tiến phù hợp** cho metric có yêu cầu độ tin cậy cao.

## 53. Fault injection: những lỗi nên chủ động tạo

| Tình huống | Rủi ro | Bằng chứng cần kiểm tra |
|---|---|---|
| Crash trước increment | Bỏ event nếu không replay | Ledger/checkpoint có cho xử lý lại? |
| Crash sau increment trước ACK | Double increment khi retry | Marker/batchId có chặn hiệu ứng trùng? |
| Counter bucket timeout | Không rõ đã tăng chưa | Outcome UNKNOWN có được kiểm chứng? |
| Replica failover | Mất write đã ACK theo cấu hình yếu | Durability/replication guarantee |
| Nhiều workers cùng tăng | Lost update nếu GET+SET | Atomic increment/CAS |
| Event đến trễ một ngày | Sai time window | Event time/watermark/correction |
| Thay B từ 8 lên 32 | Retry chuyển bucket | Layout epoch ổn định |
| Rollup job chạy hai lần | Double counting | Idempotent source range/version |
| Một bucket không đọc được | Tổng thiếu | Fail closed/partial được đánh dấu |
| TTL dọn dedup quá sớm | Replay tính lại event | Retention/replay contract |
| Một tenant tăng đột biến | Các tenant khác bị đói tài nguyên | Fair scheduling/quota |
| Read total vượt giới hạn | Read amplification/slow shard | Cache/rollup/fan-out SLO |

Fault injection cần chạy trong môi trường được phép, có dữ liệu thử nghiệm và khả năng khôi phục. Không dựa vào một lần test không lỗi để kết luận mọi failure schedule đều an toàn.

## 54. Reconciliation: làm sao biết bộ đếm đúng?

Nếu có authoritative event ledger, một job đối soát có thể:

~~~text
1. Chọn metric + window cụ thể.
2. Đọc eventIds hợp lệ từ ledger.
3. Dedup theo định nghĩa nghiệp vụ.
4. Tính expected delta/total.
5. Đọc counter buckets và rollups.
6. So expected với observed.
7. Nếu lệch, xác định missing/duplicate/replayed events.
8. Tạo correction/rebuild có checkpoint và audit.
~~~

Một kết quả đối soát:

~~~json
{
  "tenantId": "shop-a",
  "metricId": "video-77:views",
  "window": "2026-11-14",
  "expectedFromLedger": 2084301,
  "observedFromBuckets": 2084303,
  "difference": 2,
  "status": "REQUIRES_INVESTIGATION"
}
~~~

Không nên tự chạy:

~~~text
counter -= difference
~~~

khi chưa biết drift đến từ **batch duplicated, late event, wrong window hoặc read stale**, vì sửa nhầm có thể làm sai thêm.

Một chính sách có thể **rebuild materialized counters** từ source đã xác minh rồi cutover bằng version, thay vì patch số âm/dương không có lịch sử.

## 55. Đặt SLO riêng cho write, read và correctness

| SLO/metric | Câu hỏi |
|---|---|
| **Ingestion success rate** | Bao nhiêu event hợp lệ được nhận bền vững? |
| **p99 increment latency** | Một bucket update mất bao lâu? |
| **Bucket throttling rate** | Có bucket vượt resource budget không? |
| **Max/mean bucket throughput ratio** | Phân bố có lệch không? |
| **Ingest-to-visible lag** | Event mất bao lâu xuất hiện trong total? |
| **p99 aggregate read latency** | Đọc B bucket/rollup có đáp ứng UX? |
| **Rollup backlog/age** | Các windows đã được tổng hợp đến đâu? |
| **Duplicate suppressed count** | Bao nhiêu retry bị chặn? |
| **Counter reconciliation drift** | Tổng materialized lệch ledger bao nhiêu? |
| **Missing/partial bucket reads** | Có trả thiếu kết quả không? |
| **Cost per accepted event** | Giá trị throughput có bù được storage/ops? |
| **Recovery time after failover** | Bao lâu pipeline hội tụ lại? |

Đừng gom các yêu cầu thành một chữ **“nhanh”**. Tải cao có thể cần ghi được 50.000/s nhưng giao diện chỉ cần cập nhật mỗi 5 giây; ngược lại một hệ kế toán có thể chấp nhận ingest chậm hơn để đổi lấy ledger chính xác, có audit.

## 56. Một quy trình thiết kế thực tế

~~~mermaid
flowchart TD
    A["Xác định hot key và business semantics"] --> B{"Read-heavy hay write-heavy?"}
    B -->|"Read-heavy"| C["Cache, read replicas, coalescing"]
    B -->|"Write-heavy, delta cộng được"| D["Chọn bucket count và placement"]
    B -->|"Hard invariant"| E["CAS / authority / escrow / transaction"]
    D --> F["Stable eventId, hash và layout epoch"]
    F --> G["Atomic bucket update + dedup/ledger"]
    G --> H["Read sum hoặc cached/rollup total"]
    H --> I["Time windows, late events, retention"]
    I --> J["Benchmark skew, p99, cost, correctness"]
    J --> K["Fault injection, migration, reconciliation"]
    C --> K
    E --> K
~~~

Các bước chi tiết:

1. **Xác định metric và đơn vị event**: view, click, like, request, money, stock hay quota.
2. **Đo nguyên nhân nóng**: QPS/key, physical partition, read/write ratio, contention.
3. **Đặt tính đúng cần bảo vệ**: count chính xác theo event, total snapshot hay eventual với freshness SLO.
4. **Xác định nguồn thẩm quyền**: counter trực tiếp hay event ledger/materialized view.
5. **Thiết kế bucket key** gồm tenant, metric, window, bucket, epoch.
6. **Chọn số bucket từ peak rate và phép đo** chứ không lấy một con số cố định theo phong trào.
7. **Kiểm tra physical distribution**: bucket IDs có thật sự map tới nhiều partitions/nodes không?
8. **Chọn assignment** random, stable hash(eventId), worker hoặc region theo semantics.
9. **Thiết kế idempotency**: marker/transaction, durable log offset hoặc reconciliation.
10. **Chọn read path**: sum trực tiếp, cached total, hierarchical rollup, snapshot khi cần.
11. **Thiết kế lifecycle**: TTL, time windows, late events và backfill.
12. **Chuẩn bị thay đổi B**: layout epoch, cutover, dual-read/shadow nếu có và chống đếm trùng.
13. **Test lỗi**: timeout sau commit, event replay, bucket unavailable, migration, cache stale.
14. **Theo dõi correctness + performance**: không chỉ throughput mà còn total drift.

## 57. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Thêm node là key nóng tự phân tán” | Một key vẫn một partition logic | Tách hiệu ứng/key hoặc đổi data model |
| “Một document nhỏ không thể nóng” | Hotness phụ thuộc rate/contestion | Đo QPS và latency theo key |
| “Tạo 64 bucket là đã chia 64 physical shards” | Placement/hash có thể gom chung | Kiểm tra partition keys và routing |
| “Redis key có cùng hash tag sẽ phân tán” | Cùng tag về cùng slot | Dùng tags riêng nếu cần phân tán writes |
| “Hash(eventId) tự chống duplicate” | Retry cùng bucket vẫn increment | Dedup/transaction/ledger |
| “INCRBY nguyên tử nghĩa là exactly once” | Gửi lặp có thể tăng lặp | Stable operation ID và effect record |
| “Lua script Redis tự rollback khi lỗi” | Runtime error có thể để lại hiệu ứng trước đó | Tiền kiểm, protocol, reconciliation |
| “QUORUM giải quyết idempotency” | Quorum không biết ý định event | Marker/ledger/checkpoint |
| “Cassandra counter có thể TTL như row thường” | Counter có hạn chế thao tác | Thiết kế lifecycle/rollup riêng |
| “DynamoDB B buckets chung partition key luôn cân bằng” | Physical partition có thể vẫn nóng | Chọn write-sharding key thực sự phân tán |
| “Tổng N buckets luôn là snapshot nguyên tử” | Read diễn ra ở các mốc khác nhau | Snapshot/rollup version nếu cần |
| “Distinct users bằng sum distinct từng bucket” | User có thể nằm ở nhiều bucket | Union/mergeable sketch hoặc global dedup |
| “CRDT counter bảo vệ stock >= 0” | Tổng có thể âm sau concurrent decrements | Escrow/quota/CAS |
| “Đổi B=8 sang B=32 là sửa một constant” | Retry event chuyển bucket, duplicate | Epoch và migration protocol |
| “Dual-write hai layouts rồi cộng cả hai” | Event bị tính trùng | Shadow/read authority/cutover rõ |
| “Ghi rollup += snapshot mỗi lần là an toàn” | Retry rollup cộng lặp | Replace/version hoặc batch dedup |
| “TTL dọn bucket thì dữ liệu đã lên rollup” | Rollup có thể chưa xong | Checkpoint và retention margin |
| “Một bucket lỗi vẫn trả total exact” | Thiếu một phần dữ liệu | Fail closed hoặc đánh dấu partial |
| “Metric views giống likes” | Like cần uniqueness của quan hệ | State transition và event deltas |
| “Read-heavy hot key nên tách counter” | Tách có thể tăng read amplification | Cache/replica/coalescing |
| “Một lần đối soát lệch thì cứ cộng hiệu chỉnh” | Có thể do stale hoặc late event | Phân loại nguồn lệch trước khi sửa |
| “Counter nhanh nghĩa là hệ đúng” | Drift/double events có thể ẩn | Metrics correctness + fault tests |

## 58. Bài tập thực hành

### Bài tập 1 — Tìm nguồn hotness

Cluster có 16 nodes nhưng 95% increments đi vào một key. Giải thích vì sao thêm nodes không đủ và cần đo những gì ở key, partition, node và API trước khi thay schema.

### Bài tập 2 — Chọn số bucket

Peak 60.000 increments/s, mục tiêu mỗi bucket không vượt 1.200/s theo benchmark nội bộ. Tính số bucket tối thiểu trong mô hình phân bố đều và đề xuất headroom; liệt kê ba lý do kết quả tính chưa phải bảo đảm thực tế.

### Bài tập 3 — Random vs stable hash

Event E100 bị gửi ba lần vì worker timeout. So sánh việc chọn random bucket và stableHash(eventId) mod B. Giải thích vì sao cả hai vẫn cần cơ chế dedup nếu mục tiêu là count mỗi event đúng một lần.

### Bài tập 4 — Physical placement

64 bucket records của cùng video được shard theo videoId. Tại sao vẫn có hot partition? Thiết kế khóa có bucket component để phân tán, đồng thời mô tả đánh đổi đối với query đọc total.

### Bài tập 5 — Redis Cluster hash tag

So sánh hai mẫu:

~~~text
views:{video-77}:B00, views:{video-77}:B01
views:{video-77:B00}:value, views:{video-77:B01}:value
~~~

Mẫu nào buộc cùng slot, mẫu nào có cơ hội phân tán? Cần kiểm tra gì để biết thực tế các keys nằm trên nodes khác nhau?

### Bài tập 6 — Redis Lua dedup

Viết script minh họa **SADD eventId** và **INCRBY bucket** trong cùng slot. Xác định ít nhất ba giới hạn về failover, bộ nhớ, TTL và runtime errors khiến giải pháp chưa bảo đảm exactly-once bền vững toàn hệ.

### Bài tập 7 — DynamoDB write sharding

Thiết kế 32 counter items cho video-77. Viết outline UpdateItem tăng một bucket, sau đó thiết kế đường BatchGet/GetItem để cộng tổng và nêu tác động khi một bucket read thất bại.

### Bài tập 8 — DynamoDB transaction marker

Hai request cùng eventId đến đồng thời. Đề xuất TransactWriteItems gồm Put event marker có điều kiện và Update bucket ADD 1. Phân tích TTL marker, transaction limits và retry timeout.

### Bài tập 9 — MongoDB buckets

Viết updateOne với $inc và upsert cho một document bucket. Viết aggregation $match + $group để lấy tổng. Giải thích vì sao shard key chỉ có metricId có thể vẫn là bottleneck.

### Bài tập 10 — MongoDB và event dedup

Một retry sau commit làm $inc chạy lại. Thiết kế event marker duy nhất và transaction cùng bucket update, sau đó chỉ ra nhược điểm về throughput/cost nếu mỗi view phải chạy một multi-document transaction.

### Bài tập 11 — Cassandra counters

Tạo bảng counter theo metricId, windowDate, bucketId và dùng UPDATE value=value+1. Giải thích vì sao Cassandra counter update bị retry có nguy cơ đếm hai lần và vì sao không mặc định dùng TTL như ordinary column.

### Bài tập 12 — Counter vs tồn kho

Hai checkout cùng thấy stock=3 và muốn mua 2. Cho chúng giảm hai buckets độc lập. Tổng cuối là bao nhiêu? Thiết kế nguồn authoritative hoặc escrow quotas để bảo đảm không oversell.

### Bài tập 13 — Phép cộng và distinct

Bucket A có users {U1,U2}, bucket B có {U2,U3}. Tính tổng từng bucket và số users unique toàn hệ. Giải thích cần merge set/sketch như thế nào thay vì cộng distinct counts.

### Bài tập 14 — Snapshot

Hai bucket A=10, B=0. Một transfer chuyển 10 từ A sang B giữa hai lần đọc. Thiết kế lịch sử mà read tổng trả 20 dù tổng thực luôn 10. Đề xuất cách lấy snapshot hoặc sử dụng rollup đã finalize.

### Bài tập 15 — Batch event processing

Worker nhận 400 events trên một bucket, ghi +400 rồi crash trước checkpoint. Hãy chỉ ra double count risk và thiết kế batchId/transactional checkpoint hoặc rebuild từ ledger.

### Bài tập 16 — Time windows

Một view event xảy ra 23:59:59 UTC nhưng được xử lý sau nửa đêm. Nêu cách gán bucket theo event time vs processing time, late events và correction sau khi rollup đã finalize.

### Bài tập 17 — Rollup

Thiết kế minute buckets, hourly rollups, daily totals. Một hourly job bị retry hai lần; làm thế nào tránh cộng cả cùng một minute source range hai lần?

### Bài tập 18 — Thay 8 lên 32 buckets

Một event E100 đã xử lý dưới epoch 1 (B=8), retry sau khi epoch 2 (B=32) active. Thiết kế metadata/operation ID để retry không tạo effect ở bucket mới lần thứ hai.

### Bài tập 19 — Dual-write migration

Trong cutover, mỗi event được ghi đồng thời vào layout 8 và 32 buckets. Vì sao đọc sum của cả hai layout sai? Thiết kế shadow layout, verification và read authority trước/sau cutover.

### Bài tập 20 — Hot read path

64 buckets phục vụ 20.000 increments/s nhưng API tổng bị gọi 100.000 lần/s. Ước lượng số bucket reads/s nếu không cache, rồi thiết kế cached total/rollup với freshness SLO 5 giây.

### Bài tập 21 — Rate limiting

Global API limit 100 requests/phút. Một request được gán random vào 10 buckets và chỉ kiểm tra bucket được chọn. Vì sao không bảo vệ được hard limit? Đề xuất quota allocation/token bucket authority.

### Bài tập 22 — Tenant fairness

Một tenant lớn tạo 90% events trên shared worker pool. Hãy đề xuất fairness, quotas, separate queues/pools và metric không làm bùng cardinality hoặc lộ thông tin tenant.

### Bài tập 23 — Phản hồi partial

Một trong 32 buckets không đọc được. Thiết kế API response cho dashboard eventual và API exact, ghi rõ khi nào được phép trả partial total, khi nào phải lỗi.

### Bài tập 24 — Reconciliation

Ledger cho expected count 10.005, tổng buckets chỉ 10.003. Hãy nêu kế hoạch xác định missing events, late events, stale reads và duplicate corrections, rồi chọn cách rebuild/correct có audit.

### Bài tập 25 — Fault injection

Thiết kế test cố tình gây: crash sau increment trước ACK, failover, TTL dedup hết hạn, event replay, bucket count migration và rollup retry. Với mỗi lỗi, ghi expected invariant, bằng chứng kiểm chứng và recovery step.

### Bài tập 26 — Benchmark trước/sau

So sánh một counter và 16/32/64 buckets dưới cùng workload. Thiết kế benchmark gồm p95/p99, throttling, bucket skew, physical partition distribution, aggregate read cost, freshness và reconciliation drift.

### Bài tập 27 — Thiết kế hệ thống đầy đủ

Một mạng xã hội cần hiển thị lượt xem của 10 triệu videos, một số video có 80.000 view events/s; phần lớn API chỉ cần số lượt xem cập nhật trong 3 giây nhưng hệ thống phải có thể đối soát event. Đề xuất:

1. Nguồn event và logical eventId.
2. Hash/assignment và số buckets theo peak/benchmark.
3. Shard key/physical placement.
4. Cơ chế batch + idempotency.
5. Minute/hour/day/lifetime aggregation.
6. Redis/DynamoDB/MongoDB/Cassandra hoặc kiến trúc kết hợp phù hợp.
7. Read cache và freshness contract.
8. Đổi B khi một video bùng nổ.
9. Fault injection, metrics và reconciliation.

Không được trả lời “chỉ thêm Redis INCR” hoặc “chỉ tăng số nodes” mà bỏ qua **độ chính xác, ghi trùng và quyền sở hữu dữ liệu**.

---

**Kết luận:** Một **hot key** không nhất thiết cần lưu nhiều bytes; chỉ cần nhận quá nhiều read/write là đủ trở thành nút thắt. Đối với **counter có các delta cộng được**, tách một logical key thành **nhiều buckets** giúp chia tải ghi, nhưng chỉ hiệu quả khi **shard/partition placement thật sự phân tán**. Mỗi bucket cần cập nhật nguyên tử, trong khi toàn bộ hệ cần thêm **event identity, idempotency, cửa sổ thời gian, layout epoch, rollup và reconciliation** nếu muốn kết quả đáng tin khi retry, failover và thay đổi số bucket. Đọc tổng nhiều phần là một thao tác có **chi phí fan-out và giới hạn snapshot**, nên có thể cần cached total hoặc materialized rollups. Với **hard invariants** như tồn kho không âm, giới hạn quota hoặc một ghế chỉ có một chủ, không được thay cơ chế kiểm chứng quyền bằng một tổng eventual; hãy dùng **authoritative conditional write, escrow/quota hoặc transaction** phù hợp. Thiết kế tốt không chỉ chia tải ra nhiều khóa, mà còn chứng minh **mỗi hiệu ứng được ghi đúng số lần, tổng có ý nghĩa gì tại thời điểm đọc và hệ có thể phục hồi/đối soát khi xảy ra lỗi**.
