# Kiểm thử embedded resource

Trong Spring HATEOAS, **embedded resource** là tài nguyên liên quan được gửi kèm bên trong representation hiện tại. Với HAL JSON, các tài nguyên nhúng thường nằm dưới `_embedded`; các liên kết điều hướng nằm dưới `_links`. Một response collection đơn hàng có thể nhúng các đơn hàng trong `_embedded.orders`, trong khi mỗi đơn hàng vẫn có link `self` riêng.

Kiểm thử embedded resource cần xác nhận nhiều hơn việc response có JSON hợp lệ. Test phải kiểm tra đúng relation, đúng số lượng phần tử, dữ liệu được công bố, link của từng phần tử, media type và hành vi khi collection rỗng hoặc tài nguyên liên quan không được nhúng. Đây là cách bảo vệ hợp đồng hypermedia khi DTO, assembler, relation hoặc cấu hình serialization thay đổi.

## Embedded resource và link khác nhau thế nào?

HAL phân biệt dữ liệu được nhúng và liên kết tới dữ liệu:

| Thành phần | Vị trí HAL | Ý nghĩa | Kiểm thử cần xác nhận |
| --- | --- | --- | --- |
| Embedded resource | `_embedded` | Nội dung tài nguyên liên quan được gửi trong response hiện tại | Relation, dữ liệu và cấu trúc phần tử |
| Link | `_links` | URI để client có thể điều hướng hoặc truy cập tài nguyên | Relation, `href` và thuộc tính link như `templated` nếu có |

Ví dụ, `_embedded.orders` có thể chứa dữ liệu của các đơn hàng; mỗi phần tử có `_links.self.href` để client truy cập riêng đơn hàng đó. Nếu response chỉ có `_links.orders`, server mới công bố đường dẫn tới collection; nội dung collection chưa được nhúng trong response hiện tại.

Nhúng tài nguyên giúp giảm số request khi client cần dữ liệu liên quan ngay lập tức, nhưng làm response lớn hơn và tạo một bản biểu diễn tại thời điểm server trả lời. Link phù hợp khi client chỉ cần biết cách truy cập tài nguyên liên quan hoặc dữ liệu đó có thể được tải khi cần.

## Relation quyết định tên trong `_embedded`

Spring HATEOAS dùng `@Relation` để định nghĩa tên relation cho một loại representation. `itemRelation` là tên một phần tử; `collectionRelation` là tên tập hợp khi nhiều phần tử được nhúng.

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
```

Khi collection chứa `EntityModel<OrderRepresentation>`, HAL có thể dùng `orders` làm tên relation trong `_embedded`:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "8f2c6b0e-3f17-4c84-ae6c-8c0a7c0a6a01",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/8f2c6b0e-3f17-4c84-ae6c-8c0a7c0a6a01"
          }
        }
      }
    ]
  }
}
```

Tên `orders` là một phần của hợp đồng representation. Nếu đổi `collectionRelation` thành `purchaseOrders`, đường dẫn JSON mà client sử dụng cũng đổi từ `$._embedded.orders` sang `$._embedded.purchaseOrders`. Vì vậy, test relation giúp phát hiện thay đổi hợp đồng sớm.

Không nhầm `@Relation` với `LinkRelation`. `@Relation` định nghĩa tên dùng cho item/collection nhúng; `LinkRelation` định nghĩa ý nghĩa của một link trong `_links`. Một API có thể dùng `orders` trong `_embedded` và đồng thời có link `orders` hoặc `self` trong `_links`, nhưng hai vị trí phục vụ hai mục đích khác nhau.

## Chuẩn bị assembler và collection model

Assembler thường chuyển domain object thành `EntityModel` và gắn link cho từng phần tử:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }
}
```

Controller dùng assembler để tạo collection representation:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(produces = "application/hal+json")
    CollectionModel<EntityModel<OrderRepresentation>> all() {
        List<EntityModel<OrderRepresentation>> items = orderService.findAll()
            .stream()
            .map(assembler::toModel)
            .collect(Collectors.toList());

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

`Order`, `OrderService` và các kiểu nghiệp vụ là thành phần của ứng dụng minh họa. Ví dụ dùng `Collectors.toList()` để tương thích với các phiên bản Java trước khi có `Stream.toList()`. `CollectionModel` đại diện cho collection; từng `EntityModel` giữ dữ liệu và self link riêng. Khi serialize HAL JSON, relation collection lấy theo metadata relation của kiểu representation.

## Kiểm thử bằng MockMvc

Với Spring MVC, MockMvc kiểm thử request/response qua hạ tầng Spring MVC mà không cần khởi động HTTP server thật. Một integration test có thể dùng `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`; nếu chỉ dùng `@WebMvcTest`, cần cung cấp mock hoặc bean cho service, assembler và các dependency mà controller cần.

Ví dụ kiểm tra collection được nhúng:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderEmbeddedResourceTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void embedsOrdersWithTheirSelfLinks() throws Exception {
        mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath("$._embedded.orders", hasSize(2)))
            .andExpect(jsonPath("$._embedded.orders[0].id").exists())
            .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
                .value(endsWith("/orders/" + FIXTURE_ORDER_ID)))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

`FIXTURE_ORDER_ID` là hằng số ID của đơn hàng được nạp trong test fixture; ứng dụng cần bảo đảm thứ tự fixture ổn định nếu kiểm tra phần tử `[0]`. Nếu thứ tự collection không được quy định, nên tìm phần tử theo ID bằng JsonPath hoặc sắp xếp dữ liệu test thay vì phụ thuộc thứ tự ngẫu nhiên.

Test này xác nhận các điểm quan trọng: client yêu cầu HAL JSON, server trả đúng media type, relation `orders` tồn tại dưới `_embedded`, số phần tử đúng và phần tử có self link trỏ tới endpoint item. Có thể bổ sung kiểm tra các trường dữ liệu cụ thể và link collection-level như `search`, `create` hoặc `next` tùy hợp đồng.

## Kiểm thử relation và nội dung được công bố

Test nên kiểm tra tên relation rõ ràng, vì thay đổi annotation `@Relation` có thể làm client không tìm thấy embedded resource dù dữ liệu vẫn được trả về.

```java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.purchaseOrders").doesNotExist());
```

Trong test thực tế, chỉ giữ assertion về relation cũ hoặc relation mới phù hợp với contract. Ví dụ trên minh họa rằng API công bố `orders`; nó không công bố thêm tên khác ngoài hợp đồng.

Nên xác nhận response chỉ chứa trường được phép công bố. Ví dụ nếu entity có `internalCost`, `supplierSecret` hoặc trường audit nội bộ, test có thể xác nhận những trường đó không xuất hiện trong phần tử nhúng:

```java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders[0].internalCost").doesNotExist())
    .andExpect(jsonPath("$._embedded.orders[0].supplierSecret").doesNotExist());
```

Đây là kiểm thử hợp đồng dữ liệu và giảm nguy cơ vô tình serialize trực tiếp entity. Việc một trường không xuất hiện trong response không thay thế kiểm tra phân quyền ở service hoặc endpoint.

## Kiểm thử nested embedded resource

Một representation có thể nhúng tài nguyên liên quan nhiều cấp, ví dụ đơn hàng kèm khách hàng hoặc các dòng hàng. Khi API chủ ý công bố cấu trúc đó, test nên xác nhận cả relation ở từng cấp và nội dung cần thiết.

Ví dụ một HAL response minh họa:

```json
{
  "id": 42,
  "_embedded": {
    "customer": {
      "id": 7,
      "displayName": "Lan Nguyen"
    },
    "items": [
      { "productCode": "BK-01", "quantity": 2 }
    ]
  }
}
```

Nếu ứng dụng chọn cấu trúc nested như trên, test có thể kiểm tra:

```java
mockMvc.perform(get("/orders/42?projection=detail")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.customer.displayName")
        .value("Lan Nguyen"))
    .andExpect(jsonPath("$._embedded.items").isArray())
    .andExpect(jsonPath("$._embedded.items", hasSize(2)));
```

JSON và test trên chỉ minh họa hợp đồng nested mà ứng dụng có thể lựa chọn. Spring HATEOAS không tự nhúng mọi quan hệ JPA chỉ vì entity có association; ứng dụng phải chủ động tạo representation nhúng và kiểm soát độ sâu, dữ liệu được công bố. Nếu API chỉ cung cấp link `customer` trong `_links`, test đúng phải kiểm tra `_links.customer.href`, không tìm dữ liệu dưới `_embedded.customer`.

## Kiểm thử tài nguyên tùy chọn và collection rỗng

Không phải lúc nào tài nguyên liên quan cũng được nhúng. Có thể do quan hệ không tồn tại, quyền truy cập không cho phép, projection không yêu cầu hoặc API chỉ công bố link. Test cần phản ánh hợp đồng của endpoint:

```java
mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.customer").doesNotExist());
```

Nếu API không nhúng khách hàng trong trường hợp này, test có thể xác nhận embedded relation vắng mặt. Nếu API vẫn công bố link tới khách hàng, kiểm tra link riêng:

```java
mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.customer.href").exists());
```

Collection rỗng vẫn là một resource. Response có thể giữ link `self`, `search` và `create` dù không có phần tử. Cách serializer biểu diễn collection rỗng có thể khác nhau theo cấu hình và loại model; không nên mặc định `_embedded.orders` luôn là mảng rỗng nếu hợp đồng hoặc serializer không cam kết điều đó. Hãy kiểm tra link cấp collection và xác nhận nội dung rỗng theo định dạng thực tế mà ứng dụng công bố.

## Kiểm thử bằng WebTestClient cho WebFlux

Nếu controller dùng Spring WebFlux, `WebTestClient` là công cụ kiểm thử phù hợp. Nó có thể bind trực tiếp với ứng dụng hoặc test slice và xác nhận HAL response mà không cần viết test dựa trên MockMvc.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveOrderEmbeddedResourceTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void returnsEmbeddedOrders() {
        webTestClient.get()
            .uri("/orders")
            .accept(MediaTypes.HAL_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaTypes.HAL_JSON)
            .expectBody()
            .jsonPath("$._embedded.orders").isArray()
            .jsonPath("$._embedded.orders[0]._links.self.href").exists();
    }
}
```

Ví dụ dùng cho ứng dụng WebFlux có cấu hình test client và fixture chứa ít nhất một đơn hàng. Với controller MVC, dùng MockMvc; với controller WebFlux, dùng WebTestClient. Không trộn hai cơ chế kiểm thử nếu mục tiêu là xác nhận đúng stack HTTP của ứng dụng.

## Kiểm thử content negotiation và media type

Embedded resource là một phần của representation và cách serialize phụ thuộc media type. Client có thể gửi `Accept: application/hal+json`; server cần trả media type tương thích và cấu trúc HAL. Nếu endpoint hỗ trợ nhiều media type, nên kiểm thử riêng từng dạng vì một response JSON thường không có `_embedded` hoặc `_links` theo cấu trúc HAL.

Các điểm cần xác nhận:

- `Content-Type` tương thích với `application/hal+json` khi client yêu cầu HAL.
- Tên relation trong `_embedded` đúng với `@Relation` hoặc cấu hình relation provider.
- Link trong từng embedded resource được serialize dưới `_links`.
- Embedded resource lồng nhau chỉ xuất hiện khi API chủ động công bố.
- Client không nhận các trường domain nội bộ hoặc dữ liệu ngoài quyền truy cập.

Nếu test trả `406 Not Acceptable`, kiểm tra endpoint `produces`, dependency/cấu hình Spring HATEOAS và header `Accept`. Nếu response trả JSON thường, kiểm tra message converter và media type thực tế thay vì chỉ sửa JSONPath cho khớp.

## Kiểm thử thay đổi hợp đồng embedded resource

Tên relation và cấu trúc embedded là một phần hợp đồng API. Khi đổi `orders` thành `purchaseOrders`, bỏ một trường hoặc thay nested resource bằng link, client có thể cần thay đổi cách đọc response. Nên xem các thay đổi này như thay đổi hợp đồng và có test bảo vệ.

Một bộ kiểm thử tốt nên bao gồm:

1. Collection có nhiều phần tử: đúng relation, số lượng, dữ liệu và self link từng item.
2. Collection rỗng: link collection vẫn hợp lệ và body tuân theo contract rỗng.
3. Embedded relation tùy chọn: có và không có tài nguyên liên quan.
4. Nested embedded: đúng cấu trúc và độ sâu được công bố.
5. Media type: HAL JSON được thương lượng đúng.
6. Security: response không nhúng dữ liệu ngoài quyền của caller.
7. Serialization: link và relation xuất hiện đúng trong JSON thực tế.

Tránh kiểm tra toàn bộ JSON bằng một chuỗi snapshot quá dài nếu thứ tự thuộc tính không có ý nghĩa. Dùng JSONPath để xác nhận các phần có ý nghĩa của hợp đồng, và chỉ dùng snapshot khi cấu trúc tổng thể thực sự cần được bảo vệ.

## Lỗi thường gặp khi kiểm thử embedded resource

- **Kiểm tra nhầm `_links` thay cho `_embedded`:** link chỉ trỏ tới tài nguyên; nó không chứng minh nội dung đã được nhúng.
- **Dùng sai relation:** test tìm `$._embedded.order` trong khi collection relation được công bố là `orders`.
- **Bỏ qua media type:** response JSON thường không có cấu trúc HAL như test kỳ vọng.
- **Giả định thứ tự phần tử:** test dùng `[0]` dù collection không bảo đảm thứ tự.
- **Giả định collection rỗng luôn có mảng:** serializer có thể bỏ qua `_embedded` khi không có phần tử.
- **Nhúng quá sâu:** test buộc response mang toàn bộ cây quan hệ, làm tăng coupling và kích thước payload.
- **Không kiểm tra trường nhạy cảm:** serialize entity trực tiếp có thể làm lộ dữ liệu nội bộ.
- **Chỉ test assembler:** unit test assembler không xác nhận processor, message converter và HAL serializer cùng hoạt động trong HTTP response.

Kiểm thử embedded resource trong Spring HATEOAS cần xác nhận đúng relation, nội dung được nhúng, link của từng phần tử và media type thực tế. Kết hợp `@Relation`, assembler rõ ràng, MockMvc hoặc WebTestClient và JSONPath giúp bảo vệ hợp đồng hypermedia khi mô hình domain và cách tổ chức tài nguyên thay đổi.
