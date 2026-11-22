# Xác nhận request thực sự gửi form parameter trong Spring REST Docs

## 1. Mục tiêu

Khi kiểm thử endpoint nhận `application/x-www-form-urlencoded`, việc controller đọc được tham số chưa đủ để kết luận client đã gửi đúng **form body**. Tham số trong Servlet API có thể đến từ query string hoặc body form. Một bài test có thể thêm trực tiếp giá trị vào parameter map, khiến controller vẫn nhận được dữ liệu dù body HTTP không chứa các cặp `name=value` như client thật gửi.

Trong module **SPRING_REST_DOCS**, tài liệu REST API được sinh từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Spring REST Docs tạo snippet cho request, response, payload, parameter và header; sau đó snippet được biên soạn thành Asciidoctor/Markdown và đưa vào build/CI. Nếu test chỉ tạo một Servlet parameter giả lập, bảng `form-parameters.adoc` có thể đúng tên trường nhưng ví dụ HTTP request không chứng minh form body đã được gửi.

Bài học này phân biệt query parameter trong URL, form parameter trong body và Servlet request parameter map; đồng thời hướng dẫn tạo form body thật trong MockMvc và xác nhận nội dung đã được ghi nhận.

## 2. Ba khái niệm không nên đánh đồng

### 2.1. Query parameter và form parameter

```http
POST /registrations?campaign=spring HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=mai%40example.com&plan=pro
```

| Dữ liệu | Vị trí | Ý nghĩa |
| --- | --- | --- |
| `campaign=spring` | Query string sau dấu `?` | Query parameter |
| `email=mai%40example.com` | HTTP body | Form parameter |
| `plan=pro` | HTTP body | Form parameter |

Chúng có thể cùng được đọc như request parameters trong Servlet API, nhưng tài liệu hóa cần phân loại theo **nguồn thực tế**: `queryParameters(...)` cho query string và `formParameters(...)` cho form body.

### 2.2. Form body

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&plan=pro
```

Body gồm các cặp tên/giá trị, phân tách bằng `&`. Mỗi tên và giá trị phải được form-encode: `@` thành `%40`, khoảng trắng thường thành `+`, dấu cộng thật thành `%2B` và dấu `&` bên trong giá trị thành `%26`.

### 2.3. Servlet parameter map

Controller Spring MVC đọc được tham số qua `@RequestParam`, nhưng `HttpServletRequest` chỉ cho biết tập request parameters đã được phân tích. Nếu test gọi `.param("email", "mai@example.com")`, nó thêm giá trị thẳng vào parameter map của `MockHttpServletRequest`; thao tác đó không có nghĩa body đã chứa `email=mai%40example.com`.

- Test dùng `.param(...)` hữu ích khi muốn kiểm thử controller nhận tham số.
- Khi mục tiêu là xác nhận **form body**, hãy tạo body URL-encoded thật.
- Kiểm tra cả request snippet và hành vi server; đừng chỉ nhìn thấy `@RequestParam` bind thành công rồi suy ra wire format đúng.

## 3. MockMvc: tạo form body đúng cách

### 3.1. Chỉ dùng `.param(...)` chưa chứng minh có body

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "mai@example.com")
        .param("plan", "pro"))
    .andExpect(status().isCreated());
```

Đoạn này thêm `email` và `plan` vào parameter map. `Content-Type` có thể hiện là URL-encoded, nhưng `.param(...)` tự nó không nối các cặp đó thành request body. Vì vậy test này không chứng minh client đã gửi body `email=mai%40example.com&plan=pro`.

### 3.2. Raw body bằng `.content(...)`

`MockHttpServletRequestBuilder.content(...)` đặt nội dung request body. Khi `Content-Type` là `application/x-www-form-urlencoded`, MockMvc phân tích nội dung và đưa các cặp form vào request parameter map:

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .content("email=mai%40example.com&plan=pro"))
    .andExpect(status().isCreated());
```

Với ký tự đặc biệt:

```java
String formBody = "email=mai%40example.com"
        + "&displayName=Mai+Nguy%E1%BB%85n"
        + "&note=C%2B%2B+%26+Java";

mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .content(formBody))
    .andExpect(status().isCreated());
```

Server nhận `email` là `mai@example.com`, `displayName` là `Mai Nguyễn` và `note` là `C++ & Java` sau khi giải mã. Không dùng encoder để mã hóa toàn bộ chuỗi body sau khi đã nối `&` và `=`; hãy encode từng tên/giá trị rồi mới ghép.

### 3.3. `.formField(...)` và `.formFields(...)`

Spring Framework **6.1.7 trở lên** cung cấp `formField(String, String...)` và `formFields(MultiValueMap<String, String>)` trên request builder. Các API này bổ sung giá trị vào form body **và** request parameter map:

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .formField("email", "mai@example.com")
        .formField("plan", "pro")
        .formField("topics", "java", "spring"))
    .andExpect(status().isCreated());
```

Với `MultiValueMap`:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("email", "mai@example.com");
form.add("plan", "pro");
form.add("topics", "java");
form.add("topics", "spring");

mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .formFields(form))
    .andExpect(status().isCreated());
```

`formField(...)` có từ Spring Framework 6.1.7. Nếu dự án dùng phiên bản cũ hơn, dùng `.content(...)` với body URL-encoded hoặc nâng dependency theo kế hoạch; đừng gọi API chưa có trong phiên bản compile.

### 3.4. Xác minh raw body và parameter map riêng biệt

```java
MvcResult result = mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .content("email=mai%40example.com&plan=pro"))
    .andExpect(status().isCreated())
    .andReturn();

MockHttpServletRequest request = result.getRequest();
assertThat(request.getContentAsString())
    .isEqualTo("email=mai%40example.com&plan=pro");
assertThat(request.getContentType())
    .startsWith(MediaType.APPLICATION_FORM_URLENCODED_VALUE);
assertThat(request.getParameter("email")).isEqualTo("mai@example.com");
assertThat(request.getParameter("plan")).isEqualTo("pro");
```

Đoạn assertion kiểm tra hai việc riêng: raw content có các cặp form URL-encoded, và request parameter map đã parse ra giá trị mong đợi. Nếu chỉ kiểm tra `getParameter(...)`, ta mới chứng minh được ứng dụng nhìn thấy tham số, chưa chứng minh nguồn dữ liệu là body.

## 4. Tạo ví dụ REST Docs phản ánh body thật

Controller minh họa:

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {
    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String email,
            @RequestParam String plan) {
        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("pro")) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Controller được rút gọn cho ví dụ. Trong ứng dụng thực tế, dùng validation phù hợp với nghiệp vụ; `email.contains("@")` không phải bộ kiểm tra email đầy đủ.

### 4.1. Test ghi snippet từ raw form body

Dependency Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Test MockMvc:

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormWireDocumentationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsUrlEncodedBody() throws Exception {
        String formBody = "email=mai%40example.com&plan=pro";
        MvcResult result = mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .accept(MediaType.APPLICATION_JSON)
                .content(formBody))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-form-wire",
                formParameters(
                    parameterWithName("email")
                        .description("Email đăng ký; gửi trong form body"),
                    parameterWithName("plan")
                        .description("Gói đăng ký; basic hoặc pro")
                )
            ))
            .andReturn();

        MockHttpServletRequest request = result.getRequest();
        assertThat(request.getContentAsString()).isEqualTo(formBody);
        assertThat(request.getParameter("email")).isEqualTo("mai@example.com");
        assertThat(request.getParameter("plan")).isEqualTo("pro");
    }
}
```

Test này cung cấp body đã URL-encode bằng `.content(formBody)`, dùng `formParameters(...)` để sinh bảng tên field, rồi xác nhận raw body và giá trị đã parse. Ví dụ giả định dự án có AssertJ qua Spring Boot Test và controller không có dependency khác. Nếu ứng dụng có Security/CSRF, bổ sung cấu hình test tương ứng.

Snippet có identifier `registrations/create-form-wire`; thư mục output thường chứa:

```text
build/generated-snippets/
└── registrations/
    └── create-form-wire/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

`form-parameters.adoc` mô tả hợp đồng tên trường. `http-request.adoc` cho thấy request cụ thể mà Spring REST Docs ghi nhận. Hãy xem cả hai khi rà soát tài liệu.

## 5. Query parameter và form body trong cùng request

```java
mockMvc.perform(post("/registrations?campaign=spring")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .content("email=mai%40example.com&plan=pro"))
    .andExpect(status().isCreated())
    .andDo(document("registrations/create-form-with-campaign",
        queryParameters(
            parameterWithName("campaign")
                .description("Nguồn chiến dịch trong query string")
        ),
        formParameters(
            parameterWithName("email")
                .description("Email đăng ký trong form body"),
            parameterWithName("plan")
                .description("Gói đăng ký trong form body")
        )
    ));
```

Ví dụ cần static import `queryParameters` từ `RequestDocumentation`. URL query thể hiện `campaign`; body raw thể hiện `email` và `plan`. Tránh dùng `.param(...)` cho cả hai nhóm vì cách đó làm mất sự phân biệt nguồn trong test setup. Nếu query và form có cùng tên, Servlet API có thể tổng hợp tham số; tốt nhất tránh thiết kế trùng tên giữa hai nguồn nếu không thực sự cần.

## 6. WebTestClient và REST Assured

### 6.1. WebTestClient

```java
webTestClient.post()
    .uri("/registrations")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData("email", "mai@example.com")
        .with("plan", "pro"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-form",
        formParameters(
            parameterWithName("email").description("Email đăng ký"),
            parameterWithName("plan").description("Gói basic hoặc pro")
        )
    ));
```

`BodyInserters.fromFormData(...)` tạo body form. Trong WebFlux, handler có thể đọc form qua `ServerWebExchange.getFormData()` hoặc binding phù hợp; cần kiểm thử đúng loại handler đang dùng.

### 6.2. REST Assured

```java
given(specification)
    .filter(document("registrations/rest-assured-form",
        formParameters(
            parameterWithName("email").description("Email đăng ký"),
            parameterWithName("plan").description("Gói basic hoặc pro")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .formParam("plan", "pro")
    .when()
    .post("/registrations")
    .then()
    .statusCode(201);
```

`.formParam(...)` là API gửi dữ liệu form của REST Assured. Dùng `http-request.adoc`/curl snippet để rà soát request được ghi nhận và kiểm tra với HTTP server trong môi trường tích hợp nếu cần xác minh byte trên đường truyền.

## 7. Các assertion hữu ích khi xác nhận form

| Nội dung | Cách kiểm tra | Điều được chứng minh |
| --- | --- | --- |
| Media type | `request.getContentType()` | Request khai báo URL-encoded |
| Body raw | `request.getContentAsString()` | Body có dữ liệu form đã encode |
| Form parsing | `request.getParameter("email")` | Servlet parameter map nhận giá trị đã parse |
| Binding controller | Response/status hoặc service mock | Controller xử lý tham số đúng |
| Tài liệu | `formParameters(...)` và `http-request.adoc` | Snippet mô tả tên field và ví dụ request |
| Encoding | Fixture có `+`, `%2B`, `%26`, Unicode | Dữ liệu đặc biệt được giải mã như mong đợi |

Ví dụ kiểm tra encoding:

```java
String body = "displayName=Mai+Nguy%E1%BB%85n&note=C%2B%2B+%26+Java";
MvcResult result = mockMvc.perform(post("/preferences")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding("UTF-8")
        .content(body))
    .andReturn();

MockHttpServletRequest request = result.getRequest();
assertThat(request.getContentAsString()).isEqualTo(body);
assertThat(request.getParameter("displayName")).isEqualTo("Mai Nguyễn");
assertThat(request.getParameter("note")).isEqualTo("C++ & Java");
```

Đường dẫn `/preferences` là endpoint minh họa và cần tồn tại trong test context thực tế. Test cần bổ sung assertion response phù hợp với ứng dụng.

## 8. Đưa snippet vào tài liệu và CI

Ví dụ trang Asciidoctor:

```adoc
= Registrations API

== Tạo đăng ký bằng form URL-encoded

Request phải gửi Content-Type: application/x-www-form-urlencoded.

=== Form parameters
include::{snippets}/registrations/create-form-wire/form-parameters.adoc[]

=== HTTP request thực tế trong test
include::{snippets}/registrations/create-form-wire/http-request.adoc[]

=== HTTP response
include::{snippets}/registrations/create-form-wire/http-response.adoc[]
```

Thuộc tính `snippets` phải trỏ đến thư mục gốc chứa snippet, ví dụ `build/generated-snippets`. `include::...[]` là cú pháp Asciidoctor, không phải cú pháp nhúng tự động của Markdown renderer thông thường. Trang Markdown có thể liên kết tới HTML đã render hoặc dùng bước chuyển đổi rõ ràng trong pipeline.

Với Gradle Groovy DSL và plugin Asciidoctor đã được cấu hình:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI có thể chạy:

```bash
./gradlew test asciidoctor
```

Đảm bảo test tạo snippet trước khi Asciidoctor chạy. Với build cần tính tái lập, dùng workspace sạch hoặc xóa output build theo quy trình chuẩn để snippet cũ không làm tài liệu trông như vừa được xác minh.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Controller đọc được tham số nhưng body rỗng | Test chỉ dùng `.param(...)` | Dùng `.content(...)` hoặc `.formField(...)` từ Spring Framework 6.1.7+ |
| `form-parameters.adoc` có bảng nhưng request mẫu không có form body | Parameter map được điền riêng khỏi raw content | Kiểm tra `http-request.adoc`, raw body và `Content-Type` |
| Giá trị `+` bị chuyển thành khoảng trắng | Form encoding coi dấu cộng là space | Encode dấu cộng thực thành `%2B` |
| Query bị mô tả nhầm thành form parameter | Test dùng `.param(...)` cho cả hai nguồn | Dùng URL query riêng và body raw riêng; document query/form phù hợp |
| MockMvc không parse body form | Thiếu hoặc sai `Content-Type` | Đặt `application/x-www-form-urlencoded` trước khi cung cấp `.content(...)` |
| `formField(...)` không compile | Spring Framework thấp hơn 6.1.7 | Dùng raw `.content(...)` hoặc nâng dependency có kiểm soát |
| Test pass nhưng request client thật khác | Chỉ kiểm tra mock parameter map | Dùng HTTP client/REST Assured và kiểm thử tích hợp khi cần |
| Asciidoctor không tìm thấy snippet | Identifier hoặc đường dẫn include sai | So khớp `document(...)`, output directory và `include` |

## 10. Bài tập thực hành

Tạo endpoint `POST /subscriptions` nhận form gồm `email` bắt buộc, `topics` lặp tên từ 1 đến 3 lần và `note` tùy chọn có thể chứa tiếng Việt/dấu cộng.

1. Viết một test chỉ dùng `.param(...)`, quan sát parameter map và body raw.
2. Viết test dùng `.content("email=...&topics=...")` với `Content-Type: application/x-www-form-urlencoded`; xác nhận raw body và giá trị đã parse.
3. Nếu dự án dùng Spring Framework 6.1.7+, viết lại bằng `.formField(...)` hoặc `.formFields(...)`.
4. Viết thêm request có query `source=web` để phân biệt `queryParameters(...)` với `formParameters(...)`.
5. Dùng REST Assured hoặc WebTestClient gửi form tương đương; sinh `http-request.adoc` và `form-parameters.adoc`.
6. Nhúng snippet vào Asciidoctor và cho CI chạy test trước bước render tài liệu.

**Tiêu chí đạt:** bài test chứng minh body thật có dữ liệu URL-encoded, các giá trị được parse đúng, query và form được phân loại đúng và snippet Spring REST Docs phản ánh request mà client cần gửi.

## Tài liệu tham khảo

- [Spring Framework 6.1 MockHttpServletRequestBuilder API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/web/servlet/request/MockHttpServletRequestBuilder.html) — API content, param, formField và formFields.
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)

