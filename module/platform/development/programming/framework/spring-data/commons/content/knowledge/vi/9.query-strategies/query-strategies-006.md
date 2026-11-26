# Tham số nghiệp vụ và tham số đặc biệt như Pageable hoặc Sort

Trong chương **Chiến lược truy vấn** của Spring Data Commons (`SPRING_DATA_COMMONS`), bài này giải thích cách một query method tiếp nhận điều kiện nghiệp vụ cùng yêu cầu phân trang, sắp xếp. Đây là nền tảng để thiết kế repository có chữ ký rõ ràng và chọn đúng kiểu kết quả.

Commons định nghĩa các abstraction dùng chung; module như JPA hoặc MongoDB quyết định cách chuyển chúng thành thao tác với kho dữ liệu. Các ví dụ chính dưới đây dùng repository dạng imperative. Khả năng hỗ trợ query method, kiểu trả về và cách thực thi vẫn phải phù hợp với module đang sử dụng.

## 1. Hai nhóm tham số có hai trách nhiệm khác nhau

Giả sử màn hình hỗ trợ cần tìm ticket đang mở trong hàng đợi `SUPPORT`, hiển thị 20 ticket mỗi trang và ưu tiên ticket mới tạo.

Yêu cầu có thể tách thành:

| Thành phần | Giá trị minh họa | Trách nhiệm |
| --- | --- | --- |
| Trạng thái | `OPEN` | Chỉ nhận ticket thỏa trạng thái. |
| Hàng đợi | `SUPPORT` | Chỉ nhận ticket thuộc hàng đợi này. |
| Trang và kích thước | Trang chỉ số 0, tối đa 20 phần tử | Chọn một khoảng kết quả. |
| Thứ tự | `createdAt DESC, id DESC` | Xác định thứ tự trước khi chọn khoảng. |

Hai dòng đầu là **tham số nghiệp vụ**, thường được bind vào điều kiện truy vấn. Hai dòng sau được thể hiện bằng **tham số đặc biệt** mà hạ tầng nhận diện.

Ví dụ chữ ký:

```java
Page<Ticket> findByStatusAndQueueCode(
    TicketStatus status,
    String queueCode,
    Pageable pageable
);
```

Trong chữ ký này, `status` và `queueCode` tương ứng với hai điều kiện trong tên method. `pageable` không đại diện cho một điều kiện thứ ba tên là “pageable”.

Spring Data Commons mô hình hóa việc phân biệt này qua metadata tham số; tập tham số bindable loại bỏ những tham số được nhận diện là đặc biệt. Không nên lấy tổng số tham số Java rồi kết luận query phải có đúng bấy nhiêu giá trị lọc. Xem [API Parameters](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/Parameters.html).

## 2. Nhận diện theo kiểu tham số, không theo tên biến

Các import quan trọng trong bài là:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
```

Một biến Java tên `pageable` nhưng có kiểu `String` không trở thành yêu cầu phân trang. Tương tự, một chuỗi tên `sort` không tự biến thành đối tượng sắp xếp.

Hãy đọc chữ ký theo hai bước:

1. Xác định các kiểu đặc biệt được Spring Data và module nhận diện.
2. Đối chiếu những tham số nghiệp vụ còn lại với điều kiện của query.

Ví dụ:

```java
List<Ticket> findByQueueCode(String queueCode, Sort order);
```

Tên biến `order` không làm mất vai trò của `Sort`. Ngược lại:

```java
// Không phải một chữ ký để bật dynamic sorting.
List<Ticket> findByQueueCode(String queueCode, String sort);
```

Với derived query thông thường, chuỗi thứ hai là một tham số bindable thừa so với điều kiện `QueueCode`. Đổi tên biến không sửa được vấn đề; cần đổi hợp đồng method sang kiểu tham số đúng.

Cũng không tự thêm hai tham số `int page, int size` vào query method rồi chờ framework ghép chúng thành `Pageable`. Service có thể nhận hai số đó, nhưng cần tạo đối tượng phân trang trước khi gọi repository.

## 3. Một repository minh họa đầy đủ các dạng thường dùng

Giả sử mô hình `Ticket` đã được ánh xạ theo module, có các thuộc tính:

| Thuộc tính Java | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `status` | `TicketStatus` | Ví dụ `OPEN`, `CLOSED`. |
| `queueCode` | `String` | Mã hàng đợi. |
| `createdAt` | `Instant` | Thời điểm tạo. |

Repository sau chỉ minh họa hợp đồng truy vấn; cấu hình kho dữ liệu và mapping của `Ticket` được chuẩn bị riêng:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    Page<Ticket> findByStatusAndQueueCode(
        TicketStatus status,
        String queueCode,
        Pageable pageable
    );

    Slice<Ticket> findByStatus(
        TicketStatus status,
        Pageable pageable
    );

    List<Ticket> findByQueueCode(
        String queueCode,
        Sort sort
    );

    List<Ticket> findByQueueCode(
        String queueCode,
        Pageable pageable
    );
}
```

Hai overload cuối có cùng điều kiện nghiệp vụ nhưng phục vụ hai nhu cầu: sắp xếp tập kết quả, hoặc lấy một khoảng kết quả. Không chọn overload nhận `Sort` nếu yêu cầu thực sự là giới hạn 20 ticket; `Sort` tự nó không mang kích thước trang.

Việc kế thừa `CrudRepository` cung cấp những thao tác CRUD cơ sở. Các query method tự khai báo vẫn cần được module giải quyết theo chiến lược truy vấn có hiệu lực.

## 4. Sort mô tả thứ tự, không giới hạn số lượng

Tạo thứ tự ưu tiên ticket mới nhất:

```java
import org.springframework.data.domain.Sort;

Sort newestFirst = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<Ticket> tickets =
    repository.findByQueueCode("SUPPORT", newestFirst);
```

Trong ví dụ này:

- `queueCode` xác định ticket được chọn.
- `createdAt DESC` đưa ticket mới lên trước.
- `id DESC` phân định thứ tự khi nhiều ticket có cùng thời điểm tạo.

`Sort` chứa các yêu cầu sắp xếp. Những thao tác như `and(...)` trả về đối tượng kết hợp mới, vì vậy cần dùng giá trị trả về. Xem [API Sort](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html).

Ví dụ một lỗi ở phía gọi:

```java
Sort sort = Sort.by("createdAt").descending();

// Giá trị kết hợp bị bỏ đi.
sort.and(Sort.by("id").descending());
```

Cách viết đúng:

```java
Sort sort = Sort.by("createdAt").descending()
    .and(Sort.by("id").descending());
```

Trong derived query dựa trên mô hình này, dùng tên thuộc tính `createdAt`, không mặc nhiên dùng tên cột SQL như `created_at`. Với declared query, alias và biểu thức sort có thể có quy tắc riêng của module.

Nếu không có giới hạn khác, method trả `List` chỉ nhận `Sort` có thể lấy toàn bộ tập khớp. Một danh sách đã sắp xếp vẫn có thể quá lớn để tải vào bộ nhớ.

## 5. Pageable kết hợp khoảng kết quả và Sort

`Pageable` là abstraction mô tả yêu cầu phân trang, gồm thông tin trang, kích thước và thứ tự. `PageRequest` là một implementation thường dùng. Xem [API Pageable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html).

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable request = PageRequest.of(0, 20, sort);

Page<Ticket> page = repository.findByStatusAndQueueCode(
    TicketStatus.OPEN,
    "SUPPORT",
    request
);
```

Với `PageRequest`, chỉ số trang bắt đầu từ 0. Chỉ số phải không âm; kích thước trang phải lớn hơn 0. Tham số thứ nhất là số trang, không phải số bản ghi cần bỏ qua. Xem [API PageRequest](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html).

Ví dụ:

| Yêu cầu | Ý nghĩa trong mô hình offset |
| --- | --- |
| `PageRequest.of(0, 20, sort)` | Bắt đầu từ offset 0. |
| `PageRequest.of(1, 20, sort)` | Bắt đầu từ offset 20. |
| `PageRequest.of(2, 20, sort)` | Bắt đầu từ offset 40. |

Công thức với yêu cầu có phân trang là:

```text
offset = chỉ số trang × kích thước trang
```

Một trang yêu cầu 20 phần tử có thể trả ít hơn 20, hoặc không có phần tử nào. Đây là kích thước tối đa của khoảng lấy, không phải lời bảo đảm có đủ dữ liệu.

Mô hình để hình dung lời gọi ở trên:

```text
Ticket
  -> lọc status = OPEN và queueCode = SUPPORT
  -> sắp xếp createdAt giảm dần, id giảm dần
  -> lấy khoảng bắt đầu từ offset 0, tối đa 20 phần tử
  -> đóng gói kết quả theo kiểu trả về
```

Đây là mô hình ngữ nghĩa; không có nghĩa ứng dụng phải tải toàn bộ ticket rồi lọc, sort và cắt bằng Java.

## 6. Kiểu trả về quyết định thông tin cần lấy thêm

Có tham số `Pageable` chưa đủ để biết kết quả có tổng số phần tử hay không. Cần đọc cả kiểu trả về.

### 6.1. Page: nội dung cùng tổng số

`Page<T>` mở rộng `Slice<T>` và bổ sung tổng số phần tử, tổng số trang. Xem [API Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html).

```java
List<Ticket> content = page.getContent();

int requestedSize = page.getSize();
int returnedCount = page.getNumberOfElements();

long totalMatches = page.getTotalElements();
int totalPages = page.getTotalPages();
```

Trong bài toán màn hình quản trị, `totalMatches` phục vụ dòng “có 1.240 ticket phù hợp”, còn `returnedCount` chỉ đếm số ticket của trang đang hiển thị.

Để cung cấp tổng số, hạ tầng thường cần truy vấn đếm bổ sung. Không nên khẳng định mọi lần gọi `Page` luôn phát đúng hai câu truy vấn; có trường hợp tổng số được suy ra từ kết quả hoặc có tối ưu tùy module. Điểm thiết kế cần nhớ là yêu cầu tổng số có thể mang thêm chi phí.

### 6.2. Slice: có nội dung và biết còn phần tiếp theo

`Slice<T>` cung cấp nội dung, thông tin vị trí và khả năng điều hướng như `hasNext()`, `nextPageable()`, nhưng không có hợp đồng tổng số phần tử như `Page`. Xem [API Slice](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Slice.html).

Ví dụ màn hình chỉ có nút “Tải thêm”:

```java
Slice<Ticket> slice = repository.findByStatus(
    TicketStatus.OPEN,
    PageRequest.of(0, 20, sort)
);

display(slice.getContent());

if (slice.hasNext()) {
    Pageable nextRequest = slice.nextPageable();
    // Dùng nextRequest khi người dùng yêu cầu tải tiếp.
}
```

`display(...)` đại diện cho mã hiển thị của ứng dụng. Kiểm tra `hasNext()` trước khi quyết định yêu cầu phần tiếp theo.

Một cách thực thi phổ biến lấy dư một phần tử để biết còn kết quả. Phần tử dùng để xác định `hasNext` không có nghĩa giao diện phải hiển thị 21 ticket khi kích thước yêu cầu là 20.

### 6.3. List kết hợp Pageable: chỉ lấy nội dung của khoảng

```java
List<Ticket> batch = repository.findByQueueCode(
    "SUPPORT",
    PageRequest.of(0, 20, sort)
);
```

Ở dạng này, hạ tầng áp dụng khoảng lấy nhưng không tạo metadata tổng số của `Page`. Riêng việc trả `List` không cung cấp `hasNext()`.

Không kết luận “còn trang sau” chỉ vì `batch.size() == 20`: có thể đúng 20 ticket khớp và đó là toàn bộ dữ liệu. Nếu giao diện cần tín hiệu còn dữ liệu, dùng hợp đồng `Slice` phù hợp thay vì tự đoán.

| Nhu cầu của ứng dụng | Dạng kết quả phù hợp để cân nhắc |
| --- | --- |
| Hiển thị tổng số và số trang | `Page<T>` với `Pageable`. |
| Đi từng phần, biết còn phần tiếp theo | `Slice<T>` với `Pageable`. |
| Chỉ cần nội dung của một khoảng | `List<T>` với `Pageable`. |
| Chỉ cần thứ tự, đã có cơ chế kiểm soát quy mô kết quả | `List<T>` với `Sort`. |

Các dạng query method và chi phí đếm được mô tả trong [Spring Data Commons — Paging, Iterating Large Results, Sorting & Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters).

## 7. Không truyền null để biểu đạt “không áp dụng”

Dùng đối tượng diễn đạt rõ ý định:

```java
List<Ticket> unsorted =
    repository.findByQueueCode("SUPPORT", Sort.unsorted());

List<Ticket> unpaged =
    repository.findByQueueCode("SUPPORT", Pageable.unpaged());
```

Các API query method nhận `Sort` hoặc `Pageable` yêu cầu giá trị không null; xem [quy tắc tham số đặc biệt của Commons](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters).

`unsorted()` biểu đạt không bổ sung yêu cầu dynamic sort; không hứa rằng kho dữ liệu sẽ trả theo thứ tự chèn. Một thứ tự tĩnh trong query vẫn có thể tồn tại.

`unpaged()` biểu đạt không áp dụng phân trang; nó không đồng nghĩa “lấy trang đầu”. Trong ví dụ hàng đợi, gọi unpaged cho hàng đợi có hàng triệu ticket có thể làm thay đổi mạnh lượng dữ liệu cần lấy.

Khi xây helper nhận mọi `Pageable`, cần kiểm tra `isPaged()` trước khi dùng số trang, kích thước hoặc offset. Đối tượng unpaged không cung cấp những giá trị này theo cùng hợp đồng với yêu cầu có phân trang. Xem [API Pageable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html).

Tham số nghiệp vụ null là một vấn đề khác: ý nghĩa phụ thuộc loại truy vấn, annotation và module. Không suy từ quy tắc special parameter rằng `status = null` tự động có nghĩa “bỏ qua lọc trạng thái”.

## 8. Những chữ ký cần tránh

### 8.1. Nhận cả Pageable và Sort

```java
// Không hợp lệ cho query method của hạ tầng repository.
Page<Ticket> findByStatus(
    TicketStatus status,
    Pageable pageable,
    Sort sort
);
```

`Pageable` đã chứa `Sort`. Đưa thứ tự vào yêu cầu phân trang:

```java
Pageable request = PageRequest.of(0, 20, sort);
```

### 8.2. Lặp cùng một loại tham số đặc biệt

```java
// Không dùng hai Sort để biểu đạt thứ tự chính và phụ.
List<Ticket> findByQueueCode(
    String queueCode,
    Sort primary,
    Sort secondary
);
```

Kết hợp thứ tự thành một `Sort` trước lời gọi. Tương tự, không dùng hai `Pageable` để mô tả hai khoảng kết quả trong cùng query method.

Ở API có hỗ trợ `Limit`, cũng không kết hợp `Pageable` với `Limit` trong một query method, vì yêu cầu phân trang đã mang giới hạn kích thước.

Các tổ hợp loại trừ và quy tắc không lặp special parameter được nêu trong [tài liệu Commons về tham số đặc biệt](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters).

Các quy tắc này nói về query method do hạ tầng repository xử lý. Một method trong custom fragment có thân triển khai riêng phải tự thực hiện hợp đồng mà nó công bố; chỉ nhận `Pageable` không tự khiến mã tùy chỉnh được phân trang.

## 9. Với declared query, vẫn tách điều kiện khỏi điều khiển thực thi

Chiến lược truy vấn quyết định nguồn định nghĩa query. Việc query được suy từ tên hay lấy từ khai báo không biến `Pageable` thành một giá trị nghiệp vụ.

Ví dụ dưới đây **riêng cho Spring Data JPA**, giả sử `Ticket` là tên entity và repository JPA đã được cấu hình:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Đặt method này trong interface repository JPA của Ticket.
@Query(
    value = "select t from Ticket t "
        + "where t.status = :status and t.queueCode = :queue",
    countQuery = "select count(t) from Ticket t "
        + "where t.status = :status and t.queueCode = :queue"
)
Page<Ticket> findQueueTickets(
    @Param("status") TicketStatus status,
    @Param("queue") String queueCode,
    Pageable pageable
);
```

Hai named parameter trong JPQL nhận hai giá trị nghiệp vụ. Không thêm `:pageable` hoặc `:sort` vào điều kiện để bind toàn bộ đối tượng điều khiển. Query nội dung và query đếm phải mô tả cùng tập ticket cần thống kê.

Ví dụ viết rõ `countQuery` để thấy trách nhiệm của hai query; không có nghĩa mọi JPQL đơn giản đều bắt buộc khai báo nó. Với query phức tạp, đặc biệt native query, khả năng suy ra count và áp dụng dynamic sort còn tùy dạng query cùng module. Xem [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html).

Không đưa annotation `org.springframework.data.jpa.repository.Query` sang repository MongoDB chỉ vì cùng đang dùng Commons. Ngôn ngữ query, mapping và khả năng hỗ trợ thuộc module cụ thể.

## 10. Chuẩn hóa đầu vào trước khi gọi repository

Service nên chuyển yêu cầu của giao diện thành hợp đồng repository rõ ràng. Ví dụ sau giới hạn kích thước và chỉ cho phép một số khóa sắp xếp của màn hình:

```java
import java.util.Objects;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

static Pageable buildRequest(
    int page,
    int size,
    String sortKey,
    boolean descending
) {
    if (page < 0) {
        throw new IllegalArgumentException("page must be non-negative");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size must be between 1 and 100");
    }

    Objects.requireNonNull(sortKey, "sortKey");

    String property = switch (sortKey) {
        case "created" -> "createdAt";
        case "id" -> "id";
        default -> throw new IllegalArgumentException("Unsupported sort key");
    };

    Sort.Direction direction = descending
        ? Sort.Direction.DESC
        : Sort.Direction.ASC;

    Sort order = Sort.by(direction, property);

    if (!property.equals("id")) {
        order = order.and(Sort.by(direction, "id"));
    }

    return PageRequest.of(page, size, order);
}
```

Đây là chính sách ví dụ của ứng dụng, không phải giới hạn mặc định 100 của Commons. Nếu API giao diện đánh số trang từ 1, cần chuyển đổi và kiểm tra tại ranh giới API trước khi gọi helper.

Danh sách khóa sort cho phép giúp giữ hợp đồng giao diện ổn định: phía ngoài dùng `created`, còn mô hình nội bộ dùng `createdAt`. Không cần công khai mọi thuộc tính của entity.

Helper này cũng không thay thế kiểm tra quyền. Ví dụ, nếu người dùng chỉ được xem một hàng đợi nhất định, service phải lấy hoặc xác minh `queueCode` được phép rồi truyền nó như điều kiện nghiệp vụ. Phân trang và sắp xếp không cung cấp cơ chế giới hạn phạm vi dữ liệu được truy cập.

## 11. Sắp xếp ổn định và giới hạn của offset

Giả sử bốn ticket đều có `createdAt = 10:00:00`. Chỉ sort theo thời điểm tạo chưa phân định thứ tự giữa bốn ticket đó. Khi lấy hai trang riêng biệt, ứng dụng không nên dựa vào thứ tự ngẫu nhiên giữa các giá trị bằng nhau.

Thêm định danh duy nhất làm tiêu chí phụ giúp định nghĩa thứ tự đầy đủ cho tập dữ liệu đang xét. Trong ví dụ, `createdAt DESC, id DESC` quy định cả trường hợp trùng thời điểm.

Tuy nhiên, thứ tự đầy đủ không đóng băng dữ liệu qua nhiều lần gọi:

```text
Lần 1: lấy trang 0, kích thước 2 -> ticket 105, 104.
Sau đó: một ticket 106 được thêm vào đầu.
Lần 2: lấy trang 1, kích thước 2 -> ticket 104, 103.
```

Ticket 104 có thể xuất hiện lại vì vị trí offset đã dịch chuyển. Đây là tình huống dữ liệu thay đổi giữa hai yêu cầu. Nếu nghiệp vụ cần duyệt nhất quán qua tập biến động, phải thiết kế thêm cách chốt dữ liệu hoặc cơ chế duyệt phù hợp với module.

Tương tự, yêu cầu kích thước 20 ở một offset rất sâu không bảo đảm công việc của database chỉ tương đương đọc 20 hàng. Khi phân trang sâu trở thành vấn đề, cần xem cách thực thi và kế hoạch truy vấn của kho dữ liệu.

## 12. Bài thực hành nhỏ: dự đoán dữ liệu và metadata

Cho dữ liệu cố định sau; thời điểm dùng cùng ngày, cùng múi giờ:

| id | status | queueCode | createdAt |
| --- | --- | --- | --- |
| 105 | OPEN | SUPPORT | 10:05 |
| 104 | CLOSED | SUPPORT | 10:04 |
| 103 | OPEN | BILLING | 10:03 |
| 102 | OPEN | SUPPORT | 10:02 |
| 101 | OPEN | SUPPORT | 10:01 |

Thực hiện:

```java
Sort order = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Page<Ticket> result = repository.findByStatusAndQueueCode(
    TicketStatus.OPEN,
    "SUPPORT",
    PageRequest.of(0, 2, order)
);
```

Kết quả cần dự đoán:

- Tập khớp gồm ticket 105, 102, 101.
- Trang chỉ số 0 có ticket 105 và 102.
- Số phần tử hiện tại là 2; tổng số phần tử khớp là 3.
- Tổng số trang là 2.
- Cùng điều kiện với trang chỉ số 1 sẽ có ticket 101.

Sau đó đổi lời gọi sang:

```java
List<Ticket> result = repository.findByQueueCode(
    "SUPPORT",
    PageRequest.of(0, 2, order)
);
```

Lần này ticket 104 được phép xuất hiện: method chỉ lọc hàng đợi, không lọc trạng thái. Kết quả là 105 và 104. `Pageable` không giữ hộ điều kiện `OPEN` từ một lần gọi trước đó.

Tiếp tục gọi overload nhận `Sort`:

```java
List<Ticket> result =
    repository.findByQueueCode("SUPPORT", order);
```

Kết quả gồm 105, 104, 102, 101; yêu cầu này không chứa giới hạn hai phần tử.

Ba lời gọi trên cho thấy trách nhiệm cần đọc từ chữ ký: điều kiện nằm ở query và tham số nghiệp vụ; khoảng lấy cùng thứ tự nằm ở tham số điều khiển; metadata nhận được phụ thuộc kiểu trả về.
