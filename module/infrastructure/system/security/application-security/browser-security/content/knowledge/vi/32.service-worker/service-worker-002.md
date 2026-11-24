# Worker scope: phạm vi URL mà Service Worker kiểm soát

Service Worker là worker chạy nền theo mô hình sự kiện. Nó có thể nhận các sự kiện như `install`, `activate`, `fetch` và `message`, hỗ trợ cache tài nguyên hoặc xây dựng trải nghiệm offline. Một website có thể có nhiều trang và nhiều ứng dụng con, vì vậy cần xác định chính xác trang nào được một Service Worker kiểm soát.

`Worker scope` là phạm vi URL được gắn với một Service Worker registration. Khi trình duyệt tạo hoặc điều hướng một client, nó tìm registration có scope phù hợp để quyết định worker nào có thể điều khiển client đó. Scope vì vậy ảnh hưởng đến trang nào nhận controller và các sự kiện fetch phát sinh từ client được điều khiển.

Scope là một cấu hình quan trọng về kiến trúc và bảo mật. Nếu đặt quá rộng, một worker có thể tác động đến nhiều trang hơn dự kiến; nếu đặt quá hẹp, một phần ứng dụng sẽ không được điều khiển và tính năng offline có thể hoạt động không nhất quán.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích worker scope và quan hệ giữa scope, script URL và registration.
- Xác định scope mặc định từ vị trí file Service Worker.
- Đăng ký worker với scope tường minh bằng `navigator.serviceWorker.register()`.
- Hiểu quy tắc URL matching và ảnh hưởng của dấu gạch chéo cuối đường dẫn.
- Dùng `Service-Worker-Allowed` để mở rộng giới hạn scope khi thật sự cần.
- Phân biệt scope của client với URL của request được xử lý trong sự kiện fetch.
- Giải thích cách nhiều registration có scope chồng lấn được chọn.
- Xử lý trang đang mở, controller, `clients.claim()` và điều hướng sau khi đăng ký.
- Thiết kế scope an toàn cho ứng dụng đặt dưới subpath, nhiều ứng dụng cùng origin và reverse proxy.
- Kiểm thử registration, scope và controller bằng DevTools.

## 1. Worker scope là gì?

Một registration liên kết một Service Worker script với một scope URL. Scope xác định những URL tài liệu mà registration có thể điều khiển.

Ví dụ một website:

~~~text
https://example.test/
├── index.html
├── account/
│   ├── index.html
│   └── settings.html
└── shop/
    ├── index.html
    └── checkout.html
~~~

Nếu worker đăng ký với scope `https://example.test/shop/`, các trang trong khu vực `/shop/` có thể được registration đó điều khiển sau khi worker active và client phù hợp được gắn controller.

Các trang `/account/` không nằm trong scope này nên sẽ không được registration `/shop/` điều khiển.

### 1.1 Scope thuộc về registration

Một registration có các thông tin quan trọng:

- `scope`: URL scope.
- `installing`: worker đang cài đặt, nếu có.
- `waiting`: worker đã cài đặt nhưng đang chờ kích hoạt, nếu có.
- `active`: worker đang active, nếu có.

Scope không phải một biến trong file worker và cũng không phải một bộ lọc tự động cho mọi URL mà worker có thể fetch. Nó là phạm vi client được gắn với registration.

### 1.2 Scope không phải sandbox bảo mật giữa các ứng dụng cùng origin

SOP vẫn áp dụng theo origin. Hai ứng dụng cùng scheme, hostname và port vẫn thuộc cùng origin, dù chúng có các scope Service Worker khác nhau.

Scope giúp chọn worker điều khiển client. Nó không tạo ra ranh giới bảo mật tương đương origin riêng, không tách cookie hoặc IndexedDB, và không ngăn JavaScript cùng origin truy cập tài nguyên mà SOP cho phép.

Nếu hai ứng dụng có mức độ tin cậy khác nhau, hãy cân nhắc tách origin. Đừng dựa vào scope để cô lập dữ liệu bí mật giữa các ứng dụng cùng origin.

## 2. Quan hệ giữa script URL và scope

Khi đăng ký Service Worker, ứng dụng truyền URL của file script và có thể truyền thêm tùy chọn scope:

~~~js
navigator.serviceWorker.register("/shop/sw.js", {
  scope: "/shop/"
});
~~~

Hai giá trị có ý nghĩa riêng:

- `scriptURL` cho biết file JavaScript nào được tải làm Service Worker.
- `scope` cho biết registration được phép điều khiển những client URL nào.

Script URL và scope không bắt buộc phải có cùng đường dẫn. Tuy nhiên, theo mặc định, scope không được rộng hơn giới hạn đường dẫn của vị trí script. Header `Service-Worker-Allowed` có thể thay đổi giới hạn tối đa này.

### 2.1 Scope mặc định

Nếu bỏ qua tùy chọn `scope`, trình duyệt dùng thư mục chứa Service Worker script làm scope mặc định.

Ví dụ:

| Script URL | Scope mặc định |
|---|---|
| `https://example.test/sw.js` | `https://example.test/` |
| `https://example.test/shop/sw.js` | `https://example.test/shop/` |
| `https://example.test/assets/sw.js` | `https://example.test/assets/` |
| `https://example.test/app/workers/sw.js` | `https://example.test/app/workers/` |

Điểm dễ nhầm: scope mặc định được suy ra từ vị trí của script URL, không phải thư mục của trang đang gọi `register()`.

Ví dụ trang `/shop/index.html` gọi `register("/assets/sw.js")`. Nếu không chỉ định scope, registration mặc định chỉ có scope `/assets/`, chứ không tự động là `/shop/`.

### 2.2 Dùng đường dẫn tương đối hay tuyệt đối?

URL của script và scope được phân giải theo quy tắc URL của trình duyệt. Đường dẫn tương đối có thể thay đổi kết quả nếu đoạn mã đăng ký được gọi từ các trang có base URL khác nhau.

Ví dụ:

~~~js
// URL tương đối theo trang hiện tại
navigator.serviceWorker.register("./sw.js", {
  scope: "./"
});

// URL theo root của origin
navigator.serviceWorker.register("/shop/sw.js", {
  scope: "/shop/"
});
~~~

Với ứng dụng được triển khai ổn định dưới một subpath, đường dẫn site-relative như `/shop/sw.js` và `/shop/` thường dễ review hơn vì không phụ thuộc trang nào thực hiện đăng ký.

Nếu ứng dụng có thẻ `<base>`, hãy kiểm tra base URL thực tế vì nó có thể ảnh hưởng cách phân giải URL tương đối.

### 2.3 Script URL phải cùng origin và dùng secure context

Service Worker chỉ được đăng ký trong secure context, thông thường là HTTPS. `localhost` và một số loopback address là ngoại lệ phục vụ phát triển.

Script URL và scope phải cùng origin với trang đăng ký. Một trang tại `https://app.example.test` không thể đăng ký worker script từ `https://cdn.example.test/sw.js` như một Service Worker cross-origin thông thường.

File worker cần được phục vụ với JavaScript MIME type hợp lệ. Redirect, sai MIME type, URL sai hoặc response không hợp lệ đều có thể làm đăng ký thất bại.

Không dùng CORS để biến một script cross-origin thành Service Worker hợp lệ. Ràng buộc cùng origin vẫn được áp dụng.

## 3. Quy tắc matching của scope

Trình duyệt so khớp URL của client với scope URL. Về khái quát, việc matching dựa trên tiền tố của URL đã được serialize, và registration có scope khớp cụ thể nhất được ưu tiên nếu có nhiều registration phù hợp.

Điều này khiến dấu gạch chéo cuối đường dẫn rất quan trọng.

### 3.1 Vì sao nên dùng dấu gạch chéo cuối?

Giả sử scope là `https://example.test/app`. Vì matching theo tiền tố URL, scope này có thể khớp cả:

- `https://example.test/app`
- `https://example.test/app/home`
- `https://example.test/application`

Nếu mục tiêu là chỉ điều khiển khu vực `/app/`, hãy dùng scope `https://example.test/app/` để tránh khớp ngoài ý muốn với `/application`.

Bảng ví dụ:

| Scope | Client URL | Có khớp theo tiền tố? |
|---|---|---|
| `/app/` | `/app/` | Có |
| `/app/` | `/app/home` | Có |
| `/app/` | `/application` | Không |
| `/app` | `/application` | Có |
| `/shop/` | `/shop/cart/` | Có |
| `/shop/` | `/account/` | Không |

Đây là quy tắc tiền tố URL, không phải kiểm tra ranh giới segment giống một phép so sánh thư mục của hệ điều hành. Hãy chọn scope có dấu gạch chéo phù hợp với ranh giới ứng dụng.

### 3.2 Cùng origin vẫn là điều kiện bắt buộc

Scope không thể vượt sang origin khác. Một scope chỉ hợp lệ nếu cùng origin với trang đăng ký.

Ví dụ trang `https://example.test` không thể đặt scope thành `https://admin.example.test/` hoặc `https://example.test:8443/`.

Khác scheme, hostname hoặc port là khác origin.

### 3.3 Fragment không xác định registration riêng

Fragment của scope URL không được lưu để nhận diện registration. Không dùng hash như `/app/#section` để tạo phạm vi Service Worker riêng.

Thiết kế scope bằng path URL ổn định. Tránh nhét trạng thái UI hoặc query parameter vào scope.

## 4. Service-Worker-Allowed: mở rộng scope tối đa

Mặc định, một worker script chỉ được đăng ký với scope không rộng hơn thư mục chứa script. Nếu file script nằm trong `/shop/sw.js`, scope mặc định là `/shop/`.

Nếu muốn script này điều khiển cả website tại `/`, máy chủ phải trả response header `Service-Worker-Allowed` trên chính response của file worker.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript
Service-Worker-Allowed: /

~~~

Sau đó trang có thể đăng ký:

~~~js
navigator.serviceWorker.register("/shop/sw.js", {
  scope: "/"
});
~~~

Nếu không có header cho phép mở rộng, yêu cầu scope rộng hơn giới hạn script path sẽ thất bại.

### 4.1 Header áp dụng ở response nào?

`Service-Worker-Allowed` phải có trong response của Service Worker script. Đặt header này trên trang HTML đăng ký hoặc trên một API response khác không thay đổi giới hạn scope của script.

Ví dụ với script `/shop/sw.js`:

- Response `/shop/sw.js` có `Service-Worker-Allowed: /`: cho phép yêu cầu scope root.
- Response `/shop/index.html` có header đó nhưng response worker không có: không mở rộng giới hạn của worker.
- Response worker có `Service-Worker-Allowed: /shop/`: không cho phép scope root `/`.

Giá trị header xác định scope tối đa được cho phép. Nó không tự thay thế tùy chọn scope trong `register()`.

### 4.2 Chỉ mở rộng khi có lý do rõ ràng

Một worker ở `/shop/sw.js` có thể được phép điều khiển toàn bộ origin nếu server trả `Service-Worker-Allowed: /`. Điều này rất mạnh vì worker có thể trở thành controller của các trang ngoài khu vực shop.

Trước khi mở rộng, hãy xác định:

- Worker có thực sự cần điều khiển trang ngoài thư mục script không?
- Worker có thể intercept navigation hoặc request từ những khu vực nào?
- Các ứng dụng khác trên cùng origin có bị ảnh hưởng không?
- Chính sách cache có phân biệt route và account không?
- Đội vận hành có thể rollback registration nếu worker lỗi không?

Không đặt header scope rộng chỉ để sửa nhanh lỗi đăng ký.

## 5. Scope điều khiển client, không phải allowlist URL fetch

Đây là khác biệt quan trọng khi thiết kế fetch handler.

Giả sử một trang tại `/shop/checkout/` được điều khiển bởi worker scope `/shop/`. Trang này gọi:

~~~js
fetch("/api/orders/current");
~~~

Request URL là `/api/orders/current`, nằm ngoài path `/shop/`. Tuy nhiên, fetch event vẫn có thể được gửi đến Service Worker điều khiển client đã tạo request.

Scope xác định client nào được điều khiển. Nó không đơn giản là một allowlist chỉ cho phép worker nhìn thấy các request có URL nằm dưới cùng path.

Nếu cần giới hạn cách worker xử lý request, hãy tự kiểm tra URL, method, mode và destination trong fetch handler:

~~~js
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) {
    return;
  }

  if (request.method !== "GET") {
    return;
  }

  if (!url.pathname.startsWith("/shop/assets/")) {
    return;
  }

  event.respondWith(handleShopAsset(request));
});
~~~

`handleShopAsset()` là hàm do ứng dụng định nghĩa. Ví dụ chỉ minh họa một allowlist xử lý cache cho GET cùng origin trong khu vực asset. Nó không thay đổi scope registration.

### 5.1 Scope và fetch handler là hai lớp khác nhau

| Thành phần | Quyết định điều gì? |
|---|---|
| Registration scope | Client URL nào có thể được điều khiển |
| Active worker | Worker nào đang hoạt động trong registration |
| `navigator.serviceWorker.controller` | Worker hiện đang điều khiển tài liệu |
| Fetch handler | Request được xử lý, bỏ qua hoặc phản hồi thế nào |
| Cache strategy | Response nào được đọc/ghi trong Cache Storage |

Một worker có thể điều khiển client trong `/shop/` nhưng chỉ cache một số tài nguyên trong `/shop/assets/`. Phạm vi cache do code quyết định, không tự động kế thừa từ scope.

## 6. Nhiều Service Worker registration và scope chồng lấn

Một origin có thể có nhiều registration nếu mỗi registration có scope URL khác nhau.

Ví dụ:

~~~text
https://example.test/
├── sw-root.js       scope /
├── shop/
│   └── sw-shop.js   scope /shop/
└── admin/
    └── sw-admin.js  scope /admin/
~~~

Nếu một client URL khớp nhiều scope, trình duyệt chọn registration có scope khớp cụ thể nhất, tức scope URL dài nhất trong các scope khớp.

Ví dụ:

| Client URL | Scope khớp | Registration được chọn |
|---|---|---|
| `/home` | `/` | Root worker |
| `/shop/cart` | `/` và `/shop/` | Shop worker |
| `/admin/users` | `/` và `/admin/` | Admin worker |
| `/shop/admin/report` | `/`, `/shop/` | Shop worker |

Hãy tránh tạo scope chồng lấn nếu không cần. Một root worker có thể ảnh hưởng đến ứng dụng con, trong khi một worker cụ thể hơn sẽ được chọn cho client trong khu vực con.

### 6.1 Đăng ký cùng scope

Một scope URL định danh registration trong storage key tương ứng. Nếu gọi `register()` với cùng scope, trình duyệt cập nhật registration hiện có theo script URL và tùy chọn mới, thay vì tạo một registration song song cho cùng scope.

Nếu cần thay đổi phạm vi, hãy thiết kế quá trình đăng ký scope mới và gỡ registration cũ khi không còn client phụ thuộc. Không giả định việc sửa chuỗi scope trong một registration đang tồn tại sẽ tự thay đổi registration key.

### 6.2 Tách ứng dụng theo subpath

Giả sử một origin phục vụ hai ứng dụng:

~~~text
https://portal.example.test/
├── customer/
└── staff/
~~~

Có thể dùng:

~~~js
navigator.serviceWorker.register("/customer/sw.js", {
  scope: "/customer/"
});

navigator.serviceWorker.register("/staff/sw.js", {
  scope: "/staff/"
});
~~~

Mỗi ứng dụng có worker riêng. Tuy vậy, chúng vẫn cùng origin, nên cookie, storage và các quyền cùng origin vẫn có thể được chia sẻ theo quy tắc trình duyệt.

Nếu hai ứng dụng cần tách biệt bảo mật thực sự, dùng subdomain hoặc origin riêng và thiết kế xác thực, cookie cùng CORS phù hợp.

## 7. Scope và vòng đời điều khiển trang

Đăng ký thành công không đồng nghĩa trang hiện tại lập tức có controller.

Các trạng thái worker thường đi qua:

~~~text
register()
   |
   v
installing
   |
   v
installed / waiting
   |
   v
activating
   |
   v
activated
   |
   v
controller của client phù hợp
~~~

Trang đã mở trước khi worker được cài đặt có thể chưa được điều khiển ngay. Thông thường, navigation tiếp theo vào URL trong scope sẽ được worker active điều khiển.

### 7.1 Kiểm tra controller

Trong trang:

~~~js
if (navigator.serviceWorker.controller) {
  console.log("Trang đang được điều khiển");
} else {
  console.log("Trang chưa có controller");
}
~~~

Để theo dõi thay đổi controller:

~~~js
navigator.serviceWorker.addEventListener("controllerchange", () => {
  console.log("Controller của trang đã thay đổi");
});
~~~

`navigator.serviceWorker.ready` trả về registration có active worker phù hợp với trang. Nó không có nghĩa mọi request trên trang đều được cache hoặc mọi API fetch đều thành công.

### 7.2 clients.claim()

Worker active có thể gọi `clients.claim()` trong sự kiện activate để nhận quyền điều khiển các client hiện có trong scope phù hợp:

~~~js
self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});
~~~

Điều này có thể khiến trang đang mở nhận controller mà không cần reload. Tuy nhiên, hãy kiểm thử cẩn thận vì trang hiện tại có thể chưa được thiết kế để hoạt động với phiên bản worker mới.

### 7.3 skipWaiting và claim không thay đổi scope

`skipWaiting()` ảnh hưởng thời điểm worker waiting được kích hoạt. `clients.claim()` ảnh hưởng các client phù hợp được worker active nhận điều khiển.

Hai API này không mở rộng hoặc thu hẹp registration scope. Scope vẫn được quyết định bởi registration đã đăng ký.

### 7.4 unregister không lập tức ngắt client hiện tại

`registration.unregister()` yêu cầu hủy đăng ký để các navigation tiếp theo không còn dùng registration đó. Các client đang được worker điều khiển có thể tiếp tục dùng worker cho đến khi chúng unload.

Nếu cần gỡ worker trong ứng dụng đang chạy:

1. Gọi unregister cho đúng registration.
2. Xử lý cache do worker sở hữu nếu cần.
3. Điều hướng hoặc reload client theo kế hoạch.
4. Kiểm tra không còn registration cũ ngoài ý muốn.

Không xóa mọi cache hoặc unregister tất cả registration trên origin nếu ứng dụng khác cùng origin còn phụ thuộc.

## 8. Thiết kế scope cho ứng dụng triển khai dưới subpath

Ứng dụng có thể chạy ở root trong môi trường local nhưng được deploy dưới prefix như `/portal/` hoặc `/customer/app/`. Nếu hardcode scope `/`, worker có thể điều khiển rộng hơn dự kiến.

Ví dụ:

~~~text
Local:
http://localhost:5173/

Production:
https://example.test/portal/
~~~

Nếu worker được phục vụ tại `/portal/sw.js`, hãy đăng ký:

~~~js
navigator.serviceWorker.register("/portal/sw.js", {
  scope: "/portal/"
});
~~~

Không dùng `scope: "/"` trừ khi ứng dụng thật sự sở hữu toàn bộ origin và server đã cho phép giới hạn tối đa tương ứng.

### 8.1 Reverse proxy và base path

Khi deploy qua reverse proxy, hãy kiểm tra:

- URL public mà trình duyệt nhìn thấy.
- URL script worker sau khi rewrite.
- Scope mà `register()` yêu cầu.
- Header `Service-Worker-Allowed` trên response script.
- Redirect từ script URL.
- SPA fallback có trả HTML thay vì JavaScript cho URL worker hay không.

Một server có thể trả `index.html` cho mọi route không tồn tại. Nếu `/portal/sw.js` bị fallback thành HTML, đăng ký worker sẽ thất bại do MIME type không đúng hoặc nội dung script không hợp lệ.

### 8.2 Build output và asset path

Build tool có thể đặt worker vào thư mục public, assets hoặc root. Đường dẫn script phải trỏ đến file thực sự được deploy.

Đừng chỉ kiểm tra mã nguồn. Hãy mở URL worker trên môi trường triển khai và xác minh:

- Response status.
- Content-Type JavaScript.
- Redirect chain.
- Response header Service-Worker-Allowed.
- Nội dung script đúng phiên bản.

## 9. Bảo mật khi chọn scope

Service Worker có thể intercept navigation và fetch từ các client nó điều khiển. Worker sai hoặc bị thay đổi có thể ảnh hưởng rộng đến ứng dụng.

### 9.1 Least privilege

Chọn scope nhỏ nhất đáp ứng chức năng. Ví dụ ứng dụng shop đặt dưới `/shop/` nên dùng `/shop/` nếu không cần điều khiển trang khác.

Scope root `/` có tác động toàn origin. Nếu website có admin, customer portal, legacy app và marketing site cùng origin, root worker có thể gây tương tác không mong muốn.

### 9.2 Kiểm soát script URL

Không nhận URL worker từ query string, localStorage, API response hoặc input không tin cậy rồi truyền trực tiếp vào `register()`.

Ví dụ không an toàn:

~~~js
const scriptURL = new URLSearchParams(location.search).get("worker");
navigator.serviceWorker.register(scriptURL);
~~~

Kẻ tấn công có thể tìm cách khiến ứng dụng đăng ký script không mong muốn. Hãy cố định script URL trong code hoặc lấy từ cấu hình đã được kiểm soát.

CSP với directive `worker-src` giúp giới hạn nguồn worker. Nếu site thực thi Trusted Types, `register()` cũng là injection sink có thể yêu cầu `TrustedScriptURL` theo policy của trang.

### 9.3 Scope không thay thế authorization

Một worker scope chỉ quyết định client nào được điều khiển. Nó không cấp quyền đọc dữ liệu tài khoản, không xác thực user và không thay thế authorization ở server.

Không dùng kiểm tra pathname trong worker như cơ chế phân quyền duy nhất. Server phải xác thực và phân quyền mọi request nhạy cảm.

### 9.4 Tránh cache dữ liệu cá nhân ở scope rộng

Nếu worker root xử lý cả trang public và private, cần phân loại request cẩn thận. Không cache response tài khoản hoặc response chứa token chỉ vì request phát sinh từ client nằm trong scope.

Scope rộng làm tăng số client và request mà worker có thể tác động. Điều này làm tăng độ phức tạp của cache invalidation, logout và account switching.

## 10. Kiểm tra scope bằng JavaScript

Có thể liệt kê các registration mà origin hiện tại nhìn thấy:

~~~js
async function inspectRegistrations() {
  if (!("serviceWorker" in navigator)) {
    return [];
  }

  const registrations = await navigator.serviceWorker.getRegistrations();

  return registrations.map(registration => ({
    scope: registration.scope,
    activeScript: registration.active?.scriptURL ?? null,
    installingScript: registration.installing?.scriptURL ?? null,
    waitingScript: registration.waiting?.scriptURL ?? null
  }));
}

inspectRegistrations().then(console.table);
~~~

Có thể tìm registration phù hợp với một client URL:

~~~js
const registration =
  await navigator.serviceWorker.getRegistration(location.href);

console.log(registration?.scope ?? "No matching registration");
~~~

Đây là công cụ quan sát registration. Đừng dùng nó để tự động xóa registration không rõ chủ sở hữu.

### 10.1 Kiểm tra scope và controller

~~~js
console.log({
  controllerScript: navigator.serviceWorker.controller?.scriptURL ?? null
});

navigator.serviceWorker.ready.then(registration => {
  console.log({
    scope: registration.scope,
    activeScript: registration.active?.scriptURL ?? null
  });
});
~~~

`registration.scope` cho biết scope của registration. `controller.scriptURL` cho biết script của worker đang điều khiển tài liệu hiện tại. Hai giá trị có vai trò khác nhau.

## 11. Kiểm thử bằng DevTools

Trong Chrome hoặc Chromium-based browser, mở DevTools và tìm mục Application → Service Workers. Tùy trình duyệt, tên hoặc vị trí panel có thể khác.

Kiểm tra:

- Script URL.
- Scope URL.
- Trạng thái installing, waiting hoặc activated.
- Trang hiện tại có controller không.
- Registration có đang bị update hoặc blocked không.
- Worker nào nhận fetch event.
- Cache nào thuộc ứng dụng.

Trong Network:

1. Bật Preserve log.
2. Reload trang trong scope.
3. Xem request document và subresources.
4. Kiểm tra request được đánh dấu từ Service Worker nếu trình duyệt hỗ trợ.
5. So sánh URL trang với scope.
6. Kiểm tra script response và header Service-Worker-Allowed.

Trong Console:

~~~js
navigator.serviceWorker.controller?.scriptURL;
~~~

và:

~~~js
(await navigator.serviceWorker.getRegistrations())
  .map(registration => registration.scope);
~~~

### 11.1 Ma trận kiểm thử tối thiểu

| Client URL | Scope dự kiến | Kết quả cần thấy |
|---|---|---|
| `/shop/` | `/shop/` | Được điều khiển sau activation/navigation phù hợp |
| `/shop/cart` | `/shop/` | Được điều khiển |
| `/shopper/` | `/shop/` | Không được điều khiển |
| `/account/` | `/shop/` | Không được điều khiển |
| `/shop/assets/app.js` | Client `/shop/` đang được điều khiển | Fetch event có thể được phát dù asset path là request URL riêng |
| `/shop/` | Root và `/shop/` cùng khớp | Chọn scope cụ thể hơn `/shop/` |

Không chỉ kiểm tra trang chủ. Hãy kiểm tra đường dẫn biên như `/shopper/` để phát hiện scope thiếu dấu gạch chéo.

## 12. Lỗi cấu hình thường gặp

### 12.1 Đặt scope rộng hơn vị trí script

Script ở `/assets/sw.js` nhưng đăng ký scope `/`. Nếu không có Service-Worker-Allowed phù hợp, đăng ký thất bại.

Sửa bằng cách đặt scope nhỏ hơn hoặc chuyển script đến vị trí phù hợp. Chỉ dùng header để mở rộng khi có nhu cầu đã được review.

### 12.2 Nhầm scope theo trang đăng ký

Trang `/shop/index.html` đăng ký `/assets/sw.js` rồi nghĩ worker mặc định điều khiển `/shop/`. Scope mặc định thực tế theo thư mục script `/assets/`.

Hãy đặt scope tường minh và xác minh bằng `registration.scope`.

### 12.3 Thiếu dấu gạch chéo cuối

Scope `/app` có thể khớp cả `/application` do tiền tố URL. Dùng `/app/` nếu muốn giới hạn khu vực app.

### 12.4 Dùng root scope cho một ứng dụng con

Ứng dụng chỉ nằm dưới `/portal/` nhưng đăng ký `/`. Worker có thể điều khiển cả trang khác cùng origin.

Hãy chọn scope `/portal/` và chỉ mở rộng khi có thiết kế toàn site.

### 12.5 Nghĩ scope lọc request URL

Trang trong scope gọi API ngoài path scope vẫn có thể phát sinh fetch event cho worker đang điều khiển client. Nếu muốn giới hạn xử lý request, kiểm tra URL trong fetch handler.

### 12.6 Quên controller của trang hiện tại

Đăng ký đã thành công nhưng trang hiện tại vẫn chưa có controller. Hãy kiểm tra trạng thái active, điều hướng lại hoặc dùng clients.claim() khi thiết kế yêu cầu.

### 12.7 Nhiều registration chồng lấn

Root worker và app worker cùng khớp có thể làm người phát triển khó hiểu worker nào điều khiển trang. Hãy liệt kê registration, chọn scope có chủ sở hữu rõ ràng và tránh overlap không cần thiết.

### 12.8 Header đặt sai response

Service-Worker-Allowed phải nằm trên response của script worker. Đặt nó trên HTML page không mở rộng giới hạn.

### 12.9 Server fallback trả HTML cho file worker

URL worker trả status 200 nhưng body là HTML vẫn không phải script hợp lệ. Kiểm tra MIME type và response body trên production.

### 12.10 Coi scope là ranh giới bảo mật giữa sub-app

Hai ứng dụng cùng origin vẫn chia sẻ nhiều quyền và dữ liệu theo origin. Dùng origin riêng nếu cần cách ly mạnh.

## 13. Quy trình triển khai Worker scope

Trước khi phát hành:

1. Vẽ cấu trúc URL public của website.
2. Xác định client/page nào cần được Service Worker điều khiển.
3. Đặt file worker ở vị trí dễ hiểu và ổn định.
4. Chọn scope nhỏ nhất đáp ứng yêu cầu.
5. Dùng dấu gạch chéo cuối để thể hiện ranh giới path.
6. Chỉ cấu hình Service-Worker-Allowed khi cần mở rộng hơn thư mục script.
7. Kiểm tra script URL, MIME type, HTTPS và redirect.
8. Kiểm tra registration.scope và controller trên các route biên.
9. Kiểm tra fetch handler có lọc URL, method và destination phù hợp.
10. Kiểm tra các registration chồng lấn trên cùng origin.
11. Kiểm thử update, waiting worker, reload và rollback.
12. Theo dõi lỗi sau triển khai và có cách unregister registration cũ.

Mỗi registration nên có một chủ sở hữu và một phạm vi được ghi rõ trong tài liệu triển khai.

## 14. Bài thực hành

Thực hiện trên localhost hoặc HTTPS origin do bạn kiểm soát. Không đăng ký worker trên website bên thứ ba.

### Bài 1: Quan sát scope mặc định

Tạo worker ở `/lab/sw.js`. Đăng ký mà không truyền scope. Đọc `registration.scope` và giải thích vì sao kết quả là `/lab/`.

### Bài 2: Thu hẹp scope

Tạo worker ở `/sw.js` và đăng ký với scope `/lab/`. Kiểm tra trang `/lab/index.html` được điều khiển, còn trang `/account/index.html` không được điều khiển.

### Bài 3: Kiểm tra prefix và dấu gạch chéo

Đăng ký lần lượt scope `/app` và `/app/`. Kiểm tra các URL `/app/home` và `/application/home`. Ghi lại registration nào khớp.

### Bài 4: Mở rộng bằng Service-Worker-Allowed

Đặt script ở `/lab/sw.js` và yêu cầu scope `/`. Quan sát đăng ký thất bại khi thiếu header. Thêm `Service-Worker-Allowed: /` vào response worker script rồi thử lại.

### Bài 5: Nhiều registration chồng lấn

Tạo root scope `/` và scope `/shop/` với hai script khác nhau. Truy cập `/shop/cart` và `/about`. Xác định registration được chọn qua `controller.scriptURL`.

### Bài 6: Scope và fetch URL

Tạo trang `/shop/` do worker điều khiển. Từ trang đó fetch `/api/status`. Quan sát fetch event trong worker dù URL request nằm ngoài path `/shop/`. Sau đó tự giới hạn handler theo pathname.

### Bài 7: Triển khai subpath

Build ứng dụng vào `/portal/`. Đăng ký worker ở `/portal/sw.js` với scope `/portal/`. Kiểm tra reverse proxy, MIME type, response header và trang ở ngoài `/portal/`.

## 15. Checklist review Worker scope

- [ ] Đã liệt kê URL public mà worker cần điều khiển.
- [ ] Script URL cùng origin với trang đăng ký.
- [ ] Website chạy trong secure context.
- [ ] Script response có JavaScript MIME type hợp lệ.
- [ ] Scope được chỉ định tường minh khi ứng dụng deploy dưới subpath.
- [ ] Scope mặc định được hiểu theo thư mục chứa script.
- [ ] Scope dùng dấu gạch chéo cuối phù hợp với ranh giới path.
- [ ] Không mở rộng scope hơn nhu cầu thực tế.
- [ ] Service-Worker-Allowed được đặt trên response của script khi cần.
- [ ] Giá trị header chỉ mở rộng đến mức được review.
- [ ] Đã phân biệt scope client với URL request trong fetch handler.
- [ ] Fetch handler có allowlist phù hợp về origin, method và path.
- [ ] Đã kiểm tra registration chồng lấn và longest matching scope.
- [ ] Đã kiểm tra controller, clients.claim và navigation sau activation.
- [ ] Đã kiểm tra update, unregister và các tab đang mở.
- [ ] Không coi scope là ranh giới bảo mật giữa ứng dụng cùng origin.
- [ ] CSP worker-src và nguồn script được kiểm soát.
- [ ] Đã kiểm thử trên production path, reverse proxy và CDN.

## 16. Câu hỏi tự kiểm tra

**1. Worker scope là gì?**

Là URL scope gắn với registration, xác định những client URL nào có thể được Service Worker điều khiển.

**2. Scope mặc định được xác định từ đâu?**

Từ thư mục chứa Service Worker script, không phải thư mục của trang gọi register().

**3. Script ở /shop/sw.js có scope mặc định là gì?**

`/shop/`.

**4. Service-Worker-Allowed dùng để làm gì?**

Cho phép server mở rộng giới hạn scope tối đa so với thư mục chứa script. Header phải nằm trong response của Service Worker script.

**5. Vì sao nên dùng /app/ thay vì /app?**

Vì scope matching theo tiền tố URL; /app có thể khớp /application. Dấu gạch chéo cuối giúp thể hiện ranh giới path mong muốn.

**6. Scope có lọc mọi URL fetch theo path không?**

Không. Scope xác định client được điều khiển. Fetch từ client đó có thể có request URL ngoài path scope; fetch handler phải tự lọc nếu cần.

**7. Nếu nhiều scope cùng khớp một client thì sao?**

Trình duyệt chọn registration có scope khớp cụ thể nhất, tức URL scope dài nhất trong các scope khớp.

**8. Đăng ký thành công có nghĩa trang hiện tại đã có controller không?**

Không nhất thiết. Trang hiện tại có thể cần navigation/reload; worker active có thể dùng clients.claim() để nhận client phù hợp.

**9. Scope riêng có cô lập hai ứng dụng cùng origin không?**

Không. Chúng vẫn cùng origin và có thể chia sẻ cookie, storage và các quyền cùng origin.

**10. Khi nào cần Service-Worker-Allowed?**

Khi script đặt trong thư mục con nhưng ứng dụng thật sự cần scope rộng hơn thư mục đó, và server đã cho phép phạm vi tối đa phù hợp.

## Ghi nhớ

Worker scope xác định client URL nào được điều khiển bởi một Service Worker registration. Scope mặc định theo thư mục chứa script; muốn mở rộng phải có Service-Worker-Allowed trong response của script. Matching dựa trên tiền tố URL nên cần chọn path và dấu gạch chéo cuối cẩn thận. Scope không phải allowlist cho mọi request fetch và cũng không tạo ranh giới bảo mật giữa ứng dụng cùng origin. Hãy chọn scope nhỏ nhất, kiểm tra registration chồng lấn và xác minh controller trên các URL thực tế.

## Tài liệu tham khảo

- [MDN: ServiceWorkerContainer.register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register)
- [MDN: Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)
- [MDN: Service-Worker-Allowed header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Service-Worker-Allowed)
- [MDN: ServiceWorkerRegistration.scope](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/scope)
- [W3C: Service Workers specification](https://www.w3.org/TR/service-workers/)
