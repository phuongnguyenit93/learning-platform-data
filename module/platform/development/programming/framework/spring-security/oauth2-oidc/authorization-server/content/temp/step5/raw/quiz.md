Câu 1. Vai trò chính của OAuth 2.0 Authorization Server trong hệ thống Spring là gì?
A. Thay thế mọi repository domain bằng một kho credential chung.
B. Đóng vai OAuth client gọi API của các hệ thống bên ngoài.
C. Nhận access token để bảo vệ API nghiệp vụ từ resource server.
D. Xử lý yêu cầu ủy quyền và cấp token theo các grant hợp lệ.
Đáp án đúng: D

Câu 2. Trong Spring Authorization Server, interface nào truy xuất cấu hình client đã đăng ký?
A. `OAuth2AuthorizationService` chỉ lưu các redirect URI của client.
B. `OAuth2TokenGenerator` truy vấn danh sách client bằng client ID.
C. `RegisteredClientRepository` lưu và tra cứu `RegisteredClient`.
D. `OAuth2AuthorizationConsentService` quản lý client secret.
Đáp án đúng: C

Câu 3. Client secret được cấu hình an toàn trong `RegisteredClient` theo cách nào?
A. Lưu secret dạng rõ và coi TLS là thay thế cho mã hóa.
B. Đặt secret vào claim của access token để server so sánh.
C. Đưa secret vào redirect URI để xác thực lại mỗi lần login.
D. Lưu secret đã băm bằng `PasswordEncoder` tương ứng.
Đáp án đúng: D

Câu 4. Confidential client đăng ký `CLIENT_SECRET_BASIC`; token request xác thực client thế nào?
A. Gửi bearer access token của người dùng để thay client secret.
B. Gửi client secret ở tham số `state` của authorization request.
C. Gửi code challenge làm bằng chứng sở hữu client secret.
D. Gửi client ID và secret bằng HTTP Basic tới token endpoint.
Đáp án đúng: D

Câu 5. Với public client không bảo vệ được secret, phương thức client authentication nào phù hợp?
A. Đăng ký `ClientAuthenticationMethod.NONE` và dùng PKCE.
B. Đăng ký `PRIVATE_KEY_JWT` nhưng cung cấp public key của server.
C. Đăng ký `CLIENT_SECRET_POST` với secret lưu trong localStorage.
D. Đăng ký `CLIENT_SECRET_BASIC` với secret trong mã ứng dụng.
Đáp án đúng: A

Câu 6. Muốn bảo vệ endpoint của Authorization Server mà vẫn có chain khác cho ứng dụng, cách nào phù hợp?
A. Chỉ thêm `@EnableMethodSecurity` mà không cấu hình HTTP security.
B. Tách chain của AS bằng `securityMatcher` trong `SecurityFilterChain`.
C. Đặt `@RestController` cho endpoint AS để Spring tự cấp token.
D. Đặt chung `anyRequest().permitAll()` và dựa vào controller check.
Đáp án đúng: B

Câu 7. Trong authorization-code grant, `/oauth2/authorize` thường dùng để làm gì?
A. Trả signing key bí mật để client tự tạo access token hợp lệ.
B. Cấp refresh token trực tiếp cho client chỉ bằng redirect URI.
C. Nhận client secret để hoàn tất token exchange không cần code.
D. Xử lý yêu cầu ủy quyền rồi redirect về client với code.
Đáp án đúng: D

Câu 8. Để giảm nguy cơ chuyển authorization code đến client sai, server cần kiểm tra điều gì?
A. `redirect_uri` khớp URI được đăng ký cho client liên quan.
B. `redirect_uri` trùng domain của resource server bất kỳ.
C. `redirect_uri` phải trỏ về endpoint `/oauth2/token` của server.
D. `redirect_uri` chứa cùng giá trị như tham số `state` của client.
Đáp án đúng: A

Câu 9. Tham số `state` trong OAuth authorization request giúp client xử lý vấn đề nào?
A. Xác định thuật toán ký JWT mà Authorization Server sẽ sử dụng.
B. Gắn response với request ban đầu để chống giả mạo luồng đăng nhập.
C. Làm proof key được so khớp với `code_verifier` ở token endpoint.
D. Thay thế redirect URI đã được lưu trong cấu hình registered client.
Đáp án đúng: B

Câu 10. Với PKCE phương thức `S256`, `code_challenge` được tạo từ `code_verifier` như thế nào?
A. Băm MD5 verifier rồi chuyển digest sang dạng hexadecimal.
B. Băm SHA-256 verifier rồi mã hóa Base64URL không padding.
C. Ký verifier bằng client secret và dùng chữ ký làm challenge.
D. Mã hóa Base64URL verifier trực tiếp mà không cần băm SHA-256.
Đáp án đúng: B

Câu 11. Trong PKCE authorization-code flow, client gửi `code_verifier` vào giai đoạn nào?
A. Gửi kèm request đến resource server sau khi nhận access token.
B. Gửi trong request đầu tiên đến authorization endpoint thay challenge.
C. Gửi khi gọi JWKS endpoint để tải khóa công khai của server.
D. Gửi lúc đổi authorization code lấy token tại token endpoint.
Đáp án đúng: D

Câu 12. Thuộc tính nào của Spring Authorization Server yêu cầu PKCE với registered client?
A. Đặt `ClientSettings.requireAuthorizationConsent(true)` cho client đó.
B. Đặt `TokenSettings.reuseRefreshTokens(false)` cho client đó.
C. Đặt `ClientSettings.requireProofKey(true)` cho client đó.
D. Đặt `TokenSettings.accessTokenTimeToLive(...)` cho client đó.
Đáp án đúng: C

Câu 13. Authorization code đã đổi lấy token thành công được gửi lại lần nữa; cách xử lý đúng là gì?
A. Chấp nhận khi client đổi lại `state` khác ở token endpoint.
B. Từ chối code đã dùng lại, thường trả lỗi `invalid_grant`.
C. Tạo authorization code mới từ code cũ và bỏ qua redirect URI.
D. Cấp tiếp access token vì code còn trong thời gian hiệu lực.
Đáp án đúng: B

Câu 14. Client đổi authorization code lấy token tại endpoint mặc định nào của Spring Authorization Server?
A. Gửi token request đến `/oauth2/authorize` với client ID.
B. Gửi token request đến `/oauth2/token` với grant phù hợp.
C. Gửi token request đến `/.well-known/openid-configuration`.
D. Gửi token request đến `/oauth2/jwks` cùng authorization code.
Đáp án đúng: B

Câu 15. Với `client_credentials` grant, token đại diện cho chủ thể nào trong yêu cầu?
A. Cấp quyền cho client, không yêu cầu phiên login người dùng.
B. Quyền được cấp từ ID token đã được UserInfo endpoint ký.
C. Quyền được cấp cho resource owner sau khi nhập mật khẩu ở browser.
D. Quyền được cấp qua authorization code gắn với redirect URI.
Đáp án đúng: A

Câu 16. Khi Authorization Server yêu cầu user consent cho scope, người dùng thực hiện việc gì?
A. Chấp thuận các quyền mà client đề nghị trước khi cấp ủy quyền.
B. Xác nhận client secret qua giao diện đăng nhập của resource server.
C. Chọn thuật toán hash cho PKCE trước khi token được phát hành.
D. Tạo cặp khóa ký JWT mới thay cho JWKSource đang chạy.
Đáp án đúng: A

Câu 17. Spring Authorization Server dùng service nào để ghi nhận consent của user cho client?
A. `RegisteredClientRepository` ghi từng consent vào client secret.
B. `OAuth2AuthorizationService` chỉ lưu các role được người dùng chấp thuận.
C. `OAuth2AuthorizationConsentService` quản lý các consent đã lưu.
D. `OAuth2TokenCustomizer` thay database lưu thông tin consent.
Đáp án đúng: C

Câu 18. Thành phần nào lưu trạng thái authorization, authorization code và token liên quan?
A. `OAuth2AuthorizationService` lưu trạng thái grant và token.
B. `OAuth2AuthorizationConsentService` cấp phát authorization code.
C. `JWKSource` ghi trạng thái refresh token theo từng principal.
D. `RegisteredClientRepository` giữ mọi token đang có hiệu lực.
Đáp án đúng: A

Câu 19. Client có refresh token hợp lệ; để lấy access token mới, nó dùng grant nào?
A. Gọi JWKS endpoint kèm refresh token để xin ký access token.
B. Gửi `grant_type=refresh_token` cùng refresh token tới token endpoint.
C. Gửi lại authorization request với `response_type=refresh_token`.
D. Gọi UserInfo endpoint kèm ID token để nhận access token mới.
Đáp án đúng: B

Câu 20. Muốn phát refresh token mới khi dùng refresh-token grant thay vì dùng lại token cũ, cấu hình nào?
A. Đặt `TokenSettings.accessTokenFormat(REFERENCE)` cho client.
B. Cấu hình `TokenSettings.reuseRefreshTokens(false)` cho client đó.
C. Đặt `ClientSettings.requireProofKey(false)` cho registered client.
D. Đặt `ClientSettings.requireAuthorizationConsent(false)` cho client.
Đáp án đúng: B

Câu 21. Khi muốn phát opaque/reference access token thay vì JWT self-contained, cấu hình nào phù hợp?
A. Dùng `AuthorizationServerSettings.issuer("opaque")` cho server.
B. Dùng `ClientSettings.tokenEndpointAuthenticationMethod(NONE)`.
C. Cấu hình `accessTokenFormat(OAuth2TokenFormat.REFERENCE)`.
D. Dùng `JWKSource` với private key có thuật toán HMAC mặc định.
Đáp án đúng: C

Câu 22. Muốn thêm claim nghiệp vụ vào JWT access token đang phát hành, hook nào của Spring phù hợp?
A. Dùng `OAuth2TokenCustomizer<JwtEncodingContext>` để thêm claim.
B. Đăng ký `PasswordEncoder` để chỉnh payload JWT lúc hash secret.
C. Đăng ký `AuthenticationEntryPoint` để sửa claim trong response.
D. Đăng ký `RegisteredClientRepository` để viết lại token đã ký.
Đáp án đúng: A

Câu 23. JWT do Authorization Server ký bất đối xứng được resource server kiểm tra chữ ký bằng gì?
A. Refresh token của user được lưu tại authorization service.
B. Client secret của ứng dụng gửi ở authorization-code request.
C. Public key của server được công bố qua endpoint JWKS.
D. Private key tải từ JWKS endpoint bằng client credentials.
Đáp án đúng: C

Câu 24. Khi xoay khóa ký JWT, biện pháp nào giúp token cũ còn hợp lệ tiếp tục được xác minh?
A. Yêu cầu resource server bỏ bước kiểm tra JWT signature trong lúc xoay.
B. Xóa tất cả key cũ khỏi JWKS ngay khi phát token đầu tiên bằng key mới.
C. Duy trì public key cũ trong JWKS cho đến khi token liên quan hết hạn.
D. Thay đổi issuer của token cũ để khớp private key vừa triển khai.
Đáp án đúng: C

Câu 25. Trong cấu hình `AuthorizationServerSettings`, giá trị `issuer` có vai trò nào?
A. Xác định client ID được dùng để xử lý mọi OAuth grant.
B. Xác định tên cookie phiên đăng nhập của từng resource owner.
C. Xác định URL của resource server sẽ lưu tất cả refresh token.
D. Xác định danh tính issuer nhất quán trong metadata và token.
Đáp án đúng: D

Câu 26. Client muốn nhận ID token theo OpenID Connect; scope đặc biệt nào thường cần có?
A. Yêu cầu scope `email` để Authorization Server phát ID token.
B. Yêu cầu scope `offline_access` thay cho mọi OpenID scope.
C. Yêu cầu scope `openid` trong luồng OIDC được hỗ trợ.
D. Yêu cầu scope `profile` dù không khai báo `openid`.
Đáp án đúng: C

Câu 27. ID token OIDC chủ yếu nhằm cung cấp thông tin gì tới client?
A. Cấp quyền trực tiếp gọi mọi resource API thay cho access token.
B. Cung cấp thông tin xác thực người dùng: `iss`, `sub`, `aud`.
C. Chứa client secret được mã hóa để client xác thực về sau.
D. Chứa refresh token giúp ứng dụng không cần token endpoint.
Đáp án đúng: B

Câu 28. Trong OIDC, tham số `nonce` do client gửi ở authentication request giúp mục đích gì?
A. Thay thế client authentication khi gọi token endpoint.
B. Thay thế `code_verifier` trong PKCE authorization-code flow.
C. Liên kết ID token với request gốc để giảm nguy cơ replay.
D. Xác định thời gian tồn tại của refresh token trong service.
Đáp án đúng: C

Câu 29. Khi bật OIDC trong Spring Authorization Server, client tra cấu hình provider từ endpoint nào?
A. Đọc client consent qua `/oauth2/authorize` không có request.
B. Đọc token metadata ở `/oauth2/token` bằng HTTP GET.
C. Đọc danh sách scope qua `/userinfo` mà không kèm access token.
D. Đọc OIDC discovery ở `/.well-known/openid-configuration`.
Đáp án đúng: D

Câu 30. Client OIDC muốn lấy claims người dùng từ UserInfo endpoint, thông tin nào thường cần gửi?
A. Access token hợp lệ có quyền truy cập UserInfo phù hợp.
B. Refresh token hợp lệ kèm `state` từ authorization request.
C. Authorization code chưa dùng cùng `code_challenge` đã đăng ký.
D. Client secret qua query string thay vì bearer access token.
Đáp án đúng: A

Câu 31. Chọn cặp mô tả đúng mục đích hai OAuth endpoint `/oauth2/introspect` và `/oauth2/revoke`?
A. Introspect kiểm trạng thái token; revoke yêu cầu thu hồi token.
B. Introspect tải khóa công khai; revoke đổi cấu hình registered client.
C. Introspect tạo ID token; revoke đổi refresh token thành access token.
D. Introspect cấp authorization code; revoke ghi consent của user.
Đáp án đúng: A

Câu 32. Kiểm thử authorization-code + PKCE của server nên bao gồm tình huống nào để phát hiện lỗi bảo mật?
A. Luồng hợp lệ và bỏ qua request lỗi vì client đã đăng ký thành công.
B. Luồng hợp lệ và tắt kiểm tra state để giản lược số lần redirect.
C. Luồng hợp lệ và tự tạo JWT không kiểm chứng bằng signing key.
D. Chạy luồng hợp lệ và từ chối verifier sai, redirect sai, code tái dùng.
Đáp án đúng: D
