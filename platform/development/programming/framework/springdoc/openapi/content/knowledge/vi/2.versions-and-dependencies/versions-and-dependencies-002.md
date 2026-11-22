# Đọc ma trận tương thích trước khi chọn thư viện

Chọn phiên bản springdoc-openapi chỉ dựa vào số phiên bản mới nhất rất dễ dẫn đến lỗi khởi động, thiếu auto-configuration hoặc xung đột dependency. springdoc chạy bên trong ứng dụng Spring Boot, vì vậy phiên bản của nó phải phù hợp với dòng Spring Boot, Spring Framework, Java và web stack mà ứng dụng đang sử dụng.

Trước khi thêm dependency, hãy trả lời bốn câu hỏi:

1. Ứng dụng đang dùng Spring Boot dòng nào và Spring Framework phiên bản nào được Boot quản lý?
2. Ứng dụng chạy trên Java nào và đang dùng namespace `javax.*` hay `jakarta.*`?
3. Web stack là Spring MVC (Servlet) hay Spring WebFlux (Reactive)?
4. Chỉ cần OpenAPI JSON/YAML hay cần cả giao diện Swagger UI?

Sau đó mới tra ma trận springdoc-openapi và chọn đúng starter. Ma trận là điểm bắt đầu để loại các tổ hợp không tương thích; dependency graph và kiểm thử ứng dụng mới xác nhận lựa chọn hoạt động trong dự án thực tế.

## 1. Vì sao cần đọc ma trận tương thích?

springdoc-openapi đọc controller, Spring mapping, DTO, validation và cấu hình ứng dụng để sinh OpenAPI document. Thư viện phụ thuộc vào API và auto-configuration của Spring Boot/Spring Framework. Khi Spring thay đổi package, extension point hoặc cơ chế khởi tạo bean, một dòng springdoc cũ có thể không còn hoạt động.

Ví dụ:

- Spring Boot 2 dựa trên Spring Framework 5 và hệ sinh thái Java EE dùng `javax.*`.
- Spring Boot 3 chuyển sang Spring Framework 6 và Jakarta namespace `jakarta.*`.
- Spring Boot 4 dùng thế hệ Spring Framework 7 và tiếp tục dùng Jakarta namespace.

Một thư viện được biên dịch cho Spring Boot 2 không thể mặc nhiên chạy với Spring Boot 4 chỉ vì cả hai đều chạy trên JVM. Khác biệt nằm ở API mà thư viện liên kết, không chỉ ở bytecode Java.

Chọn sai phiên bản có thể gây:

- `NoSuchMethodError`, `NoClassDefFoundError` hoặc `ClassNotFoundException` khi khởi động.
- Không nạp được auto-configuration của springdoc.
- Thiếu endpoint `/v3/api-docs` hoặc Swagger UI.
- Lỗi do trộn `javax.servlet` với `jakarta.servlet`.
- Xung đột phiên bản `swagger-core`, Jackson hoặc Spring Framework.
- Ứng dụng khởi động được nhưng lỗi khi request tài liệu hoặc serialize schema.

## 2. Đọc ma trận springdoc-openapi và Spring Boot

Ma trận chính thức của springdoc ghi lại những dòng Spring Boot mà từng dòng springdoc đã được build. Tại thời điểm kiểm tra ngày **20/11/2026**, các tổ hợp được công bố như sau:

| Spring Boot | Dòng springdoc-openapi tương thích được công bố |
|---|---|
| `4.1.x` | `3.1.x` – `3.2.x` |
| `4.0.x` | `3.0.x` |
| `3.5.x` | `2.8.x` – `2.10.x` |
| `3.4.x` | `2.7.x` – `2.8.x` |
| `3.3.x` | `2.6.x` |
| `3.2.x` | `2.3.x` – `2.5.x` |
| `3.1.x` | `2.2.x` |
| `3.0.x` | `2.0.x` – `2.1.x` |
| `2.7.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.6.11` |
| `2.6.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.6.0` |
| `2.5.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.5.9` |
| `2.4.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.5.0` |
| `2.3.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.4.0` |
| `2.2.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.2.1` |
| `2.0.x` | Dòng `1.x`; tài liệu v1 liệt kê tối thiểu `1.0.0` |

Đây là các tổ hợp được tài liệu dự án công bố đã build, không phải cam kết rằng mọi patch version hoặc mọi dependency tùy biến đều tương thích. Hãy đọc trang tương ứng với major line đang dùng:

- Spring Boot 4: [springdoc-openapi hiện hành](https://springdoc.org/).
- Spring Boot 3: [tài liệu springdoc-openapi v2](https://springdoc.org/v2/).
- Spring Boot 2 và 1: [tài liệu springdoc-openapi v1](https://springdoc.org/v1/).

### Quy tắc chọn major version

| Dòng Spring Boot | Major springdoc cần chọn | Ghi chú |
|---|---|---|
| Spring Boot 4.x | springdoc 3.x | Dòng hiện hành cho Spring Boot 4 |
| Spring Boot 3.x | springdoc 2.x | Dòng dành cho Spring Boot 3 |
| Spring Boot 2.x hoặc 1.x | springdoc 1.x | Dòng legacy; bản open-source mới nhất được công bố là `1.8.0` |

Không dùng springdoc 3.x với Spring Boot 3 chỉ vì số `3` lớn hơn `2`. Hai con số thuộc hai dự án khác nhau. Major version của springdoc được chọn theo dòng Spring Boot, không theo thói quen “lấy bản lớn nhất”.

### Chọn bản ổn định trong dải tương thích

Nếu ứng dụng dùng Spring Boot `3.5.x`, ma trận cho phép springdoc `2.8.x` đến `2.10.x`. Khi bắt đầu tích hợp mới, ưu tiên patch ổn định mới nhất trong dải tương thích, sau đó chạy kiểm thử với dependency graph thực tế.

Nếu dự án đang bị khóa bởi một dependency khác hoặc cần nâng cấp từng bước, có thể chọn bản thấp hơn trong dải. Ghi lại lý do và kế hoạch cập nhật để tránh giữ phiên bản cũ vô thời hạn.

Không lấy phiên bản `SNAPSHOT`, milestone hoặc release candidate làm mặc định cho production. Nếu phải thử bản preview, cần đánh dấu rõ trong build, chạy regression test và không coi đó là tổ hợp ổn định đã được ma trận xác nhận.

## 3. Ma trận không chỉ có Spring Boot

Spring Boot quản lý một bộ dependency gồm Spring Framework, Spring Security, Jackson và nhiều thư viện khác. Vì vậy, cần kiểm tra thêm Java, Spring Framework và namespace.

| Thành phần | Spring Boot 2.x | Spring Boot 3.x | Spring Boot 4.x |
|---|---|---|---|
| Thế hệ Spring Framework | 5.x | 6.x | 7.x |
| Namespace web phổ biến | `javax.*` | `jakarta.*` | `jakarta.*` |
| Dòng springdoc | 1.x | 2.x | 3.x |
| Yêu cầu Java | Phụ thuộc bản Boot cụ thể; có thể thấp hơn Java 17 | Java 17 trở lên | Java 17 trở lên |

Spring Boot 4.1.2 hiện yêu cầu ít nhất Java 17 và Spring Framework 7.0.10 trở lên. Spring Framework 7.x dùng Jakarta EE namespace. Spring Boot 3 cũng đã chuyển sang Jakarta namespace; khi nâng từ Boot 2 lên Boot 3, các import như `javax.servlet.*`, `javax.validation.*` hoặc `javax.persistence.*` thường phải chuyển sang package `jakarta.*` tương ứng.

Hãy kiểm tra system requirements của đúng patch Spring Boot thay vì chỉ đọc bảng tổng quát. [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) và [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) là hai nguồn cần đối chiếu.

### Ví dụ lỗi namespace

Một filter cũ có thể import:

~~~java
import javax.servlet.Filter;
~~~

Trong ứng dụng Spring Boot 3/4, API Servlet dùng Jakarta:

~~~java
import jakarta.servlet.Filter;
~~~

Thêm một starter springdoc đúng major không tự chuyển mã nguồn `javax.*` sang `jakarta.*`. Việc nâng framework, source code và thư viện phải được xem như một kế hoạch migration đồng bộ.

## 4. Xác định phiên bản Spring Boot thực tế của dự án

Không chỉ nhìn vào một dòng dependency trong `pom.xml` hoặc `build.gradle`. Dự án có thể dùng parent, BOM, version catalog hoặc plugin quản lý phiên bản.

Với Maven, kiểm tra:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Các lệnh cho biết dependency đã được resolve, không chỉ là version khai báo ban đầu. Nếu nhiều module cùng dùng Spring Boot, kiểm tra đúng subproject chứa ứng dụng Springdoc.

Ghi nhận tối thiểu:

- Phiên bản `spring-boot` và `spring-boot-autoconfigure`.
- Phiên bản `spring-core`, `spring-context` và `spring-webmvc` hoặc `spring-webflux`.
- Phiên bản Java dùng để compile và chạy ứng dụng.
- Web starter thực tế được đưa vào runtime classpath.
- Major của Spring Security nếu có.
- Các dependency `swagger-core`, Jackson và thư viện liên quan do dự án override.

Nếu `spring-boot-starter-parent` hoặc `spring-boot-dependencies` quản lý Spring Framework, hãy để BOM của Boot quyết định phiên bản các module Spring. Tránh đặt thủ công `spring-core` khác dòng với Boot.

## 5. Chọn đúng WebMVC hay WebFlux

springdoc có starter riêng cho hai web stack. Chọn theo runtime thực tế của ứng dụng:

| Web stack của ứng dụng | Chỉ cần OpenAPI JSON/YAML | Cần cả Swagger UI |
|---|---|---|
| Spring MVC / Servlet (`spring-boot-starter-web`) | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux / Reactive (`spring-boot-starter-webflux`) | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

Không chọn `webflux` chỉ vì controller trả `Mono` hoặc `Flux` trong một dự án có runtime Servlet; hãy kiểm tra web application type và dependency thực tế. Ngược lại, không dùng starter WebMVC cho ứng dụng chạy Netty/WebFlux thuần.

Nếu chỉ phát hành file OpenAPI cho API portal hoặc pipeline code generation, starter `*-api` thường đủ. Nếu người dùng cần giao diện tương tác để xem operation và thử request, chọn starter `*-ui`.

## 6. Chọn đúng artifact theo mục đích

Ví dụ với Spring Boot 4.1.x và springdoc 3.2.0:

| Artifact | Dùng khi |
|---|---|
| `springdoc-openapi-starter-webmvc-api` | Ứng dụng Servlet cần endpoint OpenAPI nhưng không cần Swagger UI |
| `springdoc-openapi-starter-webmvc-ui` | Ứng dụng Servlet cần OpenAPI và Swagger UI |
| `springdoc-openapi-starter-webflux-api` | Ứng dụng Reactive cần endpoint OpenAPI nhưng không cần Swagger UI |
| `springdoc-openapi-starter-webflux-ui` | Ứng dụng Reactive cần OpenAPI và Swagger UI |

Ví dụ endpoint mặc định:

- OpenAPI JSON: `/v3/api-docs`.
- OpenAPI YAML: `/v3/api-docs.yaml`.
- Swagger UI: `/swagger-ui.html`.

Các path có thể được đổi bằng property và có thể có context path. Việc chọn starter chỉ quyết định module tích hợp; nó không thay thế việc kiểm tra URL sau khi ứng dụng chạy.

## 7. Ví dụ Maven cho Spring Boot 4

Ví dụ sau dùng Spring Boot `4.1.2`, Java 17 trở lên và springdoc `3.2.0`. Ứng dụng dùng Spring MVC và cần Swagger UI:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

Spring Boot parent quản lý các dependency Spring Boot/Spring Framework. Phiên bản springdoc được chọn từ ma trận tương thích. Không cần tự khai báo phiên bản cho `spring-boot-starter-web` khi đã dùng Boot parent.

Nếu dự án chỉ cần OpenAPI JSON/YAML, thay artifact UI bằng:

~~~xml
<artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
~~~

Nếu dùng WebFlux, chọn artifact `springdoc-openapi-starter-webflux-api` hoặc `springdoc-openapi-starter-webflux-ui` tương ứng.

## 8. Quản lý các module springdoc bằng BOM

Từ springdoc `2.8.7`, dự án cung cấp BOM để quản lý đồng bộ phiên bản các module springdoc. Nếu dự án dùng nhiều module như API, UI hoặc hỗ trợ tích hợp khác, có thể import BOM:

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

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    </dependency>
</dependencies>
~~~

BOM của Spring Boot quản lý các thư viện thuộc hệ sinh thái Boot; BOM của springdoc quản lý các module springdoc. Hai BOM có phạm vi khác nhau và có thể được dùng cùng nhau.

Không import một BOM springdoc của major khác với dòng Boot đang chạy. BOM chỉ đồng bộ các artifact trong cùng dự án; nó không biến springdoc 3.x thành phiên bản tương thích với Boot 3.

## 9. Ví dụ Maven cho Spring Boot 3

Nếu ứng dụng đang dùng Spring Boot `3.5.x`, chọn springdoc `2.8.x` đến `2.10.x` theo ma trận. Ví dụ dùng `2.10.0`:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.10.0</version>
    </dependency>
</dependencies>
~~~

Không copy dependency của Boot 4 vào dự án Boot 3 rồi chỉ thay parent version. Hãy kiểm tra artifact, major springdoc và namespace của toàn bộ dependency trước khi build.

## 10. Ví dụ Gradle Kotlin DSL

Với Gradle, có thể import BOM springdoc để không phải ghi version lặp lại ở từng module:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    implementation(platform("org.springdoc:springdoc-openapi-bom:3.2.0"))
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui")
}
~~~

Ví dụ giả định Spring Boot Gradle plugin hoặc dependency management của dự án đã quản lý phiên bản Spring Boot. Nếu không dùng cơ chế quản lý dependency đó, cần import thêm Spring Boot dependencies BOM theo cấu hình Gradle của dự án.

Với Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    implementation platform('org.springdoc:springdoc-openapi-bom:3.2.0')
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui'
}
~~~

Đổi `3.2.0` và starter theo dòng Boot, web stack và mục tiêu tài liệu của ứng dụng. Không trộn starter WebMVC và WebFlux trong cùng runtime chỉ để thử cả hai module.

## 11. Hiểu khác biệt module giữa springdoc v1 và v2/v3

Khi nâng từ springdoc v1 lên v2 hoặc v3, tên artifact và một số package Java đã thay đổi. Ví dụ:

| springdoc v1 | springdoc v2/v3 | Ý nghĩa |
|---|---|---|
| `springdoc-openapi-webmvc-core` | `springdoc-openapi-starter-webmvc-api` | OpenAPI cho Spring MVC |
| `springdoc-openapi-webflux-core` | `springdoc-openapi-starter-webflux-api` | OpenAPI cho WebFlux |
| `springdoc-openapi-ui` | `springdoc-openapi-starter-webmvc-ui` | Swagger UI cho Spring MVC |
| `springdoc-openapi-webflux-ui` | `springdoc-openapi-starter-webflux-ui` | Swagger UI cho WebFlux |
| `org.springdoc.core.GroupedOpenApi` | `org.springdoc.core.models.GroupedOpenApi` | Package của group API |
| `org.springdoc.core.customizers.OpenApiCustomiser` | `org.springdoc.core.customizers.OpenApiCustomizer` | Tên customizer |
| `org.springdoc.api.annotations.ParameterObject` | `org.springdoc.core.annotations.ParameterObject` | Package của ParameterObject |

Không chỉ đổi version trong POM rồi giữ nguyên toàn bộ import. Khi nâng major, đọc hướng dẫn migration của dòng đích và sửa package/import tương ứng. v2 và v3 dùng cấu trúc starter mới; v3 nhắm Spring Boot 4, v2 nhắm Spring Boot 3.

## 12. Tránh xung đột dependency bắc cầu

springdoc kéo theo các thành phần liên quan đến OpenAPI và Swagger UI. Không nên override riêng lẻ các dependency sau nếu chưa có bằng chứng cần thiết:

- `io.swagger.core.v3:swagger-core` hoặc `swagger-annotations`.
- Các artifact Swagger UI.
- Jackson databind và Jackson modules.
- Spring Framework modules như `spring-web`, `spring-core`, `spring-context`.
- Servlet API hoặc Reactive Streams API.

Ví dụ, ép `swagger-core` lên phiên bản mới hơn có thể làm springdoc gọi API không còn tồn tại trong phiên bản bị ép hoặc khiến schema serialize khác dự kiến. Tương tự, ép `spring-web` khác dòng với Spring Boot có thể tạo lỗi linkage lúc runtime.

Quy tắc an toàn:

1. Để Spring Boot BOM quản lý dependency Spring và Jackson mà Boot hỗ trợ.
2. Để springdoc BOM quản lý các module springdoc khi dùng nhiều artifact.
3. Chỉ override transitive dependency khi đã xác định nguyên nhân, kiểm tra tương thích và thêm test hồi quy.
4. Ghi rõ lý do override và người chịu trách nhiệm cập nhật.

## 13. Kiểm tra dependency graph sau khi thêm springdoc

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,org.springframework,io.swagger.core.v3,com.fasterxml.jackson.core
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Khi đọc kết quả, chú ý:

- Có nhiều version của cùng artifact hay không.
- Version được chọn đến từ BOM, constraint, resolution rule hay dependency trực tiếp nào.
- Có module springdoc v1 cũ còn sót trong graph không.
- Có đồng thời starter WebMVC và WebFlux không.
- Có phiên bản swagger-core hoặc Jackson bị ép khác với version mà springdoc mong đợi không.

Một dependency xuất hiện trong cây không nhất thiết là lỗi. Điều quan trọng là phiên bản được resolve có nằm trong tổ hợp tương thích và có gây xung đột với các module khác hay không.

## 14. Kiểm chứng lựa chọn bằng một vòng chạy ứng dụng

Sau khi dependency resolve và build thành công, hãy xác nhận integration hoạt động trong runtime:

1. Khởi động ứng dụng bằng profile gần với môi trường triển khai.
2. Kiểm tra log không có `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi auto-configuration.
3. Gọi `GET /v3/api-docs` và xác nhận trả OpenAPI JSON.
4. Gọi `GET /v3/api-docs.yaml` nếu ứng dụng công bố YAML.
5. Mở `/swagger-ui.html` nếu đã chọn starter UI.
6. Kiểm tra một path, operation, parameter và schema thực tế có trong document.
7. Gọi thử một endpoint business để bảo đảm việc thêm springdoc không làm thay đổi mapping hoặc security.

Ví dụ:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Nếu ứng dụng dùng context path, port khác hoặc custom docs path, điều chỉnh URL theo cấu hình. Đừng kết luận thư viện lỗi khi request đang gọi sai base path.

## 15. Ma trận quyết định nhanh

| Tình huống | Lựa chọn ban đầu |
|---|---|
| Boot 4.1.x + Spring MVC + cần Swagger UI | springdoc 3.1.x–3.2.x, `webmvc-ui` |
| Boot 4.0.x + WebFlux + chỉ cần JSON/YAML | springdoc 3.0.x, `webflux-api` |
| Boot 3.5.x + Spring MVC + cần Swagger UI | springdoc 2.8.x–2.10.x, `webmvc-ui` |
| Boot 3.3.x + WebFlux + cần JSON/YAML | springdoc 2.6.x, `webflux-api` |
| Boot 3.0.x + Spring MVC + cần Swagger UI | springdoc 2.0.x–2.1.x, `webmvc-ui` |
| Boot 2.7.x + Spring MVC | springdoc v1; kiểm tra giới hạn legacy và bản open-source `1.8.0` |
| Bất kỳ dòng Boot nào chỉ cần build artifact OpenAPI | Chọn starter `*-api` tương ứng web stack và major |
| Cần Swagger UI trong ứng dụng | Chọn starter `*-ui` tương ứng web stack và major |

Bảng này dùng để chọn hướng ban đầu. Trước khi merge, vẫn phải xác nhận Java, Spring Framework, dependency graph và runtime smoke test.

## 16. Lỗi thường gặp khi chọn phiên bản

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Boot 3 nhưng thêm springdoc 3.x | Nhầm major springdoc với major Spring Boot | Dùng dòng springdoc 2.x cho Boot 3 |
| Boot 4 nhưng dùng springdoc 2.x | Chọn dependency theo dự án Boot 3 cũ | Dùng dòng springdoc 3.x theo ma trận Boot 4 |
| `/v3/api-docs` trả 404 | Starter không đúng web stack hoặc auto-configuration không được nạp | Kiểm tra MVC/WebFlux starter và dependency graph |
| Lỗi `NoSuchMethodError` sau khi thêm thư viện | Xung đột phiên bản Spring/Swagger/Jackson | Kiểm tra dependency tree và gỡ override không cần thiết |
| Lỗi `ClassNotFoundException` với Servlet | Trộn `javax.*` và `jakarta.*` | Đồng bộ Boot major và namespace |
| Swagger UI không có nhưng JSON docs hoạt động | Đang dùng starter `*-api` | Chuyển sang starter `*-ui` nếu cần UI |
| Swagger UI lỗi khi dùng WebFlux | Đã chọn starter WebMVC | Chọn `springdoc-openapi-starter-webflux-ui` |
| Dùng springdoc v1 trên Boot 3/4 | Giữ artifact legacy sau khi nâng Boot | Chuyển sang v2 cho Boot 3 hoặc v3 cho Boot 4 |
| Build pass nhưng runtime lỗi | Chưa kiểm tra dependency runtime hoặc auto-configuration | Chạy ứng dụng, gọi `/v3/api-docs`, xem log |
| Version thay đổi giữa máy local và CI | Không pin version hoặc BOM khác nhau | Khóa BOM/version và kiểm tra effective dependency graph |
| Tài liệu sai sau khi ép Jackson | Jackson version không đồng bộ với Boot/springdoc | Bỏ override hoặc xác minh compatibility bằng test |
| Group không xuất hiện | Bean group không được component scan hoặc starter/cấu hình sai | Kiểm tra cấu hình group và package scan |

## 17. Quy trình chọn thư viện trước khi commit

Thực hiện lần lượt:

1. Đọc phiên bản Spring Boot từ parent, BOM hoặc plugin của dự án.
2. Xác nhận phiên bản Spring Framework thực tế trong runtime classpath.
3. Kiểm tra Java target và Java runtime.
4. Xác định namespace `javax.*` hay `jakarta.*`.
5. Xác định web stack: Spring MVC hay WebFlux.
6. Tra đúng trang ma trận springdoc v1, v2 hoặc v3.
7. Chọn patch ổn định mới nhất trong dải tương thích được công bố.
8. Chọn starter `webmvc`/`webflux` và `api`/`ui` theo nhu cầu.
9. Dùng BOM phù hợp để quản lý các module.
10. Kiểm tra dependency graph, build và runtime endpoints.
11. Lưu phiên bản đã chọn trong build file và ghi chú nếu có override.
12. Chạy smoke test trong CI để phát hiện sai lệch khi dependency thay đổi.

## 18. Checklist trước khi merge

- [ ] Đã xác định chính xác phiên bản Spring Boot.
- [ ] Đã đối chiếu phiên bản Spring Framework và Java runtime.
- [ ] Đã chọn đúng major springdoc theo ma trận chính thức.
- [ ] Đã kiểm tra namespace `javax.*`/`jakarta.*`.
- [ ] Đã chọn đúng WebMVC hoặc WebFlux starter.
- [ ] Đã chọn `*-api` hoặc `*-ui` theo nhu cầu.
- [ ] Không trộn module springdoc v1, v2 và v3 trong cùng runtime.
- [ ] Spring Boot BOM quản lý dependency Spring.
- [ ] springdoc BOM được dùng khi cần đồng bộ nhiều module springdoc.
- [ ] Không override swagger-core, Jackson hoặc Spring Framework tùy tiện.
- [ ] Dependency tree không có xung đột chưa giải thích.
- [ ] Ứng dụng khởi động thành công.
- [ ] `/v3/api-docs` trả document hợp lệ.
- [ ] Swagger UI hoạt động nếu starter UI được chọn.
- [ ] Có smoke test cho endpoint tài liệu trong CI.

## 19. Tài liệu tham khảo chính thức

- [springdoc-openapi v3 — Compatibility matrix and getting started](https://springdoc.org/) — ma trận Spring Boot 4, dependency starters, module WebMVC/WebFlux và BOM.
- [springdoc-openapi v2 — Compatibility matrix](https://springdoc.org/v2/) — các dải springdoc 2.x tương thích Spring Boot 3.x.
- [springdoc-openapi v1 — Compatibility matrix](https://springdoc.org/v1/) — các bản legacy hỗ trợ Spring Boot 2.x và 1.x.
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) — yêu cầu Java, Spring Framework và build tool theo phiên bản Boot.
- [Spring Framework — Supported Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) — vòng đời framework, JDK range và Java/Jakarta EE namespace.
- [springdoc-openapi — GitHub repository](https://github.com/springdoc/springdoc-openapi) — mã nguồn, release và hướng dẫn dự án.

Đọc ma trận tương thích trước khi chọn thư viện giúp loại bỏ sớm các tổ hợp sai major. Sau đó cần đối chiếu Java, Spring Framework, namespace và web stack, chọn đúng starter, kiểm tra dependency graph và xác nhận các endpoint tài liệu trong runtime. Một lựa chọn chỉ được xem là hoàn tất khi build, ứng dụng và OpenAPI document đều hoạt động trong cấu hình thực tế.
