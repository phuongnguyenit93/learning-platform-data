# Kiểm tra model trong Spring HATEOAS

Trong Spring HATEOAS, một representation model chứa dữ liệu công khai của tài nguyên cùng các liên kết hypermedia. Kiểm thử model vì thế cần xác nhận cả hai phần: dữ liệu được chuyển đổi chính xác và những liên kết được công bố phản ánh đúng hợp đồng API. Một model có đủ trường nhưng thiếu `self`, phát ra sai relation hoặc vẫn công bố thao tác không còn hợp lệ đều có thể khiến client hoạt động sai.

Bài học này hướng dẫn kiểm tra model ở nhiều mức: kiểm thử trực tiếp `RepresentationModel`, kiểm thử assembler, kiểm thử response HAL qua HTTP và kiểm thử các liên kết theo trạng thái nghiệp vụ. Ví dụ dùng API quản lý đơn hàng với hai quan hệ chính: `self` để đọc tài nguyên và `cancel` để hủy đơn khi điều kiện cho phép.

## 1. Xác định điều cần kiểm tra

Trước khi viết test, hãy xác định hợp đồng của representation. Với một model đơn hàng, hợp đồng có thể gồm:

- Các trường dữ liệu công khai như `id`, `status`, `total` có đúng giá trị và kiểu dữ liệu.
- Quan hệ `self` luôn trỏ đến tài nguyên hiện tại.
- Quan hệ nghiệp vụ `cancel` chỉ xuất hiện khi đơn hàng có thể hủy.
- Liên kết được tạo từ mapping hiện hành của controller, gồm cả path variable cần thiết.
- Response được tuần tự hóa theo media type mà client yêu cầu, chẳng hạn HAL JSON.
- Endpoint thực hiện thao tác vẫn kiểm tra quyền và trạng thái khi nhận request.

Có thể chia kiểm thử thành ba mức:

| Mức kiểm thử | Phần được xác nhận | Công cụ thường dùng |
| --- | --- | --- |
| Model/assembler unit test | Trường dữ liệu, relation, điều kiện tạo liên kết và kết quả chuyển đổi. | JUnit, AssertJ, Mockito hoặc fixture của dự án. |
| Web/API integration test | HTTP status, content type, cấu trúc JSON, `href` và relation sau serialization. | MockMvc hoặc WebTestClient. |
| Client traversal/contract test | Client tìm relation và đi theo liên kết mà không tự ghép URI. | Client thử nghiệm, `LinkDiscoverer` hoặc kiểm thử hợp đồng. |

Không phải mọi test đều cần kiểm tra toàn bộ JSON. Unit test nên tập trung vào hành vi của model và assembler; kiểm thử HTTP xác nhận kết quả serialization và hợp đồng mà client nhìn thấy.

## 2. Kiểm tra trực tiếp RepresentationModel

`RepresentationModel` cung cấp các phương thức để thêm, truy vấn và loại bỏ liên kết. Khi kiểm tra model trong bộ nhớ, những phương thức hữu ích gồm:

- `add(...)`: thêm một hoặc nhiều liên kết.
- `getLinks()`: lấy tập hợp liên kết hiện có.
- `hasLinks()`: kiểm tra model có liên kết hay không.
- `hasLink("self")`: kiểm tra model có relation cụ thể.
- `getLink("self")`: lấy liên kết theo relation dưới dạng `Optional`.
- `getRequiredLink("self")`: lấy liên kết bắt buộc; ném lỗi nếu relation không tồn tại.

Ví dụ với một model đơn giản:

```java
class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;

    OrderModel(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

Một unit test có thể tạo model trực tiếp rồi kiểm tra dữ liệu và liên kết:

```java
@Test
void modelStoresItsDataAndLinks() {
    UUID id = UUID.fromString("00000000-0000-0000-0000-000000000042");
    OrderModel model = new OrderModel(id, "PENDING");
    model.add(Link.of("/orders/42", "self"));
    model.add(Link.of("/orders/42/cancel", "cancel"));

    assertThat(model.getId()).isEqualTo(id);
    assertThat(model.getStatus()).isEqualTo("PENDING");
    assertThat(model.hasLink("self")).isTrue();
    assertThat(model.hasLink("cancel")).isTrue();
    assertThat(model.getRequiredLink("self").getHref())
            .isEqualTo("/orders/42");
}
```

Test này kiểm tra lớp model và API liên kết của Spring HATEOAS. Nó chưa xác nhận controller tạo URI đúng hoặc Jackson xuất JSON theo HAL; hai việc đó cần kiểm thử ở lớp cao hơn.

Khi chỉ quan tâm một relation, hãy kiểm tra bằng `hasLink` hoặc `getRequiredLink`. Nếu cần kiểm tra toàn bộ danh sách, có thể duyệt `getLinks()` và so sánh relation/URI tương ứng. Tránh phụ thuộc vào thứ tự liên kết vì thứ tự không phải lúc nào cũng là một phần của hợp đồng API.

## 3. Kiểm tra Link và relation

Một `Link` chứa URI đích và quan hệ. Test nên kiểm tra hai yếu tố này theo ý nghĩa của hợp đồng:

```java
Link self = model.getRequiredLink("self");

assertThat(self.getRel().value()).isEqualTo("self");
assertThat(self.getHref()).isEqualTo("/orders/42");
```

Với relation chuẩn, có thể dùng hằng số từ `IanaLinkRelations` để giảm lỗi đánh máy:

```java
assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
```

Các relation nghiệp vụ như `cancel`, `approve` hoặc `shipment` thường là quan hệ riêng của API. Tên và ý nghĩa của chúng cần được thống nhất giữa server và client. Test nên xác nhận relation đúng theo hợp đồng đã định nghĩa, thay vì chỉ kiểm tra model có ít nhất một liên kết.

Nếu URI chứa path variable, query parameter hoặc URI template, hãy kiểm tra đúng phần cần thiết. Ví dụ, một liên kết phân trang có thể chứa query template cho `page` và `size`; khi đó cần xác nhận liên kết được đánh dấu là templated và các biến có tên đúng. Không nên so sánh URI đã encode bằng một chuỗi tự dựng nếu encoding không phải nội dung mà test muốn kiểm tra.

Với các liên kết được tạo bằng `WebMvcLinkBuilder`, kiểm tra `href` trong kiểm thử web thường đáng tin cậy hơn unit test assembler chạy ngoài request context. Trong unit test thuần, nếu assembler cần thông tin request để dựng URI, phải thiết lập request context phù hợp; nếu không, hãy giới hạn unit test ở relation và dữ liệu, rồi kiểm tra URI qua MockMvc/WebTestClient.

## 4. Kiểm thử RepresentationModelAssembler

Assembler chịu trách nhiệm chuyển domain object thành representation model. Vì vậy, unit test assembler nên xác nhận:

1. Trường dữ liệu trong model lấy đúng từ domain object.
2. Relation `self` được tạo cho đúng tài nguyên.
3. Các relation nghiệp vụ xuất hiện đúng điều kiện.
4. Những relation không còn hợp lệ sẽ không được thêm.
5. Việc chuyển đổi không làm lộ trường nội bộ không thuộc hợp đồng API.

Giả sử assembler có dạng:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        UUID id = order.getId();
        OrderModel model = new OrderModel(
                id,
                order.getStatus().name()
        );

        model.add(linkTo(methodOn(OrderController.class).one(id)).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel"));
        }

        return model;
    }
}
```

Với đơn hàng đang chờ xử lý, test kiểm tra liên kết hủy xuất hiện:

```java
@Test
void addsCancelLinkWhenOrderCanBeCancelled() {
    Order order = anOrderInStatus(OrderStatus.PENDING);

    OrderModel model = assembler.toModel(order);

    assertThat(model.getId()).isEqualTo(order.getId());
    assertThat(model.getStatus()).isEqualTo("PENDING");
    assertThat(model.hasLink("self")).isTrue();
    assertThat(model.hasLink("cancel")).isTrue();
}
```

Với đơn hàng đã giao, test xác nhận liên kết hủy không xuất hiện:

```java
@Test
void omitsCancelLinkWhenOrderCannotBeCancelled() {
    Order order = anOrderInStatus(OrderStatus.SHIPPED);

    OrderModel model = assembler.toModel(order);

    assertThat(model.hasLink("self")).isTrue();
    assertThat(model.hasLink("cancel")).isFalse();
}
```

`anOrderInStatus` đại diện cho fixture hoặc factory tạo domain object của dự án. Khi assembler dùng `WebMvcLinkBuilder`, cần cung cấp request context trong unit test nếu việc dựng URI phụ thuộc request hiện tại. Một lựa chọn khác là kiểm tra relation trong unit test và để kiểm thử controller xác nhận `href` chính xác.

Đối với collection, kiểm tra cả hai cấp: liên kết của từng phần tử và liên kết của `CollectionModel`. Một lỗi thường gặp là các item có `self` đúng nhưng collection thiếu `self` hoặc `next`. Nếu API hỗ trợ phân trang, cần kiểm tra `first`, `prev`, `self`, `next`, `last` theo trang hiện tại và số trang thực tế.

## 5. Kiểm tra response HAL bằng MockMvc

Unit test không thể xác nhận đầy đủ cách model được tuần tự hóa. Với Spring MVC, MockMvc cho phép gửi request đến controller và kiểm tra response HTTP. Khi client yêu cầu HAL, dùng `MediaTypes.HAL_JSON` trong header `Accept`:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$.status").value("PENDING"))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Các assertion trên xác nhận status HTTP, media type, trường dữ liệu và hai relation. Nếu hợp đồng yêu cầu một URI cụ thể, hãy kiểm tra giá trị `href`:

```java
.andExpect(jsonPath("$._links.self.href")
        .value(endsWith("/orders/" + orderId)))
```

Ví dụ này dùng matcher `endsWith` của Hamcrest. Cách kiểm tra hậu tố phù hợp khi host hoặc context path có thể thay đổi giữa môi trường. Nếu hợp đồng quy định URI tuyệt đối hoặc đường dẫn đầy đủ, hãy so sánh với giá trị được mong đợi tương ứng.

Với đơn hàng không thể hủy, kiểm tra relation đó không xuất hiện:

```java
mockMvc.perform(get("/orders/{id}", shippedOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Trong dự án thực tế, test có thể dùng `@WebMvcTest` để tập trung vào lớp web và mock service, hoặc `@SpringBootTest` cùng `@AutoConfigureMockMvc` để kiểm tra tích hợp rộng hơn. Hãy bảo đảm cấu hình Spring HATEOAS và Jackson cần thiết được nạp trong test context; nếu thiếu cấu hình hypermedia, kết quả serialization có thể khác ứng dụng khi chạy thật.

## 6. Kiểm thử collection và tài nguyên nhúng

Collection HAL thường biểu diễn các item bên dưới `_embedded` và các liên kết điều hướng bên dưới `_links`. Cấu trúc cụ thể phụ thuộc relation của collection. Ví dụ response có thể chứa:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "status": "PENDING",
        "_links": {
          "self": { "href": "/orders/42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" },
    "next": { "href": "/orders?page=1" }
  }
}
```

Test collection nên kiểm tra:

- Relation của collection được đặt đúng tên.
- Mỗi phần tử có dữ liệu và liên kết phù hợp.
- Collection có liên kết điều hướng đúng khi còn trang tiếp theo.
- Trang đầu không có `prev` nếu hợp đồng không công bố liên kết đó; trang cuối không có `next`.
- Collection rỗng vẫn có cấu trúc và liên kết cấp collection như hợp đồng quy định.

Không nên mặc định mọi collection đều có `next` hoặc `_embedded` luôn chứa ít nhất một phần tử. Hãy tạo dữ liệu test cho collection rỗng, một phần tử, nhiều phần tử, trang đầu, trang giữa và trang cuối theo các trường hợp API thực sự hỗ trợ.

Nếu relation hoặc tên collection được tùy chỉnh bằng `@Relation`, assertion JSON cần dùng đúng tên relation đã cấu hình. Đó là một phần của hợp đồng được client đọc, nên việc đổi tên cần được xem xét như thay đổi API.

## 7. Kiểm thử media type và content negotiation

Spring HATEOAS có thể hỗ trợ nhiều định dạng hypermedia. Một client thường chọn định dạng bằng header `Accept`. Kiểm thử cần xác nhận response tương ứng với media type được hỗ trợ và cách ứng dụng xử lý media type không hỗ trợ.

Với HAL JSON:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON));
```

Nếu ứng dụng công bố một media type khác, hãy viết test riêng cho media type đó và kiểm tra đúng cấu trúc representation. Với media type không được hỗ trợ, kết quả có thể là `406 Not Acceptable` tùy cấu hình content negotiation của ứng dụng. Hãy xác định hành vi mong đợi trong hợp đồng và kiểm thử hành vi đó.

Không nên chỉ kiểm tra body có JSON hợp lệ. Một response JSON thông thường không có nghĩa client nhận được HAL. Kiểm tra content type và vị trí liên kết (`_links`) để xác nhận đúng định dạng.

## 8. Kiểm thử URI và khả năng client đi theo liên kết

Một mục tiêu của HATEOAS là để client lấy URI tiếp theo từ response. Vì vậy, ngoài việc xác nhận `href` có giá trị, nên có một kiểm thử client đơn giản:

1. Gọi URI entry point đã biết.
2. Đọc relation `orders` hoặc relation điều hướng phù hợp.
3. Lấy `href` từ relation đó.
4. Gọi URI nhận được và tiếp tục đọc liên kết từ response mới.
5. Xác nhận client không cần tự ghép URI theo cấu trúc nội bộ của server.

Khi mapping controller thay đổi, test traversal có thể phát hiện client còn phụ thuộc vào URL cũ. Để kiểm thử ở mức thấp hơn, có thể dùng `LinkDiscoverer` phù hợp với media type để trích xuất liên kết theo relation từ response. Điều này giúp test mô phỏng cách một hypermedia client tìm liên kết thay vì truy cập trực tiếp một vị trí JSON đã cố định.

Nếu liên kết có URI template, client cần biết cách điền biến. Test nên xác nhận template có các biến cần thiết và client mở rộng template với giá trị đúng. Với liên kết đã hoàn chỉnh, kiểm tra URI sau khi tạo để bảo đảm path variable và query parameter được encode đúng.

## 9. Kiểm thử bảo mật và trạng thái độc lập với liên kết

Liên kết là thông tin điều hướng được công bố trong representation. Nó không phải cơ chế phân quyền. Không xuất `cancel` cho người dùng không có quyền giúp giao diện tránh đề xuất thao tác không phù hợp, nhưng server vẫn phải bảo vệ endpoint `POST /orders/{id}/cancel`.

Hãy có các test riêng cho endpoint thao tác:

- Người dùng chưa xác thực nhận kết quả theo chính sách bảo mật, thường là `401 Unauthorized`.
- Người dùng đã xác thực nhưng không có quyền nhận kết quả theo chính sách, thường là `403 Forbidden` hoặc cách che giấu tài nguyên mà ứng dụng quy định.
- Đơn hàng đã giao hoặc đã hủy không thể bị hủy lần nữa; service/controller trả lỗi nghiệp vụ phù hợp.
- Hai request đồng thời không thể cùng thực hiện một chuyển trạng thái trái quy tắc.

Các mã status cụ thể phụ thuộc hợp đồng API và cấu hình bảo mật. Điều quan trọng là test chứng minh endpoint kiểm tra lại quyền và trạng thái tại thời điểm request đến, ngay cả khi client giữ một liên kết cũ từ response trước đó.

## 10. Những assertion dễ làm test mong manh

Một số cách kiểm tra khiến test khó bảo trì khi representation phát triển:

- **So sánh toàn bộ JSON dạng chuỗi.** Thứ tự thuộc tính hoặc định dạng có thể thay đổi mà không làm thay đổi ngữ nghĩa. Ưu tiên JSONPath hoặc parser phù hợp.
- **Phụ thuộc thứ tự link.** Hợp đồng xác định relation và đích, không nhất thiết xác định thứ tự xuất hiện. Tìm theo relation.
- **Chỉ kiểm tra status `200`.** Status thành công không chứng minh model có đủ liên kết hoặc đúng media type.
- **Kiểm tra URI bằng cách tự dựng cùng logic với code sản xuất.** Test có thể lặp lại cùng một lỗi. Dùng URI kỳ vọng độc lập hoặc kiểm tra theo phần hợp đồng ổn định.
- **Chỉ test trạng thái thành công.** Cần test cả khi liên kết không được công bố, collection rỗng, trang cuối, thiếu quyền và trạng thái không hợp lệ.
- **Dùng một integration test cho mọi chi tiết.** Tách unit test assembler khỏi test HTTP để lỗi dễ xác định và test chạy nhanh hơn.

Hãy kiểm tra những gì client được phép dựa vào: dữ liệu công khai, media type, relation, URI và hành vi thao tác. Các thuộc tính nội bộ không thuộc hợp đồng không nên trở thành assertion cố định.

## 11. Quy trình xây dựng bộ kiểm thử

Với một model mới, có thể triển khai kiểm thử theo trình tự sau:

1. **Viết hợp đồng model.** Liệt kê các trường công khai, relation bắt buộc, relation có điều kiện và media type.
2. **Kiểm thử model cơ bản.** Tạo model, thêm link và xác nhận dữ liệu cùng API truy vấn relation.
3. **Kiểm thử assembler.** Dùng fixture cho các trạng thái nghiệp vụ khác nhau; xác nhận model và các liên kết được tạo đúng.
4. **Kiểm thử controller.** Gửi request với `Accept` phù hợp; xác nhận status, content type và cấu trúc HAL.
5. **Kiểm thử collection.** Kiểm tra relation cấp collection, embedded resources, phân trang và trường hợp rỗng.
6. **Kiểm thử client traversal.** Đọc liên kết từ response và đi theo `href`.
7. **Kiểm thử quyền và trạng thái.** Gọi endpoint trực tiếp với request không hợp lệ để xác nhận server vẫn bảo vệ nghiệp vụ.

Quy trình này tạo ra các test có phạm vi rõ. Khi một test thất bại, bạn có thể xác định lỗi nằm ở chuyển đổi model, tạo liên kết, serialization, content negotiation hay xử lý request.

## 12. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng bộ test cho API đơn hàng với các yêu cầu sau:

1. Test `OrderModel` có đúng `id`, `status` và `total`.
2. Test model có relation `self` và `href` trỏ tới tài nguyên tương ứng.
3. Test assembler chỉ thêm `cancel` khi đơn hàng ở trạng thái cho phép.
4. Test response HAL có content type `application/hal+json` và `_links` đúng.
5. Test collection có relation `orders`, item có `self`, và liên kết `next` chỉ xuất hiện khi còn trang.
6. Test collection rỗng và collection chỉ có một trang.
7. Test client lấy `href` từ response và gọi endpoint tiếp theo.
8. Test endpoint hủy từ chối người dùng không có quyền và đơn hàng ở trạng thái không hợp lệ.
9. Đổi mapping của endpoint chi tiết, chạy lại test traversal và xác nhận client vẫn hoạt động nếu relation được giữ ổn định.

Bạn đã kiểm tra model tốt khi có thể chứng minh representation đúng ở cả trong bộ nhớ và trên HTTP; relation phản ánh trạng thái nghiệp vụ; client có thể khám phá URI từ response; và endpoint vẫn bảo vệ thao tác khi request đến. Những kiểm thử này giúp nhóm thay đổi cấu trúc model hoặc URI có kiểm soát mà vẫn nhận biết sớm khi hợp đồng hypermedia bị phá vỡ.
