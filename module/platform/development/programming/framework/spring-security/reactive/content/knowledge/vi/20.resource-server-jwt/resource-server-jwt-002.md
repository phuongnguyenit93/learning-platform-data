# Thiết lập phụ thuộc Resource Server và JOSE trong Spring Security reactive

## 1. Mục tiêu: một WebFlux API kiểm tra JWT Bearer token đúng cách

Một **OAuth2 Resource Server** là API bảo vệ tài nguyên; nó nhận access token do Authorization Server (AS) phát hành và quyết định có chấp nhận request hay không. Khi access token được biểu diễn thành **JWT đã ký**, Resource Server phải giải mã cú pháp token, kiểm **chữ ký**, kiểm các claims quan trọng như issuer, expiration, not-before và audience, rồi chuyển quyền thành `Authentication` dùng trong Spring Security.

Trong Spring Security reactive/WebFlux, các nhiệm vụ này cần **hai module khác nhau**:
- `spring-security-oauth2-resource-server`: cơ chế nhận và xử lý Bearer access token, authentication/authorization của Resource Server.
- `spring-security-oauth2-jose`: hỗ trợ JWT/JWS và các thao tác xác minh liên quan qua thư viện JOSE/JWT (Nimbus); chứa những lớp như `NimbusReactiveJwtDecoder`.

Với **Spring Boot**, cách cài đơn giản, được khuyến nghị là **một starter**:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Starter này kéo các thành phần Resource Server/JWT cần thiết, bao gồm JOSE, theo bộ phiên bản do Spring Boot quản lý. **Không cần khai báo thêm `spring-security-oauth2-jose` riêng nếu đã dùng starter và dependency graph đúng.** Ngược lại, nếu **không** dùng Boot starter mà chọn dependency trực tiếp, cần cả hai module để xử lý JWT.

Sơ đồ:

~~~text
Client / SPA / backend khác
     │
     │ GET /api/catalog
     │ Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
     ▼
┌──────────────────────────────────────────────┐
│ Spring Boot WebFlux API                      │
│                                              │
│ spring-boot-starter-oauth2-resource-server   │
│  ├─ spring-security-oauth2-resource-server   │
│  │    Bearer authentication + authorization  │
│  └─ spring-security-oauth2-jose              │
│       JWT parsing / JWS signature verify    │
│       NimbusReactiveJwtDecoder              │
│                                              │
│  → JwtAuthenticationToken                    │
│  → SCOPE_catalog.read / other authorities    │
│  → Controller / service                      │
└──────────────────────────────────────────────┘
     ▲
     │ Public keys được cấu hình hoặc lấy qua JWKS
     │
Authorization Server / Identity Provider
  issuer: https://idp.example.test/issuer
  JWKS:   https://idp.example.test/jwks
~~~

**Mục tiêu bài học:** biết cài phụ thuộc đúng, cấu hình nguồn xác minh JWT, hiểu các API WebFlux thay cho Servlet, khởi động project Java 17+, và kiểm thử được **401, 403, 200** bằng token ký thật. Bài cũng phân biệt JWT, JOSE, JWS, JWE, JWK, JWKS, scopes và những lỗi thường gặp khi triển khai.

### Kết quả mong đợi

Sau bài học bạn có thể:
1. Giải thích vì sao chỉ thêm `spring-security-oauth2-resource-server` không đủ khi tự cấu hình JWT mà bỏ `spring-security-oauth2-jose`.
2. Cài đúng starter Resource Server bằng Gradle/Maven, không trộn stack Servlet và WebFlux.
3. Hiểu `iss`, `aud`, `exp`, `nbf`, `sub`, `scope` và cách Resource Server đánh giá token.
4. Chọn `issuer-uri`, `jwk-set-uri`, `public-key-location` hoặc `ReactiveJwtDecoder` theo kiến trúc tin cậy.
5. Cấu hình `SecurityWebFilterChain` và `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)`.
6. Hiểu `JwtAuthenticationToken`, `ReactiveJwtDecoder`, `NimbusReactiveJwtDecoder` và authority `SCOPE_...`.
7. Kiểm thử offline bằng test-only RSA signing key, thực sự chạy đường xác minh chữ ký trên WebFlux.
8. Phân biệt `mockJwt()` không kiểm chữ ký với kiểm thử Bearer JWT thật.
9. Chẩn đoán lỗi dependency, issuer, audience, JWK key rotation, HTTPS, clock skew và invalid signature.
10. Giữ bí mật private key, không tin thuật toán/kid/jku do attacker tự đề xuất và không dùng ID Token thay access token.

## 2. JWT, JOSE, JWS, JWE, JWK và JWKS khác nhau thế nào?

Các chữ viết tắt liên quan nhưng không đồng nghĩa.

| Thuật ngữ | Ý nghĩa | Liên hệ trong Resource Server JWT |
| --- | --- | --- |
| **JWT** (JSON Web Token) | Định dạng biểu diễn claims thành token dạng JSON | Mang `iss`, `sub`, `aud`, `exp`, `scope`... |
| **JOSE** (JSON Object Signing and Encryption) | Họ đặc tả ký, mã hóa và quản lý key JSON | Nền tảng mã hóa/xác minh của JWT |
| **JWS** (JSON Web Signature) | Định dạng dữ liệu **được ký** | JWT truy cập API thường là compact JWS có chữ ký |
| **JWE** (JSON Web Encryption) | Định dạng dữ liệu **được mã hóa** | Không mặc định được xử lý giống JWT ký JWS; cần thiết kế decoder/decryption riêng khi dùng |
| **JWK** (JSON Web Key) | Biểu diễn một key theo JSON, có `kty`, `kid`... | Public key để xác minh chữ ký |
| **JWKS** (JSON Web Key Set) | JSON object chứa một mảng `keys` | Authorization Server công bố danh sách public keys |
| **JWA** (JSON Web Algorithms) | Tên và yêu cầu thuật toán | Ví dụ `RS256`, `ES256` |
| **Bearer token** | Credential mà ai nắm giữ có thể sử dụng theo quyền của token | Header `Authorization: Bearer ...`; phải bảo vệ khỏi lộ |

### 2.1. Cấu trúc compact JWS dạng JWT

JWT được ký kiểu JWS thường có **ba phần**:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Ví dụ nội dung header/payload sau khi decode:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "issuer-key-2026-11"
}
~~~

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "sub": "user-123",
  "aud": ["catalog-api"],
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790003600,
  "scope": "catalog.read"
}
~~~

**Hai JSON trên là ví dụ về hình dạng claims**, không phải token hợp lệ được ký bởi issuer thật; mốc thời gian `iat/nbf/exp` chỉ minh họa định dạng NumericDate, không dùng làm test fixture hiện tại.

Điều quan trọng:
- Header và payload JWS được **Base64URL-encoded, không được mã hóa bí mật**. Người có token có thể đọc claims.
- Chữ ký giúp phát hiện thay đổi dữ liệu và xác minh issuer sở hữu key tương ứng; chỉ đọc payload không đủ xác minh.
- `alg` trong header là dữ liệu từ token chưa đáng tin trước khi decoder kiểm. Backend phải **chỉ chấp nhận thuật toán được cấu hình cho issuer**, không đổi thuật toán tùy ý theo header.
- `kid` giúp chọn key trong JWKS. Nó **không** cấp quyền và không được dùng để tải file hoặc URL tùy ý.
- Một JWE compact thường có **năm phần**, không phải ba phần của JWS. Không giả định starter tự giải mã mọi loại JWE.
- Có chữ ký hợp lệ chưa đủ: còn phải xác minh `iss`, `aud`, thời gian, loại token và quyền.

### 2.2. Một JWKS công khai trông như thế nào?

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "issuer-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_RSA_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị trên là **placeholder minh họa cấu trúc**, không phải một JWK có thể dùng để xác minh. Với RSA public JWK:
- `n` là modulus công khai.
- `e` là public exponent.
- `kid` là key identifier để định tuyến key trong JWKS.
- `use=sig` cho biết mục đích ký.
- `alg` có thể cung cấp thông tin thuật toán dự kiến, nhưng ứng dụng vẫn phải enforce thuật toán đáng tin.

JWKS dùng cho Resource Server bình thường chỉ nên cung cấp **public key material**, không bao giờ đưa private exponent hay private signing key vào endpoint công khai. Đối với private RSA JWK, trường `d` chứa phần bí mật, tuyệt đối không công bố.

### 2.3. JOSE dependency không phải là JWE auto-configuration

`spring-security-oauth2-jose` cung cấp hạ tầng JWT/JWS và sử dụng Nimbus JOSE + JWT SDK. Không được kết luận rằng chỉ thêm JOSE starter là WebFlux tự động:
- Phát hành JWT.
- Giải mã tất cả JWE tùy thuật toán và key.
- Xác thực OIDC login.
- Tạo OAuth2 Authorization Server.
- Tự biết issuer/audience nào cần chấp nhận.

Các chức năng trên là **những vai trò khác nhau**. Resource Server JWT chủ yếu **xác minh access token được ký**, không giữ private signing key. Nếu cần JWE hoặc một profile token đặc thù, phải xác định cơ chế giải mã/chứng thực và kiểm tra khả năng của decoder/validator tương ứng.

## 3. Phân biệt ba vai trò OAuth2 thường bị cài nhầm starter

| Vai trò | Nhiệm vụ | Spring Boot starter phù hợp |
| --- | --- | --- |
| **OAuth2 Client** | Chuyển user tới Authorization Server, xử lý authorization code, có thể đăng nhập OIDC hoặc gọi API khác | `spring-boot-starter-oauth2-client` |
| **Resource Server** | Nhận Bearer access token và bảo vệ API | `spring-boot-starter-oauth2-resource-server` |
| **Authorization Server** | Phát hành tokens, quản lý clients/grants/keys theo sản phẩm auth server | Spring Authorization Server và cấu hình riêng, **không** được bật chỉ bởi Resource Server starter |

Một ứng dụng có thể đóng nhiều vai trò, nhưng không nên thêm tất cả starters “cho chắc” mà chưa có use case.

Ví dụ:
- Frontend server A đăng nhập user bằng OIDC, đóng vai OAuth2 Client.
- API B nhận `Authorization: Bearer access_token` và chỉ xác minh/authorize, đóng vai Resource Server.
- Identity Provider C phát token/JWKS, đóng vai Authorization Server.

**Cảnh báo:** ID Token của OIDC dùng cho client xác nhận authentication của user, **không nên được dùng thay access token để gọi Resource Server**. Audience của ID Token thường là OAuth2 client ID, không phải `catalog-api`; nếu Resource Server chỉ kiểm chữ ký và quên `aud`, có thể nhận nhầm ID Token.

## 4. Cài dependencies bằng Gradle

### 4.1. Spring Boot 3.3.13, Gradle 8.x, Java 17+

Project tối thiểu có REST WebFlux và OAuth2 Resource Server:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Không cần** thêm một dependency JOSE riêng khi dùng Boot starter Resource Server theo dependency graph chuẩn. Starter kéo cả Spring Security Resource Server và phần JOSE cần cho JWT.

`spring-boot-starter-webflux` là HTTP stack reactive; `spring-boot-starter-oauth2-resource-server` bổ sung Spring Security Resource Server. Nếu thêm `spring-boot-starter-web` Servlet vào cùng app một cách vô ý, Spring Boot có thể chọn MVC thay WebFlux theo classpath và code `ServerHttpSecurity` không có hiệu lực như bạn mong đợi.

Dự án được cố định ở Spring Boot 3.3.13 để nhất quán với các ví dụ Java 17/Spring Security 6.3 trong bài; không xem đây là lời khuyên dùng phiên bản đã cũ cho hệ thống production vào thời điểm đọc. Dùng phiên bản được hỗ trợ và kiểm thử nâng cấp khi triển khai thực.

### 4.2. Nếu không dùng Spring Boot starter

Một dự án quản lý dependency trực tiếp cần ít nhất hai mô-đun Spring Security, bên cạnh WebFlux/Security core:

~~~groovy
// ĐOẠN TRÍCH cho project tự quản lý Spring Security BOM.
implementation 'org.springframework.security:spring-security-oauth2-resource-server'
implementation 'org.springframework.security:spring-security-oauth2-jose'
~~~

Đừng sao chép hai dòng này vào project có starter chỉ để lặp dependency. Khi không dùng Boot, bạn phải quản lý **phiên bản tương thích** cho Spring Security, Spring Framework, Reactor và Nimbus. Hãy dùng BOM/platform thích hợp, không tự ghép các bản phát hành không tương thích.

### 4.3. Kiểm tra dependency tree

Từ thư mục project:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-security-oauth2-resource-server --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-security-oauth2-jose --configuration runtimeClasspath
~~~

Nếu dùng Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-jose --configuration runtimeClasspath
~~~

Tìm các module:
- `spring-security-oauth2-resource-server`.
- `spring-security-oauth2-jose`.
- `spring-security-oauth2-core` và các Spring Security components phụ trợ.
- Nimbus JOSE + JWT được kéo bởi thành phần JOSE.
- Reactor/WebFlux được kéo bởi starter WebFlux.

**Không dự đoán cứng cây phụ thuộc hay tất cả các version transitive**: kết quả thực tế phụ thuộc vào BOM, plugin, exclusions và Gradle resolution. Chạy `dependencyInsight` để thấy dependency đã đến từ đâu, có bị exclude hoặc override hay không.

Nếu project có nhiều đường kéo cùng một module, Gradle thường resolve một phiên bản chứ không đưa “hai bản JOSE” đồng thời vào cùng runtime. Nhưng version override sai vẫn có thể làm thiếu class/method. Đừng tự fix bằng cách thêm một phiên bản Nimbus tùy ý mà không kiểm BOM.

## 5. Cài dependencies bằng Maven

Với Spring Boot parent quản lý versions:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-jwt-resource</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Kiểm:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-oauth2-resource-server
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-oauth2-jose
~~~

**Chọn một hệ thống build**: Gradle hoặc Maven. File `build.gradle` và `pom.xml` ở hai mục là **hai phương án thay thế**, không có nghĩa ứng dụng phải dùng cả hai.

## 6. Cấu hình nguồn xác minh JWT

Có nhiều cách cung cấp public keys và issuer. Phương án khuyến nghị phụ thuộc vào kiến trúc Authorization Server.

### 6.1. Chỉ `issuer-uri` — discovery từ Authorization Server

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          audiences:
            - catalog-api
~~~

Issuer URI phải khớp claim `iss` mà Authorization Server thật phát hành. Spring Security có thể dựa vào metadata OIDC/OAuth2 Authorization Server để khám phá vị trí JWKS. Khi decoder biết public keys, nó xác minh JWT được ký bởi AS.

Khi dùng `issuer-uri`, cần lưu ý:
- Provider phải có metadata endpoint theo cấu trúc Spring Security hỗ trợ, hoặc phải khai báo `jwk-set-uri` trực tiếp.
- Metadata/JWKS endpoint phải reachable qua HTTPS và đã được tin cậy.
- Cách khởi tạo decoder và thời điểm discovery có thể thay đổi giữa version/thiết lập; với một số đường cấu hình, việc app khởi động có thể phụ thuộc availability của Authorization Server. Không dựa vào giả định chung rằng “issuer-uri sẽ không bao giờ gọi mạng lúc startup”.
- Đừng tạo `issuer-uri` từ query parameter/user input của mỗi request. Nó phải là allowlisted trust configuration.
- `audiences` giúp khẳng định token thực sự được phát **cho API này** chứ không chỉ là JWT của cùng issuer dùng cho một hệ thống khác.

### 6.2. `issuer-uri` + `jwk-set-uri` — tránh metadata discovery để tìm JWKS

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/jwks
          audiences:
            - catalog-api
~~~

Trường hợp này:
- `jwk-set-uri` chỉ ra nơi lấy public keys.
- Không cần gọi discovery endpoint để tìm địa chỉ JWKS khi khởi tạo.
- `issuer-uri` vẫn được cung cấp để **kiểm claim `iss`**.
- Không có nghĩa JWKS luôn được tải và cache thành công nếu IdP bị outage; việc lấy key mới hoặc key `kid` chưa cache vẫn phụ thuộc network.
- Không có nghĩa backend không bao giờ cần gọi IdP trong runtime.
- JWK URL là một URL hạ tầng đáng tin **được cấu hình trước**, không lấy từ header `jku`/`x5u` của token.

**Chỉ đặt `jwk-set-uri` mà quên `issuer-uri` có thể làm mất validation issuer mặc định của cấu hình Boot**, tùy validator đã chọn. Hãy luôn xác định và kiểm được cả issuer và audience; không tin rằng chữ ký hợp lệ từ một key tự nó chứng minh token dành cho đúng ứng dụng.

### 6.3. `public-key-location` — một public key tĩnh

Khi Authorization Server không công bố JWKS nhưng có public key ổn định và được phân phối an toàn:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/idp-public.pem
          audiences:
            - catalog-api
~~~

Đây là lựa chọn kiến trúc, không phải mặc định lý tưởng:
- Key rotation phải được tổ chức riêng vì public key tĩnh không tự cập nhật như JWKS.
- Phải cấu hình/kiểm **issuer validation** tương ứng, không nghĩ public key tĩnh tự kiểm `iss`.
- Chỉ đóng gói **public verification key** trong Resource Server; không đẩy private key của AS vào file resource.
- Property `public-key-location` đòi public key đúng định dạng mà Spring Boot decoder hỗ trợ.
- Khi có custom `ReactiveJwtDecoder`, phải đặt validator cho `iss`, `aud` và thời gian để tránh mất checks của Boot.

### 6.4. Khi nào dùng `ReactiveJwtDecoder` do ứng dụng cung cấp?

Trong WebFlux, decoder interface là:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
~~~

Một đoạn cấu hình trích:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withJwkSetUri("https://idp.example.test/jwks")
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
            "https://idp.example.test/issuer"));

    return decoder;
}
~~~

**Đây không phải toàn bộ cấu hình production:** ví dụ minh họa đăng ký `ReactiveJwtDecoder` và kiểm issuer/time, nhưng chưa thêm audience validation. Khi bạn tự cung cấp decoder bean, nó **thay thế con đường Boot auto-configure decoder**; phải bảo toàn tất cả security validators cần thiết. Không copy code trên rồi quên `aud`.

Sử dụng `ReactiveJwtDecoders.fromIssuerLocation(issuer)` là một đường API hỗ trợ tự xây decoder từ issuer discovery với các validators mặc định phù hợp. Chọn cấu hình properties là đơn giản nhất nếu không cần tùy biến.

## 7. Đường đi của Bearer JWT trong WebFlux Security

~~~text
GET /api/catalog
Authorization: Bearer <JWT>
       │
       ▼
Spring Security WebFilterChain
       │
       ▼
Bearer token authentication
       │
       ▼
ReactiveJwtDecoder.decode(jwt) → Mono<Jwt>
       │
       ├─ Parse định dạng token
       ├─ Verify JWS signature bằng trusted RSA public JWK
       ├─ Reject unsupported / untrusted alg
       ├─ Validate exp / nbf / iss / aud
       └─ Convert claims to Jwt object
       │
       ▼
JwtReactiveAuthenticationManager + authorities converter
       │
       ▼
JwtAuthenticationToken trong SecurityContext (Reactor Context)
       │
       ▼
authorizeExchange:
  hasAuthority("SCOPE_catalog.read")
       │
       ├─ Không có Bearer / invalid token → 401
       ├─ JWT hợp lệ nhưng không có quyền → 403
       └─ JWT hợp lệ và scope đúng → Controller 200
~~~

Các lớp thường gặp trong Spring Security reactive:
- `ReactiveJwtDecoder`: hợp đồng reactive nhận token string và trả `Mono<Jwt>` hoặc lỗi.
- `NimbusReactiveJwtDecoder`: decoder phổ biến dựa trên Nimbus JOSE + JWT SDK.
- `Jwt`: JWT đã được decode/verify theo các validators của decoder.
- `JwtReactiveAuthenticationManager`: áp decoder trong quá trình xác thực.
- `JwtAuthenticationToken`: Authentication sau khi Bearer JWT được chấp nhận.
- `ReactiveSecurityContextHolder`: truy cập Authentication theo Reactor Context, không dựa vào Servlet ThreadLocal.
- `ServerHttpSecurity` / `SecurityWebFilterChain`: HTTP security pipeline của WebFlux.

Không dùng `org.springframework.security.oauth2.jwt.JwtDecoder`/`NimbusJwtDecoder` đồng bộ của Servlet thay cho `ReactiveJwtDecoder` trong `ServerHttpSecurity`. Code này **không tự viết `block()`/`subscribe()`** để truy vấn JWT trên event loop.

### 7.1. Principal và authority mặc định

Với cấu hình Resource Server JWT thông dụng:
- Principal là một `Jwt`, thường có thể lấy bằng `@AuthenticationPrincipal Jwt jwt`.
- `Authentication.getName()` thường dựa vào claim `sub` (có thể tùy converter).
- Các OAuth2 scopes trong claim `scope` hoặc `scp` được map thành authorities có tiền tố `SCOPE_`.

Ví dụ:

~~~json
{
  "sub": "alice-123",
  "scope": "catalog.read catalog.write"
}
~~~

thường tạo authorities:

~~~text
SCOPE_catalog.read
SCOPE_catalog.write
~~~

Rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/catalog")
    .hasAuthority("SCOPE_catalog.read")
~~~

**Không** gọi `hasRole("catalog.read")` rồi kỳ vọng tự khớp scope. `hasRole("X")` thường kiểm authority `ROLE_X`, khác `SCOPE_X`.

### 7.2. Authentication không đồng nghĩa authorization tài nguyên cụ thể

JWT hợp lệ và có `SCOPE_catalog.read` chỉ cho phép **chức năng đọc catalog**, chưa đồng nghĩa user được xem mọi tài liệu tenant khác. Với endpoint `GET /api/orders/{id}`, service/repository vẫn phải kiểm owner/tenant/membership hoặc ACL.

Tương tự, JWT chứa claim `roles` không tự trở thành các Spring Security authorities theo ý muốn; muốn dùng phải định nghĩa converter và nguồn claim đáng tin. Không gán `ROLE_ADMIN` theo email hoặc query parameter.

## 8. Ví dụ WebFlux độc lập: API Catalog nhận JWT

Phần này cung cấp project **có thể build với Java 17+, Spring Boot 3.3.13 và Gradle 8.x**, cấu hình production-style theo issuer/JWKS. Unit/integration tests chạy **offline** bằng decoder khóa public test-only, và JWT được ký RSA thực trong test.

**Giới hạn có chủ đích:** `application.yml` dùng các URL `idp.example.test` làm địa chỉ kiến trúc minh họa. Không có Authorization Server thật tại đó, nên `bootRun` chạy app nhưng không thể chấp nhận token production cho đến khi bạn thay issuer và JWKS bằng provider thật. Test tự tạo RSA keypair và cung cấp một `ReactiveJwtDecoder` test-only, **không gọi IdP bên ngoài**.

### 8.1. Cấu trúc thư mục

~~~text
webflux-jwt-resource/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ResourceApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── CatalogController.java
    │   └── resources/application.yml
    └── test/java/demo/
        └── JwtResourceServerTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-jwt-resource'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm `spring-security-oauth2-jose` phiên bản thủ công vì starter đã cung cấp nó. Không thêm Spring MVC starter để tránh đổi HTTP stack.

### 8.2. `application.yml`: issuer, JWKS và audience

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/jwks
          audiences:
            - catalog-api
~~~

**Đây là endpoint giả định**, không phải một JWT Provider thực. Khi triển khai:
- `issuer-uri` phải khớp chính xác `iss` từ access token của AS (đã tin cậy).
- `jwk-set-uri` phải là endpoint HTTPS do AS công bố theo metadata/documentation.
- `audiences` phải chứa audience mà AS cấp cho API này.
- Cấu hình TLS/truststore DNS, proxy egress và JWKS key rotation theo môi trường.
- Nếu AS không cung cấp JWT access token đúng loại, bạn có thể cần opaque-token introspection, không ép một opaque token qua JWT decoder.

### 8.3. Main class

`src/main/java/demo/ResourceApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig: đúng `ServerHttpSecurity` của WebFlux

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/catalog")
                    .hasAuthority("SCOPE_catalog.read")
                .pathMatchers(HttpMethod.GET, "/api/manage")
                    .hasAuthority("SCOPE_catalog.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

Ý nghĩa:
1. `oauth2ResourceServer(...).jwt(...)` chọn Bearer JWT authentication.
2. `GET /health` công khai, không trả token hay thông tin cá nhân.
3. `GET /api/me` yêu cầu JWT hợp lệ nhưng không thêm scope riêng.
4. `GET /api/catalog` cần `SCOPE_catalog.read`.
5. `GET /api/manage` cần `SCOPE_catalog.write`.
6. `anyExchange().denyAll()` ngăn route chưa được quy định.
7. `httpBasic` và `formLogin` được tắt để API này chỉ dùng Bearer token.
8. **CSRF chưa bị vô hiệu hóa** trong ví dụ; các endpoint demo đều là GET an toàn. Nếu thêm POST/PUT/DELETE, phải thiết kế CSRF theo threat model: API Bearer-only không nhận ambient browser credentials có thể có ngoại lệ cụ thể hoặc dedicated chain, còn API session/cookie vẫn cần CSRF protection.

**Đừng đặt `csrf.disable()` toàn bộ mà không xét có browser cookie/Basic hoặc các endpoint khác trong chain hay không.** Việc lựa chọn JWT resource server không tự xóa rủi ro CSRF ở những credentials khác.

### 8.5. CatalogController: lấy Jwt đã được xác minh

`src/main/java/demo/CatalogController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class CatalogController {

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        ));
    }

    @GetMapping("/api/catalog")
    Mono<Map<String, List<String>>> catalog() {
        return Mono.just(Map.of(
            "items", List.of("webflux", "oauth2", "jwt")
        ));
    }

    @GetMapping("/api/manage")
    Mono<Map<String, String>> manage() {
        return Mono.just(Map.of(
            "capability", "catalog.write"
        ));
    }
}
~~~

Chỉ trả một số field cho mục đích học; **không** trả raw token, authorization header, private key, session ID hoặc toàn bộ claims chưa được phép công khai. `jwt.getSubject()` được lấy từ principal sau decoder, không lấy bằng cách tự Base64-decode token string.

Nếu production sử dụng access token không có issuer được biểu diễn như URI hoặc `sub`, phải có contract token riêng và kiểm rõ ràng trước khi gọi `toString()`; demo/test chủ động tạo đủ `iss` và `sub`.

## 9. Kiểm thử offline JWT ký RSA thật: không cần IdP mạng

Một bài test chỉ dùng `mockJwt()` chứng minh authorization converter/matcher hoạt động, nhưng **không** đi qua chữ ký JWT, issuer, audience hoặc expiration. Muốn kiểm lớp JOSE thực sự, test cần tạo token **được ký bằng private RSA key test-only** và cấu hình `NimbusReactiveJwtDecoder` với **public RSA key tương ứng**.

Quan trọng về kiến trúc:
- **Production Resource Server KHÔNG có private signing key.**
- **Chỉ test code** tạo private key nội bộ để ký access token giả.
- `@TestConfiguration` được import trong test, không nằm trong `src/main`.
- Public decoder trong test phải kiểm issuer, audience và thời gian giống security contract production.
- Test dùng WebTestClient đi qua actual WebFlux security filters (không `mockJwt()`), do đó có thể test 401 do chữ ký sai.

### 9.1. Cách tổ chức test

`src/test/java/demo/JwtResourceServerTests.java`:

~~~java
package demo;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(JwtResourceServerTests.OfflineJwtKeys.class)
class JwtResourceServerTests {

    private static final String ISSUER =
        "https://idp.example.test/issuer";

    @Autowired
    ApplicationContext context;

    @Autowired
    JwtEncoder encoder;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class OfflineJwtKeys {

        @Bean
        KeyPair testSigningKeys() {
            try {
                KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
                generator.initialize(2048);
                return generator.generateKeyPair();
            }
            catch (GeneralSecurityException error) {
                throw new IllegalStateException(error);
            }
        }

        @Bean
        JwtEncoder testJwtEncoder(KeyPair testSigningKeys) {
            RSAKey rsa = new RSAKey.Builder(
                (RSAPublicKey) testSigningKeys.getPublic())
                .privateKey(
                    (RSAPrivateKey) testSigningKeys.getPrivate())
                .keyID("test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<SecurityContext>(
                    new JWKSet(rsa)));
        }

        @Bean
        ReactiveJwtDecoder testJwtDecoder(KeyPair testSigningKeys) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withPublicKey(
                    (RSAPublicKey) testSigningKeys.getPublic())
                    .build();

            OAuth2TokenValidator<Jwt> audienceValidator =
                jwt -> jwt.getAudience() != null
                    && jwt.getAudience().contains("catalog-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "Missing catalog-api audience",
                                null));

            // Signature + standard time/issuer + expected audience.
            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(
                        "https://idp.example.test/issuer"),
                    audienceValidator));

            return decoder;
        }
    }

    // Ký token THẬT trong test bằng RSA private key chỉ có ở test.
    // Dùng encoder khác để mô phỏng token ký sai key.
    private String signed(
            JwtEncoder tokenEncoder,
            String issuer,
            String audience,
            String scope,
            Instant expiration) {

        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice-123")
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(10))
            .notBefore(now.minusSeconds(10))
            .expiresAt(expiration)
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return tokenEncoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private String valid(String scopes) {
        return signed(encoder, ISSUER, "catalog-api", scopes,
            Instant.now().plusSeconds(600));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingBearerTokenIsUnauthorized() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedJwtIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void realSignedTokenCanReadItsSubject() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(valid("catalog.read")))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice-123")
            .jsonPath("$.issuer").isEqualTo(ISSUER);
    }

    @Test
    void scopeCatalogReadBecomesAuthority() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(valid("catalog.read")))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items[0]").isEqualTo("webflux");
    }

    @Test
    void signedTokenWithoutRequiredScopeIsForbidden() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(valid("profile")))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void differentScopeCannotReadManagementEndpoint() {
        client.get().uri("/api/manage")
            .headers(h -> h.setBearerAuth(valid("catalog.read")))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void scopeCatalogWriteCanReadManagementEndpoint() {
        client.get().uri("/api/manage")
            .headers(h -> h.setBearerAuth(valid("catalog.write")))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.capability").isEqualTo("catalog.write");
    }

    @Test
    void wrongIssuerIsUnauthorizedDespiteValidSignature() {
        String token = signed(
            encoder, "https://evil.example", "catalog-api",
            "catalog.read", Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsUnauthorizedDespiteValidSignature() {
        String token = signed(
            encoder, ISSUER, "unrelated-api",
            "catalog.read", Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredJwtIsUnauthorized() {
        String token = signed(
            encoder, ISSUER, "catalog-api", "catalog.read",
            Instant.now().minusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void tamperedSignatureOrUnknownSigningKeyIsRejected() {
        // Public decoder chỉ tin testSigningKeys; dùng keypair thứ hai.
        KeyPair otherKeys;
        try {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            otherKeys = generator.generateKeyPair();
        }
        catch (GeneralSecurityException error) {
            throw new IllegalStateException(error);
        }

        RSAKey wrongRsa = new RSAKey.Builder(
            (RSAPublicKey) otherKeys.getPublic())
            .privateKey((RSAPrivateKey) otherKeys.getPrivate())
            .keyID("test-key")
            .build();

        JwtEncoder otherEncoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<SecurityContext>(
                new JWKSet(wrongRsa)));

        String token = signed(
            otherEncoder, ISSUER, "catalog-api",
            "catalog.read", Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockJwtIsUsefulForAuthorizationButDoesNotCheckSignature() {
        client.mutateWith(
                mockJwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_catalog.read")))
            .get().uri("/api/catalog")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

### 9.2. Các bài test chứng minh gì?

| Test | Mục tiêu | Kỳ vọng |
| --- | --- | --- |
| `healthIsPublic` | Public route không có Bearer | 200 |
| `missingBearerTokenIsUnauthorized` | Protected route không có Bearer | 401 |
| `malformedJwtIsUnauthorized` | Chuỗi không phải JWT hợp lệ | 401 |
| `realSignedTokenCanReadItsSubject` | JWT RSA signature + claims hợp lệ | 200 |
| `scopeCatalogReadBecomesAuthority` | Claim `scope` map thành `SCOPE_catalog.read` | 200 |
| `signedTokenWithoutRequiredScopeIsForbidden` | Token hợp lệ nhưng thiếu quyền | 403 |
| `differentScopeCannotReadManagementEndpoint` | Không dùng scope read thay scope write | 403 |
| `scopeCatalogWriteCanReadManagementEndpoint` | Scope write đúng | 200 |
| `wrongIssuerIsUnauthorizedDespiteValidSignature` | Signature đúng nhưng `iss` sai | 401 |
| `wrongAudienceIsUnauthorizedDespiteValidSignature` | Signature đúng nhưng `aud` sai | 401 |
| `expiredJwtIsUnauthorized` | `exp` quá khứ rõ ràng, vượt clock skew | 401 |
| `tamperedSignatureOrUnknownSigningKeyIsRejected` | Key ký không khớp public key tin cậy | 401 |
| `mockJwtIsUsefulForAuthorizationButDoesNotCheckSignature` | Authorization mock; **bỏ qua decoder thật** | 200 |

Có **13** test methods. Mục tiêu là kết hợp:
- Đường thực: chuỗi Bearer được ký RSA thực, `NimbusReactiveJwtDecoder` kiểm chữ ký, issuer, audience, thời gian, và converter kiểm scope.
- Đường mock: Spring Security Test tạo authentication giả để kiểm authorization mà **không chứng minh chữ ký**.

**Điểm cẩn trọng:** Việc test decoder với một public RSA key test-only không kiểm tra **network JWKS retrieval/rotation**, discovery metadata, SSL/truststore hoặc Authorization Server thật. Các trường hợp đó đòi integration tests với mock JWKS HTTP server hoặc test Authorization Server trong môi trường kiểm thử; không tự khẳng định đã kiểm chỉ vì `mockJwt()` pass.

### 9.3. Vì sao dùng test-only `ReactiveJwtDecoder`?

`application.yml` của production chọn issuer/JWKS URL, còn `OfflineJwtKeys` tạo decoder public RSA từ keypair test. Spring Boot sử dụng bean `ReactiveJwtDecoder` mà test cung cấp thay cho decoder tự tạo từ cấu hình production, nên test không cần gọi `idp.example.test`.

Điều đó hợp lý để test local code/JOSE và quyền. Nhưng chính vì đã override decoder, **test này chưa xác nhận production `issuer-uri`/`jwk-set-uri` trỏ đúng endpoint thật**. Cần bổ sung integration tests với JWKS/discovery và check kết quả deploy.

### 9.4. Chạy test

~~~bash
gradle test
~~~

Hoặc khi có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell/cmd, dùng `gradlew.bat test`. Project Java 17+ cần Gradle tương thích và mạng tải Maven Central ở lần build đầu. **Kỳ vọng 13 test cases pass khi dependency/API phù hợp**, nhưng kết quả thực tế phải được xác minh bằng build/test, không suy luận rằng code đã chạy chỉ từ việc đọc snippet.

### 9.5. Lệnh chạy ứng dụng

~~~bash
gradle bootRun
~~~

Ví dụ public health:

~~~bash
curl -i http://localhost:8080/health
~~~

Expected application behavior nếu server khởi động:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

ok
~~~

Không khẳng định cố định thứ tự/tập headers vì WebFlux server và security response headers có thể khác. Với endpoint protected:

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Kết quả thường là **401 Unauthorized** và `WWW-Authenticate: Bearer`. Token thật phải đến từ Authorization Server có issuer/JWKS đúng với ứng dụng. Ví dụ:

~~~bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_FROM_TRUSTED_AS" \
  http://localhost:8080/api/catalog
~~~

**`ACCESS_TOKEN_FROM_TRUSTED_AS` là placeholder**, không phải JWT hợp lệ. Đừng đưa real access tokens vào terminal logs, screenshots hoặc tài liệu chia sẻ; trong môi trường thật dùng secrets manager/tooling phù hợp và HTTPS.

## 10. Vì sao một số test trả 401 và một số trả 403?

### 10.1. 401 Unauthorized — thất bại ở xác thực Bearer

Các tình huống:
- Không có token trên protected endpoint.
- Token không có ba phần hợp lệ hoặc sai Base64URL/JSON.
- Header `alg` không được decoder chấp nhận.
- JWS signature sai hoặc key `kid` không tìm thấy trong JWKS.
- JWT `exp` đã quá hạn hoặc `nbf` ở tương lai ngoài clock skew cho phép.
- Claim `iss` sai issuer đáng tin.
- Claim `aud` không chứa audience API cần nhận.
- Decoder không thể lấy key JWKS cần thiết và request không thể xác minh token (tùy error mapping/server).

Response có thể gồm `WWW-Authenticate: Bearer error="invalid_token"` hoặc các chi tiết khác tùy lỗi. Không log raw token hoặc lộ quá mức nguyên nhân xác minh cho public client.

### 10.2. 403 Forbidden — token đã xác thực nhưng thiếu quyền

Ví dụ JWT hợp lệ:

~~~json
{
  "sub": "alice-123",
  "aud": ["catalog-api"],
  "scope": "profile"
}
~~~

JWT đó có thể truy cập `/api/me` nếu chỉ yêu cầu authenticated, nhưng bị 403 ở `/api/catalog` vì thiếu `SCOPE_catalog.read`. **Không sửa 403 bằng cách tắt Resource Server**, và không nghĩ issuer/audience validation là phần quyền truy cập từng API.

Dùng status code đúng giúp tách hai nhóm lỗi:
- **401:** credential chưa được chấp nhận.
- **403:** credential đã được chấp nhận nhưng không đủ permission ở resource/rule.

Còn `404` là tài nguyên không tồn tại/không lộ tồn tại theo policy, khác với lỗi thiếu dependency/JOSE.

## 11. JWK key rotation: Resource Server không giữ private key

Trong mô hình bất đối xứng:
- Authorization Server giữ private RSA/EC signing key.
- JWKS public công bố key xác minh tương ứng.
- JWT header chứa `kid` cho biết key ký.
- Resource Server chọn public key đúng và kiểm chữ ký.
- Khi AS rotate key, JWKS cập nhật và decoder có thể fetch/cache keys mới theo cơ chế Spring Security/Nimbus.

Timeline:

~~~text
T0  AS ký token bằng private key K1
    JWKS công bố public K1 (kid=K1)

T1  AS chuẩn bị rotate, JWKS công bố K1 + K2
    Một số tokens còn dùng K1, tokens mới có thể dùng K2

T2  AS bắt đầu ký bằng K2
    Resource Servers lấy key K2 khi cần theo policy cache/refresh

T3  Sau thời gian token K1 cũ đã hết hạn và cache ổn định,
    AS mới cân nhắc loại K1 khỏi JWKS
~~~

**Không được** loại public K1 quá sớm nếu vẫn còn access tokens K1 chưa hết hạn (trừ khi bạn chủ động muốn revoke và chấp nhận hậu quả). Hãy kiểm:
- `kid` không trùng giữa các key khác nhau trong cùng JWKS đang active.
- JWKS endpoint có HTTPS, timeout/cache/observability phù hợp.
- Không cho JWT tự chỉ định URL public key tùy ý qua `jku`/`x5u`.
- Resource Server chỉ chấp nhận một tập algorithms mà AS đã thống nhất.
- Khi JWKS gặp outage, hành vi với cached keys và key mới phải được test.
- `iss` và `aud` vẫn được kiểm sau khi signature thành công.

Với static `public-key-location`, key rotation thường cần cập nhật file/deploy/config; với JWKS có thể lấy key công khai mới linh hoạt hơn. **Không lưu private key ở Resource Server chỉ để kiểm JWT**.

## 12. Chọn thuật toán JWS có chủ đích

Trong cấu hình Spring Security JWT thông thường, `NimbusReactiveJwtDecoder` mặc định tin và kiểm tokens RS256; nếu Authorization Server dùng RS512/ES256 hoặc profile khác, hãy cấu hình **theo tài liệu issuer và version thực tế**, không chấp nhận mọi `alg` từ token.

Ví dụ config đổi algorithm (chỉ dùng khi IdP thật phát hành RS512):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/jwks
          jws-algorithms:
            - RS512
          audiences:
            - catalog-api
~~~

Việc thêm RS512 vào allowlist mà AS chỉ ký RS256 có thể làm mọi request JWT bị 401. Đừng giải quyết bằng cách cho phép `alg=none`, hoặc đồng thời cho phép HS*/RS* bừa bãi khiến verifier lẫn lộn symmetric/asymmetric key. Không tự viết JWT signature verification bằng string manipulation; dùng thư viện JOSE đã được cập nhật.

### 12.1. HS256 so với RS256

- **HS256** là HMAC đối xứng: bên ký và bên verify đều cần biết cùng secret. Khi Resource Server biết secret, nó cũng có khả năng ký JWT, làm mở rộng tác động nếu server bị xâm nhập.
- **RS256** là chữ ký RSA bất đối xứng: Resource Server chỉ cần public key. Đây là mô hình thường phù hợp hơn cho nhiều microservices nhận tokens từ một Authorization Server.
- **ES256** là ECDSA bất đối xứng, có yêu cầu key/algorithm riêng.

Không phải “HS256 luôn sai” về mặt thuật toán, nhưng trong kiến trúc microservices cần cân nhắc phạm vi secret và sự tách biệt bên phát hành/kiểm token. Cấu hình `withSecretKey(...)` cho Resource Server chỉ phù hợp với thiết kế tin cậy rõ ràng; không lưu secret mẫu trong repo production.

## 13. Audience, issuer và type validation: phụ thuộc đã đủ chưa?

Ngay cả khi Gradle báo có đủ hai module, API vẫn có thể bị sai bảo mật nếu validation thiếu.

### 13.1. Issuer chỉ ra bên phát hành

`iss` cần trùng issuer configured. Ví dụ `https://idp.company.example/tenant-a` và `https://idp.company.example/tenant-b` là hai trust namespaces khác nhau. Không bỏ đường dẫn tenant hoặc normalize issuer tùy tiện.

### 13.2. Audience chỉ ra nơi được nhận token

`aud` phải chứa API identifier mong đợi như `catalog-api`. Một token cùng issuer nhưng cấp cho `billing-api` không nên được sử dụng tại Catalog API.

Trong Spring Boot 3.3, property:

~~~yaml
spring.security.oauth2.resourceserver.jwt.audiences:
  - catalog-api
~~~

được hỗ trợ khi Boot tự cấu hình decoder. Với custom `ReactiveJwtDecoder`, **tự thiết lập validator audience** như test `OfflineJwtKeys`; cấu hình properties không nhất thiết được áp lên decoder mà bạn tự định nghĩa.

### 13.3. Token type và mục đích sử dụng

Không nhận mọi JWT cùng issuer mà không kiểm nó là **access token dành cho Resource Server**. Ví dụ:
- OIDC ID Token có audience là OAuth2 client ID, không phải Catalog API.
- JWT dùng cho password reset hoặc email verification có cùng chữ ký issuer nhưng mục đích khác.
- Một vài Authorization Servers tuân RFC 9068 và dùng `typ=at+jwt`, đòi thêm rules phù hợp profile.

Nếu ứng dụng yêu cầu RFC 9068, cần các validators/profile checks chuyên biệt chứ không chỉ chữ ký và `scope`. Khi chọn một thuật toán/type, phải kiểm thật với Authorization Server production, không đoán qua ví dụ.

## 14. Khi gặp lỗi dependency hoặc cấu hình

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm được `NimbusReactiveJwtDecoder` | Thiếu `spring-security-oauth2-jose` hoặc bị exclude | Dùng Boot starter, kiểm `runtimeClasspath` |
| Compile được Resource Server nhưng JWT decoder không cấu hình | Có resource-server module mà thiếu JOSE/config issuer | Thêm đúng starter và `issuer-uri`/JWKS |
| `JwtDecoder` không dùng được cho WebFlux | Lấy decoder Servlet đồng bộ | Dùng `ReactiveJwtDecoder` |
| Application không start vì issuer metadata unreachable | Discovery/runtime khởi tạo decoder phụ thuộc IdP/network trong cấu hình/version cụ thể | Kiểm URL/TLS/DNS, cân nhắc cấu hình JWKS trực tiếp |
| Startup được nhưng first JWT 401 | Key/JWKS chưa reachable hoặc token không hợp lệ | Xem logs bảo mật đã lọc, issuer/audience/key |
| 401 với JWT chữ ký đúng | `iss`/`aud`/`exp`/`nbf` sai hoặc sai type | Kiểm validators, không tắt hết |
| 401 khi AS rotate key | `kid` mới nhưng JWKS/cache chưa cập nhật | Kiểm JWKS, key overlap, cache/egress |
| 403 sau khi JWT đã được chấp nhận | Scope/authority thiếu | Kiểm `scope`/`scp`, `SCOPE_` prefix và route rule |
| Thêm `spring-boot-starter-oauth2-client` nhưng API chưa nhận Bearer | Client starter không thay Resource Server starter | Dùng Resource Server starter |
| Thêm `spring-boot-starter-web` làm security chain khác | Boot chọn Servlet MVC hoặc khác web application type | Giữ WebFlux stack đúng |
| `mockJwt()` test pass nhưng JWT thật 401 | Mock bỏ qua signature/decoder | Test Bearer token ký thật + JWKS integration |
| ID Token được chấp nhận như access token | Thiếu audience/type policy | Validate aud/typ/token purpose |
| App lấy `sub` nhưng vẫn truy cập sai tenant | Thiếu authorization theo object/tenant | Kiểm local principal mapping, owner/tenant |
| Gateway chặn `Authorization` header | Proxy không forward header cần thiết | Cấu hình forwarding an toàn và không log token |
| `Bearer` có token nhưng sai header encoding | Gửi token ở query/body hoặc dấu cách sai | Dùng `Authorization: Bearer <token>` |
| Custom decoder không kiểm issuer/audience | Thay Boot decoder và quên validators | Dùng `JwtValidators`/audience validator |
| Cache JWKS chưa refresh đúng | Egress/proxy/cache TTL/key rollover | Test rotation và availability |
| SSL/TLS JWKS lỗi | Chứng chỉ/truststore/hostname sai | Sửa trust chain, không disable certificate check |

### 14.1. Kiểm log nhưng không để lộ token

Trong troubleshooting, có thể log:
- Request ID, route, HTTP status, nhóm lỗi `invalid_token`/`insufficient_scope`.
- Issuer cấu hình và tên JWKS endpoint (không chứa credentials).
- `kid`/alg của token khi đã sanitize và không gây lộ dữ liệu nhạy cảm; policy logging tùy tổ chức.
- Trạng thái key cache/network và độ trễ decode.

**Không** log toàn bộ `Authorization: Bearer ...`, private key, secret, refresh token, session cookie, JWT raw payload chứa PII. 401/403 không phải lý do để in token vào log production.

## 15. Các anti-pattern cần tránh

### 15.1. Tự Base64 decode JWT và tin payload

~~~java
// PHẢN VÍ DỤ: không có verify signature hoặc validators!
String payloadBase64 = token.split("\\.")[1];
// Decode rồi lấy roles/sub trực tiếp để cấp quyền là sai.
~~~

JWT payload đọc được **không có nghĩa nội dung đáng tin**. Attacker có thể sửa claims và để một chữ ký bất kỳ. Phải để `ReactiveJwtDecoder` xác minh ký/issuer/audience/expiration trước khi dùng làm identity.

### 15.2. Chấp nhận `alg=none` hoặc algorithm theo ý token

Đừng bỏ signature verification vì “chỉ gọi nội bộ”, và đừng dùng header `alg` từ JWT để tự quyết định logic ký không có allowlist. Resource Server phải tin key và thuật toán theo chính sách cấu hình, không theo metadata chưa được xác minh.

### 15.3. Tin JWKS URL lấy từ JWT

Header `jku`/`x5u` của JWT có thể đưa một URL ngoài. Nếu backend tải key từ URL đó mà không kiểm, attacker có thể tự tạo JWKS chứa public key của mình rồi ký token giả bằng private key tương ứng. Chỉ dùng `jwk-set-uri` cấu hình từ AS đáng tin, hoặc logic allowlist được review.

### 15.4. Chỉ kiểm `exp` mà không kiểm `iss`/`aud`

Token còn hạn của một API khác vẫn không có quyền truy cập Catalog. Thêm issuer/audience validation. Với các claims permission, kiểm scope và object authorization riêng.

### 15.5. Đặt private signing key trong Resource Server

Resource Server không cần private key để verify RS256. Đẩy private key vào mọi service sẽ làm tăng blast radius và vi phạm separation of duties. Test-only private key nằm ở `src/test` được tạo runtime chỉ để minh họa; nó không phải pattern production.

### 15.6. Copy cấu hình Servlet vào reactive

~~~java
// KHÔNG DÙNG trong WebFlux:
HttpSecurity http; // Servlet security DSL
JwtDecoder decoder; // synchronous decoder
~~~

Đúng stack là `ServerHttpSecurity` và `ReactiveJwtDecoder`. Nếu cần logic custom reactive, compose `Mono`/`Flux` thay vì `block()` trên Netty event loop.

### 15.7. Tưởng có JOSE là tự có JWT login hoặc JWT minting

Resource Server nhận và verify tokens; login/OIDC redirect là OAuth2 Client, còn phát hành JWT là Authorization Server. JOSE library hỗ trợ primitives cần thiết, nhưng không tự mang lại toàn bộ giao thức/cấp phát keys.

## 16. Câu hỏi và bài tập thực hành

**Câu 1.** Nếu dự án không dùng Boot starter, muốn Resource Server JWT cần các module nào?

**Đáp án:** Ít nhất `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose`, cùng WebFlux/Spring Security dependencies tương thích.

**Câu 2.** Với Boot, nên bắt đầu bằng dependency nào?

**Đáp án:** `spring-boot-starter-oauth2-resource-server`; kiểm dependency graph để chắc JOSE được kéo vào.

**Câu 3.** JWT có ba phần là gì?

**Đáp án:** Header, payload và signature của compact JWS. Base64URL không mã hóa bí mật payload.

**Câu 4.** JOSE dùng để làm gì?

**Đáp án:** Họ đặc tả ký/mã hóa/key JSON như JWS, JWE, JWK/JWKS; Spring Security JOSE module cung cấp JWT decoding/signature support.

**Câu 5.** JWK và JWKS khác nhau thế nào?

**Đáp án:** JWK là một key mô tả bằng JSON; JWKS là tập hợp keys, thường public, dùng cho key rotation.

**Câu 6.** Resource Server cần private RSA key của IdP không?

**Đáp án:** Không. Với RS256 chỉ cần public verification key; private key ở AS.

**Câu 7.** `issuer-uri` cung cấp điều gì?

**Đáp án:** Cho biết issuer đáng tin, có thể hỗ trợ discovery và kiểm `iss` theo cấu hình.

**Câu 8.** Khi thêm `jwk-set-uri` cạnh issuer thì được gì?

**Đáp án:** Chỉ định JWKS trực tiếp, không cần discovery để tìm JWKS URL, vẫn có thể validate `iss` khi issuer được cấu hình.

**Câu 9.** Chỉ có JWKS nhưng không audience validation có an toàn chưa?

**Đáp án:** Chưa. Token cùng issuer nhưng cấp cho API khác vẫn có thể dùng sai; kiểm `aud` của resource.

**Câu 10.** `scope=catalog.read` thành authority gì theo mặc định?

**Đáp án:** `SCOPE_catalog.read`.

**Câu 11.** Tại sao `hasRole("catalog.read")` không khớp scope?

**Đáp án:** `hasRole` dùng prefix `ROLE_`; scopes mặc định dùng `SCOPE_`. Dùng `hasAuthority("SCOPE_catalog.read")`.

**Câu 12.** 401 khác 403 thế nào?

**Đáp án:** 401 khi Bearer token thiếu/không hợp lệ; 403 khi token đã chấp nhận nhưng thiếu quyền route.

**Câu 13.** `mockJwt()` kiểm được chữ ký RSA không?

**Đáp án:** Không. Nó giả lập authentication để kiểm authorization, bỏ qua decoder. Dùng signed token + decoder trong integration tests.

**Câu 14.** JWKS có thể công bố public RSA exponent/modulus không?

**Đáp án:** Có; public key dùng verify. Không công bố private exponent `d`.

**Câu 15.** Nếu IdP dùng RS512 mà decoder chỉ trust RS256 thì sao?

**Đáp án:** Token bị từ chối; phải cấu hình algorithm allowlist phù hợp AS đã xác minh, không mở mọi thuật toán.

**Câu 16.** Dùng ID Token của OIDC gọi Catalog Resource Server có đúng không?

**Đáp án:** Không. Resource Server nên nhận access token dành cho API, kiểm `aud`/purpose và profile, không dùng ID Token làm bearer access credential.

**Câu 17.** JWT hợp lệ có `SCOPE_catalog.read` cho user A xem order user B được không?

**Đáp án:** Không nếu business policy không cho. Cần kiểm owner/tenant ở tầng service/repository.

**Câu 18.** Vì sao key rotation nên công bố K1 và K2 chồng lấn?

**Đáp án:** Để các tokens ký K1 chưa hết hạn và tokens K2 mới cùng verify được trong giai đoạn chuyển đổi.

**Câu 19.** JWT có `jku=https://evil.example/jwks` thì Resource Server có nên tải không?

**Đáp án:** Không. Key source phải từ trust configuration của issuer đã được phê duyệt, không từ URL do token đề xuất.

**Câu 20.** Một API chỉ có GET nhưng dùng Bearer token đã cần tắt CSRF không?

**Đáp án:** Không nhất thiết. GET là safe method nên default CSRF không yêu cầu token. Nếu thêm POST/PUT và app chỉ Bearer-only, hãy đánh giá credential model rồi mới quyết định policy.

**Câu 21.** Khi custom `ReactiveJwtDecoder`, `audiences` property vẫn chắc chắn có hiệu lực không?

**Đáp án:** Không nên giả định. Bean custom thay Boot auto decoder; phải tự thiết lập và test validators.

**Câu 22.** Spring Security Resource Server có tự tạo endpoint `/.well-known/jwks.json` không?

**Đáp án:** Không. JWKS là nguồn keys của Authorization Server hoặc hạ tầng riêng. Resource Server thường **tiêu thụ** JWKS, không tự phát signing keys.

**Câu 23.** JWE có tự được decoder JWT JWS thông dụng hỗ trợ không?

**Đáp án:** Không được mặc định giả định; JWE là định dạng mã hóa với key/algorithm/decryption riêng, cần thiết kế decoder phù hợp.

**Câu 24.** Khi dependency tree có JOSE nhưng vẫn 401, nên thêm dependency lần nữa?

**Đáp án:** Không. Kiểm invalid signature, issuer/audience, exp, JWKS, algorithm và HTTP header.

## 17. Checklist triển khai Resource Server JWT an toàn

### Dependencies và cấu hình

- [ ] Project thực sự chạy WebFlux, không nhầm `spring-boot-starter-web` Servlet.
- [ ] Có `spring-boot-starter-oauth2-resource-server`; nếu không dùng starter thì có đủ Resource Server + JOSE modules.
- [ ] Spring Boot BOM/versions đồng bộ với Spring Security/Framework/Reactor/Nimbus.
- [ ] `gradle dependencyInsight` hoặc `mvn dependency:tree` xác nhận dependency graph thực.
- [ ] `issuer-uri` trỏ tới issuer đã được xác minh và khớp `iss`.
- [ ] JWKS endpoint HTTPS được cấu hình từ IdP đáng tin, không lấy từ token.
- [ ] API yêu cầu audience đúng; `aud` sai bị 401.
- [ ] JWS algorithms allowlist khớp IdP; không chấp nhận `none`/algorithm confusion.
- [ ] Có handling cho key rotation, cache, network outage và clock skew.
- [ ] Không đặt private signing keys trong Resource Server.

### Spring Security và quyền

- [ ] `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)` chạy trong đúng `SecurityWebFilterChain`.
- [ ] Route chưa công bố bị `denyAll` hoặc chính sách allowlist rõ ràng.
- [ ] Scopes được map đúng `SCOPE_`; không nhầm `ROLE_`.
- [ ] `JwtAuthenticationToken`/principal không bị lấy từ nguồn unverified.
- [ ] `sub` không tự là local UUID/role/tenant, phải map identity và kiểm quyền resource.
- [ ] ID Token/refresh token không được chấp nhận sai chỗ access token.
- [ ] Không dùng JWT decode Base64 tự viết để cấp quyền.
- [ ] CORS/CSRF được thiết kế theo browser credential delivery và topology.
- [ ] Không log raw tokens, secrets hoặc thông tin riêng tư.

### Kiểm thử và vận hành

- [ ] GET public → 200; protected no token → 401.
- [ ] Malformed, expired, wrong signature, wrong issuer, wrong audience → 401.
- [ ] Signed JWT hợp lệ đúng scope → 200.
- [ ] Signed JWT hợp lệ sai scope → 403.
- [ ] Có tests không dùng mock cho signature, và có test `mockJwt()` được ghi rõ giới hạn.
- [ ] Có integration test riêng cho discovery/JWKS URL/key rotation ngoài test RSA local.
- [ ] HTTPS, proxy Authorization header forwarding và timeout/key cache được quan sát.
- [ ] Có alert khi tỷ lệ 401 tăng bất thường hoặc JWKS fetch lỗi.
- [ ] Không auto-disable certificate validation hay tin host ngoài whitelist.
- [ ] Sử dụng phiên bản Boot/Security còn hỗ trợ cho production, kiểm thử nâng cấp.

## 18. Tài liệu tham khảo

- Spring Security — Reactive OAuth2 Resource Server JWT (minimal dependencies, issuer, JWKS, validators): https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 WebFlux overview (Resource Server, ReactiveJwtDecoder): https://docs.spring.io/spring-security/reference/reactive/oauth2/index.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Testing OAuth2/JWT with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Boot 3.3 — Resource Server and issuer/JWKS/audiences properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security 6.3 API — NimbusReactiveJwtDecoder: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- IETF RFC 7515 — JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
- IETF RFC 7516 — JSON Web Encryption (JWE): https://www.rfc-editor.org/rfc/rfc7516
- IETF RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- IETF RFC 7518 — JSON Web Algorithms (JWA): https://www.rfc-editor.org/rfc/rfc7518
- IETF RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- IETF RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700

**Ghi nhớ:** Một WebFlux Resource Server xử lý JWT không chỉ cần “đọc một chuỗi JWT”: nó cần module Resource Server **và JOSE**, public keys đáng tin, signature/issuer/audience/time validators và authorization theo scope/tenant. Spring Boot starter `spring-boot-starter-oauth2-resource-server` là cách gọn nhất để có dependency graph đúng; sau đó cấu hình `issuer-uri`/`jwk-set-uri`/`audiences` và `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)`. Trong kiểm thử, phân biệt rõ **JWT RSA ký thật** với `mockJwt()` chỉ kiểm quyền. Không đưa private key vào Resource Server production và không nhận ID Token thay access token.
