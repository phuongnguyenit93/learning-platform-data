# Cache key: cách trình duyệt xác định response có thể được tái sử dụng

Browser cache lưu response để giảm thời gian tải và lượng dữ liệu phải truyền lại. Khi một request mới xuất hiện, cache phải xác định response cũ có thuộc đúng request và đúng ngữ cảnh hay không. Tập thông tin dùng để nhận diện một mục cache được gọi là **cache key**.

Nếu cache key thiếu một yếu tố làm thay đổi response, browser hoặc intermediary cache có thể trả nhầm nội dung: ngôn ngữ sai, dữ liệu cá nhân của người khác, response CORS không phù hợp hoặc tài nguyên được tạo cho một biến thể request khác. Nếu key chứa quá nhiều yếu tố không cần thiết, cache bị phân mảnh và tỷ lệ cache hit giảm.

Trong HTTP caching, key cơ bản gắn với method và target URI; response có thể khai báo thêm các request header ảnh hưởng nội dung bằng Vary. Browser còn có thể phân vùng cache theo site/top-level context để giảm theo dõi cross-site. Service Worker Cache API có cơ chế matching riêng và không nên bị nhầm với HTTP cache tích hợp của browser.

Bài học thuộc chương **Browser cache**, theo đề bài **Cache key**, trong phạm vi **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cache key và vai trò của nó trong việc tìm response có thể tái sử dụng.
2. Phân biệt HTTP cache key, cache partition key và Cache API matching.
3. Xác định vai trò của request method, scheme, host, port, path và query.
4. Dùng Vary để phân biệt response theo request headers.
5. Giải thích vì sao Vary: Origin quan trọng khi server tạo CORS response theo Origin.
6. Đánh giá tác động của Cookie, Authorization và dữ liệu cá nhân đến cache safety.
7. Phân biệt cache key với freshness, validator và Cache-Control.
8. Sử dụng Fetch cache modes đúng mục đích.
9. Thiết kế cache key và cache namespace cho Service Worker Cache API.
10. Phát hiện cache poisoning, cache confusion và nguy cơ dùng nhầm response giữa người dùng.
11. Kiểm tra cache hit/miss và cache variants bằng DevTools.

## 2. Cache key giải quyết vấn đề gì?

Giả sử browser đã lưu response cho:

```http
GET https://shop.example.test/products/42
Accept-Language: vi
```

Request sau tới cùng URL nhưng có Accept-Language: en. Nếu server trả nội dung theo ngôn ngữ, cache phải biết hai request này có thể cần hai response khác nhau. Nếu cache chỉ xét URL và bỏ qua ngôn ngữ, người dùng có thể nhận trang tiếng Việt trong khi đã yêu cầu tiếng Anh.

Một ví dụ khác là CORS. Server có thể trả Access-Control-Allow-Origin theo Origin của request. Nếu cache dùng chung một response chứa allow-origin của website A cho request từ website B, kết quả có thể sai hoặc gây rò rỉ dữ liệu. Khi response thay đổi theo Origin, server cần khai báo Vary: Origin để cache phân biệt các biến thể.

Cache key trả lời câu hỏi: **response này có được tạo cho đúng request variant hiện tại không?** Các chỉ thị freshness trả lời câu hỏi khác: **response đó còn được phép dùng mà không cần xác minh lại không?**

### Cache hit và cache miss

- **Cache hit:** cache tìm thấy một response phù hợp với key và response còn dùng được theo freshness/validation policy.
- **Cache miss:** không có response phù hợp, response đã hết freshness hoặc cần lấy lại từ network.
- **Variant mismatch:** URI có thể giống nhau nhưng request header được nêu trong Vary khác nên response đã lưu không phù hợp.

Cache hit không chứng minh người dùng có quyền truy cập dữ liệu. Authorization phải được kiểm tra ở server; cache chỉ là cơ chế lưu và tái sử dụng response.

## 3. Phân biệt các loại cache trong browser

Browser có nhiều lớp cache. Chúng có mục đích và quy tắc key khác nhau.

| Loại | Ai quản lý? | Cách nhận diện/matching | Freshness và eviction |
| --- | --- | --- | --- |
| HTTP cache | Browser network stack | Method + target URI, Vary và partitioning theo implementation | Theo HTTP caching headers, validators và chính sách browser. |
| Cache API / CacheStorage | Ứng dụng hoặc Service Worker | Request URL/method và Vary; cache name chọn namespace | Ứng dụng tự quản lý version, expiry và xóa entry. |
| Memory cache | Browser process | Phụ thuộc HTTP cache và implementation | Thường ngắn hạn, có thể bị giải phóng khi tab/process thay đổi. |
| Disk cache | Browser profile | HTTP cache key và metadata nội bộ | Tồn tại qua lần mở browser, tùy quota và eviction. |
| CDN/shared proxy cache | Hạ tầng trung gian | URI, method, Vary và cấu hình cache key riêng | Theo cấu hình CDN/proxy và HTTP directives. |

Không giả định một request chỉ có một nơi lưu. Response có thể được cache ở browser, Service Worker Cache API, reverse proxy và CDN. Mỗi lớp cần được cấu hình đúng với dữ liệu mà nó có thể phục vụ.

### HTTP cache

HTTP cache là cache tích hợp trong browser cho request/response HTTP. Browser tự áp dụng HTTP semantics, freshness, conditional request và response headers như Cache-Control, ETag, Last-Modified, Vary.

Ứng dụng không trực tiếp đặt tên entry trong HTTP cache. Nó điều khiển cách response có thể được lưu/tái sử dụng thông qua URI, method, headers và caching directives.

### Cache API

Cache API là storage lập trình được qua CacheStorage và Cache. Service Worker thường dùng API này để precache app shell, offline page hoặc tài nguyên được chọn.

Ứng dụng chủ động chọn cache name, Request dùng để lưu/match và thời điểm xóa entry. Cache API không tự động vận hành theo toàn bộ freshness semantics của HTTP cache; ứng dụng phải tự quản lý expiry, version và invalidation.

### Hai lớp có thể cùng tồn tại

Một fetch trong trang có thể được Service Worker intercept. Worker có thể trả response từ Cache API hoặc gọi fetch() để browser sử dụng HTTP cache/network. Do đó, DevTools có thể cho thấy response đến từ Service Worker hoặc disk/memory cache tùy đường đi.

Không dùng kết quả một lớp cache để kết luận lớp còn lại đã được cập nhật.

## 4. Primary cache key của HTTP

Theo mô hình HTTP caching, primary cache key được xây dựng từ:

- Request method.
- Target URI.

Target URI bao gồm scheme, authority và path/query. Authority xác định host và port theo URL. Fragment không được gửi trong HTTP request target nên không phải thành phần của HTTP cache key.

### Scheme, host và port

Các URL sau có origin khác nhau:

```text
https://app.example.test/data
http://app.example.test/data
https://api.example.test/data
https://app.example.test:8443/data
```

Scheme, host hoặc port thay đổi có thể tạo target URI khác. Không coi HTTP và HTTPS là cùng một cache entry, hoặc hai subdomain là cùng một host.

### Path

Path thường phân biệt tài nguyên:

```text
/users/me
/users/42
/users/43
```

Nếu response cho từng path khác nhau, chúng phải được cache như các URI khác nhau. Không chuẩn hóa path tùy tiện ở CDN hoặc reverse proxy theo cách khiến hai route có quyền truy cập khác nhau dùng chung cache entry.

### Query string

Query string là một phần của target URI:

```text
/search?q=browser
/search?q=cache
/products?category=security
/products?category=network
```

Các URL khác query thường tạo key khác. Vì vậy, cache-busting bằng query version như ?v=42 tạo một URL variant mới. Điều này hữu ích cho asset versioning nhưng có thể làm cache phân mảnh nếu query chứa timestamp hoặc giá trị ngẫu nhiên không cần thiết.

Không giả định mọi cache hoặc CDN chuẩn hóa thứ tự query, encoding hoặc tham số trùng lặp giống nhau. Nếu ứng dụng coi hai URL là tương đương, hãy định nghĩa canonicalization nhất quán ở tầng routing và cache; không để proxy và origin hiểu URL khác nhau.

### Fragment không thuộc HTTP request

Fragment sau dấu # không được gửi tới server:

```text
https://docs.example.test/guide#section-a
https://docs.example.test/guide#section-b
```

Hai URL có thể hiển thị khác fragment trong browser nhưng HTTP request target vẫn là /guide. Do đó, fragment không tạo một HTTP cache variant riêng. Không đặt secret trong fragment với giả định browser cache sẽ phân biệt nó.

### Method

Method là một phần của primary key theo mô hình HTTP cache. GET là method được cache phổ biến nhất; HEAD có quy tắc liên hệ với metadata của GET. Một số response cho method khác có thể được cache khi semantics và freshness cho phép, nhưng không nên giả định POST request tự động được cache.

Các method không an toàn như POST, PUT hoặc DELETE còn có quy tắc invalidation đối với URI liên quan. Cache key không phải lý do để cache response thay đổi trạng thái một cách tùy tiện.

## 5. Secondary key: Vary header

Primary key chưa đủ nếu server tạo nhiều response cho cùng method và URI dựa trên request headers. Response có thể khai báo header Vary để cache so sánh các request header đó khi tìm variant.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Vary: Accept-Language
Cache-Control: public, max-age=300
```

Nếu response được tạo cho Accept-Language: vi, cache không được dùng nó cho request variant Accept-Language: en như thể hai request giống nhau.

### Vary hoạt động như thế nào?

1. Request đầu tiên gửi URL và request headers.
2. Server trả response có Vary.
3. Cache lưu response cùng metadata của các request header được nêu trong Vary.
4. Request tiếp theo tới cùng primary key.
5. Cache so sánh các header được nêu trong Vary.
6. Nếu phù hợp và response còn fresh, cache có thể reuse; nếu không, cần tìm variant khác hoặc gửi request lên network.

### Vary: Accept-Language

Phù hợp khi server trả nội dung theo ngôn ngữ:

```http
Vary: Accept-Language
```

Request tiếng Việt và tiếng Anh có thể dùng hai cache variant khác nhau. Nếu ngôn ngữ được xác định từ cookie hoặc profile thay vì header Accept-Language, chỉ thêm Vary: Accept-Language là không đủ.

### Vary: Accept-Encoding

Server có thể trả nội dung nén khác nhau:

```http
Vary: Accept-Encoding
```

Cache cần phân biệt response gzip, br hoặc encoding khác theo request header. Nhiều server/CDN tự thêm header này; cần kiểm tra cấu hình để tránh response nén bị dùng sai.

### Vary: Origin

Khi CORS response phụ thuộc Origin, server thường cần:

```http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
```

Nếu server phản chiếu một Origin đã allowlist, response có thể khác theo từng Origin. Vary: Origin giúp cache không tái sử dụng response chứa Access-Control-Allow-Origin của origin khác.

Nếu ACAO là một giá trị cố định cho mọi request, việc cần Vary phụ thuộc cách server tạo response. Khi response thay đổi theo Origin, khai báo Vary là bắt buộc để cache phân biệt. Cấu hình CORS vẫn phải dùng allowlist; Vary: Origin không tự xác thực Origin.

### Nhiều field trong Vary

Có thể nêu nhiều header:

```http
Vary: Accept-Language, Accept-Encoding
```

Cache phải xét tất cả các field được liệt kê. Tên field không phân biệt chữ hoa/thường.

### Vary: *

Vary: * biểu thị response phụ thuộc vào yếu tố ngoài các request header có thể so sánh theo cơ chế Vary thông thường. Nó không match một request khác để reuse theo cách thông thường. Không dùng Vary: * như cách thay thế Cache-Control: no-store cho dữ liệu bí mật; nếu không được phép lưu, hãy nói rõ bằng no-store.

## 6. Cache key và request headers không có trong Vary

Không phải mọi request header đều tự động trở thành một phần của HTTP cache key. Ngoài primary key, cache sử dụng những header được response nêu trong Vary và các partitioning/policy riêng của implementation.

Ví dụ, server trả nội dung theo Accept-Language nhưng quên Vary; hoặc response phụ thuộc X-Tenant-ID nhưng cache không xét header đó. Khi đó, response có thể được dùng cho request khác không cùng ngữ cảnh.

### Cookie và dữ liệu cá nhân

Nếu response phụ thuộc Cookie, cache cần được thiết kế rất cẩn thận. Một browser private cache có thể lưu response riêng cho profile; shared cache như CDN có thể phục vụ nhầm dữ liệu giữa người dùng nếu cấu hình không an toàn.

Với response cá nhân hoặc dữ liệu nhạy cảm:

- Dùng Cache-Control: private nếu chỉ cho phép private cache lưu và dữ liệu có thể được cache theo thiết kế.
- Dùng Cache-Control: no-store nếu response không được lưu trong cache.
- Không dựa vào Vary: Cookie như lớp bảo vệ duy nhất.
- Không đưa cookie/session ID vào URL hoặc custom cache key.
- Kiểm tra cache ở CDN/reverse proxy, không chỉ browser.

Vary: Cookie có thể tạo rất nhiều variant, giảm hiệu quả cache và vẫn không thay thế authorization. Với dữ liệu tài khoản, đơn hàng, hồ sơ hoặc response theo session, no-store thường là lựa chọn an toàn hơn nếu không có yêu cầu cache rõ ràng.

### Authorization header

Request có Authorization cần được xử lý theo HTTP caching rules. Shared cache không được tùy tiện reuse response cho request có Authorization; response phải có directive cho phép shared caching theo chuẩn, ví dụ public, s-maxage hoặc must-revalidate trong trường hợp thích hợp. Không dùng các directive này cho dữ liệu riêng tư chỉ để tăng cache hit.

Browser private cache và shared cache có semantics khác nhau. Không giả định Authorization tự động được thêm vào Vary hoặc mọi cache đều xử lý giống nhau. Nếu response cá nhân không nên được lưu, dùng no-store và kiểm tra toàn bộ cache chain.

### Custom header và tenant

Ví dụ server trả nội dung theo tenant:

```http
X-Tenant-ID: tenant-a
```

Nếu cache không phân biệt tenant, response của tenant A có thể bị phục vụ cho tenant B. Thiết kế tốt hơn là xác định tenant từ authenticated server context và không dùng cache dùng chung cho response cá nhân. Nếu một response public thật sự thay đổi theo header, khai báo Vary tương ứng và kiểm thử cache key ở mọi tầng.

## 7. Cache partitioning trong browser

Ngoài URL và Vary, browser hiện đại có thể phân vùng cache theo ngữ cảnh site để giảm khả năng một website theo dõi người dùng qua tài nguyên bên thứ ba.

Ví dụ:

1. Người dùng mở news.example.
2. Trang tải một script từ cdn.vendor.test.
3. Sau đó người dùng mở shop.example, cũng tải cùng URL script từ cdn.vendor.test.
4. Với cache partitioning, browser có thể dùng cache partition khác nhau theo top-level site, thay vì chia sẻ cùng entry chỉ vì URL CDN giống nhau.

Đây thường được mô tả là double-keyed hoặc partitioned cache: cache key còn gắn với top-level site/network isolation context bên cạnh resource URL. Tên và các thành phần partition key cụ thể phụ thuộc browser và phiên bản.

### Partitioning không thay thế HTTP Vary

Hai cơ chế giải quyết hai chiều khác nhau:

- Vary phân biệt response theo request headers được server khai báo.
- Cache partitioning cô lập cache giữa các top-level site/context theo implementation.

Một response vẫn cần Vary đúng dù browser có partitioning. Không dựa vào partitioning để sửa một cache key sai ở CDN hoặc reverse proxy.

### Partitioning và storage khác

Browser có thể partition nhiều loại state như HTTP cache, Cache API, storage hoặc service worker theo các quy tắc riêng. Không giả định cache partitioning có cùng key hoặc cùng vòng đời với cookie partitioning, localStorage hay IndexedDB.

Kiểm tra browser mục tiêu nếu ứng dụng phụ thuộc vào cache behavior giữa iframe/third-party context. Không thiết kế ứng dụng dựa trên việc cache bên thứ ba chắc chắn được chia sẻ giữa các top-level site.

## 8. Cache key khác freshness và validation

Cache key tìm đúng response variant. Freshness xác định response đó có thể được dùng ngay hay phải kiểm tra lại.

| Cơ chế | Câu hỏi |
| --- | --- |
| Cache key | Đây có phải response cho đúng method, URI, Vary và partition context không? |
| Freshness | Response còn trong thời gian được reuse trực tiếp không? |
| Validator | Nếu stale, server có xác nhận representation chưa thay đổi không? |
| Cache-Control | Response/request được lưu, reuse và validation theo policy nào? |

### Cache-Control: max-age

Ví dụ:

```http
Cache-Control: public, max-age=600
```

Response có thể được cache và fresh trong 600 giây theo HTTP semantics, nếu các điều kiện khác cho phép. max-age không thay đổi cache key.

### no-cache và no-store

```http
Cache-Control: no-cache
```

no-cache cho phép lưu response nhưng yêu cầu cache xác minh lại trước khi reuse theo các quy tắc HTTP. Tên directive dễ gây nhầm; nó không đồng nghĩa “không lưu”.

```http
Cache-Control: no-store
```

no-store yêu cầu cache không lưu request/response. Dùng cho dữ liệu nhạy cảm cần tránh lưu trữ. Nó không xóa bản sao đã ghi trước đó và không thay thế việc xóa cache/storage do ứng dụng quản lý.

### private và public

- private: response dành cho một user; shared cache không được lưu, private cache của browser có thể lưu nếu các directive khác cho phép.
- public: cho phép shared cache lưu response trong các trường hợp mà mặc định có thể bị hạn chế; không dùng cho response chứa dữ liệu riêng tư.

### Validators: ETag và Last-Modified

Response có thể chứa:

```http
ETag: "profile-v17"
Last-Modified: Tue, 10 Nov 2026 10:00:00 GMT
Cache-Control: private, no-cache
```

Khi response stale, browser có thể gửi If-None-Match hoặc If-Modified-Since. Server trả 304 Not Modified nếu representation chưa đổi. Validator giúp xác nhận nội dung của variant đã cache; nó không phải thành phần thay thế cho key.

### Cache-Control không tự tạo cache key riêng

Thêm private, max-age, no-cache hoặc no-store không làm cache phân biệt tenant, locale hay Origin. Nếu response thay đổi theo header, cần Vary/key đúng; nếu không được phép lưu, dùng no-store.

## 9. Fetch cache mode

Fetch API có thuộc tính cache để điều khiển tương tác với HTTP cache. Nó không cấu hình Cache API caches.open() hoặc cache.match().

| Mode | Hành vi khái quát |
| --- | --- |
| default | Browser áp dụng freshness và validation bình thường. |
| no-store | Không đọc từ HTTP cache và không lưu response vào HTTP cache. |
| reload | Bỏ qua response cache hiện có khi tạo request, nhưng có thể cập nhật cache bằng response mới. |
| no-cache | Yêu cầu xác minh lại response trước khi reuse, kể cả khi còn fresh. |
| force-cache | Dùng response cache nếu có, kể cả stale; nếu không có thì fetch network. |
| only-if-cached | Chỉ dùng response cache; nếu không có entry phù hợp, request thất bại/504 theo semantics. Chế độ này yêu cầu mode same-origin. |

Ví dụ:

```js
const response = await fetch('/api/public-catalog', {
  cache: 'no-cache'
});
```

Đây là cách yêu cầu browser xác minh lại cache entry theo HTTP semantics. Nó không có nghĩa response luôn không được lưu.

### Không dùng force-cache cho dữ liệu nhạy cảm

```js
const response = await fetch('/api/account', {
  cache: 'force-cache'
});
```

Nếu response có thể thay đổi theo session hoặc user, force-cache có thể làm ứng dụng hiển thị dữ liệu cũ. Chọn response headers và cache mode theo contract; dữ liệu nhạy cảm thường cần no-store.

### no-store cho request nhạy cảm

```js
const response = await fetch('/api/private-profile', {
  cache: 'no-store',
  credentials: 'same-origin'
});
```

Fetch cache mode này điều khiển HTTP cache. Nếu Service Worker tự lưu response vào Cache API, worker vẫn phải chủ động tôn trọng policy của ứng dụng; đừng giả định cache mode tự ngăn một đoạn code cache.put().

## 10. Cache key trong Service Worker Cache API

Cache API cung cấp một namespace có tên và các entry được matching theo Request/Response. Ví dụ:

```js
const CACHE_NAME = 'app-shell-v3';

async function cacheAppShell() {
  const cache = await caches.open(CACHE_NAME);
  await cache.addAll([
    '/',
    '/offline.html',
    '/assets/app.8f31c2.js',
    '/assets/app.91a7d0.css'
  ]);
}
```

Tên cache phân chia namespace. Trong một cache, Request/URL và các quy tắc matching xác định entry phù hợp. Hai cache có tên khác nhau có thể chứa entry cùng URL mà không phải cùng một mục.

### cache.match()

```js
const cache = await caches.open('app-shell-v3');
const response = await cache.match('/offline.html');
```

Cache API matching xét URL và method theo quy tắc của API, cùng Vary mặc định. Mặc định, query string được xét; method không phải GET không match như một entry thông thường; Vary được xét trừ khi dùng tùy chọn bỏ qua.

### ignoreSearch

```js
const response = await cache.match('/catalog?lang=vi', {
  ignoreSearch: true
});
```

ignoreSearch: true bỏ qua query string khi matching. Điều này có thể hữu ích khi query chỉ chứa tham số tracking không ảnh hưởng representation, nhưng nguy hiểm nếu query có lang, tenant, user, filter hoặc version làm thay đổi nội dung.

Không dùng ignoreSearch cho URL chứa credential, user context hoặc tham số quyết định quyền truy cập.

### ignoreVary

```js
const response = await cache.match(request, {
  ignoreVary: true
});
```

ignoreVary: true bỏ qua sự khác nhau của request headers được response khai báo trong Vary. Nếu response phụ thuộc Accept-Language, Origin hoặc một header khác, tùy chọn này có thể trả nhầm variant.

Chỉ dùng khi ứng dụng đã chứng minh header đó không làm thay đổi representation trong cache namespace đang xét. Mặc định nên giữ Vary matching.

### ignoreMethod

ignoreMethod: true yêu cầu Cache API bỏ qua kiểm tra method khi matching. Đây là tùy chọn hiếm dùng; không dùng để biến response GET thành response cho thao tác ghi hoặc để làm mờ semantics của request. Giữ method matching mặc định trong ứng dụng thông thường.

### CacheStorage.match() và cache name

```js
const response = await caches.match('/offline.html');
```

caches.match() tìm qua các cache trong CacheStorage. Nếu nhiều cache cùng có URL, kết quả có thể đến từ cache được tìm thấy trước theo thứ tự API. Với logic ứng dụng, mở cache có tên rõ ràng rồi gọi cache.match() giúp tránh match nhầm entry từ cache khác.

## 11. Cache API không tự tuân thủ HTTP freshness

Cache API là storage do ứng dụng điều khiển. Nó không tự động hết hạn entry theo Cache-Control: max-age, không tự revalidate bằng ETag và không tự xóa cache cũ khi asset đổi.

Ứng dụng phải tự:

- Đặt tên cache theo version.
- Xác định URL/Request được phép lưu.
- Quyết định response nào được lưu.
- Quản lý expiry hoặc version metadata nếu cần.
- Xóa cache cũ khi activate worker mới.
- Tránh lưu response chứa dữ liệu cá nhân hoặc token.
- Cập nhật entry khi nội dung thay đổi.

### Ví dụ cache-first có giới hạn

```js
const STATIC_CACHE = 'static-v4';
const ALLOWED_PATHS = new Set([
  '/',
  '/offline.html',
  '/assets/app.js',
  '/assets/app.css'
]);

async function cacheFirst(request) {
  if (request.method !== 'GET') {
    return fetch(request);
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin ||
      !ALLOWED_PATHS.has(url.pathname)) {
    return fetch(request);
  }

  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  const cacheControl = response.headers.get('Cache-Control') || '';
  const noStore = cacheControl.toLowerCase().includes('no-store');
  if (response.status === 200 &&
      response.type === 'basic' &&
      !noStore) {
    await cache.put(request, response.clone());
  }
  return response;
}
```

Ví dụ chỉ cache một allowlist tài nguyên tĩnh cùng origin. Trong ứng dụng thực tế, cần cân nhắc query string/version, response headers, loại nội dung, update strategy và giới hạn dung lượng. Không dùng cùng cache cho app shell và API cá nhân.

### Không cache mọi request trong fetch handler

Một lỗi phổ biến:

```js
self.addEventListener('fetch', (event) => {
  event.respondWith((async () => {
    const cache = await caches.open('everything');
    const cached = await cache.match(event.request);
    if (cached) return cached;

    const response = await fetch(event.request);
    await cache.put(event.request, response.clone());
    return response;
  })());
});
```

Đoạn code minh họa này nguy hiểm nếu áp dụng cho mọi request: có thể lưu response cá nhân, API theo session, lỗi server, redirect hoặc response không phù hợp; đồng thời bỏ qua chiến lược freshness và invalidation.

Hãy phân loại request trước khi cache: static versioned asset, public API, navigation hay private API. Chỉ lưu những loại được cho phép và kiểm tra status/type/header trước khi put().

## 12. Cache key, CORS và response theo Origin

Một API có thể cho phép nhiều frontend origin:

```js
const allowedOrigins = new Set([
  'https://app.example.test',
  'https://admin.example.test'
]);

function corsHeaders(request) {
  const origin = request.headers.get('Origin');
  const headers = new Headers({
    'Vary': 'Origin'
  });

  if (allowedOrigins.has(origin)) {
    headers.set('Access-Control-Allow-Origin', origin);
  }

  return headers;
}
```

Nếu response thay đổi theo Origin, Vary: Origin cần được giữ trên response phù hợp để cache phân biệt variant. Hãy đảm bảo cả response được phép và response bị từ chối đều có caching behavior nhất quán với cách server chọn ACAO.

### Vary không phải CORS allowlist

Vary: Origin chỉ ảnh hưởng cache matching. Nó không kiểm tra Origin có đáng tin hay không, không cấp quyền truy cập và không thay authorization.

Server vẫn phải:

- So sánh Origin với allowlist chính xác.
- Không phản chiếu Origin bất kỳ.
- Chỉ bật credentialed CORS cho origin cụ thể được tin cậy.
- Dùng Access-Control-Allow-Credentials: true chỉ khi cần.
- Không dùng Access-Control-Allow-Origin: * cùng credentialed response.
- Kiểm tra quyền người dùng ở API.

### CDN và CORS

Nếu CDN cache response CORS nhưng không đưa Origin vào cache key/variant, response cho origin này có thể bị trả cho origin khác. Kiểm tra cấu hình CDN để bảo đảm nó tôn trọng Vary: Origin hoặc cấu hình cache key tương đương. Không chỉ kiểm tra header ở origin server.

## 13. Cache poisoning và cache confusion

Cache poisoning xảy ra khi attacker khiến cache lưu response bị ảnh hưởng bởi input không được đưa vào cache key, sau đó response đó được phục vụ cho request khác.

### Unkeyed input

Giả sử origin tạo response dựa trên X-Forwarded-Host, nhưng CDN chỉ key theo URL và không xét header này. Attacker có thể gửi header độc hại để response chứa host không mong muốn được cache; request tiếp theo nhận response đó.

Biện pháp:

- Không dùng header không tin cậy để tạo nội dung cacheable.
- Chuẩn hóa và xác thực forwarded headers tại trusted proxy.
- Nếu response thực sự thay đổi theo request header, khai báo Vary hoặc cấu hình cache key tương ứng.
- Không phản chiếu Host, Origin hoặc input tùy ý vào HTML/script/redirect.
- Purge cache sau khi phát hiện poisoned response.

### Cache key quá rộng

Nếu cache bỏ qua query, Cookie, Origin hoặc tenant header nhưng response phụ thuộc chúng, có nguy cơ phục vụ nhầm variant.

| Response phụ thuộc | Nếu key bỏ qua | Nguy cơ |
| --- | --- | --- |
| Accept-Language | Ngôn ngữ request | Trả sai ngôn ngữ. |
| Origin | Origin frontend | ACAO sai, lỗi CORS hoặc response bị dùng nhầm. |
| Cookie/session | Người dùng | Rò rỉ dữ liệu giữa user. |
| Tenant header | Tenant | Rò rỉ dữ liệu giữa tenant. |
| Query filter | Filter/search parameter | Trả nhầm kết quả hoặc trang cá nhân hóa. |

### Cache key quá hẹp

Nếu key phân biệt các tham số không ảnh hưởng nội dung, cache bị phân mảnh:

- Timestamp ngẫu nhiên trong query.
- Tracking parameter không cần thiết.
- Tham số thứ tự khác nhau nhưng server coi tương đương.
- Header không cần thiết được thêm vào Vary.

Không bỏ tham số chỉ để tăng hit ratio nếu nó ảnh hưởng representation hoặc quyền truy cập. Tối ưu cache key phải giữ đúng semantics và boundary bảo mật.

### Cache deception

Một số ứng dụng và CDN phân loại cache dựa trên phần mở rộng path hoặc rule tĩnh. Nếu route cá nhân có thể được hiểu nhầm như tài nguyên tĩnh, attacker có thể khiến response riêng tư được cache. Đảm bảo route API/account có cache policy rõ ràng và CDN không cache response nhạy cảm chỉ vì URL trông giống file ảnh/CSS.

## 14. Thiết kế cache key an toàn theo loại dữ liệu

| Loại tài nguyên | Key/variant cần quan tâm | Chính sách thường phù hợp |
| --- | --- | --- |
| JS/CSS có content hash | Scheme/host/path chứa hash; query nếu có ảnh hưởng | Cache public dài hạn, immutable khi URL thay đổi theo nội dung. |
| HTML app shell | URL và deployment version | Revalidate hoặc chiến lược cập nhật app shell; quản lý cache version. |
| Nội dung đa ngôn ngữ | Accept-Language hoặc locale trong URL | Vary đúng header hoặc URL locale rõ ràng. |
| Public API theo query | Query parameter ảnh hưởng representation | Giữ query trong key; cache có freshness phù hợp. |
| API theo session | Cookie/Authorization và user context | Thường no-store; không cache shared. |
| CORS API theo Origin | Origin nếu response header thay đổi theo Origin | Vary: Origin và allowlist. |
| Tenant-specific data | Tenant identity từ authenticated context | Private/no-store; tránh shared cache nếu không có thiết kế cách ly rõ. |
| Password reset/OAuth callback | Query chứa code/token | no-store, no-referrer và xử lý/loại URL nhạy cảm. |

### Static asset versioning

Tên file content-hashed:

```text
/assets/app.8f31c2.js
/assets/app.91a7d0.css
```

Khi nội dung đổi, hash đổi và URL mới tạo cache key mới. Có thể dùng:

```http
Cache-Control: public, max-age=31536000, immutable
```

Chỉ dùng immutable khi URL thực sự thay đổi mỗi khi nội dung thay đổi. HTML entry point thường cần freshness/revalidation ngắn hơn để browser nhận asset version mới.

### Public API

Nếu response chỉ phụ thuộc URL/query và là dữ liệu công khai, có thể cache theo HTTP semantics với Vary đúng và freshness phù hợp. Không thêm Cookie/Authorization vào response public nếu không cần.

### Private API

Với profile, billing, order, hồ sơ sức khỏe hoặc dữ liệu theo session:

```http
Cache-Control: no-store
```

Đảm bảo CDN, reverse proxy và Service Worker cũng không lưu response. No-store ở HTTP response không tự ngăn ứng dụng gọi Cache API put(); code Service Worker phải có allowlist.

## 15. Kiểm tra cache key bằng DevTools

DevTools giúp quan sát request URL, request headers, response headers và nguồn response. Cache behavior có thể khác theo browser, profile, partition context và trạng thái DevTools.

### Network panel

Mở DevTools → **Network**:

- Bật Preserve log khi cần theo dõi redirect/navigation.
- Xem Request URL và Request Method.
- Xem request headers có các field được nêu trong Vary.
- Xem response headers: Cache-Control, Vary, ETag, Last-Modified, Age.
- Kiểm tra status/indicator cho memory cache, disk cache hoặc Service Worker.
- Tải lại cùng URL và so sánh cache hit/miss.

Tùy browser, Network panel có thể hiển thị (memory cache), (disk cache), from ServiceWorker hoặc thông tin tương đương. Không dựa vào một label duy nhất để kết luận cache key; đối chiếu request/response headers và server logs.

### Application panel

Mở **Application → Cache Storage**:

- Xem tên cache namespace.
- Mở từng cache và kiểm tra Request URL.
- So sánh query string.
- Kiểm tra response headers và Vary.
- Xóa cache lab và chạy lại Service Worker.

Cache Storage hiển thị entry do ứng dụng quản lý. Nó không phải danh sách toàn bộ HTTP cache của browser.

### Disable cache

Tùy chọn **Disable cache** trong Network panel thường chỉ tác động khi DevTools đang mở và có thể làm thay đổi kết quả thử nghiệm. Tắt tùy chọn này khi muốn quan sát cache behavior bình thường; dùng Clear site data hoặc xóa Cache Storage riêng khi cần reset lab.

## 16. Thực hành: quan sát cache key và variants

Thực hành trên localhost hoặc HTTPS staging do người học kiểm soát. Dùng dữ liệu giả và response công khai; không dùng profile, token hoặc dữ liệu người dùng thật.

### 16.1. Kiểm tra primary key theo URL

Tạo endpoint /lab/item trả JSON:

```json
{
  "item": "demo",
  "version": 1
}
```

Gọi lần lượt:

```js
await fetch('/lab/item');
await fetch('/lab/item?lang=vi');
await fetch('/lab/item?lang=en');
```

Quan sát Network và server log. Query string khác tạo target URI khác; không mong đợi cache entry của URL đầu tiên tự động phục vụ hai URL sau.

### 16.2. Kiểm tra Vary: Accept-Language

Tạo endpoint trả nội dung theo Accept-Language và response:

```http
Cache-Control: public, max-age=300
Vary: Accept-Language
```

Gửi hai request với header:

```js
await fetch('/lab/language', {
  headers: { 'Accept-Language': 'vi' }
});

await fetch('/lab/language', {
  headers: { 'Accept-Language': 'en' }
});
```

Kỳ vọng: cache phân biệt hai variant. Sau đó bỏ Vary ở server lab, xóa cache và quan sát vì sao response có thể bị dùng nhầm nếu representation thực sự phụ thuộc header.

### 16.3. Kiểm tra Vary: Origin

Tạo API CORS lab allowlist hai origin và phản chiếu origin được phép vào Access-Control-Allow-Origin. Thêm:

```http
Vary: Origin
```

Gọi từ hai frontend origin khác nhau và kiểm tra response headers/Network. Xác nhận CDN hoặc reverse proxy trong lab cũng tôn trọng Vary.

### 16.4. Kiểm tra Fetch cache mode

Gọi cùng endpoint với các mode:

```js
await fetch('/lab/item', { cache: 'default' });
await fetch('/lab/item', { cache: 'no-cache' });
await fetch('/lab/item', { cache: 'reload' });
await fetch('/lab/item', { cache: 'no-store' });
```

Quan sát request conditional headers và server logs. Kết quả phụ thuộc freshness, validator và browser cache state; ghi lại cả response headers thay vì chỉ đếm request.

### 16.5. Kiểm tra Cache API ignoreSearch

Trong Service Worker hoặc trang cùng origin:

```js
const cache = await caches.open('cache-key-lab');
const requestVi = new Request('/lab/catalog?lang=vi');
const responseVi = new Response('catalog: vi');

await cache.put(requestVi, responseVi);

const exact = await cache.match(
  '/lab/catalog?lang=vi'
);
const other = await cache.match(
  '/lab/catalog?lang=en'
);
const ignored = await cache.match(
  '/lab/catalog?lang=en',
  { ignoreSearch: true }
);

console.log({
  exact: await exact?.text(),
  other: other ? await other.text() : null,
  ignored: await ignored?.text()
});
```

Kỳ vọng: exact match trả nội dung vi; URL lang=en không match chính xác; ignoreSearch có thể trả nhầm nội dung vi. Xóa cache lab sau khi thử.

### 16.6. Kiểm tra Cache API và Vary

Tạo hai response cùng URL nhưng khác nội dung theo Accept-Language, mỗi response có Vary: Accept-Language. Lưu request/response tương ứng và gọi cache.match() với từng header. Xác nhận Vary được xét theo mặc định.

Sau đó thử ignoreVary: true để thấy ứng dụng có thể lấy sai variant. Không dùng tùy chọn này trong production nếu header làm thay đổi representation.

### 16.7. Kiểm tra private response

Tạo endpoint lab trả dữ liệu giả theo session và Cache-Control: private, no-store. Xác nhận Service Worker không gọi cache.put() cho route đó và CDN không cache. Dùng hai account lab riêng để kiểm tra không có response chéo.

### 16.8. Kiểm tra cache partitioning

Trong browser hỗ trợ partitioning, tạo hai top-level site lab cùng tải một tài nguyên từ host CDN lab. Quan sát Network và server request count. Kết quả phụ thuộc browser, privacy mode và phiên bản; ghi nhận hành vi cụ thể thay vì giả định tất cả browser giống nhau.

### 16.9. Bằng chứng cần lưu

| Bằng chứng | Điều cần xác nhận |
| --- | --- |
| URL variants | Query khác tạo request/cache variant khác. |
| Vary language | Accept-Language tạo variant phù hợp. |
| Vary Origin | CORS response không bị dùng nhầm giữa origin. |
| Fetch modes | no-cache/reload/no-store ảnh hưởng HTTP cache như dự kiến. |
| Cache API query | ignoreSearch có thể gộp URL khác query. |
| Cache API Vary | ignoreVary có thể bỏ qua variant. |
| Private response | Response session không vào shared/app cache. |
| Partitioning | Ghi nhận cache behavior giữa top-level site trên browser mục tiêu. |

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Người dùng thấy ngôn ngữ của người khác | Response theo Accept-Language nhưng thiếu Vary | Thêm Vary: Accept-Language hoặc đưa locale vào URL. |
| CORS response có ACAO sai | Response theo Origin nhưng cache không phân biệt Origin | Thêm Vary: Origin và kiểm tra CDN key. |
| Dữ liệu user A hiện cho user B | Cache response theo session trong shared/app cache | Dùng private/no-store và không cache route cá nhân. |
| Query khác nhưng trả cùng nội dung | Cache API dùng ignoreSearch hoặc CDN bỏ query | Giữ query ảnh hưởng representation trong key. |
| Response cũ vẫn tồn tại trong Cache API | Mong Cache API tự tôn trọng max-age | Tự quản lý expiry/version/invalidation. |
| HTTP cache miss liên tục | Vary quá rộng hoặc query tracking phân mảnh | Giảm variant chỉ khi không làm thay đổi nội dung/quyền. |
| CDN cache response bị poison | Nội dung phụ thuộc unkeyed header | Xác thực forwarded headers và cấu hình cache key/Vary đúng. |
| no-store nhưng Service Worker vẫn trả dữ liệu cũ | Worker tự cache và không kiểm tra policy | Allowlist rõ; không cache response nhạy cảm. |
| Dùng force-cache cho profile | Cache mode ép dùng response stale | Dùng no-store hoặc policy phù hợp dữ liệu cá nhân. |
| Xóa HTTP cache nhưng app vẫn offline | Cache Storage còn entry | Xóa Cache Storage và kiểm tra Service Worker. |
| Cache key dùng cả timestamp | URL luôn khác nhau | Dùng content hash/version ổn định khi nội dung đổi. |
| Dựa vào partitioning để bảo vệ CDN | Partitioning chỉ ở browser | Cấu hình key/Vary và access policy ở từng cache layer. |

## 18. Checklist production

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Primary key | Method và target URI có phân biệt representation đúng không? | Scheme/host/port/path/query được giữ đúng semantics. |
| Query | Query nào thực sự ảnh hưởng nội dung/quyền? | Không bỏ query cần thiết khỏi key. |
| Vary | Response phụ thuộc request header nào? | Vary liệt kê đủ field ảnh hưởng representation. |
| CORS | ACAO có thay đổi theo Origin không? | Vary: Origin và allowlist chính xác. |
| Cookie | Response phụ thuộc session/user không? | private/no-store theo yêu cầu; không shared-cache dữ liệu cá nhân. |
| Authorization | Shared cache có thể lưu response auth không? | Chỉ cho phép theo HTTP directive và threat model rõ; dữ liệu nhạy cảm no-store. |
| Partitioning | Có giả định cache chia sẻ giữa top-level sites không? | Kiểm thử browser mục tiêu; không dùng partitioning thay server policy. |
| Freshness | Cache key có bị nhầm với max-age/ETag không? | Key, freshness và validation được cấu hình riêng. |
| Fetch | Cache mode có phù hợp dữ liệu không? | Không force-cache private data. |
| Cache API | Cache name và URL allowlist có rõ không? | Cache namespace/version được quản lý chủ động. |
| Matching options | Có dùng ignoreSearch/ignoreVary/ignoreMethod không? | Chỉ dùng khi đã chứng minh an toàn cho representation. |
| Service Worker | Worker có cache response cá nhân hoặc lỗi không? | Chỉ cache tài nguyên đã phân loại/allowlist. |
| CDN/proxy | Cache key có đồng nhất với origin semantics không? | Vary và custom key được kiểm tra ở mọi tầng. |
| Cache poisoning | Có response phụ thuộc unkeyed header/input không? | Forwarded headers được xác thực; input không tin cậy không tạo cacheable response. |
| Invalidation | Asset/API update có xóa hoặc thay version entry không? | Versioning và purge có quy trình. |
| Observability | Có thể xác định cache hit/miss/variant mà không log secret không? | Log key metadata đã chuẩn hóa, không log credential. |
| Testing | Có test nhiều user, locale, Origin, query và cache mode không? | Có bằng chứng DevTools và staging. |

## 19. Câu hỏi tự kiểm tra

1. Cache key có nhiệm vụ gì và khác freshness như thế nào?
2. Primary cache key của HTTP gồm những thành phần nào?
3. Vì sao fragment không phải một phần của HTTP request cache key?
4. Query string ảnh hưởng cache key và cache-busting ra sao?
5. Vary bổ sung thông tin nào vào việc chọn response variant?
6. Vì sao API CORS phản chiếu Origin thường cần Vary: Origin?
7. Vì sao Vary: Cookie không phải giải pháp tổng quát cho dữ liệu cá nhân?
8. Cache partitioning khác Vary như thế nào?
9. Cache-Control no-cache khác no-store ra sao?
10. Fetch cache mode no-store có tự ngăn Service Worker gọi Cache API put() không?
11. Cache API ignoreSearch và ignoreVary có thể gây lỗi bảo mật nào?
12. Vì sao CDN có thể bị cache poisoning khi response phụ thuộc header không nằm trong key?
13. Khi nào nên dùng content-hashed URL và immutable?
14. Làm thế nào kiểm tra HTTP cache và Cache Storage bằng DevTools?

**Tiêu chí hoàn thành:** người học có thể xác định primary/secondary cache key, giải thích Vary và cache partitioning, phân biệt HTTP cache với Cache API, chọn Cache-Control/Fetch mode phù hợp, thiết kế cache cho static/public/private/CORS response và phát hiện cache confusion hoặc poisoning bằng thực hành DevTools.
