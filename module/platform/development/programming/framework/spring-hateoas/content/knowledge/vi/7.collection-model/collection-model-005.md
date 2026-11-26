# CollectionModel generic là gì?

`CollectionModel<T>` là kiểu biểu diễn trong Spring HATEOAS dùng để đóng gói một tập hợp các phần tử kiểu `T` cùng những liên kết ở cấp collection. Tham số generic `T` mô tả **kiểu của mỗi phần tử trong collection**, không phải kiểu của cả danh sách. Ví dụ, `CollectionModel<OrderResponse>` chứa các DTO đơn hàng; `CollectionModel<EntityModel<OrderResponse>>` chứa các model đơn hàng mà mỗi item có thể mang link riêng.

CollectionModel giúp API thể hiện một collection như một tài nguyên hypermedia. Response có thể công bố link `self` cho collection, các link điều hướng phân trang, và các item bên trong có thể có link `self` hoặc link nghiệp vụ riêng. Nhờ đó client vừa duyệt được danh sách vừa khám phá được tài nguyên của từng phần tử.

Trong Spring HATEOAS, việc chọn đúng kiểu generic quyết định cấu trúc dữ liệu mà controller trả về và những liên kết mà mỗi phần tử có thể mang. Bài học này tập trung vào generic type của `CollectionModel`, cách tạo collection từ DTO hoặc `EntityModel`, tích hợp với assembler và controller, serialize HAL JSON, xử lý collection rỗng và kiểm thử hợp đồng.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa tham số `T` trong `CollectionModel<T>`.
- Phân biệt `CollectionModel<OrderResponse>` với `CollectionModel<EntityModel<OrderResponse>>`.
- Tạo collection bằng factory method và gắn link ở cấp collection.
- Kết hợp link ở cấp collection với link riêng của từng item.
- Dùng `RepresentationModelAssembler` để chuyển đổi một tập hợp tài nguyên.
- Hiểu cách collection được biểu diễn trong HAL và cách kiểm thử response.

## CollectionModel giải quyết vấn đề gì?

Một endpoint danh sách đơn hàng có thể trả trực tiếp `List<OrderResponse>`:

```java
@GetMapping
List<OrderResponse> all() {
    return orderService.findAll();
}
```

Response này có dữ liệu các đơn hàng, nhưng không có chỗ chuẩn hóa để đặt link điều hướng của collection. Client có thể phải tự biết URL trang kế tiếp, URL chi tiết của từng đơn hàng hoặc cách tìm tài nguyên liên quan.

Spring HATEOAS cung cấp `CollectionModel` để bọc tập hợp và thêm link:

```java
CollectionModel<OrderResponse> model = CollectionModel.of(
    orderService.findAll(),
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Trong trường hợp này, `T` là `OrderResponse`. Collection có link `self`; từng phần tử vẫn chỉ là DTO và chưa có link riêng. Nếu muốn từng đơn hàng có link `self`, hãy chọn `CollectionModel<EntityModel<OrderResponse>>`.

## Cấu trúc và ý nghĩa generic của CollectionModel

`CollectionModel<T>` kế thừa khả năng chứa link từ `RepresentationModel` và đại diện cho một tập hợp phần tử kiểu `T`. Có thể hình dung cấu trúc như sau:

```text
CollectionModel<T>
├── content: Collection<T>
│   ├── item 1: T
│   ├── item 2: T
│   └── item 3: T
└── links
    ├── self
    ├── next
    └── related
```

`content` chứa các phần tử; `links` ở cấp ngoài mô tả collection. Nếu `T` cũng là một representation model, mỗi phần tử có thể có thêm links của riêng nó.

### T là kiểu DTO

```java
CollectionModel<OrderResponse>
```

Collection chứa các đối tượng `OrderResponse`. Kiểu này phù hợp khi API cần cung cấp dữ liệu danh sách và link điều hướng chung cho collection, còn client không cần link riêng cho từng item hoặc link item được cung cấp theo cách khác.

### T là EntityModel

```java
CollectionModel<EntityModel<OrderResponse>>
```

Mỗi phần tử là một `EntityModel<OrderResponse>`, do đó từng đơn hàng có thể có link `self`, link đến khách hàng hoặc affordance theo trạng thái. Collection ngoài cùng vẫn có thể có link `self`, `next`, `prev` và các link khác.

Đây là cấu trúc thường dùng khi xây REST API hypermedia: collection có điều hướng ở cấp danh sách và từng item có điều hướng ở cấp tài nguyên.

### T là một model tùy chỉnh

```java
CollectionModel<OrderSummaryModel>
```

Nếu `OrderSummaryModel` kế thừa `RepresentationModel<OrderSummaryModel>`, mỗi phần tử có thể mang dữ liệu tổng hợp và links riêng. Cách này hữu ích khi representation item cần cấu trúc khác với một DTO được bọc bằng `EntityModel`.

## Phân biệt List, EntityModel và CollectionModel

Các kiểu này có mục đích khác nhau:

| Kiểu | Ý nghĩa | Link ở cấp ngoài | Link riêng cho item |
| --- | --- | --- | --- |
| `List<OrderResponse>` | Danh sách Java thông thường | Không có cơ chế link từ Spring HATEOAS | Không có |
| `EntityModel<OrderResponse>` | Một item cùng links | Có, cho item đó | Áp dụng cho chính item |
| `CollectionModel<OrderResponse>` | Collection các DTO | Có | Không có nếu DTO không mang links |
| `CollectionModel<EntityModel<OrderResponse>>` | Collection các item model | Có | Có, từng item |
| `PagedModel<EntityModel<OrderResponse>>` | Collection có metadata phân trang | Có | Có, từng item |

Không nên dùng `EntityModel<List<OrderResponse>>` chỉ để thêm link cho danh sách. Kiểu đó bọc cả danh sách như một content object duy nhất, không thể hiện rõ semantics của collection và không tạo model riêng cho từng item. Hãy dùng `CollectionModel<T>` cho tập hợp.

## Tạo CollectionModel bằng factory method

Spring HATEOAS cung cấp static factory `CollectionModel.of(...)`. Có thể truyền một `Iterable<T>` và các link ở cấp collection:

```java
List<OrderResponse> orders = orderService.findAll();

CollectionModel<OrderResponse> model = CollectionModel.of(
    orders,
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Factory method suy luận `T` từ kiểu phần tử. Trong ví dụ, `orders` là `List<OrderResponse>`, do đó kết quả là `CollectionModel<OrderResponse>`.

Có thể tạo collection mà chưa có link rồi bổ sung sau:

```java
CollectionModel<OrderResponse> model = CollectionModel.of(orders);
model.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Hoặc tạo collection rỗng:

```java
CollectionModel<OrderResponse> empty = CollectionModel.empty();
```

Khi không có biến đích để Java suy luận kiểu generic, có thể ghi rõ type witness:

```java
CollectionModel<EntityModel<OrderResponse>> empty =
    CollectionModel.<EntityModel<OrderResponse>>empty();
```

Có thể truyền link ngay cả khi collection rỗng:

```java
CollectionModel<OrderResponse> empty = CollectionModel.empty(
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Collection rỗng vẫn là một kết quả hợp lệ. API nên trả collection rỗng cùng link điều hướng phù hợp thay vì xem việc không có phần tử là lỗi server.

## Hiểu generic type qua ví dụ

Giả sử DTO đơn hàng:

```java
public record OrderResponse(Long id, String description, String status) {}
```

Và service trả về danh sách DTO:

```java
public interface OrderService {
    List<OrderResponse> findAll();
}
```

Nếu cần collection chỉ chứa DTO:

```java
List<OrderResponse> orders = orderService.findAll();

CollectionModel<OrderResponse> result = CollectionModel.of(
    orders,
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Nếu mỗi item cần link riêng, chuyển từng DTO thành `EntityModel` trước khi tạo collection:

```java
List<EntityModel<OrderResponse>> items = orders.stream()
    .map(order -> EntityModel.of(order,
        linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()))
    .toList();

CollectionModel<EntityModel<OrderResponse>> result = CollectionModel.of(
    items,
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Ở đây có hai tầng link:

- Link `self` của collection trỏ đến endpoint danh sách.
- Link `self` của mỗi `EntityModel` trỏ đến endpoint chi tiết của item tương ứng.

Kiểu generic thể hiện chính xác hai tầng đó. Nếu khai báo sai kiểu, compiler sẽ báo lỗi khi gán hoặc trả về giá trị không tương thích.

## Generic invariance và kiểu phần tử

Java generic là invariant. Điều đó có nghĩa `CollectionModel<EntityModel<OrderResponse>>` không phải subtype của `CollectionModel<RepresentationModel<?>>` chỉ vì `EntityModel<OrderResponse>` có quan hệ kế thừa với `RepresentationModel`.

Ví dụ, phép gán sau không hợp lệ:

```java
CollectionModel<EntityModel<OrderResponse>> entityModels = ...;
CollectionModel<RepresentationModel<?>> representations = entityModels; // Không biên dịch
```

Nếu một phương thức chỉ cần đọc các phần tử có kiểu con của một kiểu model, có thể cân nhắc wildcard ở vị trí tham số:

```java
void inspect(CollectionModel<? extends RepresentationModel<?>> models) {
    models.forEach(model -> System.out.println(model.getLinks()));
}
```

Wildcard `? extends` hữu ích khi tiêu thụ collection. Do generic invariance, nó không làm thay đổi kiểu trả về thực tế của collection và không cho phép thêm tùy ý một representation khác vào collection đầu vào.

Trong controller, nên khai báo kiểu cụ thể và rõ ràng, ví dụ `CollectionModel<EntityModel<OrderResponse>>`. Tránh raw type như `CollectionModel` vì nó làm mất kiểm tra kiểu tại compile time và dễ khiến lỗi chỉ xuất hiện khi serialize hoặc chạy chương trình.

## Link ở cấp collection và link ở cấp item

Một response collection có thể cần cả hai loại link. Link ngoài cùng mô tả cách điều hướng collection; link bên trong mô tả từng tài nguyên.

Ví dụ cấu trúc logic:

```text
CollectionModel<EntityModel<OrderResponse>>
├── collection links
│   ├── self -> /orders?page=0
│   └── next -> /orders?page=1
└── content
    ├── EntityModel<OrderResponse>
    │   └── self -> /orders/42
    └── EntityModel<OrderResponse>
        └── self -> /orders/43
```

Không nên nhầm link `next` của collection với link `self` của một item. Client theo `next` để lấy trang tiếp theo; client theo `self` của item để truy cập chi tiết tài nguyên đó.

### Link phân trang

Với collection lớn, server thường trả một trang dữ liệu và các link phân trang:

```java
CollectionModel<EntityModel<OrderResponse>> page =
    CollectionModel.of(items,
        linkTo(methodOn(OrderController.class).search("PAID", 0, 20))
            .withSelfRel(),
        linkTo(methodOn(OrderController.class).search("PAID", 1, 20))
            .withRel("next"));
```

Đây là ví dụ minh họa, giả định controller có method `search(status, page, size)`. Trong ứng dụng thực tế, chỉ công bố `next` khi còn trang kế tiếp và `prev` khi có trang trước. Server nên tính link dựa trên metadata phân trang thực tế, tránh tự tạo `next` cho trang cuối.

Khi cần metadata như số trang, kích thước trang, tổng phần tử hoặc tổng trang, `PagedModel<T>` là kiểu chuyên biệt hơn vì nó kế thừa `CollectionModel<T>` và bổ sung thông tin trang.

## Tích hợp CollectionModel vào controller

Controller có thể trả `CollectionModel<T>` trực tiếp. Ví dụ sau chuyển từng DTO thành `EntityModel` để mỗi item có link `self`, đồng thời gắn link `self` cho collection:

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

public interface OrderService {
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

Ví dụ giả định `OrderResponse` có phương thức `id()`, `OrderService.findById` trả về `Optional<OrderResponse>` và `findAll` trả về danh sách. `methodOn` cung cấp thông tin mapping để xây link; nó không gửi request thật đến controller.

Chữ ký `CollectionModel<EntityModel<OrderResponse>>` cho client và compiler biết rằng mỗi phần tử là một model có link. Nếu endpoint chỉ cần trả DTO và link collection, có thể rút gọn thành `CollectionModel<OrderResponse>`.

## Dùng RepresentationModelAssembler với CollectionModel

Khi có nhiều endpoint cùng chuyển đổi `OrderResponse` thành representation, nên tập trung quy tắc trong assembler:

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
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
    }
}
```

`RepresentationModelAssembler` cung cấp phương thức mặc định `toCollectionModel(...)`, có thể chuyển một `Iterable` đối tượng nguồn thành `CollectionModel` của các model đã tạo:

```java
CollectionModel<EntityModel<OrderResponse>> collection =
    assembler.toCollectionModel(orderService.findAll())
        .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Kết quả có link riêng cho từng item được tạo bởi `toModel`, đồng thời có link ở cấp collection được thêm sau đó. Controller có thể trả collection này trực tiếp.

Assembler có thể thêm các link nghiệp vụ theo trạng thái của từng item. Ví dụ, chỉ đơn hàng `PENDING_PAYMENT` mới có link `payment`. Việc tạo representation phản ánh trạng thái giúp client hiểu hành động nào được công bố cho từng tài nguyên. Server vẫn phải xác thực và kiểm tra điều kiện nghiệp vụ khi xử lý request.

## CollectionModel và HAL JSON

Khi được serialize theo HAL, các link ở cấp collection được đặt trong `_links`, còn các phần tử được nhúng dưới `_embedded` theo relation của collection.

Ví dụ khái quát cho `CollectionModel<EntityModel<OrderResponse>>`:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "description": "Bàn phím cơ",
        "status": "PENDING_PAYMENT",
        "_links": {
          "self": { "href": "https://api.example.com/orders/42" }
        }
      },
      {
        "id": 43,
        "description": "Chuột không dây",
        "status": "PAID",
        "_links": {
          "self": { "href": "https://api.example.com/orders/43" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "https://api.example.com/orders" }
  }
}
```

Trong ví dụ:

- `_embedded.orders` chứa các phần tử trong collection.
- Mỗi phần tử là một `EntityModel` nên có `_links.self` riêng.
- `_links.self` ở cấp ngoài trỏ đến collection.
- Relation `orders` là tên relation dùng để biểu diễn phần tử được nhúng; tên cụ thể phụ thuộc cấu hình relation provider và loại tài nguyên.

Nếu dùng `CollectionModel<OrderResponse>`, các item nhúng chỉ chứa thuộc tính DTO, không có link riêng trừ khi chính kiểu content có khả năng biểu diễn link. HAL JSON thường được trả với media type `application/hal+json`; client nên gửi `Accept` phù hợp và kiểm tra content type response.

## Collection rỗng và generic type

Collection không có phần tử vẫn là một collection hợp lệ. Service có thể trả danh sách rỗng khi không có đơn hàng phù hợp điều kiện lọc. Controller có thể trả `CollectionModel.empty()` và vẫn cung cấp link `self` hoặc link quay lại collection gốc.

Khi tạo collection rỗng, kiểu generic có thể cần được chỉ rõ để tránh Java suy luận thành `Object`, nhất là khi dùng `var` hoặc truyền qua nhiều phương thức:

```java
CollectionModel<EntityModel<OrderResponse>> empty =
    CollectionModel.<EntityModel<OrderResponse>>empty(
        linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Khi cần relation của phần tử nhúng trong HAL mà collection rỗng, serializer không thể suy luận loại item từ một phần tử thực tế. Spring HATEOAS có hỗ trợ fallback type cho collection model trong những tình huống cần thông tin kiểu để xác định relation. Với collection chứa DTO, có thể khai báo kiểu dự phòng như sau:

```java
Link selfLink = linkTo(methodOn(OrderController.class).all()).withSelfRel();

CollectionModel<OrderResponse> empty = CollectionModel.<OrderResponse>empty(selfLink)
    .withFallbackType(OrderResponse.class);
```

Hãy khai báo fallback type khi ứng dụng cần ổn định tên relation của `_embedded` ở cả response có phần tử và response rỗng, đồng thời kiểm thử serialization trên phiên bản Spring HATEOAS đang dùng.

Không nên trả `null` thay cho collection rỗng. `null` làm client khó phân biệt “không có phần tử” với “không có representation”, trong khi collection rỗng có cấu trúc rõ ràng và vẫn có thể mang links.

## CollectionModel và PagedModel

`CollectionModel<T>` biểu diễn một tập hợp cùng links. Nó không bắt buộc phải có metadata phân trang. `PagedModel<T>` là kiểu chuyên biệt cho kết quả phân trang, bổ sung metadata như số phần tử trong trang, số trang và kích thước trang.

| Nhu cầu | Kiểu phù hợp |
| --- | --- |
| Danh sách nhỏ, không phân trang | `CollectionModel<T>` |
| Danh sách có link điều hướng nhưng không cần metadata page | `CollectionModel<T>` |
| Danh sách có page number, page size, total elements và total pages | `PagedModel<T>` |
| Trang kết quả có item links | `PagedModel<EntityModel<T>>` |

Đừng tự thêm các trường `page`, `size`, `total` vào DTO item chỉ để mô tả phân trang. Metadata đó thuộc collection hoặc page representation, không thuộc từng tài nguyên đơn lẻ.

## Kiểm thử CollectionModel

Kiểm thử collection cần xác minh cấu trúc và link ở cả hai cấp. Một response có thể có đúng số item nhưng thiếu link `self`, hoặc item có dữ liệu đúng nhưng mất link `self`.

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
class OrderCollectionControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void collectionContainsItemsAndNavigationLinks() throws Exception {
        mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._embedded.orders[0].id").exists())
            .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
    }
}
```

Test giả định collection có ít nhất một đơn hàng và relation nhúng được đặt tên `orders` trong cấu hình HAL của ứng dụng. Nếu tên relation được tùy biến, JSONPath cần theo tên thực tế.

Nên có thêm test cho collection rỗng:

```java
@Test
void emptyCollectionStillHasSelfLink() throws Exception {
    mockMvc.perform(get("/orders?status=UNKNOWN").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
}
```

Các kiểm tra khác nên bao gồm:

1. Mỗi item có đúng kiểu content và các trường được phép công bố.
2. Link collection trỏ đến collection phù hợp.
3. Link `self` của từng item trỏ đến đúng tài nguyên.
4. Link phân trang chỉ xuất hiện khi có trang tương ứng.
5. Collection rỗng vẫn trả representation hợp lệ và giữ các link cần thiết.
6. Relation của `_embedded` ổn định giữa collection có phần tử và collection rỗng.
7. Media type và content negotiation hoạt động theo hợp đồng API.

## Những sai lầm thường gặp

**Nghĩ T là kiểu của toàn bộ collection.** Trong `CollectionModel<T>`, `T` là kiểu của từng phần tử. Toàn bộ phần tử được chứa trong content collection.

**Dùng `CollectionModel<OrderResponse>` nhưng mong từng item có link riêng.** DTO thường không chứa link. Nếu cần link cho mỗi item, dùng `CollectionModel<EntityModel<OrderResponse>>` hoặc một model tùy chỉnh kế thừa `RepresentationModel`.

**Dùng `EntityModel<List<T>>` cho danh sách.** Kiểu này bọc một danh sách như một content object. `CollectionModel<T>` diễn đạt collection rõ ràng hơn và hỗ trợ link ở cấp collection.

**Chỉ thêm link cho collection mà quên link cho item.** Client có thể đi đến trang danh sách nhưng không có link chuẩn để mở từng tài nguyên. Xác định rõ nhu cầu điều hướng ở cả hai cấp.

**Dùng raw type hoặc generic quá rộng.** Raw type làm mất kiểm tra kiểu; khai báo kiểu cụ thể như `CollectionModel<EntityModel<OrderResponse>>` giúp hợp đồng rõ ràng và giảm lỗi runtime.

**Cho rằng collection rỗng là lỗi.** Không có phần tử là một kết quả bình thường. Trả collection rỗng cùng link phù hợp thay vì `null` hoặc lỗi server.

**Nhầm CollectionModel với PagedModel.** CollectionModel không tự cung cấp metadata phân trang. Khi cần thông tin trang, dùng PagedModel.

**Kiểm thử chỉ số lượng item.** Hợp đồng hypermedia còn có link collection, link item, relation nhúng và media type. Test cần xác minh những phần client dựa vào.

## Kết luận

`CollectionModel<T>` là representation cho một tập hợp, trong đó `T` là kiểu của từng phần tử. Chọn `CollectionModel<DTO>` khi item chỉ chứa dữ liệu; chọn `CollectionModel<EntityModel<DTO>>` khi từng item cần links riêng. Links ở cấp collection phục vụ điều hướng danh sách, còn links của item phục vụ truy cập từng tài nguyên.

Trong Spring HATEOAS, hãy dùng `CollectionModel.of(...)` hoặc `CollectionModel.empty(...)`, tạo item model bằng `EntityModel` hoặc assembler khi cần, rồi trả collection từ controller. Khi kiểm thử HAL, xác minh `_embedded`, link ở cấp ngoài, link của từng item, collection rỗng và media type. Khai báo generic rõ ràng giúp code an toàn kiểu và làm hợp đồng API dễ hiểu hơn.
