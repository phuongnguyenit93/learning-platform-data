# Phân biệt form parameter với request body JSON trong Spring REST Docs

## 1. Cùng dữ liệu nghiệp vụ, hai hợp đồng HTTP khác nhau

Trong chương **Form parameters** của module **SPRING_REST_DOCS**, câu hỏi quan trọng là: một API nhận dữ liệu biểu mẫu bằng `application/x-www-form-urlencoded` khác gì một API nhận đối tượng JSON bằng `application/json`? Sự khác biệt quyết định cách client đóng gói dữ liệu, cách Spring đọc request, cách kiểm thử HTTP và loại snippet mà **Spring REST Docs** có thể tạo.

Module hướng đến việc sinh tài liệu REST API **có thể kiểm chứng bằng bài kiểm thử** với MockMvc, WebTestClient hoặc REST Assured. Snippet được tạo từ request, response, payload, tham số và header trong test; tiếp đó được đưa vào tài liệu Asciidoctor/Markdown và quy trình build/CI. Nếu ghi sai loại payload hoặc chọn nhầm snippet, tài liệu có thể đánh lừa người sử dụng API dù các tên trường nhìn giống nhau.

Ví dụ cùng một thao tác đăng ký tài khoản với email, gói sử dụng và ghi chú:

**Request gửi bằng form URL-encoded:**

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json

email=mai%40example.com&plan=pro&note=Xin+ch%C3%A0o
```

**Request gửi bằng JSON:**

```http
POST /registrations HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "email": "mai@example.com",
  "plan": "pro",
  "note": "Xin chào"
}
```

Hai request có ý nghĩa nghiệp vụ tương đương nhưng **không hoán đổi tùy ý**: body, media type, bộ giải mã, kiểu dữ liệu và cơ chế tài liệu hóa khác nhau. Một endpoint có thể chấp nhận cả hai nếu khai báo và kiểm thử riêng, hoặc chỉ hỗ trợ một dạng.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận biết form parameters trong HTTP body, JSON fields và query parameters trong URL.
2. Giải thích cách Spring MVC bind dữ liệu qua `@RequestParam` và `@RequestBody`.
3. Chọn đúng `formParameters(parameterWithName(...))` hoặc `requestFields(fieldWithPath(...))`.
4. Viết test xác nhận request hợp lệ, dữ liệu thiếu, dữ liệu sai và media type không tương thích.
5. Đưa hai bộ snippet vào tài liệu mà người đọc biết chính xác phải gửi loại request nào.

## 2. So sánh cấu trúc HTTP và kiểu dữ liệu

| Tiêu chí | Form URL-encoded | JSON request body |
| --- | --- | --- |
| Request `Content-Type` | `application/x-www-form-urlencoded` | `application/json` |
| Cấu trúc | `name=value&name=value` | Object, array, string, number, boolean, `null` |
| Nơi đặt dữ liệu | HTTP body | HTTP body |
| Mã hóa khoảng trắng trong ví dụ | `+` | Ký tự khoảng trắng trong chuỗi JSON |
| Mã hóa ký tự đặc biệt | Percent-encoding theo byte của charset | Ký tự trong JSON string, escape nếu cần |
| Nhiều giá trị cùng tên | Có thể lặp `topic=java&topic=spring` | Thường dùng array `"topic":["java","spring"]` |
| Giá trị số/boolean | Trên wire thường là chuỗi, server chuyển kiểu | JSON có kiểu number/boolean trực tiếp |
| Null | Không có kiểu `null` chuẩn trong form encoding | Có literal `null` |
| Nested object | Không có biểu diễn chuẩn phổ quát | Hỗ trợ object lồng nhau |
| Spring MVC thường dùng | `@RequestParam` hoặc form/model binding | `@RequestBody` với HTTP message converter |
| REST Docs mô tả body | `formParameters(...)` | `requestFields(...)` |

**Cả form URL-encoded và JSON đều nằm trong HTTP body**, vì vậy câu “form là parameter còn JSON là request body” không hoàn toàn chính xác. Điểm khác là **cách biểu diễn và cách trích xuất dữ liệu trong body**.

### 2.1. Mã hóa form và JSON

Với form URL-encoded, các cặp tên/giá trị được nối bằng `&` và phân tách bằng `=`:

```text
email=mai%40example.com&note=C%2B%2B+%26+Java
```

Sau khi giải mã, `email` là `mai@example.com` và `note` là `C++ & Java`. Trong URL-encoded form, khoảng trắng thường biểu diễn bằng `+`, dấu cộng thật là `%2B` và dấu `&` bên trong giá trị là `%26`.

Với JSON, sử dụng cú pháp literal theo JSON:

```json
{
  "email": "mai@example.com",
  "note": "C++ & Java"
}
```

Các dấu `+` và `&` nằm trong chuỗi JSON không có nghĩa phân tách tham số. Đặc biệt, **không dùng form encoder để mã hóa toàn bộ JSON string**, cũng không gửi JSON nhưng khai báo `Content-Type: application/x-www-form-urlencoded`.

### 2.2. Query parameters là một khái niệm khác

Ví dụ URL có query parameter:

```http
POST /registrations?source=campaign HTTP/1.1
Content-Type: application/json

{"email":"mai@example.com","plan":"pro"}
```

Ở đây `source` thuộc **query string của URL** và cần `queryParameters(...)`; `email` và `plan` thuộc **JSON body** và cần `requestFields(...)`. Một request cũng có thể dùng query parameter với form body; không chọn `formParameters(...)` chỉ vì Spring MVC có thể bind query và form qua `@RequestParam`.

### 2.3. Header `Content-Type` khác `Accept`

`Content-Type` mô tả **body của chính thông điệp hiện tại**. Trong request, nó cho biết client đang gửi form hay JSON. `Accept` mô tả **định dạng response mà client muốn nhận**. Vì vậy request có thể gửi form nhưng vẫn mong response JSON:

```http
Content-Type: application/x-www-form-urlencoded
Accept: application/json
```

Khi tài liệu hóa API, kiểm thử nên chỉ rõ cả media type request và định dạng response. Nếu controller dùng `consumes`/`produces`, Spring có thể trả `415 Unsupported Media Type` hoặc `406 Not Acceptable` khi request không thỏa điều kiện tương ứng.

## 3. Phân biệt trường thiếu, rỗng, null và mảng

### 3.1. Với một trường tùy chọn

| Ý định client | Ví dụ form URL-encoded | Ví dụ JSON |
| --- | --- | --- |
| Không gửi `note` | `email=mai%40example.com` | `{"email":"mai@example.com"}` |
| Gửi chuỗi rỗng | `email=mai%40example.com&note=` | `{"email":"mai@example.com","note":""}` |
| Gửi null | Không có literal null chuẩn | `{"email":"mai@example.com","note":null}` |
| Gửi chuỗi “null” | `note=null` (chuỗi bốn ký tự) | `{"note":"null"}` (chuỗi bốn ký tự) |

Trong Spring MVC, khi `@RequestParam(required = false)` nhận trường vắng mặt, giá trị thường là `null` nếu không khai báo mặc định và không có converter tùy chỉnh. `@RequestParam(defaultValue = "basic")` có thể dùng giá trị mặc định khi tham số vắng mặt **hoặc rỗng**. Với JSON, `@RequestBody` thường giải mã object bằng Jackson; property vắng mặt và property `null` có thể cùng ánh xạ thành `null` ở DTO tham chiếu, nhưng ứng dụng vẫn có thể phân biệt bằng model/validation hoặc parser thích hợp nếu cần.

Vì vậy một API chấp nhận cả form và JSON cần **quy định rõ cùng một hợp đồng nghiệp vụ hay hai bộ quy tắc khác nhau**. Không suy ra quy tắc optional và default chỉ từ loại snippet.

### 3.2. Với danh sách nhiều giá trị

Form URL-encoded thường dùng lặp tên:

```text
topics=java&topics=spring
```

JSON có kiểu array:

```json
{
  "topics": ["java", "spring"]
}
```

Trong REST Docs, form được mô tả bằng **một** `parameterWithName("topics")` với description giải thích tên có thể lặp. JSON array thường được mô tả bằng `fieldWithPath("topics")`, sau đó có thể tài liệu hóa các đường dẫn bên trong object/mảng nếu schema phức tạp. Cú pháp `topics=java,spring` trong form chỉ tạo một chuỗi chứa dấu phẩy trên wire; việc server tách nó thành danh sách phụ thuộc converter và hợp đồng cụ thể.

### 3.3. Đối tượng lồng nhau

JSON biểu diễn cấu trúc lồng nhau một cách tự nhiên:

```json
{
  "email": "mai@example.com",
  "profile": {
    "city": "Hà Nội",
    "notifications": true
  }
}
```

Spring REST Docs có thể mô tả trường con `profile.city` và `profile.notifications` bằng `fieldWithPath(...)`. Đối với form URL-encoded, một ứng dụng có thể tự quy ước tên như `profile.city=Ha+Noi`, nhưng đó là **quy ước binding của ứng dụng**, không phải JSON object lồng nhau trong HTTP body.

## 4. Spring MVC: xử lý hai media type trên cùng một URL

Ví dụ sau minh họa hai handler `POST /registrations` cùng trả `201 Created` và response JSON. Spring MVC chọn handler dựa trên `Content-Type` của request nhờ `consumes`.

### 4.1. DTO cho JSON và response

```java
package example.docs;

public record RegistrationRequest(
        String email,
        String plan,
        String note) {
}
```

```java
package example.docs;

public record RegistrationResponse(
        String id,
        String email,
        String plan) {
}
```

Để tập trung vào tài liệu, ví dụ sử dụng Java record (Java 17+) và không kết nối cơ sở dữ liệu. Trường `id` cố định `reg-demo` chỉ là dữ liệu minh họa của bài kiểm thử; hệ thống thật sẽ tạo ID và lưu đăng ký.

### 4.2. Controller với `@RequestParam` và `@RequestBody`

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<RegistrationResponse> fromForm(
            @RequestParam("email") String email,
            @RequestParam(name = "plan", defaultValue = "basic") String plan,
            @RequestParam(name = "note", required = false) String note) {

        return register(email, plan, note);
    }

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<RegistrationResponse> fromJson(
            @RequestBody RegistrationRequest request) {

        // Với JSON, trường plan có thể vắng mặt hoặc nhận null.
        String plan = request.plan() == null || request.plan().isBlank()
                ? "basic"
                : request.plan();

        return register(request.email(), plan, request.note());
    }

    private ResponseEntity<RegistrationResponse> register(
            String email, String plan, String note) {

        // Validation tối thiểu để làm rõ các nhánh test.
        if (email == null || email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("pro")) {
            return ResponseEntity.badRequest().build();
        }

        RegistrationResponse result =
                new RegistrationResponse("reg-demo", email, plan);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
```

Lưu ý về hợp đồng:

- `fromForm(...)` sử dụng `@RequestParam` để lấy các cặp form parameter. `email` là trường bắt buộc ở tầng binding; `plan` có mặc định `basic`; `note` có thể không xuất hiện.
- `fromJson(...)` dùng `@RequestBody` để kích hoạt việc đọc toàn bộ body JSON qua `HttpMessageConverter` phù hợp (thường là Jackson trong Spring Boot). Property `email` vắng mặt không tự có quy tắc bắt buộc chỉ vì DTO khai báo `String email`; hàm `register(...)` từ chối `null`.
- Hai nhánh dùng chung `register(...)` nên quy tắc email và plan thống nhất. Việc đặt default `basic` ở nhánh JSON là **logic ứng dụng**, không phải tính năng `requestFields(...).optional()`.
- `email.contains("@")` chỉ là kiểm tra minh họa, không phải xác thực email production. Bài toán thật cần Bean Validation hoặc quy tắc kiểm tra phù hợp.
- `note` chưa được lưu; nếu cần phân biệt `null`, chuỗi rỗng và một giá trị cụ thể, phải triển khai xử lý và test tương ứng.
- Khi ứng dụng chỉ muốn hỗ trợ một kiểu body, chỉ giữ một mapping `consumes`; không cần tạo thêm handler chỉ để phục vụ tài liệu.

## 5. Chọn API Spring REST Docs đúng cho từng body

### 5.1. Form URL-encoded: `formParameters`

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

formParameters(
    parameterWithName("email")
        .description("Email đăng ký; bắt buộc và không rỗng"),
    parameterWithName("plan")
        .optional()
        .description("basic hoặc pro; mặc định basic"),
    parameterWithName("note")
        .optional()
        .description("Ghi chú tùy chọn")
)
```

Descriptor `parameterWithName("email")` mô tả **tên tham số trong form**. Theo chế độ nghiêm ngặt, nếu request có tên form chưa được mô tả, hoặc thiếu descriptor bắt buộc, bước tạo snippet thất bại. `.optional()` cho phép tham số đó vắng mặt trong request được tài liệu hóa; nó không thay đổi `@RequestParam` hay kiểm tra email hợp lệ.

Snippet được tạo có tên **`form-parameters.adoc`**.

### 5.2. JSON: `requestFields`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

requestFields(
    fieldWithPath("email")
        .description("Email đăng ký; bắt buộc và không rỗng"),
    fieldWithPath("plan")
        .optional()
        .description("basic hoặc pro; mặc định basic"),
    fieldWithPath("note")
        .optional()
        .description("Ghi chú tùy chọn")
)
```

Descriptor `fieldWithPath("email")` mô tả **đường dẫn trường trong payload JSON**. Khi JSON chứa object lồng nhau hoặc array, có thể khai báo các path như `profile.city` hoặc `items[].sku` theo schema thực tế. `.optional()` trong descriptor payload cho phép trường không hiện diện; nó **không** tự làm property trong DTO được optional, cũng không áp dụng giá trị mặc định.

Snippet được tạo có tên **`request-fields.adoc`**.

### 5.3. So sánh kiểm tra hợp đồng

| Tình huống | Form `formParameters` | JSON `requestFields` |
| --- | --- | --- |
| Request thêm tên `debug` chưa mô tả | Chế độ nghiêm ngặt báo form parameter chưa mô tả | Chế độ nghiêm ngặt báo JSON field chưa mô tả |
| Thiếu `email` trong request dùng để tạo tài liệu | Descriptor mặc định bắt buộc gây lỗi snippet | `fieldWithPath("email")` mặc định bắt buộc gây lỗi snippet |
| `note` được đánh dấu `.optional()` và bị bỏ qua | Bước kiểm tra snippet vẫn hợp lệ | Bước kiểm tra snippet vẫn hợp lệ |
| Nội dung `email` sai định dạng | Cần validation/test riêng | Cần validation/test riêng |
| Nhiều giá trị | Mô tả một tên form được lặp | Mô tả JSON array và các path phần tử nếu cần |
| Object lồng nhau | Cần quy ước binding riêng của ứng dụng | Có path lồng nhau được parser JSON hiểu trực tiếp |

**Quy tắc nhớ nhanh:** `parameterWithName(...)` mô tả *tên tham số*; `fieldWithPath(...)` mô tả *đường dẫn trường trong payload*. Không dùng `formParameters` cho JSON body hoặc `requestFields` cho URL-encoded form chỉ vì hai dạng trùng tên thuộc tính.

## 6. MockMvc: một suite test, hai loại snippet

Ví dụ dựa trên Spring Boot 3.x với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Ví dụ giả định dự án đã có dependency management cung cấp phiên bản Spring REST Docs tương thích. Với Spring Security bật CSRF, các request POST trong test cần thiết lập CSRF hợp lệ.

### 6.1. Hai test chính tạo snippet tương ứng

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
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormatDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentUrlEncodedForm() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .characterEncoding("UTF-8")
                .param("email", "mai@example.com")
                .param("plan", "pro")
                .param("note", "Xin chào"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("reg-demo"))
            .andExpect(jsonPath("$.plan").value("pro"))
            .andDo(document("registrations/form",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("application/x-www-form-urlencoded")
                ),
                formParameters(
                    parameterWithName("email")
                        .description("Email đăng ký; bắt buộc"),
                    parameterWithName("plan")
                        .optional().description("basic hoặc pro; mặc định basic"),
                    parameterWithName("note")
                        .optional().description("Ghi chú")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã đăng ký"),
                    fieldWithPath("email").description("Email đã đăng ký"),
                    fieldWithPath("plan").description("Gói được áp dụng")
                )
            ));
    }

    @Test
    void documentJsonRequest() throws Exception {
        String json = """
                {
                  "email": "mai@example.com",
                  "plan": "pro",
                  "note": "Xin chào"
                }
                """;

        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("reg-demo"))
            .andExpect(jsonPath("$.plan").value("pro"))
            .andDo(document("registrations/json",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("application/json")
                ),
                requestFields(
                    fieldWithPath("email")
                        .description("Email đăng ký; bắt buộc"),
                    fieldWithPath("plan")
                        .optional().description("basic hoặc pro; mặc định basic"),
                    fieldWithPath("note")
                        .optional().description("Ghi chú")
                ),
                responseFields(
                    fieldWithPath("id").description("Mã đăng ký"),
                    fieldWithPath("email").description("Email đã đăng ký"),
                    fieldWithPath("plan").description("Gói được áp dụng")
                )
            ));
    }

    @Test
    void formWithoutOptionalFieldsUsesDefaultPlan() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.plan").value("basic"));
    }

    @Test
    void jsonWithoutOptionalFieldsUsesDefaultPlan() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"mai@example.com"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.plan").value("basic"));
    }

    @Test
    void formWithoutEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("plan", "pro"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void jsonWithoutEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"plan":"pro"}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedMediaTypeIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.TEXT_PLAIN)
                .content("email=mai@example.com"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void malformedJsonIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{email:"))
            .andExpect(status().isBadRequest());
    }
}
```

### 6.2. Phân tích kỹ thuật test

**Request form:** `.contentType(APPLICATION_FORM_URLENCODED)` chỉ rõ media type; `.param(...)` thêm tham số vào request MockMvc. Với POST URL-encoded, MockMvc có cơ chế biểu diễn các tham số như form body. Nên kiểm tra snippet `http-request.adoc` để biết byte/request được tài liệu hóa có đúng như client thật không.

**Request JSON:** `.contentType(APPLICATION_JSON)` thiết lập media type; `.content(json)` gửi **chuỗi JSON trong body**. `.param("email", ...)` không thay thế cho JSON body; dùng nhầm `.param(...)` có thể khiến `@RequestBody` không đọc được đối tượng mong đợi.

**Response:** cả hai handler trả cùng cấu trúc JSON, vì thế đều mô tả `responseFields(...)`. Dữ liệu response có thể giống nhau dù format request khác nhau.

**Negative tests:** `formWithoutEmailIsRejected` và `jsonWithoutEmailIsRejected` xác nhận server từ chối cùng một lỗi ở hai cơ chế binding khác nhau; `malformedJsonIsRejected` kiểm tra lỗi cú pháp JSON; `unsupportedMediaTypeIsRejected` gửi `text/plain` nên không khớp một trong hai handler `consumes`.

**Hạn chế của test snippet:** `formParameters(...)`/`requestFields(...)` kiểm tra mô tả cấu trúc nhưng không tự chứng minh email hợp lệ, plan nằm trong tập cho phép, hay giá trị mặc định. Những thông tin đó cần assertion như `jsonPath("$.plan").value("basic")` và test dữ liệu xấu.

### 6.3. Cấu trúc đầu ra

Sau khi hai test có `document(...)` chạy thành công:

```text
build/generated-snippets/
└── registrations/
    ├── form/
    │   ├── form-parameters.adoc
    │   ├── request-headers.adoc
    │   ├── response-fields.adoc
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── json/
        ├── request-fields.adoc
        ├── request-headers.adoc
        ├── response-fields.adoc
        ├── http-request.adoc
        └── http-response.adoc
```

Hai trang request có hai loại bảng **khác nhau**:

| Loại request | Snippet cấu trúc request | Tên/trường ví dụ |
| --- | --- | --- |
| Form URL-encoded | `registrations/form/form-parameters.adoc` | `email`, `plan`, `note` |
| JSON | `registrations/json/request-fields.adoc` | `email`, `plan`, `note` |

Vì cùng tên trường nhưng khác loại body, hãy đặt định danh snippet tách biệt như `registrations/form` và `registrations/json`. Không dùng chung một identifier cho hai test sinh tài liệu khác nhau vì tệp output có thể bị ghi đè và làm mất khả năng đối chiếu chính xác.

## 7. WebTestClient: gửi form và JSON đúng cách

Ví dụ sau giả định `webTestClient` đã gắn cấu hình `WebTestClientRestDocumentation.documentationConfiguration(...)` và các handler WebFlux tương ứng hỗ trợ cả form và JSON. Cách đọc form trong WebFlux thường sử dụng `ServerWebExchange.getFormData()` hoặc binding phù hợp; không mặc định sao chép cách dùng `@RequestParam` của Spring MVC sang handler WebFlux.

### 7.1. Form URL-encoded bằng `BodyInserters.fromFormData`

```java
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

webTestClient.post()
    .uri("/registrations")
    .body(BodyInserters.fromFormData("email", "mai@example.com")
        .with("plan", "pro")
        .with("note", "Xin chào"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-form",
        formParameters(
            parameterWithName("email").description("Email bắt buộc"),
            parameterWithName("plan").optional()
                .description("Gói basic hoặc pro; mặc định basic"),
            parameterWithName("note").optional()
                .description("Ghi chú")
        )
    ));
```

`BodyInserters.fromFormData(...)` giúp tạo form URL-encoded với content type phù hợp. Nếu có nhiều giá trị cùng tên, dùng `MultiValueMap<String, String>`/`LinkedMultiValueMap` và thêm giá trị bằng `add(...)`.

### 7.2. JSON bằng `bodyValue` và `requestFields`

```java
import org.springframework.http.MediaType;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

webTestClient.post()
    .uri("/registrations")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new RegistrationRequest("mai@example.com", "pro", "Xin chào"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-json",
        requestFields(
            fieldWithPath("email").description("Email bắt buộc"),
            fieldWithPath("plan").optional()
                .description("Gói basic hoặc pro; mặc định basic"),
            fieldWithPath("note").optional()
                .description("Ghi chú")
        )
    ));
```

`bodyValue(...)` cần encoder JSON khả dụng trong cấu hình WebTestClient. Nếu muốn kiểm tra rõ chính xác serialized JSON, dùng `http-request.adoc` và các assertion riêng. Dù cùng class `RegistrationRequest`, handler WebFlux vẫn phải được thiết kế để đọc JSON body phù hợp.

## 8. REST Assured: `formParam` so với JSON `body`

REST Assured thường chạy trên HTTP server thực. Giả sử `specification` đã gắn `RestAssuredRestDocumentation.documentationConfiguration(...)` và server đang lắng nghe endpoint.

**Form:**

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

given(specification)
    .filter(document("registrations/rest-assured-form",
        formParameters(
            parameterWithName("email").description("Email bắt buộc"),
            parameterWithName("plan").optional()
                .description("Gói, mặc định basic"),
            parameterWithName("note").optional()
                .description("Ghi chú")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .formParam("plan", "pro")
    .formParam("note", "Xin chào")
    .when().post("/registrations")
    .then().statusCode(201);
```

**JSON:**

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

String json = """
    {"email":"mai@example.com","plan":"pro","note":"Xin chào"}
    """;

given(specification)
    .filter(document("registrations/rest-assured-json",
        requestFields(
            fieldWithPath("email").description("Email bắt buộc"),
            fieldWithPath("plan").optional()
                .description("Gói, mặc định basic"),
            fieldWithPath("note").optional()
                .description("Ghi chú")
        )))
    .contentType(ContentType.JSON)
    .body(json)
    .when().post("/registrations")
    .then().statusCode(201);
```

Trong REST Assured, `formParam(...)` cùng `ContentType.URLENC` tạo dữ liệu biểu mẫu, còn `body(...)` cùng `ContentType.JSON` gửi JSON. Không dùng `formParam(...)` để biểu diễn field JSON. Nếu client có cấu hình serializer đặc biệt, kiểm tra snippet request để xác nhận cấu trúc thực tế.

## 9. Đưa hai kiểu request vào Asciidoctor/Markdown

Một tài liệu rõ ràng cần nói API hỗ trợ cả hai dạng hay chỉ một dạng, và cho ví dụ riêng. Ví dụ trang `src/docs/asciidoc/index.adoc`:

```adoc
= Registrations API

== Tạo đăng ký

Endpoint POST /registrations nhận hai loại request body:
application/x-www-form-urlencoded và application/json.
Response thành công là JSON.

=== Cách 1: URL-encoded form

==== HTTP request
include::{snippets}/registrations/form/http-request.adoc[]

==== Request Content-Type
include::{snippets}/registrations/form/request-headers.adoc[]

==== Form parameters
include::{snippets}/registrations/form/form-parameters.adoc[]

=== Cách 2: JSON body

==== HTTP request
include::{snippets}/registrations/json/http-request.adoc[]

==== Request Content-Type
include::{snippets}/registrations/json/request-headers.adoc[]

==== JSON fields
include::{snippets}/registrations/json/request-fields.adoc[]

=== Response JSON

include::{snippets}/registrations/json/http-response.adoc[]
include::{snippets}/registrations/json/response-fields.adoc[]
```

Biến `{snippets}` phải chỉ tới thư mục gốc snippet, ví dụ `build/generated-snippets`. Tệp sinh được sử dụng làm **nguồn tài liệu**, vì vậy không chỉnh thủ công `form-parameters.adoc` hay `request-fields.adoc` sau khi test.

### 9.1. Nối test với Asciidoctor trong Gradle

Giả định plugin Asciidoctor đã được thêm vào build (Groovy DSL):

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

Khi test thất bại vì body hoặc descriptor không còn khớp, pipeline không nên phát hành trang tài liệu dựa trên snippet cũ. Kiểm tra cả tệp HTML đầu ra và sự tồn tại của các đoạn include, không chỉ tin vào một thư mục snippet từ lần build trước.

### 9.2. Nếu tài liệu chính dùng Markdown

Lệnh `include::{snippets}/...[]` là **cú pháp Asciidoctor**, không phải cú pháp nhúng được hỗ trợ mặc định bởi Markdown renderer. Có thể biên dịch Asciidoctor thành HTML rồi dẫn liên kết từ trang Markdown, hoặc thêm bước chuyển đổi và kiểm tra đầu ra. Điều quan trọng là nội dung bảng vẫn xuất phát từ test HTTP.

## 10. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Endpoint trả `415` | Media type không khớp `consumes` | Kiểm tra `Content-Type` và handler được hỗ trợ |
| Endpoint trả `400` khi gửi JSON | Body JSON lỗi cú pháp, thiếu dữ liệu, hoặc binding/validation từ chối | Kiểm tra JSON thực tế, `@RequestBody`, DTO và lỗi parse |
| JSON gửi đúng tên field nhưng server báo thiếu parameter | Đang gọi handler nhận `@RequestParam`/form mà không có binding phù hợp | Dùng đúng media type/handler hoặc bổ sung mapping JSON |
| Form gửi đúng `.param(...)` nhưng `@RequestBody` không đọc được JSON | Form body khác JSON body | Dùng `.content(...)` với `application/json` cho API JSON |
| `formParameters` không mô tả được JSON | Chọn API tài liệu sai dạng payload | Chuyển sang `requestFields(fieldWithPath(...))` |
| `requestFields` báo không phân tích được form | Body không phải JSON object | Chọn `formParameters(parameterWithName(...))` |
| Client gửi `A+B` nhưng server nhận `A B` | Dấu `+` trong form được hiểu thành khoảng trắng | Mã hóa dấu cộng thực thành `%2B` |
| JSON có array nhưng test tài liệu chỉ mô tả form field | Nhầm danh sách JSON với tên form lặp lại | Mô tả `fieldWithPath("topics")` cùng schema, test JSON array |
| Mô tả `plan` là tùy chọn nhưng server từ chối thiếu | Descriptor `.optional()` không thay đổi controller | Đồng nhất binding, logic default và test hành vi |
| Hai test cùng một identifier `document(...)` | Có nguy cơ ghi đè hoặc trộn snippet | Dùng identifier riêng theo format, chẳng hạn `registrations/form` và `registrations/json` |
| Asciidoctor không thấy snippet | Không chạy test trước hoặc chỉ sai `{snippets}` | Cho `asciidoctor` phụ thuộc `test`, kiểm tra đường dẫn |

**Dữ liệu kiểm thử:** snippet `http-request.adoc` và `curl-request.adoc` có thể hiển thị cả body. Chỉ dùng email, token và nội dung giả; không đưa thông tin cá nhân, mật khẩu hay bí mật thật vào fixture xuất bản.

## 11. Bài tập tự thực hành

Xây dựng `POST /feedback` chấp nhận **hai** định dạng body:

- Với form URL-encoded: `rating` bắt buộc; `comment` tùy chọn; `tags` có thể lặp tên.
- Với JSON: object gồm `rating` (number), `comment` (string tùy chọn), `tags` (array string tùy chọn).
- Server yêu cầu `rating` nằm trong 1–5; nếu có `tags`, mỗi phần tử chỉ có thể là `bug`, `feature` hoặc `docs`.

Thực hiện:

1. Tạo hai handler `consumes` riêng trên cùng đường dẫn, dùng `@RequestParam` và `@RequestBody` phù hợp.
2. Viết MockMvc test form với `tags=bug&tags=docs`; sinh `form-parameters.adoc` và `http-request.adoc`.
3. Viết MockMvc test JSON với `"tags":["bug","docs"]`; sinh `request-fields.adoc` và `http-request.adoc`.
4. Kiểm tra trường hợp thiếu `rating`, `rating=0`, JSON sai kiểu cho `rating`, JSON hỏng cú pháp và `Content-Type: text/plain`.
5. Thử thêm tên form `debug` và JSON field `debug` ngoài tài liệu; quan sát kiểm tra nghiêm ngặt của hai loại snippet.
6. Nhúng các snippet vào hai mục tài liệu Asciidoctor, cấu hình Gradle/CI chạy test trước khi render.

**Tiêu chí đạt:** hai định dạng có HTTP request mẫu đúng kiểu; controller xử lý đúng hợp đồng; `formParameters` và `requestFields` kiểm tra được các descriptor tương ứng; test xác nhận nghiệp vụ; tài liệu được sinh và biên soạn từ chính các bài kiểm thử.

## Tài liệu tham khảo

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Documenting Request and Response Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-headers.html)
- [Spring Framework — Request Body](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Request Parameters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
