# CollectionModel là gì trong Spring HATEOAS?

Một API thường trả về danh sách tài nguyên, chẳng hạn danh sách đơn hàng, khách hàng hoặc sản phẩm. Nếu controller chỉ trả một `List<T>`, response chủ yếu mô tả các phần tử trong danh sách. Client có thể đọc dữ liệu nhưng không có một nơi rõ ràng để khám phá các liên kết ở cấp toàn bộ collection, ví dụ liên kết tới chính danh sách, trang tiếp theo hoặc thao tác tạo tài nguyên mới.

Spring HATEOAS cung cấp `CollectionModel<T>` để biểu diễn một tập hợp tài nguyên cùng các liên kết hypermedia ở cấp collection. Mỗi phần tử bên trong cũng có thể là một representation model và mang liên kết riêng. Nhờ đó, API có thể mô tả cả danh sách lẫn cách client tiếp tục điều hướng từ danh sách đến từng tài nguyên.

## 1. CollectionModel giải quyết điều gì?

Giả sử API quản lý đơn hàng có endpoint `GET /orders`. Một response dạng danh sách JSON đơn giản có thể trông như sau:

```json
[
  { "id": "42", "status": "PENDING", "total": 125000 },
  { "id": "43", "status": "SHIPPED", "total": 98000 }
]
```

Client có thể đọc các phần tử, nhưng cấu trúc này không có vị trí chuẩn để chứa liên kết `self` của collection, `next` để chuyển trang hoặc các liên kết điều hướng khác. Nếu client cần gọi trang kế tiếp, nó có thể phải tự ghép query string hoặc biết trước quy tắc URL của server.

Với `CollectionModel`, collection trở thành một representation hypermedia. Ở cấp collection, server có thể công bố:

- `self`: URI của chính collection.
- `next` và `prev`: điều hướng giữa các trang khi API có phân trang.
- `create` hoặc `search`: quan hệ nghiệp vụ do API định nghĩa nếu client cần khám phá khả năng đó.
- Các liên kết khác giúp client tiếp tục luồng công việc.

Mỗi phần tử trong collection cũng có thể mang `self`, `customer`, `cancel` hoặc những relation phù hợp với tài nguyên đó. Client có thể đi từ collection đến item rồi tiếp tục theo các liên kết trên item mà không phải tự suy ra đường dẫn.

## 2. CollectionModel là một representation model

`CollectionModel<T>` là kiểu của Spring HATEOAS dùng để bọc một tập hợp phần tử và các liên kết của collection. Nó kế thừa `RepresentationModel`, vì vậy có thể sử dụng các phương thức quản lý link như `add`, `getLinks`, `hasLink` và `getLink`.

Các thành phần cần phân biệt:

| Kiểu | Ý nghĩa | Phạm vi liên kết |
| --- | --- | --- |
| `List<T>` | Danh sách Java thông thường. | Không có API hypermedia riêng ở cấp danh sách. |
| `EntityModel<T>` | Bọc một đối tượng dữ liệu cùng các liên kết. | Một tài nguyên. |
| `CollectionModel<T>` | Bọc nhiều phần tử cùng các liên kết của collection. | Toàn bộ danh sách; từng phần tử có thể tự mang link. |
| `PagedModel<T>` | Biểu diễn collection có metadata phân trang. | Collection, trang và các liên kết điều hướng trang. |

`CollectionModel` không thay thế `List` trong mọi tình huống. Danh sách Java vẫn phù hợp cho dữ liệu nội bộ, kết quả service hoặc API không cần hypermedia. Hãy dùng `CollectionModel` khi response cần thể hiện collection như một tài nguyên có thể điều hướng.

## 3. Tạo CollectionModel cơ bản

Spring HATEOAS cung cấp phương thức tĩnh `CollectionModel.of(...)` để tạo model từ một tập hợp phần tử. Ví dụ, nếu đã có các model đơn hàng:

```java
List<OrderModel> orders = List.of(
        new OrderModel(UUID.fromString("00000000-0000-0000-0000-000000000042"), "PENDING"),
        new OrderModel(UUID.fromString("00000000-0000-0000-0000-000000000043"), "SHIPPED")
);

CollectionModel<OrderModel> collection = CollectionModel.of(orders);
```

Collection hiện chứa các phần tử nhưng chưa có liên kết ở cấp collection. Có thể thêm liên kết sau khi tạo:

```java
collection.add(Link.of("/orders", "self"));
```

Hoặc truyền link ngay khi khởi tạo:

```java
CollectionModel<OrderModel> collection = CollectionModel.of(
        orders,
        Link.of("/orders", "self")
);
```

Trong ứng dụng Spring MVC, nên tạo URI từ mapping của controller thay vì viết cố định đường dẫn:

```java
CollectionModel<OrderModel> collection = CollectionModel.of(
        orders,
        linkTo(methodOn(OrderController.class).all()).withSelfRel()
);
```

Ví dụ trên giả định controller có method `all()` ánh xạ tới collection đơn hàng. `linkTo` và `methodOn` giúp liên kết đi theo mapping của controller khi đường dẫn được thay đổi.

## 4. Phần tử bên trong collection có thể có liên kết riêng

Collection link và item link mô tả hai cấp điều hướng khác nhau. Liên kết `self` của collection trỏ tới danh sách; liên kết `self` của từng item trỏ tới một tài nguyên cụ thể.

Ví dụ, `OrderModel` kế thừa `RepresentationModel<OrderModel>`:

```java
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;

    public OrderModel(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

Khi tạo từng item, thêm liên kết `self` tương ứng:

```java
OrderModel first = new OrderModel(orderId, "PENDING");
first.add(linkTo(methodOn(OrderController.class).one(orderId)).withSelfRel());

CollectionModel<OrderModel> collection = CollectionModel.of(List.of(first));
collection.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Khi serialize thành HAL, response thường có cấu trúc khái quát như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders"
    }
  }
}
```

Trong ví dụ, `_links` ở ngoài cùng thuộc collection; `_links` bên trong mỗi item thuộc tài nguyên đơn hàng. Client có thể đọc relation `orders` trong `_embedded` để lấy danh sách, sau đó tìm `self` trên từng item.

## 5. Xác định relation cho collection

Trong HAL, các phần tử nhúng được nhóm dưới `_embedded` theo một relation. Tên relation cần ổn định để client có thể tìm collection item. Spring HATEOAS có annotation `@Relation` để tùy chỉnh tên relation của một loại representation.

Ví dụ:

```java
@Relation(value = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {
    // Thuộc tính và getter của model.
}
```

Với cấu hình này, collection có thể dùng relation `orders` cho danh sách và `order` cho item theo quy ước relation của model. Tên thực tế cần được xác minh qua response HAL của ứng dụng, đặc biệt khi dùng nhiều loại model hoặc cấu hình serialization riêng.

Đừng chọn relation chỉ dựa trên tên class Java. Hãy xem relation là một phần hợp đồng API: nó cần mô tả đúng loại tài nguyên, được dùng nhất quán và có ý nghĩa mà client có thể hiểu. Nếu đổi tên relation, client đang tìm tên cũ có thể không còn tìm thấy collection.

## 6. Chuyển đổi collection bằng RepresentationModelAssembler

Khi dữ liệu đầu vào là domain object, không nên để controller tự lặp qua danh sách rồi chuyển đổi từng phần tử. `RepresentationModelAssembler<T, D>` hỗ trợ chuyển một đối tượng thành model qua `toModel(...)` và chuyển nhiều đối tượng thành collection model qua `toCollectionModel(...)`.

Ví dụ assembler:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class).one(order.getId())).withSelfRel()
        );
    }
}
```

Controller có thể gọi assembler để chuyển cả collection:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        CollectionModel<EntityModel<OrderView>> model =
                assembler.toCollectionModel(service.findAll());

        model.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
        return model;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }
}
```

Trong ví dụ, assembler tạo liên kết cho từng đơn hàng; controller bổ sung liên kết `self` cho collection. Có thể chuyển phần tạo link collection sang một thành phần riêng nếu nhiều controller cần dùng chung quy tắc. Các kiểu `Order`, `OrderView`, `OrderService` và mapping là ví dụ thuộc ứng dụng.

## 7. Collection rỗng vẫn là một representation

Một collection có thể không chứa phần tử nào. Ví dụ người dùng mới chưa có đơn hàng hoặc kết quả tìm kiếm không có bản ghi phù hợp. Đây vẫn là kết quả hợp lệ của endpoint collection.

Có thể tạo collection rỗng bằng:

```java
CollectionModel<OrderModel> empty = CollectionModel.empty();
empty.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Liên kết `self` vẫn có ích dù danh sách không có item. Nếu API công bố quan hệ tạo mới hoặc tìm kiếm, các liên kết cấp collection phù hợp cũng có thể xuất hiện trong response rỗng.

Khi dùng HAL, cách serializer thể hiện collection rỗng có thể phụ thuộc thông tin kiểu và cấu hình relation. Phần `_embedded` có thể không xuất hiện khi không có phần tử. Vì vậy, client không nên giả định `_embedded` luôn tồn tại hoặc luôn có ít nhất một item. Client nên xử lý trường hợp không có phần tử và vẫn có thể đọc các liên kết cấp collection.

Với collection rỗng, hãy kiểm tra các điểm sau:

- Endpoint trả status và media type theo hợp đồng.
- Response vẫn có liên kết `self` hoặc các liên kết cấp collection cần thiết.
- Client xử lý được trường hợp `_embedded` không có hoặc danh sách rỗng.
- Không có liên kết điều hướng trang không hợp lệ như `next` khi không có trang tiếp theo.

## 8. CollectionModel và PagedModel

`CollectionModel` phù hợp với một tập hợp tài nguyên nói chung. Nếu kết quả được chia trang, `PagedModel<T>` cung cấp thêm metadata trang và các liên kết điều hướng phù hợp.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Trả danh sách tài nguyên không có thông tin trang | `CollectionModel<T>` |
| Trả danh sách có số trang hiện tại, kích thước trang và tổng số phần tử | `PagedModel<T>` |
| Bọc một tài nguyên riêng lẻ có liên kết | `EntityModel<T>` hoặc class kế thừa `RepresentationModel` |
| Trả dữ liệu nội bộ không cần hypermedia | `List<T>` hoặc kiểu collection Java phù hợp |

Không nên tự thêm các trường `page`, `size`, `totalElements` vào một `CollectionModel` rồi xem đó là phân trang hypermedia hoàn chỉnh. Nếu API cần metadata trang và các liên kết `first`, `prev`, `self`, `next`, `last`, hãy sử dụng mô hình phân trang phù hợp hoặc tích hợp với Spring Data theo cấu hình của dự án.

## 9. CollectionModel trong controller và content negotiation

Một controller có thể trả trực tiếp `CollectionModel`:

```java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
CollectionModel<EntityModel<OrderView>> all() {
    return assembler.toCollectionModel(service.findAll());
}
```

Trong một ứng dụng Spring Boot có Spring HATEOAS được cấu hình, model có thể được tuần tự hóa thành HAL. Client có thể gửi:

```http
GET /orders HTTP/1.1
Accept: application/hal+json
```

Server trả về representation có các phần `_embedded` và `_links` theo HAL. Nếu ứng dụng hỗ trợ nhiều media type, hãy xác định rõ cách content negotiation hoạt động và kiểm tra response theo từng định dạng.

Không nên giả định mọi controller trả `CollectionModel` sẽ tự động đáp ứng mọi client. Cấu hình hypermedia, relation metadata và converter cần phù hợp với media type mà ứng dụng công bố. Kiểm thử response HTTP là cách xác nhận cấu trúc cuối cùng mà client thực sự nhận được.

## 10. Kiểm thử CollectionModel

Nên kiểm tra cả dữ liệu trong model và response sau serialization. Với unit test, có thể kiểm tra số phần tử và liên kết collection:

```java
CollectionModel<OrderModel> model = CollectionModel.of(List.of(first, second));
model.add(Link.of("/orders", "self"));

assertThat(model.getContent()).hasSize(2);
assertThat(model.hasLink("self")).isTrue();
assertThat(model.getRequiredLink("self").getHref()).isEqualTo("/orders");
```

Với MockMvc, kiểm tra response HAL ở cấp collection và item:

```java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

Tên `orders` trong JSONPath phải khớp với relation collection mà ứng dụng đã cấu hình. Bộ test nên bao gồm danh sách rỗng, một phần tử, nhiều phần tử và các trang nếu endpoint hỗ trợ phân trang.

Kiểm tra liên kết theo ý nghĩa thay vì so sánh toàn bộ JSON dạng chuỗi. Thứ tự thuộc tính hoặc thứ tự link có thể thay đổi mà không làm hợp đồng hypermedia thay đổi. Hãy xác nhận relation, `href`, content type và các trường dữ liệu mà client được phép sử dụng.

## 11. Những lỗi thường gặp khi dùng CollectionModel

**Trả `List<T>` khi client cần điều hướng collection.** Danh sách thuần không cung cấp một đối tượng collection có link riêng. Hãy dùng `CollectionModel` khi cần công bố `self`, `next` hoặc các relation cấp collection.

**Chỉ thêm link cho collection mà quên link cho từng item.** Client cần đi từ danh sách tới chi tiết từng tài nguyên. Hãy thêm `self` cho từng item khi hợp đồng yêu cầu.

**Chỉ thêm link cho item mà quên link cấp collection.** Item có thể điều hướng tới chi tiết, nhưng client vẫn cần biết URI của danh sách hoặc trang tiếp theo. Xác định các relation cấp collection cần công bố.

**Nhầm collection với phân trang.** `CollectionModel` không tự cung cấp metadata trang. Khi cần thông tin phân trang, sử dụng `PagedModel` hoặc tích hợp tương ứng.

**Giả định collection luôn có phần tử.** Endpoint collection có thể trả rỗng. Client và test cần xử lý trường hợp không có `_embedded` hoặc không có item.

**Không ổn định tên relation.** Đổi tên relation collection có thể khiến client không tìm thấy danh sách. Định nghĩa và kiểm thử relation như một phần của hợp đồng.

**Dùng URI cố định trong code.** Đường dẫn viết tay dễ lỗi khi mapping thay đổi. Dùng `WebMvcLinkBuilder` hoặc cơ chế dựng link phù hợp với stack web.

## 12. Bài tập thực hành và tiêu chí hoàn thành

Hãy hoàn thiện endpoint `GET /orders` theo các yêu cầu:

1. Tạo `OrderModel` hoặc `EntityModel<OrderView>` cho từng đơn hàng.
2. Dùng `CollectionModel.of(...)` để bọc các phần tử.
3. Thêm relation `self` ở cấp collection.
4. Thêm relation `self` ở từng item.
5. Cấu hình tên relation collection rõ ràng, ví dụ `orders`.
6. Trả response theo HAL và xác nhận `_embedded` cùng `_links`.
7. Kiểm tra collection rỗng và xác nhận client vẫn đọc được liên kết cấp collection.
8. Nếu có phân trang, chuyển sang `PagedModel` hoặc cơ chế tích hợp phù hợp và kiểm thử liên kết trang.
9. Tạo một client nhỏ đọc relation từ response rồi gọi URI lấy được.

Bạn đã hiểu `CollectionModel` khi có thể giải thích sự khác nhau giữa link của collection và link của từng item, tạo collection từ các representation model, xác định relation cho HAL, xử lý collection rỗng và biết khi nào cần `PagedModel`. Đây là nền tảng để xây dựng API danh sách mà client có thể khám phá và điều hướng theo hypermedia.
