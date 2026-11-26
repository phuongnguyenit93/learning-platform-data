# EntityModel là gì?

`EntityModel<T>` là một kiểu mô hình biểu diễn trong Spring HATEOAS, dùng để bọc một đối tượng nội dung cùng các liên kết hypermedia của nó. Thay vì trả về một DTO đơn lẻ, controller có thể trả về `EntityModel<OrderResponse>` để response vừa chứa dữ liệu đơn hàng vừa chứa các liên kết như `self`, `orders` hoặc `payment`.

`EntityModel` giúp thực hiện một ý tưởng quan trọng của REST: response nên cung cấp các liên kết để client khám phá tài nguyên liên quan và bước tiếp theo. Client đọc nội dung để biết tài nguyên đang ở trạng thái nào, rồi đọc các link relation để biết có thể điều hướng đến đâu.

Trong module SPRING_HATEOAS, `EntityModel` là một trong những công cụ cốt lõi để tổ chức tài nguyên và xây dựng REST API có hypermedia. Bài học này giải thích cấu trúc của `EntityModel`, cách tạo và thêm link, cách trả model từ controller, cách dùng assembler, cách nó được biểu diễn thành HAL JSON và cách kiểm thử hợp đồng.

Sau bài học, bạn có thể:

- Giải thích vai trò của `EntityModel<T>` và hai phần chính là content cùng links.
- Phân biệt `EntityModel`, `RepresentationModel`, `CollectionModel` và `PagedModel`.
- Tạo `EntityModel` bằng factory method và bổ sung link bằng Spring HATEOAS.
- Tích hợp `EntityModel` vào controller và assembler.
- Hiểu response HAL JSON được tạo từ `EntityModel` như thế nào.
- Kiểm thử cả dữ liệu lẫn liên kết của representation.

## EntityModel giải quyết vấn đề gì?

Một controller thông thường có thể trả về DTO:

```java
public record OrderResponse(Long id, String description, String status) {}
```

Response này chứa dữ liệu đơn hàng, nhưng client vẫn có thể phải biết trước URL để xem chi tiết, quay lại danh sách hoặc thực hiện bước nghiệp vụ tiếp theo. Nếu URL bị thay đổi, những client đã tự ghép URL có thể phải cập nhật.

Spring HATEOAS cho phép bọc DTO bằng `EntityModel` và thêm liên kết có quan hệ rõ ràng:

```java
EntityModel<OrderResponse> model = EntityModel.of(order,
    linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
    linkTo(methodOn(OrderController.class).all()).withRel("orders"));
```

Khi được serialize theo HAL, response chứa dữ liệu đơn hàng cùng đối tượng `_links`. Client có thể tìm relation `self` để truy cập lại tài nguyên và `orders` để đi đến collection. Client sử dụng URI do server cung cấp thay vì tự tạo URI từ một mẫu đường dẫn.

`EntityModel` không tự quyết định nghiệp vụ hay quyền truy cập. Ứng dụng quyết định link nào cần xuất hiện, còn server vẫn phải kiểm tra xác thực, phân quyền và điều kiện nghiệp vụ khi nhận request.

## Cấu trúc của EntityModel

`EntityModel<T>` đại diện cho một tài nguyên đơn lẻ. Nó có hai phần khái niệm:

1. **Content:** đối tượng dữ liệu kiểu `T`, thường là DTO hoặc projection mà API muốn công bố.
2. **Links:** tập hợp các liên kết mô tả tài nguyên hiện tại và những tài nguyên hoặc chuyển tiếp liên quan.

Ví dụ với `EntityModel<OrderResponse>`:

```text
EntityModel<OrderResponse>
├── content
│   ├── id: 42
│   ├── description: "Bàn phím cơ"
│   └── status: "PENDING_PAYMENT"
└── links
    ├── self      -> /orders/42
    └── orders    -> /orders
```

Kiểu generic `T` cho biết loại đối tượng được bọc. Vì vậy, `EntityModel<OrderResponse>` biểu thị một nội dung kiểu `OrderResponse`; `EntityModel<CustomerResponse>` biểu thị một nội dung kiểu `CustomerResponse`. Việc dùng generic giúp compiler kiểm tra kiểu và giúp chữ ký controller thể hiện rõ dạng dữ liệu được trả về.

`EntityModel` kế thừa khả năng chứa link từ `RepresentationModel`. Bạn có thể tạo model với một content, sau đó thêm một hoặc nhiều `Link`. Các phương thức thường dùng gồm:

- `EntityModel.of(content)` tạo model với content.
- `EntityModel.of(content, links...)` tạo model với content và các link ban đầu.
- `add(link)` thêm một link sau khi tạo model.
- `getContent()` truy cập content trong Java.
- `getLinks()` truy cập tập hợp link trong Java.

Đối tượng `EntityModel` là mô hình biểu diễn trong tầng web. Nó không phải entity của JPA và không thay thế entity trong persistence layer.

## EntityModel khác gì với các model khác?

Spring HATEOAS cung cấp nhiều kiểu model để diễn đạt các dạng tài nguyên khác nhau:

| Kiểu model | Dùng cho | Ví dụ |
| --- | --- | --- |
| `RepresentationModel<TSelf>` | Lớp cơ sở cho một representation tùy chỉnh có links; `TSelf` là kiểu model cụ thể | `OrderModel extends RepresentationModel<OrderModel>` |
| `EntityModel<T>` | Một đối tượng content cùng links | Một đơn hàng và các link của nó |
| `CollectionModel<T>` | Một collection các model hoặc phần tử cùng links của collection | Danh sách đơn hàng |
| `PagedModel<T>` | Collection có thông tin phân trang | Một trang kết quả tìm kiếm |

### Khi nào dùng EntityModel?

Dùng `EntityModel<T>` khi response đại diện cho một tài nguyên đơn lẻ và bạn muốn gắn links vào đối tượng đó mà không cần định nghĩa một lớp model mới. Đây là lựa chọn thuận tiện cho các DTO hoặc projection đơn giản.

Ví dụ:

```java
EntityModel<OrderResponse> orderModel = EntityModel.of(orderResponse)
    .add(linkTo(methodOn(OrderController.class)
        .one(orderResponse.id())).withSelfRel());
```

### Khi nào dùng RepresentationModel?

Dùng `RepresentationModel` khi muốn định nghĩa một lớp biểu diễn riêng có thêm thuộc tính ngoài một content object đơn giản, hoặc muốn kiểm soát rõ cấu trúc representation. Tham số generic của nó là kiểu model cụ thể (self type), không phải kiểu content được bọc như trong `EntityModel<T>`.

```java
public class OrderSummaryModel extends RepresentationModel<OrderSummaryModel> {

    private final Long id;
    private final String status;
    private final int itemCount;

    public OrderSummaryModel(Long id, String status, int itemCount) {
        this.id = id;
        this.status = status;
        this.itemCount = itemCount;
    }

    public Long getId() { return id; }
    public String getStatus() { return status; }
    public int getItemCount() { return itemCount; }
}
```

Lớp này tự định nghĩa các thuộc tính và vẫn có thể nhận link bằng `add(...)`. Generic parameter trong `RepresentationModel<OrderSummaryModel>` thể hiện kiểu model mà các thao tác fluent trả về.

### Khi nào dùng CollectionModel hoặc PagedModel?

Không nên bọc toàn bộ danh sách vào một `EntityModel<List<OrderResponse>>` chỉ vì response có nhiều phần tử. `EntityModel` biểu diễn một content object. Đối với tập hợp, dùng `CollectionModel` hoặc `PagedModel`:

```java
CollectionModel<EntityModel<OrderResponse>> orders =
    CollectionModel.of(orderModels,
        linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

`CollectionModel` có thể chứa link ở cấp collection, trong khi từng `EntityModel` trong collection có link riêng của item. `PagedModel` phù hợp khi cần biểu diễn metadata phân trang cùng các link như `first`, `prev`, `self`, `next` và `last`.

## Tạo EntityModel bằng factory method

Spring HATEOAS cung cấp static factory `EntityModel.of(...)`. Cách đơn giản nhất là truyền content:

```java
OrderResponse order = new OrderResponse(42L, "Bàn phím cơ", "PENDING_PAYMENT");

EntityModel<OrderResponse> model = EntityModel.of(order);
```

Model hiện đã bọc content nhưng chưa có link. Có thể thêm link bằng `add`:

```java
model.add(linkTo(methodOn(OrderController.class)
    .one(order.id())).withSelfRel());
```

Hoặc tạo model với link ngay từ đầu:

```java
EntityModel<OrderResponse> model = EntityModel.of(order,
    linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
    linkTo(methodOn(OrderController.class).all()).withRel("orders"));
```

Trong ví dụ:

- `linkTo(...)` bắt đầu xây link dựa trên mapping của controller.
- `methodOn(...)` tạo lời gọi mô phỏng để Spring HATEOAS xác định method mapping và các tham số URI.
- `withSelfRel()` gắn relation chuẩn `self`.
- `withRel("orders")` gắn relation có tên `orders`.

`methodOn` không gửi HTTP request và không thực thi nghiệp vụ của method controller như một lần gọi API thật. Nó cung cấp thông tin method để link builder suy ra mapping.

## Xây link cho EntityModel

Links là phần làm cho `EntityModel` trở thành representation có khả năng điều hướng. Một link thường có URI đích và relation mô tả ý nghĩa của link đó.

### Self link

Self link trỏ đến chính tài nguyên hiện tại:

```java
Link selfLink = linkTo(methodOn(OrderController.class)
    .one(order.id())).withSelfRel();
```

Một item thường nên có `self` để client có thể truy cập lại tài nguyên. URI được tạo từ mapping và tham số method, nhờ đó khi controller đổi mapping, link builder sẽ phản ánh mapping mới.

### Link đến collection hoặc tài nguyên liên quan

Một item có thể liên kết đến collection hoặc tài nguyên liên quan:

```java
Link ordersLink = linkTo(methodOn(OrderController.class)
    .all()).withRel("orders");

Link customerLink = linkTo(methodOn(CustomerController.class)
    .one(order.customerId())).withRel("customer");
```

Tên relation phải có semantics rõ ràng và được giữ ổn định. Với relation riêng của API, nên dùng một quy ước nhất quán và có tài liệu mô tả. Client nên chọn link theo relation thay vì dựa vào thứ tự link trong JSON.

### Link theo trạng thái nghiệp vụ

Không phải mọi hành động đều khả dụng với mọi tài nguyên. Ví dụ, đơn hàng ở trạng thái `PENDING_PAYMENT` có thể cung cấp link thanh toán, trong khi đơn hàng `PAID` không nên công bố link đó nữa.

```java
EntityModel<OrderResponse> toModel(OrderResponse order) {
    EntityModel<OrderResponse> model = EntityModel.of(order,
        linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
        linkTo(methodOn(OrderController.class).all()).withRel("orders"));

    if (order.status().equals("PENDING_PAYMENT")) {
        model.add(linkTo(methodOn(PaymentController.class)
            .pay(order.id())).withRel("payment"));
    }

    return model;
}
```

Đoạn mã minh họa cách công bố link theo trạng thái. Trong ứng dụng thực tế, nên dùng enum hoặc quy tắc miền nghiệp vụ thay cho chuỗi trạng thái tùy ý, đồng thời tính đến quyền của người dùng và các điều kiện khác. Link vắng mặt giúp client hiểu hành động không được công bố trong ngữ cảnh hiện tại, nhưng không thay thế kiểm tra quyền và trạng thái ở server khi nhận request.

### Link có query parameter

Với endpoint có tham số query, Spring HATEOAS hỗ trợ xây URI từ method mapping và các tham số tương ứng. Ví dụ, nếu controller có `search(String status, int page)`, có thể truyền các giá trị khi dùng `methodOn`:

```java
linkTo(methodOn(OrderController.class)
    .search("PAID", 0)).withRel("paid-orders");
```

Chữ ký method và annotation mapping quyết định tham số nào thuộc path, query hoặc request. Không nên tự nối chuỗi URL từ đầu vào người dùng vì có thể làm sai encoding hoặc cấu trúc URI.

## Tích hợp EntityModel vào controller

Controller có thể trả trực tiếp `EntityModel<T>`. Spring MVC xử lý kết quả trả về và Spring HATEOAS hỗ trợ serialize model thành representation hypermedia theo media type được chọn.

Ví dụ một controller đơn hàng:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

interface OrderService {
    Optional<OrderResponse> findById(Long id);
    List<OrderResponse> findAll();
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> one(@PathVariable Long id) {
        OrderResponse order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderResponse>> all() {
        List<EntityModel<OrderResponse>> items = orderService.findAll().stream()
            .map(order -> EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()))
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Ví dụ giả định `OrderService.findById` trả về `Optional<OrderResponse>`, `findAll` trả về danh sách và DTO `OrderResponse` có phương thức `id()`. Endpoint chi tiết trả về `EntityModel<OrderResponse>`; endpoint collection trả về `CollectionModel<EntityModel<OrderResponse>>`. Mỗi item có self link, còn collection có self link riêng.

Để sử dụng Spring HATEOAS trong Spring Boot, thêm dependency `spring-boot-starter-hateoas` phù hợp với phiên bản Spring Boot của dự án. Starter tích hợp các thành phần HATEOAS và hỗ trợ cấu hình chuyển đổi representation. Khi client gửi `Accept: application/hal+json`, ứng dụng có thể trả biểu diễn HAL JSON.

## Dùng RepresentationModelAssembler để tạo EntityModel

Nếu nhiều endpoint cùng trả một loại tài nguyên, việc tạo link lặp lại trong controller sẽ khó duy trì. `RepresentationModelAssembler<T, D>` cung cấp một điểm tập trung để chuyển đối tượng nguồn thành representation model.

Ví dụ:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderResponse, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(OrderResponse order) {
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

Controller dùng assembler:

```java
private final OrderModelAssembler assembler;

@GetMapping("/{id}")
EntityModel<OrderResponse> one(@PathVariable Long id) {
    OrderResponse order = orderService.findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    return assembler.toModel(order);
}
```

Assembler giúp:

- Giữ cách tạo `self` và relation nhất quán giữa các endpoint.
- Tách logic xây representation khỏi logic điều phối request trong controller.
- Dễ bổ sung link theo trạng thái, quyền hoặc quan hệ tài nguyên.
- Tái sử dụng cách chuyển đổi cho item trong collection và các response khác.

Assembler nên tập trung vào việc chuyển đổi đối tượng nguồn thành model. Các quy tắc nghiệp vụ quan trọng như có được thanh toán hay không vẫn cần được xác định bởi domain/service và được kiểm tra lại khi thực hiện hành động.

## EntityModel được serialize thành HAL JSON

Khi Spring HATEOAS serialize một `EntityModel<OrderResponse>` theo HAL, content được đưa vào phần dữ liệu chính và các liên kết được đưa vào `_links`.

Ví dụ response khái quát cho `GET /orders/42`:

```json
{
  "id": 42,
  "description": "Bàn phím cơ",
  "status": "PENDING_PAYMENT",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    }
  }
}
```

Trong HAL:

- Các thuộc tính của content được serialize thành các thuộc tính của resource object.
- `_links` chứa các liên kết theo relation.
- `href` là URI đích mà client có thể theo.
- `self` thường xác định URI của tài nguyên hiện tại.

Client có thể thương lượng media type bằng header `Accept`. Với HAL JSON, media type là `application/hal+json`. Không nên giả định mọi endpoint đều trả HAL nếu ứng dụng chưa cấu hình hoặc không hỗ trợ media type đó.

Nếu cùng relation có nhiều link, HAL có thể biểu diễn một hoặc nhiều đối tượng link tùy số lượng. Client nên tuân theo cấu trúc media type thay vì giả định relation luôn có một chuỗi `href` đơn lẻ.

## Chọn content phù hợp để bọc

`EntityModel<T>` có thể bọc nhiều loại đối tượng Java, nhưng content được trả ra là một phần của hợp đồng API. Vì vậy, cần chọn kiểu dữ liệu có chủ đích.

### Ưu tiên DTO hoặc projection cho API công khai

Không nên mặc định bọc trực tiếp JPA entity rồi trả ra client. Entity persistence có thể chứa:

- Quan hệ hai chiều gây vòng lặp serialize.
- Thuộc tính nội bộ không nên công bố.
- Lazy association khiến serialize kích hoạt truy vấn ngoài dự kiến.
- Cấu trúc phụ thuộc schema cơ sở dữ liệu.
- Dữ liệu nhạy cảm hoặc thông tin chỉ dùng cho nghiệp vụ nội bộ.

Thay vào đó, tạo DTO hoặc projection chứa đúng các trường API cần công bố, rồi bọc DTO bằng `EntityModel`:

```java
public record OrderResponse(Long id, String description, String status) {}

EntityModel<OrderResponse> model = EntityModel.of(orderResponse, selfLink);
```

DTO giúp tách hợp đồng HTTP khỏi mô hình lưu trữ và cho phép thay đổi entity nội bộ mà không làm response thay đổi ngoài dự kiến.

### Khi cần thêm thuộc tính ở cấp representation

Nếu representation cần các thuộc tính tổng hợp không nằm gọn trong một content DTO, hãy cân nhắc tạo một lớp riêng kế thừa `RepresentationModel`. Cách này hữu ích khi cấu trúc response cần được kiểm soát rõ, hoặc khi muốn thể hiện nhiều nhóm thông tin có ý nghĩa.

Không nên tạo nhiều lớp wrapper chỉ để thêm một hoặc hai link. Với một đối tượng content đơn giản và các link thông thường, `EntityModel` thường là đủ.

## Kiểm thử EntityModel và hợp đồng HAL

Kiểm thử controller trả `EntityModel` nên xác minh cả content lẫn links. Chỉ kiểm tra `200 OK` chưa đủ vì response có thể mất `self` hoặc relation mà client phụ thuộc.

Ví dụ với Spring MVC Test:

```java
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
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderResponseContainsContentAndLinks() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists());
    }
}
```

Test giả định dữ liệu đơn hàng mã 42 đã được chuẩn bị trong môi trường test và controller dùng HAL. Có thể mở rộng test để xác minh:

1. Content có đúng các thuộc tính được công bố và không lộ trường nội bộ.
2. `self.href` trỏ đến đúng item.
3. Relation `orders` trỏ đến collection phù hợp.
4. Link nghiệp vụ xuất hiện hoặc vắng mặt đúng theo trạng thái.
5. Request yêu cầu media type không được hỗ trợ sẽ có phản hồi phù hợp với cấu hình content negotiation.
6. ID không tồn tại trả `404 Not Found`.
7. Người dùng không có quyền không thể truy cập tài nguyên chỉ bằng cách thay ID.

Với assembler, có thể viết unit test gọi `toModel(...)` và kiểm tra content cùng các relation được tạo. Test ở tầng controller vẫn cần thiết để xác minh serialization HAL thực tế.

## Những sai lầm thường gặp

**Nhầm EntityModel với JPA Entity.** `EntityModel` là wrapper cho representation và link ở tầng web. JPA entity thuộc tầng persistence và có vòng đời, quan hệ cùng mục đích khác.

**Chỉ thêm content mà quên links.** Model có thể serialize dữ liệu đúng nhưng chưa hỗ trợ điều hướng nếu không có link cần thiết. Hãy xác định relation mà client cần và thêm chúng vào model.

**Dùng EntityModel để bọc cả collection.** `EntityModel<List<T>>` không thể hiện rõ semantics collection. Hãy dùng `CollectionModel` hoặc `PagedModel` cho tập hợp.

**Để controller tự xây link bằng chuỗi URL.** Nối chuỗi thủ công dễ tạo lỗi và gắn code vào cấu trúc path. Dùng `linkTo`, `methodOn` hoặc assembler để tạo link theo mapping.

**Coi link là quyền truy cập.** Link chỉ công bố một điều khiển trong response. Server vẫn phải kiểm tra quyền và điều kiện nghiệp vụ ở mỗi request.

**Trả trực tiếp entity persistence.** Điều này có thể lộ dữ liệu nội bộ hoặc tạo lỗi serialize. Ưu tiên DTO/projection phù hợp với hợp đồng API.

**Kiểm thử chỉ status code.** Hợp đồng hypermedia bao gồm content, media type và relation. Test nên xác minh các phần mà client sử dụng.

## Kết luận

`EntityModel<T>` là wrapper của Spring HATEOAS dành cho một đối tượng content cùng các link hypermedia. Nó cho phép controller trả một tài nguyên vừa có dữ liệu vừa có khả năng điều hướng. `RepresentationModel` phù hợp để xây model tùy chỉnh, còn `CollectionModel` và `PagedModel` dành cho collection và kết quả phân trang.

Trong ứng dụng Spring, hãy chọn DTO phù hợp làm content, dùng `linkTo` và `methodOn` hoặc `RepresentationModelAssembler` để tạo link, rồi trả `EntityModel` từ controller. Khi kiểm thử, xác minh cả dữ liệu, media type và các relation quan trọng. Cách tổ chức này giúp client khám phá tài nguyên theo hợp đồng hypermedia và giảm phụ thuộc vào cấu trúc URL nội bộ.
