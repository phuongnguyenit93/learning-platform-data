# Bộ token mẫu đã được kiểm soát để kiểm tra tương thích khi nhà phát hành thay đổi

## 1. Vì sao Resource Server cần một bộ token mẫu được kiểm soát?

Một **Spring Security OAuth 2.0 / OIDC Resource Server** phụ thuộc vào hợp đồng mà Authorization Server (AS) hoặc OpenID Provider (OP) phát hành: issuer, audience, chữ ký, thuật toán, key ID, thời hạn, token type, scopes, roles và các claims mở rộng.

Khi nhà phát hành thay đổi cấu hình hoặc nâng cấp sản phẩm, access token có thể thay đổi theo nhiều cách:

- Khóa ký được rotate, `kid` mới xuất hiện trong JWKS.
- Issuer URL được di chuyển sang realm/domain mới.
- Audience được thêm, bỏ hoặc đổi tên.
- Claim `scope` đổi từ chuỗi phân tách bằng dấu cách sang schema khác.
- Claim `roles`/`groups` được đổi tên hoặc thay kiểu dữ liệu.
- Token profile thay đổi, ví dụ `typ`, `client_id`, `sub` hoặc claim bắt buộc.
- Introspection response đổi cấu trúc hoặc cách biểu diễn `active`.
- OIDC discovery metadata thay đổi `jwks_uri` hoặc các endpoint liên quan.

Nếu chỉ kiểm tra một token thật đang hoạt động, hệ thống có thể bỏ sót các thay đổi phá vỡ tương thích. Một bộ **controlled token fixtures** cung cấp các mẫu credential và phản hồi nhà phát hành có nguồn gốc rõ, có thể tái tạo, có expected result cụ thể và được chạy lặp lại trong CI.

Bộ fixtures giúp trả lời:

1. Token đúng theo hợp đồng hiện tại còn được chấp nhận không?
2. Token sai issuer, audience, signature hoặc thời hạn có bị từ chối không?
3. Token từ key mới có được xác minh sau rotation không?
4. Token cũ còn hợp lệ trong giai đoạn overlap có được xử lý đúng không?
5. Thay đổi claim/scope của nhà phát hành có làm đổi authorities hoặc quyền endpoint không?
6. Khi introspection/JWKS service lỗi, Resource Server có fail closed và phân loại đúng lỗi không?
7. Issuer mới có được thêm có kiểm soát, còn issuer ngoài allowlist vẫn bị từ chối không?

**Token mẫu có kiểm soát là dữ liệu kiểm thử**, không phải credential production. Nên dùng khóa test riêng, token tổng hợp và sandbox issuer. Không sao chép access token/refresh token đang dùng của người dùng thật vào repository, CI logs hoặc tài liệu.

### 1.1. Phân biệt các loại fixtures

| Loại dữ liệu | Mục đích | Có nên lưu trong Git? |
|---|---|---|
| JWT tổng hợp ký bằng private key test | Test signature, claims, issuer, audience, expiry và authority mapping | Có thể, nếu key chỉ dùng cho test; tốt hơn tạo token lúc chạy |
| Public JWKS test | Cho decoder kiểm tra chữ ký test | Có thể, vì chỉ chứa public keys |
| Opaque token giả lập | Test resolver/introspector và authorization | Có thể dùng chuỗi giả, không phải token live |
| Introspection JSON fixture | Test `active`, scope, audience và claim mapping | Có thể nếu đã loại bỏ dữ liệu nhạy cảm |
| OIDC discovery metadata fixture | Test issuer/JWKS URI và metadata contract | Có thể nếu là snapshot sandbox đã kiểm soát |
| Token lấy từ production | Debug hoặc kiểm thử tương thích | Không commit, không đưa vào logs/fixtures |
| Refresh token hoặc client secret | Credential để cấp token hoặc gọi AS | Không commit, không dùng làm fixture |
| Private signing key production | Ký token thật | Tuyệt đối không đưa vào test resources |

Một file JSON chỉ có payload claims **không phải JWT signature test**. Nếu mục tiêu là kiểm tra `JwtDecoder`, cần compact JWT được ký bằng private key test, cùng public key/JWKS mà decoder tin cậy.

Ngược lại, nếu chỉ kiểm tra business mapping từ claims sang authorities, có thể dùng mock `Jwt` hoặc `Authentication`. Nhưng mock authentication không chứng minh chữ ký, issuer hoặc audience validation đã hoạt động.

### 1.2. Fixture phải có provenance

Mỗi fixture nên ghi nhận:

- Fixture ID và phiên bản bộ mẫu.
- Issuer alias và issuer URL kỳ vọng.
- Token profile/version.
- Audience và client/resource identifier.
- Thuật toán ký và `kid`.
- Claims quan trọng và kiểu dữ liệu.
- Thời điểm phát hành/expiry theo test clock.
- Expected outcome: accept, reject authentication hoặc authenticated-but-forbidden.
- Lý do fixture tồn tại: baseline, issuer drift, key rotation, wrong audience, scope regression.
- Nguồn: generated test key, sandbox contract snapshot hoặc provider-published example.

Provenance giúp phân biệt “token này sai có chủ đích” với “fixture bị hỏng ngoài ý muốn”.

## 2. Xây dựng ma trận token mẫu theo hợp đồng issuer

Giả sử Orders API chấp nhận access token theo profile:

~~~text
issuer    = https://id.example.test/realms/orders
audience  = orders-api
algorithm = RS256
type      = at+jwt
scope     = space-delimited OAuth scopes
~~~

Claims nền tảng có thể gồm:

~~~json
{
  "iss": "https://id.example.test/realms/orders",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 2000000000,
  "exp": 2000000300,
  "jti": "fixture-jti-001",
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
~~~

Đây là payload minh họa. Các trường bắt buộc phụ thuộc access token profile và hợp đồng issuer. Ví dụ RFC 9068 định nghĩa JWT Profile cho OAuth 2.0 Access Tokens, trong đó có yêu cầu cụ thể hơn về claims và header type. Không áp dụng profile RFC 9068 cho mọi JWT nếu AS chưa cam kết phát hành theo profile đó.

### 2.1. Bộ JWT fixtures cơ bản

| Fixture ID | Thay đổi so với baseline | Expected result |
|---|---|---|
| `valid-orders-read` | Issuer, audience, signature, time hợp lệ; có `orders.read` | Authentication accepted; GET read được phép |
| `valid-orders-write` | Có `orders.write` | Authentication accepted; write policy có thể cho phép |
| `wrong-issuer` | `iss` khác trusted issuer | Reject authentication |
| `wrong-audience` | `aud` chỉ có `billing-api` | Reject authentication |
| `expired-token` | `exp` nằm trong quá khứ theo test clock | Reject authentication |
| `not-yet-valid` | `nbf` nằm trong tương lai ngoài clock skew | Reject authentication |
| `bad-signature` | Ký bằng private key không được trust | Reject authentication |
| `unknown-kid` | Header `kid` không tồn tại trong trusted JWKS | Reject authentication |
| `unsupported-alg` | Thuật toán ngoài allowlist | Reject authentication |
| `missing-sub` | Thiếu claim mà profile yêu cầu | Reject nếu contract yêu cầu |
| `missing-scope` | Token valid nhưng không có scope cần thiết | Authentication accepted; endpoint trả 403 |
| `scope-type-drift` | Scope đổi kiểu từ string sang array/object | Contract test phải phát hiện drift |
| `role-claim-renamed` | `roles` đổi thành `groups` | Không tự cấp quyền ngoài dự kiến |
| `wrong-tenant` | Token có tenant khác resource path | Authentication có thể thành công; domain authorization deny |
| `old-key-during-overlap` | Token ký bằng key cũ còn được publish | Accept trong giai đoạn overlap nếu policy cho phép |
| `new-key-after-rotation` | Token ký bằng key mới | Accept sau khi JWKS được cập nhật |
| `id-token-as-access-token` | Token profile/audience dành cho OIDC client | Reject nếu không đúng access token contract |

Một fixture có thể có authentication accepted nhưng authorization denied. **Không gộp expected result của hai tầng này** thành một boolean duy nhất.

### 2.2. Expected result phải nói rõ tầng kiểm tra

~~~text
Authentication:
    Is the credential trusted and valid?

Authorization:
    Is this authenticated principal allowed to perform this action
    on this resource and tenant?
~~~

Ví dụ:

~~~text
Fixture: valid-token-without-orders-write
Decoder result: ACCEPT
Authentication result: AUTHENTICATED
POST /api/orders result: 403
GET /api/orders result: theo scope còn lại
~~~

Nếu test chỉ assert “request trả 403”, có thể decoder đã từ chối token và security handler trả 403 sai ngữ nghĩa; cần assert status, challenge và tầng xử lý.

## 3. Định nghĩa fixture manifest có phiên bản

Một manifest mô tả bộ fixtures giúp CI biết fixture thuộc issuer/profile nào và expected behavior là gì.

Ví dụ manifest **minh họa**:

~~~yaml
fixtureSet:
  id: orders-resource-server
  version: 3
  generatedFor: contract-test
  issuerAlias: orders-sandbox
  issuer: https://id.example.test/realms/orders
  audience:
    - orders-api
  tokenProfile: rfc9068
  signing:
    algorithm: RS256
    keyId: fixture-rsa-2026-01

fixtures:
  - id: valid-read
    scenario: valid-access-token
    expectedAuthentication: ACCEPT
    expectedAuthorities:
      - SCOPE_orders.read

  - id: wrong-audience
    scenario: wrong-audience
    expectedAuthentication: REJECT
    reason: TOKEN_NOT_INTENDED_FOR_RESOURCE

  - id: expired
    scenario: expired
    expectedAuthentication: REJECT
    reason: TOKEN_EXPIRED

  - id: read-only
    scenario: valid-read-only
    expectedAuthentication: ACCEPT
    expectedAuthorities:
      - SCOPE_orders.read
    expectedAuthorization:
      post-api-orders: DENY
~~~

Đây là **schema do dự án tự định nghĩa**, không phải Spring Boot property hay một chuẩn manifest OAuth. Có thể thay scenario bằng tên test factory để token được tạo lúc chạy, tránh lưu compact JWT tĩnh.

Manifest nên được review cùng validators và authorization rules. Khi issuer thay đổi, tăng fixture-set version hoặc tạo profile version mới thay vì âm thầm sửa baseline làm mất khả năng tái hiện lỗi cũ.

### 3.1. Các version không nên bị nhập làm một

- **Fixture-set version:** phiên bản bộ test scenarios.
- **Token profile version:** hợp đồng định dạng/claims của access token.
- **Issuer configuration version:** snapshot trusted issuer, audience, JWKS URI, algorithms và mapping.
- **Application version:** phiên bản Resource Server đang kiểm tra.

Khi test fail, cần biết lỗi do fixture thay đổi, issuer contract thay đổi hay application regression.

### 3.2. Dùng dữ liệu tổng hợp

Một fixture manifest có thể chứa subject `fixture-user-01`, tenant `tenant-test-a` và client `orders-test-client`. Không dùng email, phone, customer ID, order ID hoặc personal claims lấy từ production nếu không có cơ chế bảo vệ và mục đích được phê duyệt.

## 4. Tạo JWT test có chữ ký thật bằng khóa riêng cho test

Để kiểm tra Resource Server decoder, token cần được ký bằng test key. Public key tương ứng được cung cấp cho decoder/JWKS test server. Private key chỉ phục vụ tạo fixtures trong test environment.

### 4.1. Nguyên tắc quản lý test signing keys

- Dùng khóa RSA/EC riêng biệt cho test; không tái sử dụng production key.
- Đặt `kid` rõ ràng, ví dụ `fixture-rsa-2026-01`.
- Không publish private key trong JWKS endpoint.
- Có thể tạo key pair lúc chạy test để tránh lưu private key lâu dài.
- Nếu dùng key fixture cố định, giới hạn quyền đọc và không dùng nó ngoài test.
- Không dùng secret ngắn/đoán được cho HMAC để ký token.
- Chỉ tin public JWKS test endpoint trong test decoder.
- Tách test keys theo issuer để không vô tình xác thực token của issuer khác.

### 4.2. Factory tạo test key và JwtEncoder

Ví dụ với Spring Security JOSE/Nimbus:

~~~java
package com.example.orders.testsecurity;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

public final class TestSigningKeys {

    private TestSigningKeys() {}

    public static RSAKey newRsaKey(String keyId) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair pair = generator.generateKeyPair();

        return new RSAKey.Builder(
                (RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID(keyId)
            .build();
    }

    public static JwtEncoder encoder(RSAKey signingKey) {
        JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(signingKey));

        return new NimbusJwtEncoder(source);
    }
}
~~~

Các Nimbus JOSE types được Spring Security OAuth2 JOSE sử dụng. Nếu project không có classes này trên test classpath, kiểm tra dependency management của Spring Boot Resource Server starter và thêm dependency JOSE tương thích theo version, không kéo một Nimbus version tùy ý.

### 4.3. Sinh token với claims có kiểm soát

~~~java
package com.example.orders.testsecurity;

import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.RSAKey;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;

public final class AccessTokenFixtures {

    public static final String ISSUER =
        "https://id.example.test/realms/orders";

    public static final String AUDIENCE = "orders-api";

    private final JwtEncoder encoder;
    private final String keyId;

    public AccessTokenFixtures(RSAKey signingKey) {
        this.encoder = TestSigningKeys.encoder(signingKey);
        this.keyId = signingKey.getKeyID();
    }

    public String validReadToken(Instant now) {
        return token(
            now,
            ISSUER,
            List.of(AUDIENCE),
            now.plusSeconds(300),
            "orders.read",
            "tenant-test-a"
        );
    }

    public String token(
            Instant issuedAt,
            String issuer,
            List<String> audience,
            Instant expiresAt,
            String scope,
            String tenant) {

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("fixture-user-01")
            .audience(audience)
            .issuedAt(issuedAt)
            .expiresAt(expiresAt)
            .claim("jti", "fixture-jti-001")
            .claim("client_id", "orders-test-client")
            .claim("scope", scope)
            .claim("tenant_id", tenant)
            .build();

        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
            .keyId(keyId)
            .type("at+jwt")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims)
        ).getTokenValue();
    }
}
~~~

Ví dụ giả định issuer contract sử dụng `typ=at+jwt` theo JWT Access Token Profile. Nếu issuer thực tế dùng type khác hoặc không phát `typ`, fixture cần phản ánh **profile đã thỏa thuận**, không ép mọi nhà phát hành phải giống ví dụ.

Các giá trị `iat`/`exp` được truyền vào factory để test có thể dùng một `Clock` cố định. Không dựa vào thời gian ngẫu nhiên hoặc chờ token hết hạn thật trong test.

### 4.4. Tạo fixture sai có chủ đích

~~~java
String wrongAudience = fixtures.token(
    fixedNow,
    AccessTokenFixtures.ISSUER,
    List.of("billing-api"),
    fixedNow.plusSeconds(300),
    "orders.read",
    "tenant-test-a"
);

String wrongTenant = fixtures.token(
    fixedNow,
    AccessTokenFixtures.ISSUER,
    List.of(AccessTokenFixtures.AUDIENCE),
    fixedNow.plusSeconds(300),
    "orders.read",
    "tenant-test-b"
);

String expired = fixtures.token(
    fixedNow.minusSeconds(600),
    AccessTokenFixtures.ISSUER,
    List.of(AccessTokenFixtures.AUDIENCE),
    fixedNow.minusSeconds(300),
    "orders.read",
    "tenant-test-a"
);
~~~

`wrongAudience` phải thất bại ở authentication nếu audience validator được cấu hình. `wrongTenant` có thể vượt authentication nhưng phải thất bại ở domain authorization khi request yêu cầu tenant khác. `expired` phải thất bại theo clock và clock-skew policy của decoder.

### 4.5. Vì sao token tạo lúc chạy vẫn là fixture được kiểm soát?

Một fixture được kiểm soát bởi **scenario, signing key, issuer, claims, test clock và expected outcome**, không nhất thiết bởi một chuỗi compact JWT bất biến.

Tạo token lúc chạy giúp:

- Không commit raw token vào source.
- Dễ tạo nhiều biến thể claim có chủ đích.
- Test thời hạn không phụ thuộc ngày chạy.
- Tạo token với key cũ/key mới.
- Test nhiều issuer/audience profiles.

Để tái hiện bug production, lưu metadata đã redacted và scenario tái tạo; không cần sao chép bearer credential production.

## 5. Cấu hình decoder test và clock cố định

Một bộ token fixture có giá trị khi decoder được kiểm tra thật, không chỉ mock `Jwt`.

### 5.1. Decoder dùng public key test

~~~java
package com.example.orders.testsecurity;

import java.time.Clock;
import java.time.Duration;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.RSAKey;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class TestJwtDecoderFactory {

    private TestJwtDecoderFactory() {}

    public static NimbusJwtDecoder decoder(
            RSAKey trustedKey,
            String issuer,
            String audience,
            Clock clock) {

        RSAPublicKey publicKey = trustedKey.toRSAPublicKey();

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(publicKey).build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ZERO);
        timestamps.setClock(clock);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not accepted",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtIssuerValidator(issuer),
                timestamps,
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Đây là decoder cho **test JWS với RSA public key**. Trong production, thường lấy keys từ trusted JWKS URI và dùng validators phù hợp. Nếu Nimbus version trong project không có cách lấy public key như trên, có thể giữ trực tiếp `RSAPublicKey` khi tạo key pair rồi truyền vào factory.

**Lưu ý profile:** ví dụ kiểm tra issuer, timestamp và audience. Nó chưa thể hiện toàn bộ JWT Access Token Profile validation như `typ`, required `client_id`/`jti` hoặc custom claim schema. Nếu hợp đồng issuer yêu cầu chúng, thêm `OAuth2TokenValidator<Jwt>` riêng và fixtures cho từng claim.

### 5.2. Test thời gian phải deterministic

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-15T00:00:00Z"),
    ZoneOffset.UTC
);
~~~

Sinh các trường hợp:

- Token hết hạn trước fixed clock.
- Token còn hạn.
- Token có `nbf` sau fixed clock.
- Token nằm ở biên clock skew.

Không dùng `Thread.sleep` để chờ token hết hạn. Test phải nhanh, tái lập được và không phụ thuộc thời gian trên máy CI.

Nếu validator có clock skew, ghi rõ giá trị trong contract test. Một token hết hạn 10 giây trước hiện tại có thể vẫn được chấp nhận nếu policy cho phép skew 60 giây; expected result phải dựa vào policy thực tế.

## 6. Kiểm tra JWT profile, header và claims khi issuer thay đổi

### 6.1. Header fields

Một JWS JWT có header:

~~~json
{
  "alg": "RS256",
  "kid": "fixture-rsa-2026-01",
  "typ": "at+jwt"
}
~~~

Các trường cần kiểm soát:

- `alg`: chỉ cho phép thuật toán đã được phê duyệt.
- `kid`: định vị public key trong trusted JWKS; không phải bằng chứng khóa tin cậy.
- `typ`: token type/profile theo hợp đồng issuer.
- `crit`/`cty` nếu profile có sử dụng.

Không chấp nhận thuật toán chỉ vì token tự khai. **Verifier quyết định allowlist**, không phải token header.

### 6.2. Claims và kiểu dữ liệu

| Claim | Contract cần xác định | Fixture drift nên có |
|---|---|---|
| `iss` | Exact issuer identifier | Old/new issuer, issuer ngoài allowlist |
| `sub` | Subject identifier và tính ổn định | Missing/changed subject, collision giữa issuers |
| `aud` | Resource Server audience | Wrong audience, string/array representation |
| `exp` | Expiry semantics | Expired, missing nếu profile yêu cầu |
| `nbf` | Not-before | Future value |
| `iat` | Issued-at | Missing/invalid nếu profile yêu cầu |
| `jti` | Token identifier nếu profile yêu cầu | Missing/duplicate theo policy |
| `client_id` | Client identity | Missing/renamed/type drift |
| `scope`/`scp` | Scope schema | Space string, array, renamed claim |
| `roles`/`groups` | Role mapping | New claim name, unexpected role |
| `tenant_id` | Tenant binding | Missing, wrong tenant, type drift |
| `typ` | Access-token type | Missing/wrong type |

Không phải mọi claim trong bảng đều bắt buộc với mọi issuer. Ghi **required / optional / ignored / forbidden** theo token profile đã thỏa thuận.

### 6.3. Scope string và provider-specific claims

OAuth 2.0 scope values thường được biểu diễn trong access token dưới dạng chuỗi phân tách bằng dấu cách:

~~~json
{"scope": "orders.read orders.write"}
~~~

Một số provider có thể phát claim khác như `scp` hoặc role array. Không giả định mọi provider dùng cùng schema.

Ví dụ contract nội bộ:

~~~yaml
scopeMapping:
  claim: scope
  representation: space-delimited-string
  authorityPrefix: SCOPE_
  allowed:
    - orders.read
    - orders.write
    - orders.approve
~~~

Đây là manifest do ứng dụng định nghĩa. Nếu issuer đổi `scope` sang `scp`, không tự “đoán cả hai” mà không có migration plan. Có thể hỗ trợ cả hai trong giai đoạn chuyển tiếp với precedence và deadline rõ, sau đó bỏ claim cũ.

### 6.4. Token profile và `typ`

Nếu Resource Server yêu cầu JWT Access Token Profile RFC 9068, header type thường là `at+jwt` và claims/profile phải tuân thủ chuẩn đó. Không phải mọi JWT access token hiện có đều theo RFC 9068.

Nên có fixtures:

- `typ=at+jwt` đúng profile.
- `typ` bị thiếu nếu profile yêu cầu.
- `typ` khác profile.
- Token có audience dành cho OIDC client thay vì API.
- ID Token có chữ ký issuer hợp lệ nhưng sai intended use.

Đừng chỉ xác minh signature rồi chấp nhận mọi JWT cùng issuer.
## 7. Bộ fixture cho JWKS và key rotation

### 7.1. JWKS là một phần của issuer contract

Resource Server thường lấy public signing keys từ JWKS endpoint được discovery metadata hoặc cấu hình trusted cung cấp.

JWKS test có thể chứa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "fixture-rsa-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<PUBLIC-MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "fixture-rsa-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<PUBLIC-MODULUS-NEW>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị modulus là placeholder. **Không đưa private RSA parameters `d`, `p`, `q`, `dp`, `dq`, `qi` vào public JWKS.**

### 7.2. Rotation thường có giai đoạn overlap

~~~text
T0: JWKS publish key-old
T1: JWKS publish key-old + key-new
T2: issuer bắt đầu ký token mới bằng key-new
T3: token ký bằng key-old hết hạn/qua thời gian overlap
T4: JWKS bỏ key-old
~~~

Resource Server có thể cache JWKS. Vì vậy kiểm tra rotation không chỉ là “JWKS JSON có key mới” mà cần xác minh decoder có thể lấy key mới theo cache/refresh behavior của phiên bản thư viện.

### 7.3. Fixture scenarios cho rotation

| Scenario | JWKS | Token | Expected |
|---|---|---|---|
| Baseline | Chỉ key-old | Signed bởi key-old | Accept |
| Publish new key | old + new | Signed bởi key-old | Accept |
| Begin signing new key | old + new | Signed bởi key-new | Accept |
| Old token trong overlap | old + new | Signed bởi key-old, còn hạn | Accept |
| Old key removed quá sớm | Chỉ key-new | Signed bởi key-old | Reject hoặc lỗi theo policy; phát hiện rollout |
| Unknown key ID | Không có `kid` | Signed bằng key ngoài set | Reject |
| JWKS unavailable | Endpoint timeout/5xx | Token cần key chưa cache | Không fail open |
| Duplicate/ambiguous key IDs | JWKS không hợp lệ | Token có `kid` trùng | Không suy đoán key tin cậy |

Không có thời gian overlap cố định cho mọi issuer. Tính dựa trên access token max lifetime, clock skew, JWKS cache/refresh behavior và rollout topology.

### 7.4. Unknown `kid` không phải lý do tải arbitrary URL

Nếu token có header:

~~~json
{
  "kid": "attacker-key",
  "jku": "https://attacker.example/jwks.json"
}
~~~

Resource Server không nên tải `jku` tùy ý để tìm key. Chỉ lấy keys từ **trusted JWKS URI** của issuer đã được cấu hình/allowlist. `kid` chỉ chọn một key trong trusted set.

### 7.5. Algorithm migration

Nếu issuer đổi từ RS256 sang ES256, đó là thay đổi hợp đồng về key type và thuật toán:

- Resource Server phải có allowlist thuật toán phù hợp.
- JWKS phải publish public EC key đúng curve/metadata.
- Key rotation và algorithm rollout cần overlap nếu client/token lifetime đòi hỏi.
- Token signed bằng algorithm không được phép phải bị reject.
- Không tự động chấp nhận bất kỳ `alg` nào do header token gửi.

Tạo fixture cho old/new algorithm trong thời gian migration và negative fixture cho algorithm ngoài allowlist.

## 8. Fixture cho issuer, audience và discovery metadata

### 8.1. Issuer là identifier chính xác

JWT `iss` phải khớp issuer tin cậy theo contract. Những thay đổi tưởng nhỏ cũng có thể phá xác thực:

~~~text
https://id.example.test/realms/orders
https://login.example.test/realms/orders
https://id.example.test/realms/orders/
~~~

Không tự chuẩn hóa slash, scheme hoặc hostname để “làm cho khớp” nếu hợp đồng không nói như vậy. Issuer migration cần được xem là thay đổi trust configuration.

### 8.2. OIDC discovery snapshot

Một metadata fixture có thể chứa:

~~~json
{
  "issuer": "https://id.example.test/realms/orders",
  "jwks_uri": "https://id.example.test/realms/orders/protocol/openid-connect/certs",
  "authorization_endpoint": "https://id.example.test/realms/orders/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.test/realms/orders/protocol/openid-connect/token",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Resource Server JWT verification chủ yếu cần issuer/JWKS relationship; các fields khác phục vụ OAuth/OIDC clients hoặc capabilities khác. Không nhầm discovery metadata của OIDC Provider với việc mọi field đều cần cho access token validation.

Contract tests cần kiểm tra:

- Metadata `issuer` khớp exact configured issuer.
- `jwks_uri` nằm trong trusted domain/allowlist.
- HTTPS và certificate validation được giữ.
- Metadata không trỏ đến host ngoài ý muốn.
- JWKS endpoint trả key set đúng schema.
- Metadata endpoint errors được phân biệt với token invalid.
- Discovery change không vô tình đổi registration/login behavior của OAuth2 Client.

### 8.3. Issuer URL migration

Nếu issuer đổi URL, token cũ thường vẫn mang `iss` cũ. Kế hoạch migration có thể:

1. Thêm issuer mới vào trusted registry sau review.
2. Cấu hình manager/decoder cho issuer mới với audience/profile validators đầy đủ.
3. Tạm thời hỗ trợ issuer cũ và mới nếu security policy cho phép.
4. Chạy fixtures cho cả hai issuer, bao gồm sai audience và issuer giả.
5. Đảm bảo identity mapping phân biệt `(iss, sub)`.
6. Theo dõi tỷ lệ token cũ/mới và clients chưa chuyển.
7. Chờ token cũ hết hạn và hoàn tất migration.
8. Gỡ issuer cũ khỏi allowlist và chạy regression tests.

Không thay issuer cũ bằng URL mới trong config rồi kỳ vọng token cũ tự hợp lệ. Cũng không giữ issuer cũ vô thời hạn nếu trust domain đã ngừng được tin cậy.

## 9. Opaque token và introspection fixtures

Không phải issuer nào cũng phát JWT. Với opaque token, Resource Server gọi introspection endpoint theo RFC 7662. Bộ fixture cần kiểm tra **request và response contract**, không chỉ một chuỗi token.

### 9.1. Response fixture active

~~~json
{
  "active": true,
  "scope": "partner.reports.read",
  "client_id": "partner-export-client",
  "sub": "partner-user-01",
  "aud": ["partner-api"],
  "iss": "https://partner-id.example.test",
  "exp": 2000000300
}
~~~

Các fields ngoài `active` phụ thuộc provider. Không giả định mọi Authorization Server trả `aud`, `iss`, `exp` hoặc `tenant_id`.

### 9.2. Response fixture inactive

~~~json
{"active": false}
~~~

HTTP 200 với `active:false` là một introspection result hợp lệ, biểu thị token inactive. Nó khác với:

- HTTP 401 do client credentials của Resource Server sai.
- HTTP 403 do introspection client không có quyền.
- HTTP 429 do rate limit.
- HTTP 5xx hoặc timeout do dependency failure.

Không biến network failure thành `active:false` và cache nó như một quyết định revoke.

### 9.3. Ma trận opaque fixtures

| Fixture | Response/request thay đổi | Expected |
|---|---|---|
| `opaque-active-read` | active true, scope read | Authentication accepted |
| `opaque-inactive` | active false | Reject token |
| `opaque-missing-scope` | active true, không có write | Authentication accepted; write 403 |
| `opaque-wrong-audience` | active true nhưng aud sai | Reject nếu API yêu cầu audience |
| `opaque-expired` | exp đã qua | Reject nếu profile/validator yêu cầu exp |
| `introspection-unauthorized` | HTTP 401 | Lỗi credential của RS với AS |
| `introspection-forbidden` | HTTP 403 | Policy introspection client |
| `introspection-rate-limited` | HTTP 429 | Backoff/availability policy |
| `introspection-timeout` | Không có response | Fail closed |
| `introspection-schema-drift` | Claim type/name thay đổi | Contract test fail rõ |

### 9.4. Opaque token trong test không cần là token thật

~~~text
fixture-opaque-partner-read-001
~~~

Có thể dùng chuỗi giả và mock introspector hoặc HTTP stub trả JSON fixture tương ứng. Mục tiêu là test giao thức introspection, authority mapping và failure handling. Không dùng opaque access token production, vì nó là bearer credential dù không giải mã được.

Nếu test HTTP client authentication, dùng client ID/secret test riêng và kiểm tra request body/header không bị log. Chi tiết authentication method phải khớp AS contract; không mặc định mọi provider đều dùng HTTP Basic nếu provider hỗ trợ phương pháp khác.

### 9.5. Phân loại kết quả introspection

| Kết quả | Authentication interpretation |
|---|---|
| HTTP 200 + `active:true` | Token được xác nhận active; tiếp tục validators/policy |
| HTTP 200 + `active:false` | Token inactive |
| HTTP 200 nhưng thiếu `active` hoặc sai type | Response không đúng contract; không mặc định active |
| HTTP 401/403 | Introspection client authentication/authorization failure |
| HTTP 429 | AS rate limit |
| HTTP 5xx/timeout | Dependency failure |
| JSON malformed | Introspection protocol/contract failure |

Không coi HTTP 200 đơn thuần là token hợp lệ. Cũng không cache timeout như một negative token result.

### 9.6. Scope và audience của opaque token

Opaque introspection có thể trả `scope` như chuỗi và attributes tùy provider. Cần kiểm tra:

- Scope có thuộc namespace API không.
- `aud` có được provider trả theo contract không.
- Nếu API bắt buộc audience mà introspection không cung cấp, phải thỏa thuận profile/validation khác với AS.
- `exp` có tồn tại và kiểu dữ liệu được converter hỗ trợ không.
- `client_id`/`sub` được phân biệt đúng cho user-delegated và client-credentials flows.

Không giả định opaque token luôn đại diện user; principal có thể là service client tùy grant type.

## 10. Tách contract tests theo các lớp của Resource Server

Một bộ test tốt không nên phụ thuộc duy nhất vào end-to-end call tới một issuer đang chạy. Chia thành nhiều lớp để biết chính xác phần nào bị phá khi provider thay đổi.

~~~mermaid
flowchart TD
    A["Versioned fixture manifest"] --> B["JWT/JWKS unit tests"]
    A --> C["Opaque introspection contract tests"]
    A --> D["Issuer discovery tests"]
    B --> E["Decoder + claim validators"]
    C --> F["Introspector + authority mapping"]
    D --> G["Issuer/JWKS metadata trust"]
    E --> H["SecurityFilterChain integration"]
    F --> H
    G --> H
    H --> I["Authorization + tenant tests"]
    I --> J["Sandbox provider compatibility"]
    J --> K["Release gate / rollout"]
~~~

### 10.1. Unit tests cho decoder

Kiểm tra:

- Valid signed JWT accepted.
- Wrong issuer rejected.
- Wrong audience rejected.
- Expired/not-yet-valid rejected theo fixed clock.
- Bad signature rejected.
- Unknown key rejected.
- Algorithm ngoài allowlist rejected.
- Required claim missing/wrong type rejected nếu profile yêu cầu.
- `typ` sai bị từ chối nếu validator profile yêu cầu.

Unit tests nên nhanh, không cần gọi mạng. Public key test được truyền trực tiếp hoặc JWKS test snapshot được dùng tùy mục tiêu.

### 10.2. Integration tests cho SecurityFilterChain

Dùng MockMvc/Spring Security Test để kiểm tra:

- Request không token tới protected endpoint trả 401.
- Token hợp lệ có đúng scope được phép.
- Token hợp lệ thiếu scope trả 403.
- Token sai audience không vượt authentication.
- Partner token không được xử lý ở Orders JWT chain.
- Fallback chain deny paths chưa khai báo.
- Body/header/status không mâu thuẫn.

Helper `jwt()` có thể tạo Authentication giả lập để kiểm tra authorization. Nó **không chứng minh signature, issuer, audience hoặc JWKS decoder hoạt động**; cần tests decoder riêng hoặc gửi compact JWT test thật qua Bearer filter.

### 10.3. Contract tests cho OIDC discovery/JWKS

Dùng snapshot metadata/JWKS hoặc local mock server:

- Metadata issuer chính xác.
- JWKS URI nằm trong trust registry.
- JWKS có key ID/algorithm phù hợp.
- Key rotation old/new.
- Unknown key behavior.
- Network timeout/5xx.
- TLS certificate failure nếu test infrastructure hỗ trợ.
- Metadata issuer mismatch.

Không cần gọi production IdP trong mỗi unit test. Một sandbox contract suite hoặc scheduled test có thể kiểm tra integration thật, còn pull request tests dùng fixtures cố định.

### 10.4. Contract tests cho opaque introspection

Stub HTTP endpoint để trả:

- active true/false.
- Claim set đầy đủ/tối thiểu.
- HTTP 401/403/429/5xx.
- Timeout.
- Malformed JSON.
- Missing `active` hoặc wrong type.
- Scope schema thay đổi.
- Audience/issuer drift.

Assert cả request: endpoint, method POST, form parameter `token`, authentication method của Resource Server và không lộ token trong logs. Chi tiết auth method phải khớp AS contract.
## 11. Ví dụ kiểm thử decoder với JUnit

Một test cơ bản dùng decoder và token factory:

~~~java
package com.example.orders.security;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import com.nimbusds.jose.jwk.RSAKey;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

class IssuerCompatibilityTests {

    private final Instant now =
        Instant.parse("2026-11-15T00:00:00Z");

    private RSAKey signingKey;
    private AccessTokenFixtures fixtures;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        signingKey = TestSigningKeys.newRsaKey("fixture-rsa-01");
        fixtures = new AccessTokenFixtures(signingKey);

        decoder = TestJwtDecoderFactory.decoder(
            signingKey,
            AccessTokenFixtures.ISSUER,
            AccessTokenFixtures.AUDIENCE,
            Clock.fixed(now, ZoneOffset.UTC)
        );
    }

    @Test
    void acceptsValidAccessToken() {
        String token = fixtures.validReadToken(now);

        assertDoesNotThrow(() -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudience() {
        String token = fixtures.token(
            now,
            AccessTokenFixtures.ISSUER,
            List.of("billing-api"),
            now.plusSeconds(300),
            "orders.read",
            "tenant-test-a"
        );

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() {
        String token = fixtures.token(
            now.minusSeconds(600),
            AccessTokenFixtures.ISSUER,
            List.of(AccessTokenFixtures.AUDIENCE),
            now.minusSeconds(300),
            "orders.read",
            "tenant-test-a"
        );

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

Đây là ví dụ cấu trúc. `AccessTokenFixtures` và `TestJwtDecoderFactory` cần được đặt trong test source set và imports đầy đủ. Decoder dùng public key được tạo từ cùng test key; để kiểm tra **bad signature**, tạo key pair khác và ký token bằng private key không tương ứng với public key decoder tin.

### 11.1. Test issuer sai

Sinh token có signature hợp lệ bằng cùng test key nhưng `iss` khác:

~~~java
String wrongIssuer = fixtures.token(
    now,
    "https://untrusted.example.test",
    List.of(AccessTokenFixtures.AUDIENCE),
    now.plusSeconds(300),
    "orders.read",
    "tenant-test-a"
);

assertThrows(JwtException.class, () -> decoder.decode(wrongIssuer));
~~~

Test này chứng minh issuer validation được chạy sau signature decode.

### 11.2. Test tenant mismatch là authorization, không phải decoder failure

Một token có `tenant_id=tenant-test-b` vẫn có thể là JWT hợp lệ. Decoder chỉ nên xác minh issuer, audience, signature và token profile. Sau đó service/authorization policy phải từ chối request đến tenant-test-a nếu principal không có quyền.

Không nhét mọi business ACL vào JWT decoder. Decoder không có đủ context về resource ID, current membership hoặc trạng thái dữ liệu.

## 12. Kiểm thử thay đổi nhà phát hành theo từng loại drift

Một release của issuer có thể thay đổi nhiều thuộc tính cùng lúc. Fixture suite nên mô phỏng từng thay đổi riêng để tìm nguyên nhân.

### 12.1. Compatibility matrix

| Provider change | Rủi ro | Fixture/test cần thêm | Cách rollout |
|---|---|---|---|
| JWKS thêm key mới | Decoder cache/refresh không nhận key | Signed token với new `kid` | Publish overlap rồi switch signing |
| JWKS bỏ key cũ | Token cũ còn sống bị từ chối | Old-key token và expiry boundary | Chờ max token lifetime + skew/cache |
| Algorithm đổi | Decoder không hỗ trợ hoặc policy quá rộng | Old/new alg và unsupported alg | Allowlist rõ, overlap có thời hạn |
| Issuer URL đổi | `iss` mismatch, identity split | Old/new issuer fixtures | Dual trust có review, sunset old |
| Audience đổi | Token không intended for API | Old/new audience fixtures | Additive transition nếu contract cho phép |
| `scope` đổi thành `scp` | Authorities biến mất | Claim type/name fixtures | Dual mapping có deadline, sau đó remove |
| Role claim đổi tên | Privilege mapping mất hoặc tăng | Role mapping fixtures | Explicit mapping và least privilege |
| `sub` format đổi | User identity/ownership mapping sai | Subject stability/collision tests | Migration identity mapping |
| `client_id`/`azp` đổi | Client policy fail | Client identity fixtures | Update registered clients/validators |
| Token `typ` đổi | Profile mismatch | Header type fixtures | Phê duyệt profile/version |
| `exp` lifetime đổi | Session/availability/revocation behavior đổi | Short/long lifetime fixtures | Review cache, clock skew, SLO |
| Introspection schema đổi | Opaque principal/authorities sai | Active/claims response fixtures | Contract test và versioned mapping |
| Discovery `jwks_uri` đổi | Fetch từ endpoint không mong đợi | Metadata snapshot diff | Allowlist/validate new URI |
| Issuer signing cert rotate | Key trust gap | Old/new key overlap fixtures | Planned rotation |
| Scope bị thu hồi | Caller vẫn được quyền cũ do cache | Valid token thiếu scope, cache invalidation test | Invalidate/shorten cache theo policy |

### 12.2. Additive change và breaking change

**Additive** không có nghĩa tự động an toàn. Issuer thêm một claim optional mới thường ít rủi ro nếu Resource Server bỏ qua claim không dùng; nhưng thêm một role mà converter tự map mọi roles thành authorities có thể làm tăng quyền.

Breaking changes thường gồm:

- Thay issuer identifier.
- Thay audience khiến API không còn là intended recipient.
- Xóa/đổi tên scope đang được client sử dụng.
- Đổi kiểu claim mà converter phụ thuộc.
- Đổi signing algorithm/key type ngoài decoder support.
- Thay token profile hoặc required claims.

Mỗi thay đổi phải được đánh giá theo **authentication acceptance** và **authorization result**. Một token vẫn được xác thực nhưng quyền đã biến mất cũng là compatibility change ảnh hưởng client.

### 12.3. Provider drift phải làm test fail có ý nghĩa

Nếu `scope` biến từ:

~~~json
{"scope": "orders.read orders.write"}
~~~

sang:

~~~json
{"scp": ["orders.read", "orders.write"]}
~~~

một test chỉ assert HTTP 200 với endpoint public sẽ không phát hiện. Contract suite cần kiểm tra:

- Decoder chấp nhận token đúng profile.
- Converter tạo đúng authorities.
- Endpoint read/write phản ánh đúng quyền.
- Claim ngoài hợp đồng không vô tình cấp role.
- Token thiếu scope thật sự bị 403.

## 13. Kiểm soát OIDC discovery và issuer configuration

### 13.1. Metadata snapshot phải khớp issuer đã cấu hình

OIDC discovery document có trường `issuer` và `jwks_uri`. Resource Server không nên tin một metadata document chỉ vì HTTP request thành công. Nó phải thuộc đúng issuer được cấu hình/allowlist.

Khi provider thay đổi:

- `issuer` phải khớp identifier mà application tin.
- `jwks_uri` phải được chấp nhận theo network/trust policy.
- HTTPS và certificate validation phải được giữ.
- Redirects/host changes phải được đánh giá chống SSRF.
- Metadata version/capabilities cần so sánh có chủ đích.

Không tải metadata/JWKS từ arbitrary `iss` hoặc `jku` do token cung cấp.

### 13.2. Discovery contract test

Một test có thể kiểm tra snapshot metadata:

~~~java
assertEquals(
    "https://id.example.test/realms/orders",
    metadata.getIssuer().toString()
);

assertTrue(
    trustedJwksHosts.contains(metadata.getJwksUri().getHost())
);
~~~

Đây là pseudocode vì type metadata phụ thuộc client/discovery library. Mục đích là exact issuer match và trusted JWKS host policy. Không dùng host allowlist quá rộng nếu trust boundary chỉ cần một host cụ thể.

### 13.3. Không để discovery test tự sửa production trust

Contract test có thể phát hiện issuer mới, nhưng **không nên tự động thêm issuer mới vào allowlist production** chỉ vì discovery endpoint trả về nó. Thay đổi trust cần review, security approval và release policy của tổ chức.

## 14. CI pipeline cho bộ token mẫu

Một pipeline hiệu quả có thể phân lớp theo tốc độ và nguồn phụ thuộc:

~~~text
Pull request:
  1. Compile/test fixtures factory
  2. JWT decoder tests with local keys
  3. JWKS rotation tests with local stub
  4. Opaque introspection tests with HTTP stub
  5. SecurityFilterChain authorization tests
  6. Tenant/issuer negative tests

Scheduled / release candidate:
  7. Sandbox issuer discovery contract
  8. Sandbox JWKS and key rotation compatibility
  9. Sandbox opaque introspection contract
 10. Compatibility report and approval gate
~~~

Không cần gọi production IdP trong mọi pull request. Unit/contract fixtures phải tái lập được và không phụ thuộc Internet; sandbox tests kiểm tra integration thật theo lịch hoặc trước release.

### 14.1. PR tests cần deterministic

- Test clock cố định.
- Test signing keys riêng.
- JWKS stub/local endpoint.
- Introspection stub.
- Không dùng token thật.
- Không dựa vào provider uptime.
- Không chờ token hết hạn bằng sleep.
- Không chạy song song tests dùng chung mutable key/metadata state nếu gây race.

### 14.2. Sandbox contract suite

Sandbox test nên:

- Dùng client registration riêng, scopes tối thiểu.
- Token có lifetime ngắn.
- Tạo synthetic user/service principal.
- Không có quyền truy cập production data.
- Redact Authorization header/body khỏi HTTP logs.
- Thu thập issuer metadata/JWKS version và response schema.
- Chỉ thực hiện thao tác test có thể đảo ngược.
- Dọn test data theo policy.

Không tự gọi endpoint production để lấy token chỉ nhằm làm fixture.

### 14.3. Compatibility report

~~~text
Issuer alias: orders-sandbox
Issuer contract version: 4
Fixture set version: 3
Application version: 2.8.0

JWT valid baseline: PASS
Wrong issuer: PASS (rejected)
Wrong audience: PASS (rejected)
Old/new key overlap: PASS
Unknown kid: PASS (rejected)
Scope mapping: PASS
Tenant mismatch: PASS (denied)
Opaque active/inactive: PASS
Introspection timeout: PASS (fail closed)
OIDC discovery metadata: PASS
~~~

Đây là format báo cáo minh họa. **PASS cho negative test** nghĩa là hệ thống đã từ chối đúng, không phải request đã thành công.

## 15. Quy trình tương thích khi issuer thông báo thay đổi

### Bước 1 — Xác định chính xác thay đổi

Yêu cầu release notes/contract diff từ issuer:

- Thay đổi khi nào?
- Có overlap không?
- Issuer identifier có đổi không?
- Audience có đổi không?
- Key mới được publish khi nào và key cũ bị gỡ khi nào?
- Scope/role/claims thay đổi thế nào?
- Opaque introspection response có đổi schema không?
- Discovery/JWKS URI có đổi host không?

Không dựa vào một token mẫu duy nhất để đoán toàn bộ change.

### Bước 2 — Tạo fixture cho trạng thái cũ và mới

Ví dụ key rotation:

~~~text
old JWKS + old key token
old+new JWKS + old key token
old+new JWKS + new key token
new JWKS only + new key token
new JWKS only + old key token
~~~

Ví dụ scope migration:

~~~text
old claim: scope = "orders.read"
new claim: scp = ["orders.read"]
missing scope
unexpected scope
~~~

Mỗi fixture có expected result và phase tương ứng.

### Bước 3 — Chạy test ở local/CI

Chạy decoder, introspection, security chain, tenant và negative tests với fixture. Đảm bảo lỗi fail rõ ở tầng đúng, không sửa validator để mọi fixture đều pass.

### Bước 4 — Đánh giá backward compatibility

- Token cũ còn được phát hành hoặc còn hiệu lực bao lâu?
- Có cần dual trust trong một giai đoạn không?
- Có issuer mapping/identity collision?
- Có client nào chưa nâng cấp?
- Có API scope nào thay đổi semantics?
- Có cache/replicas nào giữ key/claims cũ?

### Bước 5 — Rollout có overlap và quan sát

- Publish trusted config mới sau review.
- Verify key/issuer mới trong sandbox.
- Triển khai canary.
- Theo dõi failure categories theo issuer alias.
- Giữ rollback path rõ.
- Chỉ remove issuer/key/claim cũ khi hết cửa sổ token lifetime/cache và hoàn thành migration.

### Bước 6 — Đóng contract cũ

- Bỏ old issuer/key trust theo lịch.
- Bỏ legacy claim mapping.
- Gỡ fixture cũ khỏi active suite hoặc chuyển sang regression archive nếu còn giá trị.
- Cập nhật manifest/profile version.
- Giữ negative test chứng minh issuer cũ bị từ chối nếu trust đã bị thu hồi.

Không giữ hai issuer trust mãi mãi chỉ để tránh sửa client; trust domain cũ có thể đã không còn được phép.

## 16. Không so sánh compact JWT bằng chuỗi cố định

Một JWT có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Nếu mỗi lần test tạo token mới:

- `iat`/`exp` có thể khác.
- Signature khác khi signing key khác.
- Header serialization/order có thể thay đổi.
- `jti` có thể được tạo mới.

Vì vậy không nên chỉ assert compact JWT bằng đúng một string trừ khi đang test serialization/canonicalization cụ thể.

Nên assert semantic contract:

- Decoder trả đúng issuer/subject/audience.
- Authorities đúng.
- Invalid conditions bị reject.
- Security endpoint trả status đúng.
- Key ID được resolve từ trusted JWKS.
- Claims type/mapping giữ đúng.

Nếu có snapshot test token bytes, cần khóa/clock cố định và hiểu rõ test đang bảo vệ điều gì. Snapshot bytes không thay thế signature/validator integration test.

## 17. Bảo vệ secrets và dữ liệu test

### 17.1. Không commit production credentials

Không đưa vào fixture repository:

- Access token production.
- Refresh token.
- ID Token có thông tin cá nhân.
- Client secret.
- Private signing key.
- mTLS private key/certificate có hiệu lực production.
- Raw introspection request logs.
- Authorization headers trong CI artifacts.

JWT payload thường Base64URL-encoded chứ **không được mã hóa**; ai có token có thể đọc claims. Opaque token là bearer credential dù không đọc được nội dung.

### 17.2. Test key và secret rotation

Test key có thể được version trong test resources khi chỉ có giá trị cho test. Nhưng:

- Không dùng chung với production.
- Không cấp trust test JWKS trong production config.
- Không publish private key trong artifact public.
- Không dùng một test HMAC secret cho nhiều hệ thống.
- Khi test key bị thay, cập nhật fixture manifest và public JWKS snapshot tương ứng.

### 17.3. Logs và failure diagnostics

Một log an toàn:

~~~text
event=jwt_validation_failed
issuer_alias=orders-sandbox
failure=WRONG_AUDIENCE
request_id=req-test-014
fixture_id=wrong-audience
~~~

Tránh:

~~~text
Authorization: Bearer eyJ...
introspection client_secret=...
private_key=...
~~~

Có thể log fixture ID vì nó là identifier test, nhưng không log raw token string hoặc toàn bộ request body introspection.

## 18. Những nhầm lẫn thường gặp

### “Một JWT payload JSON hợp lệ là đủ test Resource Server”

Không. Payload chưa có chữ ký; decoder phải xác minh compact token bằng key được trust.

### “Dùng mockJwt() là đã test chữ ký”

Không. Mock helper tạo Authentication cho authorization tests; cần decoder/JWKS test riêng.

### “Token lấy từ production là fixture tốt nhất”

Không nên. Đó là bearer credential và có thể chứa claims cá nhân; dùng sandbox/synthetic test tokens.

### “Chỉ cần một token valid để test issuer compatibility”

Không. Cần negative fixtures và các trường hợp key rotation, audience, scopes, claims, tenant, introspection và discovery.

### “Issuer đổi URL thì chỉ sửa property”

Token cũ vẫn mang `iss` cũ. Migration cần overlap có kiểm soát, identity mapping và thời gian sunset.

### “JWKS có key mới nghĩa Resource Server chắc chắn dùng key mới ngay”

Decoder có thể cache JWKS. Test refresh/unknown kid và rollout overlap theo behavior thực tế của thư viện.

### “Không thấy lỗi decoder tức là token được quyền gọi API”

Authentication thành công chưa bảo đảm scope, role, tenant, owner hoặc ACL.

### “Scope claim đổi từ string sang array vẫn tự tương thích”

Không mặc định. Converter và provider contract cần test kiểu dữ liệu/schema chính xác.

### “`kid` trong token đáng tin”

Không. `kid` chỉ là selector trong trusted key set; không được lấy key từ URL do token quảng bá.

### “Timeout introspection tương đương `active:false`”

Không. Timeout là dependency failure, còn `active:false` là kết quả token inactive.

### “Thêm issuer mới vào discovery metadata là đủ để tin”

Không. Trusted issuer allowlist và review vẫn cần thiết; metadata không tự cấp trust.

### “Cứ giữ issuer cũ mãi để token không hỏng”

Có thể mở rộng trust ngoài thời hạn cần thiết. Dùng migration window, đo usage và remove old trust đúng lịch.

## 19. Ma trận chọn loại test theo thay đổi

| Thay đổi của nhà phát hành | Unit fixture | Integration test | Sandbox test |
|---|---|---|---|
| JWT claim name/type | Có | Có, qua filter/authority mapping | Khi cần xác nhận provider thật |
| Issuer URL | Có old/new fixtures | Có resolver/decoder | Có, discovery |
| Audience | Có positive/negative | Có 401 behavior | Có nếu provider thay token audience |
| Signing key rotation | Có test keys old/new | Có JWKS stub/cache | Có, trước rollout |
| Algorithm | Có key/alg fixtures | Có decoder test | Có nếu provider đổi |
| Opaque active/schema | Có JSON fixtures | Có introspector HTTP stub | Có, sandbox introspection |
| Client auth method | Có request contract | Có mock endpoint | Có, provider thật |
| Scope semantics | Có mapping fixtures | Có endpoint 403/allow tests | Có nếu issuer đổi scope |
| Tenant claim | Có claim fixtures | Có service ACL tests | Chỉ khi provider contract thay |
| OIDC metadata | Snapshot tests | Có mock discovery/JWKS | Có trước release |
| Provider outage | Simulated failure | Có timeout/5xx tests | Không cần cố ý làm outage production |
| Cache/revocation | Có deterministic clock/state | Có integration | Có sandbox nếu cần xác minh semantics |

Không phải thay đổi nào cũng cần gọi sandbox. Hầu hết regression có thể được bắt bằng fixtures cục bộ; sandbox dùng để xác nhận nhà phát hành thật đang tuân contract.

## 20. Checklist áp dụng cho bộ token mẫu

- [ ] Mỗi fixture có ID, mục đích, issuer alias/profile và expected result.
- [ ] Fixture set có version riêng.
- [ ] Dùng synthetic users/tenants/clients.
- [ ] Không lưu token production, refresh token hoặc client secret.
- [ ] JWT signature tests dùng private key test và trusted public key/JWKS test.
- [ ] Test issuer sai, audience sai, expiry, nbf, signature và unknown kid.
- [ ] Kiểm tra algorithm allowlist và token type/profile theo contract.
- [ ] Kiểm tra required/optional claims và kiểu dữ liệu.
- [ ] Scope/role mapping có positive và negative fixtures.
- [ ] Có test tenant mismatch và cross-issuer identity collision.
- [ ] JWKS key rotation có old/new overlap và unknown key cases.
- [ ] Discovery metadata exact issuer và trusted JWKS URI được kiểm tra.
- [ ] Opaque introspection có active true/false, timeout, 401/403/429/5xx và schema drift.
- [ ] Authentication acceptance tách khỏi authorization decision.
- [ ] Test clock cố định, không sleep chờ token hết hạn.
- [ ] Unit/CI tests không phụ thuộc production issuer availability.
- [ ] Sandbox contract tests dùng client/scopes test tối thiểu.
- [ ] Logs và test artifacts redacted.
- [ ] Issuer migration có dual-trust window và old-issuer sunset.
- [ ] CI report ghi rõ fixture version và issuer contract version.

## 21. Tổng kết

Một bộ token mẫu được kiểm soát là **bộ hợp đồng kiểm thử có thể tái tạo**, bao gồm token hợp lệ, token sai có chủ đích, public JWKS, introspection response và metadata snapshots. Nó giúp Resource Server phát hiện thay đổi từ issuer trước khi thay đổi đó đi vào production.

Cần nhớ:

- **JWT fixture phải có chữ ký thật** nếu muốn test decoder; payload JSON hoặc `mockJwt()` chỉ kiểm tra được một phần.
- **Test keys chỉ dùng cho test**; không lưu hoặc phát lại bearer credentials production.
- **Issuer, audience, algorithm, key ID, time, type và claims** đều có thể thay đổi và cần fixtures riêng.
- **JWKS rotation** cần kiểm tra overlap giữa key cũ/mới, cache refresh và unknown key.
- **Opaque introspection** cần phân biệt `active:false` với lỗi client authentication, rate limit và timeout.
- **OIDC discovery** phải giữ exact issuer và trusted JWKS URI; không tự tin metadata/URL tùy ý.
- **Authentication và authorization** là hai tầng khác nhau; token valid vẫn có thể bị 403 do scope/tenant/ACL.
- **Issuer migration** cần allowlist, compatibility tests, overlap, identity mapping và sunset.
- CI nên chạy fixtures deterministic mỗi pull request, còn sandbox contract tests xác nhận integration thật theo lịch/release.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Multi-tenancy for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — JwtTimestampValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html)
- [Spring Security API — NimbusJwtEncoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html)
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)

