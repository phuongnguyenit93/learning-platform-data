Câu 1. Trong OAuth 2.0, nhiệm vụ chính của Spring Security Resource Server là gì?
A. Phát hành authorization code cho client sau khi user đăng nhập
B. Duyệt màn hình consent để cấp scope cho client ứng dụng
C. Kiểm tra access token và áp quy tắc quyền lên API được bảo vệ
D. Lưu tài khoản người dùng và mật khẩu như authorization server
Đáp án đúng: C

Câu 2. Với Resource Server, bearer access token thường được hiểu theo cơ chế nào?
A. Client phải ký lại token bằng mật khẩu user ở mỗi request
B. Browser luôn cần session cookie để token có thể được đọc
C. Token chỉ dùng được sau khi gọi OAuth2 authorization endpoint
D. Ai sở hữu token hợp lệ có thể dùng nó trong phạm vi quyền
Đáp án đúng: D

Câu 3. Trong Servlet HttpSecurity, cấu hình nào thường bật xác thực JWT cho API?
A. oauth2ResourceServer với tùy chọn jwt và JwtDecoder
B. oauth2Login cùng OidcUserService cho mọi REST bearer call
C. formLogin cùng UsernamePasswordAuthenticationFilter
D. saml2Login cùng RelyingPartyRegistrationRepository
Đáp án đúng: A

Câu 4. Trong Servlet Resource Server, filter nào thường đọc bearer token từ request?
A. BearerTokenAuthenticationFilter xử lý bearer authentication
B. OAuth2LoginAuthenticationFilter đổi authorization code sang token
C. UsernamePasswordAuthenticationFilter đọc mật khẩu form login
D. BasicAuthenticationFilter lấy thông tin username từ session
Đáp án đúng: A

Câu 5. Mặc định bearer token thường được client gửi bằng cách nào?
A. Header Set-Cookie với scope của authorization server
B. Tham số redirect_uri trên mọi HTTP POST tới API
C. Header Authorization với scheme Bearer theo HTTP
D. Header WWW-Authenticate do chính client tạo để gửi token
Đáp án đúng: C

Câu 6. Trước khi token được xác minh, BearerTokenAuthenticationToken thường đại diện cho gì?
A. Một authentication request chứa chuỗi bearer token chưa được kiểm tra
B. Một JWT đã có authority ROLE_ADMIN do Spring gán sẵn
C. Một SecurityContext đã được lưu bền vào HttpSession
D. Một authorization code đã được đổi thành access token
Đáp án đúng: A

Câu 7. Với JWT Resource Server, AuthenticationProvider nào thường kiểm chứng JWT?
A. DaoAuthenticationProvider đọc password hash từ user repository
B. JwtAuthenticationProvider dùng JwtDecoder để xác minh token
C. AnonymousAuthenticationProvider tạo principal từ HTTP cookie
D. RememberMeAuthenticationProvider tạo session từ browser token
Đáp án đúng: B

Câu 8. Trong JWT flow, JwtDecoder chịu trách nhiệm chính về việc gì?
A. Lưu refresh token vào database của client đang đăng nhập
B. Đổi OAuth2 authorization code thành access token mới
C. Giải mã và xác minh token JWT theo cấu hình và validator
D. Tự cấp scope cho người dùng khi không có claim nào
Đáp án đúng: C

Câu 9. Một JWT có header và payload đọc được bằng Base64URL chưa đủ đáng tin vì sao?
A. Payload đã đọc được đồng nghĩa authorization đã hoàn tất
B. JWT hợp lệ khi chỉ có sub dù signature không được kiểm tra
C. Chỉ cần so sánh chuỗi token với cookie browser đã lưu
D. Cần kiểm tra chữ ký và các claim trước khi chấp nhận
Đáp án đúng: D

Câu 10. Trong JWT, kiểm tra issuer claim nhằm đảm bảo điều gì?
A. Token đã có scope phù hợp cho mọi endpoint của API
B. Token chưa bị thu hồi bằng cách đọc database cục bộ
C. Token đến từ authorization server đã được tin cậy
D. Token được gửi bởi browser thay vì một HTTP client khác
Đáp án đúng: C

Câu 11. JWK Set URI trong cấu hình JWT Resource Server cung cấp gì?
A. Endpoint phát hành refresh token mới cho API resource server
B. Endpoint chứa public keys để xác minh chữ ký JWT
C. Endpoint kiểm tra mật khẩu user bằng form authentication
D. Endpoint cung cấp dữ liệu nhóm LDAP để map authorities
Đáp án đúng: B

Câu 12. Header kid của JWT hữu ích chủ yếu khi có nhiều khóa ký để làm gì?
A. Chỉ định tên client được phép gọi API của resource server
B. Thay thế kiểm tra issuer và audience bằng một chuỗi id
C. Xác định thời gian sống của JWT tính theo phút
D. Chọn khóa xác minh phù hợp từ tập JWK của issuer
Đáp án đúng: D

Câu 13. Khi authorization server xoay khóa ký JWT, resource server nên hỗ trợ gì?
A. Giữ duy nhất public key cũ cho đến khi ứng dụng restart
B. Bỏ kiểm tra chữ ký trong thời gian đổi khóa trên issuer
C. Lưu private key của authorization server trong client
D. Cập nhật hoặc nạp lại JWK phù hợp khi gặp khóa mới
Đáp án đúng: D

Câu 14. JWT có exp trong quá khứ, dù chữ ký đúng, kết quả phù hợp là gì?
A. Từ chối token vì thời hạn đã hết theo validator
B. Cho phép token vì chữ ký đúng chứng minh user đang login
C. Gia hạn exp ngay trong payload mà không cần ký lại
D. Đưa token vào HttpSession để gia hạn thông qua cookie
Đáp án đúng: A

Câu 15. JWT có nbf ở tương lai so với đồng hồ server, điều gì cần xem xét?
A. Token đã bị thu hồi bởi introspection endpoint mặc định
B. Token chưa tới thời điểm có hiệu lực theo nbf
C. Token có thể bỏ qua xác minh issuer khi nbf còn tương lai
D. Token được mặc định chấp nhận nếu scope đã đủ
Đáp án đúng: B

Câu 16. Vì sao API thường cần kiểm tra audience claim ngoài chữ ký và issuer?
A. Bảo đảm JWT có một scope cho mỗi HTTP method
B. Xác nhận client đã nhận refresh token từ issuer
C. Ngăn token dành cho dịch vụ khác bị dùng sai API
D. Buộc caller dùng cookie thay cho Authorization header
Đáp án đúng: C

Câu 17. Khi khai issuer-uri, Resource Server có thể dùng thông tin gì của issuer?
A. Discovery metadata để tìm JWK Set và xác lập issuer
B. Danh sách PasswordEncoder để xác thực raw password user
C. Địa chỉ CORS origin của frontend để sinh CSRF token
D. Bảng session đang đăng nhập để kiểm tra cookie browser
Đáp án đúng: A

Câu 18. Nếu chỉ cấu hình jwk-set-uri mà không thiết lập issuer validator, điều nào cần lưu ý?
A. Resource server mặc định kiểm tra issuer của mọi JWT trên mạng
B. Cấu hình đó sẽ luôn gọi introspection trước khi decode JWT
C. JWK Set URI tự động chứng minh mọi audience đều phù hợp
D. Chỉ biết nơi lấy khóa chưa đồng nghĩa tự kiểm tra claim iss
Đáp án đúng: D

Câu 19. Có nên đặt API secret hoặc mật khẩu vào payload JWT thông thường không?
A. Có, signature tự mã hóa payload và che giấu plaintext
B. Có, nếu header alg dùng RS256 thì payload không đọc được
C. Không, payload JWT có thể bị bên nhận token đọc được
D. Có, vì bearer token không thể bị ghi trong request log
Đáp án đúng: C

Câu 20. Nếu header JWT quảng cáo thuật toán alg=none, quyết định an toàn nào phù hợp?
A. Chỉ chấp nhận thuật toán ký cho phép theo cấu hình decoder
B. Tin thuật toán do token tự khai mà bỏ qua kiểm tra signature
C. Tự chuyển alg=none thành HS256 trước khi cấp authority
D. Bỏ qua algorithm nếu JWT có issuer và subject hợp lệ
Đáp án đúng: A

Câu 21. Sau JWT authentication thành công trên Servlet, loại Authentication nào thường được tạo?
A. UsernamePasswordAuthenticationToken chỉ chứa raw password
B. JwtAuthenticationToken mang principal JWT và authorities
C. AnonymousAuthenticationToken đại diện cho bearer scope
D. OAuth2LoginAuthenticationToken chứa browser authorization code
Đáp án đúng: B

Câu 22. JwtAuthenticationConverter thường được dùng để tùy chỉnh điều gì?
A. Chuyển claims của JWT thành principal và authorities
B. Lấy refresh token từ Authorization header để cấp token mới
C. Kiểm tra tên cookie session trước khi parse JWT
D. Đăng ký JWK endpoint mới trên authorization server
Đáp án đúng: A

Câu 23. Với claim scope hoặc scp, converter mặc định thường tạo authority theo quy ước gì?
A. Tiền tố ROLE_ gắn vào tên client_id của access token
B. Tiền tố OIDC_ gắn vào mọi giá trị aud của token
C. Tiền tố JWT_ gắn vào giá trị exp của token
D. Tiền tố SCOPE_ gắn vào từng scope trong access token
Đáp án đúng: D

Câu 24. Khi JWT hợp lệ có scope "orders.read", quy tắc nào kiểm tra scope tương ứng?
A. hasRole("orders.read") mà không cấu hình mapping
B. hasAuthority("ROLE_orders.read") theo mặc định JWT
C. permitAll() kết hợp hasRole("authenticated") ở URL
D. hasAuthority("SCOPE_orders.read") trên tài nguyên
Đáp án đúng: D

Câu 25. Khi dùng hasRole("ADMIN") cho JWT, điều gì dễ bị nhầm với scope mặc định?
A. hasRole mặc định tra scope admin với tiền tố SCOPE_
B. hasRole tìm ROLE_ADMIN chứ không tự đổi SCOPE_admin
C. hasRole chỉ kiểm tra claim aud, không dùng authorities
D. hasRole mặc định tạo ADMIN từ username của principal
Đáp án đúng: B

Câu 26. Một JWT xác minh chữ ký và exp thành công nhưng thiếu scope bắt buộc sẽ thế nào?
A. Có thể được xác thực nhưng bị từ chối truy cập API
B. Được cấp scope cần thiết để request chạy thành công
C. Bị coi như JWT sai chữ ký trước khi tạo Authentication
D. Được tự chuyển sang OAuth2 login và hiện trang consent
Đáp án đúng: A

Câu 27. Opaque access token khác JWT self-contained ở đặc điểm nào?
A. Opaque token bắt buộc chứa ba phần Base64URL phân tách dấu chấm
B. Opaque token luôn có JWK header với thuật toán ký cụ thể
C. Opaque token mang sẵn public key trong Authorization header
D. Resource server không tự đọc claims trực tiếp từ chuỗi token
Đáp án đúng: D

Câu 28. Với opaque token, resource server thường kiểm tra hiệu lực theo cách nào?
A. Xác minh signature JWT qua JWKS mà không gọi server ngoài
B. Lấy header kid rồi chọn khóa RS256 từ local keystore
C. So sánh token với giá trị csrf() của browser session
D. Gọi introspection endpoint đã cấu hình với token được nhận
Đáp án đúng: D

Câu 29. Trong Spring Security, abstraction nào thường dùng xử lý opaque introspection ở Servlet?
A. JwtDecoder xác thực opaque token qua JwtTimestampValidator
B. OpaqueTokenIntrospector phân tích kết quả introspection
C. OAuth2AuthorizedClientService cấp refresh token cho resource server
D. AuthenticationSuccessHandler lưu opaque token xuống session
Đáp án đúng: B

Câu 30. Khi introspection trả active=false, resource server nên phản hồi thế nào?
A. Cấp quyền read-only vì token còn có chuỗi ký tự
B. Không xác thực token và từ chối request được bảo vệ
C. Bỏ qua active để xét tiếp claim scope không đáng tin
D. Đổi opaque token thành JWT mà không cần authorization server
Đáp án đúng: B

Câu 31. Nếu introspection endpoint không truy cập được, cách xử lý an toàn là gì?
A. Cấp quyền tạm thời nếu bearer token có độ dài hợp lệ
B. Xem lỗi kết nối như active=true để tránh gián đoạn
C. Không mặc nhiên cho qua bearer token chưa được xác thực
D. Dựa riêng vào tên token để suy ra quyền user
Đáp án đúng: C

Câu 32. Opaque introspection trả scope="read write" thì cần điều gì để áp luật scope?
A. Bật JwtDecoder để lấy JWK mà không cần dữ liệu introspection
B. Đọc session cookie của client để tự sinh ROLE_USER
C. Lấy claim sub rồi coi là quyền read/write mặc định
D. Ánh xạ dữ liệu introspection sang GrantedAuthority phù hợp
Đáp án đúng: D

Câu 33. So với opaque token được introspect mỗi lần, JWT tự xác minh có hạn chế nào khi cần thu hồi ngay?
A. Token ký hợp lệ có thể còn dùng được tới hạn nếu không có cơ chế phụ
B. JWT bị vô hiệu tức thì khi user logout ở bất kỳ client nào
C. JWKS tự xóa mọi JWT cũ ngay khi password user thay đổi
D. JwtDecoder bắt buộc hỏi database về trạng thái mọi token
Đáp án đúng: A

Câu 34. Khi muốn chặn ngay một JWT cụ thể trước exp, biện pháp nào có thể áp dụng?
A. Thêm kiểm tra trạng thái thu hồi hoặc denylist phù hợp
B. Chỉ đọc lại public key mà không kiểm tra token identifier
C. Tăng clock skew để token tự hết hạn sớm hơn
D. Giữ nguyên quy tắc chữ ký và bỏ qua mọi revocation state
Đáp án đúng: A

Câu 35. Nếu xoay signing key, có nên coi mọi JWT đang lưu là đã bị thu hồi không?
A. Có, chỉ cần phát hành JWK mới là xóa được mọi JWT
B. Có, vì issuer đổi signing key nghĩa là token tự mất exp
C. Không mặc định; tùy khóa còn tin cậy và chính sách rotation
D. Không cần xem key material khi decoder đã có JWT cũ
Đáp án đúng: C

Câu 36. Với một API cần phân biệt token xác thực user và token dành cho service, điểm nào quan trọng?
A. Cứ có JWT hợp lệ là mọi tài nguyên của mọi user mở được
B. Dùng chung quyền admin cho mọi client credentials flow
C. Chỉ kiểm tra HTTP Origin để xác định token của user
D. Xét claims/authority và chính sách của token type tương ứng
Đáp án đúng: D

Câu 37. Khi request không có bearer token mà endpoint yêu cầu authenticated(), phản hồi API phổ biến là gì?
A. HTTP 403 vì token đã được xác thực nhưng thiếu scope
B. HTTP 200 với principal anonymous đủ quyền mặc định
C. HTTP 401 với Bearer challenge khi cấu hình resource server
D. HTTP 302 bắt buộc tới form login của server issuer
Đáp án đúng: C

Câu 38. Nếu token đã được xác thực nhưng thiếu authority bắt buộc, phản hồi nào thông thường hợp lý?
A. HTTP 401 vì bearer token luôn bị coi là sai signature
B. HTTP 403 vì chủ thể không được cấp quyền cần thiết
C. HTTP 200 nếu issuer đã ký đúng token ban đầu
D. HTTP 302 tới userinfo endpoint để bổ sung role
Đáp án đúng: B

Câu 39. BearerTokenAuthenticationEntryPoint trong Servlet Resource Server giúp gì?
A. Tạo phản hồi cho lỗi xác thực bearer như HTTP 401
B. Gộp dữ liệu scope thành authorities cho JwtAuthenticationToken
C. Tải JWKS và cập nhật cache khóa ký của JwtDecoder
D. Tự sinh opaque token mới khi introspection lỗi
Đáp án đúng: A

Câu 40. BearerTokenAccessDeniedHandler thường phục vụ trường hợp nào?
A. Tạo Authentication mới từ JWT khi chưa có token
B. Xử lý access denied cho bearer principal đã xác thực
C. Đổi authorization code lấy access token cho client
D. Lưu bearer token trong HttpSession sau mỗi request
Đáp án đúng: B

Câu 41. Khi app Servlet có chain riêng cho /api/**, cấu hình nào giúp áp bearer cho API?
A. Chỉ đặt @Order trên Controller mà không khai SecurityFilterChain
B. Đặt mọi endpoint vào oauth2Login() cho browser redirect
C. Dùng securityMatcher("/api/**") trên chain resource server
D. Dùng RequestCache để tự tạo JWT từ session cookie
Đáp án đúng: C

Câu 42. Với API bearer-only, SessionCreationPolicy.STATELESS chủ yếu có nghĩa gì?
A. Không gửi cookie CSRF và tự bỏ mọi header Authorization
B. Không dùng HttpSession để lấy hay lưu SecurityContext
C. Không cho resource server xử lý token opaque qua introspection
D. Không cần xác minh token trên request sau khi đã qua lần đầu
Đáp án đúng: B

Câu 43. Trong Spring WebFlux, thành phần cấu hình resource server thường là gì?
A. HttpSecurity.authorizeHttpRequests trên mọi Mono publisher
B. SecurityFilterChain Servlet để xử lý các WebFilter reactive
C. BasicAuthenticationFilter tự nạp JWT từ Reactor Context
D. ServerHttpSecurity.oauth2ResourceServer với jwt hoặc opaqueToken
Đáp án đúng: D

Câu 44. Với WebFlux Resource Server JWT, decoder phù hợp dùng kiểu API nào?
A. ReactiveJwtDecoder cung cấp xác minh JWT kiểu reactive
B. JwtDecoder Servlet mặc định được inject vào mọi WebFilter
C. ReactiveUserDetailsService giải chữ ký JWT từ JWKS
D. OpaqueTokenIntrospector Servlet thay ReactiveJwtDecoder
Đáp án đúng: A

Câu 45. Trong WebFlux, SecurityContext của request thường gắn vào đâu?
A. SecurityContextHolder ThreadLocal cố định cho mọi signal
B. HttpSessionSecurityContextRepository cho Servlet request
C. ReactiveSecurityContextHolder dựa trên Reactor Context
D. Một biến static Authentication dùng chung toàn ứng dụng
Đáp án đúng: C

Câu 46. Khi API nhận JWT từ nhiều issuer, cách cấu hình multi-tenant nào an toàn?
A. Tin mọi giá trị iss nhận từ client và nạp JWKS tương ứng
B. Dùng issuer bất kỳ mà JWT khai để tự cấp SCOPE_admin
C. Resolver chọn AuthenticationManager theo issuer đã tin cậy
D. Tự bỏ qua aud vì multi-tenant có nhiều authorization server
Đáp án đúng: C

Câu 47. Khi xác định tenant từ claim iss của JWT chưa xác minh, quy tắc nào cần bảo đảm?
A. Tải mọi JWKS từ issuer client khai để mở quyền theo scope
B. Chỉ dùng issuer thuộc tập cho phép trước khi xác minh chữ ký
C. Giữ token unverified làm Authentication đã xác thực tạm thời
D. Bỏ kiểm tra issuer nếu claim sub trùng user đã login
Đáp án đúng: B

Câu 48. Muốn kiểm thử endpoint protected theo JWT mà không gọi issuer thật, cách nào phù hợp?
A. Tắt toàn bộ SecurityFilterChain để test quyền bằng controller
B. Dùng spring-security-test jwt() và assert các quyền truy cập
C. Dùng @WithMockUser để kết luận signature JWKS được kiểm chứng
D. Lấy access token production rồi ghi cứng vào test fixture
Đáp án đúng: B
