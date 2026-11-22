# Kiểm thử client assertion sai chữ ký, sai audience và bị phát lại

Với phương thức `private_key_jwt`, client xác thực tại token endpoint bằng một JWT assertion do private key của client ký. Authorization Server lấy public key đã đăng ký để xác minh chữ ký và kiểm tra các claim xác định client, máy chủ nhận assertion và thời hạn sử dụng. Nếu server chỉ kiểm tra chữ ký mà bỏ qua audience hoặc không phát hiện assertion bị phát lại, một assertion bị đánh cắp có thể bị sử dụng sai mục đích.

Bài học này hướng dẫn kiểm thử ba nhóm lỗi quan trọng: chữ ký không hợp lệ, audience không dành cho Authorization Server hiện tại và assertion đã được sử dụng trước đó. Các ví dụ dùng `private_key_jwt` với RSA và Nimbus JOSE + JWT; có thể áp dụng cùng nguyên tắc cho thuật toán bất đối xứng khác mà deployment cho phép.

Sau bài học này, bạn có thể:

- Phân biệt client assertion dùng để xác thực client với JWT bearer grant dùng làm authorization grant.
- Tạo assertion kiểm thử có `iss`, `sub`, `aud`, `exp`, `iat`, `jti` và `kid`.
- Kiểm thử chữ ký sai, khóa không biết, audience sai và assertion hết hạn.
- Thiết kế replay detection dựa trên `jti` và kho dùng chung có thao tác nguyên tử.
- Kiểm tra client assertion qua token endpoint và quan sát lỗi OAuth phù hợp.
- Kiểm thử request đồng thời và hành vi giữa nhiều Authorization Server instance.

## 1. Phân biệt client assertion và grant assertion

JWT assertion có thể xuất hiện trong hai vai trò khác nhau:

| Cách dùng | Tham số request | Mục đích |
|---|---|---|
| JWT dùng để xác thực client (`private_key_jwt`) | `client_assertion_type`, `client_assertion` | Chứng minh client đang gọi token endpoint là client đã đăng ký |
| JWT bearer authorization grant | `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, `assertion` | Dùng JWT làm credential/authorization grant để xin token theo RFC 7523 |

Lab này kiểm tra **client authentication bằng `private_key_jwt`**. Trong request, `grant_type` có thể là `client_credentials` hoặc grant type khác được client hỗ trợ; `client_assertion` vẫn chỉ là bằng chứng xác thực client. Không nhầm nó với JWT bearer grant và không đưa assertion xác thực client vào trường `assertion` của grant type kia.

Client gửi request đến token endpoint với các tham số:

```text
grant_type=client_credentials
client_id=orders-service
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<signed-client-assertion>
scope=orders.read
```

Client không gửi HTTP Basic credentials trong request này. Authorization Server phải tìm đúng `RegisteredClient`, kiểm tra client đã đăng ký `ClientAuthenticationMethod.PRIVATE_KEY_JWT`, lấy public key của client và xác minh assertion.

## 2. Các claim và header cần kiểm tra

Một client assertion JWT có header và payload theo cấu trúc JWT/JWS. Ví dụ header dùng RSA:

```json
{
  "alg": "RS256",
  "kid": "orders-client-key-2026-01",
  "typ": "JWT"
}
```

Payload cần ràng buộc assertion với client và Authorization Server:

```json
{
  "iss": "orders-service",
  "sub": "orders-service",
  "aud": "https://auth.example.test",
  "iat": 1794859200,
  "exp": 1794859260,
  "jti": "unique-assertion-id"
}
```

Các giá trị thời gian chỉ minh họa. Trong test, tạo claim từ `Clock` hoặc một `Instant` cố định để tránh phụ thuộc thời gian máy chạy.

| Thành phần | Ý nghĩa | Kiểm tra bắt buộc trong lab |
|---|---|---|
| `alg` | Thuật toán ký | Thuộc allowlist mà server chấp nhận; không chấp nhận thuật toán tùy ý từ header |
| `kid` | Định danh public key của client | Tìm được khóa đã đăng ký và không mơ hồ |
| `iss` | Bên phát hành assertion | Khớp `client_id` theo contract client assertion |
| `sub` | Subject của assertion | Khớp `client_id` được xác thực |
| `aud` | Authorization Server nhận assertion | Chứa đúng audience mà server cấu hình chấp nhận |
| `exp` | Thời điểm assertion hết hạn | Còn hiệu lực, xét clock skew đã cấu hình |
| `iat` | Thời điểm phát hành | Nằm trong khoảng thời gian hợp lý theo policy |
| `jti` | Định danh duy nhất của assertion | Chưa từng được chấp nhận trong cửa sổ chống replay |

Với Spring Authorization Server, `JwtClientAssertionDecoderFactory` cung cấp decoder và validator mặc định cho client assertion. Cần kiểm tra chính xác audience mà phiên bản và cấu hình của ứng dụng đang yêu cầu. Trong cấu hình mặc định phổ biến, audience được đối chiếu với issuer của Authorization Server; các deployment có validator tùy chỉnh phải dùng audience đã được thống nhất trong contract. Không tự suy ra audience từ host nội bộ hoặc URL của một pod.

`jti` có mặt trong JWT chưa tự động ngăn replay. Một JWT decoder thuần stateless có thể xác minh cùng một assertion nhiều lần nếu chữ ký và thời gian vẫn hợp lệ. Nếu hệ thống yêu cầu assertion dùng một lần, cần có replay store hoặc cơ chế tương đương để đánh dấu `jti` đã được chấp nhận.

## 3. Cấu hình client kiểm thử

Tạo một confidential client riêng cho test. Đăng ký phương thức xác thực `PRIVATE_KEY_JWT`, grant type cần kiểm thử và public key/JWK Set của client.

Ví dụ cấu hình `RegisteredClient`:

```java
RegisteredClient client = RegisteredClient.withId("registered-orders-service")
        .clientId("orders-service")
        .clientAuthenticationMethod(ClientAuthenticationMethod.PRIVATE_KEY_JWT)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .jwkSetUrl(clientJwksUri)
                .build())
        .build();
```

`clientJwksUri` là URL JWKS công khai của client trong môi trường test. Nếu ứng dụng dùng cách đăng ký JWK trực tiếp hoặc một `JWKSource` tùy chỉnh, hãy giữ nguyên cách tích hợp đó và bảo đảm server có thể lấy public key tương ứng. Private key chỉ nằm ở test client; không đăng ký hoặc công bố private key lên JWKS.

Kiểm tra trước khi chạy test:

- Client có đúng `client_id` và `PRIVATE_KEY_JWT`.
- Client được phép dùng grant type đang gửi.
- Public JWK có `kid` khớp với JWT header.
- JWK có loại khóa, thuật toán và `use`/`key_ops` phù hợp nếu các thuộc tính này được khai báo.
- Issuer của Authorization Server và audience kỳ vọng trong assertion được cấu hình nhất quán.
- Token endpoint được gọi qua URL công khai mà client thực sự sử dụng.

## 4. Tạo client assertion kiểm thử bằng Nimbus

Trong test, tạo một RSA key pair riêng. Nimbus có thể giữ private key để ký và xuất public JWK cho JWKS server giả lập.

```java
static RSAKey generateClientKey(String kid) throws JOSEException {
    return new RSAKeyGenerator(2048)
            .keyID(kid)
            .generate();
}

static String createClientAssertion(
        RSAKey signingKey,
        String clientId,
        String audience,
        Instant issuedAt,
        String jti) throws JOSEException {

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(clientId)
            .subject(clientId)
            .audience(audience)
            .issueTime(Date.from(issuedAt))
            .expirationTime(Date.from(issuedAt.plusSeconds(60)))
            .jwtID(jti)
            .build();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID(signingKey.getKeyID())
            .type(JOSEObjectType.JWT)
            .build();

    SignedJWT assertion = new SignedJWT(header, claims);
    assertion.sign(new RSASSASigner(signingKey.toPrivateKey()));
    return assertion.serialize();
}
```

Đoạn mã giả định đã thêm dependency Nimbus JOSE + JWT và các import tương ứng. Trong test thực tế, dùng `Clock` cố định để tạo `issuedAt`, `exp` và validator cùng tham chiếu một nguồn thời gian. `jti` phải khác nhau cho mỗi assertion mới, trừ các test cố ý phát lại cùng assertion.

Tạo assertion hợp lệ:

```java
String validAssertion = createClientAssertion(
        clientPrivateKey,
        "orders-service",
        expectedAudience,
        clock.instant(),
        "assertion-001");
```

`expectedAudience` phải là giá trị server thực sự chấp nhận. Với cấu hình Spring Authorization Server mặc định phổ biến, dùng issuer công khai của Authorization Server; nếu ứng dụng có audience validator tùy chỉnh, dùng giá trị trong contract của validator đó.

## 5. Gửi assertion đến token endpoint

Ví dụ gọi token endpoint qua MockMvc với client credentials grant:

```java
mockMvc.perform(post(tokenEndpoint)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param(OAuth2ParameterNames.GRANT_TYPE,
                AuthorizationGrantType.CLIENT_CREDENTIALS.getValue())
        .param(OAuth2ParameterNames.CLIENT_ID, "orders-service")
        .param("client_assertion_type",
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        .param("client_assertion", validAssertion)
        .param(OAuth2ParameterNames.SCOPE, "orders.read"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.access_token").isNotEmpty())
    .andExpect(jsonPath("$.token_type").value("Bearer"));
```

`tokenEndpoint` lấy từ cấu hình test hoặc Discovery metadata. Các hằng `OAuth2ParameterNames` cần có trong phiên bản Spring Security đang dùng; nếu phiên bản không cung cấp một hằng cho assertion type, có thể dùng đúng tên parameter chuẩn trong ví dụ. Test thành công cần xác minh thêm access token dùng được tại Resource Server và có scope đã yêu cầu.

## 6. Kiểm thử assertion sai chữ ký

Server phải xác minh chữ ký bằng public key được đăng ký cho client. Có hai trường hợp cần tách riêng:

- `kid` không tồn tại trong JWKS hoặc không thể tìm được public key.
- `kid` tồn tại nhưng assertion được ký bằng private key không khớp public key đó.

Trường hợp thứ hai chứng minh server thực sự kiểm tra chữ ký. Chỉ kiểm tra `kid` tồn tại là chưa đủ.

### 6.1. Tạo assertion ký bằng khóa sai

Tạo hai key pair. Đăng ký public key của `registeredKey` trong JWKS của client, nhưng ký assertion bằng `attackerKey`. Để test tập trung vào chữ ký, có thể dùng cùng `kid` trong header của assertion sai như khóa đã đăng ký, trong khi private key ký thực tế không khớp public key đó.

```java
RSAKey registeredKey = generateClientKey("orders-key-1");
RSAKey attackerKey = generateClientKey("orders-key-1");

String wrongSignatureAssertion = createClientAssertion(
        attackerKey,
        "orders-service",
        expectedAudience,
        clock.instant(),
        "assertion-wrong-signature");
```

Trong fixture JWKS, chỉ công bố `registeredKey.toPublicJWK()`. Không công bố public key của `attackerKey` cho client này.

### 6.2. Assertion với khóa không biết

Tạo assertion ký bằng khóa khác và dùng `kid` không xuất hiện trong JWKS. Decoder không thể chọn khóa để xác minh, do đó client authentication phải thất bại.

Hai test này giúp phân biệt lỗi lookup khóa và lỗi cryptographic verification. Cả hai phải dẫn đến từ chối client authentication, thường là OAuth error `invalid_client` ở token endpoint. Không phản hồi chi tiết như public key nào được tìm thấy hoặc chữ ký sai ở vị trí nào, vì thông tin đó có thể giúp dò cấu hình khóa.

### 6.3. Assertion kiểm thử qua token endpoint

```java
mockMvc.perform(post(tokenEndpoint)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("client_id", "orders-service")
        .param("client_assertion_type",
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        .param("client_assertion", wrongSignatureAssertion)
        .param("scope", "orders.read"))
    .andExpect(jsonPath("$.error").value(OAuth2ErrorCodes.INVALID_CLIENT));
```

HTTP status cho lỗi xác thực client phụ thuộc cách endpoint và authentication mechanism phản hồi trong phiên bản framework. Assertion chính là server không cấp access token và trả error code phù hợp. Không chỉ assert status code mà bỏ qua body.

## 7. Kiểm thử audience sai

Audience ràng buộc assertion với Authorization Server dự định nhận nó. Nếu assertion được tạo cho một server khác, server hiện tại phải từ chối dù chữ ký hoàn toàn hợp lệ.

Tạo assertion bằng đúng private key của client, đúng `iss`, `sub`, `kid`, `iat`, `exp` và `jti`, nhưng đặt `aud` thành issuer của một môi trường khác hoặc một giá trị không nằm trong audience allowlist.

```java
String wrongAudienceAssertion = createClientAssertion(
        clientPrivateKey,
        "orders-service",
        "https://auth-other.example.test",
        clock.instant(),
        "assertion-wrong-audience");
```

Kết quả cần xác minh:

- Chữ ký hợp lệ không làm assertion được chấp nhận nếu audience sai.
- Token endpoint trả lỗi xác thực client.
- Không có access token được phát hành.
- Replay store không đánh dấu assertion là đã sử dụng nếu các claim cơ bản chưa qua validation.
- Không có thông tin nội bộ về issuer/audience được tiết lộ trong response lỗi.

Audience có thể là issuer hoặc một định danh Authorization Server đã thống nhất theo validator. Không chấp nhận mọi audience hoặc bỏ qua kiểm tra audience chỉ để tương thích với client cũ. Nếu cần thay đổi audience trong quá trình nâng cấp, hãy triển khai chuyển tiếp có kế hoạch và kiểm thử cả client/server version cũ lẫn mới.

## 8. Kiểm thử các claim thời gian và định danh

Ngoài chữ ký và audience, cần kiểm tra assertion không thể được tái sử dụng hoặc chuyển sang client khác bằng cách thay claim.

| Biến thể assertion | Kết quả cần xác minh |
|---|---|
| `iss` khác `client_id` | Từ chối client authentication |
| `sub` khác `client_id` | Từ chối client authentication |
| `aud` không khớp Authorization Server | Từ chối client authentication |
| `exp` đã qua | Từ chối |
| `iat` ở tương lai vượt clock skew | Từ chối nếu validator kiểm tra thời điểm phát hành |
| `exp` quá xa trong tương lai | Từ chối nếu policy giới hạn tuổi tối đa assertion |
| Thiếu `jti` khi replay protection yêu cầu | Từ chối |
| `kid` không có trong JWKS | Từ chối |
| `alg` ngoài allowlist hoặc `none` | Từ chối |
| Chữ ký không hợp lệ | Từ chối |

Giữ thời hạn assertion ngắn, thường chỉ đủ cho một lần gọi token endpoint và sai lệch đồng hồ cho phép. Giá trị chính xác phải theo policy của hệ thống. Nếu cho phép clock skew, replay store cần giữ `jti` ít nhất đến sau `exp` cộng clock skew để assertion không thể được chấp nhận lần nữa trong cửa sổ validator vẫn coi token còn hiệu lực.

## 9. Thiết kế và kiểm thử replay protection bằng `jti`

### 9.1. Vì sao cần replay store

Một JWT có chữ ký hợp lệ có thể được gửi lại nhiều lần trong thời hạn `exp`. Kiểm tra chữ ký, `iss`, `sub`, `aud` và thời gian chỉ chứng minh assertion được tạo bởi client hợp lệ và còn trong thời hạn; các kiểm tra stateless này không chứng minh assertion chưa được dùng.

Để bảo vệ replay, Authorization Server cần ghi nhận cặp định danh client và `jti` đã được chấp nhận. Kho này phải dùng chung giữa các instance. Nếu mỗi pod giữ một `Set` trong bộ nhớ, cùng assertion có thể được gửi đến pod A rồi pod B và cả hai đều được chấp nhận.

Một hợp đồng tối thiểu:

```java
public interface ClientAssertionReplayStore {
    /**
     * Atomically reserves this jti until expiresAt.
     * Returns true only for the first successful reservation.
     */
    boolean reserve(String clientId, String jti, Instant expiresAt);
}
```

Implementation có thể dùng Redis với thao tác `SET key value NX EX ...` hoặc database với unique constraint trên `(client_id, jti)` và `expires_at`. Không triển khai bằng chuỗi thao tác `exists` rồi `insert` tách rời vì hai request đồng thời có thể cùng vượt qua bước kiểm tra.

### 9.2. Thứ tự validation

Chỉ reserve `jti` sau khi assertion đã vượt qua xác minh chữ ký và các claim cơ bản như issuer, subject, audience, expiration và thời điểm phát hành. Nếu reserve trước rồi mới phát hiện audience sai, một assertion sai có thể chiếm `jti` và khiến assertion hợp lệ được tạo lại với cùng ID bị từ chối ngoài ý muốn.

Trong Spring Authorization Server, có thể tích hợp logic bổ sung thông qua validator tùy chỉnh của `JwtClientAssertionDecoderFactory` hoặc một `JwtDecoderFactory` tùy chỉnh gắn với `JwtClientAssertionAuthenticationProvider`, tùy phiên bản API đang dùng. Cấu trúc validator nên thực hiện logic theo thứ tự:

```java
OAuth2TokenValidator<Jwt> replayValidator(String clientId) {
    return jwt -> {
        String jti = jwt.getId();
        Instant expiresAt = jwt.getExpiresAt();

        if (!StringUtils.hasText(jti) || expiresAt == null) {
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
        }

        Instant retainUntil = expiresAt.plus(clockSkew);
        boolean firstUse = replayStore.reserve(clientId, jti, retainUntil);

        return firstUse
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
    };
}
```

Đoạn mã minh họa validator riêng; khi ghép vào decoder, phải chạy các validator chữ ký/issuer/subject/audience/time trước replay validator. Có thể tạo một validator tổng hợp: gọi validator cơ bản trước, chỉ khi kết quả không có lỗi mới gọi `replayStore.reserve`. API cấu hình cụ thể của `JwtClientAssertionDecoderFactory` cần khớp đúng phiên bản Spring Authorization Server của dự án.

Không trả lỗi chi tiết như “jti đã tồn tại” ra ngoài token endpoint. Có thể ghi metric hoặc audit event đã loại bỏ assertion/token để vận hành, nhưng không log toàn bộ JWT.

### 9.3. Kiểm thử phát lại cùng assertion

Tạo một assertion hợp lệ với `jti` cố định, gửi request lần thứ nhất và lần thứ hai với nguyên chuỗi JWT đó:

| Lần gửi | Kết quả mong đợi |
|---|---|
| Lần đầu với `jti` chưa có trong store | Xác thực client thành công; grant có thể cấp token |
| Lần thứ hai với cùng assertion và `jti` | Từ chối client authentication; không cấp token thứ hai |
| Assertion mới, `jti` mới | Có thể được chấp nhận nếu các claim khác hợp lệ |
| Assertion mới, cùng `jti` đã dùng | Từ chối |
| Assertion đã hết hạn | Từ chối, dù `jti` chưa xuất hiện trong store |

Ví dụ integration test:

```java
String assertion = createClientAssertion(
        clientPrivateKey,
        "orders-service",
        expectedAudience,
        clock.instant(),
        "replay-test-001");

ResultActions first = postClientCredentials(assertion);
first.andExpect(status().isOk());

ResultActions replay = postClientCredentials(assertion);
replay.andExpect(jsonPath("$.error").value(OAuth2ErrorCodes.INVALID_CLIENT));
```

`postClientCredentials` là helper test gửi đúng các form parameter ở phần trước. Nếu ứng dụng có retry tự động, cần bảo đảm retry không tái sử dụng assertion đã gửi; client phải tạo assertion mới với `jti` mới cho mỗi lần xác thực.

### 9.4. Kiểm thử đồng thời và nhiều instance

Gửi cùng một assertion đến hai request đồng thời, hoặc gửi đến hai Authorization Server instance khác nhau cùng dùng replay store. Chỉ một request được reserve `jti` và xác thực thành công. Request còn lại phải bị từ chối.

Kịch bản này phải dùng replay store thật hoặc implementation có atomic primitive tương đương. Một unit test với `HashSet` trong một JVM không chứng minh được khả năng chống replay khi triển khai nhiều instance.

Kiểm tra thêm khi replay store không khả dụng. Với client assertion authentication, hệ thống nên fail closed: không cấp token nếu không thể xác nhận `jti` chưa bị sử dụng. Không bỏ qua replay check chỉ để duy trì availability trong lúc store lỗi.

## 10. Kiểm thử xoay khóa client

Client có thể xoay private key và public JWK đã đăng ký. Trong giai đoạn chuyển tiếp, server có thể cần nhận cả khóa cũ và khóa mới:

1. Client công bố public key mới với `kid` mới lên JWKS.
2. Server tải hoặc đồng bộ public key mới.
3. Client bắt đầu ký assertion bằng private key mới.
4. Client ngừng ký bằng private key cũ.
5. Giữ public key cũ đủ lâu cho các request đang bay hoặc retry hợp lệ kết thúc, theo policy của hệ thống.
6. Loại public key cũ sau khi không còn cần xác minh assertion được hỗ trợ.

Kiểm thử cả assertion ký bằng khóa cũ và khóa mới trong giai đoạn chuyển tiếp. Sau khi khóa cũ bị loại bỏ và server refresh JWKS, assertion ký bằng khóa cũ phải bị từ chối. `kid` không được tái sử dụng cho một key pair khác.

Nếu client dùng JWKS endpoint từ xa, kiểm thử cache và khả năng refresh của server. Nếu dùng key set tĩnh được lưu cùng RegisteredClient, kiểm tra quy trình cập nhật client registration và tính nhất quán giữa các Authorization Server instance.

## 11. Ma trận kiểm thử bảo mật

| Nhóm | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Happy path | Chữ ký đúng, claim đúng, `jti` mới | Client authentication thành công |
| Wrong signature | Ký bằng private key không khớp public key đã đăng ký | `invalid_client`, không cấp token |
| Unknown `kid` | Header tham chiếu khóa không có trong JWKS | `invalid_client`, không cấp token |
| Wrong audience | Chữ ký đúng nhưng `aud` sai | `invalid_client`, không cấp token |
| Wrong issuer | `iss` không khớp client ID | `invalid_client` |
| Wrong subject | `sub` không khớp client ID | `invalid_client` |
| Expired assertion | `exp` đã qua | `invalid_client` |
| Future assertion | `iat` vượt clock skew | Từ chối theo validator thời gian |
| Missing jti | Không có `jti` khi replay protection yêu cầu | `invalid_client` |
| Replay | Gửi lại cùng assertion và `jti` | Chỉ lần đầu có thể thành công |
| Concurrent replay | Hai request đồng thời cùng `jti` | Tối đa một request thành công |
| Cross-node replay | Gửi cùng assertion đến hai instance | Tối đa một instance chấp nhận |
| Replay store outage | Không thể reserve `jti` | Fail closed, không cấp token |
| Algorithm downgrade | `alg` ngoài allowlist hoặc `none` | Từ chối |
| Client not registered for method | Client không có `PRIVATE_KEY_JWT` | `invalid_client` |
| Client not allowed grant | Client auth hợp lệ nhưng grant không được đăng ký | `unauthorized_client` |

Ngoài error code, xác minh không có access token được tạo hoặc lưu khi client authentication thất bại. Response không được chứa assertion, private key, JWKS nội bộ hoặc thông tin chi tiết về lý do chữ ký thất bại.

## 12. Tự động hóa kiểm thử

Có thể tổ chức test theo cấu trúc:

```text
src/test/java/.../clientassertion/
  ClientAssertionFactory.java
  ClientAssertionSignatureTest.java
  ClientAssertionAudienceTest.java
  ClientAssertionClaimsTest.java
  ClientAssertionReplayTest.java
  ClientAssertionConcurrencyTest.java
  ClientAssertionKeyRotationTest.java
```

Gợi ý triển khai:

- Dùng Nimbus để tạo key pair và ký JWT assertion thực.
- Dùng MockMvc hoặc WebTestClient gọi token endpoint.
- Dùng JWKS stub có thể thay đổi để mô phỏng public key đã đăng ký và key rotation.
- Dùng `Clock` cố định để kiểm tra `iat`, `exp` và clock skew.
- Dùng Redis/Testcontainers hoặc database thật cho replay store và concurrency test.
- Chạy test qua nhiều instance hoặc nhiều application context nếu cần chứng minh shared replay state.
- Tạo assertion mới cho mỗi request hợp lệ; chỉ test replay mới tái sử dụng nguyên assertion.
- Che token, assertion, secret và private key khỏi log và báo cáo test.

Trong CI, chạy test chữ ký, audience, claim và replay cơ bản ở integration build. Chạy test concurrency, replay store outage và key rotation ở pre-release/staging với hạ tầng tương đương production.

## 13. Checklist trước khi phát hành

- [ ] Client đăng ký đúng `PRIVATE_KEY_JWT` và public key tương ứng.
- [ ] `client_assertion_type` đúng URI chuẩn JWT bearer client assertion.
- [ ] `iss` và `sub` khớp client ID theo contract.
- [ ] `aud` khớp audience mà Authorization Server thực sự xác minh.
- [ ] `exp` ngắn và được kiểm tra cùng clock skew.
- [ ] `iat` được kiểm tra theo policy thời gian.
- [ ] `kid` duy nhất và trỏ đến public key phù hợp.
- [ ] Thuật toán ký nằm trong allowlist.
- [ ] Chữ ký sai và khóa không biết bị từ chối.
- [ ] Audience sai bị từ chối dù chữ ký hợp lệ.
- [ ] `jti` được kiểm tra bằng replay store dùng chung nếu policy yêu cầu one-time assertion.
- [ ] Replay check chỉ reserve sau khi các claim cơ bản đã hợp lệ.
- [ ] Hai request đồng thời với cùng `jti` không thể cùng thành công.
- [ ] Replay store lỗi khiến hệ thống fail closed.
- [ ] Key rotation được kiểm thử trên mọi instance.
- [ ] Token endpoint không trả thông tin chi tiết hoặc credential trong error response/log.

## Kết luận

Kiểm thử `private_key_jwt` phải xác minh đồng thời danh tính client, chữ ký, audience, thời hạn và tính duy nhất của assertion. Chữ ký đúng không đủ nếu assertion được gửi đến sai Authorization Server; `jti` có mặt cũng không đủ nếu server không lưu và kiểm tra nó bằng thao tác nguyên tử. Hãy dùng JWT có chữ ký thật, gọi token endpoint qua integration test và kiểm thử replay giữa nhiều instance để chứng minh client assertion không thể bị giả mạo hoặc tái sử dụng.
