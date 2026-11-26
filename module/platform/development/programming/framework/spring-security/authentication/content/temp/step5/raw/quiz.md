Câu 1. Trong Spring Security, một Authentication sau xác thực thành công thường mang những gì?
A. URL request, HTTP status và servlet response hiện tại
B. Tên SecurityFilterChain và các request matcher đã khớp
C. Principal, authorities và cờ authenticated của request
D. AuthenticationEntryPoint và cấu hình session timeout
Đáp án đúng: C

Câu 2. AuthenticationManager.authenticate(Authentication) dùng để làm gì?
A. Xác thực credential rồi trả Authentication kết quả
B. Tự lưu HttpSession và trả SessionAuthenticationStrategy
C. Kiểm tra @PreAuthorize cho từng method của controller
D. Tạo password hash rồi ghi UserDetails vào repository
Đáp án đúng: A

Câu 3. Khi ProviderManager có nhiều AuthenticationProvider, nó thường chọn cách nào?
A. Chọn provider hỗ trợ token để thực hiện xác thực
B. Chạy tất cả provider theo thứ tự và gộp principal
C. Chỉ dùng provider đầu tiên dù supports trả false
D. Chọn provider dựa trên tên bean trùng tên username
Đáp án đúng: A

Câu 4. AuthenticationProvider.supports(Class) trả true biểu thị điều gì?
A. Provider đã xác minh password của tài khoản vừa gửi
B. Provider đã lưu SecurityContext vào repository session
C. Provider có thể xử lý kiểu Authentication được truyền
D. Provider tự cho phép mọi authority của principal đó
Đáp án đúng: C

Câu 5. Để kiểm tra username/password bằng UserDetailsService, provider nào phù hợp?
A. JwtAuthenticationProvider đọc UserDetails qua Cookie
B. AnonymousAuthenticationProvider truy vấn password hash
C. DaoAuthenticationProvider kết hợp dữ liệu user với encoder
D. RememberMeAuthenticationProvider so BCrypt với input
Đáp án đúng: C

Câu 6. UserDetailsService.loadUserByUsername chủ yếu chịu trách nhiệm gì?
A. So sánh raw password và set SecurityContext của request
B. Lấy UserDetails cho username để provider dùng khi xác thực
C. Đăng nhập user bằng OIDC ID token qua browser redirect
D. Tạo access token mới cho mọi request HTTP đã xác thực
Đáp án đúng: B

Câu 7. Với mật khẩu đã được mã hóa, PasswordEncoder.matches(raw, encoded) giúp gì?
A. So sánh raw password với encoded password bằng encoder
B. Giải mã BCrypt thành plaintext rồi đối chiếu hai chuỗi
C. Tạo mật khẩu mới bằng cách ghép username với raw input
D. Chỉ kiểm tra độ dài raw password so với hash đã lưu
Đáp án đúng: A

Câu 8. Một chuỗi password lưu với tiền tố {bcrypt} khi dùng DelegatingPasswordEncoder cho biết gì?
A. User đã đăng nhập và được tự cấp role tên bcrypt
B. Password được encrypt bằng một khóa lưu trong HttpSession
C. Spring sẽ bỏ qua đối chiếu mật khẩu vì đã có prefix
D. Chọn encoder BCrypt theo id ghi trước password hash
Đáp án đúng: D

Câu 9. Vì sao BCrypt thích hợp để lưu mật khẩu hơn SHA-256 thuần không salt?
A. Cho phép khôi phục password gốc khi user quên mật khẩu
B. Tự thêm MFA cho mọi lần AuthenticationManager gọi
C. BCrypt dùng salt và chi phí tính toán điều chỉnh được
D. Đảm bảo cùng password luôn tạo một chuỗi hash giống hệt
Đáp án đúng: C

Câu 10. Nếu UserDetails.isAccountNonLocked() trả false, provider chuẩn cần xử lý thế nào?
A. Từ chối đăng nhập vì tài khoản đang ở trạng thái khóa
B. Bỏ qua kiểm tra password nhưng trả principal đã login
C. Tự thêm role UNLOCKED cho principal sau khi bind
D. Lưu SecurityContext trước rồi mới kiểm tra tài khoản
Đáp án đúng: A

Câu 11. ProviderManager thường gọi eraseCredentials sau khi xác thực thành công để làm gì?
A. Làm mất GrantedAuthority để request không thể phân quyền
B. Xóa password hash gốc khỏi user database ngay sau login
C. Xóa HttpSession của mọi user sau mỗi request thành công
D. Giảm lưu giữ secret trong Authentication đã xác thực
Đáp án đúng: D

Câu 12. Trước khi provider kiểm chứng mật khẩu, UsernamePasswordAuthenticationToken nên có trạng thái nào?
A. Token authenticated=true để tránh truy vấn UserDetailsService
B. Token chưa được xác thực và chứa credential cần kiểm tra
C. Token mang GrantedAuthority admin lấy từ login form
D. Token được lưu vào HttpSession trước AuthenticationManager
Đáp án đúng: B

Câu 13. Trong form login servlet mặc định, filter nào thường xử lý POST /login?
A. BearerTokenAuthenticationFilter đọc Authorization Basic header
B. BasicAuthenticationFilter xử lý OAuth2 authorization code
C. UsernamePasswordAuthenticationFilter xử lý form POST /login
D. AnonymousAuthenticationFilter nhận username/password từ form
Đáp án đúng: C

Câu 14. Với AuthenticationFilter tùy chỉnh, AuthenticationConverter có nhiệm vụ nào?
A. Lưu Authentication đã xác thực xuống cơ sở dữ liệu user
B. Chuyển request thành Authentication token chưa xác thực
C. Chuyển AccessDeniedException thành HTTP 403 response
D. Ánh xạ GrantedAuthority thành cookie remember-me
Đáp án đúng: B

Câu 15. Sau khi form authentication thành công, handler nào thường quyết định hành vi điều hướng?
A. AuthenticationEntryPoint xử lý mọi response sau khi login
B. AuthenticationSuccessHandler xử lý kết quả đăng nhập thành công
C. AccessDeniedHandler xử lý redirect sau khi login thành công
D. AuthenticationFailureHandler tạo redirect sau khi login đúng
Đáp án đúng: B

Câu 16. Nếu provider ném BadCredentialsException trong form login, thành phần nào thường xử lý kết quả?
A. AuthenticationSuccessHandler tạo SecurityContext thành công
B. LogoutSuccessHandler xóa SecurityContext rồi trả response
C. RequestCacheAwareFilter tự sinh principal fallback
D. AuthenticationFailureHandler định nghĩa phản hồi thất bại
Đáp án đúng: D

Câu 17. Khi HTTP Basic được bật, filter nào thường nhận thông tin Basic credentials?
A. BasicAuthenticationFilter đọc header Authorization Basic
B. UsernamePasswordAuthenticationFilter chỉ đọc OAuth2 code
C. BearerTokenAuthenticationFilter chỉ nhận Basic password
D. CsrfFilter tự giải mã Base64 để xác thực username
Đáp án đúng: A

Câu 18. Một request chưa xác thực truy cập trang yêu cầu login, AuthenticationEntryPoint thường làm gì?
A. Giải quyết request đã xác thực nhưng thiếu quyền với HTTP 403
B. Bắt đầu cơ chế đăng nhập hoặc trả HTTP 401 phù hợp
C. Ghi một principal ẩn danh vào UserDetailsService
D. Xác minh quyền bằng cách duyệt mọi method trong controller
Đáp án đúng: B

Câu 19. Trong servlet security, ExceptionTranslationFilter thường có vai trò gì?
A. So sánh password hash rồi trả Authentication mới
B. Khôi phục JwtDecoder từ SecurityContextRepository session
C. Bắt đầu OAuth2 authorization-code exchange ngay khi khởi tạo
D. Chuyển các exception xác thực/phân quyền thành phản hồi
Đáp án đúng: D

Câu 20. Sau AnonymousAuthenticationFilter, SecurityContext có anonymous token thì điều gì đúng?
A. Anonymous token tương đương tài khoản đã chứng minh mật khẩu
B. SecurityContext phải null vì anonymous không có principal
C. AnonymousAuthenticationFilter tự mở session cho mọi visitor
D. Có Authentication object nhưng chưa phải đăng nhập thực sự
Đáp án đúng: D

Câu 21. Trong ứng dụng Servlet, SecurityContextHolder mặc định gắn context với đâu?
A. Thread đang xử lý request bằng chiến lược ThreadLocal
B. HttpSession cố định cho cả ứng dụng dù chưa login
C. Reactor Context trên từng subscriber của Servlet
D. Database transaction đang dùng bởi AuthenticationProvider
Đáp án đúng: A

Câu 22. Để nạp hoặc lưu SecurityContext giữa các HTTP request, abstraction nào liên quan?
A. GrantedAuthoritiesMapper trong từng DaoAuthenticationProvider
B. PasswordEncoderFactoryBean của Spring Boot startup
C. AuthenticationConverter trong mọi endpoint login
D. SecurityContextRepository quản lý load/save SecurityContext
Đáp án đúng: D

Câu 23. Với SecurityContextHolderFilter ở chế độ requireExplicitSave, lưu login tự tạo qua request sau cần gì?
A. Chỉ SecurityContextHolder.setContext là luôn đủ để persist
B. Đặt Authentication trong local variable tới khi request kết thúc
C. Gọi PasswordEncoder.upgradeEncoding rồi trả response
D. Gọi SecurityContextRepository.saveContext khi thích hợp
Đáp án đúng: D

Câu 24. Nếu tạo task async từ Servlet request và cần dùng context của caller, cách nào phù hợp?
A. Dùng ThreadLocal thường và mặc định tự truyền sang thread pool
B. Dùng DelegatingSecurityContextRunnable hoặc executor wrapper
C. Đặt principal trong tên TaskExecutor khi cấu hình bean
D. Truy cập SecurityContextHolder toàn cục trên worker bất kỳ
Đáp án đúng: B

Câu 25. Trong Spring WebFlux, context xác thực reactive thường được truy xuất từ đâu?
A. SecurityContextHolder ThreadLocal trên mọi operator reactive
B. HttpSessionSecurityContextRepository trên mọi Mono publisher
C. ReactiveSecurityContextHolder dựa trên Reactor Context
D. RequestAttributes của Spring MVC được gắn với Flux
Đáp án đúng: C

Câu 26. Session fixation protection như changeSessionId() sau login nhằm mục đích gì?
A. Gia hạn password hash trong database khi user đăng nhập
B. Đặt cùng session ID cho browser và OAuth2 provider
C. Thay session ID sau xác thực để giảm nguy cơ cố định phiên
D. Không cho client lưu bất kỳ cookie nào trong tương lai
Đáp án đúng: C

Câu 27. SessionCreationPolicy.STATELESS trong Spring Security Servlet thường có ý nghĩa gì?
A. Không dùng HttpSession để đọc/lưu SecurityContext
B. Vô hiệu mọi HTTP cookie của application ở mọi controller
C. Tự lưu principal vào session mới cho mỗi bearer request
D. Buộc browser ngừng gửi Authorization header sau login
Đáp án đúng: A

Câu 28. Khi muốn hạn chế số session đăng nhập song song, cơ chế nào hữu ích?
A. PasswordEncoder.matches giới hạn số tab browser mở
B. AuthenticationEntryPoint theo dõi số request trên mỗi session
C. Concurrent session control cấu hình maximumSessions phù hợp
D. CsrfTokenRepository tự giới hạn số phiên của user
Đáp án đúng: C

Câu 29. Khi bật remember-me qua cookie, điều nào cần lưu ý để phòng thủ?
A. Cookie remember-me tương đương MFA và không thể bị đánh cắp
B. Token hoặc cookie phải có kiểm soát thời hạn và cách thu hồi
C. Lưu mật khẩu plaintext trong cookie để tái xác thực nhanh
D. Remember-me sẽ tự vô hiệu mọi SessionAuthenticationStrategy
Đáp án đúng: B

Câu 30. Một site dùng cookie session để login từ browser nên cân nhắc bảo vệ nào?
A. Chỉ kiểm tra JWT signature của Authorization Bearer header
B. Bỏ session fixation strategy vì trình duyệt có cookie
C. Tắt kiểm tra origin nếu login form chạy cùng domain
D. CSRF protection cho login khi browser dùng session cookie
Đáp án đúng: D

Câu 31. Spring Security LDAP bind authentication kiểm tra credential user theo cách nào?
A. Luôn đọc password hash LDAP rồi giải mã tại Spring app
B. Dùng session cookie của browser làm LDAP bind password
C. Chỉ xác nhận username tồn tại mà không thử credential
D. Dùng LDAP bind với thông tin xác thực của user được tìm
Đáp án đúng: D

Câu 32. Khi lấy quyền từ group LDAP sau user authentication, thành phần nào phù hợp?
A. JwtAuthenticationConverter tự đọc group từ LDAP server
B. PasswordEncoder tạo GrantedAuthority từ raw password
C. LdapAuthoritiesPopulator map LDAP group thành authority
D. AuthenticationEntryPoint tải LDAP schema để cấp quyền
Đáp án đúng: C

Câu 33. oauth2Login() trong Spring Security thường triển khai dạng login nào?
A. Browser login qua OAuth2 Authorization Code từ provider
B. Xác thực HTTP Basic bằng client secret của resource server
C. Cấp JWT tự ký chỉ dựa trên username của login form
D. Xác thực trực tiếp bằng refresh token từ browser cookie
Đáp án đúng: A

Câu 34. Trong OAuth2 authorization request, tham số state dùng để làm gì?
A. Làm khóa mã hóa access token trả về từ token endpoint
B. Liên kết authorization request với callback để chống CSRF
C. Định nghĩa role của user sau khi OIDC userinfo trả về
D. Chỉ định giá trị session ID bất biến sau authentication
Đáp án đúng: B

Câu 35. PKCE trong Authorization Code flow bổ sung bảo vệ nào?
A. Yêu cầu resource server lưu plaintext password của client
B. Đổi code kèm code_verifier khớp code_challenge
C. Thay ID token bằng session cookie được ký bởi browser
D. Tự cấp thêm GrantedAuthority khi access token hết hạn
Đáp án đúng: B

Câu 36. Trong OIDC login, ID token được thiết kế chủ yếu để cung cấp gì?
A. Claims xác thực danh tính user cho client OIDC
B. Quyền thay đổi dữ liệu ở mọi resource server tùy ý
C. Mật khẩu của user để client tự đăng nhập LDAP
D. Refresh token dài hạn được nhúng trong userinfo response
Đáp án đúng: A

Câu 37. Khi gọi protected API với OAuth2, token nào thông thường được gửi tới resource server?
A. ID token dành cho login của client OIDC thay access token
B. Code verifier được gửi làm bearer token mỗi API request
C. AuthenticationSuccessHandler được serialize vào HTTP header
D. Access token kèm theo Authorization Bearer phù hợp
Đáp án đúng: D

Câu 38. Khi xác thực OIDC ID token, client cần kiểm tra gì?
A. Chỉ tên hiển thị của user trong claim preferred_username
B. Chữ ký và các claim như issuer, audience, expiration
C. Chỉ scope mặc định của token mà bỏ qua token signature
D. Chỉ IP client đang gọi callback từ web browser
Đáp án đúng: B

Câu 39. Với Spring Security resource server JWT, filter nào thường trích Bearer token?
A. BearerTokenAuthenticationFilter lấy token từ request để xác thực
B. OAuth2LoginAuthenticationFilter đọc Bearer JWT của REST API
C. UsernamePasswordAuthenticationFilter so sánh JWT với user password
D. AnonymousAuthenticationFilter tự decode JWT trước provider
Đáp án đúng: A

Câu 40. Với JwtAuthenticationConverter, mục tiêu phổ biến là gì?
A. Ký mới JWT bằng secret của browser ở từng HTTP request
B. Đổi OIDC ID token thành authorization code mới
C. JwtAuthenticationConverter ánh xạ claims thành authority
D. Tự tạo session cố định cho tất cả resource server
Đáp án đúng: C

Câu 41. Nếu resource server nhận JWT hết hạn dù chữ ký hợp lệ, nên xử lý sao?
A. Coi JWT hợp lệ cho đến khi browser đóng tab hiện tại
B. Tự gia hạn exp bằng cách sửa token payload mà không ký
C. Từ chối authentication vì claim exp không còn hợp lệ
D. Bỏ qua expiration khi token có scope đủ cho endpoint
Đáp án đúng: C

Câu 42. OidcUserService trong luồng oauth2Login() có thể phục vụ việc gì?
A. Tải và tạo OidcUser từ ID token và UserInfo phù hợp
B. Phát hành authorization code mới ở resource server
C. Tự kiểm tra password của user bằng DaoAuthenticationProvider
D. Thay bearer filter để đọc access token ở mọi REST API
Đáp án đúng: A

Câu 43. Trong xác thực WebAuthn/passkey, server thường kiểm tra nhóm dữ liệu nào?
A. Mật khẩu người dùng trong session và mã TOTP chung
B. Kiểm challenge, origin và RP ID của credential đã lưu
C. Chuỗi public key do browser tự ký thay cho assertion
D. JDBC transaction ID và HTTP header X-Forwarded-For
Đáp án đúng: B

Câu 44. Với passkey WebAuthn, private key xác thực thông thường nằm ở đâu?
A. Trong database ứng dụng và gửi xuống browser mỗi login
B. Trong HTTP session trên server rồi tải xuống thiết bị
C. Trong access token OAuth2 để API kiểm tra password
D. Trong authenticator; server giữ public key của credential
Đáp án đúng: D

Câu 45. Nếu passkey dùng sinh trắc học để mở khóa trên thiết bị, điều nào đúng?
A. Xác minh tại thiết bị, server nhận chứng cứ mật mã WebAuthn
B. Server nhận ảnh vân tay gốc từ browser và so sánh
C. Sinh trắc học được chuyển thành password hash ở backend
D. Passkey luôn phụ thuộc vào SMS OTP của nhà mạng
Đáp án đúng: A

Câu 46. Khi yêu cầu MFA sau khi password hợp lệ, thiết kế trạng thái nào an toàn?
A. Cấp session đầy đủ rồi ghi log chờ TOTP đến sau
B. Xem password và PIN cùng một thiết bị là hai yếu tố khác loại
C. Bỏ kiểm tra password khi đã bật cookie remember-me
D. Chỉ cấp phiên đủ quyền sau khi yếu tố bổ sung được kiểm tra
Đáp án đúng: D

Câu 47. Với TOTP trong MFA, biện pháp nào giúp hạn chế lạm dụng mã đã lộ?
A. Cho thử mã liên tục vì TOTP thay đổi theo thời gian
B. Lưu TOTP secret vào cookie để client tự xác minh
C. Giới hạn thử sai và không chấp nhận lại mã đã sử dụng
D. Chấp nhận một mã TOTP nhiều lần trong cùng phiên
Đáp án đúng: C

Câu 48. Để kiểm thử xác thực thật thay vì chỉ giả principal bằng @WithMockUser, nên làm gì?
A. Chỉ dùng @WithMockUser để xác nhận PasswordEncoder.matches
B. Gửi request login qua MockMvc và kiểm tra success/failure
C. Chỉ gọi SecurityContextHolder.setContext trong unit test
D. Bỏ security filter chain khỏi MockMvc để test controller
Đáp án đúng: B
