# Tách URL, audience, thông tin xác thực theo môi trường

Khi triển khai **Spring Security OAuth 2.0 / OIDC Resource Server**, ứng dụng thường chạy qua nhiều môi trường như **local**, **development (dev)**, **staging** và **production (prod)**. Các môi trường có thể dùng cùng một mã nguồn nhưng lại kết nối đến những Authorization Server, API, audience và kho bí mật khác nhau. Nếu đặt các giá trị ấy trực tiếp trong code hoặc dùng nhầm cấu hình giữa môi trường, một API có thể từ chối mọi request hợp lệ hoặc chấp nhận token được cấp cho hệ thống không đúng đối tượng.

Vì vậy, một phần quan trọng của bước khởi tạo là **tách các giá trị phụ thuộc môi trường khỏi logic bảo mật**:

- **URL/URI** chỉ rõ ứng dụng gọi đến địa chỉ nào, lấy metadata hoặc khóa xác minh ở đâu.
- **Issuer và audience** xác định token đến từ nguồn nào và có được dành cho API này hay không.
- **Thông tin xác thực (credentials/secrets)** cho biết dịch vụ nào cần chứng minh danh tính với hệ thống khác và bí mật đó được cung cấp, lưu giữ, quay vòng như thế nào.

Ba nhóm cấu hình có ý nghĩa khác nhau; không thể thay thế audience bằng URL của API hoặc dùng `client-secret` như một cách kiểm tra JWT. Bài học sử dụng ví dụ **Orders API** làm Resource Server, **Shop Web** làm OAuth2 Client và **Identity Server** làm Authorization Server.

## 1. Vì sao phải tách theo môi trường?

Giả sử hệ thống có ba môi trường độc lập:

| Thành phần / giá trị | Dev | Staging | Production |
| --- | --- | --- | --- |
| Base URL của Orders API | `https://orders.dev.example.test` | `https://orders.staging.example.test` | `https://orders.example.com` |
| Issuer tin cậy | `https://id.dev.example.test/realms/shop` | `https://id.staging.example.test/realms/shop` | `https://login.example.com/realms/shop` |
| Audience Orders API yêu cầu | `orders-api-dev` | `orders-api-staging` | `orders-api` |
| JWKS endpoint | URL JWKS của issuer dev | URL JWKS của issuer staging | URL JWKS của issuer production |
| Client registration / credentials | Bộ riêng cho dev | Bộ riêng cho staging | Bộ riêng cho production |
| Dữ liệu và chính sách | Dữ liệu kiểm thử | Dữ liệu tiền sản xuất | Dữ liệu thật |

Các URL trên là **địa chỉ minh họa**, không phải endpoint của một nhà phát hành cụ thể. Audience cũng là giá trị hợp đồng minh họa: một Authorization Server khác có thể chọn URI như `https://orders.example.com` thay vì chuỗi `orders-api`.

Khi tách như vậy, một access token từ dev không được production tin cậy chỉ vì hai môi trường cùng dùng thuật toán RS256 hoặc có claim `scope = orders.read`. Production phải xác minh **issuer, chữ ký, audience, thời gian và chính sách** của chính mình.

### Ba lỗi cấu hình điển hình

1. **Dev API dùng nhầm issuer production:** Developer không gọi được API bằng token dev vì issuer sai; nghiêm trọng hơn, dev vô tình nhận token production nếu cấu hình tin cậy sai.
2. **Issuer đúng nhưng audience lấy từ môi trường khác:** Token staging được phát cho `orders-api-staging`, nhưng API mong `orders-api` nên trả 401 dù token có chữ ký hợp lệ.
3. **Dùng lại client secret giữa các môi trường:** Secret production bị đưa vào file cấu hình dev, log hoặc máy cá nhân; phạm vi ảnh hưởng của một lần lộ bí mật vượt khỏi môi trường kiểm thử.

Các lỗi ấy không được giải quyết bằng cách bỏ kiểm tra `iss`, `aud` hoặc tắt xác minh token; cần sửa **đúng nguồn cấu hình** và hợp đồng cấp token.

## 2. Phân biệt từng loại địa chỉ và định danh

Nhìn vào một ứng dụng OAuth 2.0, có nhiều URI trông tương tự nhưng có trách nhiệm riêng:

| Giá trị | Dùng cho việc gì? | Ai cần sử dụng? | Có bắt buộc là bí mật? |
| --- | --- | --- | --- |
| **API base URL** | Địa chỉ mà Client gửi request, ví dụ `https://orders.example.com` | OAuth2 Client, gateway, caller | Không |
| **Issuer URI** | Định danh nhà phát hành, so khớp claim `iss` | Resource Server; OAuth2/OIDC Client theo luồng | Không |
| **Authorization endpoint** | Nơi Client chuyển người dùng đến xin quyền/xác thực | Client tương tác với người dùng | Không |
| **Token endpoint** | Nơi Client trao đổi code hoặc dùng grant để nhận token | OAuth2 Client | Không; nhưng credential gửi đến đây có thể là bí mật |
| **JWKS URI** | Nơi Resource Server lấy khóa công khai để kiểm tra JWS/JWT | Resource Server và các bên cần xác minh chữ ký | Không; khóa **công khai** không phải private key |
| **Introspection URI** | Nơi API hỏi trạng thái opaque token | Resource Server dùng introspection | Không; nhưng credential gọi endpoint này thường là bí mật |
| **Audience (`aud`)** | Định danh đối tượng nhận access token | Authorization Server phát; Resource Server kiểm tra; Client có thể cần xin đúng resource | Không |
| **Client ID** | Định danh Client được đăng ký với Authorization Server | OAuth2 Client và Authorization Server | Thông thường không |
| **Client secret** | Credential của confidential Client | Client cần xác thực với Authorization Server | **Có** |
| **Private signing key** | Khóa riêng để Authorization Server ký token | Authorization Server hoặc hệ thống ký được ủy quyền | **Có, rất nhạy cảm** |

**Issuer không nhất thiết là URL của trang đăng nhập**, và `aud` không nhất thiết là URL có thể mở trên trình duyệt. Mỗi giá trị phải khớp quy ước được Authorization Server thực sự công bố/phát hành.

### 2.1. Issuer URI so khớp claim `iss`

Token JWT minh họa:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-481",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

Orders API production phải chỉ tin issuer mà tổ chức đã cấu hình. Giá trị `iss` là một định danh có ngữ nghĩa chính xác, không phải phép so khớp “cùng tên miền là được”.

Trong Spring Security, property thường dùng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
~~~

Khi sử dụng issuer discovery, Resource Server có thể tìm metadata và vị trí JWKS theo các quy tắc được hỗ trợ. Issuer trong cấu hình phải khớp issuer thực tế; không tùy tiện thay đường dẫn realm, thêm/bớt hậu tố hoặc đổi host qua proxy rồi mặc nhiên xem là cùng issuer.

### 2.2. JWKS URI phục vụ xác minh chữ ký

Ví dụ một Identity Provider cung cấp JWKS tại:

~~~text
https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Đây là **ví dụ một kiểu đường dẫn**, không phải chuẩn URL cố định cho mọi Authorization Server. Hãy lấy địa chỉ JWKS từ metadata hoặc tài liệu tích hợp của issuer tương ứng.

Resource Server dùng JWK phù hợp để xác minh chữ ký JWS. Tham số `kid` trong token có thể giúp chọn khóa công khai từ tập khóa tin cậy; API không được tải khóa từ một URL tùy ý do token chưa xác minh tự cung cấp rồi tin URL đó.

Nếu chọn cấu hình **cả** `issuer-uri` và `jwk-set-uri`, có thể chỉ định rõ JWKS để giảm sự phụ thuộc vào metadata discovery khi startup, trong khi vẫn giữ kiểm tra claim issuer. Cấu hình phải chắc chắn cả hai cùng thuộc **một** nhà phát hành được tin cậy.

### 2.3. Audience là định danh logic cần được issuer cấp

Giả sử có hai API cùng dùng Identity Server:

~~~text
Orders API: audience = orders-api
Billing API: audience = billing-api
~~~

Access token có `aud = billing-api` **không được** Orders API chấp nhận, dù cùng issuer và cùng cặp khóa ký. Nếu hệ thống dùng audience là URL tài nguyên, API cần so khớp đúng giá trị URL theo hợp đồng, không tự suy từ hostname request đến.

Trong một số hệ thống, Client có thể xin audience đích thông qua **resource indicator** hoặc tham số do nhà phát hành cung cấp. **Client chỉ đề nghị**; Authorization Server quyết định audience ghi vào token và Resource Server xác minh giá trị thực tế.

## 3. Thiết kế cấu hình: cùng mã nguồn, khác giá trị

Trong Spring Boot, nên giữ logic SecurityFilterChain và JWT validation trong code chung, đồng thời đưa thông tin môi trường vào **externalized configuration**: biến môi trường, hệ thống cấu hình triển khai, Spring profiles hoặc secret manager.

Ví dụ một bộ biến tối thiểu cho Orders API nhận JWT:

| Biến môi trường | Vai trò | Ví dụ production |
| --- | --- | --- |
| `SPRING_PROFILES_ACTIVE` | Chọn profile phục vụ cấu hình Spring | `prod` |
| `OAUTH_ISSUER_URI` | Issuer đáng tin của API | `https://login.example.com/realms/shop` |
| `OAUTH_JWKS_URI` | JWKS dùng xác minh chữ ký | `https://login.example.com/realms/shop/protocol/openid-connect/certs` |
| `OAUTH_API_AUDIENCE` | Audience của API | `orders-api` |
| `ORDERS_PUBLIC_BASE_URL` | Base URL công bố tới Client, nếu ứng dụng cần | `https://orders.example.com` |

**Không có `OAUTH_CLIENT_SECRET` trong danh sách tối thiểu này** vì Resource Server xác minh JWT bằng **khóa công khai**. Secret có thể cần cho những vai trò khác, chẳng hạn OAuth2 Client hoặc Resource Server dùng introspection đối với opaque token.

### 3.1. Cách A: dùng biến môi trường cho mọi giá trị thay đổi

Tạo `src/main/resources/application.yml` dùng placeholder:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
  public-base-url: ${ORDERS_PUBLIC_BASE_URL}
~~~

Spring Boot sẽ đọc các biến môi trường khi giải quyết placeholder. Các placeholder **không có default** có ích khi giá trị là bắt buộc: môi trường triển khai thiếu thông tin sẽ được phát hiện khi property được sử dụng, thay vì vô tình dùng URL localhost hoặc production làm giá trị dự phòng.

Ba môi trường cung cấp những giá trị khác nhau:

~~~text
# DEV
OAUTH_ISSUER_URI=https://id.dev.example.test/realms/shop
OAUTH_JWKS_URI=https://id.dev.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api-dev
ORDERS_PUBLIC_BASE_URL=https://orders.dev.example.test

# STAGING
OAUTH_ISSUER_URI=https://id.staging.example.test/realms/shop
OAUTH_JWKS_URI=https://id.staging.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api-staging
ORDERS_PUBLIC_BASE_URL=https://orders.staging.example.test

# PRODUCTION
OAUTH_ISSUER_URI=https://login.example.com/realms/shop
OAUTH_JWKS_URI=https://login.example.com/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
ORDERS_PUBLIC_BASE_URL=https://orders.example.com
~~~

Khối trên là **bảng minh họa tên biến và giá trị**, không phải tệp `.env` duy nhất để nạp nguyên xi cho mọi môi trường. CI/CD hoặc hệ thống chạy ứng dụng phải cung cấp **chỉ** bộ giá trị của môi trường đang triển khai.

Ưu điểm: artifact ứng dụng có thể giống nhau giữa các môi trường, và không cần rebuild chỉ để thay endpoint hoặc audience. Nhược điểm: hệ thống triển khai phải có cơ chế phân phối, kiểm soát và kiểm tra cấu hình đầy đủ.

### 3.2. Cách B: Spring profiles cho thông tin công khai

Nếu URL/issuer/audience ổn định theo môi trường, có thể lưu các giá trị **không bí mật** trong file theo profile:

`src/main/resources/application-dev.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.dev.example.test/realms/shop
          jwk-set-uri: https://id.dev.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api-dev
~~~

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api
~~~

Khi chạy production, hệ thống triển khai đặt:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Dev dùng `SPRING_PROFILES_ACTIVE=dev`; staging có file `application-staging.yml` tương ứng. Các file profile ở đây chứa **địa chỉ công khai và định danh**, không chứa client secret hoặc private signing key. Những thông tin bí mật luôn được cung cấp từ cơ chế quản lý bí mật của môi trường.

**Chọn profile không tự động tạo ranh giới bảo mật.** Nếu production bị chạy với profile dev hoặc config override sai, ứng dụng có thể trỏ nhầm issuer. Việc triển khai phải kiểm soát giá trị hiệu lực, quyền sửa cấu hình và các ràng buộc cần xác minh lúc khởi động.

### 3.3. Khi nào nên ưu tiên cách nào?

| Tiêu chí | Externalized environment variables | Spring profile files |
| --- | --- | --- |
| Artifact giống nhau giữa các môi trường | Dễ thực hiện | Có thể thực hiện nếu mọi profile cùng được đóng gói |
| Thay endpoint/audience mà không build lại | Có | Cần override ngoài hoặc build lại nếu sửa file đóng gói |
| Kiểm tra thay đổi qua code review | Cấu hình ở kho triển khai/IaC | Giá trị public được review cùng mã nguồn |
| Quản lý secrets | Kết hợp secret manager/Kubernetes Secret/CI secrets | Vẫn cần secret manager; **không commit secrets vào profile** |
| Rủi ro chính | Thiếu/sai biến trong runtime | Chọn nhầm profile hoặc profile bị override |

Hai cách có thể kết hợp: lưu tên property và cấu trúc chung trong code; giữ những URL public ổn định trong profile; cho phép override qua biến môi trường khi triển khai. Điều quan trọng là **chỉ có một nguồn sự thật đã được kiểm soát cho mỗi môi trường**, với cơ chế phát hiện override bất ngờ.

## 4. Cấu hình JWT Resource Server kiểm tra audience đúng môi trường

**Bật Resource Server không tự có nghĩa mọi access token cùng issuer đều đúng audience.** Cần quy định rõ audience mà Orders API được phép nhận và áp dụng kiểm tra khi xác minh token.

Ví dụ sử dụng **Spring Boot 3 và Spring Security 6**, đọc ba giá trị từ `application.yml` như mục 3.1:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Một ví dụ `JwtDecoder` với `NimbusJwtDecoder` và validator:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ApiJwtConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        // Giữ kiểm tra mặc định về thời hạn, hiệu lực và issuer.
        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Không chấp nhận token do issuer đúng phát cho API khác.
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token has an unexpected audience",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard,
                        audience));

        return decoder;
    }
}
~~~

Mã này làm rõ **audience lấy từ cấu hình môi trường**, không viết cứng `orders-api` trong code. `JwtValidators.createDefaultWithIssuer(issuer)` giữ các kiểm tra mặc định về thời gian và bổ sung issuer. Chữ ký được decoder kiểm tra với JWKS tin cậy trước khi JWT được chấp nhận.

Nếu tự khai báo bean `JwtDecoder`, Spring Boot có thể không còn tạo decoder mặc định từ property. Bởi vậy, phải tự bảo đảm rằng **chữ ký, thuật toán, issuer, thời hạn, audience và điều kiện token profile** được thực thi đầy đủ. Với một token profile có thêm yêu cầu `typ`, Client hoặc cách xác định subject, cần cấu hình validator phù hợp.

### 4.1. SecurityFilterChain dùng chung cho mọi môi trường

Các rule endpoint không nên thay đổi tùy tiện theo dev/staging/prod:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ giả định `/api/**` là REST API **chỉ dùng Bearer token**, không xác thực bằng cookie. Vì thế cấu hình tắt CSRF trong chuỗi filter này và yêu cầu session stateless. Nếu ứng dụng còn phục vụ giao diện web bằng session cookie hoặc phương thức xác thực khác, phải có chính sách CSRF/filter chain tương ứng.

Spring Security thường ánh xạ claim `scope` hoặc `scp` phù hợp thành authorities có tiền tố `SCOPE_`. Ví dụ `scope = "orders.read"` trở thành `SCOPE_orders.read`. Việc thực thi quyền **trên đơn hàng cụ thể** (owner, tenant, trạng thái) vẫn thuộc lớp nghiệp vụ; scope đúng chưa đủ cho phép đọc mọi bản ghi.

### 4.2. Điều gì xảy ra khi chuyển môi trường?

Với cùng mã Java:

- **Dev:** Đọc issuer dev, JWKS dev và `expected-audience = orders-api-dev`.
- **Staging:** Đọc issuer staging, JWKS staging và `expected-audience = orders-api-staging`.
- **Prod:** Đọc issuer production, JWKS production và `expected-audience = orders-api`.

Nếu token từ dev bị gửi vào prod, điều kiện issuer và/hoặc audience không đúng phải khiến token bị từ chối. Nếu công ty dùng **cùng một issuer** cho nhiều môi trường, ranh giới phân tách audience, Client registrations, scope và chính sách phải được thiết kế kỹ hơn; dùng issuer chung không tự tạo cô lập giữa môi trường.

## 5. Phân biệt secret của OAuth2 Client, Resource Server và Authorization Server

Không phải mọi thành phần OAuth 2.0 đều cần `client-id` và `client-secret`.

### 5.1. Resource Server xác minh signed JWT

Orders API nhận JWT được ký bởi Identity Server. Nó thường dùng **khóa công khai** từ JWKS để xác minh chữ ký. Trường hợp này Resource Server **không cần client secret chỉ để xác minh token**.

~~~text
Identity Server:
  private signing key  -> ký JWT (giữ bí mật)
  public key/JWKS      -> công bố cho Resource Server

Orders API:
  issuer-uri           -> issuer đáng tin
  jwk-set-uri          -> nguồn khóa công khai
  expected-audience    -> định danh API
~~~

Đừng sao chép **private signing key** của Authorization Server vào API chỉ để “xác thực JWT”. Với thuật toán ký bất đối xứng như RS256/ES256, Resource Server chỉ cần khóa công khai và thông tin ràng buộc issuer/thuật toán theo chính sách.

### 5.2. Resource Server dùng opaque token introspection

Nếu Authorization Server phát hành **opaque access token**, Orders API có thể phải gọi introspection endpoint và xác thực bản thân khi gọi endpoint đó.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Với Spring Security, security chain cho opaque token sử dụng:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

**Đây là một lựa chọn cấu hình khác với decoder JWT ở mục 4**; không cấu hình song song hai cơ chế một cách vô tình và giả định Spring sẽ tự chọn đúng kiểu token theo nhu cầu nghiệp vụ.

Ở đây, `OAUTH_INTROSPECTION_CLIENT_SECRET` là secret dành cho Orders API khi nó xác thực với Authorization Server để **kiểm tra token**, không phải khóa ký JWT. Môi trường dev/staging/prod phải dùng credential và introspection URI tương ứng, được cấp quyền tối thiểu.

Kết quả introspection cần được Resource Server đánh giá theo hợp đồng: `active`, audience hoặc resource, scope, thông tin Client/subject và các thuộc tính liên quan. Nếu không có audience trong response, cần có một cơ chế hợp đồng tương đương để xác nhận token dành cho API này; không mặc định rằng `active = true` là đủ cho mọi API.

### 5.3. Ứng dụng vừa là Resource Server vừa là OAuth2 Client

Một backend có thể vừa nhận Bearer token vào Orders API, vừa gọi Reporting API ở chiều đi ra. Ở chiều đi ra, backend là **OAuth2 Client** và có thể cần client secret riêng để xin access token:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting:
            provider: company-identity
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: reports.read
        provider:
          company-identity:
            token-uri: ${REPORTING_TOKEN_URI}
~~~

Đây là cấu hình **OAuth2 Client cho lời gọi đi ra**, không thay thế cấu hình Resource Server bảo vệ request đi vào. Access token mà backend nhận từ caller cũng **không tự động** được phép chuyển tiếp tới Reporting API vì audience của hai API có thể khác nhau.

Nếu một ứng dụng web dùng `oauth2Login()` để đăng nhập bằng OIDC, Client registration và Client credentials phục vụ luồng login lại là phần cấu hình riêng. **ID token** dành cho OIDC Client, còn Orders API cần **access token** có audience và quyền phù hợp.

### 5.4. Phân loại bí mật để tránh đặt sai vị trí

| Thông tin | Bí mật? | Cách quản lý thường dùng |
| --- | --- | --- |
| `issuer-uri`, `jwk-set-uri`, `audience` | Không | File cấu hình public hoặc hệ thống phân phối cấu hình |
| `client-id` | Thông thường không | Cấu hình theo môi trường |
| `client-secret` | **Có** | Secret manager, Kubernetes Secret, dịch vụ cung cấp secrets của CI/CD |
| Private signing/decryption key | **Có, rất nhạy cảm** | HSM/KMS hoặc kho khóa chuyên dụng theo vai trò |
| Bearer access token, refresh token | **Có tính chất credential** | Bộ nhớ/kho token an toàn, tránh log, URL, lịch sử lệnh và file commit |
| Public JWK/JWKS | Không | Công bố qua endpoint tin cậy, dùng HTTPS, chính sách khóa/thuật toán phù hợp |
| Mật khẩu tài khoản dịch vụ | **Có** | Kho secrets riêng của từng môi trường |

Đặt tiền tố biến thể hiện **vai trò** giúp tránh nhầm: `OAUTH_INTROSPECTION_CLIENT_SECRET` khác `REPORTING_CLIENT_SECRET`; đừng tạo một biến chung `OAUTH_SECRET` cho nhiều thành phần không liên quan.

## 6. Cấp cấu hình và bí mật qua hạ tầng triển khai

Việc tách môi trường không chỉ nằm trong `application.yml`. Hệ thống triển khai phải phân phối đúng cấu hình vào đúng ứng dụng, kiểm soát quyền xem/sửa và hỗ trợ thay đổi secrets an toàn.

### 6.1. Ví dụ Kubernetes: ConfigMap cho giá trị public

Một ConfigMap dành riêng cho production:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-api-oauth-config
  namespace: shop-prod
data:
  OAUTH_ISSUER_URI: "https://login.example.com/realms/shop"
  OAUTH_JWKS_URI: "https://login.example.com/realms/shop/protocol/openid-connect/certs"
  OAUTH_API_AUDIENCE: "orders-api"
  ORDERS_PUBLIC_BASE_URL: "https://orders.example.com"
~~~

Trong Deployment, các giá trị có thể được nạp vào container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: example-registry.invalid/shop/orders-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          envFrom:
            - configMapRef:
                name: orders-api-oauth-config
~~~

Ví dụ Deployment chỉ minh họa cách **truyền configuration**; nó chưa bao gồm port, health checks, policy mạng, service account hay các phần vận hành khác. Những thông số ấy vẫn cần thiết trong một triển khai thực tế.

Kubernetes **Secret** dùng cho credential nhạy cảm nếu Resource Server cần introspection:

~~~yaml
# Một phần cấu hình container khi chọn opaque introspection:
env:
  - name: OAUTH_INTROSPECTION_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: orders-api-introspection-credentials
        key: client-secret
~~~

Đoạn trên là **trích đoạn tham chiếu một Secret đã được cấp phát**, không tạo Secret chứa giá trị bí mật. Secret phải được quản trị theo môi trường, hạn chế RBAC, kiểm soát phân phối và có quy trình quay vòng. Kubernetes Secret theo mặc định không nên bị hiểu là đã mã hóa đầu-cuối ở mọi tầng; cần áp dụng biện pháp bảo vệ secret storage phù hợp nền tảng.

### 6.2. CI/CD phải cấp đúng bộ cấu hình

Pipeline production có thể tham chiếu:

~~~text
environment = production
config-set  = orders-api/prod
secret-set  = orders-api/prod
image       = orders-api:<immutable-version>
~~~

Chỉ là mô hình minh họa; công cụ CI/CD cụ thể có cú pháp khác nhau. Một số quy tắc:

1. **Không commit bí mật** vào `application-prod.yml`, mã nguồn, Dockerfile, script hoặc tài liệu.
2. **Mỗi môi trường có credential riêng**, quyền tối thiểu và khả năng thu hồi độc lập.
3. **Build một artifact rồi promote** qua môi trường khi phù hợp; các giá trị môi trường được nạp lúc deploy.
4. **Hạn chế ai có thể sửa cấu hình prod**, đặc biệt issuer/JWKS/audience hoặc endpoints liên quan đến xác thực.
5. **Không in secrets/access token vào log** khi debug, kiểm tra pipeline hoặc tạo báo cáo lỗi.

Nếu phải chạy local, secret nên đến từ nguồn quản lý bí mật của nhóm hoặc biến môi trường tạm thời, không phải chuỗi literal đẩy lên repository. Một môi trường dev có mock issuer/authorization server riêng vẫn phải xác minh token theo chính sách được thiết kế cho dev.

## 7. Tránh hardcode và tránh fallback không an toàn

### 7.1. Không nhúng issuer/audience vào Java

Mẫu dễ dẫn đến lỗi môi trường:

~~~java
// Không phù hợp cho code dùng chung nhiều môi trường:
private static final String ISSUER =
        "https://login.example.com/realms/shop";
private static final String AUDIENCE = "orders-api";
~~~

Nếu mã này được chạy ở dev, API có thể tin token production hoặc bắt developer dùng token production để thử nghiệm. Việc chuyển sang property được nạp từ cấu hình môi trường giúp code bảo mật chỉ thể hiện **quy tắc** (validate issuer/audience), còn giá trị cụ thể thuộc deployment.

### 7.2. Cẩn thận với default trong placeholder

Cấu hình sau có thể che giấu việc production thiếu biến:

~~~yaml
# Ví dụ cần tránh cho cấu hình bảo mật bắt buộc:
app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE:orders-api-dev}
~~~

Khi `OAUTH_API_AUDIENCE` thiếu, ứng dụng sẽ dùng audience dev. Với thông tin bảo mật bắt buộc, nên **không có giá trị fallback**, hoặc chỉ cho phép fallback rõ ràng trong một profile local chuyên dụng được kiểm soát.

### 7.3. Đừng dùng request host làm audience

Trong một số hệ thống có reverse proxy, request có host `orders.example.com`, host nội bộ `orders-api.shop-prod.svc.cluster.local` hoặc nhiều tên miền public. Không nên dùng hostname từ request để tự suy ra `aud` hợp lệ vì host header có thể thay đổi qua proxy, gateway hoặc bị giả mạo nếu không kiểm soát.

Audience là **định danh Resource Server theo hợp đồng với Authorization Server**, được cấu hình độc lập. URL đến API phục vụ routing; audience phục vụ kiểm tra token.

### 7.4. Đừng nới lỏng bảo mật theo profile

Một cách sai khi môi trường dev không truy cập được JWKS là tắt hoàn toàn kiểm tra JWT hoặc bỏ yêu cầu scope. Điều này khiến hành vi dev khác production, che giấu lỗi tích hợp và dễ bị đưa nhầm vào deploy.

Thay vào đó, sử dụng **issuer dev thật hoặc issuer giả lập có khóa ký xác định**, cấu hình JWKS đúng, phát token dev với audience/scope dev phù hợp và giữ các quy tắc xác minh giống nhau. Nếu một bài test đơn vị cần mock Authentication, hãy giới hạn việc mock trong test, không biến thành cấu hình runtime của API.

## 8. Kiểm tra cấu hình đúng khi khởi động

Một ứng dụng có thể khởi động thành công nhưng nhận token sai issuer, hoặc nhận token đúng issuer nhưng sai audience. Vì thế nên xác định **điều kiện cấu hình tối thiểu** ngay từ lúc triển khai.

### 8.1. Bắt buộc cung cấp các giá trị

Các giá trị sau thường phải tồn tại và không rỗng:

~~~text
OAUTH_ISSUER_URI
OAUTH_JWKS_URI
OAUTH_API_AUDIENCE
~~~

Nếu dùng introspection:

~~~text
OAUTH_INTROSPECTION_URI
OAUTH_INTROSPECTION_CLIENT_ID
OAUTH_INTROSPECTION_CLIENT_SECRET
~~~

Nếu ứng dụng đồng thời là OAuth2 Client thì bổ sung credential/endpoint tương ứng **cho Client đó**, ví dụ `REPORTING_CLIENT_ID`, `REPORTING_CLIENT_SECRET`, `REPORTING_TOKEN_URI`.

Việc dùng placeholder không có default giúp phát hiện nhiều trường hợp thiếu cấu hình khi Spring bind hoặc sử dụng property. Với cấu hình an ninh quan trọng, có thể định nghĩa `@ConfigurationProperties` kèm validation để **fail fast** rõ ràng khi giá trị trống hoặc không hợp lệ, thay vì chờ request đầu tiên.

### 8.2. Kiểm tra tính nhất quán giữa issuer và JWKS

`OAUTH_ISSUER_URI` và `OAUTH_JWKS_URI` cần thuộc cùng bộ thông tin đáng tin của môi trường. Đối chiếu với metadata của Authorization Server:

~~~text
Issuer metadata:
  issuer = https://login.example.com/realms/shop
  jwks_uri = https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Đường dẫn discovery phụ thuộc nhà phát hành và giao thức được hỗ trợ. Đừng tự tạo endpoint bằng cách nối chuỗi cứng nếu nhà phát hành thực tế công bố URI khác. Sử dụng HTTPS và chính sách tin cậy chứng chỉ TLS phù hợp.

### 8.3. Cần biết audience thực sự bên cấp token phát hành

Ví dụ:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-481"
}
~~~

Đây là **payload minh họa**. Khi tích hợp thật, có thể quan sát claim từ token test trong môi trường kiểm soát để xác nhận AS đã cấp đúng audience. Việc decode payload chỉ giúp xem dữ liệu, **không phải xác minh token**; API phải dùng decoder/validator chính thức. Không tải access token thật lên website giải mã token công khai hoặc ghi token vào hệ thống log.

## 9. Chẩn đoán 401 và 403 khi sai môi trường

Các lỗi phổ biến có biểu hiện gần giống nhau nhưng nguyên nhân khác nhau:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| API trả **401**, dev token gọi prod không được | Issuer hoặc audience khác | Kiểm tra `iss`/`aud` được AS phát và giá trị của prod |
| API trả **401** ngay sau đổi endpoint Identity Server | API đang dùng JWKS/issuer cũ hoặc sai | Kiểm tra metadata, `jwks_uri`, thay đổi realm, key rotation, log decoder |
| API trả **401** dù token “giải mã được” | Chữ ký, thời hạn, issuer, audience hoặc loại token không hợp lệ | Xác minh bằng thư viện JWT; decode thuần không đủ |
| API trả **401** ở một môi trường nhưng chạy ở môi trường khác | Sai ConfigMap/profile/env var hoặc clock skew | So sánh cấu hình hiệu lực đã loại bỏ secrets, kiểm tra đồng hồ |
| API trả **403** nhưng token hợp lệ | Thiếu `SCOPE_orders.read` hoặc quyền đối tượng | Đối chiếu scope thực tế, converter, tenant/owner policy |
| API lỗi khi đọc JWKS | Network/DNS/TLS hoặc JWKS URI không đúng | Kiểm tra connectivity, metadata, chứng chỉ, khóa/kid |
| Introspection trả không active/lỗi xác thực | Sai URI, client credentials, token hết hạn/thu hồi | Kiểm tra môi trường của introspection endpoint và quyền credential |
| OAuth2 Client không lấy được token | Sai token endpoint, Client registration, grant hoặc secret | Kiểm tra **cấu hình Client**; khác với lỗi xác minh JWT của API |

Không khắc phục lỗi sai audience bằng cách bỏ validator audience. Không khắc phục sai khóa bằng cách chấp nhận mọi chữ ký. Nếu thiếu quyền, cần sửa **scope/role/policy được cấp** theo quy trình, không tự gắn `ROLE_ADMIN` từ header request.

### 9.1. Mã lỗi HTTP không nói hết nguyên nhân

Với Bearer authentication, API thường trả:

- **401 Unauthorized:** thiếu token hoặc token không xác thực được, bao gồm sai issuer, audience, chữ ký hoặc hết hạn.
- **403 Forbidden:** token hợp lệ nhưng không đủ scope/permission hoặc không được quyền truy cập bản ghi.
- **404 Not Found:** có thể được dùng theo chính sách để tránh tiết lộ một đối tượng không được phép truy cập.

Client nên xử lý 401 và 403 theo nghĩa bảo mật của API. Không tự gửi lại token sai môi trường vô hạn; cần xác định đúng Client registration, token audience và quyền thực tế.

## 10. Trường hợp OIDC: cấu hình nhà cung cấp đăng nhập khác cấu hình API

Trong OIDC, **Client đăng nhập** dùng issuer để khám phá endpoints, xác minh ID token và thiết lập session cho người dùng. **Resource Server** dùng issuer và audience để xác minh **access token** khi bảo vệ API.

Ví dụ ứng dụng Shop Web (OAuth2/OIDC Client) có thể dùng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop-login:
            provider: shop-id
            client-id: ${SHOP_WEB_CLIENT_ID}
            client-secret: ${SHOP_WEB_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          shop-id:
            issuer-uri: ${SHOP_IDP_ISSUER_URI}
~~~

Ví dụ giả định Shop Web là **confidential web client** với `client-secret`; ứng dụng public client có mô hình khác, thường sử dụng PKCE và không nhúng secret dài hạn vào mã client. `SHOP_IDP_ISSUER_URI` có thể trùng issuer Resource Server tin cậy nếu cùng Identity Server, nhưng **Client ID/secret, redirect URI, requested scopes và audience API là các thông tin khác nhau**.

Đặc biệt:

| ID token | Access token |
| --- | --- |
| Dành cho OIDC Client và thường có `aud` là `client_id` | Dành cho Resource Server, `aud` phải phù hợp API |
| Hỗ trợ xác nhận kết quả đăng nhập theo OIDC | Dùng làm Bearer credential gọi API |
| Client cần xác minh theo quy tắc OIDC | API cần xác minh issuer, chữ ký, thời hạn, audience và quyền |

Không cấu hình Orders API chỉ kiểm tra một issuer rồi chấp nhận cả ID token chỉ vì ID token cũng là JWT. Resource Server cần xác định loại token và audience đúng mục đích theo hợp đồng tích hợp.

## 11. Khi môi trường chia sẻ một Authorization Server

Không phải lúc nào dev, staging và production cũng có ba issuer vật lý độc lập. Một tổ chức có thể dùng:

- Một Identity Provider duy nhất nhưng **realm/tenant** riêng cho từng môi trường.
- Một issuer chung với **Client registration** và **audience** khác nhau.
- Một issuer chung với audience giống nhau cho các API khác môi trường (trường hợp này cần đánh giá kỹ hơn).

Thứ tự ưu tiên thường là **cô lập hợp đồng tin cậy và quyền giữa môi trường**. Nếu các API dùng chung issuer, ít nhất cần giới hạn token được chấp nhận bằng audience và các điều kiện được chứng thực khác. Nếu issuer và audience đều chung, hai môi trường có thể khó phân biệt token với nhau; phải bổ sung ranh giới thích hợp (ví dụ resource/client binding hoặc chính sách phát hành và kiểm tra độc lập), thay vì mặc định “cùng issuer là an toàn”.

Hãy nhìn vào khả năng lạm dụng token: nếu một token dev bị rò rỉ, nó có thể được trình lên API production và qua được các điều kiện kiểm tra hay không? Câu trả lời phải được quyết định bởi **thiết kế issuer, audience, trust và policy**, không chỉ bởi tên profile.

## 12. Gợi ý quy trình triển khai theo môi trường

### Bước 1 — Xác định hợp đồng token của từng môi trường

Mỗi môi trường cần ghi nhận:

~~~yaml
# Tài liệu tích hợp minh họa, không phải schema do Spring tự đọc.
environment: prod
resource_server: orders-api
issuer: https://login.example.com/realms/shop
jwks_uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
expected_audience: orders-api
required_scopes:
  GET /api/orders/{id}: orders.read
  POST /api/orders: orders.write
token_usage: oauth2_access_token
~~~

Đây là **tài liệu hợp đồng**, không phải thay thế tự động cho `application.yml`. Nó giúp Client team, Identity team và API team cùng thống nhất giá trị để đưa vào cấu hình thật.

### Bước 2 — Chuẩn bị cấu hình triển khai

Gắn bộ thông tin môi trường tương ứng vào release hoặc workload: issuer/JWKS/audience trong ConfigMap hay configuration service; credential introspection/OAuth2 Client trong secret manager riêng.

### Bước 3 — Đảm bảo API xác minh đúng những gì đã thỏa thuận

Resource Server phải kiểm tra chữ ký bằng khóa tin cậy, `iss`, `aud`, `exp`/`nbf`, loại token và scope/authority. Sau đó lớp nghiệp vụ phải kiểm tra owner, tenant, permission hoặc các điều kiện khác.

### Bước 4 — Thử hành vi đúng/sai môi trường

| Tình huống | Kỳ vọng |
| --- | --- |
| Prod API + prod access token hợp lệ, đúng audience và scope | Được xử lý tiếp tới policy dữ liệu |
| Prod API + dev access token | **401** nếu không đáp ứng hợp đồng issuer/audience/trust của prod |
| Prod API + token cùng issuer nhưng `aud = billing-api` | **401** |
| Prod API + token đúng audience nhưng đã hết hạn | **401** |
| Prod API + token đúng issuer/audience nhưng thiếu scope endpoint | **403** |
| Prod API + token đủ scope nhưng không có quyền trên dữ liệu | **403** hoặc **404**, theo chính sách |
| API khởi động thiếu issuer/audience bắt buộc | Triển khai phải phát hiện lỗi cấu hình, không âm thầm dùng default không an toàn |

Cần quan sát cả kết quả từ Authentication và từ tầng nghiệp vụ. Không ghi Bearer token/secret vào log để chẩn đoán; có thể ghi request ID, môi trường, mã lỗi và định danh cấu hình công khai theo chính sách quan sát.

### Bước 5 — Quản lý thay đổi và quay vòng secrets

Khi đổi issuer, JWKS endpoint, audience hoặc client secret, hãy xác định ai sở hữu giá trị, môi trường nào chịu tác động, thứ tự triển khai Client/AS/API và thời gian chuyển tiếp token. Việc quay vòng khóa ký cần tính đến JWKS caching và token còn hiệu lực. Quay vòng client secret cần cập nhật bên sử dụng đúng secret mà không làm rò rỉ secret cũ/mới qua pipeline.

## 13. Các nhầm lẫn cần tránh

**“Base URL API và audience luôn giống nhau.”** Sai. Audience là định danh do hợp đồng với issuer quy định. Nó có thể là URI, nhưng không bắt buộc trùng hostname mà Client gọi.

**“Chỉ cần đúng issuer, API nào cũng dùng được token.”** Sai. Token có thể được cấp cho API khác. Resource Server cần kiểm tra audience và quyền dành cho chính mình.

**“Muốn kiểm tra JWT thì phải có client secret của nhà phát hành.”** Với JWT ký bất đối xứng, API thường xác minh bằng khóa công khai từ JWKS; secret của OAuth2 Client là một khái niệm khác.

**“JWKS là secret, không được công bố.”** JWKS để xác minh chữ ký thường chứa khóa **công khai**. Private signing key phải giữ bí mật ở bên ký; không được nhầm hai loại khóa.

**“Issuer URI chỉ là endpoint HTTP; đổi domain không ảnh hưởng gì.”** `iss` là một phần của hợp đồng xác minh. Khi issuer thay đổi, Client/API và chính sách cấp token có thể phải cập nhật đồng bộ.

**“Đặt profile = prod đã bảo vệ được production.”** Profile chỉ chọn cấu hình. Sự an toàn đến từ kiểm soát triển khai, issuer/audience đúng, credentials riêng, token validation và authorization.

**“Resource Server nào cũng cần client-id/client-secret.”** Không. Resource Server nhận signed JWT thường không cần client secret để xác minh; Resource Server introspection hoặc ứng dụng đồng thời đóng vai OAuth2 Client có thể cần credential.

**“Cùng mã nguồn dev và prod thì nên dùng cùng một secret để dễ cấu hình.”** Mỗi môi trường nên có credential độc lập để giảm phạm vi ảnh hưởng khi bị lộ hoặc thu hồi.

**“Token giải mã được và có scope là token hợp lệ.”** Decode Base64URL chỉ đọc dữ liệu, chưa xác minh chữ ký, issuer, audience, thời hạn hoặc loại token.

---

**Ghi nhớ:** Để cấu hình Spring Security OAuth 2.0/OIDC Resource Server an toàn qua nhiều môi trường, hãy giữ **logic xác minh trong cùng code**, đưa **issuer URI, JWKS URI và audience** vào cấu hình theo môi trường, đồng thời cấp **client secrets/credentials** qua cơ chế quản lý bí mật phù hợp với vai trò thực sự cần sử dụng chúng. Mỗi Resource Server chỉ tin token được cấp bởi nguồn phát hành đã thỏa thuận, dành cho đúng API và đáp ứng chính sách truy cập; việc chuyển dev, staging hay production chỉ thay giá trị cấu hình, không làm thay đổi nguyên tắc bảo mật.
