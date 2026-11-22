# Document request payload bằng `requestFields`

## 1. Vì sao cần tài liệu hóa request payload từ bài kiểm thử?

Khi một API nhận JSON, chỉ ghi ví dụ request trong tài liệu là chưa đủ: ví dụ có thể lỗi thời sau khi controller hoặc DTO thay đổi. **Spring REST Docs** giải quyết vấn đề này bằng cách sinh tài liệu từ các bài kiểm thử HTTP chạy thật. Nếu bài kiểm thử không vượt qua được các kỳ vọng về request/response hoặc mô tả payload không phù hợp với dữ liệu mẫu, quá trình sinh tài liệu sẽ thất bại. Nhờ đó, tài liệu và hành vi được kiểm thử có một điểm kiểm chứng chung.

Trong chương **Request payload**, `requestFields(...)` là công cụ trọng tâm để mô tả các trường của phần thân request, đặc biệt là **JSON request body**. Ta có thể sử dụng nó với MockMvc, WebTestClient hoặc REST Assured thông qua tích hợp Spring REST Docs tương ứng.

Sau bài này, bạn có thể:

- Xác định đường dẫn các trường JSON, kể cả object lồng nhau và phần tử của mảng.
- Viết bài kiểm thử MockMvc vừa kiểm tra API vừa sinh snippet `request-fields.adoc`.
- Phân biệt trường bắt buộc trong tài liệu, trường tùy chọn, trường bị bỏ qua và tài liệu hóa linh hoạt.
- Đưa snippet vào tài liệu Asciidoctor và chuỗi build/CI để tránh tài liệu cũ.

## 2. `requestFields` mô tả điều gì?

Giả sử hệ thống có API `POST /api/orders` với request mẫu:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 42,
  "items": [
    { "sku": "BOOK-001", "quantity": 2 },
    { "sku": "PEN-002", "quantity": 1 }
  ],
  "note": "Giao trong giờ hành chính"
}
```

Ta muốn tạo bảng tài liệu có nội dung tương đương:

| Đường dẫn trường | Kiểu JSON | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `customerId` | Number | Có | Mã khách hàng đặt hàng |
| `items` | Array | Có | Danh sách mặt hàng |
| `items[].sku` | String | Có | Mã sản phẩm của từng mặt hàng |
| `items[].quantity` | Number | Có | Số lượng của từng mặt hàng |
| `note` | String | Không | Ghi chú giao hàng |

Spring REST Docs tạo các mô tả này bằng `PayloadDocumentation.requestFields(...)` kết hợp những `FieldDescriptor` sinh từ `fieldWithPath(...)`.

Trong **chế độ chặt chẽ** của `requestFields`, quá trình tạo snippet thất bại khi request mẫu chứa trường không được tài liệu hóa hoặc thiếu một trường đã được khai báo là bắt buộc trong tài liệu. Các trường `optional()` được phép vắng mặt; các trường `ignored()` được nhận diện nhưng không xuất hiện trong bảng tài liệu. Cần lưu ý: tài liệu hóa **một object hoặc mảng ở cấp cha** có thể làm các trường con được xem là đã bao phủ, nên muốn kiểm soát chi tiết cấu trúc thì cần khai báo cả các trường con quan trọng.

`requestFields` kiểm tra **mức độ bao phủ của tài liệu đối với payload được gửi trong bài kiểm thử**. Nó không thay thế Bean Validation, kiểm thử nghiệp vụ hay một trình kiểm tra JSON Schema toàn diện. Ví dụ, `.type(JsonFieldType.NUMBER)` xác định kiểu hiển thị trong snippet; không nên coi nó là một phép xác thực kiểu dữ liệu đầu vào độc lập.

## 3. Chuẩn bị Spring REST Docs với MockMvc

Đối với dự án Spring Boot sử dụng Gradle và MockMvc, cần có dependency kiểm thử Spring REST Docs cùng bộ kiểm thử Spring Boot (phiên bản thực tế do dự án hoặc BOM quản lý):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Trong dự án Spring Boot 3.x, có thể cấu hình bài kiểm thử bằng `@SpringBootTest`, `@AutoConfigureMockMvc` và `@AutoConfigureRestDocs`. Ví dụ bên dưới giả định endpoint `POST /api/orders` đã được triển khai và trả HTTP `201 Created` cho payload hợp lệ. Hãy điều chỉnh đường dẫn, dữ liệu và mã trạng thái theo API thật của bạn.

## 4. Viết bài kiểm thử tài liệu hóa request bằng `requestFields`

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderApiDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateOrderRequest() throws Exception {
        String requestBody = """
                {
                  "customerId": 42,
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 },
                    { "sku": "PEN-002", "quantity": 1 }
                  ],
                  "note": "Giao trong giờ hành chính"
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestBody))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(
                                fieldWithPath("customerId")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Mã khách hàng đặt hàng"),
                                fieldWithPath("items")
                                        .type(JsonFieldType.ARRAY)
                                        .description("Danh sách mặt hàng"),
                                fieldWithPath("items[].sku")
                                        .type(JsonFieldType.STRING)
                                        .description("Mã sản phẩm"),
                                fieldWithPath("items[].quantity")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Số lượng đặt"),
                                fieldWithPath("note")
                                        .type(JsonFieldType.STRING)
                                        .description("Ghi chú giao hàng")
                                        .optional()
                        )
                ));
    }
}
```

Luồng thực thi của bài kiểm thử:

1. MockMvc gửi HTTP request chứa JSON thực tế tới ứng dụng Spring được khởi tạo cho kiểm thử.
2. `andExpect(status().isCreated())` xác nhận API trả mã trạng thái mong đợi.
3. `document("orders-create", ...)` chọn tên thư mục snippet; `requestFields(...)` cung cấp danh sách trường cần mô tả.
4. Nếu kiểm thử và phần tài liệu hóa đều thành công, Spring REST Docs sinh snippet trong `build/generated-snippets/orders-create/`.

Các tệp thông thường bao gồm `http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, `httpie-request.adoc` và, do đã khai báo `requestFields`, **`request-fields.adoc`**. Danh sách chính xác phụ thuộc cấu hình snippets của dự án. Nội dung `request-fields.adoc` là bảng mô tả các trường dựa trên `FieldDescriptor` của bài kiểm thử.

### Cấu trúc đường dẫn trường

| Cấu trúc JSON | Cú pháp đường dẫn | Ghi chú |
| --- | --- | --- |
| `{ "email": "a@example.com" }` | `email` | Trường cấp gốc |
| `{ "address": { "city": "Hà Nội" } }` | `address.city` | Trường trong object lồng nhau |
| `{ "tags": ["java", "spring"] }` | `tags` hoặc `tags[]` | `tags` mô tả cả mảng; `tags[]` mô tả phần tử |
| `{ "items": [{ "sku": "A" }] }` | `items[].sku` | Trường `sku` trong từng object của mảng |
| `{ "groups": [["a", "b"]] }` | `groups[][]` | Phần tử trong mảng lồng mảng |

Khi viết descriptor cho `items[].sku`, nên có ít nhất một phần tử `items` trong request mẫu để trường thực sự xuất hiện và được kiểm chứng. Với danh sách rỗng, các descriptor trường con bắt buộc có thể bị xem là không có dữ liệu tương ứng. Hãy thiết kế test cho trường hợp danh sách rỗng riêng, phù hợp với quy tắc API.

## 5. Điều khiển cách tài liệu hóa từng trường

### 5.1. Trường tùy chọn: `optional()`

```java
fieldWithPath("note")
        .type(JsonFieldType.STRING)
        .description("Ghi chú giao hàng, có thể bỏ qua")
        .optional()
```

Khai báo này cho phép **request mẫu không chứa** `note` mà việc sinh snippet vẫn thành công. Nó phản ánh rằng phía người gọi được phép không truyền trường, theo hợp đồng API. Nếu cần kiểm tra API xử lý việc vắng `note` đúng cách, hãy viết thêm một test gửi payload thực sự không có `note`.

### 5.2. Trường kỹ thuật không muốn hiển thị: `ignored()`

```java
fieldWithPath("clientTraceId")
        .description("Mã theo dõi nội bộ")
        .ignored()
```

Trường được khai báo `ignored()` được xem là đã biết để tránh lỗi trường chưa mô tả, nhưng không xuất hiện trong bảng tài liệu sinh ra. Chỉ nên sử dụng khi có lý do rõ ràng; nếu client cần gửi trường này theo hợp đồng công khai, hãy mô tả nó bình thường.

### 5.3. Mô tả một nhánh lớn: `subsectionWithPath(...)`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("shippingAddress")
        .description("Thông tin địa chỉ giao hàng")
```

`subsectionWithPath` ghi nhận cả một nhánh JSON như một mục trong tài liệu. Nó hữu ích khi muốn giới thiệu một cấu trúc phức tạp ở mức tổng quan hoặc chia tài liệu thành nhiều phần. Đánh đổi là các trường con không được liệt kê riêng ở bảng này; khi hợp đồng API cần mô tả từng thành phần, hãy dùng các đường dẫn cụ thể như `shippingAddress.city`, `shippingAddress.postalCode`.

### 5.4. Nới lỏng việc kiểm tra trường dư: `relaxedRequestFields(...)`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
        fieldWithPath("customerId").description("Mã khách hàng"),
        fieldWithPath("items").description("Danh sách mặt hàng")
)
```

`relaxedRequestFields` **không báo lỗi khi payload mẫu có trường chưa tài liệu hóa**. Tuy nhiên, các descriptor bắt buộc đã khai báo vẫn phải được tìm thấy trong payload. Cách này phù hợp khi chỉ muốn mô tả một phần của request; với API public cần hợp đồng đầy đủ, nên ưu tiên `requestFields` chặt chẽ để dễ phát hiện trường mới chưa được ghi nhận.

### 5.5. Kiểu và ràng buộc dữ liệu

`fieldWithPath(...).type(JsonFieldType.STRING)` giúp bảng ổn định và dễ đọc, nhất là khi một mẫu dữ liệu có thể chứa `null`. Nếu không đặt `.type(...)`, Spring REST Docs thường suy ra kiểu từ payload mẫu. Các giá trị thường gặp gồm `STRING`, `NUMBER`, `BOOLEAN`, `OBJECT`, `ARRAY`, `NULL` và `VARIES`.

Điều kiện như “số lượng phải lớn hơn 0”, “SKU không được rỗng” không được tạo thành quy tắc kiểm tra đầu vào chỉ bằng `.description(...)`. Cần kiểm tra bằng Bean Validation và bài kiểm thử endpoint, đồng thời ghi rõ điều kiện trong mô tả, ví dụ:

```java
fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng sản phẩm; số nguyên lớn hơn 0")
```

Bạn cũng có thể thêm metadata bằng `.attributes(...)` rồi tùy biến template snippet để hiển thị cột “Ví dụ”, “Giá trị cho phép” hoặc “Ràng buộc”. **Metadata tùy chỉnh không tự xuất hiện** trong bảng mặc định nếu template không hỗ trợ nó.

## 6. Sử dụng cùng WebTestClient và REST Assured

Các API `requestFields(...)`, `fieldWithPath(...)`, `optional()` và `ignored()` là các thành phần mô tả payload dùng chung. Khác biệt chủ yếu nằm ở cách gắn bộ sinh tài liệu vào bài kiểm thử HTTP:

| Công cụ kiểm thử | Điểm gắn tài liệu | Phù hợp với |
| --- | --- | --- |
| MockMvc | `.andDo(document("orders-create", requestFields(...)))` | Spring MVC, kiểm thử HTTP trong ứng dụng |
| WebTestClient | `.expectBody().consumeWith(document("orders-create", requestFields(...)))` | Spring WebFlux hoặc kiểm thử bằng WebTestClient |
| REST Assured | `.filter(document("orders-create", requestFields(...)))` trước khi gửi request | Kiểm thử theo cú pháp REST Assured |

Ở mỗi biến thể, cần dùng đúng hàm `document` từ tích hợp tương ứng và cấu hình REST Docs trước khi gọi. Chẳng hạn, `document` của MockMvc nằm trong `MockMvcRestDocumentation`, còn của WebTestClient nằm trong `WebTestClientRestDocumentation` và của REST Assured nằm trong `RestAssuredRestDocumentation`. Đừng trộn các static import này trong cùng ví dụ.

## 7. Đưa snippet vào tài liệu Asciidoctor và build

Spring REST Docs thường sinh snippet định dạng AsciiDoc (`.adoc`). Trong tài liệu nguồn, ví dụ `src/docs/asciidoc/api.adoc`, có thể chèn:

```adoc
= Order API
:toc: left

== Tạo đơn hàng

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Các trường của request body
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]
```

Biến `{snippets}` cần trỏ đến thư mục chứa kết quả kiểm thử. Ví dụ cấu hình Gradle với plugin Asciidoctor đã được cài đặt trong dự án:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Với cấu hình này, nhiệm vụ `asciidoctor` chạy sau `test`, đọc snippet vừa sinh và tạo tài liệu HTML. Trong CI, chạy các task kiểm thử/tạo tài liệu tương ứng với cấu hình dự án; nếu test tài liệu hóa thất bại, build phải thất bại để tránh phát hành tài liệu sai. Nếu dùng Maven, ý tưởng tương tự: xác định thư mục snippet, chạy test trước khi kết xuất Asciidoctor.

Nếu dự án muốn xuất tài liệu **Markdown**, cần cấu hình template/snippet hoặc bước chuyển đổi phù hợp. Mặc định không nên giả định file `request-fields.md` được tạo ra; tên snippet phổ biến trong ví dụ này là `request-fields.adoc`.

## 8. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Báo trường chưa được tài liệu hóa | Payload có trường mới nhưng thiếu descriptor | Thêm `fieldWithPath` tương ứng; tránh dùng `relaxedRequestFields` chỉ để che lỗi |
| Báo thiếu trường đã khai báo | Test gửi payload thiếu trường bắt buộc theo descriptor | Kiểm tra dữ liệu test, đường dẫn JSON; dùng `optional()` nếu trường thực sự không bắt buộc |
| Không tìm thấy `items[].sku` | Dùng `items.sku` hoặc mảng mẫu rỗng | Dùng cú pháp `[]` và dữ liệu mẫu đại diện |
| Test HTTP thành công nhưng không có `request-fields.adoc` | Chưa gọi `document(..., requestFields(...))`, chưa cấu hình REST Docs hoặc đọc sai thư mục output | Kiểm tra cấu hình test, `document` và `outputDir` |
| Asciidoctor báo thiếu file include | Tài liệu chạy trước test hoặc `{snippets}` trỏ sai đường dẫn | Cho task tài liệu phụ thuộc task test và thống nhất thư mục snippet |
| Tài liệu có kiểu/điều kiện không đúng thực tế | `.type(...)` và mô tả không tự xác thực toàn bộ nghiệp vụ | Bổ sung test validation/negative case và cập nhật mô tả theo contract API |

## 9. Bài thực hành

Trên endpoint tạo đơn hàng ở ví dụ:

1. Thêm trường `couponCode` (chuỗi, tùy chọn) vào request mẫu và descriptor bằng `fieldWithPath("couponCode").optional()`; xác nhận snippet có một dòng mô tả trường này.
2. Bỏ `couponCode` khỏi request mẫu và chạy lại test để xác nhận bài kiểm thử vẫn tạo tài liệu thành công.
3. Thêm trường mới `salesChannel` vào JSON nhưng **chưa** thêm descriptor; quan sát lỗi tài liệu hóa trong chế độ `requestFields` chặt chẽ. Sau đó bổ sung descriptor và chạy lại.
4. Chèn `request-fields.adoc` vào tài liệu Asciidoctor; kiểm tra bảng trường xuất hiện trong kết quả kết xuất.

**Ghi nhớ:** Mỗi lần một trường mới được thêm vào request JSON của bài kiểm thử, `requestFields` chặt chẽ tạo ra tín hiệu để cập nhật tài liệu. Kết hợp với kiểm thử HTTP, kiểm thử ràng buộc dữ liệu và build CI, snippet trở thành phần có thể kiểm chứng của hợp đồng REST API.
