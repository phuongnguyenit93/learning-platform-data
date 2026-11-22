# Operation là đơn vị kết hợp lời gọi, snippet và phần mô tả

Trong **Spring REST Docs**, tài liệu của một API được tạo từ những bài kiểm thử HTTP chạy thật. Đơn vị nối giữa kiểm thử và tài liệu là **operation**: một lần trao đổi HTTP có request, response và ngữ cảnh kiểm thử tương ứng. Spring REST Docs sử dụng dữ liệu của operation cùng các mô tả do người viết khai báo để sinh **snippet**; sau đó tài liệu Asciidoctor hoặc quy trình biên soạn Markdown sẽ đưa các snippet vào trang API hoàn chỉnh.

Chủ đề thuộc chương **Mô hình tài liệu** của module `SPRING_REST_DOCS`. Mục tiêu rộng của module là tạo tài liệu REST API có thể kiểm chứng từ MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi kết nối quá trình đó với build và CI. Bài này tập trung vào **mối liên kết một operation → các snippet → phần giải thích dành cho người tích hợp API**.

## 1. Kết quả học tập

Học xong bài này, bạn có thể:

1. Giải thích vì sao một route không đồng nghĩa với một operation tài liệu.
2. Phân biệt request/response thu được từ test, mô tả do người viết cung cấp và snippet được sinh ra.
3. Sử dụng `document("operation-id", ...)` để gắn các mô tả với đúng tương tác HTTP.
4. Xác định snippet nào cần cho một endpoint và chèn chúng vào tài liệu Asciidoctor.
5. Tổ chức nhiều operation cho các tình huống thành công, lỗi và bảo đảm CI tạo lại được tài liệu.

## 2. Operation là đơn vị kết nối ba tầng

Để hình dung, xét endpoint đọc đơn hàng:

```http
GET /api/orders/101?includeItems=true HTTP/1.1
Accept: application/json
```

Một lần thực thi request có thể nhận:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: req-docs-001

{
  "id": 101,
  "status": "CONFIRMED",
  "total": 150000,
  "items": [
    {"sku": "BK-01", "quantity": 2}
  ]
}
```

Để biến lần trao đổi này thành tài liệu có ích, cần ba tầng thông tin:

| Tầng | Nguồn thông tin | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| **Lời gọi được kiểm thử** | Request và response trong bài kiểm thử HTTP | Cung cấp sự thật quan sát được về method, URI, header, payload, status | `GET /api/orders/101` nhận `200 OK` |
| **Mô tả hợp đồng** | Người viết test khai báo các descriptor | Giải thích ý nghĩa tham số, field, header; phát hiện khác biệt giữa payload và mô tả | `orderId` là mã đơn hàng, `items[].sku` là mã mặt hàng |
| **Snippet tài liệu** | Spring REST Docs xử lý operation và descriptor | Xuất các đoạn tài liệu cho một lần trao đổi | `http-request.adoc`, `response-fields.adoc`, `path-parameters.adoc` |

Một phép kiểm thử được mô tả bằng:

```text
Test HTTP
   ├── gửi request ─────────────┐
   ├── nhận response ───────────┤
   ├── assertion hành vi        │
   └── document("orders-get", …)│
                               ▼
                         Operation ghi nhận
                         + các descriptor
                               │
                               ▼
                  generated-snippets/orders-get/
                    ├── http-request.adoc
                    ├── http-response.adoc
                    ├── path-parameters.adoc
                    ├── query-parameters.adoc
                    ├── request-headers.adoc
                    ├── response-headers.adoc
                    └── response-fields.adoc
                               │
                               ▼
                       Trang tài liệu API
                 (Asciidoctor hoặc Markdown)
```

Điểm cần nhớ: **operation không phải một file snippet**. Một operation có thể tạo nhiều snippet, mỗi snippet phản ánh một góc nhìn. Và **snippet không thay thế văn bản giải thích**: bảng field cho biết `items[].sku` là gì, còn trang tài liệu vẫn nên mô tả khi nào đơn hàng tồn tại, điều kiện phân quyền, các status có thể trả về và quy tắc nghiệp vụ.

### 2.1. Operation khác route, HTTP method và test case như thế nào?

- **Route**: khuôn dạng đường dẫn, ví dụ `/api/orders/{orderId}`.
- **HTTP method + route**: kiểu thao tác có thể thực hiện, ví dụ `GET /api/orders/{orderId}`.
- **Test case**: chương trình thiết lập dữ liệu, gửi request, kiểm tra response và có thể gọi `document(...)`.
- **Operation được tài liệu hóa**: dữ liệu của **một lần request/response** được test ghi lại, đặt dưới một định danh snippet và được diễn giải bằng các descriptor.

Hai test cùng gọi `GET /api/orders/{orderId}` nhưng một test nhận `200`, test khác nhận `404` thì đó là hai tình huống tài liệu hóa riêng. Ngược lại, nếu một test gọi cùng một endpoint nhiều lần, mỗi lần được ghi nhận là một tương tác riêng; không nên mặc định rằng “một test luôn tương ứng một operation”.

### 2.2. Vai trò của định danh operation

Khi viết:

```java
.andDo(document("orders-get", /* descriptors */))
```

`orders-get` là định danh dùng để nhóm các snippet của lần tương tác này. Đường dẫn đầu ra thường có dạng:

```text
build/generated-snippets/orders-get/      (Gradle)
target/generated-snippets/orders-get/     (Maven)
```

Đây **không phải tên route** mà ứng dụng tự sinh ra. Người viết test lựa chọn identifier sao cho ổn định và có ý nghĩa. Nên dùng các tên phân biệt tình huống như `orders-get-success`, `orders-get-not-found`, `orders-create-valid` và `orders-create-invalid` nếu cần tài liệu hóa nhiều kết quả.

Không nên cho nhiều test độc lập chạy song song ghi vào **cùng** một identifier nếu chúng tạo nội dung khác nhau: các file cùng tên trong thư mục snippet có nguy cơ bị thay thế và làm tài liệu phụ thuộc thứ tự chạy test.

## 3. Mô tả được gắn vào operation ở đâu?

Spring REST Docs có thể sinh snippet request/response từ dữ liệu HTTP đã ghi nhận, nhưng **không thể tự biết** `orderId` có ý nghĩa nghiệp vụ gì hoặc field `status` cho phép những giá trị nào. Những thông tin đó do người viết bổ sung qua API mô tả:

| Nhóm mô tả | API quen dùng | Snippet được tạo |
| --- | --- | --- |
| Biến trong URI template | `pathParameters(parameterWithName(...))` | `path-parameters.adoc` |
| Tham số query | `queryParameters(parameterWithName(...))` | `query-parameters.adoc` |
| Request header | `requestHeaders(headerWithName(...))` | `request-headers.adoc` |
| Response header | `responseHeaders(headerWithName(...))` | `response-headers.adoc` |
| Trường JSON của request | `requestFields(fieldWithPath(...))` | `request-fields.adoc` |
| Trường JSON của response | `responseFields(fieldWithPath(...))` | `response-fields.adoc` |
| Mẫu HTTP | Tạo tự động từ operation khi `document(...)` | `http-request.adoc`, `http-response.adoc` |
| Body, lệnh gọi mẫu | Tạo từ operation khi áp dụng | `request-body.adoc`, `response-body.adoc`, `curl-request.adoc`, `httpie-request.adoc` |

Một descriptor thường gồm **tên/đường dẫn**, **kiểu dữ liệu** (nếu phù hợp), **mô tả** và các thuộc tính như `optional()` hoặc `ignored()`. Ví dụ:

```java
fieldWithPath("items[].sku")
    .type(JsonFieldType.STRING)
    .description("Mã sản phẩm của từng dòng hàng")
```

Đường dẫn `items[].sku` là quy tắc chọn field lồng trong mỗi phần tử của mảng `items`; nó không phải một tên property JSON nguyên văn. Với một số payload, bạn cũng cần mô tả cả node cha, chẳng hạn `items` với kiểu `ARRAY`.

Mô tả trong snippet phải đúng với **request và response của chính operation**. Nếu test không gửi `X-Customer-Id` thì không nên viết snippet mô tả header đó như một thành phần thực có mặt trong operation, trừ khi phù hợp với cơ chế optional và hợp đồng đã xác định.

## 4. Ví dụ xuyên suốt: một operation đọc đơn hàng bằng MockMvc

Đoạn ví dụ dưới đây sử dụng JUnit 5, Spring MVC Test và Spring REST Docs. Controller được dựng ngay trong test để người đọc nhìn được toàn bộ dữ liệu: đơn hàng `101` có trạng thái `CONFIRMED`, tổng tiền và một dòng hàng; mã khác trả về `404`.

> Trong ứng dụng thực, controller thường lấy dữ liệu từ service/repository. Fixture, quyền truy cập và dữ liệu test phải được kiểm soát để mỗi lần build cho kết quả nhất quán.

### 4.1. Controller tối giản phục vụ ví dụ

```java
@RestController
class OrderController {

    @GetMapping(
        value = "/api/orders/{orderId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderView> getOrder(
            @PathVariable long orderId,
            @RequestParam(defaultValue = "false") boolean includeItems) {

        if (orderId != 101L) {
            return ResponseEntity.notFound().build();
        }

        List<OrderItem> items = includeItems
            ? List.of(new OrderItem("BK-01", 2))
            : List.of();

        OrderView body = new OrderView(
            101L, "CONFIRMED", new BigDecimal("150000"), items
        );

        return ResponseEntity.ok()
            .header("X-Request-Id", "req-docs-001")
            .body(body);
    }

    record OrderView(
        long id, String status, BigDecimal total, List<OrderItem> items
    ) {}

    record OrderItem(String sku, int quantity) {}
}
```

Phần lớn dự án sẽ đặt `OrderController` và DTO vào các file riêng. Để dùng ví dụ, cần các import tương ứng cho `BigDecimal`, `List`, `MediaType`, `@RestController`, `@GetMapping`, `@PathVariable`, `@RequestParam` và `ResponseEntity`. DTO dạng Java `record` phù hợp với Java 17 trở lên và môi trường Spring/Jackson có hỗ trợ record.

### 4.2. Test kết hợp assertion và descriptor

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new OrderController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getOrder_createsVerifiedSnippets() throws Exception {
        mockMvc.perform(
                get("/api/orders/{orderId}", 101L)
                    .queryParam("includeItems", "true")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.items[0].sku").value("BK-01"))
            .andDo(document("orders-get-success",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã đơn hàng cần lấy")
                ),
                queryParameters(
                    parameterWithName("includeItems")
                        .description("Có trả về các dòng hàng hay không")
                        .optional()
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Định dạng response client chấp nhận")
                ),
                responseHeaders(
                    headerWithName("X-Request-Id")
                        .description("Mã tương quan để tra cứu request")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Mã đơn hàng"),
                    fieldWithPath("status")
                        .type(JsonFieldType.STRING)
                        .description("Trạng thái của đơn hàng"),
                    fieldWithPath("total")
                        .type(JsonFieldType.NUMBER)
                        .description("Tổng tiền theo đơn vị tiền tệ API quy định"),
                    fieldWithPath("items")
                        .type(JsonFieldType.ARRAY)
                        .description("Các dòng hàng, có thể rỗng"),
                    fieldWithPath("items[].sku")
                        .type(JsonFieldType.STRING)
                        .description("Mã sản phẩm"),
                    fieldWithPath("items[].quantity")
                        .type(JsonFieldType.NUMBER)
                        .description("Số lượng sản phẩm")
                )
            ));
    }
}
```

Ở đây `get` phải được import từ `org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get`. Builder này giữ thông tin URI template để `pathParameters(...)` có thể tài liệu hóa `{orderId}`. Nếu dùng một request builder không giữ template, việc sinh bảng path parameter có thể không hoạt động như mong muốn.

Những static import chính:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Các type như `MockMvc`, `MockMvcBuilders`, `RestDocumentationExtension`, `RestDocumentationContextProvider` và `JsonFieldType` cũng cần import từ thư viện tương ứng. Test dùng `RestDocumentationExtension` phải có dependency và cấu hình output snippet Spring REST Docs trong dự án.

### 4.3. Phân tích đúng nhiệm vụ của từng phần

| Mã trong test | Tác dụng | Hệ quả đối với tài liệu |
| --- | --- | --- |
| `perform(get(...))` | Gửi một request theo URI template | Tạo dữ liệu HTTP thực tế cho operation |
| `queryParam("includeItems", "true")` | Quyết định request có query nào | Snippet request sẽ hiển thị tham số đó |
| `andExpect(status().isOk())` | Xác nhận response thành công | Test thất bại nếu status không đúng |
| `andExpect(jsonPath(...))` | Xác nhận dữ liệu nghiệp vụ quan trọng | Test thất bại nếu giá trị JSON ngoài mong đợi |
| `document("orders-get-success", ...)` | Gắn định danh và bộ descriptor vào tương tác | Sinh các file trong thư mục `orders-get-success` |
| `responseFields(...)` | Mô tả schema của JSON response đã nhận | Sinh bảng field, có kiểm tra mô tả so với payload |

Chỉ có `andExpect(status().isOk())` **không đủ** để khẳng định `status` trong JSON là `CONFIRMED`. Và chỉ có `responseFields(...)` **không thay thế** assertion kiểm tra giá trị nghiệp vụ. Hai cơ chế bổ sung nhau.

Trong chế độ tài liệu hóa field nghiêm ngặt thường dùng, Spring REST Docs báo lỗi khi response có field không được mô tả hoặc một field được yêu cầu mô tả lại không xuất hiện. Trường nào thật sự tùy chọn có thể được đánh dấu `optional()`. Khi chỉ muốn mô tả một phần cấu trúc, có `relaxedResponseFields(...)`, nhưng lựa chọn đó bỏ bớt khả năng phát hiện field mới chưa được cập nhật vào tài liệu. Với một endpoint public, nên mô tả đầy đủ các field thuộc hợp đồng.

## 5. Cùng route, nhiều operation theo trường hợp xử lý

Đơn hàng không tồn tại là tình huống khác với đọc đơn hàng thành công. Test tài liệu hóa riêng:

```java
@Test
void getOrder_notFound() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 999L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isNotFound())
        .andDo(document("orders-get-not-found",
            pathParameters(
                parameterWithName("orderId")
                    .description("Mã đơn hàng cần lấy")
            )
        ));
}
```

Với controller mẫu, response `404` không có JSON body. Vì vậy, test này không khai báo `responseFields(...)` cho một payload lỗi giả định chưa tồn tại. Nếu hệ thống thực tế trả body dạng:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Đơn hàng không tồn tại"
}
```

thì test và `responseFields(...)` của operation lỗi phải mô tả **đúng** schema lỗi đó, đồng thời kiểm tra status và mã lỗi quan trọng.

| Tình huống | Định danh | Request | Kết quả | Điểm cần giải thích |
| --- | --- | --- | --- | --- |
| Đơn hàng tồn tại | `orders-get-success` | `GET /api/orders/101?includeItems=true` | `200`, JSON đơn hàng | Field, tùy chọn `includeItems`, các header |
| Đơn hàng không tồn tại | `orders-get-not-found` | `GET /api/orders/999` | `404`, không body trong ví dụ | Điều kiện không tìm thấy |
| Không có quyền xem | `orders-get-forbidden` (nếu API hỗ trợ) | `GET /api/orders/101` với danh tính không đủ quyền | `403` theo hợp đồng | Điều kiện phân quyền, format lỗi |

Dòng thứ ba minh họa một **operation cần cân nhắc bổ sung**, chưa được triển khai trong controller mẫu. Không ghi nó thành ví dụ response thật cho tới khi có test chạy và hợp đồng được xác nhận.

Trong tài liệu cho một route, có thể dùng một section giới thiệu chung và các subsection trình bày từng trường hợp. Không dùng cùng một đoạn response `200` để minh họa một `404`.

## 6. Snippet được sinh ra từ operation như thế nào?

Sau khi test hoàn tất, kết quả thường nằm tại đường dẫn theo build tool, ví dụ:

```text
build/generated-snippets/
├── orders-get-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   ├── httpie-request.adoc
│   ├── request-body.adoc
│   ├── response-body.adoc
│   ├── path-parameters.adoc
│   ├── query-parameters.adoc
│   ├── request-headers.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── orders-get-not-found/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    └── path-parameters.adoc
```

Tên file thực tế phụ thuộc vào loại snippet được yêu cầu và phiên bản/cấu hình Spring REST Docs. Các file thể hiện body có thể rỗng nếu operation không có body. Không dựa vào việc mọi operation đều sinh tất cả các bảng tham số, field và header.

### 6.1. Snippet dữ liệu quan sát được

`http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, `httpie-request.adoc` thường phục vụ mục đích đưa **ví dụ gọi API** cho người đọc. Dữ liệu xuất phát từ operation đã được kiểm thử, nên nó có thể phản ánh host, port, query, header và body do test gửi/nhận.

Ví dụ, snippet `http-response.adoc` của `orders-get-success` cho thấy `200`, `X-Request-Id` và JSON đơn hàng. Một đoạn giải thích tự viết kiểu “response chứa trạng thái đơn hàng” không thể thay thế bằng chứng này về hình dạng thực tế của payload.

### 6.2. Snippet do descriptor sinh ra

`response-fields.adoc` không chỉ sao chép JSON. Nó là **bảng mô tả** các field từ `fieldWithPath(...)`, gồm đường dẫn, kiểu, trạng thái tùy chọn và diễn giải. Tương tự, `path-parameters.adoc` mô tả `orderId`; `query-parameters.adoc` mô tả `includeItems`.

Một trường có mặt trong response **chưa đủ** để bảng field tự biết cách gọi tên và giải thích nghiệp vụ. Ngược lại, một descriptor được viết rất hay nhưng không khớp payload cần bị kiểm thử phát hiện. Đó là lý do operation tạo thành cầu nối giữa sự thật HTTP và tài liệu đọc được.

### 6.3. Mẫu hóa để các operation cùng chuẩn

Khi có nhiều endpoint, có thể cấu hình các snippet mặc định hoặc dùng các helper tạo descriptor lặp lại (chẳng hạn lỗi chung, pagination, header tương quan). Mục đích là giữ thuật ngữ và cách mô tả nhất quán.

Tuy nhiên, không nên cố gắng tái sử dụng nguyên bộ `responseFields(...)` của operation thành công cho mọi operation lỗi: schema response và ý nghĩa của từng field có thể khác nhau. Tái sử dụng những phần đúng là chung, giữ các phần khác biệt theo từng tình huống.

## 7. Từ operation đến trang tài liệu có thể đọc được

Spring REST Docs sinh snippet ở bước test; một trang tài liệu cần **chèn snippet vào ngữ cảnh**. Ví dụ AsciiDoc:

```asciidoc
[[orders-get]]
=== Tra cứu đơn hàng

Gọi API để lấy đơn hàng theo mã. Nếu không tìm thấy, API trả 404.
Tham số includeItems cho biết có lấy danh sách dòng hàng hay không.

==== Thành công — HTTP 200

.Request
include::{snippets}/orders-get-success/http-request.adoc[]

.Path parameters
include::{snippets}/orders-get-success/path-parameters.adoc[]

.Query parameters
include::{snippets}/orders-get-success/query-parameters.adoc[]

.Request headers
include::{snippets}/orders-get-success/request-headers.adoc[]

.Response
include::{snippets}/orders-get-success/http-response.adoc[]

.Response headers
include::{snippets}/orders-get-success/response-headers.adoc[]

.Response fields
include::{snippets}/orders-get-success/response-fields.adoc[]

==== Không tìm thấy — HTTP 404

.Request
include::{snippets}/orders-get-not-found/http-request.adoc[]

.Response
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

Ở đây `{snippets}` là attribute được build thiết lập để trỏ tới thư mục generated snippets. Khi hai include cùng tham chiếu `orders-get-success`, chúng hiển thị hai góc nhìn của **cùng một operation**.

Nếu dự án xuất tài liệu Markdown, cần một bước chuyển đổi hoặc chèn snippet tương thích với công cụ Markdown đang dùng. Directive `include::{snippets}/...[]` là cú pháp Asciidoctor, không mặc định được tất cả trình biên dịch Markdown hỗ trợ.

### 7.1. Phần mô tả nào phải viết bằng lời?

Snippet giúp liệt kê dữ liệu và bảng trường, còn phần viết tay nên trả lời những điều nằm ngoài một request mẫu:

- **Khi nào được gọi:** endpoint dùng cho hành vi nào, ai được phép truy cập?
- **Điều kiện và ràng buộc:** `orderId` hợp lệ ra sao, `includeItems` mặc định thế nào?
- **Ý nghĩa nghiệp vụ:** `status` là một trạng thái trong vòng đời đơn hàng, `total` dùng tiền tệ và quy tắc làm tròn nào?
- **Các kết quả có thể gặp:** trường hợp nào nhận `200`, `404`, `403`; có body lỗi hay không?
- **Quan hệ tới API khác:** nếu có tạo/cập nhật đơn hàng, người đọc đi tới operation nào?

Test trong ví dụ đã có mặc định `includeItems=false` ở controller; tài liệu cần nói rõ mặc định này vì một test chỉ chạy `includeItems=true` không thể tự hiển thị mọi trường hợp. Nếu mô tả tiền tệ/format thực tế chưa xác định, tác giả phải xác minh hợp đồng trước khi ghi thành cam kết công khai.

## 8. Kết nối operation với build và CI

Một quy trình thường có chuỗi phụ thuộc:

```text
Biên dịch ứng dụng và test
         │
         ▼
Chạy test HTTP (MockMvc/WebTestClient/REST Assured)
         │
         ├── Nếu assertion hoặc snippet validation lỗi → build thất bại
         │
         ▼
Sinh generated-snippets/<operation-id>/
         │
         ▼
Biên soạn AsciiDoc hoặc xử lý Markdown
         │
         ├── Nếu thiếu file include → lỗi biên soạn hoặc lỗi kiểm tra
         │
         ▼
Xuất HTML/PDF/trang tài liệu để công bố
```

Đối với Gradle, task biên soạn tài liệu phải phụ thuộc task `test` (hoặc đúng task kiểm thử tạo snippet) và dùng thư mục snippet làm input. Với Maven, cần nối pha kiểm thử và plugin tạo tài liệu theo lifecycle phù hợp. Trong CI, chạy từ môi trường sạch rồi kiểm tra cả test lẫn bước biên soạn, tránh việc một file snippet còn sót từ build cũ che giấu một test không còn được chạy.

Một quy trình build không thay thế việc rà soát hợp đồng nghiệp vụ. Nó đảm bảo các ví dụ và bảng mô tả được sinh từ test hiện tại, nhưng độ bao phủ tùy vào những operation được đưa vào bộ kiểm thử.

### 8.1. Những dữ liệu cần chuẩn hóa trước khi xuất bản

Request/response kiểm thử có thể chứa hostname nội bộ, port ngẫu nhiên, token, cookie, email hoặc thông tin định danh thật. Vì đó là dữ liệu nằm trong operation, việc sinh tài liệu có thể vô tình đưa chúng lên trang công khai.

Spring REST Docs hỗ trợ preprocessors để trình bày các ví dụ nhất quán hơn, như `preprocessRequest(...)`, `preprocessResponse(...)` và `prettyPrint()`; các cơ chế thay thế/loại bỏ dữ liệu có thể được áp dụng khi chuẩn bị snippet. Nên dùng fixture giả an toàn, chuẩn hóa URI và loại hoặc che thông tin nhạy cảm trước khi công bố. Việc thay đổi phần hiển thị phục vụ tài liệu phải có mục đích rõ ràng để tránh làm ví dụ mô tả sai hợp đồng thật.

## 9. Sai lầm thường gặp và cách nhận diện

| Biểu hiện | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Xem route `GET /orders/{id}` là đủ cho mọi trường hợp | Không phân biệt tình huống `200`, `404`, `403` | Tạo operation test và identifier riêng cho các hành vi quan trọng |
| `path-parameters.adoc` lỗi hoặc thiếu `orderId` | Request builder không bảo toàn URI template | Sử dụng `RestDocumentationRequestBuilders` với template `{orderId}` |
| HTTP response có field mới nhưng tài liệu không thay đổi | Dùng mô tả lỏng hoặc bỏ qua validation | Dùng mô tả nghiêm ngặt với các field thuộc hợp đồng; cập nhật descriptor cùng code |
| Tài liệu có bảng field nhưng không giải thích khi nào xảy ra lỗi | Chỉ chèn snippet, thiếu văn bản ngữ cảnh | Viết rõ quy tắc và tình huống cho mỗi operation |
| `response-fields.adoc` không xuất hiện | Test không gọi `responseFields(...)` hoặc không chạy | Bổ sung descriptor vào đúng `document(...)` và kiểm tra task test |
| Thư mục snippet có kết quả lẫn giữa hai test | Hai test cùng identifier, ghi ra nội dung khác nhau | Đặt tên riêng, tránh collision khi chạy song song |
| Build tài liệu thành công dù test mới lỗi | Trang đang dùng snippet tồn dư từ build trước | Buộc task biên soạn phụ thuộc test và xác minh trên clean build |
| Ví dụ hiển thị token hoặc host nội bộ | Dữ liệu request/response được chèn nguyên trạng | Dùng fixture an toàn, chuẩn hóa và lọc dữ liệu snippet |
| Field được đánh dấu `optional()` chỉ để test qua | Mô tả không đúng ràng buộc API | Chỉ đánh dấu tùy chọn khi field thực sự có thể vắng mặt |

Một lỗi khác là nhầm **request parameter** với **JSON field**. `includeItems` trong `?includeItems=true` thuộc `queryParameters(...)`, còn `items[].sku` trong body JSON thuộc `responseFields(...)`. Mỗi loại được mô tả bằng API và snippet tương ứng; dùng sai sẽ khiến tài liệu không phản ánh đúng cấu trúc HTTP.

## 10. Bài thực hành

Giả sử cần viết tài liệu cho `GET /api/orders/{orderId}` và `POST /api/orders`:

1. **Chọn operation:** liệt kê ít nhất hai kết quả của `GET` (`200` và `404`) và hai kết quả có ý nghĩa của `POST` (ví dụ `201` và `400`).
2. **Đặt identifier:** dùng các tên riêng, rõ tình huống, tránh ghi đè snippet.
3. **Viết test:** với mỗi operation, tạo dữ liệu cố định, gửi request, kiểm tra status và giá trị nghiệp vụ quan trọng.
4. **Gắn descriptor:** dùng `pathParameters`, `queryParameters`, `requestHeaders`, `requestFields`, `responseHeaders`, `responseFields` khi thành phần tương ứng hiện diện và thuộc hợp đồng.
5. **Biên soạn tài liệu:** tổ chức trang theo endpoint và tình huống; chèn snippet phù hợp; bổ sung giải thích bằng lời.
6. **Chạy build sạch:** xác nhận các snippet có mặt, trang tài liệu sinh được và thay đổi trái hợp đồng khiến test hoặc bước sinh tài liệu thất bại.

**Câu hỏi kiểm tra:** nếu bảng `response-fields` mô tả đúng hai field nhưng JSON response thực tế thêm một field công khai thứ ba, chuyện gì nên xảy ra? Với tài liệu hóa nghiêm ngặt, test phải phát hiện field chưa được mô tả. Sau khi xác minh đây là thay đổi hợp đồng có chủ đích, cập nhật cả assertion phù hợp và descriptor, rồi sinh lại tài liệu.

## 11. Tổng kết

- **Operation** là một lần trao đổi HTTP được kiểm thử và ghi nhận; **identifier** gắn operation đó với một thư mục snippet ổn định.
- Một operation có thể sinh nhiều **snippet**: request, response, tham số, header, payload. Các **descriptor** bổ sung ý nghĩa và giúp kiểm tra sự khớp giữa dữ liệu với tài liệu.
- **Trang tài liệu** kết hợp snippet với phần giải thích nghiệp vụ, điều kiện áp dụng và danh sách tình huống thành công/lỗi.
- Kết nối test → snippet → Asciidoctor/Markdown → CI giúp tài liệu có thể tái tạo và kiểm chứng, với mức bảo đảm tương ứng phạm vi test đã viết.
