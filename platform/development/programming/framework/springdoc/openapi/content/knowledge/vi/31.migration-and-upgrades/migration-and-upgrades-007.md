# Kiểm tra thay đổi Spring Boot, Jakarta và phụ thuộc Swagger Core

Khi nâng cấp một ứng dụng Spring Boot có springdoc-openapi, cần kiểm tra đồng thời phiên bản nền tảng Spring, namespace Jakarta và các thư viện Swagger Core nằm trong dependency graph. Ba nhóm này liên quan trực tiếp với nhau: Spring Boot quyết định thế hệ Spring Framework và Jakarta API; Springdoc cung cấp tích hợp phù hợp với thế hệ đó; Swagger Core cung cấp annotation, model và bộ xử lý OpenAPI mà Springdoc sử dụng.

Springdoc tự phân tích controller, cấu hình Spring, kiểu dữ liệu và annotation để tạo OpenAPI JSON/YAML, sau đó Swagger UI có thể hiển thị tài liệu. Nếu chỉ đổi phiên bản Spring Boot nhưng vẫn giữ starter Springdoc hoặc Swagger Core của thế hệ cũ, ứng dụng có thể không biên dịch, không khởi động hoặc tạo tài liệu sai.

## 1. Ba trục tương thích cần kiểm tra

Trước khi sửa dependency, hãy xác định ba trục:

| Trục | Cần xác định | Ví dụ |
| --- | --- | --- |
| Spring Boot và Java | Phiên bản Boot, Java tối thiểu, Spring Framework được quản lý | Boot 3 cần Java 17 và Spring Framework 6 |
| Jakarta API | Thế hệ Jakarta EE, Servlet API và package namespace | Boot 3 dùng Servlet 6 và jakarta.servlet |
| Springdoc và Swagger Core | Nhánh Springdoc, starter, biến thể Swagger Core và phiên bản annotation | Boot 3 dùng Springdoc 2.x và Swagger Core Jakarta |

Không nâng từng thư viện độc lập theo phiên bản mới nhất. Hãy chọn một tổ hợp đã được Springdoc và Spring Boot kiểm thử tương thích, sau đó để BOM quản lý các dependency liên quan khi có thể.

## 2. Bản đồ tương thích Spring Boot và Springdoc

Theo compatibility matrix của Springdoc tại thời điểm biên soạn:

| Spring Boot | Springdoc tương thích |
| --- | --- |
| 4.1.x | 3.1.x đến 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x đến 2.10.x |
| 3.4.x | 2.7.x đến 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x đến 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x đến 2.1.x |
| 2.7.x | Springdoc 1.6.0 trở lên trong nhánh 1.x |

Các dải phiên bản cho biết những nhánh Springdoc đã được xây dựng với nhánh Spring Boot tương ứng. Khi bắt đầu dự án mới hoặc nâng cấp trong cùng một nhánh, ưu tiên bản maintenance mới nhất nằm trong dải tương thích thay vì chọn phiên bản vượt khỏi matrix.

Springdoc 1.8.0 là bản open-source cuối cùng hỗ trợ Spring Boot 2.x và 1.x. Đây là nhánh legacy; không dùng artifact 1.x cho ứng dụng Boot 3 hoặc Boot 4. Springdoc 2.x dành cho Boot 3, còn Springdoc 3.x dành cho Boot 4.

## 3. Những thay đổi nền tảng từ Spring Boot 2 lên 3

Spring Boot 3 là một lần nâng cấp nền tảng lớn:

- Java tối thiểu chuyển lên Java 17.
- Spring Framework chuyển từ 5.x lên 6.x.
- Spring Boot 3 dùng Jakarta EE 10 API level.
- Servlet API chuyển sang 6.0; JPA chuyển sang 3.1.
- Các package Jakarta EE đổi từ namespace javax sang jakarta.
- Những API, class và property đã deprecated trong Boot 2 có thể bị loại bỏ.

Vì Springdoc v1 được xây dựng cho thế hệ Boot 2, nâng ứng dụng lên Boot 3 đồng nghĩa phải đổi sang Springdoc 2.x và các starter mới. Không nên chỉ đổi parent version rồi giữ nguyên toàn bộ dependency cũ.

Trước khi nâng, đưa ứng dụng Boot 2 lên bản maintenance mới nhất của nhánh 2.7.x nếu lộ trình dự án cho phép. Bước này giúp xử lý deprecation và dependency cũ trước khi thay đổi Spring Framework/Jakarta.

## 4. Những thay đổi nền tảng từ Spring Boot 3 lên 4

Spring Boot 4 dựa trên Spring Framework 7 và Jakarta EE 11:

| Thành phần | Spring Boot 3 | Spring Boot 4 |
| --- | --- | --- |
| Java tối thiểu | 17 | 17 |
| Spring Framework | 6.x | 7.x |
| Jakarta EE | 10 | 11 |
| Servlet API | 6.0 | 6.1 |
| JPA | 3.1 | 3.2 |
| Bean Validation | 3.0 | 3.1 |
| Springdoc | 2.x | 3.x |

Boot 4 tiếp tục dùng namespace Jakarta. Do đó, không có một đợt đổi tên javax sang jakarta mới như khi chuyển từ Boot 2 lên Boot 3; trọng tâm là cập nhật phiên bản Jakarta API, Spring Framework và các thư viện tương thích.

Boot 4 cũng loại bỏ một số class, method và configuration property đã deprecated trong Boot 3. Hãy xử lý cảnh báo trước khi nâng để tránh lỗi compile hoặc lỗi khởi động sau khi các API đó bị xóa.

Một thay đổi đáng chú ý khác là Spring Boot 4 ưu tiên Jackson 3. Jackson 3 chuyển phần lớn group/package từ com.fasterxml.jackson sang tools.jackson; riêng jackson-annotations vẫn giữ group và package com.fasterxml.jackson.core / com.fasterxml.jackson.annotation. Nếu ứng dụng hoặc thư viện tùy chỉnh dùng trực tiếp ObjectMapper, serializer hoặc Jackson module, cần rà soát tương thích riêng.

## 5. Phân biệt javax và jakarta

Jakarta EE đổi namespace từ javax sang jakarta. Ví dụ:

| API cũ | API Jakarta |
| --- | --- |
| javax.servlet.Filter | jakarta.servlet.Filter |
| javax.servlet.http.HttpServletRequest | jakarta.servlet.http.HttpServletRequest |
| javax.validation.Valid | jakarta.validation.Valid |
| javax.validation.constraints.NotNull | jakarta.validation.constraints.NotNull |
| javax.persistence.Entity | jakarta.persistence.Entity |
| javax.annotation.PostConstruct | jakarta.annotation.PostConstruct |
| javax.transaction.Transactional | jakarta.transaction.Transactional |
| javax.ws.rs.Path | jakarta.ws.rs.Path |

Đây là thay đổi package và binary type, không chỉ là đổi tên import. Một filter được biên dịch với javax.servlet.Filter không thể được container Jakarta gọi như một jakarta.servlet.Filter. Tương tự, validation provider dùng namespace cũ không tự hiểu annotation Jakarta trên DTO.

Không thay thế mọi chuỗi javax trong source code một cách mù quáng. Một số package thuộc Java SE vẫn giữ namespace javax, chẳng hạn javax.sql, javax.crypto, javax.net và javax.xml. Chỉ chuyển các API thuộc Java EE/Jakarta EE đã được đổi namespace.

## 6. Rà soát dependency Jakarta trực tiếp và gián tiếp

Khi nâng Boot 3 hoặc Boot 4, cần kiểm tra cả dependency khai báo trực tiếp lẫn dependency bắc cầu:

- Servlet API và embedded server.
- Bean Validation API và validation provider.
- JPA API, Hibernate và persistence provider.
- Jakarta Annotations, Transactions và REST API nếu ứng dụng sử dụng.
- Các thư viện filter, security, servlet initializer hoặc integration cũ.
- Plugin build, annotation processor và test fixture.

Ví dụ dependency Servlet cho thế hệ Jakarta:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Trong ứng dụng Spring Boot thông thường, starter web và dependency management đã cung cấp phiên bản phù hợp. Chỉ khai báo Servlet API trực tiếp khi mã nguồn hoặc module cần compile với API đó; không thêm phiên bản tùy ý để ghi đè dependency do Boot quản lý.

Nếu dependency tree còn javax.servlet:javax.servlet-api trong runtime của ứng dụng Boot 3/4, cần xác định thư viện nào kéo nó vào. Có thể phải nâng thư viện đó lên bản Jakarta hoặc loại bỏ dependency cũ. Không thêm đồng thời hai API chỉ để làm cho compiler hết báo lỗi.

## 7. Springdoc v1 đổi sang v2: thay starter và module

Springdoc v2 đổi tên các module theo mô hình starter. Một số ánh xạ quan trọng:

| Springdoc v1 | Springdoc v2 |
| --- | --- |
| springdoc-openapi-common | springdoc-openapi-starter-common |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |

Các module hỗ trợ như Javadoc, Kotlin, Data REST, Security, HATEOAS và Groovy được tích hợp vào starter-common trong mô hình v2 theo migration guide. Không giữ lại các module v1 chỉ vì tên tương tự; hãy kiểm tra chức năng hiện tại đã nằm trong starter-common hay cần module mở rộng riêng.

Ví dụ trước đây dùng Swagger UI trên Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.0</version>
</dependency>
~~~

Sau khi chuyển sang Boot 3, dùng starter v2:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu ứng dụng dùng WebFlux, chọn springdoc-openapi-starter-webflux-ui. Nếu chỉ cần OpenAPI JSON/YAML, dùng biến thể webmvc-api hoặc webflux-api để tránh đưa UI vào runtime.

## 8. Những thay đổi package và class của Springdoc

Ngoài artifact, một số class chuyển package hoặc đổi tên:

| Springdoc v1 | Springdoc v2 |
| --- | --- |
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Ví dụ import GroupedOpenApi:

~~~java
// Springdoc v1
import org.springdoc.core.GroupedOpenApi;

// Springdoc v2
import org.springdoc.core.models.GroupedOpenApi;
~~~

Ví dụ customizer:

~~~java
// Springdoc v1
import org.springdoc.core.customizers.OpenApiCustomiser;

// Springdoc v2
import org.springdoc.core.customizers.OpenApiCustomizer;
~~~

Tên interface đổi từ OpenApiCustomiser sang OpenApiCustomizer. Nếu ứng dụng có bean customizer hoặc method nhận kiểu này, hãy đổi cả import lẫn khai báo type.

## 9. Springdoc v2 lên v3 khi chuyển sang Boot 4

Springdoc v3 là nhánh dành cho Spring Boot 4. Các starter tiếp tục dùng quy tắc tên webmvc/webflux và api/ui:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Ví dụ trên phù hợp với nhánh Boot 4.1.x theo compatibility matrix hiện hành. Với Boot 4.0.x, dùng Springdoc 3.0.x. Không đưa Springdoc 3.2.x vào Boot 3.5 chỉ vì đây là bản mới hơn; Boot 3.5.x thuộc nhánh Springdoc 2.8.x đến 2.10.x.

Khi chuyển từ Springdoc 2 sang 3, không nên giả định mọi dependency bắc cầu của ứng dụng vẫn giữ nguyên. Hãy kiểm tra starter, Spring Framework 7, Jakarta EE 11, Swagger Core Jakarta và Jackson theo dependency management của Boot 4.

## 10. Swagger Core có hai dòng artifact javax và Jakarta

Swagger Core 2.x cung cấp annotation, model và bộ xử lý OpenAPI. Từ phiên bản 2.1.7, Swagger Core có thêm một bộ artifact với hậu tố -jakarta song song với artifact không hậu tố:

| Namespace | Artifact ví dụ |
| --- | --- |
| javax | swagger-core, swagger-annotations, swagger-models, swagger-integration |
| Jakarta | swagger-core-jakarta, swagger-annotations-jakarta, swagger-models-jakarta, swagger-integration-jakarta |

Các artifact Jakarta được xây dựng cho hệ sinh thái Jakarta EE. Ứng dụng Spring Boot 3/4 nên dùng bộ Jakarta tương ứng khi dependency cần Swagger Core tích hợp Jakarta. Springdoc starter phù hợp thường đã kéo đúng dependency này; không thêm swagger-core-jakarta thủ công nếu không có nhu cầu trực tiếp.

Không trộn swagger-core với swagger-core-jakarta hoặc swagger-annotations với swagger-annotations-jakarta trong cùng runtime classpath. Hai dòng artifact có thể chứa class trùng tên nhưng phụ thuộc namespace khác nhau. Khi classloader chọn nhầm biến thể, ứng dụng có thể lỗi linkage hoặc tích hợp Servlet/JAX-RS không đúng.

## 11. Import Swagger annotation có đổi không?

Một điểm dễ nhầm: hậu tố -jakarta nằm ở artifact Maven, không có nghĩa package Swagger annotation đổi từ io.swagger sang jakarta.swagger.

Ví dụ import vẫn là:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
~~~

Package annotation OpenAPI v3 vẫn là io.swagger.v3.oas.annotations. Biến thể Jakarta của Swagger Core cung cấp các class annotation cùng package/API để tương thích với thế hệ Jakarta. Phần cần đổi namespace trong source thường là Servlet, Validation, Persistence hoặc Jakarta API khác, không phải import @Operation hay @Schema.

Swagger Core 1.5.x thuộc thế hệ Swagger 2.0/OpenAPI 2.0. Swagger Core 2.x tạo OpenAPI 3.x; từ 2.2.0 có hỗ trợ OpenAPI 3.1. Không nhầm phiên bản thư viện Swagger Core với version OpenAPI mà document sinh ra khai báo.

## 12. Tránh pin Swagger Core độc lập ngoài dependency management

Springdoc khai báo phiên bản Swagger Core tương thích trong dependency graph của starter. Nếu dự án thêm trực tiếp swagger-core hoặc swagger-annotations với version khác, có thể ghi đè version mà Springdoc đã kiểm thử.

Trước tiên, chỉ khai báo starter Springdoc:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Chỉ thêm Swagger Core trực tiếp khi mã ứng dụng thật sự gọi API của Swagger Core, chẳng hạn dùng ModelConverters hoặc một integration riêng. Khi đó:

- Chọn đúng artifact Jakarta cho ứng dụng Boot 3/4.
- Dùng phiên bản Swagger Core mà Springdoc đang tương thích.
- Đồng bộ swagger-core-jakarta, swagger-models-jakarta, swagger-annotations-jakarta và swagger-integration-jakarta.
- Tránh để một module Jakarta kéo theo module javax khác phiên bản.
- Kiểm tra dependency tree sau khi thêm dependency.

Nếu cần quản lý Swagger Core ở nhiều module, cân nhắc swagger-bom của Swagger Core để giữ các module cùng release. Không dùng BOM hoặc version của Swagger Core để ghi đè ngẫu nhiên phiên bản mà Springdoc đã chọn.

## 13. Kiểm tra dependency graph bằng Maven

Dependency tree giúp xác định module nào kéo phiên bản cũ vào:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Kiểm tra riêng Servlet và Jakarta:

~~~bash
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api,jakarta.servlet:jakarta.servlet-api
~~~

Kiểm tra cả Jackson khi nâng lên Boot 4:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core,tools.jackson,com.fasterxml.jackson.module
~~~

Hãy đọc đường dẫn dependency từ ứng dụng đến artifact đáng ngờ. Ví dụ, nếu swagger-core không hậu tố xuất hiện qua một thư viện cũ, xác định thư viện đó trước khi thêm exclusion. Exclusion chỉ có tác dụng khi bạn biết dependency thay thế nào cung cấp đúng chức năng.

## 14. Kiểm tra dependency graph bằng Gradle

Xem runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm dependency Swagger Core:

~~~bash
./gradlew dependencyInsight \
  --dependency swagger-core \
  --configuration runtimeClasspath
~~~

Tìm Servlet API:

~~~bash
./gradlew dependencyInsight \
  --dependency servlet-api \
  --configuration runtimeClasspath
~~~

Kiểm tra Jackson khi chuyển sang Boot 4:

~~~bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Gradle dependencyInsight cho biết phiên bản được chọn, dependency nào yêu cầu nó và vì sao một version khác bị thay thế. Đây là cách nhanh để xác định xung đột do dependency trực tiếp, constraint hoặc platform.

## 15. Rà soát package trong source code

Sau khi cập nhật dependency, tìm những import thuộc Jakarta EE cũ:

~~~bash
rg -n "javax\\.(servlet|validation|persistence|annotation|transaction|ws\\.rs)" src
~~~

Kiểm tra package Jakarta mới:

~~~bash
rg -n "jakarta\\.(servlet|validation|persistence|annotation|transaction|ws\\.rs)" src
~~~

Không thay thế hàng loạt javax. Rà soát từng import theo API thực tế và kiểm tra thư viện thứ ba có hỗ trợ Jakarta hay không. Với mã dùng cả Java SE và Jakarta EE, một số import javax cần được giữ nguyên.

Sau khi đổi import, kiểm tra:

- Filter, Servlet, Listener và HttpServletRequest.
- @Valid, @NotNull, @NotBlank và Validation provider.
- JPA entity, repository và persistence provider.
- Annotation lifecycle như @PostConstruct.
- Transaction manager và transaction annotation.
- JAX-RS API nếu ứng dụng dùng Jersey hoặc REST integration khác.
- Test fixture, mock và thư viện dùng reflection trên annotation.

## 16. Kiểm tra thay đổi Jackson khi lên Boot 4

Boot 4 ưu tiên Jackson 3. Phần lớn package chuyển từ com.fasterxml.jackson sang tools.jackson, nhưng jackson-annotations vẫn giữ package com.fasterxml.jackson.annotation.

Ví dụ khi ứng dụng trực tiếp sử dụng mapper:

~~~java
// Jackson 2
import com.fasterxml.jackson.databind.ObjectMapper;

// Jackson 3
import tools.jackson.databind.ObjectMapper;
~~~

Không áp dụng thay đổi import này cho mọi annotation. Ví dụ @JsonProperty, @JsonIgnore và @JsonInclude thuộc jackson-annotations và vẫn dùng:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
~~~

Khi chuyển Boot 4, kiểm tra custom serializer/deserializer, ObjectMapper bean, Jackson module, Kotlin module, Java Time module và Springdoc schema resolution. Nếu ứng dụng có thư viện chỉ hỗ trợ Jackson 2, xác định rõ khả năng tương thích; Spring Boot có module spring-boot-jackson2 như một giải pháp chuyển tiếp nhưng module này đã ở trạng thái deprecated và dự kiến bị loại bỏ trong tương lai.

Schema OpenAPI có thể thay đổi khi Jackson thay đổi cách nhận diện property, naming strategy, module hoặc serialization. Vì vậy cần so sánh document trước/sau nâng cấp, đặc biệt với DTO có custom serializer hoặc @JsonView.

## 17. Lưu ý riêng khi nâng lên Spring Boot 3.2

Spring Boot 3.2 thay đổi cơ chế khám phá tên parameter. Nếu ứng dụng không biên dịch với tùy chọn giữ tên parameter, Springdoc có thể không suy ra được tên query/path parameter từ bytecode.

Với Maven Compiler Plugin, bật tùy chọn parameters:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Với Gradle Java plugin:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Sau khi bật, kiểm tra OpenAPI document để chắc chắn parameter name không bị mất hoặc biến thành tên không mong muốn. Nếu controller đã khai báo name tường minh trong @RequestParam hoặc @PathVariable, tài liệu có thể ít phụ thuộc vào việc khám phá tên từ bytecode hơn.

## 18. Di chuyển cấu hình và xử lý deprecation

Spring Boot có thể đổi tên hoặc loại bỏ configuration property giữa các major version. Khi nâng Boot 2 lên 3 hoặc Boot 3 lên 4, hãy đối chiếu configuration changelog và migration guide.

Có thể thêm spring-boot-properties-migrator tạm thời:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Module này báo các property đã đổi tên hoặc bị loại bỏ khi ứng dụng khởi động và có thể tạm thời hỗ trợ migration. Sau khi cập nhật application.yml/properties, phải xóa module migrator khỏi dependency graph.

Không dùng migrator như giải pháp lâu dài. Cấu hình cuối cùng cần dùng đúng tên property của phiên bản Boot đích để tránh phụ thuộc vào cơ chế tương thích tạm thời.

## 19. Quy trình nâng cấp theo từng bước

Một quy trình có thể lặp lại và dễ khoanh vùng lỗi:

1. Ghi nhận phiên bản hiện tại của Java, Spring Boot, Spring Framework, Springdoc, Swagger Core và Jakarta API.
2. Chạy test hiện tại và lưu OpenAPI JSON/YAML làm baseline.
3. Nếu nâng từ Boot 2 lên 3, đưa ứng dụng lên bản maintenance cuối của Boot 2.7.x trước.
4. Nếu nâng từ Boot 3 lên 4, đưa ứng dụng lên bản maintenance mới nhất của Boot 3.5.x và xử lý deprecation.
5. Chọn Java version và Springdoc theo compatibility matrix của Boot đích.
6. Cập nhật Boot parent/BOM hoặc Gradle platform để dependency management đồng bộ.
7. Chuyển dependency Springdoc v1 sang starter v2 hoặc v2 sang starter v3.
8. Chuyển Jakarta EE imports/dependencies nếu đi từ Boot 2 lên Boot 3; kiểm tra Jakarta EE 11 level nếu lên Boot 4.
9. Kiểm tra Swagger Core Jakarta artifacts và loại bỏ biến thể javax cũ khỏi runtime.
10. Cập nhật package/class Springdoc đã đổi tên và các configuration property.
11. Xử lý thay đổi Jackson nếu nâng lên Boot 4.
12. Compile, chạy test, khởi động ứng dụng và tải OpenAPI document.
13. So sánh OpenAPI document mới với baseline và xác nhận thay đổi schema có chủ đích.
14. Xóa migration helper và dependency tạm sau khi hoàn tất.

Không nên nâng cùng lúc Spring Boot, Springdoc, Swagger Core, Jackson và nhiều thư viện ngoài Spring nếu chưa có baseline test. Nếu gặp lỗi, nâng theo nhóm nhỏ sẽ giúp xác định nguồn gây ra thay đổi.

## 20. Kiểm tra kết quả sau nâng cấp

Sau khi ứng dụng khởi động, kiểm tra các endpoint:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -I http://localhost:8080/swagger-ui.html
~~~

Nếu dự án đổi path hoặc chỉ dùng API-only, điều chỉnh URL tương ứng.

Kiểm tra các nội dung trong OpenAPI:

- Trường openapi có version mong muốn.
- paths chứa đầy đủ operation.
- parameters giữ đúng tên, vị trí, required và schema.
- requestBody và responses có đúng content type/schema.
- components.schemas giữ property, enum, format và nullable.
- Security schemes và requirement còn nguyên.
- Server URL và context path đúng môi trường.
- Không có schema tham chiếu bị thiếu hoặc tên component trùng ngoài ý muốn.

Đối với Swagger UI, xác nhận trang tải được swagger-config và OpenAPI document. Nếu document tải thành công nhưng UI không render, kiểm tra content type, custom HttpMessageConverter và version Swagger UI trước khi kết luận Springdoc không tương thích.

## 21. Dấu hiệu lỗi do dependency không tương thích

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| ClassNotFoundException: javax.servlet... | Thư viện cũ vẫn yêu cầu Servlet namespace javax | Tìm dependency kéo javax.servlet và nâng thư viện |
| ClassNotFoundException: jakarta.servlet... | Runtime thiếu Jakarta Servlet API hoặc dùng starter sai web stack | Kiểm tra Boot starter và runtime classpath |
| NoClassDefFoundError khi đọc annotation | Swagger annotation artifact bị thiếu hoặc sai biến thể | Kiểm tra swagger-annotations và swagger-core |
| NoSuchMethodError trong io.swagger | Các module Swagger Core khác version | Đồng bộ swagger-core, models, annotations và integration |
| ClassCastException giữa javax và jakarta | Hai namespace bị trộn trong cùng luồng tích hợp | Thay dependency cũ bằng bản Jakarta |
| Không tìm thấy GroupedOpenApi | Import package Springdoc v1 còn sót | Dùng org.springdoc.core.models.GroupedOpenApi trong v2/v3 |
| Không tìm thấy OpenApiCustomiser | Interface đã đổi tên | Dùng OpenApiCustomizer |
| OpenAPI mất tên parameter | Compiler không giữ parameter name hoặc metadata không tường minh | Bật -parameters và kiểm tra annotation binding |
| Schema thay đổi sau khi lên Boot 4 | Jackson 3 hoặc module serialization thay đổi | Kiểm tra mapper, annotation, custom serializer và OpenAPI diff |
| Swagger UI không render document | JSON converter, content type hoặc Swagger UI dependency xung đột | Kiểm tra response /v3/api-docs và dependency tree |
| Ứng dụng khởi động nhưng thiếu endpoint docs | Starter sai nhánh hoặc API docs bị disable | Kiểm tra springdoc starter, auto-configuration và property |

Không giải quyết lỗi linkage bằng cách thêm ngẫu nhiên một version swagger-core mới nhất. Hãy tìm artifact gây ra xung đột, đối chiếu với Springdoc version và chọn một bộ dependency nhất quán.

## 22. Checklist dependency trước khi phát hành

- [ ] Spring Boot version nằm trong nhánh Springdoc tương thích.
- [ ] Java runtime và compiler target đáp ứng yêu cầu của Boot.
- [ ] Spring Framework version do Boot quản lý, không bị pin lệch.
- [ ] Ứng dụng Boot 3/4 không còn dependency Java EE javax cũ trong runtime.
- [ ] Các package javax được rà soát theo API; không thay thế namespace Java SE.
- [ ] Springdoc starter dùng đúng artifact theo Web MVC/WebFlux và đúng nhánh 1/2/3.
- [ ] Không còn module Springdoc v1 cũ khi đã chuyển sang v2/v3.
- [ ] Import GroupedOpenApi, SpringDocUtils và OpenApiCustomizer đã cập nhật.
- [ ] Swagger Core Jakarta artifacts được dùng nhất quán.
- [ ] Không trộn swagger-core với swagger-core-jakarta.
- [ ] Các module swagger-core, models, annotations và integration có version tương thích.
- [ ] Không pin Swagger Core độc lập nếu starter đã quản lý dependency phù hợp.
- [ ] Jackson modules và custom serializer tương thích với Boot đích.
- [ ] Đã kiểm tra Maven dependency:tree hoặc Gradle dependencyInsight.
- [ ] OpenAPI JSON/YAML tải thành công và schema được so sánh với baseline.
- [ ] Swagger UI hiển thị document và request thử hoạt động theo cấu hình.
- [ ] Đã xóa spring-boot-properties-migrator sau khi cập nhật cấu hình.

Khi nâng Spring Boot, hãy kiểm tra cả Jakarta API và dependency Swagger Core cùng với Springdoc. Boot 2 lên 3 là thay đổi namespace và nền tảng lớn; Boot 3 lên 4 tiếp tục nâng Jakarta EE, Spring Framework và Jackson. Springdoc phải nằm đúng nhánh tương thích, còn Swagger Core phải dùng đúng biến thể Jakarta và cùng bộ version. Dependency tree, compile test và OpenAPI document trước/sau nâng cấp là ba bằng chứng quan trọng để xác nhận hệ thống đã chuyển đổi an toàn.

## Tài liệu tham khảo

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Springdoc OpenAPI v2 — Migration from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Springdoc OpenAPI — Current compatibility matrix and modules](https://springdoc.org/)
- [Swagger Core — Jakarta namespace artifacts](https://github.com/swagger-api/swagger-core)
- [Swagger Core — Jakarta annotations guidance](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
