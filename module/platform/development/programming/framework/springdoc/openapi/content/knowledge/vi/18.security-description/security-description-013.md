# Mô tả 401, 403 và các header liên quan đúng hành vi thực tế

Khi một API được bảo vệ, client cần biết vì sao request bị từ chối và phải làm gì tiếp theo. Hai status thường gặp là **401 Unauthorized** và **403 Forbidden**. Chúng có ý nghĩa HTTP khác nhau và thường đi cùng các header xác thực như request header Authorization và response header WWW-Authenticate.

Trong OpenAPI, Authorization được mô tả bằng Security Scheme và Security Requirement. WWW-Authenticate được mô tả như một response header của phản hồi 401; trong một số luồng Bearer Token, header này cũng có thể xuất hiện ở 403 khi token hợp lệ nhưng thiếu scope. Springdoc-openapi chỉ công bố hợp đồng. Spring Security, resource server hoặc gateway phải thực sự trả status, header và body tương ứng.

## 1. Phân biệt 401 và 403

Hai status này không thể dùng thay thế tùy ý:

| Status | Ý nghĩa HTTP | Trường hợp thường gặp |
|---|---|---|
| **401 Unauthorized** | Request chưa có thông tin xác thực hợp lệ cho tài nguyên. Server từ chối vì client chưa được xác thực. | Thiếu Bearer token, token hết hạn, token sai chữ ký hoặc không hợp lệ. |
| **403 Forbidden** | Server hiểu request nhưng từ chối thực hiện. | Người dùng đã đăng nhập nhưng không có role, authority hoặc quyền truy cập cần thiết. |

Một cách phân biệt thực tế:

- **401**: client cần cung cấp hoặc làm mới thông tin xác thực.
- **403**: danh tính đã được xác định, nhưng danh tính đó không có quyền thực hiện hành động này; việc gửi lại cùng credential thường không giải quyết được vấn đề.

Không nên suy luận rằng mọi 403 đều có nghĩa người dùng đã đăng nhập. Server có thể dùng 403 để từ chối theo policy, IP, tenant hoặc điều kiện nghiệp vụ khác. Tương tự, một API có thể cố ý trả 404 thay vì 403 để không tiết lộ sự tồn tại của tài nguyên. Hãy mô tả hành vi thực tế và chính sách bảo mật của ứng dụng.

### 1.1. 401 phải có authentication challenge

Theo ngữ nghĩa HTTP, phản hồi 401 phải chứa ít nhất một challenge trong header WWW-Authenticate để chỉ ra phương thức xác thực mà tài nguyên yêu cầu. Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="documents-api"
Content-Type: application/json

{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Cần xác thực để truy cập tài nguyên"
}
~~~

Challenge phụ thuộc cơ chế xác thực. Với HTTP Basic có thể là Basic realm="api"; với OAuth 2.0 Bearer Token thường là Bearer realm="api". Không mô tả cứng một challenge Bearer nếu endpoint thực tế dùng Basic, Mutual TLS hoặc cơ chế khác.

### 1.2. 403 không bắt buộc có WWW-Authenticate

Một phản hồi 403 thông thường chỉ cần mô tả rằng client không có quyền:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền thực hiện thao tác này"
}
~~~

Không tự động thêm WWW-Authenticate vào mọi response 403. Tuy nhiên, với Bearer Token theo RFC 6750, trường hợp token có hiệu lực nhưng thiếu scope cần thiết có thể trả 403 cùng challenge:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="documents:write"
Content-Type: application/json

{
  "code": "INSUFFICIENT_SCOPE",
  "message": "Token không có scope documents:write"
}
~~~

Đây là một trường hợp cụ thể của Bearer authentication. Nếu ứng dụng chỉ dùng role-based authorization và không công bố scope trong challenge, response 403 không cần header này.

## 2. Các header liên quan đến xác thực

| Header | Hướng | Vai trò | Cách mô tả |
|---|---|---|---|
| Authorization | Request | Client gửi credential, ví dụ Bearer access token. | Khai báo Security Scheme, không khai báo như query/header parameter thông thường. |
| WWW-Authenticate | Response | Server gửi authentication challenge trong phản hồi 401; có thể mô tả lỗi Bearer ở 403. | Khai báo trong headers của response tương ứng. |
| Access-Control-Allow-Headers | Response preflight | Cho biết browser được phép gửi request header nào qua CORS. | Cấu hình CORS ở server/gateway; thường không phải response header nghiệp vụ của từng operation. |
| Access-Control-Expose-Headers | Response CORS | Cho phép JavaScript đọc một số response header không nằm trong CORS-safelisted response headers. | Cấu hình CORS; cần expose WWW-Authenticate nếu browser client phải đọc header này. |
| X-Request-ID | Response (quy ước ứng dụng) | Cung cấp mã để tra cứu log hoặc hỗ trợ. | Có thể mô tả như response header nếu server thực sự trả. |

HTTP header name không phân biệt chữ hoa/chữ thường. Trong OpenAPI, giữ một cách viết nhất quán để tài liệu dễ đọc.

### 2.1. Authorization là security scheme, không phải parameter thường

Không khai báo Authorization bằng Parameter Object như sau:

~~~yaml
parameters:
  - name: Authorization
    in: header
    required: true
    schema:
      type: string
~~~

OpenAPI quy định Authorization được mô tả qua security scheme. Với Bearer JWT, khai báo scheme kiểu HTTP:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Sau đó gắn security requirement vào operation hoặc toàn tài liệu:

~~~yaml
security:
  - bearerAuth: []
~~~

Swagger UI sẽ hiển thị cơ chế Authorize tương ứng và gửi credential theo scheme. Việc mô tả security scheme không tự bảo vệ endpoint; cấu hình Spring Security hoặc gateway vẫn phải thực thi xác thực.

### 2.2. WWW-Authenticate là response header

WWW-Authenticate thuộc về phản hồi HTTP. Không đặt nó trong request parameters. Trong OpenAPI, nó nằm dưới response cụ thể:

~~~yaml
responses:
  '401':
    description: Chưa xác thực hoặc credential không hợp lệ
    headers:
      WWW-Authenticate:
        description: Challenge cho cơ chế xác thực được endpoint hỗ trợ
        schema:
          type: string
        example: 'Bearer realm="documents-api"'
~~~

Với một response 401, server có thể gửi nhiều challenge cho nhiều scheme được hỗ trợ. OpenAPI Header Object thường mô tả giá trị header dưới dạng string. Ví dụ và description nên phản ánh các challenge server thực sự phát ra; không giả định client luôn nhận đúng một chuỗi Bearer cố định.

## 3. Mô tả Bearer authentication trong Springdoc

Có thể đăng ký security scheme bằng OpenAPI model trong một bean:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiSecurityConfiguration {

    @Bean
    OpenAPI apiSecurity() {
        return new OpenAPI()
                .info(new Info()
                        .title("Documents API")
                        .version("1.0.0"))
                .components(new Components()
                        .addSecuritySchemes(
                                "bearerAuth",
                                new SecurityScheme()
                                        .type(SecurityScheme.Type.HTTP)
                                        .scheme("bearer")
                                        .bearerFormat("JWT")
                        ))
                .addSecurityItem(
                        new SecurityRequirement().addList("bearerAuth")
                );
    }
}
~~~

Trong ví dụ, scheme có tên bearerAuth, dùng HTTP Bearer và token có định dạng JWT. bearerFormat chỉ là thông tin gợi ý cho tài liệu; OpenAPI không xác minh chữ ký hay claim của JWT.

Nếu ứng dụng đã có OpenAPI bean để khai báo title, server, schema hoặc response component, hãy thêm security scheme và requirement vào bean đó. Không tạo nhiều bean OpenAPI độc lập với cấu hình chồng lấn.

### 3.1. Chỉ bảo vệ operation cần xác thực

Có thể đặt security requirement ở cấp controller hoặc operation bằng annotation:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@SecurityRequirement(name = "bearerAuth")
class DocumentController {

    @GetMapping("/api/documents")
    List<DocumentResponse> list() {
        return documentService.findAll();
    }
}
~~~

Nếu mọi endpoint đều được bảo vệ, requirement cấp tài liệu trong OpenAPI bean là cách ngắn gọn. Nếu chỉ một số operation được bảo vệ, đặt requirement ở cấp operation/controller phù hợp.

Khi security requirement được đặt toàn cục nhưng có operation công khai, OpenAPI operation đó cần ghi đè bằng security rỗng (security: []). Hãy kiểm tra JSON cuối cùng để chắc rằng Swagger UI không yêu cầu token cho endpoint công khai.

## 4. Khai báo 401 và WWW-Authenticate bằng annotation

Một response 401 nên có description rõ ràng, body lỗi nếu ứng dụng trả body và header challenge:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

@RestController
class DocumentController {

    @GetMapping("/api/documents/{id}")
    @Operation(
            summary = "Lấy tài liệu theo mã",
            security = @SecurityRequirement(name = "bearerAuth")
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy tài liệu",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = DocumentResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "401",
            description = "Thiếu Bearer token hoặc token không hợp lệ",
            headers = @Header(
                name = "WWW-Authenticate",
                description = "Bearer authentication challenge",
                schema = @Schema(
                    type = "string",
                    example = "Bearer realm=\"documents-api\""
                )
            ),
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    DocumentResponse findById(@PathVariable UUID id) {
        return documentService.findById(id);
    }
}
~~~

Các annotation có vai trò riêng:

- SecurityRequirement mô tả operation cần scheme bearerAuth.
- ApiResponse với responseCode 401 mô tả phản hồi chưa xác thực.
- Header đặt WWW-Authenticate ở response, không phải request parameter.
- Content và Schema mô tả body lỗi nếu runtime trả JSON.

Nếu endpoint trả 401 không có body, bỏ content khỏi response. Không mô tả ApiError chỉ vì ứng dụng có một error DTO khác; schema phải khớp body thực tế.

## 5. Mô tả 403 theo quyền truy cập

Response 403 thường mô tả lý do từ chối quyền. Với role-based authorization thông thường, body có thể chứa mã lỗi và thông tin hỗ trợ:

~~~java
@ApiResponse(
    responseCode = "403",
    description = "Đã xác thực nhưng không có quyền truy cập tài liệu",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Không gắn WWW-Authenticate vào response này nếu server không phát challenge. Nếu ứng dụng dùng OAuth2 Bearer Token và trả insufficient_scope, có thể mô tả header:

~~~java
@ApiResponse(
    responseCode = "403",
    description = "Token hợp lệ nhưng thiếu scope cần thiết",
    headers = @Header(
        name = "WWW-Authenticate",
        description = "Bearer challenge báo thiếu scope",
        schema = @Schema(
            type = "string",
            example = "Bearer error=\"insufficient_scope\", scope=\"documents:write\""
        )
    ),
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Nếu một API có nhiều loại 403 khác nhau, hãy mô tả đúng từng response hoặc tách operation/response component theo ngữ nghĩa. Không dùng một ví dụ insufficient_scope cho tất cả trường hợp thiếu quyền.

## 6. Bearer Token error theo RFC 6750

Với OAuth 2.0 Bearer Token, các lỗi phổ biến có cách biểu diễn đặc trưng:

| Tình huống | Status thường dùng | Challenge |
|---|---:|---|
| Không gửi token cho resource yêu cầu xác thực | 401 | Bearer realm="api" |
| Access token hết hạn, sai hoặc không hợp lệ | 401 | Bearer error="invalid_token" |
| Request dùng token sai cách hoặc có nhiều phương thức gửi token | 400 trong trường hợp invalid_request | Bearer error="invalid_request" |
| Token hợp lệ nhưng không đủ scope | 403 | Bearer error="insufficient_scope"; có thể kèm scope cần thiết. |

Các giá trị error và challenge cần tuân thủ cách server thực sự triển khai. Không tiết lộ token, chữ ký, claim nhạy cảm hoặc lý do nội bộ quá chi tiết trong error_description.

Ví dụ challenge cho token không hợp lệ:

~~~http
WWW-Authenticate: Bearer error="invalid_token", error_description="The access token expired"
~~~

Ví dụ challenge khi thiếu scope:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="documents:write"
~~~

Không phải mọi API dùng JWT đều phải đưa error_description ra ngoài. Thông tin tối thiểu thường đủ để client biết cần xác thực lại hoặc xin quyền phù hợp.

## 7. Tái sử dụng response 401 và 403 trong components

Nếu nhiều operation dùng cùng response, khai báo chúng trong components.responses và tham chiếu bằng $ref. Ví dụ cấu hình OpenAPI model:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.headers.Header;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiContractConfiguration {

    @Bean
    OpenAPI apiContract() {
        Schema<?> errorSchema = new Schema<>()
                .type("object")
                .addRequiredItem("code")
                .addRequiredItem("message")
                .addProperty("code", new StringSchema())
                .addProperty("message", new StringSchema());

        Content errorContent = new Content().addMediaType(
                "application/json",
                new MediaType().schema(
                        new Schema<>().$ref("#/components/schemas/ApiError")
                )
        );

        ApiResponse unauthorized = new ApiResponse()
                .description("Chưa xác thực hoặc Bearer token không hợp lệ")
                .addHeaderObject(
                        "WWW-Authenticate",
                        new Header()
                                .description("Bearer authentication challenge")
                                .schema(new StringSchema()
                                        .example("Bearer realm=\"documents-api\""))
                )
                .content(errorContent);

        ApiResponse forbidden = new ApiResponse()
                .description("Đã xác thực nhưng không có quyền thực hiện thao tác")
                .content(errorContent);

        Components components = new Components()
                .addSchemas("ApiError", errorSchema)
                .addResponses("Unauthorized", unauthorized)
                .addResponses("Forbidden", forbidden)
                .addSecuritySchemes(
                        "bearerAuth",
                        new SecurityScheme()
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                );

        return new OpenAPI()
                .info(new Info().title("Documents API").version("1.0.0"))
                .components(components)
                .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }
}
~~~

Sau đó controller có thể tham chiếu:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "401",
        ref = "#/components/responses/Unauthorized"
    ),
    @ApiResponse(
        responseCode = "403",
        ref = "#/components/responses/Forbidden"
    )
})
~~~

Hai response component trên giả định body lỗi JSON giống nhau. Nếu 401 không có body hoặc 403 có cấu trúc khác, hãy tạo component riêng phù hợp. Nếu 403 dùng Bearer insufficient_scope, định nghĩa response component khác có WWW-Authenticate header và mô tả đúng challenge đó.

## 8. Cấu hình Spring Security để status phản ánh đúng luồng

Với OAuth2 Resource Server dùng JWT, cấu hình authorization có thể như sau:

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
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults())
                )
                .build();
    }
}
~~~

Với cấu hình này, request không được xác thực vào endpoint bảo vệ sẽ đi qua authentication entry point và trả 401. Người dùng đã xác thực nhưng không có authority cần thiết sẽ bị access denied và trả 403. Resource Server của Spring Security có các handler Bearer mặc định để tạo challenge phù hợp với lỗi Bearer Token.

Nếu tự thay AuthenticationEntryPoint hoặc AccessDeniedHandler để tạo error body riêng, cần giữ lại status và WWW-Authenticate theo đúng loại lỗi. Đặc biệt, custom handler không được âm thầm bỏ challenge 401. Với Bearer Token thiếu scope, kiểm tra handler có phát challenge insufficient_scope nếu hợp đồng công bố điều đó.

### 8.1. Vì sao @RestControllerAdvice có thể không bắt được 401/403?

Các lỗi xác thực và phân quyền thường xảy ra trong Spring Security filter chain trước khi request tới controller. Vì vậy, @RestControllerAdvice xử lý exception của Spring MVC không tự động xử lý mọi lỗi từ security filter.

Để chuẩn hóa body cho 401/403, cấu hình AuthenticationEntryPoint và AccessDeniedHandler trong SecurityFilterChain hoặc dùng handler mặc định của Resource Server kết hợp cơ chế body phù hợp. Sau đó kiểm tra cả header và body trong HTTP response thực tế.

## 9. CORS và khả năng đọc WWW-Authenticate trên trình duyệt

Một ứng dụng frontend chạy ở origin khác có thể nhận response 401 nhưng JavaScript không đọc được WWW-Authenticate, vì đây không phải CORS-safelisted response header. Nếu frontend cần đọc challenge để quyết định hiển thị đăng nhập lại, server phải expose header qua CORS.

Ví dụ:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(
                List.of("Authorization", "Content-Type", "X-Correlation-ID"));
        configuration.setExposedHeaders(
                List.of("WWW-Authenticate", "X-Request-ID"));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }
}
~~~

Bật CORS trong SecurityFilterChain bằng http.cors(Customizer.withDefaults()) khi ứng dụng sử dụng CorsConfigurationSource như trên.

- allowedHeaders cho phép browser gửi Authorization và các header request được chỉ định.
- exposedHeaders cho phép JavaScript đọc WWW-Authenticate và X-Request-ID từ response.
- allowedOrigins nên liệt kê origin tin cậy; không mở wildcard tùy tiện khi dùng credential.

Access-Control-Allow-Headers và Access-Control-Expose-Headers thường được tạo theo cấu hình CORS và preflight/actual request. Chúng không thay thế Authorization hay WWW-Authenticate, và thường không cần lặp lại như response header nghiệp vụ trong từng operation OpenAPI.

## 10. Kiểm tra tài liệu OpenAPI được sinh ra

Sau khi cấu hình scheme và annotation, mở /v3/api-docs hoặc URL group tương ứng. Kiểm tra các điểm:

1. components.securitySchemes.bearerAuth có type: http, scheme: bearer.
2. Operation được bảo vệ có security requirement trỏ tới bearerAuth.
3. Operation công khai không bị kế thừa security requirement ngoài ý muốn.
4. Response 401 có description và WWW-Authenticate header nếu server trả challenge.
5. Response 403 chỉ có WWW-Authenticate khi luồng authorization thực tế phát challenge đó.
6. Schema body lỗi khớp JSON runtime; response không body thì không khai báo content.
7. Các response component được tham chiếu bằng $ref tồn tại trong components.responses.

Ví dụ OpenAPI rút gọn:

~~~yaml
paths:
  /api/documents/{id}:
    get:
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Tìm thấy tài liệu
        '401':
          description: Chưa xác thực hoặc token không hợp lệ
          headers:
            WWW-Authenticate:
              description: Bearer authentication challenge
              schema:
                type: string
              example: 'Bearer realm="documents-api"'
        '403':
          description: Đã xác thực nhưng không có quyền truy cập
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Ví dụ này thể hiện 403 thông thường không có WWW-Authenticate. Nếu API dùng Bearer insufficient_scope, bổ sung header và ví dụ tương ứng vào response 403.

## 11. Kiểm thử hợp đồng và hành vi HTTP

Kiểm tra tài liệu OpenAPI không đủ để chứng minh security filter chain hoạt động. Cần test cả tài liệu và các trường hợp runtime.

### 11.1. Kiểm tra OpenAPI security scheme và response header

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityOpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsBearerSchemeAndUnauthorizedChallenge() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.components.securitySchemes.bearerAuth.scheme"
                ).value("bearer"))
                .andExpect(jsonPath(
                        "$.paths['/api/documents/{id}'].get.responses['401'].headers.WWW-Authenticate"
                ).exists());
    }
}
~~~

Tên path trong JSONPath phải khớp mapping thật của ứng dụng. Nếu response dùng $ref, kiểm tra component và giá trị $ref thay vì tìm header trực tiếp trong response operation.

### 11.2. Kiểm tra request chưa xác thực

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void returns401AndChallengeWhenCredentialIsMissing() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
}
~~~

Test này giả định endpoint yêu cầu Bearer authentication và handler trả challenge. Nếu ứng dụng dùng cơ chế khác, kiểm tra challenge tương ứng.

Với token không hợp lệ hoặc hết hạn, bổ sung test gửi `Authorization: Bearer <token-khong-hop-le>` và xác nhận server trả `401`. Nếu server công bố lỗi theo RFC 6750, kiểm tra WWW-Authenticate có error `invalid_token`; không assert toàn bộ chuỗi header nếu thứ tự tham số hoặc error_description có thể thay đổi.

### 11.3. Kiểm tra người dùng đã xác thực nhưng thiếu quyền

Với Spring Security Test và JWT request post-processor, có thể tạo authentication có authority không đủ:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void returns403WhenAuthenticatedUserLacksRequiredAuthority() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority("SCOPE_documents:read"))))
            .andExpect(status().isForbidden());
}
~~~

Test này kiểm tra phân quyền ở endpoint yêu cầu authority khác, ví dụ SCOPE_admin. Việc có hay không có WWW-Authenticate trên 403 phụ thuộc handler và cách triển khai Bearer insufficient_scope; chỉ assert header nếu hợp đồng của API quy định rõ điều đó.

## 12. Những lỗi thường gặp

- **Mô tả 401 mà không có WWW-Authenticate**: thiếu challenge khiến response không phản ánh đúng ngữ nghĩa HTTP authentication.
- **Dùng 401 cho mọi lỗi thiếu quyền**: người dùng đã xác thực nhưng không đủ authority thường nhận 403.
- **Gắn WWW-Authenticate vào mọi 403**: chỉ thêm khi server thực sự phát challenge, chẳng hạn Bearer insufficient_scope.
- **Khai báo Authorization như header parameter**: dùng components.securitySchemes và security requirement.
- **Dùng ví dụ Bearer cho endpoint dùng Basic hoặc cơ chế khác**: challenge phải khớp authentication scheme thực tế.
- **Cho rằng @RestControllerAdvice bắt mọi lỗi security**: lỗi filter chain thường cần AuthenticationEntryPoint hoặc AccessDeniedHandler.
- **Custom handler bỏ mất challenge mặc định**: giữ status, WWW-Authenticate và error semantics khi thay body.
- **Swagger UI hiển thị Authorize nhưng server không kiểm tra token**: OpenAPI chỉ mô tả, Spring Security/gateway mới thực thi.
- **Browser không đọc được WWW-Authenticate**: cấu hình CORS expose header nếu frontend cần đọc.
- **Công bố body lỗi không đúng runtime**: schema, media type và status phải khớp response thực tế.
- **Không kiểm tra operation công khai**: security requirement toàn cục có thể vô tình áp dụng lên endpoint không cần token.

## 13. Quy trình mô tả bảo mật cho một operation

1. **Xác định luồng xác thực**: Bearer JWT, Basic, API key, OAuth2 hoặc cơ chế khác.
2. **Xác định điều kiện từ chối**: thiếu/sai credential là 401; thiếu quyền là 403 theo chính sách API.
3. **Xác định challenge**: ghi rõ WWW-Authenticate server thực sự phát ra ở 401 và các trường hợp 403 đặc thù.
4. **Đăng ký security scheme**: mô tả Authorization bằng components.securitySchemes.
5. **Gắn security requirement**: đặt ở cấp tài liệu, controller hoặc operation đúng phạm vi.
6. **Mô tả response**: thêm 401/403, header và body đúng hành vi.
7. **Đồng bộ Spring Security**: cấu hình entry point, access denied handler và resource server.
8. **Cấu hình CORS**: expose WWW-Authenticate nếu browser client cần đọc.
9. **Kiểm tra /v3/api-docs**: xác minh scheme, requirement, response header và schema.
10. **Kiểm thử runtime**: thiếu token, token sai/hết hạn và token hợp lệ nhưng thiếu quyền.

## 14. Checklist review

- [ ] 401 và 403 được phân biệt theo nguyên nhân xác thực/phân quyền.
- [ ] Response 401 có WWW-Authenticate challenge phù hợp.
- [ ] 403 chỉ có WWW-Authenticate khi server thực sự phát challenge, ví dụ insufficient_scope.
- [ ] Authorization được mô tả bằng security scheme.
- [ ] Security requirement chỉ áp dụng cho operation được bảo vệ.
- [ ] Body lỗi, media type và schema khớp runtime.
- [ ] AuthenticationEntryPoint và AccessDeniedHandler trả đúng status/header.
- [ ] Không giả định @RestControllerAdvice xử lý lỗi từ security filter chain.
- [ ] CORS cho phép Authorization và expose WWW-Authenticate khi cần.
- [ ] /v3/api-docs được kiểm tra cho tài liệu mặc định và group liên quan.
- [ ] Integration test bao phủ thiếu credential, credential không hợp lệ và thiếu quyền.

## 15. Tài liệu tham khảo

- [RFC 9110 – HTTP Semantics: 401 Unauthorized](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2)
- [RFC 9110 – HTTP Semantics: 403 Forbidden](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.4)
- [RFC 9110 – WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.1)
- [RFC 6750 – OAuth 2.0 Bearer Token Usage, Error Codes](https://www.rfc-editor.org/rfc/rfc6750.html#section-3.1)
- [OpenAPI Specification 3.1.2 – Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object)
- [OpenAPI Specification 3.1.2 – Security Requirement Object](https://spec.openapis.org/oas/v3.1.2.html#security-requirement-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [springdoc-openapi documentation](https://springdoc.org/)

401 và 403 mô tả hai lý do từ chối khác nhau. Hãy mô tả Authorization bằng security scheme, công bố WWW-Authenticate trong đúng response và giữ cho Spring Security, CORS, OpenAPI cùng phản ánh một hành vi HTTP. Khi client biết lúc nào cần xác thực lại và lúc nào cần xin thêm quyền, việc tích hợp API sẽ rõ ràng và đáng tin cậy hơn.
