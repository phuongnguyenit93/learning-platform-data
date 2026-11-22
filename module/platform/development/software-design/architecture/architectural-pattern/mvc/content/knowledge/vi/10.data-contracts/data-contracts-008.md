# Truyền danh sách, phân trang và thông tin điều hướng

Trong ứng dụng MVC, nhiều màn hình cần hiển thị danh sách dài như đơn hàng, khóa học, người dùng hoặc lịch sử giao dịch. Nếu trả toàn bộ dữ liệu trong một lần, máy chủ có thể truy vấn quá nhiều bản ghi, phản hồi lớn và giao diện khó sử dụng. Nếu chỉ trả một mảng phần tử mà không có thông tin trang hoặc liên kết điều hướng, client cũng khó biết còn dữ liệu hay không và phải yêu cầu trang tiếp theo như thế nào.

Hợp đồng dữ liệu cho danh sách cần mô tả rõ đầu vào tìm kiếm, cách phân trang và sắp xếp, dữ liệu của trang hiện tại, metadata tổng hợp và những hướng điều hướng hợp lệ. Controller tiếp nhận tham số, Service áp dụng quy tắc truy vấn, Repository lấy dữ liệu, DTO hoặc ViewModel định nghĩa cấu trúc phản hồi, còn View trình bày danh sách và liên kết điều hướng.

## 1. Hợp đồng dữ liệu của một danh sách

Hợp đồng dữ liệu (data contract) xác định cấu trúc, ý nghĩa và quy tắc của dữ liệu trao đổi giữa các thành phần. Với một danh sách, hợp đồng thường có hai phần: tiêu chí request và kết quả response.

### 1.1. Tiêu chí request

Một request danh sách thường có các nhóm tham số:

- **Bộ lọc:** trạng thái, loại, người phụ trách, khoảng ngày hoặc từ khóa.
- **Phân trang:** số trang và kích thước trang, hoặc cursor và giới hạn.
- **Sắp xếp:** trường cần sắp xếp và chiều tăng/giảm.
- **Ngữ cảnh:** Locale, tenant hoặc phạm vi dữ liệu được xác định từ danh tính đã xác thực.

Ví dụ:

```http
GET /orders?status=PAID&keyword=laptop&page=0&size=20&sort=CREATED_AT&direction=DESC
Accept: application/json
```

Trong hợp đồng này, `page=0` là trang đầu tiên theo quy ước zero-based; `size=20` yêu cầu tối đa 20 phần tử; `sort=CREATED_AT&direction=DESC` yêu cầu sắp xếp theo thời gian tạo giảm dần.

### 1.2. Kết quả response

Một response danh sách nên mô tả:

- Các phần tử của trang hiện tại.
- Số trang hiện tại và kích thước trang.
- Tổng số phần tử hoặc thông tin cho biết còn trang tiếp theo.
- Trạng thái đầu/cuối trang.
- Quy tắc sắp xếp đang áp dụng.
- Liên kết hoặc thông tin để đi đến trang khác.

Ví dụ JSON:

```json
{
  "items": [
    {
      "id": "ord-1024",
      "orderNumber": "ORD-1024",
      "status": "PAID",
      "total": "1250000.00",
      "currency": "VND"
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 53,
    "totalPages": 3,
    "first": true,
    "last": false,
    "hasNext": true,
    "hasPrevious": false
  },
  "sort": [
    {
      "field": "CREATED_AT",
      "direction": "DESC"
    }
  ],
  "links": {
    "self": "/orders?status=PAID&keyword=laptop&page=0&size=20&sort=CREATED_AT&direction=DESC",
    "next": "/orders?status=PAID&keyword=laptop&page=1&size=20&sort=CREATED_AT&direction=DESC",
    "last": "/orders?status=PAID&keyword=laptop&page=2&size=20&sort=CREATED_AT&direction=DESC"
  }
}
```

Đây là hợp đồng minh họa. Tên trường và định dạng có thể khác, nhưng ý nghĩa cần nhất quán. Ví dụ, `number` phải được quy định là zero-based hay one-based; `totalElements` là tổng số phần tử phù hợp với bộ lọc hay chỉ là số phần tử của trang hiện tại.

### 1.3. Không trả Entity trực tiếp làm hợp đồng

Entity thường chứa quan hệ nội bộ, trạng thái persistence, dữ liệu nhạy cảm hoặc các trường không cần cho giao diện. Hãy ánh xạ sang DTO hoặc ViewModel chỉ chứa những trường cần thiết.

Ví dụ, danh sách đơn hàng có thể cần mã đơn, tên khách hàng, trạng thái, ngày tạo và tổng tiền. Nó không cần đối tượng thanh toán đầy đủ, thông tin xác thực hoặc toàn bộ lịch sử thay đổi của đơn hàng.

## 2. Phân trang theo số trang (offset/page-based pagination)

Phân trang theo số trang chia kết quả thành các đoạn có kích thước cố định. Client gửi số trang và số phần tử muốn nhận.

Với:

- (N): tổng số phần tử phù hợp.
- (S): kích thước trang.
- (P): số trang, bắt đầu từ 0.

Vị trí bắt đầu của trang là:

```text
offset = P * S
totalPages = ceil(N / S)
```

Ví dụ có 53 đơn hàng và kích thước trang 20:

| Trang (zero-based) | Offset | Số phần tử |
|---:|---:|---:|
| 0 | 0 | 20 |
| 1 | 20 | 20 |
| 2 | 40 | 13 |

Nếu danh sách rỗng, `totalElements=0` và `totalPages=0`. Hợp đồng nên quy định rõ cách biểu diễn `first`, `last`, `hasNext` và `hasPrevious` trong trường hợp này.

### 2.1. Ưu điểm và giới hạn

Page-based pagination dễ hiểu và phù hợp với danh sách có thể nhảy đến một trang cụ thể. Nó thường thuận tiện khi giao diện cần hiển thị “Trang 2 trên 5” hoặc cho phép người dùng chọn trang cuối.

Tuy nhiên, truy vấn offset lớn có thể tốn kém vì cơ sở dữ liệu phải bỏ qua nhiều bản ghi trước khi lấy phần cần thiết. Ngoài ra, khi dữ liệu thay đổi giữa các request, phần tử có thể dịch chuyển giữa các trang, gây trùng hoặc bỏ sót trong quá trình duyệt.

### 2.2. Kích thước trang phải có giới hạn

Không nên tin client có thể yêu cầu kích thước bất kỳ. Máy chủ cần đặt:

- Giá trị mặc định nếu client không truyền.
- Kích thước tối thiểu hợp lệ.
- Kích thước tối đa để bảo vệ tài nguyên.
- Quy tắc khi tham số sai định dạng hoặc vượt giới hạn.

Ví dụ, API có thể mặc định 20 phần tử và giới hạn tối đa 100. Con số cụ thể phụ thuộc dữ liệu và hiệu năng của hệ thống.

## 3. Page, Slice và Cursor: chọn đúng mô hình

Không phải danh sách nào cũng cần tổng số phần tử hoặc số trang chính xác. Chọn mô hình theo nhu cầu giao diện và chi phí truy vấn.

| Mô hình | Dữ liệu metadata | Điểm mạnh | Hạn chế |
|---|---|---|---|
| Page | Trang hiện tại, tổng phần tử, tổng số trang | Hiển thị số trang và trang cuối | Thường cần truy vấn đếm tổng |
| Slice | Trang hiện tại, có trang tiếp theo hay không | Không cần tổng chính xác | Không thể hiển thị tổng số trang chính xác |
| Cursor/keyset | Cursor tiếp theo/trước, giới hạn | Phù hợp dữ liệu lớn và cuộn liên tục | Khó nhảy đến trang tùy ý |

### 3.1. Page

Dùng Page khi sản phẩm cần biết tổng số phần tử hoặc số trang, ví dụ màn hình quản trị có điều hướng đến trang cuối.

Trong Spring Data, `Page<T>` cung cấp nội dung, số trang, kích thước và tổng số phần tử. Để tính tổng, framework thường cần một truy vấn count riêng. Với truy vấn phức tạp hoặc dữ liệu lớn, chi phí count có thể đáng kể.

### 3.2. Slice

Dùng Slice khi chỉ cần biết còn dữ liệu hay không, ví dụ nút “Xem thêm”. Framework có thể lấy nhiều hơn một phần tử so với giới hạn để xác định có trang tiếp theo, mà không cần tính tổng toàn bộ.

Slice phù hợp khi tổng số bản ghi không quan trọng với trải nghiệm. Không nên tự tạo `totalPages` giả từ số trang đã tải.

### 3.3. Cursor hoặc keyset pagination

Cursor pagination xác định vị trí tiếp theo dựa trên giá trị sắp xếp của bản ghi cuối cùng đã nhận, thay vì số lượng bản ghi cần bỏ qua.

Ví dụ, nếu danh sách sắp xếp theo `createdAt DESC` và `id DESC`, cursor có thể chứa cặp giá trị của phần tử cuối:

```json
{
  "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTE5VDA4OjMwOjAwWiIsImlkIjoib3JkLTEwMjQifQ"
}
```

Client gửi cursor đó trong request tiếp theo:

```http
GET /orders?limit=20&after=eyJjcmVhdGVkQXQiOiIyMDI2LTExLTE5VDA4OjMwOjAwWiIsImlkIjoib3JkLTEwMjQifQ
```

Cursor nên được xem là token điều hướng do máy chủ phát hành. Nếu cursor chứa dữ liệu có thể bị sửa, cần ký hoặc mã hóa và kiểm tra tính hợp lệ. Cursor cũng cần gắn với bộ lọc, thứ tự sắp xếp và phạm vi người dùng phù hợp để tránh dùng lại trong một truy vấn khác.

Cursor pagination thường phù hợp với feed, nhật ký hoặc dữ liệu tăng liên tục. Nó không thuận tiện cho giao diện cần nhảy trực tiếp đến trang số 40.

## 4. Quy tắc sắp xếp phải ổn định và được kiểm soát

### 4.1. Luôn có thứ tự xác định

Nếu chỉ sắp xếp theo thời gian tạo, nhiều bản ghi có thể cùng timestamp. Khi đó thứ tự giữa chúng không được xác định đầy đủ và kết quả giữa các request có thể thay đổi.

Hãy thêm một trường phân biệt để tạo thứ tự ổn định, thường là ID:

```sql
ORDER BY created_at DESC, id DESC
```

Thứ tự ổn định đặc biệt quan trọng với cursor pagination, vì cursor cần xác định duy nhất vị trí tiếp theo.

### 4.2. Chỉ cho phép trường sắp xếp trong danh sách hợp lệ

Không nối trực tiếp giá trị `sort` do client gửi vào SQL. Hãy ánh xạ tên trường API sang cột hoặc thuộc tính được hỗ trợ.

Ví dụ:

```java
public enum OrderSortField {
    CREATED_AT,
    ORDER_NUMBER,
    TOTAL
}

public final class OrderSorts {

    private OrderSorts() {}

    public static Sort toStableSort(
            OrderSortField field,
            Sort.Direction direction) {
        String property = switch (field) {
            case CREATED_AT -> "createdAt";
            case ORDER_NUMBER -> "orderNumber";
            case TOTAL -> "total";
        };

        return Sort.by(direction, property).and(
            Sort.by(direction, "id")
        );
    }
}
```

Tên trường trong API không nhất thiết phải trùng với tên thuộc tính persistence. Bảng ánh xạ giúp hợp đồng bên ngoài ổn định ngay cả khi cấu trúc Entity thay đổi.

### 4.3. Sắp xếp nhiều trường

Một số danh sách cần nhiều tiêu chí, ví dụ trạng thái tăng dần rồi ngày tạo giảm dần. Hợp đồng cần xác định cú pháp, thứ tự ưu tiên và các trường được phép.

Không nên để client gửi biểu thức SQL hoặc tên cột tùy ý. Với từng trường, máy chủ cần xác thực chiều sắp xếp và áp dụng tie-breaker ổn định nếu cần.

## 5. Bộ lọc và phân trang phải đi cùng nhau

Khi người dùng lọc danh sách rồi chuyển trang, request tiếp theo phải giữ nguyên các bộ lọc và thứ tự sắp xếp. Nếu chỉ truyền `page=1` mà mất `status=PAID`, người dùng sẽ chuyển sang một tập dữ liệu khác.

Ví dụ:

```text
/orders?status=PAID&keyword=laptop&page=0&size=20&sort=CREATED_AT&direction=DESC
/orders?status=PAID&keyword=laptop&page=1&size=20&sort=CREATED_AT&direction=DESC
```

Một query criteria có kiểu có thể biểu diễn hợp đồng đầu vào:

```java
public record OrderSearchCriteria(
    String keyword,
    OrderStatus status,
    LocalDate fromDate,
    LocalDate toDate,
    int page,
    int size,
    OrderSortField sortField,
    Sort.Direction direction
) {}
```

Controller chuyển query parameter thành criteria; Service kiểm tra ngày bắt đầu/kết thúc, giới hạn page/size và xác thực trường sort. Repository nhận criteria đã được chuẩn hóa.

Cần quy định cách xử lý từ khóa rỗng, khoảng ngày không hợp lệ, trạng thái không hỗ trợ và giá trị tham số bị lặp. Đừng để mỗi Controller tự áp dụng một cách hiểu khác nhau.

## 6. Metadata và liên kết điều hướng

Metadata cho biết vị trí của trang hiện tại trong tập kết quả. Liên kết điều hướng cho client biết nơi có thể đi tiếp.

### 6.1. Các trường metadata phổ biến

| Trường | Ý nghĩa |
|---|---|
| `number` | Số trang hiện tại |
| `size` | Kích thước trang được áp dụng |
| `numberOfElements` | Số phần tử thực tế trong trang hiện tại |
| `totalElements` | Tổng số phần tử phù hợp với bộ lọc |
| `totalPages` | Tổng số trang |
| `first` | Có phải trang đầu không |
| `last` | Có phải trang cuối không |
| `hasNext` | Có trang tiếp theo không |
| `hasPrevious` | Có trang trước không |

Hợp đồng cần phân biệt `numberOfElements` và `totalElements`. Ví dụ trang cuối có thể chứa 13 phần tử trong khi tổng danh sách là 53.

Nếu dùng Slice hoặc cursor, một số trường tổng hợp có thể không tồn tại. Hãy thiết kế response phản ánh đúng thông tin mà hệ thống thực sự biết, không điền số ước lượng vào trường có ý nghĩa chính xác.

### 6.2. Liên kết theo quan hệ

Một response có thể cung cấp các liên kết:

- `self`: request hiện tại.
- `first`: trang đầu.
- `prev`: trang trước.
- `next`: trang tiếp.
- `last`: trang cuối nếu biết tổng số trang.

Liên kết giúp client không phải tự xây URL và tự đoán quy tắc query parameter. Nếu dùng định dạng hypermedia, có thể biểu diễn link theo quan hệ chuẩn; API cũng có thể đưa chúng trong trường `links` của JSON hoặc header `Link` khi phù hợp.

Không cung cấp `next` khi không còn trang tiếp theo. Với cursor, liên kết tiếp theo có thể mang cursor opaque thay vì số trang.

### 6.3. Giữ nguyên bộ lọc trong link

Khi tạo link điều hướng, cần giữ lại các tham số ảnh hưởng tập kết quả như:

- Từ khóa.
- Trạng thái.
- Khoảng ngày.
- Trường và chiều sắp xếp.
- Kích thước trang nếu sản phẩm cho phép người dùng thay đổi.

Không nhất thiết giữ các tham số chỉ phục vụ tracking hoặc trạng thái tạm thời không còn ý nghĩa ở trang tiếp theo.

## 7. Ví dụ Spring MVC: xây dựng hợp đồng danh sách

Ví dụ dưới đây dùng Spring Data để truy vấn danh sách đơn hàng và chuyển kết quả thành DTO riêng. Các lớp domain, repository và mapper được rút gọn để tập trung vào hợp đồng.

### 7.1. Request criteria và DTO

```java
public record OrderSearchRequest(
    String keyword,
    OrderStatus status,
    Integer page,
    Integer size,
    OrderSortField sort,
    SortDirection direction
) {}

public enum SortDirection {
    ASC,
    DESC
}

public record OrderRowView(
    UUID id,
    String orderNumber,
    String customerName,
    String statusLabel,
    String createdAtText,
    String totalText
) {}

public record PageMetadata(
    int number,
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious
) {}

public record OrderListResponse(
    List<OrderRowView> items,
    PageMetadata page,
    Map<String, String> links
) {}
```

Request DTO phản ánh những tham số client được phép gửi. Response DTO mô tả rõ dữ liệu và metadata công khai. Việc tách hai loại giúp API không phụ thuộc trực tiếp vào cấu trúc `Page` nội bộ của Spring Data.

### 7.2. Controller tiếp nhận request

```java
@RestController
@RequestMapping("/api/orders")
public class OrderQueryController {

    private final OrderQueryService orderQueryService;

    public OrderQueryController(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @GetMapping
    public OrderListResponse search(
            @ModelAttribute OrderSearchRequest request,
            Authentication authentication) {

        return orderQueryService.search(
            request,
            authentication.getName()
        );
    }
}
```

Controller bind query parameter vào request DTO và chuyển danh tính đã xác thực cho Service. Nếu API có yêu cầu validation chi tiết, có thể dùng Bean Validation và xử lý lỗi tham số tập trung.

### 7.3. Service chuẩn hóa phân trang và truy vấn

```java
@Service
public class OrderQueryService {

    private final OrderRepository repository;
    private final OrderAccessPolicy accessPolicy;
    private final OrderViewMapper mapper;

    public OrderListResponse search(
            OrderSearchRequest request,
            String username) {

        int pageNumber = Math.max(
            request.page() == null ? 0 : request.page(), 0
        );
        int pageSize = Math.min(
            Math.max(request.size() == null ? 20 : request.size(), 1),
            100
        );

        UserContext viewer = accessPolicy.requireViewer(username);

        OrderSortField sortField =
            request.sort() == null
                ? OrderSortField.CREATED_AT
                : request.sort();

        SortDirection requestedDirection =
            request.direction() == null
                ? SortDirection.DESC
                : request.direction();
        Sort.Direction direction = Sort.Direction.valueOf(
            requestedDirection.name()
        );

        Sort sort = OrderSorts.toStableSort(sortField, direction);
        Pageable pageable = PageRequest.of(pageNumber, pageSize, sort);

        Page<OrderProjection> result = repository.searchVisibleTo(
            request.keyword(),
            request.status(),
            viewer,
            pageable
        );

        List<OrderRowView> items = result.getContent()
            .stream()
            .map(mapper::toRowView)
            .toList();

        PageMetadata metadata = new PageMetadata(
            result.getNumber(),
            result.getSize(),
            result.getNumberOfElements(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast(),
            result.hasNext(),
            result.hasPrevious()
        );

        OrderSearchRequest normalizedRequest = new OrderSearchRequest(
            request.keyword(),
            request.status(),
            pageNumber,
            pageSize,
            sortField,
            requestedDirection
        );
        Map<String, String> links =
            OrderPageLinks.from(normalizedRequest, metadata);

        return new OrderListResponse(items, metadata, links);
    }
}
```

Ví dụ minh họa việc chuẩn hóa page/size, kiểm tra phạm vi người xem, truy vấn và ánh xạ kết quả. Trong triển khai thật, cần xử lý giá trị sort không hợp lệ theo hợp đồng (trả lỗi hoặc dùng mặc định), xác thực bộ lọc và tạo link bằng cơ chế URL builder để encode tham số đúng cách.

Không nên chỉ clamp mọi tham số sai mà không có quy tắc. Một API có thể chọn từ chối `size=0`, `page=-1` hoặc sort không hỗ trợ bằng lỗi 400; một giao diện nội bộ có thể chuẩn hóa một số giá trị. Điều quan trọng là hành vi được công bố và kiểm thử.

### 7.4. Tạo liên kết trang

Một lớp tạo link có thể dùng URI builder để giữ bộ lọc và thay số trang:

```java
public final class OrderPageLinks {

    private OrderPageLinks() {}

    public static Map<String, String> from(
            OrderSearchRequest request,
            PageMetadata page) {

        Map<String, String> links = new LinkedHashMap<>();

        links.put("self", uri(request, page.number()));

        if (!page.first()) {
            links.put("first", uri(request, 0));
            links.put("prev", uri(request, page.number() - 1));
        }

        if (page.hasNext()) {
            links.put("next", uri(request, page.number() + 1));
        }

        if (!page.last() && page.totalPages() > 0) {
            links.put("last", uri(request, page.totalPages() - 1));
        }

        return Map.copyOf(links);
    }

    private static String uri(OrderSearchRequest request, int page) {
        UriComponentsBuilder builder =
            UriComponentsBuilder.fromPath("/api/orders")
                .queryParam("page", page)
                .queryParam("size", request.size())
                .queryParam("sort", request.sort())
                .queryParam("direction", request.direction());

        if (request.keyword() != null && !request.keyword().isBlank()) {
            builder.queryParam("keyword", request.keyword());
        }
        if (request.status() != null) {
            builder.queryParam("status", request.status());
        }
        return builder.build().encode().toUriString();
    }
}
```

Đây là ví dụ rút gọn. Trong ứng dụng thực tế, cần dùng cùng một quy tắc mặc định cho page, size và sort ở cả truy vấn lẫn link; không để link phản ánh giá trị đầu vào chưa chuẩn hóa trong khi Service đã áp dụng giá trị khác. Có thể đưa criteria đã chuẩn hóa vào hàm tạo link để tránh sai lệch.

### 7.5. View HTML hiển thị danh sách và điều hướng

Với server-side rendering, Controller có thể đưa một ViewModel gồm danh sách, metadata và URL điều hướng vào Model. Thymeleaf có thể hiển thị:

```html
<nav aria-label="Điều hướng danh sách đơn hàng">
  <a th:if="${page.hasPrevious}"
     th:href="${links.prev}">Trang trước</a>

  <span th:text="|Trang ${page.number + 1}|"></span>

  <a th:if="${page.hasNext}"
     th:href="${links.next}">Trang tiếp</a>
</nav>
```

Với trang HTML, số trang hiển thị cho người dùng thường bắt đầu từ 1 dù API nội bộ dùng zero-based. Chuyển đổi chỉ nên thực hiện ở View; không thay đổi quy ước giữa các request.

Nên dùng phần tử `nav` với nhãn dễ hiểu, thể hiện trạng thái trang hiện tại và không tạo liên kết đến trang không tồn tại. Với giao diện có nhiều trang, có thể hiển thị một cửa sổ các số trang quanh trang hiện tại, cùng liên kết đầu/cuối khi phù hợp.

## 8. Hợp đồng phân trang cho API và giao diện HTML

API và SSR có thể dùng cùng kết quả truy vấn, nhưng cách thể hiện điều hướng khác nhau.

| Khía cạnh | API JSON | View HTML |
|---|---|---|
| Trang hiện tại | Metadata trong JSON | Nhãn trang và trạng thái giao diện |
| Trang tiếp theo | URL trong `links.next` hoặc cursor | Thẻ liên kết `a` |
| Bộ lọc | Query parameters | Form GET và query parameters |
| Trạng thái rỗng | Mảng `items` rỗng | Thông báo và hướng dẫn |
| Lỗi tham số | Cấu trúc lỗi API và status code | Thông báo cạnh bộ lọc hoặc trang lỗi |
| Ngôn ngữ | Có thể trả mã ổn định hoặc nội dung theo Locale được công bố | Nhãn và thông báo được bản địa hóa |

Với giao diện HTML, form lọc thường dùng GET để người dùng có thể tải lại, đánh dấu hoặc chia sẻ URL. Khi submit bộ lọc mới, thường đặt lại page về 0 vì tập kết quả đã thay đổi.

Ví dụ:

```html
<form method="get" action="/orders">
  <label for="status">Trạng thái</label>
  <select id="status" name="status">
    <option value="">Tất cả</option>
    <option value="PAID">Đã thanh toán</option>
    <option value="PENDING">Chờ thanh toán</option>
  </select>

  <label for="keyword">Từ khóa</label>
  <input id="keyword" name="keyword" />

  <input type="hidden" name="page" value="0" />
  <input type="hidden" name="size" value="20" />

  <button type="submit">Lọc</button>
</form>
```

Nếu người dùng thay đổi bộ lọc khi đang ở trang 5, cần quay về trang đầu hoặc xác định lại trang hợp lệ. Không nên giữ page cũ một cách máy móc vì kết quả mới có thể ít trang hơn.

## 9. Trạng thái biên và tính nhất quán của danh sách

### 9.1. Danh sách rỗng

Danh sách rỗng là kết quả hợp lệ của truy vấn, không phải lỗi máy chủ. Response có thể là:

```json
{
  "items": [],
  "page": {
    "number": 0,
    "size": 20,
    "numberOfElements": 0,
    "totalElements": 0,
    "totalPages": 0,
    "first": true,
    "last": true,
    "hasNext": false,
    "hasPrevious": false
  },
  "links": {
    "self": "/orders?page=0&size=20"
  }
}
```

View có thể hiển thị “Không tìm thấy kết quả” và gợi ý xóa bớt bộ lọc. Không hiển thị nút “Trang tiếp” nếu không có dữ liệu tiếp theo.

### 9.2. Yêu cầu trang vượt quá trang cuối

Nếu client yêu cầu `page=9` trong khi chỉ có 3 trang, cần quy định rõ hành vi:

- Trả một trang rỗng cùng metadata cho số trang đã yêu cầu.
- Chuẩn hóa về trang cuối và trả link hoặc redirect.
- Trả lỗi tham số nếu hợp đồng quy định trang ngoài phạm vi là không hợp lệ.

Với API danh sách, trả trang rỗng thường dễ dự đoán; với SSR, có thể redirect về trang cuối hoặc hiển thị trạng thái rỗng. Dù chọn cách nào, không nên âm thầm trả dữ liệu của trang khác mà vẫn giữ URL cũ.

### 9.3. Dữ liệu thay đổi giữa các lần đọc

Giả sử người dùng đang xem trang 1. Trong lúc đó, một đơn hàng mới được thêm hoặc một bản ghi bị xóa. Với offset pagination, vị trí các bản ghi có thể thay đổi khiến người dùng nhìn thấy phần tử lặp hoặc bỏ sót khi đi tiếp.

Nếu cần duyệt một tập dữ liệu ổn định, có thể dùng snapshot, thời điểm chốt dữ liệu hoặc cursor/keyset pagination. Không phải danh sách nào cũng cần snapshot; hãy xác định yêu cầu nhất quán của nghiệp vụ.

### 9.4. Tổng số phần tử có thể thay đổi

Truy vấn lấy trang và truy vấn count có thể chạy ở những thời điểm khác nhau. Vì vậy, `totalElements` có thể không phản ánh chính xác cùng một snapshot với `items` nếu dữ liệu thay đổi đồng thời và transaction isolation không giữ snapshot.

Hợp đồng nên xem tổng số là metadata tại thời điểm truy vấn, trừ khi hệ thống có cơ chế snapshot rõ ràng. Với màn hình giám sát cập nhật liên tục, cần chấp nhận hoặc biểu diễn tính gần đúng theo yêu cầu.

## 10. Hiệu năng và lựa chọn chiến lược truy vấn

### 10.1. Tránh truy vấn toàn bộ dữ liệu

Không tải toàn bộ bảng rồi mới cắt danh sách trong bộ nhớ. Hãy áp dụng giới hạn và offset/cursor ngay trong truy vấn cơ sở dữ liệu.

### 10.2. Chú ý truy vấn count

Page-based pagination cần tổng số phần tử để tính số trang. Với truy vấn join hoặc bộ lọc phức tạp, count query có thể tốn kém. Kiểm tra execution plan và chỉ lấy tổng khi giao diện thực sự cần.

Nếu chỉ cần “còn dữ liệu hay không”, Slice có thể phù hợp hơn.

### 10.3. Tạo chỉ mục theo bộ lọc và thứ tự phổ biến

Các cột thường dùng để lọc và sắp xếp như tenant, trạng thái, thời gian tạo và ID có thể cần chỉ mục phù hợp. Thứ tự cột trong composite index cần dựa trên truy vấn thực tế, không áp dụng một mẫu chung cho mọi bảng.

### 10.4. Chọn page size hợp lý

Trang quá nhỏ làm tăng số lần request; trang quá lớn làm tăng truy vấn, bộ nhớ, thời gian serialize và kích thước response. Nên đo theo kích thước bản ghi và trải nghiệm người dùng.

### 10.5. Dùng cursor cho dữ liệu lớn hoặc tăng liên tục

Với cursor/keyset, truy vấn có thể dùng điều kiện theo khóa sắp xếp thay vì bỏ qua nhiều bản ghi. Ví dụ sắp xếp giảm dần theo `createdAt` và `id`, truy vấn tiếp theo lấy những bản ghi có cặp khóa nhỏ hơn cặp cuối trang trước.

Cần bảo đảm điều kiện so sánh tương ứng với thứ tự sắp xếp, xử lý giá trị null và dùng tie-breaker duy nhất. Cursor không nên được tạo từ một trường không ổn định hoặc không có quy tắc so sánh rõ.

## 11. Bảo mật trong hợp đồng danh sách

Danh sách thường là nơi dễ lộ dữ liệu vì một request có thể trả về nhiều bản ghi.

- **Phân quyền theo đối tượng:** chỉ trả bản ghi mà người dùng được phép xem.
- **Cô lập tenant:** áp dụng tenant scope ở truy vấn phía máy chủ, không tin tenant ID do client gửi.
- **Giới hạn kích thước:** đặt maximum page size hoặc maximum limit.
- **Kiểm soát sort:** chỉ cho phép trường sắp xếp đã định nghĩa.
- **Tham số truy vấn an toàn:** dùng parameter binding, không nối chuỗi SQL từ từ khóa.
- **Giảm thiểu dữ liệu:** chỉ trả trường cần thiết trong DTO.
- **Cursor integrity:** kiểm tra chữ ký, thời hạn và phạm vi của cursor nếu token có thể bị sửa.
- **Cache:** tránh cache công khai response phụ thuộc quyền hoặc người dùng.

Việc client thay đổi `page`, `size`, `sort` hoặc `filter` không được phép làm vượt qua quyền truy cập. Mỗi request trang tiếp theo vẫn phải áp dụng xác thực và phân quyền như request đầu.

## 12. Phiên bản hóa và khả năng tương thích của hợp đồng

Khi API được nhiều client sử dụng, thay đổi cấu trúc response có thể ảnh hưởng ứng dụng web, mobile hoặc đối tác tích hợp.

Một số nguyên tắc:

- Giữ tên và ý nghĩa trường ổn định.
- Không đổi zero-based sang one-based mà không có kế hoạch tương thích.
- Không đổi `totalElements` từ tổng số phù hợp sang số phần tử trang hiện tại.
- Khi thêm trường tùy chọn, bảo đảm client cũ có thể bỏ qua.
- Khi bỏ trường hoặc thay đổi ý nghĩa, dùng chiến lược phiên bản hóa phù hợp.
- Công bố giới hạn page size, quy tắc sort, filter và lỗi tham số.
- Nếu chuyển từ page sang cursor, cần định nghĩa hợp đồng mới thay vì giả vờ cursor là số trang.

Không nên đưa kiểu nội bộ như `PageImpl` trực tiếp ra API công khai nếu không muốn hợp đồng phụ thuộc chi tiết framework. DTO response riêng giúp kiểm soát phiên bản và cấu trúc.

## 13. Kiểm thử hợp đồng danh sách và điều hướng

Cần kiểm thử cả dữ liệu và cách client đi đến trang kế tiếp.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không truyền page/size | Áp dụng giá trị mặc định được công bố |
| Page âm hoặc size không hợp lệ | Từ chối hoặc chuẩn hóa theo hợp đồng |
| Size vượt mức tối đa | Không trả vượt giới hạn |
| Danh sách có nhiều trang | Metadata và link next/last chính xác |
| Trang đầu | Không có link prev |
| Trang cuối | Không có link next |
| Danh sách rỗng | Items rỗng, metadata nhất quán |
| Lọc rồi chuyển trang | Filter và sort được giữ lại |
| Sort không hỗ trợ | Bị từ chối hoặc dùng mặc định đã công bố |
| Hai bản ghi cùng timestamp | Tie-breaker giữ thứ tự ổn định |
| Người dùng khác tenant | Không nhận dữ liệu ngoài phạm vi |
| Cursor bị sửa hoặc hết hạn | Bị từ chối theo hợp đồng |
| Dữ liệu thay đổi giữa các trang | Hành vi nhất quán với chiến lược đã chọn |

Nên có:

- Unit test cho việc chuẩn hóa tham số và tạo metadata.
- Repository integration test cho query, sort, filter và pagination.
- Controller test cho binding, status code và cấu trúc response.
- Contract test để xác nhận JSON không vô tình đổi tên hoặc ý nghĩa trường.
- UI test để xác nhận form lọc, liên kết trang và trạng thái rỗng hoạt động đúng.

Đặc biệt, hãy kiểm tra các trang biên: trang đầu, trang giữa, trang cuối, danh sách rỗng, trang vượt phạm vi và kích thước trang tối đa.

## 14. Những lỗi thiết kế thường gặp

### Chỉ trả mảng phần tử

Client không biết còn dữ liệu hay không, tổng số phần tử là bao nhiêu hoặc phải lấy trang tiếp theo bằng cách nào. Bổ sung metadata hoặc cursor theo đúng nhu cầu.

### Trả Page nội bộ trực tiếp ra API

Cấu trúc của framework có thể thay đổi và chứa nhiều trường không thuộc hợp đồng công khai. Dùng response DTO do ứng dụng kiểm soát.

### Không giới hạn page size

Một request có thể yêu cầu quá nhiều bản ghi, gây tải lớn cho cơ sở dữ liệu và máy chủ. Đặt giới hạn ở phía server.

### Không giữ filter khi điều hướng

Người dùng chuyển trang nhưng mất từ khóa hoặc trạng thái đang lọc. Tạo link từ criteria đã chuẩn hóa và giữ các tham số ảnh hưởng kết quả.

### Sort theo dữ liệu client tùy ý

Nối tên trường vào SQL có thể gây lỗi hoặc injection. Dùng allowlist và ánh xạ sang thuộc tính truy vấn an toàn.

### Không có tie-breaker

Sắp xếp theo timestamp có thể không tạo thứ tự duy nhất. Thêm trường ổn định như ID để tránh bản ghi dịch chuyển giữa các trang.

### Dùng Page dù không cần tổng

Truy vấn count có thể tốn kém. Nếu giao diện chỉ cần biết còn trang sau, cân nhắc Slice hoặc cursor.

### Dùng cursor nhưng không ràng buộc với query

Cursor của một bộ lọc có thể bị dùng lại với bộ lọc khác hoặc bị sửa. Kiểm tra tính toàn vẹn và ngữ cảnh của cursor.

## 15. Checklist thiết kế hợp đồng danh sách

1. Request định nghĩa rõ filter, page/limit hoặc cursor và sort.
2. Quy ước page index zero-based hay one-based được công bố.
3. Server có default và maximum page size.
4. Response phân biệt items, numberOfElements và totalElements.
5. Page, Slice hoặc cursor được chọn theo nhu cầu thực tế.
6. Sort chỉ nhận trường được hỗ trợ và có thứ tự ổn định.
7. Link điều hướng giữ bộ lọc, sort và kích thước trang.
8. Không tạo link next/prev khi không tồn tại.
9. Danh sách rỗng và page ngoài phạm vi có hành vi được định nghĩa.
10. DTO response không làm lộ Entity hoặc dữ liệu nhạy cảm.
11. Mọi request trang tiếp theo đều áp dụng lại quyền và tenant scope.
12. Có kiểm thử cho trang biên, dữ liệu thay đổi và cursor không hợp lệ.

## Kết luận

Hợp đồng truyền danh sách cần mô tả đầy đủ dữ liệu của trang hiện tại, quy tắc lọc/sắp xếp, metadata và hướng điều hướng. Page phù hợp khi cần tổng số trang; Slice phù hợp khi chỉ cần biết còn dữ liệu; cursor phù hợp với tập dữ liệu lớn hoặc tăng liên tục. Trong MVC, Controller tiếp nhận tiêu chí, Service áp dụng quy tắc, Repository truy vấn có giới hạn, DTO/ViewModel định nghĩa response và View tạo điều hướng dễ hiểu. Hợp đồng rõ ràng giúp client duyệt dữ liệu nhất quán, máy chủ kiểm soát tài nguyên và các tầng có thể thay đổi độc lập.

