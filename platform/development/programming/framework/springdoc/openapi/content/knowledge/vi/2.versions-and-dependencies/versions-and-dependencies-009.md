# Tránh trộn Springfox, Springdoc và các thư viện Swagger không tương thích

Một ứng dụng Spring Boot chỉ nên có một bộ công cụ chịu trách nhiệm tạo tài liệu API. Nếu cùng lúc đưa Springfox, Springdoc, nhiều phiên bản Swagger Core hoặc nhiều gói Swagger UI vào classpath, ứng dụng có thể gặp lỗi khởi động, lỗi liên kết thư viện, endpoint tài liệu trùng lặp hoặc annotation không được nhận diện như mong đợi. Những lỗi này thường xuất hiện sau khi nâng cấp Spring Boot hoặc thêm một dependency tài liệu mà không kiểm tra các dependency đang có.

Để tránh xung đột, cần xác định đúng thế hệ Spring Boot, chọn một dòng Springdoc hoặc Springfox phù hợp, dùng đúng starter cho Spring MVC hay WebFlux và giữ các thư viện Swagger ở phiên bản tương thích. Khi chuyển từ Springfox sang Springdoc, phải chuyển cả dependency lẫn annotation và cấu hình Java.

## 1. Phân biệt OpenAPI, Swagger, Springfox và Springdoc

Các tên gọi này có liên quan nhưng không chỉ cùng một thành phần:

- **OpenAPI** là đặc tả mô tả hợp đồng HTTP API bằng JSON hoặc YAML. Tài liệu OpenAPI mô tả path, operation, parameter, request body, response, schema và security scheme.
- **Swagger** là tên của hệ sinh thái công cụ làm việc với OpenAPI, trong đó có Swagger UI và các thư viện Swagger Core. Trong thực tế, nhiều lập trình viên cũng dùng từ “Swagger” để gọi chung tài liệu hoặc annotation API.
- **Springfox** là một dự án tích hợp tài liệu API với Spring. Nó có hệ dependency, cấu hình và cách xử lý annotation riêng. Springfox 3 có hỗ trợ OpenAPI 3 bên cạnh các khả năng Swagger trước đó, nhưng vẫn là một implementation độc lập với Springdoc.
- **Springdoc OpenAPI** là thư viện tích hợp Spring Boot với OpenAPI. Nó đọc controller, kiểu dữ liệu, annotation và cấu hình Spring để tạo đặc tả, đồng thời có thể tích hợp Swagger UI.

Vì vậy, “dùng OpenAPI” không đồng nghĩa phải dùng Springfox hay Springdoc. OpenAPI là định dạng hợp đồng; Springfox và Springdoc là các lựa chọn triển khai để tạo hoặc phục vụ tài liệu trong ứng dụng Spring.

### Hai thế hệ annotation thường gặp

Một nguồn nhầm lẫn phổ biến là hai namespace annotation sau:

| Nhóm annotation | Package | Ví dụ |
| --- | --- | --- |
| Swagger Core v1 / Swagger 2 annotations | `io.swagger.annotations` | `@Api`, `@ApiOperation`, `@ApiModel`, `@ApiParam` |
| Swagger Core v2 / OpenAPI 3 annotations | `io.swagger.v3.oas.annotations` | `@Tag`, `@Operation`, `@Schema`, `@Parameter` |

Tên annotation giữa hai thế hệ có thể gần giống nhau nhưng package, mục đích và cách diễn giải khác nhau. Springdoc sử dụng hệ annotation OpenAPI 3 trong `io.swagger.v3.oas.annotations`. Khi chuyển từ cấu hình Springfox cũ, chỉ đổi tên annotation trong mã nguồn mà giữ nguyên import cũ sẽ khiến Springdoc không đọc được metadata theo cách mong muốn.

Ví dụ, annotation `@ApiOperation` thuộc namespace cũ không phải là bản thay thế trực tiếp cho `@Operation`. Cần thay import và điều chỉnh thuộc tính theo API mới:

```java
// Annotation OpenAPI 3 dùng với Springdoc
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Parameter;

@Tag(name = "Books", description = "API quản lý sách")
class BookControllerDocumentation {

    @Operation(summary = "Tìm sách theo ID")
    void findBook(
            @Parameter(description = "Mã sách") long id) {
        // Ví dụ minh họa cách khai báo metadata.
    }
}

@Schema(description = "Thông tin sách")
record BookResponse(long id, String title) {}
```

Đây là ví dụ về metadata; controller thực tế vẫn cần các annotation ánh xạ Spring như `@RestController`, `@GetMapping` và phần xử lý nghiệp vụ.

## 2. Chọn phiên bản Springdoc theo thế hệ Spring Boot

Spring Boot 3 chuyển sang Spring Framework 6 và Jakarta EE, trong đó nhiều package Java EE cũ đổi từ `javax.*` sang `jakarta.*`. Đây là ranh giới quan trọng khi chọn thư viện tài liệu API.

| Nền tảng ứng dụng | Dòng Springdoc thường dùng | Lưu ý |
| --- | --- | --- |
| Spring Boot 1.x/2.x | Springdoc 1.x | Chọn phiên bản 1.x tương thích với minor version Spring Boot và Java của dự án |
| Spring Boot 3.x trở lên | Springdoc 2.x trở lên | Dùng starter thế hệ mới dựa trên Spring Framework 6 và Jakarta |

Không nên chỉ chọn phiên bản Springdoc mới nhất rồi thêm vào một ứng dụng Boot cũ. Ngược lại, không nên giữ Springdoc 1.x khi nâng ứng dụng lên Boot 3. Dù tên package trong mã nguồn có thể vẫn biên dịch ở một số trường hợp, các lớp nền tảng `javax`/`jakarta`, Spring Framework và các dependency bắc cầu có thể không tương thích lúc chạy.

Bảng trên chỉ định hướng theo thế hệ lớn. Khi chọn phiên bản cụ thể, hãy đối chiếu bảng tương thích của Springdoc với phiên bản Spring Boot, Java và Spring Framework thực tế trong dự án. Không tự nâng riêng Swagger Core hoặc Swagger annotations để xử lý một lỗi tương thích nếu chưa xác định dependency nào đang quản lý phiên bản đó.

### Ví dụ dependency cho Spring Boot 3 và Spring MVC

Với ứng dụng Spring MVC chạy trên Spring Boot 3, dùng starter UI tương ứng của Springdoc 2.x:

```xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

`2.x.y` là ký hiệu giữ chỗ; thay bằng phiên bản cụ thể đã được xác nhận tương thích với Spring Boot của dự án. Starter `webmvc-ui` tích hợp phần tạo OpenAPI cho Spring MVC và giao diện Swagger UI.

### Ví dụ dependency cho Spring Boot 2 và Spring MVC

Với ứng dụng thuộc thế hệ Spring Boot 2, dùng dòng Springdoc 1.x và artifact tương ứng của dòng này:

```xml
<properties>
    <springdoc.version>1.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Tên artifact của Springdoc 1.x khác với starter `springdoc-openapi-starter-*` của dòng 2.x. Không sao chép nguyên dependency của Boot 3 vào dự án Boot 2 hoặc ngược lại. Hãy xác nhận phiên bản 1.x được chọn hỗ trợ đúng minor version Boot đang chạy.

### Chọn starter theo Spring MVC hoặc WebFlux

Springdoc cung cấp các artifact riêng cho hai mô hình web chính:

| Mô hình ứng dụng | Springdoc 2.x với Swagger UI |
| --- | --- |
| Spring MVC | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-ui` |

Chọn starter theo web stack thực sự của ứng dụng. Không thêm cả hai starter chỉ để “phòng trường hợp cần dùng”; Spring Boot có quy tắc lựa chọn application context khi nhiều web stack cùng xuất hiện, và việc trộn chúng làm tăng khả năng cấu hình không rõ ràng. Nếu chỉ cần endpoint OpenAPI mà không cần giao diện, xem xét starter `*-api` tương ứng của dòng Springdoc 2.x thay vì starter `*-ui`.

## 3. Những cách trộn dependency dễ gây lỗi

### Giữ Springfox và thêm Springdoc cùng lúc

Ví dụ một `pom.xml` có cả hai bộ dependency:

```xml
<dependencies>
    <dependency>
        <groupId>io.springfox</groupId>
        <artifactId>springfox-boot-starter</artifactId>
        <version>3.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Đây là cấu hình nên tránh trong một ứng dụng đang chuyển sang Springdoc. Hai bộ thư viện có thể cùng đăng ký thành phần quét controller, cấu hình tài liệu hoặc giao diện. Kết quả có thể là nhiều endpoint tài liệu, nhiều cấu hình Swagger UI, bean không mong muốn hoặc hành vi phụ thuộc thứ tự cấu hình. Việc hai thư viện cùng có mặt trên classpath không chứng minh rằng chúng được thiết kế để phối hợp.

Khi chọn Springdoc, hãy gỡ Springfox starter và các module Springfox liên quan khỏi ứng dụng. Nếu một thư viện nội bộ kéo Springfox vào theo dependency bắc cầu, cần xác định thư viện đó có thể nâng cấp hoặc loại trừ dependency hay không.

### Thêm Swagger Core hoặc annotation độc lập với phiên bản không đồng bộ

Springdoc đã khai báo các dependency Swagger cần thiết thông qua dependency của nó. Thêm trực tiếp một phiên bản `swagger-core`, `swagger-annotations` hoặc `swagger-models` khác có thể khiến Maven/Gradle chọn phiên bản không đồng nhất với phiên bản mà Springdoc được kiểm thử cùng.

Đặc biệt, hai artifact annotation có namespace khác nhau:

```xml
<!-- Swagger Core v1: annotation cũ -->
<dependency>
    <groupId>io.swagger</groupId>
    <artifactId>swagger-annotations</artifactId>
    <version>1.x</version>
</dependency>

<!-- Swagger Core v2: annotation OpenAPI 3 -->
<dependency>
    <groupId>io.swagger.core.v3</groupId>
    <artifactId>swagger-annotations</artifactId>
    <version>2.x</version>
</dependency>
```

Không thêm cả hai chỉ vì mã nguồn đang dùng annotation từ hai package. Hãy chuyển mã nguồn sang annotation OpenAPI 3 nếu đã chọn Springdoc, rồi loại bỏ dependency Swagger v1 không còn cần thiết. Nếu có một thư viện khác thực sự yêu cầu Swagger v1, kiểm tra khả năng loại trừ hoặc nâng cấp thư viện đó trước khi giữ hai thế hệ cùng tồn tại.

### Thêm Swagger UI WebJar riêng khi starter đã cung cấp UI

Starter Springdoc có hậu tố `-ui` đã tích hợp phần cần thiết để phục vụ Swagger UI. Nếu đồng thời thêm một WebJar Swagger UI hoặc một bộ giao diện tài liệu khác, ứng dụng có thể chứa tài nguyên UI trùng lặp hoặc tải nhầm cấu hình OpenAPI. Chỉ thêm UI độc lập khi có lý do cụ thể và đã kiểm tra cách nó được phục vụ; không thêm theo thói quen.

### Dùng cả dependency cấp cao và module con cũ

Một dự án có thể đã có starter tổng hợp, sau đó lại thêm các module core, UI hoặc webmvc riêng từ một hướng dẫn cũ. Điều này có thể kéo vào nhiều phiên bản hoặc cấu hình trùng lặp. Ưu tiên một starter phù hợp với phiên bản và web stack; chỉ khai báo module riêng khi tài liệu phiên bản đó yêu cầu rõ.

## 4. Vì sao Springfox thường gặp vấn đề khi nâng cấp Spring Boot?

Springfox được xây dựng trong một giai đoạn hệ sinh thái Spring và Spring Boot có các API nền tảng khác hiện nay. Có hai thay đổi lớn cần lưu ý:

- **Spring Boot 2.6 và cơ chế path matching:** thay đổi cách Spring MVC xử lý đường dẫn có thể làm Springfox 3.0.0 gặp lỗi khi khởi tạo tài liệu, thường thể hiện qua lỗi liên quan đến `PatternsRequestCondition` hoặc `PathPattern`. Một số dự án Boot 2 cũ từng dùng cấu hình tương thích như `spring.mvc.pathmatch.matching-strategy=ant_path_matcher`, nhưng đây chỉ là biện pháp phụ thuộc phiên bản và không nên xem là giải pháp lâu dài cho mọi dự án.
- **Spring Boot 3 và Jakarta:** Boot 3 dựa trên Spring Framework 6 và chuyển nhiều API từ `javax.*` sang `jakarta.*`. Springfox 3.0.0 không phải lựa chọn tương thích cho thế hệ nền tảng này. Việc thêm Springfox vào dự án Boot 3 có thể dẫn đến lỗi class hoặc phương thức không tồn tại trong quá trình biên dịch hay khởi động.

Nếu đang nâng cấp Boot 2 lên Boot 3, đây là thời điểm thích hợp để chuyển sang Springdoc 2.x và hoàn tất việc chuyển annotation. Nếu ứng dụng vẫn chạy Boot 2, có thể tiếp tục dùng một bộ công cụ phù hợp với nền tảng đó trong khi lập kế hoạch nâng cấp; tránh thêm Springdoc chỉ để thử nghiệm vào cùng runtime hiện tại.

## 5. Quy trình chuyển từ Springfox sang Springdoc

Chuyển đổi cần thực hiện đồng bộ ở dependency, annotation, cấu hình và cách kiểm tra tài liệu.

### Bước 1: Xác định nền tảng hiện tại

Ghi nhận các thông tin trước khi sửa dependency:

- Phiên bản Spring Boot và Spring Framework.
- Phiên bản Java dùng để biên dịch và chạy.
- Ứng dụng dùng Spring MVC hay WebFlux.
- Springfox, Springdoc và Swagger Core đang được khai báo trực tiếp hoặc kéo vào bắc cầu.
- Các endpoint tài liệu và UI hiện được sử dụng trong môi trường phát triển, kiểm thử và production.

Đừng quyết định phiên bản Springdoc chỉ dựa trên một dòng dependency được tìm thấy trong một hướng dẫn khác. Phiên bản phải phù hợp với nền tảng thực tế của ứng dụng.

### Bước 2: Gỡ bộ dependency Springfox

Xóa các dependency không còn dùng như `springfox-boot-starter`, `springfox-swagger2`, `springfox-swagger-ui` hoặc các module Springfox khác đang được khai báo. Kiểm tra cả dependency bắc cầu từ thư viện nội bộ. Không để một starter Springfox cũ âm thầm tồn tại sau khi đã thêm Springdoc.

### Bước 3: Thêm đúng Springdoc starter

Chọn Springdoc 1.x hoặc 2.x theo thế hệ Spring Boot; chọn `webmvc` hoặc `webflux` theo ứng dụng; chọn hậu tố `-ui` nếu cần Swagger UI. Tránh thêm các artifact Springdoc cũ và mới cùng lúc.

### Bước 4: Chuyển annotation

Một số ánh xạ thường gặp khi chuyển từ annotation Swagger v1 sang OpenAPI 3:

| Annotation cũ | Annotation OpenAPI 3 thường dùng |
| --- | --- |
| `@Api` | `@Tag` |
| `@ApiOperation` | `@Operation` |
| `@ApiParam` | `@Parameter` |
| `@ApiModel` | `@Schema` |
| `@ApiModelProperty` | `@Schema` trên field hoặc property |
| `@ApiImplicitParam` | `@Parameter` hoặc khai báo request phù hợp với vị trí tham số |

Đây là ánh xạ theo mục đích, không phải thay thế máy móc từng thuộc tính. Ví dụ, mô tả request body thường nên được biểu diễn bằng kiểu DTO và `@RequestBody`; response cần mô tả schema và mã trạng thái bằng `@ApiResponse`, `@Content` và `@Schema` khi cần. Hãy kiểm tra import để bảo đảm các annotation thuộc `io.swagger.v3.oas.annotations`.

Ví dụ mô tả response:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@Operation(summary = "Tìm sách theo ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sách",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = BookResponse.class)
        )
    ),
    @ApiResponse(responseCode = "404", description = "Không tìm thấy sách")
})
```

### Bước 5: Thay cấu hình Springfox

Springfox thường dùng bean `Docket` và các kiểu cấu hình trong `springfox.documentation.*`. Springdoc có thể dùng bean `OpenAPI`, `GroupedOpenApi` và annotation OpenAPI 3. Không giữ `Docket` với kỳ vọng Springdoc sẽ tự chuyển đổi nó.

Ví dụ tạo một group bằng Springdoc 2.x:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
```

Nếu trước đây `Docket` lọc package, path, header hoặc cấu hình response, hãy chuyển từng quy tắc sang API cấu hình tương ứng của Springdoc và kiểm tra tài liệu kết quả. Không phải mọi tùy chọn riêng của Springfox đều có cùng tên hoặc hành vi trong Springdoc.

### Bước 6: Kiểm tra tài liệu sau chuyển đổi

Khởi động ứng dụng và xác minh các đầu ra phù hợp với cấu hình:

| Đầu ra thường dùng | Nội dung cần kiểm tra |
| --- | --- |
| `/v3/api-docs` | JSON hợp lệ, có đúng paths, schemas và responses |
| `/v3/api-docs.yaml` | YAML tương ứng với hợp đồng được công bố |
| `/swagger-ui/index.html` | Swagger UI tải được tài liệu OpenAPI mong muốn |
| `/v3/api-docs/{group}` | Từng group chứa đúng phạm vi endpoint |

Nếu ứng dụng dùng context path, reverse proxy hoặc đổi `server.servlet.context-path`, URL thực tế có thể có thêm tiền tố. Kiểm tra cả đường dẫn mà trình duyệt truy cập và URL tài liệu mà Swagger UI đang tải.

## 6. Kiểm tra dependency tree để tìm xung đột

Khi một lỗi không rõ nguyên nhân xuất hiện sau khi thêm thư viện tài liệu, hãy kiểm tra dependency tree trước khi thêm một dependency khác để “bù” class bị thiếu.

### Maven

Liệt kê các thư viện liên quan đến Springdoc, Springfox và Swagger:

```bash
mvn dependency:tree -Dincludes=org.springdoc,io.springfox,io.swagger,io.swagger.core.v3,org.webjars
```

Tìm các dấu hiệu:

- Có đồng thời `io.springfox` và `org.springdoc` trong runtime mà không có chủ đích rõ ràng.
- Có nhiều phiên bản `io.swagger.core.v3` hoặc nhiều phiên bản `swagger-annotations`.
- Một thư viện nội bộ kéo phiên bản Swagger Core cũ hơn phiên bản Springdoc cần.
- Có nhiều gói Swagger UI hoặc WebJar cung cấp cùng tài nguyên.

Maven chọn phiên bản dependency theo quy tắc mediation, thường ưu tiên dependency gần hơn trong cây. Vì thế, việc một dependency xuất hiện trong `pom.xml` không bảo đảm phiên bản đó là phiên bản cuối cùng ở runtime. Đọc cây phụ thuộc và đường dẫn kéo dependency để biết thành phần nào đang thắng.

### Gradle

Với Gradle, xem cấu hình runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để tìm lý do một phiên bản được chọn, dùng `dependencyInsight` với module cần kiểm tra, ví dụ:

```bash
./gradlew dependencyInsight \
  --dependency swagger-annotations \
  --configuration runtimeClasspath
```

Gradle có thể chọn phiên bản theo quy tắc resolution và constraint. Nếu cần loại trừ dependency bắc cầu, hãy đặt exclusion ở đúng dependency đang kéo nó vào và xác minh rằng thư viện đó vẫn hoạt động sau khi loại trừ.

Không nên ép mọi dependency Swagger về một phiên bản tùy ý bằng cách override hàng loạt. Các thành phần như `swagger-core`, `swagger-models` và `swagger-annotations` cần cùng một bộ phiên bản tương thích. Ưu tiên phiên bản do Springdoc quản lý; chỉ override khi có lý do kỹ thuật rõ ràng và đã kiểm thử.

## 7. Nhận diện lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` liên quan `javax.*`/`jakarta.*` | Thư viện không cùng thế hệ với Spring Boot hoặc còn dependency cũ | Kiểm tra Boot 2/3, Springdoc 1.x/2.x và dependency tree |
| `NoSuchMethodError` trong `io.swagger.*` hoặc `org.springdoc.*` | Các module được nạp ở phiên bản không tương thích | Dùng dependency tree hoặc `dependencyInsight` để tìm phiên bản thực tế |
| Springdoc không hiển thị mô tả từ annotation | Mã nguồn vẫn import annotation Swagger v1 hoặc import nhầm class cùng tên | Kiểm tra package `io.swagger.v3.oas.annotations` |
| Có nhiều giao diện hoặc endpoint tài liệu | Springfox và Springdoc cùng hoạt động, hoặc có UI/WebJar trùng lặp | Kiểm tra starter và tài nguyên UI trong runtime classpath |
| Ứng dụng lỗi khi tạo tài liệu sau khi nâng Boot 2.6 | Tương tác giữa Springfox và cơ chế path matching | Kiểm tra stack trace; cân nhắc chuyển sang Springdoc phù hợp |
| Swagger UI mở được nhưng không tải đặc tả | Sai URL tài liệu, context path, proxy hoặc endpoint bị bảo vệ | Kiểm tra request lấy `/v3/api-docs` trong Network và cấu hình URL |
| `/v3/api-docs` trả về 404 | Chưa có starter/API module phù hợp, đã đổi đường dẫn hoặc tài liệu bị vô hiệu hóa | Kiểm tra dependency, `springdoc.api-docs.path` và cấu hình môi trường |

Tên lỗi chỉ là dấu hiệu để khoanh vùng, không phải kết luận duy nhất. Hãy dùng stack trace đầy đủ và dependency tree của chính ứng dụng để xác định nguyên nhân.

## 8. Các nguyên tắc giữ classpath ổn định

- Chỉ chọn một implementation tạo tài liệu API cho mỗi ứng dụng: Springfox hoặc Springdoc.
- Chọn Springdoc 1.x hay 2.x theo thế hệ Spring Boot và bảng tương thích cụ thể.
- Chọn starter WebMVC hoặc WebFlux theo web stack của ứng dụng.
- Ưu tiên starter `-ui` nếu cần Swagger UI; không tự thêm WebJar trùng chức năng.
- Khi dùng Springdoc, ưu tiên annotation OpenAPI 3 trong `io.swagger.v3.oas.annotations`.
- Loại bỏ dependency Swagger v1 và cấu hình Springfox khi đã chuyển đổi xong, trừ khi có yêu cầu tương thích riêng được kiểm soát.
- Tránh override phiên bản Swagger Core và các module con khi chưa biết dependency nào đang quản lý chúng.
- Kiểm tra dependency tree sau khi thêm, nâng cấp hoặc loại bỏ thư viện.
- Xác minh cả tài liệu JSON/YAML, Swagger UI, group và các schema quan trọng sau mỗi lần thay đổi.

Việc giữ một bộ thư viện tài liệu nhất quán giúp giảm lỗi classpath và làm rõ nguồn tạo ra hợp đồng API. Khi nâng cấp Spring Boot hoặc chuyển từ Springfox sang Springdoc, hãy xử lý dependency, annotation và cấu hình như một thay đổi thống nhất, sau đó kiểm tra tài liệu được sinh ra từ ứng dụng thực tế.
