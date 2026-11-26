# Template cho search

Một API quản lý đơn hàng thường cung cấp endpoint tìm kiếm theo trạng thái, khách hàng hoặc khoảng ngày. Client cần biết endpoint tìm kiếm ở đâu và có thể truyền những điều kiện nào. Nếu server chỉ trả một URI cố định, client phải tự biết tên query parameter rồi ghép URL. Spring HATEOAS có thể công bố một search link dưới dạng URI template để client khám phá các biến truy vấn được hỗ trợ.

Trong HAL, search link thường dùng relation `search` và có thuộc tính `templated: true`. URI template có thể chứa các biến query như `status`, `customerId`, `createdFrom` và `createdTo`. Client mở rộng template bằng giá trị cần tìm, gửi GET đến URI đã tạo và nhận collection representation. Các query variable là một phần của hợp đồng API nên tên, kiểu, format và semantics cần được giữ ổn định.

## Search link và URI template

Search link là một hypermedia link dẫn đến chức năng tìm kiếm hoặc lọc resource. Relation `search` cho client biết mục đích của link; URI template mô tả các biến mà client có thể cung cấp để tạo URI cụ thể.

Ví dụ HAL:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    },
    "search": {
      "href": "https://api.example.com/api/orders/search{?status,customerId,createdFrom,createdTo}",
      "templated": true
    }
  }
}
```

Client có thể mở rộng template thành một URI cụ thể:

```text
/api/orders/search?status=PENDING&customerId=cus-73&createdFrom=2026-11-01
```

Trong đó:

- `search` là relation mô tả chức năng tìm kiếm.
- `href` chứa URI template với biểu thức query `{?...}`.
- `templated: true` cho biết `href` cần được mở rộng trước khi gửi request.
- `status`, `customerId`, `createdFrom` và `createdTo` là tên biến mà client có thể cung cấp.

URI template tuân theo cú pháp RFC 6570. Biểu thức `{?status,customerId}` mở rộng thành query component, chỉ đưa các biến có giá trị vào URI. Client không nên tự nối chuỗi query vì việc mở rộng template phải xử lý encoding và delimiter đúng quy tắc.

## Vì sao nên công bố search link?

Search link giúp client khám phá chức năng từ representation gốc thay vì phải hard-code endpoint tìm kiếm. Server có thể thay đổi URI cụ thể trong tương lai trong khi vẫn giữ relation `search` và cách client khám phá chức năng.

Lợi ích chính:

- **Khám phá:** client tìm chức năng qua relation `search`.
- **Giảm phụ thuộc URI:** client không phải tự ghép path hoặc query string.
- **Hỗ trợ tiến hóa:** server có thể thay đổi URI hoặc thêm biến mới mà không buộc client viết lại mọi URL.
- **Tái sử dụng:** nhiều client có thể dùng cùng relation và template.
- **Kết hợp pagination:** link tìm kiếm có thể dẫn đến collection được phân trang, với các link `next`/`prev` giữ lại filter hiện tại.

Search link không tự thực hiện tìm kiếm và không mô tả toàn bộ quy tắc nghiệp vụ. Nó chỉ cung cấp điểm vào và cấu trúc URI có thể mở rộng. Client vẫn cần biết ý nghĩa, kiểu và format của từng biến qua tài liệu API hoặc metadata bổ sung.

## Thiết kế endpoint tìm kiếm

Giả sử API tìm đơn hàng theo trạng thái, khách hàng và khoảng ngày. Endpoint nên dùng GET vì thao tác đọc kết quả, không làm thay đổi trạng thái server:

```http
GET /api/orders/search?status=PENDING&customerId=cus-73
```

Controller khai báo query parameter tùy chọn với tên công khai rõ ràng:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderSearchController {

    private final OrderService orders;
    private final OrderModelAssembler orderAssembler;

    OrderSearchController(OrderService orders,
                          OrderModelAssembler orderAssembler) {
        this.orders = orders;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping("/search")
    CollectionModel<EntityModel<OrderView>> search(
            @RequestParam(name = "status", required = false)
            OrderStatus status,
            @RequestParam(name = "customerId", required = false)
            UUID customerId,
            @RequestParam(name = "createdFrom", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate createdFrom,
            @RequestParam(name = "createdTo", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate createdTo) {

        List<Order> result = orders.search(status, customerId,
            createdFrom, createdTo);
        return orderAssembler.toCollectionModel(result);
    }
}
```

Đây là ví dụ cấu trúc; ứng dụng cần inject `OrderModelAssembler` và dùng kiểu service phù hợp. Các parameter được đánh dấu `required = false` để có thể bỏ qua điều kiện không cần lọc. `name` cố định tên công khai, không phụ thuộc tên biến Java. `@DateTimeFormat` quy định ngày theo ISO `yyyy-MM-dd`.

Search endpoint nên xác định rõ semantics khi một parameter bị thiếu, rỗng hoặc sai định dạng. Ví dụ, thiếu `status` có thể nghĩa là tìm mọi trạng thái; `status=` có thể bị từ chối; literal `status=null` là một chuỗi cần được xử lý theo quy tắc API, không tự động có nghĩa là Java `null`.

## Tạo URI template bằng WebMvcLinkBuilder

Spring HATEOAS có thể tạo link từ mapping controller. Khi method có các query parameter tùy chọn, việc tham chiếu method với giá trị placeholder `null` cho phép link builder tạo URI template cho các biến query.

Ví dụ thêm search link vào collection resource:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link search = linkTo(methodOn(OrderSearchController.class)
    .search(null, null, null, null))
    .withRel(IanaLinkRelations.SEARCH);

collection.add(search);
```

`methodOn(...)` tạo proxy để ghi nhận method mapping và tham số. Nó không thực thi thân controller, không gọi service và không gửi HTTP request. `linkTo(...)` sử dụng mapping của `OrderSearchController`; các tham số query tùy chọn được biểu diễn thành biến của URI template.

Kết quả dự kiến có dạng:

```text
https://api.example.com/api/orders/search{?status,customerId,createdFrom,createdTo}
```

Tên biến được lấy từ metadata mapping, đặc biệt là `@RequestParam(name = ...)`. Vì vậy nên khai báo tên parameter tường minh để hợp đồng không thay đổi khi refactor tên biến Java. Hãy kiểm tra link được serialize thực tế vì cấu hình MVC, mapping và phiên bản Spring HATEOAS ảnh hưởng đến URI cuối cùng.

## Tạo link tìm kiếm ở cấp collection

Một endpoint collection có thể trả về các item hiện có cùng search link:

Đoạn method sau nằm trong controller đã có dependency `orders` và `orderAssembler`, cùng các static import `linkTo`/`methodOn` như ví dụ trước.

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    CollectionModel<EntityModel<OrderView>> collection =
        orderAssembler.toCollectionModel(orders.findRecent());

    collection.add(linkTo(methodOn(OrderController.class).all())
        .withSelfRel());

    collection.add(linkTo(methodOn(OrderSearchController.class)
        .search(null, null, null, null))
        .withRel(IanaLinkRelations.SEARCH));

    return collection;
}
```

Trong ví dụ, `self` trỏ đến collection hiện tại còn `search` trỏ đến endpoint tìm kiếm có thể mở rộng. Hai link có mục đích khác nhau. Không dùng relation `self` cho search template vì URI tìm kiếm không phải representation hiện tại.

Search link thường được công bố ở top-level `_links` của collection. Nếu một resource riêng có chức năng tìm kiếm các resource liên quan, search link cũng có thể nằm trên representation đó, miễn relation và phạm vi tìm kiếm được xác định rõ.

## Đọc và mở rộng template

Client HAL trước hết đọc relation `search`, sau đó kiểm tra `templated`. Nếu là template, client mở rộng bằng các biến đã chọn.

Template:

```text
/api/orders/search{?status,customerId,createdFrom,createdTo}
```

Giá trị đầu vào:

```json
{
  "status": "PENDING",
  "customerId": "cus-73",
  "createdFrom": "2026-11-01"
}
```

URI sau khi mở rộng:

```text
/api/orders/search?status=PENDING&customerId=cus-73&createdFrom=2026-11-01
```

Biến không được cung cấp sẽ không xuất hiện trong query. Nếu client cung cấp chuỗi rỗng, kết quả có thể chứa parameter với giá trị rỗng; client chỉ nên làm vậy khi API quy định ý nghĩa cho giá trị đó.

Khi biến chứa ký tự đặc biệt như dấu cách, `&`, `+`, `%` hoặc ký tự Unicode, URI template processor cần encode đúng giá trị. Không thay biến bằng cách nối chuỗi thủ công vì có thể làm thay đổi ý nghĩa query hoặc tạo URI không hợp lệ.

## Nhiều giá trị cho một query variable

Một search filter có thể nhận nhiều giá trị, ví dụ tìm đơn hàng ở trạng thái `PENDING` hoặc `PAID`. API có thể chọn parameter lặp:

```http
GET /api/orders/search?status=PENDING&status=PAID
```

Trong RFC 6570, explode modifier `*` có thể được dùng trong URI template để mở rộng danh sách thành nhiều cặp query:

```text
/api/orders/search{?status*}
```

Client và server phải thống nhất cardinality và semantics của filter. Parameter lặp có thể mang nghĩa OR giữa các giá trị; nếu API chọn cách phân tách bằng dấu phẩy hoặc một cấu trúc khác, cần mô tả riêng. Không giả định mọi URI template library tự động serialize list theo cùng một cách; hãy kiểm thử expansion của client và binding của Spring MVC.

## Search template kết hợp pagination và sorting

Search result có thể rất lớn nên endpoint tìm kiếm thường hỗ trợ `page`, `size` và `sort`:

```http
GET /api/orders/search?status=PENDING&page=0&size=20&sort=createdAt,desc
```

Nếu muốn công bố các biến này trong search template, template có thể có dạng:

```text
/api/orders/search{?status,customerId,createdFrom,createdTo,page,size,sort}
```

Tuy nhiên, không nên giả định `WebMvcLinkBuilder` tự nhận diện mọi query parameter được Spring Data thêm từ `Pageable`. Nếu controller nhận `Pageable`, cơ chế resolver có thể ánh xạ nhiều query parameter mà không xuất hiện như từng `@RequestParam` trong chữ ký method. Hãy kiểm tra template thực tế hoặc khai báo các biến theo cơ chế phù hợp với API.

Sau khi client thực hiện tìm kiếm, server nên trả `PagedModel` và các link điều hướng `self`, `next`, `prev`, `first`, `last` khi phù hợp. Các page link phải giữ nguyên filter và sort của truy vấn hiện tại. Client theo `next.href` thay vì tự tăng `page` hoặc dựng lại query.

## URI template không phải form metadata

URI template chỉ mô tả cách tạo URI từ các biến. Nó không tự cho client biết:

- `status` là enum gồm những giá trị nào.
- `createdFrom` cần theo format ngày nào.
- `customerId` có kiểu UUID hay mã nghiệp vụ.
- Filter nào bắt buộc hoặc chỉ được dùng trong một trạng thái nhất định.
- Giá trị tối thiểu/tối đa hoặc prompt để hiển thị form.

Ví dụ, template `{?status,createdFrom}` chỉ cho biết tên biến. Nếu client cần metadata form, HAL-FORMS có thể mô tả method, content type và property như `name`, `prompt`, `type`, `required`, `options` và các ràng buộc. Hai cơ chế bổ sung cho nhau: URI template giúp mở rộng URI tìm kiếm; HAL-FORMS mô tả thao tác và input ở mức phong phú hơn.

Không nhầm search link GET với form POST/PATCH. Search thường là thao tác đọc, còn template HAL-FORMS có thể mô tả nhiều loại thao tác và request body.

## Đặt tên query variable ổn định

Tên biến trong URI template là một phần hợp đồng. Hãy chọn tên ngắn gọn, rõ nghĩa và giữ nhất quán giữa endpoint, tài liệu và link:

| Biến | Ý nghĩa | Format gợi ý |
| --- | --- | --- |
| `status` | Trạng thái đơn hàng | Mã enum ổn định như `PENDING` |
| `customerId` | Định danh khách hàng | UUID hoặc mã được API công bố |
| `createdFrom` | Ngày tạo bắt đầu | `yyyy-MM-dd` |
| `createdTo` | Ngày tạo kết thúc | `yyyy-MM-dd` |
| `page` | Chỉ số trang | Số nguyên, thường zero-based trong Spring Data |
| `size` | Kích thước trang | Số nguyên dương trong giới hạn server |
| `sort` | Thứ tự sắp xếp | Field và direction được allowlist |

Không đổi tên `customerId` thành `customer` chỉ trong template mà không thay đổi controller hoặc tài liệu. Nếu cần đổi tên, hãy duy trì alias cũ trong giai đoạn chuyển tiếp hoặc phát hành thay đổi versioned.

## Bảo mật và hiệu năng

Search template không phải danh sách quyền. Việc một biến xuất hiện trong template không có nghĩa mọi người dùng được phép truy vấn mọi giá trị. Server phải xác thực, phân quyền và giới hạn tập kết quả trên mỗi request.

Một số lưu ý:

- Không công bố filter làm lộ dữ liệu nhạy cảm hoặc cấu trúc nội bộ.
- Whitelist sort field; không đưa tên cột tùy ý từ client xuống SQL.
- Giới hạn page size và độ phức tạp của filter.
- Áp dụng tenant/user scope trong truy vấn trước pagination.
- Không đưa token bí mật hoặc dữ liệu nhạy cảm vào query string vì URI có thể xuất hiện trong log, browser history và cache.
- Với GET search, giữ semantics an toàn: request không làm thay đổi trạng thái nghiệp vụ.
- Cache key cần tính đến các query variable ảnh hưởng đến kết quả và phạm vi authorization.

Nếu quyền hoặc trạng thái resource thay đổi, server có thể công bố hoặc ẩn search link phù hợp. Dù vậy, endpoint vẫn phải kiểm tra quyền ở phía server vì client có thể gọi URI trực tiếp.

## Kiểm thử search template

Kiểm thử cần xác nhận search link tồn tại, có relation đúng, được đánh dấu templated và chứa các biến dự kiến.

Ví dụ với MockMvc:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(org.hamcrest.Matchers.containsString("{?status")))
    .andExpect(jsonPath("$._links.search.href")
        .value(org.hamcrest.Matchers.containsString("customerId")))
    .andExpect(jsonPath("$._links.search.href")
        .value(org.hamcrest.Matchers.containsString("createdFrom")));
```

Ví dụ giả định collection endpoint trả HAL và có search relation. Cấu trúc URI template thực tế có thể khác về thứ tự biến hoặc encoding; test nên xác nhận tập biến và `templated: true`, không phụ thuộc thứ tự query variable nếu thứ tự không thuộc hợp đồng.

Tiếp theo, kiểm thử endpoint search với các tổ hợp biến:

```java
mockMvc.perform(get("/api/orders/search")
        .param("status", "PENDING")
        .param("customerId", customerId.toString())
        .param("createdFrom", "2026-11-01"))
    .andExpect(status().isOk());
```

Nên kiểm tra service nhận đúng giá trị đã bind, response có embedded item và page links giữ filter. Ngoài ra cần kiểm thử parameter bị thiếu, rỗng, sai format, nhiều giá trị, ký tự đặc biệt, page size vượt giới hạn và người dùng không đủ quyền.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Trả link search cố định không có template | Client phải tự biết và ghép query parameter. | Công bố URI template với các biến được hỗ trợ. |
| Quên `templated: true` | Client có thể xem dấu ngoặc nhọn là một phần URI thông thường. | Dùng link builder hỗ trợ template và kiểm tra HAL output. |
| Dùng tên biến khác với `@RequestParam` | Client mở rộng template nhưng server không bind đúng giá trị. | Khai báo `@RequestParam(name = ...)` tường minh. |
| Nghĩ template mô tả type và validation | Client không biết enum, format hoặc giới hạn giá trị. | Dùng tài liệu API hoặc HAL-FORMS metadata bổ sung. |
| Ghép query string thủ công | Sai encoding, delimiter hoặc mất filter. | Dùng URI template expansion và URI builder. |
| Đưa `Pageable` vào template nhưng không kiểm tra biến thực tế | Thiếu `page`, `size` hoặc `sort` dù endpoint có hỗ trợ. | Kiểm thử template và bổ sung biến theo cơ chế phù hợp. |
| Page link làm mất điều kiện search | Client chuyển sang tập kết quả khác khi theo `next`. | Giữ query context trong các page links. |
| Xem search link là quyền truy cập | Client có thể gọi trực tiếp endpoint với giá trị tùy ý. | Authorization và validation ở server trên mọi request. |

## Ghi nhớ

- Search link dùng relation `search` để công bố chức năng tìm kiếm hoặc lọc resource.
- URI template theo RFC 6570 mô tả các biến có thể mở rộng, ví dụ `{?status,customerId}`.
- Trong HAL, link template được đánh dấu `templated: true`.
- `WebMvcLinkBuilder` có thể tạo template từ mapping controller và các `@RequestParam` tùy chọn; dùng `methodOn(...)` để tham chiếu mapping, không gọi nghiệp vụ.
- Tên query variable phải khớp hợp đồng endpoint và được giữ ổn định.
- URI template không mô tả đầy đủ kiểu, prompt, options hoặc validation; dùng HAL-FORMS khi cần metadata form.
- Với pagination, giữ filter/sort trong `self` và `next` links; client nên theo `href` thay vì tự tính page.
- Kiểm tra encoding, repeated values, parameter sai định dạng, giới hạn truy vấn và quyền truy cập ở server.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Links and URI Templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [RFC 6570 – URI Template](https://www.rfc-editor.org/rfc/rfc6570)
- [IANA Link Relations Registry – search](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
