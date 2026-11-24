# Kiểm thử browser security

## Mục tiêu

Kiểm thử browser security là quá trình xác minh các ranh giới tin cậy mà trình duyệt thực thi giữa trang web, origin, cookie, storage, tài nguyên nhúng và ứng dụng phía máy chủ. Bài thực hành này kết hợp nhiều cơ chế thành một lượt kiểm thử xuyên suốt, từ chuẩn bị môi trường, dựng threat model, kiểm tra hành vi trên trình duyệt đến ghi nhận bằng chứng và đánh giá kết quả.

Một ứng dụng web có thể dùng HTTPS và vẫn gặp lỗi bảo mật ở tầng trình duyệt: JavaScript không an toàn ghi dữ liệu vào DOM, CORS cho phép origin lạ đọc response có credentials, cookie được gửi trong request ngoài ý muốn, trang quản trị bị nhúng trong iframe, Service Worker lưu dữ liệu cá nhân hoặc cache phân phối response sai phiên. Vì vậy, cần kiểm tra cách các cơ chế phối hợp trên cùng một luồng người dùng.

Sau bài này, bạn có thể:

- Lập phạm vi và ma trận kiểm thử browser security cho một ứng dụng web.
- Kiểm tra origin, Same-Origin Policy (SOP), CORS, cookie và CSRF trên các luồng xác thực.
- Phát hiện DOM XSS bằng cách truy vết source, transformation và sink; xác minh CSP và Trusted Types.
- Kiểm tra clickjacking, security headers, storage, HTTP cache và Service Worker.
- Tự động hóa các ca kiểm thử phù hợp bằng Playwright hoặc công cụ tương đương.
- Thu thập bằng chứng có thể tái hiện, phân loại phát hiện và đề xuất biện pháp khắc phục.

## 1. Phạm vi và mô hình kiểm thử

### 1.1. Các lớp cần kiểm tra

| Lớp | Câu hỏi trọng tâm | Cơ chế liên quan |
|---|---|---|
| Origin và tài nguyên | Trang có đọc được dữ liệu từ origin khác ngoài ý muốn không? | SOP, CORS, iframe, postMessage |
| Phiên và request | Cookie/credential được gửi trong ngữ cảnh nào? Request thay đổi trạng thái có được bảo vệ không? | Secure, HttpOnly, SameSite, CSRF token, Origin validation |
| DOM và script | Dữ liệu không tin cậy có đi vào sink nguy hiểm không? | Output encoding, CSP, Trusted Types |
| Giao diện và frame | Trang nhạy cảm có thể bị nhúng và thao tác qua lớp phủ không? | frame-ancestors, X-Frame-Options |
| Storage và cache | Dữ liệu có tồn tại sau đăng xuất, đổi tài khoản hoặc thu hồi quyền không? | localStorage, sessionStorage, IndexedDB, Cache API, HTTP cache, bfcache |
| Tài nguyên và kết nối | Trình duyệt có tải tài nguyên, mở kết nối hoặc gửi referrer ngoài dự kiến không? | CSP, Referrer-Policy, CORP, COOP, COEP, Permissions-Policy |
| Quan sát và vận hành | Có phát hiện được lỗi policy và hồi quy sau phát hành không? | CSP Reporting, browser telemetry, DevTools, log máy chủ |

### 1.2. Mô hình môi trường mẫu

Dùng ba origin giả lập trong staging:

- Ứng dụng chính: https://app.example.test
- API: https://api.example.test
- Origin không tin cậy dùng để kiểm thử: https://attacker.example.test

Có thể bổ sung một origin đối tác đã được phê duyệt để kiểm tra allowlist CORS. Các domain trên chỉ là ví dụ; thay bằng hostname trong môi trường lab của bạn.

Mô hình luồng:

~~~mermaid
flowchart LR
  U[Người dùng] --> A[Browser: app.example.test]
  A -->|Cookie / API request| API[api.example.test]
  A -->|Load scripts, images, frames| R[Static resources]
  X[attacker.example.test] -->|Cross-origin request / iframe| A
  X -->|Request with browser credentials, if allowed| API
  A -->|CSP reports / telemetry| T[Telemetry collector]
  API --> L[Auth and access logs]
  R --> C[CDN / shared cache]
~~~

Trong mô hình này, trình duyệt là nơi thực thi SOP, CORS, CSP, cookie policy và framing policy. API vẫn phải tự xác thực và phân quyền; không được giao quyết định quyền truy cập cho JavaScript phía client.

### 1.3. Chuẩn bị dữ liệu thử nghiệm

Tạo hai tài khoản giả A và B với dữ liệu nhận diện khác nhau, ví dụ tên hiển thị TEST-A và TEST-B. Chuẩn bị:

- Một trang hồ sơ cá nhân có API đọc dữ liệu.
- Một thao tác thay đổi trạng thái như cập nhật tên hiển thị.
- Một trường tìm kiếm hoặc ghi chú hiển thị lại dữ liệu người dùng nhập.
- Một trang nhạy cảm như quản trị hoặc xác nhận thanh toán để kiểm tra framing.
- Một tài nguyên tĩnh công khai có thể cache.
- Một endpoint telemetry thử nghiệm.

Không dùng tài khoản thật, dữ liệu khách hàng, cookie phiên production hoặc payload gây tác động ra ngoài môi trường được phép. Dùng hồ sơ trình duyệt riêng để tách session; cần thêm một lượt thử đổi A sang B trong cùng hồ sơ để phát hiện dữ liệu còn sót.

## 2. Chuẩn bị công cụ và bằng chứng

### 2.1. DevTools

Trong Chrome hoặc Edge:

1. Mở DevTools trước khi bắt đầu lượt kiểm thử.
2. Trong Network, bật Preserve log để giữ request qua điều hướng.
3. Kiểm tra request document, fetch/XHR, OPTIONS, script, frame và response header.
4. Trong Application, xem Cookies, Local Storage, Session Storage, IndexedDB, Cache Storage và Service Workers.
5. Trong Console, ghi nhận lỗi CSP, CORS, Trusted Types và lỗi JavaScript.
6. Dùng tab Security để kiểm tra trạng thái kết nối và chứng chỉ khi cần.

Tùy chọn Disable cache chỉ dùng trong lượt so sánh riêng. Khi kiểm tra cache có hoạt động hay không, phải tắt Disable cache và ghi lại điều kiện thử. Không chia sẻ HAR nguyên bản nếu nó chứa cookie, Authorization header, query string hoặc nội dung response nhạy cảm.

### 2.2. Công cụ dòng lệnh

curl giúp quan sát response header và kiểm tra phản hồi máy chủ:

~~~bash
curl -sS -D - -o /dev/null https://app.example.test/
curl -sS -D - -o /dev/null https://api.example.test/api/profile
~~~

curl không thực thi SOP, CORS, cookie policy hoặc CSP. Nó không thể thay thế kiểm thử trên browser thật. Khi dùng curl để thử CORS, chỉ kết luận được máy chủ trả header gì:

~~~bash
curl -i \
  -H 'Origin: https://attacker.example.test' \
  https://api.example.test/api/profile
~~~

### 2.3. Quy tắc ghi nhận

Mỗi bằng chứng cần có:

- ID ca kiểm thử và thời điểm UTC.
- Browser family, phiên bản, hệ điều hành và cấu hình privacy liên quan.
- Origin nguồn, URL đích đã loại bỏ dữ liệu nhạy cảm và trạng thái đăng nhập.
- Request method, status, các header liên quan và nguồn response.
- Kết quả mong đợi, kết quả thực tế và bước tái hiện.
- Ảnh chụp hoặc log đã che cookie, token, dữ liệu cá nhân.
- Mức độ tin cậy và giới hạn quan sát.

Không dùng một ảnh chụp Console đơn lẻ để kết luận lỗi đã bị khai thác. Kết hợp request/response, trạng thái trình duyệt và kết quả nghiệp vụ.

## 3. Kiểm thử origin, SOP và CORS

### 3.1. Xác minh ranh giới origin

Origin được tạo bởi scheme, hostname và port. Các URL khác scheme hoặc port là khác origin, kể cả khi cùng hostname. Hai subdomain cũng là hai origin khác nhau.

Thực hiện:

1. Mở ứng dụng tại origin chính.
2. Tạo request đến API cùng origin và API ở origin khác.
3. Thử đọc một tài nguyên cross-origin không có CORS cho phép.
4. Thử một request đến API có CORS allowlist.
5. Quan sát Network và Console để xác định request có được gửi, response có được chia sẻ cho JavaScript hay không.

Kết quả mong đợi: trang chỉ đọc được response cross-origin khi máy chủ cho phép theo CORS. Không suy ra rằng trình duyệt không gửi request chỉ vì Console hiển thị lỗi CORS; request đơn giản có thể đã đến máy chủ.

### 3.2. Ma trận CORS

| Trường hợp | Kết quả mong đợi |
|---|---|
| Origin chính được allowlist | JavaScript đọc được response theo hợp đồng API |
| Origin đối tác đã phê duyệt | Được phép đúng route và method cần thiết |
| Origin không tin cậy | Không có response header cho phép đọc |
| Origin giả dạng bằng hậu tố, sai scheme hoặc port | Bị từ chối |
| Origin null | Bị từ chối trừ trường hợp sử dụng đặc biệt đã được phê duyệt |
| Request credentials include | ACAO là origin cụ thể; ACAC là true nếu thực sự cần credentials |
| Request cần preflight | OPTIONS chỉ cho phép origin, method và header cần thiết |
| Request đơn giản thay đổi trạng thái | CSRF protection ở máy chủ vẫn từ chối request không hợp lệ |

Với response động theo Origin, kiểm tra Vary: Origin. Với response cá nhân, áp dụng cache policy phù hợp, thường là private hoặc no-store; Vary: Origin không cách ly dữ liệu giữa hai người dùng cùng origin.

### 3.3. Kiểm tra preflight và request thực tế

Dùng request thử nghiệm yêu cầu method PATCH và header X-CSRF-Token. Quan sát:

1. Browser có gửi OPTIONS không?
2. Access-Control-Allow-Origin có khớp origin chính xác không?
3. Access-Control-Allow-Methods có bao gồm PATCH không?
4. Access-Control-Allow-Headers có liệt kê các header cần thiết không?
5. Khi preflight bị từ chối, browser có dừng trước request PATCH không?
6. Khi preflight thành công, request thực tế có được xác thực và phân quyền không?

Preflight không gửi credentials của request thực tế. Máy chủ không được coi việc OPTIONS thành công là xác thực người dùng. Trình duyệt có thể cache kết quả preflight theo Access-Control-Max-Age; khi kiểm tra thay đổi policy, dùng browser profile mới hoặc chờ cache hết hạn.

### 3.4. postMessage và iframe

Nếu ứng dụng trao đổi dữ liệu với iframe hoặc popup:

- Kiểm tra event.origin trước khi xử lý message.
- Kiểm tra event.source khi cần xác nhận đúng cửa sổ/iframe mong đợi.
- Dùng danh sách origin chính xác; không dùng so sánh chuỗi con.
- Tránh gửi token, dữ liệu cá nhân hoặc lệnh nhạy cảm trong message nếu không cần.
- Dùng targetOrigin cụ thể khi gửi message; tránh wildcard cho dữ liệu nhạy cảm.
- Kiểm tra message type và schema trước khi thực hiện hành động.

Ví dụ xử lý message an toàn hơn:

~~~javascript
const trustedOrigin = "https://app.example.test";

window.addEventListener("message", (event) => {
  if (event.origin !== trustedOrigin) return;
  if (event.source !== window.parent) return;

  const data = event.data;
  if (!data || data.type !== "resize" || typeof data.height !== "number" || !Number.isFinite(data.height)) {
    return;
  }

  const height = Math.max(100, Math.min(data.height, 1200));
  document.documentElement.style.setProperty("--frame-height", height + "px");
});
~~~

Ví dụ này chạy trong iframe con và chỉ nhận message từ parent. Với popup, cần kiểm tra window.opener hoặc source tương ứng. Đoạn mã chỉ là mẫu kiểm tra một message đơn giản; với message thực tế, cần schema validation đầy đủ, giới hạn tần suất và kiểm tra quyền trước khi thực hiện hành động có tác động.

## 4. Kiểm thử cookie, session và CSRF

### 4.1. Kiểm tra thuộc tính cookie

Trong DevTools Application → Cookies, kiểm tra cookie phiên:

| Thuộc tính | Kết quả mong đợi |
|---|---|
| Secure | Cookie phiên chỉ được gửi qua HTTPS |
| HttpOnly | JavaScript không đọc trực tiếp được cookie phiên |
| SameSite | Chọn Strict, Lax hoặc None theo luồng sản phẩm; None yêu cầu Secure |
| Domain | Ưu tiên host-only cookie khi không cần chia sẻ subdomain |
| Path | Giới hạn phạm vi cần thiết; không xem Path là ranh giới bảo mật mạnh |
| Expires/Max-Age | Thời hạn phù hợp; session rotation và revoke vẫn được xử lý ở server |
| Prefix | Cân nhắc __Host- cho cookie host-only: Secure, Path=/ và không có Domain |

HttpOnly giảm khả năng đọc cookie bằng JavaScript nhưng không ngăn XSS thực hiện request trong phiên người dùng. SameSite giảm một số request cross-site có cookie, nhưng không thay thế CSRF token hoặc kiểm tra phía server. Hai subdomain cùng site vẫn có thể khác origin.

### 4.2. Kiểm tra vòng đời phiên

Dùng tài khoản thử nghiệm A:

1. Đăng nhập và ghi nhận cookie attributes, không lưu giá trị cookie.
2. Mở trang cá nhân và gọi API được bảo vệ.
3. Đăng xuất.
4. Thử gọi lại API bằng phiên cũ trong cùng browser context.
5. Đăng nhập lại và kiểm tra session ID được xoay vòng theo thiết kế.
6. Thu hồi phiên ở server rồi thử lại bằng credential cũ.
7. Lặp lại với tài khoản B trong cùng browser profile.

Kết quả mong đợi: API từ chối credential đã hết hạn hoặc bị thu hồi; đăng xuất vô hiệu hóa phiên phía server theo thiết kế; dữ liệu A không xuất hiện trong phiên B.

### 4.3. Kiểm tra CSRF

Chọn một thao tác thay đổi trạng thái không gây hậu quả, ví dụ cập nhật tên hiển thị của tài khoản thử nghiệm.

Thực hiện các ca:

- Request hợp lệ có CSRF token đúng.
- Request thiếu token.
- Request có token sai hoặc token thuộc phiên khác.
- Request có Origin không hợp lệ.
- Request POST dạng form đơn giản từ origin khác.
- Request GET đến endpoint chỉ đọc; xác minh GET không làm thay đổi trạng thái.

Kết quả mong đợi: chỉ request hợp lệ được chấp nhận. Server phải kiểm tra token gắn với phiên và quyền nghiệp vụ. Origin/Referer validation và SameSite là lớp bổ sung. CORS không ngăn mọi request cross-origin, đặc biệt là request đơn giản.

Không thực hiện thử nghiệm thay đổi mật khẩu, thanh toán, xóa dữ liệu hoặc thao tác production. Dùng fixture có thể khôi phục.

## 5. Kiểm thử XSS, CSP và Trusted Types

### 5.1. Truy vết source-to-sink

Với mỗi trường nhập liệu được hiển thị lại, xác định:

- **Source:** query string, fragment, form input, postMessage, API response, storage hoặc dữ liệu từ URL.
- **Transformation:** decode, parse, template rendering, sanitize, format hoặc nối chuỗi.
- **Sink:** innerHTML, outerHTML, insertAdjacentHTML, document.write, eval, setTimeout với chuỗi hoặc API tạo script/style.

Kiểm tra từng context: HTML text, HTML attribute, URL, JavaScript, CSS và DOM. Cách encode phụ thuộc context; encode HTML không tự bảo vệ mọi sink JavaScript, URL hoặc CSS.

Ưu tiên DOM API an toàn như textContent, createElement và setAttribute cho thuộc tính đã được xác định là không thực thi; với URL, style hoặc thuộc tính có khả năng kích hoạt hành vi, cần kiểm tra giá trị theo allowlist riêng. Khi cần render rich text, dùng sanitizer được duy trì, cấu hình allowlist và kiểm thử các trường hợp đầu vào độc hại.

### 5.2. Thử nghiệm DOM XSS an toàn

Trong trang lab, nhập chuỗi đánh dấu vô hại để xác định dữ liệu được render dưới dạng text hay HTML. Có thể dùng một payload kiểm thử có side effect giới hạn trong trang như:

~~~html
<img src=x onerror="document.documentElement.dataset.xssTest='triggered'">
~~~

Chỉ sử dụng trong fixture cục bộ/staging được phép. Không dùng payload gửi dữ liệu ra ngoài, đọc cookie, chiếm phiên hoặc chạy lệnh. Quan sát:

1. Chuỗi xuất hiện dưới dạng text hay tạo thành element?
2. Event handler có thực thi không?
3. DOM sink nào nhận dữ liệu?
4. Sanitizer có loại bỏ thuộc tính và URL nguy hiểm không?
5. Kết quả có khác nhau giữa route hoặc browser không?

Kết quả đạt: dữ liệu không tin cậy được hiển thị như text hoặc qua sanitizer có chính sách rõ ràng; không có script/event handler ngoài ý muốn thực thi.

### 5.3. Kiểm tra CSP

Kiểm tra header thực tế trên từng route và từng response document. Một policy khởi đầu có thể gồm:

~~~http
Reporting-Endpoints: csp="https://telemetry.example.test/reports/csp"
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; report-to csp; report-uri https://telemetry.example.test/reports/csp
~~~

Đây là ví dụ cấu trúc, cần điều chỉnh theo tài nguyên thật. Nonce phải được sinh ngẫu nhiên cho mỗi response HTML, không dùng lại giữa các response và phải khớp chính xác với script được cho phép. Nếu dùng CDN cache HTML, cần bảo đảm nonce trong header và HTML luôn đồng bộ.

Kiểm tra các directive:

| Directive | Điều cần xác minh |
|---|---|
| default-src | Fallback không vô tình mở nguồn rộng |
| script-src / script-src-elem | Chỉ cho phép script hợp lệ; tránh unsafe-inline và unsafe-eval nếu không có lý do |
| object-src | Thường đặt none |
| base-uri | Ngăn thay đổi base URL ngoài ý muốn |
| frame-ancestors | Giới hạn origin có thể nhúng trang |
| form-action | Giới hạn nơi form được submit |
| connect-src | Giới hạn fetch, XHR, WebSocket và EventSource |
| img-src / style-src / font-src | Chỉ cho phép nguồn cần thiết |
| upgrade-insecure-requests | Cân nhắc khi ứng dụng có thể chuyển toàn bộ tài nguyên HTTP sang HTTPS |

Quy trình:

1. Triển khai Content-Security-Policy-Report-Only trong staging.
2. Thực hiện các luồng chính, thu thập vi phạm và phân loại false positive.
3. Sửa nguồn tài nguyên hợp lệ hoặc code phụ thuộc policy cũ.
4. Chuyển sang enforce và xác nhận script ngoài policy bị chặn.
5. Kiểm tra các route, trang lỗi, trang đăng nhập, iframe và tài nguyên CDN.
6. Theo dõi CSP report theo route và phiên bản phát hành.

Report-only chỉ báo cáo; nó không chặn hành vi. report-uri là cơ chế cũ có thể giữ để tương thích với trình duyệt chưa hỗ trợ Reporting API; endpoint phải xử lý đúng định dạng báo cáo của từng cơ chế. Báo cáo CSP có thể thiếu hoặc bị giả mạo, vì vậy không dùng một report đơn lẻ làm bằng chứng khai thác thành công.

### 5.4. Kiểm tra Trusted Types

Nếu ứng dụng hỗ trợ và có DOM sink cần bảo vệ, thử policy:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app
~~~

Kiểm tra các sink như innerHTML và API tạo script. Khi enforcement bật, phép gán chuỗi thông thường vào sink được bảo vệ phải bị từ chối trong trình duyệt hỗ trợ.

Trusted Types không tự sanitize dữ liệu. Policy tạo TrustedHTML phải gọi sanitizer đã được đánh giá và không được biến mọi chuỗi thành trusted value một cách tùy tiện. Kiểm thử:

- Luồng hợp lệ dùng policy được phê duyệt.
- Luồng không tin cậy không thể tự tạo policy tùy ý.
- Policy không có bypass kiểu trả nguyên chuỗi.
- Browser không hỗ trợ Trusted Types vẫn có biện pháp output encoding và sanitizer phù hợp.

## 6. Kiểm thử clickjacking và framing

### 6.1. Kiểm tra header chống nhúng

Trên trang nhạy cảm, kiểm tra:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Nếu sản phẩm cần nhúng trang từ một origin cụ thể, dùng frame-ancestors với danh sách chính xác. X-Frame-Options là cơ chế cũ hơn; CSP frame-ancestors là lựa chọn hiện đại. frame-ancestors phải được gửi qua response header và không có tác dụng khi đặt trong meta tag.

### 6.2. Kiểm thử bằng iframe

Trong origin kiểm thử không tin cậy, tạo trang chứa iframe trỏ đến route nhạy cảm. Quan sát:

- Trang có tải được trong frame không?
- Console/Network có báo vi phạm frame-ancestors hoặc X-Frame-Options không?
- Các route khác nhau có header nhất quán không?
- Trang đăng nhập, trang lỗi và trang redirect có được bảo vệ không?
- Có luồng tích hợp hợp lệ nào bị chặn ngoài dự kiến không?

Kết quả đạt: route không được nhúng từ origin ngoài danh sách. Nếu có trường hợp cho phép nhúng, cần xác định rõ origin được phép và kiểm thử các thao tác nhạy cảm trong frame.

Không chỉ kiểm tra trang chủ. Kẻ tấn công có thể nhắm đến route con, trang xác nhận hoặc endpoint UI có tác động.

## 7. Kiểm thử storage, HTTP cache và Service Worker

### 7.1. Rà soát browser storage

Trong DevTools Application, kiểm tra:

| Kho lưu trữ | Rủi ro |
|---|---|
| localStorage | Dữ liệu tồn tại lâu và có thể đọc bởi JavaScript cùng origin |
| sessionStorage | Dữ liệu tồn tại theo tab/session; vẫn có thể đọc bởi script cùng origin |
| IndexedDB | Có thể chứa dữ liệu lớn, bản sao API hoặc thông tin cá nhân |
| Cache Storage | Service Worker có thể chủ động lưu response |
| Cookies | Tự động gửi theo domain/path/SameSite và thuộc tính bảo vệ |

Không lưu access token dài hạn hoặc bí mật có giá trị cao trong nơi JavaScript cùng origin đọc được nếu kiến trúc có thể tránh. Khi đăng xuất hoặc đổi tài khoản, xác định rõ dữ liệu nào phải xóa, dữ liệu nào được phép giữ và điều kiện tái xác thực trước khi dùng lại.

### 7.2. Kiểm tra HTTP cache

Đối với response cá nhân, kiểm tra Cache-Control phù hợp, thường là private, no-store. Với nội dung công khai có phiên bản, có thể dùng max-age dài và tên file có hash.

Thực hiện:

1. Đăng nhập A, tải trang hồ sơ và ghi nhận nguồn response.
2. Đăng xuất A, đăng nhập B trong cùng browser profile.
3. Mở lại URL hồ sơ, nhấn Back và thử reload.
4. Kiểm tra dữ liệu hiển thị, Network source, Age, ETag và Cache-Control.
5. Lặp lại trên browser profile mới.

Kết quả đạt: dữ liệu A không được hiển thị cho B hoặc phiên đã đăng xuất. Kiểm tra bfcache riêng vì nó khôi phục snapshot tài liệu và không đồng nghĩa với HTTP cache. Khi trang được khôi phục, ứng dụng cần kiểm tra trạng thái phiên/quyền trước khi tiếp tục cho phép thao tác nhạy cảm.

### 7.3. Kiểm tra Cache API và Service Worker

Trong Application → Service Workers và Cache Storage:

- Xác định worker nào kiểm soát trang và scope của worker.
- Kiểm tra script URL, phiên bản và luồng cập nhật.
- Liệt kê các request đã lưu trong Cache Storage.
- Xác định API cá nhân hoặc response có credentials có bị lưu không.
- Kiểm tra dữ liệu được xóa hoặc làm mới sau logout, đổi tài khoản và thu hồi quyền.
- Kiểm tra luồng offline có trả dữ liệu cũ mà không xác minh trạng thái phiên không.

Cache API không tự áp dụng Cache-Control theo cách HTTP cache thực hiện; mã Service Worker phải tự quản lý mục cache. Không lưu response riêng tư vào cache dùng chung giữa các tài khoản. Khi cache tài nguyên tĩnh, giới hạn rõ đường dẫn và loại nội dung công khai.

Có thể liệt kê cache entries trong Console cùng origin:

~~~javascript
async function inspectCacheStorage() {
  const names = await caches.keys();
  const entries = [];

  for (const name of names) {
    const cache = await caches.open(name);
    const requests = await cache.keys();

    for (const request of requests) {
      entries.push({
        cacheName: name,
        method: request.method,
        url: new URL(request.url).pathname,
      });
    }
  }

  console.table(entries);
}

inspectCacheStorage();
~~~

Ví dụ chỉ hiển thị pathname để tránh in query string có thể chứa mã định danh. Không copy danh sách cache có URL nhạy cảm vào báo cáo phổ biến.

## 8. Kiểm tra security headers và isolation

Kiểm tra header trên response HTML và API liên quan. Không phải header nào cũng cần cùng một giá trị cho mọi route.

| Header | Mục tiêu | Kiểm tra |
|---|---|---|
| Strict-Transport-Security | Buộc trình duyệt dùng HTTPS sau khi nhận policy | Chỉ bật trên HTTPS; cân nhắc includeSubDomains/preload sau khi xác minh mọi subdomain |
| X-Content-Type-Options: nosniff | Ngăn MIME sniffing trong các ngữ cảnh liên quan | Kiểm tra Content-Type chính xác cho script/style |
| Referrer-Policy | Giới hạn thông tin referrer gửi sang nơi khác | Chọn policy phù hợp, thường cân nhắc strict-origin-when-cross-origin |
| Permissions-Policy | Giới hạn tính năng trình duyệt như camera, microphone, geolocation | Chỉ bật tính năng cần thiết cho từng route |
| Cross-Origin-Opener-Policy | Cô lập browsing context group trong các trường hợp phù hợp | Kiểm tra popup, OAuth và tích hợp thanh toán |
| Cross-Origin-Resource-Policy | Giới hạn cách origin khác tải tài nguyên | Xác minh ảnh, font và tài nguyên nhúng hợp lệ |
| Cross-Origin-Embedder-Policy | Yêu cầu điều kiện nhúng tài nguyên để đạt cross-origin isolation | Kiểm tra toàn bộ tài nguyên và API phụ thuộc trước khi bật |
| X-Frame-Options | Cơ chế tương thích cũ để hạn chế framing | Dùng cùng chính sách frame-ancestors phù hợp |

Không bật COEP, COOP hoặc HSTS preload hàng loạt mà không kiểm thử tác động đến OAuth popup, thanh toán, tài nguyên CDN, subdomain và ứng dụng nhúng. Mục tiêu là chọn policy phù hợp với kiến trúc và xác minh hành vi thực tế.

## 9. Tự động hóa kiểm thử browser security

### 9.1. Nguyên tắc tự động hóa

Tự động hóa tốt cho các hành vi ổn định và có thể tái hiện:

- Header bảo mật trên từng route.
- CORS allowlist và preflight.
- Cookie attributes.
- CSRF rejection.
- Framing policy.
- Luồng logout và đổi tài khoản.
- CSP violation trong fixture kiểm thử.
- Cache không lẫn dữ liệu giữa hai user.

Một số hành vi phụ thuộc browser version, privacy settings, extension hoặc chính sách cookie bên thứ ba. Với các trường hợp này, giữ browser matrix và kiểm thử thủ công bổ sung.

### 9.2. Ví dụ Playwright kiểm tra header

Đoạn test minh họa; thay route và header theo policy thực tế:

~~~javascript
import { test, expect } from "@playwright/test";

test("sensitive page has browser security headers", async ({ request }) => {
  const response = await request.get("https://app.example.test/account");
  expect(response.ok()).toBeTruthy();

  const headers = response.headers();

  expect(headers["content-security-policy"]).toBeTruthy();
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBeTruthy();
  expect(headers["strict-transport-security"]).toBeTruthy();
});
~~~

Request API của Playwright không mô phỏng đầy đủ việc trình duyệt thực thi CSP, CORS, cookie SameSite hoặc bfcache. Dùng browser page/context cho các ca phụ thuộc browser policy.

### 9.3. Ví dụ kiểm tra hai tài khoản không lẫn dữ liệu

~~~javascript
import { test, expect } from "@playwright/test";

test("account data is isolated after switching users", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto("https://app.example.test/test-login?user=A");
  await page.goto("https://app.example.test/account/profile");
  await expect(page.getByTestId("display-name")).toHaveText("TEST-A");

  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("https://app.example.test/test-login?user=B");
  await page.goto("https://app.example.test/account/profile");

  await expect(page.getByTestId("display-name")).toHaveText("TEST-B");
  await expect(page.getByText("TEST-A")).toHaveCount(0);

  await context.close();
});
~~~

Luồng đăng nhập trong ví dụ chỉ dành cho fixture staging. Test cần xác minh trạng thái server và response API, không chỉ text đang hiển thị trong DOM. Có thể thêm assertion cho request sau logout và response khi dùng session cũ.

### 9.4. Ví dụ kiểm tra framing

~~~javascript
import { test, expect } from "@playwright/test";

test("sensitive page declares a framing restriction", async ({ request }) => {
  const response = await request.get("https://app.example.test/admin");
  expect(response.ok()).toBeTruthy();

  const csp = response.headers()["content-security-policy"] || "";
  expect(csp).toContain("frame-ancestors 'none'");
});
~~~

Test này xác nhận header được phát hành. Cần thêm một lượt browser thật từ origin không tin cậy để thử nhúng route và xác nhận nội dung nhạy cảm không thể được hiển thị trong frame; request API của Playwright không thực thi framing policy.

### 9.5. Ví dụ kiểm tra CORS bằng browser context

~~~javascript
import { test, expect } from "@playwright/test";

test("untrusted origin cannot read private API response", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();

  // Route đăng nhập này chỉ tồn tại trong fixture staging và tạo cookie phiên thử nghiệm.
  await page.goto("https://api.example.test/test-login?user=A");
  await page.goto("https://attacker.example.test/");

  const result = await page.evaluate(async () => {
    try {
      const response = await fetch("https://api.example.test/api/profile", {
        credentials: "include",
      });
      await response.text();
      return "readable";
    } catch {
      return "blocked";
    }
  });

  expect(result).toBe("blocked");
  await context.close();
});
~~~

Test này chỉ có ý nghĩa nếu fixture thực sự tạo được session cần thiết và request chạy trong browser với cấu hình cookie xác định. Cần có ca dương tính từ origin hợp lệ để chứng minh endpoint hoạt động. Không xem kết quả blocked là bằng chứng API không nhận request; kiểm tra access log để xác định request đã đến server hay chưa.

## 10. Ma trận kiểm thử tổng hợp

| ID | Nhóm | Ca kiểm thử | Kết quả đạt |
|---|---|---|---|
| BS-01 | Origin/SOP | Đọc tài nguyên từ origin khác không có CORS | JavaScript không đọc được response |
| BS-02 | CORS | Origin không tin cậy gọi API có credentials | Không đọc được dữ liệu riêng tư |
| BS-03 | CORS | Preflight với method/header không được phép | Browser không gửi request thực tế |
| BS-04 | Cookie | Kiểm tra Secure, HttpOnly, SameSite và Domain | Thuộc tính đúng với mô hình phiên |
| BS-05 | Session | Dùng credential sau logout/revoke | API từ chối |
| BS-06 | CSRF | Request thay đổi trạng thái thiếu token | Server từ chối |
| BS-07 | XSS | Dữ liệu không tin cậy đi vào DOM sink | Không thực thi script ngoài ý muốn |
| BS-08 | CSP | Thử script ngoài policy trong enforce | Browser chặn và ghi nhận vi phạm |
| BS-09 | Trusted Types | Gán string thường vào sink được bảo vệ | Browser hỗ trợ từ chối thao tác |
| BS-10 | Clickjacking | Nhúng trang nhạy cảm từ origin lạ | Trang không được render trong frame |
| BS-11 | Storage | Đăng xuất rồi đổi tài khoản | Không còn dữ liệu riêng tư của user trước |
| BS-12 | Cache | Cùng URL qua hai tài khoản | Không phân phối chéo response |
| BS-13 | Service Worker | Kiểm tra Cache Storage và offline | Không lưu/tái sử dụng dữ liệu cá nhân ngoài policy |
| BS-14 | Headers | Kiểm tra CSP, HSTS, nosniff, Referrer-Policy | Header phù hợp trên route cần bảo vệ |
| BS-15 | Telemetry | Tạo vi phạm CSP trong fixture | Collector nhận event đã giảm thiểu dữ liệu |
| BS-16 | Browser matrix | Chạy luồng chính trên các browser mục tiêu | Không có sai khác bảo mật ngoài dự kiến |

Trạng thái mỗi ca nên là PASS, FAIL, BLOCKED hoặc NOT APPLICABLE. BLOCKED cần ghi rõ điều kiện chưa đáp ứng; NOT APPLICABLE cần có lý do và người xác nhận.

## 11. Phân loại phát hiện và ưu tiên xử lý

Đánh giá mức độ dựa trên tác động, khả năng khai thác, điều kiện cần, phạm vi dữ liệu và các lớp giảm thiểu hiện có.

| Mức | Ví dụ |
|---|---|
| Critical | Origin không tin cậy đọc được dữ liệu nhạy cảm có credentials trên diện rộng; XSS thực thi trong origin quản trị và cho phép thao tác đặc quyền |
| High | CSRF thực hiện được thao tác quan trọng; cookie phiên bị lộ hoặc session cũ tiếp tục dùng được; clickjacking thao tác tài chính không có xác nhận |
| Medium | CSP thiếu directive quan trọng nhưng chưa chứng minh được đường khai thác; cache hoặc storage giữ dữ liệu cá nhân trong điều kiện hạn chế |
| Low | Header thiếu trên route ít nhạy cảm, thông tin referrer vượt nhu cầu hoặc policy chưa đồng nhất nhưng chưa tạo đường truy cập đáng kể |

Không gán mức chỉ từ tên lỗi. Ví dụ, thiếu HSTS trên một subdomain không chứa dữ liệu có thể có tác động khác với thiếu HSTS trên origin xác thực. Cần ghi rõ bằng chứng, điều kiện khai thác và giới hạn.

## 12. Báo cáo kết quả

Mỗi phát hiện nên có cấu trúc:

- **Finding ID và tiêu đề:** ngắn, mô tả hành vi.
- **Severity:** mức độ và lý do.
- **Affected route/origin:** phạm vi đã xác định.
- **Preconditions:** trạng thái đăng nhập, browser, cookie và điều kiện mạng.
- **Steps to reproduce:** bước tái hiện trong staging bằng dữ liệu giả.
- **Expected vs actual:** hành vi mong đợi và thực tế.
- **Evidence:** request/response header, ảnh chụp đã che dữ liệu, log và test result.
- **Impact:** dữ liệu hoặc thao tác có thể bị ảnh hưởng.
- **Root cause:** code, cấu hình, quy trình hoặc thiếu kiểm soát.
- **Remediation:** thay đổi cụ thể và owner.
- **Retest criteria:** điều kiện kiểm chứng sau sửa.

Ví dụ phát hiện:

| Trường | Nội dung |
|---|---|
| ID | BS-02 |
| Tiêu đề | API hồ sơ phản chiếu origin không tin cậy khi bật credentials |
| Severity | High nếu dữ liệu cá nhân đọc được bằng phiên hợp lệ; cần xác nhận phạm vi |
| Bằng chứng | Browser context từ origin thử nghiệm đọc được response fixture; API trả ACAO trùng origin và ACAC true |
| Nguyên nhân | Middleware không dùng allowlist |
| Khắc phục | Allowlist theo scheme/host/port, giới hạn route/method/header và thêm Vary khi response động theo Origin |
| Retest | Origin hợp lệ đọc được; origin không hợp lệ không đọc được; request thay đổi trạng thái vẫn qua CSRF protection |

Không ghi token, cookie, dữ liệu cá nhân hoặc payload đầy đủ vào phần mô tả có quyền truy cập rộng.

## 13. Quy trình thực hành từ đầu đến cuối

Thực hiện theo trình tự:

1. **Scope:** chọn route, origin, tài khoản giả và browser mục tiêu.
2. **Baseline:** ghi lại response header, cookie attributes, storage và trạng thái Service Worker.
3. **Origin/CORS:** thử origin hợp lệ, không hợp lệ, preflight và credentials.
4. **Session/CSRF:** kiểm tra logout, revoke, đổi tài khoản và request thay đổi trạng thái.
5. **DOM/XSS:** truy vết source-to-sink, thử fixture vô hại và kiểm tra CSP/Trusted Types.
6. **Framing:** thử nhúng route nhạy cảm từ origin ngoài.
7. **Storage/cache:** kiểm tra HTTP cache, bfcache, Cache Storage và dữ liệu tồn dư.
8. **Headers/isolation:** xác minh policy trên từng response và luồng tích hợp.
9. **Automation:** chạy test hồi quy và browser matrix.
10. **Report:** phân loại phát hiện, lưu bằng chứng đã lọc, giao owner và tiêu chí retest.

Sau khi sửa, chạy lại toàn bộ ca liên quan và các luồng có thể bị ảnh hưởng. Không đóng finding chỉ vì header đã xuất hiện; phải xác minh hành vi browser và API đã thay đổi đúng như mong đợi.

## 14. Checklist hoàn tất

- [ ] Phạm vi, origin, route và tài khoản thử nghiệm đã xác định.
- [ ] Đã kiểm tra SOP và CORS bằng browser thật.
- [ ] Đã kiểm tra preflight, credentials và các biến thể Origin.
- [ ] Đã xác minh cookie attributes, logout, rotation và revoke.
- [ ] Đã kiểm tra CSRF trên request thay đổi trạng thái.
- [ ] Đã truy vết DOM source-to-sink và kiểm tra XSS trong fixture an toàn.
- [ ] Đã kiểm tra CSP report-only và enforce.
- [ ] Đã xác minh Trusted Types trên browser hỗ trợ.
- [ ] Đã kiểm tra frame-ancestors và khả năng nhúng route nhạy cảm.
- [ ] Đã rà soát localStorage, sessionStorage, IndexedDB và Cache Storage.
- [ ] Đã kiểm tra HTTP cache, bfcache và đổi tài khoản.
- [ ] Đã kiểm tra Service Worker scope, cập nhật và offline behavior.
- [ ] Đã xác minh security headers và các policy isolation phù hợp.
- [ ] Đã chạy browser matrix và test hồi quy.
- [ ] Bằng chứng đã che cookie, token, URL nhạy cảm và dữ liệu cá nhân.
- [ ] Mỗi finding có severity, owner, remediation và retest criteria.

Kiểm thử browser security hoàn tất khi các ranh giới origin và phiên hoạt động đúng, dữ liệu không tin cậy không thể thực thi script ngoài ý muốn, request thay đổi trạng thái được bảo vệ, trang nhạy cảm không bị nhúng trái phép, cache/storage không làm lộ dữ liệu giữa các phiên và các policy có thể được kiểm chứng trên những trình duyệt sản phẩm hỗ trợ.
