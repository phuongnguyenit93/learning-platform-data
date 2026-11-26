# Relation next và prev

## Mục tiêu

Sau bài này, bạn có thể giải thích ý nghĩa của hai IANA link relation `next` và `prev`, dùng chúng để mô tả điều hướng trong một chuỗi tài nguyên hoặc các trang kết quả, tạo relation bằng Spring HATEOAS, tận dụng `PagedResourcesAssembler` để sinh link phân trang và kiểm thử sự hiện diện của link theo vị trí trang.

## 1. next và prev mô tả quan hệ trong một chuỗi

Một API có thể chia dữ liệu thành nhiều trang. Mỗi trang là một representation riêng, nhưng các trang thuộc cùng một chuỗi kết quả. Client cần biết có thể đi tiếp đến đâu từ trang hiện tại.

Hai link relation chuẩn thường dùng cho việc này:

- `next`: link target là tài nguyên tiếp theo trong chuỗi.
- `prev`: link target là tài nguyên ngay trước đó trong chuỗi.

IANA định nghĩa `next` và `prev` theo quan hệ giữa link context (tài nguyên đang chứa link) và link target (tài nguyên được trỏ đến). Vì vậy, khi response của trang hiện tại chứa `next`, target là trang kế tiếp; khi chứa `prev`, target là trang liền trước.

Ví dụ một response HAL ở trang thứ hai:

```json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=20"
    },
    "prev": {
      "href": "/orders?page=0&size=20"
    },
    "next": {
      "href": "/orders?page=2&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 1
  }
}
```

Ở đây, `self` đại diện cho trang hiện tại. `prev` trỏ đến trang đầu tiên, còn `next` trỏ đến trang thứ ba. Chỉ số trang trong ví dụ dùng quy ước zero-based của Spring Data: `page=0` là trang đầu tiên.

Client nên đọc link mà server trả về và theo href tương ứng. Client không cần tự đoán cấu trúc URL, tên query parameter hoặc cách server tính trang kế tiếp.

## 2. Relation next và prev là relation chuẩn IANA

`next` và `prev` là các link relation đã đăng ký trong IANA Link Relations Registry. Chúng thuộc nhóm relation có semantics được chuẩn hóa, vì vậy nhiều client có thể hiểu ý nghĩa mà không cần một tài liệu riêng cho từng API.

IANA cũng đăng ký relation `previous` với ý nghĩa đồng nghĩa với `prev`. Spring HATEOAS cung cấp cả hai hằng số, nhưng với điều hướng phân trang nên dùng `IanaLinkRelations.PREV` để thống nhất với relation `prev` thường được các thư viện phân trang sinh ra.

Trong Spring HATEOAS, các hằng số có kiểu `LinkRelation`:

```java
import org.springframework.hateoas.IanaLinkRelations;

IanaLinkRelations.NEXT;
IanaLinkRelations.PREV;
```

Dùng hằng số giúp tránh lỗi chính tả và thể hiện rõ đây là relation chuẩn:

```java
Link next = Link.of(
        "/orders?page=2&size=20",
        IanaLinkRelations.NEXT
);

Link previous = Link.of(
        "/orders?page=0&size=20",
        IanaLinkRelations.PREV
);
```

Relation chỉ mô tả mối quan hệ giữa representation hiện tại và target. Nó không bắt buộc target phải là một URL có dạng `?page=n`. API có thể dùng URI khác, cursor hoặc token miễn là target thực sự đại diện cho phần tử kế tiếp hoặc trước đó trong chuỗi.

## 3. Biểu diễn next và prev trong HAL

Trong HAL, relation được đặt làm tên thuộc tính bên trong `_links`. Mỗi link có ít nhất một `href`:

```json
{
  "_links": {
    "self": {
      "href": "/products?category=books&page=1&size=10"
    },
    "prev": {
      "href": "/products?category=books&page=0&size=10"
    },
    "next": {
      "href": "/products?category=books&page=2&size=10"
    }
  }
}
```

Một số điểm cần nhớ:

- `prev` và `next` là tên relation, không phải tên tham số query.
- `href` là URI mà client cần theo.
- Các link có thể giữ lại filter, sort, kích thước trang hoặc ngữ cảnh truy vấn.
- Link không tồn tại có nghĩa API hiện không công bố hướng điều hướng đó.

HAL cho phép mỗi relation chứa một link object hoặc một mảng link object. Với phân trang thông thường, mỗi relation `prev` hoặc `next` chỉ cần một đích nên thường được serialize thành một object.

## 4. Tạo link thủ công với Spring HATEOAS

Nếu ứng dụng tự quản lý điều hướng, có thể tạo link bằng `Link.of(..., IanaLinkRelations...)` rồi thêm vào representation model.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

EntityModel<OrderSummary> model = EntityModel.of(summary);

model.add(Link.of(
        "/orders?page=0&size=20",
        IanaLinkRelations.PREV
));

model.add(Link.of(
        "/orders?page=2&size=20",
        IanaLinkRelations.NEXT
));
```

Cách này phù hợp khi ứng dụng đã có URI điều hướng từ một nguồn khác, hoặc khi dùng cơ chế phân trang tùy chỉnh. Code tạo link phải bảo đảm target đúng với dữ liệu và ngữ cảnh của response hiện tại.

Nếu tự xây URI từ nhiều tham số, nên dùng `UriComponentsBuilder` để mã hóa query parameter đúng cách thay vì nối chuỗi tùy tiện:

```java
URI nextUri = UriComponentsBuilder
        .fromPath("/orders")
        .queryParam("status", status)
        .queryParam("page", nextPage)
        .queryParam("size", pageSize)
        .queryParam("sort", "createdAt,desc")
        .build()
        .encode()
        .toUri();

model.add(Link.of(nextUri.toString(), IanaLinkRelations.NEXT));
```

Khi tạo link thủ công, hãy giữ lại những tham số ảnh hưởng đến tập kết quả, chẳng hạn bộ lọc và sắp xếp. Nếu link `next` làm mất `status=PENDING`, client có thể chuyển sang một chuỗi kết quả khác khi theo link.

## 5. Tự động tạo next và prev bằng PagedResourcesAssembler

Với Spring Data, controller thường nhận `Pageable` và service trả về `Page<T>`. Spring HATEOAS cung cấp `PagedResourcesAssembler` để chuyển `Page<T>` thành `PagedModel<D>`, bao gồm nội dung, metadata và link điều hướng.

Ví dụ controller:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderModelAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderModelAssembler) {
        this.orderService = orderService;
        this.orderModelAssembler = orderModelAssembler;
    }

    @GetMapping(value = "/orders", produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<EntityModel<OrderModel>> getOrders(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderService.findAll(pageable);

        return pagedAssembler.toModel(page, orderModelAssembler);
    }
}
```

Trong ví dụ, `OrderModelAssembler` triển khai:

```java
RepresentationModelAssembler<Order, EntityModel<OrderModel>>
```

`PagedResourcesAssembler` gọi assembler cho các phần tử của trang, tạo metadata trang và bổ sung link `prev` hoặc `next` khi trạng thái trang cho phép.

Hạ tầng Spring Data Web cần được bật để `Pageable` và `PagedResourcesAssembler` có thể được phân giải trong controller. Với Spring Boot và các starter Spring Data/HATEOAS phù hợp, phần lớn cấu hình này thường được auto-configure.

## 6. Khi nào prev và next xuất hiện?

Link điều hướng phụ thuộc vào vị trí trang trong chuỗi kết quả:

| Vị trí | `prev` | `next` |
|---|---|---|
| Trang đầu, còn trang sau | Không | Có |
| Trang ở giữa | Có | Có |
| Trang cuối, có trang trước | Có | Không |
| Chỉ có một trang | Không | Không |
| Trang không có dữ liệu | Phụ thuộc chính sách endpoint và trạng thái Page | Phụ thuộc chính sách endpoint và trạng thái Page |

Ví dụ với 95 đơn hàng và `size=20`, có 5 trang:

- Trang 0: không có `prev`, có `next`.
- Trang 1, 2 hoặc 3: có cả `prev` và `next`.
- Trang 4: có `prev`, không có `next`.

Client không nên giả định mọi response đều có đủ hai link. Hãy kiểm tra relation có tồn tại trước khi hiển thị nút điều hướng hoặc gửi request tiếp theo.

Một số API có thể trả response rỗng khi client yêu cầu trang vượt quá phạm vi. Hành vi đó cần được định nghĩa rõ: server có thể trả trang rỗng mà không có link tiếp theo, chuẩn hóa về trang cuối hoặc trả lỗi theo hợp đồng. Không nên tự tạo `next` đến một trang không tồn tại.

## 7. Query parameters phải được giữ khi điều hướng

Giả sử client đang tìm đơn hàng theo trạng thái và khoảng ngày:

```http
GET /orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=1&size=20&sort=createdAt,desc
```

Link `prev` và `next` cần giữ lại các filter, sort và size:

```json
{
  "_links": {
    "self": {
      "href": "/orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=1&size=20&sort=createdAt,desc"
    },
    "prev": {
      "href": "/orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=0&size=20&sort=createdAt,desc"
    },
    "next": {
      "href": "/orders?status=PENDING&from=2026-10-01&to=2026-10-31&page=2&size=20&sort=createdAt,desc"
    }
  }
}
```

Nếu endpoint dùng `PagedResourcesAssembler`, các link được tạo từ request hiện tại và cấu hình pageable resolver. Với filter được bind vào các query parameter riêng, cần kiểm tra link thực tế để chắc chắn chúng được giữ lại. Nếu ứng dụng dùng custom filter object hoặc tự xây link, hãy chuyển đầy đủ các tiêu chí cần thiết sang URI kế tiếp.

Sắp xếp cũng cần ổn định. Nếu chỉ sort theo trường có giá trị trùng nhau, thứ tự item có thể thay đổi giữa các request. Thêm một thuộc tính duy nhất làm tiêu chí phụ, ví dụ `sort=createdAt,desc&sort=id,asc`, để giảm việc item bị lặp hoặc bỏ qua khi client duyệt trang.

## 8. Điều hướng theo cursor cũng dùng next và prev

Relation `next` và `prev` mô tả thứ tự trong chuỗi, không ràng buộc cách server phân trang. Ngoài offset pagination bằng `page` và `size`, API có thể dùng cursor hoặc keyset pagination.

Ví dụ:

```json
{
  "_links": {
    "self": {
      "href": "/events?cursor=eyJpZCI6MTAwfQ"
    },
    "prev": {
      "href": "/events?cursor=eyJpZCI6ODF9"
    },
    "next": {
      "href": "/events?cursor=eyJpZCI6MTIwfQ"
    }
  }
}
```

Client chỉ cần theo href. Nó không cần giải mã cursor hoặc tự tính giá trị cursor kế tiếp. Cursor thường là token opaque do server tạo; client nên xem token như dữ liệu không có ý nghĩa nội bộ.

Với cursor pagination, `PagedResourcesAssembler` có thể không phù hợp nếu nguồn dữ liệu không phải `Page<T>` hoặc semantics cursor không ánh xạ trực tiếp sang `Pageable`. Khi đó, ứng dụng có thể tự tạo `Link` với `IanaLinkRelations.NEXT` và `IanaLinkRelations.PREV`, đồng thời bảo đảm cursor được kiểm tra và gắn với đúng bộ lọc, thứ tự và phạm vi truy cập.

Không phải API nào cũng hỗ trợ cả hai hướng. Ví dụ, một luồng sự kiện chỉ cho phép đọc tiếp về phía tương lai có thể chỉ công bố `next`. Nếu server không thể tạo cursor ngược hoặc không cho phép quay lại, đừng tạo link `prev` giả.

## 9. Client nên sử dụng next và prev như thế nào?

Client hypermedia nên dựa vào relation thay vì xây URL theo quy ước riêng:

1. Đọc response hiện tại.
2. Tìm link có relation `next` hoặc `prev`.
3. Nếu link tồn tại, gửi request đến `href`.
4. Đọc response mới và tiếp tục từ các link mà server công bố.

Pseudo-code:

```javascript
async function followRelation(document, relation) {
  const link = document._links?.[relation];

  if (!link) {
    return null;
  }

  const response = await fetch(link.href, {
    headers: { Accept: "application/hal+json" }
  });

  if (!response.ok) {
    throw new Error("Could not follow " + relation);
  }

  return response.json();
}
```

Đoạn code giả định relation có một link duy nhất và response dùng HAL. Nếu API cho phép nhiều link cùng relation hoặc cấu hình serialize một link thành mảng, client cần xử lý cả hai hình dạng.

Client cũng cần xử lý trường hợp link bị thiếu, request thất bại hoặc quyền truy cập đã thay đổi. Việc link từng xuất hiện trong response cũ không bảo đảm request tiếp theo sẽ luôn thành công.

## 10. Kiểm thử relation next và prev

Kiểm thử cần xác nhận relation xuất hiện đúng theo trạng thái trang và href trỏ đến trang mong muốn. Với MockMvc, có thể gọi trang giữa để kiểm tra cả hai link:

```java
mockMvc.perform(get("/orders")
        .param("page", "1")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("page=1")))
    .andExpect(jsonPath("$._links.prev.href")
            .value(containsString("page=0")))
    .andExpect(jsonPath("$._links.next.href")
            .value(containsString("page=2")));
```

Test này giả định dữ liệu có ít nhất ba trang và Spring Data đang dùng zero-based page parameters.

Kiểm tra trang đầu:

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.prev").doesNotExist())
    .andExpect(jsonPath("$._links.next.href").exists());
```

Kiểm tra trang cuối:

```java
mockMvc.perform(get("/orders")
        .param("page", "4")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.prev.href").exists())
    .andExpect(jsonPath("$._links.next").doesNotExist());
```

Ngoài sự tồn tại của link, hãy kiểm tra:

- `prev` và `next` có đúng relation name viết thường.
- Href giữ lại filter, sort và size.
- Href không làm mất context path hoặc base path của ứng dụng.
- Target thực sự trả trang liền trước hoặc liền sau.
- Trang đầu không có `prev`; trang cuối không có `next`.
- Client xử lý được response không có một trong hai relation.

Có thể kiểm tra trực tiếp model trước serialization:

```java
assertThat(pagedModel.getLink(IanaLinkRelations.PREV)).isPresent();
assertThat(pagedModel.getLink(IanaLinkRelations.NEXT)).isPresent();
```

Kiểm thử MockMvc vẫn cần thiết vì nó xác nhận relation được serialize thành đúng tên trong HAL và href phản ánh request thực tế.

## 11. Những lỗi thường gặp

**Dùng relation tùy ý như `previousPage`.** Client quen với IANA relation `prev` sẽ không nhận ra tên riêng đó. Dùng `IanaLinkRelations.PREV` cho link trang trước.

**Nhầm `prev` với `first`.** `prev` trỏ đến trang liền trước; `first` trỏ đến trang xa nhất về phía trước của chuỗi, tức trang đầu tiên. Trang hiện tại có thể có `prev` nhưng không cần tự suy ra `first`.

**Tự tính URL trong client.** Client có thể làm mất filter, sort, context path hoặc cách đánh số trang. Theo href server cung cấp.

**Luôn tạo cả hai link.** Trang đầu không có trang trước và trang cuối không có trang tiếp theo. Chỉ công bố link có target hợp lệ.

**Chỉ kiểm tra relation mà không kiểm tra href.** Link `next` có thể tồn tại nhưng trỏ sai trang hoặc mất bộ lọc. Kiểm tra target thực tế.

**Nhầm relation với HTTP method.** `next` và `prev` mô tả hướng điều hướng. Chúng không tự chỉ định GET hay một method khác; method được xác định bởi semantics của endpoint và affordance nếu có.

**Dùng PagedResourcesAssembler cho cursor mà không điều chỉnh.** Assembler phân trang dựa trên `Page` và `Pageable`. Với cursor opaque, cần tạo link theo cursor của ứng dụng.

**Dùng `previous` và `prev` lẫn lộn.** IANA đăng ký `previous` là synonym của `prev`, nhưng nên chọn một relation thống nhất. Với Spring HATEOAS pagination, dùng `IanaLinkRelations.PREV`.

## 12. Nguyên tắc thiết kế

- Dùng relation chuẩn `next` và `prev` để biểu diễn hướng đi trong chuỗi.
- Dùng `IanaLinkRelations.NEXT` và `IanaLinkRelations.PREV` thay cho chuỗi tự gõ.
- Dùng `PagedResourcesAssembler` khi nguồn dữ liệu là `Page<T>`.
- Chỉ công bố link khi trang đích tồn tại và có thể truy cập theo hợp đồng.
- Giữ lại filter, sort, size và ngữ cảnh truy vấn trong href.
- Để client theo link thay vì tự tính URL hoặc giải mã cursor.
- Với cursor pagination, tạo relation từ cursor do server quản lý.
- Kiểm thử relation, href, trang đầu, trang giữa và trang cuối qua MockMvc.

## Kết luận

`next` và `prev` là hai IANA link relation mô tả tài nguyên kế tiếp và liền trước trong một chuỗi. Spring HATEOAS biểu diễn chúng bằng `IanaLinkRelations.NEXT` và `IanaLinkRelations.PREV`; với dữ liệu Spring Data dạng `Page<T>`, `PagedResourcesAssembler` có thể tạo các link điều hướng theo trạng thái trang. Hãy giữ filter và sort trong href, chỉ công bố hướng đi hợp lệ và để client theo link mà server cung cấp. Kiểm thử cả relation lẫn target để bảo đảm điều hướng hoạt động đúng.

## Tài liệu tham khảo

- [IANA – Link Relations Registry](https://www.iana.org/assignments/link-relations)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [Spring HATEOAS API – IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring Data Commons Reference – Hypermedia Support for Page](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

