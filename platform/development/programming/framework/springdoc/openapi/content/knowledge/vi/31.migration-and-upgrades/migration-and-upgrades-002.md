# Chuyển cấu hình Docket của Springfox sang GroupedOpenApi khi phù hợp

Khi chuyển một ứng dụng Spring Boot từ Springfox sang springdoc-openapi, không nên thay từng dòng cấu hình Docket bằng một dòng GroupedOpenApi theo kiểu máy móc. Docket của Springfox gom nhiều trách nhiệm vào một đối tượng: chọn controller và path, đặt tên nhóm, khai báo API metadata, security, tham số và response dùng chung. GroupedOpenApi của springdoc chủ yếu mô tả một nhóm endpoint cần xuất thành một OpenAPI document. Metadata chung, security scheme và các tùy biến khác được cấu hình bằng OpenAPI bean, annotation hoặc customizer riêng.

Tài liệu migration chính thức của springdoc đưa ra một phân biệt quan trọng: nếu ứng dụng chỉ có một Docket, hãy bỏ bean đó và chuyển bộ lọc package/path sang properties; chỉ khi có nhiều Docket cần tạo nhiều document riêng mới thay chúng bằng các GroupedOpenApi bean. API metadata như title, description, version và license được chuyển sang bean OpenAPI.

Bài này trình bày cách kiểm kê Docket hiện tại, chọn cách thay thế phù hợp, ánh xạ selector và annotation Swagger 2 sang OpenAPI 3, chuyển security và cấu hình toàn cục, rồi xác minh tài liệu mới trước khi gỡ Springfox hoàn toàn.

## 1. Docket đang làm những việc gì?

Một Docket thường có các phần:

- DocumentationType: chọn định dạng Swagger 2 hoặc OpenAPI 3 mà Springfox tạo.
- select, apis và paths: chọn controller, method và URL được đưa vào tài liệu.
- groupName: tên nhóm tài liệu.
- apiInfo: title, description, version, contact và license.
- securitySchemes và securityContexts: khai báo cơ chế xác thực và operation được bảo vệ.
- globalRequestParameters hoặc globalOperationParameters: tham số mặc định cho nhiều operation.
- globalResponses: response mặc định theo HTTP method.
- ignoredParameterTypes, alternateTypeRules và directModelSubstitute: điều chỉnh cách Springfox nhận diện parameter và model.
- host, protocols, pathMapping hoặc PathProvider: điều chỉnh URL public được mô tả.

Không phải tất cả phần trên đều thuộc trách nhiệm của GroupedOpenApi. Trước khi chuyển, hãy lập bảng cấu hình Docket hiện tại và xác định mục tiêu tương ứng trong springdoc.

## 2. Phân biệt một Docket và nhiều Docket

Đây là quyết định đầu tiên của migration.

| Cấu hình Springfox hiện tại | Hướng chuyển phù hợp |
| --- | --- |
| Không có Docket, dùng cấu hình mặc định | Thêm springdoc starter; không cần GroupedOpenApi |
| Một Docket chỉ lọc package/path | Bỏ Docket, dùng springdoc.packages-to-scan và springdoc.paths-to-match |
| Một Docket chủ yếu đặt apiInfo | Bỏ Docket, tạo bean OpenAPI |
| Một Docket vừa lọc API vừa đặt metadata | Dùng properties cho bộ lọc và OpenAPI bean cho metadata |
| Nhiều Docket tạo nhiều tài liệu riêng | Tạo một GroupedOpenApi cho mỗi nhóm |
| Nhiều Docket có selector khác nhau nhưng cùng metadata | GroupedOpenApi cho selector; OpenAPI bean cho metadata dùng chung |
| Docket có security hoặc global parameter phức tạp | Tách sang OpenAPI security, annotation và customizer |

Ví dụ, nếu ứng dụng chỉ có một Docket để loại các controller nội bộ khỏi Swagger, việc tạo một GroupedOpenApi duy nhất thường không cần thiết. Properties của springdoc đủ để giới hạn tài liệu mặc định.

Nếu ứng dụng có hai Docket là public và admin, mỗi Docket tạo một tài liệu độc lập với tập operation riêng, GroupedOpenApi là lựa chọn phù hợp.

## 3. Chọn phiên bản springdoc theo Spring Boot

Trước khi sửa code, xác định Spring Boot version và chọn đúng major version springdoc. Không dùng một version springdoc cho tất cả các dòng Boot.

| Spring Boot | Dòng springdoc phù hợp | Ghi chú |
| --- | --- | --- |
| 4.1.x | 3.1.x đến 3.2.x | Theo compatibility matrix hiện hành |
| 4.0.x | 3.0.x | Dùng springdoc 3.x |
| 3.5.x | 2.8.x đến 2.10.x | Dùng tài liệu springdoc v2 |
| 3.4.x | 2.7.x đến 2.8.x | Dùng tài liệu springdoc v2 |
| 3.3.x | 2.6.x | Dùng tài liệu springdoc v2 |
| 3.2.x | 2.3.x đến 2.5.x | Dùng tài liệu springdoc v2 |
| 3.1.x | 2.2.x | Dùng tài liệu springdoc v2 |
| 3.0.x | 2.0.x đến 2.1.x | Dùng tài liệu springdoc v2 |
| Spring Boot 2.x hoặc 1.x | springdoc 1.8.0 là dòng open-source cuối | Đây là dòng legacy |

Nếu nâng Spring Boot 2 lên Boot 3, cần xử lý cả chuyển đổi Java EE sang Jakarta EE, chẳng hạn javax.validation thành jakarta.validation và javax.servlet thành jakarta.servlet. Không chỉ đổi dependency springdoc rồi kỳ vọng toàn bộ thư viện cũ tự tương thích.

## 4. Thay dependency Springfox

Với ứng dụng Spring MVC cần cả OpenAPI endpoint và Swagger UI, dependency thường dùng là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Version 3.2.0 trong ví dụ dành cho Spring Boot 4.1.x theo ma trận hiện hành. Nếu ứng dụng dùng Spring Boot 3.x, chọn version 2.x tương ứng; không chép nguyên version này vào dự án Boot 3.

Nếu chỉ cần JSON/YAML document và không cần giao diện Swagger UI, có thể dùng starter API:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Với Spring WebFlux, dùng starter tương ứng:

| Web stack | Có Swagger UI | Chỉ có API document |
| --- | --- | --- |
| Spring MVC | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-api |
| Spring WebFlux | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-api |

Gỡ các dependency Springfox đã dùng, chẳng hạn springfox-swagger2, springfox-swagger-ui, springfox-boot-starter, springfox-data-rest và các module springfox khác. Gỡ cả dependency Swagger 2 annotation cũ nếu nó được khai báo riêng. Các annotation OpenAPI 3 được cung cấp qua starter springdoc.

Không giữ đồng thời Springfox và springdoc chỉ để “chạy song song” lâu dài trong cùng một ApplicationContext. Hai thư viện có thể cùng đăng ký handler, converter hoặc tài nguyên UI, dẫn đến endpoint trùng, tài liệu khác nhau hoặc lỗi khởi động. Nếu cần so sánh trong giai đoạn migration, hãy dùng branch hoặc profile kiểm thử tách biệt, rồi gỡ Springfox sau khi xác minh.

## 5. Bỏ annotation kích hoạt Springfox

Các annotation như @EnableSwagger2 hoặc @EnableSwagger2WebMvc thuộc Springfox. Khi chuyển sang springdoc, xóa chúng cùng cấu hình Docket.

springdoc được đăng ký thông qua Spring Boot auto-configuration của starter. Thông thường không cần thêm annotation @EnableOpenApi hoặc một annotation bật riêng nào khác.

Sau khi gỡ Springfox, kiểm tra:

- Không còn import từ springfox.documentation.*.
- Không còn import annotation Swagger 2 từ io.swagger.annotations.*.
- Không còn bean Docket.
- Không còn cấu hình Swagger UI cũ của Springfox.
- Không còn dependency transitively kéo swagger-models hoặc swagger-annotations 1.x vào runtime classpath.

## 6. Ánh xạ cấu hình Docket sang springdoc

Bảng dưới đây là bản đồ trách nhiệm, không phải bảng thay thế một-một:

| Springfox Docket | springdoc tương ứng | Ghi chú |
| --- | --- | --- |
| Docket.groupName | GroupedOpenApi.builder().group(...) | Dùng khi cần document theo nhóm |
| RequestHandlerSelectors.basePackage | packagesToScan hoặc springdoc.packages-to-scan | Lọc theo package |
| PathSelectors.any/regex | pathsToMatch và paths-to-exclude | Cần kiểm tra lại ngữ nghĩa pattern |
| RequestHandlerSelectors.withMethodAnnotation | addOpenApiMethodFilter | Lọc theo annotation trên method |
| Docket.apiInfo | Bean OpenAPI với Info | Metadata chung của document |
| Docket.securitySchemes | Components.securitySchemes hoặc @SecurityScheme | Khai báo scheme |
| Docket.securityContexts | SecurityRequirement, annotation hoặc customizer | Quyết định operation nào yêu cầu security |
| globalRequestParameters | Parameter/OperationCustomizer/GlobalOperationCustomizer | Không có phép thay thế trực tiếp duy nhất |
| globalResponses | @ApiResponse, @ApiResponses, OpenApiCustomizer hoặc GlobalOpenApiCustomizer | Chọn customizer theo phạm vi document cần áp dụng |
| ignoredParameterTypes | @Parameter(hidden = true), @Hidden hoặc customizer | Ẩn parameter/controller khỏi document |
| alternateTypeRules/directModelSubstitute | DTO rõ ràng, @Schema, ModelConverter hoặc SpringDocUtils | Cần xem từng quy tắc model |
| host, protocols, servers | OpenAPI.servers và cấu hình reverse proxy | Kiểm tra public URL |
| useDefaultResponseMessages | Response annotation/customizer và ControllerAdvice | Không nên sao chép response mặc định một cách mù quáng |

Điểm quan trọng: GroupedOpenApi quyết định endpoint thuộc tài liệu nào. Nó không thay thế OpenAPI bean, security scheme hay model converter.

## 7. Chuyển một Docket duy nhất sang properties

Ví dụ cấu hình Springfox cũ:

~~~java
@Bean
Docket applicationApi() {
    return new Docket(DocumentationType.SWAGGER_2)
        .select()
        .apis(RequestHandlerSelectors.basePackage("com.example.api"))
        .paths(PathSelectors.regex("/api/.*"))
        .build()
        .apiInfo(apiInfo());
}
~~~

Nếu đây là Docket duy nhất, hãy bỏ bean và cấu hình springdoc:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
~~~

Không cần tạo GroupedOpenApi chỉ để có một document mặc định. springdoc tự tạo document từ controller phù hợp với package/path filter.

Nếu Docket cũ dùng RequestHandlerSelectors.any() và PathSelectors.any(), có thể không cần cấu hình packages-to-scan hoặc paths-to-match. Mặc định springdoc quét các API phù hợp trong ứng dụng.

## 8. Chuyển nhiều Docket sang GroupedOpenApi

Giả sử Springfox có hai Docket:

~~~java
@Bean
Docket publicApi() {
    return new Docket(DocumentationType.SWAGGER_2)
        .select()
        .apis(RequestHandlerSelectors.basePackage(
            "com.example.api.publicapi"))
        .paths(PathSelectors.regex("/public.*"))
        .build()
        .groupName("public")
        .apiInfo(apiInfo());
}

@Bean
Docket adminApi() {
    return new Docket(DocumentationType.SWAGGER_2)
        .select()
        .apis(RequestHandlerSelectors.basePackage(
            "com.example.api.admin"))
        .paths(PathSelectors.regex("/admin.*"))
        .build()
        .groupName("admin")
        .apiInfo(apiInfo());
}
~~~

Chuyển sang:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .packagesToScan("com.example.api.publicapi")
            .pathsToMatch("/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .packagesToScan("com.example.api.admin")
            .pathsToMatch("/admin/**")
            .build();
    }
}
~~~

Hai group tạo hai OpenAPI document riêng. Theo cấu hình mặc định, URL JSON của chúng là:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
~~~

Swagger UI có thể liệt kê các group này trong cấu hình UI. Tên group phải duy nhất. Tránh đặt tên trùng hoặc thay đổi tên tùy tiện vì portal, script export và client generator có thể đang phụ thuộc URL group.

## 9. Chuyển selector theo annotation của method

Springfox cho phép chọn method bằng RequestHandlerSelectors.withMethodAnnotation(Admin.class). springdoc hỗ trợ lọc method trong GroupedOpenApi bằng addOpenApiMethodFilter.

Khai báo annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Admin {
}
~~~

Khai báo group:

~~~java
@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/**")
        .addOpenApiMethodFilter(
            method -> method.isAnnotationPresent(Admin.class))
        .build();
}
~~~

Method filter được áp dụng thêm vào điều kiện package/path nếu các điều kiện đó được khai báo. Nếu chỉ muốn lọc theo annotation, có thể bỏ pathsToMatch hoặc dùng phạm vi path thích hợp. Hãy kiểm tra document được sinh để xác nhận tập operation cuối cùng đúng mong muốn.

## 10. Chuyển một Docket có nhiều selector

Một Docket có thể kết hợp package selector và path selector. Ví dụ:

~~~java
.apis(RequestHandlerSelectors.basePackage("com.example.api"))
.paths(PathSelectors.regex("/v1/.*"))
~~~

Trong springdoc:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /v1/**
~~~

Hai điều kiện package và path cùng giới hạn tập endpoint. Nếu Docket cũ có selector theo annotation, method filter hoặc selector tùy chỉnh, hãy thêm điều kiện tương ứng bằng addOpenApiMethodFilter hoặc customizer.

Không chép nguyên chuỗi regex của PathSelectors.regex vào paths-to-match. Regex của Springfox và pattern path mà springdoc dùng không nhất thiết có cùng ngữ nghĩa. Ví dụ regex /public.* thường được chuyển thành pattern /public/** sau khi kiểm tra các URL thực tế, nhưng pattern cuối cần phản ánh cấu trúc path của ứng dụng.

Sau khi chuyển, tạo danh sách các endpoint được kỳ vọng và so sánh với OpenAPI document. Việc ứng dụng trả HTTP 200 ở /v3/api-docs không chứng minh bộ lọc đã chọn đúng endpoint.

## 11. Chuyển apiInfo sang bean OpenAPI

Docket.apiInfo thường chứa metadata toàn cục. Trong springdoc, khai báo bean OpenAPI:

~~~java
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class OpenApiMetadataConfiguration {

    @Bean
    OpenAPI applicationOpenAPI(Environment environment) {
        String publicApiUrl =
            environment.getRequiredProperty("app.public-api-url");

        return new OpenAPI()
            .info(new Info()
                .title("Spring Shop API")
                .description("API quản lý cửa hàng")
                .version("1.0.0")
                .license(new License()
                    .name("Apache 2.0")
                    .url("https://www.apache.org/licenses/LICENSE-2.0")))
            .externalDocs(new ExternalDocumentation()
                .description("Tài liệu kỹ thuật")
                .url("https://docs.example.com/api"))
            .components(new Components()
                .addSecuritySchemes(
                    "bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")))
            .addServersItem(new Server()
                .url(publicApiUrl)
                .description("Public API gateway"));
    }
}
~~~

Bean OpenAPI được dùng làm metadata chung cho các group. Nếu một group cần description hoặc external documentation riêng, dùng OpenApiCustomizer gắn trực tiếp vào GroupedOpenApi tương ứng.

Ví dụ:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import io.swagger.v3.oas.models.info.Info;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/partner/**")
        .addOpenApiCustomizer(openApi ->
            openApi.info(new Info()
                .title("Partner API")
                .version("1.0.0")
                .description("API dành cho đối tác")))
        .build();
}
~~~

Chỉ tùy biến thông tin riêng của group tại đây. Không nhân bản toàn bộ metadata toàn cục trong mọi group nếu chúng cần luôn đồng nhất.

Khai báo public URL theo môi trường, ví dụ trong application.yml:

~~~yaml
app:
  public-api-url: https://api.example.com
~~~

## 12. Chuyển annotation Swagger 2 sang OpenAPI 3

Springdoc dùng annotation từ package io.swagger.v3.oas.annotations. Các thay đổi thường gặp:

| Springfox / Swagger 2 | springdoc / OpenAPI 3 |
| --- | --- |
| @Api | @Tag |
| @ApiIgnore | @Parameter(hidden = true), @Operation(hidden = true) hoặc @Hidden |
| @ApiImplicitParam | @Parameter |
| @ApiImplicitParams | @Parameters |
| @ApiModel | @Schema |
| @ApiModelProperty | @Schema |
| @ApiModelProperty(allowEmptyValue = true) | @Schema(nullable = true) |
| @ApiOperation(value = "...", notes = "...") | @Operation(summary = "...", description = "...") |
| @ApiParam | @Parameter |
| @ApiResponse(code = 404, message = "...") | @ApiResponse(responseCode = "404", description = "...") |

Các annotation cùng tên như ApiResponse có thể đến từ hai package khác nhau. Sau migration, hãy kiểm tra import. Annotation OpenAPI 3 phải dùng package io.swagger.v3.oas.annotations.responses, không phải io.swagger.annotations.

Ví dụ controller:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Orders", description = "Quản lý đơn hàng")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{orderId}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã",
        description = "Trả về thông tin một đơn hàng."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy đơn hàng"
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy đơn hàng"
        )
    })
    OrderResponse getOrder(
        @Parameter(description = "Mã đơn hàng", example = "ORD-10001")
        @PathVariable String orderId) {
        return orderService.findById(orderId);
    }
}
~~~

Khi đổi annotation, giữ lại operationId nếu client SDK hoặc contract test đang phụ thuộc tên operation. Kiểm tra lại summary, description, response code và example vì Swagger 2 và OpenAPI 3 có cấu trúc khác nhau.

## 13. Chuyển model và field annotation

Springfox thường dùng @ApiModel và @ApiModelProperty. Trong springdoc, dùng @Schema:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderResponse", description = "Thông tin đơn hàng")
public record OrderResponse(
    @Schema(
        description = "Mã đơn hàng",
        example = "ORD-10001"
    )
    String orderId,

    @Schema(
        description = "Trạng thái đơn hàng",
        allowableValues = {"PENDING", "CONFIRMED", "SHIPPED", "CANCELLED"}
    )
    String status,

    @Schema(
        description = "Ghi chú có thể không có giá trị",
        nullable = true
    )
    String note
) {
}
~~~

Đừng chỉ đổi tên annotation mà bỏ qua ngữ nghĩa. Kiểm tra:

- required và nullable có còn đúng không.
- allowEmptyValue có thực sự tương đương nullable trong trường hợp đó không.
- allowableValues có còn phản ánh tập giá trị nghiệp vụ không.
- example có đúng kiểu và format không.
- accessMode hoặc readOnly/writeOnly có cần điều chỉnh không.
- Jackson @JsonProperty, @JsonIgnore và @JsonView có làm schema khác với DTO Java không.

Nếu một method nhận object chứa nhiều query parameter, springdoc có @ParameterObject để mô tả các field của object thành parameter riêng. Ví dụ với Pageable hoặc query DTO, hãy dùng annotation này khi cần và kiểm tra URL parameter thực tế trong document.

## 14. Chuyển securitySchemes và securityContexts

Springfox thường tách khai báo scheme và điều kiện áp dụng qua securitySchemes() và securityContexts(). Trong OpenAPI 3, hai ý này tương ứng với:

1. Security scheme trong components.securitySchemes.
2. Security requirement gắn vào toàn document, controller hoặc operation.

Ví dụ bearer JWT:

~~~java
// Thêm vào bean OpenAPI đã khai báo ở phần metadata:
.components(new Components()
    .addSecuritySchemes(
        "bearerAuth",
        new SecurityScheme()
            .type(SecurityScheme.Type.HTTP)
            .scheme("bearer")
            .bearerFormat("JWT")));
~~~

Đây là một phần của cùng bean OpenAPI toàn cục, không tạo thêm một bean OpenAPI thứ hai. Một ứng dụng thông thường nên có một cấu hình OpenAPI tổng hợp metadata, security scheme và server URL; nhiều bean OpenAPI độc lập có thể gây mơ hồ khi springdoc cần chọn document nền.

Gắn requirement vào controller hoặc operation cần bảo vệ:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Admin")
@SecurityRequirement(name = "bearerAuth")
class AdminController {
    // Các operation trong controller yêu cầu bearerAuth.
}
~~~

Nếu chỉ một số method cần xác thực, đặt @SecurityRequirement ở method thay vì cả class. Có thể khai báo global security trong OpenAPI bean nếu mọi operation đều yêu cầu cùng scheme, nhưng hãy chủ động đánh dấu các endpoint public để chúng không bị mô tả sai.

SecurityContexts của Springfox có thể lọc theo path regex và HTTP method. Không nên thay bằng một security requirement toàn cục nếu API có endpoint public, login, health hoặc callback không cần bearer token. Hãy kiểm tra security array của từng operation trong OpenAPI JSON.

## 15. Chuyển global request parameters

Docket.globalRequestParameters() thường được dùng để thêm header chung như X-Request-Id, X-Tenant-Id hoặc locale. Có hai cách phổ biến:

- Nếu parameter chỉ áp dụng cho một số endpoint, khai báo @Parameter tại controller/method.
- Nếu parameter thực sự áp dụng cho mọi operation, dùng GlobalOperationCustomizer hoặc cơ chế customizer phù hợp.

Ví dụ customizer thêm header chung và tránh tạo parameter trùng:

~~~java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.GlobalOperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CommonParameterConfiguration {

    @Bean
    GlobalOperationCustomizer requestIdHeader() {
        return (operation, handlerMethod) -> {
            boolean alreadyDeclared = operation.getParameters() != null
                && operation.getParameters().stream()
                    .anyMatch(p -> "X-Request-Id".equals(p.getName())
                        && "header".equals(p.getIn()));

            if (!alreadyDeclared) {
                operation.addParametersItem(new Parameter()
                    .name("X-Request-Id")
                    .in("header")
                    .description("Mã tương quan request")
                    .required(false)
                    .schema(new StringSchema()));
            }
            return operation;
        };
    }
}
~~~

GlobalOperationCustomizer được dùng khi cần áp dụng thay đổi cho operation của document mặc định và các group. Nếu chỉ một group cần parameter, dùng OperationCustomizer được gắn vào GroupedOpenApi đó. Hãy kiểm tra parameter có bị lặp khi controller cũng khai báo cùng header hay không.

Không khai báo header là required nếu ứng dụng thực tế không bắt buộc nó. OpenAPI là hợp đồng với consumer; mô tả sai một header optional thành required có thể làm client generator tạo code hoặc validation không phù hợp.

## 16. Chuyển global responses

Springfox có globalResponses() hoặc globalResponseMessage() để thêm response dùng chung theo HTTP method. Trong OpenAPI, response nên được mô tả sát với hành vi từng operation:

- Dùng @ApiResponse/@ApiResponses cho response cụ thể của operation.
- Dùng @ControllerAdvice để chuẩn hóa lỗi và mô tả các response lỗi chung.
- Dùng OpenApiCustomizer cho document mặc định; dùng GlobalOpenApiCustomizer nếu thay đổi phải xuất hiện trong document mặc định và mọi group.
- Dùng GroupedOpenApi.addOpenApiCustomizer(...) nếu response chỉ thuộc một group cụ thể.
- Kiểm tra thuộc tính springdoc.override-with-generic-response nếu muốn springdoc thêm response từ ControllerAdvice vào các operation.

Ví dụ:

~~~java
@Operation(summary = "Tạo đơn hàng")
@ApiResponses({
    @ApiResponse(responseCode = "201", description = "Đơn hàng đã được tạo"),
    @ApiResponse(responseCode = "400", description = "Request không hợp lệ"),
    @ApiResponse(responseCode = "409", description = "Không đủ tồn kho")
})
~~~

Không thêm mọi response lỗi vào mọi operation chỉ vì Docket cũ có một danh sách global. Một endpoint đọc dữ liệu có thể không trả 409; endpoint tạo đơn có thể có lỗi nghiệp vụ riêng. Document nên phản ánh response thực sự có thể xảy ra.

## 17. Chuyển ignoredParameterTypes và API bị ẩn

Springfox có ignoredParameterTypes() để loại kiểu parameter khỏi tài liệu. Trong springdoc, nên ẩn đúng tham số hoặc operation:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/profile")
ProfileResponse profile(
    @Parameter(hidden = true)
    @AuthenticationPrincipal UserPrincipal principal) {
    return profileService.get(principal);
}
~~~

Nếu cần ẩn cả controller hoặc method, có thể dùng @Hidden hoặc hidden = true trên @Operation. Chỉ ẩn parameter kỹ thuật như principal, servlet request hoặc context object; không ẩn parameter nghiệp vụ mà client cần truyền.

## 18. Chuyển alternateTypeRules và model substitution

Các quy tắc như alternateTypeRules(), directModelSubstitute() và genericModelSubstitutes() có thể thay kiểu nội bộ bằng kiểu khác trong Swagger model. Chúng không có một phép thay thế đơn giản sang GroupedOpenApi.

Ưu tiên:

1. Tạo request/response DTO rõ ràng dành cho API.
2. Dùng @Schema(implementation = ...) khi một operation cần biểu diễn kiểu cụ thể.
3. Dùng ModelConverter hoặc cơ chế schema customization khi cần thay đổi quy tắc chuyển đổi model ở mức dùng chung.
4. Dùng SpringDocUtils cho các trường hợp thay thế kiểu được thư viện hỗ trợ, kiểm tra package theo version.

Không nên thay một type rule phức tạp bằng một OpenApiCustomizer chỉ sửa tên schema. Customizer sửa document sau khi schema đã được tạo; nó không nhất thiết thay đổi cách Jackson serialize dữ liệu thực tế.

Đặc biệt kiểm tra Pageable, Page, Sort, wrapper generic, interface/abstract type và polymorphic DTO. springdoc có các model converter cho một số kiểu phổ biến; không nên giữ custom rule cũ nếu starter mới đã hỗ trợ đúng.

## 19. Chuyển host, protocols và pathMapping

Nếu Docket cũ đặt host, scheme hoặc base path, hãy xác định URL mà client thực sự dùng. Trong OpenAPI 3, base URL được mô tả bằng servers:

~~~java
// Thêm vào bean OpenAPI đã khai báo ở phần metadata:
.addServersItem(new Server()
    .url(publicApiUrl)
    .description("Public API gateway"))
~~~

Server URL có thể được lấy từ cấu hình theo môi trường thay vì hard-code. Thêm server vào bean OpenAPI hiện có, không khai báo một bean OpenAPI thứ hai chỉ để đặt URL.

Nếu ứng dụng chạy sau reverse proxy, cấu hình forwarded headers và proxy prefix đúng theo cách proxy giữ hoặc loại prefix. Không hard-code hostname nội bộ như service-name:8080 vào OpenAPI document public.

Đừng cộng context path vào cả servers.url và operation path nếu path của operation đã chứa prefix đó. Sau migration, kiểm tra server URL và Try it out trong Swagger UI ở môi trường staging.

## 20. Cấu hình path/package filter và endpoint group

Các property quan trọng:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  packages-to-exclude:
    - com.example.api.internal
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /internal/**
~~~

Các property này áp dụng cho document mặc định. Với từng GroupedOpenApi, có thể cấu hình packagesToScan, packagesToExclude, pathsToMatch và pathsToExclude trên builder.

Nếu nhóm có selector riêng, nên cấu hình ngay trong GroupedOpenApi để tránh vô tình làm thay đổi document mặc định hoặc group khác. Sau đó kiểm tra URL:

| Document | URL mặc định |
| --- | --- |
| Document mặc định | /v3/api-docs |
| Group public | /v3/api-docs/public |
| Group admin | /v3/api-docs/admin |

Nếu đã đổi springdoc.api-docs.path, URL thực tế của tất cả document sẽ thay đổi theo base path mới.

## 21. Vấn đề tương thích Springfox với Spring Boot 2.6 trở lên

Spring Boot 2.6 chuyển mặc định Spring MVC path matching từ AntPathMatcher sang PathPatternParser. Release notes cảnh báo cấu hình này có thể gây vấn đề với một số ứng dụng Springfox, đặc biệt khi kết hợp Actuator; Boot 2.6 cũng thay đổi cách Actuator match path.

Một số dự án cũ từng dùng:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

để tạm quay lại matcher cũ cho Spring MVC. Đây không phải giải pháp migration dài hạn và không sửa được mọi vấn đề liên quan Actuator, vì path matching của Actuator không được điều khiển bởi property này. Khi chuyển sang springdoc, hãy đánh giá lại property và chỉ giữ nếu ứng dụng còn một lý do cụ thể cần AntPathMatcher.

Nếu ứng dụng đang nâng từ Boot 2.x lên Boot 3.x, cần xử lý thêm namespace Jakarta và các dependency tương thích. Springdoc v2 dành cho Boot 3; Springdoc v3 dành cho Boot 4. Không trộn annotation hoặc servlet API javax của hệ cũ vào runtime Jakarta mới.

## 22. Quy trình migration theo từng bước

1. Ghi lại toàn bộ Docket bean, selector, groupName, apiInfo, security, parameter, response và model rule.
2. Đếm số Docket và xác định số OpenAPI document thực sự cần duy trì.
3. Chọn springdoc version theo Spring Boot version.
4. Thêm đúng starter MVC hoặc WebFlux; quyết định có cần Swagger UI hay chỉ API endpoint.
5. Gỡ Springfox dependencies và annotation kích hoạt cũ.
6. Nếu chỉ có một Docket, chuyển package/path filter sang properties và apiInfo sang OpenAPI bean.
7. Nếu có nhiều Docket, tạo GroupedOpenApi cho từng document.
8. Chuyển annotation Swagger 2 sang annotation OpenAPI 3.
9. Chuyển security scheme, operation requirement, global parameter và response theo trách nhiệm riêng.
10. Xử lý model substitution, path/server URL và proxy.
11. Khởi động ứng dụng, gọi document mặc định và từng group.
12. So sánh operation, schema, security, response và examples với hợp đồng trước.
13. Kiểm tra Swagger UI, OAuth2/bearer auth, Try it out và tài nguyên tĩnh.
14. Gỡ workaround Springfox không còn cần, chẳng hạn path matching strategy cũ nếu có.
15. Xóa hoàn toàn dependency Springfox còn sót và chạy lại test/build.

Không gỡ Springfox trước khi đã ghi nhận hợp đồng cũ. Nếu không có snapshot hoặc danh sách operation mong đợi, việc so sánh migration sẽ dựa vào quan sát thủ công và dễ bỏ sót endpoint.

## 23. Kiểm tra document sau migration

Gọi OpenAPI JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json
~~~

Kiểm tra JSON có operation:

~~~bash
jq -e '.openapi and (.paths | length > 0)' openapi.json
~~~

Với từng group:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs/public \
  --output openapi-public.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs/admin \
  --output openapi-admin.json
~~~

Đối chiếu tối thiểu:

- Mỗi path và HTTP method cần thiết đều có mặt.
- Không có endpoint nội bộ bị lộ.
- operationId duy nhất và ổn định.
- Request/response schema giữ đúng field, type, required, nullable và enum.
- Response status và media type không bị mất.
- Security scheme và security requirement đúng từng operation.
- Group public/admin không chứa nhầm endpoint của nhau.
- Server URL không trỏ vào host nội bộ.
- Swagger UI tải đúng document và Try it out gọi đúng URL.

OpenAPI JSON hợp lệ không đảm bảo API runtime đúng. Bổ sung MockMvc hoặc WebTestClient contract tests cho request/response quan trọng và test security cho endpoint được bảo vệ.

## 24. Lỗi thường gặp khi chuyển Docket

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ có một document mặc định dù trước có nhiều Docket | Chỉ thêm properties mà chưa tạo GroupedOpenApi cho các nhóm riêng | Tạo bean cho từng group cần giữ |
| Document group rỗng | packagesToScan hoặc pathsToMatch quá chặt | Kiểm tra package/path thực tế và method filter |
| Group có endpoint thừa | Selector mới không tương đương selector Springfox | So sánh danh sách operation và điều chỉnh filter |
| Metadata title/version biến mất | Chỉ tạo GroupedOpenApi mà quên OpenAPI bean | Chuyển apiInfo sang bean OpenAPI |
| Group thiếu security scheme | Chỉ thêm requirement mà không khai báo scheme hoặc customizer sai phạm vi | Khai báo components.securitySchemes và kiểm tra group |
| Header xuất hiện hai lần | Annotation và global customizer cùng thêm parameter | Kiểm tra trước khi thêm parameter |
| Swagger UI báo không tải được definition | API docs path sai, endpoint bị security chặn hoặc proxy rewrite sai | Kiểm tra /v3/api-docs và swagger-config |
| DTO có schema sai | Chỉ đổi annotation nhưng bỏ sót Jackson hoặc model converter | So sánh JSON thực tế với schema và dùng DTO rõ ràng |
| Response lỗi xuất hiện ở mọi operation | Chuyển globalResponses quá rộng | Dùng annotation/customizer theo phạm vi đúng |
| Spring Boot không khởi động | Còn dependency Springfox hoặc path matching/Actuator xung đột | Gỡ dependency cũ và kiểm tra cấu hình Boot |
| Swagger 2 client generator không đọc document mới | Consumer vẫn giả định cấu trúc Swagger 2 | Nâng generator và kiểm tra OpenAPI 3 compatibility |

## 25. Checklist hoàn tất migration

- [ ] Đã kiểm kê số lượng Docket và mục đích của từng bean.
- [ ] Đã quyết định một document mặc định hay nhiều group.
- [ ] Spring Boot và springdoc version khớp compatibility matrix.
- [ ] Đã thêm đúng starter MVC/WebFlux.
- [ ] Đã gỡ dependency Springfox và Swagger 2 cũ.
- [ ] Đã bỏ @EnableSwagger2 và bean Docket.
- [ ] Một Docket duy nhất đã được thay bằng properties khi phù hợp.
- [ ] Nhiều Docket đã được thay bằng GroupedOpenApi theo từng group.
- [ ] apiInfo đã được chuyển sang bean OpenAPI.
- [ ] Annotation Swagger 2 đã được chuyển sang OpenAPI 3.
- [ ] Security scheme và security requirement được áp dụng đúng operation.
- [ ] Global parameters/responses được chuyển theo phạm vi phù hợp.
- [ ] Model substitutions đã được đánh giá từng trường hợp.
- [ ] Server URL, context path và reverse proxy được kiểm tra.
- [ ] JSON của document mặc định và từng group đã được xác minh.
- [ ] Swagger UI, authentication và Try it out hoạt động.
- [ ] Không còn endpoint nội bộ bị công bố ngoài ý muốn.
- [ ] Contract tests và security tests quan trọng đã chạy thành công.

Migration tốt giữ được những hợp đồng mà consumer đang dùng, đồng thời loại bỏ cấu hình Springfox không còn phù hợp với nền tảng Spring Boot mới. Hãy dùng GroupedOpenApi khi thật sự cần nhiều document; để metadata, security, parameter và schema được quản lý bằng các thành phần OpenAPI tương ứng. Cách tách này giúp cấu hình dễ hiểu hơn và tránh biến một Docket cũ thành một bean GroupedOpenApi quá tải trách nhiệm.

## Tài liệu tham khảo

- [springdoc-openapi – Migrating from SpringFox](https://springdoc.org/migrating-from-springfox.html)
- [springdoc-openapi – Core Properties Reference](https://springdoc.org/core-properties.html)
- [springdoc-openapi – FAQ: Multiple OpenAPI definitions and GroupedOpenApi](https://springdoc.org/faq.html)
- [springdoc-openapi – Migrating from springdoc v1 to v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Spring Boot 2.6 – Release Notes: PathPattern based path matching](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.6-Release-Notes)
- [Springfox – Docket Javadoc](https://springfox.github.io/springfox/javadoc/current/springfox/documentation/spring/web/plugins/Docket.html)
- [Springfox – Releases](https://github.com/springfox/springfox/releases)
