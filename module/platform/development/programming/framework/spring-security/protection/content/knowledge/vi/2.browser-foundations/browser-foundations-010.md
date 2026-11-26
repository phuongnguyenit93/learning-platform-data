# Nguy cơ từ mã chạy trong trang và từ yêu cầu phát sinh bên ngoài

## Mục tiêu bài học

Trong một ứng dụng web, hai hành vi nhìn bên ngoài có vẻ tương tự nhau lại có **ranh giới quyền rất khác**:

1. **Mã chạy ngay trong trang ứng dụng**, ví dụ JavaScript chính chủ, thư viện bên thứ ba được nhúng hoặc mã bị chèn bởi lỗ hổng **Cross-Site Scripting (XSS)**.
2. **Mã hoặc trang ở một website khác** muốn kích hoạt yêu cầu đến ứng dụng, ví dụ form POST, điều hướng, tải tài nguyên hay fetch cross-origin. Nhóm này liên quan **Cross-Site Request Forgery (CSRF)**, clickjacking và một số kiểu rò rỉ thông tin qua hành vi trình duyệt.

Bài thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**. Người học áp dụng kiến thức vào các lớp phòng vệ HTTP và trình duyệt trong Spring Security — **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session** — trên cả **Servlet** và **Reactive/WebFlux**.

Sau bài học, bạn có thể:

1. Phân tích **origin thực thi của JavaScript** và quyền nó có đối với DOM, cookie, storage và API cùng origin.
2. Phân biệt XSS và CSRF theo **điểm xuất phát, quyền đọc dữ liệu, khả năng gửi request, cách credential được sử dụng và biện pháp phòng vệ**.
3. Giải thích vì sao **HttpOnly, SameSite, SOP và CORS** có ích nhưng không thể thay thế nhau.
4. Nhận diện rủi ro từ **script bên thứ ba, thư viện bị xâm nhập, iframe, postMessage, clickjacking và client-side CSRF**.
5. Áp dụng phòng vệ nhiều lớp: **output encoding, API DOM an toàn, CSP, Trusted Types, CSRF token, Origin/Fetch Metadata, cookie flags, authentication và authorization**.
6. Cấu hình bảo vệ HTTP trên **Spring Security Servlet/WebFlux**, đồng thời kiểm thử bằng DevTools, trình duyệt và công cụ Spring Security.

## 1. Hai điểm xuất phát của một yêu cầu HTTP

Giả sử ứng dụng có:

~~~text
Ứng dụng:     https://app.example.com
API phiên:    https://api.example.com
Website ngoài: https://outside.test
~~~

Ở tình huống thứ nhất, người dùng đang ở **app.example.com** và trang tải một đoạn JavaScript. Nếu đoạn script được thực thi như mã của tài liệu ứng dụng, nó có nhiều quyền trong **origin của trang**.

Ở tình huống thứ hai, người dùng mở **outside.test**; mã ở đó cố tạo request đến app.example.com hoặc api.example.com. Trình duyệt áp dụng **Same-Origin Policy (SOP)**, **CORS**, cookie **SameSite** và các chính sách khác, nhưng vẫn có những cách tạo request hợp pháp qua liên kết, form và tài nguyên nhúng.

~~~mermaid
flowchart LR
    subgraph A["Mã thực thi trong trang app.example.com"]
      X["JavaScript chính chủ / XSS / third-party script"]
      D["DOM + storage trong origin trang"]
      F["Fetch/API theo quyền của trang"]
      X --> D
      X --> F
    end
    subgraph B["Trang outside.test"]
      E["HTML form / navigation / fetch / iframe"]
      P["Chính sách browser: SOP, CORS, SameSite"]
      E --> P
    end
    F --> API["API Spring Security"]
    P --> API
    API --> C["Authentication + Authorization + CSRF + kiểm tra nghiệp vụ"]
~~~

Sơ đồ không có nghĩa các lớp bảo vệ chỉ áp dụng cho một phía. Ví dụ script XSS có thể lợi dụng cookie phiên để gửi request; request cross-site cũng có thể khai thác endpoint có xử lý dữ liệu không an toàn.

### 1.1. Bảng so sánh nền tảng

| Tiêu chí | Mã chạy trong origin của ứng dụng | Trang ngoài khởi tạo request cross-origin/cross-site |
| --- | --- | --- |
| **Có quyền đọc DOM của trang ứng dụng?** | Thường có, nếu là script thực thi trong cùng document/origin và không bị sandbox/isolated world giới hạn. | Không được đọc DOM cross-origin tùy ý theo SOP. |
| **Đọc localStorage/IndexedDB của origin ứng dụng?** | Thường có qua API của origin đó, nếu script chạy trong ngữ cảnh có quyền. | Không trực tiếp đọc vùng storage cross-origin. |
| **Đọc cookie HttpOnly bằng document.cookie?** | Không. | Không. |
| **Gửi request dùng session cookie?** | Có thể; browser tự gắn cookie khi đủ điều kiện. | Có thể trong một số ngữ cảnh, tùy SameSite, loại request và cookie policy. |
| **Đọc response API của origin ứng dụng?** | Có thể đọc response same-origin; gọi API khác origin cần CORS nếu dùng fetch/XHR. | Bị SOP/CORS giới hạn khi cross-origin. |
| **Tự gắn Bearer token đang có trong JS của ứng dụng?** | Có thể nếu script lấy được token hoặc can thiệp luồng dùng token. | Thường không có quyền lấy token từ JS/storage của origin khác. |
| **Mối nguy tiêu biểu** | XSS, supply-chain compromise, lạm dụng quyền script, đánh cắp dữ liệu hoặc thao tác. | CSRF, clickjacking, XS-Leaks, thao túng luồng điều hướng. |
| **Phòng vệ cốt lõi** | Ngăn chèn mã, mã hóa đầu ra, DOM API an toàn, CSP/Trusted Types, kiểm soát dependency. | CSRF token, phân quyền, cookie SameSite, Origin/Fetch Metadata, frame-ancestors; không dựa vào CORS đơn lẻ. |

**Không có lớp nào trong bảng tự xác thực người dùng.** Kể cả khi request xuất phát cùng origin, server vẫn phải xác thực credential, phân quyền tài nguyên và xác minh các thao tác nhạy cảm.

## 2. Mã JavaScript “của trang” có quyền gì?

Trong mô hình web thông thường, mã JavaScript nhúng bằng **script** trong một document sẽ thực thi trong **ngữ cảnh origin của document đó**, ngay cả khi mã script được tải từ một host/CDN khác, nếu không có cơ chế cách ly đặc biệt.

Ví dụ trang:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <script src="https://cdn.example.net/ui/widget.js"></script>
</head>
<body>
  <main id="profile"></main>
</body>
</html>
~~~

Nếu widget.js được tải và thực thi như một script bình thường trong trang **https://app.example.com**, nó có quyền của mã chạy trong tài liệu app.example.com. Không nên hiểu rằng vì file JavaScript nằm trên cdn.example.net nên nó **tự bị giới hạn chỉ được truy cập dữ liệu của cdn.example.net**.

Tùy cấu trúc trang, đoạn mã đó có thể:

- Đọc hoặc thay đổi phần lớn DOM có thể truy cập trong document.
- Đọc localStorage và sessionStorage của origin trang khi API cho phép.
- Thực hiện request same-origin và đọc phản hồi theo quyền của trang.
- Gọi API khác origin; nếu được CORS cho phép thì đọc dữ liệu response.
- Khi cookie session phù hợp, khiến browser **tự gắn cookie HttpOnly** vào request dù script không đọc được giá trị cookie.
- Quan sát một số thông tin nhập vào biểu mẫu trong trang hoặc can thiệp vào sự kiện UI.

**Quyền ở đây là quyền của script trong browser, không phải quyền nghiệp vụ trên server.** Nếu người dùng không có quyền đổi vai trò, việc JavaScript gửi request đổi vai trò vẫn phải bị server từ chối.

### 2.1. Vì sao XSS nguy hiểm dù cookie có HttpOnly?

Giả sử ứng dụng có cookie:

~~~http
Set-Cookie: __Host-session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Script XSS không thể dùng document.cookie để lấy giá trị của cookie HttpOnly. Nhưng nếu nó đang chạy trong trang hợp lệ, nó có thể thử:

~~~javascript
// Mô phỏng một lời gọi do mã cùng origin tạo.
// Server vẫn phải kiểm tra quyền và CSRF theo cấu hình.
const response = await fetch("/api/me", {
  credentials: "same-origin"
});
~~~

Browser có thể gửi cookie hợp lệ; script nhận response same-origin nếu yêu cầu được phép. Script không cần biết session ID để sử dụng phiên đang hoạt động. Nó còn có thể tìm hoặc sử dụng CSRF token mà chính trang hợp lệ đã được phép nhận.

Do đó:

> **HttpOnly giảm nguy cơ đọc trực tiếp mã phiên, không biến mã XSS đang chạy cùng origin thành vô hại.**

Cũng không nên kết luận “CSRF token chống được XSS”: nếu attacker có khả năng thực thi script ngay trong origin đáng tin, nhiều cơ chế chống CSRF được thiết kế để phân biệt website ngoài với website hợp lệ có thể bị vượt qua trong ngữ cảnh đó.

### 2.2. Cookie không đồng nghĩa mọi request đều mang credential

Khi gọi API khác origin như **https://api.example.com**, fetch có **credentials: same-origin** mặc định và không tự gửi cookie API cho request cross-origin. Frontend hợp lệ cần chọn **credentials: include** khi mô hình cho phép:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Cookie còn phải thỏa Domain/Path/Secure/SameSite và chính sách browser. Để JavaScript ở app.example.com đọc phản hồi API khác origin có credentials, server còn phải cấp quyền **CORS phù hợp**. Dù script được tải từ CDN, nó vẫn dùng origin **của document** làm origin nguồn khi fetch.

### 2.3. Mã chạy cùng origin và ranh giới của iframe

Không phải mọi mã trên cùng màn hình đều có cùng quyền:

- **Script trực tiếp** trong document hoặc được tải bằng script src thông thường thường chạy trong ngữ cảnh document.
- **Iframe cross-origin** có một document với origin riêng; script ở iframe thường không đọc trực tiếp DOM của parent cross-origin.
- **Iframe sandbox** có thể tiếp tục hạn chế quyền như script execution, form submission, navigation hoặc origin tùy các sandbox flags.
- **Browser extension** có mô hình quyền riêng, không nên xem tương đương script website thường.
- **Dedicated worker/service worker** có môi trường thực thi và API khác document; quyền có thể phụ thuộc origin, scope và policy tương ứng.

Thiết kế cách ly phải xét **ngữ cảnh thực thi thực tế**, không dựa chỉ vào domain của file được tải xuống.

## 3. XSS: khi dữ liệu không đáng tin biến thành mã thực thi

**Cross-Site Scripting (XSS)** xảy ra khi ứng dụng cho phép dữ liệu không đáng tin được diễn giải thành script hoặc nội dung có khả năng thực thi trong ngữ cảnh trang đáng tin.

Ba kiểu thường gặp:

| Loại | Cơ chế | Ví dụ nguồn dữ liệu |
| --- | --- | --- |
| **Reflected XSS** | Dữ liệu request được phản chiếu vào response HTML theo cách không an toàn. | Tham số tìm kiếm, query, thông báo lỗi. |
| **Stored XSS** | Payload được lưu và hiển thị cho những lượt xem sau. | Bình luận, tiểu sử, tên tệp, nội dung do người dùng nhập. |
| **DOM-based XSS** | JavaScript phía client đưa dữ liệu không đáng tin vào **DOM sink** có thể diễn giải HTML/mã. | location.search/hash, postMessage, API response, localStorage. |

Đây là các cách mô tả **đường đi của dữ liệu**, không phải ba cơ chế quyền trình duyệt khác nhau. Khi dữ liệu bị diễn giải thành script trong origin ứng dụng, hậu quả có thể tương tự nhau.

### 3.1. Ví dụ DOM sink nguy hiểm

Đoạn code sau là ví dụ **không an toàn**:

~~~javascript
const search = new URLSearchParams(location.search).get("q") ?? "";
document.querySelector("#search-title").innerHTML =
  "Kết quả tìm kiếm: " + search;
~~~

Nếu q chứa markup, innerHTML có thể biến dữ liệu đầu vào thành phần tử HTML và những cơ chế thực thi không mong muốn tùy nội dung. Người dùng chỉ định xem từ khóa tìm kiếm, **không cho phép URL điều khiển cấu trúc DOM**.

Cách xử lý thích hợp khi chỉ muốn hiển thị văn bản:

~~~javascript
const search = new URLSearchParams(location.search).get("q") ?? "";

document.querySelector("#search-title").textContent =
  "Kết quả tìm kiếm: " + search;
~~~

textContent biến chuỗi thành **nội dung văn bản**, không phân tích chuỗi như HTML. Đây là ví dụ một **safe sink** cho nhu cầu hiển thị text thông thường.

### 3.2. Ngữ cảnh mã hóa đầu ra quyết định biện pháp

Không có một hàm “escape tất cả” áp dụng đúng cho mọi vị trí:

| Ngữ cảnh xuất dữ liệu | Hướng phòng vệ |
| --- | --- |
| Văn bản trong HTML | Dùng template engine tự escape hoặc DOM textContent. |
| Giá trị HTML attribute | Dùng API setAttribute/thuộc tính DOM thích hợp, kiểm tra tên thuộc tính và giá trị; tránh tạo attribute bằng nối chuỗi. |
| URL trong href/src | Xác định sơ đồ URL được phép, chuẩn hóa và kiểm tra đích; không cho các scheme nguy hiểm như javascript: ở những chỗ điều hướng. |
| Nội dung script JavaScript | Tránh nhúng dữ liệu tùy ý vào source code script; dùng JSON/data attribute qua phương thức an toàn và CSP phù hợp. |
| CSS hoặc style | Không nối trực tiếp CSS không đáng tin; chọn API và allowlist thuộc tính/giá trị phù hợp. |
| HTML người dùng được phép định dạng | Dùng **HTML sanitizer** được duy trì và cấu hình theo allowlist; không chỉ dùng text escaping nếu thực sự phải giữ markup. |

Tránh tự phát minh bộ lọc bằng vài biểu thức chính quy vì HTML, URL và JavaScript có nhiều cách biểu diễn tương đương. Cần xác định **nguồn dữ liệu, đường truyền, vị trí sử dụng và ngữ cảnh output**.

### 3.3. Ví dụ server-rendered với Thymeleaf

Trong ứng dụng Spring MVC, một template có dữ liệu nickname do người dùng nhập:

~~~html
<p th:text="${nickname}">Tên hiển thị</p>
~~~

Thymeleaf **th:text** hiển thị nội dung theo cơ chế escape text phù hợp. Nếu dùng **th:utext**, template cho phép biểu diễn HTML chưa escape, vì vậy chỉ dùng khi nội dung đã được tin cậy/xử lý phù hợp theo chính sách.

Đối với hệ thống dùng React, Vue, Angular hoặc template engine khác, hãy hiểu rõ cơ chế escape mặc định và cẩn trọng với những API cố ý chèn raw HTML, chẳng hạn khi cho phép nội dung WYSIWYG.

### 3.4. Nguy cơ ngoài HTML hiển thị

XSS có thể bắt nguồn từ nhiều nguồn ít được chú ý:

- Tên sản phẩm, tên tác giả hoặc tên file do người dùng cung cấp.
- Nội dung từ một API được frontend coi là “nội bộ” nhưng thực chất chứa input của người dùng khác.
- Dữ liệu lưu trong localStorage/sessionStorage rồi đưa vào innerHTML ở lần mở trang sau.
- **postMessage** nhận dữ liệu từ iframe/website khác mà không xác minh event.origin.
- Nội dung Markdown/HTML hoặc SVG do user upload và được nhúng không cách ly.
- Phần giao diện lỗi, dashboard vận hành hoặc trang admin hiển thị log đầu vào chưa escape.

**Server-side validation vẫn cần thiết**, nhưng không thay thế output encoding đúng ngữ cảnh hoặc DOM API an toàn. Validation giúp kiểm tra tính hợp lệ của dữ liệu nghiệp vụ; encoding và sandbox xử lý việc dữ liệu đi vào parser/thực thi.

## 4. Script bên thứ ba và rủi ro chuỗi cung ứng

Một đội phát triển có thể thêm thư viện, analytics, chat widget hoặc file script từ CDN. Khi tải theo cách nhúng script thông thường, mã được **trao quyền chạy trong ngữ cảnh trang**, không phải chỉ quyền của origin chứa file.

### 4.1. Rủi ro khi script được thay đổi ngoài ý muốn

Nếu một nguồn script hợp pháp bị xâm nhập, một dependency bị thay đổi, hoặc bản phát hành bị nhiễm mã độc, trình duyệt có thể chạy mã không mong muốn trên chính trang ứng dụng.

Các hành vi có thể xảy ra phụ thuộc quyền và giao diện:

- Đọc thông tin đang hiển thị trong DOM và dữ liệu lưu phía client.
- Theo dõi tương tác hoặc dữ liệu người dùng nhập trong trang.
- Gửi request bằng phiên hiện tại theo những điều kiện cookie/API.
- Thay đổi liên kết, biểu mẫu hoặc nội dung hiển thị để đánh lừa người dùng.
- Tạo network request đến đích bên ngoài nếu các chính sách trình duyệt cho phép.

Đây là **rủi ro tin cậy mã**, không đơn thuần là rủi ro CORS. CORS không làm một script từ CDN được thực thi theo cơ chế script src thường trở thành “script khách chỉ được đọc dữ liệu CDN”.

### 4.2. Biện pháp hạn chế

- **Giảm dependency và script bên thứ ba** trên những trang xử lý dữ liệu nhạy cảm.
- **Pin phiên bản**, kiểm soát quy trình cập nhật và nguồn phát hành.
- Sử dụng **Subresource Integrity (SRI)** với tài nguyên tĩnh phù hợp để phát hiện nội dung bị thay đổi so với hash được chấp nhận.
- Cấu hình **CSP script-src** hạn chế nguồn script được phép và tránh cho phép inline script tùy ý.
- Đưa widget không đáng tin vào **iframe khác origin có sandbox phù hợp** thay vì script chạy trực tiếp, nếu yêu cầu chức năng cho phép.
- Kiểm soát quyền của widget, đường truyền dữ liệu và những origin mà widget được phép giao tiếp.

Ví dụ minh họa cấu trúc SRI:

~~~html
<script
  src="https://cdn.example.net/library/v1.2.3/app.min.js"
  integrity="sha384-REPLACE_WITH_REAL_BASE64_HASH"
  crossorigin="anonymous"></script>
~~~

Chuỗi hash trên **chỉ là placeholder**, không phải hash hợp lệ để chạy. Khi triển khai, phải tạo hash thực của file được kiểm soát; nếu hash sai, browser sẽ từ chối tài nguyên. SRI cần được đánh giá cùng CORS của tài nguyên cross-origin và cách CDN được cấu hình.

**SRI không bảo vệ trước mọi rủi ro supply chain**: nếu bạn chủ động cập nhật sang một phiên bản nhiễm mã và đồng thời chấp nhận hash mới, SRI vẫn khớp. Nó chủ yếu giúp phát hiện nội dung tải về khác với nội dung đã được chấp nhận.

## 5. CSP, Trusted Types và phòng vệ nhiều lớp trước mã trong trang

**Content-Security-Policy (CSP)** là một response header giúp browser giới hạn những loại tài nguyên, script, kết nối và khả năng nhúng được phép. Nó là **lớp giảm thiểu hậu quả và hỗ trợ phòng ngừa**, không thay thế việc loại bỏ XSS tại nguồn.

### 5.1. Một CSP minh họa

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
~~~

Chính sách này minh họa:

- **default-src 'self'**: giá trị fallback cho một số loại tài nguyên nếu directive chuyên biệt không được chỉ định.
- **script-src 'self'**: giới hạn nguồn script ở cùng origin, không mặc nhiên cho chạy inline script không có cơ chế cho phép phù hợp.
- **object-src 'none'**: không tải các plugin/object nguy hiểm không cần thiết.
- **base-uri 'self'**: giới hạn cách khai báo base URL.
- **frame-ancestors 'none'**: cấm website khác nhúng tài liệu này trong iframe (nếu browser hỗ trợ CSP directive).
- **form-action 'self'**: hạn chế những URL mà form trong tài liệu được phép gửi tới.

Ví dụ này không nhất thiết phù hợp với mọi SPA vì ứng dụng có thể cần fetch đến API khác origin hoặc tải script từ CDN. Khi đó cần thiết kế **connect-src, img-src, style-src, script-src** theo danh sách đích thực sự cần dùng.

**Không đơn giản thêm 'unsafe-inline' để ứng dụng hết lỗi CSP** mà không đánh giá tác động. Nếu cần inline script, ưu tiên cơ chế **nonce hoặc hash** phù hợp với kiến trúc, cùng việc quản lý script chặt chẽ.

### 5.2. CSP report-only để triển khai có kiểm soát

Có thể thử chính sách bằng response header:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

Report-only hỗ trợ quan sát vi phạm trước khi thực thi, nhưng **không chặn** như chính sách Content-Security-Policy áp dụng thực sự. Việc thu thập báo cáo cần tránh lộ dữ liệu nhạy cảm và giới hạn lượng log.

Khi chuyển sang enforcing CSP, cần kiểm thử các luồng đăng nhập, thanh toán, widget, lazy-loading và mạng khác nhau. Một CSP không tương thích có thể làm ứng dụng bị hỏng chức năng dù backend vẫn bình thường.

### 5.3. Trusted Types cho DOM XSS

**Trusted Types** là cơ chế trình duyệt hỗ trợ hạn chế việc đưa chuỗi tùy ý vào những DOM sink nguy hiểm. Ví dụ một CSP có thể yêu cầu Trusted Types tại sink:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-policy
~~~

Đây là phần bảo vệ bổ sung cho những browser hỗ trợ; mức hỗ trợ và yêu cầu chuyển đổi mã khác nhau theo môi trường. Không nên chỉ bật header này rồi mặc định mọi innerHTML cũ vẫn hoạt động. Cần thiết kế **policy tạo TrustedHTML/TrustedScriptURL phù hợp** và ưu tiên tránh sink nguy hiểm khi không cần.

Trusted Types không thay thế việc xác minh URL, output encoding và HTML sanitization; nó giúp ép việc sử dụng những sink nhạy cảm qua giao diện kiểm soát rõ ràng hơn.

### 5.4. Security headers bổ trợ

- **X-Content-Type-Options: nosniff** giảm nguy cơ trình duyệt suy diễn MIME type ngoài ý muốn ở những tài nguyên có áp dụng.
- **Strict-Transport-Security (HSTS)** giúp browser ưu tiên HTTPS cho host đã có policy, nhưng không xử lý trực tiếp XSS hoặc CSRF.
- **Content-Security-Policy: frame-ancestors** và **X-Frame-Options** có thể giảm nguy cơ clickjacking bằng cách hạn chế nhúng trang.
- **Referrer-Policy** giúp hạn chế thông tin URL nguồn bị gửi qua Referer.
- Những chính sách cross-origin khác như **CORP/COOP/COEP** có mục đích riêng và cần được đánh giá theo kiến trúc ứng dụng.

Các header này không cho phép bỏ qua **authentication, authorization, CSRF token, kiểm tra dữ liệu và session management**.

## 6. Yêu cầu phát sinh từ website bên ngoài: gửi được không đồng nghĩa đọc được

Giả sử người dùng đã đăng nhập tại **https://bank.example**, còn một trang do bên khác kiểm soát chạy tại **https://outside.test**. Trang bên ngoài thường không được đọc DOM hoặc localStorage của ngân hàng vì **Same-Origin Policy**, nhưng vẫn có thể kích hoạt một số hoạt động mạng đến ngân hàng:

- Điều hướng trình duyệt sang một URL khác qua liên kết.
- Tạo **form HTML** với action trỏ đến URL đích.
- Nhúng ảnh, stylesheet hoặc iframe nếu browser và chính sách tài nguyên cho phép.
- Thử thực hiện **fetch/XHR cross-origin**; quyền gửi và đọc chịu những điều kiện CORS và chế độ request tương ứng.

Đây là lý do **SOP không đồng nghĩa mọi request cross-origin đều bị cấm**.

### 6.1. Phân biệt gửi request và đọc phản hồi

| Cơ chế | Có thể kích hoạt request cross-origin? | Có đọc được body/DOM phản hồi từ origin khác? |
| --- | --- | --- |
| **Điều hướng top-level qua liên kết** | Thường có | Trang nguồn không được đọc DOM trang đích cross-origin. |
| **HTML form GET/POST** | Thường có theo quy tắc form | Trang nguồn không tự được đọc response của origin khác. |
| **img, stylesheet, script src** | Nhiều loại tài nguyên có thể tải cross-origin, tùy chính sách | Khả năng đọc dữ liệu và hành vi tải khác nhau theo loại tài nguyên; không suy ra có thể đọc nội dung tùy ý. |
| **iframe cross-origin** | Có thể nhúng nếu không bị frame policy chặn | SOP giới hạn tương tác với DOM cross-origin. |
| **fetch/XHR CORS** | Có thể gửi trực tiếp hoặc qua preflight | Chỉ đọc được response nếu CORS cho phép; request đã gửi không bảo đảm đọc được response. |

**HTTP authentication và cookie phiên có thể được trình duyệt đính kèm tự động** trong những điều kiện phù hợp. Vì vậy server phải kiểm tra ý định request khi thực hiện thao tác thay đổi trạng thái.

### 6.2. Form POST khác fetch JSON

Một form thông thường:

~~~html
<form action="https://bank.example/api/transfer" method="POST">
  <input type="hidden" name="destination" value="demo-destination">
  <input type="hidden" name="amount" value="100">
  <button type="submit">Xác nhận</button>
</form>
~~~

có thể gửi request với Content-Type **application/x-www-form-urlencoded** mà không phải đi qua CORS preflight kiểu POST JSON có custom header.

Ngược lại, JavaScript muốn POST JSON có header chống CSRF tới API khác origin:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

thường làm browser gửi **OPTIONS preflight** trước POST. Trong ví dụ, **csrfToken phải được ứng dụng cấp hợp lệ**; một chuỗi bất kỳ không vượt qua được kiểm tra CSRF thật.

**Preflight không bảo vệ mọi kiểu request**. Một bên tấn công không cần khiến browser thực hiện một POST JSON nếu endpoint chấp nhận POST form có cùng tác dụng phụ. Do vậy, **đòi Content-Type JSON** có thể là một điều kiện phòng vệ bổ sung khi xử lý đúng, nhưng không nên là biện pháp chống CSRF duy nhất.

### 6.3. CORS cấp quyền đọc response, không cấp quyền nghiệp vụ

Khi frontend **https://app.example.com** cần đọc response của API **https://api.example.com**, API có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Đây là cách cho browser biết script từ origin được phép có thể đọc response có credentials theo điều kiện áp dụng. Nhưng:

- CORS không tự xác thực người dùng hay xác nhận CSRF token.
- CORS không khiến cookie bắt buộc được gửi; cookie vẫn theo SameSite và các điều kiện khác.
- Khi response có credentials, không kết hợp **Access-Control-Allow-Origin: *** với **Access-Control-Allow-Credentials: true**.
- Một HTTP client ngoài browser có thể gửi request trực tiếp và đọc response mà **không bị SOP/CORS thực thi** như trong trình duyệt.

Không dùng Origin được gửi đến server như một token danh tính. Origin hỗ trợ xác định ngữ cảnh trình duyệt, không thay thế authentication và authorization.

## 7. CSRF: mượn phiên của người dùng mà không cần biết mã phiên

**Cross-Site Request Forgery (CSRF)** thường khai thác việc browser **tự gửi credential** như session cookie khi có request phù hợp. Bên tấn công không nhất thiết đọc được response hoặc biết giá trị cookie.

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant E as outside.test
    participant S as Ứng dụng Spring
    U->>B: Đăng nhập ngân hàng
    B->>S: POST /login
    S-->>B: Set-Cookie: session=opaque; Secure; HttpOnly; SameSite=Lax
    U->>E: Mở website bên ngoài
    E->>B: Kích hoạt request đến ngân hàng
    B->>B: Áp dụng cookie policy/SameSite
    B->>S: Request thực (có thể mang cookie nếu được phép)
    S->>S: Kiểm tra CSRF, authentication, authorization
    S-->>B: Chấp nhận hoặc từ chối hành động
~~~

Đặc điểm phân biệt với XSS:

- Bên tấn công thường kiểm soát **một trang khác origin/site**, chứ không thực thi mã trong origin ứng dụng đích.
- Trình duyệt tự quyết định có gắn cookie hay không.
- SOP có thể ngăn đọc response, nhưng **không tự ngăn mọi request có tác dụng phụ tới server**.
- CSRF token và các kiểm tra bổ sung trên server giúp xác nhận request thay đổi trạng thái được khởi tạo theo luồng hợp lệ của ứng dụng.

### 7.1. SameSite giảm rủi ro nhưng không thay thế CSRF

| Cookie SameSite | Hành vi điển hình | Hệ quả phòng vệ |
| --- | --- | --- |
| **Strict** | Không gửi trong các ngữ cảnh cross-site thông thường | Giảm nhiều kiểu CSRF cross-site nhưng không ngăn các nguồn không đáng tin **same-site**. |
| **Lax** | Hạn chế nhiều request cross-site như POST form thông thường; thường gửi trong **top-level navigation GET** | GET không được thực hiện thao tác thay đổi trạng thái. |
| **None; Secure** | Có thể được gửi trong ngữ cảnh cross-site nếu cookie policy khác cho phép | Tăng bề mặt CSRF trong các mô hình cookie tự gửi; cần phòng vệ tương ứng. |

Nhiều browser áp dụng mặc định kiểu Lax cho cookie không khai báo SameSite; một số có hành vi tương thích ngắn hạn khác cho cookie mới được tạo. Đừng dựa vào mặc định đó thay cho chính sách CSRF.

**Same-site khác same-origin**: https://blog.example.com và https://api.example.com thường cùng site nhưng khác origin. Nếu một subdomain bị kiểm soát bởi bên không đáng tin, request từ subdomain đó có thể vẫn được xem là same-site cho mục đích gửi cookie.

### 7.2. GET không được thực hiện thao tác thay đổi trạng thái

Cookie SameSite=Lax có thể được gửi khi người dùng bấm liên kết GET điều hướng top-level từ outside.test đến ứng dụng. Vì vậy một endpoint kiểu:

~~~text
GET /api/orders/42/cancel
GET /transfer?amount=100
GET /logout
~~~

là thiết kế có rủi ro nếu nó thật sự làm thay đổi trạng thái. Các phương thức HTTP được xem là **safe** như GET và HEAD phải được giữ đúng ngữ nghĩa truy vấn; không dùng chúng để hủy đơn, đổi mật khẩu, chuyển tiền hay vô hiệu hóa phiên.

Các method **POST, PUT, PATCH, DELETE** thay đổi trạng thái cần authentication, authorization và CSRF protection khi sử dụng credential tự gửi theo mô hình session.

### 7.3. CSRF token và cookie session có vai trò khác nhau

Cookie session nhận diện phiên; CSRF token là **bằng chứng bổ sung** mà ứng dụng cấp và xác minh cho request thay đổi trạng thái.

Ví dụ request hợp lệ theo cơ chế ứng dụng:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: __Host-session=opaque-session-id
Content-Type: application/json
X-CSRF-TOKEN: token-issued-for-this-flow

{"productId":42}
~~~

Server phải xác minh token thật, không chỉ kiểm tra header X-CSRF-TOKEN hiện diện. Token có thể được gửi trong form field hoặc request header tùy cơ chế, và có thể cần được làm mới sau login/logout hoặc session rotation.

**CSRF token không cấp quyền sở hữu tài nguyên**. Người dùng có token hợp lệ vẫn không được sửa đơn hàng của người khác nếu không có quyền.

### 7.4. Login CSRF và logout CSRF

CSRF không chỉ liên quan thanh toán. Một số luồng nhạy cảm khác:

- **Login CSRF**: bên ngoài cố đưa nạn nhân vào một phiên tài khoản không mong muốn hoặc thay đổi trạng thái đăng nhập theo cách đánh lừa người dùng.
- **Logout CSRF**: bên ngoài kích hoạt việc đăng xuất không mong muốn khi ứng dụng có endpoint thay đổi trạng thái dễ gọi.
- **Thay đổi email, mật khẩu, tùy chọn bảo mật**: nếu request có cookie tự gửi mà thiếu xác minh CSRF/reauthentication, tác động có thể lớn.
- **OAuth2/OIDC login flow**: cần kiểm tra **state**, PKCE hoặc các biện pháp ràng buộc flow thích hợp với từng luồng; không suy ra một CSRF token trên form nghiệp vụ thay thế toàn bộ bảo vệ của giao thức.

Trong Spring Security dùng session, **giữ CSRF protection mặc định** và tích hợp cách cấp token đúng. Không biến GET /logout thành thao tác có tác dụng phụ chỉ để frontend sử dụng thẻ liên kết.

## 8. Client-side CSRF: mã hợp lệ bị điều khiển để gửi sai yêu cầu

Một trường hợp cần phân biệt với CSRF form cổ điển là **client-side CSRF**. Bên tấn công không nhất thiết chèn được JavaScript mới vào ứng dụng. Thay vào đó, attacker ảnh hưởng một giá trị mà **mã frontend hợp lệ** sử dụng để quyết định sẽ gọi API nào.

Ví dụ logic frontend **không an toàn**:

~~~javascript
const params = new URLSearchParams(location.search);
const action = params.get("action");

if (action) {
  await fetch("/api/" + action, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRF-TOKEN": currentCsrfToken
    }
  });
}
~~~

Ở đây **currentCsrfToken** là token hợp lệ mà frontend đã nhận qua luồng của ứng dụng. Vấn đề không nằm ở việc attacker lấy được token: attacker có thể thao túng tham số **action** trong URL để khiến **chính script của trang hợp lệ** gửi request tới một đường dẫn ngoài ý định. Ví dụ này phục vụ phân tích phòng vệ; không dùng URL không đáng tin để thực thi giao dịch thật.

Một thiết kế an toàn hơn:

~~~javascript
const params = new URLSearchParams(location.search);
const action = params.get("action");

const readOnlyActions = new Map([
  ["show-order", "/api/orders/current"],
  ["show-profile", "/api/me"]
]);

const target = readOnlyActions.get(action);

if (target) {
  const response = await fetch(target, {
    method: "GET",
    credentials: "same-origin"
  });
  // Xử lý dữ liệu đã xác thực và phân quyền từ server.
}
~~~

Những hành động thay đổi trạng thái phải được khởi tạo qua **luồng UI/điều kiện đáng tin**, có bước xác nhận phù hợp, bảo vệ CSRF và kiểm tra quyền ở server; không xây dựng URL/method nhạy cảm bằng cách ghép trực tiếp đầu vào từ location, postMessage hoặc dữ liệu không đáng tin.

### 8.1. Vì sao cả CSP lẫn CSRF token vẫn có thể không đủ?

- **CSP** giúp giới hạn nguồn script được thực thi, nhưng đoạn script ở ví dụ là **mã hợp lệ của chính ứng dụng**, nên CSP không tự phát hiện nó đang sử dụng đầu vào nguy hiểm.
- **CSRF token** có thể được mã hợp lệ đính kèm cho request, nên việc kiểm tra token chưa chắc phát hiện hành động đã bị đổi hướng bởi tham số không đáng tin.
- **SameSite** không giúp nhiều khi request do script của ứng dụng thực hiện cùng origin.
- Server vẫn phải phân quyền và kiểm tra trạng thái nghiệp vụ; phía client phải hạn chế dữ liệu điều khiển request nhạy cảm.

Client-side CSRF minh họa vì sao phải quan tâm không chỉ **ai có thể chạy mã**, mà còn **dữ liệu nào đang điều khiển mã hợp lệ đó**.

## 9. Clickjacking: đánh lừa thao tác trong giao diện

**Clickjacking** hoặc *UI redressing* là tình huống trang ngoài cố nhúng hoặc sắp xếp giao diện của ứng dụng đích sao cho người dùng thực hiện cú nhấp ngoài ý muốn.

Một iframe cross-origin thường vẫn bị SOP ngăn trang ngoài đọc DOM bên trong. Nhưng nếu trang đích **cho phép nhúng**, trang ngoài có thể thử điều khiển bố cục/trải nghiệm bên ngoài iframe để hướng người dùng nhấp một nút trong nội dung được nhúng.

Lớp phòng vệ quan trọng là **chính sách có cho phép nhúng trang hay không**, không phải CORS:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Với trang cần được nhúng bởi một đối tác đã tin cậy, có thể dùng **frame-ancestors** với allowlist origin phù hợp thay vì none, đồng thời cân nhắc giới hạn chức năng trong nội dung nhúng. **X-Frame-Options** có các lựa chọn hạn chế và không thay thế mọi khả năng của CSP frame-ancestors.

**Frame policy không thay thế CSRF hoặc phân quyền**: nó ngăn một kịch bản nhúng nhất định, nhưng không chứng minh mọi request thay đổi trạng thái đều được người dùng chủ động thực hiện.

### 9.1. Iframe và postMessage

Để giao tiếp giữa parent và iframe khác origin, dùng **postMessage** có kiểm tra hai chiều phù hợp:

~~~javascript
// Trong parent app.example.com, chỉ gửi tới origin đã biết.
const iframe = document.querySelector("#partner-frame");

iframe.contentWindow.postMessage(
  { type: "REQUEST_STATUS" },
  "https://partner.example.net"
);
~~~

Đầu nhận phải kiểm tra origin của message và định dạng dữ liệu:

~~~javascript
window.addEventListener("message", (event) => {
  if (event.origin !== "https://partner.example.net") {
    return;
  }

  if (event.data?.type === "STATUS_UPDATED") {
    renderStatusText(event.data.status);
  }
});
~~~

**renderStatusText()** là hàm ứng dụng giả định, phải hiển thị nội dung theo cách an toàn (ví dụ textContent khi chỉ cần text). Không tin event.data chỉ vì event.origin khớp; vẫn kiểm tra schema và giới hạn giá trị.

Trong ứng dụng thật, phải xác định **ai là parent, ai là iframe, origin cụ thể của bên gửi và bên nhận**, đồng thời kiểm tra event.source khi cần. **Không dùng targetOrigin "*" cho dữ liệu nhạy cảm** nếu đã biết origin đích.

## 10. XS-Leaks: SOP ngăn đọc trực tiếp nhưng vẫn có tín hiệu phụ

Nhóm **Cross-Site Leaks (XS-Leaks)** bao gồm các cách suy luận một số trạng thái từ website khác thông qua những tín hiệu browser cho phép quan sát, chẳng hạn khác biệt về trạng thái tải, điều hướng, thời gian hoặc hành vi hiển thị trong một số ngữ cảnh.

Không đồng nhất XS-Leaks với việc trang ngoài **đọc trực tiếp body JSON**: SOP thường chặn điều đó. Rủi ro nằm ở việc ứng dụng tạo ra **tín hiệu khác nhau có liên hệ với dữ liệu nhạy cảm** mà trang ngoài có thể đoán được.

Những hướng giảm thiểu cần đánh giá theo chức năng:

- Tránh thiết kế endpoint trả hành vi phân biệt rõ trạng thái bí mật trong những ngữ cảnh được nhúng hoặc điều hướng cross-site.
- Dùng **SameSite cookie** và giới hạn credential cross-site khi phù hợp.
- Cân nhắc **Fetch Metadata** để hạn chế một số loại request cross-site không mong muốn.
- Sử dụng **Cross-Origin-Resource-Policy (CORP)**, **Cross-Origin-Opener-Policy (COOP)**, **Cross-Origin-Embedder-Policy (COEP)** nếu phù hợp mô hình cô lập tài nguyên.
- Kiểm soát **frame-ancestors**, cache và phản hồi chứa dữ liệu riêng tư.
- Không tiết lộ thông tin nhạy cảm trong URL, tiêu đề response hoặc hành vi redirect không cần thiết.

Các chính sách này có phạm vi và giới hạn khác nhau, không thể bật toàn bộ trên production mà không kiểm thử tích hợp, iframe, OAuth2 login và các nguồn tài nguyên.

## 11. Tập hợp các lớp phòng vệ

| Rủi ro | Lớp phòng vệ chính | Điều lớp đó không tự làm được |
| --- | --- | --- |
| **Reflected/stored/DOM XSS** | Output encoding đúng ngữ cảnh, safe DOM APIs, HTML sanitizer phù hợp, CSP và Trusted Types. | Cookie HttpOnly không ngăn script XSS gọi API. |
| **Script CDN/dependency bị thay đổi** | Kiểm soát dependency, review update, SRI, CSP, cách ly iframe khi phù hợp. | CORS không sandbox script nhúng vào document. |
| **CSRF với cookie session** | CSRF token, SameSite, đúng HTTP methods, authentication/authorization; Origin/Fetch Metadata bổ trợ. | CORS chỉ giới hạn quyền đọc response cross-origin; không chặn mọi form POST. |
| **Client-side CSRF** | Không cho input không đáng tin quyết định URL/method nhạy cảm; allowlist hành động, confirmation, server-side authorization. | CSRF token có thể bị script hợp lệ tự gắn vào request bị điều khiển. |
| **Clickjacking** | CSP frame-ancestors, X-Frame-Options, thiết kế UI nhạy cảm có xác nhận phù hợp. | SOP không tự ngăn trang bị nhúng hoặc thao túng bối cảnh ngoài iframe. |
| **XS-Leaks** | Giảm tín hiệu phụ, cô lập tài nguyên, SameSite, Fetch Metadata, cache policy phù hợp. | SOP không loại bỏ mọi tín hiệu có thể quan sát gián tiếp. |
| **Mất phiên/lộ session ID** | HTTPS/HSTS, Secure/HttpOnly/SameSite, session rotation, server-side invalidation, thời hạn phiên. | Cookie flags không thay thế xác thực, phân quyền hay xử lý XSS. |
| **Truy cập tài nguyên không được phép** | Authentication, authorization theo tài nguyên/tenant/đối tượng. | Origin/CORS/CSRF token không chứng minh người dùng có quyền đó. |

**Bảo mật hiệu quả là phòng vệ nhiều lớp**, nhưng cần hiểu chính xác lớp nào giải quyết vấn đề nào. Không nên dùng một header duy nhất để tuyên bố ứng dụng miễn nhiễm XSS hoặc CSRF.

## 12. Cấu hình Spring Security Servlet

Ví dụ sau dành cho **Spring Security 6.x với Spring MVC/Servlet**. Giả sử ứng dụng có giao diện được server phục vụ trên một origin đáng tin và API dưới **/api/**; đồng thời nó có thể tiếp nhận request CORS từ frontend ở **https://app.example.com** khi kiến trúc cho phép.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletBrowserProtectionConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                        "default-src 'self'; " +
                                        "script-src 'self'; " +
                                        "connect-src 'self' https://api.example.com; " +
                                        "object-src 'none'; " +
                                        "base-uri 'self'; " +
                                        "frame-ancestors 'none'; " +
                                        "form-action 'self'")))
                // Không tắt CSRF: mặc định bảo vệ method thay đổi trạng thái.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN", "Authorization"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Đoạn cấu hình minh họa **ba lớp riêng**:

1. **CORS** giới hạn origin/method/header mà browser khác origin được đọc hoặc sử dụng qua quy tắc CORS.
2. **CSRF** được giữ mặc định đối với thao tác thay đổi trạng thái của ứng dụng sử dụng session/cookie.
3. **CSP** giới hạn cách tài liệu HTML do chính ứng dụng phục vụ được phép tải script, kết nối và bị nhúng vào frame.

**Điểm quan trọng:** CSP là chính sách của **document nhận response chứa CSP**. Nếu giao diện được phục vụ hoàn toàn bởi **https://app.example.com**, còn ứng dụng Spring ở **https://api.example.com** chỉ trả JSON, thì CSP gắn vào response JSON của API **không tự áp đặt script-src lên trang HTML của app.example.com**. CSP cần được cấu hình tại nơi phục vụ **trang HTML/frontend**, hoặc tại một reverse proxy/gateway kiểm soát response đó.

### 12.1. CSP phải được tinh chỉnh theo frontend thực tế

Chính sách **script-src 'self'** ở ví dụ sẽ không tự cho phép script bên ngoài hoặc inline script không có cơ chế phù hợp. Nếu frontend cần thư viện CDN, nonce/hash hoặc widget nhúng, phải thiết kế allowlist và kiểm thử cẩn thận.

Không dùng **script-src *** hoặc **'unsafe-inline'** để xử lý lỗi tạm thời mà không đánh giá rủi ro. Một CSP phù hợp vừa giảm rủi ro vừa phải tương thích các tính năng hợp lệ; nên khởi đầu với report-only khi cần khảo sát ứng dụng lớn.

Mặc dù cấu hình CSP có **frame-ancestors 'none'**, ứng dụng có thể cần nhúng hợp lệ. Khi đó thay đổi theo allowlist origin thật, không mở tùy ý. Có thể sử dụng X-Frame-Options ở những bối cảnh tương thích cũ; chính sách phải được kiểm thử trên browser mục tiêu.

### 12.2. Session cookie và CSRF là hai lớp cần phối hợp

Với ứng dụng Servlet dùng session cookie, có thể cấu hình thêm thuộc tính cookie trên Spring Boot khi triển khai HTTPS:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

Tên **__Host-session** yêu cầu cookie có **Secure**, **Path=/** và không có Domain. Không dùng cookie domain rộng nếu không cần; đặc biệt cẩn trọng khi có những subdomain không đáng tin.

Cấu hình cookie trên **không thay thế** việc cấp/kiểm tra CSRF token. Với SPA cần gửi POST/PUT/PATCH/DELETE, hãy thiết kế endpoint hoặc cơ chế nhận CSRF token hợp lệ, phù hợp **Spring Security CSRF repository** và token request handler.

### 12.3. Cấp CSRF token cho frontend một cách có kiểm soát

Với Spring MVC, một ví dụ endpoint mô tả cách expose token từ cơ chế CSRF hiện có:

~~~java
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/api/csrf")
    Map<String, String> csrf(CsrfToken csrfToken) {
        return Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken());
    }
}
~~~

Đây là một mẫu cấp token để frontend hợp lệ có thể lấy token qua **response được kiểm soát quyền và CORS**. Endpoint này phải nằm trong luồng session/CSRF được cấu hình phù hợp; với Spring Security hiện đại cần chú ý **deferred token**, biểu diễn/masking token để giảm BREACH, cùng việc làm mới token sau xác thực hoặc logout nếu cần.

Không công bố token cho mọi website bên ngoài thông qua CORS có credentials. Cần giới hạn origin được phép và không cache response token nhạy cảm ngoài ý định. Việc nhận token hợp lệ không cấp thêm quyền nghiệp vụ; authorization vẫn cần trên mỗi endpoint.

### 12.4. Bảo vệ chống session fixation và logout

Sau đăng nhập, Spring Security có cơ chế phòng vệ **session fixation** phù hợp với stack và cấu hình. Một ứng dụng dùng session cũng cần:

- Session ID khó đoán, bảo vệ qua HTTPS và HttpOnly.
- Thời gian sống session server-side độc lập với cookie expiry.
- Invalidating session khi logout, không chỉ xóa cookie.
- Giới hạn quyền của session, kiểm tra quyền đối với từng tài nguyên.
- Tính toán refresh/remember-me token nếu hệ thống có cơ chế xác thực dài hạn.

Không tạo GET /logout làm thay đổi trạng thái chỉ để tiện sử dụng liên kết. Khi CSRF bảo vệ logout đang bật, frontend phải dùng phương thức hợp lệ cùng token.

## 13. Cấu hình Spring Security Reactive/WebFlux

Trong WebFlux, dùng **SecurityWebFilterChain**, **ServerHttpSecurity** và CORS source thuộc **org.springframework.web.cors.reactive**.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveBrowserProtectionConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth -> auth
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                        "default-src 'self'; " +
                                        "script-src 'self'; " +
                                        "connect-src 'self' https://api.example.com; " +
                                        "object-src 'none'; " +
                                        "base-uri 'self'; " +
                                        "frame-ancestors 'none'; " +
                                        "form-action 'self'")))
                // Giữ CSRF mặc định cho ứng dụng WebSession/cookie.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN", "Authorization"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Sự giống nhau:** browser áp dụng SOP/CORS, SameSite, CSP và quy tắc cookie như nhau bất kể backend là Servlet hay Reactive. CSRF vẫn có ý nghĩa khi WebSession/cookie có thể được tự gửi.

**Sự khác nhau:** WebFlux có WebSession, reactive filter chain và cách expose token qua publisher khác Servlet; không dùng nhầm các lớp CorsConfigurationSource của Servlet vào Reactive. Cần cấu hình session cookie, CSRF repository và cách cấp token **tương thích WebFlux** nếu frontend dùng cookie.

Ví dụ CSP ở đây cũng chỉ bảo vệ **document mà response của WebFlux thực sự phục vụ**. Nếu API trả JSON nhưng frontend HTML nằm ở host khác, CSP cần được triển khai trên frontend host đó.

### 13.1. Đừng chặn preflight như request cần session

Với frontend/API khác origin, POST JSON kèm X-CSRF-TOKEN thường tạo **OPTIONS preflight**:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Preflight thường **không mang cookie phiên**. CORS cần được xử lý trước các filter có thể trả 401/403 chỉ vì không thấy session. POST thực được gửi sau preflight vẫn phải qua CSRF token, authentication và authorization.

Không mở mọi API cho anonymous để sửa lỗi OPTIONS; chỉ cho bộ xử lý CORS đánh giá preflight hợp lệ.

## 14. Kiểm thử ranh giới: request đã được gửi hay browser từ chối đọc?

Một kế hoạch kiểm thử phải quan sát cả **hành vi browser** và **trạng thái nghiệp vụ phía server**. Đừng chỉ nhìn Console error.

### 14.1. Kiểm thử DOM injection một cách an toàn

Trong môi trường thử nghiệm, tạo một chuỗi chứa markup nhưng **không cần payload đánh cắp dữ liệu**:

~~~javascript
const testText = "<strong>Text không được diễn giải như HTML</strong>";

document.querySelector("#result").textContent = testText;
~~~

Kết quả mong muốn: trình duyệt hiển thị nguyên văn các ký tự của chuỗi, không tạo một phần tử strong mới từ dữ liệu không đáng tin.

Nếu ứng dụng phải hỗ trợ HTML từ người dùng, cần test sanitizer với những trường hợp khó như attribute, URL scheme, SVG/MathML và markup lồng nhau; không biến dữ liệu không đáng tin thành innerHTML trực tiếp.

### 14.2. Quan sát Content-Security-Policy

Trong DevTools:

1. Mở **Network** và chọn response của **document HTML**.
2. Kiểm tra **Content-Security-Policy** hoặc **Content-Security-Policy-Report-Only**.
3. Thử các luồng giao diện hợp lệ: login, form, fetch API, widget và iframe.
4. Xem **Console** có thông báo CSP violation nào và directive nào bị vi phạm.
5. Xác định vi phạm là do **nguồn không được phép**, inline script, kết nối API ngoài allowlist hay hành vi thực sự không hợp lệ.
6. Điều chỉnh policy từ nhu cầu rõ ràng, tránh mở wildcard vô điều kiện.

**Không dùng mỗi response JSON của API làm bằng chứng frontend HTML đã có CSP đúng** khi chúng được phục vụ từ origin khác nhau.

### 14.3. Quan sát một POST từ origin ngoài

Một request do trang ngoài khởi tạo có thể không đọc được response nhưng vẫn được browser gửi dưới một số điều kiện. Trong môi trường kiểm thử có endpoint không gây tác dụng phụ, quan sát:

- **Origin** nếu browser có gửi.
- **Sec-Fetch-Site** (same-origin/same-site/cross-site/none), nếu browser hỗ trợ.
- Request có **Cookie** không, và vì sao cookie có/không đủ điều kiện gửi.
- Method là GET hay POST; có **OPTIONS preflight** không.
- Request có đi đến server không, hoặc browser bị chặn trước.
- Server từ chối do CSRF, authorization hay endpoint không tồn tại.

Chỉ dùng môi trường và dữ liệu bạn được phép kiểm thử; không chạy form thử nghiệm với tài khoản hoặc API thật có thể gây hành động ngoài ý muốn.

### 14.4. Kiểm tra preflight bằng curl

Trong môi trường API thử nghiệm:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Đổi Origin sang một origin không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://outside.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Kiểm tra API **không cấp quyền CORS với credentials** cho origin không nằm trong allowlist. Có thể có 403 hoặc response không cấp các header cho phép tùy tầng xử lý.

**curl không bị SOP/CORS của browser giới hạn**, nên nó không thể tự chứng minh một request fetch từ JavaScript sẽ đọc được response. Dùng DevTools và browser test để xác nhận chính sách thực tế.

### 14.5. MockMvc: phân biệt CSRF token và authentication

Với **spring-security-test** và cấu hình Servlet phù hợp, có thể so sánh POST có/không có CSRF token:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersCsrfMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("tester"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":42}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void requestWithValidCsrfCanReachController() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("tester"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":42}"))
            .andExpect(status().isCreated());
    }
}
~~~

**Giả định:** endpoint POST /api/orders tồn tại, user test có đủ quyền và controller trả **201 Created** khi tạo đơn thành công. Ở ứng dụng thực, status hoặc điều kiện khác có thể khác; hãy điều chỉnh assertion theo hợp đồng endpoint.

Test **.with(csrf())** là hỗ trợ mô phỏng của spring-security-test, không phải chỉ dẫn để client production tự tạo token bất kỳ. Cần thêm test chưa đăng nhập, user không đủ quyền và xác minh dữ liệu không thay đổi khi request bị từ chối.

### 14.6. WebTestClient cho Reactive

Với WebFlux, spring-security-test hỗ trợ mô phỏng user và CSRF:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

// webTestClient là WebTestClient đã gắn ứng dụng và security chain.
webTestClient
    .mutateWith(mockUser("tester"))
    .post().uri("/api/orders/42/cancel")
    .exchange()
    .expectStatus().isForbidden();

webTestClient
    .mutateWith(mockUser("tester"))
    .mutateWith(csrf())
    .post().uri("/api/orders/42/cancel")
    .exchange()
    .expectStatus().isNoContent();
~~~

Đây là đoạn minh họa bên trong test, **không phải lớp test hoàn chỉnh**. Nó giả định endpoint hợp lệ, user test có quyền và handler trả **204 No Content** sau thao tác. Request có CSRF token hợp lệ vẫn có thể bị từ chối bởi authorization hoặc logic nghiệp vụ.

### 14.7. Ma trận chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Mã từ CDN đọc được dữ liệu trong DOM trang. | Script nhúng chạy trong ngữ cảnh document, không được cô lập như iframe. | Kiểm soát script, cân nhắc SRI/CSP/iframe sandbox. |
| Cookie có HttpOnly nhưng mã bị chèn vẫn gọi API. | HttpOnly không chặn browser gửi cookie hoặc script gọi API trong origin. | Loại bỏ XSS, CSP, authorization, kiểm tra nghiệp vụ. |
| Chuỗi người dùng nhập trở thành HTML tương tác. | Dùng innerHTML/th:utext/DOM sink không an toàn. | Dùng textContent, output encoding, sanitizer thích hợp. |
| Script hợp lệ thực hiện POST từ URL query tùy ý. | Client-side CSRF hoặc dữ liệu không đáng tin điều khiển request. | Allowlist hành động, tách luồng mutation, authorization server. |
| OPTIONS bị 401/403 trước POST. | Preflight bị auth/firewall/gateway chặn hoặc policy CORS từ chối. | Kiểm tra cấu hình CORS và thứ tự filter. |
| OPTIONS đạt nhưng POST 403. | CSRF token sai, session không hợp lệ hoặc không đủ quyền. | Kiểm tra POST thực, CSRF repository và authorization. |
| POST đã thực hiện nhưng JavaScript báo lỗi CORS. | Response thực thiếu CORS header phù hợp. | Kiểm tra response POST, không retry giao dịch mù quáng. |
| Trang được nhúng vào iframe ngoài ý muốn. | Thiếu frame-ancestors hoặc X-Frame-Options phù hợp. | Cấu hình policy nhúng và kiểm tra nhu cầu hợp pháp. |
| postMessage làm UI thay đổi từ message lạ. | Thiếu kiểm tra event.origin/source hoặc schema dữ liệu. | Allowlist origin, validate event.data, safe DOM sinks. |
| CSP chặn script hợp lệ. | script-src không bao gồm cách tải/script được ứng dụng sử dụng. | Kiểm tra Console, chính sách và luồng tải thực; tránh mở wildcard vô cớ. |
| CORS đúng nhưng CSP chặn API fetch. | connect-src của CSP không cho phép URL đích. | Điều chỉnh CSP trên HTML frontend đúng origin. |
| Cookie SameSite=Strict vẫn gửi từ blog.example.com tới API cùng site. | Same-site khác same-origin; subdomain có thể không đáng tin. | Giữ CSRF token và chính sách tin cậy subdomain chặt chẽ. |
| Browser báo “blocked by response” khi nhúng trang. | frame-ancestors, X-Frame-Options, CORP hoặc policy khác. | Đọc đúng loại policy và URL nguồn/đích, không quy tất cả cho CORS. |

## 15. Bài tập tình huống

### Tình huống A — CDN script có bị cô lập theo origin CDN?

Trang https://app.example.com nhúng một file JavaScript từ https://cdn.example.net bằng script src. Một thành viên cho rằng mã đó chỉ có quyền của cdn.example.net, không thể truy cập DOM của app.example.com. Đúng không?

**Đáp án:** Không. Một script được tải và thực thi bình thường trong tài liệu có thể chạy với quyền của ngữ cảnh trang **app.example.com**, trừ khi dùng mô hình cách ly riêng. Vì vậy phải tin cậy nguồn script, quản lý dependency, CSP/SRI và cách ly widget không đáng tin khi cần.

### Tình huống B — Cookie HttpOnly nhưng có XSS

Cookie phiên có Secure và HttpOnly. Một mã XSS được thực thi trong origin ứng dụng. Nó không đọc được cookie qua document.cookie, vậy có thể coi phiên an toàn hoàn toàn không?

**Đáp án:** Không. XSS có thể đọc dữ liệu DOM, gọi API bằng phiên đang hoạt động và quan sát phản hồi hợp lệ. HttpOnly giúp hạn chế đánh cắp trực tiếp session ID, không vô hiệu hóa mọi hành động của mã chạy cùng origin.

### Tình huống C — Dùng innerHTML để hiển thị tên người dùng

Frontend lấy displayName từ API rồi đưa thẳng vào innerHTML để hiển thị. API đã xác thực người dùng, vậy dữ liệu có đáng tin để diễn giải thành HTML không?

**Đáp án:** Không mặc định. DisplayName có thể do chính người dùng hoặc nguồn khác nhập. Nếu chỉ hiển thị text, dùng textContent hoặc cơ chế escape mặc định của framework. Xác thực API không biến mọi trường dữ liệu thành HTML an toàn.

### Tình huống D — CORS chặn website ngoài đọc response

Website outside.test gửi form POST đến API thanh toán. Browser không cho JavaScript ngoài site đọc response do thiếu CORS. Có đủ kết luận API chống CSRF tốt không?

**Đáp án:** Không. Request form có thể đã đến server và thực hiện tác vụ trước khi quyền đọc response bị chặn. Cần kiểm tra CSRF token, cookie SameSite, authentication, authorization và method.

### Tình huống E — SameSite=Lax và liên kết GET

Ứng dụng dùng cookie SameSite=Lax và có endpoint GET /transfer?amount=100 làm chuyển tiền. Người dùng bấm liên kết đó từ một website ngoài. Cookie có thể được gửi không?

**Đáp án:** Có thể. SameSite=Lax thường cho phép top-level navigation GET cross-site. Đây là lý do không dùng GET cho chuyển tiền, hủy đơn hay hành động thay đổi trạng thái.

### Tình huống F — Header X-CSRF-TOKEN hiện diện

Server chỉ kiểm tra xem POST có header X-CSRF-TOKEN không, không so sánh giá trị token với repository. Như vậy đã chống CSRF đúng chưa?

**Đáp án:** Chưa. Việc kiểm tra header hiện diện không tương đương xác minh một token thật được cấp và liên kết với luồng hợp lệ. Hãy sử dụng CSRF protection đúng cơ chế của Spring Security.

### Tình huống G — Sec-Fetch-Site: same-site

Một request đến API mang Sec-Fetch-Site: same-site, Origin: https://untrusted.example.com. API có thể bỏ qua CSRF token vì đây là cùng site không?

**Đáp án:** Không. Subdomain không đáng tin có thể cùng registrable domain với API. Sec-Fetch-Site chỉ là tín hiệu hỗ trợ browser, không phải bằng chứng danh tính hoặc quyền thao tác.

### Tình huống H — CSP trên API JSON

Frontend ở https://app.example.com, API ở https://api.example.com. API thêm CSP script-src 'self' vào mọi response JSON. Có thể kết luận trang HTML của app.example.com đã được CSP bảo vệ chưa?

**Đáp án:** Không. CSP có hiệu lực theo tài liệu/response mà browser xử lý; CSP trên API JSON khác origin không tự áp dụng lên HTML frontend. Cần cấu hình CSP trên response phục vụ document của frontend.

### Tình huống I — CSP cho phép script nguồn đã bị xâm nhập

Một script CDN nằm trong allowlist script-src và bị thay bằng mã độc trên CDN. CSP có bảo đảm mã đó không chạy không?

**Đáp án:** Không. CSP allowlist chỉ giới hạn nguồn, không chứng minh nội dung nguồn đó đáng tin. Cân nhắc SRI với tài nguyên tĩnh, pin phiên bản, kiểm soát dependency và giảm mức tin cậy của script.

### Tình huống J — Iframe khác origin dùng postMessage

Ứng dụng nhận mọi message rồi dùng event.data.html làm innerHTML, không kiểm tra event.origin. Có những vấn đề gì?

**Đáp án:** Trang ngoài có thể gửi message không mong muốn, thậm chí đẩy dữ liệu vào DOM sink nguy hiểm. Cần xác minh event.origin/source, validate schema, giới hạn hành động và dùng DOM API an toàn; nếu hiển thị text, dùng textContent.

### Tình huống K — Client-side CSRF từ query string

Frontend tự đọc tham số action từ URL, ghép vào đường dẫn /api/ rồi gửi POST kèm CSRF token hợp lệ. Một URL từ bên ngoài khiến script gọi action mà người dùng không chủ ý. Đây là kiểu lỗi gì?

**Đáp án:** Đó là một dạng **client-side CSRF**, nơi dữ liệu không đáng tin điều khiển mã hợp lệ gửi request. CSRF token không tự chặn vì chính mã frontend hợp lệ đã gắn token. Cần loại bỏ cách ghép đường dẫn/method nhạy cảm, dùng allowlist và phân quyền server.

### Tình huống L — Clickjacking dù SOP vẫn hoạt động

Một trang ngân hàng cho phép mọi website nhúng nó vào iframe. Trang ngoài không thể đọc DOM iframe vì SOP. Có thể coi đã chống clickjacking chưa?

**Đáp án:** Không. Clickjacking liên quan thao túng giao diện khiến người dùng nhấp ngoài ý muốn, không đòi đọc DOM cross-origin. Cần dùng frame-ancestors/X-Frame-Options và các xác nhận phù hợp với chức năng nhạy cảm.

### Tình huống M — API POST lỗi CORS nhưng đã xử lý

Frontend gửi POST đặt hàng và báo lỗi CORS. Server log cho thấy đơn đã tạo, nhưng response thiếu Access-Control-Allow-Origin. Frontend nên tự retry ngay không?

**Đáp án:** Không. Request có thể đã thành công ở server nhưng JavaScript không được đọc response. Trước khi retry, cần kiểm tra trạng thái nghiệp vụ, idempotency và sửa response CORS để tránh tạo trùng.

### Tình huống N — OPTIONS trả 401 vì không có cookie

Frontend gửi POST JSON có X-CSRF-TOKEN đến API khác origin. OPTIONS preflight không mang session cookie và bị trả 401. Có nên buộc frontend gửi Cookie header trong OPTIONS không?

**Đáp án:** Không. Browser quản lý preflight, vốn thường không mang cookie phiên. Cần xử lý CORS trước lớp authentication có thể chặn preflight; POST thực vẫn phải vượt qua xác thực, CSRF và phân quyền.

### Tình huống O — Trusted Types thay thế output encoding?

Ứng dụng bật require-trusted-types-for 'script' nên bỏ qua output encoding và tin dữ liệu HTML người dùng nhập. Quyết định này đúng không?

**Đáp án:** Không. Trusted Types bổ sung cơ chế kiểm soát một số DOM sink, không tự làm sạch dữ liệu. Cần dùng HTML sanitizer đúng khi cho phép HTML, escape theo ngữ cảnh và giữ safe DOM APIs.

### Tình huống P — XSS và quyền truy cập

Một script XSS gửi POST hợp lệ đến endpoint sửa đơn hàng của người khác. Nó chạy trong origin của ứng dụng và có CSRF token của user. Server có được chấp nhận không?

**Đáp án:** Không. CSRF token và origin không cấp quyền truy cập đơn hàng khác. Authorization phải kiểm tra user đã xác thực có quyền thao tác đối tượng đó không.

### Tình huống Q — Chỉ bảo vệ CSRF bằng CORS và JSON

Đội phát triển cho phép POST JSON cross-origin từ một frontend duy nhất và tin rằng các form bên ngoài không thể POST JSON nên không cần CSRF token. Server lại chấp nhận text/plain có body giống JSON và tự phân tích. Vấn đề gì?

**Đáp án:** Endpoint có thể bị tác động bởi request không cần preflight thông qua media type được chấp nhận ngoài ý định. Cần thực thi Content-Type đúng hợp đồng, CSRF token khi credential tự gửi, SameSite và kiểm tra quyền; không coi CORS preflight là phòng vệ duy nhất.

### Tình huống R — Báo cáo CSP violation trong production

Sau khi bật CSP chặt chẽ, một số nút không hoạt động và Console báo vi phạm script-src. Có nên tắt CSP hoàn toàn không?

**Đáp án:** Không cần tắt toàn bộ. Xác định script hợp lệ nào đang bị chặn, kiểm tra cơ chế inline/nonce/hash và origin tài nguyên; dùng report-only khi cần thử chính sách. Chỉ nới theo nhu cầu được kiểm chứng, không mở wildcard/unsafe-inline vô điều kiện.

## 16. Checklist áp dụng vào dự án Spring Security

Khi review một tính năng web mới, có thể dùng checklist sau:

### 16.1. Mã chạy trong trang

- [ ] Dữ liệu không đáng tin được output encode hoặc đưa qua safe DOM API đúng ngữ cảnh.
- [ ] Không dùng innerHTML, th:utext, eval hoặc cơ chế thực thi chuỗi nếu không có lý do và kiểm soát chặt chẽ.
- [ ] Script bên thứ ba được kiểm kê, pin phiên bản và đánh giá độ tin cậy.
- [ ] Có CSP phù hợp trên **response HTML của origin phục vụ frontend**, không chỉ trên API JSON.
- [ ] Widget không đáng tin được cách ly bằng iframe/sandbox nếu khả thi.
- [ ] postMessage kiểm tra event.origin/source và schema dữ liệu, không dùng targetOrigin wildcard cho dữ liệu nhạy cảm.
- [ ] Kiểm thử XSS/DOM injection và theo dõi CSP violations.

### 16.2. Yêu cầu từ website bên ngoài

- [ ] GET/HEAD không cố ý làm thay đổi trạng thái nghiệp vụ.
- [ ] POST/PUT/PATCH/DELETE dùng cookie/session có CSRF protection phù hợp.
- [ ] Cookie session có Secure/HttpOnly/SameSite và scope host/path hợp lý.
- [ ] CORS dùng allowlist origin/method/header theo nhu cầu, không phản chiếu mọi Origin khi bật credentials.
- [ ] Preflight OPTIONS được đánh giá trước những filter có thể chặn vì thiếu session cookie.
- [ ] Origin/Referer/Fetch Metadata chỉ là lớp tín hiệu bổ sung với fallback hợp lý; không thay authentication.
- [ ] Server phân quyền theo người dùng và từng tài nguyên/tenant, kể cả với CSRF token hợp lệ.
- [ ] Trang nhạy cảm hạn chế nhúng bằng frame-ancestors/X-Frame-Options thích hợp.
- [ ] Không để URL/query/hash hoặc postMessage không đáng tin quyết định trực tiếp request thay đổi trạng thái.
- [ ] Kiểm tra các đường redirect, error response, cache và proxy/security headers trong môi trường triển khai thực.

### 16.3. Xác minh trước khi đưa vào sử dụng

- [ ] Có test **request cùng origin** và **request từ origin/site không được phép**.
- [ ] Có test **CSRF token thiếu/sai** phải bị từ chối, token hợp lệ nhưng user thiếu quyền vẫn bị từ chối.
- [ ] Có test **OPTIONS preflight** và **request thực** riêng biệt.
- [ ] Kiểm tra CSP trên **document HTML** và CORS trên **response API**.
- [ ] DevTools xác nhận cookie được gửi hay bị chặn và lý do chính xác.
- [ ] Test logout/session invalidation để credential cũ không tiếp tục truy cập tài nguyên.
- [ ] Kiểm tra chức năng đúng khi CSP/frame policy được bật và khi tài nguyên bên thứ ba lỗi hoặc bị từ chối.

## 17. Ghi nhớ

1. **Mã chạy trong origin ứng dụng** có thể đọc nhiều dữ liệu DOM/storage và gọi API theo quyền của trang. Script được tải từ CDN theo cách nhúng thông thường **không tự được sandbox theo origin CDN**.
2. **XSS** là dữ liệu không đáng tin bị diễn giải thành mã; **CSRF** lợi dụng khả năng browser tự gửi credential từ request bên ngoài. Hai mô hình khác nhau nhưng có thể phối hợp trong các tấn công thực tế.
3. **HttpOnly ngăn JavaScript đọc cookie**, nhưng không cản browser gửi cookie cho request hợp lệ và không tự vô hiệu hóa script XSS gọi API.
4. **SOP/CORS hạn chế quyền đọc cross-origin**, không bảo đảm mọi request form, điều hướng hoặc tài nguyên nhúng đều bị chặn. CORS không phải authentication hoặc CSRF protection.
5. **SameSite cookie** giảm một số kiểu CSRF, nhưng **same-site không phải same-origin**, và điều hướng GET cấp cao nhất có thể mang cookie SameSite=Lax.
6. **Output encoding đúng ngữ cảnh, safe DOM APIs và HTML sanitization** là nền tảng ngăn XSS; **CSP, Trusted Types, SRI và cách ly script** giúp phòng vệ nhiều lớp.
7. **CSRF token và authorization** phải được thực thi ở server đối với hành động thay đổi trạng thái sử dụng credential tự gửi. CSRF token không cấp quyền sửa dữ liệu người khác.
8. **Client-side CSRF** xuất hiện khi mã frontend hợp lệ dùng dữ liệu không đáng tin để quyết định request nhạy cảm; cần allowlist luồng và server-side authorization.
9. **Clickjacking** cần frame-ancestors/X-Frame-Options; **XS-Leaks** cần đánh giá tín hiệu phụ, SameSite, Fetch Metadata và các chính sách cô lập phù hợp.
10. Với **Spring Security Servlet và WebFlux**, cấu hình đúng CSRF/CORS/security headers trên **stack và origin thực tế**, kiểm thử cả browser lẫn server, và không đánh đồng lỗi CSP, CORS, CSRF hoặc phân quyền.
