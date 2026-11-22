# Hit ratio, độ trễ và nguy cơ chỉ tối ưu một chỉ số

Trong một hệ **Database No SQL**, bộ nhớ đệm (cache) giúp giảm số lượt đọc tới nguồn, giảm độ trễ phản hồi và hấp thụ những truy vấn lặp lại. Một dashboard thường hiển thị **cache hit ratio = 95%** và coi đó là dấu hiệu thành công. Tuy nhiên, tỷ lệ hit cao **không tự chứng minh** API nhanh, dữ liệu đủ mới, hệ chịu tải tốt hoặc chi phí giảm. Năm phần trăm request miss có thể tập trung đúng vào những truy vấn chậm nhất; một cache trả dữ liệu sai vẫn được đếm hit; tăng TTL để nâng tỷ lệ hit có thể làm sai tính đúng đắn nghiệp vụ.

Bài thuộc chương **Bộ nhớ đệm dữ liệu** của **Database No SQL**. Chúng ta sẽ đo hit ratio đúng mẫu số, nối kết tỷ lệ hit với **trung bình, p95/p99 và tốc độ request tới origin**, phân tích cache nhiều tầng, so sánh hiệu quả hit với chi phí miss, quản lý TTL/invalidation và những rủi ro khi tối ưu một con số mà bỏ qua SLO còn lại.

Một tình huống điển hình:

~~~text
Cache hit ratio:    97%
API p50 latency:     8 ms
API p99 latency:   800 ms
Origin NoSQL CPU:    95%
Support tickets: nhiều người nhìn thấy giá đã hết hiệu lực
~~~

Nếu chỉ nhìn hit ratio, nhóm có thể ăn mừng. Nếu nhìn trải nghiệm và tính đúng đắn, đây có thể là sự cố đáng xử lý.

**Thông điệp cốt lõi:** Đánh giá cache bằng **một tập chỉ số cân bằng**: hit/miss, độ trễ theo phân vị, độ tươi và nhất quán dữ liệu, tải nguồn, memory/eviction, error rate, chi phí và hành vi trong tình huống sự cố.

## 1. Cache nằm ở đâu trong hệ NoSQL?

Một luồng cache-aside quen thuộc:

~~~mermaid
flowchart LR
    Client["Client"] --> Java["Java API"]
    Java --> Cache["Redis / Caffeine Cache"]
    Cache -->|"Hit"| Java
    Java -->|"Miss"| Source["Authoritative NoSQL"]
    Source --> Java
    Java -->|"Populate"| Cache
~~~

Các lớp có thể gồm:

- **L1 local cache:** bộ nhớ trong JVM, ví dụ Caffeine.
- **L2 distributed cache:** Redis hoặc dịch vụ caching dùng chung nhiều API instances.
- **Database internal cache:** page cache, block cache, index cache hoặc query cache nếu engine có.
- **CDN/HTTP cache:** dành cho response hoặc nội dung ở gần người dùng.
- **Read model/materialized view:** dữ liệu được duy trì theo event và có thể không phải cache theo nghĩa TTL thuần.

Khi nói “cache hit”, trước tiên phải hỏi **hit ở tầng nào** và **loại request nào**. Một NoSQL DB có block-cache hit ratio riêng, không đồng nghĩa API Redis cache hit ratio.

## 2. Cache không thay nguồn dữ liệu có thẩm quyền

Một cache có thể được xóa và tái tạo từ nguồn, trừ khi kiến trúc cố tình dùng cache làm một thành phần ghi có thẩm quyền với hợp đồng riêng.

Phân biệt:

| Thành phần | Thường lưu gì? | Có tự là nguồn quyết định? |
|---|---|---|
| NoSQL source collection/table | Dữ liệu nghiệp vụ gốc | Có nếu được chỉ định owner |
| Redis cache | Bản sao giá trị gần đây | Thường không |
| Caffeine local cache | Bản sao trong process Java | Thường không |
| Search read model | Projection để truy vấn nhanh | Không tự là nguồn để xác nhận nghiệp vụ |
| Database page cache | Trang dữ liệu/index trong RAM | Không thay storage durability |
| Materialized aggregate | Dữ liệu tính lại | Theo hợp đồng projection và watermark |

Ví dụ `ProductCard.available=true` trong cache có thể phục vụ hiển thị. Nhưng khi khách đặt mua mặt hàng cuối cùng, API vẫn cần **atomic conditional update** trên Inventory source để không bán vượt tồn.

## 3. Cache hit là gì?

**Hit** là một lượt tra cứu trong cache đáp ứng tiêu chí tồn tại/giá trị hợp lệ mà tầng đo được định nghĩa, nên có thể dùng dữ liệu cache theo policy.

**Miss** là một lượt tra cứu cache không cung cấp được kết quả mong muốn, ví dụ key không tồn tại hoặc đã hết hạn.

Có những tình huống khó hơn:

- Value tồn tại nhưng bị đánh dấu stale.
- Value không tồn tại nhưng đã có **negative cache marker**.
- Cache timeout hoặc mạng lỗi.
- Lookup trả null vì domain thực sự không có entity.
- Có value nhưng version nhỏ hơn yêu cầu.
- Lookup cache được bypass có chủ đích.
- Một request cần nhiều keys; một số hit, một số miss.

Vì vậy cần công bố **cách đếm**. Không lấy một tỷ lệ từ thư viện cache rồi áp nó cho tất cả tầng hệ thống.

## 4. Công thức request hit ratio

Với những lượt lookup đủ điều kiện được ghi nhận:

\[
H=\frac{N_{\text{hit}}}{N_{\text{hit}}+N_{\text{miss}}}
\]

Và:

\[
M=\frac{N_{\text{miss}}}{N_{\text{hit}}+N_{\text{miss}}}=1-H
\]

Ví dụ trong năm phút:

~~~text
Cache lookups = 100,000
Hits           = 92,000
Misses         =  8,000

Hit ratio  = 92,000 / 100,000 = 92%
Miss ratio = 8,000 / 100,000  =  8%
~~~

Những công thức này đúng với **mẫu số đã định nghĩa**. Nếu hệ bỏ qua cache bypass, timeout, stale response hoặc batch requests khi tính, đó là một tỷ lệ với phạm vi khác, không được quảng bá thành tỷ lệ mọi HTTP requests đã được cache phục vụ.

## 5. Có nhiều mẫu số khác nhau

| Thước đo | Mẫu số | Đo điều gì? |
|---|---|---|
| Cache lookup hit ratio | Số lượt cache GET/lookup | Khả năng phục vụ của một tầng cache |
| HTTP request cache hit ratio | Số HTTP requests đủ điều kiện | Bao nhiêu request được phục vụ theo chính sách cache |
| Object/key hit ratio | Số lượt truy cập object | Độ phổ biến key đã được cache |
| Byte hit ratio | Tổng bytes được yêu cầu | Tỷ lệ băng thông được phục vụ từ cache |
| Origin offload ratio | Lượt đọc origin tránh được / lượt cần origin nếu không cache | Mức giảm tải nguồn |
| Fresh/valid hit ratio | Số hit đáp ứng freshness / số lượt lookup đủ điều kiện | Chất lượng nội dung cache |
| Transactional correctness rate | Số operation giữ invariant / số operation | Khía cạnh đúng đắn, không suy ra từ hit ratio |

Một cache nhiều tầng có thể đếm một HTTP request thành **một miss L1 và một hit L2**. Nếu cộng hits và misses của cả hai tầng mà không định nghĩa lại mẫu số, kết luận có thể sai.

## 6. Key hit ratio khác byte hit ratio

Giả sử có 100 requests:

- 90 requests đọc object 1 KiB, đều cache hit.
- 10 requests đọc object 10 MiB, đều cache miss.

**Request hit ratio:**

\[
H_{\text{request}}=90/100=90\%
\]

**Byte hit ratio theo bytes yêu cầu:**

\[
H_{\text{byte}}=\frac{90\cdot 1\text{ KiB}}
{90\cdot 1\text{ KiB}+10\cdot 10\text{ MiB}}
\]

Kết quả byte hit rất thấp vì hầu hết bytes nằm trong miss. Nếu mục tiêu giảm network egress hoặc băng thông nguồn, 90% hit theo số request có thể gây hiểu nhầm nghiêm trọng.

Ngược lại, cache vài object lớn có thể đạt byte hit cao nhưng số request phổ biến vẫn miss.

## 7. Tỷ lệ có trọng số theo chi phí origin

Không phải mọi miss có chi phí tương đương:

~~~text
Lookup Product title miss -> MongoDB point lookup 4 ms
Lookup Recommendation miss -> 5 collections / 300 ms
Lookup Report miss -> aggregate 2 seconds
~~~

Một hệ có thể quan tâm:

\[
\text{Estimated origin work avoided}
=\sum_i N_{\text{hit},i}C_{\text{origin},i}
\]

trong đó \(C_{\text{origin},i}\) là chi phí ước lượng nếu nhóm request i không được cache phục vụ.

Tỷ lệ này phải được **đo/ước lượng bằng benchmark hoặc tracing**; không nên gán một giá trị cố định cho mọi key. Một cache có hit ratio 80% vẫn có thể có tác động tốt hơn cache 95% nếu nó giữ đúng các truy vấn origin đắt đỏ.

## 8. Hit không đồng nghĩa dữ liệu đúng

Một giá sản phẩm đã hết hiệu lực vẫn có thể được trả từ cache:

~~~text
Source: current price = 120,000
Cache:  old price     = 100,000
Lookup: cache HIT
```

Cache metric thường đếm hit vì key có giá trị. Business lại phải xem đó là **stale hit** hoặc **invalid hit**.

Tách:

- **Physical hit:** cache có value.
- **Contract-valid hit:** value đáp ứng TTL, version, quyền và freshness policy.
- **Business-correct response:** dữ liệu dùng trong hành động quan trọng đáp ứng invariant tại thời điểm cần thiết.

Không nâng hit ratio bằng cách bỏ kiểm tra version/tenant/TTL rồi gọi đó là tối ưu.

## 9. Định nghĩa tỷ lệ valid-hit

Một thước đo bổ sung:

\[
H_{\text{valid}}=
\frac{N_{\text{hit đáp ứng freshness/authorization contract}}}
{N_{\text{eligible lookup}}}
\]

Nếu không thể biết một hit có stale hay không cho mọi request, có thể đo qua:

- Sampling đối chiếu với source.
- Source version/ETag.
- Event-to-cache propagation lag.
- Last update watermark.
- Audit các API có yêu cầu mạnh.

Không dùng `cacheHit=true` làm bằng chứng `isFresh=true` nếu hệ không có cơ chế kiểm chứng.

## 10. Hit ratio được ghi ở đâu?

Những nguồn metric:

- Cache library (ví dụ Caffeine) tính lookup hits/misses.
- Redis server stats cho keyspace hits/misses toàn instance.
- Application metrics tính request cacheable và response path.
- Proxy/CDN response headers và telemetry.
- NoSQL engine cache stats.
- Distributed traces cho một request qua nhiều tầng.

Mỗi nguồn có **phạm vi, quy tắc và độ trễ thu thập khác nhau**. Redis `keyspace_hits` không tự là hit ratio cho endpoint `/orders/{id}`, vì một instance có thể phục vụ nhiều ứng dụng/loại key và những lệnh không phải GET đơn giản.

## 11. Cache hit ratio theo khoảng thời gian

Cache counters thường là số tích lũy. Dashboard cần lấy **delta/rate theo cửa sổ**:

~~~text
At 10:00: hits=1,000,000; misses=100,000
At 10:05: hits=1,050,000; misses=110,000

Hits during 5 min   = 50,000
Misses during 5 min = 10,000
Window hit ratio    = 50,000 / 60,000 = 83.33%
~~~

Không lấy \(1{,}050{,}000/(1{,}050{,}000+110{,}000)\) rồi gọi đó là hit ratio của năm phút vừa qua.

Server restart/counter reset, scrape gaps và low sample counts phải được xử lý trong metric query.

## 12. Hit ratio ít traffic có thể gây nhiễu

Nếu một instance có:

~~~text
Hits=9
Misses=1
Hit ratio=90%
~~~

chỉ một miss mới đưa tỷ lệ xuống 81,8%. Khi dashboard alert mỗi phút, hệ ít traffic có thể báo động giả.

Nên theo dõi:

- Tổng số lookups.
- Ratio với minimum traffic threshold.
- Window đủ dài cho kết luận.
- Số liệu theo service/operation.
- Error count và latency song song.

Một mẫu nhỏ không có cùng ý nghĩa thống kê với hàng triệu lookups.

## 13. Latency của hit và miss

Một cách phân tích trung bình lý tưởng:

\[
E[L]\approx H\cdot E[L_{\text{hit}}]
+(1-H)\cdot E[L_{\text{miss}}]
\]

Trong đó `L_hit` và `L_miss` phải cùng là **end-to-end latency của những request cùng loại**, phân nhóm theo outcome hit/miss. Nếu `L_hit` chỉ là Redis RTT còn `L_miss` là HTTP end-to-end, phép cộng có thể không có ý nghĩa.

Ví dụ:

~~~text
Hit ratio = 95%
Average hit-path latency = 2 ms
Average miss-path latency = 200 ms
```

Khi các nhóm được định nghĩa đúng:

\[
E[L]\approx 0.95\cdot2+0.05\cdot200=11.9\text{ ms}
\]

Dù 95% requests hit, 5% misses chi phối phần lớn tổng thời gian xử lý.

## 14. Cần tính đủ đường đi miss

Một cache-aside miss path có thể gồm:

~~~text
Parse/auth/routing
    ↓
Cache GET / timeout
    ↓
Database connection selection
    ↓
NoSQL query + index/IO
    ↓
Deserialize/transform
    ↓
Cache SET/serialization
    ↓
HTTP response
```

Vì vậy:

\[
L_{\text{miss path}}
=L_{\text{common}}
+L_{\text{cache lookup}}
+L_{\text{origin}}
+L_{\text{populate}}
+L_{\text{other}}
\]

Đây là **phân rã logic**, không mặc định các bước hoàn toàn tuần tự hay độc lập (async write-back có thể không nằm trên critical path).

Nếu cache GET timeout 100 ms trước khi fallback origin, cache có thể **tăng** latency của miss so với gọi origin trực tiếp.

## 15. Tăng hit ratio không đảm bảo giảm latency

Giả sử hai phương án:

| | Phương án A | Phương án B |
|---|---:|---:|
| Hit ratio | 90% | 96% |
| Average hit latency | 1 ms | 12 ms |
| Average miss latency | 80 ms | 80 ms |
| Estimated avg latency | 8.9 ms | 14.72 ms |

Tính:

\[
E[L_A]=0.90\cdot1+0.10\cdot80=8.9
\]

\[
E[L_B]=0.96\cdot12+0.04\cdot80=14.72
\]

**B có hit ratio cao hơn nhưng trung bình chậm hơn**, ví dụ vì remote cache quá xa, serialization nặng hoặc thêm network hop.

Tối ưu cache phải xét **chi phí của hit**, không chỉ tỷ lệ hit.

## 16. p50, p95 và p99 là gì?

Một phân vị như p99 là ngưỡng mà **khoảng 99% quan sát** không vượt qua, theo cách histogram/quantile được tính từ tập dữ liệu. Nó không phải phép trung bình của 99% requests.

Ví dụ 100 requests được sắp theo latency:

~~~text
90 requests:  5 ms
9 requests:  40 ms
1 request:   900 ms
```

p50 có thể ở gần 5 ms, trong khi giá trị ở đuôi bị ảnh hưởng bởi request 900 ms. Cách xác định p99 chính xác phụ thuộc định nghĩa estimator và cách nội suy/cấu hình histogram.

Khi người dùng nhạy với độ trễ cao, chỉ báo average hoặc p50 là chưa đủ.

## 17. Vì sao miss dễ chi phối p99?

Nếu 95% requests hit và 5% miss, trong một mô hình tách biệt đơn giản nơi mọi miss đều chậm hơn mọi hit, **phần 5% chậm nhất** nằm trong miss group.

Do đó:

- p50 thường thuộc hit.
- p95 có thể gần ranh giới hit/miss.
- p99 nhiều khả năng nằm sâu trong miss distribution.

Không được tính:

~~~text
p99(total) = 0.95 * p99(hit) + 0.05 * p99(miss)
```

**Quantiles không tuyến tính như kỳ vọng**. Phải gộp các quan sát/histogram đúng cách. Phần trăm hit có thể rất tốt nhưng p99 của API vẫn vượt SLO.

## 18. Quantile của mixture không đơn giản

Hãy xét:

~~~text
Cache hit path: gần 3 ms
Cache miss path: gần 400 ms
Hit fraction: 99.5%
```

Nếu distribution của hit và miss gần như tách rời, p99 tổng có thể còn nằm trong nhóm hit, dù 0,5% request phải đợi 400 ms. Điều đó không làm 0,5% bị chậm biến mất; cần quan sát **p99.9 hoặc tỷ lệ vượt latency threshold** nếu độ rủi ro nghiệp vụ đòi.

Ngược lại khi miss fraction lên 2%, p99 có thể nhảy rất mạnh, dù hit ratio chỉ giảm từ 99,5% xuống 98%. Đó là hiện tượng **tail latency cliff**.

## 19. Một SLO nên đặt theo trải nghiệm thật

Ví dụ định nghĩa SLO cho một endpoint:

~~~text
99% GET /catalog/product requests
complete within 150 ms
over a rolling 28-day window
```

Không nên thay SLO này bằng:

~~~text
Redis hit ratio >= 98%
```

Hit ratio là **chỉ số cơ chế**, còn SLO latency là **kết quả mà người dùng nhận**. Một cache 98% hit vẫn có thể vượt ngưỡng nếu hit path chậm hoặc missed requests quá đắt.

Có thể dùng hit ratio như điều kiện cảnh báo sớm, nhưng không thay thế latency/error/freshness SLO.

## 20. Hit ratio và origin offload

Một mục đích lớn của cache là giảm tải nguồn NoSQL.

Nếu:

~~~text
Request rate = 20,000 per second
Cache hit ratio = 95%
```

Trong mô hình một eligible request dẫn tới tối đa một origin read khi miss:

\[
R_{\text{origin}}\approx 20{,}000\cdot(1-0.95)=1{,}000/s
\]

Nếu hit ratio giảm còn 90%:

\[
R_{\text{origin}}\approx20{,}000\cdot0.10=2{,}000/s
\]

**Hit ratio chỉ giảm 5 điểm phần trăm, origin read rate tăng gấp đôi.**

Tuy nhiên công thức chỉ đúng cho workload và cache logic đã giả định. Miss có thể tạo nhiều truy vấn origin, được coalesced, cần refresh, hoặc đi qua nhiều cache layers.

## 21. Miss amplification

Một miss không nhất thiết chỉ gọi một query:

~~~text
Miss ProductCard:
  1 query Catalog
  1 query Pricing
  1 query Inventory
  1 query Review aggregate
  1 query Seller
```

Nếu 2.000 miss/s và mỗi miss tạo năm origin queries:

\[
R_{\text{queries}}\approx 10{,}000/s
\]

thay vì 2.000/s.

Nên đo:

- Origin queries per cache miss.
- Total source read QPS.
- Read capacity/IO consumed.
- Query latency theo operation.
- Duplicate concurrent loads trên cùng key.
- Retry count khi origin chậm.

Hit ratio tốt không đảm bảo origin tải thấp nếu miss amplification lớn.

## 22. L1 và L2: hit ratio có điều kiện

Một Java service có:

~~~text
L1: Caffeine local memory
L2: Redis shared cache
Source: MongoDB
```

Giả sử:

- 60% requests hit L1.
- Trong **40% requests miss L1**, 80% hit L2.

Tỷ lệ được cache phục vụ:

\[
H_{\text{total}}=H_{L1}+(1-H_{L1})H_{L2\mid missL1}
\]

\[
=0.60+0.40\cdot0.80=0.92=92\%
\]

Tỷ lệ đi tới origin:

\[
P(\text{origin})=(1-H_{L1})(1-H_{L2\mid missL1})
=0.40\cdot0.20=8\%
\]

**80% hit của L2 ở đây là conditional rate**, không phải 80% trên toàn bộ HTTP requests. Không cộng 60% + 80% = 140%.

## 23. L1 cache tạo vấn đề theo process

Mỗi API instance có cache riêng:

~~~text
API Pod A -> L1 Caffeine A
API Pod B -> L1 Caffeine B
API Pod C -> L1 Caffeine C
All -> Redis L2 -> NoSQL source
```

Ưu điểm:

- L1 hit rất nhanh, không cần network.
- Giảm tải L2.
- Phù hợp hot keys nhỏ, đọc nhiều.

Rủi ro:

- Ba pods có thể giữ ba versions khác nhau.
- Rolling deploy làm cache warm-up không đồng đều.
- Scale out tạo cache lạnh ở pods mới.
- Invalidation phải tới mọi pods nếu freshness cần.
- Đo hit rate theo pod có thể khác nhau lớn.
- Memory tổng bằng số pods nhân với local cache budget.

Không suy từ một pod 99% hit thành toàn service 99% hit.

## 24. Memory hit và disk hit cũng khác

Một database hoặc cache engine có thể có:

- RAM access.
- SSD tier/cache.
- Object storage/read-through.
- Backend NoSQL source.

Nếu disk-tier cache được tính hit, latency có thể khác RAM hàng bậc độ lớn. Khi đánh giá, nên phân loại **hit path** theo storage tier hoặc ít nhất đo latency riêng, không coi mọi hit có chi phí 1 ms.

## 25. Workload shape ảnh hưởng hit ratio

Một mô hình cache thường dựa trên **temporal locality** và **key popularity**.

Ví dụ:

- 1% key phổ biến nhận 90% lượt đọc.
- 99% key còn lại chỉ nhận 10% lượt đọc.

Một cache nhỏ giữ hot keys có thể tạo hit ratio rất cao, mặc dù hầu hết **unique keys** không được cache. Điều đó không sai; nó có nghĩa hit ratio đang đo **lượt truy cập**, không đo tỷ lệ dữ liệu được lưu.

Nếu workload đổi từ đọc hot keys sang quét tuần tự hàng triệu keys, tỷ lệ hit có thể giảm đột ngột dù cache size không đổi.

## 26. Scan pollution

Một job báo cáo đọc lần lượt hàng triệu key ít dùng có thể nạp các entries lạnh và đẩy hot entries khỏi cache.

~~~text
Before report:
  cache holds hot Product keys
  hit ratio high

Report scans 5 million rare keys:
  many misses, many inserts
  hot Product keys evicted

After report:
  user traffic begins to miss
```

Cách xử lý có thể:

- Bypass cache cho scan.
- Cache admission policy thông minh.
- Caching riêng cho analytics.
- TTL/size policy khác theo operation.
- Chỉ cache objects có tái sử dụng đủ cao.
- Đo hit ratio theo workload class.

Một cache không nhất thiết nên giữ **mọi dữ liệu vừa đọc**.

## 27. LRU và LFU tối ưu những thứ khác nhau

**LRU** ưu tiên những entry được dùng gần đây. **LFU** ưu tiên các entry được dùng thường xuyên; các biến thể hiện đại kết hợp frequency estimation, admission và recency.

Đánh đổi:

- LRU có thể bị scan pollution.
- LFU có thể giữ một key từng hot nhưng không còn phổ biến.
- Windowed policies có thể thích nghi theo workload.
- TTL và memory limits vẫn cần.
- Key size/weight làm thay đổi capacity thực.

Không tuyên bố LFU luôn tốt hơn LRU hoặc ngược lại. Hãy thử bằng workload thật và xét p99, eviction, freshness, origin load chứ không chỉ hit rate.

## 28. Cache admission quan trọng ngang eviction

**Eviction** quyết định loại bỏ entry nào khi cần chỗ. **Admission** quyết định một miss mới có đáng đưa vào cache không.

Một object 20 MiB chỉ được đọc một lần có thể không đáng thay thế hàng nghìn hot objects nhỏ. Nếu mọi miss đều được populate, cache sẽ lãng phí RAM/băng thông.

Tối ưu admission dựa trên frequency/size/cost có thể giảm hit count một chút nhưng **giảm đáng kể origin cost và tail latency**.

## 29. Object size và hiệu quả bộ nhớ

Một cache memory budget 2 GiB không chứa được đúng 2 GiB payload thuần:

- Key overhead.
- Entry metadata.
- JVM object headers hoặc Redis allocator overhead.
- Serialization structures.
- Fragmentation.
- TTL/index bookkeeping.
- Replication buffer, client buffers, operational headroom.

Cần đo **resident memory, allocator fragmentation, key count, eviction rate** và payload distribution. Tăng cache max size đến mức sát RAM giới hạn có thể gây OOM hoặc eviction storm.

## 30. TTL tác động lên hit ratio và freshness

TTL (time-to-live) giới hạn một entry được sử dụng bao lâu theo policy.

~~~text
TTL ngắn:
  + fresh hơn theo expiration
  - nhiều misses/refreshes

TTL dài:
  + tăng cơ hội hit
  - stale window lớn hơn nếu invalidation thiếu
  + có thể giữ object ít dùng quá lâu
```

Tăng TTL từ 5 phút lên 24 giờ để đạt 99% hit có thể sai nếu giá, quyền truy cập hoặc stock thay đổi trong ngày.

Chọn TTL theo **tốc độ thay đổi, hậu quả stale và khả năng invalidation**, không theo một tỷ lệ hit mục tiêu duy nhất.

## 31. Expire-after-write và expire-after-access

Hai kiểu expiration phổ biến:

- **Expire after write:** entry hết hạn một khoảng sau khi tạo/cập nhật.
- **Expire after access:** entry được giữ thêm khi còn truy cập.

Expire-after-access có thể giữ một hot key rất lâu nếu liên tục đọc, dù **nguồn đã thay đổi**. Vì vậy đây không phải cơ chế đảm bảo freshness chặt cho dữ liệu mutable nếu không có invalidation hoặc refresh policy.

Một cache Caffeine có thể dùng policy hỗn hợp phù hợp; không coi mỗi TTL option có cùng semantics.

## 32. Stale-while-revalidate

Một kỹ thuật:

~~~text
Request arrives
  cache value within fresh window -> return
  stale but within allowed stale window -> optionally return stale
                                       -> schedule refresh
  too old -> synchronous reload / fail per contract
```

Ưu điểm:

- Hạn chế latency spike khi nhiều entry hết hạn.
- Hấp thụ origin chậm/ngừng tạm thời.
- Người dùng có thể tiếp tục đọc một số nội dung không quan trọng.

Nhược điểm:

- Response **cố ý stale** trong một khoảng.
- Cần chỉ rõ endpoint/field nào được phép.
- Refresh worker có thể bị lỗi.
- Không dùng stale authorization hoặc thanh toán khi nghiệp vụ cấm.

Hit ratio cần tách **fresh hit** với **stale-served**; nếu gộp, việc tăng stale window sẽ làm dashboard đẹp lên mà freshness xấu đi.

## 33. Stale-if-error

Khi nguồn NoSQL lỗi, một hệ có thể dùng bản cache cũ cho nội dung như mô tả sản phẩm. Đây là lựa chọn **availability vs freshness** có điều kiện.

Một bảng:

| Loại dữ liệu | Có thể stale-if-error? |
|---|---|
| Bài viết công khai | Thường có thể theo policy |
| Gợi ý sản phẩm | Có thể, nếu UI ghi nhận độ trễ |
| Giá tham khảo trên catalog | Tùy hợp đồng; checkout phải xác minh |
| Tồn kho dùng để xác nhận order | Không nếu gây overselling |
| Trạng thái quyền truy cập | Không nếu cần revoke tức thời |
| Số dư ví dùng để chi tiêu | Không dùng cache cũ làm authority |

Đo riêng `stale_served_total` và `origin_errors_total`. Không ghi nhận stale response như thành công vô điều kiện cho mọi business SLO.

## 34. Cache invalidation phức tạp hơn TTL

Một cập nhật source:

~~~text
t0 Catalog updates Product v42 -> v43
t1 Outbox/CDC emits ProductChanged(v43)
t2 Consumer invalidates/refreshes Redis
t3 Each Java L1 instance evicts v42
```

Lỗi có thể ở bất kỳ điểm nào:

- Event mất hoặc gửi lại.
- L1 instance không nhận invalidation.
- Consumer ghi version cũ sau version mới.
- Redis timeout khi delete.
- Cache warm-up load từ follower stale.
- ID/generation hoặc tenant key sai.
- Pipeline backlog.

**Tối ưu hit ratio bằng cách ngừng invalidation** là phản tác dụng nếu cache phục vụ dữ liệu không còn đúng.

## 35. Update cache trước hay sau database commit?

Một write path sai:

~~~text
Update Redis cache to new value
Attempt database commit
Database transaction aborts
```

Khi đó cache chứa giá trị **chưa bao giờ commit ở source**.

Một thiết kế thường dùng:

~~~text
Commit authoritative source first
Record outbox event atomically if needed
After commit: invalidate or rebuild cache
```

Tuy nhiên còn race khi cache-aside reader đang load dữ liệu cũ. Vì vậy cần TTL, version guard, sequence/generation hoặc protocol phù hợp; không đơn giản cho rằng “DB trước, cache sau” xóa mọi race.

## 36. Cache-aside race sau miss

Timeline:

~~~text
t0 Reader A cache miss
t1 A reads Source v10, pauses
t2 Writer updates Source v11
t3 Writer invalidates Cache
t4 A resumes and SET Cache v10
```

Cache đã chứa bản cũ **sau khi invalidation**. Nếu chỉ dùng delete-on-write và TTL dài, stale có thể tồn tại lâu.

Các lựa chọn:

- Mang sourceVersion vào cache và write với version guard.
- Đọc source với consistency phù hợp và revalidate.
- Single-flight/coordinated loader.
- TTL giới hạn stale exposure.
- Event-driven repair và periodic reconciliation.
- Change-log offsets hoặc generation token.

Không có một giải pháp chung không đánh đổi; lựa chọn theo business consistency.

## 37. Version guard để chặn cache downgrade

Một luật:

~~~text
Incoming (generation=1, version=11)
Current  (generation=1, version=12)
-> reject incoming, do not overwrite current

Incoming (generation=1, version=13)
Current  (generation=1, version=12)
-> accept if authorization and schema valid
```

Version phải tăng theo nguồn có thẩm quyền, không tự tạo từ local JVM timestamp. Redis script/CAS hoặc một single-writer component có thể thực hiện guard; `GET` rồi `SET` ở hai lệnh riêng vẫn có race.

Nếu ID được tái sử dụng, cần **generation/epoch** để tránh event v12 từ entity đã xóa ghi lên entity mới v1.

## 38. Negative caching

Một lookup không tìm thấy entity cũng có thể được cache:

~~~text
GET Product nonexistent
Source returns NOT_FOUND
Cache stores sentinel NOT_FOUND for 30 seconds
```

Lợi ích:

- Giảm repeated misses cho key không tồn tại.
- Hạn chế database bị đánh bởi các request dò ID.
- Bảo vệ nguồn khỏi truy vấn lặp tới khóa thường xuyên absent.

Rủi ro:

- Entity vừa được tạo nhưng sentinel cũ còn tồn tại.
- Không phân biệt `NOT_FOUND` với timeout/permission denied.
- Negative cache miss/hit semantics làm dashboard dễ nhầm.
- Key-space attack tạo rất nhiều negative entries.

Negative cache nên có TTL và key/admission limits phù hợp. **Không cache lỗi 500/timeout như NOT_FOUND**.

## 39. Đếm negative hit thế nào?

Một negative cache marker có thể **ngăn truy vấn source** và vì vậy được tính là hit về offload, nhưng API vẫn trả 404.

Do đó:

- `cacheLookupHit`: có sentinel/value.
- `originAvoided`: đã tránh source read.
- `businessFound`: entity có tồn tại không.
- `httpStatus`: 200, 404, 5xx.

Nếu chỉ dùng HTTP 200 làm hit, negative caching trông vô ích dù nó giảm tải. Nếu tính negative hit thành “sản phẩm có sẵn”, dashboard cũng sai.

## 40. Cache penetration, breakdown và avalanche

Ba tình huống cần phân biệt:

- **Cache penetration:** request nhiều tới keys không tồn tại, gây miss liên tục; negative caching và validation có thể giúp.
- **Cache breakdown/hot-key expiration:** một key rất hot hết hạn, nhiều request cùng load origin.
- **Cache avalanche:** nhiều keys hết hạn cùng lúc hoặc một tầng cache lỗi, tạo lượng miss lớn đột ngột.

Đây là những vấn đề không thể mô tả chỉ bằng tỷ lệ hit trung bình trong một giờ.

## 41. Cache stampede

Giả sử key Product hot nhận 4.000 requests/s. TTL hết hạn vào cùng một thời điểm. Nếu mọi request miss đều gọi MongoDB:

~~~text
Thousands of callers -> one missing key
                       -> thousands of source reads
```

Điều này có thể gây:

- Origin connection pool saturation.
- CPU/IO spike.
- p99 tăng.
- Retry amplification.
- Cache population race.
- Sự cố lan từ cache sang DB.

Hit ratio có thể vẫn là 99% trên cả ngày dù một đợt stampede vài giây làm nguồn sập.

## 42. Single-flight/request coalescing

Một biện pháp: chỉ một request của mỗi key thực hiện origin load, các request còn lại đợi kết quả đó.

~~~mermaid
flowchart LR
    R1["Request A"] --> Gate["Load coordinator for key K"]
    R2["Request B"] --> Gate
    R3["Request C"] --> Gate
    Gate -->|"One source read"| DB["NoSQL source"]
    DB --> Gate
    Gate --> R1
    Gate --> R2
    Gate --> R3
~~~

Trong một JVM, thư viện cache loading có thể phối hợp concurrent loads cho cùng key theo contract. Trong nhiều API instances, local single-flight chỉ gộp trong từng process; có thể cần distributed coordination hoặc L2 cache.

Cần giới hạn thời gian chờ và xử lý loader error, không giữ một “loading lock” vĩnh viễn.

## 43. Jitter TTL để tránh đồng loạt hết hạn

Nếu một batch import nạp 1 triệu keys với TTL đúng 600 giây, các keys có thể hết hạn đồng thời.

Có thể thêm random jitter:

~~~text
base TTL = 600 seconds
actual TTL = 600 + random(0..120) seconds
```

Hoặc một phân bố được thiết kế theo policy. Điều này phân tán thời điểm miss/refresh.

Không thêm jitter vượt giới hạn freshness bắt buộc. Nếu chính sách yêu cầu stale tối đa 10 phút, TTL tối đa phải nằm trong hợp đồng ấy; không tự cộng 2 phút chỉ vì giảm avalanche.

## 44. Refresh-ahead

Với hot keys có update predictably, worker có thể refresh trước khi TTL hết hạn:

~~~text
Entry loaded t0
TTL expires t0+10min
Refresh starts t0+8min
```

Lợi ích:

- Giảm synchronous misses.
- Giảm p99 từ đợt hết hạn.
- Giữ origin load có thể dự đoán.

Nhược điểm:

- Đọc nguồn cho cả keys không còn được dùng.
- Tăng background work.
- Refresh có thể cache dữ liệu stale nếu đọc replica trễ.
- Có thể tăng load đúng lúc DB đang chậm.

Nên đo **refresh efficiency**: bao nhiêu refresh giúp phục vụ hit sau đó, chi phí thực và data freshness.

## 45. Circuit breaker và cache outage

Một cache remote có thể trở thành điểm nghẽn:

~~~text
Redis latency spikes to 150 ms
Java waits for Redis GET
Then falls back to NoSQL anyway
```

Nếu mọi request chờ timeout dài, cache làm chậm cả hệ.

Một policy có thể:

- Dùng cache timeout ngắn, tách origin deadline.
- Bypass cache tạm thời khi circuit breaker mở.
- Dùng L1 cho data ít rủi ro.
- Giới hạn concurrent origin fallbacks.
- Dùng stale-if-error với nội dung được phép.
- Backpressure khi origin không chịu được toàn bộ miss traffic.
- Thoát nhanh với lỗi phù hợp thay vì gây cascading failure.

Trong outage, hit ratio có thể **không tính các bypass requests**; dashboard chỉ có Redis hits/misses sẽ che đi sự cố.

## 46. Cache bypass cần được đo

Một số requests cố ý đi thẳng origin:

- Admin read yêu cầu dữ liệu hiện hành.
- Payment/authorization check.
- `Cache-Control: no-cache` theo contract.
- API có consistency token.
- Bulk export/scan không muốn pollute cache.
- Debug/incident tool có quyền.

Nên có metric:

~~~text
eligible_requests
cache_lookups
cache_hits
cache_misses
cache_bypasses
cache_errors
origin_queries
```

Nếu tăng bypass từ 1% lên 40% nhưng cache hit ratio trên phần còn lại giữ 99%, tổng tải origin vẫn có thể tăng mạnh.

## 47. Hot key skew và công bằng giữa tenants

Giả sử hai tenants:

~~~text
Tenant A: 1 million requests, 99% hit
Tenant B: 1 thousand requests, 40% hit
```

Hit ratio tổng gần 99%, nhưng tenant B có trải nghiệm kém. Nếu B là tenant đang thanh toán hoặc có workload nhạy latency, average service metric không đủ.

Phân tích theo:

- Operation type.
- Tenant tier/class.
- Region/availability zone.
- Data size bucket.
- Client platform.
- Hot vs cold key class.
- New vs returning users.

Cẩn thận **metrics cardinality**: không gắn hàng triệu raw tenant IDs/key IDs vào Prometheus labels. Dùng cohort/trace/log và sampling phù hợp.

## 48. Simpson's paradox trong hit ratio

Một thay đổi workload mix có thể khiến hit ratio tổng tăng dù tỷ lệ hit của mỗi nhóm giảm.

Ví dụ:

| | Giai đoạn A requests | Hit A | Giai đoạn B requests | Hit B |
|---|---:|---:|---:|---:|
| Hot catalog | 100 | 99% | 900 | 98% |
| Rare reports | 900 | 50% | 100 | 40% |

Giai đoạn A:

\[
H_A=(100\cdot0.99+900\cdot0.50)/1000=54.9\%
\]

Giai đoạn B:

\[
H_B=(900\cdot0.98+100\cdot0.40)/1000=92.2\%
\]

Tổng tăng rất mạnh dù **hot catalog giảm từ 99% xuống 98% và reports giảm từ 50% xuống 40%**. Nguyên nhân là tỉ trọng traffic chuyển sang nhóm dễ hit hơn.

Phải so cùng cohort và kiểm soát workload mix trước khi kết luận tối ưu hiệu quả.

## 49. Hit ratio cao có thể là hệ quả traffic bất thường

Một bot lặp lại GET cùng key có thể đẩy hit ratio lên gần 100%, trong khi:

- Người dùng thật truy cập key mới liên tục miss.
- Origin load của các truy vấn quan trọng tăng.
- Business conversion giảm.
- Rate limit/abuse detection không phát hiện.
- P99 của nhóm người dùng thật xấu đi.

Nên phân tích hit ratio cho **eligible, authenticated, representative traffic**, không chỉ mọi GET không phân loại.

## 50. Warm-up và cold-start

Khi deploy hoặc scale out:

~~~text
New Java pod starts
L1 cache empty
Requests arrive
L1 miss ratio spikes
L2/origin load increases
```

Một service trước deploy có 95% L1 hit nhưng sau scale-out nhiều pods mới có thể có tỷ lệ thấp tạm thời. Nên xét:

- Warm-up/steady-state riêng.
- Pod age.
- Preload hot keys có giới hạn.
- L2 Redis để giảm origin misses.
- Rollout strategy.
- Cold-start budget.
- Cache admission và size.

Đừng loại hoàn toàn cold-start khỏi SLO nếu người dùng vẫn chịu ảnh hưởng; có thể đo riêng để chẩn đoán.

## 51. Cache sizing và working set

**Working set** là tập dữ liệu được truy cập trong một khoảng đáng quan tâm.

Nếu working set hot 5 GiB nhưng cache dành 500 MiB, eviction churn có thể cao. Tuy nhiên giữ toàn bộ working set có thể không tối ưu khi phần lớn keys chỉ đọc một lần.

Các câu hỏi:

- Top-N keys chiếm bao nhiêu lượt đọc?
- Distribution key sizes?
- Reuse distance/time?
- TTL trước khi key được đọc lại?
- Chi phí origin của từng loại key?
- Memory overhead và fragmentation?
- Data freshness upper bound?

Tăng cache size có **diminishing returns**. Sau một ngưỡng, thêm RAM ít tăng origin offload nhưng tăng chi phí.

## 52. Đường cong hit ratio theo capacity

Một cách thử nghiệm:

~~~text
Cache 0.5 GiB -> 80% hits
Cache 1.0 GiB -> 90% hits
Cache 2.0 GiB -> 94% hits
Cache 4.0 GiB -> 95% hits
```

Nếu mục tiêu là giảm p99 hoặc DB reads, phần tăng từ 2 lên 4 GiB có thể không xứng chi phí. Nhưng nếu 1% misses cuối cực đắt, nó vẫn có thể đáng đầu tư.

Không chọn capacity chỉ theo hit ratio: hãy vẽ đồng thời:

- Cache cost.
- Origin read QPS/cost.
- End-to-end p95/p99.
- Freshness/error rate.
- Evictions và GC pressure.
- Capacity headroom.

## 53. Memory pressure ảnh hưởng Java

Một L1 cache Caffeine quá lớn có thể tăng:

- JVM heap occupancy.
- GC pause và tail latency.
- Allocation/serialization overhead.
- OOM risk.
- Container memory pressure.
- Restart/cold-start frequency.

Một cache “hit nhiều hơn” nhưng làm JVM pause 500 ms có thể khiến API p99 tệ hơn.

Nên đo heap live set, allocation rate, GC pause, evictions, load penalty và request latency; đặt upper bound cho size/weight.

## 54. Caffeine trong Java: ví dụ cache-aside

Với thư viện Caffeine, một cache local đơn giản:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.stats.CacheStats;

import java.time.Duration;

public final class ProductReadCache {
    private final Cache<String, ProductCard> cache;
    private final ProductRepository source;

    public ProductReadCache(ProductRepository source) {
        this.source = source;
        this.cache = Caffeine.newBuilder()
            .maximumSize(50_000)
            .expireAfterWrite(Duration.ofMinutes(5))
            .recordStats()
            .build();
    }

    public ProductCard get(String tenantId, String productId) {
        String key = tenantId + "#" + productId;
        return cache.get(key, k ->
            source.loadAuthoritative(tenantId, productId)
        );
    }

    public void invalidate(String tenantId, String productId) {
        cache.invalidate(tenantId + "#" + productId);
    }

    public CacheStats stats() {
        return cache.stats();
    }
}
~~~

`ProductCard` và `ProductRepository` là domain types giả định; ví dụ cho thấy cách tạo cache, loader và instrumentation, **không phải một ứng dụng có thể biên dịch ngay nếu thiếu các kiểu đó và dependency**.

Cần lưu ý:

- `cache.get(key, mappingFunction)` có cơ chế phối hợp load cho cùng key trong phạm vi cache instance theo contract.
- `null` từ loader không được cache thành positive value theo semantics phù hợp.
- Đây chỉ là L1 trong một JVM, không chia sẻ giữa pods.
- TTL không thay invalidation khi source thay đổi.
- Không dùng cache value làm authority cho invariant quan trọng.
- `recordStats()` có overhead, nên quan sát trong workload thật.

## 55. Caffeine stats: đọc đúng các trường

Ví dụ:

~~~java
CacheStats stats = productCache.stats();

double hitRate = stats.hitRate();
double missRate = stats.missRate();

long requestCount = stats.requestCount();
long hitCount = stats.hitCount();
long missCount = stats.missCount();
long loadSuccesses = stats.loadSuccessCount();
long loadFailures = stats.loadFailureCount();
long evictions = stats.evictionCount();

double avgLoadPenaltyNanos = stats.averageLoadPenalty();
~~~

**`averageLoadPenalty` là thống kê thời gian load trong Caffeine theo API**, không tự là HTTP p99. `hitRate()` là cumulative stats của đối tượng cache đó; muốn thấy rolling window có thể export counter và tính rate/delta trong hệ giám sát.

Một cache chưa có đủ lookups không nên dùng số hit rate mà không nhìn sample count để ra quyết định quan trọng.

## 56. Caffeine hit rate không bao phủ toàn service

Một API có thể:

~~~text
GET product
  L1 Caffeine hit
  OR L1 miss -> Redis L2 hit
  OR both miss -> MongoDB
```

Nếu xem Caffeine hit rate 70% rồi kết luận 30% requests tới MongoDB là sai. 30% đó còn qua Redis; có thể phần lớn hit L2.

Phải đo đường request và L2 conditional hit rate để tính tổng origin offload.

## 57. Redis keyspace_hits và keyspace_misses

Redis có các chỉ số như:

~~~text
INFO stats
keyspace_hits:<counter>
keyspace_misses:<counter>
~~~

Một phép đo minh họa:

\[
H_{\text{Redis}}=
\frac{\Delta keyspace\_hits}
{\Delta keyspace\_hits+\Delta keyspace\_misses}
\]

Các counters là số trên **Redis server/instance** theo semantics của những lookup commands tương ứng, không tự là hit ratio riêng cho Java API của bạn.

Nếu Redis dùng chung session cache, feature flag cache và product cache, cần thêm **application metrics** để biết nhóm nào tạo hits/misses.

## 58. Redis INFO còn phải xem gì?

Các nhóm số liệu hữu ích:

- `used_memory`, `used_memory_rss`.
- `maxmemory` và eviction policy.
- `evicted_keys`, `expired_keys` theo semantics server.
- Connection count.
- Ops/sec, instantaneous throughput.
- Command latency / slowlog.
- Key counts/TTL distribution.
- Fragmentation/allocator stats.
- Network input/output.
- Replication/persistence health.
- Error/timeout metrics của Java client.

Một cache báo 99% hits nhưng đang gần OOM, eviction liên tục hoặc replication buffer quá lớn vẫn không ổn.

## 59. Java Redis: đo từng nhánh request

Pseudocode:

~~~java
public ProductCard getProduct(String key) {
    long started = System.nanoTime();

    String cached = redis.get(key);
    if (cached != null) {
        metrics.cacheHit.increment();
        ProductCard card = deserialize(cached);
        metrics.cacheHitPath.record(
            System.nanoTime() - started
        );
        return card;
    }

    metrics.cacheMiss.increment();
    ProductCard card = productSource.load(key);

    // Sử dụng populate policy, TTL và version guard phù hợp.
    redis.setex(key, 60, serialize(card));

    metrics.cacheMissPath.record(
        System.nanoTime() - started
    );
    return card;
}
~~~

Đây là **Java pseudocode**, không phải một class/SDK hoàn chỉnh; `metrics`, `redis`, `productSource` và serializer là abstraction.

Ví dụ cố tình lộ một vấn đề: giữa `load` và `setex`, source có thể thay đổi, nên code production cần xử lý **stale population race**, thất bại khi Redis timeout, negative caching, tenant namespace và deadline. Không dùng code minh họa làm lời khẳng định nó đã bảo vệ mọi trường hợp.

## 60. Đo cache timeout khác cache miss

Redis GET có thể:

- Hit.
- Miss.
- Timeout.
- Connection failure.
- Authentication/authorization failure.
- Invalid payload/deserialize failure.
- Value có version stale.

Không đếm mọi exception thành miss hợp lệ vì dễ che reliability issue.

Một bộ metric:

~~~text
cache_lookup_total{result="hit"}
cache_lookup_total{result="miss"}
cache_lookup_total{result="timeout"}
cache_lookup_total{result="error"}
cache_lookup_total{result="stale"}
cache_bypass_total
```

Trong monitoring thực tế, các tên/labels cần tuân thủ naming standards, tránh cardinality cao và bảo đảm các nhánh loại trừ nhau khi tính ratio.

## 61. Một schema metric ở application layer

Ví dụ khái niệm:

~~~text
cache_lookup_total{
  cache="product",
  tier="l1",
  result="hit"
}

cache_lookup_total{
  cache="product",
  tier="l2",
  result="miss"
}

cache_path_duration_seconds_bucket{
  cache="product",
  path="origin_fallback",
  le="0.2"
}

cache_population_total{
  cache="product",
  result="success"
}

cache_data_staleness_seconds_bucket{
  cache="product",
  le="30"
}
~~~

Không dùng raw `productId` làm Prometheus label cho hàng triệu products. Dùng tracing/sampling/log với chính sách dữ liệu phù hợp khi cần chẩn đoán một key.

## 62. PromQL: tỷ lệ hit theo cửa sổ

Giả sử counters được export như ở trên:

~~~promql
sum(rate(cache_lookup_total{
  cache="product",tier="l1",result="hit"
}[5m]))
/
sum(rate(cache_lookup_total{
  cache="product",tier="l1",result=~"hit|miss"
}[5m]))
~~~

Đây là ví dụ PromQL cho **hit/(hit+miss)** của L1. Các nhánh timeout, stale, bypass không ở mẫu số; nếu dashboard muốn **effective hit per eligible request**, cần định nghĩa denominator khác.

Nếu mẫu số bằng 0 trong khoảng không có traffic, dashboard nên hiển thị no-data thay vì tự khẳng định 100% hit.

## 63. PromQL: tỷ lệ origin fallback

Nếu mỗi request được gắn một response-path label ở application layer:

~~~promql
sum(rate(api_cache_path_total{
  route="product_get",path="origin"
}[5m]))
/
sum(rate(api_cache_path_total{
  route="product_get",path=~"l1|l2|origin|bypass"
}[5m]))
~~~

Ví dụ metric này đo **tỷ lệ request đi origin** theo các path được khai báo. Nếu một request có thể đi nhiều paths hoặc retries, cần điều chỉnh instrumentation để mỗi request được đếm một lần ở cấp request.

## 64. PromQL: p99 từ histogram

Ví dụ nếu đã export histogram của HTTP end-to-end latency:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_request_duration_seconds_bucket{
      route="product_get"
    }[5m])
  )
)
~~~

Tên metric và labels là minh họa. Phải đảm bảo histograms có buckets phù hợp SLO, instance aggregation đúng và sample volume đủ. Không lấy average của từng instance p99 để làm p99 toàn hệ.

Nếu dùng Prometheus native histograms, cú pháp/aggregation có thể khác classic bucket histogram ví dụ.

## 65. Đo hit-path và miss-path latency riêng

Nên có ít nhất ba distributions:

1. **Hit-path end-to-end latency**.
2. **Miss-path end-to-end latency**.
3. **Overall API latency**.

Thêm:

- Redis/network GET latency.
- Database origin query latency.
- Cache serialization/deserialization.
- Populate/refresh latency.
- Queue wait/connection checkout.
- Retry/circuit-breaker latency.

Không dùng latency Redis 1 ms để kết luận HTTP response 1 ms: network/client/auth/business logic vẫn có chi phí.

## 66. Mỗi endpoint cần cache policy riêng

| Endpoint | Cache strategy | Rủi ro chính |
|---|---|---|
| GET public article | TTL dài + invalidation | Stale content |
| GET Product Card | TTL + version/event invalidation | Giá/trạng thái stale |
| GET Inventory display | TTL ngắn / read model | Availability hint sai |
| POST Checkout | Source conditional write | Không được dựa vào cache làm authority |
| GET User Permissions | Thường yêu cầu freshness chặt | Revocation delay |
| GET Analytics Dashboard | Cache aggregate theo watermark | Báo cáo cũ hoặc thiếu partition |
| GET Recommendations | Có thể stale trong giới hạn | Personalization freshness |
| Admin audit export | Có thể bypass/đọc snapshot | Scan pollution và tính toàn vẹn |

Không nên áp một global TTL 24 giờ cho mọi collection chỉ để đạt cache hit ratio đẹp.

## 67. Cache data age và freshness SLO

Một projection có thể mang:

~~~json
{
  "productId": "p-101",
  "sourceVersion": 42,
  "projectedAt": "2026-11-14T09:00:00Z",
  "content": { "status": "ACTIVE" }
}
~~~

`now - projectedAt` là **tuổi kể từ lúc projection được ghi**, không nhất thiết là độ trễ so với latest source state.

Muốn đo freshness đáng tin hơn có thể dùng:

- Source commit version/time có semantics rõ.
- Consumer applied version.
- Last validated version.
- Sampling đối chiếu source authoritative.
- Watermark của change-log.
- SLO theo event-to-visible delay.

Một cache được refresh lúc 10:00 từ replica v40 trong khi source đã v42 không phải fresh chỉ vì timestamp mới.

## 68. Chi phí của một cache hit

Có những chi phí không xuất hiện trong hit ratio:

- RAM và replication memory.
- Redis cluster nodes/managed cache fees.
- Network egress giữa AZ/region.
- TLS connections.
- Serialization CPU.
- JVM heap/GC.
- Extra Redis GET roundtrip.
- Cache invalidation/event pipeline.
- Operational complexity.
- Data transfer khi resharding.
- Capacity reserve cho failover.

Một hit vẫn có chi phí, và một miss có thể còn chịu cả chi phí cache lookup **lẫn** origin query.

## 69. Một mô hình cost/benefit đơn giản

Giả sử:

- \(R\): eligible requests trong một tháng.
- \(H\): hit ratio.
- \(C_o\): trung bình chi phí origin read nếu không cache.
- \(C_c\): trung bình chi phí cache lookup.
- \(C_m\): chi phí cache memory/ops trong tháng.
- \(C_i\): chi phí invalidation/refresh.

Mô hình xấp xỉ:

\[
C_{\text{with cache}}
\approx R C_c + R(1-H)C_o + C_m + C_i
\]

So với không cache:

\[
C_{\text{no cache}}\approx R C_o
\]

Điều kiện cache có lợi về chi phí theo mô hình:

\[
R H C_o > R C_c+C_m+C_i
\]

Đây chỉ là một mô hình để đặt câu hỏi; thực tế có miss amplification, variable origin cost, network transfer, capacity tiers, batching, coalescing và SLO risk. Không lấy công thức đơn giản làm hóa đơn cloud chính xác.

## 70. CPU load và chi phí NoSQL

Trong một hệ DynamoDB, miss có thể làm tiêu thụ read capacity; trong MongoDB miss có thể tăng index/disk IO và CPU; trong Cassandra miss tăng coordinator/replica reads; Redis cache có chi phí RAM/ops riêng.

Không kết luận “95% hit nghĩa origin giảm đúng 95% chi phí” nếu:

- Cache chỉ bao phủ một phần endpoints.
- Một miss tạo nhiều queries.
- Origin vẫn phải phục vụ writes.
- Các instance idle/committed costs không đổi.
- Read units phụ thuộc item size và consistency.
- Caching tăng refresh/background reads.
- Cross-region data transfer tăng.

Tính ROI cần đo nguồn và workload thật.

## 71. Cache có thể che vấn đề thiết kế truy vấn

Nếu một query NoSQL thiếu index và mất 2 giây nhưng cache hit 99%, nhóm có thể bỏ qua query. Khi cache flush, deploy hoặc key hết hạn đồng loạt, origin nhận lượng miss lớn và sập.

Nên yêu cầu **miss path có khả năng chịu tải**:

- Index/query plan phù hợp.
- Timeout và circuit breaker.
- Load shedding/backpressure.
- Batching/coalescing.
- Capacity dự phòng cho cache failure scenario.
- Retry budget.
- Warm-up/restore plan.

**Cache là một lớp tối ưu, không phải giấy phép để origin path không thể vận hành.**

## 72. Benchmarks phải có cold và warm phases

Một benchmark chạy sau khi load toàn bộ hot keys có thể chỉ đo steady-state hit latency.

Nên tách:

1. **Cold cache:** từ trạng thái trống.
2. **Warm-up:** hit ratio đang tăng.
3. **Steady state:** workload ổn định.
4. **Churn:** key popularity/schema thay đổi.
5. **Flush/failover:** cache mất hoặc restart.
6. **Burst:** traffic tăng đột ngột.
7. **Write-heavy phase:** invalidation nhiều.
8. **Scan-heavy phase:** tránh pollution.
9. **Region failover:** network/cross-region latency thay đổi.

Không trộn số đo cold start của phương án A với warm state của phương án B để tuyên bố B nhanh hơn.

## 73. Workload benchmark phải đại diện

Một test cache dùng 100 keys và 1 triệu requests có thể đạt 99,99% hit, nhưng production có 20 triệu unique keys, nhiều tenants, skew và TTL churn.

Cần mô tả:

- Request QPS/concurrency.
- Unique key cardinality.
- Zipf/hot-key distribution hoặc trace thật.
- Read/write mix.
- Object sizes.
- TTL/invalidation rates.
- Origin latency distribution.
- Cold/warm ratio.
- Tenant/region mix.
- Cache capacity/eviction policy.
- Error/failover cases.

Không chọn benchmark chỉ vì nó giúp tối ưu một metric dễ đẹp.

## 74. A/B experiment thay vì chỉ so trước/sau

Giả sử muốn tăng cache TTL từ 5 phút lên 30 phút.

Một experiment tốt:

- Randomize users/requests/keys theo phương pháp tránh cross-contamination.
- Giữ workload đủ tương đương.
- Theo dõi hit ratio, p95/p99, source QPS, memory và cache cost.
- Đo freshness violations/stale responses.
- Quan sát lỗi/rollback và tenant cohorts.
- Có guardrail và kill switch.
- Xem kết quả theo thời gian đủ dài để trải qua warm-up, eviction và write churn.

Nếu hai variants chia chung Redis namespace, experiment có thể bị nhiễm lẫn TTL/data; cần namespace hoặc thiết kế phân nhóm rõ.

## 75. Guardrail chống tối ưu lệch mục tiêu

Ví dụ mục tiêu:

~~~text
Primary objective:
  Reduce GET Product p99 from 300 ms to 180 ms

Guardrails:
  Cache data staleness <= allowed SLO
  Checkout correctness unchanged
  Origin DB QPS below safe capacity
  Redis memory headroom >= policy
  Error/timeout rate not worse
  Cost per 1k eligible requests within budget
  No material regression for smaller tenants
~~~

Nếu hit ratio tăng 4 điểm nhưng stale price violation tăng gấp đôi, experiment cần được xem xét thất bại theo guardrail.

## 76. Những tình huống “tối ưu một chỉ số” gây hại

| Cách làm | Chỉ số được cải thiện | Tác hại có thể xảy ra |
|---|---|---|
| Tăng TTL lên rất dài | Hit ratio | Stale dữ liệu, revocation chậm |
| Cache mọi object | Lookup hit | Scan pollution, memory cost |
| Dồn key cùng slot/node | Locality/single-key hit | Hot shard, mất cân bằng |
| Tăng cache size sát RAM | Hit ratio | OOM/GC/evictions |
| Chỉ đếm valid Redis GETs | Dashboard hit | Che cache timeouts/bypass |
| Bỏ read verification | Lookup latency | Sai thông tin, security risk |
| Stale-if-error mọi endpoint | Availability | Sai inventory/authorization |
| Tăng retries trên miss | Success sau retry | Retry storm, tail latency |
| Tắt negative TTL | Ngắn hạn có vẻ fresh | Cache penetration origin overload |
| Tăng refresh-ahead mạnh | Hits cao | Background origin QPS/cost tăng |
| Cache result query thiếu index | Warm p50 | Origin meltdown khi cache flush |
| Chỉ nhìn p50 | UX trung bình | p99 và nhóm yếu bị bỏ qua |
| Chỉ nhìn p99 | Tail cải thiện | Có thể tăng cost hoặc sai dữ liệu |

**Tối ưu tốt nhất không nhất thiết có hit ratio cao nhất; đó là cấu hình đáp ứng mục tiêu tổng thể trong các ràng buộc.**

## 77. Một dashboard tối thiểu

Các nhóm nên hiển thị cùng nhau:

**Traffic và cache behavior**

- Eligible requests/s.
- L1/L2 hits, misses, bypasses, errors.
- Effective hit rate và origin fallback rate.
- Key size distribution, evictions, expirations.

**Trải nghiệm**

- HTTP p50/p95/p99 và % requests dưới latency SLO.
- Hit-path/miss-path distributions.
- Cache lookup timeout, cache circuit breaker state.
- Error rate và fallback success.

**Nguồn NoSQL**

- Read QPS/queries per miss.
- CPU/IO/throughput quota.
- Query p95/p99.
- Throttling, connection pool saturation.
- Hot partition/key signals.

**Đúng đắn và độ tươi**

- Stale-served count.
- Event-to-cache lag.
- Sampling mismatch với source.
- Invalidation failures.
- Duplicate/negative cache anomalies.

**Chi phí và sức khỏe**

- RAM/RSS/headroom, fragmentation.
- Redis cost/network.
- Java GC pause.
- Origin cost per request.
- Cache refresh/populate throughput.

## 78. SLO có thể mâu thuẫn, cần quy tắc ưu tiên

Một service có thể đưa ra:

~~~text
Latency SLO: 99% requests < 150 ms
Freshness SLO: 99.9% catalog values < 30s behind source
Cost budget: <$X / 1M reads
```

Có thể không đạt cả ba bằng một TTL duy nhất. Cần nêu ưu tiên và **đường hành động khác nhau theo endpoint**:

- Catalog view cho phép stale ngắn hạn để giữ latency.
- Checkout xác minh source condition, chấp nhận thêm latency.
- Admin/security action ưu tiên correctness và authorization freshness.
- Analytics read model hiển thị data-as-of thay vì giả vờ real-time.

Không có một cache policy “tối ưu toàn hệ” nếu nghiệp vụ và consistency requirements khác nhau.

## 79. Cache misses không luôn là xấu

Một cache miss có thể là kết quả mong muốn:

- Key vừa được tạo/đổi và cache đã invalidated đúng.
- Cache cố ý bypass cho query nhạy consistency.
- Bản stale bị loại bỏ thay vì phục vụ giá sai.
- Object quá lớn hoặc quá lạnh không đáng cache.
- Tenant có policy không cache PII.
- Data deletion yêu cầu xóa cache ngay.

Một hệ có valid-hit ratio 90% và không vi phạm correctness có thể tốt hơn hệ hit 99% nhưng dùng dữ liệu stale cho quyết định không thể hoàn tác.

## 80. Khi hit ratio giảm, hỏi những gì?

Một quy trình điều tra:

1. Traffic volume, key cardinality và request mix có đổi không?
2. Có deploy/scale out khiến L1 cold không?
3. Redis key evictions/expired_keys có tăng không?
4. Cache TTL/config/invalidation có thay đổi không?
5. Một job scan có pollution không?
6. Cache lookup timeouts/errors có bị đếm thành miss không?
7. Có tenant hoặc region cụ thể gây giảm không?
8. Các key mới có tăng do seasonal/event campaign không?
9. Origin QPS/CPU/IO có tăng tương ứng không?
10. API p95/p99/error/freshness có thật sự xấu đi không?

Đừng mặc định tăng TTL hoặc RAM trước khi hiểu nguyên nhân.

## 81. Khi hit ratio tăng nhưng p99 xấu đi

Một quy trình khác:

1. Hit-path Redis RTT có tăng?
2. Serialization/decompression CPU có nặng?
3. Java L1 cache gây GC pauses?
4. Miss path origin query có chậm bất thường?
5. Miss amplification hoặc retry storm tăng?
6. Cache GET timeout trước fallback?
7. Workload mix chuyển sang các request khó?
8. Có nhóm tenant/region chậm bị ẩn trong aggregate?
9. Cache outage/bypass có bị loại khỏi hit ratio?
10. Percentile histogram có đủ buckets và aggregation đúng?

Trả lời cần dữ liệu latency, không thể suy từ hit ratio một mình.

## 82. Khi origin QPS tăng dù hit ratio không đổi

Có thể vì:

- Tổng traffic tăng.
- Eligible request fraction tăng.
- Một miss tạo nhiều source queries hơn.
- Cache refresh/background jobs tăng.
- L1 miss nhưng L2 hit rate thay đổi.
- Negative cache policy đổi.
- Origin retries/speculative requests tăng.
- Có cache bypass path mới.
- Cache key thiết kế thay đổi cardinality.
- Một số tenants không dùng cache.

Nên đo **origin queries per incoming request** và **origin queries per cache miss** bên cạnh hit ratio.

## 83. Khi memory tăng nhưng hit ratio gần như đứng yên

Có thể:

- Cache đang giữ cold large objects.
- Entry metadata/fragmentation tăng.
- TTL quá dài so reuse interval.
- Non-evictable keys/metadata tích tụ.
- Allocation/GC pressure tăng.
- Admission policy kém.

Nên cân nhắc weight-based sizing, admission, per-object max size, TTL theo nhóm, hoặc bỏ cache một số query. Đừng chỉ tăng RAM vì đã dùng hết.

## 84. Bảo mật dữ liệu trong cache

Một cache key có tenant ID nhưng không có authorization đúng vẫn có thể rò dữ liệu:

~~~text
cache key = product:100
Tenant A fills cache
Tenant B requests product:100
API returns Tenant A content
```

Cần:

- Namespace tenant và principal theo data contract.
- Không cache kết quả user-specific dưới key dùng chung.
- Không bỏ qua authorization trên read path.
- Mã hóa và quản lý secrets/TLS phù hợp.
- Policy TTL/invalidation cho token/revoked permissions.
- Cân nhắc PII retention, backup và dump của Redis.
- Không log raw cache values chứa sensitive data.

Hit ratio cao từ việc dùng chung key giữa tenants **không phải thành công** nếu trả nhầm dữ liệu.

## 85. Dữ liệu cache có thể bị replay sau khi xóa

Nếu source xóa Product hoặc một bản PII, một event update cũ đến muộn có thể ghi lại cache/search projection.

Version/generation guard và tombstone retention giúp chống stale write:

~~~text
Delete source generation=1 version=40
Cache marker tombstone v40
Delayed update v39 arrives
-> reject, do not resurrect
```

Job reconciliation định kỳ có thể phát hiện cache/search orphan, nhưng **không thay nghĩa vụ xóa đúng hạn** khi dữ liệu nhạy cảm.

## 86. Case study: tối ưu hit ratio sai cách

Giả định một service:

~~~text
GET /catalog/product
Requests: 10,000/s
Hit ratio: 90%
Hit latency avg: 3 ms
Miss latency avg: 150 ms
```

Average xấp xỉ:

\[
0.90\cdot3+0.10\cdot150=17.7\text{ ms}
\]

Nhóm tăng TTL 5 phút → 24 giờ:

~~~text
New hit ratio: 99%
Hit latency avg: 3 ms
Miss latency avg: 150 ms
New avg approx: 4.47 ms
```

Dashboard rất đẹp. Nhưng nếu tỷ lệ giá stale tăng và checkout phải từ chối/đối soát thêm, lợi ích tổng thể có thể âm.

Giải pháp tốt hơn có thể là TTL theo loại field + event invalidation + source verification tại checkout + theo dõi staleness SLO. Các con số trong case study là **giả định để phân tích**, không phải benchmark thực nghiệm.

## 87. Case study: cache tăng hit nhưng tăng chi phí

Giả định:

~~~text
Option A:
  1 GiB cache
  hit=90%
  cache cost=$100/month

Option B:
  8 GiB cache
  hit=94%
  cache cost=$650/month

Origin savings from extra 4% hits:
  estimated $150/month
```

Nếu không có lợi ích latency/capacity khác, chênh lệch chi phí cache +$550 để tiết kiệm origin ~$150 có thể không hợp lý.

Nhưng nếu origin không thể scale hoặc 4% misses ấy làm p99 vi phạm SLO, quyết định có thể khác. **ROI cần đặt cạnh SLO và rủi ro sự cố, không chỉ dollars.**

## 88. Case study: Redis L2 và Caffeine L1

Giả sử:

~~~text
HTTP requests: 10,000/s
L1 hit ratio: 70%
L2 hit ratio conditional on L1 miss: 90%
```

Lượng request:

~~~text
L1 hits:     7,000/s
L1 misses:   3,000/s
L2 hits:     2,700/s
Origin reads:  300/s
```

Tổng hit ratio theo incoming requests:

\[
(7000+2700)/10000=97\%
\]

Nếu một pod mới scale out khiến L1 hit giảm còn 40%, L2 vẫn 90% trên L1 misses:

~~~text
Origin reads = 10,000 * 0.60 * 0.10 = 600/s
```

Source load **tăng gấp đôi** dù L2 conditional hit giữ nguyên. Vì vậy cần monitor cả hai tầng, cold start và origin QPS.

## 89. Case study: percentile cliff

Giả sử:

~~~text
All hits: ~5 ms
All misses: ~400 ms
```

Nếu miss ratio là 0,5%, gần như toàn bộ 99% requests nhanh nhất thuộc hits; p99 có thể quanh 5 ms theo bộ dữ liệu và cách ước lượng.

Nếu miss ratio tăng tới 2%, nhóm requests chậm chiếm 2%; p99 có thể ở 400 ms. Hit ratio chỉ giảm 1,5 điểm phần trăm, nhưng p99 có thể tăng nhiều lần.

Bài học: theo dõi **latency SLO violation rate, p99/p99.9 và miss count**, không suy percentile từ hit ratio tuyến tính.

## 90. Bài tập A — Tính hit ratio

Một cache có 18.000 hits và 2.000 misses trong năm phút.

**Hỏi:** hit ratio và miss ratio?

**Hướng giải:**

\[
H=18000/20000=90\%,\qquad M=10\%
\]

## 91. Bài tập B — Origin QPS

Service nhận 5.000 eligible lookups/s, mỗi miss tạo một origin query; hit ratio 96%.

**Hỏi:** origin queries/s xấp xỉ bao nhiêu?

**Hướng giải:**

\[
5000\cdot(1-0.96)=200/s
\]

Không dùng kết quả này nếu một miss phát nhiều queries hoặc có bypass/refresh chưa tính.

## 92. Bài tập C — Giảm hit ratio vài điểm

Traffic 20.000/s, hit ratio giảm 95% xuống 90%.

**Hỏi:** origin reads tăng ra sao trong mô hình một miss → một read?

**Hướng giải:** từ 1.000/s lên 2.000/s, tức tăng gấp đôi.

## 93. Bài tập D — Tính latency trung bình

Hit ratio 95%, average hit path 2 ms, miss path 200 ms.

**Hỏi:** average latency xấp xỉ?

**Hướng giải:**

\[
0.95\cdot 2+0.05\cdot200=11.9\text{ ms}
\]

Chỉ dùng khi hai nhóm latency có cùng phạm vi end-to-end.

## 94. Bài tập E — Tăng hit ratio nhưng chậm hơn

Phương án A hit 90%, hit path 1 ms, miss path 80 ms. B hit 96%, hit path 12 ms, miss path 80 ms.

**Hỏi:** phương án nào có average thấp hơn?

**Hướng giải:** A ≈ 8,9 ms; B ≈ 14,72 ms. B hit nhiều hơn nhưng mỗi hit đắt hơn.

## 95. Bài tập F — L1/L2

L1 hit 60%, trong L1 misses L2 hit 80%.

**Hỏi:** origin fallback fraction?

**Hướng giải:** \(0.4\times0.2=8\%\). Total cache-served 92%.

## 96. Bài tập G — p99 không tuyến tính

Một người tính:

~~~text
p99 = hitRate*p99Hit + missRate*p99Miss
```

**Hỏi:** công thức đúng không?

**Hướng giải:** không. Quantile của mixture không bằng weighted average các quantile; cần histogram/quan sát request-level.

## 97. Bài tập H — Negative caching

Một key không tồn tại bị hỏi 100.000 lần/s, mỗi lần miss đọc database.

**Hỏi:** có cách gì giảm tải?

**Hướng giải:** validate ID và dùng negative cache sentinel có TTL/key limits thích hợp; không cache timeout/403 như NOT_FOUND.

## 98. Bài tập I — Cache stampede

Một hot key có 4.000 requests/s, vừa hết TTL, mỗi miss load 5 NoSQL queries.

**Hỏi:** nguy cơ gì?

**Hướng giải:** một đợt misses có thể tạo hàng nghìn origin operations trong thời gian ngắn; cần coalescing, staggered TTL/refresh-ahead và backpressure.

## 99. Bài tập J — Stale hit

Redis có giá cũ; GET trả value và được đếm hit. Source đã cập nhật giá.

**Hỏi:** hit ratio đo đúng đắn chưa?

**Hướng giải:** chưa. Phải đo freshness/version và đảm bảo checkout xác minh source.

## 100. Bài tập K — Simpson's paradox

Nhóm hot có hit 99→98%, nhóm rare có hit 50→40%, nhưng tổng hit tăng do hot traffic chiếm phần lớn hơn.

**Hỏi:** có thể kết luận cache cải thiện không?

**Hướng giải:** không; cần so cohort và điều chỉnh workload mix.

## 101. Bài tập L — Redis global stats

Redis INFO báo 99% keyspace hit. Product endpoint có 65% effective hit.

**Hỏi:** có mâu thuẫn không?

**Hướng giải:** không. Redis global stats gộp nhiều workload và không tính bypass/request paths như app metric.

## 102. Bài tập M — Cache quá lớn

Tăng local JVM cache từ 1 GiB lên 5 GiB nâng hit từ 92 lên 93%, nhưng GC p99 tăng mạnh.

**Hỏi:** quyết định thế nào?

**Hướng giải:** xem end-to-end p99, origin savings, cost/GC; hit tăng một điểm có thể không đáng.

## 103. Bài tập N — Cache bypass

40% requests bypass cache; 60% lookup còn lại hit 99%.

**Hỏi:** có thể nói 99% mọi HTTP requests được cache phục vụ không?

**Hướng giải:** không. Cache-served fraction tối đa là \(0.60\times0.99=59.4\%\) nếu các nhóm loại trừ nhau và định nghĩa như trên.

## 104. Bài tập O — Scan pollution

Analytics job đọc hàng triệu keys một lần, hot keys bị evicted.

**Hỏi:** tăng TTL có phải giải pháp đầu tiên?

**Hướng giải:** không chắc. Cân nhắc bypass/admission policy hoặc cache tách workload; đo eviction và hit rate của user endpoints.

## 105. Bài tập P — Freshness và security

Cache lưu `userActive=true` nhưng source đã revoke quyền. TTL 24 giờ tăng hit.

**Hỏi:** có được dùng cache để cho phép chuyển tiền?

**Hướng giải:** không khi policy yêu cầu quyền hiện hành; cần authoritative verification và invalidation/freshness contract đủ mạnh.

## 106. Bài tập Q — Cache outage

Redis GET timeout 500 ms, sau đó Java fallback MongoDB 20 ms.

**Hỏi:** cache có giúp latency không?

**Hướng giải:** không trên đường này; miss/error path ~520 ms cộng overhead, cần timeout/circuit breaker/bypass và origin capacity controls.

## 107. Bài tập R — Invalidation race

Reader load source v10 rồi bị pause; writer commit v11 và xóa cache; reader resume ghi v10 vào cache.

**Hỏi:** TTL và invalidate-on-write có đủ không?

**Hướng giải:** không loại trừ race. Cần version guard/revalidation hoặc protocol thích hợp, TTL chỉ giới hạn thời gian stale.

## 108. Bài tập S — Byte hit vs request hit

90 requests nhỏ 1 KiB hit; 10 requests lớn 10 MiB miss.

**Hỏi:** request hit ratio cao có nghĩa tiết kiệm nhiều bandwidth không?

**Hướng giải:** không; byte hit ratio rất thấp vì phần lớn bytes nằm ở misses.

## 109. Bài tập T — Evaluation plan

Nhóm muốn tăng Caffeine maximumSize để nâng 95→97% hit.

**Hỏi:** cần những guardrails nào?

**Hướng giải:** HTTP p95/p99, GC, memory headroom, source QPS, stale/invalid hits, error rate, eviction, cost và kiểm tra cold start/tenant cohorts.

## 110. Checklist đo cache trong NoSQL

1. Hit ratio đang đo **cache lookup, HTTP requests hay bytes**?
2. Lookup denominator có bao gồm miss/error/bypass/stale không?
3. Số lượng samples và window có đủ để kết luận không?
4. Có tách các cache layers L1, L2 và origin path không?
5. L2 hit ratio có được ghi là **conditional on L1 miss** không?
6. Có effective cache-served fraction theo incoming requests không?
7. Có valid/fresh-hit metric khi business cần không?
8. Có đo latency hit/miss end-to-end riêng không?
9. Có p50, p95, p99 và SLO violation rate không?
10. Có dùng histogram đúng cách thay vì trung bình của p99 không?
11. Miss amplification/origin queries per miss có được đo không?
12. Có origin QPS, CPU/IO/quota và query latency không?
13. Cache timeout/bypass có bị che khỏi dashboard không?
14. Có đo negative hit và cacheable 404 theo semantics rõ không?
15. Có guard chống cache stampede/avalanche không?
16. TTL có phù hợp freshness policy thay vì chỉ hit ratio không?
17. L1 invalidation có tới mọi Java instances không?
18. Có version/generation guard ngăn stale populate không?
19. Có source validation cho invariant quan trọng không?
20. Có phân loại public, personal, financial và authorization data không?
21. Có Redis memory/RSS/fragmentation/evictions không?
22. Có Java GC pause, heap occupancy và Caffeine load penalty không?
23. Có xác định working set, object size và admission policy không?
24. Có so cold start, steady state, burst và cache outage không?
25. Có phân tích theo tenant cohort/region/operation không?
26. Có tránh raw key/tenant labels cardinality quá cao không?
27. Có tính cost per request và memory/network overhead không?
28. Có benchmark origin khi cache bị bypass/flush không?
29. Experiment có guardrails về data correctness không?
30. Có runbook rollback TTL/capacity/admission changes không?

## 111. Mẫu hợp đồng quan sát cache

~~~yaml
service: ProductReadApi
cache:
  architecture: L1_Caffeine_L2_Redis
  keyScope: tenantIdAndProductId
  sourceOfTruth: CatalogNoSQL
  ttl:
    policy: perDataClass
    invalidateOnSourceChange: true
  ordering:
    useSourceVersion: true
    rejectOlderPayload: true
  negativeCaching:
    allowedForAuthoritativeNotFound: true
    maxTtl: bounded
measurement:
  denominator: eligibleApiReads
  requestPaths:
    - l1Hit
    - l2Hit
    - originMiss
    - bypass
    - cacheError
  lookupOutcome:
    - hit
    - miss
    - stale
    - timeout
    - error
  metrics:
    - effectiveHitRatio
    - freshHitRatio
    - originQueriesPerRequest
    - cacheHitLatency
    - cacheMissLatency
    - apiP95
    - apiP99
    - sourceQps
    - evictions
    - memoryRss
    - gcPause
    - staleServedCount
    - costPerThousandRequests
slo:
  latency: definedPerEndpoint
  freshness: definedPerDataClass
  correctness: sourceValidationAtBusinessCommit
resilience:
  singleFlight: enabledWhereUseful
  ttlJitter: withinFreshnessBound
  redisTimeout: bounded
  originBackpressure: required
experimentGuardrails:
  - noIncreaseInStaleViolations
  - noOriginOverload
  - noApiTailLatencyRegression
  - noUnacceptableCostIncrease
tests:
  - coldStart
  - hotKeyExpiration
  - invalidationRace
  - redisTimeout
  - cacheFlush
  - loadSpike
  - staleAuthorization
~~~

YAML là **mẫu mô tả thiết kế**, không phải một file cấu hình mà Caffeine/Redis/MongoDB hoặc Spring Boot tự hiểu. Những guarantees phải được hiện thực bằng driver, instrumentation và policies thật.

## 112. Kết luận

**Cache hit ratio là một chỉ số hữu ích nhưng không phải mục tiêu cuối cùng.** Nó cho biết bao nhiêu lookup tìm thấy dữ liệu cache theo một cách đếm cụ thể; nó không tự nói API nhanh bao nhiêu, origin có chịu được misses không, cache có trả bản cũ không hoặc tổng chi phí có giảm không.

Khi đánh giá cache trong Database No SQL, luôn đặt cạnh nhau:

- **Hit/miss ratio** có mẫu số rõ ràng, chia theo cache tier và workload.
- **Độ trễ p50/p95/p99** của toàn request, hit path và miss path.
- **Tải lên NoSQL source** gồm queries per miss, CPU/IO, throttling và hot partitions.
- **Freshness/correctness** gồm TTL, invalidation, stale-hit, tenant/authorization và version guard.
- **Resilience** gồm stampede, cache outage, negative cache, circuit breaker và cold start.
- **Chi phí** gồm RAM, GC, Redis network, replication, origin reads và vận hành.

> **Tối ưu cache thành công không phải khi dashboard báo 99% hit bằng mọi giá; đó là khi dữ liệu vẫn đủ đúng, người dùng nhận phản hồi trong SLO, origin có headroom khi miss, và tổng chi phí/rủi ro ở mức chấp nhận được.**

Một kỹ sư NoSQL giỏi sẽ luôn hỏi **“Hit của ai, ở tầng nào, tránh được bao nhiêu công việc thật, nhanh bao nhiêu trong trường hợp xấu, và có còn đúng không?”** trước khi quyết định tăng TTL, tăng cache size hoặc thay eviction policy.
