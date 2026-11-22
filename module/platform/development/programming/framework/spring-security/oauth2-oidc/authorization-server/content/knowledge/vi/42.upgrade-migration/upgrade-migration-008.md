# Kiểm thử hồi quy luồng OAuth/OIDC và khả năng tương tác client

Khi nâng cấp Spring Authorization Server hoặc Spring Security, một ứng dụng có thể khởi động bình thường và endpoint vẫn trả HTTP 200 nhưng client thực tế lại không đăng nhập được, không đổi được authorization code, không làm mới được token hoặc không xác minh được ID token. Nguyên nhân thường nằm ở thay đổi cấu hình, hành vi giao thức, metadata, xác thực client, cookie/session, claim token hoặc cách lưu authorization qua phiên bản mới.

Kiểm thử hồi quy cần chứng minh các hợp đồng OAuth 2.0 và OpenID Connect mà hệ thống đang cung cấp vẫn hoạt động với những client được hỗ trợ. Bài này trình bày cách xây dựng bộ kiểm thử theo luồng đầu cuối, kiểm tra tương thích giữa các phiên bản client và Authorization Server, đồng thời phát hiện thay đổi ngoài dự kiến sau nâng cấp.

Sau bài học này, bạn có thể:

- Lập baseline cho các luồng OAuth/OIDC đang được sử dụng.
- Kiểm thử authorization code, PKCE, client credentials, refresh token và các grant type đã bật.
- Kiểm tra discovery metadata, JWKS, ID token, UserInfo và xác thực token tại Resource Server.
- Đánh giá khả năng tương tác với các client library và cấu hình client cũ.
- Phát hiện thay đổi về redirect URI, client authentication, scope, consent, error response và session.
- Tổ chức kiểm thử hồi quy trước và sau nâng cấp, bao gồm dữ liệu đã tồn tại trong database.

## 1. Xác định hợp đồng cần bảo toàn

OAuth 2.0 và OpenID Connect định nghĩa các giao thức và thông điệp mà client, Authorization Server và Resource Server trao đổi. Kiểm thử hồi quy nên bắt đầu từ hợp đồng mà hệ thống thực sự công bố, dựa trên các grant type, authentication method, scope, endpoint và extension đang được bật.

Không phải mọi hệ thống đều triển khai cùng một tập tính năng. Hãy lập danh sách từ cấu hình và hành vi hiện tại của ứng dụng, sau đó phân loại từng mục thành bắt buộc, tùy chọn hoặc không được hỗ trợ.

| Hợp đồng | Nội dung cần cố định trong baseline |
|---|---|
| Issuer và discovery | Issuer chính xác, endpoint, thuật toán và capability được công bố |
| Client registration | Client ID, loại client, redirect URI, grant type, scope và phương thức xác thực |
| Authorization code | Redirect, state, consent, code lifetime và quy tắc sử dụng một lần |
| PKCE | Phương thức `S256`, kiểm tra `code_verifier` và chính sách bắt buộc PKCE |
| Token endpoint | Client authentication, grant type, token type, scope và lỗi giao thức |
| Refresh token | Thời hạn, reuse/rotation policy và cách xử lý token đã hết hạn hoặc bị thu hồi |
| OIDC | `openid` scope, nonce, ID token, JWKS, UserInfo và các claim được cam kết |
| Resource Server | Chữ ký, issuer, audience, thời gian hiệu lực và quyền truy cập |
| Persistence | Client, authorization, consent và token còn hiệu lực sau restart hoặc migration |

Với mỗi hợp đồng, ghi rõ request đầu vào, response mong đợi, mã lỗi, trạng thái lưu trữ và client nào phụ thuộc vào hành vi đó. Baseline cần phản ánh hành vi đã được kiểm chứng của phiên bản đang chạy, không chỉ phản ánh cấu hình dự định.

## 2. Chiến lược kiểm thử trước và sau nâng cấp

Một quy trình hồi quy có thể chia thành bốn lớp:

1. **Contract test:** xác minh endpoint, HTTP status, header, JSON field, redirect và error response.
2. **Protocol integration test:** chạy trọn luồng qua Authorization Server, database, session và JWT decoder.
3. **Client interoperability test:** dùng client library hoặc ứng dụng đại diện để thực hiện giao thức như một client thật.
4. **Migration regression test:** dùng dữ liệu đã tồn tại, nâng cấp schema và kiểm tra khả năng tiếp tục xử lý authorization/token cũ.

Chạy cùng một bộ kịch bản trên phiên bản hiện tại và phiên bản nâng cấp với dữ liệu đầu vào tương đương. So sánh kết quả theo ý nghĩa giao thức. Những giá trị có tính ngẫu nhiên như authorization code, access token, refresh token, `state`, `nonce`, thời gian phát hành và `kid` có thể khác nhau; không so sánh chuỗi token nguyên vẹn hoặc snapshot toàn bộ response có chứa bí mật.

Thay vào đó, chuẩn hóa response trước khi so sánh: kiểm tra field bắt buộc, loại token, scope, thời hạn, issuer, audience, redirect URI và mã lỗi. Với JWT, decode phần header/payload để kiểm tra claim, sau đó vẫn xác minh chữ ký bằng public key từ JWKS. Chỉ decode payload không chứng minh token hợp lệ.

### 2.1. Ma trận phiên bản

Chọn các client đại diện theo cách chúng được triển khai và vận hành:

| Authorization Server | Client cũ | Client đã nâng cấp | Mục tiêu |
|---|---|---|---|
| Phiên bản hiện tại | Chạy | Chạy | Baseline và xác nhận fixture |
| Phiên bản nâng cấp | Chạy | Chạy | Kiểm tra tương thích ngược và tương thích mới |
| Phiên bản nâng cấp + dữ liệu cũ | Chạy | Chạy | Kiểm tra migration và dữ liệu đang tồn tại |

Client cũ là những ứng dụng vẫn đang được hỗ trợ và chưa thể nâng cấp cùng thời điểm với Authorization Server. Client mới đại diện cho SDK hoặc ứng dụng sẽ được phát hành cùng đợt. Không cần thử mọi tổ hợp nếu chúng không có trong phạm vi hỗ trợ, nhưng phải kiểm thử các tổ hợp có người dùng hoặc hệ thống phụ thuộc thực tế.

### 2.2. Giữ test data ổn định

Tạo fixture cho từng loại client, chẳng hạn:

- Public client dùng authorization code và PKCE.
- Confidential client dùng `client_secret_basic` hoặc phương thức xác thực đang được cấu hình.
- Service client dùng client credentials.
- OIDC client yêu cầu `openid`, nonce và UserInfo.
- Client có nhiều redirect URI hoặc scope tùy chỉnh nếu ứng dụng đang hỗ trợ các trường hợp đó.

Không dùng client production hoặc secret production trong test. Dùng secret dành riêng cho test và lưu fixture theo cách không ghi bí mật vào log hoặc snapshot. Tạo dữ liệu test mới cho mỗi lần chạy nếu code hoặc refresh token có trạng thái dùng một lần.

## 3. Kiểm thử authorization code và PKCE

Authorization code là luồng quan trọng nhất với ứng dụng web và ứng dụng native. Một kịch bản đầu cuối cần kiểm tra request authorization, đăng nhập, consent, redirect callback, đổi code lấy token và sử dụng token tại Resource Server.

### 3.1. Chuẩn bị request PKCE

Client tạo `code_verifier` ngẫu nhiên cho mỗi authorization request. Với phương thức `S256`, `code_challenge` được tính bằng SHA-256 trên verifier rồi mã hóa Base64 URL-safe, bỏ padding.

```java
static String createCodeChallenge(String verifier)
        throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
}
```

Trong test, tạo verifier bằng bộ sinh số ngẫu nhiên mật mã và giữ verifier ở phía client test. Gửi challenge đến authorization endpoint, sau đó gửi verifier khi gọi token endpoint. Không ghi verifier hoặc authorization code vào log.

Request authorization thường có các tham số:

```text
response_type=code
client_id=web-client
redirect_uri=https://client.example.test/callback
scope=openid profile orders.read
state=<random-state>
nonce=<random-nonce>
code_challenge=<base64url-sha256>
code_challenge_method=S256
```

`nonce` cần có khi client yêu cầu OIDC và muốn ràng buộc ID token với authentication request. `state` là giá trị do client tạo để liên kết callback với request ban đầu và chống CSRF trong luồng redirect. Authorization Server trả lại `state`; client phải tự xác minh giá trị nhận được khớp với giá trị đã lưu. Kiểm tra state ở phía client là một phần của interoperability test, không thể thay bằng assertion rằng server chỉ phản hồi HTTP thành công.

### 3.2. Các bước kiểm thử đầu cuối

1. Gửi authorization request với `response_type=code`, redirect URI đã đăng ký và PKCE S256.
2. Xác thực người dùng bằng test identity hoặc cơ chế đăng nhập được cấu hình.
3. Nếu client cần consent, hoàn thành consent và kiểm tra scope đã cấp.
4. Xác minh redirect callback trỏ đúng URI đã đăng ký, có authorization code và trả lại `state` nguyên vẹn.
5. Đổi code lấy token bằng đúng phương thức xác thực client.
6. Kiểm tra access token, token type, scope và thời hạn.
7. Gửi access token đến Resource Server và kiểm tra quyền truy cập.
8. Thử sử dụng lại authorization code và xác minh server từ chối.

Ở bước đổi token, ví dụ với confidential client dùng HTTP Basic:

```java
mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("web-client", testClientSecret))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "authorization_code")
        .param("code", authorizationCode)
        .param("redirect_uri", redirectUri)
        .param("code_verifier", codeVerifier))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.access_token").isNotEmpty())
    .andExpect(jsonPath("$.token_type").value("Bearer"));
```

Đoạn test giả định `authorizationCode` đã được lấy từ callback sau một authorization flow thành công, `testClientSecret` là secret test và endpoint token đang dùng đường dẫn mặc định. Với public client, không gửi client secret; request phải được nhận diện bằng `client_id` và các tham số phù hợp với cấu hình client.

### 3.3. Các trường hợp âm tính của PKCE và authorization code

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Thiếu `code_verifier` khi client bắt buộc PKCE | Token endpoint từ chối grant |
| Verifier không khớp challenge | Từ chối với lỗi phù hợp, không phát hành token |
| Dùng verifier của authorization request khác | Từ chối |
| Thay `code_challenge_method` bằng phương thức không được cho phép | Từ chối theo chính sách PKCE |
| Redirect URI khác URI đã đăng ký | Authorization hoặc token request bị từ chối theo bước kiểm tra tương ứng |
| Authorization code hết hạn | Từ chối `invalid_grant` |
| Dùng lại authorization code | Từ chối, không cấp token lần thứ hai |
| Code thuộc client khác | Từ chối |
| Client authentication sai | Từ chối xác thực client |
| Người dùng từ chối consent | Trả lỗi authorization phù hợp và không cấp code thành công |

Không kiểm tra riêng status code. Với lỗi OAuth, kiểm tra cả JSON `error`, nội dung không chứa thông tin nhạy cảm và không có token được phát hành. Ở authorization endpoint, lỗi thường được phản hồi qua redirect URI hợp lệ theo quy tắc OAuth; nếu redirect URI không hợp lệ, server không được redirect tùy ý đến URI do request cung cấp.

## 4. Kiểm thử client authentication và grant type

Nâng cấp có thể ảnh hưởng đến cách client xác thực tại token endpoint. Cần kiểm tra từng phương thức mà hệ thống đang cho phép và xác nhận metadata công bố khớp với cấu hình thực tế.

Các phương thức có thể gặp gồm:

- `client_secret_basic`: client gửi thông tin xác thực qua HTTP Basic theo quy tắc OAuth.
- `client_secret_post`: client gửi thông tin xác thực trong form body; chỉ kiểm thử nếu được bật và có lý do tương thích.
- `private_key_jwt`: client ký JWT assertion bằng private key đã đăng ký.
- Mutual TLS hoặc phương thức khác nếu hệ thống đã tích hợp và công bố.

Không mặc định mọi client đều dùng cùng phương thức. Hãy kiểm tra theo từng `RegisteredClient` và đối chiếu với discovery metadata nếu Authorization Server công bố trường tương ứng.

| Kiểm tra | Kết quả cần xác minh |
|---|---|
| Secret đúng với phương thức đã đăng ký | Xác thực thành công |
| Secret sai hoặc client không tồn tại | Từ chối với `invalid_client` theo giao thức |
| Client dùng phương thức không được đăng ký | Từ chối |
| Client gửi hai phương thức xác thực cùng lúc | Từ chối theo quy tắc client authentication |
| Client assertion hết hạn hoặc sai chữ ký | Từ chối |
| `aud` của client assertion không khớp token endpoint | Từ chối |
| Assertion ID (`jti`) bị replay khi replay detection được triển khai | Từ chối theo chính sách |

Với từng grant type đang hỗ trợ, kiểm tra cả luồng thành công và lỗi. Ví dụ, client credentials cần client authentication hợp lệ, grant type được đăng ký và scope được cho phép. Không cấp refresh token hoặc ID token cho luồng này trừ khi một extension cụ thể định nghĩa hành vi đó và hệ thống chủ động hỗ trợ.

Không đưa grant type đã bị loại khỏi chính sách vào danh sách hỗ trợ chỉ vì một client cũ vẫn gửi request. Ví dụ, implicit grant và resource owner password credentials không nên được xem là phương án mặc định cho tích hợp mới. Nếu hệ thống cần từ chối chúng, hãy có test chứng minh server không phát hành token cho request đó.

## 5. Kiểm thử refresh token và vòng đời authorization

Refresh token thường tồn tại lâu hơn access token và phụ thuộc vào trạng thái được lưu trong Authorization Server. Nâng cấp persistence hoặc cấu hình token có thể làm hỏng các refresh token đã cấp trước đó.

Kiểm thử với client được phép dùng `refresh_token`:

1. Lấy access token và refresh token bằng luồng authorization code đã cấu hình.
2. Gửi refresh token đến token endpoint với client authentication phù hợp.
3. Xác minh access token mới được cấp, scope không vượt quá quyền ban đầu và token cũ được xử lý theo reuse/rotation policy.
4. Thử refresh bằng token đã hết hạn, bị thu hồi hoặc đã dùng lại theo chính sách.
5. Kiểm tra hành vi sau khi Authorization Server restart và sau khi migration database hoàn tất.

Spring Authorization Server cho phép cấu hình hành vi reuse refresh token. Vì vậy, bài test phải lấy chính sách của ứng dụng làm chuẩn. Nếu hệ thống xoay refresh token, xác minh token mới được trả về và token cũ không thể tiếp tục sử dụng theo chính sách. Nếu hệ thống cho phép reuse, xác minh hành vi đó đúng như cấu hình và thời hạn. Không viết test giả định mọi deployment đều có cùng mặc định.

Kiểm tra thêm:

- Refresh token không được dùng bởi client khác.
- Refresh token không thể mở rộng scope vượt quyền đã cấp.
- Revocation có hiệu lực theo chính sách đã triển khai.
- Consent bị thu hồi được phản ánh trong lần cấp quyền tiếp theo.
- Authorization đã lưu vẫn có thể được đọc sau restart hoặc chuyển sang phiên bản mới.
- Hai refresh request đồng thời được xử lý đúng với chính sách rotation/reuse và không tạo ra trạng thái token không nhất quán.

## 6. Kiểm thử OpenID Connect

OpenID Connect bổ sung lớp xác thực danh tính trên OAuth 2.0. Một luồng OAuth cấp access token chưa đủ để chứng minh OIDC hoạt động. Client cần kiểm tra ID token và các endpoint liên quan.

### 6.1. Discovery metadata

Gọi OpenID Provider Configuration tại đường dẫn discovery được công bố. Thường endpoint có dạng `/.well-known/openid-configuration` gắn với issuer; cần dùng chính URL issuer của hệ thống thay vì hard-code đường dẫn nếu issuer có path.

Kiểm tra các field quan trọng:

- `issuer` trùng chính xác với issuer trong cấu hình và claim `iss` của token.
- `authorization_endpoint`, `token_endpoint`, `jwks_uri` trỏ đến endpoint có thể truy cập từ client hoặc Resource Server.
- `userinfo_endpoint` có mặt khi hệ thống hỗ trợ UserInfo.
- `response_types_supported` và `grant_types_supported` phản ánh khả năng thực tế.
- `subject_types_supported` và `id_token_signing_alg_values_supported` phù hợp với cấu hình.
- `token_endpoint_auth_methods_supported` phản ánh phương thức client authentication được bật.
- Capability OIDC bổ sung chỉ được công bố khi đã triển khai và kiểm thử.

Không snapshot toàn bộ discovery JSON mà không chuẩn hóa host, thời gian hoặc endpoint môi trường. Thay vào đó, kiểm tra các giá trị hợp đồng và xác nhận không có endpoint nội bộ, hostname pod hoặc HTTP URL ngoài dự kiến bị công bố.

### 6.2. ID token và nonce

Khi client yêu cầu scope `openid`, kiểm tra response token có ID token theo luồng OIDC đã cấu hình. ID token cần được xác minh chữ ký bằng JWKS và kiểm tra các claim:

| Claim | Kiểm tra |
|---|---|
| `iss` | Trùng issuer đã tin cậy |
| `sub` | Có giá trị định danh subject và giữ ổn định theo chính sách subject của provider |
| `aud` | Chứa client ID đã gửi authorization request |
| `exp` | Chưa hết hạn, có xét clock skew theo chính sách |
| `iat` | Thời điểm phát hành hợp lệ |
| `nonce` | Khớp nonce do client tạo và gửi trong authorization request |
| `azp` | Kiểm tra theo quy tắc OIDC khi có nhiều audience hoặc khi claim được yêu cầu |

Nếu client dùng `max_age`, kiểm tra `auth_time` theo yêu cầu. Nếu hệ thống hỗ trợ `prompt`, `acr_values` hoặc các tham số OIDC khác, thêm test theo đúng hành vi đã công bố. Không coi một claim tùy chọn là bắt buộc trong mọi cấu hình nếu ứng dụng không sử dụng nó.

Một ID token có chữ ký hợp lệ nhưng `aud` sai vẫn phải bị từ chối. Tương tự, nonce không khớp là lỗi ở phía client khi xác thực ID token; bài test client phải kiểm tra và không tạo phiên đăng nhập thành công.

### 6.3. UserInfo và subject nhất quán

Nếu có `userinfo_endpoint`, gọi endpoint bằng access token có quyền phù hợp. Xác minh:

- Token hợp lệ và có scope cần thiết.
- Response chỉ chứa claim mà scope hoặc policy cho phép.
- `sub` trong UserInfo khớp `sub` của ID token.
- Token hết hạn, sai audience hoặc thiếu quyền bị từ chối.

Không giả định mọi profile claim đều được trả về chỉ vì client yêu cầu `profile` hoặc `email`; dữ liệu thực tế còn phụ thuộc policy và dữ liệu người dùng. Hãy xác định các claim được cam kết trong ứng dụng và kiểm thử đúng tập đó.

Nếu hệ thống tích hợp logout OIDC hoặc một end-session extension, kiểm thử riêng redirect sau logout, trạng thái session và hành vi của client. Không suy ra rằng endpoint logout chuẩn đã tồn tại chỉ vì ứng dụng hỗ trợ discovery và ID token.

## 7. Kiểm thử Resource Server và token semantics

Sau khi nhận access token, client hoặc service gọi API được bảo vệ. Kiểm thử hồi quy cần xác minh token mới vẫn tương thích với Resource Server đã triển khai, đặc biệt khi thay đổi claim customizer, thuật toán ký, issuer hoặc JWKS.

Các kiểm tra cơ bản:

- JWT có chữ ký hợp lệ và `kid` được tìm thấy trong JWKS.
- `iss` đúng issuer được tin cậy.
- `aud` chứa định danh API nếu Resource Server yêu cầu audience.
- `exp` và `nbf` được kiểm tra theo clock skew đã cấu hình.
- Scope/authority được ánh xạ đúng vào quyền truy cập.
- Token thiếu scope bị từ chối tại endpoint cần quyền đó.
- Token sai chữ ký, bị sửa payload hoặc dùng thuật toán ngoài allowlist bị từ chối.
- Token cũ trong giai đoạn chuyển khóa được xác minh theo chính sách khóa.

Nếu access token là opaque, kiểm thử introspection endpoint và trạng thái active/inactive theo cấu hình. Nếu token là JWT tự xác minh, kiểm tra cả JWKS refresh và hành vi khi key rotation. Không giả định `active` của introspection và khả năng xác minh chữ ký JWT là hai phép kiểm tra tương đương.

Với scope, kiểm tra cả nội dung token và kết quả authorization. Một token có scope `orders.read` không được phép truy cập thao tác cần `orders.write`. Nếu hệ thống dùng claim tùy chỉnh để ánh xạ authority, giữ fixture cho claim đó qua nâng cấp và kiểm tra Resource Server không âm thầm đổi cách ánh xạ.

## 8. Kiểm thử consent, session, redirect và trình duyệt

Một số lỗi chỉ xuất hiện trong luồng trình duyệt, không thấy ở test gọi token endpoint trực tiếp. Sau nâng cấp Spring Security, kiểm tra lại:

- Đăng nhập, saved request và chuyển hướng trở lại authorization endpoint.
- Session được giữ xuyên suốt redirect và consent.
- CSRF protection trên các form POST như login và consent.
- Cookie session có `Secure`, `HttpOnly`, `SameSite` phù hợp với mô hình triển khai.
- Redirect URI khớp chính xác URI đã đăng ký và không chấp nhận wildcard ngoài chính sách.
- `state` được trả lại và client xác minh đúng.
- Consent đã lưu được hiển thị và áp dụng đúng cho lần authorization tiếp theo.
- Logout và session invalidation hoạt động theo hành vi đã hỗ trợ.

Với ứng dụng sau reverse proxy, kiểm tra scheme/host được tạo ra từ forwarded headers đáng tin cậy. Redirect URL và discovery endpoint phải sử dụng issuer công khai, không được lộ hostname nội bộ hoặc giao thức sai. Kiểm tra cả môi trường HTTPS thật hoặc staging có TLS termination tương tự production.

## 9. Khả năng tương tác với client library

Một server tuân thủ giao thức vẫn có thể không tương thích với client nếu metadata, encoding, authentication method hoặc redirect behavior khác kỳ vọng của thư viện. Hãy chọn client đại diện từ hệ thống đang dùng và kiểm thử bằng chính thư viện, phiên bản và cấu hình triển khai.

Ví dụ nhóm client có thể cần kiểm thử:

| Nhóm client | Kịch bản đại diện |
|---|---|
| Spring Security OAuth2 Client | Login authorization code, callback, token refresh và principal mapping |
| Ứng dụng native/mobile | Authorization code + PKCE S256, external browser và callback URI |
| Web client confidential | Client authentication, redirect URI, session và refresh token |
| Service-to-service | Client credentials và scope của API |
| OIDC relying party | Discovery, ID token validation, nonce và UserInfo |
| Resource Server Spring Security | JWKS, JWT validation, authority mapping và key rotation |

Không chỉ kiểm tra một client tự viết dựa trên cùng assumptions với Authorization Server. Dùng ít nhất một client library độc lập hoặc một ứng dụng đại diện đang được hỗ trợ để phát hiện khác biệt về cách triển khai giao thức.

Khi client library được nâng cấp cùng Authorization Server, chạy ma trận hai chiều: server mới với client cũ và server mới với client mới. Nếu client mới yêu cầu một capability chưa được server công bố, phải xác định đó là thay đổi cấu hình cần thiết hay một tính năng nằm ngoài phạm vi hỗ trợ.

### 9.1. Những khác biệt thường gây lỗi

- Client library đọc discovery metadata để tìm endpoint nhưng server công bố issuer hoặc URL không chính xác.
- Client gửi `client_secret_post` trong khi client registration chỉ cho phép `client_secret_basic`.
- Client gửi redirect URI có khác biệt về slash, port, scheme hoặc encoding.
- Client yêu cầu scope chưa được đăng ký hoặc chưa được cho phép.
- Client mong đợi refresh token nhưng `offline_access` hoặc policy cấp refresh token chưa được cấu hình theo yêu cầu.
- Client không xác minh `state`, `nonce`, issuer hoặc audience đúng cách.
- Resource Server cache JWKS cũ trong thời gian xoay khóa.
- Client xử lý error response hoặc redirect theo một định dạng không còn được server trả về.

Khi phát hiện lỗi, lưu request/response đã được loại bỏ secret, token và thông tin người dùng nhạy cảm. Ghi lại client library/version, cấu hình liên quan, endpoint, HTTP status và error code để có thể tái hiện.

## 10. Kiểm thử persistence và migration dữ liệu

Nâng cấp ứng dụng thường đi cùng thay đổi schema, thư viện JDBC hoặc cách serialize authorization/token. Một bộ test chỉ tạo dữ liệu mới trên schema rỗng sẽ không phát hiện lỗi đọc dữ liệu đã được phiên bản cũ lưu.

Tạo một database fixture bằng phiên bản hiện tại, gồm:

- Registered client với nhiều grant type, redirect URI, scope và authentication method.
- Authorization đang còn hiệu lực, có authorization code hoặc refresh token theo luồng hỗ trợ.
- Consent đã lưu cho người dùng và client.
- Token đã hết hạn hoặc bị thu hồi nếu schema lưu các trạng thái đó.

Sau đó chạy migration theo đúng quy trình nâng cấp, khởi động phiên bản mới và xác minh:

1. Registered client được đọc đúng và vẫn xác thực theo phương thức cũ.
2. Authorization còn hiệu lực có thể được đọc và xử lý tiếp.
3. Refresh token cũ hoạt động hoặc bị từ chối đúng theo policy đã cam kết.
4. Consent không bị mất hoặc tự động mở rộng quyền.
5. Token đã thu hồi không trở lại trạng thái active.
6. Restart thêm lần nữa không làm dữ liệu biến đổi ngoài dự kiến.

Nếu có rolling deployment, kiểm tra schema tương thích với cả phiên bản ứng dụng cũ và mới trong thời gian hai phiên bản cùng chạy. Dùng chiến lược expand/contract: thêm cấu trúc tương thích trước, triển khai ứng dụng, chuyển dữ liệu nếu cần, rồi chỉ loại bỏ cấu trúc cũ khi không còn phiên bản nào sử dụng.

Không đưa dữ liệu production thật vào fixture. Dùng dữ liệu tổng hợp hoặc bản sao đã được làm sạch, và không ghi access token, refresh token, authorization code hoặc client secret vào log test.

## 11. Kiểm tra error response và HTTP contract

Kiểm thử hồi quy cần kiểm tra lỗi giao thức vì client thường dựa vào `error` để quyết định retry, yêu cầu đăng nhập lại hoặc hiển thị thông báo.

| Tình huống | Error thường cần kiểm tra |
|---|---|
| Request thiếu hoặc sai tham số | `invalid_request` |
| Client authentication không hợp lệ | `invalid_client` |
| Authorization code/refresh token không hợp lệ | `invalid_grant` |
| Client không được phép dùng grant type | `unauthorized_client` |
| Grant type không được hỗ trợ | `unsupported_grant_type` |
| Scope không hợp lệ | `invalid_scope` |
| Resource Server không chấp nhận Bearer token | `invalid_token` hoặc response phù hợp với Bearer challenge |
| Token hợp lệ nhưng thiếu quyền | `insufficient_scope` khi dùng Bearer token challenge phù hợp |

Kiểm tra thêm các thuộc tính HTTP:

- `Content-Type` đúng với response JSON hoặc form encoding tương ứng.
- `Cache-Control` và các header bảo vệ token response phù hợp với yêu cầu bảo mật.
- `WWW-Authenticate` được trả về khi Bearer authentication thất bại theo quy tắc áp dụng.
- Không có stack trace, SQL detail, secret hoặc token trong response lỗi.
- Không có redirect ngoài danh sách URI được đăng ký.
- CORS chỉ cho phép origin và method được cấu hình; preflight phải phản ánh policy hiện tại.

Không nên yêu cầu mọi lỗi đều có cùng status code nếu đặc tả giao thức quy định cách xử lý khác nhau cho authorization endpoint và token endpoint. So sánh cả HTTP status lẫn nội dung lỗi theo đúng endpoint và tình huống.

## 12. Tự động hóa bộ kiểm thử

Một cấu trúc test suite có thể chia theo lớp để chạy nhanh ở pull request và chạy đầy đủ trước phát hành:

```text
src/test/
  java/
    .../contract/
      DiscoveryMetadataContractTest.java
      JwksContractTest.java
      TokenEndpointErrorContractTest.java
    .../protocol/
      AuthorizationCodePkceFlowTest.java
      ClientCredentialsFlowTest.java
      RefreshTokenLifecycleTest.java
      OidcIdTokenUserInfoTest.java
      RevocationIntrospectionTest.java
    .../interop/
      SpringOAuth2ClientCompatibilityTest.java
      NativePkceClientCompatibilityTest.java
      ResourceServerCompatibilityTest.java
    .../migration/
      ExistingAuthorizationMigrationTest.java
```

Đây là cách tổ chức minh họa; hãy dùng package và tên test phù hợp với cấu trúc dự án. Một số test cần database thật thông qua Testcontainers để kiểm tra transaction, constraint, migration và persistence. Test HTTP có thể dùng MockMvc hoặc WebTestClient cho server, còn client interoperability nên chạy qua HTTP thật trong môi trường integration/staging để kiểm tra redirect, cookie, TLS và hành vi thư viện.

### 12.1. Phân tầng pipeline

| Giai đoạn | Test nên chạy | Mục tiêu |
|---|---|---|
| Pull request | Contract test, PKCE cơ bản, client authentication, JWT validation | Phát hiện lỗi nhanh |
| Integration build | Full OAuth/OIDC flow, database, consent, refresh, introspection | Xác minh các thành phần tích hợp |
| Pre-release | Client cũ/mới, migration từ dữ liệu cũ, reverse proxy/TLS | Xác minh khả năng tương thích |
| Staging drill | Rolling deployment, key rotation, dependency failure, emergency revoke | Kiểm tra hành vi vận hành |

Mỗi test nên có dữ liệu đầu vào xác định, timeout, cleanup và log có thể truy vết. Không để test song song dùng chung một authorization code hoặc refresh token dùng một lần. Có thể tạo client ID riêng theo test case hoặc dùng fixture được khởi tạo lại trước mỗi nhóm test.

### 12.2. Tiêu chí hoàn tất nâng cấp

Chỉ đánh giá một đợt nâng cấp đạt khi:

- Các luồng bắt buộc trong baseline đều chạy thành công.
- Các trường hợp âm tính vẫn bị từ chối đúng quy tắc.
- Client cũ trong phạm vi hỗ trợ tiếp tục hoạt động.
- Discovery và JWKS công bố đúng issuer, endpoint và key set.
- Token mới tương thích với Resource Server hiện có.
- Dữ liệu client, authorization và consent cũ được đọc đúng sau migration.
- Không có thay đổi ngoài dự kiến về scope, claim, thời hạn token, consent hoặc error response.
- Các thay đổi giao thức có chủ đích đã được ghi nhận và client phụ thuộc đã được kiểm thử.

## 13. Checklist trước khi phát hành phiên bản mới

- [ ] Baseline OAuth/OIDC được lập từ hành vi của phiên bản đang chạy.
- [ ] Danh sách client, grant type, scope và authentication method đã được xác nhận.
- [ ] Authorization code + PKCE S256 chạy thành công từ redirect đến token endpoint.
- [ ] State được client kiểm tra và nonce được xác minh trong ID token.
- [ ] Redirect URI và consent giữ đúng policy.
- [ ] Client credentials và các grant type được hỗ trợ có test thành công/lỗi.
- [ ] Refresh token, rotation/reuse, revocation và persistence được kiểm thử.
- [ ] Discovery metadata và JWKS tương thích với client/resource server.
- [ ] ID token, UserInfo, issuer, audience và subject được xác minh.
- [ ] Resource Server chấp nhận token hợp lệ và từ chối token sai chữ ký/claim/scope.
- [ ] Client library cũ và mới trong phạm vi hỗ trợ đều được kiểm thử.
- [ ] Migration được chạy trên dữ liệu tổng hợp từ phiên bản cũ.
- [ ] Error response, HTTP header, CORS, cookie và redirect được kiểm tra.
- [ ] Log test không chứa secret, authorization code, access token hoặc refresh token.
- [ ] Các thay đổi giao thức có chủ đích đã có tài liệu và kế hoạch nâng cấp client.

## Kết luận

Kiểm thử hồi quy OAuth/OIDC cần theo dõi hợp đồng từ authorization request đến token, ID token, UserInfo và API được bảo vệ. Hãy chạy cùng kịch bản trên phiên bản cũ và mới, dùng client library đại diện, xác minh cả đường thành công lẫn lỗi và đưa dữ liệu đã lưu qua migration. Cách kiểm thử này giúp phát hiện thay đổi giao thức hoặc hành vi không tương thích trước khi phiên bản Spring Authorization Server mới được đưa vào vận hành.
