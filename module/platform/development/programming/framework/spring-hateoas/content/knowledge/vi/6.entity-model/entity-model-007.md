# Link đến hành động

## Mục tiêu

Sau bài này, bạn có thể thêm link dẫn đến một hành động trong `EntityModel`, tạo link dựa trên mapping của controller, chỉ công bố hành động khi trạng thái tài nguyên cho phép, phân biệt link hành động thông thường với affordance mô tả HTTP method và dữ liệu đầu vào, đồng thời kiểm thử các link đó trong response hypermedia.

## 1. Vì sao tài nguyên cần link đến hành động?

Giả sử client đọc một đơn hàng. Response chứa mã đơn và trạng thái `PENDING`. Người dùng có thể hủy đơn hàng khi đơn còn chờ xử lý. Nếu client tự tạo URL `/orders/42/cancel`, nó phải biết trước cấu trúc endpoint và quy tắc nghiệp vụ.

Với Spring HATEOAS, server có thể công bố một link có relation `cancel` trong representation của đơn hàng. Client đọc link đó để khám phá đích của hành động. Khi đơn đã giao hoặc đã hủy, server có thể bỏ link này khỏi response.

Ví dụ response HAL:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "cancel": {
      "href": "/orders/42/cancellations"
    }
  }
}
```

Link `self` trỏ đến tài nguyên đơn hàng. Link `cancel` chỉ ra đích liên quan đến hành động hủy. Việc công bố link theo trạng thái giúp client điều hướng theo khả năng mà server hiện hỗ trợ.

## 2. Link hành động trong EntityModel

`EntityModel<T>` bao một đối tượng nội dung và các liên kết. Ta có thể tạo model rồi thêm link bằng `add(...)`, hoặc truyền các link ngay khi gọi `EntityModel.of(...)`.

Ví dụ đơn giản:

```java
EntityModel<Order> model = EntityModel.of(
        order,
        linkTo(methodOn(OrderController.class)
                .getOrder(order.getId())).withSelfRel(),
        linkTo(methodOn(OrderController.class)
                .cancelOrder(order.getId(), null)).withRel("cancel")
);
```

Trong ví dụ này:

- `EntityModel.of(order, ...)` giữ dữ liệu đơn hàng trong representation.
- `withSelfRel()` đánh dấu liên kết đến chính tài nguyên.
- `withRel("cancel")` đặt relation nghiệp vụ cho link đến endpoint hủy.
- `methodOn(...)` cho Spring HATEOAS biết phương thức controller cần tham chiếu để suy ra URL theo mapping.

`null` ở lời gọi `cancelOrder` là giá trị giữ chỗ khi phương thức có tham số request body. `methodOn` dùng chữ ký phương thức để dựng liên kết; lời gọi này không gửi request và không thực thi nghiệp vụ hủy đơn.

Có thể viết theo cách từng bước nếu muốn điều kiện hóa việc thêm link:

```java
EntityModel<Order> model = EntityModel.of(order);

model.add(linkTo(methodOn(OrderController.class)
        .getOrder(order.getId())).withSelfRel());

if (order.canBeCancelled()) {
    model.add(linkTo(methodOn(OrderController.class)
            .cancelOrder(order.getId(), null)).withRel("cancel"));
}

return model;
```

Cách thứ hai hữu ích khi tập hợp link phụ thuộc vào trạng thái, quyền hoặc dữ liệu của tài nguyên.

## 3. Khai báo endpoint hành động trong controller

Một hành động thay đổi trạng thái thường được biểu diễn bằng một endpoint HTTP có method phù hợp. Ví dụ, hủy đơn hàng có thể dùng `POST` đến tài nguyên con biểu thị yêu cầu hủy:

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

    @PostMapping("/{id}/cancellations")
    public EntityModel<Order> cancelOrder(
            @PathVariable UUID id,
            @RequestBody CancellationRequest request) {
        Order cancelled = orderService.cancel(id, request.reason());
        return assembler.toModel(cancelled);
    }
}
```

DTO đầu vào có thể được khai báo riêng:

```java
public record CancellationRequest(String reason) {
}
```

Ví dụ giả định service thực hiện đầy đủ việc xác thực trạng thái và quy tắc hủy. Controller chỉ nhận request, gọi service và trả representation mới.

Tên relation `cancel` nên mô tả ý nghĩa nghiệp vụ, còn HTTP method và URL do mapping của controller quyết định. Không cần đặt tên relation trùng với tên phương thức Java; điều quan trọng là relation ổn định và có ý nghĩa đối với client.

## 4. Tạo link hành động trong assembler

Nên tập trung quy tắc tạo representation vào một assembler khi nhiều endpoint cần trả cùng kiểu tài nguyên. Assembler có thể thêm link hành động dựa trên trạng thái đơn hàng:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel();

        EntityModel<Order> model = EntityModel.of(order, self);

        if (order.canBeCancelled()) {
            Link cancel = linkTo(methodOn(OrderController.class)
                    .cancelOrder(order.getId(), null))
                    .withRel("cancel");

            model.add(cancel);
        }

        return model;
    }
}
```

Các import Spring HATEOAS liên quan trong assembler:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Luồng xử lý:

1. Tạo link `self` từ phương thức đọc đơn hàng.
2. Tạo `EntityModel` chứa đơn hàng và link `self`.
3. Kiểm tra điều kiện nghiệp vụ `canBeCancelled()`.
4. Nếu có thể hủy, tạo link đến phương thức `cancelOrder` và gắn relation `cancel`.
5. Trả model cho controller để framework tuần tự hóa thành response.

Nếu đơn hàng không thể hủy, response vẫn chứa dữ liệu và link `self`, nhưng không có link `cancel`. Client có thể dựa vào sự hiện diện của relation để quyết định có hiển thị thao tác hủy hay không.

Không nên chỉ dựa vào trạng thái entity nếu quyền người dùng cũng ảnh hưởng đến hành động. Khi đó, assembler cần nhận kết quả kiểm tra quyền từ service hoặc một thành phần authorization phù hợp. Server vẫn phải kiểm tra lại quyền và trạng thái trong endpoint hủy vì client có thể gửi request trực tiếp hoặc sử dụng response cũ.

## 5. Link điều hướng và affordance mô tả hành động

Một link HAL thông thường có `href` và relation. Nó cho client biết đích ở đâu và liên kết có ý nghĩa gì. Tuy nhiên, bản thân link HAL thông thường không mô tả đầy đủ HTTP method, content type hoặc cấu trúc dữ liệu đầu vào.

Ví dụ:

```json
{
  "_links": {
    "cancel": {
      "href": "/orders/42/cancellations"
    }
  }
}
```

Client biết đích của relation `cancel`, nhưng nếu không có quy ước hoặc metadata bổ sung thì client không thể suy ra chắc chắn request cần dùng `POST`, `DELETE` hay payload nào.

Spring HATEOAS cung cấp affordance để mô tả tương tác gắn với link. Với HAL-FORMS, metadata này có thể được biểu diễn thành template để client biết method và các trường đầu vào.

Ví dụ xây dựng affordance hủy đơn trên link `self`:

```java
Link self = linkTo(methodOn(OrderController.class)
        .getOrder(order.getId()))
        .withSelfRel();

Link orderWithCancelAffordance = Affordances.of(self)
        .afford(methodOn(OrderController.class)
                .cancelOrder(order.getId(), null))
        .withName("cancel")
        .withInput(CancellationRequest.class)
        .toLink();

return EntityModel.of(order, orderWithCancelAffordance);
```

Các phần chính:

- `Affordances.of(self)` bắt đầu từ link của tài nguyên hiện tại.
- `afford(methodOn(...))` tham chiếu phương thức controller mô tả hành động.
- `withName("cancel")` đặt tên template hành động.
- `withInput(CancellationRequest.class)` cung cấp kiểu dữ liệu đầu vào.
- `toLink()` tạo link mang affordance để đưa vào representation.

Trong ví dụ này, affordance được gắn vào link `self` của tài nguyên. Khi tuần tự hóa bằng HAL-FORMS, tên `cancel` được dùng để nhận diện template hành động. Đây là cách mô tả tương tác phong phú hơn link HAL đơn thuần.

## 6. HAL và HAL-FORMS trong response

Với HAL, link hành động thường xuất hiện trong `_links`:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "cancel": {
      "href": "/orders/42/cancellations"
    }
  }
}
```

Với HAL-FORMS, affordance có thể được tuần tự hóa thành template trong `_templates`. Ví dụ minh họa:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
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

Đây là cấu trúc minh họa; các property thực tế phụ thuộc DTO, metadata và cấu hình serialization. Client có thể yêu cầu HAL-FORMS qua header:

```http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
```

Controller có thể khai báo media type tương ứng:

```java
@GetMapping(
    value = "/{id}",
    produces = MediaTypes.HAL_FORMS_JSON_VALUE
)
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Nếu API hỗ trợ cả HAL và HAL-FORMS, cần cấu hình và kiểm thử content negotiation cho các media type tương ứng. Không nên giả định client yêu cầu HAL sẽ nhận được đầy đủ template của HAL-FORMS.

## 7. Công bố link theo trạng thái tài nguyên

Link hành động là một phần của representation tại thời điểm response được tạo. Nó nên phản ánh trạng thái nghiệp vụ và quyền của người dùng lúc đó.

Ví dụ với đơn hàng:

| Trạng thái | Link có thể công bố |
|---|---|
| `PENDING` | `self`, `cancel`, `payment` |
| `PAID` | `self`, `shipment` |
| `SHIPPED` | `self`, `tracking` |
| `CANCELLED` | `self` |

Bảng trên chỉ minh họa một quy trình đơn hàng. Trạng thái và hành động thực tế phải theo quy tắc nghiệp vụ của ứng dụng.

Một số nguyên tắc:

- Chỉ công bố hành động có thể thực hiện trong ngữ cảnh hiện tại.
- Giữ relation ổn định để client có thể dựa vào nó qua các lần cập nhật API.
- Không công bố link chỉ vì endpoint tồn tại; phải xét trạng thái tài nguyên và quyền truy cập.
- Luôn xác thực, phân quyền và kiểm tra điều kiện nghiệp vụ ở endpoint đích.

Việc bỏ link `cancel` khỏi response giúp client biết hành động không khả dụng theo representation hiện tại. Đây là hướng dẫn điều hướng, không phải cơ chế bảo mật. Server phải từ chối request hủy nếu trạng thái đã thay đổi hoặc người gọi không có quyền.

## 8. Kiểm thử link hành động

Kiểm thử MockMvc nên xác nhận link hành động xuất hiện khi điều kiện nghiệp vụ đúng:

```java
mockMvc.perform(get("/orders/{id}", pendingOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với đơn hàng không thể hủy, link `cancel` không nên xuất hiện:

```java
mockMvc.perform(get("/orders/{id}", shippedOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Cần kiểm tra cả endpoint thực hiện hành động. Ví dụ, request hủy với dữ liệu hợp lệ phải cập nhật trạng thái theo nghiệp vụ; request từ người dùng không có quyền hoặc trên đơn đã giao phải bị từ chối theo chính sách của ứng dụng.

Nếu dùng HAL-FORMS, hãy kiểm thử template và metadata:

```java
mockMvc.perform(get("/orders/{id}", pendingOrderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._templates.cancel.method").value("POST"));
```

Các kiểm thử này giúp phát hiện trường hợp assembler quên công bố link, công bố sai trạng thái hoặc thay đổi relation ngoài dự kiến. Chúng cũng xác nhận client nhận được định dạng hypermedia mà API cam kết.

## 9. Những lỗi thiết kế thường gặp

**Tự ghép URL trong assembler.** Chuỗi như `"/orders/" + id + "/cancellations"` dễ lệch mapping khi endpoint thay đổi. Hãy tham chiếu phương thức controller bằng `linkTo(methodOn(...))`.

**Nhầm link với lệnh thực thi.** Tạo link không làm hành động xảy ra. Client phải gửi HTTP request đến đích; server mới thực hiện và kiểm tra nghiệp vụ.

**Cho rằng relation tự mô tả HTTP method.** Tên `cancel` cho biết ý nghĩa nghiệp vụ, nhưng link HAL cơ bản không tự mô tả đầy đủ method và payload. Dùng affordance và định dạng như HAL-FORMS khi client cần metadata tương tác.

**Công bố mọi hành động cho mọi trạng thái.** Client sẽ hiển thị thao tác không còn hợp lệ. Hãy tạo link theo trạng thái và quyền tại thời điểm xây representation.

**Chỉ ẩn link để bảo vệ endpoint.** Client có thể tự gửi request. Kiểm tra bảo mật và quy tắc nghiệp vụ vẫn phải diễn ra ở server.

## Kết luận

`EntityModel<T>` cho phép gắn link hành động vào representation của một tài nguyên. Dùng `linkTo(methodOn(...))` để tạo đích theo mapping controller và `withRel("cancel")` để đặt relation có ý nghĩa nghiệp vụ. Khi client cần biết thêm HTTP method hoặc dữ liệu đầu vào, hãy mô tả affordance và cung cấp media type phù hợp như HAL-FORMS. Công bố link theo trạng thái và quyền truy cập, đồng thời kiểm thử cả response hypermedia lẫn endpoint thực thi hành động.

