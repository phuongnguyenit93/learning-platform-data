# Lost update và hai người dùng cùng sửa một aggregate

Khi hai người dùng cùng mở một aggregate, mỗi người có thể nhìn thấy cùng một trạng thái ban đầu. Nếu cả hai sửa rồi lưu gần như đồng thời, lần lưu sau có thể ghi đè thay đổi của lần lưu trước. Hiện tượng này gọi là **lost update** (mất cập nhật).

Trong Spring Data JDBC, cách phổ biến để phát hiện tình huống đó là **optimistic locking** bằng thuộc tính số được đánh dấu `@Version`. Version được lưu trên aggregate root. Khi repository lưu aggregate, Spring Data JDBC chỉ cập nhật nếu version trong database vẫn bằng version mà ứng dụng đã đọc. Nếu một transaction khác đã lưu trước, thao tác sau thất bại với `OptimisticLockingFailureException`.

Bài học này giải thích lost update bằng một tình huống hai người dùng cùng sửa đơn hàng, cách bật `@Version`, cách xử lý conflict ở application/API layer, và khi nào cần khóa pessimistic hoặc transaction isolation mạnh hơn.

## 1. Lost update là gì?

Giả sử một đơn hàng có trạng thái và danh sách dòng hàng:

~~~text
SalesOrder #500
    status = DRAFT
    version = 7
    lines:
        - BOOK-01, quantity = 2
        - PEN-02, quantity = 4
~~~

Người dùng A và người dùng B cùng mở đơn hàng #500. Cả hai đều nhận trạng thái version 7.

- A thay số lượng BOOK-01 từ 2 thành 3.
- B thay số lượng PEN-02 từ 4 thành 5.
- A lưu trước.
- B lưu sau bằng bản aggregate cũ.

Nếu hệ thống không phát hiện dữ liệu đã thay đổi kể từ lúc B đọc, B có thể ghi toàn bộ trạng thái cũ của aggregate cùng thay đổi của mình. Thay đổi của A biến mất.

Đây là lost update: một cập nhật hợp lệ đã được commit nhưng bị một cập nhật khác dựa trên dữ liệu cũ ghi đè.

### 1.1. Mô phỏng hai người dùng cùng sửa

~~~text
Thời gian      Người dùng A                Người dùng B
---------      ------------                ------------
T1             Đọc order #500
               version = 7

T2                                         Đọc order #500
                                           version = 7

T3             Đổi BOOK-01: 2 -> 3

T4                                         Đổi PEN-02: 4 -> 5

T5             Lưu aggregate
               Database nhận thay đổi A

T6                                         Lưu aggregate cũ
                                           Database nhận thay đổi B

Kết quả nếu không kiểm tra version:
    Thay đổi của A có thể bị ghi đè.
~~~

Trong một số thiết kế, B chỉ cập nhật một cột nên thay đổi của A có thể còn nguyên. Nhưng nếu B gửi một bản aggregate đầy đủ, hoặc câu UPDATE thay thế trạng thái của cả aggregate, nguy cơ mất cập nhật rất rõ. Việc ghi các collection con cũng có thể khiến thay đổi của người kia bị thay thế.

### 1.2. Vì sao một transaction chưa đủ?

`@Transactional` bảo đảm các thao tác trong transaction tuân theo ranh giới commit/rollback. Nó không tự biết rằng object trong bộ nhớ đã cũ so với dữ liệu mà một người dùng khác vừa lưu.

Một transaction có thể hoạt động hoàn toàn đúng theo SQL mà vẫn ghi đè một thay đổi đã commit trước đó.

Cần phân biệt:

| Cơ chế | Bảo vệ điều gì? |
|---|---|
| Transaction | Các câu lệnh trong một use case commit hoặc rollback cùng nhau |
| Foreign key / CHECK | Ràng buộc cấu trúc và giá trị ở database |
| Optimistic locking | Phát hiện cập nhật dựa trên version cũ |
| Pessimistic locking | Ngăn transaction khác sửa vùng dữ liệu đang bị khóa |
| Isolation level | Quy định dữ liệu transaction có thể nhìn thấy và các anomaly database phải ngăn |

Transaction là nền tảng cần thiết, nhưng để phát hiện lost update ở cấp aggregate, ứng dụng cần một cơ chế kiểm tra xung đột.

## 2. Optimistic locking trong Spring Data JDBC

Optimistic locking giả định xung đột không xảy ra thường xuyên. Ứng dụng cho phép nhiều người cùng đọc dữ liệu; khi lưu, nó kiểm tra xem dữ liệu có thay đổi kể từ lần đọc hay không.

Spring Data JDBC hỗ trợ optimistic locking bằng một thuộc tính số trên **aggregate root**, được đánh dấu `@Version`.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

import java.util.ArrayList;
import java.util.List;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    private SalesOrder() {
    }

    public static SalesOrder draft() {
        SalesOrder order = new SalesOrder();
        order.status = "DRAFT";
        return order;
    }

    public void changeStatus(String newStatus) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                    "Only draft orders can change status"
            );
        }

        this.status = newStatus;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

`@Version` cần có kiểu số, ví dụ `Long` hoặc `Integer`. Nó được đặt trên root vì version đại diện cho trạng thái của aggregate. Thay đổi một thành phần con thông qua việc lưu aggregate cũng phải được phối hợp với version của root.

Khi tạo aggregate mới, Spring Data JDBC khởi tạo version theo cơ chế new entity của framework. Với một aggregate đã tồn tại, version trong object là version mà lần đọc đã nhận được.

## 3. Spring Data JDBC kiểm tra version khi lưu như thế nào?

Giả sử database đang lưu:

~~~text
sales_orders
+----+---------+---------+
| id | status  | version |
+----+---------+---------+
| 500| DRAFT   | 7       |
+----+---------+---------+
~~~

A và B cùng đọc version 7.

Khi A lưu, Spring Data JDBC tạo UPDATE có điều kiện tương đương:

~~~sql
UPDATE sales_orders
SET status = :status,
    version = 8
WHERE id = 500
  AND version = 7;
~~~

Nếu đúng một hàng được cập nhật, thao tác đã kiểm tra version thành công. Version trong object và trong database được tăng lên.

Sau khi A commit:

~~~text
sales_orders
+----+---------+---------+
| id | status  | version |
+----+---------+---------+
| 500| ...     | 8       |
+----+---------+---------+
~~~

Khi B cố lưu object vẫn mang version 7, câu UPDATE có điều kiện tương đương:

~~~sql
UPDATE sales_orders
SET status = :status,
    version = 8
WHERE id = 500
  AND version = 7;
~~~

Database hiện có version 8, vì vậy không có hàng nào thỏa điều kiện. Spring Data JDBC phát hiện thao tác không cập nhật được hàng và ném `OptimisticLockingFailureException`.

Thay đổi của B không được lưu như một cập nhật thành công. Ứng dụng có thể thông báo conflict, tải trạng thái mới nhất và yêu cầu người dùng xem lại.

### 3.1. Trình tự version

~~~text
Database version = 7

A đọc version 7
B đọc version 7

A save:
    WHERE id = 500 AND version = 7
    UPDATE thành công
    version -> 8

B save:
    WHERE id = 500 AND version = 7
    0 row updated
    OptimisticLockingFailureException
~~~

Version hoạt động như một bộ đếm thay đổi. Ứng dụng không cần so sánh từng cột để xác định có người khác đã lưu hay chưa.

### 3.2. Version tăng khi lưu và kiểm tra khi xóa

Tài liệu Spring Data JDBC cũng mô tả optimistic locking cho thao tác delete: framework kiểm tra version khi xóa, nhưng không tăng version vì bản ghi bị xóa.

Điều này giúp ngăn một object cũ xóa aggregate đã được người khác cập nhật sau lần đọc của nó.

### 3.3. Version không phải timestamp

Không nên dùng updatedAt làm version chỉ vì timestamp có vẻ thể hiện lần cập nhật gần nhất.

Timestamp có thể có độ chính xác phụ thuộc database/driver, hai thao tác có thể nhận cùng thời điểm, và quy tắc cập nhật timestamp không nhất thiết tương ứng với mọi đường ghi. Một thuộc tính số `@Version` có semantics rõ ràng cho optimistic locking.

Có thể lưu cả version và updatedAt:

- version: phát hiện xung đột.
- updatedAt: hiển thị lịch sử thay đổi và phục vụ audit.

Hai trường này có mục đích khác nhau.

## 4. Vì sao version trên root bảo vệ cả aggregate?

Trong Spring Data JDBC, aggregate root là ranh giới persistence. Các entity được root sở hữu được lưu như một phần trạng thái aggregate.

Ví dụ:

~~~text
SalesOrder #500 (version 7)
    |
    +-- OrderLine #1
    +-- OrderLine #2
    +-- OrderLine #3
~~~

Nếu A thay đổi OrderLine #1 rồi gọi repository.save(order), thao tác lưu aggregate cũng phải kiểm tra version của root.

Nếu B đã lưu bất kỳ thay đổi nào trên cùng aggregate và version root đã tăng, A không thể tiếp tục lưu dựa trên version cũ.

Điều này quan trọng vì xung đột không chỉ xảy ra khi hai người cùng sửa một cột. Họ có thể sửa hai dòng hàng khác nhau nhưng vẫn đang thay đổi cùng một aggregate. Nếu nghiệp vụ yêu cầu toàn aggregate là một đơn vị nhất quán, version chung ở root sẽ phát hiện việc một người đã lưu trước.

### 4.1. Một aggregate, một version

| Thay đổi | Version root có cần thay đổi khi lưu aggregate? |
|---|---|
| Đổi trạng thái đơn | Có |
| Đổi địa chỉ giao hàng thuộc đơn | Có |
| Thêm dòng hàng | Có |
| Sửa số lượng dòng hàng | Có |
| Xóa dòng hàng | Có |
| Sửa entity con được lưu trong aggregate | Có |

Một entity con được sở hữu không cần một version độc lập chỉ để bảo vệ thao tác lưu aggregate thông thường. Version root bảo vệ toàn bộ lần cập nhật aggregate.

Nếu một dữ liệu được quản lý như aggregate độc lập, nó có thể có version riêng theo ranh giới của chính nó.

## 5. Xử lý OptimisticLockingFailureException

Phát hiện conflict mới chỉ là một nửa công việc. Ứng dụng cần quyết định phản hồi thế nào để người dùng không mất nội dung họ vừa nhập.

Repository:

~~~java
public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

Application service:

~~~java
@Service
public class SalesOrderService {

    private final SalesOrderRepository repository;

    public SalesOrderService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public SalesOrder saveChanges(SalesOrder order) {
        return repository.save(order);
    }
}
~~~

Khi `repository.save(order)` phát hiện version cũ, exception có thể được xử lý ở application boundary hoặc API exception handler.

Ví dụ REST API:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<ProblemDetail> handleOptimisticLocking(
            OptimisticLockingFailureException exception
    ) {
        ProblemDetail problem = ProblemDetail.forStatus(409);
        problem.setTitle("Concurrent modification");
        problem.setDetail(
                "The order has changed. Reload it and review your changes."
        );

        return ResponseEntity.status(409).body(problem);
    }
}
~~~

HTTP 409 Conflict là một lựa chọn hợp lý cho API báo rằng tài nguyên đã thay đổi và yêu cầu hiện tại không thể áp dụng trên phiên bản cũ. API có thể dùng 412 Precondition Failed khi client gửi điều kiện `If-Match` và điều kiện đó không còn đúng.

Không nên trả lỗi 500 chung chung cho một conflict đồng thời đã được nhận diện. Cũng không nên trả thành công nếu lần lưu thực tế đã bị từ chối.

### 5.1. Không nuốt exception rồi trả object cũ

Tránh mẫu:

~~~java
try {
    repository.save(order);
} catch (OptimisticLockingFailureException exception) {
    return order;
}
~~~

Cách này khiến caller tưởng dữ liệu đã được lưu. Object trả về vẫn có thể chứa trạng thái cũ và không phản ánh database.

Hãy để conflict đi đến nơi có thể chuyển nó thành phản hồi rõ ràng, hoặc chuyển thành một kết quả nghiệp vụ có trạng thái conflict.

### 5.2. Không retry mù bằng cùng object

Nếu save thất bại vì version cũ, thử gọi save lại cùng object thường vẫn thất bại. Version trong object chưa được cập nhật thành version mới nhất.

Ngay cả khi tải lại version mới và gán vào object cũ, việc đó có thể ghi đè thay đổi của người kia. Cần tải trạng thái mới, áp dụng lại ý định của người dùng trên trạng thái mới và chạy lại các domain rule trước khi lưu.

## 6. Các chiến lược giải quyết conflict

Không có một cách merge đúng cho mọi aggregate. Quyết định phụ thuộc ý nghĩa nghiệp vụ của thay đổi.

### 6.1. Yêu cầu người dùng tải lại và xác nhận

Đây là cách an toàn và dễ hiểu nhất khi hai người cùng sửa các trường có thể mâu thuẫn.

Quy trình:

1. API trả conflict.
2. Client tải aggregate mới nhất.
3. Hiển thị những trường đã thay đổi.
4. Người dùng xem lại nội dung mình nhập.
5. Người dùng quyết định áp dụng lại hoặc bỏ thay đổi.

Ví dụ A đổi trạng thái đơn sang CONFIRMED, trong khi B đổi địa chỉ giao hàng. Dù hai thuộc tính khác nhau, việc xác nhận có thể làm thay đổi quy tắc cho phép sửa địa chỉ. Hệ thống cần áp dụng lại domain rule trên trạng thái mới.

### 6.2. Merge có kiểm soát

Nếu các thay đổi độc lập theo nghiệp vụ, ứng dụng có thể merge.

Ví dụ:

- A thêm ghi chú nội bộ.
- B cập nhật số điện thoại liên hệ.
- Hai trường không có quan hệ phụ thuộc.

Một service có thể tải aggregate mới nhất, áp dụng lại ý định thay đổi từ command của người dùng và lưu lại.

~~~java
@Transactional
public void addInternalNote(
        Long orderId,
        String noteText
) {
    SalesOrder latest = repository.findById(orderId)
            .orElseThrow();

    latest.addInternalNote(noteText);

    repository.save(latest);
}
~~~

Ví dụ này thể hiện ý tưởng reapply một command lên trạng thái mới nhất. Trong thực tế, cần xử lý retry nếu một transaction khác lại lưu trước lần save mới.

Merge phải được thiết kế theo ý nghĩa nghiệp vụ. Không nên tự động hợp nhất hai giá trị khi chúng mâu thuẫn, chẳng hạn hai người cùng thay đổi giá bán hoặc trạng thái đơn.

### 6.3. Retry giới hạn cho thao tác có thể áp dụng lại an toàn

Một số thao tác có tính cộng dồn hoặc độc lập có thể được retry sau khi tải lại dữ liệu. Ví dụ một command "thêm một nhãn" có thể được áp dụng lại nếu domain model bảo đảm nhãn không bị trùng.

Ngược lại, command "đặt tổng tiền thành 500" không thể tùy tiện áp dụng lại sau khi người khác thay đổi giá.

Nếu triển khai retry:

- Giới hạn số lần thử.
- Mỗi lần phải tải lại trạng thái mới nhất.
- Chạy lại domain method và validation.
- Không dùng lại aggregate object cũ.
- Không lặp side effect bên ngoài transaction như gửi email hoặc trừ tiền.
- Chỉ retry khi command có semantics cho phép áp dụng lại.

Không retry vô hạn vì có thể tạo vòng lặp khi tài nguyên liên tục bị cập nhật.

## 7. Version qua HTTP API với ETag và If-Match

Khi người dùng sửa dữ liệu qua giao diện web, request GET và request PUT thường cách nhau vài phút. Transaction database không nên mở trong suốt thời gian người dùng chỉnh sửa. Thay vào đó, gửi version cùng representation hoặc đóng gói version thành HTTP ETag.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
ETag: "order-500-v7"
Content-Type: application/json

{
  "id": 500,
  "status": "DRAFT",
  "version": 7
}
~~~

Khi client cập nhật, gửi ETag đã nhận:

~~~http
PUT /orders/500
If-Match: "order-500-v7"
Content-Type: application/json
~~~

Server kiểm tra version trong request. Nếu version đã thay đổi, trả 412 Precondition Failed hoặc một response conflict theo hợp đồng API.

ETag giúp client không cần tự tạo logic so sánh timestamp. Nó cũng cho phép cache và HTTP conditional request phối hợp với optimistic concurrency.

Cần bảo đảm ETag đại diện đúng phiên bản của aggregate. Nếu bất kỳ thay đổi nào trong aggregate làm version root tăng, ETag từ version đó có thể được dùng làm validator cho representation aggregate.

### 7.1. Không nhận version từ client như một sự thật đáng tin

Client có thể gửi version trong JSON hoặc header, nhưng server vẫn phải dùng nó làm điều kiện kiểm tra với database. Không được tin version đó chỉ vì nó nằm trong request.

Version không phải secret và không thay thế authorization. Nó chỉ giúp phát hiện client đang thao tác trên một phiên bản cũ.

## 8. Optimistic locking và transaction boundary

Một luồng sửa aggregate thường gồm:

1. Đọc aggregate.
2. Chạy domain method.
3. Lưu aggregate.
4. Commit.

Các thao tác ghi cần nằm trong một transaction ngắn:

~~~java
@Transactional
public void changeShippingAddress(
        Long orderId,
        Address newAddress
) {
    SalesOrder order = repository.findById(orderId)
            .orElseThrow();

    order.changeShippingAddress(newAddress);

    repository.save(order);
}
~~~

Không nên mở transaction khi người dùng vừa tải trang và giữ nó cho đến lúc người dùng bấm Save. Người dùng có thể mất nhiều phút để chỉnh sửa; transaction dài giữ connection, có thể giữ lock hoặc snapshot và làm giảm khả năng phục vụ request khác.

Thay vào đó:

- GET tải aggregate và trả version.
- Client chỉnh sửa ở ngoài transaction database.
- PUT/POST bắt đầu transaction ngắn.
- Server tải hoặc nhận dữ liệu cần thiết, kiểm tra version và lưu.
- Nếu version không khớp, trả conflict.

Trong một thiết kế API, có thể gửi dữ liệu command cùng expected version. Repository vẫn phải kiểm tra version thật ở database.

### 8.1. Transaction rollback khi có conflict

Khi optimistic locking thất bại trong quá trình lưu aggregate, exception phải làm transaction ghi rollback. Nếu service đã ghi thêm audit/outbox trong cùng transaction, các thao tác đó cũng cần rollback theo.

Mặc định Spring rollback với RuntimeException và Error. Nếu application chuyển exception thành checked exception, cần cấu hình rollback phù hợp.

Không bắt exception bên trong transaction rồi tiếp tục commit những bước dở dang. Nếu đã có lỗi concurrency, hãy để transaction kết thúc và xử lý conflict ở boundary bên ngoài.

## 9. Optimistic locking khác pessimistic locking thế nào?

Optimistic locking không khóa hàng trong lúc người dùng đọc và chỉnh sửa. Nó chỉ kiểm tra version ở thời điểm ghi.

Pessimistic locking yêu cầu database khóa dữ liệu để transaction khác không thể sửa cùng vùng dữ liệu trong khoảng thời gian khóa.

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách hoạt động | Kiểm tra version khi ghi | Khóa dữ liệu trước khi sửa |
| Xung đột | Phát hiện lúc save | Transaction cạnh tranh phải chờ hoặc thất bại |
| Chi phí khi ít xung đột | Thấp | Có chi phí lock |
| Phù hợp | Nhiều lần đọc, ít xung đột | Xung đột cao hoặc cần tuần tự hóa |
| Rủi ro | Người dùng phải xử lý conflict | Deadlock, timeout, lock kéo dài |
| Phạm vi | Version của aggregate | Các hàng được khóa theo database |

### 9.1. SELECT FOR UPDATE

Với database hỗ trợ cú pháp này, có thể khóa hàng root trước khi thực hiện thay đổi:

~~~sql
SELECT id, version, status
FROM sales_orders
WHERE id = :orderId
FOR UPDATE;
~~~

Ví dụ dùng JdbcClient:

~~~java
@Transactional
public void updateOrderWithLock(Long orderId) {
    OrderLockInfo locked = jdbcClient
            .sql("""
                SELECT id, version, status
                FROM sales_orders
                WHERE id = :orderId
                FOR UPDATE
                """)
            .param("orderId", orderId)
            .query((rs, rowNum) -> new OrderLockInfo(
                    rs.getLong("id"),
                    rs.getLong("version"),
                    rs.getString("status")
            ))
            .single();

    // Kiểm tra trạng thái, tải/cập nhật aggregate,
    // sau đó lưu trong cùng transaction.
}
~~~

Kiểu kết quả có thể khai báo như sau:

~~~java
public record OrderLockInfo(
        Long id,
        Long version,
        String status
) {
}
~~~

Khóa chỉ tồn tại trong transaction. Phải dùng cùng datasource và transaction manager khi kết hợp truy vấn khóa với repository save.

Pessimistic lock phù hợp cho thao tác ngắn có xung đột cao. Không giữ lock trong lúc gọi HTTP service, gửi email, đợi người dùng hoặc xử lý một tác vụ kéo dài.

### 9.2. Khóa root có bảo vệ mọi bảng con không?

Khóa root chỉ hiệu quả nếu mọi đường ghi cạnh tranh tuân theo cùng giao thức. Nếu một đường khác cập nhật trực tiếp bảng con mà không khóa root hoặc không kiểm tra version, nó có thể không phối hợp đúng với quy tắc khóa của ứng dụng.

Đối với aggregate, một quy ước hữu ích là mọi command thay đổi aggregate đều phải kiểm tra/cập nhật version root hoặc khóa root trước khi sửa child.

## 10. Transaction isolation có thay thế @Version không?

Không nên mặc định rằng tăng isolation level sẽ thay thế được optimistic locking.

`@Transactional` mặc định dùng isolation level của transaction manager/database. Trong nhiều hệ thống, mức mặc định là READ COMMITTED. Ở mức này, hai transaction có thể cùng đọc một version cũ trước khi một transaction cập nhật; nếu câu UPDATE không có điều kiện version, thao tác sau vẫn có thể ghi đè dữ liệu theo semantics database.

Các isolation level mạnh hơn có thể ngăn một số anomaly hoặc làm một transaction thất bại, nhưng hành vi cụ thể phụ thuộc database.

Ví dụ PostgreSQL:

- READ COMMITTED: mỗi statement thấy dữ liệu đã commit trước khi statement bắt đầu; các lần đọc trong cùng transaction có thể thấy dữ liệu mới ở statement sau.
- REPEATABLE READ: transaction giữ snapshot ổn định; một số cập nhật cạnh tranh có thể làm transaction thất bại với serialization error.
- SERIALIZABLE: database phát hiện những lịch thực thi không tương đương một thứ tự tuần tự và có thể rollback một transaction.

Với PostgreSQL, REPEATABLE READ và SERIALIZABLE có thể yêu cầu ứng dụng retry toàn bộ transaction khi xảy ra serialization failure. Không nên bắt đầu retry chỉ từ câu SQL cuối; phải chạy lại toàn bộ transaction từ đầu để có snapshot mới.

### 10.1. Khi nào cần isolation mạnh hơn?

Isolation mạnh hơn hữu ích khi invariant phụ thuộc vào nhiều hàng hoặc nhiều aggregate và không thể được bảo vệ bằng version của một root.

Ví dụ: chỉ cho phép bán hàng nếu tổng số reservation và số lượng tồn kho còn lại thỏa một điều kiện. Hai transaction có thể cùng đọc tổng số lượng rồi cùng quyết định cho phép bán, dù mỗi transaction chỉ cập nhật một aggregate khác nhau.

Giải pháp có thể là:

- Đưa invariant vào một aggregate có ranh giới phù hợp.
- Dùng một hàng inventory làm điểm đồng bộ và cập nhật có điều kiện.
- Dùng constraint ở database.
- Khóa các hàng liên quan theo thứ tự nhất quán.
- Dùng SERIALIZABLE khi phù hợp và có retry logic.

`@Version` trên một order không thể tự bảo vệ invariant toàn cục giữa nhiều order và một inventory record độc lập.

## 11. Khi nào version root không đủ?

Version root bảo vệ việc lưu cùng một aggregate thông qua đường persistence có kiểm tra version. Nó không tự bảo vệ các thay đổi SQL đi vòng qua repository.

Ví dụ:

~~~sql
UPDATE order_lines
SET quantity = :quantity
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

Câu lệnh này không kiểm tra hoặc tăng version của sales_orders. Một repository save khác có thể không nhận ra child đã bị thay đổi trực tiếp.

Nếu cần direct SQL mutation, hãy phối hợp version root trong cùng transaction:

~~~sql
UPDATE sales_orders
SET version = version + 1
WHERE id = :orderId
  AND version = :expectedVersion;
~~~

Kiểm tra số hàng bị ảnh hưởng. Chỉ khi đúng một root được claim thành công mới tiếp tục thay đổi child. Nếu child update thất bại, rollback cả thao tác tăng version.

Một ví dụ Java:

~~~java
@Transactional
public void changeLineQuantity(
        Long orderId,
        Integer lineNo,
        Integer quantity,
        Long expectedVersion
) {
    int claimed = jdbcClient
            .sql("""
                UPDATE sales_orders
                SET version = version + 1
                WHERE id = :orderId
                  AND version = :expectedVersion
                """)
            .param("orderId", orderId)
            .param("expectedVersion", expectedVersion)
            .update();

    if (claimed != 1) {
        throw new OptimisticLockingFailureException(
                "The order has changed"
        );
    }

    int changed = jdbcClient
            .sql("""
                UPDATE order_lines
                SET quantity = :quantity
                WHERE order_id = :orderId
                  AND line_no = :lineNo
                """)
            .param("quantity", quantity)
            .param("orderId", orderId)
            .param("lineNo", lineNo)
            .update();

    if (changed != 1) {
        throw new IllegalArgumentException("Order line not found");
    }
}
~~~

Đây là mẫu minh họa cho direct SQL. Cần thêm các điều kiện domain như trạng thái đơn, tenant, giới hạn số lượng và các ràng buộc khác. Mọi đường ghi phải tuân theo cùng quy tắc version; nếu một đường ghi bỏ qua version, optimistic locking không còn bảo vệ toàn bộ aggregate.

## 12. Phân biệt xung đột cùng aggregate và xung đột giữa aggregate

Giả sử hai người dùng sửa hai đơn hàng khác nhau:

~~~text
SalesOrder #500, version 7
SalesOrder #501, version 3
~~~

Hai lần lưu này độc lập nếu nghiệp vụ không có invariant chung. Version của đơn #500 không nên chặn cập nhật đơn #501.

Nhưng nếu hai đơn cùng sử dụng một mã coupon chỉ được dùng một lần, hoặc cùng tiêu thụ một số lượng tồn kho giới hạn, hai aggregate có thể cạnh tranh trên một invariant chung.

| Tình huống | Version root có đủ không? |
|---|---|
| Hai người cùng sửa một đơn | Có thể phát hiện nếu cả hai lưu qua repository với @Version |
| Hai người sửa hai đơn độc lập | Không cần cùng một version |
| Hai đơn cùng đặt một SKU còn một sản phẩm | Không đủ nếu inventory là aggregate/bảng độc lập |
| Hai người cùng đổi một địa chỉ giao hàng thuộc một đơn | Version của đơn có thể phát hiện conflict |
| Hai đơn cùng dùng coupon một lần | Cần bảo vệ coupon/invariant dùng chung |
| Một job cập nhật child trực tiếp, một request save aggregate | Không đủ nếu job không phối hợp version root |

Hãy đặt concurrency control ở nơi invariant thực sự nằm. Không dùng version của một aggregate để giả định mọi dữ liệu liên quan trong hệ thống đều được khóa.

## 13. Kiểm thử lost update bằng integration test

Một unit test mock repository có thể kiểm tra application service phản ứng với exception, nhưng nó không chứng minh Spring Data JDBC tạo câu UPDATE có version predicate đúng.

Cần integration test với database test để thực hiện hai lần đọc độc lập rồi lưu lần lượt.

Ví dụ ý tưởng:

~~~java
@DataJdbcTest
class SalesOrderOptimisticLockingTest {

    @Autowired
    SalesOrderRepository repository;

    @Test
    void rejectsSavingAnAggregateLoadedBeforeAnotherSave() {
        SalesOrder initial = SalesOrder.draft();

        SalesOrder saved = repository.save(initial);

        SalesOrder first = repository.findById(saved.getId())
                .orElseThrow();

        SalesOrder second = repository.findById(saved.getId())
                .orElseThrow();

        first.changeStatus("CONFIRMED");
        repository.save(first);

        second.changeStatus("CANCELLED");

        assertThatThrownBy(() -> repository.save(second))
                .isInstanceOf(OptimisticLockingFailureException.class);
    }
}
~~~

Đây là ví dụ minh họa; constructor, factory và domain method cần khớp với model thật của dự án.

### 13.1. Các trường hợp nên kiểm tra

| Test case | Kết quả mong đợi |
|---|---|
| Lưu aggregate mới có @Version | Framework khởi tạo version |
| Đọc rồi lưu một lần | Version tăng |
| Hai object đọc cùng version, lưu object đầu | Lần lưu đầu thành công |
| Lưu object thứ hai còn version cũ | Ném OptimisticLockingFailureException |
| Cùng root nhưng thay đổi hai child khác nhau | Vẫn phát hiện conflict theo version root |
| Delete bằng object có version cũ | Thao tác bị từ chối |
| Direct SQL thay đổi child có tăng version root | Repository save bằng version cũ bị từ chối |
| Direct SQL không tăng version root | Test cho thấy đường ghi đó có thể phá cơ chế bảo vệ |
| Exception xảy ra giữa nhiều bước ghi | Transaction rollback toàn bộ |
| API nhận If-Match cũ | Trả response conflict theo hợp đồng API |

### 13.2. Kiểm thử đồng thời thực sự

Test đọc hai object rồi lưu tuần tự rất hữu ích để xác nhận version check. Để kiểm tra hành vi khi hai thread/transaction thực sự chạy đồng thời, dùng hai transaction độc lập và đồng bộ bằng CountDownLatch hoặc barrier.

Không dùng chung một transaction cho cả hai luồng vì như vậy không mô phỏng hai client độc lập.

Test cần xác nhận:

- Cả hai transaction đọc cùng version ban đầu.
- Chỉ một transaction lưu thành công.
- Transaction còn lại nhận conflict hoặc lỗi serialization theo chiến lược database.
- Dữ liệu cuối cùng phản ánh một lần cập nhật thành công, không phải trạng thái ghi đè im lặng.

## 14. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ thêm @Transactional | Hai transaction vẫn có thể ghi dựa trên cùng dữ liệu cũ | Dùng @Version hoặc concurrency strategy phù hợp |
| Đặt @Version trên child thay vì root | Không bảo vệ toàn bộ aggregate theo cơ chế root version | Đặt version trên aggregate root |
| Bắt exception rồi trả object cũ | Client tưởng cập nhật đã thành công | Trả conflict rõ ràng |
| Retry cùng object cũ | Version vẫn cũ, conflict tiếp tục xảy ra hoặc ghi đè khi tự sửa version | Reload và reapply command có kiểm soát |
| Tăng isolation level mà không hiểu database | Có thể vẫn không giải quyết đúng invariant, hoặc xuất hiện serialization failures | Hiểu semantics database và triển khai retry |
| Direct SQL sửa child mà không tăng version root | Repository save không nhận ra thay đổi ngoài luồng | Phối hợp version/lock trong cùng transaction |
| Mở transaction trong suốt thời gian người dùng chỉnh form | Giữ connection/lock quá lâu | Gửi version qua request và dùng transaction ngắn lúc save |
| Tự động merge mọi thay đổi | Có thể vi phạm domain rule | Chỉ merge khi nghiệp vụ xác định thay đổi độc lập |
| Dùng version root cho invariant nhiều aggregate | Không phát hiện xung đột trên tài nguyên dùng chung | Đồng bộ tại aggregate/row/constraint thực sự sở hữu invariant |

## 15. Quy trình thiết kế cập nhật aggregate an toàn

Khi một use case cho phép nhiều người cùng sửa aggregate:

**Bước 1 — Xác định aggregate boundary.** Những entity con nào thuộc cùng root? Thay đổi nào phải được xem là một lần sửa aggregate?

**Bước 2 — Thêm version root.** Dùng thuộc tính số với @Version trên aggregate root.

**Bước 3 — Trả version cho client.** Đưa version vào response hoặc ETag để client giữ lại phiên bản đã đọc.

**Bước 4 — Giữ transaction ghi ngắn.** Không giữ transaction trong thời gian người dùng suy nghĩ hoặc chỉnh sửa form.

**Bước 5 — Lưu qua repository.** Để Spring Data JDBC kiểm tra version và tăng version trong cùng lần save.

**Bước 6 — Xử lý conflict.** Chuyển OptimisticLockingFailureException thành response conflict; tải lại trạng thái mới khi cần.

**Bước 7 — Chọn merge/retry có chủ đích.** Chỉ retry khi có thể reapply command an toàn và chạy lại domain invariant.

**Bước 8 — Kiểm soát mọi đường ghi.** Direct SQL, batch job và công cụ ngoài phải phối hợp version/lock nếu chúng thay đổi cùng aggregate.

**Bước 9 — Bảo vệ invariant xuyên aggregate.** Dùng constraint, atomic conditional update, lock hoặc isolation phù hợp.

**Bước 10 — Kiểm thử hai người dùng.** Xác nhận không có cập nhật bị ghi đè âm thầm.

~~~text
Client A                  Application / Database                 Client B
--------                  ----------------------                 --------
GET order #500  --------> Load version 7
          <-------------- Order + version 7
                                                                  GET order #500
                                             Load version 7 <----
                                                                  <--- Order + version 7

Edit A
PUT with version 7 -----> UPDATE WHERE version = 7
                          Save success, version = 8

                                                                  Edit B
                          UPDATE WHERE version = 7 <------------- PUT with version 7
                          0 rows updated
                          OptimisticLockingFailureException
                          |
                          v
                     Return conflict
                                                                  <--- 409 Conflict

                                                                  Reload latest order
                                                                  Review / merge changes
                                                                  Submit with version 8
~~~

## 16. Bài tập tự suy luận

**Tình huống A — Hai người cùng sửa trạng thái**

A và B cùng đọc đơn version 5. A lưu thành công và version tăng lên 6. B lưu object version 5. Điều gì xảy ra khi có @Version?

**Gợi ý:** UPDATE của B có điều kiện WHERE version = 5, không cập nhật được hàng nào và Spring Data JDBC ném OptimisticLockingFailureException.

**Tình huống B — Chỉ thêm @Transactional**

Hai request cùng đọc version cũ, mỗi request chạy trong một transaction riêng. Chỉ thêm @Transactional có đủ ngăn lost update không?

**Gợi ý:** Không nhất thiết. Transaction bảo vệ tính nguyên tử; cần version check hoặc locking để phát hiện/ngăn cập nhật cạnh tranh.

**Tình huống C — Hai người sửa hai dòng hàng khác nhau**

A đổi quantity dòng 1, B đổi quantity dòng 2, cả hai thuộc cùng một aggregate. Có thể để cả hai lưu mà không conflict không?

**Gợi ý:** Theo mô hình version root, lần lưu thứ hai vẫn conflict vì cả hai đang lưu cùng aggregate. Muốn merge, phải tải trạng thái mới và áp dụng lại thay đổi độc lập theo domain rule.

**Tình huống D — Retry tự động**

Sau conflict, service tải aggregate mới rồi lưu lại object cũ với version mới. Cách này có an toàn không?

**Gợi ý:** Không tự động an toàn. Object cũ có thể ghi đè thay đổi mới. Phải reapply ý định command trên aggregate mới và kiểm tra lại invariant.

**Tình huống E — Direct SQL**

Một batch job cập nhật order_lines trực tiếp. Repository save của aggregate có tự biết child đã thay đổi không?

**Gợi ý:** Không nếu batch job không phối hợp version root. Cần cập nhật version hoặc khóa root theo cùng giao thức.

**Tình huống F — Hai aggregate cùng dùng inventory**

Hai đơn hàng khác nhau cùng đặt sản phẩm cuối cùng. @Version của từng đơn có đủ ngăn oversell không?

**Gợi ý:** Không. Cần concurrency control tại inventory hoặc một invariant chung, ví dụ atomic update có điều kiện trên số lượng tồn.

## 17. Ghi nhớ

| Khái niệm | Vai trò |
|---|---|
| Lost update | Cập nhật đã commit bị lần lưu dựa trên dữ liệu cũ ghi đè |
| Optimistic locking | Kiểm tra version khi ghi, không khóa trong thời gian đọc |
| @Version | Đánh dấu thuộc tính version số trên aggregate root |
| OptimisticLockingFailureException | Báo thao tác lưu/xóa không khớp version hiện tại |
| Aggregate root version | Bảo vệ lần lưu aggregate, kể cả thay đổi entity con qua repository |
| @Transactional | Gom thao tác vào transaction; không tự thay thế version check |
| Pessimistic locking | Khóa dữ liệu để transaction cạnh tranh phải chờ |
| SELECT FOR UPDATE | Ví dụ khóa hàng trong transaction |
| ETag / If-Match | Chuyển version đã đọc qua HTTP để phát hiện request cũ |
| Conflict handling | Reload, review, merge hoặc retry command có kiểm soát |
| Direct SQL | Phải phối hợp version/lock nếu thay đổi cùng aggregate |
| Cross-aggregate invariant | Cần đồng bộ ở tài nguyên hoặc ranh giới thực sự dùng chung |

**Lost update xảy ra khi một người lưu trạng thái dựa trên dữ liệu cũ sau khi người khác đã cập nhật cùng aggregate.** Spring Data JDBC giải quyết trường hợp này bằng optimistic locking qua @Version trên aggregate root: lần lưu đầu tăng version, lần lưu dùng version cũ bị từ chối. Application cần phản hồi conflict rõ ràng và chỉ merge/retry khi có thể áp dụng lại ý định người dùng một cách an toàn. Với SQL trực tiếp hoặc invariant dùng chung nhiều aggregate, hãy bổ sung cơ chế version, khóa hoặc constraint tại đúng nơi dữ liệu được thay đổi.

## Tài liệu tham khảo

- [Spring Data Relational — Persisting Entities / Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): @Version, kiểm tra version khi update/delete và OptimisticLockingFailureException.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): isolation, propagation và rollback behavior.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): semantics của Read Committed, Repeatable Read, Serializable và serialization failures.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row-level locks và SELECT FOR UPDATE.
- [HTTP Semantics — Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests): ETag, If-Match và conditional update requests.

