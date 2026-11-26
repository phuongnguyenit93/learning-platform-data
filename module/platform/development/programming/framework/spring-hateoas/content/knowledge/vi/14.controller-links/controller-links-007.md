# Link cho DELETE

Trong REST API, thao tác xóa một resource thường được thực hiện bằng HTTP `DELETE`. Với Spring MVC, handler xử lý thao tác này được khai báo bằng `@DeleteMapping`. Spring HATEOAS có thể tạo một hypermedia link trỏ đến handler đó để client khám phá hành động xóa từ representation hiện tại.

Khi xây link, cần phân biệt URI của thao tác với HTTP method thực tế. Một link HAL cơ bản chứa `href` và relation, nhưng không có trường chuẩn để nói rằng client phải gửi `DELETE`. Nếu chỉ công bố link có relation như `delete`, client cần hiểu quy ước đó từ hợp đồng API. Nếu muốn mô tả phương thức HTTP và dữ liệu đầu vào như một affordance, có thể dùng cơ chế affordance của Spring HATEOAS và một media type hỗ trợ mô tả thao tác, chẳng hạn HAL-FORMS.

## 1. Endpoint DELETE trong Spring MVC

Giả sử API quản lý đơn hàng và cho phép xóa một đơn hàng theo định danh. Controller có thể khai báo:

```java
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable UUID id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

Mapping ở cấp class tạo prefix `/orders`; `@DeleteMapping("/{id}")` ánh xạ request `DELETE /orders/{id}`. Khi thao tác thành công và không cần trả representation mới, `204 No Content` là một phản hồi phù hợp.

`ResponseEntity<Void>` cũng là kiểu trả về hữu ích khi tham chiếu handler bằng `methodOn(...)`: lời gọi được ghi nhận để dựng link, không cần thực thi service hoặc xóa dữ liệu trong lúc tạo link.

## 2. Tạo link trỏ đến handler DELETE

Spring HATEOAS có thể tạo URI từ mapping của controller bằng `WebMvcLinkBuilder`:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link deleteLink = linkTo(methodOn(OrderController.class)
        .delete(order.getId()))
        .withRel("delete");
```

`methodOn(OrderController.class).delete(order.getId())` mô tả handler `delete` và truyền giá trị path variable. `linkTo(...)` đọc mapping Spring MVC để tạo URI, còn `withRel("delete")` gắn relation cho link.

Ví dụ này tạo link trỏ đến `/orders/{id}`. `methodOn(...)` không gọi phần thân controller, không thực thi `orderService.delete(...)` và không xóa resource. Nó chỉ cung cấp thông tin về phương thức handler và tham số để xây dựng URI.

Relation `delete` là nhãn mà client có thể dùng để nhận biết ý nghĩa của link. Nếu API dùng relation tùy chỉnh, cần tài liệu hóa ý nghĩa và cách thực hiện thao tác. Không nên giả định mọi client đều suy ra HTTP method chỉ từ tên relation.

## 3. Công bố link DELETE trong representation

Một assembler có thể đưa link xóa vào representation của đơn hàng:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;
import org.springframework.hateoas.server.RepresentationModelAssembler;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        Link self = linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel();

        EntityModel<OrderRepresentation> model = EntityModel.of(
                OrderRepresentation.from(order), self);

        if (order.canBeDeleted()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .delete(order.getId())).withRel("delete"));
        }

        return model;
    }
}
```

Ví dụ giả định `Order` có `canBeDeleted()` và `OrderRepresentation.from(...)`, còn controller có handler `one(...)` để lấy chi tiết đơn hàng. Assembler luôn thêm `self`; link `delete` chỉ được thêm khi trạng thái đơn hàng cho phép xóa.

Khi serialize theo HAL, client có thể nhận representation tương tự:

```json
{
  "id": "b35e8d4d-10e1-4c17-9d5f-6e8f0d13c024",
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/b35e8d4d-10e1-4c17-9d5f-6e8f0d13c024"
    },
    "delete": {
      "href": "https://api.example.test/orders/b35e8d4d-10e1-4c17-9d5f-6e8f0d13c024"
    }
  }
}
```

Ở ví dụ này, cả `self` và `delete` có thể trỏ đến cùng một URI vì cùng định danh đơn hàng. Ý nghĩa của thao tác được phân biệt bởi relation và hợp đồng HTTP. Client theo link `delete` rồi gửi request với method `DELETE`.

## 4. Link HAL cơ bản không mô tả HTTP method

HAL link cơ bản cung cấp URI và metadata liên kết như relation, title hoặc type. Nó không có thuộc tính chuẩn `method` để mô tả rằng link phải được gọi bằng `DELETE`.

Điều đó có nghĩa:

- `href` cho biết URI đích.
- `rel` cho biết ý nghĩa liên kết trong representation.
- `DELETE` là phương thức HTTP mà client cần gửi theo hợp đồng API.
- Việc server phát link không tự thực hiện thao tác xóa.

Nếu API chỉ dùng HAL cơ bản, tài liệu hợp đồng cần giải thích relation `delete` tương ứng với HTTP `DELETE`, cùng các điều kiện và phản hồi có thể có. Client có thể dựa trên quy ước đã biết để gửi đúng method.

Nếu muốn response mô tả rõ hơn hành động, bao gồm HTTP method và các thuộc tính đầu vào, nên dùng affordance với media type hỗ trợ affordance. Không nên thêm trường `method` tùy ý vào HAL link rồi kỳ vọng client HAL tiêu chuẩn hiểu nó.

## 5. Mô tả DELETE bằng affordance

Affordance trong Spring HATEOAS cho phép gắn mô tả thao tác khả dụng vào một link. Với handler `DELETE`, có thể gắn affordance vào self link của resource:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class)
            .one(order.getId()))
            .withSelfRel()
            .andAffordance(afford(methodOn(OrderController.class)
                    .delete(order.getId())));

    return EntityModel.of(OrderRepresentation.from(order), self);
}
```

`afford(...)` mô tả thao tác của handler `delete(...)`; `andAffordance(...)` gắn mô tả đó vào link `self`. Client có thể nhận diện resource qua self link và khám phá affordance xóa gắn với resource đó.

Affordance không tự xóa resource và cũng không thay thế kiểm tra ở server. Nó mô tả một thao tác mà API công bố tại thời điểm tạo representation. Nếu trạng thái thay đổi trước khi client gửi request, endpoint vẫn phải kiểm tra lại điều kiện.

## 6. Chọn media type để công bố affordance

Media type quyết định cách affordance được biểu diễn trong response. HAL cơ bản chủ yếu mô tả liên kết; HAL-FORMS có thể biểu diễn các thao tác dưới dạng template với thông tin về phương thức HTTP và các thuộc tính đầu vào.

Client có thể yêu cầu HAL-FORMS bằng header:

```http
GET /orders/b35e8d4d-10e1-4c17-9d5f-6e8f0d13c024 HTTP/1.1
Host: api.example.test
Accept: application/prs.hal-forms+json
```

Nếu ứng dụng đã cấu hình serializer và content negotiation cho HAL-FORMS, response có thể biểu diễn affordance gắn với self link dưới dạng template mô tả thao tác `DELETE`. Cấu trúc chi tiết phụ thuộc phiên bản Spring HATEOAS và cấu hình media type. Client cần hỗ trợ HAL-FORMS để khai thác metadata này.

Nếu client chỉ hỗ trợ `application/hal+json`, nó vẫn có thể dùng link `delete` theo hợp đồng API, nhưng không nên giả định response HAL cơ bản sẽ tự chứa toàn bộ mô tả affordance.

## 7. Chỉ công bố DELETE khi hành động khả dụng

Không phải mọi đơn hàng đều có thể xóa. Ví dụ, đơn hàng ở trạng thái `DRAFT` có thể được xóa, trong khi đơn hàng đã thanh toán hoặc giao đi cần được giữ lại để phục vụ kiểm toán. Assembler có thể phản ánh điều kiện đó bằng cách chỉ thêm link hoặc affordance khi phù hợp:

```java
EntityModel<OrderRepresentation> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class)
            .one(order.getId())).withSelfRel();

    EntityModel<OrderRepresentation> model = EntityModel.of(
            OrderRepresentation.from(order), self);

    if (order.canBeDeleted()) {
        model.add(linkTo(methodOn(OrderController.class)
                .delete(order.getId())).withRel("delete"));
    }

    return model;
}
```

Điều kiện `canBeDeleted()` cần phản ánh quy tắc nghiệp vụ. Nếu quyền xóa còn phụ thuộc người dùng hiện tại, ứng dụng cần tính đến quyền của người gọi khi quyết định công bố link. Tuy nhiên, việc ẩn link chỉ giúp client khám phá đúng các khả năng; nó không phải cơ chế bảo mật.

Endpoint `DELETE` vẫn phải kiểm tra xác thực, phân quyền, trạng thái resource và các ràng buộc nghiệp vụ tại thời điểm nhận request. Client có thể lưu link cũ hoặc tự tạo request đến URI mà nó biết.

## 8. Ngữ nghĩa HTTP DELETE

HTTP `DELETE` yêu cầu server xóa liên kết giữa URI đích và chức năng hiện tại của resource. Điều này không bắt buộc server phải xóa vật lý mọi dữ liệu khỏi database; hệ thống có thể dùng soft delete, đánh dấu ngừng hoạt động hoặc áp dụng quy trình lưu trữ theo nghiệp vụ.

Một số điểm cần lưu ý:

- `DELETE` là phương thức idempotent: gửi cùng thao tác nhiều lần có cùng hiệu quả dự kiến trên trạng thái resource. Điều này không có nghĩa mọi lần gọi phải trả cùng status code.
- Server thường trả `204 No Content` nếu thao tác thành công và không trả body.
- Có thể trả `200 OK` nếu response chứa representation mô tả kết quả.
- Có thể trả `202 Accepted` nếu yêu cầu xóa được chấp nhận nhưng xử lý sẽ hoàn tất bất đồng bộ.
- `404 Not Found` có thể được dùng khi resource không tồn tại; chính sách với resource đã bị xóa cần nhất quán.
- `409 Conflict` có thể phù hợp nếu trạng thái hiện tại hoặc ràng buộc nghiệp vụ ngăn việc xóa.

Không dùng `GET` để thực hiện xóa. `GET` được kỳ vọng là safe; client, crawler hoặc cache có thể gọi GET mà không dự đoán một thay đổi trạng thái nghiệp vụ. Hành động xóa cần được thực hiện bằng `DELETE` theo hợp đồng.

## 9. Xử lý lỗi và quyền truy cập

Khi nhận request `DELETE`, server cần xác định người gọi có quyền xóa resource hay không và resource có đang ở trạng thái cho phép xóa hay không. Ví dụ:

```java
@DeleteMapping("/{id}")
ResponseEntity<Void> delete(@PathVariable UUID id) {
    Order order = orderService.getRequired(id);
    authorizationService.requireCanDelete(order);
    orderService.delete(order);
    return ResponseEntity.noContent().build();
}
```

Đây là ví dụ minh họa; trong ứng dụng thực tế, kiểm tra quyền có thể được thực hiện ở service, method security hoặc tầng nghiệp vụ phù hợp. Quan trọng là kiểm tra được áp dụng cho mọi request, kể cả khi client gọi URI trực tiếp.

Nếu thao tác không thể thực hiện, API cần trả status code và lỗi theo hợp đồng nhất quán. Không nên trả `204` nếu thao tác thực tế bị từ chối hoặc không được thực hiện, trừ khi API có chủ đích thiết kế semantics riêng và được tài liệu hóa rõ ràng.

## 10. Kiểm thử link và endpoint DELETE

Có thể kiểm tra link được công bố trong response HAL:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.delete.href").exists());
```

Sau đó kiểm tra endpoint xóa bằng request `DELETE`:

```java
mockMvc.perform(delete("/orders/{id}", orderId))
    .andExpect(status().isNoContent());
```

Các đoạn test là ví dụ minh họa; test thực tế cần chuẩn bị dữ liệu, service mock hoặc repository phù hợp. Nên kiểm tra cả trường hợp link không được công bố và endpoint từ chối thao tác:

- Đơn hàng ở trạng thái không thể xóa không có link `delete` trong representation.
- Người dùng không có quyền bị từ chối khi gọi endpoint, kể cả khi biết URI.
- Xóa thành công trả status code đúng và cập nhật trạng thái resource.
- Gọi lại thao tác tuân theo chính sách idempotency của API.
- Nếu dùng affordance, response media type được chọn có biểu diễn metadata DELETE và client dự kiến có thể đọc metadata đó.
- Nếu dùng HAL cơ bản, tài liệu API giải thích rõ relation `delete` yêu cầu HTTP `DELETE`.

## 11. Lỗi thường gặp

**Nghĩ rằng link tự thực hiện DELETE:** link chỉ công bố URI và quan hệ. Client phải gửi request `DELETE` riêng.

**Cho rằng HAL link có thuộc tính method:** HAL link cơ bản không có trường chuẩn để mô tả HTTP method. Dùng affordance và media type phù hợp nếu cần mô tả thao tác.

**Dùng GET để xóa resource:** GET được kỳ vọng là safe. Dùng `@DeleteMapping` và HTTP `DELETE` cho thao tác xóa.

**Ẩn link rồi bỏ kiểm tra quyền ở endpoint:** client có thể lưu link cũ hoặc gọi trực tiếp URI. Server vẫn phải kiểm tra quyền và điều kiện nghiệp vụ.

**Công bố link xóa cho mọi trạng thái:** link nên phản ánh khả năng hiện tại của resource và người gọi. Hãy áp dụng quy tắc nghiệp vụ khi dựng representation.

**Nhầm idempotent với cùng một response:** DELETE idempotent về hiệu quả dự kiến, nhưng lần gọi đầu và lần gọi sau có thể nhận status code khác nhau theo chính sách API.

## 12. Checklist triển khai

- Khai báo endpoint bằng `@DeleteMapping` và dùng HTTP `DELETE`.
- Tạo URI từ controller bằng `linkTo(methodOn(...).delete(id))`.
- Chọn relation rõ ràng như `delete` và tài liệu hóa cách client gọi link.
- Dùng affordance nếu cần công bố HTTP method và metadata thao tác cho client.
- Chọn media type hỗ trợ affordance, chẳng hạn HAL-FORMS, nếu client cần đọc mô tả thao tác.
- Chỉ công bố link/affordance khi trạng thái resource và quyền người gọi cho phép.
- Kiểm tra quyền và điều kiện nghiệp vụ ngay trong luồng xử lý DELETE.
- Trả status code nhất quán như `204`, `200`, `202`, `404` hoặc `409` theo kết quả.
- Kiểm thử cả representation, endpoint, trường hợp bị từ chối và request lặp.

Link cho DELETE giúp client khám phá khả năng xóa một resource trong ngữ cảnh hypermedia. Khi tạo URI từ mapping controller, công bố relation rõ ràng và dùng affordance khi cần mô tả HTTP method, Spring HATEOAS giúp API thể hiện hành động có thể thực hiện; server vẫn chịu trách nhiệm kiểm tra quyền, trạng thái và thực thi thao tác an toàn.
