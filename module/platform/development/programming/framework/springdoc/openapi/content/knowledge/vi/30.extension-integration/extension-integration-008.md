# Phạm vi endpoint được phép công bố cho bên gọi công cụ

Một bên gọi công cụ có thể là agent, workflow engine, API client hoặc hệ thống tích hợp đọc OpenAPI để khám phá operation rồi quyết định operation nào có thể gọi. Khi công bố tài liệu cho các hệ thống này, phạm vi endpoint cần được giới hạn rõ ràng. Một document chứa toàn bộ controller có thể vô tình đưa API quản trị, endpoint nội bộ hoặc thao tác có tác động lớn vào danh sách công cụ mà client có thể khám phá.

Với springdoc-openapi, cách làm phù hợp là tạo một group riêng cho bên gọi công cụ, chỉ đưa vào những operation đã được duyệt và mô tả chính xác cách xác thực cùng tác động của từng operation. OpenAPI document xác định khả năng mà client có thể khám phá; Spring Security, gateway và chính endpoint mới quyết định người gọi có thực sự được phép thực hiện thao tác hay không.

## 1. Xác định phạm vi công bố trước khi tạo group

Hãy bắt đầu bằng danh sách operation được phép công bố. Một operation được xác định bởi cặp HTTP method và path, ví dụ GET /api/tools/products hoặc POST /api/tools/orders. Không chỉ liệt kê controller hoặc package, vì một controller có thể chứa cả thao tác đọc và thao tác thay đổi dữ liệu.

Ví dụ phạm vi cho một tool client quản lý catalog và tạo đơn:

| Operation | Công bố? | Lý do |
| --- | --- | --- |
| GET /api/tools/products | Có | Tra cứu catalog, không thay đổi dữ liệu. |
| POST /api/tools/orders | Có điều kiện | Tạo đơn hàng, có tác động nghiệp vụ và cần scope ghi riêng. |
| DELETE /api/admin/orders/{id} | Không | Thao tác quản trị, có thể phá hủy dữ liệu. |
| GET /actuator/env | Không | Endpoint vận hành có thể tiết lộ cấu hình nhạy cảm. |
| POST /api/internal/reindex | Không | Tác vụ nội bộ có ảnh hưởng rộng đến hệ thống. |
| GET /api/debug/** | Không | Endpoint chẩn đoán không dành cho client bên ngoài. |

Mặc định nên ưu tiên các operation đọc có phạm vi dữ liệu rõ ràng. Chỉ đưa operation ghi vào group khi có yêu cầu nghiệp vụ, xác thực, phân quyền, giới hạn đầu vào, audit và cách xử lý retry phù hợp. Tránh đưa thao tác xóa hàng loạt, thực thi lệnh, truy cập file tùy ý hoặc gọi URL do người dùng cung cấp vào nhóm công cụ dùng chung.

Danh sách này là chính sách công bố của API. Nó cần được review cùng chủ sở hữu nghiệp vụ và đội vận hành trước khi đưa vào registry hoặc cung cấp cho bên gọi công cụ.

## 2. Tạo group riêng bằng GroupedOpenApi

Không dùng document mặc định chứa mọi endpoint làm danh mục công cụ. Tạo một group riêng, ví dụ tool-caller-v1:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ToolCallerAllowlistOpenApiConfiguration {

    @Bean
    GroupedOpenApi toolCallerApi() {
        return GroupedOpenApi.builder()
            .group("tool-caller-v1")
            .packagesToScan("com.example.api.tools")
            .pathsToMatch("/api/tools/**")
            .pathsToExclude(
                "/api/tools/admin/**",
                "/api/tools/internal/**"
            )
            .build();
    }
}
~~~

Trong ví dụ, controller được đặt trong package dành cho endpoint công cụ; path filter giới hạn URL công bố; exclude filter loại các nhánh quản trị và nội bộ. Các filter này kết hợp để thu hẹp phạm vi. Nếu controller hợp lệ nằm ngoài package được scan, operation sẽ không xuất hiện dù path khớp.

Với base path mặc định, document được truy cập tại:

- JSON: /v3/api-docs/tool-caller-v1
- YAML: /v3/api-docs/tool-caller-v1.yaml

Group id là định danh công khai của document. Hãy giữ nó ổn định trong một phiên bản hợp đồng và tạo group id mới khi cần phát hành một hợp đồng không tương thích, ví dụ tool-caller-v2.

## 3. Dùng allowlist chính xác theo path và HTTP method

packagesToScan, pathsToMatch và pathsToExclude là các bộ lọc hữu ích, nhưng path prefix rộng như /api/tools/** có thể tự động nhận cả operation mới được thêm sau này. Với nhóm công cụ có phạm vi chặt, nên duy trì allowlist gồm cả method và path.

Ví dụ dùng OpenApiCustomizer gắn riêng với group để loại operation ngoài allowlist:

Ví dụ này là phương án thay thế hoặc mở rộng cấu hình group ở mục trước. Nếu dùng cả hai, chỉ đăng ký một bean cho group tool-caller-v1 và gộp các filter vào cùng builder; không khai báo hai GroupedOpenApi bean trùng group id.

~~~java
import io.swagger.v3.oas.models.PathItem;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Map;
import java.util.Set;

@Configuration
class ToolCallerOpenApiConfiguration {

    private static final Map<String, Set<PathItem.HttpMethod>> ALLOWED = Map.of(
        "/api/tools/products", Set.of(PathItem.HttpMethod.GET),
        "/api/tools/orders", Set.of(PathItem.HttpMethod.POST)
    );

    @Bean
    GroupedOpenApi toolCallerApi() {
        OpenApiCustomizer allowOnlyApprovedOperations = openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }

            openApi.getPaths().entrySet().removeIf(entry -> {
                Set<PathItem.HttpMethod> allowedMethods = ALLOWED.get(entry.getKey());
                if (allowedMethods == null) {
                    return true;
                }

                PathItem pathItem = entry.getValue();
                for (PathItem.HttpMethod method : PathItem.HttpMethod.values()) {
                    if (allowedMethods.contains(method)) {
                        continue;
                    }
                    removeOperation(pathItem, method);
                }
                return pathItem.readOperations().isEmpty();
            });
        };

        return GroupedOpenApi.builder()
            .group("tool-caller-v1")
            .pathsToMatch("/api/tools/**")
            .addOpenApiCustomizer(allowOnlyApprovedOperations)
            .build();
    }

    private static void removeOperation(
        PathItem pathItem,
        PathItem.HttpMethod method
    ) {
        switch (method) {
            case GET -> pathItem.setGet(null);
            case PUT -> pathItem.setPut(null);
            case POST -> pathItem.setPost(null);
            case DELETE -> pathItem.setDelete(null);
            case OPTIONS -> pathItem.setOptions(null);
            case HEAD -> pathItem.setHead(null);
            case PATCH -> pathItem.setPatch(null);
            case TRACE -> pathItem.setTrace(null);
        }
    }
}
~~~

Allowlist trên chỉ giữ GET /api/tools/products và POST /api/tools/orders. Nếu thêm DELETE vào cùng path /api/tools/orders, customizer vẫn loại operation đó. Khi nâng cấp Swagger Core, kiểm tra enum PathItem.HttpMethod và các setter của phiên bản đang dùng để bảo đảm customizer vẫn bao phủ tất cả HTTP method được hỗ trợ.

Đây là bộ lọc ở lớp tạo document. Nó không xóa mapping khỏi Spring MVC và không ngăn request trực tiếp đến endpoint. Chính sách runtime vẫn phải được cấu hình riêng.

## 4. Phân biệt @Hidden với lọc riêng theo group

Có thể dùng @Hidden để loại controller hoặc operation khỏi tài liệu:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AdminOrderController {

    @Hidden
    @DeleteMapping("/api/admin/orders/{id}")
    void deleteOrder(@PathVariable String id) {
        // Xử lý thao tác quản trị.
    }
}
~~~

@Hidden phù hợp khi operation không nên xuất hiện trong bất kỳ OpenAPI document nào. Nếu endpoint cần có mặt trong tài liệu nội bộ nhưng phải biến mất khỏi group dành cho tool caller, không nên đặt @Hidden toàn cục. Hãy dùng filter riêng cho group, chẳng hạn pathsToExclude hoặc OpenApiCustomizer.

Ẩn operation khỏi OpenAPI chỉ thay đổi tài liệu được sinh ra. Mapping vẫn tồn tại và vẫn có thể được gọi nếu request vượt qua các lớp bảo mật runtime. Không dùng @Hidden như một cơ chế phân quyền.

## 5. Chỉ công bố operation có ý nghĩa rõ ràng

Operation ID thường được công cụ sinh client hoặc lớp tích hợp dùng để tạo tên hàm ổn định. Hãy đặt operationId duy nhất, ngắn gọn và mô tả hành động:

Đoạn code sau tập trung vào metadata operation; phần tham số và xử lý được rút gọn.

~~~java
@GetMapping("/api/tools/products")
@Operation(
    operationId = "searchProducts",
    summary = "Tìm sản phẩm",
    description = "Tra cứu sản phẩm đang được phép bán. Operation chỉ đọc dữ liệu catalog."
)
ProductSearchResponse searchProducts(...) {
    // ...
}
~~~

Tránh tên chung như getData, process hoặc execute. Không đổi operation ID tùy tiện sau khi client đã tạo tool binding dựa trên tên đó. Nếu cần đổi hành vi hoặc schema không tương thích, hãy xem đó là thay đổi hợp đồng và phát hành phiên bản mới phù hợp.

Description nên trả lời:

- Operation làm gì và áp dụng cho loại tài nguyên nào?
- Có thay đổi trạng thái hoặc tạo dữ liệu không?
- Có thể gọi lặp lại an toàn không?
- Tham số nào bắt buộc, có giới hạn độ dài/kích thước nào?
- Response có phân trang hoặc giới hạn số kết quả không?
- Lỗi nghiệp vụ nào có thể xảy ra?

Không viết mô tả mơ hồ như “thực hiện thao tác theo yêu cầu”. Tool caller cần biết chính xác dữ liệu được đọc hoặc thay đổi trước khi quyết định gọi operation.

## 6. Mô tả một operation chỉ đọc

Ví dụ controller cung cấp chức năng tìm kiếm catalog:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@Validated
class ToolProductController {

    @GetMapping(
        value = "/api/tools/products",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        operationId = "searchProducts",
        summary = "Tìm sản phẩm",
        description = "Chỉ đọc catalog; tối đa 50 kết quả trong một lần gọi.",
        tags = {"Tool catalog"},
        security = @SecurityRequirement(
            name = "toolOAuth",
            scopes = {"catalog.read"}
        )
    )
    ProductSearchResponse searchProducts(
        @Parameter(description = "Từ khóa tìm kiếm, tối đa 80 ký tự")
        @RequestParam(required = false)
        @Size(max = 80)
        String q,
        @Parameter(description = "Số kết quả tối đa, từ 1 đến 50")
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(50)
        int limit
    ) {
        // Gọi service đọc catalog và trả DTO.
        return new ProductSearchResponse(List.of(), 0);
    }
}

record ProductSummary(String id, String name) {}

record ProductSearchResponse(List<ProductSummary> items, int count) {}
~~~

Ví dụ giới hạn limit ở cả validation runtime và mô tả tham số. Việc ghi giới hạn trong description hoặc schema không thay thế validation. Server phải từ chối đầu vào vượt giới hạn ngay cả khi client bỏ qua OpenAPI document.

Các annotation Jakarta Validation cần provider runtime, thường được cung cấp bằng dependency spring-boot-starter-validation. Với tham số method như q và limit, @Validated bật method validation qua proxy trong các cấu hình sử dụng AOP method validation; kiểm tra cơ chế validation của phiên bản Spring MVC đang chạy. Với request body, @Valid kích hoạt validation của object sau khi deserialize.

Response nên dùng DTO có trường được phép công bố. Không trả trực tiếp entity persistence nếu entity chứa thông tin nội bộ, quan hệ lazy hoặc trường không dành cho bên gọi công cụ.

## 7. Mô tả operation có tác động ghi

Nếu tool caller cần tạo đơn hàng, mô tả rõ tác động và dùng scope riêng:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ToolOrderController {

    @PostMapping("/api/tools/orders")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createOrder",
        summary = "Tạo đơn hàng",
        description = """
            Tạo một đơn hàng mới và làm thay đổi trạng thái nghiệp vụ.
            Chỉ gọi khi người dùng đã yêu cầu tạo đơn và xác nhận nội dung.
            Không tự động retry nếu chưa xác định request trước đã được xử lý hay chưa.
            """,
        tags = {"Tool orders"},
        security = @SecurityRequirement(
            name = "toolOAuth",
            scopes = {"orders.write"}
        )
    )
    OrderCreatedResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        // Xác thực quyền trên tài nguyên, kiểm tra nghiệp vụ và tạo đơn.
        return new OrderCreatedResponse("pending");
    }
}

record CreateOrderRequest(
    @NotBlank
    @Schema(description = "Mã sản phẩm được phép đặt")
    String productId,
    @Min(1)
    @Schema(description = "Số lượng lớn hơn 0")
    int quantity
) {}

record OrderCreatedResponse(String status) {}
~~~

Với thao tác ghi, hãy xem xét thêm idempotency key để xử lý retry an toàn, giới hạn số lượng, kiểm tra quyền trên từng tài nguyên, audit actor và correlation ID. Không nên để tool caller tự quyết định retry một request tạo đơn chỉ dựa trên timeout; timeout không chứng minh server chưa xử lý request.

## 8. Khai báo OAuth2 scope trong OpenAPI

OpenAPI nên mô tả quyền tối thiểu cần có cho từng operation. Ví dụ dùng OAuth2 client credentials cho tích hợp server-to-server:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "toolOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "catalog.read",
                    description = "Đọc catalog được phép công bố"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo đơn hàng"
                )
            }
        )
    )
)
class ToolCallerSecuritySchemeConfiguration {
}
~~~

Operation đọc khai báo catalog.read; operation ghi khai báo orders.write. Client chỉ nên được cấp scope cần thiết cho nhiệm vụ. Không cấp orders.write cho một integration chỉ cần tìm kiếm catalog.

@SecurityRequirement đưa yêu cầu bảo mật vào OpenAPI document. Nó không tự cấp scope, xác minh token hoặc cấu hình authorization trong Spring Security. Resource server phải kiểm tra chữ ký, issuer, audience, thời hạn và scope/authority theo chính sách của hệ thống.

## 9. Tách quyền tải document khỏi quyền gọi operation

Có hai quyết định bảo mật độc lập:

1. Ai được tải /v3/api-docs/tool-caller-v1 để khám phá hợp đồng?
2. Ai được gọi GET /api/tools/products hoặc POST /api/tools/orders?

Một hệ thống có thể cho phép registry nội bộ tải document bằng authority docs.export, trong khi tool runtime cần scope catalog.read hoặc orders.write. Không dùng quyền tải document làm quyền gọi API, và không giả định người tải được document sẽ được phép thực hiện operation.

Ví dụ các rule authorization cần tích hợp vào SecurityFilterChain của ứng dụng:

Đây là phần rule để ghép vào authorizeHttpRequests hiện có; cần import org.springframework.http.HttpMethod và giữ các rule khác của ứng dụng theo chính sách hiện tại.

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        HttpMethod.GET,
        "/v3/api-docs/tool-caller-v1",
        "/v3/api-docs/tool-caller-v1.yaml"
    ).hasAuthority("docs.export")
    .requestMatchers(
        HttpMethod.GET,
        "/api/tools/products"
    ).hasAuthority("SCOPE_catalog.read")
    .requestMatchers(
        HttpMethod.POST,
        "/api/tools/orders"
    ).hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
)
~~~

Đoạn trên là các rule minh họa để ghép vào security chain hiện có. Với Spring Security OAuth2 Resource Server mặc định, scope thường được ánh xạ thành authority có tiền tố SCOPE_. Nếu ứng dụng dùng converter tùy chỉnh hoặc gateway, hãy dùng tên authority thực tế. Bảo đảm matcher cho URL YAML cũng được bảo vệ như JSON.

Nếu Swagger UI cần tải swagger-config, hãy cấu hình endpoint đó theo chính sách của giao diện. Nếu tool registry tải trực tiếp OpenAPI JSON/YAML và không dùng Swagger UI, không cần mở giao diện chỉ để phục vụ việc khám phá.

## 10. Dùng vendor extension khi tool registry cần metadata riêng

Một số hệ thống tích hợp đọc thêm metadata không có trường chuẩn trong OpenAPI, ví dụ nhóm công cụ hoặc đánh dấu operation chỉ đọc. Có thể bổ sung vendor extension có tiền tố x-:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.extensions.Extension;
import io.swagger.v3.oas.annotations.extensions.ExtensionProperty;

@Operation(
    operationId = "searchProducts",
    summary = "Tìm sản phẩm",
    extensions = @Extension(
        name = "x-tool",
        properties = {
            @ExtensionProperty(name = "category", value = "catalog"),
            @ExtensionProperty(
                name = "readOnly",
                value = "true",
                parseValue = true
            )
        }
    )
)
~~~

Vendor extension là metadata mở rộng. OpenAPI cho phép extension theo quy ước x-, nhưng không có nghĩa mọi tool caller đều hiểu x-tool.category hoặc x-tool.readOnly. Chỉ thêm extension khi consumer đã thống nhất schema, kiểu dữ liệu và cách xử lý. Hãy kiểm tra output JSON thực tế để xác nhận boolean được serialize thành boolean chứ không phải chuỗi.

Extension không thay thế HTTP method, OAuth2 scope hoặc runtime authorization. Không đánh dấu một operation là readOnly chỉ vì metadata nói như vậy nếu handler thực tế có side effect.

## 11. Bảo vệ dữ liệu và giới hạn đầu vào

OpenAPI document giúp tool caller hiểu schema nhưng không tự thực thi validation. Với endpoint dành cho công cụ, hãy giới hạn:

- Độ dài chuỗi tìm kiếm và kích thước request body.
- Số phần tử trong mảng và số kết quả phân trang.
- Giá trị enum và format ID.
- Kích thước file nếu có upload.
- Phạm vi thời gian hoặc ngày được truy vấn.
- Số lượng tài nguyên có thể bị thay đổi trong một request.

Dùng Bean Validation như @NotBlank, @Size, @Min, @Max, @Pattern cùng validation nghiệp vụ ở service. Dùng DTO riêng cho request/response để tránh cho tool caller ghi vào field nội bộ như ownerId, approved, role hoặc trạng thái kiểm soát do server quản lý.

Không công bố:

- Endpoint actuator, debug, metrics nội bộ hoặc endpoint quản trị.
- Hostname, IP, port hoặc path nội bộ trong servers.
- Token, password, API key hoặc dữ liệu cá nhân trong example/default.
- Stack trace, SQL, thông tin triển khai hoặc chi tiết hạ tầng trong description.
- Operation nhận URL tùy ý để server tải nội dung nếu chưa có bảo vệ SSRF phù hợp.

Nếu cần ví dụ request/response, dùng dữ liệu giả lập không chứa thông tin thật. Kiểm tra cả example, default, description và servers trước khi publish document.

## 12. Kiểm tra tập operation được công bố

Nên có allowlist hợp đồng trong test để phát hiện endpoint mới vô tình lọt vào group. Với OpenAPI JSON, có thể đọc paths và kiểm tra từng method:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ToolCallerOpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    com.fasterxml.jackson.databind.ObjectMapper objectMapper;

    @Test
    @WithMockUser(authorities = "docs.export")
    void publishesOnlyApprovedOperations() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/v3/api-docs/tool-caller-v1")
            )
            .andExpect(status().isOk())
            .andReturn();

        JsonNode document = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );

        assertThat(operations(document)).containsExactlyInAnyOrder(
            "GET /api/tools/products",
            "POST /api/tools/orders"
        );
    }

    private static Set<String> operations(JsonNode document) {
        Set<String> result = new HashSet<>();
        JsonNode paths = document.path("paths");
        Iterator<String> pathNames = paths.fieldNames();
        Set<String> methods = Set.of(
            "get", "put", "post", "delete",
            "patch", "options", "head", "trace"
        );

        while (pathNames.hasNext()) {
            String path = pathNames.next();
            Iterator<String> keys = paths.path(path).fieldNames();
            while (keys.hasNext()) {
                String method = keys.next().toLowerCase(Locale.ROOT);
                if (methods.contains(method)) {
                    result.add(method.toUpperCase(Locale.ROOT) + " " + path);
                }
            }
        }
        return result;
    }
}
~~~

containsExactlyInAnyOrder xác nhận tập operation bằng đúng allowlist: thiếu operation hoặc có thêm operation đều làm test thất bại. Test dùng @WithMockUser(authorities = "docs.export") để vượt qua rule bảo vệ document; authority này chỉ phục vụ request tải OpenAPI, không phải scope của operation nghiệp vụ.

Để dùng @WithMockUser, thêm spring-security-test trong test scope nếu dependency management của dự án chưa cung cấp:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Kiểm tra YAML riêng trong cùng test class:

~~~java
@Test
@WithMockUser(authorities = "docs.export")
void exportsToolCallerYaml() throws Exception {
    mockMvc.perform(get("/v3/api-docs/tool-caller-v1.yaml"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("openapi:")));
}
~~~

Method này dùng lại mockMvc của test class và cần static import org.hamcrest.Matchers.containsString cùng MockMvcResultMatchers.content. Nếu security matcher chỉ bảo vệ JSON, test YAML sẽ phát hiện endpoint còn lại chưa được giới hạn.

Nếu group có path parameter, giữ nguyên template như /api/tools/products/{id} trong allowlist. Nếu ứng dụng dùng YAML làm artifact chính, kiểm tra riêng URL .yaml và parse bằng YAML parser; test JSON không chứng minh route YAML cũng hoạt động.

## 13. Kiểm tra quyền runtime riêng biệt

Ngoài test document, cần kiểm tra endpoint thật:

| Request | Kết quả mong đợi |
| --- | --- |
| Không token gọi GET /api/tools/products | 401 hoặc hành vi từ chối theo entry point. |
| Token thiếu catalog.read gọi GET /api/tools/products | 403. |
| Token có catalog.read gọi GET /api/tools/products | Được phép nếu dữ liệu và điều kiện nghiệp vụ hợp lệ. |
| Token chỉ có catalog.read gọi POST /api/tools/orders | 403. |
| Token có orders.write gọi POST /api/tools/orders | Được phép nếu request hợp lệ và quyền trên tài nguyên phù hợp. |

@WithMockUser hữu ích để kiểm tra authorization rule nhưng không xác minh JWT thật, issuer, audience hoặc claim mapping. Nếu dùng OAuth2 Resource Server, bổ sung test với JWT request post-processor và integration test cho token decoder theo yêu cầu bảo mật.

Đối với operation ghi, kiểm tra audit log, idempotency, giới hạn tốc độ và quyền sở hữu tài nguyên. Một token có scope orders.write không nên tự động cho phép tạo đơn cho mọi tenant hoặc customer; service phải kiểm tra phạm vi dữ liệu của principal.

## 14. Quy trình review trước khi publish

Trước khi đưa group cho tool registry hoặc bên tích hợp:

1. Xác nhận chủ sở hữu nghiệp vụ và mục đích của từng operation.
2. So sánh method/path thực tế với allowlist đã review.
3. Xác nhận group không chứa actuator, admin, debug hoặc endpoint nội bộ.
4. Kiểm tra operation ID duy nhất và ổn định.
5. Đọc lại description, request schema, response schema và lỗi có thể xảy ra.
6. Kiểm tra OAuth2 scope của từng operation và security scheme trong document.
7. Kiểm tra servers, example và default không lộ thông tin nội bộ hoặc bí mật.
8. Chạy contract test để phát hiện operation thừa/thiếu.
9. Chạy runtime authorization test cho anonymous, thiếu scope và đủ scope.
10. Xác nhận JSON/YAML được export đúng group và chỉ chia sẻ đến consumer được phép.
11. Ghi nhận phiên bản document và quy trình thu hồi nếu phạm vi công bố thay đổi.

Nếu một endpoint mới được thêm vào /api/tools/**, đừng để nó tự động trở thành công cụ được công bố chỉ vì path prefix khớp. Yêu cầu cập nhật allowlist, review bảo mật và test trước khi phát hành.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Group công cụ chứa quá nhiều endpoint | pathsToMatch quá rộng hoặc scan toàn bộ package | Tách package dành cho tool API và thêm allowlist method/path. |
| Endpoint admin biến mất khỏi mọi document | Dùng @Hidden trong khi vẫn cần tài liệu nội bộ | Dùng filter riêng của group tool thay vì ẩn toàn cục. |
| Endpoint bị ẩn nhưng vẫn gọi được | Nhầm @Hidden với authorization | Bảo vệ mapping bằng Spring Security/gateway và test runtime. |
| Endpoint mới tự xuất hiện trong tool document | Chỉ dùng path prefix, không có allowlist chính xác | So sánh operation set với manifest/test allowlist. |
| Tool caller không biết operation làm gì | summary, description hoặc operationId mơ hồ | Đặt operation ID ổn định và mô tả tác động, đầu vào, lỗi, retry. |
| Tool caller gọi được operation ghi ngoài ý muốn | Scope dùng chung hoặc runtime rule quá rộng | Tách scope đọc/ghi và kiểm tra authority tại service. |
| Document ghi yêu cầu OAuth2 nhưng API vẫn mở | Chỉ thêm @SecurityRequirement, chưa cấu hình runtime security | Cấu hình resource server và test token thật. |
| JSON bị bảo vệ nhưng YAML công khai | Matcher chỉ bao phủ URL JSON | Thêm matcher cho .yaml và kiểm tra cả hai. |
| Registry hiểu sai vendor extension | Consumer không có schema extension thống nhất | Thỏa thuận contract x-*, kiểm tra kiểu dữ liệu và version. |
| Document lộ hostname nội bộ | Server URL suy ra từ request nội bộ/proxy | Cấu hình servers công khai và kiểm tra forwarded headers. |
| Response chứa field nhạy cảm | Dùng entity trực tiếp hoặc DTO quá rộng | Dùng response DTO allowlist và test schema/response. |

## 16. Nguyên tắc áp dụng

- Tạo group riêng cho bên gọi công cụ, không tái sử dụng document toàn bộ API.
- Ưu tiên allowlist theo HTTP method và path; package/path prefix chỉ là lớp lọc ban đầu.
- Dùng @Hidden khi cần loại operation khỏi mọi document; dùng customizer riêng khi chỉ loại khỏi một group.
- Giữ operation ID ổn định và mô tả rõ tác động của operation.
- Ưu tiên operation chỉ đọc; operation ghi phải có scope, xác nhận nghiệp vụ, audit và kiểm soát retry.
- Mô tả OAuth2 scope trong OpenAPI và thực thi quyền tương ứng ở runtime.
- Tách quyền tải document khỏi quyền gọi endpoint nghiệp vụ.
- Chỉ thêm vendor extension x-* khi consumer đã thống nhất hợp đồng.
- Giới hạn đầu vào, phân trang, kích thước payload và dữ liệu trả về bằng validation runtime.
- Kiểm tra allowlist, JSON/YAML, security và servers trước khi publish.

Phạm vi endpoint dành cho bên gọi công cụ nên là một hợp đồng nhỏ, có chủ sở hữu và được kiểm soát bằng allowlist. GroupedOpenApi tạo document riêng; OpenApiCustomizer có thể thu hẹp operation theo method/path; metadata OpenAPI mô tả operation và scope để consumer hiểu cách sử dụng. Các lớp này chỉ quyết định nội dung được công bố. Spring Security, gateway và service vẫn phải xác thực, phân quyền, giới hạn tốc độ, ghi audit và kiểm tra dữ liệu ở mỗi request. Khi contract test xác nhận chính xác tập operation và runtime test xác nhận quyền truy cập, group công cụ mới có thể được chia sẻ an toàn cho bên tích hợp.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Multiple OpenAPI Definitions và GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Customizers](https://springdoc.org/)
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
