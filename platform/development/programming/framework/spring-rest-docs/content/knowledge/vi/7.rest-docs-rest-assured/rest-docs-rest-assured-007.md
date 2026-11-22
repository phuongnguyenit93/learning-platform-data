# REST Assured 5 và yêu cầu tương thích với Spring REST Docs

## 1. Vì sao cần quan tâm đến tương thích phiên bản?

**Spring REST Docs** tạo tài liệu REST API từ các bài kiểm thử HTTP đã chạy. Có thể sử dụng Spring MVC Test/MockMvc, WebTestClient hoặc **REST Assured 5** làm công cụ gọi và kiểm chứng API. Khi chọn REST Assured, dự án cần đồng bộ phiên bản giữa Java, Spring Framework/Spring Boot, Spring REST Docs và các artifact REST Assured.

Một dependency resolve thành công chưa chắc chứng minh các thư viện tương thích lúc chạy. Một số lỗi chỉ xuất hiện khi test khởi tạo filter, serialize JSON, xử lý response hoặc tạo snippet. Vì vậy, nên chọn đúng các major version được hỗ trợ, quản lý phiên bản nhất quán và chạy một test tài liệu hóa tối thiểu trước khi mở rộng sang toàn bộ API.

Với Spring REST Docs **3.0.6**, tài liệu yêu cầu tối thiểu **Java 17**, **Spring Framework 6** và riêng module `spring-restdocs-restassured` yêu cầu **REST Assured 5.2**. Điều đó có nghĩa REST Assured 5.2 là mốc tối thiểu cho tích hợp này, không phải yêu cầu phải dùng chính xác phiên bản 5.2. Tài liệu chính thức xác định tích hợp hiện tại dành cho REST Assured 5. <https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/>.

## 2. Ma trận tương thích cần kiểm tra

| Thành phần | Mức cần đáp ứng khi dùng Spring REST Docs 3.0.6 | Lưu ý |
| --- | --- | --- |
| JDK | Java 17 trở lên | Kiểm tra cả JDK chạy Gradle/Maven và toolchain biên dịch/test. |
| Spring Framework | 6.x | Spring Boot 3.x thường quản lý Spring Framework 6; vẫn phải chọn đúng phiên bản Boot và dependency set của dự án. |
| Spring REST Docs | 3.0.x (ví dụ 3.0.6) | Các module `spring-restdocs-*` nên dùng cùng một phiên bản. |
| REST Assured | 5.2 trở lên trong nhánh 5.x | Module `spring-restdocs-restassured` 3.0.x được tài liệu mô tả cho REST Assured 5. |
| JUnit | JUnit Jupiter hoặc JUnit 4 theo cách tích hợp tương ứng | Ví dụ ở bài này dùng JUnit 5 với `RestDocumentationExtension`. |
| Build | Gradle hoặc Maven có dependency management rõ ràng | Test phải chạy trước bước biên soạn snippet. |

Đây là ma trận định hướng cho tổ hợp REST Docs 3.0.x và REST Assured 5, không phải cam kết rằng mọi patch version của Spring Boot, Jackson, Groovy hoặc HTTP client đều có thể ghép tùy ý. Dùng BOM/parent của dự án và kiểm tra dependency tree khi có xung đột.

### Phân biệt REST Assured 5, 6 và 7

- **REST Assured 5.x:** là dòng mà tích hợp `spring-restdocs-restassured` của Spring REST Docs 3.0.x yêu cầu; cần dùng tối thiểu 5.2 theo tài liệu Spring REST Docs.
- **REST Assured 6.x:** là major version riêng. Tài liệu REST Assured 6 nêu baseline Java 17 và thay đổi nền tảng Groovy lên 5.x; các thay đổi major có thể ảnh hưởng đến dependency và tích hợp. Không thay artifact 5.x bằng 6.x rồi giả định module Spring REST Docs 3.0.x vẫn được hỗ trợ chỉ vì compile được.
- **REST Assured 7.x:** cũng là major version khác, có thay đổi module/path engine và cần kiểm tra hướng dẫn tương ứng. Không lấy ví dụ cấu hình REST Assured 7 để áp dụng nguyên xi vào dự án được yêu cầu dùng REST Assured 5.

Khi nâng REST Assured qua major version, hãy kiểm tra lại tài liệu tương thích của cả hai dự án và chạy test tài liệu hóa thật. Ghi chú phát hành REST Assured 6.0 có đề cập Java 17+, Groovy 5.x và thay đổi hỗ trợ Spring 7; đây là dấu hiệu cho thấy chuyển major là một thay đổi nền tảng, không chỉ sửa số phiên bản. <https://rest-assured.io/release-notes/6-0/>.

## 3. Các artifact cần có và vai trò của chúng

Với dự án Spring Boot dùng REST Assured để gửi HTTP đến server đang chạy, thường cần các artifact test sau:

| Artifact | Group ID | Vai trò |
| --- | --- | --- |
| `rest-assured` | `io.rest-assured` | DSL `given()`, `when()`, `then()`, HTTP request và assertion. |
| `spring-restdocs-restassured` | `org.springframework.restdocs` | Filter tích hợp REST Assured với Spring REST Docs để sinh snippet. |
| `spring-boot-starter-test` | `org.springframework.boot` | Hạ tầng kiểm thử Spring Boot, JUnit Jupiter và các tiện ích test thông dụng. |
| `rest-assured-bom` (khi cần) | `io.rest-assured` | Quản lý đồng bộ version của các module REST Assured. |

Chỉ thêm module thực sự cần dùng. Chẳng hạn, bài test gọi JSON bằng GPath có thể cần module JSON path tương ứng với nhánh REST Assured đang dùng; module riêng cho MockMvc hoặc WebTestClient không cần thiết nếu bài test chỉ dùng REST Assured gọi HTTP server. REST Assured 5 có các artifact cùng group `io.rest-assured`; các module của REST Assured phải theo cùng một phiên bản. Tài liệu REST Assured mô tả nguyên tắc này tại <https://rest-assured.io/docs/modules/>.

## 4. Quản lý dependency bằng Gradle

### 4.1. Khai báo dependency

Ví dụ sau dùng **REST Assured 5.5.7** làm phiên bản minh họa thuộc nhánh 5.x. Khi áp dụng, xác nhận phiên bản patch được phép dùng trong repository của tổ chức và đồng bộ mọi artifact REST Assured khác về cùng phiên bản. Spring REST Docs trong ví dụ dùng 3.0.6:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    testImplementation 'io.rest-assured:rest-assured:5.5.7'
    testImplementation 'org.springframework.restdocs:spring-restdocs-restassured:3.0.6'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`testImplementation` giữ các thư viện trên test classpath; không đưa chúng vào runtime classpath của ứng dụng chỉ để tạo tài liệu. Nếu dự án quản lý dependency bằng Spring Boot plugin/BOM, ưu tiên cách quản lý tập trung thay vì ghi version rải rác trong từng dependency.

### 4.2. Quản lý bằng REST Assured BOM

Nếu có nhiều module REST Assured, import `rest-assured-bom` để đặt cùng version cho toàn bộ module:

```groovy
dependencies {
    testImplementation platform('io.rest-assured:rest-assured-bom:5.5.7')

    testImplementation 'io.rest-assured:rest-assured'
    testImplementation 'org.springframework.restdocs:spring-restdocs-restassured:3.0.6'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Trong ví dụ này BOM chỉ quản lý artifact `io.rest-assured:*`; nó không quản lý version Spring REST Docs. Vì vậy, `spring-restdocs-restassured` vẫn được đặt theo version tương ứng của Spring REST Docs.

Không khai báo đồng thời những version xung đột cho `rest-assured`, `json-path`, `xml-path` hoặc module khác của REST Assured. Nếu một module trực tiếp khai báo 5.5.7 còn module khác kéo về một patch/major khác, hãy đọc dependency report và loại trừ nguồn xung đột có chủ đích.

## 5. Quản lý dependency bằng Maven

### 5.1. Khai báo trực tiếp

Trong dự án đã quản lý Spring Boot dependency bằng parent/BOM, có thể đặt các dependency kiểm thử trong `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.rest-assured</groupId>
        <artifactId>rest-assured</artifactId>
        <version>5.5.7</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-restassured</artifactId>
        <version>3.0.6</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Phần này giả định parent/BOM đã quản lý phiên bản `spring-boot-starter-test`. Nếu không có dependency management, cần khai báo phiên bản cho tất cả artifact. Hạn chế dùng phiên bản Spring Framework riêng lẻ bên cạnh BOM của Spring Boot vì điều đó có thể tạo tổ hợp Spring không đồng bộ.

### 5.2. Import BOM của REST Assured

Nếu dùng thêm nhiều artifact REST Assured, có thể khai báo BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.rest-assured</groupId>
            <artifactId>rest-assured-bom</artifactId>
            <version>5.5.7</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.rest-assured</groupId>
        <artifactId>rest-assured</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-restassured</artifactId>
        <version>3.0.6</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Một BOM có thể chỉ quản lý những artifact thuộc cùng hệ thư viện. BOM REST Assured không thay thế Spring Boot BOM hoặc Spring REST Docs dependency management. Nếu dự án import nhiều BOM, kiểm tra thứ tự và quy tắc precedence của Maven để biết version cuối cùng được chọn.

## 6. Ví dụ kiểm thử REST Assured 5 cùng Spring REST Docs

Giả sử ứng dụng có endpoint HTTP `GET /api/orders/{id}` và test fixture đảm bảo đơn hàng `1001` tồn tại. API trả:

```json
{
  "id": 1001,
  "status": "CONFIRMED"
}
```

Ví dụ lớp JUnit 5 dưới đây sử dụng Spring Boot 3.x, Spring REST Docs 3.0.x và REST Assured 5.x:

```java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.http.ContentType;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.documentationConfiguration;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    @LocalServerPort
    private int port;

    private RequestSpecification specification;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.specification = new RequestSpecBuilder()
                .setBaseUri("http://localhost")
                .setPort(this.port)
                .setBasePath("/api")
                .addFilter(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetOrder() {
        given(this.specification)
                .accept(ContentType.JSON)
                .pathParam("id", 1001)
                .filter(document("orders-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã đơn hàng")),
                        responseFields(
                                fieldWithPath("id").description("Mã đơn hàng"),
                                fieldWithPath("status").description("Trạng thái đơn hàng"))))
        .when()
                .get("/orders/{id}")
        .then()
                .statusCode(200)
                .contentType(ContentType.JSON)
                .body("id", equalTo(1001))
                .body("status", equalTo("CONFIRMED"));
    }
}
```

`RANDOM_PORT` khởi động server HTTP nhúng; `@LocalServerPort` cấp cổng test thực. `documentationConfiguration(...)` được gắn vào `RequestSpecification`, còn `document("orders-get", ...)` được gắn ở request cần sinh tài liệu. Endpoint `/api/orders/{id}` và fixture phải tồn tại trong ứng dụng đang kiểm thử; tên trường JSON phải đúng response thực tế. Ví dụ này là mẫu tích hợp cho API hiện hữu, không tự tạo controller hoặc dữ liệu đơn hàng.

## 7. Những điểm khác biệt khi dùng REST Assured 5

Khi chọn REST Assured 5 cho Spring REST Docs, cần đặc biệt chú ý:

### 7.1. Dùng đúng group ID và artifact

Các bản REST Assured mới dùng group ID `io.rest-assured`. Không trộn artifact cũ `com.jayway.restassured` với artifact mới trong cùng một test classpath. Các ví dụ dựa trên REST Assured 5 nên dùng package `io.restassured.*` và `io.restassured.module.*` tương ứng.

### 7.2. Các module REST Assured phải đồng bộ version

Nếu test cần JSON path, XML path hoặc một HTTP client mở rộng, kiểm tra các module cùng phiên bản REST Assured 5. Dùng BOM giúp tránh lỗi lệch version giữa `rest-assured` và module phụ trợ. Không thêm `rest-assured-all` hoặc module path chỉ vì nghĩ rằng mọi dự án đều cần; hãy thêm theo chức năng test thực sự sử dụng.

### 7.3. Giữ Spring REST Docs và Spring Framework đúng dòng

Spring REST Docs 3.0.x được xây dựng cho Spring Framework 6 và yêu cầu Java 17. Dự án Spring Boot 3.x thường là nền tảng phù hợp, nhưng vẫn cần để BOM của Boot quản lý các thư viện Spring nhất quán. Không kéo một module Spring Framework 7 vào classpath Spring Boot 3 chỉ để thử tương thích với một bản REST Assured khác.

### 7.4. Không suy luận tương thích chỉ từ việc biên dịch được

Một số khác biệt nằm ở runtime hoặc ở filter khi Spring REST Docs xử lý trao đổi HTTP. Cần chạy test tài liệu hóa để xác minh các lớp sau cùng hoạt động:

- JUnit extension cung cấp được `RestDocumentationContextProvider`.
- `RequestSpecification` chấp nhận filter `documentationConfiguration(...)`.
- `document(...)` quan sát được request và response.
- Descriptor cho path/query parameter, header và payload kiểm tra đúng dữ liệu.
- Build tạo snippet và tác vụ Asciidoctor đọc đúng thư mục kết quả.

## 8. Kiểm tra dependency và chẩn đoán lỗi tương thích

Các lệnh sau giúp xác minh dependency đã resolve. Chạy tại thư mục dự án:

```bash
# Gradle: xem các dependency kiểm thử liên quan
./gradlew dependencies --configuration testRuntimeClasspath

# Gradle: xem riêng REST Assured và Spring REST Docs
./gradlew dependencyInsight --dependency rest-assured --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-restdocs-restassured --configuration testRuntimeClasspath

# Maven: xem cây dependency liên quan
mvn dependency:tree -Dincludes=io.rest-assured,org.springframework.restdocs,org.springframework
```

Trên Windows có thể dùng `gradlew.bat`. Đọc kết quả để xác nhận:

1. Chỉ resolve một phiên bản REST Assured 5 nhất quán cho các module `io.rest-assured` đang dùng.
2. `spring-restdocs-restassured` thuộc cùng dòng Spring REST Docs với những module REST Docs khác trong dự án.
3. Spring Framework được quản lý về dòng 6 khi dùng REST Docs 3.0.x.
4. JUnit Jupiter và test engine hiện diện nếu test dùng `@ExtendWith(RestDocumentationExtension.class)`.
5. Không có dependency cũ `com.jayway.restassured` lẫn trong classpath ngoài chủ ý chuyển đổi.

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `RestAssuredRestDocumentation` | Thiếu `spring-restdocs-restassured` hoặc dùng sai version/package. | Kiểm tra artifact `org.springframework.restdocs:spring-restdocs-restassured` trong test runtime. |
| `NoSuchMethodError` hoặc `ClassNotFoundException` | Dependency transitive bị lệch hoặc trộn major version. | Xem dependency tree, đồng bộ REST Assured modules bằng BOM và tránh trộn thư viện cũ. |
| REST Docs báo không tương thích REST Assured | Dùng REST Assured dưới 5.2 hoặc nhảy sang major 6/7 không nằm trong tổ hợp được tài liệu hóa cho module. | Dùng REST Assured 5.2+ trong dòng 5.x đối với tích hợp REST Docs 3.0.x. |
| Lỗi class version/unsupported class file | JDK dùng để chạy test thấp hơn baseline của Spring REST Docs. | Chuyển Gradle/Maven toolchain và JVM chạy test sang Java 17 trở lên. |
| Spring `NoSuchMethodError` | Trộn Spring Framework 5/7 vào dự án đang dùng REST Docs 3.0.x. | Để Spring Boot BOM quản lý phiên bản Spring Framework 6 đồng bộ. |
| Test chạy nhưng không thấy snippet | Filter REST Docs chưa gắn hoặc request không gọi `document(...)`. | Kiểm tra `documentationConfiguration(...)`, `.filter(document(...))` và output directory. |
| Test chạy nhưng descriptor thất bại | JSON/header/path parameter thực tế không khớp tài liệu. | Kiểm tra response và điều chỉnh API hoặc descriptor theo hợp đồng đã thống nhất. |

Lỗi resolve dependency và lỗi API test là hai việc khác nhau. Trước hết kiểm tra classpath và version; khi dependency nhất quán, chạy một endpoint test tối thiểu rồi mới mở rộng mô tả nhiều payload và header.

## 9. Build và CI: kiểm thử trước khi biên soạn tài liệu

Spring REST Docs sinh snippet trong lúc test chạy. Vì vậy, thứ tự build phải đảm bảo test thành công trước khi Asciidoctor biên soạn tài liệu. Ví dụ cấu hình Gradle rút gọn:

```groovy
plugins {
    id 'org.asciidoctor.jvm.convert' version '3.3.2'
}

configurations {
    asciidoctorExt
}

ext {
    snippetsDir = file('build/generated-snippets')
}

dependencies {
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor:3.0.6'
}

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    dependsOn tasks.named('test')
}
```

Đây là phần cấu hình bổ sung cho plugin và dependency Asciidoctor; nó không thay các dependency REST Assured/Spring REST Docs trong mục 4. File `.adoc` có thể nhúng snippet bằng:

```asciidoc
= Orders API

== Lấy đơn hàng

=== Request
include::{snippets}/orders-get/http-request.adoc[]

=== Path parameters
include::{snippets}/orders-get/path-parameters.adoc[]

=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
```

Trong CI, pipeline nên dừng nếu test tài liệu hóa thất bại. Không xuất bản snippet còn sót lại từ build cũ như thể nó thuộc lần chạy hiện tại. Nếu dùng Markdown, cần cấu hình quy trình xử lý snippet phù hợp vì các snippet mặc định thường ở định dạng AsciiDoc.

## 10. Checklist chọn và xác minh tổ hợp tương thích

- [ ] JDK chạy build và test là Java 17 trở lên cho Spring REST Docs 3.0.x.
- [ ] Spring Framework thuộc dòng 6 khi dùng Spring REST Docs 3.0.x.
- [ ] Đã thêm `spring-restdocs-restassured` ở test scope với version Spring REST Docs thống nhất.
- [ ] REST Assured là dòng 5.x và không thấp hơn mức 5.2 mà module tích hợp yêu cầu.
- [ ] Các artifact `io.rest-assured` đang dùng có cùng version hoặc do `rest-assured-bom` quản lý.
- [ ] Không trộn group ID cũ `com.jayway.restassured` với `io.rest-assured`.
- [ ] Đã chạy test JUnit tài liệu hóa thật và xác nhận snippet được tạo.
- [ ] Assertion và descriptor cho request/response đều pass trước khi biên soạn tài liệu.
- [ ] Build/CI chạy test trước Asciidoctor và chỉ phát hành tài liệu từ build thành công.

REST Assured 5 là dòng tích hợp mà Spring REST Docs 3.0.x mô tả hỗ trợ. Khi giữ Java 17+, Spring Framework 6 và REST Assured 5.2+ trong một tập dependency được quản lý thống nhất, dự án có nền tảng phù hợp để sinh snippet từ HTTP test và biên soạn tài liệu API có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring REST Docs – Requirements và Build configuration](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [REST Assured – Which module do I need, Keep the versions in line và Spring Boot](https://rest-assured.io/docs/modules/)
- [REST Assured – Release notes 5.2.0](https://rest-assured.io/release-notes/5-2/)
- [REST Assured – Release notes 6.0.0](https://rest-assured.io/release-notes/6-0/)
