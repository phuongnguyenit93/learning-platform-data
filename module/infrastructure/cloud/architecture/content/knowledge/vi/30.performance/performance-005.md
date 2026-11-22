# Tối ưu giao tiếp: giảm số lần gọi, batching và nén

Trong kiến trúc cloud, hiệu năng không chỉ phụ thuộc CPU, memory hay tốc độ database. Một request có thể tiêu tốn phần lớn thời gian chờ qua mạng: gọi nhiều service tuần tự, thực hiện quá nhiều round trip tới database, gửi từng message nhỏ, hoặc truyền payload lặp lại. Khi độ trễ mạng tăng, số lần giao tiếp và kích thước dữ liệu thường khuếch đại tác động lên latency, throughput, chi phí và khả năng chịu tải.

**Tối ưu giao tiếp** là thiết kế cách các thành phần trao đổi dữ liệu sao cho giảm overhead mà vẫn giữ đúng semantics của nghiệp vụ. Ba kỹ thuật phổ biến là giảm số lần gọi (request consolidation và chatty-call reduction), batching (gom nhiều thao tác thành một lần giao tiếp) và compression (nén dữ liệu truyền/lưu). Chúng có thể cải thiện đáng kể hiệu năng, nhưng cũng tạo đánh đổi: batch làm tăng latency chờ gom dữ liệu, payload lớn hơn có thể tăng memory, compression dùng CPU và thay đổi điểm quan sát lỗi.

Bài học thuộc chương **Hiệu năng** của lộ trình **Cloud Architecture**. Lộ trình này hướng dẫn thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Vì vậy, tối ưu giao tiếp phải dựa trên đo đạc end-to-end và workload thực, đồng thời giữ timeout, ordering, idempotency, security và failure handling đúng.

Sau bài học, bạn có thể:

- Nhận diện chatty communication, round-trip overhead, payload bloat và fan-out.
- Đo latency, throughput, bytes transferred và request amplification.
- Giảm số lần gọi bằng API phù hợp, projection, pagination và cache.
- Chọn batching theo throughput, latency budget, payload limit và failure semantics.
- Thiết kế batch flush theo size/time/idle trigger, backpressure và retry.
- Chọn compression algorithm/level theo CPU, payload, network và client capability.
- Tránh nén payload vốn đã compressed hoặc quá nhỏ.
- Áp dụng batching và compression an toàn cho HTTP, RPC, database và message broker.
- Kiểm thử correctness, tail latency, resource consumption và chi phí.

## 1. Vì sao số lần giao tiếp quan trọng?

Một lần gọi mạng thường gồm nhiều thành phần: DNS/connection setup nếu chưa reuse, TLS, network transit, queueing, serialization/deserialization, xử lý phía server và response. Dù mỗi lần gọi chỉ mất vài mili giây, hàng chục round trip tuần tự có thể làm request chậm đáng kể.

Ví dụ trang dashboard cần hiển thị 40 booking. Nếu ứng dụng gọi API riêng cho từng booking để lấy customer, asset và payment summary, một request có thể tạo hàng chục đến hàng trăm downstream calls. Đây là dạng **chatty communication**.

Ngược lại, một API tổng hợp có thể lấy đủ dữ liệu cho màn hình trong một số ít request, hoặc service có thể cung cấp projection đã được chuẩn bị trước.

### 1.1. Mô hình latency

Với N lần gọi tuần tự, latency xấp xỉ:

\[
T_{total} \approx \sum_{i=1}^{N}(T_{network,i}+T_{queue,i}+T_{server,i})
\]

Nếu mỗi call có latency trung bình 20 ms và có 25 call tuần tự, riêng tổng thời gian các call đã khoảng 500 ms, chưa tính xử lý local. Đây là ví dụ đơn giản; tail latency và dependency contention có thể làm kết quả xấu hơn.

Với N call chạy song song, latency có thể gần thời gian của call chậm nhất thay vì tổng, nhưng số call vẫn tạo tải fan-out và xác suất gặp ít nhất một dependency chậm/lỗi tăng lên. Parallelism không xóa overhead; nó chuyển áp lực sang concurrency, connection và downstream capacity.

### 1.2. Request amplification

Một HTTP request từ client có thể tạo ra nhiều call nội bộ. Tỷ lệ:

\[
A = \frac{\text{Tổng số downstream calls}}{\text{Số inbound requests}}
\]

Nếu mỗi inbound request tạo trung bình 18 downstream calls, amplification là 18. Khi traffic tăng từ 100 lên 1.000 request/giây, downstream có thể nhận 18.000 call/giây. Cần theo dõi amplification theo endpoint và operation.

~~~mermaid
flowchart TD
    U["One client request"] --> API["API service"]
    API --> A["Customer lookup"]
    API --> B["Asset lookup"]
    API --> C["Payment lookup"]
    API --> D["Policy lookup"]
    API --> E["History lookup"]
    A --> DB1[("Customer DB")]
    B --> DB2[("Asset DB")]
    C --> DB3[("Payment DB")]
    D --> DB4[("Policy DB")]
    E --> DB5[("History DB")]
~~~

## 2. Đo trước khi tối ưu

Không nên mặc định mọi network call đều là vấn đề. Một request phụ có thể không đáng kể nếu nó chạy song song, cache hit cao và không nằm trên critical path. Trước khi thay đổi, cần thu thập baseline.

| Metric | Ý nghĩa |
| --- | --- |
| Calls per inbound request | Mức amplification/fan-out |
| Round trips per transaction | Số lần trao đổi tuần tự |
| p50/p95/p99 latency | Phân bố độ trễ, đặc biệt tail |
| Payload bytes/request | Kích thước truyền mỗi lần |
| Total bytes/sec | Băng thông sử dụng |
| Serialization CPU/time | Chi phí encode/decode |
| Compression ratio | Tỷ lệ bytes sau nén so với trước nén |
| Batch size and wait time | Kích thước batch và thời gian chờ gom |
| Batch flush frequency | Tần suất flush |
| Retry/duplicate rate | Chi phí giao tiếp phát sinh lại |
| Connection reuse/pool saturation | Hiệu quả sử dụng connection |
| Queue age/backlog | Tác động của batching hoặc consumer capacity |

### 2.1. Theo dõi tail latency

Trung bình có thể che giấu request chậm. Nếu p99 tăng mạnh, nguyên nhân có thể là một dependency chậm, batch chờ flush, queueing hoặc payload lớn gây garbage collection. Đo latency theo endpoint, dependency, payload size, batch size và client type để xác định tương quan.

### 2.2. Phân tích critical path

Sử dụng distributed trace để thấy call tuần tự, song song, retry và serialization span. Xác định những call cần để trả response ngay; những call có thể xử lý bất đồng bộ; những dữ liệu có thể lấy bằng projection/read model.

Tối ưu tốt thường bắt đầu từ việc loại bỏ call không cần thiết khỏi critical path thay vì chỉ tăng timeout hoặc thêm thread.

## 3. Giảm số lần gọi: thiết kế API theo use case

Một cách giảm round trip là thiết kế endpoint trả đủ dữ liệu phù hợp với một use case, thay vì bắt client ghép nhiều API nhỏ.

Ví dụ, trang booking summary có thể cần booking, asset label và trạng thái thanh toán. Một endpoint tổng hợp có thể trả projection đã được domain service chuẩn bị:

~~~http
GET /v1/bookings/booking-1005/summary
Accept: application/json
~~~

Ví dụ response:

~~~json
{
  "bookingId": "booking-1005",
  "status": "CONFIRMED",
  "asset": {
    "assetId": "asset-42",
    "displayName": "Camera kit"
  },
  "payment": {
    "status": "AUTHORIZED",
    "currency": "VND"
  }
}
~~~

Projection có thể được xây trong service sở hữu use case, API composition layer hoặc read model. Cần tránh biến endpoint tổng hợp thành một distributed monolith gọi hàng chục service tuần tự.

### 3.1. API composition và BFF

Backend for Frontend (BFF) có thể tổng hợp dữ liệu phù hợp cho web/mobile client. Nó giảm request từ client nhưng không tự giảm số downstream calls nếu BFF chỉ fan-out mọi API như trước. Cần đo call graph và cân nhắc projection/caching hoặc thay đổi ownership dữ liệu.

### 3.2. GraphQL, REST aggregation và RPC

GraphQL có thể cho client chọn fields cần thiết và giảm over-fetching, nhưng resolver thiết kế kém có thể tạo N+1 queries. REST aggregation và RPC cũng có thể tạo chatty pattern nếu endpoint quá nhỏ. Công nghệ giao tiếp không tự giải quyết số lần round trip; cần thiết kế query plan, batching resolver và giới hạn depth/complexity.

## 4. Loại bỏ N+1 calls

Một anti-pattern phổ biến là query danh sách entity rồi gọi thêm một query cho mỗi entity để lấy related data.

~~~text
bookings = queryBookings(tenantId)

for booking in bookings:
    customer = getCustomer(booking.customerId)
    asset = getAsset(booking.assetId)
    append(summary(booking, customer, asset))
~~~

Với 100 booking, đoạn code có thể tạo 1 query danh sách và 200 lookup. Cách cải thiện là lấy ID theo danh sách và query bulk:

~~~text
bookings = queryBookings(tenantId)
customerIds = unique(bookings.customerId)
assetIds = unique(bookings.assetId)

customers = getCustomersByIds(customerIds)
assets = getAssetsByIds(assetIds)

return joinInMemory(bookings, customers, assets)
~~~

Nếu các dữ liệu thuộc cùng database/domain, dùng join phù hợp có thể hiệu quả hơn. Nếu thuộc các service khác nhau, bulk endpoint hoặc read projection giúp giảm network round trips.

### 4.1. Giới hạn kích thước bulk lookup

Bulk endpoint cần giới hạn số ID, payload bytes và execution time. Không cho client gửi danh sách hàng triệu ID trong một request; dùng pagination, async export hoặc job processing cho khối lượng lớn.

## 5. Pagination, field selection và payload minimization

Giảm số lần gọi không có nghĩa trả mọi dữ liệu trong một response lớn. Payload quá lớn làm tăng network transfer, memory, serialization, parse time và nguy cơ timeout.

- Pagination/cursor cho danh sách dài.
- Field selection/projection chỉ trả dữ liệu cần thiết.
- Dùng summary thay full object khi phù hợp.
- Tránh lặp metadata trên từng record.
- Dùng enum/code ổn định thay chuỗi mô tả dài nếu contract cho phép.
- Chỉ expand nested relation cần thiết.
- Giới hạn payload size và depth.
- Hỗ trợ conditional request/ETag khi có lợi.

### 5.1. Offset và cursor pagination

Offset phù hợp trang nhỏ và dataset có ít thay đổi, nhưng offset lớn có thể tốn query và kết quả dễ dịch chuyển khi dữ liệu mới xuất hiện. Cursor/keyset pagination dựa trên ordering key giúp duyệt ổn định hơn nếu sort key được chọn đúng.

Cả hai đều có trade-off. Cursor cần opaque token và validate để client không thể dùng cursor của tenant/resource khác.

## 6. Cache để tránh gọi lặp lại

Cache có thể loại bỏ những lần gọi lặp cho dữ liệu ít thay đổi hoặc có freshness policy phù hợp. Cache key phải bao gồm tenant/resource scope; TTL và invalidation cần phản ánh semantics nghiệp vụ.

Cache phù hợp với reference data, configuration non-sensitive, catalog hoặc summary. Cẩn thận khi cache quyền truy cập, payment state, inventory availability hay dữ liệu cần strong consistency.

Các lựa chọn: in-process cache, distributed cache, HTTP cache/CDN và materialized view/read model. Mỗi loại tạo dependency và freshness policy riêng. Cache hit ratio cao có thể che giấu workload khi cache cold hoặc bị invalidation đồng loạt.

## 7. Batching là gì?

**Batching** gom nhiều thao tác nhỏ thành một đơn vị giao tiếp lớn hơn để giảm fixed overhead trên mỗi operation.

Ví dụ thay vì gửi 100 message riêng, producer gom 100 message vào một batch publish. Thay vì insert từng row qua một request database, client dùng bulk insert hoặc prepared statement batch.

Tổng chi phí có thể hình dung:

\[
C_{total} \approx N \cdot C_{fixed} + C_{payload}
\]

Batching giảm số lần trả phần fixed overhead, nhưng có thể tăng payload, thời gian chờ và memory. Nếu batch quá lớn, retry một lần có thể phải xử lý lại nhiều dữ liệu và vượt giới hạn transport.

| Lớp | Ví dụ |
| --- | --- |
| HTTP API | Bulk create/update, batch lookup |
| gRPC | Client/server streaming hoặc batch RPC |
| Database | Multi-row insert, prepared statement batch |
| Message broker | Batch produce/fetch/ack theo capability |
| Object storage | Gom file nhỏ, multipart upload |
| Analytics | Micro-batch events và bulk load |
| External provider | Batch API theo rate limit/contract |

Không phải mọi protocol hỗ trợ một request batch theo cùng semantics. Với streaming, batch có thể do client library/broker tự nhóm record và flush; với API bulk, batch là một business operation có response/partial failure contract.

## 8. Chọn kích thước batch

Batch size cần cân bằng throughput, latency, memory, payload limit và lỗi.

- Batch quá nhỏ: ít giảm overhead.
- Batch quá lớn: chờ gom lâu, tăng memory và risk timeout.
- Payload batch quá lớn: vượt API/broker limit hoặc bị phân mảnh.
- Batch có record kích thước khác nhau: số item không phản ánh bytes.
- Batch xử lý lâu: một record lỗi có thể kéo dài toàn batch nếu contract không tách lỗi.

Nên giới hạn cả **max items**, **max bytes** và **max wait time**. Có thể dùng adaptive batching dựa trên traffic và downstream capacity, nhưng phải có upper bound và guardrail.

### 8.1. Flush theo size và time

Một batch producer thường flush khi đủ số message, đủ tổng bytes, hết thời gian chờ tối đa, có sự kiện shutdown hoặc một message đặc biệt cần gửi ngay theo policy.

~~~mermaid
flowchart TD
    A["New item arrives"] --> B["Add to pending batch"]
    B --> C{"Item/byte limit reached?"}
    C -- "Yes" --> F["Flush batch"]
    C -- "No" --> D{"Max wait elapsed?"}
    D -- "Yes" --> F
    D -- "No" --> B
    F --> G["Send and record result"]
    G --> H["Start next batch"]
~~~

Đặt timer không chính xác có thể gây starvation nếu luôn có traffic; cần bảo đảm batch vẫn flush khi đủ time. Khi traffic thấp, time-based flush giới hạn độ trễ.

## 9. Batching và latency

Batching thường cải thiện throughput nhưng làm tăng latency từng item vì item đầu tiên phải chờ các item sau.

\[
T_{item} = T_{wait\_in\_batch} + T_{send} + T_{process}
\]

Với low traffic, max wait time có thể chi phối tổng. Với high traffic, batch đầy nhanh nên wait thấp hơn. Cùng một cấu hình batch có thể có latency rất khác giữa giờ cao điểm và thấp điểm.

Nếu API đồng bộ cần phản hồi ngay, không nên đợi một batch đủ size. Batch thích hợp hơn cho write path bất đồng bộ, bulk operations hoặc client SDK có latency budget rõ.

### 9.1. Latency SLO và throughput objective

Chọn batch size bằng benchmark theo nhiều traffic profile: idle, normal, peak và burst. Đo p95/p99 per-item latency, batch completion latency, throughput, memory và retry. Không chỉ chọn cấu hình cho throughput tối đa nếu nó làm vi phạm latency SLO.

## 10. Partial failure trong batch

Một batch có thể gồm nhiều record nhưng không phải lúc nào tất cả đều thành công hoặc thất bại cùng nhau.

- **Atomic batch:** toàn bộ batch thành công hoặc rollback nếu nền tảng hỗ trợ transaction.
- **Partial success:** từng item có kết quả riêng.
- **Best-effort:** xử lý item hợp lệ, ghi nhận item lỗi.
- **At-least-once:** có thể giao/xử lý lại; consumer phải idempotent.
- **At-most-once:** có thể mất item nếu failure xảy ra ở thời điểm không an toàn.
- **Exactly-once effect:** cần cơ chế transaction/idempotency rõ ở cả storage và side effect; không suy ra chỉ từ tên API/broker.

Ví dụ bulk update trả kết quả per-item:

~~~json
{
  "batchId": "batch-20261118-01",
  "results": [
    {"itemId": "booking-1", "status": "UPDATED"},
    {"itemId": "booking-2", "status": "REJECTED", "code": "VERSION_CONFLICT"},
    {"itemId": "booking-3", "status": "UPDATED"}
  ]
}
~~~

Kết quả cần đủ để client retry đúng item lỗi mà không lặp side effect của item đã thành công.

## 11. Idempotency và retry cho batch

Khi response batch bị mất, client có thể không biết server đã xử lý toàn bộ, một phần hay chưa xử lý. Retry toàn batch có thể tạo duplicate.

Cần idempotency key cho batch hoặc từng item; message/item ID ổn định qua redelivery; unique constraint hoặc dedup store; batch processing state và per-item result; retry chỉ item chưa hoàn tất; backoff, jitter, retry budget; dead-letter/failed item queue; reconciliation khi kết quả unknown.

Một idempotency key cho toàn batch phù hợp nếu server lưu kết quả batch đầy đủ. Nếu batch được chia thành phần độc lập, per-item key giúp retry chính xác hơn. Validation error, authorization failure hoặc schema mismatch thường không trở thành thành công khi retry; cần phân loại transient/permanent.

## 12. Backpressure và batch queue

Batch producer/consumer cần kiểm soát pending buffer. Khi producer nhanh hơn consumer, queue hoặc memory có thể tăng không giới hạn.

Cần bounded queue/buffer, maximum inflight batch, consumer concurrency theo downstream capacity, pause/resume hoặc admission control, queue age/backlog alert, spill-to-disk hoặc durable broker khi phù hợp, fairness/quota theo tenant.

~~~mermaid
flowchart LR
    P["Producers"] --> B["Bounded pending buffer"]
    B -->|Batch flush| Q[("Durable broker")]
    Q --> C["Consumers with concurrency cap"]
    C --> D["Downstream service"]
    D -. "Capacity feedback" .-> C
    C -. "Backpressure" .-> B
~~~

Nếu consumer chậm, tăng batch size không nhất thiết giải quyết bottleneck; nó có thể làm batch processing time và memory tăng. Trước tiên xác định downstream throughput, queue age và saturation.

## 13. Message broker batching

Broker có thể batching ở producer, broker hoặc consumer fetch. Cần hiểu semantics cụ thể: batch publish có ordering trong partition/key không; broker ack khi message durable ở mức nào; failure ảnh hưởng toàn batch hay từng record; compression ở producer/broker/consumer; retry có giữ identity không; max message/batch bytes; consumer ack từng message hay theo offset; rebalance có redelivery không.

Batch theo partition/key có thể giữ ordering trong một phạm vi, nhưng nhiều partition không có global ordering mặc định. Chọn partition key theo consistency boundary nghiệp vụ.

## 14. Database batching

Database batching giảm round trip và overhead parse/execute. Prepared statement batch hoặc multi-row insert có thể hiệu quả cho bulk write.

Cần chú ý transaction boundary/atomicity; parameter/packet limits; lock duration/contention; index maintenance và WAL/log volume; constraint/trigger behavior; batch size/commit frequency; retry khi deadlock/serialization conflict; partial result semantics của driver/database.

Batch quá lớn có thể giữ lock lâu, tạo transaction log lớn hoặc rollback tốn kém. Chia theo chunk với checkpoint/idempotency thường phù hợp cho backfill lớn.

### 14.1. Bulk read

Thay nhiều point lookup bằng query WHERE id IN (...) , join hoặc table-valued input nếu database hỗ trợ. Giới hạn list size và xem query plan; danh sách cực lớn có thể gây plan kém hoặc vượt parameter limit.

## 15. Nén dữ liệu: mục tiêu và trade-off

Compression giảm số bytes truyền hoặc lưu, có thể hạ network cost và cải thiện latency khi network là bottleneck. Nhưng nén/giải nén tiêu thụ CPU, memory và có thể tạo overhead cho payload nhỏ.

\[
T_{compressed} \approx T_{compress} + \frac{S_{compressed}}{B} + T_{decompress}
\]

Trong đó S là kích thước bytes và B là throughput mạng. So với thời gian truyền S_raw/B, compression có lợi khi thời gian truyền tiết kiệm lớn hơn chi phí encode/decode và các overhead khác.

### 15.1. Khi nào compression có lợi?

Payload text/JSON/XML lớn và có tính lặp; link băng thông hạn chế hoặc egress cost đáng kể; response chậm do transfer bytes; batch có nhiều record cùng schema/metadata lặp; file log/analytics dạng text.

### 15.2. Khi nào không có lợi?

Payload nhỏ, latency bị chi phối bởi round trip; JPEG/PNG/MP4/ZIP hoặc payload đã nén; CPU đã bão hòa; client/mobile yếu phải giải nén nhiều; payload được mã hóa trước đó; hoặc compression tạo nguy cơ side-channel khi trộn secret và attacker-controlled data.

Không bật compression đại trà mà không đo payload size, CPU, latency và security context.

## 16. Chọn compression algorithm và level

| Thuật toán | Đặc điểm tổng quát | Trường hợp thường gặp |
| --- | --- | --- |
| gzip/DEFLATE | Tương thích rộng, CPU và ratio cân bằng tùy level | HTTP content encoding, text payload |
| Brotli | Thường nén tốt cho text/web; chi phí encode phụ thuộc level | Static web assets, response text khi client hỗ trợ |
| Zstandard (zstd) | Tốc độ tốt và nhiều mức trade-off | Internal service, file/batch/data pipeline khi ecosystem hỗ trợ |
| LZ4 | Tập trung vào tốc độ, ratio thường thấp hơn | High-throughput internal paths, storage/log pipeline |
| Snappy | Nén nhanh, thường dùng trong data/big data ecosystem | Data files hoặc streaming/broker ecosystem phù hợp |

Không chọn thuật toán chỉ theo bảng tổng quát. Benchmark với payload thực và thư viện/phiên bản triển khai. Cần kiểm tra client/browser, proxy, broker, database driver và format có hỗ trợ hay không.

Compression level cao thường tăng CPU và latency encode; lợi ích bytes có thể nhỏ dần. Với response realtime, mức nén thấp/trung bình có thể tốt hơn mức tối đa.

## 17. HTTP compression và content negotiation

HTTP cho phép client thông báo thuật toán chấp nhận qua header Accept-Encoding và server chỉ nên chọn encoding mà client hỗ trợ. Response dùng Content-Encoding để khai báo representation đã nén.

~~~http
GET /v1/bookings?pageSize=100 HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Encoding: gzip, br
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Vary: Accept-Encoding giúp cache phân biệt representation theo encoding. Proxy/CDN cần xử lý đúng header và cache key. Không nén response đã nén hoặc payload nhạy cảm trong bối cảnh có thể tạo compression side-channel.

### 17.1. Threshold và content type

Có thể chỉ nén khi response vượt ngưỡng byte và content type phù hợp. JSON/text thường có ích hơn ảnh JPEG đã nén. Threshold cần benchmark vì nén response 1 KB có thể tốn CPU mà chỉ tiết kiệm rất ít bytes.

### 17.2. Compression bomb và size limits

Khi nhận payload nén từ client hoặc broker, giới hạn cả compressed size và decompressed size. Một payload nhỏ có thể giải nén thành lượng dữ liệu rất lớn. Đặt maximum expansion ratio, decompressed bytes, nesting/decode depth và timeout phù hợp; validate trước khi phân bổ memory lớn.

## 18. gRPC, RPC và serialization

gRPC có thể hỗ trợ compression ở message level tùy runtime/client/server. Compression phải tương thích giữa các peer và được quan sát để tránh CPU saturation.

Các cách tối ưu giao tiếp RPC:

- Reuse channel/HTTP2 connection khi phù hợp.
- Tránh tạo channel mới mỗi request.
- Dùng deadline/cancellation.
- Chọn unary hay streaming theo semantics.
- Batch nhiều item khi có endpoint/contract phù hợp.
- Chỉ truyền field cần thiết.
- Dùng compression cho payload lớn có ích.
- Giới hạn message size và concurrent stream.
- Theo dõi serialization/deserialization time.

Binary serialization như Protocol Buffers có thể giảm payload so với JSON trong một số schema/workload, nhưng không mặc định luôn nhanh hơn; cần đánh giá CPU, compatibility, debuggability và client support. Serialization format và compression là hai lớp khác nhau.

## 19. Kết hợp batching với compression

Batching thường tăng cơ hội nén vì nhiều record có cấu trúc lặp. Nén từng item riêng có thể bỏ lỡ tính lặp giữa các item; nén batch sau serialize có thể cải thiện ratio.

Đổi lại, batch compression có thể tăng CPU producer/consumer, làm một item lỗi ảnh hưởng decode cả batch, cần buffer toàn batch, tăng decompression memory, khó random access và tăng latency do chờ batch đủ lớn.

Chọn boundary nén theo khả năng broker/protocol. Với stream lớn, chunked compression giúp tránh giữ toàn payload trong memory. Cần version và algorithm metadata để reader tương thích.

## 20. Network connection reuse và multiplexing

Giảm số lần tạo kết nối cũng giúp giảm handshake và setup overhead:

- HTTP keep-alive/reuse connection.
- HTTP/2 multiplex nhiều stream trên một connection.
- HTTP/3/QUIC có đặc tính transport khác và có thể giảm một số tác động head-of-line ở tầng transport.
- gRPC channel reuse.
- Database connection pool.
- Broker connection/session reuse.

Connection pooling cần giới hạn và lifecycle rõ. Pool quá lớn có thể làm cạn connection database; pool quá nhỏ tạo queueing. Multiplexing giảm số connection nhưng không loại bỏ giới hạn concurrency/flow control và server capacity.

## 21. Batching có thể thay đổi semantics giao tiếp

Một batch không chỉ là nhiều item đặt trong một array. Nó có thể thay đổi thời điểm item được gửi, thứ tự item, atomicity, failure scope, retry behavior, transaction boundary, observability granularity và fairness giữa tenant.

Ví dụ, nếu gom tất cả tenant vào một batch lớn, một tenant gửi nhiều dữ liệu có thể làm tenant khác phải chờ. Dùng per-tenant batch queue hoặc fairness policy nếu có yêu cầu isolation.

Đối với payment, booking hoặc inventory, không gộp thao tác nếu xử lý như một transaction chung làm thay đổi thứ tự hoặc invariant nghiệp vụ.

## 22. Security và privacy khi tối ưu payload

Giao tiếp hiệu quả vẫn phải giữ confidentiality, integrity và authorization.

- Chỉ gửi field downstream cần.
- Không gửi secret trong header/message payload nếu không cần.
- Mã hóa in transit bằng TLS/mTLS theo trust model.
- Nén sau khi đánh giá content classification và side-channel risk.
- Đặt payload size limit trước và sau decompression.
- Validate schema và version.
- Tenant scope mọi bulk request và batch item.
- Không để batch response tiết lộ record của tenant khác.
- Redact PII trong trace/log.
- Dùng checksum/signature khi cần integrity qua storage/transfer boundary.

Một bulk API phải kiểm tra authorization cho từng resource/tenant trong batch; không chỉ xác thực caller một lần rồi bỏ qua ownership từng item.

## 23. Ví dụ end-to-end: booking summary và event ingestion

Một trang dashboard lấy 50 booking, mỗi booking cần customer name, asset summary và payment status. Phiên bản đầu gọi một API danh sách booking rồi ba API cho từng booking, tạo tối đa 151 request.

### 23.1. Giảm số lần gọi

Thiết kế lại endpoint summary với pagination cursor và fields cần thiết. Booking service cung cấp read projection đã tổng hợp từ domain-owned data hoặc gọi bulk endpoint theo nhóm ID. Số round trips từ client giảm còn một vài call có giới hạn.

### 23.2. Batching event

Một producer ghi nhận booking events liên tục. Thay vì publish mỗi event như một RPC riêng, nó gom tối đa 100 event hoặc 256 KB, flush mỗi 20 ms. Các ngưỡng trên chỉ là giả định benchmark ban đầu, không phải cấu hình tối ưu chung.

Consumer xử lý batch với giới hạn concurrency, lưu per-message result và ack theo semantics broker. Message lỗi vĩnh viễn được quarantine; transient error retry có backoff và idempotency.

### 23.3. Compression

Nếu event JSON có nhiều field lặp, producer có thể serialize batch và dùng compression được broker hỗ trợ. Benchmark so sánh gzip/zstd/LZ4 theo CPU, ratio, p99 delivery latency và consumer memory. Với payload nhỏ hoặc đã compressed, bỏ compression.

~~~mermaid
flowchart LR
    API["Dashboard client"] --> SUM["Booking summary API"]
    SUM --> PROJ["Read projection / bulk lookup"]
    PROJ --> DATA[("Curated read data")]
    EVT["Booking events"] --> BATCH["Bounded batcher"]
    BATCH --> COMP["Serialize + compress"]
    COMP --> MQ[("Message broker")]
    MQ --> CON["Consumers"]
    CON --> STORE[("Downstream stores")]
~~~

### 23.4. Kế hoạch đo

| Chỉ số | Baseline | Mục tiêu đánh giá |
| --- | --- | --- |
| Client requests per dashboard | Nhiều request | Giảm rõ rệt |
| Downstream calls per summary | Cao | Giảm call amplification |
| p95/p99 dashboard latency | Baseline đo được | Không regression; cải thiện theo SLO |
| Batch item latency | Không áp dụng | Nằm trong latency budget |
| Broker throughput | Baseline | Tăng mà không backlog tăng |
| CPU producer/consumer | Baseline | Không vượt capacity |
| Bytes/event | Baseline | Giảm khi payload phù hợp |
| Duplicate/failed item rate | Baseline | Không tăng; có thể replay an toàn |

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Tạo nhiều API call nhỏ tuần tự | Round trip cộng dồn, latency cao | Projection, bulk endpoint và API theo use case |
| Chuyển fan-out tuần tự thành fan-out không giới hạn | Downstream quá tải, tail latency tăng | Concurrency cap và deadline |
| Bỏ mọi field vào response tổng hợp | Payload lớn và memory cao | Projection/field selection |
| Bỏ pagination cho bulk read | Query và response quá lớn | Cursor, max items/bytes |
| Batch không có max wait | Item đầu chờ lâu | Flush theo time/size |
| Chỉ giới hạn số item, không giới hạn bytes | Batch vượt payload/memory limit | Max item count và byte size |
| Batch atomic không phù hợp | Một item lỗi làm cả lô thất bại | Partial result hoặc chia batch |
| Retry toàn batch mù quáng | Duplicate side effect | Idempotency và per-item status |
| Buffer không bounded | Memory tăng vô hạn | Backpressure/admission control |
| Tăng batch size khi consumer nghẽn | Batch chậm hơn và memory lớn hơn | Đo bottleneck, scale/limit theo capacity |
| Nén mọi payload | CPU tăng, payload nhỏ không lợi | Threshold và content-type policy |
| Nén payload đã compressed | Tốn CPU mà ít giảm bytes | Skip compressed media/formats |
| Compression level tối đa | Encode latency/CPU cao | Benchmark level theo use case |
| Bỏ size limit sau decompress | Compression bomb/DoS | Compressed/decompressed limit |
| Không reuse connection | Handshake và setup overhead lặp lại | Keep-alive, channel/pool reuse |
| Gộp batch nhiều tenant không fairness | Noisy neighbor và tenant starvation | Per-tenant quota/queue |
| Dùng metric label là request ID | Cardinality tăng đột biến | Dùng ID trong logs/traces |
| Không đo tail latency | Average đẹp nhưng p99 xấu | Theo dõi p95/p99 và trace critical path |

## 25. Quy trình tối ưu giao tiếp

1. **Chọn user journey:** xác định endpoint/workflow có latency, throughput hoặc cost issue.
2. **Đo baseline:** calls per request, round trips, p95/p99, bytes, CPU, queue age và retry.
3. **Vẽ dependency graph:** synchronous call, fan-out, N+1 và payload transfer.
4. **Loại call không cần thiết:** projection, endpoint theo use case, bulk lookup hoặc cache.
5. **Giới hạn payload:** field selection, pagination, cursor và size limits.
6. **Chọn batching:** atomicity, item/byte limit, flush timeout và failure semantics.
7. **Thiết kế backpressure:** bounded buffer, concurrency, fairness và admission policy.
8. **Chọn compression:** algorithm, level, threshold, client compatibility và security.
9. **Tối ưu connection:** reuse, pooling, multiplexing và deadline/cancellation.
10. **Kiểm thử correctness:** ordering, idempotency, partial failure, retry và tenant isolation.
11. **Benchmark:** traffic thấp/bình thường/đỉnh/burst; đo latency, throughput, CPU, memory, bytes và cost.
12. **Rollout:** canary, health gate, rollback và quan sát consumer/downstream.
13. **Review:** xác nhận SLO, cost và behavior thực tế sau khi traffic ổn định.

## 26. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Batch có bounded buffer, retry/idempotency và partial-failure handling? Compression/decode có giới hạn? Có thể retry mà không duplicate? |
| **Bảo mật** | Bulk authorization theo từng resource? Payload có PII/secret? Compression có side-channel risk? Decompression có size limit? |
| **Hiệu quả hiệu năng** | Round trips, p95/p99, bytes và CPU được đo? Batch size/flush interval có nằm trong latency budget? Connection được reuse? |
| **Tối ưu chi phí** | Có giảm egress/requests? Compression CPU có đáng với bytes tiết kiệm? Batch có giảm operation cost nhưng tăng memory/idle wait? |
| **Khả năng vận hành** | Có dashboard call amplification, batch wait/size, compression ratio, backlog, retry và owner cho policy? |

### Checklist nghiệm thu

- [ ] Có baseline calls/request, round trips, payload bytes, p95/p99 và resource consumption.
- [ ] Critical path được xác định; call không cần thiết đã được loại bỏ hoặc chuyển bất đồng bộ.
- [ ] API aggregation không tạo distributed monolith/fan-out không giới hạn.
- [ ] Bulk lookup có max items/bytes, pagination và per-item authorization.
- [ ] N+1 pattern được kiểm tra ở API resolver, service và database.
- [ ] Batching có max item count, max bytes và max wait.
- [ ] Atomicity/partial success/order/retry semantics được ghi rõ.
- [ ] Idempotency bảo vệ duplicate khi timeout, retry và redelivery.
- [ ] Buffer bounded, concurrency quota và backpressure được kiểm thử.
- [ ] Compression chỉ bật khi payload/client phù hợp và benchmark chứng minh lợi ích.
- [ ] Có giới hạn compressed/decompressed size và timeout decode.
- [ ] Connection/channel/pool được reuse và có capacity limit.
- [ ] Tenant fairness và isolation được giữ trong batch/bulk API.
- [ ] Structured logs/traces cho biết batch ID/item ID và operation mà không lộ secret.
- [ ] Metrics tránh cardinality cao do ID duy nhất.
- [ ] Canary/rollback và load test gồm traffic thấp, peak và burst.

## 27. Bài tập áp dụng

Một ứng dụng quản lý thuê thiết bị có endpoint dashboard trả 30 booking gần nhất. Client gọi API bookings, sau đó gọi customer, asset và payment riêng cho từng booking. Background worker publish mỗi event dưới dạng một broker request; message JSON có nhiều metadata lặp lại. Khi traffic cao, p99 latency tăng và egress cost vượt dự báo. Consumer thỉnh thoảng xử lý lại message sau timeout.

Hãy thiết kế:

1. Đo gì để xác định latency do round trip, server processing, queueing và payload transfer?
2. Thay N+1 API calls bằng summary/projection hoặc bulk API nào?
3. Pagination/field selection giúp tránh payload quá lớn ra sao?
4. Chọn batch size, max bytes và flush interval cho event producer thế nào?
5. Xử lý partial failure và retry per-item ra sao để không duplicate?
6. Compression algorithm/level nào cần benchmark; trường hợp nào không nên nén?
7. Làm sao giới hạn decompressed size và bảo vệ khỏi payload độc hại?
8. Thiết kế bounded buffer/backpressure khi consumer chậm.
9. Đảm bảo ordering, tenant authorization và fairness trong batch như thế nào?
10. Chỉ số trước/sau nào chứng minh tối ưu cải thiện p99, throughput và cost mà không làm giảm correctness?

Một phương án có cơ sở sẽ dùng summary/read projection để giảm client round trips, bulk lookup có giới hạn cho dữ liệu phụ, producer batching theo item/byte/time threshold, consumer idempotent với per-item status, và compression chỉ cho payload có ratio tốt. Kết quả phải được xác nhận bằng benchmark p95/p99, bytes/event, CPU, queue age, duplicate rate và egress cost.

**Điểm cốt lõi:** giảm số lần giao tiếp hạn chế round-trip và call amplification; batching phân bổ fixed overhead trên nhiều item nhưng cần giới hạn size, wait và failure scope; compression giảm bytes nhưng tiêu tốn CPU và phải có size guardrail. Chỉ tối ưu khi đo được lợi ích end-to-end và chứng minh ordering, idempotency, security, tenant isolation cùng SLO vẫn được giữ nguyên.
