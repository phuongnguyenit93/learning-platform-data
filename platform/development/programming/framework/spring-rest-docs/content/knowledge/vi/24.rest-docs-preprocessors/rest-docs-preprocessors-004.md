# Preprocess response trước khi sinh snippet

Response do ứng dụng trả về trong bài kiểm thử HTTP là bằng chứng về hành vi của API. Spring REST Docs ghi nhận response và tạo snippet như http-response, response headers và response fields. Tuy nhiên, message ban đầu có thể chứa request ID ngẫu nhiên, cookie phiên, header nội bộ, hostname của môi trường test hoặc body có dữ liệu fixture không nên công bố. **Response preprocessing** chuẩn hóa bản response mà REST Docs dùng để sinh snippet, giúp ví dụ dễ đọc, nhất quán và an toàn.

Preprocessor chỉ thay đổi bản response dùng cho tài liệu. Test vẫn nhận response ban đầu và assertion vẫn kiểm tra status, header, body thực tế. Vì thế, không dùng preprocessing để làm một response sai trông giống response đúng hoặc che đi hành vi không an toàn của ứng dụng.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định response preprocessing trong chuỗi test → assertion → document → snippet.
2. Dùng `preprocessResponse(...)` để áp dụng `OperationResponsePreprocessor`.
3. Định dạng response body JSON/XML, loại hoặc thay response header và chuẩn hóa giá trị động.
4. Phân biệt response thật với bản response đã xử lý cho tài liệu.
5. Giữ descriptor, raw snippet và phần diễn giải thống nhất với hợp đồng API.
6. Xử lý dữ liệu nhạy cảm và metadata môi trường trước khi công bố snippet.
7. Kiểm tra các file response liên quan và tích hợp vào build/CI.

## 2. Response preprocessing nằm ở đâu?

```text
Chuẩn bị fixture và test client
             │
             ▼
Gửi HTTP request tới ứng dụng
             │
             ▼
Ứng dụng xử lý và trả response thật
             │
             ▼
Test nhận response và chạy assertions
             │
             ▼
Gọi document(identifier, ...)
             │
             ▼
preprocessResponse(...)
             │
             ▼
REST Docs tạo snippet từ response đã xử lý
             │
             ▼
Asciidoctor / Markdown ghép snippet vào tài liệu
```

Trong MockMvc, hook tài liệu hóa thường nằm trong `andDo(document(...))`. Response processor được truyền bằng `preprocessResponse(...)`. Với WebTestClient và REST Assured, API gắn recorder khác nhau nhưng nguyên tắc giống nhau: processor tác động lên bản response được ghi nhận trước khi sinh snippet.

### 2.1. Response thật và response dùng cho tài liệu

Giả sử ứng dụng trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: req-9b7c21
Set-Cookie: SESSION=test-session-9281
X-Internal-Node: app-node-03

{"id":42,"status":"PAID","updatedAt":"2026-11-17T02:14:51.492Z"}
```

Tài liệu công khai có thể cần:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: docs-request-id

{
  "id": 42,
  "status": "PAID",
  "updatedAt": "2026-11-17T00:00:00Z"
}
```

Server vẫn trả response ban đầu cho test. Bản thứ hai chỉ là ví dụ sau preprocessing. Nếu assertion kiểm tra X-Request-Id tồn tại, nó phải kiểm tra response ban đầu, không dựa vào giá trị docs-request-id đã được thay vào snippet.

### 2.2. Lý do chuẩn hóa response

Giá trị không ổn định hoặc nhạy cảm có thể làm tài liệu kém hữu ích:

- Request ID, trace ID và timestamp thay đổi mỗi lần chạy.
- Set-Cookie chứa session identifier hoặc refresh token.
- Header debug hoặc hostname tiết lộ hạ tầng nội bộ.
- JSON chứa dữ liệu cá nhân hoặc dữ liệu khách hàng từ fixture.
- URL tuyệt đối phụ thuộc hostname/port của máy test.
- Body compact khó đọc trong trang hướng dẫn.

Response preprocessing xử lý các trường hợp này tại một điểm rõ ràng trước khi file snippet được ghi.

## 3. preprocessResponse(...) và OperationResponsePreprocessor

Spring REST Docs có API trong package `org.springframework.restdocs.operation.preprocess`. `preprocessResponse(...)` nhận một hoặc nhiều response processor và tạo processor tổng hợp để gắn vào operation tài liệu hóa.

Ví dụ:

```java
.andDo(document("orders-get",
    preprocessResponse(prettyPrint())
));
```

`OperationResponsePreprocessor` là abstraction xử lý một `OperationResponse` và trả về response đã xử lý. Các hàm built-in phổ biến gồm `prettyPrint()`, `removeHeaders(...)`, `modifyHeaders()` và `replacePattern(...)`.

Static import minh họa:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

Tên và chữ ký builder cụ thể cần khớp với phiên bản Spring REST Docs được quản lý trong dự án.

## 4. Định dạng response body

### 4.1. JSON với prettyPrint()

Response JSON compact:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"name":"Notebook","active":true}
```

Gắn `prettyPrint()` vào response processor:

```java
.andDo(document("products-get",
    preprocessResponse(prettyPrint())
));
```

Snippet sẽ có khoảng trắng và xuống dòng để dễ theo dõi:

```json
{
  "id": 42,
  "name": "Notebook",
  "active": true
}
```

Pretty print chỉ thay đổi cách trình bày. Nó không kiểm tra schema, xác nhận kiểu field hoặc loại dữ liệu nhạy cảm. Assertion và descriptor vẫn phải được khai báo riêng.

### 4.2. XML response

Ví dụ response XML:

```xml
<order><id>42</id><status>PAID</status><total>189000</total></order>
```

Nếu processor và content type hỗ trợ định dạng XML trong phiên bản đang dùng, snippet có thể dễ đọc hơn:

```xml
<order>
    <id>42</id>
    <status>PAID</status>
    <total>189000</total>
</order>
```

Đọc snippet thực tế để xác nhận encoding, namespace và nội dung vẫn đúng. Với XML có whitespace-sensitive content, không giả định format lại là vô hại.

### 4.3. Text và binary response

Với text thuần, khoảng trắng và xuống dòng có thể mang ý nghĩa nên giữ nguyên có thể phù hợp. Với binary response, hình ảnh hoặc stream, không cố đưa payload nhị phân vào snippet văn bản. Hãy mô tả metadata liên quan như media type, content length hoặc hành vi download và dùng ví dụ minh họa phù hợp.

Không dùng pretty print chung cho mọi response body. Xem content type, semantics và mục tiêu tài liệu trước khi áp dụng.

## 5. Loại bỏ response header không cần công bố

`removeHeaders(...)` loại header khỏi bản response được ghi vào snippet:

```java
.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Node")
    )
));
```

Cách này phù hợp khi cookie phiên hoặc header nội bộ không phải nội dung của tài liệu API công khai. Nó chỉ loại header khỏi bản ghi snippet; response ứng dụng đã gửi cho test vẫn chứa các header đó.

Nếu server đang trả header nội bộ không nên lộ cho client thật, cần đánh giá implementation và sửa ứng dụng nếu cần. Preprocessor không phải biện pháp sửa bảo mật ở runtime.

### 5.1. Không loại header client cần hiểu

Một số response header là phần hợp đồng:

- Content-Type cho biết media type.
- Location có thể chỉ URI tài nguyên vừa tạo.
- ETag có thể là validator cho request có điều kiện.
- Cache-Control công bố chính sách cache.
- Retry-After có thể hướng dẫn thời điểm thử lại.

Không xóa các header này nếu client cần biết semantics. Nếu giá trị biến động hoặc chứa dữ liệu riêng, thay bằng giá trị mẫu an toàn nhưng giữ tên header và giải thích đúng hành vi.

## 6. Thay giá trị response header bằng dữ liệu mẫu

### 6.1. Chuẩn hóa request ID

Request ID thường khác nhau giữa các lần test. Nếu người đọc chỉ cần biết response trả header, có thể thay bằng ID mẫu ổn định:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

Test vẫn assertion header X-Request-Id tồn tại hoặc kiểm tra format trên response thật. Snippet hiển thị giá trị ổn định để tránh diff vô ích.

### 6.2. Giữ format có ý nghĩa

Nếu format là một phần hợp đồng, chẳng hạn correlation ID phải có dạng UUID, giá trị mẫu nên đúng format:

```http
X-Correlation-Id: 123e4567-e89b-12d3-a456-426614174000
```

Không thay bằng chuỗi tùy ý nếu khiến ví dụ mâu thuẫn với validation của client. Phần diễn giải cần nói đây là giá trị mẫu, không phải ID mọi request luôn nhận.

### 6.3. Thay nhiều header

Có thể dùng cùng modifier để thay nhiều giá trị:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .set("X-Environment", "example")
            .build()
    )
));
```

Chỉ thay header có lý do rõ. Nếu X-Environment không thuộc hợp đồng client, loại nó có thể thích hợp hơn thay giá trị.

## 7. Chuẩn hóa dữ liệu động trong response body

Response body có thể chứa timestamp, UUID, URL callback hoặc dữ liệu định danh từ fixture. `replacePattern(...)` có thể thay nội dung khớp regular expression trong bản response dùng cho snippet.

Ví dụ khái niệm thay timestamp UTC bằng giá trị ổn định:

```java
.andDo(document("orders-get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}Z"),
            "2026-01-01T00:00:00.000Z"
        )
    )
));
```

Pattern minh họa timestamp UTC có millisecond; code thực tế cần kiểm tra escaping, format timestamp và API version. Chỉ áp dụng vào response đã xác định đúng vị trí. Regex chung có thể thay nhầm timestamp nghiệp vụ hoặc chuỗi ở field khác.

### 7.1. Khi nào nên thay, khi nào nên giữ?

| Loại dữ liệu | Cách xử lý gợi ý | Lý do |
| --- | --- | --- |
| Timestamp tạo từ thời gian chạy | Thay bằng giá trị cố định nếu thời gian không phải trọng tâm | Snippet ổn định |
| ID ngẫu nhiên của test | Dùng fixture cố định hoặc thay bằng ID mẫu | Tập trung vào schema |
| Giá trị tiền, trạng thái nghiệp vụ | Giữ giá trị đại diện hợp lệ | Đây là semantics response |
| Email/tên khách hàng thật | Dùng dữ liệu giả hoặc ẩn danh hóa | Bảo vệ dữ liệu cá nhân |
| URL phụ thuộc môi trường | Thay hostname bằng domain ví dụ | Tài liệu độc lập môi trường |
| ETag | Giữ format/semantics cần thiết hoặc dùng validator mẫu | Client cần hiểu conditional request |

Đừng chuẩn hóa giá trị chính là nội dung cần dạy. Ví dụ bài về tiền tệ cần giữ amount/currency có ý nghĩa; bài về timestamp có thể cần giữ format và timezone ngay cả khi thay thời điểm cụ thể.

## 8. Kết hợp nhiều response processor

Một response có thể cần định dạng body, loại cookie và chuẩn hóa ID:

```java
.andDo(document("orders-get",
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie", "X-Internal-Node"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

Trong ví dụ, prettyPrint giúp body dễ đọc; removeHeaders loại metadata không cần công bố; modifyHeaders thay ID động bằng ví dụ ổn định.

### 8.1. Thứ tự processor

Thứ tự biến đổi có thể ảnh hưởng kết quả. Nếu remove header trước, processor sau không còn header để thay. Nếu sửa nội dung trước rồi mới format, bộ format áp dụng lên nội dung đã sửa.

Đặt các bước theo mục tiêu, chạy test và đọc response snippet cuối cùng. Xác minh với version Spring REST Docs thực tế.

## 9. Response preprocessing và assertions

**Assertion kiểm tra response thật; preprocessor chuẩn hóa bản response được ghi thành snippet.**

Ví dụ:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.status").value("PAID"))
    .andDo(document("orders-get",
        preprocessResponse(
            prettyPrint(),
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build()
        )
    ));
```

Assertion chạy trên response do ứng dụng trả về. Sau đó recorder ghi response đã xử lý vào snippet. Nếu response thật thiếu request ID, test thất bại; preprocessor không được tạo header giả để làm test pass.

Không dùng response processor để biến status lỗi thành thành công, chèn field bắt buộc đang thiếu, thay giá trị nghiệp vụ sai thành giá trị mong đợi, xóa header bắt buộc để né descriptor hoặc che rò rỉ của implementation.

## 10. Response descriptor và raw snippet

Response preprocessing và descriptor có vai trò khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| preprocessResponse(...) | Biến đổi response dùng để tạo snippet |
| responseHeaders(...) | Mô tả response header thuộc contract |
| responseFields(...) | Mô tả cấu trúc response body |
| http-response.adoc | Ví dụ raw response sau preprocessing |
| response-headers.adoc | Bảng descriptor response header |
| response-fields.adoc | Bảng descriptor response field |

Ví dụ:

```java
.andDo(document("orders-create",
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI của đơn hàng vừa tạo"),
        headerWithName("X-Request-Id")
            .description("Mã tương quan để tra cứu request")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Mã đơn hàng"),
        fieldWithPath("status")
            .description("Trạng thái hiện tại")
    )
));
```

Raw response snippet có ID đã chuẩn hóa và không có Set-Cookie; bảng header giải thích Location và X-Request-Id; bảng body fields mô tả JSON. Descriptor phải phản ánh contract và không mô tả header đã bị loại như thể nó xuất hiện trong raw message.

## 11. Kiểm tra response snippets sau preprocessing

Một operation có thể tạo nhiều file:

```text
target/generated-snippets/orders-get-success/
├── http-response.adoc
├── response-headers.adoc
├── response-fields.adoc
└── ...
```

Sau test, kiểm tra:

- Status và body trong http-response.adoc vẫn đúng contract.
- Header nhạy cảm như Set-Cookie đã được loại hoặc thay an toàn.
- Request ID/timestamp có giá trị mẫu đúng mục tiêu.
- response-headers.adoc chỉ mô tả header hợp đồng.
- response-fields.adoc phản ánh đúng field và semantics.
- Không có dữ liệu cá nhân/fixture thật trong body.
- HTML/PDF cuối không giữ artifact cũ có dữ liệu nhạy cảm.

Không chỉ đọc bảng descriptor; raw response là nơi có thể lộ các header không được mô tả.

## 12. Khác biệt theo test client

Nguyên tắc response preprocessing giống nhau giữa MockMvc, WebTestClient và REST Assured, nhưng điểm gắn recorder khác nhau:

| Test client | Điểm gắn tài liệu hóa | Lưu ý |
| --- | --- | --- |
| MockMvc | andDo(document(...)) | Cấu hình MockMvc với Spring REST Docs |
| WebTestClient | REST Docs filter/configuration trong exchange | Dùng module WebTestClient và API tương ứng |
| REST Assured | REST Docs filter trong request specification | Gắn processor với operation được ghi nhận |

Không sao chép cú pháp MockMvc sang test client khác. Dùng adapter và API document/filter tương ứng để truyền response preprocessor vào operation recorder.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Set-Cookie còn trong response snippet | Chưa gắn response processor hoặc remove sai tên | Kiểm tra processor và raw snippet |
| Request ID đổi mỗi build | Chưa chuẩn hóa giá trị động | Fixture cố định hoặc modifyHeaders |
| JSON vẫn compact | prettyPrint chưa gắn đúng operation hoặc body/content type không phù hợp | Kiểm tra response content type và snippet |
| Header bắt buộc biến mất | Remove quá rộng | Giữ header contract, chỉ thay value nếu cần |
| Assertion pass nhưng snippet có giá trị khác | Nhầm bản ghi sau preprocessing với response thật | Kiểm tra assertion và snippet riêng |
| Body ví dụ sai semantics | Regex thay nhầm field | Thu hẹp pattern và kiểm tra output |
| Descriptor không khớp raw response | Header không xuất hiện hoặc đã bị processor loại | Sửa descriptor/processor theo contract |
| Hostname nội bộ còn xuất hiện | Chưa xử lý URL trong response | Response processor phù hợp hoặc fixture |
| HTML vẫn có dữ liệu cũ | Không render lại từ snippet mới | Clean build và kiểm tra artifact mới |
| Dữ liệu cá nhân còn xuất hiện | Chỉ làm sạch header, bỏ qua body | Fixture giả và xử lý body snippet |

## 14. Best practices

1. Dùng response preprocessor cho response, không nhầm với request preprocessor.
2. Assertion status/header/body trên response thật trước khi tạo snippet.
3. Dùng prettyPrint để cải thiện khả năng đọc, không coi đó là validation.
4. Loại Set-Cookie và header nội bộ chỉ khi chúng không thuộc nội dung API công khai.
5. Thay request ID, timestamp và hostname động bằng giá trị mẫu ổn định khi phù hợp.
6. Không biến đổi field nghiệp vụ mà client cần hiểu.
7. Giữ descriptor nhất quán với response sau xử lý và phần diễn giải hợp đồng.
8. Rà soát raw response, header/field snippets và bản HTML/PDF.
9. Dùng fixture an toàn ngay từ đầu; preprocessor là lớp bảo vệ bổ sung.
10. Chạy clean test trước render trong CI để tránh output cũ.

## 15. Bài thực hành

Tài liệu hóa endpoint `GET /api/orders/{id}`. Response thực có JSON đơn hàng, request ID thay đổi mỗi lần test, Set-Cookie từ middleware và một header nội bộ. Tài liệu cần JSON dễ đọc, request ID mẫu ổn định và không công bố cookie hoặc header nội bộ.

**Nhiệm vụ:**

1. Viết MockMvc documentation test và assertion status, ID, trạng thái đơn hàng.
2. Assertion response có request ID trên message thật.
3. Dùng `preprocessResponse(prettyPrint())` cho JSON.
4. Dùng `removeHeaders(...)` loại Set-Cookie và header nội bộ không thuộc contract.
5. Dùng `modifyHeaders()` thay request ID động bằng giá trị mẫu.
6. Khai báo response headers và response fields đúng contract.
7. Chạy test, kiểm tra raw response, response-headers và response-fields snippet.
8. Xác nhận dữ liệu fixture nhạy cảm không còn trong snippet.
9. Include snippet vào trang AsciiDoc.
10. Chạy clean build và rà soát bản HTML/PDF cuối.

**Tiêu chí hoàn thành:** response thật được assertion; response snippet đã định dạng và chuẩn hóa có chủ đích; header không công khai không bị lộ; descriptor khớp contract; tài liệu render từ snippet mới.

## 16. Ghi nhớ

- Response preprocessing biến đổi bản response dùng để sinh snippet; không thay đổi response ứng dụng đã trả cho test.
- `preprocessResponse(...)` gắn một hoặc nhiều `OperationResponsePreprocessor` vào operation được tài liệu hóa.
- `prettyPrint()` định dạng body; `removeHeaders(...)` loại header khỏi snippet; `modifyHeaders()` thay giá trị header; `replacePattern(...)` chuẩn hóa nội dung khớp pattern.
- Assertions kiểm tra status, header và body thật; preprocessor không thay thế assertion.
- Response descriptor giải thích header/field; raw response snippet cho thấy message sau preprocessing.
- Không dùng processor để che lỗi contract hoặc rò rỉ trong implementation.
- Rà soát response snippet và artifact đã render, sau đó chạy build sạch trong CI.
