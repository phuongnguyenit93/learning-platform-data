# Test là nguồn tạo bằng chứng cho request và response

Một tài liệu REST API viết thủ công có thể mô tả endpoint rất rõ ràng nhưng vẫn sai với ứng dụng đang chạy: mã trạng thái đã đổi, header không còn xuất hiện hoặc JSON có thêm field mà bảng tài liệu chưa cập nhật. Trong **Spring REST Docs**, lời giải là dùng **bài kiểm thử HTTP thực thi được** làm nguồn sinh ví dụ request/response và các bảng mô tả API. Khi triển khai thay đổi, kiểm thử và tài liệu có thể được kiểm tra lại trong cùng quy trình build.

Bài học thuộc chương **Mô hình tài liệu** của module `SPRING_REST_DOCS`. Phạm vi của module là tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh các snippet cho request, response, payload, tham số, header; rồi biên soạn tài liệu Asciidoctor/Markdown trong build và CI. Trọng tâm ở đây là hiểu chính xác **test cung cấp bằng chứng gì, bằng chứng đó được chuyển thành tài liệu ra sao và giới hạn của nó nằm ở đâu**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **quan sát HTTP**, **assertion** và **mô tả hợp đồng** trong một test tạo tài liệu.
2. Viết kiểm thử HTTP vừa xác nhận kết quả vừa tạo snippet Spring REST Docs.
3. Giải thích vì sao snippet request/response có cơ sở kiểm chứng hơn một ví dụ tự gõ, đồng thời chỉ ra điều test **chưa** chứng minh.
4. Tạo test riêng cho tình huống thành công và thất bại, bảo đảm ví dụ không đánh lẫn các response.
5. Tổ chức fixture, assertion, tên operation và CI để tài liệu được tái tạo từ mã nguồn hiện tại.

## 2. “Bằng chứng” trong Spring REST Docs nghĩa là gì?

Xét tài liệu viết tay cho thao tác tạo yêu cầu hỗ trợ:

```http
POST /api/tickets HTTP/1.1
Content-Type: application/json

{"subject":"Không đăng nhập được"}
```

Tác giả có thể tự viết rằng server trả `201 Created`, header `Location` và một JSON gồm `id`, `subject`, `status`. Nếu không chạy test thì đây mới chỉ là **lời khẳng định trong tài liệu**.

Khi dùng Spring REST Docs, test thật sự gửi request đến hệ thống được thiết lập cho kiểm thử, nhận response rồi:

- **Ghi nhận** các dữ kiện HTTP của lần trao đổi (method, URI, header, payload, status).
- **Khẳng định** các hành vi mong đợi bằng assertion (ví dụ: status là `201`, `Location` có giá trị đúng, field `status` bằng `OPEN`).
- **Mô tả** cấu trúc và ý nghĩa của tham số/header/field qua các descriptor (ví dụ: `subject` là chủ đề do người dùng nhập).
- **Sinh snippet** từ operation vừa được kiểm thử để chèn vào tài liệu.

Luồng dữ liệu:

```text
                 Test HTTP có dữ liệu đầu vào xác định
                                  │
                                  ▼
                   Gửi request đến ứng dụng test
                                  │
                                  ▼
                    Nhận HTTP response thực tế
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
          Assertions                          Descriptors
    kiểm tra status/header/JSON          mô tả path, query, payload
                │                                   │
                └─────────────────┬─────────────────┘
                                  ▼
                 Spring REST Docs document(...)
                                  │
                                  ▼
                      generated-snippets/
                       ├─ http-request.adoc
                       ├─ http-response.adoc
                       ├─ request-fields.adoc
                       ├─ response-fields.adoc
                       └─ response-headers.adoc
                                  │
                                  ▼
                  Asciidoctor/Markdown + CI
```

Ba loại thông tin không thể thay thế lẫn nhau:

| Thành phần | Câu hỏi trả lời | Nếu thiếu |
| --- | --- | --- |
| **Request/response được quan sát** | Hệ thống kiểm thử thực sự nhận gì và trả gì? | Ví dụ HTTP có thể chỉ là nội dung đoán hoặc chép lại |
| **Assertion** | Hành vi nào bắt buộc đúng để test được coi là đạt? | Test có thể ghi lại cả response sai mà không phát hiện sai về nghiệp vụ |
| **Descriptor của Spring REST Docs** | Các field/parameter/header có tên, kiểu và ý nghĩa ra sao? | Ví dụ HTTP thiếu diễn giải hợp đồng, khó dùng và khó phát hiện chênh lệch cấu trúc |

**Test vượt qua không có nghĩa là toàn bộ API đã được chứng minh đúng.** Nó chỉ xác nhận những hành vi được kiểm tra trong điều kiện và phạm vi đã thiết lập. Ví dụ test dùng controller giả hoặc service giả chưa kiểm chứng cơ sở dữ liệu, mạng, phân quyền hay cấu hình production.

## 3. Chọn mức kiểm thử: bằng chứng phụ thuộc vào hệ thống được chạy

Spring REST Docs hỗ trợ nhiều cách tạo request/response. Chọn công cụ và phạm vi kiểm thử theo điều muốn chứng minh.

| Cách kiểm thử | Cách chạy request | Có thể xác nhận tốt | Giới hạn cần ghi nhớ |
| --- | --- | --- | --- |
| **MockMvc standalone** | Dựng controller và một phần cấu hình MVC ngay trong test | Mapping, format request/response, logic controller trong cấu hình đã dựng | Không tự bao phủ filter, security, converter hay cấu hình còn lại của ứng dụng |
| **MockMvc với WebApplicationContext** | Chạy qua Spring MVC stack từ context của test | Hành vi HTTP qua cấu hình MVC thực tế hơn, phụ thuộc phạm vi context | Vẫn không mở HTTP server thật; các bean/mock trong context ảnh hưởng kết quả |
| **WebTestClient** | Ràng buộc với ứng dụng in-memory hoặc kết nối server đang chạy | HTTP assertion trên WebFlux/MVC theo cách bind được chọn | Bằng chứng khác nhau giữa chế độ in-memory và network |
| **REST Assured** | Thường gọi HTTP tới server test; cũng có tích hợp test MVC | Request/response qua lớp HTTP thật nếu gọi server thật | Cần quản lý port, dữ liệu, môi trường và vòng đời server |

Vì vậy, câu “tài liệu được sinh từ integration test” chỉ nên dùng khi test thực sự đi qua các thành phần tích hợp mà câu đó hàm ý. Với MockMvc standalone, tài liệu phản ánh hợp đồng được controller thử nghiệm trả về trong cấu hình standalone; điều đó rất hữu ích nhưng phạm vi hẹp hơn một cuộc gọi qua server thật và cơ sở dữ liệu thật.

Mỗi công cụ cũng có cách tích hợp Spring REST Docs riêng. Các ví dụ chi tiết dưới đây sử dụng **MockMvc** vì dễ quan sát cách nối assertion và `document(...)`. Tư duy nguồn bằng chứng, mô tả descriptor và sinh snippet vẫn áp dụng cho WebTestClient và REST Assured.

## 4. Ví dụ thực hành: một hợp đồng API nhỏ, kiểm thử được

Thiết kế API tạo phiếu hỗ trợ:

- `POST /api/tickets` nhận JSON có field `subject`.
- Nếu `subject` không rỗng: trả `201 Created`, header `Location` và JSON của phiếu đã tạo.
- Nếu `subject` rỗng: trả `400 Bad Request` với JSON lỗi.
- Để ví dụ dễ lặp lại, ID được cố định là `501`. Đây là dữ liệu minh họa, không phải cách cấp ID cho hệ thống production.

### 4.1. Controller dùng trong test

```java
@RestController
@RequestMapping("/api/tickets")
class TicketController {

    record CreateTicketRequest(String subject) {}
    record TicketView(long id, String subject, String status) {}
    record ApiError(String code, String message) {}

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<?> create(@RequestBody CreateTicketRequest request) {
        if (request.subject() == null || request.subject().isBlank()) {
            return ResponseEntity.badRequest().body(
                new ApiError(
                    "INVALID_SUBJECT",
                    "subject must not be blank"
                )
            );
        }

        TicketView created =
            new TicketView(501L, request.subject(), "OPEN");

        return ResponseEntity
            .created(URI.create("/api/tickets/501"))
            .body(created);
    }
}
```

Đây là controller tối giản dùng Java `record` (Java 17+) và các lớp Spring Web. Dự án cần các import tương ứng như `java.net.URI`, `RestController`, `RequestMapping`, `PostMapping`, `RequestBody`, `ResponseEntity` và `MediaType`. Controller cố ý không dùng database và xác thực: test bên dưới chỉ chứng minh phản hồi HTTP từ controller cùng cấu hình MockMvc được dựng.

### 4.2. Khởi tạo kiểm thử tài liệu

```java
@ExtendWith(RestDocumentationExtension.class)
class TicketDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new TicketController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    // Các @Test được trình bày ở hai phần tiếp theo.
}
```

`RestDocumentationExtension` kết nối Spring REST Docs với vòng đời JUnit 5; `documentationConfiguration(provider)` gắn công cụ ghi nhận operation vào MockMvc. Khi dùng Spring Boot test hoặc context đầy đủ, cách dựng MockMvc có thể khác, nhưng test vẫn phải có cấu hình để Spring REST Docs ghi request/response và biết nơi xuất snippet.

### 4.3. Test thành công: assertion trước khi tạo snippet

Thêm phương thức sau vào class `TicketDocumentationTest`:

```java
@Test
void createTicket_success() throws Exception {
    mockMvc.perform(
            post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"subject":"Cannot log in"}
                    """)
        )
        .andExpect(status().isCreated())
        .andExpect(
            header().string("Location", "/api/tickets/501")
        )
        .andExpect(
            content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            )
        )
        .andExpect(jsonPath("$.id").value(501))
        .andExpect(
            jsonPath("$.subject").value("Cannot log in")
        )
        .andExpect(jsonPath("$.status").value("OPEN"))
        .andDo(document("tickets-create-success",
            requestHeaders(
                headerWithName("Content-Type")
                    .description("Kiểu JSON của request"),
                headerWithName("Accept")
                    .description("Kiểu response mong đợi")
            ),
            requestFields(
                fieldWithPath("subject")
                    .type(JsonFieldType.STRING)
                    .description("Chủ đề phiếu hỗ trợ")
            ),
            responseHeaders(
                headerWithName("Location")
                    .description("URI của phiếu vừa tạo")
            ),
            responseFields(
                fieldWithPath("id")
                    .type(JsonFieldType.NUMBER)
                    .description("Mã phiếu do server trả về"),
                fieldWithPath("subject")
                    .type(JsonFieldType.STRING)
                    .description("Chủ đề của phiếu"),
                fieldWithPath("status")
                    .type(JsonFieldType.STRING)
                    .description("Trạng thái hiện tại của phiếu")
            )
        ));
}
```

Trong ví dụ, `post` là hàm builder của Spring REST Docs hoặc của Spring MVC Test; vì endpoint này không có biến path nên cả hai cách đều phù hợp cho request này. Các import tĩnh chính:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
```

Các type khác như `MockMvc`, `MockMvcBuilders`, `RestDocumentationContextProvider`, `RestDocumentationExtension` và `JsonFieldType` cần import từ thư viện tương ứng. Ví dụ sử dụng API kiểu Spring REST Docs 3.x, JUnit Jupiter và môi trường Spring/Jackson có hỗ trợ record.

Chính test này xác minh rằng **với request chứa `subject="Cannot log in"`**, controller trả `201`, `Location` và các giá trị JSON cụ thể. Câu khẳng định đó được củng cố bởi assertion thực thi được. Đồng thời, Spring REST Docs tạo snippet chứa mẫu HTTP và bảng mô tả trường.

Định danh `tickets-create-success` chỉ tên một **operation tài liệu**. Không đặt tên theo giá trị ID ngẫu nhiên hoặc dữ liệu phụ thuộc môi trường, vì địa chỉ include của trang tài liệu cần ổn định.

### 4.4. Test thất bại: bằng chứng cho trường hợp 400

Một API có thể trả nhiều response trên cùng method và path. Muốn khẳng định hành vi lỗi thì phải kiểm thử nó:

```java
@Test
void createTicket_invalidSubject() throws Exception {
    mockMvc.perform(
            post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"subject":""}
                    """)
        )
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.code").value("INVALID_SUBJECT")
        )
        .andExpect(
            jsonPath("$.message")
                .value("subject must not be blank")
        )
        .andDo(document("tickets-create-invalid",
            requestFields(
                fieldWithPath("subject")
                    .type(JsonFieldType.STRING)
                    .description(
                        "Chủ đề; không được rỗng hoặc chỉ chứa khoảng trắng"
                    )
            ),
            responseFields(
                fieldWithPath("code")
                    .type(JsonFieldType.STRING)
                    .description("Mã lỗi nghiệp vụ"),
                fieldWithPath("message")
                    .type(JsonFieldType.STRING)
                    .description("Thông báo giải thích lỗi")
            )
        ));
}
```

Hai test dùng cùng endpoint nhưng khác input và điều kiện mong đợi. Do đó, chúng sinh **hai nhóm snippet độc lập**:

```text
generated-snippets/
├── tickets-create-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-fields.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── tickets-create-invalid/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
```

Đây là các file đại diện cần quan sát; ngoài ra Spring REST Docs còn có thể tạo các snippet mặc định như `curl-request.adoc`, `httpie-request.adoc` và body snippet tùy cấu hình. Trường hợp `400` không được mô tả bằng snippet thành công vì body khác nhau và `Location` không xuất hiện.

## 5. Điều nào thực sự được kiểm chứng?

Giả sử test `createTicket_success` chạy qua. Cần đọc kết quả theo hai lớp: **phạm vi chứng minh cụ thể** và **giả định ngoài kiểm thử**.

| Nhận định | Test mẫu có kiểm chứng? | Vì sao? |
| --- | --- | --- |
| Gửi JSON với `subject` hợp lệ được `201` | **Có, trong cấu hình test** | Có `status().isCreated()` |
| Response chứa `Location: /api/tickets/501` | **Có** | Có assertion chính xác trên header |
| JSON có `id = 501` và `status = OPEN` | **Có** | Có các assertion `jsonPath` |
| Request/response trong snippet được lấy từ một lần chạy | **Có** | `document(...)` xử lý operation vừa thực thi |
| Mọi giá trị `subject` hợp lệ luôn tạo được ticket | **Chưa** | Test chỉ dùng một input hợp lệ |
| ID luôn duy nhất khi nhiều client tạo ticket | **Chưa** | Controller mẫu dùng ID cố định |
| Database ghi được dữ liệu chính xác | **Chưa** | Controller không sử dụng database |
| Endpoint được bảo vệ bằng xác thực và phân quyền | **Chưa** | Test chưa dựng security hay danh tính |
| Ứng dụng production trả giống hệt môi trường test | **Chưa được đảm bảo** | Cấu hình, dữ liệu và hạ tầng có thể khác |

Nói cách khác, Spring REST Docs không tự bảo đảm tính đúng đắn của một endpoint: nó **liên kết tài liệu với hành vi quan sát được trong một bộ kiểm thử**, đồng thời hỗ trợ phát hiện khác biệt giữa mô tả và payload đã dùng. Mức độ tin cậy tăng khi bộ test bao phủ đủ tình huống, assertion có ý nghĩa và cấu hình kiểm thử đại diện cho hệ thống cần công bố.

### 5.1. Assertion mạnh hơn chỉ kiểm tra status

Ví dụ sau có thể pass dù server trả dữ liệu sai:

```java
.andExpect(status().isCreated())
.andDo(document("tickets-create-success"))
```

Nếu response body có `"status":"CLOSED"` thay vì `"OPEN"`, kiểm tra status vẫn qua và tài liệu có thể ghi lại JSON sai đó. Vì thế, hãy kiểm tra các field nghiệp vụ quan trọng, không chỉ HTTP status. Khi hợp đồng yêu cầu nội dung header, kiểu media hoặc cấu trúc lỗi, thêm assertion phù hợp.

Đừng biến test thành bản sao của một JSON snapshot lớn không có ý nghĩa nghiệp vụ. Cần ưu tiên những quy tắc công khai và bất biến mà client thực sự dựa vào, đồng thời dùng các descriptor của Spring REST Docs để mô tả cấu trúc.

### 5.2. Descriptor kiểm tra cấu trúc, không kiểm chứng mọi giá trị

Trong chế độ tài liệu hóa field nghiêm ngặt, `requestFields(...)` và `responseFields(...)` có thể làm test lỗi khi payload chứa field chưa được mô tả hoặc thiếu field bắt buộc theo descriptor. Ví dụ, nếu controller trả thêm field `priority` nhưng bộ mô tả response vẫn chỉ gồm `id`, `subject`, `status` thì test tài liệu hóa có thể thất bại và buộc người viết xem lại hợp đồng.

Tuy vậy, `fieldWithPath("status").type(JsonFieldType.STRING)` không khẳng định status phải bằng `OPEN`; cần assertion như `jsonPath("$.status").value("OPEN")`. Mô tả bằng `optional()` khi field thật sự có thể vắng mặt. Dùng `relaxedResponseFields(...)` để chỉ mô tả một phần khi đó là lựa chọn có chủ đích, vì nó không yêu cầu mô tả mọi field trong response.

Các quy tắc phức tạp như format `email`, giới hạn độ dài `subject`, enum `status` hay số tiền phải được kiểm tra bằng assertion/test riêng nếu chúng là một phần hợp đồng.

## 6. Fixture và khả năng lặp lại quyết định chất lượng bằng chứng

Một operation được ghi lại từ test mất giá trị thực tiễn nếu kết quả mỗi lần chạy tùy thuộc dữ liệu cũ trong DB, thứ tự test hoặc dịch vụ ngoài đang không ổn định.

Những thực hành quan trọng:

- **Sắp đặt trạng thái đầu vào:** tạo tài nguyên cần thiết trong fixture, làm rõ quyền của người gọi và các quan hệ dữ liệu.
- **Dùng dữ liệu xác định:** ID, timestamp và chuỗi hiển thị nên cố định hoặc được chuẩn hóa trước khi ghi snippet khi điều đó phù hợp.
- **Độc lập test:** dọn trạng thái đúng phạm vi hoặc dùng transaction/fixture có thể tái tạo, tránh test này phụ thuộc test khác.
- **Không giấu lỗi:** assertion phải thất bại khi hành vi lệch hợp đồng; không thay mọi field bằng matcher quá rộng chỉ để tài liệu sinh thành công.
- **An toàn dữ liệu:** không đưa token thật, cookie phiên, mật khẩu, email người dùng hoặc dữ liệu cá nhân vào snippet sẽ được công bố.

Ví dụ, nếu ứng dụng sinh timestamp ngẫu nhiên, có thể kiểm tra nó theo chuẩn ISO-8601 trong test và chuẩn hóa timestamp trong **bản ví dụ được xuất** bằng preprocessor khi cần ổn định tài liệu. Cần phân biệt **giá trị quan sát thật** với **giá trị đã được thay thế để trình bày**.

### 6.1. Preprocessor không thay assertion

Spring REST Docs hỗ trợ `preprocessRequest(...)`, `preprocessResponse(...)` và các hàm như `prettyPrint()` để làm ví dụ dễ đọc. Chẳng hạn khi thêm đối số preprocessors vào `document(...)`:

```java
.andDo(document("tickets-create-success",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    requestFields(
        fieldWithPath("subject")
            .description("Chủ đề phiếu hỗ trợ")
    ),
    responseFields(
        fieldWithPath("id").description("Mã phiếu"),
        fieldWithPath("subject").description("Chủ đề"),
        fieldWithPath("status").description("Trạng thái")
    )
));
```

Đây là **biến thể minh họa riêng của đoạn `andDo(...)`**, không phải lời mời chèn thêm một `andDo` thứ hai vào cùng test mà không cân nhắc output. Các hàm `preprocessRequest`, `preprocessResponse` và `prettyPrint` được cung cấp bởi `org.springframework.restdocs.operation.preprocess.Preprocessors`.

Dù đã làm đẹp JSON trước khi ghi snippet, cần giữ assertion kiểm tra hành vi thực ở phần test. Nếu lọc hoặc thay header/dữ liệu nhạy cảm để xuất bản, phải làm rõ cách hiển thị này không làm sai yêu cầu thật của client.

## 7. Từ bằng chứng test sang tài liệu Asciidoctor/Markdown

Thư mục snippet của operation thành công có thể được chèn vào trang tài liệu AsciiDoc:

```asciidoc
[[tickets-create]]
=== Tạo phiếu hỗ trợ

Gửi subject để tạo phiếu hỗ trợ mới.
subject bắt buộc là chuỗi không rỗng.

==== Thành công: HTTP 201

.Request
include::{snippets}/tickets-create-success/http-request.adoc[]

.Request fields
include::{snippets}/tickets-create-success/request-fields.adoc[]

.Response
include::{snippets}/tickets-create-success/http-response.adoc[]

.Response headers
include::{snippets}/tickets-create-success/response-headers.adoc[]

.Response fields
include::{snippets}/tickets-create-success/response-fields.adoc[]

==== Dữ liệu không hợp lệ: HTTP 400

.Request
include::{snippets}/tickets-create-invalid/http-request.adoc[]

.Response
include::{snippets}/tickets-create-invalid/http-response.adoc[]

.Error fields
include::{snippets}/tickets-create-invalid/response-fields.adoc[]
```

Attribute `{snippets}` phải được cấu hình trong bước biên soạn Asciidoctor để trỏ đến output của test, thường là `build/generated-snippets` (Gradle) hoặc `target/generated-snippets` (Maven). Các đường dẫn trên mang ý nghĩa: **một phần giải thích tài liệu trỏ tới một nhóm snippet được tạo từ test cụ thể**.

Nếu xuất Markdown, không giả định cú pháp `include::{snippets}/...[]` được trình biên dịch Markdown hiểu; cần công cụ chuyển đổi snippet, một bước include được hỗ trợ hoặc pipeline tạo Markdown thích hợp.

Tài liệu hoàn chỉnh vẫn cần phần diễn giải do tác giả viết, chẳng hạn ai được phép tạo ticket, giới hạn `subject`, ý nghĩa trạng thái và cách xử lý `400`. Một test có thể chứng minh phản hồi của một tình huống; nó không thể tự biết toàn bộ chính sách nghiệp vụ mà chưa được mô tả.

## 8. Build và CI: làm thế nào để bằng chứng không bị cũ?

Một pipeline phù hợp phải tạo lại tài liệu từ các test hiện tại theo thứ tự:

```text
Checkout source sạch
       │
       ▼
Biên dịch + chạy HTTP documentation tests
       │
       ├── Assertion fail? → pipeline fail
       ├── Descriptor fail? → pipeline fail
       └── PASS → generated-snippets/
                       │
                       ▼
             Biên soạn tài liệu
                       │
                       ├── Thiếu include? → báo lỗi
                       └── PASS → xuất HTML/PDF/Markdown
```

Với Gradle, task tạo tài liệu nên phụ thuộc vào task test sinh snippet và khai báo thư mục `generated-snippets` làm input. Với Maven, ràng buộc việc chạy test và plugin biên soạn tài liệu vào lifecycle phù hợp. Nếu test bị bỏ qua nhưng trang vẫn lấy snippet từ lần build trước, kết quả không còn là bằng chứng của mã hiện tại; do đó CI cần chạy từ output sạch và kiểm tra rằng đúng những test tài liệu hóa đang được thực thi.

**Một tiêu chí CI có ích:** khi một thay đổi làm status hoặc field phản hồi không còn khớp hợp đồng được kiểm tra, build phải thất bại ở test hoặc sinh snippet; khi tác giả cập nhật hợp đồng và test, tài liệu phải được sinh lại thành công từ mã mới.

Điểm đáng chú ý là thời điểm **xuất bản** tài liệu nên sau khi test và biên soạn đều thành công. Một file HTML build được riêng lẻ không đủ chứng minh tài liệu đang phản ánh phiên bản code sẽ phát hành.

## 9. Các phản ví dụ: bằng chứng yếu dễ gây hiểu nhầm

| Hiện tượng | Vì sao yếu? | Cách làm tốt hơn |
| --- | --- | --- |
| Test gọi `document(...)` nhưng không có assertion | Có thể chụp lại một response sai | Kiểm tra status, header và các giá trị nghiệp vụ quan trọng |
| Chỉ kiểm tra `status().isOk()` cho GET | Body có thể chứa dữ liệu sai | Thêm `jsonPath`/assertion phù hợp với hợp đồng |
| Dùng mock service trả đúng JSON mong muốn | Chứng minh đường đi ở lớp controller nhưng chưa chứng minh backend thật | Ghi rõ phạm vi và bổ sung integration test khi cần |
| Test thành công được dùng làm tài liệu lỗi | Tình huống và response không khớp | Dùng operation riêng cho `4xx`/`5xx` có ý nghĩa |
| Test dùng dữ liệu ngẫu nhiên, thứ tự chạy khác nhau | Snippet thay đổi thất thường | Cố định fixture, kiểm soát thời gian/ID hoặc chuẩn hóa ví dụ |
| Bảng response field dùng toàn `optional()` | Không phát hiện field bị thiếu theo hợp đồng | Đánh dấu optional chỉ với field thực sự có thể vắng |
| Dùng `relaxedResponseFields` cho toàn bộ API mà không có lý do | Field thêm mới có thể không được tài liệu hóa | Ưu tiên kiểm tra nghiêm ngặt cho schema công khai |
| Tài liệu lấy snippet cũ khi test fail hoặc bị skip | Không có chứng cứ từ commit hiện tại | CI tái tạo snippet và bắt buộc test pass trước khi render |
| Snippet chứa token, host nội bộ hoặc dữ liệu thật | Tài liệu có thể tiết lộ thông tin không nên xuất bản | Dùng fixture an toàn và preprocessor đúng mục đích |

### Khi nào cần thêm test?

Không thể quyết định độ phủ chỉ từ danh sách HTTP status. Nên chọn những **hành vi mà người gọi API cần dựa vào**. Ví dụ với `POST /api/tickets`, nếu API yêu cầu xác thực thì cần test `401`; nếu user không có quyền tạo ticket trong một workspace thì cần test `403`; nếu trường `subject` bị giới hạn độ dài thì cần test ranh giới hợp lệ và không hợp lệ. Các bài test đó chỉ có giá trị khi ứng dụng thật sự hỗ trợ các quy tắc tương ứng.

Bổ sung quá nhiều test chỉ lặp lại cùng một response mà không tăng độ phủ hợp đồng sẽ tạo chi phí duy trì. Hãy ưu tiên tính đại diện, rõ ràng và ý nghĩa của mỗi operation.

## 10. Bài thực hành: kiểm tra “lời khẳng định” bằng test

Một nhóm công bố rằng:

> `POST /api/tickets` với `subject` hợp lệ trả `201`, header `Location` và body chứa trạng thái `OPEN`. Nếu `subject` rỗng, API trả `400` với mã lỗi `INVALID_SUBJECT`.

Hãy biến đoạn mô tả thành bằng chứng có thể tái tạo:

1. Viết hai HTTP test có tên rõ ràng: `createTicket_success` và `createTicket_invalidSubject`.
2. Cho mỗi test chuẩn bị input cố định, gửi request bằng MockMvc và kiểm tra status cùng các giá trị response quan trọng.
3. Gắn `document(...)` với hai identifier khác nhau và các descriptor tương ứng.
4. Chạy test, mở `http-request.adoc` và `http-response.adoc` rồi đối chiếu với assertion.
5. Đưa các snippet vào trang AsciiDoc; đảm bảo cả tình huống `201` và `400` đều có lời giải thích.
6. Thử thay controller để trả `"status":"CLOSED"` khi tạo thành công. Xác nhận test `createTicket_success` phải **thất bại**. Sau đó hoàn tác thay đổi thử nghiệm và chạy lại.
7. Thử thêm một JSON field công khai vào response mà chưa mô tả. Xác nhận cơ chế mô tả field nghiêm ngặt phát hiện sự thiếu đồng bộ; cập nhật test và tài liệu khi đó là thay đổi hợp đồng có chủ đích.

**Tiêu chí hoàn thành:** test bảo vệ được các lời khẳng định công khai quan trọng, mỗi ví dụ xuất bản có nguồn operation xác định, và pipeline có thể tạo lại trang tài liệu từ output sạch.

## 11. Ghi nhớ

- Test là **nguồn bằng chứng cho tương tác HTTP đã chạy**, không phải chứng nhận toàn bộ mọi hành vi của API.
- Request/response được ghi nhận cung cấp dữ liệu thực tế; **assertion** xác nhận kết quả mong đợi; **descriptor** diễn giải và kiểm tra cấu trúc dùng để sinh snippet.
- Một tình huống thành công và một tình huống lỗi là những **operation tài liệu** khác nhau, kể cả khi cùng HTTP method và route.
- Sức mạnh của bằng chứng phụ thuộc **phạm vi test**, fixture, chất lượng assertion và mức bao phủ các quy tắc API.
- Kết nối **test → snippet → Asciidoctor/Markdown → build/CI** giúp phát hiện tài liệu không còn khớp mã hiện tại và tạo ví dụ có thể truy xuất về một bài kiểm thử cụ thể.
