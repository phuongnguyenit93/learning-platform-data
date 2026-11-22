# YCSB hoặc công cụ khác và giới hạn biểu diễn nghiệp vụ thực tế

Một nhóm phát triển Java muốn chọn cơ sở dữ liệu NoSQL cho dịch vụ đặt hàng. Họ chạy benchmark với một triệu document nhỏ, tỷ lệ 95% `read` và 5% `update`, sau đó thấy hệ A đạt 80.000 operations/giây còn hệ B đạt 60.000 operations/giây. Nhóm kết luận hệ A sẽ xử lý checkout tốt hơn. Tuy nhiên, khi triển khai, checkout còn phải kiểm tra tồn kho, ghi đơn hàng, thực hiện cập nhật có điều kiện, lưu idempotency key, phát outbox event và xác minh trạng thái thanh toán. Lượng truy cập cũng tập trung vào một số SKU “hot”, document đơn hàng lớn dần, các tenants có kích thước khác nhau, và hệ thống phải đáp ứng p99 latency trong giờ cao điểm.

**Kết luận chọn hệ A từ con số benchmark đơn lẻ là không đủ.** Đo 95% GET trên dữ liệu được phân phối đều có thể hữu ích khi đánh giá read path. Nhưng nó không đại diện cho transaction nhiều bản ghi, write contention, secondary index, CDC lag, backpressure, thao tác thất bại có chủ đích hoặc chuỗi API của checkout.

Trong chương **Hiệu năng và đo tải** của module **Database No SQL**, bài này giới thiệu **YCSB (Yahoo! Cloud Serving Benchmark)** và các công cụ bổ sung; hướng dẫn xác định phạm vi của một benchmark, tạo workload, đo throughput/latency/tail/errors, thiết kế thí nghiệm có thể lặp lại và chuyển từ synthetic operations sang **hành vi nghiệp vụ có ý nghĩa**. Trọng tâm là hiểu **điều con số đo chứng minh được**, **điều nó không chứng minh được** và **những bước cần thêm trước khi ra quyết định kiến trúc**.

> **Nguyên tắc:** Benchmark không tự trả lời câu hỏi “cơ sở dữ liệu nào nhanh hơn?”. Nó trả lời câu hỏi hẹp hơn: **“Với dữ liệu, thao tác, tỷ lệ, concurrency, cấu hình, topology, fault model và phương pháp đo này, hệ đã thể hiện như thế nào?”**.

## 1. Bốn cấp độ đo hiệu năng

Không có một công cụ duy nhất thể hiện mọi lớp của hệ thống:

| Cấp độ | Đo gì? | Ví dụ | Không tự chứng minh |
|---|---|---|---|
| **Microbenchmark** | Hàm, serializer, thuật toán hoặc data structure | JMH đo JSON serialization | Latency của API qua mạng |
| **Database operation benchmark** | Read/update/insert/scan qua client binding | YCSB | Checkout/transaction nghiệp vụ |
| **Service/API load test** | Request end-to-end qua HTTP/gRPC | k6, Gatling, JMeter, Locust, ghz | Toàn bộ journey và downstream bất đồng bộ |
| **Business workflow test** | Chuỗi bước và invariants của sản phẩm | Checkout, reservation, sync/replay | Mọi tình huống production không có trong model |

### 1.1. Benchmark cơ sở dữ liệu không phải đo API

Client YCSB có thể gọi trực tiếp driver, bỏ qua authentication, authorization, service orchestration, cache, mapping DTO, HTTP, rate limiter và các cuộc gọi phụ. Do đó, kết quả không thể được gắn thẳng lên một endpoint.

### 1.2. Benchmark API cũng có thể bỏ qua công việc nền

Một request `POST /orders` trả `202 Accepted` rất nhanh nhưng worker outbox còn xử lý hàng giờ. Chỉ đo thời gian HTTP response chưa xác nhận nghiệp vụ đã hoàn tất.

### 1.3. Đo tính đúng đắn trước khi so tốc độ

Một store bỏ conditional updates hoặc xác nhận lệnh trước khi dữ liệu được lưu bền có thể trông nhanh hơn. Kết quả của **hai hệ thực thi các bảo đảm khác nhau** không thể so trực tiếp như cùng một việc.

### 1.4. Benchmark phục vụ quyết định, không thay quyết định

Mục tiêu có thể là tìm bottleneck, ước lượng capacity, so tính năng, phát hiện regression hoặc dự đoán chi phí. Thiết kế bài test phải bắt đầu từ **câu hỏi cần quyết định**.

## 2. YCSB là gì?

YCSB là một bộ framework/workload dùng để đo các thao tác phổ biến của hệ lưu trữ phục vụ dữ liệu dạng record/key-value. Thông qua **database binding**, YCSB gọi một giao diện thao tác tương đối thống nhất lên nhiều hệ khác nhau. Điều này giúp tạo workload lặp lại và so sánh trong một phạm vi đã chuẩn hóa.

~~~mermaid
flowchart LR
    CFG["Workload configuration"] --> CORE["YCSB workload/client"]
    CORE --> BIND["Database binding"]
    BIND --> DRIVER["Vendor driver"]
    DRIVER --> DB["NoSQL cluster"]
    CORE --> MET["Client measurements"]
    DB --> S["Server-side metrics"]
~~~

### 2.1. Tách phần sinh tải và cách truy cập sản phẩm

YCSB core tạo requests theo operation mix và key/value distributions. Binding dịch các requests thành API cụ thể. Cùng config không đảm bảo hai bindings thực hiện **chính xác cùng một semantic contract** nếu một hệ có hạn chế transaction, consistency, query hoặc kiểu dữ liệu khác.

### 2.2. Các thao tác cơ bản thường gặp

- `READ`: lấy record/key.
- `UPDATE`: sửa một số fields.
- `INSERT`: tạo record mới.
- `SCAN`: đọc một phạm vi/bộ records.
- `READ_MODIFY_WRITE`: đọc, tính toán rồi cập nhật theo logic workload.

Một số binding hoặc phiên bản không triển khai đủ tính năng hay ánh xạ theo cách khác. Phải kiểm binding code/config và kết quả lỗi, không chỉ tin tên thao tác.

### 2.3. YCSB phù hợp nhất cho câu hỏi nào?

Ví dụ: “Khi 1 triệu records có kích thước gần tương đương, 95% random reads và 5% updates, 64 clients, một region, throughput và p99 của two deployments như thế nào?” Đây là câu hỏi benchmark hợp lệ nếu topology/consistency/error handling được mô tả.

### 2.4. YCSB không có “nghiệp vụ” mặc định

YCSB không hiểu Order, Cart, InventoryReservation hay Payment. Nó chỉ biết những records và operations mà workload/driver định nghĩa. Mô hình hóa nghiệp vụ phức tạp phải được triển khai thêm.

## 3. YCSB load phase và run phase

YCSB thường có hai pha chính:

~~~text
LOAD:
    Tạo dataset ban đầu theo recordcount.

RUN:
    Thực thi operations theo operationcount / run duration,
    proportions, distributions, thread count và giới hạn tốc độ.
~~~

### 3.1. Load là tạo trạng thái đầu vào

Nếu cần đo hệ có 20 triệu records, hãy tạo gần mức đó trước khi đo. Test trên database rỗng hoặc vài nghìn records có thể chỉ đo hot cache, chưa đụng indexes, compaction, partition scatter hay storage footprint như production.

### 3.2. Run là phát workload

Trong run phase, YCSB thực hiện reads/updates/inserts/scans theo mix và distribution. Dữ liệu được load có thể thay đổi; nếu nhiều tests chạy liên tiếp mà không reset, thử nghiệm sau sẽ nhìn dataset khác.

### 3.3. Load time không phải run latency

Thời gian ingest hàng triệu records hữu ích cho capacity planning, nhưng không được lẫn vào p99 phục vụ request người dùng. Báo cáo load và steady-state run riêng.

### 3.4. Trạng thái sau load có thể chưa ổn định

Bulk loading có thể kích hoạt compaction, index building, replication catch-up, background merge hoặc autoscaling. Nếu bắt đầu run ngay, kết quả có thể phản ánh hậu quả ingest hơn là trạng thái ổn định. Khi cần, chờ điều kiện warm-up/steady state được định nghĩa trước.

### 3.5. Thí nghiệm insert-heavy thay đổi database theo thời gian

Trong workload có insert, số records, indexes, cache miss và storage footprint tăng. Cần biết điểm đầu/cuối và so sánh cùng một khoảng tiến triển.

## 4. Workloads A–F thường được nhắc đến

Các bộ workload mẫu của YCSB thường được mô tả như sau; **cấu hình cụ thể phải đọc trong file workload đang chạy**, vì chúng có thể bị tùy biến:

| Workload | Tỷ lệ thao tác mẫu | Ý tưởng |
|---|---|---|
| **A — Update Heavy** | 50% `READ`, 50% `UPDATE` | Nhiều cập nhật |
| **B — Read Mostly** | 95% `READ`, 5% `UPDATE` | Chủ yếu đọc |
| **C — Read Only** | 100% `READ` | Đường đọc |
| **D — Read Latest** | 95% `READ`, 5% `INSERT` | Ưu tiên bản ghi mới |
| **E — Short Ranges** | 95% `SCAN`, 5% `INSERT` | Đọc vùng ngắn |
| **F — Read-Modify-Write** | 50% `READ`, 50% `READ_MODIFY_WRITE` | Đọc rồi cập nhật |

### 4.1. Workload A chưa phải transaction

50% update có thể đo write load, nhưng không đồng nghĩa checkout thực hiện atomic updates của Order, Inventory và Outbox.

### 4.2. Workload B không tự đại diện danh mục

Catalog search có filtering, ranking, index traversal, facet counts, pagination và nhiều query shapes. 95% direct key lookup không mô tả các phép đó.

### 4.3. Workload C hữu ích nhưng dễ thiên lệch cache

Đo read-only steady state có thể đạt throughput rất cao nếu toàn bộ keys/values nằm trong RAM. Production vừa đọc vừa ghi có compaction, cache invalidation, index updates và CDC load.

### 4.4. Workload D cần hiểu `latest` distribution

Đọc records mới nhất khác chọn key đồng đều trên toàn bộ lịch sử. Nếu sản phẩm có feed/timeline hoặc phần dữ liệu vừa tạo được truy cập nhiều, distribution này có thể hữu ích; vẫn cần xác minh tỷ lệ và locality thực.

### 4.5. Workload E không tự là mọi range query

`SCAN` trong binding có thể là key-range iteration, khác secondary-index scan, sorted search, aggregation hoặc pagination across shards. Phải biết binding nào đã được thực thi.

### 4.6. Workload F không bảo đảm atomic read–modify–write

Tên operation không chứng minh toàn bộ read+update là một transaction có isolation. Nếu business yêu cầu CAS/serializable behavior, cần test có condition và kiểm lost-update, không chỉ đo ops/s của RMW.

## 5. Ví dụ cấu hình và chạy YCSB

Đây là một ví dụ minh họa theo giao diện lệnh thường gặp ở các bản YCSB cổ điển. **Tên binding, đường dẫn script, flags và database properties thay đổi theo phiên bản/nền tảng; phải kiểm hướng dẫn của bản YCSB và binding thực tế**:

~~~bash
# Load 1 million records with a selected binding.
bin/ycsb load <binding> \
  -P workloads/workloada \
  -p recordcount=1000000 \
  -threads 16 \
  -s

# Run 2 million mixed operations.
bin/ycsb run <binding> \
  -P workloads/workloada \
  -p recordcount=1000000 \
  -p operationcount=2000000 \
  -threads 32 \
  -s
~~~

`<binding>` là chỗ trống cần thay bằng tên binding được cài; các lệnh trên **chưa** cung cấp connection/auth/TLS. Không gõ placeholder như một tên sản phẩm thật.

### 5.1. Cấu hình workload tùy chỉnh

~~~properties
recordcount=1000000
operationcount=2000000

readproportion=0.80
updateproportion=0.15
insertproportion=0.05
scanproportion=0
readmodifywriteproportion=0

requestdistribution=zipfian
fieldcount=10
fieldlength=100
readallfields=true
writeallfields=false
~~~

Các key là ví dụ thường gặp; kiểm từng property và binding trong version dùng. Tỷ lệ operations cần hợp lệ theo workload engine. `fieldcount * fieldlength` chỉ xấp xỉ payload, chưa tính key, serialization, indexes và metadata storage.

### 5.2. `recordcount` không phải số operations

`recordcount` mô tả dữ liệu đã có/được tạo theo setup. `operationcount` mô tả số operations trong run. Nếu số ops lớn mà dataset nhỏ, working set có thể fit cache và tạo benchmark quá lạc quan.

### 5.3. `-threads` khác target throughput

Thread count tăng concurrency, không định nghĩa request rate chính xác. Một công cụ có thể có `-target` hoặc pacing options theo version, nhưng phải kiểm traffic thực tế vì client có thể không đạt tốc độ đã đặt.

### 5.4. Load dataset và run phải cùng schema

Nếu load binding tạo `field0`..`field9` nhưng production giữ nested Order với arrays/metadata lớn, kết quả không đại diện document size/index behavior của workload thật.

### 5.5. Không nhét secrets vào báo cáo

Connection URIs, access keys, credentials, TLS certificates không nên xuất hiện trong logs/artifacts công khai. Dùng secret management và thông số đã redact.

## 6. Distributions: lựa chọn nào ảnh hưởng kết quả?

Ngoài tỷ lệ read/write, **keys nào được truy cập** thường quyết định hit ratio, partition skew và write contention.

| Phân phối | Mô tả | Trường hợp tham khảo |
|---|---|---|
| Uniform | Mỗi key gần như có xác suất như nhau | Access trải rộng toàn tập |
| Zipfian | Một nhóm keys hot hơn rất nhiều | Popular SKUs, viral content |
| Latest | Ưu tiên bản ghi mới | Feed, recent sessions |
| Sequential | Keys theo thứ tự | Batch import/range iteration |
| Hotspot | Phần lớn requests vào tập nhỏ | Tenant/hot SKU |
| Custom trace-based | Theo logs thực đã bảo vệ privacy | Workload sản phẩm cụ thể |

### 6.1. Uniform có thể che hot partition

Với 100 triệu keys phân bố đều, load có vẻ cân bằng. Production có một tenant chiếm 40% requests và một SKU nhận 10.000 writes/giây thì limit có thể nằm ở single partition/lock.

### 6.2. Zipfian không tự giống production

Zipfian giúp tạo skew, nhưng degree/skew, tương quan key với document size, tenant và operation type phải được calibrate. Chọn một tham số Zipf rồi khẳng định “đã mô phỏng thật” là không đủ.

### 6.3. Hot set thay đổi theo thời gian

Flash-sale làm một nhóm SKU đột ngột nóng; celebrity content hot vài phút rồi nguội. Stationary distribution trong suốt bài test không phản ánh turnover, cold cache, invalidation và scaling.

### 6.4. Tương quan giữa read/write mới là vấn đề

Người dùng có thể vừa tạo Order rồi đọc ngay, hoặc update profile rồi search. Sinh ngẫu nhiên read và update hoàn toàn độc lập bỏ mất **read-your-writes** và causal locality.

### 6.5. Tuổi dữ liệu có ảnh hưởng

Records cũ có thể lớn hơn, nhiều version/tombstones, đặt trên cold storage hoặc index shape khác. Key distribution không chứa thông tin ấy nếu không tạo dữ liệu có tuổi/lifecycle.

## 7. Kích thước và hình dạng dữ liệu

Một record YCSB gồm nhiều fields đơn giản. Nhưng NoSQL thực tế có:

~~~json
{
  "tenantId": "T1",
  "orderId": "O-100",
  "status": "PENDING",
  "totalMinor": 125000,
  "currency": "VND",
  "version": 41,
  "lines": [
    {"sku": "SKU-A", "quantity": 2, "unitPriceMinor": 45000},
    {"sku": "SKU-B", "quantity": 1, "unitPriceMinor": 35000}
  ],
  "shippingAddress": {
    "city": "Ha Noi",
    "country": "VN"
  }
}
~~~

### 7.1. Cùng 1 KiB không cùng chi phí

Một 1 KiB string value, một JSON document có 30 fields và một document có nested arrays có thể tốn CPU parsing, indexing, serialization và compression khác nhau.

### 7.2. Record growth

Một `Order` mới có 500 bytes, sau 50 events/notes có thể thành 20 KiB. Benchmark giữ fixed `fieldlength` sẽ không thể hiện document growth và write amplification.

### 7.3. Sparse fields

Trong thực tế, field có thể missing/null/unknown, các document schema versions khác nhau. Payload synthetic đồng nhất làm codec nhanh và ít validation hơn hệ thực.

### 7.4. Index entries cũng chiếm tài nguyên

Secondary indexes, compound indexes, GSIs, text/vector indexes hoặc materialized views có write amplification. Chỉ đo primary-key GET/PUT mà bỏ indexes có thể đánh giá sai write costs.

### 7.5. Compression có thể làm sai so sánh

Synthetic values lặp ký tự dễ nén không giống encrypted/compressed media hoặc dữ liệu ngẫu nhiên. Phải chọn field contents hợp lý, đo network/storage sizes thực thay vì chỉ cấu hình `fieldlength`.

## 8. Access pattern quan trọng hơn tên hệ NoSQL

Một hệ document, key-value, wide-column hay graph có khả năng tối ưu các đường truy cập khác nhau. Những câu hỏi cần xác định:

- Lookup theo primary key có partition key đầy đủ không?
- Query dùng secondary index, scatter/gather hay full scan?
- Có sort theo time và pagination ổn định không?
- Một API cần đọc bao nhiêu records trước khi trả?
- Bản ghi có update một field hay replace cả document?
- Có transaction cùng partition, cross-partition hay external side effects?
- Read cần strong/session/eventual consistency nào?
- Có delete/TTL và CDC subscribers hay không?

### 8.1. `READ` không đại diện một query phức tạp

API `searchOrders(status,createdAfter,sort,page)` có thể dùng composite index hoặc materialized view. Benchmark random GET theo ID không kiểm được index plan.

### 8.2. `UPDATE` không đồng nghĩa CAS

Blind update có thể chạy nhanh hơn update kèm version predicate. Với inventory, bỏ version guard để tăng throughput là **thay đổi correctness**, không phải tối ưu.

### 8.3. `SCAN` thay đổi theo binding

Một binding có thể ánh xạ scan thành range query, binding khác cần lọc nhiều partitions. So results mà không xem executed operations/query plan có thể so **hai công việc khác nhau**.

### 8.4. Một sản phẩm có nhiều APIs

MongoDB aggregate pipeline, DynamoDB Query/Scan, Cassandra partition range, Redis sorted set và Cosmos DB cross-partition query không cùng semantics. YCSB binding thường chỉ là **một lát cắt** của khả năng sản phẩm.

## 9. Workload 95/5 vẫn có nhiều hình thái

Hai workloads đều 95% reads và 5% updates:

~~~text
Workload X:
    Random read any of 10,000,000 keys.
    Update a uniformly random key.

Workload Y:
    60% reads target 1% hot keys.
    Updates concentrate on same hot keys.
    Every update increments entity version and index projection.
~~~

Tỷ lệ số thao tác giống nhau, nhưng Y có lock/CAS conflicts, hot partitions, cache invalidation và queueing khác hẳn.

### 9.1. Concurrency không chỉ là số threads

32 workers vào 32 keys khác nhau khác 32 workers tranh cùng một key. Lock conflicts, serial retry và backoff có thể giới hạn throughput dù CPU/IO còn dư.

### 9.2. Think time tạo burstiness

Người dùng mở trang rồi đọc, xem, đặt hàng; requests có khoảng nghỉ, session correlation và peak burst. Synthetic clients phát liên tục có thể là một workload khác.

### 9.3. Tỷ lệ update trong request khác tỷ lệ update ở DB

Một checkout HTTP request có thể phát nhiều DB reads/writes. 5% HTTP POST không đồng nghĩa 5% database write operations.

### 9.4. Background jobs đổi operation mix

CDC consumers, repair, expiration, compaction, report jobs và reindexing có thể chạy đồng thời; benchmark chỉ foreground misses các nguồn tải này.

## 10. Throughput đo thế nào?

**Throughput** thường là số **operations hoàn thành** trong một đơn vị thời gian:

\[
X = \frac{N_{\text{completed}}}{T_{\text{seconds}}}.
\]

Nếu 600.000 thao tác thành công trong 60 giây:

\[
X = 10{,}000\ \text{ops/s}.
\]

Nhưng kết quả cần ghi rõ loại thao tác và tỷ lệ thành công.

### 10.1. Offered load vs achieved throughput

Client cố gửi 50.000 requests/giây (**offered**) nhưng chỉ hoàn tất 30.000/giây (**achieved**), phần còn lại queue/error/timeout. Công bố “50.000 ops/s” mà không nói chỉ đạt 30.000 là gây hiểu nhầm.

### 10.2. Throughput không phải capacity tối đa

Nếu test chỉ có 10 clients và không saturate backend, throughput thấy được có thể phản ánh giới hạn client. Nếu tăng threads tạo lỗi và p99 quá SLO, “max ops/s bất kể latency” không phải năng lực có ích.

### 10.3. Thành công được định nghĩa ở mốc nào?

Database driver ACK write có thể chỉ là local acknowledgement, durable commit, quorum acknowledgement hoặc accepted request theo API. Phải công bố consistency/durability để tránh so thao tác khác nhau.

### 10.4. Read/write op count có thể không đồng nhất

YCSB `READ_MODIFY_WRITE` có thể là một operation logic nhưng thực hiện nhiều requests phía driver. Đo cả `business operations/s` và actual DB calls/s khi so capacity.

### 10.5. Không lấy trung bình thông qua tổng lỗi

Nếu 20% requests timeout nhưng throughput phần thành công vẫn cao, hệ không “nhanh” theo mục tiêu nghiệp vụ. Report success rate, errors, timeouts và admitted/rejected requests.

## 11. Latency: mean, percentile và tail

Độ trễ có thể đo từ lúc client bắt đầu yêu cầu tới khi nhận kết quả. Nhưng thời điểm bắt đầu **khác nhau giữa công cụ**: khi job được scheduled, khi thread thực sự gửi, hay khi driver bắt đầu gọi API?

Một phân phối minh họa:

~~~text
50% operations < 5 ms
90% operations < 12 ms
99% operations < 80 ms
99.9% operations < 400 ms
~~~

### 11.1. Mean không mô tả tail

99 requests 5 ms và 1 request 1.000 ms cho mean khoảng 14,95 ms; người dùng rơi vào request chậm vẫn phải đợi một giây. p99/p99.9 cần quan tâm khi tail gây mất trải nghiệm/timeout.

### 11.2. Percentile chỉ có nghĩa với tập mẫu định nghĩa

p99 read ≠ p99 update. Tổng hợp cả hai có thể che update tail latency cao. Report theo operation, endpoint, tenant/tier, success/failure và thời gian test.

### 11.3. Đừng cộng p99 của các services

p99 của hai bước riêng không tự cộng thành p99 end-to-end. Phân phối, correlation và branching matters. Muốn p99 checkout, đo checkout hoàn chỉnh.

### 11.4. Latency timeout cần được tính

Nếu request timeout ở 2 giây, loại tất cả timeout khỏi histogram làm p99 đẹp một cách giả. Report timeout/error rate và policy histogram/censoring rõ.

### 11.5. Histogram resolution

Không ghi mọi latency vào buckets 10ms nếu SLO 5ms, hoặc dùng unit sai (microseconds vs milliseconds). Kiểm actual output units và thống nhất conversion.

## 12. Throughput–latency curve và saturation

Một bài test hữu ích chạy nhiều mức tải thay vì chỉ một điểm:

| Offered requests/s | Achieved success/s | p99 latency | Error rate |
|---:|---:|---:|---:|
| 2.000 | 1.998 | 18 ms | 0,1% |
| 5.000 | 4.990 | 32 ms | 0,2% |
| 8.000 | 7.950 | 85 ms | 0,6% |
| 10.000 | 8.200 | 480 ms | 18% |

**Các số là giả định để minh họa**, không phải kết quả đo một sản phẩm thật.

### 12.1. “Knee point”

Tới gần capacity, thêm offered load làm queueing tăng mạnh trong khi throughput chỉ nhích ít. Điểm hữu ích thường nằm **trước vùng saturation** và còn headroom cho failover/peak.

### 12.2. SLO-constrained capacity

Nếu yêu cầu `p99 <= 100 ms` và error rate < 1%, mức 8.000 offered/s có thể gần giới hạn mục tiêu trong bảng. 10.000 offered/s tuy có achieved success/s nhỉnh hơn nhưng đã vi phạm SLO.

### 12.3. Closed vs open load generator

Closed-loop clients đợi request hoàn thành rồi mới gửi tiếp; khi backend chậm, client tự giảm request rate. Open-loop generator cố phát theo lịch độc lập với completion để mô tả arrivals. Hai kiểu tạo đường cong tải khác.

### 12.4. Steady state khác burst

Một hệ chịu 8.000 req/s trong 10 phút chưa chắc chịu burst 30.000 req/s trong 5 giây, đặc biệt với connection pools, autoscale, cache stampede và queue limits.

### 12.5. Biểu diễn error khi quá tải

Một backend có thể fail fast 429 để bảo vệ nguồn; hệ khác chờ hàng phút rồi timeout. So throughput đơn lẻ không đo user impact; chính sách overload là một phần của contract.

## 13. Closed-loop, open-loop và coordinated omission

Với **closed-loop**:

~~~text
send request
wait for response
optional think time
send next request
~~~

Khi database chậm 2 giây, cùng client không tạo thêm request trong thời gian chờ. Nếu mục tiêu là mô phỏng traffic arrivals cố định, nó có thể **không ghi nhận những requests lẽ ra đến trong thời gian service stall**.

### 13.1. Coordinated omission là gì?

Nếu bộ đo chỉ ghi latency của các requests được phát sau khi request trước kết thúc, thời gian backend “đứng hình” có thể bị thể hiện quá nhẹ. Điều này làm tail latency trông tốt hơn trong một số thiết kế test.

### 13.2. Open-loop không tự động chính xác

Một open-loop generator cũng có thể có scheduling delay, queue nội bộ, dropped requests hoặc giới hạn worker. Cần đo **scheduled time, actual send time, completion time và dropped load** theo khả năng công cụ.

### 13.3. YCSB có giới hạn biểu diễn arrivals

Nhiều cấu hình YCSB sử dụng thread-based synchronous operations; `-target`/pacing không tự biến nó thành một end-to-end open-loop model đầy đủ. Kiểm implementation/version và log achieved rate.

### 13.4. Kết hợp hai loại test

Closed-loop hữu ích để tìm throughput concurrency-bound. Open/arrival-rate test hữu ích đánh giá hệ khi traffic tiếp tục đến dù latency tăng. Dùng cả hai khi xây capacity/SLO model.

### 13.5. Đừng sửa số liệu bằng suy đoán

Nếu công cụ có coordinated-omission correction/histogram settings, cần hiểu giả định và báo cáo raw/corrected một cách minh bạch, không dùng tính năng ấy để che lỗi client.

## 14. Little's Law và giới hạn concurrency

Trong hệ ổn định, định luật Little:

\[
L = \lambda W
\]

Trong đó \(L\) là số công việc trung bình trong hệ, \(\lambda\) là tốc độ hoàn thành/đến của hệ ổn định, \(W\) là thời gian trung bình một công việc trong hệ.

Ví dụ giả định: 2.000 requests/s, average end-to-end time 0,05 s:

\[
L \approx 2{,}000 \times 0.05 = 100
\]

công việc đồng thời trung bình.

### 14.1. Tại sao cần công thức?

Nếu công cụ chỉ có 20 synchronous clients, latency 50 ms và không có think time, khó tạo 2.000 req/s ổn định. Generator/connections là giới hạn trước khi database bị saturate.

### 14.2. Hàng đợi không ổn định

Khi offered arrival rate liên tục cao hơn service capacity, queue tăng và không có steady state hữu ích. Không áp công thức với số đo từ một hệ đang phình queue vô hạn mà không nêu giả định.

### 14.3. DB operations khác HTTP requests

Một checkout request có thể tạo 5 DB calls và chờ payment; Little's Law cần áp cho đúng loại công việc và boundary. Không lấy HTTP throughput nhân DB single-op latency rồi suy concurrency checkout.

### 14.4. Thread count và connection pool

Tăng threads lên 500 khi pool chỉ 50 connections có thể đo thời gian chờ pool chứ không đo database service time. Điều này có ý nghĩa nếu pool là thành phần production, nhưng cần tách bottleneck.

## 15. Client generator có thể là bottleneck

Benchmark runner cũng dùng CPU/RAM/network. Một client yếu có thể saturate trước backend, khiến hai databases đều đạt cùng một số ops/s “trần” giả.

### 15.1. Triệu chứng

- Client CPU đạt giới hạn, server CPU thấp.
- Tăng threads không tăng throughput nhưng client GC/network tăng.
- Client network đạt băng thông trong khi server còn dư.
- Metrics server cho thấy request rate thấp hơn offered.

### 15.2. Phân tán load generators

Dùng nhiều clients ở những hosts đủ tài nguyên, nhưng cần đồng bộ thời gian đo, gộp histogram hợp lệ và tránh tính mỗi client là một kết quả độc lập khi chúng cùng tác động một cluster.

### 15.3. TLS/auth serialization cũng có chi phí

Nếu production dùng TLS, authentication, compression và tracing nhưng test tắt hết, kết quả đo không đại diện end-to-end production connection. Có thể có test isolate driver riêng, nhưng phải ghi rõ.

### 15.4. Network placement

Client cùng availability zone có latency khác client ở region khác. Không dùng kết quả LAN để hứa p99 xuyên đại dương.

### 15.5. JVM JIT và GC

Java load generator và service cần warm-up thích hợp; GC pauses ở client có thể bị gán nhầm sang database latency nếu timestamping không phân tách.

## 16. Warm cache, cold cache và working set

Một benchmark đọc đi đọc lại 100.000 keys có thể fit hoàn toàn trong cache. Production có 100 triệu keys, đuôi phân phối dài và hot set đổi từng giờ.

### 16.1. Warm cache là một trạng thái hợp lệ

Nhiều hệ thực cũng có high cache hit ratio. Nhưng phải biết tỷ lệ RAM/data, hit/miss, thời gian warm-up và eviction khi đổi workload.

### 16.2. Cold-start test

Kiểm sau restart/failover cache bị lạnh; nguồn có thể nhận burst read, tăng latency và throttling. Đây là một thí nghiệm khác steady-state warm-cache.

### 16.3. Cache là một tầng trong workload

YCSB gọi trực tiếp database không đo được L1 Caffeine, L2 Redis, invalidation, negative caching hoặc stale refresh ở API. Nếu ứng dụng production dựa vào các tầng ấy, phải test kiến trúc tương ứng.

### 16.4. Không trộn hit latency và miss latency tùy tiện

Nếu 99% cache hits 1 ms và 1% misses 200 ms, p99 có thể nằm ở vùng chuyển tiếp. Thay cache policy có thể làm p99 thay đổi dù DB benchmark không đổi.

### 16.5. TTL waves và cache stampede

Một triệu entries hết hạn cùng lúc có thể tạo origin storm. Uniform YCSB reads với cache luôn warm không thể hiện event-driven invalidation hay TTL herd.

## 17. Read consistency và write durability phải giống nhau

Hai database bindings có thể mặc định:

~~~text
System A: eventually consistent read, low write acknowledgement.
System B: strongly consistent read, durable/quorum acknowledgement.
~~~

Nếu A nhanh hơn, điều đó **không** chứng minh A xử lý cùng workload correctness với B.

### 17.1. Đặt baseline semantics

Trước khi so, ghi rõ read consistency (strong/session/eventual), write concern/commit visibility, atomic update scope, timeout và retry behavior.

### 17.2. YCSB `READ` không đo stale rate mặc định

Read latency thấp không chứng minh dữ liệu là bản mới nhất. Muốn đo read-your-writes/visibility lag, cần test ghi state version rồi đọc theo consistency requirement và tính mismatch rate.

### 17.3. Throughput cao do bỏ conditional check?

Nếu application yêu cầu tồn kho không âm, benchmark blind increment không so được với transactional conditional decrement. Phải test trên cùng invariant.

### 17.4. Async write có thể trả nhanh nhưng chưa durable

Một API trả accepted trước durable commit. Khi báo cáo, phân biệt accepted/scheduled và final committed outcomes.

### 17.5. Failover/fault model

Một write ACK có sống qua crash/promotion của node không? Benchmark happy path chưa chứng minh durability. Cần fault tests trong phạm vi hỗ trợ và tài liệu sản phẩm.

## 18. Data model, partitioning và indexing

YCSB primary-key read có thể đạt p99 rất tốt trong khi application query phụ thuộc:

~~~text
partitionKey = tenantId
sortKey = createdAt
filter = status
orderBy = createdAt DESC
limit = 50
~~~

### 18.1. Partition key skew

Một tenant lớn có thể làm một logical partition nóng, dù tổng cluster CPU còn dư. Dùng trace-based key distribution và per-partition metrics.

### 18.2. Secondary index maintenance

Một Order update status có thể đồng thời cập nhật GSI/materialized view/search projection. Nếu YCSB UPDATE field không indexed, benchmark bỏ chi phí duy trì index.

### 18.3. Read plan khác nhau

`getById` bằng primary key rất khác query `status IN (...)` across tenants/partitions. Test rõ từng access path và query plan.

### 18.4. Compound keys và document packing

Nhóm items cùng aggregate trong một document/partition có thể giảm round trips nhưng tăng document size, contention và write amplification. Benchmark phải phản ánh data model đang đề xuất.

### 18.5. Scan limit

Một store không hỗ trợ ordered range scan hiệu quả có thể phải fan-out. Nếu binding thay SCAN bằng một phép khác, kết quả không so như cùng API.

## 19. Load test giao dịch nhiều bản ghi

Một checkout hợp lệ:

~~~text
1. Load Cart and Price.
2. Read authoritative Inventory.
3. Conditionally reserve quantities.
4. Create Order with commandId deduplication.
5. Commit outbox intent.
6. Trigger payment workflow.
7. Return committed or pending/rejected outcome.
~~~

### 19.1. Một YCSB UPDATE không mô tả checkout

Update một record không đo coordination, transaction commit, retry whole unit of work, external effects hoặc atomic outbox.

### 19.2. Đo theo transaction scope

Nếu NoSQL chỉ hỗ trợ atomic single document/partition, test phải dùng thiết kế domain phù hợp. Không so giao dịch mạnh ở hệ A với hai independent writes ở B mà cùng gọi “checkout”.

### 19.3. Đo conflict và abort

Hai users cùng đặt SKU hot; một số reservation phải bị từ chối do hết hàng hoặc retry vì OCC conflict. `success rate` không được cộng mọi **business rejection** vào infrastructure failures.

### 19.4. Unknown commit outcome

Sau timeout, server có thể đã commit. Benchmark chỉ tính timeout là failure có thể vô tình retry bằng commandId mới và double order. Test cần đối soát stable commandId và final outcomes.

### 19.5. End-to-end latency khác DB latency

DB reservation có thể 10 ms, nhưng payment/outbox eventual completion mất 500 ms. Đo rõ API acknowledgement và business completion SLO.

## 20. Workload nghiệp vụ là đồ thị, không chỉ operation mix

Sơ đồ đơn giản:

~~~mermaid
flowchart TD
    USER["Checkout request"] --> CART["Read cart"]
    CART --> PRICE["Read price/version"]
    PRICE --> INV["Reserve inventory with CAS"]
    INV -->|"Committed"| ORDER["Create Order and outbox"]
    INV -->|"Business reject"| NO["Out of stock"]
    ORDER --> PUB["CDC/outbox publisher"]
    PUB --> PAY["Payment service"]
    PAY --> PROJ["Update read model"]
~~~

### 20.1. Tỷ lệ nhánh quan trọng

10% carts hết hàng, 2% payment retry, 1% unknown commitment và 15% read cache miss có thể tạo một workload khác xa “95% reads, 5% writes”.

### 20.2. Correlated traffic

Một user vừa thêm SKU-A vào cart sẽ thường đọc SKU-A, cập nhật cart rồi checkout SKU-A. Random key cho từng operation bỏ mất tính tương quan.

### 20.3. Session/journey

Một người dùng có thể mở năm product details rồi checkout, không phải sáu requests hoàn toàn độc lập. Journey mix tạo pressure lên một số indexes/records nhiều hơn.

### 20.4. Fan-out/fan-in

Một API đọc Order, Customer, Inventory và Pricing song song; response chỉ xong khi nhánh chậm nhất hoàn tất. YCSB GET latency một key không đo tail amplification.

### 20.5. Async completion

Nếu endpoint trả 202 rồi workflow hoàn tất qua events, cần đo backlog, age of oldest pending, failure/retry và time-to-final-state. Kết quả HTTP p99 ngắn có thể che backlog tăng vô hạn.

## 21. Công cụ bổ sung ngoài YCSB

| Công cụ/phương pháp | Phù hợp | Hạn chế cần nhớ |
|---|---|---|
| **YCSB** | Key-value/document CRUD workload chuẩn hóa | Không mô phỏng nghiệp vụ phức tạp mặc định |
| **k6** | HTTP/API traffic, scenarios, arrival rates | Cần script giữ domain identity/validation |
| **Gatling** | HTTP journey và concurrency/load profiles | Kịch bản phải được thiết kế đúng behavior |
| **JMeter** | HTTP/protocol tests, nhiều sampler | Dễ bị generator bottleneck nếu setup không tốt |
| **Locust** | User journey bằng Python, phân tán traffic | Task weights không tự phản ánh DB operation mix |
| **ghz** | gRPC load testing | Chỉ đo RPC đã chọn, không tự đo async effects |
| **Custom Java harness** | Transaction/CDC/CAS/idempotency/logic đặc thù | Dễ viết load/metrics sai nếu không có đo chuẩn |
| **JMH** | Serializer/codec/algorithm microbenchmark trong JVM | Không đo production NoSQL end-to-end |
| **Production trace replay** | Key/hotset và journey có bằng chứng | Cần scrub PII, limit impact, kiểm dependency |

### 21.1. Không công cụ nào tự biết correctness

Một k6 script chỉ kiểm HTTP 200 sẽ bỏ sót duplicate orders hay stale read model. Một JMeter test kiểm text response cũng không chứng minh tính nhất quán của backend.

### 21.2. Chọn theo lớp cần đo

Nếu hỏi “Redis cache có giúp giảm p99 Product API?”: dùng API-level load. Nếu hỏi “DynamoDB condition update chịu hot key bao nhiêu?”: dùng targeted adapter harness. Nếu hỏi “JSON codec nào nhanh?”: dùng JMH riêng.

### 21.3. Có thể phối hợp nhiều công cụ

YCSB dựng đường cong single-operation capacity; k6/Gatling kiểm API SLO; custom Java runner kiểm multi-key transaction, CDC, recovery; chaos/fault harness kiểm failover.

### 21.4. Tránh trộn kết quả không cùng boundary

So “ops/s YCSB direct driver” với “requests/s HTTP có auth + cache + payment” không phải cùng đơn vị công việc.

## 22. Ví dụ k6: đo HTTP API chứ không đo direct DB

Kịch bản JavaScript minh họa một API đọc Product:

~~~javascript
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    product_reads: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 50,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(99)<250"]
  }
};

export default function () {
  const sku = `SKU-${Math.floor(Math.random() * 1000)}`;
  const url = `${__ENV.BASE_URL}/api/products/${sku}`;
  const response = http.get(url, {
    headers: { Authorization: `Bearer ${__ENV.TOKEN}` }
  });
  check(response, {
    "response status expected": r => r.status === 200
  });
  sleep(0.1);
}
~~~

Đây là script mẫu cần endpoint, credentials test, data fixtures và quyền load test. Số 100 req/s và threshold là ví dụ, **không phải khuyến nghị SLO sản phẩm**. `Math.random()` tạo uniform SKU selection, không phản ánh popularity thực.

### 22.1. K6 đo network/service overhead

Kết quả bao gồm HTTP, auth, cache, serialization và DB khi đi qua endpoint thật. Nếu mục tiêu chỉ so database driver, đây là boundary khác YCSB.

### 22.2. Dữ liệu đầu vào phải hợp lệ

Nếu 80% SKUs không tồn tại, benchmark chủ yếu đo negative caching/404 chứ không phải đọc Product thực. Xác định cardinality và phân phối ID dựa dữ liệu seed.

### 22.3. Token/Auth

Authentication, token expiry, rate limit và permission scopes cần được cấu hình như production hoặc mô tả rõ bị loại khỏi test. Không đưa token thật vào source/test reports.

### 22.4. Tránh test nhầm bảo vệ rate limiter

Nếu gateway 429 từ 100 req/s, load generator đang đo admission control chứ không phải DB capacity. Báo failed/accepted categories và đi đúng quyền test.

### 22.5. Đo đúng p99

`http_req_duration` là client-side HTTP latency, không tự đo time-to-final-business-state cho một async checkout.

## 23. Java custom harness: mô hình hóa một nghiệp vụ

Ví dụ interface của kịch bản không phụ thuộc database vendor:

~~~java
public record ReserveStockCommand(
    String tenantId,
    String sku,
    String orderId,
    String commandId,
    long quantity
) {}

public sealed interface ReservationResult
    permits ReservationResult.Committed,
            ReservationResult.Rejected,
            ReservationResult.Pending {
    record Committed(String reservationId)
        implements ReservationResult {}
    record Rejected(String businessCode)
        implements ReservationResult {}
    record Pending(String commandId)
        implements ReservationResult {}
}

public interface InventoryReservationPort {
    ReservationResult reserve(ReserveStockCommand command);
    ReservationResult resolve(String tenantId, String commandId);
}
~~~

Một load runner dùng interface này có thể sinh tenants, SKU popularity, duplicate command IDs và concurrent requests để kiểm:

~~~text
Business outcomes:
    COMMITTED
    REJECTED_OUT_OF_STOCK
    PENDING_UNKNOWN_OUTCOME

Infrastructure outcomes:
    TIMEOUT / THROTTLED / UNAVAILABLE / RETRYABLE_ABORT

Latency boundaries:
    attempted → source committed
    attempted → final resolved
~~~

### 23.1. Không gộp rejection vào lỗi hạ tầng

`OUT_OF_STOCK` có thể là kết quả **đúng** khi 100 users tranh 10 sản phẩm; thống kê nó riêng. Nếu chỉ đếm “mọi request không Committed = lỗi DB”, báo cáo capacity sai.

### 23.2. Stable commandId khi retry

Retry một reservation cần dùng cùng `commandId`, không sinh ID mới mỗi attempt. Nếu không, load test có thể tự oversell/double-reserve và gây sai dữ liệu test.

### 23.3. Concurrency với skew có chủ đích

Test 80% requests vào 1% SKUs để thấy conflict/retry, rồi test phân phối đều để tìm upper bound. Ghi cả hai, không chọn kết quả đẹp nhất.

### 23.4. Side effects nên được sandbox

Không gọi payment gateway thật hoặc gửi email khách hàng trong load test. Dùng sandbox/fake boundary có semantics được mô tả; nếu test external latency, phải có phép thử được phê duyệt và isolation.

### 23.5. Harness cũng cần correctness tests

Nếu test runner map timeout thành failure rồi tạo lệnh mới, nó có thể tăng traffic/duplicates ngoài ý muốn. Đọc lại final state để reconciliation sau run.

## 24. Không chỉ đo khi hệ thống khỏe

Benchmarks steady-state rất cần thiết, nhưng production còn:

- Một node bị restart hoặc disk fail.
- Network partition làm mất quorum/leader.
- Read replica chậm và cache bị flush.
- Throttling, rate limits và autoscaling.
- CDC consumers lag, outbox backlog.
- Compaction, checkpoint, snapshot hoặc backup đang chạy.
- Một tenant đột ngột tăng tải.

### 24.1. Failover latency

Đo thời gian từ fault injection tới khi hệ trở lại SLO, số requests lỗi/timeout và có mất dữ liệu đã ACK không. Không chỉ đo throughput sau khi cluster phục hồi.

### 24.2. Consistency dưới sự cố

Một system có thể giữ availability nhưng đọc stale hoặc ghi conflict trong multi-region. Benchmark phải nêu consistency/atomicity contract và kiểm business invariants.

### 24.3. Recovery backlog

Sau sự cố, queue/outbox có thể tích backlog; DB foreground chạy lại bình thường nhưng replay/CDC workers phải catch up. Theo dõi time-to-drain và tác động lên p99.

### 24.4. Capacity headroom

Nếu một node mất và còn N−1 nodes, backend có thể không đủ throughput; cần kiểm load tại trạng thái degraded chứ không tính capacity bằng số nodes lúc khỏe.

### 24.5. Chỉ chạy fault tests trên môi trường được phép

Không ngắt mạng, kill nodes, flush cache, xóa data hoặc tạo load lớn ở production khi chưa có phê duyệt, guardrails và recovery plan.

## 25. Read/write amplification và công việc nền

Một YCSB update record nhỏ có thể dẫn đến:

~~~text
Client UPDATE
    -> WAL/commit log
    -> memtable/index update
    -> replication
    -> compaction/merge later
    -> secondary index maintenance
    -> CDC/outbox reader
    -> downstream projection writes
~~~

### 25.1. Client latency có thể chỉ là phần nổi

Một commit ACK nhanh nhưng compaction backlog tăng liên tục có thể làm hiệu năng giảm sau nhiều giờ. Run vài phút không phát hiện sustained write amplification.

### 25.2. Steady state cần đủ lâu

Đối với LSM systems, compaction có thể chạy chậm so với foreground operations. Dùng soak test để kiểm debt accumulation, IO saturation và disk growth.

### 25.3. TTL/tombstone

Workload production có delete/TTL expiration; tombstones, cleanup và compaction có thể ảnh hưởng reads. Dataset không có lifecycle/deletes có thể lạc quan.

### 25.4. CDC consumer load

Một write còn tạo event để search/reporting update. Test chỉ source DB bỏ CDC lag, retention risk và downstream backpressure.

### 25.5. Backup/index build

Snapshots, restore, reindex và anti-entropy repair có thể cạnh tranh disk/network. Benchmark lúc “cluster hoàn toàn rảnh” không đo được các giờ vận hành thật.

## 26. Multi-tenant workload: mean che noisy neighbor

SaaS có 1.000 tenants nhỏ và 3 whale tenants. Workload uniform theo tenant sẽ tạo ít pressure trên hot partitions hơn thực tế nếu whale chiếm 60% requests.

### 26.1. Tenant-weighted vs user-weighted

Chọn tenant đều nhau khác chọn request theo tỷ trọng traffic thực. Nếu mỗi tenant có load khác nhau, phải xác định distribution theo requests, theo users, theo dữ liệu hay theo doanh thu.

### 26.2. Tenant sizes tương quan với query cost

Tenant whale có nhiều records, query phức tạp và hàng trăm concurrent clients. Uniform keyspace che sự tương quan đó.

### 26.3. Noisy-neighbor test

Tăng traffic của tenant A rồi đo p99/error của tenant B. Chỉ số tổng cluster có thể đẹp nhưng một tier đang bị starve.

### 26.4. Fairness và QoS

Nếu ứng dụng có quotas/admission per tenant, test chúng cùng resource contention. “Tối đa ops/s” không đo công bằng.

### 26.5. Routing và isolation

Một số tenants ở dedicated cluster/region, số khác shared. So sánh phải chỉ ra routing và kết nối nào được đo, không trộn tất cả thành một cluster giả tưởng.

## 27. Multi-region và network topology

Đường gọi client→DB same AZ khác client→DB cross-region. Replication topology có thể thay đổi cả write latency, consistency và fault recovery.

### 27.1. Đo theo vị trí người dùng

Nếu 70% traffic tại Đông Nam Á, nhưng benchmark clients đặt cùng AZ với DB ở Mỹ, số p99 thấp không mô tả trải nghiệm thực.

### 27.2. Cross-region writes

Một số deployments có primary region, others multi-writer/conflict resolution. Không so latency của local async ACK với cross-region quorum commit như cùng một contract.

### 27.3. Read replicas và lag

Read p99 của nearest replica có thể thấp nhưng dữ liệu stale. Đo cả staleness/visibility lag khi nghiệp vụ cần read-your-writes.

### 27.4. Egress/cost

Traffic đi qua regions có thể tăng chi phí network; benchmark cần ghi bytes transferred và data residency constraints, không chỉ ops/s.

### 27.5. Failover

Đo được độ trễ khi region switch nhưng còn phải kiểm đã ACK writes và conflict histories; availability không thay tính đúng đắn.

## 28. Tính toán chi phí trên cùng SLO

Một backend nhanh hơn 20% nhưng cần instance/memory/network đắt gấp đôi có thể không phù hợp. Ngược lại, backend rẻ ở steady state nhưng cần headroom lớn cho failover có thể tốn hơn.

### 28.1. Cost per successful business operation

\[
C_{\text{op}} =
\frac{C_{\text{compute}} + C_{\text{storage}} +
      C_{\text{network}} + C_{\text{operations}}}
     {N_{\text{successful business operations}}}.
\]

### 28.2. Đừng chia theo attempted ops

Nếu 30% requests bị throttle và phải retry, “chi phí trên attempted request” đánh giá thấp chi phí cho kết quả nghiệp vụ hoàn thành.

### 28.3. Capacity dưới SLO

So “chi phí để đạt 8.000 checkout/s ở p99 < 250 ms và error < 0,5%” đáng tin hơn so “max CRUD ops/s”.

### 28.4. Background jobs tính vào ngân sách

Index storage, replicated writes, backups, CDC processing và outbox consumers đều tốn CPU/IO/egress. Hệ synthetic chạy read-only không bộc lộ chúng.

### 28.5. Overprovisioning cho N−1

Nếu cần sống qua mất node mà vẫn giữ SLA, capacity dự phòng là chi phí thực, không phải “lãng phí” do benchmark quên tính.

## 29. Phương pháp thiết kế thí nghiệm đáng tin

Một benchmark có ý nghĩa cần **điều kiện có thể lặp lại**:

~~~text
Question -> Workload definition -> Dataset -> Deployment
         -> Warm-up -> Trial -> Telemetry
         -> Verify outcomes -> Compare under same SLO.
~~~

### 29.1. Một biến mỗi khi muốn suy nguyên nhân

Nếu thay backend, instance size, cache policy và SDK cùng lúc, không biết yếu tố nào làm p99 đổi. Khi đánh giá tuning, giữ các biến còn lại cố định phù hợp.

### 29.2. Randomize trial order

Nếu luôn chạy A trước B, B có thể hưởng cache warmed hoặc chịu compaction debt của A. Reset dataset và luân phiên/rand thứ tự trials khi có thể.

### 29.3. Replicates thay một lần đo

Chạy nhiều trials độc lập để thấy variance. Tránh chọn run nhanh nhất; dùng median, phân phối, confidence interval khi phù hợp, và báo anomalies.

### 29.4. Báo trạng thái ban đầu/cuối

Số records, disk usage, cache hit ratio, compaction backlog, CPU/memory, connection counts, replication lag, indexes, operation mix và warm-up state.

### 29.5. Version mọi thứ

Ghi YCSB version/commit, binding version, driver, runtime/JVM, OS/kernel, DB version/edition, config, cluster size, region, index schema và workload files. “A nhanh hơn B” mà không có versions khó tái tạo.

## 30. Warm-up, measurement và cool-down

### 30.1. Warm-up

Cho JVM JIT, connection pools, caches và background activity đạt trạng thái mong muốn. Warm-up không phải “xóa tất cả thời gian xấu” nếu cold-start SLO quan trọng; cold benchmark nên báo riêng.

### 30.2. Measurement window

Chỉ thu metrics trong cửa sổ đã định và đồng bộ client/server timestamps. Nếu compaction/rate limit vừa bắt đầu, test window quá ngắn có thể bỏ qua hậu quả.

### 30.3. Cool-down/reset

Đợi compaction/CDC catch-up hoặc reset dataset trước trial tiếp theo. Nếu dùng same DB chứa insert growth từ run trước, ghi nhận đây là variable.

### 30.4. Soak test

Chạy nhiều giờ để quan sát memory leak, disk growth, tombstones, throttling, TTL cleanup, compaction debt, queue lag và autoscaling ổn định.

### 30.5. Step/ramp/spike tests

Step test tìm knee point; ramp cho autoscale; spike kiểm burst handling; soak kiểm bền. Mỗi loại có mục tiêu khác nhau, không thay thế nhau.

## 31. Phân loại lỗi khi đọc kết quả

| Outcome | Ví dụ | Tính vào đâu? |
|---|---|---|
| `SUCCESS` | Read/update committed theo contract | Throughput thành công |
| `BUSINESS_REJECTED` | Out of stock, invalid transition | Kết quả nghiệp vụ hợp lệ; riêng |
| `CONFLICT_RETRYABLE` | OCC write conflict/known abort | Retry theo whole unit protocol |
| `THROTTLED` | Server rate limit | Capacity/admission signal |
| `UNAVAILABLE` | No quorum/connection failure | Infrastructure error |
| `TIMEOUT_UNKNOWN` | Write có thể đã commit, ACK mất | Reconciliation; không double count |
| `NOT_FOUND` | Authoritative absence | Tùy API, có thể outcome bình thường |
| `VALIDATION_ERROR` | Payload sai kiểu/schema | Workload bug hoặc client failure |
| `UNSUPPORTED_OPERATION` | Binding không hỗ trợ scan | Không tính là successful SCAN |

### 31.1. Không loại lỗi khỏi latency

Nếu requests timeout bị drop khỏi histogram, p99 của successful subset có thể đẹp trong lúc 20% user không nhận được kết quả.

### 31.2. Business reject có thể là đúng

Một inventory SKU hết hàng từ chối 90% requests vẫn có thể bảo vệ invariant. Dùng đúng business success criterion và workload state để hiểu throughput.

### 31.3. Unknown commit không bằng rollback

Sau timeout phải đối soát stable command ID nếu test có mutations. Đếm mọi timeout là “chưa ghi” rồi retry bằng ID mới gây sai dataset.

### 31.4. SDK retries ẩn thêm workload

Một logical YCSB UPDATE có thể tạo nhiều DB attempts. Thu retries/actual server requests để biết write amplification do lỗi hoặc throttling.

### 31.5. Throttling là dữ liệu quan trọng

Một hệ từ chối sớm 429 có thể tránh queue collapse. Báo accepted rate, rejection rate và p99 của thành công cùng nhau, không chấm nó thắng chỉ vì latency thấp.

## 32. Regression benchmark trong CI/CD

Một tập nhỏ hơn có thể chạy thường xuyên để phát hiện change làm chậm read/write paths.

### 32.1. Tránh flaky thresholds

CI shared runners có noise CPU/network. Một ngưỡng p99 cứng không có confidence band có thể fail ngẫu nhiên. Dùng dedicated runner hoặc theo dõi historical baseline và tolerances phù hợp.

### 32.2. Functional correctness vẫn độc lập

Performance regression suite không thay unit/integration tests cho CAS, transaction, idempotency, CDC ordering hay schema compatibility.

### 32.3. Benchmark environment drift

Driver update, container resources đổi, DB autoscale, index thêm có thể làm baseline đổi mà không do code request. Ghi versions/config và phân tích nguyên nhân.

### 32.4. Synthetic gate và production canary

CI giúp phát hiện lỗi lớn. Canary với real-shaped traffic và observability giúp kiểm SLO; không gửi dữ liệu production nhạy cảm vào môi trường không được phép.

### 32.5. Đừng “optimize test” thay product

Nếu tuning làm YCSB random read nhanh nhưng checkout write conflicts tăng, cần ưu tiên SLO nghiệp vụ. Benchmark là công cụ hỗ trợ, không là mục tiêu cuối.

## 33. Case study 1 — Chọn NoSQL cho Product Catalog

Đặc điểm:

~~~text
70% GET product detail by ID
20% search by category + price range
8% related-products query
2% price/stock updates
Hot SKUs concentrated during campaigns
Product size: 1–20 KiB
Read model/cache has eventual invalidation
~~~

### 33.1. Dùng YCSB cho phần nào?

Direct GET 70% có thể khảo sát bằng YCSB read-heavy workload với key skew và size histogram phù hợp. Update path có thể dùng custom updates chạm indexed fields.

### 33.2. Phần nào cần tool khác?

Category/price queries, pagination, sort và recommendation index cần domain-level query benchmark hoặc HTTP API load. YCSB key lookup không đo chúng.

### 33.3. Cache invalidation

Giá update có thể làm cache stale; test phải đo version lag, hit/miss, origin p99 và risk stale refill, không chỉ database GET latency.

### 33.4. Flash-sale

SKU hot thay đổi nhanh, key Zipfian tĩnh có thể không mô phỏng đúng. Dùng phase chuyển hotspot và burst test.

### 33.5. Tiêu chí quyết định

So cost/SLO cho Product Detail p99, Search p99, update freshness lag, cache fallback khi Redis cold, và backend throughput dưới background jobs.

## 34. Case study 2 — InventoryReservation

Đặc điểm:

~~~text
90% reservation commands target 5% popular SKUs.
Each command has a stable idempotency key.
Update must prevent available < 0.
Concurrency causes CAS conflicts and business rejections.
Unknown commit requires outcome reconciliation.
~~~

### 34.1. YCSB A/F đo được gì?

Một phần read/update pressure, nhưng mặc định không bảo đảm compare-and-set/conditional decrement, stable dedupe record và conflict classifications.

### 34.2. Custom harness bắt buộc mô hình invariant

Chạy parallel reserve cùng SKU, đọc authoritative final state, kiểm `available >= 0`, tổng reservations và no-double-effect cho duplicated commands.

### 34.3. Không dùng throughput thành công để che rejection

Nếu 1.000 requests đến cho 100 units, có thể 900 requests đúng đắn bị từ chối. Report số committed units, business rejected, transient conflicts và end-to-end outcome latency.

### 34.4. Hot-partition test

Thay đổi từ uniform SKUs sang popular SKU distribution để tìm contention knee point. Thêm peak burst và retries để xem retry amplification.

### 34.5. NoSQL product comparison

Một implementation dùng atomic conditional item update; implementation khác dùng serializable transaction. Chỉ so khi cả hai đáp ứng cùng invariant/durability; nếu không, khác semantics.

## 35. Case study 3 — Dựng read model từ CDC

Một ứng dụng ghi Order vào source rồi đẩy changes qua CDC để xây search index:

~~~mermaid
flowchart LR
    APP["Order API"] --> SRC["NoSQL Source"]
    SRC --> CDC["Change Feed / Outbox"]
    CDC --> CON["Consumer"]
    CON --> IDX["Search Projection"]
    UI["Search API"] --> IDX
~~~

### 35.1. YCSB đo source write nhưng bỏ downstream

Khi viết liên tục 50.000 updates/s, source có thể ACK tốt nhưng CDC consumer chỉ xử lý 30.000/s, backlog tăng. Một benchmark nguồn đơn lẻ không nhìn thấy kết quả hệ thống.

### 35.2. Đo ba latency

`commit-to-CDC`, `CDC-to-index` và `commit-to-query-visible`. Đồng thời theo dõi replay, duplicate, failed events và retention lag.

### 35.3. Ordering per aggregate

Consumer có thể nhận changes out-of-order khi xử lý song song; phải có version/idempotency guard. Benchmark read model nên đo regressions, not-found false negatives và tombstone/deletion propagation.

### 35.4. Failure recovery

Kill consumer rồi khởi động lại; đo time-to-catch-up, impact lên source throughput và việc có mất/nhân đôi effects hay không.

### 35.5. Correctness SLO cùng performance SLO

“99% Orders searchable trong 3 giây sau commit, không resurrect Orders đã delete” là requirement có ý nghĩa hơn “CDC scanner đạt 50k records/s”.

## 36. Case study 4 — Chọn giữa hai hệ NoSQL

Nhóm có hai candidates:

~~~text
System A:
    Single-key reads very fast.
    Cross-partition transactions constrained.
    Background index projection eventual.

System B:
    Single-key reads slower.
    Stronger transaction path for intended aggregate layout.
    Better fit for required query model.
~~~

Các mô tả là giả định minh họa, không nói về sản phẩm cụ thể.

### 36.1. Hỏi đúng quyết định

Nếu 70% yêu cầu là Product Detail đọc cache và 25% là checkout cần atomic invariant, A có thể thắng YCSB nhưng B phù hợp nghiệp vụ hơn, hoặc ứng dụng cần thay data model để A đáp ứng.

### 36.2. So workload matrix

Chạy direct CRUD, transactional workflow, indexed queries, tenant skew, cold cache, CDC lag, failover và soak theo yêu cầu. Ghi nguồn so từng result.

### 36.3. Quality gates

Không đưa một hệ vào bảng so hiệu năng cuối nếu không đáp ứng business invariant bắt buộc. “Nhanh hơn vì không giữ dữ liệu đúng” không phải chiến thắng.

### 36.4. Cost dưới cùng điều kiện

Tính dollars/1.000 successful checkouts ở p99 SLO, cùng replication/backup/network. Không so ops/s trên cấu hình deployment quá khác nhau mà thiếu chuẩn hóa.

### 36.5. Kết luận có phạm vi

Ví dụ: “Trong workload GET primary-key 95%, payload 2KiB, dataset 10M records và 3 AZ topology, A có p99 thấp hơn; trong checkout transactional workload B đáp ứng invariant và SLO, A chưa có implementation đạt correctness gate.” Đây là một kết luận hữu ích hơn câu “A nhanh hơn B”.

## 37. Một ma trận test tối thiểu cho NoSQL thực tế

| Kịch bản | Công cụ thường phù hợp | Chỉ số bổ sung ngoài ops/s |
|---|---|---|
| Random key GET | YCSB | Cache hit, p99, read consistency |
| Hot key update | Custom YCSB binding/harness | CAS conflicts, retries, invariant |
| Scan/range query | Query harness/YCSB E nếu tương thích | Rows/pages, fan-out, index plan |
| Search/filter/sort | API harness | p99, index lag, result correctness |
| Create Order | API/workflow harness | Transaction outcome, idempotency |
| Checkout saga | Workflow runner | Time-to-final-state, compensation |
| CDC updates | Source + consumer harness | Lag, replay, dropped/duplicate events |
| TTL/delete | Long-running lifecycle test | Tombstones, cleanup/visibility |
| Cold cache | API load + cache metrics | Origin QPS, stampede, recovery |
| Failover | Fault injection | Recovery time, durability, errors |
| Noisy neighbor | Multi-tenant harness | Per-tier p99/fairness |
| Soak write-heavy | Long run YCSB/custom | Compaction, disk growth, p99 drift |
| Backup/restore | Recovery exercise | RPO/RTO, checksum, consistency |

### 37.1. Điều kiện qua cổng correctness

Mọi candidate phải pass required transaction, authorization/tenant scope, idempotency, schema, TTL/delete và replay tests; benchmark throughput chỉ xếp hạng trong nhóm **đúng nghĩa**.

### 37.2. Test một operation chưa đủ

Khi database có các đường truy cập khác nhau, nên có matrix workload thay vì một “YCSB score” toàn hệ.

### 37.3. Relative vs absolute performance

Relative speedup hữu ích khi quyết định tối ưu; absolute p99/throughput/error cần cho capacity planning. Report cả hai.

### 37.4. Tính biến động và khoảng tin cậy

Đưa median, số trials, range/IQR hoặc confidence intervals nếu phương pháp phù hợp; không lấy một lần chạy tốt nhất làm đại diện.

## 38. Runbook thực hiện benchmark

### Bước 1 — Viết câu hỏi và SLO

Ví dụ: “DB có chịu 5.000 successful reservations/s, p99 final outcome < 300ms, 0 oversell, dưới một node failure không?” Thông số là giả định, cần thay bằng yêu cầu sản phẩm.

### Bước 2 — Liệt kê semantics

Primary-key read, CAS, transaction scope, durability/ACK, consistency, retries, idempotency, source vs projection.

### Bước 3 — Thu hoặc suy workload model

Request mix, sessions, key popularity, hot tenants, payload size histogram, query patterns, think time, burst, data lifecycle. Nếu không có production data, ghi giả định và làm sensitivity analysis.

### Bước 4 — Chọn công cụ theo tầng

YCSB cho DB operations; API tools cho HTTP/gRPC; custom harness cho domain transaction, CDC và invariants.

### Bước 5 — Chuẩn hóa dataset

Seed số records/size/indexes/schema versions/hot keys hợp lý. Không lấy dữ liệu cá nhân thực vào test khi chưa có phép và de-identification.

### Bước 6 — Chuẩn hóa môi trường

DB version, instance type, region/AZ, replicas, write/read concern, disk/IO limits, caches, network, SDK version, client placement.

### Bước 7 — Xác nhận generator đủ khả năng

CPU/network của clients không saturate trước DB. Đo offered và achieved rates; dùng đa clients nếu cần.

### Bước 8 — Warm-up/steady-state

Tách cold-start, warm-up và measurement. Chờ compaction/replica lag đạt điều kiện được định nghĩa.

### Bước 9 — Chạy các mức tải

Step/ramp/spike/soak; thu throughput, histograms, error breakdown, retries, server metrics, source/projection lag và cost.

### Bước 10 — Verify invariants

Đối soát final records, no lost updates, no duplicate orders, stock non-negative, version monotonic, CDC coverage, tenant isolation.

### Bước 11 — Lặp lại và so sánh

Nhiều trials, reset/cool-down, công bố variance và confidence. Không thay config giữa trials mà không ghi chép.

### Bước 12 — Viết kết luận có giới hạn

Nêu điều đo được, assumptions, excluded paths, bottlenecks, SLO đạt/chưa đạt và quyết định kỹ thuật tiếp theo.

## 39. Mẫu báo cáo benchmark có thể tái tạo

~~~yaml
experiment:
  name: "nosql-reservation-capacity"
  purpose: "estimate SLO-constrained business throughput"
  date: "2026-11-14"

versions:
  loadTool: "<name and commit/version>"
  clientRuntime: "<Java/JVM or tool runtime>"
  database: "<product/version>"
  driver: "<SDK version>"

deployment:
  region: "<region>"
  nodes: "<count/size>"
  replication: "<topology>"
  readConsistency: "<mode>"
  writeDurability: "<ACK semantics>"
  indexes: "<schema version>"

dataset:
  recordCount: "<count>"
  keyDistribution: "<uniform/zipfian/trace>"
  payloadSizeP50: "<bytes>"
  payloadSizeP99: "<bytes>"
  hotKeyShare: "<ratio>"
  tenants: "<distribution>"

traffic:
  operationMix: "<by business outcome/operation>"
  offeredArrivalRate: "<req/s>"
  concurrency: "<clients/threads>"
  warmup: "<duration>"
  measurement: "<duration>"
  trials: "<count>"

observed:
  successfulBusinessOpsPerSecond: "<value>"
  p50Latency: "<ms>"
  p95Latency: "<ms>"
  p99Latency: "<ms>"
  p999Latency: "<ms>"
  timeoutRate: "<ratio>"
  throttledRate: "<ratio>"
  conflictRate: "<ratio>"
  retryAmplification: "<attempts/command>"
  originCpu: "<percent>"
  indexOrCdcLag: "<time>"
  invariantViolations: "<count>"

interpretation:
  validFor: "<precise workload/topology>"
  notCovered: "<excluded paths>"
  capacityAtSlo: "<value>"
  costAtSlo: "<currency/operation>"
  evidence: "<logs/dashboards/fixtures>"
~~~

Các placeholders phải được thay bằng dữ liệu đo thật. Mẫu không chứng minh đã có benchmark nào được thực hiện.

## 40. Những ngộ nhận phổ biến

### “YCSB Workload B là workload của mọi ứng dụng read-heavy”

Không. 95/5 chỉ là operation mix mẫu, chưa có query shapes, hot-key distribution, user journeys, cache behavior và payload thực.

### “YCSB A cao hơn nghĩa checkout nhanh hơn”

Không nếu checkout có conditional multi-step writes, dedupe, outbox và payment.

### “`READ_MODIFY_WRITE` là transaction serializable”

Không thể suy từ tên operation; cần kiểm binding/transaction semantics.

### “Kết quả YCSB giữa hai databases luôn apples-to-apples”

Không nếu consistency, durability, indexes, queries, SDK binding hoặc data models khác.

### “Ops/s càng cao càng tốt”

Không nếu p99, lỗi, throttling hoặc correctness vi phạm SLO.

### “Mean latency đủ để chọn database”

Không. p95/p99/p99.9 và timeout distribution quan trọng với người dùng.

### “Khách hàng thấy p99 bằng DB p99”

Không. HTTP, cache, auth, multiple round trips, downstream và queueing tạo end-to-end latency khác.

### “Có 64 threads nghĩa tạo đúng 64 requests mỗi giây”

Không. Thread count là concurrency; throughput phụ thuộc latency/pacing/think time.

### “Có target rate nghĩa backend nhận đúng rate”

Không. Generator có thể không đạt, requests có thể bị drop/throttle.

### “Closed-loop đo hết tác động của một outage”

Không; coordinated omission có thể làm stall được thể hiện nhẹ khi arrivals thực tiếp tục đến.

### “Uniform random keys đại diện traffic thật”

Không khi hot tenants, trending products và correlated requests chi phối.

### “Một triệu records 1KiB giống một triệu nested Order documents”

Không về parsing, indexes, updates, value distributions và growth.

### “Workload read-only phản ánh production có compaction”

Không nếu production có writes, TTL/delete, CDC và maintenance.

### “Tắt consistency để benchmark nhanh hơn vẫn là cùng thao tác”

Không; đã đổi correctness contract.

### “Bỏ timeout ra khỏi histogram làm p99 đại diện”

Không; sẽ đánh giá quá lạc quan. Report timeout separately và định nghĩa latency measurement.

### “Business rejection là lỗi DB”

Không; out-of-stock/invalid transition có thể là kết quả đúng.

### “Timeout của mutation nghĩa source không commit”

Không; outcome có thể chưa biết, cần stable commandId/reconciliation.

### “Cache hit ratio cao nghĩa database có đủ capacity”

Không; khi cache cold hoặc invalidation storm, origin load có thể vượt khả năng.

### “Benchmark 30 giây đã phản ánh long-term write performance”

Không nếu compaction debt, disk growth, TTL tombstones hoặc autoscale cần nhiều thời gian.

### “Giữ CPU server dưới 50% nghĩa còn gấp đôi throughput”

Không; bottleneck có thể ở một hot partition, IO, lock, quota, network hoặc latency budget.

### “Khác biệt 2% sau một trial là kết luận”

Không khi variance/noise chưa được kiểm soát; cần repeats và phương pháp thống kê phù hợp.

### “Mọi tool có một con số ops/s so trực tiếp được”

Không nếu đơn vị là DB operation, HTTP request, transaction commit hoặc business completion khác nhau.

### “Chỉ cần công cụ đúng, workload tự thực tế”

Không. Dữ liệu, distributions, semantics, scenario branches và environment mới quyết định mức độ đại diện.

### “Benchmark thắng thì khỏi kiểm failover”

Không. Availability, durability, recovery backlog và SLO khi mất node là một phần quyết định sản phẩm.

## 41. Checklist review trước khi tin một biểu đồ benchmark

1. **Câu hỏi quyết định đã được nêu cụ thể chưa?**
2. **Đơn vị công việc** là DB operation, API request hay business command?
3. **Thao tác có cùng semantics** về consistency/durability/atomicity không?
4. **Workload proportions** đã phản ánh operation mix thật chưa?
5. **Key distribution** có hot tenants/hot records không?
6. **Payload size/type/index shape** có giống sản phẩm không?
7. **Dataset cardinality/working set** có đủ lớn không?
8. **Transaction/conditional updates/idempotency** đã được mô hình hóa chưa?
9. **Queries theo index, scan, aggregation** đã được đo chưa?
10. **Cache hit/miss, cold start và invalidation** có trong scope không?
11. **Foreground và background load** gồm CDC, compaction, TTL, backup không?
12. **Client location/network/TLS/auth** có giống yêu cầu không?
13. **Offered vs achieved load** đã được phân biệt chưa?
14. **Generator saturation** đã được loại trừ hay báo cáo chưa?
15. **Closed/open-loop/coordinated omission** đã được xem xét chưa?
16. **p50/p95/p99/p99.9** và histogram units có được ghi rõ?
17. **Errors/timeouts/retries/throttling** được báo cáo hay bỏ khỏi mẫu?
18. **Knee point và SLO-constrained capacity** có được xác định không?
19. **Warm-up/measurement/reset** có định nghĩa và kiểm soát không?
20. **Soak/peak/spike/failover** có phù hợp production không?
21. **Kết quả có lặp lại**, variance và confidence chưa?
22. **Business invariants cuối run** đã được đối soát chưa?
23. **Cost per successful business operation** có được tính không?
24. **Versions/configuration/topology** đủ để tái tạo không?
25. **Conclusions có giới hạn scope**, không khẳng định quá mức không?

## 42. Bài tập thực hành

### Bài 1 — Đọc headline benchmark

Một bài viết nói hệ A đạt 100.000 ops/s, hệ B 80.000 ops/s. Lập danh sách ít nhất mười thông tin còn thiếu trước khi kết luận A phù hợp ứng dụng hơn.

### Bài 2 — YCSB workloads

Mô tả Workloads A–F thường gặp, tỷ lệ operations, ý nghĩa và ví dụ sản phẩm mà mỗi workload **không** mô phỏng đầy đủ.

### Bài 3 — Tạo workload read-heavy

Thiết kế cấu hình YCSB với 80% READ, 15% UPDATE và 5% INSERT; chọn `recordcount`, `operationcount`, field size và Zipfian distribution, giải thích các giả định.

### Bài 4 — Dataset size

Một test có 10.000 records, RAM cache chứa được toàn bộ, trong khi production có 100 triệu records. Phân tích thiên lệch và thiết kế thí nghiệm hai working-set sizes.

### Bài 5 — Uniform vs skew

Viết hai workload cùng 10.000 ops/s: uniform keys và 80% traffic vào 1% keys. Dự đoán khác biệt partition contention, cache hit ratio và p99.

### Bài 6 — Hot tenant

Một tenant chiếm 60% traffic trên shared cluster. Thiết kế test noisy neighbor, đo p99 của tenant khác và đề xuất quota/partition strategy.

### Bài 7 — Record growth

Order lúc tạo 1KiB, sau 30 updates thành 12KiB. Làm sao tạo dataset thể hiện size histogram và update amplification?

### Bài 8 — Query shape

YCSB READ primary key được 2ms nhưng `GET /orders?status=PENDING&sort=createdAt` mất 500ms. Phân tích vì sao và chọn tool đo query đúng.

### Bài 9 — Workload F

Một binding triển khai RMW bằng GET rồi blind UPDATE. Có bảo vệ lost-update không? Thiết kế custom CAS test nếu nghiệp vụ yêu cầu.

### Bài 10 — Throughput

Client cố gửi 20.000 ops/s, chỉ có 15.000 thành công, 3.000 timeout, 2.000 throttled. Báo cáo offered, achieved, error rate và giải thích vì sao không gọi 20.000 là throughput thành công.

### Bài 11 — Latency

Cho 99 requests 5ms và một request 1.000ms. Tính mean, mô tả tail và lý do average không phản ánh trải nghiệm người dùng chậm.

### Bài 12 — SLO-constrained capacity

Cho bảng offered load, success rate và p99 ở nhiều mức. Xác định mức cao nhất vẫn đạt `p99<200ms` và `errors<1%`, thay vì chọn throughput lớn nhất.

### Bài 13 — Little's Law

Ứng dụng đạt 4.000 req/s và average end-to-end time 100ms trong steady state. Ước lượng số requests đồng thời và nêu giả định áp dụng.

### Bài 14 — Coordinated omission

Một client closed-loop đợi database 5 giây mới gửi request tiếp theo. Giải thích vì sao không ghi được các arrivals lẽ ra xảy ra giữa lúc stall và cách open-loop test bổ sung.

### Bài 15 — Client bottleneck

Server CPU 30%, client CPU 100%, throughput không tăng khi thêm threads. Hãy lập phương án xác định generator saturation và mở rộng load generators.

### Bài 16 — Cache

YCSB trực tiếp DB cho p99 20ms, Product API có cache 95% hits. Dự đoán tại sao API p99 không thể suy trực tiếp từ YCSB và thiết kế cold-cache test.

### Bài 17 — Durability

System A ACK local asynchronous, system B majority durable. Vì sao không thể công bố A nhanh hơn cho cùng write contract? Thiết kế test trong cùng durability scope.

### Bài 18 — Multi-record transaction

Một checkout cần Inventory, Order, Outbox. Thiết kế benchmark theo business command, phân loại COMMITTED/REJECTED/PENDING và đo time-to-final-outcome.

### Bài 19 — OCC conflict

Hai clients reserve cùng SKU hot bằng version guard. Thiết kế test concurrent writers, retry whole unit, verify available không âm và thống kê conflicts.

### Bài 20 — Unknown commit

Server commit Order nhưng response mất. Benchmark retry bằng commandId mới sẽ tạo hậu quả gì? Thiết kế stable key và authoritative reconciliation.

### Bài 21 — k6 HTTP

Viết k6 scenario constant-arrival-rate cho Product API, chọn rate, VUs, thresholds, data keys và báo cáo dropped iterations.

### Bài 22 — Gatling/Locust journey

Tạo journey browse→cart→checkout có think time, branch out-of-stock và repeat user behavior. So operation mix của journey với YCSB A/B.

### Bài 23 — JMH

Chọn một Java JSON codec và đo throughput serialization với JMH; giải thích vì sao kết quả này không phải database end-to-end throughput.

### Bài 24 — CDC

Source DB xử lý 50.000 writes/s, consumer chỉ xử lý 30.000 events/s. Tính backlog tăng mỗi giây, nêu retention risks và các metrics cần theo dõi.

### Bài 25 — Soak

Một system chạy tốt 5 phút rồi p99 tăng sau một giờ do compaction backlog. Thiết kế soak test, metrics CPU/IO/disk/compaction và cách nhận diện debt.

### Bài 26 — TTL và deletes

Production có 10% deletes/expirations, YCSB test không xóa gì. Đề xuất custom workload để thể hiện tombstone và cleanup impact.

### Bài 27 — Failover

Thiết kế bài test mất node dưới tải: đo time-to-recover, ACK durability, error rate, p99, retry storm và source CDC lag.

### Bài 28 — Cost

Hệ A đạt 8.000 successful operations/s với chi phí X, hệ B 7.000/s với chi phí Y. Tính cost/1.000 business operations dưới cùng SLO và giải thích vì sao raw ops/s chưa đủ.

### Bài 29 — Variance

Ba trials có p99 lần lượt 50, 51, 180ms. Đề xuất xử lý anomaly, thêm trials, kiểm setup và không chọn run tốt nhất làm headline.

### Bài 30 — Experiment design

Bạn muốn đo tác động một GSI mới. Hãy giữ cố định topology, dataset, key distribution, operation mix và workloads; chạy before/after có reset và ghi index write amplification.

### Bài 31 — Multi-region

70% users ở Đông Nam Á, DB ở hai regions. Thiết kế load generators theo địa lý, consistency mode, cross-region writes và SLO p99 theo nhóm user.

### Bài 32 — Anti-pattern report

Một benchmark công bố “YCSB B đạt 100k ops/s nên hệ chịu 100k checkout/s, không có lỗi vì timeout bị bỏ khỏi histogram.” Hãy phản biện logic và viết mẫu kết luận có phạm vi đúng.

### Bài 33 — Trace replay

Thiết kế cách lấy log access patterns đã khử định danh, giữ key popularity/tenant tier/think time, tránh PII, rồi xây trace-based workload. Nêu tác động của historical events với môi trường thử nghiệm.

### Bài 34 — Correctness gate

Một database có p99 update 4ms nhưng lost updates dưới contention; database khác 9ms và CAS đúng. Xác định quality gate trước khi so hiệu năng và đề xuất phép thử.

### Bài 35 — Kế hoạch tổng hợp

Cho hệ Product+Checkout+CDC+Redis. Lập kế hoạch ba lớp YCSB, API load và business workflow/fault tests; xác định dataset, concurrency, distributions, SLO, invariants, retention, cost và tiêu chí ra quyết định.

---

**Kết luận:** **YCSB là công cụ hữu ích để đo các dạng thao tác cơ sở dữ liệu được chuẩn hóa**, đặc biệt khi muốn so mức tải đọc/ghi, ảnh hưởng của kích thước dữ liệu, phân phối keys và saturation trong một topology xác định. Nhưng YCSB **không tự biểu diễn nghiệp vụ**: nó không mặc định mô phỏng checkout nhiều bước, authorization, conditional transactions, outbox/CDC, cache, per-tenant skew, retries/unknown commits hay sự hoàn tất bất đồng bộ. Để đánh giá NoSQL thực tế, phải bắt đầu từ **business invariants và SLO**, xây workload phản ánh access patterns, dữ liệu và traffic của sản phẩm; dùng thêm k6/Gatling/JMeter/Locust hoặc Java harness khi cần; đo **offered vs achieved load, p99/tail, errors, retries, độ bền, consistency, chi phí và recovery**; kiểm chứng final state, lặp lại thí nghiệm và công bố giới hạn kết luận. **Con số ops/s chỉ có giá trị khi biết chính xác đã thực hiện công việc gì, trong điều kiện nào và với bảo đảm dữ liệu nào**.
