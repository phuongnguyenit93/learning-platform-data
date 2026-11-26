# Link chuyển trang

Một API trả về danh sách lớn thường chia dữ liệu thành nhiều trang để giảm kích thước response và chi phí truy vấn. Khi dùng Spring HATEOAS, response có thể công bố các link `first`, `prev`, `self`, `next` và `last` để client điều hướng giữa các trang. Client chỉ cần theo `href` mà server trả về, không phải tự tính số trang hoặc ghép query parameter.

Spring Data cung cấp `Page<T>` để biểu diễn một trang dữ liệu cùng thông tin tổng số phần tử và tổng số trang. Spring HATEOAS cung cấp `PagedModel<T>` để biểu diễn nội dung, metadata phân trang và link điều hướng. `PagedResourcesAssembler<T>` chuyển `Page<T>` thành `PagedModel` và tự tạo các link dựa trên request hiện tại cùng cấu hình `Pageable`.

Bài học này thuộc chương **Pagination** trong module **SPRING_HATEOAS**, tập trung vào cách tạo và sử dụng link chuyển trang, vai trò của `PagedModel`, `PageMetadata`, `PagedResourcesAssembler`, cách giữ nguyên filter/sort khi điều hướng và cách client theo link để tải trang tiếp theo.

Sau bài học, bạn có thể:

- Giải thích vì sao API phân trang nên công bố link hypermedia.
- Phân biệt `Page`, `Slice`, `PagedModel` và `SlicedModel`.
- Tạo link `first`, `prev`, `self`, `next`, `last` bằng `PagedResourcesAssembler`.
- Tùy chỉnh assembler để dùng self link riêng và điều khiển link first/last.
- Hiểu metadata `size`, `number`, `totalElements`, `totalPages`.
- Giữ query parameter, sort và filter khi chuyển trang.
- Viết client theo `next.href` thay vì tự dựng URL.
- Kiểm thử link phân trang, trang đầu, trang cuối và collection rỗng.

## 1. Vì sao cần link chuyển trang?

Giả sử API có 2.500 đơn hàng. Nếu trả toàn bộ dữ liệu trong một response, server phải đọc và serialize nhiều bản ghi; client cũng phải tải, phân tích và giữ một payload lớn. Phân trang giới hạn số phần tử trong mỗi response.

Một request có thể là:

```http
GET /orders?page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

Response có thể chứa 20 đơn hàng, metadata của trang và các link điều hướng. Ví dụ dưới đây có `self` do ứng dụng công bố cùng các link phân trang:

```json
{
  "_embedded": {
    "orders": [
      { "id": 42, "status": "PENDING" },
      { "id": 41, "status": "PAID" }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/orders?page=0&size=20&sort=createdAt,desc"
    },
    "next": {
      "href": "https://api.example.com/orders?page=1&size=20&sort=createdAt,desc"
    },
    "last": {
      "href": "https://api.example.com/orders?page=124&size=20&sort=createdAt,desc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 2500,
    "totalPages": 125,
    "number": 0
  }
}
```

Đây là response minh họa theo cấu trúc HAL; ví dụ giả định ứng dụng đã bật `setForceFirstAndLastRels(true)` để có `last` ngay trên trang đầu và tự công bố `self`. Các link thực tế phụ thuộc trạng thái trang và cấu hình ứng dụng. Trang đầu không có `prev`; trang cuối không có `next`. Client không cần suy ra URL trang cuối từ `totalPages`; nếu server cung cấp relation `last`, hãy theo link đó.

Link chuyển trang đem lại ba lợi ích:

- **Tách client khỏi quy tắc phân trang:** client không cần biết tên query parameter, page index bắt đầu từ 0 hay 1, hoặc cách mã hóa sort.
- **Giữ nguyên ngữ cảnh truy vấn:** server có thể tạo link tiếp theo với các filter, sort và tham số hiện tại.
- **Hỗ trợ tiến hóa API:** server có thể đổi route hoặc cách biểu diễn tham số mà client vẫn điều hướng theo link.

## 2. Page, Slice và PagedModel

Các kiểu dữ liệu có vai trò khác nhau:

| Kiểu | Package | Vai trò |
|---|---|---|
| `Page<T>` | `org.springframework.data.domain` | Kết quả truy vấn phân trang, có nội dung, số trang hiện tại và thông tin tổng số phần tử/trang. |
| `Slice<T>` | `org.springframework.data.domain` | Một lát dữ liệu, cho biết có trang trước/tiếp theo hay không; không yêu cầu tổng số phần tử và tổng số trang. |
| `PagedModel<T>` | `org.springframework.hateoas` | Representation model có nội dung, page metadata và link hypermedia. |
| `SlicedModel<T>` | `org.springframework.hateoas` | Representation model cho `Slice`, tập trung vào metadata và điều hướng trước/sau. |

`Page<T>` thường cần truy vấn đếm để xác định `totalElements` và `totalPages`. `Slice<T>` có thể tránh truy vấn đếm nếu ứng dụng chỉ cần biết còn dữ liệu tiếp theo hay không. Vì vậy, `Page` phù hợp khi giao diện cần tổng số trang hoặc link `last`; `Slice` phù hợp khi chỉ cần nút tiếp tục/tải thêm.

`PagedModel` không phải repository result. Nó là lớp biểu diễn HTTP của Spring HATEOAS, có thể chứa `EntityModel<T>` hoặc một kiểu representation khác. `PagedResourcesAssembler` chuyển `Page` thành `PagedModel` và gắn các link phù hợp.

## 3. PageMetadata mô tả trang hiện tại

`PagedModel` có `PageMetadata` để mô tả kích thước và vị trí của trang:

| Property JSON | Ý nghĩa |
|---|---|
| `size` | Số phần tử tối đa được yêu cầu trong một trang. |
| `number` | Chỉ số trang hiện tại, thường bắt đầu từ 0 với cấu hình mặc định. |
| `totalElements` | Tổng số phần tử phù hợp truy vấn. |
| `totalPages` | Tổng số trang theo page size hiện tại. |

Ví dụ metadata:

```json
{
  "page": {
    "size": 20,
    "number": 2,
    "totalElements": 2500,
    "totalPages": 125
  }
}
```

Metadata giúp client hiển thị thông tin như “trang 3 trên 125” hoặc “2.500 kết quả”. Tuy nhiên, metadata không thay thế link. Khi server thay đổi cách đánh số trang hoặc route, client nên dùng link được công bố để điều hướng.

`number` trong metadata là zero-based theo `Page`/`Pageable` mặc định: `0` là trang đầu. Nếu ứng dụng cấu hình page index bắt đầu từ 1 cho HTTP request, cần phân biệt giá trị query parameter với cách metadata của đối tượng `Page` được tạo. Hãy kiểm tra hợp đồng thực tế của ứng dụng và tránh tự cộng/trừ chỉ số trong client.

## 4. Các relation dùng trong pagination

Các relation phổ biến cho điều hướng trang:

| Relation | Ý nghĩa | Thường xuất hiện khi |
|---|---|---|
| `first` | Trang đầu tiên | Có trang đầu để điều hướng tới; có thể phụ thuộc cấu hình assembler. |
| `prev` | Trang ngay trước trang hiện tại | Trang hiện tại không phải trang đầu. |
| `self` | Trang hiện tại | Ứng dụng có thể công bố rõ ràng; không nên mặc định rằng assembler luôn thêm relation này. |
| `next` | Trang ngay sau trang hiện tại | Trang hiện tại chưa phải trang cuối. |
| `last` | Trang cuối cùng | Có trang cuối để điều hướng tới; có thể phụ thuộc cấu hình assembler. |

Ví dụ một trang ở giữa có thể chứa:

```json
{
  "_links": {
    "first": { "href": "/orders?page=0&size=20" },
    "prev": { "href": "/orders?page=1&size=20" },
    "self": { "href": "/orders?page=2&size=20" },
    "next": { "href": "/orders?page=3&size=20" },
    "last": { "href": "/orders?page=9&size=20" }
  }
}
```

`first`, `prev`, `self`, `next` và `last` là relation key ở `_links`. Mỗi `href` là URI mà client cần gọi. `PagedResourcesAssembler` tập trung tạo các link phân trang `prev`/`next` và tùy chọn `first`/`last`; nếu hợp đồng yêu cầu `self`, hãy bảo đảm representation có relation đó. Không nên đặt các link này thành property cấp cao nhất như `nextPageUrl` nếu response được thiết kế theo HAL.

## 5. Dùng PagedResourcesAssembler trong controller

Với Spring Data, cách thông dụng là nhận `Pageable` và `PagedResourcesAssembler<T>` làm tham số controller. Spring Data Web cung cấp các đối tượng này thông qua cơ chế argument resolver; trong Spring Boot, cấu hình thường được kích hoạt tự động khi dùng starter phù hợp.

Trong ứng dụng Spring MVC không dùng auto-configuration của Spring Boot, có thể bật web support bằng `@EnableSpringDataWebSupport`. Khi Spring HATEOAS có trên classpath, cấu hình này phát hiện và đăng ký các thành phần tích hợp HATEOAS, bao gồm resolver hỗ trợ tạo URI phân trang.

Ví dụ repository:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
}
```

Controller có thể chuyển `Page<Order>` thành `PagedModel<EntityModel<OrderResponse>>`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler orderAssembler;

    OrderController(OrderRepository repository, OrderModelAssembler orderAssembler) {
        this.repository = repository;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    PagedModel<EntityModel<OrderResponse>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = repository.findAll(pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
```

`OrderModelAssembler` là `RepresentationModelAssembler<Order, EntityModel<OrderResponse>>` chịu trách nhiệm chuyển từng entity thành representation của một đơn hàng. `PagedResourcesAssembler` xử lý phần bao ngoài: nội dung trang, `PageMetadata` và các link chuyển trang.

Khi `toModel(page, orderAssembler)` được gọi, assembler sẽ dùng request URI hiện tại và cấu hình `Pageable` để tạo link. Các query parameter được giữ lại phù hợp với request hiện tại, gồm page, size, sort và các filter đã có trong URI.

## 6. PagedResourcesAssembler tạo link nào?

`PagedResourcesAssembler` có các overload `toModel` thường dùng:

| Method | Mục đích |
|---|---|
| `toModel(page)` | Tạo `PagedModel<EntityModel<T>>`, bọc mỗi phần tử bằng `EntityModel`. |
| `toModel(page, assembler)` | Dùng `RepresentationModelAssembler<T, R>` để tạo representation cho từng phần tử. |
| `toModel(page, selfLink)` | Dùng self link được cung cấp làm URI cơ sở để tạo link phân trang. |
| `toModel(page, assembler, selfLink)` | Kết hợp assembler tùy chỉnh cho item và self link tùy chỉnh. |
| `toEmptyModel(page, type)` | Tạo mô hình trang rỗng có thông tin kiểu embedded resource. |

Với một `Page` có nhiều trang, `PagedResourcesAssembler` có thể tạo `prev` và `next` dựa trên trạng thái trang. Link `first` và `last` mặc định chỉ xuất hiện cùng với `prev` và `next`; hành vi này có thể thay đổi bằng `setForceFirstAndLastRels(true)`.

Để bật `first` và `last`, gọi `setForceFirstAndLastRels(true)` trên `PagedResourcesAssembler` trong lúc cấu hình instance được ứng dụng quản lý. Đây là tùy chọn của assembler, không phải một query parameter. Khi tự tạo assembler, hãy dùng cùng `HateoasPageableHandlerMethodArgumentResolver` đang phân tích `Pageable`; không tạo một resolver khác cấu hình vì hai phía có thể sinh và đọc query parameter không đồng nhất. Cách đăng ký bean tùy thuộc cấu hình Spring Data Web của ứng dụng và phiên bản đang dùng.

## 7. Dùng self link riêng làm cơ sở cho pagination

Mặc định, assembler dùng URI của request hiện tại để tạo link. Nếu trang dữ liệu cần dùng một endpoint khác làm cơ sở, có thể truyền self link vào `toModel`:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link pageSelfLink = Link.of("https://api.example.com/public/orders")
        .withSelfRel();

PagedModel<EntityModel<OrderResponse>> model =
        pagedAssembler.toModel(page, orderAssembler, pageSelfLink);

if (!model.hasLink(IanaLinkRelations.SELF)) {
    model.add(pageSelfLink);
}

return model;
```

Các link `first`, `prev`, `next` và `last` sẽ được xây dựng dựa trên URI cơ sở đó. `selfLink` là URI cơ sở để tính link chuyển trang; nếu muốn response có relation `self`, đoạn code kiểm tra và thêm link này khi assembler chưa có. Cách này hữu ích khi endpoint công khai khác URI của request nội bộ, hoặc khi representation được tạo từ một route canonical riêng.

Self link cần chứa các filter và sort có ý nghĩa đối với tập kết quả. Nếu truyền một URI không có query parameter cần thiết, các link chuyển trang có thể làm mất ngữ cảnh truy vấn. Hãy kiểm tra URI kết quả thay vì chỉ xác nhận relation đã xuất hiện.

Không hard-code host production trong assembler dùng chung. Nếu cần base URI khác, hãy lấy từ cấu hình hoặc cơ chế forwarded header đã được thiết lập đúng cho reverse proxy.

## 8. Giữ filter và sort khi chuyển trang

Một request có thể gồm nhiều tham số ngoài `page` và `size`:

```http
GET /orders?page=2&size=20&sort=createdAt,desc&status=PAID&customerId=7
```

Khi tạo link `next`, client mong đợi server giữ lại các điều kiện `sort`, `status` và `customerId` để trang tiếp theo thuộc cùng tập kết quả. `PagedResourcesAssembler` sử dụng request URI hiện tại làm cơ sở và cấu hình pageable resolver để tạo tham số phân trang phù hợp.

Controller cần nhận và áp dụng filter vào truy vấn thực tế. Ví dụ:

```java
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
PagedModel<EntityModel<OrderResponse>> search(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(required = false) Long customerId,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(status, customerId, pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

Ở đây service phải dùng `status` và `customerId` khi truy vấn. Việc giữ query parameter trong href không tự động khiến repository áp dụng filter; controller/service phải hiểu và thực thi các tham số đó.

Kiểm thử link `next.href` cần xác nhận các filter/sort vẫn còn. Nếu client tự tạo URL từ page index mới, rất dễ bỏ sót một tham số và chuyển sang tập kết quả khác.

## 9. Cấu hình Pageable và định dạng query parameter

Theo mặc định, Spring Data Web thường dùng `page`, `size` và `sort` để nhận tham số phân trang:

```text
/orders?page=0&size=20&sort=createdAt,desc
```

`PageableHandlerMethodArgumentResolver` chuyển các tham số đó thành `Pageable`. `PagedResourcesAssembler` dùng cùng cơ chế resolver để tạo link có thể được phân giải ở request kế tiếp. Nếu ứng dụng đổi tên tham số, đổi cách đánh số trang hoặc giới hạn page size, cần bảo đảm resolver dùng để nhận request và assembler dùng để sinh link có cùng cấu hình.

Ví dụ đặt giá trị mặc định cho một endpoint:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;

@GetMapping
PagedModel<EntityModel<OrderResponse>> all(
        @PageableDefault(size = 30, sort = "createdAt") Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = repository.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

`@PageableDefault` đặt giá trị mặc định khi client không truyền tham số; nó không buộc client luôn dùng page size đó. Hãy cấu hình giới hạn page size ở resolver để tránh request yêu cầu kích thước quá lớn.

Nếu tùy chỉnh tham số phân trang toàn cục, hãy dùng cơ chế cấu hình Spring Data Web của phiên bản dự án. Không chỉ đổi tên query parameter ở controller hoặc tự sửa chuỗi href sau khi assembler tạo link, vì điều đó dễ khiến link không khớp với cách server phân tích request.

## 10. Link ở trang đầu, trang giữa và trang cuối

Các link phụ thuộc trạng thái của `Page`:

| Trạng thái | Link thường có |
|---|---|
| Trang đầu, còn trang sau | `next`; `first`/`last` tùy cấu hình; `self` nếu ứng dụng công bố. |
| Trang giữa | `prev`, `next`; `first`/`last` theo cấu hình; `self` nếu ứng dụng công bố. |
| Trang cuối | `prev`; `first`/`last` tùy cấu hình; `self` nếu ứng dụng công bố. |
| Chỉ có một trang | `first`/`last` có thể được bật theo cấu hình; `self` nếu ứng dụng công bố. |
| Không có phần tử | Metadata phản ánh trang rỗng; link phụ thuộc page state và cấu hình. |

Đừng giả định response luôn có đủ năm relation. Ví dụ, `next` không có ở trang cuối và `prev` không có ở trang đầu. Client cần kiểm tra link có tồn tại trước khi hiển thị nút điều hướng.

Nếu bật `setForceFirstAndLastRels(true)`, assembler có thể công bố `first` và `last` ngay cả khi trang hiện tại chưa có `prev` hoặc `next`. Đây là lựa chọn hợp đồng; client vẫn nên xử lý trường hợp một relation không xuất hiện.

## 11. Client điều hướng bằng href

Client nên tìm relation `next` trong `_links` và theo href của nó. Ví dụ JavaScript:

```javascript
async function loadNextPage(document) {
  const nextHref = document?._links?.next?.href;

  if (!nextHref) {
    return null;
  }

  const response = await fetch(nextHref, {
    headers: { Accept: "application/hal+json" }
  });

  if (!response.ok) {
    throw new Error(`Không tải được trang tiếp theo: HTTP ${response.status}`);
  }

  return response.json();
}
```

Client không cần biết `page` tăng bao nhiêu, tên tham số phân trang là gì hoặc server có dùng offset pagination hay không. Nếu link `next` vắng mặt, không có trang tiếp theo theo representation hiện tại.

Để xây dựng nút “Trang trước”, dùng relation `prev`; để về đầu danh sách, dùng `first`; để đến cuối danh sách, dùng `last`. Với giao diện tải thêm, chỉ cần `next` và có thể tiếp tục theo link mới trong response tiếp theo.

Client cũng nên giữ các header cần thiết khi theo link, ví dụ `Accept`, authorization hoặc correlation ID. Không tự chuyển credential tới một origin khác nếu link trỏ ra ngoài domain tin cậy.

## 12. Slice và SlicedModel khi không cần tổng số trang

Nếu chỉ cần biết có dữ liệu tiếp theo hay không, dùng `Slice<T>` thay vì `Page<T>` có thể giảm chi phí đếm. Spring HATEOAS cung cấp `SlicedResourcesAssembler<T>` để chuyển `Slice<T>` thành `SlicedModel`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.web.SlicedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.SlicedModel;

@GetMapping("/recent")
SlicedModel<EntityModel<OrderResponse>> recent(
        Pageable pageable,
        SlicedResourcesAssembler<Order> slicedAssembler) {

    Slice<Order> slice = orderService.findRecent(pageable);
    return slicedAssembler.toModel(slice, orderAssembler);
}
```

`SlicedModel` có thể cung cấp link `prev` và `next` theo khả năng của `Slice`. Vì `Slice` không có `totalElements` và `totalPages`, client không nên hiển thị tổng số trang hoặc nút “đến trang cuối” nếu server không cung cấp thông tin đó.

Chọn `Page` khi tổng số kết quả là một phần quan trọng của trải nghiệm và chi phí đếm chấp nhận được. Chọn `Slice` khi giao diện chỉ cần điều hướng tuần tự và muốn tránh truy vấn tổng số bản ghi.

## 13. Phân trang thủ công với PagedModel

Nếu dữ liệu không đến từ Spring Data `Page`, có thể tạo `PagedModel` trực tiếp. Ví dụ:

```java
import java.util.List;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.PagedModel;

List<EntityModel<OrderResponse>> content = orders.stream()
        .map(orderAssembler::toModel)
        .toList();

PagedModel.PageMetadata metadata = new PagedModel.PageMetadata(
        pageSize,
        pageNumber,
        totalElements,
        totalPages
);

PagedModel<EntityModel<OrderResponse>> model = PagedModel.of(content, metadata);
```

Sau khi tạo metadata, cần tự thêm link điều hướng phù hợp:

```java
model.add(Link.of("/orders?page=0&size=20").withRel("first"));
model.add(Link.of("/orders?page=2&size=20").withRel("prev"));
model.add(Link.of("/orders?page=3&size=20").withRel("next"));
model.add(Link.of("/orders?page=9&size=20").withRel("last"));
```

Đây chỉ là minh họa API `PagedModel.of`; ứng dụng phải tự tính link đúng theo page state, filter, sort, base URI và cấu hình đánh số trang. Với dữ liệu Spring Data, ưu tiên `PagedResourcesAssembler` để tránh tự triển khai lại các quy tắc này.

## 14. Phân biệt PagedModel của Spring HATEOAS và Spring Data

Có hai kiểu `PagedModel` mang tên giống nhau nhưng thuộc package và mục đích khác nhau:

| Kiểu | Package | Đặc điểm |
|---|---|---|
| Hypermedia `PagedModel` | `org.springframework.hateoas.PagedModel` | Representation model có metadata và có thể có link hypermedia. |
| Simplified `PagedModel` | `org.springframework.data.web.PagedModel` | DTO wrapper cho `Page`, chủ yếu công bố content và metadata trang, không tự cung cấp link điều hướng HATEOAS. |

Khi mục tiêu là link chuyển trang `first`, `prev`, `next`, `last`, hãy dùng `org.springframework.hateoas.PagedModel` cùng `PagedResourcesAssembler`. Tránh import nhầm `org.springframework.data.web.PagedModel` chỉ vì tên lớp giống nhau.

## 15. Kiểm thử link chuyển trang

Kiểm thử nên xác nhận nội dung, metadata, relation và query parameter. Ví dụ MockMvc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPaginationLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void firstPageContainsNextLinkAndKeepsFilterAndSort() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "0")
                        .param("size", "20")
                        .param("sort", "createdAt,desc")
                        .param("status", "PAID")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href", containsString("page=0")))
                .andExpect(jsonPath("$._links.next.href", containsString("page=1")))
                .andExpect(jsonPath("$._links.next.href", containsString("size=20")))
                .andExpect(jsonPath("$._links.next.href", containsString("status=PAID")))
                .andExpect(jsonPath("$._links.next.href", containsString("sort=createdAt")));
    }
}
```

Ví dụ giả định endpoint trả HAL JSON, dữ liệu fixture có nhiều hơn một trang và filter `status` được áp dụng trong service. Khi test URL, nên kiểm tra các query parameter cần thiết thay vì phụ thuộc host/port.

Nên bổ sung test cho:

- Trang đầu không có `prev`.
- Trang cuối không có `next`.
- Trang giữa có cả `prev` và `next`.
- `first`/`last` theo cấu hình `setForceFirstAndLastRels`.
- Collection rỗng và chỉ có một trang.
- Filter, sort và page size được giữ trong các href.
- `Slice` chỉ công bố khả năng điều hướng phù hợp.
- Client không gọi link `next` khi relation không tồn tại.

## 16. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả `Page<T>` trực tiếp và kỳ vọng có link HAL | Response có thể chỉ có cấu trúc page DTO hoặc serialization không ổn định. | Dùng `PagedResourcesAssembler` tạo `org.springframework.hateoas.PagedModel`. |
| Tự tăng `page` trong client | Có thể làm mất filter, sort hoặc sai tên tham số. | Theo `next.href` do server trả về. |
| Cho rằng luôn có đủ first/prev/next/last | Client lỗi ở trang đầu, cuối hoặc tập dữ liệu chỉ có một trang. | Kiểm tra từng relation trước khi hiển thị nút. |
| Quên áp dụng filter trong service | Link giữ filter nhưng dữ liệu trang không lọc đúng. | Controller/service phải thực thi mọi filter. |
| Dùng resolver khác cấu hình với assembler | Link sinh ra không được request resolver nhận đúng. | Dùng chung cấu hình Pageable resolver. |
| Dùng Page khi không cần tổng số trang | Phát sinh truy vấn đếm không cần thiết. | Cân nhắc `Slice` và `SlicedResourcesAssembler`. |
| Import nhầm `PagedModel` của Spring Data | Response thiếu link chuyển trang. | Import `org.springframework.hateoas.PagedModel`. |
| Hard-code base URI hoặc query string | Link sai ở môi trường khác hoặc mất ngữ cảnh truy vấn. | Dùng request URI, forwarded header hoặc self link cấu hình. |
| Không giới hạn page size | Client có thể yêu cầu payload quá lớn. | Cấu hình giới hạn page size ở resolver/service. |

## 17. Quy trình thiết kế link chuyển trang

Khi xây dựng endpoint phân trang bằng Spring HATEOAS, hãy thực hiện theo trình tự:

1. Chọn `Page<T>` nếu cần tổng số trang hoặc `Slice<T>` nếu chỉ cần biết còn dữ liệu tiếp theo.
2. Nhận `Pageable` từ Spring Data Web và thực thi truy vấn theo page, size, sort cùng filter.
3. Tạo assembler cho từng item nếu cần DTO và link riêng của phần tử.
4. Dùng `PagedResourcesAssembler.toModel(page, itemAssembler)` để tạo `PagedModel`.
5. Nếu cần URI cơ sở riêng, truyền self link vào overload `toModel`.
6. Cấu hình `first` và `last` theo nhu cầu client; không giả định mọi relation luôn tồn tại.
7. Bảo đảm query parameter và cấu hình pageable resolver được giữ đồng nhất.
8. Hướng dẫn client theo relation `next`, `prev`, `first` hoặc `last` thay vì tự ghép URL.
9. Kiểm thử trang đầu, giữa, cuối, rỗng, filter và sort qua response HAL.

Link chuyển trang biến phân trang thành một luồng điều hướng hypermedia. Khi server công bố đúng relation và href cho từng trạng thái trang, client có thể tiếp tục truy vấn mà không phụ thuộc vào cách server đánh số trang, đặt tên tham số hoặc tổ chức route.

## Tài liệu tham khảo

- [Spring Data – Hypermedia Support for Page and Slice](https://docs.spring.io/spring-data/rest/reference/data-commons/repositories/core-extensions.html)
- [Spring Data – PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring HATEOAS – PagedModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [Spring Data – PageableHandlerMethodArgumentResolver API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html)
