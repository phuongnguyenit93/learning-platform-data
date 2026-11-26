Câu 1. Trong ứng dụng web dùng cookie phiên, vì sao yêu cầu thay đổi dữ liệu có nguy cơ CSRF?
A. TLS tự chuyển mọi yêu cầu POST của người dùng thành GET.
B. Trình duyệt cấp quyền đọc cookie phiên cho mọi domain bên ngoài.
C. Cookie phiên vẫn được gửi với request do trang khác kích hoạt.
D. Máy chủ tự chia sẻ mật khẩu của người dùng với các trang khác.
Đáp án đúng: C

Câu 2. Với Spring Security Servlet và CSRF chưa được tùy biến, yêu cầu nào thường cần CSRF token?
A. Request POST cập nhật hồ sơ của người dùng đã đăng nhập.
B. Request GET xem trang thông tin sản phẩm của cửa hàng.
C. Request HEAD kiểm tra metadata của tài nguyên tĩnh.
D. Request OPTIONS truy vấn phương thức được hỗ trợ.
Đáp án đúng: A

Câu 3. Khi gửi một HTML form có CSRF protection, ứng dụng thường chuyển token về server bằng cách nào?
A. Đặt `_csrf` trong hidden input hoặc CSRF header của request.
B. Đặt token vào response cookie của trang đăng nhập sau POST.
C. Gửi password người dùng trong `Origin` header của request.
D. Đưa session ID vào query string rồi coi là CSRF token.
Đáp án đúng: A

Câu 4. `CookieCsrfTokenRepository.withHttpOnlyFalse()` có tác dụng trực tiếp gì?
A. Ghi CSRF token vào HTTP Basic credential thay cho cookie.
B. Tự động vô hiệu hóa CSRF cho mọi request dùng XMLHttpRequest.
C. Cho JavaScript phía client đọc CSRF token trong cookie.
D. Bảo đảm CSRF token không thể bị truy cập khi có XSS.
Đáp án đúng: C

Câu 5. API chỉ chấp nhận bearer token do client chủ động gắn vào Authorization header; nhận định nào về CSRF là hợp lý?
A. CSRF phải được kiểm tra bằng cùng token lưu trong HttpSession.
B. CSRF được vô hiệu tự động khi Access-Control-Allow-Origin là `*`.
C. CSRF được ngăn hoàn toàn nếu bearer token là JWT có chữ ký.
D. CSRF dựa vào cookie ít liên quan nếu không có credential tự gửi.
Đáp án đúng: D

Câu 6. Một webhook POST không dùng cookie phiên nhưng có cơ chế kiểm tra chữ ký riêng; nên cấu hình CSRF ra sao?
A. Tắt CSRF cho mọi route có method POST nhằm tránh lỗi 403.
B. Buộc webhook gọi GET để Spring không cần kiểm tra CSRF.
C. Bỏ CSRF cho route webhook nhưng vẫn kiểm tra chữ ký.
D. Thay xác minh chữ ký bằng việc thêm header Origin tùy ý.
Đáp án đúng: C

Câu 7. Trong Spring Security WebFlux, implementation nào lưu CSRF token trong WebSession?
A. `RequestCacheWebFilter` là kho lưu CSRF token mặc định.
B. `CookieCsrfTokenRepository` dùng riêng cho server WebFlux.
C. `WebSessionServerCsrfTokenRepository` dùng WebSession lưu token.
D. `HttpSessionCsrfTokenRepository` lưu token theo Reactor Context.
Đáp án đúng: C

Câu 8. Với CSRF đang bật, request POST dùng cookie phiên nhưng thiếu CSRF token hợp lệ thường nhận HTTP status nào?
A. 401 Unauthorized vì server bắt buộc gửi lại password qua Basic.
B. 403 Forbidden vì CSRF protection từ chối yêu cầu không hợp lệ.
C. 404 Not Found vì endpoint bị ẩn khi không có CSRF token.
D. 409 Conflict vì server coi thiếu CSRF token là conflict version.
Đáp án đúng: B

Câu 9. CORS của trình duyệt chủ yếu điều khiển hoạt động nào?
A. JavaScript của origin khác được phép đọc response hay không.
B. Session đã được xác thực bằng password hay OAuth2 token chưa.
C. Request có được phép thay đổi dữ liệu mà không kèm CSRF token.
D. Người dùng có đủ role để gọi HTTP endpoint nghiệp vụ hay không.
Đáp án đúng: A

Câu 10. Browser gửi CORS preflight khi nào trong một yêu cầu cross-origin không đơn giản?
A. Gửi POST kèm `If-Match` để kiểm tra resource còn mới.
B. Gửi HEAD kèm cookie phiên và tên HTTP method sắp gọi.
C. Gửi GET kèm `Authorization` chứa access token của client.
D. Gửi OPTIONS cùng `Origin` và `Access-Control-Request-Method`.
Đáp án đúng: D

Câu 11. Để preflight không bị từ chối do thiếu xác thực trong Spring Security Servlet, nên làm gì?
A. Tắt CORS rồi dùng `hasRole('USER')` cho OPTIONS request.
B. Buộc preflight gửi session cookie trước khi kiểm tra Origin.
C. Cấu hình CORS được xử lý trước authorization bằng `http.cors(...)`.
D. Đưa client secret vào `Access-Control-Request-Headers` của preflight.
Đáp án đúng: C

Câu 12. Server cho phép CORS request có credentials; response `Access-Control-Allow-Origin` nên thế nào?
A. Trả origin được chấp thuận cụ thể thay cho wildcard `*`.
B. Trả nhiều origin phân cách dấu phẩy trong một Allow-Origin.
C. Bỏ Allow-Origin nhưng trả Allow-Credentials cho request.
D. Trả wildcard `*` kèm Allow-Credentials để browser tự xử lý.
Đáp án đúng: A

Câu 13. Tại sao CORS không thể thay thế authorization trên REST API?
A. CORS giới hạn hành vi browser, còn API phải tự kiểm quyền caller.
B. CORS loại bỏ mọi request trực tiếp từ curl hoặc service backend.
C. CORS kiểm tra quyền resource thông qua JWT trước khi trả response.
D. CORS buộc trình duyệt ký request bằng quyền admin của ứng dụng.
Đáp án đúng: A

Câu 14. Với ứng dụng Spring WebFlux cần xử lý CORS trước WebFilter bảo mật, lựa chọn nào phù hợp?
A. Dùng `OncePerRequestFilter` để biến preflight thành Reactor event.
B. Dùng `HttpSessionCsrfTokenRepository` để phát CORS header.
C. Đăng ký `CorsWebFilter` cùng `CorsConfigurationSource` phù hợp.
D. Đăng ký `CorsFilter` của Servlet vào `DispatcherHandler` WebFlux.
Đáp án đúng: C

Câu 15. Preflight yêu cầu header `X-Custom` và phương thức PUT; server cần kiểm tra cấu hình nào?
A. JWT decoder chấp thuận signing algorithm của client.
B. Cho phép PUT và `X-Custom` trong methods/headers của CORS.
C. Session fixation strategy được đặt thành migrateSession.
D. CSRF repository lưu token có tên `X-Custom` trong cookie.
Đáp án đúng: B

Câu 16. Header `X-Content-Type-Options: nosniff` chủ yếu giúp hạn chế rủi ro gì?
A. Ngăn cookie được gửi trong HTTP request xuất phát từ trang khác.
B. Ngăn browser tự đoán MIME type khác với Content-Type đã khai báo.
C. Ngăn browser chuyển HTTP request từ HTTPS thành kết nối plaintext.
D. Ngăn iframe của origin khác nhúng trang web mà không xin phép.
Đáp án đúng: B

Câu 17. Khi server gửi `Strict-Transport-Security` qua HTTPS, trình duyệt được chỉ dẫn điều gì?
A. Ưu tiên HTTPS cho các lần truy cập tiếp theo trong thời hạn HSTS.
B. Tự thêm CSRF token vào mọi form ngay sau khi nhận HSTS header.
C. Gửi toàn bộ authorization token qua HTTP để tăng tốc truyền dữ liệu.
D. Bỏ qua kiểm tra chứng chỉ TLS nếu trang từng đăng nhập thành công.
Đáp án đúng: A

Câu 18. Trước khi thêm `includeSubDomains` vào HSTS, đội triển khai nên xem xét điều gì?
A. HSTS tự phát certificate cho subdomain chưa cấu hình.
B. Subdomain chưa có TLS vẫn hoạt động HTTP như trước.
C. Browser bỏ qua HSTS cho subdomain có login riêng.
D. Đảm bảo tất cả subdomain sẵn sàng phục vụ HTTPS hợp lệ.
Đáp án đúng: D

Câu 19. Về Content Security Policy (CSP) trong Spring Security, nhận định nào đúng?
A. CSP thay thế hoàn toàn việc escape dữ liệu để ngăn lỗ hổng XSS.
B. CSP cần cấu hình riêng, không được Spring bật đầy đủ mặc định.
C. CSP tự sinh nonce cho mỗi JavaScript khi chỉ bật CORS của ứng dụng.
D. CSP được Spring bật sẵn với `default-src 'none'` trên mọi response.
Đáp án đúng: B

Câu 20. Khi CSP khai báo `script-src 'self'` mà không có nonce hoặc hash, inline script sẽ thế nào?
A. Inline script tự được server gắn nonce từ HttpSession của user.
B. Inline script được phép nếu response có header Cache-Control.
C. Inline script được chạy vì source `'self'` cho phép mọi inline.
D. Inline script thông thường bị CSP chặn dù trang cùng origin.
Đáp án đúng: D

Câu 21. Với response `X-Frame-Options: DENY`, điều nào đúng về việc nhúng trang trong iframe?
A. Trang được nhúng nếu frame xuất phát từ cùng origin với trang.
B. Trang được nhúng nếu client có cookie phiên đã đăng nhập.
C. Trang được nhúng nếu iframe gửi đúng CORS preflight request.
D. Browser không cho phép nhúng trang vào iframe theo DENY.
Đáp án đúng: D

Câu 22. So với X-Frame-Options, chỉ thị CSP `frame-ancestors` cho phép triển khai điều gì?
A. Chặn script nội tuyến mà không ảnh hưởng đến việc nhúng frame.
B. Chỉ định cookie nào cần flag `HttpOnly` trên response.
C. Kiểm soát origin nào có thể nhúng trang bằng chính sách CSP.
D. Xác định URL tải CSS bên ngoài mà không kiểm tra iframe.
Đáp án đúng: C

Câu 23. Header `Referrer-Policy` chủ yếu dùng để bảo vệ thông tin gì?
A. Kiểm soát mức thông tin URL được đưa vào header Referer.
B. Kiểm soát danh sách CSRF token đã hết hạn của ứng dụng.
C. Kiểm soát chữ ký JWT của resource server khi gửi redirect.
D. Kiểm soát nơi lưu phiên đăng nhập phía server Servlet.
Đáp án đúng: A

Câu 24. Đối với trang trả dữ liệu nhạy cảm, `Cache-Control: no-store` nhằm mục đích gì?
A. `private` cấm cả browser cache lưu response được đánh dấu.
B. `max-age=0` khiến browser xóa cookie phiên đăng nhập.
C. `no-cache` cho cache tái sử dụng mà không cần revalidate.
D. Ngăn cache lưu lại response chứa dữ liệu nhạy cảm.
Đáp án đúng: D

Câu 25. Khi thử triển khai CSP nhưng muốn ghi nhận vi phạm mà chưa chặn nội dung, lựa chọn nào phù hợp?
A. Dùng header `X-Frame-Options: SAMEORIGIN` để chỉ ghi log.
B. Dùng header `Content-Security-Policy-Report-Only` để quan sát.
C. Dùng header `Strict-Transport-Security` có thời gian max-age ngắn.
D. Dùng header `X-Content-Type-Options: nosniff` để thu thập CSP.
Đáp án đúng: B

Câu 26. Với `StrictHttpFirewall` mặc định của Spring Security, đường dẫn chứa dấu chấm phẩy có thể gặp điều gì?
A. Semicolon được coi là ranh giới giữa request body và query params.
B. Request bị từ chối vì semicolon trong URL bị hạn chế mặc định.
C. Request được tự sửa thành URL bình thường rồi chuyển về controller.
D. Firewall tự xác thực user trước khi cho phép matrix variables.
Đáp án đúng: B

Câu 27. Khi mở `StrictHttpFirewall` để cho encoded slash đi qua, rủi ro gì cần đánh giá?
A. Khác biệt giải mã path có thể tạo sai lệch route match.
B. CORS mặc định cho tất cả origin vì URL đã được decode.
C. Spring tự tắt kiểm tra CSRF token trên endpoint có dấu slash.
D. Browser tự chuyển access token thành query string khi redirect.
Đáp án đúng: A

Câu 28. Trong Servlet authentication, biện pháp nào giảm nguy cơ session fixation sau khi đăng nhập?
A. Chỉ thêm header HSTS mà không thay đổi session identifier.
B. Đổi session ID sau đăng nhập, chẳng hạn `changeSessionId`.
C. Giữ nguyên ID session trước và sau đăng nhập để tránh mất cookie.
D. Chỉ đổi tên cookie session mà giữ ID phía server như cũ.
Đáp án đúng: B

Câu 29. Với API Servlet dùng bearer token và `SessionCreationPolicy.STATELESS`, ý nghĩa chính nào đúng?
A. Browser bị cấm gửi cookie qua HTTP vì chế độ stateless.
B. JWT tự bị thu hồi sau khi client đóng trang ứng dụng.
C. Security không dùng `HttpSession` để lưu `SecurityContext`.
D. Server tự động từ chối CSRF mà không cần cấu hình security.
Đáp án đúng: C

Câu 30. Muốn hạn chế một user Servlet chỉ có một phiên đăng nhập đồng thời, cấu hình nào phù hợp?
A. Giới hạn bằng `csrf().disable()` và CORS allowed origins.
B. Giới hạn bằng `SessionCreationPolicy.STATELESS` với form login.
C. Giới hạn bằng `header().frameOptions().deny()` trên mọi request.
D. Giới hạn bằng `maximumSessions(1)` và session registry phù hợp.
Đáp án đúng: D

Câu 31. Trong reactive WebFlux security, ngữ cảnh xác thực được truyền an toàn qua luồng Reactor bằng gì?
A. ThreadLocal cố định của thread Servlet đang xử lý request.
B. Cookie CSRF như kho lưu các GrantedAuthority của principal.
C. HttpServletRequest attribute của DispatcherServlet chính.
D. Reactor Context giữ SecurityContext qua luồng reactive.
Đáp án đúng: D

Câu 32. Muốn kiểm thử CSRF của POST endpoint trong Servlet và WebFlux, cách nào phù hợp?
A. Dùng MockMvc `with(user())` và WebTestClient `mockUser()` thay CSRF.
B. Dùng MockMvc `with(csrf())` và WebTestClient `mutateWith(csrf())`.
C. Dùng MockMvc `with(httpBasic())` và WebTestClient `mockJwt()` thay CSRF.
D. Dùng MockMvc `with(authentication())` và tắt SecurityWebFilterChain.
Đáp án đúng: B
