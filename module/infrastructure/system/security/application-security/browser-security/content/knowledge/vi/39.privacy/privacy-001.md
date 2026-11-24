# Browser privacy

> **Chương:** Privacy  
> **Chủ đề:** Browser privacy  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định những loại dữ liệu browser và website có thể thu thập trong một phiên truy cập.
2. Giải thích tracking bằng cookie, storage, URL decoration, referrer và browser fingerprinting.
3. Phân biệt first-party context, third-party context, origin, site và storage partition.
4. Đánh giá tác động riêng tư của cookie, localStorage, IndexedDB, Cache Storage và Service Worker.
5. Hiểu giới hạn của private browsing, VPN, tracking protection và các tín hiệu opt-out.
6. Cấu hình privacy headers, cookie attributes và Permissions Policy phù hợp.
7. Thiết kế trải nghiệm xin quyền, lưu trữ và phân tích dữ liệu theo nguyên tắc data minimization.
8. Kiểm tra bề mặt thông tin browser mà một trang có thể quan sát mà không gửi dữ liệu ra ngoài.

## 1. Browser privacy là gì?

Browser privacy là khả năng kiểm soát dữ liệu được tạo ra, lưu trữ, chia sẻ và quan sát trong quá trình người dùng truy cập website. Dữ liệu này có thể giúp website duy trì đăng nhập, ghi nhớ lựa chọn hoặc cung cấp chức năng; đồng thời có thể được dùng để theo dõi hành vi, liên kết nhiều phiên truy cập hoặc suy đoán đặc điểm thiết bị.

Một website thường nhìn thấy nhiều tín hiệu hơn nội dung người dùng chủ động nhập. Ví dụ: địa chỉ IP ở phía server, thời điểm request, URL và referrer, cookie được browser gửi, kích thước màn hình, ngôn ngữ, múi giờ, khả năng API và trạng thái permission. Một số tín hiệu chỉ xuất hiện khi người dùng cấp quyền hoặc khi trang gọi API tương ứng.

Privacy không chỉ là ẩn danh. Người dùng có thể muốn giữ tài khoản đăng nhập nhưng không muốn bị theo dõi qua website khác; muốn cho phép camera trong một cuộc gọi nhưng không muốn website dùng microphone; hoặc muốn xóa lịch sử và dữ liệu của một site mà không xóa dữ liệu các site khác.

### 1.1. Các bên tham gia

| Bên | Dữ liệu có thể quan sát hoặc xử lý |
|---|---|
| Website first-party | Request, cookie của site, dữ liệu người dùng nhập, tương tác trong trang và storage được phép truy cập |
| Third-party script | Những dữ liệu mà script chạy trong trang được phép đọc, cùng các request mà nó tạo ra |
| Third-party embedded service | Request từ iframe, pixel, font, video hoặc widget; cookie và storage phụ thuộc browser policy |
| Browser | Cookie, storage, permission, lịch sử, cache, site isolation và các cơ chế tracking protection |
| Network/ISP | Metadata kết nối như IP đích, thời điểm và lượng dữ liệu; nội dung HTTPS được mã hóa trên đường truyền |
| Website server/CDN | IP nguồn nhìn thấy ở đầu kết nối, headers, URL, request timing và dữ liệu được gửi tới server |
| Extension hoặc phần mềm trên thiết bị | Có thể quan sát hoặc thay đổi nội dung tùy quyền được cấp và mức kiểm soát thiết bị |

Không phải mọi bên đều nhìn thấy cùng một dữ liệu. Same-Origin Policy giới hạn việc script đọc dữ liệu giữa các origin; cookie policy và storage partitioning giới hạn một số trạng thái cross-site; HTTPS bảo vệ nội dung trên đường truyền nhưng không che toàn bộ metadata mạng.

### 1.2. Origin, site và third-party context

Origin được xác định bởi scheme, hostname và port. Site là khái niệm rộng hơn được dùng trong các cơ chế như SameSite cookie; browser hiện đại thường xác định schemeful site dựa trên scheme và registrable domain. Vì vậy, hai subdomain có thể khác origin nhưng cùng site.

Ví dụ:

| URL A | URL B | Cùng origin? | Cùng site? |
|---|---|---:|---:|
| https://shop.example.test | https://shop.example.test/cart | Có | Có |
| https://shop.example.test | https://api.example.test | Không | Thường có |
| https://shop.example.test | https://shop.example.net | Không | Không |
| https://shop.example.test | http://shop.example.test | Không | Không trong schemeful-site model |

First-party và third-party phụ thuộc ngữ cảnh top-level site. Một dịch vụ analytics được nhúng trong nhiều website có thể hoạt động ở third-party context; khi người dùng truy cập trực tiếp domain của dịch vụ đó, nó trở thành top-level/first-party context.

Không suy ra rằng hai URL cùng site có thể đọc storage của nhau. Same-Origin Policy vẫn dựa trên origin, còn cookie và một số chính sách privacy dùng khái niệm site.

## 2. Dữ liệu browser có thể để lộ

### 2.1. Request metadata

Mỗi request tới server có thể mang theo:

- IP nguồn mà server hoặc reverse proxy nhìn thấy.
- Thời điểm, tần suất, kích thước và thứ tự request.
- Method, path, query string và một số request headers.
- Cookie phù hợp với domain, path, SameSite, Secure và các điều kiện browser.
- User-Agent hoặc User-Agent Client Hints nếu browser gửi.
- Referrer theo chính sách Referrer-Policy.

HTTPS mã hóa path, query, headers và body giữa browser với điểm kết thúc TLS; tuy nhiên DNS lookup, địa chỉ IP đích, thời điểm và kích thước kết nối vẫn có thể lộ một phần metadata tùy hạ tầng và giao thức. CDN hoặc reverse proxy kết thúc TLS có thể nhìn thấy request đầy đủ.

### 2.2. JavaScript-observable surface

Script trong trang có thể quan sát một số thuộc tính như:

```js
const browserSurface = {
  language: navigator.language,
  languages: navigator.languages,
  platform: navigator.platform,
  userAgent: navigator.userAgent,
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory,
  screen: {
    width: screen.width,
    height: screen.height,
    colorDepth: screen.colorDepth,
  },
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
};

console.table(browserSurface);
```

Đây là ví dụ về bề mặt có thể quan sát, không phải danh sách thuộc tính luôn tồn tại hoặc luôn chính xác. Browser có thể giảm độ chi tiết, trả giá trị chuẩn hóa, bỏ qua thuộc tính hoặc thay đổi theo privacy mode. Không nên dùng các giá trị này làm định danh duy nhất hoặc quyết định quyền truy cập.

Một số API như geolocation, camera, microphone, clipboard hoặc notifications cần permission, user activation hay điều kiện secure context. Việc một API xuất hiện trong object navigator không có nghĩa website đã được cấp quyền sử dụng.

## 3. Tracking bằng cookie và request bên thứ ba

Cookie được thiết kế để website duy trì trạng thái như session, tùy chọn và xác thực. Tracking có thể tận dụng cookie first-party hoặc third-party để liên kết request qua nhiều lần truy cập.

### 3.1. First-party cookie

Cookie first-party được đặt trong ngữ cảnh website người dùng đang truy cập. Nó có thể dùng cho session đăng nhập, giỏ hàng hoặc lựa chọn ngôn ngữ. Cookie vẫn có thể theo dõi hành vi trong chính site đó qua nhiều trang và nhiều phiên.

Các thuộc tính quan trọng:

| Thuộc tính | Tác dụng |
|---|---|
| Secure | Chỉ gửi cookie qua kênh bảo mật phù hợp như HTTPS |
| HttpOnly | Không cho JavaScript đọc cookie qua document.cookie |
| SameSite=Strict/Lax/None | Kiểm soát điều kiện gửi cookie trong ngữ cảnh same-site/cross-site |
| Domain | Xác định host hoặc domain được nhận cookie; tránh mở rộng nếu không cần |
| Path | Giới hạn path mà browser gửi cookie; không phải ranh giới bảo mật mạnh |
| Max-Age / Expires | Giới hạn thời gian tồn tại |
| Partitioned | Yêu cầu cookie được phân vùng theo top-level site trong browser hỗ trợ CHIPS |

Với session cookie nhạy cảm, thường ưu tiên host-only cookie, Secure, HttpOnly và SameSite phù hợp. Prefix __Host- yêu cầu Secure, Path=/ và không có Domain trong browser hỗ trợ; nó giúp giảm rủi ro cookie bị đặt từ subdomain.

### 3.2. Third-party cookie

Third-party cookie được gửi trong request khi domain cookie khác với top-level site đang mở. Tracking service có thể dùng cùng một định danh trên nhiều website nếu browser cho phép và cookie policy đáp ứng điều kiện.

Browser hiện đại có nhiều biện pháp hạn chế third-party tracking: chặn cookie bên thứ ba, phân vùng storage/cookie, giới hạn lifetime hoặc yêu cầu user interaction. Hành vi cụ thể khác nhau theo browser, phiên bản, cài đặt, chế độ riêng tư và các ngoại lệ tương thích. Không giả định third-party cookie luôn hoạt động hoặc đã bị chặn hoàn toàn trên mọi thiết bị.

Nếu một tích hợp phụ thuộc third-party cookie, hãy kiểm tra trên browser mục tiêu và chuẩn bị luồng thay thế có chủ đích. Không khắc phục việc cookie bị chặn bằng cách âm thầm chuyển sang fingerprinting.

### 3.3. Partitioned cookies và CHIPS

CHIPS (Cookies Having Independent Partitioned State) cho phép cookie được đánh dấu Partitioned để browser lưu trạng thái riêng theo top-level site. Một embedded service có thể duy trì trạng thái trong từng website nhúng nó mà không dùng chung một cookie cross-site toàn cục.

Ví dụ minh họa:

```http
Set-Cookie: widget_session=opaque-value; Secure; HttpOnly; SameSite=None; Partitioned; Path=/
```

Partitioned cookie cần Secure và thường dùng SameSite=None để được gửi trong embedded cross-site context. Browser support và các chi tiết triển khai cần được kiểm tra. Partitioning giảm khả năng liên kết người dùng giữa nhiều top-level site, nhưng không tự biến widget thành đáng tin cậy hoặc thay thế authorization.

### 3.4. Redirect tracking và link decoration

Website có thể gắn mã chiến dịch hoặc click identifier vào URL, ví dụ tham số quảng cáo, mã referral hoặc ID liên kết. Khi người dùng đi qua nhiều redirect, các tham số có thể được truyền tiếp và xuất hiện trong log, analytics hoặc referrer.

Biện pháp giảm rủi ro:

- Chỉ giữ tham số cần thiết và xóa chúng sau khi attribution hoàn tất.
- Không đặt email, số điện thoại, session ID hoặc dữ liệu nhạy cảm trong URL.
- Không chuyển tiếp toàn bộ query string sang domain khác.
- Dùng allowlist cho redirect destination.
- Redact identifier khỏi log và analytics khi không cần lưu.

## 4. Browser fingerprinting

Fingerprinting là kỹ thuật kết hợp nhiều thuộc tính thiết bị và browser để tạo tín hiệu có thể phân biệt một browser với nhiều browser khác. Nó có thể hoạt động mà không cần lưu cookie lâu dài.

Các tín hiệu có thể được kết hợp:

- User-Agent, platform và browser feature support.
- Ngôn ngữ, locale và timezone.
- Kích thước màn hình, color depth và device scale.
- Hardware concurrency và memory hints.
- Canvas, WebGL, audio rendering và danh sách font.
- Các khác biệt về API, timing và cách browser render nội dung.

Một thuộc tính riêng lẻ thường không định danh tốt. Sự kết hợp của nhiều thuộc tính có thể làm fingerprint phân biệt hơn; giá trị đó có thể thay đổi sau update, cài font, đổi màn hình, dùng remote desktop hoặc bật privacy protection.

### 4.1. Fingerprint không phải định danh ổn định tuyệt đối

Fingerprint có thể thay đổi giữa các phiên bản browser hoặc thiết bị. Browser có thể giảm entropy bằng cách chuẩn hóa User-Agent, giới hạn Client Hints, giảm độ chính xác của API, thêm noise hoặc yêu cầu permission. Một số biện pháp bảo vệ làm nhiều người dùng có fingerprint giống nhau hơn, giảm khả năng phân biệt.

Không dùng fingerprint để thay thế authentication, session cookie hoặc risk signal có kiểm soát. Nếu dùng để chống gian lận, cần đánh giá độ chính xác, false positive, thời hạn lưu, mục đích xử lý và tác động tới người dùng.

### 4.2. Canvas, WebGL và font enumeration

Canvas hoặc WebGL có thể tạo ra output khác nhau do hệ điều hành, GPU, driver, font và browser. Font enumeration hoặc đo kích thước text cũng có thể góp phần tạo fingerprint. Browser có thể giới hạn một số API, chuẩn hóa output hoặc làm giảm khả năng truy cập trực tiếp.

Website không nên chạy fingerprinting ngầm chỉ vì API có sẵn. Nếu có nhu cầu chống gian lận, hãy dùng tín hiệu tối thiểu, minh bạch về mục đích, giới hạn thời gian giữ và cung cấp cơ chế review khi quyết định ảnh hưởng tới tài khoản.

### 4.3. User-Agent và Client Hints

User-Agent truyền thống có thể chứa thông tin browser và platform nhưng ngày càng được giảm chi tiết để hạn chế fingerprinting. User-Agent Client Hints cung cấp một số thông tin theo cơ chế có cấu trúc; high-entropy hints có thể cần server request và browser policy cho phép.

Không parse User-Agent để suy đoán danh tính hoặc đưa ra quyết định bảo mật. Dùng feature detection và kiểm tra khả năng API trực tiếp; nếu cần Client Hints cho tương thích, chỉ yêu cầu các trường thực sự cần.

## 5. Storage, partitioning và dữ liệu tồn tại trên browser

Website có thể lưu dữ liệu ở nhiều nơi. Xóa cookie không nhất thiết xóa localStorage, IndexedDB, Cache Storage hoặc Service Worker registration. Privacy review phải kiểm kê tất cả nơi lưu trữ và vòng đời của chúng.

| Cơ chế | Dữ liệu thường lưu | Phạm vi và lưu ý |
|---|---|---|
| Cookie | Session ID, preference, feature flag | Browser tự gửi theo domain/path/SameSite; có thể bị giới hạn hoặc partition |
| localStorage | Preference, trạng thái ứng dụng, dữ liệu client | Theo origin; JavaScript cùng origin đọc được; thường tồn tại qua phiên |
| sessionStorage | Trạng thái tạm theo tab | Theo origin và browsing context; thường mất khi tab đóng |
| IndexedDB | Dữ liệu có cấu trúc, offline data | Theo origin; có thể tồn tại lâu và chiếm dung lượng lớn |
| Cache Storage | Request/response do ứng dụng hoặc Service Worker lưu | Theo origin/storage bucket và policy browser; có thể giữ nội dung cũ |
| Service Worker registration | Script và scope worker | Có thể tiếp tục điều khiển client trong scope cho tới khi unregister/clients rời đi |
| HTTP cache | Response cacheable | Được browser quản lý theo HTTP caching rules; không giống Cache Storage |

### 5.1. Storage partitioning

Browser có thể phân vùng storage của embedded third-party theo top-level site. Cùng một widget được nhúng ở hai website khác nhau có thể nhận hai vùng storage riêng, giảm khả năng dùng một ID chung để theo dõi người dùng qua nhiều site.

Partition key và phạm vi partition khác nhau giữa API và browser. Không giả định mọi loại storage có cùng mô hình partitioning. Hãy kiểm tra behavior thực tế với browser, phiên bản và embed context mà sản phẩm hỗ trợ.

### 5.2. Storage Access API

Một số dịch vụ nhúng cần truy cập trạng thái first-party cũ trong third-party context, ví dụ một widget đăng nhập. Storage Access API cung cấp cơ chế để embedded document yêu cầu quyền truy cập cookie/storage không partition trong những điều kiện browser cho phép.

API này không phải cách bỏ qua tracking protection. Browser có thể yêu cầu user gesture, tương tác trước đó hoặc user permission; request có thể bị từ chối. Hãy cung cấp trải nghiệm giải thích rõ ràng và một luồng thay thế nếu người dùng không cấp quyền.

### 5.3. Dữ liệu offline và Service Worker

Service Worker cùng Cache Storage hữu ích cho offline experience, nhưng có thể giữ dữ liệu sau khi người dùng đăng xuất hoặc chuyển tài khoản. Cần xác định:

- Response nào được cache và vì sao.
- Cache có chứa dữ liệu cá nhân, response phụ thuộc session hoặc nội dung tài khoản không.
- Cache được namespace theo ứng dụng/phiên ra sao.
- Logout và account switch có xóa đúng cache nhạy cảm không.
- Worker cũ có tiếp tục trả nội dung đã cache sau khi deploy hay không.

Không cache access token, refresh token hoặc response nhạy cảm dùng chung cho nhiều tài khoản. Nếu cần offline data cá nhân, thiết kế partition theo user/session, mã hóa và xóa có kiểm soát; nhớ rằng dữ liệu phía client vẫn có thể bị đọc bởi script cùng origin.

### 5.4. Clear site data và quyền xóa

Ứng dụng có thể chủ động xóa dữ liệu do mình sở hữu:

```js
localStorage.removeItem('ui-preference');
sessionStorage.clear();

const databaseNames = await indexedDB.databases();
for (const database of databaseNames) {
  if (database.name?.startsWith('my-app-')) {
    indexedDB.deleteDatabase(database.name);
  }
}

const cacheNames = await caches.keys();
await Promise.all(
  cacheNames
    .filter((name) => name.startsWith('my-app-'))
    .map((name) => caches.delete(name))
);
```

Ví dụ chỉ xóa các database/cache có prefix thuộc ứng dụng; không xóa toàn bộ dữ liệu origin nếu origin dùng chung nhiều ứng dụng. API indexedDB.databases() chưa được hỗ trợ đồng nhất ở mọi browser; cần xử lý fallback bằng danh sách database do ứng dụng quản lý.

Xóa dữ liệu client không thay thế revoke session/token ở server. Nếu credential đã bị sao chép, xóa localStorage chỉ xóa bản lưu tại browser hiện tại.

## 6. Permission và các API nhạy cảm

Browser dùng permission để kiểm soát một số khả năng truy cập dữ liệu hoặc phần cứng. Permission thường gắn với origin, loại API và quyết định của người dùng; một số API còn yêu cầu user activation hoặc secure context.

Ví dụ API nhạy cảm:

- Geolocation: vị trí thiết bị.
- Camera và microphone: hình ảnh/âm thanh.
- Notifications: hiển thị thông báo.
- Clipboard: đọc hoặc ghi clipboard.
- Screen capture: chia sẻ màn hình.
- Bluetooth, USB, Serial và HID: truy cập thiết bị ngoại vi trong browser hỗ trợ.
- Sensor APIs: chuyển động, hướng hoặc tín hiệu thiết bị.

### 6.1. Permission không phải lúc nào cũng có cùng trạng thái

Permissions API có thể trả granted, denied hoặc prompt, nhưng hỗ trợ từng permission name khác nhau theo browser. Query permission không nhất thiết kích hoạt prompt; API thực tế có thể yêu cầu user gesture và điều kiện riêng.

Ví dụ:

```js
async function inspectGeolocationPermission() {
  if (!navigator.permissions?.query) {
    return 'unsupported';
  }

  try {
    const status = await navigator.permissions.query({
      name: 'geolocation',
    });
    return status.state;
  } catch {
    return 'unknown';
  }
}
```

Không coi unsupported hoặc unknown là denied. Hãy phân biệt browser không hỗ trợ query, API bị policy chặn, quyền bị từ chối và người dùng chưa quyết định.

### 6.2. Xin quyền đúng thời điểm

- Giải thích chức năng cần quyền gì và dùng dữ liệu vào mục đích nào.
- Chỉ gọi API khi người dùng chủ động bắt đầu chức năng tương ứng.
- Không yêu cầu một nhóm quyền rộng ngay khi trang vừa tải.
- Nếu người dùng từ chối, cung cấp cách tiếp tục không cần quyền khi có thể.
- Dừng camera/microphone track và ngừng theo dõi vị trí khi chức năng kết thúc.
- Không tiếp tục thu thập sau khi người dùng đóng dialog hoặc rời màn hình.

Ví dụ dừng camera:

```js
let cameraStream;

async function startCamera() {
  cameraStream = await navigator.mediaDevices.getUserMedia({
    video: true,
    audio: false,
  });
}

function stopCamera() {
  cameraStream?.getTracks().forEach((track) => track.stop());
  cameraStream = null;
}
```

Permission granted không có nghĩa người dùng đồng ý cho thu thập vô thời hạn. Consent cho chức năng và permission của browser là hai khái niệm cần được xử lý rõ ràng.

### 6.3. Permissions Policy

Website có thể giới hạn một số API bằng Permissions Policy response header. Ví dụ một trang không cần camera, microphone hoặc geolocation:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Với iframe, top-level document có thể cấp quyền cho một origin cụ thể bằng header và thuộc tính allow khi thật sự cần. Không dùng allowlist rộng như * nếu chỉ có một dịch vụ được tin cậy.

Permissions Policy giới hạn khả năng sử dụng API trong document/iframe; nó không thay thế việc xin permission của người dùng và không phải cơ chế authorization cho dữ liệu backend.

## 7. Referrer, URL và privacy headers

### 7.1. Referrer có thể tiết lộ thông tin

Khi người dùng điều hướng hoặc tải tài nguyên từ một trang khác, browser có thể gửi header Referer cho destination. Tùy Referrer-Policy, header có thể chứa full URL, chỉ origin hoặc không được gửi.

Query string có thể chứa search term, mã chiến dịch, email hoặc identifier. Nếu full URL bị chuyển qua Referer tới third-party image, analytics hoặc link ngoài, dữ liệu đó có thể rời khỏi site ban đầu.

### 7.2. Chọn Referrer-Policy

Một số giá trị thường dùng:

| Policy | Hành vi |
|---|---|
| no-referrer | Không gửi Referer |
| same-origin | Chỉ gửi Referer cho request cùng origin |
| strict-origin | Chỉ gửi origin; bỏ khi downgrade HTTPS xuống HTTP |
| strict-origin-when-cross-origin | Gửi full URL cho same-origin, chỉ origin cho cross-origin an toàn; bỏ khi downgrade |
| origin | Chỉ gửi origin |

Ví dụ:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Với callback xác thực, trang chứa dữ liệu nhạy cảm hoặc luồng thanh toán, có thể dùng no-referrer để giảm rò rỉ URL. Policy cần được chọn theo yêu cầu sản phẩm và kiểm tra ảnh hưởng tới analytics hoặc tích hợp hợp lệ.

### 7.3. Privacy và security headers phối hợp

Một cấu hình cơ bản có thể gồm:

```http
Cache-Control: no-store
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Đây là điểm xuất phát, không phải policy dùng nguyên trạng cho mọi ứng dụng. CSP cần được điều chỉnh theo script, style, image, font, connect và frame origin thực tế. Cache-Control: no-store phù hợp với response nhạy cảm; không nên áp dụng mù quáng cho mọi asset tĩnh vì có thể làm giảm hiệu năng.

Các header có vai trò khác nhau:

- CSP giảm khả năng nạp/chạy nội dung không được phép và giúp phòng XSS.
- Referrer-Policy giới hạn URL được tiết lộ cho destination.
- Permissions-Policy giới hạn một số API nhạy cảm.
- Cache-Control điều khiển việc lưu response.
- X-Content-Type-Options giảm nguy cơ MIME sniffing.

## 8. Tín hiệu privacy và lựa chọn của người dùng

### 8.1. Global Privacy Control

Global Privacy Control (GPC) là tín hiệu opt-out được browser hoặc extension có thể gửi, thường qua HTTP request header Sec-GPC: 1; một số môi trường cũng cung cấp thuộc tính JavaScript tương ứng. Tín hiệu này được thiết kế để biểu đạt lựa chọn không bán/chia sẻ dữ liệu cá nhân trong các khuôn khổ pháp lý có công nhận.

Server cần biết nghĩa vụ pháp lý và chính sách áp dụng cho người dùng, rồi xử lý tín hiệu phù hợp. Không coi GPC là bằng chứng người dùng đã từ chối mọi loại cookie hoặc mọi xử lý dữ liệu; phạm vi pháp lý và cách triển khai có thể khác nhau.

### 8.2. Do Not Track

Do Not Track (DNT) từng được dùng để biểu đạt lựa chọn không bị theo dõi qua header DNT: 1 hoặc thuộc tính JavaScript. DNT không có mức hỗ trợ và hiệu lực thống nhất; nhiều dịch vụ không xử lý nó như một yêu cầu bắt buộc.

Không dùng DNT thay cho consent management hoặc GPC. Nếu sản phẩm hỗ trợ DNT, hãy mô tả rõ hệ thống làm gì khi nhận tín hiệu.

### 8.3. Consent và preference center

Một banner cookie không tự động làm cho việc thu thập dữ liệu trở nên hợp lệ. Thiết kế consent cần:

- Phân loại mục đích: cần thiết, phân tích, quảng cáo, cá nhân hóa hoặc chức năng tùy chọn.
- Không bật tracking không cần thiết trước khi có lựa chọn hợp lệ nếu quy định yêu cầu consent trước.
- Cho phép từ chối dễ như chấp nhận.
- Lưu lại phiên bản notice, thời điểm, mục đích và lựa chọn ở mức cần thiết.
- Cho phép thay đổi hoặc rút lại lựa chọn.
- Không dùng dark pattern để ép người dùng chấp thuận.
- Tách consent cho chức năng nhạy cảm khỏi permission của browser.

## 9. Private browsing, tracking protection và giới hạn ẩn danh

### 9.1. Private/Incognito mode

Private browsing thường tách phiên khỏi dữ liệu duyệt thông thường và xóa một phần dữ liệu phiên khi cửa sổ private cuối cùng đóng. Hành vi cụ thể tùy browser. Trong phiên private, website vẫn có thể nhìn thấy request, IP ở server, dữ liệu mà người dùng chủ động gửi và một số tín hiệu fingerprint.

Private browsing không đồng nghĩa:

- Ẩn IP khỏi website hoặc network operator.
- Ẩn hoạt động khỏi employer/school quản lý thiết bị hoặc mạng.
- Chặn mọi fingerprinting.
- Ngăn malware hoặc extension được cấp quyền quan sát.
- Tự động mã hóa dữ liệu đầu cuối ngoài HTTPS.

### 9.2. VPN và proxy

VPN có thể thay IP nguồn mà website nhìn thấy bằng IP của VPN endpoint, nhưng nhà cung cấp VPN có thể quan sát metadata kết nối và browser fingerprint vẫn có thể liên kết phiên. VPN không xóa cookie, localStorage hoặc tài khoản đã đăng nhập.

Proxy privacy của browser có thể giảm thông tin mạng mà website nhìn thấy, nhưng hiệu quả phụ thuộc kiến trúc và cấu hình. Không quảng bá VPN như giải pháp ẩn danh tuyệt đối.

### 9.3. Tracking protection và extension

Browser có thể chặn tracker đã biết, giới hạn third-party cookie, partition storage hoặc giảm fingerprint surface. Extension privacy có thể chặn request hoặc thay đổi nội dung, nhưng bản thân extension có thể có quyền đọc dữ liệu trang. Chỉ cài extension từ nguồn đáng tin cậy và kiểm tra permission mà extension yêu cầu.

Tracking protection có thể làm hỏng một số luồng đăng nhập, thanh toán hoặc embedded widget vốn phụ thuộc third-party state. Ứng dụng nên ưu tiên top-level redirect, BFF/session ở first-party context hoặc API partitioned phù hợp; không yêu cầu người dùng tắt toàn bộ protection như giải pháp mặc định.

## 10. Thiết kế browser privacy cho ứng dụng

Privacy cần được đưa vào kiến trúc từ đầu thay vì chỉ thêm banner sau khi sản phẩm đã thu thập dữ liệu.

### 10.1. Data minimization

- Chỉ thu thập trường dữ liệu cần cho chức năng hoặc mục đích đã công bố.
- Tránh fingerprinting nếu feature detection hoặc dữ liệu tài khoản đã đủ.
- Giới hạn thời gian lưu và tự động xóa dữ liệu không còn cần.
- Không gửi dữ liệu nhạy cảm qua URL, referrer hoặc analytics event.
- Không đưa token/session identifier vào log, crash report hoặc third-party telemetry.
- Tách dữ liệu định danh khỏi event analytics khi có thể.
- Dùng dữ liệu tổng hợp hoặc pseudonymous identifier với retention giới hạn.

Pseudonymization giảm khả năng nhận diện trực tiếp nhưng không đồng nghĩa anonymization. Nếu dữ liệu có thể liên kết lại với người dùng bằng bảng mapping hoặc tín hiệu phụ, vẫn phải xử lý như dữ liệu cá nhân theo chính sách và pháp luật liên quan.

### 10.2. Third-party scripts

Script bên thứ ba chạy trong document thường có quyền tương đương JavaScript first-party của trang đối với DOM và dữ liệu mà trang có thể đọc. Một analytics tag hoặc chat widget bị chiếm có thể đọc form, URL, storage mà script cùng origin truy cập được.

Kiểm soát:

- Giảm số script bên thứ ba và chỉ giữ integration cần thiết.
- Dùng CSP để giới hạn nguồn script/connect/frame.
- Dùng Subresource Integrity cho tài nguyên static cross-origin khi phù hợp.
- Không đưa secret hoặc token vào DOM và global JavaScript object.
- Tránh tải tag manager không kiểm soát từ nguồn có quyền thay script tùy ý.
- Review permission, data flow và retention của từng vendor.

### 10.3. Cookie và session

- Dùng cookie host-only nếu không cần chia sẻ subdomain.
- Đặt Secure, HttpOnly và SameSite theo threat model.
- Tránh cookie lifetime dài nếu không cần remember me.
- Không lưu dữ liệu cá nhân dư thừa trong cookie.
- Cấp session ID mới sau đăng nhập hoặc thay đổi mức xác thực.
- Revoke session phía server khi logout, đổi mật khẩu hoặc phát hiện compromise.
- Không dựa vào cookie flag thay cho CSRF token, authorization hoặc XSS defense.

### 10.4. Logging và analytics

Log nên phục vụ vận hành và bảo mật mà không thu thập quá mức:

- Redact query parameters có token, email hoặc identifier.
- Không ghi request body chứa mật khẩu, payment data hoặc nội dung nhạy cảm.
- Giới hạn quyền truy cập log và thời gian retention.
- Tách audit log bắt buộc khỏi analytics marketing.
- Ghi event theo schema ổn định, không gửi toàn bộ DOM hoặc form.
- Cho phép người dùng từ chối analytics tùy chọn theo policy áp dụng.

### 10.5. Privacy review theo data flow

Với mỗi tính năng, trả lời:

1. Dữ liệu nào được tạo hoặc thu thập?
2. API hoặc script nào đọc dữ liệu đó?
3. Dữ liệu đi tới server, vendor hoặc origin nào?
4. Có cần permission hoặc consent không?
5. Dữ liệu lưu ở cookie, storage, cache hay log nào?
6. Ai có thể đọc dữ liệu trong browser và phía server?
7. Khi logout, revoke consent hoặc xóa tài khoản, dữ liệu nào được xóa?
8. Có thể thực hiện chức năng với ít dữ liệu hơn không?

## 11. Thực hành: browser privacy audit bằng Node.js

Lab tạo một trang local để quan sát một phần browser surface, kiểm tra storage và permission state mà không mở prompt, đồng thời xem tác dụng của các privacy headers. Lab không dùng third-party script, không gọi tracker và không gửi browser fingerprint tới server.

Bạn sẽ kiểm tra:

- Một số thuộc tính navigator, screen, timezone và browser privacy signals.
- Giá trị document.referrer và document.cookie.
- Sự khác nhau giữa cookie HttpOnly và cookie JavaScript có thể đọc.
- Khả năng ghi/xóa dữ liệu thử nghiệm trong localStorage và sessionStorage.
- Permission state bằng Permissions API nếu browser hỗ trợ; query không gọi API phần cứng và không chủ động xin quyền.
- CSP, Referrer-Policy, Permissions-Policy và Cache-Control trên response.

### Bước 1 — Tạo file browser-privacy-lab.cjs

```js
const http = require('node:http');
const { randomBytes } = require('node:crypto');

const page = [
  '<!doctype html>',
  '<html lang="vi"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Browser privacy lab</title></head><body>',
  '<h1>Browser privacy audit</h1>',
  '<p>Lab chỉ đọc browser surface và dùng dữ liệu thử nghiệm local.</p>',
  '<button id="inspect" type="button">Inspect browser surface</button>',
  '<button id="storage-write" type="button">Write test storage</button>',
  '<button id="storage-read" type="button">Read test storage</button>',
  '<button id="storage-clear" type="button">Clear test storage</button>',
  '<button id="permission" type="button">Inspect permission state</button>',
  '<pre id="output"></pre>',
  '<script src="/app.js" defer></script>',
  '</body></html>',
].join('\n');

const appJs = [
  "const output = document.querySelector('#output');",
  "const TEST_KEY = 'browser-privacy-lab:test-value';",
  'function show(label, value) {',
  '  output.textContent += label + ": " + String(value) + "\\n";',
  '}',
  'function safeRead(read) {',
  '  try { return read(); } catch (error) { return error.name; }',
  '}',
  "document.querySelector('#inspect').addEventListener('click', () => {",
  '  output.textContent = "";',
  '  const surface = {',
  '    language: navigator.language,',
  '    languages: navigator.languages,',
  '    platform: navigator.platform,',
  '    userAgent: navigator.userAgent,',
  '    userAgentDataAvailable: Boolean(navigator.userAgentData),',
  '    hardwareConcurrency: navigator.hardwareConcurrency,',
  '    deviceMemory: navigator.deviceMemory,',
  '    cookieEnabled: navigator.cookieEnabled,',
  '    globalPrivacyControl: navigator.globalPrivacyControl,',
  '    doNotTrack: navigator.doNotTrack,',
  '    referrer: document.referrer || "(empty)",',
  '    documentCookie: document.cookie || "(empty or HttpOnly only)",',
  '    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,',
  '    screen: {',
  '      width: screen.width,',
  '      height: screen.height,',
  '      colorDepth: screen.colorDepth,',
  '    },',
  '    localStorageAvailable: safeRead(() => { localStorage.getItem(TEST_KEY); return true; }),',
  '    sessionStorageAvailable: safeRead(() => { sessionStorage.getItem(TEST_KEY); return true; }),',
  '  };',
  '  show("Browser surface", JSON.stringify(surface, null, 2));',
  '});',
  "document.querySelector('#storage-write').addEventListener('click', () => {",
  '  try {',
  '    localStorage.setItem(TEST_KEY, "synthetic-local-value");',
  '    sessionStorage.setItem(TEST_KEY, "synthetic-session-value");',
  '    show("Storage", "Wrote synthetic values only.");',
  '  } catch (error) { show("Storage error", error.name); }',
  '});',
  "document.querySelector('#storage-read').addEventListener('click', () => {",
  '  show("localStorage test key", safeRead(() => localStorage.getItem(TEST_KEY)));',
  '  show("sessionStorage test key", safeRead(() => sessionStorage.getItem(TEST_KEY)));',
  '});',
  "document.querySelector('#storage-clear').addEventListener('click', () => {",
  '  try {',
  '    localStorage.removeItem(TEST_KEY);',
  '    sessionStorage.removeItem(TEST_KEY);',
  '    show("Storage", "Removed only the lab test key.");',
  '  } catch (error) { show("Storage error", error.name); }',
  '});',
  "document.querySelector('#permission').addEventListener('click', async () => {",
  '  if (!navigator.permissions?.query) {',
  '    show("Permissions API", "Unsupported");',
  '    return;',
  '  }',
  '  for (const name of ["geolocation", "notifications", "camera", "microphone"]) {',
  '    try {',
  '      const status = await navigator.permissions.query({ name });',
  '      show("Permission " + name, status.state);',
  '    } catch (error) {',
  '      show("Permission " + name, "Unknown/unsupported: " + error.name);',
  '    }',
  '  }',
  '  show("Permission note", "Query does not request device access or display a permission prompt.");',
  '});',
].join('\n');

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');
  const commonHeaders = {
    'Cache-Control': 'no-store',
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'",
    'X-Content-Type-Options': 'nosniff',
  };

  if (req.method === 'GET' && url.pathname === '/') {
    res.writeHead(200, {
      ...commonHeaders,
      'Content-Type': 'text/html; charset=utf-8',
      // HTTP localhost lab omits Secure; production must use HTTPS and Secure.
      'Set-Cookie': 'privacy_lab_session=' + randomBytes(16).toString('hex') +
        '; Path=/; HttpOnly; SameSite=Lax; Max-Age=900',
    });
    return res.end(page);
  }

  if (req.method === 'GET' && url.pathname === '/app.js') {
    res.writeHead(200, {
      ...commonHeaders,
      'Content-Type': 'text/javascript; charset=utf-8',
    });
    return res.end(appJs);
  }

  res.writeHead(404, {
    ...commonHeaders,
    'Content-Type': 'text/plain; charset=utf-8',
  });
  res.end('Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node browser-privacy-lab.cjs
```

Mở http://localhost:3000 trong browser. Nếu cổng 3000 đang được sử dụng, đổi cổng trong server và URL base truyền vào new URL().

Cookie privacy_lab_session dùng HttpOnly; SameSite=Lax để minh họa cookie session không thể đọc qua document.cookie. Vì lab chạy HTTP trên localhost, cookie demo bỏ Secure; production phải dùng HTTPS và đặt Secure.

### Bước 3 — Quan sát browser surface

1. Nhấn **Inspect browser surface**.
2. Quan sát language, platform, User-Agent, kích thước màn hình, timezone và các privacy signal nếu browser cung cấp.
3. Xem document.referrer; trang mở trực tiếp thường không có referrer.
4. Xem document.cookie; cookie session HttpOnly không xuất hiện trong JavaScript.
5. So sánh kết quả giữa profile thông thường và private browsing nếu muốn; các giá trị có thể khác theo browser policy.

Các trường hiển thị là dữ liệu quan sát trong browser hiện tại, không phải fingerprint hoàn chỉnh và không được gửi lên server.

### Bước 4 — Thử storage

1. Nhấn **Write test storage** để ghi hai giá trị synthetic.
2. Nhấn **Read test storage** để đọc lại.
3. Mở DevTools → Application/Storage để xem key có prefix browser-privacy-lab.
4. Nhấn **Clear test storage** để xóa đúng key của lab.

Lab không xóa storage của ứng dụng khác. Hãy nhớ localStorage và sessionStorage có thể bị JavaScript cùng origin đọc; không đặt token hoặc dữ liệu cá nhân vào các key thử nghiệm.

### Bước 5 — Kiểm tra permission mà không xin quyền

Nhấn **Inspect permission state**. Lab chỉ gọi Permissions API query; nó không gọi geolocation, camera hoặc microphone và không chủ động mở prompt. Browser có thể trả granted, denied, prompt hoặc báo unsupported/unknown tùy API và policy.

### Bước 6 — Xem privacy headers

Mở DevTools → Network, chọn document và script app.js. Kiểm tra:

- Referrer-Policy là no-referrer.
- Permissions-Policy giới hạn camera, microphone và geolocation.
- Content-Security-Policy chỉ cho script cùng origin và chặn object/frame.
- Cache-Control là no-store.
- Set-Cookie có HttpOnly và SameSite=Lax.

Lab cố ý không có analytics, third-party resource, beacon hoặc endpoint thu thập fingerprint.

## 12. Checklist browser privacy

- [ ] Đã lập bản đồ dữ liệu browser, server, CDN và third-party vendor có thể quan sát.
- [ ] Đã phân biệt origin với site và first-party với third-party context.
- [ ] Cookie nhạy cảm dùng Secure, HttpOnly, SameSite và scope tối thiểu.
- [ ] Không đặt session ID, email hoặc dữ liệu cá nhân trong URL.
- [ ] Third-party cookie behavior đã được kiểm tra trên browser mục tiêu.
- [ ] Embedded state dùng partitioning/CHIPS hoặc Storage Access API đúng mục đích khi cần.
- [ ] localStorage, sessionStorage, IndexedDB, Cache Storage và Service Worker có retention/cleanup rõ ràng.
- [ ] Không cache token hoặc response cá nhân dùng chung giữa tài khoản.
- [ ] Không fingerprinting ngầm; chỉ dùng tín hiệu tối thiểu có mục đích rõ.
- [ ] API nhạy cảm chỉ được gọi khi cần và sau tương tác phù hợp.
- [ ] Permission được giải thích, có đường lui khi từ chối và được dừng khi chức năng kết thúc.
- [ ] Permissions Policy chặn API không cần và iframe allowlist theo origin cụ thể.
- [ ] Referrer-Policy giảm rò rỉ URL và query nhạy cảm.
- [ ] CSP, Cache-Control và X-Content-Type-Options được cấu hình theo loại response.
- [ ] GPC/DNT được diễn giải theo policy và nghĩa vụ pháp lý áp dụng.
- [ ] Consent có thể từ chối, thay đổi và rút lại dễ dàng.
- [ ] Third-party scripts được kiểm kê, giới hạn bằng CSP và review quyền.
- [ ] Log/analytics redact token, query identifier và dữ liệu nhạy cảm.
- [ ] Có quy trình xóa dữ liệu client và revoke session phía server.
- [ ] Private browsing/VPN không được quảng bá như giải pháp ẩn danh tuyệt đối.

## 13. Câu hỏi tự kiểm tra

**1.** Browser privacy bảo vệ điều gì?  
**Trả lời:** Khả năng kiểm soát dữ liệu được tạo, lưu, chia sẻ và quan sát khi người dùng truy cập website; nó bao gồm cả storage, network metadata, permission và tracking.

**2.** Origin khác site thế nào?  
**Trả lời:** Origin gồm scheme, host và port; site là khái niệm rộng hơn được dùng trong các cơ chế như SameSite cookie và thường dựa trên scheme cùng registrable domain.

**3.** Third-party cookie có luôn bị chặn không?  
**Trả lời:** Không thể khẳng định chung cho mọi browser. Chính sách phụ thuộc browser, phiên bản, cài đặt, context và ngoại lệ tương thích.

**4.** Storage partitioning giúp giảm rủi ro nào?  
**Trả lời:** Nó tách trạng thái embedded third-party theo top-level site, giảm khả năng dùng chung một định danh qua nhiều website.

**5.** Fingerprinting khác cookie tracking thế nào?  
**Trả lời:** Fingerprinting kết hợp thuộc tính browser/thiết bị để phân biệt client và có thể không cần lưu cookie lâu dài.

**6.** Private browsing có ẩn IP khỏi website không?  
**Trả lời:** Không. Website vẫn nhìn thấy IP ở đầu kết nối và có thể quan sát dữ liệu người dùng gửi cùng một số tín hiệu browser.

**7.** HttpOnly bảo vệ cookie như thế nào?  
**Trả lời:** JavaScript không đọc trực tiếp được cookie qua document.cookie, nhưng browser vẫn có thể gửi cookie trong request phù hợp.

**8.** Query Permissions API có tự mở prompt không?  
**Trả lời:** Thông thường không; query đọc trạng thái nếu browser hỗ trợ. Gọi API phần cứng thực tế có thể có điều kiện và prompt riêng.

**9.** Referrer-Policy giúp gì?  
**Trả lời:** Giới hạn phần URL nguồn browser gửi tới destination, giảm rò rỉ path và query string.

**10.** Vì sao xóa localStorage không đủ để logout an toàn?  
**Trả lời:** Token đã bị sao chép vẫn có thể dùng được; cần revoke session/token ở server và dọn các storage/cache liên quan.

## Tổng kết

Browser privacy là tập hợp kiểm soát trên dữ liệu request, cookie, storage, permission, referrer và các tín hiệu có thể tạo fingerprint. Hãy hiểu rõ khác biệt giữa origin và site, kiểm tra third-party cookie/partitioning theo browser mục tiêu, giới hạn API nhạy cảm và giảm dữ liệu được lưu hoặc gửi ra ngoài. Private browsing, VPN và tracking protection có thể giảm một số rủi ro nhưng không tạo ẩn danh tuyệt đối. Thiết kế tốt bắt đầu từ data minimization, retention có giới hạn, consent minh bạch, headers phù hợp và khả năng xóa dữ liệu/revoke session ở cả browser lẫn server.
