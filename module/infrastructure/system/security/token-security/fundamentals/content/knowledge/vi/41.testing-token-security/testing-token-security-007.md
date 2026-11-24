# Test wrong token type

Một API có thể nhận được token hợp lệ về mặt mật mã nhưng sai mục đích sử dụng. Ví dụ, ID token được ký đúng bởi Identity Provider, refresh token vẫn còn hiệu lực hoặc access token dành cho một API khác. Nếu Resource Server chỉ kiểm tra chữ ký hay chỉ giải mã được JWT rồi chấp nhận, hệ thống có thể nhầm một loại token thành loại khác và cấp quyền sai.

Bài học này thuộc chương **Testing token security** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là thiết kế và thực hiện kiểm thử để chứng minh mỗi endpoint chỉ chấp nhận đúng loại token theo hợp đồng OAuth 2.0/OIDC: access token cho Resource Server, refresh token cho Token Endpoint khi thực hiện refresh grant, và ID token cho client OIDC dùng để xác minh kết quả đăng nhập.

## 1. Wrong token type là lỗi gì?

**Wrong token type** xảy ra khi một thành phần nhận token hợp lệ ở một ngữ cảnh nhưng lại dùng token đó ở ngữ cảnh khác. Đây là dạng nhầm lẫn hoặc thay thế token (token confusion/substitution). Rủi ro tăng lên khi cùng một issuer phát hành nhiều loại JWT và chúng dùng chung khóa ký, cấu trúc claim hoặc thư viện xác minh.

Ví dụ một hệ thống có ba endpoint:

| Endpoint | Credential đúng | Credential sai cần từ chối |
| --- | --- | --- |
| `GET /api/orders` | Access token được cấp cho `orders-api` | ID token, refresh token, access token của API khác |
| `POST /oauth/token` với `grant_type=refresh_token` | Refresh token còn hiệu lực và gắn đúng client/grant | ID token, access token, refresh token đã thu hồi hoặc đã bị replay |
| OIDC client callback | ID token hợp lệ cho đúng `client_id`, issuer và flow | Access token hoặc refresh token bị dùng thay ID token |

Một JWT có ba phần và giải mã thành JSON không có nghĩa nó là access token. Chữ ký hợp lệ chỉ chứng minh token được ký bởi khóa tương ứng và nội dung không bị sửa kể từ khi ký. Nó không tự chứng minh token được cấp cho endpoint hiện tại.

## 2. Phân biệt loại token trước khi viết test

### 2.1. Access token

Access token là credential mà client gửi đến Resource Server để truy cập tài nguyên. Nó có thể là JWT hoặc opaque token. API phải xác minh token theo hợp đồng của issuer và chính API đó, gồm issuer, audience/resource, thời hạn, trạng thái hiệu lực, loại token và scope/quyền cần thiết.

Ví dụ JWT access token theo profile RFC 9068:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "test-key-1"
}
~~~

~~~json
{
  "iss": "https://identity.example.test/",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "web-client",
  "iat": 1795400000,
  "exp": 1795400900,
  "jti": "access-001",
  "scope": "orders:read"
}
~~~

Đây là payload minh họa cho môi trường test; các giá trị thời gian phải được thay bằng thời gian phù hợp với clock của test. Khi áp dụng RFC 9068, JWT access token phải được ký và Resource Server phải kiểm tra header `typ` là `at+jwt` hoặc `application/at+jwt`. Prefix `application/` được khuyến nghị bỏ đi. Profile còn quy định kiểm tra các claim và thuộc tính khác; không chỉ dựa vào `typ`.

### 2.2. ID token

ID token thuộc OpenID Connect. Nó thông báo kết quả xác thực cho OIDC client (Relying Party), với `aud` xác định client hoặc các client được nhận token. Client dùng ID token để xác minh issuer, subject, audience, thời gian và các ràng buộc của flow như `nonce` khi có yêu cầu.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.test/",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1795400000,
  "exp": 1795400900,
  "nonce": "login-nonce-abc"
}
~~~

ID token có thể có chữ ký đúng và chứa cùng `sub` với access token. Tuy nhiên, `aud=web-client` không phải `aud=orders-api`. Gửi ID token đến API phải bị từ chối, kể cả khi API và OIDC client tin cùng một issuer hoặc dùng chung khóa xác minh.

### 2.3. Refresh token

Refresh token được gửi đến Authorization Server tại Token Endpoint để xin access token mới theo grant và chính sách đã cấp. Client không gửi refresh token như Bearer credential đến Resource Server.

Refresh token thường là opaque string, nhưng cách biểu diễn phụ thuộc hệ thống. Vì vậy, không thể kết luận loại token chỉ bằng cách đếm dấu chấm hoặc nhìn chuỗi có giống JWT hay không. Authorization Server phải quản lý trạng thái, client binding, rotation và thu hồi theo thiết kế.

### 2.4. Opaque access token

Opaque access token không để Resource Server tự giải mã payload. Resource Server có thể xác minh bằng token introspection qua kênh được bảo vệ. Response thường có `active`, `aud`, `scope`, `iss` hoặc metadata liên quan tùy issuer và cấu hình.

Không được hiểu `active=true` là token phù hợp với mọi API. Token còn hiệu lực vẫn có thể dành cho resource khác hoặc cho mục đích khác. Hãy kiểm tra audience, scope, client/resource context và các metadata phân biệt access token theo hợp đồng của Authorization Server. `token_type_hint` trong yêu cầu introspection chỉ là gợi ý xử lý, không phải bằng chứng xác nhận loại token.

## 3. Hợp đồng xác minh loại token

Trước khi viết test, xác định chính xác quy tắc của hệ thống. Không có một claim tùy biến duy nhất được mọi nhà cung cấp OAuth/OIDC dùng giống nhau.

| Thuộc tính | Ý nghĩa khi xác minh | Lưu ý kiểm thử |
| --- | --- | --- |
| `typ` trong JWT header | Khai báo kiểu nội dung/profile JWT | Chỉ có ý nghĩa khi profile yêu cầu kiểm tra; với RFC 9068, kiểm tra `at+jwt` hoặc `application/at+jwt` |
| `iss` | Issuer đã phát hành token | Phải thuộc issuer được cấu hình tin cậy |
| `aud` | Resource hoặc client được nhận token | Access token phải dành cho API hiện tại; ID token dành cho OIDC client |
| `exp`, `nbf`, `iat` | Thời gian hiệu lực và thời điểm phát hành | Kiểm tra theo clock và clock skew đã cấu hình |
| `scope` | Quyền truy cập được cấp | Không dùng sự hiện diện của `scope` để tự kết luận token là access token |
| `token_use` hoặc `token_type` | Claim phân biệt loại token theo nhà cung cấp | Chỉ dùng nếu issuer quy định rõ; đây thường là claim riêng, không mặc định là chuẩn chung |
| `client_id`, `sub`, `jti` | Client, subject và định danh token theo profile | Kiểm tra theo hợp đồng; không thay thế issuer/audience/type validation |

Nếu Authorization Server triển khai JWT access token theo RFC 9068, Resource Server phải kiểm tra `typ` và các yêu cầu của profile đó. Nếu issuer dùng profile riêng, Resource Server phải xác minh đúng bộ claim/header do issuer quy định. Không được tự thêm giả định rằng mọi access token đều có claim `token_use=access`.

RFC 8725 khuyến nghị dùng explicit typing cho JWT mới và yêu cầu các loại JWT khác nhau của cùng issuer phải có quy tắc xác minh loại trừ lẫn nhau. Có thể kết hợp nhiều tín hiệu: `typ`, tập claim bắt buộc, giá trị `aud` khác nhau, issuer riêng hoặc khóa riêng. Một tín hiệu đơn lẻ không nên được xem là toàn bộ chính sách.

## 4. Thiết kế test matrix

Với Resource Server `orders-api`, hãy chuẩn bị ít nhất các trường hợp sau:

| Mã | Token gửi đến API | Điều kiện | Kết quả mong đợi |
| --- | --- | --- | --- |
| WT-01 | Access token hợp lệ | Đúng issuer, type, audience, thời gian và scope | Cho qua xác thực; endpoint trả kết quả theo quyền |
| WT-02 | ID token hợp lệ | Chữ ký đúng nhưng `aud=web-client` hoặc sai profile access token | `401 invalid_token` |
| WT-03 | Refresh token còn hiệu lực | Token được cấp để refresh tại Token Endpoint | `401 invalid_token` |
| WT-04 | Access token của `billing-api` | Sai audience | `401 invalid_token` |
| WT-05 | JWT có `typ` sai hoặc thiếu | API yêu cầu RFC 9068 | `401 invalid_token` |
| WT-06 | JWT có `token_use=id` | Issuer quy định claim này cho ID token | `401 invalid_token` |
| WT-07 | Token sai issuer | Issuer không nằm trong cấu hình tin cậy | `401 invalid_token` |
| WT-08 | Token hết hạn hoặc chưa đến `nbf` | Ngoài thời gian hiệu lực | `401 invalid_token` |
| WT-09 | Token chữ ký sai hoặc dùng thuật toán không được phép | Không thỏa chính sách xác minh | `401 invalid_token` |
| WT-10 | Opaque access token hợp lệ | Introspection active, audience đúng, scope đủ | Cho qua xác thực; endpoint trả kết quả theo quyền |
| WT-11 | Opaque token active nhưng sai audience hoặc sai mục đích | Metadata không phù hợp API | `401 invalid_token` |
| WT-12 | Access token đúng loại nhưng thiếu scope | Danh tính/token hợp lệ, quyền không đủ | `403 insufficient_scope` |

Ở Token Endpoint, bổ sung test riêng cho refresh grant:

| Mã | Yêu cầu | Kết quả mong đợi |
| --- | --- | --- |
| RT-01 | `grant_type=refresh_token` với refresh token hợp lệ, đúng client và chưa bị thu hồi | Cấp access token mới theo chính sách |
| RT-02 | Gửi access token vào trường `refresh_token` | Từ chối grant, thường là `invalid_grant` |
| RT-03 | Gửi ID token vào trường `refresh_token` | Từ chối grant, thường là `invalid_grant` |
| RT-04 | Refresh token hết hạn, bị thu hồi hoặc không thuộc client | Từ chối grant |
| RT-05 | Dùng lại refresh token cũ sau rotation | Phát hiện replay và áp dụng chính sách thu hồi/token family |

Mã lỗi cụ thể tại Token Endpoint cần tuân theo hợp đồng OAuth của Authorization Server. Không áp dụng máy móc mã lỗi Resource Server cho Token Endpoint.

## 5. Kiểm thử JWT type validation trong Spring Security

Giả sử API dùng Spring Security OAuth 2.0 Resource Server và issuer phát hành JWT access token theo RFC 9068. Ngoài xác minh issuer và thời gian, Resource Server cần kiểm tra audience và loại JWT. Ví dụ validator dưới đây minh họa kiểm tra header `typ`:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AccessTokenTypeValidator
        implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Object typ = jwt.getHeaders().get("typ");

        boolean isAccessToken =
                "at+jwt".equals(typ)
                || "application/at+jwt".equals(typ);

        if (isAccessToken) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "JWT is not an access token for this profile",
                        null
                )
        );
    }
}
~~~

Ghép validator loại token với validator issuer, thời gian và audience:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://identity.example.test/";
    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null)
        );
    };

    OAuth2TokenValidator<Jwt> requiredClaimsValidator = jwt -> {
        boolean complete = jwt.getSubject() != null
                && !jwt.getSubject().isBlank()
                && jwt.getClaimAsString("client_id") != null
                && !jwt.getClaimAsString("client_id").isBlank()
                && jwt.getIssuedAt() != null
                && jwt.getId() != null
                && !jwt.getId().isBlank();
        if (complete) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Missing required access token claim", null)
        );
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    audienceValidator,
                    requiredClaimsValidator,
                    new AccessTokenTypeValidator()
            )
    );
    return decoder;
}
~~~

Đây là ví dụ cho issuer tuân thủ RFC 9068. Ngoài issuer, thời gian, audience và `typ`, ví dụ còn kiểm tra sự hiện diện của các claim bắt buộc `sub`, `client_id`, `iat` và `jti`; validator thực tế cần theo đầy đủ profile và chính sách của issuer. Cần import các lớp Spring Security tương ứng và cấu hình thuật toán ký được chấp nhận theo chính sách của hệ thống. Nếu issuer không triển khai RFC 9068, hãy thay validator bằng quy tắc token type trong hợp đồng thực tế; không bật kiểm tra `at+jwt` một cách tùy tiện cho mọi JWT.

Validator phải được gọi trong luồng xác minh thật của Resource Server. Chỉ decode JWT bằng thư viện hoặc chỉ kiểm tra `typ` trước khi xác minh chữ ký là không đủ.

## 6. Viết integration test qua HTTP filter chain

Một lỗi thường gặp trong test là dùng helper tạo `JwtAuthenticationToken` trực tiếp rồi cho rằng đã kiểm thử xác minh chữ ký và loại token. Ví dụ `SecurityMockMvcRequestPostProcessors.jwt()` hữu ích để kiểm thử phân quyền/controller với một principal đã được dựng sẵn, nhưng nó có thể bỏ qua bước giải mã và xác minh JWT thực tế. Vì vậy, cần có integration test gửi bearer token được ký bằng khóa test qua đúng filter chain.

Ví dụ cấu trúc kiểm thử:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class WrongTokenTypeIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsAccessTokenForOrdersApi() throws Exception {
        String token = signedTestJwt(
                "at+jwt",
                "orders-api",
                "access"
        );

        mockMvc.perform(get("/api/orders")
                        .header(
                                HttpHeaders.AUTHORIZATION,
                                "Bearer " + token
                        ))
                .andExpect(status().isOk());
    }

    @Test
    void rejectsIdTokenEvenWhenSignatureIsValid() throws Exception {
        String token = signedTestJwt(
                "JWT",
                "web-client",
                "id"
        );

        mockMvc.perform(get("/api/orders")
                        .header(
                                HttpHeaders.AUTHORIZATION,
                                "Bearer " + token
                        ))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsAccessTokenForAnotherAudience() throws Exception {
        String token = signedTestJwt(
                "at+jwt",
                "billing-api",
                "access"
        );

        mockMvc.perform(get("/api/orders")
                        .header(
                                HttpHeaders.AUTHORIZATION,
                                "Bearer " + token
                        ))
                .andExpect(status().isUnauthorized());
    }
}
~~~

`signedTestJwt` là test fixture cần tự triển khai bằng private key chỉ dành cho test, tạo claim và header đúng với từng kịch bản. Với ví dụ trên, fixture phải tạo JWT có chữ ký hợp lệ theo public key mà decoder test tin cậy. Đối với ID token, có thể dùng cùng khóa test để chứng minh rằng **chữ ký đúng nhưng token vẫn sai loại**. Không dùng private key production hoặc token thật của người dùng trong test.

Nếu dùng `token_use` trong test fixture, hãy giữ nhất quán với validator đã cấu hình. Đoạn validator RFC 9068 ở mục trước phân biệt bằng `typ`; claim `token_use` trong fixture chỉ có ý nghĩa nếu ứng dụng có validator riêng cho claim đó. Không để test dữ liệu và validator mô tả hai hợp đồng khác nhau.

Nên tách ba lớp test:

1. **Unit test validator:** kiểm tra từng tổ hợp header/claim, bao gồm typ đúng, sai, thiếu, audience đúng/sai và issuer không hợp lệ.
2. **Integration test Resource Server:** gửi JWT có chữ ký qua HTTP filter chain, kiểm tra decoder, validator và response thực tế.
3. **Authorization test:** sau khi token đã được xác thực, kiểm tra scope/role và quyền trên endpoint. Có thể dùng helper dựng principal cho nhóm test này nếu mục tiêu không phải xác minh token.

## 7. Kiểm thử opaque token và introspection

Với opaque access token, Resource Server gọi introspection endpoint bằng thông tin xác thực của chính Resource Server. Test cần mô phỏng response introspection và xác minh API chỉ chấp nhận token có trạng thái, audience và quyền phù hợp.

| Response introspection | Kết quả ở `orders-api` |
| --- | --- |
| `active=false` | Từ chối |
| `active=true`, `aud=orders-api`, scope đủ | Cho qua xác thực và tiếp tục phân quyền |
| `active=true`, `aud=billing-api` | Từ chối |
| `active=true` nhưng thiếu metadata cần thiết theo hợp đồng | Từ chối an toàn |
| `active=true` nhưng token được issuer xác định là refresh token | Từ chối |
| Introspection endpoint timeout hoặc lỗi xác thực | Không coi lỗi là token hợp lệ; áp dụng chính sách fail-closed cho xác minh |

Nếu Authorization Server trả thêm trường riêng để nhận diện token class, Resource Server phải kiểm tra trường đó theo hợp đồng. `active` chỉ biểu thị trạng thái hoạt động theo định nghĩa của Authorization Server; nó không thay thế việc xác định token có dành cho resource đang gọi hay không. Bảo vệ kết nối introspection bằng TLS và không ghi token thô vào log.

Mock introspection server nên có test cho cả response hợp lệ, inactive, thiếu trường, sai audience, lỗi HTTP và timeout. Đừng chỉ mock response `active=true` trong tất cả test, vì như vậy không kiểm tra được nhánh từ chối.

## 8. Kiểm tra response và phân biệt lỗi xác thực với lỗi phân quyền

Đối với Bearer token gửi đến Resource Server:

- Không có thông tin xác thực: thường trả `401 Unauthorized` và Bearer challenge phù hợp.
- Token hết hạn, bị thu hồi, sai chữ ký, sai loại hoặc sai audience: trả `401 Unauthorized` với `invalid_token` theo RFC 6750.
- Access token đúng loại và hợp lệ nhưng thiếu scope cần thiết: trả `403 Forbidden` với `insufficient_scope`.

Ví dụ response khi token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Ví dụ response khi thiếu quyền:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders:read"
~~~

Không đưa nguyên token, chữ ký, khóa, claim nhạy cảm hoặc chi tiết nội bộ của validator vào response cho client. Log nội bộ có thể ghi mã lý do đã chuẩn hóa, request/correlation ID và endpoint; phải che token và dữ liệu nhạy cảm.

## 9. Những lỗi kiểm thử và triển khai thường gặp

### Chỉ kiểm tra chữ ký

ID token và access token có thể cùng được ký bởi một issuer. Nếu API chỉ xác minh chữ ký, ID token có nguy cơ được chấp nhận. Test phải dùng ID token có chữ ký hợp lệ để chứng minh validator kiểm tra cả loại token và audience.

### Chỉ kiểm tra payload có `scope`

Sự hiện diện của `scope` không phải bằng chứng độc lập rằng token là access token. Hãy kiểm tra token profile, issuer, audience và các ràng buộc khác. Kiểm tra scope là bước phân quyền sau khi token đã vượt qua xác thực.

### Chỉ kiểm tra `typ` mà bỏ qua chữ ký

JWT header có thể được đọc trước khi xác minh, nhưng attacker có thể tự tạo header `typ=at+jwt`. Chỉ dùng header sau khi toàn bộ JWT được xác minh bằng khóa và thuật toán tin cậy; validator type là một phần của pipeline xác minh.

### Chấp nhận mọi audience của cùng issuer

Một issuer có thể phát hành token cho nhiều API và client. Nếu `orders-api` nhận token dành cho `billing-api`, hệ thống mắc lỗi token redirect/substitution. Test sai audience phải đi qua cùng cấu hình decoder như production.

### Nhầm `token_type` trong OAuth response với loại JWT

Giá trị `token_type=Bearer` trong token response mô tả cách client sử dụng access token trong Authorization header. Nó không thay thế JWT header `typ` và cũng không chứng minh một chuỗi JWT cụ thể là access token.

### Tin `token_type_hint` trong introspection

Đây là gợi ý cho Authorization Server về loại token đang được introspect. Server có thể bỏ qua gợi ý hoặc phải tìm theo cách khác. Resource Server vẫn phải xác minh response thực tế và audience/context.

### Dùng test helper bỏ qua bước xác minh

Nếu mọi test chỉ dựng principal đã xác thực sẵn, cấu hình decoder sai có thể không bị phát hiện. Duy trì ít nhất một bộ integration test gửi token có chữ ký qua filter chain và một bộ test introspection thực tế ở mức contract.

## 10. Checklist trước khi hoàn thành test suite

- [ ] Đã liệt kê các endpoint và loại token mà mỗi endpoint chấp nhận.
- [ ] Có test access token hợp lệ cho đúng API.
- [ ] Có test ID token hợp lệ về chữ ký nhưng sai mục đích/audience đối với API.
- [ ] Có test refresh token bị gửi đến Resource Server.
- [ ] Có test access token bị gửi vào refresh grant tại Token Endpoint.
- [ ] Có test sai/thiếu `typ` khi triển khai RFC 9068.
- [ ] Có test sai issuer, audience, thời hạn, chữ ký và thuật toán.
- [ ] Có test opaque token với active, audience, scope và trạng thái sai.
- [ ] Có test token đúng loại nhưng thiếu scope để phân biệt `403` với `401`.
- [ ] Integration test chạy qua decoder/introspection và security filter chain thật của ứng dụng.
- [ ] Test dùng khóa và token fixture dành riêng cho môi trường test.
- [ ] Log và response không làm lộ bearer token hoặc dữ liệu xác thực.

## 11. Tình huống tổng hợp

`orders-api` và OIDC client `web-client` cùng tin issuer `https://identity.example.test/`. Một người dùng đăng nhập thành công. Client nhận ID token có chữ ký hợp lệ, `aud=web-client`, `sub=user-123`; đồng thời nhận access token có `typ=at+jwt` và `aud=orders-api`. Vì hai token cùng issuer và cùng subject, lập trình viên gửi ID token đến `GET /api/orders` và thấy chữ ký xác minh thành công.

**Kết quả đúng:** API phải từ chối ID token với `401 invalid_token` vì token không tuân theo access-token profile và audience không dành cho `orders-api`. Khi gửi access token hợp lệ, API tiếp tục kiểm tra scope `orders:read` và quyền truy cập tài nguyên. Nếu access token hợp lệ nhưng thiếu scope, API trả `403 insufficient_scope`. Refresh token chỉ được gửi đến Token Endpoint để xin access token mới; nó không được dùng thay access token khi gọi API.

Hãy viết test sao cho ba kết quả này được kiểm chứng qua pipeline thực tế. Một test chỉ chứng minh “JWT có chữ ký đúng” chưa chứng minh hệ thống đã kiểm tra “đúng loại token cho đúng endpoint”.

## 12. Tài liệu chuẩn tham khảo

- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): định nghĩa profile JWT access token, header `typ` và yêu cầu xác minh tại Resource Server.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): explicit typing, audience validation và quy tắc xác minh loại trừ lẫn nhau để chống nhầm lẫn JWT.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cách gửi Bearer access token và phản hồi `invalid_token`/`insufficient_scope`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): xác minh trạng thái và metadata của opaque token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): cấu trúc và cách xác minh ID token tại OIDC client.
