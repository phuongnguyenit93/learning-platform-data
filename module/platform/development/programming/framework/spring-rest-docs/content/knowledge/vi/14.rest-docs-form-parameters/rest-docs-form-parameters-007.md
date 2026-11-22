# Đặt tên snippet và phần mô tả form trong Spring REST Docs

## 1. Vì sao tên snippet và mô tả form quan trọng?

Spring REST Docs tạo tài liệu từ các bài kiểm thử HTTP đã chạy. Với endpoint nhận biểu mẫu **application/x-www-form-urlencoded**, hàm **formParameters(...)** sinh bảng tên trường và mô tả của từng parameter. Lệnh **document(...)** xác định **identifier** dùng để nhóm các snippet như request, response, header và form parameters.

Hai lựa chọn này ảnh hưởng trực tiếp đến khả năng bảo trì tài liệu:

- Identifier rõ ràng giúp tìm đúng ví dụ, tách từng use case và tránh ghi đè snippet giữa các test.
- Mô tả parameter rõ ràng cho client biết trường dùng làm gì, có bắt buộc không, định dạng và miền giá trị nào được chấp nhận.
- Cách đặt tên và viết mô tả thống nhất giúp trang Asciidoctor/Markdown dễ đọc, kể cả khi API có nhiều endpoint và nhiều biến thể request.

Trong module **SPRING_REST_DOCS**, mục đích là tạo tài liệu REST API có thể kiểm chứng bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; sau đó biên soạn tài liệu và đưa vào build/CI. Bài học này tập trung vào naming và cách mô tả **form parameters** để người đọc hiểu được hợp đồng HTTP mà bài kiểm thử đã xác nhận.

## 2. Identifier của document(...) là gì?

Khi viết:

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "mai@example.com"))
    .andDo(document("registrations/create-form",
        formParameters(
            parameterWithName("email")
                .description("Email đăng ký; bắt buộc")
        )
    ));
```

Chuỗi **registrations/create-form** là document identifier. Với cấu hình output directory của Spring REST Docs, nó trở thành đường dẫn thư mục con bên dưới thư mục snippet:

```text
build/generated-snippets/
└── registrations/
    └── create-form/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

Tên tệp snippet được quyết định bởi loại snippet; identifier quyết định nhóm thư mục. Ví dụ, **formParameters(...)** tạo **form-parameters.adoc**, còn snippet HTTP request mặc định tạo **http-request.adoc**.

**Identifier không phải URL endpoint, tên method Java hay tên tệp AsciiDoc.** Nó là khóa đặt tên cho bộ snippet của một ví dụ HTTP. Nên đặt có chủ đích, dễ đọc và ổn định.

## 3. Quy tắc đặt tên identifier

### 3.1. Tổ chức theo tài nguyên và hành động

Một quy ước đơn giản:

```text
<resource>/<action>-<request-format>[-<scenario>]
```

Ví dụ:

| Identifier | Mục đích |
| --- | --- |
| registrations/create-form | Tạo đăng ký bằng form URL-encoded |
| registrations/create-json | Tạo đăng ký bằng JSON body |
| registrations/create-form-minimal | Request form tối thiểu, bỏ các trường tùy chọn |
| registrations/create-form-validation-error | Request form không hợp lệ và response lỗi |
| subscriptions/update-form | Cập nhật subscription bằng form |
| uploads/create-multipart | Upload dữ liệu multipart |

Quy ước này khiến cấu trúc thư mục snippet phản ánh tài nguyên và use case, không phụ thuộc tên class test. Khi team đã có chuẩn khác (chẳng hạn api/v1/registrations/create), hãy giữ chuẩn đó nhất quán trong toàn dự án.

### 3.2. Mỗi tình huống có nội dung HTTP riêng nên có identifier riêng

Không nên để hai bài test khác nhau cùng ghi vào **registrations/create-form** nếu mỗi bài tạo ra một request/response khác nhau. Chẳng hạn:

```java
// Test request đầy đủ
document("registrations/create-form",
    formParameters(/* descriptors */));

// Test request tối thiểu
document("registrations/create-form-minimal",
    formParameters(/* cùng hợp đồng nhưng request thiếu field optional */));
```

Nếu identifier trùng, các snippet có cùng tên tệp ở cùng đường dẫn có thể bị ghi đè hoặc tạo ra kết quả khó hiểu tùy cách chạy test và cấu hình build. Một identifier nên đại diện cho **một ví dụ request/response có ý nghĩa cụ thể**.

Không nhất thiết tạo identifier cho mọi test unit. Chỉ test cần sinh tài liệu mới gọi document(...); các test kiểm tra validation phụ trợ có thể xác nhận status/body mà không sinh snippet. Ví dụ, test kiểm tra nhiều biến thể email không hợp lệ không nhất thiết cần nhiều bộ snippet.

### 3.3. Dùng tên ổn định, không nhúng dữ liệu biến động

Tránh identifier phụ thuộc vào email, tên người dùng, ID ngẫu nhiên, timestamp hoặc số thứ tự chạy test. Tên như **registrations/create-form** bền vững và dễ tham chiếu. Nếu cần phân biệt tình huống, dùng từ mô tả scenario như **minimal**, **validation-error**, **with-referral** thay vì giá trị dữ liệu riêng lẻ.

### 3.4. Chọn format trong identifier khi cùng endpoint nhận nhiều body

Một endpoint có thể nhận cả form URL-encoded và JSON nếu controller khai báo các mapping consumes phù hợp. Hãy tách:

```text
registrations/create-form
registrations/create-json
```

Hai bộ snippet khi đó được sinh độc lập:

```text
registrations/
├── create-form/
│   ├── form-parameters.adoc
│   └── http-request.adoc
└── create-json/
    ├── request-fields.adoc
    └── http-request.adoc
```

Form dùng **formParameters(parameterWithName(...))**; JSON dùng **requestFields(fieldWithPath(...))**. Không chia sẻ identifier chỉ vì tên trường giống nhau.

## 4. Viết mô tả cho từng form parameter

### 4.1. Mô tả phải giúp client gửi đúng request

Một descriptor đơn giản:

```java
parameterWithName("email")
    .description("Địa chỉ email dùng để tạo đăng ký; bắt buộc.")
```

Nội dung mô tả nên trả lời những câu hỏi thực tế:

| Thông tin | Câu hỏi của người tích hợp | Ví dụ |
| --- | --- | --- |
| Ý nghĩa | Trường dùng làm gì? | Email nhận thông báo đăng ký |
| Sự hiện diện | Có bắt buộc không? | Bắt buộc; không được để trống |
| Kiểu/format | Gửi định dạng nào? | Email hợp lệ; chuỗi UTF-8 |
| Tập giá trị | Có các lựa chọn nào? | basic hoặc pro |
| Miền giá trị | Giới hạn bao nhiêu? | Số nguyên từ 1 đến 5 |
| Giá trị mặc định | Server làm gì khi bỏ qua? | Mặc định là basic |
| Nhiều giá trị | Có thể lặp tên không? | Gửi topics một lần cho mỗi chủ đề |
| Điều kiện | Có quy tắc đặc biệt nào? | Chỉ gửi khi chọn phương thức nhận email |

Không nhất thiết đưa mọi thông tin vào mọi field. Chỉ đưa những điều quan trọng với client; tránh mô tả chung chung như “email”, “plan” hoặc lặp lại tên parameter mà không giải thích cách dùng.

### 4.2. Mô tả tính bắt buộc và tùy chọn

Spring REST Docs kiểm tra sự hiện diện của tên form parameter dựa trên descriptor. Descriptor không có **optional()** mặc định được xem là bắt buộc trong snippet. Ví dụ:

```java
formParameters(
    parameterWithName("email")
        .description("Địa chỉ email; bắt buộc, không được để trống."),
    parameterWithName("plan")
        .optional()
        .description("Gói đăng ký; có thể bỏ qua, mặc định là basic."),
    parameterWithName("referral")
        .optional()
        .description("Mã giới thiệu; chỉ gửi khi có mã hợp lệ.")
)
```

**optional()** có nghĩa là tham số có thể **vắng mặt trong request dùng để tạo snippet**. Nó không làm controller tự chấp nhận thiếu trường và không tự áp dụng giá trị mặc định. Phải bảo đảm:

1. Binding/validation của server cho phép trường vắng mặt.
2. Test kiểm tra hành vi khi bỏ trường.
3. Description giải thích mặc định hoặc điều kiện liên quan nếu có.

Ngược lại, trường bắt buộc nên không gọi optional(). Nếu request tài liệu hóa thiếu trường đó, Spring REST Docs sẽ báo lỗi khi tạo snippet, qua đó giúp phát hiện request mẫu không thể hiện đúng hợp đồng.

### 4.3. Mô tả tập giá trị và định dạng

Ví dụ:

```java
parameterWithName("plan")
    .description("Gói dịch vụ; chỉ nhận basic hoặc pro.")

parameterWithName("seats")
    .description("Số chỗ đăng ký; số nguyên từ 1 đến 5.")

parameterWithName("startDate")
    .description("Ngày bắt đầu theo ISO-8601, định dạng yyyy-MM-dd.")
```

Description là văn bản hướng dẫn client. Nó **không tự xác thực** tập giá trị, kiểu số hoặc định dạng ngày. Server cần validation tương ứng và test cần kiểm tra trường hợp hợp lệ/không hợp lệ.

Hãy dùng ví dụ bám theo định dạng thật. Nếu server chấp nhận 2026-11-17, đừng mô tả ngày theo 17/11/2026; nếu server chỉ hỗ trợ basic/pro, đừng ghi “các gói tùy ý”.

### 4.4. Mô tả nhiều giá trị cùng tên

Đối với body:

```text
topics=java&topics=spring&topics=rest-docs
```

Chỉ cần một descriptor cho tên topics:

```java
parameterWithName("topics")
    .description("Danh sách chủ đề; lặp lại tên topics cho mỗi mục. " +
                 "Chấp nhận java, spring hoặc rest-docs; tối đa 3 mục.")
```

Không tạo ba descriptor trùng tên để đại diện cho từng giá trị. formParameters(...) mô tả tên parameter; nó không kiểm tra số lượng phần tử, thứ tự hay giá trị trong danh sách. Các quy tắc đó cần validation và test riêng.

### 4.5. Mô tả trường bị bỏ qua có chủ ý

Nếu request có parameter nội bộ mà tài liệu công khai không cần trình bày, có thể dùng:

```java
parameterWithName("internalTrace")
    .ignored()
```

ignored() giúp Spring REST Docs chấp nhận parameter đã khai báo nhưng không đưa nó vào bảng snippet. Chỉ dùng khi có chủ ý rõ ràng; không dùng để che trường API công khai hoặc làm cho test qua dù quên mô tả parameter.

## 5. Ví dụ hoàn chỉnh: đặt tên snippet và mô tả form

### 5.1. Hợp đồng API

Giả sử endpoint POST /registrations nhận:

| Parameter | Quy tắc |
| --- | --- |
| email | Bắt buộc; địa chỉ email hợp lệ |
| plan | Bắt buộc; basic hoặc pro |
| seats | Bắt buộc; số nguyên từ 1 đến 5 |
| referral | Tùy chọn; mã giới thiệu dạng chuỗi |

### 5.2. Controller minh họa

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
            @RequestParam String plan,
            @RequestParam Integer seats,
            @RequestParam(required = false) String referral) {

        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("pro")) {
            return ResponseEntity.badRequest().build();
        }
        if (seats < 1 || seats > 5) {
            return ResponseEntity.badRequest().build();
        }
        // Ví dụ học tập: nghiệp vụ lưu đăng ký được lược bỏ.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Controller được rút gọn để minh họa hợp đồng. Hệ thống production nên dùng Bean Validation hoặc service validation đầy đủ; ví dụ email.contains("@") không phải kiểm tra email hoàn chỉnh.

### 5.3. Test MockMvc và identifier ổn định

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
class RegistrationDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createRegistrationDocumentsFormContract() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("plan", "pro")
                .param("seats", "2")
                .param("referral", "campaign-2026"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-form",
                formParameters(
                    parameterWithName("email")
                        .description("Địa chỉ email hợp lệ; bắt buộc."),
                    parameterWithName("plan")
                        .description("Gói đăng ký; chỉ nhận basic hoặc pro."),
                    parameterWithName("seats")
                        .description("Số chỗ; số nguyên từ 1 đến 5."),
                    parameterWithName("referral")
                        .optional()
                        .description("Mã giới thiệu; có thể bỏ qua.")
                )
            ));
    }

    @Test
    void createRegistrationWithMinimalForm() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("plan", "basic")
                .param("seats", "1"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-form-minimal",
                formParameters(
                    parameterWithName("email")
                        .description("Địa chỉ email hợp lệ; bắt buộc."),
                    parameterWithName("plan")
                        .description("Gói đăng ký; chỉ nhận basic hoặc pro."),
                    parameterWithName("seats")
                        .description("Số chỗ; số nguyên từ 1 đến 5."),
                    parameterWithName("referral")
                        .optional()
                        .description("Mã giới thiệu; có thể bỏ qua.")
                )
            ));
    }
}
```

Hai test dùng hai identifier riêng:

- **registrations/create-form:** request có mã giới thiệu.
- **registrations/create-form-minimal:** request không gửi parameter tùy chọn referral.

Descriptor vẫn khai báo referral là optional trong cả hai trường hợp. Điều này giúp test thứ hai xác nhận chính xác rằng client được phép bỏ qua trường này. Ba trường còn lại không optional, vì vậy request thiếu bất kỳ trường nào sẽ khiến bước document không thành công hoặc server từ chối request.

Các test trên giả định controller không có phụ thuộc service khác. Nếu endpoint có CSRF, xác thực hoặc dependency nghiệp vụ, bổ sung cấu hình/mock phù hợp để test phản ánh đúng luồng HTTP của ứng dụng.

## 6. Tái sử dụng descriptor mà vẫn giữ tên snippet rõ ràng

Khi nhiều kịch bản mô tả cùng một hợp đồng parameter, việc lặp lại descriptor làm tài liệu dễ lệch nhau. Có thể gom cấu hình descriptor thành một hàm dùng chung trong lớp test hoặc test support:

```java
private static ParameterDescriptor[] registrationFormParameters() {
    return new ParameterDescriptor[] {
        parameterWithName("email")
            .description("Địa chỉ email hợp lệ; bắt buộc."),
        parameterWithName("plan")
            .description("Gói đăng ký; chỉ nhận basic hoặc pro."),
        parameterWithName("seats")
            .description("Số chỗ; số nguyên từ 1 đến 5."),
        parameterWithName("referral")
            .optional()
            .description("Mã giới thiệu; có thể bỏ qua.")
    };
}
```

Cần import org.springframework.restdocs.request.ParameterDescriptor. Dùng:

```java
document("registrations/create-form",
    formParameters(registrationFormParameters()));

document("registrations/create-form-minimal",
    formParameters(registrationFormParameters()));
```

formParameters(...) nhận danh sách descriptor cho các tên form parameter. Chỉ tái sử dụng khi hai request có **cùng hợp đồng**. Nếu một biến thể có trường khác, tập giá trị khác hoặc điều kiện optional khác, hãy tạo descriptor riêng hoặc bổ sung rõ sự khác biệt thay vì ép dùng một cấu hình chung.

Đừng biến mô tả thành một chuỗi quá dài chứa mọi quy tắc của endpoint. Có thể chia thông tin:

- Description của parameter: ý nghĩa, format, sự hiện diện và miền giá trị chính.
- Phần giới thiệu trong trang AsciiDoc: quy tắc giữa nhiều trường, điều kiện nghiệp vụ và ví dụ.
- Test riêng: xác nhận các trường hợp biên mà snippet không tự kiểm tra.

## 7. Mô tả form trong trang Asciidoctor

Identifier tạo nên đường dẫn ổn định để nhúng snippet. Ví dụ tệp src/docs/asciidoc/registrations.adoc:

```adoc
= Registration API

== Tạo đăng ký bằng form URL-encoded

Gửi request với Content-Type: application/x-www-form-urlencoded.
Các trường email, plan và seats là bắt buộc.
Trường referral có thể bỏ qua.

=== Request với referral

==== HTTP request
include::{snippets}/registrations/create-form/http-request.adoc[]

==== Form parameters
include::{snippets}/registrations/create-form/form-parameters.adoc[]

==== HTTP response
include::{snippets}/registrations/create-form/http-response.adoc[]

=== Request tối thiểu

Request này không gửi referral.

==== HTTP request
include::{snippets}/registrations/create-form-minimal/http-request.adoc[]

==== Form parameters
include::{snippets}/registrations/create-form-minimal/form-parameters.adoc[]

==== HTTP response
include::{snippets}/registrations/create-form-minimal/http-response.adoc[]
```

Biến {snippets} phải trỏ đến thư mục gốc chứa snippet, ví dụ build/generated-snippets. Các lệnh include::...[] là cú pháp Asciidoctor, không được Markdown renderer thông thường diễn giải tự động. Nếu tài liệu chính là Markdown, có thể liên kết tới HTML do Asciidoctor tạo hoặc thêm bước chuyển đổi được quản lý trong build.

### 7.1. Phân cấp tiêu đề và mô tả

Mỗi section nên có tiêu đề thể hiện một thao tác hoặc một biến thể request:

```text
Registration API
└── Tạo đăng ký bằng form
    ├── Request với referral
    │   ├── HTTP request
    │   ├── Form parameters
    │   └── HTTP response
    └── Request tối thiểu
        ├── HTTP request
        ├── Form parameters
        └── HTTP response
```

Không nên dùng section tên chung chung như “Snippet 1”, “Ví dụ 2”. Tiêu đề tốt giúp độc giả biết họ đang nhìn request nào trước cả khi đọc nội dung code.

### 7.2. Tổ chức đoạn mô tả không trùng lặp

Nên đặt quy tắc chung ở phần đầu endpoint, sau đó để bảng form-parameters.adoc mô tả chi tiết từng trường. Nếu lặp lại toàn bộ quy tắc ở phần giới thiệu, từng parameter và phần ghi chú, trang sẽ dài và khó cập nhật.

Ví dụ, giới thiệu “referral là tùy chọn và chỉ áp dụng khi client có mã giới thiệu hợp lệ”; trong bảng mô tả, ghi “Mã giới thiệu hợp lệ; có thể bỏ qua.” Cả hai bổ trợ nhau nhưng không lặp toàn bộ giải thích.

## 8. Tích hợp build và CI

Với Gradle Groovy DSL và plugin Asciidoctor đã được cài đặt:

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

CI chạy:

```bash
./gradlew test asciidoctor
```

Quan hệ này bảo đảm tài liệu phụ thuộc vào snippet từ test. Khi identifier đổi, cập nhật luôn đường dẫn include::{snippets}/...[]; nếu không, Asciidoctor sẽ không tìm thấy tệp cũ. Một build sạch giúp tránh việc snippet cũ còn sót lại che mất trường hợp test không còn sinh tài liệu.

Nên kiểm tra các điều sau trong pull request:

1. Identifier có mô tả đúng resource, action và định dạng request không?
2. Mỗi kịch bản có identifier riêng nếu request/response khác nhau không?
3. Form parameter bắt buộc/tùy chọn có khớp controller và test không?
4. Description có nêu format, miền giá trị và mặc định đúng thực tế không?
5. Đường dẫn include có trỏ đến đúng identifier không?
6. Test và bước Asciidoctor có chạy trong pipeline CI không?

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippet của test bị ghi đè | Hai test dùng chung identifier và cùng tên snippet | Đặt identifier theo từng kịch bản request |
| Asciidoctor báo không tìm thấy form-parameters.adoc | Identifier trong include sai hoặc test không sinh snippet | Đối chiếu document(...), output directory và đường dẫn include |
| Description chỉ ghi “email” | Không nói ý nghĩa, format, bắt buộc hay tùy chọn | Viết mô tả hướng client gửi request đúng |
| Đánh dấu optional() nhưng controller trả 400 khi thiếu | Descriptor tài liệu không thay đổi hợp đồng server | Đồng bộ binding/validation, test và descriptor |
| Parameter mới tự xuất hiện trong request | Descriptor chưa được cập nhật | Giữ formParameters(...) nghiêm ngặt và mô tả trường mới |
| Dùng ignored() để làm test qua | Che khuất field công khai chưa được tài liệu hóa | Chỉ ignore field nội bộ có quyết định rõ ràng |
| Một descriptor dùng cho nhiều API nhưng description không còn chính xác | Hợp đồng các endpoint đã khác nhau | Tách hàm descriptor theo nhóm hợp đồng |
| Identifier chứa email/ID/timestamp | Đường dẫn output không ổn định và khó tham chiếu | Dùng tên tĩnh theo resource/action/scenario |
| Tài liệu AsciiDoc lặp đoạn mô tả | Quy tắc chung bị viết lại ở nhiều cấp heading | Giữ quy tắc endpoint ở đầu, chi tiết từng field trong bảng |

## 10. Bài tập tự thực hành

Tạo endpoint POST /subscriptions nhận form:

| Parameter | Quy tắc |
| --- | --- |
| email | Bắt buộc, email hợp lệ |
| topics | Bắt buộc, lặp tên 1–3 lần, mỗi giá trị thuộc java, spring, testing |
| frequency | Tùy chọn, weekly hoặc monthly, mặc định weekly |
| referral | Tùy chọn, chuỗi mã giới thiệu |

Thực hiện:

1. Viết controller và test request đầy đủ.
2. Đặt identifier subscriptions/create-form.
3. Viết descriptor với description thể hiện ý nghĩa, tính bắt buộc, giá trị hợp lệ, mặc định và khả năng lặp tên topics.
4. Tạo test request tối thiểu dùng identifier subscriptions/create-form-minimal.
5. Tạo test subscriptions/create-form-invalid cho giá trị frequency không hợp lệ và document response lỗi bằng responseFields(...).
6. Tái sử dụng descriptor chung cho những trường có cùng hợp đồng; không tái sử dụng nếu điều kiện thực tế khác.
7. Nhúng ba bộ snippet vào Asciidoctor và chạy ./gradlew test asciidoctor trong CI.

**Tiêu chí đạt:** identifier dễ hiểu, không đè snippet; bảng form parameters giải thích đủ để client gửi request đúng; description phản ánh hành vi server; tài liệu được biên soạn từ snippet kiểm chứng bởi test.

## Tài liệu tham khảo

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
