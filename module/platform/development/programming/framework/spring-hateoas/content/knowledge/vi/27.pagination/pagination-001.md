# Mô hình pagination

Một API quản lý đơn hàng có thể chứa hàng triệu bản ghi. Nếu mỗi request trả toàn bộ danh sách, response sẽ lớn, tốn bộ nhớ, làm tăng thời gian truyền tải và gây áp lực lên database. Pagination chia kết quả thành những phần nhỏ để client đọc dần, đồng thời cung cấp thông tin giúp client tiếp tục từ vị trí phù hợp.

Trong Spring, pagination thường đi qua nhiều lớp: controller nhận `Pageable`, service chuyển yêu cầu truy vấn xuống repository, repository trả về `Page`, `Slice` hoặc một cửa sổ kết quả, rồi tầng web chuyển dữ liệu thành representation. Với Spring HATEOAS, `PagedModel` kết hợp nội dung trang, metadata và các link điều hướng để client khám phá trang tiếp theo mà không phải tự ghép URL.

## Pagination giải quyết vấn đề gì?

Pagination giới hạn lượng dữ liệu được trả về trong một response. Thay vì lấy toàn bộ 50.000 đơn hàng, API có thể trả 20 đơn hàng mỗi lần. Client xem trang hiện tại, rồi theo link `next` để lấy phần tiếp theo.

Một mô hình pagination cần xác định:

- **Tập kết quả:** điều kiện lọc nào xác định các bản ghi thuộc collection.
- **Thứ tự:** bản ghi được sắp xếp theo tiêu chí nào.
- **Kích thước phần:** mỗi response trả tối đa bao nhiêu phần tử.
- **Vị trí tiếp tục:** client đang ở trang nào hoặc có cursor nào.
- **Metadata:** có cần tổng số phần tử, tổng số trang hoặc chỉ cần biết còn dữ liệu hay không.
- **Điều hướng:** client tiếp tục, quay lại hoặc bắt đầu từ đâu.

Pagination không chỉ là cắt một danh sách trong bộ nhớ. Cách truy vấn, thứ tự sắp xếp, tính ổn định giữa các request và hợp đồng hypermedia đều ảnh hưởng đến tính đúng đắn của kết quả.

## Các mô hình pagination phổ biến

Ba nhóm thường gặp là offset/page-based, cursor/keyset và scrolling/window. Chúng giải quyết các nhu cầu khác nhau:

| Mô hình | Vị trí được gửi | Ưu điểm | Giới hạn chính |
| --- | --- | --- | --- |
| Offset/page-based | Số trang và kích thước, hoặc offset và limit | Dễ hiểu, dễ nhảy đến trang cụ thể, có thể cung cấp tổng số trang. | Trang sâu có thể tốn chi phí; dữ liệu thay đổi có thể làm dịch chuyển item giữa các trang. |
| Cursor/keyset | Cursor hoặc giá trị khóa của vị trí cuối | Phù hợp duyệt tập dữ liệu lớn, tránh bỏ qua nhiều dòng ở offset sâu. | Khó nhảy đến trang tùy ý; cần thứ tự ổn định và cursor được quản lý đúng. |
| Window/scroll | Vị trí cuộn và giới hạn phần tử | Hỗ trợ đọc tuần tự theo từng cửa sổ, có thể dùng offset hoặc keyset. | Phụ thuộc khả năng scrolling của Spring Data store/repository. |

Không có một mô hình phù hợp cho mọi endpoint. Danh sách quản trị cần nhảy đến trang 12 có thể hợp với page-based; luồng sự kiện lớn hoặc duyệt lịch sử theo thời gian thường hợp với cursor/keyset.

## Offset pagination

Offset pagination chọn một đoạn của kết quả bằng vị trí bắt đầu và số lượng phần tử. Trong SQL, cách triển khai thường tương đương `LIMIT` và `OFFSET`:

```sql
SELECT id, status, created_at
FROM orders
WHERE status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

Query trên bỏ qua 40 bản ghi đầu tiên rồi trả tối đa 20 bản ghi tiếp theo. Nếu page index bắt đầu từ `0`, page `2` với size `20` có offset `40`.

Với page-based API, công thức cơ bản là:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Ví dụ:

| `page` | `size` | `offset` | Khoảng vị trí theo cách đếm từ 1 |
| ---: | ---: | ---: | --- |
| 0 | 20 | 0 | 1–20 |
| 1 | 20 | 20 | 21–40 |
| 2 | 20 | 40 | 41–60 |
| 3 | 20 | 60 | 61–80 |

Spring Data thường dùng page index bắt đầu từ `0`. Một số API có thể cấu hình nhận page index bắt đầu từ `1`; khi đó cần giữ quy ước nhất quán giữa request, metadata và link được sinh ra.

### Ưu điểm và giới hạn của offset

Offset dễ dùng vì client có thể yêu cầu một trang cụ thể. Nó cũng thuận tiện khi giao diện hiển thị số trang và tổng số trang.

Tuy nhiên, offset lớn có thể làm database phải đọc hoặc materialize nhiều dòng trước khi trả phần dữ liệu cần thiết. Khi dữ liệu được thêm hoặc xóa giữa hai request, vị trí của bản ghi có thể dịch chuyển. Client có thể thấy một item lặp lại hoặc bỏ sót nếu duyệt trang theo thứ tự không ổn định.

Vì vậy, offset pagination phù hợp với collection vừa phải, nhu cầu nhảy trang và truy vấn có index phù hợp. Cần giới hạn `pageSize` để tránh request trả payload quá lớn.

## Thứ tự sắp xếp phải ổn định

Pagination chỉ có ý nghĩa khi thứ tự bản ghi được xác định. Nếu chỉ sort theo `createdAt` và nhiều đơn hàng có cùng timestamp, database có thể trả chúng theo thứ tự khác nhau giữa các lần truy vấn.

Hãy thêm một khóa phân biệt duy nhất làm tie-breaker:

```java
PageRequest request = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
```

Thứ tự `createdAt DESC, id DESC` tạo ra thứ tự xác định hơn khi nhiều bản ghi có cùng thời điểm tạo. Với cursor/keyset, sort fields còn là cơ sở để server xác định vị trí tiếp tục.

Chỉ cho phép sort theo các thuộc tính API công bố. Không chuyển nguyên văn tên cột tùy ý từ client xuống SQL. Hãy whitelist thuộc tính được phép sort và kiểm tra hướng tăng/giảm.

## Spring Data: Pageable, Page và PageRequest

Spring Data cung cấp abstraction để truyền yêu cầu pagination từ web đến repository.

| Kiểu | Vai trò |
| --- | --- |
| `Pageable` | Mô tả page index, page size và sort order. |
| `PageRequest` | Implementation phổ biến để tạo `Pageable` bằng code. |
| `Page<T>` | Nội dung trang cùng metadata về tổng số phần tử và tổng số trang. |
| `Pageable` argument resolver | Chuyển query parameters của HTTP request thành `Pageable`. |

Tạo một `PageRequest` trong service hoặc test:

```java
Pageable pageable = PageRequest.of(
    1,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);

Page<Order> page = orderRepository.findAll(pageable);
```

`PageRequest.of(1, 20, ...)` yêu cầu trang thứ hai nếu index bắt đầu từ `0`. `Page<T>` cung cấp `getContent()`, `getNumber()`, `getSize()`, `getTotalElements()` và `getTotalPages()` cùng các thông tin điều hướng như `hasNext()` hoặc `hasPrevious()`.

### Nhận Pageable từ HTTP request

Spring Data Web có thể chuyển query parameters thành `Pageable` cho controller:

```http
GET /api/orders?page=1&size=20&sort=createdAt,desc&sort=id,desc
```

Ví dụ controller:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    Page<Order> all(
            @PageableDefault(size = 20, sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC) Pageable pageable) {
        return orders.findAll(pageable);
    }
}
```

`@PageableDefault` đặt kích thước và sort mặc định khi client không gửi giá trị tương ứng. Trong ứng dụng thực tế, controller thường trả representation DTO/HATEOAS thay vì domain entity như ví dụ tối giản.

Các tên parameter mặc định thường là `page`, `size` và `sort`. Có thể cấu hình resolver để đổi tên, page index hoặc giới hạn kích thước. Khi cấu hình thay đổi, link pagination cần dùng cùng resolver để client theo link vẫn tạo được request hợp lệ.

## Page và Slice khác nhau thế nào?

`Page<T>` chứa thông tin tổng số phần tử và tổng số trang. Để tính `totalElements`, repository thường cần một count query bổ sung ngoài query lấy nội dung trang.

`Slice<T>` chỉ cần biết trang hiện tại và liệu còn phần tử tiếp theo hay không. Nó không yêu cầu tổng số phần tử hoặc tổng số trang. Vì vậy, `Slice` có thể giảm chi phí khi client chỉ cần nút “Xem thêm” hoặc “Tiếp theo”.

| Tiêu chí | `Page<T>` | `Slice<T>` |
| --- | --- | --- |
| Nội dung hiện tại | Có | Có |
| `hasNext()` / `hasPrevious()` | Có | Có |
| Tổng số phần tử | Có | Không yêu cầu |
| Tổng số trang | Có | Không yêu cầu |
| Count query | Thường cần để tính tổng | Thường không cần count toàn bộ |
| Phù hợp | Giao diện cần tổng số và nhảy trang | Duyệt tiếp theo, không cần tổng số |

Chọn `Page` khi sản phẩm thực sự cần hiển thị tổng số kết quả hoặc số trang. Chọn `Slice` khi chỉ cần biết có phần tiếp theo để tránh chi phí count không cần thiết.

## Scrolling và Window trong Spring Data

Với tập kết quả lớn, Spring Data có mô hình scrolling để đọc dữ liệu theo từng cửa sổ. Một truy vấn scroll kết hợp ba thành phần:

1. Thứ tự sắp xếp ổn định.
2. Loại vị trí scroll: offset-based hoặc keyset-based.
3. Giới hạn số phần tử trong mỗi cửa sổ.

Kết quả là `Window<T>`. Từ window hiện tại, ứng dụng lấy `ScrollPosition` để yêu cầu window tiếp theo. Cách này phù hợp cho xử lý tuần tự, export hoặc API cursor khi repository/store hỗ trợ.

Ví dụ minh họa một repository method dùng keyset position:

```java
import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

interface OrderRepository extends Repository<Order, UUID> {

    Window<Order> findFirst50ByStatusOrderByCreatedAtDescIdDesc(
        OrderStatus status,
        KeysetScrollPosition position
    );
}
```

Gọi truy vấn từ đầu:

```java
Window<Order> window = orderRepository
    .findFirst50ByStatusOrderByCreatedAtDescIdDesc(
        OrderStatus.PENDING,
        ScrollPosition.keyset()
    );
```

Ví dụ phụ thuộc khả năng scrolling của Spring Data module/store và phiên bản đang dùng. Với các lần đọc tiếp theo, ứng dụng lấy vị trí từ phần tử cuối của window rồi truyền vào truy vấn tiếp theo. API có thể mã hóa vị trí đó thành cursor opaque cho client.

### Offset scrolling và keyset scrolling

Offset scrolling lưu vị trí bằng số lượng phần tử đã bỏ qua. Nó đơn giản nhưng vẫn có nhược điểm của offset sâu.

Keyset scrolling lưu các giá trị khóa sắp xếp của phần tử cuối cùng. Truy vấn tiếp theo dùng những giá trị này để tìm phần tử đứng sau theo thứ tự đã định. Database có thể tận dụng index phù hợp để tránh phải bỏ qua một lượng lớn bản ghi.

Keyset yêu cầu sort ổn định. Các thuộc tính dùng làm keyset thường cần không null, phải được đưa vào projection trả về và nên có index phù hợp. Cơ chế này có giới hạn khi cần nhảy đến một trang bất kỳ vì cursor đại diện cho vị trí tiếp nối, không phải số trang tuyệt đối.

## Cursor pagination ở tầng API

Cursor pagination công bố vị trí tiếp tục dưới dạng token opaque. Client không cần biết token chứa ID, timestamp hay các sort key nào.

Ví dụ request/response ở mức khái niệm:

```http
GET /api/orders?limit=50&after=eyJjcmVhdGVkQXQiOiIyMDI2LTExLTI2In0
```

```json
{
  "items": [
    { "id": "ord-1042", "status": "PENDING" },
    { "id": "ord-1043", "status": "PENDING" }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTI3In0"
}
```

Trong API hypermedia, thay vì yêu cầu client đọc `nextCursor` rồi tự ghép URL, server có thể công bố link `next` chứa cursor:

```json
{
  "_links": {
    "self": { "href": "/api/orders?limit=50&after=current-token" },
    "next": { "href": "/api/orders?limit=50&after=next-token" }
  }
}
```

Cursor nên được mã hóa hoặc ký để client không thể sửa vị trí, filter hay tenant context tùy ý. Server cần kiểm tra cursor có hợp lệ, còn hạn và phù hợp với truy vấn hiện tại hay không. Cursor không phải cơ chế phân quyền; mọi request tiếp theo vẫn phải xác thực và áp dụng authorization.

## Chọn mô hình nào cho endpoint?

| Nhu cầu | Gợi ý |
| --- | --- |
| Bảng quản trị có số trang và tổng số kết quả | `Page<T>` + `PagedModel` |
| Danh sách chỉ cần nút “Xem thêm” | `Slice<T>` hoặc cursor |
| Dữ liệu rất lớn, duyệt tuần tự theo thời gian/ID | Keyset scrolling hoặc cursor pagination |
| Client cần nhảy đến trang tùy ý | Offset/page-based |
| Database/store hỗ trợ scroll query và ứng dụng xử lý theo batch | `Window<T>` |
| API cần điều hướng theo hypermedia | Bọc kết quả vào `PagedModel`/`SlicedModel` hoặc custom model có link tương ứng |

Không chọn cursor chỉ vì nó mới hơn. Nếu client cần nhảy đến trang 40 hoặc hiển thị tổng số trang, cursor có thể làm trải nghiệm phức tạp hơn. Ngược lại, không dùng offset sâu cho luồng dữ liệu lớn chỉ vì `Pageable` dễ tích hợp.

## Mô hình pagination trong Spring HATEOAS

Spring HATEOAS cung cấp `PagedModel<T>` để biểu diễn một trang cùng metadata và link. Spring Data cung cấp `PagedResourcesAssembler<T>` để chuyển `Page<T>` thành `PagedModel`.

Lưu ý có hai lớp cùng tên `PagedModel` trong hệ sinh thái Spring: `org.springframework.hateoas.PagedModel` là representation model có thể mang hypermedia links; `org.springframework.data.web.PagedModel` là wrapper đơn giản cho page metadata, không cung cấp cùng mô hình navigation links. Khi xây REST API hypermedia, cần chọn đúng kiểu của Spring HATEOAS.

Một response paged hypermedia thường gồm:

- Các item đã được chuyển thành representation model.
- Page metadata như size, totalElements, totalPages và number.
- Các link điều hướng như `self`, `first`, `prev`, `next`, `last` tùy trạng thái trang và cấu hình.

Controller có thể nhận `PagedResourcesAssembler` và truyền item assembler:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderResourceController {

    private final OrderService orders;
    private final OrderModelAssembler assembler;

    OrderResourceController(OrderService orders, OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping("/api/orders")
    PagedModel<EntityModel<OrderView>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orders.findAll(pageable);
        return pagedAssembler.toModel(page, assembler);
    }
}
```

`OrderModelAssembler` cần triển khai `RepresentationModelAssembler<Order, EntityModel<OrderView>>`. `PagedResourcesAssembler.toModel(page, assembler)` chuyển từng item qua assembler và tạo page metadata cùng navigation links. Link được xây theo cấu hình pageable resolver và request hiện tại.

Nếu cần tạo link pagination dựa trên URI riêng, `PagedResourcesAssembler` có overload nhận self link. Dùng overload này khi endpoint cần một base URI khác với mapping mặc định, nhưng phải giữ filter và query parameters đúng với kết quả đang trả về.

### PagedModel và SlicedModel

`PagedModel<T>` phù hợp với `Page<T>` khi có metadata tổng số. Với `Slice<T>`, Spring HATEOAS/Spring Data cung cấp mô hình `SlicedModel<T>` và `SlicedResourcesAssembler` trong các phiên bản hỗ trợ. Mô hình slice tập trung vào việc có trang tiếp theo hay không, không công bố tổng số phần tử và tổng số trang như `PagedModel`.

Tên API và khả năng hỗ trợ phụ thuộc phiên bản Spring Data/Spring HATEOAS. Kiểm tra dependency thực tế trước khi dùng `SlicedResourcesAssembler`; nếu không có, có thể tạo custom `CollectionModel` và link `next` theo `Slice.hasNext()`.

## Pagination và các filter

Một page là một phần của một tập kết quả xác định bởi filter và sort. Ví dụ:

```http
GET /api/orders?status=PENDING&customerId=cus-73&page=1&size=20&sort=createdAt,desc
```

Khi client theo link `next`, server cần giữ các điều kiện `status`, `customerId` và `sort`. Nếu mất một filter, page tiếp theo sẽ thuộc một tập kết quả khác.

`PagedResourcesAssembler` sử dụng request và pageable resolver để tạo page links phù hợp với cấu hình. Hãy kiểm thử các filter bổ sung được giữ lại. Với custom query parameter, alias hoặc controller method có nhiều tham số, cần bảo đảm base link và resolver hiểu đúng toàn bộ ngữ cảnh.

Filter và cursor cần được ràng buộc với nhau. Nếu cursor được tạo cho `status=PENDING`, không nên cho client dùng lại cursor đó với `status=SHIPPED` nếu hai tập kết quả khác nhau. Có thể đưa fingerprint của query/filter vào cursor đã ký.

## Collection rỗng và trang ngoài phạm vi

Một truy vấn có thể trả collection rỗng. Với `Page<T>`, metadata vẫn có thể mô tả kích thước, tổng số phần tử bằng `0` và tổng số trang bằng `0`. Representation vẫn nên giữ self link để client biết resource/query đã được thực hiện.

Nếu client yêu cầu page index vượt quá phạm vi, API cần quy định hành vi nhất quán: trả page rỗng cùng metadata hoặc trả lỗi theo hợp đồng. Không để hành vi thay đổi tùy repository hoặc controller.

Khi serialize collection rỗng, framework có thể không suy ra kiểu phần tử từ nội dung. Với HAL embedded collection hoặc processor phụ thuộc generic type, cần cung cấp fallback type theo API của Spring HATEOAS phù hợp.

## Hiệu năng và giới hạn tài nguyên

Pagination giảm kích thước response nhưng không tự động làm query nhanh. Cần xem xét:

- **Index:** index cần hỗ trợ điều kiện filter và sort phổ biến.
- **Page size:** đặt default và maximum; không cho client yêu cầu kích thước không giới hạn.
- **Count query:** `Page` có thể phát sinh count query; dùng `Slice` nếu không cần tổng số.
- **Stable sort:** thêm unique tie-breaker để giảm dịch chuyển item.
- **Projection:** chỉ lấy các field cần cho response, tránh tải entity graph lớn.
- **N+1:** assembler không nên truy cập association lazy gây một query cho mỗi item.
- **Authorization:** áp dụng quyền truy cập ngay trong truy vấn/tập kết quả; không phân trang trước rồi mới loại bỏ item trái quyền.
- **Timeout và rate limit:** giới hạn chi phí của các truy vấn đắt hoặc page sâu.

Đặc biệt, không nên lấy toàn bộ danh sách vào memory rồi mới gọi `subList()` để phân trang. Repository cần thực hiện pagination ở tầng dữ liệu.

## Pagination và dữ liệu thay đổi giữa các request

Offset pagination không tạo snapshot nhất quán xuyên nhiều HTTP request. Ví dụ client lấy trang 0, sau đó có bản ghi mới được thêm lên đầu danh sách trước khi client lấy trang 1. Một số item có thể bị dịch chuyển qua ranh giới trang.

Các cách giảm ảnh hưởng:

- Dùng sort ổn định với khóa phân biệt duy nhất.
- Với luồng dữ liệu lớn, dùng cursor/keyset dựa trên sort key.
- Nếu nghiệp vụ cần snapshot nhất quán, xác định snapshot/version hoặc khoảng thời gian truy vấn.
- Tránh giả định `totalElements` không đổi trong suốt phiên duyệt collection.

Cursor/keyset cũng không tự bảo đảm snapshot nếu các sort key có thể thay đổi. Hãy chọn khóa tiếp tục ít thay đổi, ví dụ thời điểm tạo và ID bất biến.

## Kiểm thử mô hình pagination

Nên kiểm thử từ request đến repository/result model và response hypermedia.

### Kiểm tra Pageable và Page

```java
mockMvc.perform(get("/api/orders?page=1&size=20")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.number").value(1))
    .andExpect(jsonPath("$.page.totalElements").exists())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Ví dụ giả định response dùng HAL và được serialize từ `PagedModel`. Cấu trúc JSON cụ thể phụ thuộc media type và cấu hình; điều quan trọng là kiểm tra hợp đồng mà client sử dụng.

### Kiểm tra giới hạn page size

```java
mockMvc.perform(get("/api/orders?page=0&size=100000"))
    .andExpect(status().isOk());
```

Test trên chỉ minh họa request có kích thước lớn; test thực tế cần xác nhận resolver đã clamp về maximum được cấu hình hoặc trả lỗi theo chính sách API. Không để mặc định một request lớn được thực hiện không giới hạn.

### Kiểm tra filter và sort

```java
mockMvc.perform(get(
        "/api/orders?status=PENDING&page=0&size=20&sort=createdAt,desc")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("status=PENDING")))
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("sort=createdAt")));
```

Ngoài ra, nên có test cho trang đầu, trang giữa, trang cuối, collection rỗng, page ngoài phạm vi, sort không hợp lệ, quyền truy cập và cursor hết hạn/sai chữ ký nếu API hỗ trợ cursor.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Không có sort hoặc sort không ổn định | Item có thể lặp hoặc bị bỏ sót giữa các trang. | Dùng sort xác định và thêm unique tie-breaker. |
| Cho phép page size tùy ý | Response lớn và query tiêu tốn tài nguyên. | Đặt default và maximum page size. |
| Dùng `Page` dù không cần tổng số | Count query tăng chi phí không cần thiết. | Cân nhắc `Slice` hoặc cursor. |
| Dùng offset cho trang rất sâu | Database phải bỏ qua nhiều dòng. | Cân nhắc keyset/scrolling. |
| Phân trang trong bộ nhớ | Tải toàn bộ dữ liệu trước khi cắt danh sách. | Đẩy pagination xuống repository/database. |
| Mất filter khi tạo link tiếp theo | Trang sau không còn thuộc tập kết quả ban đầu. | Giữ query context trong page links. |
| Dùng cursor không ràng buộc query | Cursor có thể được tái sử dụng sai filter hoặc tenant. | Ký cursor và gắn nó với filter/sort context. |
| Phân trang trước khi áp dụng quyền | Có thể lộ số lượng hoặc tạo trang thiếu item sau lọc. | Áp dụng authorization trong query/tập kết quả trước pagination. |
| Dùng `CollectionModel` cho kết quả cần page metadata | Client không biết tổng số và trạng thái trang. | Dùng `PagedModel` hoặc mô hình slice tương ứng. |

## Ghi nhớ

- Pagination chia collection thành các phần nhỏ và cần xác định tập kết quả, sort, page size, vị trí tiếp tục và metadata.
- Offset/page-based dễ nhảy trang nhưng trang sâu và dữ liệu thay đổi có thể gây chi phí hoặc dịch chuyển item.
- Sort phải ổn định; thêm unique tie-breaker như ID.
- `Page<T>` có tổng số phần tử/trang; `Slice<T>` chỉ cần biết có phần tiếp theo.
- `Window<T>` và `ScrollPosition` hỗ trợ scrolling offset/keyset khi Spring Data store tương ứng có hỗ trợ.
- Cursor/keyset phù hợp duyệt dữ liệu lớn nhưng không thuận tiện để nhảy đến trang tùy ý.
- Spring HATEOAS dùng `PagedModel`; `PagedResourcesAssembler` chuyển `Page<T>` và item assembler thành paged representation.
- Giữ filter/sort trong link; giới hạn page size, tối ưu index và tránh count query khi không cần.
- Kiểm thử trang đầu/giữa/cuối, collection rỗng, query context, giới hạn tài nguyên và quyền truy cập.

## Tài liệu tham khảo

- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data Commons – Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data API – Pageable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html)
- [Spring Data API – Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html)
- [Spring Data API – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring HATEOAS API – PagedModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
