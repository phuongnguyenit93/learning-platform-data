# Thay đổi decoder, introspector và các lớp triển khai mặc định

Khi nâng cấp Spring Security OAuth 2.0 Resource Server, một phần rủi ro nằm ở những lớp ứng dụng thường không tự viết: **JwtDecoder**, **ReactiveJwtDecoder**, **OpaqueTokenIntrospector**, **ReactiveOpaqueTokenIntrospector** và các implementation mặc định của chúng. Những lớp này quyết định cách access token được xác minh, cách kết nối tới Authorization Server, cách xử lý signing keys, cách ánh xạ claims thành principal và authorities.

Từ Spring Security 6.5 sang 7.0/7.1 có một số thay đổi cần chuẩn bị trước:

- Việc kiểm tra JWT header **typ** được chuyển từ cơ chế kiểm tra nội bộ của Nimbus sang **JwtTypeValidator**.
- Opaque-token introspection chuyển sang cách truyền client ID/secret chưa URL-encode để Spring tự encode khi tạo request.
- Constructor cũ của một số introspector được đánh dấu deprecated; builder trở thành cách khởi tạo được khuyến nghị.
- Spring Security 7.1 bổ sung **RestClientOpaqueTokenIntrospector** cho Servlet stack khi muốn dùng Spring RestClient.
- Timeout mặc định của HTTP fetch JWKS trong **NimbusJwtDecoder** thay đổi từ 500 ms lên 30 giây.
- Một số setter của **BearerTokenAuthenticationFilter** được thay bằng cấu hình qua **BearerTokenAuthenticationConverter**.

Ngoài thay đổi theo phiên bản, cần hiểu cách Spring Boot tự cấu hình decoder/introspector và thời điểm một bean tùy chỉnh thay thế implementation mặc định. Nếu tự tạo decoder hoặc introspector, ứng dụng có thể vô tình bỏ mất issuer/timestamp/type validation, dùng sai credentials, thay đổi timeout hoặc làm mất hành vi lazy discovery.

Bài học hướng dẫn đọc lại cấu hình, phân biệt Servlet và WebFlux, nâng cấp an toàn từ 6.5 lên 7.x, kiểm thử hành vi mới và tránh thay đổi implementation chỉ vì tên lớp đã khác.

## 1. Bản đồ các abstraction và implementation

Spring Security tách contract xác minh token khỏi implementation cụ thể.

| Token và stack | Contract | Implementation Spring phổ biến |
|---|---|---|
| JWT, Servlet | **JwtDecoder** | **NimbusJwtDecoder** |
| JWT, WebFlux | **ReactiveJwtDecoder** | **NimbusReactiveJwtDecoder** |
| Opaque, Servlet | **OpaqueTokenIntrospector** | **SpringOpaqueTokenIntrospector**; từ 7.1 có **RestClientOpaqueTokenIntrospector** |
| Opaque, WebFlux | **ReactiveOpaqueTokenIntrospector** | **SpringReactiveOpaqueTokenIntrospector** |

Các abstraction này có vai trò khác nhau:

- **JwtDecoder** nhận compact JWT string và trả về Jwt đã decode, verify và validate.
- **ReactiveJwtDecoder** làm việc tương tự nhưng trả Mono<Jwt>.
- **OpaqueTokenIntrospector** gọi introspection endpoint và trả OAuth2AuthenticatedPrincipal.
- **ReactiveOpaqueTokenIntrospector** thực hiện introspection bất đồng bộ và trả Mono<OAuth2AuthenticatedPrincipal>.

Các authentication provider/manager ở phía trên sử dụng những contract này:

~~~mermaid
flowchart TD
    B[Authorization: Bearer token] --> S{Token strategy}
    S -->|JWT / Servlet| JD[JwtDecoder]
    S -->|JWT / WebFlux| RJD[ReactiveJwtDecoder]
    S -->|Opaque / Servlet| OI[OpaqueTokenIntrospector]
    S -->|Opaque / WebFlux| ROI[ReactiveOpaqueTokenIntrospector]
    JD --> JWT[Validated Jwt]
    RJD --> JWT
    OI --> P[OAuth2AuthenticatedPrincipal]
    ROI --> P
    JWT --> A[Authentication]
    P --> A
    A --> Z[Authorization]
~~~

**Không thay implementation chỉ dựa trên tên lớp.** Trước hết xác định stack, loại token, contract của issuer và những validators/attributes ứng dụng đang phụ thuộc.

## 2. Default auto-configuration và bean tùy chỉnh

Khi dùng Spring Boot, Resource Server có thể tự tạo các thành phần cần thiết dựa trên properties. Với JWT, cấu hình tối thiểu:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
~~~

Với opaque token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/introspect
          client-id: resource-server
          client-secret: \${INTROSPECTION_CLIENT_SECRET}
~~~

Khi không có bean tùy chỉnh, Boot/Security thiết lập decoder hoặc introspector mặc định cùng Resource Server filter chain.

### 2.1. JWT: decoder mặc định

Với Servlet, contract là **JwtDecoder**, implementation mặc định thường là **NimbusJwtDecoder**.

Với WebFlux, contract là **ReactiveJwtDecoder**, implementation mặc định thường là **NimbusReactiveJwtDecoder**.

Cấu hình **issuer-uri** cho phép framework tìm metadata của Authorization Server, lấy JWKS URI và kiểm tra issuer. Với reactive stack, tài liệu hiện hành mô tả discovery được trì hoãn tới request JWT đầu tiên thông qua **SupplierReactiveJwtDecoder**, giúp startup không phụ thuộc ngay vào availability của Authorization Server.

Nếu cần chỉ định JWKS URI trực tiếp nhưng vẫn giữ issuer validation:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
          jwk-set-uri: https://idp.example.com/.well-known/jwks.json
~~~

**jwk-set-uri** giúp bỏ bước metadata discovery. Giữ **issuer-uri** để tiếp tục kiểm tra claim iss.

### 2.2. Opaque: introspector mặc định

Với Servlet, implementation mặc định là **SpringOpaqueTokenIntrospector**.

Với WebFlux, implementation mặc định là **SpringReactiveOpaqueTokenIntrospector**.

Các implementation này gọi introspection endpoint bằng client credentials, kiểm tra response có **active: true**, rồi tạo principal cùng authorities. Mặc định scope được ánh xạ thành authority có prefix **SCOPE_**.

### 2.3. Khi nào bean tùy chỉnh thay thế default?

Ví dụ JWT:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder.withIssuerLocation(issuer).build();
}
~~~

Bean **JwtDecoder** tùy chỉnh có thể thay decoder mà Boot định tạo. Với WebFlux, **ReactiveJwtDecoder** cũng có vai trò tương tự.

Opaque token:

~~~java
@Bean
OpaqueTokenIntrospector introspector() {
    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Hoặc reactive:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Bean tự khai báo thay implementation mặc định cùng loại. Khi dùng DSL, **decoder(...)** hoặc **introspector(...)** cũng có thể thay thế auto-configuration tương ứng.

Cần phân biệt **ghi đè một thuộc tính** với **thay toàn bộ implementation**:

| Cách cấu hình | Phạm vi |
|---|---|
| issuer-uri | Cấu hình issuer và discovery |
| jwk-set-uri | Chỉ định nguồn JWKS; có thể giữ issuer validation nếu issuer-uri vẫn được khai báo |
| jws-algorithms | Thay đổi allowlist thuật toán |
| decoder(...) / bean JwtDecoder | Thay decoder implementation |
| introspection-uri() | Ghi đè endpoint introspection |
| introspectionClientCredentials(...) | Ghi đè credentials cho introspection |
| introspector(...) / bean introspector | Thay toàn bộ introspector implementation |

**Thay decoder hoặc introspector là một thay đổi security behavior.** Không giả định các validators, timeout, authority mapping và error handling mặc định vẫn còn sau khi thay bean.

## 3. Thay đổi JWT typ: từ Nimbus verifier sang JwtTypeValidator

Đây là thay đổi cần chuẩn bị khi nâng từ Spring Security 6.5 lên 7.0.

Trước đây, **NimbusJwtDecoder** dựa vào Nimbus JOSE processor để kiểm tra header **typ**. Spring Security 7 chuyển trách nhiệm này sang **JwtTypeValidator**, phù hợp với cách Spring Security kiểm tra các JWT claims khác.

### 3.1. Chuẩn bị trong Spring Security 6.5

Nếu ứng dụng đã tùy chỉnh Nimbus type verifier hoặc muốn chuẩn bị trước, có thể tắt type verification của Nimbus và thêm validator tương ứng:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .validateTypes(false)
        .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithValidators(
            new JwtIssuerValidator(issuer),
            JwtTypeValidator.jwt()
        )
    );

    return decoder;
}
~~~

Với token JWT thông thường, **JwtTypeValidator.jwt()** chấp nhận typ là JWT hoặc không có header typ, phù hợp với tính tùy chọn của trường này theo JOSE.

### 3.2. Cấu hình sau khi chuyển sang Spring Security 7

Trong Spring Security 7, **validateTypes** của Nimbus mặc định là false, còn các phương thức **JwtValidators.createDefault...** đã thêm **JwtTypeValidator.jwt()** vào bộ validator mặc định.

Vì vậy cấu hình chuẩn có thể rút gọn:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Không cần tiếp tục thêm JwtTypeValidator.jwt() một lần nữa nếu đang dùng factory mặc định của phiên bản 7 theo đúng hướng dẫn migration.

### 3.3. Nếu hệ thống dùng typ tùy chỉnh

Một số token profile có thể dùng type khác JWT, ví dụ một profile JOSE riêng. Nếu trước đây ứng dụng đặt **DefaultJOSEObjectTypeVerifier** trong **jwtProcessorCustomizer**, cần chuyển policy tương ứng sang **JwtTypeValidator** hoặc một **OAuth2TokenValidator** tùy chỉnh.

Ví dụ khái niệm:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .validateTypes(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(issuer),
        new JwtTypeValidator("JOSE")
    )
);
~~~

Chỉ dùng type đúng theo token profile và tài liệu migration của phiên bản đang chạy. Không cho phép một tập typ rộng hơn chỉ để làm các token cũ tiếp tục qua validation.

### 3.4. Tránh bỏ type validation khi tự cấu hình validator

Một lỗi dễ gặp là:

~~~java
decoder.setJwtValidator(new JwtTimestampValidator());
~~~

Lệnh này thay bộ validator hiện tại bằng validator được truyền vào. Nếu chỉ đặt timestamp validator, ứng dụng có thể vô tình bỏ issuer validation, type validation và các policy khác.

Khi cần custom validator, kết hợp với default validators bằng **DelegatingOAuth2TokenValidator**:

~~~java
OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> audience = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        )
    );
};

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(defaults, audience)
);
~~~

Cách này giữ bộ kiểm tra mặc định và bổ sung audience policy.

## 4. Cùng thay đổi typ trong WebFlux

Reactive decoder có contract khác Servlet:

- Servlet: **JwtDecoder** và **NimbusJwtDecoder**.
- WebFlux: **ReactiveJwtDecoder** và **NimbusReactiveJwtDecoder**.

Chuẩn bị trong 6.5:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
            .validateTypes(false)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithValidators(
            new JwtIssuerValidator(issuer),
            JwtTypeValidator.jwt()
        )
    );

    return decoder;
}
~~~

Sau khi nâng lên Spring Security 7:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Các nguyên tắc giống Servlet: giữ default validators, thêm audience/tenant validators bằng composition, không đưa blocking network work vào Reactor event loop.

## 5. Thay đổi opaque introspection client credentials

Spring Security 6.5 bổ sung builder cho **SpringOpaqueTokenIntrospector** và **SpringReactiveOpaqueTokenIntrospector**. Builder tự URL-encode client ID và client secret trước khi tạo HTTP Basic authorization cho introspection request.

Đây là thay đổi quan trọng với credentials có ký tự không an toàn trong URL/form encoding.

### 5.1. Trước thay đổi: ứng dụng tự encode credentials

Một số ứng dụng trước đây tự encode client ID/secret rồi truyền vào API cũ hoặc tự xây **RestOperations** với Basic authentication.

Nếu tiếp tục đưa giá trị đã encode vào builder mới, framework có thể encode lần nữa. Authorization Server nhận credential khác với credential đã đăng ký và trả lỗi client authentication.

### 5.2. Cách khuyến nghị trong 6.5 và 7.x

Truyền **giá trị gốc chưa encode** cho builder:

~~~java
@Bean
OpaqueTokenIntrospector introspector() {
    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(unencodedClientId)
        .clientSecret(unencodedClientSecret)
        .build();
}
~~~

Reactive:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(unencodedClientId)
        .clientSecret(unencodedClientSecret)
        .build();
}
~~~

Giữ client secret trong secret manager/environment configuration. Không hard-code, log hoặc đưa secret vào exception message.

### 5.3. Constructor cũ đã deprecated

Constructor cũ nhận URL-encoded credentials của **SpringReactiveOpaqueTokenIntrospector** được đánh dấu deprecated từ 6.5 và hướng tới removal. Ưu tiên builder:

~~~java
SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(uri)
    .clientId(clientId)
    .clientSecret(clientSecret)
    .build();
~~~

Không tự encode trước khi gọi **clientId(...)** hoặc **clientSecret(...)**.

Nếu đang có custom RestOperations/WebClient, hãy xác định rõ nơi thực hiện Basic authentication và encoding. Tránh vừa encode trong ứng dụng vừa để builder encode thêm lần nữa.

## 6. Implementation opaque token trong Servlet: SpringOpaqueTokenIntrospector và RestClientOpaqueTokenIntrospector

Trong Servlet stack, implementation truyền thống là **SpringOpaqueTokenIntrospector**, hỗ trợ **RestOperations** để gọi introspection endpoint.

Spring Security 7.1 bổ sung **RestClientOpaqueTokenIntrospector**, dùng Spring Framework **RestClient**.

Hai class cùng triển khai **OpaqueTokenIntrospector**, nhưng khác HTTP client abstraction.

| Class | HTTP client | Phù hợp khi |
|---|---|---|
| SpringOpaqueTokenIntrospector | RestOperations / RestTemplate | Ứng dụng hiện tại dùng RestTemplate hoặc muốn giữ cấu hình cũ |
| RestClientOpaqueTokenIntrospector | RestClient | Ứng dụng muốn dùng HTTP client đồng bộ hiện đại của Spring Framework |

**RestClientOpaqueTokenIntrospector là lựa chọn mới trong 7.1, không có nghĩa mọi ứng dụng tự động chuyển sang class này.** Default fallback trong tài liệu Resource Server vẫn là **SpringOpaqueTokenIntrospector**, trừ khi ứng dụng cấu hình implementation khác.

### 6.1. Dùng RestClientOpaqueTokenIntrospector

Ví dụ builder cơ bản:

~~~java
@Bean
OpaqueTokenIntrospector introspector(
        String introspectionUri,
        String clientId,
        String clientSecret) {

    return RestClientOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Builder nhận credentials chưa encode và thực hiện encoding theo contract của implementation.

### 6.2. Tùy chỉnh RestClient và timeout

Khi cần request factory, timeout hoặc interceptor riêng, tạo **RestClient** rồi truyền vào constructor:

~~~java
@Bean
OpaqueTokenIntrospector introspector(
        String introspectionUri,
        String clientId,
        String clientSecret) {

    SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

    requestFactory.setConnectTimeout(Duration.ofSeconds(5));
    requestFactory.setReadTimeout(Duration.ofSeconds(5));

    RestClient restClient = RestClient.builder()
        .requestFactory(requestFactory)
        .defaultHeaders(headers ->
            headers.setBasicAuth(clientId, clientSecret)
        )
        .build();

    return new RestClientOpaqueTokenIntrospector(
        introspectionUri,
        restClient
    );
}
~~~

Đây là cấu hình minh họa cho client tự quản lý Basic authentication. Nếu dùng builder của introspector để quản lý credentials, không đồng thời thêm một Basic Authorization header thứ hai trong RestClient.

Chọn timeout theo latency budget và availability policy. Introspection timeout không được biến thành authentication success hoặc active=true giả.

### 6.3. Khi nào giữ SpringOpaqueTokenIntrospector?

Giữ implementation hiện tại nếu:

- Ứng dụng đã có RestOperations với connection pool, proxy, TLS và timeout phù hợp.
- Không cần chuyển sang RestClient.
- Integration tests đang phụ thuộc vào behavior đã cấu hình.
- Việc nâng cấp chưa có yêu cầu thay HTTP client.

Không cần thay implementation chỉ vì Spring Security 7.1 bổ sung class mới. Chỉ thay khi có lợi ích cụ thể và đã kiểm thử tương thích.

## 7. Implementation opaque token trong WebFlux

WebFlux sử dụng **ReactiveOpaqueTokenIntrospector**. Implementation mặc định là **SpringReactiveOpaqueTokenIntrospector**, sử dụng WebClient/reactive HTTP để gọi introspection endpoint.

Ví dụ:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

Khác với Servlet, không dùng **RestClientOpaqueTokenIntrospector** trong WebFlux Resource Server chỉ vì class mới xuất hiện ở Spring Security 7.1. RestClient là synchronous client; reactive stack có implementation reactive riêng.

### 7.1. Tùy chỉnh principal/authorities bằng delegate

Nếu cần thay cách ánh xạ scope, role hoặc attributes, có thể bọc introspector mặc định thay vì tự viết lại toàn bộ HTTP exchange:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    ReactiveOpaqueTokenIntrospector delegate =
        SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(introspectionUri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return token -> delegate.introspect(token)
        .map(principal -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(principal.getAuthorities());

            // Thêm mapping theo contract đã xác minh của hệ thống.
            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities
            );
        });
}
~~~

Đoạn code chỉ minh họa cách decorate principal; phần mapping cần thay bằng policy cụ thể. Không cấp role chỉ từ một attribute chưa được xác minh hoặc không thuộc contract của issuer.

### 7.2. Không block reactive introspection

Không gọi block() trong **ReactiveOpaqueTokenIntrospector** hoặc WebFlux authentication path. Không dùng RestTemplate trực tiếp trên Reactor event loop. Nếu cần một thư viện blocking, phải chuyển sang scheduler phù hợp và kiểm soát concurrency; ưu tiên reactive WebClient implementation.

## 8. Thay đổi timeout mặc định của NimbusJwtDecoder

Trong Spring Security 7.0, **NimbusJwtDecoder** thay đổi default connect/read timeout cho **RestOperations** dùng để tải JWK Set khi ứng dụng không cung cấp RestOperations riêng:

| Phiên bản trước | Spring Security 7.0+ |
|---|---|
| 500 ms connect timeout | 30 giây |
| 500 ms read timeout | 30 giây |

Thay đổi này giúp nhiều deployment có thời gian tải JWKS thực tế hơn, nhưng có thể làm request chờ lâu hơn khi Authorization Server không phản hồi.

Điều này đặc biệt quan trọng nếu ứng dụng trước đây dựa vào failure nhanh để mở circuit breaker hoặc trả lỗi sớm.

### 8.1. Kiểm tra timeout trong migration

- Kiểm connect/read timeout của JWKS fetch.
- Kiểm timeout tổng thể ở ingress/API gateway.
- Kiểm retry và circuit breaker.
- Kiểm thời gian cold start hoặc lần đầu cần tải key.
- Kiểm behavior khi issuer/JWKS endpoint mất kết nối.
- Không retry vô hạn trong request path.

Thay đổi timeout được ghi nhận cụ thể cho **NimbusJwtDecoder** và **RestOperations**. Không suy rộng rằng mọi reactive decoder hoặc mọi custom HTTP client cũng có cùng default.

### 8.2. Cấu hình RestOperations riêng khi cần

Nếu muốn kiểm soát timeout rõ ràng, có thể truyền **RestOperations** tùy chỉnh vào builder/decoder theo API của phiên bản:

~~~java
@Bean
JwtDecoder jwtDecoder(RestTemplateBuilder builder) {
    RestOperations restOperations = builder
        .connectTimeout(Duration.ofSeconds(2))
        .readTimeout(Duration.ofSeconds(2))
        .build();

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer)
            .restOperations(restOperations)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Kiểm tra builder method theo đúng Spring Security/Spring Framework release đang dùng. Mục tiêu là đặt timeout theo budget của hệ thống, không phụ thuộc ngầm vào default thay đổi giữa các phiên bản.

## 9. Thay đổi BearerTokenAuthenticationFilter và converter

Spring Security 7 deprecate các setter trên **BearerTokenAuthenticationFilter**:

- **setBearerTokenResolver(...)**
- **setAuthenticationDetailsSource(...)**

Thay vào đó, cấu hình hai thành phần trên **BearerTokenAuthenticationConverter** rồi truyền converter vào filter.

Trước đây:

~~~java
BearerTokenAuthenticationFilter filter =
    new BearerTokenAuthenticationFilter(authenticationManager);

filter.setBearerTokenResolver(myBearerTokenResolver);
filter.setAuthenticationDetailsSource(myAuthenticationDetailsSource);
~~~

Cách mới:

~~~java
BearerTokenAuthenticationConverter converter =
    new BearerTokenAuthenticationConverter();

converter.setBearerTokenResolver(myBearerTokenResolver);
converter.setAuthenticationDetailsSource(
    myAuthenticationDetailsSource
);

BearerTokenAuthenticationFilter filter =
    new BearerTokenAuthenticationFilter(
        authenticationManager,
        converter
    );
~~~

Với đa số ứng dụng, **oauth2ResourceServer DSL** đã xử lý các use cases thông thường; không cần tự tạo filter. Thay đổi này chủ yếu quan trọng nếu ứng dụng tự lắp ghép **BearerTokenAuthenticationFilter**.

Không thay token extraction behavior trong lúc migration nếu chưa có test cho:

- Header Bearer hợp lệ.
- Thiếu header.
- Header sai format.
- Nhiều nguồn token.
- Token trong query/form nếu ứng dụng có hỗ trợ.
- Authentication details được truyền tới provider.

## 10. Default algorithm và validator không được tự mở rộng

**NimbusJwtDecoder** và **NimbusReactiveJwtDecoder** mặc định chỉ tin thuật toán **RS256** theo tài liệu Resource Server hiện hành. Nếu issuer dùng thuật toán khác, phải cấu hình allowlist rõ.

Ví dụ Servlet:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Reactive:

~~~java
NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Có thể cấu hình nhiều thuật toán nếu token issuer thực sự dùng chúng. Không tin thuật toán chỉ vì JWT header tự khai alg; allowlist phải do server cấu hình.

Ngoài signature và issuer, xác định rõ validators cho:

- exp và nbf.
- aud.
- Token type/profile.
- Client/resource binding.
- Tenant và claims bắt buộc.
- Các policy đặc thù ứng dụng.

Không thay validator mặc định bằng một custom validator chỉ kiểm một claim rồi vô tình bỏ các điều kiện còn lại.

## 11. Phân biệt thay decoder với thay JwtAuthenticationConverter

Một số migration nhầm lẫn giữa hai tầng:

- **Decoder** xác minh chữ ký, issuer, thời gian và claims.
- **Authentication converter** chuyển Jwt đã xác minh thành Authentication/GrantedAuthority.

Ví dụ custom scope mapping không nhất thiết cần custom decoder. Có thể cấu hình **JwtAuthenticationConverter** hoặc **JwtGrantedAuthoritiesConverter** ở bước chuyển đổi authority.

Nếu decoder thay đổi, hãy test signature/issuer/audience/type/time. Nếu converter thay đổi, hãy test principal/authority mapping.

Không dùng custom converter để bù cho việc decoder bỏ qua validation. Không dùng claim chưa verify để tạo authorities.

## 12. Bảo toàn lazy discovery và startup behavior

Với **issuer-uri**, Spring Security có thể trì hoãn discovery cho tới khi request JWT đầu tiên tới. Điều này giúp ứng dụng startup ngay cả khi Authorization Server tạm thời không khả dụng.

Khi tự khai báo decoder, hãy kiểm tra liệu cách tạo mới có làm discovery chạy sớm hơn hoặc lặp lại nhiều lần không.

Các lựa chọn:

| Cấu hình | Hành vi |
|---|---|
| Chỉ issuer-uri | Discovery tìm JWKS từ metadata |
| issuer-uri + jwk-set-uri | Bỏ metadata discovery nhưng vẫn kiểm issuer |
| Custom decoder từ withIssuerLocation | Ứng dụng kiểm soát decoder/validator; kiểm tra discovery timing |
| Custom decoder với JWK source tĩnh | Tự quản lý key source và rotation lifecycle |

Không gọi metadata endpoint trên mỗi request. Tái sử dụng decoder và key cache. Nếu cần độc lập với metadata endpoint lúc startup, cấu hình JWKS URI đã được quản trị.

## 13. Đổi default implementation có thể làm mất behavior nào?

Trước khi thay decoder hoặc introspector, ghi lại behavior hiện tại:

| Behavior | JWT decoder | Opaque introspector |
|---|---|---|
| Xác minh token | Signature, key, claims | Introspection active |
| Issuer | iss validator | Theo AS/introspection contract và custom policy |
| Audience | Custom/default validators tùy cấu hình | Attributes/custom validation |
| Expiration | exp/nbf validators | AS trả active và claims |
| Authority mapping | Scope/scp converter | Scope từ introspection response |
| HTTP client | JWKS/discovery client | Introspection HTTP client |
| Timeout | JWKS fetch timeout | Introspection timeout |
| Key/credential rotation | JWKS cache/key refresh | Client secret/TLS/HTTP config |
| Error handling | JwtException/authentication failure | Introspection exception/authentication failure |

Một implementation tùy chỉnh phải giữ các invariants cần thiết. Đừng giả định việc implement **JwtDecoder** hoặc **OpaqueTokenIntrospector** đồng nghĩa Spring tự động thêm toàn bộ validation mặc định.

## 14. Quy trình migration từ 6.5 lên 7.0/7.1

### Bước 1 — Xác nhận dependency alignment

Kiểm tra Spring Boot BOM/Spring Security BOM. Không nâng riêng **spring-security-oauth2-resource-server** trong khi các module **spring-security-core**, **oauth2-jose** hoặc **spring-security-test** ở version khác.

Với JWT, cần cả **spring-security-oauth2-resource-server** và **spring-security-oauth2-jose**. Opaque-token introspection không cần module JOSE chỉ để gọi introspection.

### Bước 2 — Tìm custom decoder và introspector

Tìm trong codebase:

- JwtDecoder, ReactiveJwtDecoder.
- NimbusJwtDecoder, NimbusReactiveJwtDecoder.
- OpaqueTokenIntrospector, ReactiveOpaqueTokenIntrospector.
- SpringOpaqueTokenIntrospector, SpringReactiveOpaqueTokenIntrospector.
- jwtProcessorCustomizer, setJwtValidator.
- introspectionClientCredentials, clientId, clientSecret.
- BearerTokenAuthenticationFilter setters.

### Bước 3 — Chuẩn bị JwtTypeValidator trong 6.5

Nếu đang tùy chỉnh Nimbus type verification, chuyển policy sang **JwtTypeValidator** hoặc custom **OAuth2TokenValidator** tương ứng. Test token typ đúng, sai và vắng mặt.

### Bước 4 — Bỏ encode credentials thủ công

Đổi builder input thành client ID/secret gốc. Kiểm Authorization header tới introspection endpoint bằng test server, đặc biệt với credentials có ký tự đặc biệt.

### Bước 5 — Nâng Spring Security 7

Bỏ transitional validateTypes(false) nếu không còn cần cấu hình riêng và dùng **JwtValidators.createDefaultWithIssuer(...)** cho profile JWT chuẩn. Tránh thêm duplicate default JwtTypeValidator.

### Bước 6 — Kiểm timeout JWKS

Đo behavior mới 30 giây của NimbusJwtDecoder. Nếu không phù hợp, cấu hình RestOperations timeout rõ ràng.

### Bước 7 — Xem xét RestClientOpaqueTokenIntrospector

Nếu Servlet application muốn chuyển từ RestTemplate/RestOperations sang RestClient, thử nghiệm **RestClientOpaqueTokenIntrospector** của Spring Security 7.1. Không cần đổi nếu implementation hiện tại đang đáp ứng yêu cầu.

### Bước 8 — Cập nhật custom filter assembly

Nếu tự tạo BearerTokenAuthenticationFilter, chuyển resolver/details source sang BearerTokenAuthenticationConverter. Nếu dùng DSL, kiểm tra deprecation compile warnings và giữ DSL nếu đáp ứng use case.

### Bước 9 — Chạy integration tests

Kiểm token signature, issuer, audience, type, expiration, introspection credentials, timeout, authority mapping và error behavior. Không chỉ kiểm compile.

### Bước 10 — Rollout và quan sát

Theo dõi:

- 401 tăng bất thường.
- Introspection client authentication failure.
- JWKS fetch latency/timeout.
- Decoder initialization.
- Unknown typ/signature errors.
- Scope/authority mapping changes.
- Startup/readiness behavior.

## 15. Bộ test cần có sau migration

### 15.1. JWT decoder

| Test | Kết quả |
|---|---|
| Signature hợp lệ, issuer đúng, exp còn hạn | Accept |
| Signature sai | Reject |
| Issuer sai | Reject |
| Audience sai | Reject |
| Token hết hạn | Reject |
| nbf ở tương lai | Reject |
| typ là JWT | Theo profile chuẩn, accept |
| typ vắng mặt | Theo JWT validator mặc định, accept |
| typ sai profile | Reject |
| Thuật toán ngoài allowlist | Reject |

Dùng signed test tokens và key/JWKS test server để kiểm decoder thật. **jwt()** test helper chỉ inject Authentication mock, không chứng minh decoder.

### 15.2. Opaque introspector

- active=true tạo principal.
- active=false bị từ chối.
- Client ID/secret có ký tự đặc biệt được gửi đúng.
- Không encode credentials hai lần.
- Introspection 401/403 được xử lý đúng.
- Timeout/5xx không fail-open.
- Scope được ánh xạ đúng.
- Attributes/principal mapping giữ đúng contract.

Dùng HTTP stub/test server để kiểm request thực sự tới introspection endpoint.

### 15.3. Timeout và startup

- JWKS endpoint nhanh.
- JWKS endpoint chậm hơn 500 ms nhưng dưới timeout mới.
- JWKS endpoint vượt timeout.
- Authorization Server không sẵn sàng khi startup.
- Request đầu tiên kích hoạt discovery.
- Key rotation và unknown kid.
- Introspection latency và cancellation trong WebFlux.

### 15.4. Servlet và WebFlux

Chạy test riêng cho hai stack. Không dùng Servlet **JwtDecoder** trong WebFlux hoặc **ReactiveJwtDecoder** trong Servlet chỉ vì hai interface có tên gần nhau.

Với WebFlux, kiểm không có block() trong decoder/introspector pipeline và SecurityContext tiếp tục được truyền qua Reactor Context.

## 16. Các anti-pattern thường gặp

**Giữ credentials đã encode rồi truyền vào builder mới.** Framework có thể encode lần nữa, làm Basic authentication thất bại.

**Tự tạo NimbusJwtDecoder nhưng quên validator mặc định.** Có thể bỏ issuer, timestamp hoặc type validation.

**Dùng setJwtValidator với một validator đơn lẻ.** Có thể thay thế toàn bộ validator chain trước đó.

**Coi JwtTypeValidator là một thay đổi chỉ về syntax.** Nó là một phần của token profile validation.

**Tự mở rộng thuật toán theo JWT header.** Cho phép thuật toán ngoài policy tin cậy.

**Thay SpringOpaqueTokenIntrospector bằng class khác chỉ vì 7.1 có RestClient implementation.** Không có lợi ích nếu HTTP client và behavior hiện tại đã phù hợp.

**Dùng RestClientOpaqueTokenIntrospector trong WebFlux.** Chọn implementation theo Servlet/reactive stack.

**Tạo introspector mới cho mỗi request.** Tốn HTTP client/configuration resources và làm mất cache/pooling.

**Block trong ReactiveOpaqueTokenIntrospector.** Có thể làm nghẽn Reactor event loop.

**Không kiểm timeout sau nâng cấp.** 30 giây có thể vượt deadline của gateway/request.

**Tự viết lại toàn bộ introspection HTTP chỉ để đổi authority mapping.** Có thể bỏ mất error handling và credential behavior của implementation mặc định; ưu tiên delegate/decorator.

**Dùng custom decoder để xử lý role mapping.** Chuyển đổi authorities nên ở authentication converter phù hợp.

**Cho rằng Boot vẫn dùng decoder default sau khi khai báo bean tùy chỉnh.** Bean cùng loại có thể thay auto-configuration.

**Chỉ test compile sau migration.** Các thay đổi encoding, type validation và timeout thường chỉ xuất hiện khi gọi Authorization Server thật hoặc test server.

## 17. Bảng tham chiếu nhanh theo phiên bản

| Thành phần | Spring Security 6.5 | Spring Security 7.0 | Spring Security 7.1 |
|---|---|---|---|
| JWT typ | Chuẩn bị chuyển sang JwtTypeValidator | validateTypes mặc định false; default validators thêm JwtTypeValidator.jwt() | Giữ behavior 7.0 |
| Opaque credentials | Builder encode client ID/secret; truyền giá trị gốc | Opaque support encode credentials; không tự encode trước | Giữ behavior |
| SpringOpaqueTokenIntrospector | Builder được khuyến nghị; constructor cũ có thể deprecated | Vẫn là default fallback | Vẫn có thể dùng |
| SpringReactiveOpaqueTokenIntrospector | Builder được khuyến nghị | Vẫn là reactive default | Có builder postProcessor |
| RestClientOpaqueTokenIntrospector | Chưa có | Chưa có | Có từ 7.1, Servlet stack |
| NimbusJwtDecoder JWKS timeout | 500 ms default cũ | 30 giây default | Giữ behavior 7.0 |
| BearerTokenAuthenticationFilter setters | Còn dùng được | Deprecated, chuyển sang converter | Dùng converter |

Bảng này tập trung vào các thay đổi liên quan trực tiếp tới decoder/introspector và Bearer filter. Luôn kiểm release notes và migration guide của minor version cụ thể mà dự án đang nâng lên.

## 18. Câu hỏi tự kiểm tra

**1. Servlet JWT dùng contract nào?**

JwtDecoder, thường được triển khai bởi NimbusJwtDecoder.

**2. WebFlux JWT dùng contract nào?**

ReactiveJwtDecoder, thường được triển khai bởi NimbusReactiveJwtDecoder.

**3. Opaque token Servlet và WebFlux dùng introspector nào?**

Servlet dùng OpaqueTokenIntrospector; WebFlux dùng ReactiveOpaqueTokenIntrospector.

**4. Spring Security 7 thay đổi kiểm tra typ như thế nào?**

Chuyển type validation sang JwtTypeValidator; các default validator factory thêm JwtTypeValidator.jwt().

**5. Có nên URL-encode client ID/secret trước khi gọi builder introspector không?**

Không. Truyền giá trị gốc chưa encode để builder xử lý.

**6. RestClientOpaqueTokenIntrospector có từ phiên bản nào?**

Spring Security 7.1, dành cho Servlet stack và Spring RestClient.

**7. SpringReactiveOpaqueTokenIntrospector có bị thay bằng RestClientOpaqueTokenIntrospector không?**

Không. WebFlux tiếp tục dùng reactive introspector.

**8. NimbusJwtDecoder default JWKS timeout thay đổi ra sao trong 7.0?**

Từ 500 ms lên 30 giây cho connect/read timeout mặc định của JWKS RestOperations.

**9. Vì sao phải dùng DelegatingOAuth2TokenValidator?**

Để giữ các default validators đồng thời bổ sung audience hoặc policy tùy chỉnh.

**10. Khai báo bean JwtDecoder có ảnh hưởng auto-configuration không?**

Có. Bean tùy chỉnh có thể thay decoder mà Boot định cấu hình mặc định.

**11. Khi nào nên thay SpringOpaqueTokenIntrospector bằng RestClientOpaqueTokenIntrospector?**

Khi Servlet application cần dùng RestClient hoặc cần request factory/HTTP client customization phù hợp; không bắt buộc chỉ vì đã nâng version.

**12. Vì sao cần test với introspection server thật hoặc stub?**

Để xác minh credentials, URL encoding, HTTP request, timeout, response active và authority mapping; mock Authentication không kiểm các phần này.

## Kết luận

Migration decoder và introspector cần được xem là migration của **hành vi xác thực**, không chỉ là thay tên class hoặc sửa deprecation warning.

Khi nâng từ 6.5 lên 7.x, cần xử lý **JwtTypeValidator**, truyền opaque client credentials ở dạng chưa encode, kiểm tra timeout JWKS mới và chuyển các cấu hình Bearer filter tùy chỉnh sang **BearerTokenAuthenticationConverter**. Trong Servlet stack, **RestClientOpaqueTokenIntrospector** là lựa chọn mới từ 7.1; **SpringOpaqueTokenIntrospector** vẫn là implementation hợp lệ. Trong WebFlux, giữ **ReactiveJwtDecoder** và **SpringReactiveOpaqueTokenIntrospector** tương ứng, không đưa synchronous client vào reactive path.

Trước khi thay implementation mặc định, hãy xác định bean nào đang được Boot tạo, validator nào đang chạy, authority được ánh xạ ra sao, HTTP client dùng timeout nào và lỗi được xử lý thế nào. **Một migration an toàn giữ nguyên issuer, audience, timestamp, type, signature, introspection và authority policies; mọi thay đổi có chủ đích phải được xác nhận bằng integration tests với signed JWT hoặc introspection endpoint test.**

### Tài liệu tham khảo

- [Spring Security 6.5 to 7.0 — OAuth 2.0 Migration Guide](https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html)
- [Spring Security 7.0 — OAuth 2.0 Migrations](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/oauth2.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security API — SpringOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Security API — RestClientOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/RestClientOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security — What’s New in 7.1](https://docs.spring.io/spring-security/reference/whats-new.html)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
