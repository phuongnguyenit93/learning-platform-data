# Serialize collection

Trong Spring HATEOAS, `CollectionModel<T>` biểu diễn một tập hợp tài nguyên cùng các liên kết hypermedia của chính tập hợp đó. Khi controller trả `CollectionModel` qua Spring MVC, Spring HATEOAS phối hợp với Jackson và HTTP message converter để tuần tự hóa các phần tử, liên kết của từng phần tử và liên kết điều hướng của collection thành response HTTP.

Với HAL JSON, các phần tử collection thường được đặt trong `_embedded`, còn các liên kết được đặt trong `_links`. Nếu collection được phân trang, response còn có metadata trang. Client có thể đọc danh sách, theo liên kết `self`, điều hướng tới các trang khác và truy cập từng tài nguyên qua link của phần tử.

## CollectionModel chứa gì?

`CollectionModel<T>` là representation model dành cho một tập hợp. Nó kế thừa cơ chế liên kết của `RepresentationModel` và cung cấp hai phần chính:

- **Content:** tập hợp các representation kiểu `T`, ví dụ `OrderModel` hoặc `EntityModel<OrderResponse>`.
- **Links:** các liên kết mô tả collection như `self`, `search`, `create` hoặc các quan hệ điều hướng khác.

Mỗi phần tử trong collection có thể tự mang các link riêng, chẳng hạn `self`, `customer` hoặc `cancel`. Cần phân biệt link của collection với link của từng phần tử: `self` ở cấp collection trỏ tới danh sách, còn `self` ở cấp phần tử trỏ tới một tài nguyên cụ thể.

Tạo collection đơn giản bằng `CollectionModel.of(...)`:

```java
List<OrderModel> orders = orderService.findAll().stream()
        .map(orderAssembler::toModel)
        .toList();

CollectionModel<OrderModel> model = CollectionModel.of(orders);
```

Có thể thêm liên kết cho collection sau khi tạo:

```java
model.add(linkTo(methodOn(OrderController.class).all())
        .withSelfRel());
```

Hoặc truyền link ngay khi gọi `CollectionModel.of(content, links...)`:

```java
CollectionModel<OrderModel> model = CollectionModel.of(
        orders,
        linkTo(methodOn(OrderController.class).all()).withSelfRel()
);
```

## Xác định quan hệ cho các phần tử trong HAL

HAL đặt các phần tử của collection trong `_embedded`. Khóa bên trong `_embedded` là collection relation, còn mỗi phần tử là một representation riêng.

Để xác định tên quan hệ rõ ràng, có thể dùng annotation `@Relation` trên lớp representation:

```java
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
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

Trong ví dụ, `collectionRelation = "orders"` xác định tên khóa collection trong `_embedded`; `itemRelation = "order"` đặt tên quan hệ cho từng phần tử khi định dạng hoặc client cần sử dụng quan hệ đó. Đặt tên rõ ràng giúp response ổn định và dễ đọc hơn. Nếu không cấu hình quan hệ tường minh, Spring HATEOAS dùng relation provider để suy ra tên từ kiểu representation; tên suy ra có thể không trùng với thuật ngữ nghiệp vụ mà API mong muốn.

## Tuần tự hóa collection thành HAL JSON

Giả sử collection có hai đơn hàng. Khi client yêu cầu `application/hal+json`, response có dạng minh họa:

```http
GET /api/orders HTTP/1.1
Accept: application/hal+json
```

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "a101",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/a101"
          },
          "cancel": {
            "href": "http://localhost:8080/api/orders/a101/cancel"
          }
        }
      },
      {
        "id": "a102",
        "status": "SHIPPED",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/a102"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
```

`_embedded.orders` chứa các phần tử. Mỗi phần tử mang nội dung và `_links` riêng. `_links` ở cấp ngoài cùng mô tả collection. Trong ví dụ, đơn hàng đang `PENDING` có link `cancel`, còn đơn hàng `SHIPPED` không công bố link đó.

Collection không phân trang thường không có metadata `page`. Với collection rỗng, `_embedded` có thể không xuất hiện vì không có phần tử để nhúng; các link ở cấp collection vẫn có thể được trả về để client điều hướng hoặc bắt đầu thao tác khác.

## Tạo collection bằng RepresentationModelAssembler

Khi đã có `RepresentationModelAssembler<T, D>`, Spring HATEOAS cung cấp phương thức `toCollectionModel(...)` để chuyển một iterable đối tượng miền thành `CollectionModel<D>`. Cách này bảo đảm từng phần tử được tạo bằng cùng quy tắc biểu diễn và liên kết.

```java
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
                order.getId(),
                order.getStatus().name()
        );

        model.add(linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId())).withRel("cancel"));
        }

        return model;
    }
}
```

Assembler chịu trách nhiệm tạo representation cho từng đơn hàng. Sau đó có thể tạo collection và thêm link cấp collection:

```java
CollectionModel<OrderModel> collection = orderAssembler.toCollectionModel(
        orderService.findAll()
);

collection.add(linkTo(methodOn(OrderController.class).all())
        .withSelfRel());
```

Lợi ích của cách này là link của từng phần tử được tạo tập trung. Khi thêm trường response hoặc thay đổi điều kiện xuất hiện của một action link, các endpoint sử dụng assembler có thể dùng chung quy tắc đó.

## Trả CollectionModel từ controller

Controller gọi service để lấy dữ liệu, dùng assembler để chuyển từng phần tử và trả collection. Ví dụ:

```java
import java.util.Collection;

import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(produces = "application/hal+json")
    public CollectionModel<OrderModel> all() {
        Collection<Order> orders = service.findAll();

        CollectionModel<OrderModel> model = assembler.toCollectionModel(orders);
        model.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
        return model;
    }
}
```

Đây là ví dụ rút gọn; các kiểu `Order`, `OrderService` và `OrderModelAssembler` được định nghĩa trong ứng dụng. `@GetMapping` trả về `CollectionModel<OrderModel>` thay vì một `List<Order>`, vì vậy response có thể mang liên kết của collection cùng liên kết của từng phần tử.

## Phân biệt link collection và link phần tử

Một response collection có hai cấp liên kết:

| Cấp | Ví dụ relation | Mục đích |
|---|---|---|
| Collection | `self` | Trỏ tới danh sách hiện tại |
| Collection | `create` | Dẫn tới hướng tạo tài nguyên mới nếu API công bố |
| Collection | `next`, `prev` | Điều hướng giữa các trang |
| Phần tử | `self` | Trỏ tới một tài nguyên cụ thể |
| Phần tử | `customer` | Dẫn tới tài nguyên liên quan |
| Phần tử | `cancel` | Công bố thao tác khả dụng cho phần tử |

Không nên nhầm link `self` ở cấp ngoài với `self` của phần tử. Nếu client cần mở một đơn hàng cụ thể, nó phải đọc link `self` bên trong phần tử tương ứng. Nếu cần tải lại collection, nó dùng link `self` ở cấp ngoài.

## Tuần tự hóa collection phân trang

Với tập dữ liệu lớn, không nên trả toàn bộ phần tử trong một response. Spring HATEOAS tích hợp với Spring Data để chuyển `Page<T>` thành `PagedModel<D>` thông qua `PagedResourcesAssembler<T>`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;

@GetMapping
public PagedModel<OrderModel> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pages
) {
    Page<Order> result = service.findAll(pageable);
    return pages.toModel(result, assembler);
}
```

`PagedResourcesAssembler` dùng assembler để chuyển từng phần tử trong trang và tạo các liên kết điều hướng tương ứng. Response HAL phân trang có thể chứa `_embedded`, `_links` và `page` metadata:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "a101",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/a101"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/api/orders?page=1&size=20"
    },
    "last": {
      "href": "http://localhost:8080/api/orders?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 81,
    "totalPages": 5,
    "number": 0
  }
}
```

Các giá trị trong ví dụ chỉ minh họa cấu trúc. `page.number` thường được đánh số từ 0 theo Spring Data `Pageable`. Các liên kết `next`, `prev`, `first` và `last` xuất hiện tùy vị trí trang và số trang hiện có. Client nên theo URL do server cung cấp để giữ nguyên các tham số lọc, sắp xếp và phân trang.

Nếu API có bộ lọc như `status=PENDING`, hãy bảo đảm link trang kế tiếp giữ lại bộ lọc. Nếu response dùng cursor pagination thay vì số trang, hãy công bố các liên kết tiếp diễn theo cursor để client không cần tự suy luận cách phân trang nội bộ.

## Collection rỗng và metadata

Khi service không tìm thấy phần tử nào, controller vẫn có thể trả `CollectionModel` rỗng cùng link `self`:

```java
CollectionModel<OrderModel> empty = CollectionModel.empty();
empty.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
return empty;
```

Response rỗng vẫn có thể cung cấp các liên kết cấp collection. Điều này giúp client biết nó đang ở collection nào và có thể điều hướng hoặc thực hiện một thao tác khác nếu server công bố.

Với collection phân trang, metadata có thể cho biết tổng số phần tử bằng 0 và số trang tương ứng. Hãy kiểm thử cả trường hợp collection rỗng để bảo đảm client xử lý được response không có `_embedded`.

## Content negotiation và cấu hình HAL

Để nhận collection theo HAL JSON, client gửi header:

```http
Accept: application/hal+json
```

Spring Boot với dependency `spring-boot-starter-hateoas` thường tự cấu hình hỗ trợ hypermedia. Trong cấu hình Spring MVC thủ công, có thể bật HAL bằng `@EnableHypermediaSupport(type = HypermediaType.HAL)`. Khi controller trả `CollectionModel`, converter hypermedia sẽ tuần tự hóa collection relation, các phần tử và liên kết theo cấu trúc HAL.

Nếu endpoint giới hạn media type bằng `produces = "application/hal+json"`, client yêu cầu một định dạng không được hỗ trợ có thể nhận `406 Not Acceptable`. Hãy thống nhất media type giữa server và client, đồng thời xác nhận `Content-Type` thực tế của response.

## Kiểm thử serialization của CollectionModel

Kiểm thử cần xác nhận cả collection relation, dữ liệu từng phần tử, link cấp collection và link cấp phần tử. Ví dụ với MockMvc:

```java
import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0].id").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

Với collection phân trang, kiểm tra metadata và liên kết điều hướng:

```java
mockMvc.perform(get("/api/orders?page=0&size=20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu dữ liệu có nhiều hơn một trang, có thể kiểm tra thêm `_links.next`. Với collection rỗng, kiểm thử nên xác nhận response thành công và link `self` tồn tại; không nên giả định `_embedded.orders` luôn có mặt khi không có phần tử.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả `List<T>` trực tiếp | Không có link cấp collection | Trả `CollectionModel<T>` khi cần hypermedia |
| Chỉ thêm link cho collection | Phần tử không có đường dẫn tới tài nguyên riêng | Dùng assembler để thêm link cho từng phần tử |
| Nhầm link `self` collection với `self` phần tử | Client điều hướng sai cấp tài nguyên | Kiểm thử `_links` ở cả hai cấp |
| Không xác định collection relation | Khóa `_embedded` khó đoán hoặc không đúng tên nghiệp vụ | Dùng `@Relation(collectionRelation = ...)` |
| Trả toàn bộ dữ liệu lớn | Response nặng và tốn thời gian | Dùng `PagedModel` và `PagedResourcesAssembler` |
| Bỏ qua collection rỗng | Client gặp trường hợp thiếu `_embedded` ngoài dự kiến | Kiểm thử collection rỗng và link cấp ngoài |
| Link phân trang làm mất bộ lọc | Client đi sang trang khác với truy vấn khác | Giữ filter/sort trong liên kết điều hướng |
| Kiểm thử chỉ số lượng phần tử | Không phát hiện lỗi relation hoặc link | Kiểm thử `_embedded`, `_links` và `page` |

## Quy trình thực hành

Khi xây response collection với Spring HATEOAS, hãy thực hiện theo thứ tự:

1. Chọn kiểu representation cho mỗi phần tử, ví dụ `OrderModel` hoặc `EntityModel<OrderResponse>`.
2. Xác định `itemRelation` và `collectionRelation` ổn định cho HAL.
3. Dùng assembler để tạo nội dung và link cho từng phần tử.
4. Dùng `toCollectionModel(...)` hoặc `CollectionModel.of(...)` để tạo collection.
5. Thêm link cấp collection như `self` và các link điều hướng cần thiết.
6. Nếu dữ liệu lớn, chuyển `Page<T>` thành `PagedModel<D>` bằng `PagedResourcesAssembler`.
7. Thương lượng `application/hal+json` và kiểm tra response thực tế.
8. Kiểm thử collection có dữ liệu, collection rỗng và các trang đầu/cuối.

## Kết luận

`CollectionModel` giúp REST API biểu diễn một tập hợp tài nguyên cùng các liên kết hypermedia của collection và từng phần tử. Khi tuần tự hóa theo HAL, các phần tử nằm trong `_embedded`, liên kết nằm trong `_links`, còn collection phân trang có thêm metadata `page`. Kết hợp `@Relation`, `RepresentationModelAssembler`, `PagedResourcesAssembler` và kiểm thử MockMvc giúp response collection có cấu trúc rõ ràng, dễ điều hướng và ổn định khi API phát triển.
