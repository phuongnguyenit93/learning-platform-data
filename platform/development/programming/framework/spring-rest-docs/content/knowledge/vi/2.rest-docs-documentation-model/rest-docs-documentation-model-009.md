# Thiết kế tài liệu để thay đổi implementation ít ảnh hưởng

Tài liệu API thường phải sống lâu hơn một phiên bản controller, service hoặc cấu trúc database. Nếu trang REST Docs phụ thuộc quá chặt vào tên class, tên method nội bộ, cách tổ chức package hay dữ liệu fixture của một lần test, những thay đổi implementation không làm thay đổi hợp đồng API cũng có thể kéo theo nhiều chỉnh sửa tài liệu không cần thiết.

Mục tiêu thiết kế tốt là **để tài liệu mô tả hợp đồng mà client sử dụng, trong khi implementation có thể được tái cấu trúc độc lập khi hợp đồng vẫn giữ nguyên**. Spring REST Docs hỗ trợ mục tiêu này bằng cách sinh các ví dụ HTTP và bảng mô tả từ test; người viết quyết định identifier, descriptor, cách biên soạn trang và mức thông tin nội bộ nào được đưa ra. Cần thiết kế ranh giới đó có chủ đích.

Bài học thuộc chương **Mô hình tài liệu** của module `SPRING_REST_DOCS`. Module thực hành sinh tài liệu REST API có thể kiểm chứng từ MockMvc, WebTestClient hoặc REST Assured, tạo snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown trong build và CI. Bài này tập trung vào cấu trúc tài liệu bền vững trước thay đổi implementation, cách kiểm soát phụ thuộc và cách phân biệt thay đổi nội bộ với thay đổi hợp đồng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt chi tiết implementation với thành phần công khai của hợp đồng HTTP.
2. Thiết kế trang tài liệu theo resource, operation và hành vi mà client quan sát được.
3. Chọn identifier và cấu trúc snippet ổn định khi controller/service/package được tái cấu trúc.
4. Tách fixture, assertion, descriptor và phần diễn giải nghiệp vụ để mỗi lớp có một trách nhiệm rõ.
5. Nhận biết thay đổi implementation nào không cần sửa tài liệu và thay đổi hợp đồng nào phải cập nhật test/snippet.
6. Dùng helper, template và include có kiểm soát để giảm lặp mà không che giấu sự khác nhau giữa endpoint.
7. Quản lý versioning, tương thích ngược và CI để phát hiện thay đổi API có ảnh hưởng client.

## 2. Ranh giới quan trọng: hợp đồng công khai và implementation nội bộ

Một API có thể được triển khai bằng controller MVC, service nhiều tầng, repository JPA, message broker và cache. Client chỉ giao tiếp qua hợp đồng HTTP mà server công bố: method, URI, query/path parameter, header, payload, status và ý nghĩa các trường.

Ví dụ client gọi:

```http
GET /api/orders/42
Accept: application/json
```

và nhận:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "CONFIRMED",
  "total": 189000,
  "currency": "VND"
}
```

Những điều thuộc hợp đồng có thể gồm:

- `GET /api/orders/{orderId}` là operation để đọc một đơn hàng.
- `orderId` xác định đơn hàng theo quy tắc public đã công bố.
- Response thành công chứa các field `id`, `status`, `total` và `currency` với kiểu và ý nghĩa đã mô tả.
- Các status lỗi và điều kiện phát sinh được định nghĩa rõ.
- Quyền truy cập, quy tắc tiền tệ và semantics của trạng thái được mô tả theo nghiệp vụ.

Những điều sau thường thuộc implementation nội bộ:

- Controller tên `OrderController` hay `PurchaseController`.
- Method Java tên `getOrder` hay `findById`.
- Service được chia thành bao nhiêu lớp.
- Repository dùng JPA, JDBC hay gọi dịch vụ khác.
- Package, module nội bộ, tên biến và cách cache.
- Dữ liệu được lấy qua một query hay nhiều query.

Khi những chi tiết nội bộ thay đổi nhưng HTTP behavior và semantics được bảo toàn, tài liệu public thường không nên thay đổi chỉ vì refactor.

| Chi tiết | Thuộc hợp đồng API? | Có nên xuất hiện trong tài liệu client? |
| --- | --- | --- |
| HTTP method và URI | Có | Có |
| Tên và ý nghĩa path/query parameter | Có | Có |
| Request/response header được công bố | Có | Có |
| JSON field, kiểu, nullability và semantics | Có | Có |
| HTTP status và điều kiện xảy ra | Có | Có |
| Quyền, giới hạn, side effect và retry semantics | Có, nếu là cam kết client cần biết | Có |
| Tên controller/service/repository | Thường không | Không, trừ tài liệu kiến trúc nội bộ riêng |
| Tên table/database column | Thường không | Không |
| Số lớp nội bộ hoặc thuật toán cache | Không | Không |
| Class fixture hoặc method test | Không | Không |

**Nguyên tắc:** tài liệu REST API công khai nên giúp client sử dụng giao diện ổn định, không bắt client hiểu cách server được tổ chức bên trong.

## 3. Tổ chức tài liệu quanh resource và operation

Một cấu trúc bền vững bắt đầu từ cách client nhìn API, không phải sơ đồ package của ứng dụng.

Ví dụ cấu trúc nội dung:

```text
API Reference
├── Tổng quan
│   ├── Base URL
│   ├── Xác thực
│   ├── Quy ước lỗi
│   └── Phân trang
├── Đơn hàng
│   ├── Tra cứu đơn hàng
│   ├── Tạo đơn hàng
│   ├── Cập nhật đơn hàng
│   └── Hủy đơn hàng
└── Sản phẩm
    ├── Tra cứu sản phẩm
    └── Tìm kiếm sản phẩm
```

Mỗi trang operation nên trả lời: client gọi cái gì, cần gửi gì, server có thể trả những kết quả nào, các field mang ý nghĩa gì và có điều kiện nghiệp vụ nào. Cấu trúc này vẫn có ý nghĩa dù controller được đổi tên hoặc endpoint được chuyển sang một module nội bộ khác.

### 3.1. Tách phần dùng chung khỏi phần riêng của operation

Các nội dung có thể dùng chung:

- Quy tắc xác thực và truyền token.
- Định dạng lỗi chung.
- Quy ước timestamp, tiền tệ và mã định danh.
- Phân trang, sorting và filter.
- Chính sách retry hoặc idempotency nếu áp dụng rộng.
- Các header tương quan request.

Các nội dung riêng operation:

- Ý nghĩa của path/query parameter.
- Request payload và response fields.
- Status cụ thể của operation.
- Điều kiện nghiệp vụ, quyền và side effect của hành động đó.

Một trang tổng quan có thể giải thích định dạng lỗi chuẩn. Trang `POST /api/orders` chỉ cần chỉ ra error code nào áp dụng cho request này và liên kết về phần quy ước lỗi. Tránh copy cùng một đoạn quy tắc chung vào mọi trang; khi đổi chính sách, copy ở nhiều nơi dễ lệch nhau.

### 3.2. Không để cấu trúc tài liệu phụ thuộc cấu trúc package

Ví dụ một implementation ban đầu:

```text
com.example.orders
├── web/OrderController.java
├── service/OrderService.java
└── persistence/OrderRepository.java
```

Sau tái cấu trúc thành:

```text
com.example.sales
├── api/OrderResource.java
├── application/QueryOrder.java
└── adapter/OrderStore.java
```

Nếu HTTP contract không thay đổi thì các trang `orders-get-success`, mô tả `orderId` và bảng response fields có thể giữ nguyên. Chỉ các test setup/import/fixture có thể cần sửa để vẫn thực thi cùng operation. Tài liệu không nên include đường dẫn source code nội bộ như `com.example.orders.web.OrderController` làm phần định nghĩa endpoint.

## 4. Thiết kế identifier ổn định, có nghĩa với người đọc

Identifier trong `document("orders-get-success", ...)` là khóa nối từ test tới thư mục snippet. Nên đặt tên theo resource, hành động và tình huống public:

```text
<resource>-<method-or-action>-<scenario>
```

Ví dụ:

| Identifier | Mục đích |
| --- | --- |
| `orders-get-success` | Đọc đơn hàng thành công |
| `orders-get-not-found` | Không tìm thấy đơn hàng |
| `orders-create-success` | Tạo đơn hàng thành công |
| `orders-create-invalid` | Dữ liệu tạo đơn không hợp lệ |
| `orders-cancel-conflict` | Hủy đơn bị xung đột trạng thái |

Không nên gắn identifier với tên test class/method hoặc tên controller nội bộ, ví dụ `order-controller-getOrder-test`. Nếu test được chuyển sang test suite khác hay controller đổi tên, tên snippet sẽ thay đổi dù operation public vẫn là một.

Identifier ổn định cũng không có nghĩa cố giữ tên khi contract thay đổi bản chất. Nếu operation public được đổi hoặc chia thành hành vi khác, cần đánh giá lại tên và tất cả include liên quan.

### 4.1. Phân biệt tên identifier với fixture

Một test hiện dùng ID 42 nhưng sau này fixture đổi thành 1001 để tránh va chạm dữ liệu. Nếu operation vẫn là “đọc đơn hàng thành công”, identifier `orders-get-success` vẫn phù hợp. Đừng đặt `orders-get-42` chỉ vì giá trị fixture cụ thể.

Giá trị trong snippet có thể thay đổi giữa các lần chạy khi dữ liệu ví dụ được thay đổi. Nếu muốn ví dụ ổn định, kiểm soát fixture hoặc chuẩn hóa dữ liệu trình bày; không biến tên operation thành một bản sao của dữ liệu test.

## 5. Thiết kế test và descriptor theo hợp đồng

Test cần tạo ra HTTP behavior và kiểm tra những điều quan trọng với client. Descriptor mô tả các thành phần xuất hiện trong request/response và tạo bảng snippet. Phần implementation setup nên được cách ly khỏi định nghĩa operation.

### 5.1. Ví dụ test MockMvc

Giả sử API công bố response đơn hàng:

```json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 189000,
  "currency": "VND"
}
```

Đoạn test tài liệu hóa có thể là:

```java
@Test
void getOrder_success() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("CONFIRMED"))
        .andExpect(jsonPath("$.currency").value("VND"))
        .andDo(document("orders-get-success",
            pathParameters(
                parameterWithName("orderId")
                    .description("Mã định danh đơn hàng")
            ),
            responseFields(
                fieldWithPath("id")
                    .type(JsonFieldType.NUMBER)
                    .description("Mã đơn hàng"),
                fieldWithPath("status")
                    .type(JsonFieldType.STRING)
                    .description("Trạng thái nghiệp vụ"),
                fieldWithPath("total")
                    .type(JsonFieldType.NUMBER)
                    .description("Tổng tiền theo quy tắc tài chính của API"),
                fieldWithPath("currency")
                    .type(JsonFieldType.STRING)
                    .description("Mã tiền tệ")
            )
        ));
}
```

Để `pathParameters(...)` đọc được `{orderId}` trong URI template, dùng `RestDocumentationRequestBuilders.get` của Spring REST Docs. Test cần được thiết lập với `RestDocumentationExtension` hoặc cấu hình phù hợp cho loại test client đang dùng.

Các chi tiết như `mockMvc` được khởi tạo bằng standalone setup hay application context, service được mock hay dùng thật thuộc **test configuration**. Có thể thay đổi chúng khi refactor để tăng phạm vi test mà không cần đổi phần mô tả API nếu HTTP contract không thay đổi.

### 5.2. Giữ descriptor mô tả semantics public

Tránh mô tả một field bằng ngôn ngữ nội bộ:

```java
fieldWithPath("total")
    .description("Giá trị lấy từ cột ORD_TOT của bảng ORDERS")
```

Cách mô tả này làm lộ chi tiết database và khóa tài liệu vào schema nội bộ. Nên mô tả theo khái niệm client cần hiểu:

```java
fieldWithPath("total")
    .type(JsonFieldType.NUMBER)
    .description("Tổng tiền của đơn hàng theo đơn vị currency")
```

Nếu client cần biết total gồm thuế/phí hay cách làm tròn, hãy viết rõ trong phần giải thích hợp đồng và có test nghiệp vụ phù hợp. Không dùng tên cột database để thay cho semantics.

### 5.3. Tách test setup có thể tái sử dụng

Có thể dùng base configuration, fixture builder hoặc helper để giảm lặp khi nhiều operation dùng chung một môi trường. Tuy nhiên, helper không nên giấu những khác biệt quan trọng của request/response.

Nên tái sử dụng:

- Cách khởi tạo Spring REST Docs extension.
- Cấu hình MockMvc/WebTestClient.
- Fixture builder cho resource có dữ liệu hợp lệ.
- Descriptor chung thực sự giống nhau như header trace hoặc field trong error envelope.

Không nên gom mọi operation vào một helper mơ hồ nhận nhiều cờ boolean như `isSuccess`, `isAdmin`, `useLegacyPayload` nếu điều đó làm người đọc không hiểu test đang mô tả hành vi nào. Hãy giữ test cụ thể, helper chỉ giảm phần setup lặp.

## 6. Viết phần tài liệu nguồn không kéo implementation ra ngoài

Một trang AsciiDoc có thể giữ cấu trúc ổn định:

```asciidoc
[[orders-get]]
=== Tra cứu đơn hàng

Lấy biểu diễn hiện tại của một đơn hàng mà người gọi có quyền truy cập.

==== Request
include::{snippets}/orders-get-success/http-request.adoc[]

==== Path parameters
include::{snippets}/orders-get-success/path-parameters.adoc[]

==== Response thành công
include::{snippets}/orders-get-success/http-response.adoc[]

==== Response fields
include::{snippets}/orders-get-success/response-fields.adoc[]

==== Không tìm thấy
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

Trang mô tả các khái niệm công khai. Không viết “controller gọi OrderService rồi OrderRepository truy vấn bảng ORDERS” trong API Reference. Nếu đội kỹ thuật cần thông tin đó, nó thuộc tài liệu kiến trúc hoặc hướng dẫn phát triển nội bộ với mục tiêu riêng.

### 6.1. Giữ cấu trúc section theo câu hỏi của client

Một bố cục dễ duy trì:

1. **Mục đích:** Resource/operation phục vụ việc gì?
2. **Điều kiện:** Ai có thể gọi, điều kiện đầu vào và tiền điều kiện?
3. **Request:** Ví dụ HTTP, path/query, header, body.
4. **Response:** Status, header, body và các field.
5. **Lỗi:** Các response có ý nghĩa và cách xử lý.
6. **Quy tắc nghiệp vụ:** Trạng thái, đơn vị, tính lặp lại, side effect.
7. **Liên kết:** Quy tắc chung hoặc operation liên quan.

Không cần lặp mọi phần nếu không áp dụng; ví dụ GET không có request body thì không thêm bảng request fields trống.

### 6.2. Dùng attribute và include thay cho đường dẫn tuyệt đối

Dùng `{snippets}` giúp thay đổi output directory qua cấu hình build mà không sửa tất cả trang. Không hard-code đường dẫn máy cá nhân hoặc đường dẫn tuyệt đối như `C:/workspace/project/build/generated-snippets`.

Cũng nên tập trung khai báo attribute ở task biên soạn, để các trang chỉ tham chiếu `{snippets}/<identifier>/<file>`. Nếu output chuyển từ Gradle sang Maven hoặc đổi module build folder, thay đổi thường nằm ở cấu hình build thay vì hàng loạt source page.

## 7. Phân biệt refactor nội bộ với thay đổi hợp đồng

Không phải mọi thay đổi code đều có cùng ảnh hưởng tới tài liệu. Ma trận sau giúp xác định việc cần làm:

| Thay đổi | HTTP contract có thể giữ nguyên? | Tác động tài liệu thường gặp |
| --- | --- | --- |
| Đổi tên controller hoặc method Java | Có | Không cần sửa trang/identifier nếu test vẫn mô tả cùng operation |
| Chuyển package hoặc module | Có | Sửa import/test setup; snippet và trang có thể giữ nguyên |
| Thay JPA bằng JDBC hoặc HTTP client khác | Có | Không cần sửa tài liệu nếu observable behavior không đổi |
| Tách một service thành nhiều component | Có | Không cần sửa tài liệu client |
| Thay cách lưu cache | Có | Không cần sửa tài liệu nếu semantics giữ nguyên |
| Đổi URI hoặc HTTP method | Không, thường là breaking/change contract | Sửa trang, test, identifier nếu phù hợp và thông tin migration |
| Đổi tên hoặc kiểu JSON field | Có ảnh hưởng hợp đồng | Cập nhật descriptor, test, snippet và trang; đánh giá tương thích |
| Thay status lỗi hoặc điều kiện lỗi | Có ảnh hưởng hợp đồng | Cập nhật case test và phần giải thích |
| Thay ý nghĩa `total` nhưng giữ kiểu number | Có ảnh hưởng semantics | Cập nhật lời giải thích và test nghiệp vụ |
| Thay quyền truy cập | Có ảnh hưởng hành vi public | Cập nhật test security, lỗi và mô tả quyền |
| Thêm header bắt buộc cho client | Có ảnh hưởng request contract | Cập nhật request tests, descriptors, ví dụ và hướng dẫn |

### 7.1. Phép thử “client có nhận ra thay đổi không?”

Trước khi quyết định phải sửa tài liệu hay không, hãy hỏi:

- Client có phải thay method, URL, header, payload hoặc cách parse response không?
- Có status mới hoặc điều kiện lỗi mới mà client phải xử lý không?
- Ý nghĩa của field có thay đổi dù tên và kiểu vẫn giữ nguyên không?
- Quy tắc auth, retry, idempotency hoặc side effect có thay đổi không?
- Một hành vi mà client dựa vào có còn được bảo đảm không?

Nếu câu trả lời là có, đó có thể là thay đổi hợp đồng cần tài liệu hóa. Nếu thay đổi chỉ ở cách server tổ chức class và không thay đổi điều client quan sát/được cam kết, thường không cần thay đổi API Reference.

### 7.2. Ví dụ đổi implementation mà tài liệu giữ nguyên

Trước refactor:

```java
@GetMapping("/api/orders/{id}")
OrderDto find(@PathVariable long id) {
    return orderService.find(id);
}
```

Sau refactor:

```java
@GetMapping("/api/orders/{orderId}")
OrderRepresentation query(@PathVariable long orderId) {
    return queryOrder.execute(orderId);
}
```

Nếu mapping URI, response, status, header và semantics public thực sự giữ nguyên thì nội dung tài liệu có thể không đổi. Tuy nhiên, tên biến trong URI template hoặc cách builder giữ template có thể tác động đến descriptor path parameter. Cần đảm bảo test vẫn ghi nhận cùng path contract `{orderId}` hoặc descriptor được cập nhật phù hợp với template thật. Không được bỏ qua lỗi test chỉ vì cho rằng đó là refactor nội bộ.

## 8. Giữ snippet bền vững khi implementation thay đổi

Snippet là output của test, nên output có thể thay đổi nếu cách dựng fixture hoặc môi trường test thay đổi. Để giảm churn không có ý nghĩa:

- Dùng fixture xác định và độc lập.
- Chuẩn hóa timestamp, hostname, port hoặc request ID nếu chúng không phải điểm cần minh họa.
- Tránh đưa tên class, stack trace hoặc câu lỗi nội bộ vào response public.
- Dùng identifier theo operation public, không theo tên test class.
- Chỉ mô tả những header/field thuộc hợp đồng.
- Giữ test có assertion cho giá trị nghiệp vụ quan trọng, đừng chỉ ghi response mà không kiểm tra.

Spring REST Docs hỗ trợ preprocessors như `preprocessRequest(prettyPrint())` và `preprocessResponse(prettyPrint())`. Có thể dùng preprocessor để định dạng JSON, thay dữ liệu động hoặc loại bỏ header nhạy cảm khỏi snippet. Preprocessing không được biến một response sai thành ví dụ có vẻ đúng; assertion cần chạy trên kết quả thực tế trước khi tài liệu hóa.

### 8.1. Không đưa chi tiết nội bộ vào output vô tình

Ví dụ response lỗi không nên công khai stack trace:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng"
}
```

Tránh đưa response kiểu:

```json
{
  "exception": "com.example.orders.persistence.OrderNotFoundException",
  "sql": "select * from orders where id = ?",
  "message": "..."
}
```

Nếu ứng dụng thật đang lộ thông tin nội bộ, cần sửa implementation và hợp đồng lỗi trước khi sinh tài liệu public. Việc che dữ liệu trong snippet có thể giúp không xuất bản bí mật, nhưng không thay thế việc sửa response thực tế nếu nó là lỗ hổng hoặc vi phạm hợp đồng.

## 9. Tái sử dụng helper và template mà không làm mất đặc thù

Khi có nhiều operation, có thể dùng helper để tạo descriptor phổ biến:

```java
static RequestHeadersSnippet commonRequestHeaders() {
    return requestHeaders(
        headerWithName("Accept")
            .description("Media type client chấp nhận"),
        headerWithName("X-Request-Id")
            .description("Mã tương quan nếu client truyền")
            .optional()
    );
}
```

Sau đó dùng trong nhiều test:

```java
.andDo(document("orders-get-success",
    commonRequestHeaders(),
    pathParameters(/* descriptor riêng */),
    responseFields(/* descriptor riêng */)
));
```

Đây là ví dụ về helper test, cần điều chỉnh import và kiểu snippet theo phiên bản REST Docs. Chỉ dùng chung khi các header và semantics thực sự giống nhau trên những endpoint đó. Một header bắt buộc ở POST nhưng tùy chọn ở GET không nên bị gom vào một helper chung khiến tài liệu sai.

Template Asciidoctor cũng có thể tái sử dụng để thống nhất bố cục. Nhưng template không nên ép mọi endpoint có cùng response/error section nếu endpoint đó không hỗ trợ. Tái sử dụng giảm lặp, còn phần đặc thù phải được thể hiện rõ ở test và trang.

## 10. Versioning và tương thích ngược

Khi hợp đồng cần thay đổi, cần quyết định đó là thay đổi tương thích hay không và cách client chuyển đổi.

Một số ví dụ:

| Thay đổi | Rủi ro tương thích thường gặp | Hành động tài liệu |
| --- | --- | --- |
| Thêm field response tùy chọn | Thường thấp với client bỏ qua field lạ, nhưng không phải mọi client đều như vậy | Cập nhật schema/example và ghi rõ field mới |
| Xóa field bắt buộc | Cao | Cần migration/versioning và tài liệu thay đổi |
| Đổi kiểu field | Cao | Công bố version hoặc hướng dẫn migration phù hợp |
| Đổi semantics field mà không đổi kiểu/tên | Rất cao vì client không thấy thay đổi hình dạng | Nêu rõ semantics mới và cách client điều chỉnh |
| Thêm query parameter tùy chọn | Thường thấp | Mô tả mặc định và hành vi khi có tham số |
| Thêm request header bắt buộc | Cao với client cũ | Công bố điều kiện áp dụng và hướng dẫn cập nhật |
| Thêm status lỗi mới | Client có thể chưa xử lý | Bổ sung tình huống lỗi và quy tắc retry/hiển thị |

Nếu có nhiều phiên bản API, tổ chức tài liệu theo version hoặc nhóm output directory tương ứng. Đừng include snippet của version 2 vào trang version 1 chỉ vì hai operation có tên gần giống nhau. Cấu trúc version và attribute cần rõ ràng để không trộn schema.

### 10.1. Tài liệu migration cũng là một phần của hợp đồng thay đổi

Khi có breaking change, tài liệu endpoint mới chưa đủ. Client đang sử dụng version cũ cần biết:

- Điều gì đã thay đổi?
- Thời điểm hoặc version nào thay đổi có hiệu lực?
- Client phải cập nhật request/response handling ra sao?
- Có giai đoạn song song hay thời hạn ngừng version cũ không?
- Có ví dụ trước/sau cho thao tác quan trọng không?

Các thông tin này thường nằm trong release notes/migration guide riêng nhưng được liên kết từ API Reference.

## 11. CI giúp bảo vệ ranh giới tài liệu

Pipeline nên chạy test tạo snippet trước khi render:

```text
Checkout source
      │
      ▼
Clean generated output
      │
      ▼
Run HTTP documentation tests
      │
      ├── Assertion/descriptor failure → Fail
      │
      ▼
Generate snippets
      │
      ▼
Render Asciidoctor/Markdown
      │
      ├── Missing include/link → Fail
      │
      ▼
Review public content and compatibility
      │
      ▼
Publish API docs
```

Các điểm nên kiểm tra trong CI:

1. Test documentation có được chạy, không bị skip ngoài ý muốn?
2. Output directory có đúng như cấu hình?
3. Identifier và include có trỏ tới snippet mới tạo?
4. Test có thất bại khi response public lệch assertion hoặc descriptor?
5. Trang có render từ source và snippet của cùng build không?
6. Output có chứa hostname nội bộ, token hoặc chi tiết implementation không?
7. Thay đổi hợp đồng có cập nhật release/migration notes nếu cần?

CI có thể phát hiện nhiều lỗi liên kết kỹ thuật nhưng không tự đánh giá ý nghĩa mọi thay đổi. Review code và nội dung hợp đồng vẫn cần xác định refactor có vô tình làm thay đổi behavior không, cũng như client cần được thông báo điều gì.

## 12. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đổi tên controller làm hàng loạt trang phải sửa | Identifier/include phụ thuộc tên class nội bộ | Chuyển identifier về resource/method/scenario public |
| Refactor database làm mô tả API thay đổi | Descriptor diễn giải theo column/table | Viết mô tả theo semantics client nhìn thấy |
| Test đổi identifier nhưng trang không tìm thấy snippet | Include còn giữ đường dẫn cũ | Đồng bộ identifier và include trong cùng thay đổi |
| Test mới ghi đè snippet cũ | Hai operation dùng chung identifier | Tách theo scenario; kiểm tra test chạy song song |
| Snippet thay đổi mỗi lần build | Fixture hoặc dữ liệu động không ổn định | Kiểm soát fixture và preprocessor |
| Dùng helper khiến mọi endpoint có cùng mô tả sai | Gom cả phần đặc thù vào template chung | Chỉ tái sử dụng phần thật sự có cùng contract |
| Tài liệu có stack trace hoặc tên class | Response lỗi hoặc snippet làm lộ implementation | Sửa response public, lọc output và thêm kiểm tra |
| Thay đổi semantics không làm test fail | Test chỉ kiểm tra kiểu/status | Bổ sung assertion nghiệp vụ và cập nhật diễn giải |
| Trang version 1 dùng response version 2 | Attribute/output directory lẫn nhau | Phân tách output và include theo version |
| Refactor làm test không còn đại diện hệ thống | Test setup quá cô lập | Bổ sung integration test thích hợp và ghi rõ phạm vi |
| CI render từ snippet cũ | Output không được làm sạch hoặc dependency task sai | Clean output, chạy test rồi mới render |

## 13. Bài thực hành: refactor implementation nhưng giữ hợp đồng

Giả sử API công bố operation `GET /api/orders/{orderId}` với:

- Response `200` có `id`, `status`, `total`, `currency`.
- Response `404` theo schema lỗi chung.
- Path parameter `orderId` có mô tả nghiệp vụ rõ.
- Snippet được lưu trong `orders-get-success` và `orders-get-not-found`.

Nhóm dự định đổi cấu trúc nội bộ từ controller/service/repository sang resource/application/adapter, thay JPA bằng JDBC, và đổi tên class fixture. Hợp đồng HTTP dự kiến không thay đổi.

### Nhiệm vụ

1. Liệt kê các chi tiết nội bộ có thể thay đổi mà không tác động hợp đồng.
2. Chạy lại test tài liệu hóa và xác nhận status, header, payload và field vẫn đáp ứng assertion/descriptor.
3. Giữ nguyên identifier nếu operation public không đổi.
4. Kiểm tra output snippet mới; phân biệt khác biệt chỉ do request ID/timestamp với khác biệt contract.
5. Chỉ cập nhật fixture/preprocessor nếu dữ liệu ví dụ không còn ổn định; không thay đổi mô tả public nếu semantics giữ nguyên.
6. Sau đó thử đổi kiểu `total` từ number sang string. Xác định test/descriptor nào phải fail và tài liệu nào cần cập nhật.
7. Viết một ghi chú migration nêu ảnh hưởng tới client nếu thay đổi kiểu được chấp thuận.

### Tiêu chí hoàn thành

- Refactor nội bộ không khiến API Reference phải thay đổi không cần thiết.
- Test vẫn bảo vệ request/response theo hợp đồng.
- Identifier và include vẫn ổn định, không trỏ tới output cũ.
- Thay đổi thực sự ảnh hưởng client bị phát hiện và được tài liệu hóa.
- Những chi tiết implementation không cần thiết không lọt vào tài liệu public.

## 14. Ghi nhớ

- Thiết kế tài liệu theo **hợp đồng HTTP và góc nhìn client**, không theo tên class, package, service hoặc schema database nội bộ.
- Identifier nên gắn với **resource, method/action và scenario** để test có thể chuyển vị trí mà trang tài liệu không phải đổi nếu operation vẫn giữ nguyên.
- Test setup, fixture, descriptor và phần diễn giải nghiệp vụ nên có ranh giới rõ; helper chỉ tái sử dụng phần contract thật sự giống nhau.
- Phân biệt refactor implementation với thay đổi method, URI, status, header, schema, semantics, quyền hoặc side effect.
- Khi hợp đồng đổi, cập nhật test, descriptor, snippet, trang và migration guidance; khi chỉ implementation đổi, vẫn chạy test để xác nhận behavior public được bảo toàn.
- CI giúp tái tạo và kiểm tra liên kết tài liệu; review hợp đồng vẫn cần đánh giá tính tương thích và ý nghĩa đối với client.
