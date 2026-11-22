# Vai trò của Swagger annotations, Swagger Core và WebJars

Khi tích hợp `springdoc-openapi` vào Spring Boot, nhiều thành phần cùng tham gia tạo và hiển thị tài liệu API. Các annotation Swagger/OpenAPI bổ sung ý nghĩa cho controller và DTO; Swagger Core cung cấp những kiểu dữ liệu, mô hình và tiện ích làm việc với đặc tả OpenAPI; WebJars đóng gói tài nguyên giao diện web như JavaScript, CSS và hình ảnh. Springdoc kết nối các thành phần này với cơ chế ánh xạ request của Spring và cung cấp endpoint tài liệu cùng Swagger UI.

Hiểu đúng vai trò của từng lớp giúp chọn dependency vừa đủ, đặt dependency đúng module và xử lý lỗi xung đột phiên bản. Đặc biệt, annotation, mô hình OpenAPI và giao diện Swagger UI là ba loại thành phần khác nhau, dù chúng cùng xuất hiện trong một trang tài liệu.

## 1. Bức tranh tổng thể các thành phần

Một luồng tạo và hiển thị tài liệu thường diễn ra như sau:

1. Spring Boot khởi tạo controller, DTO, cấu hình Spring MVC hoặc WebFlux và các bean liên quan.
2. Springdoc phát hiện endpoint của Spring, đọc thông tin từ mapping, kiểu dữ liệu và annotation, sau đó xây dựng tài liệu OpenAPI.
3. Các kiểu annotation và mô hình OpenAPI thuộc hệ sinh thái Swagger cung cấp metadata và cấu trúc chuẩn để biểu diễn operation, schema, response, server và security.
4. Springdoc phục vụ tài liệu qua endpoint JSON hoặc YAML, thường là `/v3/api-docs` và `/v3/api-docs.yaml`.
5. Nếu dùng starter có UI, tài nguyên Swagger UI được đóng gói trong dependency WebJar. Trình duyệt tải HTML, JavaScript và CSS, sau đó gọi endpoint tài liệu để dựng giao diện.

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Springdoc OpenAPI | Tích hợp với Spring, phát hiện endpoint, kết hợp metadata và cung cấp endpoint tài liệu/UI | `springdoc-openapi-starter-webmvc-ui` |
| Swagger annotations | Bổ sung mô tả cho operation, parameter, schema, response và security | `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse` |
| Swagger Core và các module liên quan | Cung cấp mô hình OpenAPI cùng các tiện ích xử lý đặc tả | `OpenAPI`, `Info`, `Paths`, `Schema` |
| WebJars | Đóng gói tài nguyên frontend trong JAR để ứng dụng Java phân phối qua classpath | WebJar `swagger-ui` |
| Swagger UI | Giao diện chạy trong trình duyệt để đọc tài liệu và thử request | Trang `/swagger-ui.html` |

Springdoc là cầu nối dành cho hệ sinh thái Spring. Swagger Core là thư viện nền tảng của hệ sinh thái Swagger/OpenAPI. Swagger UI là ứng dụng frontend, còn WebJars là cách phân phối các file frontend đó trong ứng dụng Java.

## 2. Swagger annotations: mô tả ý nghĩa của API

Springdoc có thể suy luận nhiều thông tin từ controller và DTO. Chẳng hạn, `@GetMapping` cho biết HTTP method và path, `@PathVariable` cho biết tham số nằm trên path, còn kiểu trả về giúp xác định schema response. Tuy vậy, chữ ký Java không thể hiện đầy đủ ý nghĩa nghiệp vụ, ví dụ mã lỗi có thể trả về, đơn vị của một trường, ví dụ request hoặc yêu cầu xác thực.

Swagger annotations cho phép bổ sung các thông tin này trực tiếp tại controller, method, tham số hoặc DTO. Các annotation phổ biến gồm:

| Annotation | Vị trí thường dùng | Ý nghĩa |
|---|---|---|
| `@Tag` | Controller hoặc nhóm operation | Đặt tên và mô tả nhóm API |
| `@Operation` | Method xử lý endpoint | Mô tả operation, summary, description và các response |
| `@Parameter` | Tham số method | Mô tả query, path, header hoặc cookie parameter |
| `@Parameters` | Method hoặc tham số | Gom nhiều parameter annotation khi cần |
| `@ApiResponse` và `@ApiResponses` | Method hoặc operation | Mô tả mã trạng thái, nội dung và schema của response |
| `@RequestBody` của Swagger | Method hoặc tham số | Mô tả request body trong hợp đồng OpenAPI |
| `@Schema` | DTO, field, property hoặc kiểu dữ liệu | Bổ sung tên, mô tả, ví dụ, giới hạn và cấu trúc schema |
| `@Content` | Request body hoặc response | Khai báo media type và schema của nội dung |
| `@ExampleObject` | Nội dung request/response | Cung cấp ví dụ payload |
| `@SecurityScheme` | Cấu hình OpenAPI | Khai báo cách xác thực như HTTP Bearer hoặc OAuth2 |
| `@SecurityRequirement` | Controller hoặc operation | Gắn yêu cầu sử dụng security scheme đã khai báo |
| `@Hidden` | Controller, method hoặc phần tử được hỗ trợ | Ẩn phần tử khỏi tài liệu được sinh |

Các annotation nằm trong những package `io.swagger.v3.oas.annotations...`. Chúng mô tả hợp đồng API; chúng không tự triển khai routing, validate request hay thực hiện xác thực. Những nhiệm vụ đó vẫn thuộc Spring MVC, Bean Validation, Spring Security và mã nghiệp vụ.

### Ví dụ mô tả endpoint

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Tra cứu thông tin sản phẩm")
class ProductController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Lấy sản phẩm theo mã",
        description = "Trả về thông tin chi tiết của một sản phẩm đang được quản lý."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(responseCode = "404", description = "Không tìm thấy sản phẩm")
    })
    ProductResponse getById(
        @Parameter(description = "Mã định danh của sản phẩm", example = "42")
        @PathVariable Long id
    ) {
        return productService.getById(id);
    }
}
```

Trong ví dụ, Spring annotations xác định endpoint có thể được gọi như thế nào; Swagger annotations giải thích endpoint đó có ý nghĩa gì trong tài liệu. Springdoc kết hợp hai nguồn thông tin để tạo operation OpenAPI.

### Mô tả schema của DTO

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Thông tin sản phẩm được trả về từ API")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", example = "42")
    Long id,

    @Schema(description = "Tên hiển thị của sản phẩm", example = "Mechanical Keyboard")
    String name,

    @Schema(description = "Giá bán theo đơn vị tiền tệ của hệ thống", example = "1290000")
    Long price
) {
}
```

`@Schema` giúp người đọc hiểu ý nghĩa của từng property và giúp công cụ sinh client có thêm metadata. Ví dụ nên khớp với kiểu dữ liệu và quy tắc thực tế. Nếu trường có giới hạn độ dài, miền giá trị hoặc định dạng đặc biệt, hãy mô tả giới hạn đó bằng các thuộc tính schema phù hợp và bảo đảm chúng phản ánh validation đang thực thi.

### Phân biệt hai annotation cùng tên `RequestBody`

Trong Spring Boot có thể gặp hai annotation tên `RequestBody`:

```java
import org.springframework.web.bind.annotation.RequestBody;
```

Annotation của Spring gắn dữ liệu HTTP request vào tham số method để Spring MVC xử lý. Trong khi đó:

```java
import io.swagger.v3.oas.annotations.parameters.RequestBody;
```

Annotation của Swagger mô tả request body trong tài liệu OpenAPI. Phần lớn trường hợp Springdoc suy luận request body từ annotation Spring và kiểu tham số, nên không cần thêm annotation Swagger cho mọi endpoint. Chỉ dùng annotation Swagger khi cần mô tả hoặc ghi đè chi tiết như description, required, content hay ví dụ. Khi cần cả hai loại trong cùng một method, hãy dùng import đầy đủ hoặc đổi cách import để tránh nhầm lẫn.

### Khai báo thông tin API ở mức ứng dụng

Các annotation không phải lựa chọn duy nhất để bổ sung metadata. Có thể tạo bean `OpenAPI` bằng mô hình của Swagger để khai báo tiêu đề, phiên bản, mô tả và thông tin dùng chung:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI productApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Product API")
                .version("v1")
                .description("API quản lý và tra cứu sản phẩm"));
    }
}
```

Bean này dùng các lớp mô hình `io.swagger.v3.oas.models`, khác package với annotation `io.swagger.v3.oas.annotations`. Springdoc sử dụng bean OpenAPI để bổ sung metadata cấp tài liệu. Có thể kết hợp bean này với annotation trên controller và DTO; nên chọn một nơi quản lý thông tin chung để tránh khai báo trùng hoặc mâu thuẫn.

## 3. Swagger Core: mô hình và tiện ích của đặc tả OpenAPI

Swagger Core là thư viện Java thuộc hệ sinh thái Swagger, cung cấp các thành phần nền tảng để biểu diễn và xử lý đặc tả OpenAPI. Các module liên quan thường bao gồm:

- **Swagger annotations:** định nghĩa annotation như `@Operation`, `@Schema` và `@ApiResponse` để gắn metadata vào mã nguồn.
- **Swagger models:** cung cấp object model như `OpenAPI`, `Info`, `Paths`, `PathItem`, `Operation`, `Components`, `Schema` và `SecurityScheme`.
- **Swagger Core:** tập hợp các tiện ích xử lý mô hình, đọc hoặc chuyển đổi đặc tả và các tích hợp mà hệ sinh thái Swagger hỗ trợ.

Tên artifact chính xác có thể khác giữa các dòng phiên bản và biến thể Jakarta. Vì vậy, cần xem dependency tree của phiên bản springdoc đang sử dụng thay vì suy luận rằng mọi lớp Swagger đều nằm trong một JAR duy nhất.

Springdoc sử dụng các thành phần của hệ sinh thái Swagger để biểu diễn hợp đồng OpenAPI, đồng thời xử lý riêng cách phát hiện endpoint và metadata đặc thù của Spring. Điều này rất quan trọng: ứng dụng Spring MVC không cần tự cấu hình một scanner JAX-RS chỉ để springdoc đọc các controller Spring. Hãy dùng starter Springdoc phù hợp với MVC hoặc WebFlux để tích hợp đúng nền tảng web.

### Khi nào làm việc trực tiếp với OpenAPI model?

Phần lớn ứng dụng chỉ cần annotation và cấu hình Springdoc. Mô hình OpenAPI hữu ích khi cần tạo hoặc tùy biến thông tin cấp tài liệu bằng Java, chẳng hạn thêm server, contact, license, tag hoặc security scheme dùng chung.

Ví dụ sau bổ sung thông tin liên hệ và server:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.List;

@Bean
OpenAPI serviceApi() {
    return new OpenAPI()
        .info(new Info()
            .title("Inventory API")
            .version("v1")
            .contact(new Contact().name("API Team")))
        .servers(List.of(
            new Server().url("https://api.example.com").description("Production")
        ));
}
```

Địa chỉ server trong ví dụ chỉ là giá trị minh họa. Trong ứng dụng thật, cần quản lý URL theo môi trường hoặc cấu hình reverse proxy để tài liệu không trỏ nhầm đến máy chủ production khi chạy ở local hay staging.

Không nên tạo lại toàn bộ tài liệu bằng cách tự viết object model nếu Springdoc đã suy luận chính xác từ controller. Chỉ tùy biến phần cần thiết, vì việc khai báo thủ công trùng với metadata được suy luận có thể làm tài liệu khó bảo trì hoặc không còn khớp với endpoint thật.

## 4. WebJars: phân phối tài nguyên giao diện trong JAR

Swagger UI là ứng dụng frontend. Nó cần các file HTML, JavaScript, CSS, font và hình ảnh để chạy trong trình duyệt. WebJars đóng gói những tài nguyên web này vào artifact Maven/Gradle để ứng dụng Java có thể lấy chúng từ classpath, thay vì yêu cầu nhóm phát triển tự tải và chép từng file vào thư mục static.

Một WebJar thường đặt tài nguyên theo cấu trúc tương tự:

```text
META-INF/resources/webjars/<webjar-name>/<webjar-version>/...
```

Trong dependency của starter Swagger UI, WebJar `swagger-ui` cung cấp các file frontend. Springdoc cấu hình việc phân phối các tài nguyên này và cung cấp điểm vào giao diện, thường là `/swagger-ui.html` hoặc `/swagger-ui/index.html` tùy đường dẫn và phiên bản. Trình duyệt tải giao diện, sau đó lấy tài liệu OpenAPI từ endpoint được cấu hình.

WebJars không tạo schema từ controller và cũng không xử lý request nghiệp vụ. Chúng chỉ phân phối tài nguyên web. Nếu endpoint `/v3/api-docs` trả về tài liệu đúng nhưng trình duyệt báo thiếu JavaScript hoặc CSS, cần kiểm tra phần phục vụ tài nguyên UI, dependency WebJar và đường dẫn tài nguyên.

### Khi nào cần thêm WebJar trực tiếp?

Với ứng dụng dùng starter `springdoc-openapi-starter-webmvc-ui` hoặc starter UI tương ứng cho WebFlux, dependency cần thiết cho Swagger UI thường đã được kéo vào theo quan hệ phụ thuộc. Không cần khai báo thêm một WebJar Swagger UI riêng nếu chỉ dùng giao diện do springdoc tích hợp.

Chỉ cân nhắc thêm hoặc quản lý WebJar trực tiếp khi ứng dụng có nhu cầu phân phối frontend riêng, thay thế phiên bản tài nguyên UI có chủ đích hoặc dùng cơ chế phục vụ static resource khác. Khi tự quản lý phiên bản WebJar, cần kiểm tra khả năng tương thích giữa tài nguyên Swagger UI và cấu hình mà springdoc mong đợi.

## 5. Chọn starter và đặt dependency đúng module

Với Spring MVC, hai lựa chọn thường gặp trong dòng starter hiện đại của springdoc là:

| Nhu cầu | Artifact |
|---|---|
| Cung cấp OpenAPI endpoint, không cần giao diện Swagger UI tích hợp | `springdoc-openapi-starter-webmvc-api` |
| Cung cấp OpenAPI endpoint cùng Swagger UI | `springdoc-openapi-starter-webmvc-ui` |

Với Spring WebFlux, dùng các starter tương ứng có tên `springdoc-openapi-starter-webflux-api` hoặc `springdoc-openapi-starter-webflux-ui`. Chọn đúng loại web stack đang chạy trong ứng dụng; không thêm đồng thời MVC và WebFlux starter nếu kiến trúc không yêu cầu cả hai.

Ví dụ dependency Maven cho ứng dụng Spring MVC cần cả tài liệu và UI:

```xml
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
```

Ví dụ Gradle:

```kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion")
}
```

Thay `YOUR_COMPATIBLE_VERSION` hoặc `springdocVersion` bằng phiên bản tương thích với dòng Spring Boot của dự án. Không dùng chuỗi placeholder làm phiên bản phát hành thật.

### Đặt dependency ở đâu trong dự án nhiều module?

Giả sử dự án có cấu trúc:

```text
application
  └── cấu hình Spring Boot và Swagger UI
product-api
  └── controller, DTO và Swagger annotations
product-domain
  └── mô hình nghiệp vụ
```

Nếu `product-api` chứa mã nguồn import `@Operation` hoặc `@Schema`, module này phải có các annotation trên compile classpath. Nếu starter Springdoc chỉ được khai báo ở `application`, dependency đó không nhất thiết xuất hiện trên compile classpath của module `product-api`, tùy cách cấu hình dependency giữa các module. Hãy khai báo dependency tại module trực tiếp sử dụng kiểu annotation, hoặc thiết kế dependency chung phù hợp với kiến trúc.

Ứng dụng khởi động và phục vụ API Docs/UI thường khai báo starter tích hợp Springdoc ở module ứng dụng. Nếu một module thư viện chỉ cần annotation để mô tả controller/DTO và không cần chạy Springdoc, có thể khai báo artifact annotation tương thích ở module đó. Khi chọn cách này, phải bảo đảm phiên bản annotation thống nhất với phiên bản mà starter Springdoc kéo vào.

Không nên đưa WebJar Swagger UI vào module domain chỉ vì module đó chứa DTO. Tài nguyên giao diện thuộc lớp ứng dụng web chịu trách nhiệm phân phối tài liệu.

## 6. Tương thích phiên bản và biến thể Jakarta

Các artifact Springdoc, Swagger Core, Swagger annotations và WebJars có quan hệ phụ thuộc với nhau. Ngoài việc khớp phiên bản thư viện, dự án còn phải khớp dòng Spring Boot và namespace Servlet mà nền tảng sử dụng.

Một điểm cần chú ý là thay đổi từ `javax.*` sang `jakarta.*` trong hệ sinh thái Spring. Các dòng Spring Boot mới dùng Jakarta namespace; dòng Spring Boot cũ dùng hệ sinh thái Java EE với `javax`. Những phiên bản Swagger Core tương ứng có thể cung cấp artifact biến thể thường và biến thể Jakarta, chẳng hạn các tên kết thúc bằng `-jakarta`.

Quy tắc lựa chọn:

1. Xác định dòng Spring Boot và web stack của ứng dụng trước khi chọn Springdoc.
2. Chọn dòng Springdoc được công bố tương thích với Spring Boot đó.
3. Để starter Springdoc quản lý các phiên bản Swagger Core, Swagger models, annotations và UI mà nó yêu cầu, trừ khi có lý do kỹ thuật rõ ràng để override.
4. Nếu khai báo Swagger annotations trực tiếp ở module khác, chọn đúng biến thể Jakarta hoặc non-Jakarta theo dòng thư viện của dự án.
5. Kiểm tra dependency tree để chắc chắn runtime không chứa nhiều phiên bản không tương thích của cùng một artifact.

Không nên chỉ đổi phiên bản `swagger-annotations` lên bản mới nhất trong khi giữ starter Springdoc cũ. Một annotation mới có thể không tồn tại trong phiên bản mà thư viện xử lý đang dùng; ngược lại, một phiên bản Swagger Core mới có thể thay đổi API mà springdoc cũ không tương thích.

## 7. Kiểm tra dependency tree và xử lý xung đột

Khi annotation không được nhận diện, endpoint tài liệu lỗi hoặc Swagger UI thiếu tài nguyên, hãy kiểm tra dependency thực tế thay vì chỉ xem file `pom.xml` hoặc `build.gradle`. Dependency khai báo trực tiếp có thể kéo theo một phiên bản khác từ module khác hoặc từ thư viện nền tảng.

Với Maven, xem các artifact liên quan:

```bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
```

Với Gradle, có thể kiểm tra dependency runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Hoặc xem lý do một dependency được chọn:

```bash
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-annotations --configuration compileClasspath
./gradlew dependencyInsight --dependency swagger-ui --configuration runtimeClasspath
```

Tên configuration có thể khác trong dự án Android, plugin hoặc module Gradle đặc thù; hãy chọn configuration tồn tại trong module cần kiểm tra.

Một số dấu hiệu và hướng xử lý:

| Dấu hiệu | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| IDE báo không tìm thấy `io.swagger.v3.oas.annotations...` | Module chứa controller thiếu annotation trên compile classpath | Kiểm tra dependency trực tiếp và quan hệ giữa các module |
| `NoClassDefFoundError` hoặc `ClassNotFoundException` khi khởi động | Thiếu JAR cần thiết hoặc loại artifact không khớp | Xem runtime dependency tree và các exclusion |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Các phiên bản Swagger Core/models/annotations không tương thích | Tìm phiên bản bị kéo trùng và dependency override |
| JSON/YAML có dữ liệu nhưng Swagger UI trả lỗi tải | Sai URL tài liệu, quyền truy cập hoặc CORS | Kiểm tra request tài liệu trong Network của trình duyệt |
| UI trả 404 cho JavaScript/CSS | WebJar hoặc resource handler không được đóng gói/phục vụ đúng | Kiểm tra starter UI, WebJar và đường dẫn sau reverse proxy |
| Annotation tồn tại nhưng mô tả không xuất hiện như mong đợi | Dùng sai package, annotation đặt sai vị trí hoặc metadata bị cấu hình ghi đè | Kiểm tra import, vị trí annotation và tài liệu sinh ra |

Khi cần loại trừ dependency bắc cầu, xác định artifact gây xung đột từ dependency tree trước. Chỉ thêm `exclusion` khi biết thành phần thay thế nào sẽ cung cấp lớp bị loại bỏ và phiên bản thay thế tương thích. Exclude toàn bộ Swagger Core hoặc Swagger models có thể khiến springdoc không khởi động được.

## 8. Những nhầm lẫn thường gặp

**Thêm Swagger annotations nghĩa là đã có Swagger UI.** Không đúng. Annotation chỉ cung cấp metadata. Muốn có endpoint tài liệu cần starter Springdoc API phù hợp; muốn có giao diện tích hợp cần starter UI hoặc một frontend khác.

**Có WebJar là tự sinh được OpenAPI.** Không đúng. WebJar chứa tài nguyên web. Springdoc và các thành phần xử lý OpenAPI mới tạo tài liệu từ ứng dụng.

**Swagger Core tự động hiểu mọi controller Spring.** Không nên giả định như vậy. Tích hợp Spring được thực hiện bởi Springdoc; hãy chọn starter MVC hoặc WebFlux tương ứng.

**Có `@SecurityRequirement` là API đã được bảo vệ.** Không đúng. Annotation chỉ mô tả bảo mật trong tài liệu. Spring Security hoặc cơ chế xác thực thực tế mới thực thi chính sách truy cập.

**Module ứng dụng có dependency thì mọi module con đều biên dịch được annotation.** Không nhất thiết. Mỗi module cần khai báo dependency trên compile classpath nếu mã nguồn của chính nó sử dụng các kiểu đó.

**Có thể nâng riêng Swagger Core mà không kiểm tra Springdoc.** Rủi ro cao. Các artifact được quản lý như một tập hợp phụ thuộc; hãy kiểm tra phiên bản tương thích và dependency tree trước khi override.

## 9. Checklist chọn và kiểm tra các thành phần

- [ ] Đã xác định ứng dụng dùng Spring MVC hay Spring WebFlux.
- [ ] Starter Springdoc phù hợp với web stack và dòng Spring Boot.
- [ ] Dùng starter API nếu chỉ cần tài liệu, hoặc starter UI nếu cần Swagger UI tích hợp.
- [ ] Module chứa controller/DTO khai báo annotation trên compile classpath.
- [ ] Import annotation từ đúng package `io.swagger.v3.oas.annotations...`.
- [ ] Các mô hình tùy biến dùng đúng package `io.swagger.v3.oas.models...`.
- [ ] Không thêm WebJar Swagger UI trùng lặp khi starter UI đã cung cấp tài nguyên cần thiết.
- [ ] Các artifact Swagger Core, annotations, models và WebJars không bị ép sang phiên bản không tương thích.
- [ ] Dependency tree không có xung đột gây lỗi compile hoặc runtime.
- [ ] Endpoint OpenAPI và tài nguyên Swagger UI đều tải được trong môi trường triển khai.

Khi phân chia đúng vai trò, controller và DTO cung cấp dữ liệu nguồn, Swagger annotations bổ sung ý nghĩa, Swagger Core cung cấp cấu trúc OpenAPI, Springdoc tích hợp với Spring và WebJars phân phối giao diện Swagger UI. Quản lý các dependency theo đúng module và cùng một dòng phiên bản tương thích giúp tài liệu được sinh ổn định, dễ bảo trì và phản ánh đúng hợp đồng API.
