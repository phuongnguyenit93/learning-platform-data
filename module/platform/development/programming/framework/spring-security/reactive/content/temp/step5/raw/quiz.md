Câu 01. Annotation nào phù hợp khi muốn khai báo bảo mật HTTP theo Spring WebFlux?
A. `@EnableWebFluxSecurity` dùng cho web security reactive
B. `@EnableReactiveMethodSecurity` dành cho bảo mật method
C. `@EnableMethodSecurity` dành cho chặn gọi service method
D. `@EnableWebSecurity` dùng cho servlet web security
Đáp án đúng: A

Câu 02. Bean loại nào mô tả chuỗi filter bảo mật HTTP trong ứng dụng WebFlux?
A. `AuthenticationManager` xử lý auth nhưng không cấu hình HTTP
B. `SecurityWebFilterChain` được xây bằng `ServerHttpSecurity`
C. `SecurityFilterChain` được xây từ `HttpSecurity` Servlet
D. `FilterChainProxy` quản lý servlet security filter chain
Đáp án đúng: B

Câu 03. API builder nào dùng để cấu hình HTTP security trên Spring WebFlux?
A. `ServerHttpSecurity` cấu hình filter HTTP cho WebFlux
B. `HttpSecurity` dùng cấu hình servlet filter security
C. `ServerWebExchange` dùng lưu thuộc tính request HTTP
D. `WebSecurityCustomizer` bỏ qua servlet security filters
Đáp án đúng: A

Câu 04. Để giới hạn `/admin/**` chỉ cho người có role ADMIN trên WebFlux, API nào phù hợp?
A. `authorizeExchange` kết hợp `pathMatchers` và `hasRole`
B. `authorizeRequests` kết hợp `antMatchers` của Servlet
C. `WebFilterChain` chỉ chứa filter mà không có policy
D. `authorizeHttpRequests` kết hợp `requestMatchers` Servlet
Đáp án đúng: A

Câu 05. Điều kiện `.hasRole("ADMIN")` mặc định đối chiếu với GrantedAuthority nào?
A. Một authority được gán tên `ROLE_ROLE_ADMIN` trong Authentication
B. Một authority được gán tên `SCOPE_ADMIN` trong Authentication
C. Một authority được gán tên `ROLE_ADMIN` trong Authentication
D. Một authority được gán tên `ADMIN` trong Authentication
Đáp án đúng: C

Câu 06. Có hai `SecurityWebFilterChain` cho `/api/**` và `/ui/**`; cách chọn chain cho request là gì?
A. Cấu hình `requestMatchers` trên cùng một Servlet FilterChain
B. Cấu hình `securityMatcher` và thứ tự chain bằng `@Order`
C. Cấu hình `@PreAuthorize` để chọn filter chain ở controller
D. Cấu hình `PasswordEncoder` để chuyển request giữa các chain
Đáp án đúng: B

Câu 07. Trong WebFlux, abstraction nào tương ứng điểm chặn HTTP ở tầng filter?
A. `HandlerInterceptor` chạy trong Servlet DispatcherServlet
B. `OncePerRequestFilter` dùng thread-local Servlet request
C. `WebFilter` nhận exchange và chạy `WebFilterChain`
D. `Filter` xử lý ServletRequest và ServletResponse
Đáp án đúng: C

Câu 08. Trong reactive web security, đối tượng nào đại diện request/response khi lọc HTTP?
A. `ServerWebExchange` giữ request và response HTTP
B. `Authentication` trực tiếp chứa HTTP request và response
C. `HttpServletRequest` mang request/response ở servlet API
D. `SecurityContextHolder` trực tiếp chứa request/response
Đáp án đúng: A

Câu 09. Interface xác thực không chặn nào nhận Authentication và trả `Mono<Authentication>`?
A. `AuthenticationManager` trả Authentication đồng bộ
B. `ReactiveUserDetailsService` trả Mono<UserDetails>
C. `ReactiveAuthorizationManager` trả Mono<AuthorizationDecision>
D. `ReactiveAuthenticationManager` trả publisher xác thực
Đáp án đúng: D

Câu 10. Trong WebFlux, filter nào thực hiện quy trình chuyển request thành Authentication?
A. `CorsWebFilter` chuyển token header thành Authentication
B. `CsrfWebFilter` chuyển username/password thành Authentication
C. `AuthorizationWebFilter` thực hiện toàn bộ luồng đọc credentials
D. `AuthenticationWebFilter` xử lý xác thực trong WebFilter chain
Đáp án đúng: D

Câu 11. Thành phần nào chuyển `ServerWebExchange` thành Authentication request trong AuthenticationWebFilter?
A. `ReactiveJwtDecoder` đọc JWT bearer token thành Authentication
B. `ServerSecurityContextRepository` đổi exchange sang credentials
C. `ServerAuthenticationConverter` đọc credential từ exchange
D. `ReactiveAuthorizationManager` đọc username từ exchange
Đáp án đúng: C

Câu 12. Service reactive nào dùng để tra cứu người dùng theo username khi đăng nhập?
A. `UserDetailsService` trả `UserDetails` ở dạng đồng bộ
B. `ReactiveAuthenticationManager` trả token dưới dạng Mono
C. `ReactiveUserDetailsService` trả `Mono<UserDetails>`
D. `ServerSecurityContextRepository` đọc SecurityContext
Đáp án đúng: C

Câu 13. Cách nào lấy SecurityContext đang gắn với reactive execution đúng hơn ThreadLocal?
A. `ServerHttpSecurity.getContext()` trả current SecurityContext
B. `HttpSession.getAttribute()` chỉ dùng servlet session context
C. `SecurityContextHolder.getContext()` đọc ThreadLocal ở worker
D. `ReactiveSecurityContextHolder.getContext()` truy xuất context
Đáp án đúng: D

Câu 14. Để gắn Authentication vào một Reactor chain riêng, cách nào hợp lý?
A. `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))`
B. `.doOnNext(ReactiveSecurityContextHolder.withAuthentication(auth))`
C. `.subscribe(ReactiveSecurityContextHolder.withAuthentication(auth))`
D. `.publishOn(ReactiveSecurityContextHolder.withAuthentication(auth))`
Đáp án đúng: A

Câu 15. Tác động nào dễ làm mất security context khi code Reactive tự gọi `.subscribe()` bên ngoài chuỗi?
A. `publishOn` tự xóa Reactor Context khi đổi scheduler
B. `flatMap` tự loại các key bảo mật khỏi Reactor Context
C. Subscription riêng không kế thừa Reactor Context của caller
D. `map` tự đóng SecurityContextRepository sau một signal
Đáp án đúng: C

Câu 16. Để áp dụng `@PreAuthorize` trên method trả Publisher trong ứng dụng Reactive, cần gì?
A. `@EnableWebFluxSecurity` chỉ kích hoạt kiểm tra `@PreAuthorize`
B. `@EnableAspectJAutoProxy` tự đăng ký Reactor security policy
C. `@EnableMethodSecurity` cấu hình reactive method riêng biệt
D. `@EnableReactiveMethodSecurity` kích hoạt bảo vệ method
Đáp án đúng: D

Câu 17. Khi kiểm tra quyền ở service trả `Mono`, điều gì đúng về việc blocking trong event-loop?
A. Dùng ThreadLocal để serialize authentication trên một thread
B. Dùng `.block()` trong `map` để đảm bảo SecurityContext còn sống
C. Dùng JDBC blocking trực tiếp trên event-loop để giữ thứ tự dữ liệu
D. Không block I/O trên event-loop; chuyển tác vụ chặn qua scheduler
Đáp án đúng: D

Câu 18. Với JWT có scope `orders.read`, authority mặc định trong Spring Resource Server thường là gì?
A. `ROLE_orders.read` là GrantedAuthority chuyển từ scope
B. `SCOPE_orders.read` là authority mặc định từ scope
C. `orders.read` là GrantedAuthority gốc theo JWT claim
D. `CLAIM_orders.read` là GrantedAuthority chuyển từ scope
Đáp án đúng: B

Câu 19. Với WebFlux JWT Resource Server, request thiếu bearer token tới endpoint bảo vệ thường nhận status nào?
A. HTTP 404 vì security filter không tìm thấy handler
B. HTTP 401 từ authentication entry point của Bearer Resource Server
C. HTTP 200 với response body chứa thông tin login
D. HTTP 403 vì client chưa cung cấp bearer credentials
Đáp án đúng: B

Câu 20. Thành phần nào tùy chỉnh phản hồi khi user đã xác thực nhưng không đủ quyền?
A. `ServerAccessDeniedHandler` xử lý tình huống bị từ chối
B. `ReactiveJwtDecoder` xác minh token nhưng không trả 403
C. `ServerAuthenticationEntryPoint` yêu cầu client xác thực
D. `ServerAuthenticationConverter` trích xuất credentials
Đáp án đúng: A

Câu 21. Repository nào mặc định thường dùng WebSession để lưu SecurityContext ở WebFlux stateful?
A. `WebSessionServerSecurityContextRepository` dùng WebSession
B. `HttpSessionSecurityContextRepository` lưu theo Servlet session
C. `RequestAttributeSecurityContextRepository` lưu trong servlet
D. `NullSecurityContextRepository` bỏ qua lưu context
Đáp án đúng: A

Câu 22. Muốn mô hình stateless không lưu SecurityContext vào WebSession, repository nào phù hợp?
A. `HttpSessionSecurityContextRepository` quản lý servlet context
B. `DelegatingSecurityContextRepository` lưu vào session servlet
C. `NoOpServerSecurityContextRepository` không lưu context
D. `WebSessionServerSecurityContextRepository` tạo session khi auth
Đáp án đúng: C

Câu 23. Trong WebFlux, DSL nào bật đăng nhập browser bằng OAuth2/OIDC provider?
A. `oauth2Client()` chỉ lấy token cho outgoing API requests
B. `oauth2ResourceServer()` xác thực bearer access token
C. `oauth2Login()` thiết lập reactive browser login từ IdP
D. `saml2Login()` xử lý SAML assertions cho Servlet SP
Đáp án đúng: C

Câu 24. Ứng dụng WebFlux cần lấy access token để gọi API khác, cấu hình nào thuộc vai trò OAuth2 Client?
A. `oauth2ResourceServer()` xác minh bearer token gọi API đến
B. `httpBasic()` xác thực username/password của request
C. `csrf()` xác minh token chống giả mạo trên HTTP request
D. `oauth2Client()` chuẩn bị token cho outgoing API call
Đáp án đúng: D

Câu 25. Để biến WebFlux app thành JWT Resource Server, cấu hình nào phù hợp?
A. `oauth2Client(oauth2 -> oauth2.jwt(...))` kiểm incoming JWT
B. `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` kiểm JWT
C. `formLogin(login -> login.jwt(...))` kiểm incoming JWT
D. `oauth2Login(oauth2 -> oauth2.jwt(...))` kiểm JWT Resource Server
Đáp án đúng: B

Câu 26. Trong reactive JWT Resource Server, abstraction nào giải mã và xác minh JWT?
A. `OAuth2AuthorizedClientManager` xin token outbound cho user
B. `JwtDecoder` trả `Jwt` đồng bộ khi giải mã token
C. `ReactiveJwtDecoder` trả `Mono<Jwt>` khi giải mã token
D. `ReactiveOpaqueTokenIntrospector` gửi token đến AS introspect
Đáp án đúng: C

Câu 27. Khi cấu hình `issuer-uri` cho JWT Resource Server, điều gì cần xác minh?
A. HTTP Referer phải khớp với issuer cho mỗi request API
B. JWT cần kiểm issuer, chữ ký và khóa đáng tin của provider
C. Client secret của browser được dùng làm signing key mặc định
D. Resource Server chấp nhận JWT dựa riêng vào claim iss
Đáp án đúng: B

Câu 28. Khi cần ánh xạ claim JWT thành quyền riêng, hướng tiếp cận nào phù hợp trong Reactive?
A. Cấu hình `ServerCsrfTokenRepository` để chuyển scope thành role
B. Cấu hình `CorsConfiguration` để chuyển token thành authorities
C. Cấu hình `PasswordEncoder` để đọc JWT role từ header
D. Dùng converter đổi JWT claims thành authorities theo policy
Đáp án đúng: D

Câu 29. Khi Resource Server nhận opaque access token, cơ chế nào phù hợp hơn JWT decoder?
A. `saml2Login()` xác minh XML Signature của opaque access token
B. `jwt()` trích xuất claims bằng JWK Set trong token opaque
C. `oauth2Login()` tạo OIDC ID Token từ opaque access token
D. `opaqueToken()` dùng introspection tại authorization server
Đáp án đúng: D

Câu 30. Trong WebFlux, abstraction nào introspect opaque token theo kiểu Reactive?
A. `OpaqueTokenIntrospector` trả principal trong servlet API
B. `ReactiveOpaqueTokenIntrospector` đọc token qua introspection
C. `ReactiveJwtDecoder` đọc JWS signature của opaque token
D. `ReactiveUserDetailsService` lấy thông tin user bằng username
Đáp án đúng: B

Câu 31. Khác biệt quan trọng giữa JWT validation và opaque token introspection ở Resource Server là gì?
A. JWT dùng browser session; opaque dùng HTTP basic theo mặc định
B. JWT thường xác minh chữ ký tại chỗ; opaque gọi AS để introspect
C. JWT yêu cầu OpenID Connect; opaque yêu cầu SAML authentication
D. JWT gọi introspection endpoint cho từng request; opaque dùng JWK
Đáp án đúng: B

Câu 32. Khi API dùng Bearer token, phát biểu nào đúng về ID Token OIDC?
A. Access token dùng gọi API; ID Token chứng minh login
B. Access token chỉ dùng cho trang đăng nhập, không dùng cho API
C. ID Token là bearer credential API do Resource Server yêu cầu
D. ID Token thay cho refresh token khi gọi introspection API
Đáp án đúng: A

Câu 33. Với WebFlux có form login và session cookie, xử lý CSRF phù hợp là gì?
A. Tắt CSRF vì WebFlux không thể lưu session cookie
B. Giữ CSRF cho request ghi dữ liệu dựa vào session cookie
C. Dùng CORS để thay cho CSRF validation tại mỗi request
D. Dùng JWT decoder để đọc CSRF token từ session cookie
Đáp án đúng: B

Câu 34. Với `WebTestClient`, configurer nào thêm CSRF token hợp lệ cho request test?
A. `mutateWith(mockUser())` tự điền CSRF token vào request test
B. `mutateWith(mockOidcLogin())` cung cấp CSRF token từ ID Token
C. `mutateWith(mockJwt())` cung cấp CSRF token từ JWT scope
D. `mutateWith(csrf())` cung cấp CSRF token test cho WebFlux
Đáp án đúng: D

Câu 35. Nếu REST API stateless xác thực thuần bằng Authorization: Bearer và không dùng cookie, đánh giá CSRF thế nào?
A. Thay CSRF bằng CORS allow-all để client gửi bearer token
B. CSRF vẫn cần như form cookie dù browser không tự gửi token
C. Có thể tắt CSRF cho API nếu không dùng xác thực tự gửi kèm
D. Chỉ dùng CSP thay CSRF cho cả bearer API lẫn cookie sessions
Đáp án đúng: C

Câu 36. Đối với HTTP CORS preflight, vì sao xử lý CORS cần chạy trước authentication?
A. Preflight mang JWT đầy đủ nên phải qua resource server trước
B. Xử lý preflight trước auth vì browser chưa gửi credentials
C. Preflight dùng CSRF token nên phải được authenticate như POST
D. Preflight chỉ xuất hiện ở WebSocket, không liên quan HTTP security
Đáp án đúng: B

Câu 37. Trong WebFlux, thành phần nào thường cấu hình xử lý CORS cho HTTP exchange?
A. `AuthenticationWebFilter` tự sinh Access-Control-Allow-Origin
B. `AuthorizationWebFilter` tự quản lý allowed CORS headers
C. `CorsWebFilter` thực thi chính sách origin và method
D. `CsrfWebFilter` thiết lập origin policy cho browser preflight
Đáp án đúng: C

Câu 38. Khi tự tạo `WebTestClient` từ application context, bước nào tích hợp Spring Security test hỗ trợ mock principal?
A. Áp dụng `oidcLogin()` từ Servlet vào WebTestClient builder
B. Áp dụng `mockJwt()` để bootstrap toàn bộ ApplicationContext
C. Áp dụng `csrf()` để tạo ServerWebExchange SecurityWebFilterChain
D. Áp dụng `springSecurity()` rồi sử dụng `mutateWith(mockUser())`
Đáp án đúng: D

Câu 39. Để kiểm thử phân quyền JWT Resource Server bằng WebTestClient mà không gọi IdP, dùng gì?
A. `mutateWith(mockJwt())` cung cấp principal JWT khi test
B. `mutateWith(mockOidcLogin())` tạo bearer JWT Resource Server
C. `mutateWith(mockUser())` xác minh chữ ký JWT bằng JWKS
D. `mutateWith(csrf())` tạo bearer access token trong header
Đáp án đúng: A

Câu 40. Để kiểm thử Reactive OAuth2/OIDC login của user trong WebTestClient, lựa chọn nào đúng?
A. `mutateWith(mockOidcLogin())` cung cấp principal OIDC giả lập
B. `mutateWith(mockJwt())` mô phỏng OIDC browser login session
C. `mutateWith(mockOAuth2Client())` tự chạy authorization code flow
D. `mutateWith(oidcLogin())` dùng MockMvc login servlet trên WebFlux
Đáp án đúng: A
