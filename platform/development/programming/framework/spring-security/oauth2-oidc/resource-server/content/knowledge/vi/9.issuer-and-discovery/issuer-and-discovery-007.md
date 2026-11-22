# Authorization Server tạm ngừng và ảnh hưởng đến khởi động, xác minh

Trong hệ thống **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, việc **Authorization Server (AS)** tạm ngừng không nhất thiết khiến mọi API đang bảo vệ bằng access token lập tức dừng hoạt động. Tác động thực tế phụ thuộc vào **thời điểm mất kết nối**, **cách Resource Server tìm metadata và khóa xác minh**, **định dạng token** và **dữ liệu khóa đã có sẵn**.

Ví dụ, Orders API nhận JWT access token do Identity Server phát hành. Khi Identity Server gặp sự cố, có thể xảy ra ba tình huống hoàn toàn khác nhau:

- **Orders API vừa khởi động:** ứng dụng có thể cần gọi issuer để khám phá metadata/JWKS trước khi hoàn tất khởi tạo bộ xác minh.
- **Orders API đã chạy và đã có khóa xác minh:** một JWT chưa hết hạn có thể tiếp tục được xác minh cục bộ, ngay cả khi Identity Server tạm ngừng.
- **Orders API cần tải khóa mới hoặc introspection:** nếu chưa có khóa phù hợp, hoặc token là opaque token phải được kiểm tra từ xa, việc xác thực request có thể thất bại.

Vì thế, câu hỏi “Authorization Server bị down thì Resource Server có hoạt động không?” không có một đáp án **có/không** cho mọi cấu hình. Cần phân biệt **discovery**, **khởi tạo decoder**, **lấy và làm mới JWK**, **xác minh access token** và **cấp access token mới**.

> **Nguyên tắc an toàn:** Có thể thiết kế Resource Server giảm phụ thuộc vào AS ở thời điểm khởi động, nhưng **không được cho qua request chỉ vì AS hoặc JWKS đang không truy cập được**. API chỉ chấp nhận token khi đã xác minh đầy đủ chữ ký, issuer, audience, thời hạn và quyền.

## 1. Các thành phần tham gia

Giả sử hệ thống có:

- **Shop Web:** OAuth2/OIDC Client xin access token cho người dùng.
- **Identity Server:** Authorization Server/issuer `https://identity.example.test/realms/shop`.
- **Orders API:** Spring Security Resource Server chấp nhận access token có audience `orders-api`.
- **JWKS endpoint:** nơi issuer công bố khóa công khai dùng xác minh token JWT có chữ ký.

Một luồng bình thường:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as OAuth2 Client
    participant AS as Authorization Server
    participant API as Orders API
    participant JWKS as JWKS endpoint

    User->>Client: Xem đơn hàng
    Client->>AS: Xin access token (theo grant)
    AS-->>Client: Access token đã ký
    Client->>API: GET /api/orders/42 + Bearer JWT
    opt Chưa có khóa phù hợp trong bộ nhớ/cache
        API->>JWKS: Lấy public JWK
        JWKS-->>API: JWKS
    end
    API->>API: Verify chữ ký, iss, aud, exp và scope
    API->>API: Kiểm tra quyền trên đơn hàng
    API-->>Client: Kết quả hoặc từ chối
~~~

Trong một triển khai đơn giản, metadata và JWKS có thể cùng do Identity Server phục vụ; sơ đồ tách tên điểm cuối để thấy rõ **hai lần truy cập mạng có vai trò khác nhau**. AS có thể mất khả dụng toàn bộ hoặc chỉ một endpoint của nó gặp lỗi.

### Hai việc rất dễ bị nhầm

| Việc | Mục tiêu | Thời điểm thường diễn ra | Có cần AS trực tuyến? |
| --- | --- | --- | --- |
| **Discovery** | Từ issuer, tìm metadata như `jwks_uri` và các endpoint liên quan | Khi dựng decoder/khởi động, tùy phiên bản và cấu hình | **Có**, nếu đang khám phá qua mạng và chưa có cấu hình thay thế |
| **JWT signature verification** | Dùng public key đáng tin để kiểm tra chữ ký của access token | Khi nhận Bearer JWT | **Không nhất thiết**, nếu khóa phù hợp đã có; có thể cần JWKS khi thiếu/làm mới khóa |

**Issuer URI** là định danh nhà phát hành và cơ sở để thực hiện discovery. **JWKS URI** là địa chỉ lấy khóa công khai. **Audience** là định danh API nhận token. Ba giá trị này có chức năng riêng, không thể thay cho nhau.

## 2. Issuer discovery làm gì?

Khi chỉ biết issuer:

~~~text
https://identity.example.test/realms/shop
~~~

Resource Server có thể sử dụng cơ chế **Authorization Server Metadata** hoặc **OpenID Provider Configuration** được thư viện hỗ trợ để xác định metadata của issuer. Metadata có thể chứa:

~~~json
{
  "issuer": "https://identity.example.test/realms/shop",
  "jwks_uri": "https://identity.example.test/realms/shop/protocol/openid-connect/certs",
  "authorization_endpoint": "https://identity.example.test/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://identity.example.test/realms/shop/protocol/openid-connect/token"
}
~~~

Đây là **ví dụ định dạng và giá trị**, không phải metadata bắt buộc của mọi sản phẩm. Một Resource Server xác minh JWT chủ yếu cần biết **issuer và nguồn khóa xác minh**; Client OIDC có thể cần thêm authorization/token endpoints.

### 2.1. Discovery không phải xác minh chữ ký

Discovery trả lời: “Issuer tự công bố **khóa và endpoints ở đâu?**”. Nó **không tự chứng minh** access token đang gửi đến API hợp lệ. Sau discovery, Resource Server vẫn phải:

1. Tải hoặc sử dụng public key phù hợp từ nguồn được cấu hình tin cậy.
2. Xác minh JWS/JWT bằng thuật toán và khóa được phép.
3. Kiểm tra `iss` đúng issuer tin cậy, thời hạn `exp`/`nbf` và audience `aud` đúng API.
4. Chỉ từ token đã được xác minh mới tạo principal/authorities.
5. Kiểm tra scope và quyền đối với tài nguyên nghiệp vụ.

### 2.2. Discovery có thể ảnh hưởng tới khởi động

Khi ứng dụng khai báo **chỉ** `issuer-uri`, quá trình tạo decoder tự động có thể cần liên lạc với issuer để tìm JWKS endpoint. Trong kiểu khởi tạo phải khám phá metadata ngay lúc dựng decoder, nếu AS không truy cập được thì **ứng dụng không hoàn tất quá trình khởi tạo bộ xác minh**, có thể dẫn đến lỗi startup.

Hành vi cụ thể còn phụ thuộc **phiên bản Spring Security/Spring Boot**, cách dựng `JwtDecoder` và việc khởi tạo component sớm hay muộn. Với một số cách cấu hình, lookup có thể được trì hoãn đến khi xử lý request đầu tiên. Vì thế không nên khẳng định mọi phiên bản “luôn gọi AS ở startup”, cũng không nên thiết kế availability dựa trên giả định “discovery chắc chắn lazy”.

Quy tắc thực hành là: **nếu startup có thể phải discovery từ xa, outage của AS có thể trở thành outage startup của Resource Server**.

## 3. Dòng thời gian: AS ngừng ở thời điểm nào?

### 3.1. Trước khi Resource Server khởi động

Một cấu hình phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
~~~

Spring Security có thể dùng issuer location để tự tìm metadata rồi xác định `jwks_uri`. Nếu bước này diễn ra trước hoặc trong khởi động và issuer đang down, decoder không khởi tạo được và ứng dụng có thể không khởi động thành công.

Hệ quả vận hành:

- Pod/instance mới có thể không qua được startup hoặc readiness.
- Một rolling deployment có thể không thay được instance cũ nếu instance mới phụ thuộc discovery.
- Autoscaling trong lúc AS bị sự cố có thể tạo thêm các instance không sẵn sàng phục vụ.
- Một instance đã chạy từ trước **không nhất thiết** dừng theo các instance mới.

Một cách giảm phụ thuộc vào discovery khi khởi động là khai báo **cả issuer và JWKS URI** theo hợp đồng tin cậy, được trình bày ở mục 5.

### 3.2. Sau khi API đã khởi động và có khóa phù hợp

Giả sử AS đã cấp JWT có chữ ký RS256. Orders API đã tải public JWK tương ứng và hiện có khóa trong bộ nhớ/cache.

Khi AS ngừng:

1. Client đã có access token chưa hết hạn vẫn có thể gửi request.
2. API có thể xác minh chữ ký bằng public key hiện có mà **không cần hỏi AS cho từng request**.
3. API vẫn kiểm tra `iss`, `aud`, `exp`, `nbf`, scope và quyền dữ liệu theo chính sách.
4. Request hợp lệ có thể tiếp tục được xử lý, miễn là bộ xác minh có khóa phù hợp và không phát sinh yêu cầu mạng khác bắt buộc.

Đó là một lợi ích của **self-contained signed JWT**: Resource Server không phải gọi Authorization Server cho từng lần xác minh chữ ký. Tuy nhiên, việc có và dùng được khóa trong cache phụ thuộc thư viện, cấu hình, thời gian cache và hoạt động quay vòng khóa.

**Không được hiểu “JWT cho phép xác minh offline” là “mọi instance luôn xác minh offline được”.** Instance vừa tạo, cache trống hoặc token được ký bằng khóa chưa biết có thể vẫn cần JWKS endpoint.

### 3.3. Khi Resource Server chưa có khóa hoặc cần làm mới JWKS

Các trường hợp có thể cần liên lạc lại với AS/JWKS:

- Instance mới chưa từng tải JWK.
- Cache JWK hết hiệu lực và implementation cần tải lại.
- Token mang `kid` mới sau khi issuer quay vòng khóa.
- Bộ xác minh không tìm được khóa phù hợp cho `alg`/`kid` của token.
- Chính sách hoặc cấu hình yêu cầu liên hệ nguồn dữ liệu từ xa khác.

Nếu JWKS không truy cập được trong các trường hợp trên, **API không thể giả vờ rằng chữ ký đã được xác minh**. Request phụ thuộc khóa chưa có phải bị từ chối hoặc thất bại theo cơ chế xử lý lỗi đã thiết kế.

| Tình huống | Khả năng xác minh local | Ảnh hưởng khi JWKS down |
| --- | --- | --- |
| JWT ký bằng khóa còn trong cache và cache được phép sử dụng | Có thể | Request có thể tiếp tục qua bước chữ ký |
| JWT ký bằng `kid` chưa biết | Không có khóa phù hợp | Không thể xác minh, request thất bại |
| Cache hết hạn và bắt buộc refresh trước khi xác minh | Phụ thuộc thư viện/cấu hình | Có thể thất bại dù token chưa hết hạn |
| Instance vừa khởi động, chưa từng có khóa | Thường chưa | Lần xác minh đầu tiên có thể thất bại |
| Resource Server dùng public key đã phân phối cục bộ | Có thể, với token do khóa đó ký | Không cần JWKS cho khóa hiện có, nhưng phải xử lý vòng đời/rotation |

Chính sách cache không có một khoảng thời gian chung cho mọi Spring Security/Nimbus JWKS implementation. Không viết logic ứng dụng với giả định “JWK luôn được cache 24 giờ” nếu chưa kiểm tra phiên bản và cấu hình đang dùng.

### 3.4. Khi Authorization Server phục hồi

Sau khi AS/JWKS phục hồi, instance đang thiếu khóa có thể truy xuất lại JWKS theo cơ chế của thư viện và chính sách retry/cache. Các request đã thất bại trước đó **không tự động thành công trở lại**; Client có thể cần gửi lại request an toàn theo ngữ nghĩa HTTP/nghiệp vụ.

Nếu AS đã quay vòng khóa trong lúc outage, phải bảo đảm public key mới được công bố đúng, old key còn được giữ theo thời gian sống của token cũ và các cache được cập nhật theo kế hoạch.

## 4. So sánh các cách cấu hình issuer và JWKS

| Cấu hình JWT Resource Server | Discovery từ issuer khi dựng decoder | Kiểm tra issuer | Khả năng phụ thuộc mạng khi xác minh |
| --- | --- | --- | --- |
| Chỉ có **`issuer-uri`** | Có thể cần để tìm `jwks_uri` | Có, khi decoder được cấu hình đúng theo issuer | Vẫn có thể cần tải/refresh JWKS |
| Có **`issuer-uri` + `jwk-set-uri`** | Có thể tránh lookup discovery ở startup | **Vẫn kiểm tra `iss`** theo cấu hình Spring phù hợp | Có thể cần tải/refresh JWKS khi thiếu khóa |
| Chỉ có **`jwk-set-uri`** | Không cần khám phá issuer | **Không tự suy ra issuer hợp lệ** chỉ từ JWKS URI | Có thể cần tải/refresh JWKS |
| Khóa công khai phân phối **cục bộ** và decoder cấu hình rõ | Không cần discovery hoặc JWKS remote để dùng khóa cục bộ | Phải tự cấu hình validator issuer/audience | Không cần endpoint khóa cho token dùng khóa đã phân phối, nhưng rotation là trách nhiệm riêng |

Phương án **issuer + JWKS URI** thường hữu ích khi muốn ứng dụng có thể khởi động trong thời gian AS tạm ngừng, đồng thời vẫn kiểm tra claim issuer. Điều này giải quyết **phụ thuộc discovery tại startup**; nó **không đảm bảo** mọi request JWT đều chạy khi JWKS down, vì có thể vẫn cần tải khóa vào lúc xử lý token.

### Lưu ý về `jwk-set-uri` đứng một mình

Nếu cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

thì API biết nguồn khóa công khai nhưng **chưa có ràng buộc `iss` được chỉ định ở đây**. Việc chữ ký xác minh được bằng một JWK không thay thế điều kiện issuer. Nếu có nhiều nhóm token được ký qua cùng một hạ tầng, bỏ qua issuer/audience dễ dẫn đến tin nhầm token.

Do đó, khi phải bỏ `issuer-uri` khỏi auto-configuration, cần tự tạo `JwtDecoder` và thiết lập validator đủ mạnh, hoặc dùng một cơ chế cấu hình tương đương kiểm tra issuer rõ ràng.

## 5. Cấu hình Spring Boot giảm phụ thuộc discovery lúc startup

Ví dụ dùng **Spring Boot 3 / Spring Security 6**. Các endpoint, issuer và audience chỉ mang tính minh họa; phải thay bằng giá trị được Identity Server công bố cho môi trường thực tế.

### 5.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 5.2. Cung cấp issuer và JWKS URI riêng

`src/main/resources/application.yml`:

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
~~~

Ví dụ biến môi trường:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

Khi cung cấp `jwk-set-uri` trực tiếp, decoder có thể biết địa chỉ lấy khóa **mà không phải truy xuất metadata từ issuer để tìm địa chỉ này** lúc khởi tạo. Đồng thời khai báo `issuer-uri` giúp giữ kiểm tra issuer trong cách tự cấu hình phù hợp của Spring Boot/Spring Security.

**Cần phân biệt:** Không discovery ở startup **không đồng nghĩa** JWKS đã được tải về. Một decoder có thể tải JWKS khi xác minh request đầu tiên hoặc khi cần khóa mới. Nếu lúc đó JWKS down và chưa có khóa, API không thể xác minh chữ ký.

### 5.3. SecurityFilterChain dùng chung

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
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
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

Đây là cấu hình ví dụ cho REST API **chỉ xác thực bằng Bearer token**, vì vậy cấu hình này tắt CSRF và dùng session stateless trong filter chain API. Ứng dụng có thêm đăng nhập bằng cookie hoặc các endpoint trình duyệt phải cấu hình CSRF, session và filter chain phù hợp.

Spring Security có thể ánh xạ claim `scope` hoặc `scp` theo định dạng được hỗ trợ thành authorities `SCOPE_...`. Điều kiện `orders.read` bảo vệ loại thao tác; nó không thay thế kiểm tra owner/tenant của đơn hàng cụ thể.

### 5.4. Khi cần kiểm tra audience rõ ràng

Issuer đúng vẫn có thể cấp JWT cho API khác. Orders API phải từ chối token với `aud` không chứa `orders-api`. Một ví dụ decoder có validator riêng:

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
class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        // Có JWKS URI từ cấu hình, không cần discovery để tìm địa chỉ này.
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        // Bao gồm các quy tắc JWT mặc định và kiểm tra issuer.
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Token đã ký hợp lệ nhưng dành cho API khác vẫn phải bị từ chối.
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token audience is not accepted",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));
        return decoder;
    }
}
~~~

Ví dụ này làm rõ hai trách nhiệm khác nhau: `NimbusJwtDecoder` dùng JWK tin cậy để **xác minh chữ ký**, còn validators xác định **token có được API chấp nhận** theo issuer, thời hạn, audience. Trước khi áp dụng vào production, cần cấu hình thuật toán được phép, loại token/profile và các claim bắt buộc theo hợp đồng với nhà phát hành.

Không được “xử lý outage” bằng cách bỏ `JwtDecoder`, bỏ validate `iss`/`aud` hay tạo một Authentication giả có toàn quyền. Khi decoder không xác minh được token, yêu cầu phải thất bại an toàn.

### 5.5. Nếu muốn loại bỏ cả phụ thuộc tải JWKS lúc request

Trong một số kiến trúc, tổ chức có thể **phân phối public key đáng tin cậy bằng cấu hình hoặc file** cùng ứng dụng, thay vì tải JWKS động. Khi đó API có thể xác minh token ký bằng khóa đã phân phối mà không cần liên lạc endpoint JWKS.

Điều kiện cần được quản lý cẩn thận:

- Public key phải được cấp phát từ nguồn quản trị đáng tin, không lấy từ header của token hoặc request.
- Bộ xác minh vẫn phải giới hạn thuật toán và kiểm tra issuer, audience, hạn dùng, loại token.
- **Quay vòng khóa** cần quy trình cập nhật và phát hành public key trước khi AS bắt đầu ký bằng khóa mới.
- Nếu chỉ phân phối **một** public key, token ký bằng khóa mới có thể bị từ chối cho đến khi Resource Server được cập nhật.
- Public key tự nó không cho biết token thuộc issuer nào; ứng dụng vẫn phải thực thi chính sách issuer.

Cách phân phối khóa cục bộ có thể phù hợp những môi trường có yêu cầu độc lập cao, nhưng phải cân nhắc chi phí vận hành và nguy cơ khóa cũ còn được tin quá lâu. Không chọn vì muốn vô hiệu hóa cơ chế rotation hoặc revocation.

## 6. AS ngừng không giống JWKS endpoint ngừng

Trong một nhà cung cấp định danh, nhiều endpoint có thể ở cùng hạ tầng nhưng phục vụ mục đích khác nhau:

| Endpoint/chức năng | Khi ngừng, ai bị ảnh hưởng? | Resource Server JWT đang chạy có thể tiếp tục? |
| --- | --- | --- |
| **Authorization endpoint** | Người dùng/Client khó bắt đầu luồng authorization code hoặc đăng nhập mới | Có thể, với token JWT đang có và khóa phù hợp |
| **Token endpoint** | Client không đổi code, refresh token hoặc xin token theo `client_credentials` được | Có thể, với access token chưa hết hạn đã cấp |
| **Discovery metadata** | Instance/decoder cần khám phá metadata có thể lỗi | Có thể, nếu discovery đã hoàn tất hoặc endpoint JWK được cấu hình rõ |
| **JWKS endpoint** | API cần tải/làm mới khóa công khai có thể lỗi | Có thể, nếu đã có khóa hợp lệ được phép sử dụng |
| **Introspection endpoint** | Resource Server dùng opaque token khó xác thực request | Thường **không**, nếu mỗi lần cần kết quả introspection mới và không có cơ chế dự phòng được thiết kế |
| **Revocation endpoint** | Client/AS khó thực hiện thu hồi token theo endpoint đó | Việc JWT đã phát hành vẫn cần được xử lý theo chính sách vòng đời |

Sự cố AS toàn bộ có thể ảnh hưởng đồng thời tất cả các chức năng. Một sự cố chỉ ở authorization UI không nhất thiết làm JWKS biến mất. Khi chẩn đoán outage, phải xác định **đúng endpoint nào thất bại**.

## 7. Resource Server nhận JWT khác Resource Server dùng opaque token

### 7.1. Signed JWT: có khả năng xác minh cục bộ

JWT access token ký bất đối xứng cho phép Resource Server:

- Xác minh JWS bằng public key tin cậy.
- Kiểm tra `iss`, `aud`, `exp`, `nbf` trên token.
- Ánh xạ scope/claims hợp lệ thành authorities.
- Kiểm tra permission và dữ liệu nghiệp vụ.

Sau khi đã có public key và các thông tin cấu hình cần thiết, những bước này **không đòi hỏi gọi AS cho từng request**. Tuy nhiên, API vẫn có thể phụ thuộc vào các hệ thống khác để tra cứu quyền động, policy hoặc dữ liệu; outage của những hệ thống ấy là vấn đề riêng.

### 7.2. Opaque token: thường cần introspection

Với opaque access token, API thường không tự đọc/xác minh nội dung bằng JWS; nó phải gọi endpoint introspection:

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

Security chain tương ứng:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

Đây là **cấu hình lựa chọn thay thế** cho xử lý JWT trong ví dụ trước; không sử dụng đồng thời hai kiểu rồi mong framework tự đoán token mà không có thiết kế rõ ràng.

~~~mermaid
sequenceDiagram
    participant Client as OAuth2 Client
    participant API as Opaque Resource Server
    participant AS as Introspection endpoint

    Client->>API: Bearer opaque token
    API->>AS: Introspect token với credential phù hợp
    alt AS trả kết quả tin cậy
        AS-->>API: active và metadata
        API->>API: Kiểm tra active, audience, scope, policy
    else AS không truy cập được
        API--xAS: Timeout / lỗi kết nối
        API-->>Client: Không thể xác thực / lỗi phù hợp
    end
~~~

Nếu introspection endpoint down và API cần phản hồi mới để xác minh token, nó phải **fail closed**: không giả định mọi opaque token đều còn active. Một số hệ thống thiết kế cache kết quả introspection, nhưng cache đó có đánh đổi về độ mới của trạng thái thu hồi, thời hạn, thay đổi quyền và yêu cầu bảo mật. **Không tự kéo dài `active = true` vô thời hạn** khi endpoint không phản hồi.

### 7.3. JWT hợp lệ không đương nhiên còn “được phép” theo trạng thái mới nhất

Xác minh JWT offline mang lại khả năng chịu lỗi, nhưng cũng tạo đánh đổi: token còn hạn có thể được chấp nhận dù tài khoản vừa bị vô hiệu hóa, quyền vừa đổi hoặc phiên vừa đăng xuất, nếu API chỉ kiểm tra JWT tại chỗ.

Các biện pháp theo rủi ro có thể gồm:

- Access token có thời gian sống ngắn.
- Kiểm tra trạng thái người dùng/tenant/permission ở nguồn dữ liệu còn hoạt động.
- Introspection hoặc một cơ chế thu hồi/báo trạng thái theo thiết kế.
- Bảo vệ nghiêm ngặt các thao tác nhạy cảm bằng policy và dữ liệu nghiệp vụ cập nhật.

Không có một lựa chọn nào loại bỏ mọi đánh đổi: **xác minh cục bộ** giảm phụ thuộc mạng nhưng có thể chậm nhận biết thay đổi; **xác minh trạng thái online** có thể cập nhật nhanh hơn nhưng phụ thuộc độ khả dụng của dịch vụ kiểm tra.

## 8. Ảnh hưởng đến OAuth2 Client và OIDC login

Khi AS down, không chỉ Resource Server bị tác động. **Client** thường cần AS để xin token mới:

| Luồng Client | Bước phụ thuộc AS | Khi AS tạm ngừng |
| --- | --- | --- |
| **Authorization Code + OIDC login** | Chuyển hướng xác thực, consent, đổi code lấy token | Đăng nhập mới/trao đổi code thường thất bại |
| **Refresh token** | Gửi refresh token đến token endpoint | Không nhận được access token mới |
| **Client Credentials** | Service xin access token từ token endpoint | Không xin được token mới |
| **Client đang giữ access token chưa hết hạn** | Gửi token tới API | Vẫn có thể gọi API JWT nếu API xác minh được và quyền hợp lệ |

Trong OIDC, **ID token** được dùng tại OIDC Client để xử lý kết quả đăng nhập; nó **không phải** access token dùng gọi Resource Server. AS ngừng khiến quá trình login/refresh mới khó thực hiện, nhưng không có nghĩa Resource Server nên chấp nhận ID token thay cho access token.

Nếu một hệ thống có session người dùng phía ứng dụng web, session đó có thể có chính sách thời hạn riêng. **Tồn tại session web không đảm bảo** ứng dụng còn có access token hợp lệ để gọi API, nhất là khi việc refresh phải liên lạc AS đang down.

## 9. Thiết kế khả dụng mà không đánh đổi tính an toàn

### 9.1. Mục tiêu rõ ràng: khởi động được, xác minh được hay cấp token được?

Một kế hoạch availability nên tách ba mục tiêu:

1. **Startup independence:** Instance mới có thể dựng bộ bảo mật dù AS metadata endpoint tạm ngừng.
2. **Verification availability:** Instance đang chạy có khóa phù hợp để xác minh JWT theo hợp đồng.
3. **Token issuance availability:** Client có thể nhận/refresh access token mới.

Khai báo `issuer-uri + jwk-set-uri` chủ yếu giúp mục tiêu **1**. Cơ chế phân phối/caching/rotation khóa giúp mục tiêu **2**. Mục tiêu **3** phụ thuộc khả năng phục vụ của AS/token endpoint, không thể được giải quyết chỉ bằng cách sửa cấu hình Resource Server.

### 9.2. Không fail open khi mất AS

Các cách xử lý sai khi JWKS/introspection không truy cập được:

~~~text
Nếu không tải được JWK -> bỏ kiểm tra signature.
Nếu AS down -> tin mọi token có sub và scope.
Nếu introspection timeout -> mặc định active = true.
Nếu issuer không phản hồi -> chấp nhận token từ issuer bất kỳ.
~~~

Những hành vi này biến một sự cố khả dụng thành **lỗ hổng xác thực**. Cách an toàn là chỉ dùng khóa tin cậy đã có và còn phù hợp theo chính sách, hoặc từ chối request không xác minh được. Nếu cần trả status biểu thị phụ thuộc không sẵn sàng, phải thiết kế error handling phù hợp mà vẫn **không thực hiện hành động được bảo vệ**.

### 9.3. Timeout, retry và circuit breaker

Với các cuộc gọi tới metadata, JWKS hoặc introspection:

- Chọn **connection timeout** và **read timeout** theo yêu cầu độ trễ và đặc tính môi trường.
- Chỉ retry những lỗi có khả năng tạm thời và trong giới hạn rõ ràng; tránh tạo retry storm khi AS gặp sự cố.
- Có thể dùng backoff/circuit breaker ở lớp phù hợp để bảo vệ thread và tài nguyên khi dependency đang down.
- Quan sát tỷ lệ refresh JWKS thất bại, thời gian introspection và lỗi tải metadata.
- Bảo đảm lỗi mạng không bị chuyển thành “token hợp lệ”.

Đừng tự tạo cơ chế cache và retry vượt qua các điều kiện của thư viện JOSE mà không hiểu cách thư viện quản lý `kid`, Cache-Control, TTL và thay đổi khóa. Hành vi cụ thể phải được điều chỉnh theo thư viện/phiên bản đang dùng.

### 9.4. Readiness và liveness

Một API có thể **sống** nhưng không **sẵn sàng** xử lý một nhóm request do JWKS chưa tải được:

- **Liveness** nên phản ánh tiến trình còn hoạt động, tránh liveness phụ thuộc một AS bên ngoài khiến toàn bộ pod restart hàng loạt khi AS down.
- **Readiness** phản ánh khả năng phục vụ theo yêu cầu hệ thống, nhưng cần cân nhắc liệu việc gắn chặt readiness với AS có gây **cascading outage** và ngăn rollout/autoscaling hay không.
- Có thể dùng kiểm tra cấu hình issuer/audience bắt buộc và quan sát trạng thái khóa xác minh riêng để đánh giá khả dụng thực tế.

Không có một cấu hình readiness duy nhất hợp lý cho mọi môi trường: API chỉ xác minh JWT với khóa đã có khác hẳn API bắt buộc introspection mọi request. Các chỉ số cần phân biệt **AS down**, **API không có khóa** và **token thực sự không hợp lệ**.

## 10. Giám sát, chẩn đoán và thông báo lỗi

Những dấu hiệu sự cố có thể xuất hiện ở các lớp khác nhau:

| Triệu chứng | Khả năng nguyên nhân | Điểm cần kiểm tra |
| --- | --- | --- |
| Instance mới không startup khi AS ngừng | Discovery lúc khởi tạo decoder phụ thuộc metadata remote | Cấu hình `issuer-uri`, stack trace, thời điểm lookup |
| Instance cũ vẫn xử lý JWT, instance mới lỗi | Instance cũ có JWK cache, instance mới chưa có | JWKS URI, khóa/kid, cache và rotation |
| JWT cũ chạy, JWT mới ký bằng `kid` khác bị từ chối | Chưa lấy được khóa mới | JWKS response, refresh, issuer, thuật toán |
| Mọi request opaque token bị lỗi trong lúc AS down | Introspection endpoint không phản hồi | Connection/timeout, credential, cache policy |
| Client không đăng nhập hoặc không refresh được | Authorization/token endpoint ngừng | Lỗi redirect/token exchange |
| JWT có chữ ký đúng nhưng API trả 401 | Sai issuer/audience, hết hạn hoặc token type | Token contract và validators |
| JWT hợp lệ nhưng API trả 403 | Thiếu scope/permission hoặc policy dữ liệu không cho phép | Authority mapping, ownership/tenant |
| API khởi động được nhưng request đầu tiên 401/lỗi kết nối | JWKS được tải theo nhu cầu lúc xác minh | Logs của JWT decoder và JWKS retrieval |

**Không suy luận chỉ từ mã HTTP.** Một lỗi mạng khi lấy JWKS có thể đi qua cơ chế authentication/error handling khác nhau tùy framework và cấu hình, dẫn tới 401 hoặc lỗi dịch vụ khác; thiếu scope thường là 403. Phải phân tích log và metric của decoder để xác định lý do thực tế, đồng thời tránh lộ thông tin không cần thiết cho Client.

### Log an toàn

Có thể ghi:

- Request/correlation ID và endpoint.
- Loại lỗi: discovery failure, JWKS fetch failure, unknown `kid`, issuer/audience mismatch, expired token, insufficient scope.
- Issuer/audience **được cấu hình** và những dữ kiện đã xác minh được, theo chính sách log của tổ chức.
- Trạng thái dependency, độ trễ gọi metadata/JWKS/introspection.

Không ghi **nguyên access token**, refresh token, client secret, private key hoặc claim nhạy cảm không cần thiết. Nếu chưa xác minh chữ ký, `iss`/`sub`/`kid` trong token là **dữ liệu do phía gửi kiểm soát**, phải được ghi log và xử lý với sự thận trọng phù hợp.

## 11. Tình huống thực tế theo từng giai đoạn

### Tình huống A — Triển khai mới khi AS down

Orders API được cấu hình chỉ `issuer-uri`. Decoder cần khám phá metadata ở giai đoạn startup, nhưng metadata endpoint không phản hồi.

**Kết quả có thể xảy ra:** instance không hoàn tất khởi động. Giải pháp cho hệ thống cần giảm phụ thuộc startup là khai báo `jwk-set-uri` tin cậy cùng issuer hoặc có cơ chế phân phối khóa phù hợp. Sau khi thay đổi, vẫn phải kiểm tra việc nhận JWT và quay vòng khóa; khởi động thành công không đồng nghĩa mọi token sẽ xác minh thành công.

### Tình huống B — AS down sau khi JWT đã được xác minh thành công

Instance Orders API đã có public JWK đang dùng. Shop Web giữ access token còn hạn, cùng `kid` đã biết và `aud = orders-api`.

**Kết quả có thể xảy ra:** API tiếp tục xác minh JWT và thực thi scope/quyền dữ liệu mà không gọi AS. Khi access token hết hạn, Shop Web có thể không refresh được cho tới khi token endpoint phục hồi.

### Tình huống C — AS quay vòng khóa ngay trước outage

AS bắt đầu ký JWT bằng khóa `kid = new-key`, trong khi Orders API chỉ có khóa `old-key`. JWKS endpoint lại không phản hồi.

**Kết quả đúng:** API không chấp nhận JWT mà nó không thể xác minh. Quy trình rotation tốt cần công bố public key mới trước khi dùng để ký, cho phép cache được cập nhật và giữ khóa cũ đủ lâu cho các token cũ.

### Tình huống D — JWT đúng chữ ký nhưng sai audience

AS đã phát token hợp lệ cho `billing-api`, Client lại gửi đến Orders API. AS đang down nhưng Orders API có khóa cũ.

**Kết quả đúng:** từ chối token theo kiểm tra `aud`. Có khóa xác minh cục bộ không phải lý do để bỏ qua audience.

### Tình huống E — Opaque token và introspection bị gián đoạn

Orders API dùng `opaque-token`, phải gọi introspection cho từng token mới. AS không phản hồi.

**Kết quả đúng:** không cho phép thao tác được bảo vệ khi không xác minh được trạng thái token. Nếu hệ thống có cache introspection, hành vi phải theo TTL/expiration/revocation policy đã được phê duyệt; không “coi mọi token còn active” trong thời gian outage.

### Tình huống F — Một instance có khóa nhưng một instance chưa có

Load balancer phân phối request tới hai pod: pod A đã tải JWKS, pod B vừa restart và cache rỗng. AS down.

**Kết quả có thể xảy ra:** cùng một JWT có thể thành công ở A nhưng thất bại ở B. Đây là vấn đề về **trạng thái khóa theo từng instance**, không phải token thay đổi quyền ngẫu nhiên. Quan sát log theo pod, `kid`, trạng thái JWKS cache và chiến lược rollout giúp xác định nguyên nhân.

## 12. Các bài kiểm tra nên có trước khi triển khai

Để kiểm chứng kiến trúc, có thể thiết kế các kịch bản integration/chaos test trong môi trường kiểm thử; không cần làm gián đoạn Authorization Server production:

| Kịch bản | Điều cần quan sát |
| --- | --- |
| Khởi động API chỉ có issuer khi metadata endpoint không truy cập được | Hành vi startup thực tế của đúng phiên bản/framework |
| Khởi động API với issuer + JWKS URI khi discovery endpoint down | Decoder có thể dựng không cần discovery; chưa suy ra request đầu tiên sẽ thành công |
| API có key cache, sau đó AS/JWKS down | JWT ký bằng khóa đã biết còn được chấp nhận theo cache policy và thời hạn hay không |
| JWT có `kid` mới khi JWKS down | Token không xác minh được phải bị từ chối |
| JWT đúng chữ ký nhưng `iss` sai | Bị từ chối |
| JWT đúng issuer nhưng `aud` sai | Bị từ chối |
| JWT đã hết hạn hoặc có `nbf` trong tương lai | Bị từ chối |
| JWT hợp lệ nhưng thiếu scope | Bị từ chối ở authorization |
| API dùng opaque token, introspection không phản hồi | Không thực hiện thao tác được bảo vệ |
| OIDC Client refresh token khi AS down | Thất bại rõ ràng, có cơ chế báo trạng thái/khôi phục theo UX |
| JWKS key rotation sau khi AS phục hồi | API có thể nhận khóa mới theo quy trình mà không bỏ kiểm tra chữ ký |

Các test quan trọng ở đây là **hành vi có/không có mạng và sự khác biệt giữa startup với runtime**. Một test chỉ kiểm tra rằng property `jwk-set-uri` có giá trị chưa đủ chứng minh Resource Server thật sự chịu lỗi khi issuer không sẵn sàng.

## 13. Runbook khi Authorization Server tạm ngừng

### Bước 1 — Xác định phạm vi sự cố

Kiểm tra riêng metadata endpoint, JWKS, token endpoint, authorization endpoint và introspection endpoint. Cùng một tên “AS down” có thể bao gồm nhiều loại sự cố khác nhau.

### Bước 2 — Xác định đường xác minh của API

API đang dùng:

~~~text
(A) Signed JWT + issuer discovery
(B) Signed JWT + issuer-uri và jwk-set-uri rõ ràng
(C) Signed JWT + khóa public cục bộ
(D) Opaque token + introspection
~~~

Với (A), kiểm tra phụ thuộc discovery khi startup. Với (B)/(C), kiểm tra tình trạng khóa phù hợp với `kid` và cache. Với (D), kiểm tra introspection và chính sách chịu lỗi.

### Bước 3 — Bảo vệ request trong thời gian sự cố

Giữ nguyên kiểm tra mật mã, issuer, audience và quyền. Không chấp nhận JWT chưa xác minh hay opaque token chưa được introspect/có cơ sở tin cậy. Nếu cần xử lý degraded mode, chỉ thực hiện **những tác vụ không đòi hỏi xác thực mới hoặc đã có phương án quyền tin cậy được thiết kế trước**, không tự tạo quyền tạm thời.

### Bước 4 — Hạn chế ảnh hưởng tới khởi động và rollout

Nếu decoder cần discovery tại startup, cân nhắc tạm dừng các thay đổi không bắt buộc làm restart hàng loạt trong outage, giữ instance hiện có khi an toàn và phù hợp vận hành. Về lâu dài, cấu hình issuer + JWKS URI hoặc cơ chế phân phối khóa có thể giảm rủi ro cho rollout, với yêu cầu kiểm tra rotation riêng.

### Bước 5 — Phục hồi và xác nhận

Sau khi AS phục hồi, xác nhận Client có thể xin token mới, API lấy được JWKS, token ký bằng `kid` hiện tại qua được xác minh, issuer/audience đúng và các endpoint còn thực thi scope/quyền dữ liệu. Xem lại metrics để xác định request hoặc instance nào vẫn phụ thuộc khóa cũ hoặc sai cấu hình.

### Bước 6 — Rút kinh nghiệm về ranh giới phụ thuộc

Ghi rõ hệ thống cần **startup độc lập đến mức nào**, **verification độc lập đến mức nào** và **việc phát hành token cần SLA nào**. Những mục tiêu này dẫn tới giải pháp khác nhau; không có một cờ cấu hình duy nhất khiến toàn bộ OAuth2/OIDC hoạt động hoàn toàn offline.

## 14. Các nhầm lẫn thường gặp

**“Authorization Server down thì JWT Resource Server chắc chắn down.”** Không nhất thiết. Resource Server có thể xác minh JWT bằng khóa công khai đã có. Tuy nhiên, discovery/JWKS/introspection hoặc các dependency khác có thể khiến một số instance/request thất bại.

**“Có `jwk-set-uri` là mọi JWT đều được xác minh offline.”** Không. JWKS URI chỉ cho biết **nơi tải** khóa; lúc cache trống hoặc có `kid` mới, API vẫn có thể cần gọi endpoint đó.

**“Không cần issuer vì đã biết JWKS.”** Sai trong một hợp đồng thông thường. JWKS giúp xác minh chữ ký nhưng không thay thế quy tắc kiểm tra `iss`, `aud` và token profile.

**“Chỉ cần token giải mã được là có thể cho truy cập khi AS down.”** Sai. Decode Base64URL không chứng minh tính toàn vẹn hoặc nguồn cấp. Không được fail open.

**“Resource Server sẽ gọi token endpoint để kiểm tra mọi JWT.”** Signed JWT thường được xác minh cục bộ bằng public JWK, không cần gọi token endpoint trên mỗi request. Opaque token dùng introspection là cơ chế khác.

**“AS down thì người dùng cũ lập tức bị đăng xuất khỏi mọi ứng dụng.”** Không mặc định. Phiên ứng dụng và access token đã cấp có vòng đời riêng. Nhưng việc đăng nhập mới/refresh token có thể thất bại khi AS không sẵn sàng.

**“JWT không cần tới AS nữa sau lần đầu.”** Không hoàn toàn. JWKS refresh/key rotation và quy tắc thu hồi có thể cần trao đổi thêm. Một JWT hợp lệ theo chữ ký cũng không tự phản ánh mọi thay đổi quyền mới nhất.

**“Trả 200 để giữ hệ thống chạy trong outage là chấp nhận được.”** Nếu chưa xác minh được credential, việc trả dữ liệu được bảo vệ tạo lỗ hổng. Availability không được đánh đổi bằng cách bỏ authentication/authorization.

**“Readiness thất bại nghĩa là nên restart ngay mọi pod.”** Không nhất thiết. Restart hàng loạt trong khi metadata/JWKS down có thể biến instance đang còn khóa thành instance cache trống, làm sự cố lan rộng. Liveness/readiness phải được thiết kế theo loại phụ thuộc và yêu cầu phục vụ.

---

**Ghi nhớ:** Spring Security Resource Server với `issuer-uri` có thể cần **discovery metadata** từ Authorization Server khi khởi tạo decoder; nếu AS đang ngừng, điều đó có thể ảnh hưởng tới **startup**. Khai báo thêm **`jwk-set-uri`** tin cậy giúp bỏ bước tìm địa chỉ khóa qua discovery lúc khởi tạo, đồng thời vẫn có thể giữ kiểm tra **`iss`**. Khi **xác minh JWT ở runtime**, Resource Server có thể tiếp tục xử lý token đã cấp nếu còn khóa phù hợp và token hợp lệ, nhưng sẽ gặp khó khăn khi cần lấy/refresh JWKS. Với **opaque token**, introspection tạo phụ thuộc trực tiếp hơn vào AS. Trong mọi trường hợp, chỉ cho phép truy cập sau khi token đã được xác minh và quyền trên tài nguyên được thực thi đầy đủ.
