# Kiểm thử template với payload thực tế

## 1. Mục tiêu của việc kiểm thử template

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test thực hiện request, xác nhận response và khai báo descriptor; REST Docs dùng dữ liệu operation để sinh snippet về request, response, fields, parameters, headers và hypermedia links. Những snippet được biên soạn thành Asciidoctor/Markdown rồi đưa vào build, CI.

Khi đã tùy chỉnh Mustache template, chỉ nhìn file template chưa đủ để biết kết quả cuối có đúng hay không. Template có thể hợp lệ nhưng vẫn hiển thị sai tên field, không nhận attributes, bỏ sót field lồng nhau, xử lý sai optional/null, làm vỡ bảng bởi ký tự đặc biệt hoặc sinh cú pháp AsciiDoc/Markdown không hợp lệ.

Vì vậy, cần kiểm tra bằng payload đại diện cho API, đi qua serializer và HTTP layer mà tài liệu mô tả. Bài này trình bày cách xây dựng documentation tests, kiểm tra descriptor coverage và xác nhận snippet thực sự được render.

## 2. Ba lớp cần kiểm tra

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Hành vi HTTP | API có trả đúng status, media type và payload không? | status assertion, JSONPath |
| Descriptor | Test đã mô tả đúng field/parameter/link công bố chưa? | requestFields(...), responseFields(...), links(...) |
| Template output | Template render đúng metadata và cấu trúc bảng không? | Kiểm tra snippet có cột Constraints và giá trị Example |

Ba lớp bổ trợ nhau. Assertion HTTP không chứng minh template hiển thị đúng; kiểm tra file snippet cũng không chứng minh endpoint hoạt động đúng. Documentation test cần kết hợp assertion và document(...), còn bước xác minh output đọc file sinh ra sau khi test hoàn tất.

~~~text
Payload fixture
      |
      v
Jackson serialization + HTTP request
      |
      v
Controller / application behavior
      |
      v
HTTP response + assertions
      |
      v
REST Docs descriptors + attributes
      |
      v
Custom Mustache template
      |
      v
Generated snippet
      |
      v
Verify snippet content + build document
~~~

## 3. Chuẩn bị payload đại diện

Không nên chỉ dùng payload tối giản có một field string. Hãy chọn dữ liệu thể hiện các cấu trúc API thực sự hỗ trợ: field cơ bản, object lồng nhau, collection, enum, số, timestamp và field có thể null hoặc vắng mặt.

Ví dụ request tạo đơn hàng:

~~~json
{
  "customerId": "c-1024",
  "note": "Giao giờ hành chính",
  "items": [
    {"productId": "p-42", "quantity": 2, "unitPrice": 125000},
    {"productId": "p-88", "quantity": 1, "unitPrice": 79000}
  ],
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  }
}
~~~

Response có thể thêm các field do server tạo:

~~~json
{
  "id": "o-9001",
  "status": "PENDING",
  "total": 329000,
  "createdAt": "2026-11-17T08:30:00Z",
  "note": "Giao giờ hành chính",
  "items": [
    {"productId": "p-42", "quantity": 2, "unitPrice": 125000},
    {"productId": "p-88", "quantity": 1, "unitPrice": 79000}
  ]
}
~~~

Payload giúp kiểm tra template với nhiều kiểu field và cấu trúc lồng nhau. Đây là fixture giả lập; không đưa thông tin khách hàng, token, địa chỉ hoặc giá trị định danh thật vào snippet công khai.

## 4. Dùng DTO và ObjectMapper để gửi payload qua HTTP test

Với MockMvc, nên tạo request từ DTO và serialize bằng ObjectMapper. Cách này kiểm tra payload đã qua cấu hình Jackson của ứng dụng, thay vì chỉ kiểm thử một JSON string tự viết không liên quan tới model.

Ví dụ DTO rút gọn:

~~~java
record CreateOrderRequest(
        String customerId,
        String note,
        List<OrderItemRequest> items,
        ShippingAddress shippingAddress) {}

record OrderItemRequest(String productId, int quantity, long unitPrice) {}

record ShippingAddress(String city, String district) {}
~~~

Documentation test dùng ObjectMapper:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void createOrderDocumentsRealRequestAndResponse() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest(
                "c-1024",
                "Giao giờ hành chính",
                List.of(
                        new OrderItemRequest("p-42", 2, 125000),
                        new OrderItemRequest("p-88", 1, 79000)),
                new ShippingAddress("Ho Chi Minh City", "District 1"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(request)))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.items.length()").value(2))
                .andDo(document("orders-create",
                        requestFields(
                                fieldWithPath("customerId").description("Mã khách hàng"),
                                fieldWithPath("note").description("Ghi chú giao hàng"),
                                fieldWithPath("items").description("Danh sách sản phẩm"),
                                fieldWithPath("items[].productId").description("Mã sản phẩm"),
                                fieldWithPath("items[].quantity").description("Số lượng"),
                                fieldWithPath("items[].unitPrice").description("Đơn giá"),
                                fieldWithPath("shippingAddress").description("Địa chỉ giao hàng"),
                                fieldWithPath("shippingAddress.city").description("Thành phố"),
                                fieldWithPath("shippingAddress.district").description("Quận/huyện")),
                        responseFields(
                                fieldWithPath("id").description("Mã đơn hàng"),
                                fieldWithPath("status").description("Trạng thái đơn hàng"),
                                fieldWithPath("total").description("Tổng tiền"),
                                fieldWithPath("createdAt").description("Thời điểm tạo"),
                                fieldWithPath("note").description("Ghi chú giao hàng"),
                                fieldWithPath("items").description("Danh sách sản phẩm"),
                                fieldWithPath("items[].productId").description("Mã sản phẩm"),
                                fieldWithPath("items[].quantity").description("Số lượng"),
                                fieldWithPath("items[].unitPrice").description("Đơn giá"))));
    }
}
~~~

Đây là mẫu tích hợp cần điều chỉnh theo DTO, endpoint, response và import của ứng dụng. Nếu dùng @WebMvcTest thay cho @SpringBootTest, cần import controller, serializer, service mock và cấu hình REST Docs phù hợp.

## 5. Kiểm tra descriptor coverage trên payload

Khi dùng requestFields(...) hoặc responseFields(...) ở chế độ strict, Spring REST Docs kiểm tra mô tả đối với cấu trúc payload. Với payload lồng nhau, cần mô tả subsection/field theo đúng cấu trúc. Descriptor quá rộng có thể che mất field mà tài liệu cần trình bày; descriptor thiếu có thể làm test thất bại.

Đọc payload trước khi viết descriptor:

- Tên field và kiểu dữ liệu thực tế sau serialize.
- Field lồng nhau, đường dẫn dạng parent.child.
- Mảng và phần tử dạng items[] hoặc items[].productId.
- Field optional, nullable hoặc có thể bị lược khỏi JSON.
- Field do server thêm vào response nhưng không có trong request.
- Field nhạy cảm phải được lọc hoặc không xuất hiện trong fixture.

Ví dụ mô tả collection và từng field:

~~~java
requestFields(
        fieldWithPath("items").description("Danh sách sản phẩm"),
        fieldWithPath("items[].productId").description("Mã sản phẩm"),
        fieldWithPath("items[].quantity").description("Số lượng"),
        fieldWithPath("items[].unitPrice").description("Đơn giá"))
~~~

Khi payload có field tùy chọn, dùng optional() đúng theo hợp đồng. Chỉ dùng ignored() cho field chủ ý không công bố; không dùng để che một field quan trọng mà descriptor đang thiếu.

## 6. Kiểm thử metadata của template

Giả sử request-fields.snippet đã được tùy chỉnh để có các cột Path, Type, Description, Constraints và Example. Test truyền metadata:

~~~java
requestFields(
        attributes(
                key("title").value("Các trường khi tạo đơn hàng"),
                key("api-version").value("v1")),
        fieldWithPath("customerId")
                .description("Mã khách hàng")
                .attributes(
                        key("constraints").value("Không được để trống"),
                        key("example").value("c-1024")),
        fieldWithPath("items[].quantity")
                .description("Số lượng")
                .attributes(
                        key("constraints").value("Từ 1 trở lên"),
                        key("example").value("2")))
~~~

Để kiểm thử template, đừng chỉ kiểm tra Java đã gọi attributes(...). Hãy kiểm tra output snippet sau khi documentation test hoàn tất:

~~~text
build/generated-snippets/
└── orders-create/
    └── request-fields.adoc
~~~

Nội dung cần thể hiện tiêu đề “Các trường khi tạo đơn hàng”, API version v1, constraint cho customerId và items[].quantity, example gắn đúng field; field không có metadata không tạo nội dung sai hoặc làm hỏng bảng.

Đây là kiểm tra trực tiếp template đã render, không chỉ xác nhận descriptor được cấu hình.

## 7. Xác minh file snippet sau khi test chạy

Snippet được ghi khi operation thực thi document(...). Vì vậy, bước đọc file cần chạy sau documentation test. Không giả định một test khác trong cùng test suite sẽ chạy sau test sinh snippet; thứ tự thực thi test thường không phải hợp đồng ổn định.

Có thể tạo một bước kiểm tra riêng trong build sau task test. Ví dụ đoạn Java độc lập để kiểm tra file đã sinh:

~~~java
Path snippet = Path.of(
        "build/generated-snippets",
        "orders-create",
        "request-fields.adoc");

String rendered = Files.readString(snippet, StandardCharsets.UTF_8);

assertThat(rendered)
        .contains("Các trường khi tạo đơn hàng")
        .contains("Không được để trống")
        .contains("Từ 1 trở lên")
        .contains("c-1024");
~~~

Đưa đoạn kiểm tra vào task/verifier chạy sau documentation tests và điều chỉnh output directory/extension theo cấu hình dự án. Không đặt verifier vào một test chạy đồng thời với test tạo snippet vì nó có thể đọc file trước khi file được ghi.

### Kiểm tra định dạng đầu ra

- Các header cột xuất hiện đúng một lần.
- Mỗi row có đủ số cột theo template.
- Section metadata tùy chọn chỉ xuất hiện khi có giá trị.
- Ký tự đặc biệt trong payload không phá cú pháp AsciiDoc/Markdown.
- Không có placeholder Mustache chưa render như {{constraints}}.
- Không còn nội dung từ payload trước nếu build tái sử dụng output directory.

Nên dùng output directory sạch trong lần sinh snippet của CI, hoặc bảo đảm task clean xóa output cũ trước documentation tests.

## 8. Dùng nhiều payload để thử độ bền template

Một payload thành công chưa đủ chứng minh template xử lý mọi dạng dữ liệu. Chọn các trường hợp kiểm tra section tùy chọn, bảng và escaping:

| Trường hợp | Dữ liệu test | Điều cần quan sát |
| --- | --- | --- |
| Giá trị bình thường | Chuỗi, số, enum hợp lệ | Bảng render đầy đủ |
| Chuỗi có ký tự đặc biệt | A&B <C> | Nội dung không phá cấu trúc |
| Chuỗi rỗng | note: "" | Ô trống có cách trình bày nhất quán |
| Giá trị null | note: null nếu API cho phép | Field hiện null hoặc bị serializer bỏ qua theo cấu hình |
| Field optional vắng mặt | Không gửi key | Descriptor optional xử lý đúng |
| Collection rỗng | items: [] | Mô tả collection không giả định có item |
| Collection nhiều phần tử | Hai hoặc nhiều item | Field path dạng mảng được mô tả đúng |
| Object lồng nhau | shippingAddress.city | Path và subsection chính xác |
| Giá trị dài | Note hoặc mô tả dài | Bảng không vỡ khi biên soạn |

Không bắt buộc mọi trường hợp phải tạo snippet công khai riêng. Có thể dùng một số documentation operation cho ví dụ chính và test bổ sung chỉ xác nhận hành vi/serializer. Nếu tạo snippet cho từng trường hợp, đặt identifier phân biệt để không ghi đè output.

## 9. Kiểm tra escaping và dữ liệu nhạy cảm

Payload thực tế có thể chứa ký tự đặc biệt của AsciiDoc, Markdown hoặc bảng. Ví dụ dấu | có thể bị hiểu là dấu phân cột, dòng mới có thể làm layout thay đổi. Template phải xử lý escaping theo format đầu ra; không giả định mọi nội dung đều an toàn khi chèn trực tiếp vào bảng.

Tạo fixture có ký tự đặc biệt:

~~~json
{
  "displayName": "An & Bình",
  "description": "Gói A | Gói B",
  "note": "Dòng một\nDòng hai"
}
~~~

Sau khi sinh snippet, kiểm tra phần dữ liệu không làm vỡ bảng hoặc tạo heading ngoài ý muốn. Nếu template cần helper escape chuyên biệt, xác nhận khả năng của engine/format đang dùng và triển khai quy tắc phù hợp; đừng sửa fixture để che lỗi render.

Chỉ sử dụng dữ liệu giả trong tài liệu. Không dùng token, cookie, email khách hàng thật, số điện thoại, địa chỉ giao nhận thật hoặc dữ liệu bí mật từ staging/production.

## 10. Kiểm thử nhiều template format

Nếu dự án hỗ trợ cả Asciidoctor và Markdown, cần xác minh output của từng format:

~~~text
templates/
├── asciidoctor/
│   └── request-fields.snippet
└── markdown/
    └── request-fields.snippet
~~~

Hai template có thể hiển thị cùng metadata nhưng dùng cú pháp bảng khác nhau. Chạy documentation tests với format tương ứng, sau đó xác minh:

| Kiểm tra | Asciidoctor | Markdown |
| --- | --- | --- |
| Output extension | .adoc | .md |
| Cú pháp bảng | AsciiDoc table | Markdown table |
| Title/note | Render đúng | Render đúng |
| Constraints/examples | Đúng field | Đúng field |
| Ký tự đặc biệt | Escape hợp lệ | Escape hợp lệ |
| Include/build | Task Asciidoctor | Quy trình Markdown |

Không chỉ kiểm tra file .snippet đã đặt đúng vị trí. Phải chạy test với format được chọn và đọc file snippet đầu ra.

## 11. Tổ chức CI để template được kiểm tra với payload hiện tại

~~~text
Clean generated snippets
          |
          v
Run documentation tests
          |
          v
Assert HTTP behavior and descriptor coverage
          |
          v
Verify generated snippet content
          |
          v
Build Asciidoctor / Markdown
          |
          v
Archive or publish documentation
~~~

Các nguyên tắc cho CI:

1. Làm sạch output cũ hoặc dùng output directory riêng cho build hiện tại.
2. Chạy documentation tests với fixture đại diện cho payload API.
3. Xác minh snippet output sau khi test đã ghi xong.
4. Biên soạn tài liệu sau bước sinh snippet.
5. Lưu artifact để reviewer so sánh khi template thay đổi.
6. Khi nâng Spring REST Docs, kiểm tra template model và diff snippet.

Nếu CI chỉ chạy Asciidoctor mà không chạy documentation tests, template mới có thể chưa từng được render trên payload hiện tại. Task biên soạn cần phụ thuộc task test sinh snippet.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Template render nhưng thiếu cột metadata | Test không truyền attribute hoặc template dùng sai key | Kiểm tra descriptor attributes và placeholder Mustache |
| Field lồng nhau không xuất hiện | Descriptor path không khớp JSON sau serialize | Xem payload thực tế và điều chỉnh field path |
| Test pass nhưng snippet sai format | Chỉ assertion HTTP, chưa xác minh output template | Thêm bước đọc snippet sau test |
| Snippet có dữ liệu cũ | Output directory giữ file từ build trước | Clean output hoặc dùng thư mục riêng |
| Template lỗi với mảng rỗng | Fixture chỉ thử collection có phần tử | Thêm trường hợp collection rỗng |
| Bảng vỡ vì dấu gạch đứng hoặc dòng mới | Nội dung chưa được escape đúng format | Điều chỉnh template và kiểm tra output |
| Optional field bị báo thiếu | Descriptor không đánh dấu optional theo hợp đồng | Dùng optional() khi việc vắng mặt hợp lệ |
| Snippet verifier không tìm thấy file | Verifier chạy trước documentation test hoặc sai output path | Đặt dependency đúng thứ tự và kiểm tra đường dẫn |
| Markdown đúng nhưng AsciiDoc lỗi | Chỉ kiểm thử một template format | Chạy và xác minh cả hai format nếu dự án hỗ trợ |
| Test fixture làm lộ dữ liệu thật | Payload sao chép từ môi trường | Thay bằng dữ liệu giả, ổn định |

## 13. Bài thực hành

1. Tạo payload request bằng DTO và ObjectMapper, bao gồm collection và object lồng nhau.
2. Viết MockMvc documentation test với status/content-type assertions và request/response field descriptors.
3. Thêm constraints, example và snippet-level title vào request-fields template.
4. Chạy test rồi xác minh file request-fields snippet chứa metadata đúng field.
5. Thêm fixture với collection rỗng, field optional và chuỗi có ký tự đặc biệt; quan sát output.
6. Tạo verifier chạy sau documentation tests để kiểm tra snippet không còn placeholder Mustache và có đủ cột.
7. Chạy cùng bộ test bằng Asciidoctor và Markdown, rồi biên soạn tài liệu trong CI.

**Tiêu chí hoàn thành:** template được kiểm thử bằng payload đã serialize qua HTTP; assertions xác nhận hành vi API; descriptor bao phủ payload cần công bố; snippet output được đọc sau khi test hoàn tất; các trường hợp biên và format đầu ra được kiểm tra.

## 14. Checklist trước khi commit

- [ ] Payload fixture đại diện cho request/response thực tế và chỉ dùng dữ liệu giả.
- [ ] Serializer tạo JSON đúng như endpoint công bố.
- [ ] Test có assertions cho status, media type và nội dung quan trọng.
- [ ] Descriptor mô tả đúng fields lồng nhau, mảng và field optional.
- [ ] Attributes ở cấp snippet/descriptor được truyền đúng key.
- [ ] Template render metadata đúng vào snippet đầu ra.
- [ ] Snippet verifier chạy sau documentation tests.
- [ ] Output directory cũ được làm sạch hoặc tách theo lần build.
- [ ] Ký tự đặc biệt, chuỗi rỗng, null và collection rỗng đã được cân nhắc.
- [ ] Mọi format được hỗ trợ đều có test render và build tài liệu.
- [ ] CI tạo artifact từ snippet mới của lần chạy hiện tại.

**Ghi nhớ:** Kiểm thử template không dừng ở việc kiểm tra file Mustache. Hãy chạy documentation tests với payload được serialize như API thật, xác nhận HTTP behavior và descriptor coverage, rồi đọc snippet đã render để chắc rằng metadata, field path, escaping và cú pháp đầu ra đều đúng trước khi biên soạn tài liệu.
