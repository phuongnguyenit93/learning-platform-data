# Metadata cho collection

## Mục tiêu

Sau bài này, bạn có thể giải thích metadata ở cấp collection trong Spring HATEOAS, tạo liên kết điều hướng cho toàn bộ tập hợp, phân biệt metadata collection với dữ liệu của từng phần tử, sử dụng `PagedModel` cho thông tin phân trang và kiểm thử cấu trúc HAL mà client dựa vào.

## 1. Metadata ở cấp collection là gì?

Một API danh sách thường trả về nhiều tài nguyên cùng loại, chẳng hạn danh sách đơn hàng. Mỗi đơn hàng có dữ liệu và các link riêng. Bên cạnh đó, chính collection cũng cần thông tin để client hiểu và điều hướng tập hợp:

- Link `self` trỏ đến collection hiện tại.
- Link đến các collection hoặc tài nguyên liên quan, ví dụ `create`, `search` hoặc `categories`.
- Link phân trang như `first`, `prev`, `next` và `last`.
- Metadata phân trang như kích thước trang, số phần tử tổng cộng và tổng số trang.

Cần phân biệt metadata cấp collection với thuộc tính của từng phần tử. Trạng thái và mã đơn hàng thuộc về một đơn hàng. Link `next` hoặc tổng số phần tử thuộc về kết quả danh sách.

Spring HATEOAS cung cấp `CollectionModel<T>` để bao một tập hợp representation và các link cấp collection. Khi cần metadata phân trang, `PagedModel<T>` mở rộng mô hình collection bằng thông tin trang.

## 2. Cấu trúc collection trong HAL

Một response HAL cho danh sách đơn hàng thường có hai phần chính:

- `_embedded`: chứa các representation của phần tử trong collection.
- `_links`: chứa các liên kết ở cấp collection.

Ví dụ:

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
        "status": "PAID",
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
    },
    "create": {
      "href": "/orders"
    }
  }
}
```

Tên `orders` trong `_embedded` là collection relation. Tên relation được xác định từ kiểu representation và cấu hình relation của ứng dụng. Link `self` ở cấp ngoài trỏ đến danh sách; `self` ở từng phần tử trỏ đến một đơn hàng cụ thể.

Một client có thể theo link collection để tải lại danh sách, theo link của phần tử để xem chi tiết hoặc theo relation nghiệp vụ để khám phá chức năng liên quan. Các relation nên có tên ổn định và ý nghĩa rõ ràng.

## 3. Tạo CollectionModel và thêm link cấp collection

`CollectionModel<T>` biểu diễn một tập hợp các phần tử cùng các link. Có thể tạo model bằng `CollectionModel.of(...)`, hoặc dùng `RepresentationModelAssembler` để chuyển nhiều đối tượng nguồn thành collection representation.

Ví dụ assembler cho từng đơn hàng:

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

Controller tạo collection và thêm link ở cấp tập hợp:

```java
@GetMapping
public CollectionModel<EntityModel<Order>> getOrders() {
    CollectionModel<EntityModel<Order>> model =
            orderModelAssembler.toCollectionModel(orderService.findAll());

    model.add(linkTo(methodOn(OrderController.class)
            .getOrders()).withSelfRel());

    model.add(linkTo(methodOn(OrderController.class)
            .createOrder(null)).withRel("create"));

    return model;
}
```

Trong ví dụ, `toCollectionModel(...)` tạo các phần tử `EntityModel<Order>`. Mỗi phần tử có link `self` riêng. Hai lệnh `add(...)` tiếp theo bổ sung link ở cấp collection:

- `self` dẫn đến endpoint danh sách.
- `create` dẫn đến endpoint tạo đơn hàng.

`null` là đối số giữ chỗ để `methodOn` phân tích chữ ký phương thức có request body; nó không gửi request tạo đơn hàng. Link `create` thông thường cho biết đích và relation. Nếu client cần biết HTTP method và schema đầu vào, hãy bổ sung affordance và sử dụng định dạng có khả năng biểu diễn metadata tương tác như HAL-FORMS.

Các import chính trong ví dụ:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

## 4. Đặt tên relation cho phần tử nhúng

HAL dùng relation để đặt tên phần tử trong `_embedded`. Spring HATEOAS có thể suy ra tên relation từ kiểu representation và cơ chế phát hiện relation. Khi cần kiểm soát tên công khai, có thể khai báo `@Relation` trên kiểu representation:

```java
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(value = "order", collectionRelation = "orders")
public class OrderRepresentation
        extends RepresentationModel<OrderRepresentation> {

    private final UUID id;
    private final OrderStatus status;

    public OrderRepresentation(UUID id, OrderStatus status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

Trong đó:

- `value = "order"` là relation của một phần tử.
- `collectionRelation = "orders"` là relation dùng cho collection nhúng.

Tên relation là một phần hợp đồng hypermedia. Nếu client đọc `_embedded.orders`, việc đổi tên thành một relation khác có thể làm client không còn tìm thấy collection. Vì vậy, hãy lựa chọn tên rõ nghĩa và giữ ổn định qua các lần thay đổi nội bộ.

Không nên phụ thuộc vào quy tắc số nhiều tự động nếu hợp đồng API cần tên relation cụ thể. Dùng annotation hoặc cấu hình relation phù hợp giúp kiểm soát tên được công bố.

## 5. Collection rỗng và fallback type

Collection rỗng vẫn là một collection hợp lệ. Response có thể không chứa phần tử trong `_embedded`, nhưng vẫn cần giữ link cấp collection để client tiếp tục điều hướng hoặc thử lại.

Ví dụ:

```java
CollectionModel<EntityModel<Order>> emptyOrders =
        CollectionModel.empty(Order.class);

emptyOrders.add(linkTo(methodOn(OrderController.class)
        .getOrders()).withSelfRel());

return emptyOrders;
```

Khi không có phần tử, serializer có thể thiếu thông tin kiểu để xác định collection relation trong `_embedded`. Fallback type cung cấp kiểu phần tử dự kiến, giúp Spring HATEOAS suy ra metadata relation cho collection rỗng trong những trường hợp cần thiết.

Có thể dùng `CollectionModel.empty(...)` với kiểu phần tử phù hợp hoặc cấu hình fallback type trên model. Hãy kiểm tra JSON thực tế ở phiên bản Spring HATEOAS của ứng dụng, đặc biệt khi API yêu cầu giữ ổn định cấu trúc collection rỗng.

Không nên biến collection rỗng thành `null` hoặc tự ý trả HTTP 204 nếu hợp đồng yêu cầu response danh sách. Một danh sách không có phần tử vẫn có thể mang `self`, `create`, `search` và các link điều hướng khác.

## 6. Metadata phân trang với PagedModel

`CollectionModel` phù hợp với tập hợp thông thường. Khi danh sách được phân trang, client cần biết thêm thông tin về trang hiện tại và toàn bộ kết quả. Spring HATEOAS cung cấp `PagedModel<T>`, là một dạng collection representation có metadata phân trang.

Metadata thường bao gồm:

| Trường | Ý nghĩa |
|---|---|
| `size` | Số phần tử tối đa trong một trang |
| `number` | Chỉ số trang hiện tại |
| `totalElements` | Tổng số phần tử trong toàn bộ kết quả |
| `totalPages` | Tổng số trang |

Ví dụ HAL rút gọn:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "status": "PENDING"
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders?page=0&size=20"
    },
    "first": {
      "href": "/orders?page=0&size=20"
    },
    "next": {
      "href": "/orders?page=1&size=20"
    },
    "last": {
      "href": "/orders?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 0
  }
}
```

Phần `page` mô tả metadata của trang. Các link điều hướng cho phép client đi đến trang đầu, trang trước, trang tiếp theo hoặc trang cuối tùy theo vị trí hiện tại. Link `next` không xuất hiện khi đã ở trang cuối; link `prev` không xuất hiện khi đang ở trang đầu.

Không nên nhầm `size` với số phần tử thực tế trong trang cuối. `size` là kích thước trang được yêu cầu hoặc cấu hình; trang cuối có thể chứa ít phần tử hơn. `totalElements` là tổng số phần tử của kết quả truy vấn, không phải số phần tử trong trang hiện tại.

## 7. Tạo PagedModel bằng PagedResourcesAssembler

Trong ứng dụng Spring Data MVC, `PagedResourcesAssembler` chuyển `Page<T>` thành `PagedModel` và tạo metadata cùng các link phân trang.

Ví dụ controller:

```java
@GetMapping
public PagedModel<EntityModel<Order>> getOrders(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);

    return pagedAssembler.toModel(page, orderModelAssembler);
}
```

Trong đó:

- `Pageable` nhận thông tin trang và kích thước trang từ request.
- Service trả về `Page<Order>`, gồm nội dung trang và thông tin tổng số phần tử.
- `PagedResourcesAssembler` chuyển trang thành `PagedModel`.
- `OrderModelAssembler` tạo representation và link cho từng đơn hàng.

Các import thường dùng:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
```

Cách này giảm việc tự tính số trang và ghép URL cho `next`, `prev`, `first` hoặc `last`. Link được xây dựng dựa trên request và thông tin trang mà Spring Data cung cấp.

Nếu cần tạo thủ công, có thể dùng `PagedModel.PageMetadata` cùng nội dung và các link:

```java
PagedModel.PageMetadata metadata = new PagedModel.PageMetadata(
        page.getSize(),
        page.getNumber(),
        page.getTotalElements(),
        page.getTotalPages()
);

PagedModel<EntityModel<Order>> model =
        PagedModel.of(orderModels, metadata, pageLinks);
```

Cách tạo thủ công phù hợp khi cần kiểm soát cách xây dựng response, nhưng ứng dụng phải tự bảo đảm các link phản ánh đúng tham số truy vấn và trang hiện tại. Nếu đã dùng Spring Data, ưu tiên assembler để tránh sai lệch khi tạo link phân trang.

## 8. Metadata nghiệp vụ tùy chỉnh

`CollectionModel` tập trung vào tập hợp phần tử và các link. Nó không tự cung cấp các trường tùy ý như `countByStatus`, `filters`, `generatedAt` hoặc `summary`.

Nếu client cần metadata nghiệp vụ, hãy xác định rõ nó thuộc về collection hay từng phần tử. Ví dụ:

- `totalElements` và `totalPages` là metadata phân trang.
- `status` của một đơn hàng là dữ liệu phần tử.
- `availableFilters` hoặc thống kê số đơn theo trạng thái có thể là metadata nghiệp vụ của kết quả tìm kiếm.

Có thể tạo một representation tùy chỉnh kế thừa `RepresentationModel` để chứa các trường tổng hợp và link. Ví dụ về hình dạng lớp:

```java
public class OrderSearchResult
        extends RepresentationModel<OrderSearchResult> {

    private final long totalMatchingOrders;
    private final List<OrderSummary> summary;

    public OrderSearchResult(
            long totalMatchingOrders,
            List<OrderSummary> summary) {
        this.totalMatchingOrders = totalMatchingOrders;
        this.summary = summary;
    }

    public long getTotalMatchingOrders() {
        return totalMatchingOrders;
    }

    public List<OrderSummary> getSummary() {
        return summary;
    }
}
```

Đây là một representation tổng hợp cho kết quả tìm kiếm. Nếu cần đồng thời trả danh sách đơn hàng, hãy bổ sung thuộc tính collection rõ ràng hoặc thiết kế representation wrapper phù hợp với hợp đồng API. Không nên cố nhét metadata nghiệp vụ vào link hay dùng `PagedModel` chỉ vì nó có sẵn trường `page`.

Khi metadata tổng hợp có thể được tính từ truy vấn, hãy để service hoặc tầng truy vấn cung cấp dữ liệu đó. Assembler chịu trách nhiệm chuyển kết quả thành representation và gắn link, không nên tự thực hiện nhiều truy vấn nghiệp vụ.

## 9. Kiểm thử metadata và link của collection

Kiểm thử nên xác nhận cả dữ liệu nhúng lẫn link cấp collection. Ví dụ với MockMvc và HAL:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

Với endpoint phân trang:

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.totalElements").exists())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nên kiểm thử thêm các trường hợp:

1. Collection rỗng vẫn trả đúng status và các link cấp collection theo hợp đồng.
2. Trang đầu không có link `prev`; trang cuối không có link `next`.
3. Trang giữa có link điều hướng đến cả trang trước và trang tiếp theo khi các trang đó tồn tại.
4. Tổng số phần tử và tổng số trang khớp với dữ liệu truy vấn.
5. Relation trong `_embedded` giữ đúng tên mà client sử dụng.
6. Các tham số lọc và sắp xếp được giữ lại trong link phân trang nếu API hỗ trợ chúng.

Không nên chỉ kiểm tra một URL cụ thể được ghép sẵn. Hãy xác nhận relation và ý nghĩa của metadata để kiểm thử tập trung vào hợp đồng hypermedia.

## 10. Nguyên tắc thiết kế metadata collection

Khi thiết kế response collection, hãy giữ các nguyên tắc sau:

- **Tách cấp collection và cấp phần tử:** link `self` của danh sách khác link `self` của từng tài nguyên.
- **Dùng PagedModel cho phân trang:** metadata trang và link điều hướng cần nhất quán với kết quả truy vấn.
- **Giữ relation ổn định:** tên trong `_embedded` và `_links` là một phần hợp đồng với client.
- **Xử lý collection rỗng có chủ đích:** giữ link điều hướng và cung cấp fallback type nếu serializer cần biết kiểu phần tử.
- **Chỉ thêm metadata nghiệp vụ có ý nghĩa:** dùng representation tùy chỉnh khi cần trường tổng hợp ngoài mô hình collection hoặc phân trang.
- **Không nhầm metadata với bảo mật:** link chỉ hướng dẫn client; endpoint vẫn phải kiểm tra quyền và điều kiện nghiệp vụ.

## Kết luận

`CollectionModel<T>` cho phép biểu diễn một tập hợp cùng các link ở cấp collection, còn `PagedModel<T>` bổ sung metadata phân trang. Trong HAL, phần tử thường nằm trong `_embedded`, link điều hướng nằm trong `_links`, và thông tin trang nằm trong `page`. Hãy phân biệt dữ liệu của từng phần tử với metadata của cả tập hợp, đặt tên relation ổn định, xử lý collection rỗng và dùng representation tùy chỉnh khi cần metadata nghiệp vụ riêng.

