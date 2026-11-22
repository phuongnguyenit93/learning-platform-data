# Bảo vệ biểu mẫu trước CSRF

## Mục tiêu

Trong ứng dụng web MVC, trình duyệt thường tự gửi cookie phiên đăng nhập cùng request đến máy chủ. Cơ chế này thuận tiện, nhưng cũng tạo ra rủi ro: một trang web khác có thể khiến trình duyệt gửi request đến ứng dụng mà người dùng đang đăng nhập, dù họ không chủ động thực hiện thao tác đó. Đây là tình huống dẫn đến Cross-Site Request Forgery (CSRF).

Bảo vệ CSRF giúp server xác định request thay đổi trạng thái có mang bằng chứng hợp lệ từ ứng dụng hay không. Với ứng dụng MVC dùng session và cookie, biện pháp phổ biến là token chống CSRF được gắn vào form hoặc header và được server kiểm tra trước khi xử lý.

Bài học này trình bày cơ chế tấn công, cách dùng token, tích hợp Spring Security với form HTML và frontend JavaScript, vai trò của cookie SameSite, kiểm tra nguồn request, các trường hợp API và webhook, cùng chiến lược kiểm thử.

Sau khi học, người học có thể:

- Giải thích CSRF và điều kiện để một cuộc tấn công thành công.
- Nhận diện request có thể làm thay đổi trạng thái cần được bảo vệ.
- Thiết kế luồng token CSRF cho form HTML và request AJAX.
- Cấu hình Spring Security để bảo vệ endpoint thay đổi trạng thái.
- Phân biệt token CSRF, cookie session, CORS và XSS.
- Dùng SameSite, Origin và Fetch Metadata như các lớp phòng vệ bổ sung.
- Xác định ngoại lệ hợp lý cho API hoặc webhook mà không vô hiệu hóa bảo vệ toàn ứng dụng.
- Kiểm thử request thiếu token, token sai và token hợp lệ.

## 1. CSRF là gì?

Cross-Site Request Forgery là kiểu tấn công trong đó kẻ tấn công khiến trình duyệt của người dùng gửi một request đến ứng dụng mà người dùng đã đăng nhập. Trình duyệt có thể tự đính kèm cookie phiên hoặc thông tin xác thực được lưu theo cơ chế tự động gửi. Server nhìn thấy request có phiên hợp lệ và có thể nhầm nó là thao tác do người dùng chủ động thực hiện.

Kẻ tấn công không nhất thiết phải đọc được response. Chỉ cần khiến trình duyệt gửi request có tác dụng phụ là đã có thể gây thiệt hại.

### Một tình huống minh họa

Giả sử người dùng đã đăng nhập vào ngân hàng tại bank.example. Trình duyệt giữ cookie phiên cho tên miền đó. Người dùng mở một trang khác do kẻ tấn công kiểm soát. Trang này chứa một form tự động gửi đến ngân hàng:

    <form action="https://bank.example/transfers" method="post">
        <input type="hidden" name="recipient" value="attacker">
        <input type="hidden" name="amount" value="1000000">
    </form>
    <script>
        document.forms[0].submit();
    </script>

Khi trình duyệt gửi form, nó có thể đính kèm cookie phiên của bank.example. Nếu server chỉ kiểm tra cookie đăng nhập mà không có cơ chế chống CSRF, request có thể được xử lý như thao tác chuyển tiền hợp lệ.

Trang tấn công thường không đọc được response do same-origin policy, nhưng điều đó không ngăn trình duyệt gửi request và cũng không tự ngăn server thực hiện tác dụng phụ.

### Điều kiện thường gặp để CSRF xảy ra

Một cuộc tấn công CSRF thường cần các điều kiện:

1. Người dùng đã xác thực với ứng dụng mục tiêu.
2. Trình duyệt tự động gửi thông tin xác thực, thường là cookie session.
3. Ứng dụng chấp nhận request thay đổi trạng thái mà không xác minh nguồn hoặc ý định hợp lệ.
4. Kẻ tấn công có cách khiến trình duyệt gửi request phù hợp, chẳng hạn form HTML hoặc một request đơn giản.

Token CSRF bổ sung một giá trị bí mật mà trang ngoài không thể tự biết để tạo request hợp lệ. Server chỉ xử lý thao tác khi token được kiểm tra thành công.

## 2. Vì sao cookie đăng nhập không đủ?

Cookie session chứng minh request gắn với một phiên đã xác thực. Nó không chứng minh người dùng đã chủ động nhấn nút hoặc gửi form trên giao diện hợp lệ.

Trình duyệt quản lý cookie theo domain, path, expiry và các thuộc tính bảo mật. Khi request phù hợp với quy tắc cookie, trình duyệt có thể tự gửi cookie mà JavaScript của trang bên ngoài không cần biết giá trị cookie.

Do đó, server cần một bằng chứng bổ sung gắn với giao diện hoặc phiên ứng dụng. Token CSRF đảm nhiệm vai trò này.

### Token CSRF không phải token đăng nhập

| Loại | Mục đích | Cách sử dụng |
|---|---|---|
| Session cookie / access credential | Xác định phiên hoặc danh tính đã xác thực | Trình duyệt gửi theo quy tắc xác thực |
| CSRF token | Chứng minh request thay đổi trạng thái có token hợp lệ từ ứng dụng | Form hoặc JavaScript gửi thêm token; server xác minh |

Không dùng CSRF token thay cho authentication hoặc authorization. Có token hợp lệ không có nghĩa người dùng được phép sửa tài nguyên. Server vẫn phải xác thực và kiểm tra quyền trên từng use case.

### CSRF có thể ảnh hưởng nhiều thao tác

Các thao tác có thể thay đổi trạng thái cần được xem xét, chẳng hạn:

- Chuyển tiền hoặc tạo thanh toán.
- Thay đổi email, mật khẩu hoặc thông tin hồ sơ.
- Tạo, sửa hoặc xóa dữ liệu.
- Thay đổi quyền, vai trò hoặc cấu hình.
- Đăng ký, hủy đăng ký hoặc xác nhận giao dịch.
- Đăng xuất hoặc đăng nhập theo một luồng có tác động đến phiên.

Không chỉ những thao tác tài chính mới cần bảo vệ. Một thao tác thay đổi trạng thái nhỏ cũng có thể gây ảnh hưởng khi bị kích hoạt ngoài ý muốn.

## 3. Nguyên tắc quan trọng: GET không được thay đổi trạng thái

HTTP định nghĩa một số method có ngữ nghĩa an toàn (safe methods), thường gồm GET, HEAD và OPTIONS. Request dùng các method này không nên yêu cầu server thực hiện thay đổi trạng thái nghiệp vụ.

Không tạo endpoint kiểu:

    GET /account/delete
    GET /orders/42/cancel
    GET /transfer?to=attacker&amount=1000000

Các URL này có thể bị truy cập bởi trình duyệt, crawler, prefetcher, preview bot hoặc người dùng chỉ mở liên kết. Nếu GET gây tác dụng phụ, ứng dụng tạo thêm một bề mặt CSRF và khiến cache/công cụ HTTP hoạt động sai ngữ nghĩa.

Hãy dùng POST, PUT, PATCH hoặc DELETE cho thao tác thay đổi trạng thái và bảo vệ chúng bằng token CSRF khi dùng cơ chế xác thực tự động như cookie. Việc dùng method không an toàn không tự động ngăn CSRF; nó chỉ giúp xác định rõ request nào cần kiểm tra token.

| Ý định | Method thường dùng | Có cần CSRF token với session cookie? |
|---|---|---|
| Xem danh sách hoặc chi tiết | GET | Không |
| Tạo tài nguyên | POST | Có |
| Cập nhật toàn bộ | PUT | Có |
| Cập nhật một phần | PATCH | Có |
| Xóa tài nguyên | DELETE | Có |
| Hiển thị form xác nhận | GET | Không, nếu chỉ đọc |
| Xác nhận thao tác | POST | Có |

Nếu một endpoint GET thực sự thay đổi dữ liệu, hãy thiết kế lại semantics của endpoint trước khi tìm cách thêm token cho nó.

## 4. Token CSRF hoạt động như thế nào?

Một cách triển khai phổ biến là Synchronizer Token Pattern. Server tạo token khó đoán và gắn token đó với phiên người dùng hoặc trạng thái server-side. Giao diện nhận token qua HTML form hoặc một cơ chế bootstrap an toàn. Khi gửi request thay đổi trạng thái, client gửi lại token. Server so sánh token nhận được với token mong đợi và từ chối request nếu thiếu hoặc không hợp lệ.

    Người dùng mở form
          |
          v
    Browser GET /profile/edit
          |
          v
    Server tạo / lấy CSRF token
          |
          v
    HTML form chứa hidden token
          |
          v
    Người dùng gửi form
          |
          | POST + session cookie + CSRF token
          v
    CSRF filter kiểm tra token
          |
          +---- token hợp lệ ----> Controller / Use Case
          |
          +---- token thiếu/sai --> 403 Forbidden

Token tạo thêm một bằng chứng mà trang bên ngoài không thể lấy theo cách thông thường do same-origin policy. Trang ngoài có thể khiến browser gửi cookie, nhưng không thể đọc nội dung trang hợp lệ để lấy token gắn trong form hoặc request bootstrap.

### Yêu cầu đối với token

Token CSRF nên:

- Khó đoán và được tạo bằng nguồn ngẫu nhiên an toàn.
- Được ràng buộc với phiên hoặc ngữ cảnh phù hợp.
- Được server xác minh trước khi xử lý tác dụng phụ.
- Không được coi là thông tin xác thực hoặc quyền truy cập.
- Không xuất hiện trong URL, log, analytics hoặc liên kết chia sẻ.
- Được quản lý vòng đời nhất quán khi đăng nhập, đăng xuất hoặc đổi phiên.

Trong phần lớn ứng dụng, nên dùng cơ chế của framework bảo mật thay vì tự tạo token và tự viết filter. Framework đã xử lý nhiều chi tiết về lưu trữ, so sánh, rotation và tích hợp request.

### Token theo phiên và token theo request

Một số triển khai dùng token ổn định trong phạm vi phiên; một số triển khai có thể thay token theo request hoặc theo luồng. Token theo phiên thường dễ sử dụng với nhiều tab và form mở đồng thời. Token thay đổi liên tục có thể làm form cũ hoặc thao tác song song thất bại nếu không có cơ chế tương thích.

Không tự đặt chính sách token one-time nếu ứng dụng không có nhu cầu rõ ràng. Hãy theo hành vi framework và kiểm thử trường hợp nhiều tab, form cũ, đăng nhập lại và đăng xuất.

## 5. Hai cách triển khai token phổ biến

### Synchronizer Token Pattern

Server lưu token trong session hoặc một kho trạng thái gắn với phiên. Khi render form, server đưa token vào hidden input. Khi nhận POST/PUT/PATCH/DELETE, filter đọc token từ request và so sánh với token của phiên.

Ưu điểm:

- Server kiểm soát token và vòng đời.
- Phù hợp tự nhiên với ứng dụng MVC server-side dùng session.
- Token không cần nằm trong cookie mà JavaScript có thể đọc.

Hạn chế:

- Cần quản lý session hoặc trạng thái tương ứng.
- Frontend JavaScript cần một cách lấy token và gửi token qua header.
- Cần xử lý token khi phiên được tạo mới hoặc thay đổi.

### Double Submit Cookie Pattern

Server gửi một cookie chứa token CSRF. Client gửi lại cùng giá trị trong một header hoặc trường form. Server xác minh hai giá trị phù hợp. Một biến thể an toàn hơn có thể ký token hoặc ràng buộc nó với session để ngăn kẻ tấn công tự đặt cookie tùy ý.

Ưu điểm:

- Có thể phù hợp với một số frontend không dùng server-side session.
- Server có thể xác minh token từ cookie và request mà không lưu token riêng trong session.

Hạn chế:

- Cookie token có thể cần được JavaScript đọc, do đó không thể đặt HttpOnly cho cookie CSRF đó.
- Cần thiết kế chống cookie injection và bảo đảm token được xác thực đúng.
- Cấu hình phải phù hợp với framework và cách frontend gửi header.

Không nhầm cookie chứa CSRF token với cookie session. Cookie session vẫn nên được bảo vệ bằng HttpOnly, Secure và SameSite phù hợp. Nếu cookie CSRF cần JavaScript đọc, chỉ cookie CSRF được cấu hình theo nhu cầu đó; không làm cookie session có thể đọc bằng JavaScript.

## 6. Bảo vệ form HTML trong Spring MVC và Spring Security

Spring Security cung cấp CSRF protection cho ứng dụng servlet và bật cơ chế này theo mặc định trong cấu hình web thông thường. CSRF filter kiểm tra token trên các request không an toàn trước khi request đến Controller.

Ví dụ cấu hình có thể giữ CSRF protection rõ ràng:

    @Configuration
    @EnableWebSecurity
    public class SecurityConfig {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {

            return http
                    .authorizeHttpRequests(auth -> auth
                            .requestMatchers("/login", "/assets/**").permitAll()
                            .anyRequest().authenticated())
                    .csrf(Customizer.withDefaults())
                    .build();
        }
    }

Customizer.withDefaults() giữ cấu hình CSRF mặc định. Với cấu hình servlet tiêu chuẩn, Spring Security dùng token repository phù hợp với session. Không gọi csrf(csrf -> csrf.disable()) chỉ để làm cho form POST chạy được; hãy kiểm tra form đã gửi token hay chưa.

### Thêm token vào form

Khi tích hợp Spring MVC, Spring Security và template engine đúng cách, framework có thể tự thêm hidden CSRF input vào form không an toàn. Hãy xác minh HTML thực tế được render trong trình duyệt và hành vi của phiên bản framework đang dùng.

Nếu cần khai báo token rõ ràng trong Thymeleaf, có thể dùng request attribute _csrf:

    <form th:action="@{/profile}"
          th:object="${profileForm}"
          method="post">

        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <label for="displayName">Tên hiển thị</label>
        <input id="displayName"
               type="text"
               th:field="*{displayName}">

        <button type="submit">Lưu thay đổi</button>
    </form>

_csrf.parameterName là tên tham số mà server chờ nhận; _csrf.token là token được cấp cho request/phiên theo cơ chế framework. Dùng đúng thuộc tính do Spring Security cung cấp, không tự đặt tên hoặc giá trị token.

Với JSP hoặc template engine khác, cách truy cập token có thể khác. Điều quan trọng là hidden input được render trong form và request gửi lại đúng tên cùng giá trị.

### Form đăng nhập cũng cần được xem xét

CSRF không chỉ liên quan đến form sau khi người dùng đăng nhập. Login CSRF có thể khiến nạn nhân đăng nhập vào tài khoản do kẻ tấn công kiểm soát, sau đó vô tình lưu dữ liệu riêng tư vào tài khoản đó. Hãy giữ bảo vệ cho luồng đăng nhập theo cấu hình Spring Security và kiểm tra token trên form login tùy chỉnh.

Logout cũng là thao tác thay đổi trạng thái phiên. Dùng POST cho logout và giữ CSRF protection. Không tạo liên kết GET để đăng xuất.

### Nếu token bị thiếu hoặc sai

Spring Security thường từ chối request không có token hợp lệ bằng 403 Forbidden. Controller và Application Service không được chạy cho request bị filter từ chối. Người dùng có thể cần tải lại form để lấy token mới hoặc đăng nhập lại nếu phiên đã hết hạn.

Không nên hiển thị token mong đợi hoặc giá trị token nhận được trong thông báo lỗi hay log.

## 7. Gửi token từ JavaScript hoặc SPA

Một frontend JavaScript có thể gửi request thay đổi trạng thái qua fetch hoặc thư viện HTTP. Khi dùng cookie session, trình duyệt vẫn có thể tự gửi cookie, vì vậy request cần kèm CSRF token trong header theo hợp đồng server.

Một cách triển khai là dùng CookieCsrfTokenRepository của Spring Security:

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .csrf(csrf -> csrf
                        .csrfTokenRepository(
                                CookieCsrfTokenRepository.withHttpOnlyFalse()))
                .build();
    }

Cấu hình này dùng cookie XSRF-TOKEN để frontend có thể đọc token và gửi lại qua header X-XSRF-TOKEN theo mặc định của repository. withHttpOnlyFalse() áp dụng cho cookie CSRF để JavaScript đọc được; không áp dụng nó cho cookie session.

Ví dụ request:

    const response = await fetch("/api/profile", {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
      },
      body: JSON.stringify({
        displayName: "Lan Nguyen"
      })
    });

Trong ví dụ, csrfToken phải được lấy từ cookie hoặc cơ chế bootstrap đã được ứng dụng thiết kế. Không hardcode token vào JavaScript, không lấy token từ URL và không lưu token trong nơi có thể bị chia sẻ công khai.

### Lưu ý với Spring Security hiện đại

Các phiên bản Spring Security mới có thể dùng deferred token và BREACH protection với token được mã hóa khi đưa vào request attribute. Khi xây dựng SPA, cần cấu hình CsrfTokenRequestHandler và luồng tải lại token theo hướng dẫn của đúng phiên bản đang sử dụng. Cookie repository có thể chứa giá trị token gốc trong khi giá trị được hiển thị cho form/request attribute đã được xử lý theo cơ chế bảo vệ response.

Sau khi đăng nhập hoặc đăng xuất, token có thể được làm mới hoặc xóa cùng session. SPA cần lấy token mới trước request thay đổi trạng thái tiếp theo. Hãy kiểm thử luồng thực tế thay vì giả định token cookie cũ luôn dùng được.

### Không gửi token trong URL

Không dùng dạng:

    POST /api/profile?csrfToken=secret-value

URL có thể xuất hiện trong browser history, access log, proxy log, analytics, Referer hoặc hệ thống giám sát. Token nên nằm trong hidden form field hoặc header theo cơ chế framework.

## 8. Cookie SameSite là lớp phòng vệ bổ sung

Thuộc tính SameSite kiểm soát khi nào trình duyệt gửi cookie trong ngữ cảnh request cross-site.

| Giá trị | Hành vi khái quát | Tác động |
|---|---|---|
| Strict | Cookie chỉ được gửi trong ngữ cảnh same-site | Giảm mạnh việc gửi cookie khi điều hướng từ site khác, nhưng có thể ảnh hưởng liên kết từ bên ngoài |
| Lax | Cookie được gửi trong một số ngữ cảnh same-site và điều hướng top-level an toàn | Thường cân bằng khả năng sử dụng và bảo vệ; không thay thế CSRF token |
| None | Cho phép gửi cookie cross-site | Phải đi cùng Secure trong trình duyệt hiện đại và cần cân nhắc CSRF kỹ hơn |

Cookie session có thể được cấu hình với Secure, HttpOnly và SameSite phù hợp:

- Secure: chỉ gửi cookie qua HTTPS.
- HttpOnly: JavaScript không đọc trực tiếp cookie.
- SameSite: hạn chế cookie trong một số request cross-site.

### Vì sao SameSite không thay thế token?

SameSite là một lớp bảo vệ hữu ích, nhưng không nên là biện pháp duy nhất cho các thao tác quan trọng:

- Cấu hình SameSite=None có thể cần cho một số luồng tích hợp hoặc nhúng.
- Một số tình huống điều hướng top-level vẫn có thể gửi cookie với Lax.
- Ứng dụng có thể có nhiều subdomain hoặc ranh giới site khác origin.
- Hành vi cookie phụ thuộc trình duyệt và cấu hình triển khai.
- Token CSRF cho phép server kiểm tra request theo hợp đồng rõ ràng.

Hãy dùng SameSite như defense in depth, đồng thời giữ token cho các request thay đổi trạng thái dùng cookie authentication.

### Site và origin không giống nhau

Origin thường được xác định bởi scheme, host và port. Site dùng khái niệm registrable domain cùng scheme theo quy tắc của trình duyệt. Hai subdomain có thể khác origin nhưng vẫn cùng site. Điều này quan trọng khi thiết kế cookie, CORS và luồng frontend/backend trên nhiều host.

Không giả định rằng hai URL khác origin luôn là cross-site hoặc hai subdomain cùng tổ chức luôn an toàn như nhau.

## 9. Kiểm tra Origin, Referer và Fetch Metadata

Ngoài token, server có thể kiểm tra các header mô tả nguồn request.

### Origin

Header Origin cho biết origin đã khởi tạo request trong những trường hợp trình duyệt gửi header này. Server có thể so sánh với danh sách origin được phép. So sánh cần dùng origin chuẩn hóa gồm scheme, host và port; không dùng kiểm tra chuỗi con như endsWith("example.com") vì có thể chấp nhận nhầm domain giả.

### Referer

Header Referer có thể cung cấp URL của trang nguồn. Nó có thể bị lược bỏ do Referrer-Policy hoặc chính sách trình duyệt, vì vậy không nên yêu cầu header này luôn tồn tại trong mọi trường hợp.

### Fetch Metadata

Các header như Sec-Fetch-Site, Sec-Fetch-Mode và Sec-Fetch-Dest cho biết ngữ cảnh fetch của trình duyệt. Ví dụ, Sec-Fetch-Site: cross-site có thể giúp server nhận diện request bắt nguồn từ site khác.

Có thể từ chối một số request thay đổi trạng thái rõ ràng là cross-site nếu ứng dụng không có luồng hợp lệ cần chúng. Tuy nhiên, cần có fallback và quy tắc rõ cho client không gửi các header này.

### Dùng các kiểm tra này như lớp bổ sung

Một chính sách phòng vệ có thể gồm:

1. Bắt buộc CSRF token với request thay đổi trạng thái dùng cookie session.
2. Kiểm tra Origin khi header hiện diện và theo allowlist.
3. Dùng Referer làm tín hiệu bổ sung khi phù hợp.
4. Phân tích Fetch Metadata để chặn một số request cross-site không mong muốn.
5. Cấu hình SameSite cho cookie phiên.

Không nên chỉ dựa vào Referer hoặc Fetch Metadata để thay thế token trong một ứng dụng có thể dùng token. Header nguồn giúp tăng khả năng phát hiện request bất thường nhưng có giới hạn về khả năng hiện diện và tương thích.

## 10. CSRF khác gì với CORS và XSS?

Ba khái niệm này thường bị nhầm lẫn vì đều liên quan đến trình duyệt và request cross-origin, nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Câu hỏi chính | Vai trò |
|---|---|---|
| CSRF protection | Request thay đổi trạng thái có mang bằng chứng hợp lệ từ ứng dụng không? | Ngăn site khác lợi dụng thông tin xác thực tự động gửi |
| CORS | JavaScript từ origin nào được phép đọc response cross-origin? | Kiểm soát quyền truy cập response từ script trên origin khác |
| XSS protection | Nội dung không tin cậy có thể chạy script trong origin ứng dụng không? | Ngăn kẻ tấn công thực thi script cùng quyền với trang |

### CORS không thay thế CSRF

CORS chủ yếu kiểm soát việc script ở origin khác có được đọc response hay không. Một HTML form có thể gửi một số request cross-origin mà không cần quyền đọc response. Vì vậy, cấu hình CORS không tự ngăn một form độc hại gửi POST đến server.

Preflight có thể ngăn một số request JavaScript không đơn giản, nhưng không nên dựa vào điều đó làm cơ chế CSRF tổng quát.

### XSS có thể vượt qua CSRF token

Nếu kẻ tấn công đã chạy được JavaScript trong origin hợp lệ thông qua XSS, script có thể đọc token trong DOM hoặc lấy token qua endpoint hợp lệ rồi gửi request. Vì vậy, CSRF token không thay thế output encoding, Content Security Policy và các biện pháp phòng chống XSS.

### Cần nhiều lớp bảo vệ

Ứng dụng dùng session cookie nên kết hợp:

- CSRF token cho request thay đổi trạng thái.
- Cookie Secure, HttpOnly và SameSite phù hợp.
- Output encoding và CSP để giảm nguy cơ XSS.
- CORS allowlist đúng nhu cầu cho API cross-origin.
- Authentication và authorization cho từng use case.

Mỗi cơ chế giải quyết một phần rủi ro riêng.

## 11. API JSON và xác thực không dùng cookie

Không phải mọi API đều có cùng rủi ro CSRF. Hãy xem trình duyệt gửi thông tin xác thực bằng cách nào.

### Bearer token được JavaScript chủ động gắn vào header

Nếu client lưu access token ở một nơi không tự động được gửi theo request và chủ động đặt:

    Authorization: Bearer <access-token>

thì trang ngoài thường không thể khiến browser tự gắn header Authorization tùy ý. Rủi ro CSRF theo mô hình cookie giảm đáng kể.

Tuy nhiên, cách lưu token có thể tạo rủi ro XSS hoặc đánh cắp token. Cần đánh giá toàn bộ mô hình xác thực, không kết luận rằng mọi API JSON đều không cần CSRF.

### Token được lưu trong cookie

Nếu access token hoặc session token được lưu trong cookie và trình duyệt tự động gửi cookie, API vẫn có thể chịu CSRF dù response là JSON. Định dạng JSON không tự bảo vệ endpoint.

### HTTP Basic hoặc thông tin xác thực tự động gửi

Nếu trình duyệt tự động đính kèm thông tin xác thực như Basic Authentication hoặc cookie, cần đánh giá CSRF tương tự cơ chế tự động gửi credential. Không chỉ dựa vào việc API không có HTML form.

### Quyết định theo cơ chế xác thực

| Cơ chế xác thực | Rủi ro CSRF điển hình | Cách tiếp cận |
|---|---|---|
| Session cookie | Có, vì browser tự gửi cookie | Bật CSRF token cho request thay đổi trạng thái |
| Access token trong cookie | Có, vì browser tự gửi cookie | Bảo vệ CSRF tương ứng |
| Bearer token do JavaScript gắn vào Authorization header | Thấp hơn đối với CSRF cổ điển | Bảo vệ token khỏi XSS, kiểm soát CORS và authorization |
| HTTP Basic tự động gửi bởi browser | Có thể có | Đánh giá CSRF và cấu hình phù hợp |
| Webhook có chữ ký từ server-to-server | Thường không dùng cookie phiên browser | Xác minh chữ ký, timestamp và chống replay |

Không tắt CSRF chỉ vì endpoint có tiền tố /api hoặc chỉ nhận JSON. Hãy xác định credential có được trình duyệt tự động gửi hay không.

## 12. Webhook và endpoint cần miễn CSRF

Một webhook từ hệ thống bên ngoài thường không có session cookie của người dùng. Nó có thể xác thực bằng chữ ký HMAC, mTLS hoặc một cơ chế server-to-server khác. Trong trường hợp đó, endpoint webhook có thể cần được loại khỏi kiểm tra CSRF token vì bên gửi không có cách lấy token từ form của ứng dụng.

Việc miễn phải có phạm vi hẹp và đi kèm xác thực webhook thực sự:

- Xác minh chữ ký trên raw request body theo tài liệu nhà cung cấp.
- Kiểm tra timestamp hoặc nonce để giảm replay.
- Dùng so sánh chữ ký an toàn theo thư viện phù hợp.
- Kiểm tra event ID để xử lý message trùng.
- Giới hạn kích thước body và tốc độ request.
- Không tin header hoặc payload chỉ vì URL được gọi là webhook.

Ví dụ cấu hình minh họa:

    http
        .csrf(csrf -> csrf
            .ignoringRequestMatchers("/webhooks/provider/**"));

Chỉ áp dụng ngoại lệ này khi endpoint dùng cơ chế xác thực webhook độc lập với cookie browser. Nếu webhook có thể được gọi bằng session cookie của người dùng, cần xem xét lại rủi ro.

Không nên miễn CSRF cho toàn bộ /api/** chỉ để tránh lỗi 403. Một ứng dụng có thể đồng thời có API dành cho SPA dùng session cookie và API server-to-server. Phạm vi bảo vệ phải phản ánh cơ chế xác thực của từng endpoint.

## 13. Vòng đời token khi đăng nhập, đăng xuất và nhiều tab

CSRF token gắn với phiên hoặc ngữ cảnh bảo mật. Khi trạng thái xác thực thay đổi, token có thể cần được làm mới hoặc xóa để tránh dùng lại giá trị thuộc phiên cũ.

Các tình huống cần xem xét:

- Người dùng đăng nhập thành công và session ID được thay đổi.
- Người dùng đăng xuất và session bị hủy.
- Phiên hết hạn trong khi form vẫn mở.
- Người dùng mở nhiều tab với các form được render ở thời điểm khác nhau.
- SPA giữ cookie CSRF cũ sau khi authentication state thay đổi.
- Server triển khai nhiều instance và cần chia sẻ session/token state.

Hãy dùng session management và CSRF integration của framework để xử lý rotation. Nếu tự xây dựng, cần thiết kế rõ token có hiệu lực bao lâu, khi nào bị vô hiệu, và điều gì xảy ra với form đang mở.

### Form cũ sau khi session hết hạn

Một người dùng có thể mở form, để đó lâu rồi mới gửi. Nếu session đã hết hạn, token không còn hợp lệ và server từ chối request. Giao diện nên thông báo phiên đã hết hạn và hướng dẫn đăng nhập lại hoặc tải lại form. Không nên tắt CSRF để làm cho form cũ tiếp tục gửi được.

### Không lưu token vào log

Token CSRF là dữ liệu bí mật theo phiên. Không log hidden input, request parameter hoặc header token. Khi điều tra lỗi 403, ghi loại lỗi, request ID và trạng thái token thiếu/sai nếu framework cung cấp; không ghi giá trị token.

## 14. Kiểm thử CSRF trong Spring Security

Kiểm thử cần xác nhận cả request hợp lệ lẫn request thiếu hoặc sai token. Với Spring Security Test, có thể dùng csrf() RequestPostProcessor trong MockMvc.

Ví dụ request hợp lệ:

    mockMvc.perform(post("/profile")
            .with(csrf())
            .param("displayName", "Lan"))
        .andExpect(status().is3xxRedirection());

Request không có token:

    mockMvc.perform(post("/profile")
            .param("displayName", "Lan"))
        .andExpect(status().isForbidden());

Request có token không hợp lệ:

    mockMvc.perform(post("/profile")
            .with(csrf().useInvalidToken())
            .param("displayName", "Lan"))
        .andExpect(status().isForbidden());

Có thể kiểm tra token qua header cho frontend:

    mockMvc.perform(patch("/api/profile")
            .with(csrf().asHeader())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "Lan"
                }
                """))
        .andExpect(status().isOk());

Các ví dụ giả định test đã cấu hình Spring Security filter chain, chẳng hạn dùng springSecurity() trong MockMvc setup, và endpoint thực tế trả status như mong đợi. Cần thêm dependency spring-security-test tương ứng với phiên bản Spring Security của dự án.

### Kiểm thử form được render

Ngoài MockMvc request test, hãy xác minh HTML thực tế:

- Form POST có hidden input chứa CSRF token.
- Tên input khớp với tên parameter framework mong đợi.
- Giá trị token không rỗng.
- Form GET không cần gửi token chỉ để hiển thị.
- Các form thay đổi trạng thái khác cũng có token.
- Token không xuất hiện trong URL hoặc nội dung log.

Nếu template engine tự động thêm token, test nên xác nhận hành vi tích hợp đó thay vì thêm một hidden input thứ hai.

### Kiểm thử luồng phiên

Các test tích hợp nên bao gồm:

- Đăng nhập rồi gửi form với token mới.
- Đăng xuất qua POST có token.
- Request sau khi session hết hạn bị từ chối hoặc yêu cầu đăng nhập lại theo chính sách.
- Token cũ sau khi đổi session không được chấp nhận ngoài chính sách.
- SPA tải token mới sau login/logout.
- Endpoint webhook được miễn CSRF vẫn yêu cầu chữ ký hợp lệ.
- Endpoint API dùng cookie session vẫn từ chối request thiếu token.

Không chỉ kiểm tra rằng một request POST có thể thành công. Mục tiêu là chứng minh filter từ chối request không có bằng chứng CSRF hợp lệ trước khi use case chạy.

## 15. Xử lý lỗi CSRF thân thiện và an toàn

Khi token thiếu, sai hoặc hết hiệu lực, Spring Security thường trả 403 Forbidden. Đây là kết quả của lớp bảo mật trước Controller, không phải lỗi validation của form và không nên chuyển thành thông báo thành công.

Với ứng dụng HTML, có thể hiển thị trang lỗi ngắn:

- “Phiên làm việc đã hết hạn hoặc biểu mẫu không còn hợp lệ.”
- “Vui lòng tải lại trang và thử lại.”
- Nếu cần, hướng dẫn đăng nhập lại.

Với API, trả error code ổn định như CSRF_TOKEN_INVALID hoặc một mã bảo mật chung theo hợp đồng. Không trả token mong đợi, token nhận được hoặc chi tiết session.

### Phân biệt 401 và 403

- 401 Unauthorized thường biểu thị request chưa có xác thực hợp lệ.
- 403 Forbidden thường biểu thị request đã được nhận diện hoặc không được phép thực hiện, bao gồm trường hợp CSRF token bị từ chối.

Trong thực tế, Spring Security có thể xử lý authentication entry point và access denied handler khác nhau. Hãy kiểm tra response theo cấu hình thật của ứng dụng, không giả định mọi lỗi bảo mật đều có cùng status.

### Không làm lộ lý do chi tiết cho bên ngoài

Không cần nói token bị sai vì giá trị nào hoặc phiên có token nào. Người dùng chỉ cần biết cần tải lại form hoặc đăng nhập lại. Diagnostic log có thể ghi loại exception và request ID trong phạm vi nội bộ mà không lưu token.

## 16. Các sai lầm thường gặp

### Tắt CSRF để sửa lỗi 403

Điều này làm mất bảo vệ cho tất cả endpoint nằm trong phạm vi cấu hình. Hãy kiểm tra hidden input, header, token lifecycle và filter chain trước khi thay đổi cấu hình.

### Chỉ bảo vệ form HTML, bỏ quên API

API dùng cookie session cũng có rủi ro CSRF. Cần đánh giá theo cách browser gửi credential, không theo URL hoặc media type.

### Dùng GET cho thao tác thay đổi trạng thái

GET có thể bị kích hoạt bởi link, prefetch hoặc crawler. Dùng method phù hợp và bảo vệ request thay đổi trạng thái.

### Coi CORS là cơ chế chống CSRF

CORS chủ yếu giới hạn việc đọc response cross-origin. HTML form vẫn có thể gửi một số request cross-origin. Cần CSRF token cho cookie-authenticated requests.

### Đưa token vào URL

Token có thể rò rỉ qua history, logs và Referer. Dùng hidden input hoặc header.

### Để JavaScript đọc cookie session

Cookie session nên có HttpOnly. Nếu SPA cần đọc CSRF token từ cookie, chỉ cookie CSRF được cấu hình có chủ đích để JavaScript đọc.

### Dùng SameSite làm lớp bảo vệ duy nhất

SameSite hữu ích nhưng không thay thế token trong ứng dụng có thao tác nhạy cảm hoặc nhiều kiểu client.

### Miễn CSRF cho toàn bộ API

Chỉ miễn endpoint có lý do rõ ràng và xác thực độc lập với cookie browser. /api không phải bằng chứng endpoint không thể bị CSRF.

### Không kiểm thử request thiếu token

Một test chỉ chứng minh request có token thành công chưa đủ. Cần xác nhận request thiếu và token sai bị từ chối, đồng thời use case không được gọi.

## 17. Quy trình bảo vệ một biểu mẫu MVC

Khi xây dựng form hoặc endpoint thay đổi trạng thái, có thể làm theo trình tự:

1. Liệt kê thao tác có tác dụng phụ và bảo đảm chúng không dùng GET.
2. Xác định cơ chế xác thực: session cookie, token trong cookie, bearer header hay server-to-server.
3. Giữ CSRF protection cho các request có credential tự động gửi.
4. Dùng token repository và filter của framework.
5. Bảo đảm form HTML gửi hidden token hoặc frontend gửi header theo hợp đồng.
6. Cấu hình cookie session với Secure, HttpOnly và SameSite phù hợp.
7. Kiểm tra Origin/Fetch Metadata như lớp bổ sung khi phù hợp.
8. Chỉ miễn endpoint không dùng cookie browser và có xác thực riêng như webhook signature.
9. Thiết kế phản hồi 403 thân thiện, không tiết lộ token.
10. Kiểm thử token hợp lệ, thiếu, sai, hết hạn, login/logout, nhiều tab và endpoint được miễn.

## 18. Checklist trước khi đưa form vào sử dụng

- Mọi thao tác thay đổi trạng thái dùng method HTTP phù hợp.
- GET, HEAD và OPTIONS không làm thay đổi trạng thái nghiệp vụ.
- CSRF protection được bật cho endpoint dùng session cookie.
- Form có token hidden hoặc tích hợp tự động đã được xác minh.
- Request AJAX/SPA gửi token qua header đúng quy ước.
- Cookie session có Secure, HttpOnly và SameSite phù hợp.
- Token không nằm trong URL, log hoặc analytics.
- Đăng nhập, đăng xuất và session rotation có xử lý token phù hợp.
- CORS không bị coi là biện pháp thay thế CSRF.
- Endpoint API được đánh giá theo cách xác thực thực tế.
- Ngoại lệ webhook có chữ ký hoặc xác thực độc lập và phạm vi miễn hẹp.
- Request thiếu hoặc sai token bị từ chối trước khi use case chạy.
- Thông báo lỗi không tiết lộ token hoặc chi tiết session.

## Kết luận

CSRF lợi dụng việc trình duyệt tự động gửi cookie hoặc thông tin xác thực để khiến ứng dụng thực hiện thao tác mà người dùng không chủ động yêu cầu. Với MVC dùng session cookie, token CSRF là bằng chứng bổ sung cho các request thay đổi trạng thái. Server kiểm tra token trước khi cho phép Controller và use case tiếp tục.

Trong Spring MVC, Spring Security cung cấp filter và token repository để bảo vệ form và request API. Form HTML gửi token qua hidden input; frontend JavaScript có thể gửi token qua header theo cấu hình phù hợp. SameSite, Origin và Fetch Metadata tăng cường phòng vệ, còn CORS và XSS protection giải quyết các vấn đề khác. Khi giữ đúng ranh giới, giới hạn ngoại lệ và kiểm thử request thiếu/sai token, ứng dụng có thể bảo vệ các thao tác thay đổi trạng thái mà vẫn giữ trải nghiệm người dùng rõ ràng.
