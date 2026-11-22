# Phân trang, dữ liệu không tồn tại và chính sách lỗi

Trong Domain-Driven Design (DDD), **Repository** cung cấp một cách truy cập aggregate thông qua ngôn ngữ của miền nghiệp vụ. Repository giúp application làm việc với entity hoặc aggregate mà không cần biết dữ liệu được lưu trong SQL, document database hay một cơ chế persistence khác.

Khi hệ thống cần phân trang, tìm dữ liệu không tồn tại hoặc xử lý lỗi, hợp đồng repository phải thể hiện rõ ý nghĩa của từng kết quả. Một truy vấn không tìm thấy aggregate khác với một truy vấn danh sách không có phần tử. Một lỗi nghiệp vụ khác với lỗi kết nối database. Nếu trộn lẫn các trường hợp này, caller sẽ khó quyết định nên hiển thị “không tìm thấy”, trả danh sách rỗng, thử lại hay báo lỗi hệ thống.

Bài này trình bày cách thiết kế hợp đồng repository cho truy vấn và tải aggregate, cách chọn offset pagination hoặc keyset pagination, cách biểu diễn dữ liệu vắng mặt và cách phân loại lỗi qua các lớp domain, application và infrastructure.

## 1. Repository trong DDD và trách nhiệm của nó

Repository tạo ra một giao diện truy cập aggregate giống như một tập hợp các đối tượng trong bộ nhớ. Application có thể yêu cầu tải một aggregate theo định danh, lưu thay đổi hoặc tìm các aggregate thỏa một điều kiện nghiệp vụ. Adapter phía ngoài thực hiện các thao tác đó bằng database hoặc công nghệ lưu trữ cụ thể.

Một hợp đồng đơn giản:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Interface này nói rằng application có thể tìm một đơn hàng theo `OrderId` và lưu một aggregate `Order`. Nó không tiết lộ SQL, bảng, ORM hoặc kiểu dữ liệu của database.

### 1.1. Repository không phải là nơi chứa mọi truy vấn

Repository theo nghĩa DDD thường tập trung vào aggregate root. Mục tiêu là tải và lưu aggregate để thực hiện hành vi nghiệp vụ, đồng thời giữ invariant của aggregate.

Không nên biến một repository thành một lớp truy vấn tổng quát cho mọi màn hình, báo cáo và thống kê. Những truy vấn đọc phức tạp có thể cần projection, join nhiều bảng hoặc dữ liệu tổng hợp không tương ứng với aggregate. Chúng có thể được phục vụ bởi query service hoặc read adapter riêng.

Ví dụ:

- `OrderRepository.findById(orderId)` tải một aggregate để hủy hoặc xác nhận đơn.
- `OrderQueryService.searchOrders(criteria, page)` trả danh sách dòng hiển thị cho màn hình quản trị.
- `SalesReportQuery` trả dữ liệu tổng hợp doanh thu theo tháng.

Ba nhu cầu này có thể dùng chung database nhưng có hợp đồng và mục đích khác nhau. Không cần buộc truy vấn báo cáo phải tải hàng nghìn aggregate chỉ để lấy vài cột hiển thị.

### 1.2. Repository interface nên thuộc phía trong

Application hoặc domain định nghĩa abstraction phù hợp với nhu cầu. Infrastructure triển khai abstraction bằng JPA, JDBC, MongoDB hoặc công nghệ khác.

```text
Application / Domain
        |
        v
  OrderRepository (port)
        ^
        |
JpaOrderRepositoryAdapter
        |
        v
     Database
```

Không để interface phía trong trả về `JpaRepository`, `EntityManager`, `Page<OrderJpaEntity>`, `ResultSet` hoặc kiểu riêng của driver. Những kiểu đó khiến application phụ thuộc vào công nghệ lưu trữ.

## 2. Phân biệt truy vấn một aggregate và truy vấn tập hợp

Hợp đồng repository nên thể hiện rõ caller đang yêu cầu một aggregate cụ thể hay một tập kết quả.

| Nhu cầu | Kết quả phù hợp | Ý nghĩa khi không có dữ liệu |
|---|---|---|
| Tìm đơn theo ID, có thể không tồn tại | `Optional<Order>` | `Optional.empty()` |
| Tải đơn bắt buộc để thực hiện use case | Có thể dùng `Optional` ở repository, application quyết định lỗi | Application trả kết quả not found phù hợp |
| Tìm các đơn thỏa điều kiện | `List<OrderSummary>` hoặc kiểu trang kết quả | Danh sách rỗng |
| Tìm đơn đầu tiên theo tiêu chí có thể không có | `Optional<Order>` hoặc projection tương ứng | `Optional.empty()` |
| Đếm số đơn thỏa điều kiện | `long` hoặc kiểu đếm phù hợp | `0` |

Không nên dùng `null` để biểu diễn dữ liệu không tồn tại. `Optional` làm cho khả năng không có kết quả trở nên rõ ràng trong chữ ký Java.

### 2.1. `findById` và `getRequired` có ý nghĩa khác nhau

`findById` diễn đạt rằng aggregate có thể không tồn tại:

```java
Optional<Order> findById(OrderId id);
```

Caller phải xử lý cả hai trường hợp. Với use case cần có đơn hàng, application có thể chuyển kết quả vắng mặt thành lỗi nghiệp vụ hoặc application error:

```java
Order order = orderRepository.findById(id)
    .orElseThrow(() -> new OrderNotFoundException(id));
```

Có thể tạo một helper `getRequiredById` ở application service hoặc một abstraction có ngữ nghĩa rõ. Tuy nhiên, cần cân nhắc nơi sở hữu loại lỗi. Repository thường chỉ báo dữ liệu có tồn tại hay không; application biết việc thiếu aggregate có làm use case thất bại hay không.

Ví dụ, “xem thông tin đơn hàng” có thể trả not found nếu ID không có. Một tác vụ đồng bộ có thể coi việc thiếu một aggregate là điều bình thường và bỏ qua. Một quy trình bắt buộc phải có đơn có thể chuyển nó thành `OrderNotFoundException`.

### 2.2. Danh sách rỗng không phải lỗi not found

Một truy vấn danh sách hợp lệ có thể không tìm thấy phần tử nào:

```java
List<OrderSummary> search(OrderCriteria criteria);
```

Nếu không có đơn phù hợp, trả `List.of()` thay vì `null` hoặc ném `OrderNotFoundException`. Danh sách rỗng là một kết quả bình thường của truy vấn tập hợp.

Phân biệt này rất quan trọng với API:

- `GET /orders/ORD-100` có thể trả `404 Not Found` nếu đơn không tồn tại hoặc người gọi không được phép biết nó tồn tại.
- `GET /orders?status=OPEN` thường trả `200 OK` cùng danh sách rỗng nếu không có đơn đang mở.

Không nên trả 404 chỉ vì một trang danh sách không có phần tử. Tài nguyên danh sách tồn tại; tập kết quả của điều kiện tìm kiếm chỉ tình cờ rỗng.

## 3. Phân trang giải quyết vấn đề gì?

Khi số lượng bản ghi lớn, tải toàn bộ dữ liệu về bộ nhớ và trả trong một response gây tốn bộ nhớ, băng thông, thời gian truy vấn và thời gian render. Pagination chia kết quả thành các phần nhỏ để caller lấy dần.

Các mục tiêu thường gặp:

- Giới hạn số phần tử được tải và truyền trong một lần.
- Giữ thời gian phản hồi ổn định hơn khi dữ liệu tăng.
- Cho phép người dùng duyệt dữ liệu theo trang hoặc cuộn liên tục.
- Hạn chế việc aggregate hoặc entity lớn bị nạp không cần thiết.
- Kiểm soát tải database và API.

Phân trang cần có thứ tự xác định. Nếu database không có `ORDER BY`, thứ tự dòng không được bảo đảm. Khi các bản ghi có cùng giá trị sắp xếp, cần thêm một khóa phụ duy nhất để tạo thứ tự ổn định.

## 4. Offset pagination

Offset pagination dùng số lượng bản ghi cần bỏ qua và số lượng cần lấy. Đây là cách phổ biến cho giao diện có nút trang trước/sau và cho phép nhảy đến một trang cụ thể.

Ví dụ SQL:

```sql
SELECT id, order_number, status, created_at
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, id DESC
LIMIT :page_size OFFSET :offset;
```

Nếu `page=3`, `pageSize=20` và đánh số trang từ 0, offset là:

\[
offset = page \times pageSize = 3 \times 20 = 60
\]

Database bỏ qua 60 dòng đầu theo thứ tự đã sắp xếp và trả tối đa 20 dòng tiếp theo.

### 4.1. Ưu điểm và hạn chế

**Ưu điểm:**

- Dễ hiểu và dễ triển khai.
- Hỗ trợ nhảy trực tiếp đến trang bất kỳ.
- Phù hợp với danh sách có số trang và tổng số phần tử.
- Được hỗ trợ rộng rãi bởi các database và thư viện persistence.

**Hạn chế:**

- Offset lớn có thể khiến database phải duyệt và bỏ qua nhiều dòng trước khi trả kết quả.
- Khi dữ liệu được thêm hoặc xóa giữa các lần đọc, phần tử có thể dịch chuyển giữa các trang.
- Tổng số bản ghi (`COUNT(*)`) có thể tốn chi phí trên tập dữ liệu lớn.
- Trang càng sâu có thể càng chậm, tùy database, index và query plan.

### 4.2. Dữ liệu thay đổi giữa các trang

Giả sử trang đầu trả các đơn A, B, C và trang thứ hai dự kiến trả D, E, F. Sau khi người dùng tải trang đầu, một bản ghi mới X được thêm lên đầu danh sách. Khi request trang hai dùng `OFFSET 3`, kết quả có thể chứa C lần nữa vì các vị trí đã dịch chuyển.

Ngược lại, nếu một bản ghi trước offset bị xóa, một bản ghi phía sau có thể bị bỏ qua. Đây là đặc tính của phân trang theo vị trí trên một tập dữ liệu đang thay đổi.

Nếu cần một tập dữ liệu nhất quán qua nhiều trang, cần xác định yêu cầu snapshot hoặc thời điểm truy vấn. Một transaction snapshot không phải lúc nào cũng phù hợp để giữ mở trong suốt thời gian người dùng duyệt trang. Với nhiều use case, keyset pagination hoặc một snapshot/version token là lựa chọn tốt hơn.

### 4.3. Thiết kế page request

Application có thể định nghĩa kiểu độc lập framework:

```java
public record PageRequest(int page, int size, OrderSort sort) {
    public PageRequest {
        if (page < 0) {
            throw new IllegalArgumentException("Page must not be negative");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("Page size must be between 1 and 100");
        }
    }
}
```

Giới hạn `size` giúp ngăn caller yêu cầu một trang quá lớn. Giá trị tối đa cần được chọn theo hiệu năng và nhu cầu sản phẩm, không nhất thiết là 100 trong mọi hệ thống.

Không truyền trực tiếp `Pageable` hoặc `Sort` của Spring Data vào domain/application nếu muốn giữ độc lập framework. Adapter có thể chuyển `PageRequest` nội bộ thành `Pageable` khi thực thi truy vấn.

### 4.4. Kết quả trang

Có thể định nghĩa kiểu kết quả của application:

```java
public record PageResult<T>(
    List<T> items,
    int page,
    int size,
    long totalElements,
    int totalPages
) {}
```

Nếu cần tổng số bản ghi, adapter có thể chạy thêm câu `COUNT`. Với tập dữ liệu lớn, count chính xác có thể tốn kém; hãy xác định giao diện có thực sự cần tổng số trang hay chỉ cần biết còn dữ liệu tiếp theo.

Đừng để `PageResult` mang theo entity JPA. Với màn hình tìm kiếm, `T` thường nên là projection hoặc DTO đọc như `OrderSummary`, chỉ chứa các field cần hiển thị.

## 5. Keyset pagination (seek pagination)

Keyset pagination lấy trang tiếp theo dựa trên giá trị của phần tử cuối cùng ở trang trước, thay vì bỏ qua một số lượng dòng. Nó phù hợp với danh sách lớn, duyệt tuần tự hoặc feed có dữ liệu thay đổi thường xuyên.

Giả sử kết quả được sắp xếp theo `created_at DESC, id DESC`. Trang tiếp theo dùng cặp `(created_at, id)` của phần tử cuối cùng làm cursor:

```sql
SELECT id, order_number, status, created_at
FROM orders
WHERE customer_id = :customer_id
  AND (
      created_at < :last_created_at
      OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
```

Ứng dụng lấy `pageSize + 1` dòng để biết có phần tử tiếp theo hay không. Nếu có thêm một dòng, bỏ dòng phụ và trả `hasNext=true` cùng cursor mới từ phần tử cuối thực sự được trả.

### 5.1. Vì sao cần khóa phụ duy nhất?

Nếu chỉ sắp xếp theo `created_at`, nhiều đơn có thể có cùng thời điểm tạo. Cursor chỉ chứa timestamp sẽ không xác định chính xác điểm tiếp tục, dẫn đến bỏ sót hoặc lặp bản ghi.

Thêm `id` duy nhất vào `ORDER BY` tạo ra thứ tự toàn phần. Điều kiện seek phải phản ánh đúng thứ tự và chiều sắp xếp của tất cả field.

### 5.2. Ưu điểm và hạn chế

**Ưu điểm:**

- Hiệu quả hơn ở các trang sâu khi có index phù hợp.
- Không phải duyệt và bỏ qua toàn bộ các dòng trước đó.
- Ít bị dịch chuyển phần tử do insert mới ở đầu danh sách.
- Phù hợp với infinite scroll, event feed và lịch sử giao dịch.

**Hạn chế:**

- Không hỗ trợ nhảy đến trang bất kỳ một cách tự nhiên.
- Cần một thứ tự sắp xếp ổn định và cursor chứa đủ giá trị sort.
- Query phức tạp hơn khi có nhiều field sort, điều kiện null hoặc chiều sort hỗn hợp.
- Nếu field sort có thể thay đổi trong lúc duyệt, phần tử có thể di chuyển qua ranh giới cursor.

Keyset pagination giảm các vấn đề do offset nhưng không tự tạo snapshot nhất quán tuyệt đối. Nếu một bản ghi đã đọc bị cập nhật `created_at` hoặc sort key và chuyển vị trí, kết quả vẫn có thể khác giữa các lần gọi. Thường nên chọn sort key bất biến như thời điểm tạo cộng ID, hoặc dùng snapshot/version khi nghiệp vụ đòi hỏi.

### 5.3. Cursor nên là chi tiết của query contract

API có thể nhận `cursor` và `limit`, rồi trả `nextCursor`. Cursor có thể mã hóa các giá trị sort và filter cần thiết. Nên xem cursor là token opaque đối với client: client gửi lại nguyên vẹn nhưng không tự chỉnh sửa các giá trị bên trong.

Một cursor có thể chứa:

- Giá trị của các cột sắp xếp cuối cùng.
- Phiên bản định dạng cursor.
- Các filter hoặc tenant scope cần ràng buộc.
- Thời điểm snapshot nếu hệ thống hỗ trợ.
- Chữ ký hoặc MAC để phát hiện token bị sửa đổi.

Không đưa thông tin bí mật vào cursor nếu token chỉ được Base64 encode; Base64 không phải mã hóa. Nếu cursor có dữ liệu nhạy cảm, cần mã hóa hoặc chỉ dùng một token ngẫu nhiên trỏ đến trạng thái lưu phía server.

### 5.4. Khi nào chọn offset và khi nào chọn keyset?

| Nhu cầu | Gợi ý |
|---|---|
| Trang quản trị cần nhảy đến trang 12 | Offset pagination |
| Danh sách nhỏ, có tổng số trang | Offset pagination |
| Lịch sử giao dịch lớn, cuộn liên tục | Keyset pagination |
| Feed có dữ liệu mới được thêm liên tục | Keyset pagination với sort key ổn định |
| Cần duyệt snapshot cố định qua nhiều request | Snapshot/version token hoặc chiến lược snapshot phù hợp |
| Truy vấn báo cáo tổng hợp | Query/reporting model, có thể không dùng repository aggregate |

Không có lựa chọn đúng cho mọi endpoint. Hãy dựa vào cách người dùng duyệt, kích thước dữ liệu, tần suất thay đổi và khả năng của database.

## 6. Hợp đồng phân trang trong application

Hợp đồng application nên biểu đạt yêu cầu nghiệp vụ hoặc truy vấn ứng dụng, không để lộ API riêng của ORM.

Ví dụ một query service:

```java
public record OrderSearchCriteria(
    CustomerId customerId,
    OrderStatus status,
    Instant createdFrom,
    Instant createdTo
) {}

public interface SearchOrdersQuery {
    PageResult<OrderSummary> execute(
        OrderSearchCriteria criteria,
        PageRequest pageRequest
    );
}
```

`OrderSummary` có thể là read model chỉ chứa ID, mã đơn, trạng thái, thời gian và tổng tiền. Query service không cần tải toàn bộ aggregate `Order` nếu không thực hiện hành vi miền.

Với keyset pagination, có thể định nghĩa hợp đồng riêng:

```java
public record CursorPageRequest(String cursor, int limit) {}

public record CursorPage<T>(
    List<T> items,
    String nextCursor,
    boolean hasNext
) {}

public interface SearchOrderFeed {
    CursorPage<OrderSummary> execute(
        OrderSearchCriteria criteria,
        CursorPageRequest request
    );
}
```

Đừng thiết kế một kiểu phân trang quá tổng quát nếu mỗi use case có semantics khác nhau. Offset và cursor có những điều kiện và bảo đảm khác nhau; thể hiện rõ chúng trong hợp đồng giúp caller không hiểu nhầm.

### 6.1. Sắp xếp và filter phải được kiểm soát

Không nối trực tiếp tên cột hoặc hướng sắp xếp từ query string vào SQL. Adapter nên ánh xạ các lựa chọn được cho phép sang biểu thức query đã định nghĩa.

Ví dụ client có thể yêu cầu `createdAt` hoặc `orderNumber`; adapter dùng whitelist:

```java
SortExpression toSortExpression(OrderSort sort) {
    return switch (sort.field()) {
        case CREATED_AT -> SortExpression.createdAt(sort.direction());
        case ORDER_NUMBER -> SortExpression.orderNumber(sort.direction());
    };
}
```

Nếu filter có phạm vi tenant hoặc customer, adapter phải áp dụng điều kiện scope ở phía server dựa trên danh tính đã xác thực. Không tin một `customerId` do client gửi mà không kiểm tra quyền truy cập.

## 7. Repository trả về dữ liệu không tồn tại như thế nào?

Một aggregate có thể không tồn tại vì ID sai, đã bị xóa, chưa được tạo hoặc caller không được phép truy cập. Hợp đồng repository cần biểu diễn khả năng đó một cách rõ ràng.

### 7.1. Dùng Optional cho truy vấn có thể không có kết quả

```java
Optional<Customer> findById(CustomerId id);
```

Adapter trả `Optional.empty()` nếu không có aggregate phù hợp. Nó không nên tự ném `CustomerNotFoundException` cho mọi truy vấn, bởi vì ý nghĩa của việc không tìm thấy phụ thuộc use case.

### 7.2. Application quyết định dữ liệu vắng mặt có phải lỗi không

Ví dụ use case bắt buộc có đơn:

```java
public final class CancelOrderService {
    private final OrderRepository orders;

    public void cancel(OrderId id) {
        Order order = orders.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        order.cancel();
        orders.save(order);
    }
}
```

Ví dụ truy vấn tùy chọn:

```java
public Optional<OrderSummary> findLatestOrder(CustomerId customerId) {
    return orderQueries.findLatestFor(customerId);
}
```

Use case thứ nhất cần đơn để thực hiện hành vi nên chuyển `empty` thành lỗi not found. Use case thứ hai có thể xem việc khách hàng chưa từng đặt đơn là một kết quả bình thường.

### 7.3. Không dùng exception cho kết quả rỗng bình thường

Nếu danh sách không có kết quả là một trường hợp thường gặp, hãy trả danh sách rỗng hoặc trang rỗng. Dùng exception cho trạng thái khiến use case không thể tiếp tục theo hợp đồng, chẳng hạn aggregate bắt buộc không tồn tại hoặc một invariant bị vi phạm.

Tránh:

```java
if (orders.isEmpty()) {
    throw new OrderNotFoundException();
}
```

đối với một truy vấn tìm kiếm nhiều đơn. Một danh sách rỗng không có nghĩa là có một đơn hàng cụ thể bị thiếu.

## 8. Chính sách lỗi qua các lớp

Không phải mọi lỗi đều có cùng ý nghĩa. Phân loại đúng giúp application và adapter xử lý phù hợp.

| Nhóm lỗi | Ví dụ | Nơi phát sinh/nhận diện | Cách xử lý thường gặp |
|---|---|---|---|
| Validation đầu vào | Page âm, limit vượt giới hạn, cursor sai định dạng | Inbound adapter hoặc application boundary | Trả lỗi đầu vào rõ ràng |
| Dữ liệu không tồn tại | Aggregate theo ID không có | Repository trả `Optional.empty()`; application diễn giải | Not found hoặc kết quả rỗng tùy use case |
| Vi phạm quy tắc miền | Đơn đã giao không thể hủy | Domain model | Giữ trạng thái, trả domain error phù hợp |
| Xung đột trạng thái | Version đã thay đổi, unique constraint bị vi phạm | Persistence adapter/application | Conflict hoặc thử lại có kiểm soát nếu an toàn |
| Lỗi hạ tầng tạm thời | Timeout, connection reset, database unavailable | Infrastructure | Retry có giới hạn nếu thao tác an toàn; nếu không thì báo lỗi dịch vụ |
| Lỗi lập trình hoặc cấu hình | Null không mong muốn, mapping sai, SQL lỗi | Bất kỳ lớp nào | Ghi log/alert, xử lý như lỗi hệ thống; không che giấu |

### 8.1. Domain exception

Domain exception biểu đạt một hành động không hợp lệ theo quy tắc miền, ví dụ:

```java
public final class OrderCannotBeCancelledException extends RuntimeException {
    public OrderCannotBeCancelledException(OrderId id) {
        super("Order cannot be cancelled: " + id.value());
    }
}
```

Domain exception không nên phụ thuộc `ResponseStatusException`, `HttpStatus` hoặc một framework web. Một adapter HTTP có thể ánh xạ exception sang HTTP 409; một consumer có thể chuyển thành kết quả từ chối nghiệp vụ.

### 8.2. Application error

Application có thể định nghĩa lỗi use case như `OrderNotFoundException` hoặc `CustomerNotAuthorizedException`. Những lỗi này thể hiện ca sử dụng không thể hoàn thành theo yêu cầu. Tùy thiết kế, chúng có thể là application exception hoặc kiểu kết quả có phân biệt thành công/thất bại.

Nếu dùng `Result`/`Either` thay exception, hãy làm cho các trường hợp lỗi được liệt kê rõ và tránh tạo một kiểu kết quả tổng quát chứa chuỗi lỗi tùy ý. Chọn cách nhất quán theo codebase và mức độ dự kiến của lỗi.

### 8.3. Persistence exception

Database có thể trả các lỗi như:

- Unique constraint violation.
- Foreign key violation.
- Deadlock hoặc lock timeout.
- Optimistic locking failure.
- Connection timeout hoặc transaction rollback.

Adapter có thể chuyển một số lỗi đã hiểu rõ thành lỗi application/domain có ý nghĩa. Ví dụ, vi phạm unique constraint trên mã đơn có thể trở thành `DuplicateOrderNumberException` nếu đó là một điều kiện nghiệp vụ dự kiến.

Không nên chuyển mọi `DataAccessException` thành “dữ liệu không hợp lệ”. Lỗi kết nối database hoặc SQL sai là lỗi hạ tầng/lập trình, không phải lỗi do người dùng nhập sai. Giữ nguyên nguyên nhân kỹ thuật trong log và telemetry để có thể điều tra.

### 8.4. Không nuốt lỗi

Các pattern nguy hiểm:

```java
try {
    return repository.findById(id).orElse(null);
} catch (Exception ignored) {
    return null;
}
```

Đoạn mã này biến lỗi database, lỗi mapping và lỗi lập trình thành một giá trị “không tồn tại”. Caller không thể biết hệ thống không có dữ liệu hay không thể truy cập dữ liệu.

Hãy bắt đúng loại lỗi mà lớp hiện tại có thể xử lý. Nếu không thể xử lý, truyền lỗi lên boundary phù hợp sau khi bổ sung ngữ cảnh và log theo chính sách. Không log rồi tiếp tục trả kết quả thành công giả.

## 9. Ánh xạ lỗi ra API và giao diện

HTTP adapter chịu trách nhiệm chuyển lỗi ứng dụng/miền thành giao thức HTTP. Một chính sách tham khảo:

| Lỗi phía trong | HTTP response thường dùng | Ghi chú |
|---|---|---|
| Aggregate không tồn tại | `404 Not Found` | Có thể dùng 404 để tránh tiết lộ tài nguyên không được phép xem |
| Dữ liệu đầu vào sai định dạng | `400 Bad Request` hoặc `422 Unprocessable Content` | Chọn nhất quán theo hợp đồng API |
| Vi phạm trạng thái nghiệp vụ | `409 Conflict` | Ví dụ đơn đã giao không thể hủy |
| Không được phép | `403 Forbidden` hoặc `404` theo chính sách bảo mật | Không để lộ sự tồn tại của tài nguyên nếu cần che giấu |
| Lỗi phụ thuộc tạm thời | `503 Service Unavailable` | Có thể kèm `Retry-After` nếu biết thời gian phù hợp |
| Lỗi không dự kiến | `500 Internal Server Error` | Không gửi stack trace hoặc chi tiết nội bộ cho client |

Đây là hướng dẫn tham khảo, không phải ánh xạ cứng cho mọi API. Hợp đồng public cần xác định mã lỗi, payload và khả năng retry rõ ràng.

Ví dụ exception handler:

```java
@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("ORDER_NOT_FOUND", "Order was not found"));
    }

    @ExceptionHandler(OrderCannotBeCancelledException.class)
    ResponseEntity<ApiError> handleConflict(OrderCannotBeCancelledException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("ORDER_CANNOT_BE_CANCELLED", ex.getMessage()));
    }
}

public record ApiError(String code, String message) {}
```

Trong API thực tế, cần cân nhắc việc trả thông điệp lỗi có tiết lộ dữ liệu nhạy cảm hay không. Có thể ghi chi tiết vào log nội bộ nhưng chỉ trả mã và thông điệp an toàn cho client.

## 10. Các trường hợp biên cần xác định rõ

### 10.1. Trang vượt quá số trang cuối

Nếu client yêu cầu page 99 nhưng chỉ có 3 trang, có một số chính sách hợp lệ:

- Trả trang rỗng với metadata page 99 và totalPages 3.
- Trả lỗi page out of range.
- Chuẩn hóa về trang cuối, nếu sản phẩm yêu cầu.

Không có một lựa chọn duy nhất cho mọi sản phẩm. API cần quy định rõ. Với giao diện tìm kiếm, trả trang rỗng thường đơn giản; với quy trình yêu cầu trang phải tồn tại, có thể trả lỗi validation. Không nên âm thầm chuyển sang trang đầu vì client có thể hiểu sai dữ liệu.

### 10.2. Page size bằng 0 hoặc quá lớn

Page size bằng 0 thường không có ý nghĩa và có thể tạo hành vi bất thường. Page size quá lớn gây áp lực lên database và bộ nhớ. Hãy đặt minimum/maximum rõ ràng, trả lỗi đầu vào khi không hợp lệ và có default hợp lý ở adapter.

### 10.3. Filter không có kết quả

Filter hợp lệ nhưng không khớp dữ liệu nên trả kết quả rỗng. Không chuyển thành `NotFoundException` trừ khi hợp đồng đang tìm một aggregate bắt buộc cụ thể.

### 10.4. Aggregate bị xóa giữa lúc tìm và lúc thao tác

Một use case có thể tìm thấy aggregate, nhưng aggregate bị xóa hoặc thay đổi trước khi cập nhật. Đây là race condition. Cần cơ chế version, transaction hoặc constraint phù hợp. Không nên giả định `findById()` thành công nghĩa là aggregate chắc chắn còn tồn tại tại thời điểm commit.

### 10.5. Soft delete và quyền truy cập

Nếu hệ thống dùng soft delete, cần thống nhất repository mặc định có loại bản ghi đã xóa khỏi kết quả hay không. Có thể có phương thức riêng để truy vấn lịch sử hoặc phục hồi. Tương tự, tenant scope và quyền truy cập phải được áp dụng nhất quán ở query boundary; tránh trả “không tồn tại” theo cách khác nhau khiến người dùng suy ra tài nguyên của tenant khác.

## 11. Tối ưu phân trang và truy vấn repository

### 11.1. Index theo filter và sort

Query pagination cần index phù hợp với điều kiện lọc và thứ tự sắp xếp. Ví dụ:

```sql
CREATE INDEX ix_orders_customer_created_id
ON orders (customer_id, created_at DESC, id DESC);
```

Index cụ thể phụ thuộc database và query plan. Không nên tạo index cho mọi tổ hợp filter; index cũng làm tăng chi phí ghi và lưu trữ. Hãy xem execution plan, số lượng dữ liệu và mẫu truy vấn thực tế.

### 11.2. Tránh N+1 query

Nếu query trả 20 dòng order summary rồi mỗi dòng lại tải customer riêng, hệ thống có thể phát sinh 21 query. Với read model, cân nhắc projection, join có kiểm soát hoặc batch fetch. Không tải toàn bộ graph aggregate chỉ để hiển thị vài field.

### 11.3. Count query có thể đắt

`Page<T>` thường cần tổng số bản ghi để tính `totalPages`. Trên bảng lớn với filter phức tạp, count có thể đắt ngang hoặc hơn query lấy dữ liệu. Nếu giao diện chỉ cần biết có trang tiếp theo, dùng `Slice`/`hasNext` hoặc keyset cursor có thể hiệu quả hơn. Không cần trả `totalElements` nếu sản phẩm không sử dụng nó.

### 11.4. Không phân trang bên trong bộ nhớ khi database có thể làm

Tránh tải hàng trăm nghìn aggregate rồi dùng `stream().skip(offset).limit(size)`. Hãy đẩy filter, sort và limit xuống database hoặc search engine phù hợp. In-memory pagination chỉ phù hợp với tập dữ liệu nhỏ đã có sẵn trong bộ nhớ hoặc trường hợp đặc biệt có lý do rõ.

## 12. Ví dụ thiết kế hoàn chỉnh

Giả sử màn hình quản trị cần tìm đơn hàng theo trạng thái và thời gian, đồng thời use case hủy đơn cần tải một aggregate theo ID.

### 12.1. Hợp đồng repository cho aggregate

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

### 12.2. Hợp đồng query riêng cho màn hình

```java
public interface OrderSearchQuery {
    PageResult<OrderSummary> search(
        OrderSearchCriteria criteria,
        PageRequest pageRequest
    );
}
```

### 12.3. Application service cho use case bắt buộc có đơn

```java
public final class CancelOrderService {
    private final OrderRepository orders;

    public CancelOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void execute(OrderId id) {
        Order order = orders.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        order.cancel();
        orders.save(order);
    }
}
```

### 12.4. Query adapter thực hiện pagination

Infrastructure có thể dùng Spring Data/JPA để thực thi query, sau đó map kết quả về kiểu application:

```java
Page<OrderSummary> result = springDataRepository.search(
    criteria.status(),
    criteria.createdFrom(),
    criteria.createdTo(),
    pageable
);

return new PageResult<>(
    result.getContent(),
    result.getNumber(),
    result.getSize(),
    result.getTotalElements(),
    result.getTotalPages()
);
```

`Page` và `Pageable` chỉ xuất hiện trong adapter. Application nhận `PageResult` không phụ thuộc Spring. Nếu query dùng projection, adapter map projection thành `OrderSummary` trước khi trả kết quả.

## 13. Kiểm thử hợp đồng và chính sách lỗi

Repository và query adapter cần được kiểm thử bằng database phù hợp để xác nhận hành vi thực tế, đặc biệt với sort, cursor, transaction và constraint.

Các trường hợp nên có:

- Tìm ID có dữ liệu trả aggregate đúng.
- Tìm ID không có dữ liệu trả `Optional.empty()`.
- Truy vấn danh sách không có kết quả trả collection/trang rỗng.
- Trang đầu, trang giữa, trang cuối và trang vượt phạm vi tuân theo chính sách đã chọn.
- Sort có giá trị trùng nhau vẫn có tie-breaker ổn định.
- Keyset cursor không lặp hoặc bỏ sót trong dữ liệu tĩnh.
- Cursor không hợp lệ hoặc đã hết hạn bị từ chối rõ ràng.
- Tenant filter không trả dữ liệu của tenant khác.
- Query projection không tạo N+1 ngoài dự kiến.
- Database timeout không bị chuyển nhầm thành not found.
- Optimistic lock conflict được chuyển thành kết quả xung đột phù hợp.

Unit test application có thể dùng fake repository để kiểm tra use case diễn giải `Optional.empty()` đúng. Integration test adapter kiểm tra cách database thực hiện truy vấn và trả lỗi. Không dùng mock để chứng minh rằng SQL pagination hoặc isolation hoạt động đúng trên database thật.

## 14. Sai lầm thường gặp

**Trả `null` khi không tìm thấy.** Caller phải đoán ý nghĩa và dễ phát sinh `NullPointerException`. Dùng `Optional` cho một kết quả đơn có thể vắng mặt.

**Ném not found khi danh sách rỗng.** Một truy vấn tập hợp không có kết quả là bình thường. Trả collection hoặc page rỗng.

**Để repository quyết định mọi chính sách lỗi.** Repository không biết việc thiếu aggregate có phải lỗi của use case hay không. Hãy để application diễn giải theo mục đích gọi.

**Trả kiểu ORM ra khỏi adapter.** `Page<Entity>` hoặc `Pageable` làm application phụ thuộc Spring Data. Dùng kiểu hợp đồng riêng.

**Phân trang không có thứ tự ổn định.** Không có `ORDER BY` hoặc thiếu tie-breaker có thể gây lặp/bỏ sót ngay cả khi dữ liệu không thay đổi.

**Dùng offset sâu cho feed lớn.** Database có thể phải bỏ qua nhiều dòng. Cân nhắc keyset pagination.

**Tin cursor từ client.** Cursor có thể bị sửa để truy cập phạm vi khác hoặc làm query sai. Kiểm tra, ký hoặc lưu trạng thái cursor phù hợp.

**Bắt mọi exception rồi trả danh sách rỗng.** Lỗi hạ tầng bị ngụy trang thành “không có dữ liệu”, khiến sự cố khó phát hiện.

**Trả stack trace cho API caller.** Chi tiết nội bộ có thể tiết lộ thông tin nhạy cảm. Trả mã lỗi ổn định, log chi tiết ở server.

**Tải toàn bộ aggregate chỉ để hiển thị.** Query/read model nên chỉ lấy field cần thiết, tránh N+1 và tải graph không cần thiết.

## 15. Checklist thiết kế

Trước khi hoàn tất hợp đồng repository hoặc query, hãy kiểm tra:

- Repository đang quản lý aggregate root hay bị biến thành lớp truy vấn mọi thứ?
- Interface phía trong có tránh kiểu ORM/database/framework không?
- Truy vấn một aggregate có thể không tồn tại đã dùng `Optional` hoặc kết quả rõ ràng chưa?
- Truy vấn danh sách không có kết quả có trả collection/trang rỗng không?
- Application có quyết định việc thiếu aggregate có phải lỗi theo use case không?
- Pagination có giới hạn page size và thứ tự ổn định không?
- Offset có phù hợp với nhu cầu nhảy trang và quy mô dữ liệu không?
- Keyset có cursor đủ sort key và tie-breaker duy nhất không?
- Filter, sort và tenant scope có được kiểm soát ở phía server không?
- Count query có thực sự cần thiết không?
- Lỗi domain, application và infrastructure có được phân loại riêng không?
- Adapter có tránh nuốt lỗi hoặc biến lỗi database thành not found không?
- API có ánh xạ lỗi nhất quán và không lộ thông tin nội bộ không?
- Integration test đã kiểm tra pagination và lỗi trên database tương ứng chưa?

## 16. Câu hỏi tự kiểm tra

1. Vì sao repository trong DDD thường tập trung vào aggregate root?
2. Phân biệt `Optional.empty()` từ `findById` với một danh sách tìm kiếm rỗng.
3. Tại sao application layer thường là nơi quyết định dữ liệu không tồn tại có làm use case thất bại hay không?
4. Offset pagination có ưu điểm và hạn chế gì khi dữ liệu thay đổi giữa các request?
5. Vì sao keyset pagination cần sort key ổn định và một tie-breaker duy nhất?
6. Khi nào `Slice` hoặc cursor có thể phù hợp hơn `Page` cần tổng số phần tử?
7. Tại sao không nên để `Pageable` hoặc `Page<Entity>` của Spring Data xuất hiện trong domain/application contract?
8. Phân biệt lỗi validation, domain, not found, optimistic lock và lỗi hạ tầng.
9. Vì sao không nên bắt mọi exception rồi trả `Optional.empty()` hoặc danh sách rỗng?
10. Những kiểm thử nào cần chạy trên database thật để xác nhận pagination và chính sách lỗi?

## Kết luận

Repository cần cung cấp hợp đồng rõ ràng cho việc tải và lưu aggregate; truy vấn đọc phục vụ danh sách lớn có thể dùng query service riêng. Dùng `Optional` cho một aggregate có thể vắng mặt và collection/trang rỗng cho truy vấn tập hợp không có kết quả. Chọn offset pagination khi cần nhảy trang và keyset pagination khi cần duyệt tuần tự trên tập dữ liệu lớn. Application diễn giải dữ liệu vắng mặt theo use case, domain biểu đạt quy tắc nghiệp vụ, còn adapter chuyển đổi lỗi persistence và giao thức. Khi các ranh giới này rõ ràng, caller có thể xử lý not found, empty result, conflict và lỗi hạ tầng một cách nhất quán.
