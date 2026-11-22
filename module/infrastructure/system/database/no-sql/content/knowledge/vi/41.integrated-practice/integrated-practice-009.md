# Đo tải trước/sau thay đổi chỉ mục hoặc cách tổ chức dữ liệu

Một truy vấn NoSQL đang chậm. Nhóm phát triển thêm một chỉ mục, chạy lại vài câu lệnh trên máy cá nhân và thấy thời gian giảm từ 500 ms còn 20 ms. Họ kết luận đã tối ưu thành công. Nhưng khi lên production, write p99 tăng, CPU và disk I/O cao hơn, chỉ mục ngốn thêm dung lượng, một nhóm tenant lớn vẫn bị nóng và các yêu cầu phân trang có thể trả dữ liệu sai thứ tự.

**Tối ưu NoSQL phải được chứng minh bằng phép đo có đối chứng.** Một chỉ mục mới có thể làm đọc nhanh hơn nhưng ghi đắt hơn; đổi partition key có thể phân tán tải nhưng bắt buộc fan-out khi đọc; nhúng dữ liệu vào document có thể giảm số round trip nhưng tăng kích thước bản ghi và nguy cơ lost update. Vì vậy không thể chỉ so một truy vấn riêng lẻ trước/sau rồi quyết định.

Bài học thuộc chương **Thực hành tổng hợp**, module **Database No SQL**. Mục tiêu là thiết kế và thực hiện một vòng đo tải trước/sau (baseline/treatment), quan sát query plan, độ trễ, throughput, tài nguyên, correctness, write amplification và chi phí; cuối cùng quyết định giữ, điều chỉnh hoặc hoàn tác thay đổi dựa trên dữ liệu có thể tái lập.

> **Quy tắc quan trọng:** So sánh **cùng kết quả nghiệp vụ, cùng phân phối dữ liệu, cùng tải và cùng mức nhất quán/durability**. Không tính một truy vấn nhanh hơn là thành công nếu tạo thêm lỗi, mất tính đúng đắn hoặc đẩy chi phí sang thao tác khác.

Các số liệu và cấu hình trong bài là ví dụ giả định. Cú pháp chỉ mục, thống kê truy vấn, consistency và cách tổ chức khóa khác nhau giữa MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và các hệ NoSQL khác. Khi thực hiện trên môi trường thật, cần xác minh với tài liệu engine/phiên bản/SDK và tuân thủ quy định bảo mật, giới hạn tải, rollback.

## 1. Kết quả học tập và sản phẩm đầu ra

Sau bài thực hành, người học có thể:

1. Xác định một truy vấn/chức năng đang gặp vấn đề và lập **giả thuyết tối ưu** có thể kiểm chứng.
2. Thiết kế hai cấu hình **Before** và **After** chỉ khác ở thay đổi cần thử nghiệm.
3. Sinh dữ liệu đại diện về kích thước, tenant, thời gian, độ lệch và vòng đời.
4. Tạo workload gồm read/write/update/delete, đồng thời và hot keys.
5. Đo latency p50/p95/p99, throughput, errors, bytes scanned, index/storage, CPU/I/O và retry count.
6. Xác minh query semantics, kết quả trả về và bất biến nghiệp vụ vẫn đúng.
7. Phân tích trade-off: read improvement vs write overhead, partition skew, index maintenance.
8. Đánh giá migration/index-build overhead, rollout risk và cách rollback.
9. Viết một báo cáo có bảng đo, assumptions, quyết định GO/NO-GO và next actions.

**Sản phẩm thực hành** gồm: mô tả workload, manifest dataset, cấu hình schema/index hai nhánh, log kết quả đo, bảng so sánh, data correctness report và decision record. Các mẫu trong bài giúp hình dung định dạng, không phải yêu cầu dùng công cụ cụ thể.

## 2. Đề bài xuyên suốt: xem lịch sử đơn hàng theo khách

Hệ thương mại điện tử có các thao tác chính:

- `CreateOrder`: tạo đơn, chứa `tenantId`, `customerId`, `createdAt`, trạng thái và số tiền.
- `ListOrdersByCustomer`: lấy 20 đơn mới nhất của một khách theo thời gian giảm dần.
- `GetOrderById`: đọc chi tiết đơn hàng.
- `UpdateOrderStatus`: cập nhật trạng thái đơn.
- `ReserveStock`: giữ hàng bằng conditional write trên một số SKU nóng.
- `DeleteExpiredOrders`: xóa/TTL theo chính sách lưu trữ.

Một document ví dụ:

~~~json
{
  "_id": "O-10001",
  "tenantId": "t-07",
  "customerId": "c-891",
  "createdAt": "2026-11-14T08:00:00.000Z",
  "status": "CONFIRMED",
  "totalMinor": 285000,
  "itemCount": 3,
  "version": 12
}
~~~

**Điều kiện cần giữ:** Một API lấy lịch sử của khách t-07/c-891 phải lọc đúng tenant, đúng customer; sắp xếp thời gian giảm dần, có tie-breaker ổn định theo ID; phân trang không lộ dữ liệu khách khác và không vi phạm API read consistency đã cam kết.

Mục tiêu thử nghiệm là xem **thêm chỉ mục ghép** hoặc **đổi mô hình lưu theo access pattern** giúp gì và phải trả giá ở đâu.

## 3. Tách rõ hai loại thay đổi

| Loại | Ví dụ | Điều phải đo |
|---|---|---|
| **Thay đổi chỉ mục** | Thêm index trên tenant, customer, time | Query plan, index size, read latency, write overhead |
| **Thay đổi tổ chức dữ liệu** | Tạo view/partition theo customer + time | Read fan-out, write fan-out, migration, consistency |
| Thay đổi partition key | Thêm bucket tháng hoặc salt | Hot partition, throughput, lookup scatter |
| Nhúng hoặc tách document | Embed OrderItems vào Order | Read round trips, update contention, document growth |
| Tạo materialized projection | OrdersByCustomer riêng | Projection freshness, CDC/backfill, storage |
| Đổi TTL/retention | Giữ ít lịch sử hơn | Data size, correctness, compliance |
| Đổi consistency level | Strong → eventual | Không phải tối ưu tương đương nếu contract khác |

Không được gộp đồng thời **thêm index + đổi data model + tăng nodes + chuyển strong read sang eventual** rồi tuyên bố chỉ mục đã giúp p99 giảm. Nếu muốn thử nhiều thay đổi, dùng **các nhánh hoặc giai đoạn thí nghiệm tách biệt** để phân biệt tác động.

## 4. Viết giả thuyết có thể bác bỏ

Giả thuyết:

> “Với 30 triệu Order, trong đó 75% lượt đọc tập trung vào dữ liệu 30 ngày gần nhất và 20% khách tạo 80% truy vấn, index ghép `tenantId, customerId, createdAt DESC, _id DESC` sẽ giảm p99 của `ListOrdersByCustomer` từ trên 250 ms xuống dưới 100 ms tại peak 1.200 requests/s, trong khi p99 của `CreateOrder` không tăng quá 15% và storage/index tổng tăng không quá 25%.”

Cần định nghĩa rõ:

- **Đầu vào:** dataset, skew, version engine, topology.
- **Biến độc lập:** chỉ mục B so với A.
- **Biến phụ thuộc:** p99 read/write, bytes, CPU, index size, error rate.
- **Điều kiện đo:** warm-up, concurrency, query mix, duration.
- **Hard gates:** không missing/lộ Orders, không duplicate intents.
- **Quyết định:** PASS, FAIL hoặc INCONCLUSIVE với lý do.

Một kết luận “index nhanh hơn” không phải giả thuyết đủ tốt vì không nêu **ở tải nào, với dữ liệu nào và giá phải trả là gì**.

## 5. Chọn baseline và treatment

Mô hình:

~~~mermaid
flowchart TD
    D["Dataset manifest + fixed seed"] --> A["Environment A: Before"]
    D --> B["Environment B: After"]
    W["Same workload profiles"] --> A
    W --> B
    A --> M["Measurements + business oracle"]
    B --> M
    M --> C["Paired comparison and decision"]
~~~

Có hai cách tổ chức:

1. **Hai cụm/môi trường riêng**: chạy A/B trên cùng dataset, cấu hình được chuẩn hóa; tốt cho isolation nhưng phải quản lý cloud noise.
2. **Một cụm chạy tuần tự**: đo Before, thay đổi index/schema, reset seed/state theo thiết kế, đo After; tiết kiệm tài nguyên nhưng chịu time-order effects, warm cache và index build/compaction.

Khi không thể chạy hai môi trường ngang nhau, phải ghi rõ những yếu tố có thể gây thiên lệch và **lặp lại thí nghiệm**. Không dùng production traffic làm treatment không kiểm soát chỉ vì có đủ user requests.

## 6. Điều kiện giữ nguyên giữa hai nhánh

| Yếu tố | Quy tắc |
|---|---|
| Logical data | Cùng records, relationships, cardinality, tombstones |
| Data distribution | Cùng hot tenants, key skew, time locality |
| API contract | Cùng kết quả, filtering, ordering, auth |
| Consistency/durability | Cùng mức yêu cầu cho từng operation |
| Logical workload | Cùng mix, arrival schedule, hot keys, payloads |
| Infra budget | Cùng class hoặc so thêm cost-to-SLO |
| Replication/topology | Cùng failure-domain guarantees |
| Cache policy | Cold vs warm được tách và ghi |
| SDK | Phiên bản, retries, timeouts, connection pools tương ứng |
| Security | TLS/auth/encryption và tenant isolation |
| Background work | Backup, CDC, compaction được điều phối/ghi lại |
| Measurement | Cùng công cụ, clock model, sampling và cửa sổ |
| Test correctness | Cùng expected results và business invariants |

**Không khóa chết thiết kế schema giống nhau cho hai NoSQL engines khác mô hình** nếu đang đo thay đổi tổ chức dữ liệu. Hãy giữ **logical behavior** giống nhau, cho phép physical representation khác và tính đúng chi phí chuyển đổi.

## 7. Phân biệt so cùng tài nguyên và so cùng ngân sách

Một cách đo:

- **Fixed hardware:** A và B có cùng CPU, RAM, storage class, topology; xem thay đổi làm thay đổi hiệu quả thế nào.
- **Fixed SLO:** cho phép B cần ít hoặc nhiều nodes hơn để đạt cùng throughput, latency và durability; xem chi phí tối thiểu của từng cấu hình.

Trong bài này, giai đoạn đầu nên cố định resources để xác định tác dụng của chỉ mục. Sau đó, nếu phương án B cần nhiều disk/index hoặc memory hơn, chạy thêm **cost-to-SLO** để đánh giá lợi ích tổng thể.

Có thể tăng throughput sau thêm index vì node trống CPU hơn. Nhưng nếu dataset trở nên lớn đến mức index không còn nằm trong RAM, lợi ích có thể thay đổi. Cần thử sensitivity, không ngoại suy tùy tiện.

## 8. Dữ liệu đại diện cần có gì?

Dataset minh họa:

~~~yaml
dataset:
  seed: 5872026
  tenants: 300
  customers: 500000
  orders: 30000000
  avgOrderItems: 3.1
  orderSize:
    p50Bytes: 900
    p95Bytes: 3400
    p99Bytes: 12000
  tenantSkew:
    largestTenantWriteShare: 0.28
  customerReadSkew:
    topTwentyPercentShare: 0.80
  recency:
    readsWithinThirtyDays: 0.75
  lifecycle:
    statusUpdatesPerOrderAvg: 2.4
    includeSoftDeletes: true
    includeTtlExpired: true
  noRealPersonalData: true
~~~

Số liệu giả định; cần profile theo sản phẩm thực tế. Nếu bộ test chỉ có 100.000 Orders đồng kích thước và uniform keys, nó có thể nằm trọn trong cache và che cả index scan lẫn hot partitions.

## 9. Sinh dữ liệu cần giữ tính nhân quả

Dữ liệu test phải hợp lệ:

- `tenantId` thuộc danh sách tenants.
- Mỗi customer thuộc một tenant.
- Order gắn đúng customer/tenant.
- Total = tổng OrderItems theo fixed-point money units.
- Status nằm trong state machine hợp lệ.
- Version tăng khi update.
- Thời gian có order/causal constraints phù hợp.
- Delete/TTL không làm records “hồi sinh” sai.

Một dataset cùng kích thước mà các quan hệ không đúng có thể làm truy vấn theo tenant/customer trả gần như rỗng, khiến p99 đẹp giả. Phải kiểm **phân phối truy vấn hợp lệ và hit ratio**.

## 10. Độ lệch khóa có thể quyết định kết quả

Thử ít nhất:

1. **Uniform key traffic** làm baseline.
2. **Skewed customer reads**: top 20% customers nhận 80% reads.
3. **Hot tenant writes**: một tenant chiếm 28% writes.
4. **Recent-key locality**: 75% reads nhắm Orders 30 ngày gần nhất.
5. **Hot SKU contention**: nhiều conditional reservations cùng một key.
6. **Cold history reads**: truy vấn vài năm về trước.

Một index ghép có thể giúp range reads nhưng vẫn không giải quyết hot write item; một bucket theo tháng có thể giảm partition size nhưng tăng read fan-out khi khách lọc nhiều tháng. Vì vậy **không dùng một con số aggregate QPS thay cho performance theo nhóm key/tenant**.

## 11. Tạo danh mục thao tác cần đo

Một bảng đo đáng tin bắt đầu từ **logical operations**, không từ từng command của database.

| Operation | Normal mix | Peak mix | SLO minh họa | Đường dữ liệu |
|---|---:|---:|---|---|
| `ListOrdersByCustomer` | 25% | 28% | p99 ≤ 100 ms | Index/range read |
| `GetOrderById` | 25% | 20% | p99 ≤ 70 ms | Point lookup |
| `CreateOrder` | 20% | 20% | p99 ≤ 230 ms | Insert + indexes |
| `UpdateOrderStatus` | 15% | 12% | p99 ≤ 180 ms | Update + indexed fields |
| `ReserveStock` | 10% | 15% | p99 ≤ 180 ms | Conditional write |
| `Delete/TTL` | 5% | 5% | Background budget | Delete/index maintenance |
| **Tổng** | **100%** | **100%** | | |

Nếu chỉ đo `ListOrdersByCustomer`, phương án có chỉ mục mới có thể “thắng” rõ rệt nhưng thực tế làm 40–50% các thao tác ghi chậm hơn. **Workload mix phải phản ánh toàn hệ thống**, đồng thời có một bộ microbenchmark riêng để cô lập truy vấn mục tiêu.

### 11.1. Tải cần nối các thao tác với nhau

Một user journey có thể là:

~~~text
CreateOrder(K1)
  -> GET Order(K1)
  -> ListOrdersByCustomer(customer)
  -> UpdateOrderStatus(K1)
  -> ListOrdersByCustomer(customer) again
~~~

Sau khi CreateOrder trả thành công, ListOrders có thể cần nhìn thấy Order mới theo contract. Nếu After sử dụng một read projection bất đồng bộ, phải tính lag và các false misses, không chỉ lấy p99 thấp.

## 12. Query shape phải giống production

Ví dụ truy vấn logic:

~~~text
LIST orders
WHERE tenantId = :tenant
  AND customerId = :customer
  AND (createdAt, orderId) < (:cursorTime, :cursorId)
ORDER BY createdAt DESC, orderId DESC
LIMIT 20
~~~

Đây là ký pháp **khái niệm**, không phải SQL chạy được trên mọi NoSQL engine. Test phải giữ:

- Tenant/customer filter đầy đủ.
- Sort hai trường để các records có timestamp bằng nhau vẫn ổn định.
- Page size và projection giống production.
- Cursor semantics khi concurrent writes/deletes.
- Số pages mỗi session tương đối thực tế (ví dụ 1–5).
- Các customers có số Orders rất khác nhau.
- Hit/miss ratio thực tế; queries không trả dữ liệu không nên chiếm gần hết mẫu.

Không thay `LIMIT 20` thành `LIMIT 1` trong After hoặc bỏ field khỏi output mà không thay hợp đồng; một query nhanh nhờ trả ít dữ liệu **không tương đương**.

## 13. Thiết kế tải theo thời gian

Lịch giả định:

~~~text
Phase 0 (5 min):  start service, load data and verify readiness
Phase 1 (8 min):  warm-up, 30% peak offered load
Phase 2 (15 min): normal traffic, 60% peak
Phase 3 (20 min): steady peak, 100% peak
Phase 4 (5 min):  burst at 200% peak
Phase 5 (15 min): recovery to 100% peak
Phase 6 (30 min): soak at 70% with updates/deletes
~~~

Cần định nghĩa:

- **Offered QPS:** load generator lên lịch bao nhiêu logical requests.
- **Completed QPS:** số logical requests hoàn tất, bao gồm success/failure classification.
- **Concurrency:** số requests đang xử lý hoặc chờ.
- **Queue time:** chờ pool/thread/socket/server.
- **Retry attempts:** số physical operations trên một logical intent.
- **Deadlines:** timeout tổng và thời gian chờ mỗi attempt.

Phải ghi source CPU/concurrency của load generator để bảo đảm **generator không thành bottleneck**. Tải burst/soak chỉ thử trong môi trường được phép, giới hạn độ lớn và có stop conditions.

## 14. Open-loop, closed-loop và coordinated omission

**Closed-loop:** mỗi virtual user gửi request, đợi kết quả rồi gửi tiếp. Khi DB chậm, generator gửi ít hơn, có thể che phần tải thiếu phục vụ.

**Open-loop:** request được lên lịch theo tốc độ đến độc lập với response, nhưng có bounded queue và safety limits. Nó phản ánh backlog khi hệ gần saturation.

~~~text
Closed-loop:
  user sends -> waits for response -> next request
  slow DB -> offered traffic falls

Open-loop:
  schedule 1200 arrivals/s
  slow DB -> queue/errors/latency rise
~~~

Một phép đo **coordinated omission** xảy ra khi các khoảng gián đoạn dài không tạo samples tương xứng do client không gửi tiếp. Để tránh báo p99 quá đẹp, ghi **scheduled arrival time**, thực tế start/finish, timeouts và offered-vs-completed traffic.

Có thể dùng cả hai loại để trả lời hai câu hỏi khác nhau. Không trộn kết quả rồi gọi chúng là một p99 duy nhất.

## 15. Đơn vị đo: client, query và business journey

Ba tầng latency:

1. **Client end-to-end:** từ khi request được lên lịch/được gọi cho đến success/error/timeout, gồm queue/pool/network.
2. **DB operation:** thời gian driver/server thực hiện một command, gồm retry nếu policy quy định.
3. **Business journey:** toàn chuỗi `CreateOrder → read → update → read`, có thể gồm nhiều requests/hệ.

Một index có thể làm DB query từ 100 ms xuống 15 ms, nhưng API end-to-end chỉ giảm 5 ms nếu phần lớn thời gian nằm ở serialization/authorization/network. Ngược lại, DB query trung bình nhanh nhưng p99 API vẫn tăng do pool wait.

Do vậy số liệu nên gắn với **cùng nhãn**: operation, tenant group, hot/cold, run ID, phase, candidate và version.

## 16. Các metric bắt buộc ở tầng client

| Metric | Giải thích |
|---|---|
| Offered logical ops/s | Tải dự định gửi |
| Completed valid ops/s | Business requests hoàn tất đúng |
| p50/p95/p99 latency | Theo từng operation và phase |
| Timeout/error rate | Không loại khỏi kết luận p99 |
| Retries per intent | Khuếch đại tải thật |
| Success/rejected/unknown | Phân biệt business rejection với lỗi mạng |
| Client queue wait | Load generator, thread, pool |
| Payload size | Bytes serialize/deserialize |
| Cursor pages/session | Fan-out và memory |
| Read-your-writes failures | Tính nhất quán/API correctness |
| Tenant-level p99 | Noisy neighbor và skew |
| CPU/GC của API | Phần overhead ngoài database |

**Không gộp p99 của GetOrder 2 ms với reporting 2 s thành một chỉ số tổng**; giữ SLO/độ trễ theo thao tác.

## 17. Metric ở tầng database và hệ thống

Đo khi có thể:

- Query plan, index sử dụng, số keys/docs scanned và returned.
- Read/write units, request cost, scans/bytes transferred.
- Cache hit/miss, disk read/write IOPS, storage latency.
- Index size, index count, data size, storage growth.
- WAL/commitlog/oplog activity, compaction/GC.
- CPU, memory, disk headroom và network bandwidth.
- Replication lag, quorum/member health.
- Hot partition, throttled/failed requests.
- Connection count, pool queue, server selection.
- Secondary index update/backfill progress.
- CDC/outbox lag khi có data projection.
- TTL/tombstone cleanup và long-running cursor resource cost.

Một query plan báo “index used” chưa đủ; nó vẫn có thể scan quá nhiều keys, fetch quá nhiều documents hoặc gây fan-out. Cần nhìn **scanned/returned ratio, server resource và end-to-end latency**.

## 18. Trước khi đo: chuẩn hóa môi trường và trạng thái

Quy trình chuẩn bị:

1. Chọn engine/driver versions và region/AZ topology.
2. Provision storage class/IOPS và memory đã định.
3. Bật TLS/auth/replication/consistency như production contract.
4. Seed dữ liệu từ manifest cố định, cùng IDs/histograms.
5. Build các indexes đang thuộc baseline; đợi hoàn tất.
6. Đợi cụm khỏe, replicas caught up, compaction/index jobs không ở trạng thái ngoài kế hoạch.
7. Đặt read/write pool, retry/backoff/deadlines giống nhau.
8. Đo background metrics và idle resource consumption.
9. Reset business state hoặc dùng dataset clone trước mỗi paired run.
10. Ghi environment/config fingerprint và số records/bytes ở điểm bắt đầu.

Nếu After được đo sau khi cluster đã warm còn Before lúc cold, không thể gán hết chênh lệch cho index. Vì vậy hoặc **cố định cache state**, hoặc đo rõ cold/warm riêng.

## 19. Baseline Before: các hoạt động cụ thể

Với nhánh A:

1. Xác nhận cấu hình chưa có chỉ mục/representation mới.
2. Xác nhận số records, types, hot groups và query output semantics.
3. Ghi query plan của `ListOrdersByCustomer` và số scanned keys/docs.
4. Chạy smoke nhỏ cho mỗi operation để bảo đảm workflow hợp lệ.
5. Warm-up theo thời lượng đã định.
6. Chạy normal/peak/burst/soak với seed và logical schedule cố định.
7. Thu client latency, errors, throughput và system metrics.
8. Lưu accepted business intents và correctness oracle.
9. Chờ background work theo protocol; ghi log compaction/cache state.
10. Xuất một manifest cho run A (không chứa thông tin nhạy cảm).

Mục đích là có **bức tranh về chi phí truy vấn trước thay đổi**, không chỉ một con số p99. Nếu Before có query plan full scan, ghi đây là bottleneck dự kiến chứ không ngầm xem là benchmark công bằng giữa tất cả storage models.

## 20. Treatment After: thay đúng một phương án

Một thử nghiệm chỉ mục:

- Giữ cùng base records.
- Thêm compound index đã thiết kế.
- Đợi index build hoàn tất và mọi replica có trạng thái cần thiết.
- Không tăng nodes/IOPS trong cùng phép so fixed-resource.
- Không thay result projection, page size hoặc consistency.
- Ghi index build time, index bytes, CPU/disk/network và ảnh hưởng tới write traffic.
- Warm-up tương ứng.
- Chạy cùng workload phases, seeds và correctness assertions.
- Thu metrics cùng cách.
- Chạy lặp để đánh giá độ biến thiên.

Nếu muốn thử thêm data layout change, tạo **nhánh C** hoặc vòng thử riêng với snapshot/seed và đầy đủ migration costs. **Không gọi A→B là chỉ “thêm index” nếu phía B đồng thời dùng denormalized data view và nhiều nodes hơn.**

## 21. Ví dụ thực hành MongoDB: truy vấn trước khi thêm chỉ mục

Giả sử collection `orders` đã có primary index trên `_id`, nhưng chưa có index phù hợp với list orders của một customer.

Truy vấn cơ bản:

~~~javascript
const filter = {
  tenantId: "t-07",
  customerId: "c-891"
};

db.orders
  .find(filter, {
    _id: 1,
    createdAt: 1,
    status: 1,
    totalMinor: 1
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Trong môi trường test, có thể xem execution plan:

~~~javascript
db.orders
  .find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Một số trường cần quan sát tùy version/plan shape:

- Winning plan có dùng collection scan hay index scan.
- `totalDocsExamined`, `totalKeysExamined`.
- `nReturned`.
- Sort có yêu cầu in-memory sort hay không.
- Các stages FETCH, IXSCAN, SORT và execution time theo phương pháp công cụ cung cấp.
- Execution stats có đại diện cho end-to-end API p99 không? **Không**, vì explain không thay client load test.

Trên dataset nhỏ, collection scan có thể vẫn nhanh; trên 30 triệu records và nhiều concurrent queries, scan có thể tiêu CPU/I/O lớn. Không dùng kết quả từ `explain` của một query duy nhất làm tất cả benchmark evidence.

## 22. Thêm chỉ mục ghép đúng access pattern

Một compound index minh họa:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "orders_tenant_customer_recent"
  }
);
~~~

Thứ tự trường phản ánh equality filters trước, sort/range sau; đây là chiến lược **cần kiểm theo query shape, index rules và engine version**, không phải công thức bất biến cho mọi truy vấn.

Đo lại:

~~~javascript
db.orders
  .find({
    tenantId: "t-07",
    customerId: "c-891"
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Cần tìm bằng chứng index phù hợp được dùng, số keys/docs examined giảm hợp lý và sort không còn phải xử lý nhiều data ngoài index. Đồng thời đo:

- Index size tăng bao nhiêu?
- Thời gian build index trên dataset đầy đủ?
- CPU/disk/replica lag khi build?
- P99 `CreateOrder` có tăng vì phải update index?
- Query selectivity giữa customer có 5 Order và customer có 50.000 Order?
- Cache của index có chiếm chỗ data khác?
- Khi thêm index vào production, rollout/rollback sẽ được thực hiện thế nào?

Không cố ép `hint` trong production nếu chưa chứng minh query planner thực sự cần; khi thí nghiệm, dùng hint có kiểm soát để phân lập index choice nhưng **ghi rõ khác behavior mặc định**.

## 23. Phân trang ổn định với cursor

Nếu nhiều Order có cùng `createdAt`, chỉ sort theo thời gian có thể trả thứ tự không ổn định. Cursor có thể dùng cặp `(createdAt, _id)`:

~~~javascript
const cursorTime = new Date("2026-11-13T23:30:00.000Z");
const cursorId = "O-09000";

db.orders
  .find({
    tenantId: "t-07",
    customerId: "c-891",
    $or: [
      { createdAt: { $lt: cursorTime } },
      { createdAt: cursorTime, _id: { $lt: cursorId } }
    ]
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Thực hành cần tạo dữ liệu có timestamp trùng, inserts/deletes đồng thời và paging qua nhiều pages để kiểm:

1. Không lộ tenant khác.
2. Không bỏ hoặc lặp các records **trong snapshot semantics đã chọn**.
3. Cursor hợp lệ khi read target/replica thay đổi.
4. Compound index vẫn có plan tốt với điều kiện `$or` và boundary.
5. Keyset pagination có latency ổn định khi page sâu hơn so với skip/offset.

**Keyset pagination không tự tạo một snapshot bất biến.** Khi records mới được thêm hoặc sửa sort key, cách nhìn dữ liệu giữa các pages phụ thuộc snapshot/read consistency của ứng dụng. Chỉ số p99 không thay được correctness test này.

## 24. Đo write amplification do index

Một insert ban đầu có thể ghi:

~~~text
Before:
  base Order record
  primary key index

After:
  base Order record
  primary key index
  new compound secondary index
~~~

Nếu update `status` nhưng index mới không chứa status, nó vẫn có thể có chi phí khác với update key field; nếu update `customerId` hoặc `createdAt`, index entry có thể cần thay đổi. Cách storage engine triển khai khác nhau, nên phải đo **theo loại update thật**.

Các phép đo:

- p50/p95/p99 của CreateOrder, UpdateOrderStatus và Delete.
- Disk bytes written/compaction work.
- Index size, cache/working set growth.
- CPU và I/O ở steady peak.
- Replication lag/write commit latency.
- GC, long transactions hoặc lock/contention.
- Index maintenance cost khi có TTL/deletes.
- Chi phí backup/restore vì index và metadata lớn hơn.

Một chỉ mục giúp đọc giảm từ 250 ms xuống 50 ms nhưng làm ghi p99 tăng từ 100 lên 240 ms có thể **không đạt** nếu CreateOrder SLO là 200 ms. Xem cả operation mix và hard gates.

## 25. Chỉ mục thừa và mục đích của từng chỉ mục

Nhiều index có overlap:

~~~text
Index A: tenantId, customerId
Index B: tenantId, customerId, createdAt DESC, _id DESC
Index C: status
Index D: tenantId, status, createdAt DESC
~~~

Không nên mặc định xóa A khi thêm B dù index prefix có vẻ được bao phủ: phải xem tính năng/uniqueness/sparse/partial/collation, các queries khác và planner semantics. PoC cần lập **index inventory**:

| Index | Query được phục vụ | Kích thước | Write cost | Quyết định |
|---|---|---|---|---|
| Primary ID | GetOrder | Baseline | Required | Giữ |
| Tenant/customer | Customer lookup | Đo | Đo | Xem có redundancy |
| Tenant/customer/time | Recent order list | Đo | Đo | Candidate |
| Status index | Admin status report | Đo | Đo | Theo workload |
| TTL index | Retention policy | Đo | Background | Giữ theo compliance |

Một chỉ mục không được query planner chọn trong vài phút test **không chứng minh vô dụng**: có thể phục vụ background jobs, rare endpoints hoặc constraints. Data-driven cleanup phải xem full query inventory và lịch sử thực tế phù hợp.

## 26. Index build trong khi hệ còn ghi

Trên production, tạo index lớn có thể:

- Tăng đọc/ghi disk và CPU.
- Tăng replication lag.
- Tiêu disk tạm/metadata/index memory.
- Làm các truy vấn p99 xấu do tranh tài nguyên.
- Gặp lỗi khi thiếu disk hoặc schema/collation không phù hợp.
- Có trạng thái build/background khác tùy engine/version.
- Cần repair/retry sau node failover.
- Làm tăng chi phí backup/replication.

Vì vậy PoC có hai phép đo riêng:

**A. Steady-state comparison:** Index đã hoàn thành, chỉ đo vận hành bình thường.

**B. Rollout/build impact:** Tạo index khi foreground workload vẫn chạy ở 50–100% peak theo phạm vi an toàn; đo p99, errors, disk, build duration và recovery nếu build bị gián đoạn.

Một index chạy tốt **sau khi tạo xong** chưa đủ cơ sở để triển khai nếu quá trình xây nó làm ứng dụng ngừng phục vụ hoặc vượt giới hạn dung lượng.

## 27. Thử partial/sparse/covering index có điều kiện

Một số engine hỗ trợ:

- **Partial index:** chỉ lập chỉ mục cho subset documents có predicate phù hợp.
- **Sparse index:** bỏ các documents không có field theo quy tắc engine.
- **Covering index:** đủ fields để đáp ứng một query mà giảm fetch record.
- **Multikey index:** index field trong array, có các giới hạn riêng.
- **TTL index:** áp retention, thường mang semantics/cleanup khác query index.

Một phương án partial index cho `status=CONFIRMED` có thể làm đọc nhóm này nhanh hơn và giảm index size, nhưng query lấy **mọi statuses** không được chỉ nhìn partial index nếu thiếu records. Query planner có thể chỉ dùng index khi predicate khớp điều kiện.

Thực hành:

1. Viết predicate và shape query nào hợp lệ với index.
2. Sinh records có field missing/null, enum và expired states.
3. So index bytes, keys examined, write overhead.
4. Kiểm wrong-results risk do query shape hoặc manual hints.
5. Xem portability giữa các engines nếu đang lựa chọn công nghệ.

**Tối ưu index mà đánh đổi mất records hợp lệ là lỗi correctness, không phải giảm latency.**

## 28. Thay cách tổ chức dữ liệu: view theo khách hàng

Nếu source Orders không phục vụ tốt customer time-range query, một ứng viên là materialized read model:

~~~text
Authoritative:
  OrdersById/{orderId} -> full Order state

Read projection:
  OrdersByCustomer/{tenantId}/{customerId}/
    {reverseTime}/{orderId} -> Order summary
~~~

Đọc lịch sử khách có thể truy cập một logical partition/range thay vì lọc một collection lớn. Nhưng khi tạo hoặc cập nhật Order:

- Source write tới `OrdersById`.
- Projection write tới `OrdersByCustomer`.
- Nếu customer/status thay đổi, có delete/insert entry.
- Outbox/CDC hoặc transaction phải phối hợp.
- Delete/TTL phải truyền sang cả hai nơi.
- Projection phải quản lý version/ordering và duplicate events.

Đây không còn chỉ là **thay index** mà là **thay physical data model**. Benchmark Before/After phải đo cả projection write fan-out, lag, storage và độ phức tạp vận hành.

## 29. Cùng dữ liệu logic, khác representations

Ví dụ hai phương án:

| Đặc điểm | A: Orders collection | B: OrdersByCustomer projection |
|---|---|---|
| Nguồn ghi có thẩm quyền | Orders | Orders |
| GetOrderById | Point lookup | Giữ OrdersById |
| ListOrdersByCustomer | Query + compound index | Partition/range read |
| CreateOrder | Single source + index maintenance | Source + outbox + async projection |
| UpdateOrder | Index maintenance | CDC/update projection |
| Read-your-writes | Theo source read contract | Cần watermark/route/fallback |
| Delete/TTL | Theo index và source | Propagate tombstone đến projection |
| Storage | Data + indexes | Data + projections + log |
| Failure modes | DB/index | DB + CDC + consumer + lag |

Đề bài đo tải phải đặt **cùng business behavior**: nếu A trả Order mới ngay nhưng B có thể chậm 3 giây, không thể so thuần p99 mà bỏ **freshness constraint**.

## 30. Thiết kế partition và time buckets

Một khách có hàng triệu Orders có thể tạo một partition quá lớn ở một số wide-column/data models. Tách bucket theo tháng:

~~~text
Partition key:
  tenantId + customerId + yearMonth

Clustering/order key:
  createdAt DESC + orderId DESC
~~~

Ưu điểm có thể là giới hạn kích thước mỗi partition, phân phối dữ liệu lịch sử và giới hạn scan. Chi phí:

- Query last 20 Orders có thể phải nhìn tháng hiện tại và tháng trước.
- Range nhiều năm cần nhiều buckets.
- Query fan-out và merge top-K ở app.
- Chuyển bucket boundary, DST/timezone và late-arriving events.
- Retention/drop theo bucket cần tuân chính sách.
- Hot current-month bucket vẫn có thể nóng.
- Shard salt thêm read fan-out nếu không biết route.

Đo ít nhất: **recent-only queries, cross-month queries, deep history queries, writes trên hot month và TTL/deletes**. Không dùng số liệu một month bucket rất ít records rồi suy “partitioning đã giải quyết mọi vấn đề”.

## 31. DynamoDB: thử GSI và mô hình khóa truy vấn

Trong DynamoDB, cách tổ chức `PK`/`SK` và các secondary indexes quyết định request có thể dùng key condition hay phải scan. Nếu ứng dụng lấy Orders theo customer/time mà base table được đánh theo Order ID, có thể xem xét **GSI** với:

~~~text
Base table:
  PK = ORDER#<orderId>
  SK = META

GSI "OrdersByCustomer":
  GSI_PK = TENANT#<tenantId>#CUSTOMER#<customerId>
  GSI_SK = <createdAt>#<orderId>
~~~

Đây là **mô hình minh họa**, cần kiểm expression/encoding, sort order, projection type, limits, sparse-index behavior và SDK theo phiên bản đang dùng.

Các chỉ số:

- Query latency/RCUs so với Scan trên dữ liệu đại diện.
- Index storage và write capacity/WCUs cho GSI.
- GSI update propagation lag.
- Throttling/hot partition trên GSI key.
- Query result correctness, trường projected nào có/không.
- Pagination với `LastEvaluatedKey` theo semantics dịch vụ.
- Backfill GSI trên table đang ghi, thời gian và resource pressure.
- Cost của truy vấn theo key vs scans và retry.

**Lưu ý consistency:** không tự cho rằng GSI có cùng khả năng strongly consistent read với base table. Nếu read-your-writes là hard gate, cần route/thiết kế thích hợp hoặc chọn data model khác, rồi tính chi phí vào PoC.

### 31.1. GSI không tự giải hot business key

Thêm GSI cho `customerId` có thể tăng hiệu quả customer list, nhưng một SKU chỉ có một item giữ stock có thể vẫn là hot key; việc dàn customer keys không giải bottleneck của conditional stock update. Thử riêng **read access-path** và **hot-write contention**.

## 32. Cassandra/ScyllaDB: partition key và clustering columns

Trong wide-column models, tổ chức theo partition key và clustering order có thể quyết định phần lớn chi phí truy vấn.

Một schema CQL minh họa:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    bucket_ym text,
    created_at timestamp,
    order_id text,
    status text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, bucket_ym),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Mục đích là truy vấn một `tenant/customer/month` với thứ tự có ích. Đây không thay thế phần kiểm tra schema type, duplicate timestamps, token distribution, partition size và app merge logic.

**Before:** một mô hình khóa không hỗ trợ yêu cầu ListOrders hiệu quả.  
**After:** tổ chức dữ liệu đúng query shape, ví dụ như bảng trên.

PoC cần đo:

- Read cost/latency theo một partition và nhiều buckets.
- Partition size/distribution, hot current bucket.
- Write rate và compaction/tombstone overhead.
- Consistency level đang dùng, replica health và coordinator load.
- Query cần `ALLOW FILTERING` có thể là dấu hiệu không phù hợp, không phải giải pháp scale mặc định.
- Secondary-index/SAI/materialized view features nếu ứng viên hỗ trợ, theo version.
- TTL và delete behavior trong long soak.
- Schema migration/dual-write hoặc CDC để xây lại view.

**Không suy semantics Cassandra và ScyllaDB giống hoàn toàn chỉ vì cùng ngôn ngữ CQL.** Kiểm công cụ/index feature và write/read behavior theo sản phẩm/phiên bản.

## 33. Redis: secondary structures do ứng dụng tự quản lý

Redis thường mạnh ở key-based access. Nếu cần danh sách Orders theo customer, có thể lưu:

~~~text
order:<orderId> -> hash/document representation
customerOrders:<tenantId>:<customerId> -> sorted set by time
~~~

Một read có thể dùng sorted set để lấy IDs rồi truy xuất chi tiết. Nhưng cần:

- Hai structures có được cập nhật atomic đủ cho nghiệp vụ không?
- Dữ liệu source ở đâu, Redis là cache hay authoritative?
- Sorted set lớn/hot key, memory growth và eviction.
- TTL consistency giữa Order và index key.
- Duplicate member, tie-breaker và ordering.
- Persistence/replication/backup nếu Redis giữ state quan trọng.
- Cache invalidation/CDC và source DB pressure.
- Query p99 qua network round trips/pipelining.
- Cost RAM và write amplification.

Đừng so Sorted Set lookup đã có sẵn với một database query phải scan toàn bộ records rồi tuyên bố “Redis luôn tốt hơn”. Hãy tính **source-of-truth, maintenance và recovery** vào kiến trúc A/B.

## 34. Document embedding: đọc ít round trip hơn, ghi có thể đắt hơn

Một Order document có thể nhúng OrderItems:

~~~json
{
  "_id": "O1001",
  "tenantId": "t01",
  "customerId": "c17",
  "items": [
    {"sku": "SKU-A", "qty": 1, "priceMinor": 120000},
    {"sku": "SKU-B", "qty": 2, "priceMinor": 45000}
  ],
  "totalMinor": 210000,
  "status": "CONFIRMED"
}
~~~

So với tách `Orders` và `OrderItems`:

| Mặt | Embedded | Separate |
|---|---|---|
| Đọc một Order đầy đủ | Có thể một record | Có thể nhiều round trips |
| Cập nhật một item | Ghi một phần document nếu engine hỗ trợ | Ghi item riêng |
| Document growth | Có giới hạn kích thước và update cost | Dễ kiểm soát từng item |
| Cross-aggregate reuse | Dữ liệu có thể nhân bản | Reference theo quan hệ |
| Atomicity | Có thể tận dụng single-document atomicity | Có thể cần transaction/outbox |
| Query theo item | Có thể cần multikey index | Cần data model/index riêng |
| Hot Order | Contention vào cùng record | Có thể phân chia writes |

Thực hành phải tạo **Orders có 1, 10, 100 hoặc rất nhiều items** (theo business distribution) thay vì chỉ 2 items. Đo update amplification và document size limit, không chỉ một GET nhỏ.

## 35. Read-your-writes khi tổ chức dữ liệu thành projection

Giả sử source Order đã commit nhưng `OrdersByCustomer` cập nhật thông qua CDC:

~~~text
T0: Source CreateOrder ACK
T1: Client immediately calls ListOrdersByCustomer
T2: Projection update arrives after T1
~~~

Nếu list cần thấy Order vừa tạo, một read từ projection tại T1 có thể sai dù rất nhanh.

Có thể chọn:

- Keep this read on authoritative source.
- Dùng session/source version watermark và chờ projection catch up trong deadline.
- Route fallback có điều kiện khi version chưa đạt.
- Đổi API contract rõ ràng sang asynchronous/pending nếu business cho phép.
- Dùng transactionally maintained read structure nếu engine hỗ trợ và chi phí hợp lý.

Bộ đo cần ghi **freshness p50/p95/p99, false missing results, write-to-visible delay**, không chỉ query latency. Nếu cần đọc mạnh, **projection eventual chỉ phù hợp khi có cơ chế đáp ứng contract**.

## 36. Migration/backfill là một phần chi phí thay data model

Để chuyển từ Orders sang OrdersByCustomer, có thể cần:

~~~mermaid
flowchart LR
    A["Authoritative Orders"] --> B["Snapshot/backfill"]
    A --> C["CDC/outbox"]
    B --> D["OrdersByCustomer projection"]
    C --> D
    D --> E["Reconciliation"]
    E --> F["Shadow/canary reads"]
    F --> G["Read cutover"]
~~~

Bộ test phải kiểm:

- Snapshot cùng CDC handoff có gap/duplicate không.
- Backfill record version cũ có ghi đè event mới không.
- Update/delete/tombstone/TTL được replay thế nào.
- Mọi tenant/range được coverage đầy đủ không.
- CDC backlog/lag và log retention đủ không.
- Schema/index target được tạo xong trước live reads chưa.
- Cutover/rollback đọc trong ứng dụng như thế nào.
- Read access có chuyển từng tenant hay một lần.
- Background backfill có làm source foreground p99 xấu đi không.

**Một cấu trúc đọc tốt nhưng không có cách migrate an toàn từ hệ đang chạy có thể không khả thi** về thời gian, RPO hoặc rủi ro triển khai.

## 37. Java: biểu diễn workload bằng business intent

Ví dụ interface minh họa cho harness độc lập engine:

~~~java
import java.time.Instant;

public enum Operation {
    LIST_ORDERS,
    GET_ORDER,
    CREATE_ORDER,
    UPDATE_STATUS,
    RESERVE_STOCK,
    DELETE_EXPIRED
}

public record BusinessIntent(
    String operationId,
    String tenantId,
    String customerId,
    String targetId,
    Operation operation,
    long expectedVersion,
    Instant scheduledTime
) {}

public enum Outcome {
    ACKNOWLEDGED,
    BUSINESS_REJECTED,
    UNKNOWN,
    ERROR
}

public record Observation(
    String runId,
    String operationId,
    Operation operation,
    Outcome outcome,
    int physicalAttempts,
    long scheduledNanos,
    long startedNanos,
    long completedNanos,
    String errorCategory
) {}

public interface NoSqlScenarioAdapter {
    Observation execute(
        BusinessIntent intent,
        String runId
    ) throws Exception;
}

public interface CorrectnessOracle {
    void verifyAfterRun(
        Iterable<BusinessIntent> submittedIntents
    ) throws Exception;
}
~~~

Adapter A và B có thể chạy queries khác nhau, nhưng dùng **cùng logical intents và expected results**. `scheduledNanos`/`startedNanos`/`completedNanos` nên thuộc một clock monotonic khi đo duration trong cùng process; `Instant` hữu ích làm metadata lịch nhưng không dùng wall-clock nhiều hosts để đo nano-duration.

Đây không phải chương trình hoàn chỉnh: adapter, driver pools, arrival controller, metrics, fault cleanup và business oracle phải được hiện thực hóa theo môi trường.

## 38. Java: deterministic workload generator đơn giản

Một cách sinh phân phối có hot customers:

~~~java
import java.util.SplittableRandom;

public final class CustomerSampler {
    private final SplittableRandom random;
    private final int total;
    private final int hot;
    private final double probabilityHot;

    public CustomerSampler(long seed, int total,
                           int hot, double probabilityHot) {
        if (total <= 1 || hot <= 0 || hot >= total ||
            probabilityHot < 0.0 || probabilityHot > 1.0) {
            throw new IllegalArgumentException("Invalid profile");
        }
        this.random = new SplittableRandom(seed);
        this.total = total;
        this.hot = hot;
        this.probabilityHot = probabilityHot;
    }

    public String nextCustomer() {
        int index = random.nextDouble() < probabilityHot
            ? random.nextInt(hot)
            : hot + random.nextInt(total - hot);
        return "customer-" + index;
    }
}
~~~

Với `total=500000`, `hot=100000`, `probabilityHot=0.8`, 20% customers nhận khoảng 80% lookup events theo model hai nhóm. Đây **không phải Zipf chính xác**, chỉ là generator tái lập có skew. PoC thật cần giữ tenant ownership, customer Order counts, time recency và independent seeds cho nhiều runs.

### 38.1. Tránh tác động seed tới candidate

Giữ cùng ordered intents ở hai nhánh khi so paired runs. Tuy nhiên nếu chạy source cùng dataset rồi tạo updates, state sẽ khác sau mỗi run. Phải restore từ snapshot/seed hoặc chọn **immutable workload partition** có trạng thái khởi đầu giống nhau. Nếu dùng một synthetic workload trace replay, ghi trace version và privacy policy.

## 39. Java: ghi observation đầy đủ để tránh đo sai

Một record log có thể là:

~~~json
{
  "runId": "row587-after-r2",
  "scenario": "mixed-peak",
  "candidate": "After",
  "operationId": "intent-000082",
  "operation": "LIST_ORDERS",
  "tenantClass": "large",
  "scheduledAt": "2026-11-14T09:00:00.000Z",
  "startedAt": "2026-11-14T09:00:00.003Z",
  "finishedAt": "2026-11-14T09:00:00.088Z",
  "attempts": 1,
  "outcome": "ACKNOWLEDGED",
  "itemsReturned": 20,
  "bytesReturned": 4100
}
~~~

Ý nghĩa:

- Logical operation ID giữ qua retry.
- Latency có thể tính scheduled-to-finish và started-to-finish theo đồng hồ phù hợp.
- Số returned items phát hiện việc query nhanh vì thiếu records.
- Tenant class và operation để tách p99.
- Retry count để tính physical amplification.
- Timestamp/correlation cho driver/server tracing.
- Không log raw customer data/payment/PII.

Load generator phải lưu **errors, timeouts, unknown outcomes** bên cạnh success latency. Không coi request bị timeout là “không có observation”.

## 40. Oracle: so đúng nghiệp vụ trước khi so nhanh/chậm

Những assertions:

1. Mọi ListOrders lọc đúng `tenantId`/`customerId`.
2. Sort `createdAt DESC, orderId DESC` đúng.
3. Cùng snapshot, không duplicate/missing Orders qua pages.
4. Tổng OrderItems tương ứng Order `totalMinor`, nếu workflow bao gồm.
5. Mỗi idempotency key tạo tối đa một Order.
6. Conditional stock không oversell.
7. Những writes đã ACK vẫn tồn tại sau test/failover theo durability contract.
8. Delete/TTL không hồi sinh record qua backfill/CDC.
9. Với read model eventual, lag nằm trong freshness contract.
10. Không có cross-tenant access hoặc security regression.

Một candidate có `ListOrders` p99 12 ms nhưng trả sai 5% records **không phải phương án tốt hơn** candidate p99 70 ms trả đúng. Dữ liệu oracle cần có nguồn expected state độc lập, không chỉ so output giữa hai implementations vì cả hai có thể cùng sai.

## 41. Tính chênh lệch trước/sau đúng cách

Với một đại lượng đo theo cùng phương pháp:

\[
\Delta_\% =
\frac{x_{\mathrm{After}}-x_{\mathrm{Before}}}
{x_{\mathrm{Before}}}\times100\%.
\]

Khi đo latency/dung lượng, dấu âm thường nghĩa là giảm; khi đo valid throughput, dấu dương thường tốt. Tuy nhiên **phần trăm cải thiện không tự là tiêu chí PASS**:

- p99 giảm 50% nhưng errors tăng từ 0% lên 4% không phải cải thiện đúng.
- Read QPS tăng nhưng write SLO trượt là trade-off.
- CPU giảm nhưng disk writes/index bytes tăng lớn có thể làm TCO xấu.
- p50 giảm nhưng hot-tenant p99 tăng vẫn có thể vi phạm SLO.
- Baseline rất gần 0 làm % change lớn và ít ý nghĩa; nên ghi giá trị tuyệt đối.

Với duplicate business effects, tenant leakage hoặc acknowledged-write loss, đánh giá bằng **violation count và hard gate**, không trung bình vào score tốc độ.

## 42. Ví dụ kết quả A/B: index mới có thật sự đáng thêm?

Giả định hai nhánh dùng cùng seed, workload, tài nguyên và hợp đồng. **Số liệu dưới đây hoàn toàn giả định**, không phải benchmark một sản phẩm cụ thể.

| Metric | Before A | After B | Nhận xét |
|---|---:|---:|---|
| ListOrders p50 | 60 ms | 12 ms | Giảm nhiều |
| ListOrders p95 | 230 ms | 36 ms | Giảm nhiều |
| ListOrders p99 | 420 ms | 72 ms | Đạt mục tiêu ≤ 100 ms |
| ListOrders completed/s | 1.145 | 1.195 | Tăng nhẹ |
| ListOrders error rate | 0,4% | 0,2% | Cải thiện |
| CreateOrder p99 | 130 ms | 158 ms | Tăng khoảng 21,5% |
| UpdateOrderStatus p99 | 115 ms | 128 ms | Tăng |
| Peak CPU | 68% | 63% | Có thể giảm scans |
| Peak disk writes | 340 MiB/s | 420 MiB/s | Tăng index maintenance |
| Total index storage | 35 GiB | 45 GiB | Tăng khoảng 28,6% |
| Index build duration | — | 23 phút | Chi phí rollout |
| Critical invariant violations | 0 | 0 | Cả hai đúng theo oracle |
| Read-your-writes violations | 0 | 0 | Không thay contract |
| Restore rehearsal | 42 phút | 47 phút | Thêm index/restore overhead |

Nếu acceptance đặt **CreateOrder p99 không tăng quá 15%**, After B **không đạt toàn bộ tiêu chí** dù read p99 cải thiện rất mạnh.

Tính toán:

\[
\frac{158-130}{130}\times100\%\approx21{,}54\%.
\]

Với ListOrders:

\[
\frac{72-420}{420}\times100\%\approx-82{,}86\%.
\]

Read p99 giảm gần 83% không bù được một **write hard gate** đã vi phạm. Quyết định có thể NO-GO ở phương án này hoặc điều chỉnh giả thuyết rồi thử lại với chi phí rõ ràng.

## 43. Khi After không cải thiện như kỳ vọng

Nếu query plan dùng index nhưng p99 vẫn cao:

- Một nhóm hot keys vẫn bị contention.
- Index giảm scan nhưng FETCH documents lớn còn tốn I/O.
- Fan-out/cross-shard routing vẫn chi phối.
- Query predicate/sort/cursor không thực sự khớp index.
- Phần lớn latency nằm ở application/pool/network.
- Dataset quá nhỏ nên Before vốn đã cache-hit.
- Index mới đẩy data khác khỏi page cache.
- Compaction/GC hoặc lock waits tăng vì index maintenance.
- Filter ít chọn lọc, index scan gần tương đương full scan.

Cách tiếp:

1. Phân tách operation/tenant/hot vs cold, không chỉ aggregate p99.
2. So plans và scanned/returned ratio.
3. Phân rã latency bằng traces.
4. So CPU/disk/pool waits, replica lag/background tasks.
5. Kiểm lại kích thước working set và sự lệch phân phối.
6. Đề xuất hypothesis mới (covering index, bucket, projection).
7. Giới hạn thời gian tuning và lưu kết quả cũ.

Không thay đồng thời cả schema/index/topology rồi chỉ gán nguyên nhân cho index.

## 44. Lặp nhiều runs và báo độ không chắc chắn

Một p99 70 ms ở B và 80 ms ở A chưa chắc có ý nghĩa nếu cloud noise làm dao động ±20 ms. Nên:

- Chạy nhiều lần theo protocol, ví dụ 3–5 runs nếu ngân sách cho phép.
- Giữ seed, trace, duration, offered rate và mix nhất quán.
- Đổi thứ tự A→B/B→A nếu môi trường cho phép để tránh time-order bias.
- Ghi cache state, background jobs, config fingerprint.
- So per-run distributions/ranges, không chọn best run.
- Báo sample count, confidence/variation nếu có.
- Không lấy trung bình các p99 theo phút làm p99 global; cần hợp nhất samples/histograms theo đúng phương pháp.
- Ghi errors/timeouts/unknown song song với success-only percentiles.

Một kết quả nằm rất gần SLO cần **safety margin** và sensitivity test. Nếu mẫu ít hoặc nhiễu lớn, trạng thái **INCONCLUSIVE** thường đúng hơn việc ép chọn thắng/thua.

## 45. Kiểm sensitivity theo kích thước dữ liệu

Chạy nhiều mức:

~~~text
Dataset A:   0.5 million Orders
Dataset B:   5.0 million Orders
Dataset C:  15.0 million Orders
Dataset D:  30.0 million Orders
~~~

Giữ skew, time-locality và ratio hot working set/cache phù hợp. Đo p99 query, index size, disk I/O, build duration, write amplification và cold customer queries.

Sự tăng phi tuyến có thể đến từ cache cliff, hot partitions, compaction hoặc fan-out. **Không suy production p99 chỉ bằng phép nhân tuyến tính từ một microbenchmark nhỏ.**

## 46. So mức tải lớn nhất vẫn đạt SLO

Thay vì hỏi “DB đạt QPS tối đa bao nhiêu?”, cần định nghĩa:

> Mức offered load lớn nhất mà hệ giữ được mọi mandatory SLO và business correctness trong thời lượng đo đã chọn.

Một load staircase:

~~~text
25% peak  -> warm/stabilize/measure
50% peak  -> stabilize/measure
75% peak  -> stabilize/measure
100% peak -> stabilize/measure
125% peak -> measure if safety guardrails allow
150% peak -> measure if safe
~~~

Ở từng mức ghi **valid business completions**, p99 từng operation, errors, retries, queue wait, disk/CPU saturation và invariant violations. Nếu offered rate tăng nhưng completed throughput đứng yên và p99 tăng, hệ đã gần hoặc qua saturation.

Nếu After tốt ở 100% peak nhưng không còn headroom khi công ty dự kiến tăng lưu lượng 30% trong quý tới, phải xem lại capacity/cost thay vì chỉ ghi PASS ở hiện tại.

## 47. Tính chi phí theo một business journey

Một `CreateOrder` có thể thực hiện:

~~~text
1 conditional inventory write
1 authoritative Order write
1 outbox write
1 secondary index maintenance
1 customer projection update
1 search update event
~~~

Chi phí gần đúng:

\[
C_{\mathrm{journey}}=
\frac{C_{\mathrm{compute}}+C_{\mathrm{storage}}+
C_{\mathrm{IO}}+C_{\mathrm{network}}+
C_{\mathrm{backup}}+C_{\mathrm{operations}}}
{N_{\mathrm{valid\ business\ journeys}}}.
\]

Cần định nghĩa window, amortization, phân bổ fixed/shared cost và tránh đếm trùng. **Không coi retries/duplicates là sản lượng có ích**.

Một index mới có chi phí:

- Extra index bytes khi growth 1×, 3×, 10×.
- Write amplification insert/update/delete.
- Memory index chiếm, đẩy data khỏi cache.
- CPU/disk/network qua replicas.
- Index build và rollback/recovery.
- Extra backup/restore time.
- Có thể tiết kiệm read I/O/CPU vì giảm scans.

**Tính TCO ở cùng business SLO**, không chỉ cùng số physical DB requests/s.

## 48. Khi After dùng read projection, phải đo toàn bộ đường cập nhật

Sai lệch phổ biến:

~~~text
Before:
  ListOrders scans base Orders.

After:
  ListOrders reads prebuilt projection.
  (Benchmark ignores how projection was populated.)
~~~

Để so công bằng cần thêm:

1. Backfill duration/cost.
2. CDC/outbox lag và replay gap handling.
3. Source write + projection write fan-out.
4. Event duplicate/out-of-order updates.
5. Delete/TTL/tombstone propagation.
6. Rebuild projection từ scratch.
7. Cold/steady cache behavior.
8. Privacy/tenant filtering tại view.
9. Cutover/rollback read routing.
10. Restore/failover và consumer resumption.

Nếu Before strong read còn After eventual read thì chức năng không tương đương trừ khi business đã chấp thuận contract đổi. **Một projection nhanh nhưng stale vượt yêu cầu là FAIL**, không thể trừ điểm freshness rồi lấy average score che đi.

## 49. Thử index build bị gián đoạn trong rollout

Một thử nghiệm thuộc **transition cost**:

~~~text
1. Start mixed foreground traffic at controlled rate.
2. Begin supported index build.
3. Measure foreground p99/error, disk and replica lag.
4. Simulate a controlled maintenance interruption.
5. Observe index build progress/resume/rollback semantics.
6. Wait for index to reach usable state.
7. Verify query plan and record correctness.
8. Measure final headroom and cleanup.
~~~

Chỉ inject faults trên môi trường/phạm vi được cấp phép. Các engine có semantics khác nhau về index build, replica propagation và recovery.

**Một index chạy rất nhanh sau khi xây xong vẫn không thể triển khai an toàn** nếu quá trình build làm production cạn disk hoặc vượt error budget. Đặt GO/NO-GO riêng cho rollout/build.

## 50. Runtime benefit khác migration feasibility

Một thay đổi có các ngân sách:

| Nhóm | Chi phí cần tính |
|---|---|
| **Steady-state** | p99, throughput, CPU/I/O, storage, index maintenance |
| **Transition** | Backfill, CDC, index build, dual-read/dual-write protocol, warm-up |
| **Recovery** | Restore, failover, rollback/forward repair, schema compatibility |
| **Operations** | Alerts, monitoring, runbook, on-call, training |

Ví dụ projection cho p99 35 ms nhưng đòi 12 giờ backfill, trong khi business chỉ cho maintenance 10 phút. Nó **có thể** vẫn khả thi nếu có snapshot+CDC live migration, cutover không mất ACK và thời gian đóng write đủ ngắn; không thể kết luận chỉ bằng thời lượng backfill. Ngược lại, không có CDC/rollback thì lựa chọn rất rủi ro.

Bài thực hành phải có hai kết luận: **cải thiện lúc chạy** và **khả năng triển khai/chuyển đổi an toàn**.

## 51. Mẫu báo cáo A/B theo run và operation

~~~yaml
experiment:
  id: row587-index-order-history
  date: "2026-11-14"
  owner: backend-and-database
  scenario: mixed-peak-with-hot-tenants
  sourceOfExpectedResults: deterministic-test-ledger
  dataset:
    manifest: orders-30m-v1
    seed: 5872026
  topology:
    replicas: 3
    zones: 3
    tls: true
  contract:
    listOrdersP99Ms: 100
    createOrderMaxP99IncreasePercent: 15
    noDuplicateBusinessEffect: true
    tenantIsolation: true
  runs:
    before: [A1, A2, A3]
    after: [B1, B2, B3]
  recorded:
    - offered-and-completed-ops
    - latency-histograms-per-operation
    - timeout-and-retry-count
    - query-plans
    - keys-and-docs-examined
    - storage-and-index-bytes
    - cpu-memory-disk-io
    - correctness-oracle-results
    - index-build-logs
    - cost-and-rollback-analysis
  decisions:
    listReadGate: PASS
    createWriteOverheadGate: FAIL
    overall: NO_GO_UNTIL_REDESIGN
~~~

Đây là **mẫu báo cáo**, không phải input chạy được của một công cụ cụ thể. Đổi tên fields theo conventions của tổ chức và ghi liên kết tới artifacts/commit, không đưa credentials vào.

## 52. Quy tắc quyết định nhiều tầng

1. **Correctness hard gates:** tenant isolation, no lost acknowledged writes, no duplicate intents, required consistency. Vi phạm → NO-GO.
2. **Functional hard gates:** mọi required query trả đúng shape/sort/filter trong scope, không dùng unsupported feature → FAIL nếu không đạt.
3. **SLO:** p99 theo operation, error budget, throughput at target load → PASS/FAIL.
4. **Resource/recovery:** disk headroom, failover, restore, migration within constraints.
5. **Cost/complexity:** quyết định trade-off khi mandatory gates đã đạt.
6. **Uncertainty:** thiếu evidence → INCONCLUSIVE, có owner/timebox bổ sung.

Không dùng “weighted score” để bù cho một lỗi data leakage hoặc oversell. Khi read p99 tốt và write p99 chưa đạt, có thể điều chỉnh index hoặc workload assumptions rồi retest, **không sửa ngưỡng sau khi xem kết quả** trừ khi có thay đổi yêu cầu kinh doanh chính thức.

## 53. Runbook thực hành: đo A rồi B trên cùng bộ dữ liệu

### Phase A — Thiết lập

1. Chọn business operation đang chậm và nêu nguyên nhân giả định.
2. Chốt dataset manifest: seed, tenant skew, Orders sizes, time distribution, TTL.
3. Chốt query semantics: fields, sort, cursor, consistency và auth.
4. Chốt critical SLO/hard gates cho đọc và ghi.
5. Cấu hình topology, TLS/IAM, driver retries và monitoring.
6. Tạo baseline index inventory và query plan.
7. Đặt giới hạn an toàn: load, disk headroom, stop authority.

### Phase B — Đo Before

8. Seed/snapshot dataset vào môi trường A.
9. Kiểm các counters/known business intents đầu vào.
10. Warm-up theo protocol hoặc chạy cold test riêng.
11. Chạy workload normal/peak/burst/soak.
12. Thu latency histograms, offered/completed QPS, errors, retries.
13. Thu server query plan, index/storage bytes, CPU/I/O, cache và replica lag.
14. Lưu config, logs, run ID và correctness result.

### Phase C — Đo After

15. Reset/clone dataset về cùng trạng thái đầu A.
16. Tạo chỉ mục hoặc representation mới theo thiết kế.
17. Đo index build/backfill/CDC costs ở phase riêng.
18. Đợi target ready, ghi version và index state.
19. Warm-up bằng cùng policy.
20. Chạy workload với trace/seed/arrival schedule tương đương.
21. Thu cùng metrics và business oracle.
22. Lặp runs để thấy noise/variability.

### Phase D — Ra quyết định

23. So correctness và mandatory SLO trước.
24. So p50/p95/p99, throughput, errors, retries per operation.
25. So data/index bytes, read/write amplification, TCO.
26. Kiểm hot tenant, cold history, long soak và recoverability.
27. Đánh giá transition/rollback risks.
28. Ghi PASS/FAIL/INCONCLUSIVE, evidence và owner.
29. Nếu GO, lập rollout/canary/monitoring gate.
30. Nếu NO-GO, giữ baseline và nêu giả thuyết sửa đổi cụ thể.

Đây là **runbook thử nghiệm**, không phải lệnh triển khai production. Mọi thay đổi index/partition trên production cần change approval, backup, recovery và công cụ theo engine thực tế.

## 54. Triển khai dần khi quyết định giữ index

Một rollout có thể gồm:

~~~mermaid
flowchart TD
    A["Index design approved"] --> B["Capacity/backup/preflight"]
    B --> C["Build index under monitored load"]
    C --> D["Verify index ready on required replicas"]
    D --> E["Shadow queries / plan comparison"]
    E --> F["Canary read traffic"]
    F --> G["Increase eligible traffic"]
    G --> H["Verify full SLO + write impact"]
    H --> I["Update runbooks and index inventory"]
~~~

Cần đánh giá:

- Build index có ảnh hưởng p99/replica lag quá ngưỡng?
- Query planner thực sự chọn index phù hợp?
- App có cần restart/feature flag/query hint thay đổi?
- Read canary có còn đúng tenant/customer/sort/cursor?
- Write impact trên source và index data growth?
- Một index mới có thể ảnh hưởng query plan của query khác?
- Có đủ storage headroom khi rollback cần hai versions không?
- Nếu lệnh build lỗi thì cleanup/resume ra sao?

**Canary read success không chứng minh chi phí ghi** vì mọi writes có thể đã duy trì index ngay từ lúc build xong. Vì vậy monitor write p99 và resource trong cả canary lẫn steady full traffic.

## 55. Rollback khi index mới không đạt

Một rollback an toàn không nên chỉ “xóa index ngay”.

Quy trình:

1. **Contain:** ngừng các hints/query rewrites phụ thuộc index (nếu có).
2. **Verify fallback:** các truy vấn cũ vẫn đúng và trong performance budget tạm chấp nhận.
3. **Observe:** xem index có đang phục vụ critical query hay constraint không.
4. **Plan drop/remove:** tính I/O và locks/DDL semantics của engine.
5. **Keep evidence:** lưu query plans, p99, index size, fault/tuning logs.
6. **Execute controlled removal** nếu được phê duyệt và engine cho phép.
7. **Monitor:** query correctness/performance, write p99, resource recovery.
8. **Update schema inventory** để môi trường khác không lệch nhau.

Nếu After thay **physical data model** chứ không chỉ thêm index, rollback khó hơn: read projections/cursors có thể đã thay; writes mới chỉ tồn tại trong representation mới. Cần read route fallback, CDC/reconciliation hoặc một forward-repair protocol.

**Không xóa một unique index hoặc policy-critical index chỉ vì write chậm** khi chưa kiểm tra invariant bảo vệ bởi index đó.

## 56. Sự cố A — Index mới khiến write p99 tăng bất ngờ

Tình huống giả định:

~~~text
Before:
  CreateOrder p99 110ms
  ListOrders p99 350ms

After:
  CreateOrder p99 290ms
  ListOrders p99 65ms

Other observations:
  Disk writes +55%
  Replica lag 0.3s -> 6s
  Background compaction queue grows
~~~

Khả năng nguyên nhân:

- Index entry updates trên mỗi insert/update.
- Index lớn gây disk/page cache pressure.
- Replication và compaction write amplification.
- Một số indexed fields bị sửa liên tục.
- Concurrent index build chưa hoàn tất trên tất cả nodes.
- Working-set ratio thay đổi.

Điều tra: tách write paths theo field modified, nhìn disk I/O/cache/compaction/replica lag, giữ workload profile và thời điểm metrics. Không giải bằng tăng write timeout vô hạn hoặc hạ durability nếu business không cho phép.

**PASS đọc nhưng FAIL ghi** có thể dẫn đến loại index, thiết kế index nhỏ hơn/partial hơn, tách read model hoặc scale có tính chi phí.

## 57. Sự cố B — Overall p99 tốt nhưng tenant lớn tệ hơn

Giả định:

~~~text
Overall ListOrders p99:     80ms -> 50ms
Small tenant p99:           70ms -> 25ms
Largest tenant p99:        200ms -> 450ms
Largest tenant QPS share:  28%
~~~

Mức p99 overall không mô tả đầy đủ fairness; tenant lớn có thể gây hot partition, fan-out hoặc dữ liệu quá nhiều. Một số yêu cầu enterprise có SLO riêng, hoặc tenant lớn tạo dependency cho các tenants khác.

Hãy:

1. Group metrics theo tenant size và high-cardinality keys.
2. Xem per-partition throttling/query plan và result sizes.
3. So distribution Orders/customer, TTL/age và cache locality.
4. Kiểm data model có tạo một hot logical partition không.
5. Thử bucket/salt, nhưng đo read fan-out và merge.
6. Đặt tenant-level quotas/backpressure nếu phù hợp contract.
7. Test noisy neighbor: tenant lớn có làm tenants nhỏ chậm theo không.
8. Ghi risk/owner nếu không thể xử lý trong timebox.

Một index không nên được chấp nhận chỉ vì p50/p99 gộp trông đẹp nếu critical tenant class vi phạm cam kết.

## 58. Sự cố C — QPS After tăng vì workload sai

Một benchmark “After” báo 3.000 operations/s so với “Before” 1.500. Nhưng kiểm:

~~~text
Before queries:
  90% matched existing customers.
  average 20 results per page.

After queries:
  70% targeted nonexistent customers.
  average 0.8 results per page.
~~~

After nhanh hơn vì query **trả ít dữ liệu**, không phải index tốt hơn. Các lỗi tương tự:

- Cùng query name nhưng khác projection.
- `LIMIT` bị giảm.
- Cache warmed khác nhau.
- Index/fan-out thay đổi ngữ nghĩa filter.
- Auth tenant bị bỏ.
- Read consistency khác.
- Workload generator không giữ cùng key trace.
- Client timeout loại requests chậm khỏi sample.
- Một số writes/retry bị thất bại nhưng tính thành completed.

Cách sửa: lưu logical trace/key IDs, result count/hashes và schema/output contract; reset state; đo lại bằng same seed. **Không dùng kết quả sai điều kiện làm bằng chứng chọn kiến trúc**.

## 59. Sự cố D — Cache và background jobs tạo chênh lệch giả

Một phép đo Before chạy ngay sau seed, khi page cache lạnh và compaction đang bận. After chạy một giờ sau, khi working set nóng trong RAM và compaction đã giảm. Tốc độ tăng có thể đến từ **môi trường**, không phải index.

Cần tách:

- Cold-start performance.
- Warm steady-state performance.
- Background index build/compaction/repair pressure.
- Cache hit/miss, eviction và disk reads.
- Replica lag, node health.
- Storage burst credit/quota.
- JVM/driver/connection-pool warm-up.

Thực hành:

1. Ghi cache/compaction state trước mỗi run.
2. Warm-up theo một protocol có metrics xác định, không chỉ sleep cố định.
3. Có cold test riêng hoặc reset state tương đương trong môi trường an toàn.
4. Chạy paired repeats, đổi thứ tự A/B khi phù hợp.
5. Ghi một run gặp external anomaly là inconclusive, không che nó.
6. So query plan/IO ngoài latency.

Kết luận phải trả lời: **Tốc độ thay đổi vì index hay vì data/cache/workload khác?**

## 60. Mẫu decision record

~~~markdown
# Decision: Add compound index for Order history

## Problem
ListOrdersByCustomer p99 exceeds target under skewed peak.

## Options
A: Existing schema/index.
B: Compound tenant-customer-time-orderId index.
C: Dedicated OrdersByCustomer projection.

## Requirements
- Exact tenant/customer filtering.
- Stable descending cursor pagination.
- Read-your-writes according to API.
- No duplicate intents or acknowledged write loss.

## Experiment
- Dataset seed/version/distribution.
- Same workload and arrival schedule.
- Same topology, TLS/auth, consistency and SDK settings.
- Repeated runs: normal, peak, burst, soak.

## Evidence
- p50/p95/p99 and errors by operation/tenant.
- Query plans, documents/keys scanned.
- Storage/index bytes, CPU/disk/network, write cost.
- Correctness oracle and freshness result.
- Index build/backfill/restore/rollback costs.

## Gate results
- Read SLO: PASS or FAIL.
- Write regression: PASS or FAIL.
- Correctness: PASS or FAIL.
- Recovery/migration: PASS or FAIL.

## Decision
GO, NO-GO or INCONCLUSIVE; include owner and date.

## Rollout
Canary, stop conditions, monitoring and safe rollback.

## Open risks
Risk, evidence gap, mitigation, owner, review date.
~~~

Không đặt credentials, PII hoặc raw payment payload trong báo cáo. Liên kết kết quả tới versioned logs/histograms/query plans và schema commit để người khác tái lập.

## 61. Bài tập A — Thêm compound index cho Orders

Giả sử collection Orders có 5 triệu records, 20% customers chiếm 80% reads, mỗi trang 20 Orders, 30% writes là CreateOrder.

Yêu cầu:

1. Viết query theo `tenantId`, `customerId`, `createdAt`, `orderId`.
2. Đề xuất index ghép và giải thích thứ tự fields.
3. Thiết kế baseline quan sát scan/plan.
4. Sinh dữ liệu với customer skew và createdAt trùng nhau.
5. Chạy read workloads ở 100, 500, 1.000 requests/s.
6. Chạy mixed read/write peak, không chỉ read-only.
7. Thu p50/p95/p99, errors, completed throughput.
8. Thu query plan, keys/docs examined, storage bytes.
9. Đo CreateOrder/UpdateOrderStatus p99 trước/sau.
10. Kiểm stable cursor khi concurrent insert/delete.
11. Đo tác động index build và disk headroom.
12. Đặt gates: ListOrders p99, max write regression, no tenant leakage.
13. Viết bảng PASS/FAIL với evidence.
14. Lập rollback nếu index gây regression.

**Gợi ý:** Nếu read p99 giảm mạnh nhưng write p99 vi phạm gate, bài giải đúng phải nêu trade-off/next experiment, không tự quyết định GO.

## 62. Bài tập B — Đổi cách tổ chức dữ liệu theo bucket tháng

Cho dữ liệu:

~~~text
30 million Orders
Largest customer has 500,000 Orders
80% queries target last 30 days
10% queries target 12 months
10% queries target full history
One tenant contributes 40% writes
~~~

Một representation đề xuất:

~~~text
Partition key = tenantId + customerId + YYYYMM
Sort key = createdAt DESC + orderId DESC
~~~

Hãy:

1. Vẽ sơ đồ source-of-truth và bucketed read projection.
2. Xác định bao nhiêu buckets một query 12 tháng có thể đọc.
3. Thiết kế top-K merge với stable tie-breaker.
4. Thiết kế cursor qua nhiều buckets để tránh trùng/bỏ record.
5. Tạo test cases tại month boundary và dữ liệu late-arriving.
6. Đo p99 recent-only, multi-month và deep-history.
7. Đo bytes/queries per logical ListOrders.
8. Đo write contention trên current bucket.
9. Thiết kế version/tombstone replay source → projection.
10. Kiểm read-your-writes khi projection chưa bắt kịp.
11. Đo projection storage và write amplification.
12. Nếu dùng salting, đo read fan-out tăng ra sao.
13. So TCO với compound-index approach.
14. Đặt NO-GO nếu consistency, latency hoặc migration không đạt.

**Không bắt buộc bucketing phải thắng**. Một kết luận hợp lệ có thể là index thông thường đã đủ tốt và bucket làm hệ phức tạp không đáng.

## 63. Bài tập C — Phân tích số liệu và quyết định

Hai nhánh dùng cùng dataset/trace có kết quả giả định:

| Metric | Before | After |
|---|---:|---:|
| ListOrders p99 | 320 ms | 85 ms |
| CreateOrder p99 | 145 ms | 178 ms |
| ListOrders error | 0,3% | 0,2% |
| CreateOrder error | 0,1% | 0,1% |
| Peak CPU | 74% | 68% |
| Disk write IOPS | 12.000 | 16.000 |
| Total index storage | 40 GiB | 55 GiB |
| Duplicate business effects | 0 | 0 |
| Tenant leakage | 0 | 0 |
| Largest tenant ListOrders p99 | 380 ms | 270 ms |

Acceptance:

~~~text
Overall ListOrders p99 <= 100 ms
CreateOrder p99 regression <= 15%
Largest tenant ListOrders p99 <= 200 ms
No duplicate effect or tenant leakage
Index storage increase <= 40%
~~~

Câu hỏi:

1. Overall ListOrders gate đạt chưa?
2. CreateOrder p99 tăng bao nhiêu phần trăm?
3. Index storage tăng bao nhiêu phần trăm?
4. Tenant lớn có đạt gate không?
5. Tại sao overall p99 không thay tenant SLO?
6. Có thể đánh giá After GO không?
7. Tại sao disk IOPS có thể tăng dù CPU giảm?
8. Nếu p99 dựa trên rất ít samples, cần báo uncertainty gì?
9. Đề xuất một hypothesis để giảm write amplification.
10. Nếu thử phương án projection, phải đo thêm metrics nào?
11. Đặt stop conditions cho index build on-live-traffic.
12. Viết một decision record ngắn, có evidence.

**Gợi ý:** 145 → 178 ms tăng khoảng 22,8%, vượt 15%; largest-tenant p99 vẫn 270 ms, chưa đạt 200 ms. Dù read p99 tổng đã xuống 85 ms, toàn bộ hard gates chưa đạt.

## 64. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Thay thế |
|---|---|---|
| “Thêm index chắc chắn nhanh hơn” | Có thể tăng write, storage, cache pressure | Đo read + write + resources |
| “Chỉ cần chạy một query trước/sau” | Không đại diện workload mix | Mixed load and business journeys |
| “p99 tốt nghĩa không có lỗi” | Timeouts/errors có thể bị loại | Đo toàn bộ outcomes |
| “Cùng count nghĩa dataset giống” | Skew, size, age khác | Dataset manifest/histograms |
| “100 nghìn records đủ ngoại suy 30 triệu” | Cache cliff/index nonlinear | Multi-size tests |
| “Index dùng tức query tối ưu” | Scan/fetch vẫn lớn | Keys/docs examined và p99 |
| “Query đúng 20 records là đủ” | Có thể sai tenant/order/cursor | Business oracle |
| “Đổi pageSize không ảnh hưởng so sánh” | Bytes/workload khác | Same API contract |
| “Cold A vs warm B là công bằng” | Cache bias | Same warm/cold protocol |
| “Write p99 không liên quan index” | Index maintenance khi ghi | Write amplification metrics |
| “Index build time không tính” | Rollout có thể gây outage | Measure transition |
| “Data layout change chỉ đổi tên key” | Có CDC/backfill/projection | Full architecture costs |
| “View eventual luôn tương đương source read” | Read-your-writes có thể fail | Freshness contract |
| “Một QPS tổng đại diện mọi tenants” | Hot tenant bị che | Tenant/key-level results |
| “Tăng nodes giải mọi hot key” | Một key vẫn serial/hot | Change partition/business model |
| “DynamoDB GSI giống base strong read” | Consistency properties khác | Verify per API/index |
| “ALLOW FILTERING là index thay thế” | Có thể query tốn scan | Model đúng partition |
| “Redis sorted set không có cost cập nhật” | App duy trì nhiều structures | Measure write/recovery |
| “Read model được seed sẵn là miễn phí” | Backfill/CDC có cost | Include migration/steady maintenance |
| “Chỉ nhìn average latency” | Tail p99/error bị che | Per-operation percentiles |
| “Closed-loop QPS giảm tức DB tốt hơn” | Generator tự chậm theo server | Offered vs completed |
| “Một run có p99 thấp là bằng chứng chắc” | Noise/sampling | Paired repetitions |
| “Tính trung bình các p99 là global p99” | Percentile không cộng tuyến tính | Merge raw/histograms properly |
| “Index size tăng ít nên TCO không đổi” | I/O, replicas, backup có cost | Full cost-to-SLO |
| “Rollback chỉ là xóa index” | Dependent queries/DDL risk | Controlled fallback |
| “Hai DB trả giống nhau nghĩa cả hai đúng” | Cùng có thể sai | Independent oracle |
| “Business correctness có thể bù bằng weighted score” | Safety/tenant isolation là hard gate | Hard gate trước score |
| “Một cải thiện 1 ms chắc đáng migrate” | Migration risk có thể lớn hơn lợi ích | Confidence + transition cost |
| “Đo peak là đủ” | Soak/TTL/compaction có thể khác | Long-run and maintenance |
| “Index có tên giống nhau hoạt động như nhau giữa engines” | Semantics khác | Engine/version documentation |

## 65. Câu hỏi tự kiểm tra

1. Vì sao cần baseline và treatment có đối chứng?
2. Thay index khác đổi data model ở điểm nào?
3. Điều gì phải giữ nguyên để so công bằng?
4. Fixed resources và fixed SLO đem lại hai cách nhìn gì?
5. Vì sao cần dataset có hot tenant và recency?
6. Working set/cache ratio ảnh hưởng thế nào?
7. Một query trả 0 records có thể khiến benchmark sai ra sao?
8. Tại sao stable cursor cần tie-breaker?
9. Concurrent writes ảnh hưởng pagination semantics thế nào?
10. Khi nào compound index nên ưu tiên equality fields?
11. Explain plan cho biết gì và không cho biết gì?
12. Keys/docs examined có ý nghĩa gì?
13. Một index mới có thể khiến CreateOrder chậm thế nào?
14. Vì sao indexed field update có chi phí khác nonindexed update?
15. Index size ảnh hưởng cache và backup ra sao?
16. Partial index có thể không hợp lệ cho query nào?
17. Index build khác steady-state benchmark thế nào?
18. Migration data layout cần backfill và CDC vì sao?
19. Vì sao projection eventual có thể fail read-your-writes?
20. Time bucket giúp gì và tạo thêm read fan-out thế nào?
21. Salting hot key có đánh đổi gì?
22. DynamoDB GSI cần đo write units và staleness thế nào?
23. Cassandra partition/clustering key phải gắn với query shape ra sao?
24. Redis sorted set query nhanh nhưng có những maintenance costs nào?
25. Embedded vs separated OrderItems nên so bằng metric nào?
26. Một Java harness cần stable operation IDs vì sao?
27. Scheduled start và actual start giúp đo điều gì?
28. Offered QPS và completed valid throughput khác nhau thế nào?
29. Open-loop/closed-loop khác nhau thế nào?
30. Coordinated omission khiến p99 bị báo thấp ra sao?
31. Little's law có liên quan concurrency và latency trong điều kiện nào?
32. Vì sao không so chỉ p99 success-only khi error rate khác?
33. Làm sao xác minh no duplicate Orders và no oversell?
34. Khi data model thay đổi, oracle cần kiểm logic gì?
35. Một query plan dùng index vẫn có thể chậm vì sao?
36. Vì sao nên đo cả hot tenant và cold history?
37. Lặp nhiều runs giúp xử lý uncertainty thế nào?
38. Tại sao không lấy average per-minute p99 làm global p99?
39. Load staircase xác định saturation theo SLO ra sao?
40. Cách tính % regression của CreateOrder p99?
41. Chi phí per business journey khác cost per physical request thế nào?
42. Read projection cần tính chi phí viết/khôi phục gì?
43. Khi nào index mới bị đánh NO-GO dù read p99 cải thiện?
44. Một rollback index cần những steps phòng rủi ro nào?
45. Vì sao test failover/index build impact có thể cần phase riêng?
46. Khi API không được hạ consistency, có thể so eventual với strong trực tiếp không?
47. Dataset seed và manifest giúp tái lập kết quả thế nào?
48. Số liệu gần SLO nhưng nhiễu lớn nên kết luận gì?
49. Báo cáo cần giữ artifacts nào?
50. Khi nào nên chọn không đổi index/data model vì lợi ích chưa đủ?

## 66. Tổng kết: đo tải là phép chứng minh hệ thống, không chỉ một truy vấn

Thêm index hay thay cách tổ chức dữ liệu đều làm thay đổi **đường truy cập và công việc mà database thực hiện**. Một index ghép có thể rút ngắn range scan nhưng tăng write amplification. Một bucket hoặc materialized projection có thể làm read rất nhanh nhưng tăng fan-out, storage, CDC lag và migration complexity. Vì vậy **Before/After đúng** phải giữ cùng nghiệp vụ, dữ liệu, tải, consistency và durability, rồi đo đồng thời read, write, tài nguyên, lỗi và tính đúng đắn.

Quy trình có thể lặp lại:

~~~text
1. Xác định query/business operation và SLO đang gặp vấn đề.
2. Viết giả thuyết, hard gates và success criteria.
3. Lập dataset manifest có size, skew, recency và lifecycle đúng.
4. Dựng baseline với topology và security như dự kiến.
5. Lập workload mix có concurrency, hot keys, bursts và soak.
6. Ghi query plan, p50/p95/p99, errors, resource và correctness.
7. Chạy Before, giữ đầy đủ config và kết quả.
8. Thêm index hoặc đổi representation theo một biến thay đổi rõ.
9. Đo index build/backfill và steady-state After riêng.
10. Chạy cùng workload/seed, lặp để đánh giá độ biến thiên.
11. So results theo operation, tenant, time phase và SLO.
12. Kiểm business oracle, read-your-writes, TTL/deletes, tenant rights.
13. Tính storage/index/write amplification và cost-to-SLO.
14. Đánh giá migration, rollout, rollback, failover và restore.
15. Ghi PASS/FAIL/INCONCLUSIVE cùng evidence và owner.
16. Triển khai dần có stop gates, hoặc giữ baseline nếu chưa đủ lợi ích.
~~~

**Kết luận cốt lõi:** *Một thay đổi chỉ mục hoặc mô hình dữ liệu chỉ đáng giữ khi hệ thống trả đúng kết quả và đạt các cam kết nghiệp vụ dưới tải đại diện, với chi phí đọc, ghi, vận hành và phục hồi chấp nhận được. Tốc độ một query không thể đại diện cho chất lượng của toàn hệ thống.*










