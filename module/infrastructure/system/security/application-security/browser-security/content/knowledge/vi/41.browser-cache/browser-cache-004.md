# Public response

**Public response** là HTTP response được đánh dấu để các cache dùng chung (shared cache), chẳng hạn reverse proxy hoặc CDN, có thể lưu và tái sử dụng cho nhiều request phù hợp. Chỉ thị Cache-Control: public cho phép shared cache lưu response ngay cả trong một số trường hợp mà response thông thường không được shared cache lưu, ví dụ response cho request có header Authorization.

Đây là một quyết định về ranh giới dữ liệu. Một response thật sự công khai như ảnh logo, CSS, JavaScript đã version hóa hoặc catalog chung có thể được phân phối từ CDN để giảm độ trễ và tải origin. Một response chứa tên, email, đơn hàng, hóa đơn, số dư, quyền hoặc nội dung riêng của người dùng không được chia sẻ giữa các phiên. Nếu gắn public hoặc cấu hình CDN bỏ qua cookie/Authorization cho response cá nhân hóa, cache có thể trả dữ liệu của người dùng A cho người dùng B.

public không tự bảo đảm response sẽ được cache; nó cho phép cache lưu response. Freshness lifetime, cache key, Vary, validator và cấu hình CDN vẫn quyết định response có thể được tái sử dụng trong tình huống cụ thể hay không. Set-Cookie cũng không phải cơ chế thay thế Cache-Control: private hoặc no-store.

Bài học thuộc chương **Browser cache** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser cache, shared cache/CDN, origin, cookie và ứng dụng web; tập trung vào public response, Cache-Control, cache key, dữ liệu cá nhân, validation, cache poisoning/deception và kiểm chứng hành vi cache.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt browser private cache với shared cache như reverse proxy và CDN.
2. Giải thích ý nghĩa của response directive public, private, no-cache và no-store.
3. Chọn freshness policy bằng max-age, s-maxage, Expires và must-revalidate.
4. Giải thích cách cache key và Vary ảnh hưởng tới việc tái sử dụng response.
5. Phân tích rủi ro khi cache response có Cookie, Set-Cookie hoặc request Authorization.
6. Dùng ETag, Last-Modified, If-None-Match và 304 Not Modified để revalidation.
7. Phân biệt public representation với response cá nhân hóa.
8. Nhận diện cache poisoning, cache deception và lỗi cấu hình CDN bỏ qua thành phần của cache key.
9. Thiết kế Cache-Control policy cho static asset, public API, trang cá nhân và response nhạy cảm.
10. Kiểm tra cache bằng DevTools, curl và một Node.js lab mô phỏng shared cache.

## 2. Browser cache và shared cache

HTTP caching cho phép lưu response để dùng lại khi request sau phù hợp. Cache có thể nằm ở nhiều tầng:

~~~text
Browser
  |
  | HTTPS request
  v
CDN / shared edge cache
  |
  v
Reverse proxy / gateway cache
  |
  v
Application origin
  |
  v
Database / service
~~~

### 2.1. Private cache

Browser cache là một private cache gắn với user agent/profile. Nó phục vụ lại response cho cùng browser context khi policy cho phép. Cache-Control: private vẫn cho phép private cache lưu response; directive này chỉ ngăn shared cache lưu response đó.

Private cache không đồng nghĩa dữ liệu được mã hóa hoặc an toàn trước người có quyền truy cập thiết bị. Browser profile có thể tồn tại trên máy dùng chung; malware, extension hoặc người dùng khác cùng profile có thể tiếp cận dữ liệu theo quyền hệ điều hành/browser. Với dữ liệu rất nhạy cảm, cân nhắc no-store và kiểm soát thiết bị.

### 2.2. Shared cache

Shared cache phục vụ nhiều user hoặc nhiều client. Ví dụ:

- CDN edge cache.
- Reverse proxy cache.
- Forward proxy do tổ chức quản lý.
- Gateway hoặc caching layer đặt trước origin.

Shared cache có thể nhận request của user A, lưu response, rồi dùng response đó cho request của user B nếu cache key và freshness policy cho phép. Đây là lợi ích lớn với nội dung công khai và là rủi ro nghiêm trọng với nội dung cá nhân hóa.

### 2.3. Một response có thể đi qua nhiều cache

Response có thể được browser cache, CDN và proxy đánh giá độc lập. Cấu hình tại CDN có thể có cache rule riêng, override header hoặc bỏ qua một số request header. Vì vậy, không chỉ đọc header do origin trả về; cần xác minh hành vi thực tế của từng tầng cache.

Cache-Control là một phần của policy HTTP. Một CDN còn có thể hỗ trợ cấu hình vendor-specific như cache rule, surrogate key, purge API hoặc Surrogate-Control. Các cơ chế riêng này phải được kiểm tra cùng với header HTTP tiêu chuẩn.

## 3. Ý nghĩa của Cache-Control: public

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60, s-maxage=300
Date: Sun, 22 Nov 2026 05:00:00 GMT

{"items":[{"id":"p-101","name":"Keyboard"}]}
~~~

Response directive public cho biết bất kỳ cache nào cũng có thể lưu response. Điều này đặc biệt có ý nghĩa với shared cache trong các tình huống response thông thường bị hạn chế cache, ví dụ response cho request chứa Authorization.

### 3.1. public không có nghĩa là ai cũng được phép truy cập origin

public là chỉ thị cacheability, không phải authorization policy. Nó không cấp quyền đăng nhập, không làm endpoint thành public API và không thay thế kiểm tra quyền ở origin.

Tuy nhiên, khi một shared cache đã lưu response public, cache có thể trả response đó cho request phù hợp mà không gọi origin. Nếu response chứa dữ liệu theo user hoặc cache key không phân biệt representation, dữ liệu có thể bị lộ dù origin đã xác thực request đúng.

### 3.2. public không tự đặt thời gian cache

Cache-Control: public không chỉ định response tươi trong bao lâu. Cần có freshness information như max-age, s-maxage hoặc Expires, hoặc cache có thể áp dụng heuristic freshness nếu response đủ điều kiện.

Ví dụ:

~~~http
Cache-Control: public, max-age=300
~~~

Cho phép cache lưu và xem response fresh trong 300 giây theo quy tắc age/freshness của HTTP caching.

### 3.3. public và request Authorization

Theo HTTP caching semantics, shared cache mặc định không được dùng response cho request có header Authorization để đáp ứng request khác, trừ khi response có directive cho phép rõ ràng, ví dụ public, s-maxage hoặc must-revalidate.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, s-maxage=120
Content-Type: application/json

{"catalogVersion":"2026.11"}
~~~

Chỉ dùng cách này nếu representation thực sự giống nhau với mọi client có thể nhận response. Không thêm public chỉ để tăng cache hit cho endpoint trả dữ liệu phụ thuộc bearer token.

### 3.4. Khi nào nên dùng public?

Các trường hợp phù hợp thường là:

- Logo, icon, font, ảnh và asset tĩnh công khai.
- JavaScript/CSS đã build và có content hash trong tên file.
- Catalog, danh mục hoặc dữ liệu sản phẩm giống nhau với mọi người.
- API trả cấu hình công khai không phụ thuộc user/session.
- Trang công khai đã được xác định rõ không chứa thông tin cá nhân hoặc nội dung theo quyền.

Các trường hợp cần tránh:

- Hồ sơ tài khoản, đơn hàng, hóa đơn, số dư hoặc thông tin thanh toán.
- Dashboard cá nhân hoặc nội dung theo tenant.
- API trả dữ liệu khác nhau theo Cookie, Authorization hoặc role.
- Response có nội dung riêng tư dù một phần body nhìn giống dữ liệu công khai.
- Callback đăng nhập, token response hoặc response có credential.

## 4. Phân biệt public, private, no-cache và no-store

Đây là bốn directive thường bị nhầm lẫn:

| Directive | Shared cache | Private/browser cache | Ý nghĩa |
| --- | --- | --- | --- |
| public | Có thể lưu nếu các điều kiện cache khác cho phép | Có thể lưu | Cho phép shared cache lưu response |
| private | Không được lưu response | Có thể lưu | Response dành cho một user |
| no-cache | Có thể lưu nhưng phải validate trước khi reuse | Có thể lưu nhưng phải validate trước khi reuse | Không được dùng response đã lưu mà không kiểm tra lại |
| no-store | Không được lưu | Không được lưu trong HTTP cache | Không lưu request/response trong cache theo HTTP caching rules |

### 4.1. private

Ví dụ:

~~~http
Cache-Control: private, max-age=60
~~~

Browser private cache có thể giữ response trong 60 giây, nhưng shared cache không được lưu response. Directive này phù hợp với response cá nhân hóa nếu ứng dụng chấp nhận browser cache giữ dữ liệu trong thời gian freshness.

private không ngăn người dùng khác truy cập thiết bị/profile đọc dữ liệu browser cache, cũng không xóa dữ liệu đã cache trước đó.

### 4.2. no-cache

Ví dụ:

~~~http
Cache-Control: private, no-cache
ETag: "profile-v17"
~~~

Cache có thể lưu response, nhưng phải hỏi origin để xác minh trước khi dùng lại. Nếu representation chưa đổi, origin có thể trả 304 Not Modified; nếu đã đổi, origin trả representation mới.

Tên no-cache dễ gây hiểu nhầm: nó không có nghĩa “không được lưu”. Nó có nghĩa response không được reuse mà chưa revalidate.

### 4.3. no-store

Ví dụ:

~~~http
Cache-Control: no-store
~~~

Cache không được lưu bất kỳ phần nào của request/response theo HTTP caching rules. Đây là lựa chọn phù hợp với response chứa dữ liệu nhạy cảm mà ứng dụng không muốn lưu trong HTTP cache.

no-store không phải cơ chế xóa dữ liệu khỏi mọi nơi. Nó không xóa log, analytics, screenshot, JavaScript memory, database của ứng dụng hoặc dữ liệu do Service Worker tự lưu bằng Cache Storage. Nó cũng không bảo vệ response sau khi đã được hiển thị trên màn hình.

### 4.4. Không ghép directive theo cảm tính

Ví dụ:

~~~http
Cache-Control: public, no-store
~~~

Hai directive này truyền tải ý định mâu thuẫn: public cho phép shared cache lưu, còn no-store yêu cầu cache không lưu. Tránh tạo policy khó hiểu. Chọn một policy diễn đạt đúng mục tiêu và xác minh hành vi cache thực tế.

## 5. Freshness: max-age, s-maxage và Expires

Cache cần biết response còn fresh hay đã stale.

### 5.1. max-age

max-age=N đặt freshness lifetime tính bằng giây cho response. Nó áp dụng cho cả private cache và shared cache, trừ khi một directive khác có ưu tiên riêng cho shared cache.

~~~http
Cache-Control: public, max-age=60
~~~

Trong ví dụ, cache có thể xem response fresh trong 60 giây sau khi tính current age theo HTTP caching algorithm.

### 5.2. s-maxage

s-maxage=N chỉ áp dụng cho shared cache và ghi đè max-age/Expires đối với shared cache. Nó cũng khiến shared cache phải revalidate response stale trước khi dùng lại, tương đương áp dụng proxy-revalidate.

~~~http
Cache-Control: public, max-age=60, s-maxage=300
~~~

| Cache | Freshness lifetime |
| --- | --- |
| Browser private cache | 60 giây |
| Shared cache/CDN | 300 giây |

Đây là cách đặt TTL browser ngắn hơn CDN khi representation công khai và có thể chia sẻ an toàn.

### 5.3. Expires

Expires là ngày/giờ tuyệt đối mà sau đó response không còn fresh. max-age có ưu tiên cao hơn Expires khi cả hai xuất hiện.

~~~http
Cache-Control: public
Expires: Sun, 22 Nov 2026 05:05:00 GMT
~~~

Ưu tiên max-age/s-maxage trong thiết kế mới vì dễ cấu hình TTL tương đối. Cần đảm bảo đồng hồ hệ thống và header Date được xử lý đúng.

### 5.4. Age và Date

- Date thể hiện thời điểm response được tạo theo HTTP date.
- Age cho biết ước lượng số giây response đã tồn tại trong cache/proxy.
- Age tăng dần khi response được phục vụ từ cache; giá trị cụ thể còn phụ thuộc thuật toán age calculation.

Ví dụ:

~~~http
Date: Sun, 22 Nov 2026 05:00:00 GMT
Age: 45
Cache-Control: public, max-age=60
~~~

Response đã có current age khoảng 45 giây; không thể hiểu rằng request hiện tại luôn được hưởng thêm 60 giây freshness.

### 5.5. must-revalidate và proxy-revalidate

must-revalidate yêu cầu cache không dùng response stale nếu chưa xác minh được với origin. proxy-revalidate áp dụng yêu cầu tương tự cho shared cache.

~~~http
Cache-Control: public, max-age=60, must-revalidate
~~~

Không dựa vào must-revalidate để bảo vệ response cá nhân hóa; hãy chọn private hoặc no-store trước. Đây là directive về cách xử lý stale response, không phải authorization control.

### 5.6. immutable cho asset đã version hóa

immutable là extension được chuẩn hóa trong RFC 8246. Nó cho biết response sẽ không thay đổi trong suốt freshness lifetime; browser có thể tránh conditional revalidation khi người dùng reload trong khoảng đó.

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Chỉ dùng TTL dài và immutable cho URL có version/content hash, ví dụ:

~~~text
/assets/app.8f31c2a7.js
/assets/styles.4d19b1e0.css
~~~

Khi nội dung thay đổi, build tạo URL mới. Nếu dùng URL cố định cho file thay đổi thường xuyên, browser/CDN có thể tiếp tục dùng bản cũ trong thời gian dài.

## 6. Cache key và Vary

Cache key xác định request nào có thể dùng chung một stored response. Cache key cơ bản thường bao gồm method và target URI theo cache implementation; shared cache còn có thể thêm host, scheme, path, query, header hoặc thành phần cấu hình riêng.

Nếu origin tạo response dựa trên một request header nhưng cache key không phân biệt header đó, response có thể bị dùng cho request có giá trị header khác.

### 6.1. Vary

Response header Vary khai báo các request header ảnh hưởng đến representation:

~~~http
Vary: Accept-Encoding, Accept-Language
~~~

Nếu request A có Accept-Language: vi và request B có Accept-Language: en, cache phải coi chúng là các biến thể khác nhau theo Vary khi quyết định response có match hay không.

### 6.2. Ví dụ Vary: Origin

API có thể tạo CORS response dựa trên Origin request:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Cache-Control: public, max-age=60
~~~

Nếu server phản chiếu một origin được allowlist vào Access-Control-Allow-Origin, cache cần phân biệt representation theo Origin. Nếu thiếu Vary: Origin, response được tạo cho origin A có thể được phục vụ cho request từ origin B, gây lỗi CORS hoặc lộ dữ liệu nếu response body cũng khác nhau.

Vary: Origin chỉ giải quyết cache variation; server vẫn phải xác minh Origin và kiểm soát CORS. Không phản chiếu mọi Origin không kiểm tra.

### 6.3. Vary: Cookie không phải cách chữa mặc định cho response cá nhân hóa

Có thể thấy:

~~~http
Vary: Cookie
~~~

Điều này yêu cầu cache xét giá trị Cookie khi match response. Tuy nhiên, Cookie thường có nhiều giá trị, thay đổi liên tục và có thể tạo cache key cardinality rất lớn. Một CDN còn có thể cấu hình bỏ qua cookie hoặc chỉ chọn một số cookie.

Với response cá nhân hóa, dùng private hoặc no-store trước. Chỉ dùng cache variation theo cookie khi đã thiết kế rõ representation, cache key và behavior của toàn bộ tầng cache.

### 6.4. Vary: Authorization không tự giải quyết mọi rủi ro

Vary: Authorization có thể phân biệt các representation theo giá trị Authorization trong một số cache implementation, nhưng không nên dùng để biến API cá nhân thành shared cache một cách tùy tiện. Authorization header là credential; cache key có thể chứa hoặc dẫn xuất từ giá trị nhạy cảm. Một CDN custom cache key có thể bỏ qua header này.

Với response user-specific, dùng private/no-store; nếu có mục tiêu cache ở tầng backend, thiết kế partition theo identity ở server-side cache có kiểm soát, không dựa vào shared HTTP cache.

### 6.5. Vary: *

Vary: * có nghĩa request luôn được coi là không match một stored response cho reuse theo cơ chế Vary. Nó thường làm response không thể được tái sử dụng từ cache cho request sau.

Đừng dùng Vary: * thay cho Cache-Control: no-store; nếu mục tiêu là không lưu, hãy chỉ định no-store rõ ràng.

## 7. Cookie, Set-Cookie và Authorization

### 7.1. Cookie trong request không tự động cấm cache

Browser có thể gửi Cookie trong request:

~~~http
GET /api/profile HTTP/1.1
Host: app.example.com
Cookie: session=opaque-session
~~~

Origin có thể dùng cookie để trả profile cá nhân. Nếu response được đánh dấu public hoặc CDN được cấu hình bỏ qua Cookie, shared cache có nguy cơ lưu response của một session rồi trả cho session khác.

Không giả định rằng request có Cookie thì CDN tự bỏ qua cache. Hãy kiểm tra cache policy và cache key của CDN/reverse proxy.

### 7.2. Set-Cookie không phải cache-control directive

Response có:

~~~http
Set-Cookie: session=opaque-session; Secure; HttpOnly; SameSite=Lax
~~~

không có nghĩa response tự động không cache được. Theo HTTP caching semantics, cache không được dùng sự hiện diện của Set-Cookie làm tiêu chí duy nhất để quyết định response có cacheable hay không.

Nếu response vừa chứa Set-Cookie vừa có thể bị shared cache lưu, cache có thể lưu/reuse response theo policy. Điều này có thể làm lộ body hoặc gây hành vi cookie không mong muốn tùy cache implementation. Với response liên quan phiên đăng nhập hoặc dữ liệu cá nhân, đặt Cache-Control: private hoặc no-store rõ ràng và kiểm tra CDN.

### 7.3. Authorization request và shared cache

Theo RFC 9111, shared cache không được dùng response cho request chứa Authorization để đáp ứng request khác, trừ khi response có directive cho phép rõ ràng như public, s-maxage hoặc must-revalidate.

Điều này có nghĩa một response:

~~~http
Cache-Control: public, s-maxage=120
~~~

có thể được shared cache lưu dù request ban đầu có Authorization. Chỉ làm vậy khi body và metadata thực sự không phụ thuộc danh tính/quyền của bearer token.

### 7.4. Mẫu policy cho dữ liệu theo user

Response profile:

~~~http
Cache-Control: private, no-cache
ETag: "profile-user-42-v8"
~~~

Browser có thể lưu response riêng và phải revalidate trước khi reuse; shared cache không được lưu.

Response chứa dữ liệu nhạy cảm:

~~~http
Cache-Control: no-store
~~~

Nếu cần ngăn shared cache nhưng cho phép browser lưu trong thời gian ngắn, private, max-age=N có thể phù hợp sau khi đánh giá thiết bị và độ nhạy dữ liệu.

## 8. Revalidation: ETag, Last-Modified và 304

Khi response đã stale hoặc có no-cache, cache có thể hỏi origin xem representation có thay đổi không.

### 8.1. ETag và If-None-Match

Origin trả validator:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=0, must-revalidate
ETag: "catalog-v12"
Content-Type: application/json

{"version":12,"items":["keyboard","mouse"]}
~~~

Lần sau cache gửi:

~~~http
GET /api/catalog HTTP/1.1
If-None-Match: "catalog-v12"
~~~

Nếu representation chưa đổi, origin trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "catalog-v12"
Cache-Control: public, max-age=0, must-revalidate
~~~

304 không có representation body mới. Cache dùng body đã lưu và cập nhật metadata theo response validation. Nếu nội dung đã đổi, origin trả 200 với body và ETag mới.

### 8.2. Strong và weak ETag

- Strong ETag thường dùng để nhận diện representation byte-for-byte.
- Weak ETag có prefix W/ và thể hiện semantic equivalence, không nhất thiết byte giống hệt.

Ví dụ:

~~~http
ETag: "asset-a1"
ETag: W/"catalog-semantic-v12"
~~~

Chọn validator phù hợp với cách representation được tạo. Không dùng một ETag chung cho các user nếu body hoặc metadata khác nhau.

### 8.3. Last-Modified và If-Modified-Since

Origin có thể trả:

~~~http
Last-Modified: Sun, 22 Nov 2026 04:00:00 GMT
~~~

Cache gửi lại:

~~~http
GET /api/catalog HTTP/1.1
If-Modified-Since: Sun, 22 Nov 2026 04:00:00 GMT
~~~

Nếu tài nguyên chưa thay đổi kể từ thời điểm đó, origin có thể trả 304. Last-Modified có độ phân giải thời gian thường theo giây và có thể kém chính xác hơn ETag khi nhiều thay đổi xảy ra trong một giây hoặc representation phụ thuộc biến thể.

### 8.4. 304 không được vượt qua ranh giới user

Validator phải được tính theo representation và identity context phù hợp. Nếu origin trả cùng ETag cho dữ liệu user A và user B nhưng cache dùng chung response, 304 có thể khiến cache giữ body của user A cho request user B.

Đối với dữ liệu cá nhân, private/no-store và cache key đúng quan trọng hơn việc chỉ thêm ETag. Revalidation không thay thế authorization.

## 9. Thiết kế public response an toàn

### 9.1. Tách endpoint công khai khỏi endpoint cá nhân

| Endpoint | Dữ liệu | Policy gợi ý |
| --- | --- | --- |
| /assets/app.<hash>.js | Asset tĩnh, giống nhau cho mọi người | public, max-age=31536000, immutable |
| /api/catalog | Catalog công khai | public, max-age=60, s-maxage=300 |
| /api/profile | Hồ sơ theo session | private, no-cache hoặc no-store |
| /api/orders | Đơn hàng của user | private, no-store |
| /oauth/callback | Authorization code/state tạm thời | no-store, no-referrer |
| /api/config | Cấu hình chung không có secret | public, max-age=300 |

Đừng trộn dữ liệu public và private trong một response rồi đánh dấu public chỉ vì phần lớn body là dữ liệu công khai.

### 9.2. Chỉ cache representation độc lập với user

Trước khi đánh dấu public, hãy trả lời:

- Body có phụ thuộc Cookie không?
- Body có phụ thuộc Authorization hoặc role không?
- Body có phụ thuộc tenant, locale, geolocation hoặc feature flag không?
- Header response có chứa Set-Cookie, user identifier hoặc quyền không?
- Cache key có phân biệt mọi request header/query ảnh hưởng representation không?
- CDN có bỏ qua hoặc chuẩn hóa query/header nào không?
- Response có chứa URL ký, reset token, invite code hoặc dữ liệu riêng không?

Nếu representation phụ thuộc danh tính, không dùng public shared caching trừ khi đã có thiết kế partition an toàn và được kiểm thử cụ thể.

### 9.3. Dùng versioned asset cho TTL dài

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript
Cache-Control: public, max-age=31536000, immutable
ETag: "app-8f31c2a7"
~~~

Đặt content hash trong URL. Khi deploy version mới, URL mới được tạo; cache không cần purge mọi client ngay lập tức.

### 9.4. Public API có dữ liệu cập nhật thường xuyên

~~~http
Cache-Control: public, max-age=30, s-maxage=120, stale-while-revalidate=30
ETag: "catalog-v12"
Vary: Accept-Encoding
~~~

stale-while-revalidate là extension cho phép cache phục vụ response stale trong khoảng quy định trong khi revalidate ở background, nếu cache implementation hỗ trợ. Chỉ dùng khi dữ liệu có thể chấp nhận độ trễ cập nhật và representation thật sự công khai.

### 9.5. Dữ liệu theo user

~~~http
Cache-Control: private, no-cache
Vary: Accept-Encoding
ETag: "profile-v8"
~~~

Nếu dữ liệu nhạy cảm hoặc không muốn browser cache giữ lại:

~~~http
Cache-Control: no-store
~~~

Không cần thêm public hoặc s-maxage cho response này. Kiểm tra các tầng cache có tuân thủ header và không override bằng custom rule.

### 9.6. Invalidation và purge

Khi public representation thay đổi, có hai cách thường dùng:

- **Version hóa URL:** đổi tên asset theo content hash hoặc version. URL mới tạo cache key mới; đây là cách phù hợp với CSS, JavaScript, font và ảnh build-time.
- **Purge/invalidation:** yêu cầu CDN hoặc reverse proxy xóa entry theo URL, cache tag/surrogate key hoặc rule của nhà cung cấp. Cách này hữu ích với API/catalog có URL ổn định.

Purge ở CDN không tự xóa browser private cache hoặc Cache Storage do Service Worker quản lý. Nếu browser đang giữ response fresh, nó có thể tiếp tục dùng bản cũ cho tới khi freshness hết hạn hoặc ứng dụng đổi URL. Với asset version hóa, trang HTML mới phải tham chiếu URL mới; với API ổn định, chọn TTL và revalidation phù hợp.

Purge cũng có thể mất thời gian lan tới mọi edge node. Trong thời gian đó, một số client có thể nhận phiên bản cũ. Không dùng purge như biện pháp thu hồi dữ liệu cá nhân đã bị cache sai; trước hết phải ngăn shared cache tiếp tục phục vụ response, sau đó xử lý entry đã lộ và điều tra phạm vi ảnh hưởng.

## 10. Cache poisoning và cache deception

### 10.1. Cache poisoning

Cache poisoning xảy ra khi attacker khiến cache lưu một response không mong muốn dưới cache key mà các request hợp lệ khác sẽ dùng. Nguyên nhân thường là origin hoặc cache xử lý request input không nhất quán.

Ví dụ:

1. Origin tạo absolute URL hoặc response body dựa trên X-Forwarded-Host.
2. CDN không đưa X-Forwarded-Host vào cache key.
3. Attacker gửi request với host giả và khiến response độc hại được cache.
4. User khác request cùng URL và nhận response đã bị đầu độc.

Các input cần kiểm tra:

- Host và forwarded host/scheme.
- Query parameter mà origin dùng nhưng CDN bỏ khỏi cache key.
- Header Accept/Accept-Language/Origin.
- Cookie hoặc Authorization.
- Header điều khiển compression, content negotiation hoặc feature flag.
- Path normalization, encoded slash, duplicate query key và URL rewrite.

Phòng vệ:

- Chuẩn hóa host và forwarded header tại trusted proxy.
- Chỉ tin forwarded header do proxy được cấu hình ghi đè.
- Đồng bộ cache key với mọi input ảnh hưởng representation.
- Không phản chiếu dữ liệu request vào HTML/header mà thiếu validation.
- Không cache response có nội dung phụ thuộc input chưa được key hóa.
- Kiểm thử cache bằng nhiều giá trị header/query và nhiều user.

### 10.2. Cache deception

Cache deception xảy ra khi attacker khiến một response động/cá nhân hóa bị cache dưới URL trông giống tài nguyên tĩnh, ví dụ:

~~~text
/account/profile.css
/settings/export.js
~~~

Nếu origin route xử lý các path đó như trang tài khoản nhưng CDN áp rule cache mọi file .css hoặc .js, response cá nhân có thể bị lưu và chia sẻ.

Phòng vệ:

- Không dựa riêng vào phần mở rộng URL để quyết định response có public hay không.
- Đặt Cache-Control private/no-store trên response động và nhạy cảm.
- Tách static asset path khỏi application route.
- Cấu hình CDN cache theo allowlist path đã review.
- Kiểm tra cả URL có path suffix, encoded path và route fallback.

### 10.3. Cache key bỏ qua query parameter

Một số CDN được cấu hình bỏ query parameter khỏi cache key để tăng hit ratio. Nếu origin dùng query để chọn representation, hai URL có thể bị gộp:

~~~text
/api/catalog?currency=VND
/api/catalog?currency=USD
~~~

Nếu cache bỏ currency khỏi key, người dùng có thể nhận sai giá hoặc sai currency. Tương tự với locale, page, version, tenant hoặc filter. Chỉ bỏ query parameter khi đã chứng minh parameter đó không ảnh hưởng response.

### 10.4. Cache poisoning không phải lúc nào cũng cần response public

Shared cache có thể lưu response theo heuristic hoặc policy CDN ngay cả khi origin không đặt public. Do đó, cần kiểm tra toàn bộ cacheability, status code, freshness heuristic và custom CDN configuration. Với response động không muốn cache, đặt private hoặc no-store rõ ràng và kiểm thử thực tế.

## 11. Kiểm tra public response trong DevTools và curl

### 11.1. Network panel

Trong DevTools → Network:

1. Chọn request GET cần kiểm tra.
2. Xem Request URL, Cookie và Authorization nếu có.
3. Xem response Cache-Control, Vary, ETag, Last-Modified, Date, Age và Expires.
4. Xem status, size và dấu hiệu response được phục vụ từ memory/disk cache.
5. Reload để quan sát revalidation hoặc cache hit.
6. So sánh request của hai user/session trong browser profile phù hợp.

Tên cột và cách hiển thị cache source khác nhau giữa browser. Không dựa duy nhất vào dòng from disk cache; cần xem response header và hành vi CDN/origin.

### 11.2. curl kiểm tra header

Xem response:

~~~bash
curl -i https://www.example.com/api/catalog
~~~

Gửi request có Authorization:

~~~bash
curl -i \
  -H 'Authorization: Bearer DEMO-TOKEN' \
  https://www.example.com/api/catalog
~~~

Nếu response có public hoặc s-maxage, kiểm tra kỹ body có thực sự giống nhau giữa các user hay không.

Gửi conditional request:

~~~bash
curl -i \
  -H 'If-None-Match: "catalog-v12"' \
  https://www.example.com/api/catalog
~~~

Quan sát status 304 hoặc 200 tùy validator và representation.

### 11.3. Kiểm tra hai session

Gửi cùng URL bằng hai cookie/session khác nhau và so sánh:

- Body.
- Cache-Control.
- Age.
- ETag.
- Vary.
- CDN cache status header nếu có.

Nếu response khác nhau theo user nhưng CDN báo HIT cho cùng cache key, cần dừng rollout hoặc purge cache và sửa policy trước khi tiếp tục phục vụ.

### 11.4. Không dùng token thật trong lệnh hoặc screenshot

Khi thử Authorization, dùng token demo hoặc môi trường test. Shell history, process log, terminal capture và screenshot có thể giữ credential. Redact Cookie, Authorization và Set-Cookie trước khi chia sẻ kết quả.

## 12. Thực hành: mô phỏng shared cache trả nhầm response

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Server tạo một in-memory cache để mô phỏng hành vi shared cache/CDN:

- /public/catalog: response công khai giống nhau cho mọi user.
- /unsafe/profile: response phụ thuộc header X-Demo-User nhưng cache key cố ý chỉ dùng path. Đây là cấu hình sai để quan sát rò rỉ chéo user.
- /safe/profile: response cá nhân có Cache-Control: private, no-store, không được lab cache lưu.
- /conditional/catalog: minh họa ETag và 304.
- /purge: xóa cache mô phỏng để lặp lại thử nghiệm.

Lab chỉ dùng tên Alice/Bob và dữ liệu giả. In-memory cache là mô hình giáo dục đặt trong cùng Node server, không phải triển khai CDN production.

### 12.1. Tạo file browser-cache-public-lab.mjs

~~~js
import { createServer } from 'node:http';

const sharedCache = new Map();
const FRESHNESS_MS = 30_000;

function sendJson(response, status, body, headers = {}) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    ...headers,
  });
  response.end(JSON.stringify(body));
}

function serveSharedCache(response, key, createRepresentation) {
  const now = Date.now();
  const stored = sharedCache.get(key);

  if (stored && stored.expiresAt > now) {
    const age = Math.floor((now - stored.storedAt) / 1000);
    response.writeHead(200, {
      ...stored.headers,
      Age: String(age),
      'X-Cache': 'HIT',
    });
    response.end(stored.body);
    return;
  }

  const representation = createRepresentation();
  const body = JSON.stringify(representation.body);
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'public, max-age=30, s-maxage=30',
    'X-Cache': 'MISS',
  };

  sharedCache.set(key, {
    body,
    headers,
    storedAt: now,
    expiresAt: now + FRESHNESS_MS,
  });

  response.writeHead(200, headers);
  response.end(body);
}

function callbackPage() {
  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<title>Public response cache lab</title>',
    '<style>',
    'body{font:16px system-ui,sans-serif;max-width:850px;margin:32px auto;padding:0 16px}',
    'button,select{padding:8px;margin:4px}',
    'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f2f2;padding:12px}',
    '</style></head><body>',
    '<h1>Public response and shared cache</h1>',
    '<p>Chỉ dùng dữ liệu giả. Chọn user rồi thử cùng một URL.</p>',
    '<label>User <select id="user"><option>Alice</option><option>Bob</option></select></label>',
    '<p>',
    '<button id="unsafe">Gọi unsafe profile</button>',
    '<button id="safe">Gọi safe profile</button>',
    '<button id="catalog">Gọi public catalog</button>',
    '<button id="conditional">Kiểm tra ETag</button>',
    '<button id="purge">Purge shared cache</button>',
    '</p>',
    '<pre id="output">Chưa có request.</pre>',
    '<script>',
    'const output = document.querySelector("#output");',
    'const user = document.querySelector("#user");',
    'async function call(path, options = {}) {',
    '  const response = await fetch(path, { cache: "no-store", ...options });',
    '  const body = await response.text();',
    '  output.textContent = [',
    '    "status: " + response.status,',
    '    "X-Cache: " + (response.headers.get("x-cache") || "(none)"),',
    '    "Age: " + (response.headers.get("age") || "(none)"),',
    '    "Cache-Control: " + (response.headers.get("cache-control") || "(none)"),',
    '    "ETag: " + (response.headers.get("etag") || "(none)"),',
    '    "body: " + body,',
    '  ].join("\\n");',
    '  return response;',
    '}',
    'document.querySelector("#unsafe").addEventListener("click", () => {',
    '  call("/unsafe/profile", { headers: { "X-Demo-User": user.value } });',
    '});',
    'document.querySelector("#safe").addEventListener("click", () => {',
    '  call("/safe/profile", { headers: { "X-Demo-User": user.value } });',
    '});',
    'document.querySelector("#catalog").addEventListener("click", () => {',
    '  call("/public/catalog");',
    '});',
    'document.querySelector("#conditional").addEventListener("click", async () => {',
    '  const first = await fetch("/conditional/catalog", { cache: "no-store" });',
    '  const etag = first.headers.get("etag");',
    '  const second = await fetch("/conditional/catalog", {',
    '    cache: "no-store",',
    '    headers: { "If-None-Match": etag || "" },',
    '  });',
    '  output.textContent = "first status: " + first.status +',
    '    "\\nETag: " + etag +',
    '    "\\nsecond status: " + second.status +',
    '    "\\nA 304 response has no representation body.";',
    '});',
    'document.querySelector("#purge").addEventListener("click", () => {',
    '  call("/purge", { method: "POST" });',
    '});',
    '</script></body></html>',
  ].join('\n');
}

const server = createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost:3000');

  if (url.pathname === '/') {
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(callbackPage());
    return;
  }

  if (url.pathname === '/unsafe/profile') {
    const requestedUser = request.headers['x-demo-user'] || 'Anonymous';

    // LỖI CỐ Ý: cache key bỏ qua X-Demo-User.
    serveSharedCache(response, url.pathname, () => ({
      body: {
        profile: requestedUser,
        note: 'Response cá nhân bị đánh dấu public và cache theo path.',
      },
    }));
    return;
  }

  if (url.pathname === '/safe/profile') {
    const requestedUser = request.headers['x-demo-user'] || 'Anonymous';
    sendJson(response, 200, {
      profile: requestedUser,
      note: 'Response cá nhân không được shared cache lưu.',
    }, {
      'Cache-Control': 'private, no-store',
      'X-Cache': 'BYPASS',
    });
    return;
  }

  if (url.pathname === '/public/catalog') {
    serveSharedCache(response, url.pathname, () => ({
      body: {
        items: ['keyboard', 'mouse', 'monitor'],
        visibility: 'public',
      },
    }));
    return;
  }

  if (url.pathname === '/conditional/catalog') {
    const etag = '"catalog-v1"';
    const cacheControl = 'public, max-age=0, must-revalidate';

    if (request.headers['if-none-match'] === etag) {
      response.writeHead(304, {
        ETag: etag,
        'Cache-Control': cacheControl,
      });
      response.end();
      return;
    }

    sendJson(response, 200, {
      version: 1,
      items: ['keyboard', 'mouse'],
    }, {
      ETag: etag,
      'Cache-Control': cacheControl,
    });
    return;
  }

  if (url.pathname === '/purge' && request.method === 'POST') {
    sharedCache.clear();
    sendJson(response, 200, {
      cleared: true,
      entries: sharedCache.size,
    });
    return;
  }

  sendJson(response, 404, { error: 'Not found' });
});

server.listen(3000, () => {
  console.log('Open http://localhost:3000');
});
~~~

### 12.2. Chạy lab

~~~bash
node browser-cache-public-lab.mjs
~~~

Mở http://localhost:3000.

### 12.3. Quan sát lỗi public response

1. Nhấn Purge shared cache.
2. Chọn Alice và nhấn Gọi unsafe profile.
3. Kết quả đầu tiên trả profile Alice với X-Cache: MISS.
4. Chọn Bob và nhấn Gọi unsafe profile lần nữa.
5. URL vẫn là /unsafe/profile; cache key mô phỏng chỉ dùng path.
6. Response có thể vẫn chứa profile Alice với X-Cache: HIT.

Đây là lỗi rò rỉ dữ liệu do response cá nhân bị đánh dấu public và cache key bỏ qua header dùng để chọn user. Một CDN thực tế có thể có cache key khác; cần kiểm tra cấu hình thực tế chứ không suy luận từ lab.

### 12.4. So sánh với private, no-store

1. Chọn Alice và nhấn Gọi safe profile.
2. Chọn Bob và nhấn lại.
3. Mỗi response trả đúng user đã chọn.
4. Header hiển thị Cache-Control: private, no-store và X-Cache: BYPASS.

### 12.5. Quan sát public response đúng cách

1. Nhấn Purge shared cache.
2. Nhấn Gọi public catalog.
3. Request đầu tiên là MISS.
4. Nhấn lại; response có thể là HIT với Age tăng theo thời gian.
5. Catalog giống nhau cho mọi user nên việc chia sẻ representation là phù hợp.

### 12.6. Kiểm tra ETag và 304

Nhấn Kiểm tra ETag. Lab gửi request đầu tiên nhận 200 và ETag, sau đó gửi If-None-Match. Server trả 304 nếu validator khớp. Response 304 không có body mới; client có thể dùng representation đã lưu theo quy tắc HTTP cache.

### 12.7. Giới hạn lab

- Shared cache là Map trong một Node.js process, chỉ mô phỏng một phần hành vi CDN.
- Cache key của unsafe endpoint cố ý sai và chỉ dùng path.
- fetch dùng cache no-store để browser cache không che khuất hành vi cache server mô phỏng.
- Lab không mô phỏng nhiều node CDN, purge propagation, stale-while-revalidate hoặc cache collapse.
- Dữ liệu Alice/Bob là giả; không dùng cookie, token hoặc dữ liệu cá nhân thật.
- Lab không thay thế kiểm thử cache key và rule trên CDN đang chạy production.

## 13. Checklist review public response

1. **Phân loại dữ liệu:** xác định response công khai, cá nhân, tenant-specific hay nhạy cảm.
2. **Kiểm tra identity dependency:** body/header có phụ thuộc Cookie, Authorization, role, tenant hoặc user không?
3. **Chọn directive:** public cho representation chia sẻ; private cho response một user; no-store cho dữ liệu không nên lưu; no-cache khi cần revalidation.
4. **Đặt freshness:** chọn max-age cho cache nói chung và s-maxage cho shared cache.
5. **Thiết kế cache key:** bao gồm host, path, query và các biến thể ảnh hưởng response.
6. **Khai báo Vary:** với Accept-Encoding, Accept-Language, Origin hoặc header khác thực sự thay đổi representation.
7. **Không tin Set-Cookie tự chặn cache:** đặt private/no-store rõ ràng.
8. **Xử lý Authorization:** không cho shared cache reuse response xác thực nếu chưa có directive cho phép và representation thực sự công khai.
9. **Dùng validator đúng:** ETag/Last-Modified phải tương ứng với representation và identity context.
10. **Chặn cache poisoning:** chuẩn hóa Host/forwarded headers và không bỏ input khỏi cache key nếu origin dùng input đó.
11. **Chặn cache deception:** không cache chỉ dựa vào extension/path suffix; đặt policy trên response động.
12. **Kiểm tra CDN:** xác minh cache rule, query normalization, cookie handling, header forwarding và purge behavior.
13. **Kiểm thử đa user:** gửi cùng URL bằng hai session khác nhau và so sánh body, Age, ETag, X-Cache.
14. **Kiểm tra Service Worker:** xác minh app không tự cache response riêng trong Cache Storage.
15. **Theo dõi vận hành:** giám sát cache hit/miss, Age, purge, stale response và sự cố cross-user.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “public nghĩa là endpoint không cần authentication.” | public chỉ cho phép cache chia sẻ response; authorization ở origin vẫn là việc riêng. |
| “public tự đặt TTL.” | Cần max-age, s-maxage, Expires hoặc freshness policy khác. |
| “private nghĩa browser không cache.” | private chỉ cấm shared cache; browser private cache vẫn có thể lưu. |
| “no-cache nghĩa không lưu.” | Cache có thể lưu nhưng phải revalidate trước khi reuse. |
| “no-store xóa mọi bản sao dữ liệu.” | Nó điều khiển HTTP cache; không xóa log, analytics, app storage hoặc Cache Storage do code tự quản lý. |
| “Set-Cookie làm response tự động uncacheable.” | Không thể dựa vào Set-Cookie để quyết định cacheability; phải đặt Cache-Control rõ ràng. |
| “Request có Authorization thì CDN không bao giờ cache.” | Shared cache có thể được phép lưu nếu response có directive phù hợp như public hoặc s-maxage. |
| “Vary: Cookie là đủ an toàn cho profile.” | Cache key có thể bị cấu hình bỏ qua; dữ liệu user nên dùng private/no-store. |
| “ETag thay thế authorization.” | ETag chỉ là validator; origin vẫn phải kiểm tra user và representation. |
| “304 không có body nên không thể lộ dữ liệu.” | 304 có thể khiến cache reuse body cũ; validator/cache key sai vẫn có thể gây lộ dữ liệu. |
| “CDN chỉ cache file tĩnh.” | CDN có thể cache HTML/API theo rule; cần kiểm tra cấu hình thực tế. |
| “Purge CDN xóa mọi cache trên browser.” | Purge ở CDN không tự xóa browser cache hoặc Cache Storage. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Public response có ý nghĩa gì?

**Gợi ý trả lời:** Response được đánh dấu để bất kỳ cache nào, gồm shared cache, có thể lưu nếu các điều kiện cache khác cho phép.

**Câu 2.** Vì sao public response cá nhân có thể gây rò rỉ dữ liệu?

**Gợi ý trả lời:** Shared cache có thể lưu response của user A rồi trả cho user B nếu cache key không phân biệt identity hoặc CDN bỏ qua Cookie/Authorization.

**Câu 3.** private khác no-store thế nào?

**Gợi ý trả lời:** private cấm shared cache nhưng vẫn cho private/browser cache lưu; no-store yêu cầu HTTP cache không lưu request/response.

**Câu 4.** no-cache có nghĩa gì?

**Gợi ý trả lời:** Response có thể được lưu, nhưng cache phải revalidate với origin trước khi dùng lại.

**Câu 5.** s-maxage áp dụng cho cache nào?

**Gợi ý trả lời:** Shared cache; nó ghi đè max-age/Expires đối với shared cache và yêu cầu revalidate khi stale.

**Câu 6.** Vì sao Set-Cookie không đủ để ngăn shared caching?

**Gợi ý trả lời:** HTTP caching semantics không coi sự hiện diện của Set-Cookie là chỉ thị cấm cache; response phải có private/no-store rõ ràng nếu không được chia sẻ.

**Câu 7.** Vary có tác dụng gì?

**Gợi ý trả lời:** Nó khai báo request header ảnh hưởng representation để cache phân biệt các biến thể khi match response.

**Câu 8.** ETag và 304 phối hợp ra sao?

**Gợi ý trả lời:** Cache gửi If-None-Match; nếu representation chưa đổi, origin trả 304 để cache dùng body đã lưu và cập nhật metadata.

**Câu 9.** Cache poisoning khác cache deception thế nào?

**Gợi ý trả lời:** Poisoning khiến cache lưu response độc hại dưới key được request khác dùng; deception khiến response động/cá nhân bị cache do URL trông giống tài nguyên tĩnh.

**Câu 10.** Cách kiểm tra quan trọng nhất trước khi bật public cho API?

**Gợi ý trả lời:** Xác minh body và header không phụ thuộc user/session/tenant/Authorization, cache key bao phủ mọi input ảnh hưởng representation và thử cùng URL bằng nhiều identity.

## Tài liệu tham khảo

- IETF — [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html).
- IETF — [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).
- IETF — [RFC 8246: HTTP Immutable Responses](https://www.rfc-editor.org/rfc/rfc8246.html).
- IETF — [RFC 5861: HTTP Cache-Control Extensions for Stale Content](https://www.rfc-editor.org/rfc/rfc5861.html).
- IETF — [RFC 9211: The Cache-Status HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9211.html).
- MDN — [HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching).
- MDN — [Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control).
- MDN — [Vary](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary).
- OWASP — [Web Cache Deception Attack](https://owasp.org/www-community/attacks/Web_Cache_Deception).
- OWASP — [Web Cache Poisoning](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/07-Testing_for_Web_Cache_Poisoning).
