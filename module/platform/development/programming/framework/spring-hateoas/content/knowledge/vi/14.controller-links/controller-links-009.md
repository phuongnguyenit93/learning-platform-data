# Link khi có nhiều mapping

## Mục tiêu

Sau bài này, bạn có thể giải thích cách Spring MVC kết hợp mapping ở cấp controller và phương thức, nhận diện những tình huống một phương thức có nhiều đường dẫn hoặc nhiều điều kiện mapping, tạo link đến đúng endpoint bằng Spring HATEOAS và thiết kế link rõ ràng khi API có alias hoặc nhiều phiên bản. Bạn cũng có thể kiểm thử href để phát hiện link trỏ nhầm mapping.

## 1. Vì sao nhiều mapping làm link khó xác định?

Một controller có thể có mapping ở cấp lớp và cấp phương thức. Ví dụ:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<Order> getOrder(@PathVariable UUID id) {
        // ...
    }
}
```

Mapping đầy đủ của phương thức là `/orders/{id}`: phần `/orders` đến từ lớp, phần `/{id}` đến từ phương thức.

Trong ứng dụng thực tế, cùng một tài nguyên có thể được truy cập qua nhiều đường dẫn:

- Đường dẫn chuẩn: `/orders/42`.
- Đường dẫn cũ để tương thích: `/legacy/orders/42`.
- Đường dẫn theo phiên bản: `/v1/orders/42` và `/v2/orders/42`.

Spring MVC cho phép một handler khai báo nhiều path pattern hoặc nhiều điều kiện mapping. Điều này thuận tiện khi nhiều URL cùng gọi một xử lý. Tuy nhiên, khi tạo link, ứng dụng phải xác định rõ URL nào cần được công bố cho client.

## 2. Các kiểu mapping có thể xuất hiện cùng một handler

Spring MVC hỗ trợ nhiều thuộc tính mapping:

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| `path` hoặc `value` | `@GetMapping({"/{id}", "/legacy/{id}"})` | Một handler nhận nhiều đường dẫn |
| `params` | `@GetMapping(value="/search", params="view=full")` | Chọn handler theo query parameter |
| `headers` | `headers="X-Client=mobile"` | Chọn handler theo header |
| `consumes` | `consumes="application/json"` | Chọn handler theo media type của request body |
| `produces` | `produces="application/hal+json"` | Giới hạn media type của response |
| `method` | `method=RequestMethod.GET` | Giới hạn HTTP method |

Các điều kiện này có vai trò khác nhau. Path pattern xác định những URI có thể đi đến handler. Các điều kiện `params`, `headers`, `consumes` và `produces` giúp Spring chọn handler hoặc representation phù hợp với request.

Một link HAL thông thường chứa relation và href. Chỉ riêng href không mô tả đầy đủ mọi điều kiện mapping, chẳng hạn header bắt buộc hoặc HTTP method cần dùng. Khi client cần biết cách tương tác, hãy bổ sung affordance hoặc metadata phù hợp với media type mà API hỗ trợ.

## 3. Tạo link khi mỗi phương thức có một mapping rõ ràng

Với Spring HATEOAS, `linkTo(methodOn(...))` là cách thông dụng để tạo href theo mapping của phương thức controller.

```java
Link self = linkTo(methodOn(OrderController.class)
        .getOrder(order.getId()))
        .withSelfRel();
```

`methodOn` tham chiếu đúng phương thức Java và truyền các giá trị như path variable hoặc request parameter. Spring HATEOAS đọc mapping tương ứng để xây link.

Ví dụ controller có một đường dẫn chuẩn và một alias riêng:

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

    @GetMapping("/legacy/{id}")
    public EntityModel<Order> getOrderLegacy(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }
}
```

Hai phương thức dùng chung service nhưng có mapping riêng. Vì vậy, assembler có thể tham chiếu chính xác phương thức cần công bố:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link canonical = linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel();

        Link legacy = linkTo(methodOn(OrderController.class)
                .getOrderLegacy(order.getId()))
                .withRel("legacy");

        return EntityModel.of(order, canonical, legacy);
    }
}
```

Trong ví dụ, `self` luôn trỏ đến đường dẫn chuẩn `/orders/{id}`. Relation mở rộng `legacy` công bố đường dẫn tương thích cũ nếu client hoặc hệ thống tích hợp còn cần dùng. Nếu không cần công bố alias, có thể bỏ link `legacy` và chỉ giữ `self`.

Các import liên quan:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Việc tách phương thức giúp ý định tạo link rõ ràng. Các phương thức có thể gọi chung một private method hoặc service để tránh lặp logic nghiệp vụ.

## 4. Khi một phương thức khai báo nhiều path pattern

Spring MVC cho phép một handler nhận nhiều đường dẫn:

```java
@GetMapping({"/{id}", "/legacy/{id}"})
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Cả `/orders/{id}` và `/orders/legacy/{id}` đều gọi cùng một phương thức. Cách này phù hợp khi hai URL chỉ là alias kỹ thuật và ứng dụng không cần phân biệt chúng ở tầng controller.

Tuy nhiên, lời gọi:

```java
linkTo(methodOn(OrderController.class).getOrder(orderId))
        .withSelfRel();
```

tham chiếu đến phương thức `getOrder`, không mang thông tin về path pattern nào đã được client sử dụng để đến handler. Vì thế, không nên xem `methodOn` như một cơ chế chọn alias theo request hiện tại. Nếu hợp đồng yêu cầu công bố một đường dẫn cụ thể, hãy tạo mapping riêng có phương thức tham chiếu riêng hoặc tạo URI tường minh theo cấu hình đã quản lý.

Đặc biệt, nếu muốn response luôn có `self` là URL chuẩn, hãy tham chiếu phương thức có mapping chuẩn. Đừng để lựa chọn alias phụ thuộc vào thứ tự khai báo các path pattern hay hành vi nội bộ mà client không thể biết.

## 5. Nhiều mapping phân biệt bằng query parameter

Một số API dùng query parameter để chọn biến thể xử lý:

```java
@GetMapping(value = "/search", params = "view=summary")
public CollectionModel<EntityModel<OrderSummary>> searchSummary(
        @RequestParam String view) {
    // ...
}

@GetMapping(value = "/search", params = "view=full")
public CollectionModel<EntityModel<Order>> searchFull(
        @RequestParam String view) {
    // ...
}
```

Hai handler có cùng path nhưng được chọn theo giá trị `view`. Khi tạo link đến một biến thể cụ thể, hãy tham chiếu đúng phương thức và cung cấp giá trị query parameter tương ứng:

```java
Link summary = linkTo(methodOn(OrderController.class)
        .searchSummary("summary"))
        .withRel("summary");

Link full = linkTo(methodOn(OrderController.class)
        .searchFull("full"))
        .withRel("full");
```

Trong trường hợp này, query parameter là một phần quan trọng của đích. Kiểm tra href được tạo để chắc chắn nó có `view=summary` hoặc `view=full` đúng với điều kiện mapping. Nếu điều kiện mapping dùng `params="view=summary"` nhưng phương thức không nhận tham số tương ứng, link builder không có giá trị đối số để thể hiện điều kiện đó; hãy tạo link tường minh hoặc thiết kế lại chữ ký phương thức sao cho điều kiện được thể hiện rõ.

Không nên công bố hai link có cùng href rồi kỳ vọng client tự suy ra biến thể nào cần dùng. Relation cần diễn đạt mục đích và href cần chứa đủ thông tin để request được định tuyến đúng.

## 6. Mapping phụ thuộc header và media type

Mapping có thể phụ thuộc header hoặc content negotiation:

```java
@GetMapping(value = "/{id}", produces = "application/hal+json")
public EntityModel<Order> getOrderHal(@PathVariable UUID id) {
    // ...
}

@GetMapping(value = "/{id}", produces = "application/json")
public Order getOrderJson(@PathVariable UUID id) {
    // ...
}
```

Hai handler có cùng path nhưng response format khác nhau. Trong trường hợp này, href có thể giống nhau; client chọn representation qua header `Accept`. Link builder chủ yếu giúp xác định URI theo mapping. Một link thông thường không tự bảo đảm client đã gửi đúng `Accept`.

Với các hành động có request body, điều kiện `consumes` và HTTP method cũng ảnh hưởng đến việc gọi endpoint. Nếu cần mô tả thao tác, hãy dùng affordance để công bố method và kiểu đầu vào; nếu cần định hướng representation, hãy ghi rõ media type mà client phải yêu cầu.

Không nên tạo hai URI khác nhau chỉ để phân biệt `produces` nếu hợp đồng API đã dùng content negotiation. Ngược lại, nếu hai biến thể là tài nguyên hoặc phiên bản hợp đồng khác nhau, URL versioned riêng có thể dễ hiểu hơn.

## 7. Nhiều phiên bản API

API có thể duy trì nhiều phiên bản trong cùng một thời gian:

```text
/v1/orders/42
/v2/orders/42
```

Nếu mỗi phiên bản có representation hoặc semantics khác nhau, nên tách mapping thành phương thức hoặc controller rõ ràng:

```java
@RestController
public class VersionedOrderController {

    @GetMapping("/v1/orders/{id}")
    public EntityModel<OrderV1> getV1(@PathVariable UUID id) {
        return v1Assembler.toModel(orderService.getRequiredV1(id));
    }

    @GetMapping("/v2/orders/{id}")
    public EntityModel<OrderV2> getV2(@PathVariable UUID id) {
        return v2Assembler.toModel(orderService.getRequiredV2(id));
    }
}
```

Mỗi assembler nên tạo `self` theo phiên bản mà representation đang đại diện. Client đang dùng hợp đồng v1 sẽ tiếp tục theo link v1; client dùng v2 sẽ nhận link v2.

Nếu hai phiên bản chỉ khác cách trình bày nhưng dùng chung một tài nguyên chuẩn, hãy quyết định rõ `self` đại diện cho URI nào theo hợp đồng. Không nên vô tình trả self link v1 trong response v2 chỉ vì assembler dùng chung mà không nhận biết phiên bản.

Với versioning qua header hoặc media type, URL có thể giống nhau và client chọn phiên bản bằng `Accept` hoặc header chuyên biệt. Khi đó, hãy kiểm thử content negotiation và mô tả media type/profile tương ứng; `methodOn` không tự thay thế quy tắc versioning qua header.

## 8. Kiểm thử link khi có nhiều mapping

Kiểm thử cần xác nhận link được tạo trỏ đến đúng mapping mong muốn, không chỉ xác nhận link tồn tại.

Với ví dụ đường dẫn chuẩn và alias:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/" + orderId)))
    .andExpect(jsonPath("$._links.legacy.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/legacy/" + orderId)));
```

Cũng cần kiểm tra truy cập alias:

```java
mockMvc.perform(get("/orders/legacy/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/" + orderId)));
```

Nếu mapping được phân biệt bằng query parameter, kiểm tra href có đúng giá trị điều kiện. Nếu mapping được phân biệt bằng `produces`, gửi các header `Accept` khác nhau và xác nhận đúng media type được trả về. Với versioned route, kiểm tra self link của từng phiên bản.

Một số tình huống nên có trong bộ kiểm thử:

1. Mapping chuẩn tạo self href chuẩn.
2. Alias trỏ đến cùng tài nguyên nhưng response vẫn công bố canonical self link theo hợp đồng.
3. Link alias chỉ xuất hiện khi API có chủ đích công bố alias.
4. Query parameter hoặc header cần thiết được thể hiện đúng trong request.
5. Mỗi phiên bản API tạo link đến đúng phiên bản representation.
6. Đường dẫn thực tế vẫn truy cập được sau khi mapping thay đổi.

## 9. Những lỗi thường gặp

**Dùng một method có nhiều path rồi kỳ vọng methodOn chọn alias theo request.** Lời gọi methodOn tham chiếu phương thức, không ghi nhớ URL client đã gọi. Tách phương thức khi cần công bố alias cụ thể.

**Dùng cùng relation cho nhiều ý nghĩa khác nhau.** Nếu một relation trỏ đến các đích có semantics khác nhau, client khó quyết định hành động. Chọn relation rõ ràng như `self`, `legacy`, `summary` hoặc `full` theo hợp đồng.

**Quên query parameter điều kiện.** Handler có thể chỉ được chọn khi có `view=summary`, nhưng href lại thiếu tham số. Hãy thể hiện điều kiện trong chữ ký phương thức và kiểm tra URI sau khi build.

**Nhầm produces với URL khác nhau.** Nếu chỉ khác representation, content negotiation thường là cơ chế phù hợp. Client cần gửi đúng `Accept`.

**Dùng assembler chung nhưng không biết phiên bản.** Self link có thể trỏ sang phiên bản khác. Tách assembler hoặc truyền rõ ngữ cảnh phiên bản khi hợp đồng yêu cầu.

**Dùng alias cũ làm self link ngoài ý muốn.** Chọn một canonical mapping rõ ràng và tạo self link bằng phương thức tương ứng.

## 10. Nguyên tắc thiết kế

- Tạo một phương thức controller riêng cho mỗi mapping cần được tham chiếu rõ ràng từ link builder.
- Dùng chung service hoặc private helper để tránh lặp logic nghiệp vụ giữa các alias.
- Xác định canonical URI cho mỗi representation và công bố bằng relation `self`.
- Dùng relation mở rộng có tài liệu khi cần công bố alias hoặc biến thể nghiệp vụ.
- Đưa query parameter cần thiết vào lời gọi link builder hoặc URI được tạo tường minh.
- Dùng content negotiation cho các representation khác nhau trên cùng URI khi phù hợp.
- Kiểm thử href, relation, header và phiên bản API như một phần hợp đồng hypermedia.

## Kết luận

Khi một controller có nhiều mapping, Spring HATEOAS cần được cung cấp tham chiếu rõ ràng đến endpoint mà API muốn công bố. `linkTo(methodOn(...))` tạo href từ phương thức và mapping, nhưng một lời gọi phương thức không cho biết client đã dùng alias nào nếu cùng handler khai báo nhiều path pattern. Tách mapping thành các phương thức riêng khi cần kiểm soát URL, xác định canonical self link, thể hiện điều kiện query/header phù hợp và kiểm thử từng biến thể sẽ giúp link luôn trỏ đúng hợp đồng API.

