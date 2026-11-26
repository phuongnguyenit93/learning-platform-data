# Collection resource link

## Mục tiêu

Sau bài này, bạn có thể giải thích collection resource trong REST hypermedia, tạo liên kết đến collection bằng `EntityLinks` của Spring HATEOAS, phân biệt link collection với link item, cấu hình controller để thư viện nhận diện loại tài nguyên và kiểm thử các relation trong response HAL.

## 1. Collection resource là gì?

Một collection resource đại diện cho tập hợp các tài nguyên cùng loại. Ví dụ, `/orders` là điểm truy cập collection đơn hàng, còn `/orders/42` là tài nguyên đơn hàng có định danh 42.

Hai URI này có vai trò khác nhau:

- **Collection resource:** cho phép client duyệt hoặc tìm kiếm tập hợp đơn hàng.
- **Item resource:** cho phép client truy cập một đơn hàng cụ thể.

Một response HAL của item có thể chứa link đến collection:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "collection": {
      "href": "/orders"
    }
  }
}
```

Relation `self` trỏ đến đơn hàng hiện tại; relation `collection` dẫn đến tập hợp chứa đơn hàng. Client có thể quay lại danh sách thông qua link collection mà không cần tự ghép URL từ ID hoặc tên endpoint.

Collection link cũng có thể xuất hiện trên chính representation của collection:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
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

Trong response này, `_links.self` ở cấp ngoài là self link của collection. `_links.self` bên trong từng phần tử là self link của item. Không nên nhầm hai cấp liên kết này.

## 2. EntityLinks trong Spring HATEOAS

Spring HATEOAS cung cấp abstraction `EntityLinks` để tạo link đến collection resource hoặc item resource dựa trên loại tài nguyên. Thay vì tham chiếu trực tiếp một phương thức controller ở mỗi nơi, assembler có thể yêu cầu link theo class của domain resource.

Hai phương thức thường dùng:

| Phương thức | Mục đích |
|---|---|
| `linkToCollectionResource(Order.class)` | Tạo link đến collection của đơn hàng |
| `linkToItemResource(Order.class, id)` | Tạo link đến một đơn hàng theo định danh |

Ví dụ:

```java
Link orders = entityLinks
        .linkToCollectionResource(Order.class)
        .withRel(IanaLinkRelations.COLLECTION);

Link order = entityLinks
        .linkToItemResource(Order.class, orderId)
        .withSelfRel();
```

`EntityLinks` tách quy tắc tạo link khỏi cách controller được tổ chức. Nếu mapping của collection thay đổi, implementation có thể tạo link theo mapping đã cấu hình thay vì buộc từng assembler giữ chuỗi URL.

Lưu ý tên `EntityLinks` ở đây là API của Spring HATEOAS. Nó không phải một collection trong JPA hay một quan hệ entity của Spring Data.

## 3. Khai báo controller bằng @ExposesResourceFor

Để implementation dựa trên controller biết controller nào công bố một loại tài nguyên, hãy đánh dấu controller bằng `@ExposesResourceFor`.

Ví dụ:

```java
@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<Order>> getOrders() {
        return assembler.toCollectionModel(orderService.findAll());
    }

    @GetMapping("/{id}")
    public EntityModel<Order> getOrder(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }
}
```

Annotation `@ExposesResourceFor(Order.class)` khai báo rằng controller này cung cấp endpoint cho tài nguyên `Order`. Mapping `/orders` ở cấp lớp kết hợp với mapping phương thức để xác định các đường dẫn collection và item.

Các import chính:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
```

Ứng dụng cần bật hạ tầng Spring HATEOAS để có implementation `EntityLinks` phù hợp. Trong ứng dụng Spring Boot sử dụng starter HATEOAS, các thành phần hypermedia thường được auto-configure. Với cấu hình Spring thủ công, hãy bảo đảm implementation dựa trên controller được đăng ký và có thể phát hiện các controller đã khai báo `@ExposesResourceFor`.

## 4. Inject EntityLinks vào assembler

Assembler là nơi thích hợp để tập trung cách tạo representation và các liên kết của tài nguyên. Có thể inject `EntityLinks` vào assembler qua constructor:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    private final EntityLinks entityLinks;

    public OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = entityLinks
                .linkToItemResource(Order.class, order.getId())
                .withSelfRel();

        Link collection = entityLinks
                .linkToCollectionResource(Order.class)
                .withRel(IanaLinkRelations.COLLECTION);

        return EntityModel.of(order, self, collection);
    }
}
```

Các import liên quan:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.RepresentationModelAssembler;
```

Khi assembler chuyển một đơn hàng thành `EntityModel`, nó tạo hai link:

1. `linkToItemResource(...)` tạo href đến đúng đơn hàng và được gắn relation `self`.
2. `linkToCollectionResource(...)` tạo href đến collection và được gắn relation `collection`.

Controller chỉ cần gọi assembler. Điều này giữ logic tạo link tập trung và tránh lặp mapping trong nhiều endpoint.

## 5. Thêm self link cho collection resource

Khi trả về danh sách, collection representation cũng cần self link ở cấp ngoài. Có thể dùng chính `EntityLinks`:

```java
@GetMapping
public CollectionModel<EntityModel<Order>> getOrders() {
    CollectionModel<EntityModel<Order>> model =
            orderAssembler.toCollectionModel(orderService.findAll());

    model.add(entityLinks
            .linkToCollectionResource(Order.class)
            .withSelfRel());

    return model;
}
```

Trong trường hợp này, `EntityLinks` được inject vào controller hoặc một thành phần tạo collection model. Nếu muốn controller gọn hơn, hãy chuyển phần tạo collection representation vào một assembler chuyên trách.

Kết quả HAL có cấu trúc minh họa:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "_links": {
          "self": {
            "href": "/orders/42"
          },
          "collection": {
            "href": "/orders"
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

Ở đây, link `collection` trong từng item cho phép quay về tập hợp. Link `self` cấp ngoài xác định URI của collection response hiện tại. Nếu API hỗ trợ lọc hoặc phân trang, self link của collection cần phản ánh đúng request hiện tại, bao gồm query parameter liên quan.

## 6. Collection link và link phân trang

Collection resource không nhất thiết là một danh sách không phân trang. Với kết quả phân trang, Spring HATEOAS có thể biểu diễn collection dưới dạng `PagedModel` và tạo link điều hướng như `first`, `prev`, `next`, `last`.

Ví dụ response rút gọn:

```json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=20"
    },
    "first": {
      "href": "/orders?page=0&size=20"
    },
    "prev": {
      "href": "/orders?page=0&size=20"
    },
    "next": {
      "href": "/orders?page=2&size=20"
    },
    "last": {
      "href": "/orders?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 1
  }
}
```

`collection` thường chỉ collection resource, còn `self` của một response phân trang chỉ URI của trang hiện tại. Link `next` và `prev` cho phép client đi qua các trang. Các link này cần giữ lại tiêu chí lọc và sắp xếp để client không vô tình mất ngữ cảnh tìm kiếm khi chuyển trang.

Nếu dùng Spring Data, `PagedResourcesAssembler` có thể chuyển `Page<T>` thành `PagedModel` và tạo metadata trang. `EntityLinks` vẫn hữu ích để tạo link collection hoặc item trong các representation không được assembler phân trang tự động tạo ra.

## 7. Khi nào dùng EntityLinks và khi nào dùng linkTo(methodOn)?

Hai cách tạo link có mục tiêu gần nhau nhưng phù hợp với các trường hợp khác nhau:

| Cách tạo link | Phù hợp khi |
|---|---|
| `EntityLinks` | Muốn tạo link collection/item dựa trên loại tài nguyên đã được controller công bố |
| `linkTo(methodOn(...))` | Muốn tham chiếu một phương thức controller cụ thể, gồm tham số và mapping cụ thể |
| `Link.of(...)` | Đích URI là giá trị tường minh, ví dụ link đến tài liệu hoặc hệ thống bên ngoài |

Dùng `EntityLinks` khi assembler chỉ cần biết loại tài nguyên và định danh của nó. Cách này giảm phụ thuộc vào tên controller và phương thức.

Dùng `linkTo(methodOn(...))` khi link trỏ đến một thao tác hoặc mapping cụ thể, chẳng hạn endpoint tìm kiếm có query parameter, endpoint cập nhật hoặc endpoint không tuân theo quy ước collection/item thông thường.

Với URI ngoài ứng dụng, có thể dùng `Link.of(...)` hoặc lấy URI từ cấu hình. Không nên dùng `EntityLinks` để tạo link đến endpoint mà controller của ứng dụng không quản lý.

## 8. Kiểm thử collection resource link

Kiểm thử nên xác nhận relation và href được công bố đúng trong response HAL.

Với endpoint item:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/" + orderId)))
    .andExpect(jsonPath("$._links.collection.href")
            .value(org.hamcrest.Matchers.endsWith("/orders")));
```

Với endpoint collection:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith("/orders")))
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
            .exists());
```

Nên kiểm tra thêm:

1. Collection rỗng vẫn có self link cấp collection.
2. Item có self link trỏ đúng ID.
3. Relation `collection` của item trỏ đến collection đúng.
4. Mapping collection thay đổi thì link do EntityLinks tạo ra cũng thay đổi tương ứng.
5. Khi collection có phân trang hoặc bộ lọc, self link giữ đúng query parameter hiện tại.

Các kiểm thử này bảo vệ cấu trúc hypermedia mà client sử dụng. Không nên chỉ xác nhận JSON có thuộc tính `_links`; cần kiểm tra relation và đích thực tế.

## 9. Lỗi thường gặp

**Quên khai báo loại tài nguyên trên controller.** Nếu implementation dựa trên controller không biết controller nào công bố `Order`, việc tạo link theo `Order.class` có thể không tìm được mapping. Hãy khai báo `@ExposesResourceFor(Order.class)` và bảo đảm hạ tầng EntityLinks được cấu hình.

**Nhầm collection link với self link của item.** `linkToCollectionResource(Order.class)` trỏ đến danh sách; `linkToItemResource(Order.class, id)` trỏ đến một đơn hàng. Chọn phương thức theo đúng cấp tài nguyên.

**Chỉ thêm self link cho từng item.** Collection response vẫn cần self link riêng ở cấp ngoài nếu hợp đồng API yêu cầu client có thể truy cập lại collection.

**Hard-code đường dẫn collection.** Chuỗi `"/orders"` có thể lệch khi controller mapping đổi hoặc ứng dụng có context path. Dùng EntityLinks khi đường dẫn thuộc controller được khai báo.

**Dùng EntityLinks cho endpoint hành động bất kỳ.** EntityLinks tập trung vào collection và item resource. Với endpoint như `/orders/{id}/cancellations`, dùng link builder tham chiếu phương thức controller hoặc affordance phù hợp.

**Không kiểm tra query của collection.** Với collection lọc hoặc phân trang, link self cần phản ánh đúng request hiện tại. Link đến collection gốc không nhất thiết tương đương link đến trang hoặc kết quả lọc hiện tại.

## 10. Nguyên tắc thiết kế

- Khai báo rõ controller công bố loại tài nguyên nào bằng `@ExposesResourceFor`.
- Dùng `linkToCollectionResource` cho collection và `linkToItemResource` cho từng item.
- Tập trung tạo link trong assembler để response nhất quán.
- Giữ riêng self link của collection và self link của từng phần tử.
- Dùng `PagedModel` và `PagedResourcesAssembler` khi collection có phân trang.
- Dùng `linkTo(methodOn(...))` cho endpoint hoặc hành động cụ thể ngoài quy ước collection/item.
- Kiểm thử relation và href như một phần của hợp đồng API.

## Kết luận

`EntityLinks` giúp Spring HATEOAS tạo link đến collection resource và item resource theo loại tài nguyên mà controller công bố. Đánh dấu controller bằng `@ExposesResourceFor`, inject `EntityLinks` vào assembler và sử dụng `linkToCollectionResource` hoặc `linkToItemResource` để tránh lặp URL trong mã nguồn. Khi trả collection, hãy phân biệt self link của tập hợp với self link của từng item; khi kiểm thử, xác nhận cả relation và href thực tế mà client sẽ theo.

