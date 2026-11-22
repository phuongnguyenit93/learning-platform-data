# Bảo vệ session, cookie và thông tin nhạy cảm

Ứng dụng MVC trên web thường cần ghi nhớ người dùng đã đăng nhập, quyền truy cập và một số trạng thái trong quá trình điều hướng giữa nhiều request. HTTP vốn không lưu trạng thái giữa các request, vì vậy ứng dụng thường dùng session phía máy chủ và cookie trong trình duyệt để liên kết các request với cùng một phiên làm việc.

Session và cookie là những cơ chế tiện lợi nhưng cũng là ranh giới bảo mật quan trọng. Cookie phiên thường mang một mã định danh có giá trị như thông tin xác thực dạng bearer: ai lấy được mã này có thể thử sử dụng phiên của người dùng. Session phía máy chủ có thể chứa trạng thái đăng nhập hoặc dữ liệu cá nhân. Vì vậy, cần bảo vệ cả mã cookie, kho session và những dữ liệu được đưa vào session.

Bài học này tập trung vào cách bảo vệ session, cookie và thông tin nhạy cảm trong ứng dụng MVC web. Các ví dụ sử dụng Java, Spring MVC và Spring Security; nguyên tắc vẫn áp dụng cho những framework web khác.

## 1. HTTP không tự duy trì trạng thái phiên

Mỗi HTTP request độc lập ở cấp giao thức. Trình duyệt gửi một request, máy chủ trả response, rồi request tiếp theo được gửi như một lần trao đổi mới. Máy chủ không tự biết hai request thuộc cùng một người dùng nếu ứng dụng không có cơ chế nhận diện.

Ví dụ người dùng đăng nhập thành công rồi mở trang hồ sơ. Ứng dụng cần biết request xem hồ sơ thuộc về phiên đã đăng nhập nào. Một cách phổ biến là:

1. Người dùng gửi thông tin đăng nhập.
2. Máy chủ xác thực thông tin và tạo session.
3. Máy chủ gửi cookie chứa session identifier về trình duyệt.
4. Trình duyệt tự gửi cookie đó trong những request tiếp theo phù hợp với phạm vi cookie.
5. Máy chủ dùng session identifier để tìm trạng thái phiên phía máy chủ.
6. Khi đăng xuất hoặc session hết hạn, máy chủ vô hiệu hóa phiên.

### 1.1. Session và cookie không phải cùng một thứ

- **Session:** trạng thái được ứng dụng quản lý, thường lưu ở máy chủ hoặc kho session dùng chung.
- **Session identifier:** mã định danh phiên, dùng để tra cứu session.
- **Cookie:** cơ chế trình duyệt lưu và gửi một cặp tên/giá trị cùng các thuộc tính điều khiển phạm vi và cách gửi.
- **Authentication:** kết quả xác thực danh tính, thường được framework bảo mật duy trì trong SecurityContext gắn với request/session.
- **Authorization:** quyết định người dùng đã xác thực có được phép thực hiện hành động cụ thể hay không.

Cookie không phải kho dữ liệu an toàn để lưu toàn bộ session. Trong mô hình session phía máy chủ, cookie chỉ cần chứa một định danh khó đoán; trạng thái thật nằm trong session store.

### 1.2. Luồng session cơ bản

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant A as Ứng dụng MVC
    participant S as Session Store

    U->>B: Gửi biểu mẫu đăng nhập
    B->>A: POST /login
    A->>A: Xác thực thông tin
    A->>S: Tạo session và SecurityContext
    S-->>A: Session ID
    A-->>B: Set-Cookie: SESSION=opaque-id
    B->>B: Lưu cookie theo thuộc tính
    B->>A: GET /profile + Cookie
    A->>S: Tra cứu session
    S-->>A: Trạng thái phiên
    A->>A: Kiểm tra quyền
    A-->>B: HTML hoặc JSON
~~~

Session identifier là dữ liệu nhạy cảm. Nếu bị đánh cắp, kẻ tấn công có thể chiếm quyền sử dụng phiên mà không cần biết mật khẩu của người dùng. Vì vậy, cần bảo vệ nó như một credential.

## 2. Vòng đời của session

Vòng đời session thường gồm tạo mới, sử dụng, gia hạn, hết hạn và hủy bỏ.

### 2.1. Tạo session

Session có thể được tạo khi người dùng đăng nhập hoặc khi ứng dụng cần lưu trạng thái trước đăng nhập, ví dụ giỏ hàng ẩn danh. Không nên tạo session một cách không cần thiết cho mọi request công khai nếu ứng dụng không cần trạng thái.

Khi xác thực thành công, framework bảo mật cần gắn trạng thái xác thực vào session đã được bảo vệ. Không tự tạo session identifier bằng UUID hoặc timestamp trong mã ứng dụng; hãy để servlet container hoặc framework tạo mã có độ ngẫu nhiên và cơ chế quản lý phù hợp.

### 2.2. Xoay vòng session identifier sau đăng nhập

Một rủi ro phổ biến là session fixation. Kẻ tấn công tìm cách khiến nạn nhân sử dụng một session identifier mà kẻ tấn công đã biết. Nếu ứng dụng giữ nguyên identifier đó sau khi nạn nhân đăng nhập, kẻ tấn công có thể sử dụng cùng phiên.

Sau khi xác thực thành công hoặc nâng quyền, ứng dụng cần thay đổi session identifier. Framework có thể đổi ID nhưng giữ lại trạng thái session hợp lệ. Với Servlet hiện đại, thao tác thường dùng là changeSessionId.

Ví dụ cấu hình Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId())
        );

    return http.build();
}
~~~

Đoạn cấu hình minh họa Spring Security hiện đại. Hành vi mặc định có thể đã thực hiện bảo vệ session fixation tùy phiên bản và cấu hình; khai báo tường minh giúp chính sách dễ được đọc và rà soát. Không tự giữ lại session ID cũ sau khi đăng nhập.

Cũng cần cân nhắc đổi hoặc làm mới session khi người dùng nâng quyền, thay đổi mật khẩu, bật/tắt MFA hoặc thực hiện thao tác nhạy cảm. Việc thay đổi ID cần đi cùng quy tắc giữ lại những thuộc tính session hợp lệ và loại bỏ trạng thái không còn tin cậy.

### 2.3. Gia hạn và hết hạn

Hai khái niệm thời gian thường gặp:

- **Idle timeout:** phiên hết hạn sau một khoảng thời gian không có hoạt động.
- **Absolute timeout:** phiên hết hạn sau tổng thời gian tối đa kể từ khi tạo, kể cả khi người dùng vẫn hoạt động.

Idle timeout giúp giảm thời gian một phiên bị bỏ quên vẫn còn hiệu lực. Absolute timeout giới hạn thời gian sống tối đa của credential. Với thao tác rủi ro cao, ứng dụng có thể yêu cầu xác thực lại dù session vẫn còn hiệu lực.

Không nên để session đăng nhập tồn tại vô thời hạn chỉ vì người dùng thỉnh thoảng mở một tab. Thời hạn nên dựa trên độ nhạy của ứng dụng, môi trường sử dụng và chính sách tổ chức.

### 2.4. Đăng xuất và hủy session

Đăng xuất cần vô hiệu hóa trạng thái phía máy chủ, xóa thông tin xác thực trong SecurityContext và yêu cầu trình duyệt xóa cookie phiên.

Ví dụ cấu hình logout:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("SESSION")
        );

    return http.build();
}
~~~

Tên cookie trong ví dụ phải khớp với tên ứng dụng thực tế. Khi xóa cookie, thuộc tính Path và Domain cũng cần khớp với cookie đã tạo; nếu không, trình duyệt có thể giữ lại cookie cũ. Spring Security mặc định thường hỗ trợ hủy session và xóa SecurityContext khi logout; cấu hình cần được điều chỉnh theo tên cookie và cách triển khai session store.

Đăng xuất bằng trình duyệt nên là request thay đổi trạng thái, thường là POST có CSRF protection. Không dùng GET để logout vì trình thu thập liên kết hoặc website khác có thể kích hoạt request ngoài ý muốn.

### 2.5. Đăng xuất trên mọi thiết bị

Xóa cookie trong trình duyệt hiện tại không tự động thu hồi các session khác của cùng người dùng. Nếu sản phẩm có tính năng “đăng xuất tất cả thiết bị”, máy chủ cần tìm và vô hiệu hóa những session liên quan hoặc tăng một phiên bản bảo mật mà các session cũ không còn hợp lệ.

Khi người dùng đổi mật khẩu, tài khoản bị khóa hoặc phát hiện credential bị lộ, hãy xác định rõ chính sách thu hồi phiên hiện có. Việc này thường cần hỗ trợ từ session registry hoặc session store tập trung.

## 3. Bảo vệ cookie phiên

Cookie phiên thường mang session identifier. Các thuộc tính cookie giúp trình duyệt giới hạn cách lưu và gửi mã định danh đó.

### 3.1. HttpOnly

HttpOnly ngăn JavaScript phía trình duyệt đọc cookie qua các API như document.cookie.

Lợi ích: nếu một đoạn script độc hại chạy trong trang, nó khó lấy trực tiếp giá trị cookie phiên bằng JavaScript.

Giới hạn: HttpOnly không ngăn XSS thực hiện hành động thay mặt người dùng. Script độc hại vẫn có thể gửi request cùng origin; trình duyệt vẫn tự đính kèm cookie phù hợp. Vì vậy, vẫn phải phòng chống XSS bằng output encoding, sanitization và Content Security Policy khi phù hợp.

### 3.2. Secure

Secure yêu cầu trình duyệt chỉ gửi cookie qua kết nối HTTPS. Nếu ứng dụng cho phép HTTP không mã hóa, session cookie có thể bị lộ khi truyền qua mạng.

Trong môi trường production, trang đăng nhập và toàn bộ phiên đã xác thực cần dùng HTTPS. Có thể dùng HTTP Strict Transport Security (HSTS) để yêu cầu trình duyệt ưu tiên HTTPS cho host sau khi đã nhận policy.

Secure không thay thế TLS. Cần cấu hình chứng chỉ hợp lệ, chấm dứt TLS đúng ranh giới và bảo vệ cả kết nối giữa reverse proxy với ứng dụng nếu mạng nội bộ không được tin cậy.

### 3.3. SameSite

SameSite kiểm soát khi nào trình duyệt gửi cookie trong ngữ cảnh điều hướng hoặc request cross-site.

| Giá trị | Hành vi khái quát | Trường hợp sử dụng |
|---|---|---|
| Strict | Hạn chế gửi cookie trong điều hướng cross-site | Ứng dụng có thể chấp nhận việc người dùng mở liên kết ngoài rồi chưa được nhận diện ngay |
| Lax | Cho phép một số điều hướng cấp cao an toàn, hạn chế nhiều request cross-site khác | Thường là điểm khởi đầu hợp lý cho session cookie của ứng dụng web |
| None | Cho phép gửi cookie trong ngữ cảnh cross-site | Cần khi kiến trúc thực sự cần cookie cross-site; bắt buộc Secure trên trình duyệt hiện đại |

SameSite là lớp phòng vệ bổ sung cho CSRF, không thay thế CSRF token và kiểm tra nguồn request. Các luồng đăng nhập liên kết, SSO hoặc tích hợp nhúng có thể cần cấu hình khác; hãy kiểm tra toàn bộ luồng redirect/callback trước khi chọn Strict hoặc None.

### 3.4. Path và Domain

- **Path** giới hạn đường dẫn request mà trình duyệt gửi cookie.
- **Domain** xác định host hoặc phạm vi host nhận cookie.

Nếu không cần chia sẻ cookie giữa các subdomain, hãy bỏ thuộc tính Domain để tạo host-only cookie. Không đặt Domain quá rộng như toàn bộ miền cha nếu các subdomain có mức độ tin cậy khác nhau.

Path không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host. Không dựa vào Path để cô lập các ứng dụng có quyền truy cập cùng origin.

### 3.5. Max-Age và Expires

Max-Age hoặc Expires xác định thời hạn lưu cookie ở trình duyệt. Cookie không có thời hạn rõ ràng thường được xem là cookie phiên của trình duyệt, nhưng hành vi khôi phục phiên có thể khác nhau giữa trình duyệt.

Thời hạn cookie và thời hạn session phía máy chủ là hai chính sách riêng. Cookie còn tồn tại không có nghĩa session phía máy chủ vẫn hợp lệ; session đã hết hạn thì server phải từ chối session identifier đó. Ngược lại, xóa cookie ở client không tự hủy session phía máy chủ nếu không có request logout hoặc cơ chế thu hồi.

### 3.6. Tên cookie với tiền tố __Host-

Trình duyệt hỗ trợ tiền tố __Host- với các điều kiện: cookie phải có Secure, Path=/ và không được có Domain. Điều này giúp giảm một số rủi ro cookie bị đặt từ subdomain hoặc phạm vi không mong muốn.

Ví dụ tên cookie có thể là __Host-SESSION khi môi trường và framework hỗ trợ cấu hình phù hợp. Nếu dùng tiền tố này, phải đáp ứng đủ các điều kiện; không chỉ đổi tên mà bỏ qua Secure hoặc Path.

### 3.7. Cấu hình cookie trong Spring Boot

Ví dụ cấu hình cho ứng dụng production chạy HTTPS, dùng session cookie host-only:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-SESSION
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Các thuộc tính trên cần được kiểm tra với phiên bản Spring Boot/Servlet container mà dự án đang dùng. Không khai báo Domain nếu muốn đáp ứng quy tắc host-only của tiền tố __Host-. Khi chạy local bằng HTTP, Secure cookie có thể không được gửi như môi trường production; không vì vậy mà tắt Secure trong production.

## 4. Session phía máy chủ nên lưu gì?

Session store là nơi giữ trạng thái phiên. Chỉ lưu dữ liệu cần thiết để duy trì trải nghiệm và bảo mật; không biến session thành một bản sao đầy đủ của hồ sơ người dùng hoặc cơ sở dữ liệu.

### 4.1. Dữ liệu có thể phù hợp

Tùy ứng dụng, session có thể chứa:

- SecurityContext hoặc tham chiếu đến trạng thái xác thực do framework quản lý.
- User ID hoặc định danh chủ thể đã xác thực.
- CSRF token hoặc trạng thái liên quan đến cơ chế CSRF.
- Locale hoặc một số tùy chọn giao diện.
- ID giỏ hàng tạm thời hoặc trạng thái quy trình nhiều bước.
- Thời điểm xác thực gần nhất hoặc thông tin quản lý phiên cần thiết.

Hãy ưu tiên lưu ID và tải dữ liệu nghiệp vụ mới nhất từ nguồn có thẩm quyền. Khi quyền người dùng hoặc trạng thái tài nguyên thay đổi, dữ liệu cache trong session không được làm cho ứng dụng tiếp tục cấp quyền cũ.

### 4.2. Không lưu dữ liệu nhạy cảm không cần thiết

Tránh lưu trong session:

- Mật khẩu dạng rõ hoặc bản sao thông tin xác thực.
- Access token, refresh token hoặc API key không cần thiết.
- Số thẻ thanh toán đầy đủ, CVV hoặc dữ liệu thanh toán nhạy cảm.
- Bí mật mã hóa, private key hoặc secret cấu hình.
- Toàn bộ hồ sơ cá nhân nếu chỉ cần User ID.
- Entity JPA lớn có quan hệ lazy hoặc trạng thái persistence.
- Dữ liệu biểu mẫu nhạy cảm lâu hơn thời gian cần thiết.

Nếu một token phải được lưu để gọi dịch vụ ngoài, hãy cân nhắc kho credential riêng có mã hóa, quyền truy cập hạn chế và cơ chế xoay vòng. Không dùng session như một kho bí mật tổng quát.

### 4.3. Session chỉ nên giữ trạng thái nhỏ và có vòng đời rõ

Không lưu một Entity JPA trong session rồi dùng lại qua nhiều request. Entity có thể trở nên stale, gắn với persistence context đã đóng, hoặc chứa quan hệ lớn. Lưu định danh cần thiết, rồi tải lại Entity trong transaction của request hiện tại.

Cũng không nên lưu một object mutable lớn mà nhiều request đồng thời có thể sửa. Một người dùng có thể mở nhiều tab; hai request từ cùng session vẫn có thể chạy đồng thời. Hãy thiết kế cập nhật session có kiểm soát và tránh phụ thuộc vào thứ tự request.

## 5. Lưu trữ session trong môi trường triển khai

### 5.1. Session trong bộ nhớ của một instance

Ứng dụng đơn instance có thể lưu session trong bộ nhớ của servlet container. Cách này đơn giản nhưng session có thể mất khi ứng dụng khởi động lại và không tự chia sẻ với instance khác.

Khi mở rộng nhiều instance, cần sticky session hoặc kho session dùng chung. Sticky session định tuyến cùng client về một instance, nhưng không giải quyết mọi vấn đề khi instance lỗi hoặc cần mở rộng linh hoạt.

### 5.2. Session store dùng chung

Có thể dùng Spring Session với Redis hoặc JDBC để nhiều instance đọc/ghi cùng session store.

Lợi ích:

- Session không phụ thuộc vào một instance ứng dụng.
- Có thể thu hồi phiên tập trung.
- Có thể áp dụng TTL và quản lý session theo người dùng.
- Hỗ trợ triển khai nhiều instance mà không cần giữ trạng thái trong từng process.

Kho session trở thành thành phần nhạy cảm. Cần giới hạn network access, xác thực, phân quyền, TLS, bảo vệ dữ liệu lưu trữ, backup và giám sát. Không mở Redis hoặc database session store ra Internet.

### 5.3. Thời hạn và dọn session

Session store cần TTL hoặc cơ chế dọn dữ liệu hết hạn. Nếu session hết hạn ở ứng dụng nhưng bản ghi trong store vẫn còn quá lâu, dữ liệu cũ có thể tồn tại không cần thiết.

TTL nên phù hợp với idle timeout và chính sách absolute timeout. Nếu dùng session registry để quản lý nhiều thiết bị, cần đồng bộ trạng thái giữa registry và store.

### 5.4. Mã hóa và phân quyền kho session

Dữ liệu session có thể chứa SecurityContext hoặc thông tin cá nhân. Hãy giới hạn ai có thể đọc kho session, mã hóa kết nối và dữ liệu lưu trữ theo mô hình đe dọa của hệ thống.

Mã hóa at-rest không thay thế access control. Một ứng dụng bị chiếm quyền với credential của session store vẫn có thể đọc hoặc sửa session. Cần quản lý secret kết nối riêng, xoay vòng credential và không ghi chúng vào source code.

## 6. Chống CSRF khi dùng cookie phiên

Trình duyệt tự gửi cookie theo domain, path và SameSite. Đặc tính này thuận tiện cho xác thực nhưng cũng tạo rủi ro Cross-Site Request Forgery (CSRF): một website khác có thể dụ trình duyệt đã đăng nhập gửi request đến ứng dụng mục tiêu.

### 6.1. Nguyên tắc chống CSRF

Với ứng dụng xác thực bằng cookie, hãy:

- Bật CSRF protection của framework cho các thao tác thay đổi trạng thái.
- Dùng POST, PUT, PATCH hoặc DELETE cho thao tác ghi; không thay đổi dữ liệu qua GET.
- Gửi CSRF token trong form hoặc header được server kiểm tra.
- Kiểm tra Origin/Referer khi phù hợp như một lớp phòng vệ bổ sung.
- Dùng SameSite phù hợp nhưng không coi nó là biện pháp duy nhất.
- Không cho phép CORS credentials từ origin tùy ý.

Spring Security bật CSRF protection cho các ứng dụng servlet theo cấu hình mặc định thông dụng. Không tắt CSRF chỉ vì ứng dụng có API; hãy đánh giá cách client xác thực và cơ chế token của từng endpoint.

### 6.2. Token trong biểu mẫu HTML

Một biểu mẫu POST cần gửi CSRF token mà server đã cấp. Ví dụ HTML khái niệm:

~~~html
<form method="post" action="/profile">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_CAP" />

  <label for="displayName">Tên hiển thị</label>
  <input id="displayName" name="displayName" />

  <button type="submit">Lưu</button>
</form>
~~~

Với Thymeleaf và tích hợp Spring Security, token có thể được thêm tự động vào form dùng th:action tùy cấu hình. Nếu tự dựng form hoặc dùng JavaScript, cần bảo đảm token được gửi đúng tên tham số hoặc header mà server mong đợi.

CSRF token không phải session identifier. Không dùng session cookie làm CSRF token và không đưa session ID vào HTML.

### 6.3. Request AJAX/fetch

Với request JavaScript, có thể đưa CSRF token vào header. Token được render vào trang theo cơ chế của framework, rồi JavaScript đọc giá trị token được cung cấp và gửi cùng request same-origin.

~~~javascript
async function saveProfile(payload, csrfToken) {
  const response = await fetch("/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error("Profile update failed");
  }
}
~~~

Tên header phụ thuộc cấu hình CSRF của ứng dụng. Không hardcode token lâu dài trong JavaScript bundle; token cần được cấp theo phiên hoặc theo cơ chế đã chọn.

### 6.4. Không dùng GET để thay đổi trạng thái

Các endpoint như /delete?id=42 hoặc /logout dùng GET có thể bị kích hoạt bởi liên kết, preview, crawler hoặc request cross-site. GET phải an toàn về mặt ngữ nghĩa: không tạo, xóa hoặc cập nhật trạng thái nghiệp vụ.

## 7. XSS và session hijacking

XSS và session hijacking có liên hệ chặt chẽ. Kẻ tấn công có thể dùng script injection để thực hiện hành động trong phiên của nạn nhân, hoặc tìm cách lấy credential phiên nếu cookie không được bảo vệ.

### 7.1. HttpOnly không chữa được XSS

HttpOnly ngăn JavaScript đọc cookie trực tiếp, nhưng script độc hại vẫn có thể gửi request cùng origin và đọc nội dung response mà người dùng có quyền truy cập. Vì vậy, cần:

- Escape dữ liệu động theo ngữ cảnh HTML.
- Sanitize HTML do người dùng nhập nếu sản phẩm cho phép rich text.
- Tránh chèn chuỗi không tin cậy vào script inline.
- Dùng Content Security Policy phù hợp.
- Cập nhật thư viện frontend và loại bỏ script không cần thiết.

### 7.2. Bảo vệ session khỏi bị đánh cắp

- Chỉ truyền session cookie qua HTTPS bằng Secure.
- Bật HttpOnly và SameSite phù hợp.
- Xoay session ID sau đăng nhập và thay đổi quyền.
- Không đưa session ID vào URL, log hoặc analytics.
- Không cho phép cache công khai trang đã xác thực.
- Có idle timeout và absolute timeout.
- Thu hồi session khi logout, đổi mật khẩu hoặc tài khoản bị khóa theo chính sách.
- Giám sát các dấu hiệu đăng nhập bất thường.

Session ID là bearer credential; không nên ghi nó vào log ngay cả khi đã hash một phần nếu không có nhu cầu điều tra rõ ràng. Nếu cần tương quan log, dùng một correlation ID riêng không có khả năng xác thực.

### 7.3. Không ràng buộc session cứng vào IP một cách máy móc

Địa chỉ IP có thể thay đổi do mạng di động, NAT, proxy hoặc chuyển vùng. Ràng buộc session vào IP tuyệt đối có thể làm người dùng hợp lệ bị đăng xuất và không phải biện pháp chống chiếm phiên đáng tin cậy trong mọi môi trường.

Có thể dùng IP, User-Agent và tín hiệu thiết bị như dữ liệu phát hiện bất thường, nhưng cần cân nhắc độ tin cậy, quyền riêng tư và khả năng thay đổi tự nhiên của các giá trị này.

## 8. Bảo vệ thông tin nhạy cảm ngoài session

Session chỉ là một nơi có thể lưu dữ liệu. Thông tin nhạy cảm còn xuất hiện trong form, request, response, log, cache, URL, tệp tải xuống và kho cấu hình.

### 8.1. Chỉ thu thập và trả dữ liệu cần thiết

DTO request/response nên chứa đúng trường cần cho ca sử dụng. Không serialize toàn bộ Entity hoặc đối tượng SecurityContext ra JSON. Với trang hồ sơ, chỉ trả tên hiển thị, email đã được phép xem và những trường giao diện cần.

### 8.2. Không đưa bí mật vào URL

Query string có thể xuất hiện trong browser history, reverse proxy log, analytics, referrer hoặc ảnh chụp màn hình. Không truyền password, access token, session ID, reset token hoặc dữ liệu thanh toán nhạy cảm trong URL.

Dùng body hoặc header theo hợp đồng giao thức phù hợp; vẫn cần TLS và kiểm soát log.

### 8.3. Bảo vệ log

Các header và trường cần được che hoặc loại khỏi log:

- Cookie và Set-Cookie.
- Authorization.
- CSRF token.
- Password và trường xác thực.
- Access token, refresh token và API key.
- Dữ liệu thanh toán và thông tin cá nhân nhạy cảm.

Không log toàn bộ request/response body một cách mặc định. Nếu cần audit, hãy ghi sự kiện nghiệp vụ và định danh cần thiết thay vì sao chép toàn bộ payload.

### 8.4. Cache trang có thông tin cá nhân

Trang hồ sơ, hóa đơn, dữ liệu tài khoản hoặc response có thông tin riêng tư thường cần chính sách cache nghiêm ngặt. Có thể trả:

~~~http
Cache-Control: no-store
~~~

Không dùng cache public cho nội dung phụ thuộc session hoặc quyền người dùng. Cũng cần kiểm tra cache tại reverse proxy, CDN và service worker; header ở ứng dụng không có tác dụng nếu tầng khác ghi đè sai chính sách.

### 8.5. Mã hóa và quản lý secret

Mật khẩu phải được lưu bằng password hashing phù hợp như Argon2id hoặc thuật toán được nền tảng bảo mật hỗ trợ, với salt riêng cho từng mật khẩu. Không mã hóa mật khẩu theo cách có thể giải mã rồi dùng lại như dữ liệu thông thường.

API key, private key và credential dịch vụ nên được quản lý bằng secret manager hoặc cơ chế cấu hình an toàn của môi trường triển khai. Không commit secret vào Git, không đưa vào image hoặc log, và có kế hoạch xoay vòng khi bị lộ.

## 9. Session cookie và JWT: không nhầm hai mô hình

Ứng dụng web có thể dùng session cookie truyền thống hoặc đặt token như JWT trong cookie. Việc token có định dạng JWT không tự động làm ứng dụng an toàn hơn.

| Khía cạnh | Session cookie phía máy chủ | JWT trong cookie |
|---|---|---|
| Giá trị cookie | Session identifier opaque | Token có claims và chữ ký |
| Trạng thái | Chủ yếu ở session store | Một phần trạng thái nằm trong token |
| Thu hồi | Có thể vô hiệu hóa session ở store | Cần expiry ngắn, denylist, version hoặc cơ chế thu hồi khác |
| Dữ liệu | Server quyết định dữ liệu session | Claims có thể đọc được nếu chỉ ký mà không mã hóa |
| CSRF | Cần phòng chống vì browser tự gửi cookie | Vẫn cần phòng chống nếu JWT nằm trong cookie tự động gửi |
| Phù hợp | Ứng dụng MVC cần logout và quản lý phiên tập trung | Một số kiến trúc phân tán có nhu cầu token rõ ràng |

JWT được ký không đồng nghĩa payload được mã hóa. Không đưa dữ liệu bí mật vào claims nếu token chỉ được ký. Token cũng là bearer credential: ai sở hữu token hợp lệ có thể sử dụng nó trong phạm vi quyền được cấp.

Nếu JWT nằm trong cookie, cần HttpOnly, Secure, SameSite và CSRF protection như cookie phiên. Nếu token được lưu trong localStorage, JavaScript có thể đọc token; XSS có thể lấy nó trực tiếp. Hãy chọn kiến trúc dựa trên nhu cầu thu hồi, thời hạn, tích hợp và mô hình đe dọa thay vì chỉ dựa vào xu hướng.

## 10. Cấu hình session trong Spring MVC/Security

Một cấu hình an toàn cần kết hợp cookie, vòng đời session, xác thực, CSRF và logout. Các phần dưới đây minh họa những cấu hình thường gặp; hãy xác nhận tên property và API theo phiên bản Spring Boot/Spring Security của dự án.

### 10.1. Thời hạn session và cookie

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-SESSION
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Session timeout là idle timeout do servlet container quản lý. Nếu cần absolute timeout, ứng dụng cần bổ sung thời điểm tạo phiên hoặc cơ chế quản lý thời hạn riêng; không giả định idle timeout tự thực hiện chính sách đó.

### 10.2. Session fixation và logout

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId())
        )
        .logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("__Host-SESSION")
        );

    return http.build();
}
~~~

CSRF protection được giữ theo cấu hình mặc định. Form logout nên gửi POST và có CSRF token. Nếu ứng dụng dùng tên cookie mặc định khác, hãy thay tên trong cấu hình xóa cookie cho khớp.

### 10.3. Không tự lưu thông tin xác thực vào HttpSession

Không viết mã tự lưu password hoặc token thô vào HttpSession. Hãy để Spring Security quản lý SecurityContext và dùng principal/Authentication để lấy danh tính đã xác thực. Session attribute của ứng dụng chỉ nên chứa dữ liệu ngắn hạn cần cho trải nghiệm.

### 10.4. Dùng session store phân tán

Nếu triển khai nhiều instance và cần session dùng chung, có thể cân nhắc Spring Session với Redis hoặc JDBC. Cần cấu hình TTL, bảo vệ kết nối, credential riêng, quyền truy cập tối thiểu và giám sát. Kiểm tra cách session được serialize; tránh lưu class không ổn định hoặc object quá lớn.

## 11. Các tình huống vận hành cần xử lý

### 11.1. Người dùng đóng trình duyệt

Cookie phiên có thể bị xóa khi trình duyệt đóng, nhưng một số trình duyệt có thể khôi phục session. Server-side session vẫn cần idle timeout và cleanup; không dựa vào việc đóng trình duyệt để thu hồi phiên.

### 11.2. Session hết hạn khi người dùng đang nhập biểu mẫu

Nếu session hết hạn trong lúc người dùng đang soạn form, request submit có thể nhận 401, redirect đến login hoặc lỗi CSRF tùy cấu hình. Giao diện nên thông báo rõ, giữ lại dữ liệu biểu mẫu không nhạy cảm khi có thể và yêu cầu đăng nhập lại.

Không lưu password, mã xác thực hoặc dữ liệu thanh toán trong bản nháp phía client để phục hồi form.

### 11.3. Người dùng đổi mật khẩu

Chính sách nên xác định có thu hồi các session hiện tại hay không. Với tài khoản có nguy cơ bị xâm phạm, thu hồi mọi phiên khác là lựa chọn an toàn. Session hiện tại có thể cần được làm mới hoặc yêu cầu đăng nhập lại.

### 11.4. Quyền người dùng thay đổi

Nếu người dùng bị gỡ vai trò hoặc tài khoản bị khóa, session cũ không nên tiếp tục cấp quyền dựa trên thông tin lỗi thời. Tùy yêu cầu, có thể tải quyền từ nguồn có thẩm quyền mỗi request, dùng security version hoặc thu hồi session khi quyền thay đổi.

### 11.5. Nhiều tab hoặc request đồng thời

Một session có thể được nhiều tab dùng chung. Các request có thể đến đồng thời và cập nhật cùng session attribute. Tránh dùng session như một nơi lưu trạng thái mutable phức tạp; nếu phải dùng, bảo đảm cập nhật nguyên tử hoặc lưu trạng thái nghiệp vụ trong database với concurrency control.

## 12. Kiểm thử bảo mật session và cookie

Không chỉ kiểm thử đăng nhập thành công. Cần kiểm tra thuộc tính cookie, vòng đời session, CSRF, logout và cách ứng dụng xử lý trạng thái hết hạn.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Đăng nhập thành công | Server tạo session và gửi cookie phiên |
| Sau đăng nhập | Session ID được thay đổi theo chính sách fixation protection |
| Cookie phiên | Có HttpOnly, Secure và SameSite phù hợp |
| Cookie host-only | Không có Domain nếu dùng tiền tố __Host- |
| Request HTTP không an toàn | Không gửi Secure cookie qua HTTP |
| POST thiếu CSRF token | Bị từ chối khi CSRF protection được bật |
| GET endpoint thay đổi dữ liệu | Không tồn tại hoặc không thay đổi trạng thái |
| Session idle timeout | Request tiếp theo yêu cầu xác thực lại |
| Logout | Session bị invalidate và cookie bị xóa |
| Đăng xuất mọi thiết bị | Các session khác bị thu hồi theo chính sách |
| User bị khóa | Session cũ không tiếp tục được cấp quyền |
| Response chứa dữ liệu riêng tư | Không bị cache public |
| Log request | Không chứa cookie, token hoặc password |
| XSS test | Dữ liệu không tin cậy được encode; HttpOnly không bị xem là biện pháp duy nhất |

### 12.1. Kiểm tra cookie trong integration test

Với Spring MVC, MockMvc có thể kiểm tra response đăng nhập hoặc endpoint tạo session:

~~~java
MvcResult result = mockMvc.perform(post("/login")
        .param("username", "demo")
        .param("password", "correct-password"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

Cookie sessionCookie = result.getResponse().getCookie("__Host-SESSION");

assertThat(sessionCookie).isNotNull();
assertThat(sessionCookie.isHttpOnly()).isTrue();
assertThat(sessionCookie.getSecure()).isTrue();
assertThat(sessionCookie.getPath()).isEqualTo("/");
~~~

Ví dụ cần được điều chỉnh theo cơ chế đăng nhập, tên cookie và phiên bản servlet container của dự án. MockMvc không thay thế việc kiểm tra hành vi thực tế của trình duyệt đối với SameSite, tiền tố cookie, TLS và redirect cross-site; cần có kiểm thử trình duyệt hoặc kiểm tra response header ở môi trường tích hợp.

### 12.2. Kiểm thử CSRF

Với Spring Security Test, có thể dùng request post kèm csrf() để kiểm tra đường hợp lệ và request thiếu token để xác nhận bị từ chối:

~~~java
mockMvc.perform(post("/profile")
        .with(user("demo"))
        .with(csrf())
        .param("displayName", "An"))
    .andExpect(status().is3xxRedirection());

mockMvc.perform(post("/profile")
        .with(user("demo"))
        .param("displayName", "An"))
    .andExpect(status().isForbidden());
~~~

Cần kiểm tra thêm form HTML thực tế đã render token và JavaScript gửi đúng header. Test chỉ gắn csrf() không chứng minh giao diện đã tích hợp token đúng.

## 13. Những lỗi thiết kế thường gặp

### Lưu session ID trong URL

URL có thể bị lưu trong history, log, referrer và analytics. Không truyền session identifier qua query string hoặc path.

### Tắt HttpOnly để JavaScript đọc cookie phiên

Frontend không cần đọc session ID để gửi request; trình duyệt tự gửi cookie. Tắt HttpOnly làm tăng khả năng đánh cắp credential khi có XSS.

### Chỉ dùng SameSite để chống CSRF

SameSite là một lớp phòng vệ, không thay thế token và thiết kế HTTP method an toàn. Các luồng cross-site hợp lệ cũng có thể cần cấu hình khác.

### Đặt Domain quá rộng

Cookie chia sẻ với nhiều subdomain làm tăng phạm vi tin cậy. Nếu không cần, hãy bỏ Domain và dùng host-only cookie.

### Không đổi session ID sau đăng nhập

Giữ identifier trước và sau xác thực có thể tạo điều kiện cho session fixation. Dùng cơ chế xoay ID của framework.

### Xóa cookie nhưng không hủy session phía máy chủ

Kẻ tấn công hoặc client khác vẫn có thể dùng session ID đã sao chép nếu server chưa thu hồi. Logout phải invalidate session ở server.

### Lưu password hoặc token thô trong session

Session store là dữ liệu nhạy cảm và có thể bị truy cập qua nhiều thành phần vận hành. Chỉ lưu trạng thái cần thiết và dùng kho secret/credential chuyên biệt khi cần.

### Tin quyền đã lưu lâu trong session

Vai trò hoặc trạng thái tài khoản có thể thay đổi. Request nhạy cảm cần kiểm tra quyền theo dữ liệu có thẩm quyền hoặc cơ chế thu hồi phù hợp.

### Log toàn bộ header và body

Cookie, Authorization và dữ liệu biểu mẫu có thể chứa credential hoặc PII. Che dữ liệu nhạy cảm trước khi log và giới hạn quyền truy cập log.

### Cho phép cache trang riêng tư

Cache ở browser, proxy hoặc CDN có thể làm lộ dữ liệu giữa người dùng. Đặt chính sách cache phù hợp và kiểm tra toàn bộ tầng phân phối.

## 14. Checklist bảo vệ session, cookie và thông tin nhạy cảm

1. Session identifier được tạo bởi framework/container với độ ngẫu nhiên phù hợp.
2. Session cookie có HttpOnly, Secure và SameSite theo mô hình sử dụng.
3. Cookie host-only nếu không cần chia sẻ subdomain; cân nhắc tiền tố __Host-.
4. Chỉ dùng HTTPS cho phiên đã xác thực và cấu hình HSTS phù hợp.
5. Session ID được đổi sau đăng nhập và khi nâng quyền theo chính sách.
6. Có idle timeout và absolute timeout phù hợp mức độ nhạy cảm.
7. Logout invalidate session phía máy chủ và xóa cookie đúng phạm vi.
8. Có cơ chế thu hồi session khác khi đổi mật khẩu, khóa tài khoản hoặc đăng xuất mọi thiết bị.
9. CSRF protection được bật cho request thay đổi trạng thái; GET không thay đổi dữ liệu.
10. Session chỉ chứa dữ liệu nhỏ, tối thiểu và có vòng đời rõ.
11. Session store được bảo vệ bằng network access control, credential, TLS và TTL.
12. Không lưu password, token hoặc dữ liệu thanh toán nhạy cảm nếu không cần.
13. Không đưa credential vào URL, log, analytics hoặc response HTML.
14. Trang riêng tư có cache policy phù hợp.
15. Có kiểm thử cookie attributes, fixation, timeout, logout, CSRF và thu hồi phiên.

## Kết luận

Session giúp ứng dụng MVC duy trì trạng thái giữa các request; cookie giúp trình duyệt mang session identifier về máy chủ. Vì session identifier là credential dạng bearer, ứng dụng phải bảo vệ cookie bằng HttpOnly, Secure, SameSite và phạm vi host phù hợp; xoay vòng ID sau xác thực; đặt thời hạn; hủy session ở phía máy chủ khi logout; và phòng chống CSRF, XSS cùng các hình thức rò rỉ thông tin.

Session store cần giữ dữ liệu tối thiểu, có quyền truy cập và thời hạn rõ ràng. Thông tin nhạy cảm phải được giảm thiểu trong request, response, log và cache. Khi các quy tắc này được thực hiện xuyên suốt từ View, Controller, Spring Security đến session store và hạ tầng triển khai, phiên đăng nhập sẽ khó bị chiếm dụng hơn và dữ liệu người dùng được bảo vệ tốt hơn.

