Câu 01. Ứng dụng Spring cần gọi API đối tác bằng access token OAuth2; chức năng nào phù hợp nhất?
A. `oauth2Client()` lấy và quản lý access token để gọi API đối tác
B. `saml2Login()` xử lý thông điệp xác thực SAML từ IdP
C. `formLogin()` xác thực username/password qua form HTTP
D. `oauth2ResourceServer()` xác thực bearer token đi vào ứng dụng
Đáp án đúng: A

Câu 02. Để người dùng đăng nhập qua nhà cung cấp OIDC trong Spring Security Servlet, cấu hình nào phù hợp?
A. `oauth2Login()` cấu hình browser login qua OIDC provider
B. `httpBasic()` kích hoạt HTTP Basic cho endpoint login
C. `oauth2ResourceServer()` xác minh JWT gửi đến REST API
D. `saml2Login()` thiết lập đăng nhập bằng SAML assertions
Đáp án đúng: A

Câu 03. Một service backend chỉ cần token theo `client_credentials` và không thực hiện đăng nhập người dùng; cách nào phù hợp?
A. Dùng OIDC `oauth2Login()` để lấy ID Token cho từng nhân viên
B. Dùng Resource Server JWT decoder để tự phát hành access token
C. Dùng authorized-client manager với grant `client_credentials` cho service
D. Dùng `saml2Login()` để gửi SAML Assertion tới API đối tác
Đáp án đúng: C

Câu 04. Trong Spring Security OAuth2 Client, cấu phần nào quản lý các cấu hình client/provider theo `registrationId`?
A. `OAuth2AuthorizedClientService` tra cứu các provider registrations
B. `ClientRegistrationRepository` tra cứu thông tin client đã đăng ký
C. `JwtDecoder` tra cứu thông tin grant và redirect URI của client
D. `OAuth2AuthorizedClientRepository` tra cứu thông tin client cấu hình
Đáp án đúng: B

Câu 05. Trong Spring Boot, property nào khai báo client ID cho registration tên `acme`?
A. `spring.security.oauth2.client.registration.acme.issuer-uri`
B. `spring.security.oauth2.client.registration.acme.client-id`
C. `spring.security.oauth2.client.provider.acme.client-id`
D. `spring.security.oauth2.resourceserver.jwt.acme.client-id`
Đáp án đúng: B

Câu 06. Sự khác nhau chính giữa `ClientRegistration` và `OAuth2AuthorizedClient` là gì?
A. Registration giữ session; authorized client giữ các endpoint URI
B. Registration giữ refresh token; authorized client giữ client secret
C. Registration chứa cấu hình; authorized client giữ token được cấp
D. Registration giữ user profile; authorized client giữ private JWK
Đáp án đúng: C

Câu 07. Theo cấu hình Servlet mặc định, URL nào bắt đầu Authorization Code login cho `google`?
A. `/oauth2/authorization/google` khởi tạo login và chuyển tới IdP
B. `/oauth2/token/google` chuyển browser tới authorization endpoint
C. `/oauth2/jwks/google` chuyển browser tới authorization endpoint
D. `/login/oauth2/code/google` chuyển browser tới authorization endpoint
Đáp án đúng: A

Câu 08. Theo cấu hình Servlet mặc định, provider chuyển authorization code về URL nào?
A. `/oauth2/authorized-client/google` là redirect endpoint nhận code
B. `/login/oauth2/code/google` là redirect endpoint nhận code
C. `/oauth2/authorization/google` là redirect endpoint nhận code
D. `/login/saml2/sso/google` là redirect endpoint nhận code
Đáp án đúng: B

Câu 09. Sau khi callback mang authorization code hợp lệ, OAuth2 Client thực hiện bước nào để có access token?
A. Đọc access token trực tiếp từ fragment trên URL callback
B. Trao đổi code tại token endpoint kèm client và redirect URI để lấy access token
C. Đổi authorization code thành access token bằng JWT decoder
D. Gửi code tới UserInfo endpoint rồi lấy token từ profile
Đáp án đúng: B

Câu 10. Trong PKCE, `code_challenge` được gửi ở giai đoạn nào của Authorization Code flow?
A. Gắn code challenge vào ID Token sau khi token đã được ký
B. Gửi code challenge trong HTTP logout request tới provider
C. Gửi code challenge cùng refresh token khi token hết hạn
D. Đưa `code_challenge` vào authorization request để ràng buộc code được cấp
Đáp án đúng: D

Câu 11. Với PKCE `S256`, `code_challenge` được hình thành theo cách nào?
A. Base64url của chữ ký JWS băm từ redirect URI đã đăng ký
B. Base64url của HMAC-SHA256 băm bằng client secret phía server
C. Base64url của SHA-256 băm từ ID Token nhận ở token endpoint
D. Băm `code_verifier` bằng SHA-256 rồi mã hóa Base64url không đệm
Đáp án đúng: D

Câu 12. Trong token request dùng PKCE, tham số nào cho phép authorization server kiểm tra challenge ban đầu?
A. `code_challenge` chứng minh bên đổi code sở hữu client secret
B. Gửi `code_verifier` đã tạo khi bắt đầu PKCE để đổi code lấy token
C. `state` chứng minh bên đổi code sở hữu refresh token đã cấp
D. `nonce` chứng minh bên đổi code sở hữu signing key của IdP
Đáp án đúng: B

Câu 13. Trong Spring Security, helper nào có thể bổ sung PKCE vào Authorization Request tùy chỉnh?
A. `OAuth2AuthorizationRequestCustomizers.withPkce()` cấu hình PKCE
B. `OAuth2AuthorizationCodeGrantFilter.withPkce()` cấu hình PKCE
C. `OidcClientInitiatedLogoutSuccessHandler.withPkce()` cấu hình PKCE
D. `OAuth2AuthorizedClientProviderBuilder.withPkce()` cấu hình PKCE
Đáp án đúng: A

Câu 14. Tham số `state` trong OAuth2 authorization response chủ yếu dùng để bảo vệ điều gì?
A. Xác minh refresh token thuộc về phiên người dùng đã đăng nhập
B. Xác minh chữ ký của JWT ID Token do OIDC provider phát hành
C. `state` nối callback về request ban đầu của browser để phòng CSRF
D. Chọn JWK dùng xác minh chữ ký trên OAuth2 access token
Đáp án đúng: C

Câu 15. Trong Authorization Code flow, điều nào giúp giảm nguy cơ code bị chuyển tới callback trái phép?
A. Đưa client secret vào query string để browser tự kiểm tra
B. Bỏ kiểm tra redirect URI nếu PKCE đã được kích hoạt
C. Kiểm `redirect_uri` đã đăng ký khi cấp authorization code cho client
D. Tái sử dụng một authorization code cho các lần đăng nhập
Đáp án đúng: C

Câu 16. Để yêu cầu OpenID Connect trên Authorization Code flow, scope nào cần có?
A. Scope `email` tự bật kiểm chữ ký ID Token từ server metadata
B. Scope `offline_access` thay cho scope nhận diện giao thức OIDC
C. Scope `profile` yêu cầu cấp access token kiểu client credentials
D. Scope `openid` yêu cầu OIDC authentication và phát hành ID Token
Đáp án đúng: D

Câu 17. Trong OIDC authentication request, `nonce` được đối chiếu với claim nào sau khi nhận ID Token?
A. Claim `exp` của ID Token được kiểm với access token expiry
B. Claim `state` của ID Token được kiểm với cookie browser hiện tại
C. Claim `aud` của ID Token được kiểm với HTTP request path
D. Claim `nonce` của ID Token được kiểm với giá trị đã gửi lúc đầu
Đáp án đúng: D

Câu 18. Trong OAuth2/OIDC Client, cách dùng ID Token và access token nào phù hợp?
A. ID Token dùng làm bearer API; access token dùng làm login session
B. ID Token chứng minh login; access token gọi protected API ở resource server
C. ID Token dùng refresh grant; access token dùng chứng thực `nonce`
D. ID Token dùng ký AuthnRequest; access token dùng trong SAML ACS
Đáp án đúng: B

Câu 19. Khi xác minh OIDC ID Token, claim `iss` được kiểm tra theo giá trị nào?
A. Issuer thuộc provider tin cậy được khai báo trong registration
B. Giá trị `state` nhận từ callback sau khi đổi authorization code
C. Tên client-side JavaScript bundle đã khởi tạo login request
D. Địa chỉ Referer của browser trước lúc đi tới authorization URL
Đáp án đúng: A

Câu 20. Để kiểm chữ ký ID Token JWT, nguồn khóa nào phù hợp?
A. JWK Set bất kỳ trùng với trường `kid` của JWT token
B. JWK Set URL do token tùy ý nêu trong JWT header `jku`
C. JWK Set URL do browser gửi trong query param khi callback
D. JWK Set từ metadata của issuer đã cấu hình tin cậy để kiểm chữ ký
Đáp án đúng: D

Câu 21. Trong OIDC ID Token, claim `aud` thường được đối chiếu với giá trị nào?
A. Redirect URI của browser sau khi OIDC login thành công
B. Authorization endpoint của provider đang cấp ID Token
C. Resource server API endpoint mà user có quyền gọi
D. Client ID của ứng dụng đã đăng ký với OIDC provider
Đáp án đúng: D

Câu 22. Để tùy biến việc lấy UserInfo và tạo `OidcUser` sau login, Spring Security cung cấp lớp nào?
A. `JwtAuthenticationConverter` gọi UserInfo thay cho OidcUser
B. `OAuth2AuthorizedClientService` gọi UserInfo theo principal
C. `OidcUserService` hỗ trợ tải UserInfo rồi xây `OidcUser`
D. `DefaultOAuth2UserService` xử lý ID Token OIDC và SAML
Đáp án đúng: C

Câu 23. Khi cần ánh xạ authorities từ OIDC provider sang quyền nội bộ, extension point nào phù hợp?
A. `ClientRegistrationRepository` ánh xạ authorities của từng user
B. `OAuth2AuthorizationRequestResolver` ánh xạ roles từ refresh
C. `GrantedAuthoritiesMapper` ánh xạ authorities sau khi xác thực
D. `JwtDecoder` gán roles theo request header trong login
Đáp án đúng: C

Câu 24. Trong Servlet MVC, thành phần nào có thể lưu authorized client gắn với request/người dùng?
A. `ClientRegistrationRepository` lưu access token theo user session
B. `OAuth2AuthorizationRequestResolver` lưu refresh token dài hạn
C. `JwtAuthenticationConverter` lưu authorized client theo request
D. `OAuth2AuthorizedClientRepository` gắn token với web context và user
Đáp án đúng: D

Câu 25. Nếu cần lưu authorized clients qua nhiều request, abstraction nào quản lý token gắn với principal ở tầng service?
A. `OAuth2AuthorizedClientService` lưu token theo principal
B. `OAuth2UserService` lưu access token qua các HTTP request
C. `OidcUserService` lưu refresh token của từng principal
D. `ClientRegistrationRepository` lưu token theo principal và grant
Đáp án đúng: A

Câu 26. Trong Servlet request flow, manager nào thường phối hợp registration repo và authorized-client repo để authorize?
A. `OAuth2AuthorizationRequestResolver` tự authorize và lưu token
B. `AuthorizedClientServiceOAuth2AuthorizedClientManager` chuyên cho HTTP context
C. `DefaultOAuth2AuthorizedClientManager` quản lý grant trong HTTP context
D. `DefaultReactiveOAuth2AuthorizedClientManager` cho Servlet HTTP context
Đáp án đúng: C

Câu 27. Để manager tự làm mới access token khi phù hợp và có refresh token, cần provider nào?
A. `ClientRegistrationRepository` có hỗ trợ `refreshToken()` grant
B. `OAuth2AuthorizationRequestResolver` phát hành refresh token
C. `OAuth2UserService` làm mới token bằng OIDC nonce validation
D. `OAuth2AuthorizedClientProvider` hỗ trợ refresh-token grant
Đáp án đúng: D

Câu 28. Vì sao `client_credentials` không phù hợp để chứng minh danh tính người dùng đang đăng nhập?
A. Grant xác thực client, không mang ngữ cảnh login của user cuối
B. Grant dùng ID Token OIDC làm token mặc định cho Resource Server
C. Grant phát sinh SAML Assertion cho từng user của ứng dụng
D. Grant buộc từng user cung cấp username/password cho token endpoint
Đáp án đúng: A

Câu 29. Một scheduled job Servlet cần lấy token OAuth2 ngoài HTTP request; manager nào phù hợp?
A. `AuthorizedClientServiceOAuth2AuthorizedClientManager` dùng cho job ngoài HTTP
B. `OAuth2AuthorizationRequestResolver` cấp token ngoài HTTP request
C. `DefaultOAuth2AuthorizedClientManager` đòi `HttpServletRequest` ngầm
D. `DefaultReactiveOAuth2AuthorizedClientManager` yêu cầu Servlet session
Đáp án đúng: A

Câu 30. Khi dùng WebClient trong ứng dụng Servlet, filter nào gắn authorized access token vào outgoing request?
A. `ServerOAuth2AuthorizedClientExchangeFilterFunction` dành cho servlet
B. `ServletOAuth2AuthorizedClientExchangeFilterFunction` dùng WebClient
C. `OAuth2AuthorizationCodeGrantFilter` thêm token vào WebClient
D. `BearerTokenAuthenticationFilter` thêm token vào WebClient
Đáp án đúng: B

Câu 31. Trong ứng dụng Reactive dùng WebClient, filter nào tích hợp OAuth2 authorized client?
A. `BearerTokenAuthenticationFilter` tạo access token cho WebFlux client
B. `OAuth2LoginAuthenticationFilter` cấu hình WebFlux client
C. `ServerOAuth2AuthorizedClientExchangeFilterFunction` cho WebFlux client
D. `ServletOAuth2AuthorizedClientExchangeFilterFunction` cho WebFlux client
Đáp án đúng: C

Câu 32. Trong WebFlux, repository nào giữ `ClientRegistration` ở dạng reactive?
A. `ReactiveOAuth2AuthorizedClientService` giữ provider metadata
B. `ClientRegistrationRepository` trả về `Mono<ClientRegistration>`
C. `ReactiveClientRegistrationRepository` tra cứu client config
D. `ServerOAuth2AuthorizedClientRepository` lưu client registrations
Đáp án đúng: C

Câu 33. Với ứng dụng WebFlux HTTP request, manager nào xử lý authorization cùng ServerOAuth2AuthorizedClientRepository?
A. `DefaultReactiveOAuth2AuthorizedClientManager` cho WebFlux
B. `DefaultOAuth2AuthorizedClientManager` xử lý grant trong WebFlux
C. `AuthorizedClientServiceOAuth2AuthorizedClientManager` dành WebFlux
D. `OAuth2AuthorizationRequestRedirectFilter` làm WebFlux authorized manager
Đáp án đúng: A

Câu 34. Nếu OIDC Provider hỗ trợ RP-Initiated Logout, class nào chuyển browser tới logout endpoint IdP?
A. `OidcClientInitiatedLogoutSuccessHandler` gọi flow đăng xuất IdP
B. `CookieClearingLogoutHandler` gọi OIDC end-session cho provider
C. `Saml2RelyingPartyInitiatedLogoutSuccessHandler` xử lý OIDC logout
D. `SecurityContextLogoutHandler` chuyển browser tới OIDC end-session
Đáp án đúng: A

Câu 35. Nếu ứng dụng xóa local session nhưng chưa kết thúc phiên SSO tại IdP, kết quả nào có thể xảy ra?
A. Access token đã phát hành bị vô hiệu từ phía IdP khi local logout
B. Refresh token của ứng dụng bị thu hồi khi browser xóa cookie
C. Lần đăng nhập sau có thể SSO tiếp mà không nhập lại mật khẩu
D. Provider chặn đăng nhập kế tiếp đến hết ID Token đã cấp
Đáp án đúng: C

Câu 36. Khi lưu refresh token của OAuth2 Client, biện pháp nào phù hợp?
A. Đặt refresh token vào URL redirect để browser lưu lịch sử
B. Giới hạn truy cập và mã hóa lưu trữ token nhạy cảm khi cần
C. Ghi refresh token vào log để debug các lần refresh thất bại
D. Dùng ID Token thay refresh token để tránh chính sách lưu giữ
Đáp án đúng: B

Câu 37. Với public client chạy trong browser/native app, PKCE giúp giảm rủi ro nào?
A. Thay chức năng xác minh issuer/audience của OIDC ID Token
B. PKCE chặn đổi code bị lộ khi thiếu `code_verifier` tương ứng
C. Cho phép bỏ việc kiểm redirect URI ở authorization server
D. Giúp ẩn client secret đã nhúng sẵn trong source của browser
Đáp án đúng: B

Câu 38. Khi kiểm thử Servlet authorization dựa trên OIDC claims, MockMvc postprocessor nào phù hợp?
A. `user()` tự tạo một ID Token có chữ ký hợp lệ của IdP
B. `jwt()` giả lập OIDC login thông qua authorization code
C. `oauth2Client()` trao đổi authorization code qua token endpoint
D. `oidcLogin()` tạo principal OIDC giả lập cho request test
Đáp án đúng: D

Câu 39. Với `WebTestClient` và `spring-security-test`, công cụ nào giả lập OIDC login trong Reactive?
A. `oidcLogin()` cấu hình OIDC principal vào WebTestClient
B. `mockJwt()` giả lập phiên OAuth2/OIDC browser login
C. `oauth2Client()` chạy authorization code OIDC trong test
D. `mockOidcLogin()` đặt OIDC principal vào WebTestClient
Đáp án đúng: D

Câu 40. Trong request WebClient Reactive, cách nào chọn registration khi có nhiều OAuth2 clients?
A. Đặt redirect URI trong HTTP Accept để chọn OIDC Provider
B. Dùng thuộc tính `clientRegistrationId` của OAuth2 WebClient filter
C. Đặt SAML entityID trong query để chọn OAuth2 authorized client
D. Đặt ID Token vào header Host để Spring tự chọn registration
Đáp án đúng: B
