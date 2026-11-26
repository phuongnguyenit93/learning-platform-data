# Thiếu self link

## Mục tiêu

Sau bài này, bạn có thể nhận biết response hypermedia bị thiếu liên kết `self`, xác định các nguyên nhân thường gặp và bổ sung liên kết này bằng Spring HATEOAS. Bạn cũng có thể phân biệt `self` của một tài nguyên với `self` của collection, kiểm tra href được tạo từ mapping controller và viết kiểm thử để ngăn lỗi tái diễn.

## 1. Self link có vai trò gì?

Relation `self` trỏ đến chính tài nguyên hoặc representation đang được mô tả. Nó giúp client nhận diện địa chỉ chuẩn để truy cập lại tài nguyên, làm mới dữ liệu hoặc lưu tham chiếu đến tài nguyên đó.

Ví dụ response HAL của một đơn hàng:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
```

Link `self` trỏ đến đơn hàng hiện tại. Link `customer` trỏ đến tài nguyên liên quan. Hai link có vai trò khác nhau: client có thể theo `self` để truy cập lại đơn hàng và theo `customer` để khám phá thông tin khách hàng.

Nếu response không có `self`, client vẫn có thể đọc dữ liệu và dùng các link khác, nhưng thiếu một cách điều hướng trực tiếp, nhất quán về chính tài nguyên hiện tại. Điều này đặc biệt bất tiện với client tổng quát, cache hoặc công cụ duyệt API vốn dựa vào relation thay vì tự ghép URL.

## 2. Nhận biết response thiếu self link

Với HAL, self link thường nằm tại `_links.self.href`. Một response có thể thiếu self link theo một số dạng:

**Chỉ có link liên quan:**

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "customer": {
      "href": "/customers/7"
    }
  }
}
```

**Có links nhưng dùng relation khác:**

```json
{
  "id": "42",
  "_links": {
    "current": {
      "href": "/orders/42"
    }
  }
}
```

Trong ví dụ thứ hai, client không tìm thấy relation chuẩn `self`, dù URL có thể trỏ đến chính đơn hàng. Relation `current` không tự động có cùng semantics với `self`.

**Không có phần hypermedia:**

```json
{
  "id": "42",
  "status": "PENDING"
}
```

Response này là JSON dữ liệu thông thường. Nếu API cam kết trả HAL, cần kiểm tra media type, message converter và kiểu đối tượng controller trả về.

## 3. Những nguyên nhân thường gặp

Self link thường bị thiếu do cách tạo representation hoặc cấu hình response:

1. **Tạo EntityModel mà không truyền link.** `EntityModel.of(order)` chỉ bao dữ liệu. Nó không tự suy ra endpoint cần dùng làm self link.
2. **Assembler chỉ thêm link liên quan.** Assembler có thể thêm `customer`, `orders` hoặc `payment` nhưng quên `self`.
3. **Dùng relation tùy chỉnh cho chính tài nguyên.** Ví dụ `withRel("current")` tạo relation `current`, không phải `self`.
4. **Tạo URL bằng chuỗi hoặc tham số sai.** Href có thể thiếu path variable, dùng sai mapping hoặc trỏ nhầm tài nguyên.
5. **Trả về DTO hoặc entity thuần.** Nếu controller không trả một hypermedia model, Spring HATEOAS không có danh sách link để tuần tự hóa.
6. **Kiểm tra nhầm định dạng response.** Nếu client nhận JSON thông thường thay vì HAL, cấu trúc `_links` sẽ không xuất hiện theo cách mong đợi.

Khi chẩn đoán, hãy kiểm tra từ controller đến assembler và response thực tế. Xác định controller trả kiểu gì, assembler tạo những relation nào và request đang thương lượng media type nào.

## 4. Bổ sung self link bằng linkTo và methodOn

Với Spring MVC, cách thông dụng là dùng `WebMvcLinkBuilder`. `methodOn(...)` tham chiếu phương thức controller, còn `linkTo(...)` tạo href dựa trên mapping và tham số của phương thức đó.

Ví dụ controller:

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
        Order order = orderService.getRequired(id);
        return assembler.toModel(order);
    }
}
```

Assembler luôn thêm relation `self` khi tạo model:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel();

        return EntityModel.of(order, self);
    }
}
```

Các import liên quan:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Điểm quan trọng là `withSelfRel()` tạo relation chuẩn `self`. Tham chiếu đến `getOrder(order.getId())` giúp href sử dụng đúng mapping và định danh của đơn hàng đang được chuyển thành representation.

Nếu controller đổi mapping từ `/orders/{id}` sang một đường dẫn khác, link builder có thể theo mapping mới khi ứng dụng được cập nhật. Cách này giảm lỗi do tự ghép chuỗi URL trong assembler.

## 5. Bổ sung self link trực tiếp vào model

Nếu không cần một assembler riêng, có thể thêm link vào model ngay tại nơi tạo response:

```java
@GetMapping("/{id}")
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    Order order = orderService.getRequired(id);

    EntityModel<Order> model = EntityModel.of(order);

    model.add(linkTo(methodOn(OrderController.class)
            .getOrder(id)).withSelfRel());

    return model;
}
```

Cách này phù hợp với controller nhỏ hoặc ví dụ đơn giản. Khi nhiều endpoint cùng tạo một loại representation, nên gom quy tắc vào assembler để tránh mỗi controller tạo self link theo một cách khác nhau.

Có thể thêm cả self link và link liên quan:

```java
return EntityModel.of(
        order,
        linkTo(methodOn(OrderController.class)
                .getOrder(order.getId())).withSelfRel(),
        linkTo(methodOn(OrderController.class)
                .getOrders()).withRel("collection")
);
```

Ở đây `self` trỏ đến đơn hàng hiện tại, còn `collection` trỏ đến danh sách chứa đơn hàng. Không dùng một link thay cho cả hai quan hệ.

## 6. Self link của collection và của từng phần tử

Một response collection có thể cần self link ở hai cấp:

- Self link của collection trỏ đến endpoint trả danh sách.
- Self link của từng phần tử trỏ đến endpoint chi tiết của phần tử đó.

Ví dụ HAL:

```json
{
  "_links": {
    "self": {
      "href": "/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      },
      {
        "id": "43",
        "_links": {
          "self": {
            "href": "/orders/43"
          }
        }
      }
    ]
  }
}
```

Assembler của từng phần tử có thể thêm self link như sau:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .getOrder(order.getId())).withSelfRel()
        );
    }
}
```

Controller tạo collection và thêm self link cấp collection:

```java
@GetMapping
public CollectionModel<EntityModel<Order>> getOrders() {
    CollectionModel<EntityModel<Order>> model =
            orderAssembler.toCollectionModel(orderService.findAll());

    model.add(linkTo(methodOn(OrderController.class)
            .getOrders()).withSelfRel());

    return model;
}
```

Nếu chỉ thêm self link cho collection, từng phần tử có thể vẫn thiếu self link. Ngược lại, nếu chỉ thêm self link cho các phần tử, client không có link chuẩn để truy cập lại toàn bộ collection. Hãy xác định rõ response có những cấp tài nguyên nào và bổ sung self link ở đúng cấp.

## 7. Kiểm tra mapping và href

Khi self link vẫn không đúng sau khi thêm `withSelfRel()`, kiểm tra các yếu tố sau:

- Phương thức được truyền vào `methodOn` có phải endpoint đọc đúng tài nguyên không?
- Path variable có nhận đúng ID của đối tượng hiện tại không?
- Controller có mapping ở cấp lớp như `@RequestMapping("/orders")` không?
- Link builder có được dùng đúng stack web không? Spring MVC dùng `WebMvcLinkBuilder`; WebFlux dùng API link builder tương ứng.
- Ứng dụng có chạy sau reverse proxy hoặc context path khiến absolute href cần forwarded header không?
- Request có yêu cầu đúng media type HAL và ứng dụng có cấu hình converter phù hợp không?

Không nên sửa lỗi bằng cách gắn cứng `http://localhost:8080/orders/42` vào assembler. Địa chỉ đó có thể sai ở staging, production hoặc sau proxy. Link builder từ mapping controller thường là lựa chọn phù hợp cho endpoint nội bộ.

Nếu API dùng URI tương đối, client cần phân giải href theo URI cơ sở của response. Nếu API công bố absolute URI, cần bảo đảm scheme và host là địa chỉ public mà client truy cập được.

## 8. Kiểm thử self link bằng MockMvc

Kiểm thử response HAL nên xác nhận relation `self` tồn tại và href trỏ đến đúng tài nguyên:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/" + orderId)));
```

Nếu API trả collection, kiểm tra cả self link của collection và từng phần tử:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
            .exists());
```

Có thể bổ sung các kiểm thử sau:

1. ID khác nhau tạo self href tương ứng với từng tài nguyên.
2. Collection rỗng vẫn có self link cấp collection.
3. Mọi phần tử trong collection đều có self link nếu hợp đồng API yêu cầu.
4. Self href vẫn đúng khi mapping controller thay đổi.
5. Response trả đúng media type mà client yêu cầu.

Nên kiểm tra relation và phần URI có ý nghĩa theo hợp đồng, tránh khóa cứng scheme hoặc host của môi trường kiểm thử nếu chúng không phải phần hợp đồng công khai.

## 9. Những lỗi cần tránh

**Chỉ trả về entity hoặc DTO thuần trong endpoint hypermedia.** Khi API cam kết representation HAL, hãy trả một kiểu model Spring HATEOAS hoặc representation tùy chỉnh có links.

**Giả định EntityModel tự tạo self link.** `EntityModel.of(order)` không biết controller nào đại diện cho đối tượng đó. Hãy thêm link rõ ràng.

**Dùng relation khác thay cho self.** `current`, `detail` hoặc `resource` không có semantics tương đương relation chuẩn `self`.

**Thêm self link trỏ sai cấp.** Link của collection và link của từng item cần trỏ đến đúng endpoint tương ứng.

**Tự ghép href từ ID.** Cách này dễ lệch mapping, context path và cấu hình triển khai. Ưu tiên `linkTo(methodOn(...))`.

**Cho rằng self link là cơ chế bảo mật.** Self link chỉ chỉ ra URI của tài nguyên. Server vẫn phải xác thực, phân quyền và kiểm tra trạng thái khi nhận request.

## 10. Checklist xử lý thiếu self link

Khi response HAL thiếu `_links.self`, có thể kiểm tra theo trình tự:

1. Xác nhận client đang yêu cầu media type HAL và response có `Content-Type` phù hợp.
2. Xác nhận controller trả về `EntityModel`, `CollectionModel` hoặc representation model có hỗ trợ links.
3. Kiểm tra assembler có gọi `withSelfRel()` hay thêm relation `self` hay không.
4. Xác nhận `methodOn` tham chiếu đúng phương thức và đúng ID.
5. Kiểm tra self link cấp collection và self link của từng phần tử riêng biệt.
6. Dùng MockMvc kiểm tra relation và href thực tế.

## Kết luận

Self link là relation trỏ đến chính tài nguyên hoặc representation hiện tại. Spring HATEOAS không tự biết endpoint của mọi đối tượng domain khi bạn chỉ gọi `EntityModel.of(order)`; hãy bổ sung `withSelfRel()` bằng `linkTo(methodOn(...))` trong assembler hoặc controller. Với collection, kiểm tra cả self link cấp danh sách và self link của từng phần tử. Kiểm thử `_links.self.href` giúp bảo vệ khả năng điều hướng và tính nhất quán của hợp đồng hypermedia.

