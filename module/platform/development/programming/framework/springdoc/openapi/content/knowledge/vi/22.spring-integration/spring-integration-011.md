# Kiểm tra tính năng tích hợp theo đúng thế hệ Springdoc đang sử dụng

springdoc-openapi tích hợp sâu với Spring Boot, Spring MVC, Spring WebFlux, Spring Security, Spring Data và các thư viện Swagger. Vì vậy, một cấu hình đúng ở thế hệ này có thể không còn đúng ở thế hệ khác. Dependency artifact, package Java, cơ chế auto-configuration và một số API mở rộng đã thay đổi qua các phiên bản lớn.

Khi kiểm tra một tính năng tích hợp, trước hết phải xác định ứng dụng đang dùng Spring Boot thế hệ nào và dependency springdoc nào thực sự được nạp vào runtime. Sau đó mới chọn tài liệu, starter, import và cách cấu hình tương ứng. Việc chỉ nhìn version khai báo trực tiếp trong build file là chưa đủ vì dependency management hoặc thư viện bắc cầu có thể kéo thêm một phiên bản khác.

Bài này trình bày quy trình kiểm tra từ dependency đến runtime: chọn đúng thế hệ, kiểm tra Web MVC/WebFlux, đối chiếu package và API, xác minh auto-configuration, kiểm tra endpoint OpenAPI/Swagger UI và xử lý các lỗi tích hợp thường gặp. Mục tiêu là xác nhận tính năng đang hoạt động trên đúng tổ hợp Spring Boot và springdoc của ứng dụng.

## 1. Vì sao phải xác định thế hệ Springdoc?

springdoc-openapi phát triển cùng các thay đổi lớn của Spring Boot và Spring Framework. Một số thay đổi có ảnh hưởng trực tiếp tới mã nguồn:

- Spring Boot 3 chuyển hệ sinh thái Jakarta EE từ namespace `javax.*` sang `jakarta.*`.
- springdoc 2.x chuyển sang cấu trúc starter và đổi tên một số package, class, interface.
- springdoc 3.x hỗ trợ thế hệ Spring Boot 4.
- Auto-configuration và các dependency được quản lý có thể khác giữa các dòng phiên bản.

Nếu dùng sai thế hệ, ứng dụng có thể không biên dịch, không khởi động, không tạo tài liệu hoặc Swagger UI không tải được OpenAPI document. Một số lỗi chỉ xuất hiện khi chạy do classpath có nhiều phiên bản không tương thích.

Quy trình đúng bắt đầu từ phiên bản Spring Boot thực tế, sau đó chọn springdoc tương thích. Không chọn springdoc chỉ dựa trên ví dụ trên Internet vì ví dụ có thể thuộc dòng Boot khác.

## 2. Ma trận tương thích theo Spring Boot

Theo bảng tương thích trên tài liệu springdoc chính thức tại thời điểm cập nhật bài học:

| Spring Boot | Thế hệ springdoc | Ghi chú |
|---|---|---|
| 4.1.x | 3.1.x đến 3.2.x | springdoc 3.x được xây dựng cho Spring Boot 4 |
| 4.0.x | 3.0.x | Dùng dòng 3.0.x tương ứng |
| 3.5.x | 2.8.x đến 2.10.x | Dòng springdoc 2.x |
| 3.4.x | 2.7.x đến 2.8.x | Dòng springdoc 2.x |
| 3.3.x | 2.6.x | Dòng springdoc 2.x |
| 3.2.x | 2.3.x đến 2.5.x | Dòng springdoc 2.x |
| 3.1.x | 2.2.x | Dòng springdoc 2.x |
| 3.0.x | 2.0.x đến 2.1.x | Dòng springdoc 2.x |
| 2.x và 1.x | 1.x | Bản mã nguồn mở cuối cùng của dòng 1.x là 1.8.0; kiểm tra ma trận chi tiết với bản Boot cũ |

Đây là bảng theo các phiên bản đã được dự án công bố là tương thích, không phải lời khuyên nâng cấp Spring Boot chỉ để dùng springdoc mới. Với dự án đang chạy ổn định, hãy chọn phiên bản springdoc được hỗ trợ cho đúng dòng Boot hiện tại và kiểm tra changelog trước khi nâng cấp.

Ma trận có thể thay đổi khi Spring Boot hoặc springdoc phát hành phiên bản mới. Luôn đối chiếu tài liệu tương ứng:

- Tài liệu hiện hành: https://springdoc.org/
- Tài liệu springdoc 2.x: https://springdoc.org/v2/
- Tài liệu springdoc 1.x: https://springdoc.org/v1/
- Repository và release notes: https://github.com/springdoc/springdoc-openapi

## 3. Xác định phiên bản Spring Boot thực tế

Kiểm tra build file và dependency management trước khi chọn starter.

Với Maven, tìm version trong parent hoặc dependency management:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
~~~

Nếu dự án import Spring Boot BOM thay vì dùng starter parent, kiểm tra version trong dependencyManagement. Nếu version được truyền qua property, cần kiểm tra giá trị cuối cùng sau khi Maven resolve.

Có thể xem dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

Với Gradle, kiểm tra plugin và dependency management:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.5.16"
}
~~~

Sau đó xem dependency đã được resolve:

~~~bash
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
~~~

Không chỉ xem version trong file build. Parent POM, BOM, version catalog, plugin hoặc convention plugin có thể quyết định version thực tế.

## 4. Xác định Web MVC hay WebFlux

springdoc có starter khác nhau tùy web stack. Chọn nhầm starter có thể khiến auto-configuration không hoạt động như mong muốn hoặc tạo classpath có cả hai stack.

| Web stack của ứng dụng | Starter có Swagger UI | Starter chỉ tạo OpenAPI |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

Đối với springdoc 2.x và 3.x, các artifact có tiền tố `springdoc-openapi-starter-`. Với springdoc 1.x, tên artifact cũ không có cấu trúc starter mới, ví dụ `springdoc-openapi-ui` cho MVC và `springdoc-openapi-webflux-ui` cho WebFlux.

Ví dụ ứng dụng MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Ví dụ ứng dụng WebFlux:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Các version trong ví dụ chỉ minh họa dòng springdoc 2.x tương ứng với Spring Boot 3.5.x. Nếu ứng dụng chạy Spring Boot 4, dùng dòng springdoc 3.x và xác minh đúng version theo ma trận hiện hành.

Không thêm đồng thời starter MVC và WebFlux chỉ để thử. Trước tiên xác định ứng dụng thực sự dùng `spring-boot-starter-web` hay `spring-boot-starter-webflux`, rồi chọn starter tương ứng.

## 5. Chọn đúng artifact cho nhu cầu

Không phải dự án nào cũng cần giao diện Swagger UI. Nếu chỉ cần endpoint JSON/YAML để pipeline tải đặc tả, dùng starter API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu cần giao diện tương tác, dùng starter có hậu tố `-ui`. Starter UI cung cấp cả OpenAPI endpoints và Swagger UI.

Một số module tích hợp như Spring HATEOAS, Kotlin, Javadoc, Data REST và Security đã được hợp nhất hoặc chuyển cách khai báo qua các thế hệ. Đặc biệt trong dòng 2.x, tài liệu migration chỉ rõ nhiều module v1 đã được gom vào `springdoc-openapi-starter-common`. Không tiếp tục sao chép dependency phụ từ ví dụ v1 mà chưa kiểm tra tài liệu v2/v3.

## 6. Khác biệt package và class giữa v1 và v2

Khi nâng từ springdoc 1.x lên 2.x, một số class đã chuyển package hoặc đổi tên:

| springdoc 1.x | springdoc 2.x |
|---|---|
| `org.springdoc.core.SpringDocUtils` | `org.springdoc.core.utils.SpringDocUtils` |
| `org.springdoc.api.annotations.ParameterObject` | `org.springdoc.core.annotations.ParameterObject` |
| `org.springdoc.core.GroupedOpenApi` | `org.springdoc.core.models.GroupedOpenApi` |
| `org.springdoc.core.customizers.OpenApiCustomiser` | `org.springdoc.core.customizers.OpenApiCustomizer` |
| `org.springdoc.core.Constants` | `org.springdoc.core.utils.Constants` |
| `org.springdoc.core.SwaggerUiConfigParameters` | `org.springdoc.core.properties.SwaggerUiConfigParameters` |

Một khác biệt dễ bỏ sót là `OpenApiCustomiser` dùng cách viết Anh-Anh trong v1, còn interface ở v2 là `OpenApiCustomizer`. Khi compiler báo không tìm thấy symbol, hãy kiểm tra import theo đúng thế hệ thay vì thêm một dependency cũ để làm cho class xuất hiện.

Các annotation chuẩn của Swagger/OpenAPI vẫn nằm trong namespace:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

Đừng nhầm thay đổi package của class springdoc với package annotation `io.swagger.v3.oas.annotations`.

## 7. Khác biệt namespace javax và jakarta

Spring Boot 2 thường sử dụng các API Java EE cũ dưới namespace `javax.*`. Spring Boot 3 và các thế hệ mới dùng Jakarta EE với namespace `jakarta.*`.

Ví dụ:

| API | Spring Boot 2 thường gặp | Spring Boot 3/4 |
|---|---|---|
| Validation | `javax.validation.Valid` | `jakarta.validation.Valid` |
| Constraint | `javax.validation.constraints.NotNull` | `jakarta.validation.constraints.NotNull` |
| Servlet | `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| Persistence | `javax.persistence.Entity` | `jakarta.persistence.Entity` |

Nếu nâng Boot 2 lên Boot 3 nhưng vẫn dùng annotation validation hoặc servlet từ `javax.*`, các thư viện mới có thể không nhận diện metadata như mong muốn. Đây là vấn đề tương thích namespace của ứng dụng và dependency, không phải lỗi riêng của springdoc.

Khi kiểm tra schema validation, hãy xác minh import constraint đến từ namespace phù hợp với Spring Boot hiện tại. Nếu một DTO dùng `jakarta.validation.constraints.NotNull` nhưng classpath chỉ có API cũ, ứng dụng có thể không biên dịch hoặc validation không chạy.

## 8. Kiểm tra dependency tree và xung đột phiên bản

Một dự án có thể khai báo springdoc 2.x nhưng dependency bắc cầu lại đưa một artifact v1 vào runtime. Kết quả có thể là `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` hoặc hành vi không nhất quán.

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Kiểm tra các điểm:

- Chỉ có một thế hệ springdoc trong runtime classpath.
- Các artifact `org.springdoc` cùng thuộc một dòng tương thích.
- `swagger-core` và Swagger UI không bị ép về version không tương thích.
- Không có starter MVC và WebFlux cùng được kéo vào ngoài ý muốn.
- Không khai báo trực tiếp version thư viện mà Spring Boot BOM đã quản lý nếu không có lý do cụ thể.
- Không giữ lại artifact v1 sau khi đã chuyển sang starter v2/v3.

Khi có version conflict, hãy xác định dependency nào kéo phiên bản cũ vào rồi loại trừ hoặc nâng dependency gốc. Không xử lý bằng cách thêm nhiều bản JAR hoặc khai báo class trùng.

## 9. Kiểm tra cấu hình auto-configuration

springdoc sử dụng Spring Boot auto-configuration để đăng ký bean, endpoint và các tích hợp. Khi dependency đúng nhưng endpoint không xuất hiện, cần kiểm tra auto-configuration có được nạp hay bị loại trừ.

Khởi động ứng dụng với debug condition report:

~~~bash
java -jar app.jar --debug
~~~

Hoặc thêm tham số tương ứng khi chạy ứng dụng trong IDE. Tìm các condition report liên quan đến Springdoc và kiểm tra:

- Auto-configuration có được phát hiện không?
- Điều kiện classpath có thỏa mãn không?
- Ứng dụng đang chạy MVC hay WebFlux?
- Có cấu hình exclude loại bỏ auto-configuration không?
- Có bean hoặc cấu hình tùy biến ghi đè hành vi mặc định không?
- Các package chứa `@Configuration`, `@OpenAPIDefinition`, `@SecurityScheme` và `GroupedOpenApi` có được component scan không?

Ở các thế hệ Spring Boot mới, auto-configuration được khai báo theo cơ chế import riêng của Spring Boot. Không nên tự chép class cấu hình nội bộ của springdoc vào ứng dụng. Nếu đang tích hợp Spring Framework không dùng Spring Boot, cách cấu hình sẽ khác và cần làm theo hướng dẫn dành riêng cho ứng dụng đó.

## 10. Kiểm tra cấu trúc package và component scan

Springdoc cần phát hiện controller, DTO, annotation và bean cấu hình. Một lỗi phổ biến là lớp ứng dụng đặt ở package quá sâu khiến controller hoặc configuration nằm ngoài vùng component scan.

Ví dụ cấu trúc dễ quét:

~~~text
com.example.store
├── StoreApplication.java
├── api
│   └── ProductController.java
├── dto
│   └── ProductResponse.java
└── config
    └── OpenApiConfiguration.java
~~~

Lớp `StoreApplication` nên nằm ở package gốc phù hợp để các package con được quét. Nếu chủ động giới hạn `scanBasePackages`, hãy chắc chắn package chứa controller và cấu hình OpenAPI được bao gồm.

Nếu dùng `@Controller` thay vì `@RestController`, method cần có `@ResponseBody` hoặc cách cấu hình tương ứng để được xem là REST endpoint. Một controller trả view có thể không được springdoc đưa vào tài liệu theo cách bạn mong đợi.

Nếu dùng `GroupedOpenApi`, hãy xác nhận bean group được component scan và các điều kiện `pathsToMatch`, `packagesToScan` không loại nhầm endpoint.

## 11. Kiểm tra endpoint sau khi ứng dụng khởi động

Với cấu hình mặc định, endpoint thường gặp:

| Endpoint | Mục đích |
|---|---|
| `/v3/api-docs` | OpenAPI JSON |
| `/v3/api-docs.yaml` | OpenAPI YAML |
| `/v3/api-docs/{group}` | OpenAPI document của group |
| `/swagger-ui.html` | Điểm vào Swagger UI |

Gọi trực tiếp bằng curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
~~~

Kiểm tra status code, Content-Type và nội dung. Một phản hồi 200 chưa đủ: `/v3/api-docs` phải là JSON OpenAPI hợp lệ, không phải trang HTML đăng nhập hoặc trang lỗi do proxy trả về.

Nếu đã đổi `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, context path hoặc management port, dùng URL thực tế theo cấu hình. Không kết luận endpoint bị thiếu chỉ vì thử đường dẫn mặc định.

## 12. Xác minh OpenAPI document thay vì chỉ nhìn Swagger UI

Swagger UI là giao diện đọc và thử đặc tả. Khi giao diện không hiển thị, hãy kiểm tra OpenAPI document trực tiếp để xác định lỗi ở phần sinh tài liệu hay phần UI.

Một document cơ bản phải có các phần như:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Store API",
    "version": "1.0.0"
  },
  "paths": {
    "/api/products": {
      "get": {
        "responses": {
          "200": {
            "description": "Danh sách sản phẩm."
          }
        }
      }
    }
  }
}
~~~

Version OpenAPI thực tế có thể là 3.0.x hoặc 3.1.x tùy cấu hình và phiên bản thư viện. Không hardcode giả định mọi phiên bản springdoc đều xuất cùng một `openapi` version.

Kiểm tra:

- `info.title` và `info.version` đúng.
- `paths` chứa endpoint mong đợi.
- HTTP method và path parameter chính xác.
- Request body và response có media type phù hợp.
- Schema được tham chiếu đúng.
- Security scheme và security requirement có mặt khi cần.
- Group document chỉ chứa các endpoint thuộc group đó.
- JSON và YAML cùng phản ánh một hợp đồng.

Nếu JSON hợp lệ nhưng Swagger UI không render, tập trung kiểm tra đường dẫn Swagger UI, URL spec, CORS, proxy, security và nội dung cấu hình UI.

## 13. Kiểm tra Swagger UI và URL OpenAPI

Swagger UI có thể dùng endpoint mặc định hoặc URL đặc tả được cấu hình riêng. Các thuộc tính thường dùng gồm:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    url: /v3/api-docs
~~~

Nếu ứng dụng dùng nhiều group, cấu hình `springdoc.swagger-ui.urls` có thể tạo danh sách tài liệu. Hãy xác minh từng URL group truy cập được và trả đúng JSON.

Nếu UI hiện thông báo không tải được definition:

1. Mở trực tiếp URL OpenAPI JSON trong browser.
2. Xác nhận status code và Content-Type.
3. Kiểm tra response có phải JSON OpenAPI hợp lệ.
4. Mở Developer Tools và xem Network/Console để tìm lỗi request.
5. Xác nhận UI đang trỏ đúng URL, context path và group.
6. Kiểm tra CORS nếu UI và document khác origin.
7. Kiểm tra Spring Security có chặn document hoặc redirect không.

Không sửa nội dung OpenAPI chỉ để che lỗi tải tài liệu. Trước hết xác định request nào thất bại và ở lớp nào.

## 14. Kiểm tra cấu hình context path và reverse proxy

Trong production, ứng dụng có thể chạy dưới context path hoặc phía sau reverse proxy. Swagger UI cần tạo URL đúng với địa chỉ mà browser nhìn thấy.

Ví dụ ứng dụng được công bố ở:

~~~text
https://api.example.com/store
~~~

nhưng backend chỉ nhận request nội bộ ở:

~~~text
http://store-service:8080
~~~

Nếu forwarded headers không được xử lý đúng, server URL hoặc URL tải spec có thể bị tạo theo host nội bộ. Kiểm tra cấu hình proxy, context path, forwarded headers và chiến lược `server.forward-headers-strategy` của Spring Boot phù hợp với hạ tầng.

Chỉ tin forwarded headers từ proxy đáng tin cậy. Không bật chế độ tin mọi header từ client bên ngoài nếu ứng dụng có thể bị truy cập trực tiếp.

Khi thay context path hoặc management port, kiểm tra cả Swagger UI lẫn endpoint OpenAPI. Một endpoint có thể hoạt động trong ứng dụng chính nhưng không được expose trên management port, hoặc ngược lại.

## 15. Kiểm tra Spring Security integration

Khi ứng dụng bật Spring Security, endpoint `/v3/api-docs` hoặc tài nguyên `/swagger-ui/**` có thể bị bảo vệ. Nếu UI trả 401, 403 hoặc redirect login, đó có thể là policy của security filter chain thay vì lỗi springdoc.

Hãy kiểm tra riêng:

- `/swagger-ui.html`
- `/swagger-ui/**`
- `/v3/api-docs`
- `/v3/api-docs.yaml`
- `/v3/api-docs/{group}`

Nếu tài liệu cần đăng nhập, cấu hình rule cho cả document endpoint và tài nguyên UI. Nếu cho phép public, dùng `permitAll()` có chủ đích cho đúng đường dẫn. Không tắt toàn bộ Spring Security chỉ để Swagger UI hiển thị.

Đảm bảo scheme trong OpenAPI mô tả đúng cơ chế runtime. `@SecurityScheme` và `@SecurityRequirement` chỉ mô tả hợp đồng; chúng không thay thế cấu hình xác thực và phân quyền thực tế.

## 16. Kiểm tra parameter name discovery

Một số ứng dụng sau khi nâng Spring Boot 3.2 trở lên có thể thấy tên parameter không còn được suy ra như trước nếu mã bytecode không giữ tên tham số. Điều này có thể khiến OpenAPI hiển thị tên parameter thiếu hoặc không như mong đợi.

Với Maven Compiler Plugin, bật lưu tên parameter:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Với Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Sau khi đổi cấu hình, clean và compile lại để bytecode được tạo mới. Với API công khai, vẫn nên khai báo rõ `@PathVariable("id")`, `@RequestParam("page")` hoặc `@Parameter(name = "...")` khi tên parameter là một phần quan trọng của hợp đồng.

## 17. Kiểm tra HttpMessageConverter khi dùng Spring MVC

Trong Spring MVC, springdoc cần các message converter phù hợp để trả tài liệu. Nếu ứng dụng tự ghi đè danh sách `HttpMessageConverter`, Swagger UI có thể không tải hoặc không render được OpenAPI definition.

Tài liệu springdoc lưu ý khi override converter mặc định của Spring Boot, cần giữ `ByteArrayHttpMessageConverter` và chú ý thứ tự đăng ký. Ví dụ:

~~~java
converters.add(new ByteArrayHttpMessageConverter());
converters.add(new MappingJackson2HttpMessageConverter(jacksonBuilder.build()));
~~~

Đây là lưu ý cho ứng dụng MVC tùy biến converter. Không áp dụng máy móc đoạn mã này cho WebFlux, vì WebFlux sử dụng codec khác. Khi gặp lỗi serialize hoặc response body, hãy xác định stack đang dùng trước rồi kiểm tra converter/codec tương ứng.

## 18. Kiểm tra API thay đổi khi nâng major version

Khi nâng springdoc 1.x lên 2.x hoặc 2.x lên 3.x, không nên chỉ đổi version trong dependency rồi chờ build thành công. Hãy rà soát:

1. Artifact đã đổi sang starter phù hợp chưa?
2. Package import đã được cập nhật chưa?
3. Namespace Jakarta đã được cập nhật nếu nâng Spring Boot 2 lên 3/4 chưa?
4. Các bean customizer, GroupedOpenApi và SpringDocUtils có dùng API đúng thế hệ không?
5. Cấu hình properties còn hợp lệ trong tài liệu version mới không?
6. Auto-configuration có được phát hiện và không bị exclude không?
7. Các integration module đã được thay bằng starter/module mới chưa?
8. JSON/YAML có thay đổi schema hoặc OpenAPI version không?
9. Swagger UI có hoạt động với authentication và proxy hiện tại không?
10. Test contract có phát hiện khác biệt không mong muốn không?

Với thay đổi lớn, tạo một nhánh nâng cấp, cập nhật dependency và import theo từng bước. Giữ bản OpenAPI trước nâng cấp để so sánh với bản sau nâng cấp.

## 19. Kiểm tra bằng dependency và integration tests

Một quy trình kiểm tra nên có cả bước build và bước chạy ứng dụng:

~~~text
Build file / BOM
      |
      v
Resolve dependency tree
      |
      v
Verify Boot + springdoc + web stack
      |
      v
Compile and start application
      |
      v
Check auto-configuration
      |
      v
Request JSON / YAML / Swagger UI
      |
      v
Validate paths, schemas, groups and security
      |
      v
Compare OpenAPI contract with previous release
~~~

Nên tự động hóa một smoke test kiểm tra:

- Ứng dụng khởi động thành công.
- `/v3/api-docs` trả 200 và JSON parse được.
- `/v3/api-docs.yaml` trả YAML hợp lệ nếu được bật.
- Swagger UI trả HTML và tải được spec.
- Các group quan trọng có mặt.
- Operation quan trọng có path, method, request/response schema.
- Security scheme và requirement không bị mất.
- Không có endpoint nội bộ bị công bố ngoài dự kiến.

Với MVC có thể dùng MockMvc hoặc kiểm thử qua cổng HTTP thực. Với WebFlux có thể dùng WebTestClient. Nếu lỗi chỉ xảy ra sau reverse proxy, cần một kiểm thử tích hợp đi qua URL công khai vì test trong ứng dụng không mô phỏng được toàn bộ hạ tầng.

## 20. Chẩn đoán lỗi theo dấu hiệu

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không tìm thấy starter hoặc artifact | Chọn sai tên artifact theo major version | Đối chiếu starter v1, v2 hoặc v3 |
| `ClassNotFoundException` với class springdoc | Import hoặc dependency thuộc thế hệ khác | Cập nhật package và loại dependency cũ |
| `NoSuchMethodError` | Xung đột version giữa springdoc, swagger-core hoặc Spring | Kiểm tra runtime dependency tree |
| Không tìm thấy `GroupedOpenApi` | Dùng import v1 trong v2/v3 | Kiểm tra package `org.springdoc.core.models` |
| Không tìm thấy `OpenApiCustomiser` | Dùng tên interface cũ | Với v2/v3 dùng `OpenApiCustomizer` |
| Validation annotation không được phản ánh | Dùng `javax.validation` trên Boot 3/4 hoặc thiếu validation dependency | Kiểm tra `jakarta.validation` và runtime |
| Không có endpoint `/v3/api-docs` | Sai starter, auto-configuration bị loại trừ hoặc sai web stack | Kiểm tra classpath và condition report |
| Chỉ thiếu một số controller | Component scan, package filter hoặc group filter sai | Kiểm tra package và `GroupedOpenApi` |
| Swagger UI không tải definition | JSON endpoint lỗi, security, CORS, proxy hoặc URL spec sai | Mở JSON trực tiếp và xem Network |
| Swagger UI không render sau khi override converter | Thiếu hoặc sai thứ tự ByteArray converter | Kiểm tra `HttpMessageConverter` MVC |
| Thiếu tên parameter | Compiler không lưu parameter name | Bật `-parameters`, khai báo tên rõ ràng |
| URL spec trỏ host nội bộ | Forwarded headers hoặc context path sai | Cấu hình proxy và forwarded-header strategy |
| Group không xuất hiện | Bean group không được scan hoặc filter không khớp | Kiểm tra bean và điều kiện group |
| JSON đúng nhưng Try it out thất bại | Security, CORS, server URL hoặc API runtime | Kiểm tra request thực tế từ browser |

Không giải quyết lỗi bằng cách nâng đồng loạt mọi dependency lên bản mới nhất. Trước hết tìm nguyên nhân cụ thể, đối chiếu compatibility matrix và nâng phiên bản theo một tổ hợp đã được hỗ trợ.

## 21. Quy trình kiểm tra khi bắt đầu một dự án

Thực hiện theo thứ tự:

1. Đọc version Spring Boot từ parent, BOM hoặc plugin.
2. Xác định Java version và web stack MVC/WebFlux.
3. Chọn major/minor springdoc từ compatibility matrix chính thức.
4. Chọn đúng starter UI hoặc API-only.
5. Kiểm tra artifact đã resolve trong runtime dependency tree.
6. Kiểm tra package imports và namespace javax/jakarta.
7. Khởi động ứng dụng và xác minh auto-configuration.
8. Gọi JSON/YAML endpoints trực tiếp.
9. Mở Swagger UI và kiểm tra Network/Console.
10. Kiểm tra groups, security, context path và reverse proxy.
11. Chạy integration test để xác nhận contract.
12. Ghi nhận phiên bản Boot, springdoc, starter và kết quả kiểm thử trong tài liệu dự án.

Khi nâng cấp, lặp lại quy trình và so sánh OpenAPI document trước/sau. Điều này giúp phát hiện thay đổi hợp đồng do dependency hoặc cách sinh schema.

## 22. Ghi nhớ

- Chọn springdoc theo thế hệ Spring Boot, không chỉ theo version mới nhất.
- Boot 2.x dùng dòng springdoc 1.x; Boot 3.x dùng dòng 2.x; Boot 4.x dùng dòng 3.x.
- Boot 3/4 dùng namespace Jakarta; Boot 2 thường dùng namespace Javax.
- Chọn starter WebMVC hay WebFlux đúng với web stack thực tế.
- V2/v3 dùng starter artifact và có thay đổi package so với v1.
- `GroupedOpenApi`, `SpringDocUtils` và `OpenApiCustomizer` có package/API khác qua các thế hệ.
- Kiểm tra runtime dependency tree để phát hiện xung đột phiên bản.
- Kiểm tra auto-configuration, component scan và group filters nếu endpoint hoặc controller bị thiếu.
- Xác minh JSON/YAML độc lập trước khi điều tra Swagger UI.
- Khi tùy biến `HttpMessageConverter`, giữ converter cần thiết và đúng thứ tự; WebFlux dùng codec riêng.
- Kiểm tra parameter name discovery, context path, reverse proxy và Spring Security.
- Tự động hóa smoke test để bảo đảm tính năng tích hợp vẫn hoạt động sau mỗi lần nâng cấp.

Để kiểm tra tính năng tích hợp theo đúng thế hệ Springdoc đang sử dụng, hãy bắt đầu từ tổ hợp Spring Boot, Java và web stack của ứng dụng. Chọn đúng springdoc major, starter và package API, sau đó xác minh dependency runtime, auto-configuration, endpoint JSON/YAML và Swagger UI. Cuối cùng, dùng integration test để chứng minh tài liệu được sinh ra khớp với API thực tế.
