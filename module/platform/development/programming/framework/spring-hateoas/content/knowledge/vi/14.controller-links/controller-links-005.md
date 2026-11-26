# Link cho PUT

Một ứng dụng quản lý đơn hàng cho phép người dùng mở chi tiết đơn hàng và thay thế thông tin giao hàng. API có thể cung cấp `GET /api/orders/{id}` để đọc đơn hàng và `PUT /api/orders/{id}` để cập nhật representation của đơn hàng. Khi trả về chi tiết, server có thể mô tả thao tác cập nhật bằng affordance gắn với link. Client biết resource nào có thể được cập nhật và, nếu media type hỗ trợ, biết method cùng các trường đầu vào cần gửi.

Spring HATEOAS xây dựng liên kết theo mapping của controller bằng `linkTo(methodOn(...))`. Để mô tả thao tác PUT, có thể dùng `afford(methodOn(...))` rồi gắn affordance vào link bằng `andAffordance(...)`. Link thông thường cho biết đích; affordance bổ sung mô tả cách tương tác. HAL cơ bản biểu diễn link trong `_links`, còn HAL-FORMS có thể biểu diễn thêm template của thao tác trong `_templates`.

## PUT dùng để làm gì?

HTTP `PUT` yêu cầu server tạo hoặc thay thế trạng thái của resource tại URI đích bằng representation được gửi trong request, theo hợp đồng của endpoint. Trong API cập nhật một đơn hàng đã tồn tại, client gửi toàn bộ các trường mà hợp đồng yêu cầu để thay thế representation hiện tại.

PUT có ngữ nghĩa **idempotent**: gửi cùng một request một hoặc nhiều lần phải dẫn đến cùng trạng thái resource như gửi một lần. Điều này không có nghĩa mọi chi tiết vận hành phải giống hệt nhau; server vẫn có thể ghi log hoặc cập nhật metadata kiểm toán, nhưng trạng thái nghiệp vụ được PUT định nghĩa phải ổn định khi lặp lại request.

Nếu client chỉ gửi một vài trường để cập nhật từng phần, hãy cân nhắc `PATCH` với định dạng patch được công bố rõ ràng. Không nên dùng PUT với body một phần rồi âm thầm giữ lại các trường không được gửi, trừ khi hợp đồng API định nghĩa rõ hành vi đó.

Kết quả của PUT thường là:

| Status | Trường hợp thường gặp |
| --- | --- |
| `200 OK` | Server cập nhật resource và trả representation mới. |
| `204 No Content` | Server cập nhật thành công nhưng không trả body. |
| `201 Created` | PUT tạo resource mới tại URI đích và trả kết quả phù hợp. |
| `400 Bad Request` hoặc `422 Unprocessable Content` | Body không hợp lệ theo hợp đồng hoặc quy tắc nghiệp vụ. |
| `404 Not Found` | Resource đích không tồn tại và API không hỗ trợ tạo mới qua PUT. |
| `409 Conflict` hoặc `412 Precondition Failed` | Có xung đột trạng thái hoặc điều kiện cập nhật như `If-Match` không thỏa mãn. |

## Link đến endpoint PUT

Giả sử controller có endpoint đọc và thay thế đơn hàng:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return EntityModel.of(orders.get(id));
    }

    @PutMapping("/{id}")
    OrderView replace(
            @PathVariable UUID id,
            @Valid @RequestBody ReplaceOrderRequest request) {
        return orders.replace(id, request);
    }
}
```

Phương thức `replace(...)` được ánh xạ bằng `@PutMapping`. Để tạo link trỏ đến endpoint này, dùng `methodOn` với đúng chữ ký phương thức:

```java
Link update = linkTo(methodOn(OrderController.class)
    .replace(orderId, null))
    .withRel("edit");
```

`methodOn(...)` tạo proxy để ghi nhận phương thức controller và các đối số. Giá trị `null` ở vị trí body chỉ là placeholder khi tham chiếu phương thức để xây dựng URI và metadata; nó không gọi `replace(...)`, không gửi request PUT và không thực hiện cập nhật dữ liệu. Path variable `orderId` được dùng để tạo phần `/{id}` của URI. Request body không trở thành một phần của URI.

Trong code thật, hãy giữ chữ ký controller rõ ràng và dùng cùng kiểu request DTO mà endpoint nhận. Nếu phương thức có nhiều tham số, thứ tự đối số trong `methodOn` phải khớp chữ ký Java.

## Mô tả thao tác PUT bằng affordance

Một link với `rel="edit"` và `href` chỉ cho biết đích chỉnh sửa. Bản thân link HAL cơ bản không nói client phải dùng PUT hay PATCH, cũng không mô tả các trường trong request body. Spring HATEOAS cho phép gắn affordance để mô tả thao tác controller tương ứng:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link edit = linkTo(methodOn(OrderController.class).one(orderId))
    .withSelfRel()
    .andAffordance(afford(
        methodOn(OrderController.class).replace(orderId, null)));
```

Ở đây link `self` trỏ đến representation đơn hàng. Affordance được tạo từ phương thức `replace(...)`, vì vậy Spring HATEOAS có thể đọc metadata mapping, HTTP method PUT và thông tin tham số của phương thức. Client dùng media type có hỗ trợ affordance để khám phá cách thực hiện thao tác.

Có thể gắn affordance vào một link `edit` riêng thay vì link `self`, tùy cách tổ chức hợp đồng:

```java
Link edit = linkTo(methodOn(OrderController.class).replace(orderId, null))
    .withRel("edit")
    .andAffordance(afford(
        methodOn(OrderController.class).replace(orderId, null)));
```

Trong cách này, `self` vẫn đại diện cho resource hiện tại, còn `edit` là quan hệ được API dùng để chỉ thao tác chỉnh sửa. Hãy chọn một quy ước nhất quán và tài liệu hóa relation để client hiểu đúng.

## Ví dụ đầy đủ với EntityModel

Ví dụ sau trả về đơn hàng cùng self link và affordance PUT. Request DTO dùng các trường mà endpoint cho phép thay thế:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderView(
    UUID id,
    String status,
    String shippingAddress,
    BigDecimal total
) {
}
```

```java
import jakarta.validation.constraints.NotBlank;

public record ReplaceOrderRequest(
    @NotBlank String shippingAddress
) {
}
```

Controller:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        OrderView order = orders.get(id);

        Link self = linkTo(methodOn(OrderController.class).one(id))
            .withSelfRel()
            .andAffordance(afford(
                methodOn(OrderController.class).replace(id, null)));

        return EntityModel.of(order, self);
    }

    @PutMapping("/{id}")
    OrderView replace(
            @PathVariable UUID id,
            @Valid @RequestBody ReplaceOrderRequest request) {
        return orders.replace(id, request);
    }
}
```

Các kiểu `OrderService`, `OrderView` và `ReplaceOrderRequest` được giả định là những thành phần của ứng dụng. Trong dự án thực tế, thêm import cho DTO và service theo package tương ứng. Ví dụ rút gọn cho thấy điểm quan trọng: link self được tạo từ GET, affordance được suy ra từ PUT, còn PUT thật sự chỉ chạy khi client gửi request đến endpoint.

Nếu đơn hàng chỉ được phép cập nhật khi đang ở trạng thái `PENDING`, chỉ thêm affordance khi trạng thái và quyền hiện tại cho phép:

```java
Link self = linkTo(methodOn(OrderController.class).one(id)).withSelfRel();

if ("PENDING".equals(order.status()) && currentUser.canEdit(order)) {
    self = self.andAffordance(afford(
        methodOn(OrderController.class).replace(id, null)));
}
```

`currentUser.canEdit(order)` chỉ là biểu thức minh họa cho chính sách phân quyền của ứng dụng. Endpoint PUT vẫn phải kiểm tra quyền và trạng thái khi request thực sự đến. Việc ẩn affordance không phải là biện pháp bảo mật.

## HAL và HAL-FORMS biểu diễn PUT khác nhau

### HAL cơ bản

HAL (`application/hal+json`) biểu diễn link trong `_links`. Nếu server gắn affordance nhưng client chỉ nhận HAL cơ bản, client vẫn có thể thấy link `self` hoặc `edit` với `href`. HAL cơ bản không cung cấp cấu trúc form tiêu chuẩn để mô tả đầy đủ method PUT và các trường body.

Ví dụ HAL rút gọn:

```json
{
  "id": "ord-1042",
  "status": "PENDING",
  "shippingAddress": "12 Nguyen Hue, District 1",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    }
  }
}
```

Client muốn gửi PUT trong trường hợp chỉ có HAL cần biết hợp đồng endpoint từ tài liệu hoặc một cơ chế khác. Chỉ nhìn `href` là chưa đủ để suy ra method và body.

### HAL-FORMS

HAL-FORMS (`application/prs.hal-forms+json`) có thể biểu diễn affordance dưới dạng template trong `_templates`. Template mô tả method, target và các property đầu vào mà client có thể gửi.

Ví dụ minh họa cho thao tác thay thế đơn hàng:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    }
  },
  "_templates": {
    "default": {
      "method": "put",
      "target": "https://api.example.com/api/orders/ord-1042",
      "properties": [
        {
          "name": "shippingAddress",
          "required": true
        }
      ]
    }
  }
}
```

Tên template và danh sách property thực tế phụ thuộc relation, cấu hình hypermedia và metadata mà Spring HATEOAS suy ra từ controller/request DTO. JSON trên minh họa cấu trúc và ý nghĩa, không phải cam kết mọi cấu hình đều sinh chính xác cùng tên template.

Client yêu cầu media type HAL-FORMS bằng header:

```http
GET /api/orders/ord-1042
Accept: application/prs.hal-forms+json
```

Ứng dụng Spring Boot dùng starter HATEOAS thường có cấu hình hypermedia tự động. Với cấu hình Spring MVC thủ công, có thể bật HAL-FORMS như sau:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
```

Nếu ứng dụng cần hỗ trợ nhiều media type, hãy cấu hình và kiểm thử content negotiation theo phiên bản Spring HATEOAS đang sử dụng.

## Tạo link PUT trong RepresentationModelAssembler

Khi nhiều endpoint cần biểu diễn đơn hàng giống nhau, có thể đặt logic tạo link và affordance trong assembler:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {
        Link self = linkTo(methodOn(OrderController.class).one(order.id()))
            .withSelfRel();

        if ("PENDING".equals(order.status())) {
            self = self.andAffordance(afford(
                methodOn(OrderController.class).replace(order.id(), null)));
        }

        return EntityModel.of(order, self);
    }
}
```

Assembler trên thêm affordance PUT khi trạng thái là `PENDING`. Nếu quyền người dùng ảnh hưởng đến khả năng cập nhật, cần đưa ngữ cảnh phân quyền vào cách xây representation hoặc xử lý tại controller/service phù hợp. Tránh để assembler giả định mọi người dùng đều có cùng quyền.

## PUT, ETag và cập nhật đồng thời

Idempotency không tự giải quyết xung đột khi nhiều client cùng sửa một resource. Một client có thể đọc phiên bản cũ, trong khi client khác đã cập nhật trước. Nếu API cần ngăn ghi đè thay đổi mới, có thể dùng validator như `ETag` cùng điều kiện `If-Match`.

Luồng điển hình:

1. Client GET đơn hàng và nhận `ETag: "v7"`.
2. Client gửi PUT với `If-Match: "v7"`.
3. Server chỉ cập nhật nếu phiên bản hiện tại vẫn khớp.
4. Nếu resource đã đổi, server trả `412 Precondition Failed` để client tải lại và xử lý xung đột.

Affordance có thể mô tả thao tác PUT, nhưng không thay thế cơ chế điều kiện HTTP. Client vẫn cần gửi header điều kiện nếu hợp đồng yêu cầu. Tương tự, việc gắn affordance không tự tạo ra ETag hay xử lý optimistic locking; đó là trách nhiệm của controller, service và tầng persistence.

## Kiểm thử link và affordance PUT

Kiểm thử nên xác nhận cả relation, URI đích và metadata thao tác theo media type được công bố.

### Kiểm tra HAL cơ bản

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Test này xác nhận link đến resource có mặt. Nó không chứng minh client có thể suy ra method PUT từ HAL cơ bản.

### Kiểm tra HAL-FORMS template

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates.default.method").value("put"))
    .andExpect(jsonPath("$._templates.default.target")
        .value(org.hamcrest.Matchers.endsWith("/api/orders/" + orderId)));
```

JSON path `default` là tên template minh họa; nếu cấu hình relation tạo tên template khác, hãy điều chỉnh test theo hợp đồng thực tế. Có thể kiểm tra thêm property `shippingAddress` để xác nhận body schema mà client được mô tả.

### Kiểm tra PUT thật sự

Ngoài link, cần kiểm thử endpoint PUT độc lập:

```java
mockMvc.perform(put("/api/orders/{id}", orderId)
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"shippingAddress":"12 Nguyen Hue, District 1"}
            """))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.shippingAddress")
        .value("12 Nguyen Hue, District 1"));
```

Để kiểm tra idempotency, gửi cùng một request PUT hai lần và xác nhận trạng thái resource cuối cùng không thay đổi sau lần gửi thứ hai. Nếu API dùng `If-Match`, bổ sung kiểm thử cập nhật thành công với ETag hiện tại và thất bại với ETag cũ.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ trả link có `href` rồi kỳ vọng client biết phải dùng PUT | HAL cơ bản không mô tả method và body. | Dùng affordance với media type hỗ trợ như HAL-FORMS hoặc công bố hợp đồng endpoint khác. |
| Dùng `methodOn` như lời gọi controller thật | Có thể hiểu nhầm body `null` sẽ được gửi hoặc nghiệp vụ sẽ chạy. | Xem `methodOn` là proxy ghi nhận invocation để tạo metadata. |
| Dùng PUT cho cập nhật một phần mà không công bố rõ | Client có thể vô tình xóa hoặc giữ sai các trường. | Định nghĩa PUT là thay thế theo hợp đồng hoặc dùng PATCH cho cập nhật một phần. |
| Thêm affordance PUT cho mọi trạng thái | Client nhìn thấy hành động không hợp lệ. | Chỉ phát affordance khi trạng thái và quyền cho phép; endpoint vẫn phải kiểm tra lại. |
| Cho rằng affordance là cơ chế bảo mật | Người gọi vẫn có thể gọi trực tiếp endpoint PUT. | Xác thực, phân quyền và kiểm tra invariant ở server. |
| Kiểm thử chỉ có self link | Không phát hiện sai method hoặc thiếu property của template. | Kiểm tra HAL-FORMS method, target và property. |
| Bỏ qua cập nhật đồng thời | PUT có thể ghi đè thay đổi của client khác. | Dùng ETag/If-Match hoặc cơ chế versioning phù hợp. |

## Ghi nhớ

- PUT thay thế trạng thái resource theo hợp đồng và có ngữ nghĩa idempotent.
- Dùng `linkTo(methodOn(...))` để tạo URI từ mapping của controller.
- Dùng `afford(methodOn(...))` và `andAffordance(...)` để mô tả thao tác PUT gắn với link.
- `methodOn` chỉ ghi nhận phương thức và đối số; body `null` trong biểu thức tạo affordance không gửi request và không thực thi controller.
- HAL cơ bản biểu diễn link; HAL-FORMS có thể mô tả method PUT, target và property trong `_templates`.
- Chỉ phát affordance khi trạng thái và quyền cho phép, nhưng luôn kiểm tra lại ở endpoint.
- Kiểm thử cả template PUT lẫn endpoint thực tế, idempotency và điều kiện cập nhật đồng thời nếu có.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring HATEOAS API – Affordance](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Affordance.html)
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/)
- [RFC 9110 – HTTP Semantics, PUT](https://www.rfc-editor.org/rfc/rfc9110#section-9.3.4)
