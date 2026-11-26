# Relation first và last

Trong API có phân trang, client thường cần hai cách điều hướng nhanh: quay về trang đầu tiên và đi thẳng tới trang cuối cùng. IANA định nghĩa hai link relation chuẩn cho mục đích này: `first` và `last`. Spring HATEOAS cung cấp các hằng `IanaLinkRelations.FIRST` và `IanaLinkRelations.LAST`; Spring Data có `PagedResourcesAssembler` để tạo `PagedModel` cùng các link phân trang.

`first` trỏ tới tài nguyên ở vị trí đầu tiên của một chuỗi; `last` trỏ tới tài nguyên ở vị trí cuối cùng. Trong API phân trang, tài nguyên đích thường là trang đầu và trang cuối của collection. Client đọc relation rồi theo `href` do server cung cấp, không cần tự tính URL hoặc giả định tên tham số phân trang.

## Ngữ nghĩa IANA của first và last

IANA Link Relation Registry định nghĩa:

- `first`: IRI trỏ tới tài nguyên ở vị trí xa nhất về trước trong một chuỗi tài nguyên.
- `last`: IRI trỏ tới tài nguyên ở vị trí xa nhất về sau trong một chuỗi tài nguyên.

Hai relation này được đăng ký theo RFC 8288 – Web Linking. Relation mô tả mối quan hệ giữa tài nguyên hiện tại (link context) và tài nguyên đích (link target). Nó không mô tả media type của response và cũng không bắt buộc client phải hiểu cấu trúc URL của tài nguyên đích.

Trong phân trang, nếu client đang xem trang thứ ba của một collection, `first` đưa client về trang đầu, còn `last` đưa client tới trang cuối. Hai relation này mô tả hai đầu của chuỗi; `prev` và `next` mô tả hai trang kề ngay trước và ngay sau trang hiện tại.

| Relation | Ý nghĩa trong phân trang | Ví dụ khi đang ở trang 2 |
|---|---|---|
| `first` | Trang đầu tiên | `page=0` |
| `prev` | Trang liền trước | `page=1` |
| `self` | Trang hiện tại | `page=2` |
| `next` | Trang liền sau | `page=3` |
| `last` | Trang cuối cùng | `page=4` nếu có 5 trang |

Giá trị `page` trong bảng giả định API dùng chỉ số trang bắt đầu từ 0 như `Pageable` mặc định của Spring Data. Nếu API dùng chỉ số bắt đầu từ 1 hoặc cursor, client vẫn phải theo `href` thực tế thay vì áp dụng phép tính trong ví dụ.

## Phân biệt first/last với prev/next

`first` và `last` giúp nhảy tới hai đầu của chuỗi. `prev` và `next` giúp duyệt tuần tự. Client không nên suy ra rằng nếu có `next` thì chắc chắn có `last`, hoặc tự tăng `page` để tìm trang tiếp theo. Server có thể dùng offset, cursor hoặc một chiến lược phân trang khác; relation và URI do server công bố mới là hợp đồng điều hướng.

Ví dụ response HAL khi đang ở trang 2 trong collection có 5 trang:

```json
{
  "_embedded": {
    "orders": [
      { "id": "ORD-2041", "status": "PENDING" },
      { "id": "ORD-2042", "status": "PAID" }
    ]
  },
  "_links": {
    "first": { "href": "/api/orders?page=0&size=2" },
    "prev": { "href": "/api/orders?page=1&size=2" },
    "self": { "href": "/api/orders?page=2&size=2" },
    "next": { "href": "/api/orders?page=3&size=2" },
    "last": { "href": "/api/orders?page=4&size=2" }
  },
  "page": {
    "size": 2,
    "totalElements": 10,
    "totalPages": 5,
    "number": 2
  }
}
```

Ở đây `first` và `last` trỏ tới các trang, không phải link trực tiếp tới phần tử đầu tiên hoặc cuối cùng trong `_embedded.orders`. Nếu cần điều hướng tới một item cụ thể, API cần công bố link tới item đó với relation phù hợp.

## Sử dụng IanaLinkRelations trong Spring HATEOAS

Spring HATEOAS định nghĩa các relation chuẩn trong `IanaLinkRelations`. Dùng các hằng này để tránh gõ sai tên relation:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link firstLink = Link.of("/api/orders?page=0&size=20", IanaLinkRelations.FIRST);
Link lastLink = Link.of("/api/orders?page=4&size=20", IanaLinkRelations.LAST);
```

Có thể thêm link vào một representation model:

```java
import org.springframework.hateoas.RepresentationModel;

public class OrderCollectionModel extends RepresentationModel<OrderCollectionModel> {
}

OrderCollectionModel model = new OrderCollectionModel();
model.add(firstLink, lastLink);
```

Khi serialize theo HAL, các link được biểu diễn trong `_links` bằng tên relation chuẩn `first` và `last`. Client chỉ cần tìm đúng relation rồi đọc `href`.

## Tạo link first và last từ dữ liệu phân trang

Với offset pagination, `Page<T>` cung cấp thông tin cần để xác định trang đầu và trang cuối:

- Trang đầu có chỉ số `0` trong cấu hình mặc định của Spring Data.
- `getTotalPages()` trả tổng số trang.
- Trang cuối có chỉ số `getTotalPages() - 1` nếu collection có ít nhất một trang.
- `getPageable().getPageSize()` cho biết kích thước trang hiện tại.

Không nên tính URL trong client. Server biết chính xác tham số query, cách sắp xếp, bộ lọc và cấu hình `Pageable`, nên server tạo link hoàn chỉnh rồi đưa vào response.

## Tạo PagedModel bằng PagedResourcesAssembler

Trong ứng dụng Spring MVC dùng Spring Data, `PagedResourcesAssembler` là cách thuận tiện để chuyển `Page<T>` thành `PagedModel`. Assembler tạo metadata phân trang và các link điều hướng theo request hiện tại cùng cấu hình `PageableHandlerMethodArgumentResolver`.

Ví dụ assembler cho một đơn hàng:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        UUID id = order.getId();

        return EntityModel.of(
                new OrderResponse(id, order.getStatus().name()),
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

Controller nhận `Pageable`, lấy `Page<Order>` từ service và dùng `PagedResourcesAssembler` để tạo response:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler orderAssembler;

    public OrderController(OrderService service, OrderModelAssembler orderAssembler) {
        this.service = service;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<EntityModel<OrderResponse>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler
    ) {
        Page<Order> page = service.findAll(pageable);

        pagedAssembler.setForceFirstAndLastRels(true);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
```

Spring Data Web cung cấp `PagedResourcesAssembler` như một tham số controller khi hạ tầng Spring Data web được cấu hình. `toModel(page, orderAssembler)` chuyển từng đơn hàng thành `EntityModel<OrderResponse>` rồi tạo `PagedModel` chứa metadata và link phân trang.

Lệnh `setForceFirstAndLastRels(true)` yêu cầu assembler luôn thêm hai relation `first` và `last`. Theo API hiện hành, mặc định thuộc tính này là `false`; khi đó các link `first` và `last` chỉ xuất hiện cùng các link `prev` và `next`. Nếu hợp đồng API yêu cầu hai relation đầu/cuối luôn có mặt, hãy bật tùy chọn này và kiểm thử cả trang đầu, trang giữa và trang cuối.

Assembler cũng xây dựng URI theo cấu hình phân trang hiện tại. Nếu ứng dụng đổi tên query parameter, cách xử lý page index hoặc cấu hình sort, hãy để resolver/assembler tạo link thay vì tự nối chuỗi query.

## Đọc response ở các vị trí khác nhau trong chuỗi

Với collection có 5 trang và chỉ số trang bắt đầu từ 0, các link thường được hiểu như sau khi API bật `first` và `last`:

| Trang hiện tại | Link `first` | Link `prev` | Link `next` | Link `last` |
|---|---|---|---|---|
| Trang 0 | Trang 0 | Không có | Trang 1 | Trang 4 |
| Trang 1 | Trang 0 | Trang 0 | Trang 2 | Trang 4 |
| Trang 2 | Trang 0 | Trang 1 | Trang 3 | Trang 4 |
| Trang 3 | Trang 0 | Trang 2 | Trang 4 | Trang 4 |
| Trang 4 | Trang 0 | Trang 3 | Không có | Trang 4 |

`prev` không có ở trang đầu và `next` không có ở trang cuối vì không tồn tại trang kề theo hướng đó. Nếu API bật force first/last, trang đầu có thể có `first` trỏ lại chính nó và trang cuối có thể có `last` trỏ lại chính nó. Với collection chỉ có một trang, hai link có thể cùng trỏ tới trang duy nhất.

## Bảo toàn filter và sort trong link first/last

Một request phân trang thường chứa nhiều tham số:

```http
GET /api/orders?page=2&size=20&sort=createdAt,desc&status=PENDING&customerId=C-100
```

Link `first` và `last` phải giữ các điều kiện lọc và sắp xếp để client vẫn xem cùng một tập kết quả ở trang khác:

```text
first -> /api/orders?page=0&size=20&sort=createdAt,desc&status=PENDING&customerId=C-100
last  -> /api/orders?page=4&size=20&sort=createdAt,desc&status=PENDING&customerId=C-100
```

Khi dùng `PagedResourcesAssembler`, link được xây dựng từ request và resolver, nên các tham số được cấu hình có thể được duy trì tự động. Khi tự tạo link, hãy chỉ thay tham số trang và giữ lại các query parameter liên quan. Nếu bỏ `status` hoặc `sort`, `first`/`last` có thể dẫn client sang một collection khác với collection đang duyệt.

## Tạo link first và last thủ công

Đôi khi API không dùng `Pageable` hoặc cần tạo một representation phân trang tùy chỉnh. Khi đó, có thể dùng `IanaLinkRelations.FIRST` và `IanaLinkRelations.LAST` để gắn relation tường minh.

Ví dụ với tham số `page` mặc định, `ServletUriComponentsBuilder` lấy URI request hiện tại rồi thay chỉ số trang. Cách này giữ lại `size`, `sort` và các filter query đang có:

```java
import org.springframework.data.domain.Page;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

public void addFirstAndLastLinks(
        PagedModel<?> model,
        Page<?> page
) {
    if (page.getTotalPages() == 0) {
        return; // Collection rỗng không có trang cuối.
    }

    String firstHref = ServletUriComponentsBuilder.fromCurrentRequest()
            .replaceQueryParam("page", 0)
            .build()
            .toUriString();

    String lastHref = ServletUriComponentsBuilder.fromCurrentRequest()
            .replaceQueryParam("page", page.getTotalPages() - 1)
            .build()
            .toUriString();

    model.add(
            Link.of(firstHref, IanaLinkRelations.FIRST),
            Link.of(lastHref, IanaLinkRelations.LAST)
    );
}
```

Đoạn code giả định API dùng query parameter `page` và request hiện tại chứa các tham số cần giữ. Nếu `PageableHandlerMethodArgumentResolver` đã được cấu hình tên parameter khác, hãy dùng tên đã cấu hình. Cũng cần tránh thêm link trùng nếu `PagedResourcesAssembler` đã tạo `first` và `last`; có thể kiểm tra `model.hasLink(IanaLinkRelations.FIRST)` và `model.hasLink(IanaLinkRelations.LAST)` trước khi thêm.

Với cursor pagination, trang cuối có thể không biết trước hoặc dữ liệu có thể tiếp tục được thêm. Trong trường hợp đó, không tạo `last` giả bằng cách ước lượng cursor. Chỉ công bố `last` khi server có thể xác định URI đích đúng theo semantics của relation.

## Client điều hướng theo relation

Client nên tìm relation `first` hoặc `last` trong `_links` rồi gửi request tới `href` tương ứng:

```javascript
const firstHref = document._links.first?.href;
const lastHref = document._links.last?.href;

if (firstHref) {
  const firstPage = await fetch(firstHref, {
    headers: { Accept: "application/hal+json" }
  });
}

if (lastHref) {
  const lastPage = await fetch(lastHref, {
    headers: { Accept: "application/hal+json" }
  });
}
```

Đây là ví dụ JavaScript minh họa cách client theo link. Client cần xử lý trường hợp relation không được công bố, request thất bại hoặc server trả về một representation mới có tập link khác. Client không nên tự suy ra URL từ `totalPages` hoặc ghép `?page=0` nếu server đã cung cấp link.

## Kiểm thử first và last bằng MockMvc

Kiểm thử tích hợp nên xác nhận relation xuất hiện và `href` trỏ tới đúng chỉ số trang. Giả sử dữ liệu test tạo ra 5 trang, mỗi trang 20 phần tử:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
class OrderPaginationLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesFirstAndLastLinksForMiddlePage() throws Exception {
        mockMvc.perform(get("/api/orders")
                .param("page", "2")
                .param("size", "20")
                .param("status", "PENDING")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.first.href")
                    .value(containsString("page=0")))
            .andExpect(jsonPath("$._links.last.href")
                    .value(containsString("page=4")))
            .andExpect(jsonPath("$._links.prev.href")
                    .value(containsString("page=1")))
            .andExpect(jsonPath("$._links.next.href")
                    .value(containsString("page=3")));
    }
}
```

Test này cũng có thể xác nhận filter `status=PENDING` còn trong link:

```java
.andExpect(jsonPath("$._links.first.href")
        .value(containsString("status=PENDING")))
```

Hãy có thêm test cho trang đầu và trang cuối để kiểm tra `prev`/`next` được xuất hiện đúng điều kiện. Nếu `setForceFirstAndLastRels(true)` được bật, kiểm tra `first` và `last` vẫn có mặt ở hai biên. Với collection rỗng, xác định rõ hợp đồng có công bố link trang hay không; không tạo `last` nếu không tồn tại trang cuối.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `first` để chỉ phần tử đầu tiên | Client hiểu sai link điều hướng | Dùng `first` cho tài nguyên đầu của chuỗi/trang đầu; dùng link item cho phần tử |
| Dùng `last` như một link `next` khác | Client không thể nhảy tới cuối collection | Phân biệt `last` với trang kề `next` |
| Tự ghép `page=0` ở client | Client phụ thuộc quy ước URL và tham số | Theo `href` trong relation `first` |
| Quên giữ filter hoặc sort | Client chuyển sang tập kết quả khác | Để resolver/assembler xây link hoặc giữ các query parameter |
| Công bố `last` khi không biết trang cuối | Link không hợp lệ hoặc không ổn định | Chỉ tạo khi server xác định được target |
| Mặc định nghĩ assembler luôn thêm first/last | Hợp đồng thiếu relation ở một số trang | Dùng `setForceFirstAndLastRels(true)` nếu cần luôn có |
| Thêm link trùng với assembler | Response có nhiều link cùng relation ngoài ý muốn | Chọn một nơi chịu trách nhiệm tạo link và kiểm tra `hasLink(...)` |
| Coi số trang là một-based trong Spring Data mặc định | `first` trỏ sai trang | Dùng `page=0` với `Pageable` mặc định hoặc theo resolver đã tùy chỉnh |

## Quy trình triển khai

1. Xác định API có một chuỗi trang với điểm đầu và điểm cuối có thể biết được hay không.
2. Dùng relation IANA `first` và `last` để công bố hai đầu chuỗi.
3. Phân biệt hai relation này với `prev`, `next` và `self`.
4. Với Spring Data `Page`, ưu tiên `PagedResourcesAssembler` để tạo `PagedModel` và link điều hướng.
5. Bật `setForceFirstAndLastRels(true)` nếu hợp đồng yêu cầu hai link luôn xuất hiện.
6. Nếu tạo link thủ công, dùng `IanaLinkRelations.FIRST` và `IanaLinkRelations.LAST`, đồng thời giữ filter, sort và kích thước trang.
7. Kiểm thử `href` ở trang đầu, trang giữa, trang cuối và collection rỗng.
8. Đảm bảo client theo `href` được công bố thay vì tự tính URI.

## Kết luận

`first` và `last` là hai relation IANA chuẩn để chỉ tài nguyên đầu tiên và cuối cùng trong một chuỗi. Với API phân trang, chúng thường trỏ tới trang đầu và trang cuối của collection; `prev` và `next` vẫn dành cho điều hướng từng bước. Spring HATEOAS cung cấp `IanaLinkRelations.FIRST` và `IanaLinkRelations.LAST`, còn Spring Data `PagedResourcesAssembler` tạo `PagedModel` cùng link phân trang và cho phép ép luôn công bố hai relation đầu/cuối. Khi link giữ nguyên filter và sort, client có thể nhảy tới hai đầu collection mà không phụ thuộc vào cấu trúc URL nội bộ.

## Tài liệu tham khảo

- [IANA Link Relation Registry](https://www.iana.org/assignments/link-relations/): định nghĩa chính thức của relation `first` và `last`.
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html): mô hình link context, link relation type và link target.
- [Spring HATEOAS – IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html): các hằng relation chuẩn, gồm `FIRST` và `LAST`.
- [Spring Data – PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html): tạo `PagedModel`, pagination links và cấu hình `setForceFirstAndLastRels`.
