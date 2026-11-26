Câu 1. Trong ứng dụng Servlet, DelegatingFilterProxy thường làm gì với request HTTP?
A. Tự tìm controller MVC rồi gọi trực tiếp method @RequestMapping
B. Tạo Authentication đã được xác thực từ mọi request cookie
C. Chuyển lời gọi Filter tới bean Spring được cấu hình làm delegate
D. Ghi quyền của user vào database trước khi chạy FilterChain
Đáp án đúng: C

Câu 2. Bean tên springSecurityFilterChain thường đại diện cho thành phần nào?
A. DispatcherServlet ánh xạ URL sang RestController của ứng dụng
B. FilterChainProxy điều phối các SecurityFilterChain của ứng dụng
C. UsernamePasswordAuthenticationFilter lưu password của mọi user
D. SessionRegistry lưu toàn bộ thông tin user đang đăng nhập
Đáp án đúng: B

Câu 3. Nếu ứng dụng có nhiều SecurityFilterChain, FilterChainProxy xử lý thế nào?
A. Gộp filter của mọi chain khớp để chạy cùng một request
B. Chọn chain chứa nhiều filter nhất trong ApplicationContext
C. Luôn dùng chain được tạo gần nhất lúc khởi động server
D. Chọn SecurityFilterChain đầu tiên có matcher phù hợp request
Đáp án đúng: D

Câu 4. Khi nhiều SecurityFilterChain có matcher giao nhau, @Order hỗ trợ gì?
A. Sắp xếp độ ưu tiên các chain trước bước chọn chain khớp
B. Thay thế toàn bộ RequestMatcher bằng quyền của user hiện tại
C. Quyết định thứ tự controller được DispatcherServlet gọi
D. Cho phép nhiều chain gộp quyền bằng toán tử logic AND
Đáp án đúng: A

Câu 5. Một bean SecurityFilterChain được dựng từ HttpSecurity thường định nghĩa gì?
A. Cấu hình toàn bộ repository của ứng dụng để phân trang
B. Filter và chính sách bảo mật HTTP cho tập request phù hợp
C. Danh sách method Java được gọi trong mỗi Servlet handler
D. Mapping mọi HttpServletResponse sang entity lớp domain
Đáp án đúng: B

Câu 6. Trong HttpSecurity, securityMatcher("/api/**") chủ yếu có tác dụng gì?
A. Giới hạn những request được xét bởi SecurityFilterChain đó
B. Đặt quy tắc phân quyền cho từng API method controller
C. Đổi URL đăng nhập mặc định thành /api/login trên chain
D. Chỉ cho phép API trả response nếu request có Bearer token
Đáp án đúng: A

Câu 7. Trong authorizeHttpRequests, requestMatchers("/admin/**").hasRole("ADMIN") làm gì?
A. Chọn SecurityFilterChain nào được FilterChainProxy thực thi
B. Tự thêm ROLE_ADMIN vào Authentication lúc user đăng nhập
C. Yêu cầu role ADMIN khi request khớp /admin/** trong chain
D. Thay servlet mapping để URL /admin được chuyển tới JSP
Đáp án đúng: C

Câu 8. Nếu một request không khớp SecurityFilterChain nào, cần hiểu gì?
A. FilterChainProxy mặc định áp luật denyAll trên mọi URL lạ
B. Spring tự chuyển request sang chain gần đúng theo độ dài URL
C. Request bị chặn trước khi tới Servlet nếu không có session
D. Request đó không được chain Spring Security nào bảo vệ
Đáp án đúng: D

Câu 9. Khi cần đặt custom filter ngay trước một filter bảo mật đã biết, API nào phù hợp?
A. HttpSecurity.addFilterBefore với filter và class mốc
B. HttpSecurity.authorizeHttpRequests đặt thêm rule permitAll
C. HttpSecurity.securityMatcher với class của custom filter
D. HttpSecurity.sessionManagement đặt custom filter làm registry
Đáp án đúng: A

Câu 10. Nếu một custom Filter vừa là Servlet filter được auto-register vừa thêm vào SecurityFilterChain, rủi ro gì?
A. Spring sẽ tự xóa bean để bảo đảm filter chỉ chạy một lần
B. RequestMatcher tự biến thành allowAll với custom filter
C. Filter có thể chạy hai lần theo hai cơ chế đăng ký khác nhau
D. Tất cả AuthenticationProvider sẽ bị vô hiệu trong chain
Đáp án đúng: C

Câu 11. Khi muốn custom filter giới hạn chạy một lần trong một request dispatch thích hợp, lớp nền nào hữu ích?
A. GenericFilterBean luôn lưu SecurityContext vào session
B. FilterChainProxy tự bắt buộc mọi custom filter chạy một lần
C. OncePerRequestFilter hỗ trợ cơ chế đánh dấu đã lọc
D. DelegatingFilterProxy tự ghép mọi filter trùng class thành một
Đáp án đúng: C

Câu 12. SecurityContextHolder trong stack Servlet thường dùng để truy cập gì?
A. Danh sách mọi SecurityFilterChain đã cấu hình của ứng dụng
B. SecurityContext của thread đang thực thi request
C. SessionRegistry của tất cả user trên server hiện tại
D. JWT signing key được HttpSecurity dùng để phát hành token
Đáp án đúng: B

Câu 13. Thành phần chính mà SecurityContext giữ cho request đang xử lý là gì?
A. HttpServletResponse chứa header Authorization gửi về client
B. PasswordEncoder dùng để so plaintext của tất cả user
C. FilterInvocation chứa toàn bộ ServletContextListener
D. Authentication mô tả principal và authorities hiện tại
Đáp án đúng: D

Câu 14. SecurityContextRepository có vai trò gì trong bảo mật Servlet?
A. Chọn một AuthenticationProvider dựa trên username prefix
B. Sinh authorization code cho OAuth2 authorization server
C. Nạp và lưu SecurityContext giữa các request theo chính sách
D. Cập nhật mật khẩu hash của user sau mỗi lần GET request
Đáp án đúng: C

Câu 15. Với SecurityContextHolderFilter yêu cầu lưu tường minh, login custom muốn tồn tại qua request tiếp theo cần gì?
A. Chỉ setContext ở ThreadLocal rồi mặc định được persist mãi
B. Đặt Authentication vào request attribute rồi bỏ repository
C. Gọi HttpSession.invalidate sau khi login thành công
D. Lưu context bằng SecurityContextRepository.saveContext thích hợp
Đáp án đúng: D

Câu 16. Khi chạy tác vụ qua thread pool và cần mang SecurityContext của caller, cách nào phù hợp?
A. Dựa vào ThreadLocal mặc định tự truyền tới mọi pooled thread
B. Đặt userId vào tên thread để SecurityContextHolder tự tìm
C. Dùng @Order trên Executor bean để copy Authentication
D. Dùng DelegatingSecurityContextExecutor hoặc wrapper tương ứng
Đáp án đúng: D

Câu 17. AuthenticationManager.authenticate(token) khác AuthorizationManager ở điểm nào?
A. Cả hai đều cấp access token và quản lý refresh token mặc định
B. AuthenticationManager chỉ áp quyền, AuthorizationManager so password
C. Một bên xác thực credential; bên kia quyết định quyền truy cập
D. AuthorizationManager tạo HttpSession khi user vào login page
Đáp án đúng: C

Câu 18. ProviderManager thường xác định AuthenticationProvider xử lý token bằng gì?
A. Dựa vào tên controller đầu tiên có cùng request path
B. Dựa vào số lượng cookie mà request mang đến server
C. Dựa vào @Order của SecurityFilterChain sau khi đã login
D. Dựa vào supports và kết quả xác thực của các provider
Đáp án đúng: D

Câu 19. Khi bật formLogin theo mặc định, POST /login thường do filter nào xử lý?
A. UsernamePasswordAuthenticationFilter thu username và password
B. BearerTokenAuthenticationFilter đổi Bearer JWT thành form data
C. BasicAuthenticationFilter tự tạo login page HTML cho browser
D. AnonymousAuthenticationFilter đối chiếu raw password của user
Đáp án đúng: A

Câu 20. Khi tùy chỉnh loginPage("/signin"), điều nào cần lưu ý?
A. Spring tự sinh HTML trang /signin dựa trên mọi form field
B. Tự cung cấp trang GET /signin và cho phép user truy cập nó
C. Login page thay thế PasswordEncoder khi đăng nhập từ browser
D. Form có thể POST tới URL bất kỳ vì Spring tự tìm credential
Đáp án đúng: B

Câu 21. loginProcessingUrl("/auth/login") trong formLogin dùng vào việc gì?
A. Đổi URL trang HTML do ứng dụng hiển thị cho user
B. Chỉ định URL nhận credential POST của form login
C. Đổi tên bean AuthenticationManager đang dùng cho login
D. Đặt URL HTTP callback của OIDC authorization code
Đáp án đúng: B

Câu 22. Khi đăng nhập qua form thành công, thành phần nào thường quyết định redirect hoặc response?
A. AuthenticationFailureHandler quyết định redirect dù đã login
B. AccessDeniedHandler xử lý response sau xác thực thành công
C. CsrfTokenRepository kiểm tra authority trước khi redirect
D. AuthenticationSuccessHandler xử lý kết quả xác thực thành công
Đáp án đúng: D

Câu 23. Nếu mật khẩu không hợp lệ trong form login, handler nào xử lý phản hồi phù hợp?
A. AuthenticationSuccessHandler tạo SecurityContext cho password sai
B. AuthenticationFailureHandler xử lý response login sai
C. LogoutSuccessHandler ghi remember-me cookie khi login sai
D. AccessDeniedHandler cấp ROLE_USER thay vì ném exception
Đáp án đúng: B

Câu 24. Khi request chưa xác thực vào trang bắt buộc đăng nhập, ai thường bắt đầu authentication flow?
A. AuthenticationEntryPoint bắt đầu login hoặc trả HTTP 401
B. AccessDeniedHandler cấp thêm quyền rồi trả HTTP 200
C. RequestCache xóa tài khoản để yêu cầu đăng ký mới
D. LogoutFilter nhận credential để thực hiện login
Đáp án đúng: A

Câu 25. Khi user đã xác thực nhưng không đủ quyền cho URL, handler nào thường phản hồi?
A. AuthenticationSuccessHandler cấp thêm authority cho user
B. AccessDeniedHandler xử lý tình huống bị cấm như HTTP 403
C. AuthenticationEntryPoint mặc định luôn phát JWT mới
D. UsernamePasswordAuthenticationFilter tự tải lại role từ database
Đáp án đúng: B

Câu 26. ExceptionTranslationFilter thường được dùng để làm gì trong Servlet chain?
A. Tạo mới PasswordEncoder khi một request thiếu cookie session
B. Đổi exception xác thực hoặc từ chối quyền thành phản hồi HTTP
C. Tự xác minh JWT signature thay cho JwtAuthenticationProvider
D. Đăng ký client OAuth2 khi người dùng truy cập login form
Đáp án đúng: B

Câu 27. AuthorizationFilter chịu trách nhiệm chính cho phần nào của request?
A. Áp AuthorizationManager lên request và SecurityContext
B. Giải mã Basic Authorization trước khi AuthenticationManager chạy
C. Lưu SecurityContext xuống JDBC sau khi controller trả response
D. Sinh CSRF token dưới dạng access token cho client
Đáp án đúng: A

Câu 28. Với hasRole("ADMIN"), authority nào theo quy ước mặc định được kiểm tra?
A. ROLE_ADMIN trong GrantedAuthority của Authentication
B. ADMIN không có prefix trong claim userInfo của OIDC
C. SCOPE_ADMIN được tự ánh xạ thành ROLE_ADMIN khi login
D. PERMISSION_ADMIN được HttpSession cấp cho mọi user
Đáp án đúng: A

Câu 29. Vì sao permitAll() khác web.ignoring() đối với một URL đăng nhập?
A. permitAll bỏ toàn bộ filter như khi URL bị ignoring hoàn toàn
B. permitAll tự tắt CSRF trên mọi POST cùng prefix đường dẫn
C. permitAll vẫn chạy security filters, chỉ cho qua luật quyền
D. permitAll tự đặt SecurityContext của request là authenticated
Đáp án đúng: C

Câu 30. Khi có luật /admin/** và anyRequest(), nên sắp đặt thế nào?
A. anyRequest trước để các rule sau luôn được xét bổ sung
B. Hai rule sẽ cộng quyền nếu cùng khớp một request
C. Luật cụ thể chỉ hiệu lực khi đặt trong chain thứ hai
D. Luật cụ thể trước, anyRequest ở cuối tập quy tắc phân quyền
Đáp án đúng: D

Câu 31. Session fixation protection đổi session ID sau login chủ yếu bảo vệ khỏi gì?
A. Kẻ tấn công đoán BCrypt password hash thông qua API
B. Kẻ tấn công cố định session ID trước khi user xác thực
C. Nhà cung cấp OAuth2 thay đổi public key trong JWKS
D. Browser bị mất kết nối với resource server khi tải trang
Đáp án đúng: B

Câu 32. Muốn giới hạn session đồng thời cho mỗi tài khoản, tính năng nào phù hợp?
A. Dùng concurrent session control với maximumSessions
B. Đặt PasswordEncoder có work factor cao hơn cho mọi request
C. Giới hạn số endpoint trong từng SecurityFilterChain riêng
D. Cấu hình CSRF token tối đa một lần cho mọi account
Đáp án đúng: A

Câu 33. SessionCreationPolicy.STATELESS thông thường được hiểu như thế nào?
A. Ứng dụng không thể tạo cookie nào ở bất kỳ controller
B. Không dùng HttpSession để đọc/lưu SecurityContext
C. Tất cả bearer token được lưu trong session sau lần đầu
D. CSRF luôn được bật cho mọi endpoint bearer API không cookie
Đáp án đúng: B

Câu 34. Khi logout với form login có session, thao tác nào thường được cấu hình?
A. Đổi PasswordEncoder sang NoOpPasswordEncoder cho user
B. Giữ nguyên Authentication để request sau vẫn được phép
C. Hủy HttpSession và xóa SecurityContext qua logout handlers
D. Tự thu hồi mọi access token ở authorization server bên ngoài
Đáp án đúng: C

Câu 35. Nếu CSRF protection bật, Spring Security thường yêu cầu gì ở logout request?
A. Chỉ dùng HTTP GET vì GET tự động xoá session an toàn
B. Gửi Authorization Basic với credential của server
C. Dùng JWT có scope logout làm CSRF token mặc định
D. POST /logout cần CSRF token hợp lệ nếu bảo vệ CSRF bật
Đáp án đúng: D

Câu 36. Vì sao POST từ browser dùng session cookie cần CSRF protection?
A. Browser tự đặt header Authorization Bearer từ localStorage
B. TLS ngăn mọi request được gửi từ domain khác qua internet
C. Browser có thể tự gửi cookie khi website khác kích hoạt request
D. CSRF chỉ xảy ra khi browser lưu token ở query parameter
Đáp án đúng: C

Câu 37. CsrfFilter với cấu hình mặc định thường kiểm tra token trên loại HTTP method nào?
A. Chỉ GET và HEAD vì các method này truy vấn tài nguyên
B. Chỉ OPTIONS preflight do trình duyệt gửi trước CORS
C. Các method như POST, PUT, PATCH, DELETE cần CSRF token
D. Chỉ request chứa Authorization Bearer không có session
Đáp án đúng: C

Câu 38. Khi webhook POST không dùng cookie auth nhưng thuộc cùng chain, cấu hình nào hỗ trợ miễn CSRF đúng phạm vi?
A. Tắt mọi filter Spring Security của tất cả endpoint cùng ứng dụng
B. Dùng anyRequest().permitAll để bỏ CSRF mà không sửa cấu hình
C. Đặt @CrossOrigin cho webhook để CsrfFilter không kiểm tra
D. csrf.ignoringRequestMatchers cho đường dẫn webhook phù hợp
Đáp án đúng: D

Câu 39. Một SPA dùng cookie session và CSRF token cookie cần chú ý gì?
A. Chỉ cần đặt Content-Type JSON để CsrfFilter bỏ kiểm tra
B. SPA tự tạo token mới không liên quan token lưu ở server
C. Header token từ SPA cần khớp CsrfTokenRepository
D. Dùng JWT decoder để kiểm tra cookie CSRF như access token
Đáp án đúng: C

Câu 40. Vì sao CORS preflight cần được xử lý phù hợp trước bước xác thực Servlet?
A. Preflight chứa mã OAuth2 authorization code cho API
B. OPTIONS preflight thường không có cookie xác thực user
C. Preflight tự mang SecurityContextHolder của request chính
D. CorsFilter thay AuthenticationManager khi login qua form
Đáp án đúng: B

Câu 41. Để cấu hình allowed origins và methods cho Servlet CORS, thành phần nào hữu ích?
A. SecurityContextRepository tự tính Access-Control-Allow-Origin
B. CorsConfigurationSource cung cấp allowed origins và methods
C. PasswordEncoder so khớp HTTP Origin với BCrypt salt
D. SessionRegistry quản lý Access-Control-Allow-Methods
Đáp án đúng: B

Câu 42. CORS khác Authorization ở điểm nào trong ứng dụng Spring Security?
A. CORS cấp ROLE_USER cho origin được allow, authorization tạo cookie
B. CORS kiểm tra mật khẩu, còn authorization xử lý HTTP preflight
C. CORS điều phối browser cross-origin, còn authorization kiểm soát quyền
D. CORS thay CSRF protection cho mọi request có session cookie
Đáp án đúng: C

Câu 43. Trong cấu hình securityHeaders, HSTS hướng tới mục tiêu nào?
A. Yêu cầu browser ưu tiên HTTPS cho host theo chính sách HSTS
B. Tự kiểm tra password bằng TLS certificate mỗi HTTP request
C. Ngăn redirect sau form login bằng thay đổi ServletContext
D. Lưu SecurityContext trong JWT token của browser
Đáp án đúng: A

Câu 44. oauth2Login() trong HttpSecurity thường phù hợp với luồng nào?
A. oauth2Login hỗ trợ browser login qua Authorization Code
B. Kiểm tra opaque bearer token API bằng introspection mặc định
C. Phát hành access token do ứng dụng đóng vai authorization server
D. Xác thực HTTP Basic bằng id token qua form login filter
Đáp án đúng: A

Câu 45. Khi oauth2Login được cấu hình mặc định, URL nào thường bắt đầu redirect đến provider?
A. /login/oauth2/code/{registrationId} dùng để khởi tạo redirect
B. /api/oauth2/introspect dùng cho mọi browser login
C. /oauth2/token/{registrationId} tự tạo refresh token phía client
D. Dùng /oauth2/authorization/{registrationId} để bắt đầu login
Đáp án đúng: D

Câu 46. Trong oauth2Login mặc định, callback authorization code thường đến URL nào?
A. Callback mặc định là /login/oauth2/code/{registrationId}
B. /oauth2/authorization/{registrationId} để khởi tạo redirect mới
C. /logout/oauth2/code/{registrationId} để xóa cookie browser
D. /api/token/{registrationId} do JwtDecoder sinh ở resource server
Đáp án đúng: A

Câu 47. Khi cần bảo vệ riêng /api/** với Bearer JWT và web page với session, hướng nào phù hợp?
A. Tạo chain API và web riêng với matcher, thứ tự và policy
B. Dùng oauth2Login làm decoder Bearer JWT cho mọi request API
C. Bỏ securityMatcher để tất cả filter bắt buộc chạy hai lần
D. Bật formLogin để JwtDecoder tự xác minh JWT sau đăng nhập
Đáp án đúng: A

Câu 48. MockMvc test Servlet security nên làm gì để đánh giá cả filter và CSRF?
A. Bỏ filter chain rồi chỉ assert nội dung JSON trả về
B. Dùng @WithMockUser để kiểm chứng JWT signature đã được decode
C. Chỉ chạy unit test controller, không tạo request security
D. Áp dụng springSecurity(), gửi request với user và csrf() khi cần
Đáp án đúng: D
