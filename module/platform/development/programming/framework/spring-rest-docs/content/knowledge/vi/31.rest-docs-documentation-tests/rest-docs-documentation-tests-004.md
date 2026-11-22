# Phát hiện field thừa trong request hoặc response

## 1. Vì sao cần phát hiện field chưa được tài liệu hóa?

Một API có thể thay đổi payload theo thời gian. Developer thêm một field mới vào request DTO hoặc response model, nhưng quên cập nhật tài liệu. Khi đó client đọc tài liệu sẽ không biết field mới tồn tại, field có ý nghĩa gì hoặc có được phép gửi hay không.

Spring REST Docs giúp phát hiện kiểu drift này bằng cơ chế kiểm tra descriptor. Khi dùng `requestFields(...)` hoặc `responseFields(...)` ở chế độ strict, các field xuất hiện trong payload nhưng chưa được mô tả có thể làm bài test tài liệu hóa thất bại. Test buộc nhóm phải xem xét field mới trước khi cập nhật tài liệu.

Trong **SPRING_REST_DOCS**, module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Các test này sinh snippet cho request, response, payload, tham số và header; tài liệu sau đó được biên soạn bằng Asciidoctor/Markdown và đưa vào build/CI. Chương **Kiểm thử tài liệu** tập trung vào việc biến thay đổi payload thành tín hiệu kiểm tra rõ ràng.

Bài này giải thích cách phát hiện field thừa trong request hoặc response, cách xử lý khi field mới là hợp lệ, và khi nào nên dùng `ignored()` hoặc `relaxedRequestFields(...)` / `relaxedResponseFields(...)`.

Sau bài học, bạn có thể:

- Hiểu strict field documentation kiểm tra payload như thế nào.
- Nhận biết lỗi khi request hoặc response có field chưa được mô tả.
- Phân biệt field thừa với field descriptor bắt buộc nhưng bị thiếu.
- Dùng `ignored()` khi field đã biết nhưng không cần xuất hiện trong bảng.
- Dùng relaxed mode có chủ đích khi muốn cho phép field bổ sung.
- Tổ chức test để phát hiện thay đổi contract và cập nhật snippet trong CI.

## 2. Strict mode: descriptor phải bao phủ payload

Ví dụ request tạo sản phẩm:

```json
{
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "active": true
}
```

Test mô tả các field:

```java
requestFields(
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("price").description("Giá bán"),
    fieldWithPath("active").description("Sản phẩm đang được kinh doanh")
);
```

Với `requestFields(...)`, Spring REST Docs kiểm tra request payload so với tập descriptor. Nếu payload có thêm field `category` nhưng descriptor không có `category`, snippet generation sẽ thất bại với lỗi dạng `SnippetException` cho biết field chưa được tài liệu hóa.

Điều này rất hữu ích khi DTO được mở rộng:

```json
{
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "active": true,
  "category": "ACCESSORY"
}
```

Nếu test vẫn dùng descriptor cũ, strict mode báo rằng `category` chưa được mô tả. Nhóm phải quyết định:
- `category` là một phần public contract và cần thêm vào tài liệu;
- field nội bộ đã biết, cần được nhận diện nhưng không đưa vào bảng;
- hoặc operation thực sự cho phép field mở rộng chưa cần mô tả trong snippet này.

Không nên bỏ qua lỗi ngay lập tức. Field mới có thể ảnh hưởng client, validation, compatibility hoặc dữ liệu được lưu.

## 3. Phát hiện field thừa trong request bằng MockMvc

Giả sử endpoint `POST /api/products` nhận JSON và trả `201 Created`.

```java
@Test
void documentCreateProduct() throws Exception {
    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Mechanical Keyboard",
                  "price": 1290000,
                  "active": true,
                  "category": "ACCESSORY"
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("products-create",
            requestFields(
                fieldWithPath("name")
                    .description("Tên sản phẩm"),
                fieldWithPath("price")
                    .description("Giá bán"),
                fieldWithPath("active")
                    .description("Trạng thái kinh doanh")
            )
        ));
}
```

Trong ví dụ, request có `category` nhưng descriptor không có. Khi Spring REST Docs tạo request fields snippet, strict validation phát hiện field dư và test tài liệu hóa thất bại.

Thông báo cụ thể phụ thuộc phiên bản, nhưng thường chỉ ra một hoặc nhiều payload paths chưa được mô tả. Hãy đọc path trong exception để xác định field nào vừa xuất hiện.

### 3.1. Cập nhật descriptor khi field thuộc contract

Nếu `category` là field client được phép gửi, bổ sung descriptor:

```java
requestFields(
    fieldWithPath("name")
        .description("Tên sản phẩm"),
    fieldWithPath("price")
        .description("Giá bán"),
    fieldWithPath("active")
        .description("Trạng thái kinh doanh"),
    fieldWithPath("category")
        .description("Danh mục sản phẩm")
);
```

Chạy lại test. Khi payload và descriptor khớp, snippet được sinh với field mới.

Đây là quy trình review có chủ đích: thay đổi DTO/request payload kéo theo thay đổi test descriptor và tài liệu. Nếu field mới chưa nên public, cần xem lại DTO hoặc mapping thay vì tùy tiện đưa nó vào docs.

## 4. Phát hiện field thừa trong response

Cơ chế tương tự áp dụng cho response. Giả sử endpoint trả:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 1290000,
  "stock": 18
}
```

Test chỉ mô tả ba field đầu:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm"),
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("price").description("Giá bán")
);
```

Nếu response có thêm `stock`, strict `responseFields(...)` phát hiện field chưa được tài liệu hóa. Điều này quan trọng vì response field mới có thể là thay đổi public contract, dù endpoint vẫn trả status `200 OK`.

Ví dụ MockMvc:

```java
@Test
void documentGetProduct() throws Exception {
    mockMvc.perform(get("/api/products/{id}", 42)
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("products-get",
            responseFields(
                fieldWithPath("id")
                    .description("Mã sản phẩm"),
                fieldWithPath("name")
                    .description("Tên sản phẩm"),
                fieldWithPath("price")
                    .description("Giá bán")
            )
        ));
}
```

Nếu response fixture có `stock` nhưng descriptor không có, bước tạo response fields snippet thất bại. Bổ sung `fieldWithPath("stock").description(...)` nếu field đó thuộc response contract.

Strict mode giúp phát hiện field mới; nó không tự quyết định field đó có nên được public hay không. Quyết định vẫn cần review API.

## 5. Phân biệt field thừa và field bị thiếu

Có hai chiều kiểm tra khác nhau:

1. **Field thừa trong payload:** payload có path mà descriptor chưa khai báo.
2. **Field bắt buộc bị thiếu trong payload:** descriptor khai báo field nhưng request/response mẫu không có path đó.

Ví dụ:

| Payload | Descriptor | Kết quả strict |
| --- | --- | --- |
| Có `name`, `price` | Mô tả `name`, `price` | Khớp |
| Có thêm `category` | Chỉ mô tả `name`, `price` | Field thừa chưa mô tả |
| Chỉ có `name` | Mô tả `name`, `price` | `price` bị thiếu nếu descriptor required |
| Có `name`, không có `note` | `note` được `.optional()` | Hợp lệ |
| Có `name`, có `internalCode` | `internalCode` `.ignored()` | Được nhận diện, không đưa vào bảng |

Field descriptor mặc định được xem là required trong payload được tài liệu hóa. Nếu field có thể vắng, dùng `.optional()`:

```java
fieldWithPath("note")
    .description("Ghi chú bổ sung")
    .optional();
```

`.optional()` không cho phép field dư chưa khai báo. Nó chỉ cho phép descriptor của field đó vắng trong payload mẫu.

## 6. Dùng `ignored()` khi field đã biết nhưng không muốn xuất bảng

Có trường hợp payload chứa field kỹ thuật hoặc field không cần trình bày trong bảng, nhưng nhóm vẫn muốn strict mode nhận diện nó. Khi đó dùng `.ignored()`:

```java
requestFields(
    fieldWithPath("name")
        .description("Tên sản phẩm"),
    fieldWithPath("price")
        .description("Giá bán"),
    fieldWithPath("internalTrace")
        .description("Mã trace nội bộ")
        .ignored()
);
```

`internalTrace` đã được khai báo trong descriptor, nên không còn là field chưa biết. Tuy nhiên, nó không xuất hiện thành dòng trong snippet.

Điều này khác với relaxed mode:
- `.ignored()` khai báo rõ một field cụ thể và loại field đó khỏi bảng.
- relaxed mode cho phép các field chưa có descriptor xuất hiện trong payload.

Nếu field có thể vắng, có thể kết hợp `.optional().ignored()`:

```java
fieldWithPath("internalTrace")
    .description("Mã trace nội bộ nếu có")
    .optional()
    .ignored();
```

Chỉ dùng ignored cho field đã được review. Đừng dùng nó để che giấu một field public mới mà tài liệu cần giải thích.

## 7. Khi nào dùng relaxed mode?

Spring REST Docs cung cấp:

- `relaxedRequestFields(...)`
- `relaxedResponseFields(...)`

Các API này vẫn tạo snippet từ những descriptor được khai báo, nhưng cho phép payload có thêm field chưa được mô tả. Điều này hữu ích khi:
- Một endpoint có payload mở rộng và trang hiện tại chỉ mô tả một phần.
- Có field phụ trợ do module khác quản lý.
- Nhóm đang tài liệu hóa một tập con của response lớn.
- API chủ đích hỗ trợ thêm field tương thích mà client có thể bỏ qua.

Ví dụ:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
    fieldWithPath("name")
        .description("Tên sản phẩm"),
    fieldWithPath("price")
        .description("Giá bán")
);
```

Nếu payload có thêm `category`, `internalCode` hoặc field khác, relaxed mode không làm test thất bại chỉ vì các field đó chưa được descriptor liệt kê.

### 7.1. Đánh đổi của relaxed mode

Relaxed mode làm giảm khả năng phát hiện payload drift. Khi một developer thêm field mới, test có thể vẫn thành công dù tài liệu không nhắc tới field đó.

Do đó:
- Dùng strict mode cho tài liệu contract đầy đủ của public API.
- Dùng relaxed mode khi chủ đích chỉ mô tả một phần payload.
- Ghi rõ phần payload nào được bao phủ và phần nào không.
- Có thể bổ sung test contract riêng để theo dõi các field quan trọng nếu snippet cần relaxed.

Không dùng relaxed chỉ để “làm xanh” test sau khi strict mode phát hiện field mới. Trước hết hãy xác định field mới có ý nghĩa gì.

## 8. Strict và relaxed: bảng so sánh

| Cơ chế | Field đã mô tả | Field dư chưa mô tả | Field descriptor vắng mặt |
| --- | --- | --- | --- |
| `requestFields(...)` | Được kiểm tra và hiển thị | Có thể làm test thất bại | Required có thể làm test thất bại |
| `responseFields(...)` | Được kiểm tra và hiển thị | Có thể làm test thất bại | Required có thể làm test thất bại |
| `.optional()` | Được mô tả khi có mặt | Không ảnh hưởng field dư | Cho phép descriptor vắng |
| `.ignored()` | Được nhận diện | Không ảnh hưởng field khác | Vẫn required trừ khi optional |
| `relaxedRequestFields(...)` | Được mô tả | Được phép tồn tại | Descriptor vẫn tuân theo optional |
| `relaxedResponseFields(...)` | Được mô tả | Được phép tồn tại | Descriptor vẫn tuân theo optional |

Strict/relaxed là lựa chọn ở cấp snippet. Optional/ignored là thuộc tính của descriptor. Hiểu đúng phạm vi sẽ giúp tránh bỏ sót field cần công bố.

## 9. Field lồng nhau và mảng

Field dư không chỉ nằm ở cấp root. Ví dụ response:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "supplier": {
    "id": 7,
    "name": "Acme",
    "country": "VN"
  },
  "tags": ["keyboard", "accessory"]
}
```

Nếu descriptor chỉ mô tả:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm"),
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("supplier.id").description("Mã nhà cung cấp"),
    fieldWithPath("supplier.name").description("Tên nhà cung cấp"),
    fieldWithPath("tags").description("Danh sách nhãn")
);
```

Strict mode có thể phát hiện `supplier.country` chưa được mô tả. Path cần được đọc theo cấu trúc JSON thực tế, không phải tên thuộc tính Java nếu Jackson đã đổi tên.

Với mảng object, dùng path như `items[].sku` và `items[].quantity`. Nếu có field mới `items[].discount`, descriptor cũng cần được cập nhật nếu snippet strict mô tả đầy đủ phần tử.

Nếu một object con được tài liệu hóa như một khối tổng quát bằng `subsectionWithPath(...)`, quy tắc mô tả các field con có thể khác so với việc liệt kê từng field. Hãy chọn cách mô tả theo mức chi tiết mong muốn và kiểm tra kết quả bằng test.

## 10. Ví dụ kiểm tra field thừa ở cả request và response

Một operation có thể sinh cả request fields và response fields. Strict descriptors ở hai phía phát hiện drift độc lập:

```java
mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "Mechanical Keyboard",
              "price": 1290000,
              "active": true
            }
            """))
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("price").description("Giá bán"),
            fieldWithPath("active").description("Trạng thái kinh doanh")
        ),
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm"),
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("price").description("Giá bán"),
            fieldWithPath("active").description("Trạng thái kinh doanh")
        )
    ));
```

Nếu request thêm `category` mà chưa có descriptor, request snippet thất bại. Nếu response thêm `stock` mà chưa có descriptor, response snippet thất bại. Một phía có descriptor đúng không làm phía còn lại tự động được kiểm tra.

Đây là lý do nên giữ request và response descriptors tách biệt, ngay cả khi hai payload có field trùng tên.

## 11. Cách xử lý khi test báo field thừa

Khi strict snippet báo field chưa được tài liệu hóa:

1. Đọc chính xác path được nêu trong exception.
2. Xác định field đến từ request hay response.
3. Kiểm tra DTO, serializer hoặc mapping tạo ra field đó.
4. Xác định field có thuộc public API contract không.
5. Nếu có, thêm descriptor và mô tả rõ ý nghĩa.
6. Nếu không cần công bố nhưng cần nhận diện, dùng `.ignored()` với lý do rõ ràng.
7. Nếu operation chỉ mô tả một phần payload theo thiết kế, cân nhắc relaxed mode và ghi rõ phạm vi.
8. Chạy lại test để sinh snippet mới và review diff.

Ví dụ thêm field:

```java
fieldWithPath("category")
    .type(JsonFieldType.STRING)
    .description("Danh mục sản phẩm");
```

Nếu field mới là lỗi lộ dữ liệu nội bộ, không nên thêm `.ignored()` ngay. Hãy xem xét loại field đó khỏi response hoặc sửa serializer/mapping trước khi cập nhật tài liệu.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test báo field không được tài liệu hóa | Payload có path mới nhưng descriptor chưa có | Review field rồi thêm descriptor hoặc ignored có chủ đích |
| Dùng `.optional()` nhưng field dư vẫn báo lỗi | Optional chỉ áp dụng cho descriptor đã khai báo | Thêm descriptor cho field dư hoặc dùng relaxed theo contract |
| Dùng `.ignored()` nhưng field vẫn required | Ignored không tự làm field optional | Thêm `.optional()` nếu payload mẫu có thể thiếu |
| Relaxed test pass nhưng docs thiếu field quan trọng | Relaxed cho phép field dư | Dùng strict hoặc bổ sung test contract riêng |
| Request fields đúng nhưng response fields fail | Hai payload được kiểm tra độc lập | Cập nhật descriptor đúng phía |
| Field nested không tìm thấy | Path descriptor không khớp JSON thực tế | Dùng path đầy đủ như `supplier.country` |
| Field mảng không khớp | Dùng sai cú pháp path | Dùng `items[].sku` cho phần tử mảng |
| Field Java có tên khác JSON | Jackson naming strategy hoặc `@JsonProperty` đổi tên | Tài liệu hóa JSON path trên wire |
| Field nội bộ xuất hiện trong response | DTO/serializer đang expose dữ liệu ngoài ý muốn | Sửa response model; không che bằng ignored nếu đó là rò rỉ |
| Test không chạy document snippet | Test chỉ assert HTTP, chưa đăng ký `document(...)` | Gắn snippet và descriptors vào operation |
| CI không phát hiện thay đổi | Test không được chạy hoặc snippet dùng relaxed | Kiểm tra task dependency và strict coverage |

## 13. Tích hợp Asciidoctor và build/CI

Khi test strict thành công, snippet fields được sinh dưới operation directory:

```text
build/generated-snippets/
└── products-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
```

Trang Asciidoctor include snippet:

```adoc
= Product API
:toc: left

== Tạo sản phẩm

=== Request fields
include::{snippets}/products-create/request-fields.adoc[]

=== Response fields
include::{snippets}/products-create/response-fields.adoc[]
```

Với Gradle và plugin Asciidoctor đã cấu hình:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Luồng CI:

```text
HTTP documentation tests
          |
          v
requestFields / responseFields
          |
          v
So sánh payload với descriptors
          |
          +---- Field dư chưa mô tả -> Test FAIL
          |
          +---- Descriptor thiếu required -> Test FAIL
          |
          v
Generated snippets
          |
          v
Asciidoctor / bước xuất Markdown
          |
          v
Review và publish
```

CI chỉ phát hiện drift nếu test tài liệu hóa được chạy và snippet đang dùng strict mode. Nếu toàn bộ operation đều chuyển sang relaxed, field mới có thể lọt qua mà không có review.

## 14. Bài thực hành

Với endpoint `POST /api/products`:

1. Viết request JSON có `name`, `price`, `active`.
2. Dùng `requestFields(...)` mô tả đúng ba field và chạy test.
3. Thêm field `category` vào request nhưng chưa thêm descriptor; quan sát lỗi strict mode.
4. Bổ sung descriptor cho `category` và xác nhận snippet được tạo.
5. Thêm `internalTrace` vào payload test, khai báo `.ignored()` và xác nhận field không xuất hiện trong bảng.
6. Thử bỏ field `note` được khai báo `.optional()`; xác nhận test vẫn tạo snippet.
7. Thêm field `stock` vào response nhưng không cập nhật `responseFields(...)`; quan sát lỗi ở response snippet.
8. Thử `relaxedResponseFields(...)`, quan sát test cho phép field dư và đánh giá liệu lựa chọn đó có phù hợp contract.
9. Tạo field lồng `supplier.country` rồi kiểm tra path descriptor.
10. Chạy test trong CI và xác nhận build thất bại khi một field public mới chưa được review.

### Câu hỏi tự đánh giá

- Strict `requestFields(...)` phát hiện điều gì khi payload có field mới?
- `responseFields(...)` kiểm tra request hay response?
- Field dư khác descriptor required bị thiếu như thế nào?
- `.optional()` có cho phép field chưa khai báo không?
- `.ignored()` khác relaxed mode ở điểm nào?
- Khi nào nên dùng `relaxedRequestFields(...)` hoặc `relaxedResponseFields(...)`?
- Vì sao field lồng nhau cần path khớp JSON trên wire?
- Nếu field mới là dữ liệu nội bộ bị lộ trong response, có nên chỉ đánh dấu ignored không?
- CI cần chạy bước nào để phát hiện payload drift?

**Ghi nhớ:** Strict `requestFields(...)` và `responseFields(...)` biến field chưa được mô tả thành tín hiệu lỗi trong test tài liệu hóa. Khi payload thêm field, hãy review ý nghĩa và quyết định công bố, ignored hay relaxed theo contract. `.optional()` xử lý field descriptor có thể vắng; `.ignored()` xử lý field đã biết không cần xuất bảng; relaxed mode cho phép field bổ sung chưa được mô tả.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): `requestFields`, `responseFields`, relaxed fields và field descriptors.
- [Spring REST Docs — `PayloadDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): API mô tả request/response payload.
- [Spring REST Docs — `FieldDescriptor` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): optional, ignored và metadata của field descriptor.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): include generated snippets vào tài liệu.
