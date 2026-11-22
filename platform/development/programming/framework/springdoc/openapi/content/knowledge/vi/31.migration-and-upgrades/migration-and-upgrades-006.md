# Chuyển artifact và package từ Springdoc v1 sang v2

Springdoc-openapi v2 là dòng phát hành dành cho Spring Boot 3 và hệ sinh thái Spring Framework 6/Jakarta EE. Khi nâng cấp từ Springdoc v1, công việc chính gồm thay artifact cũ bằng starter v2, cập nhật một số package Java, xử lý các thay đổi javax sang jakarta của Spring Boot 3 và xác minh lại OpenAPI document sau khi build.

Không nên xem migration là thao tác đổi số phiên bản dependency. V1 thường được dùng trong các ứng dụng Spring Boot 1/2; v2 được thiết kế cho Spring Boot 3 trở lên. Nếu dự án vẫn chạy Spring Boot 2, cần giữ dòng Springdoc v1 tương thích thay vì đưa starter v2 vào classpath. Nếu nâng cả Spring Boot và Springdoc, hãy xử lý các thay đổi nền tảng cùng một kế hoạch có kiểm soát.

## 1. Hiểu ranh giới tương thích giữa v1 và v2

| Thành phần | Springdoc v1 | Springdoc v2 |
|---|---|---|
| Nền tảng Spring Boot | Dòng Spring Boot 1/2, tùy phiên bản Springdoc | Spring Boot 3 trở lên |
| Spring Framework | Spring Framework 5 ở các cấu hình Boot 2 phổ biến | Spring Framework 6 |
| Java | Phụ thuộc phiên bản Spring Boot v1 đang dùng | Spring Boot 3 yêu cầu Java 17 trở lên |
| Namespace Jakarta | Chủ yếu API javax trong nền tảng Boot 2 | API Jakarta dùng namespace jakarta |
| Artifact tích hợp MVC/UI | Thường dùng springdoc-openapi-ui | Dùng springdoc-openapi-starter-webmvc-ui |
| Artifact tích hợp WebFlux/UI | Thường dùng springdoc-openapi-webflux-ui | Dùng springdoc-openapi-starter-webflux-ui |
| API không cần Swagger UI | Dùng module core/API phù hợp của v1 | Dùng starter-webmvc-api hoặc starter-webflux-api |
| GroupedOpenApi | org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |

Springdoc v2 không phải bản thay thế trực tiếp cho mọi ứng dụng Spring Boot 2. Trước khi đổi dependency, xác định phiên bản Spring Boot, Java và web stack của dự án. Nếu dự án chưa thể nâng lên Boot 3, chọn phiên bản v1 phù hợp với Boot hiện tại và lên kế hoạch nâng nền tảng riêng.

## 2. Kiểm tra nền tảng trước khi nâng cấp

Ghi lại các thông tin sau trước khi thay đổi:

- Phiên bản Spring Boot trong parent, plugin hoặc version catalog.
- Phiên bản Java được dùng khi compile, test và chạy production.
- Dự án dùng Spring MVC hay Spring WebFlux.
- Dự án có cần Swagger UI hay chỉ cần OpenAPI JSON/YAML.
- Các module Springdoc đang dùng, kể cả module hỗ trợ như security, data-rest hoặc Kotlin.
- Các package org.springdoc được import trong source.
- Các annotation Swagger 2 hoặc OpenAPI 3 đang dùng.
- Các thư viện bên thứ ba phụ thuộc Springfox, Swagger Core hoặc javax.

Với Maven, kiểm tra parent và property quản lý phiên bản trong pom.xml. Nếu dự án dùng Gradle, kiểm tra plugin Spring Boot, version catalog, convention plugin và dependency constraints. Không suy ra phiên bản thực tế chỉ từ một file nếu version được quản lý ở nơi khác.

## 3. Ánh xạ artifact UI từ v1 sang v2

Với ứng dụng Spring MVC cần Swagger UI, thay dependency v1:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.x.y</version>
</dependency>
~~~

bằng starter v2:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Với ứng dụng WebFlux cần Swagger UI, dùng starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Các giá trị 1.x.y và 2.x.y là placeholder minh họa. Thay bằng phiên bản đã được xác nhận tương thích với Spring Boot và Java của dự án.

Tên artifact thể hiện web stack. Không dùng starter WebMVC cho ứng dụng WebFlux thuần hoặc ngược lại. Nếu classpath đồng thời có spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot có thể chọn web application type theo điều kiện classpath; hãy xác định web stack thực sự của ứng dụng trước khi chọn starter Springdoc.

## 4. Chọn starter API khi không cần Swagger UI

Nếu chỉ cần endpoint OpenAPI JSON/YAML để pipeline tải hoặc công cụ khác tiêu thụ, không nhất thiết phải kéo theo Swagger UI assets.

Spring MVC API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Spring WebFlux API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Chọn một starter phù hợp với stack và mục đích của ứng dụng. Starter UI đã bao gồm phần API cần thiết cho stack tương ứng; không thêm đồng thời starter UI và starter API cùng stack chỉ để đảm bảo đủ dependency.

## 5. Cập nhật dependency trong Maven

Có thể khai báo phiên bản Springdoc trong pom.xml:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

Thay 2.x.y bằng phiên bản v2 đã được xác nhận tương thích với Spring Boot đang dùng. Nếu tổ chức quản lý version bằng Spring Boot dependency management hoặc Maven BOM nội bộ, hãy tuân theo quy ước của project. Không khai báo một version khác ở nhiều nơi khiến dependency mediation chọn phiên bản ngoài dự kiến.

Sau khi sửa, chạy:

~~~bash
mvn -U clean test
~~~

Nếu project dùng Maven Wrapper, ưu tiên mvnw hoặc mvnw.cmd theo hệ điều hành để giữ cùng Maven version trong CI và máy developer.

## 6. Cập nhật dependency trong Gradle

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y")
}
~~~

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation "org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y"
}
~~~

Quản lý version trong version catalog, convention plugin hoặc gradle.properties theo cấu trúc dự án. Với ứng dụng WebFlux, thay artifact bằng springdoc-openapi-starter-webflux-ui; nếu không cần UI, dùng starter API tương ứng.

Sau khi cập nhật:

~~~bash
./gradlew clean test
~~~

Nếu project dùng wrapper trên Windows, chạy gradlew.bat clean test.

## 7. Loại bỏ artifact v1 để tránh classpath trùng lặp

Khi đã chuyển sang starter v2, rà soát và loại các artifact v1 không còn cần thiết, ví dụ:

- springdoc-openapi-ui
- springdoc-openapi-webmvc-core
- springdoc-openapi-webflux-ui
- springdoc-openapi-webflux-core
- Các module Springdoc v1 được khai báo trực tiếp hoặc kéo theo transitively.

Danh sách trên là các artifact thường gặp, không phải danh sách đầy đủ cho mọi project. Dựa vào dependency tree để xác định artifact thực tế.

Không giữ cả starter v2 và các module core v1 trên cùng classpath. Việc trộn hai major version có thể gây lỗi class loading, method signature không tương thích, auto-configuration trùng hoặc document sinh ra không nhất quán.

Không xóa module add-on chỉ dựa vào tên. Hãy xác định chức năng nó cung cấp và chọn module/starter tương ứng trong dòng v2 theo tài liệu của phiên bản đang nâng cấp.

## 8. Di chuyển package của GroupedOpenApi

Một thay đổi source thường gặp là package của GroupedOpenApi.

V1:

~~~java
import org.springdoc.core.GroupedOpenApi;
~~~

V2:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
~~~

Ví dụ cấu hình group sau migration:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/internal/**")
                .build();
    }
}
~~~

Các method builder quen thuộc như group, pathsToMatch và pathsToExclude vẫn là cách cấu hình group phổ biến. Sau khi đổi import, kiểm tra lại filter để chắc chắn tập operation trong từng document không bị thay đổi ngoài ý muốn.

## 9. Di chuyển OpenApiCustomiser sang OpenApiCustomizer

Trong v1, interface thường được viết theo chính tả Anh-Anh là OpenApiCustomiser. Ở v2, tên interface dùng chính tả OpenApiCustomizer.

V1:

~~~java
import org.springdoc.core.customizers.OpenApiCustomiser;

@Bean
OpenApiCustomiser addDescription() {
    return openApi ->
            openApi.getInfo().setDescription("Tài liệu API");
}
~~~

V2:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer addDescription() {
    return openApi ->
            openApi.getInfo().setDescription("Tài liệu API");
}
~~~

Đây là thay đổi tên type và import. Logic customizer cần được kiểm tra lại vì một customizer có thể được áp dụng cho document mặc định hoặc group tùy loại bean và cách cấu hình. Nếu ứng dụng có nhiều group, xác nhận tất cả document đều nhận các chỉnh sửa dự kiến.

## 10. Rà soát OperationCustomizer và customizer khác

Các dự án có thể dùng thêm:

- OperationCustomizer để thay đổi từng operation.
- GlobalOpenApiCustomizer để áp dụng thay đổi chung cho các OpenAPI document.
- OpenApiCustomizer để tùy biến document theo phạm vi cấu hình.
- Các bean filter hoặc customizer riêng của ứng dụng.

Không đổi tên hoặc package của mọi customizer theo một quy tắc tự suy đoán. Tìm từng import org.springdoc, đọc lỗi compiler sau khi nâng dependency và đối chiếu API của phiên bản v2 được chọn. Một số type giữ tên, một số type hoặc package đã thay đổi.

Ví dụ minh họa một operation customizer:

~~~java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OperationCustomizationConfiguration {

    @Bean
    OperationCustomizer addOperationDescription() {
        return (operation, handlerMethod) -> {
            if (operation.getDescription() == null) {
                operation.setDescription("Operation do ứng dụng công bố.");
            }
            return operation;
        };
    }
}
~~~

Khi chuyển customizer hiện có, giữ nguyên điều kiện áp dụng, thứ tự xử lý và phạm vi group. Đừng thay một customizer toàn cục bằng customizer chỉ áp dụng cho một group nếu hợp đồng phụ thuộc vào metadata chung.

## 11. Giữ nguyên package annotation OpenAPI 3

Các annotation Swagger Core OpenAPI 3 thường dùng vẫn có package io.swagger.v3.oas.annotations, ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
~~~

Các annotation Operation, Parameter, Schema, ApiResponse, Tag, Hidden và OpenAPIDefinition không cần đổi sang package org.springdoc chỉ vì nâng Springdoc từ v1 lên v2.

Phân biệt các annotation OpenAPI 3 này với annotation Swagger 2 cũ trong package io.swagger.annotations, chẳng hạn Api, ApiOperation, ApiModel và ApiModelProperty. Nếu dự án còn annotation Swagger 2, cần migration riêng sang annotation OpenAPI 3; việc đổi starter không tự chuyển các annotation đó.

## 12. Xử lý javax sang jakarta khi nâng Spring Boot 3

Spring Boot 3 và Spring Framework 6 chuyển các API Jakarta EE sang namespace jakarta. Đây là thay đổi của nền tảng, không phải thay đổi riêng của springdoc.

Một số package thường cần chuyển:

| Trước (Boot 2) | Sau (Boot 3) |
|---|---|
| javax.validation.* | jakarta.validation.* |
| javax.servlet.* | jakarta.servlet.* |
| javax.persistence.* | jakarta.persistence.* |

Ví dụ validation:

~~~java
// Trước
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;

// Sau
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
~~~

Không thay mọi chuỗi javax một cách máy móc. Một số package thuộc Java SE vẫn dùng javax, ví dụ javax.sql và javax.crypto. Chỉ chuyển các API đã được Jakarta EE đổi namespace; kiểm tra dependency và tài liệu của từng thư viện.

Các thư viện bên thứ ba vẫn phát hành bản dùng javax có thể không tương thích với Spring Boot 3. Nâng hoặc thay các thư viện đó bằng bản hỗ trợ Jakarta trước khi kết luận lỗi thuộc Springdoc.

## 13. Kiểm tra cấu hình application properties

Các property Springdoc thường dùng trong v1 tiếp tục có tên tương ứng ở v2, chẳng hạn:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
~~~

Không nên đổi mọi property chỉ vì major version tăng. Tuy nhiên, hãy xác nhận property được hỗ trợ trong tài liệu đúng phiên bản v2, nhất là khi dự án dùng property ít phổ biến, custom path, group, cache, OAuth hoặc cấu hình Swagger UI nâng cao.

Sau migration, kiểm tra các URL mặc định:

- /v3/api-docs cho OpenAPI JSON.
- /v3/api-docs.yaml cho OpenAPI YAML.
- /swagger-ui.html hoặc path Swagger UI đã cấu hình.

Nếu có context path hoặc reverse proxy, kiểm tra URL public và forwarded headers như trong cấu hình triển khai của ứng dụng.

## 14. Chuyển cấu hình group và endpoint tài liệu

Nếu dự án đang sử dụng GroupedOpenApi, sau khi đổi package cần xác nhận endpoint group vẫn hoạt động. Ví dụ group tên public thường được truy cập qua:

~~~text
/v3/api-docs/public
/v3/api-docs.yaml/public
~~~

Kiểm tra:

- Group name có giữ nguyên không.
- pathsToMatch và pathsToExclude có đúng không.
- Package filter có còn chọn đúng controller không.
- Operation không bị thiếu hoặc xuất hiện ở nhiều group ngoài ý muốn.
- Customizer có được áp dụng vào đúng group không.
- Security rule cho endpoint group có còn phù hợp không.

Một lỗi import có thể khiến group bean không được tạo hoặc application context không khởi động. Một lỗi filter có thể khiến ứng dụng khởi động bình thường nhưng document group rỗng hoặc thiếu operation.

## 15. Xử lý module bổ sung

Ngoài starter MVC/WebFlux, dự án có thể dùng Springdoc cho các tích hợp như Spring Data REST, HATEOAS, security, Kotlin hoặc các thành phần đặc thù. Khi chuyển v2:

1. Liệt kê từng artifact v1 đang khai báo.
2. Xác định chức năng mà module cung cấp.
3. Tìm module/starter tương ứng trong dòng v2.
4. Kiểm tra ma trận tương thích với Spring Boot và Java.
5. Chỉ giữ một phiên bản Swagger Core phù hợp với starter.
6. Chạy test cho tính năng add-on, không chỉ test endpoint docs mặc định.

Không đoán tên artifact v2 chỉ bằng cách thêm tiền tố starter vào tên cũ. Cấu trúc module đã được tổ chức lại; đối chiếu danh sách module trong tài liệu release tương ứng.

## 16. Kiểm tra dependency tree và xung đột phiên bản

Sau khi đổi starter, xem dependency tree để phát hiện artifact cũ còn được kéo vào.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
~~~

Kiểm tra:

- Chỉ có một major line Springdoc trong runtime classpath.
- Không còn starter Springfox/Springdoc v1 ngoài ý muốn.
- Swagger Core và Swagger annotations dùng bộ phiên bản tương thích.
- Không có thư viện cũ kéo theo javax API xung đột với Jakarta.
- Không override một dependency transitive bằng version tùy tiện nếu chưa kiểm tra compatibility.

Không thêm trực tiếp swagger-core, swagger-annotations hoặc swagger-annotations-jakarta chỉ để chữa lỗi compile nếu starter đã quản lý các dependency đó. Trước tiên xác định dependency nào thiếu hoặc bị conflict.

## 17. Tìm và sửa import trong source

Có thể tìm package cũ trong source:

~~~bash
rg -n "org\.springdoc\.core\.GroupedOpenApi|OpenApiCustomiser|io\.swagger\.annotations|javax\.validation|javax\.servlet|javax\.persistence" .
~~~

Sau đó phân loại kết quả:

| Kết quả tìm kiếm | Việc cần làm |
|---|---|
| org.springdoc.core.GroupedOpenApi | Đổi sang org.springdoc.core.models.GroupedOpenApi |
| OpenApiCustomiser | Kiểm tra và đổi sang OpenApiCustomizer cùng package v2 tương ứng |
| io.swagger.annotations.* | Migration annotation Swagger 2 sang OpenAPI 3 nếu còn dùng |
| javax.validation.* | Chuyển sang jakarta.validation.* khi nâng Boot 3 |
| javax.servlet.* | Chuyển sang jakarta.servlet.* khi nâng Boot 3 |
| javax.persistence.* | Chuyển sang jakarta.persistence.* khi nâng Boot 3 |

Không chạy thay thế hàng loạt trên mọi file mà chưa xem ngữ cảnh. Ví dụ javax.sql.DataSource không đổi thành jakarta.sql.DataSource; package javax.sql thuộc Java SE.

## 18. Ví dụ cấu hình OpenAPI sau migration

Một cấu hình đơn giản trên v2 có thể dùng GroupedOpenApi và OpenApiCustomizer:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .build();
    }

    @Bean
    OpenApiCustomizer customizeOpenApiInfo() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }
            openApi.getInfo()
                    .description("Tài liệu API công khai của ứng dụng.");
        };
    }
}
~~~

Đoạn code minh họa package import chính trong v2. Nếu customizer cần áp dụng cho tất cả group, hãy chọn interface/bean có phạm vi toàn cục phù hợp với phiên bản đang dùng và kiểm tra output của từng group.

## 19. Kiểm tra sau khi build

Sau khi source compile:

~~~bash
mvn clean verify
~~~

Hoặc:

~~~bash
./gradlew clean check
~~~

Khởi động ứng dụng và kiểm tra endpoint JSON:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi-v2.json
~~~

Kiểm tra YAML:

~~~bash
curl -fS http://localhost:8080/v3/api-docs.yaml -o openapi-v2.yaml
~~~

Kiểm tra document có thể parse:

~~~bash
jq -e '.openapi and .info and .paths' openapi-v2.json
~~~

Sau đó mở Swagger UI nếu starter UI được sử dụng. Nếu chỉ dùng starter API, không kỳ vọng /swagger-ui.html hoạt động.

## 20. So sánh hợp đồng trước và sau migration

Nâng major version có thể làm thay đổi cách springdoc phát hiện controller, suy luận schema hoặc áp dụng customizer. Vì vậy, nên lưu OpenAPI JSON của v1 làm baseline trước khi chuyển và so sánh với document v2.

Các điểm nên kiểm tra:

- Danh sách path và HTTP method.
- operationId, summary và description.
- Path, query, header và cookie parameter.
- Request body, required flag và media type.
- Response status, headers và content type.
- Component schema, $ref, enum và nullability.
- Security scheme và security requirement.
- Group membership và document group.
- servers, tags và external documentation.

Dùng công cụ diff hiểu OpenAPI thay vì chỉ so sánh văn bản byte-by-byte. Một số khác biệt về thứ tự key hoặc formatting không làm thay đổi hợp đồng; ngược lại, việc mất một response hoặc thay đổi required field có thể là breaking change dù file chỉ khác vài dòng.

## 21. Kiểm tra security và Swagger UI

Sau khi thay starter, kiểm tra lại security chain cho các endpoint:

- /v3/api-docs và /v3/api-docs/**
- /v3/api-docs.yaml và endpoint YAML group nếu có.
- /swagger-ui.html.
- /swagger-ui/** static assets.

Starter v2 không tự quyết định chính sách ai được đọc tài liệu. Nếu trước đó dự án dùng Spring Security để permit hoặc protect docs, xác nhận matcher vẫn khớp đường dẫn thực tế.

Nếu Swagger UI tải trang nhưng không hiện operation, kiểm tra request đến /v3/api-docs/swagger-config và spec URL trong browser Network. Nếu API docs hoạt động nhưng UI 404, xác nhận dự án có starter UI chứ không phải starter API-only.

## 22. Lỗi thường gặp khi chuyển v1 sang v2

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Maven/Gradle không resolve artifact | Vẫn dùng tên artifact v1 hoặc sai repository/version | Chuyển sang starter v2 đúng web stack và kiểm tra repository |
| Spring Boot 2 không khởi động với starter v2 | Springdoc v2 dành cho Spring Boot 3+ | Giữ Springdoc v1 tương thích hoặc nâng nền tảng |
| GroupedOpenApi không tìm thấy | Import package v1 | Dùng org.springdoc.core.models.GroupedOpenApi |
| OpenApiCustomiser không tìm thấy | Interface đã đổi spelling/name | Dùng OpenApiCustomizer theo API v2 |
| Lỗi javax/jakarta | Dependency hoặc source còn namespace cũ | Chuyển API Jakarta tương ứng và nâng thư viện bên thứ ba |
| NoSuchMethodError hoặc ClassNotFoundException | Trộn module v1/v2 hoặc Swagger Core không tương thích | Xem dependency tree và loại version conflict |
| Swagger UI 404 nhưng JSON hoạt động | Dùng starter API-only hoặc proxy chưa route UI assets | Dùng starter UI nếu cần hoặc cập nhật proxy |
| API docs 404 | API docs bị tắt, sai path hoặc starter không đúng stack | Kiểm tra property, context path và starter |
| Group document rỗng | Filter hoặc package scan thay đổi | Kiểm tra GroupedOpenApi và các điều kiện match |
| Customizer không tác động lên group | Bean có phạm vi áp dụng khác dự kiến | Chọn customizer toàn cục phù hợp và test từng group |
| Schema khác sau migration | Khác biệt introspection, Jakarta validation hoặc Jackson | So sánh OpenAPI JSON và test payload runtime |
| UI mở nhưng spec request bị 401/403 | Security matcher hoặc auth config không còn đúng | Kiểm tra filter chain và quyền truy cập docs |

## 23. Quy trình migration theo từng bước

1. Chốt phiên bản Spring Boot, Java và web stack hiện tại.
2. Lưu OpenAPI JSON/YAML v1 làm baseline.
3. Lập danh sách Springdoc artifact và import org.springdoc.
4. Xác định các dependency add-on đang sử dụng.
5. Nâng Spring Boot lên phiên bản 3.x tương thích và đặt Java tối thiểu 17 nếu dự án chưa ở nền tảng này.
6. Chuyển các API Jakarta EE từ javax sang jakarta theo từng package thực sự thuộc Jakarta.
7. Thay artifact v1 bằng starter v2 đúng MVC/WebFlux và UI/API.
8. Loại các module v1 trùng lặp khỏi dependency graph.
9. Cập nhật GroupedOpenApi và OpenApiCustomiser cùng các import bị thay đổi.
10. Giữ annotation OpenAPI 3 đúng package và xử lý riêng annotation Swagger 2 còn tồn tại.
11. Build và sửa lỗi compile/runtime do dependency hoặc namespace.
12. Kiểm tra endpoint JSON/YAML, Swagger UI và từng group.
13. So sánh document v2 với baseline v1 và chạy contract/integration test.
14. Chỉ triển khai khi schema, security và operation quan trọng đã được xác nhận.

Nếu tổ chức chia việc nâng Spring Boot và Springdoc thành nhiều pull request, giữ mỗi bước có thể build và test được. Tuy nhiên, không chạy Springdoc v2 trên nền Spring Boot 2 chỉ để tạo trạng thái trung gian.

## 24. Kế hoạch rollback

Trước khi triển khai, lưu:

- Commit hoặc tag source trước migration.
- Dependency lockfile hoặc dependency tree của bản cũ.
- OpenAPI JSON/YAML baseline.
- Cấu hình Spring Security và proxy liên quan docs.
- Kết quả build/test trước migration.

Nếu bản v2 gây lỗi production, rollback cả bộ thay đổi nền tảng/dependency/source tương ứng về một commit đã xác nhận hoạt động. Không chỉ hạ version Springdoc về v1 trong khi vẫn giữ Spring Boot 3 và Jakarta-only dependencies nếu tổ hợp đó không tương thích.

## 25. Checklist hoàn tất

- [ ] Spring Boot và Java nằm trong dải tương thích của Springdoc v2 đã chọn.
- [ ] Ứng dụng dùng đúng starter MVC hoặc WebFlux.
- [ ] Đã chọn starter UI hoặc API theo nhu cầu.
- [ ] Artifact Springdoc v1 không còn trên runtime classpath.
- [ ] Không trộn Swagger Core major version không tương thích.
- [ ] GroupedOpenApi dùng package v2.
- [ ] OpenApiCustomiser đã được xử lý thành OpenApiCustomizer nếu dự án dùng.
- [ ] Các customizer khác đã được compile và kiểm tra phạm vi áp dụng.
- [ ] Annotation OpenAPI 3 vẫn dùng package io.swagger.v3.oas.annotations.
- [ ] Annotation Swagger 2 còn sót đã được rà soát.
- [ ] Các API Jakarta EE đã chuyển sang jakarta; Java SE javax được giữ nguyên.
- [ ] Build và test thành công.
- [ ] /v3/api-docs và /v3/api-docs.yaml hoạt động.
- [ ] Swagger UI hoạt động nếu đã chọn starter UI.
- [ ] Group, security và customizer cho kết quả như trước.
- [ ] OpenAPI document v2 đã được so sánh với baseline v1.

## 26. Nguyên tắc thiết kế

- Chọn Springdoc v2 cùng Spring Boot 3+, không ghép v2 vào ứng dụng Boot 2.
- Dùng starter theo web stack và nhu cầu UI/API.
- Loại dependency v1 còn sót để tránh trộn major version.
- Cập nhật GroupedOpenApi sang package org.springdoc.core.models.
- Chuyển OpenApiCustomiser sang OpenApiCustomizer và xác nhận phạm vi customizer.
- Giữ annotation OpenAPI 3 trong package io.swagger.v3.oas.annotations.
- Xử lý javax theo từng API Jakarta EE, không thay thế chuỗi máy móc.
- Kiểm tra add-on module trong tài liệu v2 thay vì đoán tên artifact.
- Xem dependency tree để tìm xung đột trước khi thêm override.
- So sánh document và runtime behavior sau migration, không chỉ dựa vào build thành công.

## Kết luận

Chuyển Springdoc v1 sang v2 là một phần của quá trình chuyển sang Spring Boot 3 và Jakarta. Hãy thay artifact cũ bằng starter v2 đúng MVC/WebFlux và nhu cầu UI/API, cập nhật package GroupedOpenApi, đổi OpenApiCustomiser sang OpenApiCustomizer khi sử dụng, đồng thời rà soát dependency và namespace Jakarta. Các annotation OpenAPI 3 trong io.swagger.v3.oas.annotations vẫn được dùng; các annotation Swagger 2 và API javax cần được xử lý riêng theo mục đích. Hoàn tất migration bằng dependency tree, build/test, kiểm tra endpoint tài liệu, group, Swagger UI, security và so sánh OpenAPI document v2 với baseline v1.

## Tài liệu tham khảo

- [springdoc-openapi documentation](https://springdoc.org/)
- [springdoc-openapi migration guide](https://springdoc.org/#migrating-from-springdoc-openapi-v1)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Framework 6.0 Overview](https://docs.spring.io/spring-framework/reference/overview.html)
