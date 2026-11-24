# Dùng local storage mà không xét XSS

Lưu access token hoặc refresh token trong `localStorage` có vẻ thuận tiện vì ứng dụng có thể đọc token sau khi tải lại trang. Nhưng `localStorage` được truy cập trực tiếp bằng JavaScript của cùng origin. Nếu ứng dụng có lỗ hổng Cross-Site Scripting (XSS), mã độc chạy trong origin đó có thể đọc và gửi token ra ngoài. Kẻ tấn công sau đó có thể dùng token như một Bearer credential cho đến khi token hết hạn, bị thu hồi hoặc bị chặn bởi cơ chế ràng buộc bổ sung.

Bài học thuộc chương **Lỗi thường gặp** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung giải thích rủi ro khi lưu token trong browser storage, cách chọn mô hình BFF hoặc SPA phù hợp, vai trò của cookie `HttpOnly`, `Secure`, `SameSite`, phòng chống XSS/CSRF, vòng đời refresh token và cách kiểm thử kiến trúc lưu trữ.

## 1. Vấn đề nằm ở đâu?

`localStorage` là kho lưu trữ key/value theo origin. JavaScript chạy trong trang có thể gọi `localStorage.getItem()` để đọc dữ liệu. Điều này phù hợp với dữ liệu giao diện không nhạy cảm, nhưng khiến `localStorage` không thích hợp để giữ bí mật có quyền truy cập như access token hoặc refresh token khi ứng dụng có nguy cơ XSS.

Một lỗi XSS có thể xuất hiện từ:

- Render HTML không tin cậy bằng `innerHTML` hoặc API tương tự mà không sanitize đúng cách.
- Hiển thị nội dung do người dùng nhập mà thiếu output encoding theo ngữ cảnh.
- Dùng template hoặc framework theo cách bỏ qua cơ chế escape mặc định.
- Thư viện bên thứ ba, tag manager, analytics hoặc dependency bị xâm nhập.
- Trang quản trị, trang hỗ trợ hoặc một sub-route ít được kiểm thử nhưng cùng origin với ứng dụng chính.

Nếu script độc hại chạy được trong origin của ứng dụng, Same-Origin Policy không ngăn script đó đọc `localStorage` của chính origin. Kẻ tấn công không cần phá mã hóa TLS hay giả mạo chữ ký JWT; họ chỉ cần khiến trình duyệt thực thi JavaScript dưới quyền của trang.

## 2. Chuỗi tấn công: XSS dẫn đến token theft

Một tình huống phổ biến:

1. Người dùng đăng nhập và nhận access token, refresh token.
2. SPA lưu token vào `localStorage` để dùng lại sau khi tải trang.
3. Ứng dụng hiển thị nội dung không tin cậy và có lỗ hổng XSS.
4. Attacker khiến mã JavaScript chạy trong origin của ứng dụng.
5. Script đọc token từ `localStorage` và gửi ra máy chủ do attacker kiểm soát.
6. Attacker phát lại token để gọi API từ một thiết bị hoặc mạng khác.

~~~mermaid
flowchart TD
    A["Người dùng đăng nhập"] --> B["SPA nhận access/refresh token"]
    B --> C["Token được lưu trong localStorage"]
    D["Dữ liệu không tin cậy đi vào DOM"] --> E["Lỗ hổng XSS"]
    E --> F["JavaScript độc hại chạy cùng origin"]
    C --> F
    F --> G["Đọc token và gửi ra ngoài"]
    G --> H["Attacker phát lại Bearer token"]
    H --> I["API có thể chấp nhận đến khi token hết hạn hoặc bị thu hồi"]
~~~

Token vẫn có thể hợp lệ về chữ ký, issuer, audience và thời hạn. Vì vậy, Resource Server không thể chỉ dựa vào các kiểm tra JWT thông thường để biết token đã bị lấy cắp. Đây là lý do cần giảm khả năng token bị đọc, giới hạn tuổi thọ, hỗ trợ thu hồi và quan sát hành vi sử dụng bất thường.

## 3. localStorage thực sự bảo vệ điều gì?

| Đặc tính | localStorage |
| --- | --- |
| Phạm vi truy cập | JavaScript cùng origin có thể đọc/ghi |
| Thời gian tồn tại | Thường tồn tại qua lần đóng/mở browser cho đến khi bị xóa |
| Gửi tự động trong HTTP request | Không; ứng dụng thường tự gắn token vào header |
| Bảo vệ trước XSS cùng origin | Không |
| Bảo vệ bằng mã hóa tích hợp | Không có cơ chế mã hóa bí mật mặc định |
| Chống token replay nếu bị sao chép | Không |

Mã hóa token trước khi ghi vào `localStorage` thường không giải quyết được vấn đề nếu khóa giải mã cũng nằm trong JavaScript hoặc có thể truy cập từ cùng origin. Khi XSS chạy trong cùng ngữ cảnh, script có thể gọi chính hàm giải mã hoặc đọc khóa mà ứng dụng sử dụng.

`sessionStorage` và IndexedDB cũng không phải nơi cất bí mật an toàn trước XSS. Chúng có vòng đời và API khác nhau, nhưng JavaScript cùng origin vẫn có thể truy cập dữ liệu. Chuyển token từ `localStorage` sang `sessionStorage` có thể giảm thời gian tồn tại sau khi đóng tab, nhưng không loại bỏ khả năng script độc hại đọc token khi trang đang hoạt động.

## 4. So sánh các lựa chọn lưu trữ token

| Mô hình | Ưu điểm | Rủi ro / giới hạn |
| --- | --- | --- |
| Access token trong memory | Không tồn tại lâu qua lần tải lại trang; giảm dữ liệu lưu bền vững | XSS vẫn có thể đọc hoặc sử dụng token khi ứng dụng đang chạy |
| Access/refresh token trong localStorage | Dễ khôi phục phiên sau reload | JavaScript cùng origin và XSS có thể đọc token; token tồn tại lâu |
| Token trong sessionStorage | Dữ liệu gắn với tab/session | JavaScript cùng origin vẫn đọc được; không ngăn XSS |
| Token trong IndexedDB | Hỗ trợ dữ liệu có cấu trúc và bất đồng bộ | Vẫn truy cập được bằng JavaScript cùng origin |
| Token trong cookie HttpOnly | JavaScript không đọc trực tiếp cookie | Browser tự gửi cookie; cần bảo vệ CSRF; XSS vẫn có thể gửi request cùng origin |
| BFF giữ OAuth token phía server | Browser chỉ giữ session cookie; access/refresh token không đi vào JavaScript | Cần vận hành backend session, CSRF protection và quản lý token server-side |

Với ứng dụng web có backend, **Backend-for-Frontend (BFF)** thường là lựa chọn tốt để giữ access token và refresh token ngoài browser JavaScript. Browser chỉ nhận session cookie có thuộc tính bảo mật; BFF gọi Resource Server bằng token lưu phía server.

Với SPA thuần không có backend riêng, access token chỉ giữ trong memory có thể giảm rủi ro tồn tại lâu hơn so với `localStorage`, nhưng không biến token thành bí mật trước XSS. Cần kết hợp Authorization Code Flow với PKCE, phòng chống XSS, thời hạn token ngắn và cơ chế refresh được thiết kế thận trọng.

## 5. Mô hình khuyến nghị: BFF giữ token phía server

Trong mô hình BFF:

1. Browser chuyển hướng người dùng đến Authorization Server để đăng nhập.
2. Authorization Server trả authorization code về callback của BFF.
3. BFF đổi code lấy token qua back channel, xác minh response và lưu token trong server-side session/token store.
4. Browser chỉ nhận session cookie ngẫu nhiên, không chứa access token hoặc refresh token.
5. Browser gọi BFF; BFF xác thực session, kiểm tra CSRF và gọi Resource Server bằng access token.
6. Khi access token hết hạn, BFF sử dụng refresh token phía server theo chính sách rotation.

~~~mermaid
sequenceDiagram
    participant Browser
    participant BFF
    participant AS as Authorization Server
    participant API as Resource Server
    Browser->>BFF: Bắt đầu đăng nhập
    BFF->>AS: Authorization Code + PKCE
    AS-->>BFF: Authorization code qua callback
    BFF->>AS: Đổi code qua HTTPS back channel
    AS-->>BFF: Access token + Refresh token
    BFF-->>Browser: Session cookie HttpOnly, Secure
    Browser->>BFF: Request + session cookie + CSRF proof
    BFF->>BFF: Xác minh session và CSRF
    BFF->>API: Request + Bearer access token
    API-->>BFF: Kết quả API
    BFF-->>Browser: Kết quả ứng dụng
~~~

Lợi ích chính là OAuth token không được đưa vào storage mà JavaScript của browser có thể đọc. BFF vẫn phải bảo vệ session cookie, endpoint, CSRF và server-side token store. Nếu XSS xảy ra, script vẫn có thể thực hiện hành động thông qua phiên browser đang đăng nhập, nhưng khó lấy token thô để mang sang thiết bị khác và sử dụng độc lập.

## 6. Cấu hình session cookie đúng cách

Với session cookie của BFF, cấu hình tham khảo:

~~~http
Set-Cookie: __Host-app_session=<opaque-random-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ý nghĩa:

- `HttpOnly`: JavaScript không thể đọc cookie qua `document.cookie`.
- `Secure`: browser chỉ gửi cookie qua kết nối HTTPS.
- `SameSite=Lax`: giảm một số request cross-site tự động gửi cookie; cần chọn Strict/Lax/None theo flow đăng nhập và tích hợp.
- `Path=/`: cookie có hiệu lực trên toàn host.
- Prefix `__Host-`: browser yêu cầu cookie có `Secure`, `Path=/` và không có thuộc tính `Domain`, giúp giới hạn cookie ở host đã đặt.

Không đặt access token hoặc refresh token trực tiếp vào cookie chỉ vì cookie có `HttpOnly`. Ưu tiên cookie chứa session ID ngẫu nhiên, khó đoán; BFF ánh xạ session ID sang token phía server. Session ID cần được xoay vòng sau đăng nhập hoặc thay đổi quyền quan trọng, có idle timeout và absolute timeout.

Nếu phải dùng cookie cross-site, thường cần `SameSite=None; Secure`; khi đó cần đánh giá kỹ CSRF, CORS, third-party cookie restrictions và chính sách trình duyệt. `SameSite` là một lớp phòng vệ, không nên là biện pháp CSRF duy nhất.

## 7. Cookie và CSRF: bảo vệ XSS không đồng nghĩa bỏ qua CSRF

Khác với Bearer token do JavaScript tự gắn vào `Authorization` header, cookie được browser tự động gửi theo quy tắc domain/path/samesite. Vì vậy, cookie session có thể tạo bề mặt Cross-Site Request Forgery (CSRF).

Các biện pháp nên kết hợp:

1. Dùng anti-CSRF token gắn với session hoặc cơ chế double-submit cookie được triển khai đúng.
2. Kiểm tra `Origin` và/hoặc `Referer` cho request thay đổi trạng thái khi phù hợp.
3. Dùng `SameSite=Lax` hoặc `Strict` nếu flow cho phép; chỉ dùng `None` khi thực sự cần cross-site.
4. Không dùng GET cho hành động thay đổi trạng thái.
5. Cấu hình CORS theo allowlist origin cụ thể; không phản chiếu origin tùy ý khi bật credentials.
6. Xác minh CSRF token ở BFF trước khi gọi Resource Server cho thao tác nhạy cảm.

**CORS không thay thế CSRF protection.** CORS chủ yếu kiểm soát việc JavaScript đọc response cross-origin; một số request cross-site vẫn có thể được gửi mà không cần JavaScript đọc response. `SameSite` cũng không ngăn script XSS cùng origin thực hiện request hợp lệ.

## 8. Nếu SPA gọi API trực tiếp

Không phải hệ thống nào cũng có thể triển khai BFF ngay. Với SPA public client:

- Dùng OAuth 2.0 Authorization Code Flow với PKCE (`S256`); không dùng Implicit Flow cho ứng dụng mới.
- Xác minh `state`, `nonce` khi flow yêu cầu, issuer và redirect URI chính xác.
- Giữ access token trong memory nếu có thể; không lưu refresh token dài hạn trong `localStorage`.
- Nếu Authorization Server cho phép cấp refresh token cho browser public client, áp dụng rotation, reuse detection, giới hạn lifetime và ràng buộc client theo chính sách; hiểu rõ refresh token vẫn có thể bị sử dụng bởi XSS khi script đang chạy.
- Cân nhắc DPoP hoặc sender-constrained token nếu Authorization Server và Resource Server hỗ trợ, nhưng không xem đây là cách loại bỏ XSS.
- Dùng HTTPS cho mọi endpoint, không đưa token vào URL, query string, fragment, log hoặc analytics.
- Khi reload, nếu không có session cookie hoặc cơ chế cấp token an toàn, có thể yêu cầu người dùng đăng nhập lại thay vì lưu bí mật dài hạn trong browser storage.

Ví dụ gọi API khi access token chỉ được giữ trong memory:

~~~javascript
let accessToken = null;

export function setAccessToken(token) {
  accessToken = token;
}

export async function loadProfile() {
  if (!accessToken) {
    throw new Error("No active access token");
  }

  const response = await fetch("/api/profile", {
    headers: {
      Authorization: "Bearer " + accessToken
    }
  });

  if (!response.ok) {
    throw new Error("Profile request failed: " + response.status);
  }

  return response.json();
}
~~~

Ví dụ này chỉ minh họa vị trí lưu access token trong memory. Nó **không** bảo vệ token khỏi XSS: script độc hại có thể gọi API của ứng dụng, đọc state qua các đường tích hợp hoặc sử dụng quyền của phiên đang hoạt động. Cần kết hợp phòng chống XSS và vòng đời token phù hợp.

Với BFF, frontend không cần nhận token:

~~~javascript
export async function loadProfile(csrfToken) {
  const response = await fetch("/bff/profile", {
    method: "GET",
    credentials: "same-origin",
    headers: {
      "Accept": "application/json",
      "X-CSRF-Token": csrfToken
    }
  });

  if (!response.ok) {
    throw new Error("Profile request failed: " + response.status);
  }

  return response.json();
}
~~~

Với request GET không thay đổi trạng thái, CSRF token có thể không bắt buộc tùy policy; ví dụ trên minh họa việc truyền token khi BFF yêu cầu. Các request POST/PUT/PATCH/DELETE cần kiểm tra CSRF theo hợp đồng ứng dụng. Browser tự gửi session cookie; JavaScript không cần và không thể đọc cookie `HttpOnly`.

## 9. Phòng chống XSS ở lớp ứng dụng

Không có lựa chọn storage nào thay thế được việc sửa lỗ hổng XSS. Nên áp dụng phòng vệ theo nhiều lớp:

### Output encoding và sanitization

- Escape dữ liệu theo đúng ngữ cảnh HTML, attribute, URL, JavaScript hoặc CSS.
- Dùng cơ chế auto-escaping của framework; tránh API render raw HTML khi không cần.
- Nếu phải cho phép rich text/HTML do người dùng nhập, dùng sanitizer đã được duy trì và cấu hình allowlist chặt.
- Tránh ghép chuỗi để tạo HTML hoặc script.
- Không đưa dữ liệu không tin cậy vào `innerHTML`, `outerHTML`, `document.write`, event handler inline hoặc các DOM sink nguy hiểm.

### Content Security Policy (CSP)

CSP là lớp giảm tác động khi có lỗi injection. Ví dụ policy cần điều chỉnh theo ứng dụng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{per-response-random}'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types app
~~~

Nonce phải ngẫu nhiên, khó đoán và sinh riêng cho mỗi response; chỉ gắn nonce vào script được phép. Không thêm `unsafe-inline` hoặc `unsafe-eval` một cách tùy tiện. `require-trusted-types-for 'script'` và `trusted-types` hỗ trợ giảm DOM XSS trên browser có triển khai Trusted Types; cần có fallback và kiểm thử tương thích.

Triển khai CSP trước ở chế độ Report-Only để thu thập vi phạm, điều chỉnh allowlist rồi mới enforce. Report endpoint phải lọc dữ liệu nhạy cảm và chống abuse.

### Quản lý dependency và script bên thứ ba

- Giảm số lượng script bên thứ ba có quyền chạy trong origin ứng dụng.
- Tự host script khi phù hợp; pin version và cập nhật dependency theo quy trình.
- Dùng Subresource Integrity (SRI) cho tài nguyên cross-origin tĩnh khi khả thi.
- Kiểm soát tag manager, analytics, chat widget và script hỗ trợ khách hàng.
- Tách ứng dụng nhạy cảm khỏi origin chứa nội dung không tin cậy khi kiến trúc cho phép.

## 10. Refresh token, logout và thu hồi phiên

Nếu ứng dụng giữ refresh token trong browser storage, một XSS có thể lấy token để xin access token mới. Việc access token ngắn hạn không đủ nếu refresh token bị lộ và có thể tiếp tục được dùng.

Nên áp dụng:

- Refresh token rotation và phát hiện reuse theo token family.
- Giới hạn absolute lifetime và idle lifetime.
- Ràng buộc refresh token với client/session và sender-constrained mechanism khi phù hợp.
- Revoke refresh token family khi nghi ngờ compromise.
- Không ghi token vào log, browser console, error tracking hoặc analytics.
- Khi logout, xóa state phía browser và yêu cầu BFF/Authorization Server hủy session hoặc revoke token theo chính sách.

Xóa một giá trị khỏi `localStorage` chỉ xóa bản sao phía browser hiện tại; nó không làm token đã bị sao chép mất hiệu lực. Nếu nghi ngờ token đã bị exfiltrate, phải revoke token/refresh family hoặc session tại nơi có thẩm quyền, kiểm tra propagation và xử lý các access token còn hiệu lực. Với JWT tự chứa, thu hồi tức thời có thể cần denylist, introspection, session/version check hoặc thời hạn access token ngắn.

## 11. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| `localStorage` an toàn vì cùng origin | XSS chạy trong origin có thể đọc storage đó |
| Chuyển token sang `sessionStorage` là hết XSS | JavaScript cùng origin vẫn đọc được trong thời gian tab hoạt động |
| Mã hóa token trước khi lưu là đủ | Nếu code/khóa giải mã có thể truy cập từ cùng origin, XSS có thể gọi chúng |
| Cookie `HttpOnly` loại bỏ XSS | Cookie khó bị đọc trực tiếp, nhưng XSS vẫn có thể gửi request bằng phiên đang đăng nhập |
| Cookie `SameSite` loại bỏ mọi CSRF | Cần đánh giá flow và kết hợp anti-CSRF/Origin validation |
| CORS chặn mọi request cross-site | CORS không ngăn mọi request được gửi và không thay thế CSRF defense |
| Access token ngắn hạn làm refresh token an toàn | Refresh token bị đánh cắp vẫn có thể duy trì quyền truy cập |
| Logout bằng cách xóa localStorage là thu hồi token | Bản sao token ở nơi khác vẫn có thể hoạt động |
| CSP là cách sửa mọi XSS | CSP là lớp phòng vệ bổ sung; vẫn cần sửa injection và DOM sink |

## 12. Kiểm thử bảo mật cho kiến trúc lưu trữ

Kiểm thử cần bao gồm cả hành vi browser, BFF, Authorization Server và Resource Server. Dùng token giả dành riêng cho test, không dùng credential thật.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Đăng nhập SPA theo thiết kế memory-only | Không có access/refresh token trong localStorage, sessionStorage hoặc IndexedDB |
| BFF đăng nhập thành công | Browser chỉ nhận session cookie; token được giữ phía server |
| JavaScript gọi `document.cookie` trong BFF | Không đọc được cookie session `HttpOnly` |
| Browser gửi request đến BFF | Session cookie được gửi theo đúng Secure/SameSite/Path/host policy |
| Request thay đổi trạng thái thiếu CSRF proof | BFF từ chối |
| Request có Origin không được phép | BFF từ chối theo policy |
| XSS canary chạy trong môi trường test | Không thể đọc token từ storage trong thiết kế không lưu token ở browser; CSP/sanitizer ghi nhận hoặc chặn payload theo policy |
| XSS canary gọi endpoint BFF | Kiểm tra giới hạn thực tế: XSS có thể hành động trong phiên, do đó cần bảo vệ thao tác nhạy cảm và phát hiện bất thường |
| Refresh token cũ được dùng lại sau rotation | Authorization Server phát hiện reuse và áp dụng token family policy |
| Logout BFF | Session phía server bị vô hiệu hóa; cookie được xóa với đúng thuộc tính |
| Token bị nghi exfiltrate | Revoke/containment được kiểm tra ở Authorization Server và Resource Server |
| CSP Report-Only nhận vi phạm | Report không chứa token hoặc dữ liệu nhạy cảm |

Test XSS nên chạy trên fixture và origin cô lập. Dùng payload canary không gửi dữ liệu thật ra Internet; xác minh bằng một tín hiệu test an toàn. Không đưa token thực vào test payload hoặc report.

## 13. Checklist lựa chọn và vận hành

- [ ] Đã đánh giá XSS theo toàn bộ origin, gồm trang quản trị và script bên thứ ba.
- [ ] Không lưu access token/refresh token dài hạn trong `localStorage`.
- [ ] Ưu tiên BFF khi ứng dụng có backend và cần giữ OAuth token khỏi JavaScript.
- [ ] Nếu SPA gọi API trực tiếp, dùng Authorization Code + PKCE và giới hạn token trong memory khi có thể.
- [ ] Hiểu rằng memory-only vẫn có rủi ro XSS trong thời gian ứng dụng hoạt động.
- [ ] Nếu dùng cookie, bật `HttpOnly`, `Secure`, `SameSite` và cấu hình host/path phù hợp.
- [ ] BFF có CSRF token hoặc cơ chế tương đương, kiểm tra Origin và không dùng GET cho mutation.
- [ ] CORS chỉ cho phép origin cần thiết; không bật credentials với wildcard origin.
- [ ] Có output encoding, sanitizer, CSP và Trusted Types khi phù hợp.
- [ ] Giảm script bên thứ ba, quản lý dependency và dùng SRI khi khả thi.
- [ ] Refresh token có rotation, reuse detection, lifetime và revoke policy.
- [ ] Logout vô hiệu hóa server-side session/token theo chính sách; xóa storage chỉ là bước phía client.
- [ ] Log, analytics, trace và error reporting không chứa token hoặc Authorization header.
- [ ] Có integration test cho XSS, CSRF, cookie attributes, refresh rotation và logout.

## 14. Tình huống tổng hợp

Một SPA lưu access token và refresh token trong `localStorage` để người dùng không phải đăng nhập lại sau reload. Trang hồ sơ cho phép hiển thị phần mô tả do người dùng nhập bằng cách gán trực tiếp vào `innerHTML`. Attacker gửi nội dung chứa script; khi nhân viên hỗ trợ mở trang, script chạy trong origin của ứng dụng và đọc token.

Chữ ký JWT vẫn hợp lệ nên API tiếp tục chấp nhận access token cho đến khi token hết hạn hoặc bị thu hồi. Attacker còn có refresh token nên có thể xin access token mới nếu Authorization Server chưa phát hiện reuse hoặc chưa revoke family.

Hướng xử lý:

1. Sửa DOM sink bằng output encoding hoặc sanitizer phù hợp; bổ sung CSP và kiểm thử XSS.
2. Thu hồi refresh token family và session bị ảnh hưởng; xác minh các Resource Server đã nhận trạng thái revoke.
3. Đánh giá access token đã phát hành, dữ liệu API đã truy cập và thời gian compromise.
4. Chuyển kiến trúc sang BFF nếu phù hợp; browser chỉ giữ session cookie `HttpOnly`, `Secure`, `SameSite`.
5. Bổ sung CSRF defense cho BFF và kiểm thử lại luồng mutation.
6. Thêm alert cho refresh token reuse, token usage bất thường và truy cập nhạy cảm.

**Điều cần nhớ:** `localStorage` không phải kho bí mật trước JavaScript cùng origin. Muốn giảm rủi ro token theft, cần kết hợp lựa chọn kiến trúc lưu trữ phù hợp, phòng chống XSS, CSRF defense khi dùng cookie, token lifetime/rotation/revocation và kiểm thử toàn bộ luồng đăng nhập đến API.

## 15. Tài liệu chuẩn tham khảo

- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): khuyến nghị bảo mật OAuth 2.0 hiện đại, gồm Authorization Code + PKCE và bảo vệ refresh token.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): vai trò access token, refresh token và authorization server.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): PKCE cho public client.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): lưu ý bảo mật với Web Storage và dữ liệu phía browser.
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding và phòng chống XSS.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): cookie, SameSite và CSRF defense.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session cookie, timeout, rotation và logout.
