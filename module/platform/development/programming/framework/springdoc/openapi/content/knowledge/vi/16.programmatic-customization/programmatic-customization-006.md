# Bổ sung header, mã lỗi hoặc extension theo quy ước ứng dụng

Một ứng dụng Spring Boot thường có những quy ước chung cho toàn bộ API: header tương quan request, header trả về để truy vết, mã lỗi máy đọc được, hoặc metadata riêng để API gateway và công cụ nội bộ xử lý. Nếu khai báo từng quy ước lặp lại ở mọi controller, tài liệu OpenAPI khó duy trì và dễ không đồng nhất.

Springdoc-openapi cho phép bổ sung metadata bằng các điểm mở rộng lập trình như `OpenApiCustomizer`, `GlobalOpenApiCustomizer`, `OperationCustomizer` và `GlobalOperationCustomizer`. Các customizer có thể sửa tài liệu sau khi springdoc phân tích controller: thêm parameter, response, header, schema hoặc vendor extension. Việc tùy biến này chỉ thay đổi đặc tả OpenAPI; ứng dụng vẫn phải thực sự nhận/gửi header và trả mã lỗi tương ứng ở runtime.

## 1. Chọn đúng điểm tùy biến

Springdoc có nhiều cấp tùy biến. Chọn cấp phù hợp giúp thay đổi đúng phạm vi và tránh áp dụng metadata ngoài ý muốn.

| Cơ chế | Phạm vi | Khi nên dùng |
|---|---|---|
| `OpenAPI` bean | Metadata và components cấp tài liệu | Khai báo info, server, security scheme, schema và response dùng chung. |
| `OpenApiCustomizer` | Một tài liệu OpenAPI mặc định | Chỉnh sửa paths, operations hoặc components sau khi sinh. |
| `GlobalOpenApiCustomizer` | Tài liệu mặc định và các group | Áp dụng cùng quy tắc document-level cho mọi tài liệu được sinh. |
| `OperationCustomizer` | Từng operation cùng `HandlerMethod` tương ứng | Dựa vào method/controller annotation để bổ sung parameter, response hoặc extension. |
| `GlobalOperationCustomizer` | Operation ở các tài liệu/group | Áp dụng quy tắc operation-level xuyên suốt các group. |

Một số nguyên tắc lựa chọn:

- Dữ liệu dùng chung và ổn định như `components.responses` nên đăng ký ở cấp `OpenAPI` bean.
- Header áp dụng cho tất cả operation có thể được bổ sung ở cấp document bằng `GlobalOpenApiCustomizer`.
- Quy tắc phụ thuộc annotation của controller/method nên dùng `GlobalOperationCustomizer` hoặc `OperationCustomizer`.
- Extension ở cấp API đặt trên `OpenAPI`; extension gắn với một endpoint đặt trên `Operation`.
- Nếu chỉ một vài endpoint có quy tắc riêng, hãy dùng annotation đánh dấu hoặc customizer có điều kiện thay vì thêm metadata vào mọi operation.

Tên package của các customizer trong springdoc 2.x/3.x thường thuộc `org.springdoc.core.customizers`. Kiểm tra dependency và import theo major version đang dùng nếu IDE không tìm thấy interface.

## 2. Bổ sung request header dùng chung

Giả sử tất cả request có thể gửi header `X-Correlation-ID` để liên kết log giữa gateway, controller và service. Đây là request header nên được mô tả trong `parameters` của operation với `in: header`.

Có thể thêm parameter bằng `GlobalOpenApiCustomizer`:

```java
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.List;

@Configuration
class CommonHeaderOpenApiConfiguration {

    @Bean
    GlobalOpenApiCustomizer correlationIdHeader() {
        return openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }

            openApi.getPaths().values().forEach(pathItem -> {
                boolean inherited = hasHeader(
                        pathItem.getParameters(), "X-Correlation-ID");

                pathItem.readOperations().forEach(operation -> {
                    if (!inherited && !hasHeader(
                            operation.getParameters(), "X-Correlation-ID")) {
                        operation.addParametersItem(
                                new Parameter()
                                        .in("header")
                                        .name("X-Correlation-ID")
                                        .description("Mã tương quan request do client hoặc gateway tạo")
                                        .required(false)
                                        .schema(new StringSchema())
                        );
                    }
                });
            });
        };
    }

    private static boolean hasHeader(
            List<Parameter> parameters, String headerName) {
        return parameters != null && parameters.stream().anyMatch(parameter ->
                "header".equalsIgnoreCase(parameter.getIn())
                        && headerName.equalsIgnoreCase(parameter.getName())
        );
    }
}
```

Đoạn code kiểm tra header đã được khai báo ở cấp Path Item hoặc Operation trước khi thêm. Việc kiểm tra không phân biệt chữ hoa/chữ thường vì tên HTTP header không phân biệt hoa thường. Điều này giúp tránh tạo hai parameter cùng tên khi controller đã khai báo header riêng.

Trong ứng dụng, request header cần được đọc hoặc tạo ở runtime bằng filter, interceptor, argument resolver hoặc controller phù hợp. Customizer chỉ làm cho Swagger UI và client generator biết header đó tồn tại.

### 2.1. Không khai báo `Authorization` như một header parameter thông thường

OpenAPI có quy tắc riêng cho xác thực. Không mô tả header `Authorization`, `Accept` hoặc `Content-Type` bằng Parameter Object thông thường. Với Bearer token, API key hoặc OAuth2, khai báo `components.securitySchemes` rồi gắn security requirement vào tài liệu/operation.

Ví dụ Bearer JWT:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;

@Bean
OpenAPI securityOpenAPI() {
    return new OpenAPI()
            .info(new Info().title("Document API").version("1.0.0"))
            .components(new Components().addSecuritySchemes(
                    "bearerAuth",
                    new SecurityScheme()
                            .type(SecurityScheme.Type.HTTP)
                            .scheme("bearer")
                            .bearerFormat("JWT")
            ))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
}
```

Security scheme vừa mô tả cách xác thực vừa cho Swagger UI biết cách yêu cầu token. Việc thêm một parameter tên `Authorization` không thay thế cơ chế này.

Nếu ứng dụng đã có `OpenAPI` bean để đăng ký schema hoặc response component, hãy thêm security scheme vào bean hiện tại thay vì tạo bean thứ hai với cấu hình trùng lặp.
`addSecurityItem` ở cấp tài liệu áp dụng yêu cầu Bearer cho mọi operation. Với endpoint công khai, khai báo security rỗng ở operation đó để thể hiện rằng endpoint không yêu cầu scheme này.

## 3. Bổ sung response header

Request header được mô tả trong `parameters`; response header được mô tả bên trong Response Object. Ví dụ, server trả `X-Request-ID` để client cung cấp mã khi liên hệ bộ phận hỗ trợ.

Có thể thêm header vào một response component dùng chung:

```java
import io.swagger.v3.oas.models.headers.Header;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.responses.ApiResponse;

ApiResponse notFoundResponse = new ApiResponse()
        .description("Không tìm thấy tài nguyên")
        .addHeaderObject(
                "X-Request-ID",
                new Header()
                        .description("Mã request dùng để tra cứu log phía server")
                        .schema(new StringSchema())
        );
```

Nếu nhiều response cùng trả header đó, hãy đưa header vào component response hoặc dùng customizer để bổ sung vào các response đã chọn. Không thêm response header vào `parameters`: hai vị trí có ý nghĩa khác nhau trong OpenAPI.

Có thể bổ sung header cho các response lỗi đã được khai báo:

```java
import io.swagger.v3.oas.models.headers.Header;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer requestIdOnErrorResponses() {
    return openApi -> {
        if (openApi.getPaths() == null) {
            return;
        }

        openApi.getPaths().values().forEach(pathItem ->
                pathItem.readOperations().forEach(operation -> {
                    if (operation.getResponses() == null) {
                        return;
                    }

                    operation.getResponses().forEach((status, response) -> {
                        boolean isError = status.matches("[45][0-9]{2}")
                                || "default".equals(status);
                        if (isError) {
                            // Bỏ qua response reference; khai báo header trong component đích.
                            if (response.get$ref() != null) {
                                return;
                            }
                            boolean alreadyDefined = response.getHeaders() != null
                                    && response.getHeaders().keySet().stream()
                                            .anyMatch(name -> name.equalsIgnoreCase("X-Request-ID"));
                            if (!alreadyDefined) {
                                response.addHeaderObject(
                                        "X-Request-ID",
                                        new Header()
                                                .description("Mã request dùng để tra cứu log")
                                                .schema(new StringSchema())
                                );
                            }
                        }
                    });
                })
        );
    };
}
```

Customizer này thêm header cho response lỗi `4xx`, `5xx` và `default`, đồng thời tránh ghi đè header cùng tên đã có. Với response là `$ref`, customizer bỏ qua entry đó; hãy khai báo header trực tiếp trong `components.responses` tương ứng để không tạo sibling field không hợp lệ. Chỉ dùng quy tắc toàn cục nếu server thực sự trả `X-Request-ID` cho các phản hồi đó. Nếu một số endpoint không có header này, hãy giới hạn theo path, group hoặc annotation đánh dấu.

## 4. Chuẩn hóa body và mã lỗi

Mã lỗi thường là một field trong JSON body để client có thể xử lý bằng logic ổn định. Ví dụ:

```json
{
  "code": "DOCUMENT_NOT_FOUND",
  "message": "Không tìm thấy tài liệu",
  "traceId": "a8b7c6d5e4",
  "timestamp": "2026-11-20T10:30:00Z",
  "path": "/api/documents/42"
}
```

`code` là mã máy đọc được, ổn định giữa các ngôn ngữ; `message` là nội dung dành cho người đọc và có thể được bản địa hóa; `traceId` hỗ trợ truy vết; `timestamp` và `path` cung cấp ngữ cảnh. Không nên yêu cầu client phân tích nội dung `message` để quyết định nghiệp vụ vì câu chữ có thể thay đổi.

Tạo DTO dùng chung:

```java
import java.time.Instant;

public record ApiError(
        String code,
        String message,
        String traceId,
        Instant timestamp,
        String path
) {}
```

Đăng ký schema trong `OpenAPI` bean:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.responses.ApiResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiErrorSchemaConfiguration {

    @Bean
    OpenAPI apiErrorSchema() {
        Schema<?> errorSchema = new Schema<>()
                .type("object")
                .addRequiredItem("code")
                .addRequiredItem("message")
                .addProperty("code", new StringSchema()
                        .description("Mã lỗi ổn định để client xử lý")
                        .example("DOCUMENT_NOT_FOUND"))
                .addProperty("message", new StringSchema()
                        .description("Thông điệp mô tả lỗi"))
                .addProperty("traceId", new StringSchema()
                        .description("Mã truy vết request"))
                .addProperty("timestamp", new StringSchema().format("date-time"))
                .addProperty("path", new StringSchema());

        Components components = new Components()
                .addSchemas("ApiError", errorSchema)
                .addResponses("BadRequest", apiErrorResponse("Tham số hoặc body không hợp lệ"))
                .addResponses("Unauthorized", apiErrorResponse("Chưa xác thực hoặc token không hợp lệ"))
                .addResponses("Forbidden", apiErrorResponse("Không có quyền thực hiện thao tác"))
                .addResponses("NotFound", apiErrorResponse("Không tìm thấy tài nguyên"))
                .addResponses("Conflict", apiErrorResponse("Dữ liệu xung đột với trạng thái hiện tại"));

        return new OpenAPI()
                .info(new Info().title("Document API").version("1.0.0"))
                .components(components);
    }

    private static ApiResponse apiErrorResponse(String description) {
        return new ApiResponse()
                .description(description)
                .content(new Content().addMediaType(
                        "application/json",
                        new MediaType().schema(
                                new Schema<>().$ref("#/components/schemas/ApiError")
                        )
                ));
    }
}
```

Trong ứng dụng đã có một `OpenAPI` bean khác, hãy hợp nhất các component vào bean hiện hữu thay vì khai báo nhiều bean cùng mục đích rồi dựa vào thứ tự khởi tạo. Một lựa chọn khác là dùng `OpenApiCustomizer` để thêm schema vào `openApi.getComponents()` sau khi kiểm tra components đã tồn tại.

### 4.1. Định nghĩa response lỗi dùng chung

Bean ở phần trước đăng ký `ApiError` trong `components.schemas` và năm response trong `components.responses`. Mỗi Response Object có description riêng nhưng dùng chung schema body. Nếu response thực tế dùng `application/problem+json` hoặc một error envelope khác, hãy đổi media type và schema cho khớp.

Khi ứng dụng đã có `OpenAPI` bean, thêm schema và response vào `Components` hiện hữu thay vì khai báo bean thứ hai. Bean `OpenAPI` là nơi phù hợp cho component cần xuất hiện nhất quán trong tài liệu mặc định và các group.

## 5. Tự động gắn response lỗi theo quy ước

Không nên tự động thêm `404` vào mọi operation nếu không phải endpoint nào cũng có thể trả lỗi không tìm thấy. Một cách kiểm soát phạm vi là dùng annotation nội bộ để đánh dấu method/controller cần các response chuẩn.

Annotation đánh dấu:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface DocumentedApiErrors {
    String[] value() default {"400", "401", "403", "404"};
}
```

Đặt annotation ở controller nếu mọi operation trong controller có cùng nhóm lỗi, hoặc đặt trên method nếu chỉ một operation cần chúng:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.validation.Valid;
import java.util.UUID;

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    @DocumentedApiErrors({"400", "401", "403", "404"})
    @GetMapping("/{id}")
    DocumentResponse findById(@PathVariable UUID id) {
        return documentService.findById(id);
    }

    @DocumentedApiErrors({"400", "401", "403", "409"})
    @PostMapping
    DocumentResponse create(@Valid @RequestBody CreateDocumentRequest request) {
        return documentService.create(request);
    }
}
```

Tạo `GlobalOperationCustomizer` để chuyển annotation thành response reference:

```java
import io.swagger.v3.oas.models.responses.ApiResponse;
import org.springdoc.core.customizers.GlobalOperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiErrorOperationCustomizerConfiguration {

    @Bean
    GlobalOperationCustomizer documentedApiErrors() {
        return (operation, handlerMethod) -> {
            DocumentedApiErrors marker = AnnotatedElementUtils.findMergedAnnotation(
                    handlerMethod.getMethod(), DocumentedApiErrors.class);

            if (marker == null) {
                marker = AnnotatedElementUtils.findMergedAnnotation(
                        handlerMethod.getBeanType(), DocumentedApiErrors.class);
            }

            if (marker == null) {
                return operation;
            }

            for (String status : marker.value()) {
                String componentName = responseComponentName(status);
                if (componentName == null) {
                    throw new IllegalArgumentException(
                            "Chưa đăng ký response component cho status " + status);
                }

                if (operation.getResponses() == null) {
                    operation.setResponses(new io.swagger.v3.oas.models.responses.ApiResponses());
                }

                if (!operation.getResponses().containsKey(status)) {
                    operation.getResponses().addApiResponse(
                            status,
                            new ApiResponse().$ref(
                                    "#/components/responses/" + componentName)
                    );
                }
            }
            return operation;
        };
    }

    private static String responseComponentName(String status) {
        return switch (status) {
            case "400" -> "BadRequest";
            case "401" -> "Unauthorized";
            case "403" -> "Forbidden";
            case "404" -> "NotFound";
            case "409" -> "Conflict";
            default -> null;
        };
    }
}
```

Customizer trên chỉ gắn response mà annotation yêu cầu và không ghi đè response đã khai báo trực tiếp trên operation. Nếu một method đã định nghĩa response `404` với schema đặc thù, định nghĩa tường minh đó được giữ lại.

Trong ví dụ, danh sách status được giới hạn bởi `responseComponentName`. Khi bổ sung mã lỗi mới, cần thêm component tương ứng và cập nhật ánh xạ. Không tự tạo `$ref` tới component chưa tồn tại.

Nếu không cần annotation riêng, có thể khai báo `@ApiResponse(ref = "#/components/responses/NotFound")` trực tiếp trên method. Customizer hữu ích khi quy ước lặp lại trên nhiều controller hoặc cần lấy metadata từ annotation của ứng dụng.

## 6. Bổ sung vendor extension `x-*`

OpenAPI cho phép thêm vendor extension để lưu metadata riêng của tổ chức. Tên extension phải bắt đầu bằng `x-`, ví dụ:

- `x-owner-team`: nhóm chịu trách nhiệm operation.
- `x-audit-event`: tên sự kiện audit cần ghi nhận.
- `x-rate-limit-tier`: mức giới hạn được gateway áp dụng.
- `x-internal`: đánh dấu metadata nội bộ cho công cụ build hoặc portal.

Extension có thể được gắn ở cấp tài liệu, operation, parameter, schema hoặc response tùy nơi cần sử dụng. Giá trị nên là dữ liệu JSON hợp lệ như string, boolean, number, array hoặc object.

### 6.1. Extension cấp tài liệu

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OpenApiCustomizer apiCatalogMetadata() {
    return openApi -> {
        openApi.addExtension("x-api-domain", "document-management");
        openApi.addExtension("x-owner-team", "platform-documents");
        openApi.addExtension("x-contract-tier", "internal");
    };
}
```

Kết quả xuất hiện ở cấp gốc OpenAPI:

```yaml
x-api-domain: document-management
x-owner-team: platform-documents
x-contract-tier: internal
```

### 6.2. Extension theo từng operation

Nếu metadata khác nhau theo endpoint, dùng `OperationCustomizer` hoặc `GlobalOperationCustomizer`:

```java
import org.springdoc.core.customizers.GlobalOperationCustomizer;
import java.util.Map;

@Bean
GlobalOperationCustomizer auditMetadata() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().getName().startsWith("find")) {
            operation.addExtension("x-audit-event", "resource.read");
        } else if (handlerMethod.getMethod().getName().startsWith("delete")) {
            operation.addExtension("x-audit-event", "resource.delete");
        }
        return operation;
    };
}
```

Quy tắc dựa trên tên method chỉ phù hợp với ví dụ đơn giản. Trong dự án lớn, nên dùng annotation rõ ràng như `@AuditEvent("document.read")` để tránh việc refactor tên method vô tình thay đổi metadata hợp đồng.

Một extension có thể chứa object:

```java
import java.util.Map;

operation.addExtension("x-rate-limit", Map.of(
        "requests", 100,
        "windowSeconds", 60,
        "scope", "user"
));
```

Đoạn code này cần `import java.util.Map;` và được đặt bên trong customizer hoặc phương thức đang có biến `operation`.

Chỉ thêm extension nếu có consumer cụ thể như API portal, gateway plugin, tài liệu nội bộ hoặc code generation. Consumer không hiểu extension có thể bỏ qua nó; không dùng extension để thay thế field chuẩn của OpenAPI như `security`, `parameters`, `responses` hoặc `deprecated`.

## 7. Dùng `@Extension` khi metadata tĩnh là đủ

Không phải mọi extension đều cần customizer. Với metadata cố định trên một operation, có thể dùng `@Extension` và `@ExtensionProperty`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.extensions.Extension;
import io.swagger.v3.oas.annotations.extensions.ExtensionProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import java.util.UUID;

@Operation(
    summary = "Lấy tài liệu theo mã",
    extensions = @Extension(properties = {
        @ExtensionProperty(name = "x-owner-team", value = "platform-documents"),
        @ExtensionProperty(name = "x-audit-event", value = "document.read")
    })
)
@GetMapping("/{id}")
DocumentResponse findById(@PathVariable UUID id) {
    return documentService.findById(id);
}
```

Annotation phù hợp với giá trị tĩnh, còn customizer phù hợp với metadata được suy ra từ cấu hình, annotation nội bộ, môi trường hoặc quy tắc dùng chung. Kiểm tra output để xác nhận kiểu dữ liệu extension đúng mong muốn; `@ExtensionProperty` thường mô tả giá trị dạng chuỗi, trong khi customizer có thể thêm object/number/boolean có kiểu.

## 8. Tránh trùng lặp và ghi đè metadata

Customizer có thể chạy trên tài liệu đã chứa annotation hoặc metadata được suy ra. Nếu chỉ gọi `addParametersItem` hoặc `addApiResponse` vô điều kiện, tài liệu có thể chứa thông tin trùng hoặc làm thay đổi response đã được controller mô tả cụ thể.

Một số quy tắc an toàn:

- Kiểm tra parameter theo cả `name` và `in`; cùng tên ở query và header là hai parameter khác nhau.
- So sánh tên header không phân biệt hoa thường.
- Kiểm tra `responses.containsKey(status)` trước khi thêm response mới.
- Chỉ thêm response lỗi cho operation có khả năng trả lỗi đó.
- Dùng component `$ref` để tránh sao chép body/schema giữa nhiều operation.
- Khi sửa component dùng chung, đánh giá ảnh hưởng tới tất cả operation đang tham chiếu.
- Đặt customizer có tính idempotent: chạy lại không tạo thêm bản sao.
- Không ghi đè extension đã được khai báo rõ ràng nếu giá trị hiện tại có ưu tiên cao hơn.

Ví dụ helper thêm extension khi chưa có:

```java
import io.swagger.v3.oas.models.Operation;

private static void addExtensionIfAbsent(
        Operation operation, String name, Object value) {
    if (operation.getExtensions() == null
            || !operation.getExtensions().containsKey(name)) {
        operation.addExtension(name, value);
    }
}
```

Nếu cần cho phép cấu hình override, hãy xác định thứ tự ưu tiên rõ ràng, ví dụ annotation trên method ưu tiên hơn annotation trên class, và metadata của method ưu tiên hơn giá trị mặc định toàn cục.

## 9. Phân biệt tài liệu OpenAPI với hành vi runtime

Customizer chỉ sửa đặc tả. Nó không tự triển khai filter, không tạo header HTTP, không đổi status code và không sinh error body.

| Thay đổi OpenAPI | Việc runtime cần có |
|---|---|
| Thêm request header `X-Correlation-ID` | Filter/interceptor/controller đọc hoặc tạo mã tương quan. |
| Thêm response header `X-Request-ID` | Response filter, interceptor hoặc controller thực sự ghi header. |
| Mô tả `ApiError.code` | Exception handler trả body có field `code` với mã ổn định. |
| Khai báo response `429` và `Retry-After` | Rate limiter/gateway trả `429` cùng header `Retry-After`. |
| Thêm `x-rate-limit-tier` | Gateway hoặc consumer nội bộ hiểu và thực thi metadata đó. |
| Thêm security scheme | Spring Security/gateway phải thực sự bảo vệ endpoint tương ứng. |

Đừng công bố một header hoặc response chỉ vì muốn Swagger UI hiển thị đẹp. Client có thể sinh code dựa trên hợp đồng đó và sẽ gặp lỗi khi server không thực hiện như tài liệu.

## 10. Kiểm tra OpenAPI sau khi tùy biến

Sau khi thêm customizer, khởi động ứng dụng và truy cập `/v3/api-docs`. Với group, truy cập tài liệu group tương ứng. Kiểm tra:

1. Request header nằm trong `parameters` với `in: header`.
2. Response header nằm trong `responses.<status>.headers`.
3. Error schema nằm trong `components.schemas` và response component nằm trong `components.responses`.
4. Operation tham chiếu đúng component bằng `$ref`.
5. Extension có tiền tố `x-` và nằm đúng cấp.
6. Không có parameter hoặc response trùng.
7. Các group cần công bố đều nhận được customizer tương ứng.
8. Security scheme được mô tả bằng `securitySchemes`, không phải parameter `Authorization`.

Ví dụ cấu trúc OpenAPI sau tùy biến:

```yaml
paths:
  /api/documents/{id}:
    get:
      parameters:
        - name: X-Correlation-ID
          in: header
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Tìm thấy tài liệu
        '404':
          $ref: '#/components/responses/NotFound'
      x-owner-team: platform-documents
      x-audit-event: document.read
components:
  schemas:
    ApiError:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
        traceId:
          type: string
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      headers:
        X-Request-ID:
          schema:
            type: string
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
```

Đây là ví dụ minh họa. Tên component, schema và extension thực tế phải khớp với cấu hình và quy ước của ứng dụng.

## 11. Kiểm thử tùy biến bằng integration test

Có thể dùng MockMvc để kiểm tra tài liệu JSON được sinh ra. Ví dụ kiểm tra request header và extension:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiCustomizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsCommonHeaderAndOperationExtensions() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.paths['/api/documents/{id}'].get.parameters[?(@.name=='X-Correlation-ID')]"
                ).isNotEmpty())
                .andExpect(jsonPath(
                        "$.paths['/api/documents/{id}'].get['x-owner-team']"
                ).value("platform-documents"));
    }
}
```

Với response component, kiểm tra cả định nghĩa lẫn reference:

```java
@Test
void documentsReusableNotFoundResponse() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                    "$.components.responses.NotFound.description"
            ).exists())
            .andExpect(jsonPath(
                    "$.paths['/api/documents/{id}'].get.responses['404']['$ref']"
            ).value("#/components/responses/NotFound"));
}
```

Test OpenAPI không thay thế test HTTP runtime. Hãy kiểm tra request có correlation ID, response có request ID, và exception handler thực sự trả đúng `ApiError` cùng status code.

## 12. Những lỗi thường gặp

- **Thêm `Authorization` như header parameter**: dùng security scheme và security requirement của OpenAPI.
- **Nhầm request header với response header**: request header nằm trong `parameters`; response header nằm trong Response Object.
- **Thêm header vào mọi operation nhưng server không xử lý**: tài liệu và runtime lệch nhau.
- **Gắn `404` vào mọi endpoint**: một số operation không thể trả `404`; dùng annotation hoặc quy tắc lọc.
- **Tham chiếu response component chưa được đăng ký**: `$ref` không phân giải được.
- **Ghi đè response đã khai báo**: customizer làm mất schema hoặc description riêng; kiểm tra key trước khi thêm.
- **Dùng extension thay cho field chuẩn**: nếu OpenAPI đã có `security`, `deprecated`, `tags` hoặc `responses`, hãy dùng field chuẩn.
- **Extension không có consumer**: metadata không được công cụ nào sử dụng sẽ làm tài liệu khó hiểu; ghi rõ mục đích và chủ sở hữu.
- **Dùng `OpenApiCustomizer` nhưng mong áp dụng cho mọi group**: chọn `GlobalOpenApiCustomizer` khi cần xử lý tất cả tài liệu group.
- **Customizer không idempotent**: nhiều lần xử lý có thể thêm parameter hoặc extension trùng lặp.
- **Không kiểm tra runtime**: OpenAPI hiển thị header hoặc mã lỗi nhưng controller/filter không trả dữ liệu tương ứng.

## 13. Quy trình triển khai quy ước API

1. **Xác định quy ước**: ghi rõ tên header, mã lỗi, body lỗi và extension cần công bố.
2. **Chọn phạm vi**: toàn API, một group, một controller hay một operation.
3. **Đăng ký component dùng chung**: schema lỗi, response, security scheme hoặc metadata cấp tài liệu.
4. **Chọn customizer**: document-level hay operation-level; dùng global variant nếu áp dụng cho group.
5. **Tránh ghi đè**: kiểm tra parameter, response và extension đã có trước khi thêm.
6. **Đồng bộ runtime**: triển khai filter/interceptor, exception handler, rate limiter hoặc security policy tương ứng.
7. **Kiểm tra `/v3/api-docs`**: xác nhận vị trí, schema, `$ref`, header và extension.
8. **Kiểm thử HTTP**: xác nhận server thực sự nhận/gửi header và trả status/body đã mô tả.
9. **Review consumer**: bảo đảm gateway, SDK generator hoặc portal hiểu extension nếu có.

## 14. Checklist review

- [ ] Request header được khai báo ở đúng vị trí `in: header`.
- [ ] Response header được khai báo trong response tương ứng.
- [ ] Không dùng parameter thông thường cho `Authorization`, `Accept` hoặc `Content-Type`.
- [ ] Error body có mã lỗi ổn định và schema dùng chung.
- [ ] Response component đã được đăng ký trước khi operation tham chiếu.
- [ ] Chỉ gắn mã lỗi cho operation có thể trả status tương ứng.
- [ ] Extension có tiền tố `x-`, đúng cấp và có consumer rõ ràng.
- [ ] Customizer phù hợp với tài liệu mặc định hay tất cả group.
- [ ] Logic tránh trùng và không ghi đè metadata tường minh.
- [ ] Runtime filter/interceptor/exception handler thực hiện đúng quy ước đã công bố.
- [ ] `/v3/api-docs` và các group đã được kiểm tra.
- [ ] Integration test kiểm tra cả OpenAPI lẫn HTTP response thực tế.

## 15. Tài liệu tham khảo

- [springdoc-openapi documentation](https://springdoc.org/)
- [springdoc-openapi FAQ – OpenAPI and operation customizers](https://springdoc.org/faq.html)
- [OpenAPI Specification 3.1.2 – Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object)
- [OpenAPI Specification 3.1.2 – Response Object](https://spec.openapis.org/oas/v3.1.2.html#response-object)
- [OpenAPI Specification 3.1.2 – Specification Extensions](https://spec.openapis.org/oas/v3.1.2.html#specification-extensions)
- [Swagger Core – OpenAPI model](https://github.com/swagger-api/swagger-core)
- [Swagger Annotations – `@ExtensionProperty`](https://docs.swagger.io/swagger-core/v2.2.30/apidocs/io/swagger/v3/oas/annotations/extensions/ExtensionProperty.html)
- [Spring Framework – Filters and Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)

Các quy ước header, mã lỗi và extension nên được định nghĩa một lần, áp dụng đúng phạm vi và kiểm chứng với hành vi HTTP thật. Springdoc customizer giúp giữ tài liệu nhất quán giữa nhiều controller và group; response component giúp tái sử dụng schema lỗi; vendor extension cung cấp metadata cho công cụ riêng. Khi mỗi thay đổi OpenAPI đều có phần runtime tương ứng và integration test, hợp đồng API sẽ rõ ràng và đáng tin cậy hơn.
