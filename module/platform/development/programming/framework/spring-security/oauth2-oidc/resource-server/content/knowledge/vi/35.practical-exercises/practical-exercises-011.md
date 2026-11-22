# Thử nghiệm thu hồi token, lỗi nhà phát hành và các chính sách cache

Khi triển khai **Spring Security OAuth 2.0 Resource Server**, cần xử lý đồng thời ba vấn đề dễ bị đánh đồng: token được xác minh hợp lệ, token có còn hiệu lực sau khi bị thu hồi hay không, và dữ liệu xác thực/ủy quyền được giữ trong cache bao lâu.

Một **JWT** có chữ ký đúng, issuer và audience đúng, chưa hết hạn vẫn có thể tiếp tục được Resource Server chấp nhận **sau khi Authorization Server đã nhận lệnh revoke**, nếu ứng dụng chỉ dùng JwtDecoder để xác minh cục bộ. Ngược lại, với **opaque token**, Resource Server thường gọi introspection endpoint để hỏi trạng thái `active`; nếu cache phản hồi `active=true`, trạng thái đó có thể lỗi thời sau khi token bị thu hồi.

Do vậy, thực hành phải tách riêng:

1. **Revocation:** ai gửi yêu cầu thu hồi, AS xử lý thế nào và Resource Server nhận biết khi nào?
2. **Issuer/AS failures:** token sai issuer, chữ ký hoặc audience khác với JWKS, discovery, introspection endpoint bị lỗi ra sao?
3. **Cache policies:** JWKS, introspection, denylist, tenant configuration, authorization decisions có TTL, key, capacity, invalidation và stale policy gì?

Bài học hướng dẫn xây dựng test suite từ unit test tới integration test cho Servlet và WebFlux, bao gồm cả token có chữ ký thật, HTTP introspection test server, cache được điều khiển bằng clock/ticker, event propagation và failure handling. **Không được coi mock Authentication test là bằng chứng kiểm tra chữ ký hoặc introspection thực tế.**

## 1. Bản đồ vòng đời và trách nhiệm

~~~mermaid
flowchart TD
    C[OAuth client] -->|Token request| AS[Authorization Server]
    AS -->|Access token| C
    C -->|Bearer token| RS[Resource Server]
    C -->|RFC 7009 revocation request| AS
    RS --> M{Validation strategy}
    M -->|JWT local| J[JwtDecoder: JWS + claims]
    M -->|Opaque hoặc JWT introspected| I[OpaqueTokenIntrospector]
    I --> CACHE{Positive introspection cache?}
    CACHE -->|Miss| AS2[AS introspection RFC 7662]
    CACHE -->|Hit còn hợp lệ| A[Authenticated principal]
    AS2 -->|active=true| A
    AS2 -->|active=false| X[Authentication failure]
    AS2 -->|Timeout hoặc 5xx| E[Không có kết quả xác minh]
    J -->|Valid| R{Có revocation lookup?}
    J -->|Invalid| X
    R -->|Not revoked| A
    R -->|Revoked| X
    R -->|Không có policy lookup| A
    R -->|Store error| E
    A --> Z[Scope, role, tenant, ownership]
    Z -->|Đủ quyền| OK[Cho phép]
    Z -->|Thiếu quyền| D[403 hoặc domain 404]
~~~

Lưu ý:

- **RFC 7009** mô tả request từ OAuth client tới Authorization Server để thu hồi token.
- **RFC 7662** mô tả request từ protected resource tới Authorization Server để xác định trạng thái và metadata của token.
- Revocation endpoint không phải API mà Resource Server phải gọi trong mọi request.
- Cache hit có thể nhanh hơn introspection nhưng **không chứng minh trạng thái token hiện tại của AS**.

### 1.1. Bốn khái niệm khác nhau

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Signature verification | Token có được ký bởi key đáng tin? | RS256 + public JWK |
| Claim validation | Token dành cho API này, còn hạn, do issuer hợp lệ? | iss, aud, exp, nbf |
| Revocation check | Token/grant/session đã bị AS hoặc chính sách nội bộ thu hồi? | active=false, denylist jti |
| Authorization | Principal được thao tác trên resource này? | SCOPE_orders.read và tenant_id |

Một token có thể qua ba điều kiện đầu nhưng vẫn không đủ quyền nghiệp vụ.

## 2. RFC 7009: thu hồi token

OAuth client có thể yêu cầu thu hồi token khi người dùng logout, xóa liên kết, admin thu hồi grant, tài khoản bị vô hiệu hóa hoặc credential bị lộ.

Request ví dụ:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=example-refresh-token&token_type_hint=refresh_token
~~~

Đường dẫn endpoint, client authentication và việc hỗ trợ thu hồi access token phụ thuộc Authorization Server. `token_type_hint` chỉ là gợi ý. Theo RFC 7009, kết quả thành công không được dùng để tiết lộ một token có tồn tại hay không.

### 2.1. Thành công ở revocation endpoint chưa đủ

Giả sử AS phát JWT hết hạn lúc 10:30 và nhận lệnh thu hồi lúc 10:05:

~~~text
10:00  Access JWT được cấp, exp = 10:30
10:05  Client gọi revocation endpoint, AS phản hồi thành công
10:06  Resource Server nhận JWT đã phát
10:06  Chữ ký, iss, aud, exp vẫn hợp lệ
10:06  Nếu không introspect hoặc tra denylist -> token có thể vẫn qua
10:30  Token hết hạn, decoder không chấp nhận nữa
~~~

Điều này không có nghĩa decoder bị lỗi. **Xác minh chữ ký và kiểm tra revocation là hai cơ chế khác nhau.**

### 2.2. Revocation refresh token và access token

Thu hồi refresh token thường ngăn việc tiếp tục lấy access token mới từ grant đó, nhưng không bảo đảm access token đang lưu hành bị vô hiệu ngay lập tức. Việc revoke access token có được hỗ trợ và ảnh hưởng thế nào đến các token liên quan tùy AS policy.

Vì vậy test cần xác nhận:

- Token được revoke là access token hay refresh token?
- AS có revoke toàn grant/token family không?
- Access token đang lưu hành còn hợp lệ trong bao lâu?
- Các Resource Servers nhận trạng thái mới bằng cách nào?
- Có cache nào làm kéo dài thời gian thu hồi?

## 3. Chọn chiến lược revocation

| Chiến lược | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| JWT ngắn hạn | Chờ exp; refresh token được quản lý tập trung | Ít network mỗi request | Cửa sổ token cũ còn được dùng |
| JWT + introspection | AS trả active trên request | Trạng thái tập trung | Phụ thuộc AS latency/availability |
| JWT + denylist jti | RS kiểm tra state revoked | Thu hồi có thể nhanh | Cần shared state, TTL và fail-closed |
| JWT + session/token version | So khớp version của user/grant | Hữu ích khi revoke theo phiên | Cần lookup/invalidation |
| Opaque introspection | AS kiểm active và trả metadata | Policy tập trung | Network dependency |
| Event-driven revocation | AS gửi revoke event tới nodes | Giảm request liên tục tới AS | Event loss, lag, multi-node consistency |

Chọn giải pháp theo **revocation SLA**: thời gian tối đa từ lúc AS thu hồi token đến khi mọi Resource Server từ chối token đó. Nếu chỉ dùng JWT exp ngắn, SLA không thể nhỏ hơn cửa sổ còn lại của access token nếu không có cơ chế bổ sung.

## 4. Opaque token và JWT introspection

Spring Security hỗ trợ opaque token bằng **OpaqueTokenIntrospector** ở Servlet và **ReactiveOpaqueTokenIntrospector** ở WebFlux.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Với Servlet:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

Introspection response:

~~~json
{
  "active": true,
  "iss": "https://idp.example.com",
  "sub": "alice",
  "client_id": "orders-client",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Spring Security có thể ánh xạ scope thành `SCOPE_orders.read` và `SCOPE_orders.write`; authorization tiếp tục áp dụng rule của Resource Server.

### 4.1. Active=false và thiếu scope khác nhau

| Kết quả AS | Authentication | Authorization |
|---|---|---|
| active=false | Thất bại | Không tới bước xét quyền |
| active=true, đủ scope | Thành công | Có thể cho phép |
| active=true, thiếu scope | Thành công | Từ chối, thường 403 |
| active=true, sai tenant | Thành công | Từ chối theo tenant policy |
| Introspection timeout | Không có kết quả xác minh | Không được tạo principal active |
| Introspection 5xx | Không có kết quả xác minh | Không được fail-open |

### 4.2. Có thể introspect cả JWT

Spring Security Opaque Token support không yêu cầu token thực sự có định dạng opaque; nó chuyển nguyên Bearer token tới introspection endpoint. Vì thế một JWT cũng có thể được xác minh qua AS nếu security architecture cần kiểm trạng thái thu hồi tập trung.

Khi đó principal thường là **OAuth2AuthenticatedPrincipal** trong **BearerTokenAuthentication**, không phải **Jwt** trong **JwtAuthenticationToken**. Test controller phải dùng Authentication type tương ứng.

## 5. Kiểm thử bằng Authentication giả lập: phạm vi và giới hạn

MockMvc có `jwt()` và `opaqueToken()`; WebTestClient có `mockJwt()` và `mockOpaqueToken()`. Các helper này cung cấp Authentication giả lập vào test context. Chúng hữu ích cho:

- Scope và role authorization.
- Kiểm tra controller đọc sub, tenant_id và other claims.
- Kiểm tra ownership/resource permissions.
- Method security.
- Kiểm tra 403 khi principal thiếu authority.

Ví dụ:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

**Helper này không gọi JwtDecoder**, không xác minh chữ ký và không tra revocation store nếu revocation được tích hợp trong decoder.

Tương tự:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

**mockOpaqueToken() không gọi ReactiveOpaqueTokenIntrospector**. Không dùng test này để tuyên bố revocation hoặc introspection HTTP đã hoạt động.

## 6. Kiểm thử JWT có chữ ký thật

Để test signature, issuer, audience, expiration và custom revocation wrapper, tạo JWT bằng test private key và gửi qua Authorization Bearer tới SecurityFilterChain thật.

### 6.1. Tạo RSA test key

~~~java
RSAKey rsaKey = new RSAKeyGenerator(2048)
    .keyID("test-rsa-1")
    .generate();

JWKSource<SecurityContext> signingSource =
    new ImmutableJWKSet<>(new JWKSet(rsaKey));

JwtEncoder encoder = new NimbusJwtEncoder(signingSource);

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(rsaKey.toRSAPublicKey())
    .build();
~~~

Private key chỉ ở test encoder; Resource Server nhận public key. Không tái sử dụng production keys.

### 6.2. Cấu hình issuer và audience validators

~~~java
String issuer = "https://issuer.test";
String audience = "orders-api";

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains(audience)
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Audience does not match resource",
                null
            )
        );

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    )
);
~~~

Giữ default validators để kiểm thời gian, issuer và những mặc định khác của phiên bản Spring Security. Không thay toàn bộ chain bằng một validator chỉ kiểm aud.

### 6.3. Ký JWT có jti

~~~java
Instant now = Instant.now();

JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer("https://issuer.test")
    .subject("alice")
    .audience(List.of("orders-api"))
    .issuedAt(now.minusSeconds(10))
    .expiresAt(now.plusSeconds(300))
    .id("jti-test-001")
    .claim("scope", "orders.read")
    .claim("tenant_id", "tenant-a")
    .build();

JwsHeader header = JwsHeader
    .with(SignatureAlgorithm.RS256)
    .keyId("test-rsa-1")
    .build();

String token = encoder.encode(
    JwtEncoderParameters.from(header, claims)
).getTokenValue();
~~~

Gửi token thực qua filter chain:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
    .andExpect(status().isOk());
~~~

Test này cần MockMvc được gắn Spring Security filters. Không gọi `.with(jwt())` trong request nếu muốn decoder và revocation check thực sự chạy.

### 6.4. Negative test cases

| Token test | Kết quả |
|---|---|
| Key đúng, issuer/audience/time đúng | Authenticated |
| Token ký bằng private key khác | 401, signature invalid |
| Issuer claim sai | 401, issuer validator |
| Audience claim sai | 401, audience validator |
| Expired | 401 |
| nbf ở tương lai ngoài clock skew | 401 |
| Thuật toán ngoài allowlist | Từ chối |
| Có chữ ký hợp lệ nhưng thiếu scope | Authenticated, 403 nếu policy yêu cầu scope |

Dùng key pair thứ hai để tạo token sai chữ ký; không chỉ thay một ký tự trong token rồi khẳng định đã test một thuật toán signature cụ thể.

## 7. Test JWT revocation bằng jti denylist

Giả sử hệ thống duy trì state:

~~~text
revoked:<issuer-id>:<jti>
~~~

Cặp issuer+jti giúp không nhầm token IDs giữa các issuers. Chỉ đọc jti **sau khi JWT đã được decoder xác minh**.

### 7.1. Bọc decoder trong Servlet

~~~java
interface RevocationStore {
    boolean isRevoked(String issuer, String jti);
}

JwtDecoder revocationAwareDecoder(
        JwtDecoder delegate,
        RevocationStore store) {

    return compactToken -> {
        Jwt jwt = delegate.decode(compactToken);

        if (jwt.getIssuer() == null || jwt.getId() == null) {
            throw new JwtException("Required revocation claims are missing");
        }

        String issuer = jwt.getIssuer().toString();
        if (store.isRevoked(issuer, jwt.getId())) {
            throw new JwtException("Token has been revoked");
        }

        return jwt;
    };
}
~~~

Ở đây `store.isRevoked` phải có semantics phân biệt **false đã kiểm và chưa revoke** với **store unavailable**. Không trả false khi timeout nếu fail-closed là yêu cầu bảo mật.

### 7.2. WebFlux cần store reactive

~~~java
interface ReactiveRevocationStore {
    Mono<Boolean> isRevoked(String issuer, String jti);
}

ReactiveJwtDecoder revocationAwareDecoder(
        ReactiveJwtDecoder delegate,
        ReactiveRevocationStore store) {

    return compactToken -> delegate.decode(compactToken)
        .flatMap(jwt -> {
            if (jwt.getIssuer() == null || jwt.getId() == null) {
                return Mono.error(
                    new JwtException("Required revocation claims are missing")
                );
            }

            return store.isRevoked(
                    jwt.getIssuer().toString(),
                    jwt.getId()
                )
                .flatMap(revoked ->
                    revoked
                        ? Mono.error(new JwtException("Token has been revoked"))
                        : Mono.just(jwt)
                );
        });
}
~~~

Không dùng `.block()` hoặc `onErrorReturn(false)` trong authentication flow. Nếu store lỗi, authentication không được mặc định cho qua.

### 7.3. Test denylist

1. JWT ký hợp lệ, chưa có jti trong store → được authenticated.
2. Ghi issuer+jti vào store → cùng token bị từ chối ở request sau.
3. Token của issuer khác có cùng jti không bị liên đới nếu issuer hợp lệ riêng.
4. JWT thiếu jti → từ chối nếu policy yêu cầu jti bắt buộc.
5. Store timeout → không tạo Authentication thành công.
6. Denylist entry phải sống tới exp cộng clock-skew margin.
7. Cache eviction không được làm token revoked được chấp nhận lại.

**Không dùng jwt()/mockJwt() cho các test này**, vì helper không chạy decoder wrapper.

## 8. Thử nghiệm introspection HTTP thực tế

Để kiểm code thật gọi Authorization Server đúng cách, sử dụng một HTTP test server như MockWebServer hoặc WireMock. SpringOpaqueTokenIntrospector phải được cấu hình trỏ tới endpoint cục bộ.

### 8.1. Servlet introspector test

~~~java
OpaqueTokenIntrospector introspector =
    SpringOpaqueTokenIntrospector
        .withIntrospectionUri(
            mockWebServer.url("/introspect").toString()
        )
        .clientId("test-resource-server")
        .clientSecret("test-client-secret")
        .build();
~~~

Gắn vào HttpSecurity:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        OpaqueTokenIntrospector introspector) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector))
        )
        .build();
}
~~~

### 8.2. Active=true

~~~java
mockWebServer.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("""
        {
          "active": true,
          "sub": "alice",
          "scope": "orders.read",
          "tenant_id": "tenant-a"
        }
        """));

mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-opaque-token"))
    .andExpect(status().isOk());
~~~

Kiểm HTTP exchange:

~~~java
RecordedRequest request = mockWebServer.takeRequest(
    1, TimeUnit.SECONDS
);

assertThat(request).isNotNull();
assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/introspect");
assertThat(request.getHeader("Authorization")).startsWith("Basic ");
assertThat(request.getBody().readUtf8())
    .contains("token=test-opaque-token");
~~~

Đây là integration test với HTTP client thực sự của introspector nhưng dùng test AS response. Nó không khẳng định Authorization Server production hoạt động giống vậy.

### 8.3. Active=false

~~~java
mockWebServer.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"active\":false}"));

mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer revoked-token"))
    .andExpect(status().isUnauthorized());
~~~

Không có Authentication thành công, controller không được thực thi.

### 8.4. Active=true nhưng thiếu scope

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.write"
}
~~~

GET /api/orders yêu cầu SCOPE_orders.read thường trả 403. Không gộp trường hợp này vào test inactive token.

### 8.5. Reactive introspection

WebFlux dùng:

~~~java
ReactiveOpaqueTokenIntrospector introspector =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(
            mockWebServer.url("/introspect").toString()
        )
        .clientId("test-resource-server")
        .clientSecret("test-client-secret")
        .build();
~~~

Gắn vào SecurityWebFilterChain rồi gửi:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("test-opaque-token"))
    .exchange()
    .expectStatus().isOk();
~~~

Để khẳng định HTTP introspection thực sự được gọi, kiểm RecordedRequest của test server. Không dùng mockOpaqueToken() trên request này.

## 9. Kiểm thử RFC 7009 end-to-end

Một integration test với Authorization Server sandbox có thể:

1. Tạo user/client/grant trong test environment.
2. Xin access token và xác minh request Resource Server thành công.
3. Gọi revocation endpoint với token tương ứng.
4. Dùng cùng token gọi lại Resource Server.
5. Đo thời gian cho tới khi Resource Server từ chối.
6. Lặp trên nhiều replicas.
7. So sánh worst-case với revocation SLA.
8. Cleanup client/grant/token test.

~~~mermaid
sequenceDiagram
    participant T as Test client
    participant AS as Authorization Server
    participant RS as Resource Server
    T->>AS: Request test access token
    AS-->>T: Access token
    T->>RS: GET /api/orders + Bearer
    RS-->>T: 200
    T->>AS: POST /revoke (RFC 7009)
    AS-->>T: Revocation response
    T->>RS: Same Bearer token
    RS->>AS: Introspection hoặc revocation state lookup
    AS-->>RS: inactive / revoked
    RS-->>T: 401
~~~

Trong kiến trúc chỉ dùng JWT local validation không có revocation lookup, bước cuối có thể tiếp tục được chấp nhận cho tới exp. Test phải mô tả đúng policy, không coi 401 tức thời là behavior mặc định của JwtDecoder.

## 10. Issuer validation và lỗi Authorization Server

Một issuer sai khác với một issuer không truy cập được.

| Tình huống | Ý nghĩa | Security outcome |
|---|---|---|
| JWT malformed | Không parse được token | Không authenticated |
| Signature sai | Không được ký bởi key được tin | Không authenticated |
| Issuer sai | Issuer claim không khớp trusted issuer | Không authenticated |
| Audience sai | Token dành cho resource khác | Không authenticated |
| Expired / nbf | Time constraints sai | Không authenticated |
| JWKS HTTP 404/5xx | Không tải được key cần thiết | Không bỏ signature verification |
| JWKS timeout | Key retrieval failure | Không tin key chưa được xác minh |
| Metadata discovery sai | Không có issuer/JWKS config hợp lệ | Không tự tạo trust từ input request |
| Introspection active=false | Token inactive | Authentication failure |
| Introspection 401/403 | Client authentication/configuration lỗi | Không tạo principal active |
| Introspection timeout/5xx | AS/network unavailable | Không fail-open |
| Tenant registry lỗi | Không xác định trust configuration | Không fallback sang tenant khác |

### 10.1. Issuer mismatch

Ví dụ Resource Server tin `https://id-a.example.com`, nhưng JWT có `iss=https://id-b.example.com`. Dù một key khác có thể xác minh chữ ký, token vẫn phải bị từ chối theo issuer/audience policy của API.

Trong multi-tenant, issuer trong JWT chưa xác minh chỉ có thể là **routing hint** vào trusted issuer registry. Không tạo decoder/JWKS client cho issuer URL tùy ý do JWT đưa ra.

### 10.2. JWKS outage có cache hit khác cache miss

Nếu decoder đã cache public key, một JWT có thể vẫn được xác minh khi JWKS endpoint tạm thời down, theo cache policy. Nếu gặp key mới chưa được cache, decoder phải lấy public key hợp lệ; nếu không lấy được thì không thể xác minh chữ ký.

Test riêng:

- Cached key + JWKS down.
- New kid + JWKS down.
- Signature sai nhưng JWKS hoạt động.
- Issuer mismatch dù key có thể verify.
- Timeout vượt request budget.

Không coi mọi JWKS outage là token invalid, nhưng cũng không được chấp nhận token chưa xác minh để giữ availability.

### 10.3. Introspection timeout/5xx

Không có active result đáng tin thì không tạo Authentication thành công. HTTP status cụ thể có thể phụ thuộc exception translation và API error policy; test phải xác nhận không trả protected data và lỗi được phân loại đúng, thay vì giả định mọi hạ tầng timeout đều trả 401.

## 11. Key rotation và cache JWKS

JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-02",
  "typ": "JWT"
}
~~~

Rotation thông thường:

1. AS publish public key mới trên JWKS.
2. AS bắt đầu ký token mới bằng private key tương ứng.
3. Resource Servers refresh JWKS, tìm key mới.
4. AS giữ key cũ trong overlap để token chưa hết hạn còn được verify.
5. AS loại key cũ sau khi policy cho phép.

### 11.1. Test rotation

- Token ký bằng key A được chấp nhận khi JWKS chứa A.
- Publish key B, ký token bằng B; decoder refresh và chấp nhận B.
- Token ký bằng key lạ bị từ chối.
- Gỡ A và xác định thời điểm mọi nodes ngừng chấp nhận token ký bằng A.
- Unknown kid không tạo refresh storm hoặc cache entry vô hạn.
- Key của issuer A không bị dùng trong trust context issuer B.

### 11.2. Emergency key compromise

Gỡ key khỏi JWKS không bảo đảm mọi node nhận ngay. JWKS cache có thể tiếp tục giữ key bị compromise đến khi refresh/invalidation. Cần emergency plan: invalidate key cache, trigger refresh, revoke affected tokens hoặc đổi trust configuration.

Không dùng key rotation thay cho cơ chế thu hồi một token cụ thể nếu nhiều tokens dùng cùng signing key.

## 12. Phân biệt các loại cache

| Cache | Dữ liệu | Security impact |
|---|---|---|
| JWKS/key cache | Public keys theo issuer | Rotation và compromise |
| Positive introspection cache | active=true và attributes | Revocation lag |
| Negative introspection cache | active=false | Cache cardinality và stale negative |
| JWT denylist | issuer+jti hoặc token fingerprint | Nếu entry mất trước exp, revoked JWT có thể được chấp nhận |
| Tenant metadata cache | Issuer, audience, active state, policy version | Tenant disabled/policy mới không áp dụng |
| Authorization decision cache | Subject, resource, action, tenant, policy | Quyền bị thu hồi nhưng cached decision còn |
| Decoder/manager cache | Validator/key source/HTTP client object | Tái sử dụng trust configuration cũ |

**JWKS cache không phải revocation cache.** Nó chỉ phục vụ xác minh chữ ký.

### 12.1. Positive introspection cache tạo stale window

~~~text
10:00:00  Introspection -> active=true, cache TTL 10s
10:00:02  Authorization Server revoke token
10:00:05  Resource Server cache hit -> vẫn active=true
10:00:10  TTL hết hạn
10:00:11  New introspection -> active=false
~~~

Khoảng này là độ trễ thu hồi do cache. Nếu revocation SLA là tối đa 5 giây, TTL 10 giây không phù hợp nếu không có event invalidation được chứng minh đáp ứng SLA.

### 12.2. TTL positive result không vượt token exp

Một policy:

~~~text
effective cache TTL =
    min(configured positive TTL,
        remaining token lifetime,
        allowed revocation staleness)
~~~

Nếu response không có exp, cần một maximum token lifetime được bảo đảm bởi issuer contract trước khi cache positive lâu; nếu không, bỏ cache positive hoặc chọn TTL rất ngắn theo risk acceptance.

### 12.3. Negative cache không được tăng vô hạn

Cache active=false có thể giúp chống repeated invalid token requests, nhưng phải có TTL ngắn và maximum size. Không cache mọi exception HTTP như active=false; timeout là lỗi hạ tầng, không phải token state.

### 12.4. Denylist cần sống đến exp

Nếu revoked jti entry bị eviction trước exp, local JwtDecoder vẫn có thể xác minh token và revoke check trả “không có entry”, tạo acceptance trở lại. Store phải có retention theo exp cộng clock skew hoặc cơ chế khác bảo đảm token không thể được chấp nhận.

## 13. Cache key, isolation và policy version

Không dùng raw Bearer token trong Redis key, log hoặc metric label. Có thể sử dụng token fingerprint SHA-256/HMAC-SHA-256 theo threat model và quản lý key phù hợp.

Ví dụ logical keys:

~~~text
introspection : issuer-id : resource-id : token-fingerprint
revocation    : issuer-id : jti
tenant        : tenant-id : policy-revision
jwt-manager   : issuer-id : audience : validator-revision
authorization : tenant-id : subject : resource : action : policy-revision
~~~

Không dùng active result của issuer A cho issuer B hoặc reuse authorization decision qua tenants khác. Khi policy audience, role mapping hoặc tenant status đổi, tăng revision/invalidate cache.

### 13.1. Local vs distributed cache

Local Caffeine cache có latency thấp nhưng mỗi application replica giữ state riêng. Distributed cache giúp chia sẻ revocation state nhưng thêm network failure modes. Với WebFlux, không gọi blocking cache API trên Reactor event loop.

### 13.2. Event invalidation và reconciliation

Có thể phát events:

~~~text
TokenRevoked(issuerId, jti, exp)
TenantDisabled(tenantId, policyRevision)
UserDisabled(issuerId, subject, revision)
SigningKeyCompromised(issuerId, kid)
~~~

Các nodes phải invalidate cache liên quan. Event có thể bị mất; cần durable delivery, retry, idempotency và periodic reconciliation. Không coi propagation là tức thời nếu chưa đo worst-case.

## 14. Ví dụ positive introspection cache decorator

Caffeine có thể được dùng để giữ kết quả của một OpaqueTokenIntrospector sau khi delegate đã xác minh. Ví dụ Servlet:

~~~java
final class CachedOpaqueIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Clock clock;
    private final Cache<String, OAuth2AuthenticatedPrincipal> cache;

    CachedOpaqueIntrospector(
            OpaqueTokenIntrospector delegate,
            Clock clock) {
        this.delegate = delegate;
        this.clock = clock;
        this.cache = Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofSeconds(2))
            .build();
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String fingerprint = fingerprint(token);

        OAuth2AuthenticatedPrincipal cached =
            cache.getIfPresent(fingerprint);

        if (cached != null) {
            if (notExpired(cached)) {
                return cached;
            }
            cache.invalidate(fingerprint);
        }

        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        if (notExpired(principal)) {
            cache.put(fingerprint, principal);
        }

        return principal;
    }

    private boolean notExpired(OAuth2AuthenticatedPrincipal principal) {
        Object rawExp = principal.getAttribute("exp");
        Instant expiration;

        if (rawExp instanceof Instant instant) {
            expiration = instant;
        }
        else if (rawExp instanceof Number epochSeconds) {
            expiration = Instant.ofEpochSecond(epochSeconds.longValue());
        }
        else {
            return false;
        }

        return clock.instant().isBefore(expiration);
    }

    private static String fingerprint(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        }
        catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

**Đây là minh họa cache local, không phải implementation production đầy đủ.**

- TTL hai giây chỉ là một ví dụ, không phải SLA mặc định.
- Cache read tự kiểm exp nên cached principal không bị trả sau hạn.
- Trong hệ thống nhiều issuers/resources, phải thêm namespace cho fingerprint key.
- Phải có cách invalidate entry ngay khi revoke event tới nếu SLA yêu cầu.
- Không cache failed introspection, inactive result dưới dạng principal hoặc exception như positive result.
- Cần kiểm memory, concurrency, cache stampede và data protection.
- Có thể dùng HMAC fingerprint thay cho hash thuần nếu cần chống offline comparison với token có entropy không đủ.
- Cần cache result isolation nếu principal attributes chứa dữ liệu cá nhân.

Với WebFlux, dùng decorator reactive + nonblocking cache/store hoặc asynchronous loading. Không gọi `.block()` trong reactive introspector.

## 15. Test cache bằng fake clock/ticker

Đừng dùng Thread.sleep dài nếu có thể kiểm deterministic bằng fake Clock và cache Ticker.

### 15.1. Test hit/miss

~~~java
AtomicInteger calls = new AtomicInteger();

OpaqueTokenIntrospector delegate = token -> {
    calls.incrementAndGet();
    return principalWithValidExpiration(token);
};
~~~

Kịch bản:

1. Request 1: delegate được gọi, principal được cache.
2. Request 2 trong TTL: cache hit, calls không tăng.
3. Advance test ticker vượt TTL.
4. Request 3: delegate được gọi lại.
5. Delegate trả inactive: authentication thất bại.
6. Delegate timeout: không tạo positive cache entry.

### 15.2. Test revoke trong khi TTL chưa hết

~~~text
T0: active=true -> cached
T1: AS revoke token
T2: request cache hit -> có thể vẫn 200 theo stale policy
T3: revoke event arrives -> invalidate positive entry
T4: request calls AS -> active=false -> 401
~~~

Đo T4 - T1 và so sánh với revocation SLA. Nếu SLA yêu cầu tức thời, positive cache với stale window không được chấp nhận trừ khi invalidation đảm bảo giới hạn.

### 15.3. Test token exp trước cache TTL

Token exp còn một giây trong khi cache TTL hai giây. Advance clock hai giây; cache không được trả principal active sau exp dù cache entry chưa bị eviction tự động.

### 15.4. Test lỗi không bị cache

- Introspector timeout ở request 1.
- Test server phục hồi và trả active=true ở request 2.
- Request 2 phải gọi lại delegate, không dùng cached error hoặc cached principal giả.

## 16. Xử lý issuer outage và policy fail-closed

Không có một fallback chung cho tất cả lỗi. Xác định từng trường hợp:

| Sự cố | Khả năng tiếp tục | Ranh giới không được vượt |
|---|---|---|
| JWKS server down, key đã cache | Có thể tiếp tục verify bằng key còn tin | Không bỏ signature/issuer validation |
| JWKS down, cần key mới | Chưa verify được | Không coi token hợp lệ |
| Introspection down, không có cache | Không có active status | Không tạo Authentication thành công |
| Introspection down, positive cache còn TTL | Theo stale policy và revoke SLA | Không vượt exp/SLA |
| Revocation store down | Fail-closed nếu lookup bắt buộc | Không map error thành not-revoked |
| Tenant registry down | Có thể dùng trusted snapshot giới hạn tuổi hoặc từ chối | Không tạo tenant/issuer từ request tùy ý |
| Event broker down | Cache có thể stale | Cần TTL và reconciliation |
| Signing key bị compromise | Emergency invalidate/rotate | Không tiếp tục tin key vô thời hạn |

### 16.1. Không tiết lộ thông tin nội bộ

Response cho client không được chứa raw Bearer token, introspection client secret, JWKS/internal URLs, TLS credential hay stack trace. Log nội bộ nên có correlation ID, logical issuer/tenant identifier, error category và request timing.

### 16.2. 401, 403 và lỗi hạ tầng

- **401:** token không có hoặc authentication thất bại (signature, expiry, inactive).
- **403:** đã authenticated nhưng thiếu authority/role/resource permission.
- **Lỗi AS/JWKS infrastructure:** response status cụ thể phụ thuộc exception translation và API contract; không mặc định mọi timeout luôn trả 401.

Test cần khẳng định **protected data không được trả khi chưa xác minh** và lỗi được phân loại đủ rõ để vận hành.

## 17. Kiểm thử nhiều Resource Server replicas

Nếu mỗi node có cache local, revocation có thể được nhận biết ở thời điểm khác nhau.

~~~text
Node A cache expires at 10:00:05
Node B cache expires at 10:00:09
Node C cache expires at 10:00:07

10:00:03 token revoked
10:00:04 A/B/C có thể vẫn cached active=true
10:00:05 A introspects again
10:00:07 C introspects again
10:00:09 B introspects again
~~~

Test multi-node:

1. Gửi token qua từng replica để tạo cache entry.
2. Revoke token tại AS hoặc phát event.
3. Gửi lại token qua mọi replica theo chu kỳ.
4. Đo thời gian node cuối cùng bắt đầu từ chối.
5. Kiểm event broker outage và restart.
6. Kiểm một replica mới không tái tạo trạng thái active sai.
7. Kiểm issuer/tenant cache isolation.
8. So sánh worst-case lag với SLA.

Không chỉ đo trung bình hoặc một node thuận lợi.

## 18. Observability và audit

Các chỉ số có ích:

| Metric group | Mục đích |
|---|---|
| Introspection request count/latency | Đo tải AS và p95/p99 |
| Introspection active/inactive/errors | Phân biệt invalid token với AS outage |
| Positive/negative cache hit/miss | Hiểu stale window và hiệu suất |
| JWT validator failures | Signature, issuer, audience, timestamp |
| JWKS refresh and unknown kid | Key rotation, abuse, outage |
| Revocation lookup latency/errors | State store availability |
| Revocation propagation lag | Cam kết SLA đa node |
| Tenant policy revision | Phát hiện stale configuration |

Không dùng token, subject, jti hay fingerprint làm metric labels có cardinality không giới hạn. Audit log cần hạn chế dữ liệu nhạy cảm và áp retention policy.

## 19. Ma trận test tổng hợp

| Scenario | Test setup | Điều cần chứng minh |
|---|---|---|
| JWT hợp lệ | Test RSA key + decoder thật | Signature/claims hợp lệ |
| JWT sai issuer | Signed token khác iss | Issuer validation |
| JWT sai audience | Signed token khác aud | Audience validation |
| JWT sai chữ ký | Key khác | Authentication failure |
| JWT bị revoke | Valid JWT + jti denylist | Request sau revoke bị từ chối |
| Revocation store timeout | Store mock lỗi | Fail-closed |
| Opaque active=true | HTTP introspection server | Principal/authority được tạo |
| Opaque active=false | HTTP response inactive | Authentication failure |
| Opaque thiếu scope | active=true, scope sai | Authorization 403 |
| Introspection client credentials sai | AS returns 401/403 | Không có authenticated principal |
| Introspection timeout/5xx | HTTP stub fault | Không cache active/fail-open |
| JWKS down/cache hit | Key đã cache | Stale key policy đúng |
| JWKS down/cache miss | Key chưa biết | Không tin key mới chưa verify |
| Unknown kid flood | Nhiều kid ngẫu nhiên | Refresh bounded |
| Positive cache stale | Revoke trong TTL | Lag được đo |
| Cache invalidation event | Remove entry | Request gọi lại AS |
| Token exp trước TTL | Fake clock | Không dùng expired principal |
| Tenant disabled | Update policy version | Manager/cache cũ không cấp quyền |
| Multi-node revoke | Nhiều replicas | Worst-case SLA được giữ |

## 20. Anti-pattern thường gặp

**Gọi RFC 7009 rồi coi mọi JWT đã bị từ chối tức thời.** Decoder cục bộ không tự biết revoke.

**Dùng jwt() hoặc mockJwt() để test denylist nằm trong decoder.** Helper dựng Authentication, không gọi decoder.

**Dùng opaqueToken() hoặc mockOpaqueToken() để test HTTP introspection.** Helper bypass introspector.

**Cache active=true vô thời hạn hoặc lâu hơn exp.** Token hết hạn/revoked có thể được chấp nhận.

**Chỉ tối ưu cache hit ratio mà bỏ revocation SLA.** Tăng performance nhưng giảm khả năng thu hồi.

**Dùng JWKS cache để thay token revocation.** Public key không đại diện token state.

**Evict revoked jti trước exp.** Token có thể trở lại trạng thái được chấp nhận.

**Cache timeout thành active=true.** AS outage bị biến thành fail-open.

**Dùng `onErrorReturn(false)` cho denylist lookup.** Lỗi store trở thành “not revoked”.

**Không namespace cache theo issuer/resource.** Dễ trộn trust domains.

**Đọc issuer URL chưa verify rồi tạo decoder.** Có nguy cơ SSRF và mở rộng trust ngoài ý muốn.

**Không test cached-key JWKS outage riêng với cache miss.** Không nắm được behavior thật.

**Chỉ kiểm một node.** Không chứng minh cluster-wide revocation SLA.

**Log toàn bộ introspection response hoặc Bearer token.** Có thể làm lộ credential và dữ liệu cá nhân.

## 21. Quy trình triển khai và kiểm thử

**Bước 1 — Xác định token strategy.** JWT local, JWT + denylist, JWT introspection hay opaque introspection.

**Bước 2 — Ghi revocation SLA.** Thời gian tối đa mà token bị thu hồi vẫn có thể được chấp nhận.

**Bước 3 — Lập bản đồ state/caches.** JWKS, positive/negative introspection, denylist, tenant metadata, authorization decisions.

**Bước 4 — Đặt cache key/TTL/capacity.** Namespace issuer/resource/tenant; positive TTL không vượt exp hoặc SLA; denylist tới exp + skew.

**Bước 5 — Test scope/tenant policy bằng helper mock identity.** Không dùng chúng thay signature/introspection tests.

**Bước 6 — Ký JWT test và gửi Bearer qua decoder thật.** Kiểm signature, issuer, audience, exp/nbf.

**Bước 7 — Test JWT revocation lookup.** Ghi denylist, test từ chối và store failures.

**Bước 8 — Dựng introspection HTTP server.** Test active true/false, client credentials, body, timeout, 5xx, scopes.

**Bước 9 — Test cache hit/miss/invalidation.** Dùng fake clock/ticker; không phụ thuộc sleep dài.

**Bước 10 — Test key rotation/issuer outage.** Cached key, unknown kid, JWKS timeout, discovery mismatch.

**Bước 11 — Test event propagation trên nhiều replicas.** Đo worst-case revoke lag.

**Bước 12 — Chạy AS sandbox contract test.** Xác nhận RFC 7009 và RFC 7662 behavior của nhà phát hành thực tế.

**Bước 13 — Theo dõi metrics và audit.** Không đưa token/secret vào logs hoặc labels.

## 22. Câu hỏi tự kiểm tra

**1. RFC 7009 định nghĩa gì?**

Một endpoint để OAuth client yêu cầu Authorization Server thu hồi token.

**2. RFC 7662 định nghĩa gì?**

Token introspection: protected resource hỏi token active và attributes.

**3. JWT bị revoke có tự bị JwtDecoder từ chối không?**

Không nếu decoder chỉ xác minh chữ ký và claims, không có revocation check bổ sung.

**4. active=false và active=true thiếu scope khác nhau thế nào?**

active=false là authentication failure; active=true thiếu scope thường là authorization 403.

**5. JWKS cache có nói token bị revoke không?**

Không. JWKS chỉ chứa public keys.

**6. Positive introspection cache tạo rủi ro gì?**

Cached active=true có thể còn được dùng sau khi token đã bị revoke.

**7. Cache positive có được vượt exp không?**

Không. Phải giới hạn theo remaining lifetime và kiểm khi đọc.

**8. Vì sao denylist cần issuer+jti?**

Để tránh nhầm token IDs giữa issuers.

**9. Nếu revocation store timeout có nên coi token chưa revoke không?**

Không khi lookup bắt buộc; đó là fail-open.

**10. JWKS down có khiến mọi JWT đều fail không?**

Không nhất thiết. Key đã cache có thể vẫn verify, còn key mới chưa biết thì không được tin.

**11. MockOpaqueToken có gọi introspection thật không?**

Không. Cần Bearer request qua filter chain và HTTP introspection test server.

**12. Vì sao phải test nhiều replicas?**

Mỗi replica có cache/invalidation khác nhau, có thể kéo dài revocation lag.

## Kết luận

Thu hồi token, lỗi nhà phát hành và cache là một bài toán về **thời gian và phạm vi tin cậy của credential**. RFC 7009 cho OAuth client yêu cầu thu hồi; RFC 7662 cho Resource Server kiểm tra trạng thái. JWT local validation không tự nhận biết revoke, trong khi introspection cập nhật trạng thái tập trung nhưng thêm network dependency.

JWKS cache ảnh hưởng key rotation; positive introspection cache ảnh hưởng revocation lag; denylist giữ token bị thu hồi; tenant và authorization caches giữ trust/policy decisions. Mỗi loại phải có TTL, cache key, capacity, invalidation và consistency riêng.

Bộ test phải bao gồm signed JWT, issuer/audience/signature failures, JWKS key rotation/outage, introspection active true/false, timeout/5xx, revocation lookup, cache stale/invalidation, token exp và multi-node propagation. **Không fail-open khi không có kết quả xác minh tin cậy; không giữ positive cache sau exp hoặc quá revocation SLA; không để cache eviction làm JWT đã revoke được chấp nhận trở lại.**

### Tài liệu tham khảo

- [Spring Security — Servlet JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet OAuth2 Resource Server Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — WebFlux OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [Caffeine — Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
