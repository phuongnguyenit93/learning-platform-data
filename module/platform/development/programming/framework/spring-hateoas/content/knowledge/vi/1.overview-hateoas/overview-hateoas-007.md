# Khái niệm affordance

## Mục tiêu

Sau bài này, bạn có thể giải thích affordance trong REST và Spring HATEOAS, phân biệt affordance với một đường dẫn thông thường, mô tả một hành động bằng metadata phù hợp, và kiểm thử các hành động mà API công bố theo trạng thái tài nguyên.

## 1. Vì sao API cần affordance?

Giả sử client gọi API để đọc đơn hàng `42`. Phản hồi có thể chứa dữ liệu đơn hàng và đường dẫn đến chính tài nguyên đó:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "/orders/42" }
  }
}
```

Đường dẫn `self` giúp client tìm lại đơn hàng. Tuy nhiên, chỉ nhìn vào phản hồi này, client chưa biết đơn hàng có thể được cập nhật, hủy hay thanh toán hay không. Nếu client tự ghép URL như `/orders/42/cancel`, nó phải biết trước cấu trúc endpoint và quy tắc nghiệp vụ của server.

Hypermedia giải quyết vấn đề khám phá bằng cách để server công bố các liên kết dẫn đến những tài nguyên hoặc bước tiếp theo. **Affordance** bổ sung mô tả về cách client có thể tương tác qua một liên kết: tên hành động, HTTP method, kiểu dữ liệu đầu vào và, khi có, kiểu dữ liệu đầu ra.

Ví dụ, phản hồi của đơn hàng đang chờ xử lý có thể cho biết hành động `update` dùng `PUT` và nhận dữ liệu cập nhật. Khi đơn hàng đã giao, server có thể không công bố affordance này nữa. Client đọc khả năng hiện có từ phản hồi thay vì tự suy đoán toàn bộ quy tắc chuyển trạng thái.

## 2. Phân biệt link và affordance

| Thành phần | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Link | Tài nguyên hoặc đích liên quan nằm ở đâu? | `self → /orders/42` |
| Link relation | Liên kết có ý nghĩa gì trong ngữ cảnh? | `self`, `next`, `payment` |
| Affordance | Có thể thực hiện tương tác nào qua đích đó và cần gửi dữ liệu gì? | `update`, `PUT`, đầu vào `OrderUpdate` |
| Endpoint | Server thực thi yêu cầu ở đâu và bằng quy tắc nào? | Controller xử lý `PUT /orders/42` |

Link và affordance có quan hệ gần nhau nhưng không đồng nghĩa. Một link thông thường có thể chỉ chứa `href` và relation. Affordance gắn thêm mô tả tương tác để client biết cách sử dụng đích đó. Affordance cũng không phải lời gọi hàm có thể thực thi trực tiếp trong client; client vẫn gửi HTTP request theo metadata được công bố.

Tên affordance thường mô tả hành động như `update`, `cancel` hoặc `pay`. Relation mô tả ý nghĩa của liên kết trong đồ thị tài nguyên. Không nên dùng hai khái niệm này thay thế cho nhau: `self` thường là relation của tài nguyên hiện tại, còn `update` có thể là tên một biểu mẫu hoặc hành động được mô tả trên liên kết đó.

## 3. Mô hình hóa affordance bằng Spring HATEOAS

Spring HATEOAS cung cấp API `Affordances` để bổ sung metadata tương tác cho `Link`. Kết hợp với `methodOn`, framework có thể suy ra đường dẫn và thông tin phương thức từ phương thức controller được tham chiếu. `withInput` cho biết kiểu dữ liệu client cần gửi.

Ví dụ dưới đây mô tả hành động cập nhật đơn hàng. Giả sử ứng dụng đã có lớp `Order`, DTO `OrderUpdate` và dịch vụ đọc/cập nhật đơn hàng.

Controller khai báo các thao tác HTTP thực tế:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<Order> getOrder(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @PutMapping("/{id}")
    public EntityModel<Order> updateOrder(
            @PathVariable UUID id,
            @RequestBody OrderUpdate request) {
        Order updated = orderService.update(id, request);
        return assembler.toModel(updated);
    }
}
```

Assembler xây dựng representation và công bố affordance cập nhật khi trạng thái đơn hàng cho phép:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel();

        if (!order.canBeUpdated()) {
            return EntityModel.of(order, self);
        }

        Link update = Affordances.of(self)
                .afford(methodOn(OrderController.class)
                        .updateOrder(order.getId(), null))
                .withName("update")
                .withInput(OrderUpdate.class)
                .toLink();

        return EntityModel.of(order, update);
    }
}
```

Các phần quan trọng:

- `linkTo(methodOn(...).getOrder(...)).withSelfRel()` tạo liên kết đến tài nguyên đơn hàng bằng thông tin mapping của controller.
- `Affordances.of(self)` bắt đầu mô tả tương tác trên liên kết hiện có.
- `afford(methodOn(...).updateOrder(...))` tham chiếu thao tác cập nhật. Giá trị `null` chỉ là đối số giữ chỗ để Spring HATEOAS phân tích chữ ký phương thức; đây không phải request được gửi đi.
- `withName("update")` đặt tên cho affordance.
- `withInput(OrderUpdate.class)` khai báo kiểu dữ liệu đầu vào mà client cần cung cấp.
- `toLink()` tạo link mang affordance để đưa vào representation.

Ví dụ tập trung vào một hành động để làm rõ cách khai báo. Khi tài nguyên có nhiều hành động, hãy thêm affordance tương ứng theo API của phiên bản Spring HATEOAS đang dùng và giữ các tên hành động ổn định. Có thể tổ chức logic tạo model trong `RepresentationModelAssembler` để controller không phải tự ghép metadata cho từng response.

## 4. Biểu diễn affordance bằng HAL-FORMS

HAL biểu diễn các liên kết trong phần `_links`. Để truyền thêm mô tả biểu mẫu và thao tác HTTP, Spring HATEOAS hỗ trợ HAL-FORMS với media type `application/prs.hal-forms+json`. Spring HATEOAS dùng metadata affordance để tạo các template trong phần `_templates`.

Ví dụ rút gọn về một đơn hàng có thể cập nhật:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "update": {
      "method": "PUT",
      "contentType": "application/json",
      "properties": [
        {
          "name": "shippingAddress",
          "required": true
        },
        {
          "name": "note",
          "required": false
        }
      ]
    }
  }
}
```

Đây là ví dụ minh họa cấu trúc, không phải JSON cố định cho mọi DTO. Các property thực tế phụ thuộc kiểu đầu vào, metadata của thuộc tính và cấu hình serialization. Trong ứng dụng Spring, có thể khai báo media type cần trả về ở mapping:

```java
@GetMapping(
    value = "/{id}",
    produces = MediaTypes.HAL_FORMS_JSON_VALUE
)
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Client yêu cầu HAL-FORMS bằng header `Accept: application/prs.hal-forms+json`, đọc template `update`, tạo dữ liệu theo các property được mô tả rồi gửi request bằng method và content type tương ứng. Nếu client chỉ yêu cầu HAL, response tập trung vào liên kết và không cung cấp đầy đủ mô tả biểu mẫu của HAL-FORMS. Vì vậy, server và client cần thống nhất media type mà hợp đồng API hỗ trợ.

## 5. Công bố affordance theo trạng thái và quyền truy cập

Affordance có ích khi phản ánh đúng những hành động hiện có tại thời điểm trả response. Chẳng hạn:

- Đơn hàng ở trạng thái `PENDING` có thể cho phép cập nhật hoặc hủy.
- Đơn hàng ở trạng thái `SHIPPED` có thể không còn affordance cập nhật địa chỉ giao hàng.
- Đơn hàng đã hoàn tất có thể chỉ còn các liên kết đọc hoặc xem hóa đơn.

Quyết định công bố hành động nên dựa trên trạng thái nghiệp vụ và quyền của người dùng hiện tại. Nếu khả năng cập nhật phụ thuộc người dùng, assembler cần nhận được kết quả kiểm tra quyền từ tầng phù hợp; không nên chỉ dựa vào trạng thái của entity.

Có ba nguyên tắc cần giữ:

1. **Mô tả đúng hợp đồng.** HTTP method, kiểu đầu vào và tên hành động phải khớp với endpoint thực tế. DTO đầu vào nên chỉ chứa trường client được phép thay đổi, thay vì nhận trực tiếp entity nội bộ.
2. **Công bố theo ngữ cảnh.** Chỉ thêm affordance khi hành động có ý nghĩa với tài nguyên và người dùng hiện tại. Điều này giúp client điều hướng giao diện phù hợp với trạng thái server.
3. **Vẫn kiểm tra ở server.** Việc không công bố affordance không bảo vệ endpoint. Client có thể gửi request thủ công hoặc dùng response cũ. Controller, service và security layer vẫn phải xác thực, phân quyền, kiểm tra trạng thái và dữ liệu đầu vào trên mỗi request.

Affordance giúp client giảm phụ thuộc vào cấu trúc URL và quy tắc chuyển trạng thái được hard-code. Khi server thay đổi đường dẫn nhưng vẫn giữ quan hệ và metadata tương tác phù hợp, client hypermedia có thể tiếp tục khám phá hành động qua response. Khả năng tiến hóa này chỉ hiệu quả khi các relation, tên affordance và schema đầu vào được quản lý như một phần của hợp đồng API.

## 6. Kiểm thử affordance trong response

Kiểm thử nên xác nhận cả liên kết điều hướng và mô tả hành động ở đúng media type. Ví dụ với MockMvc:

```java
mockMvc.perform(get("/orders/{id}", id)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.update.method").value("PUT"));
```

Cũng cần kiểm tra trường hợp không cho phép cập nhật. Với đơn hàng không còn ở trạng thái phù hợp, response không nên công bố template `update`:

```java
mockMvc.perform(get("/orders/{id}", shippedOrderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.update").doesNotExist());
```

Cuối cùng, kiểm thử trực tiếp endpoint cập nhật với người dùng không có quyền hoặc dữ liệu không hợp lệ. Response không có affordance là tín hiệu hướng dẫn cho client; kết quả kiểm tra bảo mật của request mới là cơ chế bảo vệ thực sự.

## 7. Quy trình sử dụng từ phía client

Một client hypermedia có thể làm việc theo trình tự sau:

1. Gửi GET đến entry point hoặc một liên kết đã biết, đồng thời yêu cầu media type mà client hỗ trợ.
2. Đọc `_links` để tìm tài nguyên liên quan và đọc `_templates` để khám phá các thao tác khả dụng.
3. Chọn template theo tên và tạo payload theo các property, method và content type được mô tả.
4. Gửi request đến target do response cung cấp.
5. Đọc response mới để biết trạng thái tài nguyên và các affordance tiếp theo.

Client vẫn cần hiểu ý nghĩa nghiệp vụ của những hành động mà nó hỗ trợ, nhưng không cần tự xây dựng mọi URL hoặc giả định rằng một hành động luôn khả dụng. Server giữ vai trò công bố trạng thái và các chuyển tiếp hợp lệ thông qua representation.

## Kết luận

Affordance mở rộng ý nghĩa của link bằng cách mô tả cách client tương tác với tài nguyên. Trong Spring HATEOAS, `Affordances` kết hợp với `methodOn`, `withName` và `withInput` giúp khai báo hành động dựa trên mapping controller và kiểu dữ liệu đầu vào. Khi được biểu diễn bằng HAL-FORMS, metadata này trở thành template mà client có thể khám phá và sử dụng. Thiết kế tốt cần công bố hành động theo trạng thái và quyền truy cập, đồng thời luôn thực thi kiểm tra nghiệp vụ và bảo mật ở server.

