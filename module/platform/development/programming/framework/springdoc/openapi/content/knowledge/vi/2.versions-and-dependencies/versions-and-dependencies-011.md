# Phân biệt tính năng dùng chung với tính năng chỉ có ở một nhánh

Springdoc-openapi giữ một mô hình chung qua các nhánh: đọc endpoint Spring, kết hợp kiểu Java và annotation, tạo OpenAPI document rồi cung cấp JSON/YAML và giao diện tài liệu nếu ứng dụng chọn starter tương ứng. Tuy nhiên, không thể lấy dependency, package Java, cấu hình hoặc khả năng của một nhánh rồi mặc định chúng áp dụng cho mọi nhánh. Spring Boot 1/2, 3 và 4 có các thế hệ Spring Framework, Jakarta API, cơ chế auto-configuration và hệ sinh thái phụ thuộc khác nhau; Springdoc vì thế phát hành các dòng tương thích riêng.

Khi chọn hoặc nâng phiên bản, hãy tách hai câu hỏi: khái niệm nào vẫn giữ nguyên và chi tiết triển khai nào phụ thuộc nhánh? Các khái niệm như operation, parameter, schema, response, security scheme, group và OpenAPI JSON/YAML có tính liên tục. Artifact Maven, package import, module composition, tích hợp framework và các tính năng mới lại cần được kiểm tra theo release line. Bài này đặt các điểm chung và điểm khác cạnh nhau, sau đó đưa ra quy trình chọn dependency, đọc release notes và kiểm chứng khả năng thực tế.

## 1. Phân biệt khái niệm chung và cách triển khai theo phiên bản

Một khái niệm có thể tồn tại xuyên suốt nhiều nhánh nhưng cách kích hoạt nó có thể thay đổi. Ví dụ, ứng dụng vẫn cần mô tả endpoint bằng OpenAPI, nhưng dependency cung cấp Swagger UI ở nhánh 1.x có tên khác starter tương ứng ở nhánh 2.x và 3.x.

| Nhóm | Thường ổn định về khái niệm | Cần kiểm tra theo nhánh |
|---|---|---|
| API contract | Path, HTTP method, parameter, request body, response | Kiểu OpenAPI được phát ra, schema edge case và default |
| Java metadata | Controller, DTO, annotation mô tả | Package import, Spring API và cách annotation được phát hiện |
| Tài liệu | OpenAPI JSON/YAML | Starter, endpoint path và cách export |
| Giao diện | UI đọc OpenAPI document | Swagger UI/Scalar starter và phiên bản UI |
| Web stack | MVC và reactive là hai mô hình web khác nhau | Artifact MVC/WebFlux và tích hợp theo Spring Boot |
| Tùy biến | Có extension point để chỉnh document | Package, tên interface, thứ tự và phạm vi customizer |
| Tích hợp | Có thể kết nối với security, validation, data modules | Module nào được gộp, module nào cần starter riêng |
| Tính năng mới | Mục tiêu mô tả API vẫn giống nhau | Release nào mới bổ sung capability cụ thể |

Không nên suy ra một tính năng có mặt chỉ vì annotation cùng tên vẫn compile. Hãy kiểm tra dependency thực tế, tài liệu đúng nhánh và OpenAPI document được tạo bởi đúng runtime.

## 2. Ba dòng phát hành chính

Springdoc hiện chia thành ba dòng tương thích với thế hệ Spring Boot:

| Springdoc | Spring Boot tương ứng | Phạm vi |
|---|---|---|
| 1.x | Spring Boot 1.x và 2.x | Dòng cũ; 1.8.0 là bản open-source cuối cho Boot 1/2 |
| 2.x | Spring Boot 3.x | Dòng starter cho Boot 3 |
| 3.x | Spring Boot 4.x | Dòng dành cho Boot 4 |

Đây là ranh giới lựa chọn quan trọng nhất. Không thêm springdoc 3.x vào ứng dụng Boot 3 chỉ vì 3.x có version mới hơn; cũng không dùng 2.x trong ứng dụng Boot 4 nếu compatibility matrix không công bố cặp đó.

Tài liệu chính thức duy trì tài liệu riêng cho v1 và v2, còn nhánh hiện hành mô tả v3. Hãy mở đúng trang trước khi sao chép dependency hoặc package import.

## 3. Ma trận tương thích phải được đọc theo Spring Boot minor line

Ma trận do Springdoc công bố tại thời điểm biên soạn:

| Spring Boot | Dòng Springdoc đã được build/test theo tài liệu |
|---|---|
| 4.1.x | 3.1.x đến 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x đến 2.10.x |
| 3.4.x | 2.7.x đến 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x đến 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x đến 2.1.x |
| 2.7.x và một số dòng 2.x cũ | 1.6.x trở lên theo từng minor |

Ma trận là hướng dẫn tương thích đã kiểm chứng, không phải lời hứa mọi tổ hợp đều giống nhau. Khi dự án nâng Spring Boot minor, hãy đọc lại bảng hiện hành và release notes. Không lấy một version Springdoc ngẫu nhiên trong cùng major line rồi cho rằng mọi Boot minor đều đã được kiểm thử.

## 4. Các mốc phiên bản hiện hành cần nhận diện

Theo tài liệu và release list đang công bố:

- Springdoc 1.8.0 là bản open-source cuối của dòng Boot 1/2.
- Springdoc 2.10.0 thuộc dòng Boot 3.5.x.
- Springdoc 3.2.0 thuộc dòng Boot 4.1.x.

Các số này là mốc tham khảo tại thời điểm bài được viết. Khi triển khai thực tế, kiểm tra trang release mới nhất và compatibility matrix; không giữ nguyên version trong bài học nếu dự án đã nâng nền tảng.

## 5. Vì sao không dùng một major version cho mọi Spring Boot?

Major line phản ánh thay đổi ở nền tảng tích hợp. Spring Boot 3 chuyển hệ sinh thái Java EE cũ sang Jakarta namespace, đồng thời nâng thế hệ Spring Framework và nhiều dependency. Spring Boot 4 tiếp tục nâng nền tảng và API nền. Springdoc phải biên dịch, tích hợp auto-configuration và kiểm thử trên các API tương ứng.

Một dependency có thể gặp lỗi ngay ở compile time nếu nó tham chiếu lớp hoặc package không còn trong nền tảng. Một số khác có thể compile nhưng lỗi lúc khởi động vì auto-configuration, bean hoặc method signature đã thay đổi.

Vì vậy, chọn major line theo Spring Boot trước, sau đó chọn minor/patch theo compatibility matrix và release notes.

## 6. Các khả năng cốt lõi dùng chung

Qua các dòng hỗ trợ OpenAPI 3, những khái niệm cốt lõi thường gặp gồm:

- Phân tích controller Spring MVC hoặc Spring WebFlux theo starter tương ứng.
- Tạo path và operation từ request mapping.
- Mô tả path, query và header parameter.
- Phân tích request body và response type.
- Tạo schema từ DTO, generic type và annotation.
- Đọc các annotation Swagger/OpenAPI như Operation, Parameter, Schema, ApiResponse, Tag và SecurityScheme.
- Lọc controller theo package hoặc path.
- Tạo nhiều document bằng group.
- Tùy biến OpenAPI bằng customizer.
- Cung cấp OpenAPI JSON và YAML.
- Tích hợp giao diện Swagger UI khi chọn starter UI.

Đây là các năng lực chung ở mức khái niệm. Một edge case cụ thể, cách suy luận nullable, annotation validation mới hoặc module tích hợp có thể chỉ được hỗ trợ từ một release nhất định. Luôn xác minh chi tiết với version đang dùng.

## 7. Khái niệm OpenAPI không đồng nghĩa với Springdoc major version

Có ba loại version dễ bị nhầm:

| Version | Ý nghĩa |
|---|---|
| Springdoc version | Version thư viện tích hợp Spring |
| OpenAPI specification version | Phiên bản chuẩn được ghi trong trường openapi của document |
| Spring Boot version | Phiên bản nền tảng ứng dụng |

Ví dụ, ứng dụng có thể dùng Spring Boot 3.5.x, Springdoc 2.10.x và document OpenAPI có trường openapi riêng. Không suy ra version specification chỉ từ số major Springdoc.

Hãy mở đầu file JSON/YAML và đọc trường openapi. Nếu công cụ downstream chỉ hỗ trợ một phiên bản OpenAPI cụ thể, xác minh document thực tế và cấu hình hỗ trợ của đúng release.

## 8. Swagger annotations là metadata, không phải Springdoc API

Các annotation như Operation, Schema, Parameter, ApiResponse và Tag thuộc hệ sinh thái Swagger/OpenAPI annotations, thường được import từ package io.swagger.v3.oas.annotations.

Springdoc sử dụng metadata này để tạo document. Đây là lý do nhiều annotation nghiệp vụ có thể giữ nguyên qua nâng cấp Springdoc, miễn là dependency Swagger annotations tương thích và không bị xung đột version.

Tuy nhiên, API của chính Springdoc như GroupedOpenApi, SpringDocUtils hoặc customizer interface có thể đổi package hoặc tên giữa các major. Không nhầm việc annotation Swagger còn giống nhau với việc mọi class Springdoc nội bộ cũng giữ nguyên package.

## 9. Thay đổi module lớn từ v1 sang v2

Ở v1, các module được tách thành nhiều artifact riêng. Khi chuyển sang v2, Springdoc đổi tên module và gom một số tích hợp vào starter-common để giảm số dependency phải khai báo.

| Artifact v1 | Artifact v2 tương ứng | Ghi chú |
|---|---|---|
| springdoc-openapi-common | springdoc-openapi-starter-common | Nền tảng dùng chung |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api | OpenAPI cho Spring MVC |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api | OpenAPI cho WebFlux |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui | MVC kèm Swagger UI |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui | WebFlux kèm Swagger UI |
| springdoc-openapi-data-rest | springdoc-openapi-starter-common | Tích hợp được gộp vào common |
| springdoc-openapi-hateoas | springdoc-openapi-starter-common | Tích hợp được gộp vào common |
| springdoc-openapi-kotlin | springdoc-openapi-starter-common | Tích hợp được gộp vào common |
| springdoc-openapi-javadoc | springdoc-openapi-starter-common | Tích hợp được gộp vào common |
| springdoc-openapi-security | springdoc-openapi-starter-common | Tích hợp được gộp vào common |

Bảng là hướng dẫn chuyển đổi từ v1 sang v2 theo tài liệu migration. Không ghép tất cả artifact vào project một cách máy móc; chọn starter theo web stack và nhu cầu UI/API-only.

## 10. Một số package Springdoc đổi từ v1 sang v2

Migration v1 sang v2 có các thay đổi import quan trọng:

| v1 | v2 |
|---|---|
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Lưu ý OpenApiCustomiser đổi cách viết từ Customiser sang Customizer. Nếu chỉ sửa version dependency mà không sửa import, project có thể không compile.

Đối với v3, không tự suy ra mọi package mới chỉ từ bảng v1/v2. Kiểm tra API docs và source của đúng tag v3 trước khi thay import.

## 11. Chọn starter theo web stack

Với các nhánh sử dụng starter layout, cần chọn đúng web stack:

| Nhu cầu | Spring MVC | Spring WebFlux |
|---|---|---|
| Chỉ OpenAPI document | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| OpenAPI và Swagger UI | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |
| OpenAPI và Scalar | springdoc-openapi-starter-webmvc-scalar | springdoc-openapi-starter-webflux-scalar |

Starter MVC tích hợp với spring-boot-starter-web. Starter WebFlux tích hợp với spring-boot-starter-webflux. Không thêm cả hai chỉ để có thêm giao diện; ứng dụng phải có web stack phù hợp.

Tên artifact trong bảng là dạng starter của các nhánh hiện hành. Nếu đang dùng v1, hãy tra tài liệu v1 thay vì sao chép tên artifact v2/v3.

## 12. Phân biệt API-only với starter giao diện

Không phải ứng dụng nào cũng cần Swagger UI. Nếu chỉ cần OpenAPI document cho CI, code generator hoặc developer portal khác, dùng starter API-only tương ứng.

Ví dụ với Spring MVC ở nhánh v3:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Nếu cần Swagger UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Ví dụ trên dành cho Spring Boot 4.1.x theo dòng 3.2.x. Với Boot 3, chọn starter cùng cấu trúc nhưng version 2.x tương thích. Với Boot 2, tra artifact v1.

API-only vẫn cung cấp document; nó không tự kéo Swagger UI. Ngược lại, starter UI cung cấp cả tích hợp tài liệu và giao diện.

## 13. Ví dụ chọn dependency cho Boot 3 và Boot 4

Ứng dụng Spring Boot 3.5.x có thể dùng dòng Springdoc 2.8.x đến 2.10.x theo ma trận:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Ứng dụng Spring Boot 4.1.x có thể dùng dòng Springdoc 3.1.x đến 3.2.x:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Tên artifact giống nhau không có nghĩa binary tương thích chéo major. Version 2.10.0 và 3.2.0 được build cho các thế hệ Spring Boot khác nhau.

## 14. Các tính năng thường dùng nhưng phải kiểm tra module

Một số tính năng không chỉ phụ thuộc Springdoc version mà còn phụ thuộc starter hoặc tích hợp framework:

| Năng lực | Điều cần kiểm tra |
|---|---|
| Swagger UI | Có dùng starter UI đúng MVC/WebFlux không |
| Scalar | Có starter Scalar và release hỗ trợ tương ứng không |
| Spring Data REST | Tích hợp có được gộp vào common hay cần module riêng ở nhánh cũ |
| Spring HATEOAS | Version tương thích và schema HAL |
| Actuator | Module hoặc auto-configuration hỗ trợ đúng Boot line |
| Kotlin | Nullability, sealed class và compiler metadata |
| Groovy/Javadoc | Module có sẵn trong nhánh đang dùng không |
| Functional endpoints | Kiểu RouterFunction/functional mapping có được hỗ trợ trong release đó không |
| MCP | Chỉ có ở các release 3.x hỗ trợ, bắt đầu từ 3.0.3 |
| API versioning của Spring Framework | Kiểm tra release 3.x và phiên bản Spring Framework tương ứng |

Không đánh đồng việc tính năng xuất hiện trong trang README hiện hành với việc nó đã tồn tại ở v1 hoặc mọi patch của v2.

## 15. Những tính năng mới chỉ có ở một nhánh

Một số capability được bổ sung ở các release mới:

- MCP integration được thêm trong Springdoc 3.0.3 trên nhánh Spring Boot 4.
- Hỗ trợ API versioning của Spring Framework được bổ sung trong nhánh 3.x theo các release tương ứng.
- Một số cải tiến về Kotlin nullability, schema và serialization được bổ sung theo từng release.
- Tích hợp Scalar và các thay đổi security/configuration có thể khác theo mốc 3.x.

Nếu ứng dụng Boot 3 cần một capability chỉ được công bố trong 3.x, không thể chỉ nâng Springdoc 2.x lên 3.x mà bỏ qua Boot major. Hãy đánh giá nâng Spring Boot trước hoặc thiết kế cách tích hợp khác được hỗ trợ.

## 16. MCP là ví dụ điển hình của tính năng theo nhánh

Springdoc MCP chuyển các OpenAPI operation thành MCP tools cho AI client. Release notes ghi nhận tính năng này được thêm ở Springdoc 3.0.3.

Vì vậy:

- Springdoc 1.x không có module MCP của Springdoc.
- Springdoc 2.x dành cho Boot 3 không có starter MCP tương ứng trong dòng này.
- Springdoc 3.x trên Boot 4 có module MCP từ release hỗ trợ.

Không thêm artifact MCP 3.x vào ứng dụng Boot 3 đang dùng Springdoc 2.x. Nếu cần MCP trên Boot 3, hãy đánh giá giải pháp MCP native phù hợp với Spring AI và dependency matrix của ứng dụng, thay vì giả định Springdoc 2.x có cùng module.

## 17. OpenAPI annotations có tính liên tục, nhưng API Springdoc có thể đổi

Annotation Swagger v3 như Operation, Schema, Parameter, ApiResponse và Tag thường là phần metadata mà controller dùng qua các nhánh. Chúng thuộc hệ sinh thái OpenAPI annotations.

Các API extension của Springdoc có thể đổi:

- Package của GroupedOpenApi.
- Package của SpringDocUtils.
- Tên và package của customizer.
- Artifact chứa auto-configuration.
- Cách Springdoc tích hợp với Spring Boot properties.

Khi nâng major, hãy tìm lỗi compile theo package import trước. Sau khi compile, kiểm tra bean customizer có được Spring đăng ký và document cuối cùng có áp dụng thay đổi.

## 18. Các property chung và property mới

Nhiều property giữ cùng prefix springdoc, ví dụ:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
  packages-to-scan:
    - com.acme.api
  paths-to-match:
    - /api/**
~~~

Tuy nhiên, không nên sao chép toàn bộ file application.yml giữa các major mà không kiểm tra property reference. Một property có thể được thêm, đổi default, đổi kiểu, chuyển sang module khác hoặc không còn được hỗ trợ.

Hãy kiểm tra trang properties của đúng nhánh và xác nhận property binding ở runtime. Property lạ không báo lỗi luôn; có thể ứng dụng khởi động bình thường nhưng giá trị bị bỏ qua.

## 19. Cách chọn đúng trang tài liệu

Springdoc duy trì các trang riêng:

| Dòng ứng dụng | Tài liệu nên mở |
|---|---|
| Boot 1/2 + Springdoc 1.x | springdoc.org/v1 |
| Boot 3 + Springdoc 2.x | springdoc.org/v2 |
| Boot 4 + Springdoc 3.x | springdoc.org |

Không dùng trang mặc định cho mọi ứng dụng. Trang hiện hành có thể mô tả property hoặc module mới chưa tồn tại trong nhánh cũ.

Khi đọc một ví dụ trên blog hoặc Stack Overflow, kiểm tra ngày đăng, artifact version, import package và Spring Boot version trước khi áp dụng.

## 20. Maven và Gradle plugin cũng có vòng đời riêng

Springdoc cung cấp plugin để export OpenAPI document ở build time. Plugin này khác với starter runtime:

- Starter runtime tích hợp với ứng dụng để tạo document khi ứng dụng chạy.
- Maven/Gradle plugin khởi động ứng dụng hoặc gọi cấu hình phù hợp để lấy document trong quá trình build.
- Version plugin không nhất thiết trùng version starter.

Ví dụ Gradle plugin cần được cấu hình cùng Spring Boot plugin theo tài liệu plugin của release đang dùng. Với Gradle plugin v2, cách chạy task và yêu cầu Gradle khác so với plugin v1; không sao chép task hoặc plugin DSL cũ mà không xem migration guide.

Nếu chỉ cần runtime endpoint, không bắt buộc phải thêm build plugin. Nếu cần artifact OpenAPI trong CI, kiểm tra plugin compatibility, cách khởi động app và profile cần dùng.

## 21. BOM và quản lý version đồng bộ

Nếu dự án dùng nhiều module Springdoc, BOM có thể giúp quản lý version đồng bộ khi nhánh cung cấp BOM tương ứng.

Ví dụ ý tưởng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-bom</artifactId>
            <version>3.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó các module có thể không cần khai báo version riêng nếu BOM quản lý artifact đó. Kiểm tra BOM có được phát hành cho đúng line và artifact cần dùng hay không.

Không trộn BOM v3 với starter v2 hoặc dependency Springdoc cũ. Hãy để một dependency management source quản lý các module cùng dòng.

## 22. Kiểm tra dependency tree khi có xung đột

Khi ứng dụng dùng Springdoc cùng Swagger Core hoặc thư viện khác, có thể tồn tại nhiều version của swagger-annotations, swagger-models hoặc swagger-core.

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies
~~~

Tập trung kiểm tra:

- org.springdoc artifacts có cùng major line không.
- swagger-core, swagger-annotations và swagger-models có bị override không.
- Có Springfox cũ còn trong classpath không.
- Có nhiều starter MVC/WebFlux cùng lúc không.
- Có version Swagger UI bị kéo vào từ dependency khác không.

Một lỗi NoSuchMethodError hoặc ClassNotFoundException có thể do dependency graph không đồng nhất, không nhất thiết do controller annotation sai.

## 23. Chuyển từ v1 sang v2: checklist migration

Khi nâng từ Spring Boot 2/Springdoc 1 sang Boot 3/Springdoc 2:

1. Xác nhận ứng dụng đã chuyển sang Spring Boot 3 và Jakarta namespace.
2. Chọn Springdoc 2.x đúng với Boot 3 minor.
3. Thay artifact v1 bằng starter tương ứng.
4. Cập nhật package import Springdoc đã đổi.
5. Kiểm tra customizer interface và cách đăng ký bean.
6. Kiểm tra Spring Security, HATEOAS, Data REST và Actuator integration.
7. Export OpenAPI JSON/YAML.
8. So sánh paths, schema, responses và security với baseline.
9. Chạy HTTP integration test và OpenAPI validation.

Không chỉ nâng dependency. Đây là migration cả nền tảng Spring Boot và hệ sinh thái Jakarta.

## 24. Chuyển từ v2 sang v3: checklist migration

Khi nâng từ Spring Boot 3/Springdoc 2 sang Boot 4/Springdoc 3:

1. Nâng Spring Boot theo kế hoạch riêng và kiểm tra Spring Framework compatibility.
2. Chọn Springdoc 3.x đúng minor Boot 4.
3. Kiểm tra starter artifact và module MVC/WebFlux/UI/Scalar.
4. Kiểm tra API Springdoc nội bộ mà ứng dụng import.
5. Kiểm tra property reference và default mới.
6. Đọc release notes của các version trung gian, đặc biệt thay đổi schema và security.
7. Nếu dùng API versioning, MCP hoặc capability mới, xác nhận mốc release tối thiểu.
8. Export OpenAPI document từ đúng profile.
9. Chạy contract diff và integration tests.

Không đưa MCP hoặc API versioning vào production chỉ vì nhánh 3.x hỗ trợ; cần cấu hình security và test behavior của chính ứng dụng.

## 25. Đừng nhầm Swagger UI với OpenAPI document

OpenAPI là hợp đồng máy đọc được. Swagger UI là giao diện render hợp đồng đó. Hai phần có thể được cung cấp bởi các starter khác nhau.

Vì vậy:

- API-only starter có thể tạo document mà không có Swagger UI.
- UI starter cung cấp giao diện cùng tài liệu.
- Có thể dùng Scalar thay cho Swagger UI nếu starter và release hỗ trợ.
- Tắt UI không đồng nghĩa tắt JSON/YAML.
- Một UI version khác không nhất thiết thay đổi schema API, nhưng có thể thay đổi cách hiển thị hoặc thử request.

Khi lỗi chỉ xuất hiện ở giao diện, kiểm tra document JSON trực tiếp trước khi đổi Springdoc version.

## 26. MVC và WebFlux là khác biệt theo kiến trúc ứng dụng

Spring MVC xử lý request theo servlet stack. WebFlux sử dụng reactive stack. Springdoc có starter riêng cho từng loại.

Không chọn WebFlux starter chỉ vì controller trả Mono hoặc Flux nếu ứng dụng thực tế đang chạy servlet stack, hoặc ngược lại. Hãy xác định dependency nền:

| Web stack | Dependency Spring Boot thường dùng | Springdoc starter |
|---|---|---|
| MVC | spring-boot-starter-web | webmvc-api hoặc webmvc-ui |
| WebFlux | spring-boot-starter-webflux | webflux-api hoặc webflux-ui |

Một số functional endpoint có thể được hỗ trợ, nhưng khả năng cụ thể và API versioning của functional routes phụ thuộc release. Đọc tài liệu đúng nhánh và kiểm tra document được sinh.

## 27. Validation support không đồng nghĩa mọi validator đều được chuyển thành schema

Các annotation phổ biến như NotNull, NotBlank, Size, Min, Max, DecimalMin và Pattern có thể đóng góp constraint vào schema tùy phiên bản và cấu hình.

Tuy nhiên:

- Custom validator phụ thuộc service/database không thể tự chuyển thành JSON Schema một cách đầy đủ.
- Annotation mới có thể chỉ được hỗ trợ từ một release nhất định.
- Jakarta Validation và javax.validation thuộc các thế hệ namespace khác nhau.
- Runtime validation vẫn cần dependency validation và @Valid hoặc cơ chế kích hoạt phù hợp.

Nếu nâng từ Boot 2 sang Boot 3/4, kiểm tra namespace javax/jakarta trong DTO và validation provider. Nếu schema thiếu constraint, kiểm tra document và dependency trước khi kết luận Springdoc không hỗ trợ.

## 28. Parameter name discovery là ví dụ về thay đổi nền tảng

Spring Boot 3.2 thay đổi cách phát hiện tên parameter trong một số trường hợp. FAQ Springdoc hướng dẫn bật tùy chọn compiler -parameters nếu tên parameter không được tạo đúng trong OpenAPI.

Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Điểm này cho thấy lỗi thiếu query parameter có thể liên quan tới compiler metadata chứ không phải feature bị xóa khỏi Springdoc. Khi nâng Spring Boot hoặc Java compiler, hãy kiểm tra tên parameter trong OpenAPI output.

## 29. Tính năng tích hợp với hệ sinh thái có thể thay đổi theo release

Springdoc hỗ trợ nhiều tích hợp như Spring Security, Spring Data REST, Spring HATEOAS, Actuator, Spring Cloud Function, Kotlin, Groovy và Javadoc. Nhưng cách đóng gói có thể thay đổi:

- Ở v1 có nhiều artifact tích hợp riêng.
- Ở v2, một số tích hợp được đưa vào starter-common.
- Ở v3, các starter tiếp tục được tổ chức theo Boot 4 và có capability mới theo release.

Không thấy artifact riêng không có nghĩa tính năng đã mất. Có thể nó đã được gộp vào starter-common. Ngược lại, không thấy tên tính năng trong README không có nghĩa starter hiện tại tự động bật mọi tích hợp; kiểm tra modules guide.

## 30. Cách đọc release notes để tìm tính năng theo nhánh

Khi cần xác định một khả năng xuất hiện từ version nào:

1. Mở GitHub Releases của springdoc-openapi.
2. Chọn đúng tag v1, v2 hoặc v3.
3. Tìm mục Added, Changed, Fixed và Security.
4. Kiểm tra release đầu tiên có tính năng.
5. Kiểm tra release sau có thay đổi behavior hoặc default.
6. Đối chiếu version đó với Spring Boot compatibility matrix.
7. Tạo test nhỏ trên đúng dependency trước khi nâng dự án chính.

Release notes quan trọng với các tính năng mới như MCP, API versioning, Kotlin nullability, Scalar integration hoặc thay đổi schema required/default.

## 31. Kiểm tra feature bằng một project tối thiểu

Nếu chưa rõ tính năng có ở version nào, tạo một sample nhỏ với:

- Spring Boot version giống ứng dụng.
- Một starter Springdoc duy nhất.
- Một controller tối giản.
- Một DTO có annotation liên quan.
- Cấu hình tối thiểu cho feature đang kiểm tra.

Khởi động ứng dụng và kiểm tra:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Sau đó xác minh:

- Application context khởi động thành công.
- Bean auto-configuration mong đợi được đăng ký.
- Endpoint tài liệu có phản hồi.
- JSON/YAML có field hoặc behavior mong muốn.
- Không có warning hoặc exception tương ứng.

Một sample nhỏ giúp tách lỗi tương thích thư viện khỏi cấu hình phức tạp của ứng dụng thật.

## 32. Cách đọc document để xác minh OpenAPI version và feature

Mở đầu file JSON:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Catalog API",
    "version": "1.0.0"
  },
  "paths": {}
}
~~~

Ví dụ trên chỉ minh họa cấu trúc, không phải cam kết rằng mọi nhánh Springdoc phát ra đúng version này. Hãy đọc giá trị thực tế trong document của ứng dụng.

Đối với feature cụ thể, kiểm tra phần liên quan:

- paths để xem operation.
- components/schemas để xem model.
- securitySchemes để xem authentication metadata.
- tags để xem nhóm.
- servers để xem server URL.
- extensions có prefix x- để xem metadata tùy biến.

Nếu một capability không thể biểu diễn trong OpenAPI document, có thể nó thuộc UI, build plugin hoặc runtime integration chứ không phải contract schema.

## 33. Ma trận quyết định nhanh khi chọn version

| Tình trạng dự án | Hướng chọn |
|---|---|
| Spring Boot 2.x đang chạy ổn định | Dòng Springdoc 1.x phù hợp; cân nhắc kế hoạch nâng nền tảng vì v1 đã kết thúc open-source line |
| Spring Boot 3.0.x | Springdoc 2.0.x–2.1.x |
| Spring Boot 3.2.x | Springdoc 2.3.x–2.5.x |
| Spring Boot 3.5.x | Springdoc 2.8.x–2.10.x |
| Spring Boot 4.0.x | Springdoc 3.0.x |
| Spring Boot 4.1.x | Springdoc 3.1.x–3.2.x |
| Cần MCP của Springdoc | Nhánh 3.x từ release hỗ trợ, trên Boot 4 |
| Chỉ cần OpenAPI JSON/YAML | Chọn starter API-only |
| Cần Swagger UI | Chọn starter UI theo MVC/WebFlux |
| Cần Scalar | Chọn starter Scalar của đúng nhánh |

Ma trận này là điểm khởi đầu. Luôn kiểm tra compatibility matrix cập nhật và release notes trước khi khóa version.

## 34. Các lỗi thường gặp khi trộn nhánh

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ClassNotFoundException trong org.springdoc | Import từ package khác major | Đối chiếu migration guide và cập nhật import |
| NoSuchMethodError ở swagger-core | Dependency graph trộn version | Xem dependency tree và BOM |
| Auto-configuration không tạo API docs | Starter không đúng web stack hoặc Boot line | Chọn đúng MVC/WebFlux và compatibility line |
| Không tìm thấy artifact starter | Sao chép tên artifact v2/v3 vào v1 | Dùng module docs của nhánh đang chạy |
| Swagger UI không có nhưng JSON có | Dùng API-only starter | Thêm starter UI nếu thực sự cần |
| MCP artifact không resolve ở Boot 3 | MCP Springdoc thuộc nhánh 3.x | Dùng giải pháp tương thích Boot 3 hoặc nâng nền tảng |
| Query parameter mất tên | Compiler không lưu parameter name hoặc binding khác | Bật -parameters và kiểm tra signature |
| Schema khác sau nâng patch | Release thay đổi introspection hoặc dependency | Đọc release notes và chạy contract diff |
| Scalar hoặc UI behavior khác | Starter/UI version đổi | Kiểm tra module docs và release notes |
| Property bị bỏ qua | Property không tồn tại ở nhánh đang dùng | Kiểm tra properties reference đúng nhánh |
| Functional endpoint không có operation | Release hoặc kiểu route chưa được hỗ trợ như kỳ vọng | Kiểm tra support matrix và sample cùng version |

## 35. Quy trình nâng cấp an toàn

Thực hiện theo thứ tự:

1. Ghi nhận Spring Boot version, Java version và web stack.
2. Ghi nhận toàn bộ Springdoc artifacts đang có.
3. Xác định major line tương thích từ ma trận chính thức.
4. Chọn đúng starter và loại UI/API-only.
5. Kiểm tra các package Springdoc được import trong source.
6. Đọc migration guide nếu đổi major.
7. Đọc release notes từ version hiện tại tới version đích.
8. Cập nhật dependency management và loại dependency cũ trùng lặp.
9. Compile để phát hiện package/API incompatibility.
10. Khởi động ứng dụng bằng profile thực tế.
11. Export OpenAPI JSON và YAML.
12. So sánh paths, operationId, parameters, schemas, responses và security.
13. Chạy contract tests và OpenAPI validator.
14. Kiểm tra UI, reverse proxy và document group.
15. Ghi lại feature nào được thêm, bỏ hoặc thay đổi.

Không kết luận migration hoàn tất chỉ vì Maven/Gradle build thành công. Document có thể thay đổi trong runtime dù source compile không lỗi.

## 36. Ghi nhớ

- Springdoc có ba dòng chính: 1.x cho Boot 1/2, 2.x cho Boot 3 và 3.x cho Boot 4.
- Chọn version theo Spring Boot minor compatibility matrix, không chỉ theo major hoặc version mới nhất.
- Các khái niệm OpenAPI như operation, parameter, schema, response, group và security có tính liên tục.
- Artifact, package import, module composition và auto-configuration có thể thay đổi giữa major.
- V1 dùng các artifact cũ; v2 chuyển sang starter layout và gộp một số tích hợp vào starter-common.
- V2 có các package migration như GroupedOpenApi, SpringDocUtils và OpenApiCustomizer.
- V3 dành cho Boot 4; các capability như Springdoc MCP xuất hiện theo mốc release cụ thể.
- MVC, WebFlux, API-only, Swagger UI và Scalar cần starter đúng nhu cầu.
- Springdoc version không phải OpenAPI specification version; đọc trường openapi trong document.
- Bean Validation, Jackson, Kotlin và functional endpoint support cần được kiểm tra theo release.
- Maven/Gradle plugin có version và vòng đời riêng với runtime starter.
- Dependency tree và release notes là công cụ thiết yếu khi điều tra incompatibility.
- Sau nâng cấp, phải kiểm tra OpenAPI JSON/YAML và contract diff, không chỉ compile.

Khái niệm dùng chung giúp người phát triển chuyển kiến thức giữa các nhánh Springdoc, nhưng chi tiết triển khai vẫn phải theo version thực tế. Hãy bắt đầu từ Spring Boot và web stack, chọn major/minor Springdoc tương thích, sau đó xác minh artifact, package, module và release-specific feature. Khi nâng cấp, so sánh OpenAPI document trước và sau để phát hiện thay đổi hợp đồng mà compiler không thể cảnh báo.

## Tài liệu tham khảo

- Springdoc OpenAPI v1 documentation: https://springdoc.org/v1/
- Springdoc OpenAPI v2 documentation and migration guide: https://springdoc.org/v2/
- Springdoc OpenAPI current documentation: https://springdoc.org/
- Springdoc Getting Started: https://springdoc.org/getting-started.html
- Springdoc Modules: https://springdoc.org/modules.html
- Springdoc Properties: https://springdoc.org/properties.html
- Springdoc GitHub Releases: https://github.com/springdoc/springdoc-openapi/releases
- Springdoc GitHub repository and compatibility overview: https://github.com/springdoc/springdoc-openapi
