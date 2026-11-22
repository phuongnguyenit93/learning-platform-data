# Độ trễ, thông lượng và thời gian xử lý xác thực trong một yêu cầu

## 1. Vì sao cần đo riêng thời gian xác thực?

Một request tới API được bảo vệ bởi Spring Security Resource Server đi qua nhiều bước: nhận kết nối, xử lý HTTP, chạy security filters hoặc web filters, đọc access token, xác minh token, tạo Authentication, kiểm tra quyền, chạy controller và truy cập dữ liệu. Khi API chậm, không thể mặc định nguyên nhân nằm ở JWT hoặc Spring Security.

Thời gian phản hồi của người dùng là tổng thời gian của toàn bộ đường đi. Thời gian xác thực chỉ là một phần của đường đi, nhưng nó có thể trở thành nút thắt khi mọi request đều phải introspect token từ Authorization Server, tải khóa JWKS, truy vấn quyền từ database hoặc chờ một dịch vụ từ xa.

Ba khái niệm cần phân biệt:

- **Độ trễ (latency):** thời gian từ khi một request bắt đầu tới khi có kết quả mà ta đang đo. Có thể đo toàn request hoặc riêng một bước xác thực.
- **Thông lượng (throughput):** số request được xử lý trong một đơn vị thời gian, thường là requests/second (RPS).
- **Thời gian xử lý xác thực:** khoảng thời gian từ khi security component bắt đầu xác minh thông tin xác thực tới khi tạo Authentication thành công hoặc thất bại.

Độ trễ và thông lượng có liên quan nhưng không đồng nghĩa. Một hệ thống có thể xử lý 2.000 RPS khi request nhẹ, nhưng chỉ đạt 400 RPS khi mỗi request phải gọi introspection endpoint. Một request đơn lẻ có thể có latency thấp trong lúc hệ thống nhàn, rồi tăng mạnh khi connection pool, CPU hoặc downstream service bão hòa.

Trong chương Hiệu năng và vận hành, mục tiêu là đo đúng đoạn đường, hiểu các yếu tố tạo ra chi phí, tìm điểm bão hòa và tối ưu mà vẫn giữ nguyên chính sách bảo mật.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đường đi của một request qua Spring Security Resource Server.
2. Phân biệt latency toàn request với latency xác thực.
3. So sánh chi phí xử lý JWT và opaque token.
4. Hiểu ảnh hưởng của JWK cache, introspection, authority mapping và truy vấn quyền.
5. Đo p50, p95, p99, throughput, error rate và saturation.
6. Thiết kế load test có warm-up, ramp-up, steady state và soak test.
7. Phát hiện blocking call trong WebFlux và bottleneck trong Servlet.
8. Tối ưu cache, connection pool, concurrency và timeout đúng cách.
9. Theo dõi hiệu năng mà không đưa token hoặc dữ liệu nhạy cảm vào metric/log.
10. Đánh giá trade-off giữa hiệu năng, freshness của trạng thái token và khả năng thu hồi.

---

## 2. Một request đi qua những bước nào?

### 2.1. Đường đi ở mức tổng quan

Với JWT access token, một request thường đi qua các bước sau:

~~~mermaid
flowchart TD
    A[HTTP request đến API] --> B[Servlet Filter Chain hoặc WebFilter Chain]
    B --> C[Trích xuất Authorization header]
    C --> D[Authentication Manager]
    D --> E[ReactiveJwtDecoder hoặc JwtDecoder]
    E --> F[Parse JWT và xác minh chữ ký]
    F --> G[Validate issuer, audience, thời gian, claims]
    G --> H[Authentication Converter]
    H --> I[SecurityContext]
    I --> J[Authorization rules]
    J --> K[Controller và business logic]
    K --> L[Repository hoặc downstream service]
    L --> M[HTTP response]
~~~

Với opaque token, phần decoder thường được thay bằng introspector:

~~~mermaid
sequenceDiagram
    participant Client
    participant RS as Resource Server
    participant AS as Authorization Server
    participant API as Application

    Client->>RS: Request + Bearer token
    RS->>RS: Đọc token và bắt đầu authentication
    RS->>AS: Introspection request
    AS-->>RS: active, subject, scope, claims
    RS->>RS: Tạo Authentication
    RS->>RS: Kiểm tra authorization
    RS->>API: Chạy controller
    API-->>Client: Response
~~~

Sơ đồ chỉ thể hiện các bước logic. Một số bước được gộp trong filter, provider hoặc manager; thứ tự và thành phần cụ thể có thể thay đổi theo cấu hình Servlet/WebFlux và JWT/opaque token.

### 2.2. Các khoảng thời gian nên tách

Để tìm bottleneck, hãy tách tối thiểu các khoảng sau:

| Khoảng đo | Bắt đầu | Kết thúc | Ý nghĩa |
|---|---|---|---|
| HTTP server duration | Server nhận request | Server ghi response | Trải nghiệm ở phía server |
| Security chain duration | Bắt đầu security filter/web filter | Kết thúc security chain | Chi phí của security pipeline |
| Authentication duration | Bắt đầu authentication | Có Authentication hoặc lỗi | Thời gian xác minh token |
| JWT decode duration | Gọi decoder | Decoder phát Jwt hoặc lỗi | Parse, signature, validators và key lookup nếu cache miss |
| Introspection duration | Gửi introspection request | Nhận/đọc response | Chi phí network và AS |
| Converter duration | Nhận Jwt/principal | Tạo Authentication | Mapping subject, scope và authority |
| Authorization duration | Bắt đầu kiểm tra quyền | Có quyết định | Scope, role, policy hoặc tenant lookup |
| Application duration | Vào controller/service | Hoàn thành nghiệp vụ | Business logic và data access |

Không cộng tất cả các số đo nếu chúng lồng nhau. Ví dụ HTTP server duration chứa security, controller và repository. Nếu cộng HTTP duration với security duration, ta đã đếm security hai lần.

### 2.3. Latency của một request không phải tổng đơn giản của mọi timer

Một request tuần tự có thể xấp xỉ:

\[
T_{request} = T_{network-in} + T_{security} + T_{application} + T_{network-out}
\]

Trong đó:

\[
T_{security} = T_{extract} + T_{authenticate} + T_{authorize}
\]

Và với JWT:

\[
T_{authenticate} \approx T_{decode} + T_{validate} + T_{convert}
\]

Với opaque token:

\[
T_{authenticate} \approx T_{introspection} + T_{convert}
\]

Đây là mô hình phân rã để tư duy, không phải công thức cộng chính xác trong mọi hệ thống. Một số tác vụ có thể chạy song song, một số timer chứa thời gian chờ scheduler hoặc connection pool, và một số instrumentation đo cùng một khoảng.

---

## 3. Những yếu tố quyết định thời gian xác thực

### 3.1. Parse và xác minh JWT

JWT thường gồm ba phần Base64URL: JOSE header, payload và signature. Resource Server cần parse token, kiểm tra thuật toán, xác minh chữ ký và chạy các validators.

Chi phí xác minh chữ ký phụ thuộc vào:

- Thuật toán ký, ví dụ RSA hoặc ECDSA.
- Kích thước khóa và implementation crypto provider.
- CPU architecture và mức tải CPU.
- Kích thước token và số lượng claim.
- Số validators và logic mapping bổ sung.
- Cache khóa đã tải từ JWKS endpoint.

Không nên kết luận ECDSA luôn nhanh hơn RSA hoặc ngược lại. Hãy benchmark đúng thuật toán, kích thước key, JDK, crypto provider và phần cứng của môi trường triển khai.

Parse JWT và kiểm tra claims thường là xử lý trong tiến trình. Với cấu hình JWT Resource Server bình thường, server không cần gọi Authorization Server cho mỗi token chỉ để xác minh chữ ký. Tuy nhiên, nếu cần tải signing key mới, có thể phát sinh network request tới JWKS endpoint.

### 3.2. JWK Set và cache khóa

Resource Server lấy public key từ JWK Set URI hoặc metadata issuer discovery. Khi key đã được tải và cache, các request tiếp theo có thể xác minh chữ ký cục bộ.

Đường đi điển hình:

~~~text
Request đầu tiên hoặc cache miss
  -> Decoder cần key theo kid
  -> JWK source tìm key trong cache
  -> Nếu chưa có key phù hợp, tải JWK Set
  -> Chọn key và xác minh signature
  -> Cache key/JWK theo policy

Request tiếp theo với key đã cache
  -> Lấy key từ cache
  -> Xác minh signature cục bộ
~~~

Điều này tạo ra khác biệt giữa **cold path** và **warm path**:

- Cold path có thể bao gồm DNS, TLS handshake, kết nối HTTP, tải JWKS và parse JWK.
- Warm path thường chỉ cần lookup cache và verify signature.
- Khi Authorization Server rotate key, Resource Server có thể cần refresh JWK Set để tìm key mới.
- Khi cache hết hạn hoặc bị evict, một request lại có thể kích hoạt fetch.

Đừng benchmark chỉ bằng một request đầu tiên rồi coi đó là latency ổn định. Cũng đừng chỉ đo warm path nếu production có nhiều instance mới khởi động cùng lúc hoặc AS thường xuyên rotate key.

### 3.3. Issuer discovery và JWKS retrieval

Nếu cấu hình bằng issuer URI, framework có thể cần lấy metadata của Authorization Server để tìm endpoint JWKS. Cấu hình và lifecycle của decoder quyết định metadata được lấy khi khởi tạo hay khi cần.

Để giảm ảnh hưởng lúc phục vụ traffic:

- Khởi tạo decoder và kiểm tra metadata trong startup/warm-up nếu kiến trúc cho phép.
- Dùng JWKS endpoint ổn định và có khả năng chịu tải.
- Cấu hình timeout hợp lý cho kết nối metadata/JWKS.
- Giữ các signing key cũ trong thời gian overlap phù hợp khi rotate.
- Theo dõi lỗi fetch key, cache miss và thời gian tải JWKS.
- Tránh tạo một decoder mới cho từng request; decoder nên là bean dùng chung.

Không tự cache key vô thời hạn. Key rotation là một phần của trust lifecycle. Cache quá lâu có thể làm chậm việc nhận key mới hoặc tiếp tục tin key đã bị loại bỏ theo policy.

### 3.4. Opaque token introspection

Với opaque token, Resource Server thường gửi token tới introspection endpoint để hỏi token còn active hay không và lấy subject, scope cùng attributes.

Khác biệt hiệu năng quan trọng:

- JWT có thể được xác minh cục bộ sau khi đã có key.
- Opaque token thường cần network round trip tới AS cho mỗi lần introspection, trừ khi ứng dụng có cache hoặc một cơ chế tối ưu khác.
- Thời gian introspection phụ thuộc network, TLS, connection pool, AS capacity, database/token store của AS và payload response.
- Khi AS chậm, latency xác thực và số request đang chờ tăng theo.

Một introspection call có thể tốn vài mili giây trong mạng nội bộ hoặc cao hơn nhiều khi có tải, nhưng không nên dùng con số cố định để dự đoán production. Đo trên topology và tải thật.

### 3.5. Authority mapping và Authentication conversion

Sau khi token được xác minh, Resource Server còn phải tạo Authentication:

- Đọc subject/principal name.
- Map scope thành authority, ví dụ SCOPE_orders.read.
- Map claim roles/groups nếu ứng dụng có policy đó.
- Chuẩn hóa các claim custom.
- Tạo principal hoặc authentication object.
- Có thể truy vấn role directory hoặc entitlement service nếu thiết kế yêu cầu.

Mapping claim trong bộ nhớ thường rẻ hơn một network call. Nếu converter gọi database hoặc HTTP cho từng request, chi phí đó có thể lớn hơn cả JWT signature verification.

Nếu cần quyền động, hãy quyết định rõ dữ liệu quyền được lấy ở authentication time, authorization time hay từ cache. Việc tải toàn bộ quyền của user trong mỗi request có thể làm tăng latency và tải downstream không cần thiết.

### 3.6. Authorization sau Authentication

Xác thực trả lời “token/principal này là ai và có hợp lệ không?”. Authorization trả lời “principal này có được thực hiện hành động trên tài nguyên này không?”.

Một request có thể xác thực nhanh nhưng chậm ở bước kiểm tra:

- Role hoặc group từ database.
- Tenant membership.
- Object ownership.
- Policy engine.
- Permission service.
- Method security hoặc ACL.
- Truy vấn dữ liệu để kiểm tra quyền.

Khi dashboard chỉ ghi một metric “security duration”, cần tách authentication và authorization để tránh tối ưu nhầm phần.

---

## 4. So sánh JWT và opaque token dưới góc nhìn hiệu năng

| Tiêu chí | JWT access token | Opaque access token |
|---|---|---|
| Xác minh mỗi request | Thường cục bộ sau khi có key | Thường gọi introspection endpoint |
| Network dependency trên hot path | Thường không cần | Thường có |
| Chi phí chính | Parse, signature verify, validators, mapping | Network, AS processing, response parsing, mapping |
| Khả năng scale Resource Server | Tăng theo CPU và request rate | Phụ thuộc thêm capacity của AS và connection pool |
| Thu hồi token tức thời | Khó nếu chỉ xác minh JWT cục bộ | AS có thể trả inactive ở lần introspection tiếp theo |
| Cache | JWKS/key cache; có thể cache kết quả theo policy | Introspection result cache với TTL có giới hạn |
| Khi AS tạm thời lỗi | Token đã có key vẫn có thể xác minh | Introspection mới thường thất bại |
| Kích thước request | Token thường dài hơn | Token thường ngắn hơn |
| Freshness trạng thái token | Phụ thuộc expiry và cơ chế bổ sung | Phụ thuộc mỗi lần introspect hoặc TTL cache |

JWT không tự động luôn nhanh hơn trong mọi hệ thống. Nếu JWT lớn, signature verify nặng, converter truy vấn database hoặc decoder liên tục fetch JWKS thì lợi thế có thể giảm. Opaque token có thể đạt latency tốt nếu AS ở gần, connection pool tốt và có cache đúng policy.

Lựa chọn token format cần cân bằng:

- Mức độ cần thu hồi token sớm.
- Số lượng Resource Server.
- Khả năng chịu tải của Authorization Server.
- Latency giữa RS và AS.
- Yêu cầu audit và trạng thái token.
- Khả năng vận hành key rotation.
- Chính sách cache và thời gian stale tối đa có thể chấp nhận.

Không đổi từ opaque sang JWT chỉ vì một benchmark đơn lẻ. Hãy đo cả hot path, cold path, key rotation, AS outage và yêu cầu revocation.

---

## 5. Cache có thể cải thiện hiệu năng ở đâu?

### 5.1. Cache JWK và metadata

JWK cache giảm số lần Resource Server phải gọi JWKS endpoint. Cần xem xét:

- Cache lifetime và refresh policy.
- Hành vi khi gặp unknown kid.
- Khả năng đồng bộ refresh giữa nhiều instance.
- Overlap của key cũ và key mới khi rotation.
- Timeout/retry khi JWKS endpoint không sẵn sàng.

Khi nhiều instance cùng khởi động hoặc cùng gặp unknown kid, có thể xảy ra hiện tượng nhiều request tải JWKS đồng thời. Nếu cần, dùng startup warm-up, cache phù hợp và giới hạn concurrency ở tầng key retrieval.

### 5.2. Cache kết quả introspection

Một cache introspection có thể giảm round trip tới AS. Nhưng cache làm giảm freshness của trạng thái token.

Ví dụ token bị revoke ngay sau khi cache lưu active=true:

~~~text
t0: RS introspect -> active=true, cache TTL 30s
t1: AS revoke token
t2: RS đọc cache -> vẫn thấy active=true
t3: cache hết hạn
t4: RS introspect lại -> active=false
~~~

Trong ví dụ, cửa sổ stale tối đa gần với TTL còn lại của cache, cộng thêm độ trễ propagation và các chi tiết implementation.

Chọn TTL theo yêu cầu bảo mật:

- Token có quyền thấp và access token ngắn hạn có thể chấp nhận cache TTL dài hơn.
- Token quản trị hoặc giao dịch nhạy cảm cần freshness cao hơn.
- Nếu cần thu hồi gần như tức thời, cache active=true phải rất ngắn hoặc cần cơ chế invalidation chủ động.
- Không cache response lỗi/timeout như token active.
- Không dùng cache key chứa raw token trong log hoặc metric.

### 5.3. Cache authority và tenant data

Authority mapping có thể lấy từ token claims hoặc từ một permission service. Nếu cache kết quả permission:

- Xác định key gồm subject, tenant, resource/action và version dữ liệu cần thiết.
- TTL phải phù hợp với thời gian cập nhật quyền.
- Invalidation phải được thiết kế rõ khi role/tenant membership thay đổi.
- Không dùng cache của một user cho user khác.
- Không để cache hit bỏ qua kiểm tra resource ownership cần thực hiện theo từng bản ghi.

Một claim scope trong access token thường là snapshot quyền tại thời điểm phát hành. Nếu ứng dụng cần quyền cập nhật gần realtime, cần có cơ chế ngoài scope snapshot và phải đo chi phí của cơ chế đó.

### 5.4. Cache không phải giải pháp cho mọi bottleneck

Cache có thể làm giảm network call nhưng cũng tạo thêm:

- Memory footprint.
- Serialization/deserialization.
- Eviction và contention.
- Invalidation complexity.
- Stale authorization.
- Cache stampede.
- Khó quan sát khi hit/miss không được đo.

Đo cache hit ratio, latency hit/miss, eviction, size và stale window. Nếu cache hit ratio thấp hoặc dữ liệu gần như luôn thay đổi, cache có thể không giúp nhiều.

---

## 6. Connection pool, timeout và concurrency

### 6.1. Introspection WebClient

Với opaque token, Resource Server cần HTTP client có connection pool được cấu hình phù hợp. Nếu pool quá nhỏ, request phải chờ connection dù AS vẫn phản hồi nhanh. Nếu pool quá lớn, hệ thống có thể tạo quá nhiều connection và làm AS quá tải.

Theo dõi:

- Số connection đang active.
- Số connection idle.
- Pending acquire count và thời gian chờ lấy connection.
- Connect timeout.
- Response timeout.
- TLS handshake frequency.
- Số request lỗi do pool exhaustion.
- Connection reuse và keep-alive.

Không tạo một WebClient mới cho mỗi request. Tạo client dùng chung, cấu hình pool và timeout rõ ràng.

### 6.2. Timeout phải phản ánh budget của request

Giả sử API có mục tiêu p95 là 300 ms. Nếu introspection timeout đặt 5 giây, một phần request có thể giữ tài nguyên rất lâu sau khi đã vượt xa latency budget.

Timeout nên được phân tầng:

- Connection acquisition timeout.
- Connect timeout.
- TLS handshake timeout nếu client hỗ trợ cấu hình riêng.
- Response/read timeout.
- Tổng deadline của request.
- Timeout cho permission service hoặc database.

Một timeout ở lớp dưới không nên dài hơn deadline tổng mà caller còn chờ. Đồng thời, timeout quá ngắn sẽ tạo lỗi giả khi có burst hoặc network jitter.

### 6.3. Concurrency và backpressure trong WebFlux

WebFlux dùng reactive pipeline để tránh giữ một thread cho mỗi request đang chờ I/O. Điều đó không làm downstream có capacity vô hạn.

Nếu 5.000 request cùng gọi một introspection endpoint, Resource Server vẫn tạo tải tương ứng lên connection pool và AS. Cần giới hạn concurrency hoặc dùng bulkhead ở dependency boundary để bảo vệ hệ thống.

Không gọi blocking JDBC, blocking Redis client hoặc RestTemplate trực tiếp trên event loop. Blocking call có thể làm một event-loop thread không xử lý được các request khác, khiến latency tăng trên diện rộng.

Nếu buộc phải gọi một API blocking, chuyển nó sang scheduler phù hợp là giải pháp chuyển tiếp; về lâu dài nên dùng reactive client/driver tương ứng. Scheduler cũng có giới hạn thread và queue, không phải nơi chứa workload vô hạn.

### 6.4. Concurrency và thread pool trong Servlet

Servlet stack thường dùng request threads. Khi request chờ introspection hoặc database, thread vẫn bị chiếm trong thời gian chờ. Nếu downstream chậm:

- Active request threads tăng.
- Request queue tăng.
- Thread pool cạn.
- Request mới chờ lâu hơn hoặc bị từ chối.
- Latency tail tăng nhanh.

Theo dõi active threads, queue length, rejected tasks, request concurrency và thời gian chờ downstream. Không tăng max threads vô hạn; nhiều thread hơn có thể tăng context switching và làm downstream quá tải.

---

## 7. Đo latency đúng cách

### 7.1. Không chỉ nhìn average

Average có thể che giấu một nhóm request rất chậm. Ví dụ 99 request mất 20 ms và 1 request mất 2 giây thì average là 39,8 ms, trong khi một user vẫn phải chờ 2 giây.

Nên theo dõi các percentile:

- **p50:** một nửa request nhanh hơn hoặc bằng giá trị này.
- **p90:** 90% request nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% request nhanh hơn hoặc bằng giá trị này.
- **p99:** 99% request nhanh hơn hoặc bằng giá trị này.
- **max:** request chậm nhất trong cửa sổ đo; nhạy với outlier và sample size.

p95/p99 hữu ích để quan sát tail latency. Tuy nhiên, percentile cần đủ số lượng sample và cửa sổ thời gian phù hợp; p99 trên vài chục request không có ý nghĩa ổn định.

### 7.2. Throughput và error rate

Theo dõi ít nhất:

- Requests per second.
- Successful requests per second.
- 401 và 403 rate.
- 5xx rate.
- Timeout rate.
- Authentication failure theo nhóm nguyên nhân.
- Introspection/JWKS dependency error rate.
- CPU, memory, GC và connection pool saturation.

Một hệ thống đạt RPS cao bằng cách trả 401 hoặc 503 cho nhiều request không phải hệ thống có throughput hữu ích cao. Luôn đọc throughput cùng success/error rate.

### 7.3. Histogram và metric cardinality

Dùng histogram khi cần tính percentile từ phân phối latency. Metric label phải có cardinality giới hạn.

Các label phù hợp thường là:

- operation: jwt_decode, opaque_introspection, authentication, authorization.
- outcome: success, invalid, error, timeout, cancelled.
- token_type: jwt hoặc opaque nếu dimension này được kiểm soát.
- application/route group đã chuẩn hóa, không phải raw path chứa ID.

Không dùng các giá trị sau làm metric label:

- Access token hoặc refresh token.
- Subject/user ID.
- Email.
- Session ID.
- Request ID.
- Raw URL có path variable.
- Exception message tùy ý.

Cardinality cao có thể làm metrics backend tốn bộ nhớ và CPU. Dữ liệu định danh cần thiết cho trace/log phải được xử lý theo chính sách privacy và không bao giờ bao gồm token bí mật.

### 7.4. Tránh log token

Không log Authorization header, compact JWT, introspection request body, client secret hoặc DPoP proof. Khi cần correlate lỗi, dùng trace ID hoặc một identifier đã được thiết kế an toàn, không dùng raw credential.

Log exception cũng cần xem xét vì một số HTTP client có thể đưa request details vào message. Scrub credential trước khi đưa vào log.

---

## 8. Instrumentation với Micrometer

### 8.1. Đo một reactive component

Ví dụ wrapper đo thời gian của ReactiveJwtDecoder. Timer được tạo khi Publisher được subscribe, và dừng ở terminal signal:

~~~java
public final class TimedReactiveJwtDecoder
        implements ReactiveJwtDecoder {

    private final ReactiveJwtDecoder delegate;
    private final MeterRegistry registry;

    public TimedReactiveJwtDecoder(
            ReactiveJwtDecoder delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public Mono<Jwt> decode(String token) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return delegate.decode(token)
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "complete";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancelled";
                        default -> "other";
                    };

                    sample.stop(
                        registry.timer(
                            "security.jwt.decode",
                            "outcome", outcome
                        )
                    );
                });
        });
    }
}
~~~

Đoạn code dùng Java switch expression; nếu dự án chạy Java thấp hơn phiên bản hỗ trợ, thay bằng switch statement thông thường. Metric chỉ gắn label outcome có số lượng giá trị hữu hạn. Không thêm token hoặc subject vào tag.

Wrapper phải được đăng ký làm decoder mà Resource Server thực sự sử dụng. Nếu đo một bean không nằm trong security chain, metric sẽ không phản ánh request production.

### 8.2. Đo introspector

Có thể áp dụng cùng mẫu cho ReactiveOpaqueTokenIntrospector:

~~~java
public final class TimedOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final MeterRegistry registry;

    public TimedOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return delegate.introspect(token)
                .doFinally(signal -> {
                    String outcome = signal == SignalType.ON_ERROR
                        ? "error"
                        : signal == SignalType.CANCEL
                            ? "cancelled"
                            : "complete";

                    sample.stop(registry.timer(
                        "security.opaque.introspection",
                        "outcome", outcome
                    ));
                });
        });
    }
}
~~~

Trong production, phân biệt token inactive với lỗi AS/network bằng cách phân loại exception an toàn. Không gắn exception message vào metric tag. Nếu muốn ghi thêm metric cho timeout, hãy phân loại bằng loại exception hoặc error code ổn định.

### 8.3. Đo converter và authorization

Converter có thể được bọc tương tự, nhưng tránh instrument từng thao tác nhỏ nếu overhead lớn hơn giá trị thu được. Hãy bắt đầu với các boundary có ý nghĩa:

- JWT decode.
- Opaque introspection.
- Authority lookup.
- Tenant/permission check.
- Tổng authentication.
- Tổng authorization.
- Tổng HTTP request.

Nếu một request có nhiều lần authorization check, metric phải có tên/đơn vị rõ ràng để không nhầm “mỗi lần check” với “mỗi request”.

### 8.4. Đo bằng Observation

Spring/Micrometer Observation cho phép ghi nhận một operation với timer và tracing handler. Khi dự án đã dùng Observation convention, ưu tiên theo convention chung thay vì tạo một hệ thống metric riêng cho cùng một operation.

Một observation hữu ích có thể mang tên operation và outcome. Không thêm thông tin nhạy cảm hoặc label không giới hạn vào low-cardinality key values. Dùng high-cardinality tracing data chỉ khi backend và privacy policy cho phép, và tuyệt đối không đưa access token vào trace baggage.

---

## 9. Phân tích bottleneck qua dấu hiệu vận hành

| Dấu hiệu | Nguyên nhân có thể | Cách xác nhận |
|---|---|---|
| p95 JWT decode tăng cùng CPU | Signature verification, parsing hoặc validators tốn CPU | CPU profile, benchmark decoder |
| p99 tăng khi unknown kid | JWKS fetch, retry hoặc key rotation | Đo JWKS cache miss và fetch latency |
| Opaque introspection chậm nhưng CPU RS thấp | AS/network/pool wait | Đo outbound HTTP timing và pool pending |
| Latency tăng khi RPS vượt một ngưỡng | Saturation CPU, thread, pool hoặc AS | Load test ramp và theo dõi queue |
| WebFlux latency toàn app tăng cùng event-loop busy | Blocking call trên event loop | BlockHound, thread dump, profiler |
| Servlet active threads gần max | Request chờ downstream | Thread pool metrics và dependency latency |
| Authentication nhanh nhưng request vẫn chậm | Authorization/business/data access | Tách timer từng stage |
| 401 tăng khi rotate key | JWKS propagation/cache hoặc key overlap | Kiểm tra kid và JWKS response |
| Cache hit cao nhưng stale authorization | TTL/invalidation chưa phù hợp | So sánh revoke/change time với cache expiry |
| p99 cao khi introspection pool pending tăng | Connection pool nhỏ hoặc AS chậm | Pool acquire time, active connections |
| CPU thấp nhưng latency cao | I/O wait, queue hoặc lock contention | Distributed trace và queue metrics |
| Error rate tăng khi timeout được siết | Timeout budget không phù hợp | So sánh downstream latency distribution |

Một dashboard tốt phải cho phép so sánh cùng một time window: request latency, authentication latency, downstream dependency latency, RPS, error rate và saturation.

---

## 10. Thiết kế load test cho Resource Server

### 10.1. Mục đích test

Load test không chỉ nhằm tìm RPS cao nhất. Cần trả lời:

- p95/p99 là bao nhiêu ở mức traffic dự kiến?
- Khi nào throughput ngừng tăng dù concurrency tiếp tục tăng?
- CPU hay downstream dependency bão hòa trước?
- Tỷ lệ 401/403/5xx thay đổi thế nào?
- Cold start và JWKS refresh có tạo spike không?
- Introspection cache làm giảm tải AS bao nhiêu và tăng stale window bao nhiêu?
- Hệ thống hoạt động ra sao trong soak test dài?
- Khi AS/JWKS endpoint lỗi, Resource Server xử lý đúng policy không?

### 10.2. Các giai đoạn

Một kịch bản nên có:

1. **Warm-up:** làm nóng JVM/JIT, connection pool, DNS/TLS và JWK cache.
2. **Ramp-up:** tăng dần traffic để quan sát điểm bắt đầu bão hòa.
3. **Steady state:** giữ tải ổn định đủ lâu để lấy percentile đáng tin cậy.
4. **Burst:** tăng tải ngắn hạn để kiểm tra queue và autoscaling.
5. **Soak:** giữ tải lâu để phát hiện memory leak, cache growth, pool leak và GC pressure.
6. **Recovery:** giảm tải và quan sát thời gian hệ thống trở lại bình thường.

### 10.3. Tách workload

Không trộn tất cả loại request vào một nhóm rồi suy luận hiệu năng token:

| Workload | Điều cần đo |
|---|---|
| JWT warm key, token hợp lệ | Chi phí hot path |
| JWT cold key/JWKS miss | Chi phí fetch và refresh key |
| JWT sai signature/claim | Chi phí failure path |
| Opaque introspection active | Network và AS capacity |
| Opaque introspection inactive | Failure path |
| Cache hit/miss | Lợi ích và chi phí cache |
| Token có ít/nhiều claims | Parse và mapping |
| Authority lookup local/remote | Chi phí converter/policy |
| Thiếu scope | Authorization failure |
| Request business nặng | Tách security khỏi application cost |

Dùng token fixture hợp lệ và không hợp lệ được tạo trước. Tránh sinh key pair hoặc ký token trong chính script load test nếu mục tiêu là đo Resource Server; nếu làm vậy, client load generator trở thành bottleneck và kết quả không phản ánh server.

### 10.4. Ví dụ k6 cho JWT hot path

Ví dụ đơn giản gửi một access token test đã ký sẵn:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL;
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN;

export const options = {
  scenarios: {
    resource_server: {
      executor: 'constant-arrival-rate',
      rate: 500,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<700'],
  },
};

export default function () {
  const response = http.get(BASE_URL + '/api/orders/42', {
    headers: {
      Authorization: 'Bearer ' + ACCESS_TOKEN,
    },
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
~~~

Đây là mẫu workload, không phải ngưỡng hiệu năng áp dụng cho mọi hệ thống. Cấu hình scenario phải khớp mục tiêu RPS và năng lực load generator. Với constant-arrival-rate, k6 cố gắng duy trì tốc độ bắt đầu iteration; cần theo dõi dropped iterations và số VU thực tế.

Không truyền token production qua shell history, CI log hoặc source repository. Dùng secret injection cho test environment và token có quyền tối thiểu.

### 10.5. Test opaque introspection riêng

Kịch bản opaque token cần gửi token test hợp lệ qua endpoint Resource Server có introspector thật/stub. Đo đồng thời:

- HTTP duration ở Resource Server.
- Introspection timer.
- AS request rate.
- Pool active/pending.
- AS latency và error rate.
- Cache hit ratio nếu có.

Nếu Resource Server đạt 500 RPS nhưng AS chỉ xử lý được 200 introspection RPS, kết quả có thể đến từ cache hoặc request fail. Hãy đối chiếu success rate và số lần gọi introspection thực tế.

### 10.6. Đảm bảo load generator không phải bottleneck

Một máy phát tải có thể hết CPU, socket hoặc ephemeral ports trước Resource Server. Dấu hiệu gồm CPU generator cao, dropped iteration, latency phía client tăng nhưng server không có tải tương ứng.

Có thể chạy nhiều load generator, dùng mạng đủ năng lực và so sánh server-side request rate với client-side iteration rate. Không kết luận server chỉ dựa trên số liệu của một máy phát tải.

---

## 11. Throughput, concurrency và Little's Law

Little's Law mô tả mối quan hệ giữa số request trung bình đang ở trong hệ thống, throughput và thời gian ở trong hệ thống:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số request trung bình đang được xử lý hoặc chờ.
- \(\lambda\): throughput trung bình (request/second).
- \(W\): thời gian trung bình trong hệ thống (second).

Ví dụ: nếu hệ thống xử lý 400 RPS và thời gian trung bình là 0,1 giây:

\[
L = 400 \times 0.1 = 40
\]

Trung bình có khoảng 40 request đang ở trong hệ thống. Nếu latency tăng lên 0,5 giây mà throughput vẫn là 400 RPS:

\[
L = 400 \times 0.5 = 200
\]

Số request đồng thời trung bình tăng lên 200. Điều đó kéo theo nhu cầu về request slots, connection pool, memory và queue.

Little's Law áp dụng cho hệ thống ổn định và số liệu trung bình trong cùng boundary. Không lấy p99 nhân với RPS rồi coi đó là concurrency chính xác.

### 11.1. Tăng concurrency không luôn tăng throughput

Ban đầu tăng concurrency có thể giúp tận dụng CPU và I/O. Khi đã đạt capacity:

- CPU queue tăng.
- Connection pool pending tăng.
- Thread pool queue tăng.
- GC pause và context switching tăng.
- AS/database bị quá tải.
- Latency p95/p99 tăng nhanh.
- Throughput hữu ích có thể đi ngang hoặc giảm.

Đây là điểm bão hòa. Mục tiêu vận hành thường là giữ traffic dưới vùng latency bắt đầu tăng dốc, đồng thời có headroom cho burst và node failure.

### 11.2. Phân biệt latency service và latency end-to-end

Client đo end-to-end có thể bao gồm DNS, TCP, TLS, gateway, network và server. Server timer chỉ đo từ khi request đến một boundary nhất định.

Khi so sánh, phải ghi rõ boundary:

- Client-side request duration.
- Gateway upstream duration.
- Resource Server HTTP duration.
- Authentication component duration.
- AS introspection duration.

Nếu các boundary khác nhau, số liệu không thể so sánh trực tiếp.

---

## 12. Tối ưu hiệu năng theo thứ tự hợp lý

### 12.1. Đo trước khi tối ưu

Bắt đầu với baseline:

- RPS và concurrency.
- p50/p95/p99 của request.
- p50/p95/p99 của authentication.
- CPU, heap, GC.
- Connection pool và thread/event-loop metrics.
- JWKS fetch và introspection latency.
- Error rate và status distribution.

Lưu lại phiên bản ứng dụng, JDK, CPU/memory limit, token type, thuật toán ký, cache settings và workload. Nếu không cố định các yếu tố này, benchmark trước/sau khó có ý nghĩa.

### 12.2. Giảm network call trên hot path

Nếu mỗi request gọi introspection hoặc permission service:

- Kiểm tra có thể dùng JWT validation cục bộ không, nếu threat model và revocation policy cho phép.
- Dùng connection reuse và pool đúng kích thước.
- Đặt service gần nhau về network/region.
- Dùng cache có TTL theo freshness requirement.
- Gộp các lookup quyền nếu có thể mà không tạo query quá lớn.
- Loại bỏ request phụ không cần thiết trong converter.

### 12.3. Giữ decoder và client dùng chung

Không khởi tạo JwtDecoder, WebClient, HTTP client hoặc connection pool cho từng request. Các component này nên có lifecycle được quản lý và được reuse.

Tạo client mới cho từng request có thể làm mất connection reuse, tăng TLS handshake, DNS lookup và allocation. Tạo decoder mới liên tục cũng có thể làm mất JWK cache.

### 12.4. Tối giản token claims có chủ đích

JWT chứa quá nhiều claims làm tăng:

- Kích thước request header.
- Chi phí truyền tải và parse.
- Memory allocation.
- Số lượng mapping cần thực hiện.
- Rủi ro vượt giới hạn header ở proxy/server.

Chỉ đưa claims cần thiết cho Resource Server. Không biến JWT thành bản sao toàn bộ profile hoặc permission database.

Không loại bỏ claim bắt buộc cho security policy chỉ để giảm vài byte. Tối ưu phải giữ issuer, audience, expiry, scope và binding cần thiết.

### 12.5. Giữ converter nhẹ

Converter nên chủ yếu map claim đã xác minh thành Authentication/GrantedAuthority. Nếu cần gọi service từ xa, hãy đo riêng và cân nhắc cache hoặc chuyển lookup sang authorization boundary.

Không thực hiện công việc nặng như gọi nhiều service tuần tự, đọc profile đầy đủ hoặc tải toàn bộ ACL nếu endpoint không cần chúng.

### 12.6. Tránh blocking trong WebFlux

Các lời gọi blocking có thể làm event-loop thread bị chiếm. Dùng reactive driver/client, và kiểm tra bằng profiler hoặc BlockHound trong test phù hợp.

Nếu có đoạn blocking bắt buộc, cách ly bằng scheduler bounded phù hợp, đặt concurrency/queue limit và timeout. Không dùng scheduler mặc định như một kho chứa vô hạn cho blocking work.

### 12.7. Tối ưu crypto sau khi có bằng chứng

Nếu CPU profile cho thấy signature verification là bottleneck:

- Benchmark thuật toán/key size được AS hỗ trợ.
- Kiểm tra JDK và crypto provider.
- Kiểm tra CPU instruction support.
- Tránh parse/convert token lặp lại không cần thiết.
- Giữ key/JWK cache đúng lifecycle.
- Scale Resource Server theo CPU khi workload thực sự CPU-bound.

Không tự giảm key size hoặc nới lỏng thuật toán allowlist để đạt RPS. Mọi thay đổi crypto phải đáp ứng security baseline.

---

## 13. Hiệu năng khi có nhiều loại request và token

### 13.1. Token hợp lệ và token không hợp lệ có cost khác nhau

Token sai format có thể bị từ chối sớm khi parse. Token có format đúng nhưng signature sai vẫn phải thực hiện một phần crypto verification. Token hợp lệ sẽ tiếp tục chạy validators, converter và authorization.

Vì vậy, không benchmark chỉ bằng một loại invalid token rồi suy ra throughput cho traffic hợp lệ.

### 13.2. 401 và 403 có đường đi khác nhau

- **401 Unauthorized:** thường là chưa xác thực được, ví dụ thiếu token, token hết hạn, sai chữ ký hoặc introspection không active.
- **403 Forbidden:** Authentication đã thành công nhưng không đủ authority/policy.

Nếu 403 request còn chạy tenant lookup hoặc object authorization, cost có thể cao hơn một 401 bị từ chối sớm. Tách metric theo outcome để hiểu phân phối.

### 13.3. Method security có thể thêm chi phí

Các annotation method security có thể thực hiện kiểm tra bổ sung khi gọi service method. Nếu cùng một quyền đã được kiểm tra ở filter chain rồi lại được kiểm tra ở nhiều tầng, cần xác định mục đích từng lớp.

Không bỏ method security chỉ để giảm latency nếu nó là lớp bảo vệ quan trọng. Thay vào đó, tránh truy vấn lặp, cache dữ liệu quyền đúng cách và thiết kế policy boundary rõ.

### 13.4. Request có nhiều lần gọi service

Một request có thể gọi permission service, tenant service, repository và downstream API. Nếu gọi tuần tự, tổng latency có thể là tổng các round trip. Nếu độc lập và được gọi song song, latency có thể gần với bước chậm nhất nhưng concurrency/load lên downstream tăng.

Không song song hóa các kiểm tra nếu có phụ thuộc dữ liệu hoặc nếu điều đó tạo tải đột biến. Hãy dùng trace để xác định critical path.

---

## 14. Resilience khi Authorization Server hoặc JWKS endpoint chậm

### 14.1. JWT đã có key và JWKS endpoint lỗi

Nếu Resource Server đã có public key hợp lệ trong cache, nó thường vẫn có thể xác minh token bằng key đó khi JWKS endpoint tạm thời lỗi. Nhưng khi token dùng key mới chưa có trong cache, decoder có thể không xác minh được.

Cần kiểm thử:

- Key đã cache, JWKS endpoint down.
- Token mới dùng unknown kid, JWKS endpoint down.
- JWKS response chậm.
- Key rotation trong lúc nhiều request đến.
- Cache refresh và retry behavior.

Không dùng key cũ vô thời hạn chỉ để duy trì availability; key bị compromise cần được loại bỏ theo quy trình khẩn cấp.

### 14.2. Opaque introspection endpoint lỗi

Nếu AS không phản hồi, RS không biết token còn active hay không. Không được chuyển lỗi timeout thành active=true hoặc cấp Authentication mặc định.

Các lựa chọn vận hành:

- Fail closed khi không xác minh được token.
- Cache active response trong một TTL ngắn được policy cho phép.
- Dùng circuit breaker để tránh dồn request vào AS đang lỗi.
- Giới hạn concurrency và timeout.
- Phát cảnh báo khi AS error rate hoặc latency vượt ngưỡng.
- Phân biệt inactive token với AS unavailable.

Circuit breaker không được biến dependency failure thành quyền truy cập. Fallback phải tuân theo security policy; đối với token chưa được xác minh, fallback thường là từ chối.

### 14.3. Stale cache và revocation

Cache có thể tăng availability nhưng làm chậm việc nhận biết token bị revoke. Ghi rõ:

- TTL tối đa.
- Cách invalidation.
- Thời gian propagation giữa các node.
- Hành vi khi cache backend lỗi.
- Policy cho token có quyền cao.
- Thời gian access token còn hiệu lực.

Đây là trade-off bảo mật/hiệu năng phải được phê duyệt ở cấp policy, không chỉ là tuning kỹ thuật.

---

## 15. Ví dụ đọc một kết quả benchmark

Giả sử một lần thử nghiệm có số liệu:

| Kịch bản | RPS thành công | p50 request | p95 request | p99 request | p95 authentication |
|---|---:|---:|---:|---:|---:|
| JWT, warm JWK cache | 1.200 | 28 ms | 75 ms | 140 ms | 4 ms |
| JWT, JWKS miss thường xuyên | 700 | 45 ms | 210 ms | 900 ms | 90 ms |
| Opaque, introspection trực tiếp | 350 | 85 ms | 260 ms | 700 ms | 65 ms |
| Opaque, cache TTL 20 giây | 900 | 35 ms | 100 ms | 230 ms | 8 ms |

Các số trên là dữ liệu giả định để minh họa cách đọc bảng, không phải benchmark chuẩn của Spring Security.

Có thể rút ra các câu hỏi cần điều tra:

- JWT warm path có authentication p95 thấp; phần còn lại của request có thể nằm ở application hoặc network.
- JWT JWKS miss thường xuyên làm p99 tăng mạnh; cần xem key cache/rotation và JWKS dependency.
- Opaque introspection trực tiếp có authentication p95 cao; cần đo AS, pool wait và network.
- Opaque cache cải thiện latency nhưng phải đánh giá cửa sổ stale sau revoke.
- RPS cao hơn không đủ để kết luận tốt hơn nếu error rate, stale authorization hoặc memory cost tăng.

Không dùng một bảng giả định để đặt SLA production. Benchmark thật cần lặp lại trên cùng phần cứng, cùng phiên bản và cùng workload.

---

## 16. Checklist vận hành

### 16.1. Trước khi triển khai

- [ ] Định nghĩa latency SLO cho toàn request và authentication.
- [ ] Xác định JWT hay opaque token và policy revocation.
- [ ] Kiểm tra JWK cache, refresh và key rotation.
- [ ] Đặt timeout cho JWKS, introspection và permission services.
- [ ] Cấu hình connection pool dùng chung.
- [ ] Kiểm tra không có blocking I/O trên WebFlux event loop.
- [ ] Giới hạn cache TTL theo freshness requirement.
- [ ] Xác định failure policy khi AS hoặc cache backend lỗi.
- [ ] Bảo đảm metric label không chứa token/user ID.
- [ ] Chuẩn bị workload hợp lệ, invalid và cold/warm path.

### 16.2. Trong khi chạy production

- [ ] Theo dõi p50/p95/p99 của HTTP và authentication.
- [ ] Theo dõi RPS thành công, 401/403/5xx và timeout.
- [ ] Theo dõi CPU, heap, GC, thread và event-loop utilization.
- [ ] Theo dõi JWK cache miss và JWKS fetch latency.
- [ ] Theo dõi introspection latency, error và pool pending.
- [ ] Theo dõi converter/permission lookup duration.
- [ ] Theo dõi cache hit ratio, eviction và stale window.
- [ ] Cảnh báo khi tail latency tăng hoặc throughput giảm.
- [ ] Không log access token, refresh token, client secret hoặc DPoP proof.

### 16.3. Khi latency tăng đột ngột

1. Xác định thời điểm bắt đầu và route/token type bị ảnh hưởng.
2. So sánh HTTP latency với authentication latency.
3. Kiểm tra RPS, error rate và saturation cùng thời điểm.
4. Nếu JWT: kiểm tra CPU, JWK cache miss, key rotation và signature failures.
5. Nếu opaque: kiểm tra AS latency, connection pool, timeout và introspection rate.
6. Nếu converter/authorization: kiểm tra role/tenant service và query latency.
7. Nếu WebFlux: tìm blocking call, event-loop saturation và scheduler queue.
8. Nếu chỉ p99 tăng: kiểm tra queueing, retry, GC pause, lock contention và cold path.
9. Thực hiện một thay đổi có kiểm soát và đo lại trên cùng workload.
10. Xác nhận không làm suy yếu token validation hoặc revocation policy.

---

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Latency khác throughput như thế nào?

**Trả lời:** Latency là thời gian một request đi qua boundary được đo; throughput là số request xử lý mỗi giây. Hệ thống có thể tăng RPS nhưng đồng thời làm p95/p99 xấu đi nếu đã gần saturation.

**Câu 2.** Vì sao JWT thường không cần gọi AS cho mỗi request?

**Trả lời:** Resource Server có thể xác minh chữ ký cục bộ bằng public key đã tải từ JWKS và cache. AS/JWKS chỉ cần được gọi khi cần metadata/key hoặc refresh theo policy.

**Câu 3.** JWKS cache miss ảnh hưởng gì?

**Trả lời:** Decoder có thể phải thực hiện network call để tải JWK Set, tạo cold-path latency cao hơn warm path. Nếu nhiều request cùng miss, có thể tạo spike lên AS.

**Câu 4.** Opaque introspection tạo thêm chi phí gì?

**Trả lời:** Thường có network round trip, connection acquisition, TLS/HTTP processing và thời gian xử lý ở Authorization Server.

**Câu 5.** Cache introspection active=true có rủi ro gì?

**Trả lời:** Token bị revoke sau cache hit vẫn có thể được coi là active cho tới khi cache hết hạn hoặc bị invalidate. TTL là một phần của revocation policy.

**Câu 6.** Vì sao cần đo p95 và p99?

**Trả lời:** Average có thể che giấu nhóm request rất chậm. Percentile cho thấy tail latency mà một phần người dùng thực sự gặp.

**Câu 7.** Tại sao không cộng mọi timer lại?

**Trả lời:** Timer có thể lồng nhau. HTTP duration đã chứa security và application duration; cộng chúng sẽ đếm thời gian nhiều lần.

**Câu 8.** WebFlux có bảo đảm throughput vô hạn không?

**Trả lời:** Không. Reactive giúp quản lý I/O bất đồng bộ, nhưng CPU, connection pool, downstream capacity và concurrency vẫn hữu hạn. Blocking call còn có thể làm nghẽn event loop.

**Câu 9.** Little's Law biểu diễn điều gì?

**Trả lời:** Số request trung bình trong hệ thống bằng throughput trung bình nhân với thời gian trung bình trong hệ thống, với điều kiện hệ thống ổn định và cùng boundary đo.

**Câu 10.** Vì sao không dùng subject làm metric tag?

**Trả lời:** Subject tạo cardinality rất lớn và có thể là dữ liệu định danh. Metric label nên là dimension giới hạn như operation hoặc outcome.

**Câu 11.** Converter gọi role service có thể chậm hơn JWT verification không?

**Trả lời:** Có. Một network/database round trip thường có thể chiếm nhiều thời gian hơn parse và signature verification trong bộ nhớ. Cần đo riêng converter và lookup.

**Câu 12.** Khi introspection timeout, Resource Server có nên cấp Authentication từ cache bất kỳ không?

**Trả lời:** Chỉ khi có một cache policy đã được thiết kế và phê duyệt với TTL/freshness rõ ràng. Không được mặc định chuyển timeout thành active=true hoặc principal mặc định.

**Câu 13.** Vì sao cần cold-path và warm-path benchmark?

**Trả lời:** Cold path có thể phải tải JWKS, tạo kết nối hoặc làm nóng JIT; warm path dùng cache và connection đã sẵn sàng. Production trải qua cả hai trạng thái.

**Câu 14.** Tăng thread pool hoặc connection pool có luôn tăng throughput không?

**Trả lời:** Không. Quá nhiều thread/connection có thể tăng context switching, memory, contention và tải lên downstream. Cần tìm capacity thực tế bằng load test.

**Câu 15.** Làm sao biết bottleneck ở authentication hay business logic?

**Trả lời:** Đo riêng decoder/introspection, converter, authorization, controller/repository và toàn HTTP request; so sánh chúng trên cùng trace/time window.

---

## 18. Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reactive JWT decoder, validation và authentication converter.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque token và introspection.
- [Spring Security — Reactive Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): ReactiveOpaqueTokenIntrospector và WebFlux integration.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, JWK Set, JWT validation và key retrieval.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics và application instrumentation.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer, histogram và percentile concepts.
- [Reactor Reference — Testing and instrumentation](https://projectreactor.io/docs/core/release/reference/): reactive pipeline, scheduler và instrumentation.
- [k6 — Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/): mô hình load test và arrival-rate executor.
- [Little's Law](https://en.wikipedia.org/wiki/Little%27s_law): quan hệ giữa throughput, thời gian trong hệ thống và concurrency.

Hãy kiểm tra tài liệu đúng phiên bản Spring Security, Spring Boot, Micrometer và Reactor mà dự án đang dùng. Tên metric mặc định và hành vi instrumentation có thể thay đổi theo phiên bản, cấu hình và observation convention.

## 19. Ghi nhớ

Thời gian xác thực là một phần của request latency. Để tối ưu Resource Server, hãy đo tách biệt JWT decode, JWKS lookup, opaque introspection, Authentication conversion, authorization và business logic.

- **JWT:** hot path thường xác minh chữ ký cục bộ bằng JWK đã cache; cold path hoặc key rotation có thể phát sinh fetch.
- **Opaque token:** introspection thường thêm network dependency; cache giảm latency nhưng kéo dài cửa sổ nhận biết revocation.
- **WebFlux/Servlet:** reactive không loại bỏ giới hạn CPU, pool và downstream; blocking call trong event loop có thể làm latency tăng toàn ứng dụng.
- **Đo lường:** dùng p50/p95/p99, RPS thành công, error rate, saturation và timer theo từng boundary.
- **Tối ưu:** đo trước, giữ decoder/client dùng chung, giảm network call không cần thiết, đặt timeout/concurrency hợp lý và không nới lỏng security validation.
- **Vận hành:** quan sát cold/warm path, key rotation, AS outage, cache freshness và tail latency; không đưa credential vào logs hoặc metric labels.

Một Resource Server nhanh cần xử lý token hiệu quả, nhưng vẫn phải giữ đúng issuer, audience, signature, expiry, scope, quyền trên tài nguyên và policy thu hồi.
