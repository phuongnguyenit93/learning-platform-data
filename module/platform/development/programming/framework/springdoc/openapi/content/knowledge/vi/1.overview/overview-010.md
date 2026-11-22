# Lộ trình học từ API đầu tiên đến kiểm chứng và phát hành hợp đồng

Một API Spring Boot có thể chạy đúng nhưng vẫn khó tích hợp nếu người dùng không biết endpoint nào tồn tại, gửi dữ liệu theo cấu trúc nào, nhận được những mã trạng thái nào và phải xác thực ra sao. **Hợp đồng API** giải quyết vấn đề đó bằng một mô tả có cấu trúc, có thể đọc bằng máy và dùng chung giữa nhóm phát triển, kiểm thử, vận hành và các nhóm tích hợp.

Trong hệ sinh thái Spring, **springdoc-openapi** phân tích các endpoint Spring MVC hoặc Spring WebFlux cùng thông tin chú thích để tạo đặc tả OpenAPI. Công cụ có thể cung cấp đặc tả JSON/YAML và giao diện Swagger UI để con người khám phá, thử gọi API. Lộ trình dưới đây đi từ một controller đơn giản đến việc kiểm chứng, quản lý phiên bản và phân phối hợp đồng trong quy trình phát hành.

## Kết quả cần đạt

Sau khi hoàn thành lộ trình, bạn có thể:

- Tích hợp springdoc-openapi đúng với phiên bản Spring Boot và loại ứng dụng web đang dùng.
- Đọc và tùy biến tài liệu OpenAPI được sinh từ controller, DTO và các annotation.
- Mô tả rõ request, response, lỗi, schema, ví dụ và cơ chế bảo mật.
- Chia tài liệu theo nhóm API, tùy chỉnh metadata và xuất tài liệu ở dạng JSON hoặc YAML.
- Kiểm tra tài liệu có hợp lệ và có phản ánh đúng hành vi API hay không.
- Quản lý phiên bản hợp đồng và đưa tài liệu đã kiểm chứng vào quy trình phát hành.

## Bản đồ lộ trình

~~~mermaid
flowchart TD
    A["API Spring Boot đầu tiên"] --> B["Tích hợp springdoc-openapi"]
    B --> C["Sinh OpenAPI và mở Swagger UI"]
    C --> D["Mô tả request, response và schema"]
    D --> E["Bổ sung lỗi và bảo mật"]
    E --> F["Nhóm và tùy biến tài liệu"]
    F --> G["Xuất JSON/YAML"]
    G --> H["Kiểm tra tính hợp lệ và độ khớp"]
    H --> I["Quản lý phiên bản và phát hành"]
~~~

Mỗi giai đoạn nên tạo ra một sản phẩm có thể kiểm tra được. Không nên bắt đầu bằng việc thêm thật nhiều annotation: trước hết hãy hiểu tài liệu được sinh từ đâu, sau đó bổ sung mô tả ở những chỗ mà mã nguồn chưa thể diễn đạt đầy đủ ý nghĩa của hợp đồng.

## 1. Bắt đầu với một API Spring Boot

Hãy chọn một ứng dụng REST nhỏ có ít nhất một endpoint đọc dữ liệu và một endpoint nhận dữ liệu. Ví dụ, một API quản lý sản phẩm có thể cung cấp:

| Phương thức | Đường dẫn | Mục đích |
|---|---|---|
| GET | /api/products/{id} | Lấy một sản phẩm |
| GET | /api/products | Tìm kiếm hoặc liệt kê sản phẩm |
| POST | /api/products | Tạo sản phẩm |

Trước khi tích hợp springdoc-openapi, cần hiểu các thành phần Spring cơ bản:

- Controller khai báo các điểm vào HTTP bằng những annotation như @RestController, @RequestMapping, @GetMapping và @PostMapping.
- DTO định nghĩa cấu trúc dữ liệu vào và ra. DTO giúp hợp đồng API ổn định hơn so với việc phơi bày trực tiếp entity của cơ sở dữ liệu.
- Bean Validation diễn đạt các ràng buộc dữ liệu như bắt buộc, độ dài, định dạng email hoặc giá trị tối thiểu.
- Cấu hình bảo mật quyết định endpoint nào cần xác thực và quyền nào được phép truy cập.

Hãy chạy thử API bằng HTTP client hoặc test tích hợp trước. Khi đã biết hành vi thực tế, bạn sẽ có cơ sở để đối chiếu tài liệu được sinh ra.

## 2. Tích hợp springdoc-openapi

Chọn starter theo mô hình ứng dụng:

| Ứng dụng | Starter thường dùng |
|---|---|
| Spring MVC | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | springdoc-openapi-starter-webflux-ui |

Với Spring Boot 3 và Maven, dependency MVC có thể được khai báo như sau. Thay giá trị thuộc tính phiên bản bằng phiên bản springdoc tương thích với phiên bản Spring Boot của dự án theo bảng tương thích của springdoc-openapi.

~~~xml
<properties>
    <springdoc.version>YOUR_COMPATIBLE_VERSION</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Ứng dụng WebFlux dùng starter WebFlux tương ứng. Không thêm đồng thời cả hai starter chỉ để thử nghiệm; hãy dùng starter khớp với stack web của ứng dụng. Với dự án Spring Boot 2 hoặc dự án đang dùng dòng springdoc cũ, tên artifact và cách cấu hình có thể khác. Luôn đối chiếu hướng dẫn di trú và ma trận tương thích của đúng major version trước khi nâng cấp.

Khởi động ứng dụng và kiểm tra các địa chỉ mặc định:

| Tài nguyên | Địa chỉ mặc định |
|---|---|
| Đặc tả OpenAPI dạng JSON | /v3/api-docs |
| Đặc tả OpenAPI dạng YAML | /v3/api-docs.yaml |
| Swagger UI | /swagger-ui.html |

Đường dẫn có thể được đổi bằng cấu hình. Ví dụ:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /docs
~~~

Khi thay đổi đường dẫn, hãy kiểm tra lại cả endpoint JSON/YAML lẫn trang Swagger UI. Đừng giả định rằng giao diện và endpoint đặc tả luôn dùng cùng một URL.

Ở bước này, tài liệu đã được sinh tự động từ controller. Đây là điểm khởi đầu tốt, nhưng chưa chắc đã là hợp đồng đủ rõ: tên tham số, ý nghĩa nghiệp vụ, ví dụ và các trường hợp lỗi thường cần được mô tả thêm.

## 3. Hiểu OpenAPI và Swagger UI

OpenAPI là định dạng đặc tả mô tả một HTTP API. Tài liệu thường chứa các nhóm thông tin:

- **info**: tên, mô tả và phiên bản của API.
- **servers**: các địa chỉ máy chủ mà client có thể gọi.
- **paths**: đường dẫn và các thao tác HTTP.
- **parameters**: tham số trên path, query, header hoặc cookie.
- **requestBody**: cấu trúc dữ liệu gửi lên.
- **responses**: các phản hồi có thể nhận được.
- **components**: schema, security scheme và các thành phần dùng lại.

springdoc-openapi đảm nhiệm việc tạo đặc tả từ ứng dụng Spring. Swagger UI đọc đặc tả đó và hiển thị thành giao diện tương tác. Hai khái niệm có liên quan nhưng không đồng nghĩa: có thể xuất bản file OpenAPI cho công cụ khác sử dụng mà không cần xuất bản Swagger UI.

Một tài liệu OpenAPI tốt cho phép người tích hợp trả lời nhanh các câu hỏi: gọi URL nào, dùng phương thức nào, trường nào bắt buộc, dữ liệu có định dạng gì, thành công và thất bại trả về ra sao, cần gửi thông tin xác thực nào.

## 4. Mô tả thao tác, request và response

Springdoc có thể suy ra nhiều thông tin từ chữ ký controller và kiểu dữ liệu Java. Dùng annotation của OpenAPI để bổ sung ngữ nghĩa mà mã nguồn chưa thể hiện.

Ví dụ DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

@Schema(description = "Thông tin cần có để tạo sản phẩm")
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Tên sản phẩm", example = "Bàn phím cơ")
    String name,

    @Positive
    @Schema(description = "Giá bán, tính theo đơn vị tiền tệ của cửa hàng",
            example = "1250000")
    long price
) {}
~~~

Ví dụ controller:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Quản lý sản phẩm")
public class ProductController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Lấy sản phẩm theo mã",
        description = "Trả về thông tin sản phẩm nếu mã tồn tại."
    )
    @ApiResponse(responseCode = "200", description = "Tìm thấy sản phẩm")
    @ApiResponse(responseCode = "404", description = "Không tìm thấy sản phẩm")
    public ProductResponse getById(
        @Parameter(description = "Mã sản phẩm", example = "42")
        @PathVariable long id
    ) {
        // Gọi service và trả về DTO.
        return productService.getById(id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Tạo sản phẩm mới")
    @ApiResponse(responseCode = "201", description = "Tạo thành công")
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu đầu vào không hợp lệ",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    )
    public ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
~~~

Đoạn mã minh họa cách mô tả; cần thay ProductResponse, ApiError và productService bằng kiểu dữ liệu, service thực tế của ứng dụng.

Khi viết mô tả, hãy chú ý:

1. **Path parameter** xác định tài nguyên cụ thể, thường là một phần của URL. Ví dụ: id trong /api/products/{id}.
2. **Query parameter** thường dùng để lọc, phân trang hoặc sắp xếp. Nêu rõ giá trị mặc định, miền giá trị và cách kết hợp bộ lọc.
3. **Header parameter** dùng cho thông tin điều khiển hoặc ngữ cảnh của request. Không mô tả token bí mật như một tham số thông thường; hãy khai báo security scheme.
4. **Request body** cần chỉ ra schema, trường bắt buộc, giới hạn và ví dụ hợp lệ.
5. **Response** cần mô tả mã HTTP, schema trả về và điều kiện phát sinh.

Các annotation thường gặp:

| Annotation | Vai trò |
|---|---|
| @Tag | Nhóm các thao tác liên quan trong tài liệu |
| @Operation | Mô tả một thao tác API |
| @Parameter | Bổ sung thông tin cho tham số |
| @ApiResponse và @ApiResponses | Mô tả các phản hồi |
| @Schema | Mô tả schema hoặc thuộc tính |
| @ExampleObject | Cung cấp ví dụ request/response |
| @io.swagger.v3.oas.annotations.parameters.RequestBody | Mô tả nội dung request trong OpenAPI; khác với @RequestBody của Spring dùng để binding dữ liệu HTTP |

Các annotation của Spring quyết định cách ứng dụng nhận và xử lý request. Annotation OpenAPI bổ sung mô tả cho hợp đồng. Không nên nhầm hai vai trò này, cũng không nên lặp lại annotation khi springdoc đã suy ra thông tin chính xác từ mã nguồn.

## 5. Mô tả schema và quy tắc dữ liệu

Schema là nền tảng để client biết cấu trúc dữ liệu. Một schema rõ ràng nên trả lời được:

- Thuộc tính có kiểu dữ liệu nào: string, integer, number, boolean, array hay object?
- Thuộc tính có bắt buộc hay không?
- Giá trị có giới hạn độ dài, miền số hoặc định dạng nào?
- Enum có những giá trị hợp lệ nào?
- Thuộc tính có ý nghĩa nghiệp vụ gì và ví dụ điển hình là gì?

Hãy ưu tiên DTO riêng cho request và response. Chẳng hạn, request tạo sản phẩm không cần chứa id do máy chủ sinh; response có thể bổ sung id, thời điểm tạo và trạng thái. Việc dùng chung một entity cho mọi chiều dữ liệu dễ làm lộ trường nội bộ hoặc khiến hợp đồng thay đổi ngoài ý muốn khi cấu trúc lưu trữ thay đổi.

Bean Validation như @NotNull, @NotBlank, @Size, @Min, @Max và @Email có thể cung cấp thêm thông tin cho schema. Tuy vậy, cần kiểm tra đặc tả được sinh ra để chắc chắn các ràng buộc đã xuất hiện đúng như mong đợi. Quy tắc nghiệp vụ phức tạp trong service thường không thể tự suy ra từ kiểu Java hoặc validation annotation; hãy mô tả chúng bằng nội dung và ví dụ.

Đối với kiểu dữ liệu đặc biệt, hãy kiểm tra định dạng trong OpenAPI, múi giờ của ngày giờ, độ chính xác của số thập phân và cách biểu diễn giá trị null. Ví dụ, một trường thời gian nên thống nhất dùng ISO 8601 và quy định rõ có mang offset hoặc ký hiệu UTC hay không.

## 6. Chuẩn hóa lỗi và mô tả bảo mật

Một hợp đồng chỉ mô tả phản hồi thành công sẽ khiến client khó xử lý tình huống thực tế. Hãy lập danh sách lỗi có thể xảy ra cho từng thao tác, chẳng hạn:

| Mã HTTP | Ý nghĩa thường gặp | Thông tin cần mô tả |
|---|---|---|
| 400 | Request sai định dạng hoặc vi phạm validation | Trường lỗi và thông điệp |
| 401 | Chưa xác thực hoặc thông tin xác thực không hợp lệ | Cách cung cấp thông tin xác thực |
| 403 | Đã xác thực nhưng không đủ quyền | Điều kiện quyền truy cập |
| 404 | Không tìm thấy tài nguyên | Tài nguyên hoặc mã định danh liên quan |
| 409 | Xung đột trạng thái hoặc dữ liệu | Điều kiện gây xung đột |
| 500 | Lỗi máy chủ ngoài dự kiến | Mã tham chiếu hỗ trợ, không làm lộ chi tiết nội bộ |

Nếu ứng dụng dùng một cấu trúc lỗi chung, hãy mô tả schema đó và tái sử dụng trong các response. Có thể dùng @ApiResponse tại từng thao tác hoặc các cơ chế tùy biến OpenAPI để bổ sung phản hồi dùng chung. Việc có @ControllerAdvice không tự động đảm bảo mọi response lỗi đều được mô tả đầy đủ trong hợp đồng; hãy kiểm tra tài liệu sau khi cấu hình xử lý lỗi.

Với API dùng bearer token, khai báo security scheme trong OpenAPI để Swagger UI và client hiểu cách xác thực:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@SecurityRequirement(name = "bearerAuth")
public class OpenApiSecurityConfig {
}
~~~

Có thể đặt @SecurityRequirement ở cấp lớp hoặc thao tác tùy theo phạm vi cần bảo vệ trong tài liệu. Với OAuth2 hoặc OpenID Connect, cần khai báo flow và các scope tương ứng thay vì mô tả chung chung là “dùng token”.

Security scheme chỉ mô tả cách client xác thực. Nó **không bật bảo mật cho endpoint**, không thay thế Spring Security và không cấp quyền truy cập. Quy tắc thực thi vẫn phải được cấu hình và kiểm thử trong ứng dụng.

## 7. Tùy biến metadata và chia nhóm tài liệu

Metadata giúp người dùng nhận diện đúng hợp đồng. Có thể khai báo bằng @OpenAPIDefinition hoặc tạo bean OpenAPI:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI productApi() {
        return new OpenAPI().info(new Info()
            .title("Product API")
            .description("API quản lý danh mục và sản phẩm")
            .version("1.0.0")
            .contact(new Contact()
                .name("API Support")
                .email("api-support@example.com")));
    }
}
~~~

Thay thông tin liên hệ minh họa bằng địa chỉ hỗ trợ thật của tổ chức trước khi phát hành. Phiên bản trong info.version là phiên bản hợp đồng API do nhóm dự án quản lý; nó khác với phiên bản đặc tả OpenAPI nằm ở trường openapi của tài liệu được sinh ra.

Khi ứng dụng có nhiều nhóm endpoint, hãy chia tài liệu bằng GroupedOpenApi. Ví dụ sau minh họa ý tưởng cấu hình một nhóm public:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .build();
    }
}
~~~

Package của GroupedOpenApi có thể khác giữa các major version springdoc; hãy dùng import tương ứng với phiên bản dự án. Có thể tạo các nhóm riêng cho public, internal hoặc admin, kết hợp pathsToMatch, packagesToScan và các bộ lọc phù hợp. Đặc tả của một nhóm thường có dạng /v3/api-docs/{group}, ví dụ /v3/api-docs/public.

Chia nhóm giúp người đọc tìm đúng phạm vi API và cho phép phân phối tài liệu theo đối tượng. Tuy nhiên, việc ẩn một nhóm khỏi Swagger UI không phải là biện pháp bảo mật. Nếu tài liệu nội bộ không được phép truy cập công khai, hãy kiểm soát endpoint tài liệu bằng cấu hình bảo mật hoặc tắt chúng ở môi trường cần thiết.

## 8. Xuất và phân phối JSON/YAML

OpenAPI JSON phù hợp cho các công cụ xử lý tự động; YAML thường thuận tiện cho việc đọc và review trong pull request. Có thể tải trực tiếp từ endpoint:

~~~bash
curl -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs \
  -o openapi.json

curl -H "Accept: application/yaml" \
  http://localhost:8080/v3/api-docs.yaml \
  -o openapi.yaml
~~~

Nếu dự án có nhóm tài liệu, hãy xuất đúng endpoint của từng nhóm. Trong CI, nên lưu file đặc tả như một build artifact có gắn mã commit hoặc phiên bản phát hành. Điều này giúp truy vết chính xác hợp đồng đã được kiểm tra và gửi cho đối tác.

Một quy trình phân phối thường gồm: khởi động ứng dụng hoặc môi trường sinh tài liệu, tải OpenAPI, kiểm tra định dạng, lưu artifact, sau đó xuất bản lên cổng tài liệu hoặc nơi lưu trữ đã được phê duyệt. Không đưa token, mật khẩu, dữ liệu khách hàng hoặc địa chỉ máy chủ nội bộ vào ví dụ công khai.

Trong môi trường production, hãy quyết định rõ ai được xem đặc tả và Swagger UI. Nếu không cần cung cấp tài liệu trực tiếp từ ứng dụng, có thể tắt các endpoint bằng cấu hình:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Một lựa chọn khác là chỉ bật tài liệu trong môi trường phát triển hoặc staging, hoặc đặt endpoint tài liệu sau cơ chế xác thực. Cách làm cụ thể phụ thuộc chính sách phát hành của hệ thống.

## 9. Kiểm chứng hợp đồng trước khi phát hành

Việc endpoint /v3/api-docs trả về HTTP 200 chỉ chứng minh tài liệu có thể được tạo và truy cập. Nó chưa chứng minh tài liệu hợp lệ, đầy đủ hoặc khớp với hành vi thật của API.

Nên kiểm tra theo nhiều lớp:

1. **Kiểm tra khả năng sinh tài liệu:** gọi endpoint JSON/YAML trong môi trường kiểm thử và xác nhận nội dung không rỗng.
2. **Kiểm tra cấu trúc:** dùng OpenAPI validator hoặc linter để phát hiện tài liệu sai cấu trúc, tham chiếu schema không tồn tại và quy ước mô tả chưa đạt.
3. **Kiểm tra nội dung:** xác nhận các path, HTTP method, request body, response, mã lỗi, security requirement và ví dụ quan trọng đều có mặt.
4. **Kiểm tra hành vi:** gửi request thực tế cho các trường hợp thành công, dữ liệu sai, thiếu xác thực, thiếu quyền và không tìm thấy tài nguyên; đối chiếu status code cùng schema trả về với hợp đồng.
5. **Kiểm tra thay đổi:** so sánh đặc tả mới với bản đã phát hành để nhận diện thay đổi có thể phá vỡ client.

Ví dụ, nếu OpenAPI khai báo POST /api/products trả về 201 với ProductResponse nhưng ứng dụng thực tế trả về 200 hoặc trả về một cấu trúc khác, hợp đồng và triển khai đang lệch nhau. Tương tự, nếu tài liệu đánh dấu một trường là tùy chọn nhưng server từ chối khi trường đó bị bỏ qua, client sẽ được hướng dẫn sai.

Các tình huống kiểm thử tối thiểu cho endpoint tạo sản phẩm:

| Trường hợp | Kết quả cần đối chiếu |
|---|---|
| Request hợp lệ | Mã 201 và schema ProductResponse |
| Thiếu tên sản phẩm | Mã lỗi validation và schema ApiError |
| Giá trị giá không hợp lệ | Mã lỗi và thông điệp theo quy ước |
| Không có token | Mã 401 nếu endpoint yêu cầu xác thực |
| Token không đủ quyền | Mã 403 nếu chính sách áp dụng |

Đưa các kiểm tra này vào CI để lỗi hợp đồng được phát hiện trước khi phát hành. Với hệ thống có nhiều client hoặc đối tác, có thể bổ sung contract test giữa provider và consumer để kiểm tra các giả định tích hợp quan trọng.

## 10. Quản lý phiên bản và thay đổi tương thích

Phiên bản API và phiên bản đặc tả OpenAPI là hai khái niệm khác nhau:

- Phiên bản đặc tả, ví dụ OpenAPI 3.x, cho biết tài liệu tuân theo phiên bản định dạng nào.
- Phiên bản API, thường đặt trong info.version, cho biết hợp đồng của sản phẩm đang được phát hành ở phiên bản nào.

Hãy xác định chiến lược versioning nhất quán, chẳng hạn dùng đường dẫn /api/v1 và /api/v2, hoặc một cơ chế versioning khác đã được thống nhất trong hệ thống. Tạo nhóm tài liệu tương ứng để người dùng có thể tra cứu đúng hợp đồng. Không tăng phiên bản chỉ vì một thay đổi nội bộ không ảnh hưởng đến client; ngược lại, thay đổi có thể phá vỡ tương thích cần được đánh giá và truyền thông trước.

Những thay đổi thường cần xem xét kỹ gồm xóa hoặc đổi tên field, đổi kiểu dữ liệu, làm một field tùy chọn thành bắt buộc, xóa response code, thay đổi ý nghĩa enum, thay đổi cơ chế xác thực hoặc thay đổi định dạng lỗi. Thêm một field response có thể tương thích với nhiều client nhưng vẫn có thể ảnh hưởng đến client xử lý dữ liệu quá nghiêm ngặt; hãy đánh giá theo quy ước của hệ sinh thái client thực tế.

Lưu bản OpenAPI đã phát hành cùng mã nguồn hoặc build artifact tương ứng. Khi cần điều tra sự cố, nhóm có thể xác định client đã tích hợp theo hợp đồng nào thay vì dựa vào tài liệu đang thay đổi trên môi trường chạy.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có /v3/api-docs | Thiếu starter, sai loại starter hoặc cấu hình đã tắt | Kiểm tra dependency, log khởi động và cấu hình springdoc |
| Swagger UI không tải được | Sai đường dẫn, context path hoặc proxy rewrite | Mở endpoint OpenAPI trực tiếp rồi kiểm tra URL giao diện |
| Thiếu endpoint trong tài liệu | Bộ lọc group, package scan hoặc điều kiện bean | Kiểm tra pathsToMatch, packagesToScan và mapping thực tế |
| Schema thiếu ràng buộc | DTO không có metadata hoặc validation không được nhận diện như mong đợi | Kiểm tra JSON sinh ra và bổ sung @Schema khi cần |
| Response lỗi không xuất hiện | Chưa khai báo response hoặc chưa cấu hình mô tả dùng chung | Bổ sung @ApiResponse hay OpenApiCustomizer |
| Nút Authorize không hoạt động như kỳ vọng | Security scheme khai báo sai hoặc phạm vi requirement chưa đúng | Kiểm tra components.securitySchemes và security của operation |
| Tài liệu hoạt động ở local nhưng lỗi sau deploy | Context path, reverse proxy, HTTPS hoặc cấu hình môi trường khác nhau | Kiểm tra URL public, forwarded headers và cấu hình theo môi trường |

Khi xử lý lỗi, hãy lấy tài liệu JSON làm nguồn kiểm tra đầu tiên. Swagger UI chỉ là cách trình bày; nếu nội dung JSON đã sai thì việc chỉnh giao diện sẽ không sửa được hợp đồng.

## 12. Bài thực hành tổng hợp

Từ một ứng dụng Spring Boot có ProductController, hãy hoàn thành các đầu việc sau:

1. Thêm starter springdoc phù hợp với Spring MVC hoặc WebFlux.
2. Mở JSON, YAML và Swagger UI; lưu lại một bản OpenAPI ban đầu.
3. Bổ sung mô tả cho thao tác lấy sản phẩm, tìm kiếm và tạo sản phẩm.
4. Tách DTO request/response, khai báo validation, ví dụ và schema.
5. Mô tả các response thành công và lỗi; thống nhất schema lỗi.
6. Khai báo bearer authentication nếu API thực sự sử dụng JWT.
7. Tạo ít nhất một nhóm tài liệu và xác nhận endpoint nhóm hoạt động.
8. Xuất JSON/YAML, chạy validator và viết kiểm tra cho các trường hợp request chính.
9. So sánh đặc tả với hành vi thực tế, sửa các điểm không khớp.
10. Lưu artifact có mã phiên bản và đưa bước kiểm tra vào CI.

### Tiêu chí hoàn thành

- [ ] Mọi endpoint được đưa vào phạm vi tài liệu đều xuất hiện đúng path và HTTP method.
- [ ] Request và response dùng schema có tên, kiểu dữ liệu và ví dụ dễ hiểu.
- [ ] Trường bắt buộc, ràng buộc validation và giá trị enum được mô tả chính xác.
- [ ] Các mã lỗi quan trọng có response schema và điều kiện phát sinh.
- [ ] Security scheme và security requirement phản ánh đúng chính sách xác thực.
- [ ] JSON/YAML vượt qua công cụ kiểm tra OpenAPI đã chọn.
- [ ] Kiểm thử thực tế xác nhận hợp đồng khớp với status code và payload của API.
- [ ] Artifact phát hành được gắn phiên bản và có thể truy xuất lại.
- [ ] Quyền truy cập tài liệu production phù hợp chính sách của hệ thống.

## Tiếp tục học

Sau bài tổng quan này, hãy đi sâu theo từng nhóm kỹ năng: annotation và schema cho request/response; xử lý lỗi và security scheme; GroupedOpenApi cùng các customizer; xuất tài liệu và tích hợp CI; kiểm thử tương thích và quản lý thay đổi hợp đồng. Khi học từng chủ đề, luôn đối chiếu ba thứ: mã controller/DTO, tài liệu OpenAPI được sinh ra và phản hồi HTTP thực tế. Sự nhất quán giữa ba thứ đó là dấu hiệu quan trọng nhất cho thấy hợp đồng API có thể được tin cậy và sử dụng để tích hợp.
