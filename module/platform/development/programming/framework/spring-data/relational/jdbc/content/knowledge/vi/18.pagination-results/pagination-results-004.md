# Slice và cách xác định còn trang tiếp theo

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, truy vấn phân trang có thể trả về `Slice<T>` khi giao diện chỉ cần hiển thị một phần dữ liệu và biết **có còn kết quả ở phía sau hay không**. `Slice` cung cấp nội dung của một lát dữ liệu, thông tin trang hiện tại và trạng thái `hasNext()` mà không cần biết tổng số bản ghi của toàn bộ truy vấn.

Đây là lựa chọn phù hợp cho nút **Xem thêm**, cuộn vô hạn hoặc danh sách có nút Trang trước/Trang tiếp theo nhưng không cần hiển thị “Trang 2 trên 37”. Khi chỉ cần xác định có trang tiếp theo, `Slice` tránh việc phải tính tổng số hàng như `Page`.

## 1. Slice là gì?

`Slice<T>` thuộc Spring Data Commons, biểu diễn một phần kết quả có giới hạn. Một Slice thường có:

- Danh sách phần tử của lát hiện tại.
- Số trang hiện tại và kích thước trang.
- Trạng thái `hasNext()` và `hasPrevious()`.
- Các thông tin điều hướng như `nextPageable()` và `previousPageable()`.

Ví dụ ứng dụng hiển thị các đơn hàng đang mở, mỗi lần lấy 20 đơn. Giao diện không cần biết hệ thống có tổng cộng bao nhiêu đơn; chỉ cần biết sau 20 đơn này còn đơn nào không để hiển thị nút “Xem thêm”.

~~~mermaid
flowchart TB
    Request["Request: page=0, size=20"]
    Repo["OrderRepository"]
    DB[("Database")]
    Fetch["Lấy tối đa 21 hàng"]
    Slice["Slice<Order><br/>content tối đa 20"]
    More{"Có hàng thứ 21?"}
    Next["hasNext() = true<br/>hiển thị Xem thêm"]
    End["hasNext() = false<br/>đã tới cuối"]

    Request --> Repo --> DB --> Fetch --> Slice --> More
    More -->|Có| Next
    More -->|Không| End
~~~

Điểm cần nhớ là `Slice` trả lời câu hỏi **“có kết quả tiếp theo không?”**, không trả lời **“tổng cộng có bao nhiêu kết quả?”**.

## 2. Khai báo repository method trả về Slice

Giả sử entity `Order` có các thuộc tính `id`, `status` và `createdAt`. Repository có thể khai báo:

~~~java
package com.example.sales.order;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository extends CrudRepository<Order, Long> {

    Slice<Order> findByStatus(String status, Pageable pageable);
}
~~~

Hai thành phần quan trọng:

- `Slice<Order>` cho biết kết quả được trả theo từng lát và có thông tin điều hướng.
- `Pageable` chứa số trang, kích thước trang và thông tin sắp xếp.

`Pageable` là tham số đặc biệt được Spring Data nhận diện; nó không trở thành điều kiện lọc thông thường của entity. Tên method `findByStatus` vẫn mô tả điều kiện theo property `status`.

Có thể khai báo sắp xếp ngay trong tên method để đảm bảo thứ tự mặc định:

~~~java
Slice<Order> findByStatusOrderByCreatedAtDescIdDesc(
    String status,
    Pageable pageable
);
~~~

Hoặc truyền Sort qua Pageable để lựa chọn thứ tự tại nơi gọi. Tên thuộc tính trong query method và Sort là **property Java** của entity, ví dụ `createdAt`; framework ánh xạ property sang cột SQL tương ứng theo mapping.

## 3. Pageable và PageRequest

`Pageable` mô tả yêu cầu phân trang. Cách tạo thông dụng là `PageRequest.of(pageNumber, pageSize)`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable firstPage = PageRequest.of(0, 20);
Pageable secondPage = PageRequest.of(1, 20);
~~~

Số trang bắt đầu từ **0**:

| pageNumber | pageSize | Offset | Vị trí hàng đầu tiên |
|---:|---:|---:|---:|
| 0 | 20 | 0 | 1 |
| 1 | 20 | 20 | 21 |
| 2 | 20 | 40 | 41 |

Offset được tính theo:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

`PageRequest` cũng nhận thông tin sắp xếp:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Ví dụ này sắp xếp đơn mới nhất trước; nếu hai đơn có cùng thời điểm tạo, ID giảm dần quyết định thứ tự giữa chúng.

## 4. Spring Data xác định hasNext() như thế nào?

Để xác định có trang tiếp theo mà không đếm toàn bộ kết quả, cơ chế Slice thường lấy **nhiều hơn một hàng so với kích thước trang yêu cầu**:

\[
\text{maxResults} = \text{pageSize} + 1
\]

Với page size bằng 20:

- Database được yêu cầu lấy tối đa 21 hàng phù hợp.
- Nếu nhận được 21 hàng, framework biết chắc còn ít nhất một hàng sau 20 hàng đầu.
- Framework giữ 20 hàng đầu trong content và dùng hàng thứ 21 để xác định `hasNext = true`.
- Nếu nhận được từ 0 đến 20 hàng, không có hàng dư để chứng minh trang sau tồn tại, nên `hasNext = false`.

Ví dụ:

| Số hàng truy vấn trả về | Số hàng trong Slice | `hasNext()` | Ý nghĩa |
|---:|---:|---|---|
| 21 | 20 | `true` | Có ít nhất một hàng tiếp theo |
| 20 | 20 | `false` | Đã tới trang cuối |
| 7 | 7 | `false` | Trang cuối chỉ còn 7 hàng |
| 0 | 0 | `false` | Không có kết quả cho trang này |

Giả sử có đúng 40 đơn thỏa điều kiện, page size 20:

1. Trang 0 lấy tối đa 21 hàng, nhận 21; content giữ 20 và `hasNext = true`.
2. Trang 1 lấy từ offset 20 tối đa 21 hàng, chỉ nhận 20; content giữ 20 và `hasNext = false`.

Không cần chạy thêm `SELECT COUNT(*)` để tính tổng số đơn. Đây là khác biệt quan trọng giữa `Slice` và `Page`.

### SQL minh họa

Với PostgreSQL hoặc MySQL, truy vấn ở trang đầu có thể tương đương:

~~~sql
SELECT id, customer_id, status, created_at
FROM sales_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 0;
~~~

Trang kế tiếp:

~~~sql
SELECT id, customer_id, status, created_at
FROM sales_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 20;
~~~

Đây là SQL **minh họa ý nghĩa** của phân trang Slice. Spring Data JDBC và dialect chịu trách nhiệm tạo giới hạn truy vấn cho repository method; không cần tự thêm `LIMIT pageSize + 1` vào một derived query.

## 5. Đọc Slice và xác định trang tiếp theo

Ví dụ service lấy trang đầu:

~~~java
package com.example.sales.order;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public Slice<Order> findOpenOrders(int page, int size) {
        Pageable pageable = PageRequest.of(page, size);
        return orders.findByStatusOrderByCreatedAtDescIdDesc(
            "OPEN",
            pageable
        );
    }
}
~~~

Controller hoặc tầng gọi có thể đọc kết quả:

~~~java
Slice<Order> slice = orderQueryService.findOpenOrders(0, 20);

slice.getContent().forEach(order ->
    System.out.println(order.getId())
);

if (slice.hasNext()) {
    System.out.println("Có thể tải trang tiếp theo");
}
~~~

Các method thường dùng:

| Method | Ý nghĩa |
|---|---|
| `getContent()` | Danh sách phần tử trong Slice |
| `getNumber()` | Số trang hiện tại, bắt đầu từ 0 |
| `getSize()` | Kích thước trang được yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế trong content |
| `hasNext()` | Có trang tiếp theo hay không |
| `hasPrevious()` | Có trang trước hay không |
| `nextPageable()` | Pageable cho trang kế tiếp |
| `previousPageable()` | Pageable cho trang trước |
| `isFirst()` | Có phải trang đầu không |
| `isLast()` | Có phải trang cuối không |

Chỉ gọi `nextPageable()` khi `hasNext()` là true:

~~~java
if (slice.hasNext()) {
    Pageable nextPageable = slice.nextPageable();
    Slice<Order> nextSlice =
        orderRepository.findByStatusOrderByCreatedAtDescIdDesc(
            "OPEN",
            nextPageable
        );
}
~~~

`nextPageable()` chỉ mô tả yêu cầu trang kế tiếp; nó **không tự chạy truy vấn**. Ứng dụng phải truyền Pageable đó vào lần gọi repository tiếp theo.

## 6. Slice khác Page và List như thế nào?

Ba kiểu trả về có hợp đồng khác nhau:

| Tiêu chí | `List<T>` | `Slice<T>` | `Page<T>` |
|---|---|---|---|
| Nội dung kết quả | Có | Có | Có |
| Số trang hiện tại | Không | Có | Có |
| Biết còn trang tiếp theo | Không tự có | Có | Có |
| Biết tổng số phần tử | Không | Không | Có |
| Biết tổng số trang | Không | Không | Có |
| Thường cần count query | Không | Không | Có thể cần |
| Hợp với | Danh sách nhỏ/không phân trang | Xem thêm, infinite scroll | Giao diện cần tổng số trang |

### Page có tổng số

Ví dụ:

~~~java
Page<Order> findByStatus(String status, Pageable pageable);
~~~

`Page<Order>` có thêm:

- `getTotalElements()`: tổng số hàng phù hợp điều kiện.
- `getTotalPages()`: tổng số trang.

Để biết tổng số chính xác, framework thường cần một count query riêng hoặc cơ chế đếm tương đương. Với bảng lớn và điều kiện phức tạp, count query có thể tốn đáng kể thời gian.

### Slice chỉ cần biết còn dữ liệu

~~~java
Slice<Order> findByStatus(String status, Pageable pageable);
~~~

Không cần tổng số; framework chỉ cần biết có hàng dư ngoài page size. Điều này thường phù hợp hơn cho trải nghiệm cuộn hoặc nút “Xem thêm”.

### List với Pageable

Một method trả về `List<T>` có thể dùng `Pageable` để giới hạn và lấy một phần kết quả, nhưng danh sách tự nó không mang thông tin `hasNext`. Caller không thể biết chắc có trang sau chỉ từ việc nhận được đúng page size hàng.

Nếu chỉ cần content và trạng thái còn trang sau, `Slice` diễn đạt ý định rõ ràng hơn.

## 7. Xây dựng endpoint “Xem thêm”

Ví dụ response API có thể trả content và một cờ boolean:

~~~java
public record OrderSliceResponse(
    List<OrderSummary> content,
    int page,
    int size,
    boolean hasNext
) {}

public record OrderSummary(
    Long id,
    String status
) {}
~~~

Service chuyển Slice thành response:

~~~java
public OrderSliceResponse getOpenOrderSlice(int page, int size) {
    Slice<Order> slice =
        orderRepository.findByStatusOrderByCreatedAtDescIdDesc(
            "OPEN",
            PageRequest.of(page, size)
        );

    List<OrderSummary> content = slice.getContent().stream()
        .map(order -> new OrderSummary(
            order.getId(),
            order.getStatus()
        ))
        .toList();

    return new OrderSliceResponse(
        content,
        slice.getNumber(),
        slice.getSize(),
        slice.hasNext()
    );
}
~~~

Client gửi:

~~~http
GET /api/orders/open?page=0&size=20
~~~

Ví dụ response:

~~~json
{
  "content": [
    { "id": 501, "status": "OPEN" },
    { "id": 498, "status": "OPEN" }
  ],
  "page": 0,
  "size": 20,
  "hasNext": true
}
~~~

Response chỉ minh họa hai phần tử đầu để dễ đọc; trong thực tế content có tối đa 20 phần tử theo size đã yêu cầu. Client lưu page hiện tại; khi người dùng bấm “Xem thêm”, tăng page lên 1 và gọi endpoint lần nữa. Nếu `hasNext` là false, ẩn nút hoặc kết thúc việc tải.

Không nhất thiết phải trả toàn bộ object `Slice` trực tiếp ra JSON. DTO cho phép kiểm soát hợp đồng API và không làm lộ các chi tiết nội bộ của Spring Data.

## 8. Sắp xếp ổn định là điều kiện quan trọng

Phân trang chỉ có ý nghĩa khi kết quả được sắp xếp nhất quán. Nếu không khai báo `ORDER BY`, database không bảo đảm thứ tự hàng. Hai lần gọi trang 0 và trang 1 có thể nhận các hàng theo thứ tự khác nhau.

Ví dụ nên dùng:

~~~java
Pageable pageable = PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

`createdAt` có thể trùng nhau giữa nhiều Order. Thêm `id` làm khóa phụ duy nhất tạo ra thứ tự xác định hơn.

Quy tắc:

- Luôn có thứ tự rõ ràng cho truy vấn phân trang.
- Nên thêm khóa duy nhất làm tie-breaker cuối cùng.
- Dùng property Java trong `Sort`, không nhầm với tên cột SQL nếu naming strategy khác.
- Không thay đổi thứ tự giữa các request của cùng một chuỗi phân trang.

## 9. Offset pagination và dữ liệu thay đổi giữa các lần tải

`PageRequest` thông thường sử dụng **offset pagination**. Ví dụ trang 2, size 20 tương ứng offset 40. Cách này dễ hiểu và phù hợp với nhiều màn hình quản trị, nhưng có hai hạn chế.

### Offset lớn có thể tốn kém

Khi người dùng yêu cầu một trang rất sâu, database có thể phải đi qua nhiều hàng bị bỏ qua trước khi trả kết quả. Index phù hợp giúp cải thiện, nhưng không làm mọi truy vấn offset sâu trở nên miễn phí.

### Dữ liệu mới có thể làm dịch chuyển vị trí

Giả sử trang 0 đã trả 20 đơn mới nhất. Trước khi client tải trang 1, một đơn mới được insert ở đầu danh sách. Với offset 20, trang tiếp theo có thể chứa lại một hàng cuối của trang trước hoặc làm một hàng bị bỏ qua, tùy thứ tự và thời điểm truy vấn.

Mỗi request Slice thường là một truy vấn riêng; nó không tự giữ snapshot xuyên suốt toàn bộ hành trình cuộn trang. Nếu ứng dụng cần duyệt một tập dữ liệu ổn định trong lúc dữ liệu thay đổi, cần cân nhắc transaction/snapshot phù hợp hoặc thiết kế cursor/keyset.

## 10. Keyset pagination khi offset không còn phù hợp

Với danh sách lớn hoặc thay đổi liên tục, có thể dùng **keyset pagination**: thay vì nói “bỏ qua 40 hàng”, request tiếp theo gửi giá trị khóa của hàng cuối cùng đã nhận.

Giả sử thứ tự là `created_at DESC, id DESC`. Nếu hàng cuối trang hiện tại có `created_at = :lastCreatedAt` và `id = :lastId`, trang sau lọc:

~~~sql
SELECT id, customer_id, status, created_at
FROM sales_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Điều kiện so sánh phải khớp chính xác thứ tự sort và xử lý null của các cột sort. Với sort nhiều cột, biểu thức cursor cần chứa đủ giá trị để xác định vị trí duy nhất.

Keyset có thể giảm chi phí bỏ qua hàng ở các trang sâu và giảm hiện tượng dịch chuyển do insert ở đầu danh sách. Tuy nhiên:

- Nó cần cursor chứa các giá trị khóa cuối trang.
- Thay đổi hoặc xóa dữ liệu vẫn có thể ảnh hưởng kết quả.
- Không hỗ trợ nhảy trực tiếp đến trang số 50 theo cách offset thường làm.
- Việc triển khai có thể cần custom query/repository tùy API và phiên bản Spring Data JDBC.

**Slice không đồng nghĩa với keyset pagination.** Một Slice dùng Pageable/PageRequest thường vẫn dùng offset; muốn keyset cần thiết kế cursor và điều kiện truy vấn rõ ràng.

## 11. Giới hạn kích thước trang

Không nên để client yêu cầu page size tùy ý, ví dụ hàng trăm nghìn bản ghi. Điều đó có thể gây tải lớn cho database, network và heap của ứng dụng.

Ví dụ giới hạn ở service:

~~~java
private static final int DEFAULT_SIZE = 20;
private static final int MAX_SIZE = 100;

public Slice<Order> findOpenOrders(int page, int requestedSize) {
    if (page < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }

    int size = requestedSize <= 0
        ? DEFAULT_SIZE
        : Math.min(requestedSize, MAX_SIZE);

    Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    );

    return orderRepository.findByStatus("OPEN", pageable);
}
~~~

Trong thực tế, cần quyết định rõ việc size không hợp lệ sẽ dùng mặc định hay trả lỗi HTTP 400. Đừng để một client có thể yêu cầu trang cực lớn và vô tình tạo truy vấn nặng.

## 12. Slice với @Query hoặc SQL tùy chỉnh

Khi dùng SQL tùy chỉnh, method vẫn có thể nhận `Pageable` và trả `Slice` nếu query method và phiên bản Spring Data JDBC hỗ trợ kiểu trả về đó. Ví dụ:

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM sales_orders
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    """)
Slice<Order> findOpenOrders(
    @Param("status") String status,
    Pageable pageable
);
~~~

Ví dụ dùng `@Query` để minh họa SQL khai báo tường minh; không thêm `LIMIT` cố định vào câu SQL khi đồng thời giao cho framework xử lý Pageable, vì có thể xung đột với giới hạn phân trang. Kiểm tra hỗ trợ Pageable/Slice của phiên bản Spring Data JDBC đang sử dụng và xem SQL thực tế trong log khi cần.

Nếu query có join hoặc trả về projection, cần bảo đảm result mapping tương thích kiểu trả về. Phân trang kết quả join có thể gặp trùng root khi một Order nối với nhiều hàng con; khi đó cần thiết kế query để trang được xác định trên các root duy nhất, ví dụ chọn ID root trước rồi lấy dữ liệu cần hiển thị.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `Page` dù chỉ cần biết còn dữ liệu | Có thể phát sinh count query không cần thiết | Dùng `Slice` nếu không cần tổng số |
| Dùng `List` rồi kiểm tra `size()` | Không có thông tin chắc chắn về trang tiếp theo | Dùng `Slice` hoặc tự thiết kế query pageSize+1 |
| Nghĩ `hasNext()` là tổng số trang | Hiểu sai hợp đồng Slice | `hasNext` chỉ là boolean |
| Quên thứ tự `ORDER BY` | Hàng có thể xuất hiện lặp hoặc bị bỏ qua | Sắp xếp ổn định và thêm unique tie-breaker |
| Dùng page number bắt đầu từ 1 | Lấy lệch trang | `PageRequest` bắt đầu từ 0 |
| Gọi `nextPageable()` khi không có next | Điều hướng không hợp lệ hoặc không có ý nghĩa | Kiểm tra `hasNext()` trước |
| Nghĩ `nextPageable()` tự tải dữ liệu | Không có truy vấn mới | Gọi repository với Pageable mới |
| Page size quá lớn | Tốn bộ nhớ và tài nguyên database | Giới hạn size ở API/service |
| Dùng offset sâu trên bảng lớn | Truy vấn chậm | Cân nhắc keyset/cursor |
| Dùng Slice và cho rằng đã có snapshot xuyên nhiều request | Dữ liệu thay đổi có thể làm lệch các trang | Chọn snapshot hoặc cursor theo yêu cầu nhất quán |
| Thêm LIMIT thủ công cùng Pageable | Giới hạn bị chồng hoặc SQL sai | Để framework áp dụng pageable hoặc tự quản lý toàn bộ custom SQL |

## 14. Bài thực hành

1. Tạo repository method `Slice<Order> findByStatus(String status, Pageable pageable)`.
2. Gọi với `PageRequest.of(0, 5)` và kiểm tra `getContent().size()` cùng `hasNext()`.
3. Chuẩn bị 12 đơn OPEN. Lấy trang 0 size 5, trang 1 size 5 và trang 2 size 5. Dự đoán số hàng và `hasNext` ở mỗi trang.
4. Đổi method trả về `Page<Order>`. Quan sát các thuộc tính `getTotalElements()`, `getTotalPages()` và sự khác biệt về nhu cầu count.
5. Thử trả về `List<Order>` với Pageable. Vì sao List không cung cấp `hasNext`?
6. Bỏ `ORDER BY` rồi gọi lại nhiều lần. Giải thích vì sao không nên dựa vào thứ tự ngẫu nhiên của database.
7. Dùng sort `createdAt DESC, id DESC`. Kiểm tra các hàng có cùng createdAt vẫn có thứ tự xác định.
8. Trong lúc client tải trang 1, insert một đơn mới ở đầu danh sách. Quan sát tác động của offset pagination.
9. Viết truy vấn keyset theo `created_at` và `id` với cursor là hàng cuối của trang trước.
10. Thêm giới hạn page size tối đa 100 ở service và thử gửi yêu cầu size lớn hơn.

Ví dụ kết quả với 12 đơn và page size 5:

| Trang | Hàng nhận từ truy vấn (tối đa 6) | Content trả về | `hasNext` |
|---:|---:|---:|---|
| 0 | 6 | 5 | `true` |
| 1 | 6 | 5 | `true` |
| 2 | 2 | 2 | `false` |

## 15. Ghi nhớ

`Slice<T>` phù hợp khi ứng dụng cần lấy một phần dữ liệu và biết còn trang tiếp theo mà không cần tổng số phần tử. Spring Data xác định `hasNext` bằng cách lấy dư một hàng so với page size: có hàng dư thì giữ lại đúng page size phần content và đánh dấu còn trang; không có hàng dư thì đây là lát cuối.

`Page` cung cấp tổng số và thường cần count query; `List` chỉ cung cấp các phần tử. Với Slice, hãy dùng `Pageable`/`PageRequest`, sắp xếp ổn định bằng một khóa duy nhất làm tie-breaker và kiểm tra `hasNext()` trước khi lấy `nextPageable()`. Nếu dữ liệu rất lớn hoặc thường xuyên thay đổi, hãy đánh giá giới hạn của offset pagination và cân nhắc keyset/cursor phù hợp.
