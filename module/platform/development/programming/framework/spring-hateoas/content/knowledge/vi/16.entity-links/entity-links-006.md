# EntityLinks tùy biến

`EntityLinks` là abstraction của Spring HATEOAS giúp tạo link tới collection resource và item resource dựa trên kiểu domain. Nó tách nơi sử dụng link khỏi chi tiết controller và route. Thay vì để mỗi assembler tự ghép URI, ứng dụng có thể yêu cầu `EntityLinks` tạo link cho một kiểu như `Order` hoặc cho một đơn hàng cụ thể.

Trong trường hợp thông thường, Spring HATEOAS có thể suy ra mapping từ controller được đánh dấu bằng `@ExposesResourceFor`. Khi URI có cấu trúc đặc biệt, chứa tenant, phiên bản API hoặc quy tắc định tuyến riêng, ứng dụng có thể bổ sung chiến lược link tùy biến. Chiến lược đó có thể là một implementation của `EntityLinks` hoặc một lớp chuyên biệt bao bọc cách tạo link cho domain cụ thể.

## EntityLinks giải quyết vấn đề gì?

Một ứng dụng có thể có nhiều nơi cần tạo link tới cùng một loại tài nguyên: controller, assembler, processor và các thành phần trình bày khác. Nếu từng nơi tự ghép `/orders/{id}`, thay đổi route sẽ buộc phải sửa nhiều chỗ. `EntityLinks` cung cấp một điểm truy cập theo kiểu tài nguyên để tập trung cách xác định URI.

Hai nhu cầu cơ bản là:

- Link tới **collection resource** của một kiểu, ví dụ danh sách đơn hàng.
- Link tới **item resource** cụ thể, ví dụ đơn hàng có mã `42`.

`EntityLinks` phù hợp với link định danh tài nguyên. Với link hành động như `approve`, `cancel` hoặc `pay`, thường dùng `WebMvcLinkBuilder`/`WebFluxLinkBuilder` trực tiếp hoặc một lớp chuyên biệt tạo action link, vì những link đó gắn với thao tác controller cụ thể.

## Cấu hình mapping mặc định bằng @ExposesResourceFor

`ControllerEntityLinks` là implementation dựa trên controller mapping. Controller khai báo loại domain mà nó expose bằng `@ExposesResourceFor`:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/orders")
class OrderController {

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> all() {
        // Trả representation của collection đơn hàng.
        return orderQueryService.findAllModels();
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable("id") UUID id) {
        // Trả representation của một đơn hàng.
        return orderQueryService.findModel(id);
    }
}
```

`Order` là domain type được expose; `OrderRepresentation` là kiểu dữ liệu trả về qua API. Annotation giúp Spring HATEOAS liên hệ domain type với controller quản lý resource. Các phương thức trong ví dụ được lược giản để tập trung vào mapping.

Khi controller có mapping phù hợp, `EntityLinks` có thể tạo link theo kiểu tài nguyên:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    private final EntityLinks entityLinks;

    OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation body = new OrderRepresentation(
            order.getId(), order.getStatus().name(), order.getTotal());

        Link self = entityLinks
            .linkForItemResource(Order.class, order.getId())
            .withSelfRel();

        Link collection = entityLinks
            .linkFor(Order.class)
            .withRel("orders");

        return EntityModel.of(body, self, collection);
    }
}
```

Ví dụ minh họa cách sử dụng `EntityLinks`: `linkFor(Order.class)` tạo link tới collection, còn `linkForItemResource(Order.class, id)` tạo link tới một item. Các link được tạo theo mapping mà implementation biết, vì vậy assembler không cần biết controller nằm ở lớp nào hoặc route cụ thể là gì.

## Những phương thức thường dùng

`EntityLinks` cung cấp các biến thể tạo link theo kiểu tài nguyên và tham số route. Tùy phiên bản Spring HATEOAS, các phương thức trả về `LinkBuilder` để tiếp tục gắn relation hoặc chuyển thành `Link`.

| Phương thức | Mục đích |
| --- | --- |
| `linkFor(Order.class)` | Link tới collection resource của `Order` |
| `linkFor(Order.class, parameters...)` | Link tới collection khi route cần thêm path parameter |
| `linkFor(Order.class, parameterMap)` | Link collection với path variable được truyền theo tên |
| `linkForItemResource(Order.class, id)` | Link tới item theo định danh |
| `linkForItemResource(Order.class, parameterMap)` | Link item khi route cần nhiều path variable |
| `linkForItemResource(order)` | Link tới item từ một instance domain |

Khi route chỉ có `/orders/{id}`, overload nhận `id` thường là đủ. Khi route lồng như `/tenants/{tenantId}/orders/{orderId}`, cần cung cấp đủ giá trị path variable mà mapping yêu cầu. Dùng map theo tên biến giúp lời gọi dễ đọc hơn khi route có nhiều tham số.

## Khi nào cần chiến lược EntityLinks tùy biến?

Implementation mặc định dựa vào controller mapping là lựa chọn phù hợp nếu URI của resource phản ánh trực tiếp các mapping đó. Một chiến lược tùy biến có ích khi ứng dụng có quy tắc định tuyến không thể suy ra chỉ từ controller:

- **Multi-tenant:** mọi URI đơn hàng phải nằm dưới `/tenants/{tenantId}/orders/...` và tenant được xác định từ ngữ cảnh hiện tại.
- **Versioning:** URI công khai có prefix phiên bản như `/api/v2/orders`, trong khi controller nội bộ không dùng cùng cấu trúc.
- **Legacy route:** tài nguyên vẫn được công bố qua URI cũ để giữ tương thích trong khi controller hoặc service đã thay đổi.
- **Nhiều host hoặc gateway:** link cần trỏ tới API host công khai hoặc một gateway riêng thay vì host nội bộ.
- **Quy tắc định danh:** URI item cần thêm mã vùng, loại tài nguyên hoặc một khóa ghép.

Trước khi viết implementation riêng, hãy xác định liệu mapping controller và overload nhận tham số của `EntityLinks` đã giải quyết được nhu cầu hay chưa. Nếu chỉ có một vài route đặc biệt, một lớp link factory chuyên biệt thường dễ kiểm thử và bảo trì hơn việc thay thế toàn bộ `EntityLinks` dùng chung.

## Ví dụ: route có tenant và nhiều path variable

Giả sử URI công khai của đơn hàng có dạng:

```text
/tenants/{tenantId}/orders/{orderId}
```

Controller expose `Order` nhưng route cần cả `tenantId` và `orderId`:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/tenants/{tenantId}/orders")
class TenantOrderController {

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> all(
            @PathVariable("tenantId") UUID tenantId) {
        return orderQueryService.findModels(tenantId);
    }

    @GetMapping("/{orderId}")
    EntityModel<OrderRepresentation> one(
            @PathVariable("tenantId") UUID tenantId,
            @PathVariable("orderId") UUID orderId) {
        return orderQueryService.findModel(tenantId, orderId);
    }
}
```

Với controller mapping như trên, có thể truyền các path variable theo tên cho `EntityLinks`:

```java
import java.util.Map;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;

Link collection = entityLinks
    .linkFor(Order.class, Map.of("tenantId", tenantId))
    .withRel("orders");

Link item = entityLinks
    .linkForItemResource(Order.class,
        Map.of("tenantId", tenantId, "orderId", orderId))
    .withSelfRel();
```

Các tên trong map phải khớp tên path variable trong controller. Với route này, chỉ truyền `orderId` là chưa đủ vì URI item còn phụ thuộc `tenantId`. Ứng dụng cũng phải xác thực rằng `orderId` thực sự thuộc `tenantId`; việc tạo được link không chứng minh quan hệ đó hợp lệ.

Nếu implementation `EntityLinks` đang dùng không hỗ trợ hoặc không thể suy ra mapping nhiều biến theo cách ứng dụng cần, có thể tạo một factory chuyên biệt bằng `WebMvcLinkBuilder`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

@Component
class TenantOrderLinks {

    Link collection(UUID tenantId) {
        return linkTo(methodOn(TenantOrderController.class).all(tenantId))
            .withRel("orders");
    }

    Link item(UUID tenantId, UUID orderId) {
        return linkTo(methodOn(TenantOrderController.class)
            .one(tenantId, orderId)).withSelfRel();
    }
}
```

Factory này là một chiến lược tùy biến ở cấp ứng dụng: nó giữ quy tắc tạo link cho đơn hàng tenant trong một nơi. `methodOn(...)` dùng mapping controller thật để tạo URI; không nối chuỗi route thủ công. Nếu dự án cần một SPI `EntityLinks` thống nhất cho nhiều domain type, có thể triển khai interface đó và ủy quyền các loại không tùy biến cho implementation mặc định.

## Tổ chức implementation EntityLinks riêng

Khi thật sự cần thay thế cách tạo link mặc định cho một nhóm domain type, implementation riêng nên có phạm vi rõ ràng:

1. Xác định các domain type mà implementation hỗ trợ, ví dụ chỉ `Order.class`.
2. Tạo link collection và item theo quy tắc URI công khai đã chọn.
3. Nhận đầy đủ tham số route, bao gồm tenant hoặc version nếu cần.
4. Xử lý trường hợp thiếu tham số hoặc type không được hỗ trợ bằng lỗi rõ ràng.
5. Giữ relation do caller chọn; implementation chịu trách nhiệm tạo URI, không tự ý đổi ý nghĩa relation.
6. Đăng ký implementation như Spring bean và cấu hình việc chọn bean/delegate rõ ràng để không tạo xung đột khi implementation mặc định cũng hiện diện.

Một implementation có thể hỗ trợ một tập domain type hẹp và ủy quyền những type khác cho implementation mặc định. Tránh một class lớn chứa hàng loạt `if/else` theo entity, tenant, phiên bản và endpoint. Khi số chiến lược tăng lên, tách chúng thành các factory nhỏ hoặc một cơ chế delegate có quy tắc chọn rõ ràng.

Nếu class triển khai trực tiếp `EntityLinks`, cần đáp ứng toàn bộ overload mà phiên bản Spring HATEOAS của dự án công bố: link collection theo type, link collection có tham số, link item theo ID, link item theo map path variable và link item từ domain instance. Không chỉ triển khai phương thức đang được một assembler gọi, vì thành phần khác có thể dùng overload còn lại. Các overload không phù hợp với chiến lược phải từ chối rõ ràng hoặc delegate; không trả về URI giả hay link thiếu path variable.

Khi ứng dụng đồng thời có implementation mặc định và implementation riêng, cần cấu hình bean selection có chủ đích. Có thể giới hạn injection bằng qualifier hoặc chọn một implementation chính nếu nó thực sự thay thế chiến lược chung. Nếu custom implementation chỉ xử lý `Order`, đừng để nó vô tình trở thành implementation duy nhất cho mọi domain type khác.

Đối với ứng dụng dùng cả Spring MVC và WebFlux, cần chọn builder tương ứng trong custom strategy. `WebMvcLinkBuilder` tạo link đồng bộ cho Spring MVC; `WebFluxLinkBuilder` tạo kết quả reactive và cần được ghép vào `Mono`/`Flux`. Không tái sử dụng builder MVC trong pipeline WebFlux chỉ vì hai API có tên phương thức tương tự.

## Dùng EntityLinks trong assembler và processor

Assembler là nơi phù hợp để dùng `EntityLinks` khi link gắn với danh tính của tài nguyên:

```java
@Component
class OrderModelAssembler {

    private final EntityLinks entityLinks;

    OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation body = toRepresentation(order);

        Link self = entityLinks
            .linkForItemResource(Order.class, order.getId())
            .withSelfRel();

        return EntityModel.of(body, self);
    }
}
```

Nếu link cần điều kiện theo trạng thái, ví dụ `cancel` chỉ khả dụng khi đơn hàng đang chờ xử lý, có thể để assembler hoặc `RepresentationModelProcessor` bổ sung link hành động. Không nên dùng `EntityLinks` để che giấu quy tắc nghiệp vụ hoặc kiểm tra quyền; các điều kiện đó thuộc service/policy và endpoint vẫn phải xác thực request khi được gọi.

## Kiểm thử EntityLinks tùy biến

Kiểm thử nên xác nhận URI được tạo theo đúng quy tắc, cả ở mức link factory và response HTTP cuối cùng.

Unit test cho factory tenant có thể xác nhận path variable được đưa vào đúng vị trí:

```java
assertThat(tenantOrderLinks.item(tenantId, orderId).getHref())
    .endsWith("/tenants/" + tenantId + "/orders/" + orderId);
```

Với integration test, gọi endpoint và kiểm tra link `self` trong HAL JSON:

```java
mockMvc.perform(get("/tenants/{tenantId}/orders/{orderId}",
        tenantId, orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(endsWith("/tenants/" + tenantId + "/orders/" + orderId)));
```

Các ca kiểm thử nên bao gồm:

- Collection link chứa đúng tenant và không nhầm tenant khác.
- Item link chứa đủ mọi path variable.
- ID không tồn tại hoặc không thuộc tenant trả lỗi theo chính sách API.
- Domain type không được implementation hỗ trợ tạo lỗi rõ ràng hoặc được delegate đúng nơi.
- Context path, API version và reverse proxy tạo ra base URI công khai mong muốn.
- Assembler và processor không tạo hai link `self` trùng nhau.

## Lỗi thiết kế thường gặp

- **Đưa route vào assembler:** nhiều assembler tự ghép cùng một URI, khiến thay đổi route phải sửa nhiều nơi.
- **Thiếu `@ExposesResourceFor`:** implementation dựa trên controller không biết controller expose domain type nào.
- **Thiếu path variable:** route lồng tenant cần `tenantId` nhưng lời gọi chỉ truyền `orderId`.
- **Dùng EntityLinks cho action link:** link `cancel` hoặc `approve` phụ thuộc thao tác cụ thể, không chỉ phụ thuộc entity type.
- **Có nhiều implementation mơ hồ:** Spring không biết bean nào cần inject hoặc delegate không được chọn nhất quán.
- **Nhầm link với phân quyền:** link có mặt không cấp quyền; endpoint phải kiểm tra tenant và quyền truy cập độc lập.
- **Hardcode host:** link có thể sai khi ứng dụng chạy sau gateway hoặc reverse proxy.

`EntityLinks` giúp chuẩn hóa việc tạo link collection và item theo domain type. Bắt đầu với `@ExposesResourceFor` và implementation dựa trên controller; chỉ bổ sung chiến lược tùy biến khi URI có quy tắc riêng. Khi giữ logic tạo link tập trung, truyền đủ path variable và kiểm thử response hypermedia thực tế, API Spring HATEOAS có thể thay đổi route mà không buộc assembler và client phụ thuộc vào cấu trúc URL cũ.
