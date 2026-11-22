# Document form parameters bằng `formParameters`

## 1. Khi nào cần tài liệu hóa form parameters?

Trong **Spring REST Docs** (`SPRING_REST_DOCS`), tài liệu REST API được tạo từ những bài kiểm thử HTTP đã chạy thành công. Một endpoint nhận dữ liệu từ biểu mẫu HTML thường dùng `Content-Type: application/x-www-form-urlencoded`; từng cặp `tên=giá trị` nằm trong **body** của request. API gọi endpoint cần biết trường nào bắt buộc, trường nào có thể bỏ qua, ý nghĩa và định dạng của từng giá trị.

Ví dụ, client gửi yêu cầu đăng ký nhận bản tin:

```http
POST /subscriptions HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=lan%40example.com&frequency=weekly&referral=docs
```

Sau khi giải mã form, server nhận ba tham số `email`, `frequency` và `referral`. Khác với JSON, chúng không phải các trường của một đối tượng JSON. Spring REST Docs cung cấp `RequestDocumentation.formParameters(...)` để mô tả các **form parameter nằm trong body** và sinh snippet `form-parameters.adoc` từ request thật trong bài kiểm thử.

**Mục tiêu thực hành:** tạo endpoint nhận form, viết bài kiểm thử MockMvc tạo snippet, hiểu cách kiểm tra tham số, rồi đưa snippet vào trang Asciidoctor và quy trình build/CI. Cùng ý tưởng có thể áp dụng qua WebTestClient và REST Assured.

## 2. Phân biệt form parameters với các thành phần request khác

| Dữ liệu | Vị trí / kiểu dữ liệu | Cách tài liệu hóa phù hợp |
| --- | --- | --- |
| `email=lan%40example.com` | Body `application/x-www-form-urlencoded` | `formParameters(...)` |
| `?page=2&size=10` | Query string trên URL | `queryParameters(...)` |
| `/subscriptions/42` | Giá trị nằm trong đường dẫn | `pathParameters(...)` |
| `{"email":"lan@example.com"}` | Body JSON | `requestFields(...)` |
| `Authorization: Bearer ...` | HTTP header | `requestHeaders(...)` |
| Tệp và các phần trong `multipart/form-data` | Multipart request body | `requestParts(...)`, các snippet hỗ trợ request part |

Không nên xem `formParameters` và `queryParameters` là tương đương chỉ vì Spring MVC đều có thể ánh xạ chúng bằng `@RequestParam`. Ví dụ `POST /subscriptions?source=web` đồng thời gửi body `email=...` có hai nơi chứa tham số khác nhau: `source` là query parameter, còn `email` là form parameter. Nếu cần tài liệu hóa cả hai, thêm riêng hai snippet vào lệnh `document(...)`.

API `formParameters(...)` có từ **Spring REST Docs 3.0.0**. Khi tham khảo mã cũ dùng `requestParameters(...)`, hãy kiểm tra phiên bản thư viện và chuyển sang cặp API chuyên biệt `queryParameters(...)` / `formParameters(...)` khi dùng Spring REST Docs 3.x trở lên.

## 3. API cốt lõi: `formParameters` và `parameterWithName`

Các static import thường dùng:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.relaxedFormParameters;
```

Ví dụ khai báo hợp đồng của một biểu mẫu:

```java
formParameters(
    parameterWithName("email")
        .description("Địa chỉ email đăng ký; bắt buộc"),
    parameterWithName("frequency")
        .optional()
        .description("Tần suất: weekly hoặc monthly; mặc định weekly"),
    parameterWithName("referral")
        .optional()
        .description("Mã giới thiệu; có thể không gửi")
)
```

- `parameterWithName("email")` tạo mô tả cho **tên tham số**, không đại diện cho một giá trị cụ thể.
- `.description(...)` giải thích ý nghĩa, giá trị hợp lệ, định dạng, đơn vị hoặc mặc định. Nên viết rõ quy tắc mà API thực sự thực thi.
- `.optional()` cho phép tham số không xuất hiện trong request đang được kiểm thử; nó **không tự biến** `@RequestParam` trong controller thành tham số tùy chọn và không thay cho kiểm thử nghiệp vụ.
- `.ignored()` dùng khi phải chấp nhận một tham số xuất hiện nhưng không muốn hiển thị nó trong bảng snippet.

Ở chế độ mặc định, Spring REST Docs kiểm tra **tập tên tham số**: request chứa form parameter chưa được khai báo thì bước tạo snippet thất bại; tham số đã khai báo nhưng không có trong request cũng gây lỗi nếu chưa đánh dấu `optional()`. Kiểm tra này không tự xác minh email hợp lệ, miền giá trị hay điều kiện nghiệp vụ; những điều đó cần assertion và test riêng.

## 4. Ví dụ hoàn chỉnh với Spring MVC và MockMvc

Giả sử API đăng ký nhận bản tin có ba tham số: `email` bắt buộc; `frequency` và `referral` tùy chọn. Khi bỏ qua `frequency`, server lấy `weekly` làm mặc định.

### 4.1. Controller nhận dữ liệu form

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
@RequestMapping("/subscriptions")
public class SubscriptionController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String email,
            @RequestParam(defaultValue = "weekly") String frequency,
            @RequestParam(required = false) String referral) {

        // Mô phỏng quy tắc nghiệp vụ; một hệ thống thật sẽ lưu đăng ký.
        if (!frequency.equals("weekly") && !frequency.equals("monthly")) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Đây là controller minh họa tối giản: nó kiểm tra `frequency`, nhưng chưa kiểm tra cú pháp email, chống đăng ký trùng hoặc lưu dữ liệu. Tài liệu của hệ thống thật phải bám sát những quy tắc đã được hiện thực và kiểm thử.

### 4.2. Tích hợp Spring REST Docs trong bài kiểm thử

Với dự án Spring Boot dùng Gradle, cần có Spring Boot Test và thư viện tương ứng cho MockMvc:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Ví dụ sau giả định phiên bản Spring REST Docs do cấu hình dependency management của dự án cung cấp.

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SubscriptionController.class)
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class SubscriptionDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createSubscriptionGeneratesFormParameterSnippet() throws Exception {
        mockMvc.perform(post("/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.com")
                .param("frequency", "weekly")
                .param("referral", "docs"))
            .andExpect(status().isCreated())
            .andDo(document("subscriptions/create",
                formParameters(
                    parameterWithName("email")
                        .description("Email đăng ký; bắt buộc"),
                    parameterWithName("frequency")
                        .optional()
                        .description("weekly hoặc monthly; mặc định weekly"),
                    parameterWithName("referral")
                        .optional()
                        .description("Mã giới thiệu, nếu có")
                )
            ));
    }

    @Test
    void missingRequiredEmailIsRejected() throws Exception {
        mockMvc.perform(post("/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("frequency", "weekly"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidFrequencyIsRejected() throws Exception {
        mockMvc.perform(post("/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.com")
                .param("frequency", "hourly"))
            .andExpect(status().isBadRequest());
    }
}
```

Quy trình của test tạo tài liệu:

1. `post(...)` tạo request HTTP; `contentType(APPLICATION_FORM_URLENCODED)` mô tả dạng body mà API nhận; `.param(...)` cung cấp từng giá trị form cho MockMvc.
2. `.andExpect(status().isCreated())` kiểm tra response. Nếu assertion này thất bại, chuỗi xử lý không đi đến bước tạo snippet trong ví dụ.
3. `.andDo(document("subscriptions/create", ...))` ghi các snippet vào thư mục theo định danh `subscriptions/create`.
4. `formParameters(...)` đối chiếu tên các trường của request với những `parameterWithName(...)` đã khai báo, đồng thời tạo bảng tài liệu.

Hai test lỗi minh họa **kiểm chứng hợp đồng của endpoint**, bổ sung cho việc Spring REST Docs kiểm chứng tính đầy đủ của danh sách tham số. Tùy cấu hình Spring Security, các request POST trong dự án có bảo vệ CSRF có thể cần bổ sung CSRF hợp lệ trong test.

### 4.3. Snippet được tạo ra

Sau khi chạy test thành công, thư mục đầu ra chứa tệp:

```text
build/generated-snippets/
└── subscriptions/
    └── create/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

`form-parameters.adoc` là bảng AsciiDoc do Spring REST Docs tạo, có nội dung tương đương ví dụ sau (cách trình bày thực tế phụ thuộc template):

| Parameter | Description |
| --- | --- |
| `email` | Email đăng ký; bắt buộc |
| `frequency` | weekly hoặc monthly; mặc định weekly |
| `referral` | Mã giới thiệu, nếu có |

**Chú ý:** đánh dấu `.optional()` giúp kiểm thử không lỗi nếu thiếu trường; hãy giải thích tính tùy chọn và giá trị mặc định trong description để độc giả hiểu đúng, thay vì chỉ dựa vào cách render của template.

## 5. Các tình huống quan trọng khi tài liệu hóa form

### 5.1. Bỏ qua tham số phụ bằng `.ignored()`

Giả sử request có thêm `trackingCode` do tầng tích hợp sử dụng, còn trang tài liệu chỉ muốn công bố các trường nghiệp vụ:

```java
formParameters(
    parameterWithName("email").description("Email đăng ký"),
    parameterWithName("trackingCode").ignored()
)
```

Khi request có `trackingCode`, phần kiểm tra không coi nó là tham số chưa khai báo, nhưng nó **không xuất hiện** trong bảng `form-parameters.adoc`. Chỉ dùng `ignored()` khi chủ động quyết định không công bố trường đó; đừng áp dụng tràn lan để che lỗi tài liệu thiếu trường.

### 5.2. Chế độ nới lỏng `relaxedFormParameters(...)`

```java
relaxedFormParameters(
    parameterWithName("email").description("Email đăng ký")
)
```

Ở chế độ này, form có thể chứa các tên tham số khác mà không làm bước tạo snippet thất bại. Tuy nhiên, `email` vẫn được kiểm tra hiện diện vì chưa đánh dấu `.optional()`. Chế độ nới lỏng phù hợp với tài liệu cho **một phần** của biểu mẫu lớn; tài liệu mô tả hợp đồng công khai hoàn chỉnh nên ưu tiên `formParameters(...)` ở chế độ nghiêm ngặt.

### 5.3. Trường tùy chọn thực sự vắng mặt

Một request hợp lệ chỉ gửi `email`:

```java
mockMvc.perform(post("/subscriptions")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "lan@example.com"))
    .andExpect(status().isCreated())
    .andDo(document("subscriptions/create-minimal",
        formParameters(
            parameterWithName("email").description("Email đăng ký"),
            parameterWithName("frequency").optional()
                .description("Tần suất; mặc định weekly"),
            parameterWithName("referral").optional()
                .description("Mã giới thiệu")
        )
    ));
```

Đây là cách kiểm chứng rằng tài liệu chấp nhận một request thiếu hai trường tùy chọn. Để kiểm tra server thực sự áp dụng giá trị mặc định, nên thêm assertion ở tầng phù hợp (ví dụ xác minh tham số được truyền đến service) thay vì suy ra chỉ từ status `201`.

### 5.4. Một tên tham số có nhiều giá trị

Với endpoint có tham số form `topics=spring&topics=docs`, trong MockMvc có thể tạo request bằng:

```java
.param("topics", "spring", "docs")
```

Và khai báo **một** descriptor theo tên:

```java
parameterWithName("topics")
    .description("Danh sách chủ đề; có thể lặp lại tên topics")
```

`formParameters` kiểm tra tên `topics`, không kiểm tra từng phần tử của danh sách hoặc số lượng giá trị. Hãy tạo test riêng nếu endpoint yêu cầu giới hạn số mục, không cho phép giá trị trùng hoặc kiểm tra giá trị thuộc một tập cho phép.

### 5.5. Khi vừa có query parameter, vừa có form parameter

```java
mockMvc.perform(post("/subscriptions?source=landing-page")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "lan@example.com"))
    .andExpect(status().isCreated())
    .andDo(document("subscriptions/create-with-source",
        queryParameters(
            parameterWithName("source").description("Nguồn truy cập")
        ),
        formParameters(
            parameterWithName("email").description("Email đăng ký")
        )
    ));
```

Đoạn code này cần static import `queryParameters`. Với query parameter, truyền giá trị ngay trên URL hoặc dùng `.queryParam(...)` giúp nguồn tham số rõ ràng. Không dùng `.param(...)` thay thế một cách máy móc cho query parameter, vì nó biểu diễn tham số request ở mức Servlet và dễ gây nhầm lẫn với form body.

## 6. Cùng kỹ thuật với WebTestClient và REST Assured

Spring REST Docs hỗ trợ nhiều công cụ kiểm thử HTTP; `formParameters(...)` và `parameterWithName(...)` vẫn thuộc cùng package `org.springframework.restdocs.request`. Điểm khác nhau chủ yếu là cách gửi request và móc bước tạo snippet vào kết quả.

### 6.1. WebTestClient

Ví dụ dưới đây giả định `webTestClient` đã được cấu hình Spring REST Docs và endpoint WebFlux có xử lý body form:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("email", "lan@example.com");
form.add("frequency", "weekly");

webTestClient.post()
    .uri("/subscriptions")
    .body(BodyInserters.fromFormData(form))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("subscriptions/webtestclient",
        formParameters(
            parameterWithName("email").description("Email đăng ký"),
            parameterWithName("frequency").optional()
                .description("Tần suất, mặc định weekly")
        )
    ));
```

Các import liên quan là `org.springframework.util.MultiValueMap`, `LinkedMultiValueMap`, `org.springframework.web.reactive.function.BodyInserters` và `WebTestClientRestDocumentation.document`. `BodyInserters.fromFormData(...)` tạo body form URL-encoded. Trong Spring WebFlux, cách đọc form của handler khác Spring MVC; không mặc định áp dụng ví dụ controller `@RequestParam` phía trên cho WebFlux. Hãy kiểm tra binding của handler, chẳng hạn dùng `ServerWebExchange.getFormData()` hoặc một model phù hợp.

### 6.2. REST Assured

Ví dụ sau giả định `specification` đã gắn `RestAssuredRestDocumentation.documentationConfiguration(...)` và có server HTTP đang chạy:

```java
given(specification)
    .filter(document("subscriptions/rest-assured",
        formParameters(
            parameterWithName("email").description("Email đăng ký"),
            parameterWithName("frequency").optional()
                .description("Tần suất, mặc định weekly")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "lan@example.com")
    .formParam("frequency", "weekly")
    .when().post("/subscriptions")
    .then().statusCode(201);
```

Các thành phần đặc thù: `io.restassured.RestAssured.given`, `io.restassured.http.ContentType.URLENC` và `RestAssuredRestDocumentation.document`. REST Assured gửi form bằng `.formParam(...)` và áp dụng bộ lọc tài liệu bằng `.filter(...)`.

## 7. Đưa snippet vào tài liệu và CI

### 7.1. Biên soạn trang Asciidoctor

Tạo một trang AsciiDoc (ví dụ `src/docs/asciidoc/index.adoc`) và dùng chỉ thị `include`:

```adoc
= API đăng ký nhận bản tin

== Tạo đăng ký

=== HTTP request
include::{snippets}/subscriptions/create/http-request.adoc[]

=== Form parameters
include::{snippets}/subscriptions/create/form-parameters.adoc[]

=== HTTP response
include::{snippets}/subscriptions/create/http-response.adoc[]
```

`{snippets}` cần được cấu hình trỏ tới **thư mục chứa snippet thực tế** (ví dụ `build/generated-snippets` với Gradle). Giá trị tương đối phải được giải quyết đúng theo thư mục tài liệu; trong tác vụ build có thể dùng đường dẫn tuyệt đối để tránh phụ thuộc nơi chạy lệnh.

### 7.2. Nối bước kiểm thử và xuất tài liệu

Trong Gradle có plugin Asciidoctor, ý tưởng cấu hình quan hệ tác vụ như sau (Groovy DSL, bổ sung vào build đang có plugin phù hợp):

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir.absolutePath
}
```

Sau đó một bước CI có thể chạy `./gradlew test asciidoctor`. Khi test thất bại vì hợp đồng tham số không còn khớp, pipeline dừng và không công bố tài liệu được coi là hợp lệ. Khi test qua, Asciidoctor lấy các đoạn sinh được và tạo HTML hoặc định dạng xuất mà dự án đã cấu hình. Cần kiểm tra cả tệp đầu ra của Asciidoctor, không chỉ kiểm tra thư mục snippet tồn tại.

Nếu tài liệu chính viết bằng **Markdown**, có thể đặt liên kết tới tài liệu HTML đã sinh hoặc thiết kế bước chuyển đổi/nhúng phù hợp; `include::{snippets}/...[]` là **cú pháp AsciiDoc**, không phải cú pháp nhúng được hỗ trợ mặc định bởi mọi trình render Markdown.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `form-parameters.adoc` không xuất hiện | Chưa gọi `document(...)`, chưa cấu hình REST Docs hoặc test không tới được bước ghi snippet | Kiểm tra cấu hình `@AutoConfigureRestDocs`, assertion, định danh snippet và thư mục output |
| Báo tham số chưa được tài liệu hóa | Form body có tên mới mà `formParameters(...)` chưa khai báo | Bổ sung `parameterWithName(...)`, hoặc chỉ `ignored()` khi có chủ ý |
| Báo thiếu tham số đã khai báo | Test không gửi tham số nhưng descriptor mặc định là bắt buộc | Thêm dữ liệu test nếu bắt buộc; đánh dấu `.optional()` nếu hợp đồng thực sự cho phép bỏ qua |
| Gửi JSON nhưng bảng form trống / lỗi | Body không phải form URL-encoded | Dùng đúng content type và body form, hoặc chuyển sang `requestFields(...)` cho JSON |
| Ghi `page` trong URL nhưng dùng `formParameters` | Nhầm query string với form body | Dùng `queryParameters(...)` cho `page` |
| Dùng `relaxedFormParameters` khiến thay đổi biểu mẫu không bị phát hiện | Chế độ nới lỏng chấp nhận tên ngoài danh sách | Quay về chế độ nghiêm ngặt khi cần bảo vệ đầy đủ hợp đồng |
| Asciidoctor báo không thấy file `include` | Test chưa chạy, sai identifier hoặc `{snippets}` sai đường dẫn | Cho tác vụ tài liệu phụ thuộc tác vụ test, kiểm tra thư mục sinh thực tế |

Không đưa token, mật khẩu, địa chỉ hay dữ liệu cá nhân thật vào fixture: snippet HTTP request có thể đưa giá trị request kiểm thử vào tài liệu xuất bản. Dùng dữ liệu giả như `lan@example.com` và xem lại các snippet trước khi phát hành.

## 9. Bài tập tự thực hành

1. Tạo API `POST /feedback` với form `rating` bắt buộc (1–5), `comment` tùy chọn và `tags` có thể nhận nhiều giá trị.
2. Viết MockMvc test gửi form hợp lệ và dùng `formParameters(...)` mô tả ba tham số, trong đó `comment` và `tags` được đánh dấu `.optional()` nếu controller cho phép bỏ qua.
3. Viết thêm test xác nhận `rating=6` bị từ chối; đừng coi việc tạo snippet thành công là bằng chứng rằng validation đã đúng.
4. Thử thêm tham số `unexpected=1` vào body mà không khai báo; quan sát kiểm thử bị fail ở chế độ nghiêm ngặt. Sau đó thử `relaxedFormParameters(...)` và giải thích sự khác nhau.
5. Nhúng `form-parameters.adoc` vào trang Asciidoctor và xác nhận trang cuối cùng hiển thị bảng đúng từ test vừa chạy.

**Tiêu chí đạt:** có bài kiểm thử HTTP xác nhận hành vi, snippet `form-parameters.adoc` sinh ra từ chính request đó, tài liệu giải thích đúng trường bắt buộc/tùy chọn, và build tài liệu không bỏ qua lỗi hợp đồng tham số.

## Tham khảo

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
