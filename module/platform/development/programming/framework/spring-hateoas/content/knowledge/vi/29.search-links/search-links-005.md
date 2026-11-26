# Search pagination

Một search endpoint thường trả về nhiều kết quả hơn mức client cần hiển thị trong một lần. Nếu client tìm đơn hàng theo trạng thái hoặc từ khóa, API nên hỗ trợ phân trang để giới hạn payload, thời gian xử lý và lượng dữ liệu cần giữ trong bộ nhớ. Trong REST API dùng Spring HATEOAS, server có thể công bố một **search link** để client khám phá thao tác tìm kiếm, sau đó trả kết quả dưới dạng `PagedModel` với các link điều hướng giữa các trang.

Search link thường dùng relation `search` và có thể là URI template chứa các biến như `q`, `status`, `page`, `size` và `sort`. Client mở rộng template bằng các tiêu chí tìm kiếm. Server trả một trang kết quả có metadata và các relation `self`, `first`, `prev`, `next`, `last` tùy vị trí hiện tại. Client tiếp tục theo link do server cung cấp để duyệt trang, thay vì tự ghép URI hoặc tự tính trang kế tiếp.

Trong module SPRING_HATEOAS, search pagination kết hợp hai khả năng hypermedia: khám phá thao tác tìm kiếm qua relation và điều hướng một collection phân trang qua page links. Bài học này tập trung vào search URI template, `PagedModel`, `PagedResourcesAssembler`, cách giữ filter và sort giữa các trang, cách client theo `next`/`prev`, cùng các trường hợp biên và kiểm thử.

Sau bài học, bạn có thể:

- Giải thích vai trò của search link trong một collection resource.
- Tạo search link có URI template cho filter và tham số phân trang.
- Phân biệt search link với link `next` của một trang kết quả.
- Trả kết quả tìm kiếm bằng `Page<T>` và `PagedModel<T>`.
- Dùng `PagedResourcesAssembler` để tạo page metadata và navigation links.
- Giữ filter, sort và page size khi chuyển trang.
- Mở rộng search template và theo link pagination ở client.
- Xử lý collection rỗng, trang đầu, trang cuối và page không hợp lệ.
- Kiểm thử cả kết quả lọc lẫn hợp đồng hypermedia.

## Search pagination trong hypermedia

Giả sử API quản lý đơn hàng có collection tại `/orders`. Client cần tìm các đơn hàng đã thanh toán:

~~~http
GET /orders/search?status=PAID&page=0&size=20
Accept: application/hal+json
~~~

Kết quả có thể có hàng trăm đơn hàng. Nếu server trả toàn bộ dữ liệu trong một response, payload sẽ lớn và client phải xử lý nhiều phần tử dù chỉ hiển thị một trang. Pagination chia kết quả thành những trang có kích thước giới hạn.

Một luồng hypermedia điển hình:

~~~text
GET /orders
   |
   +-- search
         URI template: /orders/search{?q,status,page,size,sort}
                |
                | client mở rộng với status=PAID, page=0, size=20
                v
        GET /orders/search?status=PAID&page=0&size=20
                |
                v
        PagedModel
          _embedded.orders
          page metadata
          _links.self
          _links.first
          _links.next
          _links.last
                |
                | client theo next
                v
        Trang tiếp theo với cùng filter và sort
~~~

Search link và page links phục vụ hai giai đoạn khác nhau:

| Link | Vai trò |
| --- | --- |
| `search` | Khám phá và bắt đầu một truy vấn |
| `self` | URI của trang kết quả hiện tại |
| `first` | Trang đầu của cùng truy vấn |
| `prev` | Trang ngay trước trang hiện tại, nếu có |
| `next` | Trang ngay sau trang hiện tại, nếu có |
| `last` | Trang cuối của cùng truy vấn |

Search link giúp client bắt đầu truy vấn. Các page links giúp client duyệt kết quả của truy vấn đó.

## Công bố search link bằng URI template

Một search link có thể mô tả các query variable mà endpoint hỗ trợ. Spring HATEOAS biểu diễn link bằng `Link`; URI template được nhận biết từ biểu thức trong href.

Ví dụ:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link search = Link
    .of("/orders/search{?q,status,page,size,sort}")
    .withRel(IanaLinkRelations.SEARCH);
~~~

Spring HATEOAS nhận diện URI template ngay trong `Link.of(...)`. Có thể kiểm tra bằng `search.isTemplated()` và xem các biến qua `search.getVariableNames()`. Khi serialize thành HAL, link được đánh dấu `templated: true`.

Trong template:

- `q` là từ khóa tìm kiếm.
- `status` là filter theo trạng thái.
- `page` là số trang.
- `size` là số phần tử tối đa trong một trang.
- `sort` là tiêu chí và hướng sắp xếp.

Ví dụ representation collection có search link:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

CollectionModel<OrderModel> model =
    CollectionModel.of(orderModels)
        .add(Link.of("/orders").withSelfRel())
        .add(Link.of("/orders/search{?q,status,page,size,sort}")
            .withRel(IanaLinkRelations.SEARCH));
~~~

Đây là ví dụ minh họa cấu trúc. Trong ứng dụng thực tế, nên xây href từ mapping controller hoặc URI builder của Spring để giữ đúng context path, servlet path và cấu hình proxy. Một URI template thủ công phù hợp khi API có target ổn định và các biến được quản lý rõ ràng.

### Vì sao dùng relation search?

Relation `search` có semantics được đăng ký trong IANA Link Relations. Client có thể tìm link theo relation thay vì phụ thuộc tên đường dẫn `/orders/search`. Server có thể thay đổi cấu trúc URI mà vẫn giữ relation và semantics của thao tác.

Client nên coi href là đích do server công bố. Không nên giả định search luôn nằm ở `/search`, luôn là con của collection, hoặc luôn có cùng tên query parameter giữa các API.

### URI template không phải form body

Search GET thường đưa filter vào query string:

~~~http
GET /orders/search?q=keyboard&status=PAID
~~~

Các biến `q` và `status` trong URI template mở rộng URI. Chúng không phải các property của JSON body. Nếu API thiết kế một thao tác tìm kiếm bằng POST với body phức tạp, input model và media type của body phải được mô tả riêng trong affordance hoặc media type hỗ trợ form.

## Thiết kế endpoint tìm kiếm có phân trang

Trong Spring MVC, Spring Data `Pageable` có thể nhận các tham số `page`, `size` và `sort`. Repository hoặc service trả `Page<T>`, sau đó `PagedResourcesAssembler` chuyển trang thành `PagedModel<D>`.

Ví dụ domain và response DTO:

~~~java
public record Order(
    Long id,
    String orderNumber,
    OrderStatus status
) {}

public record OrderResponse(
    Long id,
    String orderNumber,
    String status
) {}
~~~

Assembler tạo representation có self link cho từng đơn hàng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
            order.id(),
            order.orderNumber(),
            order.status().name());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
    }
}
~~~

Controller nhận filter cùng `Pageable`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/search", produces = MediaTypes.HAL_JSON_VALUE)
    PagedModel<EntityModel<OrderResponse>> search(
            @RequestParam(name = "q", required = false) String query,
            @RequestParam(name = "status", required = false) OrderStatus status,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC)
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> result = orderService.search(query, status, pageable);
        return pagedAssembler.toModel(result, assembler);
    }

    // Endpoint one(id) is used by the item assembler to build self links.
}
~~~

Ví dụ giả định `OrderService.search(query, status, pageable)` trả về `Page<Order>` và `OrderStatus` là enum. `PagedResourcesAssembler` chuyển mỗi `Order` thành `EntityModel<OrderResponse>`, đồng thời tạo page metadata và navigation links. Endpoint `one(id)` cần được khai báo trong controller thực tế để assembler tạo self link.

Để Spring MVC phân giải `Pageable` và cung cấp `PagedResourcesAssembler`, ứng dụng cần bật Spring Data Web support. Spring Boot thường tự cấu hình phần này khi có dependency phù hợp; với cấu hình thủ công, dùng `@EnableSpringDataWebSupport` và tích hợp Spring HATEOAS tương ứng.

Mặc định, `pagedAssembler.toModel(result, assembler)` dùng URI của request hiện tại làm cơ sở tạo page links. Nếu cần chỉ định một base link khác, có thể dùng overload nhận `Link`:

~~~java
Link searchSelf = linkTo(methodOn(OrderController.class)
    .search(query, status, pageable, null)).withSelfRel();

return pagedAssembler.toModel(result, assembler, searchSelf);
~~~

Base link cần chứa target search cùng các filter hiện tại. Assembler sẽ điều chỉnh các tham số phân trang theo `PageableHandlerMethodArgumentResolver`. Cách này hữu ích khi page links cần trỏ đến một URI khác với URI của request hiện tại.

### Pageable nhận những tham số nào?

Spring Data Web hỗ trợ các tham số phổ biến:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `page` | Chỉ số trang, mặc định là 0 | page=0 |
| `size` | Số phần tử yêu cầu trong một trang, mặc định thường là 20 | size=20 |
| `sort` | Trường sắp xếp và hướng; có thể lặp tham số để thêm tiêu chí | sort=createdAt,desc |

Có thể đặt mặc định:

~~~java
@PageableDefault(
    size = 20,
    sort = "createdAt",
    direction = Sort.Direction.DESC
)
Pageable pageable
~~~

Đoạn ví dụ cần import `org.springframework.data.domain.Sort` và `org.springframework.data.web.PageableDefault`. Cú pháp sort của Spring Data Web cũng cho phép lặp query parameter, ví dụ `?sort=createdAt,desc&sort=id,desc`.

Giá trị mặc định phải thống nhất giữa endpoint, search template và tài liệu API. Search template có thể để `page`, `size` và `sort` là biến tùy chọn vì server có thể áp dụng default khi client bỏ qua.

### Giới hạn page size

Không nên cho client yêu cầu page size tùy ý. Đặt giới hạn tối đa ở cấu hình Spring Data Web hoặc trong tầng service để bảo vệ database và bộ nhớ. Ví dụ:

~~~java
@PageableDefault(size = 20)
Pageable pageable
~~~

`@PageableDefault` đặt giá trị mặc định, không phải giới hạn tối đa. Giới hạn tối đa cần cấu hình resolver hoặc kiểm tra và chuẩn hóa `Pageable` trước khi truy vấn.

## PagedModel và page metadata

`PagedModel<T>` là representation cho một collection có phân trang. Nó chứa content, metadata về trang và các link điều hướng.

Ví dụ response:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "orderNumber": "ORD-0042",
        "status": "PAID",
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
      "href": "/orders/search?status=PAID&page=1&size=20"
    },
    "first": {
      "href": "/orders/search?status=PAID&page=0&size=20"
    },
    "prev": {
      "href": "/orders/search?status=PAID&page=0&size=20"
    },
    "next": {
      "href": "/orders/search?status=PAID&page=2&size=20"
    },
    "last": {
      "href": "/orders/search?status=PAID&page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 1
  }
}
~~~

Các giá trị trên chỉ minh họa một trang ở giữa kết quả. Trong response thực tế, link có thể là URI tuyệt đối hoặc tương đối tùy cấu hình; các relation không phù hợp với vị trí hiện tại sẽ không xuất hiện.

Metadata page thường cho biết:

- `size`: kích thước trang.
- `totalElements`: tổng số phần tử thỏa truy vấn.
- `totalPages`: tổng số trang.
- `number`: chỉ số trang hiện tại.

Client có thể dùng metadata để hiển thị “trang 2 trên 5” hoặc “85 kết quả”. Tuy nhiên, client nên theo các link để điều hướng vì server có thể thay đổi cách đánh số trang hoặc dùng chiến lược phân trang khác trong tương lai.

### Vai trò của từng relation

| Relation | Có thể xuất hiện khi | Client sử dụng |
| --- | --- | --- |
| `self` | Trang hiện tại có representation | Tải lại trang hiện tại |
| `first` | Collection có trang đầu | Quay về trang đầu |
| `prev` | Trang hiện tại có trang đứng trước | Lùi một trang |
| `next` | Trang hiện tại có trang đứng sau | Tiến một trang |
| `last` | Có thể xác định trang cuối | Đi đến trang cuối |

Trang đầu thường không có `prev`; trang cuối không có `next`. Nếu không có kết quả, response vẫn có thể là một page rỗng với metadata phù hợp, nhưng không có link next/last.

`PagedResourcesAssembler` mặc định tạo `prev` và `next` theo trạng thái trang. `first` và `last` không nhất thiết xuất hiện trong mọi response; có thể bật chúng bằng `setForceFirstAndLastRels(true)` nếu hợp đồng API muốn luôn công bố hai relation này. Vì vậy, client phải kiểm tra sự tồn tại của link trước khi dùng.

Ví dụ cấu hình khi muốn luôn có `first` và `last`:

~~~java
pagedAssembler.setForceFirstAndLastRels(true);
return pagedAssembler.toModel(result, assembler);
~~~

Đặt tùy chọn trên instance `PagedResourcesAssembler` nhận được trong controller trước khi gọi `toModel`. Nếu muốn áp dụng thống nhất cho nhiều endpoint, hãy đóng gói tùy chọn này trong cấu hình hoặc thành phần dùng chung của ứng dụng.

## Giữ filter và sorting khi phân trang

Một search request thường có nhiều tham số:

~~~http
GET /orders/search?q=keyboard&status=PAID&sort=createdAt,desc&page=0&size=20
~~~

Khi client theo link `next`, query state phải được giữ lại:

~~~http
GET /orders/search?q=keyboard&status=PAID&sort=createdAt,desc&page=1&size=20
~~~

Chỉ `page` thay đổi; `q`, `status`, `sort` và `size` tiếp tục giữ nguyên. Nếu link next làm mất filter, client có thể nhận một tập kết quả khác và việc duyệt trang trở nên sai lệch.

`PagedResourcesAssembler` tạo các link phân trang dựa trên request hiện tại và `Pageable`. Với cấu hình Spring MVC/Spring Data chuẩn, các query parameter khác của request thường được giữ khi page link được tạo và các tham số phân trang được cập nhật. Nếu ứng dụng tùy biến URI building, dùng reverse proxy hoặc tự tạo page links, hãy kiểm tra response thực tế để bảo đảm filter và sort không bị mất.

### Khi filter thay đổi, bắt đầu lại từ trang đầu

Giả sử client đang ở trang 4 của truy vấn `status=PAID`. Người dùng đổi filter thành `status=CANCELLED`. Không nên tiếp tục dùng `next` của truy vấn cũ. Client cần mở search template với filter mới và bắt đầu từ trang 0:

~~~text
Truy vấn cũ:
/orders/search?status=PAID&page=4&size=20

Truy vấn mới:
/orders/search?status=CANCELLED&page=0&size=20
~~~

Lý do là tập kết quả và số trang đã thay đổi. Trang 4 có thể không tồn tại trong tập kết quả mới.

### Sort phải ổn định

Nếu nhiều bản ghi có cùng giá trị sort, thứ tự giữa chúng có thể thay đổi giữa các lần truy vấn. Để pagination ổn định, nên bổ sung một trường tie-breaker duy nhất, thường là ID:

~~~http
sort=createdAt,desc&sort=id,desc
~~~

Sort ổn định giảm nguy cơ một item bị lặp hoặc bị bỏ qua khi dữ liệu thay đổi giữa các request. Với dữ liệu thay đổi liên tục hoặc collection rất lớn, cursor/keyset pagination có thể phù hợp hơn offset pagination.

Tên trường trong `sort` là dữ liệu do client gửi. Spring Data phân giải các tên thuộc tính này từ request nhưng không tự xác thực chúng với domain model. Ứng dụng cần whitelist trường được phép sắp xếp và giới hạn số tiêu chí, tránh để client sắp xếp theo thuộc tính nội bộ hoặc gây truy vấn tốn kém.

## Mở rộng search link ở client

Client lấy search relation từ collection resource, sau đó mở rộng URI template:

~~~java
import java.util.Map;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.IanaLinkRelations;

CollectionModel<?> collection = ...;

Link search = collection.getRequiredLink(IanaLinkRelations.SEARCH);
Link firstSearch = search.expand(Map.of(
    "q", "keyboard",
    "status", "PAID",
    "page", 0,
    "size", 20,
    "sort", "createdAt,desc"));
~~~

`expand` thay các biến trong URI template bằng giá trị tương ứng. Các giá trị cần được encode đúng theo URI template; không nối chuỗi query bằng phép cộng thủ công.

Gọi endpoint bằng WebClient:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.core.TypeReferences;
import reactor.core.publisher.Mono;

Mono<PagedModel<EntityModel<OrderResponse>>> firstPage =
    webClient.get()
        .uri(firstSearch.getHref())
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .bodyToMono(
            new TypeReferences.PagedModelType<EntityModel<OrderResponse>>() {});
~~~

Ví dụ giả định `webClient` đã có base URL hoặc search href là URI tuyệt đối, đồng thời hypermedia decoder đã được cấu hình. Generic type reference giúp client giữ được content type của từng item và links của chúng.

## Theo link next và prev

Sau khi nhận `PagedModel`, client tìm link điều hướng:

~~~java
import java.util.Optional;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

PagedModel<EntityModel<OrderResponse>> page = ...;

Optional<Link> next = page.getLink(IanaLinkRelations.NEXT);
Optional<Link> previous = page.getLink(IanaLinkRelations.PREV);
~~~

Nếu link tồn tại, client gọi đúng href:

~~~java
Mono<PagedModel<EntityModel<OrderResponse>>> loadNext(
        PagedModel<EntityModel<OrderResponse>> current) {

    return current.getLink(IanaLinkRelations.NEXT)
        .map(link -> webClient.get()
            .uri(link.getHref())
            .accept(MediaTypes.HAL_JSON)
            .retrieve()
            .bodyToMono(
                new TypeReferences.PagedModelType<EntityModel<OrderResponse>>() {}))
        .orElseGet(Mono::empty);
}
~~~

Đoạn mã thể hiện nguyên tắc điều hướng; ứng dụng cần xử lý trường hợp link tương đối bằng base URL thích hợp và chuyển lỗi HTTP thành trạng thái UI hoặc lỗi nghiệp vụ phù hợp.

Client không nên:

- Tự cộng `page + 1` để tạo URL next.
- Giả định `size` luôn bằng 20.
- Bỏ qua filter hoặc sort đang áp dụng.
- Gọi next khi relation không có.
- Ghép thêm query parameter vào href đã được server cung cấp mà không hiểu semantics của link.

Theo link giúp client thích ứng nếu server thay đổi URI, page size mặc định hoặc chiến lược điều hướng.

## Offset pagination và cursor pagination

`Pageable` và `PagedModel` thường được dùng cho offset/page-number pagination. Request chỉ rõ page và size:

~~~http
GET /orders/search?status=PAID&page=3&size=20
~~~

Offset pagination phù hợp với nhiều màn hình quản trị và collection có quy mô vừa phải. Tuy nhiên, khi dữ liệu được thêm hoặc xóa trong lúc client đang duyệt, offset có thể dịch chuyển khiến kết quả giữa các trang thay đổi.

Cursor pagination dùng một token đại diện vị trí tiếp tục:

~~~http
GET /orders/search?status=PAID&cursor=eyJjcmVhdGVkQXQiOi...
~~~

Response công bố link `next` chứa cursor mới. Client không cần hiểu hoặc tự tạo token; nó chỉ theo link:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/search?status=PAID"
    },
    "next": {
      "href": "/orders/search?status=PAID&cursor=eyJjcmVhdGVkQXQiOi..."
    }
  }
}
~~~

Cursor pagination có thể ổn định và hiệu quả hơn với collection lớn hoặc thay đổi thường xuyên. `PagedModel` và `PagedResourcesAssembler` được thiết kế xoay quanh page metadata; cursor API có thể dùng `CollectionModel` hoặc representation tùy chỉnh với `next`/`prev` links và metadata cursor riêng. Không nên ép cursor token vào trường `page` nếu semantics không phải page number.

## Collection rỗng và các trang biên

Search pagination cần xác định rõ hành vi ở những trường hợp đặc biệt:

| Trường hợp | Hành vi mong đợi |
| --- | --- |
| Không có filter | Trả trang đầu theo default và size |
| Filter khớp nhiều kết quả | Trả page cùng links điều hướng |
| Filter không khớp kết quả | Trả page rỗng hợp lệ |
| Trang đầu | Không có `prev` |
| Trang cuối | Không có `next` |
| Page vượt quá tổng số trang | Theo chính sách API: page rỗng hoặc lỗi validation |
| Size bằng 0 hoặc âm | Từ chối hoặc chuẩn hóa theo chính sách đã công bố |
| Size quá lớn | Giới hạn ở mức tối đa |

Không nên trả 404 chỉ vì filter không có kết quả. Search collection vẫn tồn tại; tập kết quả của truy vấn chỉ đang rỗng. Cần phân biệt trường hợp endpoint hoặc tài nguyên cha không tồn tại với trường hợp truy vấn hợp lệ không tìm thấy item.

### Tổng số kết quả có thể tốn chi phí

`Page<T>` thường cần tổng số phần tử để tạo `totalElements` và `totalPages`. Với truy vấn phức tạp hoặc dữ liệu rất lớn, phép đếm có thể tốn kém. Có thể cân nhắc `Slice<T>` cùng `SlicedModel<T>` và `SlicedResourcesAssembler` nếu client chỉ cần biết còn trang tiếp theo hay không. Khi đổi loại phân trang, representation và metadata cần phản ánh đúng semantics mới.

## Kiểm thử search pagination

Nên kiểm thử cả hành vi tìm kiếm, page metadata và links. Chỉ xác minh số phần tử trong `_embedded` là chưa đủ.

### Kiểm thử endpoint trả PagedModel

~~~java
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
class OrderSearchPaginationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsPagedSearchResultsWithNavigationLinks() throws Exception {
        mockMvc.perform(get("/orders/search")
                .accept(MediaTypes.HAL_JSON)
                .param("status", "PAID")
                .param("page", "0")
                .param("size", "2"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Test giả định dữ liệu chuẩn bị có ít nhất một đơn hàng PAID và relation collection được cấu hình là `orders`. Nếu có hơn hai kết quả, trang đầu còn có thể chứa `next`.

### Kiểm tra filter được giữ trong page links

Với dữ liệu có nhiều hơn một trang, kiểm tra href của `next` vẫn chứa filter và sort:

~~~java
mockMvc.perform(get("/orders/search")
        .accept(MediaTypes.HAL_JSON)
        .param("status", "PAID")
        .param("sort", "createdAt,desc")
        .param("page", "0")
        .param("size", "2"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.next.href").value(
        org.hamcrest.Matchers.allOf(
            org.hamcrest.Matchers.containsString("status=PAID"),
            org.hamcrest.Matchers.containsString("sort=createdAt")
        )));
~~~

Trong test thực tế, có thể parse href thành URI và kiểm tra từng query parameter để tránh phụ thuộc thứ tự hoặc encoding.

### Kiểm tra search relation

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.href").exists());
~~~

Nếu API dùng URI template, hãy xác minh link được đánh dấu `templated` và có các biến mong đợi theo output của media type:

~~~json
{
  "_links": {
    "search": {
      "href": "/orders/search{?q,status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Các trường hợp nên kiểm thử:

1. Collection resource công bố relation `search`.
2. Search template có đủ biến filter, page, size và sort.
3. Client mở rộng template tạo đúng request URI.
4. Endpoint áp dụng filter trước khi phân trang.
5. Page metadata phản ánh đúng trang và tổng kết quả.
6. `next` và `prev` chỉ xuất hiện khi có trang tương ứng.
7. Page links giữ nguyên filter, sort và page size.
8. Filter mới bắt đầu truy vấn từ trang đầu.
9. Collection rỗng vẫn trả representation hợp lệ.
10. Page size vượt giới hạn được xử lý theo chính sách.
11. Client theo href thay vì tự ghép URI.
12. Response có Content-Type phù hợp với `Accept`.

## Những sai lầm thường gặp

**Chỉ công bố endpoint search mà không có relation.** Client phải biết URI cụ thể. Dùng relation `search` để client khám phá thao tác.

**Nhầm search link với next link.** Search link bắt đầu một truy vấn; next link tiếp tục truy vấn hiện tại ở trang sau.

**Tự ghép URL trang kế tiếp.** Theo relation `next` hoặc `prev` do server trả về để tránh phụ thuộc cấu trúc URI.

**Làm mất filter khi tạo page links.** Giữ query state của search trong `self`, `first`, `prev`, `next` và `last`.

**Đổi filter nhưng giữ page cũ.** Khi tiêu chí tìm kiếm thay đổi, bắt đầu lại từ trang đầu của tập kết quả mới.

**Chỉ dùng page metadata để điều hướng.** Metadata hữu ích để hiển thị, nhưng link mới là hướng dẫn điều hướng do server công bố.

**Không giới hạn page size.** Client có thể yêu cầu payload quá lớn. Đặt default và maximum rõ ràng.

**Sắp xếp không ổn định.** Khi nhiều bản ghi có cùng giá trị sort, thêm tie-breaker duy nhất để giảm lặp hoặc bỏ sót item giữa các trang.

**Dùng Page cho mọi collection.** Nếu không cần tổng số phần tử, cân nhắc Slice hoặc cursor pagination để tránh truy vấn đếm tốn kém.

**Trả 404 khi search không có kết quả.** Một truy vấn hợp lệ không có item thường nên trả page rỗng.

## Kết luận

Search pagination kết hợp search relation và page navigation links. Search link công bố URI template để client bắt đầu truy vấn với filter, sort, page và size; endpoint trả `PagedModel` chứa embedded items, page metadata và các relation như `self`, `first`, `prev`, `next`, `last`. Spring Data `Pageable` nhận tham số phân trang, còn `PagedResourcesAssembler` chuyển `Page<T>` thành representation hypermedia.

Hãy giữ filter và sort trong các page links, bắt đầu lại từ trang đầu khi filter thay đổi, giới hạn page size và dùng sort ổn định. Client nên mở rộng search template rồi theo link next/prev do server trả về thay vì tự tạo URL. Kiểm thử cả kết quả lọc, metadata page, sự tồn tại của relation và việc giữ query state để bảo đảm quá trình duyệt kết quả nhất quán.

Tài liệu tham khảo:

- [Spring HATEOAS Reference — Pagination](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.paging).
- [Spring HATEOAS Reference — Links and URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links).
- [Spring Data Commons Reference — Web support and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html).
- [Spring Data Commons API — PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html).
- [IANA Link Relations — search](https://www.iana.org/assignments/link-relations/link-relations.xhtml).
