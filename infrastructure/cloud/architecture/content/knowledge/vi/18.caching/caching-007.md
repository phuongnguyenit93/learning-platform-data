# Đồng bộ nhiều tầng đệm: trình duyệt, CDN, ứng dụng và dữ liệu

## 1. Vì sao nhiều tầng cache phải được thiết kế cùng nhau?

Một hệ thống cloud thường có nhiều tầng cache: trình duyệt giữ response hoặc tài nguyên tĩnh; CDN lưu nội dung gần người dùng; reverse proxy/API gateway có thể cache response; ứng dụng lưu kết quả trong memory hoặc distributed cache; database giữ buffer/cache trang và các materialized view. Mỗi tầng giảm một loại chi phí khác nhau, nhưng cũng tạo thêm một bản sao dữ liệu có thể cũ.

Nếu chỉ cấu hình TTL riêng lẻ, hệ thống dễ gặp những tình huống khó giải thích: CDN đã purge nhưng trình duyệt vẫn giữ response cũ; application cache đã cập nhật nhưng CDN tiếp tục trả phiên bản trước; database commit thành công nhưng cache chưa bị invalidation; một tenant nhìn thấy dữ liệu của tenant khác do cache key thiếu phạm vi truy cập.

**Đồng bộ nhiều tầng cache** là việc thiết kế cách dữ liệu được tạo, lưu, xác thực, làm mới và vô hiệu hóa xuyên suốt các tầng. Mục tiêu không nhất thiết là mọi tầng đổi dữ liệu cùng một mili giây. Mục tiêu là xác định **độ mới được phép, hành vi khi dữ liệu cũ, thứ tự cập nhật, ranh giới bảo mật và cách khôi phục** cho từng loại dữ liệu.

Trong module **CLOUD_ARCHITECTURE**, đây là quyết định kết nối mạng, compute, lưu trữ và mô hình triển khai; cần cân bằng **hiệu năng, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ có trang tìm phòng, ảnh property, nội dung mô tả, giá, tồn phòng, hồ sơ tài khoản và lịch sử booking. Ảnh ít đổi, mô tả đổi theo ngày, giá và tồn phòng có thể đổi liên tục, còn lịch sử booking là dữ liệu riêng tư cần được xác thực quyền trước khi trả.

## 2. Bức tranh phân tầng cache

~~~mermaid
flowchart TB
    B["Browser / Mobile client cache"]
    E["CDN / Edge cache"]
    P["Reverse proxy / API gateway cache"]
    A["Application cache"]
    D["Database buffer / query cache / materialized data"]
    S[("Authoritative source of truth")]
    B -->|"MISS / revalidate"| E
    E -->|"MISS / revalidate"| P
    P -->|"MISS"| A
    A -->|"MISS"| D
    D -->|"read"| S
    S -. "write event / invalidation" .-> A
    S -. "purge / version update" .-> E
    S -. "new representation / validator" .-> B
~~~

Sơ đồ là mô hình logic. Một request có thể bỏ qua một số tầng, ví dụ API không cache ở CDN hoặc ứng dụng đọc trực tiếp database; cache tại browser và CDN thường áp dụng cho HTTP response, còn application cache có thể lưu object hoặc kết quả truy vấn. Quan trọng là mọi tầng phải có **hợp đồng cache** cho dữ liệu mà nó giữ.

| Tầng | Đối tượng thường cache | Lợi ích chính | Rủi ro chính |
| --- | --- | --- | --- |
| Browser | HTML, CSS, JS, ảnh, API response được phép | Giảm round trip và tải về; trải nghiệm nhanh | Client giữ dữ liệu cũ hoặc nhạy cảm quá lâu |
| CDN/Edge | Tài nguyên tĩnh, response công khai, nội dung theo cache key | Giảm latency và tải origin trên diện rộng | Sai cache key, purge chậm, cache nhầm nội dung cá nhân |
| Reverse proxy/API gateway | Response API hoặc fragment được phép | Giảm tải backend, tập trung policy | Header/authorization/cookie không được xử lý đúng |
| Application cache | Object, profile công khai, kết quả tính toán, session tùy mô hình | Tránh truy vấn hoặc tính toán lặp lại | Invalidation, stampede, phân tán state |
| Data/database cache | Buffer page, query result, materialized view, read replica gần | Tăng throughput đọc hoặc giảm I/O | Hiểu nhầm cache DB là nguồn dữ liệu bền vững; freshness/replication lag |

**Database buffer cache** thường do database engine tự quản lý và giữ các page dữ liệu/index trong bộ nhớ. Ứng dụng không nên tùy tiện coi đây là cache có thể purge theo API. Materialized view hoặc read model là dữ liệu dẫn xuất cần refresh theo cơ chế riêng.

## 3. Bắt đầu từ hợp đồng freshness theo loại dữ liệu

Không phải dữ liệu nào cũng cần cùng mức nhất quán. Một TTL 10 phút có thể tốt cho ảnh property nhưng không phù hợp với tồn phòng trước khi xác nhận booking.

| Loại dữ liệu | Tính chất thay đổi | Chính sách tham khảo | Nguồn xác minh cuối |
| --- | --- | --- | --- |
| CSS/JS có tên chứa content hash | Chỉ đổi khi build | Cache dài hạn, immutable | Build artifact/version |
| Ảnh property công khai | Ít đổi, cần phân phối nhanh | TTL dài, purge/version khi cập nhật | Media metadata/origin |
| Mô tả và tiện nghi | Đổi theo quản trị nội dung | TTL ngắn hơn, event purge khi sửa | Property Service |
| Kết quả tìm kiếm | Tùy dữ liệu và bộ lọc | TTL ngắn hoặc cache có khóa theo query | Search projection; kiểm tra booking ở nguồn authoritative |
| Giá | Có thể đổi thường xuyên | Cache rất ngắn hoặc chỉ dùng cho hiển thị sơ bộ | Pricing Service |
| Tồn phòng | Thay đổi theo giao dịch | Không dùng cache để xác nhận giữ/đặt phòng | Inventory/Booking Service |
| Hồ sơ cá nhân | Dữ liệu theo người dùng | Private cache với chính sách phù hợp hoặc no-store | Identity/Profile Service |
| Trạng thái thanh toán/booking | Nhạy cảm và có ý nghĩa giao dịch | Thường tránh shared cache; xác minh quyền và trạng thái | Payment/Booking database |

### 3.1. Định nghĩa freshness bằng thời gian và điều kiện

Một hợp đồng freshness nên nêu freshness target, maximum stale age, consistency requirement, invalidation trigger, fallback và scope. Ví dụ, p95 của thời gian từ source commit tới lúc nội dung mới được phục vụ phải dưới 30 giây; dữ liệu stale tối đa được chấp nhận là 2 phút; khi invalidation lỗi thì chỉ nội dung mô tả công khai được phục vụ stale.

TTL chỉ là giới hạn thời gian lưu hoặc một tín hiệu làm mới theo cấu hình. TTL không bảo đảm mọi tầng cùng hết hạn một lúc, và cũng không phải cam kết mọi thay đổi được phản ánh trong đúng TTL nếu có stale-while-revalidate, replication delay hoặc lỗi invalidation.

## 4. Cache key: điều kiện tiên quyết để cache đúng và an toàn

Cache key xác định hai request có được xem là cùng một nội dung có thể dùng chung hay không. **Thiếu một chiều ảnh hưởng response có thể gây cache collision về ngữ nghĩa hoặc rò dữ liệu.** Thêm quá nhiều chiều thì cache bị phân mảnh, hit ratio thấp.

| Chiều | Khi nào cần đưa vào key |
| --- | --- |
| HTTP method | Chỉ cache những method và semantics được hỗ trợ; GET/HEAD khác với POST |
| Host/route/path | Response khác theo hostname hoặc endpoint |
| Query parameters | Filter, sort, page, locale hoặc phiên bản API làm thay đổi nội dung |
| Content negotiation | Accept, Accept-Encoding hoặc format output |
| Locale/language | Nội dung dịch theo ngôn ngữ |
| Tenant | Response thực sự khác theo tenant và cache dùng chung giữa tenant |
| Identity/role | Chỉ khi có chiến lược private cache an toàn; thường tránh shared cache cho nội dung cá nhân |
| Cookie/header | Chỉ những cookie/header thực sự làm thay đổi response; tránh Vary quá rộng |
| Version | Schema, API version hoặc content version làm thay đổi biểu diễn |

Ví dụ cache key logic cho trang tìm kiếm công khai:

~~~text
search:v3:locale=vi:city=city-hcm:checkin=2026-12-18:
checkout=2026-12-21:guests=2:sort=price:page=1
~~~

Không đưa raw access token, session cookie, email hoặc dữ liệu cá nhân vào key. Nếu cần phân tách theo user/tenant, dùng identifier đã xác thực và opaque; đồng thời giới hạn TTL và quyền truy cập cache.

### 4.1. Query normalization

Hai request có thể tương đương về nghiệp vụ nhưng tạo key khác nhau nếu query parameter không được chuẩn hóa, ví dụ thứ tự tham số, chữ hoa/thường, default value hoặc khoảng trắng. Cần quy định tham số mặc định, thứ tự và cách encode query, giá trị đa lựa chọn, locale/currency/timezone và tham số tracking có thể bỏ qua. Không loại bỏ tham số chỉ vì nghĩ chúng không quan trọng; phải chứng minh response không thay đổi theo tham số đó.

## 5. Đồng bộ Browser cache và HTTP semantics

Browser cache thường tuân theo HTTP caching semantics. Server cung cấp response header; browser/proxy đánh giá có thể dùng bản lưu, cần revalidate hay phải lấy mới.

### 5.1. Cache-Control

| Directive | Ý nghĩa khái quát | Dùng khi |
| --- | --- | --- |
| max-age=3600 | Fresh trong 3600 giây theo cache policy | Nội dung được phép lưu trong thời gian xác định |
| public | Response có thể được shared cache lưu nếu các điều kiện khác cho phép | Nội dung công khai |
| private | Response chỉ dành cho private cache, không dành cho shared cache theo semantics HTTP | Nội dung cá nhân nhưng browser có thể lưu |
| no-cache | Có thể lưu nhưng phải revalidate trước khi dùng lại | Muốn kiểm tra phiên bản trước khi tái sử dụng |
| no-store | Không lưu response trong cache theo HTTP semantics | Nội dung nhạy cảm hoặc không muốn cache |
| must-revalidate | Khi đã stale, phải revalidate trước khi dùng lại theo điều kiện directive | Không cho dùng stale ngoài điều kiện cho phép |
| stale-while-revalidate | Có thể phục vụ stale trong khoảng quy định trong khi revalidate nền | Nội dung công khai chịu được độ cũ ngắn |
| stale-if-error | Có thể dùng stale khi origin lỗi trong khoảng quy định | Giữ trải nghiệm cho dữ liệu không nhạy cảm, có ngưỡng cũ rõ |

Ví dụ:

~~~http
Cache-Control: public, max-age=300, s-maxage=900, stale-while-revalidate=30
ETag: "property-91-v1842"
Vary: Accept-Encoding
~~~

Ở ví dụ này, max-age hướng tới cache private như browser, s-maxage áp dụng cho shared cache theo HTTP caching semantics và có thể ghi đè thời gian freshness tương ứng. CDN thực tế còn có cấu hình cache policy riêng; cần hiểu cách sản phẩm ưu tiên origin header, TTL tối thiểu/tối đa, query string và cookie.

**Không đặt public chỉ để tăng hit ratio.** Response có dữ liệu theo user, tenant, cookie hoặc quyền truy cập có thể bị shared cache lưu sai phạm vi nếu policy/key không được thiết kế chính xác.

### 5.2. ETag và Last-Modified

ETag là validator đại diện cho một phiên bản representation. Browser gửi If-None-Match; nếu representation chưa đổi, server có thể trả 304 Not Modified mà không gửi lại body. Last-Modified cùng If-Modified-Since là cơ chế validator theo thời gian, thường có độ chính xác phụ thuộc implementation.

Validator giúp **revalidate** thay vì tải lại toàn bộ representation. Tuy nhiên, phải đảm bảo ETag phản ánh đúng nội dung và variant; ETag của gzip và uncompressed có semantics tùy implementation. Không dùng ETag làm bằng chứng phân quyền hoặc chống sửa dữ liệu nghiệp vụ.

### 5.3. Tài nguyên tĩnh và cache busting

Với CSS/JS/image được build có content hash trong tên file, có thể cache rất lâu và đánh dấu immutable:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Ví dụ app.a83f91c2.js và app.19bc72d0.css. Khi nội dung thay đổi, build tạo tên file khác; HTML hoặc manifest mới tham chiếu phiên bản mới. Không ghi đè nội dung dưới cùng một URL đã được công bố immutable vì browser/CDN có thể tiếp tục dùng bản cũ trong thời hạn dài.

## 6. CDN và reverse proxy: cache gần người dùng

CDN thường cache theo hostname/path/query/header/cookie tùy cấu hình. Nó giảm round trip tới origin, phân phối tài nguyên tĩnh và một số response API công khai.

### 6.1. CDN cache policy

Khi cấu hình CDN cần xác định cacheable methods, cache key, origin request policy, TTL, compression/content encoding, purge/invalidation, stale behavior và origin protection. Thông thường chỉ cache GET/HEAD; không cache POST/PUT/DELETE nếu chưa có semantics rõ.

### 6.2. Cache hit ratio không phải mục tiêu duy nhất

CDN có hit ratio cao nhưng cache nhầm locale, tenant hoặc phiên bản vẫn là lỗi nghiêm trọng. Một số tuyến có tỷ lệ hit thấp nhưng vẫn cần phục vụ từ origin để bảo vệ tính đúng đắn. Đánh giá đồng thời hit ratio, origin offload, latency, error rate, cache key cardinality và false sharing.

### 6.3. Purge/invalidation từ origin tới CDN

Khi property đổi ảnh hoặc nội dung, có thể:

1. Ghi nội dung mới vào object storage với key/version mới.
2. Cập nhật metadata trong nguồn có thẩm quyền.
3. Phát event PropertyMediaUpdated.
4. Invalidation worker xác định URL/prefix/surrogate key liên quan.
5. Gửi purge tới CDN và theo dõi trạng thái.
6. UI tham chiếu URL/version mới; URL cũ hết hạn hoặc bị purge theo policy.

Purge có thể không tức thì trên mọi edge node. Không nên thiết kế một transaction nghiệp vụ phụ thuộc việc mọi CDN edge xác nhận purge đồng thời. Với nội dung cần thay ngay vì an toàn/chính sách, cần thêm cơ chế serving denylist hoặc URL mới và kiểm soát truy cập ở origin.

## 7. Application cache: local memory và distributed cache

Application cache thường lưu kết quả tính toán, object domain, session hoặc read model.

| Loại | Đặc điểm | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| In-process memory | Nằm trong bộ nhớ từng instance | Dữ liệu nhỏ, truy cập nhanh, chấp nhận cache riêng mỗi instance | Instance khác nhau có bản cache khác nhau; restart mất cache |
| Distributed cache | Nhiều instance cùng truy cập Redis/Memcached hoặc dịch vụ tương ứng | Chia sẻ cache, giảm truy vấn database | Thêm network hop, dependency, chi phí và failure mode |

### 7.1. Cache-aside

Một mẫu phổ biến:

1. Ứng dụng đọc cache theo key.
2. Nếu hit, trả dữ liệu theo freshness policy.
3. Nếu miss, đọc nguồn dữ liệu có thẩm quyền.
4. Ghi cache với TTL phù hợp.
5. Khi cập nhật dữ liệu, commit source rồi invalidate/update cache theo cơ chế nhất quán đã chọn.

~~~text
value = cache.get(key)
if value is fresh:
    return value
value = database.read(key)
cache.set(key, value, ttl)
return value
~~~

Đây là pseudocode. Cần xử lý cache miss đồng thời, cache lỗi, dữ liệu không tồn tại, serializer/version và lỗi sau commit.

### 7.2. Read-through và write-through/write-behind

- **Read-through:** cache layer tự tải từ nguồn khi miss; ứng dụng gọi cache như điểm đọc.
- **Write-through:** ghi qua cache layer và cập nhật nguồn theo cơ chế được hỗ trợ, thường cần cân nhắc transaction.
- **Write-behind/write-back:** ghi cache trước rồi ghi nguồn sau; throughput có thể tốt nhưng rủi ro mất dữ liệu và yêu cầu durable queue/flush/error recovery cao hơn.

Không chọn write-behind cho giao dịch có thẩm quyền nếu chưa có mô hình bảo đảm durability, replay và đối soát. Cache thông thường không phải database bền vững.

## 8. Đồng bộ invalidation giữa các tầng

Thách thức lớn là một thay đổi nguồn cần tác động tới nhiều tầng cache. Không có một primitive purge chung có thể atomic xuyên browser, CDN, app cache và database.

### 8.1. Event-driven invalidation

~~~mermaid
sequenceDiagram
    participant U as Admin/API
    participant DB as Source DB
    participant O as Outbox
    participant W as Invalidation Worker
    participant C as App Cache
    participant CDN as CDN
    U->>DB: Update property
    DB->>O: Commit event in same transaction
    O-->>W: PropertyUpdated v1843
    W->>C: Delete/update application keys
    W->>CDN: Purge related URL/tag
    W-->>W: Record result and retry failures
~~~

Với browser, server không thể tùy tiện xóa cache của mọi client đang offline. Có thể dùng URL versioned cho tài nguyên tĩnh, TTL ngắn/revalidate cho response động, hoặc thay đổi version trong trang/manifest để client tham chiếu tài nguyên mới.

### 8.2. Invalidation phải idempotent

Event có thể giao lặp; purge cùng URL nhiều lần thường có thể chấp nhận, nhưng worker vẫn cần thiết kế idempotent, giới hạn retry và ghi nhận kết quả. Nếu một event đến sai thứ tự, event cũ không nên làm cache quay về nội dung trước. Dùng version/generation của entity hoặc kiểm tra version trước khi update cache.

### 8.3. Invalidate sau commit

Nếu xóa cache trước rồi transaction database rollback, request tiếp theo có thể đọc dữ liệu cũ từ database và ghi lại vào cache. Một quy trình thường an toàn hơn là commit thay đổi vào source of truth, ghi outbox/change event cùng transaction hoặc cơ chế log bảo đảm không mất, invalidation worker nhận event, xóa/cập nhật cache theo generation/version và ghi trạng thái xử lý, retry, cảnh báo khi backlog vượt freshness SLO.

Vẫn có một khoảng thời gian cache cũ tồn tại giữa commit và invalidation. Nếu nghiệp vụ không chấp nhận cửa sổ này, cần kiểm tra nguồn authoritative khi đọc hoặc thiết kế đồng bộ mạnh cho đúng luồng đó.

## 9. Versioning để đồng bộ cache dễ dự đoán

Purge theo URL hoặc key có thể khó khi có nhiều tầng và nhiều bản sao. Một kỹ thuật là đưa **version/generation** vào cache key hoặc URL:

~~~text
property:property-91:v1843
property-media/property-91/image-v1843.webp
search-result:v3:locale=vi:...
~~~

Khi source cập nhật version từ 1842 lên 1843, ứng dụng đọc key mới. Cache cũ có thể còn tồn tại nhưng không được dùng bởi request mới; TTL sẽ dọn dần. Với object/media, URL mới tránh phải chờ purge mọi edge trước khi người dùng thấy bản mới.

Versioning hữu ích cho static assets có content hash, projection/document có sourceVersion, application cache của aggregate, HTML/manifest trỏ tới asset phiên bản mới và API response có schema/content generation.

Nhược điểm là cache cũ có thể tiêu thụ dung lượng cho đến khi TTL/eviction xảy ra; phải có retention và quota. Không đưa một generation toàn cục vào mọi key nếu một thay đổi nhỏ làm vô hiệu hóa toàn bộ cache và giảm hit ratio.

## 10. Cache stampede, thundering herd và cách phòng tránh

**Cache stampede** xảy ra khi một key nóng hết hạn, nhiều request đồng thời cùng cache miss và dồn xuống database hoặc service nguồn.

Các biện pháp:

- **Single-flight/request coalescing:** chỉ một request tải dữ liệu; các request khác chờ kết quả chung.
- **TTL jitter:** thêm độ lệch ngẫu nhiên vào TTL để nhiều key không hết hạn cùng lúc.
- **Refresh ahead:** làm mới trước khi hết hạn dựa trên mức độ phổ biến và khả năng dự đoán.
- **Stale-while-revalidate:** trả dữ liệu stale trong giới hạn cho phép trong khi một worker cập nhật.
- **Negative caching:** cache kết quả không tồn tại trong thời gian ngắn để giảm truy vấn lặp, nhưng phải xử lý khi object vừa được tạo.
- **Rate limit/bulkhead:** giới hạn tải miss xuống origin.

Ví dụ TTL jitter:

~~~text
effectiveTTL = baseTTL + random(0, jitterWindow)
~~~

Không áp stale-while-revalidate cho dữ liệu có thể gây quyết định sai như tồn phòng, trạng thái thanh toán hoặc quyền truy cập. Negative cache cũng không nên có TTL dài nếu dữ liệu mới có thể xuất hiện ngay sau đó.

## 11. Khi nào phục vụ stale và khi nào phải xác minh lại?

Không phải stale data luôn xấu. Khi origin tạm thời lỗi, trả mô tả property cũ có thể tốt hơn trang trắng; nhưng dùng tồn phòng cũ để xác nhận booking có thể gây overbooking.

| Dữ liệu/hành động | Có thể phục vụ stale? | Điều kiện |
| --- | --- | --- |
| Ảnh/mô tả công khai | Thường có thể | Trong stale age đã định, không vi phạm yêu cầu gỡ nội dung |
| Danh mục/tiện nghi | Có thể | Hiển thị thời gian cập nhật hoặc chấp nhận sai lệch nhỏ |
| Kết quả tìm kiếm | Có thể có giới hạn | Nguồn giao dịch phải xác minh trước khi đặt |
| Giá ước tính | Có điều kiện | Ghi rõ chỉ tham khảo và xác nhận lại trước checkout |
| Tồn phòng | Không dùng stale để commit | Luôn kiểm tra inventory/booking source |
| Phân quyền/role | Không dùng stale quá lâu nếu ảnh hưởng quyền | Refresh/revoke nhanh, kiểm tra quyền theo yêu cầu bảo mật |
| Thanh toán/booking status | Không dùng stale để thực hiện side effect | Đọc nguồn có thẩm quyền hoặc trạng thái đã xác minh |

Khi cấp quyền bị thu hồi, cache permission cũ có thể tạo lỗ hổng. Cần freshness/revocation SLO riêng cho authorization cache, không dùng TTL dài như dữ liệu ảnh.

## 12. Cache key, tenant isolation và dữ liệu riêng tư

Cache dùng chung giữa nhiều tenant có nguy cơ rò dữ liệu nếu key không bao gồm tenant hoặc policy không tách response riêng tư.

Các quy tắc an toàn:

- Xác thực identity và tenant ở server trước khi xây cache key.
- Không tin header tenant do client tự gửi nếu chưa xác minh membership.
- Shared cache chỉ lưu nội dung công khai hoặc response đã được thiết kế an toàn để chia sẻ.
- Với response cá nhân, dùng private cache hoặc key phân tách theo identity; cân nhắc Cache-Control private hoặc no-store.
- Không cache response có token/cookie hoặc thông tin quyền nếu cache policy chưa được kiểm thử.
- Khi role/quyền thay đổi, invalidation cần theo identity/tenant và không để response cũ tiếp tục dùng ngoài freshness SLO.
- Không log key chứa token, email hoặc dữ liệu cá nhân.

### 12.1. HTTP Vary và cache partition

Header Vary thông báo response thay đổi theo request header nào. Ví dụ Vary: Accept-Encoding cho phép cache phân biệt nội dung nén và không nén. Nếu response thực sự thay đổi theo ngôn ngữ, Vary: Accept-Language có thể cần thiết.

Không thêm Vary: Cookie toàn cục mà không đánh giá; nó có thể tạo rất nhiều biến thể và làm giảm hit ratio. Nhưng bỏ qua cookie/header làm thay đổi nội dung lại có nguy cơ shared cache trả sai dữ liệu. Phải xem header thực tế, cache key của CDN và semantics của response.

## 13. Đồng bộ cache khi deploy và thay đổi schema

Cache chứa dữ liệu được serialize theo schema của ứng dụng. Khi deploy version mới, application instance cũ và mới có thể cùng truy cập distributed cache trong rolling deployment.

Các chiến lược:

- **Versioned cache key:** thêm namespace/version vào key, ví dụ profile:v2:<id>.
- **Backward-compatible serialization:** code mới đọc được format cũ trong giai đoạn chuyển tiếp.
- **Dual-read:** thử key mới rồi fallback key cũ có thời hạn.
- **Warm-up:** nạp trước nhóm key quan trọng sau deploy hoặc failover.
- **Gradual migration:** xóa cache cũ sau khi instance cũ đã kết thúc và metric xác nhận.

Không đổi format serialized object mà vẫn giữ nguyên key nếu instance cũ không thể deserialize. Điều này có thể gây lỗi hàng loạt trong rollout.

### 13.1. Cache warm-up và cold start

Khi một cache cluster restart hoặc đổi key namespace, hit ratio có thể giảm đột ngột; database phải xử lý miss đồng loạt. Cần warm-up theo danh sách key hot đã đo, giới hạn tốc độ nạp/concurrency, dùng single-flight và backpressure, theo dõi hit ratio/origin RPS/DB saturation và cho phép cache warm-up dần theo traffic.

## 14. Topology, availability và vận hành cache

| Failure mode | Tác động | Hành vi cần thiết kế |
| --- | --- | --- |
| Browser có cache cũ | UI cũ hoặc dữ liệu stale | Versioned asset, validator, TTL và hard refresh path có kiểm soát |
| CDN edge lỗi/không purge | Tăng tải origin hoặc stale response | Multi-origin/edge policy theo khả năng, TTL và versioned URL |
| Distributed cache mất kết nối | Cache miss hàng loạt hoặc API lỗi | Timeout ngắn, fallback có giới hạn, bulkhead và backpressure |
| Cache cluster failover | Mất một phần key hoặc latency tăng | Persistence/replication theo nhu cầu, warm-up và kiểm tra data loss tolerance |
| Invalidation worker backlog | Cache cũ kéo dài | Queue age alert, retry, dead-letter và reconciliation |
| Database quá tải do cache miss | API transaction chậm | Shed load, rate limit, stale policy chỉ cho dữ liệu được phép |
| Purge nhầm quá rộng | Hit ratio giảm, origin spike | Scoped purge, canary, audit và capacity headroom |

### 14.1. Fallback khi cache lỗi

Không phải lúc nào cũng nên bỏ qua cache và đọc thẳng database. Nếu 100% request cùng chuyển sang origin khi Redis lỗi, database có thể sập theo. Chiến lược fallback nên có timeout ngắn, circuit breaker, giới hạn concurrency/rate xuống origin, stale chỉ cho dữ liệu được phép, degraded mode với truy vấn không an toàn và khôi phục cache dần.

## 15. Quan sát freshness và hiệu quả xuyên các tầng

Đừng chỉ đo hit ratio. Cần quan sát **độ mới và độ đúng**:

| Nhóm metric | Ví dụ |
| --- | --- |
| Browser/HTTP | Cache-Control, 304 rate, asset version, client report về stale content nếu có |
| CDN | Hit/miss, origin offload, age header, purge completion, error theo POP |
| Application cache | Hit/miss, evictions, key cardinality, memory, latency, timeout |
| Invalidation | Outbox lag, queue age, purge success/failure, retry/DLQ |
| Data source | Commit timestamp/version, replication lag, read latency |
| Freshness | Source version so với cached/indexed version, age của response |
| Correctness | Mismatch theo sample, stale booking/price prevented, tenant isolation tests |
| Cost | Cache node/memory, CDN transfer/request, origin egress, purge và vận hành |

### 15.1. Freshness lag xuyên tầng

~~~text
freshnessLag = now - sourceCommitTime
versionLag   = sourceVersion - cachedSourceVersion
~~~

Đây là công thức khái niệm; đồng hồ giữa các hệ thống phải được đồng bộ và version phải có semantics so sánh hợp lệ. Với browser cache, server không trực tiếp biết mọi client đã nhận bản mới; có thể đo bằng asset version telemetry hoặc phản hồi của client nếu phù hợp quyền riêng tư.

### 15.2. Truy vết một thay đổi

Khi user báo giá cũ, cần xác định database/Pricing Service đang có version nào; application cache giữ key/version nào; CDN cache key có bao gồm mọi tham số ảnh hưởng giá không; response header nói TTL/validator ra sao; browser đang dùng URL/ETag nào; event invalidation đã phát, tới worker và hoàn tất purge chưa.

Một dashboard theo request trace/correlation ID, cache age và source version giúp phân biệt lỗi cache key, invalidation chậm hay dữ liệu nguồn chưa cập nhật.

## 16. Quy trình thiết kế đồng bộ nhiều tầng

~~~mermaid
flowchart TD
    A["Phân loại dữ liệu và hành trình"]
    A --> B["Đặt freshness/stale SLO"]
    B --> C["Chọn tầng cache phù hợp"]
    C --> D["Thiết kế key, TTL, validator và security"]
    D --> E["Định nghĩa write/invalidation/version flow"]
    E --> F["Kiểm thử stale, stampede, failure và tenant isolation"]
    F --> G["Triển khai canary và quan sát"]
    G --> H["Điều chỉnh TTL, purge, fallback và cost"]
~~~

Với từng loại dữ liệu, lập cache contract gồm owner và nguồn có thẩm quyền; tầng được phép cache; cache key dimensions và cách normalize; TTL/freshness/max stale age; HTTP header/validator/shared-private behavior; invalidation event/version và thứ tự sau commit; fallback; tenant/privacy constraints; metric/alert/runbook/retention/chi phí.

## 17. Bài thực hành: đồng bộ cache cho nền tảng đặt chỗ

**Bối cảnh giả định:** nền tảng có website và mobile app, CDN toàn cầu, API gateway, 4 instance Booking API và distributed cache. Trang property có ảnh, mô tả, tiện nghi; tìm kiếm có filter theo ngày và giá; tồn phòng và giá có thể thay đổi thường xuyên; tài khoản và booking là dữ liệu cá nhân.

### Nhiệm vụ

1. Vẽ sơ đồ browser → CDN → gateway → application cache → database/search store, đánh dấu request nào đi qua từng tầng.
2. Phân loại ít nhất sáu loại dữ liệu theo freshness SLO và maximum stale age.
3. Thiết kế HTTP Cache-Control/ETag cho asset tĩnh, property page và endpoint riêng tư.
4. Thiết kế cache key cho search query, trong đó có locale, ngày, số khách, filter và tenant nếu cần; chứng minh không cross-tenant.
5. Xây dựng flow cập nhật ảnh/property bằng versioned key và CDN purge; xác định hành vi browser cache cũ.
6. Xây dựng flow cập nhật giá/tồn phòng và chứng minh search cache không thể xác nhận booking.
7. Thiết kế outbox/event invalidation cho application cache và CDN; xử lý event lặp/sai thứ tự.
8. Mô phỏng cache stampede, Redis unavailable, CDN purge backlog và cold start; xác định fallback/backpressure.
9. Xác định metric freshness, hit ratio, origin offload, invalidation lag, stale response và chi phí.
10. Viết ADR nêu lựa chọn cache tier, TTL, consistency, rủi ro và điều kiện cần xem lại.

### Mẫu cache contract

| Dữ liệu | Nguồn chuẩn | Tầng cache | Freshness/stale | Invalidation |
| --- | --- | --- | --- | --- |
| CSS/JS hash | Build artifact | Browser + CDN | Dài hạn, immutable | URL mới khi build |
| Property image | Media service/object storage | Browser + CDN | Dài hạn theo version | Key/URL mới và purge có scope |
| Property description | Property DB | CDN/app tùy public policy | Ngắn; stale có giới hạn | PropertyUpdated event |
| Search results | Search projection | CDN/app tùy key và privacy | Ngắn; chỉ ứng viên | Index update/version |
| Price | Pricing DB/service | Có thể cache ngắn cho hiển thị | Không stale để chốt | PriceUpdated/version |
| Availability | Inventory/Booking DB | Hạn chế cache | Không stale để commit | Recheck authoritative |
| Personal booking | Booking DB | Private/no-store theo rủi ro | Xác minh quyền và trạng thái | Không shared-cache |

### Tiêu chí hoàn thành

- Mỗi loại dữ liệu có freshness contract và nguồn có thẩm quyền.
- Cache key không tạo collision sai nghĩa hoặc rò dữ liệu tenant/user.
- Browser/CDN/application cache có TTL, validator, purge/version và fallback nhất quán với nhau.
- Invalidation event có thể retry, xử lý lặp và quan sát backlog.
- Giá, tồn phòng, permission và booking được kiểm tra ở nguồn có thẩm quyền khi cần.
- Có phương án chống stampede và không làm sập origin khi cache lỗi.
- Đã thử cache stale, deploy schema mới, cold start, purge và tenant isolation.
- Có số đo về latency, hit ratio, freshness, correctness và chi phí.

## 18. Checklist Well-Architected trước khi đưa multi-layer cache vào production

- [ ] Đã phân loại dữ liệu theo access pattern, mức độ nhạy cảm và tốc độ thay đổi.
- [ ] Mỗi loại dữ liệu có authoritative source, freshness target và maximum stale age.
- [ ] Đã xác định tầng nào được phép cache; shared cache chỉ chứa response có semantics chia sẻ an toàn.
- [ ] Cache key bao gồm mọi chiều ảnh hưởng response và không chứa token/PII.
- [ ] Query normalization, Vary, cookie/header và content negotiation đã được kiểm chứng.
- [ ] Cache-Control, ETag/Last-Modified, TTL và stale directives phù hợp từng route.
- [ ] Static assets dùng version/content hash nếu cần cache dài hạn; không ghi đè URL immutable.
- [ ] CDN policy xác định method, query, cookie, header, origin request, TTL và purge rõ ràng.
- [ ] Application cache có strategy đọc/ghi, version, TTL và invalidation.
- [ ] Invalidation diễn ra theo source commit, có event/CDC/outbox, retry và idempotency.
- [ ] Cache stampede, thundering herd, cold start và cache outage đã có biện pháp giảm tải.
- [ ] Stale được phục vụ có điều kiện; không dùng stale cho giao dịch, tồn phòng, giá cuối hoặc quyền.
- [ ] Tenant isolation, authorization revocation, TLS, IAM và log masking được kiểm tra.
- [ ] Có metric cho hit/miss, freshness lag, origin load, purge backlog, stale response và correctness.
- [ ] Có runbook khi CDN, distributed cache, invalidation worker hoặc origin gặp sự cố.
- [ ] Đã đánh giá chi phí cache memory, CDN, request, egress, purge và vận hành.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** browser, CDN, application và data cache là các bản sao ở những vị trí khác nhau, với khả năng điều khiển và thời gian sống khác nhau. Muốn chúng hoạt động như một hệ thống, phải định nghĩa **nguồn có thẩm quyền, cache key, freshness, validator, invalidation/versioning, stale policy và fallback** cho từng loại dữ liệu. Cache tốt làm hệ thống nhanh hơn mà vẫn giữ đúng dữ liệu và ranh giới bảo mật khi tải tăng hoặc một tầng gặp sự cố.
