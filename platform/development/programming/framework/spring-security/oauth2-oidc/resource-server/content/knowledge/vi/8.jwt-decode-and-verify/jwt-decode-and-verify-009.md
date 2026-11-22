# Xử lý typ và hồ sơ token theo khả năng của phiên bản

Khi một **Spring Security OAuth 2.0 Resource Server** nhận JWT, chỉ kiểm tra chữ ký, thời hạn và issuer chưa phải lúc nào cũng đủ. API còn phải biết **đó là loại token nào** và **token có tuân thủ hồ sơ (profile) mà API chấp nhận hay không**. Một chỉ báo quan trọng nằm trong **JOSE header**, tên là `typ`. Ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

Giá trị `at+jwt` thường được dùng cho **JWT access token theo RFC 9068**, còn `JWT` là một giá trị kiểu tổng quát thường gặp. Cách Spring Security/Nimbus xác minh `typ` đã và có thể tiếp tục thay đổi theo phiên bản: ở một số phiên bản, decoder của Nimbus kiểm tra kiểu ngay trong quá trình giải mã; ở các phiên bản hoặc chế độ khác, Spring Security có thể kiểm tra bằng **`OAuth2TokenValidator<Jwt>`**. Vì vậy, khi hỗ trợ hồ sơ token như `at+jwt`, cần phân biệt **hồ sơ chuẩn**, **hợp đồng của Authorization Server** và **API thực sự có trong phiên bản dependency đang dùng**.

Mục tiêu của bài là hiểu cách `typ` tham gia bảo vệ Resource Server, tránh nhầm access token với ID token, cấu hình validation theo khả năng phiên bản và biết giới hạn của từng cách làm.

## 1. `typ` trong JOSE header là gì?

Một JWT ký theo JWS Compact Serialization thường có ba phần:

~~~text
BASE64URL(protected-header).BASE64URL(claims-payload).BASE64URL(signature)
~~~

Ví dụ JWT access token đã được giải mã phần header và payload:

**JOSE protected header:**

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-7"
}
~~~

**JWT Claims Set:**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "iat": 1761955200,
  "exp": 1761958800,
  "jti": "token-abc-123",
  "scope": "orders.read"
}
~~~

Ở đây:

| Trường | Vị trí | Ý nghĩa chính |
| --- | --- | --- |
| `alg` | JOSE header | Thuật toán bảo vệ chữ ký/chứng thực mà JWT tuyên bố sử dụng; API phải giới hạn thuật toán được phép |
| `kid` | JOSE header | Gợi ý định danh khóa để tìm khóa xác minh phù hợp trong tập khóa **đáng tin cậy** |
| `typ` | JOSE header | Khai báo loại nội dung/token, giúp phân biệt các loại JWT theo hợp đồng giao thức |
| `cty` | JOSE header khi có | Kiểu nội dung bên trong; thường liên quan đến JWT lồng nhau, **không phải đồng nghĩa với `typ`** |
| `iss`, `sub`, `aud` | JWT claims | Issuer, subject, audience |
| `exp`, `nbf`, `iat` | JWT claims | NumericDate: thời điểm hết hạn, bắt đầu hiệu lực, phát hành |
| `scope`, `client_id` | JWT claims theo hồ sơ/hợp đồng | Phạm vi quyền được cấp, định danh client |

**`typ` nằm trong JOSE header, không phải là claim ở payload.** Một payload có trường `"typ": "at+jwt"` do issuer tự đặt không thay thế việc kiểm tra protected-header `typ` theo hồ sơ token.

`typ` có thể giúp ứng dụng ngăn một JWT có **mục đích khác** bị sử dụng sai vị trí. Tuy nhiên, `typ` chỉ là một trường dữ liệu; nó **không tự xác minh** chữ ký, issuer, audience, thời hạn hay scope. Kẻ tấn công có thể tự viết bất kỳ `typ` nào vào một token giả. Hệ thống chỉ nên dựa vào `typ` sau khi token đã đi qua xử lý mật mã và các kiểm tra tin cậy phù hợp.

### Phân biệt `typ` và `cty`

Ví dụ header JWS thông thường:

~~~json
{
  "alg": "RS256",
  "typ": "JWT"
}
~~~

Header của **nested JWT** có thể có `cty` cho biết nội dung bên trong là JWT:

~~~json
{
  "alg": "dir",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

Ví dụ thứ hai chỉ minh họa ý nghĩa `cty` ở một lớp JOSE mã hóa. Resource Server cấu hình `NimbusJwtDecoder` cho JWS thông thường **không mặc nhiên có khả năng đọc mọi JWE hoặc nested JWT**. Nếu hệ thống sử dụng token mã hóa/lồng nhau, cần decoder, khóa, chính sách JOSE và xử lý lớp token phù hợp với định dạng được phát hành.

## 2. JWT tổng quát và hồ sơ JWT chuyên biệt

**JWT (RFC 7519)** định nghĩa cấu trúc và các claim cơ bản. Trên nền tảng này, những giao thức khác có thể đặt thêm quy tắc để chỉ rõ JWT được dùng làm gì.

Một **token profile** là bộ ràng buộc cụ thể hơn về định dạng và ngữ nghĩa token. Profile có thể quy định:

- Giá trị `typ` phải có hoặc thuộc tập giá trị nào.
- Các claim bắt buộc, kiểu dữ liệu và cách diễn giải của chúng.
- Bên phát hành nào được chấp nhận.
- Audience nào hợp lệ cho ứng dụng/API nhận token.
- Yêu cầu thuật toán, chữ ký, thời hạn, cách lấy khóa và mức độ tin cậy.
- Quy tắc về chủ thể, client, scope hoặc các claim đặc thù.

Một số dạng token dễ gặp:

| Token hoặc profile | Giá trị `typ` có thể gặp | Được dùng ở đâu? | Resource Server cần lưu ý |
| --- | --- | --- | --- |
| JWT tổng quát theo RFC 7519 | `JWT` hoặc không có `typ`, tùy quy ước | Nhiều loại ứng dụng dùng JWT | Không thể suy luận đây chắc chắn là OAuth 2.0 access token |
| JWT access token theo RFC 9068 | `at+jwt` hoặc `application/at+jwt` | Client gửi đến Resource Server | Kiểm tra kiểu token cùng **toàn bộ** điều kiện profile access token |
| OIDC ID token | Thường là JWT; `typ` không phải luôn là `at+jwt` | OIDC Client dùng để xác thực người dùng | **Không** sử dụng ID token thay cho access token của API |
| JWT có profile nội bộ | Giá trị do profile quy định | Chỉ trong hệ thống/quan hệ tin cậy xác định | Cần validator theo đúng tài liệu issuer, không tự mặc định tương thích RFC 9068 |
| Opaque access token | Không có JOSE header đọc trực tiếp theo JWT | Resource Server xác thực qua introspection hoặc cơ chế issuer hỗ trợ | Kiểm tra `typ` của JWT không áp dụng cho chuỗi opaque |

Hai JWT có thể cùng chữ ký hợp lệ, cùng issuer và cùng claim `sub` nhưng **mục đích sử dụng khác nhau**. Chẳng hạn:

- **ID token** xác nhận một lần xác thực người dùng đối với OIDC client; `aud` thường hướng đến định danh của client.
- **Access token** dành cho Resource Server; `aud` phải phản ánh API hoặc resource indicator được phép.

Nếu API chỉ kiểm tra chữ ký và `iss`, rồi coi mọi JWT từ issuer là token gọi API hợp lệ, nó có nguy cơ chấp nhận **token được phát hành cho bên nhận hoặc mục đích khác** (token confusion/cross-JWT confusion).

## 3. `typ` trong RFC 7519 và RFC 9068

### 3.1. JWT chung: `typ` là tùy chọn, profile có thể siết chặt

Trong JWT tổng quát, header `typ` được dùng để khai báo kiểu đối tượng. Một JWT hợp lệ theo cấu trúc chung **không bắt buộc** phải có `typ`. Giá trị `JWT` rất phổ biến, nhưng riêng giá trị đó **không chứng minh** token là OAuth 2.0 access token dành cho API.

Điều này giải thích vì sao Resource Server không thể chỉ làm:

~~~text
if header.typ == "JWT" then accept
~~~

Một JWT dành cho mục đích khác cũng có thể mang `typ: JWT`. Kiểm tra `typ` chỉ có ý nghĩa khi kết hợp với **những điều kiện khác của token profile**.

### 3.2. RFC 9068: JWT Profile for OAuth 2.0 Access Tokens

**RFC 9068** quy định một profile chuẩn để biểu diễn OAuth 2.0 access token bằng JWT. Điểm nhận diện quan trọng là JOSE header `typ` dùng:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt"
}
~~~

Hoặc dạng media type đầy đủ được profile cho phép:

~~~json
{
  "alg": "RS256",
  "typ": "application/at+jwt"
}
~~~

Khi API chỉ chấp nhận access token theo **RFC 9068**, token có `typ: JWT` chung, hoặc không có `typ`, **không đáp ứng điều kiện type của profile**, dù nó có thể vẫn là JWT đúng định dạng chung.

RFC 9068 đặt thêm các yêu cầu đối với issuer, chữ ký, audience, thời gian và các claim trong access token. Các claim điển hình của profile gồm:

| Claim | Ý nghĩa |
| --- | --- |
| `iss` | Authorization Server/issuer đã phát hành access token |
| `sub` | Chủ thể token nói tới; có thể phản ánh người dùng hoặc thực thể client tùy grant |
| `aud` | Resource Server hoặc tập resource đích được chỉ định |
| `exp` | Thời hạn token |
| `iat` | Thời điểm phát hành |
| `jti` | Định danh token |
| `client_id` | OAuth 2.0 client nhận quyền |
| `scope` | Phạm vi quyền được cấp khi có; không phải claim quyền sở hữu mọi đối tượng |

Một access token mang `typ: at+jwt` **vẫn có thể bị từ chối** nếu chữ ký sai, `iss` không đáng tin, `aud` không chứa API hiện tại, token đã hết hạn, claim bắt buộc thiếu/sai kiểu hoặc chính sách quyền không cho phép.

**Không nên chấp nhận `typ: JWT` như một cách “tương đương” với `at+jwt` nếu hợp đồng thực tế yêu cầu RFC 9068.** Muốn cho phép nhiều profile, hãy mô tả rõ từng profile và áp dụng validator riêng với các điều kiện của nó.

### 3.3. Token do issuer phát hành có thể không theo RFC 9068

Không phải mọi OAuth 2.0 Authorization Server đều phát hành access token theo RFC 9068. Có nhà cung cấp:

- Phát hành **opaque access token**.
- Phát hành JWT access token với `typ: JWT`.
- Phát hành JWT có header hoặc claims theo profile riêng.
- Chỉ hỗ trợ RFC 9068 khi bật cấu hình hoặc chọn loại client/resource cụ thể.

Vì vậy, **không bật profile RFC 9068 một cách máy móc** chỉ vì token có hình dạng JWT. Trước khi cấu hình, cần xác định access token issuer thực sự cấp và các yêu cầu chính thức của issuer/API.

## 4. `typ` được kiểm tra ở tầng nào trong Spring Security?

Với Resource Server JWT trên Servlet stack, luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["AuthenticationManager"]
    C --> D["JwtAuthenticationProvider"]
    D --> E["JwtDecoder / NimbusJwtDecoder"]
    E --> F{"JOSE & JWT hợp lệ?"}
    F -- "Không" --> X["AuthenticationException → 401"]
    F -- "Có" --> G["JWT claims và protected headers"]
    G --> H["Jwt validators: thời gian, issuer, audience, typ/profile..."]
    H --> I{"Đáp ứng chính sách token?"}
    I -- "Không" --> X
    I -- "Có" --> J["JwtAuthenticationConverter"]
    J --> K["JwtAuthenticationToken"]
    K --> L["SecurityContext và authorization"]
    L --> M["Controller hoặc 403 nếu thiếu quyền"]
~~~

Vị trí kiểm tra `typ` **có thể khác nhau theo phiên bản**:

1. **Trong tầng xử lý JOSE/JWT của Nimbus**: decoder có thể từ chối header `typ` không thuộc loại nó chấp nhận **trước khi** Spring `OAuth2TokenValidator<Jwt>` nhận được đối tượng `Jwt`.
2. **Trong tầng token validator của Spring Security**: decoder được cấu hình để chuyển quyết định về `typ` cho validator, chẳng hạn `JwtTypeValidator` hoặc validator theo profile `at+jwt`, nếu API đó có trong phiên bản đang dùng.

Đối với nhà phát triển, điều này dẫn đến hai trường hợp khác nhau:

| Hiện tượng | Giải thích |
| --- | --- |
| Token `at+jwt` bị decoder từ chối ngay, validator tự viết không thấy token | Tầng Nimbus vẫn đang kiểm tra kiểu như JWT tổng quát |
| Token đã decode nhưng bị validator từ chối do `typ` | Phần kiểm tra header đã đi tới tầng validator của Spring Security |

Vì vậy, khi xử lý token khác `typ: JWT`, **không chỉ thêm một validator rồi kỳ vọng nó luôn được gọi**. Trước hết phải xem khả năng xử lý `typ` của `NimbusJwtDecoder` trong đúng phiên bản Spring Security đang chạy.

## 5. Tại sao câu trả lời phải phụ thuộc phiên bản?

**Spring Security, Spring Boot, Nimbus JOSE + JWT và các starter liên quan có vòng đời phiên bản riêng.** Spring Boot quản lý tập dependency mặc định, nhưng dự án có thể override thủ công. Tên class, builder option và hành vi validation thay đổi theo các dòng phiên bản.

Có ba mức khả năng cần phân biệt:

| Mức khả năng | Bạn có thể làm gì? | Điều cần xem trong phiên bản thực tế |
| --- | --- | --- |
| **Chỉ có decoder JWT thông thường** | Xác minh JWT theo cấu hình và những profile mà decoder mặc định hỗ trợ | Header `typ` mặc định được chấp nhận là gì; có khả năng chuyển kiểm tra type sang validator không |
| **Decoder hỗ trợ tùy chọn `validateType(false)`** | Cho tầng Nimbus không tự quyết định `typ` theo quy tắc mặc định, để tầng Spring kiểm tra bằng validator | Builder bạn đang dùng có phương thức này không; các validator đi kèm là gì |
| **Có `JwtTypeValidator` hoặc `JwtValidators.createAtJwtValidator()`** | Kiểm tra `typ` hoặc một profile `at+jwt` bằng cơ chế validation được Spring Security cung cấp | Chính xác public API, chữ ký phương thức, ràng buộc claim và chính sách mặc định của phiên bản |

Trong những phiên bản hỗ trợ, cách tiếp cận được khuyến nghị là **để decoder kiểm tra chữ ký và các lớp validator kiểm tra hợp đồng token cụ thể**. Tuy nhiên, không nên sao chép ví dụ API từ phiên bản mới vào dự án cũ rồi tự sửa lệnh gọi theo phỏng đoán.

### Checklist khi chọn cấu hình cho phiên bản của dự án

1. Xác định **phiên bản Spring Boot và Spring Security thực sự được resolve** khi build, không suy luận chỉ từ một phiên bản starter viết trong tài liệu.
2. Xác định issuer phát hành **JWT hay opaque**, có `typ` nào, profile nào và có hỗ trợ metadata/JWKS hay không.
3. Kiểm tra API `NimbusJwtDecoder` của phiên bản: builder `withIssuerLocation(...)` hoặc `withJwkSetUri(...)` có `validateType(...)` không.
4. Kiểm tra `JwtValidators` có builder kiểm tra **RFC 9068** không; nếu không, kiểm tra `JwtTypeValidator` hoặc khả năng cung cấp `OAuth2TokenValidator<Jwt>` riêng.
5. Xác định tập validator đang chạy cho **issuer, audience, thời hạn, type/profile**. Tránh thay thế một validator rồi vô tình bỏ mất các kiểm tra còn lại.
6. Phân biệt **điều kiện parse/verify của Nimbus** với **điều kiện validate của Spring**. Chỉ một tầng từ chối thì request cũng không được xác thực.

**“Hỗ trợ `at+jwt`” không chỉ có nghĩa là decoder không ném lỗi khi thấy `typ: at+jwt`.** Hỗ trợ đúng còn đòi hỏi kiểm tra các yêu cầu profile và chính sách của Resource Server.

## 6. Cấu hình JWT Resource Server cơ bản

Với Spring Boot Servlet ứng dụng API, dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Ví dụ `application.yml` khi issuer phát hành JWT được API chấp nhận:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Ví dụ Servlet security chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là cấu hình bảo vệ API bằng bearer JWT, **chưa tự bảo đảm kiểm tra audience hoặc một token profile riêng như RFC 9068** ở mọi phiên bản. Việc tắt CSRF trong ví dụ chỉ phù hợp cho API stateless xác thực bằng bearer token và **không** dùng cookie xác thực tự động gửi từ trình duyệt; ứng dụng có cookie phiên cần bảo vệ CSRF thích hợp.

Nếu token có scope `orders.read`, mapping mặc định thường tạo authority `SCOPE_orders.read`. Điều đó chỉ kiểm tra quyền ở mức thao tác; logic đọc đơn hàng vẫn phải xác minh người gọi có được xem **đúng bản ghi và tenant** hay không.

## 7. Cấu hình theo profile RFC 9068 khi phiên bản hỗ trợ

Ở các phiên bản Spring Security **có** builder option `validateType(false)` và phương thức `JwtValidators.createAtJwtValidator()`, có thể cấu hình JWT decoder theo hướng sau.

### 7.1. Ví dụ cho một issuer, một API và một client được phép

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class AccessTokenJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://auth.example.com/realms/shop";
    private static final String AUDIENCE = "orders-api";
    private static final String CLIENT_ID = "orders-web";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(ISSUER)
            .validateType(false)
            .build();

        OAuth2TokenValidator<Jwt> accessTokenValidator =
            JwtValidators.createAtJwtValidator()
                .issuer(ISSUER)
                .audience(AUDIENCE)
                .clientId(CLIENT_ID)
                .build();

        decoder.setJwtValidator(accessTokenValidator);
        return decoder;
    }
}
~~~

**Điều kiện áp dụng:** Đây là ví dụ cho **dòng phiên bản có đầy đủ các API vừa dùng**. Nếu `createAtJwtValidator()` hoặc `validateType(false)` không có trong dependency của dự án, ví dụ **không biên dịch**. Khi ấy cần tìm phương án tương thích với phiên bản thực tế, hoặc cân nhắc nâng cấp, thay vì xóa các bước kiểm tra bảo mật để cho code chạy.

Phân tích từng phần:

1. `withIssuerLocation(ISSUER)` thiết lập cách xác định thông tin issuer/JWKS theo cơ chế hỗ trợ. Kết nối đến issuer phải được tin cậy theo cấu hình hệ thống.
2. `validateType(false)` **không có nghĩa “bỏ xác thực JWT”**. Trong những phiên bản cung cấp tùy chọn này, nó tắt cơ chế kiểm tra `typ` mặc định ở tầng decoder tương ứng để việc kiểm tra loại token có thể do validator của Spring Security quyết định.
3. `createAtJwtValidator()` cung cấp cách kiểm tra profile **OAuth 2.0 access token JWT theo RFC 9068** khi Spring Security có hỗ trợ.
4. `issuer(...)`, `audience(...)` và `clientId(...)` chỉ rõ những giá trị mà ví dụ này kỳ vọng.
5. `setJwtValidator(...)` gắn validator vào decoder; đây là nơi dễ mắc lỗi nếu thay thế validators cần thiết bằng một validator quá hẹp.

Trong trường hợp API cho phép **nhiều client**, không thể gắn cứng một `CLIENT_ID` như ví dụ và mong mọi client khác được chấp nhận. Cần thiết kế chính sách client được phép dựa trên hợp đồng issuer/API, rồi sử dụng cách validate tương ứng với phiên bản. Đừng loại bỏ toàn bộ xác thực `client_id` chỉ để mọi token đi qua nếu hệ thống thực sự có yêu cầu kiểm soát client.

### 7.2. Vì sao không chỉ gọi `validateType(false)`?

Đây là cấu hình **thiếu bước xác minh profile** nếu không có validator `typ`/access-token tương ứng:

~~~java
// MINH HỌA cách làm chưa đầy đủ cho API yêu cầu at+jwt.
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation("https://auth.example.com/realms/shop")
    .validateType(false)
    .build();

// Chưa chỉ rõ validator cho at+jwt/token profile.
~~~

Khi decoder không kiểm tra kiểu trong tầng Nimbus mà ứng dụng cũng không kiểm tra ở tầng Spring, API có thể **mất lớp bảo vệ phân biệt loại JWT**. Nguy cơ này đặc biệt đáng chú ý nếu cùng issuer phát hành ID token và access token cho các bên nhận khác nhau.

**Cách dùng đúng** là phối hợp giải mã/chữ ký và validator profile thích hợp: loại JWT, issuer, audience, thời hạn, các claim bắt buộc và chính sách ứng dụng.

### 7.3. Nguy cơ thay thế mất validators mặc định

Một lỗi khác là gắn validator mới chỉ kiểm tra một điều kiện:

~~~java
// KHÔNG DÙNG một mình cho Resource Server bảo vệ API.
decoder.setJwtValidator(jwt ->
    "at+jwt".equals(jwt.getHeaders().get("typ"))
        ? org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.success()
        : org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.failure(
            new org.springframework.security.oauth2.core.OAuth2Error("invalid_token")
        )
);
~~~

`setJwtValidator(...)` thay validator đã gắn trên decoder. Nếu ứng dụng thay thế validator tổng hợp bằng một bộ chỉ so `typ` mà không giữ các kiểm tra thời gian, issuer, audience và profile tương ứng, token không hợp lệ có thể bị chấp nhận.

Trong phiên bản có hỗ trợ profile validator chuẩn, **ưu tiên dùng profile validator phù hợp**. Nếu phải tự định nghĩa validator, hãy xây chuỗi kiểm tra đầy đủ và gắn vào decoder với những thành phần thực sự có trong version. Đừng coi “decoder kiểm tra chữ ký” là tương đương “Resource Server đã kiểm tra toàn bộ token”.

## 8. Tự kiểm tra `typ` bằng `OAuth2TokenValidator<Jwt>`

Không phải tổ chức nào cũng sử dụng RFC 9068. Một số API nhận JWT theo một profile nội bộ có `typ` cụ thể. Với phiên bản cho phép chuyển việc kiểm tra `typ` sang tầng Spring Security, ứng dụng có thể viết validator riêng.

Ví dụ **chỉ minh họa cách kiểm tra JOSE header** cho token profile chấp nhận hai cách biểu diễn `at+jwt`:

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
        boolean matchesProfile =
            "at+jwt".equals(typ) ||
            "application/at+jwt".equals(typ);

        if (matchesProfile) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Unexpected token type for this API",
                null
            )
        );
    }
}
~~~

**Giới hạn của ví dụ:** Validator này **chỉ kiểm tra `typ`**, chưa phải một bộ kiểm tra **RFC 9068 đầy đủ**. Nó không chứng minh `iss`, `aud`, `exp`, `client_id`, `jti` và các điều kiện khác hợp lệ. Nếu phiên bản hỗ trợ `JwtValidators.createAtJwtValidator()` thì đó là điểm bắt đầu phù hợp hơn cho profile RFC 9068.

Nếu phải kết hợp các validators riêng, Spring Security cung cấp `DelegatingOAuth2TokenValidator<Jwt>`. Ví dụ khái niệm:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

String issuer = "https://auth.example.com/realms/shop";
String expectedAudience = "orders-api";

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains(expectedAudience)
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null)
        );

OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(),
        new JwtIssuerValidator(issuer),
        audienceValidator,
        new AccessTokenTypeValidator()
    );

// Gắn validator vào NimbusJwtDecoder đã được cấu hình xác minh chữ ký
// và đã xử lý lựa chọn validateType phù hợp với phiên bản.
~~~

Đoạn code này mô tả **cách kết hợp các validator theo điều kiện riêng**, không thay cho profile RFC 9068 đầy đủ. Khi dùng thực tế, phải bổ sung các claim bắt buộc và chính sách mà API/issuer yêu cầu. Một số API trong ví dụ có thể khác ở phiên bản cũ; lúc đó hãy dùng cơ chế tương đương được phiên bản đó hỗ trợ.

**Thứ tự quan trọng về mặt tin cậy:** ứng dụng có thể đọc header chưa xác thực để định tuyến xử lý kỹ thuật trong những trường hợp đã thiết kế, nhưng **không được coi giá trị header tự khai báo là bằng chứng cấp quyền**. Chỉ chấp nhận JWT sau khi xác minh chữ ký/khóa đáng tin và toàn bộ validator bắt buộc thành công.

## 9. Các kiểu lỗi cần phân biệt khi xử lý `typ`

Giả sử Orders API chỉ nhận JWT access token theo RFC 9068, issuer `https://auth.example.com/realms/shop` và audience `orders-api`.

| Tình huống | Kết luận |
| --- | --- |
| `typ: at+jwt`, chữ ký hợp lệ, issuer/audience/thời hạn/claim profile hợp lệ | Token **có thể** được xác thực; còn phải kiểm tra scope và quyền nghiệp vụ |
| `typ: application/at+jwt` cùng các điều kiện hợp lệ | Có thể chấp nhận nếu API dùng đúng cách biểu diễn được profile cho phép |
| `typ: JWT` nhưng API bắt buộc RFC 9068 | Từ chối vì không đúng token type/profile |
| Không có `typ` trong khi profile bắt buộc | Từ chối theo yêu cầu profile |
| `typ: at+jwt` nhưng chữ ký không hợp lệ | Từ chối; header không chứng minh được sự tin cậy |
| `typ: at+jwt` nhưng `aud` dành cho Payments API | Từ chối; token không dành cho Orders API |
| `typ: at+jwt` nhưng hết hạn | Từ chối; giá trị type không gia hạn thời gian sống |
| `typ: at+jwt` với issuer lạ | Từ chối; không tin issuer ngoài danh sách cho phép |
| `typ: at+jwt`, hợp lệ nhưng thiếu `orders.write` | Xác thực có thể thành công nhưng request ghi dữ liệu bị **403** |
| Client gửi opaque token vào decoder JWT | Decoder JWT từ chối vì token không có cấu trúc/phương thức xác minh phù hợp |

Trong Resource Server, **token sai chữ ký/type/issuer/audience/expiry** thường dẫn đến lỗi xác thực như **401 Unauthorized**. Token xác thực hợp lệ nhưng không đủ scope hoặc quyền đối tượng thường dẫn đến **403 Forbidden**. Status và header `WWW-Authenticate` cụ thể tùy entry point/access-denied handler và cấu hình ứng dụng; không mặc định mọi 401 đều là sai `typ`.

### Khi `typ` hợp lệ nhưng vẫn nhận 401

Hãy tách nguyên nhân theo lớp:

1. **Bearer parsing**: header có đúng cú pháp không?
2. **JOSE processing**: JWS có cấu trúc hợp lệ, thuật toán được phép và chữ ký đúng không?
3. **Type/profile**: header `typ` có thuộc loại API chấp nhận và profile tương ứng có đủ claim không?
4. **Token validation**: `iss`, `exp`, `nbf`, `aud`, `client_id`... có đúng hợp đồng không?
5. **Authorization**: token hợp lệ nhưng scope/quyền thao tác có đủ không?

Không khắc phục lỗi bằng cách bỏ hết validator hoặc chấp nhận bất kỳ `typ` nào mà không làm rõ token profile của issuer.

## 10. Tránh nhầm OIDC ID token với OAuth 2.0 access token

OIDC ID token có thể cũng là JWT được ký bằng khóa của cùng một issuer. Ví dụ:

**ID token (minh họa):**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": "orders-web",
  "iat": 1761955200,
  "exp": 1761958800,
  "nonce": "n-123456"
}
~~~

**Access token dành cho Orders API (minh họa):**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "iat": 1761955200,
  "exp": 1761958800,
  "jti": "at-123456",
  "scope": "orders.read"
}
~~~

Cả hai có thể có `iss`, `sub` và `exp` giống nhau. Nhưng **ID token hướng đến OIDC client**, còn access token dành cho API. Nếu API chỉ so `iss` và chữ ký, client có thể vô tình hoặc cố ý gửi ID token vào `Authorization: Bearer ...`.

Cần xác định token purpose qua hợp đồng issuer:

- **Audience** của access token phải khớp API.
- **Header `typ`** phải đáp ứng profile khi profile yêu cầu.
- **Claims** phải có đúng ngữ nghĩa access token; riêng OIDC ID token có tập yêu cầu khác.
- API **không** chấp nhận token chỉ vì nó mang một danh tính người dùng hợp lệ.

Đây cũng là lý do không nên xây bộ lọc chỉ gọi `jwt.getSubject()` rồi coi có `sub` là đã xác thực đúng quyền truy cập API.

## 11. Nhiều issuer, nhiều token profile và nhiều SecurityFilterChain

Một hệ thống có thể tích hợp:

- Issuer A phát hành JWT access token theo RFC 9068 với `typ: at+jwt`.
- Issuer B phát hành access token JWT theo profile nội bộ, dùng `typ: JWT`.
- Một dịch vụ nội bộ khác phát hành opaque token và cung cấp introspection.

**Không nên gộp mọi token thành quy tắc “JWT nào cũng được”.** Mỗi loại cần có tập điều kiện tin cậy riêng: issuer, JWKS hoặc introspection endpoint, audience, thuật toán, thời hạn và profile.

Trên Servlet stack, một số hướng triển khai:

1. **Nhiều `SecurityFilterChain`**: phân tách các endpoint rõ ràng, mỗi chain có cách xác thực tương ứng nếu đường dẫn/API có hợp đồng token riêng.
2. **`AuthenticationManagerResolver<HttpServletRequest>`**: chọn authentication manager dựa trên ngữ cảnh đã được thiết kế và giới hạn bằng allowlist, áp dụng khi cùng phạm vi endpoint cần nhiều issuer/profile.
3. **Một issuer, một profile**: thường đơn giản nhất cho API; cấu hình một decoder với validators rõ ràng.

Ví dụ bố cục theo đường dẫn:

~~~text
/api/orders/**     -> issuer A / JWT at+jwt / audience orders-api
/api/legacy/**     -> issuer B / JWT theo profile riêng
/api/partner/**    -> introspection của issuer được phê duyệt
~~~

Với nhiều chain, phải cấu hình `securityMatcher(...)` và thứ tự chain đúng; không đăng ký vài chain áp dụng tràn lan cho cùng một đường dẫn rồi giả định cả ba đều được chạy.

**Không lấy `iss` hoặc `typ` từ payload/header chưa xác minh rồi tự động truy cập JWKS URL tùy ý của người gửi.** Nếu dùng token claims để chọn cơ chế xử lý, chúng chỉ nên đóng vai trò **gợi ý định tuyến** trong tập issuer/decoder tin cậy đã được kiểm soát. Việc xác minh cuối cùng phải bảo đảm token thực sự thuộc issuer, audience và profile tương ứng. Điều này vừa giúp tránh tin nhầm issuer vừa giảm nguy cơ server bị dẫn tới địa chỉ mạng ngoài kiểm soát.

## 12. JWT header `typ` và các vấn đề JOSE liên quan

Một validator chỉ kiểm tra `typ` sẽ không phát hiện toàn bộ rủi ro JOSE. Resource Server còn cần quan tâm:

### 12.1. Thuật toán và khóa tin cậy

JOSE header có thể tuyên bố `alg: RS256`, `ES256` hoặc giá trị khác. API phải giới hạn những thuật toán phù hợp với issuer và cấu hình khóa tin cậy. Không chấp nhận token `alg: none` như một signed access token bảo vệ API.

`kid` là **gợi ý chọn khóa**, không phải URL đáng tin cậy hay bằng chứng cho phép gọi API. Chỉ dùng khóa thuộc JWKS/keystore đã được cấu hình đáng tin; không tải khóa tùy ý từ một giá trị header do attacker đưa vào.

### 12.2. Header bổ sung, `crit` và profile mở rộng

Một số cơ chế JOSE sử dụng header mở rộng hoặc `crit` để thông báo các tham số bắt buộc phải hiểu. Các thành phần bảo mật phải tuân theo quy tắc JOSE/decoder cho những header này. Không nên tự viết bộ parser “bỏ qua mọi header không biết” để cố nhận token lạ.

### 12.3. JWT có `typ` đúng nhưng claim sai kiểu

Token có:

~~~json
{
  "exp": "1761958800",
  "aud": 123
}
~~~

không đáp ứng định dạng NumericDate của `exp` và dạng audience đúng theo JWT. **`typ` đúng không biến claim sai kiểu thành hợp lệ.** Tương tự, `"scope": ["orders.read"]` không được mặc nhiên hiểu giống chuỗi scope trong một profile yêu cầu định dạng string; phải kiểm tra theo tài liệu profile/issuer.

## 13. Phân biệt “khả năng cấu hình” với “hành vi mặc định”

Một ví dụ trên Internet có thể ghi:

~~~java
NimbusJwtDecoder.withIssuerLocation(issuer)
    .validateType(false)
    .build();
~~~

Đây là **một lựa chọn cấu hình ở các phiên bản có hỗ trợ**, không phải khẳng định rằng mọi phiên bản Spring Security đều:

- Có `validateType(false)`.
- Chấp nhận `at+jwt` mặc định.
- Tự động sử dụng `JwtTypeValidator`.
- Tự động bật đầy đủ RFC 9068 validators.
- Tự nhận biết ID token và access token chỉ qua định dạng JWT.

Tương tự, khi đã có `JwtValidators.createAtJwtValidator()` trong một phiên bản, cần hiểu bộ validators đó kiểm tra những điều kiện nào và truyền các tham số phù hợp với hệ thống. Hành vi mặc định ở phiên bản khác có thể thay đổi theo định hướng chuyển phần `typ` validation giữa Nimbus và Spring Security.

**Nguyên tắc bền vững qua các phiên bản:** phải quyết định rõ token profile mà API chấp nhận, xác thực chữ ký/khóa và issuer, kiểm tra audience/thời hạn/type/claims theo profile rồi mới dùng principal và authorities để phân quyền.

### Nếu phiên bản không có API mong muốn

Có những cách tiếp cận cần cân nhắc theo khả năng thực tế:

1. **Dùng profile mà issuer và decoder hiện tại cùng hỗ trợ**, với các validators cần thiết. Phải dựa trên hợp đồng token chứ không đơn giản yêu cầu issuer đổi `at+jwt` thành `JWT` để tránh lỗi.
2. **Nâng cấp Spring Security/Spring Boot tương thích** nếu cần hỗ trợ RFC 9068 và khả năng tùy chỉnh `typ` dễ kiểm soát hơn.
3. **Xây hoặc cấu hình `JwtDecoder`/JOSE processor tương thích** nếu không thể nâng cấp, bảo đảm đầy đủ xác minh chữ ký và profile. Đây là phần bảo mật nhạy cảm, phải dùng thư viện JOSE tin cậy và review thiết kế kỹ lưỡng.
4. **Dùng introspection** khi Authorization Server hỗ trợ và hợp đồng hệ thống cho phép. Đây là một phương thức xác minh khác, không phải cách “bỏ qua kiểm tra JWT `typ`” tùy tiện.

Việc loại bỏ `typ` validation mà không thay bằng chính sách token profile rõ ràng **không phải giải pháp tương đương**.

## 14. Ví dụ bảng hành vi mong muốn của Orders API

Giả sử yêu cầu thiết kế là: Orders API chỉ chấp nhận **access token RFC 9068** từ issuer tin cậy, audience `orders-api`, scope `orders.read` cho lệnh GET.

| Token thử nghiệm | Kết quả mong muốn | Lý do |
| --- | --- | --- |
| JWT ký đúng, `typ: at+jwt`, `iss` đúng, `aud` đúng, chưa hết hạn, đủ scope/profile | **200** nếu quyền trên đơn hàng cũng cho phép | Đúng profile và thỏa quyền nghiệp vụ |
| JWT ký đúng, `typ: JWT`, cùng issuer/audience | **401** | Sai loại token đối với profile RFC 9068 |
| JWT ký đúng, `typ: at+jwt`, `aud: payments-api` | **401** | Token không dành cho Orders API |
| JWT ký đúng, `typ: at+jwt`, `exp` quá hạn | **401** | Token hết hiệu lực |
| JWT `typ: at+jwt` nhưng chữ ký giả | **401** | Không tin cậy JWT dù `typ` nhìn đúng |
| JWT hợp lệ nhưng chỉ có `orders.write` | **403** | Thiếu scope cần cho GET |
| JWT hợp lệ và có `orders.read` nhưng user không được xem order 123 | **403** hoặc phản hồi nghiệp vụ phù hợp | Quyền trên đối tượng cụ thể không đủ |
| Không gửi bearer token | **401** cho endpoint bảo vệ | Thiếu thông tin xác thực |

Các mã HTTP nêu hành vi mong muốn theo cấu hình thông dụng; kết quả thực tế có thể bị ảnh hưởng bởi custom entry point, access-denied handler và chính sách trả lỗi nghiệp vụ.

### Lưu ý khi kiểm thử

**Kiểm thử bộ lọc/decoder thực sự** cần một JWT được ký bằng khóa thử nghiệm và một decoder/issuer configuration phù hợp. Các phương tiện mock authentication như `jwt()` trong Spring Security Test giúp kiểm tra **authorization rules**, nhưng thường **bỏ qua giải mã chữ ký và token validators thực tế**. Vì vậy, một test mock `jwt()` thành công **không chứng minh** API đã chặn sai `typ` hoặc sai signature trong production.

Nên phân biệt loại kiểm tra:

- **Kiểm tra authorization**: scope, authorities, endpoint và quyền truy cập đối tượng với `Authentication` đã xác thực.
- **Kiểm tra token validation**: JWT thật dùng issuer/khóa thử nghiệm, header `typ` đúng/sai, audience sai, hết hạn, chữ ký sai và claim profile thiếu.

Đây là định hướng để hiểu tính năng, không thay thế việc kiểm chứng với đúng phiên bản thư viện khi triển khai hệ thống.

## 15. Các nhầm lẫn phổ biến

**“`typ` là một claim, nên dùng `jwt.getClaimAsString("typ")`.”**  
Không. Trong trường hợp đang bàn, `typ` là **JOSE header**; với Spring Security `Jwt`, dùng `jwt.getHeaders()` để đọc header. Payload claim tùy chỉnh mang tên `typ` không tương đương.

**“`typ: JWT` nghĩa là đây chắc chắn là access token.”**  
Không. Đó là khai báo loại JWT tổng quát, không chỉ ra đầy đủ mục đích. ID token hoặc token khác cũng có thể là JWT.

**“Mọi OAuth 2.0 JWT access token đều có `typ: at+jwt`.”**  
Không. RFC 9068 là một profile cụ thể. Issuer có thể phát hành JWT theo profile khác hoặc opaque token.

**“Chỉ cần `validateType(false)` là nhận được RFC 9068 access token an toàn.”**  
Không. Tùy chọn này, khi tồn tại, chỉ thay đổi cách tầng decoder xử lý `typ`; phải có validators kiểm tra token profile đúng.

**“Chỉ cần validator so `typ` là đủ.”**  
Không. Còn cần xác minh JOSE signature, issuer, audience, thời hạn và các claim bắt buộc của profile.

**“Token bị từ chối do `typ` thì API nên tự cấp access token mới.”**  
Không. Spring Security Resource Server chỉ xác thực access token. Client phải xin token phù hợp từ Authorization Server theo grant được hỗ trợ.

**“Có `JwtTypeValidator` trong một bài viết thì phiên bản nào cũng dùng được.”**  
Không. Cần đối chiếu API công khai của phiên bản Spring Security đang dùng và xem validation được thực hiện ở tầng Nimbus hay Spring.

**“Nếu `typ` không giống profile, đổi nó bằng cách sửa payload/header JWT.”**  
Không. Header được bảo vệ bằng chữ ký JWS; thay đổi header làm chữ ký không còn hợp lệ. Chỉ Authorization Server có thẩm quyền phát hành token phù hợp theo profile được thiết kế.

## 16. Quy trình thiết kế cho Resource Server

Khi triển khai một API Spring Security OAuth 2.0/OIDC Resource Server, có thể lần lượt trả lời:

1. **Token đến từ ai?** Xác định issuer được phép, phương thức lấy khóa/JWKS hoặc introspection và tập thuật toán được chấp nhận.
2. **Token dùng cho mục đích gì?** Xác định JWT access token theo RFC 9068, JWT theo profile nội bộ, hay opaque token. Không nhầm với OIDC ID token.
3. **Header `typ` phải như thế nào?** Ghi rõ có bắt buộc không và những giá trị nào hợp lệ theo profile.
4. **Những claim nào bắt buộc?** Xác định `iss`, `aud`, `exp`, `iat`, `client_id`, `jti`, `scope` và custom claims theo đúng profile.
5. **Version hỗ trợ gì?** Kiểm tra `NimbusJwtDecoder`, `validateType(false)`, `JwtTypeValidator`, `JwtValidators.createAtJwtValidator()` và khả năng ghép validators trên bản thư viện đang chạy.
6. **Bảo vệ endpoint và dữ liệu ra sao?** Sau khi xác thực JWT, tiếp tục kiểm tra scope, role, tenant, quyền bản ghi và chính sách nghiệp vụ.
7. **Khi token sai sẽ làm gì?** Từ chối xác thực đúng cách; không bỏ validator hoặc chấp nhận token khác mục đích để “giải quyết” lỗi 401.

Một cấu hình bảo mật đúng phải trả lời cả **“token này được ai phát hành và có hợp lệ không?”** lẫn **“token này được phát hành theo profile nào và dành cho API này hay không?”**. Header `typ` chỉ là một phần của câu trả lời. Với Spring Security, hãy sử dụng đúng khả năng phiên bản để kết hợp kiểm tra `typ` và token profile với xác minh chữ ký, issuer, audience, thời hạn và phân quyền.
