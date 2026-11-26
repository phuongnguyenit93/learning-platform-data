Câu 1. Muốn viết test MockMvc với các helper kiểm thử bảo mật của Spring, dependency nào phù hợp?
A. Thêm `spring-security-oauth2-client` để chạy MockMvc security test.
B. Thêm `spring-security-test` vào test classpath của ứng dụng.
C. Thêm `spring-security-web` để tự có mọi test postprocessor.
D. Thêm `spring-security-config` thay cho thư viện test.
Đáp án đúng: B

Câu 2. Với MockMvc được xây từ `WebApplicationContext`, thao tác nào áp dụng tích hợp Spring Security test?
A. Dùng `.defaultRequest(get("/").with(csrf()))` thay SecurityFilterChain.
B. Dùng `.alwaysExpect(status().isOk())` khi tạo MockMvc builder.
C. Dùng `.addFilters(new CorsFilter(...))` để thay toàn bộ security.
D. Dùng `.apply(springSecurity())` khi tạo MockMvc builder.
Đáp án đúng: D

Câu 3. Để kiểm chứng một endpoint thực sự bị chặn bởi HTTP security filter, môi trường MockMvc cần gì?
A. Giữ security filter chain trong pipeline của request test.
B. Chỉ gọi service method rồi suy ra HTTP filter đã kiểm quyền.
C. Vô hiệu toàn bộ filter bằng `addFilters=false` trước assertion.
D. Mock controller rồi bỏ qua kiểm tra bằng security filter.
Đáp án đúng: A

Câu 4. Khi sử dụng `@WithMockUser` không truyền thuộc tính, principal và role mặc định nào được tạo?
A. Username `guest` cùng GrantedAuthority `SCOPE_USER`.
B. Username `user` cùng GrantedAuthority `ROLE_USER`.
C. Username `anonymousUser` cùng GrantedAuthority `ROLE_ANONYMOUS`.
D. Username `admin` cùng GrantedAuthority `ROLE_ADMIN`.
Đáp án đúng: B

Câu 5. Trong `@WithMockUser(roles="ADMIN")`, Spring Security thường đưa authority nào vào Authentication?
A. Authority `ADMIN` trực tiếp mà không bổ sung prefix.
B. Authority `SCOPE_ADMIN` do chuyển role thành OAuth scope.
C. Authority `PERMISSION_ADMIN` do tạo ACL permission.
D. Dùng authority `ROLE_ADMIN` với tiền tố role mặc định.
Đáp án đúng: D

Câu 6. Nếu annotation là `@WithMockUser(authorities="invoice:approve")`, authority được thiết lập thế nào?
A. Tự đổi thành OAuth scope `SCOPE_invoice:approve`.
B. Chuyển chuỗi thành role `ROLE_INVOICE_APPROVE` mặc định.
C. Giữ authority `invoice:approve` đúng như chuỗi khai báo.
D. Tự thêm `ROLE_` rồi thành `ROLE_invoice:approve`.
Đáp án đúng: C

Câu 7. Khi test cần principal được tải bằng `UserDetailsService` của ứng dụng, annotation nào phù hợp?
A. Dùng `@WithUserDetails("alice")` để nạp user trong context.
B. Dùng `@WithMockUser("alice")` để bắt buộc truy vấn kho người dùng.
C. Dùng `@WithSecurityContext` mà không cung cấp factory.
D. Dùng `@WithAnonymousUser` và đặt username ở test method.
Đáp án đúng: A

Câu 8. Khi cần principal tùy biến có tenant và permissions phức tạp, extension test nào hữu ích?
A. Định nghĩa `@WithUserDetails` rồi bỏ UserDetailsService trong context.
B. Định nghĩa `@WithAnonymousUser` để chèn DTO vào Authentication.
C. Định nghĩa `@WithMockUser` thêm tùy ý field tenant vào annotation.
D. Định nghĩa `@WithSecurityContext` và factory sinh SecurityContext.
Đáp án đúng: D

Câu 9. Một class test gắn `@WithMockUser` nhưng một test method cần anonymous; nên dùng annotation nào trên method?
A. Dùng `@WithUserDetails` nhưng truyền chuỗi username rỗng.
B. Gắn `@WithAnonymousUser` lên method cần anonymous.
C. Dùng `@WithSecurityContext` không có factory và không principal.
D. Dùng `@WithMockUser(roles={})` để mô phỏng anonymous.
Đáp án đúng: B

Câu 10. Một test MockMvc cần gán vai trò MANAGER riêng cho request GET; cách nào phù hợp?
A. Dùng `.with(user("alice").roles("MANAGER"))`.
B. Dùng `.with(jwt().username("alice"))`.
C. Gọi `.with(csrf().roles("MANAGER"))` trên request.
D. Gọi `.with(anonymous().roles("MANAGER"))` trên request.
Đáp án đúng: A

Câu 11. Khác biệt quan trọng giữa MockMvc `.with(httpBasic(...))` và `.with(user(...))` là gì?
A. `httpBasic` bypass filter chain; `user` phát header WWW-Authenticate.
B. `httpBasic` gắn SecurityContext; `user` mã hóa password thật.
C. `httpBasic` tự phát JWT; `user` kiểm password trong database.
D. `httpBasic` gửi credential; `user` gắn Authentication giả lập.
Đáp án đúng: D

Câu 12. Đã có một Authentication tùy biến được tạo trong test; dùng MockMvc postprocessor nào để gắn nó?
A. Dùng `.with(httpBasic(customAuth))` để gắn principal tùy biến.
B. Dùng `.with(authentication(customAuth))` cho request test.
C. Dùng `.with(oauth2Client(customAuth))` cho mọi authentication.
D. Dùng `.with(csrf(customAuth))` để thay SecurityContext.
Đáp án đúng: B

Câu 13. MockMvc test POST bị CSRF bảo vệ và cần đường đi thành công; request postprocessor nào nên thêm?
A. Thêm `.with(csrf())` để gắn CSRF token hợp lệ.
B. Thêm `.with(jwt())` để buộc mọi POST được miễn CSRF.
C. Thêm `.with(httpBasic())` để bỏ qua CSRF filter.
D. Thêm `.with(user())` để tự sinh CSRF token hợp lệ.
Đáp án đúng: A

Câu 14. Muốn kiểm tra CSRF filter từ chối token không hợp lệ, helper MockMvc nào phù hợp?
A. Dùng `.with(user().invalidCsrf())` rồi assert bị từ chối.
B. Dùng `.with(httpBasic().invalidToken())` rồi assert status 403.
C. Dùng `.with(csrf().useInvalidToken())` rồi assert bị từ chối.
D. Dùng `.with(csrf().disable())` rồi assert status 403.
Đáp án đúng: C

Câu 15. Để kiểm thử JWT resource server Servlet mà không gọi JwtDecoder thật, MockMvc cung cấp gì?
A. Dùng `.with(oauth2Login())` để bắt buộc decode Bearer JWT.
B. Dùng `.with(jwt())` để tạo JwtAuthenticationToken giả lập.
C. Dùng `.with(httpBasic())` để tạo token theo JWK của server.
D. Dùng `.with(csrf())` để biến request thành JWT authentication.
Đáp án đúng: B

Câu 16. Muốn test `hasAuthority('SCOPE_orders:read')` bằng MockMvc JWT giả, cần bổ sung gì?
A. Dùng `.with(jwt().authorities(...))` với `SCOPE_orders:read`.
B. Đặt header Origin thành `SCOPE_orders:read` rồi assert 200.
C. Đặt role `orders:read` trong `.with(csrf().roles(...))`.
D. Đặt claim issuer thành `SCOPE_orders:read` thay cho authority.
Đáp án đúng: A

Câu 17. Ứng dụng dùng OAuth2 opaque token resource server; MockMvc helper nào mô phỏng principal token?
A. Dùng `.with(oauth2Login())` để thực hiện introspection thật.
B. Dùng `.with(jwt())` để buộc opaque token được decode như JWT.
C. Dùng `.with(opaqueToken())` cho principal token giả.
D. Dùng `.with(oidcLogin())` làm opaque token.
Đáp án đúng: C

Câu 18. Để kiểm thử controller của ứng dụng đã đăng nhập bằng OAuth2 Login Servlet, MockMvc helper nào phù hợp?
A. Dùng `.with(jwt())` để mô phỏng OAuth2 login browser session.
B. Dùng `.with(opaqueToken())` để phát OAuth2 authorization code.
C. Dùng `.with(oauth2Login())` để gắn OAuth2AuthenticationToken.
D. Dùng `.with(httpBasic())` để tạo OAuth2AuthorizedClient tự động.
Đáp án đúng: C

Câu 19. Khi controller cần principal `OidcUser` với ID token, nên dùng helper MockMvc nào?
A. Dùng `.with(user())` để tự tạo ID token theo claim openid.
B. Dùng `.with(oidcLogin())` để mô phỏng đăng nhập OpenID Connect.
C. Dùng `.with(jwt())` để biến JwtAuthenticationToken thành OidcUser.
D. Dùng `.with(oauth2Client())` để sinh `OidcIdToken` cho principal.
Đáp án đúng: B

Câu 20. Client controller cần OAuth2AuthorizedClient cho một registration; MockMvc postprocessor nào phù hợp?
A. Dùng `.with(httpBasic("my-client"))` để đăng ký OAuth2 client.
B. Dùng `.with(oauth2Client("my-client"))` cho request.
C. Dùng `.with(csrf("my-client"))` để giả registration trong session.
D. Dùng `.with(oidcLogin("my-client"))` để cấp OAuth2AuthorizedClient.
Đáp án đúng: B

Câu 21. Khi API HTTP Basic yêu cầu đăng nhập nhưng MockMvc gửi request không có credential, assertion nào phù hợp?
A. Kiểm tra HTTP 401 và authentication challenge theo cấu hình Basic.
B. Kiểm tra HTTP 403 vì mọi request chưa đăng nhập đều đã xác thực.
C. Kiểm tra HTTP 200 vì Spring Security mặc định cho anonymous vào API.
D. Kiểm tra HTTP 404 vì server tự ẩn mọi endpoint có security.
Đáp án đúng: A

Câu 22. Test client đã xác thực nhưng thiếu `ROLE_ADMIN` truy cập endpoint admin, kết quả nào thường đúng?
A. Assert 200 vì user giả đã tự vượt authorization policy.
B. Assert 401 vì thiếu role được xem giống thiếu credential.
C. Assert HTTP 403 cho principal có role không phù hợp.
D. Assert 302 vì thiếu role kích hoạt luồng login mới.
Đáp án đúng: C

Câu 23. Để bắt lỗi IDOR khi đọc `/orders/{id}`, tập trường hợp test nào phù hợp?
A. Cho mọi user truy cập rồi lọc order của tenant bên UI.
B. Cho owner truy cập rồi suy ra mọi ID khác đều đã được bảo vệ.
C. Cho owner truy cập và từ chối user khác với cùng order ID.
D. Cho ADMIN truy cập và bỏ qua case principal có role USER.
Đáp án đúng: C

Câu 24. Muốn kiểm chứng `@PreAuthorize` trên service method, test cần gọi service qua thành phần nào?
A. Gọi đối tượng service bằng `new` để tránh tạo test context.
B. Gọi private method trực tiếp rồi bỏ qua AOP security advisor.
C. Gọi repository mock để kiểm thử method security.
D. Gọi service bean qua Spring proxy có method security.
Đáp án đúng: D

Câu 25. Vì sao test với `.with(user(...))` không đủ để kiểm tra password encoder hoặc authentication provider?
A. Postprocessor khởi tạo JWT signature và kiểm tra khóa ký thật.
B. Postprocessor thực thi UserDetailsService với mọi username đầu vào.
C. Postprocessor gửi Basic header nên AuthenticationManager luôn chạy.
D. Request nhận Authentication giả, không qua đăng nhập thật.
Đáp án đúng: D

Câu 26. Khi dùng `WebTestClient.bindToApplicationContext(context)` cho WebFlux security, bước tích hợp nào phù hợp?
A. Áp `SecurityMockMvcConfigurers.springSecurity()` cho WebFlux client.
B. Áp `SecurityMockServerConfigurers.springSecurity()` vào builder.
C. Áp `MockMvcBuilders.webAppContextSetup(context)` lên WebTestClient.
D. Áp `csrf()` của MockMvc trực tiếp vào application context.
Đáp án đúng: B

Câu 27. Để đóng vai user `alice` có role STAFF cho một WebTestClient request, cách nào phù hợp?
A. Dùng `.mutateWith(mockJwt().username("alice"))` trên client.
B. Dùng `.with(user("alice").roles("STAFF"))` của MockMvc builder.
C. Dùng `.mutateWith(csrf().roles("STAFF"))` cho user.
D. Dùng `.mutateWith(mockUser("alice").roles("STAFF"))`.
Đáp án đúng: D

Câu 28. Với WebFlux POST có CSRF protection, helper WebTestClient nào tạo CSRF token cho request?
A. Dùng `.with(csrf())` của MockMvcRequestPostProcessors.
B. Dùng `.mutateWith(mockJwt())` để vô hiệu CSRF kiểm tra.
C. Dùng `.mutateWith(csrf())` cho WebTestClient.
D. Dùng `.mutateWith(mockUser())` gắn CSRF.
Đáp án đúng: C

Câu 29. Để mô phỏng bearer JWT của reactive resource server bằng WebTestClient, helper nào phù hợp?
A. Dùng `.with(jwt())` của Servlet request postprocessor.
B. Dùng `.mutateWith(mockOidcLogin())` để sinh bearer token thật.
C. Dùng `.mutateWith(mockJwt())` để tạo Authentication JWT giả.
D. Dùng `.mutateWith(mockOAuth2Login())` để validate chữ ký JWT.
Đáp án đúng: C

Câu 30. WebFlux controller có `@AuthenticationPrincipal OidcUser`; helper nào tạo ngữ cảnh OIDC giả lập?
A. Dùng `.mutateWith(mockOidcLogin())` để gắn OidcUser.
B. Dùng `.mutateWith(csrf())` để thêm OIDC authentication.
C. Dùng `.mutateWith(mockUser())` để tạo ID token mặc định.
D. Dùng `.mutateWith(mockJwt())` để tự ánh xạ sang OidcUser.
Đáp án đúng: A

Câu 31. Test method security trong service reactive có `@PreAuthorize` và trả `Mono`; nên xác minh điều gì?
A. Dùng ThreadLocal ở test thread để thay cho Reactor Context.
B. Kiểm tra object `Mono` được tạo và coi security đã chạy.
C. Dựa vào MockMvc để suy ra reactive service đã chạy.
D. Subscribe `Mono` để assert quyền theo Reactor Context.
Đáp án đúng: D

Câu 32. Để ngăn hồi quy bảo mật Servlet và WebFlux, bộ test nên bao gồm trường hợp nào?
A. Ca đúng quyền, 401 thiếu auth, 403 thiếu role và CSRF.
B. Test controller sau khi tắt filter rồi dựa vào response body.
C. Chạy request admin thành công và bỏ qua các trạng thái từ chối.
D. Assert JWT có claim role và không gọi endpoint chứa policy.
Đáp án đúng: A
