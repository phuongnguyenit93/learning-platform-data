# Template method

## Mục tiêu

Sau bài này, bạn có thể giải thích thuộc tính `method` trong template HAL-FORMS, xác định cách Spring HATEOAS suy ra HTTP method từ mapping của controller, gắn nhiều affordance vào một link, khai báo method tường minh khi cần và kiểm thử method được tuần tự hóa đúng trong `_templates`.

## 1. Template method có ý nghĩa gì?

HAL-FORMS mở rộng HAL bằng cách mô tả những biểu mẫu hoặc tương tác mà client có thể thực hiện trên tài nguyên. Một template nằm trong thuộc tính `_templates` và có thể chứa tên, method, content type, target cùng danh sách thuộc tính đầu vào.

Ví dụ response:

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
    "update": {
      "method": "put",
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

Thuộc tính `method` chỉ HTTP method mà client phải dùng khi gửi dữ liệu theo template. Trong ví dụ, client gửi request `PUT` đến target của template `update`.

Cần phân biệt ba thông tin:

- `href` trong `_links.self` là URI của tài nguyên hiện tại.
- `method` trong template mô tả HTTP method dùng khi submit tương tác.
- `properties` mô tả các trường dữ liệu client có thể hoặc cần gửi.

Ví dụ, client có thể tải tài nguyên bằng `GET /orders/42`, sau đó dùng template `update` để gửi `PUT /orders/42`. Method của request đọc representation và method của template là hai việc khác nhau.

## 2. Spring HATEOAS lấy method từ đâu?

Spring HATEOAS có thể suy ra affordance từ phương thức controller được tham chiếu. Khi dùng `afford(methodOn(...))`, framework phân tích mapping của phương thức đó, bao gồm HTTP method và metadata của request/response.

Các annotation mapping thường xác định method như sau:

| Annotation | HTTP method được mô tả |
|---|---|
| `@GetMapping` | `GET` |
| `@PostMapping` | `POST` |
| `@PutMapping` | `PUT` |
| `@PatchMapping` | `PATCH` |
| `@DeleteMapping` | `DELETE` |

Ví dụ controller:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderView> getOrder(@PathVariable UUID id) {
        return EntityModel.of(orderService.getView(id));
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public EntityModel<OrderView> updateOrder(
            @PathVariable UUID id,
            @Valid @RequestBody OrderUpdate input) {
        return EntityModel.of(orderService.update(id, input));
    }

    @PatchMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public EntityModel<OrderView> partiallyUpdateOrder(
            @PathVariable UUID id,
            @Valid @RequestBody OrderPatch input) {
        return EntityModel.of(orderService.partiallyUpdate(id, input));
    }
}
```

Khi affordance trỏ đến `updateOrder(...)`, Spring HATEOAS đọc `@PutMapping` và tạo metadata method là `put`. Khi affordance trỏ đến `partiallyUpdateOrder(...)`, method được suy ra là `patch`.

Giá trị trong JSON HAL-FORMS được tuần tự hóa bằng chữ thường, ví dụ `"put"` và `"patch"`. Đây là cách biểu diễn của template; HTTP method mà client gửi vẫn là method tương ứng theo HTTP.

## 3. Gắn method vào self link bằng affordance

Một tài nguyên thường có self link được tạo từ endpoint GET. Ta có thể gắn các affordance trỏ đến phương thức cập nhật vào chính link đó:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

public EntityModel<OrderView> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class)
            .getOrder(order.getId()))
            .withSelfRel();

    Link actions = self
            .andAffordance(afford(methodOn(OrderController.class)
                    .updateOrder(order.getId(), null)))
            .andAffordance(afford(methodOn(OrderController.class)
                    .partiallyUpdateOrder(order.getId(), null)));

    return EntityModel.of(order.toView(), actions);
}
```

Trong ví dụ:

1. `self` trỏ đến `GET /orders/{id}`.
2. Affordance thứ nhất tham chiếu phương thức có `@PutMapping`.
3. Affordance thứ hai tham chiếu phương thức có `@PatchMapping`.
4. Cả hai thao tác được gắn với cùng một link tài nguyên.

Đối số `null` là giá trị giữ chỗ cho request body trong lời gọi proxy `methodOn(...)`. Nó giúp Spring HATEOAS đọc chữ ký phương thức; không gửi request và không gọi service cập nhật.

Khi client yêu cầu HAL-FORMS, response có thể chứa hai template:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "updateOrder": {
      "method": "put"
    },
    "partiallyUpdateOrder": {
      "method": "patch"
    }
  }
}
```

Nếu chỉ có một template, HAL-FORMS dùng tên `default`. Khi có nhiều affordance, tên template có thể được suy ra từ phương thức được tham chiếu hoặc được cấu hình tường minh bằng API xây dựng affordance. Không nên để client phụ thuộc vào tên tự suy ra nếu hợp đồng yêu cầu tên ổn định; hãy đặt tên có chủ đích và kiểm thử nó.

## 4. Đặt tên template và khai báo method tường minh

Khi cần kiểm soát tên template và method độc lập với tên phương thức Java, Spring HATEOAS cung cấp API `Affordances` để tạo affordance thủ công.

```java
import org.springframework.http.HttpMethod;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.hateoas.Link;

Link self = linkTo(methodOn(OrderController.class)
        .getOrder(orderId))
        .withSelfRel();

Link actions = Affordances.of(self)
        .afford(HttpMethod.PUT)
        .withInput(OrderUpdate.class)
        .withOutput(OrderView.class)
        .withName("update")
        .andAfford(HttpMethod.PATCH)
        .withInput(OrderPatch.class)
        .withOutput(OrderView.class)
        .withName("partialUpdate")
        .toLink();
```

Ở cách này, method được chỉ định trực tiếp bằng `HttpMethod.PUT` và `HttpMethod.PATCH`. `withName(...)` đặt tên template công khai; `withInput(...)` khai báo kiểu payload đầu vào; `withOutput(...)` khai báo kiểu representation đầu ra.

Dùng cách xây dựng thủ công khi affordance không thể suy ra trực tiếp từ controller method, hoặc khi cần kiểm soát metadata. Khi dùng controller mapping, ưu tiên tham chiếu phương thức thật để method và target phản ánh đúng endpoint đang được triển khai.

Nếu khai báo method thủ công, phải bảo đảm endpoint thực tế chấp nhận method đó. Metadata sai có thể khiến client gửi request không được server hỗ trợ.

## 5. Method và target là hai thuộc tính khác nhau

Template HAL-FORMS có thể chứa cả `method` và `target`:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "update": {
      "method": "put",
      "properties": [
        {
          "name": "note"
        }
      ]
    },
    "cancel": {
      "method": "post",
      "target": "/orders/42/cancellations",
      "properties": [
        {
          "name": "reason"
        }
      ]
    }
  }
}
```

- `method` cho biết cách gửi request.
- `target` cho biết URI đích của template.
- Nếu target của affordance giống URI của link mà nó được gắn vào, HAL-FORMS không cần lặp lại `target`.
- Nếu target khác link gốc, Spring HATEOAS có thể đưa `target` vào template.

Trong ví dụ, template `update` thao tác trên chính `/orders/42`, nên target có thể được suy ra từ self link. Template `cancel` gửi request đến tài nguyên con `/orders/42/cancellations`, nên cần target riêng.

Đừng nhầm việc thay đổi method với thay đổi target. Hai template có thể cùng target nhưng dùng method khác nhau, chẳng hạn `PUT` và `PATCH`; cũng có thể dùng cùng method nhưng target khác nhau.

## 6. Method kết hợp với contentType và input properties

Thuộc tính `method` không mô tả định dạng body. HAL-FORMS dùng `contentType` để mô tả media type mà server mong đợi khi nhận request. Spring HATEOAS chỉ đưa thuộc tính này vào template khi mapping controller khai báo `consumes` hoặc media type được cấu hình tường minh cho affordance.

Ví dụ:

```java
@PutMapping(
    value = "/{id}",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public EntityModel<OrderView> updateOrder(
        @PathVariable UUID id,
        @Valid @RequestBody OrderUpdate input) {
    return EntityModel.of(orderService.update(id, input));
}
```

Template tương ứng có thể chứa:

```json
{
  "method": "put",
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
```

Các property được suy ra từ kiểu input được khai báo cho affordance. Metadata validation cũng có thể đóng góp thông tin:

- `@NotNull` có thể làm property được đánh dấu `required: true`.
- `@Pattern` có thể cung cấp `regex`.
- Các constraint như `@Min`, `@Max`, `@Size` có thể cung cấp giới hạn tương ứng.
- Với template dùng `PATCH`, Spring HATEOAS tự xem các property là không bắt buộc theo semantics cập nhật một phần.

Các metadata này hỗ trợ client tạo form phù hợp, nhưng không thay thế validation phía server. Endpoint vẫn phải kiểm tra payload thực tế bằng Bean Validation và quy tắc nghiệp vụ.

## 7. Method của GET template và các thao tác ghi

HAL-FORMS không chỉ mô tả thao tác ghi. Template có thể dùng `GET` cho truy vấn hoặc tìm kiếm với các tham số, còn `POST`, `PUT`, `PATCH` và `DELETE` thường mô tả các thao tác thay đổi trạng thái.

Ví dụ một link collection có thể mang affordance tìm kiếm:

```java
Link collection = linkTo(methodOn(OrderController.class)
        .getOrders(null, null))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class)
                .searchOrders(null, null)));
```

Nếu phương thức `searchOrders` được ánh xạ bằng `@GetMapping`, template tìm kiếm sẽ mô tả method `get`. Các tham số truy vấn có thể được biểu diễn thành template properties hoặc query parameters tùy chữ ký và metadata được cung cấp.

Điều quan trọng là client không nên tự suy ra method chỉ từ relation. Relation `search` nói về mục đích của liên kết; thuộc tính `method` mới mô tả HTTP method cần dùng cho template.

## 8. Bật HAL-FORMS và thương lượng nội dung

HAL-FORMS dùng media type:

```text
application/prs.hal-forms+json
```

Client yêu cầu định dạng này bằng header:

```http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
```

Với ứng dụng Spring Boot dùng HATEOAS starter, auto-configuration thường đăng ký hạ tầng hypermedia cần thiết. Khi cấu hình Spring thủ công, có thể bật HAL-FORMS bằng:

```java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
public class HypermediaConfiguration {
}
```

Controller hoặc endpoint cần hỗ trợ media type tương ứng trong content negotiation. Nếu client yêu cầu HAL thông thường bằng `application/hal+json`, đừng kỳ vọng response có các template HAL-FORMS giống như khi yêu cầu đúng media type.

## 9. Kiểm thử method trong template

Kiểm thử MockMvc nên xác nhận response có đúng media type, tên template và HTTP method. Ví dụ với affordance được đặt tên rõ ràng là `update` và `partialUpdate`:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.update.method").value("put"))
    .andExpect(jsonPath("$._templates.partialUpdate.method").value("patch"));
```

Nếu mapping cập nhật khai báo `consumes = "application/json"`, kiểm tra thêm:

```java
.andExpect(jsonPath("$._templates.update.contentType")
        .value("application/json"));
```

Cũng nên kiểm thử các trường hợp:

1. Template cập nhật toàn phần công bố `put`.
2. Template cập nhật một phần công bố `patch`.
3. Template tìm kiếm công bố `get` nếu endpoint được ánh xạ bằng GET.
4. Template hủy công bố đúng method và target của endpoint hủy.
5. Một thay đổi mapping controller làm method trong template được cập nhật đúng.
6. HAL-FORMS chỉ được trả khi client yêu cầu media type phù hợp.
7. Endpoint thực tế chấp nhận method đã công bố và xử lý payload tương ứng.

Kiểm thử response xác nhận metadata; kiểm thử endpoint xác nhận hành động có thể thực thi. Cần cả hai để bảo vệ hợp đồng.

## 10. Lỗi thường gặp

**Nhầm method của template với method tải tài nguyên.** Client có thể dùng GET để tải representation, rồi dùng PUT để submit template cập nhật. Đây là hai request khác nhau.

**Gắn affordance đến nhầm controller method.** Template sẽ công bố sai method hoặc target. Hãy tham chiếu đúng phương thức có mapping tương ứng.

**Đặt method thủ công nhưng endpoint không hỗ trợ.** Client sẽ gửi request bị từ chối. Nếu dùng `Affordances.of(...).afford(HttpMethod...)`, phải kiểm thử method thực tế.

**Cho rằng method quyết định content type.** `method` và `contentType` là metadata riêng. Khai báo `consumes` hoặc cấu hình media type đầu vào khi cần.

**Không phân biệt target với href của link.** Template có thể gửi request đến cùng URI hoặc URI khác. Chỉ có `method` không đủ để xác định target khi target khác link gốc.

**Dùng tên template không ổn định.** Tên tự suy ra có thể phụ thuộc phương thức Java. Nếu client dùng tên template để tìm hành động, hãy đặt tên rõ ràng và kiểm thử.

**Chỉ kiểm tra JSON mà không gọi endpoint.** Method trong template có thể đúng về hình thức nhưng mapping thực tế không hỗ trợ. Kiểm thử cả request thực.

## 11. Nguyên tắc thiết kế

- Dùng controller mapping thật để Spring HATEOAS suy ra HTTP method khi có thể.
- Gắn affordance vào link đại diện cho tài nguyên hoặc collection liên quan.
- Đặt tên template tường minh nếu client cần một định danh ổn định.
- Phân biệt `method`, `target` và `contentType`.
- Khai báo DTO input riêng, chỉ chứa các trường client được phép gửi.
- Dùng validation để cung cấp metadata property và bảo vệ endpoint.
- Công bố template theo trạng thái và quyền hiện tại của tài nguyên.
- Kiểm thử method, target, content type và endpoint thực thi.

## Kết luận

Trong HAL-FORMS, `method` cho biết HTTP method client phải dùng khi submit một template. Spring HATEOAS có thể suy ra giá trị này từ mapping controller được tham chiếu bằng `afford(methodOn(...))`, hoặc cho phép khai báo tường minh qua `Affordances`. Hãy phân biệt method với href, target và content type; giữ tên template ổn định; kiểm thử metadata được tuần tự hóa và xác nhận endpoint thực sự hỗ trợ method đã công bố.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server-side.affordances)
- [Spring HATEOAS Reference – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS Affordances API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/Affordances.html)

