# @SecurityScheme để đăng ký cơ chế xác thực

OpenAPI mô tả cách client xác thực khi gọi API thông qua các security scheme. Với springdoc-openapi, annotation <code>@SecurityScheme</code> đăng ký một cơ chế xác thực dùng lại trong <code>components.securitySchemes</code>. Sau đó, <code>@SecurityRequirement</code> tham chiếu scheme đó ở cấp API hoặc operation để cho biết endpoint nào yêu cầu xác thực.

Đăng ký scheme giúp Swagger UI hiểu cần hiển thị loại thông tin xác thực nào, chẳng hạn Bearer token, API key, Basic authentication hoặc OAuth2. Annotation chỉ mô tả hợp đồng cho công cụ và client. Ứng dụng vẫn phải cấu hình Spring Security, bộ lọc xác thực hoặc cơ chế kiểm tra credential tương ứng ở runtime.

## 1. Security scheme và security requirement khác nhau

Hai khái niệm này thường bị nhầm lẫn:

| Thành phần | Vai trò | OpenAPI đặt ở đâu |
|---|---|---|
| <code>@SecurityScheme</code> | Định nghĩa một cơ chế xác thực có thể dùng lại | <code>components.securitySchemes</code> |
| <code>@SecurityRequirement</code> | Gắn một cơ chế đã định nghĩa vào API hoặc operation | <code>security</code> ở cấp root hoặc operation |

Ví dụ, scheme có tên <code>bearerAuth</code> mô tả HTTP Bearer token. Chỉ đăng ký scheme này chưa có nghĩa tất cả endpoint đều yêu cầu token. Muốn áp dụng, cần thêm security requirement tham chiếu đúng tên <code>bearerAuth</code>.

Tên trong requirement phải khớp với tên đã đăng ký. Nếu scheme tên <code>bearerAuth</code> nhưng requirement tham chiếu <code>bearerToken</code>, OpenAPI sẽ không có component tương ứng.

## 2. Đăng ký HTTP Bearer token

Với API dùng access token trong header <code>Authorization</code>, khai báo scheme như sau:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Access token gửi trong Authorization header"
)
class OpenApiSecurityConfiguration {
}
~~~

Các thuộc tính quan trọng:

- <code>name</code>: tên component để requirement tham chiếu.
- <code>type = HTTP</code>: dùng cơ chế xác thực HTTP.
- <code>scheme = "bearer"</code>: sử dụng HTTP Bearer authentication.
- <code>bearerFormat = "JWT"</code>: gợi ý định dạng token cho người đọc và công cụ.
- <code>description</code>: giải thích cách client lấy và gửi token.

Khi scheme được hiển thị trong Swagger UI, người dùng thường thấy nút **Authorize** và có thể nhập token. UI sẽ thêm header theo dạng:

~~~http
Authorization: Bearer eyJ...example-token
~~~

<code>bearerFormat = "JWT"</code> chỉ là thông tin mô tả. Nó không kiểm tra chữ ký, issuer, audience, thời hạn hoặc scope của JWT. Những việc đó thuộc trách nhiệm của resource server và cấu hình bảo mật tại runtime.

### 2.1. Gắn Bearer scheme vào operation

Để mô tả một endpoint cần Bearer token, dùng <code>@SecurityRequirement</code>:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
class ProfileController {

    @GetMapping
    @SecurityRequirement(name = "bearerAuth")
    ProfileResponse getProfile() {
        return new ProfileResponse("user-100", "An");
    }
}

record ProfileResponse(String userId, String displayName) {}
~~~

<code>@SecurityRequirement</code> tham chiếu scheme đã khai báo. Swagger UI biết operation này cần Bearer token và có thể gửi token đã nhập trong Authorize khi thực thi request.

## 3. Đăng ký nhiều scheme với @SecuritySchemes

Một API có thể hỗ trợ nhiều cách xác thực, ví dụ Bearer token cho người dùng và API key cho đối tác tích hợp. Dùng <code>@SecuritySchemes</code> để khai báo nhiều scheme trên cùng cấu hình:

Đây là cấu hình thay thế cho class chỉ đăng ký Bearer ở phần trước. Trong một ứng dụng, hãy giữ một cấu hình tổng hợp với các tên scheme duy nhất; không khai báo hai class cùng tên <code>OpenApiSecurityConfiguration</code>.

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecuritySchemes({
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "Access token của người dùng"
    ),
    @SecurityScheme(
        name = "partnerApiKey",
        type = SecuritySchemeType.APIKEY,
        in = SecuritySchemeIn.HEADER,
        paramName = "X-API-Key",
        description = "API key cấp cho hệ thống đối tác"
    )
})
class OpenApiSecurityConfiguration {
}
~~~

Mỗi scheme có tên riêng. <code>partnerApiKey</code> mô tả API key nằm trong header <code>X-API-Key</code>; <code>bearerAuth</code> mô tả token trong header Authorization.

Có thể gắn scheme khác nhau cho các nhóm endpoint:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/partner")
@SecurityRequirement(name = "partnerApiKey")
class PartnerController {
    // Các operation dành cho đối tác
}
~~~

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/account")
@SecurityRequirement(name = "bearerAuth")
class AccountController {
    // Các operation dành cho người dùng đã đăng nhập
}
~~~

Đặt requirement ở cấp controller giúp áp dụng cho các operation thuộc controller đó. Có thể đặt ở cấp method nếu chỉ một operation cần cơ chế xác thực cụ thể. Hãy kiểm tra tài liệu sinh ra để xác nhận phạm vi đúng như dự kiến.

## 4. Các loại SecurityScheme thường dùng

OpenAPI hỗ trợ nhiều loại scheme. <code>type</code> quyết định các thuộc tính cần khai báo:

| Loại | Annotation | Thuộc tính thường dùng | Trường hợp |
|---|---|---|---|
| HTTP Basic | <code>type = HTTP</code>, <code>scheme = "basic"</code> | <code>scheme</code> | Username/password theo HTTP Basic |
| HTTP Bearer | <code>type = HTTP</code>, <code>scheme = "bearer"</code> | <code>scheme</code>, <code>bearerFormat</code> | Access token trong Authorization header |
| API key | <code>type = APIKEY</code> | <code>in</code>, <code>paramName</code> | Khóa tích hợp trong header, query hoặc cookie |
| OAuth2 | <code>type = OAUTH2</code> | <code>flows</code> | Access token được cấp theo OAuth2 flow |
| OpenID Connect | <code>type = OPENIDCONNECT</code> | <code>openIdConnectUrl</code> | Khám phá cấu hình OpenID Provider |

Không dùng <code>scheme = "bearer"</code> cho API key. Với API key, cần xác định vị trí truyền key bằng <code>in</code> và tên tham số bằng <code>paramName</code>.

### 4.1. HTTP Basic

Khai báo Basic authentication:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "basicAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "basic",
    description = "HTTP Basic authentication cho môi trường nội bộ"
)
class BasicSecurityDocumentation {
}
~~~

Client gửi thông tin đăng nhập trong header <code>Authorization</code> theo cơ chế Basic. Vì credential có thể được giải mã từ Base64, chỉ sử dụng qua HTTPS và theo chính sách bảo mật của hệ thống.

### 4.2. API key trong header

Ví dụ API key được truyền trong header:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "partnerKey",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-Partner-Key",
    description = "Khóa định danh ứng dụng đối tác"
)
class PartnerKeyDocumentation {
}
~~~

Swagger UI có thể tạo header <code>X-Partner-Key</code> khi gọi operation yêu cầu scheme này.

API key cũng có thể được đặt trong query hoặc cookie bằng <code>SecuritySchemeIn.QUERY</code> hoặc <code>SecuritySchemeIn.COOKIE</code>. Tuy nhiên, key trong query string dễ xuất hiện trong access log, browser history, proxy log và URL được chia sẻ. Với API mới, ưu tiên header qua HTTPS trừ khi hợp đồng có lý do cụ thể để dùng vị trí khác.

Khi đã mô tả API key bằng security scheme, không khai báo thêm cùng header như một tham số thông thường bằng <code>@RequestHeader</code>/<code>@Parameter</code> nếu không có lý do riêng; điều đó có thể khiến tài liệu hiển thị header xác thực hai lần.

Không khai báo API key thật trong annotation, ví dụ, source code hoặc OpenAPI document. Tên scheme và tên header là metadata; giá trị key phải được cấp và quản lý bên ngoài tài liệu.

## 5. Khai báo OAuth2 và scopes

OAuth2 scheme cần mô tả các flow mà client được phép sử dụng. Ví dụ ứng dụng web dùng Authorization Code flow:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth2/authorize",
            tokenUrl = "https://auth.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "orders:read",
                    description = "Đọc đơn hàng"
                ),
                @OAuthScope(
                    name = "orders:write",
                    description = "Tạo và cập nhật đơn hàng"
                )
            }
        )
    ),
    description = "OAuth2 Authorization Code flow"
)
class OAuthDocumentation {
}
~~~

Trong cấu hình:

- <code>authorizationUrl</code> là endpoint điều hướng người dùng đến máy chủ cấp quyền.
- <code>tokenUrl</code> là endpoint đổi authorization code lấy token.
- <code>scopes</code> liệt kê quyền mà client có thể yêu cầu.

Tên và URL phải khớp với cấu hình thực tế của Authorization Server. Các URL <code>example.com</code> trong đoạn mã chỉ là địa chỉ minh họa, cần thay bằng endpoint của hệ thống.

Gắn OAuth2 requirement với scope cần thiết:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
@SecurityRequirement(
    name = "ordersOAuth",
    scopes = {"orders:read"}
)
List<OrderResponse> listOrders() {
    // ...
    return List.of();
}
~~~

Với operation ghi dữ liệu, có thể yêu cầu <code>orders:write</code>. Scope trong OpenAPI mô tả quyền cần có; server vẫn phải kiểm tra claim/scope trong access token trước khi xử lý request.

Không khai báo OAuth2 flow chỉ vì muốn có nút Authorize. Chọn flow dựa trên loại client, khả năng của Identity Provider và hướng dẫn bảo mật hiện hành. Với ứng dụng trình duyệt hoặc ứng dụng di động công khai, Authorization Code kết hợp PKCE thường là lựa chọn phù hợp; không nhúng client secret vào mã client công khai.

## 6. Khai báo OpenID Connect

Nếu hệ thống sử dụng OpenID Connect Discovery, có thể đăng ký URL discovery:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "openId",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://identity.example.com/.well-known/openid-configuration",
    description = "OpenID Connect provider"
)
class OpenIdDocumentation {
}
~~~

<code>openIdConnectUrl</code> trỏ đến tài liệu discovery của OpenID Provider. Client có thể dùng metadata ở đó để tìm endpoint và thông tin hỗ trợ. URL phải có thể truy cập từ môi trường client sử dụng.

OpenID Connect là lớp định danh xây dựng trên OAuth2. Không nhầm OpenID Connect với một HTTP scheme tùy ý hoặc coi URL discovery là endpoint nhận request nghiệp vụ.

## 7. Áp dụng security toàn cục và theo operation

Có thể khai báo security requirement ở cấp toàn bộ API bằng <code>@OpenAPIDefinition</code>:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
class OpenApiDefinitionConfiguration {
}
~~~

Khi khai báo ở cấp root, các operation kế thừa yêu cầu bảo mật toàn cục trừ khi operation có cấu hình security riêng. Nếu một endpoint công khai không cần xác thực, đặc tả của operation đó cần có <code>security: []</code> để ghi đè yêu cầu root. Hãy kiểm tra output OpenAPI để xác nhận operation công khai thực sự không kế thừa security requirement.

Có thể đặt requirement ở cấp controller hoặc method để giới hạn phạm vi:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
@SecurityRequirement(name = "bearerAuth")
class AdminController {

    @GetMapping("/reports")
    List<String> reports() {
        return List.of();
    }
}
~~~

Nếu cùng một controller có cả endpoint công khai và endpoint bảo vệ, cân nhắc đặt requirement ở method để tránh vô tình mô tả sai phạm vi. Cấu hình security trong OpenAPI phải phản ánh đúng policy thực tế của từng operation.

## 8. Hiểu đúng ngữ nghĩa AND và OR của nhiều security requirement

OpenAPI cho phép nhiều phương án xác thực:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Hai object trong mảng là các lựa chọn **OR**: client có thể xác thực bằng Bearer token hoặc API key.

Nếu một request bắt buộc phải cung cấp đồng thời hai scheme, chúng phải nằm trong cùng một Security Requirement Object:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

Các scheme trong cùng một object có nghĩa **AND**: request cần cả Bearer token và API key. Không nhầm hai object riêng trong mảng với hai scheme cùng nằm trong một object.

Khi lặp nhiều annotation <code>@SecurityRequirement</code>, mỗi requirement thường trở thành một lựa chọn riêng trong mảng <code>security</code>, tức logic OR. Nếu cần AND, hãy kiểm tra output và dùng <code>OpenApiCustomizer</code> để tạo một Security Requirement Object chứa đồng thời các scheme trong cùng object.

## 9. Kết hợp với Spring Security

Đăng ký <code>@SecurityScheme</code> không tự cấu hình Spring Security. Ví dụ, khai báo Bearer scheme không tạo JWT decoder, không xác thực chữ ký và không bảo vệ endpoint.

Ở runtime, ứng dụng cần cấu hình resource server hoặc filter tương ứng. Với Spring Security OAuth2 Resource Server, cấu hình cơ bản có thể trông như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Đoạn cấu hình trên minh họa việc yêu cầu xác thực cho endpoint ngoài <code>/public/**</code> và dùng JWT resource server. Dự án cần dependency Resource Server, cấu hình issuer hoặc public key phù hợp và chính sách phân quyền theo yêu cầu. Nếu API dùng API key, Basic hoặc cơ chế riêng, cần filter/provider tương ứng; OpenAPI annotation không thay thế chúng.

Khi chia sẻ tài liệu, hãy đối chiếu ba phần:

1. Security scheme trong OpenAPI mô tả client phải gửi credential như thế nào.
2. Security requirement chỉ ra operation nào cần credential nào.
3. Spring Security thực thi xác thực và phân quyền trên request thật.

## 10. Kiểm tra tài liệu OpenAPI được sinh ra

Sau khi khởi động ứng dụng, mở:

~~~text
http://localhost:8080/v3/api-docs
~~~

Kiểm tra các mục:

1. <code>components.securitySchemes</code> có scheme với đúng tên.
2. <code>type</code>, <code>scheme</code>, <code>in</code>, <code>name</code>, OAuth2 flow hoặc OpenID URL phù hợp với cơ chế đang dùng.
3. <code>security</code> ở cấp root hoặc operation tham chiếu đúng tên component.
4. Operation công khai có security rỗng nếu cần ghi đè security toàn cục.
5. OAuth2 scope trong requirement tồn tại trong danh sách scope đã khai báo.
6. Các nhóm tài liệu <code>GroupedOpenApi</code> đều có scheme và requirement cần thiết trong tài liệu tương ứng.

Một phần JSON/YAML mong đợi với Bearer:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

paths:
  /api/profile:
    get:
      security:
        - bearerAuth: []
      responses:
        "200":
          description: OK
~~~

Sau đó mở Swagger UI, kiểm tra nút Authorize, nhập token thử nghiệm và gọi một endpoint được bảo vệ. Xác minh cả hai trường hợp token hợp lệ và token thiếu/không hợp lệ. Nếu UI gửi đúng header nhưng server vẫn trả <code>401</code>, kiểm tra cấu hình resource server, issuer, chữ ký và thời hạn token. Nếu trả <code>403</code>, kiểm tra quyền hoặc scope.

## 11. Lỗi thường gặp

**Chỉ khai báo <code>@SecurityScheme</code> rồi mong endpoint được bảo vệ.** Scheme chỉ định nghĩa component. Cần thêm <code>@SecurityRequirement</code> hoặc cấu hình security ở root.

**Tên scheme không khớp.** Requirement phải tham chiếu đúng tên <code>name</code> trong <code>@SecurityScheme</code>. Kiểm tra cả chữ hoa/thường và tên component sinh ra.

**Dùng sai type.** Bearer/Basic dùng <code>type = HTTP</code>; API key dùng <code>type = APIKEY</code>; OAuth2 dùng <code>type = OAUTH2</code>; OpenID Connect dùng <code>type = OPENIDCONNECT</code>.

**Khai báo API key thiếu vị trí hoặc tên tham số.** API key cần <code>in</code> và <code>paramName</code>; nếu thiếu, tài liệu không mô tả đầy đủ nơi client gửi key.

**Dùng bearerFormat như cơ chế xác thực.** <code>bearerFormat</code> chỉ là gợi ý cho người đọc và công cụ, không xác minh JWT.

**Khai báo OAuth2 flow hoặc scope sai.** URL authorization/token và scope phải khớp Identity Provider cùng policy của server.

**Bảo vệ UI nhưng quên tài liệu JSON.** Nếu <code>/swagger-ui/**</code> được bảo vệ nhưng <code>/v3/api-docs</code> vẫn công khai, người dùng vẫn có thể tải đặc tả trực tiếp.

**Nhầm OR với AND.** Nhiều Security Requirement Object trong mảng biểu thị các lựa chọn thay thế. Muốn yêu cầu đồng thời nhiều scheme, đặt chúng trong cùng một object.

**OpenAPI và Spring Security không thống nhất.** Swagger UI có thể gửi token theo tài liệu nhưng backend vẫn cho phép hoặc từ chối khác dự kiến. Kiểm tra cả đặc tả lẫn filter chain thực tế.

## 12. Danh sách rà soát trước khi công bố

- [ ] Mỗi scheme có tên duy nhất, mô tả rõ và đúng <code>type</code>.
- [ ] HTTP scheme có <code>scheme</code> phù hợp; API key có <code>in</code> và <code>paramName</code>.
- [ ] OAuth2 flow, URL và scopes khớp Identity Provider.
- [ ] OpenID Connect dùng URL discovery hợp lệ.
- [ ] <code>@SecurityRequirement</code> tham chiếu đúng tên scheme.
- [ ] Phạm vi global, controller và method phản ánh đúng policy của API.
- [ ] Đã kiểm tra logic AND/OR khi có nhiều scheme.
- [ ] Endpoint công khai được mô tả không yêu cầu security nếu cần.
- [ ] Spring Security thực sự xác thực và phân quyền ở runtime.
- [ ] Swagger UI gửi đúng credential và <code>/v3/api-docs</code> không bị lộ ngoài dự kiến.

## Tài liệu tham khảo

- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object): các loại HTTP, API key, OAuth2 và OpenID Connect.
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object): cách áp dụng một hay nhiều cơ chế xác thực và ngữ nghĩa AND/OR.
- [Swagger Core – SecurityScheme annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/security/SecurityScheme.html): thuộc tính của <code>@SecurityScheme</code>.
- [Swagger Core – SecurityRequirement annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html): tham chiếu security scheme trong annotation.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác thực Bearer JWT ở runtime.
- [springdoc-openapi](https://springdoc.org/): tích hợp annotation OpenAPI với ứng dụng Spring Boot.
