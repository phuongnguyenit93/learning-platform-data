# request-fields và response-fields

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, một API thường trao đổi JSON ở cả hai chiều: client gửi request body và server trả response body. Tài liệu cần mô tả field, kiểu dữ liệu, ý nghĩa, tính bắt buộc và cấu trúc lồng nhau. Spring REST Docs cung cấp hai nhóm snippet mặc định để ghi lại phần hợp đồng này: **request-fields** và **response-fields**.

Hai snippet được sinh từ các field descriptor mà bài test khai báo. Khi dùng cấu hình mặc định, REST Docs kiểm tra descriptor với payload thực tế: field có trong payload phải được xử lý trong tài liệu và descriptor phải khớp với dữ liệu đã quan sát. Nhờ vậy, thay đổi payload có thể khiến bài test tài liệu thất bại thay vì âm thầm làm tài liệu lỗi thời.

Sau bài này, bạn có thể:

- Phân biệt request-fields với response-fields.
- Dùng requestFields và responseFields để sinh snippet.
- Khai báo fieldWithPath, subsectionWithPath và thuộc tính mô tả field.
- Mô tả field tùy chọn và field có mặt nhưng không công bố.
- Hiểu hành vi kiểm tra mặc định và khi nào dùng relaxedRequestFields/relaxedResponseFields.
- Mô tả object lồng nhau, array và cấu trúc payload.
- Chẩn đoán lỗi descriptor không khớp request/response thực tế.

## 1. Hai snippet mô tả hai chiều payload

### request-fields

request-fields mô tả các field trong request body mà client gửi tới endpoint. Ví dụ request tạo sản phẩm:

```json
{
  "name": "Mechanical Keyboard",
  "price": 129.90,
  "category": "ACCESSORIES"
}
```

Test khai báo field descriptor để mô tả đường dẫn, ý nghĩa và các thông tin bổ sung. REST Docs tạo snippet request-fields từ descriptor đó.

### response-fields

response-fields mô tả các field trong response body server trả về. Ví dụ:

```json
{
  "id": 501,
  "name": "Mechanical Keyboard",
  "price": 129.90,
  "category": "ACCESSORIES",
  "createdAt": "2026-11-17T08:30:00Z"
}
```

Response có thể chứa field server sinh ra như id hoặc createdAt, không xuất hiện trong request. Vì vậy, descriptor response thường khác descriptor request ngay cả khi hai payload có một số field trùng tên.

| Snippet | Mô tả | Thời điểm thường dùng |
| --- | --- | --- |
| request-fields | Hợp đồng dữ liệu client gửi | POST, PUT, PATCH hoặc endpoint nhận JSON body |
| response-fields | Hợp đồng dữ liệu server trả | GET, POST, PUT hoặc endpoint có response body |

Không dùng request-fields chỉ vì test gửi request. Nếu endpoint không có request body, có thể tài liệu hóa path parameter, query parameter hoặc header bằng snippet tương ứng. Nếu response là 204 No Content thì không tạo response-fields cho body không tồn tại.

## 2. Field descriptor là gì?

Field descriptor là khai báo cho biết REST Docs cần ghi nhận field nào trong payload và mô tả field đó ra sao.

| Thành phần | Vai trò |
| --- | --- |
| Field path | Đường dẫn tới field trong payload, ví dụ name hoặc customer.email |
| Description | Ý nghĩa field đối với người dùng API |
| Type | Kiểu dữ liệu được ghi vào snippet hoặc suy ra từ payload |
| Optional | Khai báo field có thể vắng mặt |
| Ignored | Field có trong payload nhưng không được mô tả trong bảng snippet |
| Attributes | Metadata bổ sung cho template tùy chỉnh |

API thường dùng:

- fieldWithPath("...") tạo descriptor cho một field hoặc path.
- subsectionWithPath("...") mô tả toàn bộ một object/subsection như một đơn vị.
- description("...") gán diễn giải cho descriptor.
- optional() đánh dấu field có thể không xuất hiện.
- ignored() xử lý field có trong payload nhưng không hiển thị như field thông thường.

## 3. Ví dụ request-fields với MockMvc

Giả sử DTO:

```java
public record CreateProductRequest(
        String name,
        BigDecimal price,
        String category
) {
}
```

Test MockMvc:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "name": "Mechanical Keyboard",
                  "price": 129.90,
                  "category": "ACCESSORIES"
                }
                """))
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name")
                .description("Tên sản phẩm."),
            fieldWithPath("price")
                .description("Giá bán của sản phẩm."),
            fieldWithPath("category")
                .description("Mã nhóm sản phẩm.")
        )));
```

REST Docs tạo snippet cho operation products-create. Với cấu hình mặc định, snippet request-fields có bảng field path, type và description. Type hiển thị được suy ra từ payload hoặc có thể chỉ định tường minh nếu cần.

Một phần nội dung AsciiDoc sinh ra có dạng:

```asciidoc
|===
|Path|Type|Description

|name
|String
|Tên sản phẩm.

|price
|Number
|Giá bán của sản phẩm.

|category
|String
|Mã nhóm sản phẩm.
|===
```

Đây là hình dạng minh họa; type hiển thị phụ thuộc payload, descriptor và snippet template của phiên bản đang dùng.

## 4. Ví dụ response-fields

Test:

```java
this.mockMvc.perform(get("/api/products/{id}", 501)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        responseFields(
            fieldWithPath("id")
                .description("Định danh sản phẩm do server tạo."),
            fieldWithPath("name")
                .description("Tên sản phẩm."),
            fieldWithPath("price")
                .description("Giá bán hiện tại."),
            fieldWithPath("category")
                .description("Mã nhóm sản phẩm."),
            fieldWithPath("createdAt")
                .description("Thời điểm tạo sản phẩm theo ISO-8601.")
        )));
```

Snippet response-fields độc lập với request-fields. Dù name, price và category xuất hiện ở cả hai payload, mô tả có thể khác nhau theo ngữ cảnh đọc/ghi. Không nên tái sử dụng một danh sách descriptor chỉ vì field path giống nhau nếu ý nghĩa hoặc tính bắt buộc khác.

## 5. Field tùy chọn với optional()

Một field có thể xuất hiện trong một số request nhưng không bắt buộc. Ví dụ description:

```java
requestFields(
    fieldWithPath("name")
        .description("Tên sản phẩm."),
    fieldWithPath("price")
        .description("Giá bán."),
    fieldWithPath("description")
        .optional()
        .description("Mô tả sản phẩm; có thể không gửi.")
)
```

optional() có nghĩa field có thể vắng mặt trong payload mà test vẫn hợp lệ. Nó không có nghĩa field phải mang giá trị null. Hai payload sau khác nhau:

```json
{
  "name": "Keyboard"
}
```

```json
{
  "name": "Keyboard",
  "description": null
}
```

Field có thể vắng mặt và field được gửi với giá trị null là hai trạng thái khác nhau ở cấp JSON. Tài liệu cần phản ánh cách API thực sự xử lý cả hai nếu chúng có ý nghĩa khác nhau.

Với response, optional() hữu ích nếu một field chỉ có ở một số trạng thái hoặc loại tài nguyên. Test hiện tại vẫn cần xác minh response quan sát được và descriptor tương ứng.

## 6. Field ignored() — có trong payload nhưng không liệt kê

Đôi khi payload có field không muốn công bố trong bảng tài liệu:

- Field kỹ thuật nội bộ.
- Metadata không thuộc trọng tâm operation.
- Giá trị được mô tả ở phần khác.

Có thể dùng ignored():

```java
responseFields(
    fieldWithPath("id")
        .description("Mã sản phẩm."),
    fieldWithPath("name")
        .description("Tên sản phẩm."),
    fieldWithPath("internalVersion")
        .ignored()
)
```

ignored() cho REST Docs biết descriptor này được xử lý nhưng không đưa vào bảng mô tả snippet như field thông thường. Khác optional(), ignored() không có nghĩa field có thể vắng mặt; nó vẫn phải phù hợp với payload được kiểm tra. Nếu muốn field vừa có thể vắng mặt vừa không hiển thị, hãy kết hợp trạng thái phù hợp theo API descriptor của phiên bản đang dùng và xác minh bằng test.

Không nên lạm dụng ignored() để che giấu thay đổi schema. Nếu field là một phần hợp đồng mà client cần biết, nên mô tả thay vì bỏ qua.

## 7. Hành vi mặc định: strict payload documentation

requestFields và responseFields áp dụng kiểm tra payload theo hướng đầy đủ:

- Mọi field thực tế trong payload cần được mô tả hoặc xử lý bằng descriptor phù hợp.
- Descriptor trỏ tới field không tồn tại trong payload có thể làm test thất bại.
- Field descriptor chưa bao phủ một phần payload sẽ khiến test nhắc tới field chưa được tài liệu hóa.

Đây là một điểm mạnh của REST Docs: snippet không chỉ là văn bản viết tay mà còn được kiểm chứng với payload test.

Ví dụ payload thực tế:

```json
{
  "id": 501,
  "name": "Keyboard",
  "status": "ACTIVE"
}
```

Nhưng descriptor chỉ khai báo id và name:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm."),
    fieldWithPath("name").description("Tên sản phẩm.")
)
```

Test có thể thất bại vì status chưa được mô tả. Khi API thêm field mới, người viết cần xem xét: thêm mô tả status, đánh dấu ignored nếu có lý do, hoặc chọn chiến lược relaxed nếu mục tiêu tài liệu chỉ bao phủ một phần response.

### 7.1. Khi descriptor trỏ tới field không có

Nếu descriptor khai báo category nhưng response không có category, test có thể báo descriptor path không tìm thấy trong payload. Hãy xem lại:

- Test fixture có đúng dữ liệu không?
- API có thay đổi schema không?
- Tên field có bị Jackson đổi bằng @JsonProperty không?
- Field có nằm trong nested object hoặc array không?
- Descriptor có dành cho đúng operation không?

Không giải quyết bằng cách đánh dấu optional một cách máy móc nếu field phải có theo hợp đồng.

## 8. relaxedRequestFields và relaxedResponseFields

Trong một số tài liệu, chỉ cần mô tả một phần payload. REST Docs cung cấp API relaxed:

```java
relaxedRequestFields(
    fieldWithPath("name")
        .description("Tên sản phẩm.")
)
```

```java
relaxedResponseFields(
    fieldWithPath("id")
        .description("Mã sản phẩm.")
)
```

So sánh:

| API | Mục tiêu | Hành vi |
| --- | --- | --- |
| requestFields | Mô tả request body đầy đủ | Field chưa được xử lý làm test thất bại |
| responseFields | Mô tả response body đầy đủ | Field chưa được xử lý làm test thất bại |
| relaxedRequestFields | Chỉ mô tả phần request quan tâm | Cho phép field khác chưa liệt kê |
| relaxedResponseFields | Chỉ mô tả phần response quan tâm | Cho phép field khác chưa liệt kê |

Ví dụ response có id, name, status, createdAt, updatedAt nhưng trang tài liệu chỉ giải thích id và name. relaxedResponseFields có thể phù hợp nếu các field còn lại đã được giải thích ở tài liệu chung hoặc không thuộc trọng tâm operation.

### 8.1. Không dùng relaxed theo mặc định

Nếu luôn dùng relaxedResponseFields, một field mới có thể xuất hiện mà không khiến test thất bại. Điều này làm giảm khả năng phát hiện thay đổi hợp đồng API.

Ưu tiên strict requestFields/responseFields cho payload mà tài liệu cần mô tả đầy đủ. Chỉ dùng relaxed khi nhóm đã quyết định rõ snippet chỉ là mô tả một phần và có cách tài liệu hóa các field còn lại.

## 9. Mô tả object lồng nhau

Payload JSON có thể chứa object con:

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

Có hai hướng mô tả.

### 9.1. Mô tả từng field con

```java
responseFields(
    fieldWithPath("id")
        .description("Mã sản phẩm."),
    fieldWithPath("name")
        .description("Tên sản phẩm."),
    fieldWithPath("manufacturer.id")
        .description("Mã nhà sản xuất."),
    fieldWithPath("manufacturer.name")
        .description("Tên nhà sản xuất.")
)
```

Cách này phù hợp khi người đọc cần hiểu từng thuộc tính bên trong object.

### 9.2. Mô tả cả subsection

```java
responseFields(
    fieldWithPath("id")
        .description("Mã sản phẩm."),
    fieldWithPath("name")
        .description("Tên sản phẩm."),
    subsectionWithPath("manufacturer")
        .description("Thông tin nhà sản xuất.")
)
```

subsectionWithPath mô tả toàn bộ subsection như một đơn vị, thay vì liệt kê từng field con trong bảng hiện tại. Nếu muốn mô tả chi tiết manufacturer, có thể tạo phần tài liệu riêng hoặc snippet khác cho cấu trúc đó.

Không khai báo đồng thời subsection và các field con như hai nhánh độc lập trong cùng descriptor set nếu chúng chồng lấn. Chọn cách mô tả phù hợp cho từng bảng snippet.

## 10. Mô tả array và object trong array

Ví dụ response có danh sách sản phẩm:

```json
{
  "items": [
    { "id": 501, "name": "Keyboard" },
    { "id": 502, "name": "Mouse" }
  ]
}
```

Có thể mô tả field trong phần tử array bằng path:

```java
responseFields(
    fieldWithPath("items")
        .description("Danh sách sản phẩm."),
    fieldWithPath("items[].id")
        .description("Mã sản phẩm."),
    fieldWithPath("items[].name")
        .description("Tên sản phẩm.")
)
```

Ký hiệu [] thể hiện các phần tử trong mảng đối với JSON payload field path của Spring REST Docs. Test phải chứa array có phần tử để descriptor được kiểm tra theo payload thực tế.

Nếu array rỗng trong response test, descriptor cho items[].id có thể không có phần tử thực tế để xác minh như dự kiến. Hãy thiết kế fixture có dữ liệu đại diện cho cấu trúc tài liệu cần mô tả, đồng thời có test riêng cho trường hợp collection rỗng khi cần.

## 11. Ghi đè type và metadata

REST Docs thường suy luận type từ payload. Nếu cần ghi type rõ ràng:

```java
fieldWithPath("price")
    .type(JsonFieldType.NUMBER)
    .description("Giá bán theo đơn vị tiền tệ của API.")
```

Các kiểu JSON thường gặp gồm STRING, NUMBER, BOOLEAN, OBJECT, ARRAY và NULL. Chỉ định type tường minh có thể giúp tài liệu nhất quán, nhưng phải khớp payload thực tế.

Có thể thêm attributes:

```java
fieldWithPath("price")
    .type(JsonFieldType.NUMBER)
    .description("Giá bán.")
    .attributes(key("constraints").value("Lớn hơn 0"))
```

Attributes chỉ hữu ích nếu template snippet có đọc và hiển thị key đó. Template mặc định không tự động hiển thị mọi custom attribute. Nếu cần cột hoặc dòng riêng, cần tùy chỉnh snippet template.

## 12. Mẫu tổ chức request và response descriptor

Một test thường đặt request và response payload descriptor gần nhau nhưng tách riêng:

```java
this.mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(
            fieldWithPath("name").description("Tên sản phẩm."),
            fieldWithPath("price").description("Giá bán."),
            fieldWithPath("category").description("Nhóm sản phẩm.")
        ),
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm do server tạo."),
            fieldWithPath("name").description("Tên sản phẩm đã lưu."),
            fieldWithPath("price").description("Giá bán đã lưu."),
            fieldWithPath("category").description("Nhóm sản phẩm."),
            fieldWithPath("createdAt").description("Thời điểm tạo.")
        )));
```

Trong ví dụ này, request có ba field còn response có thêm id và createdAt. Hai danh sách descriptor phản ánh hai schema khác nhau.

Khi test có response không có body, bỏ responseFields. Khi request không có body, bỏ requestFields. Không tạo descriptor rỗng chỉ để mọi test có cùng cấu trúc.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Test báo field không được tài liệu hóa | Payload có field không được descriptor xử lý | Bổ sung descriptor hoặc dùng ignored/relaxed với lý do rõ |
| Test báo descriptor không tìm thấy field | Path sai hoặc payload không có field | Đối chiếu JSON thực tế, tên Jackson và path |
| Field tùy chọn làm test thất bại khi vắng mặt | Chưa đánh dấu optional | Dùng optional nếu field thật sự có thể thiếu |
| Field null và field vắng mặt bị nhầm | Nhầm optional với cho phép giá trị null | Xác định và test riêng hai trường hợp |
| Snippet không hiển thị custom attribute | Template không render attribute | Tùy chỉnh snippet template hoặc ghép vào description |
| Object lồng nhau không có chi tiết con | Dùng subsectionWithPath | Dùng fieldWithPath cho từng field con nếu cần bảng chi tiết |
| Array path không khớp | Sai cú pháp path hoặc fixture array rỗng | Kiểm tra cú pháp items[].field và tạo fixture đại diện |
| Response thay đổi nhưng tài liệu vẫn xanh | Đang dùng relaxedResponseFields | Cân nhắc chuyển về strict responseFields |
| Có request-fields cho endpoint không body | Chọn sai snippet cho loại request | Dùng snippet parameter/header hoặc bỏ request-fields |

## 14. Bài thực hành

1. Tạo endpoint POST /api/products nhận name, price và category.
2. Viết MockMvc test dùng requestFields để mô tả đủ request body.
3. Cho endpoint trả id, name, price, category và createdAt; dùng responseFields để mô tả response body.
4. Thêm description là field optional và xác minh test vẫn chạy khi field vắng mặt.
5. Thêm field internalVersion và đánh dấu ignored nếu thực sự không muốn hiển thị trong snippet.
6. Thêm field mới vào response JSON nhưng chưa thêm descriptor; quan sát strict responseFields làm test thất bại.
7. Thử relaxedResponseFields và giải thích trade-off về khả năng phát hiện schema drift.
8. Thêm manufacturer object và items array; mô tả một trường hợp bằng subsectionWithPath, trường hợp khác bằng path chi tiết.

**Câu hỏi tự đánh giá**

1. request-fields và response-fields mô tả hai phần nào của HTTP exchange?
2. Vì sao nên tách request descriptor và response descriptor?
3. optional() khác ignored() như thế nào?
4. Strict requestFields/responseFields giúp phát hiện loại thay đổi nào?
5. Khi nào relaxedResponseFields là lựa chọn phù hợp?
6. fieldWithPath và subsectionWithPath khác nhau ở mục đích nào?
7. Cú pháp items[].id biểu diễn điều gì?
8. Custom attribute có tự xuất hiện trong snippet mặc định không?

## Tài liệu tham khảo chính thức

- [Spring REST Docs — Documenting Request/Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): requestFields, responseFields và các biến thể relaxed.
- [Spring REST Docs — Payload Documentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html): API tạo payload field snippet.
- [FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): optional, ignored, type, description và attributes.
- [JsonFieldType API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/JsonFieldType.html): các kiểu JSON dùng trong descriptor.

**Kết luận thực hành:** Dùng requestFields và responseFields để mô tả hợp đồng payload theo từng chiều. Bắt đầu với descriptor đầy đủ để test kiểm tra payload chặt chẽ; dùng optional cho field có thể vắng mặt, ignored cho field không cần hiển thị và relaxed chỉ khi tài liệu chủ ý mô tả một phần. Với nested object và array, chọn field path chi tiết hoặc subsection phù hợp, sau đó chạy test để xác minh snippet phản ánh đúng JSON thực tế.
