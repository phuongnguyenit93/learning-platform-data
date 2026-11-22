# Thông tin phiên bản ứng dụng và metadata theo môi trường

## 1. Vì sao OpenAPI cần thông tin phiên bản và môi trường?

OpenAPI document không chỉ liệt kê path và HTTP method. Phần metadata cho client biết tài liệu mô tả API nào, phiên bản hợp đồng nào, server nào được dùng và đơn vị nào chịu trách nhiệm.

Trong Spring Boot, ứng dụng có thể chạy ở nhiều môi trường như local, development, staging và production. Mỗi môi trường có thể có public base URL, mô tả, contact hoặc chính sách phân phối tài liệu khác nhau. Đồng thời, phiên bản build của ứng dụng có thể thay đổi thường xuyên trong khi hợp đồng API vẫn giữ nguyên.

Vì vậy, cần quản lý riêng các nhóm thông tin:

- **OpenAPI Specification version**: phiên bản chuẩn OpenAPI mà document tuân theo, được biểu diễn ở trường `openapi`.
- **API contract version**: phiên bản hợp đồng API được công bố, thường nằm ở `info.version`.
- **Application/build version**: phiên bản artifact Spring Boot được build và triển khai.
- **Source revision**: commit hoặc revision tạo ra artifact, nếu tổ chức cần công bố.
- **Environment metadata**: tên môi trường và server URL mà tài liệu đang mô tả.

Springdoc OpenAPI tạo document từ controller, DTO và metadata cấu hình. Có thể dùng `OpenAPI` bean, annotation hoặc customizer để đưa thông tin này vào tài liệu. Khi giá trị thay đổi theo môi trường, nên dùng Spring Boot externalized configuration thay vì hard-code URL production trong Java.

## 2. Phân biệt ba loại phiên bản

Một lỗi phổ biến là dùng cùng một giá trị cho phiên bản OpenAPI, phiên bản API và phiên bản ứng dụng.

| Thông tin | Ví dụ | Ý nghĩa |
|---|---|---|
| OpenAPI Specification version | `3.1.0` | Phiên bản chuẩn mô tả cấu trúc document |
| API contract version | `1.4.0` | Phiên bản hợp đồng API mà client tích hợp |
| Application version | `2.8.3` | Phiên bản artifact Spring Boot được triển khai |
| Source revision | `a1b2c3d` | Commit hoặc revision của source tạo ra artifact |

Ví dụ phần đầu OpenAPI document:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: "1.4.0"
~~~

Trường `openapi` cho biết document dùng OpenAPI Specification 3.1.0. Trường `info.version` cho biết phiên bản của API/document được mô tả. Đây không phải hai cách ghi cùng một phiên bản.

Nếu ứng dụng được build ở version 2.8.3 nhưng API contract vẫn là 1.4.0, điều đó hoàn toàn có thể hợp lý. Một bản build mới có thể chỉ sửa lỗi nội bộ, cập nhật thư viện hoặc thay đổi triển khai mà không làm thay đổi hợp đồng công khai.

Không nên tự động tăng `info.version` mỗi lần build nếu chính sách versioning của API không yêu cầu như vậy. Ngược lại, khi thay đổi contract có ảnh hưởng client, cần cập nhật API version theo quy tắc quản lý phiên bản của tổ chức.

## 3. Những trường metadata thường dùng trong Info Object

OpenAPI Info Object có các trường thường dùng:

| Trường | Mục đích |
|---|---|
| `title` | Tên API hiển thị trong Swagger UI và tài liệu |
| `summary` | Tóm tắt ngắn, được hỗ trợ trong OpenAPI 3.1 |
| `description` | Mô tả mục tiêu, phạm vi và cách sử dụng API |
| `version` | Phiên bản API/document |
| `termsOfService` | URL điều khoản sử dụng |
| `contact` | Thông tin nhóm hỗ trợ hoặc owner |
| `license` | Thông tin giấy phép |

Ví dụ YAML:

~~~yaml
info:
  title: Catalog API
  summary: API quản lý danh mục sản phẩm
  description: |
    API cung cấp chức năng tra cứu, tạo và cập nhật sản phẩm.
    Client cần sử dụng security scheme được công bố trong document.
  version: "1.4.0"
  contact:
    name: API Platform Team
    email: api-support@example.com
    url: https://developer.example.com/support
  license:
    name: Internal API Terms
    url: https://developer.example.com/terms
~~~

Trường `summary` thuộc OpenAPI 3.1. Nếu dự án xuất OpenAPI 3.0 hoặc model dependency chưa hỗ trợ trường này, hãy dùng `description` để trình bày phần giới thiệu ngắn.

Thông tin contact và license nên trỏ tới địa chỉ được duy trì. Không điền email cá nhân hoặc URL nội bộ nếu tài liệu được công khai cho đối tác.

## 4. Khai báo metadata tĩnh bằng @OpenAPIDefinition

Với API có metadata cố định, có thể dùng annotation của Swagger Core:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Catalog API",
        version = "1.4.0",
        description = "API quản lý danh mục sản phẩm.",
        contact = @Contact(
            name = "API Platform Team",
            email = "api-support@example.com",
            url = "https://developer.example.com/support"
        )
    )
)
public class OpenApiDefinitionConfiguration {
}
~~~

Các annotation thuộc package `io.swagger.v3.oas.annotations`. Springdoc đọc metadata này khi tạo OpenAPI document.

Cách này dễ hiểu với cấu hình đơn giản và ít thay đổi theo môi trường. Tuy nhiên, annotation có giá trị tĩnh và không thuận tiện khi title, API version hoặc server URL phải lấy từ environment variable, profile hay build metadata.

Không nên khai báo cùng một trường ở nhiều nguồn mà không xác định nguồn chính. Nếu vừa có `@OpenAPIDefinition` vừa có `OpenAPI` bean hoặc customizer cùng thay `Info`, kết quả cuối cùng có thể phụ thuộc quá trình tạo document và phiên bản thư viện. Hãy chọn một nguồn chính cho metadata toàn cục rồi kiểm tra JSON thực tế.

## 5. Dùng OpenAPI bean khi metadata cần lấy từ cấu hình

Khi metadata thay đổi theo môi trường, có thể tạo `OpenAPI` bean:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI applicationOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Catalog API")
                .description("API quản lý danh mục sản phẩm.")
                .version("1.4.0"))
            .servers(List.of(
                new Server()
                    .url("https://api.example.com")
                    .description("Production")
            ));
    }
}
~~~

Springdoc sử dụng bean này làm metadata nền cho document và bổ sung operation được suy luận từ controller.

Các import model trong ví dụ thuộc package `io.swagger.v3.oas.models`; `@Configuration` và `@Bean` thuộc Spring Framework.

OpenAPI bean phù hợp khi cần:

- Đọc title và version từ application properties.
- Chọn server URL theo profile.
- Thêm contact, license hoặc external documentation.
- Đưa build metadata vào vendor extension.
- Xây dựng document theo cấu hình runtime.

Nếu ứng dụng đã có OpenAPI bean, hãy mở rộng bean đó thay vì khai báo nhiều bean không rõ cách kết hợp.

## 6. Đưa metadata vào application.yml

Có thể tập trung các giá trị thay đổi theo môi trường trong cấu hình:

~~~yaml
app:
  api:
    title: Catalog API
    version: ${API_CONTRACT_VERSION:1.4.0}
    description: API quản lý danh mục sản phẩm.
    environment: ${APP_ENV:local}
    server-url: ${PUBLIC_API_URL:http://localhost:8080}
    expose-build-metadata: false
~~~

Ở đây:

- `title` là tên API.
- `version` là API contract version.
- `description` là mô tả API.
- `environment` là tên môi trường.
- `server-url` là public base URL mà client nên gọi.
- `expose-build-metadata` quyết định có công bố thông tin build hay không.

Spring Boot hỗ trợ externalized configuration. Các placeholder có thể nhận giá trị từ environment variable hoặc cấu hình profile. Ví dụ, `API_CONTRACT_VERSION` có thể được đặt trong pipeline phát hành và `PUBLIC_API_URL` được đặt bởi môi trường triển khai.

Không đặt password, token, private key hoặc secret trong phần metadata OpenAPI. Document có thể được tải xuống và chia sẻ, kể cả khi Swagger UI được bảo vệ.

## 7. Gom cấu hình bằng @ConfigurationProperties

Với nhiều metadata liên quan, `@ConfigurationProperties` giúp gom cấu hình thành một kiểu Java rõ ràng.

Ví dụ dùng Java record:

~~~java
@ConfigurationProperties(prefix = "app.api")
public record ApiMetadataProperties(
    String title,
    String version,
    String description,
    String environment,
    URI serverUrl,
    boolean exposeBuildMetadata
) {
}
~~~

Đăng ký class cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ApiMetadataProperties.class)
public class ApiMetadataConfiguration {
}
~~~

Spring Boot bind các giá trị từ `app.api.*` vào record. Kiểu `URI` giúp biểu diễn server URL có cấu trúc thay vì xử lý chuỗi tùy ý.

Nếu dự án đã dùng `@ConfigurationPropertiesScan`, có thể để Boot tự phát hiện class thay vì thêm `@EnableConfigurationProperties` cho từng cấu hình.

Với dự án lớn, có thể thêm validation để bảo đảm title và version không rỗng, server URL có scheme hợp lệ và environment thuộc tập giá trị được cho phép. Cần chọn cách validation phù hợp với phiên bản Spring Boot và dependency validation của dự án.

## 8. Tạo OpenAPI bean từ metadata đã bind

Sau khi có properties, có thể xây dựng document:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ApiMetadataProperties.class)
public class OpenApiConfiguration {

    @Bean
    public OpenAPI applicationOpenAPI(ApiMetadataProperties metadata) {
        Info info = new Info()
            .title(metadata.title())
            .description(metadata.description())
            .version(metadata.version());

        OpenAPI openAPI = new OpenAPI()
            .info(info);

        if (metadata.serverUrl() != null) {
            openAPI.addServersItem(
                new Server()
                    .url(metadata.serverUrl().toString())
                    .description(metadata.environment())
            );
        }

        return openAPI;
    }
}
~~~

Ví dụ trên giữ `Info.version` lấy từ API contract version và Server URL lấy từ môi trường. Khi chạy local, document có thể mô tả `http://localhost:8080`; khi chạy production, cùng code có thể dùng URL công khai của production.

Không nên tạo một server URL từ hostname container hoặc địa chỉ nội bộ rồi đưa vào tài liệu công khai. Giá trị `server-url` phải là URL mà client thực sự có thể truy cập.

Nếu OpenAPI document có nhiều server, Swagger UI có thể cho người dùng chọn server. Chỉ liệt kê nhiều server khi tất cả đều là endpoint được phép sử dụng bởi audience của document đó. Không nên đưa staging, development hoặc hostname nội bộ vào tài liệu public chỉ để tiện kiểm thử.

## 9. Dùng Spring Profiles cho metadata theo môi trường

Có thể giữ cấu hình mặc định trong `application.yml`:

~~~yaml
app:
  api:
    title: Catalog API
    version: "1.4.0"
    description: API quản lý danh mục sản phẩm.
    environment: local
    server-url: http://localhost:8080
    expose-build-metadata: false
~~~

Cấu hình staging trong `application-staging.yml`:

~~~yaml
app:
  api:
    environment: staging
    server-url: https://staging-api.example.com
~~~

Cấu hình production trong `application-prod.yml`:

~~~yaml
app:
  api:
    environment: production
    server-url: https://api.example.com
~~~

Kích hoạt profile bằng cấu hình triển khai, ví dụ:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Spring Boot sẽ nạp cấu hình profile tương ứng và ghi đè các giá trị mặc định. Cùng một artifact có thể được triển khai ở nhiều môi trường với metadata khác nhau.

Không nên build một artifact riêng chỉ để đổi server URL nếu externalized configuration đã đáp ứng được. Dùng cùng artifact giúp giảm khác biệt giữa các môi trường và đơn giản hóa việc truy vết build.

## 10. Dùng environment variables trong container và pipeline

Khi chạy bằng container hoặc nền tảng triển khai, có thể truyền metadata qua environment variables:

~~~text
SPRING_PROFILES_ACTIVE=prod
API_CONTRACT_VERSION=1.4.0
APP_ENV=production
PUBLIC_API_URL=https://api.example.com
~~~

Ví dụ Docker Compose:

~~~yaml
services:
  catalog-api:
    image: example/catalog-api:2.8.3
    environment:
      SPRING_PROFILES_ACTIVE: prod
      API_CONTRACT_VERSION: "1.4.0"
      APP_ENV: production
      PUBLIC_API_URL: https://api.example.com
~~~

Tag image `2.8.3` là application build version trong ví dụ; `API_CONTRACT_VERSION=1.4.0` là phiên bản hợp đồng API. Hai giá trị được quản lý riêng.

Pipeline nên cung cấp giá trị metadata từ nguồn có kiểm soát. Không nên để người dùng cuối gửi query parameter hoặc header tùy ý để thay đổi title, version hoặc server URL của OpenAPI document trong production.

Nếu mỗi request có thể làm document trả về metadata khác nhau, cache và contract testing sẽ khó dự đoán. Metadata môi trường nên ổn định trong suốt vòng đời của một deployment.

## 11. Thêm build version bằng Spring Boot BuildProperties

Spring Boot Maven Plugin có goal `build-info` để tạo `META-INF/build-info.properties` trong artifact. Ví dụ cấu hình Maven:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>build-info</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Với Gradle, Spring Boot Gradle Plugin hỗ trợ:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Khi file build info có trong artifact, Spring Boot có thể cung cấp bean `BuildProperties` với thông tin như artifact, group, name, version và time.

Không có build-info file thì bean này có thể không tồn tại. Vì vậy, không nên inject bắt buộc `BuildProperties` vào mọi ứng dụng nếu local/test profile không tạo metadata đó. Có thể dùng `ObjectProvider` hoặc cấu hình có điều kiện để xử lý trường hợp không có bean.

Build version nên được lấy từ artifact thực sự đang chạy, thay vì chỉ đọc một giá trị tự khai báo có thể khác với version đã đóng gói.

## 12. Đưa build metadata vào OpenAPI bằng vendor extension

Build version không nhất thiết phải thay thế API contract version. Nếu cần hiển thị build đang phục vụ tài liệu, có thể thêm vendor extension:

~~~java
@Configuration(proxyBeanMethods = false)
public class OpenApiConfiguration {

    @Bean
    public OpenAPI applicationOpenAPI(
            ApiMetadataProperties metadata,
            ObjectProvider<BuildProperties> buildPropertiesProvider) {

        OpenAPI openAPI = new OpenAPI()
            .info(new Info()
                .title(metadata.title())
                .description(metadata.description())
                .version(metadata.version()));

        if (metadata.serverUrl() != null) {
            openAPI.addServersItem(
                new Server()
                    .url(metadata.serverUrl().toString())
                    .description(metadata.environment())
            );
        }

        BuildProperties build = buildPropertiesProvider.getIfAvailable();

        if (metadata.exposeBuildMetadata()
                && build != null
                && StringUtils.hasText(build.getVersion())) {
            openAPI.addExtension(
                "x-application-version",
                build.getVersion()
            );
        }

        return openAPI;
    }
}
~~~

Trong ví dụ, `x-application-version` là vendor extension do tổ chức tự định nghĩa. Tiền tố `x-` được dùng cho extension riêng. Client hoặc công cụ chỉ hiểu extension này nếu được thiết kế để đọc nó.

Cần import:

- `org.springframework.boot.info.BuildProperties`
- `org.springframework.beans.factory.ObjectProvider`
- `org.springframework.util.StringUtils`
- Các model `OpenAPI`, `Info`, `Server` từ `io.swagger.v3.oas.models`

Extension chỉ được thêm khi cấu hình cho phép công bố build metadata và bean BuildProperties có sẵn. Mặc định nên tắt nếu tài liệu được công khai rộng rãi.

## 13. Source revision và GitProperties

Trong một số hệ thống, đội vận hành muốn biết build đang chạy được tạo từ commit nào. Spring Boot có thể đọc `git.properties` để cung cấp bean `GitProperties`, nếu build được cấu hình tạo file này.

Có thể thêm revision vào document theo cách có điều kiện:

~~~java
GitProperties git = gitPropertiesProvider.getIfAvailable();

if (metadata.exposeBuildMetadata()
        && git != null
        && StringUtils.hasText(git.getShortCommitId())) {
    openAPI.addExtension(
        "x-source-revision",
        git.getShortCommitId()
    );
}
~~~

Cần bổ sung tham số `ObjectProvider<GitProperties> gitPropertiesProvider` vào bean method và import `org.springframework.boot.info.GitProperties`.

Git metadata có thể chứa branch, commit ID, commit time hoặc thông tin repository. Chỉ công bố trường thật sự cần thiết. Branch name, repository URL hoặc commit message có thể tiết lộ thông tin nội bộ của tổ chức.

Nếu mục tiêu chỉ là hỗ trợ truy vết vận hành, có thể giữ revision trong actuator/build info hoặc log nội bộ thay vì đưa vào OpenAPI public. Việc có GitProperties bean phụ thuộc build plugin và cấu hình tạo `git.properties`; không giả định bean luôn tồn tại.

## 14. Không nhầm metadata môi trường với server URL

Trường `servers` của OpenAPI mô tả base URL mà client có thể dùng để gọi API. Trường `info.description` mô tả API. Một extension như `x-environment` có thể ghi tên môi trường, nhưng nó không thay thế Server Object.

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: "1.4.0"
servers:
  - url: https://api.example.com
    description: Production
x-environment: production
x-application-version: "2.8.3"
~~~

Ở đây:

- `info.version` là API contract version.
- `servers[0].url` là public base URL.
- `servers[0].description` giúp người đọc nhận diện server.
- `x-environment` là metadata riêng.
- `x-application-version` là build version.

Không phải công cụ nào cũng hiểu các extension tùy chỉnh. Các client generator thường dựa vào cấu trúc OpenAPI chuẩn; extension chỉ là thông tin bổ sung.

Nếu document được phát hành công khai, không nhất thiết phải thêm tên môi trường hoặc build version. Chỉ công bố những gì có ích cho client và không làm lộ topology hoặc thông tin triển khai.

## 15. Metadata riêng cho từng document group

Ứng dụng có thể tạo nhiều OpenAPI document bằng `GroupedOpenApi`. Ví dụ public API và partner API có thể có title, version hoặc server URL khác nhau.

~~~java
@Bean
public GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi -> {
            if (openApi.getInfo() != null) {
                openApi.getInfo()
                    .title("Partner API")
                    .version("2.1.0")
                    .description("API dành cho đối tác tích hợp.");
            }

            openApi.addExtension("x-audience", "partners");
        })
        .build();
}
~~~

Customizer được gắn với group để thay đổi document của nhóm đó. Cần xác minh cách customizer và OpenAPI bean toàn cục được áp dụng trong phiên bản Springdoc đang dùng.

Nếu mỗi group là một hợp đồng API riêng, có thể có API contract version riêng. Không nên đặt version khác nhau chỉ vì group chạy ở môi trường khác; version phản ánh hợp đồng, còn môi trường phản ánh nơi triển khai.

Khi dùng group-specific server URL, hãy kiểm tra endpoint `/v3/api-docs/partner` và đảm bảo server chỉ trỏ tới host mà audience của group được phép truy cập.

## 16. Quản lý nhiều môi trường mà không làm lộ endpoint nội bộ

Một số tổ chức muốn dùng cùng tài liệu ở local, staging và production. Có thể chọn một trong các cách:

- Sinh document theo profile để mỗi môi trường có server URL riêng.
- Công bố một server công khai và quản lý routing qua API gateway.
- Phân phối OpenAPI artifact đã chuẩn hóa trong CI, không lấy metadata từ request runtime.
- Tách document nội bộ và public bằng document group.

Không nên đưa tất cả hostname như `localhost`, `staging.internal`, `prod-db` vào một OpenAPI document public. Swagger UI có thể cho người dùng chọn server và gửi request tới các URL đó.

Nếu một document có nhiều Server Object, mỗi server phải thực sự được hỗ trợ và phù hợp với audience. Không đưa URL database, service discovery, admin host hoặc địa chỉ nội bộ vào `servers`.

Với môi trường production, cân nhắc cấu hình public base URL tường minh từ deployment manifest hoặc environment variable đã được quản trị, thay vì suy luận từ Host header không đáng tin.

## 17. Versioning API và thay đổi hợp đồng

`info.version` là nhãn phiên bản của API/document; nó không tự tạo versioned endpoint. Ví dụ:

- `/api/v1/products` và `/api/v2/products` là path versioning.
- `info.version: 1.4.0` mô tả phiên bản hợp đồng của document.
- `application.version: 2.8.3` mô tả phiên bản artifact.

Có thể dùng path versioning, media type versioning hoặc header-based versioning tùy chính sách. OpenAPI document nên mô tả đúng cách client chọn phiên bản API.

Khi thay đổi contract:

- Thêm optional field thường ít phá vỡ client hơn xóa field.
- Đổi tên property, đổi kiểu dữ liệu hoặc xóa operation có thể là breaking change.
- Thay đổi response status hoặc security requirement có thể ảnh hưởng client.
- Thay đổi path hoặc parameter name thường cần migration.
- Nâng application build version không nhất thiết là breaking API change.

Nên dùng contract diff hoặc OpenAPI compatibility checker trong CI để xác định thay đổi có ảnh hưởng client không. Chính sách tăng version cần được định nghĩa rõ, ví dụ dùng semantic versioning cho API contract nếu phù hợp với tổ chức.

Không để pipeline tự động tăng API version chỉ vì có commit mới. Hãy gắn API version với quyết định phát hành hợp đồng.

## 18. Dùng customizer để bổ sung metadata

Nếu metadata cần được thêm sau khi OpenAPI document đã được tạo, có thể dùng `OpenApiCustomizer`:

~~~java
@Bean
public OpenApiCustomizer environmentMetadataCustomizer(
        ApiMetadataProperties metadata) {
    return openApi -> {
        openApi.addExtension(
            "x-environment",
            metadata.environment()
        );
    };
}
~~~

Customizer phù hợp để thêm extension hoặc cập nhật một trường cụ thể. Tránh thay toàn bộ Info hoặc Servers nếu chỉ cần bổ sung một giá trị, vì có thể làm mất metadata đã được khai báo bằng bean hoặc annotation.

Nếu chỉ muốn áp dụng metadata cho một group, gắn customizer vào builder của group thay vì áp dụng toàn cục. Nếu cần áp dụng cho tất cả document, kiểm tra cơ chế global customizer của phiên bản Springdoc.

Extension phải bắt đầu bằng `x-`. Đừng tạo tên extension có ý nghĩa giống trường chuẩn như `version` hoặc `servers`; dùng tên riêng có namespace rõ ràng.

## 19. Kiểm tra metadata trong OpenAPI JSON

Sau khi ứng dụng khởi động, tải:

~~~http
GET /v3/api-docs
~~~

Kiểm tra các trường:

- `openapi` có đúng phiên bản đặc tả mà ứng dụng xuất.
- `info.title`, `info.description`, `info.version` đúng API contract.
- `servers` có URL công khai và scheme đúng.
- `servers[].description` mô tả đúng môi trường.
- Extension build metadata chỉ xuất hiện khi được bật.
- Không có hostname nội bộ, secret hoặc thông tin không dành cho audience.
- Document group có metadata riêng đúng như cấu hình.

Có thể dùng MockMvc để kiểm tra metadata:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Catalog API"))
    .andExpect(jsonPath("$.info.version").value("1.4.0"))
    .andExpect(jsonPath("$.servers[0].url")
        .value("https://api.example.com"));
~~~

Nếu ứng dụng có nhiều server, đừng giả định server mong muốn luôn ở index 0 trừ khi thứ tự được kiểm soát. Có thể parse JSON và tìm server theo URL hoặc description.

Kiểm tra cả document group:

~~~http
GET /v3/api-docs/partner
~~~

Swagger UI cũng nên được mở ở profile tương ứng để xác nhận title, version và server selector hiển thị đúng.

## 20. Kiểm tra cấu hình theo profile trong CI/CD

Có thể kiểm tra từng profile bằng integration test hoặc khởi động ứng dụng với cấu hình riêng:

| Profile | Giá trị cần xác minh |
|---|---|
| local | localhost hoặc URL local |
| dev | dev API base URL |
| staging | staging public URL |
| prod | production public URL |

Pipeline nên kiểm tra:

1. Artifact có đúng application build version.
2. API contract version được truyền đúng.
3. Profile được kích hoạt đúng.
4. Server URL thuộc allowlist của môi trường.
5. OpenAPI JSON có metadata phù hợp.
6. Không có hostname hoặc extension nội bộ bị công bố.
7. Contract diff không phát hiện breaking change ngoài dự kiến.

Có thể lưu OpenAPI JSON làm artifact của pipeline và so sánh với bản phát hành trước. Điều này giúp phát hiện metadata hoặc schema thay đổi bất ngờ trước khi publish tài liệu.

Không dùng cùng một snapshot OpenAPI nếu document có server URL thay đổi theo môi trường mà không có chính sách chuẩn hóa. Hãy quyết định CI so sánh contract thuần hay so sánh cả metadata deployment.

## 21. Các lỗi thường gặp khi quản lý version và metadata

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| info.version thay đổi mỗi lần build | Dùng application build version làm API contract version |
| Trường openapi bị hiểu là API version | Nhầm OpenAPI Specification version với Info.version |
| Server URL vẫn là localhost ở production | Profile hoặc PUBLIC_API_URL chưa được nạp |
| Swagger UI gọi hostname container | Server URL được suy luận từ request nội bộ hoặc cấu hình sai |
| Metadata khác nhau giữa các lần gọi | Giá trị bị lấy từ request header hoặc nguồn runtime không ổn định |
| BuildProperties không có bean | Artifact không chứa build-info.properties |
| GitProperties không có bean | Build chưa tạo git.properties |
| Document group có title/version sai | Group customizer hoặc cấu hình toàn cục ghi đè metadata |
| Extension không hiển thị trong Swagger UI | UI không trình bày vendor extension; kiểm tra JSON trực tiếp |
| Lộ branch hoặc commit nội bộ | Công bố Git metadata không cần thiết |
| Nhiều server xuất hiện ngoài dự kiến | Kết hợp bean, annotation và customizer chưa được kiểm soát |
| API version tăng dù contract không đổi | Pipeline tự động tăng version theo build number |
| OpenAPI document không phản ánh profile | Dùng sai profile hoặc property source precedence |

Khi điều tra, kiểm tra environment đang active, giá trị đã bind vào ConfigurationProperties và OpenAPI JSON cuối cùng. Không chỉ kiểm tra file YAML vì environment variable hoặc command-line argument có thể ghi đè cấu hình.

## 22. Nguyên tắc thiết kế metadata theo môi trường

Khi quản lý thông tin phiên bản và metadata cho Springdoc OpenAPI:

1. Phân biệt OpenAPI Specification version, API contract version và application build version.
2. Dùng Info.version cho phiên bản hợp đồng API.
3. Dùng BuildProperties để đọc build version từ artifact nếu cần.
4. Dùng GitProperties có điều kiện khi cần truy vết source revision.
5. Dùng ConfigurationProperties để gom metadata và externalized configuration.
6. Dùng Spring Profiles hoặc environment variables cho server URL theo môi trường.
7. Chọn một nguồn chính cho metadata toàn cục, tránh bean/annotation/customizer ghi đè không rõ ràng.
8. Chỉ đưa server URL mà audience thực sự được phép gọi vào document.
9. Không công bố secret, hostname nội bộ, branch hoặc revision nếu không cần.
10. Kiểm tra cả document mặc định và từng document group.
11. Dùng contract diff trong CI để phát hiện thay đổi ảnh hưởng client.
12. Kiểm tra OpenAPI JSON cuối cùng thay vì chỉ dựa trên cấu hình nguồn.

Thông tin phiên bản giúp client nhận biết hợp đồng API; build metadata giúp đội vận hành truy vết artifact; environment metadata cho biết client nên gọi server nào. Khi ba nhóm thông tin được quản lý riêng và được đưa vào OpenAPI từ cấu hình có kiểm soát, tài liệu Springdoc sẽ nhất quán giữa local, staging và production mà không làm lẫn phiên bản triển khai với phiên bản hợp đồng.

