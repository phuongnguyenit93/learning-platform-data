# Dữ liệu cũ do cache, Vary hoặc đọc replica

## 1. Triệu chứng: ghi thành công nhưng GET vẫn trả trạng thái trước đó

Trong module **INTEGRATION_API_REST**, API có thể tuân thủ URI, phương thức và status HTTP mà người dùng vẫn thấy **dữ liệu cũ**. Đây là nhóm sự cố khó phân biệt vì nhiều tầng có thể trả cùng JSON/status: browser cache, CDN/gateway, cache ứng dụng, Redis, ORM cache hoặc **read replica** của database.

Ví dụ một Order API đa tenant sử dụng **Spring Boot 3, Spring Security, PostgreSQL primary/replicas** và Redis:

- **PATCH /api/v1/orders/{id}** có If-Match, trả **200** với trạng thái PAID và ETag mới sau khi transaction commit.
- Ngay sau đó, **GET /api/v1/orders/{id}** trả **200** với trạng thái CREATED, hoặc **304 Not Modified** dù client kỳ vọng dữ liệu mới.
- Một thiết bị thấy PAID, thiết bị khác thấy CREATED; đôi khi tải lại trang mạnh hoặc đợi vài giây thì hết lỗi.
- Một số người dùng chỉ gặp lỗi trên trình duyệt, người khác chỉ gặp lỗi khi đọc qua khu vực/replica nhất định.

**Mục tiêu bài học:** tìm đúng nguồn stale data, hiểu **Cache-Control / Age / Vary / ETag / 304**, sửa cache key và invalidation, nhận biết replica lag và consistency guarantee, triển khai các guardrails bằng Java/Spring, bảo vệ quyền theo tenant, thiết kế kiểm thử và runbook phục hồi.

**Nguyên tắc:** đừng xóa hết cache hoặc tắt replicas theo phản xạ. Trước tiên phải trả lời: **request nào nhận representation nào, do tầng nào sinh ra, với validator/variant nào và dữ liệu nguồn tại thời điểm ấy là gì?**

### 1.1. Dữ liệu cũ và tính nhất quán không đồng nghĩa dữ liệu sai quyền

Có thể có ba vấn đề độc lập:

1. **Freshness:** trả phiên bản cũ của cùng resource dù đã có version mới.
2. **Consistency:** client cần *read-your-writes*, *monotonic reads* hoặc chỉ *eventual consistency*; hệ thống đang đáp ứng hay vi phạm mức đã cam kết?
3. **Authorization:** dù snapshot còn trong cache, caller **phải có quyền hiện tại** để đọc. Cache stale có thể trở thành sự cố an ninh nếu dữ liệu đã bị thu hồi quyền.

Một lỗi 200 stale khác với **409 conflict** hoặc **412 Precondition Failed** khi client ghi dựa trên revision cũ. Không gộp các tình huống dưới cùng nhãn "cache lỗi".

## 2. Bản đồ đường đi của một GET

~~~mermaid
flowchart LR
    B[Browser / Mobile] --> C[Browser HTTP cache]
    C --> G[CDN / reverse proxy / API gateway]
    G --> S[Spring Security + Controller]
    S --> A[App cache / Redis]
    A --> P[(PostgreSQL primary)]
    A --> R[(Read replica)]
    P -. WAL replication .-> R
~~~

Sơ đồ cho thấy các nơi có thể có dữ liệu cũ, không có nghĩa mọi request đi qua đủ các tầng. Một request có thể **không tới server** vì browser cache còn fresh; CDN có thể trả cached response; Spring có thể trả từ Redis; cuối cùng một cache miss vẫn có thể đọc replica chưa replay xong.

| Tầng | Dấu hiệu thường gặp | Cách xác minh |
| --- | --- | --- |
| **Browser cache / service worker** | Reload/tab/device khác cho kết quả khác; backend không thấy request | DevTools Network/Service Worker, cache mode, timing |
| **CDN/gateway** | Chỉ qua domain public bị stale, gọi trực tiếp backend đã mới | Age, Via, provider-specific cache status, edge logs |
| **Spring / Redis / ORM cache** | Có request vào app nhưng không phát SQL mới | Cache hit metrics, trace spans, key + TTL + version |
| **Read replica** | Cache bypass vẫn cũ, primary đúng; sau vài giây tự mới | DB endpoint, transaction LSN/replay lag, query trên primary và replica |
| **Search index / materialized view** | Chi tiết order mới nhưng list/search vẫn cũ | Indexing/outbox lag, refresh policy, query source |

**Nguồn sự thật** phải được xác định theo operation. Đối với đơn hàng, thường là transaction **đã commit trên primary**. Một 200 từ replica chưa đồng bộ không có nghĩa primary đã mất dữ liệu.

### 2.1. Timeline quan trọng hơn thời điểm quan sát chung chung

~~~text
T0: primary có order v7 = CREATED
T1: PATCH v7 -> v8 bắt đầu
T2: primary COMMIT order v8 = PAID
T3: client GET order, mong thấy ít nhất v8
T4: replica mới replay được v8
T5: HTTP/CDN/app cache v7 hết hạn hoặc bị invalidated
~~~

Nếu T3 nằm trước T4, đọc replica có thể trả v7. Nếu cache v7 vẫn được phép dùng đến T5, ngay cả primary đã cập nhật và replica đã bắt kịp thì client vẫn có thể thấy v7. Vì thế cần lưu **revision, cache state, datasource identity và các mốc commit/replay** trong trace chẩn đoán.

## 3. Phân biệt stale từ HTTP cache và stale từ dữ liệu nguồn

Một HTTP cache quyết định reuse representation theo **freshness lifetime, age, validation và response directives**. Database replica quyết định dữ liệu nào đã được replay theo **replication progress**. Hai cơ chế độc lập.

Ví dụ một cache được phép giữ response 60 giây:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: "order-v7"
Vary: Accept-Encoding
Date: Wed, 18 Nov 2026 08:00:00 GMT

{"id":"...","status":"CREATED","version":7}
~~~

Sau PATCH đã commit v8 nhưng chưa có invalidation, CDN có thể vẫn trả v7 trong freshness lifetime. Nếu response cacheable theo hợp đồng, đây có thể là **hành vi cache đúng cấu hình nhưng không đáp ứng yêu cầu read-after-write của sản phẩm**. Không thể sửa chỉ bằng cách tăng replication speed.

Trong chiều ngược lại, GET từ replica v7 có thể được origin trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
ETag: "order-v7"

{"id":"...","status":"CREATED","version":7}
~~~

Đây vẫn là dữ liệu cũ dù **HTTP caching đã bị cấm**. No-store không khiến replica cập nhật nhanh hơn; nó chỉ quy định việc HTTP caches không lưu response theo chuẩn.

**Chẩn đoán luôn tách hai câu hỏi:** response có được *reuse từ cache* không, và nếu được tạo mới thì datasource/app đã đọc *phiên bản dữ liệu nào*?

## 4. Cache-Control: tránh hiểu sai no-cache, no-store và stale directives

| Directive | Ý nghĩa chính | Không có nghĩa |
| --- | --- | --- |
| **no-store** | HTTP cache không được lưu response/request theo yêu cầu của directive | Không tắt Redis/JPA cache hoặc replica |
| **no-cache** | Có thể lưu nhưng phải revalidate với origin trước khi reuse | Không đồng nghĩa "không cache" |
| **private** | Chỉ private cache (ví dụ browser), shared cache không được lưu | Không cấp quyền xem dữ liệu cho người khác |
| **public** | Cho phép shared caching nếu các điều kiện khác phù hợp | Không làm dữ liệu cá nhân trở thành công khai |
| **max-age=60** | Freshness lifetime 60 giây cho response theo ngữ cảnh | Không phải Redis TTL hay thời gian replica lag |
| **s-maxage=30** | Freshness riêng cho shared caches, thường ưu tiên so max-age | Không bảo đảm mọi CDN cấu hình giữ đúng 30s |
| **must-revalidate** | Khi stale, cache phải revalidate; không được reuse tùy tiện khi mất kết nối | Không có nghĩa origin sẽ luôn trả dữ liệu mới |
| **stale-while-revalidate=30** | Cache hỗ trợ có thể phục vụ stale trong cửa sổ được chỉ định khi tái xác minh | Không áp cho mọi cache/client như nhau |
| **stale-if-error=60** | Cache hỗ trợ có thể dùng stale trong cửa sổ khi gặp lỗi cho phép | Không thể bỏ ACL, kiểm giá hay policy dữ liệu |

**stale-while-revalidate** và **stale-if-error** được định nghĩa trong RFC 5861; việc hỗ trợ và giới hạn phụ thuộc cache. Không dùng chúng vô điều kiện cho **giá hiện hành, tình trạng thanh toán, consent hoặc dữ liệu đã bị thu hồi quyền**. Với dữ liệu riêng tư đặc biệt nhạy cảm, thường chọn:

~~~http
Cache-Control: private, no-store
~~~

Với trang catalog công khai có thể chịu stale trong 60 giây, một chính sách hợp lệ hơn là:

~~~http
Cache-Control: public, max-age=60, stale-while-revalidate=30
~~~

Đó là **quyết định nghiệp vụ**. Nếu endpoint có JWT, thông tin tenant hoặc giá tùy vai trò, **không copy policy public** từ catalog sang order chỉ vì muốn giảm tải.

### 4.1. Age, Date và cache status

- **Age** ước lượng tuổi response theo cơ chế HTTP cache (seconds). Age lớn giúp nghi ngờ cache, nhưng **Age vắng mặt không chứng minh cache miss**.
- **Date** là thời gian tạo HTTP message theo nguồn; không thay timestamp commit DB.
- **Via** hoặc headers như **X-Cache, CF-Cache-Status, CDN-Cache-Status** có thể giúp xác định proxy; tên/semantics khác nhau theo provider.
- **Cache-Control** chỉ ra policy; để xác minh có hit thật cần log cache và trace origin.
- Một CDN có cấu hình override/force cache có thể khiến production hành xử khác contract; kiểm effective policy thực trên gateway/edge.

**Không dùng các header chẩn đoán nhạy cảm** để công bố nội bộ cho mọi caller; bật có kiểm soát, hoặc ghi vào trace/log nội bộ theo request ID.

## 5. Vary: khi cùng URL có nhiều representation

**Vary** nói với cache rằng một response còn phụ thuộc vào các **request header** bên cạnh URL. Nếu bỏ thiếu chiều biến thể, cache có thể reuse sai response cho request có headers khác.

~~~http
GET /api/v1/catalog HTTP/1.1
Accept-Language: vi
Accept-Encoding: gzip
~~~

~~~http
HTTP/1.1 200 OK
Content-Language: vi
Content-Encoding: gzip
Vary: Accept-Language, Accept-Encoding
Cache-Control: public, max-age=60

(compressed Vietnamese JSON)
~~~

Với request tiếng Anh, cache không được reuse response tiếng Việt chỉ vì URL giống nhau. Với Accept-Encoding: identity, cache cũng không được đưa bytes gzip khi client không chấp nhận gzip.

### 5.1. Những biến thể phổ biến

| Representation thay đổi theo | Cách tách variant |
| --- | --- |
| **Accept-Encoding** | Vary: Accept-Encoding |
| **Accept-Language** | Vary: Accept-Language |
| **Accept** (JSON/CSV/media profile) | Vary: Accept |
| **Origin** khi CORS phản hồi ACAO động | Vary: Origin; preflight còn xét Access-Control-Request-* |
| **X-Fields** nếu fieldset nằm trong header | Vary: X-Fields |
| **Query fields, limit, cursor, locale** | Query string vốn là phần của cache key; canonicalize đúng |
| **Authorization, tenant, user role** | Không chỉ dựa vào Vary: Authorization để cache dữ liệu riêng trên shared CDN; ưu tiên private/no-store và cache partition an toàn |

Ví dụ CDN trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Vary Origin bảo vệ selection của **CORS response headers**; bản thân nó không thực thi quyền đọc resource. Đối với preflight còn cần cache xét **Access-Control-Request-Method** và **Access-Control-Request-Headers** theo chính sách CORS.

### 5.2. Vary thiếu và cache key sai có biểu hiện tương tự

Nếu backend gửi đúng Vary nhưng CDN custom cache key **loại bỏ Accept-Language**, cache vẫn có thể bị reuse sai do cấu hình edge. Nếu field selector là **?fields=id,name**, cache phải phân biệt URI query; Vary không tự sửa key bỏ query.

Điều kiện cần kiểm:

1. Log **normalized URL + query** của request cache lookup.
2. Log **Vary response** và giá trị tương ứng của request headers được dùng làm cache variant.
3. Kiểm cấu hình CDN **cache key overrides**, query normalization, cookie forwarding, header stripping.
4. So expected representation version, language, content coding, projection và tenant scope.
5. Kiểm response **200, 304, 401/403 và 5xx** có bị cache nhầm hoặc bị rewrite headers không.

**Vary không tự bảo vệ dữ liệu bí mật.** Nếu shared cache có thể lưu response của user A, thêm Vary Origin không ngăn user B cùng origin nhận body của A.

## 6. ETag, If-None-Match và lỗi 304 không đúng thời điểm

Một cache có thể revalidate representation bằng **If-None-Match**:

~~~http
GET /api/v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <token>
If-None-Match: "order-v7"
~~~

Nếu origin nhìn thấy **v8**, nó không nên trả 304 cho validator v7:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v8"
Cache-Control: private, no-cache

{"id":"11111111-1111-4111-8111-111111111111",
 "status":"PAID","version":8}
~~~

**304 Not Modified** chỉ đúng khi preconditions phù hợp với **selected representation hiện tại**, request đã vượt authentication/authorization và không có thay đổi cần trả body. Nếu origin lấy **v7 từ replica**, nó có thể trả 304 đối với If-None-Match v7 **dù primary đã commit v8**. Đây là **triệu chứng replica freshness**, không nhất thiết là lỗi parser ETag.

### 6.1. ETag mạnh, yếu và nguồn tạo validator

- **Strong ETag** đại diện cho selected representation theo yêu cầu so khớp mạnh; đổi bytes/projection/content-coding có thể đòi validator khác.
- **Weak ETag** dùng tiền tố W/ cho tương đương ngữ nghĩa; If-None-Match áp **weak comparison**, còn If-Match yêu cầu **strong comparison**.
- **Last-Modified / If-Modified-Since** có độ phân giải thời gian hạn chế; nhiều writes trong một giây có thể khiến test khó phát hiện thay đổi hơn ETag version.
- ETag tạo chỉ từ **primary business version** nhưng body lấy từ **replica stale** có thể không khớp. Validator và JSON phải được tính từ **cùng snapshot/representation được chọn**.
- **304 không chứa message body**; cache có thể dùng stored representation, nên 304 sai có thể khiến client tiếp tục hiển thị v7 rất lâu.

**Một test quan trọng:** GET order v7 lấy ETag, PATCH có If-Match v7 thành công tạo v8; GET có If-None-Match v7 sau đó **phải trả 200 v8** nếu API hứa read-your-writes. Đừng chỉ assert server trả ETag string khác mà không kiểm status/body/transaction đã commit.

### 6.2. Không lấy 304 làm bằng chứng đã đọc primary

Với ứng dụng có replica, ETag response v7 và 304 có thể hoàn toàn nhất quán **trên replica** nhưng không đủ mới so với primary. Khi buộc phải đọc dữ liệu vừa ghi, route request hoặc conditional validation đến nguồn có consistency phù hợp; không có header cache nào ép PostgreSQL replica catch up tức thời.

## 7. Cache ứng dụng và Redis: những lỗi phổ biến

Ngay cả khi gửi **Cache-Control: no-store**, service vẫn có thể dùng Redis:

~~~text
HTTP GET -> Spring @Cacheable / Redis key -> cached order v7
                                                |
                                         Primary DB v8
~~~

Nguyên nhân thường gặp:

- **Cache key thiếu tenant/user/permission/projection**: không chỉ stale, có thể rò dữ liệu.
- **Evict sai key** hoặc evict trước commit: transaction rollback/retry làm cache và DB lệch.
- **Invalidate đúng rồi repopulate từ replica stale**: v7 được cache lại sau khi primary đã v8.
- **TTL quá dài** so với freshness/consistency policy.
- **Concurrent read/write race**: request cũ tải v7 sau đó ghi đè cache vừa được invalidate.
- **Local in-memory cache trên nhiều pods**: invalidation chỉ tới một pod.
- **Negative cache** (404/empty collection) còn sống sau khi resource vừa được tạo.
- **Serialization schema/version** thay đổi nhưng Redis vẫn giữ DTO cũ.

### 7.1. Tránh cache key chỉ theo ID

Ví dụ logic nguy hiểm:

~~~java
@Cacheable(cacheNames = "orders", key = "#id")
public OrderDto find(UUID id) {
    // Nếu phương thức này phụ thuộc caller nhưng key chỉ là ID,
    // kết quả đã authorize của một caller có thể bị dùng cho caller khác.
}
~~~

Nếu cache chứa dữ liệu **đã được phân quyền/ẩn field theo caller**, key phải phản ánh phạm vi đó hoặc thiết kế an toàn hơn là **cache dữ liệu nội bộ không nhạy cảm theo tenant + version, kiểm ACL ở mỗi request trước khi projection**. Key không phải cơ chế authorization; quyền có thể bị thu hồi sau lúc cache ghi. Không lưu raw bearer token trong key/log.

Ví dụ key conceptual: **orders:{tenantId}:{orderId}:{revision}:{projectionProfile}**. Nếu response thực sự phụ thuộc vào user và consent, còn cần phân vùng theo scope/subject hoặc **không cache response cuối**. Tránh log actual PII trong metrics labels.

### 7.2. Invalidation phải xét thời điểm transaction commit

Việc gọi Redis delete trước khi transaction DB commit có thể tạo race: một GET khác miss Redis, đọc DB cũ v7, ghi v7 vào cache; sau đó transaction commit v8 và không còn invalidation nào. Giải pháp thường dùng:

- Invalidate **sau commit** bằng callback transaction synchronization nếu phù hợp.
- Với yêu cầu reliability cao, dùng **transactional outbox + consumer idempotent** để không mất sự kiện invalidation khi process crash sau commit.
- Dùng **versioned cache keys / compare-and-set** để một bản v7 không ghi đè value v8.
- Không cho một miss read replica stale lấp đầy cache dùng cho read-your-writes mà không có guard.

**After-commit callback không phải distributed transaction:** Redis có thể unreachable sau DB commit. Khi đó cần retry/outbox hoặc TTL/chính sách degrade rõ ràng. Nếu cache inconsistency gây sai tiền/quyền, fail closed hoặc đọc primary, không trả "best effort" vô điều kiện.

## 8. Replica lag: đọc bản sao chưa replay kịp commit

PostgreSQL physical **streaming replication** thường là asynchronous trừ khi được cấu hình khác; primary có thể commit v8 trong khi replica mới replay đến v7. Ứng dụng dùng read/write splitting hoặc **@Transactional(readOnly=true)** có thể vô tình chọn replica cho GET sau POST.

**Bản chất:** replica không hỏng và cũng không phải HTTP cache. Nó đang phục vụ **snapshot hợp lệ nhưng chưa theo kịp nguồn mới nhất**.

### 8.1. Đo tiến độ WAL, không chỉ nhìn timestamp

Trên primary:

~~~sql
-- Trên PRIMARY
SELECT pg_current_wal_lsn() AS primary_current_lsn;
~~~

Trên replica:

~~~sql
-- Trên REPLICA
SELECT pg_is_in_recovery() AS is_replica,
       pg_last_wal_receive_lsn() AS received_lsn,
       pg_last_wal_replay_lsn() AS replayed_lsn,
       pg_last_xact_replay_timestamp() AS last_replay_timestamp;
~~~

**Chú ý diễn giải:**

- **Receive LSN** cho biết log đã tới replica đến đâu; **replay LSN** cho biết đã được áp đến đâu. Received không chứng minh row đã đọc được.
- Chỉ so LSN khi chúng thuộc **cùng cluster/timeline** và snapshot đo phù hợp. Một LSN primary đo sau commit có thể nằm phía trước nhiều commit khác; dùng nó làm watermark bảo thủ, không ngầm coi là commit LSN chính xác của request.
- **now() - pg_last_xact_replay_timestamp()** không phải lag tuyệt đối trong mọi trường hợp: khi primary idle lâu, timestamp replay cuối có thể rất cũ dù replica đã catch up.
- Replication slot, network RTT, disk replay, long queries và conflict có thể ảnh hưởng lag; đo cùng trace timestamp/cluster identity.

Nếu có yêu cầu **read-your-writes**, cách đơn giản và đáng tin là **đọc primary ngay sau write** hoặc trong transaction có read consistency thích hợp. Với replica reads, có thể dùng watermark/LSN và **wait with bounded timeout** cho đến khi replay đạt ngưỡng, rồi **fallback primary**; việc đó phải được thiết kế/cấp ngân sách riêng, không chặn request vô hạn.

### 8.2. Read-your-writes khác eventual consistency

| Mức cam kết | Hành vi sau PATCH v8 |
| --- | --- |
| **Eventual consistency** | GET qua replica có thể thấy v7 tạm thời; client phải biết hợp đồng này |
| **Read-your-writes** | Cùng session/caller phải thấy ít nhất v8 sau khi write đã xác nhận |
| **Monotonic reads** | Client đã thấy v8 không được quay lại thấy v7 ở request sau |
| **Strong/current read** | Đọc nguồn đủ nhất quán tại thời điểm hợp đồng định nghĩa; thường cần primary hoặc cơ chế DB tương ứng |

**Sticky primary reads trong vài giây** là heuristic có thể dùng khi SLA lag được đo, nhưng **không bảo đảm tuyệt đối** nếu replica chậm hơn TTL hoặc sticky state bị mất giữa devices/pods. Nếu sản phẩm yêu cầu mạnh, dùng primary/consistency token có semantics rõ ràng.

### 8.3. Tránh thay đổi routing chỉ bằng annotation

**@Transactional(readOnly=true)** trong Spring là metadata/hint cho transaction; **không tự động bảo đảm route sang replica** và **không đồng nghĩa luôn đọc dữ liệu mới**. Routing tùy Datasource/router/transaction manager, thời điểm lấy JDBC connection và propagation.

Khi dùng **AbstractRoutingDataSource** dựa trên thread-local readOnly, lưu ý transaction có thể lấy connection **trước** khi readOnly flag được thiết lập; cần thiết kế đúng với **LazyConnectionDataSourceProxy** hoặc explicit routing, kiểm thực nghiệm bằng logs/connection endpoint. Không dùng annotation thay cho chứng minh datasource đang đọc thực tế.

## 9. Quy trình khoanh vùng: đi từ client đến primary

Không có một header nào trả lời chắc chắn "đây là lỗi CDN hay replica". Cần **so sánh nhiều đường đọc** với cùng identity, tenant, resource, thời điểm và representation.

### 9.1. Bốn phép thử có khả năng phân biệt cao

| Phép thử | Nếu trả mới | Nếu vẫn cũ |
| --- | --- | --- |
| **A. Browser bình thường vs DevTools Disable cache** | Nghi browser HTTP cache; còn phải kiểm service worker | Kiểm CDN, backend, app cache, replica |
| **B. Public gateway vs origin/backend trong môi trường được phép** | Nghi gateway/CDN cache key, TTL, Vary hoặc rewrite | Kiểm cache ứng dụng và DB |
| **C. Backend có/không Redis trong test profile** | Nghi Redis/local cache, invalidation và TTL | Kiểm primary/replica |
| **D. Query primary vs replica bằng read-only diagnostic** | Primary mới, replica cũ: replication lag/routing | Nếu primary cũng cũ: write chưa commit/sai row/transaction |

**Bỏ qua HTTP cache không bỏ qua Redis hoặc replica.** Thêm request header Cache-Control: no-cache chỉ yêu cầu các HTTP caches liên quan revalidate trước reuse; nó không ép Spring xóa cache nội bộ hoặc đọc primary.

Một quy trình đầy đủ:

1. Xác nhận PATCH **đã commit thành công** chứ không chỉ nhận 202 Accepted, hoặc HTTP client đã timeout với kết quả chưa xác định. Kiểm operation ID/idempotency ledger.
2. Lấy **order ID, tenant context, expected revision v8, request ID và thời điểm commit** từ phía hệ thống an toàn.
3. Gửi cùng GET với và không có **If-None-Match**; so status 200/304, ETag, Cache-Control, Vary, Age, Date.
4. So đường public CDN, backend và nguồn đọc primary/replica **trong môi trường quản trị được ủy quyền**; không mở DB/backend nội bộ ra Internet để debug.
5. Xem trace để biết request đã **cache HIT, gọi SQL qua datasource nào, lấy revision nào**.
6. Xác định vị trí phát sinh stale, test lại sau thay đổi có giới hạn, rồi chọn fix lâu dài thay vì cache purge thủ công mãi mãi.

### 9.2. curl để tái hiện các response conditions

~~~bash
# GET hiện tại, kiểm status, ETag, Age, Vary, Cache-Control.
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  'https://api.example.test/api/v1/orders/<id>'

# Buộc HTTP cache revalidate theo request directive, nếu được hỗ trợ.
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  -H 'Cache-Control: no-cache' \
  'https://api.example.test/api/v1/orders/<id>'

# Thử conditional GET với ETag cũ đã lấy từ chính API.
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  -H 'If-None-Match: "order-v7"' \
  'https://api.example.test/api/v1/orders/<id>'
~~~

**curl không tự có browser HTTP cache.** Nếu curl qua gateway vẫn stale thì không thể kết luận browser cache là thủ phạm duy nhất. Đừng dùng token sản xuất trong lịch sử shell hoặc chia sẻ nguyên HTTP logs; test token/identity có scope tối thiểu và redact khi ghi báo cáo.

### 9.3. Phân biệt cache miss với origin trả stale

Nếu CDN có **MISS** nhưng response vẫn v7, origin có thể lấy v7 từ Redis hoặc replica. Nếu Spring ghi **cache MISS** nhưng SQL từ replica trả v7, xóa Redis không sửa tận gốc. Nếu primary v8 nhưng SQL order GET trả v7 trên primary, kiểm transaction snapshot/isolation, query predicates, sai database/cluster, versioning, application DTO mapper hoặc write thực chưa commit.

**Đừng chỉ chọn một 200 mới làm bằng chứng đã khắc phục**: cần test nhiều lần, đủ thời gian cho cache TTL, replica catch-up, các pod/edge locations và consistency guarantee của client.

## 10. Spring MVC: điều kiện trả 304 phải dựa trên dữ liệu đã được phép xem

Ví dụ controller Spring Boot 3 đọc từ nguồn phù hợp yêu cầu **freshness**, xác thực caller và sau đó mới đánh giá ETag:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderReadController {
    private final OrderReadService service;
    private final CallerResolver callers;

    public OrderReadController(
            OrderReadService service, CallerResolver callers) {
        this.service = service;
        this.callers = callers;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> get(
            @PathVariable UUID id,
            Authentication authentication,
            WebRequest webRequest,
            HttpServletResponse servletResponse) {

        Caller caller = callers.require(authentication);

        // Bắt buộc xác thực tenant và object ACL trước 304.
        // Đây là đường đọc yêu cầu freshness đủ mạnh.
        OrderView order = service.requireFreshVisible(caller, id);

        // Giả sử route này có JSON projection cố định và validator
        // của selected representation do service kiểm soát.
        String etag = order.responseEtag();

        CacheControl policy = CacheControl.noCache().cachePrivate();
        if (webRequest.checkNotModified(etag)) {
            // Spring có thể chọn 304 hoặc 412 tùy precondition.
            return ResponseEntity.status(servletResponse.getStatus())
                .eTag(etag)
                .cacheControl(policy)
                .build();
        }
        return ResponseEntity.ok()
            .eTag(etag)
            .cacheControl(policy)
            .body(order);
    }
}
~~~

**Giới hạn minh họa:**

- **Caller, OrderView, OrderReadService, CallerResolver** là domain abstractions cần cài đặt, không phải class sẵn có trong Spring.
- **WebRequest.checkNotModified(etag)** xử lý precondition/validator ở HTTP boundary. Trường hợp If-None-Match cho GET có thể là 304, còn một số precondition khác như If-Match thất bại có thể là 412; không hardcode 304 cho mọi nhánh trả true. Test nhiều giá trị, weak tags và wildcard theo implementation thực.
- **Cache-Control: private, no-cache** cho phép private cache lưu nhưng yêu cầu revalidate khi reuse. Nếu order nhạy cảm cần **no-store**, dùng no-store và không coi 304 là tối ưu chủ đạo.
- **responseEtag** phải phản ánh đúng selected representation/projection. Nếu gateway nén gzip/identity thành bytes khác, cần chính sách strong/weak ETag đúng content coding. Không lấy mỗi version DB làm strong ETag rồi tái dùng cho các body/encoding khác nhau.
- **If-Match** cho PATCH có yêu cầu strong validator riêng; nếu GET dùng weak validator, không dùng weak tag ấy để thỏa If-Match.
- Khi client không có quyền xem order, trả 403/404 theo privacy policy, **không trả 304** chỉ vì ETag khớp một cache cũ.

Một lỗi phổ biến là tính ETag từ revision trên replica v7 rồi trả 304 mặc dù primary v8. Trong route **hứa read-your-writes**, **requireFreshVisible** phải chọn primary hoặc chờ replica đạt watermark với fallback. Không phải mọi GET đều cần primary: list/catalog có thể chấp nhận eventual consistency nếu contract công bố rõ.

### 10.1. Kiểm soát serialization/caching ở nhiều tầng

Ngay cả khi Spring trả Cache-Control và ETag đúng, gateway/CDN có thể override TTL, strip Vary hoặc tạo ETag khác khi compress body. Chạy integration tests qua **HTTP socket và public gateway route**, không chỉ MockMvc, để xác nhận hiệu quả cuối cùng.

## 11. Java/Spring: transaction, cache invalidation và phiên bản dữ liệu

Giả sử service cập nhật order trong transaction và muốn xóa cache sau commit:

~~~java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final CacheInvalidator invalidator;

    public OrderCommandService(
            OrderRepository orders, CacheInvalidator invalidator) {
        this.orders = orders;
        this.invalidator = invalidator;
    }

    @Transactional
    public UpdatedOrder pay(Caller caller, UUID id, long expectedVersion) {
        Order order = orders.requireEditable(caller, id);
        if (order.version() != expectedVersion) {
            throw new PreconditionFailedException();
        }

        order.markPaid();
        long newVersion =
            orders.saveWithExpectedVersion(order, expectedVersion);

        UUID tenant = caller.tenantId();
        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    // Redis lỗi sau commit không được giả định DB rollback.
                    try {
                        invalidator.evictOrder(tenant, id);
                    } catch (RuntimeException ex) {
                        // Metrics + alert; durable retry/outbox cần thiết
                        // khi mất invalidation có thể vi phạm contract.
                        reportCacheEvictionFailure(tenant, id, ex);
                    }
                }
            }
        );

        return new UpdatedOrder(id, newVersion);
    }
}
~~~

**Lưu ý vận hành:**

1. **saveWithExpectedVersion** phải là DB CAS/optimistic lock thật, trả revision mới sau mutation; check Java trước đó không tự ngăn race giữa hai PATCH. Hàm **reportCacheEvictionFailure** là hook giả định, không log token/PII.
2. Callback **afterCommit** chỉ chạy sau commit thành công, nhưng Redis có thể lỗi; không có atomic transaction chung giữa DB và Redis.
3. Nếu cần bảo đảm invalidation không mất, ghi **outbox record trong cùng DB transaction** và có worker retry/dedup publish sau commit. Chỉ callback không có durable retry chưa đủ.
4. **Invalidation sau commit vẫn có race repopulation từ request cũ/replica cũ**. Dùng version-based cache values, kiểm revision tối thiểu, TTL phù hợp và route primary khi cần fresh.
5. Nếu Hibernate/ORM đã dùng second-level/query cache, kiểm invalidation và transaction boundaries tại tầng đó; xóa Redis không xóa mọi cache.

Một pattern ổn định hơn cho dữ liệu có revision là cache entry chứa **tenantId, orderId, revision, data**. Khi client yêu cầu tối thiểu v8, cached v7 bị coi là **không đủ mới**, dù TTL còn; service đọc primary hoặc replica đã theo kịp. Bản cache được repopulate phải tránh ghi revision thấp đè revision cao.

### 11.1. Spring @Cacheable: kiểm quyền ở mỗi request

Với method:

~~~java
@Cacheable(cacheNames = "orderViews", key = "#id")
public OrderView readOrder(Caller caller, UUID id) {
    return repository.requireVisible(caller, id);
}
~~~

Đây là **anti-pattern bảo mật**. Một cache hit có thể trả ngay trước khi method body/ACL query thực thi và key chỉ theo id có thể dùng response đã được authorize cho user khác. Sửa kiến trúc theo một trong hai hướng:

- **Authorize trước** cache lookup và cache dữ liệu đủ an toàn theo **tenant + permission/projection/version context**; trên hit vẫn phải xét quyền hiện tại.
- **Không cache response cuối chứa dữ liệu nhạy cảm**, hoặc chỉ dùng per-user private cache đã ràng buộc lifecycle quyền và có invalidation khi revoke.

**@CacheEvict không tự bảo đảm after-commit đúng mọi trường hợp**: thứ tự AOP/transaction advice, self-invocation qua Spring proxy và quyền gọi method cần được test. Không đặt security correctness lên một annotation mà không xác minh behavior khi race và rollback.

## 12. Explicit primary/replica routing cho consistency quan trọng

Có thể thiết kế service dùng **hai reader adapters** để gọi đúng datasource thay vì suy readOnly annotation = replica:

~~~java
public interface AuthorizedOrderReader {
    OrderView requireVisible(Caller caller, UUID orderId);
}

@Service
public class OrderFreshnessService {
    private final AuthorizedOrderReader primaryReader;
    private final AuthorizedOrderReader replicaReader;

    public OrderFreshnessService(
            @Qualifier("primaryOrderReader")
                AuthorizedOrderReader primaryReader,
            @Qualifier("replicaOrderReader")
                AuthorizedOrderReader replicaReader) {
        this.primaryReader = primaryReader;
        this.replicaReader = replicaReader;
    }

    public OrderView get(
            Caller caller, UUID id, boolean requireReadYourWrites) {
        if (requireReadYourWrites) {
            return primaryReader.requireVisible(caller, id);
        }
        return replicaReader.requireVisible(caller, id);
    }
}
~~~

**Hai adapters phải thực thi cùng tenant + object ACL**, không chỉ kiểm ở HTTP controller. Nếu read replica chứa ACL snapshot cũ sau khi quyền bị thu hồi, có thể trả dữ liệu không còn được phép: **authorization hiện hành phải lấy nguồn đủ mới**, ví dụ primary policy store, trước khi sử dụng data replica hoặc cache theo quy tắc security.

Trong các ứng dụng phức tạp, read-your-writes có thể dùng **consistency token** như minimum revision/LSN được chứng minh là đã commit, gắn với session hoặc request kế tiếp. Phải hạn chế:

- Token không phải bearer authorization, không được thay JWT/tenant ACL.
- Client không được tự gửi revision quá lớn để giữ connection/replica wait vô hạn; giới hạn wait budget và format.
- Không dùng timestamp từ máy client để đo WAL replay hay đảm bảo commit order.
- Khi replica chưa đáp ứng minimum revision, đọc primary hoặc trả lỗi đúng hợp đồng; **không lặng lẽ trả phiên bản thấp hơn** cho client yêu cầu fresh.
- **Monotonic reads** có thể yêu cầu ghi nhớ revision tối thiểu đã nhìn thấy, kể cả khi client chuyển pod/region.

### 12.1. Read routing và transaction isolation

Trong cùng DB primary, một transaction snapshot ở mức **REPEATABLE READ** có thể tiếp tục thấy snapshot cũ dù transaction khác đã commit. Với **READ COMMITTED**, mỗi statement thường có snapshot riêng trong PostgreSQL; vẫn phải xét transaction boundaries và connection routing. Chẩn đoán lỗi "replica stale" cần phân biệt **transaction isolation/snapshot lâu dài** với **WAL replication lag**.

## 13. Checklist hiệu chỉnh HTTP caching và Vary ở gateway

Không nên tắt cache toàn site vì một route sensitive bị stale. Thay vào đó phân loại endpoint theo nghiệp vụ:

| API | Freshness policy gợi ý | Chú ý |
| --- | --- | --- |
| Public catalog/static reference | Cache public ngắn, Vary đầy đủ | TTL và stale directives theo product SLO |
| Order detail / payment status | Private/no-store hoặc private + revalidate theo yêu cầu | Read-your-writes, không share cache qua users |
| Search kết quả có ACL | Private/no-store hoặc cache scope chặt | Count/facet/cursor không rò tenant |
| Profile/consent/token | Thường no-store | Không dùng stale-if-error để hồi sinh quyền cũ |
| Export binary riêng tư | Private/no-store, signed URL TTL ngắn theo policy | CDN/object cache không làm URL còn quyền mãi |
| Rate limit/quotas | Quyết định từ nguồn hạn mức đủ tin cậy | Không fail-open khi Redis store hỏng |

**Điều chỉnh gateway:**

1. Xác định route nào đang cache: **method, status, response Cache-Control, authorization policy**.
2. So **effective cache key** với URL + query, header variants Vary, content encoding và tenant scope.
3. Bảo đảm gateway **giữ ETag/Vary** khi compress/rewrite response, hoặc tự tính validator đúng representation.
4. Không cache 401/403/404 nhạy cảm bằng public policy; negative cache cần TTL/invalidation khi resource xuất hiện.
5. CORS response ACAO động có **Vary: Origin**; không để cache response origin A phát thành origin B.
6. Không dùng **Cache-Control: no-store** rồi đồng thời tuyên bố browser sẽ tái sử dụng 304 như một chiến lược cache chính; nếu cần revalidation, cân nhắc **private, no-cache** và security approval.
7. Khi purge, purge **đúng namespace/variant/key** và xem origin có repopulate từ replica stale không. Purge chỉ chữa tạm thời nếu cấu hình và race chưa sửa.

## 14. Observability: chứng minh ai trả dữ liệu cũ

Cần gắn **request/correlation ID**, nhưng tránh log raw access token hoặc user PII. Trong trace nội bộ có thể dùng:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **HTTP status, route, ETag, Cache-Control, Vary, Age** | Client nhận variant và freshness nào |
| **CDN cache hit/miss/stale/revalidation** | Edge có reuse object không |
| **Spring Redis cache name/key hash, hit/miss, entry revision** | App có dùng dữ liệu cached v7 không |
| **Datasource role (primary/replica), DB cluster ID, transaction isolation** | Thực sự đọc từ nguồn nào |
| **Order logical revision + commit/outbox sequence** | Dữ liệu business nào đã commit |
| **Replica receive/replay LSN và lag windows** | Bản sao đã bắt kịp nguồn chưa |
| **Outbox/invalidation lag, retry errors** | Vì sao cache không bị xóa |
| **Vary variant dimensions** | Có reuse sai language/encoding/projection không |
| **Auth/tenant scope decisions** | Không bỏ qua phân quyền khi cache hit |
| **Client session minimum revision (opaque/hash)** | Có vi phạm read-your-writes/monotonic reads không |

Metric labels nên là **route template, cache tier, datasource role, version cohort, region**, không dùng orderId/tenantId cá nhân trực tiếp làm labels có cardinality rất cao. Revision/order ID nếu cần điều tra được lưu ở trace có quyền truy cập hạn chế và retention phù hợp.

**Một observation quan trọng:** tỷ lệ Redis HIT tăng đồng thời p95 GET giảm không chứng minh tính đúng đắn. Nếu v7 vẫn được phục vụ sau v8, "cache hiệu quả" có thể là bằng chứng của bug freshness.

## 15. Ma trận kiểm thử stale data và cache isolation

Đừng chỉ test một GET thành công. Dữ liệu cũ cần được tái hiện theo **commit, cache fill/invalidation, replica replay và quyền**.

| ID | Điều kiện thử | Kết quả cần chứng minh |
| --- | --- | --- |
| H01 | PATCH v7 thành v8, GET ngay cùng session | Đáp ứng read-your-writes nếu contract yêu cầu |
| H02 | GET với If-None-Match v7 sau PATCH v8 | **200 v8**, không trả 304 sai |
| H03 | GET v8 lần trước, request sau tới replica v7 | Không vi phạm monotonic reads nếu đã cam kết |
| H04 | HTTP Cache-Control: no-cache | Cache revalidate; không coi Redis/replica đã bị bypass |
| H05 | HTTP Cache-Control: no-store | Browser/CDN không tái dùng stored response |
| V01 | Vi vs en cùng URL | Vary: Accept-Language; không reuse nhầm ngôn ngữ |
| V02 | gzip vs identity | Vary: Accept-Encoding, bytes/ETag coding đúng |
| V03 | CORS Origin A vs B | Vary: Origin khi ACAO động, không lẫn headers |
| V04 | fields=id,name vs fields=id,name,price | Key/projection/ETag không trộn |
| V05 | Gateway custom key bỏ query hoặc Vary | Test phát hiện cache HIT sai variant |
| C01 | 200 user A được cached rồi user B truy cập | Không lộ tenant/order/field nhạy cảm |
| C02 | Resource vừa được tạo sau negative 404 cache | Negative cache không che mãi resource mới |
| C03 | Invalidate Redis trước commit rồi concurrent GET | Không repopulate v7 vĩnh viễn |
| C04 | Invalidate sau commit nhưng Redis timeout | Durable outbox/retry hoặc policy fail-safe |
| C05 | Local cache nhiều pods, chỉ một pod evict | Không có pod tiếp tục trả v7 trái hợp đồng |
| C06 | Cache put v8 rồi stale in-flight put v7 | Bản v7 không hạ revision đã cached |
| R01 | Replica replay chậm 500 ms | GET eventual có thể v7; GET fresh phải >=v8 |
| R02 | Primary đã commit nhưng replica LSN chưa đủ | Bounded wait/fallback primary, không block vô hạn |
| R03 | Replica idle lâu với last replay timestamp cũ | Không báo lag sai chỉ dựa vào age timestamp |
| R04 | Long-running REPEATABLE READ transaction | Phân biệt stale snapshot với replication lag |
| S01 | ACL bị thu hồi khi cache v7 còn valid | Không đọc được v7 trái quyền hiện hành |
| S02 | Token expired nhưng cache còn data | Vẫn trả 401, không cache bypass security |
| O01 | CDN purge nhưng app cache từ replica v7 | Không kết luận resolved cho đến khi origin đúng |
| O02 | Invalid ETag/304 sau serializer/schema change | Test bắt validator sai selected representation |

Các test cần **fixture tenant A/B, owner/ACL, versions v7/v8 và cấu hình TTL cụ thể**. Khi test physical replica, không dựa duy nhất vào Thread.sleep(500): điều khiển replication link/fault bằng staging/test setup, đo receive/replay LSN và dùng deadline/assertions có giới hạn.

### 15.1. Contract test với REST Assured/JUnit 5

Đoạn minh họa giả định PATCH thành công trả **200** và GET dùng strong ETag tương thích với If-Match; nếu API chọn 204 hoặc ETag yếu cho GET, điều chỉnh đúng contract:

~~~java
@Test
void conditionalGetAfterPatchMustNotReturnOld304() {
    String id = seededOrderId;
    String token = tokens.tenantAEditor();

    Response before = given()
        .spec(api())
        .auth().oauth2(token)
    .when()
        .get("/orders/{id}", id)
    .then()
        .statusCode(200)
        .extract().response();

    String oldTag = before.header("ETag");
    assertNotNull(oldTag);

    given()
        .spec(api())
        .auth().oauth2(token)
        .header("If-Match", oldTag)
        .contentType("application/merge-patch+json")
        .body("{\"status\":\"PAID\"}")
    .when()
        .patch("/orders/{id}", id)
    .then()
        .statusCode(200);

    Response after = given()
        .spec(api())
        .auth().oauth2(token)
        .header("If-None-Match", oldTag)
    .when()
        .get("/orders/{id}", id)
    .then()
        .statusCode(200)
        .extract().response();

    assertEquals("PAID", after.jsonPath().getString("status"));
    assertNotEquals(oldTag, after.header("ETag"));
}
~~~

Đây là **test skeleton**, cần TestTokenFactory, dữ liệu seeded, imports REST Assured/JUnit/Hamcrest, API route và DB test độc lập. Nếu Read-after-write contract chưa yêu cầu freshness mạnh, không ép mọi GET qua replica phải trả v8 tức thì; thay bằng test **eventual convergence trong SLA** và một endpoint/mode fresh có guarantee rõ.

**Một response 200 v8 chưa đủ** nếu PATCH tạo hai side effects hoặc order thuộc tenant khác. Với concurrency, kiểm DB revision và idempotency ledger; với security, có thêm test token tenant B nhận 403/404 và không rò ETag/status của A.

### 15.2. Kiểm cache revision không bị tụt vì race

Một test đơn vị hữu ích là cho bản v8 được put vào cache trước, sau đó một request cũ cố put v7:

~~~java
@Test
void lateCacheFillCannotReplaceNewerRevision() {
    cache.putIfNewer(tenantA, orderId,
        new CachedOrder(8L, "PAID"));
    cache.putIfNewer(tenantA, orderId,
        new CachedOrder(7L, "CREATED"));

    assertEquals(8L,
        cache.get(tenantA, orderId).revision());
}
~~~

**putIfNewer phải là thao tác atomically compare-and-update** tại cache store (ví dụ Redis Lua/transaction/CAS), không phải GET rồi SET tách rời; nếu không race giữa nhiều pods vẫn có thể hạ revision.

### 15.3. Test cả browser và gateway

- Trên browser thật, thử reload, back/forward navigation và service worker để xác định origin request có được gửi không.
- Qua CDN, dùng hai headers Accept-Language và Accept-Encoding khác nhau, nhiều edges nếu có; kiểm **Vary, Age, cache hit và decoded body**.
- Trên Spring với RANDOM_PORT, kiểm SecurityFilterChain, HTTP cache headers và selected ETag; MockMvc một mình **không kiểm CDN behavior hoặc replication**.
- Với database, dùng PostgreSQL/Testcontainers hoặc môi trường test replication được phép; query **primary vs replica**, kiểm WAL LSN và commit timing, không giả lập kết luận từ mock Redis.

## 16. Runbook xử lý sự cố khi người dùng thấy dữ liệu cũ

### 16.1. Triệu chứng và tuyến điều tra

| Triệu chứng | Nghi phạm đầu | Hành động xác minh |
| --- | --- | --- |
| Chỉ một browser/tab cũ | Browser HTTP cache, service worker | DevTools cache/service worker, so curl |
| Mọi client một region cũ | CDN edge/cache key, regional replica | Age, edge logs, datasource region |
| Request đến Spring nhưng không có SQL | Redis/local/ORM cache | Trace cache HIT, entry revision, TTL |
| SQL có thực thi nhưng v7 | Replica/transaction snapshot | Data source role, primary/replica comparison |
| 304 khi primary đã v8 | Validator từ replica/cache cũ | Audit selected representation và read routing |
| Sau PATCH tạo mới nhưng list chưa thấy | Replica/search index/materialized view lag | Kiểm indexing/backfill lag, list source |
| Một user được dữ liệu của user khác | Cache key/authorization breach | **Security incident**; hạn chế phạm vi, preserve evidence |
| Thời gian stale tăng sau deploy | Cache namespace/schema change, new routing, queue lag | So release flags, metrics trước/sau |

### 16.2. Thứ tự hành động trong incident

1. **Xác định mức độ nghiêm trọng.** Cross-tenant leakage, quyền bị thu hồi nhưng vẫn đọc được hoặc sai số tiền là sự cố an ninh/toàn vẹn, ưu tiên bảo vệ người dùng hơn cache hit rate.
2. **Khóa dấu vết.** Lưu timestamps, request IDs, tenant context an toàn, revision mong đợi và thực tế, headers Age/ETag/Vary, cache tier và datasource role.
3. **Xác minh commit.** Nếu write response timeout, không tự suy dữ liệu đã commit; kiểm primary/outbox/idempotency.
4. **Khoanh vùng.** Browser → CDN/gateway → Redis/app → replica → primary theo các phép thử mục 9.
5. **Mitigate có mục tiêu.** Với order nhạy cảm, route read sang primary/tắt cache riêng route hoặc loại variant sai; với replica lag, giảm traffic đọc replica và giữ giới hạn connection; với cache invalidation backlog, tăng xử lý có kiểm soát.
6. **Kiểm security và cost.** Route toàn bộ reads sang primary có thể gây overload; áp admission/monitoring, giới hạn thời gian canary và rollback nếu p95/DB pool bất thường.
7. **Phục hồi và xác nhận.** Tạo PATCH test vN sang vN+1, kiểm same-session và cross-session, mọi pod/edge/replica cần thiết, TTL và authorization.
8. **Hậu kiểm.** Viết root-cause, sửa key/Vary/invalidation/routing, thêm regression test, xác định owner/SLO và đề xuất cảnh báo dài hạn.

**Đừng chỉ purge CDN hoặc flush toàn bộ Redis rồi đóng ticket.** Purge có thể chữa biểu hiện tạm, nhưng stale value sẽ được nạp lại nếu origin vẫn đọc replica chưa bắt kịp hoặc invalidation race chưa sửa. Flush toàn cục còn gây cache stampede và áp lực lên primary.

### 16.3. Điều kiện kết thúc xử lý sự cố

Tuyên bố resolved khi đã có bằng chứng:

- Primary có revision đúng, các đường đọc đúng theo **consistency contract**.
- Browser/CDN/app cache không reuse sai variant/tenant.
- Replica lag trở về ngưỡng, hoặc strong-read route được áp dụng có giới hạn.
- Không có dữ liệu cũ trái quyền, không có lỗi 304/ETag tại read-after-write test.
- Bounded load/canary không làm primary quá tải; metrics giữ ổn định qua nhiều cửa sổ đo.
- Có regression test/runbook để lỗi tương tự không tái diễn âm thầm.

## 17. Bài thực hành: Order v8 vẫn hiển thị v7

**Bối cảnh:** REST API chạy qua CDN, Spring Boot 3, Redis cache và PostgreSQL primary + một read replica. PATCH order từ CREATED sang PAID commit ở primary, trả ETag mới. Gọi GET ngay sau đó đôi khi thấy CREATED hoặc 304. API là multi-tenant, dùng JWT; người dùng muốn **read-your-writes** với chi tiết order nhưng list analytics có thể eventual.

**Nhiệm vụ (100 điểm):**

1. **Bản đồ & HTTP – 25 điểm:** vẽ tuyến browser/CDN/Spring/Redis/replica/primary; giải thích Cache-Control no-cache vs no-store, Age, Vary, ETag/304 và đường hiện tượng sai.
2. **Chẩn đoán – 25 điểm:** lập ít nhất sáu phép thử phân biệt browser/CDN/app cache/replica; mô tả primary/replica WAL diagnostics, chú ý replay timestamp khi idle.
3. **Java/Spring – 25 điểm:** tạo GET order fresh với authorization trước 304, policy cache an toàn, xử lý invalidation after-commit + outbox, cache version guard và explicit primary reader khi cần.
4. **Security/tests – 25 điểm:** xây ma trận hai tenant, revoke ACL, Accept-Language/Encoding Vary, PATCH→GET conditional, replica lag, cache repopulation race và rollback/mitigation dưới tải.

**Hướng giải:** bắt đầu bằng chứng PATCH commit v8 ở primary. Nếu GET có Age lớn/cache HIT, kiểm HTTP cache/Vary; nếu origin Redis HIT v7, kiểm key/eviction/race; nếu Redis MISS nhưng SQL replica v7, kiểm replay lag. Với chi tiết order, chọn primary/read-your-writes hoặc bounded watermark wait có fallback. Không trả 304 dựa trên v7 khi contract yêu cầu thấy v8. Dữ liệu nhạy cảm phải **fail-closed** khi quyền bị thu hồi.

**Tiêu chí đạt:** cùng caller sau PATCH v8 không thấy v7; tenant B không thấy order A; nếu CDN variant thay đổi theo headers, không có reuse sai; hệ thống có thể chứng minh nguyên nhân qua trace và regression tests.

## 18. Checklist kỹ thuật và nguồn tham khảo

- [ ] Xác định **nguồn sự thật**, mức consistency theo endpoint, version và commit boundary.
- [ ] Biết response đến từ browser, CDN/gateway, Spring cache, Redis hay DB.
- [ ] Hiểu **no-cache khác no-store**, private/public, Age và stale directives.
- [ ] Vary phản ánh Accept/Language/Encoding/Origin hoặc custom header selector cần thiết.
- [ ] Cache key có URL/query và scope; không phát lại tenant/field của caller khác.
- [ ] ETag/304 được tính từ đúng selected representation và **sau authorization**.
- [ ] Không dùng validator của replica stale cho route hứa read-your-writes.
- [ ] Redis invalidation sau commit có retry/outbox; không repopulate revision thấp.
- [ ] @Cacheable không được bypass ACL; revoked permission có hiệu lực theo policy.
- [ ] PostgreSQL receive/replay LSN được diễn giải đúng; không tin mỗi replay timestamp.
- [ ] Primary vs replica routing và transaction isolation được kiểm bằng trace/test.
- [ ] Có tests two tenants, cache invalidation race, conditional GET, Vary và lag.
- [ ] Mitigation có giới hạn tải, rollback/monitoring và hậu kiểm root cause.

**Ghi nhớ:** một JSON **200** hoặc **304** không nói được dữ liệu đã mới. Phải hỏi **phiên bản nào, được chọn bằng policy/variant nào, cache ở đâu, replica đã replay đến đâu và caller có còn quyền không**. Chỉ khi trả lời đủ mới phân biệt được lỗi HTTP caching, cấu hình Vary và replica consistency.

### Tài liệu tham khảo

- **RFC 9110 – HTTP Semantics:** ETag, If-None-Match, If-Match, 304, selected representation.
- **RFC 9111 – HTTP Caching:** Cache-Control, Vary, Age, validation và shared/private caches.
- **RFC 5861 – HTTP Cache-Control Extensions for Stale Content:** stale-while-revalidate, stale-if-error.
- **PostgreSQL Documentation:** streaming replication, pg_stat_replication, WAL LSN, hot standby, transaction isolation.
- **Spring Framework / Spring Boot / Spring Security:** WebRequest.checkNotModified, @Cacheable, transaction synchronization, DataSource routing.
- **OWASP API Security Top 10:** BOLA/BOPLA, authorization và resource consumption; hướng dẫn cache isolation của gateway/CDN provider.
