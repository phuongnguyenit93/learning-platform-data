Câu 01. Trong đăng nhập SAML 2.0, ứng dụng Spring Security nhận xác thực từ IdP đóng vai trò nào?
A. Resource Server bảo vệ API bằng bearer access token
B. Identity Provider (IdP) xác thực người dùng cho các SP
C. Authorization Server phát hành OAuth2 access token
D. Service Provider (SP) tin khẳng định danh tính từ IdP
Đáp án đúng: D

Câu 02. Trong Spring Security SAML2, repository nào lưu các relying-party registration?
A. `OAuth2AuthorizedClientService` lưu cấu hình SAML SP/IdP
B. `RelyingPartyRegistrationRepository` lưu cấu hình SP/IdP
C. `Saml2AuthenticationRequestRepository` lưu cấu hình SAML SP/IdP
D. `ClientRegistrationRepository` lưu cấu hình SAML SP/IdP
Đáp án đúng: B

Câu 03. Một `RelyingPartyRegistration` cần thông số nào để xử lý SAML SSO?
A. OIDC issuer URI, client secret và JWKS của IdP
B. IdP logout endpoint, NameIDPolicy và entity ID phía IdP
C. HTTP session cookie, CSRF token và redirect URL
D. SP entity ID, ACS URL và chứng thư xác minh của IdP
Đáp án đúng: D

Câu 04. Trong ứng dụng có nhiều IdP SAML, `registrationId` giúp Spring Security làm gì?
A. Chọn RelyingPartyRegistration tương ứng với IdP cần dùng
B. Chọn quyền ADMIN từ thuộc tính NameID của user
C. Chọn session ID mới theo tên của SAML response
D. Chọn loại XML Signature từ tham số HTTP redirect
Đáp án đúng: A

Câu 05. Với cấu hình mặc định, đường dẫn nào khởi tạo đăng nhập SAML 2.0 cho một registration?
A. `/oauth2/authorization/{registrationId}` khởi tạo OAuth2 login
B. `/login/oauth2/code/{registrationId}` tiếp nhận authorization code
C. `/login/saml2/sso/{registrationId}` tiếp nhận SAML Response
D. `/saml2/authenticate/{registrationId}` khởi tạo AuthnRequest
Đáp án đúng: D

Câu 06. Theo cấu hình mặc định, endpoint nào nhận SAML Response qua Assertion Consumer Service?
A. `/saml2/authenticate/{registrationId}` là ACS của Spring Security
B. `/oauth2/authorization/{registrationId}` là ACS của Spring
C. `/login/saml2/sso/{registrationId}` là ACS của Spring Security
D. `/login/oauth2/code/{registrationId}` là ACS của Spring
Đáp án đúng: C

Câu 07. Trong SAML SP-initiated SSO, AuthnRequest có chức năng chính nào?
A. SP gửi yêu cầu xác thực tới IdP trước khi nhận Response
B. IdP gửi LogoutResponse tới SP sau khi kết thúc phiên
C. IdP gửi chứng nhận SSL tới SP trước khi nhận Response
D. SP gửi JWT access token tới Resource Server để đăng nhập
Đáp án đúng: A

Câu 08. Trong SAML 2.0, Assertion được IdP phát hành chủ yếu mang thông tin gì?
A. Assertion nêu chủ thể, xác thực và attributes liên quan
B. Danh sách private keys IdP và certificates của phía SP
C. Các endpoint SSO/SLO và certificates của IdP metadata
D. HTTP routing, controller mapping và headers của ứng dụng
Đáp án đúng: A

Câu 09. Khi kiểm tra SAML Response có chữ ký, khóa nào cần được dùng để xác minh?
A. Khóa bí mật đăng nhập của người dùng vừa nhập ở IdP
B. Public key IdP đáng tin đã được gắn với registration
C. Khóa ký riêng của SP để xác minh các Response nhận được
D. Khóa công khai được gửi từ URL kèm SAML Response chưa tin
Đáp án đúng: B

Câu 10. Một SAML Response có XML Signature hợp lệ nhưng claims trích xuất nằm ngoài vùng đã ký; xử lý thế nào?
A. Dựa vào AudienceRestriction để bỏ qua phạm vi chữ ký XML
B. Từ chối: claims ngoài phần ký chưa có bảo đảm xác thực
C. Coi chữ ký ở phần tử khác là hợp lệ cho claims chưa được ký
D. Dựa vào session cookie để xác nhận các claims không có chữ ký
Đáp án đúng: B

Câu 11. Trong SAML Assertion, AudienceRestriction nên khớp với thông tin nào của SP?
A. Định danh entity ID của SP được phép nhận Assertion
B. URI của OpenID Connect UserInfo endpoint tại IdP
C. Đường dẫn của HTTP logout controller tại ứng dụng
D. Tên role mặc định mà ứng dụng Spring cấp cho user
Đáp án đúng: A

Câu 12. Kiểm tra Recipient của SubjectConfirmationData trong SAML giúp bảo vệ điều gì?
A. Recipient chỉ ra OAuth2 client secret dùng cho OIDC
B. Recipient chỉ ra attributes để ánh xạ role của user
C. Recipient trỏ đúng ACS endpoint tiếp nhận tại SP
D. Recipient chỉ ra bản ghi audit lưu ở database SP
Đáp án đúng: C

Câu 13. Với đăng nhập SAML bắt đầu từ SP, `InResponseTo` dùng để kiểm tra gì?
A. Response chứa access token cho đúng resource server
B. Response chứa đủ các SAML attributes ứng dụng yêu cầu
C. `InResponseTo` khớp ID AuthnRequest SP đã gửi
D. Response dùng đúng URL đăng xuất trên browser hiện tại
Đáp án đúng: C

Câu 14. Các điều kiện `NotBefore` và `NotOnOrAfter` của SAML Assertion nhằm kiểm soát gì?
A. Khoảng thời gian refresh token OAuth2 còn được sử dụng
B. Khoảng thời gian Assertion được phép sử dụng để xác thực
C. Khoảng thời gian TLS certificate web server còn hiệu lực
D. Khoảng thời gian SP giữ cookie remember-me trên trình duyệt
Đáp án đúng: B

Câu 15. Để giảm nguy cơ phát lại Assertion đã được chấp nhận, biện pháp nào phù hợp?
A. Tăng thời gian lưu HTTP session thay cho kiểm tra replay ID
B. Nhận lại Assertion cũ nếu chữ ký IdP vẫn xác minh đúng
C. Nới thời gian Assertion để tránh đồng hồ SP và IdP lệch
D. Lưu ID Assertion đã dùng và từ chối replay đến khi hết hạn
Đáp án đúng: D

Câu 16. Trong metadata SAML, `entityID` của IdP có ý nghĩa chính gì?
A. Là URI ACS mà trình duyệt POST SAML Response vào SP
B. Là mật khẩu quản trị IdP cần đưa vào cấu hình SP
C. Là session cookie để trình duyệt nối tiếp SSO login
D. Định danh thực thể IdP trong quan hệ tin cậy SAML
Đáp án đúng: D

Câu 17. Khi IdP xoay vòng chứng thư ký SAML, SP cần làm gì để giữ xác thực an toàn?
A. Cập nhật chứng thư xác minh IdP đáng tin khi chuyển khóa
B. Thay chứng thư xác minh bằng key từ response chưa được tin
C. Đổi entityID từng user để dùng chứng thư ký mới của IdP
D. Bỏ bước kiểm chữ ký trong thời gian xoay vòng chứng thư
Đáp án đúng: A

Câu 18. Với SAML Assertion được mã hóa cho SP, thành phần nào cần cấu hình để giải mã?
A. Khóa riêng của SP tương ứng chứng thư dùng mã hóa
B. Khóa công khai ký của IdP lấy từ metadata công bố
C. Khóa công khai TLS của endpoint ACS trên web server
D. Khóa chia sẻ giữa các consumer trong Kafka cluster
Đáp án đúng: A

Câu 19. Để ánh xạ SAML attributes thành quyền Spring, nguồn dữ liệu nào phù hợp?
A. HTTP Referer do client đính kèm khi callback SAML
B. Tên XML metadata chưa được kiểm tra nguồn đáng tin cậy
C. Tham số `role` do trình duyệt gửi trong query string
D. Attributes từ `Saml2AuthenticatedPrincipal` đã xác minh
Đáp án đúng: D

Câu 20. Khi xử lý SAML Single Logout, kiểm tra nào quan trọng tại ranh giới tin cậy?
A. Tin NameID nhận qua query string không có signature
B. Xóa cookie trên client và bỏ qua trạng thái IdP
C. Đăng xuất các session theo tên tài khoản chưa xác minh
D. Kiểm thông điệp logout có xác thực và đúng phiên SSO
Đáp án đúng: D

Câu 21. Trong Spring Security, cấu hình nào dành cho đăng nhập OIDC dựa trên OAuth2?
A. `saml2Login()` xử lý authorization code của OIDC Provider
B. `oauth2Login()` kết nối luồng xác thực với OIDC Provider
C. `oauth2ResourceServer()` khởi tạo đăng nhập browser OIDC
D. `formLogin()` kiểm tra ID Token do OIDC Provider trả về
Đáp án đúng: B

Câu 22. Trong OpenID Connect, ID Token chủ yếu chứng minh thông tin nào với RP?
A. ID Token liệt kê các SAML assertions của nhà cung cấp
B. Access token cấp quyền API của những resource server khác
C. ID Token mô tả kết quả đăng nhập và danh tính người dùng
D. ID Token chứa thông tin client discovery của provider
Đáp án đúng: C

Câu 23. Trong Spring Security OAuth2/OIDC, repository nào chứa cấu hình client và provider?
A. `ReactiveJwtDecoder` lưu client ID và OIDC provider settings
B. `ClientRegistrationRepository` lưu client ID cùng IdP config
C. `OAuth2AuthorizedClientRepository` lưu provider metadata gốc
D. `RelyingPartyRegistrationRepository` lưu OIDC client settings
Đáp án đúng: B

Câu 24. Khi khai báo OIDC `issuer-uri`, cơ chế discovery giúp lấy thông tin nào từ provider?
A. Chứng thư ký SAML, ACS URL và NameIDPolicy của IdP
B. UserInfo attributes và ID Token của user đang đăng nhập
C. Dữ liệu HTTP session hiện tại của browser tại ứng dụng
D. Issuer, token/authorization endpoints và JWKS URI của IdP
Đáp án đúng: D

Câu 25. Khi xác minh ID Token, claim `iss` cần được đối chiếu với giá trị nào?
A. Địa chỉ IP do proxy chuyển tiếp trong request callback
B. Issuer đã được tin trong cấu hình client/provider đang dùng
C. Địa chỉ Referer của trình duyệt trước khi redirect tới RP
D. Giá trị state được client gửi vào OAuth2 authorization URL
Đáp án đúng: B

Câu 26. Trong OIDC ID Token, claim `aud` dùng để kiểm tra điều gì?
A. ID Token nhắm tới SAML ACS endpoint của ứng dụng
B. ID Token nhắm tới client ID đã đăng ký của RP
C. ID Token nhắm tới Kafka group xử lý login event
D. ID Token trỏ tới URL refresh token của trình duyệt
Đáp án đúng: B

Câu 27. Nếu ID Token đã vượt `exp` sau khi tính clock skew được phép, RP nên làm gì?
A. Từ chối ID Token quá hạn, không tạo phiên đăng nhập
B. Tiếp tục đăng nhập khi chữ ký JWT còn xác minh đúng
C. Đổi claim exp trong payload ID Token trước khi tạo phiên
D. Dùng URL trong token header để xin private key giải mã
Đáp án đúng: A

Câu 28. Với OIDC authentication request có `nonce`, kiểm tra nonce trong ID Token giúp gì?
A. Chuyển access token thành ID Token theo cùng signature
B. Ràng buộc ID Token với yêu cầu đăng nhập đã khởi tạo
C. Chọn callback URL dựa trên tên người dùng trong ID Token
D. Xác định thời hạn lưu cookie trên OIDC Provider
Đáp án đúng: B

Câu 29. Trong authorization code login, tham số OAuth2 `state` chủ yếu bảo vệ điều gì?
A. Xác minh XML Signature của SAML Response trước xử lý
B. Gán quyền quản trị theo mã HTTP status của callback
C. State gắn phản hồi với yêu cầu ban đầu để ngăn CSRF
D. Cấp client secret mới cho mỗi lần redirect login
Đáp án đúng: C

Câu 30. Khi xác minh chữ ký JWT ID Token, RP nên lấy JWK Set từ đâu?
A. JWKS URI tin cậy lấy từ provider metadata đã được kiểm
B. Từ giá trị `jku` tùy ý trong JWT header nhận được
C. Từ query param jwks do browser gửi vào HTTP callback
D. Từ OAuth2 access token của tài khoản chưa liên quan
Đáp án đúng: A

Câu 31. Về phạm vi sử dụng, access token khác ID Token OIDC ở điểm nào?
A. Access token bảo vệ XML Signature; ID Token chứa SP metadata
B. Access token mô tả danh tính; ID Token cấp quyền API trực tiếp
C. Access token dành cho SAML ACS; ID Token dùng refresh token
D. Access token dùng ủy quyền API; ID Token nói về đăng nhập
Đáp án đúng: D

Câu 32. Trong Spring Security OIDC, service nào có thể nạp UserInfo cho OidcUser sau đăng nhập?
A. `JwtAuthenticationConverter` lấy UserInfo bằng AuthnRequest
B. `Saml2AuthenticationToken` dùng UserInfo tạo OidcUser
C. `OidcUserService` nạp UserInfo để xây OidcUser
D. `DefaultOAuth2UserService` giải mã SAML Assertion từ IdP
Đáp án đúng: C

Câu 33. Để chuyển authorities nhận từ OIDC thành các quyền Spring, điểm mở rộng nào phù hợp?
A. `JwtDecoder` ánh xạ role bằng metadata SAML của ứng dụng
B. `RelyingPartyRegistration` ánh xạ role từ URL endpoint ACS
C. `GrantedAuthoritiesMapper` ánh xạ authorities khi đăng nhập
D. `OAuth2AuthorizationRequestResolver` cấp role từ logout request
Đáp án đúng: C

Câu 34. Để khởi tạo OIDC RP-Initiated Logout tại IdP, handler nào phù hợp khi provider hỗ trợ?
A. `SecurityContextLogoutHandler` tự gọi end_session_endpoint của IdP
B. `CookieClearingLogoutHandler` xóa cookie để gọi end_session_endpoint
C. `Saml2RelyingPartyInitiatedLogoutSuccessHandler` gọi OIDC endpoint
D. `OidcClientInitiatedLogoutSuccessHandler` dùng end_session_endpoint
Đáp án đúng: D

Câu 35. Nếu ứng dụng chỉ hủy local HTTP session nhưng IdP SSO session còn hiệu lực, điều gì có thể xảy ra?
A. Lần login sau có thể SSO lại mà không nhập mật khẩu
B. Các access token do IdP cấp sẽ bị thu hồi khi SP logout
C. SP từ chối phiên OIDC mới sau khi browser xóa cookie
D. IdP kết thúc các phiên liên quan khi SP xóa cookie local
Đáp án đúng: A

Câu 36. Trong ứng dụng SSO đa tenant, cách chọn IdP an toàn hơn là gì?
A. Tin IdP metadata từ URL do browser gửi cho SP lúc đăng nhập
B. Dùng SAML Issuer trong response chưa ký để tạo trust mới
C. Map host/path đã kiểm soát sang registration trong allowlist
D. Dùng JWKS từ domain có trong header JWT chưa được tin
Đáp án đúng: C

Câu 37. Khi xử lý OIDC nhiều issuer, cách nào tránh mở rộng trust từ JWT tùy ý?
A. Cho access token quyết định danh sách tenant của hệ thống
B. Giới hạn issuer/registration theo các provider đã tin cậy
C. Đọc claim `iss` rồi tải JWKS URI do token gợi ý
D. Dùng client secret chung cho các issuer không liên quan
Đáp án đúng: B

Câu 38. Khi ánh xạ group/role từ IdP sang quyền nội bộ, biện pháp nào giảm nguy cơ leo thang quyền?
A. Ánh xạ claims đã xác minh theo policy từng tenant/issuer
B. Gộp group từ tenant khác khi tên tài khoản trùng nhau
C. Tin role trong cookie khi ID Token thiếu group claims
D. Dùng query `role=ADMIN` ghi đè group IdP cung cấp
Đáp án đúng: A

Câu 39. Với MockMvc và spring-security-test, postprocessor nào tạo phiên OIDC giả lập để test authorization?
A. `jwt()` tạo OIDC login session bằng authorization code
B. `saml2Login()` tạo OIDC principal từ JWT ID Token
C. `oidcLogin()` tạo principal OIDC giả với các authorities
D. `oauth2Client()` xác minh ID Token và login OIDC đầy đủ
Đáp án đúng: C

Câu 40. Khi kiểm thử negative cases tại ranh giới tin cậy SAML, tổ hợp nào bao quát nhất?
A. Kiểm NameID mapping, group roles và logout redirect
B. Kiểm redirect URI, cookie flags, session rotation và SameSite
C. Chữ ký sai, sai audience/recipient, hết hạn và replay
D. Kiểm signature hợp lệ, metadata load và happy-path login
Đáp án đúng: C
