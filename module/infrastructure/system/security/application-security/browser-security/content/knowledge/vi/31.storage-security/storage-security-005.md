# Cache chứa dữ liệu: bảo vệ thông tin người dùng trong browser cache

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt HTTP cache, Cache API/CacheStorage, cache trong ứng dụng và Back/Forward Cache (BFCache).
2. Giải thích dữ liệu nào có thể được lưu trong cache và ranh giới tin cậy của từng loại.
3. Chọn đúng Cache-Control directive cho response công khai, response cá nhân hóa và dữ liệu nhạy cảm.
4. Hiểu vì sao no-store không tự xóa dữ liệu đã lưu trước đó và không tự ngăn service worker gọi Cache API để ghi response.
5. Thiết kế service worker chỉ cache tài nguyên tĩnh đã xác định, tránh lưu API response có thông tin cá nhân.
6. Xử lý logout, đổi tài khoản, cache versioning, invalidation và dữ liệu còn sót trên thiết bị dùng chung.
7. Nhận diện rủi ro XSS, cache poisoning, cache key sai và rò rỉ dữ liệu giữa người dùng/tenant.
8. Kiểm tra browser cache bằng Chrome DevTools, Network panel, Application panel và các bài thực hành an toàn.

> **Bối cảnh:** Module Browser Security phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Bài này tập trung vào cache có thể chứa dữ liệu ứng dụng hoặc dữ liệu người dùng, cách phân loại dữ liệu, giới hạn cache và xử lý vòng đời an toàn.

## 1. Cache có thể chứa những dữ liệu gì?

Cache giúp giảm thời gian tải và giảm số request phải gửi tới server. Trong ứng dụng web, cache có thể chứa:

- HTML của trang.
- JavaScript, CSS, font, hình ảnh và tệp tĩnh.
- JSON trả về từ API.
- Hồ sơ người dùng, danh sách đơn hàng hoặc dữ liệu dashboard.
- Nội dung offline do service worker lưu.
- Kết quả tìm kiếm, bộ lọc hoặc dữ liệu đã tải trước.
- Snapshot trạng thái trang mà browser giữ để quay lại nhanh.

Cache không chỉ là nơi lưu file tĩnh. Nếu ứng dụng cache response có thông tin cá nhân, browser hoặc service worker có thể giữ lại dữ liệu đó sau khi người dùng rời trang, logout hoặc chuyển sang tài khoản khác.

### Vì sao cần phân loại cache?

Tài nguyên công khai và dữ liệu cá nhân có yêu cầu khác nhau:

| Loại dữ liệu | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| Tài nguyên công khai, versioned | JS/CSS có tên chứa hash build | Có thể cache dài hạn, immutable |
| Nội dung công khai nhưng thay đổi thường xuyên | Tin tức, danh mục sản phẩm | Cache có thời hạn hoặc revalidation |
| Nội dung cá nhân hóa | Hồ sơ, lịch sử đơn hàng, dashboard | Hạn chế cache; thường dùng private hoặc no-store tùy độ nhạy |
| Dữ liệu nhạy cảm | Thông tin tài chính, hồ sơ riêng tư, credential, response xác thực | Ưu tiên no-store và tránh ghi vào Cache API |
| Dữ liệu offline do ứng dụng quản lý | Bản đồ offline, tài liệu người dùng tải xuống có chủ đích | Chỉ cache khi có yêu cầu, kiểm soát quyền, vòng đời và xóa dữ liệu |

Không chọn cache policy chỉ dựa trên loại file. Một response JSON có thể công khai, còn một file PDF có thể chứa hợp đồng riêng tư. Hãy phân loại theo nội dung, người được phép đọc và hậu quả nếu dữ liệu còn lại trên thiết bị.

## 2. Bốn loại cache thường gặp trong browser

Từ “cache” thường được dùng cho nhiều cơ chế khác nhau. Cần phân biệt chúng trước khi thiết kế bảo mật.

| Loại | Ai quản lý? | Dữ liệu | Cơ chế kiểm soát chính |
| --- | --- | --- | --- |
| HTTP cache | Browser và các HTTP cache trung gian | Request/response HTTP | Cache-Control, Expires, validators, Vary |
| Cache API / CacheStorage | JavaScript và service worker | Request/Response do ứng dụng chủ động ghi | Cache API, cache name, key, logic xóa và versioning |
| Application memory cache | Code của ứng dụng | Object, state, response đã parse | Vòng đời component/app, logout và xóa state |
| Back/Forward Cache (BFCache) | Browser | Snapshot trang để điều hướng back/forward nhanh | Vòng đời pagehide/pageshow và hành vi browser |

### HTTP cache

Browser có thể lưu response HTTP trong memory hoặc trên đĩa để dùng lại. Các HTTP cache tuân theo quy tắc caching của HTTP, gồm Cache-Control, Expires, ETag, Last-Modified và Vary.

Một số proxy/CDN cũng là shared cache. Nếu cấu hình sai, response cá nhân hóa có thể bị dùng chung giữa nhiều người dùng.

### Cache API và CacheStorage

Cache API cho phép ứng dụng chủ động lưu cặp Request/Response. Service worker thường dùng API này để hỗ trợ offline hoặc cache-first cho tài nguyên tĩnh.

CacheStorage có thể tồn tại qua nhiều lần reload và đóng/mở browser, tùy browser, quota và chính sách lưu trữ. JavaScript cùng origin và service worker có quyền phù hợp có thể đọc hoặc xóa các cache này.

### Application memory cache

Ứng dụng có thể giữ dữ liệu trong biến, state manager hoặc thư viện query cache. Dữ liệu này thường tồn tại trong vòng đời trang/tab, nhưng có thể vẫn nằm trong heap khi trang được giữ ở BFCache.

### Back/Forward Cache

BFCache giữ snapshot của document để browser khôi phục nhanh khi người dùng bấm Back hoặc Forward. Đây không phải HTTP cache và cũng không phải Cache API. Snapshot có thể giữ DOM và trạng thái JavaScript của trang.

Không thể xóa BFCache bằng CacheStorage.delete(). Hãy xử lý việc trang được khôi phục bằng sự kiện pageshow và kiểm tra lại session/quyền truy cập trước khi hiển thị dữ liệu nhạy cảm.

## 3. HTTP cache và Cache-Control

Server dùng Cache-Control để hướng dẫn HTTP caches cách lưu và tái sử dụng response.

### no-store

Với response nhạy cảm:

    Cache-Control: no-store

Directive này yêu cầu private cache và shared cache không lưu response. Đây là lựa chọn quan trọng cho response chứa credential, thông tin tài chính hoặc dữ liệu cá nhân nhạy cảm.

no-store không phải lệnh xóa ngược dữ liệu đã được cache trước đó. Nếu response cũ đã được lưu, cần xử lý invalidation phù hợp; browser không tự tìm mọi bản cũ và xóa chỉ vì response mới có no-store.

no-store cũng không tự ngăn code ứng dụng gọi Cache API và chủ động ghi response vào CacheStorage. Cache API là cơ chế do script quản lý; service worker phải tự quyết định response nào được cache.

### private

    Cache-Control: private

private yêu cầu shared cache không lưu response, nhưng private cache riêng của người dùng, chẳng hạn HTTP cache của browser, vẫn có thể lưu.

Do đó private không đồng nghĩa với “không lưu trên thiết bị”. Nếu response chứa dữ liệu nhạy cảm và không nên tồn tại trong browser cache, dùng no-store.

### no-cache

    Cache-Control: no-cache

no-cache không có nghĩa là “đừng lưu”. Cache có thể lưu response nhưng phải kiểm tra lại với origin trước khi sử dụng bản đã lưu cho request tiếp theo.

Đây là lựa chọn hữu ích khi muốn giữ bản response để revalidate bằng ETag hoặc Last-Modified, nhưng không muốn cache tự dùng bản cũ mà chưa hỏi server.

### max-age

    Cache-Control: private, max-age=60

max-age xác định thời gian response được coi là fresh. Trong ví dụ này, private cache của browser có thể tái sử dụng response trong 60 giây mà không cần revalidation.

Không dùng max-age dài cho dữ liệu thay đổi theo quyền hoặc session nếu không có chiến lược invalidation rõ ràng.

### must-revalidate

    Cache-Control: private, max-age=0, must-revalidate

Khi response đã stale, cache phải revalidate trước khi dùng lại. Nếu origin không thể xác nhận, cache không được tự dùng response stale theo quy tắc thông thường.

### Bảng so sánh directive

| Directive | Có thể lưu? | Điều kiện dùng lại |
| --- | --- | --- |
| no-store | Không | Không được lưu response trong HTTP cache |
| private | Private cache có thể lưu; shared cache không được lưu | Theo freshness và validator |
| no-cache | Có thể lưu | Phải revalidate trước khi reuse |
| max-age=N | Có thể lưu | Có thể reuse khi còn fresh |
| must-revalidate | Có thể lưu | Khi stale phải revalidate |
| public | Cho phép shared cache lưu nếu các điều kiện khác phù hợp | Theo freshness và quy tắc HTTP cache |

Các directive có thể kết hợp. Hãy đọc toàn bộ policy thay vì suy luận từ một token.

### Set-Cookie không tự động cấm cache

Không dựa vào việc response có Set-Cookie để kết luận response sẽ không được cache. Header Set-Cookie tự nó không phải chỉ thị cấm cache. Server phải phát Cache-Control phù hợp với dữ liệu và audience của response.

### Vary không phải cơ chế phân quyền

Vary cho cache biết header request nào ảnh hưởng đến representation:

    Vary: Accept-Encoding

Vary có thể giúp cache phân biệt response theo header, nhưng không thay thế authorization. Không dùng Vary như biện pháp duy nhất để ngăn dữ liệu user A được phục vụ cho user B.

## 4. Chọn policy theo độ nhạy của dữ liệu

### Tài nguyên tĩnh công khai, versioned

Với asset có URL mới ở mỗi lần build và nội dung không thay đổi tại URL cũ:

    Cache-Control: public, max-age=31536000, immutable

Ví dụ:

    /assets/app.8c7f1a2d.js
    /assets/site.4a5d9e10.css

Khi phát hành bản mới, đổi URL hoặc fingerprint. Không ghi đè nội dung tại URL immutable.

### Nội dung công khai cần revalidate

Với danh mục sản phẩm công khai cần cập nhật thường xuyên:

    Cache-Control: public, max-age=60, stale-while-revalidate=30

Đây là ví dụ chính sách cho nội dung công khai; chỉ dùng stale-while-revalidate khi chấp nhận hiển thị bản cũ trong khoảng cho phép.

### Response cá nhân hóa

Với response gắn với tài khoản:

    Cache-Control: private, no-cache

Browser private cache có thể giữ bản response, nhưng phải revalidate trước khi dùng lại. Chỉ chọn cách này nếu dữ liệu được phép tồn tại trong cache riêng và server kiểm tra quyền mỗi lần revalidation.

Nếu nội dung nhạy cảm hoặc không được lưu trên thiết bị:

    Cache-Control: no-store

### Response chứa credential hoặc dữ liệu rất nhạy cảm

Ví dụ response xác thực, thông tin thanh toán hoặc hồ sơ nhạy cảm:

    Cache-Control: no-store

Đồng thời:

- Không ghi response vào Cache API.
- Không lưu bản copy trong localStorage/sessionStorage.
- Không ghi nội dung nhạy cảm vào log hoặc analytics.
- Kiểm tra server authorization mỗi lần request.
- Xóa application memory state khi logout hoặc đổi tài khoản.

Không có một directive duy nhất thay thế phân loại dữ liệu và kiểm soát quyền truy cập.

## 5. Cache API: ứng dụng chủ động lưu response

Cache API khác HTTP cache. Ứng dụng mở cache theo tên và ghi Request/Response:

    const cache = await caches.open("static-shell-v1");
    await cache.put("/offline.html", response.clone());

Đọc lại:

    const cache = await caches.open("static-shell-v1");
    const response = await cache.match("/offline.html");

Liệt kê cache:

    const names = await caches.keys();
    console.log(names);

Xóa cache:

    await caches.delete("static-shell-v1");

### Cache API không tự quản lý freshness như HTTP cache

Cache API không tự áp dụng các HTTP caching directives như HTTP cache của browser. Ứng dụng phải tự quản lý:

- Cache entry nào được ghi.
- Khi nào entry hết hạn.
- Khi nào cần cập nhật.
- Khi nào cần xóa cache cũ.
- Dữ liệu nào không được phép lưu.

Đặc biệt, không dựa vào Cache-Control: no-store để ngăn một service worker tự gọi cache.put(). Hãy thiết kế code service worker chỉ cache allowlist tài nguyên tĩnh và bỏ qua API response nhạy cảm.

### Cache API cũng nằm trong ranh giới origin

CacheStorage thuộc storage của origin. JavaScript chạy cùng origin có thể gọi caches.keys(), mở cache và đọc response mà ứng dụng đã lưu.

Vì vậy, nếu XSS xảy ra, attacker có thể tìm và đọc dữ liệu trong CacheStorage. Việc đặt tên cache khó đoán không phải cơ chế bảo vệ; script cùng origin có thể liệt kê tên cache.

### Cache partitioning và third-party context

Browser hiện đại có thể phân vùng một số loại cache theo top-level site hoặc network partition key để giảm tracking và ngăn website nhúng dùng lại một số cache từ website khác. Chi tiết partitioning khác nhau theo browser, phiên bản và loại cache.

Partitioning không phải cơ chế phân quyền dữ liệu trong ứng dụng:

- Không ngăn JavaScript cùng origin đọc CacheStorage mà origin đó được phép truy cập.
- Không thay authorization ở backend.
- Không bảo đảm dữ liệu cá nhân đã cache sẽ tự biến mất khi người dùng logout.
- Không cho phép ứng dụng giả định third-party iframe luôn có cùng cache state giữa mọi top-level site.

Nếu một iframe bên thứ ba cần dữ liệu, hãy thiết kế API và permission flow rõ ràng; không dựa vào việc cache được chia sẻ giữa các website.

### HTTP cache và Cache API là hai kho khác nhau

- Xóa CacheStorage không tự xóa HTTP cache của browser.
- Header no-store áp dụng cho HTTP caching, không tự ngăn script ghi Cache API.
- Xóa HTTP cache trong DevTools không nhất thiết xóa CacheStorage.
- Xóa CacheStorage không xóa state trong JavaScript memory hoặc BFCache.

Khi xử lý dữ liệu nhạy cảm, cần biết ứng dụng đã ghi dữ liệu vào những lớp nào.

## 6. Service worker: chỉ cache những gì đã được cho phép

Service worker có thể xử lý request và phục vụ response từ CacheStorage. Đây là nền tảng phổ biến cho offline support.

Nguyên tắc an toàn:

1. Chỉ cache GET request.
2. Chỉ cache URL nằm trong allowlist tài nguyên tĩnh.
3. Không cache endpoint API chứa dữ liệu người dùng.
4. Không cache response có thông tin xác thực, thanh toán hoặc dữ liệu riêng tư.
5. Không cache request chỉ vì response status là 200.
6. Đặt tên cache có version và xóa cache cũ có kiểm soát.
7. Không dùng URL hoặc query do người dùng tùy ý cung cấp làm cache key cho dữ liệu nhạy cảm.

### Ví dụ service worker chỉ cache asset tĩnh

    const STATIC_CACHE = "static-shell-v3";

    self.addEventListener("install", (event) => {
      event.waitUntil((async () => {
        const cache = await caches.open(STATIC_CACHE);
        await cache.addAll([
          "/offline.html",
          "/assets/app.8c7f1a2d.js",
          "/assets/site.4a5d9e10.css"
        ]);
      })());
    });

    self.addEventListener("activate", (event) => {
      event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(
          names
            .filter((name) =>
              name.startsWith("static-shell-") &&
              name !== STATIC_CACHE
            )
            .map((name) => caches.delete(name))
        );
        await self.clients.claim();
      })());
    });

    self.addEventListener("fetch", (event) => {
      const request = event.request;
      const url = new URL(request.url);

      if (request.method !== "GET") return;
      if (url.origin !== self.location.origin) return;
      if (!url.pathname.startsWith("/assets/") &&
          url.pathname !== "/offline.html") {
        return;
      }

      event.respondWith((async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(request);
        if (cached) return cached;

        const response = await fetch(request);
        if (response.ok && response.type === "basic") {
          await cache.put(request, response.clone());
        }
        return response;
      })());
    });

Ví dụ này chỉ cache asset trong đường dẫn đã chọn và trang offline. Trong ứng dụng thực, cần bảo đảm không đặt API JSON hoặc file riêng tư trong thư mục allowlist đó.

### Không dùng quy tắc cache-first cho mọi GET

GET không đồng nghĩa với dữ liệu công khai. Một endpoint như /api/account hoặc /api/orders có thể trả dữ liệu cá nhân. Không áp dụng cache-first cho mọi request GET chỉ vì method là GET.

Đối với API:

- Mặc định đi qua network và để server trả Cache-Control phù hợp.
- Dùng no-store cho response nhạy cảm.
- Không ghi response API vào CacheStorage nếu không có yêu cầu offline đã được đánh giá.
- Nếu bắt buộc offline, định nghĩa dữ liệu, user scope, mã hóa, vòng đời và logout cleanup riêng.

## 7. Cache key và nguy cơ lẫn dữ liệu giữa người dùng

Cache key xác định request nào có thể nhận lại response đã lưu. Nếu key không phản ánh các yếu tố làm thay đổi dữ liệu, cache có thể trả sai representation.

Ví dụ hai người dùng cùng gọi:

    GET /api/profile

Nếu response phụ thuộc session cookie nhưng shared cache chỉ phân biệt theo URL, response của user A có nguy cơ được trả cho user B khi cấu hình cache sai.

### Không cache response cá nhân trong shared cache

Với API trả dữ liệu cá nhân, không cấu hình CDN/shared cache để lưu response dùng chung. Dùng policy phù hợp như:

    Cache-Control: private, no-store

Nếu dữ liệu được phép lưu trong browser private cache và cần revalidation, có thể cân nhắc private, no-cache sau khi đánh giá.

### Cache API và key theo user

CacheStorage do ứng dụng quản lý, nên ứng dụng có thể đặt tên cache theo tài khoản:

    account-cache-user-123

Điều này có thể hỗ trợ cleanup và phân tách logic, nhưng tên cache không phải ranh giới bảo mật. Script cùng origin vẫn có thể liệt kê và đọc cache. Không dựa vào user ID trong cache name để authorization.

Nếu buộc phải cache dữ liệu offline theo user:

- Không lưu credential hoặc token trong cache.
- Chỉ lưu trường dữ liệu tối thiểu.
- Xác minh user/session trước khi hiển thị dữ liệu sau khi mở app.
- Xóa cache user-scoped khi logout hoặc đổi tài khoản.
- Không cho response của user trước xuất hiện trước khi xác minh session mới.
- Cân nhắc mã hóa dữ liệu offline với khóa không thể lấy chỉ từ JavaScript của cùng origin; lưu ý XSS đang hoạt động vẫn có thể đọc dữ liệu sau giải mã.

### Vary và cache key không thay thế authorization

Vary có thể yêu cầu HTTP cache phân biệt response theo một số request header. Tuy nhiên, shared cache và CDN có nhiều quy tắc riêng; sai cấu hình cache key vẫn có thể làm rò rỉ dữ liệu.

Không dùng Vary: Cookie như biện pháp duy nhất để bảo vệ dữ liệu tài khoản. Tốt hơn là không cache response nhạy cảm trong shared cache.

### Cache poisoning

Cache poisoning xảy ra khi attacker khiến cache lưu một response sai hoặc độc hại rồi response đó được phục vụ cho request khác. Nguyên nhân có thể là cache key bỏ sót header/query ảnh hưởng nội dung, proxy xử lý Host hoặc forwarded header không nhất quán, hay ứng dụng phản chiếu input không an toàn vào response có thể cache.

Biện pháp giảm rủi ro:

- Xác định chính xác yếu tố nào làm thay đổi response và cấu hình cache key tương ứng.
- Không cache response có nội dung phụ thuộc cookie, Authorization hoặc dữ liệu tenant trong shared cache nếu chưa có thiết kế phân tách đã kiểm chứng.
- Không phản chiếu Host, X-Forwarded-Host hoặc input tùy ý vào nội dung cacheable.
- Giới hạn query parameter được phép ảnh hưởng representation.
- Kiểm tra cache behavior qua CDN/proxy với nhiều user, tenant và header khác nhau.
- Purge cache khi phát hiện response độc hại, sau khi đã sửa nguyên nhân gốc.

## 8. XSS và cache chứa dữ liệu

XSS cho phép attacker thực thi JavaScript trong origin của ứng dụng. Khi đó, attacker có thể truy cập các API storage mà trang có quyền:

- Đọc localStorage/sessionStorage.
- Đọc CacheStorage qua caches.open() và cache.match().
- Gọi API mà trang có thể gọi.
- Đọc dữ liệu đang hiển thị trong DOM.
- Sửa hoặc xóa cache để gây sai lệch trạng thái/offline.

HTTP cache của browser không có API JavaScript tổng quát để liệt kê mọi response đã lưu, nhưng XSS vẫn có thể gọi lại URL cùng origin và khai thác dữ liệu mà ứng dụng trả về hoặc đang hiển thị. Với Cache API, quyền đọc trực tiếp của script cùng origin rõ ràng hơn.

### Không coi cache là nơi bí mật

Cache chủ yếu tối ưu hiệu năng và offline. Không dùng nó làm kho lưu credential hoặc dữ liệu cần bảo mật khỏi JavaScript cùng origin.

Mã hóa response trước khi ghi cache có thể hữu ích trong một số thiết kế offline, nhưng nếu JavaScript cùng origin có thể lấy khóa và giải mã, XSS đang hoạt động vẫn có thể lấy plaintext. Mã hóa không thay thế phòng XSS và quản lý khóa.

### Phòng XSS để bảo vệ cache

- Dùng output encoding theo đúng HTML/attribute/URL/JavaScript context.
- Tránh innerHTML với dữ liệu không tin cậy; ưu tiên textContent.
- Dùng CSP nonce/hash và loại bỏ unsafe-inline khi có thể.
- Dùng Trusted Types để kiểm soát các DOM sink phù hợp.
- Giảm script bên thứ ba và pin dependency.
- Validate dữ liệu trước khi render.
- Không đặt token hoặc bí mật vào CacheStorage, localStorage hay sessionStorage.

## 9. Logout, đổi tài khoản và invalidation

Logout là thời điểm quan trọng vì dữ liệu có thể còn trong nhiều lớp cache.

### Các bước khi logout

1. Kết thúc/revoke session ở backend.
2. Xóa state người dùng trong memory và query cache của ứng dụng.
3. Gửi yêu cầu cho service worker xóa cache chứa dữ liệu user nếu ứng dụng có lưu loại dữ liệu đó.
4. Xóa các key user-scoped trong localStorage/sessionStorage nếu có.
5. Thông báo các tab khác để chúng cập nhật giao diện và session state.
6. Chuyển về trang public/login và không hiển thị dữ liệu cũ trước khi xác minh session mới.

Xóa CacheStorage:

    async function deleteUserCaches() {
      const names = await caches.keys();
      const userCaches = names.filter((name) =>
        name.startsWith("user-data-")
      );

      await Promise.all(
        userCaches.map((name) => caches.delete(name))
      );
    }

Chỉ xóa cache do ứng dụng sở hữu. Không xóa toàn bộ CacheStorage nếu ứng dụng có cache static shell cần giữ lại.

### CacheStorage và service worker đang điều khiển nhiều tab

Nếu page cần yêu cầu service worker cleanup, có thể dùng postMessage:

    navigator.serviceWorker.controller?.postMessage({
      type: "CLEAR_USER_CACHE"
    });

Service worker cần kiểm tra message type và chỉ xóa namespace cache đã định nghĩa. Không để message tùy ý chọn cache name hoặc đường dẫn để xóa/đọc.

### Logout ở một tab, các tab khác thì sao?

Có thể dùng BroadcastChannel hoặc storage event để thông báo:

    const channel = new BroadcastChannel("auth-state");

    channel.postMessage({ type: "logout" });

Tab nhận cần:

1. Xóa user state trong memory.
2. Xóa cache user-scoped theo quy ước.
3. Điều hướng về login hoặc trạng thái public.
4. Kiểm tra session với backend trước khi hiển thị dữ liệu.

Thông báo giữa các tab không thay thế revoke session ở backend. Một tab có thể đang offline hoặc không nhận được event.

### Invalidation HTTP cache

JavaScript không có API chuẩn để xóa tùy ý mọi entry trong HTTP cache của browser. Vì vậy, cách phòng ngừa chính là đặt Cache-Control đúng ngay khi server phát response.

Khi nội dung cần thay đổi, dùng URL versioned, validator hoặc revalidation. Không dựa vào việc logout sẽ xóa hết HTTP cache.

## 10. BFCache: trang nhạy cảm có thể được khôi phục

BFCache giữ snapshot của trang để thao tác Back/Forward nhanh. Người dùng có thể quay lại một trang account và thấy DOM/trạng thái trước đó được khôi phục.

Đây là cơ chế khác với HTTP cache:

- HTTP cache lưu response.
- CacheStorage lưu Request/Response do ứng dụng ghi.
- BFCache giữ snapshot document và trạng thái trang.

Lắng nghe pageshow:

    const sensitiveArea = document.querySelector("#sensitive-content");

    window.addEventListener("pagehide", () => {
      sensitiveArea?.setAttribute("hidden", "");
    });

    window.addEventListener("pageshow", async (event) => {
      if (!event.persisted) return;

      try {
        const session = await fetch("/api/session", {
          credentials: "same-origin",
          cache: "no-store"
        });

        if (!session.ok) {
          clearSensitiveUiState();
          location.replace("/login");
          return;
        }

        await refreshSensitiveData();
        sensitiveArea?.removeAttribute("hidden");
      } catch {
        clearSensitiveUiState();
        location.replace("/login");
      }
    });

Ví dụ này minh họa việc revalidate session khi trang được khôi phục từ BFCache. Endpoint session cần trả response no-store và kiểm tra session ở server. Trong ứng dụng thực, có thể tạm ẩn vùng nhạy cảm cho tới khi xác minh xong.

Không dùng unload event để cố xóa BFCache; unload có thể ảnh hưởng đến khả năng BFCache và không phải cơ chế bảo đảm xóa dữ liệu.

Hành vi BFCache khác nhau theo browser và có thể thay đổi. Không giả định Cache-Control no-store luôn vô hiệu hóa BFCache trên mọi phiên bản. Hãy kiểm thử browser mục tiêu và revalidate trạng thái khi trang được khôi phục.

## 11. Kiểm thử cache bằng Chrome DevTools

Thực hiện trên local/staging với tài khoản và dữ liệu giả. Không dùng hồ sơ hoặc response thật của người dùng.

### Bước 1 — Kiểm tra HTTP cache

1. Mở DevTools → Network.
2. Tải một asset public versioned.
3. Chọn request và xem Response Headers.
4. Kiểm tra Cache-Control, ETag, Last-Modified, Age và Vary nếu có.
5. Reload để quan sát memory/disk cache hoặc revalidation.

Khi bật Disable cache trong DevTools, browser có thể bỏ qua HTTP cache trong lúc DevTools đang mở. Tắt tùy chọn này để kiểm tra hành vi bình thường.

### Bước 2 — Kiểm tra response nhạy cảm

1. Gọi endpoint profile test.
2. Kiểm tra response header có Cache-Control: no-store.
3. Reload và xem request có đi tới server hay không.
4. Kiểm tra CDN/proxy có ghi cache hay không nếu kiến trúc có shared cache.

Không chỉ dựa vào việc Network panel hiển thị một request; xác minh cả response headers và cấu hình proxy/CDN.

### Bước 3 — Kiểm tra CacheStorage

1. DevTools → Application → Cache Storage.
2. Mở từng cache name.
3. Xem request URL và response đã lưu.
4. Xác định có API path hoặc dữ liệu cá nhân nào bị ghi nhầm không.
5. Xóa cache test và tải lại để kiểm tra service worker có tạo lại đúng asset allowlist hay không.

### Bước 4 — Kiểm tra service worker

1. Application → Service Workers.
2. Xác định worker đang điều khiển trang.
3. Kiểm tra version worker và cache names.
4. Update worker trong staging.
5. Xác nhận activate cleanup chỉ xóa cache version cũ thuộc namespace ứng dụng.

### Bước 5 — Kiểm tra logout

1. Đăng nhập bằng user test A.
2. Mở trang account và quan sát cache.
3. Logout.
4. Kiểm tra CacheStorage và memory state đã được dọn theo thiết kế.
5. Đăng nhập user test B trong cùng browser profile.
6. Xác nhận dữ liệu của A không xuất hiện trước khi server trả dữ liệu của B.

### Bước 6 — Kiểm tra BFCache

1. Mở trang account trong staging.
2. Điều hướng sang trang khác.
3. Bấm Back.
4. Quan sát pageshow và event.persisted.
5. Xác nhận session được kiểm tra lại trước khi hiển thị nội dung nhạy cảm.

### Ma trận kiểm thử

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Asset public versioned | public, max-age dài, immutable | Browser cache asset |
| Response nhạy cảm | no-store | HTTP cache không lưu response theo policy |
| Response private | private | Shared cache không lưu; browser private cache có thể lưu |
| Response no-cache | no-cache + validator | Cache revalidate trước khi reuse |
| Cache API ghi asset | Service worker allowlist static | Chỉ asset được phép xuất hiện trong CacheStorage |
| Cache API nhận API path | API không nằm trong allowlist | Không được ghi vào CacheStorage |
| no-store với cache.put | Code thử ghi chủ động | Cache API vẫn có thể lưu nếu ứng dụng gọi; phải chặn bằng logic |
| Logout | User-scoped cache tồn tại | Cache user bị xóa và server session kết thúc |
| Đổi user | User A logout, B login | Không hiển thị dữ liệu A cho B |
| XSS lab | Script cùng origin | Có thể đọc CacheStorage; chứng minh không coi cache là bí mật |
| BFCache restore | Trang được khôi phục bằng Back | Session/quyền được revalidate |
| Cache version update | Worker v3 thay v2 | Chỉ cache cũ trong namespace được quản lý bị xóa |

## 12. Xử lý sự cố cache chứa dữ liệu sai hoặc nhạy cảm

Khi phát hiện cache chứa dữ liệu không nên lưu:

1. Xác định loại cache: HTTP cache, shared CDN/proxy, CacheStorage, memory cache hay BFCache.
2. Xác định URL, response, user/tenant, thời gian và browser bị ảnh hưởng.
3. Dừng logic ghi cache mới cho endpoint/dữ liệu đó.
4. Phát Cache-Control phù hợp ở server; với dữ liệu nhạy cảm thường dùng no-store.
5. Nếu dữ liệu nằm trong CacheStorage, phát service worker update để xóa đúng cache namespace và entry liên quan.
6. Purge shared CDN/proxy cache theo quy trình nhà cung cấp nếu response đã bị lưu ở đó.
7. Kết thúc/revoke session hoặc credential nếu dữ liệu bị lộ có thể dùng để xác thực.
8. Kiểm tra logout, account switching, cache key và service worker fetch handler.
9. Kiểm tra log, telemetry và phạm vi người dùng/tenant có thể đã nhận response sai.
10. Thêm regression test để endpoint nhạy cảm không bị cache trong tương lai.

Không tuyên bố dữ liệu đã bị xóa an toàn khỏi thiết bị chỉ vì CacheStorage.delete() trả true. Browser, hệ điều hành, backup, disk snapshot và shared cache có vòng đời riêng; ứng dụng web không có bảo đảm secure erasure tổng quát.

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ mọi cache chỉ chứa file tĩnh | API response và dữ liệu cá nhân có thể bị lưu | Inventory từng lớp cache và endpoint |
| Dùng private thay no-store cho dữ liệu nhạy cảm | Browser private cache vẫn có thể lưu | Dùng no-store khi không được lưu |
| Nghĩ no-cache có nghĩa không lưu | Response vẫn có thể nằm trong cache | Hiểu no-cache là phải revalidate |
| Nghĩ Set-Cookie tự cấm cache | Response có thể vẫn được cache theo policy khác | Phát Cache-Control rõ ràng |
| Nghĩ no-store ngăn Cache API | Service worker vẫn có thể gọi cache.put | Chặn bằng logic allowlist trong worker |
| Cache mọi GET response | API cá nhân có thể bị lưu offline | Chỉ cache path asset tĩnh đã xác định |
| Dùng URL làm cache key cho dữ liệu user | Hai user có thể nhận nhầm response | Không cache dữ liệu cá nhân hoặc thiết kế user scope và cleanup |
| Dùng Vary: Cookie như authorization | Shared cache vẫn có thể cấu hình sai | Không cache response nhạy cảm trong shared cache |
| Chỉ xóa CacheStorage khi logout | HTTP cache, memory hoặc BFCache vẫn còn state | Thiết kế cleanup theo từng loại cache và revalidate |
| Nghĩ max-age=0 xóa mọi cache cũ | Không xóa CacheStorage hoặc mọi bản đã lưu | Dùng invalidation đúng cơ chế |
| Nghĩ BFCache là HTTP cache | Không xử lý trang được restore | Dùng pageshow và kiểm tra session |
| Ghi đè URL immutable | Browser có thể tiếp tục dùng bytes cũ | Phát URL mới có fingerprint |
| Nghĩ xóa cache là secure erase | Không bảo đảm xóa vật lý mọi bản sao | Giảm lưu dữ liệu ngay từ đầu và revoke quyền |

## 14. Câu hỏi củng cố

**Câu 1.** HTTP cache và Cache API khác nhau thế nào?

**Giải đáp:** HTTP cache do browser/cache trung gian quản lý theo HTTP caching directives. Cache API do JavaScript/service worker chủ động ghi, đọc và xóa Request/Response.

**Câu 2.** Cache-Control: private có nghĩa browser không lưu dữ liệu không?

**Giải đáp:** Không. private ngăn shared cache lưu response, nhưng private cache của browser vẫn có thể lưu.

**Câu 3.** no-cache có giống no-store không?

**Giải đáp:** Không. no-cache cho phép lưu nhưng yêu cầu revalidate trước khi reuse; no-store yêu cầu HTTP cache không lưu response.

**Câu 4.** Response có no-store có thể được service worker ghi vào CacheStorage không?

**Giải đáp:** Có, nếu code chủ động gọi Cache API. Cache API không tự thực thi HTTP caching directives; service worker phải tự loại response nhạy cảm khỏi cache.

**Câu 5.** Vì sao không cache mọi GET request?

**Giải đáp:** GET có thể trả dữ liệu cá nhân như profile hoặc đơn hàng. Method GET không chứng minh response là công khai.

**Câu 6.** Logout có xóa được mọi browser cache bằng JavaScript không?

**Giải đáp:** Không. Ứng dụng có thể xóa CacheStorage và state do mình quản lý, nhưng không có API chuẩn để xóa tùy ý toàn bộ HTTP cache hoặc BFCache. Cần đặt policy đúng từ đầu và kết thúc session ở server.

**Câu 7.** BFCache có giống CacheStorage không?

**Giải đáp:** Không. BFCache giữ snapshot document để back/forward; CacheStorage giữ Request/Response do ứng dụng ghi.

**Câu 8.** Vì sao XSS có thể đọc CacheStorage?

**Giải đáp:** CacheStorage thuộc storage của origin. Script chạy cùng origin có thể dùng Cache API để liệt kê và đọc cache mà ứng dụng có quyền truy cập.

## 15. Tổng kết

Cache có thể chứa HTML, asset công khai, API response, dữ liệu cá nhân hoặc snapshot trạng thái trang. Cần phân biệt HTTP cache, Cache API/CacheStorage, application memory cache và BFCache vì mỗi loại có chủ thể quản lý, vòng đời và cơ chế xóa khác nhau.

Với HTTP response nhạy cảm, dùng Cache-Control: no-store và kiểm tra cả shared cache. private vẫn cho phép browser private cache lưu; no-cache cho phép lưu nhưng buộc revalidate. Cache API không tự tuân theo HTTP caching directives, nên service worker phải dùng allowlist tài nguyên tĩnh và tuyệt đối không cache API response nhạy cảm theo quy tắc chung.

Khi logout hoặc đổi tài khoản, kết thúc session ở server, xóa application state và CacheStorage do ứng dụng sở hữu, đồng bộ các tab và xác minh session trước khi hiển thị dữ liệu. XSS cùng origin có thể đọc CacheStorage; vì vậy cache không phải kho bí mật. Hãy giảm dữ liệu lưu, giới hạn cache key, bảo vệ service worker và kiểm thử từng lớp cache bằng DevTools.

## Tài liệu tham khảo

1. [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): quy tắc HTTP cache, freshness, validation và Cache-Control.
2. [MDN — HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): browser cache, Cache-Control, revalidation và best practices.
3. [MDN — Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache): Cache API và thao tác Request/Response.
4. [MDN — CacheStorage](https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage): quản lý các named cache.
5. [MDN — Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API): service worker lifecycle và offline caching.
6. [MDN — Back/forward cache](https://developer.mozilla.org/en-US/docs/Glossary/bfcache): snapshot trang và hành vi điều hướng.
7. [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): lưu trữ phía client và rủi ro dữ liệu nhạy cảm.
