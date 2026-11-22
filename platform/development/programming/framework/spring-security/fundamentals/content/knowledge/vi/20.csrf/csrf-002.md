# Điều kiện tấn công CSRF khi trình duyệt tự gửi cookie hoặc thông tin xác thực

Một người đã đăng nhập vào `https://bank.example.test`. Trình duyệt đang giữ cookie phiên hợp lệ, chẳng hạn `JSESSIONID`. Trong lúc phiên còn hoạt động, người đó mở một trang khác do kẻ tấn công kiểm soát. Trang này có thể khiến trình duyệt gửi một yêu cầu tới hệ thống ngân hàng. **Nếu trình duyệt tự đính kèm thông tin xác thực, endpoint nhận yêu cầu có tác dụng thay đổi dữ liệu, và server không kiểm tra được rằng hành động thật sự được khởi tạo từ giao diện tin cậy**, một cuộc tấn công **Cross-Site Request Forgery (CSRF)** có thể xảy ra.

CSRF không bắt đầu từ việc kẻ tấn công biết mật khẩu hoặc đọc được cookie. Điểm cốt lõi là trình duyệt **có thể gửi credential đang có thay cho người dùng** khi liên hệ với đúng server nhận credential, trong khi request được tạo từ một ngữ cảnh không đáng tin. Do đó, việc API “đã đăng nhập” hoặc “đã kiểm tra quyền” **chưa đủ để kết luận request là một hành động chủ động của người dùng**.

Bài này thuộc nhóm **CSRF** của **Spring Security - fundamentals**. Trọng tâm là **điều kiện tấn công khi trình duyệt tự gửi cookie hoặc thông tin xác thực**: loại credential nào có thể tự được đính kèm, cookie `SameSite` ảnh hưởng thế nào, tại sao CORS không phải giải pháp CSRF, Spring Security chặn request ra sao, và cách kiểm thử hành động có/không có CSRF token. Ví dụ chính sử dụng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet**.

## 1. CSRF là gì và đâu là yếu tố nguy hiểm?

**Cross-Site Request Forgery** là tình huống một bên không đáng tin khiến trình duyệt đang có quyền truy cập của nạn nhân gửi yêu cầu ngoài ý muốn tới một website hoặc API. Website đích có thể nhầm yêu cầu đó với hành động được người dùng chủ động thực hiện.

Ví dụ ở mức ý tưởng:

~~~text
(1) Người dùng đăng nhập app.example.test
        |
        | browser lưu cookie phiên của app.example.test
        v
(2) Người dùng mở attacker.example.org
        |
        | trang lạ yêu cầu gửi POST tới app.example.test
        v
(3) Browser quyết định có gửi cookie của app.example.test hay không
        |
        | nếu điều kiện cookie/credentials cho phép
        v
(4) POST /settings/email mang phiên đã đăng nhập
        |
        | server kiểm tra authentication: "đây là tài khoản lan"
        | server kiểm tra CSRF/Origin: có tin request đến từ flow hợp lệ?
        |
        +--> có kiểm tra hợp lệ → request lạ bị chặn
        |
        +--> không kiểm tra → có nguy cơ thay đổi email không mong muốn
~~~

Kẻ tấn công **không cần xem được kết quả phản hồi** để một thao tác như đổi cài đặt, thêm mặt hàng vào giỏ hoặc tạo yêu cầu thanh toán gây tác dụng phụ. Chính sách Same-Origin Policy thường ngăn script của origin lạ **đọc** dữ liệu từ origin đích; nó không mặc nhiên ngăn mọi cách **gửi** request đến origin đích.

Điểm nguy hiểm không phải chỉ là “có cookie” mà là **credential tự được trình duyệt đưa vào request tới đích**, làm server có thể xác nhận danh tính mà không có bằng chứng người dùng đã chủ động chọn hành động đó.

## 2. Những điều kiện cần hội tụ để tấn công thành công

Một kịch bản CSRF kinh điển cần những điều kiện sau phù hợp với nhau:

1. **Có danh tính hoặc quyền đang được duy trì:** nạn nhân còn một session cookie hợp lệ, thông tin HTTP authentication được browser ghi nhớ, hoặc một credential khác có thể tự được dùng cho server đích.
2. **Kẻ tấn công khiến browser tạo request đến endpoint đích:** ví dụ qua HTML form, điều hướng, tài nguyên tải tự động hoặc một cơ chế request mà chính sách browser cho phép.
3. **Browser thực sự đính kèm credential phù hợp:** cookie phải khớp domain/path, HTTPS/Secure, SameSite và các chính sách chặn cookie; HTTP Basic/Negotiate hoặc client certificate phải được browser sử dụng trong hoàn cảnh tương ứng.
4. **Endpoint cho phép hành động có tác dụng phụ:** chẳng hạn `POST /settings/email` thay đổi email, hoặc tệ hơn `GET /account/delete` thực hiện xóa tài khoản.
5. **Server không yêu cầu đủ bằng chứng chống CSRF:** thiếu hoặc kiểm tra sai synchronizer CSRF token, Origin/Referer/Fetch Metadata không phù hợp, hoặc có lỗ hổng trong chính sách.
6. **Quyền hiện tại đủ cho hành động đó:** nếu người dùng không có quyền trên tài nguyên, authorization có thể từ chối; nếu người dùng có quyền, server cần kiểm tra **ý định nguồn gốc request** ngoài quyền đó.

Đây là **điều kiện theo mô hình tấn công**, không phải cứ có cookie và POST là một trang bất kỳ sẽ thực hiện được CSRF. Ví dụ, cookie `SameSite=Lax` được khai báo rõ thường không được gửi trong một form POST cross-site; nếu thiếu cookie xác thực mà endpoint không có cơ chế khác, request có thể thất bại ở authentication.

### Phân biệt điều kiện cần và kết quả

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Có credential đang dùng được cho website đích không? | Có thể không có quyền để thay đổi dữ liệu |
| Browser có thể tạo request đến đích không? | Không có request bị rèn giả |
| Credential có tự được gắn vào request đó không? | Server có thể chỉ thấy anonymous |
| Request có đạt quyền của chức năng không? | Authorization có thể chặn |
| Có thiếu/qua mặt được kiểm tra CSRF không? | Request rèn giả bị từ chối |
| Endpoint có thay đổi trạng thái không? | Có thể không có tác dụng phụ dù đã gửi request |

**Authentication trả lời “request mang danh tính gì?”. CSRF protection trả lời “request thay đổi trạng thái có bằng chứng phù hợp rằng nó đến từ luồng tin cậy không?”.** Hai câu hỏi độc lập và cần cả hai khi kiến trúc dựa vào browser gửi credential tự động.

## 3. Cookie tự động được trình duyệt gửi trong tình huống nào?

Giả sử server cấp cookie sau khi người dùng đăng nhập:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=None
~~~

Ví dụ trên minh họa cookie phiên được dùng tại `https://app.example.test`, với `SameSite=None` cho phép xem xét gửi cookie ở những request cross-site phù hợp. Việc browser có thực sự gửi còn chịu chính sách cookie bên thứ ba, domain/path, thời hạn, điều kiện Secure, trạng thái phiên và các ràng buộc khác.

Khi browser yêu cầu đúng domain/path mà cookie áp dụng, header gửi đến server có thể là:

~~~http
POST /settings/email HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=opaque-session-id
Content-Type: application/x-www-form-urlencoded

email=changed%40example.test
~~~

**Trang lạ không nhất thiết đọc được cookie này.** Browser tự lựa chọn cookie theo URL đích; header Cookie thường không thể bị trang lạ đặt trực tiếp từ JavaScript. Kẻ tấn công chỉ cố **kích hoạt request** trong hoàn cảnh browser tự gắn cookie.

### 3.1. Những thuộc tính cookie cần hiểu

- `Domain`: quyết định những host nào có thể nhận cookie. Không khai báo Domain thường tạo cookie host-only. Khai báo quá rộng như `Domain=example.test` có thể làm tăng phạm vi ảnh hưởng qua subdomain.
- `Path`: giới hạn request path mà cookie có thể được gửi tới; **không phải ranh giới bảo mật mạnh giữa những endpoint trên cùng origin**.
- `Secure`: thông thường chỉ gửi cookie qua HTTPS; **không** ngăn CSRF khi request đích dùng HTTPS.
- `HttpOnly`: ngăn JavaScript phía client trực tiếp đọc cookie bằng các API như `document.cookie`; **không** ngăn browser tự gửi cookie qua HTTP request.
- `SameSite`: hướng dẫn browser hạn chế gửi cookie ở những tình huống cross-site.
- `Max-Age`/`Expires`: liên quan thời hạn cookie; cookie còn trong browser không chứng minh session phía server chưa hết hạn.

Không nhầm **cookie HttpOnly** với **CSRF protection**: HttpOnly giảm nguy cơ JavaScript đánh cắp cookie, trong khi CSRF dựa trên việc browser **tự gửi cookie** cho server đích.

### 3.2. Bảng SameSite và rủi ro

| Cookie của server đích | Cross-site form POST | Cross-site top-level GET navigation | Ý nghĩa |
| --- | --- | --- | --- |
| `SameSite=Strict` | Thông thường không gửi | Thông thường không gửi | Giảm mạnh việc gửi cookie từ site khác |
| `SameSite=Lax` khai báo rõ | Thông thường không gửi | Có thể gửi khi điều hướng cấp cao dùng method an toàn | GET phải thật sự không thay đổi trạng thái |
| `SameSite=None; Secure` | Có thể gửi nếu chính sách browser cho phép | Có thể gửi | Cross-site cookie có thể hoạt động; cần CSRF protection |
| Không khai báo `SameSite` | Phụ thuộc browser/default hiện hành | Phụ thuộc browser | Không nên suy ra một chính sách nhất quán |

**Ngoại lệ quan trọng:** một số browser áp dụng *Lax-by-default* cho cookie không khai báo SameSite, có thể có khoảng nới lỏng ngắn cho POST sau khi cookie vừa được tạo. Vì vậy **đừng dựa vào hành vi mặc định khi bỏ trống SameSite**. Khai báo có chủ đích và kiểm thử trên browser được hỗ trợ.

`SameSite=None` trong các browser hiện đại thường yêu cầu `Secure`, nhưng điều đó không có nghĩa mọi browser sẽ luôn cho phép cookie bên thứ ba: nhiều browser còn có cơ chế chặn/partition cookie theo ngữ cảnh.

### 3.3. Same-site không đồng nghĩa same-origin

**Origin** thường gồm **scheme + host + port**. **Site** trong cách hiểu “schemeful same-site” dựa trên scheme và miền đăng ký (*registrable domain*), không phân biệt mọi subdomain theo cách origin phân biệt.

Ví dụ:

~~~text
https://app.example.test
https://forum.example.test

Hai URL:
- khác origin vì host khác
- có thể cùng site vì cùng scheme và registrable domain example.test
~~~

Nếu một subdomain không đáng tin bị chiếm quyền, request từ subdomain đó tới app có thể được coi là **same-site**, dù vẫn **cross-origin**. Cookie host-only của `app.example.test` không bị lộ cho subdomain kia, nhưng browser **vẫn có thể gửi cookie tới host app** khi request đích là app, theo chính sách áp dụng.

Điều này giải thích vì sao **SameSite không thay thế hoàn toàn CSRF token và việc bảo vệ các subdomain**. Đừng dùng `SameSite=Strict` rồi kết luận mọi đường tấn công từ một origin khác đều đã bị vô hiệu hóa.

## 4. Trình duyệt còn có thể tự gửi thông tin xác thực nào?

Ngoài cookie phiên, browser có thể xử lý một số kiểu credential theo cách liên quan đến CSRF:

| Cơ chế | Browser có thể tự dùng khi request tới server đích? | Điều kiện/nhận xét |
| --- | --- | --- |
| Session cookie `JSESSIONID` | Có, tùy cookie và chính sách browser | Kịch bản CSRF phổ biến |
| Cookie chứa JWT access token | Có, nếu được lưu như cookie và cookie đủ điều kiện | Token ở trong cookie **vẫn là credential tự đính kèm** |
| HTTP Basic đã được browser ghi nhớ | Có thể, tùy authentication protection space/browser | Không nên mặc định miễn CSRF chỉ vì không dùng cookie |
| HTTP Negotiate/Kerberos/NTLM | Có thể tự thương lượng theo cấu hình browser/doanh nghiệp | Cần đánh giá môi trường intranet |
| TLS client certificate (mTLS) | Có thể được browser sử dụng theo cấu hình/certificate selection | Có nguy cơ request không mong muốn nếu endpoint dựa vào credential này |
| Bearer token mà JavaScript hợp lệ tự đặt trong Authorization header | Không tự gắn cho trang lạ chỉ vì browser đang có token trong bộ nhớ | Khác cookie; vẫn cần bảo vệ XSS và nơi lưu token |
| Mật khẩu lưu trong password manager | Không phải browser tự gửi mật khẩu trên mọi request tới domain | Chỉ khi cơ chế login/form thật sự sử dụng |
| API key cố định do một client đặc thù tự đính trong header | Không phải browser mặc định tự gắn cho mọi cross-site form | Đánh giá cách client/server truyền credential |

Điểm phân loại quan trọng nhất không phải tên “cookie”, “token” hay “password”, mà là câu hỏi:

> **Một tài liệu ở origin kẻ tấn công, không biết bí mật, có thể khiến browser gửi request mà credential hợp lệ tự đi kèm hay không?**

Nếu **có**, mô hình nguy cơ CSRF cần được xem xét. Nếu API chỉ dùng `Authorization: Bearer ...` được **JavaScript của ứng dụng tin cậy chủ động gắn** (không lưu token trong cookie tự gửi và không hỗ trợ cơ chế ambient khác), thì một HTML form cross-site thông thường **không tự có header này**. Nguy cơ CSRF cổ điển giảm đáng kể trong kiến trúc thuần Bearer header, nhưng nguy cơ **XSS/token theft** vẫn tồn tại.

Không suy ra rằng “JWT thì miễn CSRF”; **JWT được lưu trong cookie tự gửi** vẫn có thể tạo điều kiện CSRF.

## 5. Một request giả mạo có thể xuất phát từ HTML form

HTML có thể tạo request sang một origin khác, ngay cả khi JavaScript ở origin đó **không được đọc phản hồi** do Same-Origin Policy.

Ví dụ mô hình kiểm thử trong môi trường **giả lập**:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Mô phỏng request cross-site</title></head>
<body>
  <form action="https://app.example.test/settings/email" method="post">
    <input type="hidden" name="email" value="changed@example.test">
    <button type="submit">Gửi yêu cầu thử nghiệm</button>
  </form>
</body>
</html>
~~~

Trang HTML này chỉ mô tả khả năng **phát sinh POST từ một tài liệu ở origin khác**; nó không truy cập một dịch vụ thật, không tự đọc cookie và không tự chứng minh yêu cầu thành công. Nếu user bấm nút trong một lab nội bộ, browser sẽ tạo request tới URL action. Cookie của `app.example.test` có được gửi hay không còn phụ thuộc `SameSite`, `Secure`, domain/path, browser và trạng thái đăng nhập. Nếu có cookie, server vẫn cần kiểm tra CSRF token hợp lệ trước khi thay đổi dữ liệu.

### Tại sao CORS không tự chặn HTML form?

Các browser từ lâu cho phép một số **simple cross-origin requests** như form `POST` với `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`. Việc script không được đọc kết quả **không đồng nghĩa browser không gửi request**.

Một form POST đơn giản **không cần đạt preflight CORS để được gửi**. Nếu server đã thực hiện thay đổi dữ liệu, việc phản hồi sau đó bị giới hạn đọc bởi browser không thể đảo ngược side effect.

Đối với JavaScript `fetch` gọi cross-origin, có những quy tắc khác về credentials mode, simple requests và preflight. Không lấy một lần fetch bị CORS từ chối để kết luận HTML form/điều hướng cross-origin không thể tác động server.

## 6. CORS, SOP, SameSite và CSRF token khác nhau thế nào?

| Cơ chế | Kiểm soát chính | Không tự bảo đảm |
| --- | --- | --- |
| Same-Origin Policy (SOP) | Hạn chế script origin khác đọc/chạm tới tài nguyên của origin đích | Ngăn mọi request cross-origin được gửi |
| CORS | Cho phép/hạn chế script ở origin khác đọc phản hồi và một số kiểu request cross-origin | Bảo vệ tất cả form POST hoặc xác nhận ý định người dùng |
| Cookie `SameSite` | Quy tắc browser đính kèm cookie khi request cross-site | Chặn mọi request cross-origin hoặc chặn subdomain same-site |
| `HttpOnly` | Giảm khả năng JS đọc cookie | Ngăn browser gửi cookie |
| `Secure`/HTTPS | Giới hạn việc gửi cookie và bảo vệ kênh truyền | Xác nhận người dùng chủ động gửi một hành động |
| `@PreAuthorize` / URL authorization | Người dùng có quyền trên hành động/tài nguyên không? | Request có được khởi tạo từ ngữ cảnh tin cậy hay không? |
| CSRF token gắn với phiên/ngữ cảnh | Request có thêm bằng chứng không tự được browser gửi hay không? | Thay thế xác thực, phân quyền, XSS protection hoặc validation |
| Kiểm tra `Origin`/`Referer` | Nguồn gốc request có trong danh sách được chấp nhận không? | Tự giải quyết mọi trường hợp thiếu header, proxy, subdomain/XSS |

Ví dụ, server trả:

~~~http
Access-Control-Allow-Origin: https://trusted.example.test
Access-Control-Allow-Credentials: true
~~~

chỉ có ý nghĩa trong cơ chế CORS. Nó không đồng nghĩa request từ origin khác không được gửi hoặc không thể gây tác dụng phụ. **Đừng dùng CORS làm biện pháp CSRF duy nhất.**

### Fetch có tự gửi cookie cross-origin không?

Với `fetch`, `credentials` mặc định thường là `"same-origin"`: script không tự gửi cookie với một request **cross-origin** trong chế độ mặc định. Nếu code sử dụng `credentials: "include"`, browser có thể gửi cookie theo những giới hạn như SameSite/third-party cookie policy; để script đọc response, server còn phải cho phép CORS với credentials phù hợp.

Nhưng HTML form có cơ chế khác và không thể suy diễn rủi ro CSRF dựa trên một đoạn `fetch`. Tài liệu an toàn phải xét **mọi cách browser tạo request tới endpoint**, không chỉ SDK JavaScript chính thức của sản phẩm.

## 7. GET nguy hiểm khi nó làm thay đổi dữ liệu

Các chuẩn HTTP coi `GET`, `HEAD`, `OPTIONS` và `TRACE` là **safe methods**: chúng được thiết kế không thực hiện hành động thay đổi trạng thái do client yêu cầu. Spring Security mặc định áp dụng CSRF protection cho các method không được coi là safe, như `POST`, `PUT`, `PATCH`, `DELETE`.

Một API thiết kế sai:

~~~java
// KHÔNG dùng thiết kế này trong sản phẩm:
@GetMapping("/account/remove")
public String remove() {
    accountService.deleteCurrentAccount();
    return "removed";
}
~~~

Đây là **đoạn minh họa lỗi thiết kế**, không phải một tệp Java độc lập. Nếu request GET có thể xóa tài khoản thì chỉ một đường dẫn hoặc tài nguyên nhúng có thể kích hoạt hành động, trong khi `CsrfFilter` mặc định không yêu cầu token với GET.

Thiết kế đúng phải dùng method có ý nghĩa thay đổi trạng thái, bảo vệ bằng CSRF nếu dùng credential tự gửi, và kiểm tra quyền:

~~~java
@PostMapping("/account/remove")
public String remove() {
    accountService.deleteCurrentAccount();
    return "removed";
}
~~~

Đây cũng là ví dụ chữ ký; cần đặt trong Controller và thêm lớp service khi sử dụng thật. **Đổi GET thành POST chưa đủ** nếu server vẫn không kiểm tra CSRF hoặc vô hiệu hóa CSRF tùy tiện. Ngược lại, đặt action thay đổi dữ liệu ở GET khiến nhiều biện pháp mặc định mất tác dụng.

Một thiết kế tốt bảo đảm **safe method không gây tác dụng phụ nghiệp vụ do yêu cầu của client**, đồng thời kiểm tra CSRF trên các request thay đổi trạng thái khi phù hợp với mô hình xác thực.

## 8. Spring Security xử lý CSRF trên Servlet như thế nào?

Spring Security cung cấp `CsrfFilter` và các thành phần:

- `CsrfTokenRepository`: tạo, lưu và tải CSRF token kỳ vọng. Mặc định cho ứng dụng Servlet theo phiên thường là `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: cung cấp token cho view/request và lấy token thực tế từ header/parameter.
- `XorCsrfTokenRequestAttributeHandler`: handler mặc định của Spring Security 6, có lớp ngẫu nhiên hóa để giảm nguy cơ BREACH và xử lý biểu diễn token đưa vào response.
- `CsrfFilter`: với request cần protection, so sánh token do client gửi với token kỳ vọng; nếu thiếu/sai, request bị từ chối.

Luồng khái quát:

~~~text
HTTP request đến ứng dụng
       |
       v
CsrfFilter
       |
       +--> Method được coi là safe? (GET, HEAD, OPTIONS, TRACE)
       |           |
       |           +--> Có: không yêu cầu token theo matcher mặc định
       |
       +--> Method cần CSRF protection?
                   |
                   +--> tải expected token từ CsrfTokenRepository
                   +--> lấy actual token từ request parameter/header
                   |
                   +--> đúng: chuyển tiếp chuỗi filter
                   |
                   +--> thiếu/sai: AccessDeniedException
                                   → thường trả HTTP 403
~~~

Ví dụ, một form HTML hợp lệ thường có trường ẩn:

~~~html
<form action="/settings/email" method="post">
    <input name="email" type="email">
    <input type="hidden" name="_csrf" value="VALUE_FROM_SERVER">
    <button type="submit">Lưu</button>
</form>
~~~

`VALUE_FROM_SERVER` chỉ là ký hiệu cho token được render từ server, không được hardcode. Vì browser **không tự chế tạo một trường hợp lệ này**, một trang origin khác thông thường không biết giá trị phù hợp với phiên của nạn nhân.

Ở Spring MVC tích hợp Thymeleaf phù hợp, form có `th:action`/POST có thể tự nhận hidden input CSRF qua `RequestDataValueProcessor`. Với JavaScript SPA, cấu hình cookie CSRF và request handler phải xét thêm vấn đề **BREACH/XOR masking, deferred token và token được xóa/tạo lại sau login/logout** ở Spring Security 6. Không sao chép công thức cũ chỉ với `CookieCsrfTokenRepository.withHttpOnlyFalse()` rồi giả định mọi SPA sẽ hoạt động đúng.

### CSRF token không phải access token

CSRF token nhằm chứng minh **request thay đổi trạng thái** có một giá trị không được browser đính kèm tự động. Nó không dùng để đăng nhập thay cho mật khẩu/session và không cấp quyền riêng. Một attacker có CSRF token mà không có credential phù hợp cũng không tự thành người dùng có quyền. Một user đã đăng nhập nhưng không có CSRF token phù hợp có thể bị 403 trước khi vào Controller.

## 9. Ứng dụng Spring Boot thực hành: thay đổi email cần session và CSRF token

Để tự kiểm chứng, ta tạo ứng dụng học tập cho phép:

- `GET /`: trang công khai.
- `GET /settings`: trang thiết lập cho người đã đăng nhập.
- `POST /settings/email`: cập nhật email cho tài khoản đang đăng nhập.
- Form login mặc định để tạo phiên người dùng trong trình duyệt.
- CSRF protection mặc định **không bị tắt**.
- Một lớp lưu dữ liệu in-memory để kiểm tra rằng request thiếu token **không thực hiện thay đổi**.

Ví dụ sử dụng Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x. Đây là bài lab với tài khoản mẫu; không sử dụng dữ liệu tài khoản thật.

### 9.1. Cấu trúc dự án

~~~text
csrf-browser-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/example/csrf/
│   ├── CsrfBrowserApplication.java
│   ├── SecurityConfig.java
│   ├── ContactStore.java
│   └── SettingsController.java
├── src/main/resources/templates/
│   └── settings.html
└── src/test/java/example/csrf/
    └── CsrfBrowserTest.java
~~~

### 9.2. settings.gradle và build.gradle

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'csrf-browser-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là build file mẫu cho dự án Gradle Java 17. Chạy từ môi trường có Gradle hoặc wrapper tương thích với Spring Boot 3.3.x. Khi ứng dụng đã có build file, ghép dependency cần thiết thay vì tạo bộ plugin trùng lặp.

### 9.3. CsrfBrowserApplication.java

Tệp `src/main/java/example/csrf/CsrfBrowserApplication.java`:

~~~java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfBrowserApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfBrowserApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java

Tệp `src/main/java/example/csrf/SecurityConfig.java`:

~~~java
package example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/settings").authenticated()
                .requestMatchers(HttpMethod.POST, "/settings/email")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Không gọi csrf.disable(): giữ mặc định bảo vệ các unsafe methods.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }
}
~~~

Lưu ý:

- `formLogin` bật login form và phiên trong browser, nên đây **chính là trường hợp có credential tự đính kèm** cần bảo vệ CSRF.
- `.hasRole("USER")` đòi authority `ROLE_USER` theo quy ước mặc định.
- CSRF được bật mặc định trong Spring Security Servlet; không cần gọi `.csrf(Customizer.withDefaults())` nhưng có thể gọi rõ nếu muốn. Bài này để mặc định.
- `anyRequest().denyAll()` là quy tắc fallback khi chưa khai báo method/path.
- Mật khẩu tài khoản demo được mã hóa bằng BCrypt. Ứng dụng thật không dùng user in-memory cố định trong source.

### 9.5. ContactStore.java

Tệp `src/main/java/example/csrf/ContactStore.java`:

~~~java
package example.csrf;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class ContactStore {

    private final ConcurrentHashMap<String, String> emails =
            new ConcurrentHashMap<>();

    public void save(String username, String email) {
        emails.put(username, email);
    }

    public String current(String username) {
        return emails.getOrDefault(username, "(unset)");
    }

    public void clear() {
        emails.clear();
    }
}
~~~

Đây là kho in-memory để dễ kiểm tra một request có gây side effect hay không. Ứng dụng sản xuất cần database, validation email, quyền theo chủ thể, giới hạn cập nhật và cơ chế xác minh đổi email; không xem `ConcurrentHashMap` là hệ thống tài khoản thật.

### 9.6. SettingsController.java

Tệp `src/main/java/example/csrf/SettingsController.java`:

~~~java
package example.csrf;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class SettingsController {

    private final ContactStore store;

    public SettingsController(ContactStore store) {
        this.store = store;
    }

    @GetMapping("/")
    @ResponseBody
    public String home() {
        return "Public home";
    }

    @GetMapping("/settings")
    public String settings() {
        return "settings";
    }

    @PostMapping("/settings/email")
    @ResponseBody
    public String updateEmail(@RequestParam String email,
                              Authentication authentication) {
        store.save(authentication.getName(), email);
        return "saved:" + email;
    }
}
~~~

Phương thức `settings()` trả tên view, không phải nội dung HTML. `updateEmail(...)` tạo side effect **chỉ sau khi request đi qua các bộ lọc bảo mật**. Không cho client gửi tham số `username` rồi dùng nó để cập nhật tài khoản tùy ý; mã lấy tên người dùng từ `Authentication` đã được Spring Security xác nhận.

### 9.7. settings.html

Tệp `src/main/resources/templates/settings.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Cập nhật email</title>
</head>
<body>
    <h1>Thiết lập tài khoản</h1>

    <form th:action="@{/settings/email}" method="post">
        <label for="email">Email mới</label>
        <input id="email" type="email" name="email" required>
        <button type="submit">Lưu email</button>
    </form>
</body>
</html>
~~~

Với tích hợp Spring MVC + Thymeleaf/Spring Security phù hợp, `th:action` với POST sẽ đi qua xử lý form, tự bổ sung field CSRF ẩn (thường có tên `_csrf`). Khi chạy thật, hãy mở DevTools và **kiểm tra HTML sau khi render** có hidden token; đừng mặc định mọi file HTML tĩnh đều tự có nó.

Không đưa `_csrf` vào `Set-Cookie` và nghĩ browser gửi cookie CSRF tự động là đã có synchronizer token: **giá trị actual phải ở parameter/header mà bên tấn công không thể tự biết hoặc tự gửi hợp lệ**.

### 9.8. Chạy trong browser

Sau khi có Gradle wrapper phù hợp, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Truy cập `http://localhost:8080/settings` khi chưa đăng nhập. Browser được chuyển tới trang login mặc định. Đăng nhập bằng tài khoản demo `lan / demo123`, quay về trang settings rồi submit form. Request POST được Spring Security kiểm tra CSRF token và quyền USER, sau đó Controller trả `saved:...`.

**Kỳ vọng trên trình duyệt:** form hợp lệ được xử lý; request POST tự tạo không có token sẽ bị chặn 403. Mã ví dụ chưa phải kết quả thực thi trong môi trường của người đọc. Không dùng tài khoản/mật khẩu mẫu trên môi trường công khai.

## 10. Kiểm thử Spring Security bằng MockMvc

Phần này chứng minh những điều quan trọng ở tầng server:

- Người dùng đã xác thực **vẫn bị 403** khi POST thiếu hoặc sai CSRF token.
- Người có token hợp lệ và đúng quyền được phép thực hiện cập nhật.
- Ngay cả với CSRF token hợp lệ, người **thiếu quyền** vẫn bị chặn.
- Method GET không được dùng để thay đổi email.
- Thêm header `Origin` giống website hợp lệ **không thay thế CSRF token** trong cấu hình này.

Tệp `src/test/java/example/csrf/CsrfBrowserTest.java`:

~~~java
package example.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfBrowserTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ContactStore store;

    @BeforeEach
    void reset() {
        store.clear();
    }

    @Test
    void publicGetWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public home"));
    }

    @Test
    void anonymousUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/settings"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void validUserReceivesFormWithCsrfInput() throws Exception {
        mvc.perform(get("/settings")
                .with(user("lan").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void authenticatedPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .param("email", "forged@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .with(csrf().useInvalidToken())
                .param("email", "forged@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void authenticatedPostWithValidCsrfCanUpdate() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .with(csrf())
                .param("email", "lan@example.test"))
                .andExpect(status().isOk())
                .andExpect(content().string("saved:lan@example.test"));

        assertEquals("lan@example.test", store.current("lan"));
    }

    @Test
    void csrfTokenDoesNotReplaceAuthentication() throws Exception {
        mvc.perform(post("/settings/email")
                .with(csrf())
                .param("email", "anonymous@example.test"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void csrfTokenDoesNotReplaceAuthorization() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("visitor").roles("GUEST"))
                .with(csrf())
                .param("email", "visitor@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("visitor"));
    }

    @Test
    void originHeaderAloneDoesNotReplaceCsrfToken() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .header("Origin", "https://app.example.test")
                .param("email", "forged@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void getWithEmailParameterDoesNotUpdate() throws Exception {
        mvc.perform(get("/settings")
                .with(user("lan").roles("USER"))
                .param("email", "forged@example.test"))
                .andExpect(status().isOk());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void logoutPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout")
                .with(user("lan").roles("USER")))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests '*CsrfBrowserTest'
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "*CsrfBrowserTest"
~~~

**Kết quả kỳ vọng:** 11 phép thử thành công với cấu hình và phiên bản phù hợp. Đây là **dự đoán theo hợp đồng Spring Security**, chưa phải log thực thi Java/Gradle. Chúng kiểm tra bên server có chặn request thiếu token và giữ nguyên trạng thái, không kiểm tra cookie `SameSite`, SOP hoặc CORS trên trình duyệt thật.

`MockMvc` không phải browser: `.with(user(...))` chỉ tạo danh tính thử nghiệm cho request. Nó **không chứng minh browser sẽ tự gửi cookie từ origin khác**. Muốn kiểm tra điều kiện cookie cross-site, cần một bài test trình duyệt có các origin/site thử nghiệm, HTTPS và cookie policy thực tế.

## 11. Kiểm thử browser riêng cho điều kiện credential tự gửi

Một kiểm thử CSRF thực tế cần trả lời hai câu hỏi độc lập:

1. **Browser có tự gửi credential sang website đích trong tình huống cụ thể không?**
2. **Nếu browser có gửi credential, server có từ chối request thiếu bằng chứng chống CSRF không?**

Một quy trình quan sát an toàn trên **hai host thử nghiệm do bạn kiểm soát**:

1. Chạy ứng dụng mẫu ở một origin thử nghiệm có HTTPS và cookie theo cấu hình cần kiểm tra.
2. Đăng nhập bằng tài khoản giả, kiểm tra cookie tồn tại và browser có gắn `Cookie` vào request same-site không.
3. Mở trang HTML thử nghiệm ở **origin khác**, gửi form POST tới endpoint thử nghiệm. Chỉ dùng dữ liệu mẫu.
4. Trong DevTools → Network, xem request tới server đích có header `Cookie` hay không. Không ghi lại giá trị thật vào tài liệu.
5. Kiểm tra response và trạng thái trong `ContactStore`: nếu thiếu CSRF token, hệ thống phải từ chối và dữ liệu không đổi.
6. Lặp lại với cookie `SameSite=Lax`, `Strict`, `None; Secure` và đối chiếu theo browser. Đặt ý nghĩa test là xác minh **hành vi browser**, không lầm nó với việc thay đổi code xác thực.
7. Lặp lại với một origin khác nhưng cùng site (subdomain thử nghiệm), để thấy “cross-origin” không nhất thiết là “cross-site”.

Các điều kiện lab phải dùng tên miền và chứng chỉ do bạn quản lý. Tránh thay đổi cookie trên ứng dụng sản xuất hoặc thử trên hệ thống không có quyền.

### Ma trận quan sát kỳ vọng

| Cấu hình thử nghiệm | Cookie ở cross-site POST? | CSRF token vắng mặt | Kỳ vọng server |
| --- | --- | --- | --- |
| Cookie `SameSite=None; Secure` và browser cho phép | Có thể có | Có | Bị chặn 403 |
| Cookie `SameSite=Lax` rõ ràng | Thường không có | Có | Không xác thực/không đủ điều kiện, và vẫn không được cập nhật |
| Cookie `SameSite=Strict` | Thường không có | Có | Không được cập nhật |
| Request cùng site, cookie hợp lệ | Có thể có | Có | Bị chặn 403 |
| Request cùng site, cookie hợp lệ | Có và CSRF token hợp lệ | Không | Được xử lý nếu đủ quyền |

Bảng nêu **kỳ vọng**, không phải kết quả đo của một trình duyệt cụ thể. Dù cookie không gửi ở case này, server vẫn phải áp dụng CSRF protection đúng nơi vì cấu hình cookie, browser, subdomain và cách gửi credential có thể thay đổi.

## 12. Trường hợp dùng API Bearer token: khi nào có thể không cần CSRF?

Một API chỉ chấp nhận Bearer access token trong header:

~~~http
POST /api/items HTTP/1.1
Authorization: Bearer example-access-token
Content-Type: application/json

{"name":"demo"}
~~~

Nếu token chỉ được JavaScript của ứng dụng **chủ động gắn** vào header và **không** có cookie/session/Basic/client certificate được browser tự gửi mà API chấp nhận, một form cross-origin thông thường không thể tự thêm header Authorization chứa token không biết. Vì vậy mô hình CSRF cổ điển giảm đáng kể.

Trong một ứng dụng `oauth2ResourceServer` thuần Bearer header và stateless, việc vô hiệu hóa CSRF có thể phù hợp sau khi đánh giá đầy đủ mô hình xác thực. Nhưng cần phân biệt:

- **Bearer token ở header do app JavaScript chủ động thêm:** browser ở origin lạ không tự có header đó.
- **JWT trong HttpOnly cookie:** browser **vẫn tự gửi cookie** nếu cookie policy cho phép; CSRF vẫn phải xét.
- **API nhận cả Bearer header và session cookie:** một đường xác thực tự đính kèm có thể giữ rủi ro CSRF.
- **XSS ở chính origin ứng dụng:** mã độc có thể dùng context của ứng dụng để thực hiện request; CSRF token không được coi là biện pháp chữa XSS.

Không áp dụng quy tắc “API JSON thì không thể CSRF”. Một server có thể chấp nhận simple form content type, có endpoint ghi bằng GET hoặc dùng cookie. Quyết định bật/tắt CSRF phải dựa vào **cách credential được trình duyệt gửi trong mọi endpoint**, không phải tên đường dẫn bắt đầu bằng `/api`.

## 13. Nhiều lớp phòng thủ ngoài synchronizer token

### 13.1. CSRF token gắn với phiên hoặc ngữ cảnh

Đối với form/session cookie, synchronizer token là biện pháp quan trọng. Token phải khó đoán, server kiểm tra giá trị được gửi **không tự động**, và không truyền token qua URL dễ bị log. Theo Spring Security 6, việc tạo/load token có thể deferred và giá trị render có masking để giảm nguy cơ BREACH.

### 13.2. Cookie SameSite phù hợp

Đặt `SameSite=Lax` hoặc `Strict` khi tương thích với trải nghiệm sử dụng; chỉ dùng `None; Secure` khi có nhu cầu cross-site thật sự và có các lớp bảo vệ khác. Khi dùng SSO, iframe hoặc embedded app, việc điều chỉnh SameSite cần được kiểm thử kỹ để tránh hỏng luồng đăng nhập.

### 13.3. Kiểm tra Origin/Referer và Fetch Metadata

Với những endpoint nhạy cảm, xác minh `Origin`, fallback `Referer` đúng cách khi cần, và cân nhắc header `Sec-Fetch-Site` để phân biệt request same-origin, same-site, cross-site. Đừng mù quáng tin mọi request không có Origin đều hợp lệ hoặc mọi subdomain trong cùng site đều đáng tin.

Những kiểm tra này là lớp phòng thủ bổ sung, không loại bỏ nhu cầu authorization, validation và CSRF token trong các thiết kế rủi ro cao.

### 13.4. Không có side effect trong safe methods

Dùng POST/PUT/PATCH/DELETE thích hợp cho thao tác thay đổi trạng thái; tránh thiết kế `GET /delete` hay `GET /transfer`. Kết hợp auth và CSRF trên các unsafe methods. Không dựa vào tên controller như “readOnly” để tự suy ra an toàn nếu code thật vẫn ghi database.

### 13.5. Không tin CORS là cơ chế CSRF

Chỉ bật CORS cho origin tin cậy, nhưng vẫn bảo vệ form POST và những request browser có thể gửi mà không cần preflight. `Access-Control-Allow-Origin` quyết định quyền đọc response của script ở nhiều trường hợp, không xác nhận người dùng muốn chuyển tiền hay đổi email.

### 13.6. Phòng chống XSS và subdomain không tin cậy

XSS có thể giúp mã độc chạy cùng origin, đọc nội dung trang và lấy CSRF token nếu JavaScript có thể nhìn thấy token. Các biện pháp như output encoding, Content Security Policy, giảm JavaScript không tin cậy, kiểm soát dependency và phân tách subdomain đều cần được đánh giá. Một host cùng site bị chiếm quyền có thể làm giảm tác dụng của SameSite.

## 14. Các lỗi nhận thức phổ biến

1. **“Cookie có HttpOnly thì không thể CSRF.”** Sai. HttpOnly ngăn JS đọc cookie, không ngăn browser gửi cookie.
2. **“HTTPS ngăn CSRF.”** Sai. HTTPS bảo vệ đường truyền, không xác minh ý định nguồn gốc request.
3. **“Đã có Spring Security login và hasRole là đủ.”** Sai. Authentication/authorization không thay thế CSRF protection.
4. **“CORS không cho đọc response thì kẻ tấn công không gây side effect.”** Sai. Simple form POST có thể đã được gửi trước khi có vấn đề đọc response.
5. **“Chỉ cần đổi GET sang POST.”** Sai nếu POST vẫn chấp nhận cookie tự gửi mà không kiểm tra CSRF.
6. **“SameSite=Lax chặn mọi CSRF.”** Sai. Top-level safe navigation có thể gửi cookie; sự khác nhau same-site/cross-origin và cookie default cũng quan trọng.
7. **“SameSite=Strict luôn chặn mọi origin lạ.”** Sai khi các origin khác thuộc cùng site hoặc có những tấn công khác.
8. **“JWT thì miễn CSRF.”** Sai nếu JWT được lưu trong cookie trình duyệt tự gửi.
9. **“Authorization: Bearer tự xuất hiện trong HTML form của origin lạ.”** Sai đối với Bearer token chỉ được app tin cậy chủ động đặt ở header.
10. **“Có CSRF token thì được phép mọi thao tác.”** Sai. Token không thay authentication/authorization.
11. **“Có thể lấy CSRF token từ cookie một cách máy móc và gửi lại cùng cookie.”** Nếu cả hai giá trị đều tự được gửi và không có kiểm tra đúng thiết kế, chưa tạo được bằng chứng riêng; phải hiểu synchronizer/double-submit và cách triển khai.
12. **“Một 403 chứng minh CSRF hoạt động.”** 403 có thể đến từ thiếu quyền, CSRF sai hoặc endpoint khác; kiểm tra cả state và log/filter liên quan.
13. **“MockMvc mô phỏng hoàn toàn chính sách SameSite của browser.”** Sai. MockMvc kiểm tra server, không thay browser cross-site thật.
14. **“GET thay đổi dữ liệu vẫn được bảo vệ vì bật CSRF mặc định.”** Sai với matcher safe methods thông thường.
15. **“Ứng dụng API có JSON thì không có CSRF.”** Không đúng nếu cookie tự gửi hoặc endpoint chấp nhận simple requests.
16. **“Browser có thể tự điền password manager vào mọi POST sang domain đó.”** Không đồng nghĩa gửi HTTP authentication: phải xác định cụ thể browser/endpoint đang dùng credential nào.

## 15. Bài tập tình huống và đáp án

**Câu 1.** Người dùng đang có `JSESSIONID` và trang lạ tạo POST đến `/settings/email`. Điều kiện nào quyết định browser có gửi cookie không?

**Đáp án:** URL đích, Domain/Path, Secure/HTTPS, SameSite, thời hạn và chính sách cookie của browser. Cookie tồn tại không có nghĩa nó được gửi trong mọi cross-site POST.

**Câu 2.** Cookie là `HttpOnly; Secure; SameSite=None`, trình duyệt cho phép gửi cookie cross-site. Server chỉ kiểm tra `authenticated()` cho POST đổi email. Có rủi ro gì?

**Đáp án:** Có nguy cơ CSRF nếu browser tự gửi cookie phiên và endpoint không kiểm tra CSRF token/Origin hay bằng chứng tương đương. HttpOnly/Secure không tự chặn hành động giả mạo.

**Câu 3.** API yêu cầu Bearer token do JavaScript same-origin tự đặt vào Authorization header và không chấp nhận cookie/Basic. Một HTML form từ site lạ có tự thêm token không?

**Đáp án:** Không theo mô hình đó. Rủi ro CSRF cổ điển giảm, nhưng cần kiểm soát XSS và nơi lưu Bearer token.

**Câu 4.** Server có CORS chỉ cho `https://trusted.example.test`. Một form POST đơn giản từ site khác gửi đến server. Có thể mặc định request không bao giờ được gửi không?

**Đáp án:** Không. CORS không phải tường lửa chặn mọi HTML form; request có thể tới server, nên server vẫn cần CSRF protection.

**Câu 5.** Cookie có `SameSite=Lax`. Người dùng bấm liên kết cross-site đến `GET /account/delete`. Vì sao vẫn đáng lo?

**Đáp án:** Lax có thể gửi cookie khi điều hướng cấp cao bằng safe method như GET; một endpoint GET có side effect là thiết kế nguy hiểm. Không dùng GET để xóa dữ liệu.

**Câu 6.** Hai origin `https://app.example.test` và `https://forum.example.test` có cùng site không?

**Đáp án:** Có thể có cùng schemeful site, nhưng khác origin. Nếu forum không tin cậy, SameSite một mình chưa phải ranh giới bảo vệ đủ mạnh.

**Câu 7.** Trong MockMvc, POST có `with(user("lan"))` nhưng thiếu `with(csrf())` trả 403. Điều này chứng minh điều gì?

**Đáp án:** Theo cấu hình thử nghiệm, server từ chối POST thiếu token dù có danh tính. Nó chưa chứng minh browser thực gửi cookie cross-site.

**Câu 8.** Vì sao `with(csrf())` mà không có `with(user(...))` vẫn không đủ để đổi email?

**Đáp án:** CSRF token không thay authentication/authorization. Endpoint vẫn yêu cầu một danh tính có quyền USER.

**Câu 9.** Người dùng đã đăng nhập và API trả 403 cho POST không có CSRF, nhưng GET `/account/remove` lại xóa dữ liệu thành công. Lỗi ở đâu?

**Đáp án:** Endpoint thay đổi trạng thái bằng GET, một safe method mà Spring Security CSRF mặc định không yêu cầu token. Cần sửa thiết kế HTTP và policy.

## 16. Checklist kiểm tra trước khi triển khai

- Đã liệt kê mọi hình thức xác thực browser có thể tự gửi (cookie, Basic/Negotiate, client certificate) chưa?
- Đã xác định API nào dùng Bearer header do client chủ động gắn, API nào còn nhận cookie chưa?
- Đã kiểm tra Domain, Path, Secure, HttpOnly, SameSite và chính sách third-party cookies cho các browser mục tiêu chưa?
- Đã phân biệt rõ same-origin và same-site, kiểm soát các subdomain không tin cậy chưa?
- Mọi HTTP GET/HEAD/OPTIONS/TRACE có tuân thủ “không đổi trạng thái” chưa?
- Các POST/PUT/PATCH/DELETE dùng credential tự gửi có cơ chế CSRF token hoặc biện pháp phù hợp thực sự được server kiểm tra chưa?
- Có tránh gửi token trong URL và log không?
- CORS có được giới hạn đúng origin, đồng thời không bị coi là biện pháp CSRF duy nhất chưa?
- Với SPA, đã tích hợp CSRF cookie/request handler đúng với Spring Security 6 và refresh token sau login/logout chưa?
- Đã kiểm thử bằng MockMvc cả trường hợp có user nhưng thiếu/sai CSRF, token đúng nhưng thiếu quyền, token và quyền đúng chưa?
- Đã quan sát browser ở hai origin/site thử nghiệm để xác minh cookie thực sự được đính kèm theo chính sách chưa?
- Đã kiểm thử thay đổi dữ liệu **không xảy ra** khi request bị từ chối, thay vì chỉ nhìn status 403 chưa?
- Đã kiểm tra các endpoint logout, đổi email, thay mật khẩu, mua hàng và giao dịch nhạy cảm có lớp bảo vệ thích hợp chưa?

**Tóm tắt:** CSRF có thể xảy ra khi **một request do nguồn không tin cậy kích hoạt** vẫn được browser **tự mang credential hợp lệ**, endpoint **thực hiện thay đổi trạng thái**, và server **thiếu kiểm chứng nguồn gốc/CSRF token** phù hợp. Cookie `HttpOnly`, HTTPS và CORS không tự giải quyết điều kiện này. Phòng thủ đúng cần kết hợp **CSRF token, thiết kế safe methods đúng, cookie SameSite phù hợp, kiểm tra nguồn gốc khi cần, authentication/authorization và kiểm thử trên browser thật**.

## Tài liệu tham khảo

- [Spring Security — Cross Site Request Forgery (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `CsrfFilter`, `CsrfTokenRepository`, deferred tokens, BREACH và form/SPA.
- [Spring Security — CSRF Overview](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): nguyên lý tấn công và synchronizer token pattern.
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` và token không hợp lệ.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model, token, Origin, SameSite, Fetch Metadata, CORS.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): các thuộc tính và hành vi SameSite.
- [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookie và khác biệt giữa same-site/cross-site.
