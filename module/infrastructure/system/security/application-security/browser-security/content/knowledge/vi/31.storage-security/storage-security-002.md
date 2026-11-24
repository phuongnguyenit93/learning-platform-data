# Sensitive data trong browser

## 1. Vì sao dữ liệu trong browser cần được bảo vệ?

Ứng dụng web thường lưu dữ liệu ngay trong browser để giữ trạng thái đăng nhập, ghi nhớ tùy chọn, hỗ trợ offline hoặc cải thiện tốc độ. Các nơi lưu phổ biến gồm cookie, `localStorage`, `sessionStorage`, IndexedDB, Cache Storage và bộ nhớ JavaScript đang chạy.

Những vùng lưu trữ này nằm trong môi trường mà JavaScript của trang có thể truy cập theo các quy tắc của browser. Nếu ứng dụng có lỗ hổng Cross-Site Scripting (XSS), mã độc chạy cùng origin có thể đọc hoặc thay đổi dữ liệu mà ứng dụng tin cậy. Vì vậy, dữ liệu nhạy cảm trong browser cần được thiết kế theo threat model, giới hạn tối thiểu và có vòng đời rõ ràng.

Ví dụ, lưu một access token dài hạn trong `localStorage` rất thuận tiện cho ứng dụng gọi API. Nhưng bất kỳ script nào chạy được trong origin đó, bao gồm script bị chèn qua XSS hoặc dependency bên thứ ba bị xâm nhập, đều có thể đọc token và gửi ra ngoài. Token có thể tiếp tục bị sử dụng sau khi tab đóng, cho đến khi hết hạn hoặc server thu hồi.

Một lựa chọn khác là giữ session identifier trong cookie `HttpOnly`, `Secure` và `SameSite` phù hợp. JavaScript không đọc trực tiếp được cookie `HttpOnly`, giúp giảm khả năng đánh cắp session bằng một đoạn XSS chỉ đọc storage. Tuy nhiên, XSS vẫn có thể thực hiện hành động thay mặt người dùng trong phiên đang mở. Cookie cũng cần CSRF protection và cấu hình scope chính xác.

Bài học này tập trung vào câu hỏi dữ liệu nào nên được lưu trong browser, kẻ tấn công nào có thể tiếp cận dữ liệu, XSS thay đổi rủi ro ra sao, mã hóa phía client bảo vệ được đến đâu và làm thế nào để thu thập, sử dụng, hết hạn và xóa dữ liệu an toàn.

### Kết quả học tập

Sau bài này, người học có thể:

1. Xây dựng threat model cho dữ liệu lưu trong browser.
2. So sánh cookie, Web Storage, IndexedDB, Cache Storage và memory.
3. Giải thích vì sao XSS có thể đọc hoặc sử dụng dữ liệu cùng origin.
4. Chọn nơi lưu trữ dựa trên độ nhạy cảm, thời hạn và nhu cầu truy cập.
5. Hiểu giới hạn của mã hóa phía client, Web Crypto và non-extractable key.
6. Áp dụng data minimization và giới hạn thời gian lưu dữ liệu.
7. Thiết kế logout, revoke, expiry và deletion cho cả browser lẫn server.
8. Kiểm tra dữ liệu nhạy cảm bằng DevTools và các tình huống XSS giả lập an toàn.

## 2. Threat model cho dữ liệu phía client

Trước khi chọn API lưu trữ, hãy xác định tài sản cần bảo vệ, ai có thể tấn công, họ có khả năng gì và tác động nếu dữ liệu bị lộ.

### 2.1. Tài sản cần bảo vệ

Ví dụ về dữ liệu có thể xuất hiện trong browser:

- Session identifier, access token, refresh token và thông tin xác thực.
- Thông tin cá nhân: tên, email, số điện thoại, địa chỉ, vị trí.
- Dữ liệu tài chính, đơn hàng, hóa đơn và thông tin thanh toán.
- Nội dung riêng tư, tài liệu, tin nhắn và dữ liệu công việc.
- Khóa mã hóa, recovery secret và dữ liệu dùng để khôi phục tài khoản.
- Dữ liệu định danh thiết bị, lịch sử hoạt động và thông tin phân tích.
- Nội dung form chưa gửi, dữ liệu offline và bản nháp.

Không phải mọi dữ liệu đều có cùng mức độ nhạy cảm. Một theme preference có thể được lưu lâu dài trong `localStorage`; refresh token hoặc dữ liệu y tế không nên được xử lý như một tùy chọn giao diện.

### 2.2. Đối thủ và khả năng

| Đối thủ/tình huống | Khả năng điển hình | Hệ quả |
| --- | --- | --- |
| XSS trong origin của ứng dụng | Đọc Web Storage/IndexedDB, truy cập DOM, gọi API, sử dụng dữ liệu trong runtime | Lộ dữ liệu, chiếm phiên hoặc thao tác thay người dùng |
| Dependency hoặc script bên thứ ba bị xâm nhập | Chạy JavaScript trong trang nếu được tải và thực thi | Tiếp cận dữ liệu mà origin cấp cho script |
| Website độc hại khác origin | Bị SOP giới hạn; có thể thử CSRF, nhúng tài nguyên hoặc khai thác luồng tích hợp | Gửi request ngoài ý muốn nếu ứng dụng thiếu bảo vệ |
| Người dùng chung thiết bị | Mở lại browser profile hoặc tab còn đăng nhập | Xem dữ liệu còn lưu, dùng phiên chưa kết thúc |
| Malware hoặc extension có quyền rộng | Đọc/điều khiển browser hoặc hệ thống tùy quyền | Có thể vượt ngoài ranh giới của storage API |
| Truy cập vật lý hoặc sao lưu profile | Sao chép dữ liệu profile, cache hoặc file browser | Lộ dữ liệu lưu tại máy |
| Lỗi vận hành/logging | Ghi token, URL nhạy cảm hoặc payload vào log | Dữ liệu tồn tại ngoài vùng lưu dự kiến |

Threat model cần nói rõ giả định. SOP cô lập origin trước các website khác, nhưng không cô lập dữ liệu khỏi script được phép chạy trong cùng origin. Mã độc đã chạy trong origin thường có quyền gần với ứng dụng đối với DOM và API mà trang có thể truy cập.

### 2.3. Phạm vi bảo vệ của browser storage

Browser cung cấp một số ranh giới:

- Storage thường được phân vùng theo origin hoặc storage key theo quy tắc browser.
- Cookie có domain/path/secure/samesite attributes và các quy tắc gửi tự động.
- `HttpOnly` ngăn JavaScript đọc cookie.
- SOP hạn chế JavaScript từ origin khác truy cập storage.
- Browser có thể mã hóa dữ liệu profile trên đĩa hoặc dùng cơ chế bảo vệ hệ điều hành, tùy nền tảng.

Các ranh giới này hữu ích, nhưng không biến browser thành một secret vault chống lại XSS, malware hoặc người có quyền truy cập profile. Hãy thiết kế với giả định dữ liệu mà JavaScript của ứng dụng có thể đọc thì script độc hại cùng origin cũng có thể đọc.

## 3. Những nơi browser có thể lưu dữ liệu

### 3.1. So sánh nhanh

| Nơi lưu | Đặc điểm | XSS có thể tiếp cận? | Phù hợp với |
| --- | --- | --- | --- |
| JavaScript memory | Tồn tại trong runtime hiện tại; thường mất khi page/context kết thúc | Có thể đọc hoặc sử dụng khi XSS chạy trong page | Dữ liệu ngắn hạn cần trong phiên |
| `sessionStorage` | Key/value string theo origin và page session/tab | Có | Tùy chọn tạm thời, trạng thái không nhạy cảm |
| `localStorage` | Key/value string theo origin, tồn tại qua lần tải lại | Có | Theme, ngôn ngữ, tùy chọn UI |
| IndexedDB | Database bất đồng bộ, hỗ trợ object và dữ liệu lớn | Có, nếu script cùng origin được phép truy cập | Cache dữ liệu ứng dụng đã phân loại, dữ liệu offline có kiểm soát |
| Cache Storage | Lưu Request/Response, thường dùng với service worker | Có, qua API cùng origin và service worker | Asset và response phù hợp với cache policy |
| HTTP cache | Browser cache response theo HTTP caching semantics | XSS không nhất thiết đọc trực tiếp cache tùy ý, nhưng response đã cache có thể được ứng dụng/service worker sử dụng lại | Tài nguyên có cache policy rõ; response nhạy cảm cần kiểm soát chặt |
| Cookie `HttpOnly` | Browser tự gửi theo quy tắc cookie; JavaScript không đọc được | Không đọc trực tiếp; XSS vẫn có thể dùng phiên để gửi request | Session identifier do server quản lý |

Không có lựa chọn nào tự động an toàn chỉ vì tên API hoặc cách lưu. Độ nhạy cảm, quyền JavaScript, cách gửi request, thời gian tồn tại và cơ chế xóa mới quyết định mức rủi ro.

### 3.2. JavaScript memory

Giữ dữ liệu trong biến runtime giúp tránh lưu bền vững xuống Web Storage hoặc IndexedDB:

```js
let accessToken = null;

async function signIn() {
  const result = await authenticate();
  accessToken = result.accessToken;
}
```

Dữ liệu thường mất khi page reload hoặc context kết thúc. Nhưng XSS chạy trong cùng page có thể đọc biến toàn cục, hook function, gọi API thay ứng dụng hoặc lấy dữ liệu tại thời điểm nó được sử dụng. Module-scoped variable không phải ranh giới bảo mật chống lại mã độc cùng origin.

Memory có thể phù hợp với dữ liệu ngắn hạn cần trong một phiên, nhưng cần xóa tham chiếu khi không còn dùng, dừng các luồng đang hoạt động và không ghi giá trị nhạy cảm vào console hoặc telemetry.

### 3.3. `sessionStorage`

`sessionStorage` cung cấp API đồng bộ theo key/value:

```js
sessionStorage.setItem("activeTab", "orders");

const activeTab = sessionStorage.getItem("activeTab");

sessionStorage.removeItem("activeTab");
```

Dữ liệu được phân vùng theo origin và page session, thường gắn với tab. Nó tồn tại qua reload trong page session và thường được xóa khi tab/session kết thúc. Hành vi với tab được duplicate hoặc opener có thể có chi tiết riêng theo browser; không dùng `sessionStorage` như bảo đảm rằng dữ liệu chắc chắn bị xóa ngay khi người dùng đóng tab.

Nó phù hợp với trạng thái UI tạm thời không nhạy cảm. Tránh lưu password, bearer token, recovery code hoặc dữ liệu cá nhân có độ nhạy cảm cao.

### 3.4. `localStorage`

`localStorage` lưu chuỗi key/value theo origin và tồn tại qua nhiều lần mở trang:

```js
localStorage.setItem("theme", "dark");

const theme = localStorage.getItem("theme");

localStorage.removeItem("theme");
```

API đồng bộ, nên thao tác dữ liệu lớn có thể chặn main thread. Dữ liệu có thể tồn tại lâu cho tới khi bị xóa, browser dọn dẹp hoặc người dùng xóa site data.

`localStorage` dễ dùng nhưng mọi JavaScript cùng origin có thể truy cập. Không lưu long-lived bearer token, refresh token, password hoặc secret chỉ với lý do dữ liệu sẽ nằm trên máy người dùng.

### 3.5. IndexedDB

IndexedDB là database bất đồng bộ trong browser, hỗ trợ lưu object và dữ liệu có cấu trúc:

```js
const request = indexedDB.open("app-cache", 1);

request.onupgradeneeded = () => {
  const db = request.result;
  if (!db.objectStoreNames.contains("preferences")) {
    db.createObjectStore("preferences", { keyPath: "key" });
  }
};

request.onsuccess = () => {
  const db = request.result;
  const transaction = db.transaction("preferences", "readwrite");
  transaction.objectStore("preferences").put({
    key: "layout",
    value: "compact"
  });
};
```

IndexedDB thích hợp cho cache hoặc dữ liệu offline có cấu trúc, nhưng không phải vùng bí mật. JavaScript cùng origin có thể mở database và đọc object store mà ứng dụng cho phép truy cập. Nếu lưu bản sao dữ liệu cá nhân, cần có retention, phân quyền nghiệp vụ, xóa theo tài khoản và xử lý khi người dùng logout.

Browser áp dụng quota và eviction policy cho storage. IndexedDB không phải kho lưu trữ bền vững tuyệt đối: browser có thể giới hạn dung lượng hoặc xóa dữ liệu trong một số điều kiện, nhất là khi thiếu dung lượng. Ứng dụng cần xử lý quota error, dữ liệu bị mất và đồng bộ lại từ server khi cần; không dùng bản lưu client làm bản ghi duy nhất có thẩm quyền.

### 3.6. Cache Storage và service worker

Cache Storage thường được dùng để lưu asset hoặc response cho trải nghiệm offline:

```js
const cache = await caches.open("static-v1");
await cache.addAll([
  "/assets/app.css",
  "/assets/app.js",
  "/offline.html"
]);
```

Service worker có thể truy cập cache trong scope được browser cấp. Nếu cache cả response chứa dữ liệu riêng tư hoặc API trả thông tin tài khoản, dữ liệu có thể còn sau khi logout hoặc đổi người dùng trên cùng thiết bị.

Không cache mọi response một cách máy móc. Cần xác định response nào public, response nào private, cache key có gắn đúng user context không, và khi logout thì cache riêng của user được xóa hoặc vô hiệu hóa thế nào.

Cache Storage là API do ứng dụng/service worker quản lý; nó khác HTTP cache do browser tự quản lý theo response headers. Xóa Cache Storage không xóa HTTP cache, và ngược lại.

### 3.7. HTTP cache và response riêng tư

Ngay cả khi ứng dụng không gọi Cache API, browser hoặc intermediary cache vẫn có thể lưu response theo HTTP caching semantics. Với response chứa dữ liệu nhạy cảm, server cần đặt cache policy phù hợp. Ví dụ:

```http
Cache-Control: no-store
```

`no-store` yêu cầu cache không lưu response. `private` chỉ giới hạn shared cache; browser cache riêng vẫn có thể lưu response nếu các directive khác cho phép. Với response riêng tư cần tái sử dụng có kiểm soát, hãy chọn policy dựa trên threat model và kiểm tra cả CDN/reverse proxy. Không dựa vào việc logout xóa Web Storage để xử lý response đã đi vào HTTP cache.

`no-store` cũng không ngăn người dùng chụp màn hình, sao chép nội dung hoặc một extension/malware có quyền rộng thu thập dữ liệu khi response đang hiển thị.

### 3.8. Cookie

Cookie khác Web Storage ở chỗ browser có thể tự động gửi cookie theo domain, path, scheme, SameSite và các thuộc tính khác của request. Cookie có thể được đặt từ server:

```http
Set-Cookie: __Host-session=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
```

- `HttpOnly`: JavaScript không đọc cookie qua `document.cookie`.
- `Secure`: browser chỉ gửi cookie qua kết nối bảo mật.
- `SameSite=Lax`: hạn chế cookie trong nhiều request cross-site; lựa chọn thực tế cần phù hợp luồng đăng nhập và CSRF.
- `Path=/`: cookie áp dụng toàn bộ path của host.
- Prefix `__Host-`: yêu cầu `Secure`, `Path=/` và không có `Domain`, giúp giới hạn cookie ở host tạo nó.

Cookie `HttpOnly` giảm khả năng đánh cắp session identifier bằng JavaScript. Tuy nhiên, nếu XSS chạy trong trang đã đăng nhập, script vẫn có thể gửi request same-origin và browser tự đính kèm cookie. Vì vậy vẫn cần phòng XSS, CSRF token hoặc kiểm tra Origin/Fetch Metadata phù hợp cho hành động thay đổi trạng thái.

`Path` không phải ranh giới bảo mật giữa các ứng dụng trên cùng host. Tránh dùng `Domain=.example.com` nếu cookie không cần chia sẻ với subdomain khác; cookie host-only thường có scope hẹp hơn.

## 4. XSS làm thay đổi rủi ro storage ra sao?

### 4.1. XSS có thể đọc dữ liệu cùng origin

Nếu một trang có XSS, mã chèn có thể truy cập các API storage mà JavaScript thông thường của origin đó được phép dùng:

```js
// Minh họa rủi ro: đọc dữ liệu đã lưu trong origin.
const profile = localStorage.getItem("profile");
const cached = sessionStorage.getItem("draft");
```

IndexedDB và Cache Storage cũng không miễn nhiễm. Script cùng origin có thể mở database, đọc object store hoặc gọi Cache API trong phạm vi quyền của document/service worker.

Do đó, đổi từ `localStorage` sang IndexedDB không giải quyết gốc rễ của việc XSS có thể đọc dữ liệu.

### 4.2. XSS có thể sử dụng dữ liệu mà không cần đọc secret

Ngay cả khi session identifier nằm trong cookie `HttpOnly`, XSS vẫn có thể thực hiện hành động bằng phiên của người dùng:

```js
// Minh họa: mã cùng origin gửi request, browser tự đính kèm cookie.
fetch("/api/account/email", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ email: "attacker@example.test" })
});
```

Nếu server không có kiểm tra CSRF/origin phù hợp, xác thực lại cho hành động nhạy cảm hoặc xác minh nghiệp vụ, request có thể được xử lý trong phiên đang đăng nhập. Cookie `HttpOnly` bảo vệ khả năng đọc giá trị cookie, không ngăn XSS thao tác ứng dụng.

### 4.3. Script bên thứ ba cũng nằm trong threat model

Analytics, chat widget, tag manager, A/B testing và thư viện CDN có thể chạy JavaScript trong document. Nếu script được cấp quyền thực thi trong origin, nó thường có thể truy cập DOM và Web Storage như script ứng dụng.

Hạn chế rủi ro bằng cách:

- Giảm số lượng script bên thứ ba và quyền chúng được cấp.
- Dùng CSP để giới hạn nguồn script, kết hợp nonce/hash phù hợp.
- Dùng Subresource Integrity (SRI) cho asset bên ngoài khi phù hợp.
- Không đưa dữ liệu nhạy cảm vào global object hoặc DOM attribute.
- Tách ứng dụng/host không tin cậy sang origin riêng khi kiến trúc cho phép.
- Rà soát dependency, phiên bản và quy trình cập nhật.

### 4.4. Bảo vệ storage cần đi cùng phòng XSS

Các lớp bảo vệ quan trọng gồm output encoding theo context, tránh HTML injection, dùng DOM API an toàn như `textContent`, sanitizer đã được kiểm tra khi thật sự cần rich HTML, CSP, Trusted Types khi phù hợp và kiểm soát dependency. Các lớp này giảm khả năng script độc hại chạy được; storage design giảm tác động khi một lớp phòng vệ thất bại.

## 5. Chọn nơi lưu theo độ nhạy cảm

### 5.1. Bảng quyết định

| Dữ liệu | Lựa chọn thường phù hợp | Tránh |
| --- | --- | --- |
| Theme, ngôn ngữ, bố cục | `localStorage` hoặc cookie không nhạy cảm | Không cần mã hóa phức tạp |
| Trạng thái tab, bộ lọc tạm | `sessionStorage` hoặc memory | Không lưu token cùng object UI |
| Session identifier | Cookie `HttpOnly; Secure; SameSite` do server quản lý | Đưa session ID vào `localStorage` |
| Refresh token dài hạn | Thiết kế BFF/session cookie; nếu buộc dùng client OAuth thì cần đánh giá threat model và cơ chế rotation | Lưu refresh token lâu dài trong Web Storage |
| Access token ngắn hạn | Ưu tiên giữ trong memory khi kiến trúc cần token ở client; cân nhắc BFF để browser không giữ bearer token | Lưu bearer token dài hạn trong `localStorage` |
| Dữ liệu offline không nhạy cảm | IndexedDB/Cache Storage với expiry và quota handling | Lưu tràn lan không có xóa/partition theo user |
| Dữ liệu riêng tư cần offline | Chỉ lưu khi có yêu cầu rõ, giảm trường dữ liệu, đánh giá mã hóa và rủi ro XSS | Giả định mã hóa phía client ngăn XSS |
| Password, recovery secret | Không lưu sau khi hoàn tất tác vụ xác thực | Lưu trong Web Storage, IndexedDB hoặc log |

Bảng là hướng dẫn thiết kế, không phải quy tắc áp dụng cho mọi ứng dụng. Hãy xét loại dữ liệu, thời gian tồn tại, browser support, luồng offline và mức độ tác động nếu profile bị truy cập.

### 5.2. Ưu tiên BFF và session cookie khi phù hợp

Với ứng dụng web cần đăng nhập, một kiến trúc Backend for Frontend (BFF) có thể giữ access/refresh token ở server. Browser chỉ nhận session cookie ngẫu nhiên, giới hạn scope:

```http
Set-Cookie: __Host-session=OPAQUE_RANDOM_ID; Path=/; Secure; HttpOnly; SameSite=Lax
```

Browser gửi cookie tự động tới BFF; BFF kiểm tra session và gọi API downstream bằng token được giữ server-side. Thiết kế này giảm việc bearer token dài hạn xuất hiện trong JavaScript storage.

Cookie tự động gửi có rủi ro CSRF, nên BFF cần CSRF defense phù hợp: token anti-CSRF, kiểm tra `Origin`/`Referer` theo policy, Fetch Metadata và `SameSite` như lớp bổ sung. Cần rotate session sau đăng nhập hoặc thay đổi mức quyền, hết hạn idle/absolute và revoke session phía server khi logout.

### 5.3. Nếu ứng dụng buộc phải giữ token ở client

Một số SPA gọi trực tiếp resource server. Khi đó cần giới hạn tác động:

- Dùng access token thời hạn ngắn và scope tối thiểu.
- Ưu tiên giữ access token trong memory nếu mô hình ứng dụng cho phép.
- Không lưu refresh token dài hạn trong `localStorage` chỉ để tiện khôi phục phiên.
- Dùng Authorization Code + PKCE theo hướng dẫn của identity provider.
- Có rotation/reuse detection cho refresh token nếu provider hỗ trợ.
- Hạn chế token trong log, URL, crash report, analytics và error telemetry.
- Có cơ chế revoke và xử lý session compromise ở server/provider.

Memory không ngăn XSS sử dụng token khi token còn trong runtime. Nó chủ yếu giảm thời gian tồn tại và khả năng đọc lại sau reload/profile access so với storage bền vững.

## 6. Mã hóa dữ liệu phía client và giới hạn

### 6.1. Mã hóa at rest không tự giải quyết XSS

Ứng dụng có thể mã hóa dữ liệu trước khi ghi vào IndexedDB hoặc Web Storage. Điều này có thể bảo vệ bản sao dữ liệu nếu kẻ tấn công chỉ lấy được file database nhưng không có khóa. Tuy nhiên, nếu ứng dụng tự động lấy khóa từ cùng origin và giải mã dữ liệu khi tải trang, XSS có thể chạy trong lúc ứng dụng đã mở khóa.

Ví dụ, nếu khóa được lưu cạnh ciphertext trong `localStorage`, kẻ lấy được cả hai có thể giải mã ngoại tuyến. Nếu khóa là `CryptoKey` không extractable trong IndexedDB, JavaScript không thể export raw key, nhưng XSS cùng origin vẫn có thể lấy object key nếu truy cập được và yêu cầu Web Crypto thực hiện decrypt thay cho nó.

Mã hóa phía client hữu ích khi threat model bao gồm truy cập dữ liệu lưu trữ mà không có quyền chạy code trong origin đã mở khóa. Nó không bảo đảm chống lại script độc hại đang chạy trong phiên ứng dụng.

### 6.2. Web Crypto API

Web Crypto API cung cấp primitive mật mã như AES-GCM, HMAC, ECDSA và các hàm derive/import/export key. Không tự thiết kế thuật toán hoặc chế độ mã hóa. Khi cần mã hóa dữ liệu, dùng thuật toán chuẩn, IV/nonce ngẫu nhiên đúng quy tắc, quản lý khóa có chủ đích và thư viện/thiết kế đã được review.

Ví dụ minh họa mã hóa một buffer với AES-GCM bằng khóa đã được cấp từ một quy trình quản lý khóa riêng:

```js
async function encryptWithKey(key, plaintext) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(plaintext);

  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    encoded
  );

  return {
    iv: Array.from(iv),
    ciphertext: Array.from(new Uint8Array(ciphertext))
  };
}
```

Ví dụ chỉ minh họa thao tác mã hóa. Ứng dụng phải bảo đảm mỗi lần mã hóa với cùng AES-GCM key dùng IV duy nhất; không hardcode IV và không tái sử dụng IV. Cần lưu metadata phiên bản/thuật toán, xử lý lỗi xác thực khi decrypt và có quy trình xoay khóa.

### 6.3. Non-extractable key không chống được XSS đang hoạt động

Có thể tạo key không extractable:

```js
const key = await crypto.subtle.generateKey(
  {
    name: "AES-GCM",
    length: 256
  },
  false,
  ["encrypt", "decrypt"]
);
```

Tham số `extractable: false` ngăn export raw key qua các API export key. Nhưng nếu XSS có thể gọi code trong origin, nó có thể yêu cầu ứng dụng dùng key để decrypt dữ liệu mà ứng dụng được phép giải mã, hoặc đọc plaintext sau khi giải mã.

Không xem `CryptoKey` không extractable như một vùng lưu trữ an toàn tuyệt đối. Quyền sử dụng key và quyền đọc plaintext là hai vấn đề khác nhau.

### 6.4. Password-derived key

Nếu người dùng nhập passphrase để mở dữ liệu offline, ứng dụng có thể derive key từ password và salt bằng KDF phù hợp. Salt phải ngẫu nhiên và riêng cho từng bộ dữ liệu; KDF cần cấu hình đủ tốn kém để làm chậm brute-force. Web Crypto hỗ trợ PBKDF2; lựa chọn KDF cần cân nhắc browser support và hướng dẫn mật mã hiện hành.

Mô hình này có thể bảo vệ dữ liệu lưu trên đĩa khi người lấy dữ liệu không có passphrase. Nhưng nếu XSS chạy lúc người dùng nhập passphrase hoặc khi dữ liệu đã được mở, script có thể đánh cắp passphrase, gọi thao tác decrypt hoặc đọc plaintext. Không lưu passphrase hay derived key cùng ciphertext nếu mục tiêu là bảo vệ trước việc sao chép profile.

### 6.5. Mã hóa không thay thế data minimization

Cách giảm tác động tốt nhất thường là không lưu dữ liệu nhạy cảm nếu tính năng không cần. Nếu chỉ cần hiển thị tên, đừng lưu toàn bộ hồ sơ. Nếu chỉ cần trạng thái đơn hàng, đừng cache toàn bộ response tài khoản. Nếu dữ liệu chỉ cần trong vài phút, đừng giữ nó vô thời hạn.

## 7. Data minimization và phân loại dữ liệu

### 7.1. Thu thập đúng mục đích

Trước khi lưu, hãy hỏi:

- Tính năng có thật sự cần dữ liệu này ở client không?
- Có thể lấy dữ liệu từ server khi cần thay vì lưu bản sao không?
- Có thể chỉ lưu identifier không nhạy cảm thay vì toàn bộ record không?
- Dữ liệu có thể được xử lý trong memory rồi bỏ đi không?
- Có thể giảm độ chính xác, số trường hoặc số bản ghi không?

### 7.2. Phân loại theo mức độ nhạy cảm

Một phân loại đơn giản:

| Mức | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Công khai | Theme mặc định, danh sách public | Có thể cache theo policy |
| Nội bộ ít nhạy cảm | Tùy chọn UI, trạng thái tab | Web Storage phù hợp nếu cần |
| Cá nhân | Tên, email, lịch sử đơn hàng | Giảm trường dữ liệu, hạn chế retention, tránh cache không cần |
| Nhạy cảm | Vị trí chính xác, tài liệu riêng, thông tin tài chính | Chỉ lưu khi cần thiết; bảo vệ truy cập và thời gian lưu |
| Bí mật xác thực | Password, refresh token, session secret, recovery code | Tránh Web Storage; dùng thiết kế session/secret phù hợp |

Phân loại phải gắn với mục đích nghiệp vụ và yêu cầu pháp lý của tổ chức. Một trường dữ liệu tưởng ít nhạy cảm có thể trở nên nhạy cảm khi kết hợp với dữ liệu khác.

### 7.3. Tránh đưa secret vào URL và DOM

Không đưa token hoặc thông tin xác thực vào query string hoặc fragment:

```text
https://app.example.com/callback?access_token=SECRET
```

URL có thể xuất hiện trong history, log server/proxy, analytics, screenshot hoặc `Referer` tùy chính sách. Dùng flow xác thực chuẩn và truyền credential qua kênh phù hợp.

Cũng tránh đặt secret trong `data-*` attribute, hidden input, HTML comment hoặc global JavaScript object nếu không cần. Hidden field chỉ ẩn trên giao diện; JavaScript và người có quyền truy cập DOM vẫn đọc được.

### 7.4. Logging và telemetry

Không ghi dữ liệu nhạy cảm vào:

- `console.log()` trong production.
- Error message hoặc stack trace chứa request headers/body.
- Analytics event, replay tool hoặc session recording.
- URL, query string và referrer.
- Crash report hoặc diagnostic bundle.
- Log của service worker và background sync.

Mask/redact dữ liệu trước khi gửi telemetry. Có chính sách retention và quyền truy cập cho log như đối với storage chính.
## 8. Vòng đời an toàn của dữ liệu trong browser

Một thiết kế tốt xác định rõ thời điểm tạo, nơi lưu, mục đích sử dụng, thời hạn, cách thu hồi và cách xóa.

### 8.1. Create — chỉ tạo dữ liệu cần thiết

- Chỉ lưu trường dữ liệu mà tính năng cần.
- Không lưu password hoặc secret sau khi hoàn tất xác thực.
- Gắn owner/account context rõ ràng cho dữ liệu offline.
- Ghi metadata như schema version, createdAt và expiresAt khi cần.
- Không lưu dữ liệu cá nhân vào storage trước khi người dùng đồng ý nếu mục đích cần consent.

### 8.2. Read — kiểm tra quyền và tính hợp lệ

- Kiểm tra dữ liệu có thuộc tài khoản hiện tại không.
- Validate schema và version; không tin dữ liệu chỉ vì nó ở IndexedDB.
- Xử lý dữ liệu cũ, thiếu field hoặc bị sửa thủ công.
- Không đưa giá trị từ storage vào innerHTML hoặc dynamic code.
- Server vẫn kiểm tra quyền cho hành động nhạy cảm.

Dữ liệu trong browser có thể bị người dùng, extension, XSS hoặc công cụ developer sửa. Không dùng local state làm bằng chứng authorization hoặc số tiền/role có thẩm quyền.

### 8.3. Update — thay đổi có kiểm soát

- Cập nhật theo schema version và migration rõ ràng.
- Xóa field cũ khi không còn cần.
- Không để nhiều bản cache khác nhau giữ dữ liệu đã thay đổi quyền.
- Khi đổi tài khoản, không ghi đè hoặc trộn cache của hai user.
- Khi session hết hạn, vô hiệu hóa luồng đọc dữ liệu private.

### 8.4. Expire — hết hạn thực sự

`localStorage` và IndexedDB không tự hết hạn theo một trường `expiresAt`. Ứng dụng phải kiểm tra thời gian khi đọc và dọn dữ liệu:

```js
function readUnexpiredItem(key) {
  const raw = localStorage.getItem(key);
  if (!raw) return null;

  try {
    const item = JSON.parse(raw);

    if (!item || typeof item.expiresAt !== "number") {
      localStorage.removeItem(key);
      return null;
    }

    if (Date.now() >= item.expiresAt) {
      localStorage.removeItem(key);
      return null;
    }

    return item.value;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}
```

Đây là ví dụ cho dữ liệu không nhạy cảm. Client clock có thể sai hoặc bị người dùng thay đổi; expiry ở client không thay thế expiration và revocation ở server.

### 8.5. Logout — kết thúc phiên và dọn dữ liệu

Logout nên là một quy trình có thứ tự:

1. Gửi yêu cầu logout tới server để revoke/invalidate session nếu mô hình hỗ trợ.
2. Server xóa session cookie bằng `Set-Cookie` có cùng scope attributes phù hợp.
3. Dừng camera, microphone, WebSocket, timer và background task liên quan.
4. Xóa dữ liệu private trong `localStorage`, `sessionStorage`, IndexedDB và Cache Storage theo account namespace.
5. Xóa state trong memory và điều hướng về trang phù hợp.
6. Đảm bảo back-forward cache hoặc tab cũ không tiếp tục hiển thị dữ liệu riêng tư mà không kiểm tra session.

Không chỉ xóa cookie ở client rồi coi phiên đã bị thu hồi. Nếu server vẫn chấp nhận session identifier cũ, người có bản sao identifier có thể tiếp tục sử dụng phiên cho tới khi hết hạn.

### 8.6. Delete — xóa tất cả bản sao do ứng dụng quản lý

Dữ liệu có thể có nhiều bản sao:

- Web Storage.
- IndexedDB.
- Cache Storage.
- Cache của service worker.
- Memory của tab.
- Download hoặc file người dùng đã lưu.
- Server-side session, cache và bản sao đồng bộ.

Khi xóa, hãy xác định phạm vi dữ liệu mà ứng dụng kiểm soát và xóa theo account/user context. Không tuyên bố secure erase trên thiết bị nếu browser/OS/filesystem không cung cấp bảo đảm đó. Xóa key trong Web Storage không chứng minh mọi bản sao vật lý hoặc backup đã biến mất.

## 9. Mẫu quản lý dữ liệu không nhạy cảm

Ví dụ dưới đây lưu tùy chọn UI với schema version và thời hạn. Nó minh họa validation, error handling và cleanup; không dùng làm nơi lưu token hoặc secret.

```js
const UI_KEY = "ui-preferences-v1";
const UI_TTL_MS = 30 * 24 * 60 * 60 * 1000;

function saveUiPreferences(value) {
  const allowedThemes = new Set(["light", "dark", "system"]);

  if (!value || !allowedThemes.has(value.theme)) {
    throw new TypeError("Theme không hợp lệ");
  }

  const record = {
    version: 1,
    theme: value.theme,
    expiresAt: Date.now() + UI_TTL_MS
  };

  try {
    localStorage.setItem(UI_KEY, JSON.stringify(record));
  } catch (error) {
    // Storage có thể bị chặn hoặc hết quota.
    throw new Error("Không thể lưu tùy chọn UI", { cause: error });
  }
}

function loadUiPreferences() {
  let raw;

  try {
    raw = localStorage.getItem(UI_KEY);
  } catch {
    return { theme: "system" };
  }

  if (!raw) return { theme: "system" };

  try {
    const record = JSON.parse(raw);
    const allowedThemes = new Set(["light", "dark", "system"]);

    if (
      record?.version !== 1 ||
      !allowedThemes.has(record.theme) ||
      typeof record.expiresAt !== "number" ||
      Date.now() >= record.expiresAt
    ) {
      localStorage.removeItem(UI_KEY);
      return { theme: "system" };
    }

    return { theme: record.theme };
  } catch {
    localStorage.removeItem(UI_KEY);
    return { theme: "system" };
  }
}

function clearUiPreferences() {
  try {
    localStorage.removeItem(UI_KEY);
  } catch {
    // Tùy chọn UI có thể trở về giá trị mặc định trong memory.
  }
}
```

Ứng dụng thực tế cần xử lý trường hợp storage bị disable, quota exceeded hoặc dữ liệu bị sửa. Không lưu thông tin xác thực vào record này và không dùng dữ liệu client làm căn cứ cho quyết định server.

## 10. Xóa dữ liệu theo tài khoản và Cache Storage

### 10.1. Namespace dữ liệu

Nếu ứng dụng hỗ trợ nhiều tài khoản trên cùng browser profile, hãy tách dữ liệu offline theo account namespace:

```js
function userCacheName(userId) {
  // userId phải là identifier ổn định đã được xác thực, không phải dữ liệu tự khai từ UI.
  return "private-cache-" + encodeURIComponent(userId);
}
```

Namespace giúp tìm và dọn dữ liệu đúng tài khoản, nhưng không phải cơ chế authorization. Mã độc cùng origin vẫn có thể truy cập cache mà origin được phép mở. Server phải xác thực mọi request; client không được tự tin rằng userId trong cache key chứng minh danh tính.

### 10.2. Dọn Cache Storage của một tài khoản

```js
async function clearUserCaches(userId) {
  const prefix = userCacheName(userId);
  const names = await caches.keys();

  await Promise.all(
    names
      .filter(name => name === prefix || name.startsWith(prefix + "-"))
      .map(name => caches.delete(name))
  );
}
```

Chỉ xóa cache do ứng dụng quản lý và đã đặt namespace theo quy ước. Đừng xóa cache public dùng chung nếu không cần; cũng đừng giả định xóa Cache Storage sẽ xóa IndexedDB hoặc Web Storage.

### 10.3. Xóa IndexedDB

Có thể yêu cầu browser xóa database:

```js
function deleteDatabase(name) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name);

    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => {
      console.warn("Đóng các tab đang dùng database rồi thử lại.");
    };
  });
}
```

Nếu tab khác đang giữ kết nối, thao tác xóa có thể bị blocked. Ứng dụng nên đóng kết nối khi không cần và xử lý event `versionchange` để nhường đường cho migration hoặc deletion.

## 11. Kiểm tra dữ liệu nhạy cảm bằng DevTools

### 11.1. Application panel

Mở DevTools → Application (hoặc Storage tùy browser):

- Local Storage: kiểm tra key/value và token có bị lưu nhầm không.
- Session Storage: kiểm tra dữ liệu tạm có còn sau reload không.
- IndexedDB: kiểm tra database, object store và bản ghi.
- Cookies: xem `HttpOnly`, `Secure`, `SameSite`, Domain, Path và expiry.
- Cache Storage: kiểm tra response API/private có bị cache không.
- Network/HTTP cache: kiểm tra response riêng tư có `Cache-Control` phù hợp, ví dụ `no-store`, và không bị CDN/shared cache lưu ngoài dự kiến.
- Service Workers: xem scope và cache lifecycle.

Không chụp hoặc chia sẻ screenshot chứa token, cookie value, thông tin cá nhân hay nội dung tài khoản thật.

### 11.2. Console

Có thể kiểm tra loại storage đang có dữ liệu:

```js
console.table(
  Object.keys(localStorage).map(key => ({
    key,
    length: localStorage.getItem(key)?.length ?? 0
  }))
);
```

Đoạn này chỉ liệt kê tên key và độ dài value; không in nội dung. Với ứng dụng có dữ liệu nhạy cảm, dùng tài khoản thử nghiệm và xóa dữ liệu lab sau khi kiểm tra.

### 11.3. Network

Kiểm tra:

- Token có xuất hiện trong query string hoặc fragment không.
- Request có gửi cookie đúng scope không.
- Response API private có cache header phù hợp không.
- Service worker có intercept/cache response nhạy cảm không.
- Logout có revoke session server-side và xóa cookie không.
- Response có vô tình chứa dữ liệu nhiều hơn giao diện cần không.

### 11.4. Kiểm thử XSS exposure có kiểm soát

Trong môi trường local/staging và với dữ liệu giả, có thể mô phỏng script cùng origin đọc Web Storage:

```js
const keys = Object.keys(localStorage);
console.log("Các key có thể truy cập bởi script cùng origin:", keys);
```

Không gửi dữ liệu ra ngoài. Mục đích là xác nhận script trong origin có thể nhìn thấy storage nào và từ đó đánh giá hậu quả của XSS. Với cookie `HttpOnly`, thử đọc `document.cookie` sẽ không trả cookie đó, nhưng có thể kiểm tra rằng request same-origin vẫn tự đính kèm cookie trong Network.

## 12. Ma trận kiểm thử

| Mã | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| STORE-01 | XSS giả lập đọc `localStorage` | Nhận diện được dữ liệu mà script cùng origin có thể đọc |
| STORE-02 | Session cookie có `HttpOnly` | JavaScript không đọc được giá trị cookie |
| STORE-03 | XSS gửi request same-origin khi có session cookie | Server vẫn yêu cầu CSRF/origin và authorization phù hợp |
| STORE-04 | Logout trên một tài khoản | Session bị revoke server-side và dữ liệu private được dọn |
| STORE-05 | Đăng nhập tài khoản khác trên cùng profile | Cache và IndexedDB của user cũ không bị hiển thị |
| STORE-06 | Dữ liệu local hết hạn | Ứng dụng không sử dụng record hết hạn |
| STORE-07 | JSON storage bị sửa hoặc sai schema | Ứng dụng loại bỏ hoặc migrate an toàn |
| STORE-08 | Browser chặn storage hoặc hết quota | Có fallback và thông báo phù hợp |
| STORE-09 | Service worker cache response private | Cache policy không giữ dữ liệu sau logout |
| STORE-10 | Dữ liệu có trong URL hoặc log | Không xuất hiện token/secret hoặc trường nhạy cảm |
| STORE-11 | CryptoKey không extractable nhưng XSS đang chạy | Không giả định key chống được việc XSS yêu cầu decrypt |
| STORE-12 | Browser profile bị sao chép khi app đã khóa | Mã hóa chỉ bảo vệ nếu khóa không nằm cùng bản sao |
| STORE-13 | Người dùng thu hồi session ở server | Request tiếp theo bằng session cũ bị từ chối |
| STORE-14 | Cache/IndexedDB đang mở ở tab khác khi xóa | Deletion xử lý blocked/versionchange đúng |
| STORE-15 | Storage chứa dữ liệu dư thừa | Chỉ lưu trường tối thiểu cần cho tính năng |
| STORE-16 | Dữ liệu private được tải lại từ server | Server xác thực và authorize, không tin cache key phía client |

## 13. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| `localStorage` an toàn vì chỉ nằm trên máy người dùng | Script cùng origin có thể đọc và sửa dữ liệu |
| IndexedDB an toàn hơn localStorage trước XSS | Cả hai đều có thể bị JavaScript cùng origin truy cập |
| `sessionStorage` chắc chắn bị xóa ngay khi đóng tab | Vòng đời phụ thuộc browser/page session; không dùng làm bảo đảm xóa bí mật |
| Cookie `HttpOnly` ngăn XSS | Nó ngăn đọc cookie trực tiếp; XSS vẫn có thể dùng phiên để gửi request |
| `SameSite` thay thế CSRF token trong mọi trường hợp | SameSite là một lớp bảo vệ; đánh giá CSRF theo kiến trúc và browser |
| Mã hóa dữ liệu trong localStorage là đủ | Nếu khóa có thể lấy hoặc dùng trong cùng origin, XSS có thể lấy plaintext |
| Non-extractable CryptoKey chống mọi XSS | Nó ngăn export key; không ngăn script độc hại yêu cầu thao tác crypto |
| Dữ liệu client có thể dùng làm nguồn authorization | Client storage có thể bị sửa; server phải xác minh quyền |
| Logout chỉ cần xóa localStorage | Cần revoke session, xóa cookie/cache/database và dừng tác vụ liên quan |
| Xóa key đồng nghĩa secure erase | Browser/OS có thể còn bản sao, journal, backup hoặc cache |
| Cache API chỉ chứa asset public | Service worker có thể lưu cả response riêng tư nếu code cho phép |
| URL fragment không bao giờ bị lộ | Script, extension, history hoặc telemetry vẫn có thể tiếp cận URL; không đặt secret trong URL |
| Có HTTPS thì dữ liệu trong browser đã được bảo vệ khỏi XSS | HTTPS bảo vệ đường truyền; XSS là mã chạy trong origin |
| Lưu ít dữ liệu làm ứng dụng kém tiện lợi | Có thể cache có chọn lọc, giới hạn thời gian và tải lại khi cần |

## 14. Checklist thiết kế storage an toàn

- [ ] Lập danh mục dữ liệu và phân loại độ nhạy cảm.
- [ ] Xác định threat model: XSS, script bên thứ ba, thiết bị dùng chung, malware và profile backup.
- [ ] Chỉ lưu dữ liệu client khi có mục đích rõ ràng.
- [ ] Không lưu password, recovery secret hoặc refresh token dài hạn trong Web Storage.
- [ ] Ưu tiên BFF và session cookie `HttpOnly; Secure; SameSite` khi phù hợp.
- [ ] Giới hạn cookie bằng host-only hoặc `__Host-` khi có thể; tránh Domain rộng không cần thiết.
- [ ] Bảo vệ request dùng cookie bằng CSRF defense phù hợp.
- [ ] Dùng memory cho dữ liệu ngắn hạn khi kiến trúc cho phép, nhưng vẫn coi XSS là đối thủ.
- [ ] Đặt expiry cho dữ liệu offline và kiểm tra expiry khi đọc.
- [ ] Tách namespace cache theo user/account và dọn khi đổi tài khoản.
- [ ] Không cache response private nếu không có yêu cầu và chính sách rõ.
- [ ] Kiểm tra HTTP cache riêng với Cache Storage; đặt `Cache-Control: no-store` cho response nhạy cảm khi phù hợp.
- [ ] Không đưa token/secret vào URL, DOM attribute, console hoặc telemetry.
- [ ] Chỉ dùng Web Crypto với thuật toán chuẩn và quản lý khóa được review.
- [ ] Không coi encryption at rest hoặc non-extractable key là biện pháp chống XSS.
- [ ] Có logout/revoke server-side, xóa cookie đúng scope và dọn browser storage.
- [ ] Xử lý service worker, IndexedDB, Cache Storage và tab khác khi cleanup.
- [ ] Kiểm tra bằng DevTools với dữ liệu giả, không chia sẻ secret trong screenshot.
- [ ] Xác minh server luôn xác thực và authorize hành động, không tin dữ liệu client.

### Ghi nhớ

**Browser storage là vùng dữ liệu của origin, không phải secret vault chống XSS.** JavaScript cùng origin có thể đọc Web Storage, IndexedDB và Cache Storage; cookie `HttpOnly` ngăn đọc giá trị cookie nhưng không ngăn XSS dùng phiên để gửi request. Mã hóa phía client có thể bảo vệ bản sao dữ liệu khi khóa được giữ độc lập và ứng dụng chưa mở khóa, nhưng không bảo vệ plaintext trước script độc hại đang chạy. Hãy giảm dữ liệu lưu, chọn storage theo mục đích, giới hạn thời gian tồn tại, bảo vệ session ở server và thiết kế logout/revoke/deletion cho mọi bản sao do ứng dụng quản lý.
