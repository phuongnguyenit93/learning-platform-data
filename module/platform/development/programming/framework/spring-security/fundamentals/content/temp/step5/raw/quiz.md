Câu 1. Một bean SecurityFilterChain trong Spring Security thường xác định điều gì?
A. Các phương thức repository để load dữ liệu tài khoản
B. Khai các filter và chính sách bảo vệ HTTP request
C. Các controller mapping theo HTTP verb của ứng dụng
D. Các thuộc tính JPA entity cho bảng user nội bộ
Đáp án đúng: B

Câu 2. DelegatingFilterProxy trong Servlet container đóng vai trò gì?
A. Tự dựng Authentication từ toàn bộ request header đã đọc
B. Đăng ký tất cả endpoint @RequestMapping vào DispatcherServlet
C. Tự mã hóa cookie session trước khi trả về HTTP response
D. Chuyển xử lý Filter sang bean tương ứng trong Spring context
Đáp án đúng: D

Câu 3. Khi có nhiều SecurityFilterChain, FilterChainProxy thường chọn chain nào?
A. Tất cả chain khớp request và ghép filter theo thứ tự
B. Chain có nhiều AuthorizationManager nhất trong context
C. Chain được định nghĩa sau cùng trong file Java config
D. Chain đầu tiên có RequestMatcher khớp request đang xét
Đáp án đúng: D

Câu 4. Annotation @Order trên các SecurityFilterChain thường giúp gì?
A. Quy định độ ưu tiên khi các chain được xét để khớp request
B. Đặt thứ tự chạy các method @PreAuthorize của controller
C. Sắp xếp mật khẩu người dùng trước khi đưa vào encoder
D. Thay đổi thứ tự HTTP method trong DispatcherServlet
Đáp án đúng: A

Câu 5. Khác biệt giữa securityMatcher và requestMatchers trong authorizeHttpRequests là gì?
A. securityMatcher đặt role, requestMatchers chọn PasswordEncoder
B. securityMatcher chỉ dành cho JWT, requestMatchers chỉ cho session
C. securityMatcher chọn chain, requestMatchers đặt luật trong chain
D. securityMatcher bắt buộc dùng regex, requestMatchers chỉ dùng path
Đáp án đúng: C

Câu 6. Nếu một HTTP request không khớp SecurityFilterChain nào, điều gì cần lưu ý?
A. Spring tự tạo thêm chain mặc định cho riêng request đó
B. Request tự chuyển thành anonymous và bị HTTP 403 bắt buộc
C. FilterChainProxy sẽ chạy chain gần khớp path nhất
D. Request không qua Spring Security filter chain nào
Đáp án đúng: D

Câu 7. Quy tắc anyRequest().authenticated() trong authorizeHttpRequests thường yêu cầu gì?
A. Request phải mang authority ROLE_ADMIN mới được xử lý
B. Request phải có cookie JSESSIONID dù dùng bearer token
C. Request phải có principal được Spring xem là đã xác thực
D. Request bắt buộc được gửi từ browser thay vì API client
Đáp án đúng: C

Câu 8. Vì sao permitAll() khác việc loại đường dẫn khỏi web security?
A. permitAll bỏ mọi security filter như web.ignoring()
B. permitAll tự thay Authentication thành principal admin mặc định
C. Cho qua authorization nhưng vẫn chạy các security filter
D. permitAll tắt CSRF cho tất cả request POST trên đường dẫn
Đáp án đúng: C

Câu 9. Khi cấu hình hasRole("ADMIN"), authority nào thông thường được tìm?
A. Authority ROLE_ADMIN có trong Authentication hiện tại
B. ADMIN_ROLE được gắn trong tên HttpSession của browser
C. ROLE_USER do AuthenticationManager tạo mặc định cho user
D. ADMIN lấy từ trường username không qua GrantedAuthority
Đáp án đúng: A

Câu 10. Khi dùng hasAuthority("SCOPE_read"), điều kiện nào phù hợp?
A. Spring tự đổi SCOPE_read thành ROLE_SCOPE_read trước khi xét
B. SecurityContext cần có principal tên SCOPE_read bất kể role
C. Authentication cần authority có tên chính xác SCOPE_read
D. Request phải có HTTP header tên SCOPE_read của browser
Đáp án đúng: C

Câu 11. Khi khai luật requestMatchers cho URL cụ thể và anyRequest, cần lưu ý gì?
A. anyRequest nên đặt đầu để các luật sau tự được ưu tiên
B. Thứ tự luật không ảnh hưởng vì chúng đều được chạy
C. Tất cả luật requestMatchers luôn cộng dồn theo phép AND
D. Luật cụ thể nên được xét trước luật bao quát cuối cùng
Đáp án đúng: D

Câu 12. Để sử dụng @PreAuthorize tại service method, ứng dụng thường phải bật gì?
A. Method security như @EnableMethodSecurity trong cấu hình
B. Chỉ @EnableTransactionManagement trên mọi service bean
C. Chỉ thêm @RestController trên method cần phân quyền
D. Chỉ bật formLogin trên SecurityFilterChain bất kỳ
Đáp án đúng: A

Câu 13. @PreAuthorize("hasAuthority('invoice:read')") bảo vệ service method thế nào?
A. Tự gán authority invoice:read cho user nếu chưa có
B. Mã hóa kết quả method để chỉ invoice service giải mã
C. Kiểm tra authority trước khi cho method được thực thi
D. Chỉ áp dụng kiểm tra sau khi method trả giá trị thành công
Đáp án đúng: C

Câu 14. Trong Spring Security, phân biệt Authentication và Authorization thế nào?
A. Authentication quyết định quyền; Authorization kiểm tra mật khẩu
B. Authentication chọn security filter; Authorization lưu HttpSession
C. Authentication gửi redirect; Authorization tự tạo user database
D. Authentication xác minh danh tính; Authorization quyết định quyền
Đáp án đúng: D

Câu 15. Sau xác thực thành công, Authentication thường mang thông tin nào?
A. Principal, authorities và trạng thái authenticated
B. URL hiện tại, HTTP response status và TLS certificate
C. Cấu hình SecurityFilterChain cùng thứ tự @Order
D. Danh sách session cookie của mọi user trong hệ thống
Đáp án đúng: A

Câu 16. Một SecurityContext thường giữ thành phần gì để dùng trong xử lý request?
A. Danh sách tất cả HttpServletRequest từng được xử lý
B. Authentication của chủ thể trong ngữ cảnh hiện tại
C. PasswordEncoder mặc định của Spring ApplicationContext
D. Một bản sao của mỗi SecurityFilterChain đã đăng ký
Đáp án đúng: B

Câu 17. SecurityContextHolder mặc định trong Servlet app thường gắn SecurityContext với đâu?
A. Database connection đang dùng bởi service method
B. HttpSession toàn cục dùng chung cho mọi tài khoản
C. Reactor Context trên mỗi event-loop của Spring MVC
D. Thread đang xử lý bằng chiến lược ThreadLocal
Đáp án đúng: D

Câu 18. Trong ứng dụng dùng phiên đăng nhập, SecurityContextRepository giúp gì?
A. Tự cấp GrantedAuthority cho mọi session mới tạo
B. Nạp và lưu SecurityContext theo cấu hình repository
C. Giải mã password hash thành plaintext cho lần login sau
D. Chọn SecurityFilterChain có đường dẫn URL ngắn nhất
Đáp án đúng: B

Câu 19. AuthenticationManager.authenticate(token) thông thường nhận và trả về gì?
A. Nhận URL path, trả RequestMatcher phù hợp với filter
B. Nhận Authentication đề nghị, trả kết quả đã xác thực
C. Nhận CSRF token, trả HTTP response cho browser
D. Nhận SecurityContext, trả danh sách session ID đang hoạt động
Đáp án đúng: B

Câu 20. Với nhiều AuthenticationProvider, ProviderManager thường điều phối ra sao?
A. Thử provider hỗ trợ kiểu Authentication được cung cấp
B. Chỉ chọn provider có bean name trùng với login form
C. Gộp tất cả authorities trước khi kiểm tra credentials
D. Dùng provider cuối cùng bất kể supports trả false
Đáp án đúng: A

Câu 21. UserDetailsService.loadUserByUsername chủ yếu giải quyết việc gì?
A. So sánh raw password và encrypted password ở controller
B. Tự tạo JWT access token cho toàn bộ user trong database
C. Đăng ký remember-me cookie cho mọi lần GET request
D. Tải UserDetails theo username phục vụ authentication
Đáp án đúng: D

Câu 22. PasswordEncoder.matches(raw, encoded) được dùng đúng trong trường hợp nào?
A. Giải mã password BCrypt để lấy lại mật khẩu ban đầu
B. Đối chiếu mật khẩu nhập với hash đã lưu theo encoder
C. Tự đổi role của user khi đăng nhập bằng formLogin
D. Dùng raw password làm CSRF token cho browser session
Đáp án đúng: B

Câu 23. Vì sao BCrypt thường phù hợp cho việc lưu password hơn SHA-256 thuần?
A. Có salt và work factor làm tăng chi phí dò mật khẩu
B. Tự phát hành access token để user không cần session
C. Cho phép phục hồi raw password khi tài khoản quên
D. Bảo đảm hai lần hash cùng mật khẩu ra giá trị y hệt
Đáp án đúng: A

Câu 24. Một mật khẩu lưu dạng {bcrypt}... với DelegatingPasswordEncoder nói lên điều gì?
A. Prefix đã xác nhận user sở hữu ROLE_BCRYPT trên server
B. Prefix xác định encoder id bcrypt để kiểm tra password
C. Prefix là tên LDAP group phải được gán vào session
D. Prefix chỉ là comment, encoder phải đoán thuật toán hash
Đáp án đúng: B

Câu 25. Với formLogin mặc định, POST /login thường được xử lý bởi filter nào?
A. BearerTokenAuthenticationFilter đọc username từ form cookie
B. AnonymousAuthenticationFilter kiểm tra password từ session
C. UsernamePasswordAuthenticationFilter nhận form POST /login
D. AuthorizationFilter tự tạo UsernamePasswordAuthenticationToken
Đáp án đúng: C

Câu 26. Trong HTTP Basic authentication, phần credential được mang thế nào?
A. Authorization Bearer chứa ID token đã ký cho mỗi request
B. Header Authorization Basic mang Base64(username:password)
C. Cookie JSESSIONID được dùng thay cho Authorization header
D. X-CSRF-TOKEN chứa hash password dưới dạng hex string
Đáp án đúng: B

Câu 27. Để tùy chỉnh điều hướng sau khi đăng nhập form thành công, dùng gì?
A. AuthenticationFailureHandler quyết định response khi success
B. AuthenticationSuccessHandler quyết định response sau success
C. AccessDeniedHandler bắt mọi success của AuthenticationManager
D. CsrfTokenRequestHandler tạo URL redirect cho login success
Đáp án đúng: B

Câu 28. Khi một request chưa đăng nhập bị chặn bởi luật authenticated(), thành phần nào thường phản hồi?
A. AccessDeniedHandler tự cấp anonymous role để thử lại
B. PasswordEncoder sinh user account rồi redirect tới home
C. AuthenticationEntryPoint khởi động xác thực hoặc trả 401
D. SecurityContextHolder tạo mới HttpSession và cấp role user
Đáp án đúng: C

Câu 29. Khi user đã xác thực nhưng thiếu quyền truy cập tài nguyên, thành phần nào thường xử lý?
A. AuthenticationSuccessHandler đăng nhập lại bằng session cũ
B. AuthenticationEntryPoint luôn cấp thêm role được yêu cầu
C. LogoutSuccessHandler xóa account của user trong database
D. AccessDeniedHandler tạo phản hồi bị từ chối như HTTP 403
Đáp án đúng: D

Câu 30. ExceptionTranslationFilter trong filter chain chủ yếu làm gì?
A. Chuyển exception xác thực và phân quyền thành xử lý HTTP
B. Tải UserDetails rồi kiểm tra mật khẩu bằng BCrypt encoder
C. Lưu GrantedAuthority của mọi user vào SessionRegistry
D. Đọc JWT claims rồi tạo Authentication trên resource server
Đáp án đúng: A

Câu 31. Khi SecurityContext chứa anonymous Authentication, nhận định nào phù hợp?
A. Có token anonymous nhưng không xem là đăng nhập thực sự
B. AnonymousAuthenticationToken tương đương user đã nhập password
C. Anonymous user được tự cấp ROLE_ADMIN nếu thiếu principal
D. SecurityContext không thể có Authentication trong anonymous flow
Đáp án đúng: A

Câu 32. Session fixation protection đổi session ID sau đăng nhập nhằm mục đích gì?
A. Tự gia hạn thời gian sống của JWT trên mọi browser
B. Chuyển cookie session thành bearer token của resource server
C. Lưu password hash mới vào database sau mỗi lần login
D. Giảm nguy cơ kẻ tấn công cố định session ID trước login
Đáp án đúng: D

Câu 33. Cấu hình SessionCreationPolicy.STATELESS thường tác động gì tới Spring Security?
A. Bắt buộc xóa mọi cookie ứng dụng trên từng HTTP response
B. Không dùng HttpSession để lấy hay lưu SecurityContext
C. Tạo HttpSession mới mỗi lần xác thực bearer token
D. Cấm HTTP Basic vì mọi request phải có session cookie
Đáp án đúng: B

Câu 34. Muốn giới hạn số phiên đồng thời của một tài khoản, nên cấu hình gì?
A. PasswordEncoder với số vòng BCrypt phù hợp session count
B. Concurrent session control với maximumSessions thích hợp
C. CSRF token repository lưu đúng một token trên mỗi ứng dụng
D. JwtDecoder có danh sách cookie phiên của browser
Đáp án đúng: B

Câu 35. Khi logout qua Spring Security với session login, điều gì thường được cấu hình?
A. Invalidate session và xóa SecurityContext theo logout handlers
B. Giữ nguyên Authentication và chỉ chuyển người dùng về /login
C. Đổi toàn bộ password hash của user thành giá trị mới
D. Thu hồi mọi refresh token ở provider bên ngoài mặc định
Đáp án đúng: A

Câu 36. Tại sao CSRF là rủi ro đáng quan tâm với ứng dụng đăng nhập bằng cookie?
A. Browser luôn tự thêm Authorization Bearer từ localStorage
B. CSRF chỉ xảy ra khi mật khẩu dùng SHA-256 thay BCrypt
C. Cookie tự gửi khiến request từ site khác có thể lợi dụng
D. HTTPS tự vô hiệu mọi request cross-site có cookie
Đáp án đúng: C

Câu 37. Một ứng dụng dùng cookie session cho phép POST thay đổi dữ liệu nên áp dụng gì?
A. Chỉ dùng PasswordEncoder.matches trên request POST
B. Dùng CSRF token cho thao tác thay đổi trạng thái
C. Tắt CSRF để session cookie được gửi về server
D. Chỉ yêu cầu X-Requested-With mà bỏ CSRF validation
Đáp án đúng: B

Câu 38. Trong thiết kế HTTP đúng chuẩn, GET lấy dữ liệu nên có đặc điểm nào hỗ trợ chống CSRF?
A. Xóa user session sau mỗi lần GET được xử lý
B. Bắt buộc đổi password hash ở từng GET request
C. Dùng cùng một CSRF token làm query parameter cho GET
D. GET không tạo side effect đổi trạng thái nghiệp vụ
Đáp án đúng: D

Câu 39. Một SPA gọi API với cookie session cần gửi CSRF token theo cách nào?
A. Lấy mật khẩu user từ cookie rồi đưa vào Authorization Basic
B. Chỉ thêm Content-Type: application/json là đủ an toàn
C. Đọc token qua cơ chế server cấp và gửi ở header phù hợp
D. Tự đặt chuỗi ngẫu nhiên không liên quan token server lưu
Đáp án đúng: C

Câu 40. CORS và CSRF khác nhau ở điểm chính nào?
A. CORS giới hạn đọc cross-origin; CSRF chống request giả mạo
B. CORS xác minh user password, CSRF chọn AuthenticationProvider
C. CORS giữ SecurityContext trong session, CSRF giải mã JWT
D. CORS chỉ áp dụng JDBC, CSRF chỉ áp dụng OAuth2 login
Đáp án đúng: A

Câu 41. Khi bật HTTP Basic, vì sao nên dùng HTTPS?
A. Base64 làm password tự xuất hiện trong server log
B. Base64 không mã hóa credential trên đường truyền
C. HTTPS thay AuthenticationManager khi kiểm tra mật khẩu
D. HTTPS chuyển Basic credentials thành JWT được ký
Đáp án đúng: B

Câu 42. HSTS trong bảo vệ HTTP thường có mục đích gì?
A. Yêu cầu browser dùng HTTPS cho host theo chính sách
B. Bắt browser phải gửi CSRF token trên mỗi HTTP GET
C. Tự bổ sung quyền ROLE_ADMIN cho phiên HTTPS
D. Tự đổi mọi cookie không an toàn thành JWT bearer
Đáp án đúng: A

Câu 43. Với Content-Security-Policy trong Spring Security, nhận định nào đúng?
A. Spring tự tạo CSP hoàn chỉnh từ tất cả controller hiện tại
B. CSP thay cho CSRF token ở mọi request cập nhật dữ liệu
C. CSP cần cấu hình riêng theo chính sách ứng dụng
D. CSP tự cấu hình OAuth2 authorization code cho login
Đáp án đúng: C

Câu 44. Để xác thực Bearer JWT trên REST API bằng Spring Security, hướng nào phù hợp?
A. Bật formLogin và mặc định đọc JWT từ UsernamePasswordFilter
B. Bật OAuth2 Login để mọi Bearer token thành browser session
C. Dùng CSRF token repository để giải chữ ký JWT từ client
D. Cấu hình OAuth2 Resource Server JWT với JwtDecoder phù hợp
Đáp án đúng: D

Câu 45. Khi resource server nhận JWT đã hết hạn nhưng chữ ký đúng, xử lý nào hợp lý?
A. Cho token qua vì chữ ký RSA đã xác minh thành công
B. Tự sửa payload exp mà không ký JWT lại rồi cho qua
C. Bác token do claim exp không còn hợp lệ tại thời điểm xác minh
D. Lấy password của user để thay claim exp đã hết hạn
Đáp án đúng: C

Câu 46. oauth2Login() khác oauth2ResourceServer().jwt() điển hình ở điểm nào?
A. oauth2Login cho browser; resourceServer().jwt cho bearer API
B. Cả hai cùng thay PasswordEncoder bằng một JWT generator
C. oauth2Login chỉ kiểm tra Basic header của request tới API
D. resourceServer().jwt chỉ dùng để mở redirect trang login
Đáp án đúng: A

Câu 47. Để test controller có áp dụng luật Spring Security, MockMvc nên được thiết lập ra sao?
A. Tắt filter chain để chỉ kiểm tra tên @PreAuthorize đã khai
B. Mock controller mà không dùng WebApplicationContext hoặc filters
C. Chỉ kiểm tra JSON body và bỏ qua HTTP 401/403
D. Chạy security filters và assert status theo quyền user
Đáp án đúng: D

Câu 48. Trong MockMvc test một POST có CSRF protection đang bật, cách nào thường phù hợp?
A. Chỉ đặt @WithMockUser rồi bỏ qua CSRF token trong request
B. Tắt hết Spring Security filters để request POST thành công
C. Dùng .with(csrf()) cho POST khi CSRF protection bật
D. Chỉ thêm cookie JSESSIONID mà không gửi CSRF token
Đáp án đúng: C
