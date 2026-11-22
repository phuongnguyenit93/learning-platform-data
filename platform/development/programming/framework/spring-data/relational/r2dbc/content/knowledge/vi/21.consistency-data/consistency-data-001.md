# Các hiện tượng mất cập nhật, đọc không lặp lại và đọc bóng

Khi nhiều request hoặc transaction cùng đọc và thay đổi dữ liệu, thứ tự thực thi có thể làm kết quả cuối khác với điều nghiệp vụ mong đợi. Ba hiện tượng thường gặp là **mất cập nhật (lost update)**, **đọc không lặp lại (non-repeatable read)** và **đọc bóng (phantom read)**.

Các hiện tượng này liên quan đến cách database cô lập những transaction đồng thời. Trong Spring Data R2DBC, ứng dụng có thể kiểm soát chúng bằng transaction reactive, isolation level, optimistic locking với `@Version`, câu lệnh cập nhật nguyên tử hoặc khóa tường minh khi database và driver hỗ trợ.

Không có một isolation level duy nhất luôn phù hợp cho mọi thao tác. Hãy xác định dữ liệu nào có thể bị cạnh tranh, hậu quả nếu đọc dữ liệu thay đổi giữa chừng, và mức độ khóa hoặc retry mà hệ thống có thể chấp nhận.

## 1. Vì sao transaction đồng thời có thể gây bất thường?

Một transaction là một đơn vị công việc đọc và/hoặc ghi dữ liệu. Khi nhiều transaction chạy cùng lúc, database có thể xen kẽ các câu lệnh của chúng để tăng throughput.

Ví dụ, hai request cùng cập nhật số dư tài khoản. Mỗi request có thể đọc cùng một giá trị ban đầu rồi tính toán kết quả riêng. Nếu cả hai ghi lại giá trị dựa trên dữ liệu cũ, một thay đổi có thể bị ghi đè.

Các transaction cần những đảm bảo nhất quán nhất định. Database cung cấp chúng qua isolation level, khóa, MVCC (Multi-Version Concurrency Control), kiểm tra xung đột và cơ chế commit/rollback.

### 1.1. Một số thuật ngữ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Transaction | Nhóm thao tác database được quản lý như một đơn vị commit hoặc rollback |
| Concurrent transactions | Các transaction có thời gian thực thi chồng lấn nhau |
| Isolation level | Mức độ database ngăn một transaction quan sát ảnh hưởng chưa hoàn tất hoặc thay đổi của transaction khác |
| MVCC | Cơ chế quản lý nhiều phiên bản dữ liệu để transaction có thể đọc một snapshot phù hợp |
| Lock | Cơ chế phối hợp quyền đọc/ghi trên hàng, khóa hoặc phạm vi dữ liệu |
| Optimistic locking | Phát hiện xung đột khi ghi bằng version hoặc điều kiện so sánh, thay vì khóa độc quyền từ đầu |
| Pessimistic locking | Chủ động khóa dữ liệu để hạn chế transaction khác thay đổi trong thời gian thao tác |

Isolation level là một phần của hợp đồng transaction. Cơ chế triển khai và mức đảm bảo thực tế phụ thuộc hệ quản trị database.

## 2. Mất cập nhật (Lost Update)

Mất cập nhật xảy ra khi hai transaction cùng đọc một phiên bản dữ liệu, tính toán thay đổi riêng, rồi lần ghi sau ghi đè kết quả của lần ghi trước. Cả hai thao tác có thể đều báo thành công, nhưng một thay đổi nghiệp vụ không còn trong giá trị cuối.

### 2.1. Ví dụ số dư tài khoản

Giả sử tài khoản có số dư ban đầu là 100. Hai request đồng thời:

- Transaction T1 rút 20.
- Transaction T2 rút 10.

Kết quả đúng nếu cả hai giao dịch được chấp nhận là 70. Nhưng cách đọc-sửa-ghi không an toàn có thể tạo lịch thực thi sau:

| Thứ tự | Transaction T1 | Transaction T2 | Số dư trong database |
| ---: | --- | --- | ---: |
| 1 | Đọc số dư = 100 | | 100 |
| 2 | | Đọc số dư = 100 | 100 |
| 3 | Tính 100 - 20 = 80 | | 100 |
| 4 | | Tính 100 - 10 = 90 | 100 |
| 5 | Ghi 80 | | 80 |
| 6 | | Ghi 90 | 90 |

Kết quả cuối là 90. Thay đổi rút 20 của T1 đã bị T2 ghi đè. Đây là lost update.

### 2.2. Code đọc-sửa-ghi có nguy cơ

Một service có thể được viết như sau:

```java
@Transactional
public Mono<Account> withdraw(Long accountId, BigDecimal amount) {
    return accountRepository.findById(accountId)
            .flatMap(account -> {
                BigDecimal newBalance = account.getBalance().subtract(amount);
                account.setBalance(newBalance);
                return accountRepository.save(account);
            });
}
```

Transaction giúp gom các thao tác trong một đơn vị commit, nhưng chỉ khai báo `@Transactional` không tự động ngăn mọi lost update. Hai transaction vẫn có thể đọc cùng một giá trị rồi ghi theo dữ liệu cũ nếu không có cơ chế phát hiện hoặc khóa xung đột phù hợp.

### 2.3. Cách 1: Cập nhật nguyên tử trong database

Nếu nghiệp vụ chỉ cần trừ tiền và bảo đảm số dư không âm, hãy để database thực hiện phép tính trong một câu lệnh có điều kiện:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId
  AND balance >= :amount;
```

Hai request không còn gửi lại một giá trị số dư đã đọc từ trước. Mỗi câu lệnh cập nhật dựa trên giá trị hiện tại tại thời điểm database thực thi thao tác, và điều kiện `balance >= :amount` được kiểm tra cùng câu update.

Repository có thể khai báo:

```java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("""
           UPDATE accounts
           SET balance = balance - :amount
           WHERE id = :accountId
             AND balance >= :amount
           """)
    Mono<Integer> withdrawIfEnough(
            @Param("accountId") Long accountId,
            @Param("amount") BigDecimal amount);
}
```

Service kiểm tra số hàng bị tác động:

```java
public Mono<Void> withdraw(Long accountId, BigDecimal amount) {
    if (amount.signum() <= 0) {
        return Mono.error(new IllegalArgumentException("Amount must be positive"));
    }

    return accountRepository.withdrawIfEnough(accountId, amount)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                return Mono.error(new InsufficientBalanceException(accountId));
            });
}
```

Ví dụ giả định mỗi ID xác định đúng một tài khoản. Nếu số hàng là 0, tài khoản có thể không tồn tại hoặc không đủ số dư; có thể truy vấn thêm nếu nghiệp vụ cần phân biệt hai trường hợp. Cần xác nhận semantics đếm hàng của driver/database.

Atomic update đặc biệt hữu ích cho bộ đếm, tồn kho, số dư và các phép biến đổi có thể biểu diễn trực tiếp bằng SQL. Tuy nhiên, nếu quyết định cập nhật phụ thuộc vào nhiều quy tắc domain phức tạp, cần thiết kế câu lệnh và transaction để thể hiện đầy đủ các điều kiện đó.

### 2.4. Cách 2: Optimistic locking với `@Version`

Optimistic locking cho phép nhiều transaction đọc cùng một bản ghi, nhưng kiểm tra version khi ghi. Transaction đầu tiên cập nhật thành công và tăng version. Transaction tiếp theo vẫn dùng version cũ nên không cập nhật được.

Entity:

```java
@Table("accounts")
public class Account {

    @Id
    private Long id;

    @Version
    private Long version;

    private BigDecimal balance;

    // Constructor, getter và setter được lược bớt.
}
```

Repository:

```java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {
}
```

Khi lưu entity có `@Version`, Spring Data Relational sử dụng version trong điều kiện update và cập nhật version khi thao tác thành công. Nếu không có hàng nào khớp version mong đợi, Spring Data phát sinh lỗi optimistic locking, thường là `OptimisticLockingFailureException`.

Lịch thực thi minh họa:

| Thứ tự | T1 | T2 |
| ---: | --- | --- |
| 1 | Đọc balance 100, version 4 | |
| 2 | | Đọc balance 100, version 4 |
| 3 | Ghi balance 80 với điều kiện version = 4; thành công, version thành 5 | |
| 4 | | Ghi balance 90 với điều kiện version = 4; không có hàng khớp |
| 5 | | Nhận lỗi optimistic locking và xử lý xung đột |

T2 không âm thầm ghi đè T1. Ứng dụng có thể yêu cầu client thử lại, tải phiên bản mới rồi tính toán lại hoặc trả conflict tùy nghiệp vụ.

### 2.5. Cách 3: Pessimistic locking hoặc khóa tường minh

Với thao tác cần đọc một bản ghi rồi đưa ra quyết định dựa trên trạng thái hiện tại, có thể dùng câu lệnh khóa như `SELECT ... FOR UPDATE` trong transaction. Database giữ khóa phù hợp cho tới khi transaction kết thúc, khiến transaction cạnh tranh phải chờ hoặc thất bại theo timeout/deadlock policy.

Ví dụ repository:

```java
@Query("SELECT * FROM accounts WHERE id = :id FOR UPDATE")
Mono<Account> findByIdForUpdate(@Param("id") Long id);
```

Service:

```java
@Transactional
public Mono<Account> withdrawWithLock(Long id, BigDecimal amount) {
    return accountRepository.findByIdForUpdate(id)
            .switchIfEmpty(Mono.error(new AccountNotFoundException(id)))
            .flatMap(account -> {
                if (account.getBalance().compareTo(amount) < 0) {
                    return Mono.error(new InsufficientBalanceException(id));
                }

                account.setBalance(account.getBalance().subtract(amount));
                return accountRepository.save(account);
            });
}
```

Đây là ví dụ theo cú pháp của các database hỗ trợ `FOR UPDATE`. Khả năng khóa, phạm vi khóa và cú pháp cụ thể khác nhau theo database/driver. Transaction phải thực sự bao quanh cả câu `SELECT ... FOR UPDATE` và thao tác ghi; nếu query chạy ngoài transaction, khóa có thể được giải phóng ngay khi statement hoàn tất.

Giữ transaction khóa thật ngắn. Không gọi HTTP, gửi email hoặc chờ người dùng phản hồi trong khi đang giữ khóa database.

## 3. Đọc không lặp lại (Non-repeatable Read)

Non-repeatable read xảy ra khi một transaction đọc cùng một hàng hai lần nhưng nhận giá trị khác nhau vì transaction khác đã commit thay đổi giữa hai lần đọc.

### 3.1. Ví dụ trạng thái đơn hàng

Giả sử T1 đang tạo báo cáo và cần đọc trạng thái đơn hàng hai lần trong cùng một transaction:

| Thứ tự | Transaction T1 | Transaction T2 |
| ---: | --- | --- |
| 1 | `SELECT status` → `PAID` | |
| 2 | | `UPDATE orders SET status = 'CANCELLED' WHERE id = 10` |
| 3 | | COMMIT |
| 4 | `SELECT status` lần hai → `CANCELLED` | |

T1 đọc cùng một hàng nhưng giá trị khác nhau trong cùng transaction. Đây là non-repeatable read.

### 3.2. Isolation level ảnh hưởng thế nào?

Theo mô hình isolation của SQL:

- `READ COMMITTED` ngăn đọc dữ liệu chưa commit nhưng cho phép một transaction nhìn thấy giá trị mới đã commit giữa hai statement. Vì vậy có thể xảy ra non-repeatable read.
- `REPEATABLE READ` bảo đảm các lần đọc lại cùng hàng có tính lặp lại theo chuẩn SQL, nhưng hành vi cụ thể với snapshot và các truy vấn phạm vi còn phụ thuộc database.
- `SERIALIZABLE` yêu cầu kết quả tương đương một thứ tự thực thi tuần tự hợp lệ, do đó ngăn các bất thường tuần tự hóa như non-repeatable read.

Một số database dùng MVCC và cung cấp snapshot ổn định cho transaction `REPEATABLE READ`; một số khác có cách khóa và định nghĩa khác. Hãy kiểm tra tài liệu của hệ quản trị đang dùng thay vì suy ra mọi chi tiết chỉ từ tên isolation level.

### 3.3. Khi nào cần ngăn non-repeatable read?

Không phải mọi API đọc đều cần cùng một snapshot cho cả request. Nếu màn hình chỉ hiển thị dữ liệu hiện tại tại từng lần truy vấn, `READ COMMITTED` có thể phù hợp.

Ngăn non-repeatable read có ích khi một transaction cần:

- Đọc cùng một giá trị nhiều lần để đưa ra một quyết định nhất quán.
- Tính tổng hoặc xác nhận điều kiện dựa trên dữ liệu đã đọc trước đó.
- Tạo báo cáo mà các bước đọc phải dùng cùng snapshot.
- Kiểm tra trạng thái trước khi thực hiện các thay đổi liên quan.

Nếu chỉ cần một giá trị ổn định, đôi khi có thể đọc một lần rồi giữ trong biến cục bộ. Nhưng nếu quyết định phụ thuộc vào nhiều statement và dữ liệu cạnh tranh, cần cân nhắc isolation hoặc khóa phù hợp.

## 4. Đọc bóng (Phantom Read)

Phantom read xảy ra khi một transaction chạy lại cùng một truy vấn điều kiện và nhận thêm hoặc mất các hàng vì transaction khác đã insert, delete hoặc thay đổi một hàng để nó bắt đầu/kết thúc thỏa điều kiện.

Khác với non-repeatable read, trọng tâm của phantom read là **tập hàng thỏa predicate thay đổi**, không chỉ giá trị của một hàng đã đọc.

### 4.1. Ví dụ đếm đơn hàng đang mở

T1 cần đếm số đơn hàng `OPEN`:

| Thứ tự | Transaction T1 | Transaction T2 |
| ---: | --- | --- |
| 1 | `SELECT COUNT(*) FROM orders WHERE status = 'OPEN'` → 5 | |
| 2 | | `INSERT INTO orders (..., status) VALUES (..., 'OPEN')` |
| 3 | | COMMIT |
| 4 | Chạy lại cùng query → 6 | |

Hàng mới do T2 thêm trở thành một “phantom” đối với lần đọc thứ hai của T1.

Phantom cũng có thể xuất hiện khi T2 đổi trạng thái một đơn hàng từ `CLOSED` sang `OPEN`, hoặc xóa một hàng đang thỏa predicate.

### 4.2. Vì sao khóa một hàng chưa chắc ngăn phantom?

Nếu T1 chỉ khóa các hàng `OPEN` hiện có, một transaction khác có thể chèn hàng mới thỏa điều kiện vào phạm vi đó, tùy database và loại khóa. Để ngăn phantom, database cần cơ chế bảo vệ predicate/range hoặc dùng snapshot/isolation phù hợp.

Một số database sử dụng range lock hoặc predicate lock ở mức isolation cao. Database khác dựa vào MVCC và phát hiện xung đột khi commit. Cách triển khai không giống nhau.

### 4.3. Isolation level và phantom read

Theo các mức isolation của SQL:

- `READ COMMITTED` cho phép phantom read.
- `REPEATABLE READ` theo chuẩn SQL ngăn non-repeatable read nhưng có thể vẫn cho phép phantom read.
- `SERIALIZABLE` ngăn phantom read theo yêu cầu tương đương thực thi tuần tự.

Một số hệ quản trị triển khai `REPEATABLE READ` mạnh hơn mức tối thiểu của chuẩn. Ví dụ, snapshot isolation của một database có thể ngăn phantom trong một transaction cụ thể nhưng vẫn không tương đương hoàn toàn `SERIALIZABLE` đối với mọi dạng write skew. Cần kiểm tra tài liệu database và kiểm thử trên cấu hình thật.

## 5. So sánh ba hiện tượng

| Hiện tượng | Điều thay đổi mà transaction quan sát | Ví dụ | Cách xử lý thường dùng |
| --- | --- | --- | --- |
| Lost update | Ghi sau ghi đè thay đổi của ghi trước dựa trên dữ liệu cũ | Hai request cùng sửa số dư | Atomic update, `@Version`, khóa tường minh |
| Non-repeatable read | Cùng một hàng được đọc hai lần cho giá trị khác nhau | Trạng thái order đổi giữa hai lần SELECT | Isolation `REPEATABLE_READ`/`SERIALIZABLE`, khóa phù hợp |
| Phantom read | Tập hàng thỏa cùng predicate thay đổi giữa hai lần query | Số order `OPEN` tăng do insert mới | `SERIALIZABLE`, predicate/range locking hoặc snapshot phù hợp |

Lost update là vấn đề ghi đè khi cập nhật, trong khi non-repeatable và phantom read là bất thường của việc đọc trong transaction. Một hệ thống có thể cần xử lý nhiều loại cùng lúc.

## 6. Isolation level trong SQL

SQL định nghĩa các mức isolation phổ biến sau. Bảng dưới mô tả hành vi theo mô hình chuẩn; database thực tế có thể cung cấp đảm bảo mạnh hơn hoặc cách triển khai khác.

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không theo chuẩn | Có thể theo chuẩn |
| `SERIALIZABLE` | Không | Không | Không |

### 6.1. Dirty read để phân biệt

Dirty read là việc một transaction đọc dữ liệu mà transaction ghi chưa commit. Nếu transaction ghi rollback, transaction đọc đã sử dụng một giá trị chưa bao giờ trở thành dữ liệu đã commit.

Dirty read khác ba hiện tượng đang học:

- Lost update: thay đổi bị ghi đè.
- Non-repeatable read: đọc lại một hàng thấy giá trị khác.
- Phantom read: đọc lại một predicate thấy tập hàng khác.

`READ COMMITTED` trở lên ngăn dirty read theo mô hình SQL.

### 6.2. Không nên suy luận quá mức từ tên isolation

Hai database cùng nhận `REPEATABLE READ` có thể dùng MVCC, khóa hoặc quy tắc phát hiện xung đột khác nhau. Một số database có thể abort transaction khi phát hiện xung đột; database khác khiến transaction chờ khóa.

Vì vậy, cần xem:

- Isolation level mặc định của database.
- Isolation level thực sự được áp dụng cho connection.
- Semantics của MVCC/locking trong hệ quản trị.
- Những lỗi serialization/deadlock có thể phát sinh.
- Cách driver truyền isolation level và transaction tới database.

## 7. Cấu hình isolation level trong Spring Data R2DBC

Spring quản lý transaction reactive thông qua `R2dbcTransactionManager` hoặc transaction manager tương thích với `ConnectionFactory`. Có thể đặt isolation level bằng `@Transactional`.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class OrderReportService {

    private final OrderRepository orderRepository;

    public OrderReportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Mono<OrderSnapshot> createSnapshot(Long orderId) {
        return orderRepository.findById(orderId)
                .flatMap(order -> orderRepository.findById(orderId)
                        .map(secondRead -> new OrderSnapshot(
                                order.getId(),
                                order.getStatus(),
                                secondRead.getStatus())));
    }
}
```

Ví dụ minh họa việc khai báo isolation. Một use case thực tế thường đọc nhiều nguồn dữ liệu hoặc thực hiện một quyết định nghiệp vụ thay vì đọc cùng một hàng hai lần như ví dụ.

### 7.1. Reactive transaction được gắn với publisher

Với phương thức trả về `Mono` hoặc `Flux`, Spring sử dụng reactive transaction management. Transaction context được truyền trong Reactor Context, không dựa đơn thuần vào thread hiện tại.

Vì vậy:

- Giữ các thao tác database thuộc transaction trong cùng publisher chain.
- Để framework hoặc caller subscribe publisher.
- Không gọi `.block()` bên trong pipeline transaction.
- Không gọi `.subscribe()` độc lập cho một thao tác cần thuộc transaction hiện tại.
- Bảo đảm các repository dùng cùng `ConnectionFactory` và transaction manager nếu cần tham gia cùng transaction.

### 7.2. Dùng `TransactionalOperator`

Có thể quản lý ranh giới transaction bằng `TransactionalOperator` thay vì annotation:

```java
public Mono<OrderSnapshot> loadSnapshot(Long orderId) {
    Mono<OrderSnapshot> work = orderRepository.findById(orderId)
            .flatMap(order -> paymentRepository.findByOrderId(orderId)
                    .collectList()
                    .map(payments -> new OrderSnapshot(order, payments)));

    return transactionalOperator.transactional(work);
}
```

`TransactionalOperator` hữu ích khi muốn bao một pipeline cụ thể hoặc khi ranh giới transaction được tạo động. Cấu hình operator phải dùng transaction manager R2DBC tương ứng.

### 7.3. Isolation level không thay thế transaction boundary

Khai báo isolation trên một method không có nghĩa mọi lời gọi database trong ứng dụng đều dùng mức đó. Nó áp dụng cho transaction được tạo ở ranh giới tương ứng. Nếu phương thức không thực sự chạy qua transaction proxy hoặc publisher không được tiêu thụ đúng cách, transaction có thể không được áp dụng như mong muốn.

Khi có nhiều transaction manager, chỉ định rõ manager phù hợp nếu cần, tránh để thao tác R2DBC vô tình dùng transaction manager JDBC.

## 8. Optimistic locking trong Spring Data Relational

`@Version` là một cách phổ biến để phát hiện lost update mà không phải giữ khóa độc quyền trong toàn bộ thời gian người dùng chỉnh sửa dữ liệu.

### 8.1. Entity có version

```java
@Table("products")
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private Integer stock;

    // Constructor, getter và setter được lược bớt.
}
```

Schema cần có cột version tương ứng:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    stock INTEGER NOT NULL
);
```

Khi lưu entity mới, Spring Data khởi tạo version theo quy tắc của kiểu version. Khi update, version hiện tại được dùng trong điều kiện và giá trị version mới được ghi nếu update thành công.

### 8.2. Xử lý optimistic locking failure

Khi hai request cùng đọc version 3, chỉ một request có thể update thành công với version đó. Request còn lại nhận lỗi xung đột.

```java
public Mono<Product> updateProduct(Product product) {
    return productRepository.save(product)
            .onErrorMap(OptimisticLockingFailureException.class,
                    error -> new ProductConflictException(product.getId(), error));
}
```

Ứng dụng có thể chuyển lỗi thành HTTP `409 Conflict` hoặc một kết quả nghiệp vụ tương ứng. Không nên bắt lỗi rồi trả về entity cũ như thể thao tác đã thành công.

### 8.3. Retry phải tải dữ liệu mới và tính lại

Khi optimistic locking thất bại, không nên chỉ gọi `save()` lại cùng object có version cũ. Cần tải phiên bản mới, kiểm tra lại quy tắc nghiệp vụ và tính lại thay đổi.

Ví dụ khái niệm:

```java
public Mono<Product> reserveStock(Long productId, int quantity) {
    return productRepository.findById(productId)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(productId)))
            .flatMap(product -> {
                if (product.getStock() < quantity) {
                    return Mono.error(new InsufficientStockException(productId));
                }

                product.setStock(product.getStock() - quantity);
                return productRepository.save(product);
            });
}
```

Nếu cần retry tự động, hãy bao toàn bộ bước đọc mới, kiểm tra và ghi trong một lần thử, giới hạn số lần retry và chỉ retry khi nghiệp vụ an toàn. Không retry mù các thao tác có side effect bên ngoài như gửi tiền, gửi email hoặc phát message nếu chưa có cơ chế idempotency.

## 9. Cập nhật nguyên tử và optimistic locking: chọn cách nào?

| Tình huống | Cách phù hợp |
| --- | --- |
| Tăng/giảm counter, stock hoặc balance bằng phép tính đơn giản | Một câu `UPDATE column = column + ...` có predicate |
| Cập nhật aggregate sau khi kiểm tra nhiều field | `@Version` và repository `save()` |
| Đọc rồi quyết định dựa trên trạng thái hiện tại cần khóa | `SELECT ... FOR UPDATE` trong transaction ngắn, nếu database hỗ trợ |
| Nhiều người chỉnh sửa cùng một bản ghi và cần phát hiện xung đột | Optimistic locking và trả conflict |
| Điều kiện phụ thuộc phạm vi nhiều hàng | Predicate/range lock hoặc `SERIALIZABLE`, theo semantics database |
| Không cần snapshot nhất quán giữa nhiều lần đọc | Có thể dùng isolation mặc định phù hợp, thường là `READ COMMITTED` |

Atomic update thường có ít round trip và tránh khoảng thời gian giữa đọc và ghi. Optimistic locking phù hợp khi cần tải entity và áp dụng logic domain. Pessimistic locking phù hợp với một số thao tác cạnh tranh cao nhưng làm tăng thời gian chờ và nguy cơ deadlock.

## 10. Phòng ngừa non-repeatable read và phantom read

### 10.1. Dùng snapshot transaction khi cần đọc nhất quán

Nếu một use case cần nhiều câu SELECT nhìn thấy một trạng thái dữ liệu ổn định, hãy chọn isolation level phù hợp với database. `REPEATABLE_READ` có thể đủ cho cùng một hàng hoặc snapshot đọc theo semantics của hệ quản trị. Nếu cần bảo vệ tập hàng theo predicate trước các insert/update cạnh tranh, có thể cần `SERIALIZABLE` hoặc cơ chế khóa phạm vi.

### 10.2. Dùng một statement khi có thể

Nếu cần tính tổng, đếm và đọc các giá trị liên quan, một câu SQL có thể tránh việc hai statement quan sát hai trạng thái khác nhau.

Ví dụ:

```sql
SELECT status, COUNT(*) AS order_count
FROM orders
WHERE created_at >= :fromTime
GROUP BY status;
```

Một statement được database thực thi theo snapshot/statement semantics của nó. Cách này có thể đơn giản hơn việc chạy nhiều query rời rồi ghép kết quả, nhưng vẫn cần isolation phù hợp nếu transaction thực hiện thêm quyết định ghi sau đó.

### 10.3. Khóa phạm vi hoặc dùng SERIALIZABLE cho predicate quan trọng

Ví dụ nghiệp vụ giới hạn tối đa 10 đơn hàng đang `OPEN`. Chỉ đọc `COUNT(*)` rồi insert có thể bị race: hai transaction đều thấy 9 và cả hai cùng thêm, tạo thành 11.

Để bảo vệ invariant này, có thể:

- Thiết kế một hàng counter/slot được cập nhật nguyên tử với điều kiện `open_count < 10`.
- Khóa một hàng đại diện cho phạm vi nghiệp vụ, sau đó kiểm tra và ghi trong transaction.
- Dùng `SERIALIZABLE` và xử lý serialization failure bằng retry an toàn.
- Dùng constraint hoặc cấu trúc dữ liệu database có thể biểu diễn invariant trực tiếp.

Chỉ khóa các hàng hiện có trong kết quả `OPEN` có thể chưa đủ để ngăn một hàng mới được chèn vào phạm vi, tùy database. Cần kiểm tra semantics predicate/range lock.

## 11. Deadlock và serialization failure

Khi dùng khóa hoặc `SERIALIZABLE`, transaction có thể bị database từ chối để duy trì nhất quán.

- **Deadlock** xảy ra khi các transaction chờ khóa lẫn nhau theo chu trình.
- **Serialization failure** xảy ra khi database không thể cho phép một transaction commit mà vẫn giữ kết quả tương đương thực thi tuần tự.
- **Lock timeout** xảy ra khi chờ khóa vượt giới hạn cấu hình.

Ứng dụng cần xử lý các lỗi này theo chính sách retry có giới hạn hoặc trả lỗi conflict/service unavailable phù hợp. Không nên retry vô hạn vì có thể làm tăng tải và kéo dài hàng đợi.

Để giảm deadlock:

1. Truy cập các hàng theo thứ tự nhất quán giữa các transaction.
2. Giữ transaction ngắn.
3. Chỉ khóa dữ liệu cần thiết.
4. Tránh gọi dịch vụ ngoài khi đang giữ khóa.
5. Đặt timeout hợp lý.
6. Ghi log transaction ID, query và thời gian chờ khóa mà không làm lộ dữ liệu nhạy cảm.

## 12. Kiểm thử các hiện tượng đồng thời

Unit test đơn luồng thường không phát hiện được lost update, non-repeatable read hoặc phantom read. Cần integration test với database thật và ít nhất hai connection/transaction độc lập.

### 12.1. Thiết kế test có đồng bộ hai transaction

Một test concurrency nên:

1. Tạo dữ liệu ban đầu xác định.
2. Mở hai transaction độc lập.
3. Dùng barrier/latch để cả hai đọc trước khi cho phép ghi tiếp.
4. Điều khiển thứ tự commit hoặc rollback.
5. Đọc kết quả cuối và xác nhận invariant nghiệp vụ.
6. Lặp lại test đủ lần để bắt các race condition khó xuất hiện.

Không dùng cùng một connection cho cả hai transaction. Nếu test chạy trong một transaction test duy nhất, nó không tái hiện được sự cạnh tranh thực tế.

### 12.2. Test lost update

Với số dư ban đầu 100, chạy hai thao tác rút 20 và 10 đồng thời. Xác nhận:

- Nếu cả hai giao dịch được chấp nhận, số dư cuối là 70.
- Nếu một giao dịch bị từ chối do xung đột, kết quả phải phản ánh đúng giao dịch đã được chấp nhận và client biết giao dịch còn lại thất bại.
- Không có trường hợp cả hai báo thành công nhưng số dư cuối là 80 hoặc 90 do ghi đè.

### 12.3. Test non-repeatable read

Mở T1 ở isolation level cần kiểm tra. T1 đọc một hàng; T2 cập nhật và commit; T1 đọc lại cùng hàng. Xác nhận kết quả theo semantics của database và isolation level đang cấu hình.

### 12.4. Test phantom read

T1 chạy query đếm các hàng theo predicate. T2 insert một hàng thỏa predicate và commit. T1 chạy lại query. Xác nhận tập hàng hoặc count theo isolation level thực tế. Không dựa vào giả định chung của SQL nếu database có triển khai isolation mạnh hơn.

### 12.5. Công cụ kiểm thử reactive

`StepVerifier` giúp kiểm tra publisher phát giá trị, hoàn tất hoặc lỗi:

```java
StepVerifier.create(accountService.withdraw(accountId, new BigDecimal("20.00")))
        .verifyComplete();
```

Đối với test concurrency, cần thêm cơ chế phối hợp giữa các publisher/transaction, chẳng hạn `Sinks.One`, `CountDownLatch` ở phần điều phối test hoặc một test harness chuyên dụng. Không đưa blocking synchronization vào event-loop thread của ứng dụng.

## 13. Ví dụ minh họa hai transaction bằng SQL

Các đoạn sau nên chạy trong hai session database riêng biệt để quan sát cách isolation hoạt động. Cú pháp và kết quả cụ thể phụ thuộc hệ quản trị.

### 13.1. Non-repeatable read ở mức READ COMMITTED

Session A:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT status FROM orders WHERE id = 10;
-- Tạm dừng để Session B cập nhật và COMMIT.

SELECT status FROM orders WHERE id = 10;
COMMIT;
```

Session B:

```sql
BEGIN;
UPDATE orders SET status = 'CANCELLED' WHERE id = 10;
COMMIT;
```

Trong một database dùng semantics READ COMMITTED phổ biến, Session A có thể thấy giá trị mới ở câu SELECT thứ hai.

### 13.2. Phantom read theo mô hình SQL

Session A:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM orders WHERE status = 'OPEN';
-- Tạm dừng để Session B insert và COMMIT.

SELECT COUNT(*) FROM orders WHERE status = 'OPEN';
COMMIT;
```

Session B:

```sql
BEGIN;
INSERT INTO orders (id, status) VALUES (9001, 'OPEN');
COMMIT;
```

Session A có thể nhận count khác ở lần đọc thứ hai. Nếu chạy với isolation cao hơn, database có thể giữ snapshot cũ, khóa phạm vi hoặc từ chối một transaction.

## 14. Những lỗi thường gặp khi xử lý concurrency

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Số dư hoặc tồn kho bị ghi đè | Đọc-sửa-ghi không có kiểm tra version/điều kiện | Atomic update, `@Version` hoặc khóa phù hợp |
| Hai request cùng báo thành công nhưng kết quả chỉ giữ một thay đổi | Lost update | Kiểm tra invariant bằng concurrency test; phát hiện xung đột khi ghi |
| Cùng transaction đọc một hàng nhưng giá trị thay đổi | Isolation cho phép non-repeatable read | `REPEATABLE_READ`, `SERIALIZABLE` hoặc khóa phù hợp |
| Count thay đổi giữa hai lần SELECT | Phantom read hoặc dữ liệu nguồn thay đổi | Snapshot/`SERIALIZABLE` hoặc bảo vệ predicate |
| Lỗi optimistic locking | Entity đã cũ hoặc transaction khác cập nhật trước | Tải lại, kiểm tra lại nghiệp vụ, trả conflict hoặc retry có giới hạn |
| Transaction chờ lâu | Khóa bị giữ lâu hoặc pool/database quá tải | Rút ngắn transaction, xem lock wait và timeout |
| Deadlock | Transaction khóa tài nguyên theo thứ tự khác nhau | Chuẩn hóa thứ tự truy cập, retry có giới hạn |
| Retry làm thao tác lặp | Side effect không idempotent | Idempotency key, outbox hoặc thiết kế retry an toàn |
| `@Transactional` không có tác dụng như mong đợi | Lời gọi không qua proxy, publisher không được tiêu thụ đúng hoặc sai transaction manager | Kiểm tra proxy, reactive chain và ConnectionFactory |

## 15. Quy trình chọn biện pháp nhất quán

Khi thiết kế một thao tác đọc/ghi, hãy đi theo các bước:

1. Xác định invariant nghiệp vụ, ví dụ số dư không âm hoặc số đơn hàng mở không vượt giới hạn.
2. Xác định thao tác có thể chạy đồng thời trên cùng hàng hoặc cùng tập dữ liệu.
3. Kiểm tra nguy cơ lost update, non-repeatable read và phantom read riêng biệt.
4. Nếu phép cập nhật có thể biểu diễn bằng một câu SQL, ưu tiên cập nhật nguyên tử có predicate.
5. Nếu cần đọc entity rồi áp dụng domain logic, cân nhắc `@Version`.
6. Nếu cần khóa dữ liệu trong lúc kiểm tra và ghi, cân nhắc pessimistic locking trong transaction ngắn.
7. Nếu nhiều statement phải dùng cùng snapshot, chọn isolation level theo semantics database.
8. Nếu invariant liên quan đến tập hàng/predicate, xem xét `SERIALIZABLE`, range/predicate lock hoặc cấu trúc counter/constraint phù hợp.
9. Xác định cách xử lý optimistic conflict, deadlock và serialization failure.
10. Viết integration test dùng nhiều transaction độc lập trên đúng database triển khai.

## 16. Sơ đồ lựa chọn cơ chế

```mermaid
flowchart TD
    A[Phát hiện nhiều transaction có thể cạnh tranh] --> B{Cập nhật là phép biến đổi đơn giản?}
    B -->|Có| C[Atomic UPDATE có điều kiện]
    B -->|Không| D{Có thể chấp nhận optimistic conflict?}
    D -->|Có| E[@Version và xử lý retry/conflict]
    D -->|Không| F{Cần khóa khi đọc rồi ghi?}
    F -->|Có| G[SELECT FOR UPDATE trong transaction ngắn]
    F -->|Không| H[Thiết kế lại invariant và transaction]
    C --> I{Cần nhiều lần đọc cùng snapshot?}
    E --> I
    G --> I
    H --> I
    I -->|Có| J[Chọn REPEATABLE_READ hoặc SERIALIZABLE theo DB]
    I -->|Không| K[Isolation mặc định phù hợp]
    J --> L[Kiểm thử concurrency trên database thật]
    K --> L
```

## 17. Kết luận

Lost update là tình trạng một lần ghi ghi đè thay đổi của transaction khác; non-repeatable read là việc đọc lại cùng một hàng nhưng thấy giá trị khác; phantom read là việc chạy lại cùng predicate nhưng tập hàng kết quả thay đổi.

Trong Spring Data R2DBC, hãy chọn biện pháp theo loại bất thường: dùng atomic update cho phép tính đơn giản, `@Version` để phát hiện xung đột khi lưu entity, `SELECT ... FOR UPDATE` khi cần khóa tường minh và isolation level phù hợp khi nhiều câu đọc phải dùng một snapshot nhất quán. Với reactive transaction, giữ các thao tác trong cùng publisher chain và dùng đúng transaction manager R2DBC.

Các tên isolation level không bảo đảm mọi database có hành vi giống nhau. Hãy kiểm tra semantics của hệ quản trị, xử lý deadlock/serialization failure có giới hạn và kiểm thử bằng nhiều transaction độc lập trên database thực tế trước khi dựa vào một đảm bảo nhất quán trong production.
