# Giới hạn của Same-Origin Policy (SOP)

## 1. Đặt vấn đề: SOP bảo vệ điều gì và dừng lại ở đâu?

**Same-Origin Policy (SOP)** là một nền tảng cách ly của trình duyệt: mã chạy trong tài liệu thuộc một origin thường không được tùy ý đọc DOM hoặc dữ liệu được bảo vệ của tài liệu thuộc origin khác. Với URL HTTP(S) thông thường, origin được xác định bởi **scheme, host, port**.

Ví dụ:

- `https://shop.example.test` và `https://shop.example.test/cart`: cùng origin.
- `https://shop.example.test` và `https://api.example.test`: khác origin do khác host.
- `http://localhost:3000` và `http://localhost:4000`: khác origin do khác port.
- `http://shop.example.test` và `https://shop.example.test`: khác origin do khác scheme.

Nếu chỉ nhớ “SOP cấm trang web này truy cập trang web khác”, ta sẽ hiểu sai nhiều hành vi bảo mật. SOP **không phải tường lửa mạng, cơ chế xác thực, kiểm soát phân quyền, bộ lọc XSS hay giải pháp chống CSRF**. Một số tương tác cross-origin được trình duyệt chủ động cho phép vì web cần liên kết, biểu mẫu, ảnh, stylesheet, script và iframe từ nhiều nguồn.

Bài học **“Giới hạn của SOP”** thuộc chương **Same-origin policy** của module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`. Trong phạm vi bảo mật ứng dụng web, việc hiểu đúng giới hạn giúp thiết kế CORS, cookie, CSP, Trusted Types, iframe sandbox và security headers một cách có chủ đích; đồng thời xác định việc nào **bắt buộc do backend quyết định**.

### Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Phân biệt **gửi request**, **nhúng tài nguyên**, **đọc response**, **đọc DOM**, **thực thi script** và **thay đổi trạng thái máy chủ**.
2. Chỉ ra ví dụ cụ thể chứng minh SOP không chặn mọi hoạt động cross-origin.
3. Giải thích vì sao vẫn có thể xảy ra **CSRF**, **clickjacking**, **XSS** hoặc rò rỉ thông tin gián tiếp dù SOP đang hoạt động đúng.
4. Hiểu những ngoại lệ có kiểm soát như **CORS** và **`postMessage`**, cùng trách nhiệm xác minh nguồn gửi.
5. Phân tích các lớp bảo vệ bổ sung: cookie `SameSite`, CSRF token, CSP, Trusted Types, `frame-ancestors`, CORP, COOP, COEP và kiểm tra quyền backend.
6. Quan sát thực tế bằng DevTools và thử nghiệm cục bộ, tránh kết luận chỉ từ một dòng lỗi trên Console.

## 2. Bản đồ ranh giới: SOP không phải câu trả lời cho mọi hành động

Sơ đồ sau minh họa luồng thường gặp trong một ứng dụng thương mại:

~~~mermaid
flowchart LR
    U["Người dùng"] --> A["Frontend<br/>https://shop.example.test"]
    A -->| "fetch()" | B["API<br/>https://api.example.test"]
    X["Trang khác<br/>https://outside.test"] -->| "form / link / image" | B
    A -->| "iframe" | P["Thanh toán<br/>https://pay.vendor.test"]
    A -->| "script src" | S["Script bên thứ ba<br/>https://cdn.vendor.test"]
    P <-->| "postMessage" | A
    D["Dữ liệu người dùng<br/>review / URL / JSON"] --> A
~~~

Trong sơ đồ có ít nhất **năm ranh giới khác nhau**:

| Ranh giới | Câu hỏi bảo mật | Chủ thể kiểm soát chính |
| --- | --- | --- |
| Frontend ↔ response của API khác origin | JavaScript có đọc được response không? | SOP và CORS tại trình duyệt; backend cấu hình CORS. |
| Trang bên ngoài → request đến API | Request có được gửi? Nếu đến nơi, có được thực hiện? | Trình duyệt có các hạn chế gửi nhất định; **backend** kiểm tra xác thực, CSRF, phân quyền. |
| Frontend ↔ iframe | Có đọc được DOM của nhau? Có được nhúng? | SOP, iframe sandbox, CSP `frame-ancestors`, giao thức `postMessage`. |
| Script CDN → môi trường thực thi frontend | Script được chạy với quyền nào? | Script truyền thống thường chạy trong origin **của trang nhúng**; CSP/SRI và quản lý dependency. |
| Dữ liệu người dùng → DOM, HTML, JavaScript | Dữ liệu có bị biến thành mã thực thi không? | API DOM an toàn, encode/sanitize, CSP, Trusted Types. |

Nói “khác origin” mới là bước đầu phân tích. Cần hỏi rõ **hành động gì**, **tài nguyên gì**, **quyền nào** và **ai có trách nhiệm chặn**.

### 2.1. Ma trận “SOP thường chặn được gì?”

| Hành động từ trang `https://app.example.test` đến `https://other.test` | Kết quả điển hình | Giới hạn hoặc cơ chế khác |
| --- | --- | --- |
| Đọc `iframe.contentWindow.document` | **Bị chặn** nếu iframe khác origin | Một số thao tác cross-origin hẹp vẫn được phép trên `WindowProxy`. |
| Đọc response JSON bằng `fetch` | **Bị giới hạn bởi CORS** | Request có thể đã gửi; CORS là giao thức cho phép đọc có điều kiện. |
| Đọc `localStorage` của origin khác | **Không có quyền trực tiếp** | Chính sách lưu trữ/partitioning có thể áp dụng thêm. |
| Gửi `<form>` cross-origin | **Thường được phép** | Dễ liên quan CSRF; máy chủ phải kiểm tra yêu cầu. |
| Điều hướng bằng liên kết hoặc `location` | **Thường được phép**, tùy ngữ cảnh/chính sách | Điều hướng không đồng nghĩa được đọc tài liệu sau điều hướng. |
| Tải ảnh, CSS, script, media cross-origin | **Thường được phép** | Có hạn chế riêng theo loại tài nguyên, CORS, CORP, CSP và MIME. |
| Nhúng iframe cross-origin | **Thường được phép** | Bên được nhúng có thể từ chối qua `frame-ancestors` hoặc `X-Frame-Options`. |
| Trao đổi thông điệp giữa hai cửa sổ | **Được phép qua `postMessage`** | Các bên phải kiểm tra origin, source và dữ liệu. |
| Gửi dữ liệu đến URL ngoài bằng các cơ chế web | **Có thể** | SOP không phải hệ thống ngăn rò rỉ dữ liệu từ script đã chạy hợp lệ. |
| Gọi API bằng một client không phải trình duyệt | **Không chịu SOP như browser script** | Phải bảo vệ API bằng authentication, authorization và kiểm soát server. |

Các từ “thường” và “điển hình” rất quan trọng: CSP, Fetch Metadata, mixed content, sandbox, cookie policy, các cơ chế chặn theo trình duyệt hoặc mạng có thể bổ sung hạn chế. Không thể kết luận một loại request luôn thành công chỉ vì SOP không chặn nó.

## 3. Giới hạn thứ nhất: SOP không ngăn mọi request cross-origin

Web cần khả năng liên kết tới trang khác, gửi biểu mẫu, tải ảnh và nhúng tài nguyên. Vì vậy trình duyệt có nhiều đường **khởi tạo request** không yêu cầu JavaScript được cấp quyền đọc response.

Ví dụ trang ngoài có biểu mẫu:

~~~html
<form action="https://account.example.test/profile" method="POST">
  <input type="hidden" name="displayName" value="Changed">
  <button type="submit">Gửi</button>
</form>
~~~

Nếu người dùng kích hoạt biểu mẫu, trình duyệt có thể gửi POST đến `account.example.test`. Kẻ tạo trang ngoài **không vì thế mà đọc được response**, nhưng nếu endpoint thiếu bảo vệ, request có thể làm thay đổi trạng thái trên máy chủ.

Đây là lý do **SOP không phải cơ chế chống CSRF**.

### 3.1. Gửi request và đọc response là hai quyết định khác nhau

Giả sử trang `http://localhost:3000` chạy:

~~~js
fetch("http://localhost:4000/status")
  .then((response) => response.json())
  .then(console.log)
  .catch(console.error);
~~~

Nếu API không cho phép origin 3000 qua CORS, trình duyệt thường báo lỗi đọc response. Nhưng với request GET thông thường, **máy chủ cổng 4000 vẫn có thể đã nhận và xử lý request**.

Không nên suy luận:

> “Console báo CORS error, vậy máy chủ chưa thấy yêu cầu.”

Đó là kết luận không có đủ cơ sở. Phải xem tab **Network**, loại request, preflight và log backend.

### 3.2. Request “simple” và preflight

CORS sử dụng cơ chế **preflight** cho một số request cross-origin: trình duyệt gửi `OPTIONS` để hỏi máy chủ có chấp nhận method/header hay không. Tuy nhiên không phải mọi request đều preflight. Các request đáp ứng những điều kiện nhất định về method, headers và content type có thể đi ngay mà không cần preflight.

Ví dụ biểu mẫu HTML `application/x-www-form-urlencoded` hoặc `multipart/form-data` thường có thể khởi tạo POST cross-origin mà không cần yêu cầu CORS để được gửi.

Vì vậy:

- **Có preflight** không phải bằng chứng request đã được xác thực.
- **Không có preflight** không phải lỗ hổng tự thân; đó là hành vi thiết kế của web.
- **Chặn response bằng CORS** không đồng nghĩa đã chặn thay đổi trạng thái.
- **Backend** phải xác thực user, kiểm tra quyền và có biện pháp chống CSRF thích hợp với cơ chế phiên đang dùng.

### 3.3. CSRF: cookie được tự động gửi là phần của vấn đề

Nếu ứng dụng dùng cookie phiên, trình duyệt có thể tự đính kèm cookie khi gửi request đáp ứng chính sách cookie. Một trang bên ngoài có thể lợi dụng khả năng **khởi tạo request có thông tin phiên đi kèm** nếu endpoint thiếu phòng vệ.

Các lớp bảo vệ thường dùng:

1. Endpoint đổi trạng thái sử dụng method phù hợp; **GET không được thực hiện thay đổi nghiệp vụ nhạy cảm**.
2. Với phiên dựa trên cookie, dùng **CSRF token** hoặc mô hình phòng vệ tương đương và kiểm tra ở máy chủ.
3. Kiểm tra `Origin`/`Referer` hoặc Fetch Metadata headers phù hợp với loại endpoint; xác định rõ chính sách khi header thiếu.
4. Thiết lập cookie `SameSite`, `Secure`, `HttpOnly`, phạm vi `Domain`/`Path` phù hợp.
5. Kiểm tra **authentication**, **authorization**, ownership và ràng buộc nghiệp vụ cho từng request.

**Ví dụ tình huống:** Endpoint `POST /change-email` chỉ kiểm tra cookie phiên và nhận email mới từ form. SOP không đủ để chứng minh người dùng muốn thay email. API cần kiểm tra CSRF và có thể yêu cầu xác thực lại cho hành động nhạy cảm.

## 4. Giới hạn thứ hai: SOP cho phép nhiều kiểu nhúng cross-origin

Một trang có thể hiển thị nội dung từ nguồn khác mà không được đọc dữ liệu nội bộ của nội dung đó.

~~~html
<img src="https://images.vendor.test/banner.png" alt="Banner">

<link rel="stylesheet" href="https://cdn.vendor.test/site.css">

<iframe
  src="https://payment.vendor.test/checkout"
  title="Thanh toán"
></iframe>
~~~

Khả năng **hiển thị/nhúng** và quyền **đọc qua JavaScript** không đồng nghĩa nhau.

| Tài nguyên nhúng | Điều thường được phép | Điều vẫn bị giới hạn |
| --- | --- | --- |
| Ảnh cross-origin | Hiển thị ảnh trên trang | Đọc pixel từ canvas nếu ảnh làm canvas `tainted` và chưa được cấp CORS phù hợp. |
| Stylesheet cross-origin | Áp dụng style | Đọc trực tiếp `cssRules` của stylesheet cross-origin có thể bị chặn bởi bảo vệ CSSOM. |
| Iframe cross-origin | Hiển thị tài liệu bên ngoài | Truy cập trực tiếp DOM, cookie, storage và nhiều thuộc tính của frame. |
| Script qua `<script src>` truyền thống | Tải và thực thi script nếu chính sách cho phép | **Không** bị cách ly trong origin của host cung cấp script; đây là một rủi ro khác. |

Các kiểu nhúng có thể còn bị kiểm soát bởi CSP, CORS theo yêu cầu từng loại tài nguyên, CORP, COEP, MIME type, `nosniff`, chính sách trình duyệt và server. Không thể dựa vào việc SOP chặn DOM để suy rằng mọi nội dung bên ngoài đều vô hại.

### 4.1. Iframe bị chặn đọc DOM vẫn có thể gây clickjacking

Một trang tấn công có thể cố nhúng trang thanh toán hoặc trang quản trị vào iframe, rồi đặt lớp giao diện đánh lừa người dùng nhấp vào một nút thật bên trong. Kẻ tấn công **không cần đọc DOM iframe** để gây ra **clickjacking**; họ có thể khai thác bố cục giao diện, tương tác của người dùng và việc trang được phép nhúng.

Bảo vệ nằm ở **response của trang cần bảo vệ**:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Hoặc cho phép một parent cụ thể:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://trusted-portal.example.test
~~~

`frame-ancestors` giới hạn **ai được nhúng trang hiện tại**. Đừng nhầm với `frame-src`, chỉ thị giới hạn **trang hiện tại được nhúng nội dung từ đâu**.

`X-Frame-Options: DENY` hoặc `SAMEORIGIN` có thể bổ sung khả năng tương thích cho những trường hợp phù hợp. Việc kiểm soát hành động nghiệp vụ vẫn thuộc backend, dù trang đã được bảo vệ chống nhúng.

### 4.2. Iframe sandbox bổ sung ranh giới mà SOP chưa thể hiện

Ví dụ một widget ít tin cậy:

~~~html
<iframe
  src="https://widget.vendor.test/preview"
  sandbox="allow-scripts"
  referrerpolicy="no-referrer"
  title="Widget preview"
></iframe>
~~~

`sandbox` hạn chế các năng lực của iframe. Khi không có `allow-same-origin`, nội dung sandbox thường có **opaque origin**, giúp hạn chế hơn so với chỉ xét host URL.

Chỉ cấp những token `allow-*` cần thiết. Đặc biệt, dùng `allow-scripts` cùng `allow-same-origin` cho nội dung **cùng origin** có thể làm mất tác dụng cách ly sandbox, vì nội dung có thể tìm cách gỡ sandbox và tải lại. Với nội dung không tin cậy, dùng origin riêng và giao thức `postMessage` hẹp, có kiểm tra.

### 4.3. Script bên thứ ba không được SOP sandbox

Một nhầm lẫn nguy hiểm:

~~~html
<script src="https://cdn.vendor.test/analytics.js"></script>
~~~

Script truyền thống tải từ CDN thường thực thi **trong origin và môi trường JavaScript của trang nhúng**. Nếu script bị thay thế bằng mã độc, nó có thể đọc/sửa DOM và thực hiện các hành động mà script của ứng dụng được phép. SOP không tạo một “vùng an toàn” chỉ vì `src` là URL khác origin.

Biện pháp bổ sung:

- Chỉ tải script từ nguồn thực sự cần và có mức tin cậy phù hợp.
- Dùng CSP `script-src` với chính sách chặt chẽ; cân nhắc nonce/hash nơi phù hợp.
- Dùng **Subresource Integrity (SRI)** với tài nguyên tĩnh mà bạn cần xác minh đúng phiên bản; đồng thời xử lý yêu cầu CORS đối với nguồn cross-origin khi cần.
- Giảm dependency, kiểm soát cập nhật và sử dụng iframe khác origin để cách ly widget ít tin cậy.
- Đừng coi **Trusted Types** là biện pháp cô lập script ngoài: nó bảo vệ một số DOM sinks, không thay đổi origin của script đang chạy.

## 5. Giới hạn thứ ba: SOP không bảo vệ khi mã độc đã chạy cùng origin

SOP coi script đang chạy trong tài liệu của `https://app.example.test` là mã có quyền của môi trường đó theo các chính sách hiện hành. Nếu ứng dụng đưa dữ liệu không tin cậy vào HTML hoặc script sink, **XSS** có thể khiến mã do kẻ tấn công điều khiển chạy **ngay trong origin hợp lệ**.

Ví dụ lỗi:

~~~js
const username = new URLSearchParams(location.search).get("name") ?? "";
document.querySelector("#welcome").innerHTML =
  "Xin chào, " + username;
~~~

`innerHTML` diễn giải chuỗi thành HTML; dữ liệu đến từ query URL có thể tạo markup hoặc handler không mong muốn. SOP **không** giúp phân biệt “script do nhà phát triển viết” với “script do XSS tạo ra” khi cả hai đã nằm trong cùng môi trường thực thi.

Cách xử lý an toàn nếu chỉ muốn hiển thị chữ:

~~~js
const username = new URLSearchParams(location.search).get("name") ?? "";
document.querySelector("#welcome").textContent =
  "Xin chào, " + username;
~~~

Các biện pháp cần thiết:

- Sử dụng API DOM nhận **text** như `textContent` khi không cần HTML.
- Nếu thực sự cần HTML đầu vào, dùng giải pháp **sanitize** có duy trì và cấu hình chặt, cộng với encoding theo ngữ cảnh khi render.
- Tránh các sink nguy hiểm như `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval` hoặc mã thực thi sinh từ chuỗi không tin cậy.
- Dùng **CSP** làm lớp giảm tác động, ví dụ hạn chế nguồn script và inline execution.
- Cân nhắc **Trusted Types** trên trình duyệt hỗ trợ để giảm việc truyền chuỗi chưa kiểm soát vào các DOM injection sinks.

Ví dụ cấu hình chính sách minh họa:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; object-src 'none'; base-uri 'none'
~~~

Nonce phải được sinh ngẫu nhiên, khó đoán cho **mỗi response HTML** và gắn vào những script được cấp phép. Cần thiết kế và kiểm thử chính sách phù hợp với tài nguyên thật của ứng dụng. Cấu hình CSP không thay thế sửa XSS ở nguồn.

Trusted Types có thể tăng cường ranh giới dữ liệu/HTML:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types appPolicy
~~~

Đây chỉ là một minh họa chính sách: ứng dụng phải định nghĩa policy đáp ứng đúng chức năng và **thực sự sanitize dữ liệu** nếu chấp nhận HTML. Trusted Types không mặc định được hỗ trợ giống nhau trên mọi trình duyệt.

### 5.1. Vì sao `HttpOnly` chưa đủ khi có XSS?

Cookie `HttpOnly` ngăn truy cập cookie qua `document.cookie`, nhưng XSS chạy trong origin hợp lệ vẫn có thể thực hiện những hành động mà frontend bình thường được phép, chẳng hạn gọi API trong phiên của người dùng, đọc dữ liệu DOM hoặc response cùng origin, hoặc thay đổi giao diện để lừa người dùng.

Vì vậy “có `HttpOnly` và có SOP” không biến XSS thành vô hại. Phải chống đưa dữ liệu thành mã thực thi và kiểm tra quyền nghiệp vụ ở máy chủ.

## 6. Giới hạn thứ tư: CORS mở quyền đọc có kiểm soát nhưng không là cơ chế phân quyền

CORS (**Cross-Origin Resource Sharing**) bổ sung cơ chế cho phép trình duyệt cung cấp response cross-origin cho JavaScript của những origin được máy chủ cho phép.

Giả sử trang ở `https://app.example.test` muốn đọc API `https://api.example.test`:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

API có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Khi thực sự dùng cookie/credentials cross-origin và cho phép chúng, phía client có thể viết:

~~~js
fetch("https://api.example.test/v1/orders", {
  credentials: "include"
});
~~~

Và API cần phản hồi có điều kiện phù hợp, ví dụ:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Cookie có được gửi hay không còn phụ thuộc `Domain`/host, `SameSite`, `Secure` và chính sách cookie của trình duyệt. `credentials: "include"` không ép trình duyệt bỏ qua những quy tắc này.

### 6.1. Những điều CORS không làm

1. **Không xác thực người gọi.** Một client ngoài trình duyệt có thể tự gửi header `Origin` hoặc không gửi; SOP/CORS không bảo vệ API khỏi client tự do gửi HTTP.
2. **Không quyết định user có quyền đọc đơn hàng nào.** Quyền nghiệp vụ vẫn phải kiểm tra ở backend.
3. **Không chống CSRF** cho mọi tình huống. Form hoặc một số request có thể được gửi cross-origin mà không cần đọc response.
4. **Không tự động ngăn mọi request đến máy chủ** khi JavaScript gặp CORS error.
5. **Không giới hạn việc thực thi script được nhúng** theo nguyên tắc origin của nguồn script.
6. **Không bảo đảm rằng một origin được allowlist đáng tin trong mọi thời điểm**: origin có thể bị XSS hoặc bị chiếm quyền.

### 6.2. Cấu hình CORS sai có thể làm mất ranh giới đọc

Ví dụ anti-pattern:

~~~http
Access-Control-Allow-Origin: https://untrusted.test
Access-Control-Allow-Credentials: true
~~~

Nếu `untrusted.test` không phải origin đáng tin mà API trả dữ liệu nhạy cảm theo cookie, chính sách này có thể cho phép JavaScript từ origin đó đọc response bằng thông tin phiên trong những điều kiện cookie/trình duyệt cho phép. Tương tự, việc **phản chiếu bất kỳ header `Origin`** mà không có allowlist tạo cấu hình quá rộng.

Tránh kiểm tra tùy tiện:

~~~js
// Không an toàn: đối tượng tấn công có thể dùng api.example.test.attacker.test
if (origin.includes("example.test")) {
  allowCors(origin);
}
~~~

Thay bằng allowlist **origin đầy đủ**:

~~~js
const allowedOrigins = new Set([
  "https://app.example.test",
  "https://admin.example.test"
]);

if (allowedOrigins.has(requestOrigin)) {
  // Cấu hình CORS tương ứng với tài nguyên và cách xác thực.
}
~~~

Cần chú ý cả scheme lẫn port; `https://app.example.test:8443` là origin khác `https://app.example.test`.

### 6.3. `mode: "no-cors"` không phải “tắt bảo mật”

Một nhầm lẫn khác là cố sửa lỗi CORS bằng:

~~~js
const response = await fetch("https://api.example.test/private", {
  mode: "no-cors"
});

console.log(response.type); // Thông thường: "opaque"
~~~

Với request cross-origin `no-cors` thông thường, JavaScript chỉ nhận được **opaque response**, không đọc được body hoặc phần lớn thông tin response. `no-cors` còn giới hạn một số lựa chọn method/header mà mã có thể dùng; nó không phải đường tắt để đọc JSON bị SOP chặn.

## 7. Giới hạn thứ năm: origin không đồng nghĩa với site hay phạm vi cookie

Origin được xác định bằng `scheme + host + port`. Trong mô hình **schemeful same-site**, site của URL HTTP(S) thường dựa trên scheme và **registrable domain** theo Public Suffix List.

| Địa chỉ A ↔ B | Quan hệ origin | Quan hệ site |
| --- | --- | --- |
| `https://app.example.test` ↔ `https://api.example.test` | Khác origin | Cùng site |
| `https://app.example.test` ↔ `https://app.example.test:8443` | Khác origin | Cùng site |
| `https://app.example.test` ↔ `http://app.example.test` | Khác origin | Khác site theo schemeful model |
| `https://app.example.test` ↔ `https://other.test` | Khác origin | Khác site |

Cookie không được cách ly hoàn toàn bằng bộ ba origin:

- Cookie xét host/`Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite` và các chính sách khác.
- **Port không phải ranh giới riêng của cookie**. Hai dịch vụ cùng host nhưng khác cổng có thể liên quan đến cùng cookie phù hợp.
- `localStorage` và IndexedDB về nguyên tắc gắn với origin, dù các browser hiện đại còn có partitioning theo ngữ cảnh.
- `SameSite` xét quan hệ **site**, không đơn giản là phép so origin.

Ví dụ session cookie:

~~~http
Set-Cookie: __Host-session=opaqueValue; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Prefix `__Host-` trong trình duyệt hỗ trợ yêu cầu `Secure`, `Path=/` và không có `Domain`, giúp giữ cookie ở host gốc. Nó không thay thế xác thực hoặc chống CSRF.

### 7.1. Subdomain khác origin vẫn có thể same-site

Giả sử:

- Ứng dụng chính: `https://app.example.test`.
- API: `https://api.example.test`.
- Subdomain cũ: `https://legacy.example.test`.

Ba URL cross-origin với nhau nhưng có thể same-site. Nếu `legacy` bị chiếm quyền, chỉ dựa vào `SameSite=Lax` hoặc `SameSite=Strict` chưa chắc loại trừ các request từ subdomain đó tới API; chúng có thể được xem là same-site.

Do vậy phải đánh giá mức tin cậy của các subdomain, host chứa nội dung do khách hàng kiểm soát, phạm vi cookie và quy tắc backend, ngoài phép so SOP.

### 7.2. Đừng dựa vào `document.domain` để “nới” origin

`document.domain` là cơ chế cũ từng được dùng để làm giảm ràng buộc host giữa một số tài liệu cùng vùng tên miền. Cơ chế này đã **deprecated**, có hạn chế lớn và không tạo giải pháp chia sẻ quyền tổng quát cho `fetch`, storage hay các cơ chế cách ly hiện đại.

Thiết kế mới nên dùng origin rõ ràng, API có phân quyền và giao tiếp `postMessage` được kiểm soát. Khi buộc phải tích hợp legacy, phải kiểm chứng hành vi của trình duyệt mục tiêu thay vì xem `document.domain` là đường tắt bảo mật.

## 8. Giới hạn thứ sáu: `postMessage` là ngoại lệ có chủ đích, bên nhận phải tự kiểm tra

SOP ngăn truy cập DOM trực tiếp giữa phần lớn các tài liệu cross-origin, nhưng cung cấp kênh giao tiếp qua `window.postMessage`. Đây là một **cơ chế trao đổi dữ liệu được phép**, không phải bằng chứng mọi thông điệp đều an toàn.

Ví dụ trang cha có iframe thanh toán:

~~~html
<iframe
  id="checkout"
  src="https://pay.vendor.test/checkout"
  title="Cổng thanh toán"
></iframe>
~~~

Gửi thông điệp tới đích cụ thể:

~~~js
const checkout = document.querySelector("#checkout");

checkout.contentWindow.postMessage(
  { type: "checkout-init", orderId: "order-123" },
  "https://pay.vendor.test"
);
~~~

Nhận thông điệp từ iframe:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://pay.vendor.test") return;
  if (event.source !== checkout.contentWindow) return;

  const data = event.data;
  if (!data || typeof data !== "object") return;
  if (data.type !== "checkout-status") return;
  if (typeof data.orderId !== "string") return;

  // Đây chỉ là tín hiệu từ client.
  // Server cần xác minh trạng thái thật với nhà cung cấp thanh toán.
  refreshOrderStatusFromBackend(data.orderId);
});
~~~

Bốn giới hạn phải nhớ:

1. **`postMessage` không tự xác thực bên gửi.** Phải kiểm tra `event.origin` và khi phù hợp, `event.source`.
2. **`event.data` là dữ liệu không tin cậy.** Validate schema, kiểu, giới hạn độ dài và ý nghĩa nghiệp vụ.
3. **`targetOrigin: "*"`** có thể làm lộ dữ liệu nếu cửa sổ đích bị điều hướng sang origin khác; chỉ dùng khi thật sự có cơ sở thiết kế cho phép.
4. **`event.origin === "null"`** không chứng minh cùng một origin đặc biệt đáng tin: các opaque origin khác nhau có thể đều được serialize thành chuỗi `"null"`.

Mọi trạng thái liên quan đến thanh toán, phân quyền hoặc giao dịch quan trọng phải được backend xác minh. Thông điệp trình duyệt chỉ nên mang dữ liệu và tín hiệu cần thiết.

### 8.1. Quyền rất hạn chế trên `WindowProxy` cross-origin

Khi có tham chiếu đến cửa sổ hoặc iframe khác origin, JavaScript thường không đọc được `document`, nhưng có thể thực hiện một số thao tác hạn chế tùy chính sách như gửi message hoặc một số loại điều hướng. Đây là hành vi có chủ đích để hỗ trợ web, không phải bằng chứng DOM đã được mở.

Khi mở tab khác:

~~~html
<a
  href="https://external.example.test/"
  target="_blank"
  rel="noopener noreferrer"
>Trang ngoài</a>
~~~

`noopener` giúp cắt quan hệ `window.opener` để giảm những kiểu tấn công như tabnabbing. `noreferrer` giảm việc gửi thông tin referrer; không bắt buộc phải dùng cả hai trong mọi luồng vì có thể ảnh hưởng nghiệp vụ tracking.

## 9. Giới hạn thứ bảy: còn có những kênh rò rỉ gián tiếp

SOP thường chặn JavaScript đọc trực tiếp body hoặc DOM của origin khác, nhưng **không bảo đảm tuyệt đối rằng mọi đặc tính của tài nguyên cross-origin đều bị che giấu**.

Các biến thể được nghiên cứu dưới tên **Cross-Site Leaks (XS-Leaks)** có thể khai thác những khác biệt quan sát được giữa các trường hợp: tài nguyên có tải được không, chuyển hướng ra sao, thời gian phản hồi, trạng thái tương tác hoặc hành vi nhúng trong một số trình duyệt/ngữ cảnh.

Ví dụ mô hình đe dọa:

1. Một endpoint trả phản hồi khác nhau tùy người dùng có đang đăng nhập hoặc có một tài nguyên hay không.
2. Trang ngoài không đọc được JSON vì SOP.
3. Nhưng thông qua các hành vi mà trình duyệt cho phép quan sát, trang ngoài có thể suy luận **một bit thông tin** từ thành công/thất bại, timing hoặc hành vi tải/nhúng.
4. Lặp lại quan sát có thể dẫn đến rò rỉ thông tin, dù chưa bao giờ đọc trực tiếp nội dung response.

Mức độ khả thi rất phụ thuộc API, browser và các chính sách khác. Không nên suy từ ví dụ khái niệm rằng mọi tín hiệu `load`/`error` đều cho phép đọc trạng thái HTTP hoặc nội dung cross-origin.

### 9.1. Các lớp giảm rò rỉ bên cạnh SOP

| Biện pháp | Tác dụng chính | Giới hạn cần hiểu |
| --- | --- | --- |
| `Cross-Origin-Resource-Policy` (CORP) | Để tài nguyên khai báo phạm vi có thể được nhúng/tải trong ngữ cảnh `no-cors` tương ứng | Không thay authentication và không phải bộ kiểm soát truy cập API tổng quát. |
| `Cross-Origin-Opener-Policy` (COOP) | Kiểm soát quan hệ giữa tài liệu top-level và các cửa sổ khác trong browsing context group | Có thể ảnh hưởng popup/đăng nhập liên kết. |
| `Cross-Origin-Embedder-Policy` (COEP) | Áp đặt điều kiện nghiêm ngặt hơn khi nhúng tài nguyên cross-origin, tùy chế độ | Có thể làm hỏng CDN, widget, iframe chưa tương thích. |
| Fetch Metadata headers | Giúp backend phân biệt ngữ cảnh request như same-origin, same-site, cross-site | Cần xây chính sách server cho từng endpoint và xử lý client không gửi header. |
| `Cache-Control`, thiết kế endpoint | Giảm rò rỉ qua cache và phản hồi nhạy cảm | Không tự loại trừ mọi XS-Leak. |
| Tái thiết kế hành vi nhạy cảm | Tránh tiết lộ sự khác biệt trạng thái qua tài nguyên có thể nhúng hoặc request vô tình | Cần phân tích threat model và kiểm chứng thực tế. |

Ví dụ resource chỉ cho phép một số tình huống nhúng:

~~~http
Cross-Origin-Resource-Policy: same-origin
~~~

Ví dụ trang cần cross-origin isolation có thể đánh giá:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Những header trên cần thử tương thích với tài nguyên và luồng đăng nhập, popup, widget thực tế. Chúng **không** làm biến mất nhu cầu bảo vệ CSRF, XSS, clickjacking hay backend authorization.

### 9.2. Browser không phải firewall chống truy cập API

Một API có dữ liệu bí mật mà chỉ trông chờ CORS/SOP sẽ không được bảo vệ khi client là:

- `curl` hoặc chương trình HTTP tùy ý;
- ứng dụng native hoặc máy chủ khác;
- mã script chạy trong origin đã được API cho phép nhưng bị XSS;
- client truy cập từ công cụ kiểm thử hoặc dịch vụ không chịu chính sách trình duyệt.

CORS hữu ích để kiểm soát quyền đọc **trong môi trường trình duyệt**, không phải access control được tin cậy ở backend. API cần kiểm tra danh tính, phân quyền và tốc độ/truy cập theo yêu cầu.

## 10. Giới hạn thứ tám: không phải kênh mạng nào cũng chịu cùng quy tắc CORS

Một số cơ chế giao tiếp trình duyệt có mô hình bảo vệ riêng. **WebSocket** là ví dụ quan trọng: kết nối WebSocket từ trình duyệt có thể gửi header `Origin` trong quá trình handshake nhưng không tuân theo cơ chế preflight/`Access-Control-Allow-Origin` giống `fetch` CORS thông thường.

Ví dụ client:

~~~js
const ws = new WebSocket("wss://realtime.example.test/socket");

ws.addEventListener("open", () => {
  ws.send(JSON.stringify({ type: "subscribe", channel: "order-status" }));
});
~~~

Nếu máy chủ WebSocket dùng cookie hoặc phương thức xác thực chịu các điều kiện cross-origin, cần **kiểm tra Origin theo allowlist** trong handshake khi thích hợp, xác thực phiên, phân quyền từng kênh và kiểm tra message. Không thể chỉ cấu hình CORS cho endpoint HTTP rồi giả định WebSocket được bảo vệ tương đương.

Các API khác như WebRTC, BroadcastChannel, Service Worker, canvas hoặc Web Storage cũng có phạm vi và điều kiện truy cập riêng. Mỗi bề mặt cần đánh giá bằng chính sách áp dụng cho nó; không mặc định SOP có một “công tắc” chung cho mọi quyền.

### 10.1. DNS và kết nối không là phép định danh origin

Origin xét **host trong URL** chứ không phải chỉ IP đích tại thời điểm kết nối. Hai tên host khác nhau có thể cùng trỏ đến một IP nhưng vẫn khác origin. Ngược lại, DNS có thể thay đổi đích kết nối của một hostname theo thời gian; bản thân SOP không được thiết kế làm chính sách firewall theo mạng nội bộ.

Khi thiết kế hệ thống local/admin, cần thêm kiểm soát ở server và mạng: xác thực, kiểm tra `Host` khi phù hợp, hạn chế truy cập dịch vụ quản trị và chính sách đối với các request hướng vào mạng riêng. Một số trình duyệt có cơ chế bảo vệ yêu cầu mạng riêng, nhưng không nên dựa vào một hành vi hỗ trợ cụ thể để bỏ bảo vệ backend.

## 11. Case study: cửa hàng điện tử có frontend, API và widget đối tác

Giả sử hệ thống gồm:

| Thành phần | Địa chỉ | Mong đợi bảo mật |
| --- | --- | --- |
| Trang bán hàng | `https://shop.example.test` | Hiển thị catalog, đơn hàng của người dùng. |
| API | `https://api.example.test` | Trả dữ liệu đúng quyền, xử lý đặt hàng. |
| Trang quản trị | `https://admin.example.test` | Chỉ nhân viên có quyền mới được thao tác. |
| Widget đánh giá | `https://reviews.vendor.test` | Hiển thị nội dung bên thứ ba, hạn chế quyền tác động trang chính. |
| Cổng thanh toán | `https://pay.vendor.test` | Trao đổi thông điệp và xác minh giao dịch. |
| Trang ngoài | `https://outside.test` | Không được đọc dữ liệu cá nhân hoặc kích hoạt thay đổi trái ý người dùng. |

### Tình huống A: Trang ngoài gửi form đổi địa chỉ

SOP không cho `outside.test` đọc DOM `shop.example.test`, nhưng trang ngoài có thể tạo form POST tới API. Nếu request mang cookie phiên và API thiếu CSRF token/kiểm tra nguồn phù hợp, thay đổi vẫn có thể xảy ra.

**Cách khắc phục:** token hoặc cơ chế chống CSRF tương đương, kiểm tra quyền và ownership ở API, cấu hình cookie phù hợp. CORS không phải đáp án chính cho tình huống này.

### Tình huống B: Widget bên thứ ba bị thay đổi

Nếu `shop` nhúng widget bằng `<script src>` truyền thống, script chạy trong môi trường frontend. SOP không cách ly đoạn mã này.

**Cách khắc phục:** hạn chế dependency, kiểm soát tính toàn vẹn và nguồn tải, CSP phù hợp, hoặc dùng iframe có origin riêng và sandbox khi có thể. Kiểm soát nội dung dữ liệu vào DOM để chống XSS.

### Tình huống C: Trang quản trị bị lồng trong trang giả

Nếu `admin` cho phép nhúng, trang ngoài có thể cố gắng dựng clickjacking, dù không đọc được DOM iframe.

**Cách khắc phục:** `frame-ancestors` phù hợp, có thể bổ sung `X-Frame-Options`. Endpoint quản trị vẫn yêu cầu phân quyền server.

### Tình huống D: API cấp CORS quá rộng

Nếu API cho phép origin tùy ý và cho phép credentials, dữ liệu có thể bị script ở origin không đáng tin đọc trong các điều kiện cookie/trình duyệt phù hợp.

**Cách khắc phục:** allowlist origin chính xác, hạn chế credentials, không phản chiếu `Origin` không kiểm tra, phân quyền từng bản ghi và giám sát cấu hình.

### Tình huống E: Iframe gửi “đã thanh toán”

Thông điệp `postMessage` từ iframe có thể bị giả mạo hoặc chứa dữ liệu sai nếu trang cha không xác minh origin và schema. Ngay cả thông điệp đúng nguồn cũng không tự là bằng chứng giao dịch đã tất toán.

**Cách khắc phục:** kiểm tra `event.origin`, `event.source`, schema; để backend đối soát trạng thái từ nguồn đáng tin.

## 12. Thực hành kiểm chứng hành vi thực tế

Các thử nghiệm sau chỉ thực hiện trong môi trường **localhost hoặc staging do bạn kiểm soát**. Mục tiêu là quan sát giới hạn cơ chế, không gọi endpoint của hệ thống khác nếu chưa có quyền.

### Bài thử A — Phân biệt “gửi” và “đọc”

Cần hai máy chủ đơn giản:

- Frontend: `http://localhost:3000`.
- API: `http://localhost:4000`.

Cho API có `GET /hello` trả JSON nhưng **ban đầu không có** `Access-Control-Allow-Origin`.

Tại Console trang frontend:

~~~js
fetch("http://localhost:4000/hello")
  .then((r) => r.json())
  .then(console.log)
  .catch((e) => console.error("Bị hạn chế đọc:", e));
~~~

Quan sát:

1. Console có thể báo lỗi CORS.
2. Tab **Network** và log API có thể cho thấy request GET vẫn được gửi đến API.
3. Thêm header `Access-Control-Allow-Origin: http://localhost:3000` vào API rồi thử lại.
4. Khi CORS hợp lệ và response không có lỗi khác, script có thể đọc JSON.

**Điều cần chứng minh:** SOP/CORS thường giới hạn quyền JavaScript **đọc response**, không phải cam kết rằng request chưa tới server.

### Bài thử B — `no-cors` và opaque response

Với hai origin cục bộ trên, thực hiện:

~~~js
const result = await fetch("http://localhost:4000/hello", {
  mode: "no-cors"
});

console.log(result.type);   // Thường là "opaque"
console.log(result.status); // Thường là 0 đối với opaque response
~~~

Không thể sử dụng `result.json()` để lấy JSON thực trong opaque response. Nếu thao tác đọc body thất bại, đây là giới hạn được thiết kế, **không** phải biện pháp “vượt CORS”.

### Bài thử C — Iframe cross-origin và clickjacking defense

Trên frontend `http://localhost:3000`, nhúng trang thử nghiệm `http://localhost:4000`:

~~~html
<iframe
  id="target"
  src="http://localhost:4000/"
  title="Trang demo"
></iframe>
~~~

Trong Console của trang cha:

~~~js
const target = document.querySelector("#target");

try {
  console.log(target.contentWindow.document.title);
} catch (error) {
  console.log("Không đọc được DOM khác origin:", error.name);
}
~~~

Dự kiến thao tác đọc bị từ chối do khác port.

Tiếp theo thêm header tại **response trang đang được nhúng**:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Tải lại và xem Console/Network. Trình duyệt hỗ trợ sẽ từ chối nhúng iframe.

**Điều cần chứng minh:** Chặn đọc DOM theo SOP và chặn **nhúng trang** theo `frame-ancestors` là hai loại phòng vệ khác nhau.

### Bài thử D — Script bên ngoài có quyền của trang nhúng

Tạo một script thử nghiệm vô hại do bạn kiểm soát và đưa vào trang thử:

~~~html
<script src="http://localhost:4000/demo.js"></script>
~~~

Script `demo.js`:

~~~js
console.log("Script từ máy chủ cổng 4000");
console.log("Origin môi trường thực thi:", location.origin);
document.body.dataset.demoScriptExecuted = "true";
~~~

Nếu trang ở cổng 3000 cho phép tải script theo CSP/chính sách hiện hành, log `location.origin` sẽ cho thấy **origin của trang nhúng** là `http://localhost:3000`. DOM ở cổng 3000 cũng bị thay đổi.

**Điều cần chứng minh:** Nguồn tải script khác origin không tự tạo một vùng chạy cách ly cho script truyền thống.

### Bài thử E — Bảo vệ thông điệp

Tạo hai trang thử nghiệm có iframe và thực hiện một luồng `postMessage`. Ở phía nhận, bắt đầu bằng:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "http://localhost:4000") return;
  if (event.data?.type !== "demo-ready") return;

  console.log("Thông điệp hợp lệ từ iframe demo");
});
~~~

Sau đó:

1. Gửi một message từ đúng origin, đúng cấu trúc.
2. Gửi message không có `type` phù hợp để kiểm tra nó bị bỏ qua.
3. Kiểm tra thêm `event.source` đối với tham chiếu iframe dự kiến.
4. Không dùng message để thực hiện thay đổi dữ liệu nhạy cảm khi chưa xác minh ở backend.

**Điều cần chứng minh:** Kênh giao tiếp cross-origin là ngoại lệ có chủ đích; việc tin hay bỏ qua một thông điệp là trách nhiệm của bên nhận.

### Ghi nhận kết quả

Với mỗi bài thử, lập bảng:

| Thử nghiệm | Request có xuất hiện trong Network? | JavaScript đọc được dữ liệu? | Có security header liên quan? | Kết luận |
| --- | --- | --- | --- | --- |
| A: `fetch` không CORS | Tự quan sát | Tự quan sát | `Access-Control-Allow-Origin` | Gửi khác với đọc. |
| B: `no-cors` | Tự quan sát | Tự quan sát | CORS mode | Opaque response. |
| C: iframe | Tự quan sát | Tự quan sát DOM | `frame-ancestors` | Nhúng khác với đọc. |
| D: script bên ngoài | Tự quan sát | Kiểm tra DOM trang nhúng | CSP `script-src` | Script không sandbox theo host nguồn. |
| E: `postMessage` | Không phải HTTP request cho mỗi message | Chỉ nhận payload được kiểm tra | Không thay kiểm tra origin/source | Kênh message cần validate. |

## 13. Cách chọn biện pháp khi SOP không đủ

| Mối đe dọa hoặc yêu cầu | SOP hỗ trợ gì? | Lớp cần bổ sung |
| --- | --- | --- |
| Origin ngoài muốn đọc JSON của API | Thường chặn nếu không có CORS hợp lệ | CORS allowlist chính xác, authentication, authorization. |
| Trang ngoài gửi form thay đổi dữ liệu | Không ngăn mọi form POST cross-origin | CSRF token/biện pháp tương đương, kiểm tra nguồn và quyền ở backend, `SameSite`. |
| Trang ngoài nhúng giao diện quản trị | Ngăn đọc DOM cross-origin nhưng không nhất thiết ngăn nhúng | CSP `frame-ancestors`, có thể thêm `X-Frame-Options`. |
| Dữ liệu người dùng biến thành script | Không phân biệt script độc khi đã chạy trong origin | API DOM an toàn, sanitize/encode, CSP, Trusted Types. |
| CDN cung cấp script độc hại | Không cô lập script truyền thống | Kiểm soát dependency, CSP, SRI, origin riêng/iframe cho widget ít tin cậy. |
| Parent/iframe trao đổi message | Cho phép kênh `postMessage` | Kiểm tra origin/source, schema, giới hạn tác động, xác minh server. |
| Rò rỉ thông tin qua tín hiệu gián tiếp | Hạn chế nhiều dạng đọc trực tiếp | Phân tích XS-Leaks, CORP/COOP/COEP, Fetch Metadata, kiểm soát cache và endpoint. |
| Truy cập API bằng client ngoài browser | Không áp dụng SOP như browser | Xác thực, phân quyền, giới hạn truy cập ở server/network. |
| WebSocket được mở từ trang khác | Không áp dụng cơ chế CORS như `fetch` | Kiểm tra `Origin` phù hợp, authentication, authorization theo message/channel. |

### 13.1. Quy trình suy luận nhanh

~~~mermaid
flowchart TD
    A["Có luồng cross-origin?"] --> B{"Hành động chính là gì?"}
    B -->| "Đọc DOM / storage" | C["SOP và chính sách tài liệu"]
    B -->| "Đọc API response" | D["CORS + auth/authorization server"]
    B -->| "Gửi request đổi trạng thái" | E["CSRF + auth/authorization server"]
    B -->| "Nhúng giao diện" | F["frame-ancestors / sandbox"]
    B -->| "Nạp script / xử lý HTML" | G["CSP / SRI / encoding / Trusted Types"]
    B -->| "Gửi message" | H["postMessage origin + source + schema"]
    C --> I["Kiểm thử hành vi thực tế"]
    D --> I
    E --> I
    F --> I
    G --> I
    H --> I
~~~

## 14. Những ngộ nhận thường gặp

1. **“SOP ngăn website A gửi request tới website B.”** Sai theo cách diễn đạt tuyệt đối: nhiều request được gửi, nhất là điều hướng, biểu mẫu và tài nguyên nhúng.
2. **“Bị CORS error nghĩa là request chưa đến backend.”** Không nhất thiết; phải xem Network và log server.
3. **“Bật CORS cho frontend là đã bảo vệ API.”** Không; API vẫn cần xác thực và phân quyền.
4. **“Không đọc được iframe nên không thể clickjacking.”** Sai; clickjacking không cần đọc DOM của iframe.
5. **“Mã từ CDN khác origin nên không có quyền của trang.”** Sai với script truyền thống nhúng vào document.
6. **“XSS bị SOP chặn vì script độc đến từ nguồn khác.”** Sai; nếu script đã thực thi trong origin ứng dụng thì ranh giới đã bị xâm phạm.
7. **“`mode: no-cors` giúp đọc API đang bị CORS chặn.”** Sai; response thường opaque.
8. **“`SameSite` và `Same-Origin` là cùng một phép so.”** Sai; same-site xét một ranh giới khác, ảnh hưởng cách cookie được gửi.
9. **“`postMessage` tự bảo đảm thông điệp đáng tin.”** Sai; phía nhận cần xác minh origin, source và payload.
10. **“SOP chặn mọi rò rỉ thông tin giữa hai trang.”** Không tuyệt đối; XS-Leaks lợi dụng các tín hiệu gián tiếp trong những điều kiện nhất định.
11. **“CORS đủ bảo vệ WebSocket.”** Sai; WebSocket có handshake và mô hình kiểm soát riêng.
12. **“Chỉ cần security headers là khỏi kiểm tra quyền trên server.”** Sai; header chủ yếu là lớp kiểm soát hành vi trình duyệt.

## 15. Checklist khi review một ứng dụng web

- [ ] Liệt kê frontend, API, iframe, nguồn script, websocket, popup và origin của từng thành phần.
- [ ] Phân biệt hành động **gửi request**, **đọc response**, **đọc DOM**, **nhúng trang**, **thực thi script**, **nhận message** và **thay đổi trạng thái backend**.
- [ ] Với API, kiểm tra authentication/authorization độc lập với CORS.
- [ ] Với request dùng cookie và làm thay đổi dữ liệu, kiểm tra CSRF, `Origin`/`Referer` hoặc Fetch Metadata theo thiết kế, và `SameSite`.
- [ ] Với nội dung không tin cậy, kiểm tra DOM sinks, encoding/sanitization, CSP và Trusted Types nếu có hỗ trợ.
- [ ] Với tài nguyên bên thứ ba, đánh giá script có quyền gì; áp dụng CSP, SRI hoặc cách ly iframe khi phù hợp.
- [ ] Với iframe, phân biệt `frame-src`, `frame-ancestors`, `sandbox` và quyền DOM của từng origin.
- [ ] Với `postMessage`, kiểm tra `event.origin`, `event.source` và cấu trúc dữ liệu; hạn chế dữ liệu nhạy cảm trong thông điệp.
- [ ] Với kênh WebSocket, kiểm tra `Origin` và quyền ở server; không giả định CORS bảo vệ handshake.
- [ ] Với endpoint nhạy cảm, cân nhắc XS-Leaks, CORP/COOP/COEP, cache và cơ chế hạn chế request ngoài ngữ cảnh.
- [ ] Dùng DevTools và log máy chủ để xác minh kết luận; không suy từ một lỗi Console đơn lẻ.

**Kết luận học thuật:** SOP là một **ranh giới quan trọng nhưng có phạm vi cụ thể**, chủ yếu hạn chế các quyền truy cập và đọc giữa những origin khác nhau. Nó không ngăn mọi request cross-origin, không tự cấm nhúng, không cô lập script truyền thống từ CDN, không kiểm tra quyền nghiệp vụ và không giải quyết toàn bộ rò rỉ gián tiếp. Thiết kế browser security đúng đắn là đặt từng mối đe dọa vào **đúng ranh giới và đúng cơ chế bảo vệ**: SOP/CORS cho quyền đọc, CSRF và backend authorization cho thay đổi dữ liệu, CSP/Trusted Types cho dữ liệu trở thành script, `frame-ancestors` cho clickjacking, `postMessage` có kiểm tra cho giao tiếp cross-origin, và các chính sách cách ly bổ sung khi threat model yêu cầu.
