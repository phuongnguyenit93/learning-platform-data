# Cache Storage — lưu cache ứng dụng và hiểu ranh giới riêng tư

> **Chương:** Storage  
> **Mục tiêu:** Hiểu Cache Storage API và cách lưu cặp Request/Response cho ứng dụng web; phân biệt Cache Storage với HTTP cache; quản lý cache trong Service Worker; hiểu origin scope và storage partitioning theo top-level site trong third-party context; tránh dùng cache làm kho bí mật hoặc công cụ theo dõi; kiểm tra quota, eviction và hành vi thực tế trên browser.

## 1. Cache Storage là gì?

**Cache Storage API** là API cho phép JavaScript lưu và tra cứu các cặp Request/Response có tên cache. Ứng dụng có thể chủ động quyết định tài nguyên nào được lưu, lúc nào cập nhật và khi nào xóa.

Cache Storage thường được dùng với Service Worker để:

- Phục vụ app shell và tài nguyên tĩnh khi offline.
- Giảm số lần tải lại CSS, JavaScript, font hoặc ảnh.
- Xây dựng chiến lược cache như cache-first hoặc network-first.
- Cung cấp trang offline khi mạng không khả dụng.

Cache Storage không bắt buộc phải dùng cùng Service Worker. API có thể được truy cập từ Window và worker trong secure context. Tuy nhiên, Service Worker là nơi phổ biến để kiểm soát request mạng và quyết định trả response từ cache hay network.

Ví dụ mở một cache:

```js
const cache = await caches.open("app-assets-v1");
```

Tên cache là chuỗi do ứng dụng quản lý. Một origin có thể có nhiều cache có tên khác nhau.

## 2. Cache Storage khác HTTP cache như thế nào?

Hai cơ chế đều lưu response, nhưng quyền điều khiển khác nhau:

| Đặc điểm | HTTP cache | Cache Storage API |
| --- | --- | --- |
| Ai quản lý? | Browser và HTTP caching rules | Code ứng dụng/Service Worker |
| Cách lưu | Theo request, response và freshness policy | Gọi rõ `cache.put()`, `add()`, `addAll()` |
| Cách tìm | Browser tự quyết định khi request mạng | Code gọi `match()` hoặc `caches.match()` |
| Hết hạn | Theo Cache-Control, Expires, validator và browser policy | Không tự hết hạn theo tuổi; ứng dụng phải cập nhật/xóa |
| Offline strategy | Browser có thể dùng cache theo HTTP rules | Ứng dụng có thể chủ động trả response đã lưu |
| Xóa | Browser settings hoặc HTTP cache management | `cache.delete()`, `caches.delete()` |

**Cache Storage API không tự tuân theo HTTP caching headers.** Nếu code gọi `cache.put()`, response có thể được lưu ngay cả khi server gửi `Cache-Control: no-store`. Vì vậy, Service Worker phải chủ động bỏ qua endpoint nhạy cảm và không ghi response đó vào Cache Storage.

HTTP cache và Cache Storage cũng là hai kho riêng. Xóa cache do Service Worker quản lý không đồng nghĩa xóa toàn bộ HTTP cache của browser.

## 3. CacheStorage, Cache và Request/Response

Mô hình API gồm ba thành phần:

- `CacheStorage`: danh mục các cache có tên, truy cập qua global `caches`.
- `Cache`: một tập các cặp Request/Response.
- `Request` và `Response`: khóa và giá trị được lưu.

Các thao tác thường dùng:

| API | Tác dụng |
| --- | --- |
| `caches.open(name)` | Mở hoặc tạo cache có tên |
| `caches.keys()` | Liệt kê tên cache |
| `caches.delete(name)` | Xóa toàn bộ cache theo tên |
| `caches.match(request)` | Tìm request trong các cache được quản lý |
| `cache.match(request)` | Tìm response trong một cache cụ thể |
| `cache.add(url)` | Fetch URL rồi lưu response |
| `cache.addAll(urls)` | Fetch và lưu nhiều URL |
| `cache.put(request, response)` | Lưu một cặp Request/Response |
| `cache.delete(request)` | Xóa entry khớp request |
| `cache.keys()` | Liệt kê request key trong cache |

Ví dụ lưu và đọc một tài nguyên công khai cùng origin:

```js
async function cachePublicGuide() {
  const cache = await caches.open("public-guides-v1");
  const request = new Request("/guides/offline-basics.json");
  const response = await fetch(request);

  if (!response.ok || response.type !== "basic") {
    throw new Error("Response không phù hợp để cache");
  }

  await cache.put(request, response.clone());
}

async function readPublicGuide() {
  const cache = await caches.open("public-guides-v1");
  return cache.match("/guides/offline-basics.json");
}
```

Response body là stream có thể bị tiêu thụ. Hãy dùng `response.clone()` khi cần vừa trả response cho caller vừa lưu một bản vào cache.

## 4. Cache Storage có ranh giới origin

Same-Origin Policy tiếp tục áp dụng cho Cache Storage. Một document chỉ truy cập CacheStorage trong storage context của chính nó; website khác origin không thể mở cache của origin này bằng cách đoán tên cache.

Với URL HTTP(S), origin gồm:

- Scheme, ví dụ `https`.
- Host, ví dụ `app.example.com`.
- Port, ví dụ `443` hoặc `8443`.

Ví dụ:

| Document | Quan hệ | CacheStorage |
| --- | --- | --- |
| `https://app.example.com` | Cùng origin với chính nó | Dùng storage context của app |
| `https://app.example.com/settings` | Cùng origin, khác path | Dùng cùng origin storage context |
| `https://static.example.com` | Khác host | Không đọc trực tiếp cache của app |
| `http://app.example.com` | Khác scheme | Không đọc cache HTTPS của app |
| `https://app.example.com:8443` | Khác port | Không đọc cache ở port mặc định |

Cache name không tạo ra một ranh giới bảo mật mới. Mọi script chạy trong cùng origin context có thể truy cập các cache mà origin đó được phép truy cập, bất kể tên cache do module nào tạo.

## 5. Cache Storage chỉ dành cho Service Worker?

Không. `caches` có thể được dùng từ:

- Window của trang web.
- Service Worker.
- Một số worker context được browser hỗ trợ.

Ví dụ từ trang:

```js
const names = await caches.keys();
console.log(names);
```

Ví dụ từ Service Worker:

```js
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("app-shell-v1").then((cache) =>
      cache.addAll(["/", "/offline.html", "/assets/app.css"])
    )
  );
});
```

API được định nghĩa trong Service Worker specification, nhưng không có nghĩa chỉ Service Worker mới có thể dùng nó. Dù truy cập từ Window hay worker, dữ liệu vẫn chịu ranh giới origin và storage partitioning của browser.

## 6. Storage partitioning là gì?

Trước đây, nhiều dạng state phía client thường được khóa chủ yếu theo origin của resource. Nếu cùng một bên thứ ba được nhúng trên nhiều website, nó có thể lưu một định danh ở storage của chính nó rồi đọc lại khi xuất hiện trên website khác.

**Storage partitioning** bổ sung ngữ cảnh top-level site vào khóa lưu trữ trong third-party context. Nhờ vậy, cùng một origin được nhúng dưới hai website khác nhau có thể nhận hai vùng storage riêng.

Ví dụ:

- Người dùng mở `https://news.example`, trang này nhúng `https://widget.partner.test`.
- Người dùng mở `https://shop.example`, trang này cũng nhúng `https://widget.partner.test`.
- Trong browser có partitioning, storage của widget trong ngữ cảnh news có thể tách khỏi storage của widget trong ngữ cảnh shop.

Mục tiêu là hạn chế việc bên thứ ba nối dữ liệu giữa các website để theo dõi người dùng hoặc suy luận trạng thái đăng nhập.

## 7. Storage key trong first-party và third-party context

Hãy hình dung một storage key có thể bao gồm origin của resource và top-level site:

```text
First-party:
  top-level site = app.example
  resource origin = app.example

Third-party trên site A:
  top-level site = news.example
  resource origin = widget.partner.test

Third-party trên site B:
  top-level site = shop.example
  resource origin = widget.partner.test
```

Hai ngữ cảnh third-party có cùng resource origin nhưng top-level site khác nhau. Browser có thể đặt chúng vào hai partition khác nhau.

Đây là mô hình khái niệm, không phải cam kết rằng mọi browser dùng chính xác cùng một cấu trúc key. Một số implementation còn xét chuỗi ancestor hoặc trạng thái cross-site của các frame lồng nhau. Không viết ứng dụng dựa trên giả định rằng một origin luôn có duy nhất một CacheStorage dùng chung ở mọi ngữ cảnh.

## 8. Cache Storage trong iframe bên thứ ba

Giả sử `widget.partner.test` được nhúng bằng iframe:

```html
<iframe
  src="https://widget.partner.test/embed"
  title="Widget đối tác"
></iframe>
```

Code bên trong iframe chạy dưới origin của widget. Khi gọi:

```js
const cache = await caches.open("widget-cache-v1");
```

nó thao tác trên CacheStorage của widget trong storage context mà browser cấp cho iframe. Trong browser có third-party storage partitioning, context đó có thể được phân vùng theo top-level site.

Vì vậy:

- Widget được nhúng trên site A không nên giả định thấy cache đã tạo khi nó được nhúng trên site B.
- Widget không nên dựa vào CacheStorage để nhận diện người dùng xuyên website.
- Dữ liệu cache ở iframe không phải kho dùng chung với cache của trang cha.
- Việc phân vùng storage không cấp quyền cho iframe đọc DOM, cache hoặc dữ liệu của parent.

## 9. Script bên thứ ba và iframe bên thứ ba khác nhau

Hai cách tích hợp thường bị nhầm:

### Tải script bằng thẻ script

```html
<script src="https://widget.partner.test/widget.js"></script>
```

Script này chạy trong browsing context của document nhúng. Nó có quyền JavaScript theo origin của trang chủ, không có một origin riêng như iframe. Nếu gọi `caches.open()`, nó truy cập CacheStorage của trang chủ.

Điều này có nghĩa một script bên thứ ba được nhúng trực tiếp có thể đọc hoặc sửa dữ liệu same-origin mà trang chủ có quyền truy cập. Chỉ tin cậy script từ nguồn có lý do rõ ràng và kiểm soát phiên bản/integrity.

### Nhúng bằng iframe

```html
<iframe src="https://widget.partner.test/embed"></iframe>
```

Document iframe chạy theo origin của widget. Nó bị giới hạn bởi SOP và storage policy riêng của browser; storage có thể được partition theo top-level site.

| Cách tích hợp | Origin của code | CacheStorage được truy cập |
| --- | --- | --- |
| `<script src>` | Origin của trang nhúng | CacheStorage của trang nhúng |
| `<iframe src>` | Origin của iframe | CacheStorage của iframe trong partition hiện hành |

Đây là khác biệt quan trọng khi đánh giá quyền của SDK, analytics, quảng cáo hoặc widget đối tác.

## 10. Storage partitioning và privacy boundary

Partitioning giúp giảm khả năng dùng shared state để liên kết hoạt động của người dùng trên nhiều top-level site. Nếu bên thứ ba không thể đọc cùng một cache state ở hai website, nó khó dùng CacheStorage như một định danh xuyên site.

Partitioning cũng có thể làm thay đổi hành vi tích hợp hợp lệ:

- Widget không còn thấy dữ liệu đã lưu khi người dùng truy cập nó trực tiếp ở first-party context.
- Service Worker/cache của third-party embed có thể tách theo website nhúng.
- Một số luồng đăng nhập liên kết hoặc personalization cũ có thể cần thiết kế lại.
- Cache được tạo trong iframe của site A không nhất thiết được tái sử dụng trong iframe của site B.

Partitioning không thay thế SOP. Nó chia nhỏ vùng state mà cùng một origin có thể dùng trong các ngữ cảnh khác nhau; nó không cho phép một origin đọc storage của origin khác.

## 11. Khác biệt giữa browser và nested iframe

Các browser triển khai storage partitioning theo chính sách và phiên bản riêng. Ví dụ, Firefox mô tả việc partition các storage API theo top-level site; Chrome có partitioning cho storage và communication APIs trong third-party context; WebKit cũng partition third-party storage và Service Worker cache.

Một số implementation còn xét chuỗi ancestor. Ví dụ, nếu site A nhúng site B rồi B nhúng lại A, browser không nhất thiết xem iframe A lồng bên trong là first-party chỉ vì nó cùng site với top-level A. Một cờ ancestor hoặc thành phần tương tự có thể được dùng để giữ ranh giới privacy.

Vì vậy:

- Không hardcode giả định về số partition hoặc tên partition.
- Không dùng kết quả của một browser để kết luận mọi browser giống nhau.
- Kiểm thử top-level, iframe trực tiếp và nested iframe.
- Theo dõi thay đổi browser policy khi cập nhật phiên bản.

## 12. Storage Access API không phải cách đọc cache của origin khác

Third-party iframe có thể cần truy cập unpartitioned state cho một use case hợp lệ, ví dụ đăng nhập liên kết. Storage Access API cung cấp:

- `document.hasStorageAccess()`: kiểm tra context đã có storage access hay chưa.
- `document.requestStorageAccess()`: yêu cầu browser cấp quyền truy cập state không partition trong những điều kiện được hỗ trợ.

Ví dụ tối giản:

```js
async function requestEmbeddedStorageAccess() {
  if (!document.hasStorageAccess || !document.requestStorageAccess) {
    return { supported: false, granted: false };
  }

  if (await document.hasStorageAccess()) {
    return { supported: true, granted: true };
  }

  try {
    // Gọi từ thao tác rõ ràng của người dùng khi browser yêu cầu.
    await document.requestStorageAccess();
    return { supported: true, granted: true };
  } catch {
    return { supported: true, granted: false };
  }
}
```

Storage Access API có điều kiện và khác biệt giữa browser; một số luồng cần transient user activation hoặc quyền đã được cấp trước đó. Không gọi tự động khi trang vừa tải.

API này không phá SOP và không cho iframe đọc CacheStorage của parent hoặc origin khác. Mục đích của nó là xử lý một số trường hợp cần unpartitioned third-party state; không dùng nó như cơ chế đồng bộ cache xuyên website. Nếu widget cần dữ liệu, thiết kế API server hoặc giao thức message có kiểm tra origin và quyền phù hợp.

## 13. Partitioned cookies và Cache Storage là hai cơ chế khác nhau

Cookie có thể được partition theo top-level site, ví dụ cơ chế CHIPS với thuộc tính `Partitioned`. Đây là chính sách dành cho cookie.

Cache Storage là kho Request/Response của Cache API. Nó không phải cookie jar và không dùng thuộc tính `Partitioned` để điều khiển cache.

| Cơ chế | Dữ liệu | Mục tiêu |
| --- | --- | --- |
| Partitioned cookie | Cookie gửi qua HTTP và truy cập theo cookie rules | Cho phép cookie của embed có vùng riêng theo top-level site |
| Cache Storage partitioning | Request/Response trong Cache API | Ngăn cache state của third-party embed bị dùng để nối hoạt động giữa site |
| Storage Access API | Quyền truy cập unpartitioned third-party state | Hỗ trợ một số tích hợp cần state first-party trong embed |

Không giả định bật CHIPS sẽ làm CacheStorage được chia sẻ hoặc đồng bộ. Mỗi API có quy tắc storage riêng.

## 14. Cache key và quy tắc match

Cache API tìm entry dựa trên Request và các tùy chọn matching. Theo mặc định, việc match xét URL, method và header `Vary` theo quy tắc của API.

Các tùy chọn có thể ảnh hưởng kết quả:

- `ignoreSearch`: bỏ qua query string khi match.
- `ignoreMethod`: bỏ qua khác biệt method.
- `ignoreVary`: bỏ qua header Vary.

Ví dụ:

```js
const cache = await caches.open("public-pages-v1");

const exact = await cache.match("/docs/page.html");
const byPathOnly = await cache.match("/docs/page.html?lang=vi", {
  ignoreSearch: true,
});
```

Chỉ dùng `ignoreSearch: true` khi query string chắc chắn không làm thay đổi nội dung. Nếu query chứa locale, phiên bản, tenant, bộ lọc hoặc định danh người dùng, bỏ qua query có thể trả nhầm response.

Không dùng `ignoreVary: true` tùy tiện. Server có thể trả nội dung khác theo `Accept-Language`, `Accept` hoặc header khác. Bỏ qua Vary có thể làm cache trả sai representation.

## 15. Không dùng cache name làm ranh giới bảo mật

Tên cache chỉ giúp ứng dụng tổ chức dữ liệu:

```js
await caches.open("public-assets-v2");
await caches.open("account-data-v1");
```

Hai tên khác nhau không tạo hai sandbox. Script cùng origin có thể gọi `caches.keys()`, mở cache theo tên và đọc/xóa entry nếu được browser cho phép trong context đó.

Không lưu bí mật vào cache với suy nghĩ rằng chỉ module biết tên cache mới đọc được. Không dùng cache name làm access control hoặc thay authorization.

Nếu ứng dụng cần phân tách dữ liệu theo user, tenant hoặc workspace, hãy thực hiện authorization ở server và tránh lưu response nhạy cảm trong Cache Storage. Việc đổi tên cache theo user không tự tạo ranh giới bảo mật.

## 16. Rủi ro XSS và cache poisoning

JavaScript chạy cùng origin có thể truy cập CacheStorage của origin đó. Nếu attacker đạt được DOM XSS hoặc thực thi script không tin cậy trong origin, họ có thể:

- Đọc response đã cache và trích xuất dữ liệu nhạy cảm.
- Ghi response giả vào cache để thay nội dung lần truy cập sau.
- Xóa cache hoặc làm ứng dụng mất khả năng hoạt động offline.
- Ghi đè tài nguyên tĩnh nếu Service Worker chấp nhận request không được kiểm soát.
- Duy trì nội dung độc hại sau khi nguồn tấn công ban đầu đã biến mất.

Cache Storage không tự xác minh nội dung có đáng tin hay không. Ứng dụng phải kiểm soát nguồn request, loại response, route được phép cache và quy trình cập nhật.

Biện pháp:

- Chỉ cache tài nguyên đã xác định rõ.
- Kiểm tra origin, method, status và loại response trước khi lưu.
- Không cache response do message hoặc input người dùng tùy ý chỉ định.
- Dùng CSP, output encoding và Trusted Types để giảm nguy cơ script injection.
- Dùng SRI cho script tĩnh từ CDN khi phù hợp; Cache API không thay SRI.
- Quản lý Service Worker script và quá trình deploy như code có đặc quyền.

## 17. Không lưu dữ liệu nhạy cảm vào Cache Storage

Tránh cache:

- Access token, refresh token hoặc session secret.
- Trang tài khoản, hóa đơn, lịch sử giao dịch hoặc response cá nhân hóa.
- API response phụ thuộc cookie/session nhưng cache key không phân biệt người dùng.
- Dữ liệu y tế, tài chính hoặc định danh cá nhân.
- Nội dung có quyền truy cập theo tenant hoặc role nếu không có thiết kế cache an toàn được đánh giá riêng.

Rủi ro thường gặp: Service Worker cache response của người dùng A, sau đó người dùng B dùng chung browser profile hoặc thiết bị và nhận lại response cũ.

Với API riêng tư, hãy để Service Worker đi thẳng tới network và không ghi response vào Cache Storage. Có thể cấu hình server `Cache-Control: no-store` cho response nhạy cảm, nhưng nhớ rằng Cache API không tự tuân theo header này; code vẫn phải chủ động bỏ qua.

## 18. Logout và dọn dữ liệu người dùng

Logout phải xử lý cả session server và dữ liệu client có thể còn lại:

1. Hủy hoặc thu hồi session/token ở server.
2. Dừng request đang chạy và trạng thái ứng dụng liên quan.
3. Xóa cache riêng tư nếu ứng dụng từng tạo cache đó.
4. Xóa dữ liệu user-specific trong IndexedDB/localStorage nếu có.
5. Đảm bảo Service Worker không tiếp tục trả response riêng tư từ cache.
6. Điều hướng tới trang đăng nhập hoặc trạng thái đã đăng xuất.

Ví dụ xóa một cache do ứng dụng sở hữu:

```js
async function clearPrivateCache() {
  await caches.delete("private-api-v1");
}
```

Nếu ứng dụng chỉ cache app shell công khai, không cần xóa toàn bộ cache tĩnh mỗi lần logout. Hãy phân biệt cache công khai với dữ liệu theo phiên.

Xóa cache không thu hồi session server và không đảm bảo mọi bản sao dữ liệu đã biến mất khỏi memory, log, HTTP cache hoặc storage khác. Logout cần được thiết kế xuyên suốt.

## 19. Cache response opaque và cross-origin

Fetch no-CORS cross-origin có thể tạo opaque response. Script không thể đọc status, headers hoặc body của response đó theo cách thông thường.

Nếu ứng dụng lưu một response opaque trong Cache Storage theo luồng được browser cho phép, ứng dụng vẫn không thể kiểm tra nội dung bên trong để xác minh dữ liệu. Vì vậy:

- Không coi opaque response là nội dung đã được xác minh.
- Không dùng opaque response cho API cần đọc dữ liệu.
- Nếu cần kiểm tra response hoặc áp dụng logic nghiệp vụ, dùng CORS đúng cách.
- Chỉ cache tài nguyên cross-origin khi đã hiểu request mode, CORS/CORP và policy của document.

CORP và COEP có thể ảnh hưởng việc tài nguyên cross-origin được phép tải/nhúng trong một số context. Cache Storage không bỏ qua các quy tắc này.

## 20. Quota, eviction và thời gian tồn tại

Cache Storage là kho lưu trữ lâu dài theo khả năng browser, nhưng **không phải dữ liệu được bảo đảm tồn tại vĩnh viễn**.

Browser có thể:

- Giới hạn dung lượng theo origin hoặc partition.
- Từ chối thao tác khi vượt quota.
- Xóa dữ liệu khi thiết bị thiếu dung lượng.
- Xóa dữ liệu khi người dùng clear site data.
- Dùng chính sách khác trong private browsing hoặc embedded context.

Ứng dụng có thể ước lượng dung lượng:

```js
async function inspectStorageUsage() {
  if (!navigator.storage?.estimate) return null;

  const { usage, quota } = await navigator.storage.estimate();
  return { usage, quota };
}
```

Có thể yêu cầu persistent storage nếu phù hợp:

```js
async function requestPersistentStorage() {
  if (!navigator.storage?.persist) return false;
  return navigator.storage.persist();
}
```

Browser có quyền quyết định có cấp persistent storage hay không. Không coi `persist()` là bảo đảm tuyệt đối và không lưu dữ liệu duy nhất mà sản phẩm không thể tái tạo.

## 21. Cache entry không tự hết hạn

Cache API không tự áp dụng freshness lifetime theo `Cache-Control` như HTTP cache. Entry thường tồn tại cho tới khi code xóa, browser eviction hoặc người dùng xóa dữ liệu site.

Ứng dụng cần:

- Đặt tên cache có version.
- Xóa cache version cũ khi activate Service Worker mới.
- Xác định chính sách cập nhật tài nguyên.
- Giới hạn loại URL được lưu.
- Dọn entry cũ hoặc không còn sử dụng.
- Xử lý quota error và cache miss.

Không dùng cache entry như nguồn sự thật cho trạng thái nghiệp vụ. Dữ liệu quan trọng phải được xác minh lại với server khi cần.

## 22. Ví dụ Service Worker: cache app shell, không cache API riêng tư

Ví dụ dưới đây chỉ cache tài nguyên tĩnh cùng origin trong đường dẫn `/assets/`. Navigation luôn thử network trước và chỉ dùng trang offline công khai khi mạng lỗi. Request API không được ghi vào cache.

```js
const CACHE_NAME = "app-shell-v3";
const CACHE_PREFIX = "app-shell-";
const APP_SHELL = [
  "/offline.html",
  "/assets/app.css",
  "/assets/app.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(APP_SHELL);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names
        .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
        .map((name) => caches.delete(name)),
    );
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        return await fetch(request);
      } catch {
        const cache = await caches.open(CACHE_NAME);
        return (await cache.match("/offline.html")) ??
          new Response("Offline", { status: 503 });
      }
    })());
    return;
  }

  if (!url.pathname.startsWith("/assets/")) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    if (response.ok && response.type === "basic") {
      try {
        await cache.put(request, response.clone());
      } catch {
        // Cache thất bại không được làm hỏng response mạng.
      }
    }
    return response;
  })());
});
```

Ví dụ này tránh cache route API và chỉ lưu tài nguyên tĩnh cùng origin. Khi deploy, hãy đồng bộ version cache với artifact; nếu trang HTML mới yêu cầu asset cũ hoặc ngược lại, cần có chiến lược deploy tương thích.

## 23. Versioning và cleanup cache

Tên cache nên gắn với version của app shell hoặc nhóm tài nguyên:

```js
const CACHE_NAMES = {
  shell: "app-shell-v3",
  images: "public-images-v2",
};
```

Khi Service Worker mới active:

1. Liệt kê cache bằng `caches.keys()`.
2. Giữ lại cache version hiện hành.
3. Xóa cache cũ thuộc prefix do ứng dụng sở hữu.
4. Không xóa cache của thư viện hoặc ứng dụng khác cùng origin nếu không thuộc quyền quản lý.

Ví dụ:

```js
async function deleteOldAppCaches() {
  const keep = new Set(["app-shell-v3", "public-images-v2"]);
  const names = await caches.keys();

  await Promise.all(
    names
      .filter((name) => name.startsWith("app-") && !keep.has(name))
      .map((name) => caches.delete(name)),
  );
}
```

Đừng xóa mọi cache theo cách không phân biệt tên nếu origin chứa nhiều ứng dụng hoặc module cùng chia sẻ storage scope.

## 24. Cache Storage và các API storage khác

| API | Dữ liệu | Vai trò chính |
| --- | --- | --- |
| Cache Storage | Request/Response | Cache tài nguyên và response cho offline |
| localStorage | String key/value | Cấu hình nhỏ, đồng bộ |
| sessionStorage | String key/value theo tab/origin | Trạng thái ngắn hạn trong tab |
| IndexedDB | Object store có cấu trúc | Dữ liệu lớn, truy vấn và transaction |
| Cookies | Key/value gửi theo HTTP rules | Session và state server/client |
| Storage Access API | Quyền truy cập unpartitioned state trong embed | Hỗ trợ một số tích hợp third-party |

Không dùng Cache Storage thay IndexedDB cho dữ liệu cần truy vấn có cấu trúc hoặc transaction. Không dùng Cache Storage thay cookie/session để xác thực. Chọn API theo mục đích và threat model.

## 25. Kiểm thử Cache Storage và storage partitioning

Thực hành trong môi trường local/staging với các origin do bạn kiểm soát. Không dùng token hoặc dữ liệu người dùng thật.

### Bước 1 — Kiểm tra secure context

Mở Console:

```js
console.log(window.isSecureContext);
console.log("caches" in window);
```

CacheStorage thường yêu cầu secure context. Localhost được browser xử lý như môi trường phát triển đáng tin theo quy tắc secure context.

### Bước 2 — Tạo cache ở first-party context

Truy cập trực tiếp widget origin ở top-level, sau đó:

```js
const cache = await caches.open("partition-lab-v1");
await cache.put(
  "/marker",
  new Response("created in first-party context"),
);
console.log(await cache.keys());
```

### Bước 3 — Nhúng cùng origin vào site A

Tạo một trang top-level trên origin A và nhúng widget bằng iframe. Trong iframe, mở cùng tên cache và kiểm tra marker. Ghi nhận browser có dùng storage riêng cho third-party context hay không.

### Bước 4 — Nhúng vào site B

Lặp lại với top-level site B. So sánh kết quả với site A và first-party context. Trong browser có storage partitioning, các context third-party có thể không nhìn thấy cùng cache state.

### Bước 5 — So sánh script tag và iframe

Thử tải một script từ widget origin bằng thẻ script và một iframe từ cùng origin. Kiểm tra:

- Script tag chạy trong origin của trang cha.
- Iframe chạy trong origin của widget.
- CacheStorage được truy cập tương ứng với browsing context của code.

### Bước 6 — Kiểm tra Service Worker và nested iframe

Thử đăng ký Service Worker trong context được browser hỗ trợ. Sau đó tạo nested iframe A → B → A và quan sát partitioning/policy. Một số browser có thể hạn chế đăng ký hoặc chia partition Service Worker trong third-party context.

### Bước 7 — Kiểm tra DevTools

Mở DevTools → Application/Storage:

- Cache Storage: xem tên cache và request entry.
- Service Workers: xem registration, scope và trạng thái worker.
- Storage: xem quota/usage nếu browser cung cấp.
- Network: xác định response đến từ Service Worker, Cache Storage hay network.

Tên tab và khả năng hiển thị khác nhau giữa browser. Thử thêm trong profile riêng hoặc chế độ privacy phù hợp; không thay đổi cài đặt bảo mật trên profile dùng hàng ngày chỉ để ép kết quả.

## 26. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `caches.open()` bị SecurityError | Không ở secure context hoặc browser hạn chế storage | Dùng HTTPS/localhost và kiểm tra browser support |
| Cache tồn tại ở top-level nhưng không thấy trong iframe | Third-party storage partitioning hoặc policy của browser | Kiểm tra top-level site, iframe context và browser privacy policy |
| Widget thấy cache trên site A nhưng không thấy trên site B | Cache được partition theo top-level site | Không dựa vào cache chia sẻ xuyên site; thiết kế API đồng bộ phù hợp |
| Script CDN thấy cache của trang cha | Script chạy trong origin của embedder | Đánh giá quyền của third-party script; cân nhắc iframe isolation |
| Response cũ vẫn được trả | Cache API không tự hết hạn theo Cache-Control | Version cache, cập nhật entry và xóa version cũ |
| API riêng tư bị trả dữ liệu cũ sau logout | Service Worker đã cache response cá nhân | Bỏ qua API/private routes và xóa dữ liệu theo phiên |
| Cache.put() bị lỗi | Quota, request không hợp lệ hoặc response không được chấp nhận | Bắt lỗi, kiểm tra Request/Response và quota |
| Asset mới nhưng browser vẫn dùng bản cũ | Cache name/version không đổi hoặc entry chưa bị xóa | Version cache và đồng bộ deploy |
| Hai cache cùng URL trả kết quả khác | Tìm cache không xác định hoặc Vary khác nhau | Mở cache cụ thể và kiểm tra Request/Vary |
| Offline page không hiển thị | Offline asset chưa được precache hoặc install thất bại | Kiểm tra install event và addAll response |
| Storage Access API không cấp quyền | Browser policy, thiếu user activation hoặc yêu cầu chưa thỏa | Xử lý từ chối và thiết kế fallback |

## 27. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Cache Storage là HTTP cache.” | Cache Storage là kho do code quản lý; HTTP cache do browser quản lý theo HTTP rules. |
| “Cache-Control: no-store ngăn Cache.put().” | Cache API không tự tuân theo HTTP caching headers; code phải chủ động không lưu. |
| “Cache name là sandbox.” | Script cùng origin có thể truy cập nhiều cache trong storage context của nó. |
| “CacheStorage chỉ dùng được trong Service Worker.” | Window và worker cũng có thể truy cập API trong môi trường được hỗ trợ. |
| “Một origin chỉ có một cache dùng chung ở mọi website.” | Third-party storage partitioning có thể tách storage theo top-level site và context. |
| “Cùng origin nghĩa là luôn cùng partition.” | Trong third-party context, browser có thể thêm top-level site hoặc ancestor state vào storage key. |
| “Script CDN có origin riêng.” | Script tag chạy trong browsing context/origin của trang nhúng; iframe mới có document origin riêng. |
| “Storage Access API cho iframe đọc cache của parent.” | API không phá SOP và không cấp quyền đọc storage của origin khác. |
| “Cache API tự xóa entry cũ.” | Ứng dụng phải version, cập nhật và cleanup; browser cũng có thể eviction. |
| “Cache là nơi an toàn để lưu token.” | XSS cùng origin có thể đọc cache; không dùng Cache Storage làm secret vault. |
| “Cache offline luôn tồn tại.” | Quota, eviction, private mode và user settings có thể làm cache biến mất. |

## 28. Checklist triển khai Cache Storage

- Chỉ cache tài nguyên công khai hoặc dữ liệu đã được đánh giá rõ về quyền truy cập.
- Phân biệt Cache Storage với HTTP cache; không dựa vào Cache-Control để kiểm soát Cache API.
- Chỉ cache request cần thiết, ưu tiên GET và allowlist URL.
- Kiểm tra origin, status, response type và content trước khi lưu.
- Không dùng cache name làm ranh giới bảo mật hoặc authorization.
- Không cache token, response cá nhân hóa hoặc dữ liệu nhạy cảm theo session.
- Bỏ qua API/private routes trong Service Worker fetch handler.
- Dùng versioned cache names và cleanup đúng prefix do ứng dụng sở hữu.
- Dùng clone khi response cần vừa trả về vừa lưu cache.
- Giữ mặc định match theo query/Vary; chỉ bỏ qua khi đã chứng minh an toàn.
- Xử lý quota error, eviction, cache miss và offline fallback.
- Hiểu script tag chạy dưới origin của embedder; dùng iframe khi cần origin isolation.
- Kiểm thử first-party, third-party iframe, top-level site khác nhau và nested frames.
- Không dựa vào Storage Access API để chia sẻ CacheStorage xuyên origin.
- Dùng CSP, SRI và kiểm soát Service Worker script để giảm nguy cơ cache poisoning.
- Kiểm tra Network/Application trên browser mục tiêu và sau mỗi thay đổi privacy policy.

## 29. Câu hỏi tự kiểm tra

1. Cache Storage khác HTTP cache ở quyền điều khiển và expiry như thế nào?
2. CacheStorage, Cache và Request/Response có vai trò gì?
3. Vì sao Cache API không tự tuân theo Cache-Control: no-store?
4. Same-Origin Policy giới hạn việc truy cập CacheStorage ra sao?
5. Storage partitioning bổ sung top-level site vào storage boundary để giải quyết vấn đề gì?
6. Vì sao cùng một third-party iframe có thể thấy cache khác nhau trên site A và site B?
7. Script tag và iframe khác nhau thế nào về origin của code?
8. Vì sao cache name không phải ranh giới bảo mật?
9. XSS có thể đọc hoặc ghi CacheStorage cùng origin như thế nào?
10. Vì sao không nên cache API response cá nhân hóa?
11. Storage Access API có thể giải quyết trường hợp nào và không làm gì?
12. Cache API match chịu ảnh hưởng của query string và Vary như thế nào?
13. Vì sao phải version cache và cleanup entry cũ?
14. Browser eviction ảnh hưởng tới tính năng offline ra sao?
15. Cần kiểm thử những context nào để xác minh storage partitioning?

## Tài liệu tham khảo

- [MDN — Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
- [MDN — CacheStorage](https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage)
- [MDN — State Partitioning](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/State_Partitioning)
- [MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
- [MDN — Storage Access API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_Access_API)
- [Chrome Privacy Sandbox — Storage Partitioning](https://privacysandbox.google.com/cookies/storage-partitioning)
- [W3C — Service Workers](https://www.w3.org/TR/service-workers/)

**Ghi nhớ:** Cache Storage là kho Request/Response do code quản lý trong storage context của browser. SOP giới hạn truy cập theo origin; storage partitioning có thể chia thêm theo top-level site trong third-party context để giảm tracking và side-channel leaks. Script tag chạy dưới origin của trang nhúng, còn iframe có origin riêng. Cache không phải kho bí mật: XSS cùng origin có thể đọc/ghi cache, Cache API không tự tuân theo Cache-Control và entry không tự hết hạn. Chỉ cache dữ liệu cần thiết, version và cleanup rõ ràng, tránh response nhạy cảm, và kiểm thử first-party lẫn third-party context trên browser mục tiêu.
