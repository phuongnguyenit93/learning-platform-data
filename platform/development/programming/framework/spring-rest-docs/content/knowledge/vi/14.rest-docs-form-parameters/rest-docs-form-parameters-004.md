# Biểu diễn giá trị nhiều phần trong form với Spring REST Docs

## 1. Bối cảnh và mục tiêu

Trong chương **Form parameters** của `SPRING_REST_DOCS`, một biểu mẫu HTTP không nhất thiết chỉ gồm các trường mang một giá trị. Người dùng có thể chọn nhiều nhãn, nhiều quyền, nhiều mục quan tâm hoặc gửi nhiều tệp đính kèm. Khi thiết kế REST API, cách biểu diễn **nhiều giá trị** quyết định cách máy chủ phân tích request, cách kiểm thử, và cách Spring REST Docs tạo tài liệu.

Cụm “giá trị nhiều phần trong form” thường dễ gây nhầm giữa hai khái niệm:

1. **Một form parameter có nhiều giá trị (multi-value parameter):** trong body `application/x-www-form-urlencoded`, cùng một **tên trường** được gửi lặp lại, chẳng hạn `topics=java&topics=spring`.
2. **Request multipart:** trong body `multipart/form-data`, dữ liệu được chia thành nhiều **part** độc lập, mỗi part có header và nội dung riêng; phù hợp với tệp và dữ liệu kết hợp. Nhiều part cũng có thể có cùng tên.

Hai trường hợp đều chứa “nhiều”, nhưng khác cấu trúc HTTP và cách tài liệu hóa. Với Spring REST Docs, form URL-encoded dùng `formParameters(...)`; multipart dùng `requestParts(...)`, kết hợp `requestPartFields(...)` nếu một part chứa JSON.

Mục tiêu của bài là tạo tài liệu REST API **có thể kiểm chứng từ test HTTP** (MockMvc, WebTestClient hoặc REST Assured): kiểm tra request/response, payload, tham số và header; sinh snippet; nhúng vào Asciidoctor/Markdown và buộc bước sinh tài liệu đi sau kiểm thử trong CI.

## 2. Một tên form field có nhiều giá trị

### 2.1. Mô hình trên wire

Giả sử API lưu sở thích của người dùng. Một người có thể chọn đồng thời ba chủ đề:

```http
POST /preferences HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&topics=java&topics=spring&topics=rest-docs
```

Ở đây có **hai tên parameter**: `email` và `topics`. Tuy nhiên, `topics` xuất hiện **ba lần**, mang ba giá trị độc lập. Hình dung dưới dạng map nhiều giá trị:

```text
email  -> ["mai@example.com"]
topics -> ["java", "spring", "rest-docs"]
```

Kiểu dữ liệu tương ứng trong Spring là `MultiValueMap<String, String>`, thay vì `Map<String, String>` chỉ lưu một giá trị cho mỗi tên.

Các trường hợp thường gặp:

| Nhu cầu | Body form URL-encoded | Ghi chú |
| --- | --- | --- |
| Chỉ chọn một chủ đề | `topics=java` | Một tên, một giá trị |
| Chọn ba chủ đề | `topics=java&topics=spring&topics=rest-docs` | Một tên, ba giá trị |
| Không chọn chủ đề nào | Không có `topics` | Trường vắng mặt |
| Gửi trường trống | `topics=` | Có tên nhưng giá trị rỗng; không đồng nghĩa với vắng mặt |
| Lặp lại một giá trị | `topics=java&topics=java` | Hai giá trị trùng nhau, server phải tự quyết định cách xử lý |

Các giá trị trên wire vẫn là chuỗi. Java/Spring có thể chuyển chúng thành `List<String>`, mảng hoặc tập hợp, nhưng **không có một schema mảng JSON mặc định** được nhúng trong URL-encoded form.

### 2.2. Vì sao không tự nối chuỗi bằng dấu phẩy?

So sánh:

```text
# Hai giá trị riêng biệt
topics=java&topics=spring

# Một giá trị duy nhất chứa dấu phẩy
topics=java%2Cspring
```

Trong trường hợp thứ hai, dữ liệu trên wire là một giá trị `java,spring`. Một số cơ chế binding của Spring có thể tách chuỗi theo dấu phẩy khi chuyển sang kiểu collection, tùy converter và cấu hình. Nhưng đó là **quy tắc chuyển kiểu của server**, không biến hai dạng HTTP trên thành một hợp đồng phổ quát. Khi tài liệu quy định “lặp lại tên `topics`”, client nên gửi đúng dạng `topics=...&topics=...`.

Tương tự, cú pháp `topics[]=java&topics[]=spring` tạo ra tên tham số thực tế là `topics[]`. Dấu ngoặc vuông **không tự biến** dữ liệu thành mảng theo một tiêu chuẩn chung; chỉ sử dụng nếu endpoint đã định nghĩa và kiểm thử quy ước đó.

### 2.3. Giá trị chứa ký tự đặc biệt

Với `application/x-www-form-urlencoded`, mỗi tên và giá trị phải được mã hóa đúng. Ví dụ:

| Giá trị gốc | Giá trị sau form encoding |
| --- | --- |
| `Spring REST Docs` | `Spring+REST+Docs` |
| `C++` | `C%2B%2B` |
| `A & B` | `A+%26+B` |
| `Đà Nẵng` | `%C4%90%C3%A0+N%E1%BA%B5ng` |

Khoảng trắng thường thành `+`, trong khi dấu cộng thật phải thành `%2B`. Nếu tự ghép body bằng phép nối chuỗi thiếu mã hóa, ký tự `&` trong một giá trị có thể bị hiểu nhầm là điểm bắt đầu parameter mới. Nên dùng bộ mã hóa form của HTTP client và thống nhất UTF-8 cho dữ liệu Unicode.

### 2.4. HTML form tạo repeated fields như thế nào?

Ví dụ người dùng có thể chọn nhiều checkbox hoặc nhiều lựa chọn trong `select`:

```html
<form action="/preferences" method="post" accept-charset="UTF-8">
  <label>
    Email
    <input name="email" type="email" required>
  </label>

  <label><input type="checkbox" name="topics" value="java"> Java</label>
  <label><input type="checkbox" name="topics" value="spring"> Spring</label>
  <label><input type="checkbox" name="topics" value="rest-docs"> REST Docs</label>

  <button type="submit">Lưu sở thích</button>
</form>
```

Các checkbox được chọn có thể gửi nhiều cặp `topics=...`, mỗi cặp mang cùng tên. Checkbox **không được chọn** thông thường không tạo ra cặp tham số tương ứng. Khi cần client gửi tối thiểu một lựa chọn, yêu cầu này phải được kiểm tra ở server; HTML validation chỉ hỗ trợ trải nghiệm người dùng.

## 3. Binding nhiều giá trị trong Spring MVC

Một endpoint đơn giản cho phép 1–3 chủ đề, mỗi chủ đề thuộc danh sách `java`, `spring`, `rest-docs`, `testing` và không được trùng:

```java
package example.docs;

import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/preferences")
public class PreferenceController {

    private static final Set<String> ALLOWED_TOPICS =
            Set.of("java", "spring", "rest-docs", "testing");

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> save(
            @RequestParam("email") String email,
            @RequestParam("topics") List<String> topics,
            @RequestParam(name = "note", required = false) String note) {

        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (topics.isEmpty() || topics.size() > 3) {
            return ResponseEntity.badRequest().build();
        }
        if (topics.stream().anyMatch(topic -> !ALLOWED_TOPICS.contains(topic))) {
            return ResponseEntity.badRequest().build();
        }
        if (topics.stream().distinct().count() != topics.size()) {
            return ResponseEntity.badRequest().build();
        }

        // Ví dụ học tập: ứng dụng thật cần lưu sở thích vào một service.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Giải thích từng lựa chọn:

- `@RequestParam("topics") List<String> topics` biểu diễn một **tên parameter** được gắn với nhiều giá trị. Đây là binding phía Spring MVC; client vẫn gửi các cặp tên/giá trị trong HTTP body.
- `@RequestParam("topics")` mặc định yêu cầu tham số phải có mặt; một request không có `topics` thường bị từ chối trước khi vào controller.
- `topics.isEmpty()`, `topics.size() > 3`, phép kiểm tra tập giá trị và phép kiểm tra trùng lặp thực thi **quy tắc nghiệp vụ**. REST Docs không tự kiểm tra chúng.
- `@RequestParam(name = "note", required = false)` cho phép bỏ trường `note`.
- Kiểm tra email minh họa đơn giản; `contains("@")` không phải bộ xác thực email chuẩn cho ứng dụng thực tế.

Muốn chắc chắn cách server xử lý `topics=`, `topics=java,docs` hoặc một tên trường có dấu ngoặc vuông, phải bổ sung test phù hợp với cấu hình converter thực tế. Không suy ra hành vi chỉ từ kiểu tham số `List<String>`.

## 4. Tài liệu hóa nhiều giá trị bằng `formParameters(...)`

### 4.1. Một descriptor cho một tên parameter

Spring REST Docs tạo một dòng mô tả cho **tên** `topics`, dù request có một hay nhiều giá trị:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

formParameters(
    parameterWithName("email")
        .description("Địa chỉ email; bắt buộc"),
    parameterWithName("topics")
                .description("Lặp tên topics để gửi 1–3 chủ đề; " +
                "chỉ nhận java, spring, rest-docs, testing; không trùng"),
    parameterWithName("note")
        .optional()
        .description("Ghi chú tùy chọn")
)
```

**Không viết ba descriptor khác nhau cùng tên `topics`** để mô tả `java`, `spring` và `rest-docs`. Descriptor thuộc về tên field, còn giá trị hợp lệ và quy tắc lặp được giải thích bằng `description(...)`. Số lượng, thứ tự và tính hợp lệ của các giá trị cần kiểm thử bằng assertion hoặc logic nghiệp vụ.

Ở chế độ nghiêm ngặt, `formParameters(...)` kiểm tra tập tên parameter: field xuất hiện nhưng không được mô tả gây lỗi; descriptor bắt buộc nhưng không có trong request cũng gây lỗi. `.optional()` cho phép thiếu tên trường; `.ignored()` bỏ một tên đã khai báo khỏi bảng hiển thị; `relaxedFormParameters(...)` chấp nhận tên chưa được mô tả. Các chế độ này **không** thay thế validation nhiều giá trị.

### 4.2. Bài kiểm thử MockMvc sinh snippet

Ví dụ dùng Spring Boot 3.x với Gradle Groovy DSL và dependency tương ứng:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Mã kiểm thử hoàn chỉnh cho controller trên:

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void multipleValuesGenerateOneParameterDescriptor() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .param("email", "mai@example.com")
                .param("topics", "java", "spring", "rest-docs")
                .param("note", "Học theo dự án"))
            .andExpect(status().isCreated())
            .andDo(document("preferences/multiple-topics",
                formParameters(
                    parameterWithName("email")
                        .description("Email bắt buộc"),
                    parameterWithName("topics")
                        .description("Danh sách 1–3 chủ đề: " +
                                "java, spring, rest-docs, testing; lặp tên topics"),
                    parameterWithName("note")
                        .optional()
                        .description("Ghi chú tùy chọn")
                )
            ));
    }

    @Test
    void singleTopicAndOmittedNoteAreValid() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java"))
            .andExpect(status().isCreated());
    }

    @Test
    void missingTopicsAreRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void duplicateTopicsAreRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java", "java"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownTopicIsRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java", "unknown"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void tooManyTopicsAreRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java", "spring", "rest-docs", "testing"))
            .andExpect(status().isBadRequest());
    }
}
```

Quy trình và kết quả:

1. `.param("topics", "java", "spring", "rest-docs")` tạo nhiều giá trị cho cùng tên `topics` trong request MockMvc.
2. Header `Content-Type: application/x-www-form-urlencoded` xác định nội dung form. Nếu request ngoài thực tế dùng client khác, kiểm tra `http-request.adoc` để chắc chắn body thật được mã hóa đúng.
3. `.andExpect(status().isCreated())` xác nhận một request hợp lệ được server chấp nhận.
4. `.andDo(document(..., formParameters(...)))` sinh `form-parameters.adoc` cho tên `email`, `topics` và `note`.
5. Các test lỗi chứng minh rằng server từ chối giá trị trùng, sai danh sách, quá số lượng hoặc thiếu trường bắt buộc. **Spring REST Docs không thể tự suy ra các quy tắc này từ descriptor.**

Nếu test dùng Spring Security với CSRF, request POST cần token hoặc thiết lập bảo mật kiểm thử phù hợp. Các ví dụ giả định controller không có phụ thuộc service bổ sung; nếu có, hãy mock dependency hoặc dùng cấu hình slice test thích hợp.

### 4.3. Kết quả snippet

Khi test tạo tài liệu thành công, các tệp tương ứng thường nằm tại:

```text
build/generated-snippets/
└── preferences/
    └── multiple-topics/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

Bảng thông tin của `form-parameters.adoc` có dạng:

| Parameter | Description |
| --- | --- |
| `email` | Email bắt buộc |
| `topics` | Danh sách 1–3 chủ đề: java, spring, rest-docs, testing; lặp tên topics |
| `note` | Ghi chú tùy chọn |

Bạn sẽ thấy **một hàng `topics`** dù request kiểm thử gửi ba giá trị. Để cho người đọc thấy cú pháp đầy đủ của request lặp tên, nhúng thêm `http-request.adoc` hoặc `curl-request.adoc`. Đừng sửa tay snippet để thêm từng giá trị; hãy làm rõ ý nghĩa ngay trong `description(...)` và fixture HTTP.

## 5. Biểu diễn nhiều giá trị với WebTestClient và REST Assured

Spring REST Docs có API `formParameters(...)` dùng chung cho các cách kiểm thử, nhưng mỗi HTTP client có cú pháp gửi repeated values riêng.

### 5.1. WebTestClient: `MultiValueMap`

Ví dụ giả định `webTestClient` đã gắn cấu hình Spring REST Docs, endpoint WebFlux có xử lý form body, và request thành công trả `201`:

```java
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("email", "mai@example.com");
form.add("topics", "java");
form.add("topics", "spring");
form.add("topics", "rest-docs");

webTestClient.post()
    .uri("/preferences")
    .body(BodyInserters.fromFormData(form))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("preferences/webtestclient",
        formParameters(
            parameterWithName("email").description("Email bắt buộc"),
            parameterWithName("topics")
                .description("Chủ đề có thể lặp lại, 1–3 giá trị")
        )
    ));
```

`MultiValueMap.add(...)` thêm giá trị mới **không ghi đè** những giá trị đã có cùng tên. `BodyInserters.fromFormData(form)` xây dựng form URL-encoded. Đối với WebFlux, handler thường nhận form qua `ServerWebExchange.getFormData()` hoặc binding phù hợp; không giả định có cùng quy tắc nguồn tham số với servlet `@RequestParam` của Spring MVC.

### 5.2. REST Assured: nhiều đối số của `formParam`

Ví dụ giả định có server đang chạy và `specification` đã được cấu hình bằng `RestAssuredRestDocumentation.documentationConfiguration(...)`:

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(specification)
    .filter(document("preferences/rest-assured",
        formParameters(
            parameterWithName("email").description("Email bắt buộc"),
            parameterWithName("topics")
                .description("Chủ đề có thể lặp lại, 1–3 giá trị")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .formParam("topics", "java", "spring", "rest-docs")
    .when().post("/preferences")
    .then().statusCode(201);
```

`ContentType.URLENC` xác định URL-encoded form. `formParam("topics", ...)` cung cấp các giá trị cùng tên; dùng `http-request.adoc` hoặc ghi nhận request HTTP trong test để xác nhận client đã gửi đúng dạng lặp tên. Tránh `body("[...]")` hoặc JSON khi hợp đồng API yêu cầu form body.

## 6. Phân biệt repeated form values với `multipart/form-data`

### 6.1. Multipart gồm các part có header riêng

Nếu API có tệp đính kèm hoặc payload phức tạp, dùng media type `multipart/form-data`. Body được phân định bằng một chuỗi `boundary` do HTTP client tạo. Ví dụ minh họa đơn giản hóa:

```http
POST /uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=FormBoundary123

--FormBoundary123
Content-Disposition: form-data; name="title"

Tài liệu khóa học
--FormBoundary123
Content-Disposition: form-data; name="files"; filename="lesson-a.txt"
Content-Type: text/plain

Content A
--FormBoundary123
Content-Disposition: form-data; name="files"; filename="lesson-b.txt"
Content-Type: text/plain

Content B
--FormBoundary123--
```

Một multipart request có nhiều **part**; trong ví dụ, tên `files` xuất hiện ở hai part riêng biệt. Mỗi part có thể mang nội dung nhị phân, text hoặc JSON và có metadata như `Content-Type`/`filename`. Đây không phải chuỗi `files=a&files=b` của URL-encoded form. Các dấu kết thúc dòng thực tế trong multipart theo định dạng HTTP tuân theo CRLF; ví dụ đã lược giản phần byte để dễ đọc.

| Đặc tính | Repeated URL-encoded form values | Multipart form |
| --- | --- | --- |
| Content-Type | `application/x-www-form-urlencoded` | `multipart/form-data; boundary=...` |
| Cấu trúc | Các cặp `name=value`, có thể trùng tên | Nhiều part, mỗi part có header riêng |
| Phù hợp | Chuỗi ngắn, checkbox, select nhiều lựa chọn | Upload tệp, hỗn hợp tệp và metadata |
| Mô tả bằng REST Docs | `formParameters(parameterWithName(...))` | `requestParts(partWithName(...))` |
| Nếu part chứa JSON | Không áp dụng như JSON part | Có thể dùng thêm `requestPartFields(...)` |

### 6.2. Server nhận nhiều tệp cùng một tên

Một controller Spring MVC minh họa:

```java
package example.docs;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/uploads")
public class UploadController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Void> upload(
            @RequestParam("files") List<MultipartFile> files) {

        if (files.isEmpty() || files.size() > 2 ||
                files.stream().anyMatch(MultipartFile::isEmpty)) {
            return ResponseEntity.badRequest().build();
        }
        // Ví dụ: chưa lưu hay quét nội dung tệp.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Sử dụng `List<MultipartFile>` cho cùng tên `files`. Endpoint thực tế cần bổ sung giới hạn kích thước, kiểm tra định dạng, tên tệp, bảo mật và xử lý lưu trữ. Các điều kiện đó không được REST Docs kiểm chứng tự động.

### 6.3. Document multipart bằng `requestParts(...)`

Giả sử `mockMvc` đã cấu hình Spring REST Docs với controller `UploadController`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MockMultipartFile first = new MockMultipartFile(
    "files", "lesson-a.txt", "text/plain",
    "Content A".getBytes(StandardCharsets.UTF_8));

MockMultipartFile second = new MockMultipartFile(
    "files", "lesson-b.txt", "text/plain",
    "Content B".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/uploads").file(first).file(second))
    .andExpect(status().isCreated())
    .andDo(document("uploads/multiple-files",
        requestParts(
            partWithName("files")
                .description("Từ 1 đến 2 tệp; gửi nhiều part cùng tên files")
        )
    ));
```

Kết quả sinh `request-parts.adoc`, trong đó tên `files` có một mô tả hợp đồng. `requestParts` kiểm tra **tên part được mô tả**, không tự xác thực rằng có đúng hai tệp, file không rỗng hay có `Content-Type` phù hợp; những điều này được xử lý bằng validation và test riêng. Nếu một part chứa JSON có cấu trúc, có thể bổ sung `requestPartFields("metadata", fieldWithPath("version").description(...))` để tạo snippet riêng cho nội dung của part `metadata`; cần gửi part JSON tương ứng trong request kiểm thử.

**Lưu ý:** không dùng `formParameters(...)` thay cho `requestParts(...)` để mô tả các file upload. Nếu một multipart request đồng thời chứa text field, hãy lựa chọn cách tài liệu hóa dựa trên việc dữ liệu được gửi dưới dạng parameter hay request part trong request thực và xác minh snippet được sinh.

## 7. Đưa các snippet vào tài liệu và CI

Với test form URL-encoded ở mục 4, trang Asciidoctor có thể nhúng:

```adoc
= Preferences API

== Gửi nhiều chủ đề quan tâm

=== HTTP request có tên form lặp lại
include::{snippets}/preferences/multiple-topics/http-request.adoc[]

=== Form parameters
include::{snippets}/preferences/multiple-topics/form-parameters.adoc[]

=== HTTP response
include::{snippets}/preferences/multiple-topics/http-response.adoc[]

== Upload nhiều tệp

=== Multipart request
include::{snippets}/uploads/multiple-files/http-request.adoc[]

=== Các part
include::{snippets}/uploads/multiple-files/request-parts.adoc[]
```

Biến `{snippets}` phải trỏ đến thư mục gốc chứa snippet, chẳng hạn `build/generated-snippets`. Lệnh `include::{snippets}/...[]` thuộc Asciidoctor, không phải tính năng mặc định của Markdown. Nếu sản phẩm cần Markdown, hãy liên kết đến HTML được biên dịch hoặc thêm bước chuyển đổi có kiểm soát.

Trong Gradle Groovy DSL với plugin Asciidoctor đã được cài:

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

Trong CI:

```bash
./gradlew test asciidoctor
```

Pipeline cần kiểm tra test thành công, snippet được tạo ở đường dẫn dự kiến và tài liệu kết quả đã render. Khi server đổi từ “một giá trị” thành “nhiều giá trị” hoặc từ URL-encoded sang multipart, hãy cập nhật fixture, validation, descriptor và ví dụ HTTP; không nên chỉnh trực tiếp các tệp `.adoc` được sinh tự động.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Server chỉ nhận phần tử cuối | Client/map ghi đè giá trị khi dùng cùng tên | Dùng cơ chế nhiều giá trị (`MultiValueMap.add`, varargs `.param`) và xác minh HTTP body |
| API yêu cầu lặp tên nhưng client gửi `topics=java,spring` | Nhầm chuỗi chứa dấu phẩy với repeated fields | Gửi `topics=java&topics=spring` theo hợp đồng |
| Nhìn thấy `topics[]` nhưng không bind được `topics` | Tên thực tế khác nhau | Đồng nhất tên field với controller và descriptor hoặc cấu hình binding có chủ đích |
| REST Docs chỉ hiển thị một hàng `topics` | Snippet mô tả tên parameter, không mô tả từng giá trị | Giải thích quy tắc lặp trong description và nhúng HTTP request mẫu |
| Test snippet qua nhưng danh sách chứa giá trị trùng | REST Docs không xác nhận số lượng, tính duy nhất | Thêm validation và test lỗi nghiệp vụ |
| Dấu `+` mất hoặc `&` tách giá trị sai | Form encoding bị làm thủ công | Dùng encoder, UTF-8, kiểm tra raw request |
| Request upload được gửi bằng URL-encoded | Nhầm repeated text values với file parts | Dùng `multipart/form-data` và `requestParts(...)` |
| Multipart dùng `formParameters` nhưng không tài liệu hóa file | Chọn sai đối tượng snippet | Dùng `requestParts(partWithName(...))`; thêm `requestPartFields` cho payload JSON có cấu trúc |
| Trang Asciidoctor không thấy snippet | Test chưa chạy, sai tên identifier hoặc thiếu biến `{snippets}` | Cho build tài liệu phụ thuộc `test` và kiểm tra đường dẫn thực tế |

Không dùng mật khẩu, token hay dữ liệu cá nhân thật trong fixture; snippet `http-request.adoc` có thể đưa giá trị request vào tài liệu công bố. Với upload, chỉ dùng tệp giả và không xuất nội dung nhạy cảm trong ví dụ.

## 9. Bài tập thực hành

Thiết kế hai endpoint để kiểm chứng sự khác nhau:

**Bài A — URL-encoded multi-value:** `POST /enrollments` nhận `studentId` bắt buộc và `courses` lặp lại 1–4 lần; khóa học phải thuộc tập `java`, `sql`, `git`, `testing` và không trùng nhau.

1. Viết controller nhận `List<String> courses` cùng các điều kiện nghiệp vụ.
2. Viết MockMvc test gửi `courses=java&courses=git`, sinh `form-parameters.adoc` với **một** descriptor tên `courses`.
3. Viết test thiếu `courses`, trùng `courses` và quá bốn giá trị. Quan sát rằng test hành vi, chứ không phải descriptor, phát hiện lỗi này.
4. Dùng WebTestClient `MultiValueMap` hoặc REST Assured `formParam` để tạo request tương đương và đối chiếu snippet HTTP.

**Bài B — multipart:** `POST /assignments` nhận từ một đến hai file cùng tên `attachments`, giới hạn kích thước/tệp theo yêu cầu bạn định nghĩa.

1. Gửi hai `MockMultipartFile` cùng tên `attachments` qua `multipart(...)`.
2. Sinh `request-parts.adoc` với `requestParts(partWithName("attachments")...)`.
3. Thử thêm part metadata JSON và tài liệu hóa trường bên trong bằng `requestPartFields(...)`.
4. Tạo trang Asciidoctor gồm ví dụ request và hai bảng phù hợp; đưa test vào trước bước render tài liệu trong CI.

**Tiêu chí đạt:** bạn xác định đúng khi nào một **parameter chứa nhiều giá trị** và khi nào một **request gồm nhiều part**; client gửi đúng wire format; server kiểm chứng số lượng/giá trị; snippet Spring REST Docs được sinh từ kiểm thử HTTP và được biên soạn tự động thành tài liệu.

## Tham khảo

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
