# Document response payload bằng `responseFields`

## 1. Mục tiêu và vai trò của `responseFields`

Trong **Spring REST Docs**, `responseFields(...)` mô tả cấu trúc dữ liệu trả về của một REST API ngay trong bài kiểm thử HTTP. Mỗi trường được khai báo bằng `fieldWithPath(...)` cùng phần giải thích có ý nghĩa với người dùng API. Khi kiểm thử chạy thành công, Spring REST Docs sinh ra **snippet** `response-fields.adoc` để nhúng vào tài liệu Asciidoctor.

Cách tiếp cận này giúp tài liệu bám sát hành vi đã được kiểm thử:

- Phần mô tả trường nằm cạnh kiểm thử của endpoint, thuận tiện cập nhật khi hợp đồng API thay đổi.
- Ở chế độ mặc định, trường thực tế xuất hiện trong response nhưng chưa được mô tả hoặc trường bắt buộc đã khai báo nhưng không xuất hiện có thể khiến bước sinh tài liệu thất bại.
- Cùng một response có thể được kiểm tra về HTTP status, nội dung và cấu trúc tài liệu trong một lần chạy.
- Snippet được tái sử dụng trong tài liệu tổng hợp và trong quy trình build/CI.

`responseFields` là công cụ **mô tả và xác minh các trường payload tại thời điểm kiểm thử**. Nó không thay thế các assertion về nghiệp vụ, phân quyền, định dạng đặc biệt hay toàn bộ ràng buộc của schema. Ví dụ, muốn bảo đảm `available` là `true` hoặc `id` có giá trị cụ thể thì cần thêm assertion của MockMvc.

## 2. Ví dụ response cần tài liệu hóa

Giả sử endpoint `GET /api/books/42` trả HTTP `200 OK` với JSON:

```json
{
  "id": 42,
  "title": "Spring REST Docs",
  "available": true,
  "authors": [
    {
      "id": 7,
      "name": "Nguyễn An"
    }
  ],
  "tags": ["spring", "documentation"]
}
```

Ta muốn xuất tài liệu cho năm nhóm thông tin: `id`, `title`, `available`, danh sách `authors` với các trường trong từng phần tử, và mảng `tags`. Đường dẫn đến trường lồng nhau hoặc phần tử mảng phải phản ánh **JSON thực tế sau khi serialization**, không chỉ tên thuộc tính trong lớp Java.

## 3. Viết bài kiểm thử MockMvc sinh `response-fields.adoc`

Ví dụ sau dùng JUnit Jupiter, MockMvc và Spring REST Docs. Dự án cần các thư viện kiểm thử Spring MVC/JUnit và dependency `spring-restdocs-mockmvc`; mẫu dùng Java 17+ vì có `record`. `standaloneSetup` tạo controller đơn giản để bài học tập trung vào việc tài liệu hóa response.

```java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookResponseDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetBookResponse() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.authors[0].id").value(7))
                .andDo(document("books-get",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã định danh của sách"),
                                fieldWithPath("title")
                                        .description("Tên sách"),
                                fieldWithPath("available")
                                        .description("Sách có đang sẵn để sử dụng hay không"),
                                fieldWithPath("authors")
                                        .description("Danh sách tác giả"),
                                fieldWithPath("authors[].id")
                                        .description("Mã định danh của từng tác giả"),
                                fieldWithPath("authors[].name")
                                        .description("Tên của từng tác giả"),
                                fieldWithPath("tags")
                                        .description("Các nhãn phân loại sách")
                        )
                ));
    }

    @RestController
    static class BookController {
        @GetMapping(value = "/api/books/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        BookResponse getBook(@PathVariable long id) {
            return new BookResponse(
                    id,
                    "Spring REST Docs",
                    true,
                    List.of(new Author(7L, "Nguyễn An")),
                    List.of("spring", "documentation")
            );
        }
    }

    record Author(long id, String name) {}

    record BookResponse(long id, String title, boolean available,
                        List<Author> authors, List<String> tags) {}
}
```

**Diễn giải các phần quan trọng:**

1. `documentationConfiguration(restDocumentation)` gắn cơ chế ghi nhận HTTP exchange vào MockMvc; `RestDocumentationExtension` quản lý ngữ cảnh tài liệu cho từng kiểm thử.
2. `document("books-get", ...)` đặt định danh cho bộ snippet của hoạt động HTTP. Tên này trở thành thư mục con trong thư mục generated snippets.
3. `responseFields(...)` nhận các `FieldDescriptor` mô tả payload của **response**; đường dẫn `authors[].id` được áp dụng cho trường `id` trong các đối tượng thuộc mảng `authors`.
4. `andExpect(...)` kiểm tra kết quả HTTP và dữ liệu nghiệp vụ. `andDo(document(...))` sinh snippet từ exchange đã thực hiện.

Trong dự án thực tế, có thể dùng `@SpringBootTest`/`@AutoConfigureMockMvc` hoặc `@WebMvcTest` với cấu hình REST Docs tương ứng, thay vì khai báo controller trực tiếp trong lớp kiểm thử. Với WebTestClient và REST Assured, nguyên lý mô tả `fieldWithPath` là tương tự nhưng cách nối thao tác `document(...)` vào kiểm thử khác theo từng thư viện.

## 4. Đọc và thiết kế đường dẫn JSON

`fieldWithPath` sử dụng cú pháp đường dẫn trường của Spring REST Docs. Với JSON, có thể mô tả object lồng nhau, mảng object và mảng kiểu nguyên thủy.

| Payload ví dụ | Descriptor | Ý nghĩa |
| --- | --- | --- |
| `{"id":42}` | `fieldWithPath("id")` | Trường ở cấp gốc |
| `{"publisher":{"name":"A"}}` | `fieldWithPath("publisher.name")` | Thuộc tính bên trong object |
| `{"authors":[{"id":7}]}` | `fieldWithPath("authors[].id")` | Trường trong mỗi object thuộc mảng |
| `{"tags":["spring","java"]}` | `fieldWithPath("tags")` | Mô tả cả mảng các giá trị |
| `{"items":[{"sku":"B-1"}]}` | `fieldWithPath("items[].sku")` | Cấu trúc phần tử của danh sách |

Một số nguyên tắc khi lựa chọn descriptor:

- Dùng `fieldWithPath("authors")` để mô tả ý nghĩa của cả mảng và `fieldWithPath("authors[].id")`/`fieldWithPath("authors[].name")` để công bố cấu trúc từng phần tử khi người tích hợp cần biết chi tiết.
- Với mảng giá trị đơn giản như `tags`, mô tả cả mảng thường là đủ. Khi cần làm rõ ý nghĩa hoặc kiểu phần tử, bổ sung thông tin trong `description`.
- Trong response phân trang, các đường dẫn thường có dạng `content[].id`, `content[].title`, `page.totalElements`, `page.totalPages`; tên thực tế phải lấy từ JSON được trả về.
- Nếu fixture dùng để sinh tài liệu chứa mảng rỗng, các đường dẫn đến phần tử như `authors[].id` có thể không tìm thấy và làm kiểm thử thất bại. Hãy sử dụng response mẫu có phần tử đại diện hoặc thiết kế bộ kiểm thử riêng cho trường hợp mảng rỗng.

Để tài liệu rõ ràng, phần mô tả nên diễn đạt **ý nghĩa và hợp đồng sử dụng**: ví dụ `available` nghĩa là gì, khi nào giá trị thay đổi, hoặc `tags` phục vụ tìm kiếm/lọc như thế nào; tránh chỉ lặp lại tên trường.

## 5. Trường tùy chọn, trường bỏ qua và kiểu dữ liệu

Payload thực tế thường có các trường vắng mặt tùy ngữ cảnh hoặc có dữ liệu kỹ thuật không cần đưa vào bảng tài liệu. Spring REST Docs hỗ trợ các tùy chọn trên descriptor:

```java
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("subtitle")
        .optional()
        .type(JsonFieldType.STRING)
        .description("Phụ đề; có thể không được trả về"),

fieldWithPath("internalTraceId")
        .optional()
        .ignored()
```

Các descriptor trên là **đoạn minh họa bên trong danh sách đối số** của `responseFields(...)`, không phải một chương trình Java độc lập.

| Khai báo | Hành vi cần hiểu |
| --- | --- |
| `.description("...")` | Nội dung giải thích được đưa vào snippet |
| `.optional()` | Cho phép trường được khai báo vắng mặt trong response đang kiểm thử |
| `.ignored()` | Trường được phép xuất hiện nhưng không hiển thị trong bảng tài liệu |
| `.type(JsonFieldType.STRING)` | Chỉ định kiểu trường được trình bày, hữu ích khi khó suy ra kiểu từ dữ liệu mẫu như giá trị `null` |

**Lưu ý:** `optional()` mô tả khả năng **thiếu trường**, khác với khẳng định một trường được trả về có giá trị `null`. `ignored()` cần được dùng có chủ đích vì một trường bỏ qua sẽ không còn được người đọc nhìn thấy trong snippet. Cần viết assertion riêng cho các điều kiện nghiệp vụ hoặc quy tắc kiểu dữ liệu quan trọng, thay vì chỉ dựa vào bảng trường được sinh.

## 6. Chế độ nghiêm ngặt, `relaxedResponseFields` và subsection

Theo mặc định, `responseFields(...)` áp dụng việc kiểm tra chặt chẽ: các trường payload chưa được tài liệu hóa có thể khiến kiểm thử thất bại. Đây là cơ chế hữu ích để phát hiện API phát sinh thêm trường nhưng nhóm phát triển chưa cập nhật tài liệu.

Khi chỉ muốn mô tả một phần response trong giai đoạn chuyển tiếp, có thể dùng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
        fieldWithPath("id").description("Mã định danh của sách"),
        fieldWithPath("title").description("Tên sách")
)
```

`relaxedResponseFields(...)` bỏ qua **các trường ngoài danh sách mô tả** khi xác minh tài liệu, nhưng descriptor bắt buộc đã khai báo vẫn phải khớp với payload. Chỉ nên dùng khi có lý do rõ ràng: đổi lấy sự linh hoạt là nguy cơ không phát hiện trường mới được thêm vào API.

Nếu một nhánh JSON là cấu trúc lớn được mô tả ở một tài liệu riêng, có thể tài liệu hóa nhánh đó như một subsection:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
        fieldWithPath("id").description("Mã định danh của sách"),
        fieldWithPath("title").description("Tên sách"),
        fieldWithPath("available").description("Trạng thái sẵn có"),
        subsectionWithPath("authors")
                .description("Danh sách tác giả (xem tài liệu chi tiết)"),
        fieldWithPath("tags").description("Nhãn phân loại")
)
```

`subsectionWithPath("authors")` xem nhánh `authors` và các trường bên dưới là một phần đã được mô tả. Chỉ dùng cách này khi tài liệu của endpoint không cần công bố chi tiết từng phần tử của nhánh đó.

## 7. Sinh snippet và đưa vào Asciidoctor

Sau khi kiểm thử chạy thành công, Spring REST Docs tạo các tệp trong thư mục generated snippets. Với bố cục Gradle thông dụng, đường dẫn của ví dụ là:

```text
build/generated-snippets/
└── books-get/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

Các snippet khác có thể được tạo tùy cấu hình mặc định và cách gọi `document(...)`; danh sách trên tập trung vào các tệp liên quan của ví dụ. Với Maven, thư mục đầu ra thông dụng là `target/generated-snippets`. Vị trí chính xác có thể được tùy chỉnh trong cấu hình kiểm thử/build.

`response-fields.adoc` chứa bảng mô tả đường dẫn, kiểu dữ liệu và phần diễn giải từ các `FieldDescriptor`. Tài liệu Asciidoctor có thể nhúng snippet bằng:

```adoc
= Book API
:snippets: build/generated-snippets

== Lấy chi tiết sách

=== Response ví dụ
include::{snippets}/books-get/http-response.adoc[]

=== Các trường trong response
include::{snippets}/books-get/response-fields.adoc[]
```

Giá trị thuộc tính `snippets` phải trỏ đúng đến nơi build tạo snippet. Trong quy trình build/CI, cần chạy kiểm thử sinh snippet **trước** bước Asciidoctor hoặc bước đóng gói tài liệu. Nếu kiểm thử HTTP hoặc bước sinh tài liệu thất bại, pipeline cần trả lỗi thay vì xuất bản tài liệu cũ.

Markdown cũng có thể được sử dụng để biên soạn tài liệu ở lớp xuất bản, nhưng ví dụ `response-fields.adoc` là snippet Asciidoctor mặc định. Muốn tạo nội dung Markdown trực tiếp cần cấu hình template/đầu ra phù hợp, không chỉ đổi phần mở rộng tệp.

## 8. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Kiểm thử báo có trường chưa được mô tả | Response có thuộc tính mới mà danh sách `responseFields` chưa bao phủ | Bổ sung descriptor có ý nghĩa, hoặc chủ động `.ignored()` nếu đúng hợp đồng |
| Kiểm thử báo không tìm thấy trường đã khai báo | Sai JSON path, khác quy tắc serialization, trường không có trong fixture | Xem JSON thực tế, sửa path; dùng `.optional()` nếu hợp đồng cho phép thiếu |
| Mảng object không tạo được bảng trường con | Fixture trả mảng rỗng nên không có `items[].id`, `items[].name` | Sử dụng fixture có ít nhất một phần tử khi sinh tài liệu cấu trúc |
| Bảng hiển thị kiểu không phù hợp hoặc khó xác định | Dữ liệu mẫu thiếu, chỉ có `null`, hoặc mô tả không khớp kiểu JSON | Bổ sung fixture đại diện; cân nhắc `.type(JsonFieldType...)` và assertion kiểu riêng |
| Không thấy `response-fields.adoc` | Chưa chạy kiểm thử, không gọi `document(...)`, hoặc cấu hình thư mục chưa đúng | Kiểm tra kiểm thử đã chạy thành công và đường dẫn generated snippets |
| Asciidoctor báo lỗi `include` | Thuộc tính `snippets` trỏ sai hoặc task tạo tài liệu chạy trước task kiểm thử | Sửa đường dẫn và thứ tự/phụ thuộc tác vụ build |

Một số lớp Java dùng `@JsonProperty`, naming strategy, `@JsonInclude` hoặc DTO tùy theo trạng thái nghiệp vụ. Những yếu tố này có thể thay đổi **JSON thực gửi tới client**. Luôn bám vào response thực tế do MockMvc/WebTestClient/REST Assured ghi nhận để cập nhật `fieldWithPath`.

## 9. Thực hành kiểm chứng hợp đồng response

Với endpoint `GET /api/books/42`, hãy thử các thay đổi sau theo thứ tự:

1. Thêm trường `isbn` vào JSON trả về nhưng chưa bổ sung descriptor. Quan sát lỗi của `responseFields(...)` ở chế độ nghiêm ngặt.
2. Bổ sung `fieldWithPath("isbn").description("Mã ISBN của sách")`; chạy lại kiểm thử và xem bảng trường mới được sinh.
3. Cho trường `subtitle` xuất hiện ở một số response và biến mất ở các response khác. Khai báo `.optional()` theo đúng hợp đồng, đồng thời giữ assertion cho các trường bắt buộc.
4. Thử response với `authors: []` để thấy tác động đến các descriptor `authors[].id` và `authors[].name`. Xây fixture đại diện cho bài kiểm thử sinh tài liệu.
5. Nhúng `response-fields.adoc` vào một trang Asciidoctor và chạy pipeline kiểm thử → tạo tài liệu, xác minh bảng được cập nhật sau khi sửa cấu trúc response.

**Tiêu chí hoàn thành:** kiểm thử xác nhận status và các giá trị quan trọng; tất cả trường public trong fixture được mô tả phù hợp; trường tùy chọn/được bỏ qua có chủ đích; snippet được sinh đúng thư mục; tài liệu tổng hợp lấy nội dung từ snippet mới nhất. Đây là nền tảng để duy trì REST API documentation có thể kiểm chứng cùng với mã nguồn Spring.
