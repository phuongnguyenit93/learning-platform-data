# Ghi đè yêu cầu toàn cục cho endpoint công khai

Trong nhiều ứng dụng Spring Boot, phần lớn API yêu cầu xác thực bằng JWT, API key hoặc OAuth 2.0. Vì vậy, tài liệu OpenAPI thường khai báo một yêu cầu bảo mật ở cấp toàn bộ document. Tuy nhiên, một số endpoint như đăng nhập, đăng ký, kiểm tra trạng thái dịch vụ hoặc lấy danh mục công khai không yêu cầu thông tin xác thực.

OpenAPI cho phép từng operation ghi đè yêu cầu bảo mật toàn cục. Với `springdoc-openapi`, có thể dùng annotation `@SecurityRequirements` rỗng trên method để công bố operation không có security requirement. Cần hiểu rõ sự khác nhau giữa metadata bảo mật trong tài liệu và rule xác thực/phân quyền thật của Spring Security: annotation chỉ điều khiển OpenAPI, còn cấu hình bảo mật runtime quyết định request có được phép đi qua hay không.

## 1. Yêu cầu bảo mật toàn cục hoạt động như thế nào?

OpenAPI có thể khai báo `security` ở cấp root để áp dụng cho tất cả operation. Ví dụ, một API dùng bearer JWT:

```yaml
openapi: 3.0.3
security:
  - bearerAuth: []
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

`components.securitySchemes` định nghĩa cơ chế xác thực có tên `bearerAuth`. `security` ở cấp root yêu cầu các operation dùng cơ chế đó, trừ khi operation có khai báo `security` riêng để ghi đè.

Nếu operation không có trường `security`, nó kế thừa yêu cầu ở cấp root. Vì vậy, việc chỉ bỏ annotation `@SecurityRequirement` khỏi một method không có nghĩa method đó tự động trở thành công khai khi document đang có security toàn cục.

## 2. Phân biệt `SecurityScheme` và `SecurityRequirement`

Hai thành phần này có nhiệm vụ khác nhau:

| Thành phần | Vị trí trong OpenAPI | Vai trò |
| --- | --- | --- |
| Security scheme | `components.securitySchemes` | Mô tả cách client cung cấp thông tin xác thực, ví dụ bearer token, API key hoặc OAuth 2.0. |
| Security requirement | `security` ở cấp root hoặc operation | Chỉ định operation nào yêu cầu một hay nhiều security scheme đã định nghĩa. |

Chỉ khai báo `bearerAuth` trong `components.securitySchemes` chưa bắt buộc operation dùng bearer token. Cần có security requirement ở cấp root hoặc operation mới thể hiện yêu cầu đó trong hợp đồng.

Ngược lại, một security requirement phải tham chiếu đúng tên scheme đã khai báo. Nếu document dùng `bearerAuth` nhưng component chỉ có `jwtAuth`, đặc tả không nhất quán và Swagger UI có thể không xử lý xác thực như mong muốn.

## 3. Khai báo security toàn cục trong springdoc

Có thể định nghĩa scheme và requirement bằng một bean `OpenAPI`:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Store API")
                .version("1.0.0"))
            .components(new Components()
                .addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")))
            .addSecurityItem(new SecurityRequirement()
                .addList("bearerAuth"));
    }
}
```

Trong ví dụ:

- `addSecuritySchemes("bearerAuth", ...)` đăng ký scheme trong `components.securitySchemes`.
- `type(HTTP)` và `scheme("bearer")` mô tả HTTP Bearer Authentication.
- `bearerFormat("JWT")` cung cấp gợi ý định dạng token cho công cụ tài liệu.
- `addSecurityItem(...)` thêm yêu cầu bảo mật ở cấp root, áp dụng mặc định cho các operation.

Có thể khai báo scheme bằng annotation `@SecurityScheme` và security toàn cục bằng `@OpenAPIDefinition(security = ...)`. Chọn một cách cấu hình nhất quán để tránh khai báo trùng hoặc tên scheme không khớp. Springdoc cũng hỗ trợ định nghĩa security scheme thông qua OpenAPI bean trong tài liệu FAQ chính thức.

## 4. Ghi đè security toàn cục cho một endpoint công khai

Đặt `@SecurityRequirements` rỗng trên method cần công khai:

```java
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PublicController {

    @GetMapping("/api/public/status")
    @SecurityRequirements
    PublicStatus getStatus() {
        return new PublicStatus("UP");
    }
}
```

`@SecurityRequirements` là annotation chứa danh sách các `@SecurityRequirement`. Khi đặt annotation này rỗng ở method, springdoc có thể ghi nhận rõ rằng operation có danh sách security requirement rỗng, từ đó ghi đè yêu cầu ở cấp root.

OpenAPI được sinh ra có dạng:

```yaml
security:
  - bearerAuth: []
paths:
  /api/public/status:
    get:
      responses:
        '200':
          description: Trạng thái dịch vụ
      security: []
  /api/private/profile:
    get:
      responses:
        '200':
          description: Hồ sơ người dùng
```

Operation `/api/public/status` có `security: []`, nghĩa là nó không kế thừa yêu cầu bảo mật ở cấp root. Operation `/api/private/profile` không khai báo `security` riêng nên tiếp tục kế thừa `bearerAuth`.

Hãy dùng annotation ở method cụ thể cần công khai. Nếu đặt `@SecurityRequirements` ở cấp controller, phạm vi ảnh hưởng có thể bao gồm tất cả operation trong controller đó.

## 5. Phân biệt `security: []` với `security: [{}]`

Đây là khác biệt quan trọng trong OpenAPI:

| Giá trị ở operation | Ý nghĩa |
| --- | --- |
| Không có trường `security` | Kế thừa yêu cầu bảo mật ở cấp root. |
| `security: []` | Ghi đè và loại bỏ yêu cầu bảo mật toàn cục cho operation đó. |
| `security: [{}]` | Cho phép truy cập ẩn danh như một lựa chọn bảo mật; có thể kết hợp với lựa chọn xác thực khác. |
| `security: [{ bearerAuth: [] }]` | Yêu cầu bearer token. |

Ví dụ `security: [{}]` cùng một lựa chọn bearer:

```yaml
security:
  - {}
  - bearerAuth: []
```

Danh sách này biểu thị client có thể gọi operation ẩn danh hoặc dùng bearer token. Đây là trường hợp xác thực tùy chọn, ví dụ endpoint có thể trả dữ liệu cá nhân hóa nếu client gửi token nhưng vẫn cho phép khách chưa đăng nhập xem nội dung cơ bản.

Với endpoint công khai hoàn toàn, không cần xác thực tùy chọn, hãy dùng `security: []`. Không nhầm mảng rỗng `[]` với object rỗng `{}`.

## 6. Vì sao nên dùng `@SecurityRequirements` thay vì chỉ ghi `@Operation(security = {})`?

`@Operation.security` là một mảng annotation có giá trị mặc định rỗng. Trong một số phiên bản hoặc đường xử lý annotation, mảng rỗng có thể được hiểu là không khai báo metadata security, khiến operation tiếp tục kế thừa security toàn cục.

`@SecurityRequirements` là một annotation riêng. Sự hiện diện của nó thể hiện rõ ý định ghi đè bằng danh sách requirement rỗng. Đây là cách springdoc đã hỗ trợ để loại bỏ security toàn cục cho một operation. Vì vậy, dùng:

```java
@GetMapping("/api/public/status")
@SecurityRequirements
PublicStatus getStatus() {
    return new PublicStatus("UP");
}
```

Sau đó kiểm tra `/v3/api-docs` để xác nhận operation thực sự có `security: []`. Không chỉ nhìn annotation trong source rồi giả định kết quả tài liệu đã đúng. Nếu dự án dùng phiên bản springdoc hoặc swagger-annotations cũ, hãy kiểm tra khả năng hỗ trợ của phiên bản đó trước khi áp dụng trên diện rộng.

## 7. Quy tắc AND và OR trong security requirement

OpenAPI biểu diễn nhiều cơ chế xác thực bằng danh sách security requirement object:

- Nhiều scheme nằm trong cùng một object nghĩa là client phải thỏa tất cả scheme đó (AND).
- Nhiều object trong mảng nghĩa là client có thể thỏa một trong các lựa chọn (OR).

Ví dụ yêu cầu đồng thời bearer token và API key:

```yaml
security:
  - bearerAuth: []
    clientKey: []
```

Ví dụ cho phép bearer token hoặc API key:

```yaml
security:
  - bearerAuth: []
  - clientKey: []
```

Khi ghi đè global security, hãy kiểm tra toàn bộ danh sách requirement đang được dùng. Nếu operation cần một cơ chế xác thực khác, khai báo requirement mới ở operation thay vì dùng danh sách rỗng. Nếu operation công khai hoàn toàn, dùng `@SecurityRequirements` rỗng.

## 8. Ghi đè security trong cấu hình Spring Security runtime

`@SecurityRequirements` chỉ ảnh hưởng tài liệu OpenAPI. Để request thật không cần đăng nhập, phải cấu hình Spring Security cho phép truy cập endpoint đó.

Ví dụ với Spring Security:

```java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .build();
    }
}
```

`permitAll()` cho phép request đến các path công khai đi qua bước authorization mà không cần người dùng đã xác thực. Các endpoint còn lại vẫn yêu cầu authentication theo cấu hình này.

Hai thay đổi cần được thực hiện và kiểm tra riêng:

1. **OpenAPI:** `@SecurityRequirements` làm operation có `security: []`, giúp Swagger UI không đánh dấu operation đó là bắt buộc xác thực theo global requirement.
2. **Runtime:** `requestMatchers(...).permitAll()` cho phép request thật truy cập endpoint mà không cần đăng nhập.

Nếu chỉ làm bước 1, Swagger UI có thể gửi request không có token nhưng Spring Security vẫn trả `401` hoặc `403`. Nếu chỉ làm bước 2, API gọi được công khai nhưng tài liệu vẫn thể hiện bearer token là bắt buộc.

Ngoài authorization rule, hãy kiểm tra custom authentication filter. Một filter tự viết có thể từ chối request thiếu token trước khi request đến bước `permitAll()`. Khi đó filter cần bỏ qua các path công khai hoặc chỉ xác thực khi có credential theo đúng thiết kế. `permitAll()` không tự bỏ qua mọi filter trong security chain.

## 9. Ví dụ hoàn chỉnh: API công khai và API riêng tư

Một controller có thể chứa cả hai loại endpoint:

```java
@RestController
@RequestMapping("/api")
class AccountController {

    @GetMapping("/public/health")
    @SecurityRequirements
    HealthResponse health() {
        return new HealthResponse("UP");
    }

    @GetMapping("/account/profile")
    ProfileResponse profile(@AuthenticationPrincipal Jwt jwt) {
        return accountService.getProfile(jwt.getSubject());
    }
}
```

Tài liệu OpenAPI có thể công bố:

```yaml
security:
  - bearerAuth: []
paths:
  /api/public/health:
    get:
      security: []
  /api/account/profile:
    get:
      responses:
        '200':
          description: Hồ sơ tài khoản
```

Endpoint health không yêu cầu bearer token theo hợp đồng; endpoint profile kế thừa yêu cầu toàn cục. Spring Security cũng phải cho phép `/api/public/health` và bảo vệ `/api/account/profile` tương ứng.

Nếu một method cần truy cập ẩn danh nhưng vẫn có thể nhận principal tùy chọn để cá nhân hóa response, hãy thiết kế tham số principal nullable hoặc tùy chọn và kiểm tra rõ hành vi khi không có người dùng đăng nhập. Không giả định `@AuthenticationPrincipal` luôn có giá trị ở endpoint công khai.

## 10. Kiểm tra kết quả trong OpenAPI và Swagger UI

Sau khi thêm `@SecurityRequirements`, hãy kiểm tra tài liệu được sinh ra:

1. Mở `/v3/api-docs` hoặc endpoint tài liệu của group tương ứng.
2. Xác nhận root `security` vẫn chứa requirement toàn cục như `bearerAuth`.
3. Tìm operation công khai và xác nhận trường `security` tồn tại với mảng rỗng `[]`.
4. Tìm operation riêng tư và xác nhận nó không có `security` riêng, nên kế thừa root requirement.
5. Mở Swagger UI, xác nhận operation công khai không hiển thị trạng thái bắt buộc bearer token, còn operation riêng tư vẫn có yêu cầu bảo mật.
6. Dùng **Try it out** không nhập token để gọi endpoint công khai.
7. Gọi endpoint riêng tư không token và xác nhận server từ chối theo chính sách runtime.
8. Gọi endpoint riêng tư với token hợp lệ và xác nhận request được xử lý.

Nếu ứng dụng có `GroupedOpenApi`, hãy kiểm tra document của từng group chứa endpoint. Mỗi group có thể có customizer riêng hoặc phạm vi operation khác nhau; kết quả ở `/v3/api-docs` mặc định chưa chứng minh các group document đều giống nhau.

## 11. Kiểm thử tài liệu và runtime

Có thể dùng MockMvc để xác nhận endpoint công khai có security array rỗng trong OpenAPI:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PublicSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicOperationOverridesGlobalSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.security[0].bearerAuth").exists())
            .andExpect(jsonPath("$['paths']['/api/public/health']['get']['security']").isArray())
            .andExpect(jsonPath("$['paths']['/api/public/health']['get']['security']").isEmpty());
    }

    @Test
    void publicEndpointCanBeCalledWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/api/public/health"))
            .andExpect(status().isOk());
    }
}
```

Test đầu xác nhận hợp đồng tài liệu. Test thứ hai xác nhận rule runtime. Nên bổ sung kiểm thử cho endpoint riêng tư để chứng minh nó vẫn yêu cầu xác thực; status chính xác có thể là `401` hoặc `403` tùy authentication entry point và cấu hình ứng dụng.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Endpoint công khai vẫn có biểu tượng khóa trong Swagger UI | Operation không có `security: []` và tiếp tục kế thừa root security | Đặt `@SecurityRequirements` trên method và kiểm tra `/v3/api-docs`. |
| `@Operation(security = {})` không ghi đè security toàn cục | Mảng rỗng bị xem như không có metadata trong phiên bản đang dùng | Dùng annotation container rỗng `@SecurityRequirements`. |
| Tài liệu bỏ khóa nhưng request thật vẫn trả `401` | Chỉ thay đổi OpenAPI, chưa cấu hình Spring Security | Thêm rule `permitAll()` cho đúng path và kiểm tra authentication filter. |
| API truy cập được nhưng Swagger UI vẫn yêu cầu token | Runtime đã mở nhưng OpenAPI vẫn kế thừa root security | Bổ sung `@SecurityRequirements` và xác minh operation security. |
| Tất cả endpoint trong controller trở thành công khai | Đặt annotation rỗng ở cấp class thay vì method | Chuyển annotation xuống đúng method cần công khai. |
| Scheme biến mất khỏi Authorize | Xóa `components.securitySchemes` thay vì chỉ ghi đè requirement | Giữ scheme toàn cục; chỉ đặt `security: []` ở operation công khai. |
| Tên scheme không khớp | Requirement tham chiếu tên khác với component | Đồng bộ chính xác tên `bearerAuth`, `apiKey` hoặc scheme thực tế. |
| Endpoint vẫn bị custom filter chặn | Filter từ chối request thiếu token trước bước authorization | Cập nhật matcher/logic bỏ qua path công khai trong filter. |
| Một group vẫn hiển thị security khác group mặc định | Customizer hoặc OpenAPI bean của group thay đổi document riêng | Kiểm tra URL `/v3/api-docs/{group}` và cấu hình customizer của group. |

## 13. Nguyên tắc áp dụng

- Định nghĩa `SecurityScheme` một lần và dùng tên nhất quán trong các security requirement.
- Dùng root `security` cho chính sách mặc định của toàn document.
- Dùng `@SecurityRequirements` rỗng trên method để ghi đè root requirement cho endpoint công khai.
- Phân biệt `security: []` (loại bỏ yêu cầu toàn cục) với `security: [{}]` (cho phép lựa chọn ẩn danh).
- Không xóa security scheme nếu chỉ muốn một operation công khai.
- Cấu hình `permitAll()` hoặc rule tương đương trong Spring Security cho endpoint runtime.
- Kiểm tra custom authentication filter, vì filter có thể chặn request trước authorization rule.
- Xác minh cả OpenAPI JSON, Swagger UI và request HTTP thật.
- Kiểm tra riêng từng group document nếu ứng dụng có nhiều `GroupedOpenApi`.

Ghi đè security toàn cục là thao tác ở cấp operation trong hợp đồng OpenAPI. `@SecurityRequirements` rỗng giúp springdoc công bố rõ operation không kế thừa security requirement của document; Spring Security vẫn cần một rule runtime cho phép endpoint được gọi ẩn danh. Khi kiểm tra cả hai phía, tài liệu sẽ mô tả đúng endpoint công khai và hành vi bảo vệ của ứng dụng vẫn được duy trì cho các API riêng tư.

## Tài liệu tham khảo

- [OpenAPI Specification 3.0 – Security Requirement và Operation Object](https://spec.openapis.org/oas/v3.0.3)
- [Springdoc OpenAPI FAQ – định nghĩa SecurityScheme toàn cục](https://springdoc.org/faq.html)
- [Swagger Core – `@SecurityRequirement` và `@SecurityRequirements`](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirements.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Springdoc issue #259 – ghi đè security toàn cục bằng `@SecurityRequirements`](https://github.com/springdoc/springdoc-openapi/issues/259)
