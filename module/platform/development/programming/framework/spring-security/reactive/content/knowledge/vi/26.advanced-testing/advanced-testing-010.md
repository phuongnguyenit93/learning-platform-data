# Giả lập JWK endpoint, introspection endpoint và lỗi nhà cung cấp danh tính

> **Phạm vi:** kiểm thử chuyên sâu một **Spring Security WebFlux Resource Server** nhận Bearer token, trong đó hệ thống xác thực dựa vào JWK Set (JWT) hoặc OAuth 2.0 Token Introspection (opaque token). Mục tiêu là kiểm tra cả giao tiếp HTTP với Identity Provider (IdP) lẫn hành vi bảo mật khi IdP phản hồi lỗi, chứ không chỉ giả lập người dùng đã đăng nhập.

## 1. Mục tiêu học tập và ranh giới

Sau bài này, bạn có thể:

1. Phân biệt kiểm thử **ủy quyền** bằng `mockJwt()` / `mockOpaqueToken()` với kiểm thử **xác thực thực tế** dùng JWT ký thật, HTTP JWK Set và HTTP introspection.
2. Dựng một IdP giả lập chạy trên cổng ngẫu nhiên, công bố khóa công khai JWK, phản hồi introspection và ghi nhận request đến từ Resource Server.
3. Kiểm thử JWT hợp lệ, chữ ký sai, `kid` không khớp, issuer/audience/thời hạn không hợp lệ và kịch bản đổi khóa.
4. Kiểm thử opaque token `active=true/false`, scope, client authentication và các lỗi 401/429/5xx/timeout từ introspection endpoint.
5. Chứng minh hệ thống **fail closed**: lỗi xác thực hoặc không thể xác minh token không được làm lộ tài nguyên; phân biệt lỗi token với sự cố hạ tầng và quan sát được nguyên nhân.

**Lưu ý về phiên bản:** ví dụ Java 17+ dùng JUnit 5, Reactor Test, `MockWebServer` 4.x và các API Reactive của Spring Security 6.5. Với Spring Security 7, hãy đối chiếu chữ ký API khi nâng cấp. Đây là bài về *Resource Server* WebFlux, không phải đăng nhập OAuth2 Login hoặc Servlet `HttpSecurity`.

## 2. Cơ chế nền tảng

### 2.1. JWT và JWK Set

Một JWT được ký bằng khóa riêng, mang header như `{"alg":"RS256","kid":"key-a"}` và claims như `iss`, `sub`, `aud`, `exp`, `nbf`, `scope`. Resource Server tải **JWK Set** (JWKS) chứa khóa **công khai** từ endpoint IdP, chọn khóa theo `kid`/thuật toán và xác minh chữ ký cục bộ. Ví dụ phản hồi rút gọn:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-a",
      "alg": "RS256",
      "n": "<modulus-base64url>",
      "e": "AQAB"
    }
  ]
}
```

`n` và `e` ở đây là ký hiệu minh họa, **không phải JWK hợp lệ để chạy**. Test thực tế phải sinh RSA key pair, ký token bằng private key và chỉ công bố public JWK. Đừng đưa `d`, `p`, `q` hoặc private JWK vào HTTP response.

Luồng:

```text
Client -- Authorization: Bearer <signed-JWT> --> WebFlux Resource Server
                  |                                |
                  |                       ReactiveJwtDecoder
                  |                                |
                  |                        GET /jwks (khi cần)
                  |                                v
                  |                         IdP giả lập
                  |                        200 { "keys": [...] }
                  |                                |
                  +--> xác minh chữ ký, alg, exp, nbf, iss, aud theo cấu hình
                                                   |
                                        Authentication + authorities
                                                   |
                                         SecurityWebFilterChain
```

Các điểm dễ nhầm:

- `jwk-set-uri` chỉ cho biết nơi lấy khóa; nếu tự tạo `NimbusReactiveJwtDecoder` bằng builder, hãy cấu hình validator `iss`/`aud` cần thiết. Đừng giả định chỉ có chữ ký hợp lệ là đủ.
- Dùng đồng thời `issuer-uri` và `jwk-set-uri` trong cấu hình Spring Boot giúp chỉ định JWKS trực tiếp mà vẫn kiểm tra `iss` theo cấu hình chuẩn.
- JWK Set có thể được cache; việc gọi lại endpoint phụ thuộc cơ chế cache, phiên bản và key selection. Không khẳng định “mỗi request đều GET /jwks”.
- JWT hợp lệ về chữ ký vẫn có thể bị từ chối vì `exp`, `nbf`, `iss`, `aud` hay thiếu scope. Kiểm tra xác thực và ủy quyền là hai phép kiểm khác nhau.

### 2.2. Opaque token và introspection

Opaque token thường không mang thông tin mà Resource Server tự xác minh được. Mỗi lần cần xác minh (trừ khi ứng dụng chủ động thêm cache), `ReactiveOpaqueTokenIntrospector` gửi HTTP POST tới IdP theo RFC 7662, thường dùng Basic authentication cho client:

```http
POST /introspect HTTP/1.1
Authorization: Basic <base64(client-id:client-secret)>
Content-Type: application/x-www-form-urlencoded

token=opaque-123
```

Phản hồi thành công và còn hiệu lực:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "lesson:read",
  "client_id": "resource-server-client",
  "token_type": "Bearer"
}
```

Token hết hiệu lực hoặc đã bị thu hồi:

```json
{"active": false}
```

`active=false` khác với IdP đang hỏng: trường hợp đầu là một kết luận xác thực hợp lệ; trường hợp sau là **không thể xác minh được**. Theo mặc định, scope `lesson:read` thường ánh xạ thành authority `SCOPE_lesson:read`. Đừng tự coi HTTP 200 là “token hợp lệ” nếu body báo `active=false`.

### 2.3. Chọn lớp kiểm thử đúng

| Lớp | Cách làm | Điều được chứng minh | Điều chưa được chứng minh |
| --- | --- | --- | --- |
| Ủy quyền nhanh | `WebTestClient.mutateWith(mockJwt())` hoặc `mockOpaqueToken()` | Rule `hasAuthority`, `hasRole`, mapping principal, 403 khi thiếu quyền | HTTP JWKS/introspection, chữ ký, parser, credential, timeout |
| Contract của adapter | `MockWebServer` + decoder/introspector thật + `StepVerifier` | Cách Spring gửi request, phân tích response, nhận/loại token, xử lý lỗi upstream | Mọi filter/controller trong ứng dụng |
| Tích hợp WebFlux | `@SpringBootTest` + `WebTestClient` + IdP stub | HTTP 401/403/2xx, `SecurityWebFilterChain`, property binding, behavior fail closed | Mức tương thích 100% với IdP thật |
| Tương thích môi trường | IdP thật trong staging/Testcontainers nếu có | Contract đặc thù của nhà cung cấp, TLS, metadata, chính sách thực tế | Không thích hợp làm nền cho mọi unit test |

`mockJwt()` và `mockOpaqueToken()` rất hữu ích nhưng đi vòng qua bước kiểm tra token từ network. Dùng chúng cho authorization; với đề bài **giả lập endpoint**, cần ít nhất một test đi qua decoder/introspector thật.

## 3. Thiết lập môi trường kiểm thử

Với Gradle Groovy DSL trong dự án Spring Boot có dependency management, các dependency thường dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` cung cấp các thành phần xác thực Bearer và JWT, bao gồm hỗ trợ JOSE; `spring-boot-starter-webflux` cung cấp runtime reactive. Không hard-code URL hoặc client secret môi trường thật trong test. `MockWebServer` là HTTP stub in-process, tự cấp port trống: không cần chạy Keycloak hoặc IdP ngoài máy.

Cấu hình ứng dụng **JWT mode** khi dùng Spring Boot tự cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.test/realm
          jwk-set-uri: http://127.0.0.1:${JWK_STUB_PORT}/jwks
```

Cấu hình ứng dụng **opaque mode** trong profile/context test riêng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: http://127.0.0.1:${INTROSPECTION_STUB_PORT}/introspect
          client-id: resource-server-client
          client-secret: test-secret
```

Các placeholder `${JWK_STUB_PORT}` và `${INTROSPECTION_STUB_PORT}` chỉ minh họa việc cấp URL động; đoạn YAML không chạy độc lập nếu chưa cấp biến. Trong integration test, dùng `@DynamicPropertySource` để đưa `server.url(...).toString()` vào Spring context **trước khi tạo context**. Khi cần kiểm tra hai loại token, tách test context cấu hình `.jwt()` và `.opaqueToken()` rõ ràng; đừng giả định cả hai cùng tự kích hoạt như nhau chỉ vì khai báo hai bộ properties.

## 4. Ví dụ JUnit hoàn chỉnh: mock JWK và introspection trên HTTP thật

Tạo file `src/test/java/example/security/IdpEndpointContractTest.java`. Ví dụ này chạy độc lập như một lớp JUnit trong project có các dependencies bên trên; nó kiểm tra các component reactive thực tế mà không phụ thuộc controller của từng dự án.

```java
package example.security;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import reactor.test.StepVerifier;

import java.io.IOException;
import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class IdpEndpointContractTest {
    private MockWebServer idp;

    @BeforeEach
    void startIdp() throws IOException {
        idp = new MockWebServer();
        idp.start();
    }

    @AfterEach
    void stopIdp() throws IOException {
        idp.shutdown();
    }

    @Test
    void jwtDecoderFetchesJwkAndValidatesSignatureAndIssuer() throws Exception {
        RSAKey key = new RSAKeyGenerator(2048)
                .keyID("key-a")
                .keyUse(KeyUse.SIGNATURE)
                .generate();

        // HTTP chỉ công bố phần khóa công khai; private key chỉ dùng để ký.
        String publicJwks = new JWKSet(key.toPublicJWK()).toString();
        idp.enqueue(json(200, publicJwks));

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
                .withJwkSetUri(idp.url("/jwks").toString())
                .build();
        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer("https://idp.test/realm"));

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer("https://idp.test/realm")
                .subject("alice")
                .issueTime(Date.from(now.minusSeconds(5)))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .build();

        SignedJWT signed = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID("key-a")
                        .build(),
                claims);
        signed.sign(new RSASSASigner(key));

        StepVerifier.create(decoder.decode(signed.serialize()))
                .assertNext(jwt -> assertEquals("alice", jwt.getSubject()))
                .verifyComplete();

        RecordedRequest request = idp.takeRequest(2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/jwks", request.getPath());
    }

    @Test
    void introspectionSendsFormAndBasicAuthThenRejectsInactiveToken()
            throws Exception {
        var introspector = SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(idp.url("/introspect").toString())
                .clientId("sample-client")
                .clientSecret("sample-secret")
                .build();

        idp.enqueue(json(200,
                "{\"active\":true,\"sub\":\"alice\",\"scope\":\"lesson:read\"}"));

        StepVerifier.create(introspector.introspect("opaque-123"))
                .assertNext(principal -> {
                    assertEquals("alice", principal.getAttribute("sub"));
                    assertTrue(principal.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("SCOPE_lesson:read")));
                })
                .verifyComplete();

        RecordedRequest request = idp.takeRequest(2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("POST", request.getMethod());
        assertEquals("/introspect", request.getPath());
        assertTrue(request.getHeader("Authorization").startsWith("Basic "));
        assertTrue(request.getBody().readUtf8().contains("token=opaque-123"));

        idp.enqueue(json(200, "{\"active\":false}"));

        StepVerifier.create(introspector.introspect("revoked-token"))
                .expectError()
                .verify();
    }

    @Test
    void unavailableIdpNeverCountsAsSuccessfulIntrospection() {
        var introspector = SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(idp.url("/introspect").toString())
                .clientId("sample-client")
                .clientSecret("sample-secret")
                .build();

        idp.enqueue(json(503, "{\"error\":\"temporarily_unavailable\"}"));

        StepVerifier.create(introspector.introspect("opaque-123"))
                .expectError()
                .verify();
    }

    private static MockResponse json(int status, String body) {
        return new MockResponse()
                .setResponseCode(status)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
```

Chạy riêng class bằng Gradle wrapper của dự án:

```bash
./gradlew test --tests 'example.security.IdpEndpointContractTest'
```

Trên Windows PowerShell, dùng `.\gradlew.bat test --tests 'example.security.IdpEndpointContractTest'`.

**Kết quả kỳ vọng:** ba test **PASS**. JWK test chứng minh HTTP GET được gọi và khóa công khai hợp lệ giải mã được JWT ký bằng private key tương ứng. Introspection test chứng minh HTTP POST form, Basic auth, authority từ scope và việc từ chối `active=false`. Test 503 chứng minh lỗi upstream không biến thành authenticated principal. Không có stdout cố định; báo cáo PASS/FAIL là của JUnit/Gradle và phụ thuộc kết quả chạy thực tế.

**Vì sao test dùng `StepVerifier`?** `decode()` và `introspect()` là publisher `Mono`. Test subscribe thực sự và phân biệt `onNext/onComplete` với `onError`. Chỉ tạo `Mono` mà không subscribe sẽ không thực hiện HTTP; gọi `.block()` trong handler WebFlux production là sai vì có thể chặn event-loop, nhưng dùng `StepVerifier` trong test là phù hợp.

## 5. Mở rộng thành kiểm thử HTTP WebFlux end-to-end

Một ứng dụng thực có thể bảo vệ API như sau:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/lessons/**")
                    .hasAuthority("SCOPE_lesson:read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    org.springframework.security.config.Customizer.withDefaults()))
            .build();
}
```

Đoạn trên là **mảnh cấu hình** cần đặt trong class `@Configuration`; để test opaque token, trong context riêng thay `.jwt(...)` bằng `.opaqueToken(Customizer.withDefaults())`. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `@AutoConfigureWebTestClient`, gửi JWT ký thật bằng `WebTestClient`:

```java
// Minh họa phần thân một test; signedJwt phải được sinh từ test fixture.
webTestClient.get()
        .uri("/api/lessons/42")
        .headers(headers -> headers.setBearerAuth(signedJwt))
        .exchange()
        .expectStatus().isOk();
```

Ứng dụng cần có route `/api/lessons/42`; ví dụ này **không phải một class chạy độc lập**. Các điểm xác minh:

1. Một JWT ký đúng, claim hợp lệ và `SCOPE_lesson:read` → response 2xx theo API.
2. JWT hợp lệ nhưng thiếu scope cần thiết → HTTP 403 (đã xác thực, không đủ quyền).
3. JWT hết hạn/sai chữ ký/sai issuer → HTTP 401 khi dùng default bearer authentication entry point.
4. Opaque token `active=false` → HTTP 401.
5. IdP HTTP 5xx, bị ngắt kết nối hoặc timeout → không có request nào được coi là authenticated; status cụ thể có thể là 401 hoặc 5xx tùy cách exception được chuyển đổi và handler đã cấu hình. Chốt chính sách response của ứng dụng rồi assert **status và error body đã quan sát thực tế**, tránh đoán cố định từ test component.

Phải bắt đầu IdP stub trước khi Spring context đọc `@DynamicPropertySource`, và dừng sau khi test context hoàn tất. Dùng port ngẫu nhiên giúp tránh xung đột CI. Nếu chỉ kiểm thử authorization mà không cần remote verification, có thể dùng `SecurityMockServerConfigurers.mockJwt()`/`mockOpaqueToken()` với `WebTestClient` đã tích hợp Spring Security; khi đó **không thể** dùng `verify` số request JWK/introspection như bằng chứng.

## 6. Ma trận tình huống cần kiểm tra

### 6.1. JWK endpoint và JWT

| Tình huống | Stub hoặc token đầu vào | Kết quả cần chứng minh |
| --- | --- | --- |
| Thành công | JWKS 200 có RSA public key `kid=key-a`, JWT RS256 ký bằng private key tương ứng | `decode()` trả `Jwt`; claim và authority được kiểm tra đúng |
| Chữ ký bị sửa | Giữ chữ ký cũ rồi đổi payload, hoặc ký bằng private key khác với JWK công bố | `decode()` phát `onError`; API không cấp quyền |
| Không tìm thấy `kid` | Header `kid=key-b`, JWKS chỉ có `key-a` | Không chấp nhận token; có thể có thao tác refresh JWK tùy cache |
| Thuật toán không được tin cậy | JWT sử dụng alg khác allowlist, ví dụ không cho phép `HS256` | Từ chối; không tin `alg` chỉ vì nó có trong header |
| Claim thời gian | `exp` quá khứ, `nbf` tương lai, kể cả chênh lệch đồng hồ | Từ chối theo validator và clock skew đã cấu hình |
| Claim nguồn/đích | `iss` khác trusted issuer, hoặc `aud` không chứa API mong đợi | Từ chối khi có validator tương ứng; đừng quên khai báo audience validator |
| JWKS hỏng | HTTP 200 nhưng JSON sai, thiếu `keys`, RSA modulus sai | Lỗi giải mã/JWK; không xác thực |
| IdP unavailable | 500/503, ngắt kết nối, DNS lỗi, timeout | Không có đường bypass để cấp quyền; ghi nhận loại lỗi |
| Đổi khóa | JWKS từ `key-a` sang `key-b`; JWT có `kid=key-b` | Test qua kiểm soát cache/decoder để xác nhận refresh và token mới |
| Nhiều khóa | JWKS chứa `key-a` và `key-b` | Đúng `kid`, `kty`, `use`, `alg`; token ký sai khóa bị loại |

**Rotation có bẫy cache:** không viết test phụ thuộc “GET /jwks phải đúng hai lần”. Khi muốn chứng minh refresh, dùng một decoder/context mới hoặc cơ chế cache kiểm soát được, phát JWT có `kid` mới và kiểm tra kết quả cũng như các request thực sự ghi nhận. Đừng tắt xác minh chữ ký để test rotation dễ hơn.

**Audience:** trường `aud` không tự nhiên được kiểm tra chỉ nhờ JWKS URI. Trong Spring Boot, có thể cấu hình `spring.security.oauth2.resourceserver.jwt.audiences` nếu phiên bản hỗ trợ; với decoder tự tạo, thêm `OAuth2TokenValidator<Jwt>` cho audience và kết hợp với validator mặc định/issuer.

### 6.2. Introspection endpoint và opaque token

| Tình huống | Phản hồi giả lập | Điều kiểm tra |
| --- | --- | --- |
| Token còn hiệu lực | `200 {"active":true,"sub":"alice","scope":"lesson:read"}` | Principal và authority đúng |
| Token đã thu hồi | `200 {"active":false}` | Xác thực bị từ chối |
| Thiếu quyền truy cập | `active=true` nhưng thiếu scope | Xác thực có thể thành công; API bảo vệ trả 403 |
| Thông tin client sai | `401` hoặc `403` từ introspection | Xử lý như lỗi credential/IdP, không coi là token active |
| Quá tải | `429` và có thể `Retry-After` | Không bypass; kiểm tra timeout/retry có giới hạn |
| Sự cố máy chủ | `500`, `502`, `503` | Không xác thực thành công; lỗi được phân loại/quan sát |
| Response sai schema | JSON không hợp lệ, thiếu `active`, sai kiểu dữ liệu, sai content type | Không âm thầm coi token hợp lệ |
| Đường truyền chậm | Stub delay vượt ngưỡng đã cấu hình | Hoàn tất bằng timeout hữu hạn; không treo test vô thời hạn |
| Credentials/encoding | Stub ghi lại `Authorization`, form `token` và `Content-Type` | POST đúng định dạng, Basic dùng test secret; tránh ghi log secret |
| Token chứa ký tự đặc biệt | Ví dụ token có `+`, `/`, `=` | Dữ liệu form URL-encoded đúng; IdP nhận token nguyên nghĩa |

Một response 401 **từ IdP** không đồng nghĩa 401 **từ API của bạn**: đây là hai HTTP hop và có thể được ánh xạ khác nhau. Quan sát ngoại lệ tại introspector, rồi kiểm tra status trên `WebTestClient` riêng. Tránh dùng `onErrorReturn(principalAdmin)` hoặc cache mặc định “cho qua khi lỗi” vì tạo lỗ hổng fail-open.

## 7. Chủ động giả lập lỗi nhà cung cấp danh tính

Có ba nhóm cần phân biệt:

1. **Token invalid/revoked:** IdP hoạt động và đưa kết luận token không hợp lệ; phần mềm trả lời xác thực thất bại.
2. **IdP/transport failure:** 5xx, HTTP 429, DNS/TLS, connection reset, timeout; Resource Server không thể hoàn tất xác minh. Phải chặn truy cập và có log/metric phân loại, tránh lộ token hoặc credentials.
3. **Configuration/protocol failure:** sai `issuer-uri`, JWKS sai định dạng, thiếu public key, sai mTLS/client secret, JSON schema sai; cần báo rõ cho vận hành, không “tự sửa” bằng cách bỏ validator.

Dùng `MockWebServer.enqueue()` để xếp response theo thứ tự, hoặc WireMock mappings theo URL/method/body khi có nhiều route. Ví dụ với `MockWebServer` (đoạn ghép vào method test tương ứng):

```java
idp.enqueue(new MockResponse()
        .setResponseCode(503)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"error\":\"temporarily_unavailable\"}"));

idp.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"active\":false}"));
```

Đây là **hai response tuần tự**; chỉ dùng chung một server khi biết thứ tự hai request trong test. Để tránh test flaky khi chạy song song, mỗi test tạo server độc lập như ví dụ JUnit ở trên. Muốn mô phỏng timeout, dùng phản hồi có delay dài hơn **timeout network cấu hình chủ động trên WebClient/HTTP client**, rồi đặt timeout tổng cho test; không lấy timeout mặc định dài của framework làm tiêu chí.

**Retry và circuit breaker:** chỉ thêm khi thiết kế vận hành yêu cầu. Introspection có thể được gọi nhiều lần nếu retry; cần giới hạn số lần, backoff và ngân sách thời gian. Không tự động retry tất cả lỗi HTTP hoặc tạo “fallback authenticated”. Với JWKS, cache có thể giúp tiếp tục xác minh token đã có khóa tin cậy khi IdP tạm thời lỗi, nhưng key mới chưa tải được không nên được chấp nhận. Kiểm tra behavior thực tế của thư viện và chính sách cache thay vì giả định.

## 8. Xác minh điều quan trọng nhất: fail closed và không rò rỉ dữ liệu

Trong mỗi kịch bản lỗi, nên assert đủ ba tầng:

- **Auth result:** không có `Authentication` hợp lệ khi chữ ký sai/`active=false`/IdP không thể xác minh; API không trả dữ liệu được bảo vệ.
- **HTTP contract:** kiểm tra mã trạng thái, `WWW-Authenticate` khi phù hợp, response body không chứa token, client secret, private key hoặc stacktrace.
- **Observability:** phân biệt invalid token, missing scope, upstream 401/403, upstream 429/5xx và timeout bằng logger/metric an toàn; correlation ID cho phép truy vết mà không log raw Bearer token.

Không dùng production credential, private signing key hoặc token người dùng thật trong fixture. Mock server chỉ công bố public JWK. Với HTTP introspection, việc kiểm tra Basic header trong test có thể so sánh với giá trị tạo từ **test credentials**, nhưng không in header ra console hoặc báo cáo CI.

Khi test ký JWT, cố định key pair theo fixture hoặc sinh trong mỗi test để độc lập; đồng thời dùng `Instant.now()` cùng biên thời gian đủ rộng (ví dụ ± vài phút) để tránh fail do thời gian chạy. Kịch bản clock skew nên có test riêng và đồng hồ điều khiển được. Với CI song song, đừng chia sẻ `MockWebServer`/response queue giữa các test không đồng bộ.

## 9. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `mockJwt()` rồi tuyên bố “đã test JWKS” | Chưa có HTTP GET hay xác minh RSA | Tạo JWT ký thật + decoder thật + public JWKS stub |
| Trả placeholder `n` trong JWK | JSON có vẻ đúng nhưng khóa không thể dùng | Sinh `RSAKey` thực và gọi `toPublicJWK()` |
| Chỉ kiểm tra HTTP 200 của introspection | `active=false` vẫn có 200 | Kiểm tra body và `StepVerifier` error |
| Dùng API servlet `JwtDecoder`, `HttpSecurity` | Không phản ánh luồng WebFlux | Dùng `ReactiveJwtDecoder`, `ServerHttpSecurity`, `WebTestClient` |
| Quên issuer/audience validator khi tạo decoder thủ công | Token ký đúng nhưng sai đối tượng có thể lọt | Gắn validator một cách tường minh |
| Assert số GET JWKS cố định | Cache/key rotation tạo test flaky | Kiểm tra hành vi xác minh; kiểm soát cache khi test refresh |
| Trộn cả JWT và opaque trong một context không chủ đích | Đang test nhầm authentication manager | Chia context hoặc cấu hình filter chain rõ ràng |
| `Mono` không được subscribe | Không có request HTTP nào xảy ra | Dùng `StepVerifier` hoặc `WebTestClient.exchange()` |
| Coi timeout/503 là “anonymous nhưng cho qua” | Dễ fail-open và rò tài nguyên | Từ chối truy cập, phân loại lỗi và giám sát |
| Ghi token/client secret vào test log | Rò credential trong CI | Redact log, fixture giả, assert nội bộ |

## 10. Checklist hoàn thành một bộ kiểm thử đáng tin cậy

- [ ] Có ít nhất một JWT ký thật và public JWKS hợp lệ; xác minh chữ ký, `kid` và issuer.
- [ ] Có case chữ ký sai và token hết hạn; không trả quyền truy cập.
- [ ] Có một case key rotation hoặc JWK `kid` mismatch, với chính sách cache được nêu rõ.
- [ ] Có POST introspection thực tế, kiểm tra form/Basic authentication và `active=true/false`.
- [ ] Có case scope đúng/sai; tách 401 (xác thực) và 403 (ủy quyền).
- [ ] Có ít nhất một 5xx và một timeout/connection error; không fail-open.
- [ ] Kiểm tra response API bằng `WebTestClient` nếu cần xác nhận filter chain end-to-end.
- [ ] Test độc lập, port ngẫu nhiên, cleanup server và không phụ thuộc IdP internet.
- [ ] Không để private key, raw token hoặc secret xuất hiện trong log, báo cáo hoặc response.

## Tài liệu tham khảo

- Spring Security — [Reactive Resource Server: JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html).
- Spring Security — [Reactive Resource Server: Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html).
- Spring Security — [Testing OAuth 2.0 với WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).

**Kết quả mong đợi:** người học có thể đưa ra bằng chứng rằng tài nguyên chỉ được truy cập khi token được xác minh đúng bằng remote JWK/introspection, còn mọi sai token hoặc sự cố IdP đều bị xử lý có kiểm soát và có thể chẩn đoán.