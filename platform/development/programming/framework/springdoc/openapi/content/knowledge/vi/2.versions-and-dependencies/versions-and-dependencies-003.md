# Các nhánh Springdoc v1, v2, v3 và thế hệ Spring Boot tương ứng

springdoc-openapi có ba nhánh major được dùng cho ba thế hệ Spring Boot khác nhau. Quy tắc chọn nhánh là:

- Spring Boot 1.x và 2.x: springdoc-openapi v1.
- Spring Boot 3.x: springdoc-openapi v2.
- Spring Boot 4.x: springdoc-openapi v3.

Đây là quan hệ tương thích giữa thư viện và nền tảng Spring Boot, không phải phiên bản của chuẩn OpenAPI. Ví dụ, springdoc 3.2.0 vẫn có thể sinh document mang field openapi là 3.1.0. Số 3.2.0 là phiên bản thư viện Java; giá trị trong field openapi là phiên bản đặc tả mà document tuân theo.

Chọn đúng major chỉ là bước đầu. Mỗi minor line của Spring Boot có các phiên bản springdoc đã được dự án build và kiểm tra cụ thể. Không nên lấy một bản springdoc mới nhất rồi gắn vào bất kỳ bản Spring Boot nào cùng major.

## 1. Quy tắc chọn nhánh

| Thế hệ Spring Boot | Nhánh springdoc | Tài liệu chính |
|---|---|---|
| Boot 1.x và 2.x | v1.x | springdoc.org/v1 |
| Boot 3.x | v2.x | springdoc.org/v2 |
| Boot 4.x | v3.x | springdoc.org |

Có thể nhớ ngắn gọn: Boot 2 dùng springdoc 1, Boot 3 dùng springdoc 2, Boot 4 dùng springdoc 3. Không áp dụng phép ghép số này cho OpenAPI Specification.

Springdoc tự phân tích Spring application, controller, cấu hình, kiểu dữ liệu và annotation để sinh OpenAPI JSON/YAML; starter UI còn cung cấp giao diện tương tác. Các major được tách theo thay đổi nền tảng của Spring Boot, Spring Framework, Java và Jakarta EE.

## 2. Ma trận tương thích chi tiết

### Spring Boot 1.x và 2.x: springdoc v1

v1 là nhánh dành cho Spring Boot 1 và 2. Phiên bản open-source cuối cùng được công bố cho thế hệ này là 1.8.0. Dự án cũng thông báo có hình thức extended support riêng cho tổ chức cần hỗ trợ ngoài vòng đời open-source.

Các mốc tối thiểu được tài liệu v1 công bố:

| Spring Boot | Phiên bản springdoc tối thiểu được ghi nhận |
|---|---|
| 2.7.x | 1.6.11+ |
| 2.6.x | 1.6.0+ |
| 2.5.x | 1.5.9+ |
| 2.4.x | 1.5.0+ |
| 2.3.x | 1.4.0+ |
| 2.2.x | 1.2.1+ |
| 2.0.x | 1.0.0+ |
| 1.5.x | 1.6.11+ ở mốc tương thích cao nhất được liệt kê cùng Boot 2.7.x |

Với ứng dụng Boot 2.7 đang dùng v1, 1.8.0 là lựa chọn open-source cuối của nhánh này. Không dùng v1 cho Boot 3 chỉ vì ứng dụng vẫn compile được một số class; Boot 3 chuyển sang Jakarta namespace và springdoc v2 là nhánh được xây dựng cho nền tảng đó.

### Spring Boot 3.x: springdoc v2

v2 được thiết kế cho Spring Boot 3, Spring Framework 6 và Java 17 trở lên. Ma trận chi tiết được tài liệu v2 công bố:

| Spring Boot | Dải springdoc đã được build |
|---|---|
| 3.5.x | 2.8.x đến 2.10.x |
| 3.4.x | 2.7.x đến 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x đến 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x đến 2.1.x |

Ở thời điểm 20-11-2026, tài liệu v2 liệt kê 2.10.0 là bản stable mới nhất của nhánh. Tuy nhiên, điều đó không có nghĩa 2.10.0 là lựa chọn đúng cho mọi Boot 3.x. Ví dụ, ma trận chỉ ghi Boot 3.5.x với dải 2.8.x–2.10.x; Boot 3.2.x được xác nhận với 2.3.x–2.5.x.

### Spring Boot 4.x: springdoc v3

v3 là nhánh dành cho Spring Boot 4 và Spring Framework 7. Ma trận chính thức hiện hành:

| Spring Boot | Dải springdoc đã được build |
|---|---|
| 4.1.x | 3.1.x đến 3.2.x |
| 4.0.x | 3.0.x |

Ở thời điểm 20-11-2026, 3.2.0 là bản stable mới nhất được tài liệu springdoc công bố. Bản này được build trên Spring Boot 4.1.2 và ma trận xác nhận dòng Boot 4.1.x.

Spring Boot 4.2.0 đã xuất hiện trong danh sách stable của tài liệu Spring Boot, nhưng ma trận springdoc hiện hành chưa có dòng Boot 4.2.x. Vì vậy, chưa thể coi springdoc 3.2.0 là cặp đã được springdoc xác nhận cho Boot 4.2.x. Nếu dự án muốn dùng cặp này, cần kiểm tra release note hoặc ma trận mới hơn và tự chạy integration test trước khi chốt production.

### Cách đọc ma trận

Một hàng như Boot 3.5.x với springdoc 2.8.x–2.10.x có nghĩa dự án đã build các phiên bản springdoc trong dải đó trên nhánh Boot tương ứng. Đây không phải lời khẳng định rằng mọi tổ hợp patch dependency tùy ý đều tương thích.

Khi chọn phiên bản:

1. Xác định chính xác Spring Boot major và minor.
2. Tìm hàng tương ứng trong ma trận springdoc.
3. Chọn một phiên bản springdoc nằm trong dải đã công bố.
4. Kiểm tra Java runtime và Spring Framework do Boot quản lý.
5. Kiểm tra dependency tree sau khi resolve.
6. Chạy test khởi động ứng dụng, tải OpenAPI JSON/YAML và kiểm tra Swagger UI nếu dùng.

Nếu phiên bản Boot chưa xuất hiện trong ma trận, không suy ra tương thích từ việc Maven hoặc Gradle tải được artifact.

## 3. Vì sao springdoc tách major theo Spring Boot?

springdoc không chỉ là một file JSON generator. Thư viện tích hợp sâu với Spring:

- Auto-configuration và điều kiện tạo bean.
- Spring MVC hoặc Spring WebFlux.
- Controller mapping và functional endpoint.
- Message converter, codec và serialization.
- Bean Validation.
- Spring Security.
- Spring Data, HATEOAS và Actuator.
- Swagger Core, Swagger UI và các module bổ trợ.

Khi Spring Boot nâng major, các nền tảng bên dưới cũng thay đổi. springdoc phải có nhánh phù hợp để biên dịch, khởi động và đọc đúng metadata của runtime mới.

### Ba thế hệ nền tảng

| Nền tảng | Spring Boot | Spring Framework | Namespace quan trọng |
|---|---|---|---|
| Thế hệ cũ | 1.x/2.x | 4.x/5.x tùy Boot line | Java EE với javax |
| Thế hệ Boot 3 | 3.x | 6.x | Jakarta EE với jakarta |
| Thế hệ Boot 4 | 4.x | 7.x | Jakarta EE thế hệ mới và API nền tảng tương ứng |

Spring Boot 3 chuyển các API Java EE được quản lý sang Jakarta EE 10, bao gồm đổi package từ javax sang jakarta. Spring Boot 4 tiếp tục dựa trên Spring Framework 7 và các thế hệ Jakarta mới hơn. Các thay đổi này giải thích vì sao springdoc cần các major riêng.

## 4. Yêu cầu Java và nền tảng cần kiểm tra

Không chỉ nhìn version springdoc. Kiểm tra Java và Spring Framework mà Spring Boot yêu cầu:

| Nền tảng | Yêu cầu nền tảng cần nhớ |
|---|---|
| Spring Boot 2.x | Yêu cầu Java phụ thuộc minor line; các dòng cũ có thể chạy trên Java 8 |
| Spring Boot 3.x | Java 17 trở lên; Spring Framework 6 |
| Spring Boot 4.x | Java 17 trở lên; Spring Framework 7 |

Spring Boot 3.0 nâng baseline lên Java 17 và chuyển sang Jakarta EE 10. Spring Boot 4.0 cũng yêu cầu ít nhất Java 17 và Spring Framework 7.0. Các thư viện bên thứ ba có thể yêu cầu Java cao hơn, vì vậy hãy kiểm tra tài liệu của từng starter và plugin.

Ví dụ, một ứng dụng Boot 2 cũ vẫn chạy Java 8 không thể chỉ đổi dependency sang springdoc v2. Cần nâng cả nền tảng Boot/Java trước, sau đó mới chọn nhánh springdoc tương ứng.

## 5. Chọn starter theo web stack và nhu cầu giao diện

Các major mới dùng nhóm artifact starter. Hai yếu tố độc lập cần chọn:

1. Ứng dụng dùng Spring MVC hay Spring WebFlux?
2. Chỉ cần OpenAPI endpoint hay cần thêm giao diện Swagger UI?

| Nhu cầu | Spring MVC | Spring WebFlux |
|---|---|---|
| Chỉ sinh OpenAPI JSON/YAML | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webflux-api |
| Sinh tài liệu và có Swagger UI | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webflux-ui |

Với v1, artifact name có dạng cũ như springdoc-openapi-ui hoặc springdoc-openapi-webflux-ui. Từ v2, các module chính được đổi sang tên starter. Nhánh v3 tiếp tục dùng nhóm starter tương ứng với Boot 4.

Ví dụ endpoint mặc định vẫn quen thuộc:

~~~text
/v3/api-docs
/v3/api-docs.yaml
/swagger-ui.html
~~~

Đường dẫn có thể được tùy chỉnh qua cấu hình springdoc. Việc giữ endpoint quen thuộc không có nghĩa dependency, package hoặc auto-configuration giữa các major giống nhau.

## 6. Ví dụ dependency cho từng thế hệ

### Boot 2.7 với springdoc v1

Ví dụ Maven cho ứng dụng Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.0</version>
</dependency>
~~~

Nếu dùng WebFlux, v1 có artifact riêng springdoc-openapi-webflux-ui. Kiểm tra đúng artifact theo web stack.

### Boot 3.5 với springdoc v2

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu ứng dụng dùng WebFlux, thay artifact bằng springdoc-openapi-starter-webflux-ui. Nếu chỉ cần JSON/YAML cho CI, dùng starter webmvc-api hoặc webflux-api tương ứng để không đóng gói Swagger UI.

### Boot 4.1 với springdoc v3

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Với WebFlux, dùng springdoc-openapi-starter-webflux-ui. Với API-only, dùng artifact starter-webmvc-api hoặc starter-webflux-api.

Các version trong ví dụ minh họa những cặp nằm trong ma trận được công bố tại thời điểm soạn bài. Hãy cập nhật theo ma trận mới nhất khi bắt đầu dự án hoặc nâng cấp.

## 7. Khác biệt migration quan trọng từ v1 sang v2

Đổi major từ v1 sang v2 không chỉ là sửa số version. Tài liệu migration chính thức nêu rõ các module đã được đổi tên và một số package/class cũng chuyển vị trí.

### Đổi artifact

| Artifact v1 | Artifact v2 |
|---|---|
| springdoc-openapi-common | springdoc-openapi-starter-common |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |
| springdoc-openapi-data-rest | Tích hợp qua starter-common |
| springdoc-openapi-hateoas | Tích hợp qua starter-common |
| springdoc-openapi-security | Tích hợp qua starter-common |
| springdoc-openapi-kotlin | Tích hợp qua starter-common |
| springdoc-openapi-groovy | Tích hợp qua starter-common |
| springdoc-openapi-javadoc | Tích hợp qua starter-common |

Không giữ cả artifact v1 và v2 trong cùng ứng dụng. Xóa module cũ đã được thay thế trước khi thêm starter mới, rồi kiểm tra dependency tree để tránh class trùng hoặc hai auto-configuration cùng hoạt động.

### Đổi package và class

| Tên cũ | Tên mới |
|---|---|
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Đặc biệt, class OpenApiCustomiser được đổi cách viết thành OpenApiCustomizer. Các import trong customizer, configuration và test phải được cập nhật cùng nhau.

### Chuyển từ javax sang jakarta

Spring Boot 3 chuyển từ Java EE namespace sang Jakarta EE namespace. Ví dụ:

~~~java
// Trước khi nâng Spring Boot 3
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.servlet.http.HttpServletRequest;

// Sau khi nâng Spring Boot 3
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.servlet.http.HttpServletRequest;
~~~

Đây là thay đổi của nền tảng Spring Boot/Jakarta, không phải một đổi tên riêng do springdoc thực hiện. DTO, controller, filter và thư viện tích hợp đều cần dùng namespace phù hợp.

## 8. Nâng từ v2 sang v3 khi chuyển sang Spring Boot 4

v2 và v3 đều dùng tên starter theo dạng springdoc-openapi-starter-*. Khi chuyển v2 lên v3, trọng tâm là chuyển nền tảng Boot 3/Spring Framework 6 sang Boot 4/Spring Framework 7, sau đó chọn springdoc v3 đã được xác nhận cho minor line Boot mới.

Không có một bảng đổi toàn bộ artifact/package từ v2 sang v3 tương tự tài liệu v1-to-v2. Vì vậy, không tự tạo danh sách đổi package chưa được tài liệu xác nhận. Thay vào đó:

1. Đọc Spring Boot 4 migration guide và release notes.
2. Nâng Java toolchain và Spring Boot plugin.
3. Cập nhật dependency management theo Boot 4.
4. Chuyển springdoc sang v3 trong dải tương thích đã công bố.
5. Kiểm tra starter MVC/WebFlux và module tích hợp.
6. Compile lại các customizer, configuration và test đang dùng API springdoc.
7. Kiểm tra thay đổi của Spring Framework 7, Jakarta APIs, serialization và security.
8. Sinh lại OpenAPI document và so sánh với baseline.

Các tên starter webmvc-ui, webflux-ui, webmvc-api và webflux-api vẫn được dùng trong tài liệu v3. Tuy nhiên, phải lấy version v3 phù hợp với Boot 4 minor line, không dùng version v2 chỉ vì artifact name giống nhau.

## 9. Những thứ không đổi giữa các major

Nâng major thư viện không có nghĩa phải thiết kế lại toàn bộ API contract. Các khái niệm sau vẫn giữ vai trò tương tự:

- Controller mapping được đọc để tạo path và operation.
- Annotation của Swagger/OpenAPI mô tả operation, parameter, schema, response và security.
- OpenAPI document có thể được xuất thành JSON hoặc YAML.
- Swagger UI đọc document để hiển thị và thử request.
- GroupedOpenApi được dùng để chia tài liệu theo nhóm.
- OpenApiCustomizer được dùng để chỉnh sửa document sinh ra.

Điều cần phân biệt là API Java và integration layer của springdoc có thể thay đổi giữa major, trong khi HTTP contract mà consumer sử dụng có thể giữ nguyên.

## 10. Quản lý version đồng bộ trong Maven

Chỉ khai báo một starter springdoc phù hợp với web stack. Với module bổ trợ, dùng cùng version với starter hoặc dependency management do dự án cung cấp.

Ví dụ đặt version ở property:

~~~xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Đổi cả property và version dependency theo ma trận Boot đang dùng. Không để module webmvc-ui ở một version nhưng starter-common hoặc module bổ trợ ở một version khác.

Nếu dự án quản lý version tập trung qua Maven BOM hoặc parent POM nội bộ, hãy giữ version springdoc ở một nơi và kiểm tra dependency tree sau khi resolve.

## 11. Quản lý version đồng bộ trong Gradle

Khai báo version tại một nơi, ví dụ version catalog:

~~~toml
[versions]
springdoc = "2.10.0"

[libraries]
springdoc-webmvc-ui = { module = "org.springdoc:springdoc-openapi-starter-webmvc-ui", version.ref = "springdoc" }
~~~

Sau đó sử dụng alias trong build:

~~~kotlin
dependencies {
    implementation(libs.springdoc.webmvc.ui)
}
~~~

Đối với Boot 4, đổi version catalog sang phiên bản springdoc v3 nằm trong ma trận tương thích. Nếu dùng nhiều app có Boot major khác nhau trong một repository, mỗi app có thể cần version catalog hoặc dependency constraint riêng.

## 12. Tránh trộn các major và override dependency bắc cầu

Các lỗi phổ biến khi nâng version:

- Một module springdoc v1 còn sót lại trong khi starter v2/v3 đã được thêm.
- Dùng springdoc 2.x với Spring Boot 4 hoặc springdoc 3.x với Spring Boot 3.
- Kéo swagger-core hoặc swagger-annotations phiên bản khác với phiên bản mà springdoc quản lý.
- Cùng lúc có WebMVC UI và WebFlux UI trong một app mà không có chủ đích rõ ràng.
- Thêm swagger-ui WebJar độc lập và vô tình ghi đè assets do springdoc starter cung cấp.
- Dùng một bản snapshot hoặc prerelease cho production mà không kiểm soát.

Kiểm tra dependency tree:

~~~bash
# Maven
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars

# Gradle
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-annotations --configuration runtimeClasspath
~~~

Nếu thấy hai major springdoc hoặc nhiều version swagger-core, tìm dependency kéo chúng vào. Sửa dependency declaration hoặc exclusion có chủ đích; không thêm một override toàn cục trước khi biết module nào cần version đó.

## 13. Kiểm tra ứng dụng sau khi đổi nhánh

Sau khi nâng dependency, xác minh tối thiểu:

1. Application context khởi động không lỗi.
2. Không có NoSuchMethodError, ClassNotFoundException hoặc NoClassDefFoundError liên quan springdoc/swagger-core.
3. /v3/api-docs trả JSON hợp lệ.
4. /v3/api-docs.yaml trả YAML hợp lệ nếu endpoint YAML được bật.
5. Swagger UI tải đúng document nếu dùng starter UI.
6. GroupedOpenApi vẫn sinh đủ group.
7. OperationId, path, parameter và schema không biến mất.
8. Security scheme và response code vẫn đúng.
9. OpenAPI document được validate và semantic diff với baseline.
10. Test runtime cho request/response quan trọng vẫn PASS.

Đừng chỉ dựa vào việc trang Swagger UI mở được. UI có thể tải HTML thành công nhưng document JSON lại lỗi hoặc thiếu operation.

## 14. Kiểm tra các thay đổi có thể làm document khác sau nâng cấp

Ngay cả khi HTTP API không đổi, schema được sinh ra có thể thay đổi do Spring Boot, swagger-core, Jackson, validation hoặc springdoc được nâng cấp.

Hãy review:

- Required và nullable của property.
- Kiểu số, date/time và format.
- Enum và tên schema component.
- Generic wrapper, Page, Pageable và HATEOAS model.
- Request parameter được suy ra từ tên method parameter.
- Response code từ @ResponseStatus và @ControllerAdvice.
- Security requirement ở cấp root và operation.
- Server URL sau proxy/context path.
- OpenAPI version trong field openapi.

Một số lỗi parameter không được sinh có thể liên quan việc Spring Boot 3.2 thay đổi parameter name discovery. Tài liệu springdoc hướng dẫn bật compiler option -parameters trong Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Nếu document thay đổi, so sánh JSON/YAML và xác định thay đổi đến từ controller, DTO, Spring Boot, springdoc hay swagger-core trước khi cập nhật baseline.

## 15. Lộ trình nâng cấp từ v1 lên v2

Đối với ứng dụng Boot 2:

1. Chốt Boot minor và Java runtime mục tiêu.
2. Nâng nền tảng ứng dụng lên Spring Boot 3 và Java 17 theo migration guide.
3. Chuyển import Java EE từ javax sang jakarta ở những API thuộc Jakarta EE.
4. Xóa artifact springdoc v1.
5. Thêm starter v2 phù hợp MVC hoặc WebFlux.
6. Chuyển các package/class springdoc theo bảng migration.
7. Cập nhật test và cấu hình OpenAPI.
8. Build, khởi động, tải JSON/YAML và kiểm tra Swagger UI.
9. Review semantic diff và runtime contract tests.
10. Chỉ phát hành khi dependency graph và API contract đều đạt.

Không nâng springdoc v1 lên v2 trong khi vẫn giữ Boot 2. Nếu chưa thể nâng Boot 3, giữ nhánh v1 phù hợp và lập kế hoạch chuyển nền tảng riêng.

## 16. Lộ trình nâng cấp từ v2 lên v3

Đối với ứng dụng Boot 3:

1. Xác định Boot 4 minor line mục tiêu.
2. Kiểm tra Java 17+ và các yêu cầu của Spring Framework 7.
3. Đọc Spring Boot 4 migration guide cho ứng dụng.
4. Cập nhật dependency management và plugin build.
5. Thay springdoc v2 bằng v3 đã được xác nhận cho Boot minor đó.
6. Giữ đúng starter webmvc hoặc webflux.
7. Compile lại customizer và code tích hợp springdoc.
8. Kiểm tra cấu hình, auto-configuration và security.
9. Sinh OpenAPI JSON/YAML, validate và semantic diff.
10. Chạy integration test trên runtime Boot 4.

Nếu Boot minor chưa có trong ma trận springdoc, hãy chờ release hỗ trợ hoặc thực hiện đánh giá tương thích riêng có kiểm thử. Không gắn nhãn production-ready chỉ vì build thành công.

## 17. Chọn nhánh theo tình huống

| Tình huống | Hướng chọn |
|---|---|
| Ứng dụng cũ đang chạy Boot 2.7 | Dùng springdoc v1 trong dải hỗ trợ; 1.8.0 là bản OSS cuối |
| Dự án đang nâng Boot 2 lên Boot 3 | Chuyển sang springdoc v2 sau khi xử lý Jakarta và Java 17 |
| Dự án mới trên Boot 3.5 | Chọn springdoc 2.8.x–2.10.x theo ma trận; 2.10.0 là bản stable mới nhất tại thời điểm bài viết |
| Dự án trên Boot 4.0 | Chọn springdoc 3.0.x |
| Dự án trên Boot 4.1 | Chọn springdoc 3.1.x–3.2.x |
| Dự án trên Boot 4.2.0 | Ma trận hiện hành chưa xác nhận; kiểm tra release springdoc mới hơn trước khi chốt |
| Ứng dụng chỉ cần OpenAPI cho CI | Chọn starter API-only, không cần starter UI |
| Ứng dụng cần Swagger UI | Chọn starter UI đúng MVC/WebFlux |

## 18. Troubleshooting theo dấu hiệu

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không resolve được starter | Sai artifact name hoặc version line | Đối chiếu starter theo major và web stack |
| Boot 3 báo thiếu javax/jakarta class | Còn thư viện Java EE cũ hoặc chưa migration Jakarta | Kiểm tra import và dependency tree |
| Boot 3 lỗi với springdoc v1 | Dùng nhầm major | Chuyển sang springdoc v2 |
| Boot 4 lỗi với springdoc v2 | Dùng nhánh không dành cho Boot 4 | Chuyển sang v3 nằm trong ma trận |
| NoSuchMethodError trong swagger-core | Dependency bắc cầu bị override | Dùng version được springdoc quản lý và kiểm tra dependency tree |
| Không thấy GroupedOpenApi class cũ | Package đã chuyển khi v1 lên v2 | Cập nhật import sang org.springdoc.core.models |
| Customizer không compile | OpenApiCustomiser đổi thành OpenApiCustomizer | Cập nhật tên class và package |
| Swagger UI mở nhưng document lỗi | API docs endpoint hoặc serializer bị ảnh hưởng | Gọi trực tiếp /v3/api-docs và xem response/log |
| Parameter biến mất sau nâng Boot 3.2 | Parameter name metadata không được giữ | Bật compiler option -parameters |
| Document có required/nullable khác | Thay đổi schema inference hoặc dependency version | Review schema diff và kiểm tra runtime payload |
| Cả MVC và WebFlux starter cùng xuất hiện | Dependency graph không đúng stack | Chọn một web stack và starter tương ứng |

## 19. Checklist trước khi chốt phiên bản

- [ ] Đã xác định chính xác Spring Boot major và minor.
- [ ] Đã chọn đúng springdoc major tương ứng.
- [ ] Minor/patch springdoc nằm trong ma trận đã công bố.
- [ ] Java runtime đáp ứng yêu cầu của Spring Boot.
- [ ] Spring Framework và Jakarta APIs đúng baseline.
- [ ] Chỉ có một major springdoc trong dependency graph.
- [ ] Starter phù hợp với MVC hoặc WebFlux.
- [ ] Chỉ dùng UI starter khi thực sự cần Swagger UI.
- [ ] Đã xử lý module/package rename nếu nâng từ v1 lên v2.
- [ ] Đã cập nhật javax sang jakarta khi nâng nền tảng Boot 3.
- [ ] Đã đọc migration guide khi nâng lên Boot 4.
- [ ] Không override swagger-core/annotations ngoài chủ đích.
- [ ] OpenAPI JSON/YAML tải được và hợp lệ.
- [ ] Swagger UI hiển thị đúng document.
- [ ] Operation, schema, security và server URL đã được kiểm tra.
- [ ] Semantic diff và runtime contract tests đã PASS.

## 20. Tài liệu tham khảo chính thức

- [springdoc-openapi v1](https://springdoc.org/v1/): nhánh 1.8.0, Boot 1.x/2.x và ma trận tương thích.
- [springdoc-openapi v2](https://springdoc.org/v2/): nhánh 2.10.0, Boot 3.x và ma trận tương thích.
- [springdoc-openapi v3](https://springdoc.org/): nhánh 3.2.0, Boot 4.x và ma trận tương thích.
- [Migrating from springdoc-openapi v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html): đổi module, package và class khi lên v2.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6 và Jakarta EE.
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Java 17, Spring Framework 7 và build tool.
- [Spring Boot Wiki](https://github.com/spring-projects/spring-boot/wiki): migration guides và release notes theo thế hệ Boot.
- [springdoc-openapi Releases](https://github.com/springdoc/springdoc-openapi/releases): thay đổi từng phiên bản v1/v2/v3.

## Kết luận

Hãy chọn springdoc theo thế hệ Spring Boot: v1 cho Boot 1/2, v2 cho Boot 3 và v3 cho Boot 4. Sau đó đối chiếu minor line trong ma trận chính thức, vì không phải mọi patch của cùng một major đều đã được build với mọi minor Boot. Khi nâng v1 lên v2, xử lý module/package rename và chuyển Jakarta cùng Boot 3; khi nâng v2 lên v3, thực hiện migration Boot 4 và kiểm tra lại dependency graph, auto-configuration, schema và Swagger UI. Phiên bản thư viện springdoc không phải phiên bản OpenAPI được ghi trong document, và việc dependency resolve thành công không thay thế kiểm thử tương thích.
