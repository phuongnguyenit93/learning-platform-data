# Khởi động đồng thời nhiều nút và dồn tải discovery, JWKS

Một cụm Spring Security OAuth 2.0 Resource Server có thể chạy ổn định trong điều kiện bình thường nhưng gặp sự cố khi triển khai phiên bản mới, scale-out hoặc khôi phục sau một lần mất điện. Nguyên nhân thường không nằm ở một request API riêng lẻ: **nhiều instance cùng khởi động và cùng truy cập Authorization Server để lấy metadata discovery hoặc signing keys**.

Hiện tượng này thường được gọi là *thundering herd* hoặc *cache stampede*. Một đợt rollout tạo ra hàng chục hoặc hàng trăm JVM mới. Mỗi instance có cache riêng, nên metadata hoặc JWKS chưa có trong cache. Nếu các instance cùng thực hiện discovery, tải JWKS hoặc refresh key trong một khoảng thời gian ngắn, Authorization Server có thể bị quá tải đúng lúc hệ thống đang cần phục hồi.

Bài này giải thích vòng đời discovery/JWKS, cách nhận diện tải dồn, cách tổ chức cache và refresh, cách giảm áp lực khi khởi động/scale-out, cách xử lý key rotation và lỗi dependency, cùng những điểm cần kiểm chứng trong Spring Security theo phiên bản đang dùng.

Mục tiêu vận hành là để **số instance tăng không biến thành một đợt request đồng thời không kiểm soát đến issuer**, trong khi Resource Server vẫn xác minh token đúng và từ chối token không thể xác minh.

## 1. Vì sao khởi động nhiều instance có thể làm issuer quá tải?

Giả sử Orders API chạy 40 pod. Một đợt rollout thay toàn bộ pod trong vài phút. Mỗi pod tạo decoder dựa trên issuer URI và cần metadata để tìm JWKS endpoint. Sau đó, khi request Bearer đầu tiên đến, decoder có thể cần tải signing keys.

Tùy version Spring Security, cấu hình decoder và cách bean được khởi tạo, discovery có thể diễn ra trong lúc khởi động hoặc được trì hoãn đến lúc xử lý token. JWKS cũng thường được tải khi decoder cần key và cache chưa có dữ liệu phù hợp. Vì vậy, cần đo chính xác implementation của ứng dụng thay vì mặc định mọi request đều gọi discovery hoặc mọi lần startup đều tải JWKS theo cùng cách.

Một kịch bản điển hình:

~~~text
Deployment controller
       |
       +-- tạo đồng thời nhiều pod mới
               |
               +-- Pod 1: discovery / JWKS fetch
               +-- Pod 2: discovery / JWKS fetch
               +-- Pod 3: discovery / JWKS fetch
               +-- ...
               +-- Pod 40: discovery / JWKS fetch
                         |
                         v
              Authorization Server / proxy
                         |
                         v
              metadata/JWKS request spike
                         |
                         v
              latency, 429, 5xx hoặc timeout
                         |
                         v
              decoder không lấy được key
                         |
                         v
              token hợp lệ bị từ chối / pod chưa sẵn sàng
~~~

Một số nguồn tạo ra đợt tải:

- **Cold start:** JVM mới chưa có metadata/JWKS cache.
- **Scale-out:** autoscaler tạo nhiều replica trong thời gian ngắn.
- **Rolling deployment:** nhiều replica mới được tạo theo maxSurge hoặc rollout policy.
- **Node recovery:** node/pod mất đồng thời sau sự cố hạ tầng.
- **Cache expiry:** nhiều cache entry được tạo gần cùng thời điểm và hết hạn gần nhau.
- **Key rotation:** token mới có kid mới khiến nhiều decoder cùng refresh JWKS.
- **Unknown kid:** token có kid chưa biết kích hoạt refresh; một lượng lớn token có kid lạ có thể tạo refresh storm nếu không giới hạn.
- **Issuer outage recovery:** sau khi issuer hoạt động lại, nhiều instance cùng retry.
- **Health check thiết kế sai:** probe hoặc warm-up request liên tục kích hoạt discovery/JWKS fetch.

## 2. Phân biệt discovery traffic và JWKS traffic

Hai nhóm request thường bị gộp chung thành “OAuth server call”, nhưng vòng đời và cache khác nhau.

| Request | Mục đích | Thời điểm có thể phát sinh | Dữ liệu trả về |
| --- | --- | --- | --- |
| OIDC Provider Discovery | Tìm metadata của OpenID Provider | Decoder/registration cần discovery; startup hoặc lazy initialization tùy cấu hình | issuer, jwks_uri, endpoint và capability metadata |
| OAuth Authorization Server Metadata | Tìm metadata OAuth AS theo RFC 8414 | Khi cần metadata của issuer OAuth | issuer, jwks_uri, token/introspection/revocation endpoints nếu được công bố |
| JWKS fetch | Lấy public keys để xác minh JWT | Cache miss, chưa có kid phù hợp hoặc refresh theo implementation | JSON Web Key Set |
| JWKS refresh | Cập nhật tập key đã cache | TTL, unknown kid hoặc refresh policy | JWKS mới |
| Token introspection | Hỏi trạng thái opaque token hoặc token được issuer hỗ trợ | Mỗi lần introspect/cache miss | active và metadata token |

**Discovery không phải JWKS.** Discovery trả metadata, trong đó có thể chứa jwks_uri. JWKS endpoint mới trả public keys. Một deployment có thể tạo tải discovery lớn mà chưa tải JWKS; hoặc discovery đã cache nhưng JWKS vẫn bị refresh do key rotation.

Vì vậy, metrics và access logs cần phân biệt:
- Request đến well-known metadata endpoint.
- Request đến JWKS URI.
- Request đến introspection endpoint.
- Request đến token/revocation endpoint nếu cùng issuer phục vụ nhiều vai trò.

Không gộp mọi endpoint vào một counter chung nếu muốn tìm nguyên nhân cache stampede.

## 3. Cache của một Resource Server có phạm vi nào?

Thông thường, metadata/JWKS cache do decoder hoặc HTTP/JWK client quản lý trong tiến trình. Nếu có 30 pod, có thể tồn tại 30 cache độc lập.

~~~text
                 Authorization Server
                   /metadata
                   /jwks
                        ^
                        |
       +----------------+----------------+
       |                |                |
   Pod A cache      Pod B cache      Pod C cache
   metadata        metadata         metadata
   JWKS            JWKS             JWKS
       |                |                |
   JwtDecoder       JwtDecoder        JwtDecoder
~~~

Một số hệ quả:

- Cache warm ở Pod A không có nghĩa Pod B đã warm.
- Restart JVM xóa cache in-memory.
- Scale-out tạo cache mới.
- Mỗi replica có thể refresh ở thời điểm khác nhau.
- Một shared HTTP proxy/cache có thể giảm request ra issuer, nhưng phải cấu hình đúng semantics HTTP, cache headers và key rotation.
- Cache token status/introspection khác cache metadata và cache JWKS.

Không mặc định JWKS cache được chia sẻ giữa các instance chỉ vì các instance cùng chạy một ứng dụng. Hãy kiểm tra JWK source/cache implementation và cấu hình thực tế.

### Các lớp cache cần phân biệt

| Cache | Key/data | Rủi ro khi quá hạn hoặc stale |
| --- | --- | --- |
| Discovery metadata | Issuer → metadata document | Endpoint cũ, jwks_uri hoặc capability cũ |
| JWKS | jwks_uri → public key set | Key mới chưa có; key bị loại vẫn còn được tin theo cache |
| Negative lookup | kid không tìm thấy | Có thể trì hoãn nhận key mới nếu TTL quá dài |
| DNS/connection pool | Hostname và kết nối HTTP | Endpoint đổi IP hoặc connection lỗi |
| Introspection result | Token/status/claims | Token đã revoke vẫn được chấp nhận đến khi entry hết TTL |
| Application config | issuer-uri, jwk-set-uri, audience | Sai issuer/endpoint hoặc config drift |

JWKS cache không phải token revocation cache. Introspection cache cũng không thay thế JWKS cache.

## 4. Vì sao cache expiry cùng lúc tạo ra stampede?

Giả sử tất cả 40 pod khởi động trong cùng một phút. Mỗi pod fetch JWKS gần như cùng thời điểm và cache response với TTL bằng nhau. Nếu TTL hết hạn sau một khoảng cố định, cache ở các pod có thể hết hạn gần nhau. Request đầu tiên đến mỗi pod sau thời điểm đó đều kích hoạt refresh.

~~~text
Thời gian       Pod A        Pod B        Pod C        Pod N
-------------------------------------------------------------
t0              fetch        fetch        fetch        fetch
t0 + TTL        expired      expired      expired      expired
t1              refresh      refresh      refresh      refresh
t1 + ...        retry        retry        retry        retry
~~~

Một lần refresh có thể đủ để một pod tiếp tục xác minh token, nhưng nếu mọi pod cùng refresh, issuer vẫn nhận một đợt request lớn.

Các yếu tố làm tăng xác suất:
- Startup đồng bộ do deployment controller.
- Cache TTL cố định, không jitter.
- Không có single-flight/coalescing cho nhiều request cùng cache key.
- HTTP client cho phép quá nhiều concurrent requests.
- Retry ngay lập tức khi lỗi.
- Unknown kid từ nhiều request khác nhau.
- Health check gọi decoder hoặc endpoint có side effect cache.
- Không có rate limit ở tầng proxy hoặc issuer.

## 5. Đo tải trước khi thay đổi cấu hình

Trước khi tối ưu, cần biết request nào đang tăng và nó có tương quan với rollout/scale event hay không.

Theo dõi tối thiểu:

| Metric | Ý nghĩa |
| --- | --- |
| Discovery requests/minute | Số request metadata discovery |
| JWKS requests/minute | Số lần tải/refresh JWKS |
| Introspection requests/minute | Số lần gọi introspection nếu dùng opaque token |
| JWKS fetch latency | Độ trễ lấy signing keys |
| Discovery latency | Độ trễ lấy metadata |
| Fetch success/error rate | Tỷ lệ HTTP success, timeout, 429, 5xx |
| Cache hit/miss | Hiệu quả cache nếu implementation cho phép quan sát |
| Unknown kid count | Token tham chiếu key chưa có trong cache |
| Decoder authentication failures | Số lần xác minh JWT thất bại |
| Startup/readiness duration | Thời gian pod đến trạng thái sẵn sàng |
| Concurrent outbound requests | Số kết nối/request đồng thời tới issuer |
| Retry count | Số lần retry do dependency failure |

Tách label theo issuer hoặc endpoint class, nhưng tránh label có cardinality cao như raw kid, token, subject, tenant ID hoặc URL đầy đủ do client kiểm soát. Nếu cần điều tra kid, ghi log có giới hạn/tần suất và không biến nó thành metric label vô hạn.

### Cần tương quan với sự kiện triển khai

Đặt các mốc trên cùng timeline:
- Deployment bắt đầu/kết thúc.
- Replica count và pod creation rate.
- Discovery/JWKS request rate.
- Issuer CPU, connection count, 429/5xx.
- Pod readiness và authentication error rate.
- Key rotation event.
- Cache expiry/refresh event nếu quan sát được.

Nếu request spike xuất hiện ngay khi pod mới được tạo, nhiều khả năng là cold-start traffic. Nếu spike xảy ra theo chu kỳ mà không có rollout, kiểm tra TTL và refresh schedule.

## 6. Giảm số instance khởi động đồng thời

Biện pháp đầu tiên thường nằm ở rollout và autoscaling, không phải thay validator.

### Rolling deployment có giới hạn

Không tạo toàn bộ replica mới cùng một lúc. Điều chỉnh:
- maxSurge và maxUnavailable của deployment.
- Số pod được thay trong mỗi đợt.
- Khoảng cách giữa các batch nếu deployment platform hỗ trợ.
- PodDisruptionBudget để tránh mất quá nhiều instance đang phục vụ.
- Readiness gate để instance mới chỉ nhận traffic sau khi dependencies cần thiết sẵn sàng.

Ví dụ khái niệm Kubernetes:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: app
          image: example/orders-api:version
~~~

Giá trị maxSurge cần tính theo tổng replica và khả năng issuer. Không sao chép con số minh họa vào production mà không đo tải.

### Scale-out theo batch

Autoscaler có thể tăng replica nhanh khi CPU hoặc queue depth tăng. Nếu mỗi replica mới tạo cache lạnh, autoscaling nhanh có thể làm issuer chịu một burst phụ. Cần:
- Giới hạn scale-up rate nếu nền tảng hỗ trợ.
- Tăng replica theo batch nhỏ.
- Kết hợp readiness delay/warm-up có kiểm soát.
- Theo dõi issuer capacity như một dependency của scale-out.

Không giảm scale-up quá mức đến nỗi ứng dụng không đáp ứng tải nghiệp vụ. Tính cả khả năng phục vụ của replica hiện tại trong lúc pod mới đang warm.

## 7. Jitter để tránh các cache hết hạn cùng lúc

Jitter thêm một độ lệch ngẫu nhiên vào thời điểm refresh hoặc TTL. Thay vì mọi instance refresh ở cùng một thời điểm, các instance trải refresh ra một khoảng thời gian.

Ví dụ khái niệm:
- TTL nền: T.
- Jitter: một giá trị ngẫu nhiên trong khoảng [0, J].
- Thời điểm refresh: T - random(0, J), hoặc cache lifetime được phân bố quanh T theo policy.

Không áp dụng jitter một cách tùy tiện nếu cache implementation không cho phép điều khiển TTL. Có thể triển khai tại cache wrapper, proxy cache hoặc cơ chế refresh được thư viện hỗ trợ.

Jitter có ích khi:
- Nhiều replica khởi động cùng lúc.
- Cache TTL cố định.
- Issuer có thể phục vụ tổng tải nhưng không chịu được spike.
- Key set không cần đồng bộ refresh tuyệt đối giữa mọi instance.

Không làm TTL vượt quá freshness/security policy. Jitter chỉ phân tán thời gian refresh; nó không được kéo dài thời gian tin cậy một key đã bị thu hồi vượt quá giới hạn được chấp nhận.

## 8. Single-flight và request coalescing

Single-flight có nghĩa là nhiều request đồng thời cần cùng một dữ liệu chỉ kích hoạt **một lần fetch** trong phạm vi mà cơ chế đó kiểm soát. Những request còn lại chờ cùng kết quả.

~~~text
100 request cùng phát hiện JWKS cache miss
              |
              v
        Single-flight gate
              |
              +-- một HTTP GET JWKS
              |
              +-- các request khác chờ cùng kết quả
              |
              v
         Cập nhật cache
              |
              v
       tiếp tục xác minh token
~~~

Phạm vi rất quan trọng:

- Single-flight trong một JVM chỉ hợp nhất request của cùng instance.
- Nó không tự hợp nhất 50 pod thành một request.
- Shared cache/proxy có thể coalesce ở tầng cluster hoặc edge.
- Một distributed lock có thể giảm fetch trùng, nhưng cần timeout, fencing/lease và xử lý owner crash; không thêm distributed lock nếu chưa chứng minh cần thiết.

Kiểm tra JWK source/HTTP client của phiên bản đang dùng có request coalescing hay không. Không tự giả định decoder đã bảo đảm single-flight chỉ vì nó có cache.

### Không khóa toàn bộ request API

Nếu một thread đang refresh JWKS, không nên thiết kế một global lock làm mọi request của ứng dụng bị chặn vô thời hạn. Chỉ coalesce công việc fetch cùng resource/key set, có timeout và giới hạn chờ. Các token dùng key đã cache có thể tiếp tục được xác minh theo policy khi issuer tạm lỗi.

## 9. Dùng proxy/cache chung cho discovery và JWKS

Một reverse proxy hoặc caching layer nội bộ có thể giảm request trùng từ nhiều pod đến issuer:

~~~text
Pod A ----\
Pod B -----+----> Internal metadata/JWKS cache ----> Authorization Server
Pod C -----+
Pod N ----/
~~~

Lợi ích:
- Cache metadata/JWKS ở một điểm chung.
- Có thể coalesce concurrent fetch.
- Giảm số kết nối từ ứng dụng đến issuer.
- Có thể áp dụng timeout, rate limit và observability tập trung.

Nhưng proxy cache trở thành một phần của trust boundary. Cần kiểm soát:
- Chỉ cache đúng issuer/URI đã allowlist.
- Không cho client tự chọn JWKS URL tùy ý.
- Không bỏ qua TLS server validation khi proxy lấy JWKS.
- Tôn trọng cache headers và freshness policy.
- Không phục vụ key set của issuer khác do cache key collision.
- Không biến cache stale thành cách chấp nhận token không thể xác minh.
- Có cơ chế purge/refresh khẩn cấp khi key bị compromise.
- Giới hạn response size và thời gian fetch.
- Không cache introspection active response như thể nó là JWKS.

JWKS thường là dữ liệu public, nhưng vẫn là dữ liệu bảo mật quan trọng vì nó quyết định chữ ký nào được tin. Public không có nghĩa là có thể cache vô hạn hoặc lấy từ nguồn không xác thực.

## 10. Discovery metadata: cache và cấu hình tĩnh

### Khi dùng issuer-uri

Cấu hình Resource Server phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Spring Security có thể dùng issuer để discovery metadata và xác định JWKS URI. Thời điểm discovery thực hiện phụ thuộc version, cách tạo decoder/bean và cơ chế lazy/deferred initialization. Cần xác nhận bằng log hoặc test với HTTP stub ở đúng dependency version.

Không giả định:
- Mọi startup đều gọi discovery đúng một lần.
- Mọi request API đều gọi discovery.
- JWKS được tải ngay khi metadata được đọc.
- Cache metadata và JWKS có cùng TTL.
- Tất cả replica chia sẻ cùng cache.

### Cấu hình jwk-set-uri tường minh

Trong các version hỗ trợ, có thể khai báo cả issuer-uri và jwk-set-uri:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
          jwk-set-uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

Cấu hình JWKS URI tường minh có thể giảm phụ thuộc discovery trong quá trình khởi tạo decoder, đồng thời issuer-uri vẫn được dùng cho issuer validation theo behavior của version/configuration tương ứng. Phải xác nhận điều này với tài liệu version đang chạy và test thực tế; không bỏ issuer validation để tránh discovery.

Lợi ích vận hành:
- Resource Server không phải tìm jwks_uri từ metadata ở runtime nếu endpoint đã được cấu hình.
- Discovery metadata có thể được kiểm tra riêng trong pipeline/deployment validation.
- Startup có thể ít phụ thuộc một endpoint metadata, tùy cách decoder được khởi tạo.

Giới hạn:
- JWKS vẫn phải được fetch/refresh khi cần key.
- Endpoint thay đổi cần cập nhật config.
- Config drift giữa môi trường có thể dẫn đến sai issuer/JWKS.
- Cần giữ allowlist host và TLS validation.
- Cần giữ issuer/time/audience validators.

### Discovery ở pipeline/deployment

Có thể kiểm tra metadata trước khi rollout:
- Fetch metadata bằng job/monitor có giới hạn.
- Xác nhận issuer khớp chính xác issuer dự kiến.
- Xác nhận jwks_uri dùng HTTPS và thuộc host được phép.
- Kiểm tra JWKS trả schema hợp lệ và có key hiện hành.
- Lưu kết quả kiểm chứng/config version phục vụ audit.

Không nhất thiết mọi pod phải tự discovery lại nếu metadata đã được xác nhận và endpoint tĩnh được quản lý an toàn. Tuy nhiên, phải có quy trình phát hiện endpoint/key thay đổi; không biến snapshot cũ thành nguồn tin vĩnh viễn.

## 11. JWKS cache và key rotation

JWKS cache giảm tải issuer, nhưng cần phối hợp với quy trình key rotation.

Một rotation an toàn thường có các giai đoạn:

~~~text
1. JWKS công bố K1
2. Publish K2 cùng K1
3. Resource Server refresh và nhận K2
4. Authorization Server bắt đầu ký token mới bằng K2
5. Token K1 cũ hết hạn dần
6. Sau overlap, loại K1 khỏi JWKS
~~~

Nếu issuer chuyển sang ký K2 trước khi các Resource Server có cơ hội lấy K2, request đầu tiên mang token kid=K2 có thể kích hoạt refresh đồng loạt. Điều này đặc biệt dễ xảy ra sau rollout khi cache mọi pod đều lạnh.

### Pre-publish key mới

Nếu Authorization Server hỗ trợ quy trình publish key trước khi sử dụng, hãy:
1. Đưa K2 vào JWKS trong khi vẫn ký bằng K1.
2. Cho cache ở Resource Server có thời gian nhận K2.
3. Xác nhận JWKS refresh đã thành công ở fleet hoặc cache layer.
4. Chuyển issuer sang ký token mới bằng K2.
5. Giữ K1 đủ lâu cho token cũ còn hiệu lực và cache policy.
6. Loại K1 theo lịch đã công bố.

Đừng giả định chỉ cần đợi một khoảng cố định là mọi cache đã refresh; cần có bằng chứng từ cache/proxy/metrics hoặc một quy trình kiểm soát refresh.

### Unknown kid

Khi JWT có kid chưa thấy:
- Thực hiện refresh theo policy có giới hạn.
- Coalesce refresh đồng thời cho cùng JWKS URI.
- Rate limit refresh do unknown kid.
- Nếu fetch thành công nhưng không có key phù hợp, từ chối token.
- Nếu fetch thất bại và không có key tin cậy trong cache, không xác minh được token.

Không thử lần lượt mọi key hoặc dùng key bất kỳ để xác minh. Không để mỗi token với một kid ngẫu nhiên kích hoạt một request mạng không giới hạn.

### Key bị compromise khác rotation bình thường

Trong sự cố compromise:
- Loại key khỏi trust set theo quy trình khẩn cấp.
- Đánh giá cache TTL/stale behavior.
- Invalidate cache hoặc ép refresh theo khả năng vận hành.
- Thu hồi token liên quan nếu issuer hỗ trợ.
- Xem xét token lifetime và các Resource Server đang offline.
- Không tiếp tục chấp nhận key cũ chỉ vì cache còn dữ liệu nếu incident policy yêu cầu distrust ngay.

Một policy stale-if-error có thể cải thiện availability trong sự cố mạng, nhưng không được dùng để giữ một key đã biết là compromise.

## 12. Timeout, retry và exponential backoff

Retry ngay lập tức khi issuer timeout có thể làm đợt quá tải nặng hơn. Cần một retry budget rõ ràng.

Một chiến lược backoff có jitter:

~~~text
delay(n) = random(0, min(maxDelay, baseDelay * 2^n))
~~~

Ví dụ tham số minh họa:
- baseDelay: 200 ms.
- maxDelay: 5 s.
- Số lần retry: giới hạn nhỏ theo startup/request budget.
- Tổng thời gian retry: không vượt dependency timeout budget.

Con số thực tế phải theo SLA issuer và latency budget của API. Không dùng retry vô hạn hoặc retry ở nhiều tầng cùng lúc (HTTP client, decoder wrapper, application filter) mà không tính tổng số lần gọi.

### Retry theo loại lỗi

| Lỗi | Hướng xử lý |
| --- | --- |
| DNS/connect timeout | Retry có giới hạn và backoff |
| HTTP 429 | Tôn trọng Retry-After nếu có; giảm concurrency |
| HTTP 5xx | Retry có giới hạn, jitter |
| TLS certificate validation failure | Không retry vô nghĩa; sửa trust/hostname/certificate |
| HTTP 404 metadata/JWKS | Kiểm tra endpoint/config; không lặp nhanh |
| JWKS response JSON sai | Fail closed, cảnh báo; không coi response lỗi là key set rỗng hợp lệ |
| Unknown kid sau refresh thành công | Từ chối token; áp dụng negative lookup/rate limit |
| Introspection active=false | Token inactive; không retry như lỗi mạng |
| Introspection client 401/403 | Điều tra credentials/registration |

### Timeout

Đặt riêng hoặc kiểm soát rõ:
- DNS/connect timeout.
- TLS handshake timeout.
- Response/read timeout.
- Connection pool acquisition timeout.
- Tổng thời gian refresh.
- Thời gian chờ của request đang cần key.

Timeout quá dài làm request threads/connections bị giữ; quá ngắn làm refresh thất bại khi issuer có độ trễ bình thường. Đo từ runtime network của ứng dụng, không chỉ từ laptop.

## 13. Circuit breaker và stale key policy

Circuit breaker có thể ngăn ứng dụng tiếp tục tạo request tới dependency đang lỗi. Nhưng nó phải được áp dụng cẩn thận với xác minh token.

Một policy hợp lý có thể là:
- Token dùng key đã cache và vẫn được phép tin theo policy có thể tiếp tục xác minh local.
- Token cần key mới khi circuit đang mở không thể xác minh và phải bị từ chối.
- Không chấp nhận token không có key chỉ vì issuer không sẵn sàng.
- Khi circuit half-open, chỉ cho phép một lượng probe nhỏ.
- Không để mọi pod cùng probe tại cùng thời điểm; dùng jitter hoặc shared proxy.

Stale key policy cần cân bằng:
- Availability: dùng key cũ đã biết trong lúc issuer tạm outage có thể giúp request hiện tại tiếp tục.
- Security freshness: key bị thu hồi hoặc compromise có thể vẫn được tin nếu cache quá lâu.

Phải xác định:
- Cache max age.
- Stale-if-error window nếu có.
- Key removal/compromise emergency path.
- Cách ép refresh/invalidate.
- Token max lifetime.
- Issuer outage policy.

Không có một giá trị TTL đúng cho mọi hệ thống. Hãy quyết định theo risk, rotation cadence, SLA và khả năng phát hiện key compromise.

## 14. Startup, readiness và liveness

Discovery/JWKS failure có thể tác động đến trạng thái pod. Phân biệt ba khái niệm:

- **Startup:** tiến trình và application context đã khởi tạo.
- **Readiness:** instance có đủ điều kiện nhận traffic theo policy.
- **Liveness:** tiến trình có bị treo/hỏng cần restart hay không.

Không nên biến mọi lỗi issuer ngắn hạn thành liveness failure, khiến orchestrator restart đồng loạt và tạo thêm cold-start storm.

### Nếu discovery là điều kiện để tạo decoder

Nếu ứng dụng không thể tạo decoder khi metadata endpoint unavailable, startup có thể thất bại. Khi đó:
- Giới hạn startup retry.
- Dùng backoff/jitter.
- Điều chỉnh rollout để không tạo quá nhiều pod cùng retry.
- Cân nhắc cấu hình jwk-set-uri tường minh nếu phù hợp và vẫn giữ issuer validation.
- Có cảnh báo cho dependency startup failure.

### Nếu startup có thể hoàn tất nhưng JWKS chưa lấy được

Pod có thể khởi động nhưng request đầu tiên cần key sẽ thất bại. Cần quyết định readiness policy:
- Nếu API bắt buộc xác minh JWT để phục vụ traffic, không đánh dấu ready cho đến khi có khả năng xác minh tối thiểu.
- Nếu endpoint public/health có thể phục vụ mà không cần JWT, có thể dùng readiness policy tinh hơn, nhưng không nhận request protected khi decoder chưa thể xác minh.
- Không gọi discovery/JWKS mỗi lần health probe; warm-up phải có giới hạn và idempotent.

### Liveness không nên phụ thuộc trực tiếp vào issuer

Nếu issuer tạm downtime, restart pod không sửa được dependency và có thể làm tình hình xấu hơn. Liveness nên tập trung vào tình trạng process. Readiness/monitoring có thể phản ánh khả năng xác thực token theo policy riêng.

## 15. Warm-up có kiểm soát

Warm-up có thể tải metadata/JWKS trước khi pod nhận traffic. Tuy nhiên, nếu tất cả pod chạy warm-up cùng lúc, nó chỉ chuyển thundering herd từ request đầu tiên sang startup hook.

Một warm-up an toàn:
- Chỉ chạy một lần cho mỗi instance hoặc qua cache proxy chung.
- Có timeout và retry budget.
- Có jitter giữa các instance.
- Không dùng token production hoặc token giả để ép decoder theo đường không đại diện.
- Nếu kiểm tra decoder bằng canary token, token phải được phát hành cho đúng issuer/audience và không ghi log.
- Không tạo nhiều request chỉ để “giữ cache nóng”.
- Không để readiness probe gọi warm-up lặp liên tục.

Có thể triển khai warm-up như một application startup task có giới hạn, hoặc một pre-deployment job/monitor kiểm tra issuer/JWKS. Lựa chọn phụ thuộc việc ứng dụng có cần key sẵn trước request protected đầu tiên hay không.

## 16. Giới hạn concurrency và connection pool

Nếu issuer có giới hạn số request đồng thời, HTTP client của decoder/JWK source cần phù hợp:
- Connection pool có max connections.
- Pending acquire có timeout.
- Fetch request có deadline.
- Retry không vượt giới hạn concurrency.
- Refresh cùng JWKS URI được coalesce nếu implementation hỗ trợ.
- Không dùng một pool không giới hạn cho tất cả dependency.

Trong WebFlux, cần đặc biệt tránh chặn event-loop khi fetch JWKS hoặc khi tự viết wrapper đồng bộ. Dùng reactive client phù hợp với stack và API của version; không gọi block() trên event-loop.

Trong Servlet, cũng không nên để hàng trăm request đồng thời cùng chờ một refresh mạng mà không có giới hạn. Cần đo request queue, pool saturation và thời gian chờ.

## 17. Cấu hình Spring Security: giữ policy trong khi tối ưu tải

### Cấu hình issuer-uri và jwk-set-uri

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
          jwk-set-uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

Đây là cấu hình minh họa. Hãy xác nhận:
- Version Spring Boot/Security có hỗ trợ các property này.
- Behavior discovery khi khai báo cả hai.
- Issuer validator vẫn được áp dụng.
- Audience validator của API vẫn được cấu hình.
- Decoder/JWK source cache behavior ở version đó.
- Endpoint có thể truy cập từ pod qua TLS/DNS/network policy.

Không bỏ issuer validator hoặc chấp nhận mọi audience để làm giảm tải. Discovery traffic là vấn đề vận hành; issuer/audience validation là security policy.

### Custom decoder và validator

Khi cần custom decoder, giữ các validators mặc định cần thiết rồi bổ sung audience/profile validator:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(
            "https://auth.example.com/realms/shop/protocol/openid-connect/certs")
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTimestamp =
        JwtValidators.createDefaultWithIssuer(
            "https://auth.example.com/realms/shop");

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null));
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTimestamp,
            audience));

    return decoder;
}
~~~

Đây là mẫu cho Servlet decoder. Imports và API cần theo version. Nếu ứng dụng dùng WebFlux, cần cấu hình ReactiveJwtDecoder tương ứng; không inject decoder đồng bộ rồi block trong reactive chain.

Đoạn code cho thấy validator độc lập với cache tuning. Tối ưu fetch không được làm mất kiểm tra issuer, timestamp hoặc audience.

### Cache customization phụ thuộc version

Spring Security có thể dùng Nimbus JOSE/JWT và remote JWK source cho JWKS. Khả năng truyền Spring Cache, tùy chỉnh JWKSource, HTTP client, cache TTL hoặc refresh policy thay đổi theo release/API. Trước khi dùng:
- Kiểm tra builder API của đúng version.
- Xác nhận cache được áp dụng ở metadata, JWK source hay cả hai.
- Kiểm tra cache có hỗ trợ concurrent refresh/coalescing không.
- Kiểm tra TTL và behavior khi endpoint trả 304/429/5xx.
- Xác nhận cách xử lý unknown kid và key removal.
- Viết integration test để chứng minh số HTTP request thực tế.

Không tự đặt property như jwks-cache-ttl nếu Spring Boot/Security version không công bố property đó. Nếu cần custom JWK source, đóng gói rõ thành bean và kiểm thử behavior; không giả định một tên API ở version mới có mặt ở version cũ.

## 18. Không cache sai hoặc chia sẻ nhầm JWKS

Cache key cần phân biệt issuer và JWKS URI. Không cache JWKS chỉ theo hostname nếu cùng host phục vụ nhiều realm/tenant.

Ví dụ:

~~~text
https://auth.example.com/realms/shop/protocol/openid-connect/certs
https://auth.example.com/realms/finance/protocol/openid-connect/certs
~~~

Hai endpoint có thể có key set khác nhau dù cùng host. Cache collision có thể làm decoder nhận key sai hoặc gây lỗi xác minh.

Các nguyên tắc:
- Cache theo canonical URI/issuer context.
- Không để token tự chọn jwks_uri hoặc jku tùy ý.
- Chỉ cho phép issuer/JWKS endpoint trong allowlist.
- Không theo redirect tới host không tin cậy.
- Xác minh TLS hostname và certificate chain.
- Giới hạn response size, key count và parsing time.
- Không dùng stale cache giữa hai issuer.
- Có invalidation theo issuer/key set.

## 19. Rate limit và bảo vệ issuer

Tại issuer hoặc internal proxy, có thể giới hạn:
- Discovery request rate theo client/network.
- JWKS fetch rate theo endpoint.
- Introspection request rate theo client registration.
- Concurrent connections.
- Burst và sustained request rate.
- Retry-after behavior.

Không áp dụng cùng một limit cho JWKS và introspection nếu profile/tải khác nhau. JWKS thường có thể cache dài hơn; introspection có thể có request volume cao hơn vì liên quan token status.

Nếu trả 429, Resource Server nên tôn trọng Retry-After khi có, giảm concurrency và không tạo vòng retry đồng loạt. Cần phối hợp retry policy ở mọi tầng để tổng số request không bị nhân lên.

## 20. Ước lượng tải cho một đợt rollout

Một mô hình ước lượng đơn giản:

~~~text
R_discovery = N_new_instances * discovery_fetches_per_instance
R_jwks      = N_new_instances * jwks_fetches_per_instance
~~~

Nếu 60 instance mới, mỗi instance thực hiện một metadata fetch và một JWKS fetch trong cùng một phút, issuer nhận khoảng 60 request discovery và 60 request JWKS trong phút đó, chưa tính retry, health check, unknown kid hoặc các ứng dụng khác.

Nếu retry 3 lần, số request có thể tăng nhiều lần. Nếu mỗi pod có nhiều decoder/issuer, nhân theo số cache key thực tế.

Với cache proxy coalesce, số request từ proxy đến issuer có thể giảm gần với số lần cache miss của proxy, nhưng proxy vẫn phải phục vụ request từ các pod và phải có capacity riêng.

Một bảng rollout planning:

| Tham số | Ví dụ | Ý nghĩa |
| --- | ---: | --- |
| Tổng replica | 60 | Fleet sau rollout |
| Max surge | 3 | Số pod mới tối đa mỗi đợt vượt desired count |
| Issuer discovery capacity | Theo SLA | Ngưỡng request metadata |
| Issuer JWKS capacity | Theo SLA | Ngưỡng request key set |
| Retry attempts | Giới hạn nhỏ | Tổng lần gọi lại |
| Jitter window | Theo tải | Phân tán thời điểm fetch |
| Cache TTL | Theo policy | Freshness và tải |
| Warm-up concurrency | Giới hạn | Số instance warm cùng lúc |

Các số ở bảng chỉ minh họa cách tính. Dùng load test và SLA issuer để chọn giá trị thực tế.

## 21. Kiểm thử cold start và cache stampede

Không chỉ test một instance chạy lâu. Cần kiểm tra hành vi khi nhiều decoder cùng bắt đầu với cache lạnh.

### Test discovery

- Dùng HTTP stub server phục vụ metadata.
- Tạo nhiều application context/decoder theo cách gần với deployment.
- Khởi tạo đồng thời có kiểm soát.
- Đếm request đến metadata endpoint.
- Xác nhận request rate nằm trong budget.
- Kiểm tra khi metadata endpoint timeout hoặc trả 429/5xx.

### Test JWKS

- Bắt đầu với cache rỗng.
- Gửi đồng thời token dùng cùng kid.
- Quan sát số lần GET JWKS.
- Xác nhận cache/coalescing hoạt động theo implementation.
- Thay JWKS để thêm key mới.
- Gửi token có kid mới và đo refresh.
- Gửi nhiều kid không tồn tại để kiểm tra refresh rate limit.
- Giả lập timeout và response sai schema.

### Test fleet

Mô phỏng:
- 10, 50, 100 instance khởi động cùng lúc.
- Rollout batch nhỏ.
- Cache TTL cùng lúc và có jitter.
- Issuer latency bình thường và tăng cao.
- Issuer trả 429/503.
- Issuer outage rồi phục hồi.
- Key rotation trong khi một phần instance cache lạnh.
- Nhiều instance cùng nhận token có kid mới.

Không nhất thiết chạy 100 JVM trong mỗi build. Có thể có unit/integration tests nhỏ thường xuyên và một load test riêng cho release/infra validation.

## 22. Ma trận failure behavior

| Sự cố | Key đã cache | Key mới/unknown kid | Hành vi cần xác định |
| --- | --- | --- | --- |
| Discovery endpoint outage | Decoder đã có metadata | Decoder chưa có metadata | Startup/deferred initialization policy |
| JWKS endpoint timeout | Có key phù hợp | Chưa có key phù hợp | Cache policy; unknown key fail closed |
| JWKS trả 429 | Có key phù hợp | Chưa có key phù hợp | Backoff, Retry-After, readiness |
| JWKS trả 5xx | Có key phù hợp | Chưa có key phù hợp | Retry budget và stale-key policy |
| JWKS JSON không hợp lệ | Key cũ có thể còn trong cache | Không lấy được key mới | Cảnh báo, fail closed cho key chưa biết |
| Issuer outage kéo dài | Key cũ còn cache | Token mới dùng key mới | SLA/cache freshness và incident runbook |
| Key bị compromise | Cache có thể còn key cũ | Có thể refresh key set | Emergency invalidation, revoke, denylist nếu cần |
| Unknown kid storm | Cache có key khác | Rất nhiều kid lạ | Refresh coalescing, rate limit, negative cache |

Một policy availability có thể cho phép dùng key đã cache trong một cửa sổ xác định khi issuer tạm lỗi. Nhưng token không có key tin cậy không được chấp nhận. Nếu key bị compromise, security incident policy có thể yêu cầu ngừng tin key ngay cả khi cache còn hiệu lực.

## 23. Readiness và warm-up không được tạo thêm tải

Health check thường chạy liên tục từ orchestrator hoặc load balancer. Nếu readiness endpoint gọi decoder hoặc cố xác minh một token bằng key mới mỗi lần, nó có thể tạo traffic không cần thiết.

Thiết kế:
- Liveness không gọi issuer.
- Readiness đọc trạng thái đã được cập nhật bởi một background check có giới hạn.
- Background check dùng cache và single-flight, không chạy một request riêng cho từng probe.
- Warm-up có timeout/backoff và chỉ chạy theo lifecycle cần thiết.
- Khi issuer lỗi, readiness policy phản ánh khả năng xác minh token theo đúng security requirement.
- Không trả healthy chỉ vì pod process sống nếu protected API không thể xác minh bất kỳ token nào cần thiết.

Không biến probe thành một endpoint public có thể ép ứng dụng fetch JWKS theo yêu cầu attacker.

## 24. Logging và observability an toàn

Có thể ghi nhận:
- Issuer alias đã cấu hình.
- Endpoint class: discovery, jwks hoặc introspection.
- HTTP status, latency, timeout category.
- Cache hit/miss/refresh nếu implementation cung cấp.
- Kid không tìm thấy dưới dạng log có rate limit.
- Pod identity, deployment revision.
- Decoder failure category.
- Correlation ID của rollout/incident.

Không ghi:
- Access token.
- Refresh token.
- Client secret.
- Private key.
- Toàn bộ Authorization header.
- DPoP proof hoặc JWT payload nhạy cảm.
- Subject/tenant/token làm metric label có cardinality cao.

Nếu cần log kid để điều tra rotation, kid thường là metadata công khai nhưng vẫn cần giới hạn cardinality và tránh để client tạo vô hạn label.

## 25. Runbook khi issuer bị quá tải trong rollout

Khi discovery/JWKS latency tăng mạnh:

1. Xác định endpoint nào bị quá tải: discovery, JWKS hay introspection.
2. Kiểm tra số pod mới và rollout/scale event cùng thời điểm.
3. Xem request rate, concurrency, 429/5xx, timeout và retry count.
4. Tạm giảm rollout batch hoặc scale-up rate nếu có thể.
5. Kiểm tra các instance có cache hit hay tất cả đều cold.
6. Xác nhận key rotation có diễn ra cùng thời điểm không.
7. Giảm retry storm và áp dụng backoff/jitter theo policy.
8. Nếu có cache proxy, kiểm tra proxy health, hit ratio và cache key.
9. Không tắt issuer/audience/signature validation để khôi phục traffic.
10. Với key đã cache, áp dụng stale policy đã phê duyệt; với key mới chưa xác minh, fail closed.
11. Khi issuer hồi phục, cho instance retry theo batch/jitter, tránh đồng loạt.
12. Sau incident, kiểm tra rollout policy, TTL, coalescing, timeout và alert threshold.

Không xóa toàn bộ cache trong lúc issuer đang quá tải trừ khi incident yêu cầu distrust key; thao tác đó có thể làm toàn fleet fetch lại cùng lúc.

## 26. Những lỗi vận hành thường gặp

**“Mỗi pod có cache nên tổng tải không đáng kể.”** Không. Cache in-memory thường độc lập; cold start có thể nhân số request theo replica.

**“Discovery và JWKS là một request.”** Không. Discovery tìm metadata; JWKS trả public keys. Đo và tối ưu riêng.

**“Chỉ cần tăng TTL thật dài.”** TTL dài giảm fetch nhưng làm key rotation/removal chậm được nhìn thấy. Chọn theo freshness và security policy.

**“Khi cache miss, cứ retry ngay.”** Retry đồng loạt làm issuer quá tải nặng hơn. Dùng backoff, jitter, giới hạn concurrency và retry budget.

**“Có JWKS URI tĩnh thì không còn request JWKS.”** Không. Nó có thể giảm discovery, nhưng decoder vẫn phải lấy/refresh key.

**“Có issuer-uri thì mọi behavior startup giống nhau.”** Không. Thời điểm discovery phụ thuộc version, bean lifecycle và cấu hình.

**“Một pod warm nghĩa cả fleet warm.”** Không nếu cache độc lập.

**“Unknown kid cứ refresh không giới hạn.”** Điều đó có thể tạo request storm. Giới hạn refresh và từ chối khi không có key phù hợp.

**“Issuer outage thì chấp nhận token chưa xác minh.”** Không. Không thể xác minh key mới thì không được chấp nhận token đó.

**“Liveness fail khi issuer lỗi để pod tự restart.”** Điều này có thể tạo cold-start storm. Phân biệt process liveness với dependency readiness.

**“Cache proxy có thể phục vụ JWKS vô hạn.”** Không. Cache vẫn cần freshness, key rotation và emergency invalidation.

**“Xóa cache là cách xử lý mọi lỗi key.”** Khi issuer đang quá tải, xóa cache toàn fleet có thể làm tải tăng đột biến.

## 27. Quy trình thiết kế và triển khai

1. **Đo baseline:** tách discovery, JWKS và introspection traffic; ghi nhận cache behavior.
2. **Xác nhận version:** ghi lại Spring Boot, Spring Security, Nimbus và HTTP client version thực tế.
3. **Kiểm tra lifecycle:** xác định discovery/JWKS fetch diễn ra lúc startup, lazy initialization hay refresh.
4. **Xác định cache scope:** in-memory từng JVM, proxy cache hay shared cache; ghi rõ TTL và invalidation.
5. **Giới hạn rollout:** điều chỉnh batch, maxSurge và scale-up rate theo issuer capacity.
6. **Phân tán refresh:** thêm jitter nếu implementation cho phép và có single-flight/coalescing.
7. **Cấu hình network:** timeout, pool, retry budget, exponential backoff và rate limit.
8. **Tách startup/readiness/liveness:** không tạo probe fetch liên tục và không restart cả fleet khi issuer tạm lỗi.
9. **Quản lý key rotation:** pre-publish key mới, overlap, quan sát refresh và có emergency invalidation.
10. **Bảo vệ trust:** giữ issuer, audience, signature và TLS validation; không fallback fail-open.
11. **Kiểm thử cold start:** nhiều instance, cache lạnh, unknown kid, 429/5xx và outage recovery.
12. **Theo dõi vận hành:** dashboard, alert, runbook và metrics không chứa token/secret.
13. **Triển khai theo batch:** rollout staging trước, đo tải issuer rồi mới áp dụng production.

**Điểm cần nhớ:** nhiều Resource Server khởi động cùng lúc có thể tạo một đợt discovery/JWKS fetch vì cache thường độc lập theo JVM. Hãy phân biệt metadata discovery với JWKS, đo request và cache hit/miss, giới hạn rollout, dùng jitter và single-flight khi có hỗ trợ, cấu hình timeout/backoff/concurrency, và phối hợp key rotation với cache freshness. Cấu hình jwk-set-uri tường minh có thể giảm phụ thuộc discovery nhưng không loại bỏ JWKS fetch. Khi issuer lỗi hoặc key chưa biết, chỉ xác minh bằng key tin cậy đã có theo stale policy được phê duyệt; token không thể xác minh phải bị từ chối.
