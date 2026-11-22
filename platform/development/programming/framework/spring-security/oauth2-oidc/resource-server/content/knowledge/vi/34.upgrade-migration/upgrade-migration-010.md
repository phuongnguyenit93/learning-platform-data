# Giữ bộ token, khóa, phản hồi lỗi và ca kiểm thử từ chối làm mốc so sánh

Khi nâng cấp Spring Security, Spring Boot hoặc cấu hình OAuth 2.0 / OIDC Resource Server, ứng dụng có thể vẫn khởi động và trả HTTP 200 cho happy path nhưng đã thay đổi cách xác minh token hoặc xử lý lỗi. Ví dụ: validator audience bị bỏ sót, khóa cũ không còn được nhận diện, token hết hạn lại được chấp nhận, response 401 mất Bearer challenge, hoặc request thiếu scope bị chuyển thành 401 thay vì 403.

Để phát hiện các thay đổi này, hãy duy trì một **regression baseline** gồm bốn thành phần có thể tái tạo:

1. **Bộ token test:** JWT và opaque token đại diện cho các trường hợp hợp lệ, biên và bị từ chối.
2. **Bộ khóa test:** private/public key, JWKS và key ID ổn định để ký, xác minh và kiểm tra rotation.
3. **Bộ phản hồi lỗi mong đợi:** status, headers, Bearer challenge và response body theo API contract.
4. **Bộ ca kiểm thử từ chối:** chứng minh token sai hoặc thiếu quyền bị chặn trước khi business operation chạy.

Baseline là hợp đồng hành vi của ứng dụng. Khi thay dependency hoặc cấu hình, chạy cùng một bộ vector trên cấu hình cũ và mới, so sánh kết quả rồi điều tra mọi khác biệt có chủ đích hoặc ngoài ý muốn. Không tạo baseline bằng token production hoặc secret thật; mọi fixture phải dùng dữ liệu test được quản lý riêng.

## 1. Baseline bảo vệ điều gì?

Một lần migration có thể thay đổi nhiều tầng:

- Cách trích xuất Bearer token từ HTTP request.
- Cách decode JWT và xác minh chữ ký.
- Cách tải, cache và làm mới JWK Set.
- Cách kiểm tra issuer, audience, timestamp và algorithm.
- Cách introspect opaque token và ánh xạ metadata thành principal/authorities.
- Cách quyết định request được phép hay bị từ chối.
- Cách ánh xạ exception thành HTTP status, header và body.
- Cách filter chain, method security và custom handlers được đăng ký.

Baseline không chỉ kiểm tra một endpoint thành công. Nó phải ghi nhận cả những trường hợp mà ứng dụng **bắt buộc phải từ chối**. Một thay đổi làm token hợp lệ bị từ chối là regression về availability; một thay đổi làm token không hợp lệ được chấp nhận là regression bảo mật nghiêm trọng.

## 2. Bốn lớp của một test vector

Mỗi vector nên mô tả đầu vào, môi trường xác minh, kết quả authentication và kết quả HTTP:

| Lớp | Nội dung | Ví dụ |
| --- | --- | --- |
| Input | Token, headers, request method/path/body | JWT có audience sai gọi GET /api/orders |
| Verification fixture | Key/JWKS, issuer, clock, introspection response | Test JWKS chứa public key có kid cố định |
| Expected security result | Authenticated, rejected, authorization denied | Rejected vì audience mismatch |
| Expected API result | Status, challenge, body và side effect | 401, Bearer invalid_token, service không được gọi |

Một vector cần đủ thông tin để người khác chạy lại mà không phải đoán token được ký bằng key nào, clock đang là thời điểm nào hoặc endpoint dùng chain nào.

## 3. Phân biệt test token với token đang dùng ở production

Không lấy access token thật từ browser, log, database hoặc môi trường staging để đưa vào fixture. Token thật có thể còn hiệu lực, chứa PII và phụ thuộc trạng thái Authorization Server.

Dùng các fixture được tạo riêng:

- JWT được ký bằng private key chỉ dành cho test.
- Public JWK/JWKS tương ứng được dùng trong decoder test.
- Opaque token là chuỗi giả không có giá trị ở IdP thật.
- Introspection response được mock theo từng case.
- Subject, tenant, client ID và audience là dữ liệu tổng hợp.
- Clock và key rotation được điều khiển trong test.

Một fixture có thể commit trong repository nếu chỉ chứa test key và dữ liệu giả. Đặt tên rõ ràng như test-only để không bị dùng nhầm làm cấu hình runtime.

## 4. Định nghĩa bộ token theo mục đích

Không cần tạo hàng trăm token ngẫu nhiên. Hãy tạo một corpus nhỏ nhưng bao phủ các ranh giới xác minh quan trọng:

| Nhóm | Vector đại diện | Kết quả mong đợi |
| --- | --- | --- |
| Valid | Signature, issuer, audience, time hợp lệ | Authentication success |
| Expired | exp nằm trước test clock | Rejected |
| Not yet valid | nbf nằm sau test clock | Rejected |
| Wrong issuer | iss không thuộc trust configuration | Rejected |
| Wrong audience | aud không chứa resource hiện tại | Rejected |
| Bad signature | Payload hợp lệ nhưng ký bằng key khác | Rejected |
| Unknown key | kid không có trong JWKS được tin cậy | Rejected hoặc refresh rồi reject |
| Unsupported algorithm | alg ngoài allowlist | Rejected |
| Missing required claim | Thiếu claim theo token profile | Rejected theo policy |
| Insufficient scope | Token hợp lệ nhưng thiếu authority | Authentication success, authorization denied |
| Wrong tenant/owner | Scope đúng nhưng domain access không hợp lệ | Authorization denied |
| Opaque inactive | Introspection trả active=false | Rejected |
| Opaque active, no scope | active=true nhưng thiếu quyền | Authenticated, authorization denied |
| Malformed credential | Bearer value/JWT format không hợp lệ | Rejected |

Tách token invalid khỏi token hợp lệ nhưng thiếu quyền. Hai trường hợp thường có status khác nhau và cần metric/runbook khác nhau.

## 5. Đặt tên vector ổn định

Dùng ID không chứa dữ liệu nhạy cảm, không phụ thuộc thời điểm chạy:

```text
jwt.valid.orders-reader
jwt.expired.orders-reader
jwt.not-before.future
jwt.issuer.untrusted
jwt.audience.billing-only
jwt.signature.wrong-key
jwt.key.unknown-kid
jwt.algorithm.disallowed
jwt.scope.missing-write
jwt.subject.missing
opaque.active.orders-reader
opaque.inactive
opaque.active.scope-empty
opaque.introspection.invalid-client
opaque.introspection.timeout
```

ID vector là tên test fixture, không phải metric label bắt buộc. Khi đổi tên fixture, giữ mapping hoặc ghi migration để lịch sử regression vẫn đọc được.

Không đặt subject thật, email, token value hoặc private key identifier nhạy cảm trong tên vector.

## 6. Cố định thời gian để test token có thể tái lập

JWT chứa các NumericDate claims như exp, nbf và iat. Nếu test dùng Instant.now() ở nhiều nơi, kết quả có thể khác nhau theo thời gian chạy, timezone, clock skew hoặc tốc độ CI.

Chọn một thời điểm cố định:

```java
static final Instant TEST_NOW =
    Instant.parse("2030-01-15T10:00:00Z");

static final Clock TEST_CLOCK =
    Clock.fixed(TEST_NOW, ZoneOffset.UTC);
```

Tạo token tương đối với thời điểm đó:

```java
Instant issuedAt = TEST_NOW.minusSeconds(60);
Instant expiresAt = TEST_NOW.plusSeconds(300);
Instant notBefore = TEST_NOW.minusSeconds(30);
```

Token expired có thể đặt exp trước TEST_NOW; token not-yet-valid đặt nbf sau TEST_NOW. Dùng clock skew được khai báo trong validator để kiểm tra cả ranh giới ngay trước, đúng tại và ngay sau thời điểm chấp nhận.

Không dùng thời gian hiện tại của máy CI làm oracle ngầm. Nếu decoder/validator hỗ trợ inject Clock, truyền test clock; nếu không, thiết kế fixture với khoảng thời gian đủ rộng và ghi rõ tolerance.

## 7. Tạo JWT test bằng key pair ổn định

Một cách tốt là tạo RSA key pair chỉ dùng trong test, gắn kid cố định và dùng cùng key cho encoder/decoder fixture.

Ví dụ với Nimbus JOSE + JWT:

```java
RSAKey signingJwk = new RSAKey.Builder((RSAPublicKey) keyPair.getPublic())
    .privateKey((RSAPrivateKey) keyPair.getPrivate())
    .keyID("test-rsa-2026-a")
    .build();

JWKSource<SecurityContext> jwkSource =
    new ImmutableJWKSet<>(new JWKSet(signingJwk));

JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);
```

Các import và kiểu generic cụ thể cần khớp phiên bản Nimbus/Spring Security của project. Nguyên tắc là private key chỉ dùng để ký fixture; decoder hoặc JWKS server chỉ nhận public key.

Không sinh key pair mới trong từng test nếu mục tiêu là so sánh signature/JWK behavior ổn định. Có thể có fixture riêng cho key rotation, nhưng mỗi key vẫn cần kid cố định và metadata rõ ràng.

## 8. Tạo JWT có claims xác định

Dùng một factory thay vì lặp lại cách dựng token trong từng test:

```java
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer("https://issuer.test/realms/shop")
    .subject("user-1001")
    .audience(List.of("orders-api"))
    .issuedAt(TEST_NOW.minusSeconds(60))
    .expiresAt(TEST_NOW.plusSeconds(300))
    .claim("scope", "orders.read")
    .claim("tenant_id", "tenant-test-a")
    .build();

JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
    .keyId("test-rsa-2026-a")
    .build();

String token = encoder.encode(
    JwtEncoderParameters.from(header, claims)
).getTokenValue();
```

Factory có thể nhận một profile rồi sửa đúng một thuộc tính để tạo negative vector. Ví dụ wrong-audience chỉ thay aud; bad-signature ký cùng claims bằng key không nằm trong JWKS. Nhờ vậy mỗi test chỉ kiểm tra một nguyên nhân từ chối.

Không thay nhiều claim cùng lúc trong một vector negative. Nếu issuer, audience và signature đều sai, test pass không cho biết validator nào thực sự hoạt động.

## 9. Giữ key material test và JWKS ở dạng dễ đọc

Một cấu trúc fixture có thể dùng:

```text
src/test/resources/security-baseline/
  keys/
    rsa-a-private.pem
    rsa-a-public.pem
    rsa-b-private.pem
    rsa-b-public.pem
  jwks/
    jwks-a.json
    jwks-a-and-b.json
    jwks-b-only.json
  tokens/
    vectors.yml
  responses/
    unauthorized.json
    forbidden.json
    invalid-token.headers
```

Private key chỉ xuất hiện trong test resources và không được đóng gói vào production artifact. Nếu tổ chức không cho phép commit private test key, có thể tạo key fixture một lần trong test setup và giữ public JWKS snapshot tương ứng; khi đó cần bảo đảm generation deterministic hoặc snapshot được lưu để so sánh.

Không dùng key production đã export. Không dùng key test làm fallback trong runtime nếu JWK endpoint lỗi.

## 10. JWKS fixture và kid

Một JWKS chứa public keys mà decoder có thể chọn theo kid:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "test-rsa-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "TEST_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
```

Giá trị modulus ở trên chỉ là placeholder minh họa; fixture thực tế phải chứa public JWK được tạo từ key pair test. Không tự thay bằng modulus tùy ý rồi kỳ vọng chữ ký verify được.

kid giúp decoder chọn key phù hợp trong JWKS. Nếu token có kid không tồn tại, decoder có thể refresh JWK Set theo cache policy rồi vẫn từ chối. Test cần xác nhận không có fallback sang key khác chỉ vì một key có thể verify signature.

## 11. Bộ key rotation phải có các giai đoạn

Một key rotation an toàn thường có overlap:

1. **Before rotation:** JWKS chỉ có key A; token A được chấp nhận.
2. **Overlap:** JWKS có key A và B; token A và B đều được chấp nhận.
3. **After retirement:** JWKS chỉ có key B; token B được chấp nhận, token A bị từ chối sau khi decoder refresh theo policy.
4. **Unknown kid:** token ký bằng key C không có trong JWKS bị từ chối.

Fixture nên có ít nhất ba JWKS snapshots:

```text
jwks-a.json          -> key A
jwks-a-and-b.json    -> key A + key B
jwks-b-only.json     -> key B
```

Test phải điều khiển mock JWK endpoint/cache để biết lúc nào refresh xảy ra. Nếu decoder đang cache key A, thay response mock thành key B không có nghĩa request kế tiếp lập tức thấy JWKS mới. Hãy làm rõ cache TTL/refresh behavior thay vì viết test phụ thuộc timing ngẫu nhiên.

## 12. Kiểm tra algorithm allowlist

Baseline nên có token được ký bằng thuật toán được phép và token dùng thuật toán không được phép.

Ví dụ policy chỉ chấp nhận RS256:

```java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwkSetUri)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();
```

Cấu hình thực tế có thể dùng một hoặc nhiều thuật toán được tổ chức cho phép. Test nên xác nhận:
- RS256 hợp lệ được chấp nhận.
- Key/algorithm mismatch bị từ chối.
- Token không chữ ký hoặc alg không được phép bị từ chối.
- Không tự động cho phép thuật toán yếu chỉ để tương thích token cũ.

Không dùng chung một key cho nhiều mục đích hoặc thuật toán nếu security profile yêu cầu tách key.

## 13. Baseline cho issuer và audience

Một JWT có chữ ký hợp lệ vẫn có thể không thuộc issuer hoặc resource hiện tại.

Các vector nên bao gồm:

| Vector | iss | aud | Kết quả |
| --- | --- | --- | --- |
| Valid | Issuer được trust | orders-api | Accept |
| Wrong issuer | issuer khác | orders-api | Reject |
| Wrong audience | Issuer được trust | billing-api | Reject |
| Missing audience | Issuer được trust | Không có | Reject nếu profile yêu cầu |
| Multiple audience | Issuer được trust | orders-api + billing-api | Theo policy đã công bố |

Giữ nguyên issuer string, trailing slash và audience identifiers trong fixtures. Các giá trị gần giống nhau vẫn có thể khác theo exact matching.

Nếu dùng JwtValidators.createDefaultWithIssuer, bổ sung audience validator riêng khi API yêu cầu. Baseline phải kiểm tra decoder thật có validator đó, không chỉ kiểm tra một helper độc lập.

## 14. Baseline cho thời gian và clock skew

Kiểm thử các biên:

- exp nhỏ hơn TEST_NOW quá clock skew: reject.
- exp nằm trong khoảng clock skew: theo policy validator.
- exp đúng tại ranh giới chấp nhận: xác định semantics bằng test.
- nbf lớn hơn TEST_NOW quá clock skew: reject.
- iat nằm trong tương lai ngoài tolerance: theo validator/profile.
- Token còn hạn nhưng tuổi token vượt maximum age: reject nếu policy có quy định.

Ghi rõ clock skew trong baseline, ví dụ 60 giây. Không tăng tolerance chỉ để một fixture cũ pass sau migration; điều đó có thể mở rộng cửa sổ chấp nhận token.

## 15. Baseline cho claim bắt buộc và authority mapping

Tạo vector có:
- sub hợp lệ.
- sub thiếu hoặc rỗng.
- scope hợp lệ.
- scope thiếu.
- scope sai kiểu.
- roles ở claim path đúng.
- roles ở claim path sai.
- Tenant claim hợp lệ/thiếu.
- Claim custom có giá trị ngoài allowlist.

Kiểm tra cả principal attributes và granted authorities. Ví dụ scope orders.read orders.write phải map thành hai authority theo converter đã định nghĩa. Token có scope profile.read không được cấp orders.read.

Nếu service token không có subject người dùng, baseline phải có profile riêng dựa trên client identity. Đừng làm một test factory luôn thêm sub mặc định vì nó sẽ che việc Authorization Server thực tế không trả claim đó.

## 16. Opaque token cũng cần corpus ổn định

Opaque token không có cấu trúc JWT để test bằng cách sửa claims. Dùng token strings giả và mock introspection response:

```text
opaque-valid-orders-reader
opaque-inactive
opaque-valid-without-scope
opaque-active-missing-subject
opaque-client-profile
opaque-invalid-client-fixture
```

Mỗi chuỗi chỉ là fixture identifier/value trong test. Authorization Server thật không được biết hoặc chấp nhận các giá trị này.

Giữ response fixture riêng để test thay đổi metadata độc lập với token value. Một token có thể được mock active ở test này và inactive ở test khác, nhưng không dùng chung test name khiến người đọc nghĩ đó là trạng thái cố định ngoài fixture.

## 17. Bộ introspection response cho opaque token

Response active đủ quyền:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-1001",
  "aud": ["orders-api"],
  "iss": "https://issuer.test/realms/shop"
}
```

Response inactive:

```json
{
  "active": false
}
```

Response active nhưng thiếu scope:

```json
{
  "active": true,
  "sub": "user-1001",
  "aud": ["orders-api"]
}
```

Response malformed hoặc thiếu active phải có fixture riêng. Test nên phân biệt confirmed inactive với response contract violation nếu custom adapter cần phân loại hai trường hợp đó.

## 18. Introspection client error là một vector khác

Resource Server gửi client credentials riêng để gọi introspection endpoint. Baseline cần bao gồm:

- HTTP 401 với invalid_client.
- HTTP 403 khi client không được phép introspect.
- HTTP 429 rate limit.
- HTTP 5xx.
- Connect/read timeout.
- TLS/DNS failure nếu test harness có thể mô phỏng.
- HTTP 200 với malformed JSON hoặc thiếu active.

Các ca này không được ghi thành active=false. Chúng chứng minh Resource Server không thể xác minh token vì dependency/configuration error.

Khi test endpoint giả lập, kiểm tra client authentication method, POST method, form field token, timeout và response parsing. Không đưa secret production vào fixture hoặc test output.

## 19. Lưu expected error response như API contract

Baseline không nên chỉ ghi “trả 401”. Với mỗi trường hợp từ chối, xác định các phần response ổn định:

- HTTP status.
- WWW-Authenticate challenge.
- Content-Type.
- Error code/body theo API contract.
- Các headers bảo mật cần có.
- Business side effect có xảy ra hay không.

Ví dụ Bearer token invalid có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

Token hợp lệ nhưng thiếu scope có thể trả 403 và challenge insufficient_scope nếu Bearer access denied handler được cấu hình như vậy. Response thực tế phụ thuộc Spring Security handler và API customization. Hãy chụp behavior hiện hành đã được chấp thuận làm baseline thay vì giả định mọi ứng dụng phải có cùng body/header.

## 20. Phân biệt missing token, invalid token và insufficient scope

Ba ca này thường có semantics khác:

| Trường hợp | Authentication | HTTP thường gặp | Bearer challenge |
| --- | --- | --- | --- |
| Không có token | Chưa authenticated | 401 | Bearer |
| Token invalid/expired | Authentication rejected | 401 | Bearer error=invalid_token |
| Token hợp lệ, thiếu scope | Authenticated | 403 | Có thể insufficient_scope |
| Token hợp lệ, ownership denied | Authenticated | 403 hoặc 404 | Theo API contract |

Đừng dùng một expected response cho tất cả các ca. Nếu application có custom ProblemDetail body, giữ status và body contract nhất quán, nhưng tránh để lộ token, subject hoặc lý do nhạy cảm.

## 21. Chuẩn hóa response trước khi so sánh

Một số response fields thay đổi theo lần chạy:
- Date header.
- Trace ID/request ID.
- Server timing.
- Nonce hoặc correlation ID.
- JSON field order.
- Whitespace.
- Header order/casing.

Không so sánh byte-for-byte toàn bộ HTTP response nếu có các trường động. Hãy chuẩn hóa:
1. Giữ status code.
2. Lấy các headers được contract quản lý, so sánh theo semantics không phân biệt casing.
3. Parse JSON body rồi so sánh object hoặc các field ổn định.
4. Bỏ dynamic fields đã được xác định trước.
5. Không bỏ WWW-Authenticate, error code hoặc security headers chỉ để test pass.

Không normalize quá rộng. Nếu bỏ hết headers, baseline sẽ không phát hiện việc Bearer challenge bị mất.

## 22. Golden files và test vector manifest

Một manifest đơn giản có thể mô tả corpus:

```yaml
vectors:
  - id: jwt.valid.orders-reader
    token: jwt-valid-orders-reader
    expectedAuthentication: success
    expectedStatus: 200

  - id: jwt.expired.orders-reader
    token: jwt-expired-orders-reader
    expectedAuthentication: rejected
    expectedStatus: 401
    expectedChallenge: invalid_token

  - id: jwt.scope.missing-write
    token: jwt-valid-orders-reader
    expectedAuthentication: success
    expectedAuthorization: denied
    expectedStatus: 403

  - id: opaque.inactive
    token: opaque-inactive
    introspectionFixture: inactive.json
    expectedAuthentication: rejected
    expectedStatus: 401
```

Đây là format minh họa; project có thể dùng JSON/YAML hoặc Java test factory. Manifest không nên chứa raw production token, secret hoặc private key. Nếu token được tạo động, manifest lưu profile/claims và key fixture ID thay vì lưu bearer value.

Golden files phù hợp với response contract ổn định. Với headers có dynamic values, dùng assertion có chọn lọc thay vì snapshot toàn bộ.

## 23. Chạy baseline trên cấu hình cũ và mới

Khi migrate, có thể giữ hai test contexts hoặc hai test applications:

- Legacy configuration chạy với dependency version cũ trong một module/branch hoặc test fixture cô lập.
- Candidate configuration chạy với version mới.
- Cả hai dùng chung token corpus, key/JWKS fixtures, clock và HTTP response assertions.
- Kết quả được xuất thành report có vector ID, old outcome và new outcome.

Không cố nạp hai phiên bản Spring Security khác nhau vào cùng một classloader. Nếu dependency incompatibility khiến không thể chạy hai context cùng process, chạy hai build/test jobs riêng rồi so sánh artifact kết quả.

## 24. Bảng so sánh behavior

Một report có thể có dạng:

| Vector | Baseline cũ | Candidate mới | Kết luận |
| --- | --- | --- | --- |
| jwt.valid.orders-reader | 200 | 200 | Giữ nguyên |
| jwt.expired.orders-reader | 401 invalid_token | 401 invalid_token | Giữ nguyên |
| jwt.audience.billing-only | 401 invalid_token | 200 | Regression nghiêm trọng |
| jwt.scope.missing-write | 403 insufficient_scope | 403 insufficient_scope | Giữ nguyên |
| opaque.inactive | 401 invalid_token | 401 invalid_token | Giữ nguyên |
| opaque.invalid-client | Dependency error | 401 generic | Cần kiểm tra error telemetry/mapping |

Mỗi khác biệt cần có disposition:
- Expected change: policy/API contract đã được phê duyệt.
- Regression: behavior thay đổi ngoài dự kiến.
- Environment variance: khác biệt do test environment hoặc dependency fixture.
- Unclassified: chưa đủ evidence; không tự đánh dấu pass.

Một HTTP status giống nhau không chứng minh behavior giống nhau. Ví dụ hai lần trả 401 nhưng một lần là token expired và lần kia là introspection client misconfiguration. Cần so sánh cả internal outcome category.

## 25. Ca từ chối phải xác nhận business code không chạy

Một test chỉ assert 401/403 có thể chưa đủ. Hãy kiểm tra service, repository write, event publisher hoặc downstream client không được gọi.

Ví dụ:

```java
@Test
void expiredTokenDoesNotReachOrderService() throws Exception {
    String expiredToken = tokenFactory.expiredOrdersReader();

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + expiredToken))
        .andExpect(status().isUnauthorized());

    verify(orderService, never()).listOrders();
}
```

Đối với authorization denial:

```java
@Test
void readOnlyTokenCannotCreateOrder() throws Exception {
    String readOnlyToken = tokenFactory.validOrdersReader();

    mvc.perform(post("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + readOnlyToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"sku\":\"TEST-1\"}"))
        .andExpect(status().isForbidden());

    verify(orderService, never()).createOrder(any());
}
```

Ví dụ cần service bean/spy và test application context thực tế. Nếu method security nằm ở service, test phải gọi qua Spring proxy. Đừng mock toàn bộ secured service rồi kết luận annotation của implementation đã được thực thi.

## 26. Negative tests cho JWT

Bộ test JWT tối thiểu nên bao gồm:

1. Token hợp lệ được chấp nhận.
2. Token hết hạn bị từ chối.
3. Token chưa đến nbf bị từ chối.
4. Signature bị thay đổi bị từ chối.
5. Token ký bằng key không tin cậy bị từ chối.
6. Issuer sai bị từ chối.
7. Audience sai/thiếu bị từ chối theo profile.
8. Algorithm không được phép bị từ chối.
9. Required subject/claim thiếu bị từ chối theo policy.
10. Scope thiếu không vượt qua authorization rule.
11. Key rotation overlap hoạt động.
12. Key đã retire không còn được chấp nhận sau refresh theo cache contract.

Mỗi test nên nêu rõ failure point: decoder, validator, authority converter hay AuthorizationManager. Điều này giúp xác định chính xác lớp bị regression.

## 27. Negative tests cho opaque token

Bộ test opaque tối thiểu:

1. Introspection active=true với metadata hợp lệ.
2. Introspection active=false.
3. Response thiếu active.
4. active sai kiểu.
5. Response active nhưng thiếu subject bắt buộc.
6. Response active nhưng thiếu scope.
7. Response active nhưng audience không đúng.
8. Introspection client invalid_client.
9. Client không có quyền introspect.
10. Timeout, DNS/TLS hoặc upstream 5xx.
11. Malformed response body.
12. Token cache hit sau khi trạng thái thay đổi theo freshness policy.

Dùng mock introspection endpoint thật ở mức HTTP cho các test request/credential/response parsing. Post-processor opaqueToken() chỉ tạo Authentication giả lập và không kiểm tra introspection endpoint.

## 28. Giữ nguyên 401/403 và Bearer challenge

Các assertion response nên kiểm tra:

```java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + invalidToken))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("Bearer")));
```

Với insufficient scope, nếu contract hiện hành dùng Bearer challenge:

```java
mvc.perform(post("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + readOnlyToken))
    .andExpect(status().isForbidden())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("insufficient_scope")));
```

Challenge có thể khác nếu application thay handler. Đừng hard-code toàn bộ string nếu thứ tự tham số không có ý nghĩa; kiểm tra scheme và các parameters quan trọng. Nếu API không phát challenge cho 403 theo contract, baseline phải phản ánh behavior đã được quyết định.

## 29. Kiểm tra ProblemDetail hoặc error body tùy chỉnh

Nếu API trả body JSON cho lỗi:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "AUTHENTICATION_REQUIRED"
}
```

hoặc:

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "code": "INSUFFICIENT_PERMISSION"
}
```

Hãy cố định field contract cần thiết: status, code, title/type và message public. Không đưa stack trace, introspection response, token value hoặc client secret vào body.

Nếu response body không phải một phần public API contract, đừng tạo snapshot quá chặt khiến thay đổi wording vô hại gây regression noise. Giữ các assertion có ý nghĩa với client.

## 30. Test WWW-Authenticate cho từng tình huống

Bearer challenge là một phần quan trọng của API behavior:

- Missing credentials: challenge Bearer không nhất thiết có error parameter.
- Invalid/expired token: challenge thường có error=invalid_token.
- Insufficient scope: access denied handler có thể trả error=insufficient_scope và scope cần thiết.
- Custom error handler: challenge phải được bảo toàn nếu API contract yêu cầu.

Test challenge qua HTTP response thật, không chỉ unit test một helper. Một migration có thể thay exception handler và vô tình bỏ header dù status vẫn 401.

Không đưa chi tiết nội bộ như invalid_client của introspection client vào challenge gửi cho caller. Đây là lỗi giữa Resource Server và Authorization Server.

## 31. Kiểm thử bằng WithMockUser không thay thế token baseline

WithMockUser thiết lập Authentication giả lập trong SecurityContext. Nó hữu ích cho method security và controller policy test, nhưng bỏ qua:
- Bearer token extraction.
- JWT signature verification.
- Issuer/audience/timestamp validation.
- JWK retrieval/rotation.
- Opaque token introspection.
- Authority conversion từ token claims.

Vì vậy, giữ hai lớp test:
1. Policy test dùng mock Authentication để kiểm tra rule method/domain.
2. Resource Server integration test dùng Bearer token fixture thật qua filter chain.

Không dùng WithMockUser để chứng minh token validation vẫn đúng sau dependency upgrade.

## 32. Phân biệt decoder test, filter-chain test và end-to-end test

| Loại test | Điều được kiểm tra | Fixture phù hợp |
| --- | --- | --- |
| Decoder unit/integration | Signature, issuer, audience, timestamp, algorithm | JWT ký bằng test key và fixed clock |
| Filter-chain test | Bearer extraction, Authentication entry point, status/challenge | MockMvc + real decoder/JWK fixture |
| Opaque introspection test | HTTP call, client auth, active/metadata parsing | Mock introspection server |
| Authorization test | Scope, role, tenant, ownership | Authentication fixture + domain fixtures |
| End-to-end test | IdP/resource integration và API contract | Test IdP hoặc environment test cô lập |

Một test nhỏ, tập trung thường dễ xác định regression hơn một E2E test lớn. Tuy nhiên, ít nhất một test integration phải đi qua đúng filter chain và decoder/introspector được production dùng.

## 33. Giữ test fixture tương thích qua dependency upgrade

Khi Spring Security hoặc Nimbus đổi version, API builder có thể thay đổi. Tách fixture generation khỏi test assertions:

- Một TokenFixtureFactory tạo JWT.
- Một TestKeySet cung cấp private/public keys và JWKS.
- Một TestClock cố định thời gian.
- Một IntrospectionStub quản lý response fixtures.
- Một SecurityResponseAssertions chuẩn hóa HTTP response.
- Một BaselineVector mô tả expected result.

Nếu API library thay đổi, sửa adapter/factory ở một nơi. Không sửa expected result hàng loạt chỉ để làm test pass; cần xác minh thay đổi behavior có đúng chủ đích không.

## 34. Quản lý baseline khi policy thay đổi có chủ đích

Không phải mọi khác biệt đều là regression. Ví dụ tổ chức có thể:
- Bắt buộc audience mà trước đây chưa kiểm tra.
- Loại bỏ một thuật toán ký cũ.
- Thu hồi key đã hết vòng đời.
- Bỏ scope legacy.
- Chuẩn hóa error body hoặc chuyển từ 404 sang 403 theo API contract.

Khi đó, cập nhật baseline theo quy trình có review:
1. Nêu lý do và threat/compatibility impact.
2. Xác định vector nào thay đổi.
3. Cập nhật expected result cho đúng vector.
4. Giữ nguyên các vector không liên quan.
5. Ghi ngày/policy version hoặc migration reference.
6. Chạy toàn bộ corpus trước khi merge.

Không sửa baseline snapshot cùng lúc với code mà không giải thích. Nếu làm vậy, snapshot chỉ ghi nhận behavior mới chứ không còn giúp đánh giá thay đổi.

## 35. Bảo vệ private test key và fixture repository

Private key test không phải production secret, nhưng vẫn cần quản lý để tránh nhầm lẫn:

- Dùng key có tên và path chỉ rõ test.
- Không copy key production vào test resources.
- Không đóng gói test private key vào production artifact.
- Có thể dùng CI-generated ephemeral key nếu không cần snapshot cố định.
- Nếu key cố định để regression signature/JWKS, chỉ dùng cho test và không được trust ở production.
- Không log PEM hoặc bearer token trong test failure message.
- Public JWKS fixture có thể được chia sẻ; private key chỉ nằm trong test scope.

Một test key cố định giúp kết quả deterministic; key ephemeral giúp tránh lưu private material. Chọn cách phù hợp với nhu cầu tái lập và policy repository, nhưng không dùng production key.

## 36. Đừng so sánh toàn bộ token string khi mục tiêu là behavior

JWT string thay đổi nếu:
- iat/exp thay đổi.
- JSON claim ordering khác.
- Header serialization khác.
- Signing key/kid khác.
- Library cập nhật cách serialize.

Nếu đang test signature output hoặc token issuance, có thể có assertion riêng cho serialization contract đã định nghĩa. Nhưng regression baseline Resource Server chủ yếu nên so sánh:
- Token có được chấp nhận không.
- Principal/authorities được tạo thế nào.
- Request được phép hay từ chối.
- HTTP response/challenge có đúng không.
- Business side effects có bị chặn không.

Không biến một thay đổi JSON ordering vô hại thành security regression; đồng thời không bỏ qua claim/authority differences thực sự.

## 37. Kiểm tra cache và key rotation trong baseline

Key cache và opaque introspection cache có thể khiến kết quả phụ thuộc thứ tự test. Để baseline tái lập:

- Tạo cache instance mới cho mỗi test group hoặc reset state rõ ràng.
- Điều khiển clock/TTL khi có thể.
- Mock JWK endpoint để trả snapshots theo thứ tự xác định.
- Xác nhận decoder refresh khi gặp kid chưa biết theo behavior version hiện tại.
- Test token cũ trong overlap và sau khi key retire.
- Với opaque cache, kiểm tra positive TTL không vượt expiry/revocation policy.
- Không để test trước làm warm cache cho test sau một cách ngầm định.

Nếu framework không cung cấp API reset cache, tạo decoder/introspector mới theo test context hoặc dùng endpoint fixture riêng cho từng test.

## 38. Baseline cho error mapping khi dependency unavailable

Introspection client error, JWK timeout hoặc TLS failure có thể đi qua authentication failure handling mặc định. HTTP response cuối cùng phụ thuộc framework và custom handler.

Baseline nên lưu hai kết quả:
- **Internal failure category:** invalid client, timeout, malformed response, JWK unavailable.
- **Public API response:** status/body/challenge theo error contract đã chọn.

Không yêu cầu mọi lỗi upstream phải trả cùng một status nếu API có custom availability policy. Nhưng tuyệt đối không tạo Authentication hoặc cho business request đi tiếp khi token chưa được xác minh.

Nếu API muốn trả 503 khi IdP unavailable, test phải chứng minh mapping đó hoạt động và không biến token invalid thông thường thành 503.

## 39. Chạy corpus trên CI

Một pipeline có thể tổ chức:

1. Compile test fixtures và key resources.
2. Chạy decoder/token validation tests.
3. Chạy filter-chain HTTP tests.
4. Chạy opaque introspection HTTP tests.
5. Chạy authorization denial tests.
6. Xuất report theo vector ID.
7. So sánh với approved baseline artifact nếu pipeline hỗ trợ.
8. Fail build khi có unexpected acceptance, rejection hoặc response contract change.

Ưu tiên fail ngay nếu token invalid được chấp nhận. Những thay đổi về wording hoặc dynamic headers có thể được normalize theo policy, nhưng không normalize các security-relevant fields.

Không phụ thuộc Authorization Server production trong CI. Dùng test key, mock endpoint hoặc test IdP có vòng đời được kiểm soát.

## 40. Ma trận baseline trước/sau migration

Một bảng mẫu để review:

| Area | Baseline cũ | Candidate mới | Điều cần giữ |
| --- | --- | --- | --- |
| Valid JWT | Accepted | Accepted | Principal và authorities đúng |
| Expired JWT | 401 | 401 | Không có business execution |
| Wrong issuer/audience | 401 | 401 | Không nới trust boundary |
| Bad signature | 401 | 401 | Không có fallback key |
| Key overlap | A và B accepted | A và B accepted | Rotation window |
| Retired key | Rejected sau refresh | Rejected sau refresh | Retirement semantics |
| Opaque inactive | 401 | 401 | Không tạo principal |
| Introspection invalid client | Dependency error category | Dependency error category | Không gắn nhầm inactive |
| Missing scope | 403 | 403 | Authentication vẫn thành công |
| Ownership denied | 403/404 theo contract | Giữ contract | Không có side effect |
| Error challenge | Bearer challenge | Bearer challenge | Client compatibility |
| Custom body | Problem code ổn định | Problem code ổn định | Không lộ nội bộ |

Baseline không yêu cầu candidate có mọi implementation detail giống hệt. Nó yêu cầu các security/API guarantees đã công bố được giữ hoặc thay đổi có chủ đích.

## 41. Các anti-pattern khi duy trì baseline

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng token production | Credential/PII leak, test không tái lập | Test-only token corpus |
| Dùng private key production | Rủi ro lộ signing authority | Test key riêng |
| Sinh token theo clock hệ thống | CI flaky | Fixed clock |
| Chỉ test happy path | Bỏ sót fail-open regression | Corpus negative đầy đủ |
| Một token có nhiều lỗi | Không biết validator nào hoạt động | Mỗi vector kiểm tra một điều kiện chính |
| Chỉ assert status | Mất challenge/body semantics | Assert headers và stable body fields |
| So sánh byte response toàn bộ | False positive do dynamic fields | Normalize có chọn lọc |
| Dùng jwt() làm decoder test | Bỏ qua signature/JWK | Bearer token qua real decoder |
| Dùng opaqueToken() làm introspection test | Bỏ qua HTTP introspection | Mock endpoint + Bearer header |
| Cập nhật snapshot cùng code vô điều kiện | Che regression | Review mọi expected change |
| Không reset cache | Test phụ thuộc thứ tự | Isolated cache/decoder |
| Bỏ side-effect assertion | Request bị deny nhưng write vẫn chạy | Verify service/repository/event không chạy |

## 42. Checklist review một baseline mới

Trước khi dùng corpus làm mốc cho migration, xác nhận:

- Mọi vector có ID ổn định và mục đích rõ.
- JWT chỉ được ký bằng test key.
- Public JWKS và private test key tương ứng được quản lý đúng.
- kid, issuer, audience, algorithm và clock được cố định.
- Có vector exp, nbf, signature, issuer, audience và scope.
- Có vector key overlap, unknown kid và retired key.
- Opaque response bao gồm active true/false, missing/malformed metadata.
- Có introspection invalid_client, timeout và upstream error.
- 401/403, WWW-Authenticate và error body được ghi theo contract.
- Ca từ chối xác nhận business operation không chạy.
- Dynamic headers/fields được normalize có chủ đích.
- Metric/log/test output không chứa raw token hoặc secret.
- Mọi thay đổi expected result có lý do và reviewer.
- CI chạy cùng corpus trên candidate dependency/configuration.

## 43. Tài liệu tham khảo

- [Spring Security 6.5 — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT decoder, validators và JWK Set.
- [Spring Security 6.5 — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection và custom OpaqueTokenIntrospector.
- [Spring Security 6.5 — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): test support cho authentication và HTTP security.
- [Spring Security 6.5 — MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html): kiểm thử filter chain với MockMvc.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html): JWK/JWKS và key identifiers.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): registered claims và NumericDate.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer challenge và invalid_token/insufficient_scope.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): introspection response và active metadata.

## 44. Kết luận

Một baseline migration đáng tin cần giữ cùng một bộ token, key/JWKS, expected error responses và negative test cases qua các lần thay đổi Spring Security, Spring Boot hoặc OAuth/OIDC configuration. JWT fixtures cần signature thật với test-only key, kid ổn định và fixed clock. Opaque token fixtures cần response introspection riêng cho active/inactive, thiếu metadata và lỗi client/dependency.

So sánh cả authentication outcome, authorization decision, HTTP status, Bearer challenge, response body ổn định và side effects. Token invalid phải bị từ chối; token hợp lệ nhưng thiếu scope/ownership phải bị deny; lỗi JWK/introspection phải được nhận diện là lỗi xác minh, không được biến thành principal hợp lệ. Khi policy thay đổi có chủ đích, cập nhật đúng vector và ghi rõ lý do.

**Điểm cốt lõi:** *Dùng lại cùng một corpus có thể tái lập để chứng minh migration giữ nguyên các ranh giới bảo mật và API contract; mọi thay đổi trong ca từ chối đều cần được giải thích trước khi chấp nhận.*
