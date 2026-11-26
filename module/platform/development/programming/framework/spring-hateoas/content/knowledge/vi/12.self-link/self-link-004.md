# Self link cho collection

Một API quản lý đơn hàng có endpoint `/api/orders` trả về danh sách đơn hàng. Mỗi đơn hàng trong danh sách có thể có link `self` để mở chi tiết, nhưng chính danh sách cũng là một resource có thể được tham chiếu. Vì vậy response collection cần một link `self` ở cấp cao nhất, trỏ về đúng collection mà client vừa yêu cầu.

Trong Spring HATEOAS, `CollectionModel<T>` cho phép gắn link ở cấp collection. Khi thêm relation `self`, client có thể nhận biết URI đại diện cho collection hiện tại, quay lại đúng tập kết quả hoặc lưu tham chiếu đến representation đó. Link `self` của collection có vai trò khác với link `self` của từng phần tử bên trong collection.

## Self link của collection là gì?

Self link là liên kết có relation `self`, trỏ đến resource được mô tả bởi representation hiện tại. Với response của một collection, self link phải trỏ đến collection đó; với response của một item, self link phải trỏ đến item tương ứng.

Ví dụ request:

```http
GET /api/orders?status=PENDING&sort=createdAt,desc
Accept: application/hal+json
```

Response có thể chứa một self link cấp collection:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders?status=PENDING&sort=createdAt,desc"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/ord-1042"
          }
        }
      }
    ]
  }
}
```

Ở đây có hai cấp self link:

- `$._links.self` ở cấp gốc đại diện cho collection đã lọc và sắp xếp.
- `$._embedded.orders[0]._links.self` đại diện cho đơn hàng `ord-1042`.

Không được dùng URI chi tiết của một phần tử làm self link của collection. Ngược lại, cũng không dùng URI collection làm self link của từng item.

## Vì sao collection cần self link?

Self link giúp client biết URI chuẩn của representation collection hiện tại. Điều này hữu ích khi:

- Client cần lưu hoặc chia sẻ địa chỉ của tập kết quả đang xem.
- Client cần tải lại collection theo đúng filter, sort hoặc page hiện tại.
- Một thành phần trung gian hoặc công cụ API cần xác định URI của resource được mô tả.
- Server thay đổi cấu trúc đường dẫn nội bộ nhưng vẫn cung cấp đích điều hướng chính xác qua hypermedia.
- Client cần phân biệt collection hiện tại với các collection liên quan như danh sách đơn hàng của một khách hàng hoặc danh sách đơn hàng đang chờ.

Self link không phải là link “quay lại” theo nghĩa giao diện người dùng. Nó xác định resource hiện tại. Client có thể dùng nó để tải lại representation, nhưng việc quay lại màn hình trước đó thuộc logic điều hướng của client.

## Tạo self link bằng CollectionModel

Spring HATEOAS cung cấp `CollectionModel.of(content, links...)` để bọc tập hợp phần tử và thêm link ở cấp collection. Có thể dùng `withSelfRel()` để tạo relation `self`.

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

`linkTo(methodOn(...))` tạo URI dựa trên mapping của controller. `methodOn(...)` dùng proxy để tham chiếu phương thức đích; nó không gọi phương thức controller thật để chạy nghiệp vụ. `withSelfRel()` gắn quan hệ chuẩn `self` cho link.

Ví dụ này phù hợp với collection không có tham số truy vấn. Nếu endpoint có filter, sort hoặc pagination, self link cần giữ đúng ngữ cảnh của request hiện tại.

## Giữ filter và sort trong self link

Giả sử endpoint hỗ trợ lọc theo trạng thái và sắp xếp theo thời gian tạo:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
CollectionModel<OrderView> all(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "createdAt,desc") String sort) {

    List<OrderView> content = orders.findAll(status, sort);

    Link self = linkTo(methodOn(OrderController.class).all(status, sort))
        .withSelfRel();

    return CollectionModel.of(content, self);
}
```

Khi request là `/api/orders?status=PENDING&sort=createdAt,desc`, link self được tạo với cùng giá trị filter và sort. Nếu self link chỉ trỏ đến `/api/orders`, client theo link sẽ nhận collection mặc định, không còn là tập kết quả đang được mô tả.

Khi controller chuẩn hóa tham số mặc định, self link có thể đưa cả giá trị mặc định vào URI. Đây là lựa chọn hợp lệ nếu hợp đồng coi URI đã chuẩn hóa là định danh của collection. Điều quan trọng là client theo self link phải nhận được cùng ngữ nghĩa collection.

Với nhiều query parameter, cần bảo đảm tất cả tham số ảnh hưởng đến tập kết quả đều được phản ánh trong self link: filter, sort, page, size, cursor hoặc locale nếu locale làm thay đổi representation. Không đưa token xác thực hay dữ liệu bí mật vào query string.

## Tạo self link từ request hiện tại

Trong một số trường hợp, muốn giữ chính xác URI của request đang xử lý, bao gồm các query parameter đã gửi. Spring Web cung cấp `ServletUriComponentsBuilder.fromCurrentRequest()` để lấy URI từ request hiện tại:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

CollectionModel<OrderView> model = CollectionModel.of(
    orders.findAll(status, sort),
    Link.of(ServletUriComponentsBuilder.fromCurrentRequest()
        .build()
        .toUriString())
        .withSelfRel());
```

Cách này giữ query string hiện tại mà không cần khai báo lại từng tham số trong `methodOn(...)`. Nó phụ thuộc vào request context của Servlet và cấu hình xử lý forwarded headers nếu ứng dụng chạy sau reverse proxy. Nếu cần tạo link ngoài ngữ cảnh HTTP request, chẳng hạn trong batch job hoặc message consumer, hãy dùng URI được xây dựng từ cấu hình base URL hoặc mapping phù hợp thay vì gọi `fromCurrentRequest()`.

Khi chạy sau proxy, cần cấu hình Spring Boot xử lý `Forwarded` hoặc `X-Forwarded-*` theo hạ tầng. Nếu không, self link có thể chứa scheme, host hoặc port nội bộ. Chỉ tin forwarded headers từ proxy đáng tin cậy; proxy biên cần xóa hoặc ghi đè header do client tự gửi.

## Self link với phần tử có model riêng

Một collection thường chứa các item có link riêng. Có thể chuyển mỗi DTO thành `EntityModel`, sau đó bọc các model đó trong `CollectionModel`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
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

        Link collectionSelf = linkTo(methodOn(OrderController.class).all())
            .withSelfRel();

        return CollectionModel.of(content, collectionSelf);
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return toModel(orders.get(id));
    }

    private EntityModel<OrderView> toModel(OrderView order) {
        Link itemSelf = linkTo(methodOn(OrderController.class).one(order.id()))
            .withSelfRel();

        return EntityModel.of(order, itemSelf);
    }
}
```

Trong ví dụ, `collectionSelf` được gắn vào `CollectionModel`, còn `itemSelf` được gắn vào từng `EntityModel`. Hai link có cùng relation `self` nhưng thuộc hai representation khác nhau và trỏ đến URI khác nhau.

Nếu không cần link riêng cho từng item, có thể dùng `CollectionModel<OrderView>` để giảm wrapper. Việc chọn kiểu phần tử không làm thay đổi yêu cầu rằng collection cần self link riêng khi hợp đồng hypermedia cần nó.

## Self link khi dùng RepresentationModelAssembler

`RepresentationModelAssembler` thường tạo link cho từng item thông qua `toModel(...)`. Phương thức mặc định `toCollectionModel(...)` chuyển đổi các phần tử nguồn thành collection model; controller có thể bổ sung self link của collection sau đó.

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    CollectionModel<EntityModel<OrderView>> collection =
        orderAssembler.toCollectionModel(orders.findRecent());

    collection.add(
        linkTo(methodOn(OrderController.class).all()).withSelfRel());

    return collection;
}
```

Assembler tập trung link của từng item, còn controller biết request collection hiện tại và có thể tạo self link phù hợp với filter hoặc sort. Nếu nhiều endpoint cần cùng quy tắc collection link, có thể tạo một phương thức hoặc component chuyên xây dựng collection representation để tránh lặp mã.

Đừng cho rằng `toCollectionModel(...)` tự động thêm self link theo request hiện tại. Hãy xác nhận link được tạo bởi assembler hoặc bổ sung link rõ ràng trong controller.

## Self link và phân trang

Với collection lớn, API thường trả về một trang thay vì toàn bộ dữ liệu. Trong trường hợp này, `PagedModel` biểu diễn trang hiện tại và có thể chứa các link `self`, `first`, `prev`, `next`, `last`.

Self link của trang phải phản ánh đúng page, size, sort và filter hiện tại. Link `next` trỏ đến trang kế tiếp, còn link `prev` trỏ đến trang trước. Client nên theo các link này thay vì tự tính URL.

Spring Data HATEOAS cung cấp `PagedResourcesAssembler` để chuyển `Page<T>` thành `PagedModel`. Ví dụ:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(Pageable pageable) {
    Page<OrderView> page = orders.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

Trong ví dụ, `pagedAssembler` là `PagedResourcesAssembler<OrderView>` được tiêm vào controller và `orderAssembler` là `RepresentationModelAssembler<OrderView, EntityModel<OrderView>>`. Assembler phân trang tạo metadata và các link điều hướng dựa trên request/page hiện tại. Hãy kiểm thử các link thực tế theo cấu hình Spring Data và URI công khai của ứng dụng.

Với cursor pagination, self link nên giữ cursor hiện tại nếu cursor xác định chính collection đang xem. Link `next` chứa cursor kế tiếp do server phát hành. Không nên tự tạo cursor từ ID hoặc timestamp ở client nếu hợp đồng yêu cầu cursor opaque.

## Self link cho collection rỗng

Collection rỗng vẫn là một collection resource hợp lệ nếu URI collection tồn tại. Ví dụ, người dùng chưa có đơn hàng nào nhưng `/api/orders` vẫn là điểm truy cập danh sách đơn hàng của họ.

```java
CollectionModel<OrderView> empty = CollectionModel.of(
    List.of(),
    linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Response có thể không có `_embedded` hoặc có cấu trúc embedded rỗng tùy cách serializer biểu diễn. Tuy nhiên, link `self` cấp collection vẫn cần có mặt nếu hợp đồng yêu cầu. Không trả `404` chỉ vì collection không có phần tử; `404` dành cho trường hợp resource được yêu cầu không tồn tại hoặc không được công bố.

## Kiểm tra self link trong HAL

Với HAL, self link cấp collection nằm tại `._links.self.href`. Khi mỗi item cũng có self link, nó nằm bên trong phần tử tương ứng của `_embedded`.

Ví dụ kiểm tra self link cấp collection bằng MockMvc:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu collection có filter và sort, nên xác nhận self link giữ đúng query parameter:

```java
mockMvc.perform(get("/api/orders?status=PENDING&sort=createdAt,desc")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.containsString("status=PENDING")))
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.containsString("sort=createdAt,desc")));
```

Với collection chứa `EntityModel`, có thể kiểm tra link item riêng nếu hợp đồng yêu cầu:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

`orders` là tên embedded relation minh họa; hãy cấu hình relation qua `@Relation` hoặc relation provider nếu muốn tên ổn định và dùng đúng JSON path theo hợp đồng của ứng dụng.

Các trường hợp nên kiểm thử:

- Collection có phần tử và collection rỗng đều có self link.
- Self link cấp collection trỏ đến endpoint collection, không trỏ đến item đầu tiên.
- Self link giữ filter, sort, page, size hoặc cursor hiện tại.
- Self link được tạo với scheme, host, port và path prefix công khai khi chạy sau proxy.
- Self link của từng item trỏ đến đúng resource nếu item có representation riêng.
- `Accept: application/hal+json` trả đúng media type và cấu trúc `_links` theo hợp đồng.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng self link của item làm self link collection | Client theo self link đến một đơn hàng thay vì danh sách. | Tạo self link từ mapping collection hoặc request hiện tại. |
| Bỏ self link ở cấp collection | Client không có URI chuẩn để tham chiếu hoặc tải lại tập kết quả. | Thêm link `self` vào `CollectionModel`. |
| Bỏ filter/sort khỏi self link | Client theo link nhận collection khác với response hiện tại. | Giữ mọi tham số ảnh hưởng kết quả trong link. |
| Nghĩ `toCollectionModel()` tự thêm self link | Collection model có thể không có relation `self`. | Kiểm tra kết quả assembler và bổ sung link ở controller khi cần. |
| Dùng `fromCurrentRequest()` ngoài request context | Không có request hiện tại để tạo URI hoặc sinh link sai. | Dùng mapping controller hoặc base URI cấu hình cho tác vụ nền. |
| Không xử lý forwarded headers sau proxy | Self link có thể trỏ đến hostname hoặc scheme nội bộ. | Cấu hình proxy và forwarded headers đúng cách; kiểm thử ở staging. |
| Giả định collection rỗng không cần link | Client khó nhận biết URI của collection đang rỗng. | Giữ self link ngay cả khi không có phần tử. |

## Ghi nhớ

- Self link của collection trỏ đến collection hiện tại; self link của item trỏ đến item riêng.
- Dùng `CollectionModel.of(content, selfLink)` hoặc thêm link `self` vào model đã tạo.
- `linkTo(methodOn(...))` tạo URI dựa trên mapping controller; `ServletUriComponentsBuilder.fromCurrentRequest()` giữ URI request hiện tại trong ngữ cảnh Servlet.
- Self link cần giữ filter, sort và thông tin phân trang/cursor xác định tập kết quả.
- `RepresentationModelAssembler.toCollectionModel(...)` ánh xạ các item; controller có thể bổ sung self link cấp collection.
- Collection rỗng vẫn có thể là resource hợp lệ và nên giữ self link.
- Kiểm thử self link ở cấp collection, cấp item, query parameter và URL công khai sau proxy.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring Framework – ServletUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html)
