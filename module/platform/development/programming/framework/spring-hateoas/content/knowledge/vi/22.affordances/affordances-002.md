# Mô tả hành động khả dụng

## Mục tiêu

Sau bài này, bạn có thể giải thích affordance trong REST hypermedia, phân biệt affordance với link thông thường, mô tả HTTP method và dữ liệu đầu vào của hành động bằng Spring HATEOAS, công bố template qua HAL-FORMS và kiểm thử các hành động được API cung cấp theo trạng thái tài nguyên.

## 1. Affordance giúp client hiểu cách tương tác

Một response REST có thể trả dữ liệu đơn hàng cùng các liên kết:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
```

Các link cho client biết tài nguyên hiện tại ở đâu và có tài nguyên liên quan nào. Nhưng response này chưa mô tả đầy đủ cách thực hiện hành động cập nhật hoặc hủy đơn hàng. Client không thể chỉ nhìn vào `href` để biết chắc phải dùng HTTP method nào, cần gửi payload gì hoặc dữ liệu đầu vào có những trường nào.

**Affordance** là mô tả về một tương tác khả dụng gắn với một link. Tùy định dạng hypermedia, mô tả này có thể cung cấp:

- Tên hành động hoặc template.
- HTTP method như `PUT`, `POST` hoặc `DELETE`.
- Kiểu nội dung request, ví dụ `application/json`.
- Các trường đầu vào, kiểu dữ liệu và thông tin bắt buộc nếu có.
- Kiểu representation đầu ra hoặc thông tin về kết quả, khi cần khai báo tường minh.

Client có thể đọc metadata này để tạo biểu mẫu, chọn phương thức gửi request và xây dựng payload phù hợp. Server công bố những hành động có ý nghĩa ở trạng thái hiện tại của tài nguyên.

## 2. Phân biệt link, relation và affordance

Ba khái niệm có liên quan nhưng trả lời những câu hỏi khác nhau:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Link | Đích liên kết ở đâu? | `href: /orders/42` |
| Relation | Liên kết có ý nghĩa gì? | `self`, `customer`, `payment` |
| Affordance | Có thể tương tác với đích như thế nào? | Hành động `update`, method `PUT`, input `OrderUpdate` |

Một link HAL thông thường có relation và href. Affordance bổ sung metadata tương tác cho link. Relation `self` cho biết link trỏ đến chính tài nguyên; tên affordance `update` có thể mô tả một template thao tác trên tài nguyên đó.

Affordance không phải lời gọi hàm và cũng không thực hiện hành động. Nó là metadata để client hiểu cách gửi một HTTP request. Server vẫn phải xác thực, phân quyền, kiểm tra trạng thái nghiệp vụ và validate payload khi request thực sự đến.

## 3. Affordance trong Spring HATEOAS

Spring HATEOAS cung cấp API `Affordances` để gắn mô tả hành động vào một `Link`. Thông tin affordance có thể được suy ra từ mapping controller được tham chiếu qua `methodOn(...)`, sau đó được bổ sung bằng kiểu đầu vào hoặc đầu ra.

Các thành phần thường dùng:

| API | Vai trò |
|---|---|
| `Affordances.of(link)` | Bắt đầu xây dựng affordance trên một link hiện có |
| `afford(methodOn(...))` | Tham chiếu phương thức controller đại diện cho hành động |
| `withInput(Type.class)` | Khai báo kiểu dữ liệu request |
| `withOutput(Type.class)` | Khai báo kiểu dữ liệu response khi cần chỉ rõ |
| `withName("...")` | Đặt tên affordance/template |
| `toLink()` | Tạo link mang metadata affordance |

Ví dụ ngắn:

```java
Link self = linkTo(methodOn(OrderController.class)
        .getOrder(orderId))
        .withSelfRel();

Link update = Affordances.of(self)
        .afford(methodOn(OrderController.class)
                .updateOrder(orderId, null))
        .withInput(OrderUpdate.class)
        .withName("update")
        .toLink();
```

`methodOn(...)` giúp Spring HATEOAS xác định mapping và chữ ký phương thức. Đối số `null` là giá trị giữ chỗ cho request body khi tạo tham chiếu; nó không gửi request và không chạy phương thức cập nhật. `withInput(OrderUpdate.class)` cung cấp kiểu dữ liệu đầu vào mà client cần gửi.

## 4. Khai báo controller và DTO cho hành động

Giả sử API đơn hàng hỗ trợ đọc, cập nhật và hủy. Mỗi thao tác có mapping HTTP rõ ràng:

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

    @GetMapping(
        value = "/{id}",
        produces = MediaTypes.HAL_FORMS_JSON_VALUE
    )
    public EntityModel<OrderView> getOrder(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @PutMapping("/{id}")
    public EntityModel<OrderView> updateOrder(
            @PathVariable UUID id,
            @RequestBody OrderUpdate request) {
        return assembler.toModel(orderService.update(id, request));
    }

    @PostMapping("/{id}/cancellations")
    public EntityModel<OrderView> cancelOrder(
            @PathVariable UUID id,
            @RequestBody CancellationRequest request) {
        return assembler.toModel(orderService.cancel(id, request));
    }
}
```

Các DTO thể hiện rõ dữ liệu mà client được phép gửi:

```java
public record OrderUpdate(
        String shippingAddress,
        String note
) {
}

public record CancellationRequest(
        String reason
) {
}

public record OrderView(
        UUID id,
        String status,
        BigDecimal total
) {
}
```

DTO đầu vào nên chỉ chứa các trường mà client được phép thay đổi. Tránh nhận trực tiếp entity persistence, vì entity có thể chứa trường nội bộ hoặc trạng thái mà client không được phép ghi.

Trong ứng dụng thực tế, hãy bổ sung validation như `@NotBlank`, `@Size` hoặc constraint phù hợp trên DTO. Metadata template có thể phản ánh một phần thông tin thuộc tính và ràng buộc mà framework nhận diện, nhưng validation phía server vẫn là nguồn quyết định cuối cùng.

## 5. Gắn nhiều affordance vào link của tài nguyên

Assembler tạo representation đơn hàng và link `self`. Trên link đó, ta mô tả các hành động cập nhật và hủy:

```java
@Component
public class OrderModelAssembler {

    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        Link self = linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel();

        Link withActions = Affordances.of(self)
                .afford(methodOn(OrderController.class)
                        .updateOrder(order.getId(), null))
                .withInput(OrderUpdate.class)
                .withName("update")
                .andAfford(methodOn(OrderController.class)
                        .cancelOrder(order.getId(), null))
                .withInput(CancellationRequest.class)
                .withName("cancel")
                .toLink();

        return EntityModel.of(view, withActions);
    }
}
```

Các import chính:

```java
import org.springframework.hateoas.Affordances;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Trong ví dụ:

1. `self` xác định URI của đơn hàng hiện tại.
2. `afford(...updateOrder...)` mô tả thao tác cập nhật.
3. `withInput(OrderUpdate.class)` khai báo DTO request của thao tác cập nhật.
4. `withName("update")` đặt tên template là `update`.
5. `andAfford(...cancelOrder...)` thêm một thao tác khác trên cùng link.
6. `withInput(CancellationRequest.class)` khai báo payload cho hành động hủy.
7. `withName("cancel")` đặt tên template hủy.
8. `toLink()` tạo link chứa các affordance đã khai báo.

Cách này giúp client khám phá các hành động gắn với tài nguyên mà không cần tự ghi nhớ mọi endpoint và cấu trúc payload. Nếu một thao tác không có body, không cần khai báo input DTO cho thao tác đó. Khi kiểu response không thể suy ra rõ từ chữ ký controller, có thể dùng `withOutput(...)` để cung cấp kiểu đầu ra tường minh.

## 6. HAL-FORMS biểu diễn affordance như thế nào?

HAL biểu diễn link trong `_links`. Để mô tả template thao tác cùng method và các trường đầu vào, Spring HATEOAS hỗ trợ HAL-FORMS với media type:

```text
application/prs.hal-forms+json
```

Khi client yêu cầu HAL-FORMS, metadata affordance có thể được tuần tự hóa trong phần `_templates`. Ví dụ minh họa:

```json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000,
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
    },
    "cancel": {
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "required": true
        }
      ]
    }
  }
}
```

Đây là hình dạng minh họa để giải thích ý nghĩa. JSON thực tế phụ thuộc chữ ký controller, DTO, metadata validation và cấu hình serialization. Tên template được lấy từ `withName(...)`; method được suy ra từ mapping HTTP được tham chiếu.

Client yêu cầu HAL-FORMS bằng header:

```http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
```

Controller có thể khai báo media type ở `produces` như ví dụ trước. Ứng dụng cũng cần dependency và message converter Spring HATEOAS tương ứng. Nếu client chỉ yêu cầu HAL (`application/hal+json`), response HAL thông thường không cung cấp đầy đủ template tương tác của HAL-FORMS.

## 7. Khi nào công bố affordance?

Affordance nên phản ánh hành động có thể thực hiện trong ngữ cảnh hiện tại. Ví dụ với đơn hàng:

| Trạng thái | Affordance có thể công bố |
|---|---|
| `PENDING` | `update`, `cancel`, có thể `pay` |
| `PAID` | Có thể `shipment`, không còn `cancel` nếu nghiệp vụ không cho phép |
| `SHIPPED` | `tracking`, có thể `return` |
| `CANCELLED` | Chỉ các thao tác đọc hoặc xem lịch sử |

Bảng chỉ minh họa; quy tắc thực tế phụ thuộc domain. Assembler có thể tạo affordance có điều kiện:

```java
Link self = linkTo(methodOn(OrderController.class)
        .getOrder(order.getId()))
        .withSelfRel();

if (order.canBeUpdated() && order.canBeCancelled()) {
    Link actions = Affordances.of(self)
            .afford(methodOn(OrderController.class)
                    .updateOrder(order.getId(), null))
            .withInput(OrderUpdate.class)
            .withName("update")
            .andAfford(methodOn(OrderController.class)
                    .cancelOrder(order.getId(), null))
            .withInput(CancellationRequest.class)
            .withName("cancel")
            .toLink();

    return EntityModel.of(view, actions);
}

if (order.canBeUpdated()) {
    Link update = Affordances.of(self)
            .afford(methodOn(OrderController.class)
                    .updateOrder(order.getId(), null))
            .withInput(OrderUpdate.class)
            .withName("update")
            .toLink();
    return EntityModel.of(view, update);
}

if (order.canBeCancelled()) {
    Link cancel = Affordances.of(self)
            .afford(methodOn(OrderController.class)
                    .cancelOrder(order.getId(), null))
            .withInput(CancellationRequest.class)
            .withName("cancel")
            .toLink();
    return EntityModel.of(view, cancel);
}

return EntityModel.of(view, self);
```

Đoạn minh họa xử lý bốn trường hợp: có cả hai hành động, chỉ cập nhật, chỉ hủy hoặc không có hành động nào. Khi có cả hai, `andAfford(...)` thêm affordance thứ hai vào cùng link. Khi chỉ có một hành động, builder chỉ tạo affordance tương ứng; khi không có hành động, representation giữ link `self`.

Nếu hành động phụ thuộc quyền truy cập, hãy dùng policy hoặc service authorization để xác định khả năng hiện tại. Không nên chỉ dựa vào trạng thái entity. Khi người dùng không có quyền hủy, response có thể không công bố affordance `cancel`.

Việc ẩn affordance không phải cơ chế bảo mật. Client có thể gửi request thủ công hoặc sử dụng template đã lưu từ response cũ. Endpoint phải kiểm tra lại quyền, trạng thái và dữ liệu đầu vào mỗi lần nhận request.

## 8. Affordance và tiến hóa hợp đồng API

Affordance giúp giảm phụ thuộc vào chi tiết endpoint được hard-code trong client. Client có thể đọc link, relation và template để biết cách tiếp tục tương tác. Server có thể thay đổi đường dẫn hoặc cấu trúc nội bộ mà vẫn giữ khả năng khám phá nếu hợp đồng hypermedia được duy trì.

Tuy vậy, affordance vẫn là một phần của hợp đồng công khai. Các yếu tố cần quản lý ổn định:

- Relation của link và tên template.
- HTTP method được công bố.
- Tên, kiểu và semantics của các trường input.
- Content type của request.
- Ý nghĩa của hành động trong từng trạng thái.
- Kiểu output hoặc semantics của response sau thao tác.

Đổi tên template `update` thành `modify` có thể làm client không tìm thấy hành động. Đổi tên trường `shippingAddress` hoặc thay đổi ý nghĩa của nó cũng có thể phá vỡ payload client tạo ra. Hãy xem các thay đổi này như thay đổi hợp đồng API, có versioning hoặc chiến lược tương thích khi cần.

Không nên công bố template cho endpoint chưa tồn tại hoặc không hỗ trợ method tương ứng. Affordance phải được tạo từ mapping thật và được kiểm thử để tránh metadata lệch với endpoint.

## 9. Kiểm thử affordance bằng MockMvc

Kiểm thử cần xác nhận cả media type HAL-FORMS và metadata template được công bố. Ví dụ:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.update.method").value("PUT"))
    .andExpect(jsonPath("$._templates.cancel.method").value("POST"))
    .andExpect(jsonPath("$._templates.update.properties[0].name")
            .value("shippingAddress"));
```

Nếu đơn hàng đã giao và không thể hủy, template `cancel` không nên xuất hiện:

```java
mockMvc.perform(get("/orders/{id}", shippedOrderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates.cancel").doesNotExist());
```

Test trên tập trung xác nhận template `cancel` vắng mặt khi đơn đã giao. Nếu policy cũng cấm cập nhật trong trạng thái này, có thể bổ sung assertion cho template `update`; hãy điều chỉnh theo quy tắc nghiệp vụ thật.

Ngoài response, cần kiểm thử endpoint thực thi:

- Gửi request `PUT` theo template update với payload hợp lệ và xác nhận tài nguyên được cập nhật.
- Gửi request `POST` theo template cancel và xác nhận trạng thái thay đổi.
- Gửi payload thiếu hoặc sai định dạng và xác nhận validation hoạt động.
- Gửi request bởi người dùng không có quyền hoặc với trạng thái không hợp lệ và xác nhận server từ chối.

Kiểm thử template chỉ xác nhận server công bố mô tả đúng; kiểm thử endpoint xác nhận server thực thi đúng hành động.

## 10. Những lỗi thường gặp

**Nhầm affordance với link thông thường.** Link chỉ cung cấp đích và relation. Nếu client cần method và payload, hãy mô tả affordance và dùng media type hỗ trợ metadata tương tác.

**Chỉ đặt tên template mà không khai báo input.** Client có thể biết hành động tên gì nhưng không biết cần gửi dữ liệu nào. Dùng `withInput(...)` khi endpoint nhận request body.

**DTO input chứa quá nhiều trường.** Chỉ đưa các trường client được phép thay đổi vào DTO. Không dùng entity persistence làm payload cập nhật tổng quát.

**Mapping và affordance không khớp.** Method hoặc chữ ký endpoint thay đổi nhưng template vẫn được tạo từ mapping khác. Dùng `methodOn(...)` trỏ đến phương thức thật và kiểm thử method được tuần tự hóa.

**Công bố hành động theo trạng thái nhưng bỏ qua quyền.** Hãy xét cả trạng thái lẫn quyền hiện tại khi tạo template.

**Tin rằng ẩn affordance bảo vệ endpoint.** Server vẫn phải kiểm tra authorization và nghiệp vụ ở request thực tế.

**Yêu cầu HAL nhưng kiểm tra template HAL-FORMS.** Chọn đúng media type trong header `Accept` và assertion tương ứng.

**Không kiểm tra thay đổi hợp đồng.** Tên template, field input và method là những chi tiết client có thể phụ thuộc. Quản lý chúng như một phần API contract.

## 11. Nguyên tắc thiết kế

- Gắn affordance vào link của tài nguyên mà hành động thao tác.
- Dùng `methodOn(...)` để tham chiếu mapping controller thực tế.
- Khai báo `withInput(...)` cho request body và `withOutput(...)` khi cần kiểu đầu ra tường minh.
- Đặt tên template ngắn, ổn định và có ý nghĩa nghiệp vụ.
- Công bố affordance theo trạng thái và quyền truy cập hiện tại.
- Dùng HAL-FORMS khi client cần template có method và các trường đầu vào.
- Giữ DTO request nhỏ, rõ ràng và có validation.
- Kiểm thử cả metadata template lẫn endpoint thực thi.
- Xem tên template, relation, method và schema input là một phần hợp đồng API.

## Kết luận

Affordance mở rộng link hypermedia bằng cách mô tả cách client có thể tương tác với tài nguyên. Spring HATEOAS dùng `Affordances.of(link)`, `afford(methodOn(...))`, `withInput(...)` và tên template để mô tả hành động từ mapping controller. Khi được tuần tự hóa thành HAL-FORMS, metadata trở thành template mà client có thể khám phá và sử dụng. Hãy công bố hành động theo trạng thái và quyền, giữ schema ổn định, đồng thời kiểm thử cả template lẫn endpoint để bảo vệ hợp đồng API.

