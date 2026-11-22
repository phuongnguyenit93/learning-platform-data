# Thiếu field descriptor làm test thất bại

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, request-fields và response-fields không chỉ tạo bảng mô tả payload. Ở chế độ mặc định, chúng còn kiểm tra xem các field xuất hiện trong payload HTTP đã được xử lý trong descriptor hay chưa. Nếu endpoint trả thêm field nhưng tài liệu chưa đề cập, documentation test có thể thất bại. Cơ chế này giúp nhóm phát hiện schema drift và buộc người viết quyết định có công bố field mới, bỏ qua có chủ đích hay chỉ mô tả một phần payload.

Sau bài này, bạn có thể:

- Giải thích vì sao thiếu field descriptor làm strict payload snippet thất bại.
- Phân biệt field không được mô tả với descriptor trỏ tới field không tồn tại.
- Dùng fieldWithPath, subsectionWithPath, optional và ignored đúng mục đích.
- Chọn giữa requestFields/responseFields và các biến thể relaxed.
- Xử lý nested object, array và field mới trong response.
- Đọc lỗi của REST Docs để xác định descriptor cần cập nhật.
- Duy trì kiểm tra tài liệu chặt chẽ khi API phát triển.

## 1. Vì sao REST Docs kiểm tra field descriptor?

Giả sử API trả response:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90
}
```

Test mô tả response:

```java
this.mockMvc.perform(get("/api/products/{id}", 501)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm."),
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán.")
        )));
```

Các descriptor bao phủ cả ba field. REST Docs có thể sinh response-fields.adoc từ payload và descriptor đó.

Giả sử endpoint được thay đổi để trả thêm status:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90,
  "status": "ACTIVE"
}
```

Nếu test vẫn chỉ mô tả id, name và price, strict responseFields phát hiện status chưa được xử lý và làm documentation test thất bại. Người viết phải quyết định:

- Thêm descriptor và giải thích status trong tài liệu.
- Đánh dấu status ignored nếu có lý do rõ ràng để không công bố field đó.
- Dùng relaxedResponseFields nếu operation chỉ chủ ý mô tả một phần response.

Điểm quan trọng: field mới không được âm thầm lọt vào payload mà vẫn khiến tài liệu đầy đủ trông như đã cập nhật. Test yêu cầu nhóm review thay đổi schema trước khi chấp nhận tài liệu.

## 2. Strict requestFields và responseFields

Hai API mặc định:

```java
requestFields(
    fieldWithPath("name").description("Tên sản phẩm."),
    fieldWithPath("price").description("Giá bán.")
)
```

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm.")
)
```

Strict payload snippet thực hiện hai chiều đối chiếu:

1. **Payload sang descriptor:** field trong payload phải được mô tả hoặc xử lý bằng descriptor phù hợp. Field chưa được tài liệu hóa có thể làm snippet thất bại.
2. **Descriptor sang payload:** path đã khai báo phải tồn tại trong payload, trừ trường hợp descriptor được đánh dấu optional. Descriptor sai tên hoặc không còn xuất hiện cũng có thể làm test thất bại.

| Tình huống | Hành vi thường thấy ở strict mode |
| --- | --- |
| Payload có field mới chưa có descriptor | Báo field chưa được tài liệu hóa |
| Descriptor khai báo path không tồn tại | Báo descriptor path không tìm thấy |
| Descriptor có optional và field không xuất hiện | Được chấp nhận |
| Descriptor có ignored và field xuất hiện | Được xử lý nhưng không đưa vào bảng mô tả |

Strict mode là mặc định phù hợp khi snippet được kỳ vọng mô tả đầy đủ payload của operation.

## 3. Ví dụ lỗi khi response có field mới

Response thực tế:

```json
{
  "id": 501,
  "name": "Keyboard",
  "price": 129.90,
  "status": "ACTIVE"
}
```

Descriptor cũ:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm."),
    fieldWithPath("price").description("Giá bán.")
)
```

Khi chạy test, REST Docs có thể báo rằng payload chứa field chưa được tài liệu hóa, cụ thể là status. Nội dung lỗi chính xác có thể thay đổi theo phiên bản và cấu trúc payload, nhưng hướng xử lý là kiểm tra danh sách field được báo rồi đối chiếu với response thực tế.

Cập nhật descriptor:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm."),
    fieldWithPath("price").description("Giá bán."),
    fieldWithPath("status").description("Trạng thái hiện tại của sản phẩm.")
)
```

Nếu status là một phần hợp đồng mà client cần dùng, đây là cách xử lý đúng. Chạy lại documentation test để xác minh field mới được đưa vào snippet.

## 4. Field mới trong request

Giả sử request ban đầu:

```json
{
  "name": "Keyboard",
  "price": 129.90
}
```

API thêm field currency:

```json
{
  "name": "Keyboard",
  "price": 129.90,
  "currency": "VND"
}
```

Nếu requestFields chưa có descriptor currency, test phát hiện payload chứa field chưa được mô tả. Điều này hữu ích vì field request mới có thể làm thay đổi cách client tạo dữ liệu.

Descriptor được cập nhật:

```java
requestFields(
    fieldWithPath("name").description("Tên sản phẩm."),
    fieldWithPath("price").description("Giá bán."),
    fieldWithPath("currency").description("Mã tiền tệ ISO 4217.")
)
```

Nếu currency chỉ được gửi khi client muốn ghi đè đơn vị mặc định, descriptor có thể là optional:

```java
fieldWithPath("currency")
    .optional()
    .description("Mã tiền tệ; có thể bỏ qua để dùng đơn vị mặc định.")
```

Optional cho phép field vắng mặt trong payload test; nếu field xuất hiện, nó vẫn được mô tả. Không dùng optional để xử lý field mới mà chưa biết nó có thật sự tùy chọn hay không.

## 5. fieldWithPath và subsectionWithPath cho nested object

Payload lồng nhau:

```json
{
  "id": 501,
  "name": "Keyboard",
  "manufacturer": {
    "id": 8,
    "name": "Acme"
  }
}
```

### 5.1. Mô tả từng field con

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm."),
    fieldWithPath("manufacturer.id")
        .description("Mã nhà sản xuất."),
    fieldWithPath("manufacturer.name")
        .description("Tên nhà sản xuất.")
)
```

Khi dùng field path chi tiết, cần bao phủ các field con của object mà snippet đang mô tả. Nếu API thêm manufacturer.country mà descriptor chưa xử lý, strict mode có thể báo field mới.

### 5.2. Mô tả toàn bộ subsection

Nếu không cần liệt kê từng field con trong bảng hiện tại, dùng subsectionWithPath:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm."),
    subsectionWithPath("manufacturer")
        .description("Thông tin nhà sản xuất.")
)
```

subsectionWithPath đánh dấu toàn bộ object con là một phần được mô tả. Khi dùng nó, các field con được bao phủ bởi subsection descriptor thay vì phải liệt kê riêng trong cùng bảng.

Chọn một trong hai hướng theo mục đích:

- Dùng fieldWithPath chi tiết nếu người đọc cần biết từng thuộc tính.
- Dùng subsectionWithPath nếu tài liệu chỉ cần giải thích object như một đơn vị.

Không nên vừa mô tả subsection vừa thêm descriptor con chồng lấn trong cùng một descriptor set nếu không có chủ ý được REST Docs hỗ trợ.

## 6. Array và object trong array

Response:

```json
{
  "items": [
    {"id": 10, "name": "Keyboard"},
    {"id": 11, "name": "Mouse"}
  ]
}
```

Descriptor:

```java
responseFields(
    fieldWithPath("items").description("Danh sách sản phẩm."),
    fieldWithPath("items[].id").description("Mã sản phẩm."),
    fieldWithPath("items[].name").description("Tên sản phẩm.")
)
```

Path items[].name mô tả field name trong các phần tử của array. Nếu API thêm category trong từng phần tử, strict descriptor có thể phát hiện field đó và yêu cầu cập nhật.

Nếu muốn mô tả toàn bộ phần tử như một cấu trúc con, cân nhắc subsection descriptor phù hợp với payload và xác minh bằng test. Với array rỗng, fixture không cung cấp phần tử mẫu để kiểm tra các path bên trong; tạo test tài liệu với dữ liệu đại diện khi cần mô tả schema phần tử.

## 7. optional(), ignored() và relaxed: không cùng ý nghĩa

Ba cách này thường bị dùng thay thế cho nhau, nhưng giải quyết các vấn đề khác nhau.

| Cách làm | Khi nào dùng? | Field mới không được khai báo |
| --- | --- | --- |
| Thêm field descriptor | Field là một phần hợp đồng cần công bố | Được mô tả rõ ràng |
| optional() | Field đã biết nhưng có thể vắng mặt | Vẫn bị phát hiện nếu field khác chưa được mô tả |
| ignored() | Field được biết và chủ ý không đưa vào bảng snippet | Chỉ field được ignored được xử lý |
| relaxedRequestFields/relaxedResponseFields | Chỉ muốn mô tả một phần payload | Field khác chưa liệt kê được bỏ qua |

### 7.1. optional()

Ví dụ:

```java
fieldWithPath("description")
    .optional()
    .description("Mô tả; có thể không có.")
```

Descriptor vẫn nằm trong bảng snippet khi có mặt. optional chỉ điều chỉnh yêu cầu field phải xuất hiện trong payload test hay không.

### 7.2. ignored()

Ví dụ:

```java
fieldWithPath("internalVersion").ignored()
```

Field này được xử lý trong kiểm tra payload nhưng không hiển thị như field mô tả thông thường. ignored không phải cách ghi chú một field tùy chọn; cũng không tự động cho phép field đó vắng mặt.

Dùng ignored khi đã đánh giá field và có lý do để không đưa vào bảng hiện tại. Với field nhạy cảm, cần kiểm tra cả việc API có nên trả field đó hay không; ignored chỉ là quyết định hiển thị trong snippet, không phải biện pháp bảo mật.

### 7.3. relaxedRequestFields và relaxedResponseFields

Ví dụ response chỉ muốn nhấn mạnh id và name:

```java
relaxedResponseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm.")
)
```

Payload có thể chứa các field khác chưa được descriptor liệt kê mà không làm test thất bại vì thiếu mô tả. Tuy vậy, path đã khai báo vẫn cần hợp lệ trong payload, trừ khi optional.

Relaxed phù hợp với tài liệu theo góc nhìn hoặc một phần schema. Đổi strict sang relaxed chỉ để làm test xanh sẽ làm giảm khả năng phát hiện field mới.

## 8. Khi nào nên thêm descriptor và khi nào nên relaxed?

Dùng các câu hỏi sau để chọn:

1. Field mới có giúp client gửi request hoặc hiểu response không? Nếu có, thêm descriptor với mô tả rõ.
2. Field đã được xác định là tùy chọn trong hợp đồng chưa? Nếu có, dùng optional.
3. Field không cần công bố trong bảng nhưng đã được review chưa? Nếu có, cân nhắc ignored.
4. Trang tài liệu chỉ chủ ý mô tả một phần payload và phần còn lại được giải thích ở nơi khác chưa? Nếu có, relaxed có thể phù hợp.
5. Chưa biết vì sao field xuất hiện? Giữ strict mode, điều tra schema và hành vi trước khi thay đổi descriptor.

Ví dụ response có một field debug mới. Đừng tự động đánh dấu ignored. Trước hết xác định field đó có bị lộ dữ liệu nội bộ không, có thuộc public API không và có cần loại khỏi response hay không. Quyết định documentation không thay thế việc xem xét thiết kế API.

## 9. Đọc và xử lý lỗi descriptor

Khi test thất bại, xử lý theo trình tự:

### Trường hợp A: field trong payload chưa được tài liệu hóa

1. Đọc tên field/path được báo trong lỗi.
2. Kiểm tra response/request body thực tế của test.
3. Xác định field mới là thay đổi chủ đích, field nội bộ hay lỗi serialize ngoài ý muốn.
4. Thêm descriptor, ignored hoặc chuyển sang relaxed theo quyết định hợp đồng.
5. Chạy lại test và xem snippet được tạo.

### Trường hợp B: descriptor path không tồn tại

1. Kiểm tra chính tả và chữ hoa/chữ thường của field path.
2. Kiểm tra JSON thực tế, bao gồm tên đã được Jackson serialize.
3. Kiểm tra field nằm trong object hoặc array nào.
4. Xác định field đã bị xóa/đổi tên hay chỉ vắng mặt trong fixture.
5. Nếu field thực sự có thể vắng mặt, dùng optional; nếu không, sửa DTO/fixture hoặc descriptor theo hợp đồng.

### Trường hợp C: thay đổi nested payload

1. Xác định field nằm ở root, object con hay phần tử array.
2. Đối chiếu path descriptor với cấu trúc JSON.
3. Chọn fieldWithPath chi tiết hoặc subsectionWithPath.
4. Thêm fixture có đủ dữ liệu đại diện cho nested structure.

Không xử lý lỗi bằng cách thêm ignored cho mọi field còn thiếu. Cách đó làm mất tín hiệu quan trọng từ strict mode.

## 10. Ví dụ đầy đủ: API thêm field vào response

Ban đầu:

```java
this.mockMvc.perform(get("/api/orders/{id}", 7001))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7001))
    .andDo(document("orders-get",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng."),
            fieldWithPath("total").description("Tổng tiền đơn hàng.")
        )));
```

Sau thay đổi API, response có thêm currency:

```json
{
  "id": 7001,
  "total": 250000,
  "currency": "VND"
}
```

Test cũ chưa có assertion và descriptor cho currency. Strict responseFields phát hiện field mới chưa được xử lý. Sửa test:

```java
this.mockMvc.perform(get("/api/orders/{id}", 7001))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7001))
    .andExpect(jsonPath("$.currency").value("VND"))
    .andDo(document("orders-get",
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng."),
            fieldWithPath("total").description("Tổng tiền đơn hàng."),
            fieldWithPath("currency").description("Mã tiền tệ của tổng tiền.")
        )));
```

Thay đổi được kiểm chứng ở hai lớp:

- Assertion xác nhận giá trị currency đúng theo fixture/hợp đồng.
- Descriptor đảm bảo currency được giải thích trong tài liệu.

Nếu currency chỉ là thông tin tùy chọn, test cần thêm một trường hợp response không có currency và descriptor optional. Không thể kết luận tính tùy chọn chỉ từ một response mẫu có field đó.

## 11. Phân biệt lỗi REST Docs với lỗi assertion endpoint

Một documentation test có thể thất bại vì nhiều lý do:

| Loại lỗi | Ví dụ | Nơi xử lý |
| --- | --- | --- |
| Assertion HTTP | Status không phải 200 như mong đợi | Endpoint, test data hoặc hợp đồng |
| Assertion body/header | JSON value sai hoặc Content-Type thiếu | Hành vi endpoint |
| Missing field descriptor | Payload có field mới chưa được mô tả | Descriptor hoặc schema |
| Descriptor path invalid | Mô tả field không tồn tại | Path, fixture hoặc optional |
| Snippet generation | Không ghi được file, cấu hình snippet sai | REST Docs/test setup |
| Asciidoctor include | Include trỏ tới file không tồn tại | Operation ID, snippet name hoặc build path |

Hãy đọc loại lỗi trước khi sửa. Nếu assertion status thất bại, thêm descriptor không giải quyết được vấn đề. Nếu strict snippet báo field chưa mô tả, tăng JSONPath assertion nhưng không cập nhật descriptor cũng chưa giải quyết lỗi đó.

## 12. Quy trình review thay đổi schema

Khi documentation test báo field descriptor bị thiếu:

1. Xem diff của DTO/controller/serializer và JSON thực tế.
2. Xác định field có thuộc public contract hay không.
3. Kiểm tra tên, kiểu, nullable/optional và ý nghĩa của field.
4. Nếu field công khai, thêm descriptor và assertion giá trị/kiểu quan trọng.
5. Nếu field không nên công khai, sửa response hoặc serializer thay vì chỉ ignored.
6. Nếu field đã được review nhưng không thuộc phạm vi bảng này, cân nhắc ignored hoặc relaxed và ghi rõ lý do trong code review.
7. Chạy documentation tests và biên soạn tài liệu để xác minh cả snippet lẫn include.

Strict mode biến thay đổi payload thành một điểm review có chủ đích. Nó không tự quyết định schema mới là tốt hay xấu; nhóm phát triển vẫn phải đánh giá ý nghĩa của thay đổi.

## 13. Bài thực hành

1. Tạo endpoint GET /api/products/{id} trả id, name và price.
2. Viết responseFields strict cho cả ba field và chạy test thành công.
3. Thêm status vào JSON response nhưng chưa sửa descriptor; quan sát lỗi field chưa được tài liệu hóa.
4. Thêm descriptor status và assertion JSONPath cho giá trị ACTIVE.
5. Thêm manufacturer object; thử mô tả bằng fieldWithPath cho từng field con.
6. Đổi sang subsectionWithPath và quan sát khác biệt của snippet.
7. Thêm field description có thể vắng mặt; dùng optional và kiểm tra cả payload có/không có field.
8. Thêm field internalVersion; thử ignored sau khi xác định lý do không công bố.
9. Thử relaxedResponseFields trong một test khác và giải thích những thay đổi schema nào không còn được strict mode phát hiện.

**Câu hỏi tự đánh giá**

1. Vì sao responseFields strict làm test thất bại khi payload có field mới?
2. Strict mode kiểm tra cả payload sang descriptor và descriptor sang payload như thế nào?
3. optional khác ignored ra sao?
4. subsectionWithPath giúp xử lý nested object như thế nào?
5. Vì sao relaxedResponseFields có thể làm một field mới không bị phát hiện?
6. Khi nào nên thêm descriptor thay vì ignored?
7. Một descriptor path không tồn tại có thể chỉ ra những vấn đề nào?
8. Vì sao JSONPath assertion và field descriptor là hai lớp kiểm tra khác nhau?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): requestFields, responseFields, relaxed variants, field descriptors và nested payload.
- [PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): API tạo payload snippets.
- [FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): description, optional, ignored và attributes.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): kiểm chứng HTTP exchange và tạo snippet.

**Kết luận thực hành:** Khi strict requestFields hoặc responseFields báo thiếu descriptor, hãy xem đó là yêu cầu review một thay đổi payload. Thêm descriptor nếu field thuộc hợp đồng, optional nếu field có thể vắng mặt, ignored nếu đã quyết định không hiển thị, hoặc relaxed khi tài liệu chủ ý chỉ mô tả một phần. Giữ strict mode ở những operation cần tài liệu đầy đủ để test tiếp tục phát hiện schema drift.
