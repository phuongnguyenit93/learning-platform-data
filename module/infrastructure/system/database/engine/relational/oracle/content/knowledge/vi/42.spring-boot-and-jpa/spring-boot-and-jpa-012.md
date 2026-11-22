# Optimistic locking, pessimistic locking và timeout

## 1. Vì sao ứng dụng cần cơ chế locking?

Trong ứng dụng Spring Boot và JPA, nhiều request có thể đọc và cập nhật cùng một bản ghi gần như đồng thời. Nếu không có cơ chế kiểm soát cạnh tranh, một request có thể ghi đè thay đổi của request khác hoặc đọc dữ liệu ở trạng thái không còn phù hợp.

Ví dụ, tài khoản có số dư 1.000. Hai request cùng đọc số dư 1.000. Request A trừ 300 và ghi 700; request B trừ 200 nhưng vẫn tính từ giá trị cũ 1.000 rồi ghi 800. Nếu cả hai lần ghi đều thành công, kết quả cuối là 800 thay vì 500. Đây là lost update.

Locking giúp điều phối các giao dịch đồng thời. JPA cung cấp hai chiến lược chính:

- **Optimistic locking** giả định xung đột ít xảy ra. Nhiều transaction có thể đọc cùng dữ liệu; khi ghi, provider kiểm tra dữ liệu có bị thay đổi kể từ lần đọc hay không.
- **Pessimistic locking** giả định có thể xảy ra tranh chấp. Transaction yêu cầu database khóa dữ liệu trước hoặc trong khi thao tác để transaction khác không thể cập nhật/xóa dòng đang bị khóa theo cách xung đột.

Timeout giới hạn thời gian chờ khi lấy lock hoặc thực hiện transaction/query. Timeout giúp hệ thống không chờ vô hạn, nhưng cần phân biệt lock timeout, query timeout, transaction timeout và connection-pool timeout vì chúng áp dụng ở các tầng khác nhau.

## 2. Optimistic locking với @Version

### 2.1. Cơ chế version column

JPA hỗ trợ optimistic locking thông qua annotation `@Version`. Mỗi entity có một thuộc tính version được provider quản lý. Khi đọc entity, Hibernate lưu version hiện tại trong persistence context. Khi cập nhật, Hibernate tạo câu SQL có điều kiện kiểm tra version cũ.

Ví dụ entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "PRODUCTS")
public class Product {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private Integer quantity;

    @Version
    @Column(nullable = false)
    private Long version;

    // getters/setters
}
```

Schema Oracle cần có cột version tương ứng:

```sql
CREATE TABLE products (
    id       NUMBER(19) PRIMARY KEY,
    name     VARCHAR2(200) NOT NULL,
    quantity NUMBER(10) NOT NULL,
    version  NUMBER(19) NOT NULL
);
```

Giá trị version được Hibernate quản lý; không tự tăng version trong business code khi đang dùng `@Version`. Khi insert, provider khởi tạo version theo chiến lược của nó; khi update, provider tăng version nếu thao tác cần version check.

### 2.2. SQL cập nhật có điều kiện version

Giả sử entity được đọc với `id=10`, `quantity=20`, `version=4`. Khi cập nhật, SQL có dạng khái quát:

```sql
UPDATE products
SET quantity = 18,
    version = 5
WHERE id = 10
  AND version = 4;
```

Nếu một transaction khác đã cập nhật dòng và version hiện tại thành 5, câu SQL trên không cập nhật dòng nào. Hibernate nhận biết số dòng bị ảnh hưởng khác với số dòng mong đợi và báo xung đột optimistic locking.

Như vậy, hai transaction có thể cùng đọc version 4, nhưng chỉ một transaction cập nhật thành công. Transaction còn lại phải xử lý xung đột thay vì âm thầm ghi đè dữ liệu mới.

### 2.3. Khi nào xung đột được phát hiện?

Xung đột không nhất thiết xuất hiện ngay tại câu lệnh setter hoặc `repository.save()`. JPA có thể trì hoãn SQL đến lúc flush. Vì vậy, exception có thể xuất hiện khi:

- Gọi `EntityManager.flush()`.
- Hibernate flush tự động trước query hoặc trước commit.
- Transaction commit và provider thực hiện flush cuối cùng.

Ví dụ:

```java
@Transactional
public void decreaseStock(Long productId, int amount) {
    Product product = entityManager.find(Product.class, productId);
    if (product.getQuantity() < amount) {
        throw new IllegalStateException("Insufficient stock");
    }

    product.setQuantity(product.getQuantity() - amount);
    // Hibernate performs version check at flush/commit.
}
```

Có thể gọi `flush()` tường minh nếu cần phát hiện xung đột trước khi thực hiện các bước tiếp theo, nhưng flush không commit transaction. Transaction vẫn có thể rollback sau đó.

### 2.4. Xử lý OptimisticLockException

Khi phát hiện version mismatch, JPA có thể ném `OptimisticLockException`. Spring/Hibernate có thể chuyển đổi exception sang các exception thuộc hệ sinh thái Spring, chẳng hạn `ObjectOptimisticLockingFailureException` hoặc `OptimisticLockingFailureException`.

Ví dụ xử lý ở tầng service/API:

```java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<String> handleOptimisticConflict(
            OptimisticLockingFailureException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("Dữ liệu đã được người khác cập nhật. Hãy tải lại và thử lại.");
    }
}
```

Tùy exception thực tế được Spring translate, có thể cần bắt cả exception JPA/Hibernate ở tầng phù hợp. Không nên bắt mọi `RuntimeException` rồi trả về HTTP 409 vì sẽ che giấu các lỗi khác.

Một transaction gặp optimistic conflict thường không thể tiếp tục như chưa có gì xảy ra. Hãy rollback transaction hiện tại; nếu muốn thử lại, thực hiện retry bằng một transaction mới và đọc lại dữ liệu mới nhất.

### 2.5. OPTIMISTIC và OPTIMISTIC_FORCE_INCREMENT

JPA định nghĩa các lock mode optimistic:

| Lock mode | Ý nghĩa |
|---|---|
| `OPTIMISTIC` | Yêu cầu kiểm tra version khi transaction hoàn tất để phát hiện entity bị thay đổi cạnh tranh |
| `OPTIMISTIC_FORCE_INCREMENT` | Ngoài kiểm tra optimistic, yêu cầu tăng version của entity, kể cả khi ứng dụng không thay đổi field thông thường |

Ví dụ:

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.OPTIMISTIC
);
```

Và yêu cầu tăng version:

```java
entityManager.lock(product, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

`OPTIMISTIC_FORCE_INCREMENT` hữu ích khi sự kiện nghiệp vụ cần làm mất hiệu lực các bản đọc cũ, ví dụ một aggregate root thay đổi trạng thái logic dù không có field thông thường nào thay đổi. Dùng có chủ đích vì tăng version có thể làm các transaction khác đang giữ entity cũ bị xung đột.

Các tên cũ `READ` và `WRITE` trong `LockModeType` là alias legacy cho `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT`; nên dùng tên mới để code thể hiện rõ ý định.

## 3. Pessimistic locking với JPA

### 3.1. Cơ chế khóa ở database

Pessimistic locking yêu cầu database lấy lock trên dòng dữ liệu. Với Oracle, Hibernate thường sử dụng SQL dạng `SELECT ... FOR UPDATE` cho `PESSIMISTIC_WRITE`.

```sql
SELECT id, name, quantity, version
FROM products
WHERE id = 10
FOR UPDATE;
```

Khi transaction A giữ row lock, transaction B muốn cập nhật hoặc lấy lock xung đột trên cùng dòng phải chờ, nhận lỗi timeout hoặc bỏ qua dòng tùy chiến lược được sử dụng. Row lock thường được giữ tới khi transaction commit hoặc rollback.

Pessimistic locking phù hợp với thao tác đọc rồi cập nhật mà không thể chấp nhận hai transaction cùng xử lý trên một giá trị cũ, ví dụ giữ chỗ tồn kho hoặc cấp phát một công việc cho worker. Tuy nhiên, lock lâu làm giảm concurrency và có thể gây deadlock.

### 3.2. PESSIMISTIC_READ

`PESSIMISTIC_READ` yêu cầu lock nhằm ngăn transaction khác cập nhật/xóa dữ liệu đang được đọc theo semantics JPA. Database/provider có thể dùng shared lock hoặc một hình thức lock mạnh hơn nếu cần.

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_READ
);
```

Không nên giả định `PESSIMISTIC_READ` luôn tạo đúng một loại Oracle lock cố định. Provider và database quyết định SQL cụ thể; trong một số trường hợp lock mạnh hơn có thể được dùng để đáp ứng semantics.

### 3.3. PESSIMISTIC_WRITE

`PESSIMISTIC_WRITE` yêu cầu lock đủ mạnh để ngăn transaction khác sửa/xóa dòng đang bị khóa cho đến khi transaction hiện tại hoàn tất:

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE
);

if (product.getQuantity() < amount) {
    throw new IllegalStateException("Insufficient stock");
}

product.setQuantity(product.getQuantity() - amount);
```

Đoạn code phải chạy trong transaction. Nếu không có transaction phù hợp, provider có thể báo lỗi vì pessimistic lock cần transaction để duy trì lock đến thời điểm hoàn tất.

### 3.4. PESSIMISTIC_FORCE_INCREMENT

`PESSIMISTIC_FORCE_INCREMENT` kết hợp pessimistic lock với việc tăng version của entity versioned. Nó hữu ích khi cần khóa dòng ngay lập tức và đồng thời làm tăng version để các bản đọc optimistic khác phát hiện thay đổi.

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

Chỉ dùng khi entity có version và nghiệp vụ cần cả hai đặc tính. Đây không phải lựa chọn mặc định cho mọi thao tác cập nhật.

### 3.5. @Lock trong Spring Data JPA

Spring Data JPA cho phép gắn lock mode lên repository query bằng `@Lock`:

```java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findByIdForUpdate(@Param("id") Long id);
}
```

Service gọi method trong transaction:

```java
@Service
public class InventoryService {
    private final ProductRepository productRepository;

    @Transactional
    public void reserve(Long productId, int amount) {
        Product product = productRepository.findByIdForUpdate(productId)
                .orElseThrow();

        if (product.getQuantity() < amount) {
            throw new IllegalStateException("Insufficient stock");
        }

        product.setQuantity(product.getQuantity() - amount);
    }
}
```

Spring Data JPA chuyển lock mode cho JPA provider; Hibernate tạo SQL phù hợp Oracle. Không đặt `@Lock` rồi gọi repository ngoài transaction nếu cần lock giữ xuyên suốt phần kiểm tra và cập nhật.

## 4. Chọn optimistic hay pessimistic locking?

| Tiêu chí | Optimistic | Pessimistic |
|---|---|---|
| Giả định | Xung đột ít xảy ra | Có thể có tranh chấp đáng kể |
| Cách kiểm soát | So sánh version khi ghi/hoàn tất | Lấy lock database trên dữ liệu |
| Thời gian chờ | Thường không chờ lock dòng khi đọc thông thường; có thể thất bại ở flush/commit | Có thể phải chờ lock, timeout hoặc nhận lỗi |
| Throughput | Tốt khi conflict thấp | Có thể giảm khi nhiều transaction tranh cùng dòng |
| Retry | Thường cần đọc lại và thử lại transaction mới | Có thể retry khi lock timeout/deadlock theo chính sách |
| Phù hợp | CRUD, dữ liệu ít bị cập nhật đồng thời | Inventory/queue/điều phối công việc có tranh chấp cao |

Không có một chiến lược đúng cho toàn bộ ứng dụng. Có thể dùng optimistic cho phần lớn entity và chỉ dùng pessimistic cho một số thao tác nhạy cảm. Ví dụ, màn hình chỉnh sửa thông tin khách hàng thường phù hợp optimistic; thao tác cấp phát một job cho worker có thể cần pessimistic hoặc `SKIP LOCKED`.

## 5. Lock timeout trong JPA

### 5.1. Hint jakarta.persistence.lock.timeout

JPA định nghĩa hint `jakarta.persistence.lock.timeout` để yêu cầu giới hạn thời gian chờ khi lấy pessimistic lock. Giá trị tính bằng milliseconds.

Ví dụ với EntityManager:

```java
Map<String, Object> hints = Map.of(
        "jakarta.persistence.lock.timeout", 3000
);

Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE,
        hints
);
```

Hoặc đặt hint trên query:

```java
Product product = entityManager.createQuery(
        "select p from Product p where p.id = :id", Product.class)
    .setParameter("id", productId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .setHint("jakarta.persistence.lock.timeout", 3000)
    .getSingleResult();
```

Với Hibernate 5/JPA cũ dùng namespace `javax.persistence.lock.timeout`; Hibernate 6/7 và Jakarta Persistence dùng `jakarta.persistence.lock.timeout`. Phải chọn tên hint theo API JPA thực tế của ứng dụng.

Đây là hint chuẩn ở tầng JPA. Provider/database có thể có giới hạn trong cách hiện thực; cần kiểm tra tài liệu Hibernate và SQL thực tế. Không giả định mọi JDBC driver/database đều áp dụng timeout chính xác như nhau.

### 5.2. Timeout bằng Spring Data JPA

Có thể gắn lock và query hint trên repository:

```java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.lock.timeout",
            value = "3000"
        )
    })
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findForUpdate(@Param("id") Long id);
}
```

Giá trị `3000` biểu thị 3.000 milliseconds theo JPA hint. Nếu Hibernate/Oracle dialect chuyển hint thành cú pháp `WAIT` của Oracle, hãy kiểm tra generated SQL và hành vi của đúng phiên bản. Một số provider có thể bỏ qua hoặc xử lý khác hint này.

### 5.3. Spring transaction timeout khác lock timeout

Spring `@Transactional(timeout = ...)` đặt giới hạn thời gian cho transaction theo đơn vị giây (tùy transaction manager và cách tích hợp):

```java
@Transactional(timeout = 10)
public void reserve(Long productId, int amount) {
    // Business operation
}
```

Giá trị này không đồng nghĩa với `jakarta.persistence.lock.timeout`. Transaction timeout áp dụng ở phạm vi giao dịch; lock timeout áp dụng cho thời gian chờ lấy lock cụ thể. Transaction manager có thể truyền timeout xuống JDBC/provider, nhưng không nên giả định hai cấu hình thay thế nhau.

### 5.4. Query timeout và connection timeout

Các timeout thường bị nhầm lẫn:

| Timeout | Phạm vi | Ví dụ cấu hình |
|---|---|---|
| Lock timeout | Chờ lấy lock | `jakarta.persistence.lock.timeout` |
| Transaction timeout | Toàn bộ transaction | `@Transactional(timeout = 10)` |
| Query timeout | Thời gian thực thi câu SQL | `jakarta.persistence.query.timeout`, `Query.setHint` hoặc JDBC `setQueryTimeout` |
| Connection acquisition timeout | Chờ mượn connection từ pool | Cấu hình HikariCP/UCP |
| Network/socket timeout | Chờ dữ liệu qua mạng | JDBC driver/network properties |

Ví dụ query timeout:

```java
List<Product> products = entityManager.createQuery(
        "select p from Product p where p.quantity < :threshold", Product.class)
    .setParameter("threshold", 5)
    .setHint("jakarta.persistence.query.timeout", 5000)
    .getResultList();
```

Query timeout không nhất thiết giải phóng mọi lock hoặc kết thúc transaction ngay lập tức trong mọi provider. Nếu query bị timeout, ứng dụng cần xử lý exception và rollback transaction theo đúng ranh giới nghiệp vụ.

## 6. Oracle locking: NOWAIT, WAIT và SKIP LOCKED

Oracle hỗ trợ các tùy chọn trên `SELECT ... FOR UPDATE` để điều khiển hành vi khi dòng đã bị transaction khác khóa.

### 6.1. Mặc định: chờ lock

```sql
SELECT id, quantity
FROM products
WHERE id = :id
FOR UPDATE;
```

Nếu transaction khác đang giữ lock xung đột, câu lệnh có thể chờ tới khi lock được giải phóng. Nếu transaction giữ lock commit/rollback, câu lệnh đang chờ có thể tiếp tục và lấy lock nếu dòng vẫn phù hợp.

### 6.2. NOWAIT

```sql
SELECT id, quantity
FROM products
WHERE id = :id
FOR UPDATE NOWAIT;
```

Nếu dòng đang bị khóa, Oracle trả lỗi ngay thay vì chờ. Trên Oracle, lỗi thường gặp là `ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired`.

`NOWAIT` phù hợp khi ứng dụng muốn phản hồi nhanh “đang được xử lý” thay vì giữ request chờ. Tuy nhiên, không nên biến mọi lỗi `ORA-00054` thành lỗi hệ thống; có thể trả HTTP 409/423 hoặc thông báo retry tùy semantics nghiệp vụ.

### 6.3. WAIT n

```sql
SELECT id, quantity
FROM products
WHERE id = :id
FOR UPDATE WAIT 5;
```

Oracle chờ tối đa số giây được chỉ định trong mệnh đề `WAIT`. Nếu hết thời gian, câu lệnh lỗi do không lấy được lock. Lựa chọn này hữu ích khi nghiệp vụ chấp nhận chờ ngắn nhưng không muốn request treo lâu.

### 6.4. SKIP LOCKED

```sql
SELECT id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` bỏ qua các dòng đang bị session khác khóa và trả các dòng khả dụng. Nó thường phù hợp cho nhiều worker cùng lấy việc từ queue, tránh các worker chờ cùng một dòng đầu tiên.

`SKIP LOCKED` không phải lock timeout. Nó thay đổi tập dòng được trả về bằng cách bỏ qua dòng đang khóa. Nếu không còn dòng nào khả dụng, truy vấn có thể trả kết quả rỗng dù queue vẫn có job đang được worker khác xử lý.

Với JPA, `PESSIMISTIC_WRITE` cùng lock timeout tiêu chuẩn không tự bảo đảm Hibernate sinh `SKIP LOCKED`. Đây là lựa chọn Oracle-specific/provider-specific và cần xác nhận API Hibernate/Oracle JDBC đang dùng. Nếu nghiệp vụ cần queue worker với `SKIP LOCKED`, có thể dùng native SQL hoặc tính năng chuyên biệt của provider.

## 7. Deadlock và các lỗi locking thường gặp

### 7.1. Deadlock

Deadlock xảy ra khi hai hoặc nhiều transaction giữ lock mà transaction còn lại cần, tạo thành chu trình chờ.

Ví dụ:

```text
Transaction A                 Transaction B
-------------                 -------------
Lock row 1                    Lock row 2
Request lock row 2             Request lock row 1
       |                              |
       +---------- deadlock ----------+
```

Oracle phát hiện deadlock và thường trả `ORA-00060: deadlock detected while waiting for resource`, đồng thời rollback statement được chọn để phá deadlock. Ứng dụng cần xử lý transaction lỗi và không tiếp tục dùng trạng thái persistence context như thể thao tác thành công.

### 7.2. Giảm nguy cơ deadlock

- Luôn truy cập nhiều dòng theo thứ tự nhất quán, ví dụ tăng dần theo primary key.
- Giữ transaction ngắn.
- Không chờ HTTP, message hoặc thao tác người dùng trong lúc đang giữ row lock.
- Không khóa nhiều dòng hơn mức nghiệp vụ cần.
- Thiết kế index phù hợp để tránh truy vấn khóa quét quá nhiều dòng.
- Kiểm tra execution plan và predicate của câu `SELECT FOR UPDATE`.
- Retry deadlock có giới hạn, có backoff và chỉ khi nghiệp vụ idempotent/an toàn.

### 7.3. Các lỗi cần phân biệt

| Oracle/JPA/Spring error | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `ORA-00054` | `NOWAIT` hoặc lock timeout hết hạn | Xem transaction đang giữ lock; quyết định trả conflict hay retry |
| `ORA-00060` | Deadlock | Kiểm tra deadlock trace, thứ tự lock và transaction boundary |
| `ORA-30006` | Hết thời gian chờ với `WAIT` khi acquire lock | Kiểm tra thời gian giữ lock và timeout |
| `OptimisticLockException` | Version không còn khớp | Rollback, đọc lại dữ liệu và yêu cầu người dùng xử lý conflict |
| `PessimisticLockException` | Lỗi lấy/giữ pessimistic lock khiến transaction thất bại | Rollback transaction và điều tra resource contention |
| `LockTimeoutException` | Không lấy được lock trong thời hạn; semantics JPA phân biệt statement/transaction failure | Xem provider translation và trạng thái transaction |
| Spring `CannotAcquireLockException` | Spring translate lỗi lấy lock | Xem root cause JDBC/Oracle và retry policy |

Tên exception cuối cùng phụ thuộc tầng phát sinh và exception translation. Hãy log root cause Oracle error code/SQLState cùng transaction correlation ID, đồng thời tránh ghi dữ liệu nhạy cảm.

## 8. Locking với bulk update và native query

### 8.1. JPQL bulk update bỏ qua entity lifecycle thông thường

JPQL bulk update chạy trực tiếp trên database, không tải từng entity vào persistence context. Vì vậy, nó không áp dụng optimistic version checking giống cập nhật entity được quản lý thông thường và không tự đồng bộ các entity đang được giữ trong persistence context.

Ví dụ:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("update Product p set p.quantity = p.quantity - :amount " +
       "where p.id = :id and p.quantity >= :amount")
int decreaseQuantity(@Param("id") Long id, @Param("amount") int amount);
```

Truy vấn trả số dòng được cập nhật. Nếu cần optimistic locking cho bulk update, phải thiết kế điều kiện version và tăng version một cách tường minh, hoặc dùng một cách cập nhật entity có quản lý. Cần xem lại persistence context sau bulk DML vì entity đã load trước đó có thể trở nên stale.

### 8.2. Native SQL

Native query có thể dùng cú pháp Oracle cụ thể như `FOR UPDATE WAIT`, `NOWAIT` hoặc `SKIP LOCKED`. Khi tự viết native SQL, ứng dụng chịu trách nhiệm bảo đảm transaction boundary, parameter binding và đồng bộ trạng thái entity.

Không nối input người dùng trực tiếp vào chuỗi native SQL. Dùng bind parameters cho giá trị; các phần cú pháp không bind được như tên cột hoặc hướng sort phải được whitelist.

## 9. Kết hợp @Version với pessimistic lock

Một entity có thể có `@Version` và một số thao tác vẫn yêu cầu `PESSIMISTIC_WRITE`. Hai cơ chế không loại trừ nhau:

- Pessimistic lock ngăn transaction khác thay đổi dòng trong thời gian transaction đang giữ lock.
- Version check phát hiện thay đổi được thực hiện qua đường truy cập không giữ cùng lock hoặc thay đổi xảy ra trước khi lock được lấy.

Khi dùng cả hai, Hibernate/Oracle cần thực hiện đúng semantics của provider. Không thêm lock mode cho mọi query chỉ vì entity đã có `@Version`; điều đó có thể làm giảm concurrency không cần thiết.

## 10. Isolation level và locking

Isolation level và explicit lock mode là hai lớp kiểm soát liên quan nhưng khác nhau.

Oracle mặc định dùng `READ COMMITTED` ở mức transaction. Mỗi câu SQL nhìn thấy dữ liệu đã commit trước thời điểm statement bắt đầu, với multi-version concurrency control (MVCC). Một truy vấn đọc thông thường không khóa các dòng để ngăn transaction khác cập nhật; `SELECT FOR UPDATE` mới yêu cầu row lock.

`SERIALIZABLE` thay đổi cách transaction nhìn snapshot và có thể báo lỗi serialization khi phát hiện xung đột. Nó không thay thế mọi trường hợp cần pessimistic lock; cũng không nên nâng isolation toàn ứng dụng chỉ để giải quyết một race condition cụ thể.

JPA `LockModeType` biểu đạt yêu cầu lock trên entity/query; JDBC transaction isolation biểu đạt mức cô lập transaction. Cần chọn đúng công cụ cho semantics nghiệp vụ.

## 11. Thiết kế retry an toàn

### 11.1. Retry optimistic conflict

Khi optimistic conflict, retry cần đọc entity mới trong transaction mới. Không lặp lại thao tác trên entity cũ trong persistence context đã thất bại.

Ví dụ ý tưởng:

```java
public void updateWithRetry(Long id, int delta) {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            updateInNewTransaction(id, delta);
            return;
        } catch (ObjectOptimisticLockingFailureException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
            backoff(attempt);
        }
    }
}
```

`updateInNewTransaction` phải thực sự chạy trong transaction mới, ví dụ qua một Spring bean khác hoặc một cơ chế transaction boundary được cấu hình đúng. Gọi một method `@Transactional` khác trong cùng object qua self-invocation có thể không đi qua Spring proxy nên propagation không hoạt động như mong đợi.

Không phải nghiệp vụ nào cũng được phép retry tự động. Nếu request biểu diễn thao tác dựa trên quyết định của người dùng, có thể cần trả conflict để người dùng xem lại dữ liệu mới thay vì tự áp dụng delta lên trạng thái mới.

### 11.2. Retry lock timeout/deadlock

Chỉ retry khi:

- Transaction cũ đã rollback/được đánh dấu rollback và connection/persistence context được xử lý đúng.
- Lỗi là lỗi transient được nhận diện rõ.
- Thao tác idempotent hoặc có idempotency key/kiểm soát duplicate.
- Có giới hạn số lần thử và exponential backoff với jitter.
- Retry không làm tăng tải quá mức trong lúc database đang contention.

Không retry vô hạn một câu `SELECT FOR UPDATE` khi lock holder bị treo. Cần tìm nguyên nhân transaction giữ lock lâu và sửa lifecycle.

## 12. Quy trình chọn và kiểm thử locking

1. Xác định invariant nghiệp vụ cần bảo vệ, ví dụ tồn kho không âm hoặc chỉ một worker được nhận một job.
2. Đánh giá mức độ tranh chấp và thời gian transaction; conflict thấp thường phù hợp optimistic.
3. Thêm `@Version` cho entity cần phát hiện lost update và kiểm tra schema version column.
4. Dùng `PESSIMISTIC_WRITE`/`@Lock` cho thao tác cần khóa dòng trước khi đọc-sửa-ghi.
5. Chọn lock timeout riêng với transaction/query/pool timeout; kiểm tra provider có hỗ trợ hint như mong đợi.
6. Nếu dùng Oracle `NOWAIT`, `WAIT n` hoặc `SKIP LOCKED`, kiểm tra SQL được Hibernate sinh ra hoặc dùng native query có kiểm soát.
7. Chạy kiểm thử concurrency bằng nhiều transaction thực sự, không chỉ unit test một thread.
8. Kiểm tra optimistic conflict, lock timeout, deadlock, rollback và retry.
9. Quan sát Oracle wait events, blocking sessions, lock duration, SQL plan và connection pool metrics.
10. Chỉ triển khai retry khi thao tác an toàn và transaction mới được tạo đúng cách.

## 13. Ví dụ kiểm thử hai transaction đồng thời

Một cách kiểm thử optimistic locking là mở hai transaction độc lập, cùng đọc một entity versioned, sau đó lần lượt flush:

```text
Transaction A                 Transaction B
-------------                 -------------
Read Product v=4              Read Product v=4
Change quantity               Change quantity
Flush -> UPDATE ... v=4       
Commit -> version becomes 5   
                              Flush -> UPDATE ... v=4
                              0 rows updated
                              Optimistic lock exception
```

Với pessimistic locking:

```text
Transaction A                 Transaction B
-------------                 -------------
SELECT ... FOR UPDATE         SELECT ... FOR UPDATE
Gets row lock                 Waits / NOWAIT error
Update row                    
Commit                        Acquires lock or fails
```

Kiểm thử phải dùng hai connection/session độc lập và transaction boundary thật. Một test chạy tuần tự trong cùng persistence context không tái hiện được cạnh tranh.

## 14. Nguyên tắc cần ghi nhớ

- Optimistic locking dùng `@Version` để phát hiện dữ liệu đã bị thay đổi trước khi ghi; nó không khóa dòng trong suốt thời gian đọc.
- Pessimistic locking yêu cầu database lock dòng; Oracle thường dùng `SELECT FOR UPDATE` và giữ lock tới commit/rollback.
- `OPTIMISTIC_FORCE_INCREMENT` và `PESSIMISTIC_FORCE_INCREMENT` yêu cầu tăng version theo lock mode tương ứng.
- Spring Data JPA `@Lock` đặt lock mode cho repository query; thao tác cần transaction phù hợp.
- `jakarta.persistence.lock.timeout` là hint tính bằng milliseconds; Hibernate/driver/database có thể có giới hạn hiện thực.
- `@Transactional(timeout=...)`, query timeout và connection-pool timeout là các giới hạn khác nhau.
- Oracle `NOWAIT`, `WAIT n` và `SKIP LOCKED` có semantics khác nhau; SKIP LOCKED bỏ qua dòng đang bị khóa chứ không chờ.
- Deadlock cần xử lý bằng transaction rollback, thứ tự lock nhất quán và transaction ngắn; không retry vô hạn.
- Bulk JPQL/native DML cần được xử lý riêng vì có thể bỏ qua optimistic version check/persistence-context synchronization thông thường.
- Chỉ retry trong transaction mới khi nghiệp vụ idempotent hoặc có cơ chế chống xử lý trùng.

## Tài liệu tham khảo

- [Jakarta Persistence Specification — Locking and Concurrency](https://jakarta.ee/specifications/persistence/)
- [Hibernate ORM User Guide — Locking](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#locking)
- [Spring Data JPA Reference — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html)
- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html)
