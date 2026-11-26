# Giả mạo yêu cầu liên trang (CSRF) và điều kiện xảy ra

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích **Cross-Site Request Forgery (CSRF)** là gì, vì sao trình duyệt có thể vô tình thực hiện thao tác thay cho người dùng.
- Nhận diện các **điều kiện cần** để một yêu cầu giả mạo có thể dẫn đến thay đổi trạng thái.
- Phân biệt CSRF với XSS, CORS và hiểu chính xác vai trò của cookie, `SameSite`, Same-Origin Policy.
- Đánh giá nguy cơ CSRF đối với ứng dụng Spring Security dùng session/cookie và API dùng token trong header, ở cả Servlet và Reactive.
- Nhận biết dấu hiệu của cơ chế chống CSRF khi phân tích một yêu cầu HTTP hoặc kiểm thử ứng dụng.

## 1. CSRF là gì?

**CSRF (Cross-Site Request Forgery)**, hay **giả mạo yêu cầu liên trang**, là kiểu tấn công trong đó kẻ tấn công khiến trình duyệt của nạn nhân gửi một yêu cầu đến ứng dụng đích và ứng dụng đích xử lý yêu cầu đó với quyền/ngữ cảnh xác thực của nạn nhân, dù nạn nhân không chủ ý thực hiện thao tác tương ứng.

Ví dụ: người dùng đang đăng nhập vào ứng dụng ngân hàng. Khi họ mở một trang do kẻ tấn công kiểm soát, trang đó kích hoạt yêu cầu chuyển tiền đến ngân hàng. Nếu trình duyệt đính kèm cookie phiên và ngân hàng chỉ kiểm tra phiên đăng nhập mà không xác minh nguồn gốc/ý định của yêu cầu, thao tác có thể được thực hiện như thể người dùng tự gửi.

Điểm then chốt là **kẻ tấn công không nhất thiết phải đánh cắp mật khẩu, cookie hay đọc được phản hồi**. Họ tận dụng việc **trình duyệt tự gửi thông tin xác thực** cho máy chủ đích trong những điều kiện nhất định.

> **Nguyên tắc cốt lõi:** Xác thực người dùng trả lời câu hỏi *“Yêu cầu này gắn với tài khoản nào?”*. Chống CSRF giải quyết thêm câu hỏi *“Yêu cầu thay đổi trạng thái này có xuất phát từ một tương tác được ứng dụng đích chấp thuận hay không?”*.

## 2. Cách một cuộc tấn công CSRF diễn ra

Giả sử ứng dụng đích có endpoint:

~~~http
POST https://bank.example/transfer
Content-Type: application/x-www-form-urlencoded

to=recipient-123&amount=1000000
~~~

Người dùng đã đăng nhập và trình duyệt có cookie phiên hợp lệ cho `bank.example`. Kẻ tấn công đặt đoạn HTML sau trên trang `https://gift.attacker.test`:

~~~html
<!doctype html>
<html lang="vi">
  <body>
    <form id="attack" method="post" action="https://bank.example/transfer">
      <input type="hidden" name="to" value="attacker-account">
      <input type="hidden" name="amount" value="1000000">
    </form>
    <script>
      document.getElementById("attack").submit();
    </script>
  </body>
</html>
~~~

Khi nạn nhân mở trang độc hại, trình duyệt có thể tạo yêu cầu HTTP tương tự:

~~~http
POST /transfer HTTP/1.1
Host: bank.example
Origin: https://gift.attacker.test
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=<giá-trị-phiên-hợp-lệ>

to=attacker-account&amount=1000000
~~~

Đoạn `Cookie` ở trên **chỉ xuất hiện nếu chính sách cookie và trình duyệt cho phép gửi cookie trong ngữ cảnh yêu cầu đó**; ví dụ cookie được cấu hình `SameSite=None; Secure` và không bị chính sách chặn cookie của trình duyệt loại bỏ. Đây là điều kiện quan trọng, không phải mọi form gửi từ một website khác đều mang theo session cookie.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant T as Trang tấn công
    participant S as Ứng dụng đích

    U->>S: Đăng nhập hợp lệ
    S-->>B: Thiết lập cookie phiên
    U->>B: Mở trang tấn công
    B->>T: Tải HTML
    T-->>B: Form gửi đến ứng dụng đích
    B->>S: POST thay đổi trạng thái + cookie (nếu được gửi)
    Note over S: Nếu chỉ tin phiên và thiếu kiểm tra CSRF
    S-->>B: Thực hiện thao tác dưới danh tính nạn nhân
~~~

Sơ đồ cho thấy **trang độc hại chỉ cần kích hoạt yêu cầu**. Same-Origin Policy thường ngăn mã JavaScript của trang tấn công đọc dữ liệu nhạy cảm trong *phản hồi* từ miền khác, nhưng bản thân chính sách đó **không ngăn mọi yêu cầu liên trang được gửi đi**. Các form HTML có thể tạo ra một số loại yêu cầu liên trang từ lâu, kể cả khi không có quyền CORS.

## 3. Những điều kiện để CSRF xảy ra

Một kịch bản CSRF điển hình thành công khi các điều kiện dưới đây đồng thời thỏa mãn.

| Điều kiện | Diễn giải | Cách nhận diện |
|---|---|---|
| **1. Có thao tác nhạy cảm hoặc làm thay đổi trạng thái** | Endpoint cho phép chuyển tiền, đổi email, đặt hàng, thêm quyền, xóa dữ liệu, thay cấu hình… | Kiểm tra endpoint thực sự làm gì, kể cả nếu nó dùng `GET`. |
| **2. Trình duyệt có thể tự đính kèm thông tin xác thực** | Cookie phiên, cookie xác thực, HTTP Basic đã được trình duyệt lưu, hoặc một cơ chế xác thực tự động khác được gửi khi yêu cầu đến đích. | Xem `Cookie`/cơ chế xác thực và các chính sách `SameSite`, `Secure`, chặn cookie. |
| **3. Kẻ tấn công có thể khiến trình duyệt gửi yêu cầu phù hợp** | Dùng form, liên kết, điều hướng hoặc những cách gửi yêu cầu được trình duyệt cho phép. | Endpoint có nhận kiểu request mà một trang ngoài có thể tạo không? |
| **4. Máy chủ không kiểm tra hiệu quả tính hợp lệ của yêu cầu** | Chỉ dựa vào cookie/session, thiếu hoặc bỏ qua CSRF token hay biện pháp xác minh tương đương. | Thử gửi yêu cầu thay đổi trạng thái khi **thiếu/sai CSRF token**. |
| **5. Những hạn chế của trình duyệt không chặn được đường tấn công cụ thể** | Ví dụ: cookie vẫn được gửi trong ngữ cảnh đó; yêu cầu không bị một cơ chế bảo vệ khác từ chối. | Kiểm tra trực tiếp bằng trình duyệt và cấu hình cookie thực tế. |

Các điều kiện này giải thích vì sao **“có cookie” chưa đủ để kết luận có lỗ hổng CSRF**, và **“có CORS” cũng chưa đủ để kết luận an toàn**. Phải xem toàn bộ cách yêu cầu được tạo, thông tin xác thực được gửi và cách máy chủ quyết định có chấp nhận thao tác hay không.

### 3.1. Vì sao cookie thường là mắt xích quan trọng?

Trong ứng dụng web dùng session, máy chủ cấp cookie như `JSESSIONID` hoặc cookie phiên tùy cấu hình. Trình duyệt quản lý cookie và có thể tự đính kèm nó vào yêu cầu đến máy chủ phù hợp. Vì vậy, **quyền xác thực gắn với phiên có thể đi theo một yêu cầu mà người dùng không chủ động tạo ra trên trang ứng dụng đích**.

Cookie có thuộc tính `HttpOnly` sẽ không thể bị JavaScript thông thường đọc qua `document.cookie`; điều này hữu ích chống đánh cắp cookie qua một số kịch bản XSS, **nhưng không tự ngăn CSRF**, vì trình duyệt vẫn có thể gửi cookie ấy. Thuộc tính `Secure` yêu cầu gửi cookie qua HTTPS; nó cũng **không thay thế CSRF token**.

Đối với HTTP Basic hoặc cơ chế chứng chỉ khách mà trình duyệt tự sử dụng, tư duy đánh giá tương tự: nếu trình duyệt tự gắn thông tin xác thực vào yêu cầu liên trang thì phải xem xét nguy cơ CSRF.

### 3.2. Khi nào trang ngoài có thể tạo request?

Form HTML có thể gửi `POST` với những kiểu mã hóa chuẩn như `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`. Một yêu cầu form đơn giản thường **không cần CORS preflight** để được gửi đi. JavaScript ở trang ngoài không cần đọc được phản hồi để gây tác động.

Ngược lại, khi endpoint đòi hỏi một header tùy chỉnh và chỉ chấp nhận định dạng yêu cầu làm phát sinh preflight, trình duyệt sẽ có thêm rào cản đối với mã JavaScript chạy ở origin khác. Tuy nhiên, **chỉ dựa vào CORS hay việc “API dùng JSON” không phải cách thay thế toàn diện cho kiểm tra CSRF**, nhất là nếu còn đường xử lý khác chấp nhận simple request hoặc CORS bị cấu hình sai.

### 3.3. Có bắt buộc nạn nhân phải đăng nhập sẵn không?

**Không phải trong mọi biến thể.** Kịch bản phổ biến là nạn nhân có phiên đã đăng nhập. Tuy nhiên, **login CSRF** có thể khiến trình duyệt nạn nhân đăng nhập vào *tài khoản do kẻ tấn công kiểm soát*. Nạn nhân sau đó nhập dữ liệu vào tài khoản ấy mà không nhận ra. Một số luồng liên kết tài khoản hoặc hành động trước đăng nhập cũng cần xem xét CSRF theo mô hình đe dọa riêng.

## 4. Phân biệt cross-site, cross-origin, CORS và SameSite

### 4.1. “Origin” và “site” là hai khái niệm khác nhau

- **Origin** gồm bộ ba *scheme + hostname + port*. Ví dụ `https://shop.example.com` và `https://admin.example.com` khác origin.
- **Site** theo cách hiểu hiện đại (schemeful same-site) dựa chủ yếu vào *scheme* và **registrable domain**. Hai subdomain cùng registrable domain, cùng scheme thường được coi là same-site, dù khác origin.
- **CORS** là cơ chế trình duyệt quản lý quyền đọc phản hồi cross-origin của JavaScript và preflight đối với những yêu cầu nhất định; nó không phải cơ chế CSRF token.
- **`SameSite`** là thuộc tính cookie ảnh hưởng đến việc cookie có được gửi trong ngữ cảnh cross-site hay không.

Điều này đặc biệt quan trọng khi các ứng dụng nằm trên nhiều subdomain: một yêu cầu có thể **cross-origin nhưng same-site**. Cookie `SameSite=Strict`/`Lax` không đảm bảo ngăn mọi hành động giữa các subdomain trong cùng site.

### 4.2. Tác động của từng chế độ SameSite

| Thuộc tính cookie | Ảnh hưởng thường gặp khi yêu cầu cross-site |
|---|---|
| `SameSite=Strict` | Không gửi cookie trong ngữ cảnh cross-site; có khả năng chặn nhiều đường CSRF phụ thuộc cookie. |
| `SameSite=Lax` | Thường không gửi cookie cho **cross-site form POST**, nhưng có thể gửi khi **điều hướng cấp cao (top-level navigation) bằng phương thức an toàn như GET**. |
| `SameSite=None; Secure` | Cho phép cookie trong những ngữ cảnh cross-site theo chính sách cookie, nhưng trình duyệt vẫn có thể áp dụng hạn chế riêng đối với cookie bên thứ ba. |

Nhiều trình duyệt hiện đại áp dụng hành vi gần với `Lax` khi cookie không khai báo `SameSite`, song **không được giả định mọi trình duyệt/phiên bản có hành vi giống nhau**; có thể có ngoại lệ tương thích đối với cookie mới thiết lập. Cần xem giá trị `Set-Cookie` và thử trong đúng trình duyệt dự kiến.

**Một bẫy phổ biến:** nếu `GET /account/delete?id=123` thực sự xóa tài khoản, liên kết từ trang tấn công có thể kích hoạt điều hướng top-level và cookie `SameSite=Lax` vẫn được gửi. Vì vậy, thao tác làm thay đổi trạng thái không được thiết kế dưới các phương thức an toàn (`GET`, `HEAD`, `OPTIONS`, `TRACE`).

### 4.3. Vì sao CORS không giải quyết CSRF?

Hãy tách riêng hai câu hỏi:

1. **Có gửi được yêu cầu không?** Một số yêu cầu cross-site, đặc biệt qua form HTML, vẫn được trình duyệt gửi.
2. **Mã JavaScript ở trang ngoài có đọc được phản hồi không?** Same-Origin Policy/CORS chủ yếu kiểm soát điểm này và các trường hợp cần preflight.

Nếu yêu cầu gửi thành công và máy chủ đã thực hiện đổi email, dù trình duyệt không cho trang tấn công đọc phản hồi, **hậu quả CSRF vẫn có thể xảy ra**. Mặt khác, cấu hình CORS nghiêm ngặt vẫn có ích để hạn chế đọc dữ liệu và một số request script; đó là lớp bảo vệ bổ sung, không phải lý do để bỏ qua kiểm tra CSRF khi có cookie tự động gửi.

## 5. Nhận diện nguy cơ trong ứng dụng Spring Security

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, CSRF là một lớp phòng vệ HTTP/trình duyệt, đứng cạnh các chủ đề khác như CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Hiểu điều kiện xảy ra CSRF giúp chọn và kiểm thử biện pháp thích hợp khi xây dựng ứng dụng **Servlet** hoặc **Reactive**.

### 5.1. Ứng dụng session và API dùng bearer token

| Kiểu ứng dụng | Đánh giá CSRF | Lý do |
|---|---|---|
| Web MVC/Servlet có form đăng nhập, cookie phiên, endpoint POST thay đổi dữ liệu | **Cần bảo vệ CSRF** | Trình duyệt có thể tự gửi cookie phiên nếu điều kiện cookie cho phép. |
| WebFlux/Reactive dùng phiên/cookie trong trình duyệt | **Cần bảo vệ CSRF** | Mô hình đe dọa giống Servlet dù pipeline và API cấu hình khác nhau. |
| SPA gọi API bằng cookie phiên với `credentials: "include"` | **Cần bảo vệ CSRF** | Cookie vẫn là thông tin xác thực do trình duyệt quản lý; phải xét cả SameSite. |
| API chỉ nhận bearer token trong header `Authorization` mà mã ứng dụng tự thêm vào từng request | **Thông thường ít chịu CSRF truyền thống** | Trang ngoài không khiến trình duyệt tự gắn token vào request chỉ bằng form hoặc link. |
| API “stateless” nhưng vẫn xác thực bằng cookie tự động gửi | **Vẫn phải đánh giá CSRF** | Không lưu session phía máy chủ không có nghĩa là trình duyệt thôi tự gửi cookie. |

**Lưu ý:** Thẻ `Authorization: Bearer ...` trong bảng chỉ có ý nghĩa khi token **không** được trình duyệt tự thêm vào yêu cầu từ trang khác. Chỉ gọi API là “REST”, “JWT” hoặc “stateless” không đủ để kết luận vô hiệu hóa CSRF là an toàn.

### 5.2. Mặc định của Spring Security

Trong cấu hình web điển hình, Spring Security có cơ chế chống CSRF **được bật mặc định** cho cả hai stack:

- **Servlet:** chuỗi lọc bảo mật dùng `CsrfFilter`; cấu hình liên quan nằm trong `HttpSecurity`.
- **Reactive/WebFlux:** chuỗi lọc bảo mật dùng `CsrfWebFilter`; cấu hình liên quan nằm trong `ServerHttpSecurity`.

Mặc định, những phương thức được coi là chỉ đọc (`GET`, `HEAD`, `TRACE`, `OPTIONS`) không bị yêu cầu CSRF token; các phương thức còn lại, như `POST`, `PUT`, `PATCH` và `DELETE`, thường phải vượt qua kiểm tra token. Điều này dựa trên giả định quan trọng rằng **endpoint chỉ đọc không làm thay đổi trạng thái**.

Ví dụ, một request POST đã xác thực hợp lệ nhưng **thiếu hoặc có CSRF token sai** có thể bị từ chối với HTTP `403 Forbidden` trước khi đến logic nghiệp vụ. Ngược lại, việc request có CSRF token hợp lệ **không tự cấp quyền truy cập**; ứng dụng vẫn phải thực hiện xác thực và phân quyền.

Cấu hình cụ thể có thể tùy chỉnh vùng áp dụng CSRF, nơi lưu token và cách nhận token. Không nên quyết định tắt kiểm tra CSRF trên toàn ứng dụng trước khi xác định rõ **cơ chế trình duyệt gửi credential** ở từng luồng.

### 5.3. Ví dụ phân tích một endpoint

Xét `POST /profile/email` đổi email tài khoản. Đặt lần lượt những câu hỏi sau:

1. Người dùng xác thực bằng **cookie phiên** hay **bearer token trong header do client tự bổ sung**?
2. Trang nằm ở origin/site khác có thể tạo request đến endpoint bằng **form HTML** không? Endpoint có tiếp nhận request như vậy không?
3. Với cùng request đó, **cookie có thực sự được trình duyệt gửi** theo `SameSite` và chính sách cookie hiện hành không?
4. Server có từ chối khi **thiếu/sai token chống CSRF**, hoặc có biện pháp xác minh tính hợp lệ tương đương không?
5. Nếu gọi endpoint với `GET` hoặc đi qua đường xử lý dự phòng, liệu có cách nào **thay đổi dữ liệu** mà bỏ qua bảo vệ không?

Chỉ khi xác minh đầy đủ chuỗi hành vi mới kết luận được một đường khai thác CSRF khả thi.

## 6. Những lớp phòng vệ liên quan và giới hạn của chúng

Ở bài này, mục tiêu là nhận diện nguyên nhân và điều kiện tấn công. Những cơ chế sau là nền tảng để học phần cấu hình/kiểm thử chi tiết:

| Cơ chế | Chức năng chính | Điều cần nhớ |
|---|---|---|
| **CSRF token** gắn với session hoặc cơ chế kiểm chứng tương đương | Buộc request thay đổi trạng thái mang một giá trị kẻ tấn công ngoài origin khó biết/giả mạo. | Cần sinh, lưu, gắn vào form/header và kiểm tra đúng; **không** được chấp nhận token tùy ý. |
| **SameSite cookie** | Hạn chế gửi cookie ở những tình huống cross-site. | Có sự khác biệt giữa `Lax`, `Strict`, `None`; là lớp bổ sung, không nên là biện pháp duy nhất. |
| **Kiểm tra `Origin`/`Referer`** | Đối chiếu nguồn phát sinh yêu cầu. | Phải xử lý đúng các trường hợp header thiếu/hợp lệ, proxy và origin được phép. |
| **Fetch Metadata** (`Sec-Fetch-Site`, …) | Cung cấp ngữ cảnh nguồn gốc request để server xây chính sách chặn. | Có giới hạn hỗ trợ và ngoại lệ; dùng bổ trợ cho kiểm tra cốt lõi. |
| **Thiết kế đúng phương thức HTTP** | Không làm thay đổi trạng thái qua phương thức được coi là an toàn. | Đặc biệt cần thiết vì mặc định bảo vệ CSRF thường không áp dụng cho `GET`. |
| **Chống XSS và bảo vệ phiên** | Ngăn mã độc chạy trong origin đáng tin cậy hoặc chiếm đoạt phiên. | XSS có thể làm suy yếu/bỏ qua CSRF token; các lớp bảo vệ phải đi cùng nhau. |

CSRF token thường được ứng dụng chèn vào form bằng hidden field hoặc để client hợp lệ gửi qua header. Một attacker kiểm soát website khác có thể tạo form gửi đến đích, nhưng thông thường **không đọc được token được cung cấp chỉ trong trang hợp lệ**. Đây là khác biệt nền tảng giữa request có **cookie tự động** và request có **token mà ứng dụng chủ động phát hành/kiểm tra**.

## 7. Kiểm thử và chẩn đoán tình huống CSRF

Trong môi trường kiểm thử được phép, có thể thực hiện ba biến thể của **cùng một thao tác thay đổi dữ liệu**:

| Biến thể | Kết quả kỳ vọng khi bật chống CSRF đúng cách |
|---|---|
| Có xác thực, **thiếu CSRF token** | Bị từ chối (thường `403`) với phương thức yêu cầu bảo vệ. |
| Có xác thực, **token sai hoặc không khớp phiên** | Bị từ chối (thường `403`). |
| Có xác thực, **token hợp lệ** | Vượt qua bước kiểm tra CSRF; vẫn có thể bị từ chối vì phân quyền, validation hoặc quy tắc nghiệp vụ khác. |

Khi dùng Spring Security Test, có thể viết test cho Servlet bằng `MockMvc` và post request kèm/không kèm `csrf()`; trên Reactive dùng `WebTestClient` và các hỗ trợ kiểm thử bảo mật phù hợp. Điều quan trọng là **đảm bảo request đi qua security filter chain thực tế**, thay vì chỉ gọi trực tiếp controller.

Để đánh giá khả năng **khai thác từ một website khác**, ngoài việc thử request thiếu token, phải kiểm tra trong trình duyệt: request có được gửi đi hay không, cookie nào đi kèm và `SameSite` hoạt động thế nào. Công cụ HTTP client gửi cookie thủ công có thể chứng minh server thiếu kiểm tra CSRF, nhưng **không chứng minh được một trình duyệt hiện đại sẽ tự gửi chính cookie đó trong kịch bản cross-site**.

Khi gặp HTTP `403`:

- Kiểm tra request có thuộc phương thức bắt buộc CSRF token và token đã được gửi đúng nơi, đúng phiên chưa.
- Phân biệt từ chối do **CSRF**, do **chưa xác thực**, do **thiếu quyền**, hoặc do cơ chế bảo vệ khác. Mã `403` một mình chưa đủ chẩn đoán.
- Trong Servlet, có thể lần theo các ngoại lệ như `MissingCsrfTokenException` hoặc `InvalidCsrfTokenException` và cấu hình bảo mật liên quan; không nên suy luận từ giao diện lỗi đơn thuần.

## 8. Những hiểu lầm thường gặp

**“Tôi đã bật CORS nên không còn CSRF.”** Không chính xác. CORS không bảo đảm chặn form submission cross-site và không thay thế xác minh yêu cầu thay đổi trạng thái.

**“Cookie có HttpOnly/Secure nên không thể bị CSRF.”** Không chính xác. Hai thuộc tính này có vai trò riêng, trong khi trình duyệt vẫn có thể tự đính kèm cookie khi điều kiện gửi được thỏa mãn.

**“SameSite=Lax luôn chặn CSRF.”** Không chính xác. Các điều hướng top-level bằng phương thức an toàn có thể mang cookie. Một endpoint dùng GET để đổi dữ liệu vẫn nguy hiểm; cần xét các ngoại lệ, tương thích và yêu cầu same-site khác origin.

**“Ứng dụng dùng JWT/SPA nên không cần CSRF.”** Phụ thuộc **token được gửi bằng cách nào**. Token do JavaScript chủ động gắn trong `Authorization` khác với token được cất trong cookie tự động gửi.

**“Có session hợp lệ nghĩa là người dùng đã bấm nút.”** Không chính xác. Cookie xác định phiên; nó không chứng minh người dùng chủ động khởi tạo request tại trang đích.

**“Chỉ cần chống XSS hoặc chỉ cần CSRF token.”** Mỗi cơ chế xử lý một hướng tấn công khác nhau. XSS xảy ra ngay trong origin tin cậy có thể giúp attacker lấy hoặc sử dụng CSRF token; do đó các lớp phòng vệ cần bổ sung cho nhau.

## 9. Tự kiểm tra

**Tình huống A.** Một web app dùng session cookie, `POST /settings` nhận form đơn giản, không kiểm tra CSRF token. Cookie được gửi trong một cross-site POST theo chính sách trình duyệt hiện tại. Trang ngoài có thể tự submit form. **Kết luận:** có đủ những điều kiện trọng yếu cho CSRF, nếu endpoint làm thay đổi trạng thái với quyền của phiên.

**Tình huống B.** API chỉ nhận `Authorization: Bearer <token>` do JavaScript của ứng dụng cùng origin tự thêm; trình duyệt không tự gắn token ấy từ website ngoài. **Kết luận:** kiểu CSRF dựa vào credential tự động gửi thường không khả thi. Vẫn cần chống XSS, lộ token, cấu hình CORS sai và các rủi ro khác.

**Tình huống C.** Một endpoint `GET /unsubscribe` làm thay đổi dữ liệu, cookie `SameSite=Lax` được gửi khi người dùng điều hướng đến liên kết từ site khác. **Kết luận:** vẫn có đường CSRF. Chuyển thao tác sang phương thức thay đổi trạng thái thích hợp và áp dụng kiểm tra chống CSRF.

## Tổng kết

CSRF xuất hiện khi kẻ tấn công **kích hoạt được yêu cầu**, trình duyệt **gửi kèm thông tin xác thực trong ngữ cảnh đó**, ứng dụng **thực hiện hành động nhạy cảm**, và **không có kiểm tra đủ mạnh để từ chối yêu cầu giả mạo**. Trong Spring Security, việc bật cơ chế CSRF mặc định ở cả Servlet lẫn Reactive tạo ra lớp phòng vệ quan trọng cho ứng dụng dựa trên cookie/session. Để triển khai đúng, cần hiểu rõ thiết kế endpoint, mô hình xác thực, chính sách cookie và những khác biệt giữa **cross-site**, **cross-origin** và **CORS**.
