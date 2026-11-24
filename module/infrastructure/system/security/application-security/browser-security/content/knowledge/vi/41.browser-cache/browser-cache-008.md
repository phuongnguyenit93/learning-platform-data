# Cache invalidation

> **Chương:** Browser cache  
> **Chủ đề:** Cache invalidation  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt HTTP cache, Cache Storage, Service Worker cache, CDN cache và Back/Forward Cache.
2. Giải thích freshness, validation, conditional request và phản hồi 304 Not Modified.
3. Chọn đúng Cache-Control, ETag, Last-Modified và Vary.
4. Thiết kế cache invalidation bằng TTL, revalidation, URL versioning và CDN purge.
5. Quản lý cache khi deploy SPA, static asset và Service Worker.
6. Ngăn dữ liệu cá nhân hoặc response phụ thuộc quyền truy cập bị dùng lại sai người dùng.
7. Chẩn đoán stale content, cache key mismatch và lỗi triển khai khi invalidation.
8. Kiểm thử cache headers và conditional request bằng DevTools cùng Node.js lab.

## 1. Cache invalidation là gì?

Browser cache lưu response để giảm thời gian tải, tiết kiệm băng thông và giảm tải server. Khi tài nguyên thay đổi, ứng dụng cần bảo đảm browser và các cache trung gian không tiếp tục dùng bản cũ quá thời gian cho phép.

Cache invalidation là quá trình làm cho bản cache cũ không còn được sử dụng, hoặc buộc cache kiểm tra lại với origin trước khi dùng. Đây là một phần của thiết kế vòng đời dữ liệu: cần xác định tài nguyên nào được cache, cache trong bao lâu, cách nhận biết bản mới và cách xử lý khi deploy hoặc thu hồi dữ liệu.

Ví dụ:

- Logo và JavaScript có tên file chứa content hash có thể cache lâu vì URL đổi khi nội dung đổi.
- HTML của SPA thường cần revalidate để browser nhận manifest và asset version mới.
- API catalog có thể dùng ETag để browser hỏi origin xem representation có thay đổi không.
- Response chứa thông tin tài khoản cần policy riêng để không bị shared cache hoặc browser profile khác sử dụng.
- Service Worker có thể trả response từ Cache Storage ngay cả khi HTTP cache đã được cập nhật.

Không có một nút “clear cache” duy nhất bao phủ mọi lớp. Browser HTTP cache, Cache Storage, CDN, reverse proxy, application cache và bfcache có vòng đời cùng cơ chế invalidation khác nhau.

## 2. Phân biệt các loại cache

| Loại | Nơi lưu | Cách kiểm soát/invalidate |
|---|---|---|
| Browser HTTP cache | Browser-managed cache | Cache-Control, Expires, validators, URL versioning, browser cache controls |
| Memory cache | Vùng cache trong tiến trình browser | Browser tự quản lý; thường mất khi tiến trình/tab kết thúc |
| Disk cache | Bộ nhớ lưu trữ của browser | HTTP caching rules, browser settings và eviction |
| Cache Storage | Storage API theo origin, thường dùng với Service Worker | caches.delete(), cache.delete(), versioned cache names |
| Service Worker response logic | Code trong worker quyết định trả network hay cache | Update worker, đổi cache strategy, cleanup cache cũ |
| CDN/shared cache | Edge node hoặc reverse proxy | TTL, purge/invalidation API, surrogate key/tag, versioned URL |
| Back/Forward Cache | Snapshot document để Back/Forward nhanh | Browser lifecycle; không phải HTTP cache và không xóa bằng Cache-Control đơn giản |
| Application data cache | State trong framework, query client hoặc JavaScript memory | Invalidate query/key, refetch, clear store theo user/session |

### 2.1. HTTP cache và Cache Storage không giống nhau

HTTP cache tuân theo HTTP caching semantics: freshness lifetime, validators, Cache-Control, Expires và Vary. Browser tự quyết định lưu response theo những quy tắc này.

Cache Storage là API mà ứng dụng hoặc Service Worker chủ động quản lý. Một response có thể được lưu trong Cache Storage bằng cache.put() ngay cả khi ứng dụng có logic riêng về thời hạn. Đổi Cache-Control trên response không tự động xóa entry mà Service Worker đã lưu trước đó.

Nếu trang luôn nhận dữ liệu cũ, kiểm tra cả Network panel lẫn Application → Cache Storage và trạng thái Service Worker. Chỉ nhìn header của response origin chưa đủ để kết luận response cuối cùng được render từ đâu.

### 2.2. Back/Forward Cache là cơ chế khác

Back/Forward Cache (bfcache) lưu snapshot document để browser khôi phục khi người dùng Back hoặc Forward. Nó có thể giữ DOM và JavaScript state của trang. Đây không phải response cache và không được invalidated bằng ETag hay CDN purge.

Ứng dụng có dữ liệu nhạy cảm hoặc trạng thái session cần xử lý lifecycle như pageshow, pagehide và event.persisted. Khi trang được khôi phục, kiểm tra lại trạng thái cần thiết trước khi cho phép thao tác. Server vẫn phải kiểm tra authorization cho mọi request có side effect.

## 3. HTTP caching: freshness và validation

HTTP cache thường có hai cách quyết định dùng response:

1. **Freshness:** response còn mới trong khoảng thời gian được phép, nên cache có thể dùng lại mà không hỏi origin.
2. **Validation:** response đã stale hoặc policy yêu cầu kiểm tra; cache gửi conditional request để origin xác nhận representation chưa đổi.

### 3.1. Freshness lifetime

Server có thể dùng Cache-Control max-age để chỉ định thời gian response được xem là fresh:

```http
Cache-Control: public, max-age=3600
```

Trong ví dụ này, cache có thể dùng response trong một giờ mà không cần revalidate, tùy các directive khác và cache behavior. Với shared cache/CDN, s-maxage có thể chỉ định freshness riêng:

```http
Cache-Control: public, max-age=60, s-maxage=600
```

Browser private cache dùng max-age=60; shared cache có thể dùng s-maxage=600. s-maxage cũng có các tác động liên quan tới directive shared-cache như proxy-revalidate.

Expires là cơ chế freshness cũ hơn dùng ngày/giờ tuyệt đối. Khi có max-age, max-age được ưu tiên trong HTTP caching semantics. Với ứng dụng mới, thường dùng Cache-Control để policy rõ ràng hơn.

### 3.2. no-cache, no-store và max-age=0

Ba cấu hình này có ý nghĩa khác nhau:

| Directive | Ý nghĩa |
|---|---|
| no-cache | Có thể lưu response nhưng phải revalidate trước khi dùng lại |
| no-store | Cache không được lưu response theo HTTP caching rules |
| max-age=0 | Response hết freshness ngay; thường dẫn tới validation khi có validator |

no-cache không có nghĩa “không cache”. Đây là nhầm lẫn phổ biến. Nó hữu ích cho HTML/API muốn browser lưu response nhưng xác nhận với origin trước khi dùng lại.

no-store phù hợp với response nhạy cảm hoặc dữ liệu không nên được lưu trong HTTP cache. Tuy nhiên, nó không xóa dữ liệu đã được JavaScript lưu trong localStorage, IndexedDB hoặc Cache Storage, và không xóa log đã ghi.

Một response mới mang no-store cũng không phải lệnh purge tổng quát cho mọi bản cache cũ đã tồn tại ở browser hoặc CDN. Nếu cùng URL trước đó đã có response cacheable, hãy thiết kế revalidation, purge hoặc đổi URL phù hợp; không dựa riêng vào no-store để thu hồi bản đã lưu.

### 3.3. private và public

private chỉ cho phép private cache như browser cache lưu response; shared cache không được lưu response đó theo directive này:

```http
Cache-Control: private, max-age=60
```

public cho phép shared cache lưu response nếu các điều kiện khác đáp ứng:

```http
Cache-Control: public, max-age=300
```

Không dùng public cho response chứa dữ liệu người dùng hoặc phụ thuộc cookie/session nếu cache key không được thiết kế để tách đúng representation. Với dữ liệu nhạy cảm, ưu tiên private, no-store hoặc policy được threat model và HTTP semantics xác nhận.

### 3.4. Các directive bổ sung

| Directive | Mục đích |
|---|---|
| must-revalidate | Khi response stale, cache phải validate trước khi dùng lại; không tự dùng stale khi không liên lạc được origin |
| proxy-revalidate | Quy tắc tương tự cho shared cache |
| immutable | Báo rằng representation không thay đổi trong freshness lifetime; phù hợp với URL content-hashed |
| stale-while-revalidate | Cho phép dùng stale response trong khoảng thời gian trong lúc cache revalidate ở nền |
| stale-if-error | Cho phép dùng stale response trong một khoảng khi origin lỗi, nếu policy và cache hỗ trợ |
| no-transform | Ngăn intermediary biến đổi representation trong các trường hợp áp dụng |

Ví dụ asset có content hash:

```http
Cache-Control: public, max-age=31536000, immutable
```

Chỉ dùng lifetime dài khi URL thay đổi theo nội dung. Nếu ghi đè file cùng URL, browser có thể tiếp tục dùng bản cũ trong thời gian dài.

## 4. Validators: ETag và Last-Modified

Validator cho phép cache kiểm tra representation có thay đổi mà không phải tải lại toàn bộ body. Nếu tài nguyên chưa đổi, origin trả 304 Not Modified và cache dùng body đã lưu.

### 4.1. ETag

ETag là validator do origin tạo cho một representation:

```http
HTTP/1.1 200 OK
ETag: "catalog-v17"
Cache-Control: no-cache
Content-Type: application/json
```

Khi cần revalidate, browser gửi:

```http
GET /api/catalog HTTP/1.1
If-None-Match: "catalog-v17"
```

Nếu representation vẫn tương ứng validator, origin trả:

```http
HTTP/1.1 304 Not Modified
ETag: "catalog-v17"
Cache-Control: no-cache
```

Response 304 không có body; cache kết hợp metadata mới với body đã lưu. Nếu dữ liệu thay đổi, origin trả 200 OK, ETag mới và representation mới.

### 4.2. Strong và weak ETag

Strong ETag thường có dạng "abc123" và biểu thị representation byte-for-byte tương đương theo strong comparison. Weak ETag có tiền tố W/, ví dụ W/"catalog-v17", biểu thị semantic equivalence nhưng không cam kết byte giống hệt.

Weak validator có thể hữu ích khi nội dung tương đương về mặt ngữ nghĩa nhưng thay đổi cách serialize hoặc encoding. Với range request và một số thao tác cần byte identity, strong validator có vai trò riêng.

ETag không nhất thiết phải là hash nội dung, nhưng phải thay đổi đúng khi representation cần được xem là khác. Nếu server giữ ETag cũ sau khi nội dung thay đổi, cache có thể tiếp tục dùng dữ liệu sai.

### 4.3. Last-Modified

Origin có thể gửi:

```http
Last-Modified: Sun, 22 Nov 2026 08:00:00 GMT
```

Browser revalidate bằng:

```http
If-Modified-Since: Sun, 22 Nov 2026 08:00:00 GMT
```

Nếu tài nguyên chưa thay đổi kể từ thời điểm đó, server có thể trả 304 Not Modified. Last-Modified có độ phân giải thời gian theo giây và có thể không phân biệt được nhiều lần cập nhật trong cùng một giây hoặc metadata file không phản ánh nội dung. ETag thường chính xác hơn khi cần validator ổn định.

### 4.4. Thứ tự conditional headers

Khi request có cả If-None-Match và If-Modified-Since, server nên áp dụng precedence của HTTP semantics: If-None-Match được ưu tiên. Không để Last-Modified làm kết quả mâu thuẫn với ETag.

If-None-Match cũng có thể dùng với method ghi để kiểm soát precondition, chẳng hạn If-None-Match: * khi tạo resource nếu chưa tồn tại. Đó là conditional request semantics cho thao tác, khác với browser cache revalidation thông thường.

### 4.5. 304 không có nghĩa server không được làm gì

Server vẫn phải xác thực request, xác định representation và đánh giá validator trước khi trả 304. Không bỏ qua authorization vì “chỉ là 304”. Với response cá nhân, phải bảo đảm cache không dùng validator hoặc body của user khác.

## 5. Vary và cache key

Cache key quyết định request nào có thể dùng lại một response đã lưu. Với HTTP cache, method và target URI là phần cốt lõi của key; Vary bổ sung request headers mà representation phụ thuộc. Các cache/CDN có thể thêm host, query normalization, cookie hoặc custom key fields theo cấu hình.

Ví dụ server nén response khác nhau theo Accept-Encoding:

```http
Vary: Accept-Encoding
```

Nếu response còn phụ thuộc ngôn ngữ:

```http
Vary: Accept-Encoding, Accept-Language
```

Cache phải phân biệt các variant tương ứng. Nếu thiếu Vary, cache có thể trả representation tiếng Việt cho request tiếng Anh hoặc response nén sai định dạng.

### 5.1. Vary không phải cách chữa mọi cache key

Không thêm tùy tiện mọi request header vào Vary. Điều đó tạo nhiều variant, giảm cache hit và làm cache khó vận hành. Chỉ vary theo header thực sự làm thay đổi representation.

Vary: * khiến response không khớp để tái sử dụng theo cơ chế cache thông thường. Nó không phải cách tối ưu để bảo vệ dữ liệu cá nhân; dùng private hoặc no-store phù hợp hơn.

### 5.2. Query string và URL normalization

Các URL khác query thường là cache key khác nhau:

- /api/items?page=1
- /api/items?page=2
- /api/items?page=1&lang=vi

CDN có thể cấu hình bỏ qua hoặc sắp xếp query parameters. Nếu cache key bỏ qua tham số làm thay đổi nội dung, cache có thể trả nhầm response. Nếu giữ mọi tracking parameter, cache hit có thể giảm mạnh.

Chỉ normalize query theo schema đã biết. Không bỏ tenant, locale, currency, permission scope hoặc filter có ảnh hưởng nội dung khỏi cache key.

### 5.3. Cookie và Authorization

Shared cache phải xử lý cẩn thận response phụ thuộc Cookie hoặc Authorization. Không giả định mọi CDN tự động tách cache key theo mọi cookie hoặc token. Cũng không đưa raw session ID vào cache key log hoặc cấu hình cache tùy tiện.

Với response cá nhân, dùng Cache-Control: private hoặc no-store tùy nhu cầu và kiểm tra cấu hình CDN. Nếu muốn cache ở edge, thiết kế cache key và authorization-aware caching một cách tường minh, có test cho hai user/tenant khác nhau.

## 6. Các chiến lược cache invalidation

Không phải lúc nào cũng cần purge cache. Chọn chiến lược dựa trên mức độ thay đổi, độ nhạy dữ liệu, yêu cầu freshness và khả năng kiểm soát URL.

### 6.1. TTL ngắn

Đặt max-age ngắn cho dữ liệu thay đổi thường xuyên:

```http
Cache-Control: public, max-age=30
```

Ưu điểm là đơn giản, cache tự hết freshness. Nhược điểm là dữ liệu có thể stale tối đa gần bằng TTL và lượng request revalidation/tải lại tăng khi TTL ngắn.

TTL phù hợp với dữ liệu chấp nhận độ trễ cập nhật có giới hạn. Không dùng TTL dài cho dữ liệu có thể bị thu hồi khẩn cấp nếu không có đường purge hoặc revalidation.

### 6.2. Revalidation bằng ETag

Với response cần giữ local body nhưng phải kiểm tra phiên bản trước khi dùng lại, dùng no-cache cùng ETag hoặc Last-Modified. Browser gửi conditional request; nếu chưa đổi, server trả 304 và tiết kiệm body.

Đây là lựa chọn hữu ích cho HTML, JSON catalog hoặc metadata cần freshness cao nhưng body tương đối lớn. Server vẫn phải tính đúng validator và xác thực quyền truy cập trước khi trả 304.

### 6.3. URL versioning và content hashing

Đổi URL khi nội dung đổi là chiến lược mạnh cho static asset:

```text
/assets/app.4f92c1.js
/assets/styles.81ab02.css
/images/logo.6d03a7.svg
```

Tên file có thể chứa hash của nội dung hoặc build ID. Khi deploy phiên bản mới, HTML tham chiếu URL mới; URL cũ tiếp tục trỏ tới byte cũ và có thể cache lâu.

Kết hợp:

- HTML: no-cache hoặc max-age ngắn để browser kiểm tra bản mới.
- Asset có content hash: public, max-age dài, immutable.
- API động: TTL hoặc validator theo yêu cầu freshness.
- Response cá nhân: private/no-store theo threat model.

Không dùng URL versioning bằng timestamp ngẫu nhiên cho mọi request API; điều đó phá cache hit và có thể tăng tải origin. Version chỉ nên thay đổi khi representation thay đổi.

### 6.4. CDN purge/invalidation

CDN thường cung cấp purge theo URL, prefix, tag hoặc surrogate key. Tag-based purge cho phép xóa một nhóm response liên quan, ví dụ mọi trang sản phẩm thuộc catalog đã thay đổi.

Quy trình cần xem xét:

1. Xác định cache key thực tế tại edge, bao gồm host, path, query và Vary.
2. Purge đúng URL/variant/tag.
3. Kiểm tra các edge region đã nhận invalidation.
4. Kiểm tra origin trả phiên bản mới và validator mới.
5. Theo dõi stale response, cache hit ratio và lỗi origin sau purge.

Purge không nhất thiết diễn ra tức thì ở mọi edge. Một số hệ thống có propagation delay hoặc request đang in-flight vẫn có thể trả dữ liệu cũ. Nếu cần chuyển phiên bản chính xác, URL versioning thường dễ dự đoán hơn purge đơn lẻ.

### 6.5. Soft purge và stale serving

Một số CDN cho phép soft purge: đánh dấu object stale nhưng vẫn giữ bản cũ để phục vụ trong lúc revalidate hoặc khi origin lỗi. Điều này tăng availability nhưng có thể trả nội dung cũ.

Không bật stale-while-revalidate hoặc stale-if-error cho response có tính chất bảo mật hoặc cần thu hồi ngay nếu chưa đánh giá tác động. Với dữ liệu public ít nhạy cảm, stale serving có thể là trade-off hợp lý.

## 7. Deploy không làm người dùng kẹt ở asset cũ

Một lỗi phổ biến là deploy HTML và asset không đồng bộ. HTML mới tham chiếu file JavaScript chưa được upload tới CDN, hoặc HTML cũ vẫn tham chiếu asset đã bị xóa.

### 7.1. Thứ tự deploy an toàn

Với asset content-hashed:

1. Upload asset mới trước, giữ asset cũ còn tồn tại.
2. Xác minh asset mới truy cập được qua origin/CDN.
3. Deploy HTML hoặc manifest mới tham chiếu asset mới.
4. Chờ thời gian cache/rollout phù hợp trước khi xóa asset cũ.
5. Purge HTML nếu cần; không cần purge asset content-hashed cũ để cập nhật nội dung.

Giữ asset cũ giúp tab đang mở hoặc HTML stale vẫn tải được script/style tương ứng. Xóa ngay asset cũ có thể tạo lỗi 404 cho người dùng đang dùng phiên bản trước.

### 7.2. HTML thường cần freshness ngắn

HTML là entry point dẫn tới asset version. Nếu HTML bị cache quá lâu, người dùng có thể tiếp tục nhận tham chiếu asset cũ. Dùng no-cache hoặc TTL ngắn để browser kiểm tra HTML; giữ asset versioned cache lâu.

Với server-side rendered HTML có dữ liệu người dùng, phải đặt policy riêng như private/no-store; không áp dụng public caching chỉ vì HTML là document.

### 7.3. Rolling deployment và compatibility

Trong rolling deployment, một số server có thể chạy phiên bản mới trong khi server khác còn phiên bản cũ. API và asset cần tương thích trong khoảng rollout. Không deploy frontend yêu cầu API mới trước khi backend hỗ trợ hoặc ngược lại nếu không có compatibility window.

Dùng manifest/build ID để chẩn đoán phiên bản. Nếu phát hiện lỗi, rollback HTML/manifest về bản tương thích và giữ asset cần thiết trong thời gian rollback.

## 8. Cache invalidation trong Service Worker

Service Worker có thể intercept request và trả response từ Cache Storage theo strategy do ứng dụng lập trình. Vì vậy, HTTP cache headers không tự động quyết định toàn bộ hành vi offline cache.

### 8.1. Versioned cache names

Một mẫu phổ biến:

```js
const CACHE_NAME = 'app-static-v12';
const PRECACHE_URLS = [
  '/',
  '/offline.html',
  '/assets/app.4f92c1.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names
        .filter((name) => name.startsWith('app-static-') && name !== CACHE_NAME)
        .map((name) => caches.delete(name))
    );
    await self.clients.claim();
  })());
});
```

Đổi cache name khi precache set hoặc semantics thay đổi. Cleanup chỉ xóa namespace do ứng dụng sở hữu; không xóa cache của thư viện hoặc ứng dụng khác trên cùng origin nếu không có quyền quản lý.

### 8.2. Waiting worker và client cũ

Worker mới có thể ở trạng thái waiting trong khi client vẫn được điều khiển bởi worker cũ. Đây là cơ chế tránh thay worker giữa lúc trang đang chạy. `skipWaiting()` và `clients.claim()` có thể làm update nhanh hơn nhưng cũng khiến worker mới điều khiển client đang dùng HTML/asset cũ.

Chỉ kích hoạt worker mới ngay khi đã bảo đảm tương thích giữa worker, cache và client đang mở. Nếu cần thông báo “có phiên bản mới”, cho người dùng reload vào thời điểm phù hợp. Không dùng skipWaiting như nút purge chung.

### 8.3. Xóa entry cụ thể

Có thể xóa một URL khỏi Cache Storage:

```js
const cache = await caches.open('app-api-v3');
await cache.delete('/api/catalog');
```

Hoặc xóa toàn bộ cache thuộc namespace:

```js
const names = await caches.keys();
await Promise.all(
  names
    .filter((name) => name.startsWith('app-api-'))
    .map((name) => caches.delete(name))
);
```

Xóa cache chỉ ảnh hưởng Cache Storage. Browser HTTP cache, CDN cache và JavaScript state có thể vẫn giữ bản khác. Nếu worker đang chạy logic cache-first, nó có thể ghi lại response cũ nếu network strategy hoặc version check sai.

### 8.4. Cache strategy và invalidation

| Strategy | Hành vi | Phù hợp |
|---|---|---|
| Cache First | Trả cache nếu có, fallback network | Asset versioned, offline shell |
| Network First | Thử network, fallback cache | Nội dung cần mới hơn nhưng cần offline fallback |
| Stale While Revalidate | Trả cache ngay, cập nhật cache nền | Nội dung public chấp nhận stale ngắn |
| Network Only | Luôn dùng network | API nhạy cảm hoặc dữ liệu cần kiểm tra quyền mỗi lần |
| Cache Only | Chỉ dùng cache | Precache/offline resource có version rõ ràng |

Chọn strategy theo loại dữ liệu. Không áp dụng cache-first cho API tài khoản chỉ vì nó cải thiện tốc độ.

## 9. Fetch cache modes và application cache

Fetch API có option cache để điều khiển tương tác với HTTP cache của browser:

| Giá trị | Hành vi khái quát |
|---|---|
| default | Dùng HTTP cache theo caching semantics mặc định |
| no-store | Bỏ qua HTTP cache và không lưu response mới vào HTTP cache |
| reload | Bỏ qua cache khi lấy response nhưng cập nhật cache với response nhận được |
| no-cache | Revalidate response trong cache trước khi dùng nếu có thể |
| force-cache | Dùng response cache nếu có, kể cả stale; nếu không có thì lấy từ network |
| only-if-cached | Chỉ dùng cache; nếu không có entry phù hợp thì request thất bại; dùng cùng mode same-origin |

Ví dụ:

```js
const latest = await fetch('/api/catalog', {
  cache: 'no-cache',
});

const uncached = await fetch('/api/private-summary', {
  cache: 'no-store',
});
```

Fetch cache mode điều khiển HTTP cache của browser; nó không tự xóa Cache Storage, CDN cache hoặc state do query library giữ. Nếu Service Worker intercept request, worker có thể trả cache riêng trước khi request tới HTTP cache/network.

Không dùng cache: 'no-store' như cách sửa mọi stale-data bug. Tìm đúng lớp cache đang trả dữ liệu và sửa policy ở nơi đó.

## 10. Cache và bảo mật dữ liệu người dùng

Cache có thể khiến response được dùng lại ngoài thời điểm hoặc ngữ cảnh ban đầu. Điều này đặc biệt quan trọng với ứng dụng có session, tenant, role hoặc dữ liệu cá nhân.

### 10.1. Response cá nhân

Ví dụ response trang hồ sơ:

```http
Cache-Control: private, no-store
```

Nếu cần browser lưu nhưng phải kiểm tra lại trước khi dùng, có thể dùng private, no-cache với validator phù hợp. Tuy nhiên, dữ liệu nhạy cảm có thể vẫn được lưu trong browser cache; đánh giá theo threat model và yêu cầu xóa dữ liệu.

Shared cache không được phép trả response riêng của user A cho user B. Không dựa vào việc request có Cookie hoặc Authorization để mặc định CDN sẽ bypass cache; kiểm tra cấu hình cache key và bypass rules của chính hạ tầng.

### 10.2. Logout và đổi tài khoản

Logout cần revoke session phía server và dọn dữ liệu client do ứng dụng quản lý. Nếu browser Back khôi phục trang từ bfcache hoặc SPA store vẫn giữ dữ liệu, người dùng tiếp theo trên thiết bị có thể nhìn thấy nội dung cũ.

Khi logout/account switch:

- Revoke session/token phía server.
- Xóa state chứa dữ liệu cá nhân trong application store.
- Xóa Cache Storage namespace có response cá nhân.
- Không cache API nhạy cảm trong HTTP cache nếu không có nhu cầu rõ.
- Khi trang được khôi phục từ bfcache, kiểm tra session trước khi hiển thị hoặc cho phép thao tác nhạy cảm.
- Bảo đảm mọi API vẫn kiểm tra authorization server-side.

Cache invalidation không phải authorization. Dù giao diện còn hiện dữ liệu cũ, server không được chấp nhận thao tác nếu session đã revoke hoặc quyền đã thay đổi.

### 10.3. Thu hồi quyền và dữ liệu cũ

Nếu một user mất quyền truy cập tài liệu, việc purge cache giúp giảm khả năng browser/CDN hiển thị bản cũ, nhưng không thể thu hồi bản đã tải về, screenshot, export hoặc copy. Với dữ liệu nhạy cảm, hạn chế tải/lưu ở client ngay từ thiết kế và thực thi authorization mỗi lần truy cập.

Không dùng ETag để thay thế authorization. ETag chỉ là validator của representation; server phải xác thực user và quyền trước khi trả 200 hoặc 304.

### 10.4. Cache poisoning và cache deception

Cache poisoning xảy ra khi attacker làm cache lưu response bị thao túng để request khác nhận nội dung không mong muốn. Cache deception có thể khiến response động hoặc riêng tư bị cache dưới URL mà cache coi là static.

Giảm rủi ro:

- Cache key phải bao gồm mọi thành phần ảnh hưởng representation.
- Không phản chiếu untrusted Host/header/query vào response cacheable nếu không kiểm soát.
- Không cache response cá nhân vào shared cache.
- Chuẩn hóa path và kiểm tra routing giống nhau ở CDN, proxy và origin.
- Dùng Content-Type đúng, X-Content-Type-Options: nosniff và cache policy rõ ràng.
- Test route động có suffix giống file tĩnh, query lạ và header ảnh hưởng nội dung.

## 11. Chẩn đoán cache invalidation

Khi người dùng báo “đã deploy nhưng vẫn thấy bản cũ”, đi theo từng lớp:

1. Xác định URL chính xác và build/version mong đợi.
2. Mở DevTools → Network, xem request có thực sự tới network hay được phục vụ từ memory/disk cache.
3. Kiểm tra status 200/304, Age, Cache-Control, ETag, Last-Modified, Vary và các header CDN như X-Cache hoặc tương đương.
4. Kiểm tra response body và validator tại origin, không chỉ edge.
5. Kiểm tra Service Worker controller và Application → Cache Storage.
6. Kiểm tra framework/query cache hoặc JavaScript memory state.
7. Thử tab mới và hard reload; hiểu rằng hard reload behavior tùy browser và không thay thế purge hoặc sửa policy.
8. Nếu Back/Forward khôi phục nội dung cũ, kiểm tra bfcache và pageshow.

### 11.1. Dấu hiệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| HTML cũ, asset mới | HTML freshness quá dài hoặc edge chưa purge | Kiểm tra HTML Cache-Control, Age và CDN cache |
| HTML mới nhưng JS 404 | Deploy HTML trước asset hoặc xóa asset cũ quá sớm | Kiểm tra manifest, asset upload và rollout order |
| API luôn trả 304 dù dữ liệu đổi | ETag không đổi hoặc validator được tính sai | So sánh body với ETag ở origin |
| User A thấy dữ liệu User B | Shared cache key/bypass rule sai | Test hai session, kiểm tra Cookie/Authorization và cache key |
| Xóa HTTP cache nhưng vẫn thấy bản cũ | Service Worker Cache Storage hoặc app state | Bypass worker, kiểm tra caches.keys() và query cache |
| Chỉ Back mới thấy trang cũ | bfcache khôi phục snapshot | Quan sát pageshow và event.persisted |
| Purge CDN nhưng một số khu vực vẫn cũ | Propagation delay hoặc variant chưa purge | Kiểm tra edge region, host, query và Vary |
| Asset vẫn cũ dù reload | URL không versioned và response immutable/max-age dài | Đổi URL theo content hash hoặc sửa TTL |

### 11.2. DevTools

Trong Chrome/Edge DevTools:

- Network: xem Size/Transferred, status, request/response headers và initiator.
- Disable cache: chỉ có hiệu lực khi DevTools đang mở; chủ yếu hữu ích để chẩn đoán HTTP cache.
- Application → Service Workers: xem controller, update và bypass for network.
- Application → Cache Storage: xem cache names và entries.
- Application → Storage: xem site data và thao tác clear theo origin.
- Performance/Navigation: xem navigation và lifecycle khi cần chẩn đoán bfcache.

Tên cột và hành vi UI có thể khác giữa browser. Ghi nhận chính xác cache source và response headers thay vì chỉ nói “đã clear cache”.

## 12. Thực hành: HTTP cache invalidation với Node.js

Lab mô phỏng một API catalog có ETag và Last-Modified, một asset immutable và một endpoint cập nhật dữ liệu. Bạn sẽ gửi conditional request để thấy 304, cập nhật catalog rồi nhận 200 với validator mới.

Node fetch không triển khai browser HTTP cache tự động; phần kiểm thử bằng Node sẽ gửi If-None-Match và If-Modified-Since thủ công để xác minh semantics phía server. Sau đó dùng browser DevTools để quan sát behavior cache thật.

### Bước 1 — Tạo file `browser-cache-invalidation-lab.cjs`

```js
const http = require('node:http');
const { createHash } = require('node:crypto');

let catalogVersion = 1;
let catalogUpdatedAt = new Date();

function getCatalog() {
  return {
    version: catalogVersion,
    updatedAt: catalogUpdatedAt.toISOString(),
    items: [
      { id: 'book-1', name: 'Browser Security Basics', price: 120 },
      { id: 'book-2', name: 'HTTP Cache Lab', price: 95 },
    ],
  };
}

function createEtag(body) {
  const hash = createHash('sha256').update(body).digest('hex');
  return '"' + hash + '"';
}

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Browser cache invalidation lab</title></head><body>',
  '<h1>Browser cache invalidation lab</h1>',
  '<p>API catalog dùng Cache-Control: no-cache và ETag để revalidate.</p>',
  '<button id="load-default" type="button">Load catalog (default)</button>',
  '<button id="load-revalidate" type="button">Load catalog (no-cache)</button>',
  '<button id="load-no-store" type="button">Load catalog (no-store)</button>',
  '<button id="update" type="button">Update catalog at origin</button>',
  '<button id="private" type="button">Load private sample</button>',
  '<pre id="output"></pre>',
  '<script src="/app.js" defer></script>',
  '</body></html>',
].join('\n');

const appJs = [
  "const output = document.querySelector('#output');",
  'async function loadCatalog(cacheMode) {',
  '  const options = cacheMode ? { cache: cacheMode } : {};',
  '  const response = await fetch("/api/catalog", options);',
  '  const body = await response.json();',
  '  output.textContent = JSON.stringify({',
  '    cacheMode: cacheMode || "default",',
  '    status: response.status,',
  '    etag: response.headers.get("etag"),',
  '    body,',
  '  }, null, 2);',
  '}',
  "document.querySelector('#load-default').addEventListener('click', () => loadCatalog());",
  "document.querySelector('#load-revalidate').addEventListener('click', () => loadCatalog('no-cache'));",
  "document.querySelector('#load-no-store').addEventListener('click', () => loadCatalog('no-store'));",
  "document.querySelector('#update').addEventListener('click', async () => {",
  '  const response = await fetch("/__lab/update", { method: "POST" });',
  '  output.textContent = "Origin update: " + await response.text();',
  '});',
  "document.querySelector('#private').addEventListener('click', async () => {",
  '  const response = await fetch("/api/private");',
  '  output.textContent = "Private sample: " + await response.text();',
  '});',
].join('\n');

function send(res, status, headers, body = '') {
  res.writeHead(status, headers);
  res.end(body);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method === 'GET' && url.pathname === '/') {
    return send(res, 200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
      'X-Content-Type-Options': 'nosniff',
    }, page);
  }

  if (req.method === 'GET' && url.pathname === '/app.js') {
    return send(res, 200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    }, appJs);
  }

  if (req.method === 'GET' && url.pathname === '/api/catalog') {
    const body = JSON.stringify(getCatalog());
    const etag = createEtag(body);
    const lastModified = catalogUpdatedAt.toUTCString();
    const headers = {
      'Cache-Control': 'no-cache',
      'Content-Type': 'application/json; charset=utf-8',
      ETag: etag,
      'Last-Modified': lastModified,
      Vary: 'Accept-Encoding',
    };

    const ifNoneMatch = req.headers['if-none-match'];
    const ifModifiedSince = req.headers['if-modified-since'];
    let notModified = false;

    if (ifNoneMatch) {
      const candidates = ifNoneMatch.split(',').map((value) => value.trim());
      notModified = candidates.some((value) =>
        value === '*' || value.replace(/^W\//, '') === etag
      );
    } else if (ifModifiedSince) {
      const since = Date.parse(ifModifiedSince);
      const modified = Date.parse(lastModified);
      notModified = Number.isFinite(since) && modified <= since;
    }

    if (notModified) {
      console.log('[LAB] catalog conditional hit -> 304', etag);
      return send(res, 304, headers);
    }

    console.log('[LAB] catalog body -> 200', etag);
    return send(res, 200, headers, body);
  }

  if (req.method === 'GET' && url.pathname === '/api/private') {
    return send(res, 200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'private, no-store',
    }, JSON.stringify({ sample: 'synthetic private response', user: 'demo-user' }));
  }

  if (req.method === 'POST' && url.pathname === '/__lab/update') {
    catalogVersion += 1;
    catalogUpdatedAt = new Date();
    console.log('[LAB] catalog updated to version', catalogVersion);
    return send(res, 200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    }, JSON.stringify({ ok: true, version: catalogVersion }));
  }

  if (req.method === 'GET' && url.pathname === '/assets/app.v1.js') {
    return send(res, 200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'public, max-age=31536000, immutable',
    }, 'console.log("versioned asset v1");');
  }

  return send(res, 404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store',
  }, 'Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node browser-cache-invalidation-lab.cjs
```

Mở http://localhost:3000. Nếu cổng 3000 đang được sử dụng, đổi cổng trong `server.listen()` và URL base trong `new URL()`.

### Bước 3 — Quan sát ETag và 304

1. Mở DevTools → Network, bật Preserve log.
2. Nhấn **Load catalog (default)** và quan sát response 200 cùng ETag.
3. Nhấn lại nút; browser có thể dùng cache hoặc revalidate tùy freshness và cache mode.
4. Nhấn **Load catalog (no-cache)**. Browser phải revalidate response; nếu không đổi, server log ghi 304 và DevTools có thể hiển thị 304 hoặc response cache đã được revalidated tùy browser.
5. Quan sát request header If-None-Match và response header ETag.

### Bước 4 — Thay đổi representation

1. Nhấn **Update catalog at origin** để tăng version.
2. Nhấn **Load catalog (no-cache)**.
3. Server trả 200 với body và ETag mới vì representation đã thay đổi.
4. Nhấn lại; server có thể trả 304 cho validator mới.

### Bước 5 — So sánh no-store và asset immutable

1. Nhấn **Load private sample**; kiểm tra Cache-Control: private, no-store.
2. Mở trực tiếp /assets/app.v1.js trong browser và kiểm tra Cache-Control: public, max-age=31536000, immutable.
3. Thử thay nội dung asset trong lab nhưng giữ nguyên URL: browser có thể tiếp tục dùng bản cũ trong freshness lifetime.
4. Đổi URL thành /assets/app.v2.js trong route/build để mô phỏng content versioning; URL mới là cache key mới.

Node fetch test bên dưới xác minh response headers và conditional semantics ở origin. Nó không mô phỏng browser HTTP cache, nên vẫn cần kiểm tra DevTools để quan sát browser thực tế.

### Bước 6 — Kiểm tra thủ công bằng Node

```sh
node -e "const base='http://localhost:3000'; (async()=>{ let r=await fetch(base+'/api/catalog'); const tag=r.headers.get('etag'); console.log('first',r.status,tag); r=await fetch(base+'/api/catalog',{headers:{'If-None-Match':tag}}); console.log('conditional',r.status); await fetch(base+'/__lab/update',{method:'POST'}); r=await fetch(base+'/api/catalog',{headers:{'If-None-Match':tag}}); console.log('after update',r.status,r.headers.get('etag')); })().catch(e=>{console.error(e);process.exitCode=1});"
```

Kết quả mong đợi: request đầu 200, conditional request khi chưa đổi 304, sau update conditional request với ETag cũ trả 200 và ETag mới.

## 13. Checklist triển khai cache invalidation

- [ ] Phân loại rõ HTTP cache, Cache Storage, Service Worker, CDN và application cache.
- [ ] Mỗi loại response có Cache-Control phù hợp với độ nhạy và yêu cầu freshness.
- [ ] Hiểu đúng no-cache, no-store, private, public, max-age và s-maxage.
- [ ] HTML/manifest có TTL ngắn hoặc revalidate để phát hiện build mới.
- [ ] Static asset dùng content hash/versioned URL trước khi áp dụng immutable lâu dài.
- [ ] ETag thay đổi khi representation thay đổi; Last-Modified có độ chính xác phù hợp.
- [ ] Server xử lý If-None-Match precedence so với If-Modified-Since.
- [ ] Response 304 vẫn đi qua authentication và authorization cần thiết.
- [ ] Vary và cache key bao gồm mọi yếu tố làm thay đổi representation.
- [ ] CDN không dùng chung response cá nhân giữa user, tenant hoặc role.
- [ ] Purge được thực hiện đúng URL/variant/tag và có kiểm tra propagation.
- [ ] Deploy asset mới trước HTML mới và giữ asset cũ trong compatibility window.
- [ ] Service Worker dùng cache namespace có version và cleanup đúng phạm vi.
- [ ] skipWaiting/clients.claim chỉ dùng khi worker mới tương thích client đang mở.
- [ ] Logout/account switch xóa application state và Cache Storage nhạy cảm.
- [ ] Server vẫn kiểm tra session và authorization bất kể cache/UI đang hiển thị gì.
- [ ] Cache poisoning/deception được kiểm thử với Host, query, path và header khác nhau.
- [ ] DevTools được dùng để xác định nguồn response thay vì chỉ hard reload.
- [ ] Không coi purge hoặc no-store là cách thu hồi bản dữ liệu đã tải xuống/copy.

## 14. Câu hỏi tự kiểm tra

**1.** Cache invalidation giải quyết vấn đề gì?  
**Trả lời:** Làm cho cache cũ không còn được dùng hoặc buộc cache revalidate trước khi sử dụng response.

**2.** no-cache khác no-store thế nào?  
**Trả lời:** no-cache cho phép lưu nhưng yêu cầu revalidate; no-store yêu cầu không lưu response trong HTTP cache.

**3.** ETag dùng để làm gì?  
**Trả lời:** Là validator đại diện cho một representation; browser gửi If-None-Match để server xác nhận nội dung còn tương ứng hay không.

**4.** 304 Not Modified có body không?  
**Trả lời:** Không. Cache dùng body đã lưu và cập nhật metadata theo response 304.

**5.** Nếu có cả If-None-Match và If-Modified-Since, server ưu tiên điều kiện nào?  
**Trả lời:** If-None-Match được ưu tiên theo HTTP conditional request semantics.

**6.** Vì sao cần Vary?  
**Trả lời:** Để cache phân biệt representation phụ thuộc request header như Accept-Encoding hoặc Accept-Language.

**7.** Vì sao asset content-hashed có thể cache một năm?  
**Trả lời:** Nội dung thay đổi sẽ tạo URL/hash mới; URL cũ vẫn đại diện cho byte cũ.

**8.** Purge CDN có bảo đảm mọi edge lập tức bỏ bản cũ không?  
**Trả lời:** Không nhất thiết. Invalidation có thể cần thời gian lan truyền và phải purge đúng variant/cache key.

**9.** Vì sao đổi Cache-Control không xóa Cache Storage do Service Worker quản lý?  
**Trả lời:** Cache Storage là API do ứng dụng quản lý; phải xóa entry hoặc đổi cache namespace bằng code worker.

**10.** Cache invalidation có thay authorization không?  
**Trả lời:** Không. Server phải xác minh session và quyền ở mọi request; cache purge không thu hồi dữ liệu đã tải hoặc sao chép.

## Tổng kết

Cache invalidation cần được thiết kế theo từng lớp lưu trữ. HTTP cache dùng freshness và validators; ETag/Last-Modified giúp revalidate; Vary và cache key bảo đảm response đúng variant; URL versioning giúp asset immutable an toàn qua deploy. CDN cần purge đúng key/tag, còn Service Worker phải tự quản lý version và Cache Storage. Response cá nhân cần policy riêng, logout phải dọn application state và cache nhạy cảm, nhưng server luôn phải thực thi authorization. Khi chẩn đoán stale content, xác định chính xác response đến từ browser HTTP cache, CDN, Service Worker, bfcache hay application state trước khi thay đổi policy.
