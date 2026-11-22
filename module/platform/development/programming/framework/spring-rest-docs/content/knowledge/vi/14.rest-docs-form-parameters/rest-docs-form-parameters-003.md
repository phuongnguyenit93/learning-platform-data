# Form field bắt buộc và tùy chọn trong Spring REST Docs

## 1. Mục tiêu và bối cảnh

Trong một REST API nhận biểu mẫu, mỗi trường (form field) có thể **bắt buộc** hoặc **tùy chọn**. Đối với người gọi API, phân biệt này quyết định request tối thiểu cần gửi những gì và giá trị mặc định nào được áp dụng nếu bỏ qua một trường. Đối với người viết kiểm thử, nó quyết định các tình huống cần xác minh. Đối với người tạo tài liệu, nó quyết định cấu hình descriptor tương ứng trong Spring REST Docs.

Trong module **SPRING_REST_DOCS**, mục đích là tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**, rồi đưa các snippet request, response, payload, tham số và header vào tài liệu Asciidoctor/Markdown và quy trình build/CI. Riêng chương **Form parameters** này tập trung vào request có body `application/x-www-form-urlencoded`, sử dụng `formParameters(...)` và `parameterWithName(...)` để mô tả hợp đồng của từng trường.

Sau bài học, bạn có thể:

1. Giải thích sự khác biệt giữa trường vắng mặt, trường có giá trị rỗng và trường có giá trị hợp lệ.
2. Phân biệt quy tắc binding/validation của controller với quy tắc kiểm tra snippet trong Spring REST Docs.
3. Dùng `.optional()` đúng chỗ để tài liệu phản ánh một form có trường bắt buộc và tùy chọn.
4. Viết kiểm thử cho request đầy đủ, request tối thiểu và các request không hợp lệ.
5. Sinh snippet `form-parameters.adoc` và đưa nó vào tài liệu được kiểm tra trong CI.

## 2. “Bắt buộc” và “tùy chọn” nằm ở ba lớp khác nhau

Giả sử API đăng ký có ba trường:

| Field | Quy tắc nghiệp vụ | Ví dụ |
| --- | --- | --- |
| `email` | Bắt buộc, không được để trống | `mai@example.com` |
| `plan` | Tùy chọn, mặc định `basic`; nhận `basic` hoặc `plus` | `plus` |
| `displayName` | Tùy chọn; có thể bỏ qua | `Mai Nguyễn` |

Để mô tả chính xác, phải xét ba lớp:

| Lớp | Câu hỏi cần trả lời | Công cụ kiểm chứng |
| --- | --- | --- |
| **Request thực tế** | Tên tham số có nằm trong body form không? Nếu có, giá trị là gì? | HTTP request và snippet `http-request.adoc` |
| **Hợp đồng server** | Thiếu trường có bị từ chối không? Giá trị rỗng/hỏng có được chấp nhận không? Giá trị mặc định là gì? | Controller, validation và các assertion trong test |
| **Hợp đồng tài liệu** | Tên trường được khai báo trong `formParameters(...)` chưa? Nó có thể vắng mặt trong request kiểm thử không? | `parameterWithName(...)`, `.optional()` và kiểm tra snippet của Spring REST Docs |

**Điểm mấu chốt:** `parameterWithName("plan").optional()` chỉ đánh dấu trường là *có thể vắng mặt trong request được dùng để sinh tài liệu*. Nó **không thay đổi** chữ ký controller, không thêm giá trị mặc định và không tự kiểm tra tập giá trị `basic`/`plus`. Những hành vi đó phải được triển khai và kiểm thử ở tầng ứng dụng.

### 2.1. Form field không phải JSON field

Đây là body form URL-encoded:

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&plan=plus&displayName=Mai+Nguy%E1%BB%85n
```

Còn body sau là JSON:

```http
POST /registrations HTTP/1.1
Content-Type: application/json

{"email":"mai@example.com","plan":"plus","displayName":"Mai Nguyễn"}
```

Hai request có thông tin tương tự nhưng cấu trúc khác nhau. Với **form body**, dùng `formParameters(...)`; với **JSON body**, dùng `requestFields(...)`. Còn tham số nằm sau dấu `?` của URL thì dùng `queryParameters(...)`. Không chọn snippet dựa trên tên annotation `@RequestParam` của controller mà bỏ qua vị trí thật của dữ liệu trong HTTP request.

### 2.2. Trường vắng mặt khác trường rỗng

Xét ba form body:

```text
# A: Chỉ có email
email=mai%40example.com

# B: Có displayName nhưng giá trị rỗng
email=mai%40example.com&displayName=

# C: Có displayName là chuỗi chứa dấu cách
email=mai%40example.com&displayName=Mai+Nguy%E1%BB%85n
```

- **A:** `displayName` vắng mặt; một `@RequestParam(required = false) String displayName` thường nhận `null` nếu không có cơ chế cung cấp giá trị khác.
- **B:** `displayName` xuất hiện và có giá trị chuỗi rỗng `""`; điều này không đồng nghĩa với vắng mặt.
- **C:** `displayName` xuất hiện với giá trị `"Mai Nguyễn"` sau giải mã form.

Spring REST Docs có thể mô tả cả ba tình huống nhưng không quyết định chúng hợp lệ về nghiệp vụ hay không. `.optional()` cho phép thiếu tên tham số; nếu muốn **có mặt nhưng không rỗng**, phải kiểm tra điều kiện này ở server và trong test.

Trong Spring MVC, `@RequestParam(defaultValue = "basic")` có thể áp dụng khi tham số thiếu **hoặc** có giá trị rỗng; khai báo giá trị mặc định đồng thời khiến tham số không còn bắt buộc theo binding. Hãy viết test cho cả hai trường hợp nếu API cần phân biệt chúng.

## 3. API Spring REST Docs dành cho form field

Với Spring REST Docs 3.x trở lên, các static import thường dùng:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.relaxedFormParameters;
```

Mô tả ba trường của ví dụ:

```java
formParameters(
    parameterWithName("email")
        .description("Email đăng ký, bắt buộc và không được để trống"),
    parameterWithName("plan")
        .optional()
        .description("Gói basic hoặc plus; mặc định basic"),
    parameterWithName("displayName")
        .optional()
        .description("Tên hiển thị; có thể bỏ qua")
)
```

| API | Ý nghĩa | Điều không được suy diễn |
| --- | --- | --- |
| `parameterWithName("email")` | Khai báo descriptor cho tên form parameter `email`; mặc định được coi là bắt buộc trong kiểm tra snippet | Không xác nhận email hợp lệ hay không rỗng |
| `.description("...")` | Giải thích ý nghĩa, định dạng, tập giá trị, giá trị mặc định | Nội dung mô tả không tự trở thành quy tắc validation |
| `.optional()` | Không báo lỗi snippet khi request dùng để sinh tài liệu không chứa tên tham số này | Không tự thay đổi `@RequestParam` hay logic nghiệp vụ |
| `.ignored()` | Chấp nhận tham số đã khai báo nhưng loại nó khỏi bảng tài liệu | Không nên dùng để che các trường công khai đáng ra phải mô tả |
| `relaxedFormParameters(...)` | Cho phép request có thêm form parameter chưa khai báo descriptor | Không có nghĩa các descriptor bắt buộc đã khai báo được phép vắng mặt |

Ở chế độ `formParameters(...)` thông thường, Spring REST Docs đối chiếu **tập tên tham số** trong request với descriptor:

- **Có tham số trong request, không có descriptor:** thất bại do chưa tài liệu hóa tham số.
- **Có descriptor bắt buộc, thiếu tham số trong request:** thất bại do không tìm thấy tham số đã khai báo.
- **Có descriptor `.optional()`, thiếu tham số trong request:** hợp lệ ở bước kiểm tra snippet.
- **Có descriptor `.ignored()`, tham số có mặt:** không hiển thị descriptor đó trong bảng kết quả.

Kiểm tra của `formParameters` chủ yếu liên quan đến **tên và sự hiện diện**. Nó không đảm bảo kiểu dữ liệu, quy tắc business, biểu thức chính quy hay số lượng phần tử của một trường nhiều giá trị. Những yêu cầu này phải có assertion và validation khác.

## 4. Xây dựng endpoint có trường bắt buộc và tùy chọn

Ví dụ sau dùng Spring MVC. Endpoint `POST /registrations` nhận `application/x-www-form-urlencoded`, luôn đòi hỏi `email` và cho phép bỏ qua `plan`, `displayName`, `tag`. `tag` được phép lặp lại nhiều lần trong body form.

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

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam("email") String email,
            @RequestParam(name = "plan", defaultValue = "basic") String plan,
            @RequestParam(name = "displayName", required = false) String displayName,
            @RequestParam(name = "tag", required = false) List<String> tags) {

        // Đơn giản hóa nghiệp vụ để tập trung vào quy tắc form field.
        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("plus")) {
            return ResponseEntity.badRequest().build();
        }

        // Hệ thống thật sẽ lưu đăng ký, plan, displayName và tags.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Các ý cần phân biệt:

1. `@RequestParam("email")` bắt buộc phải xuất hiện; nếu thiếu, Spring MVC thông thường trả `400 Bad Request` trước khi đi vào phương thức controller. Nếu gửi `email=`, tham số **có mặt** nhưng bị logic `isBlank()` từ chối.
2. `@RequestParam(defaultValue = "basic")` giúp server sử dụng `basic` khi `plan` thiếu hoặc rỗng; vì thế descriptor REST Docs tương ứng phải là `.optional()` nếu test có request bỏ trường đó.
3. `required = false` của `displayName` và `tag` cho phép trường vắng mặt. Với `tag=a&tag=b`, một danh sách nhiều giá trị có thể được binding vào `List<String>`.
4. Ví dụ dùng kiểm tra `email.contains("@")` để minh họa việc từ chối dữ liệu; đây **không phải** bộ kiểm tra cú pháp email đầy đủ. API thực tế cần validation chuẩn và test cụ thể theo hợp đồng của hệ thống.
5. Việc controller trả `201` cho request hợp lệ không chứng minh dữ liệu đã được lưu; phần lưu trữ đang được lược bỏ có chủ đích.

## 5. MockMvc: kiểm thử các trường hợp thực tế và sinh snippet

### 5.1. Cấu hình test

Với ứng dụng dùng Spring Boot 3.x và Gradle Groovy DSL, cần cấu hình kiểm thử tương thích:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Dependency management của dự án cần cung cấp các phiên bản Spring Boot và Spring REST Docs tương thích. Với dự án không dùng Spring Boot, tích hợp `RestDocumentationExtension`/`RestDocumentationContextProvider` và bộ cấu hình MockMvc tương ứng.

### 5.2. Request đầy đủ và request tối thiểu

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

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void fullFormRequestIsDocumented() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .param("email", "mai@example.com")
                .param("plan", "plus")
                .param("displayName", "Mai Nguyễn")
                .param("tag", "java", "spring"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-full",
                formParameters(
                    parameterWithName("email")
                        .description("Email đăng ký; bắt buộc, không rỗng"),
                    parameterWithName("plan")
                        .optional()
                        .description("Gói basic hoặc plus; mặc định basic"),
                    parameterWithName("displayName")
                        .optional()
                        .description("Tên hiển thị; có thể bỏ qua"),
                    parameterWithName("tag")
                        .optional()
                        .description("Nhãn quan tâm; có thể lặp nhiều lần")
                )
            ));
    }

    @Test
    void minimalFormRequestIsDocumented() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-minimal",
                formParameters(
                    parameterWithName("email")
                        .description("Email đăng ký; bắt buộc, không rỗng"),
                    parameterWithName("plan")
                        .optional()
                        .description("Gói basic hoặc plus; mặc định basic"),
                    parameterWithName("displayName")
                        .optional()
                        .description("Tên hiển thị; có thể bỏ qua"),
                    parameterWithName("tag")
                        .optional()
                        .description("Nhãn quan tâm; có thể lặp nhiều lần")
                )
            ));
    }

    @Test
    void missingRequiredEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("plan", "plus"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void blankEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", ""))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownPlanIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("plan", "enterprise"))
            .andExpect(status().isBadRequest());
    }
}
```

**Cách đọc kết quả:**

- Test `fullFormRequestIsDocumented` có đủ bốn tên trường. Dù `plan`, `displayName` và `tag` được đánh dấu `.optional()`, chúng vẫn xuất hiện trong request này. “Tùy chọn” không có nghĩa “không được gửi”.
- Test `minimalFormRequestIsDocumented` chỉ gửi `email`. Ba trường còn lại vắng mặt nhưng không làm `formParameters(...)` thất bại vì đã có `.optional()`.
- Test `missingRequiredEmailIsRejected` chứng minh hành vi của server khi thiếu tên `email`. Không cần cố dùng `formParameters(...)` để tạo snippet thành công từ một request sai hợp đồng của endpoint.
- Test `blankEmailIsRejected` phân biệt trường có mặt với giá trị rỗng. Dù có descriptor cho `email`, REST Docs không tự phát hiện chuỗi rỗng là dữ liệu sai.
- Test `unknownPlanIsRejected` khẳng định quy tắc về tập giá trị cho phép của `plan`. `.description(...)` chỉ mô tả quy tắc này; assertion mới kiểm chứng được hành vi server.

**Lưu ý về kiểm thử:** `.param(...)` của MockMvc biểu diễn tham số request; khi dùng cho POST URL-encoded, hãy kiểm tra snippet `http-request.adoc` để xác minh cách framework dựng HTTP body. Nếu dùng Spring Security có CSRF, request POST có thể cần cấu hình token CSRF hợp lệ. Điều đó là yêu cầu bảo vệ ứng dụng, không phải điều kiện chung của `formParameters(...)`.

### 5.3. Kết quả sinh tài liệu

Khi hai test có `document(...)` thành công, thư mục sinh snippet có cấu trúc tương tự:

```text
build/generated-snippets/
└── registrations/
    ├── create-full/
    │   ├── form-parameters.adoc
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── create-minimal/
        ├── form-parameters.adoc
        ├── http-request.adoc
        └── http-response.adoc
```

Nội dung thông tin của bảng `form-parameters.adoc` bao gồm:

| Parameter | Description |
| --- | --- |
| `email` | Email đăng ký; bắt buộc, không rỗng |
| `plan` | Gói basic hoặc plus; mặc định basic |
| `displayName` | Tên hiển thị; có thể bỏ qua |
| `tag` | Nhãn quan tâm; có thể lặp nhiều lần |

Spring REST Docs dùng template để trình bày snippet. Hãy **ghi rõ sự bắt buộc và tính tùy chọn trong mô tả**, vì người đọc tài liệu không nhất thiết nhìn thấy cách descriptor Java được khai báo trong test.

## 6. Những trường hợp dễ sai

### 6.1. Đánh dấu `.optional()` khi server vẫn yêu cầu tham số

Đây là tình huống tài liệu và server mâu thuẫn:

```java
// Controller: email bắt buộc
@RequestParam("email") String email

// Descriptor lại cho phép email vắng mặt
parameterWithName("email").optional()
    .description("Email đăng ký")
```

REST Docs sẽ không coi sự vắng mặt của `email` là lỗi của snippet, nhưng controller có thể từ chối request `400`. Vì vậy, descriptor nên phản ánh hành vi API đã được kiểm thử. Nếu `email` bắt buộc, **bỏ `.optional()`** và mô tả rõ điều kiện không được rỗng.

### 6.2. Quên `.optional()` đối với trường thực sự có thể vắng mặt

Ví dụ endpoint chấp nhận `plan` vắng mặt, nhưng snippet lại khai báo:

```java
formParameters(
    parameterWithName("email")
        .description("Email bắt buộc"),
    parameterWithName("plan")
        .description("Gói, mặc định basic")
)
```

Khi dùng request chỉ chứa `email`, Spring REST Docs coi `plan` là descriptor bắt buộc và thất bại vì request không có tham số đó. Sửa bằng `.optional()` cho `plan`; không nên sửa test bằng cách thêm `plan=basic` nếu mục tiêu test là chứng minh client được quyền bỏ trường.

### 6.3. Sử dụng `relaxedFormParameters(...)` để che thiếu sót

```java
relaxedFormParameters(
    parameterWithName("email")
        .description("Email đăng ký")
)
```

Biến thể nới lỏng cho phép request có thêm tên tham số chưa được tài liệu hóa. Nó **không giải quyết** trường hợp descriptor `email` bắt buộc nhưng request vắng mặt `email`. Với tài liệu hợp đồng API công khai, nên ưu tiên `formParameters(...)` nghiêm ngặt và dùng `.optional()` theo từng trường có thể vắng mặt.

### 6.4. Nhầm trường vắng mặt, trường rỗng và giá trị mặc định

Giả sử controller dùng `@RequestParam(defaultValue = "basic") String plan`:

| Body form | Giá trị `plan` server nhận (theo binding mặc định Spring MVC) | Đánh giá |
| --- | --- | --- |
| `email=mai%40example.com` | `basic` | `plan` vắng mặt, dùng mặc định |
| `email=mai%40example.com&plan=` | `basic` | `plan` có mặt nhưng rỗng, vẫn dùng mặc định |
| `email=mai%40example.com&plan=plus` | `plus` | `plan` do client cung cấp |
| `email=mai%40example.com&plan=enterprise` | `enterprise` | Controller cần tự từ chối vì không hợp lệ |

Nếu yêu cầu nghiệp vụ là “gửi trường thì tuyệt đối không được rỗng”, không nên chỉ dựa vào `defaultValue`: cơ chế này có thể biến giá trị rỗng thành mặc định, làm mất khả năng phân biệt hai tình huống. Khi cần phân biệt chính xác, hãy thiết kế binding và validation theo yêu cầu rồi tạo test cho cả **thiếu** và **rỗng**.

### 6.5. Một tên trường xuất hiện nhiều lần

Form encoding cho phép:

```text
email=mai%40example.com&tag=java&tag=spring
```

Một descriptor `parameterWithName("tag")` mô tả tên tham số `tag`, cho dù nó xuất hiện một lần hay nhiều lần. Nếu server cho phép bỏ mọi `tag`, đánh dấu descriptor là `.optional()`. Nếu server yêu cầu ít nhất một nhãn, cần validation và test riêng; `formParameters(...)` không tự kiểm tra số lượng giá trị.

### 6.6. Trường bị bỏ qua có chủ ý

Trong một hệ thống có trường nội bộ, có thể dùng:

```java
formParameters(
    parameterWithName("email")
        .description("Email đăng ký"),
    parameterWithName("trackingId")
        .ignored()
)
```

`trackingId` vẫn được nhận diện để kiểm tra tài liệu, nhưng không xuất hiện trong bảng snippet. Chỉ dùng `.ignored()` khi có quyết định rõ ràng về phạm vi công bố; nếu client công khai cần biết tham số này, hãy mô tả thay vì bỏ qua.

## 7. WebTestClient và REST Assured có gì khác?

Với **WebTestClient** và **REST Assured**, cùng nguyên tắc vẫn áp dụng: cần gửi form body chính xác, khai báo `formParameters(...)` trong bước tạo tài liệu, và xác minh status/response. Cách gắn snippet vào bài kiểm thử thay đổi theo thư viện.

### 7.1. WebTestClient

Giả sử `webTestClient` đã gắn cấu hình Spring REST Docs, còn handler WebFlux được cài đặt để đọc form data:

```java
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

webTestClient.post()
    .uri("/registrations")
    .body(BodyInserters.fromFormData("email", "mai@example.com"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-minimal",
        formParameters(
            parameterWithName("email")
                .description("Email bắt buộc"),
            parameterWithName("plan")
                .optional().description("Gói, mặc định basic"),
            parameterWithName("displayName")
                .optional().description("Tên hiển thị"),
            parameterWithName("tag")
                .optional().description("Nhãn quan tâm")
        )
    ));
```

`BodyInserters.fromFormData(...)` tạo body form URL-encoded. Trong Spring WebFlux, việc đọc dữ liệu form có thể dùng `ServerWebExchange.getFormData()` hoặc cơ chế binding phù hợp; không giả định handler WebFlux tự đọc body form thông qua `@RequestParam` giống controller Spring MVC trong ví dụ trước.

### 7.2. REST Assured

Giả sử một HTTP server đang chạy và `specification` đã được cấu hình bằng `RestAssuredRestDocumentation.documentationConfiguration(...)`:

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

given(specification)
    .filter(document("registrations/rest-assured-minimal",
        formParameters(
            parameterWithName("email")
                .description("Email bắt buộc"),
            parameterWithName("plan")
                .optional().description("Gói, mặc định basic"),
            parameterWithName("displayName")
                .optional().description("Tên hiển thị"),
            parameterWithName("tag")
                .optional().description("Nhãn quan tâm")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .when().post("/registrations")
    .then().statusCode(201);
```

`formParam(...)` giúp REST Assured gửi dữ liệu biểu mẫu, còn `ContentType.URLENC` thể hiện `application/x-www-form-urlencoded`. Không dùng `body("{...}")` với JSON rồi mong có một bảng form parameter phù hợp.

## 8. Đưa snippet vào Asciidoctor/Markdown và pipeline CI

Từ test `fullFormRequestIsDocumented`, Spring REST Docs sinh `registrations/create-full/form-parameters.adoc` cùng request và response snippets. Trong trang `src/docs/asciidoc/index.adoc`, có thể nhúng:

```adoc
= Registration API

== Tạo đăng ký

Gửi `Content-Type: application/x-www-form-urlencoded`.

=== Request tối thiểu
include::{snippets}/registrations/create-minimal/http-request.adoc[]

=== Các trường biểu mẫu
include::{snippets}/registrations/create-full/form-parameters.adoc[]

=== Response thành công
include::{snippets}/registrations/create-full/http-response.adoc[]
```

Trong code block trên, thay dấu định dạng nội dòng theo quy ước AsciiDoc của dự án nếu cần; lệnh `include::{snippets}/...[]` mới là phần có ý nghĩa. Biến `{snippets}` phải trỏ tới thư mục gốc của các đoạn sinh, chẳng hạn `build/generated-snippets`.

Với Gradle Groovy DSL có plugin Asciidoctor phù hợp, kết nối các bước:

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

Chạy trong CI:

```bash
./gradlew test asciidoctor
```

Khi server thay đổi tính bắt buộc của field, hãy cập nhật **cả test hành vi lẫn descriptor tài liệu**. Nếu test thất bại, không coi tài liệu từ một lần build cũ là bằng chứng hợp đồng vẫn đúng. Chỉ thị AsciiDoc `include::[]` không được Markdown renderer thông thường xử lý tự động; khi phát hành Markdown cần liên kết tới trang HTML sinh bởi Asciidoctor hoặc có bước chuyển đổi chủ động.

## 9. Bài tập kiểm chứng hiểu biết

Thiết kế API `POST /feedback` nhận form URL-encoded với:

- `rating`: bắt buộc, số nguyên từ 1 đến 5.
- `comment`: tùy chọn, nhưng nếu gửi thì không được chỉ gồm khoảng trắng.
- `nickname`: tùy chọn, mặc định `anonymous` khi vắng mặt.
- `category`: tùy chọn, có thể lặp tên để gửi nhiều mục.

Thực hiện lần lượt:

1. Tạo controller với binding và validation thể hiện chính xác quy tắc trên.
2. Viết test request đầy đủ và request tối thiểu; dùng `formParameters(...)` cùng `parameterWithName(...)`/`.optional()` để tạo hai snippet.
3. Gửi form thiếu `rating` và xác minh phản hồi lỗi. Lặp lại với `rating=0`, `rating=abc`, `comment=+++` và `comment=`; giải thích khác biệt giữa thiếu field, sai kiểu và giá trị rỗng.
4. Thử bỏ `.optional()` của `nickname` khi chạy test tối thiểu; quan sát lỗi Spring REST Docs và sửa lại descriptor.
5. Thêm một tên tham số chưa có trong descriptor, so sánh `formParameters(...)` với `relaxedFormParameters(...)`, giải thích vì sao chế độ nghiêm ngặt thường phù hợp với tài liệu công khai.
6. Nhúng bảng `form-parameters.adoc` vào Asciidoctor; cấu hình CI chạy test trước tác vụ tạo tài liệu.

**Tự kiểm tra:** “Một form field là tùy chọn” có nghĩa là **server chấp nhận việc không có field ấy theo hợp đồng API**. Để tài liệu đáng tin cậy, điều đó cần được phản ánh đồng thời trong cấu hình binding/validation, test HTTP và `.optional()` của Spring REST Docs.

## Tham khảo

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
