# Self link cho item trong Spring HATEOAS

Khi API trả về một collection, mỗi item thường đại diện cho một tài nguyên riêng có thể được đọc hoặc thao tác độc lập. Để client đi từ danh sách đến đúng tài nguyên, mỗi item nên có một liên kết `self` trỏ tới URI định danh chính nó. Trong Spring HATEOAS, liên kết này được tạo bằng `Link` và relation chuẩn `self`, thường thông qua `WebMvcLinkBuilder`.

Self link của item có ý nghĩa khác với self link của collection. Link ở cấp collection trỏ tới danh sách; link ở cấp item trỏ tới một tài nguyên cụ thể. Khi cả hai cấp được công bố đúng, client có thể duyệt collection, chọn một item và tiếp tục theo URI mà server cung cấp mà không cần tự ghép đường dẫn từ mã định danh.

## 1. Self link của item là gì?

Self link là liên kết có relation `self`, trỏ tới tài nguyên đang được biểu diễn. Với một đơn hàng có mã `42`, self link có thể là `/orders/42`. Với khách hàng có mã `7`, self link có thể là `/customers/7`.

Ví dụ representation của một đơn hàng:

```json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
```

Client đọc relation `self` để lấy URI của chính item. Nó có thể dùng URI này để tải representation mới nhất, chia sẻ tài nguyên hoặc đi tiếp theo các liên kết mà tài nguyên đó công bố.

Self link không phải là một bản sao của dữ liệu và cũng không phải mã định danh nội bộ của database. Nó là URI mà API công bố để client truy cập tài nguyên. URI có thể chứa path, query hoặc host tùy thiết kế API; điều quan trọng là URI đó phải xác định đúng tài nguyên.

## 2. Phân biệt self link của collection và self link của item

Một response collection có thể có self link ở cấp ngoài cùng và self link trong từng phần tử. Hai liên kết có phạm vi khác nhau:

| Vị trí | URI ví dụ | Ý nghĩa |
| --- | --- | --- |
| Collection `self` | `/orders` | Trỏ tới danh sách đơn hàng. |
| Item thứ nhất `self` | `/orders/42` | Trỏ tới đơn hàng có mã `42`. |
| Item thứ hai `self` | `/orders/43` | Trỏ tới đơn hàng có mã `43`. |

HAL có thể biểu diễn collection như sau:

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
      },
      {
        "id": "43",
        "status": "SHIPPED",
        "_links": {
          "self": {
            "href": "/orders/43"
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

Trong ví dụ, `_links.self` bên ngoài trỏ tới collection, còn `_embedded.orders[n]._links.self` trỏ tới từng đơn hàng. Client không nên dùng self link của collection như thể đó là URI của một item.

## 3. Tạo self link bằng Link và withSelfRel

Spring HATEOAS cung cấp `Link` để mô tả URI cùng relation. Với một URI đã biết, có thể tạo link bằng `Link.of(...)` và gắn relation `self` qua `withSelfRel()`:

```java
Link self = Link.of("/orders/42").withSelfRel();
```

Sau đó thêm link vào model:

```java
OrderModel model = new OrderModel(order.getId(), order.getStatus().name());
model.add(Link.of("/orders/" + order.getId()).withSelfRel());
```

Đây là cách minh họa ngắn khi URI đã có sẵn. Trong controller Spring MVC, nên tạo URI từ mapping thay vì ghép chuỗi bằng tay. Nếu mapping thay đổi, chuỗi viết tay có thể không còn trỏ tới endpoint thật.

Relation `self` là relation chuẩn. Có thể dùng `IanaLinkRelations.SELF` khi truy vấn hoặc kiểm tra relation để tránh viết chuỗi lặp lại:

```java
boolean hasSelf = model.hasLink(IanaLinkRelations.SELF);
```

## 4. Tạo self link từ mapping controller

`WebMvcLinkBuilder` giúp tạo URI dựa trên mapping Spring MVC. Hai phương thức thường dùng là `linkTo(...)` và `methodOn(...)`.

Ví dụ controller có endpoint đọc một đơn hàng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        // Tải đơn hàng và tạo representation.
    }
}
```

Tạo self link cho đơn hàng có mã `id`:

```java
Link self = linkTo(methodOn(OrderController.class).one(id))
        .withSelfRel();
```

`methodOn` tạo một tham chiếu để Spring HATEOAS phân tích mapping và tham số. Nó không gọi method controller để thực thi truy vấn hoặc nghiệp vụ. `linkTo` dùng thông tin mapping để tạo URI tương ứng.

Khi mapping là `@RequestMapping("/orders")` và method là `@GetMapping("/{id}")`, link được tạo sẽ trỏ tới đường dẫn chi tiết của item. Nếu sau này đường dẫn đổi, code tạo link vẫn dựa trên mapping mới, miễn là method được tham chiếu được cập nhật đúng.

## 5. Dùng RepresentationModelAssembler để thêm self link cho từng item

Trong API thực tế, collection thường được tạo từ danh sách domain object. `RepresentationModelAssembler<T, D>` giúp chuyển mỗi object thành representation model. Khi tạo item trong `toModel`, hãy thêm self link của chính item đó.

Ví dụ DTO công khai:

```java
public record OrderView(UUID id, String status, BigDecimal total) {}
```

Assembler chuyển `Order` thành `EntityModel<OrderView>`:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        UUID id = order.getId();
        OrderView view = new OrderView(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

Mỗi lần assembler xử lý một `Order`, nó tạo một `EntityModel` chứa DTO và self link có mã định danh tương ứng. Nhờ vậy, khi assembler chuyển nhiều phần tử thành collection model, từng item đã có URI riêng.

Controller có thể trả collection như sau:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    CollectionModel<EntityModel<OrderView>> model =
            orderAssembler.toCollectionModel(orderService.findAll());

    model.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    return model;
}
```

Assembler tạo self link cho từng item; controller bổ sung self link cho collection. Đây là hai trách nhiệm riêng. Các kiểu `Order`, `OrderService`, `OrderView` và controller trong ví dụ là thành phần minh họa của ứng dụng.

## 6. Khi nào dùng EntityModel và khi nào kế thừa RepresentationModel?

Có hai cách thông dụng để tạo item có self link:

**Bọc DTO bằng `EntityModel<T>`.** Cách này phù hợp khi đã có một DTO và chỉ cần thêm liên kết:

```java
EntityModel<OrderView> model = EntityModel.of(
        view,
        linkTo(methodOn(OrderController.class).one(view.id())).withSelfRel()
);
```

**Tạo class riêng kế thừa `RepresentationModel<T>`.** Cách này phù hợp khi representation có cấu trúc riêng hoặc cần tái sử dụng một kiểu model chuyên biệt:

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

Assembler tạo model rồi thêm self link:

```java
OrderModel model = new OrderModel(id, order.getStatus().name());
model.add(linkTo(methodOn(OrderController.class).one(id)).withSelfRel());
return model;
```

Hai cách đều cho phép item mang liên kết. Chọn kiểu model theo cấu trúc representation và khả năng tái sử dụng; không cần tạo class riêng nếu `EntityModel` cùng DTO đã đáp ứng hợp đồng.

## 7. Self link trong HAL

Khi controller trả `EntityModel` hoặc class kế thừa `RepresentationModel` và ứng dụng được cấu hình Spring HATEOAS với HAL, liên kết được tuần tự hóa bên dưới `_links`.

Ví dụ một item:

```json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
```

Với collection, item được đặt dưới `_embedded` theo relation của collection. Tên relation có thể được tùy chỉnh bằng `@Relation` hoặc cấu hình relation provider. Ví dụ JSON dùng `orders` để minh họa tên collection; hãy kiểm tra cấu hình thực tế của ứng dụng.

Client HAL nên tìm `_links.self.href` trên item mà nó quan tâm. Client không nên suy ra URI từ trường `id`, vì server có thể thay đổi cách định tuyến hoặc định dạng URI mà không đổi mã định danh nghiệp vụ.

## 8. Self link có nên trỏ tới endpoint GET?

Thông thường, self link của một tài nguyên trỏ tới URI mà client dùng để truy xuất representation của chính tài nguyên đó. Với HTTP API, endpoint `GET` là cách phổ biến để đọc tài nguyên. Vì vậy, nếu item có self link `/orders/42`, client thường kỳ vọng có thể gửi `GET /orders/42` để lấy representation của đơn hàng.

Self link không nhất thiết mô tả mọi thao tác có thể thực hiện trên item. Các thao tác nghiệp vụ như hủy, duyệt hoặc thanh toán thường được công bố bằng relation riêng, ví dụ `cancel`, `approve`, `pay`. Điều này giúp client phân biệt URI định danh tài nguyên với URI hoặc affordance dành cho một hành động.

Nếu một item trong collection chỉ là bản tóm tắt, không thể truy cập độc lập hoặc không có URI riêng, đừng tạo một self link giả. Có thể trả dữ liệu tóm tắt như embedded representation và chỉ công bố self link khi tài nguyên thực sự có endpoint hoặc định danh điều hướng rõ ràng.

## 9. Self link và khả năng tiến hóa URI

Self link giúp client không cần tự ghép URI từ ID và cấu trúc path. Server có thể thay đổi mapping từ `/orders/{id}` sang một đường dẫn khác; client vẫn có thể lấy URI mới từ relation `self` trong representation.

Để đạt lợi ích này:

- Luôn tạo self link từ mapping hoặc một cơ chế link builder dùng chung.
- Dùng relation `self` ổn định cho URI của chính tài nguyên.
- Tránh yêu cầu client nối ID vào một path đã biết trước.
- Kiểm thử self link sau khi mapping hoặc context path thay đổi.
- Kiểm thử client lấy `href` từ representation và gọi URI nhận được.

HATEOAS không tự làm client tương thích nếu client bỏ qua liên kết và tiếp tục gọi URL đã mã hóa cứng. Thay đổi URI cũng không loại bỏ nhu cầu quản lý các thay đổi khác trong hợp đồng như relation, media type hoặc cấu trúc dữ liệu.

## 10. Self link, proxy và URI công khai

Trong môi trường triển khai có reverse proxy, ingress hoặc load balancer, ứng dụng có thể nhận request trên một host hoặc port nội bộ nhưng client truy cập qua host công khai. Nếu cấu hình forwarded headers không đúng, self link được tạo có thể chứa hostname nội bộ hoặc scheme sai.

Hãy kiểm tra URI trong môi trường gần với triển khai thực tế và cấu hình Spring để xử lý forwarded headers từ proxy đáng tin cậy. Không tin các header forwarded từ nguồn không được kiểm soát, vì chúng có thể khiến ứng dụng tạo link tới host giả mạo.

Self link cũng không phải cơ chế bảo mật. Việc client nhìn thấy URI không đồng nghĩa client được phép truy cập. Endpoint đích vẫn phải xác thực, phân quyền và kiểm tra quyền trên đúng tài nguyên khi request đến.

## 11. Kiểm thử self link của item

Nên kiểm thử ở hai mức: assembler/model trong bộ nhớ và response HTTP sau serialization.

### Kiểm thử assembler

```java
@Test
void createsSelfLinkForEachOrder() {
    Order order = anOrderWithId(orderId);

    EntityModel<OrderView> model = orderAssembler.toModel(order);

    assertThat(model.hasLink("self")).isTrue();
    assertThat(model.getRequiredLink("self").getHref())
            .endsWith("/orders/" + orderId);
}
```

`anOrderWithId` đại diện cho fixture hoặc factory của dự án. Nếu assembler dùng `WebMvcLinkBuilder`, test thuần có thể cần request context để tạo URI; có thể kiểm tra relation ở unit test và xác nhận `href` chính xác trong kiểm thử web.

### Kiểm thử response collection bằng MockMvc

```java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
            .value(endsWith("/orders/" + orderId)));
```

Assertion đầu kiểm tra self link của collection; assertion sau kiểm tra self link của item đầu tiên. `orders` phải khớp với relation collection mà ứng dụng đã cấu hình.

Một bộ test tốt nên kiểm tra:

- Mỗi item có self link trỏ tới đúng ID của chính nó.
- Hai item khác nhau không vô tình nhận cùng một `href`.
- Item có thể truy xuất được qua URI self link theo hợp đồng.
- Self link của collection trỏ tới danh sách, không trỏ tới một item.
- Response có media type và cấu trúc HAL đúng.
- Client có thể đọc relation `self` và điều hướng theo `href` mà không tự ghép URI.

Không nên so sánh toàn bộ JSON dưới dạng chuỗi hoặc phụ thuộc thứ tự link. Hãy kiểm tra relation, `href` và các trường mà client được phép dựa vào.

## 12. Các lỗi thường gặp

**Chỉ tạo self link cho collection.** Client biết URI danh sách nhưng không có URI riêng của từng item. Hãy thêm self link khi item là tài nguyên có thể truy cập độc lập.

**Dùng URI của collection làm self link cho mọi item.** Mỗi item cần trỏ tới URI của chính nó, thường chứa định danh riêng.

**Tự ghép URI từ ID.** Cách này khiến client hoặc assembler phụ thuộc vào cấu trúc path. Dùng `linkTo(methodOn(...))` để dựa trên mapping controller.

**Dùng self link như link hành động.** Self link định danh tài nguyên. Hành động nghiệp vụ nên được công bố bằng relation riêng và hợp đồng thao tác tương ứng.

**Tạo self link cho item không có URI độc lập.** Một dòng dữ liệu tóm tắt không nhất thiết là tài nguyên có thể truy cập riêng. Chỉ công bố self link khi URI đích có ý nghĩa và hoạt động.

**Không kiểm tra URI được tạo qua proxy.** Link có thể trỏ tới host nội bộ hoặc sai scheme. Kiểm thử cấu hình forwarded headers trong môi trường triển khai phù hợp.

**Cho rằng self link cấp quyền truy cập.** Endpoint vẫn phải kiểm tra xác thực và phân quyền độc lập với việc link xuất hiện trong response.

## 13. Bài tập thực hành và tiêu chí hoàn thành

Hãy hoàn thiện endpoint `GET /orders` với self link cho từng item:

1. Tạo `OrderView` để công bố các trường cần thiết cho client.
2. Viết `OrderModelAssembler` trả về `EntityModel<OrderView>`.
3. Trong `toModel`, tạo self link từ `OrderController.one(id)` bằng `linkTo(methodOn(...)).withSelfRel()`.
4. Dùng `toCollectionModel` để chuyển danh sách đơn hàng thành collection.
5. Thêm self link ở cấp collection và phân biệt với self link trên từng item.
6. Yêu cầu HAL JSON và kiểm tra `_embedded` có self link đúng cho mỗi đơn hàng.
7. Dùng `href` từ self link để gọi endpoint chi tiết của một item.
8. Thay đổi mapping endpoint chi tiết và xác nhận self link được cập nhật theo mapping mới.
9. Kiểm tra endpoint vẫn áp dụng xác thực và phân quyền khi client gọi URI self.

Bạn đã nắm được self link cho item khi có thể tạo URI từ mapping controller, gắn relation `self` vào từng representation, phân biệt link của item với link của collection, kiểm tra response HAL và để client điều hướng theo `href`. Đây là nền tảng để collection trong Spring HATEOAS có thể dẫn client tới từng tài nguyên một cách rõ ràng và ổn định.
