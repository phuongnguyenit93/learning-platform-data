# Đánh giá conformance OAuth/OIDC và hồi quy sau thay đổi bảo mật

Một Authorization Server chỉ hoạt động đúng khi các client độc lập có thể hiểu và sử dụng nó theo chuẩn OAuth 2.0/OpenID Connect, đồng thời các ràng buộc bảo mật vẫn được giữ sau mỗi lần thay đổi. Một luồng đăng nhập thành công trên trình duyệt chưa đủ chứng minh máy chủ tuân thủ giao thức: redirect có thể sai, token có thể mang claim không đúng, PKCE có thể bị bỏ qua hoặc metadata có thể công bố issuer khác với issuer trong ID Token.

Đánh giá conformance kiểm tra hành vi của máy chủ so với các đặc tả và profile đã chọn. Kiểm thử hồi quy xác minh những hành vi đã đúng trước đó tiếp tục đúng sau khi thay đổi code, cấu hình, dependency, dữ liệu client, khóa ký, proxy hoặc hạ tầng. Hai hoạt động bổ trợ cho nhau: conformance xác lập chuẩn cần đạt; regression giữ chuẩn đó ổn định qua các lần phát hành.

Với Spring Authorization Server, cần kiểm tra cả cấu hình RegisteredClient, endpoint OAuth/OIDC, quá trình xác thực người dùng, phát hành và xác minh token, lưu trữ authorization/consent, cũng như cách hệ thống triển khai ở phía sau reverse proxy. Bài này tập trung vào Authorization Code Flow, PKCE và OpenID Connect Authorization Code Flow; các grant hoặc profile khác chỉ được đánh giá khi hệ thống chủ động hỗ trợ.

## 1. Xác định phạm vi conformance

OAuth 2.0 là framework ủy quyền. OpenID Connect bổ sung lớp xác thực người dùng và ID Token trên OAuth 2.0. Một máy chủ có thể hỗ trợ OAuth 2.0 mà không bật OIDC; do đó, không áp dụng các bài kiểm thử OIDC cho endpoint hoặc tính năng chưa được cấu hình.

Trước khi viết test, lập danh mục các tính năng được triển khai và đặc tả áp dụng:

| Phạm vi | Đặc tả hoặc yêu cầu liên quan | Nội dung cần xác minh |
|---|---|---|
| OAuth 2.0 Authorization Framework | RFC 6749 | Authorization request, token request, client, grant, redirect và error response |
| OAuth 2.0 Security Best Current Practice | RFC 9700 | PKCE, loại bỏ luồng yếu, bảo vệ redirect và chống các kiểu tấn công OAuth phổ biến |
| PKCE | RFC 7636 | code_challenge, code_challenge_method=S256 và code_verifier |
| Authorization Server Metadata | RFC 8414 | Metadata OAuth, issuer và endpoint được công bố |
| OAuth Token Revocation | RFC 7009 | Thu hồi token và hành vi sau khi thu hồi |
| OAuth Token Introspection | RFC 7662 | Trạng thái token và thông tin trả về cho resource server |
| OAuth Authorization Server Issuer Identification | RFC 9207 | Tham số iss trong authorization response, nếu được hỗ trợ |
| OpenID Connect Core 1.0 | OIDC Core | ID Token, nonce, UserInfo, xác thực và các claim |
| OpenID Connect Discovery 1.0 | OIDC Discovery | Provider metadata, issuer, endpoint và thuật toán được hỗ trợ |
| Sender-constrained token | RFC 8705 hoặc RFC 9449 | mTLS hoặc DPoP, chỉ khi profile đó được triển khai |

Không nên đánh dấu hệ thống “conformant OAuth/OIDC” chỉ vì một số endpoint trả về HTTP 200. Kết quả phải gắn với phiên bản đặc tả, profile, grant type, loại client và tính năng thực sự được bật. Nếu sản phẩm chỉ hỗ trợ Authorization Code Flow với PKCE và OIDC, báo cáo phải nêu rõ phạm vi đó.

### Phân biệt ba loại kiểm thử

- **Conformance test:** xác minh request và response tuân theo chuẩn, kể cả các trường hợp hợp lệ, không hợp lệ và ranh giới.
- **Security test:** chủ động thử bypass, giả mạo, replay, rò rỉ thông tin, nhầm lẫn issuer/audience hoặc hạ cấp cơ chế bảo vệ.
- **Regression test:** lưu lại các điều kiện đã được xác minh và chạy lại sau thay đổi để phát hiện hành vi bị suy giảm.

Một test có thể thuộc nhiều nhóm. Ví dụ, kiểm tra authorization code chỉ dùng được một lần vừa là kiểm thử giao thức, vừa là kiểm thử chống replay, vừa là regression test cho kho lưu authorization.

## 2. Chuẩn bị ma trận kiểm thử

Ma trận giúp tránh bỏ sót tính năng hoặc chỉ kiểm tra happy path. Mỗi dòng nên có request đầu vào, điều kiện trước, kết quả mong đợi, bằng chứng và mức độ nghiêm trọng nếu thất bại.

| Nhóm | Trường hợp thành công | Trường hợp âm hoặc ranh giới |
|---|---|---|
| Metadata | Issuer và endpoint công khai chính xác | Issuer/host/scheme sai, metadata thiếu endpoint bắt buộc |
| Authorization | Authorization Code Flow hợp lệ | Thiếu hoặc sai client_id, response_type, scope, redirect_uri |
| PKCE | S256 challenge và verifier khớp | Thiếu verifier, verifier sai, challenge sai định dạng hoặc phương thức không được phép |
| Redirect | URI khớp chính xác URI đăng ký | Host, port, path, query hoặc scheme không khớp |
| State và nonce | Client kiểm tra state; OIDC client kiểm tra nonce | Giá trị bị thiếu, thay đổi hoặc không tương ứng phiên |
| Client authentication | Phương thức đã đăng ký được chấp nhận | Secret sai, phương thức không hỗ trợ, client không được phép dùng grant |
| Authorization code | Code được đổi một lần trong thời hạn | Code hết hạn, đã dùng, thuộc client khác hoặc redirect khác |
| Access token | Chữ ký, issuer, audience, expiry và scope hợp lệ | Token giả, hết hạn, sai issuer/audience hoặc thuật toán không được phép |
| ID Token | Claim và chữ ký đúng theo OIDC | Sai iss, aud, nonce, exp, iat, sub hoặc chữ ký |
| Refresh token | Luân chuyển và cấp token mới theo chính sách | Token hết hạn, bị thu hồi, replay hoặc thuộc client khác |
| Consent | Consent được ghi nhận và áp dụng đúng scope | Người dùng từ chối hoặc scope vượt quá consent |
| Revocation/introspection | Trạng thái token phản ánh đúng chính sách | Token đã thu hồi vẫn được chấp nhận hoặc introspection tiết lộ dữ liệu thừa |
| JWKS và khóa | kid trỏ đúng public key | kid không tồn tại, khóa cũ bị xóa quá sớm, thuật toán không cho phép |
| Phiên và đăng xuất | Login/logout theo chính sách | Session fixation, CSRF, logout redirect không được đăng ký |
| Triển khai | HTTPS, proxy và URL công khai nhất quán | Header giả mạo, HTTP redirect hoặc backend truy cập ngoài ý muốn |

Ma trận cần phân biệt public client và confidential client. Public client không thể giữ bí mật client secret an toàn; PKCE là ràng buộc quan trọng để bảo vệ authorization code. Confidential client phải được kiểm tra cả xác thực client và PKCE theo chính sách đã chọn. Đừng giả định một phương thức xác thực client phù hợp với mọi client.

### Lập hồ sơ cho từng client kiểm thử

Tạo các client đại diện cho cấu hình thực tế, ví dụ:

| Client fixture | Loại | Grant và tính năng | Mục đích |
|---|---|---|---|
| web-confidential-test | Confidential | Authorization Code, OIDC, PKCE | Kiểm tra web application có backend |
| spa-public-test | Public | Authorization Code, PKCE S256 | Kiểm tra client chạy trong trình duyệt |
| service-test | Confidential | Client Credentials | Kiểm tra machine-to-machine nếu được hỗ trợ |
| legacy-negative-test | Public hoặc confidential | Cấu hình grant không được phép | Xác minh máy chủ từ chối luồng đã loại bỏ |

Dùng client ID, secret, user và khóa dành riêng cho môi trường kiểm thử. Không sao chép thông tin xác thực production vào test suite. Ghi lại grant type, authentication method, redirect URI, scope, consent policy và token lifetime của từng fixture để test có thể tái lập.

## 3. Kiểm tra Authorization Code Flow và PKCE

Authorization Code Flow là luồng cốt lõi cần kiểm tra cho ứng dụng web và ứng dụng native/browser-based. Luồng kiểm thử cần đi qua toàn bộ vòng đời: tạo authorization request, đăng nhập, consent, nhận code, đổi code lấy token và sử dụng token.

### Kiểm tra request hợp lệ

Một authorization request OIDC điển hình có dạng:

~~~http
GET /oauth2/authorize?
  response_type=code&
  client_id=spa-public-test&
  redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&
  scope=openid%20profile&
  state=state-value&
  nonce=nonce-value&
  code_challenge=BASE64URL_SHA256_CHALLENGE&
  code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Các giá trị trên chỉ là ví dụ; challenge phải được tính từ verifier theo RFC 7636. Test nên xác minh:

1. Client được nhận diện và grant type được phép.
2. redirect_uri khớp chính xác một URI đã đăng ký.
3. response_type=code được hỗ trợ.
4. Scope được phép đối với client và người dùng.
5. PKCE được yêu cầu theo chính sách và S256 được xử lý đúng.
6. Với OIDC, scope openid kích hoạt hành vi OIDC; nếu authorization request có nonce thì giá trị tương ứng phải được đưa vào ID Token.
7. Máy chủ yêu cầu đăng nhập và consent theo chính sách, sau đó redirect về đúng URI đã đăng ký với authorization code và state tương ứng.

Không xác minh state chỉ ở phía Authorization Server. state chủ yếu giúp client liên kết callback với request ban đầu và chống CSRF trong luồng redirect. Test client cần xác minh state trả về giống giá trị đã tạo và từ chối callback thiếu hoặc sai state.

### Kiểm tra PKCE bằng test dương và test âm

Với verifier đã tạo, challenge S256 được tính như sau:

~~~text
code_challenge =
  BASE64URL-ENCODE-NO-PADDING(
    SHA256(ASCII(code_verifier))
  )
~~~

Khi đổi code tại token endpoint, gửi cùng code_verifier:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64(client-id:client-secret)

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&
code_verifier=ORIGINAL_CODE_VERIFIER
~~~

Với public client, bỏ client secret và xác thực theo phương thức client được đăng ký. Không gửi secret giả định cho public client.

Các test âm tối thiểu:

- Không gửi code_verifier khi authorization code được ràng buộc với PKCE.
- Gửi verifier khác với verifier đã tạo challenge.
- Dùng verifier không hợp lệ theo giới hạn cú pháp/độ dài của RFC 7636.
- Gửi challenge method không được cho phép, chẳng hạn plain, khi chính sách chỉ cho phép S256.
- Thay redirect_uri khi đổi code.
- Dùng code đã đổi thành công lần trước.
- Dùng code hết hạn hoặc code được cấp cho client khác.

Các trường hợp thất bại phải trả lỗi giao thức phù hợp, thường là invalid_grant ở token endpoint khi code không hợp lệ. Response không được tiết lộ code thuộc user nào, client nào hoặc lý do nội bộ chi tiết. Không chỉ kiểm tra status code; hãy xác minh response không chứa access token, refresh token hoặc ID Token trong trường hợp thất bại.

### Kiểm tra authorization code dùng một lần

Sau khi code được đổi thành công:

1. Gửi lại đúng authorization code với verifier ban đầu.
2. Xác minh lần đổi thứ hai bị từ chối.
3. Xác minh không có token mới được cấp.
4. Kiểm tra trạng thái authorization trong kho lưu trữ và log bảo mật nếu hệ thống có audit event.

Test này cần chạy với đúng loại persistence đang dùng. Nếu ứng dụng có nhiều instance, phát code ở node A rồi đổi ở node B; tiếp tục thử replay qua node khác. Kết quả phải nhất quán giữa các node.

## 4. Kiểm tra client authentication và chính sách grant

RegisteredClient quyết định client được phép dùng grant nào, scope nào và phương thức xác thực nào. Thay đổi cấu hình client có thể làm mở rộng quyền mà không cần sửa code, vì vậy cần regression test cho dữ liệu đăng ký client và quá trình nạp cấu hình.

Với confidential client, kiểm tra từng phương thức được khai báo, chẳng hạn client_secret_basic, client_secret_post, private_key_jwt hoặc tls_client_auth nếu hệ thống hỗ trợ. Không kiểm tra một phương thức chưa được bật như thể đó là tính năng bắt buộc.

Các trường hợp cần thử:

- Client ID không tồn tại.
- Client secret sai hoặc đã hết hiệu lực.
- Client dùng phương thức xác thực khác với phương thức đăng ký.
- Client gửi thông tin xác thực ở nhiều vị trí không được phép.
- Client yêu cầu grant type không nằm trong danh sách được cấp.
- Client yêu cầu scope không được phép.
- Client credentials được dùng tại endpoint hoặc grant không phù hợp.
- Client bị vô hiệu hóa hoặc đã bị thu hồi đăng ký.

Đối với secret rotation, xác minh secret mới hoạt động sau khi triển khai và secret cũ bị từ chối theo thời điểm chính sách quy định. Nếu hệ thống hỗ trợ giai đoạn chuyển tiếp, kiểm thử chính xác thời hạn chồng lấn và cách kết thúc giai đoạn đó.

Không log client secret, private key, authorization code, access token, refresh token hoặc ID Token nguyên vẹn. Khi cần đối chiếu trong test report, dùng fixture ID hoặc fingerprint không thể dùng lại làm thông tin xác thực.

## 5. Kiểm tra access token, ID Token và JWKS

Access token là thông tin cấp quyền cho resource server. ID Token là assertion xác thực dành cho OIDC client. Không được dùng ID Token như access token hoặc dùng access token để thay thế các bước xác minh danh tính của OIDC client.

### Access token

Với JWT access token, kiểm tra tối thiểu:

- Chữ ký được xác minh bằng public key tin cậy.
- iss khớp chính xác issuer đã cấu hình.
- aud chứa resource server dự kiến khi profile yêu cầu audience.
- exp chưa hết hạn và nbf (nếu có) đã có hiệu lực.
- iat hợp lý theo chính sách.
- Scope hoặc authority phản ánh đúng quyền được cấp.
- Thuật toán ký nằm trong allowlist.
- kid chọn đúng khóa trong JWKS.
- Token không chứa dữ liệu nhạy cảm không cần thiết.

Nếu hệ thống dùng opaque token, kiểm tra luồng introspection, trạng thái active, client/resource audience, scope và chính sách cache. Không áp dụng test claim JWT cho opaque token.

Một token có chữ ký hợp lệ vẫn có thể không hợp lệ với API nếu issuer hoặc audience sai. Tạo test resource server riêng để xác minh token theo đúng cấu hình mà API sử dụng, thay vì chỉ decode JWT và kiểm tra chuỗi JSON.

### ID Token theo OIDC

ID Token cần được xác minh theo OIDC Core. Tùy flow và yêu cầu, kiểm tra:

- iss bằng issuer của Provider.
- sub là định danh subject hợp lệ và không bị thay đổi tùy tiện.
- aud chứa client ID của RP; xử lý azp khi áp dụng.
- exp và iat hợp lệ.
- nonce khớp nonce từ authentication request nếu request có nonce.
- Chữ ký và thuật toán nằm trong tập được client tin cậy.
- auth_time, acr, amr hoặc các claim khác phù hợp khi client yêu cầu và Provider hỗ trợ.

Với UserInfo endpoint, xác minh access token có quyền phù hợp và sub trong UserInfo khớp sub trong ID Token của cùng phiên xác thực. Không trả claim vượt quá scope hoặc chính sách consent. Nếu endpoint không được bật, ghi rõ trong phạm vi conformance.

### JWKS và vòng đời khóa

JWKS là điểm phụ thuộc của client khi xác minh token. Kiểm thử:

1. jwks_uri trong discovery trỏ đến endpoint công khai.
2. Public key tương ứng với khóa ký hiện tại xuất hiện trong JWKS.
3. kid trong header JWT chọn đúng key.
4. Key rotation công bố khóa mới trước khi token ký bằng khóa mới cần được xác minh.
5. Khóa cũ được giữ đủ lâu để xác minh token còn hiệu lực đã ký bằng khóa cũ.
6. Khóa đã bị thu hồi hoặc hết thời hạn tin cậy không tiếp tục được sử dụng theo chính sách.
7. Client xử lý kid không tồn tại bằng cách refresh JWKS theo cơ chế hợp lý và từ chối token nếu vẫn không xác minh được.

Test rotation nên chạy bằng hai tập khóa kiểm thử. Phát token bằng khóa A, công bố A; sau đó chuyển sang khóa B, công bố A và B trong thời gian chuyển tiếp. Xác minh token A và B vẫn được xác minh trong thời gian dự kiến. Sau khi token A hết hiệu lực và hết giai đoạn giữ khóa, kiểm tra chính sách loại bỏ A.

Không dùng một private key production trong test suite. Tạo key riêng cho test hoặc dùng key fixture được quản lý an toàn.

## 6. Kiểm tra refresh token, consent, revocation và introspection

### Refresh token

Refresh token thường có vòng đời dài hơn access token và có thể cấp access token mới. Kiểm tra:

- Chỉ client được phép mới nhận refresh token.
- Refresh token gắn với đúng client và authorization.
- Scope mới không vượt quá quyền đã cấp.
- Token hết hạn hoặc đã thu hồi bị từ chối.
- Chính sách rotation được thực hiện đúng nếu hệ thống bật.
- Token cũ bị vô hiệu hóa sau khi rotation thành công.
- Replay refresh token cũ được phát hiện và xử lý theo chính sách.
- Logout, thu hồi consent hoặc thu hồi authorization có hiệu lực theo thiết kế.

Không giả định mọi cấu hình đều tự động rotation refresh token. Ghi rõ chính sách hiện tại, ví dụ reuse token hay rotation, thời hạn, và hành vi khi phát hiện replay. Test phải khớp chính sách đã triển khai.

### Consent

Tạo các tình huống:

- Người dùng chấp thuận một phần scope nếu giao diện và chính sách cho phép.
- Người dùng từ chối consent.
- Người dùng đã consent trước đó và request lại cùng scope.
- Request thêm scope mới cần consent bổ sung.
- Client bị thu hồi hoặc consent bị xóa.
- Hai phiên đồng thời thay đổi consent.

Xác minh access token và ID Token phản ánh quyền thực tế được cấp. Một client không được nhận scope cao hơn chỉ vì đã gửi scope đó trong authorization request.

### Revocation và introspection

Nếu bật revocation endpoint, kiểm tra token hợp lệ, token không tồn tại, token đã thu hồi, client không được phép thu hồi và xác thực client sai. RFC 7009 quy định response của revocation không nên làm lộ token có tồn tại hay không; test cần xác minh không rò rỉ thông tin nhạy cảm qua khác biệt response ngoài những gì đặc tả cho phép.

Nếu bật introspection endpoint, kiểm tra client được phép introspect, token active/inactive và các metadata được trả về. Sau revocation, introspection và resource server phải phản ánh trạng thái mới theo giới hạn cache đã định. Nếu resource server cache kết quả introspection, kiểm thử độ trễ thu hồi và đặt TTL theo yêu cầu rủi ro.

## 7. Kiểm tra OIDC Discovery và hành vi xác thực

Khi OIDC được bật, endpoint discovery là hợp đồng mà Relying Party dùng để tìm cấu hình Provider. Thường có địa chỉ:

~~~text
https://auth.example.test/.well-known/openid-configuration
~~~

Kiểm tra:

- issuer khớp chính xác issuer đã cấu hình và claim iss trong ID Token.
- authorization_endpoint, token_endpoint, jwks_uri và userinfo_endpoint (nếu hỗ trợ) là URL công khai hợp lệ.
- Các danh sách response_types_supported, grant_types_supported, subject_types_supported, id_token_signing_alg_values_supported phản ánh đúng khả năng thật.
- Các phương thức xác thực token endpoint được công bố phải được triển khai và hoạt động.
- Các scope, claim, endpoint hoặc tính năng không hỗ trợ không bị quảng bá như thể đã bật.
- Metadata OAuth tại RFC 8414 và OIDC Discovery nhất quán về issuer và endpoint tương ứng.

Không hardcode một danh sách metadata dựa trên kỳ vọng của test nếu cấu hình có chủ đích thay đổi giữa các profile. Thay vào đó, định nghĩa contract cho từng profile triển khai và so sánh response với contract đã được review.

### Authentication request nâng cao

Nếu Provider hỗ trợ các tham số OIDC, kiểm tra hành vi theo chính sách:

- prompt=none khi người dùng chưa đăng nhập hoặc cần consent tương tác phải trả lỗi OIDC phù hợp, ví dụ login_required hoặc consent_required.
- max_age yêu cầu xác thực gần đây và auth_time phản ánh thời điểm xác thực.
- prompt=login yêu cầu xác thực lại theo hành vi đã cấu hình.
- nonce được đưa vào ID Token và được RP xác minh.
- acr_values chỉ được đáp ứng khi mức xác thực tương ứng thực sự được thực hiện.
- login_hint hoặc domain_hint không được dùng làm bằng chứng xác thực.
- Các tham số không hỗ trợ phải được xử lý theo đặc tả thay vì âm thầm làm giảm mức bảo vệ.

Nếu bật RP-Initiated Logout, kiểm tra post_logout_redirect_uri theo danh sách URI đã đăng ký, state được giữ nguyên, phiên Provider được kết thúc đúng chính sách và callback không tạo open redirect. Đăng xuất khỏi phiên SSO không tự động đồng nghĩa mọi access token đã bị thu hồi; kiểm tra riêng hành vi token và session.

## 8. Kiểm tra các ranh giới bảo mật xung quanh endpoint

Conformance không chỉ là nội dung JSON của token. Các lớp web và hạ tầng có thể làm thay đổi kết quả giao thức.

### Session, CSRF và CORS

- Kiểm tra cookie phiên có Secure, HttpOnly và SameSite phù hợp với luồng trình duyệt.
- Kiểm tra session ID được thay đổi sau đăng nhập nếu cơ chế session fixation protection được sử dụng.
- Kiểm tra request thay đổi trạng thái và consent có bảo vệ CSRF thích hợp.
- CORS chỉ cho phép origin, method và header cần thiết; không phản chiếu origin tùy ý cùng credentials.
- Không dùng CORS như biện pháp xác thực client hoặc thay thế kiểm tra redirect URI.
- Kiểm tra logout và consent khi cookie hết hạn hoặc phiên bị thu hồi.

### Reverse proxy và URL công khai

Thực hiện test qua domain bên ngoài, không chỉ gọi trực tiếp servlet container. Kiểm tra issuer, redirect, discovery, JWKS, callback và cookie đều dùng scheme/host/path công khai đúng.

Gửi thử các header do client giả mạo như Forwarded, X-Forwarded-Host và X-Forwarded-Proto. Proxy biên phải xóa hoặc ghi đè chúng. Backend phải bị giới hạn để chỉ proxy được phép gọi. Một bài test MockMvc không chứng minh firewall, ingress hoặc TLS termination đang đúng; cần có kiểm thử deployment riêng.

### Error handling và rate limiting

Các response lỗi OAuth/OIDC phải có cấu trúc phù hợp, không lộ stack trace, SQL, secret, token hoặc thông tin người dùng. Kiểm tra các nhóm lỗi như invalid_request, invalid_client, invalid_grant, unauthorized_client, unsupported_grant_type và invalid_scope tại đúng endpoint.

Kiểm tra giới hạn tần suất cho đăng nhập, token, introspection và endpoint nhạy cảm theo mô hình đe dọa. Xác minh hệ thống không khóa tài khoản hoặc client theo cách cho phép attacker gây từ chối dịch vụ dễ dàng. Log cần đủ correlation ID và sự kiện audit để điều tra nhưng không chứa credential có thể phát lại.

## 9. Tổ chức kiểm thử trong Spring và CI

Nên chia bộ test theo lớp để phản hồi nhanh và vẫn kiểm chứng được hành vi thật.

| Lớp | Công cụ/cách chạy | Mục tiêu |
|---|---|---|
| Unit | JUnit, AssertJ, Mockito | Token customizer, validator, scope mapping, consent policy và quy tắc nội bộ |
| Spring integration | SpringBootTest, AutoConfigureMockMvc, MockMvc | Security filter chain, endpoint, persistence adapter và error response |
| HTTP end-to-end | Test client qua URL triển khai | Cookie, redirect, TLS, proxy, session và nhiều instance |
| Protocol conformance | OpenID Foundation conformance suite và bộ test giao thức phù hợp | Tương tác với client/RP độc lập theo profile |
| Regression deployment | Pipeline trên môi trường staging | So sánh metadata, JWKS, token, revocation và hành vi giữa các bản phát hành |

### Ví dụ kiểm thử lỗi tại token endpoint

Ví dụ sau minh họa test integration gửi authorization code không hợp lệ. Fixture cần đăng ký client_secret_basic, endpoint token chuẩn và Spring Security test support:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenEndpointRegressionTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsUnknownAuthorizationCode() throws Exception {
        mockMvc.perform(post("/oauth2/token")
                .with(httpBasic("web-confidential-test", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "authorization_code")
                .param("code", "unknown-code")
                .param("redirect_uri",
                        "https://client.example.test/callback"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist())
            .andExpect(jsonPath("$.refresh_token").doesNotExist());
    }
}
~~~

Các import thường dùng gồm SecurityMockMvcRequestPostProcessors.httpBasic, MockMvc, MediaType và các static matcher của MockMvc. Test cần chạy với client fixture có phương thức xác thực đúng; nếu fixture dùng private_key_jwt hoặc mTLS thì thay request authentication tương ứng.

Test trên chỉ xác minh một trường hợp lỗi ở token endpoint. Nó không thay thế một luồng Authorization Code Flow hoàn chỉnh, cũng không xác minh PKCE nếu code không tồn tại. Hãy bổ sung test tạo authorization code thực, đổi code đúng verifier, sau đó đổi lại code và thử verifier sai.

### Luồng test tích hợp đầy đủ

Một kịch bản end-to-end có thể được tổ chức như sau:

~~~text
Tạo client fixture và user test
             |
             v
Gửi authorization request với PKCE S256
             |
             v
Đăng nhập và xử lý consent
             |
             v
Nhận callback: code + state
             |
             v
Client xác minh state
             |
             v
Đổi code + code_verifier
             |
             v
Xác minh access token và ID Token
             |
             v
Gọi UserInfo / Resource Server
             |
             v
Refresh token, revocation và logout
             |
             v
Đối chiếu audit event và trạng thái persistence
~~~

Test cần giữ cookie/session giữa các request như trình duyệt thực. Nếu dùng MockMvc, cấu hình session và cookie jar trong test client; với kiểm thử qua nhiều instance, dùng HTTP client thực để điều phối request giữa các node. Không giả lập kết quả đăng nhập bằng cách bỏ qua hoàn toàn security filter chain khi mục tiêu là kiểm tra giao thức.

### Dùng conformance suite bên ngoài

OpenID Foundation cung cấp conformance test suite cho OpenID Connect và các profile liên quan. Có thể triển khai test plan phù hợp với vai trò OP (OpenID Provider) của Spring Authorization Server. Chọn đúng profile, response type, client authentication method và tính năng được bật.

Quy trình khuyến nghị:

1. Triển khai một môi trường test cô lập có URL HTTPS truy cập được từ test suite.
2. Cấu hình client và user thử nghiệm, redirect URI riêng, khóa test và dữ liệu giả.
3. Chọn test plan tương ứng với profile đã công bố.
4. Chạy toàn bộ test bắt buộc, lưu test ID, kết quả, request/response đã loại bỏ credential và phiên bản triển khai.
5. Phân tích failure theo đặc tả, xác định lỗi cấu hình, lỗi ứng dụng hay giới hạn của test harness.
6. Sửa lỗi, chạy lại test thất bại và chạy lại toàn bộ suite bắt buộc trước khi tuyên bố đạt.

Không chạy conformance suite trên production nếu test plan có thể tạo user, authorization, token, consent hoặc dữ liệu trạng thái. Không cung cấp tài khoản production, private key hoặc secret thật cho test harness. Nếu cần chứng minh tương thích với một RP cụ thể, chạy thêm kiểm thử liên thông với RP đó; conformance suite không đảm bảo mọi tích hợp thực tế đều đúng.

## 10. Xây dựng regression gate sau mỗi thay đổi bảo mật

Không phải thay đổi nào cũng cần chạy lại cùng một tập test, nhưng thay đổi liên quan đến giao thức hoặc ranh giới tin cậy phải kích hoạt các test tương ứng.

| Thay đổi | Regression tối thiểu |
|---|---|
| Spring Authorization Server/Spring Security upgrade | Authorization, token, PKCE, client auth, OIDC discovery, error response |
| Sửa RegisteredClient hoặc dữ liệu client | Grant, scope, redirect URI, authentication method và consent |
| Sửa token customizer/claim | Access token, ID Token, issuer, audience, scope và resource server validation |
| Đổi issuer/domain/context path | Discovery, metadata, redirect, JWKS, ID Token iss, proxy |
| Đổi khóa ký hoặc thuật toán | JWT signature, kid, JWKS rotation, token cũ và token mới |
| Đổi persistence/schema | Code single-use, refresh, revocation, consent và nhiều instance |
| Đổi session/CSRF/CORS | Login, consent, callback, cookie, logout và browser flow |
| Đổi reverse proxy/ingress/TLS | Forwarded header spoofing, HTTPS, redirect, cookie, discovery |
| Đổi rate limit/logging | Error response, chống lạm dụng, audit và không rò rỉ credential |

Một pipeline có thể có bốn cổng:

- **Pull request:** unit test và integration test nhanh cho module thay đổi; chạy test âm về redirect, PKCE và client auth nếu code liên quan.
- **Build candidate:** chạy toàn bộ regression suite OAuth/OIDC, migration test và kiểm thử token/JWKS.
- **Staging:** chạy end-to-end qua proxy, test nhiều instance, conformance suite bắt buộc và các kịch bản liên thông.
- **Release gate:** không phát hành nếu có lỗi nghiêm trọng chưa được giải quyết, metadata không nhất quán, token validation sai hoặc test bắt buộc chưa có kết quả.

Nếu một test được miễn trừ, ghi rõ lý do, người phê duyệt theo quy trình nội bộ, phạm vi ảnh hưởng và thời hạn xem xét lại. Không biến test đang thất bại thành skipped chỉ để pipeline xanh.

### Đặt tiêu chí pass/fail rõ ràng

Một release candidate chỉ được xem là đạt khi:

1. Các test bắt buộc của profile đang hỗ trợ đều pass.
2. Không có authorization code hoặc refresh token replay được chấp nhận ngoài chính sách.
3. Redirect URI, issuer, audience, PKCE và chữ ký token được xác minh đúng.
4. Metadata, JWKS và endpoint công khai nhất quán.
5. Revocation và consent có hiệu lực theo SLA/chính sách đã xác định.
6. Các test qua proxy và nhiều instance đạt.
7. Không có credential hoặc dữ liệu nhạy cảm trong log, response lỗi hoặc artifact.
8. Các failure đã biết có đánh giá rủi ro và quyết định xử lý được lưu lại.

Không dùng một tỷ lệ pass tổng hợp để che khuất test bảo mật trọng yếu thất bại. Ví dụ, 99% test pass vẫn là release không đạt nếu test xác minh redirect URI hoặc PKCE bị bypass.

## 11. Quản lý bằng chứng và chẩn đoán lỗi

Mỗi lần chạy nên lưu một bộ bằng chứng đủ để tái lập:

- Commit SHA, phiên bản ứng dụng, Spring Authorization Server và Spring Security.
- Profile OAuth/OIDC, cấu hình endpoint và phiên bản test plan.
- Danh sách test ID, kết quả, thời gian chạy và môi trường.
- Metadata đã loại bỏ dữ liệu nhạy cảm, public JWKS và fingerprint khóa.
- Request/response đã scrub token, code, cookie, secret và dữ liệu cá nhân.
- Correlation ID hoặc audit event liên quan.
- Failure summary, nguyên nhân gốc, quyết định miễn trừ và liên kết issue.

Khi test thất bại, điều tra theo thứ tự:

1. Xác nhận test plan và profile có phù hợp với tính năng đang bật.
2. Kiểm tra request có đúng client, redirect URI, scope và phương thức xác thực.
3. Đối chiếu issuer, endpoint và JWKS mà test harness thực sự gọi.
4. Kiểm tra cấu hình RegisteredClient, AuthorizationServerSettings, token customizer và security filter chain.
5. Kiểm tra persistence, session và sự nhất quán giữa các instance.
6. Kiểm tra proxy, TLS, forwarded headers, clock và cache.
7. Tái hiện lỗi bằng test nhỏ trong môi trường cô lập, sau đó thêm regression test cho nguyên nhân gốc.

Không ghi nguyên authorization code, access token, refresh token, ID Token, cookie hoặc client secret vào CI log. Khi cần phân tích JWT, dùng token test và scrub payload nhạy cảm trước khi đính kèm artifact.

## 12. Checklist trước khi phát hành

- [ ] Phạm vi OAuth/OIDC và phiên bản đặc tả được ghi rõ.
- [ ] Mỗi grant type và client authentication method đang hỗ trợ có test dương và test âm.
- [ ] Redirect URI được kiểm tra chính xác; không có open redirect.
- [ ] Authorization Code Flow yêu cầu PKCE theo chính sách; S256 được kiểm tra.
- [ ] Authorization code hết hạn, dùng lại hoặc sai verifier đều bị từ chối.
- [ ] Client authentication, scope, consent và grant type đúng cấu hình.
- [ ] Access token được xác minh issuer, audience, expiry, signature và scope.
- [ ] ID Token được xác minh issuer, audience, nonce, thời hạn và chữ ký.
- [ ] JWKS và key rotation không làm mất khả năng xác minh token còn hiệu lực.
- [ ] Refresh, revocation và introspection tuân theo chính sách.
- [ ] Discovery metadata phản ánh đúng endpoint và tính năng đã bật.
- [ ] UserInfo, logout và tham số OIDC nâng cao được kiểm tra nếu hỗ trợ.
- [ ] Cookie, session, CSRF, CORS, TLS và reverse proxy được kiểm thử qua đường truy cập thực.
- [ ] Test conformance bắt buộc và regression gate đều đạt.
- [ ] Bằng chứng được lưu an toàn, không chứa credential hoặc token có thể phát lại.

Đánh giá conformance cho Spring Authorization Server là một hoạt động liên tục. Mỗi lần thay đổi client, token, issuer, khóa ký, persistence, session hoặc proxy đều có thể làm thay đổi hành vi giao thức. Khi ma trận kiểm thử gắn với profile đã công bố, test âm bao phủ các ranh giới bảo mật và regression gate chạy trước phát hành, đội vận hành có thể phát hiện sớm sai lệch OAuth/OIDC và giữ tính tương thích của Authorization Server qua các phiên bản.

