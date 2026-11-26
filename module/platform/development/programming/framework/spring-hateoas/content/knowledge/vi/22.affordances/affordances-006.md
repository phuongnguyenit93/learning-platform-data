# Affordance cho PATCH

Một ứng dụng quản lý đơn hàng cho phép client thay đổi địa chỉ giao hàng mà không phải gửi lại toàn bộ representation đơn hàng. API có thể cung cấp `PATCH /api/orders/{id}` để cập nhật một phần resource. Khi trả về chi tiết đơn hàng, server có thể mô tả thao tác PATCH bằng affordance gắn với link. Client khám phá được endpoint nào hỗ trợ cập nhật, HTTP method cần dùng và, nếu media type hỗ trợ, các trường đầu vào của request.

Spring HATEOAS cho phép xây affordance từ method mapping của controller bằng `afford(methodOn(...))`, sau đó gắn vào link bằng `andAffordance(...)`. Link thông thường cung cấp URI và relation; affordance bổ sung thông tin về cách tương tác với URI đó. Khi dùng HAL-FORMS, thông tin này có thể được serialize thành template trong `_templates`, bao gồm method PATCH và các property của request.

## PATCH dùng để làm gì?

HTTP `PATCH` yêu cầu server áp dụng một tập thay đổi lên resource đích. Khác với PUT thường được dùng để thay thế representation theo hợp đồng, PATCH phù hợp với cập nhật một phần hoặc một thao tác biến đổi được mô tả bởi patch document.

Ví dụ, client chỉ muốn đổi địa chỉ giao hàng của đơn hàng. Thay vì gửi toàn bộ thông tin đơn hàng, client gửi phần thay đổi:

```http
PATCH /api/orders/ord-1042
Content-Type: application/json
Accept: application/hal+json

{
  "shippingAddress": "25 Le Loi, District 1"
}
```

PATCH không tự quy định cấu trúc body. API phải công bố định dạng patch và ý nghĩa của từng trường. Một số định dạng phổ biến:

| Định dạng | Media type | Cách biểu diễn thay đổi |
| --- | --- | --- |
| JSON Merge Patch | `application/merge-patch+json` | Một object JSON mô tả các giá trị cần hợp nhất; giá trị `null` thường biểu thị xóa thuộc tính. |
| JSON Patch | `application/json-patch+json` | Một mảng thao tác như `add`, `remove`, `replace`, `move`, `copy`, `test` trên JSON Pointer path. |
| Patch DTO riêng của API | Thường là `application/json` hoặc media type vendor riêng | Các field và quy tắc absent/null do API định nghĩa. |

Không nên chỉ đổi annotation thành `@PatchMapping` rồi giả định body JSON có ngữ nghĩa chuẩn. Hãy xác định rõ media type, cách hiểu field bị bỏ qua, cách xử lý `null`, validation và tính nguyên tử của thay đổi.

### PATCH có idempotent không?

PATCH không được bảo đảm idempotent theo mặc định. Một patch đặt `shippingAddress` thành một giá trị cố định có thể idempotent nếu áp dụng lặp lại vẫn cho cùng trạng thái. Một patch tăng số lượng thêm một đơn vị sẽ không idempotent nếu được áp dụng nhiều lần.

Server nên áp dụng toàn bộ patch một cách nguyên tử: hoặc toàn bộ thay đổi thành công, hoặc không thay đổi resource. Nếu cần bảo vệ cập nhật đồng thời, có thể kết hợp ETag và `If-Match` để phát hiện client đang sửa trên phiên bản cũ.

## Tạo endpoint PATCH trong controller

Giả sử API cho phép cập nhật một phần một số trường đơn hàng. Patch DTO dưới đây minh họa hợp đồng riêng của ứng dụng:

```java
public record OrderPatchRequest(
    String shippingAddress,
    String deliveryNote
) {
}
```

Controller nhận DTO và chuyển cho service:

```java
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
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

    @PatchMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderView patch(
            @PathVariable UUID id,
            @Valid @RequestBody OrderPatchRequest patch) {
        return orders.patch(id, patch);
    }
}
```

Ví dụ dùng `application/json` vì đây là patch DTO riêng của API. `OrderService.patch(...)` phải thực hiện quy tắc partial update đã công bố. Cụ thể, nếu client bỏ `deliveryNote`, service có thể hiểu là giữ nguyên; nếu client gửi `null`, hợp đồng phải quy định rõ là giữ nguyên hay xóa giá trị. DTO record đơn giản không tự phân biệt mọi trường hợp absent và explicit null sau khi deserialize.

Nếu API cần phân biệt chính xác ba trạng thái “không gửi”, “gửi null” và “gửi giá trị”, hãy dùng một kiểu dữ liệu hoặc parser có khả năng giữ presence của property, hoặc chọn JSON Merge Patch/JSON Patch với semantics đã định nghĩa. Không âm thầm suy diễn `null` thành “không thay đổi” nếu client không được thông báo.

## Gắn affordance PATCH vào link

Một link `self` đến đơn hàng chỉ cung cấp URI resource. Để mô tả thao tác cập nhật một phần, tạo affordance từ phương thức `patch(...)`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;

Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
    .withSelfRel()
    .andAffordance(afford(
        methodOn(OrderController.class).patch(order.getId(), null)));
```

Ví dụ giả định controller cũng có `one(UUID id)` để đọc đơn hàng. `methodOn(...)` tạo proxy ghi nhận method mapping và đối số; nó không thực thi thân controller, không gửi PATCH và không thay đổi dữ liệu. `null` là placeholder cho request body khi tham chiếu chữ ký phương thức để Spring HATEOAS đọc metadata.

`afford(...)` tạo affordance từ phương thức PATCH; `andAffordance(...)` gắn mô tả thao tác đó vào link self. Khi serializer hỗ trợ affordance, client có thể nhận được metadata của phương thức và các trường đầu vào được suy ra từ mapping/DTO.

Có thể tạo link `edit` riêng nếu API muốn phân biệt quan hệ đọc với quan hệ chỉnh sửa:

```java
Link edit = linkTo(methodOn(OrderController.class).one(order.getId()))
    .withRel("edit")
    .andAffordance(afford(
        methodOn(OrderController.class).patch(order.getId(), null)));
```

Trong cách này, `self` vẫn trỏ đến representation hiện tại, còn `edit` biểu diễn khả năng chỉnh sửa. Relation `edit` là quy ước của API; hãy dùng nhất quán và mô tả trong hợp đồng. Affordance có thể được gắn vào cùng một link hoặc một link riêng tùy cách client cần khám phá thao tác.

## Ví dụ đầy đủ với EntityModel

Assembler có thể tạo representation đơn hàng, self link và affordance PATCH:

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
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = OrderView.from(order);

        Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
            .withSelfRel();

        if (order.isEditable()) {
            self = self.andAffordance(afford(
                methodOn(OrderController.class).patch(order.getId(), null)));
        }

        return EntityModel.of(view, self);
    }
}
```

`OrderView.from(...)` và `order.isEditable()` là các phương thức domain/mapper minh họa. Ứng dụng cần triển khai điều kiện chỉnh sửa theo trạng thái và chính sách thực tế. Nếu quyền người dùng cũng quyết định khả năng PATCH, hãy tính đến ngữ cảnh bảo mật khi tạo representation.

Việc không phát affordance không ngăn client gọi trực tiếp endpoint. Controller/service vẫn phải xác thực, phân quyền, kiểm tra trạng thái và validation mỗi khi nhận request PATCH.

## HAL cơ bản và HAL-FORMS

### HAL cơ bản

HAL (`application/hal+json`) biểu diễn các liên kết trong `_links`. Ví dụ:

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

HAL cơ bản cho client biết URI của đơn hàng. Nó không có cấu trúc form chuẩn để mô tả rằng endpoint chấp nhận PATCH, cũng không mô tả các property của request body. Nếu client chỉ nhận HAL cơ bản, client cần biết hợp đồng PATCH qua tài liệu API hoặc một cơ chế khác.

### HAL-FORMS

HAL-FORMS (`application/prs.hal-forms+json`) mở rộng representation bằng `_templates`. Template có thể mô tả HTTP method, target và các property mà client cần gửi.

Ví dụ minh họa:

```json
{
  "id": "ord-1042",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    }
  },
  "_templates": {
    "default": {
      "method": "PATCH",
      "target": "https://api.example.com/api/orders/ord-1042",
      "contentType": "application/json",
      "properties": [
        {
          "name": "shippingAddress",
          "required": false
        },
        {
          "name": "deliveryNote",
          "required": false
        }
      ]
    }
  }
}
```

Tên template, cách serialize `contentType` và metadata property thực tế phụ thuộc relation, cấu hình hypermedia và phiên bản Spring HATEOAS. JSON trên minh họa các thông tin client cần biết; hãy kiểm tra response được tạo bởi ứng dụng thay vì giả định mọi cấu hình đều cho đúng từng byte như ví dụ.

Client yêu cầu HAL-FORMS bằng header:

```http
GET /api/orders/ord-1042
Accept: application/prs.hal-forms+json
```

Với Spring Boot starter HATEOAS, hỗ trợ hypermedia thường được cấu hình tự động. Nếu cấu hình Spring MVC thủ công, có thể bật HAL-FORMS:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
```

Nếu API cần hỗ trợ đồng thời HAL và HAL-FORMS, cấu hình content negotiation theo hướng dẫn của phiên bản Spring HATEOAS đang dùng và kiểm thử từng `Accept` header. Không mặc định rằng metadata affordance sẽ xuất hiện trong mọi media type.

## Chọn định dạng PATCH phù hợp

Affordance mô tả endpoint và input mà client có thể gửi, nhưng không thay thế việc chọn semantics của patch document.

### Patch DTO riêng của ứng dụng

Đây là cách dễ tích hợp với controller Spring MVC và request DTO. Ví dụ `OrderPatchRequest` có các field tùy chọn. Cần định nghĩa rõ:

- Field bị bỏ qua có nghĩa là không thay đổi.
- Field có giá trị mới sẽ thay thế giá trị cũ.
- Field `null` có nghĩa là giữ nguyên, xóa hay không hợp lệ.
- Các field nào có thể cập nhật và field nào bị cấm.
- Có cho phép cập nhật nhiều field trong một request hay không.

HAL-FORMS có thể giúp client khám phá tên và metadata property. Tuy nhiên, form template không tự mô tả đầy đủ mọi quy tắc nghiệp vụ hoặc semantics absent/null của DTO.

### JSON Merge Patch

JSON Merge Patch dùng media type `application/merge-patch+json`. Ví dụ:

```json
{
  "shippingAddress": "25 Le Loi, District 1",
  "deliveryNote": null
}
```

Theo JSON Merge Patch, giá trị `null` có ý nghĩa loại bỏ member tương ứng khỏi target object. Vì vậy định dạng này không phù hợp nếu API cần phân biệt “đặt field thành JSON null” với “xóa field” mà không có quy ước bổ sung. Server cần hỗ trợ media type và áp dụng merge semantics theo RFC 7396.

### JSON Patch

JSON Patch dùng media type `application/json-patch+json`. Body là danh sách thao tác:

```json
[
  {
    "op": "replace",
    "path": "/shippingAddress",
    "value": "25 Le Loi, District 1"
  },
  {
    "op": "remove",
    "path": "/deliveryNote"
  }
]
```

JSON Patch phù hợp khi client cần mô tả thao tác rõ ràng trên các path. Server cần xác thực path, operation, quyền sửa từng field và áp dụng toàn bộ patch nguyên tử. Affordance cho endpoint JSON Patch nên mô tả request body là patch document, không giả định body là DTO chứa trực tiếp các field của resource.

## Content negotiation và Accept-Patch

Server có thể công bố các media type patch được hỗ trợ qua response header `Accept-Patch`, ví dụ:

```http
Accept-Patch: application/merge-patch+json, application/json-patch+json
```

Header này cho client biết endpoint chấp nhận những định dạng patch nào. Nó bổ sung thông tin cho affordance, đặc biệt khi cùng endpoint có thể nhận nhiều loại patch document.

Hãy dùng `consumes` trên `@PatchMapping` để giới hạn media type mà endpoint chấp nhận. Request gửi media type không hỗ trợ cần nhận phản hồi phù hợp, thường là `415 Unsupported Media Type`. Nếu body hợp lệ về cú pháp nhưng vi phạm quy tắc nghiệp vụ, trả lỗi validation hoặc conflict theo hợp đồng.

## Điều kiện để công bố affordance PATCH

Không phải mọi resource hoặc trạng thái đều cho phép cập nhật. Ví dụ, đơn hàng đã giao có thể không được đổi địa chỉ. Khi tạo representation, chỉ gắn affordance nếu điều kiện nghiệp vụ và quyền hiện tại cho phép:

```java
Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
    .withSelfRel();

if (order.isEditable() && authorization.canEdit(order)) {
    self = self.andAffordance(afford(
        methodOn(OrderController.class).patch(order.getId(), null)));
}
```

`authorization.canEdit(...)` minh họa một chính sách phân quyền. Nếu response được cache, link phụ thuộc người dùng hoặc vai trò cần cache policy phù hợp để không dùng nhầm affordance của người này cho người khác.

Trạng thái có thể thay đổi giữa lúc client đọc representation và lúc gửi PATCH. Vì vậy, server phải kiểm tra lại điều kiện tại thời điểm cập nhật. Nếu cần optimistic concurrency, dùng ETag/If-Match hoặc version field phù hợp.

## Kiểm thử affordance PATCH

Kiểm thử cần xác nhận link, method, target và metadata input theo media type. Nên tách kiểm thử controller PATCH thật với kiểm thử serialization affordance.

### Kiểm tra HAL cơ bản

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Test này chỉ xác nhận link. Nó không chứng minh HAL cơ bản đã mô tả method PATCH hoặc request properties.

### Kiểm tra HAL-FORMS template

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates.default.method").value("PATCH"))
    .andExpect(jsonPath("$._templates.default.target")
        .value(org.hamcrest.Matchers.endsWith("/api/orders/" + orderId)));
```

`default` là tên template minh họa. Nếu serializer đặt template dưới một key khác, hãy điều chỉnh JSON path theo response thực tế và hợp đồng đã công bố. Có thể kiểm tra thêm `_templates.default.properties[*].name` để bảo đảm các field patch cần thiết xuất hiện.

### Kiểm tra endpoint PATCH

```java
mockMvc.perform(patch("/api/orders/{id}", orderId)
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {"shippingAddress":"25 Le Loi, District 1"}
            """))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.shippingAddress")
        .value("25 Le Loi, District 1"));
```

Đây là test cho patch DTO riêng của ứng dụng. Nếu endpoint dùng JSON Merge Patch hoặc JSON Patch, thay `Content-Type` và body bằng đúng định dạng tương ứng.

Ngoài ra, nên kiểm thử:

- Field bị bỏ qua giữ nguyên giá trị theo hợp đồng.
- `null` được xử lý đúng semantics đã công bố.
- Field không được phép cập nhật bị từ chối.
- Patch document sai cú pháp hoặc sai path không làm resource thay đổi một phần.
- Người dùng không có quyền không nhìn thấy affordance nếu chính sách yêu cầu, và vẫn bị từ chối khi gọi endpoint trực tiếp.
- ETag/If-Match phát hiện cập nhật đồng thời nếu API hỗ trợ.
- Content negotiation trả đúng HAL hoặc HAL-FORMS theo `Accept`.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ thêm link `href` rồi kỳ vọng client biết dùng PATCH | HAL cơ bản không mô tả method và body. | Gắn affordance và dùng media type hỗ trợ như HAL-FORMS. |
| Dùng PATCH nhưng không định nghĩa semantics body | Client không biết field vắng mặt hoặc `null` có nghĩa gì. | Công bố patch format và quy tắc absent/null rõ ràng. |
| Cho rằng PATCH luôn idempotent | Retry có thể áp dụng thao tác tăng/append nhiều lần. | Thiết kế operation idempotent khi cần hoặc xử lý retry/concurrency rõ ràng. |
| Dùng `methodOn` như lời gọi controller thật | Hiểu nhầm placeholder body sẽ được gửi hoặc nghiệp vụ sẽ chạy. | Xem `methodOn` là proxy ghi nhận invocation để tạo metadata. |
| Dùng affordance như cơ chế bảo mật | Client vẫn có thể gọi endpoint trực tiếp. | Kiểm tra quyền và trạng thái tại controller/service. |
| Không giới hạn `consumes` | Endpoint có thể nhận media type không đúng semantics. | Khai báo media type được hỗ trợ và công bố `Accept-Patch` khi phù hợp. |
| Kiểm thử chỉ self link | Không phát hiện template thiếu method hoặc property. | Kiểm tra HAL-FORMS `_templates` cùng endpoint PATCH thực tế. |
| Bỏ qua cập nhật đồng thời | Client có thể ghi đè thay đổi mới hơn. | Dùng ETag/If-Match hoặc versioning phù hợp. |

## Ghi nhớ

- PATCH áp dụng thay đổi lên một phần resource; body và semantics do patch format/hợp đồng API quy định.
- Dùng `@PatchMapping` cho endpoint và `afford(methodOn(...))` để mô tả mapping đó.
- `andAffordance(...)` gắn thao tác PATCH vào link; `methodOn(...)` chỉ ghi nhận method và tham số, không thực thi controller.
- HAL cơ bản cung cấp link; HAL-FORMS có thể biểu diễn method, target và request properties trong `_templates`.
- Phân biệt patch DTO riêng, JSON Merge Patch và JSON Patch; định nghĩa rõ absent/null và media type.
- Công bố affordance theo trạng thái/quyền nhưng luôn kiểm tra lại ở server khi nhận request.
- PATCH không idempotent theo mặc định; cân nhắc atomicity, ETag/If-Match và retry.
- Kiểm thử template, endpoint PATCH, content negotiation và các trường hợp lỗi.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring HATEOAS API – Affordance](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Affordance.html)
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/)
- [RFC 5789 – PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789)
- [RFC 7396 – JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
- [RFC 6902 – JSON Patch](https://www.rfc-editor.org/rfc/rfc6902)
