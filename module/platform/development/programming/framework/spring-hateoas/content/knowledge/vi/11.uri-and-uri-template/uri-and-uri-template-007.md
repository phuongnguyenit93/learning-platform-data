# Template và query parameter

Trong REST API, URI template mô tả một URI có các biến chưa được điền giá trị. Ví dụ `/orders{?status,page,size}` biểu thị một đường dẫn tới collection đơn hàng cùng các query parameter tùy chọn để lọc và phân trang. Client có thể mở rộng template bằng các giá trị phù hợp để tạo URI hoàn chỉnh.

Spring HATEOAS có thể công bố URI template dưới dạng một hypermedia link. Khi serialize thành HAL JSON, link có template được biểu diễn với `templated: true`. Nhờ vậy client khám phá được các tham số mà API hỗ trợ thay vì tự đoán query parameter hoặc ghép URL theo quy ước nội bộ.

## Cấu trúc URI và query parameter

Một URI thường có các thành phần: scheme, authority, path, query và fragment. Ví dụ:

```text
https://api.example.com/orders/42?expand=customer#summary
```

- `https` là scheme.
- `api.example.com` là authority/host.
- `/orders/42` là path, thường nhận diện tài nguyên đơn hàng `42`.
- `expand=customer` là query, bổ sung tham số cho request.
- `summary` là fragment, được xử lý ở phía client và không được gửi trong HTTP request tới server.

**Path parameter** thường xác định tài nguyên hoặc một phần của đường dẫn, ví dụ `/orders/42`. **Query parameter** thường chọn tập con, sắp xếp, phân trang hoặc điều chỉnh cách server trả representation, ví dụ `/orders?status=PENDING&page=0&size=20`.

Query parameter không tự động mang một ý nghĩa cố định trong REST. Ý nghĩa của `status`, `page`, `size`, `sort` hoặc `expand` do hợp đồng API định nghĩa. Server cần công bố tên, kiểu dữ liệu, giá trị mặc định, giới hạn và cách kết hợp các tham số.

## URI template và RFC 6570

URI Template được đặc tả trong RFC 6570. Một template kết hợp URI cơ sở với các biểu thức biến. Biểu thức có dấu ngoặc nhọn `{...}` cho biết vị trí và cách mở rộng biến. Một số dạng thường gặp:

| Cú pháp | Ý nghĩa | Kết quả minh họa |
| --- | --- | --- |
| `/orders{/id}` | Mở rộng biến thành một path segment | `/orders/42` |
| `/orders{?status}` | Thêm query parameter `status` | `/orders?status=PENDING` |
| `/orders{?status,page,size}` | Thêm nhiều query parameter | `/orders?status=PENDING&page=0&size=20` |
| `/orders{&sort}` | Thêm query parameter vào query đã có | `/orders?page=0&sort=createdAt` |
| `/orders{?tag*}` | Mở rộng danh sách thành các tham số lặp | `/orders?tag=java&tag=spring` |

Toán tử `?` bắt đầu phần query; toán tử `&` bổ sung tham số vào query hiện có; `{/...}` mở rộng biến trong path. Dấu `*` (explode modifier) cho phép một danh sách được mở rộng thành nhiều cặp tên/giá trị, hữu ích khi API chấp nhận query parameter lặp.

Một template không phải URI hoàn chỉnh. Client cần điền các biến theo cú pháp của template trước khi gửi request. Nếu biến tùy chọn không có giá trị, biểu thức tương ứng có thể bị bỏ qua khi mở rộng. Client không nên tự thay dấu ngoặc nhọn bằng chuỗi tùy ý hoặc nối query string bằng tay.

## Template cho query parameter tùy chọn

Giả sử API có endpoint tìm kiếm đơn hàng với các tham số:

| Tham số | Kiểu/giá trị | Ý nghĩa |
| --- | --- | --- |
| `status` | Chuỗi hoặc không có | Lọc theo trạng thái đơn hàng |
| `page` | Số nguyên, mặc định `0` | Chỉ số trang, bắt đầu từ `0` |
| `size` | Số nguyên dương, có giới hạn | Số phần tử tối đa trên một trang |
| `sort` | Một hoặc nhiều quy tắc sắp xếp | Trường và chiều sắp xếp, ví dụ `createdAt,desc` |

Link template có thể là:

```text
/orders{?status,page,size,sort}
```

Client có thể mở rộng chỉ với `status`, hoặc truyền thêm `page`, `size` và `sort`. Nếu không có `status`, tham số đó được bỏ qua. Server vẫn áp dụng giá trị mặc định cho `page` và `size` theo hợp đồng của endpoint.

Ví dụ một số URI sau có thể được tạo từ cùng template:

```text
/orders
/orders?status=PENDING
/orders?status=PENDING&page=0&size=20
/orders?page=2&size=50&sort=createdAt,desc
```

Template giúp client biết những biến có thể được cung cấp. Nó không có nghĩa mọi biến đều bắt buộc hoặc mọi tổ hợp giá trị đều hợp lệ; server vẫn xác thực và áp dụng quy tắc nghiệp vụ cho từng request.

## Tạo templated link bằng Spring HATEOAS

Spring HATEOAS cho phép tạo `Link` với URI template. `search` là relation chuẩn trong IANA Link Relation Registry, có thể dùng để client nhận biết link tìm kiếm:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

class OrderLinks {

    static final LinkRelation SEARCH = IanaLinkRelations.SEARCH;

    Link searchTemplate() {
        return Link.of("/orders{?status,page,size,sort}", SEARCH);
    }
}
```

Khi `Link` chứa biểu thức template, Spring HATEOAS nhận biết đây là templated link. Nếu response được serialize theo HAL JSON, link sẽ có thuộc tính `templated: true` để client biết cần mở rộng URI trước khi sử dụng.

Có thể gắn link template vào collection model:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import java.util.List;

CollectionModel<EntityModel<OrderRepresentation>> toCollectionModel(
        List<EntityModel<OrderRepresentation>> orders) {

    Link self = linkTo(methodOn(OrderController.class)
        .list(null, 0, 20, null)).withSelfRel();

    Link search = Link.of("/orders{?status,page,size,sort}", IanaLinkRelations.SEARCH);

    return CollectionModel.of(orders, self, search);
}
```

`OrderRepresentation` và `OrderController` là các kiểu thuộc ứng dụng. `self` ở đây là URI cụ thể của một lần truy cập collection với các đối số đã truyền. `search` là template để client có thể lựa chọn các query parameter. Hai link phục vụ hai mục đích khác nhau: một link nhận diện view hiện tại, một link mô tả cách tạo các URI tìm kiếm khác.

Nếu ứng dụng có context path, reverse proxy hoặc prefix phiên bản API, hãy tạo template dựa trên URI gốc phù hợp với cấu hình triển khai. Không mặc định một đường dẫn tương đối bắt đầu bằng `/` luôn đúng trong mọi môi trường nếu API được triển khai dưới một base path khác.

## Khai báo query parameter trên controller

Các tham số trong template nên khớp với tên và ngữ nghĩa mà controller nhận. Ví dụ:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService orderQueryService;

    OrderController(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> list(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String sort) {

        // Chuyển tham số thành tiêu chí truy vấn và trả collection model.
        return orderQueryService.search(status, page, size, sort);
    }
}
```

`@RequestParam` liên kết query parameter với tham số phương thức. Tên mặc định được suy ra từ tên tham số Java nếu biên dịch có metadata tên tham số; có thể chỉ định rõ `name` để hợp đồng không phụ thuộc cấu hình biên dịch. Ví dụ trên giả định `orderQueryService.search(...)` thực hiện truy vấn, kiểm tra đầu vào và tạo representation.

`WebMvcLinkBuilder` kết hợp `linkTo(methodOn(...))` có thể tạo URI từ mapping và các giá trị đối số cụ thể. Ví dụ `methodOn(OrderController.class).list("PENDING", 0, 20, "createdAt,desc")` tạo link cho một lần tìm kiếm cụ thể. Nếu muốn công bố các biến query chưa được chọn để client tự điền, hãy dùng một URI template rõ ràng như `Link.of("/orders{?status,page,size,sort}", SEARCH)`.

## Mở rộng template bằng UriTemplate

Spring HATEOAS cung cấp `UriTemplate` để làm việc với URI template ở phía Java. Có thể mở rộng template bằng một map tên biến/giá trị:

```java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of("/orders{?status,page,size}");

URI uri = template.expand(Map.of(
    "status", "PENDING",
    "page", 1,
    "size", 20
));

// URI được mở rộng thành /orders?status=PENDING&page=1&size=20
```

Map dùng tên biến khớp với template. Với giá trị chuỗi chứa khoảng trắng, dấu `&`, `?`, dấu tiếng Việt hoặc ký tự dành riêng khác, quá trình mở rộng cần percent-encode theo quy tắc URI Template để các ký tự đó được hiểu là dữ liệu của giá trị, không bị diễn giải thành cấu trúc URI.

Không tự nối chuỗi như `"?status=" + status + "&page=" + page` khi giá trị có thể chứa ký tự đặc biệt. Cách nối thủ công dễ tạo URI sai hoặc làm lộ lỗi khi giá trị có dấu cách, dấu `&`, dấu `#` hay Unicode. Dùng `UriTemplate` hoặc URI builder của Spring để xử lý mã hóa và cấu trúc URI.

## Danh sách và query parameter lặp

Một số API cho phép nhiều giá trị cho cùng một query parameter, ví dụ lọc theo nhiều nhãn:

```text
/orders{?tag*}
```

Nếu client mở rộng `tag` với danh sách `java` và `spring`, kết quả có thể là:

```text
/orders?tag=java&tag=spring
```

Đây là cách biểu diễn khác với một tham số duy nhất chứa chuỗi phân tách bằng dấu phẩy như `tag=java,spring`. API cần quy định rõ cách nhận danh sách và server phải xử lý các giá trị lặp nhất quán. Không nên để client tự lựa chọn giữa hai cách nếu hợp đồng chưa mô tả chúng.

Trong Spring MVC, tham số lặp có thể được nhận bằng collection:

```java
@GetMapping
CollectionModel<EntityModel<OrderRepresentation>> listByTags(
        @RequestParam(name = "tag", required = false) List<String> tags) {
    return orderQueryService.searchByTags(tags);
}
```

Ví dụ này giả định API định nghĩa `tag` là query parameter lặp và service xử lý danh sách. Cần quy định giới hạn số tag, cách xử lý giá trị trùng và hành vi khi danh sách rỗng.

## HAL JSON biểu diễn templated link

Khi serialize link template thành HAL JSON, thuộc tính `templated` cho client biết `href` chưa phải URI cuối cùng:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders?status=PENDING&page=0&size=20"
    },
    "search": {
      "href": "https://api.example.com/orders{?status,page,size,sort}",
      "templated": true
    }
  }
}
```

`self` trỏ tới kết quả tìm kiếm hiện tại; `search` cung cấp cách tạo các URI tìm kiếm khác. Client cần đọc `templated: true`, mở rộng các biến theo RFC 6570 rồi mới gửi request. Nếu bỏ qua trạng thái templated và gửi nguyên `href`, server sẽ nhận chuỗi có dấu ngoặc nhọn thay vì một URI tìm kiếm hợp lệ.

## Kiểm thử URI template và query parameter

Nên kiểm tra cả template ở mức Java lẫn response HTTP đã serialize. Ví dụ kiểm tra link model:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.hateoas.Link;

Link search = model.getLink(OrderLinks.SEARCH).orElseThrow();

assertThat(search.isTemplated()).isTrue();
assertThat(search.getHref()).contains("{?status,page,size,sort}");
```

Với MockMvc, xác nhận HAL JSON công bố đúng href và cờ `templated`:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(containsString("{?status,page,size,sort}")));
```

Trong test mở rộng template, kiểm tra trường hợp không truyền biến tùy chọn, truyền đủ biến, giá trị có dấu cách hoặc ký tự Unicode, danh sách lặp và giá trị không hợp lệ. Đồng thời xác nhận server xử lý default, giới hạn `size`, sort field cho phép và quyền truy cập đúng như hợp đồng.

## Nguyên tắc thiết kế

- **Chỉ công bố biến có ý nghĩa:** mỗi biến trong template phải được endpoint hỗ trợ và tài liệu hóa.
- **Tên biến khớp query parameter:** tránh template khai báo `state` nhưng controller nhận `status`.
- **Phân biệt URI cụ thể và URI template:** link `self` thường nhận diện request hiện tại; link `search` thường mô tả các lựa chọn truy vấn.
- **Dùng đúng toán tử:** `?` bắt đầu query, `&` nối thêm query và `{/var}` mở rộng path.
- **Để thư viện mã hóa URI:** không tự ghép hoặc encode nhiều lần các giá trị đầu vào.
- **Kiểm soát giá trị:** validate page, size, sort và filter; giới hạn kích thước và độ phức tạp truy vấn.
- **Giữ relation ổn định:** relation như `search` giúp client nhận biết mục đích link, còn template và `href` mô tả cách sử dụng hiện tại.
- **Không xem template là bảo mật:** client có thể tự sửa query parameter; server luôn phải kiểm tra quyền và dữ liệu đầu vào.

URI template giúp Spring HATEOAS công bố khả năng tìm kiếm, lọc và phân trang theo một hợp đồng có thể khám phá. Khi chọn đúng biến, dùng cú pháp RFC 6570, tạo link bằng `Link`/`UriTemplate`, xử lý encoding và kiểm thử HAL response, client có thể xây URI hợp lệ mà ít phụ thuộc vào cấu trúc URL nội bộ của server.
