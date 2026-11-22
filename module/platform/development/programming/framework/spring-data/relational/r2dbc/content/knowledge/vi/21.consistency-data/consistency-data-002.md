# Chọn mức cô lập theo bất biến nghiệp vụ

Transaction isolation quyết định những thay đổi đồng thời mà một transaction có thể quan sát và cách database phối hợp các transaction đang chạy. Với Spring Data R2DBC, mức cô lập được cấu hình ở transaction reactive thông qua Spring transaction manager và cuối cùng phụ thuộc khả năng của database cùng R2DBC driver.

Không nên chọn `SERIALIZABLE` cho mọi thao tác chỉ vì muốn dữ liệu “an toàn”, cũng không nên luôn giữ mức mặc định mà không hiểu bất biến nghiệp vụ. Hãy xác định điều gì phải luôn đúng, xem các thao tác đồng thời có thể phá vỡ điều kiện đó ra sao, rồi chọn cơ chế phù hợp: constraint ở database, câu lệnh cập nhật nguyên tử, optimistic locking, khóa hàng hoặc mức isolation cao hơn.

## 1. Bắt đầu từ bất biến nghiệp vụ

Bất biến nghiệp vụ là điều kiện phải đúng trước và sau mọi giao dịch hợp lệ. Ví dụ:

- Số lượng hàng tồn không được âm.
- Một email chỉ thuộc về một tài khoản trong cùng tenant.
- Một phòng chỉ có tối đa một đặt chỗ đang hiệu lực trong cùng khung giờ.
- Tổng tiền chuyển đi phải bằng tổng tiền chuyển đến.
- Trong một nhóm trực, luôn phải có ít nhất một người đang trực.
- Một đơn hàng không thể vừa được xác nhận thanh toán vừa bị hủy theo hai luồng đồng thời.

Isolation chỉ là một phần của giải pháp. Nhiều bất biến được bảo vệ tốt hơn bằng constraint hoặc một câu lệnh SQL nguyên tử. Ví dụ, `CHECK (available >= 0)` và câu `UPDATE ... WHERE available >= :quantity` có thể bảo vệ tồn kho trực tiếp ở database mà không cần dùng `SERIALIZABLE` cho mọi thao tác.

Trước khi chọn mức cô lập, hãy trả lời:

1. Điều kiện nào phải luôn đúng?
2. Những transaction nào có thể đọc hoặc ghi cùng hàng, cùng tập hàng hoặc cùng một phạm vi logic?
3. Một transaction có cần đọc lại dữ liệu và phải thấy đúng snapshot ban đầu không?
4. Nhiều transaction có thể cùng kiểm tra một điều kiện rồi cùng cập nhật các hàng khác nhau không?
5. Database có constraint hoặc thao tác nguyên tử để bảo vệ điều kiện đó không?
6. Nếu database từ chối transaction do xung đột, ứng dụng có thể retry an toàn không?

## 2. Các hiện tượng khi transaction chạy đồng thời

Các mức isolation thường được giải thích qua một số anomaly (hiện tượng bất thường). Chúng giúp xác định điều gì có thể xảy ra khi hai transaction chạy xen kẽ.

### 2.1 Dirty read

Dirty read xảy ra khi transaction A đọc dữ liệu mà transaction B đã thay đổi nhưng chưa commit. Nếu B rollback, A đã sử dụng một giá trị chưa bao giờ trở thành dữ liệu đã commit.

Ví dụ: B giảm số dư từ 100 xuống 20 nhưng chưa commit. A đọc được 20 và quyết định từ chối một khoản chi. Sau đó B rollback, số dư thực tế trở lại 100. Quyết định của A dựa trên dữ liệu tạm thời.

`READ_UNCOMMITTED` theo mô hình SQL cho phép dirty read. Nhiều database không thực sự cung cấp dirty read; chẳng hạn PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`. Phải xem hành vi của database mục tiêu, không chỉ dựa vào tên mức isolation.

### 2.2 Non-repeatable read

Non-repeatable read xảy ra khi một transaction đọc cùng một hàng hai lần nhưng nhận hai giá trị khác nhau vì transaction khác đã commit cập nhật giữa hai lần đọc.

Ví dụ: A đọc trạng thái đơn hàng là `PENDING`. B cập nhật thành `PAID` và commit. Khi A đọc lại cùng hàng, A thấy `PAID`. Nếu nghiệp vụ cần các lần đọc trong transaction nhìn thấy cùng một phiên bản dữ liệu, cần mức isolation hoặc chiến lược snapshot phù hợp.

### 2.3 Phantom read

Phantom read xảy ra khi một transaction chạy lại cùng một điều kiện truy vấn và thấy tập hàng thay đổi vì transaction khác đã thêm, xóa hoặc thay đổi hàng khiến nó thỏa điều kiện đó.

Ví dụ: A đếm số đặt chỗ của phòng trong một khoảng thời gian và nhận 0. B thêm một đặt chỗ phù hợp rồi commit. A chạy lại cùng truy vấn và nhận 1. Hàng mới xuất hiện trong tập kết quả là phantom.

### 2.4 Lost update

Lost update xảy ra khi hai transaction cùng đọc một giá trị, tự tính giá trị mới rồi ghi đè lẫn nhau. Ví dụ số dư là 100; A tính 100 + 10 = 110, B tính 100 - 20 = 80. Nếu cả hai ghi giá trị tuyệt đối mà không có kiểm soát xung đột, kết quả cuối có thể là 110 hoặc 80 thay vì 90.

Không phải mọi database hoặc mọi mức isolation đều xử lý lost update giống nhau. Có thể tránh bằng phép cập nhật tương đối nguyên tử (`balance = balance + :delta`), optimistic version check hoặc khóa hàng tùy nghiệp vụ.

### 2.5 Write skew

Write skew có thể xảy ra khi hai transaction cùng đọc một tập dữ liệu thỏa bất biến, sau đó mỗi transaction cập nhật một hàng khác nhau. Vì chúng không ghi đè cùng một hàng nên cơ chế phát hiện xung đột theo từng hàng có thể không ngăn được vi phạm ở cấp toàn tập.

Ví dụ có hai bác sĩ đang trực. Bất biến là luôn có ít nhất một người trực. A đọc thấy cả bác sĩ 1 và 2 đều trực, rồi tắt lịch của bác sĩ 1. B cũng đọc snapshot có cả hai người trực, rồi tắt lịch của bác sĩ 2. Nếu cả hai commit, không còn ai trực dù mỗi transaction riêng lẻ đều thấy một người còn lại.

Write skew là lý do cần hiểu bất biến ở cấp nhiều hàng. `@Version` trên từng hàng không tự giải quyết mọi xung đột giữa các hàng khác nhau. Có thể cần `SERIALIZABLE`, khóa một hàng đại diện cho nhóm, hoặc thiết kế lại mô hình dữ liệu để database constraint có thể bảo vệ điều kiện.

## 3. Các mức isolation phổ biến

Spring định nghĩa các mức isolation theo `TransactionDefinition`:

| Mức isolation | Dirty read | Non-repeatable read | Phantom read | Ý nghĩa khái quát |
|---|---|---|---|---|
| `READ_UNCOMMITTED` | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra | Cho phép đọc dữ liệu chưa commit theo chuẩn; database có thể nâng lên mức cao hơn. |
| `READ_COMMITTED` | Không | Có thể xảy ra | Có thể xảy ra | Mỗi câu lệnh chỉ đọc dữ liệu đã commit tại thời điểm phù hợp với database. |
| `REPEATABLE_READ` | Không | Không theo định nghĩa chuẩn | Có thể xảy ra theo định nghĩa chuẩn | Giữ ổn định dữ liệu đã đọc; cách xử lý phantom phụ thuộc database. |
| `SERIALIZABLE` | Không | Không | Không theo mô hình chuẩn | Kết quả tương đương một thứ tự thực thi tuần tự; transaction có thể bị hủy do xung đột. |

Bảng này mô tả ngữ nghĩa theo chuẩn SQL ở mức khái quát. Database có thể triển khai bằng lock, MVCC hoặc cơ chế khác, và một số hệ thống mạnh hơn mức tối thiểu của chuẩn. Ví dụ PostgreSQL dùng snapshot isolation cho `REPEATABLE READ`, ngăn phantom theo cách triển khai của nó nhưng vẫn có thể có serialization anomaly; `SERIALIZABLE` của PostgreSQL dùng Serializable Snapshot Isolation và có thể hủy transaction cần retry.

`DEFAULT` không phải một mức cô lập độc lập trong bảng anomaly. Nó yêu cầu Spring dùng mức mặc định do transaction manager/database cấu hình. Hãy kiểm tra mặc định của database thay vì giả định mọi hệ thống đều là `READ_COMMITTED`.

## 4. Chọn mức theo loại bất biến

Một số định hướng thường gặp:

| Bất biến hoặc nhu cầu | Cơ chế nên cân nhắc trước | Isolation thường phù hợp |
|---|---|---|
| Không cho phép email trùng | Unique constraint ghép theo tenant và email | Thường không cần nâng isolation chỉ để bảo đảm duy nhất. |
| Tồn kho không âm | `CHECK` constraint và `UPDATE ... WHERE available >= :qty` | Thường có thể dùng mức mặc định/`READ_COMMITTED` nếu thao tác nguyên tử. |
| Cập nhật cùng một hàng, cần phát hiện ghi đè | `@Version` hoặc cập nhật có điều kiện theo version | Mức mặc định có thể đủ nếu xử lý conflict. |
| Đọc cùng một snapshot trong nhiều câu lệnh | Snapshot/transaction isolation phù hợp | `REPEATABLE_READ` hoặc mức tương đương theo database. |
| Quy tắc phụ thuộc nhiều hàng/phạm vi, có nguy cơ write skew | Constraint, khóa phạm vi hoặc transaction tuần tự | Có thể cần `SERIALIZABLE`. |
| Đọc báo cáo không yêu cầu snapshot nhất quán giữa các câu lệnh | Query riêng hoặc read model | Thường dùng mặc định/`READ_COMMITTED`. |

Đây là điểm xuất phát để phân tích, không phải bảng thay thế tài liệu database. Cần xem SQL cụ thể, index, constraint, transaction pattern và semantics của hệ quản trị đang chạy.

## 5. Cấu hình isolation trong Spring Data R2DBC

Spring Data R2DBC sử dụng reactive transaction manager, thường là `R2dbcTransactionManager`, để quản lý transaction cho `ConnectionFactory`. Có thể khai báo mức isolation bằng annotation `@Transactional` trên phương thức trả về publisher reactive.

Ví dụ yêu cầu `READ_COMMITTED`:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional(isolation = Isolation.READ_COMMITTED)
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus(OrderStatus.CONFIRMED);
            return orderRepository.save(order);
        });
}
```

Với `@Transactional`, cần bảo đảm phương thức được gọi qua Spring proxy theo cách cấu hình transaction của ứng dụng. Self-invocation trong cùng bean thường không đi qua proxy. Phương thức reactive phải trả về `Mono` hoặc `Flux` để transaction bao quanh vòng đời publisher; không gọi `subscribe()` hoặc `block()` bên trong để tách thao tác khỏi transaction context.

Nếu không khai báo `isolation`, Spring dùng `ISOLATION_DEFAULT`, tức mức mặc định của transaction manager/database. Không nên gán `SERIALIZABLE` ở mọi service nếu chỉ một vài thao tác có bất biến cần mức này.

### 5.1 Cấu hình bằng TransactionalOperator

Khi muốn điều khiển ranh giới transaction trực tiếp trong reactive chain, có thể tạo `TransactionalOperator` với `TransactionDefinition`:

```java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;

DefaultTransactionDefinition definition = new DefaultTransactionDefinition();
definition.setIsolationLevel(TransactionDefinition.ISOLATION_SERIALIZABLE);

TransactionalOperator serializableOperator =
    TransactionalOperator.create(transactionManager, definition);

Mono<Booking> result = serializableOperator.transactional(
    createBookingAndCheckCapacity(request)
);
```

`DefaultTransactionDefinition` cho phép đặt isolation, timeout và propagation. Có thể tạo operator riêng cho một use case cần isolation khác. Với cấu hình có nhiều `ConnectionFactory`, phải chọn đúng `ReactiveTransactionManager` cho database mà publisher sử dụng.

Mức isolation được yêu cầu phải được driver và database hỗ trợ. Nếu không hỗ trợ, transaction có thể thất bại khi bắt đầu hoặc khi thiết lập isolation. Một số database ánh xạ nhiều mức về cùng hành vi. Hãy kiểm tra tài liệu driver và xác minh bằng kiểm thử tích hợp.

## 6. Ví dụ: bảo vệ tồn kho bằng câu lệnh nguyên tử

Giả sử tồn kho không được âm. Cách dễ sai là đọc số lượng, kiểm tra ở Java rồi cập nhật:

```java
repository.findById(productId)
    .flatMap(product -> {
        if (product.getAvailable() >= quantity) {
            product.setAvailable(product.getAvailable() - quantity);
            return repository.save(product);
        }
        return Mono.error(new InsufficientStockException());
    });
```

Hai request có thể cùng đọc tồn kho 5 và mỗi request muốn mua 4. Cả hai đều thấy đủ hàng rồi cùng tính giá trị mới là 1. Nếu cập nhật không có kiểm soát cạnh tranh, kết quả có thể không phản ánh hai lần bán.

Một cách phù hợp hơn là để database kiểm tra điều kiện và cập nhật trong cùng một câu lệnh:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
```

Sau đó kiểm tra số hàng bị ảnh hưởng:

```java
Mono<Void> reserveStock(Long productId, int quantity) {
    if (quantity <= 0) {
        return Mono.error(new IllegalArgumentException("quantity must be positive"));
    }

    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity
            WHERE product_id = :productId
              AND available >= :quantity
            """)
        .bind("quantity", quantity)
        .bind("productId", productId)
        .fetch()
        .rowsUpdated()
        .flatMap(updated -> updated == 1
            ? Mono.empty()
            : Mono.error(new InsufficientStockException()));
}
```

Với câu lệnh này, hai request cạnh tranh sẽ được database tuần tự hóa trên hàng cần cập nhật. Chỉ request còn đủ điều kiện mới cập nhật được. Nên bổ sung `CHECK (available >= 0)` để bảo vệ bất biến ngay tại schema. Cách này thường đơn giản và hiệu quả hơn việc nâng toàn bộ use case lên `SERIALIZABLE` chỉ để trừ tồn kho.

## 7. Ví dụ: cập nhật có điều kiện bằng optimistic locking

Nếu nhiều người có thể chỉnh sửa cùng một entity, có thể dùng `@Version` để phát hiện một transaction đã thay đổi hàng sau khi transaction khác đọc nó:

```java
@Table("product")
public class Product {
    @Id
    private Long id;

    private String name;

    @Version
    private Long version;
}
```

Spring Data Relational có thể đưa version vào điều kiện cập nhật và tăng version khi lưu entity. Nếu số hàng cập nhật không như mong đợi vì version đã thay đổi, thao tác có thể phát `OptimisticLockingFailureException`.

Optimistic locking phù hợp khi xung đột không thường xuyên và ứng dụng có thể yêu cầu người dùng tải lại hoặc retry nghiệp vụ. Nó bảo vệ cùng hàng được version hóa. Nó không tự bảo vệ bất biến liên quan đến nhiều hàng khác nhau, chẳng hạn tổng số ghế đã đặt không vượt sức chứa nếu mỗi request cập nhật một hàng đặt chỗ riêng.

Với câu SQL tự viết, không giả định `@Version` tự được thêm vào câu lệnh. Cần tự đưa `version = :expectedVersion` vào `WHERE`, tăng version và kiểm tra `rowsUpdated()`.

## 8. Ví dụ: khóa hàng khi cần đọc rồi mới quyết định

Một số nghiệp vụ cần đọc trạng thái hiện tại, kiểm tra nhiều điều kiện rồi cập nhật. Nếu các transaction khác không được thay đổi hàng trong khoảng đó, có thể dùng pessimistic row lock nếu database hỗ trợ.

Ví dụ SQL:

```sql
SELECT id, available
FROM inventory
WHERE product_id = :productId
FOR UPDATE;
```

`FOR UPDATE` yêu cầu database khóa hàng được chọn đến khi transaction kết thúc theo semantics của database. Sau khi đọc và kiểm tra, transaction cập nhật hàng rồi commit. Các transaction khác cần khóa xung đột có thể phải chờ.

Lệnh khóa phải chạy trong transaction đang hoạt động. Nếu select và update chạy trên hai connection/transaction khác nhau, khóa không bảo vệ được đoạn xử lý. Hãy giữ transaction ngắn, khóa theo thứ tự ổn định khi cần nhiều hàng để giảm nguy cơ deadlock, và kiểm tra cú pháp/khả năng khóa của database cụ thể.

R2DBC không có một annotation portable tương đương mọi cơ chế pessimistic locking của JPA. Với Spring Data R2DBC, thường thể hiện bằng SQL tường minh qua `DatabaseClient` hoặc cơ chế truy vấn được driver/database hỗ trợ.

## 9. Ví dụ: bất biến trải trên nhiều hàng

Giả sử một phòng có giới hạn 10 chỗ. Mỗi booking tạo một hàng riêng. Hai transaction cùng đếm số booking hiện có là 9, rồi mỗi transaction thêm một booking. Nếu chỉ kiểm tra bằng `COUNT(*)` trước khi insert, cả hai có thể cùng thấy còn một chỗ và cùng thêm, dẫn đến 11 booking.

Có một số cách thiết kế:

- Dùng một hàng `room_capacity` làm bộ đếm và cập nhật nguyên tử có điều kiện: `UPDATE room_capacity SET reserved = reserved + 1 WHERE room_id = :id AND reserved < capacity`. Mỗi booking chỉ được tạo nếu cập nhật thành công; cả hai thao tác nằm trong một transaction.
- Khóa hàng phòng bằng `SELECT ... FOR UPDATE`, kiểm tra số chỗ rồi tạo booking trong cùng transaction.
- Dùng `SERIALIZABLE` nếu bất biến được kiểm tra qua một tập hàng và không có constraint/câu lệnh nguyên tử phù hợp, đồng thời xử lý serialization failure bằng retry.
- Thiết kế constraint hoặc mô hình dữ liệu khác nếu database có khả năng biểu diễn trực tiếp giới hạn cần bảo vệ.

Đếm rồi insert dưới `READ_COMMITTED` không đủ để bảo đảm giới hạn khi có cạnh tranh. Tăng isolation có thể là giải pháp, nhưng một hàng bộ đếm được cập nhật nguyên tử thường dễ quan sát và dễ kiểm soát hơn.

## 10. Khi nào cần SERIALIZABLE?

`SERIALIZABLE` phù hợp khi kết quả đúng phụ thuộc vào một chuỗi đọc/ghi trên nhiều hàng hoặc một phạm vi dữ liệu, và không thể bảo vệ đầy đủ bằng constraint, atomic update hay khóa tường minh đơn giản.

Ví dụ, quy tắc “ít nhất một bác sĩ trong nhóm phải trực” phụ thuộc vào trạng thái của nhiều hàng. Nếu hai transaction đồng thời đọc cùng snapshot rồi cập nhật hai hàng khác nhau, có thể xuất hiện write skew. `SERIALIZABLE` yêu cầu database bảo đảm kết quả tương đương một thứ tự tuần tự; một transaction xung đột có thể bị hủy thay vì cho cả hai commit.

Điều đó có nghĩa `SERIALIZABLE` không chỉ “chờ để mọi thứ chạy lần lượt”. Database có thể dùng lock hoặc phát hiện xung đột và trả lỗi serialization. Ứng dụng phải sẵn sàng retry toàn bộ transaction khi gặp lỗi serialization/deadlock phù hợp.

Trước khi chọn `SERIALIZABLE`, hãy đánh giá:

- Tần suất các transaction đụng cùng dữ liệu.
- Khối lượng đọc và phạm vi predicate của truy vấn.
- Chi phí retry khi xung đột.
- Hành vi isolation thực tế của database.
- Khả năng giữ các side effect bên ngoài transaction hoặc phát sau commit.

## 11. Retry khi transaction bị hủy do xung đột

Ở mức `SERIALIZABLE`, database có thể từ chối commit một transaction để bảo đảm thứ tự tuần tự. Đây không nhất thiết là lỗi lập trình; nó có thể là kết quả bình thường khi hai giao dịch cạnh tranh. Có thể retry toàn bộ transaction với số lần giới hạn và backoff.

Ví dụ minh họa:

```java
Mono<Booking> createWithRetry(BookingRequest request) {
    Mono<Booking> oneAttempt = transactionalOperator.transactional(
        createBookingAndValidateCapacity(request)
    );

    return oneAttempt.retryWhen(
        Retry.backoff(3, Duration.ofMillis(100))
            .filter(this::isSerializationFailure)
    );
}
```

`isSerializationFailure` phải nhận diện đúng lỗi do driver/database phát ra hoặc exception đã được Spring dịch chuyển. Mã lỗi và kiểu exception cụ thể khác nhau giữa PostgreSQL, MySQL, SQL Server và các driver. Không retry mọi `DataAccessException` vì lỗi constraint, dữ liệu không hợp lệ hoặc lỗi cú pháp không tự hết khi thử lại.

Đặt retry bên ngoài publisher transaction để mỗi lần subscribe lại có một transaction mới. Retry chỉ an toàn nếu toàn bộ thao tác có thể thực hiện lại. Không gửi email, gọi API thanh toán hoặc publish message trực tiếp bên trong đoạn có thể retry; dùng outbox hoặc phát side effect sau commit để tránh thực hiện lặp.

## 12. Isolation không thay thế constraint

Ngay cả khi service dùng `SERIALIZABLE`, constraint vẫn là nơi quan trọng để bảo vệ những điều kiện dữ liệu mà database có thể biểu diễn:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0),
    CONSTRAINT uk_account_tenant_email UNIQUE (tenant_id, email)
);
```

Trong ví dụ:

- `PRIMARY KEY` bảo đảm định danh duy nhất.
- `UNIQUE (tenant_id, email)` bảo đảm email không trùng trong một tenant.
- `CHECK (balance >= 0)` bảo đảm số dư không âm.

Các constraint này bảo vệ dữ liệu bất kể thay đổi đến từ Spring Data R2DBC, một ứng dụng khác, script vận hành hay batch import. Isolation chỉ kiểm soát cách các transaction tương tác; nó không thay thế kiểm tra tính hợp lệ cuối cùng của từng hàng.

## 13. Cẩn trọng với transaction lồng nhau và propagation

Một phương thức `@Transactional` có thể gọi một phương thức transaction khác. Với propagation `REQUIRED` mặc định, thao tác thường tham gia transaction đang tồn tại thay vì tạo transaction độc lập. Vì vậy, khai báo isolation khác trên một phương thức được gọi bên trong transaction hiện tại không nhất thiết tạo ra transaction mới với mức isolation mới.

Nếu một use case thực sự cần transaction độc lập, `REQUIRES_NEW` có semantics khác và có thể cần connection bổ sung. Không dùng nó chỉ để “nâng isolation” cho một đoạn code mà chưa xem xét ảnh hưởng đến tính nguyên tử và pool connection.

Với `TransactionalOperator`, vị trí bọc publisher quyết định phạm vi transaction. Khi operator được áp dụng bên trong một transaction hiện hữu, hành vi phụ thuộc propagation đã cấu hình. Hãy thiết kế ranh giới rõ ràng và tránh tạo transaction lồng nhau không cần thiết.

## 14. Lựa chọn theo database và R2DBC driver

Isolation là khái niệm chuẩn nhưng chi tiết triển khai khác nhau:

- Database có thể hỗ trợ một số mức isolation nhưng ánh xạ mức khác về mức gần nhất.
- `REPEATABLE_READ` có thể ngăn phantom trong một database nhưng không bảo đảm cùng hành vi ở database khác.
- `SERIALIZABLE` có thể dùng khóa hoặc MVCC/SSI, nên mức độ chờ và loại lỗi xung đột khác nhau.
- R2DBC driver phải chuyển yêu cầu isolation từ Spring sang database. Khả năng thiết lập isolation có thể bị giới hạn bởi driver hoặc trạng thái connection.
- Một số database chỉ cho phép thay đổi isolation ở thời điểm bắt đầu transaction hoặc có quy tắc riêng cho transaction read-only.

Khi chuyển database hoặc nâng phiên bản driver, cần chạy lại kiểm thử tích hợp về cạnh tranh và isolation. Không chỉ kiểm tra rằng ứng dụng khởi động được hoặc annotation không phát lỗi.

## 15. Kiểm thử bất biến dưới cạnh tranh

Một unit test chạy tuần tự không thể chứng minh bất biến được bảo vệ khi hai transaction chạy đồng thời. Nên có integration test với database/driver mục tiêu, dùng hai luồng hoặc hai connection độc lập để tạo tình huống cạnh tranh.

Ví dụ các tình huống cần kiểm tra:

| Bất biến | Kịch bản cạnh tranh | Kết quả mong đợi |
|---|---|---|
| Tồn kho không âm | Hai request cùng mua số lượng lớn hơn tổng tồn | Chỉ request đủ điều kiện thành công; `available` không âm. |
| Email duy nhất | Hai transaction cùng insert cùng tenant/email | Một insert thành công, insert còn lại nhận lỗi unique constraint. |
| Optimistic locking | Hai transaction đọc cùng version rồi cùng lưu | Một cập nhật thành công; cập nhật cũ nhận conflict. |
| Giới hạn sức chứa | Hai transaction cùng đặt chỗ cuối cùng | Chỉ một booking được chấp nhận. |
| Bất biến nhiều hàng | Hai transaction cập nhật các hàng khác nhau nhưng cùng vi phạm điều kiện tổng thể | Database ngăn commit đồng thời hoặc ứng dụng dùng khóa/constraint phù hợp. |

Test cần đồng bộ điểm bắt đầu để hai transaction thực sự cạnh tranh, kiểm tra số hàng cuối cùng và trạng thái lỗi. Dùng mock repository chỉ kiểm tra được logic xử lý publisher, không chứng minh semantics isolation của database.

## 16. Quy trình chọn mức cô lập

Có thể áp dụng trình tự sau cho từng use case:

1. Viết bất biến nghiệp vụ dưới dạng điều kiện có thể kiểm tra.
2. Xác định các hàng và phạm vi dữ liệu mà nhiều transaction có thể đọc/ghi đồng thời.
3. Kiểm tra có thể bảo vệ bằng primary key, unique, foreign key hoặc check constraint hay không.
4. Kiểm tra có thể chuyển logic đọc-sửa-ghi thành một câu lệnh cập nhật nguyên tử hay không.
5. Nếu xung đột cùng một hàng, cân nhắc `@Version` hoặc `SELECT ... FOR UPDATE`.
6. Nếu bất biến trải trên nhiều hàng và có nguy cơ write skew, đánh giá `SERIALIZABLE` hoặc khóa một hàng đại diện cho phạm vi.
7. Cấu hình isolation tại ranh giới transaction reactive phù hợp và xác minh driver/database hỗ trợ.
8. Xác định lỗi xung đột có thể retry không; retry toàn bộ transaction và giữ side effect bên ngoài khỏi đoạn có thể lặp.
9. Viết integration test chạy đồng thời trên database mục tiêu và theo dõi deadlock, serialization failure, lock wait cùng retry rate.

Mức isolation nên được chọn theo bất biến cần bảo vệ và anomaly có thể phá vỡ bất biến đó. Dùng constraint và thao tác nguyên tử cho điều kiện có thể biểu diễn trực tiếp; dùng optimistic hoặc pessimistic locking khi cần kiểm soát xung đột cụ thể; chọn `SERIALIZABLE` khi quy tắc phụ thuộc vào nhiều hàng hoặc phạm vi đọc/ghi và không có cơ chế đơn giản hơn đủ bảo vệ. Cuối cùng, luôn kiểm chứng hành vi trên database và R2DBC driver thực tế vì tên isolation giống nhau không bảo đảm mọi hệ quản trị có cùng cách triển khai.
