# Thiết kế thử nghiệm khả thi với dữ liệu/tải đại diện

Một nhóm phát triển muốn chọn cơ sở dữ liệu NoSQL cho hệ thống đặt hàng. Họ chạy 10.000 lần ghi một document nhỏ, thấy cơ sở dữ liệu X đạt 40.000 thao tác/giây và Y đạt 30.000 thao tác/giây, rồi quyết định chọn X. Sau khi lên production, truy vấn xem lịch sử đơn hàng của khách chậm, các tenant lớn làm nóng một số partition, TTL/delete tạo lượng tombstone lớn, còn một lần mất node khiến ứng dụng retry quá nhiều và vượt SLO.

Vấn đề không nằm ở chỗ con số QPS đã đo là “giả”; vấn đề là thử nghiệm đã **không đại diện cho công việc mà hệ thống thực sự phải làm**. Một thử nghiệm khả thi (proof of concept, PoC; hoặc proof of value, PoV khi nhấn mạnh giá trị thực tế) chỉ hữu ích nếu nó kiểm chứng được các giả thuyết và rủi ro quan trọng để ra quyết định.

Bài học thuộc chương **Đánh giá và lựa chọn** của module **Database No SQL**. Nội dung hướng dẫn cách thiết kế PoC có dữ liệu và tải đại diện, xác định tiêu chí chấp nhận, giữ công bằng giữa ứng viên, đo tính đúng đắn cùng hiệu năng, ước lượng chi phí và chuyển kết quả thành một quyết định kỹ thuật có bằng chứng.

> **Nguyên tắc:** Không lựa chọn NoSQL dựa vào “benchmark đẹp nhất”. Hãy lựa chọn dựa vào khả năng đáp ứng **đúng access pattern, đúng dữ liệu, đúng cam kết nhất quán, dưới tải và sự cố gần với thực tế**, với chi phí và rủi ro chấp nhận được.

Các mức tải, dữ liệu, API và sản phẩm trong ví dụ là giả định để học. Kết luận phải được xác minh theo phiên bản, cấu hình, vùng triển khai, giá dịch vụ, topology và ứng dụng thực tế. Các mã ví dụ là thành phần minh họa phương pháp, không phải bộ framework benchmark đầy đủ có thể dùng nguyên xi cho production.

## 1. PoC, benchmark, pilot và production rollout khác nhau thế nào?

| Hoạt động | Mục tiêu | Đầu ra |
|---|---|---|
| **Spike/technical exploration** | Tìm hiểu API và giả định kỹ thuật chưa rõ | Prototype, ghi chú rủi ro |
| **PoC khả thi** | Kiểm chứng các yêu cầu/hypothesis quan trọng | Evidence cho GO/NO-GO |
| **Benchmark** | Đo một hoặc nhiều khía cạnh hiệu năng có phương pháp | Latency, throughput, cost, resource metrics |
| **PoV** | Kiểm tra giá trị tổng thể so với chi phí/rủi ro | Khuyến nghị kinh tế-kỹ thuật |
| **Pilot** | Đưa một phần tải/người dùng thật vào vận hành có kiểm soát | Tín hiệu vận hành thực tế, rollout gates |
| **Production rollout** | Thay đổi hệ thống đang phục vụ | Runbook, migration, monitoring, recovery |

Benchmark là **một thành phần** của PoC, không thay toàn bộ PoC. Ngược lại, một ứng dụng demo thao tác CRUD chạy được chưa chứng minh khả năng chịu tải, bảo đảm durability, phân quyền hoặc restore.

### 1.1. Câu hỏi quyết định phải xuất hiện trước khi thử

Thay vì hỏi:

> “MongoDB hay Cassandra nhanh hơn?”

Hãy hỏi:

> “Trong cấu trúc đơn hàng của chúng tôi, ứng viên nào giữ được p99 API đọc/ghi, độ tươi dữ liệu, bất biến đặt hàng, khả năng phục hồi khi mất một AZ và chi phí tổng dưới các ngưỡng được xác định khi lưu lượng tăng 3 lần?”

Câu hỏi thứ hai tạo ra một phép thử có thể **bác bỏ giả thuyết**, với các kết quả đo cần thu thập.

## 2. Bắt đầu bằng business scenario, không bằng tên sản phẩm

Một bảng mapping đầu tiên:

| Nghiệp vụ | Đường dữ liệu | Hệ quả cho PoC |
|---|---|---|
| Tạo Order | Conditional stock reserve + Order + outbox | Kiểm tra atomicity/idempotency, contention và commit |
| Xem Order của khách | Lookup theo tenant/customer, sort thời gian | Composite key, pagination, p99 và index |
| Xem chi tiết sản phẩm | Key lookup, read-heavy | Cache hit/miss, hot product và latency |
| Tìm kiếm | Text/filter/rank | Search index, cập nhật dữ liệu và freshness |
| Theo dõi sự kiện | Append event, time-range query | Write throughput, retention, partitioning |
| Chạy báo cáo | Tổng hợp dài, scan phạm vi lớn | Read amplification hoặc separate read model |
| Xóa dữ liệu theo quyền riêng tư | Delete/tombstone/TTL | Correctness, lag và retention |
| Khôi phục khi lỗi | Backup/PITR, replica/region failover | RPO/RTO, unknown writes và resync |

PoC nên ưu tiên những yêu cầu có **tác động kinh doanh cao, rủi ro cao, hoặc chưa được chứng minh**. Không cần triển khai mọi endpoint ít quan trọng để kết luận về một kiến trúc.

## 3. Phân biệt hard gate, mục tiêu SLO và ưu tiên mềm

### 3.1. Hard gate: vi phạm là NO-GO

Ví dụ:

- Không hỗ trợ mức atomic conditional update cần để ngăn bán quá số lượng mà không có giải pháp khả thi.
- Không đáp ứng data residency/quy định lưu trữ bắt buộc.
- Không có cách quản lý quyền tenant/identity theo chính sách.
- Không có backup/restore đáp ứng giới hạn RPO/RTO bắt buộc.
- Không có tính năng, chính sách license hoặc API được phép sử dụng.
- Không thể triển khai topology đáp ứng failure-domain availability yêu cầu.
- Không thể thực hiện thao tác xóa/retention theo nghĩa vụ nghiệp vụ.

Ứng viên vượt trội throughput vẫn phải bị loại nếu **vi phạm hard gate**.

### 3.2. SLO/SLA và tiêu chí đo được

Ví dụ giả định:

| SLI | Mục tiêu được chọn cho PoC |
|---|---|
| Checkout p99 | Không quá 350 ms ở peak |
| Order detail p99 | Không quá 180 ms ở peak |
| Business correctness | 0 acknowledged intent bị mất; 0 duplicate charge |
| Search freshness p99 | Không quá 10 giây |
| Monthly restore drill | Hoàn thành trong RTO 60 phút |
| Availability under one-node fault | Degraded window trong error budget |
| Tenant isolation | Không truy cập chéo tenant |
| Peak load | 3× normal traffic trong 15 phút |

Đây chỉ là **ngưỡng minh họa**; PoC thực phải lấy từ business SLO và capacity plan. Kết quả ghi rõ workload, dataset, engine, config và thời điểm đo.

### 3.3. Soft criteria

Có thể gồm chi phí hạ tầng, developer productivity, khả năng vận hành, khả năng tuyển người, ecosystem/driver maturity, portability và độ phức tạp migration. Các tiêu chí mềm chỉ nên so sánh **sau khi hard gates đạt**, không dùng điểm mạnh này để che một lỗi dữ liệu nghiêm trọng.

## 4. Viết giả thuyết có khả năng bị bác bỏ

Một hypothesis tốt có dạng:

> “Với 80 triệu Order, 15% khách tạo 70% lượt đọc và ba tenant lớn chiếm 60% lưu lượng ghi, schema theo tenant–customer–createdAt của ứng viên A sẽ giữ Order-list p99 dưới 180 ms tại 2.000 reads/s, với không quá 1% throttled requests.”

Không nên dùng câu mơ hồ như “cơ sở dữ liệu A scale tốt”.

Mỗi giả thuyết ghi:

- **Điều kiện đầu vào:** dataset/version/topology/tải.
- **Kỳ vọng:** metric, ngưỡng, confidence và observation window.
- **Cơ chế có thể gây thất bại:** hot partition, index miss, replica lag.
- **Cách đo:** client, driver, server và data oracle.
- **Quy tắc quyết định:** PASS, FAIL hoặc INCONCLUSIVE.
- **Bước tiếp:** remediation/retest hoặc loại ứng viên.

PoC có thể có một bảng hypothesis registry thay vì thu thập hàng trăm biểu đồ mà không liên hệ quyết định.

## 5. Representative data không chỉ là “số document gần giống”

Một tập dữ liệu đại diện cần phản ánh nhiều chiều:

| Chiều | Vì sao quan trọng |
|---|---|
| Số records/bytes | Ảnh hưởng storage, indexes, cache, compaction |
| Kích thước mỗi record | Network/CPU/serialization, tail latency |
| Độ sâu/cấu trúc document | Query projection, nested indexes, update cost |
| Key cardinality | Partition distribution và index selectivity |
| Skew/hot keys | Một số khóa chịu quá nhiều requests |
| Tenant distribution | Một tenant lớn có thể chi phối tài nguyên |
| Time distribution | Các record mới được đọc/ghi nhiều hơn |
| Record lifecycle | Insert/update/delete/TTL, tombstones |
| Index coverage | Working set và write amplification |
| Relationship graph | Fan-out, JOIN trong application, denormalization |
| Type/encoding | Decimal, int64, binary, null/missing, collation |
| Data compression | Disk, CPU, egress và restore time |
| Value distributions | Query selectivity, filter/sort cardinality |

**Một triệu documents có cùng kích thước và các khóa sinh ngẫu nhiên đều không đại diện** cho 100 triệu đơn hàng có tập khách hoạt động rất không đều, phần lớn traffic nhắm vào dữ liệu mới.

## 6. Lấy dữ liệu đại diện mà không gây rủi ro bảo mật

Có ba hướng:

1. **Synthetic dataset có cấu trúc và phân phối dựa trên số đo thực tế.** Thường an toàn nhất để lặp test và chia sẻ.
2. **Đã ẩn danh/biến đổi từ dữ liệu production** theo chính sách, nhưng phải đánh giá nguy cơ tái định danh, keys, free text và liên kết giữa bảng.
3. **Sampling từ nguồn thật trong môi trường được phê duyệt**, chỉ khi phù hợp privacy/security; cần bảo vệ dữ liệu, quyền, logs và retention.

Synthetic data cần giữ **phân phối**, không nhất thiết giữ raw PII. Có thể thay email bằng ID giả, tên bằng chuỗi nhân tạo, số tiền theo khoảng thực tế nhưng không giữ giá trị nhận diện. Đừng coi hash đơn giản của email/phone là bảo đảm ẩn danh: có thể bị đảo bằng dictionary hoặc liên kết qua metadata.

### 6.1. Mẫu lấy dữ liệu dễ gây thiên lệch

- Chỉ lấy 10.000 bản ghi mới nhất → đánh giá sai độ sâu lịch sử.
- Chỉ lấy ngẫu nhiên theo row → bỏ qua những tenants rất lớn/nhỏ.
- Chỉ lấy active records → bỏ qua tombstones/expired records.
- Chỉ lấy các document nhỏ → đánh giá thấp disk/network/GC tail.
- Chỉ lấy IDs có phân phối đều → làm mất hot partition thật.
- Chỉ xuất dữ liệu đã clean → không kiểm tra malformed/legacy schema.
- Chỉ dựng 1% records → index/cache có thể nằm hoàn toàn trong RAM dù production thì không.

Hãy dùng **stratified sampling** theo tenant, tuổi bản ghi, kích thước và hot-key frequency, rồi xác nhận phân phối đầu vào bằng profile số đo đã được phép dùng.

## 7. Ước lượng working set, không chỉ total storage

Giả sử 100 triệu records chiếm 1 TiB trên disk, nhưng phần lớn requests đọc 8 triệu records mới nhất cùng indexes chiếm khoảng 140 GiB. Nếu PoC chỉ tạo 5 GiB data, toàn bộ dữ liệu vừa RAM và latency sẽ đẹp hơn production.

Cần quan tâm:

- **Total logical data:** tổng bytes trước storage overhead.
- **Physical storage:** compression, replicas, indexes, logs, metadata.
- **Hot working set:** pages/index data được truy cập thường xuyên.
- **Cache budget:** RAM dành cho cache sau OS, process, buffers, heap.
- **Cold data access:** truy cập dữ liệu lâu đời/ít dùng.
- **Growth:** data và index tăng theo retention policy.

Một phép thử cần cân nhắc **dataset scale gần working-set/physical ratio của hệ đích**. Nếu chỉ chạy bản nhỏ, ghi rõ giới hạn ngoại suy.

## 8. Phân phối khóa và hiện tượng điểm nóng

NoSQL partitioning có thể phản ứng rất khác với các kiểu khóa:

- **Uniform:** mỗi key gần xác suất bằng nhau.
- **Zipf-like:** một số key được truy cập nhiều hơn đa số.
- **Time-correlated:** writes dồn vào bucket hiện tại.
- **Sequential IDs:** có thể tạo hot range ở những storage/routing models nhất định.
- **Tenant-skewed:** vài tenants lớn.
- **Event bursts:** một SKU/sản phẩm trở thành hot trong chiến dịch.

Ví dụ:

~~~text
Uniform test:
  1,000,000 keys, each receives roughly similar load.

Production-like:
  Top 1% of product keys receive 45% reads.
  One tenant produces 30% of writes.
  80% order lookups target last 7 days.
  A flash-sale SKU receives 3,000 concurrent reservation attempts.
~~~

PoC không nên chỉ đo QPS đều: hot key có thể bị giới hạn bởi một logical item/partition hoặc lock contention dù tổng cluster CPU thấp.

## 9. Dữ liệu có đời sống: update, delete, TTL và backfill

Một thử nghiệm chỉ insert mới bỏ qua:

- Update nhiều lần lên cùng document.
- Partial update vs replace.
- Deletes, soft deletes, tombstones.
- TTL/expiry, background cleanup và compaction.
- CDC/outbox/consumer lag.
- Index build và schema evolution.
- Batch import/backfill.
- Truy vấn dữ liệu vừa hết hạn hoặc vừa cập nhật.
- Growth của storage/index/commitlog theo thời gian.

Nếu TTL 90 ngày nhưng PoC chạy 30 phút, chưa thể suy chi phí tombstone cleanup/compaction dưới tải thật. Có thể **pre-seed dữ liệu đã có tuổi**, dùng khoảng TTL thử nghiệm phù hợp và quan sát background behavior, nhưng phải ghi rõ sự khác biệt với production.

## 10. Multi-tenant workload và noisy neighbor

Trong SaaS, trung bình 2.000 requests/s có thể che giấu một tenant chiếm hơn một nửa lưu lượng trong khi hàng nghìn tenant còn lại dùng rất ít.

PoC nên thử:

- **Tenant lớn:** data và traffic cao, có bursts.
- **Tenant trung bình:** access pattern phổ biến.
- **Tenant nhỏ:** nhiều tenant chia sẻ nguồn lực.
- **Noisy neighbor:** một tenant gây hot partition, throttling hoặc GC pressure.

Câu hỏi: tenant lớn có khiến p99 của tenant nhỏ vượt SLO? Có quotas/circuit breaker/per-tenant concurrency không? Partition key có tạo tập dữ liệu quá lớn cho một tenant? Các truy vấn toàn tenant cần fan-out? Tenant deletion/restore có cô lập không?

**Fairness và tenant isolation là yêu cầu khả thi**, không chỉ là tối ưu performance.

## 11. Access-pattern catalog có tần suất và yêu cầu

Mỗi operation quan trọng cần một đặc tả:

| Thuộc tính | Ví dụ |
|---|---|
| Operation | `ListOrdersByCustomer` |
| Input | tenantId, customerId, cursor, pageSize |
| Output | 20–50 Order summaries/page, sort time descending |
| Normal/peak rate | 800/2.400 requests/s |
| High-cardinality group | Một customer có 50.000 Orders |
| Consistency | Read-your-writes cho Order mới |
| SLO | p99 ≤ 180 ms |
| Time locality | 80% requests truy cập 7 ngày mới |
| Authorization | Tenant-scoped/customer owner |
| Failure | Retry không bỏ/trùng trang |

Đồng thời ghi GET-by-ID, range, update, delete, aggregation, scan, search và cross-partition operations mà ứng dụng thực sự thực hiện. Một benchmark lặp cùng một key chỉ đo cache hit; không đo phân phối IDs đa dạng.

## 12. Thiết kế workload mix theo nghiệp vụ

Ví dụ một ứng dụng bán hàng:

| Operation | Normal (%) | Peak (%) | P99 mục tiêu |
|---|---:|---:|---:|
| GetProduct | 28 | 35 | 70 ms |
| ListOrdersByCustomer | 18 | 12 | 180 ms |
| CreateOrder | 10 | 14 | 350 ms |
| ReserveStockConditional | 12 | 18 | 200 ms |
| UpdateOrderStatus | 12 | 8 | 200 ms |
| SearchCatalog | 12 | 8 | 500 ms |
| ReportingAggregation | 5 | 3 | 3 s |
| Delete/TTL-related | 3 | 2 | Theo contract |
| **Tổng** | **100** | **100** | |

Nếu ứng viên A được dùng cache và search riêng, còn ứng viên B phải chạy cả search/analytics trên database giao dịch, đó không phải so sánh đồng dạng nếu không ghi rõ **kiến trúc, chi phí và đường request**.

Một user journey cần quan hệ nhân quả:

~~~text
Browse product
 -> Reserve stock with condition
 -> Create Order + outbox
 -> Immediately GET Order
 -> Update status later
 -> Search projection catches up
~~~

PoC đo cả **end-to-end business latency** và từng database operation. GET sau POST không thể bị xem là đúng nếu trả 404 stale khi API đã cam kết read-your-writes.

## 13. Các query shapes cần thử

- **Point lookup:** theo key đầy đủ.
- **Range scan:** theo thời gian, token/range, pagination.
- **Compound filter + sort:** phải có index hợp lý.
- **Secondary-index lookup:** có read benefit nhưng write/storage cost.
- **Nested document query:** array/object và projection.
- **Aggregations:** sum/count/group/distinct, fan-out.
- **Full-text/search/geo/vector:** nếu là use case thật, có thể cần engine phụ.
- **Graph traversal:** multi-hop, relationship-based reads.
- **Cross-partition operations:** transaction/consistency và contention.
- **Read merge:** tổng hợp nhiều buckets/shards với stable ordering.

Một PoC chỉ đo point lookup không giúp quyết định cho hệ cần lấy 20 Orders mới nhất qua 32 time buckets. Phải tính query plan, fan-out, bytes transferred, CPU merge và correctness của top-K.

## 14. Các write patterns cần thử

| Write | Rủi ro |
|---|---|
| Insert unique key | Collision, index amplification, throttling |
| Partial update | Atomicity, lost update |
| Replace document | Overwrite khi concurrent writes |
| Conditional write/CAS | Conflict retries và serial contention |
| Append event | Hot partition, time bucket growth |
| Increment counter | Non-idempotent retries |
| Batch write | Partial success và unprocessed entries |
| Multi-item transaction | Commit p99, limits, conflicts |
| Delete/TTL | Tombstones, cleanup, visibility |
| Upsert | Version constraints, duplicate intents |

Với đặt hàng, 100.000 writes/s không quan trọng nếu hệ **không thể bảo vệ stock >= 0**. Phải tạo concurrency vào cùng SKU/partition và verify bất biến bằng dữ liệu cuối.

## 15. Offered load, completed load và concurrency

Các thuật ngữ:

- **Offered arrival rate:** requests/s generator muốn gửi.
- **Completed throughput:** requests/s hoàn thành.
- **Concurrency:** số requests còn đang xử lý/chờ.
- **Latency:** thời gian từ lịch đến response/error/timeout.
- **Queue time:** chờ thread, pool, network, server.

Ví dụ một giây:

~~~text
Offered:       4,000 requests/s
Success:       3,100 requests/s
Timeout:         850 requests/s
Rejected:         50 requests/s
~~~

Với phép đo thực, cần cùng cửa sổ và tính cả requests đang bay; không suy tổng luôn bằng offered ở mọi khoảng thời gian. Báo cáo chỉ 3.100 successful throughput rồi bỏ 900 lỗi sẽ đánh lừa lựa chọn.

### 15.1. Dùng định luật Little có điều kiện

Ở trạng thái ổn định:

\[
L=\lambda W
\]

`L` là số việc trung bình trong hệ, `λ` là throughput trung bình và `W` là thời gian trung bình. Nếu 2.000 requests/s, average response time 50 ms thì average concurrency khoảng 100 requests.

Đây là quan hệ **trung bình trong steady state**, không phải công thức xác định p99 hoặc số connections luôn đủ. Nếu arrival rate vượt service rate, queue tăng và hệ không còn ổn định.

## 16. Open-loop, closed-loop và coordinated omission

**Closed-loop:** mỗi virtual user đợi request hoàn thành rồi gửi tiếp; khi DB chậm, offered load thường tự giảm.

**Open-loop:** requests được lên lịch theo arrival rate, có bounded queue và safety limits. Nó giúp nhìn rõ saturation nhưng cũng có thể gây overload nếu kiểm soát kém.

~~~text
Closed-loop:
  100 users send -> wait -> next
  Slower server -> fewer arrivals.

Open-loop:
  2,000 arrivals/s
  Slower server -> backlog and timeouts rise.
~~~

PoC nên dùng cả hai khi thích hợp: closed-loop cho journeys, open-loop cho capacity/peak. Ghi scheduled start và actual result, không chỉ latency của requests thành công.

**Coordinated omission**: nếu load generator chờ mỗi request chậm rồi mới gửi tiếp, outage không tạo nhiều request samples, dẫn đến p99 bị đo thấp. Cần ghi offered/completed rates, timeouts, error budget, scheduled latency và phân phối success-only với chú thích rõ.

## 17. Tải theo thời gian và burst

Real traffic có chu kỳ theo giờ/ngày và thay đổi đột ngột:

- Flash sale 3× normal peak.
- Batch import/ETL ở giờ thấp điểm.
- Hàng nghìn clients reconnect sau deploy.
- Cache miss storm khi cache bị flush.
- Daily TTL/compaction/backup jobs.
- Một tenant upload nhiều tài liệu.
- Retry storm sau network hiccup.

Một time-profile giả định:

~~~text
00-05 min: warm-up at 30% peak
05-20 min: normal traffic 60%
20-35 min: sustained peak 100%
35-40 min: burst 300%
40-55 min: back to 100%, observe recovery
55-85 min: soak at 70%, background jobs active
~~~

Một burst 3× dài 30 giây khác 3× dài 45 phút. Dùng dữ liệu lịch sử/forecast hoặc ít nhất nêu giả định để xác định **burst length, arrival shape và recovery window**.

## 18. Tương quan giữa các thao tác

Các request không xuất hiện ngẫu nhiên độc lập:

- Một khách xem nhiều sản phẩm trước khi đặt hàng.
- Một số SKU cùng xuất hiện trong nhiều giỏ.
- Customer tạo nhiều orders cùng lúc.
- Tenant lớn import records rồi query ngay.
- Payment webhook cập nhật trạng thái sau vài giây.
- CDC/search projection trễ so với source.
- Privacy deletion xảy ra theo nhóm hoặc lifecycle.

Một simulator có thể dùng state machine:

~~~mermaid
flowchart TD
    A["Browse"] --> B{"Add to cart?"}
    B -->|Yes| C["Reserve stock"]
    B -->|No| A
    C --> D["Create Order"]
    D --> E["GET Order immediately"]
    E --> F["Fulfil and update later"]
    F --> G["Search/report projection"]
~~~

Mỗi bước có dependencies, expected status, deadlines và assertions. **Random GET/PUT độc lập** không mô phỏng contention, retries hoặc read-after-write của một hành trình thật.

## 19. So sánh công bằng: cùng contract, không nhất thiết cùng câu lệnh

Hai NoSQL engines có thể có mặc định khác nhau về replication, durability, consistency, compression, cache và logging. So các defaults mà không ghi contract có thể ưu ái hệ **trả ACK với bảo đảm yếu hơn**.

Cần cố định/giải thích:

| Yếu tố | Điều phải ghi |
|---|---|
| Dataset | Cùng seed, kích thước và phân phối |
| Business operations | Cùng input, output, correctness assertions |
| Durability | ACK có nghĩa gì trong fault model |
| Read consistency | Freshness, read-your-writes tương đương |
| Index support | Query trả kết quả đúng và không full scan nguy hiểm |
| Topology | Replicas, zones, network hops tương ứng |
| Driver | Versions, pools, retries, serialization |
| Security | TLS/auth/encryption theo cùng chính sách |
| Infrastructure | Resource allocation, storage/IOPS/region |
| Warm-up | Cache state và background jobs |
| Dependencies | Cache/search/CDC/queue phụ trợ đã tính chi phí chưa |
| Cost | Compute, storage, network, backup, license và vận hành |

**Công bằng không đồng nghĩa ép mọi engine có cùng partition key hoặc schema.** Document, wide-column và key-value stores có cách model dữ liệu khác nhau. Nên để mỗi ứng viên dùng **thiết kế hợp lý theo thế mạnh của nó** để phục vụ cùng nghiệp vụ, và công bố chi phí/độ phức tạp thêm.

## 20. So ở cùng tài nguyên và ở cùng ngân sách SLO

Hai loại thí nghiệm bổ sung:

1. **Fixed resources:** dùng mức CPU/RAM/IOPS/network được chuẩn hóa để đo hiệu quả và bottleneck.
2. **Fixed SLO/functional contract:** cho phép mỗi engine scale/tune để đạt yêu cầu; so chi phí và độ phức tạp cần bỏ ra.

Ví dụ candidate A cần 3 nodes, B cần 5 nodes. Nếu mỗi node A đắt hơn B, compute bill có thể tương đương; nhưng network egress, backup, multi-AZ replication và on-call hours còn khác.

Không nên chỉ so 3 nodes của hai hệ rồi kết luận B không khả thi nếu engine B cần topology khuyến nghị khác. Nhưng cũng không nên cho B thêm 10 nodes mà không tính chi phí. Báo cáo nên có **performance per resource** và **cost to meet SLO**.

## 21. Các yếu tố nhiễu trong benchmark

- VM shares CPU với tác vụ không liên quan.
- Kubernetes CPU throttling hoặc pod reschedule.
- Burst credits của disk/cloud quota.
- Warm cache không giống nhau.
- Một hệ đang compaction/repair/backup, hệ kia không.
- Thời gian autoscaling khác nhau.
- Driver pool hoặc JVM/JIT chưa warm-up.
- Index đang build ở một candidate.
- Network hops khác vùng/AZ.
- Dataset version/seed khác.
- Thay cấu hình mid-run nhưng không ghi audit.

Thực hành:

1. Ghi environment/config fingerprint.
2. Dùng môi trường đủ cô lập để giảm nhiễu.
3. Warm-up như nhau hoặc có cold-start test riêng.
4. Chạy lặp nhiều lần và đổi thứ tự A/B khi hợp lý.
5. Đo variation, không chỉ chọn run nhanh nhất.
6. Ghi background events, GC, autoscaling.
7. Phân loại infrastructure anomaly và run inconclusive.
8. Không xóa kết quả xấu không có lý do từ báo cáo.

Một PoC không cần phòng thí nghiệm tuyệt đối, nhưng phải **tái lập được setup và dữ liệu đo**.

## 22. Topology phải gần production

Production dự kiến ba AZ với replicas, API TLS, outbox và backup; PoC single-node cùng VM với load generator sẽ không phản ánh quorum/network/replication cost.

Ví dụ:

~~~text
Region R1:
  AZ-1: DB replica 1
  AZ-2: DB replica 2
  AZ-3: DB replica 3

Application:
  API pods across AZs
  real driver pooling and TLS

Supporting:
  metrics/logging, backup, CDC/search
~~~

Nên định nghĩa:

- Replication factor/voting members/data placement.
- Read/write consistency/durability mode.
- Disk tier, IO limits, memory và NIC.
- App driver/client count và location.
- Network hops/AZ latency.
- Backup/compaction/index/CDC overhead.
- Provider quotas và autoscaling.

Single-node microbenchmark vẫn có ích cho debugging, nhưng **không dùng làm quyết định production HA**.

## 23. Data model của từng ứng viên là thành phần PoC

Một domain Order có thể biểu diễn:

- Document với embedded OrderItems.
- Hai collections Orders/OrderItems có index thích hợp.
- Wide-column partition theo tenant/customer, sort theo time.
- Key-value point record và secondary read projection.
- Separate search index cho full text.
- Time buckets, shard key salt cho hot write streams.

Với mỗi ứng viên cần:

1. Partition/key strategy và cardinality.
2. Index/query plan cho top access patterns.
3. Transaction/conditional-write model.
4. Denormalization và write fan-out.
5. TTL/tombstones/retention.
6. Tenant/auth boundaries.
7. Backup, CDC, restore/migration plan.
8. Growth và hot-key mitigation.

Một ứng viên thua vì schema PoC được thiết kế kém không đủ bằng chứng engine kém. Lưu ADR cho lựa chọn schema, những trade-off và việc tune đã làm.

## 24. Kiểm tra query plan thay vì chỉ nhìn kết quả đúng

Một truy vấn list orders:

~~~text
Input: tenant=t01, customer=c19, pageSize=20
Output: 20 newest Orders, stable tie-breaker
SLO: p99 <= 180ms at peak
~~~

Nếu hệ scan 1 triệu Orders rồi sort trong ứng dụng, nó có thể nhanh trên 1.000 records nhưng không mở rộng được.

Cần ghi:

- Query/explain plan hoặc equivalent.
- Rows scanned vs returned.
- Read units, bytes và round trips.
- Index coverage, write amplification.
- Number of partitions/shards touched.
- Client merge/sort CPU và memory.
- Pagination semantics khi concurrent writes.
- Cold-cache và warm-cache p99.

**Một query chạy được chưa chắc phù hợp production**, đặc biệt nếu chỉ nhanh nhờ dữ liệu nhỏ vừa hết trong RAM.

## 25. Denormalization làm tăng chi phí và độ trễ hội tụ

Một Order được lưu ở nhiều read models:

~~~text
ordersById/O1
ordersByCustomer/t01-c19/...
ordersByStatus/t01-PENDING/...
searchIndex/O1
~~~

Khi Order chuyển PENDING → CONFIRMED, hệ có thể phải:

- Ghi source Order.
- Cập nhật view theo khách.
- Xóa entry trạng thái PENDING, thêm entry CONFIRMED.
- Phát outbox event và cập nhật search.
- Invalid cache.
- Xử lý retries, duplicate events, TTL và delayed updates.

PoC nên tính **tổng số writes và bytes** do một business operation gây ra, chứ không chỉ một primitive write. Khi failure xảy ra giữa các projections, business read contract có còn giữ?

Một engine có native index có thể đổi write/storage cost để giảm application complexity; một engine khác cần custom projection/CDC. Phải tính cả hai vào solution TCO.

## 26. Data generator tái lập bằng seed và manifest

Một manifest minh họa:

~~~yaml
dataset:
  seed: 20261114
  domain: commerce-orders
  tenants: 2000
  customers: 1500000
  products: 400000
  orders: 80000000
  avgItemsPerOrder: 3.2
  sizes:
    smallPercent: 70
    mediumPercent: 25
    largePercent: 5
  skew:
    topOnePercentProductsReadShare: 45
    topTenantsWriteShare: 60
  recency:
    lastSevenDaysReadShare: 80
  retention:
    days: 90
    includeExpiredAndTombstoneStates: true
  numericPrecision: exact-integer-minor-units
  noRealPersonalData: true
~~~

Đây là mô hình mô tả, không phải format của một tool cụ thể. Dự án thật cần:

- Generator version và fixed random seed.
- Logical/physical bytes, counts, indexes, compression.
- Phân phối record sizes/keys/ages sau tạo.
- Stable business IDs để đối soát.
- Có thể dùng nhiều seeds để đo độ nhạy, nhưng báo run tương ứng.
- Tách dữ liệu synthetic khỏi production PII.
- Phần backfill/index build tính vào initial load time.

Một dataset lớn nhưng uniform không trở thành “đại diện” chỉ nhờ số record.

## 27. Test oracle độc lập với ứng viên

Một **oracle** mô tả kết quả đúng:

- Mọi Order được ACK có thể đọc lại theo consistency contract.
- Một idempotency key không tạo hai effects.
- Stock luôn không âm.
- Tổng tiền OrderItems khớp tổng tiền Order theo integer minor units.
- Không truy cập dữ liệu tenant khác.
- Privacy delete được áp sau event replay.
- Pagination không mất/trùng records theo snapshot semantics đã công bố.
- Search projections hội tụ trong freshness window.
- TTL/retention không giữ dữ liệu ngoài policy.

Nếu cùng một lỗi nằm trong generator, hai ứng viên có thể cùng xuất kết quả sai. Oracle nên dùng **expected business facts** đã tạo và lưu riêng, assertions tại nguồn authoritative, không dựa độc nhất vào việc hai database trả kết quả giống nhau.

## 28. Consistency/durability thuộc tiêu chí chấp nhận

| Operation | Contract | Test |
|---|---|---|
| Reserve last unit | Conditional atomic business invariant | 100 concurrent intents, no oversell |
| Create Order | Durable ACK theo policy | Failover after ACK, no lost acknowledged Order |
| Read own Order | Read-your-writes | GET immediately after write ACK |
| Catalog browse | Bounded eventual staleness | Distribution of source→visible lag |
| Permission revoke | Security freshness policy | Deny revoked identity as contract requires |
| Analytics report | Snapshot/historical semantics | Stable counts and cutoff |
| Privacy delete | Propagation and suppression policy | Deletion not resurrected after replay |

Không dùng tên “strong”/“eventual” một cách trừu tượng. Phải ghi rõ **phạm vi key/partition/transaction/index/region**, loại failure và expected visibility.

## 29. Java: mô hình workload dưới dạng business intents

Ví dụ dùng Java records và interface nhằm minh họa cách tách ý định khỏi lần gửi; chưa có adapter engine cụ thể:

~~~java
import java.time.Instant;

public enum Operation {
    GET_PRODUCT,
    LIST_ORDERS,
    CREATE_ORDER,
    RESERVE_STOCK,
    UPDATE_STATUS,
    DELETE_CUSTOMER
}

public record WorkloadIntent(
    String operationId,
    String tenantId,
    Operation operation,
    String targetKey,
    long expectedVersion,
    Instant scheduledAt
) {}

public enum Outcome {
    ACKNOWLEDGED, BUSINESS_REJECTED, UNKNOWN, ERROR
}

public record AttemptTrace(
    String operationId,
    int attempt,
    Outcome outcome,
    long latencyNanos,
    String errorClass
) {}

public interface NoSqlAdapter {
    AttemptTrace execute(WorkloadIntent intent) throws Exception;
}

public interface BusinessOracle {
    void assertFinalState(WorkloadIntent intent) throws Exception;
}
~~~

Tác dụng:

1. `operationId` giữ ổn định qua retry.
2. `tenantId` và `targetKey` tạo phân phối cùng hot keys.
3. `scheduledAt` giúp đo latency từ lúc request được dự định phát.
4. `expectedVersion` hỗ trợ conditional semantics.
5. `Outcome.UNKNOWN` không bị coi nhầm như rejection.
6. `BusinessOracle` độc lập với API success counter.

Adapter mỗi engine có cách encode và query riêng, nhưng phải giữ cùng **logic và contract của operation**.

## 30. Java: generator có skew theo tenant

Mã minh họa đơn giản. Không giả lập chính xác Zipf, chỉ mô phỏng một tenant nóng chiếm xác suất lớn hơn:

~~~java
import java.util.SplittableRandom;

public final class TenantSampler {
    private final SplittableRandom random;
    private final int tenantCount;
    private final int hotTenantCount;
    private final double hotShare;

    public TenantSampler(
            long seed,
            int tenantCount,
            int hotTenantCount,
            double hotShare) {
        if (tenantCount < 1 ||
            hotTenantCount < 1 ||
            hotTenantCount > tenantCount ||
            hotShare < 0.0 || hotShare > 1.0) {
            throw new IllegalArgumentException("Invalid profile");
        }
        this.random = new SplittableRandom(seed);
        this.tenantCount = tenantCount;
        this.hotTenantCount = hotTenantCount;
        this.hotShare = hotShare;
    }

    public String nextTenant() {
        boolean chooseHot =
            random.nextDouble() < hotShare;
        int index;
        if (chooseHot) {
            index = random.nextInt(hotTenantCount);
        } else {
            index = random.nextInt(tenantCount);
        }
        return "tenant-" + index;
    }
}
~~~

**Lưu ý kỹ thuật:** trong mã này, nhóm hot còn có thể được lấy bởi nhánh `else`, nên tổng phần trăm nhóm hot **cao hơn hotShare**. Nếu muốn chính xác `hotShare` cho nhóm hot và phần còn lại cho nhóm cold, nhánh else phải lấy ID từ khoảng `[hotTenantCount, tenantCount)`, với xử lý trường hợp không có cold tenant. Đây là điểm cần nêu rõ khi so profile thực nghiệm; không thể chỉ đặt một tham số tên “45%” và coi phân phối thực đã đúng.

Mã giả giản lược khác để đạt phân phối chính xác theo hai nhóm:

~~~text
if hotTenantCount == tenantCount:
    choose uniformly among all tenants
else if random() < requestedHotGroupShare:
    choose uniformly in [0, hotTenantCount)
else:
    choose uniformly in [hotTenantCount, tenantCount)
~~~

Ở PoC cần đo **empirical histogram** sau sinh dữ liệu. Generator có thể thêm correlations cho customer, hot SKU, time, record sizes và burst.

## 31. Load harness: ghi cả số liệu đầu vào lẫn kết quả

Một record đo:

~~~json
{
  "runId": "nosql-poc-a-r03",
  "candidate": "candidate-A",
  "workload": "mixed-peak",
  "intentId": "op-000019",
  "operation": "CREATE_ORDER",
  "scheduledAt": "2026-11-14T10:00:00.000Z",
  "startedAt": "2026-11-14T10:00:00.004Z",
  "finishedAt": "2026-11-14T10:00:00.118Z",
  "attempts": 2,
  "outcome": "ACKNOWLEDGED",
  "errorClass": null,
  "payloadBytes": 1280,
  "serverRole": "coordinator"
}
~~~

Fields cần dùng để:

- Tính offered vs completed throughput.
- Tính end-to-end latency từ scheduled start và service latency từ actual start.
- Nhìn queue delay.
- Đếm attempts trên mỗi logical intent.
- Phân biệt rejected/timeout/unknown outcomes.
- Correlate với server metrics, config version và injected faults.

Không ghi raw customer PII/credentials hoặc full payment payload vào logs. Với khối lượng lớn, có thể dùng histogram và sampling traces nhưng cần giữ **complete counters/errors** để tránh bỏ qua tail failures.

## 32. Metric suite: latency chỉ là một phần

| Nhóm | Metric |
|---|---|
| End user | p50/p95/p99, success rate, business outcome |
| Workload | Offered/completed ops/s, concurrency, queued/in-flight |
| Retry | Attempts/intent, timeout, throttling, backoff |
| Read | Rows scanned/returned, read units, fan-out, cache hit |
| Write | Write units, conditional conflicts, index updates |
| Storage | Disk bytes/IOPS/latency, compaction backlog, tombstones |
| Runtime | CPU, RSS/heap, GC, page faults, disk saturation |
| Cluster | Replica lag, quorum, election/rebalance/streaming |
| Query | Plan, index coverage, full scan, pagination |
| Consistency | Read-your-writes violations, staleness distribution |
| Correctness | Duplicates, acknowledged writes missing, invariant violations |
| Recovery | RPO/RTO, restore duration, CDC catch-up |
| Cost | Storage, compute, network, requests, backup, operations |

Một dashboard đẹp với p50 thấp nhưng **write conflict/unknown outcome** tăng chưa thể coi là thành công. Báo cáo phải gắn metrics với business intents và hard gates đã định.

## 33. Quy trình chạy PoC nhiều pha thay vì một phép đo duy nhất

Một run có thể chia:

~~~mermaid
flowchart TD
    A["Provision and validate topology"] --> B["Seed representative data"]
    B --> C["Verify schema and distributions"]
    C --> D["Warm-up / cold-start baseline"]
    D --> E["Normal workload"]
    E --> F["Steady peak workload"]
    F --> G["Burst and recovery"]
    G --> H["Long soak + maintenance"]
    H --> I["Fault and scale tests"]
    I --> J["Data reconciliation + restore"]
    J --> K["Collect evidence and decide"]
~~~

Mỗi pha ghi rõ:

- Bắt đầu khi nào, run bao lâu, scope và dataset nào.
- Offered arrival rate/concurrency, operation mix, seed.
- Điều kiện dừng/khởi động lại run.
- Các metrics và evidence cần giữ.
- Cấu hình/topology không được thay lén giữa phép đo.
- Khi nào coi run invalid hoặc inconclusive.
- Cách reset/seed trước run lặp lại.

Một run chỉ có 30 giây tải nhẹ có thể không thấy compaction, GC, autoscaling hoặc cache exhaustion; nhưng soak dài không có business oracle cũng không đủ.

## 34. Warm-up và cold-start phải được đo riêng

Một hệ vừa mới dựng sẽ khác hệ đã chạy một ngày:

- Page cache chưa có hot set.
- JVM/JIT chưa warm nếu app/engine dùng JVM.
- Connection pools chưa đầy.
- Compaction/index build có thể chưa ổn định.
- Managed capacity/autoscaling chưa đạt target.
- Driver DNS/topology discovery có cold-start cost.

Cách làm:

1. **Cold-start test:** đo thời gian từ deploy đến đáp ứng requests và recovery sau restart.
2. **Warm steady-state test:** cho workload ổn định đủ lâu, rồi đo SLO.
3. **Cache flush/test:** chỉ nếu đó là failure scenario được thiết kế, không làm một candidate mất cache khi candidate khác giữ cache.
4. **State record:** lưu cache hit, memory working set, index/compaction trạng thái khi đo.

Không xóa bất lợi cold-start của sản phẩm chỉ bằng warm-up vô hạn, nhưng cũng không so p99 cold A với warm B. Có thể cần cả hai vì production phải chịu deploy/failover.

## 35. Tìm điểm bão hòa một cách có kiểm soát

Một **load staircase** giúp xác định headroom:

~~~text
10% target peak -> stabilize and record.
30% target peak -> stabilize and record.
50% target peak -> stabilize and record.
75% target peak -> stabilize and record.
100% target peak -> stabilize and record.
125% target peak -> if safe.
150% target peak -> if safe.
Beyond -> stop when safety threshold reached.
~~~

Ở từng mức, ghi:

- Offered/completed throughput.
- Success/error/timeout rates.
- p95/p99 latency, queue/pool wait.
- CPU/disk/network saturation.
- Read/write units/throttling.
- Replica lag/GC/compaction.
- Hot partition/tenant fairness.
- Business correctness.

**Saturation point** không nhất thiết là QPS lớn nhất trước khi process chết. Có thể là mức đầu tiên làm p99 vượt SLO, errors tăng, write freshness không đạt hoặc CPU/disk quá ngưỡng an toàn.

### 35.1. Hai dạng đường throughput

~~~text
A) Healthy scaling:
   Offered load ↑ -> completed throughput ↑
   Latency roughly stable until near capacity.

B) Saturation:
   Offered load ↑ -> completed throughput plateaus
   Queue, retries, p99 and timeouts ↑.
~~~

Nếu retries tạo thêm physical work, server QPS có thể tăng dù **business intents/s hoàn tất không tăng**. Tính giá trị trên completed **valid business operations**, không trên số physical DB commands.

## 36. Percentile, sample size và thống kê

Trong workload critical, p99 quan trọng vì phản ánh tail, nhưng:

- p99 của 100 samples gần như chỉ nhìn vài trường hợp cuối.
- p99 của 1 triệu samples ổn định hơn về ước lượng, nhưng vẫn cần cùng workload.
- Các API khác nhau cần p99 riêng, không gộp point read với 3-second report.
- Percentiles không được suy từ trung bình các p99 theo phút để làm “global p99”.
- Cần ghi errors/timeouts song song với latency.
- Độ biến thiên giữa các runs có thể lớn khi cloud noisy.
- Nên quan sát confidence/uncertainty thay vì so hơn kém 2 ms thiếu ý nghĩa.

Báo cáo nên có:

| Metric | Ví dụ |
|---|---|
| Samples | 150.000 completed `CreateOrder` |
| Offered intents | 156.000 |
| Errors/timeouts | 6.000 |
| p50/p95/p99 successful calls | 42/120/310 ms |
| Scheduled-start p99 toàn attempts | Cần tính theo methodology |
| Repeated runs | 5 seeds hoặc 5 runs |
| Range/variation | Phân phối per-run, không chọn một best run |
| Violation count | Số requests vượt deadline/SLO |

Một so sánh “A p99=180 ms, B p99=185 ms” có thể **inconclusive** nếu standard run-to-run noise ±20 ms. Không được đổi kết luận thành chắc chắn chỉ vì một run có số nhỏ hơn.

## 37. Correctness dưới contention: thử nghiệm không phải chỉ đọc số QPS

Ví dụ chỉ còn 1 sản phẩm, 1.000 người cùng nhấn đặt:

~~~text
Initial stock = 1
1,000 unique intent IDs attempt reserve 1.
Expected:
  at most one confirmed reservation
  final stock = 0 if one succeeds
  no duplicate charge per intent
~~~

Test:

1. Đồng bộ start để tạo cạnh tranh.
2. Dùng conditional update/transaction theo engine.
3. Mỗi intent có ID ổn định.
4. Phân loại conflict vs transient timeout.
5. Retry với same ID khi phù hợp, bounded budget.
6. Sau khi hệ ổn, đọc source authoritative.
7. Verify stock, reservations, ledger, outbox.
8. Lặp khi có node failover/packet loss.
9. Đo success rate có điều kiện: không yêu cầu 1.000 đều thành công.
10. Kiểm latency và throughput của những requests đúng.

Một hệ có p99 thấp nhưng ghi hai reservations là **FAIL** về tính đúng đắn.

## 38. Failover/chaos trong PoC: kiểm chứng ngoài steady-state

Candidate phải được thử đúng failure model dự kiến:

- Mất một replica/node ở một AZ.
- Primary/leader step-down khi in-flight writes.
- Network partition làm thay đổi quorum/route.
- Replica lag và read-after-write.
- Driver reconnect khi DNS/topology thay đổi.
- CDC consumer restart/lag.
- Restore backup hoặc failover region theo kế hoạch DR.
- Worker lease hết và retry.
- Cache failover dẫn đến source miss storm.

Trong test nên gắn một tập **known business intent IDs** rồi đối soát sau sự cố:

- Acknowledged writes còn theo durability contract?
- Timeout có được phân loại UNKNOWN thay vì chắc chắn failed?
- Retry có tạo duplicate effects?
- Read-only fallback có làm stale permissions/Orders?
- p99 và availability phục hồi trong bao lâu?
- Replica/CDC hội tụ sau khi node phục hồi?

**Không kill node ngẫu nhiên trên production** chỉ để tạo benchmark. Fault injection phải có authorization, blast radius, cleanup và stop threshold.

## 39. Đo recovery thành nhiều mốc

Ví dụ:

~~~text
T0: Inject node failure.
T1: Leader/quorum reconfigured.
T2: Driver discovers new topology.
T3: First correct new write acknowledged.
T4: API p99/errors return inside SLO.
T5: Replica and CDC lag return to safe levels.
~~~

Đo riêng T1−T0, T2−T0, T3−T0, T4−T0, T5−T0. Việc bầu leader sau 5 giây không chứng minh ứng dụng nhận write đúng sau 5 giây nếu driver còn reconnect hoặc backpressure.

PoC về HA cần đánh giá:

- Time-to-recover-availability.
- Error-budget burn trong fault window.
- Acknowledged-write safety.
- Data freshness và convergence.
- Recovery resource pressure.
- Operator intervention cần thiết.

## 40. Backup/restore và data recovery là một phần quyết định

Một candidate có throughput tốt nhưng restore vài TiB mất nhiều giờ có thể không đạt RTO.

Thử:

1. Tạo full backup ở mức dữ liệu đại diện.
2. Ghi consistency cut, metadata, checksums và key references.
3. Restore vào môi trường cô lập với topology/version phù hợp.
4. Replay logs/PITR nếu yêu cầu.
5. Khôi phục indexes/schema/roles/TTL và các dependencies.
6. Chạy business oracle trên dữ liệu restore.
7. Đo data transfer, index rebuild, replica resync, app cutover.
8. Kiểm decrypt keys và permission ở DR region.
9. Xác minh privacy deletion/suppression sau restore.
10. Báo actual RPO/RTO và uncertainty.

**Backup job SUCCESS không bằng recoverable system.** Một physical snapshot ở một node không tự chứng minh global consistent cluster backup.

## 41. Scale-out, scale-in và rebalance

NoSQL thường được chọn vì khả năng mở rộng, nên PoC không chỉ test một cluster size.

| Trường hợp | Điều cần đo |
|---|---|
| Scale 3 → 6 nodes | Thời gian, data movement, peak p99 và throughput |
| Scale-in 6 → 3 | Chuyển data, availability, safe utilization |
| Thêm hot tenant | Skew, quota, partition split |
| Thay partition/bucket count | Migration/cursor/dual-read costs |
| Một node chết trong rebalance | Recovery và quorum |
| Autoscaling reaction | Thời gian tới capacity mới, hysteresis |
| Thêm GSI/index | Backfill/load và write amplification |
| Schema/data growth 3× | Index/cache/compaction và cost |

Thêm nodes không luôn tăng throughput tuyến tính. Hot key/counter, coordinator bottleneck, network cross-shard và global constraints có thể tiếp tục là điểm nghẽn.

### 41.1. Elasticity có chi phí chuyển trạng thái

Một test chỉ chạy **sau khi scale-out hoàn tất** bỏ qua giai đoạn:

- Bootstrap/streaming data.
- Rebalance/repair.
- Cache cold start.
- Index/replica rebuild.
- Application reconnect.
- Temporary storage/network peak.

Hãy đo **thời gian và chi phí chuyển từ capacity cũ sang capacity mới**, đặc biệt nếu application cần tự phục hồi khi traffic tăng bất ngờ.

## 42. Soak test: chạy đủ lâu để gặp vấn đề chậm

Một soak test vài giờ/ngày (tùy yêu cầu) có thể phát hiện:

- Memory leak/GC degradation.
- Compaction backlog tăng liên tục.
- Disk fragmentation/tombstone bloat.
- Long-running scans pin snapshot versions.
- Connection leaks trong ứng dụng.
- CDC backlog tăng nếu consumer chậm hơn source.
- TTL cleanup bất thường.
- Index/storage growth không như giả định.
- Quota/burst credit cạn.
- Backup/repair va chạm peak load.

Nếu chưa thể chạy lâu, ghi rõ **không kiểm chứng được long-term stability**; có thể mô phỏng data age/compaction và bổ sung pilot production sau, nhưng không dùng soak 10 phút để kết luận chi phí vận hành 2 năm.

## 43. Bảo mật, compliance và quyền truy cập

Các test cần có:

- Tenant isolation ở điểm đọc và ghi.
- RBAC/ACL/IAM theo service identity.
- TLS/mTLS, certificate validation, auth rotation.
- Encryption at rest và KMS recovery.
- Secret storage không đưa token vào log.
- Network segmentation/public endpoint policy.
- Audit logs cho write/delete/export/restore.
- Data residency và cross-region replication controls.
- TTL/deletion/retention, backup privacy suppression.
- Quyền operator vs application, least privilege.

Một candidate không nên được benchmark với TLS/auth tắt rồi dùng số đó làm production expectation nếu hệ thật buộc bật bảo mật. **Bảo mật là cấu hình của workload thực**, không phải bài bổ sung sau khi chọn engine.

## 44. Đánh giá khả năng vận hành, không chỉ API của developer

Một công nghệ có thể viết CRUD nhanh nhưng khó vận hành ở quy mô và SLA mong muốn. PoC nên trả lời:

- Provision/upgrade/rollback cấu hình mất bao lâu?
- Có patch/security update và version compatibility ra sao?
- Replica placement, repair và rebalance cần mức tự động hóa nào?
- Backup/PITR/restore có được diễn tập không?
- Alerts nào chỉ ra hot partition, lag, tombstones, throttling?
- On-call có phân biệt app issue với DB issue không?
- Khi query bị chậm, có explain/trace/slow query logging đủ?
- Có giới hạn managed service quota hoặc request burst không?
- Dữ liệu có thể export/migrate nếu cần rời sản phẩm không?
- Nhà cung cấp hỗ trợ version, region và enterprise feature cần thiết không?
- Đội ngũ hiện tại cần học gì và mất bao lâu để vận hành an toàn?
- Có cách kiểm thử thay đổi cấu hình/driver trong CI/staging không?

**Operational feasibility** gồm số bước xử lý sự cố, rủi ro thủ công, kiến thức đội ngũ và chi phí trực hệ. “Managed” giảm một số trách nhiệm nhưng không xóa trách nhiệm thiết kế key, schema, retries, IAM, backup hoặc SLO của ứng dụng.

## 45. Developer experience và khả năng mô hình hóa đúng

Một PoC có thể để hai nhóm developer thực hiện cùng nhóm nghiệp vụ:

1. Create/Update Order với preconditions.
2. List Orders theo customer/time.
3. Cập nhật status và outbox.
4. Delete/TTL/restore một tập dữ liệu.
5. Thêm một query mới và index tương ứng.
6. Xử lý lỗi transient, unknown commit, idempotency.
7. Test tích hợp bằng SDK chính thức.
8. Viết dashboard/query tracing.

Đo:

- Time to working feature (không đánh đổi tính đúng).
- LOC/complexity của query logic và manual denormalization.
- Số nơi phải cập nhật khi schema evolve.
- Có client drivers cho runtime/language hiện tại không.
- Testability, mocks, local environment, tracing.
- Tính ổn định của contract/cursor/query API.
- Kiến thức cần cho operator/developer.

Không dùng số dòng code đơn lẻ làm tiêu chí quyết định: code ít nhưng lỗi khi concurrent writes có thể nguy hiểm hơn code nhiều có kiểm chứng.

## 46. Chi phí: nhìn TCO, không chỉ bảng giá instance

Tổng chi phí cần xét:

\[
C_{\mathrm{TCO}} =
C_{\mathrm{compute}}+
C_{\mathrm{storage}}+
C_{\mathrm{requests}}+
C_{\mathrm{network}}+
C_{\mathrm{backup}}+
C_{\mathrm{observability}}+
C_{\mathrm{operations}}+
C_{\mathrm{migration}}+
C_{\mathrm{risk}}
\]

Đây là **khung phân loại**, không phải công thức kế toán bắt buộc; một số hạng có thể chồng lấn tùy mô hình giá. Cần tránh tính trùng.

### 46.1. Nhóm chi phí thường bị bỏ sót

- Nhiều replicas/AZ/regions và egress liên vùng.
- Secondary indexes và replicated indexes.
- Write amplification do denormalized read models.
- Background compaction/repair/index builds.
- CDC/stream consumers và search engine.
- PITR/backup/object storage cross-region.
- Long-term retention, TTL cleanup và compliance.
- Network requests, query planning và serverless request units.
- Monitoring, logs/traces, backup restore drills.
- Operations/on-call/security patching.
- Migration/reindex/rewrite application.
- Commitment discounts, quota/burst price, support tier.
- Cost khi cache hit giảm và source phải chịu tải thay.

PoC nên ghi chi phí ở **cùng workload và SLO đạt được**. Không nhân một giá/tháng từ một run 5 phút mà bỏ qua index/storage growth và operations.

## 47. Chi phí mỗi business operation

Đếm đơn vị thực:

~~~text
One CreateOrder journey:
  1 conditional stock update
  1 Order write
  1 Outbox write
  2 secondary-index updates
  1 GET read-after-write
  1 CDC event
  1 search projection update
~~~

Nếu business throughput là 1.000 Orders/s, số physical writes/requests có thể lớn hơn 1.000 nhiều lần. Một ứng viên tính tiền theo request units, ứng viên khác theo nodes/IOPS; so sánh cần quy về **valid, completed Orders** hoặc **một triệu business journeys** cùng semantic requirements.

Ví dụ:

\[
\text{Cost per 1M orders}
=
\frac{\text{total attributable cost during measured window}}
{\text{valid completed orders}/1{,}000{,}000}
\]

Cần định nghĩa kỳ đo đủ dài, amortization và cách phân bổ fixed costs. Không tính failed/duplicate Orders như throughput có ích.

## 48. Sensitivity analysis: điều gì xảy ra khi giả định sai?

Một lựa chọn chỉ phù hợp nếu biết **nó nhạy với giả định nào**.

Tạo ma trận biến động:

| Biến | Baseline | Stress |
|---|---:|---:|
| Dataset | 1× | 3× và 10× dự báo |
| Offered QPS | 1× | 2×/5× |
| Hot-key share | 10% | 40% |
| Largest tenant share | 20% | 60% |
| Average record size | 1 KiB | 4 KiB |
| Read/write ratio | 80/20 | 40/60 |
| TTL/retention | 30 ngày | 180 ngày |
| Replica count | 3 | 5 và một node mất |
| Search freshness | 30 s | 5 s |
| Query complexity | Point lookup | Cross-partition aggregate |

Không cần thử mọi tổ hợp \(2^{10}\) nếu ngân sách không cho phép. Chọn **risk-driven experiments**, ví dụ hot-key × burst, TTL × compaction, failover × write contention, scale-out × CDC.

Kết quả nên chỉ ra: nếu lớn nhất tenant tăng từ 20% lên 60%, ứng viên nào cần thay data model? Chuyển partition key có yêu cầu migration/reindex? Một chi phí công nghệ thấp hiện tại có thể tạo **chi phí đổi kiến trúc** rất cao khi giả định sai.

## 49. Ước lượng migration và tính khả thi triển khai

Chọn candidate không kết thúc ở “nó chạy được trong môi trường mới”. Nếu có dữ liệu đang vận hành, cần thử:

- Extract/backfill speed và cost từ source.
- Data type/schema transformation fidelity.
- CDC handoff từ snapshot tới live stream.
- Tạo indexes/constraints ở target.
- Read shadow/canary và reconciliation.
- In-flight write cutover/unknown outcome.
- Idempotency và cross-source operation IDs.
- Reverse sync/rollback feasibility sau target writes.
- Downtime window và source/target capacity.
- Decommission old resource có bảo vệ backup/privacy.

Một engine đòi đổi data model cực lớn để đạt SLO có thể vẫn tốt về lâu dài, nhưng phải tính **migration cost/risk** trước khi chọn. Không coi kết quả PoC là đã chứng minh cutover production nếu chỉ import một file tĩnh 1 GiB.

## 50. Đánh giá candidate bằng hai tầng quyết định

### 50.1. Tầng 1: hard gates

Mỗi ứng viên có trạng thái:

- **PASS:** đã có bằng chứng đạt yêu cầu.
- **FAIL:** đã có bằng chứng vi phạm.
- **INCONCLUSIVE:** chưa đủ dữ liệu hoặc test không hợp lệ.
- **NOT_APPLICABLE:** yêu cầu không áp dụng, có giải thích.

Một candidate **FAIL** hard gate không được cứu bởi weighted score cao. Một candidate **INCONCLUSIVE** không nên được mặc định coi PASS.

### 50.2. Tầng 2: weighted trade-off khi đã đủ điều kiện

Ví dụ giả định:

| Tiêu chí | Trọng số | Candidate A (1–5) | Candidate B (1–5) |
|---|---:|---:|---:|
| Normal/peak performance | 20% | 4 | 5 |
| Operational resilience | 20% | 5 | 3 |
| Data-model fit | 20% | 4 | 4 |
| Cost to meet SLO | 15% | 3 | 4 |
| Team maintainability | 15% | 5 | 2 |
| Migration effort | 10% | 4 | 2 |
| **Tổng** | **100%** | **4,20** | **3,50** |

Điểm có tính minh họa: Candidate A = 0,2×4 + 0,2×5 + 0,2×4 + 0,15×3 + 0,15×5 + 0,1×4 = 4,20. Candidate B = 0,2×5 + 0,2×3 + 0,2×4 + 0,15×4 + 0,15×2 + 0,1×2 = 3,50. **Bảng chỉ có ý nghĩa khi từng điểm có bằng chứng và công thức được ghi thống nhất**; giá trị tổng trong hàng minh họa phải được tính bằng phương pháp áp dụng, không nhập thủ công theo cảm nhận.

Nếu muốn tránh trọng số chủ quan, có thể cung cấp **Pareto frontier**: công nghệ nào trade cost for latency hoặc ops for flexibility. Nhưng hard gates vẫn phải đứng trước.

## 51. Khi kết quả gần nhau: không ép tìm “người thắng”

Có thể hai candidates cùng đạt tất cả hard gates, p99 chỉ khác nhau vài ms trong phạm vi nhiễu, TCO chênh ít nhưng một cái tốt hơn theo kiến thức đội ngũ.

Kết luận hợp lệ có thể là:

- Cả hai khả thi; chọn ứng viên dễ vận hành hơn.
- PoC chưa đủ evidence về multi-region/backup; bổ sung pilot có mục tiêu.
- Candidate A tốt cho transactional core, candidate B tốt cho search/events; chọn kiến trúc đa lưu trữ nhưng ghi complexity.
- Chưa nên migrate vì lợi ích không vượt migration cost/risk.
- Chọn candidate rẻ hơn ở current load nhưng đặt trigger reevaluation khi hot tenant vượt ngưỡng.

Một PoC có chất lượng **không nhất thiết kết luận một sản phẩm vượt trội tuyệt đối**. Nó phải giảm bất định và xác định trade-offs đáng tin.

## 52. Quy tắc GO/NO-GO kèm trạng thái chưa rõ

Ví dụ hard-gate decision:

~~~text
GO if all are true:
  1. Critical queries meet SLO at normal and peak.
  2. No acknowledged-write loss or duplicate business effect.
  3. Tenant isolation and privacy tests pass.
  4. Replica/node failure recovery within agreed budget.
  5. Restore drill meets RPO/RTO and correctness.
  6. Target capacity has documented headroom.
  7. Cost at target SLO fits business budget.
  8. Migration/rollback risk is acceptable.

NO-GO if any mandatory gate fails.
INCONCLUSIVE if critical evidence is missing or invalid.
~~~

Đặt rõ **người sở hữu quyết định** (engineering lead, SRE/DBA, security/compliance, product/business sponsor), risk acceptance và thời hạn đánh giá lại. Không để một điểm số tổng quát thay thế chữ ký chấp nhận rủi ro tính đúng đắn.

## 53. Case study: ba kiểu NoSQL cùng chạy CRUD nhưng khác mức phù hợp

Giả định một hệ Orders/Inventory cân nhắc:

- **Candidate D:** document store có index linh hoạt.
- **Candidate W:** wide-column store tối ưu query theo partition/clustering key.
- **Candidate K:** managed key-value/document service với pricing theo request/capacity.

Đây là **ba mô hình giả định**, không phải bảng đánh giá thực tế của bất kỳ sản phẩm nào.

### 53.1. Dataset và workload chung

~~~text
50 million Orders
2 million Customers
250,000 Products
5% large Orders, 20% medium, 75% small
Top 1% product keys receive 40% reads
One tenant produces 35% writes

Normal:        2,000 business ops/s
Peak:          6,000 business ops/s
Flash burst:  12,000 business ops/s for 3 minutes

Critical paths:
  CreateOrder, ReserveStock, GetOrder, ListOrders
~~~

So normal/peak/burst, tenant size, cold/warm reads và business invariants theo cùng contract.

### 53.2. Kết quả hoàn toàn giả định

| Test | Candidate D | Candidate W | Candidate K |
|---|---|---|---|
| CreateOrder p99 peak | 240 ms | 190 ms | 220 ms |
| ListOrders p99 peak | 160 ms | 140 ms | 175 ms |
| Checkout invariant | PASS | PASS | PASS |
| Hot SKU contention | PASS | FAIL | PASS |
| One-node failure safety | PASS | PASS | PASS theo contract |
| Restore RTO 60 phút | PASS | FAIL, 110 phút | PASS, 45 phút |
| Tenant isolation | PASS | PASS | PASS |
| Relative TCO index | 1,00 | 0,88 | 1,12 |
| Migration complexity | Trung bình | Cao | Thấp-trung bình |

Dù Candidate W có p99 thấp nhất và TCO tốt nhất trong bảng giả định, nó **FAIL hard gates** hot-SKU contention và RTO, nên NO-GO với cấu hình đã thử. Candidate D và K còn khả thi; chọn theo chi phí, vận hành và rủi ro thay đổi.

Không suy một kết quả giả định thành nhận định thật về document/wide-column/managed NoSQL. Bảng nhằm minh họa **hard gate đứng trước weighted score**.

### 53.3. Cho phép tuning có giới hạn và công bằng

Nếu W thất bại vì hot partition, có thể thử time buckets, salt keys hoặc một mô hình reservation khác. Nhưng phải ghi:

- Query fan-out tăng bao nhiêu?
- Bất biến stock còn giữ thế nào?
- Schema/index/update code cần đổi đến mức nào?
- Data migration/cutover costs có tăng không?
- Sau tuning, phải benchmark lại **toàn bộ operations liên quan**.
- Mỗi candidate có cùng ngân sách/thời gian tuning phù hợp.

Không dành toàn bộ thời gian cải thiện ứng viên yêu thích rồi so với một cấu hình mặc định chưa tối ưu của ứng viên khác.

## 54. Mẫu specification để chạy thử nghiệm lặp lại

~~~yaml
experiment:
  id: nosql-poc-peak-v1
  owner: backend-reliability
  question: "Can candidate meet checkout and order-list SLO?"
  candidates: [document-candidate, wide-column-candidate]
  hardGates:
    noOversell: true
    noAcknowledgedWriteLoss: true
    tenantIsolation: true
  dataset:
    manifestRef: orders-v3
    seed: 20261114
    orders: 50000000
    hotTenants: true
    ttlAndTombstones: true
  workload:
    profileRef: mixed-peak-v2
    arrivalModel: open-loop-bounded
    offeredBusinessOpsPerSecond: 6000
    durationMinutes: 30
    mix:
      createOrder: 15
      reserveStock: 20
      listOrders: 20
      getOrder: 35
      deleteAndMaintenance: 10
  sLO:
    createOrderP99Ms: 350
    listOrdersP99Ms: 180
    maxCriticalCorrectnessViolations: 0
  metrics:
    - offered-and-completed-ops
    - error-and-timeout-count
    - latency-by-operation
    - retries-per-business-intent
    - disk-cpu-network
    - replica-and-index-lag
    - correctness-oracle
    - estimated-cost
  repetitions: 3
  stop:
    noQuorum: true
    criticalInvariantViolation: true
    tenantLeakage: true
  artifacts:
    - run-metadata
    - metrics
    - traces
    - oracle-results
    - config-fingerprint
    - cost-model
~~~

Đây là **template tài liệu**, chưa phải input hợp lệ của một framework benchmark cụ thể. Cần hiện thực hóa adapters, secret handling, environment protection và versioned result storage.

## 55. Runbook PoC từ yêu cầu đến quyết định

**Phase A — Định nghĩa vấn đề**

1. Liệt kê các business operations và truy vấn critical.
2. Đặt hard gates, SLO, business correctness assertions.
3. Chọn candidate dựa vào yêu cầu kiến trúc thật.
4. Viết hypotheses có khả năng bị bác bỏ.
5. Thống nhất ngân sách thử nghiệm, owner và decision date.

**Phase B — Dữ liệu và môi trường**

6. Thu thập profile production được phép dùng, không đưa PII ra test.
7. Sinh synthetic data với seed, đúng skew/age/size distributions.
8. Thiết kế partition/index/schema phù hợp từng ứng viên.
9. Provision replicas, AZ placement, TLS/IAM, observability, backup.
10. Ghi fingerprint và metadata cho dataset/topology.

**Phase C — Benchmark và correctness**

11. Kiểm semantic correctness trước đo throughput.
12. Chạy normal, warm/cold, peak và burst có offered rate rõ.
13. Chạy hot-key contention và session/read-your-writes.
14. Chạy soak với compaction/index/CDC/background maintenance.
15. Thử failover và reconcile operation IDs.
16. Test restore/recovery và privacy/security.
17. Chạy scale-out/rebalance nếu business dự định cần.
18. Lặp lại runs, lưu latency/errors/metrics/cost.

**Phase D — Quyết định**

19. Đánh giá hard gates PASS/FAIL/INCONCLUSIVE.
20. Tính cost ở mức SLO và tải tương đương.
21. So vận hành, developer ergonomics, migration risk.
22. Ghi kết quả, giới hạn và alternatives trong decision record.
23. Chọn GO/NO-GO/pilot tiếp theo có owner.
24. Định nghĩa trigger để đánh giá lại khi workload thay đổi.

Đích đến không phải một biểu đồ đẹp, mà là **một quyết định có bằng chứng và điều kiện có thể kiểm tra lại**.

## 56. Failure story: benchmark nhỏ làm mọi dữ liệu nằm trong cache

Một nhóm sinh 100.000 Orders (~0,5 GiB), chạy point reads và thấy một candidate đạt 100.000 ops/s. Cache của cụm lớn hơn nhiều so với dataset, nên hầu hết reads chỉ dùng RAM. Production dự kiến 500 triệu Orders, indexes tới 1 TiB và working set nóng 100 GiB.

Các thiếu sót:

- Không có cold reads hoặc index scan.
- Không giữ tỷ lệ working-set/cache như thực tế.
- Không có concurrent compaction.
- Không có network cross-AZ/replication cost.
- Không mô phỏng tenants cực lớn.
- Không có burst làm cache churn.

Biện pháp: thử một dataset vượt cache budget, một profile có locality và cold reads, rồi đo index/CPU/disk I/O. Nếu không đủ ngân sách để thử kích thước lớn, ghi rõ **khoảng ngoại suy chưa được xác minh** và chạy các mức trung gian với trend, không khẳng định tuyến tính.

## 57. Failure story: uniform keys che hot partition

Benchmark tạo 10 triệu IDs uniform và đạt 20.000 writes/s, cluster CPU trung bình chỉ 40%. Nhưng production có một SKU flash sale với 4.000 conditional decrements/s lên cùng một business item.

Hệ có thể gặp:

- Hot key khiến serial contention tăng.
- Conditional-write conflicts và retries.
- Partition throttling dù global CPU thấp.
- p99 checkout tăng mạnh.
- Đếm throughput physical attempts thay vì valid reservations.
- Phải redesign inventory reservation (shard/escrow/token pre-allocation) với rủi ro correctness mới.

Biện pháp:

1. Thử uniform **và** Zipf/hot-key profiles.
2. Dồn concurrent writes lên cùng item.
3. Theo dõi metrics per key/partition hoặc dấu hiệu tương đương.
4. Đếm valid business outcomes, không tính failed retries thành success.
5. Kiểm stock invariant và idempotency.
6. Đo chi phí một phương án bucketing/escrow nếu đề xuất.

## 58. Failure story: đo chi phí chỉ bằng số QPS

Candidate A phục vụ một ListOrders bằng một indexed query. Candidate B phải fan-out 12 buckets, merge/sort trong app và cập nhật hai denormalized indexes khi ghi.

Cùng 5.000 **logical queries/s** nhưng có thể khác xa về:

- Physical requests per logical operation.
- Bytes scanned vs bytes returned.
- Cache hit rate và hot partition.
- Cross-AZ network bytes.
- CPU merge và memory của application.
- Write amplification và index growth.
- Retry/throttled request volume.
- Serverless capacity/IOPS bills.
- CDC/search/maintenance overhead.

Để so công bằng, tính **cost per valid business journey** và TCO để đạt cùng SLO, chứ không chỉ list price của một node.

## 59. Risk register sau PoC

Một PoC có thể chưa xóa hết bất định. Nên lưu:

| Rủi ro | Evidence hiện có | Mức chưa chắc chắn | Hành động |
|---|---|---|---|
| Hot key mùa cao điểm | Đã thử 2× traffic | Peak 5× chưa xác minh | Burst pilot có kiểm soát |
| Restore 10 TiB | Restore 1 TiB thành công | Không biết thời gian 10 TiB | Tăng scale test/benchmark |
| Multi-region write | Chỉ test local region | Conflict policy chưa rõ | Thiết kế contract và fault test |
| TTL/compaction | Soak 2 giờ | 90-day retention chưa mô phỏng | Pre-seed aged records, extended soak |
| Tenant isolation | Tests pass | Admin export permissions chưa kiểm | Security review |
| Cost | Resource estimate | Egress/backup biến động | Sensitivity model |
| Migration | Backfill tĩnh pass | Live CDC/cutover chưa thử | Isolated cutover rehearsal |

Trường trạng thái nên là **RESOLVED, ACCEPTED_RISK, ACTION_REQUIRED, BLOCKER** kèm owner/due date. Không biến “chưa đo” thành “PASS mặc định”.

### 59.1. Kết quả INCONCLUSIVE không phải thất bại công nghệ

Nếu fault controller gây lỗi cả hai candidates vì test network chưa cấu hình đúng, hoặc load generator bão hòa CPU trước database, đó là **giới hạn thí nghiệm**. Cần sửa phương pháp rồi lặp lại; không quy lỗi cho engine. Ngược lại, nếu một ứng viên fail vì core query pattern không được hỗ trợ, đừng xóa evidence bằng cách đổi yêu cầu kinh doanh sau khi xem số.

## 60. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách tiếp cận |
|---|---|---|
| “Nhanh nhất về QPS là tốt nhất” | Query mix và correctness chưa đo | Contract + business operations |
| “PoC demo CRUD là xong” | Thiếu tải, failover, restore | Risk-driven test plan |
| “Cùng số rows là dataset đại diện” | Skew/size/age/cardinality khác | Representative profiles |
| “Random uniform là traffic thực” | Hot keys và tenant skew | Distribution-driven generator |
| “Nhỏ hơn production 100 lần vẫn ngoại suy tuyến tính” | Cache/compaction/index nonlinear | Scale and sensitivity tests |
| “Đổi engine nhưng giữ schema cũ cho công bằng” | Data model theo access pattern khác | Comparable logical contracts |
| “Tắt TLS khi benchmark không sao” | Production cost/latency khác | Same security requirements |
| “Một node là đủ đánh giá HA” | Thiếu quorum/replication | Production-like topology |
| “Mọi requests đều có trọng số như nhau” | Critical checkout khác reporting | Per-operation SLO |
| “p99 của success-only đủ” | Errors/timeouts bị loại | Full attempt reporting |
| “Closed-loop không bị thiên lệch” | Coordinated omission | Scheduled arrivals + errors |
| “Throughput DB bằng business throughput” | Fan-out, retries, projections | Valid business ops |
| “NoSQL scale tuyến tính khi tăng nodes” | Hot key/global invariant bottleneck | Scale test and hotspot test |
| “Latency tốt nghĩa data đúng” | Stale reads/oversell | Consistency oracle |
| “Backup bật sẵn nghĩa RTO đạt” | Chưa restore drill | Measured recovery |
| “Benchmark chỉ cần một lần” | Noisy neighbor/run variation | Repetitions and uncertainty |
| “Giá máy chủ là TCO” | Storage, egress, ops, migration | Full cost model |
| “Managed nghĩa không cần DBA/SRE” | Key design, IAM, backup, SLO vẫn cần | Operational ownership |
| “Test thiếu dữ liệu vẫn kết luận PASS” | Hard gate chưa có evidence | INCONCLUSIVE |
| “Điểm tổng cao cứu được lỗi dữ liệu” | Correctness là hard gate | Gate before scoring |
| “PoC phải chọn một sản phẩm thắng” | Có thể ngang nhau hoặc chưa đủ | Decision with uncertainty |
| “Thử failover trên production để nhanh” | Rủi ro dữ liệu và user | Isolated or approved scope |
| “Một query plan chạy được là đủ” | Full scan có thể tăng phi tuyến | Explain/IO/fan-out |
| “Tuning mãi cho một ứng viên là công bằng” | Budget/timebox khác nhau | Controlled iteration |
| “Cùng tên API consistency nghĩa cùng guarantee” | Scope và failure semantics khác | Contract-specific tests |
| “Skip TTL/deletes vì là cleanup” | Retention và privacy là chức năng | Data lifecycle in PoC |
| “Mọi metrics đẹp khi idle chứng minh peak” | Không có saturation/backlog | Load staircase |
| “Pilot thành công nghĩa không cần rollback” | Migration và future load vẫn rủi ro | Recovery/stop plan |

## 61. Bài tập A — Thiết kế bộ dữ liệu cho NoSQL PoC

Giả sử hệ có:

~~~text
200 tenants
5,000,000 Order records
100,000 Product records
Order size: 0.5 KiB to 32 KiB
One tenant stores 40% of Orders
Top 2% Products receive 50% reads
90% Order reads target last 30 days
Orders older than 180 days are archived/deleted by policy
~~~

Hãy:

1. Viết dataset manifest và fixed random seed.
2. Phân bố số records của tenants lớn/trung bình/nhỏ.
3. Dùng một hàm sinh skew cho product keys thay uniform.
4. Sinh timestamps có recency locality.
5. Sinh nhiều kích thước Order và nested items.
6. Tạo indexes/query inputs nhất quán giữa candidates.
7. Thêm updated/deleted/TTL records và outbox state.
8. Giữ types tiền/timestamps chính xác.
9. Đảm bảo data hoàn toàn synthetic, không có PII thật.
10. Đặt phép kiểm empirical histogram sau khi seed.
11. Tính working set và cache ratio cần đạt trong test.
12. Liệt kê ít nhất ba giới hạn của dataset so với production.

**Đầu ra mong đợi:** manifest, generator pseudo/Java, profile histogram và assumptions document.

## 62. Bài tập B — Thiết kế workload và acceptance

Hệ cần:

~~~text
Normal: 1,500 business ops/s
Peak:   4,500 business ops/s
Burst:  9,000 business ops/s for 2 minutes
Critical API: checkout p99 <= 300ms
Noncritical read: p99 <= 500ms
Read-your-writes is mandatory for Order details
No acknowledged Order loss; no duplicate payment charge
~~~

Thiết kế:

1. Bảng operation mix normal và peak.
2. Data-key distribution/hot tenants và hot SKU.
3. Tải open-loop hay closed-loop cho từng kịch bản?
4. Concurrency/backpressure và timeout budgets.
5. Warm-up, steady peak, burst, soak và recovery windows.
6. Oracle cho acknowledged Orders và idempotency.
7. Test conditional stock writes dưới contention.
8. Failover khi request đang commit và mất ACK.
9. Metrics client/DB/CDC/replica/tenant cần thu.
10. GO/NO-GO thresholds, sample count và owner.
11. Kế hoạch bảo vệ môi trường và cleanup.
12. Cách tính cost per valid checkout journey.

## 63. Bài tập C — Phân tích kết quả PoC giả định

Hai candidates cùng chạy trên dataset đã xác nhận:

| Metric | Candidate A | Candidate B |
|---|---:|---:|
| Peak offered requests/s | 6.000 | 6.000 |
| Peak completed valid requests/s | 5.820 | 5.900 |
| Checkout success-only p99 | 260 ms | 220 ms |
| Timeout/error % | 2,8% | 1,5% |
| Hot-key oversell violations | 0 | 2 |
| Tenant isolation test | PASS | PASS |
| Backup restore time | 48 phút | 42 phút |
| RTO threshold | 60 phút | 60 phút |
| TCO relative index | 1,0 | 0,9 |
| Failover ACKed loss | 0 | 0 |

Yêu cầu:

1. Ứng viên nào vượt hard gates hiện tại? Vì sao?
2. Vì sao B có p99 và TCO tốt hơn vẫn có thể NO-GO?
3. Success-only p99 có cần đọc cùng errors và offered load không?
4. Hai tỷ lệ lỗi có tương ứng với counts không?
5. Kiểm thử oversell có thể sai do oracle hay thật? Kiểm thế nào?
6. A có đủ capacity headroom cho burst 9.000 requests/s chưa?
7. RTO 48/42 phút được đo end-to-end hay chỉ restore bytes?
8. Nếu B sửa được oversell bằng CAS có contention, cần chạy lại những test nào?
9. Cần xét team operations và migration cost thế nào?
10. Ghi một kết luận có ba phần: verified facts, remaining risks, proposed action.

**Gợi ý:** Một vi phạm “không được oversell” là hard blocker cho B trước khi xem điểm tổng. Tuy nhiên B có thể được thử lại với model hợp lệ nếu đây là vấn đề có phương án sửa rõ và còn timebox.

## 64. Bộ bằng chứng cần lưu để người khác tái hiện kết luận

Một PoC kết thúc tốt nên có tối thiểu:

| Artifact | Nội dung |
|---|---|
| **Decision brief** | Vấn đề, ứng viên, lựa chọn, điều kiện |
| **Requirements matrix** | Hard gates, SLO, soft criteria và owners |
| **Hypothesis registry** | Điều kiện, cách đo, kết quả, confidence |
| **Dataset manifest** | Generator version, seed, count, bytes, skew, TTL |
| **Workload profile** | Arrival process, mix, hot-key distribution, durations |
| **Schema/index ADR** | Key strategy, query plan, write fan-out, caveats |
| **Environment fingerprint** | Engine/SDK versions, topology, AZ, resources, settings |
| **Run logs/results** | Start/end, metrics, errors, repeats, inconclusive runs |
| **Correctness report** | Idempotency, invariant, freshness, data comparison |
| **Fault/restore results** | RPO/RTO, client recovery, backup and failover |
| **Cost model** | Billable units, TCO assumptions, scaling sensitivity |
| **Risk register** | Gaps, owner, mitigation, decision deadline |
| **Migration plan** | Backfill/CDC/cutover/rollback/forward-repair |
| **Approval record** | Người chấp nhận rủi ro và điều kiện pilot |

Các artifact có thể ở nhiều định dạng, nhưng nên tham chiếu bằng ID/version rõ ràng. Không công khai raw PII, credentials hoặc cluster access tokens trong báo cáo.

Báo cáo PoC cần trả lời được: **“Nếu một người khác dựng cùng dữ liệu và cùng cấu hình, họ có thể lặp phép thử, xác nhận giả thuyết và hiểu vì sao chúng ta chọn giải pháp này không?”**

## 65. Câu hỏi tự kiểm tra

1. PoC khác một CRUD demo ở điểm nào?
2. Benchmark là toàn bộ hay một phần PoC?
3. Khi nào nên đánh dấu INCONCLUSIVE thay vì PASS?
4. Vì sao cần viết hypothesis có điều kiện đo rõ?
5. Hard gate khác weighted criterion thế nào?
6. Một QPS cao có thể che lỗi nghiệp vụ ra sao?
7. Vì sao dataset cùng row count chưa chắc đại diện?
8. Working set và total logical data khác nhau ở đâu?
9. Khi cache đủ chứa toàn data test, điều gì bị che?
10. Hot-key distribution ảnh hưởng partition performance thế nào?
11. Tenant skew có thể tạo noisy neighbor ra sao?
12. Vì sao cần giữ tỷ lệ độ tuổi dữ liệu?
13. Deletes/TTL/tombstones phải có trong PoC khi nào?
14. Tại sao lấy 10.000 rows mới nhất gây sampling bias?
15. Vì sao hash email không tự bảo đảm ẩn danh?
16. Access-pattern catalog nên chứa những trường nào?
17. Query mix theo phần trăm khác journey mix thế nào?
18. Vì sao READ-your-WRITES phải đo cùng POST?
19. Point read có đại diện cho range/fan-out query không?
20. Index read benefit đổi lấy write/storage cost thế nào?
21. Conditional write khác blind overwrite ở điểm nào?
22. Offered throughput và completed throughput khác nhau thế nào?
23. Concurrency có phải tương đương offered QPS không?
24. Little's law được dùng với giả định gì?
25. Open-loop khác closed-loop load generator ở đâu?
26. Coordinated omission gây kết luận sai ra sao?
27. Burst kéo dài có thể tạo hậu quả nào?
28. Tại sao random requests độc lập bỏ lỡ correlation?
29. Công bằng benchmark là cùng schema hay cùng business contract?
30. Fixed resources và fixed budget/SLO so gì khác nhau?
31. Những nguồn nhiễu nào có thể làm p99 dao động?
32. Vì sao topology single-node không thể chứng minh HA?
33. Một ứng viên cần data model riêng có còn được coi là so công bằng?
34. Khi query phải full scan, PoC cần đo gì?
35. Tại sao denormalization làm write fan-out tăng?
36. Một synthetic generator cần lưu seed/manifest vì sao?
37. Test oracle độc lập với database là gì?
38. Vì sao data correctness không thể chỉ so record counts?
39. Consistency contract phải rõ phạm vi nào?
40. Test staircase xác định điểm saturation ra sao?
41. p99 có ý nghĩa gì khi timeouts bị loại khỏi samples?
42. Một kết quả hơn kém 2 ms có luôn mang ý nghĩa thống kê không?
43. Test hot SKU nên kiểm invariant nào?
44. Khi failover, acknowledged writes phải được kiểm ra sao?
45. Vì sao election time khác user-facing recovery time?
46. Restore drill phải gồm những phần ngoài copy bytes?
47. Scale-out có chi phí tạm thời nào?
48. Soak test phát hiện vấn đề gì mà run ngắn bỏ lỡ?
49. Security bật/tắt có làm benchmark mất công bằng không?
50. Operational readiness có ảnh hưởng quyết định NoSQL không?
51. TCO gồm các khoản lớn nào thường bị quên?
52. Vì sao nên tính cost per valid business journey?
53. Sensitivity analysis giúp quyết định gì?
54. Khi live migration, backfill đơn lẻ đã đủ chưa?
55. Vì sao reverse sync/failback phải được thiết kế trước?
56. Candidate FAIL hard gate có thể thắng nhờ điểm tổng không?
57. Có trường hợp hai candidates đều đủ điều kiện không?
58. Case study giả định không thể dùng làm benchmark sản phẩm thật vì sao?
59. Mỗi kết quả nên đi kèm artifacts nào để tái lập?
60. Khi workload thực tăng 3×, trigger reevaluation nên là gì?

## 66. Tổng kết: thử nghiệm khả thi là phép đo có tính đại diện và có thể quyết định

Trong bối cảnh **đánh giá và lựa chọn NoSQL**, điều khó nhất không phải viết script gửi một triệu requests, mà là chọn đúng **những giả thuyết, dữ liệu và business operations** mà kết quả sẽ thay đổi quyết định. Một benchmark nhanh nhưng dùng key uniform, data nhỏ vừa cache và không kiểm tra tính đúng đắn có thể cho kết luận nguy hiểm hơn việc chưa benchmark.

Một quy trình đáng tin:

~~~text
1. Bắt đầu từ business goals, access patterns và hard gates.
2. Định nghĩa SLO, consistency/durability và correctness assertions.
3. Chọn candidates và giả thuyết có thể bị bác bỏ.
4. Thu profile dữ liệu/tải được phép dùng, bảo vệ privacy.
5. Sinh dataset có kích thước, skew, age, lifecycle đại diện.
6. Thiết kế schema/partition/index riêng phù hợp từng engine.
7. Dựng topology, TLS/IAM, replicas và recovery gần production.
8. Dùng workload mix có correlation, hot keys, bursts, concurrency.
9. Đo offered/completed rate, p95/p99, errors, retries và queues.
10. Đo resource saturation, query plans, write/read amplification.
11. Chạy contention, failure, scale-out, soak, backup/restore tests.
12. Đối soát business intents, idempotency, security và freshness.
13. Tính TCO ở mức SLO tương đương, gồm migration/ops/risk.
14. Lặp các runs, báo uncertainty và những điều chưa kiểm chứng.
15. Áp hard gates trước, sau đó mới so trade-offs/weighted criteria.
16. Lưu decision record, artifacts, risk owners và pilot next steps.
~~~

PoC tốt không nhất thiết tìm ra một công nghệ thắng tuyệt đối. Nó phải làm rõ **ứng viên nào đáp ứng được yêu cầu cụ thể**, điều kiện nào khiến giải pháp không còn phù hợp và chi phí/rủi ro nào được tổ chức chấp nhận.

**Nguyên tắc cốt lõi:** *Chỉ tin vào kết luận lựa chọn NoSQL khi dữ liệu đầu vào, tải và failure scenarios đủ đại diện cho hệ cần xây; phép đo phản ánh các kết quả nghiệp vụ đúng; và người khác có thể tái hiện bằng cùng contract, configuration và phương pháp.* Đó là sự khác biệt giữa một demo nhanh và một thử nghiệm khả thi dùng được cho quyết định kiến trúc.














