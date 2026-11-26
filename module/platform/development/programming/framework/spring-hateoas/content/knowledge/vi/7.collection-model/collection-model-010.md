# Khi nào dùng CollectionModel

Một API quản lý đơn hàng thường có endpoint trả về một đơn hàng và endpoint trả về danh sách đơn hàng. Với endpoint chi tiết, `EntityModel<OrderView>` có thể bọc dữ liệu của một đơn hàng cùng các liên kết như `self` và `orders`. Với endpoint danh sách, client còn cần biết chính collection đang được truy cập ở đâu, có thể điều hướng đến đâu và mỗi phần tử có những liên kết nào. Đây là lúc `CollectionModel` phát huy tác dụng.

`CollectionModel<T>` là kiểu representation của Spring HATEOAS dành cho một tập hợp phần tử. Nó cho phép gắn liên kết ở cấp collection, đồng thời có thể chứa các phần tử đã có liên kết riêng. Hãy dùng nó khi response thực sự đại diện cho một collection resource và cần hypermedia ở cấp tập hợp. Nếu kết quả lớn và cần metadata phân trang, hãy chọn `PagedModel` hoặc cơ chế phân trang tương ứng.

## Collection resource là gì?

Trong REST, collection là một resource có URI riêng, thường đại diện cho một tập hợp các resource cùng loại hoặc một tập hợp được xác định bởi tiêu chí truy vấn. Ví dụ:

| URI | Ý nghĩa |
| --- | --- |
| `/api/orders` | Collection các đơn hàng người gọi được phép xem |
| `/api/orders?status=PENDING` | Collection đơn hàng đang chờ xử lý |
| `/api/customers/cus-73/orders` | Collection đơn hàng trong phạm vi một khách hàng |
| `/api/orders/ord-1042` | Một resource đơn hàng cụ thể |

Collection có thể được lọc, sắp xếp hoặc giới hạn theo quyền truy cập. Vì vậy, nó có danh tính và ngữ cảnh điều hướng riêng, khác với một mảng dữ liệu thuần túy. Khi client truy cập `/api/orders?status=PENDING`, response nên có liên kết `self` phản ánh đúng collection đã lọc để client có thể quay lại đúng kết quả đó.

Collection resource không nhất thiết là một bảng trong cơ sở dữ liệu. Nó có thể là kết quả tổng hợp từ nhiều nguồn hoặc là tập hợp ảo được xác định bởi người dùng, bộ lọc và chính sách truy cập.

## CollectionModel cung cấp điều gì?

`CollectionModel<T>` bọc một tập hợp phần tử và các link ở cấp collection. Nó không tự quyết định cách truy vấn dữ liệu, phân trang hay kiểm tra quyền; những trách nhiệm đó thuộc controller, service và tầng nghiệp vụ.

Một response collection thường cần hai nhóm hypermedia:

- **Link cấp collection:** `self`, `create`, `search`, `profile` hoặc các quan hệ điều hướng khác. Những link này mô tả collection hoặc hành động áp dụng lên collection.
- **Link cấp phần tử:** `self`, `customer`, `cancel` hoặc các quan hệ của từng item. Các link này chỉ xuất hiện nếu kiểu phần tử có model hypermedia riêng, chẳng hạn `EntityModel<T>` hoặc một lớp kế thừa `RepresentationModel`.

Do đó, hai khai báo sau có ý nghĩa khác nhau:

```java
CollectionModel<OrderView>
CollectionModel<EntityModel<OrderView>>
```

`CollectionModel<OrderView>` cung cấp link ở cấp collection; từng `OrderView` chỉ là dữ liệu. `CollectionModel<EntityModel<OrderView>>` cung cấp link ở cấp collection và mỗi đơn hàng cũng có thể có link riêng.

## Khi nào nên dùng CollectionModel?

Chọn `CollectionModel` khi các điều kiện sau phù hợp:

1. Endpoint trả về một tập hợp được xem như một resource, chẳng hạn danh sách đơn hàng, danh mục hoặc kết quả tìm kiếm.
2. Client cần link ở cấp collection để quay lại, khám phá hoặc thực hiện hành động trên tập hợp.
3. Tập hợp có kích thước hữu hạn hoặc được giới hạn hợp lý, không cần metadata phân trang chuyên biệt.
4. Ứng dụng muốn biểu diễn rõ ràng cả trường hợp collection rỗng mà vẫn giữ các link điều hướng.

Ví dụ, một danh sách trạng thái đơn hàng có vài phần tử và link `self` là ứng viên tốt cho `CollectionModel`. Một danh sách hàng triệu đơn hàng cần phân trang; không nên tải toàn bộ chỉ để đưa vào `CollectionModel`.

### Phân biệt với List, EntityModel và PagedModel

| Kiểu trả về | Khi phù hợp | Link và metadata |
| --- | --- | --- |
| `List<T>` | Endpoint nội bộ hoặc response mảng đơn giản không cần hypermedia cấp collection | Không có model riêng để đặt link cấp collection; từng phần tử phụ thuộc kiểu `T`. |
| `EntityModel<T>` | Một resource đơn lẻ | Có thể chứa link cho chính resource đó. |
| `CollectionModel<T>` | Một collection không cần metadata trang | Có link cấp collection; mỗi phần tử có link nếu `T` là representation model. |
| `PagedModel<T>` | Một trang trong collection lớn | Có metadata trang và link điều hướng giữa các trang. |

Không phải mọi endpoint trả về `List` đều bắt buộc phải đổi sang `CollectionModel`. Nếu API không dùng hypermedia và hợp đồng đã chọn mảng JSON đơn giản, `List` có thể là lựa chọn phù hợp. Ngược lại, nếu API công bố collection resource theo HAL và client cần điều hướng, `CollectionModel` tạo nơi rõ ràng để gắn link.

`CollectionModel` không tự động phân trang. Nó cũng không có metadata như số trang, tổng số phần tử hoặc kích thước trang. Khi client cần các thông tin đó, hãy dùng `PagedModel` hoặc cơ chế phân trang/cursor được thiết kế rõ ràng.

## Tạo CollectionModel trong Spring HATEOAS

Có thể tạo model bằng `CollectionModel.of(content, links...)`. Ví dụ đơn giản với DTO:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<OrderView> all() {
        List<OrderView> content = orders.findRecent();

        return CollectionModel.of(content,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Ví dụ giả định `OrderService.findRecent()` trả về một tập hợp có giới hạn và `OrderView` là DTO dành cho API. `linkTo(methodOn(...))` tạo URI dựa trên mapping controller; `withSelfRel()` gắn quan hệ `self` cho chính collection. Nếu endpoint có bộ lọc hoặc sắp xếp, hãy đưa các tham số đó vào phương thức controller được tham chiếu để link `self` giữ nguyên ngữ cảnh truy vấn.

### Thêm link cấp collection

Ngoài `self`, collection có thể cung cấp link đến các chức năng áp dụng lên collection:

```java
CollectionModel<OrderView> model = CollectionModel.of(
    orders.findRecent(),
    linkTo(methodOn(OrderController.class).all()).withSelfRel(),
    linkTo(methodOn(OrderController.class).search(null)).withRel("search"));
```

Ví dụ giả định controller có phương thức `search(String query)` được ánh xạ tới endpoint tìm kiếm. Relation `search` là quan hệ do API định nghĩa; cần mô tả ý nghĩa và cách sử dụng trong hợp đồng. Nếu thao tác có request body hoặc method khác GET, có thể bổ sung affordance và chọn media type có khả năng mô tả thao tác như HAL-FORMS.

Không nên thêm link chỉ để làm response phong phú. Mỗi relation cần có ý nghĩa thực tế với client và phải dẫn đến endpoint có thể truy cập.

## CollectionModel chứa các phần tử có link riêng

Nếu client cần điều hướng từ từng đơn hàng đến chi tiết, khách hàng hoặc thao tác khả dụng, hãy chuyển từng DTO thành `EntityModel` trước khi tạo collection.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        List<EntityModel<OrderView>> content = orders.findRecent().stream()
            .map(this::toModel)
            .toList();

        return CollectionModel.of(content,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        OrderView order = orders.get(id);
        return toModel(order);
    }

    private EntityModel<OrderView> toModel(OrderView order) {
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

Trong ví dụ, collection có link `self`; mỗi phần tử có `self` và `orders`. Cách tổ chức này hữu ích khi client cần mở một đơn hàng từ danh sách mà không phải tự tạo URI dựa trên ID.

Nếu không cần link ở cấp từng phần tử, dùng `CollectionModel<OrderView>` sẽ đơn giản hơn và tránh tạo wrapper dư thừa. Việc chọn kiểu phần tử là một quyết định riêng với việc chọn model cho collection.

## Tách ánh xạ phần tử bằng RepresentationModelAssembler

Khi nhiều endpoint cần biểu diễn cùng một loại item, nên dùng `RepresentationModelAssembler` để gom logic chuyển đổi DTO/domain object thành `EntityModel` hoặc model tùy chỉnh.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

Controller có thể gọi `assembler.toCollectionModel(...)` để chuyển cả collection nguồn thành `CollectionModel<EntityModel<OrderView>>`, sau đó bổ sung link riêng ở cấp collection:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    CollectionModel<EntityModel<OrderView>> model =
        assembler.toCollectionModel(orders.findRecent());

    model.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    return model;
}
```

`toCollectionModel(...)` sử dụng `toModel(...)` cho từng phần tử. Assembler giúp link của item nhất quán; controller vẫn có thể thêm các link riêng cho collection như `self`, `search` hoặc một quan hệ điều hướng khác.

Nếu cần tùy chỉnh cách ánh xạ toàn bộ collection, có thể ghi đè `toCollectionModel(...)` trong assembler. Chỉ nên làm vậy khi có quy tắc biểu diễn chung cho collection; các tham số truy vấn, link của request hiện tại hoặc chính sách điều hướng thường phù hợp hơn ở controller hay một component chuyên tạo collection model.

## Collection rỗng vẫn là một resource

Một collection không có phần tử vẫn có thể được truy cập và có ý nghĩa. Ví dụ, người dùng chưa tạo đơn hàng nào nhưng endpoint `/api/orders` vẫn tồn tại. Response nên giữ link `self` và các quan hệ có ý nghĩa, chẳng hạn `search` hoặc `create` nếu người dùng có quyền tạo đơn hàng.

```java
CollectionModel<OrderView> empty = CollectionModel.of(
    List.of(),
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Không nên trả `404 Not Found` chỉ vì collection rỗng. `404` phù hợp khi chính resource được yêu cầu không tồn tại hoặc không được công bố. Một collection tồn tại nhưng không có item thường trả `200 OK` với representation rỗng. Quy tắc cụ thể vẫn cần nhất quán với hợp đồng API.

## CollectionModel và HAL

Khi ứng dụng dùng HAL (`application/hal+json`), collection model thường được tuần tự hóa với `_embedded` chứa các phần tử và `_links` chứa liên kết cấp collection.

Ví dụ minh họa:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "_links": {
          "self": { "href": "/api/orders/ord-1042" }
        }
      },
      {
        "id": "ord-1043",
        "status": "SHIPPED",
        "_links": {
          "self": { "href": "/api/orders/ord-1043" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders" },
    "search": { "href": "/api/orders/search" }
  }
}
```

Tên relation `orders` trong `_embedded` là tên minh họa. Spring HATEOAS có thể suy ra relation từ kiểu phần tử hoặc cấu hình qua `@Relation` và relation provider. Với API công khai, hãy đặt tên collection relation rõ ràng và kiểm thử nó thay vì để client phụ thuộc vào tên mặc định do class Java quyết định.

Nếu dùng `CollectionModel<OrderView>`, các item trong `_embedded` chỉ chứa dữ liệu DTO; nếu dùng `CollectionModel<EntityModel<OrderView>>`, mỗi item còn có `_links` riêng. Hai cấu trúc phục vụ nhu cầu điều hướng khác nhau.

## Bộ lọc và link self

Khi collection được tạo từ tham số truy vấn, link `self` nên giữ các tham số xác định collection đó. Ví dụ, request:

```http
GET /api/orders?status=PENDING&sort=createdAt,desc
Accept: application/hal+json
```

thì `self.href` nên trỏ đến collection `PENDING` với thứ tự đã yêu cầu. Nếu link `self` bỏ mất bộ lọc hoặc sắp xếp, client theo link có thể nhận một tập kết quả khác.

Với các collection lớn, bộ lọc nên được chuẩn hóa và giới hạn. Không nên đưa dữ liệu nhạy cảm hoặc thông tin xác thực vào URI. Các tham số cần được xác thực và áp dụng cùng chính sách phân quyền như request gốc.

## Khi nào chuyển sang PagedModel?

`CollectionModel` không có metadata phân trang. Nếu danh sách có thể tăng lớn, hãy giới hạn số phần tử hoặc chuyển sang `PagedModel<T>`. `PagedModel` bổ sung metadata như `size`, `number`, `totalElements`, `totalPages` và thường có các link `first`, `prev`, `self`, `next`, `last`.

Trong Spring Data, `Page<T>` có thể được chuyển thành `PagedModel` bằng `PagedResourcesAssembler`. Ví dụ rút gọn:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(Pageable pageable) {
    Page<OrderView> page = orders.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

Đoạn code giả định controller đã được tiêm `PagedResourcesAssembler<OrderView>` và `RepresentationModelAssembler<OrderView, EntityModel<OrderView>>`. Cấu hình Spring Data HATEOAS và media type quyết định cấu trúc response cụ thể.

Hãy dùng `CollectionModel` cho collection có quy mô kiểm soát được và không cần metadata trang. Hãy dùng `PagedModel` khi client cần biết vị trí của trang hiện tại và điều hướng qua nhiều trang. Với dữ liệu cực lớn hoặc thay đổi liên tục, cursor pagination có thể phù hợp hơn offset pagination; khi đó link `next` nên mang cursor do server phát hành.

## Kiểm thử CollectionModel

Kiểm thử nên xác nhận status code, media type, link cấp collection và cấu trúc phần tử nhúng. Với MockMvc, có thể kiểm tra các thuộc tính cơ bản của HAL:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/hal+json")))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded").exists());
```

Với collection rỗng, kiểm tra link cấp collection vẫn có mặt và response không biến thành lỗi chỉ vì không có phần tử:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu hợp đồng quy định tên relation nhúng là `orders`, có thể kiểm tra cụ thể `jsonPath("$._embedded.orders").isArray()`. Với collection có link riêng cho item, kiểm tra một phần tử có `self` và relation cần thiết. Những đường dẫn JSON trong test phải khớp relation thực tế đã cấu hình.

Ngoài ra, nên kiểm tra:

- Bộ lọc và sắp xếp được giữ trong link `self`.
- Link cấp collection không xuất hiện nếu người gọi không có quyền thực hiện hành động tương ứng.
- Link `self` của mỗi phần tử trỏ đến đúng resource.
- Collection quá lớn được giới hạn hoặc trả về dưới dạng phân trang.
- Client có thể theo link được cung cấp mà không cần tự ghép URI.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `List<T>` trong khi client cần link ở cấp collection | Response không có nơi rõ ràng để gắn `self`, `search` hoặc `create`. | Trả `CollectionModel<T>`. |
| Dùng `CollectionModel` cho danh sách không giới hạn | Payload lớn, tốn bộ nhớ và thời gian phản hồi. | Giới hạn kết quả hoặc dùng `PagedModel`. |
| Cho rằng `CollectionModel<T>` tự tạo link cho từng phần tử | Client không có link item để mở chi tiết. | Dùng `CollectionModel<EntityModel<T>>` hoặc model tùy chỉnh khi cần link item. |
| Chỉ thêm link cho item, quên link collection | Client khó quay lại collection hoặc khám phá thao tác cấp tập hợp. | Bổ sung link `self` và các relation cấp collection cần thiết. |
| Collection rỗng trả `404` | Client hiểu nhầm collection resource không tồn tại. | Trả representation collection rỗng nếu collection vẫn tồn tại. |
| Link self bỏ mất filter/sort | Theo link self tạo ra một tập kết quả khác. | Tạo link từ mapping có đầy đủ query parameter hiện tại. |
| Để client dựa vào tên `_embedded` mặc định | Đổi tên class Java có thể vô tình làm thay đổi hợp đồng. | Cấu hình relation bằng `@Relation` hoặc relation provider và kiểm thử. |

## Ghi nhớ

- `CollectionModel<T>` biểu diễn một collection resource và cho phép gắn link ở cấp tập hợp.
- Dùng `CollectionModel<T>` khi collection có quy mô kiểm soát được và không cần metadata phân trang.
- Dùng `CollectionModel<EntityModel<T>>` khi từng phần tử cũng cần link riêng.
- Collection rỗng vẫn có thể là resource hợp lệ và vẫn nên giữ link `self`.
- Với HAL, collection thường được biểu diễn qua `_embedded` và link cấp collection nằm trong `_links`.
- Giữ filter và sort trong link `self`; cấu hình tên embedded relation ổn định cho API công khai.
- Chọn `PagedModel` hoặc cursor pagination khi tập hợp lớn và client cần điều hướng qua nhiều phần dữ liệu.
- Kiểm thử response HAL đã serialize, cả collection có phần tử lẫn collection rỗng.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring HATEOAS – HAL Support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring Data – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
