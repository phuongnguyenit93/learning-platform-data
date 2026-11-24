# Đo tỷ lệ cache hit và kiểm chứng tính đúng đắn của phản hồi trong Spring Cloud Gateway

Bật response cache ở API Gateway có thể giảm độ trễ và số lần gọi microservice, nhưng **cache trả lời nhanh không đồng nghĩa cache trả lời đúng**. Một tỷ lệ hit cao vẫn có thể đi kèm lỗi nghiêm trọng: trả dữ liệu của tenant khác, tái sử dụng một response đã hết hạn, bỏ qua biến thể ngôn ngữ hoặc giữ nội dung cũ sau thao tác cập nhật.

Trong **SPRING_CLOUD_GATEWAY**, chức năng response caching (ví dụ `LocalResponseCache` của Gateway Server WebFlux ở các phiên bản hỗ trợ) nằm trong cùng hệ thống route predicate, GatewayFilter và downstream routing. Bài học thuộc chương **Bộ nhớ đệm**, tập trung vào hai câu hỏi không thể tách rời:

1. **Đo hiệu quả:** Bao nhiêu request thực sự được trả từ cache? Tỷ lệ hit/miss được tính trên tập request nào? Đã giảm bao nhiêu lượt gọi backend và độ trễ?
2. **Kiểm chứng tính đúng đắn:** Mỗi hit có trả đúng dữ liệu cho URL, query, người dùng, tenant, header biến thể và trạng thái dữ liệu hiện tại hay không?

Bài cũng liên hệ xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và observability để xây dựng cổng vào microservices vừa hiệu quả vừa an toàn.

> **Phạm vi:** Ví dụ chủ yếu theo **Spring Cloud Gateway Server WebFlux** với cấu hình kiểu Gateway 4.x. `LocalResponseCache` là bộ đệm **cục bộ trong tiến trình Gateway**, không phải mặc định là cache phân tán. Tên thuộc tính, các trạng thái cache được, cách xử lý cache-control và metrics có thể thay đổi theo release train. Luôn đối chiếu tài liệu **đúng phiên bản** và kiểm thử hành vi thực tế. Không áp dụng nguyên ví dụ cho Gateway Server MVC nếu chưa kiểm tra sự khác biệt.

## 1. Cache nằm ở đâu trong pipeline Gateway?

Gateway có thể cache **response** sau khi đã có kết quả từ backend để phục vụ lại các request về sau, thay vì forward mọi lần. Một pipeline khái niệm:

~~~mermaid
flowchart TD
    C["Client: GET /api/catalog/items/42"] --> S["Spring Security / WebFlux"]
    S --> P{"Route predicates match?"}
    P -->|Không| N["Handler khác / 404"]
    P -->|Có| F["Gateway filter chain"]
    F --> K["Tính định danh bản thể response / cache lookup"]
    K --> H{"Có entry hợp lệ?"}
    H -->|Hit| RH["Trả response đã lưu theo chính sách"]
    H -->|Miss / cần fetch| LB["Routing, LoadBalancer, downstream"]
    LB --> U["Backend catalog"]
    U --> E{"Response đủ điều kiện cache?"}
    E -->|Có| W["Ghi cache + phục vụ response"]
    E -->|Không| BY["Phục vụ response, không lưu"]
    W --> OUT["Client"]
    BY --> OUT
    RH --> OUT
~~~

Sơ đồ mô tả ý nghĩa **lookup → hit/miss → fetch/không fetch**, không cam kết thứ tự chính xác giữa mọi `GlobalFilter`, `GatewayFilter`, `Retry`, `CircuitBreaker` hoặc filter chuẩn hóa URL trong mọi bản Gateway. Cần xác minh thứ tự khi các filter cùng tác động lên request/response.

### Điều cache thường lưu giữ

Một entry có thể chứa response body, response headers và metadata về thời gian sống. Việc lưu dữ liệu không đủ; cache còn phải biết **khi nào entry hợp lệ và request nào được dùng lại cùng entry**.

| Thành phần | Tác động đến tính đúng đắn |
|---|---|
| HTTP method | GET thường là ứng viên tốt; POST thay đổi dữ liệu thường không nên cache một cách ngây thơ |
| Path | `/items/42` và `/items/43` cần dữ liệu riêng |
| Query string | `?lang=vi` và `?lang=en` hoặc `?sort=price` có thể tạo response khác nhau |
| Request headers | `Accept-Language`, `Accept-Encoding` và headers khác có thể tạo biến thể |
| Danh tính/tenant | Nội dung cá nhân hóa phải tách biệt hoặc **không cache ở lớp dùng chung** |
| Status code | Không phải status nào cũng được implementation lưu |
| Response headers | `Cache-Control`, `Vary`, `ETag` và metadata HTTP ảnh hưởng chính sách |
| TTL / invalidation | Entry có thể còn tồn tại nhưng đã không còn đúng với dữ liệu nguồn |

**Cache là một cơ chế tái sử dụng dữ liệu có điều kiện**, không phải shortcut để bỏ qua xác thực và phân quyền.

## 2. LocalResponseCache: chỉ bật khi hiểu phạm vi

Ở những phiên bản Gateway Server WebFlux hỗ trợ, `LocalResponseCache` là GatewayFilter Factory có thể lưu response body và headers trong **bộ nhớ của Gateway instance**. Tài liệu của các dòng liên quan mô tả điều kiện điển hình như:

- Request là **GET không có body**.
- Response có status được hỗ trợ, thường bao gồm `200 OK`, `206 Partial Content` hoặc `301 Moved Permanently` theo tài liệu phiên bản tương ứng.
- Không lưu khi request có `Cache-Control: no-store` hoặc response có `Cache-Control: no-store` / `private` theo cơ chế được mô tả.
- Cache có cấu hình **time-to-live (TTL)** và giới hạn **size**; implementation có thể sử dụng thư viện **Caffeine**.
- Một số bản tính toán/điều chỉnh `Cache-Control: max-age` theo thời gian còn lại của entry.

**Đừng suy rộng những điều này thành HTTP cache đầy đủ theo mọi đặc tả RFC.** Ví dụ phải kiểm chứng riêng việc phân biệt `Vary`, xử lý conditional GET/`304`, `Range`/`206` và dữ liệu chứa `Authorization`. Chỉ vì một status được liệt kê là có khả năng cache **không có nghĩa mọi response cùng status đó an toàn để lưu**.

### Route ví dụ dành cho catalog công khai

Giả sử backend `catalog-service` cung cấp một API **thật sự công khai, không cá nhân hóa**. Một dạng cấu hình minh họa theo các phiên bản hỗ trợ shortcut `LocalResponseCache`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: public-catalog
          uri: http://localhost:9090
          predicates:
            - Path=/api/public/catalog/**
            - Method=GET
          filters:
            - StripPrefix=2
            - LocalResponseCache=30s,50MB
~~~

Trong ví dụ, ý định là cache response trên route `public-catalog` với TTL khoảng **30 giây** và giới hạn kích thước **50 MB**. **Cú pháp shortcut, thứ tự TTL/size, đơn vị và điều kiện kích hoạt cần đối chiếu tài liệu theo đúng bản Gateway**; môi trường thực tế cũng cần các dependencies/cache implementation tương thích.

`StripPrefix=2` xóa hai phân đoạn `api` và `public`; backend nhận `/catalog/...`. Filter nào nhìn thấy URI gốc hay URI đã biến đổi phụ thuộc thứ tự filter và implementation. Khi thay path/query, kiểm chứng **hai URL có thể tạo entry chung hoặc entry riêng như thế nào** thay vì suy đoán cache key.

### Không bật toàn cục trước khi phân loại routes

Bật cache trên mọi route có thể làm dữ liệu của các API có cookie/JWT hoặc dữ liệu tenant bị lưu trong tiến trình Gateway. Quy trình an toàn:

1. Phân loại endpoint **public và ổn định** trước.
2. Chỉ bật cache cho các route đã có hợp đồng response và TTL rõ ràng.
3. Kiểm thử trường hợp không đủ điều kiện, dữ liệu phân quyền và biến thể nội dung.
4. Mở rộng dần theo kết quả metrics và correctness tests.

Đối với dữ liệu người dùng như `/api/me`, orders, hóa đơn, session, token hoặc hồ sơ tài khoản, **mặc định không dùng shared Gateway response cache** trừ khi đã có mô hình khóa theo danh tính, invalidation và isolation được chứng minh đầy đủ. `Cache-Control: private, no-store` ở upstream là tín hiệu phòng vệ cần thiết với các response nhạy cảm.

## 3. Định nghĩa hit, miss, bypass và error trước khi tính tỷ lệ

Một request đi qua route có cache chưa chắc **thực sự được lookup**. Nếu gộp mọi trường hợp làm “miss”, biểu đồ dễ đánh lừa.

| Phân loại | Diễn giải | Có tính là lookup hit/miss? |
|---|---|---|
| **HIT** | Tìm được entry phù hợp và còn hợp lệ; trả từ cache | Có |
| **MISS** | Request được phép lookup nhưng không có entry dùng được; cần fetch backend | Có |
| **BYPASS** | Không lookup/không dùng cache theo policy, ví dụ loại trừ theo method, thông tin nhạy cảm, no-store | Không, nếu metric định nghĩa như vậy |
| **INELIGIBLE** | Request/response không thuộc nhóm hỗ trợ lưu cache | Có thể là lý do bypass hoặc thống kê riêng |
| **EXPIRED / STALE** | Entry đã hết hạn hoặc không còn đủ điều kiện freshness | Phải định nghĩa rõ được ghi như miss hay một loại riêng |
| **ERROR** | Cache lookup/store có lỗi hoặc không xác định kết quả | Cần thống kê riêng; không tự coi là hit |
| **REVALIDATED** | Có cơ chế xác thực lại với origin và entry còn dùng được sau revalidation | Chỉ dùng nhãn này nếu implementation hỗ trợ và đã đo thật |

**Quy ước khuyến nghị:** Một lần lookup được ghi **đúng một outcome chính** (`hit` hoặc `miss`). `bypass` và `error` là loại riêng. Những lý do như `expired` hoặc `no-store` có thể là tag/phân loại phụ, nhưng không làm một request bị đếm hai lần trong mẫu số.

### Ví dụ bảng số liệu 5 phút

Giả sử tập request đến những route đã bật cache trong 5 phút như sau:

| Outcome | Số request |
|---|---:|
| HIT | 800 |
| MISS | 400 |
| BYPASS theo policy | 250 |
| INELIGIBLE không thực hiện lookup | 50 |
| **Tổng request đi vào tập route** | **1.500** |

Ở đây có **1.200 lookup đủ điều kiện**. Tỷ lệ cache hit trong tập lookup là:

\[
\text{Hit ratio}_{eligible} =
\frac{H}{H+M} = \frac{800}{800+400}
= 66{,}67\%
\]

Còn tỷ lệ request được đáp ứng bằng hit trong **toàn bộ traffic của tập route** là:

\[
\text{Hit coverage}_{traffic} =
\frac{H}{N_{requests}} = \frac{800}{1500}
= 53{,}33\%
\]

Cả hai số đều đúng **nhưng trả lời hai câu hỏi khác nhau**. Một dashboard chỉ hiển thị “hit ratio 66,67%” mà không nêu mẫu số dễ bị hiểu nhầm rằng Gateway đã giảm 66,67% **toàn bộ** traffic downstream.

### Những tỷ lệ nên báo cáo riêng

- **Eligible hit ratio:** khả năng tái sử dụng entry trong tập request đủ điều kiện lookup.
- **Traffic hit coverage:** phần trăm tổng requests được cache phục vụ.
- **Bypass ratio:** tỷ lệ traffic không sử dụng cache và nguyên nhân.
- **Cache error ratio:** số lần lookup/store lỗi trên tập hoạt động phù hợp.
- **Origin offload:** số lượt backend thực tế **không phải nhận** nhờ cache, cần được xác minh bằng downstream request counters.

**Origin offload không mặc định bằng hit coverage** nếu hệ thống có retries, conditional requests, CDN bên ngoài, circuit breaker, fallback hoặc nhiều lần outbound call cho một request client.

## 4. Đừng nhầm Gateway requests metrics với cache hit metrics

Spring Cloud Gateway có thể phát hành **Gateway request metrics** qua Micrometer/Actuator (ví dụ meter gắn với `spring.cloud.gateway.requests` ở một số phiên bản). Những metrics đó hữu ích để quan sát **route, HTTP status, latency và tổng requests**.

Nhưng chúng **không tự chứng minh** response là cache hit.

~~~text
GET /api/public/catalog/42 -> HTTP 200, latency 5ms
~~~

Request 5ms có thể là:
- Cache hit ở Gateway.
- Backend rất nhanh.
- CDN/ingress trả từ cache trước Gateway.
- Một response fallback nhanh.
- Một handler không gọi backend.

Tương tự, HTTP `200` không phải tín hiệu hit; response `Cache-Control: max-age=30` không chứng minh entry hiện đã tồn tại.

### Ba nguồn bằng chứng nên đối chiếu

| Nguồn | Chứng minh được | Không tự chứng minh được |
|---|---|---|
| **Metric hit/miss của cache implementation** | Lookup có dùng entry hay không | Backend thật sự nhận bao nhiêu attempts nếu còn tầng khác |
| **Gateway request metric** | Traffic, latency, route/status | Request có hit hay miss |
| **Backend request counter / access logs** | Bao nhiêu request thực sự đến service | Vì sao một request không đến backend |
| **HTTP headers/response body ở client** | Kết quả client quan sát | Entry lấy từ đâu, nếu không có instrumentation |
| **Distributed tracing** | Đường đi qua Gateway/downstream khi span được tạo | Mọi hit nếu instrumentation không đánh dấu quyết định cache |

**Không kết luận cache hoạt động chỉ vì thời gian phản hồi giảm.** Kết hợp một metric phản ánh **quyết định lookup** với số lượt gọi downstream và một phép kiểm tra tính đúng đắn.

## 5. Đo hit/miss thế nào khi không có metric chuẩn sẵn có?

Không nên giả định mọi bản `LocalResponseCache` tự cung cấp meter tên `cache.hit` hoặc `gateway.cache.hits`. Tên và khả năng xuất metric phụ thuộc Gateway, cache implementation, Spring Boot Actuator, Micrometer binder và cấu hình bật thu thập thống kê.

Có ba cách tiếp cận:

1. **Dùng thống kê cache thực sự được expose** từ Caffeine/implementation khi có hỗ trợ, ví dụ hitCount, missCount, evictionCount. Cần kiểm tra **đã bật recordStats chưa**, cache nào được binder nhận diện và metric name/tags ở runtime.
2. **Instrumentation có kiểm soát trên đường lookup** trong một cache filter/cache service do ứng dụng quản lý: mỗi quyết định phát một event `hit`, `miss`, `bypass` hoặc `error`. Đây là cách chủ động nhất nếu không có metric chính thức.
3. **Đối chiếu thực nghiệm**: backend counter + client request count + controlled test cases để chứng minh cache làm giảm outbound calls, khi không thể thay thư viện.

Không nên thêm một `GlobalFilter` rồi dự đoán hit chỉ bằng độ trễ hoặc response header `Cache-Control`. Filter ấy **không tự truy cập quyết định hit/miss nội bộ** của một factory khác. Nếu muốn metric chính xác, cần một hook/cách instrument tại **đúng nơi thực hiện cache lookup**, hoặc một component cache do bạn kiểm soát.

### Quy ước metric tự xây (không phải tên built-in)

Ví dụ định nghĩa một counter **do ứng dụng chủ động instrument**:

~~~text
gateway_response_cache_lookups_total{
  route_id="public-catalog",
  outcome="hit"
} 800

gateway_response_cache_lookups_total{
  route_id="public-catalog",
  outcome="miss"
} 400

gateway_response_cache_bypass_total{
  route_id="public-catalog",
  reason="policy"
} 250
~~~

Đây là **tên meter đề xuất**, không phải khẳng định Gateway có sẵn chúng. Mỗi metric phải đi kèm mô tả đơn vị và điều kiện tăng bộ đếm. Nếu có error, cần quy định error nằm ngoài tổng hit/miss hay được phân loại riêng trong cùng metric.

### Không dùng cache key hoặc user ID làm metric tag

Chỉ dùng những tags có cardinality được kiểm soát, chẳng hạn:

~~~text
route_id = public-catalog
outcome  = hit | miss | bypass | error
reason   = expired | no-store | unauthorized | method | other
~~~

**Không dùng** `url` đầy đủ với query cá nhân, session ID, access token, API key, tenant ID, email hoặc cache key thô làm tag. Cardinality cao gây quá tải Prometheus/metrics backend và có nguy cơ rò dữ liệu.

Nếu cần phân tích theo tenant, xem xét cơ chế analytics phân quyền riêng, tổng hợp theo nhóm hữu hạn và tuân thủ chính sách dữ liệu thay vì bắn hàng triệu series.

## 6. Tính hit ratio trong Prometheus/Grafana

**Chỉ áp dụng các truy vấn dưới đây nếu bạn đã instrument và expose metric tùy chỉnh** `gateway_response_cache_lookups_total` với tag `outcome` chính xác như phần 5. Không dán truy vấn rồi kỳ vọng nó trả dữ liệu trên một Gateway chưa có counter này.

### Tỷ lệ hit trên mọi route trong cửa sổ 5 phút

~~~promql
sum(rate(gateway_response_cache_lookups_total{outcome="hit"}[5m]))
/
sum(rate(gateway_response_cache_lookups_total{outcome=~"hit|miss"}[5m]))
~~~

Nhân 100 khi muốn biểu diễn theo **phần trăm** thay vì số từ 0 đến 1.

### Tỷ lệ hit theo route ID

~~~promql
sum by (route_id) (
  rate(gateway_response_cache_lookups_total{outcome="hit"}[5m])
)
/
sum by (route_id) (
  rate(gateway_response_cache_lookups_total{outcome=~"hit|miss"}[5m])
)
~~~

**Khi không có lookup trong cửa sổ, mẫu số bằng 0.** Dashboard nên hiển thị “N/A / no traffic” thay vì coi là 0% hit hoặc 100% hit. Tương tự, counter mới reset/restart cần được xử lý theo semantics của `rate`/`increase`, không trừ trực tiếp hai giá trị counter.

### Đo trên cửa sổ dài hơn

~~~promql
sum(increase(gateway_response_cache_lookups_total{outcome="hit"}[1h]))
/
sum(increase(gateway_response_cache_lookups_total{outcome=~"hit|miss"}[1h]))
~~~

Cửa sổ **5 phút** phù hợp phát hiện biến động nhanh nhưng nhiễu nếu ít traffic; **1 giờ/24 giờ** giúp thấy xu hướng ổn định. Nên hiển thị **số lượng hit/miss tuyệt đối cùng tỷ lệ**, vì 90% của 10 requests không tương đương 90% của 1 triệu requests.

### Nên theo dõi thêm gì?

| Metric | Lợi ích |
|---|---|
| Hit/miss/bypass counts & rates | Biết cache có phục vụ đúng lượng traffic kỳ vọng |
| Backend requests per second | Xác nhận offload thật |
| Gateway latency P50/P95/P99 theo route | Đo cải thiện trải nghiệm, không chỉ trung bình |
| Cache entry count/weight/evictions | Phát hiện cache quá nhỏ hoặc key churn |
| Miss load time | Chi phí khi fetch backend sau miss |
| Memory/GC/heap và direct memory | Kiểm tra cache có gây áp lực tài nguyên |
| Tỷ lệ lỗi 4xx/5xx và stale correctness alarms | Không đánh đổi an toàn để lấy hit cao |
| Retry attempts/circuit breaker fallback | Phân biệt offload do cache với đường xử lý resilience |

Không mặc định mọi metric đều được xuất sẵn; khả năng thu thập phụ thuộc thư viện và instrument của dự án.

## 7. Đọc cache key và hiểu thế nào là một response “giống nhau”

Hai HTTP requests chỉ có thể dùng chung một cached representation khi **những yếu tố ảnh hưởng đến phản hồi được nhận diện đầy đủ**.

Ví dụ:

~~~http
GET /api/public/catalog/items?sort=price&lang=vi HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: vi
~~~

So với:

~~~http
GET /api/public/catalog/items?sort=price&lang=en HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: en
~~~

Nếu nội dung được dịch theo `lang`, hai requests cần **biến thể cache khác nhau**. Không được gộp chỉ vì path giống nhau.

### Những biến cần kiểm chứng trong key

| Biến | Ví dụ khác nhau | Rủi ro nếu cache không phân biệt |
|---|---|---|
| Path | `/items/42` vs `/items/43` | Trả sai tài nguyên |
| Query | `?page=1` vs `?page=2` | Trả sai trang |
| Sort/filter | `?sort=price` vs `?sort=name` | Trả sai sắp xếp |
| Locale | `Accept-Language: vi` vs `en` | Trả sai ngôn ngữ |
| Media type | `Accept: application/json` vs loại khác | Trả sai representation |
| Encoding | `Accept-Encoding: gzip` vs `identity` | Gửi body/Content-Encoding không tương thích |
| Tenant | Tenant A vs B | **Rò dữ liệu chéo tenant** |
| User/role | User X vs Y | **Rò dữ liệu cá nhân hoặc quyền hạn** |
| Feature flag | App version/experiment | Dùng sai cấu hình nội dung |
| Route rewrite | URI trước/sau `RewritePath` | Đụng cache key hoặc phân mảnh entry |

**Không tự giả định `LocalResponseCache` đưa tất cả các yếu tố trên vào cache key** hoặc tôn trọng mọi tổ hợp `Vary` theo cách hệ thống mong muốn. Hãy kiểm tra implementation theo phiên bản và thiết kế **negative tests** cho từng biến có thể làm response khác.

### Cache key chuẩn hóa không đúng cũng có thể gây lỗi

Hai query strings:

~~~text
?tag=red&tag=blue
?tag=blue&tag=red
~~~

có thể **khác ngữ nghĩa** nếu backend quan tâm thứ tự giá trị lặp. Ngược lại:

~~~text
?sort=price&page=1
?page=1&sort=price
~~~

có thể cùng ý nghĩa với một API cụ thể nhưng được lưu thành hai key khác nhau nếu không chuẩn hóa. Không tự sắp xếp/bỏ giá trị query trùng tên nếu chưa hiểu hợp đồng backend.

**Tính đúng đắn quan trọng hơn tiết kiệm vài entry.** Nếu không chắc hai requests tương đương, giữ chúng tách biệt hoặc không cache.

## 8. Cache-Control, TTL và revalidation: đúng nghĩa HTTP

Các response headers liên quan:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=30
ETag: "catalog-42-v8"
Vary: Accept-Language

{"id":42,"title":"Sản phẩm"}
~~~

Ý nghĩa khái quát:

- `Cache-Control: public`: representation có thể được lưu ở shared cache nếu không có ràng buộc khác.
- `max-age=30`: chỉ thị freshness trong phạm vi **30 giây** theo semantics HTTP; không bảo đảm cache thực tế sẽ lưu đúng 30 giây.
- `ETag`: validator để kiểm chứng representation có thay đổi hay không khi hỗ trợ conditional request.
- `Vary: Accept-Language`: selection của response phụ thuộc request header ấy, nên cache tuân thủ HTTP phải phân biệt biến thể phù hợp.
- `Age` (nếu cache/proxy phát hành) mô tả độ tuổi ước lượng của representation theo HTTP; **không tự giả định mọi LocalResponseCache hit đều có Age**.

### `no-store` khác `no-cache` và `private`

| Chỉ thị | Ý nghĩa quan trọng |
|---|---|
| `no-store` | Không lưu representation theo yêu cầu caching thông thường |
| `private` | Không cho **shared cache** lưu response; private browser cache có thể có semantics khác |
| `no-cache` | Không được dùng lại mà không revalidate thành công, **không đồng nghĩa tuyệt đối cấm lưu** |
| `max-age=N` | Chỉ thị thời gian freshness |
| `s-maxage=N` | Chỉ thị dành cho shared cache khi cache tuân theo semantics tương ứng |
| `must-revalidate` | Hết freshness thì phải revalidate trước khi dùng lại theo các điều kiện HTTP |
| `Vary` | Các request headers ảnh hưởng lựa chọn representation |

Một implementation cụ thể có thể **không hỗ trợ mọi chỉ thị HTTP cache**. Do đó, bài kiểm thử phải xác minh **hành vi đang chạy**, không suy rằng chỉ cần gửi `ETag` hay `s-maxage` thì filter chắc chắn tự revalidate.

### Conditional GET và 304

Client có thể gửi:

~~~http
GET /api/public/catalog/42 HTTP/1.1
If-None-Match: "catalog-42-v8"
~~~

Nếu validator còn phù hợp, một origin HTTP có thể trả `304 Not Modified` không có body để client hoặc cache cập nhật trạng thái. Nhưng **không tự xem 304 là một cache hit của LocalResponseCache**. `304` có semantics riêng và cần được xử lý đúng cùng headers đi kèm. Một số bộ lọc chỉ cache các response status cụ thể; nếu `304` không thuộc nhóm hỗ trợ, việc nó được trả thế nào là vấn đề integration riêng.

**Bài kiểm thử bắt buộc**: gửi request có và không có `If-None-Match`, kiểm tra status/body/ETag/Cache-Control ở Gateway, so sánh với gọi trực tiếp origin. Không trả nhầm body từ representation khác hoặc trả `304` cho client chưa có bản thể tương ứng.

## 9. Đánh đổi TTL và tính mới của dữ liệu

TTL dài thường làm tăng hit ratio, nhưng cũng tăng thời gian mà người dùng có thể nhận dữ liệu **không còn mới**.

Một API hiển thị tên danh mục công khai có thể chấp nhận cập nhật trễ hàng chục giây. Một API thể hiện **số dư, tồn kho giữ chỗ hoặc giá giao dịch thời gian thực** có thể không phù hợp để shared-cache, dù request dùng GET.

### Mô hình kinh doanh để chọn TTL

| Loại dữ liệu | Yêu cầu freshness | Chiến lược sơ bộ |
|---|---|---|
| Danh mục công khai ít đổi | Cho phép trễ ngắn | TTL có giới hạn, kiểm thử đúng key |
| Nội dung bài viết/public info | Cho phép trễ phút nếu product chấp nhận | TTL + purge/invalidation khi xuất bản |
| Giá hiển thị thay đổi theo chiến dịch | Phụ thuộc nghiệp vụ | TTL rất ngắn hoặc versioned key, xác nhận giá lúc đặt hàng |
| Tồn kho/đặt chỗ | Thường cần mới | Hạn chế hoặc tránh shared response cache |
| `/api/me`, hóa đơn, hồ sơ user | Cá nhân hóa, nhạy cảm | Không dùng shared cache trừ khi isolation được chứng minh |
| Authentication/Authorization responses | Có thể thay đổi ngay khi thu hồi quyền | Tránh shared caching; cần policy riêng |
| API lỗi/fallback | Hết sức phụ thuộc status và contract | Không tự cache degraded response chỉ để tăng hit |

Với TTL cố định `30s`, câu hỏi không chỉ là “tỷ lệ hit tăng bao nhiêu?” mà còn là **“hệ thống có chấp nhận hiển thị thông tin cũ trong khoảng đó không?”**.

### Kiểm thử hết hạn và cập nhật

1. Gọi request lần đầu, xác nhận response đúng và (nếu đủ điều kiện) entry được lưu.
2. Gọi lại **trong TTL**: kỳ vọng hit và dữ liệu có thể giống bản đã lưu.
3. Thay đổi dữ liệu ở backend bằng quy trình lab có kiểm soát.
4. Gọi lại **trước khi TTL hết**: xác định hợp đồng có cho phép dữ liệu cũ hay không.
5. Gọi lại **sau TTL**: kỳ vọng miss/fetch và nhận dữ liệu mới, nếu backend và các tầng cache khác không giữ bản cũ.
6. Lặp với nhiều Gateway instances, xem một node có thể trả bản mới trong khi node khác vẫn giữ entry cũ không.

Không coi “TTL 30 giây” là đồng hồ chính xác tuyệt đối theo thời gian người dùng; lập lịch, cache expiration strategy, clock, cache-control freshness và các proxy khác có thể ảnh hưởng.

## 10. Kiểm chứng bảo mật: auth, cookie, tenant và route filters

**Rủi ro nghiêm trọng nhất của shared response cache là phục vụ nội dung của một người/tenant cho người khác.**

Giả sử API `GET /api/me` trả:

~~~json
{"userId":"alice","email":"alice@example.test","balance":120}
~~~

Nếu Gateway cache response chỉ theo URI và dùng lại cho request có cookie hoặc token của Bob, đây là lỗi **cross-user data exposure**. Một hit ratio rất cao trong tình huống này là **tín hiệu nguy hiểm**, không phải thành tích.

### Quy tắc an toàn mặc định

- Đừng cache response có nội dung riêng theo JWT, cookie, session hoặc tenant ở shared Gateway cache khi chưa xác nhận mô hình partitioning đầy đủ.
- Backend nên đánh dấu response nhạy cảm bằng `Cache-Control: private, no-store` khi phù hợp với hợp đồng.
- Đừng dùng `Authorization` hoặc cookie **giá trị thô** làm cache key/metric label/log.
- Đừng coi HTTP `200` sau auth là “public”; người đã xác thực có thể thấy dữ liệu khác nhau.
- Kiểm tra **thứ tự Spring Security và GatewayFilter**: một cache hit không được trở thành cách vượt phân quyền.
- Nếu dùng service discovery tạo route tự động, tránh vô tình áp cache toàn cục lên API internal/tenant-sensitive.

### Ma trận kiểm thử cách ly danh tính

| Request | Điều cần bảo đảm |
|---|---|
| User A, `GET /api/me` | Chỉ thấy dữ liệu A |
| User B, cùng URL | Chỉ thấy dữ liệu B, không reuse entry của A |
| User A đổi vai trò/quyền | Response không tiếp tục tiết lộ dữ liệu đã bị thu hồi quyền |
| Tenant A và Tenant B, cùng path/query | Dữ liệu không chảy giữa hai tenant |
| Token/cookie thiếu hoặc hết hạn | Security trả 401/403 theo policy, không dùng cache để bypass |
| Header `X-Tenant-Id` do client tự điền | Không được tin để tạo key/phân quyền nếu chưa được xác thực |
| Route fallback trả response tổng quát | Không biến response nhạy cảm hay lỗi thành entry dùng chung sai |

**Nếu không thể chứng minh isolation**, lựa chọn đúng thường là **tắt Gateway response caching cho route đó**, thay vì thêm một key tùy biến nhưng chưa kiểm thử toàn bộ trust boundary.

## 11. Vary, nén và Range: kiểm thử đúng cả body lẫn headers

Ngay cả API public có thể tạo các bản thể khác nhau theo request headers. Ví dụ:

~~~http
GET /api/public/articles/42 HTTP/1.1
Accept-Language: vi
Accept-Encoding: gzip
~~~

Backend có thể trả:

~~~http
HTTP/1.1 200 OK
Vary: Accept-Language, Accept-Encoding
Content-Encoding: gzip
Content-Type: text/html; charset=utf-8
~~~

Một request tiếng Anh với `Accept-Encoding: identity` **không được nhận nhầm body gzip của bản tiếng Việt**.

### Các trường cần so sánh cùng body

| Trường | Lỗi nếu không nhất quán |
|---|---|
| `Content-Type` / charset | Client parse sai representation |
| `Content-Encoding` | Browser giải nén sai, body không đọc được |
| `Content-Length` / transfer framing | Cắt body hoặc đếm kích thước sai |
| `ETag` / `Last-Modified` | Validator không tương ứng body |
| `Vary` | Trả sai biến thể header |
| `Cache-Control` / freshness | Client cache quá lâu hoặc hiểu nhầm thời gian còn lại |
| `Content-Range` và status `206` | Trả sai byte range, hỏng file/stream |
| `Set-Cookie` | Có thể phát lại cookie/session của user khác nếu lỡ cache |
| Security/CORS headers | Vùng tin cậy và chính sách browser không nhất quán |

**Đặc biệt với `206 Partial Content`:** nếu implementation có thể cache `206`, phải thử requests có `Range` khác nhau. Không cho hai khoảng byte khác nhau vô tình dùng chung entry. Header `Content-Range` và nội dung byte phải tương ứng chính xác với yêu cầu. Với download lớn hoặc streaming, cân nhắc tắt Gateway local cache nếu không thể chứng minh cache key và range handling đúng.

### CORS và Origin

Một response có header `Access-Control-Allow-Origin` phụ thuộc `Origin` hoặc có `Vary: Origin` cần xử lý đúng biến thể. Nếu cache body public nhưng gắn lại CORS header của Origin A vào response Origin B, browser có thể chặn hoặc, tệ hơn, policy có thể trở nên sai.

Không tự cho rằng `DedupeResponseHeader` hay `RemoveResponseHeader` sửa được lỗi phân vùng cache. Filter response headers có thể sửa header cuối nhưng **không bảo đảm body vốn được chọn đúng**.

## 12. Những yếu tố làm hit ratio tăng giả hoặc giảm giả

Tỷ lệ hit có thể thay đổi do môi trường mà không phản ánh chất lượng chính sách.

| Hiện tượng | Vì sao xảy ra | Cách đọc metric |
|---|---|---|
| Traffic tăng vào một URL “hot” | Nhiều lookup cùng key | Hit ratio cao dù phần lớn URLs khác không dùng cache |
| Cache vừa restart | Bộ nhớ rỗng (cold start) | Miss tăng tạm thời |
| Hệ thống scale từ 2 lên 10 Gateway instances | Mỗi instance có cache riêng | Cùng dữ liệu phải warm nhiều nơi |
| Sticky routing giữ client ở một node | Warm entry được tái sử dụng tốt hơn | Hit ratio phụ thuộc cân bằng tải |
| CDN phục vụ request trước Gateway | Gateway không nhìn thấy nhiều request hot | Gateway hit ratio có thể giảm nhưng tổng offload tăng |
| TTL tăng | Entry sống lâu | Hit ratio tăng nhưng nguy cơ stale data |
| Key quá rộng, bỏ query/header/tenant | Nhiều request “nhìn như” cùng một key | Hit ratio tăng **cùng với lỗi correctness** |
| Key quá chi tiết (gắn timestamp/random ID) | Entry khó được tái sử dụng | Hit ratio thấp vì fragmentation |
| Backend lỗi, fallback nhanh | Thời gian phản hồi có thể thấp hơn | Không chứng minh cache hit |
| Retry tăng | Một miss có thể gọi backend nhiều lần | Offload kém hơn hit ratio ngụ ý |
| Cache eviction do thiếu memory | Entry bị đẩy sớm | Miss tăng, cần xem eviction count |

**Không tối ưu riêng chỉ số hit ratio.** Hãy đặt guardrail: **không rò dữ liệu**, không sai status/headers, stale-data budget hợp lệ, giới hạn memory, P95/P99 latency và tải downstream.

### Local cache và nhiều instances

Một cache cục bộ trên Gateway A **không tự đồng bộ entry** với Gateway B. Cùng URL có thể:

- Hit tại A vì A đã warm.
- Miss tại B vì B chưa từng thấy request.
- Trả bản cũ tại A và bản mới tại B nếu origin vừa thay đổi.

Vì vậy, **hit ratio tổng phải tổng hợp từ tất cả các instance**, đồng thời cần biểu đồ per-instance để phát hiện uneven load. Nếu yêu cầu nhất quán nghiêm ngặt, cân nhắc quản lý invalidation/versioning hoặc kiến trúc cache khác, không coi local cache như shared distributed state.

## 13. Kiểm chứng bằng backend counter và cURL

### Môi trường lab

Giả sử:

- Gateway: `http://localhost:8080`.
- Backend public catalog: `http://localhost:9090`.
- Route `public-catalog` của phần 2 với `LocalResponseCache` nếu runtime hỗ trợ.
- Backend phục vụ `GET /catalog/items/42`, mỗi lần **thật sự được gọi** sẽ tăng một bộ đếm và trả version nội dung.
- Không có CDN, reverse proxy cache hoặc client SDK retry trong lab để tránh nhiễu.

Một backend WebFlux demo:

~~~java
package example.catalog.lab;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CatalogEchoController {

    private final AtomicInteger originCalls = new AtomicInteger();

    @GetMapping("/catalog/items/{id}")
    public Mono<ResponseEntity<Map<String, Object>>> item(
            @PathVariable String id) {

        int call = originCalls.incrementAndGet();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("itemId", id);
        body.put("originCall", call);
        body.put("name", "Demo product");

        return Mono.just(ResponseEntity.ok()
            .cacheControl(CacheControl.maxAge(
                java.time.Duration.ofSeconds(30)).cachePublic())
            .body(body));
    }
}
~~~

Đây là code dành cho **backend lab**, không phải code để chèn vào tiến trình Gateway; nó không có auth và không phù hợp xuất bản public. Counter ở đây **thuộc một process và tất cả request**, chỉ để thử thủ công trong môi trường một backend instance. Trong production, dùng metrics đúng đơn vị và không đưa số call vào response khách hàng thật.

### Bước 1 — Gọi trực tiếp backend

~~~bash
curl -i "http://localhost:9090/catalog/items/42"
~~~

Kiểm tra response có `Cache-Control` phù hợp, body chứa `originCall` và backend hoạt động. Đây là **mốc đối chứng**: endpoint backend phải chạy đúng trước khi thử cache.

### Bước 2 — Lần gọi đầu qua Gateway

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

Với cache mới/chưa warm và route match, đây thường là **miss**. Trong lab không có traffic khác, `originCall` tăng vì backend được gọi.

### Bước 3 — Gọi lại ngay trong TTL

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

Nếu route cache hoạt động và response đủ điều kiện, backend counter **không nên tăng thêm** vì hai request tiếp theo được phục vụ từ cache. Body có thể giữ `originCall` của lượt miss; đó là tín hiệu thuận tiện cho lab, nhưng **metric lookup/cache instrumentation vẫn là nguồn xác nhận tốt hơn**.

Hãy kiểm tra cùng lúc:

| Quan sát | Dự kiến khi cache thật sự HIT |
|---|---|
| Counter từ backend | Không tăng đối với lượt hit |
| Cache hit metric (nếu có) | Tăng đúng lượt lookup hit |
| Client body | Bản thể đúng với URL được yêu cầu |
| HTTP status | Theo contract của response lưu |
| `Cache-Control` | Không cho phép freshness vượt chính sách đã định |
| Latency | Có thể giảm, nhưng không phải điều kiện chứng minh |
| Security/headers | Không có nội dung nhạy cảm bị reuse sai |

### Bước 4 — Thử query và path khác

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/43"
curl -i "http://localhost:8080/api/public/catalog/items/42?lang=vi"
curl -i "http://localhost:8080/api/public/catalog/items/42?lang=en"
~~~

Backend demo ở trên chưa dùng `lang` để tạo nội dung khác; vì vậy **chưa thể chứng minh key khác nhau theo query** chỉ từ body hiện tại. Để kiểm thử nghiêm ngặt, sửa **backend lab theo bài kiểm thử** để trả dữ liệu thực sự phụ thuộc query, hoặc dùng mock backend với response khác biệt rõ. Sau đó xác nhận không có cross-key collision.

### Bước 5 — Chờ TTL và quan sát refresh

Đợi qua TTL đã cấu hình, rồi gọi:

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

Nếu entry đã hết hạn và không có cache layer khác, backend counter sẽ tăng và body có `originCall` mới. Nếu không tăng, kiểm tra TTL hiệu lực, thời điểm warm, các proxy khác và cấu hình route/cache ở instance đang phục vụ.

### Bước 6 — Request yêu cầu no-store

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42" \
  -H "Cache-Control: no-store"
~~~

Theo các phiên bản `LocalResponseCache` có ghi nhận xử lý no-store ở request, đây là trường hợp cần **bypass hoặc không dùng entry** theo hợp đồng filter. Xác minh backend có được gọi không và các response có lưu lại hay không. Đừng mặc định thêm `Cache-Control: no-cache` sẽ có cùng semantics với `no-store`.

### Bước 7 — Thử response nhạy cảm và biến thể

Dùng **mock backend riêng** trả `Cache-Control: private, no-store` cho endpoint giả lập `/api/me`; nếu route test có cấu hình cache, phải xác minh **không có entry dùng chung**. Tiếp theo thử response thay đổi theo `Accept-Language`, `Origin`, `Range` và các request headers theo hợp đồng API. Không dùng dữ liệu hay access token thực trong lab.

## 14. Ma trận kiểm thử correctness theo loại dữ liệu

Một bộ test có ý nghĩa phải có cả **positive tests** (đúng là hit) và **negative tests** (không được hit sai).

| Case | Điều kiện | Kỳ vọng |
|---|---|---|
| Cùng GET public, cùng representation, trong TTL | Endpoint cacheable | Lần đầu miss, lần sau hit |
| Cùng URL public sau TTL | Entry hết hạn | Fetch lại hoặc xử lý freshness đúng policy |
| Hai resource IDs khác nhau | `/42` và `/43` | Không trả dữ liệu chéo ID |
| Query thay đổi kết quả | `lang=vi` và `lang=en` | Không dùng nhầm representation |
| Request có `no-store` | Cache policy loại trừ | Không sử dụng/lưu trái chính sách |
| Response có `private, no-store` | Dữ liệu cá nhân | Không shared-cache |
| User A/B cùng URL riêng tư | Authentication khác | Không bao giờ lộ A cho B |
| Tenant A/B | Tenant khác | Isolation đúng |
| `Vary: Accept-Language` | Vi/En | Đúng body ngôn ngữ |
| `Vary: Accept-Encoding` | gzip/identity | Body và Content-Encoding đồng bộ |
| `Range` request | Đoạn byte khác | `206`/`Content-Range` chính xác hoặc không cache |
| `If-None-Match` | Validator còn/không còn đúng | Status 200/304 và body/headers phù hợp |
| POST cập nhật rồi GET | Dữ liệu đã đổi | Freshness/invalidation theo hợp đồng |
| Retry một lần miss | Backend bị lỗi tạm | Không ghi entry sai/fallback ngoài ý định |
| CircuitBreaker fallback | Backend outage | Không cache response degraded sai policy |
| Nhiều Gateway nodes | Entry warm khác nhau | Correctness ổn định dù hit ratio per-node khác |
| Security 401/403 | Token sai/thiếu quyền | Không bypass vì cache |
| Streaming/response bị commit | Body dài/SSE | Không giả định có thể lưu/replay an toàn |

Nếu một test cho thấy cache key không phân biệt yếu tố mà response thực sự phụ thuộc, **tắt cache trên route đó** cho đến khi có giải pháp đúng. Đừng chỉ sửa dashboard để số hit trông tốt hơn.

## 15. Tương tác với Retry, CircuitBreaker, RateLimiter và service discovery

### Rate limiter

Nếu `RequestRateLimiter` chạy trước phần trả response từ cache, cả hit và miss có thể bị tính vào ngân sách request của client. Nếu chính sách muốn **hit rẻ hơn miss**, cần thiết kế theo năng lực filter/metrics thực tế, không mặc định một bộ lọc có thể biết quyết định cache của bộ lọc khác trước khi lookup.

`KeyResolver` theo user/tenant/IP không phải cache key. Một user có thể bị rate limit riêng trong khi tất cả user dùng một **public cached representation**; ngược lại, route riêng tư không trở nên an toàn để cache chỉ vì rate limiter phân biệt tenant.

### Retry và CircuitBreaker

Một cache miss có thể đi qua Retry và tạo **nhiều outbound attempts**; hit thì có thể bỏ qua chuỗi này nếu filter order cho phép. Vì vậy:

~~~text
1 cache lookup MISS
  -> Backend attempt #1 (503)
  -> Retry backoff
  -> Backend attempt #2 (200)
  -> Có thể lưu response cuối nếu thật sự đủ điều kiện
~~~

Ở mô hình khác, CircuitBreaker có thể chuyển sang fallback. Nếu fallback trả `200` với dữ liệu degraded, một cache quá rộng có thể **lưu nhầm dữ liệu dự phòng như representation bình thường**. Cần kiểm tra response status, headers, filter order và chính sách không cache fallback; không dựa vào mã 200 để kết luận an toàn.

### Service discovery và nhiều backend instances

URI `lb://catalog-service` chọn một instance khi cache miss. Cache hit cục bộ có thể **không gọi LoadBalancer và backend** theo pipeline. Nhưng nếu các backend instances trả dữ liệu không nhất quán, một cache miss đến instance A và miss đến instance B có thể tạo entry khác nhau. Cần giải quyết tính nhất quán của dữ liệu nguồn trước khi đánh giá hit ratio.

### TLS và proxy/CDN

Cache không thay thế TLS. HTTPS client → Gateway và Gateway → backend bảo vệ những dữ liệu vẫn phải truyền. Nếu có CDN/ingress cache đứng trước, cần phân biệt **CDN hit**, **Gateway hit** và **backend fetch**, mỗi tầng có metrics/invalidation riêng. Header `X-Cache` do một proxy đưa ra **không mặc định mô tả LocalResponseCache của Gateway**.

## 16. Dashboard và quy trình vận hành

Một dashboard hữu ích cho mỗi route cacheable nên trình bày **đủ hiệu quả, đúng đắn và sức khỏe hạ tầng**:

| Nhóm | Biểu đồ / chỉ số |
|---|---|
| Traffic | Requests/s, cache-eligible lookup/s, bypass/s |
| Hiệu quả | Hit ratio 5m/1h, hit coverage, backend requests/s |
| Latency | P50/P95/P99 Gateway và downstream; tách hit/miss nếu có instrumentation thật |
| Bộ nhớ | Cache weight/entry count/evictions; heap/GC |
| Freshness | TTL effective, expired misses, age khi có metric đáng tin |
| Safety | Cross-user/tenant invariant failures, Vary/Range test results |
| Resilience | Retry attempts, breaker opens, fallback rate, 5xx |
| Môi trường | Per-instance cache stats, deployments/restarts, cache warm-up |

### Các cảnh báo đáng ưu tiên

- **P95 latency tăng** kèm miss rate tăng và backend saturation.
- **Evictions tăng mạnh** dù lưu lượng tương đương: có thể cache quá nhỏ hoặc key fragmentation.
- **Hit ratio giảm sau deploy**: có thể cold cache; kiểm tra cùng restart/autoscaling events.
- **Gateway trả dữ liệu cũ vượt TTL cho phép**: ưu tiên cảnh báo correctness hơn hiệu suất.
- **Cross-user/tenant isolation test fail**: coi là sự cố bảo mật; tắt cache route liên quan và điều tra.
- **Backend call rate không giảm** dù hit metric cao: có thể metrics đếm sai, nested retries hoặc những request khác vẫn đi origin.

Đừng dùng “hit ratio phải luôn trên 90%” như một SLO chung cho mọi API. Với một tập URL ít truy cập nhưng biến thể rất nhiều, hit thấp là điều tự nhiên; **giữ kết quả đúng** quan trọng hơn cố đẩy hit lên.

### Quy trình rollout an toàn

1. Chọn **một route GET public** có response ổn định và TTL được business chấp nhận.
2. Chạy **correctness tests** cả hit/miss, TTL, query, Vary, status và security.
3. Bật cache ở staging, so sánh Gateway metrics và backend request counters.
4. Thử restart/scale nhiều Gateway nodes và đo memory/evictions.
5. Rollout hạn chế, theo dõi hit ratio **cùng** lỗi dữ liệu/latency/offload.
6. Có kế hoạch **disable cache nhanh** nếu phát hiện leak, stale vượt hạn hoặc mismatch HTTP headers.
7. Sau khi ổn định mới cân nhắc route khác; mỗi route cần hợp đồng data freshness/authorization riêng.

## 17. Troubleshooting: tỷ lệ hit không khớp kỳ vọng

| Triệu chứng | Nguyên nhân đáng kiểm tra | Bước xác minh |
|---|---|---|
| Hit ratio bằng 0 dù gọi lại cùng URL | Filter chưa được nạp, entry không đủ điều kiện, `no-store`, TTL quá ngắn | Kiểm tra route runtime và backend call count |
| Hit ratio cao nhưng backend vẫn bị gọi nhiều | Metric sai phạm vi, nested retries, CDN/traffic khác | Đếm outbound attempts theo route và instance |
| Chỉ một Gateway node hit nhiều | Cache cục bộ chưa warm đều, load balancer phân bố lệch | Xem per-instance stats và rollout |
| Hit ratio giảm đột ngột sau deploy | Restart xóa local cache | Đối chiếu thời gian khởi động và warming |
| Dữ liệu cũ quá lâu | TTL hoặc HTTP Cache-Control/proxy không như mong muốn | Kiểm tra freshness qua các tầng, backend version |
| User B thấy dữ liệu User A | Sai phân vùng cache hoặc cache nhầm API private | **Tắt cache route, điều tra bảo mật ngay** |
| Query khác nhưng body giống nhau bất thường | Key bỏ query hoặc backend vốn không phân biệt query | Dùng mock backend trả hai phiên bản khác nhau |
| Language/encoding bị lẫn | `Vary`/cache key không phù hợp | Test `Accept-Language`, `Accept-Encoding`, headers/body |
| Range 206 sai nội dung | Cache không phân biệt `Range` hoặc metadata sai | So sánh bytes và `Content-Range` |
| Header `Cache-Control` thay đổi giữa hit và miss | Filter điều chỉnh max-age theo TTL còn lại | Kiểm tra tài liệu và semantics HTTP, không so chuỗi cứng |
| 304 trả bất thường | Conditional GET/revalidation không được hỗ trợ đúng | Kiểm tra `If-None-Match` và origin behavior |
| Cache metadata không có trong Actuator | Binder/stats không bật hoặc thư viện không expose | Kiểm tra metric names thực tế, không tự giả định có sẵn |
| Bộ nhớ tăng khi cache nhiều | Entry quá lớn, weight limit, eviction hoặc body buffering | Xem heap/GC/Caffeine stats, điều chỉnh size |
| Fallback data bị cache nhầm | Response dự phòng mang status/headers cho phép cache | Tách route hoặc đặt `no-store` và test filter order |
| Sau POST GET vẫn cũ | TTL chưa hết, thiếu invalidation hoặc CDN giữ bản cũ | Định nghĩa stale budget và chiến lược purge/version |
| Lỗi chỉ xuất hiện qua ingress | CDN/proxy cache/headers khác Gateway | Kiểm tra từng hop và `Vary`/Cache-Control thực tế |

### Sáu câu hỏi khi điều tra

1. **Request có match đúng route** và `LocalResponseCache` thực sự hoạt động trên instance đó không?
2. **Request có đủ điều kiện lookup**? Method, body, headers và policy là gì?
3. **Tại đúng lookup có event hit/miss nào**? Hay ta chỉ đang suy từ latency/HTTP 200?
4. **Cache key/biến thể nào được sử dụng**? Có phân biệt query, auth/tenant, locale, Range theo hợp đồng không?
5. **Origin thực sự nhận bao nhiêu attempts**, và có CDN, Retry, CircuitBreaker hay fallback chen vào không?
6. **Response cuối** có đúng body, status, ETag, Vary, Cache-Control, Content-Encoding và stale budget không?

Một lỗi cache thường là sự kết hợp của **định danh entry + TTL + filter order + chính sách bảo mật**, không chỉ là cấu hình thiếu một thuộc tính.

## 18. Checklist tự đánh giá và nghiệm thu

- [ ] Tôi phân biệt **HIT, MISS, BYPASS, INELIGIBLE, ERROR** và định nghĩa mẫu số hit ratio rõ ràng.
- [ ] Tôi biết tính `H/(H+M)` và `H/total requests`, không đánh đồng hai tỷ lệ.
- [ ] Tôi không dùng HTTP 200, latency thấp hay `spring.cloud.gateway.requests` làm bằng chứng hit duy nhất.
- [ ] Tôi biết metric hit/miss phải đến từ **cache lookup thật** hoặc instrumentation được xác minh.
- [ ] Tôi không giả định mọi phiên bản có metric cache built-in cùng tên.
- [ ] Tôi tránh metric tags chứa user ID, cache key, raw URL query, token, cookie hoặc API key.
- [ ] Tôi đã xác định route GET public thích hợp và giới hạn TTL/size hợp lý.
- [ ] Tôi đã xác minh điều kiện `Cache-Control: no-store`/`private` theo implementation thực tế.
- [ ] Tôi đã kiểm thử cache key theo path, query, headers và `Vary`.
- [ ] Tôi đã kiểm tra `ETag`/`304`, gzip/identity và `Range`/`206` nếu API dùng chúng.
- [ ] Tôi không bật shared cache cho dữ liệu cá nhân/tenant-sensitive khi chưa chứng minh isolation.
- [ ] Tôi đã thử user A/B, tenant A/B, token hết hạn và security 401/403.
- [ ] Tôi hiểu TTL/cold start/evictions và nguy cơ stale data sau cập nhật.
- [ ] Tôi đếm backend calls để xác nhận offload, có lưu ý retries/fallback và cache nhiều tầng.
- [ ] Tôi đã test Gateway nhiều instances với local cache không chia sẻ entry.
- [ ] Tôi giám sát per-route hit ratio, hit coverage, P95/P99, memory/GC và backend saturation.
- [ ] Tôi có quy trình tắt cache/rollback khi correctness fail hoặc lộ dữ liệu.
- [ ] Tôi vẫn duy trì TLS, authorization, RateLimiter, Retry và CircuitBreaker như các chính sách độc lập.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm **LocalResponseCache GatewayFilter Factory**, **Local Response Cache Global Filter**, HTTP timeouts và metrics của **Server WebFlux** theo phiên bản.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — tài liệu dự án và release train.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111) — freshness, validation, private/no-store, Age, Vary và quy tắc shared cache.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — HTTP methods, status 200/206/304, validators và representation metadata.
- [Caffeine Cache Documentation](https://github.com/ben-manes/caffeine/wiki) — ghi thống kê và giới hạn bộ nhớ của cache trong tiến trình, khi implementation sử dụng Caffeine.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — counters, tags và đo lường qua Micrometer.
- [Prometheus Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase`, phép tính trên counters và cửa sổ quan sát.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — metrics endpoint, cách expose và bảo vệ management APIs.

**Ghi nhớ:** **Cache hit ratio chỉ đo mức độ tái sử dụng**, không bảo đảm **response đúng**. Khi đánh giá Gateway response caching, hãy đo **hit/miss thực sự tại lookup**, nêu rõ mẫu số và so với backend call count; đồng thời xác nhận **đúng dữ liệu theo user/tenant/URL/query/Vary, đúng thời gian sống và đúng status/headers**. Nếu có xung đột, ưu tiên **tính đúng đắn và bảo mật** hơn việc tăng tỷ lệ hit.
