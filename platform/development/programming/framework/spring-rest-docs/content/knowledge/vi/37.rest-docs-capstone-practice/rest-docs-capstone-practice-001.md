# Thiết lập dự án Spring MVC tạo tài liệu bằng MockMvc

## 1. Mục tiêu capstone

Trong bài thực hành tổng hợp này, bạn sẽ thiết lập một dự án Spring MVC có thể tự sinh tài liệu REST API bằng Spring REST Docs và MockMvc. Kết quả cuối là một quy trình có thể chạy lặp lại:

1. Ứng dụng Spring MVC cung cấp endpoint REST.
2. MockMvc gửi HTTP request đến endpoint trong test.
3. Test xác nhận status, headers và payload.
4. Spring REST Docs sinh snippet từ operation đã kiểm thử.
5. Asciidoctor ghép snippet thành tài liệu HTML.
6. Gradle điều phối test và build tài liệu trong CI.

Spring REST Docs giúp tài liệu phản ánh HTTP behavior đã được kiểm tra. Khi response hoặc hợp đồng thay đổi, documentation test có thể phát hiện descriptor không còn khớp; snippet mới được tạo từ lần chạy test hiện tại.

## 2. Kiến trúc và cấu trúc thư mục

Một dự án đơn module có thể tổ chức như sau:

~~~text
spring-rest-docs-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/com/example/catalog/
    │   │   ├── CatalogApplication.java
    │   │   └── ProductController.java
    │   └── resources/
    ├── test/
    │   ├── java/com/example/catalog/
    │   │   └── ProductDocumentationTest.java
    │   └── resources/
    │       └── org/springframework/restdocs/templates/
    │           └── asciidoctor/
    │               └── request-fields.snippet
    └── docs/
        └── asciidoc/
            └── api-guide.adoc
~~~

| Đường dẫn | Nội dung |
| --- | --- |
| src/main/java | Spring Boot application và REST controllers |
| src/test/java | MockMvc documentation tests và descriptors |
| src/test/resources | Template override chỉ dùng khi chạy test |
| build/generated-snippets | Snippet sinh ra sau documentation tests |
| src/docs/asciidoc | Tài liệu AsciiDoc viết thủ công và include snippet |
| build/docs/asciidoc | HTML được Asciidoctor tạo ra |

Không chỉnh sửa trực tiếp file trong build/generated-snippets; chúng là output có thể tái tạo từ test.

## 3. Khởi tạo Gradle project

Tạo settings.gradle:

~~~groovy
rootProject.name = 'spring-rest-docs-demo'
~~~

Ví dụ build.gradle dùng Spring Boot, dependency management và Asciidoctor Gradle plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.0'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.asciidoctor.jvm.convert' version '4.0.4'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

configurations {
    asciidoctorExt
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'

    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

tasks.named('test') {
    useJUnitPlatform()
    outputs.dir layout.buildDirectory.dir('generated-snippets')
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    configurations 'asciidoctorExt'
    inputs.dir layout.buildDirectory.dir('generated-snippets')
    attributes 'snippets': layout.buildDirectory.dir('generated-snippets').get().asFile
}
~~~

Phiên bản trong ví dụ là bộ phiên bản minh họa. Khi tạo dự án mới, chọn Spring Boot, Java và Asciidoctor plugin tương thích với môi trường hiện tại của nhóm; không nâng riêng một thành phần mà bỏ qua compatibility matrix của dự án.

spring-restdocs-mockmvc cung cấp tích hợp REST Docs cho MockMvc. spring-restdocs-asciidoctor cung cấp hỗ trợ Asciidoctor, bao gồm cách include snippet thuận tiện. Không cần thêm dependency production cho Spring REST Docs nếu ứng dụng chỉ dùng nó trong test.

## 4. Tạo Spring Boot application và endpoint

Application entry point:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Tạo controller nhỏ để thực hành:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    Product getProduct(@PathVariable String id) {
        return new Product(id, "Mechanical Keyboard",
                new BigDecimal("1299000"));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    Product createProduct(@RequestBody CreateProductRequest request) {
        return new Product("p-100", request.name(), request.price());
    }

    record CreateProductRequest(String name, BigDecimal price) {}

    record Product(String id, String name, BigDecimal price) {}
}
~~~

Đây là endpoint mẫu để thiết lập quy trình tài liệu. Trong ứng dụng thực tế, controller thường gọi service và repository; documentation test nên dùng test data ổn định, không phụ thuộc dịch vụ bên ngoài.

## 5. Cấu hình MockMvc và Spring REST Docs

Spring Boot có thể tự cấu hình MockMvc và REST Docs thông qua test annotations:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductDocumentationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

AutoConfigureMockMvc tạo MockMvc dựa trên Spring application context. AutoConfigureRestDocs đăng ký REST Docs integration và chỉ định nơi ghi snippet. Nếu dự án đã cấu hình REST Docs theo cách thủ công, dùng documentationConfiguration(...) với MockMvcBuilders thay cho việc cấu hình trùng lặp.

## 6. Viết documentation test cho GET endpoint

Test GET cần xác nhận status, media type và các field response:

~~~java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getProduct() throws Exception {
        mockMvc.perform(get("/api/products/{id}", "p-42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("p-42"))
                .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
                .andDo(document("products-get",
                        responseFields(
                                fieldWithPath("id").description("Mã sản phẩm"),
                                fieldWithPath("name").description("Tên sản phẩm"),
                                fieldWithPath("price").description("Giá sản phẩm"))));
    }
}
~~~

Đặt imports và class trong đúng package. Nếu dùng một test class cho nhiều operation, mỗi test cần identifier riêng như products-get và products-create.

## 7. Viết documentation test cho POST endpoint

POST test kiểm tra request fields và response fields:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void createProduct() throws Exception {
    mockMvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Desk Lamp",
                              "price": 450000
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("p-100"))
            .andDo(document("products-create",
                    requestFields(
                            fieldWithPath("name").description("Tên sản phẩm"),
                            fieldWithPath("price").description("Giá sản phẩm")),
                    responseFields(
                            fieldWithPath("id").description("Mã sản phẩm được tạo"),
                            fieldWithPath("name").description("Tên sản phẩm"),
                            fieldWithPath("price").description("Giá sản phẩm"))));
}
~~~

Trong class thực tế, thêm static imports cho post(...) và requestFields(...). Strict field descriptors giúp test thất bại nếu request/response xuất hiện field chưa được mô tả hoặc descriptor không còn khớp payload.

## 8. Sinh snippet và kiểm tra output

Sau khi documentation tests chạy, output có cấu trúc:

~~~text
build/generated-snippets/
├── products-get/
│   ├── curl-request.adoc
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
└── products-create/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
~~~

Các snippet mặc định có thể thay đổi theo cấu hình. Hãy kiểm tra thư mục output thực tế thay vì giả định mọi file trong ví dụ đều được sinh ra.

Chạy riêng test:

~~~bash
./gradlew clean test
~~~

Sau khi test thành công, mở build/generated-snippets/products-create/request-fields.adoc và xác nhận bảng có hai field name, price cùng mô tả đúng. Nếu file không có, kiểm tra identifier truyền cho document(...), output directory và test có thực thi operation hay không.

## 9. Biên soạn tài liệu AsciiDoc

Tạo file src/docs/asciidoc/api-guide.adoc:

~~~adoc
= Catalog REST API
:toc:
:sectnums:

== Giới thiệu

API minh họa quản lý sản phẩm trong catalog.

== Xem sản phẩm

=== Request

include::{snippets}/products-get/curl-request.adoc[]
include::{snippets}/products-get/http-request.adoc[]

=== Response

include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Tạo sản phẩm

=== Request

include::{snippets}/products-create/curl-request.adoc[]
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/request-fields.adoc[]

=== Response

include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]
~~~

Thuộc tính snippets được plugin Asciidoctor cung cấp qua cấu hình Gradle ở phần trước. Tên identifier trong include phải khớp tuyệt đối với identifier trong document(...).

## 10. Chạy build tài liệu

Chạy:

~~~bash
./gradlew asciidoctor
~~~

Task asciidoctor phụ thuộc test, vì vậy test tạo snippet trước khi Asciidoctor include chúng. HTML đầu ra thường nằm dưới:

~~~text
build/docs/asciidoc/
└── api-guide.html
~~~

Để kiểm tra toàn bộ quy trình từ đầu:

~~~bash
./gradlew clean asciidoctor
~~~

Nếu muốn tạo JAR chứa tài liệu, có thể thêm task copy hoặc cấu hình artifact riêng. Chỉ thêm bước đóng gói khi nhóm thực sự cần phân phối tài liệu cùng ứng dụng.

## 11. Tùy chỉnh template và preprocessors

Sau khi quy trình cơ bản hoạt động, có thể thêm template override trong:

~~~text
src/test/resources/org/springframework/restdocs/templates/asciidoctor/
~~~

Ví dụ request-fields.snippet để thay cách trình bày bảng request fields. Bắt đầu từ template mặc định của đúng phiên bản REST Docs, rồi bổ sung cột hoặc metadata cần thiết. Không tạo template tối giản làm mất trạng thái optional/ignored hoặc thông tin chuẩn mà template mặc định đang cung cấp.

Có thể pretty-print request/response và làm sạch dữ liệu nhạy cảm trước khi ghi snippet:

~~~java
mockMvc.perform(get("/api/products/{id}", "p-42"))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                preprocessRequest(prettyPrint(),
                        removeHeaders("Authorization", "Cookie")),
                preprocessResponse(prettyPrint(),
                        removeHeaders("Set-Cookie"))));
~~~

Đây là ví dụ áp dụng preprocessors tại operation; thêm static imports tương ứng từ OperationPreprocessors. Trong ứng dụng có xác thực, request vẫn gửi credential fixture để kiểm tra behavior; preprocessor chỉ loại chúng khỏi bản ghi tài liệu. Kiểm tra snippet sinh ra để chắc rằng token/session không bị ghi lại.

## 12. Tổ chức test và tài liệu khi dự án lớn hơn

~~~text
src/test/java/com/example/catalog/
├── products/
│   └── ProductDocumentationTest.java
├── categories/
│   └── CategoryDocumentationTest.java
└── common/
    ├── RestDocsConfig.java
    └── ApiDescriptors.java
~~~

Dùng helper cho phần thật sự dùng chung như header descriptors, preprocessors hoặc template format. Mỗi operation vẫn cần descriptor riêng cho payload và contract của nó.

Đặt identifier theo resource và hành động: products-get, products-create, categories-list. Identifier ổn định giúp AsciiDoc include dễ đọc và tránh snippet ghi đè nhau.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test pass nhưng không có snippet | Không gọi document(...) hoặc operation không chạy đến bước đó | Kiểm tra test và identifier |
| Strict fields test thất bại | Payload có field chưa mô tả hoặc descriptor sai path | Đối chiếu JSON thực tế và cập nhật descriptors |
| Asciidoctor báo thiếu include | Test chưa sinh snippet hoặc identifier sai | Chạy test trước và kiểm tra thư mục output |
| Snippet nằm sai thư mục | Output directory không thống nhất | Đồng bộ AutoConfigureRestDocs và Gradle |
| HTML không cập nhật | Task build không phụ thuộc test hoặc dùng output cũ | Khai báo dependency và chạy clean |
| Token/cookie xuất hiện trong tài liệu | Chưa preprocess header nhạy cảm | Loại bỏ hoặc thay thế giá trị trước khi ghi |
| Template override không có hiệu lực | Sai package, format ID hoặc tên snippet | Kiểm tra test classpath và template name |
| Test phụ thuộc dữ liệu bên ngoài | Dùng database/service không ổn định | Dùng fixture, mock hoặc test container phù hợp |

Khi xử lý lỗi, kiểm tra theo thứ tự: HTTP test, descriptor, snippet output, Asciidoctor include và Gradle task graph. Mỗi bước tạo đầu vào cho bước kế tiếp.

## 14. Bài tập capstone

Hoàn thiện tài liệu cho API catalog với các yêu cầu:

1. GET /api/products/{id}: mô tả path parameter, response fields và response headers.
2. POST /api/products: mô tả request fields, response fields, status 201 và content types.
3. GET /api/products: thêm query parameters page, size và sort.
4. Thêm một response lỗi 404 và mô tả payload lỗi.
5. Tạo một template override có thêm cột Example hoặc Constraints.
6. Preprocess Authorization/Cookie trước khi ghi snippet.
7. Include các snippet vào api-guide.adoc.
8. Chạy ./gradlew clean asciidoctor và kiểm tra HTML cuối.

**Tiêu chí hoàn thành:** documentation tests chạy ổn định; HTTP assertions xác nhận behavior; descriptors bao phủ payload/parameters/headers; snippets được sinh từ test hiện tại; Asciidoctor tạo HTML không thiếu include; không có credential hoặc dữ liệu thật trong tài liệu.

## 15. Checklist trước khi đưa vào CI

- [ ] Spring MVC application khởi động được trong test context.
- [ ] MockMvc và Spring REST Docs được cấu hình đúng output directory.
- [ ] Mỗi operation có identifier duy nhất.
- [ ] Test xác nhận status, media type và payload quan trọng.
- [ ] Request/response descriptors phản ánh đúng JSON thực tế.
- [ ] Template override nằm trong test classpath và đúng format ID.
- [ ] Header nhạy cảm được làm sạch trước khi ghi snippet.
- [ ] Gradle test chạy trước Asciidoctor.
- [ ] ./gradlew clean asciidoctor chạy thành công từ đầu.
- [ ] HTML artifact được kiểm tra và lưu lại trong CI.

**Ghi nhớ:** Một dự án Spring MVC dùng MockMvc và Spring REST Docs cần ba phần gắn kết: HTTP tests kiểm chứng behavior, descriptors mô tả hợp đồng, và Asciidoctor biên soạn snippet thành tài liệu. Khi Gradle điều phối test trước bước biên soạn, tài liệu có thể được tái tạo nhất quán trong máy phát triển và CI.
