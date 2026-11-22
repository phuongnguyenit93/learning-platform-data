# Caching nhiều tầng và kiểm tra hiệu lực sau thay đổi

## 1. Cache nhanh nhưng không được trả dữ liệu sai

Một ứng dụng Java/Spring triển khai REST API bán hàng: người dùng mở trang sản phẩm, gọi GET /api/products/BOOK-01 và nhận giá 350.000 đồng. Để giảm truy vấn database, hệ thống có cache tại trình duyệt, CDN, API gateway và Redis. Quản trị viên vừa đổi giá thành 320.000 đồng, nhưng một số khách hàng vẫn nhìn thấy giá cũ; người khác gửi If-None-Match và nhận 304, giữ nguyên bản thể đã lỗi thời.

Vấn đề không chỉ là **cache hit ratio**: cache được coi là thành công khi **đúng bản thể, đúng người, đúng thời điểm và đúng hợp đồng nhất quán**. Hiệu năng mà làm lộ đơn hàng khách khác, xác nhận ETag cũ sau khi mất quyền, hoặc khiến POST thanh toán lặp lại là hiệu năng không chấp nhận được.

Trong module **INTEGRATION_API_REST**, bài học nối thiết kế resource/URI, GET/PUT/PATCH, mã trạng thái, Cache-Control, ETag, idempotency, authentication/authorization, OpenAPI và kiểm thử Java/Spring vào một chủ đề: **caching nhiều tầng và xác minh tính hiệu lực của dữ liệu sau khi thay đổi**.

Sau bài, người học cần:

1. Vẽ được các tầng cache, ai sở hữu dữ liệu và giới hạn về độ cũ.
2. Chọn HTTP freshness/validators, phân biệt **cache lifetime** với **tính đúng đắn của phiên bản**.
3. Thiết kế cache key, scope tenant, biến thể nội dung và chính sách cho tài nguyên riêng tư.
4. Triển khai cache-aside và invalidation trong Spring với ranh giới transaction rõ ràng.
5. Nhận diện race giữa fill, update, eviction, CDN purge; chọn versioned keys/outbox khi cần.
6. Kiểm tra read-after-write, conditional GET, rollback, đồng thời và hiệu năng bằng MockMvc, HTTP client, Redis integration test.

> **Nguyên tắc:** Cache là một bản sao có hạn sử dụng của dữ liệu nguồn, không phải nguồn sự thật. Sau khi ghi, hãy xác định rõ khi nào bản sao ở **mỗi tầng** hết hiệu lực và **làm sao chứng minh** điều đó.

## 2. Sơ đồ nhiều tầng: một GET đi qua những gì?

~~~mermaid
flowchart LR
    B[Browser cache] --> C[CDN / edge]
    C --> G[API gateway / reverse proxy]
    G --> A[Spring REST application]
    A --> R[Redis / distributed cache]
    R --> D[(Database source of truth)]
    A --> L[Local in-process cache]
    L -.-> D
~~~

Sơ đồ cho thấy **các vị trí có thể lưu bản sao**, không phải mọi request luôn đi lần lượt qua cả Redis và local cache. Một triển khai có thể dùng browser/CDN rồi **chỉ Redis**, hoặc local cache rồi DB; gateway cũng có thể không cache. Với cache hit ở CDN, Spring **không nhận request**, nên metric chỉ đo ở ứng dụng sẽ bỏ qua lưu lượng này.

| Tầng | Có thể lưu gì? | Cơ chế làm mới / giới hạn |
|---|---|---|
| **Trình duyệt** | GET responses, ảnh, scripts theo HTTP policy | Freshness, conditional GET, clear/invalidation theo browser |
| **CDN / reverse proxy** | Bản thể công khai được cache chung | TTL, surrogate key, purge theo provider, revalidation |
| **API gateway** | Response theo tuyến, API policies | Cache-key và rule auth/cache của gateway |
| **Local cache trong JVM** | Object/DTO theo key | TTL/size, evict theo node; **không chia sẻ giữa pods** |
| **Redis/distributed cache** | Serialized view hoặc query result | TTL, atomic operations, eviction, versioned key |
| **Database / durable store** | Trạng thái nghiệp vụ có transaction | Nguồn sự thật; read replica có thể lag |

**Cùng một tài nguyên có thể tồn tại ở nhiều phiên bản:**

~~~text
DB revision=19        giá mới 320000
Redis revision=19     giá mới 320000
CDN revision=18       giá cũ 350000
Browser revision=17   giá rất cũ
~~~

Evict Redis không làm CDN hoặc browser tự biến mất. Một CDN purge thành công không bảo đảm mọi tab trình duyệt đã bỏ bản thể fresh đang giữ. Cần xác định **hợp đồng độ cũ tối đa**: ví dụ catalog được phép cũ tối đa 60 giây; giá thanh toán bắt buộc được server tính lại từ dữ liệu đủ mới; đơn hàng chứa PII không cache ở shared CDN.

### 2.1. Lợi ích và chi phí của một hit

**Cache hit** giảm network round trips, CPU, truy vấn DB và latency. Nhưng hit ở tầng nào có ý nghĩa khác nhau:

- **Browser hit:** nhanh nhất cho người dùng, có thể không phát HTTP request tới edge.
- **CDN hit:** không gọi service, nhưng có thể thấy dữ liệu cũ so với DB.
- **Redis hit:** giảm DB; vẫn tốn network/serialization giữa app và Redis.
- **Local hit:** giảm Redis round trip; khó invalidation xuyên nhiều instances.

Theo dõi **hit ratio theo tầng và theo route**, không lấy một tỷ lệ 95% toàn hệ thống rồi kết luận GET sản phẩm hoặc GET đơn hàng đều đang nhanh/đúng.

### 2.2. Chọn mô hình phù hợp với dữ liệu

| Nhóm tài nguyên | Cách tiếp cận gợi ý | Ranh giới |
|---|---|---|
| Ảnh và asset có URL version/hash | Public CDN cache dài hạn, immutable | Khi đổi nội dung phải đổi URL/version |
| Catalog công khai, thay đổi có kiểm soát | CDN + Redis, TTL ngắn, purge/version khi cập nhật | Giá hiển thị có thể cũ trong giới hạn công bố |
| Đơn hàng của cá nhân | **Private/no-store** tại HTTP, app cache nếu ACL/key chặt | Không để tenant khác nhận cùng cached object |
| Số dư/quyền truy cập/giá chốt thanh toán | Ưu tiên nguồn đáng tin, caching rất thận trọng | Không dựa vào catalog cache để thu tiền |
| Báo cáo tổng hợp | Precompute/cache theo version/filter | Cần quy định “as-of time” và kiểm dữ liệu sau backfill |

Quyết định cuối phải dựa vào **độ nhạy cảm, tần suất ghi, khả năng chịu stale, chi phí truy vấn và yêu cầu consistency**. Không buộc mọi route phải dùng cùng TTL.

## 3. HTTP cache semantics: freshness và validation không giống nhau

HTTP caching chủ yếu áp dụng cho các response có thể lưu/tái sử dụng theo quy tắc; **GET/HEAD** là trường hợp quen thuộc. Với REST API, các response **200 OK** của GET có thể được cache khi policy cho phép; cache có thể trả nội dung mà không cần gọi origin nếu còn fresh.

### 3.1. Các directive quan trọng

| Directive | Ý nghĩa thực hành |
|---|---|
| **Cache-Control: max-age=60** | Freshness tối đa 60 giây tính theo tuổi response |
| **Cache-Control: s-maxage=120** | Freshness cho **shared cache** như CDN, có ưu tiên so với max-age ở shared cache |
| **Cache-Control: public** | Cho phép shared cache lưu response khi quy tắc khác cho phép; không làm dữ liệu nhạy cảm thành an toàn |
| **Cache-Control: private** | Shared cache **không được lưu** response; private browser cache có thể lưu |
| **Cache-Control: no-cache** | **Có thể lưu**, nhưng phải **revalidate thành công** trước mỗi lần tái sử dụng |
| **Cache-Control: no-store** | Cache tuân thủ chỉ thị không lưu request/response được chỉ định; chọn cho dữ liệu nhạy cảm |
| **Cache-Control: must-revalidate** | Không dùng response stale khi cần revalidate mà không thể, theo quy tắc HTTP |
| **stale-while-revalidate** | Cho phép phục vụ stale trong thời gian giới hạn khi đang revalidate, nếu cache hỗ trợ và contract chấp nhận |
| **stale-if-error** | Cho phép phục vụ stale trong một khoảng khi gặp lỗi, nếu cache hỗ trợ và policy cho phép |

**no-cache không có nghĩa không lưu.** Nếu mục tiêu là không để browser/CDN giữ thông tin đơn hàng bí mật, **no-store** phù hợp hơn. **private không tự cấm browser cache**; với thông tin phiên/người dùng nhạy cảm vẫn cần cân nhắc no-store.

~~~http
GET /api/products/BOOK-01 HTTP/1.1
Host: api.example.test
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60, s-maxage=120
ETag: "product-BOOK-01-v18-json"
Vary: Accept-Encoding

{"sku":"BOOK-01","name":"Java API Design","priceMinor":350000}
~~~

Ở đây browser có thể coi bản thể fresh trong khoảng 60 giây; shared CDN có thể dùng s-maxage 120 giây. **ETag không làm hai TTL biến thành đồng nhất**. Nếu yêu cầu khách nhìn thấy giá mới ngay sau cập nhật, chỉ purge CDN là chưa đủ khi browser vẫn đang có bản thể fresh.

**Tuổi thực của response** còn chịu tác động Date, Age, thời gian truyền, heuristic và quy tắc cache HTTP. Không suy “bắt đầu TTL từ khi ứng dụng Spring trả body” khi response đã ở CDN trong vài chục giây. Có thể dùng **Age** để điều tra một cache hit ở shared proxy.

### 3.2. Conditional GET với ETag

Khi bản thể stale, client có thể hỏi server xem phiên bản đã đổi chưa:

~~~http
GET /api/products/BOOK-01 HTTP/1.1
If-None-Match: "product-BOOK-01-v18-json"
Accept: application/json

HTTP/1.1 304 Not Modified
ETag: "product-BOOK-01-v18-json"
Cache-Control: public, max-age=60, s-maxage=120
Vary: Accept-Encoding
~~~

**304 không có response body.** Cache/client kết hợp metadata của 304 với bản thể cũ phù hợp để dùng tiếp; 304 **không tự chứng minh bản thể là mới nhất trong DB** nếu server so ETag từ một bản sao Redis cũ.

Sau khi đổi giá và cập nhật phiên bản:

~~~http
GET /api/products/BOOK-01 HTTP/1.1
If-None-Match: "product-BOOK-01-v18-json"
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-BOOK-01-v19-json"
Cache-Control: public, max-age=60, s-maxage=120

{"sku":"BOOK-01","name":"Java API Design","priceMinor":320000}
~~~

Với GET, If-None-Match dùng **weak comparison** theo HTTP semantics; server phải xử lý danh sách ETags và dấu **\*** đúng chuẩn, không chỉ so chuỗi header đơn giản. Với **If-Match** để chống ghi đè, cần **strong comparison**: ETag yếu (W/) không phù hợp làm điều kiện optimistic update. ETag cần đại diện **selected representation**, có thể khác theo Content-Encoding, ngôn ngữ hoặc projection; không tái dùng một validator sai biến thể.

**Last-Modified / If-Modified-Since** là lựa chọn validator khác; độ chính xác thường ở mức giây, nên hai lần cập nhật trong cùng giây có thể không được phân biệt nếu chỉ dựa vào timestamp. Với cập nhật thường xuyên hoặc yêu cầu chặt, ưu tiên **ETag version đúng semantics**. Không tự lấy thời gian hệ thống của JVM làm Last-Modified khi nó không gắn với phiên bản dữ liệu.

### 3.3. Caching khác optimistic concurrency

~~~http
PATCH /api/products/BOOK-01 HTTP/1.1
Authorization: Bearer <admin-token>
Content-Type: application/merge-patch+json
If-Match: "product-BOOK-01-v18-json"

{"priceMinor":320000}
~~~

Nếu nguồn sự thật đã ở v19, precondition v18 không còn đúng: trả **412 Precondition Failed** và **không ghi đè**. Nếu caller không có quyền thay giá, từ chối **403/404 theo policy** trước khi tiết lộ thông tin version. **If-Match/412 bảo vệ cạnh tranh ghi**, còn **If-None-Match/304 giảm tải đọc**; chúng liên quan nhưng không thay nhau.

HTTP cache có thể tự vô hiệu các stored responses cho target URI khi unsafe method nhận phản hồi hợp lệ theo quy tắc HTTP caching, **nhưng điều đó không bảo đảm mọi lớp Redis, CDN khác hoặc browser tab đều đã purge**. Thiết kế invalidation ứng dụng vẫn cần rõ ràng.

### 3.4. Vary và các biến thể bản thể

Ví dụ một response khác nhau theo **Accept-Language** phải khai báo **Vary: Accept-Language**, nếu không cache có thể phục vụ bản tiếng Việt cho client mong tiếng Anh. **Vary: Accept-Encoding** có thể cần cho representation nén; với CORS phản chiếu origin từ allowlist, cân nhắc **Vary: Origin**.

**Không dựa vào Vary: Authorization như giải pháp tổng quát để lưu cache chung cho dữ liệu cá nhân.** Shared cache và authenticated responses có quy tắc riêng, policy proxy tùy sản phẩm; cách an toàn cho đơn hàng hoặc profile riêng tư thường là **Cache-Control: private/no-store**, auth và ACL tại server, key nội bộ có tenant/subject khi thực sự cần cache.

## 4. Sau khi thay đổi: định nghĩa “cache còn hiệu lực” bằng bất biến

Để đánh giá invalidation, phải xác định **mốc ghi đã hoàn tất** và mức nhất quán sản phẩm cần. Có ba mức phổ biến:

1. **Bounded staleness:** dữ liệu có thể cũ tối đa N giây. Phù hợp catalog/ảnh được version hóa, nơi thay đổi không nhất thiết phải thấy ngay.
2. **Read-your-writes:** người vừa thực hiện PATCH thành công **phải thấy bản mới** ở lần đọc tiếp theo qua luồng được bảo đảm, dù người dùng khác có thể thấy bản cũ trong giới hạn. Cần giải pháp đồng nhất session/version hoặc bypass cache.
3. **Strong/linearizable visibility:** sau khi cập nhật commit, mọi lượt đọc mới trong phạm vi cam kết phải thấy phiên bản mới. Rất khó khi có nhiều browser/CDN/replica; có thể cần **không cache**, đọc từ leader hoặc điều phối version chặt chẽ.

**Nói “cache được xóa sau khi update” chưa phải contract.** Với nhiều tầng, xóa tầng A có thể hoàn thành muộn hơn trả HTTP 200 của PATCH; một read từ tầng B vẫn trả cũ. Hãy ghi rõ **độ trễ propagation**, hành vi khi purge thất bại và cách xác minh.

### 4.1. Ma trận chính sách theo hành vi nghiệp vụ

| Thao tác | Mức mới dữ liệu mong muốn | Hệ quả triển khai |
|---|---|---|
| GET thông tin sản phẩm công khai | Chấp nhận cũ ≤60 giây | TTL hữu hạn, purge CDN tối ưu |
| PATCH giá trong backoffice, GET lại ngay | Read-your-writes cho admin | Sau commit đọc version mới từ nguồn đáng tin, bypass cache cũ |
| POST checkout với giá từ catalog | Giá **được chốt server-side** tại thời điểm quy định | Không tin giá từ browser/CDN; tính lại dựa trên dữ liệu phù hợp |
| GET đơn hàng người mua | Không lộ sai tenant, hiển thị trạng thái đủ mới | Authorization mỗi request, no-store/private, tránh shared cache |
| GET inventory phục vụ giữ chỗ | Nhất quán theo quy tắc reservation | Không xem cached số lượng là bảo đảm đặt hàng thành công |

Một hệ thống có thể có hai cửa sổ nhất quán: **catalog public** chịu stale vài chục giây, nhưng **đường thanh toán** phải đọc dữ liệu đã được kiểm định riêng. Việc tăng TTL giúp tăng hit ratio không được tự động thay đổi invariant của checkout.

### 4.2. Một cập nhật đi qua những tầng nào?

~~~mermaid
sequenceDiagram
    participant A as Admin client
    participant S as Spring API
    participant D as Database
    participant R as Redis cache
    participant C as CDN
    participant B as Browser khác
    A->>S: PATCH product (If-Match v18)
    S->>D: UPDATE price, revision=19
    D-->>S: COMMIT
    S->>R: Evict old key / publish version
    S->>C: Purge path or surrogate key
    S-->>A: 200 v19
    B->>C: GET product
    C-->>B: 200 v18 nếu purge chưa đến
    Note over S,C: Cần SLA propagation hoặc versioned URL/key
~~~

Sơ đồ **minh họa một thứ tự**, không bảo đảm Spring sẽ đợi Redis/CDN purge trước khi trả 200. Nếu CDN purge có độ trễ hoặc thất bại, người khác vẫn có thể nhận v18. Cần **chọn hợp đồng thực tế**: ví dụ kết quả PATCH chỉ cam kết DB commit, còn dữ liệu công khai cập nhật trong tối đa 60 giây; hoặc việc phát hành giá mới buộc hoàn tất purge/switch version trước khi công bố.

### 4.3. Evict trước hay sau commit?

**Evict trước khi transaction commit** nguy hiểm:

~~~text
T1: Evict cache key product/BOOK-01
T2: GET cache miss -> đọc DB giá cũ v18 -> fill cache v18
T3: UPDATE commit giá mới v19
T4: Cache vẫn lưu v18
~~~

Evict **sau commit** tránh trường hợp đơn giản này, nhưng vẫn có race khác:

~~~text
T1: GET cache miss, bắt đầu đọc DB v18 (chậm)
T2: UPDATE commit v19
T3: Invalidate key v18
T4: GET cũ hoàn tất và ghi v18 vào cache (stale refill)
~~~

Điều này giải thích vì sao **transactional AFTER_COMMIT eviction + TTL** thường là *eventual consistency*, không tự bảo đảm mọi read sau commit đều đúng. Có thể dùng **versioned cache keys**, kiểm version trước khi fill, optimistic compare-and-set ở cache, serializing update/read qua cùng coordinator hoặc bypass caching trên tuyến đòi mạnh; lựa chọn tùy correctness target.

### 4.4. Versioned keys và generation

Thay vì chỉ dùng key cố định:

~~~text
catalog:BOOK-01             -> bản thể v18/v19 thay nhau
~~~

Có thể dùng:

~~~text
catalog:BOOK-01:revision:18 -> immutable v18
catalog:BOOK-01:revision:19 -> immutable v19
catalog-current:BOOK-01     -> revision 19
~~~

Khi đọc, phải **lấy current revision từ nguồn đủ mới và đáng tin**. Nếu chính con trỏ **catalog-current** bị cache stale, việc chuyển sang versioned keys vẫn có thể trả v18. Sau commit cần cập nhật con trỏ atomically hoặc bảo đảm read từ DB/version service, và có chính sách TTL/garbage collection cho keys cũ.

Versioned asset URLs (ví dụ /static/app.a1b2c3.js) dễ áp dụng hơn: nội dung bất biến, cập nhật chỉ thay URL ở HTML/manifest. Với tài nguyên nghiệp vụ **cùng URI nhưng nội dung thay đổi**, ETag/version phải được quản lý theo selected representation và invalidation.

### 4.5. Cache-aside, write-through, write-behind

| Mô hình | Cách làm | Đánh đổi |
|---|---|---|
| **Cache-aside** | Read cache → miss load DB → put; update DB và evict | Đơn giản, phổ biến; có race refill, miss storm |
| **Write-through** | Write cache + nguồn dữ liệu trong đường ghi | Cần thiết kế thứ tự/atomicity; cache success chưa chắc DB commit |
| **Write-behind** | Ghi cache trước, DB theo lô/bất đồng bộ | Tăng throughput nhưng có nguy cơ mất ghi và lệch nguồn sự thật |
| **Refresh-ahead** | Chủ động làm mới gần TTL | Giảm miss nhưng có thể giữ stale khi nguồn thay đổi |
| **Read-through** | Cache provider tự gọi loader | Giảm boilerplate; không tự giải quyết multi-tier invalidation |

Với REST API có giao dịch tiền, tồn kho hoặc trạng thái đơn, tránh xem write-behind cache là nơi lưu **trạng thái giao dịch đã cam kết** nếu không có durability, ordering và recovery semantics rõ.

## 5. Đồng bộ thay đổi giữa nhiều replica và CDN

Khi nhiều pod Spring dùng Redis chung, **evict trên Redis** có thể xóa một bản sao mà mọi pod cùng đọc. Nhưng nếu mỗi pod còn local Caffeine cache, cần phát thông báo invalidation tới tất cả pods hoặc dùng TTL/version; nếu một pod không nhận event, nó có thể tiếp tục trả stale.

### 5.1. Transactional outbox và thứ tự sự kiện

Nếu cần đẩy invalidation sang message broker/CDN:

1. Trong **một database transaction**, ghi bản thể v19 **và outbox event** chứa resource ID/revision.
2. Sau commit, outbox relay công bố **ProductChanged(sku=BOOK-01, revision=19)**.
3. Cache consumers evict/version advance một cách **idempotent**; CDN invalidator yêu cầu purge theo path/surrogate key.
4. Theo dõi retry, dead-letter và **invalidation lag**; không coi gửi event thành công là CDN đã purge.

~~~text
DB TX: UPDATE products revision=19
       INSERT outbox(product_changed, sku=BOOK-01, revision=19)
       COMMIT

Outbox relay -> Redis invalidation / CDN purge / projection refresh
              -> acknowledge with retry + observability
~~~

Event có thể đến **trễ, trùng hoặc sai thứ tự**. Không cho event revision=18 đến muộn làm “đưa con trỏ hiện tại” từ 19 về 18; dùng revision monotonic và kiểm khi apply. Cũng cần xử lý trường hợp **tạo mới, xóa, khôi phục hoặc đổi visibility**: purge chỉ một URI có thể chưa đủ nếu dữ liệu xuất hiện trong collection search, thống kê, filter và page cache.

### 5.2. Invalidation theo resource, collection và biến thể

Đổi giá BOOK-01 có thể ảnh hưởng:

- GET /api/products/BOOK-01 và các ngôn ngữ/encoding khác nhau.
- GET /api/products?category=books&sort=price hoặc search pages.
- Khối “sản phẩm liên quan”, recommendations hoặc báo cáo tổng hợp.
- Thẻ HTML/JSON được CDN cache và bản thể đã lưu ở browser.

Có hai cách phổ biến: **purge theo dependency/surrogate tags** (nếu CDN hỗ trợ) hoặc **generation key** cho các tập liên quan. Purge theo URI đơn lẻ thường bỏ sót query variants, còn flush toàn bộ cache gây **cache stampede**. Thiết kế dependency graph ở mức đủ kiểm soát và có TTL fallback.

### 5.3. Giới hạn tối đa khi event thất bại

Với catalog chấp nhận stale tối đa 60 giây, TTL **60 giây ở mọi tầng** có thể là một fallback, **nhưng không đơn giản cộng/so TTL độc lập để tuyên bố stale ≤60 giây kể từ commit**. Cache thấp hơn có thể nhận v18 ngay trước khi nó hết hạn, làm mới bản sao v18 tại tầng trên và kéo dài stale qua nhiều giai đoạn.

Để cam kết “≤60 giây từ thời điểm thay đổi DB”, cần kiểm **max staleness end-to-end**: source version age, TTL của từng tầng, cách reset TTL khi refill, cơ chế event/purge và độ trễ queue. Có thể gắn **updated_at/revision** hoặc **data-as-of** có thể xác minh để giới hạn tuổi dữ liệu thật. Tránh tăng tuổi bản thể lên “fresh thêm 60 giây” ở mỗi tầng mà không xét timestamp gốc.

**Khi purge thất bại**, sản phẩm phải chọn rõ: tạm đóng cache, trả dữ liệu cũ kèm cảnh báo theo contract, hoặc chặn một số thao tác nhạy cảm. Hệ thống thanh toán không được lặng lẽ tin giá cũ chỉ vì CDN chưa cập nhật.

## 6. Java/Spring: cache-aside cho catalog công khai

Giả sử chọn **Redis** làm một tầng cache chung cho nhiều Spring instances, còn response GET sản phẩm công khai có HTTP TTL 60 giây. Spring Cache abstraction giúp viết cache-aside ngắn gọn, nhưng cần hiểu chính xác những gì annotation **có** và **không** bảo đảm.

### 6.1. Read service với @Cacheable

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

record CatalogView(
        String sku, String name, long priceMinor, long revision) {}

interface CatalogRepository {
    CatalogEntity getRequired(String sku);
    CatalogEntity getForUpdate(String sku);
}

@Service
class CatalogReadService {
    private final CatalogRepository repository;

    CatalogReadService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "catalogBySku",
               key = "#p0", sync = true)
    public CatalogView find(String sku) {
        CatalogEntity entity = repository.getRequired(sku);
        return new CatalogView(entity.sku(), entity.name(),
            entity.priceMinor(), entity.revision());
    }
}
~~~

Đây là **Java fragment**: CatalogEntity/repository/exception mapping cần định nghĩa trong ứng dụng. Bật **@EnableCaching** và cấu hình **CacheManager** cụ thể; nếu không Spring sẽ không áp cache interceptor như mong muốn. Không dùng JPA entity gắn session làm cached response; DTO bất biến dễ quản lý serialization và tránh lộ fields nội bộ.

- **key = #p0** (đối số thứ nhất, SKU) an toàn **chỉ vì catalog công khai** có cùng representation cho mọi caller. Nếu dữ liệu theo tenant/locale/currency/role, phải đưa dimensions đó vào key hoặc **không cache ở tầng dùng chung**.
- **sync=true** yêu cầu provider hỗ trợ synchronized loading cho cùng key; có thể giảm stampede **trong phạm vi mà provider bảo đảm**, không mặc nhiên lock xuyên mọi pod/CDN.
- TTL, max size, serializer và Redis connection policy **không nằm trong @Cacheable**. Phải cấu hình CacheManager/Redis và test TTL thực.
- Spring cache advice thường dựa vào **proxy**; method tự gọi từ cùng class có thể **bỏ qua @Cacheable**. Kiểm qua bean proxy và hit/miss thật, không chỉ đọc annotation.

### 6.2. Controller GET với Cache-Control và conditional request

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.WebRequest;

@RestController
@RequestMapping("/api/products")
class CatalogController {
    private final CatalogReadService catalog;

    CatalogController(CatalogReadService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{sku}")
    ResponseEntity<CatalogView> get(
            @PathVariable String sku, WebRequest request) {
        CatalogView view = catalog.find(sku);
        String etag = "\"catalog-" + sku
            + "-revision-" + view.revision() + "\"";
        CacheControl policy = CacheControl
            .maxAge(60, TimeUnit.SECONDS).cachePublic();

        if (request.checkNotModified(etag)) {
            return ResponseEntity.status(304)
                .eTag(etag).cacheControl(policy).build();
        }
        return ResponseEntity.ok()
            .eTag(etag).cacheControl(policy).body(view);
    }
}
~~~

**Lưu ý về ETag:** code giả định revision tăng khi **bất kỳ field nào trong JSON công khai** thay đổi và response không có các biến thể selected representation khác. Nếu JSON phụ thuộc locale, currency, fields selection hay Content-Encoding, strong ETag phải phản ánh **từng representation** (hoặc dùng weak validator khi phù hợp). Đừng giữ một ETag mạnh giống nhau cho hai byte representations khác nhau. Khi **CatalogReadService đang đọc v18 từ Redis lỗi thời**, method checkNotModified có thể trả **304 sai sau khi DB đã v19**; Spring xử lý điều kiện HTTP đúng cú pháp nhưng không biết cache nội bộ đã stale.

**WebRequest.checkNotModified** xử lý conditional request theo Spring Web framework thay vì tự so một chuỗi If-None-Match; việc trả ResponseEntity 304 trong nhánh trên làm ý định rõ ràng. Controller không phải nơi **bảo đảm** freshness của Redis/CDN; đó là invariant ở tầng dữ liệu và cache orchestration.

Với response chứa giá cá nhân/discount riêng theo account, **không dùng cachePublic()** và không trả cùng key cho tất cả users. Chọn private/no-store hoặc một cơ chế versioned, scoped cache đã có thiết kế bảo mật.

### 6.3. Ghi DB rồi evict sau commit

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

record CatalogChanged(String sku, long revision) {}

@Service
class CatalogWriteService {
    private final CatalogRepository repo;
    private final ApplicationEventPublisher events;

    CatalogWriteService(CatalogRepository repo,
                        ApplicationEventPublisher events) {
        this.repo = repo;
        this.events = events;
    }

    @Transactional
    public void updatePrice(
            String sku, long newPriceMinor, long expectedRevision) {
        CatalogEntity product = repo.getForUpdate(sku);
        if (product.revision() != expectedRevision) {
            throw new StaleRevisionException();
        }
        product.setPriceAndIncrementRevision(newPriceMinor);
        // JPA dirty checking/flush hoặc repository save theo implementation.
        events.publishEvent(
            new CatalogChanged(sku, product.revision()));
    }
}

@Component
class CatalogEviction {
    private final CacheManager cacheManager;

    CatalogEviction(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void evict(CatalogChanged changed) {
        Cache cache = cacheManager.getCache("catalogBySku");
        if (cache != null) cache.evict(changed.sku());
    }
}
~~~

**StaleRevisionException** và CatalogEntity là types thuộc ứng dụng; phải map thành HTTP **412 Precondition Failed** khi client gửi If-Match không đúng. Để thực thi đúng HTTP, controller còn cần xác thực, kiểm scope/role/tenant, parse **strong If-Match** và không để caller lấy phiên bản từ dữ liệu không đáng tin. Với resource công khai ở ví dụ này, quyền ghi chỉ dành cho admin đã được xác minh.

Sự kiện Spring AFTER_COMMIT ở trên chỉ là **in-process event**, không bảo đảm CDN purge, local caches ở các instances khác hoặc delivery sau khi process chết. Nếu Redis là CacheManager dùng chung, evict key Redis có tác dụng cho các readers cùng namespace; nếu dùng local cache riêng, phải có invalidation kèm. Muốn chắc chắn truyền thay đổi ra ngoài tiến trình, thêm **durable transactional outbox** hoặc cơ chế tương đương.

**Phạm vi nhất quán:** ví dụ chỉ bảo đảm cache eviction được yêu cầu sau commit khi listener chạy. Nó **không** loại race stale refill ở mục 4; với cập nhật buộc thấy ngay, thêm versioned cache key, CAS hoặc bypass cache theo operation. Không biến “@TransactionalEventListener” thành lời hứa strong consistency.

### 6.4. Cache configuration không nên bị bỏ quên

Một cấu hình Redis CacheManager mẫu để quy định TTL/cache serialization:

~~~java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
class CatalogCacheConfig {
    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {
        RedisCacheConfiguration config =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofSeconds(60))
                .disableCachingNullValues();
        return RedisCacheManager.builder(factory)
            .cacheDefaults(config)
            .build();
    }
}
~~~

Đây là **minh họa Spring Data Redis**, không cấu hình đầy đủ serializer/type compatibility, TLS/authentication, connection pool, namespace prefix, maxmemory policy và migration khi đổi schema DTO. **Giới hạn TTL ở Redis không phải TTL trên CDN/browser**. Kiểm serialize/deserialize record với Redis client và Spring Data Redis version thực tế; tránh đưa dữ liệu JWT/PII vào shared Redis hoặc để key trùng giữa môi trường dev/prod.

## 7. Cache key là một phần của ranh giới bảo mật và đúng dữ liệu

Một cache key đúng phải phân biệt mọi yếu tố **làm thay đổi selected representation** hoặc quyền nhìn thấy dữ liệu. Ví dụ URL:

~~~http
GET /api/orders?status=OPEN&sort=createdAt,desc&limit=20 HTTP/1.1
Authorization: Bearer <token-of-tenant-A>
Accept-Language: vi
~~~

Cache key ngây thơ **"/api/orders"** sẽ làm lẫn bộ lọc, phân trang, tenant và ngôn ngữ. Một key ứng dụng có kiểm soát có thể gồm:

~~~text
apiVersion=v2
operation=orders.list
verifiedTenant=tenant-A
verifiedSubject=buyer-17 (nếu quyền theo người)
policyVersion=acl-42
filter=status:OPEN
sort=createdAt:desc,id:desc
cursor=<validated and canonicalized cursor>
limit=20
locale=vi
representation=json-v3
~~~

Các giá trị tenant/subject/policyVersion phải lấy từ **identity/policy đã xác minh**, không nhận từ query/header client tự đặt. **Không đưa raw Authorization token vào key**, vì rò rỉ và churn; nếu dùng hash/token-derived key, cần threat model, giới hạn log và chiến lược thu hồi. Với ACL phức tạp, việc xác định key an toàn khó hơn lợi ích cache: ưu tiên **không cache danh sách riêng tư ở shared layer**.

### 7.1. Canonicalization tránh cache fragmentation và poisoning

Hai request có thể cùng ngữ nghĩa nhưng khác thứ tự query:

~~~text
GET /api/products?category=books&limit=20
GET /api/products?limit=20&category=books
~~~

Nếu canonicalize, phải phân biệt trường hợp **query keys trùng lặp**, **case sensitivity**, percent-encoding, filter mặc định và cursor. Chỉ chuẩn hóa khi logic API đã định nghĩa tương đương; không merge hai truy vấn vốn khác ngữ nghĩa. Không để header **Host, X-Forwarded-Host, X-Original-URL** do caller không tin cậy điều khiển cache namespace hoặc redirect của cached response.

### 7.2. Authorization có thể thay đổi mà object không đổi

Ví dụ user A từng được giao xem order X, sau đó bị thu hồi quyền. Order version vẫn v19, ETag cũng không đổi, nhưng A **không được nhận 304** để tiếp tục dùng cached body. Nếu endpoint hỗ trợ conditional GET riêng tư, phải **xác thực và kiểm quyền trước khi so validator**, xử lý cache security và invalidation khi membership thay đổi.

Với dữ liệu thật sự riêng tư, trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-17","status":"CONFIRMED"}
~~~

**Không lưu response riêng tư ở public CDN** chỉ vì nó là GET. Sử dụng **Cache-Control: no-store** thường đơn giản và an toàn hơn so với cố gắng giải bài toán cache đa tenant có ACL thay đổi liên tục.

**Thay response sang no-store không tự xóa bản sao đã được lưu dưới chính sách cũ.** Khi sửa lỗi cấu hình cache gây lộ dữ liệu, phải đánh giá purge/thu hồi bản sao ở CDN/browser theo năng lực thực tế và xử lý sự cố bảo mật, không chỉ deploy header mới rồi kết luận đã khắc phục.

### 7.3. Cache và request có side effects

**GET phải safe**; dùng GET để hủy đơn hoặc thay trạng thái sẽ khiến prefetch, CDN/revalidation và crawler vô tình gây side effect. Với **POST**, Idempotency-Key xử lý **cùng ý định nghiệp vụ bị retry**, không phải HTTP response cache cho GET. Không dùng cache key dựa trên request body để “dedup” thanh toán thay cho **durable idempotency ledger** với fingerprint, scope và transaction.

Với **PUT/PATCH/DELETE**, request cần authentication, authorization và concurrency control; sau commit mới phát invalidation. Xóa tài nguyên có thể tạo **404 hoặc 410** theo hợp đồng; negative caching cho “không tồn tại” phải có TTL và invalidation khi resource được tạo lại.

## 8. Quy trình kiểm tra hiệu lực sau PATCH/PUT/DELETE

Một kỹ sư không thể chỉ gọi GET từ **chính app instance vừa ghi** rồi kết luận cache đa tầng đã cập nhật. Phép kiểm phải có **baseline, update, visibility point, các đường đọc và điều kiện thành công**.

### 8.1. Giao thức thử nghiệm đọc sau ghi

Giả sử GET public product trả **v18**, PATCH đã được admin thực hiện hợp lệ và DB commit **v19**:

1. **Baseline:** gọi GET qua browser/edge/gateway và origin; lưu ETag, giá, Age, Cache-Control, Vary, CDN cache status nếu provider công bố.
2. **Write:** thực hiện PATCH hoặc PUT có **If-Match: "catalog-BOOK-01-revision-18"** và token admin hợp lệ; kiểm status 200/204, transaction commit và DB revision=19.
3. **Origin check:** đọc qua tuyến **bypass các cache được phép bypass trong môi trường test**, xác minh revision=19, priceMinor=320000.
4. **Application cache check:** gọi nhiều pods có Redis/local cache, xác minh không trả lại v18 sau mốc consistency mà hợp đồng hứa.
5. **Edge check:** GET qua CDN từ nhiều điểm/POP nếu cần, với request bình thường và một request **conditional** sử dụng ETag v18.
6. **Client check:** browser đã lưu v18 phải nhận **200 v19** khi revalidate, hoặc chỉ được phục vụ v18 tới hết khoảng stale cho phép nếu còn fresh.
7. **Negative/security check:** người không có quyền phải nhận 401/403/404 phù hợp, **không được nhận 304 làm lộ sự tồn tại hoặc giữ dữ liệu đã mất quyền**.
8. **Recovery check:** giả lập Redis timeout, CDN purge failure hoặc event duplicate; xác minh deadline/khả năng tự phục hồi và cảnh báo.

**Tránh “cache bust” như ?random=... để giả vờ invalidation đạt.** Nó thường tạo một cache key mới rồi đọc mới, **không chứng minh key cũ đã hết hiệu lực**. Cache bust có thể dùng để chẩn đoán nguồn gốc response hoặc tạm khắc phục, nhưng bài test phải kiểm **URI/key thực mà người dùng đang dùng**.

### 8.2. Ma trận kết quả của conditional GET sau thay đổi

| Tình huống | If-None-Match do client gửi | Kết quả kỳ vọng |
|---|---|---|
| Source vẫn v18, caller còn quyền, validator phù hợp | ETag v18 | **304** không body |
| Source đã v19, cache đã cập nhật đúng | ETag v18 | **200 v19**, ETag v19 |
| Source đã v19, client gửi ETag v19 | ETag v19 | **304** không body |
| Client không gửi validator | Không có | **200** body, theo freshness/cache policy |
| User mất quyền trên order dù representation không đổi | ETag đã giữ trước đó | **403/404** theo policy, không 304 |
| Resource bị xóa | ETag trước khi xóa | **404/410** theo contract, không 304 |
| Gateway/Redis vẫn chỉ biết v18 | ETag v18 | Có thể trả **304 sai về freshness** — lỗi phải được phát hiện |

**Kiểm tra hiệu lực** khác với yêu cầu 304 lúc nào cũng phải trở thành 200 sau một thay đổi. Nếu API cho phép **bounded staleness**, CDN có thể phục vụ v18 trong TTL đã công bố. Test cần đánh giá **thời điểm bắt buộc v19 xuất hiện**, không kết luận sai chỉ vì một response trong cửa sổ stale hợp lệ.

### 8.3. Read-your-writes cho người chỉnh sửa

Một chiến lược thực tế khi admin vừa đổi giá:

~~~text
PATCH /api/products/BOOK-01  -> DB commit revision 19
Server trả revision/ETag 19  -> Admin giữ expectedMinVersion=19
Admin GET ngay              -> Bypass stale shared cache hoặc
                               yêu cầu version >=19 tại origin
Nếu cache chỉ có revision 18 -> Không trả stale, đọc nguồn đủ mới
~~~

Cách này đòi **đường đọc có biết expected version** và nguồn phiên bản đáng tin, không đơn giản thêm header tự phát rồi mong mọi CDN hiểu. Có thể thực hiện bằng admin API riêng với **Cache-Control: no-store**, query nguồn chính, hoặc versioned resource endpoint. **Không để client tự tuyên bố dữ liệu đúng**: server phải so min version trên dữ liệu được xác minh.

### 8.4. Sau xóa và tạo lại: negative caching dễ bị quên

Nếu cache 404 cho GET /api/products/BOOK-99 trong 5 phút, rồi POST tạo BOOK-99 sau 10 giây, client có thể vẫn nhận 404 từ negative cache. Vì vậy phải:

- Định nghĩa **negative TTL** ngắn và phạm vi key cụ thể.
- Invalidate negative entries khi create/restore thành công.
- Không cache 404 do **authorization che giấu resource** như một shared negative response cho mọi principal.
- Phân biệt 404/410 tùy contract; **410 Gone** cũng có chính sách cache riêng cần suy xét.

Với HTTP 304 sau delete, test chắc chắn **không xác nhận lại ETag cũ** chỉ vì key Redis chưa evict. Nếu bảo đảm strong read-after-delete, cần bỏ qua mọi tầng còn có thể giữ phiên bản cũ.

## 9. Tối ưu hiệu năng mà không tự tạo lỗi tải

### 9.1. Latency, hit ratio và cost

Giả sử trước khi thêm cache, GET sản phẩm có p95 **180 ms**; sau khi có Redis, p95 **35 ms** trong một load test có cùng traffic. Đây là tín hiệu tốt, nhưng cần so:

| Chỉ số | Vì sao cần |
|---|---|
| **Hit ratio theo tầng/route** | Biết browser, CDN, Redis hay local cache tạo hiệu quả |
| **Miss latency/p95/p99** | Cache miss có thể đắt hơn trước vì contention hoặc serialization |
| **Backend QPS và DB connection pool** | Cache có thật sự giảm tải nguồn không? |
| **Eviction/invalidation lag** | Độ cũ sau thay đổi có nằm trong hợp đồng không? |
| **Stale responses sau commit** | Tỷ lệ/độ trễ trả v18 khi DB đã v19 |
| **Cache memory, eviction, key count** | Bị churn/thrashing/overflow hay không? |
| **Redis errors/timeouts, CDN origin errors** | Failure mode có làm tăng tail latency không? |
| **Business correctness** | Số lần sai giá, sai tenant, stale authorization, charge trùng |

**Hit ratio = hit/(hit + miss)** theo phạm vi đo, nhưng khi cache ở CDN hit thì app không thấy request. Đừng lấy cache hit ratio làm SLI chất lượng cho checkout; **p95/p99 và correctness** quan trọng hơn.

Nếu miss load DB mất 150 ms, Redis hit mất 3 ms và hit ratio 90%, latency kỳ vọng lý tưởng gần **17,7 ms** ở tầng đó (chưa tính các overhead khác). Đây chỉ là mô hình đơn giản; tail latency dưới tải, hàng đợi và stampede có thể phá giả định độc lập.

### 9.2. Cache stampede và synchronized loading

Một key hot vừa hết TTL có thể khiến 1.000 request đồng thời đều gọi database. Kỹ thuật giảm:

- **Single-flight/per-key coalescing:** một loader thực thi, các request còn lại chờ/kết quả dùng chung; xác minh phạm vi lock local/distributed.
- **TTL jitter:** phân tán thời điểm hết hạn, tránh hàng loạt keys cùng expire.
- **Refresh-ahead:** làm mới trước hạn khi dữ liệu được phép stale trong giới hạn và nguồn chịu được.
- **Bounded stale serving:** stale-while-revalidate/stale-if-error có giới hạn **nếu hợp đồng chấp nhận**.
- **Concurrency limiter:** giới hạn số miss đi vào DB, queue/timeout hợp lý; tránh thả vô hạn.

Không dùng stale-if-error cho quyền truy cập đã thu hồi, số dư nhạy cảm hoặc giá chốt thanh toán chỉ vì nó cải thiện availability. Nếu sử dụng **stale-while-revalidate**, đo thời gian stale thực tế và điều kiện refresh thất bại; mọi lớp cache đều có thể nới độ cũ hơn kỳ vọng.

### 9.3. Negative cache và cache poisoning

**Negative caching** 404/empty có thể giảm truy vấn ID không tồn tại, nhưng dễ gây sai sau create, backfill hoặc thay quyền. **Cache poisoning** xảy ra khi một request không đáng tin ảnh hưởng cache key/response khiến người khác nhận nội dung sai. Bảo vệ bằng canonicalization, xác thực Host/forwarded headers, giới hạn kích thước keys, Content-Type và validation cho origin/currency/language, tránh để response công khai chứa thông tin từ Authorization context.

Khi Redis không sẵn sàng, hệ thống có thể **fallback DB** với circuit breaker/concurrency limit, nhưng phải tránh chuyển sự cố Redis thành stampede DB. Với tuyến nhạy cảm, nếu không thể bảo đảm freshness/authorization thì **fail closed hoặc trả 503** an toàn hơn phục vụ bản stale không kiểm chứng.

### 9.4. Load test phải có pha đọc, ghi và lỗi

Một bài benchmark chỉ bắn GET lặp lại cùng SKU sẽ tạo **hot cache 100%**, không phản ánh thực tế. Nên có:

1. **Warm-up:** làm rõ trạng thái cache cold/warm, reset metrics có kiểm soát.
2. **Traffic mix:** nhiều SKU hot/cold, queries khác nhau, một tỷ lệ PATCH/DELETE/CREATE thực tế.
3. **Variants:** locale, pagination, tenant (chỉ trong fixture an toàn).
4. **Faults:** Redis chậm, DB chậm, CDN purge failure, cache restart.
5. **Correctness assertions:** sau cập nhật phải thấy phiên bản đúng trong freshness bound, không lộ sai tenant.
6. **Metrics phân tầng:** p50/p95/p99, QPS, error rate, hit/miss, backend load và invalidation lag.

Đặt ngưỡng từ yêu cầu sản phẩm, không tự cho rằng **90% hit** hoặc p95 **50 ms** luôn là mục tiêu hợp lý. Đừng chạy load test gây quá tải production ngoài cửa sổ/ủy quyền được phép.

## 10. Kiểm thử Spring/HTTP: từ ETag đến invalidation thật

### 10.1. MockMvc xác minh conditional GET và HTTP headers

Controller ở mục 6 có thể được thử bằng **MockMvc**. Dưới đây là **JUnit fragment** với fixture CatalogReadService đã được mock, không test Redis:

~~~java
@Test
void unchangedRepresentationReturns304WithoutBody() throws Exception {
    given(catalog.find("BOOK-01"))
        .willReturn(new CatalogView(
            "BOOK-01", "Java API Design", 350000, 18));

    mvc.perform(get("/api/products/BOOK-01")
            .header("If-None-Match",
                "\"catalog-BOOK-01-revision-18\""))
        .andExpect(status().isNotModified())
        .andExpect(header().string(
            "ETag", "\"catalog-BOOK-01-revision-18\""))
        .andExpect(content().string(""));
}

@Test
void changedRepresentationReturns200AndNewVersion() throws Exception {
    given(catalog.find("BOOK-01"))
        .willReturn(new CatalogView(
            "BOOK-01", "Java API Design", 320000, 19));

    mvc.perform(get("/api/products/BOOK-01")
            .header("If-None-Match",
                "\"catalog-BOOK-01-revision-18\""))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "ETag", "\"catalog-BOOK-01-revision-19\""))
        .andExpect(header().string(
            "Cache-Control",
            org.hamcrest.Matchers.containsString("max-age=60")))
        .andExpect(jsonPath("$.priceMinor").value(320000));
}
~~~

**Test fixture:** thêm @WebMvcTest(CatalogController.class), MockMvc, @MockitoBean CatalogReadService, JUnit/Mockito/Spring Test imports và cấu hình filter/security phù hợp. Với Spring Boot/Spring Framework cũ, annotation override mock có thể khác theo version. Nếu chạy slice không nạp authentication/authorization filters, test này **chỉ chứng minh HTTP handling với dữ liệu mock**, không chứng minh quyền truy cập hay Redis invalidation.

Đừng viết test chỉ assert 304 khi client đưa ETag v18 nhưng backend mock vẫn trả v18 rồi kết luận mọi cache đã cập nhật: đó chính là kiểu test **không thể phát hiện stale internal cache**.

### 10.2. Integration test cache-aside và transaction

Một kiểm thử có giá trị cần **Spring context thật + Redis + database**, ví dụ Redis/Testcontainers và DB test instance. Kịch bản:

~~~text
Given: DB product=BOOK-01 revision=18, cache empty
When:  GET qua CatalogReadService lần 1
Then:  DB query count tăng 1, Redis chứa revision=18

When:  GET lần 2 qua cùng service
Then:  Không query DB thêm; dữ liệu revision=18

When:  PATCH có quyền, If-Match v18 -> DB COMMIT revision=19
Then:  Event AFTER_COMMIT đã xử lý/invalidation có acknowledgement

When:  GET lại qua nhiều application instances
Then:  Cache key hiện tại không phục vụ v18 sau mốc consistency đã hứa
       Response 200 revision=19; ETag mới
~~~

**Đừng chạy GET lại trước khi transaction commit** rồi coi đó là kết quả read-after-write. Trong test sử dụng @Transactional ở method test, transaction của test có thể **chưa commit**, khiến @TransactionalEventListener(AFTER_COMMIT) chưa chạy; sử dụng **TestTransaction.end()**, setup/cleanup commit có chủ đích hoặc gọi qua server thật để quan sát ranh giới đúng.

Test Redis TTL phải dùng **Redis client/cache thật** để kiểm expiry và serializer. Dùng **fake Clock/virtual time** ở tầng ứng dụng khi có hỗ trợ; nếu phải chờ TTL thực, dùng bounded polling và deadline thay vì Thread.sleep không giới hạn. Đối với multi-pod, một in-memory CacheManager không chứng minh eviction xuyên instances.

### 10.3. Race condition: GET miss song song PATCH

Thiết lập đồng thời bằng CountDownLatch/barrier hoặc controllable repository:

~~~text
T1: GET cache miss, pause trước khi put v18
T2: PATCH commit v19, emit invalidation v19
T3: Release T1; loader cũ cố put v18
T4: GET khác ngay sau mốc consistency
~~~

Nếu contract yêu cầu **read-after-write mạnh**, test phải thấy v19 và implementation cần kiểm version/CAS hoặc bypass cache. Với **eventual consistency** và TTL, test kiểm không có v18 sau giới hạn stale công bố, đồng thời log/metric ghi nhận lag. Chạy bài test nhiều lần trong CI, vì race có thể chỉ xuất hiện dưới lịch thực thi cụ thể.

Test tương tự với **event delivery sai thứ tự**: apply revision 19 rồi đến revision 18; cache/version pointer **không được lùi** xuống 18. Kiểm **duplicate event**, Redis restart, purge 429/503 và outbox retry. Mock event publisher hoàn hảo không chứng minh relay vận hành thật.

### 10.4. Security: cache key phải tôn trọng ACL

Với đơn hàng riêng tư, test tích hợp bằng **hai principals thật sự khác quyền**:

| Ca | Kết quả |
|---|---|
| User A đọc order A lần đầu | 200 đúng body |
| User B biết ID order A | **403/404** theo policy, không nhận body từ cache A |
| Admin vừa thu hồi quyền A | A không nhận 200/304 cho dữ liệu không còn quyền |
| User B đổi query filter/cursor | Không lấy cached list của A |
| Cookie/session request của browser | Cache-Control private/no-store, CSRF/auth theo mô hình |
| JWT hết hạn rồi retry GET | Không dựa vào cached “200 trước đó” để bypass auth |
| GET order có If-None-Match cũ | Authorization được kiểm **trước** quyết định 304 |

**MockMvc với jwt()** của Spring Security Test không tự xác minh chữ ký/issuer/audience của JWT. Cần test JWT decoder/security integration riêng. Để kiểm CDN/browser thực, gửi HTTP request qua chính edge với hai clients có tokens khác nhau; **cURL hoặc Java HttpClient không thực thi SOP/CORS như trình duyệt**, nên nếu frontend cần xem ETag/Location hãy thêm browser test và CORS exposed headers.

### 10.5. CDN và browser: kiểm bằng đường đi thực

Một kiểm thử end-to-end bổ sung có thể:

1. Đọc public product qua domain edge, ghi ETag/Age/cache-status nếu CDN cung cấp.
2. Ghi thay đổi với quyền admin, xác minh DB revision mới.
3. Đọc lại **cùng URI** từ edge/POP A và B, không chỉ gọi origin bằng host nội bộ.
4. Gửi If-None-Match chứa ETag cũ và kiểm 200 v19 **sau freshness bound**.
5. Trên browser đã nhận v18, kiểm khi nào nó tái xác minh; nếu cần read-your-writes, dùng tuyến phù hợp thay vì chờ browser TTL.
6. Giả lập purge lỗi và khôi phục; kiểm alert **invalidation lag** và TTL fallback.

**Không assert rằng mọi GET ngay sau PATCH luôn là v19 nếu contract chỉ cho bounded staleness.** Ngược lại, nếu contract hứa read-your-writes hoặc strong visibility, một response v18 sau mốc commit/consistency là lỗi dù TTL 60 giây chưa hết.

## 11. HTTP contract: mô tả và dùng cache validators từ client Java

### 11.1. OpenAPI mô tả ETag/304, không tự triển khai cache

Fragment **OpenAPI 3.1** cho GET sản phẩm:

~~~yaml
paths:
  /api/products/{sku}:
    get:
      operationId: getProduct
      parameters:
        - name: sku
          in: path
          required: true
          schema: {type: string}
        - name: If-None-Match
          in: header
          required: false
          description: ETag validator of previously stored representation
          schema: {type: string}
      responses:
        '200':
          description: Product representation
          headers:
            ETag:
              schema: {type: string}
            Cache-Control:
              schema: {type: string}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/CatalogView'}
        '304':
          description: Not modified; no response body
          headers:
            ETag:
              schema: {type: string}
            Cache-Control:
              schema: {type: string}
        '404': {description: Product not found}
~~~

Đây là **fragment**, cần bổ sung openapi/info/components, JSON schema CatalogView, authorization cho thao tác ghi và các response khác. Khi PATCH/PUT dùng **If-Match**, mô tả precondition và response **412** trong operation tương ứng. **OpenAPI chỉ mô tả hợp đồng HTTP**, không tự purge CDN, không bảo đảm database revision mới và không kiểm revalidation/tenant ACL. Bộ **contract tests** phải kiểm actual response 200/304/412 và header thật qua gateway.

### 11.2. Một Java HTTP client kiểm validator theo contract

Một backend Java dùng **java.net.http.HttpClient** không tự có shared HTTP response cache như browser/CDN. Nó có thể lưu ETag và body trong **application-owned store**, nhưng phải tự thực thi scope, freshness, version và security:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

// Fragment: storedEtag và storedJson đến từ một cache an toàn
// cho ĐÚNG URI, principal/tenant và selected representation.
HttpRequest.Builder builder = HttpRequest.newBuilder(
        URI.create("https://api.example.test/api/products/BOOK-01"))
    .GET();
if (storedEtag != null && !storedEtag.isBlank()) {
    builder.header("If-None-Match", storedEtag);
}

HttpResponse<String> result = httpClient.send(
    builder.build(), HttpResponse.BodyHandlers.ofString());

if (result.statusCode() == 304) {
    if (storedJson == null) {
        throw new IllegalStateException(
            "304 without matching stored representation");
    }
    // Reuse storedJson only under proper cache/identity policy.
} else if (result.statusCode() == 200) {
    String newEtag = result.headers()
        .firstValue("ETag").orElse(null);
    // Validate JSON schema, content type, policy; update stored body.
} else {
    // 401/403/404/412/429/5xx require distinct handling.
}
~~~

Fragment cần biến **httpClient, storedEtag, storedJson**, error handling, timeout và cache store cụ thể; **không phải chương trình copy-paste chạy độc lập**. Nếu request là dữ liệu cá nhân, phải gửi Authorization phù hợp và **không tái sử dụng cached representation sau khi scope/tenant/ACL thay đổi**. Với 304 không body, client không thể gọi JSON decoder trên response rỗng như 200.

Thực tế Java HTTP client cần timeout, connection pooling, retry budget và giải quyết unknown outcomes: **không retry POST thanh toán vô điều kiện** vì tưởng 304/ETag xử lý chống trùng. ETag là validator đọc; Idempotency-Key là hợp đồng xử lý cùng một ý định ghi.

## 12. Bài tập áp dụng và đáp án

**Bài 1 — Cùng ETag, giá đã thay.** Browser lưu response sản phẩm v18; DB đã cập nhật v19. Client gửi If-None-Match v18 và CDN còn giữ v18 trả 304. Có thể kết luận Spring đã lỗi? **Đáp án:** Chưa. Cần biết CDN còn trong freshness bound hợp lệ không, bản thể nào CDN đang revalidate, Age/TTL/purge; nếu vượt bound hoặc hệ thống hứa strong visibility, đó là lỗi tính hiệu lực. 304 từ một cache cũ không chứng minh DB vẫn v18.

**Bài 2 — Evict trước commit.** Service xóa Redis key rồi mới commit DB. Trong khoảng giữa, một GET miss đọc v18 và fill cache. Sau commit người dùng thấy v18. **Đáp án:** Race invalidation-before-commit. Dời evict sau commit, thêm kiểm version/cơ chế chống stale refill và test concurrent. AFTER_COMMIT một mình chưa giải quyết mọi race.

**Bài 3 — Multiple pods.** Mỗi pod dùng local cache với TTL 20 phút; admin chỉ evict local key ở pod A. Các pods khác trả giá cũ. **Đáp án:** Local cache không chia sẻ invalidation. Dùng Redis chung, broadcast event có xác nhận/TTL, versioned keys hoặc bỏ local cache; xác minh qua mọi pods.

**Bài 4 — Browser và CDN khác TTL.** Browser max-age=60, CDN s-maxage=300. Sau khi CDN được purge lúc t=10 giây, browser của user vẫn hiển thị v18 đến t=60. **Đáp án:** Purge CDN không xóa bản thể đang còn fresh ở browser. Nếu cần hiển thị ngay, giảm TTL, version URL, revalidation có chủ đích hoặc tuyến read-your-writes; không tuyên bố “purge toàn hệ thống” chỉ từ CDN.

**Bài 5 — Truy cập chéo tenant.** Spring @Cacheable dùng key = orderId; người A đọc order X, người B có scope orders.read nhưng không thuộc tenant A gọi cùng ID và nhận cache hit. **Đáp án:** Lỗ hổng authorization/BOLA. Không đặt data riêng tư trong shared cache key chỉ theo ID; kiểm quyền trước mỗi lần phục vụ, tách namespace theo verified tenant/subject/policy hoặc dùng no-store và bypass shared cache.

**Bài 6 — DELETE và 404 cache.** GET BOOK-99 từng trả 404, CDN giữ 5 phút. POST tạo BOOK-99 thành công nhưng GET vẫn 404. **Đáp án:** Negative cache cần TTL thấp và invalidation cả trên create/restore. Không chỉ evict khi PATCH/DELETE; cần test tồn tại sau create với URI/key cũ.

**Bài 7 — Versioned key nhưng pointer stale.** Cache key catalog:sku:revision:19 tồn tại, song catalog-current:sku vẫn là 18. GET vẫn đọc v18. **Đáp án:** Versioned key chỉ giải quyết khi chọn **revision mới từ nguồn đúng**; cần nâng pointer atomically/monotonically, invalidate pointer hoặc đọc source version đáng tin.

**Bài 8 — ETag của ngôn ngữ và giá.** Response English và Vietnamese khác JSON nhưng server dùng chung strong ETag theo SKU, không Vary. **Đáp án:** Sai selected representation; cần Vary: Accept-Language, key phân biệt ngôn ngữ và strong ETag tương ứng bytes/representation (hoặc validator khác theo semantics).

**Bài 9 — Benchmark.** Load test 10.000 GET cùng SKU có 99,9% hit và p95 10 ms; báo cáo “caching đã tối ưu toàn bộ REST API”. **Đáp án:** Chưa đủ. Cần traffic mix, cold misses, writes, ACL variants, Redis outages, cache invalidation lag, p99 và DB throughput. Hit ratio cao có thể che dữ liệu cũ hoặc hot-key bất thường.

**Bài 10 — Giá cuối thanh toán.** UI lấy priceMinor từ public cached product response và POST giá đó vào checkout; server tin giá client gửi. **Đáp án:** Lỗi bảo mật/nghiệp vụ. Giá chốt phải do server tính hoặc xác minh trên nguồn/chính sách authoritative, độc lập với freshness của catalog hiển thị.

## 13. Checklist thiết kế, triển khai và nghiệm thu

- [ ] Từng resource có **source of truth**, cache layers, TTL, chủ sở hữu và mức stale tối đa rõ?
- [ ] Phân biệt **request cache của browser/CDN** với **object cache Redis/local** và cache DB/read replica?
- [ ] HTTP Cache-Control public/private/no-cache/no-store/s-maxage được chọn theo đúng dữ liệu?
- [ ] ETag/Last-Modified đại diện selected representation, 304 không body và quyền được kiểm trước validator?
- [ ] Tài nguyên nhạy cảm có tenant/subject/ACL trong thiết kế hoặc **không shared-cache**?
- [ ] Cache keys phân biệt filter, sort, cursor, locale, API version và representation đúng ngữ nghĩa?
- [ ] PUT/PATCH/DELETE dùng auth + If-Match/version khi cần; 412 không làm thay đổi DB?
- [ ] Evict sau commit; có chiến lược xử lý stale refill, event trễ/trùng/sai thứ tự?
- [ ] CDN/collection/search/negative cache được purge hoặc có version/generation và TTL fallback?
- [ ] Mức **read-your-writes/strong/bounded staleness** được viết thành assertion có thời hạn?
- [ ] Read replica, browser TTL, CDN Age và Redis TTL đã được tính trong end-to-end staleness?
- [ ] Có chống cache stampede, TTL jitter, lock scope rõ, giới hạn miss concurrency và outage policy?
- [ ] Metrics theo tầng đo hit/miss, p95/p99, DB QPS, invalidation lag và **stale responses**?
- [ ] Đã chạy MockMvc conditional GET, Redis/DB integration test, concurrency races và HTTP qua CDN?
- [ ] POST idempotency được kiểm bằng ledger/transaction riêng, không dùng GET caching thay thế?
- [ ] Kiểm thử bảo mật chứng minh không trả dữ liệu user khác, không 304 sau khi thu hồi quyền?

**Kết luận:** Caching nhiều tầng giúp giảm độ trễ và chi phí khi **mỗi bản sao có chính sách freshness, cache key và invalidation đúng**. Cách kiểm chứng có giá trị nhất không phải nhìn vào một con số hit ratio, mà là **ghi thay đổi có version, đọc lại qua các tầng với ETag cũ/mới, đo thời gian stale và kiểm quyền**. Chỉ khi giữ được bất biến dữ liệu sau thay đổi, việc tăng cache hit mới thực sự là cải thiện hiệu năng cho REST API.
