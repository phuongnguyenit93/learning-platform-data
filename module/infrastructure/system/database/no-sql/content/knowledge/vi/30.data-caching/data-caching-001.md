# Mục đích caching và lựa chọn dữ liệu nên đưa vào bộ nhớ đệm

Một hệ thống NoSQL có thể xử lý hàng nghìn yêu cầu đọc mỗi giây nhưng vẫn chậm hoặc tốn kém khi cùng một nội dung được tính lại và truy vấn liên tục. Ví dụ trang sản phẩm được 10.000 người truy cập trong một phút: tên, hình ảnh, giá niêm yết và mô tả có thể không thay đổi trong khoảng thời gian đó, nhưng nếu mọi request đều đi thẳng vào database, hệ phải lặp lại nhiều công việc gần như giống nhau.

**Caching (bộ nhớ đệm)** là kỹ thuật giữ một bản sao hoặc một kết quả đã xử lý ở tầng truy cập nhanh hơn, nhằm giảm thời gian chờ, giảm số lần truy vấn tới nguồn gốc và cải thiện khả năng chịu tải. Tuy nhiên, **cache là một bản sao có vòng đời riêng**, có thể bị cũ, bị xóa, không đủ dữ liệu hoặc sai phạm vi người dùng. Chọn nhầm dữ liệu để cache có thể dẫn tới giảm hiệu năng, chiếm quá nhiều RAM, lộ dữ liệu hoặc trả quyết định nghiệp vụ sai.

Bài học này thuộc chương **Bộ nhớ đệm dữ liệu** của module **Database No SQL**, tập trung trả lời:

- Vì sao cần cache khi dùng NoSQL, ngay cả khi database đã nhanh?
- Dữ liệu nào mang lại lợi ích rõ ràng khi đưa vào cache?
- Dữ liệu nào nên được loại trừ hoặc phải có điều kiện bảo vệ đặc biệt?
- Cần cân bằng độ trễ, chi phí, tính nhất quán, dung lượng và khả năng vận hành thế nào?
- Khi đưa cache vào hệ thống, cần đo gì để biết lợi ích thực sự?

Các giá trị thời gian, lưu lượng, dung lượng và hit rate trong các ví dụ là **giả định dùng để học**, không phải đặc tính cố định của Redis, MongoDB, Cassandra, DynamoDB hoặc một dịch vụ cụ thể. Cache hit, TTL và throughput trong production phải được đo theo access patterns, data model và cấu hình thực tế.

## 1. Cache là gì trong kiến trúc NoSQL?

Một cache thường lưu ánh xạ:

~~~text
Cache key                -> Cached value
"product:t01:SKU-A:v1"   -> {name, description, price...}
"category:t01:hot:v2"    -> [product IDs...]
"config:feature-flag"    -> {enabled: true}
~~~

Một yêu cầu đọc có thể đi theo đường:

~~~mermaid
flowchart LR
    C["Client"] --> A["Application"]
    A --> K{"Cache hit?"}
    K -->|Có| H["Trả cached value"]
    K -->|Không| D["NoSQL source"]
    D --> S["Đưa kết quả vào cache"]
    S --> R["Trả dữ liệu"]
~~~

- **Cache hit:** tìm thấy entry phù hợp, còn hiệu lực theo quy tắc ứng dụng.
- **Cache miss:** không có entry, entry đã hết hạn hoặc không hợp lệ.
- **Source of truth:** nguồn dữ liệu có thẩm quyền xác định giá trị nghiệp vụ.
- **Cache population:** đưa giá trị vào cache sau khi đọc/tính toán.
- **Invalidation:** làm entry cũ không còn được sử dụng sau thay đổi.
- **Eviction:** cache loại entry do chính sách bộ nhớ/dung lượng.
- **TTL (time to live):** khoảng thời gian entry được giữ trước khi hết hạn theo chính sách.

Điểm cốt lõi: **cache không mặc nhiên là nơi quyết định dữ liệu nào đúng**. Với đa số hệ ứng dụng nghiệp vụ, database và logic commit/transaction mới xác định Order đã được giữ hàng, thanh toán hay hủy.

## 2. “NoSQL nhanh rồi” vẫn cần cache vì sao?

Một NoSQL database có thể tối ưu point lookup nhưng vẫn phải làm việc thực sự mỗi lần được gọi:

1. Định tuyến đến partition/shard.
2. Kiểm tra connection, request headers và quyền truy cập.
3. Đọc memory/index/disk tùy trạng thái dữ liệu.
4. Áp mức nhất quán được chọn.
5. Deserialize và truyền kết quả qua network.
6. Có thể chạy aggregation hoặc kết hợp nhiều partition.
7. Tính capacity/quota và ghi metrics.
8. Chịu sự biến động khi node failover, compaction, GC hoặc network jitter.

Nếu cùng một dữ liệu được đọc lặp lại và không thay đổi thường xuyên, một cache gần ứng dụng có thể bỏ qua phần lớn những bước này. **Giảm công việc lặp lại** thường là lý do quan trọng hơn việc “RAM nhanh hơn disk” một cách đơn giản.

~~~text
GET /products/SKU-A không dùng cache:
  App -> DB round trip -> decode -> response

GET /products/SKU-A có cache hit:
  App -> memory/remote cache -> response
~~~

Cache hit ở bộ nhớ **trong process** có thể tránh network tới cache. Cache hit ở Redis vẫn có network round trip, nhưng thường ít tốn hơn một truy vấn nguồn phức tạp. Tuy nhiên, cache remote có thể không giúp nếu giá trị rất lớn, network không ổn định hoặc nguồn vốn đã gần ứng dụng và query rất rẻ.

## 3. Những mục đích quan trọng của caching

| Mục đích | Cách cache giúp | Ví dụ |
|---|---|---|
| **Giảm độ trễ** | Trả dữ liệu đã có, không truy vấn/tính lại | Chi tiết sản phẩm |
| **Giảm tải nguồn** | Hạn chế read QPS lên NoSQL | Product page hot |
| **Tiết kiệm chi phí** | Giảm capacity và data processing ở nguồn | Dashboard lặp lại |
| **Tăng throughput** | Cùng cluster phục vụ nhiều intent hơn | API đọc catalog |
| **Giảm fan-out** | Lưu kết quả tổng hợp nhiều partition | Top sản phẩm tuần |
| **Giảm tính toán** | Tái sử dụng kết quả transform/enrichment | Bộ lọc cấu hình |
| **Giảm tail latency** | Tránh truy vấn xa/hay chậm trên một số request | Cache dữ liệu vùng gần user |
| **Bảo vệ trước burst** | Hấp thụ nhiều reads cùng key | Sự kiện flash sale |
| **Tăng khả năng chịu lỗi có giới hạn** | Có thể trả dữ liệu cũ khi nguồn lỗi nếu contract cho phép | Nội dung hướng dẫn |
| **Giảm truy cập hệ ngoài** | Tránh lặp API lookups tốn phí | Metadata đã xác minh |

Caching **không** đảm bảo mọi mục tiêu cùng lúc. Cache hit cao có thể giảm DB calls nhưng lại tạo một cache hot key, tăng chi phí RAM hoặc trả dữ liệu đã quá cũ. Mỗi mục tiêu cần chỉ số và giới hạn riêng.

## 4. Phân biệt cache với database, replica và materialized view

| Thành phần | Vai trò chính | Dữ liệu có thể bỏ/tạo lại? | Cần chú ý |
|---|---|---|---|
| **Transactional NoSQL source** | Ghi nhận state nghiệp vụ có thẩm quyền | Thường không được tự ý mất | Durability, consistency, backup |
| **Read replica** | Sao chép nguồn, phục vụ một số reads | Không phải một cache tùy ý | Replication lag/failover |
| **Cache** | Lưu dữ liệu có thể lấy/tính lại | Thường có thể mất toàn bộ | Miss, eviction, stale, stampede |
| **Materialized view** | Duy trì projection theo một access pattern | Có thể rebuild nếu có nguồn/log | Freshness, updates, reconciliation |
| **Search index** | Tối ưu tìm kiếm/filter | Có thể rebuild nếu source đủ | Index lag, query semantics |
| **Warehouse** | Phân tích/report quy mô lớn | Tùy data contract và backup | Snapshot/cutoff, lineage |

Trong thực tế, materialized view có thể được dùng **như nguồn cho cache**, và cache có thể giữ kết quả từ warehouse. Nhưng đừng xem mọi thành phần “chứa bản sao” có cùng consistency/durability contract.

Ví dụ: một cached product description có thể bỏ đi và tải lại từ NoSQL. Một durable ledger chứa thông tin Payment đã thu tiền **không thể** chỉ lưu ở cache nếu đây là bằng chứng duy nhất về giao dịch.

## 5. Mục tiêu phải gắn với access pattern thực tế

Trước khi chọn dữ liệu, ghi lại các đường đọc:

~~~text
GET /products/{sku}            7.000 req/s
GET /categories/hot             800 req/s
GET /orders/{orderId}            300 req/s
GET /inventory/{sku}           1.500 req/s
GET /admin/revenue-report         10 req/min
POST /reservations               600 req/s
~~~

Các con số giả định. Không thể chỉ nhìn QPS để quyết định:

- Product description được đọc nhiều, đổi ít: **ứng viên cache tốt**.
- Inventory availability được đọc nhiều nhưng cập nhật liên tục và quyết định giữ hàng: **cache chỉ dùng như gợi ý hiển thị**, không dùng làm kết quả cấp phát có thẩm quyền.
- Order theo ID không hẳn được lặp lại nhiều; với hàng triệu IDs khác nhau, có thể cache kém hiệu quả.
- Revenue report tính toán nhiều nhưng request ít; có thể cache **kết quả tổng hợp** với freshness contract hoặc dùng materialized view.
- POST reservation là command tạo side effect, không thể “cache response” như GET thông thường nếu không có idempotency/outcome protocol.

**Access pattern mới là đầu vào chính của quyết định caching**, không phải loại database hay tên endpoint.

## 6. Tần suất đọc và độ lặp lại của khóa

Một tập dữ liệu có tổng read QPS cao vẫn có thể không cache hiệu quả nếu gần như mọi request dùng khóa mới.

~~~text
Trường hợp A:
  10.000 GET/s
  100 product keys thường được lặp lại
  -> Có cơ hội hit rate cao.

Trường hợp B:
  10.000 GET/s
  Mỗi request có một orderId chưa từng đọc trước đó
  -> Cache miss gần như toàn bộ.
~~~

Cần đo:

- Số **unique keys** trong khoảng thời gian.
- Độ lệch phổ biến (popular/hot keys).
- Số lần một key được đọc lại **trước khi TTL hoặc eviction**.
- Khoảng cách giữa hai lần truy cập cùng key (*reuse distance*).
- Read QPS theo tenant và theo nhóm nghiệp vụ.
- Tỉ lệ access tới top 1%, top 10% keys.

Một danh mục 100.000 sản phẩm có thể dễ cache nếu chỉ 500 SKU được xem nhiều nhất tạo ra phần lớn reads. Ngược lại, 100.000 khách mỗi người xem một Order riêng thì số lượng requests lớn không đồng nghĩa tập dữ liệu nóng nhỏ.

## 7. Tỷ lệ đọc/ghi và sự ổn định của giá trị

Một metric hữu ích là **read-to-update ratio** theo key hoặc nhóm:

\[
R = \frac{\text{số reads trong kỳ}}{\text{số updates trong cùng kỳ}}
\]

Giả sử:

- Description SKU-A đọc 20.000 lần/ngày, sửa 1 lần/tuần.
- Live bidding price đọc 3.000 lần/giây, cập nhật 2.000 lần/giây.
- User preference đọc 100 lần/ngày, đổi 1 lần/tháng.

Description có cơ hội cache mạnh; live bid price cần latency/freshness chặt và strategy khác; preference cũng có thể cache hiệu quả nếu được tái sử dụng.

Nhưng **read/write ratio không đủ**: dữ liệu có thể ít đổi nhưng hậu quả khi stale rất lớn (ví dụ quyền truy cập đã bị thu hồi). Vì vậy phải kết hợp mức độ thay đổi với **rủi ro của việc trả bản cũ**, không chỉ đọc nhiều hơn viết bao nhiêu lần.

## 8. Chi phí truy vấn nguồn và chi phí tạo dữ liệu

Một truy vấn nguồn đắt thường là ứng viên cache mạnh hơn một point lookup rất rẻ.

| Loại đọc | Chi phí nguồn | Khi cache có thể giúp |
|---|---|---|
| Get product by ID | Một key lookup | Giảm QPS/latency ở hotspot |
| List top-20 category | Query index + sort | Giảm query lặp |
| User permissions từ nhiều dịch vụ | Nhiều lookups + merge | Giảm fan-out, nhưng quyền cần invalidation mạnh |
| Monthly chart | Aggregate nhiều ngày | Cache kết quả với cutoff |
| Country code list | Nhỏ, gần như bất biến | Local cache rất hợp |
| Every-new-order unique key | Một point read, ít lặp | Có thể không đáng cache |
| Large raw export | Streaming hàng triệu rows | Không nên nhét toàn bộ vào RAM cache |

Một dữ liệu có thể **ít được đọc nhưng tính rất đắt** vẫn đáng cache nếu kết quả được tái sử dụng đủ lần và chi phí lưu nhỏ. Ngược lại, một query rất rẻ, kết quả lớn và không lặp có thể làm cache tốn hơn nguồn.

## 9. Độ mới dữ liệu là ràng buộc kinh doanh

Trước khi cache, hỏi: **người dùng được phép nhìn dữ liệu cũ tối đa bao lâu?**

| Dữ liệu | Độ trễ chấp nhận có thể có | Cách dùng cache |
|---|---|---|
| Danh sách quốc gia | Hàng giờ/ngày theo version | Local hoặc shared cache |
| Mô tả sản phẩm | Giây/phút tùy chính sách | TTL + invalidation |
| Bảng xếp hạng xem nhiều | Vài phút | Cache kết quả aggregate |
| Dự báo/counters thống kê | Giây/phút tùy UX | Có nhãn cập nhật |
| Giá đang khuyến mại | Có thể rất ngắn | Cache để hiển thị, revalidate khi mua |
| Tồn kho để giữ chỗ | Không chấp nhận dùng bản cũ quyết định | Authoritative conditional write |
| Quyền truy cập bị thu hồi | Có thể cần hiệu lực gần tức thì | Token/version/revocation strategy |
| Payment status | Không được tự xác nhận từ cache cũ | Source/outcome lookup |

Các khoảng chỉ là **ví dụ phân loại**, không phải mặc định. “Được phép stale 60 giây” nên được ghi rõ trong data/API contract, bao gồm tình huống invalidation event bị trễ, cache mất kết nối hoặc database đang failover.

### 9.1. Freshness khác TTL

TTL 60 giây không tự chứng minh giá trị tối đa chỉ cũ 60 giây:

~~~text
T=0     Source price = 100, cache populate TTL 60s.
T=1     Source price = 120.
T=59    Cache vẫn trả 100.
~~~

Giá trị trả có thể đã cũ gần 58 giây. Nếu có **stale-while-revalidate** sau TTL, tuổi dữ liệu có thể còn cao hơn. Nếu clock/cache/replication cho phép refresh từ một replica cũ, TTL kể từ lúc cache population còn không phản ánh tuổi của chính dữ liệu.

Cần phân biệt:

- **Cache entry lifetime:** entry tồn tại bao lâu trong cache.
- **Source version age:** bản sao đã đi sau nguồn bao xa.
- **Staleness budget:** doanh nghiệp chấp nhận lệch bao lâu.
- **Invalidation delay:** mất bao lâu sau commit để cache bỏ bản cũ.

## 10. Dung lượng giá trị và số lượng khóa

Cache thường dùng bộ nhớ hạn chế hoặc storage tính phí cao cho mỗi byte. Quyết định caching phải xét:

1. Giá trị trung bình và p99 lớn bao nhiêu?
2. Có bao nhiêu unique keys đang active?
3. Mỗi entry cần bao nhiêu metadata (key, TTL, hash, object overhead)?
4. Có nhiều tenants/regions phải giữ cùng bản sao không?
5. Data có được nén/serialize hiệu quả không?
6. Có fan-out nhân nhiều variants của cùng một item?
7. Cần bao nhiêu headroom để tránh eviction storm?
8. Cần replicate cache cho availability không, và chi phí nhân bản là bao nhiêu?

Ước lượng đơn giản:

\[
M_{\mathrm{raw}}\approx N_{\mathrm{entries}}\times
(S_{\mathrm{key}}+S_{\mathrm{value}}+S_{\mathrm{overhead}})
\]

Ví dụ giả định có 2 triệu entries, mỗi entry trung bình 1 KiB tính cả key và metadata:

\[
M_{\mathrm{raw}}\approx 2.000.000\ \mathrm{KiB}
\approx 1{,}91\ \mathrm{GiB}.
\]

Đó mới là **dung lượng biểu diễn giả định**, chưa tính allocator fragmentation, eviction headroom, replication, snapshots, overhead runtime và thực tế phân phối entry sizes. Không chọn node chỉ bằng cách chia payload trung bình cho RAM máy.

## 11. Working set: chỉ cache phần dữ liệu đang dùng

**Working set** là nhóm keys được truy cập đủ thường xuyên trong khoảng thời gian có ý nghĩa. Một cache không cần chứa cả database, mà cần giữ những keys mà đọc lại có lợi.

~~~text
Source database: 500 triệu product/item records.
Last 10-minute active keys: 80.000.
Top 5.000 keys chiếm 75% reads.
~~~

Một cache chứa top hot keys có thể tạo phần lớn lợi ích mà không phải mua RAM đủ cho 500 triệu records.

> **Ưu tiên cache dữ liệu có khả năng được truy cập lại trước khi hết hạn hoặc bị đẩy ra**, không cache chỉ vì dữ liệu tồn tại.

Nếu dữ liệu được đưa vào cache một lần rồi không được đọc lại, thao tác populate thêm network/serialization/storage nhưng ít lợi ích. Đây là **cache pollution**.

## 12. Hit ratio và miss ratio: các chỉ số cơ bản

\[
\text{Hit ratio}=\frac{\text{cache hits}}{\text{lookups}}
\qquad
\text{Miss ratio}=1-\text{Hit ratio}.
\]

Ví dụ 100.000 lookups:

~~~text
Hits:    85.000
Misses:  15.000

Hit ratio = 85%
Miss ratio = 15%
~~~

Nhưng hit ratio không đủ đánh giá lợi ích:

- 85% hits có thể là những key nguồn vốn chỉ mất 1 ms, còn 15% misses là queries 2 giây.
- Cache có thể lưu nhiều empty/error responses để “tăng hit” sai nghĩa.
- Cache hit có thể trả stale value trái contract.
- Source read amplification có thể vẫn cao vì mỗi miss tạo nhiều retries.
- Hit rate tổng có thể che một tenant có hit rate gần 0.
- Hit rate cao có thể do một vài keys rất nóng, còn bộ nhớ bị chiếm bởi keys lạnh.

Nên đo **hit ratio theo operation, value class, tenant và độ lớn**, đồng thời đo **latency/chi phí tiết kiệm được**, không chỉ nhắm 99% bằng mọi giá.

## 13. Quyết định cache dựa trên lợi ích kỳ vọng

Một mô hình đơn giản cho độ trễ trung bình:

\[
E[L]\approx
h\cdot L_{\mathrm{hit}}+
(1-h)\cdot L_{\mathrm{miss}},
\]

trong đó `h` là xác suất cache hit, `L_hit` là latency đường hit và `L_miss` là latency đường miss (có thể gồm populate).

Ví dụ giả định:

~~~text
Source read không cache:       40 ms
Cache hit:                      3 ms
Cache miss:                    45 ms
Hit rate:                      80%
~~~

\[
E[L]\approx 0{,}8\times3+0{,}2\times45
=11{,}4\ \mathrm{ms}.
\]

Giảm trung bình so với 40 ms, nhưng **không suy được p99**: miss path có thể timeout hoặc bị stampede. Công thức sơ bộ cho số source reads nếu mỗi miss tạo đúng một truy vấn và bỏ qua refresh/prefetch:

\[
Q_{\mathrm{source}}\approx Q_{\mathrm{requests}}\times(1-h).
\]

10.000 GET/s và hit rate 90% có thể còn khoảng 1.000 source reads/s; thực tế còn refresh, invalidation, retry, warm-up và misses đồng thời.

Một quyết định cache tốt cần đo **độ trễ, bytes/CPU/capacity tiết kiệm, chi phí cache và rủi ro dữ liệu cũ**. Cache hit cao không phải đích cuối cùng.

## 14. “Giá trị” của một cache entry

Một mô hình định hướng:

\[
\mathrm{Benefit}(k)\approx
\mathrm{Expected\ reused\ reads}(k)
\times \mathrm{Source\ work\ saved\ per\ hit}(k)
-\mathrm{Cache\ costs}(k).
\]

Cache costs gồm population, storage, network, replication, serialization, invalidation, xử lý outage, giám sát và cả **business cost của stale data**.

| Ứng viên | Reuse | Source cost | Dung lượng | Staleness risk | Nhận xét |
|---|---|---|---|---|---|
| Product detail hot | Cao | Vừa | Nhỏ | Quản lý được | Rất phù hợp |
| Hóa đơn PDF riêng ít đọc | Thấp | Có thể cao | Rất lớn | Nhạy cảm | Object store/CDN có thể tốt hơn RAM |
| Top-20 category | Cao | Aggregate tốn | Nhỏ | Cho phép vài phút | Cache/materialize tốt |
| Available stock dùng để confirm | Cao | Có thể vừa | Nhỏ | Rất cao | Không dùng cache làm authority |
| Report filter tùy ý hiếm gặp | Thấp | Cao | Khó dự đoán | Tùy | Dùng report job/materialization |

Không đánh đồng **có thể cache** với **nên cache trong Redis**. File lớn ít đổi có thể hợp với object storage/CDN; cấu hình nhỏ có thể hợp với in-process cache.

## 15. Dữ liệu lý tưởng để cache

Các ứng viên điển hình:

1. Danh mục tĩnh: mã quốc gia, loại sản phẩm, metadata không nhạy cảm.
2. Chi tiết sản phẩm nóng: tên, mô tả, hình ảnh, thuộc tính gần như bất biến.
3. Danh sách phổ biến: featured products, top categories, trending items.
4. Kết quả đọc phải tổng hợp nhiều lần lookup hoặc transform tốn CPU.
5. User preference ít đổi, với key và quyền riêng từng user/tenant.
6. Tính toán deterministic đắt, có input/version ổn định.
7. Feature/configuration data **nếu** có cơ chế emergency invalidation phù hợp.
8. Thống kê mang tính trình bày, cho phép eventual consistency.
9. Reference data có phiên bản/chu kỳ phát hành rõ ràng.
10. Read projection có thể tái dựng từ authoritative source.

Tiêu chí chung là **reuse cao, chi phí lấy lại đủ lớn, kích thước có thể kiểm soát, cho phép stale theo contract và có đường hồi phục khi cache mất**.

### 15.1. Tách những field có độ biến động khác nhau

Một product document:

~~~json
{
  "sku": "SKU-A",
  "title": "Tai nghe",
  "description": "Mô tả dài",
  "listPrice": 500000,
  "promotionPrice": 420000,
  "availableToSell": 3,
  "catalogVersion": 104
}
~~~

Không nhất thiết cache **nguyên document** với một TTL:

- `title/description`: thay đổi ít, có thể cache lâu hơn.
- `promotionPrice`: hiển thị có thể cache có kiểm soát, nhưng phải tính lại/xác nhận tại checkout.
- `availableToSell`: snapshot biến động, **không làm căn cứ duy nhất cho việc reserve**.
- `catalogVersion`: hỗ trợ versioned key/invalidation.

Tách các projection phù hợp giúp tránh để một field thay đổi liên tục buộc cả object bị invalidate hoặc một field cần mạnh bị kéo theo TTL dài.

## 16. Dữ liệu không nên cache một cách ngây thơ

| Loại | Nếu cache sai | Hướng xử lý |
|---|---|---|
| Stock availability để reserve | Oversell / từ chối sai | Conditional write ở nguồn |
| Payment completion/outcome | Báo thành công khi chưa commit | Authoritative outcome lookup |
| Account balance dùng để chuyển tiền | Vượt giới hạn | Ledger/transaction phù hợp |
| Quyền truy cập vừa bị thu hồi | Truy cập trái phép | Revocation/version validation |
| Giá chốt đơn/coupon quota | Sai giá/quota | Revalidate theo luật giao dịch |
| PII hoặc private fields | Lộ xuyên tenant/user | Encryption/permissions/minimization |
| Raw export hàng GiB | RAM pressure/eviction | File/object storage |
| Random one-off keys | Hit thấp, cache pollution | Đọc source |
| Dữ liệu bản gốc duy nhất | Cache mất là mất nghiệp vụ | Durable data store |
| OTP/secrets | Lộ hoặc tái sử dụng sai | Thiết kế chuyên biệt theo threat model |

Không phải mọi dữ liệu nhạy cảm đều **cấm** cache; session/security systems có thể có cache chuyên dụng với quy tắc bảo mật và thu hồi. Nhưng shared public cache không được dùng cho dữ liệu đó chỉ vì muốn nhanh.

## 17. Object cache và query-result cache

**Object cache:**

~~~text
product:t01:SKU-A -> ProductView
product:t01:SKU-B -> ProductView
~~~

**Query-result cache:**

~~~text
search:t01:category=headphones:sort=popular:page=1
  -> [SKU-A, SKU-B, SKU-C]
~~~

| Tiêu chí | Object cache | Query-result cache |
|---|---|---|
| Key | Business ID + scope/version | Filters/sort/page/locale/tenant |
| Reuse | Nhiều endpoints dùng cùng object | Nhiều requests query giống hệt |
| Invalidation | Theo object ID | Một update ảnh hưởng nhiều query keys |
| Cardinality | Theo số objects hoạt động | Có thể bùng nổ theo tổ hợp filters |
| Dung lượng | Payload per object | Có thể lặp data trong nhiều lists |
| Freshness | Kiểm tra per object/version | Cần đúng cả tập kết quả |

Query-result caching chỉ hữu ích khi các truy vấn có thể **chuẩn hóa thành một tập nhỏ lặp lại**. Nếu mỗi request có hàng chục filters tùy ý, cache key cardinality có thể quá lớn và hit thấp.

## 18. Cache key phải bao gồm mọi biến ảnh hưởng kết quả

Ví dụ:

~~~text
Bad:
  "search:headphones"

Better:
  "search:v3:tenant=t01:locale=vi:category=headphones:
   sort=popular:page=1:currency=VND:visibility=public"
~~~

Nếu giá khác theo currency, discount theo user group hoặc kết quả giới hạn theo tenant, **thiếu các biến trong key có thể trả sai dữ liệu hoặc lộ thông tin**.

Một key ổn định có thể gồm:

~~~text
<app>:<view>:<schemaVersion>:<tenant>:<businessId>:<variant>

shop:product:v4:t01:SKU-A:vi-VN
shop:category-top:v2:t01:headphones:week-2026-W46
shop:profile-view:v3:t01:u42:basic
~~~

Không lưu password, access token hoặc raw PII vào key; dùng opaque ID/hash đúng semantics. Đừng cache toàn bộ private response cho nhiều users dưới cùng một key. **Authorization vẫn phải được kiểm tra mỗi request theo threat model**, trừ khi cache chính sách quyền có hợp đồng bảo mật tương đương.

## 19. Cache in-process, distributed hay edge?

| Tầng | Ưu điểm | Hạn chế | Ví dụ |
|---|---|---|---|
| **In-process L1** | Rất nhanh, không network | Bản sao riêng mỗi instance, invalidation khó | Config/reference nhỏ |
| **Distributed L2** | Chia sẻ giữa instances | Network, hot keys, cache outage | Product views |
| **CDN/edge** | Gần client, giảm origin traffic | Cache-control/private/public/region invalidation | Static assets |
| **Browser/client** | Có thể không cần HTTP request | Khó ép refresh, client khác nhau | Versioned assets |
| **Materialized view** | Tối ưu phép tính/query gốc | Pipeline, lag, rebuild | Daily rankings |
| **Object storage** | Tốt cho file lớn, retention dài | Không giống cache RAM | Reports/images |

Càng nhiều tầng, càng nhiều nơi có thể giữ bản cũ. Một lệnh invalidate L2 **không tự xóa L1, CDN hoặc browser cache**. Cần xác định freshness **end-to-end**, đặc biệt với dữ liệu thay đổi quyền hoặc giá.

## 20. Cache-aside: đọc nguồn khi miss

~~~mermaid
flowchart TD
    A["GET product"] --> B["Read cache"]
    B --> C{"Entry hợp lệ?"}
    C -->|Có| D["Return cached value"]
    C -->|Không| E["Read NoSQL source"]
    E --> F["Populate cache với TTL/version"]
    F --> G["Return source value"]
~~~

**Cache-aside (lazy loading)** đặt việc kiểm tra và điền cache tại application.

Ưu điểm: chỉ cache keys thực sự được đọc; nguồn có thẩm quyền rõ; cache mất có thể phục hồi nếu source đủ năng lực chịu misses.

Nhược điểm: miss chậm; concurrent misses cùng key có thể làm database quá tải; update source cần invalidation; dễ xảy ra **read-populate race** nếu giá trị cũ được ghi lại sau khi nguồn đã đổi.

Cache-aside thường là điểm bắt đầu hợp lý cho read-heavy data có thể tái tạo, **không có nghĩa phù hợp với mọi business state**.

## 21. Các chiến lược ghi cache và tính phù hợp dữ liệu

| Chiến lược | Ý tưởng | Phù hợp | Rủi ro |
|---|---|---|---|
| **Cache-aside** | Miss đọc source rồi populate | Reads lặp, tái tạo dễ | Stale và race khi điền cache |
| **Write-through** | Lớp ghi cập nhật cache và nguồn theo protocol | Muốn cache sẵn sau write | Atomicity giữa hai hệ |
| **Write-around** | Write source, không populate cache | Ghi nhiều, ít đọc | Read đầu miss |
| **Write-behind/back** | Nhận ghi trong cache, flush nguồn sau | Workload chuyên biệt | Mất write nếu cache lỗi trước durable flush |
| **Read-through** | Cache layer fetch nguồn khi miss | Thư viện/service có hỗ trợ | Dependency/policy khó quan sát |
| **Refresh-ahead** | Làm mới hot entries trước TTL | Keys nóng, stable | Background load |

**Write-through không tự bảo đảm transaction nguyên tử giữa cache và NoSQL.** Source commit thành công nhưng cache update thất bại vẫn có thể xảy ra. Write-behind nguy hiểm hơn nếu cache là nơi duy nhất giữ mutation chưa bền; không phù hợp cho Payment/Reservation nếu thiếu durable log và giao thức chính xác.

Chọn dữ liệu trước, rồi chọn strategy: catalog description có thể cache-aside; stock reservation cần commit nguồn; analytics aggregates có thể eventual; business event ledger cần durability.

## 22. TTL theo loại dữ liệu, không phải một con số cho mọi key

| Cache class | TTL giả định thử nghiệm | Điều kiện |
|---|---:|---|
| Country code list | 24 giờ | Reference version và update policy |
| Product description | 10 phút | Invalidate khi editor publish |
| Trending list | 1 phút | Hiển thị timestamp |
| Feature config | 30 giây | Emergency kill switch không chỉ dựa TTL |
| Read-only summary | 5 phút | Có cutoff/freshness label |
| User profile projection | 30 giây | Scope và invalidation đúng user |
| Inventory display hint | 1–5 giây | Checkout revalidate nguồn |
| Permission data | Không chọn tùy tiện | Security revocation contract |

Các con số chỉ minh họa. TTL phải dựa trên **frequency of change, freshness budget, chi phí miss, invalidation và source capacity**.

### 22.1. TTL thấp có thể gây miss storm

Hot key nhận 20.000 GET/s, TTL 1 giây. Khi key hết hạn, nhiều requests có thể đồng thời miss và gọi database trước khi một request kịp populate. TTL thấp giảm thời gian giữ bản cũ nhưng có thể tăng tải nguồn khi thiếu chống stampede.

TTL cao giảm miss, nhưng nếu invalidation thất bại thì bản cũ tồn tại lâu hơn. **TTL không thay thế explicit invalidation** khi business cần cập nhật hiệu lực nhanh.

## 23. Negative caching: khi nào cache “không có dữ liệu”?

~~~text
GET product:SKU-NOT-FOUND
  -> DB xác nhận NOT_FOUND
  -> cache marker NOT_FOUND với TTL ngắn
  -> request lặp có thể trả 404 từ cache
~~~

Lợi ích: giảm truy vấn lặp tới ID sai/không tồn tại.

Rủi ro:

- Key có thể được tạo ngay sau cache populate.
- DB timeout hoặc permission denied **không đồng nghĩa NOT_FOUND**.
- Cache shared không được lộ sự tồn tại của object người khác.
- Bot gửi rất nhiều random IDs có thể làm negative cache bùng cardinality.
- Cần invalidate marker khi tạo object nếu phải thấy ngay.

Chọn TTL ngắn, giới hạn số negative entries, phân biệt **ABSENT, FORBIDDEN, TIMEOUT, UNKNOWN**. Không biến lỗi mạng thành “không tồn tại”.

## 24. Cache kết quả tổng hợp thay vì toàn bộ events

Một dashboard hiển thị top 20 sản phẩm, trong khi nguồn chứa hàng triệu view events:

~~~text
Input: 5 triệu events/ngày.
Output: 20 SKU và score cho cửa sổ 5 phút.
~~~

Có thể lưu:

~~~json
{
  "windowStart": "2026-11-14T10:00:00Z",
  "windowEnd": "2026-11-14T10:05:00Z",
  "updatedAt": "2026-11-14T10:05:12Z",
  "items": [
    {"sku": "SKU-A", "views": 1200},
    {"sku": "SKU-B", "views": 1050}
  ]
}
~~~

Cache nhỏ, read lặp, tránh fan-out nhiều partitions. Nhưng event late/replayed có thể khiến aggregate sai. Cần event dedup và **window/watermark/cutoff contract**, không chỉ TTL.

## 25. Cache một projection thay vì nguyên document

Nguồn:

~~~json
{
  "productId": "SKU-A",
  "publicInfo": {"name": "Tai nghe", "description": "..."},
  "supplierContracts": {"internalNote": "private"},
  "inventory": {"available": 3},
  "auditHistory": ["...large list..."]
}
~~~

Cache nguyên object có thể ngốn RAM, truyền fields không dùng, đưa thông tin nhạy cảm vào cache quyền rộng, buộc TTL ngắn vì stock biến động.

Public cache projection:

~~~json
{
  "sku": "SKU-A",
  "name": "Tai nghe",
  "description": "...",
  "imageUrl": "/images/SKU-A.png",
  "catalogVersion": 104
}
~~~

Projection admin/checkout cần cache namespace, authorization và TTL khác. Không chia sẻ payload chứa private fields rồi trông đợi UI ẩn chúng.

## 26. Read-populate race: invalidate vẫn có thể stale

~~~text
T1 Reader R miss cache, đọc DB version=7.
T2 Writer W cập nhật DB version=8.
T3 Writer W DEL cache key.
T4 Reader R ghi lại cache version=7 vừa đọc.
T5 Các requests tiếp theo đọc bản cũ v7.
~~~

Một số hướng khắc phục:

- Kèm **version**; chỉ thay cached value nếu version mới không thấp hơn.
- Version/generation keys, key mới đổi khi nguồn commit.
- Populate có điều kiện hoặc compare-and-set theo metadata.
- Chấp nhận cửa sổ stale với TTL/invalidation nếu nghiệp vụ cho phép.
- Với bước quyết định quan trọng, đọc/commit ở nguồn có thẩm quyền.

**Cache invalidation khó hơn gọi DEL(key)** vì còn thứ tự thực thi, reader đang fetch, network delay và crash.

### 26.1. Vì sao DB write rồi DEL chưa đủ?

~~~text
DB write commit -> DEL cache
~~~

Nó là pattern hữu ích nhưng không bảo đảm atomicity:

1. Process có thể crash sau DB commit nhưng trước DEL.
2. DEL có thể timeout.
3. Reader miss có thể populate giá trị cũ sau DEL.
4. L1/other region có thể chưa nhận invalidation.

Nếu chấp nhận eventual consistency, bổ sung TTL, version, repair và observability. Nếu quyết định không được stale, **cache không làm authority**.

## 27. Cache stampede / thundering herd

~~~text
Hot key: product:SKU-A
10.000 users mở trang cùng thời điểm.

Cache entry expires.
10.000 requests -> MISS
10.000 source GETs -> hot DB partition / overload.
~~~

Các biện pháp:

- **Single-flight:** các requests cùng key trong một process dùng chung một fetch.
- **Distributed lease:** một worker refill, các workers khác chờ hoặc trả stale được phép.
- **Stale-while-revalidate:** trả bản cũ có nhãn, refresh trong nền.
- **TTL jitter:** tránh nhiều keys cùng hết hạn.
- **Refresh-ahead/prewarming:** biết trước hot keys hoặc campaign.
- **Admission/rate limiting:** không vượt capacity source.

Single-flight **trong một process không đồng nghĩa một refill toàn cluster**. Distributed lock cần expiration/fencing và failure handling. Không để một lock hoặc cache outage làm requests chờ vô hạn.

## 28. Hot cache key: hotspot có thể chuyển chỗ

Khi SKU cực nóng nằm ở distributed cache, NoSQL giảm tải nhưng mọi GET có thể tập trung vào **một cache key/slot/node**.

Dấu hiệu: cache GET p99 tăng, node network saturation, CPU/event loop cao, connection pool wait; DB QPS giảm nhưng API chưa nhanh.

Cách xử lý:

- L1 local cache ngắn hạn cho hot value.
- CDN cho public immutable assets.
- Read replicas/client-side cache nếu platform hỗ trợ.
- Đa bản sao read-only có cơ chế invalidation đúng.
- Giảm kích thước value; cache projection thay full object.
- Request coalescing hoặc pre-aggregation.

**Cache chuyển tải khỏi database nhưng có thể tạo hotspot mới**. Cần theo dõi cả cache owner lẫn DB owner.

## 29. Eviction khác TTL

TTL hết hạn do chính sách thời gian; **eviction** loại entry sớm do áp lực bộ nhớ.

Các chính sách phổ biến tùy engine:

- **LRU:** giữ những key mới được dùng gần đây.
- **LFU:** giữ những key được dùng thường xuyên.
- **TTL-aware:** ưu tiên entries sắp/hết hạn.
- **Size/cost aware:** cân nhắc dung lượng và chi phí phục hồi nếu hỗ trợ.
- **Random:** có thể loại hot entry và gây miss bất ngờ.

Một scan tuần tự lớn có thể làm cache pollution và đẩy hot entries. Theo dõi eviction rate, allocated memory, fragmentation, hit ratio per key group và nguồn misses. **Entry chưa hết TTL không đồng nghĩa nó chắc chắn còn trong cache.**

## 30. Cache miss phải là đường chạy hợp lệ

~~~text
Cache down / key evicted / TTL expired
  -> application kiểm tra deadline/quyền
  -> read source có hạn mức
  -> trả response hoặc degraded outcome
~~~

Một kiến trúc tốt chuẩn bị:

- Source chịu được bao nhiêu cold misses?
- Bounded concurrency và circuit breaker có chặn overload?
- TTL jitter, request coalescing, gradual warmup?
- Retry/deadline và stale-if-error contract?
- Dữ liệu quan trọng có nguồn durable để tái tạo?
- Nếu cache trống sau restart, ứng dụng có hồi phục không?

Cache thường **tùy chọn về tính đúng đắn** nhưng có thể **quan trọng về năng lực phục vụ**. Nếu hệ chỉ mua DB capacity đủ chịu 5% miss, cache outage có thể gây overload nghiêm trọng; phải có degrade/queue/admission plan.

## 31. Cache không được là bản duy nhất của nghiệp vụ quan trọng

Không lưu duy nhất những dữ liệu sau vào một cache có thể mất:

- Order đã CONFIRMED.
- Payment receipt/outcome hoặc giao dịch cần đối soát.
- Reservation hold đã cấp nhưng chưa ghi bền.
- Business intent đang PENDING sau client timeout.
- Audit event duy nhất của thao tác nhạy cảm.

Nếu cache lỗi làm mất các thông tin này, nó đang được dùng như **primary database/durable queue** nhưng thiếu hợp đồng durability.

~~~text
Transactional source:
  durable records và authoritative outcome

Cache:
  derived representation có thể evict/rebuild

Outbox/event log:
  durable integration intent + replay/idempotency
~~~

Có hệ dùng Redis hoặc in-memory data grid như datastore chính với persistence/replication được thiết kế chuyên biệt. Khi ấy phải **đánh giá nó như một database có source-of-truth contract**, không mặc định đặc điểm của cache có thể xóa.

## 32. Cache dữ liệu liên quan quyền truy cập và tenant

User có quyền xem document tại T0; tại T1 quyền bị thu hồi. Nếu cache vẫn trả một response cũ mà không xác minh quyền, đó là **lỗi bảo mật**.

Các biện pháp:

1. Cache base public/non-sensitive data và kiểm tra quyền mỗi request.
2. Nếu personalized cache, key bao gồm tenant/user/scope/version phù hợp.
3. Có revocation token/generation hoặc invalidation event đúng latency requirement.
4. Không trả cached response của user A cho user B vì URL giống.
5. Logout/role change phải có quy tắc phiên bản session/quyền.
6. Tách public CDN cache khỏi private authenticated responses.
7. TTL ngắn là biện pháp bổ sung, không thay thế revoke khi cần hiệu lực tức thì.
8. Không log raw cached payload hoặc key chứa secrets/PII.

Cache một authorization decision có thể hợp lệ trong hệ chuyên biệt, nhưng phải định nghĩa **thời gian hiệu lực, cơ chế revoke và xử lý khi validation service lỗi**.

### 32.1. Multi-tenant cache key

Sai:

~~~text
cacheKey = "product:SKU-A"
~~~

Nếu SKU-A ở nhiều tenants nhưng giá/dữ liệu khác, các tenants có thể nhận nhầm response. Key có scope:

~~~text
product:v4:tenant=t01:SKU-A:currency=VND
~~~

Kể cả khi key phân biệt tenant, application vẫn phải **xác thực user thuộc tenant đó**, không tin tùy ý tenantId từ client.

## 33. Query parameters có thể làm nổ cardinality

Một endpoint:

~~~text
GET /analytics?from=2026-11-14T10:00:01.003Z
               &to=2026-11-14T10:00:59.871Z
~~~

Nếu mọi request có time window khác nhau đến mili-giây, mỗi tổ hợp tạo một key. Có thể:

- Chọn fixed windows theo phút nếu semantics cho phép.
- Chuẩn hóa thứ tự params, timezone, encoding và defaults.
- Chỉ cache report templates/filters phổ biến.
- Materialize aggregates theo fixed buckets rồi combine.
- Không cache requests quá đặc thù và hiếm lặp.
- Gắn algorithm/schema version vào key.

**Không tự làm tròn thời gian** khi báo cáo tài chính hoặc truy vấn đòi ranh giới chính xác; normalization phải giữ đúng semantics.

## 34. MongoDB: cache projection theo truy vấn được lặp

Ví dụ point query public product:

~~~javascript
db.products.findOne(
  { tenantId: "t01", sku: "SKU-A" },
  {
    projection: {
      _id: 0,
      sku: 1,
      title: 1,
      description: 1,
      imageUrl: 1,
      catalogVersion: 1
    }
  }
);
~~~

Nếu một vài products rất nóng, application có thể cache **projection nhỏ** thay nguyên document.

Lưu ý:

- Query phải có index đúng schema/access pattern.
- Đọc từ secondary có thể stale theo read preference/concern.
- Tenant/locale/price variants cần key khác.
- Product update cần invalidation/TTL/version để tránh read-populate race.
- Change stream invalidation có thể lag hoặc gián đoạn; cần resume/repair.

**Cache không thay thế index/data modeling.** Nếu miss path là unbounded collection scan, cache chỉ tạm che vấn đề; cold start/expiry vẫn có thể làm hệ quá tải.

## 35. DynamoDB: giảm read capacity trên hot items

Một table có product item được GET nhiều lần:

~~~text
Source:
  Get Product by tenantId + sku

Cache:
  catalog:tenant=t01:sku=SKU-A:v4 -> ProductView
~~~

Cache có thể giảm source reads/capacity. Nhưng:

- Source vẫn phải chịu cold misses và retry storms theo kế hoạch.
- Cache hot key vẫn có thể thành hotspot mới.
- Cache hit không mặc nhiên tương đương strongly consistent read.
- Conditional writes/transactions để reserve stock vẫn phải ở nguồn.
- Secondary index/projection có thể có freshness semantics khác nguồn.
- Invalidation qua stream có thể tới muộn.

Với dịch vụ caching tích hợp, cần đọc **consistency, TTL, invalidation và failure behavior của chính phiên bản/chế độ dùng**. Không mặc định một write commit sẽ lập tức làm mọi cached reads thấy bản mới.

## 36. Cassandra/ScyllaDB: cached read patterns và hot partitions

Một wide-column table được thiết kế theo partition-key query:

~~~text
events_by_device_day:
  PK = deviceId + day
  repeated reads latest 20 events

App cache:
  "latest-20:device-42:day=2026-11-14" -> EventSummary
~~~

Cần xét:

- Latest events thay đổi mỗi khi có record mới; TTL/invalidation phải phù hợp.
- Cache một large scan có thể làm value rất lớn.
- Tombstones/compaction có thể làm miss path đắt hơn hit path.
- Với hot partition do writes, **đổi data model/partitioning** có thể quan trọng hơn thêm cache.
- Các consistency levels có hợp đồng khác; cache không được giả là đạt `LOCAL_QUORUM`.
- Replica/cache outage có thể dồn reads lại nguồn.

Cache hit không chứng minh read-your-writes. Nếu client vừa ghi event mới, ứng dụng phải có session logic/bypass hoặc revalidation phù hợp nếu cần nhìn thấy ngay.

## 37. Redis: distributed cache có chi phí và giới hạn riêng

Redis thường làm remote cache vì operations theo key hiệu quả, có TTL và eviction policy. Nhưng không mặc định:

- Redis GET miễn phí CPU/network.
- Mọi hit nhanh hơn in-process cache.
- Một hot key tự động phân phối đều trên các nodes.
- TTL đủ bảo vệ correctness.
- Redis Cluster multi-key operations luôn atomic xuyên slots.
- Cache luôn durable như một transactional source.

Ví dụ lệnh minh họa có placeholder:

~~~text
SET product:v4:t01:SKU-A:vi-VN <serialized-value> EX 300
GET product:v4:t01:SKU-A:vi-VN
DEL product:v4:t01:SKU-A:vi-VN
~~~

`<serialized-value>` đại diện bytes đã serialize, không phải cú pháp để copy chạy nguyên xi. Invalidation sau source commit cần xử lý race/version nếu contract freshness chặt.

Redis Cluster có hash slots: các keys có hash tag giống nhau có thể cùng slot, hữu ích cho một số multi-key operations nhưng cũng có thể tạo hot spot. Tên một key còn ảnh hưởng privacy, namespace và memory overhead.

## 38. Java: cache-aside ở tầng ứng dụng

Giả sử repository:

~~~java
public interface ProductRepository {
    ProductView findPublicView(String tenantId, String sku);
}

public record ProductView(
    String sku,
    String title,
    String description,
    long catalogVersion
) {}
~~~

Pseudocode Java để minh họa policy:

~~~java
public ProductView getProduct(String tenant, String sku) {
    String key = "product:v4:" + tenant + ":" + sku;

    ProductView cached = cache.getIfPresent(key);
    if (cached != null) {
        return cached;
    }

    ProductView current = repository.findPublicView(tenant, sku);
    if (current != null) {
        cache.put(key, current);
    }
    return current;
}
~~~

Đây là **pseudocode**, chưa có class cache cụ thể và chưa giải quyết negative caching, stampede, timeout hoặc stale refill. Với production dùng cache library có **maximum size/weight, TTL, metrics, loading coalescing và lifecycle** phù hợp.

Nếu app có 20 instances, mỗi instance L1 riêng. Một source update có thể cần invalidate 20 bản hoặc có TTL/version chấp nhận cửa sổ stale. Không được hiểu in-process cache là kho đồng bộ toàn cụm.

## 39. Versioned cache entry và tránh ghi lùi dữ liệu

Một cached value có thể mang source version:

~~~java
public record CachedProduct(
    ProductView value,
    long sourceVersion,
    long fetchedAtEpochMillis
) {}
~~~

Cần:

- Source cấp **monotonic version** đúng theo entity.
- Cache so sánh version **nguyên tử** nếu muốn từ chối stale populate.
- Invalidation/deletion có generation/tombstone để không hồi sinh bản cũ.
- Có session minimum version khi API yêu cầu read-your-writes.
- Không nhầm cache population timestamp với source data version.

Pseudocode:

~~~text
putIfNewer(key, candidate, version):
  atomically:
    old = cache[key]
    if allowedByGeneration(version, deletionMarker)
       and (old absent OR version > old.sourceVersion):
        cache[key] = candidate
    else:
        reject stale candidate
~~~

Không mặc định một cache library bất kỳ hỗ trợ đúng compare-and-set. Đặc biệt, “entry absent” sau DEL có thể cần generation marker để tránh old fetch điền lại stale data.

## 40. L1 + L2 + NoSQL: nhiều tầng, nhiều trạng thái

~~~mermaid
flowchart LR
    C["Client"] --> A["Application"]
    A --> L1{"L1 local cache"}
    L1 -->|miss| L2{"L2 distributed cache"}
    L2 -->|miss| DB["NoSQL source"]
    DB --> L2
    L2 --> L1
~~~

Ưu điểm: L1 tránh remote cache round trip; L2 chia sẻ giữa instances; source chịu misses cuối.

Nhược điểm:

- Invalidation phải đến cả L1 và L2, hoặc L1 có TTL/version bảo đảm.
- L1 có thể stale dù L2 đã mới.
- Mỗi tầng có timeout, eviction và khả năng outage riêng.
- Khi L2 down, nhiều L1 misses cùng dồn lên source.
- Cần đo riêng `L1-hit`, `L2-hit`, `source-miss` và logical request latency.

Thêm một tầng chỉ khi nó giải bottleneck được đo; không có quy tắc “càng nhiều tầng cache càng tốt”.

## 41. Prewarm có chọn lọc

Một chiến dịch có thể biết trước 200 SKU được xem nhiều:

~~~text
Before campaign:
  populate public ProductViews for 200 hot SKU.
  verify source version and TTL.
  throttle cache warm-up reads.
  monitor cache memory and source load.
~~~

Ngược lại, load 10 triệu products lúc startup có thể gây scan đắt, evictions, nhiều instances warmup cùng lúc và data stale ngay khi chưa dùng.

**Chọn key theo hotness dự đoán và giới hạn ngân sách**, sau đó đo hit rate thật. Prewarm không thay cache-aside, data modeling hoặc source capacity planning.

## 42. HTTP/CDN caching: representation và quyền

Nếu cache ở CDN/browser:

- Response là public hay private?
- Có cookies, Authorization hoặc personalized discounts?
- `Cache-Control`, `ETag`, `Last-Modified` và `Vary` phản ánh đúng response variants?
- Có stale-if-error/while-revalidate được phép?
- Invalidation tới nhiều edge locations mất bao lâu?
- Có cache nhầm 404/500/redirect?
- Schema/key generation có đổi khi deploy?

Một ảnh với content-addressed URL có thể cache lâu vì ảnh mới sinh URL mới. Endpoint `/account/balance` thì không được public-cache chỉ vì HTTP GET.

**Cache placement và access control là một quyết định chung**, không chọn TTL riêng rẽ khỏi nơi lưu và người được đọc.

## 43. Quy trình chọn một dữ liệu để cache

Bảy bước:

1. **Phân loại:** immutable, slowly changing, volatile, transactional, regulated?
2. **Đo reuse:** per-key QPS, unique keys, repeated reads, source cost.
3. **Định nghĩa freshness:** stale tối đa, đọc sau ghi, yêu cầu invalidation.
4. **Đánh giá business/security risk:** có tác động payment, stock, quyền, PII?
5. **Tính size/cardinality/scope:** có fit working set và tenant isolation?
6. **Chọn tier/strategy:** local, Redis/shared, CDN, projection hoặc không cache.
7. **Thử nghiệm:** hit/miss, source load, p95/p99, evictions, correctness, outage.

Một mẫu data contract minh họa:

~~~yaml
cacheCandidate: productPublicView
sourceOfTruth: product-service/NoSQL
key: "catalog:v4:{tenantId}:{sku}:{locale}"
fields: [sku, title, description, imageUrl, catalogVersion]
freshness:
  targetSeconds: 60
  invalidation: "after confirmed publish event"
  maxStaleOnFailureSeconds: 120
security:
  scope: tenant
  pii: false
capacity:
  estimatedWorkingSetEntries: 200000
  averageEntryBytes: 1500
strategy:
  tier: distributed
  mode: cache-aside
  ttlSeconds: 60
fallback: "bounded source read"
validation:
  - "source QPS and cache hit/miss"
  - "version mismatch and stale age"
  - "eviction and stampede metrics"
~~~

Đây là **YAML mô tả quyết định thiết kế**, không phải cấu hình trực tiếp cho Redis hoặc NoSQL. Mọi số liệu phải được xác nhận bằng workload thật.

## 44. Ma trận đánh giá ứng viên cache

| Tiêu chí | Ít phù hợp | Phù hợp |
|---|---|---|
| Reuse | Key gần như chỉ đọc một lần | Cùng key đọc liên tục |
| Source cost | Lookup rất rẻ | Tốn I/O, fan-out, transform |
| Độ ổn định | Giá trị đổi liên tục | Ít thay đổi |
| Staleness | Gây lỗi nghiệp vụ nghiêm trọng | Chấp nhận có giới hạn |
| Size/cardinality | Lớn và không kiểm soát | Nhỏ, working set rõ |
| Invalidation | Không biết khi nào đổi | Có version/event hợp lệ |
| Tái tạo | Không có nguồn bền | Có thể rebuild |
| Bảo mật | Dễ lộ/xuyên tenant | Scope và quyền rõ |

**Không cộng điểm để bù cho vi phạm bảo mật hoặc bất biến nghiệp vụ.** Một dữ liệu có hit rate rất cao nhưng không được phép stale vẫn có thể bị loại khỏi generic cache path.

| Dữ liệu | Đánh giá |
|---|---|
| Reference dictionary | Ứng viên rất tốt |
| Public product view | Tốt với version/invalidation |
| Trending top-20 | Tốt nếu freshness/cutoff rõ |
| Inventory available-to-sell | Chỉ dùng làm gợi ý; không quyết định reserve |
| Payment outcome | Lấy/đối soát từ nguồn có thẩm quyền |
| Sensitive OTP/secret | Hệ security store chuyên biệt |
| Ad hoc report tùy ý | Job/materialization có thể tốt hơn RAM cache |

## 45. Observability: chứng minh cache thực sự có ích

| Nhóm | Metric | Câu hỏi |
|---|---|---|
| Adoption | Hit/miss rate theo operation | Endpoint nào được lợi? |
| Latency | L1/L2 hit p95/p99, source miss p99 | Hit có nhanh? |
| Source | DB read QPS/CPU/IOPS/capacity | Tải nguồn giảm bao nhiêu? |
| Working set | Unique keys, top hot keys | RAM có lưu giá trị đáng giữ? |
| Memory | Used memory, p99 entry size | Có nguy cơ OOM? |
| Eviction | Eviction count/rate | Hot keys có bị đẩy ra? |
| Correctness | Stale-age/version mismatch | Có vượt freshness budget? |
| Stampede | Concurrent fills per key | Miss có tạo burst? |
| Invalidation | Event lag/failure/retry | Update lan nhanh tới đâu? |
| Security | Cross-tenant/key-scope failures | Có lộ dữ liệu? |
| Availability | Cache timeout, source fallback | Cache outage ảnh hưởng SLO? |
| Cost | Cache spend vs saved source capacity | Có đáng đầu tư? |

Tách metrics theo nhóm:

~~~text
catalog-description:  hit 95%, low stale risk
category-top20:       hit 90%, accepts 60s staleness
order-detail:         hit 20%, high unique-key churn
inventory-hint:       hit 75%, checkout must revalidate
~~~

Một hit ratio tổng đẹp có thể che nhóm có hiệu quả kém hoặc rủi ro cao. **Không đo chỉ successful cache hits rồi loại misses/timeouts khỏi p99**.

## 46. Benchmark warm cache, cold cache và failure

Để biết một nhóm dữ liệu đáng cache không, cần thử **cả trạng thái thuận lợi và bất lợi**, không chỉ hit latency.

| Kịch bản | Cache state | Workload | Điều cần quan sát |
|---|---|---|---|
| A | Không cache | Normal traffic | Baseline latency và source capacity |
| B | Warm cache | Normal traffic | Hit ratio, saved reads, p99 |
| C | Cold cache | Normal traffic | Miss burst, warm-up |
| D | Warm cache | Peak traffic | Hot cache key, network |
| E | TTL expiry đồng loạt | Hot-key burst | Stampede |
| F | Cache unavailable | Peak traffic | Fallback/admission |
| G | Source unavailable | Warm cache | Stale-if-error policy |
| H | Frequent updates | Read-heavy | Invalidation/stale-age |
| I | Tenant/role changed | Personalized access | No data leak |
| J | Rolling deployment | Cache schema đổi | Compatibility và cleanup |

Điều kiện pass/fail chọn trước:

- API p95/p99 vẫn đạt SLO.
- Source không bị dồn tải quá năng lực khi cold cache.
- Không có dữ liệu sai cross-tenant hoặc stale vượt contract.
- Cached stock không được dùng như authority để reserve.
- Cache outage không gây mất business write.
- Chi phí cache và vận hành tương xứng capacity nguồn tiết kiệm.

**Cold start, TTL expiry, bulk invalidation và failover có thể là những tình huống quan trọng nhất để chứng minh thiết kế.**

## 47. Capacity: working set và headroom

Ước lượng:

\[
M_{\mathrm{needed}}
\approx N_{\mathrm{hot}}\cdot S_{\mathrm{entry,avg}}
+M_{\mathrm{overheads}}+M_{\mathrm{headroom}}.
\]

Nếu 200.000 hot keys, mỗi entry trung bình 1,5 KiB:

\[
M_{\mathrm{data}}\approx 300.000\ \mathrm{KiB}
\approx 293\ \mathrm{MiB}.
\]

Đó chưa gồm fragmentation, metadata, replication/persistence, buffers hoặc entries lớn bất thường. Cần đo **phân phối kích thước**, không chỉ trung bình. Cache nhỏ quá gây evictions liên tục; quá lớn giữ cold data và tăng chi phí.

Chọn size theo **working-set reuse curve**: tăng thêm 1 GiB RAM cải thiện hit ratio, p99, source reads và cost bao nhiêu? Không cần cache bằng tổng kích thước NoSQL database.

## 48. Runbook khi cache khiến API chậm

Giả sử:

~~~text
Product GET p99:     75 ms -> 650 ms
Cache hit rate:      92% -> 40%
Evictions/minute:    100 -> 80.000
Source read QPS:     200 -> 5.000
Cache memory used:   95% of configured limit
~~~

Quy trình:

1. Xác định endpoint/tenant/key class bị ảnh hưởng.
2. Tách cache hit latency, miss path latency và DB query latency.
3. Xem eviction, memory pressure và key cardinality.
4. Tìm query variants hoặc bot tạo nhiều one-off keys.
5. Tìm TTL expiry/invalidation đồng loạt và stampede.
6. Đo source hot partitions, read capacity, throttling.
7. Dùng bounded concurrency/single-flight/rate limit để giảm miss burst.
8. Không giảm correctness: Payment/Inventory vẫn xác nhận ở nguồn.
9. Kiểm tra stale data, tenant scope và schema version.
10. Prewarm chọn lọc, không tải mọi key cùng lúc.
11. Theo dõi p99, source QPS, eviction và stale-age sau khôi phục.
12. Bổ sung fault tests và cache sizing policy sau incident.

Không tăng TTL cho mọi data class chỉ để cứu hit rate: việc đó có thể làm quyền truy cập, giá hoặc thông tin nhạy cảm bị cũ quá hạn.

## 49. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
|---|---|---|
| “Mọi GET nên cache” | One-off, private, stale risk | Phân tích access pattern |
| “NoSQL nhanh không cần cache” | Repeated reads vẫn tốn nguồn | Đo QPS, latency, cost |
| “Cache là source of truth” | Có thể mất/evict | Giữ durable source |
| “Hit rate 99% thì p99 tốt” | Miss tail vẫn rất chậm | Đo request p99 |
| “TTL 60s = dữ liệu không cũ quá 60s” | Source read có thể stale | Source version/freshness |
| “TTL càng ngắn càng tốt” | Stampede và miss overhead | Cân bằng theo contract |
| “DEL cache atomic với DB commit” | Crash/race qua hai hệ | Version/invalidation |
| “Eviction chỉ lúc TTL hết” | Memory policy có thể loại sớm | Eviction metrics |
| “Cache nguyên document tốt nhất” | RAM, private, volatile fields | Chọn projection |
| “Read QPS cao chắc cache tốt” | Unique-key churn | Đo reuse |
| “Ít đổi luôn an toàn” | Quyền bị thu hồi có hậu quả lớn | Business risk |
| “404 giống timeout” | Timeout không chứng minh absent | Negative cache cẩn thận |
| “Key chung cho nhiều tenants” | Lộ hoặc nhầm dữ liệu | Scope/version/authorization |
| “Đã cache tốt thì DB không cần capacity” | Cold misses có thể bùng | Fallback plan |
| “L1 tự đồng bộ mọi instances” | Mỗi process một bản | Invalidation/TTL |
| “CDN cache private như assets” | Cookies/auth/PII | Cache-control và quyền |
| “Cache giải mọi hot write” | Cache đọc không thay partitioning ghi | Sửa data model |
| “Hot Redis key scale tuyến tính” | Có node/slot bottleneck | L1/CDN/read spreading |
| “Tăng RAM luôn tăng hit mạnh” | Cold entries không reuse | Working set |
| “Cache xác nhận vé cuối” | Stale stock có thể oversell | Conditional commit nguồn |
| “Prewarm tất cả key” | Scan/eviction/overload | Warm hot set |
| “Miss là lỗi” | TTL/eviction bình thường | Miss path đúng, bounded |

## 50. Bài tập A — Quyết định dữ liệu nào nên cache

Một ứng dụng có workload giả định:

| Dữ liệu | Reads/giây | Updates/giây | Payload |
|---|---:|---:|---|
| Country codes | 2.000 | Gần 0 | 50 KiB toàn tập |
| Product details | 10.000 | 5 | 1,5 KiB/item |
| Live inventory | 5.000 | 3.000 | 100 B/item |
| Order details | 1.000 | 100 | 3 KiB/item |
| Top-20 products | 500 | Recompute mỗi phút | 5 KiB |
| Monthly CSV export | 1/ngày | Không áp dụng | 2 GiB |

Nhiệm vụ:

1. Phân loại thành nhóm in-process cache, distributed cache, CDN, object storage hoặc không cache.
2. Phân biệt cache **inventory display hint** với nguồn **reserve authority**.
3. Chọn TTL thử nghiệm và điều kiện invalidation từng ứng viên.
4. Dữ liệu nào nên dùng materialized view/aggregate thay vì cache raw records?
5. Vì sao 2 GiB CSV không hợp với một cache RAM phục vụ point reads?
6. Nếu Product có locale và currency variants, cache key phải có gì?
7. Khi Product được update, tránh stale read-populate thế nào?
8. Những metric nào chứng minh lợi ích và tính đúng đắn?
9. Cache mất toàn bộ trong flash sale, API phải có kế hoạch gì?
10. Dữ liệu nào cần mã hóa/tenant isolation?

## 51. Bài tập B — Tính hit, miss và chi phí

Giả định:

~~~text
Logical GET rate = 8.000 req/s
Cache hit rate = 75%
Cache hit latency = 2 ms
Cache miss latency = 50 ms
Một miss tạo 1 source read nếu không stampede.
~~~

Hãy:

1. Tính số hits/s.
2. Tính số misses/s và source reads/s.
3. Tính độ trễ kỳ vọng qua E[L].
4. Nếu hit rate lên 90%, source reads giảm bao nhiêu?
5. Vì sao không dùng E[L] để kết luận p99?
6. Nếu 100 clients cùng miss một hot key, thực tế nguồn có thể nhận bao nhiêu queries?
7. Single-flight có thể giảm bao nhiêu source requests nếu 100 misses xảy ra trên cùng một process?
8. Nếu nguồn đang lỗi, stale-if-error có phù hợp cho Payment outcome không?
9. Nếu eviction tăng, hit rate và chi phí thay đổi ra sao?
10. Thiết kế benchmark warm cache và cold cache cho endpoint này.

## 52. Bài tập C — Race giữa đọc, ghi và invalidation

Một item:

~~~text
Source version=10, cache empty.

Reader R:
  starts GET, sees version 10,
  pauses before populating cache.

Writer W:
  updates source to version 11,
  invalidates cache.

Reader R:
  resumes, puts version 10 into cache.
~~~

Hãy:

1. Vẽ timeline và chỉ ra vì sao DEL không đủ.
2. Dùng generation key hoặc versioned cache key để tránh race này ra sao?
3. Một atomic compare-and-set cần kiểm tra điều kiện gì?
4. Nếu entry đã bị DEL, metadata nào giúp ngăn R ghi lại v10?
5. Với TTL 30 giây, giá trị v10 có thể tiếp tục được đọc như thế nào?
6. Một client vừa đổi profile cần read-your-writes bằng cách gì?
7. Nếu R đọc từ replica lag, cần so version nào?
8. Khi dữ liệu đã bị xóa, tombstone/generation giúp gì?
9. Khi invalidation event mất, TTL/repair và alert phải như thế nào?
10. Tạo một concurrent test trong lab để phát hiện stale refill.

## 53. Bài tập D — Multi-tenant cache key an toàn

Response phụ thuộc:

~~~text
tenantId
sku
locale
currency
userMembershipTier
productCatalogVersion
~~~

Bài tập:

1. Viết một key canonical đầy đủ cho từng variant.
2. Nếu không muốn cache theo từng user, có thể cache base public data rồi tính discount riêng ra sao?
3. Vì sao không đưa raw access token vào key?
4. Khi membership tier đổi, invalidation/version xử lý thế nào?
5. Hai tenants có cùng SKU có được dùng cùng value không?
6. Quyền truy cập cần được kiểm tra ở đâu dù cache hit?
7. Public CDN có được cache response chứa personalized price không?
8. Negative caching với ID không tồn tại có thể tiết lộ điều gì?
9. Khi user logout, private browser cache phải có policy nào?
10. Những test nào phát hiện cross-tenant leakage?

## 54. Câu hỏi tự kiểm tra

1. Cache khác source of truth ở điểm nào?
2. Vì sao NoSQL nhanh vẫn có thể cần cache?
3. Mục đích của cache ngoài latency là gì?
4. Read QPS cao có đủ chứng minh cache tốt không?
5. Working set và reuse distance cho biết điều gì?
6. Read-to-update ratio có ích thế nào, và vì sao chưa đủ?
7. Dữ liệu ít đổi vẫn có thể không an toàn để cache vì sao?
8. TTL khác freshness/staleness budget thế nào?
9. Hit, miss, eviction và invalidation khác nhau ra sao?
10. Hit ratio cao có thể che loại request nào?
11. Negative caching phù hợp khi nào?
12. Vì sao DB timeout không nên cache thành NOT_FOUND?
13. Object cache khác query-result cache ở invalidation?
14. Cache key cần chứa những biến gì để tránh lẫn tenant?
15. Vì sao không cache raw PII hoặc token vào public namespace?
16. Khi nào CDN phù hợp hơn distributed RAM cache?
17. L1 in-process có ưu điểm và hạn chế nào?
18. Vì sao L1 + L2 làm invalidation phức tạp?
19. Cache-aside hoạt động thế nào khi miss?
20. Write-through có atomic với nguồn NoSQL không?
21. Write-behind có thể mất dữ liệu khi cache crash không?
22. Stampede xảy ra khi nào?
23. Single-flight khác distributed lease ở phạm vi nào?
24. TTL jitter giúp ngăn hiện tượng gì?
25. Hot Redis key có thể thành bottleneck mới ra sao?
26. LRU và LFU ưu tiên entry thế nào?
27. Cache miss có phải lỗi ứng dụng không?
28. Cache outage cần nguồn fallback chịu tải ra sao?
29. Có nên dùng cached stock để confirm giữ hàng?
30. Cached permissions phải hỗ trợ thu hồi ra sao?
31. Read-populate race có thể xảy ra sau DEL như thế nào?
32. Source version khác fetchedAt timestamp ra sao?
33. Product projection khác cache toàn document ở điểm nào?
34. DynamoDB cache có làm conditional write không còn cần thiết không?
35. Cache đọc Cassandra có tự đáp ứng consistency level của DB không?
36. MongoDB miss query thiếu index sẽ gây hậu quả gì lúc cold cache?
37. Prewarm cần giới hạn nguồn tải vì sao?
38. Tại sao export 2 GiB nên chuyển sang artifact/object storage?
39. Những metrics nào chứng minh saved source capacity?
40. Những tests nào bảo đảm không lộ dữ liệu xuyên tenant?

## 55. Tổng kết: cache đúng dữ liệu, không cache mọi thứ

Caching có ích khi nó giữ **bản sao được đọc lại nhiều lần, kích thước phù hợp hoặc đắt để tạo, có nguồn tái tạo rõ ràng và độ mới được chấp nhận**. Trong NoSQL, cache có thể giảm độ trễ, giảm read QPS, hấp thụ burst và tiết kiệm nguồn lực. Nhưng lợi ích không miễn phí: cache mang thêm state có thể stale, eviction, stampede, hot key, outage và rủi ro phân quyền.

Một trình tự lựa chọn:

~~~text
1. Đo read QPS, unique keys, reuse và source cost.
2. Đặt freshness, read-your-writes và business correctness.
3. Loại dữ liệu có rủi ro bảo mật/invariant không kiểm soát.
4. Chọn object, projection, aggregate hoặc query-result cache.
5. Chọn L1, L2, CDN hoặc materialized view phù hợp.
6. Thiết kế key với tenant, version, locale và variants cần thiết.
7. Chọn TTL/invalidation/negative cache có điều kiện.
8. Phòng stampede, hot cache key và stale refill races.
9. Giới hạn RAM/eviction, quota và fallback khi cache hỏng.
10. Benchmark warm, cold, expiry, outages và cập nhật nguồn.
11. Theo dõi p99, source load, stale-age, privacy và chi phí.
12. Điều chỉnh hoặc bỏ cache nếu lợi ích không tương xứng.
~~~

**Nguyên tắc quan trọng nhất:** *Cache dùng để tăng tốc việc đọc dữ liệu phù hợp; không sử dụng bản sao có thể cũ để thay thế quyết định nghiệp vụ tại nguồn có thẩm quyền.* Chọn đúng dữ liệu, đúng tầng và đúng freshness contract giúp hệ NoSQL phục vụ tải lớn mà vẫn giữ tính đúng đắn, bảo mật và khả năng phục hồi.








