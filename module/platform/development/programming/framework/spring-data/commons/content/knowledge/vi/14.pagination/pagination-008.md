# Pageable.unpaged và biến thể có Sort theo phiên bản

Trong chương **Phân trang** của Spring Data Commons (`SPRING_DATA_COMMONS`), một tham số `Pageable` không bắt buộc luôn mô tả một trang có số thứ tự và kích thước. Nó còn có thể biểu đạt yêu cầu **không áp dụng phân trang qua tham số này** bằng `Pageable.unpaged()`.

Từ Spring Data Commons 3.2, có thêm `Pageable.unpaged(Sort)` để mang thứ tự sắp xếp mà vẫn không khai báo khoảng trang. Bài này phân biệt hai biến thể, cách dùng theo phiên bản và những điểm cần giữ đúng khi repository hoặc adapter nhận cả paged lẫn unpaged.

Commons cung cấp abstraction; module kho dữ liệu quyết định cách thực thi query tương ứng. Các ví dụ giả định module hỗ trợ kiểu query method và tham số đang minh họa.

## 1. Unpaged biểu đạt điều gì?

Ví dụ:

```java
import org.springframework.data.domain.Pageable;

Pageable request = Pageable.unpaged();
```

Đối tượng này có:

```text
isPaged()   = false
isUnpaged() = true
```

Ý nghĩa là không áp dụng một khoảng lấy theo page number/page size qua Pageable.

Nó không tự làm những việc sau:

- Bỏ điều kiện nghiệp vụ của query.
- Chuyển repository sang đọc một bảng hoặc collection khác.
- Xóa một giới hạn được khai báo ở nơi khác trong query.
- Bảo đảm nguồn dữ liệu có quy mô nhỏ.
- Biến kết quả thành một luồng streaming.

Nếu query đang lọc theo tenant và trạng thái, các điều kiện ấy vẫn có hiệu lực khi truyền unpaged.

Cần đọc unpaged như một chế độ của yêu cầu lấy dữ liệu, không phải tên gọi khác của “trang đầu”.

## 2. Unpaged không tham số không mang dynamic sort

Với:

```java
Pageable request = Pageable.unpaged();
```

`request.getSort()` biểu đạt `Sort.unsorted()`.

Có thể quan sát:

```java
System.out.println(request.isUnpaged());        // true
System.out.println(request.getSort().isSorted()); // false
```

Điều đó nói rằng request này không mang yêu cầu dynamic sort. Một thứ tự tĩnh trong tên method hoặc declared query vẫn có thể tồn tại.

Ví dụ method có `OrderByCreatedAtDesc` không mất thứ tự tĩnh chỉ vì caller dùng unpaged không tham số.

Cũng không được suy rằng “unsorted” có nghĩa store phải trả theo thứ tự chèn. Nếu thứ tự là một phần của hợp đồng nghiệp vụ, hãy biểu đạt nó bằng cơ chế được module hỗ trợ.

## 3. Biến thể unpaged(Sort) có từ Commons 3.2

Ví dụ:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort order = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable request = Pageable.unpaged(order);
```

Đối tượng vẫn là unpaged:

```text
isPaged()   = false
isUnpaged() = true
getSort()   = createdAt DESC, id DESC
```

Sắp xếp và phân trang là hai chiều thông tin riêng. Có thứ tự không bắt buộc phải có page size.

API ghi mốc `Since: 3.2` cho overload nhận Sort. Tham số Sort không được null; khi không cần thứ tự, dùng `Sort.unsorted()`. Xem [API Pageable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html).

Bảng phiên bản minh họa:

| Spring Data Commons | unpaged() | unpaged(Sort) |
| --- | --- | --- |
| 3.1.x | Có dạng không tham số. | Chưa có overload này. |
| Từ 3.2 | Có dạng không tham số. | Có dạng mang Sort. |

Có thể đối chiếu mã nguồn [Pageable tại tag 3.1.0](https://github.com/spring-projects/spring-data-commons/blob/3.1.0/src/main/java/org/springframework/data/domain/Pageable.java) và [Pageable tại tag 3.2.0](https://github.com/spring-projects/spring-data-commons/blob/3.2.0/src/main/java/org/springframework/data/domain/Pageable.java).

Mốc này là phiên bản của artifact Spring Data Commons. Không tự suy ra API có sẵn chỉ từ số phiên bản Java, Spring Framework hoặc một dependency Spring khác.

## 4. Ví dụ repository dùng cùng điều kiện cho hai chế độ

Giả sử mô hình `Ticket` có:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `tenantId` | `String` | Tenant sở hữu ticket. |
| `status` | `TicketStatus` | Ví dụ OPEN hoặc CLOSED. |
| `createdAt` | `Instant` | Thời điểm tạo. |

Mapping và cấu hình store được chuẩn bị riêng.

```java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    List<Ticket> findByTenantIdAndStatus(
        String tenantId,
        TicketStatus status,
        Pageable pageable
    );

    List<Ticket> findByTenantIdAndStatus(
        String tenantId,
        TicketStatus status,
        Sort sort
    );
}
```

Trên Commons từ 3.2, caller có thể dùng overload Pageable:

```java
Sort order = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<Ticket> tickets = repository.findByTenantIdAndStatus(
    "ACME",
    TicketStatus.OPEN,
    Pageable.unpaged(order)
);
```

Điều kiện vẫn là tenant ACME và trạng thái OPEN. Request yêu cầu thứ tự nhưng không đặt khoảng trang.

Khi muốn lấy một trang:

```java
import org.springframework.data.domain.PageRequest;

List<Ticket> firstPage = repository.findByTenantIdAndStatus(
    "ACME",
    TicketStatus.OPEN,
    PageRequest.of(0, 20, order)
);
```

Hai lời gọi khác chế độ lấy kết quả, không khác điều kiện lọc.

Cần xác minh module và đường query thực tế có áp dụng Sort trong chế độ unpaged đúng như hợp đồng. Việc tạo đối tượng Pageable thành công mới chứng minh metadata đã được biểu đạt.

## 5. Không đọc page number, page size hoặc offset của unpaged

Một điểm dễ gặp lỗi là code xử lý chung luôn gọi:

```java
request.getPageNumber();
request.getPageSize();
request.getOffset();
```

Đối với unpaged chuẩn, các API này ném `UnsupportedOperationException`. Chúng không trả 0, kích thước vô hạn hoặc một giá trị sentinel để caller tự diễn giải.

Các nhóm thao tác cần tách:

| Thao tác | Khi request là unpaged |
| --- | --- |
| `isPaged()`, `isUnpaged()` | Dùng để phân nhánh chế độ. |
| `getSort()` | Có thể đọc; unpaged vẫn có thể mang Sort. |
| `getPageNumber()` | Không có số trang để đọc theo hợp đồng này. |
| `getPageSize()` | Không có kích thước trang để đọc. |
| `getOffset()` | Không có offset trang để đọc. |

Triển khai tham chiếu có thể xem ở [Unpaged tại tag Commons 3.2.0](https://github.com/spring-projects/spring-data-commons/blob/3.2.0/src/main/java/org/springframework/data/domain/Unpaged.java).

Một helper chỉ đọc metadata có thể viết:

```java
import java.util.Objects;

import org.springframework.data.domain.Pageable;

static String describe(Pageable request) {
    Objects.requireNonNull(request, "request");

    String sort = request.getSort().toString();

    if (request.isUnpaged()) {
        return "unpaged; sort=" + sort;
    }

    return String.format(
        "page=%d; size=%d; offset=%d; sort=%s",
        request.getPageNumber(),
        request.getPageSize(),
        request.getOffset(),
        sort
    );
}
```

Nhánh unpaged được xử lý trước khi truy cập các thông tin trang. Nguyên tắc này cũng áp dụng cho logging, tracing và custom repository.

Không ép mọi Pageable thành `PageRequest`. Đối tượng trả từ `unpaged(...)` thực hiện cùng interface nhưng không phải một PageRequest có kích thước đặc biệt.

## 6. toOptional có thể làm mất Sort nếu dùng sai mục đích

`Pageable.toOptional()` trả Optional empty khi request là unpaged, kể cả khi unpaged mang Sort.

Vì vậy, đoạn sau có thể làm mất thứ tự:

```java
Sort extracted = request.toOptional()
    .map(Pageable::getSort)
    .orElse(Sort.unsorted());
```

Với `Pageable.unpaged(order)`, nhánh map không chạy và `extracted` trở thành unsorted.

Nếu chỉ cần đọc thứ tự, dùng:

```java
Sort extracted = request.getSort();
```

Nếu cần thứ tự dự phòng khi chưa có sort:

```java
Sort fallback = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Sort effective = request.getSortOr(fallback);
```

`getSortOr` chỉ trả một Sort phù hợp; nó không sửa request ban đầu. Muốn đưa thứ tự mới vào một yêu cầu unpaged trên API từ 3.2, tạo request tương ứng:

```java
Pageable effectiveRequest = Pageable.unpaged(effective);
```

Cách đọc đúng ở đây là:

```text
Optional empty: không có chế độ phân trang để biểu đạt qua phép chuyển này.
Không có nghĩa: đối tượng request không còn thông tin hữu ích nào khác.
```

Hành vi của `toOptional()` và các factory có trong [mã nguồn Pageable 3.2.0](https://github.com/spring-projects/spring-data-commons/blob/3.2.0/src/main/java/org/springframework/data/domain/Pageable.java).

## 7. Phiên bản chưa có unpaged(Sort): dùng hợp đồng Sort phù hợp

Nếu dự án dùng Commons 3.1.x, lời gọi:

```java
Pageable.unpaged(order);
```

không có overload tương ứng để biên dịch.

Với repository đã có dạng query method nhận riêng Sort, có thể viết:

```java
List<Ticket> tickets = repository.findByTenantIdAndStatus(
    "ACME",
    TicketStatus.OPEN,
    order
);
```

Đây là lời gọi không yêu cầu phân trang và có thứ tự, theo khả năng query method của module. Nó không cần mô phỏng một trang có kích thước rất lớn.

Hai overload trong repository ở phần trước có cùng điều kiện nghiệp vụ, nhưng một dạng nhận Pageable và một dạng nhận Sort. Không gộp chúng thành chữ ký:

```java
// Không hợp lệ như một query method của hạ tầng repository.
List<Ticket> findByTenantIdAndStatus(
    String tenantId,
    TicketStatus status,
    Pageable pageable,
    Sort sort
);
```

Pageable đã có thông tin Sort; tổ hợp Pageable và Sort riêng trong cùng query method là tổ hợp loại trừ. Quy tắc special parameter và dạng query nhận Sort được mô tả trong [Spring Data Commons — Paging, Sorting and Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters).

### Phân biệt lỗi biên dịch và lỗi runtime do dependency

| Biểu hiện | Hướng kiểm tra |
| --- | --- |
| IDE/compiler không tìm thấy unpaged(Sort) | Phiên bản Commons trên compile classpath có API này không. |
| Code đã build nhưng runtime báo NoSuchMethodError liên quan overload | Artifact Commons được nạp ở runtime có khớp API lúc build không. |
| Factory tạo được nhưng query không giữ thứ tự | Đường xử lý của module, phiên bản và query thực tế. |

Khi dùng dependency management hoặc BOM, cần giữ bộ phiên bản tương thích. Không xem việc chỉ thay một JAR Commons là cách nâng cấp toàn bộ khả năng của module store.

## 8. Một trang rất lớn vẫn là paged

Ví dụ:

```java
Pageable request = PageRequest.of(
    0,
    Integer.MAX_VALUE,
    order
);
```

Đối tượng trên vẫn có `isPaged() == true`. Nó có page number, page size và giới hạn hữu hạn được khai báo.

So sánh:

| Yêu cầu | Chế độ | Khoảng lấy |
| --- | --- | --- |
| `Pageable.unpaged()` | Unpaged. | Không có khoảng trang qua Pageable. |
| `Pageable.unpaged(order)` | Unpaged, có Sort. | Không có khoảng trang qua Pageable. |
| `PageRequest.of(0, 20, order)` | Paged. | Trang đầu, tối đa 20 phần tử. |
| `PageRequest.of(0, Integer.MAX_VALUE, order)` | Paged. | Một trang với kích thước hữu hạn rất lớn. |

Dùng page size rất lớn có thể tạo hành vi giới hạn và metadata khác với unpaged, đồng thời vẫn có thể làm ứng dụng tải nhiều dữ liệu.

Tương tự, `Pageable.ofSize(20)` tạo yêu cầu trang đầu có kích thước 20. Nó không phải một cách tạo unpaged.

## 9. Unpaged không xóa những giới hạn khác của query

Ví dụ một query method theo tên:

```java
List<Ticket> findTop100ByTenantIdOrderByCreatedAtDescIdDesc(
    String tenantId,
    Pageable pageable
);
```

Trong module hỗ trợ cấu trúc này, `Top100` đã biểu đạt giới hạn của query. Truyền `Pageable.unpaged()` không tự xóa giới hạn đó.

Tương tự, declared query hoặc API store có thể có giới hạn riêng. Cần đọc cả hợp đồng query, không chỉ trạng thái Pageable.

Cũng phân biệt:

- Unpaged không tham số không mang dynamic Sort.
- Thứ tự tĩnh trong query có thể vẫn được áp dụng.
- Không có khoảng trang không đồng nghĩa không có điều kiện lọc.
- Không có khoảng trang không tự bảo đảm kết quả chứa mọi bản ghi của toàn bộ database.

Nếu cần lấy tất cả phần tử khớp theo nghĩa nghiệp vụ, phải xác định rõ cả bộ lọc và những giới hạn còn lại.

## 10. Kiểu kết quả không tự bật lại phân trang

Một query method có thể trả List hoặc Page tùy hợp đồng được module hỗ trợ.

Với List và request unpaged, ứng dụng có thể nhận toàn bộ tập khớp nếu không có giới hạn khác. Điều đó có thể làm tăng lượng dữ liệu materialize trong bộ nhớ.

Với một query method trả `Page<Ticket>`, truyền unpaged không tự biến request thành một PageRequest có kích thước mặc định. Page là kiểu đóng gói kết quả; Pageable là yêu cầu điều khiển việc lấy kết quả.

Khi dùng Page, đọc metadata từ kết quả theo hợp đồng của Page. Không quay lại gọi `getPageSize()` trên request unpaged để tự tính tổng số trang.

Cũng không khẳng định mọi query trả Page với unpaged luôn phát cùng số câu lệnh đếm. Cách thực thi phụ thuộc module, query và phiên bản; quan sát query thực tế nếu chi phí này quan trọng.

Nếu use case chỉ cần một danh sách không phân trang, một hợp đồng List với Sort hoặc unpaged có Sort thường dễ đọc hơn việc tạo metadata phân trang không cần thiết.

## 11. Một factory chọn chế độ có thể giữ chính sách rõ ràng

Ví dụ sau dùng API từ Commons 3.2:

```java
import java.util.Objects;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

static Pageable createRequest(
    boolean paginationEnabled,
    int page,
    int size,
    Sort sort
) {
    Objects.requireNonNull(sort, "sort");

    if (!paginationEnabled) {
        return Pageable.unpaged(sort);
    }

    if (page < 0) {
        throw new IllegalArgumentException("page must be non-negative");
    }

    if (size < 1 || size > 200) {
        throw new IllegalArgumentException("size must be between 1 and 200");
    }

    return PageRequest.of(page, size, sort);
}
```

Hợp đồng của helper:

- Sort luôn được giữ trong cả hai chế độ.
- Page và size chỉ được dùng, kiểm tra khi bật phân trang.
- Giới hạn 200 là chính sách ví dụ của ứng dụng, không phải mặc định Commons.
- Chế độ unpaged không bị thay bằng một page size giả.

Nếu sản phẩm yêu cầu từ chối việc gửi page/size khi chọn unpaged, cần bổ sung chính sách validation đó ở ranh giới nhận yêu cầu. Hai cách đều cần được mô tả rõ; helper trên chọn bỏ qua hai số trong nhánh unpaged.

Không mặc định một tham số giao diện hoặc HTTP tên “unpaged” sẽ tự được mọi resolver chuyển thành request này. Việc cung cấp chế độ đó thuộc hợp đồng của ứng dụng.

## 12. Chọn unpaged theo quy mô và cách tiêu thụ dữ liệu

Một số use case phù hợp để cân nhắc:

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| Danh mục hoặc tập dữ liệu đã được giới hạn rõ bằng nghiệp vụ | Có thể dùng unpaged khi quy mô phù hợp. |
| Muốn không phân trang nhưng vẫn có thứ tự | unpaged(Sort) từ 3.2, hoặc query nhận riêng Sort khi thích hợp. |
| Tập dữ liệu lớn cần duyệt từng phần | Cân nhắc Slice, scrolling hoặc cơ chế đọc theo phần của module. |
| Cần xử lý streaming | Chọn API streaming được module hỗ trợ và quản lý tài nguyên. |
| Giao diện cần tổng số và điều hướng trang | Giữ một hợp đồng phân trang đáp ứng nhu cầu đó. |

Unpaged không tạo cursor, không tự chọn index và không bảo đảm mức bộ nhớ cố định. Store có thể phải sort một tập dữ liệu lớn trước khi ứng dụng nhận kết quả.

Khi cung cấp chức năng xuất dữ liệu, cần xác định phạm vi dữ liệu và cách tiêu thụ. Việc bỏ phân trang ở một query trả List có thể thay đổi mạnh lượng dữ liệu giữ trong một lần gọi.

## 13. Thực hành đối chiếu các yêu cầu

Giả sử dữ liệu cố định, thời điểm cùng ngày và múi giờ:

| id | tenantId | status | createdAt |
| --- | --- | --- | --- |
| 101 | ACME | OPEN | 10:00 |
| 102 | ACME | OPEN | 10:02 |
| 103 | ACME | CLOSED | 10:03 |
| 104 | OTHER | OPEN | 10:04 |
| 105 | ACME | OPEN | 10:02 |
| 106 | ACME | OPEN | 09:59 |

Dùng điều kiện tenant ACME, trạng thái OPEN, với:

```java
Sort order = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Kỳ vọng, khi module thực hiện đúng hợp đồng:

| Request | Nội dung kỳ vọng |
| --- | --- |
| `PageRequest.of(0, 2, order)` | ID 105, 102. |
| `PageRequest.of(1, 2, order)` | ID 101, 106. |
| `Pageable.unpaged(order)` | ID 105, 102, 101, 106. |
| `Pageable.unpaged()` | Cùng bốn ticket khớp; request không quyết định dynamic order. |

Ticket 103 và 104 vẫn bị loại trong chế độ unpaged vì các điều kiện nghiệp vụ không bị bỏ.

Thêm các kiểm tra về metadata và đường thực thi:

1. Cả hai biến thể unpaged có isPaged bằng false không?
2. Sort có còn đúng sau khi đi qua helper hoặc adapter không?
3. Có nơi nào đọc page size hoặc offset trước khi kiểm tra chế độ không?
4. Có logic dùng toOptional rồi vô tình làm mất Sort không?
5. API có tồn tại trên đúng phiên bản Commons được build và chạy không?
6. Query thực tế có bỏ giới hạn theo Pageable nhưng giữ đúng bộ lọc và thứ tự không?

Khi đổi phiên bản hoặc module store, kiểm chứng lại các phần này trên đúng cấu hình ứng dụng. Hợp đồng cần giữ là chế độ lấy kết quả, điều kiện nghiệp vụ và thứ tự đã công bố.
