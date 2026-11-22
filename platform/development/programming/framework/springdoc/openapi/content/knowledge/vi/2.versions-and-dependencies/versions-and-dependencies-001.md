# Phân biệt phiên bản Spring Boot, Springdoc và đặc tả OpenAPI

Khi thêm springdoc-openapi vào một ứng dụng Spring Boot, có ít nhất ba loại phiên bản cần phân biệt: phiên bản Spring Boot, phiên bản thư viện springdoc-openapi và phiên bản đặc tả OpenAPI mà ứng dụng xuất ra. Ba con số này không cần giống nhau và không thay thế cho nhau. Một ứng dụng có thể chạy Spring Boot 4.1, dùng springdoc 3.2.0 nhưng vẫn xuất document theo OpenAPI 3.0 nếu cấu hình và consumer yêu cầu.

Chọn sai dòng springdoc có thể làm ứng dụng không khởi động, thiếu auto-configuration hoặc gặp lỗi tương thích với Spring Framework, Jakarta API, Swagger Core và Jackson. Chọn sai phiên bản OpenAPI có thể khiến SDK generator, API gateway hoặc tool registry không đọc được schema như mong đợi. Vì vậy, cần xác định nền tảng Spring trước, chọn springdoc theo compatibility matrix, rồi chọn OpenAPI version theo khả năng của consumer.

## 1. Ba trục phiên bản và phiên bản API công khai

| Trục | Ví dụ | Quyết định điều gì? |
| --- | --- | --- |
| Spring Boot | `4.1.2`, `3.5.16` | Nền tảng ứng dụng, Spring Framework, auto-configuration, dependency management và yêu cầu Java. |
| springdoc-openapi | `3.2.0`, `2.10.0` | Phiên bản thư viện tích hợp Spring, quét controller/model và sinh tài liệu. |
| OpenAPI Specification | `3.1.0`, `3.0.1` | Cú pháp và ngữ nghĩa của document JSON/YAML được sinh ra. |
| API version (`info.version`) | `1.4.0`, `2026-11` | Phiên bản hợp đồng API do đội phát triển công bố cho consumer. |

Ba trục đầu có quan hệ tương thích nhưng có vòng đời riêng. `info.version` là metadata mô tả API, không phải phiên bản Spring Boot, springdoc hoặc OpenAPI Specification. Ví dụ, thay springdoc từ `2.9.x` lên `2.10.x` không bắt buộc phải đổi `info.version` nếu hợp đồng API không thay đổi.

Trong OpenAPI document, trường đầu tài liệu:

~~~yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.4.0
~~~

`openapi: 3.1.0` cho biết document tuân theo phiên bản OpenAPI Specification 3.1.0. `info.version: 1.4.0` là phiên bản API mà nhóm phát triển công bố. Hai trường này có ý nghĩa khác nhau.

## 2. Compatibility matrix giữa Spring Boot và springdoc

Springdoc duy trì các dòng chính khác nhau cho từng thế hệ Spring Boot. Theo compatibility matrix chính thức được kiểm tra ngày 20-11-2026:

| Spring Boot | Dòng springdoc được xây dựng tương thích |
| --- | --- |
| `4.1.x` | `3.1.x` – `3.2.x` |
| `4.0.x` | `3.0.x` |
| `3.5.x` | `2.8.x` – `2.10.x` |
| `3.4.x` | `2.7.x` – `2.8.x` |
| `3.3.x` | `2.6.x` |
| `3.2.x` | `2.3.x` – `2.5.x` |
| `3.1.x` | `2.2.x` |
| `3.0.x` | `2.0.x` – `2.1.x` |
| Spring Boot `2.x` và `1.x` | Dòng legacy `springdoc 1.x`; `1.8.0` là bản Open Source cuối cùng được công bố cho các dòng này. |

Ma trận là hướng dẫn chọn dòng thư viện, không có nghĩa mọi patch release trong một khoảng đều đã được kiểm thử với mọi patch release của Spring Boot. Khi chọn phiên bản cụ thể, hãy đọc release notes và compatibility matrix của đúng dòng. Không suy luận rằng một phiên bản springdoc mới hơn luôn tương thích ngược với mọi Spring Boot cũ.

Tại thời điểm kiểm tra, tài liệu chính thức liệt kê `springdoc 3.2.0` cho dòng Spring Boot `4.1.x` và `springdoc 2.10.0` cho dòng Spring Boot `3.5.x`. Đây là mốc tham khảo tại ngày nêu trên; trước mỗi lần nâng cấp, hãy kiểm tra lại trang release và ma trận vì dự án có thể phát hành bản mới.

### 2.1. Vì sao Boot 2, Boot 3 và Boot 4 dùng các dòng khác nhau?

- **Spring Boot 1.x/2.x:** thuộc dòng springdoc 1.x. Đây là dòng legacy dùng hệ sinh thái Spring cũ và namespace Java EE `javax.*`. Bản `1.8.0` là bản Open Source cuối cùng được công bố cho các dòng này.
- **Spring Boot 3.x:** dùng springdoc 2.x. Boot 3 yêu cầu Java 17 trở lên và chuyển sang Jakarta EE 9 với namespace `jakarta.*`. Springdoc 2 được xây dựng cho thế hệ nền tảng này.
- **Spring Boot 4.x:** dùng springdoc 3.x. Không chọn springdoc 2 chỉ vì ứng dụng trước đây dùng Boot 3; Boot 4 thuộc dòng tích hợp mới.

Khi nâng Boot 2 lên Boot 3, ngoài đổi springdoc 1.x sang 2.x, còn phải xử lý thay đổi namespace `javax.*` sang `jakarta.*` và các thay đổi lớn của Spring Framework. Khi nâng Boot 3 lên Boot 4, chọn springdoc 3.x và kiểm tra các thay đổi tương thích của Spring Boot 4. Không xem đây là thao tác chỉ thay một số dependency.

## 3. Chọn starter theo web stack và nhu cầu giao diện

Springdoc cung cấp starter riêng cho Spring MVC, WebFlux và việc có hoặc không có giao diện Swagger UI:

| Web stack | Có Swagger UI | Chỉ cần OpenAPI endpoint |
| --- | --- | --- |
| Spring MVC / Servlet | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux / Reactive | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

Chọn đúng một starter theo stack thực tế. Với Spring Boot 3, ứng dụng Spring MVC thường dùng `spring-boot-starter-web`; ứng dụng WebFlux dùng `spring-boot-starter-webflux`. Từ Spring Boot 4, starter MVC được đổi tên thành `spring-boot-starter-webmvc`; `spring-boot-starter-web` vẫn còn nhưng đã deprecated để chuyển sang tên mới. Ứng dụng WebFlux tiếp tục dùng starter WebFlux tương ứng. Không thêm cả hai springdoc UI starter chỉ để thử nghiệm, vì có thể kéo theo cấu hình và dependency không cần thiết.

Nếu chỉ xuất OpenAPI JSON/YAML cho API catalog, CI hoặc SDK generator, starter `*-api` là đủ. Nếu người phát triển cần giao diện tương tác, chọn starter `*-ui`. Không cần thêm một dependency Swagger UI riêng khi starter UI của springdoc đã cung cấp tích hợp đó.

Các artifact starter trên dành cho các dòng springdoc hiện đại. Dự án legacy springdoc 1.x dùng cách đặt tên module cũ; không sao chép tọa độ Maven của v2/v3 vào ứng dụng Boot 2 mà chưa đối chiếu tài liệu v1.

## 4. Ví dụ Maven cho Spring Boot 4.1 và springdoc 3.2

Với ứng dụng Spring MVC chạy Spring Boot 4.1.x, có thể dùng starter WebMVC UI. Ví dụ dưới đây minh họa mốc tương thích được tài liệu springdoc công bố tại thời điểm kiểm tra:

~~~xml
<properties>
    <java.version>17</java.version>
    <springdoc.version>3.2.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Ví dụ giả định dự án đã dùng `spring-boot-starter-parent` hoặc import Spring Boot dependency BOM để quản lý các dependency Spring. Springdoc version được khai báo riêng vì Spring Boot BOM không tự động chọn dòng springdoc tương thích cho mọi ứng dụng.

## 5. Ví dụ Maven cho Spring Boot 3.5 và springdoc 2.10

Với ứng dụng Spring MVC chạy Spring Boot 3.5.x, chọn springdoc 2.10.x theo ma trận:

~~~xml
<properties>
    <java.version>17</java.version>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Nếu ứng dụng dùng WebFlux, dùng `spring-boot-starter-webflux` và springdoc artifact `springdoc-openapi-starter-webflux-ui`. Nếu chỉ cần JSON/YAML, thay hậu tố `-ui` bằng `-api`.

Không thêm `swagger-core`, `swagger-annotations` hoặc `swagger-ui` phiên bản tùy ý để sửa một lỗi trước khi kiểm tra dependency tree. Starter springdoc quản lý các dependency liên quan; override riêng một thành phần có thể làm các thư viện Swagger dùng các phiên bản không tương thích.

## 6. Ví dụ Gradle Kotlin DSL

Với Gradle, khai báo springdoc version thành một biến để dễ nâng cấp và review:

~~~kotlin
val springdocVersion = "2.10.0"

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
    )
}
~~~

Đoạn trên dành cho Spring Boot 3.5.x. Nếu dự án dùng Boot 4.1.x, chọn dòng springdoc 3.1.x–3.2.x theo ma trận hiện hành, ví dụ `3.2.0` ở thời điểm kiểm tra. Gradle không thay đổi nguyên tắc tương thích chỉ vì cú pháp dependency khác Maven.

Nếu dự án dùng version catalog (`libs.versions.toml`), đặt version trong catalog và tham chiếu alias trong `build.gradle.kts`. Tránh khai báo cùng một version ở nhiều file vì dễ tạo lệch khi nâng cấp.

## 7. Phiên bản OpenAPI Specification được xuất ra

Phiên bản springdoc quyết định khả năng tích hợp và phiên bản Swagger Core đi kèm; phiên bản OpenAPI document có thể được chọn riêng trong phạm vi mà springdoc hỗ trợ.

Tài liệu cấu hình hiện hành cung cấp property:

`springdoc.api-docs.version`

Property này chọn OpenAPI 3.0 hoặc OpenAPI 3.1. Ví dụ:

Trong tài liệu cấu hình hiện hành của springdoc v2/v3, giá trị mặc định là OpenAPI 3.1. Dòng springdoc v1 có mặc định OpenAPI 3.0; nếu nâng từ v1 lên v2, hãy kiểm tra trường `openapi` của document vì dialect mặc định có thể thay đổi dù controller không đổi.

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Nếu một API catalog hoặc SDK generator chỉ hỗ trợ OpenAPI 3.0, có thể cấu hình:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Hãy xác nhận giá trị property được hỗ trợ bởi đúng dòng springdoc đang dùng. Sau khi thay đổi, gọi `/v3/api-docs` và kiểm tra trường `openapi` ở đầu document; đừng chỉ dựa vào cấu hình YAML mà không kiểm tra output.

### 7.1. Khác biệt quan trọng giữa OpenAPI 3.0 và 3.1

OpenAPI 3.1 cập nhật mô hình Schema Object để gần với JSON Schema Draft 2020-12 hơn. Điều này mở rộng cách biểu diễn nullable, union type và các schema phức tạp. OpenAPI 3.0 dùng mô hình schema riêng với một số quy tắc khác, chẳng hạn thuộc tính `nullable`.

Ví dụ minh họa:

~~~yaml
# OpenAPI 3.0
type: string
nullable: true
~~~

~~~yaml
# OpenAPI 3.1
type:
  - string
  - "null"
~~~

Đây là ví dụ về cách biểu diễn schema; không phải mọi schema đều có thể chuyển đổi chỉ bằng cách thay trường `openapi`. Kiểm tra validator, SDK generator, API gateway, mock server và contract testing tool trước khi đổi dialect.

Nếu consumer còn phụ thuộc OpenAPI 3.0, giữ 3.0 trong thời gian chuyển tiếp có thể phù hợp hơn việc chuyển ngay sang 3.1. Nếu consumer đã hỗ trợ đầy đủ 3.1 và cần các khả năng schema mới, hãy nâng cấp có kiểm thử.

## 8. Không nhầm OpenAPI version với info.version

Ví dụ cấu hình document:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Và metadata API:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI storeApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Store API")
                .version("1.4.0"));
    }
}
~~~

Trong document kết quả, `openapi` mô tả phiên bản specification, còn `info.version` mô tả phiên bản API. Đổi `info.version` từ `1.4.0` thành `1.5.0` không tự chuyển document từ OpenAPI 3.0 sang 3.1. Đổi `springdoc.api-docs.version` cũng không tự phát hành API nghiệp vụ version mới.

## 9. Spring Boot BOM quản lý gì và không quản lý gì?

Spring Boot dependency management giúp chọn các phiên bản tương thích của Spring Framework, Jackson, logging, validation và nhiều thư viện tích hợp khác. Khi dùng Spring Boot parent hoặc BOM, thông thường không nên tự đặt phiên bản cho từng module `spring-core`, `spring-web`, `spring-context` hoặc Jackson nếu không có lý do cụ thể.

Springdoc là thư viện tích hợp bổ sung. Hãy chọn phiên bản springdoc theo compatibility matrix và khai báo rõ ràng trong Maven/Gradle. Không giả định Spring Boot BOM sẽ tự nâng springdoc lên dòng tương thích.

Các nguyên tắc:

- Giữ các dependency Spring Boot theo BOM của dự án.
- Khai báo một version springdoc rõ ràng, có thể dùng property/version catalog.
- Để starter springdoc quản lý phiên bản Swagger Core, annotations và UI đi kèm.
- Không override một module Swagger đơn lẻ khi chưa xác định nguyên nhân xung đột.
- Khi cần override dependency bắc cầu, kiểm tra release notes và chạy contract test cho document sinh ra.

## 10. Kiểm tra dependency tree khi có xung đột

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.springframework
~~~

Có thể kiểm tra POM hiệu lực:

~~~bash
./mvnw help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
~~~

Tìm các trường hợp:

- Có đồng thời springdoc 1.x và 2.x/3.x.
- Có nhiều starter MVC/WebFlux không cần thiết.
- Swagger Core hoặc `swagger-annotations` bị ép sang phiên bản khác với starter.
- Jackson/Spring Framework bị override khỏi phiên bản Spring Boot quản lý.
- Có dependency cũ `springdoc-openapi-ui` cùng starter mới.

Khi thấy nhiều phiên bản, đừng loại dependency ngẫu nhiên. Xem dependency nào kéo phiên bản đó vào, vì sao có mặt và starter nào cần nó. Sau khi điều chỉnh, chạy build và tải document để xác nhận auto-configuration vẫn hoạt động.

## 11. Chuyển từ springdoc 1.x sang 2.x

Đây thường là một phần của việc nâng Spring Boot 2 lên Boot 3. Các bước chính:

1. Nâng ứng dụng lên Java 17 trở lên.
2. Nâng Spring Boot lên dòng 3.x phù hợp với dependency của dự án.
3. Chuyển namespace Java EE `javax.*` sang Jakarta `jakarta.*` ở các API tương ứng.
4. Thay dependency springdoc 1.x bằng starter springdoc 2.x phù hợp với MVC hoặc WebFlux.
5. Kiểm tra các annotation Swagger, Spring Security, validation và customizer.
6. Build lại ứng dụng và kiểm tra `/v3/api-docs`, Swagger UI cùng các group.
7. So sánh OpenAPI document trước/sau nâng cấp để phát hiện schema, operation hoặc metadata thay đổi.

Không thay toàn bộ namespace bằng tìm-thay thế máy móc. Một số package Java tiêu chuẩn vẫn thuộc `javax.*`; chỉ các API đã chuyển sang Jakarta mới cần đổi. Kiểm tra compile error và hướng dẫn migration của Spring Boot.

## 12. Chuyển từ springdoc 2.x sang 3.x

Spring Boot 4 thuộc dòng springdoc 3.x. Khi nâng cấp:

1. Xác nhận ứng dụng đã đáp ứng yêu cầu nền tảng và Java của Spring Boot 4.
2. Chọn springdoc 3.x theo ma trận Boot 4.0/4.1 tương ứng.
3. Kiểm tra starter MVC hay WebFlux và module UI/API-only.
4. Đọc release notes của springdoc 3.x và Spring Boot 4.
5. Kiểm tra các API, auto-configuration, customizer và model converter mà ứng dụng đang dùng.
6. Chạy test khởi động context, contract test và kiểm tra JSON/YAML.
7. So sánh document với baseline trước khi phát hành.

Không giữ springdoc 2.x trong ứng dụng Boot 4 chỉ vì code compile được ở IDE. Compatibility matrix là cơ sở chọn dòng; test khởi động và kiểm tra document xác nhận tích hợp thực tế.

## 13. Quy trình nâng cấp an toàn

Khi cần nâng Spring Boot, springdoc hoặc OpenAPI dialect, chia công việc thành các bước có thể review:

1. Ghi nhận phiên bản Java, Spring Boot, springdoc và `openapi` hiện tại.
2. Lưu OpenAPI JSON/YAML hiện tại làm baseline.
3. Ghi lại các group, operationId, component schema và endpoint docs đang được consumer sử dụng.
4. Chọn phiên bản springdoc theo compatibility matrix của Spring Boot đích.
5. Thay dependency springdoc và xử lý migration source cần thiết.
6. Giữ nguyên OpenAPI dialect trong lần nâng cấp đầu nếu consumer chưa cần đổi.
7. Chạy test và sinh lại document ở cùng profile/cấu hình.
8. Diff document mới với baseline, phân loại thay đổi do dependency và thay đổi API có chủ đích.
9. Chỉ đổi OpenAPI 3.0 sang 3.1 trong một thay đổi riêng có kiểm thử consumer.
10. Phát hành và theo dõi lỗi từ SDK generator, gateway, registry hoặc client.

Tách nâng dependency khỏi thay đổi hợp đồng giúp tìm nguyên nhân khi document thay đổi. Nếu cùng lúc đổi Boot, springdoc, schema, operationId và OpenAPI dialect, rất khó xác định thay đổi nào gây lỗi.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng Boot 3 không khởi động với springdoc 1.x | Chọn sai dòng springdoc cho Boot 3/Jakarta | Chuyển sang springdoc 2.x phù hợp ma trận. |
| Ứng dụng Boot 4 lỗi auto-configuration | Dùng springdoc 2.x thay vì 3.x | Chọn springdoc 3.x theo đúng minor Boot 4. |
| Lỗi `ClassNotFoundException` hoặc `NoSuchMethodError` | Swagger Core/Spring/Jackson bị lệch phiên bản | Kiểm tra dependency tree và để starter/BOM quản lý dependency liên quan. |
| Không thấy `/v3/api-docs` | Dùng starter sai hoặc cấu hình endpoint bị tắt | Kiểm tra MVC/WebFlux, artifact API/UI và `springdoc.api-docs.enabled`. |
| Swagger UI không xuất hiện nhưng JSON có | Dùng starter `*-api` hoặc UI bị tắt | Chọn starter `*-ui` nếu cần giao diện. |
| Hai starter MVC và WebFlux cùng có mặt | Copy dependency từ nhiều ví dụ | Giữ starter tương ứng web stack thực tế. |
| SDK generator lỗi khi chuyển sang OpenAPI 3.1 | Consumer chưa hỗ trợ đầy đủ dialect/schema mới | Giữ OpenAPI 3.0 hoặc nâng cấp consumer có kiểm thử. |
| `info.version` đổi nhưng OpenAPI version không đổi | Nhầm API version với specification version | Kiểm tra `info.version` và trường `openapi` riêng biệt. |
| OpenAPI document đổi sau nâng springdoc | Swagger Core hoặc introspection thay đổi | Diff baseline và review schema/operation bị ảnh hưởng. |
| Maven/Gradle kéo nhiều phiên bản Swagger | Override dependency hoặc dùng starter legacy cùng starter mới | Xác định dependency path và bỏ xung đột có chủ đích. |
| Dự án Boot 2 không dùng được starter v2/v3 | Nhầm artifact starter mới với module legacy | Dùng dòng springdoc 1.x và tài liệu v1 cho dự án cũ. |

## 15. Checklist trước khi thêm hoặc nâng springdoc

Trước khi merge thay đổi dependency, xác nhận:

1. Đã biết chính xác Spring Boot minor version và Java version của ứng dụng.
2. Dòng springdoc được chọn nằm trong compatibility matrix của Boot.
3. MVC hay WebFlux được xác định đúng.
4. Đã chọn UI starter hay API-only starter theo nhu cầu.
5. Không có springdoc legacy và starter mới cùng xuất hiện.
6. Không override Swagger Core/Jackson/Spring module ngoài ý muốn.
7. OpenAPI Specification version được chọn theo khả năng consumer.
8. `info.version` không bị nhầm với trường `openapi`.
9. `/v3/api-docs`, YAML, Swagger UI và các group cần thiết hoạt động.
10. Contract diff không có breaking change ngoài kế hoạch.
11. Release notes của Spring Boot và springdoc đã được đọc.
12. Dependency tree được kiểm tra khi có dấu hiệu xung đột.

## 16. Nguyên tắc áp dụng

- Xác định Spring Boot trước, sau đó chọn springdoc theo compatibility matrix.
- Boot 4 dùng springdoc 3.x; Boot 3 dùng springdoc 2.x; Boot 1/2 thuộc dòng springdoc 1.x legacy.
- Chọn starter MVC/WebFlux và UI/API-only đúng với kiến trúc ứng dụng.
- Để Spring Boot BOM quản lý dependency nền tảng; khai báo springdoc version riêng.
- Tránh override Swagger Core, annotations hoặc Swagger UI nếu chưa kiểm tra dependency tree.
- Phân biệt phiên bản Spring Boot, springdoc, OpenAPI Specification và `info.version`.
- Chọn OpenAPI 3.0/3.1 theo khả năng của validator, SDK generator và consumer.
- Giữ OpenAPI dialect ổn định khi nâng dependency nếu chưa có yêu cầu đổi dialect.
- Lưu baseline và diff document sau mỗi lần nâng cấp.
- Đọc release notes và kiểm thử endpoint JSON/YAML trước khi phát hành.

Spring Boot quyết định nền tảng ứng dụng; springdoc quyết định thư viện tích hợp có tương thích với nền tảng đó hay không; OpenAPI Specification quyết định định dạng hợp đồng được xuất ra; còn `info.version` là phiên bản API do đội phát triển công bố. Khi chọn đúng từng trục, dùng starter phù hợp và kiểm tra document sau nâng cấp, ứng dụng có thể thay đổi nền tảng hoặc thư viện mà không vô tình làm hỏng công cụ và client đang tiêu thụ OpenAPI.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Compatibility Matrix và Getting Started](https://springdoc.org/)
- [Springdoc OpenAPI v2 – Spring Boot 3 Documentation](https://springdoc.org/v2/)
- [Springdoc OpenAPI v1 – Legacy Spring Boot Documentation](https://springdoc.org/v1/index.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI – Releases](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot 4.0 Migration Guide – renamed/deprecated starters](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [OpenAPI Specification 3.0.4](https://spec.openapis.org/oas/v3.0.4.html)
- [Spring Boot – Upgrading](https://docs.spring.io/spring-boot/reference/upgrading/index.html)
