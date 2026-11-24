# Service worker registration

> **Chương:** Service worker  
> **Chủ đề:** Service worker registration  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích điều kiện bảo mật để đăng ký Service Worker.
2. Dùng `navigator.serviceWorker.register()` với URL script và scope phù hợp.
3. Phân tích quan hệ giữa vị trí file worker, phạm vi kiểm soát và header `Service-Worker-Allowed`.
4. Đọc trạng thái registration và vòng đời `installing`, `waiting`, `active`.
5. Theo dõi worker controller, sự kiện `updatefound` và kiểm tra phiên bản mới.
6. Chọn `type` và `updateViaCache` theo cách đóng gói script.
7. Hủy đăng ký đúng cách và hiểu vì sao Cache Storage vẫn còn.
8. Bảo vệ endpoint script worker, scope và nội dung mà worker được phép cache.

## 1. Service Worker registration là gì?

Service Worker là một worker chạy trong browser, tách khỏi trang web và có thể nhận các sự kiện như install, activate, fetch, message và push. Browser quản lý vòng đời worker; nó có thể dừng worker khi không hoạt động rồi khởi động lại khi có sự kiện cần xử lý.

**Registration** là đối tượng browser lưu để liên kết một script Service Worker với một phạm vi URL (scope) trên cùng origin. Khi đăng ký thành công, browser tải script, cài đặt worker và kích hoạt nó theo vòng đời. Worker đang active có thể điều khiển các client nằm trong scope, ví dụ tab hoặc trang đang mở.

Đăng ký không đồng nghĩa worker lập tức kiểm soát trang hiện tại. Trang vừa tải lần đầu có thể chưa có controller; sau khi worker activate và claim client, hoặc sau lần điều hướng/tải lại tiếp theo, trang mới được điều khiển.

Ví dụ tối thiểu:

```js
if ('serviceWorker' in navigator) {
  const registration = await navigator.serviceWorker.register('/sw.js');
  console.log('Scope:', registration.scope);
}
```

Registration được browser lưu theo origin và scope. Khi ứng dụng gọi lại register với cùng script và scope, browser thường tái sử dụng registration hiện có và kiểm tra cập nhật thay vì tạo một worker độc lập mới cho mỗi lần gọi.

Service Worker không phải tiến trình chạy liên tục. Không dùng biến global trong worker để lưu trạng thái lâu dài; browser có thể terminate worker bất cứ lúc nào khi không có event đang xử lý. Dữ liệu cần bền vững nên đặt trong Cache Storage hoặc IndexedDB với thiết kế phù hợp.

Worker chạy trong global scope riêng, thường dùng đối tượng `self`; nó không có `window`, `document` hoặc `localStorage` như trang. Vì vậy, không truy cập DOM trực tiếp từ worker. Trang và worker trao đổi qua message, còn dữ liệu cần chia sẻ phải đi qua API phù hợp như IndexedDB hoặc Cache Storage.

## 2. Điều kiện để đăng ký

### 2.1. Secure context

Service Worker chỉ hoạt động trong secure context. Website production cần HTTPS với certificate hợp lệ. Các địa chỉ loopback như `http://localhost` được browser hiện đại xem là đáng tin cậy cho phát triển local.

| URL | Khả năng đăng ký |
|---|---|
| `https://app.example.test` | Có, nếu certificate hợp lệ và browser hỗ trợ |
| `http://localhost:3000` | Thường được phép trong môi trường phát triển |
| `http://127.0.0.1:3000` | Thường được xem là loopback đáng tin cậy |
| `http://192.168.1.20` | Thông thường không phải secure context |
| `file:///C:/project/index.html` | Không phải môi trường triển khai Service Worker thông thường |

Kiểm tra nhanh:

```js
console.log(window.isSecureContext);
console.log('serviceWorker' in navigator);
```

Nếu API không tồn tại, hãy kiểm tra secure context, browser support và chính sách của môi trường trước khi điều tra code worker.

### 2.2. Script phải cùng origin

URL script Service Worker phải cùng origin với trang đăng ký. Origin gồm scheme, hostname và port. Một trang tại `https://app.example.test` không thể đăng ký worker từ `https://cdn.example.test/sw.js` hoặc một port khác.

Các ví dụ:

| Trang đăng ký | Script | Kết quả |
|---|---|---|
| `https://app.example.test` | `https://app.example.test/sw.js` | Cùng origin |
| `https://app.example.test` | `https://app.example.test:8443/sw.js` | Khác origin do port |
| `https://app.example.test` | `http://app.example.test/sw.js` | Khác origin do scheme |
| `https://app.example.test` | `https://cdn.example.test/sw.js` | Khác origin do hostname |

Không lấy URL worker từ query string, nội dung CMS hoặc dữ liệu do người dùng kiểm soát. Hãy dùng đường dẫn cố định trong code và phục vụ script từ origin đáng tin cậy. Worker có quyền xử lý request của các trang trong scope; đăng ký nhầm script có thể ảnh hưởng rộng tới ứng dụng.

### 2.3. Response phải là JavaScript hợp lệ

Browser phải tải được script worker từ URL đã đăng ký. Kiểm tra:

- Response thành công và nội dung thực sự là JavaScript.
- `Content-Type` là MIME JavaScript phù hợp, ví dụ `text/javascript` hoặc `application/javascript`.
- Server không trả HTML của SPA fallback cho URL `/sw.js`.
- Không redirect script sang origin khác.
- URL không bị CDN hoặc reverse proxy thay nội dung ngoài dự kiến.

Một lỗi phổ biến là route worker không tồn tại nhưng server trả `index.html` với status 200. Network có thể cho thấy request thành công, nhưng browser từ chối cài đặt vì MIME type hoặc nội dung không phải script.

## 3. Đăng ký bằng navigator.serviceWorker.register()

Phương thức `register()` nhận URL script và một đối tượng options:

```js
const registration = await navigator.serviceWorker.register(
  '/sw.js',
  {
    scope: '/',
    type: 'classic',
    updateViaCache: 'imports',
  }
);
```

Các option quan trọng:

| Option | Giá trị | Ý nghĩa |
|---|---|---|
| `scope` | URL path cùng origin | Giới hạn các client mà registration có thể điều khiển |
| `type` | `classic` hoặc `module` | Chọn classic worker hoặc module worker; mặc định là `classic` |
| `updateViaCache` | `all`, `imports`, `none` | Điều khiển cách HTTP cache được dùng khi kiểm tra script worker và các script import |

`register()` trả về Promise resolve thành `ServiceWorkerRegistration`. Promise này không có nghĩa mọi client đã được worker điều khiển. Hãy đọc `registration.installing`, `registration.waiting`, `registration.active` và `navigator.serviceWorker.controller` để hiểu trạng thái hiện tại.

### 3.1. URL script tương đối và tuyệt đối

Có thể truyền URL tương đối:

```js
await navigator.serviceWorker.register('/sw.js');
```

Hoặc tạo URL từ origin hiện tại:

```js
const workerUrl = new URL('/sw.js', window.location.origin);
await navigator.serviceWorker.register(workerUrl);
```

Không ghép chuỗi từ input tùy ý. URL cần được kiểm tra trước khi đăng ký; việc dùng path cố định giúp review và deploy dễ hơn.

### 3.2. Đăng ký lặp lại

Đặt lời gọi register trong luồng khởi tạo ứng dụng, không tạo scope ngẫu nhiên mỗi lần render component. Gọi lặp cùng scope/script thường được browser xử lý như kiểm tra registration hiện có và cập nhật nếu cần, nhưng nhiều lời gọi không cần thiết làm luồng khởi tạo khó quan sát.

Ví dụ khởi tạo có kiểm tra:

```js
async function registerAppWorker() {
  if (!('serviceWorker' in navigator)) {
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register('/sw.js', {
      scope: '/',
      updateViaCache: 'none',
    });

    console.log('Registered scope:', registration.scope);
    return registration;
  } catch (error) {
    console.error('Service Worker registration failed:', error);
    return null;
  }
}
```

Không nuốt lỗi hoàn toàn trong production. Ghi nhận loại lỗi và thông tin triển khai cần thiết, nhưng không ghi token, cookie hoặc dữ liệu người dùng vào log.

## 4. Scope quyết định worker kiểm soát URL nào

Scope là URL path trên cùng origin. Worker chỉ có thể điều khiển các client có URL nằm trong phạm vi scope của registration. Khi nhiều scope cùng khớp, registration có scope path cụ thể hơn (dài hơn) được ưu tiên.

Ví dụ:

| Script URL | Scope mặc định | URL thường nằm trong phạm vi |
|---|---|---|
| `/sw.js` | `/` | `/`, `/products/1`, `/account/` |
| `/app/sw.js` | `/app/` | `/app/`, `/app/orders/` |
| `/admin/sw.js` | `/admin/` | `/admin/`, `/admin/users/` |

Nếu script ở `/app/sw.js`, scope mặc định là `/app/`. Nó không tự điều khiển `/` hoặc `/admin/`.

### 4.1. Scope không phải đường dẫn của file script

Có thể chỉ định scope hẹp hơn:

```js
await navigator.serviceWorker.register('/sw.js', {
  scope: '/shop/',
});
```

Trong ví dụ này, script nằm ở root nhưng chỉ điều khiển các URL dưới `/shop/`. Cách này hữu ích khi một origin host nhiều ứng dụng độc lập.

### 4.2. Mở rộng scope bằng Service-Worker-Allowed

Theo mặc định, scope tối đa bị giới hạn bởi thư mục chứa script. Server có thể cho phép scope rộng hơn bằng response header `Service-Worker-Allowed` trên chính response của file worker.

Ví dụ script ở `/assets/sw.js` nhưng cần scope `/`:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript
Service-Worker-Allowed: /
```

Sau đó:

```js
await navigator.serviceWorker.register('/assets/sw.js', {
  scope: '/',
});
```

Header này chỉ mở rộng giới hạn scope tối đa mà browser cho phép; nó không cấp quyền cross-origin và không vượt qua secure-context requirement. Chỉ mở rộng khi ứng dụng thật sự cần worker quản lý các URL đó.

### 4.3. Chọn scope theo ranh giới ứng dụng

Không đăng ký scope `/` theo thói quen nếu worker chỉ phục vụ một ứng dụng nằm dưới `/app/`. Một worker ở scope rộng có thể nhận fetch event từ nhiều route hơn, làm tăng tác động của lỗi cache hoặc logic định tuyến.

Hãy xác định:

- Những trang nào cần được điều khiển?
- Các route đăng nhập, quản trị và thanh toán có nên đi qua cùng worker không?
- Worker có thể phục vụ nhầm HTML/cache của ứng dụng khác trên cùng origin không?
- Có route nào cần chính sách cache hoặc cập nhật riêng không?

Scope là ranh giới định tuyến, không phải ranh giới authorization. Server vẫn phải xác thực và phân quyền cho mọi request.

## 5. Registration và vòng đời worker

Một registration có thể chứa worker đang cài đặt, đang chờ hoặc đang active. Một worker riêng có các state:

| State | Ý nghĩa |
|---|---|
| `installing` | Browser đang cài worker mới và xử lý sự kiện `install` |
| `installed` | Cài đặt hoàn tất; worker mới có thể đang chờ activate |
| `activating` | Browser đang chạy sự kiện `activate` |
| `activated` | Worker đã active và có thể xử lý event cho client được điều khiển |
| `redundant` | Worker không còn được sử dụng, ví dụ cài đặt thất bại hoặc bị thay thế |

Các thuộc tính registration thường được kiểm tra:

- `registration.installing`
- `registration.waiting`
- `registration.active`
- `registration.scope`
- `registration.updateViaCache`

### 5.1. install

Khi script mới được cài, browser phát sự kiện `install`. Worker có thể dùng `event.waitUntil()` để báo browser chờ hoàn tất công việc cần thiết, ví dụ tạo cache shell tối thiểu.

```js
self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open('app-shell-v1');
    await cache.addAll(['/', '/offline.html']);
  })());
});
```

Nếu Promise truyền vào `waitUntil()` reject, install có thể thất bại và worker trở thành `redundant`. Chỉ pre-cache tài nguyên cần thiết; một file sai đường dẫn hoặc response lỗi có thể làm hỏng toàn bộ bước cài đặt.

### 5.2. waiting và cập nhật phiên bản

Khi đã có worker active, một worker mới có thể cài xong nhưng ở trạng thái waiting trong khi các client còn được worker cũ điều khiển. Browser chờ để tránh thay worker giữa chừng làm các trang đang mở dùng lẫn logic hoặc cache không tương thích.

Đây là hành vi bình thường. Không nên tự động gọi `skipWaiting()` cho mọi bản cập nhật nếu phiên bản mới không tương thích với trang đang chạy.

Nếu sản phẩm có nút “Cập nhật ứng dụng”, hãy thông báo người dùng và phối hợp reload khi phiên bản mới sẵn sàng. Trước khi activate ngay, bảo đảm API, cache schema và HTML/JS cũ có thể hoạt động với nhau.

### 5.3. activate

Khi worker mới được phép active, browser phát sự kiện `activate`. Đây là thời điểm phù hợp để dọn cache phiên bản cũ hoặc thực hiện migration có kiểm soát.

```js
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((key) => key.startsWith('app-shell-') && key !== 'app-shell-v2')
        .map((key) => caches.delete(key))
    );
    await self.clients.claim();
  })());
});
```

`clients.claim()` yêu cầu worker active nhận quyền điều khiển các client hiện có nằm trong scope. Trang có thể nhận sự kiện `controllerchange`. Không dùng claim để bỏ qua kiểm thử tương thích; một trang đang chạy code cũ có thể bắt đầu gửi request qua worker mới.

### 5.4. ready và controller

`navigator.serviceWorker.ready` trả Promise chờ một registration active có thể dùng cho trang hiện tại:

```js
const registration = await navigator.serviceWorker.register('/sw.js');
const readyRegistration = await navigator.serviceWorker.ready;

console.log('Active worker:', readyRegistration.active?.state);
console.log('Current controller:', navigator.serviceWorker.controller);
```

`ready` không phải timeout hay trạng thái lỗi; Promise có thể tiếp tục pending nếu chưa có active worker phù hợp. `navigator.serviceWorker.controller` là worker hiện đang điều khiển document. Giá trị này có thể là `null` trong lần tải đầu trước khi worker kiểm soát client.

Theo dõi thay đổi controller:

```js
navigator.serviceWorker.addEventListener('controllerchange', () => {
  console.log('Document controller changed');
});
```

Không dùng `registration.active !== null` để kết luận trang hiện tại đã được kiểm soát. Hãy kiểm tra `navigator.serviceWorker.controller`.

## 6. Theo dõi registration và update

### 6.1. updatefound và statechange

Sự kiện `updatefound` của registration báo rằng một worker mới bắt đầu cài đặt. Có thể theo dõi state của worker đó:

```js
function observeRegistration(registration) {
  const logWorker = (worker) => {
    if (!worker) return;
    console.log('Worker state:', worker.state);
    worker.addEventListener('statechange', () => {
      console.log('Worker state changed:', worker.state);
    });
  };

  logWorker(registration.installing);
  logWorker(registration.waiting);
  logWorker(registration.active);

  registration.addEventListener('updatefound', () => {
    logWorker(registration.installing);
  });
}
```

State có thể thay đổi nhanh. UI nên hiển thị trạng thái có ý nghĩa như “Đang cài đặt”, “Có bản cập nhật đang chờ” hoặc “Đã sẵn sàng”, thay vì phụ thuộc vào một lần đọc duy nhất.

### 6.2. Chủ động kiểm tra update

Browser tự kiểm tra cập nhật theo lịch và trong một số điều kiện như điều hướng tới trang nằm trong scope. Ứng dụng cũng có thể yêu cầu kiểm tra:

```js
const registration = await navigator.serviceWorker.getRegistration('/');

if (registration) {
  await registration.update();
}
```

`update()` kích hoạt quy trình kiểm tra script mới. Nó không bảo đảm luôn có phiên bản mới và không có nghĩa worker mới đã active ngay khi Promise resolve.

Không gọi update liên tục theo timer ngắn. Việc kiểm tra quá thường xuyên làm tăng request và có thể tạo tải không cần thiết cho server.

### 6.3. HTTP cache và updateViaCache

`updateViaCache` quyết định browser sử dụng HTTP cache thế nào khi kiểm tra worker script và các script được import:

| Giá trị | Script chính | Script import |
|---|---|---|
| `all` | Có thể dùng HTTP cache | Có thể dùng HTTP cache |
| `imports` (mặc định) | Không dùng HTTP cache | Có thể dùng HTTP cache |
| `none` | Không dùng HTTP cache | Không dùng HTTP cache |

Ví dụ:

```js
await navigator.serviceWorker.register('/sw.js', {
  updateViaCache: 'none',
});
```

Với script worker chính, server thường nên trả `Cache-Control: no-cache` để browser có thể revalidate khi kiểm tra update. Điều này khác `no-store`: no-cache cho phép lưu nhưng yêu cầu kiểm tra lại trước khi dùng; no-store yêu cầu không lưu response trong HTTP cache.

Không nhầm HTTP cache của file script với Cache Storage do code worker quản lý. Hai cơ chế có vòng đời và API khác nhau.

## 7. Classic worker, module worker và import

Mặc định, `register()` dùng `type: 'classic'`. Classic worker có thể dùng `importScripts()` để nạp script bổ sung.

```js
await navigator.serviceWorker.register('/sw.js', {
  type: 'classic',
});
```

Nếu dự án đóng gói worker theo ES module, có thể đăng ký:

```js
await navigator.serviceWorker.register('/sw.js', {
  type: 'module',
});
```

Module worker sử dụng cú pháp import của JavaScript module. Kiểm tra browser support, đường dẫn import và cách build/deploy trước khi chuyển type. Không trộn `importScripts()` với module worker.

Dù dùng classic hay module, script worker vẫn phải tuân thủ yêu cầu secure context, same-origin và MIME type. Các file import cũng cần được phục vụ đúng nội dung và cập nhật đồng bộ với worker chính.

## 8. Hủy đăng ký và dọn dữ liệu

`registration.unregister()` yêu cầu browser hủy registration:

```js
const registration = await navigator.serviceWorker.getRegistration('/');

if (registration) {
  const removed = await registration.unregister();
  console.log('Unregistered:', removed);
}
```

Giá trị trả về cho biết registration có được hủy hay không. Hủy registration không đồng nghĩa worker lập tức biến mất khỏi các tab đang mở. Các client hiện tại có thể tiếp tục được worker đã active điều khiển cho tới khi chúng đóng hoặc rời phạm vi; browser sẽ không dùng registration đã hủy để điều khiển các client mới theo cách thông thường.

Unregister cũng không xóa Cache Storage. Nếu ứng dụng cần dọn cache, phải làm riêng và giới hạn đúng prefix do ứng dụng sở hữu:

```js
const keys = await caches.keys();

await Promise.all(
  keys
    .filter((key) => key.startsWith('my-app-cache-'))
    .map((key) => caches.delete(key))
);
```

Không xóa toàn bộ cache của origin nếu cùng origin có nhiều ứng dụng. Đặt tên cache có namespace để tránh xóa nhầm dữ liệu của thành phần khác.

## 9. Bảo mật khi đăng ký Service Worker

Service Worker có thể trở thành lớp trung gian cho các request của trang trong scope. Nếu script worker bị thay thế hoặc triển khai sai, nó có thể trả nội dung giả, phục vụ cache cũ, làm lộ dữ liệu hoặc gây gián đoạn ứng dụng.

### 9.1. Bảo vệ script worker

- Phục vụ script từ origin của ứng dụng và URL cố định.
- Không cho người dùng upload hoặc chỉnh sửa file được dùng làm worker script.
- Bảo vệ pipeline build, CDN, reverse proxy và quyền deploy.
- Đặt MIME type JavaScript chính xác.
- Dùng `Cache-Control: no-cache` phù hợp cho script chính để hỗ trợ update check.
- Kiểm soát redirect và đảm bảo endpoint không trả SPA fallback.
- Review mọi thay đổi worker như thay đổi mã chạy ở ranh giới network của ứng dụng.

Một XSS hoặc dependency bị chiếm có thể tạo điều kiện cho attacker thực thi JavaScript cùng origin. Nếu ứng dụng cho phép đăng ký worker từ một đường dẫn mà attacker có thể ghi nội dung, rủi ro có thể kéo dài qua các lần điều hướng. Không phục vụ nội dung upload không tin cậy dưới đường dẫn có thể trở thành worker script.

### 9.2. Giới hạn nguồn worker bằng CSP

CSP có directive `worker-src` để giới hạn nguồn worker script:

```http
Content-Security-Policy: worker-src 'self'
```

Directive này áp dụng cho nguồn worker như Worker, SharedWorker và Service Worker trong browser hỗ trợ. CSP của document cũng cần cho phép script ứng dụng gọi API đăng ký; response của worker có thể có CSP riêng để giới hạn hành vi trong worker global.

`worker-src 'self'` không bảo vệ khỏi script độc hại đã được phép chạy cùng origin nếu origin có một file worker không đáng tin cậy. Hãy kiểm soát nội dung và quyền ghi của endpoint worker ở server.

### 9.3. Không cache dữ liệu nhạy cảm theo cách dùng chung

Worker có thể ghi response vào Cache Storage. Không mặc định cache:

- Response chứa thông tin cá nhân hoặc dữ liệu tài khoản.
- API response phụ thuộc session/cookie hoặc authorization.
- Nội dung quản trị, hóa đơn, thông tin thanh toán.
- Response có token hoặc credential trong body/header.

Nếu buộc phải cache dữ liệu cá nhân, phải có thiết kế phân tách theo người dùng/phiên, chính sách xóa khi logout, xử lý account switch và kiểm tra response trước khi phát lại. Không dùng cache làm nơi lưu access token hoặc refresh token.

### 9.4. Server vẫn là nơi thực thi authorization

Service Worker không thay thế authentication hoặc authorization ở server. Người dùng có thể bỏ qua worker, xóa registration, gọi API trực tiếp hoặc dùng client khác. Mọi endpoint nhạy cảm vẫn phải xác minh session/token và quyền trên mỗi request.

Scope chỉ quyết định URL client nào có thể bị worker điều khiển; nó không cấp quyền đọc dữ liệu server và không phải ranh giới phân quyền.

## 10. Chẩn đoán lỗi registration

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `navigator.serviceWorker` không tồn tại | Trang không ở secure context hoặc browser không hỗ trợ | Kiểm tra `window.isSecureContext`, URL và browser |
| `register()` reject | URL sai, script khác origin, policy chặn hoặc response không hợp lệ | Đọc exception, Console và Network |
| MIME type error | Server trả HTML hoặc content type không phải JavaScript | Kiểm tra response body và `Content-Type` của `/sw.js` |
| Scope bị từ chối | Scope rộng hơn giới hạn thư mục script | Kiểm tra vị trí script và header `Service-Worker-Allowed` |
| Worker không activate | `install` thất bại hoặc Promise trong `waitUntil()` reject | Xem state `redundant`, Console và request pre-cache |
| Worker ở waiting | Client cũ vẫn đang được worker active điều khiển | Kiểm tra tab đang mở và quy trình update |
| Trang không có controller | Worker chưa active/claim hoặc trang nằm ngoài scope | Kiểm tra `navigator.serviceWorker.controller` và `registration.scope` |
| Update không xuất hiện | Script chưa đổi, HTTP cache/CDN giữ bản cũ hoặc browser chưa kiểm tra | Gọi `registration.update()`, kiểm tra response và `updateViaCache` |
| Unregister nhưng worker vẫn chạy ở tab hiện tại | Client cũ vẫn được worker điều khiển | Đóng các tab thuộc scope rồi mở lại |
| Offline page không xuất hiện | Navigation chưa được điều khiển hoặc fallback chưa được cache | Reload sau khi activate, kiểm tra Cache Storage và fetch handler |

### 10.1. Kiểm tra bằng DevTools

Trong Chromium-based browser:

1. Mở DevTools → Application → Service Workers.
2. Xem script URL, scope, trạng thái worker và client đang được điều khiển.
3. Dùng Update hoặc kiểm tra update để xác minh worker mới.
4. Xem Cache Storage để kiểm tra cache do worker tạo.
5. Mở Network, bật Preserve log và kiểm tra request tới script worker.
6. Thử Offline sau khi trang đã được worker điều khiển.
7. Khi debug, dùng Unregister hoặc Clear site data có chủ đích; thao tác này có thể xóa storage khác của origin.

Tên và vị trí mục DevTools có thể khác giữa browser. Hãy phân biệt lỗi đăng ký với lỗi fetch handler: worker có thể đăng ký thành công nhưng logic xử lý request vẫn sai.

## 11. Thực hành: lab Service Worker registration với Node.js

Lab dùng Node.js built-in, không cần package ngoài. Server chạy trên `http://localhost:3000`, một secure context được browser hiện đại cho phép trong môi trường phát triển.

Lab giúp quan sát:

- Đăng ký script `/sw.js` với scope `/`.
- Theo dõi registration, state và controller.
- Kiểm tra bản cập nhật bằng `registration.update()`.
- Hủy registration.
- Cache trang shell và trả trang offline khi navigation không kết nối được server.

### Bước 1 — Tạo file `service-worker-registration-lab.cjs`

```js
const http = require('node:http');

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Service Worker registration lab</title></head><body>',
  '<h1>Service Worker registration lab</h1>',
  '<p>Origin: http://localhost:3000</p>',
  '<button id="register" type="button">Register</button>',
  '<button id="inspect" type="button">Inspect registration</button>',
  '<button id="update" type="button">Check update</button>',
  '<button id="unregister" type="button">Unregister</button>',
  '<button id="clear-cache" type="button">Clear lab cache</button>',
  '<p id="controller">Controller: chưa kiểm tra</p>',
  '<pre id="log"></pre>',
  '<script>',
  "const output = document.querySelector('#log');",
  "const controllerText = document.querySelector('#controller');",
  'let currentRegistration = null;',
  'function log(message) { output.textContent += message + "\\n"; }',
  'function workerState(worker) { return worker ? worker.state : "none"; }',
  'function showController() {',
  "  controllerText.textContent = 'Controller: ' +",
  "    (navigator.serviceWorker.controller ? 'active' : 'none');",
  '}',
  "if ('serviceWorker' in navigator) {",
  "  navigator.serviceWorker.addEventListener('controllerchange', () => {",
  "    showController();",
  "    log('controllerchange');",
  '  });',
  '}',
  'async function inspectRegistration(registration) {',
  '  if (!registration) { log("Không tìm thấy registration."); return; }',
  '  currentRegistration = registration;',
  '  log("scope: " + registration.scope);',
  '  log("installing: " + workerState(registration.installing));',
  '  log("waiting: " + workerState(registration.waiting));',
  '  log("active: " + workerState(registration.active));',
  '  showController();',
  '}',
  "document.querySelector('#register').addEventListener('click', async () => {",
  "  if (!('serviceWorker' in navigator)) {",
  '    log("Browser không hỗ trợ Service Worker.");',
  '    return;',
  '  }',
  '  try {',
  '    const registration = await navigator.serviceWorker.register("/sw.js", {',
  '      scope: "/",',
  '      type: "classic",',
  '      updateViaCache: "none"',
  '    });',
  '    currentRegistration = registration;',
  '    registration.addEventListener("updatefound", () => {',
  '      const worker = registration.installing;',
  '      if (!worker) return;',
  '      log("updatefound: " + worker.state);',
  '      worker.addEventListener("statechange", () => {',
  '        log("worker state: " + worker.state);',
  '      });',
  '    });',
  '    await inspectRegistration(registration);',
  '    const ready = await navigator.serviceWorker.ready;',
  '    log("ready active: " + workerState(ready.active));',
  '    showController();',
  '  } catch (error) {',
  '    log("register failed: " + error.name + " - " + error.message);',
  '  }',
  '});',
  "document.querySelector('#inspect').addEventListener('click', async () => {",
  '  try {',
  '    const registration = await navigator.serviceWorker.getRegistration("/");',
  '    await inspectRegistration(registration);',
  '  } catch (error) { log("inspect failed: " + error.name); }',
  '});',
  "document.querySelector('#update').addEventListener('click', async () => {",
  '  try {',
  '    const registration = currentRegistration ||',
  '      await navigator.serviceWorker.getRegistration("/");',
  '    if (!registration) { log("Chưa có registration."); return; }',
  '    await registration.update();',
  '    log("Đã yêu cầu kiểm tra update.");',
  '    await inspectRegistration(registration);',
  '  } catch (error) { log("update failed: " + error.name); }',
  '});',
  "document.querySelector('#unregister').addEventListener('click', async () => {",
  '  try {',
  '    const registration = currentRegistration ||',
  '      await navigator.serviceWorker.getRegistration("/");',
  '    if (!registration) { log("Không có registration để hủy."); return; }',
  '    const removed = await registration.unregister();',
  '    log("unregister returned: " + removed);',
  '    log("Tab hiện tại có thể vẫn được worker cũ điều khiển cho tới khi rời scope.");',
  '  } catch (error) { log("unregister failed: " + error.name); }',
  '});',
  "document.querySelector('#clear-cache').addEventListener('click', async () => {",
  '  const keys = await caches.keys();',
  '  const labKeys = keys.filter((key) => key.startsWith("registration-lab-"));',
  '  await Promise.all(labKeys.map((key) => caches.delete(key)));',
  '  log("Đã xóa lab caches: " + labKeys.join(", "));',
  '});',
  'showController();',
  '</script>',
  '</body></html>',
].join('\n');

const worker = [
  'const CACHE_NAME = "registration-lab-v1";',
  '',
  'self.addEventListener("install", (event) => {',
  '  event.waitUntil((async () => {',
  '    const cache = await caches.open(CACHE_NAME);',
  '    await cache.addAll(["/", "/offline.html"]);',
  '  })());',
  '});',
  '',
  'self.addEventListener("activate", (event) => {',
  '  event.waitUntil((async () => {',
  '    const keys = await caches.keys();',
  '    await Promise.all(keys',
  '      .filter((key) => key.startsWith("registration-lab-") && key !== CACHE_NAME)',
  '      .map((key) => caches.delete(key)));',
  '    await self.clients.claim();',
  '  })());',
  '});',
  '',
  'self.addEventListener("fetch", (event) => {',
  '  if (event.request.mode !== "navigate") return;',
  '  const requestUrl = new URL(event.request.url);',
  '  if (requestUrl.origin !== self.location.origin) return;',
  '  event.respondWith((async () => {',
  '    try {',
  '      return await fetch(event.request);',
  '    } catch {',
  '      const cached = await caches.match("/offline.html");',
  '      return cached || new Response("Offline", {',
  '        status: 503,',
  '        headers: { "Content-Type": "text/plain; charset=utf-8" }',
  '      });',
  '    }',
  '  })());',
  '});',
].join('\n');

const offlinePage = [
  '<!doctype html>',
  '<html lang="vi"><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Offline</title><body>',
  '<h1>Đang offline</h1>',
  '<p>Service Worker đã trả trang dự phòng từ Cache Storage.</p>',
  '<a href="/">Thử tải lại</a>',
  '</body></html>',
].join('\n');

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method !== 'GET') {
    res.writeHead(405);
    return res.end('Method not allowed');
  }

  if (url.pathname === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    return res.end(page);
  }

  if (url.pathname === '/sw.js') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-cache',
    });
    return res.end(worker);
  }

  if (url.pathname === '/offline.html') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    return res.end(offlinePage);
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node service-worker-registration-lab.cjs
```

Mở `http://localhost:3000`. Nếu cổng 3000 đang được sử dụng, đổi cổng trong server và các URL tương ứng trong ví dụ worker/page.

### Bước 3 — Đăng ký và quan sát scope

1. Nhấn **Register**.
2. Quan sát log `scope` phải là `http://localhost:3000/`.
3. Quan sát các state installing, waiting và active khi browser cài worker.
4. Sau activate, `controllerchange` có thể xuất hiện vì worker gọi `clients.claim()`.
5. Nhấn **Inspect registration** để đọc lại trạng thái và controller.

Nếu lần đầu `controller` là none, chờ activate hoặc tải lại trang. Registration có thể đã tồn tại dù document hiện tại chưa được điều khiển.

### Bước 4 — Kiểm tra offline fallback

1. Đăng ký worker và đợi active.
2. Mở DevTools → Network, bật Offline.
3. Tải lại trang trong scope `/`.
4. Browser phải nhận trang `/offline.html` từ Cache Storage.
5. Tắt Offline và tải lại để trở về trang lab.

Nếu offline fallback không xuất hiện, xác minh trang đã có controller trước khi chuyển Offline và bước install đã cache thành công cả `/` lẫn `/offline.html`.

### Bước 5 — Kiểm tra update

Đổi chuỗi `registration-lab-v1` trong worker thành `registration-lab-v2`, lưu file lab và khởi động lại Node server để endpoint `/sw.js` trả nội dung mới. Sau đó nhấn **Check update**. Browser sẽ tải và cài phiên bản mới. Quan sát `updatefound` và state change. Nếu còn client cũ, worker mới có thể ở waiting.

Lab không tự gọi `skipWaiting()`: người học có thể thấy hành vi chờ update và hiểu vì sao browser không thay worker đang điều khiển các tab ngay lập tức.

### Bước 6 — Unregister và dọn cache

1. Nhấn **Unregister** để hủy registration.
2. Tab hiện tại có thể vẫn được worker cũ điều khiển; đóng tab hoặc tải lại sau khi worker không còn client.
3. Nhấn **Clear lab cache** để xóa các cache có prefix riêng của lab.
4. Kiểm tra Application → Service Workers và Cache Storage để xác nhận trạng thái.

Unregister và xóa cache là hai thao tác riêng. Không xóa mọi cache của origin trong môi trường có ứng dụng khác cùng chạy.

## 12. Checklist triển khai registration

- [ ] Trang được phục vụ trong secure context.
- [ ] Script worker dùng URL cố định và cùng origin với trang đăng ký.
- [ ] Server trả JavaScript với MIME type chính xác, không trả SPA fallback.
- [ ] Redirect và CDN không thay đổi nội dung worker ngoài dự kiến.
- [ ] Scope chỉ bao phủ các route cần được điều khiển.
- [ ] Nếu mở rộng scope vượt thư mục script, `Service-Worker-Allowed` được cấu hình có chủ đích.
- [ ] Registration được gọi trong luồng khởi tạo phù hợp, không tạo scope ngẫu nhiên.
- [ ] UI phân biệt registration active với controller của document hiện tại.
- [ ] Install dùng `waitUntil()` và chỉ pre-cache tài nguyên bắt buộc.
- [ ] Update được kiểm thử với tab cũ, worker waiting và tương thích phiên bản.
- [ ] `updateViaCache` và HTTP cache headers được chọn có chủ đích.
- [ ] Unregister không bị nhầm với xóa Cache Storage.
- [ ] CSP `worker-src` giới hạn nguồn worker phù hợp.
- [ ] Endpoint worker không cho người dùng hoặc nội dung upload kiểm soát.
- [ ] Cache không chứa token hoặc response cá nhân dùng chung ngoài thiết kế.
- [ ] Server vẫn xác thực và phân quyền độc lập với Service Worker.

## 13. Câu hỏi tự kiểm tra

**1.** Service Worker registration liên kết những thành phần nào?  
**Trả lời:** Script Service Worker với một scope URL trên cùng origin, để browser quản lý vòng đời và các client có thể được điều khiển.

**2.** Vì sao Service Worker cần secure context?  
**Trả lời:** Worker có thể can thiệp request của trang trong scope nên browser yêu cầu kênh và môi trường tin cậy; HTTPS và localhost là các trường hợp thường dùng.

**3.** URL script khác origin có đăng ký được không?  
**Trả lời:** Không. Script worker phải cùng origin với document đăng ký.

**4.** Scope mặc định của `/assets/sw.js` là gì?  
**Trả lời:** `/assets/`; muốn scope rộng hơn cần cấu hình header `Service-Worker-Allowed` phù hợp.

**5.** `Service-Worker-Allowed` làm gì?  
**Trả lời:** Đặt giới hạn scope tối đa mà script được phép đăng ký; nó không cấp quyền cross-origin.

**6.** `registration.active` khác `navigator.serviceWorker.controller` thế nào?  
**Trả lời:** active là worker active của registration; controller là worker hiện đang điều khiển document cụ thể.

**7.** Vì sao worker mới có thể ở trạng thái waiting?  
**Trả lời:** Worker cũ vẫn đang điều khiển client mở; browser chờ client cũ rời đi để tránh thay worker giữa chừng.

**8.** `updateViaCache` điều khiển điều gì?  
**Trả lời:** Cách HTTP cache được sử dụng khi kiểm tra script Service Worker chính và các script được import.

**9.** Unregister có xóa Cache Storage không?  
**Trả lời:** Không. Hủy registration và xóa cache là hai thao tác độc lập.

**10.** Service Worker scope có thay thế authorization ở server không?  
**Trả lời:** Không. Scope chỉ xác định client URL nào có thể được worker điều khiển; server vẫn phải xác thực và phân quyền từng request.

## Tổng kết

Service Worker registration là bước browser liên kết một script cùng origin với scope URL để quản lý vòng đời worker và các client được điều khiển. Đăng ký cần secure context, script JavaScript hợp lệ và scope nằm trong giới hạn cho phép. Hãy theo dõi installing/waiting/active, phân biệt registration với controller, kiểm soát update và cache, cũng như hiểu rằng unregister không tự xóa Cache Storage. Vì worker có thể can thiệp request trong phạm vi của nó, script, scope và cache cần được bảo vệ như một thành phần bảo mật quan trọng; authorization vẫn phải được thực thi ở server.
