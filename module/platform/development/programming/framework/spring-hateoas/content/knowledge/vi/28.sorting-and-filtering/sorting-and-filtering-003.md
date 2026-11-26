# Query parameter ổn định

Một API tìm kiếm đơn hàng thường nhận các điều kiện như trạng thái, khách hàng, khoảng ngày, thứ tự sắp xếp và trang cần xem. Nếu tên hoặc ý nghĩa của các query parameter thay đổi tùy endpoint, client phải ghi nhớ nhiều quy tắc riêng và rất dễ tạo request sai. Một query parameter ổn định giúp API giữ hợp đồng dễ dự đoán qua các lần phát triển: cùng một tên luôn mang cùng ý nghĩa, kiểu dữ liệu và quy tắc xử lý được công bố rõ ràng.

Trong Spring MVC, query parameter thường được ánh xạ bằng `@RequestParam`; Spring Data Web có thể ánh xạ `page`, `size`, `sort` thành `Pageable`. Với Spring HATEOAS, server có thể tạo link hoặc URI template để client khám phá cách lọc và điều hướng. Khi trả collection có phân trang, các link `self`, `next`, `prev` cần giữ đúng filter và sort của truy vấn hiện tại.

## Query parameter là một phần của hợp đồng API

Query component nằm sau dấu `?` trong URI. Ví dụ:

```http
GET /api/orders?status=PENDING&customerId=cus-73&page=0&size=20&sort=createdAt,desc
```

Trong request này:

- `status` lọc đơn hàng theo trạng thái.
- `customerId` giới hạn kết quả theo khách hàng.
- `page` xác định trang cần đọc.
- `size` giới hạn số item trong trang.
- `sort` xác định thứ tự kết quả.

Một parameter được xem là ổn định khi API giữ được các cam kết như tên, kiểu dữ liệu, cardinality, format, default, semantics của giá trị bị thiếu và cách kết hợp với các parameter khác. Ổn định không có nghĩa là không bao giờ được bổ sung parameter mới; nó có nghĩa client hiện tại vẫn hiểu đúng những parameter mà nó đang sử dụng.

Query parameter là một phần của URI và thường ảnh hưởng đến kết quả GET. Vì vậy, thay đổi tên hoặc ý nghĩa của nó có thể là thay đổi hợp đồng công khai, ảnh hưởng đến client, bookmark, cache, log, monitoring và các link hypermedia đã phát hành.

## Xác định hợp đồng cho từng parameter

Trước khi viết controller, hãy mô tả rõ từng parameter:

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Name | Tên chính xác trong URI là gì? | `customerId` |
| Type | Giá trị được parse thành kiểu nào? | UUID |
| Format | Chuỗi được biểu diễn theo quy ước nào? | UUID chuẩn, ngày ISO `yyyy-MM-dd` |
| Cardinality | Một giá trị hay nhiều giá trị? | Một `customerId`, nhiều `status` |
| Required | Có bắt buộc xuất hiện không? | `status` tùy chọn |
| Default | Khi không gửi thì xử lý thế nào? | Mặc định sort theo ngày tạo giảm dần |
| Empty/null | Giá trị rỗng hoặc chuỗi `null` có ý nghĩa gì? | `status=` bị từ chối hoặc được xem như không lọc |
| Combination | Kết hợp với parameter khác bằng AND hay OR? | Nhiều status được hiểu là OR |
| Error | Giá trị sai trả lỗi nào? | UUID không hợp lệ trả `400 Bad Request` |

Không để client phải đoán những quy tắc này từ implementation. Tài liệu API và response hypermedia cần phản ánh cùng một hợp đồng.

## Dùng tên rõ nghĩa và ổn định

Chọn tên theo ngữ nghĩa nghiệp vụ hoặc khái niệm API, không dựa trên tên biến tạm hay tên cột database. Ví dụ `customerId` dễ hiểu hơn `cust_fk`; `createdAfter` dễ hiểu hơn `ts1`.

Một bộ tên có thể dùng nhất quán trên các endpoint:

| Mục đích | Tên gợi ý |
| --- | --- |
| Lọc theo trạng thái | `status` |
| Lọc theo khách hàng | `customerId` |
| Từ ngày | `createdFrom` |
| Đến ngày | `createdTo` |
| Tìm chuỗi | `q` hoặc `query` |
| Sắp xếp | `sort` |
| Trang | `page` |
| Kích thước trang | `size` |

Không đổi `customerId` thành `customer` ở một endpoint khác nếu cả hai đều có cùng ý nghĩa. Cũng không tái sử dụng `status` để mang nghĩa khác nhau giữa collection đơn hàng và collection thanh toán mà không có tài liệu rõ ràng.

## Ánh xạ query parameter bằng @RequestParam

Khai báo tên parameter tường minh để giữ hợp đồng độc lập với tên biến Java:

```java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderSearchController {

    private final OrderSearchService orderService;

    OrderSearchController(OrderSearchService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/search")
    OrderSearchResult search(
            @RequestParam(name = "customerId", required = false) UUID customerId,
            @RequestParam(name = "createdFrom", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate createdFrom,
            @RequestParam(name = "createdTo", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate createdTo) {

        return orderService.search(customerId, createdFrom, createdTo);
    }
}
```

Ví dụ giả định `orderService` được inject và `OrderSearchResult` là kiểu response của ứng dụng. Tên trong `@RequestParam(name = ...)` là tên client phải gửi, dù sau này tên biến Java được đổi.

Với ngày, dùng format rõ ràng như ISO-8601 thay vì phụ thuộc locale của máy chủ. Ví dụ `createdFrom=2026-11-01` luôn có cùng cách hiểu. Không dùng chuỗi ngày kiểu `01/11/2026` nếu API không định nghĩa rõ thứ tự ngày/tháng.

## Giá trị bị thiếu, rỗng và mặc định

Ba trường hợp sau có thể khác nhau:

```http
GET /api/orders
GET /api/orders?status=
GET /api/orders?status=null
```

- Parameter bị thiếu: client không đưa ra điều kiện lọc.
- Parameter có chuỗi rỗng: client gửi parameter nhưng không có giá trị.
- Parameter có literal `null`: client gửi bốn ký tự `n`, `u`, `l`, `l`, trừ khi API tự định nghĩa quy ước khác.

Không tự động coi ba trường hợp là tương đương. Chọn một quy tắc và kiểm thử nó. Nếu giá trị rỗng không hợp lệ, hãy trả lỗi validation rõ ràng; nếu nó có nghĩa là bỏ filter, hãy công bố điều đó.

`@RequestParam(defaultValue = "...")` cung cấp giá trị mặc định khi parameter không có hoặc có giá trị rỗng theo cơ chế binding của Spring MVC. Khi cần phân biệt missing với empty, không nên dựa vào `defaultValue`; hãy nhận giá trị thô hoặc dùng một lớp binding/validation phù hợp.

Ví dụ default cho một parameter:

```java
@GetMapping("/api/orders")
OrderPage search(
        @RequestParam(name = "status", required = false) OrderStatus status,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return orderService.search(status, size);
}
```

Default `size=20` cần được công bố trong tài liệu API và giữ ổn định. Thay đổi default có thể làm cùng một URI trả về số lượng item hoặc thứ tự kết quả khác trước, dù client không thay đổi request.

## Kiểu dữ liệu và format nên ổn định

Query parameter thường được truyền dưới dạng chuỗi trong URI, sau đó Spring chuyển đổi sang kiểu Java. Nên chọn kiểu có format rõ ràng:

| Ý nghĩa | Kiểu Java thường dùng | Format công khai |
| --- | --- | --- |
| Định danh | `UUID` | UUID dạng chuỗi chuẩn |
| Ngày | `LocalDate` | `yyyy-MM-dd` |
| Thời điểm | `Instant` | ISO-8601 UTC, ví dụ `2026-11-26T08:30:00Z` |
| Số nguyên | `Integer` hoặc `Long` | Chữ số thập phân, không có dấu phân cách hàng nghìn |
| Trạng thái | Enum hoặc value object | Mã ổn định như `PENDING` |
| Boolean | `Boolean` | `true` hoặc `false` theo quy ước API |

Không dùng tên enum Java làm hợp đồng nếu tên đó có thể bị đổi mà không có kế hoạch tương thích. Có thể dùng converter riêng để ánh xạ mã API ổn định sang enum nội bộ.

Với khoảng thời gian, định nghĩa rõ múi giờ và tính bao gồm của hai đầu mút. Ví dụ `createdFrom` và `createdTo` có thể biểu diễn ngày theo UTC hoặc theo timezone nghiệp vụ; client phải biết chính xác. Tránh để server dùng timezone mặc định của máy chạy ứng dụng.

## Một giá trị hay nhiều giá trị?

API cần quy định cardinality của parameter. Một trạng thái đơn có thể được gửi như:

```http
GET /api/orders?status=PENDING
```

Nếu cần lọc theo nhiều trạng thái, có thể dùng parameter lặp:

```http
GET /api/orders?status=PENDING&status=PAID
```

Spring MVC có thể bind parameter lặp vào collection:

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/orders")
OrderSearchResult search(
        @RequestParam(name = "status", required = false)
        List<OrderStatus> statuses) {
    return orderService.searchByStatuses(statuses);
}
```

Trong ví dụ, nhiều status được hiểu là tập lựa chọn; service có thể dùng điều kiện OR để lấy đơn hàng có một trong các trạng thái. Nếu API muốn semantics khác, phải mô tả rõ.

Một số API dùng giá trị phân tách bằng dấu phẩy, ví dụ `status=PENDING,PAID`. Hai dạng `status=PENDING&status=PAID` và `status=PENDING,PAID` không nên bị trộn lẫn mà không công bố. Hãy chọn một cách, giữ nhất quán và kiểm thử binding cũng như URI encoding.

## Query parameter sort ổn định

Spring Data Web thường nhận `sort` theo dạng:

```http
GET /api/orders?sort=createdAt,desc&sort=id,desc
```

Mỗi giá trị `sort` có thể mô tả một thuộc tính và hướng sắp xếp. Có thể khai báo nhiều sort order để tạo thứ tự xác định, ví dụ `createdAt DESC` rồi `id DESC` làm tie-breaker.

Controller có thể nhận `Pageable`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
OrderPage all(
        @PageableDefault(size = 20,
            sort = {"createdAt", "id"},
            direction = Sort.Direction.DESC) Pageable pageable) {
    return orderService.findAll(pageable);
}
```

Tên property trong `sort` phải nằm trong danh sách API cho phép. Không chuyển một sort expression tùy ý từ client xuống SQL. Hãy whitelist sort fields và direction; với thuộc tính API khác tên domain property, dùng mapping rõ ràng.

Nếu thay đổi tên sort field công khai, hãy duy trì alias cũ trong thời gian chuyển tiếp hoặc phát hành thay đổi versioned. Đừng đổi ngữ nghĩa của `sort=createdAt` từ “ngày tạo” sang “ngày cập nhật” mà không đổi tên/phiên bản hợp đồng.

## Query parameter pagination

Các parameter `page`, `size` và `sort` cần có quy tắc ổn định:

- `page` xác định trang; Spring Data thường dùng index bắt đầu từ `0`.
- `size` xác định số item tối đa trong trang.
- `sort` xác định thứ tự; có thể lặp để khai báo nhiều sort order.

Đặt default và maximum cho size. Không cho client yêu cầu một page size không giới hạn. Nếu API đổi page numbering hoặc tên parameter, phải cập nhật cả controller binding, link pagination, tài liệu và test contract.

Khi kết hợp với filter, cùng một filter phải được giữ trên tất cả link điều hướng. Ví dụ:

```http
GET /api/orders?status=PENDING&customerId=cus-73&page=1&size=20&sort=createdAt,desc
```

Link `next` cần tiếp tục truy vấn `status=PENDING` và `customerId=cus-73`; nếu chỉ giữ `page` và `size`, client sẽ rời khỏi tập kết quả ban đầu.

## Giữ query context khi tạo link bằng Spring HATEOAS

Với endpoint có mapping rõ ràng, `WebMvcLinkBuilder` có thể tạo link theo method controller:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link filtered = linkTo(methodOn(OrderSearchController.class)
    .search(customerId, createdFrom, createdTo))
    .withRel("search");
```

Ví dụ giả định phương thức `search(...)` có các `@RequestParam` tương ứng. Việc tham chiếu qua `methodOn(...)` giúp URI được tạo theo mapping của controller, thay vì viết cứng path và tên query parameter ở nhiều nơi.

Với pagination dựa trên `Page<T>`, ưu tiên `PagedResourcesAssembler` để tạo `PagedModel` và page links. Assembler dùng request hiện tại cùng cấu hình pageable resolver để xây link `self`, `next`, `prev` và các link biên phù hợp. Các filter bổ sung cần được kiểm thử để bảo đảm chúng vẫn có mặt trong link.

Không tự ghép chuỗi query bằng `"?page=" + page` hoặc `"&status=" + status`. Cách này dễ làm mất filter, sai encoding, trùng dấu `?`, hoặc làm hỏng URI khi giá trị có dấu cách, `&`, `+` hay ký tự Unicode.

## URI template cho filter có thể khám phá

Một API hypermedia có thể công bố link tìm kiếm dưới dạng URI template để client biết các biến query có thể điền:

```java
Link search = linkTo(methodOn(OrderSearchController.class)
    .search(null, null, null))
    .withRel("search");
```

Khi các tham số query được đánh dấu là tùy chọn và serializer hỗ trợ URI template, link có thể được biểu diễn với biến query tương ứng. Client có thể mở rộng template bằng giá trị `status`, `createdFrom` hoặc `createdTo`.

URI template chỉ mô tả cấu trúc URI. Nó không thay thế tài liệu về kiểu dữ liệu, format, default hoặc semantics của parameter. Hãy công bố metadata phù hợp trong tài liệu API hoặc media type có khả năng mô tả input, và kiểm thử template được serialize đúng.

## Encoding và thứ tự query parameter

Query parameter phải được encode theo quy tắc URI. Ví dụ, dấu cách, dấu `&`, dấu `+` hoặc ký tự tiếng Việt trong giá trị cần được xử lý đúng để không bị hiểu nhầm thành delimiter.

Không tự encode một phần rồi ghép với URL đã encode vì có thể tạo double encoding. Hãy dùng `UriComponentsBuilder`, `UriBuilder` hoặc API link của Spring để tạo URI:

```java
import java.net.URI;

import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder
    .fromPath("/api/orders/search")
    .queryParam("q", "giao hàng & đổi địa chỉ")
    .queryParam("status", "PENDING")
    .build()
    .encode()
    .toUri();
```

`encode()` giúp encode query value theo quy tắc URI. Hãy kiểm thử URI kết quả và cách framework parse lại giá trị để bảo đảm round-trip chính xác.

Thứ tự các cặp query parameter thường không làm thay đổi semantics của request, nhưng có thể ảnh hưởng cache key, chữ ký URL hoặc hệ thống logging. Nếu API ký request hoặc dùng canonical URL, cần định nghĩa cách sắp xếp và chuẩn hóa parameter rõ ràng. Không yêu cầu client tự sắp xếp query string nếu server không công bố quy tắc đó.

## Tương thích ngược khi thay đổi query parameter

Các thay đổi sau có thể phá vỡ client:

- Đổi tên parameter.
- Đổi kiểu hoặc format, ví dụ UUID sang mã nội bộ khác.
- Đổi default khiến cùng URI trả kết quả khác.
- Đổi cardinality từ một giá trị sang nhiều giá trị nhưng không giữ tương thích.
- Đổi semantics từ OR sang AND khi gửi nhiều giá trị.
- Đổi timezone hoặc tính bao gồm của `createdFrom`/`createdTo`.
- Đổi sort field hoặc hướng mặc định.
- Đổi tên `page`/`size` hoặc page index từ zero-based sang one-based.

Khi cần thay đổi:

1. Thêm parameter mới với tên và semantics rõ ràng.
2. Duy trì parameter cũ trong giai đoạn chuyển tiếp nếu có thể.
3. Nếu hai dạng cùng được hỗ trợ, định nghĩa ưu tiên khi client gửi cả hai.
4. Đánh dấu parameter cũ deprecated trong tài liệu và response documentation.
5. Cập nhật link/URI template để client mới khám phá cách dùng mới.
6. Chỉ loại bỏ parameter cũ trong một thay đổi versioned hoặc sau thời gian deprecation đã công bố.

Không dùng cùng một parameter name cho hai ý nghĩa khác nhau tùy ngữ cảnh ngầm định. Nếu semantics thay đổi căn bản, hãy dùng tên mới hoặc version API.

## Validation và bảo mật

Query parameter đến từ client là dữ liệu đầu vào không đáng tin cậy. Cần kiểm tra:

- Kiểu và format có parse được không.
- Khoảng ngày có hợp lệ và `createdFrom` có trước `createdTo` không.
- Page size có nằm trong giới hạn không.
- Sort field có thuộc allowlist không.
- Enum hoặc danh sách giá trị có thuộc tập cho phép không.
- Nhiều parameter có bị lặp quá mức hoặc tạo truy vấn quá nặng không.
- Filter có được áp dụng trong phạm vi tenant và quyền truy cập hiện tại không.

Không nối trực tiếp query value vào SQL. Dùng repository query parameterization, Criteria API hoặc query builder an toàn. Không dựa vào việc client chỉ sử dụng URI template do server cung cấp; client có thể gửi request tùy ý.

Nếu query parameter ảnh hưởng đến dữ liệu theo người dùng/tenant, không để cache dùng chung trả kết quả của một phạm vi truy cập cho người khác. Cache key và authorization phải được thiết kế phù hợp với phạm vi dữ liệu.

## Kiểm thử hợp đồng query parameter

Kiểm thử cần xác nhận controller binding và link hypermedia giữ đúng tên, kiểu, default và query context.

### Kiểm tra tên và binding

```java
mockMvc.perform(get("/api/orders/search")
        .param("customerId", customerId.toString())
        .param("createdFrom", "2026-11-01")
        .param("createdTo", "2026-11-30"))
    .andExpect(status().isOk());
```

Test này xác nhận các tên công khai được binding. Có thể verify service nhận đúng `UUID` và `LocalDate` bằng mock hoặc kiểm tra kết quả.

### Kiểm tra nhiều giá trị

```java
mockMvc.perform(get("/api/orders")
        .param("status", "PENDING", "PAID"))
    .andExpect(status().isOk());
```

Test cần xác nhận nhiều giá trị được hiểu theo semantics đã công bố, ví dụ OR giữa các trạng thái. Đừng chỉ kiểm tra status 200 nếu điều quan trọng là query đã nhận đúng danh sách.

### Kiểm tra query context trong page links

```java
mockMvc.perform(get(
        "/api/orders?status=PENDING&customerId=" + customerId
            + "&page=0&size=20&sort=createdAt,desc")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.containsString("status=PENDING")))
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("customerId=" + customerId)));
```

Ví dụ giả định endpoint trả HAL pagination và có trang tiếp theo. Trong test thực tế, dùng URI builder hoặc MockMvc `.param(...)` để tránh ghép chuỗi không an toàn. Nếu framework encode giá trị, hãy parse query của `href` rồi kiểm tra decoded parameter thay vì so sánh chuỗi thô.

### Những trường hợp cần kiểm thử thêm

- Parameter bị thiếu, rỗng và literal `null`.
- Default `size`, `sort` và trạng thái khi parameter không xuất hiện.
- UUID, ngày hoặc enum sai format.
- Khoảng ngày không hợp lệ.
- Sort field không được phép và page size vượt giới hạn.
- Parameter lặp và parameter có dấu phẩy.
- Giá trị có dấu cách, ký tự Unicode, `&`, `+` và `%`.
- Filter/sort được giữ trên link `self`, `next`, `prev`.
- Alias parameter cũ và mới trong giai đoạn deprecation.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng tên query parameter khác nhau cho cùng ý nghĩa | Client phải duy trì nhiều quy tắc không cần thiết. | Chuẩn hóa tên và giữ tên ổn định. |
| Không khai báo tên `@RequestParam` tường minh | Đổi tên biến Java có thể làm thay đổi binding nếu metadata tên tham số không được giữ. | Dùng `name`/`value` rõ ràng. |
| Không định nghĩa missing, empty và `null` | Client và server hiểu khác nhau về filter. | Công bố semantics và kiểm thử cả ba trường hợp. |
| Đổi default âm thầm | Cùng URI trả về kết quả khác trước. | Coi default là một phần hợp đồng và deprecate/version khi thay đổi. |
| Không quy định cardinality | Client không biết lặp parameter hay dùng dấu phẩy. | Chọn một format và giữ nhất quán. |
| Tự ghép query string | URI dễ lỗi encoding hoặc mất filter. | Dùng API URI builder và link builder. |
| Page link làm mất filter/sort | Client rời khỏi tập kết quả đang duyệt. | Giữ query context và kiểm thử link HAL. |
| Cho phép sort field tùy ý | Truy vấn tốn kém hoặc lộ thuộc tính nội bộ. | Whitelist sort fields. |
| Thay đổi timezone hoặc semantics date range | Kết quả lọc khác với client kỳ vọng. | Dùng format và timezone rõ ràng, có test biên. |

## Ghi nhớ

- Query parameter là một phần của hợp đồng URI; giữ ổn định tên, kiểu, format, cardinality, default và semantics.
- Dùng `@RequestParam(name = ...)` để tên công khai không phụ thuộc tên biến Java.
- Phân biệt parameter bị thiếu, rỗng và literal `null`; định nghĩa default rõ ràng.
- Chọn format ổn định cho UUID, ngày, thời điểm, enum và boolean.
- Công bố cách gửi nhiều giá trị: parameter lặp hay chuỗi phân tách.
- Giữ `page`, `size`, `sort` và các filter nhất quán; page links phải bảo toàn query context.
- Dùng `WebMvcLinkBuilder`, `PagedResourcesAssembler` và `UriComponentsBuilder` thay vì ghép URL thủ công.
- Thay đổi query parameter cần kế hoạch tương thích ngược và deprecation.
- Validate sort, page size, date range, tenant scope và mọi query input ở server.
- Kiểm thử binding, encoding, repeated values, default và link hypermedia đã serialize.

## Tài liệu tham khảo

- [Spring Framework – @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Data Commons – Web support and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Framework API – UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [RFC 3986 – Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
