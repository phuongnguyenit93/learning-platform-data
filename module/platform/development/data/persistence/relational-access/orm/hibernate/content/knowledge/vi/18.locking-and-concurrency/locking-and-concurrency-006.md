# Timeout khóa, deadlock và xử lý thất bại có giới hạn trong Hibernate ORM

## 1. Bài toán: cùng một dữ liệu, nhiều giao dịch cùng muốn thay đổi

Trong hệ thống đặt hàng, hai khách có thể đồng thời mua sản phẩm cuối cùng. Một nhân viên điều chỉnh tồn kho đúng lúc dịch vụ thanh toán xác nhận đơn. Một tác vụ chạy nền cũng có thể đang khóa những bản ghi mà API cần sửa.

Hibernate ORM giúp ứng dụng ánh xạ entity thành SQL, nhưng **việc khóa hàng, chờ khóa, phát hiện deadlock, hủy transaction và cấp phát tài nguyên là trách nhiệm kết hợp giữa Hibernate, transaction manager và cơ sở dữ liệu**.

Giả sử bảng Product có hai hàng:

| id | sku | stock_quantity |
|---:|---|---:|
| 101 | KB-01 | 20 |
| 102 | MS-02 | 15 |

Hai giao dịch cùng muốn cập nhật cả hai sản phẩm:

- Giao dịch A khóa sản phẩm 101, sau đó cần khóa 102.
- Giao dịch B khóa sản phẩm 102, sau đó cần khóa 101.

Mỗi giao dịch đang giữ tài nguyên mà giao dịch kia cần. Nếu không thể tiếp tục, ta có **deadlock**. Trong tình huống đơn giản hơn, A giữ khóa 101 trong thời gian dài còn B chỉ muốn cập nhật 101, B có thể **chờ khóa** rồi vượt quá thời gian cho phép (**lock timeout**) mà không có deadlock.

Bài học này tập trung vào câu hỏi: **Khi một giao dịch không lấy được khóa, ứng dụng phải làm gì để thất bại an toàn, có giới hạn thời gian, không tạo thêm lỗi dữ liệu và không retry vô hạn?**

### Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt lock contention, lock timeout, NOWAIT, deadlock, statement timeout và transaction timeout.
2. Hiểu cơ chế khóa bi quan trong JPA/Hibernate, giới hạn của timeout hint và những hành vi phụ thuộc database dialect.
3. Đọc mã SQLSTATE thường gặp trên PostgreSQL để phân loại lỗi.
4. Giải thích vì sao **một transaction đã lỗi ở PostgreSQL thường phải rollback trước khi retry**.
5. Viết retry **toàn bộ đơn vị công việc** với max attempts, deadline, exponential backoff và jitter.
6. Thiết kế thứ tự lấy khóa ổn định, transaction ngắn, idempotency và cơ chế trả lỗi có kiểm soát.
7. Dùng NOWAIT hoặc SKIP LOCKED đúng tình huống và hiểu rủi ro bỏ qua công việc.
8. Chẩn đoán deadlock/lock wait bằng log, PostgreSQL monitoring và integration test có hai transaction thật.

Ví dụ sử dụng Java 17+, Jakarta Persistence API, Hibernate ORM 6.x, Spring Boot 3.x/Spring Data JPA và PostgreSQL. Cú pháp lock hint, native SQL và mã lỗi trong bài cần được diễn giải theo hệ quản trị và phiên bản thực tế; chúng không mặc nhiên giống nhau trên MySQL, SQL Server, Oracle hoặc H2.

## 2. Sáu khái niệm cần tách biệt

| Tình huống | Bản chất | Có cần chu trình chờ vòng tròn không? | Kết quả có thể xảy ra |
|---|---|---|---|
| **Lock contention** | Một transaction phải chờ tài nguyên do transaction khác giữ | Không | Chờ rồi lấy khóa, hoặc thất bại vì timeout |
| **Lock timeout** | Thời gian chờ lấy khóa vượt giới hạn | Không | Database hủy statement chờ khóa; transaction cần xử lý phù hợp |
| **NOWAIT** | Yêu cầu khóa ngay, nếu bận thì báo lỗi thay vì chờ | Không | Thất bại nhanh khi khóa đang bị giữ |
| **Deadlock** | Các transaction chờ nhau thành chu trình, không ai tự tiến lên nếu không can thiệp | **Có** | DB chọn một transaction làm nạn nhân để phá vòng chờ |
| **Statement/query timeout** | Một câu SQL chạy hoặc chờ quá lâu so với giới hạn của statement | Không | Hủy statement, kể cả khi nguyên nhân là scan/sort chậm chứ không phải khóa |
| **Transaction timeout / deadline** | Đơn vị công việc giao dịch vượt thời gian cho phép | Không | Framework/DB có thể đánh dấu rollback, hủy công việc hoặc từ chối commit |

Một điểm thường bị bỏ qua là **connection pool acquisition timeout**: request chưa lấy được connection từ pool nên không gửi được câu SQL nào. Đây là lỗi thiếu connection/tài nguyên ứng dụng, **không phải lock timeout của PostgreSQL**. Tương tự, timeout HTTP của API gateway bao toàn request không đồng nhất với timeout đợi khóa trong database.

### 2.1. Chờ khóa bình thường

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as PostgreSQL
    participant B as Transaction B
    A->>DB: UPDATE Product #101
    Note over A,DB: A giữ row lock
    B->>DB: SELECT Product #101 FOR UPDATE
    Note over B,DB: B chờ A kết thúc
    A->>DB: COMMIT
    DB-->>B: Cấp khóa sau khi A nhả
    B->>DB: UPDATE Product #101
    B->>DB: COMMIT
~~~

Chờ khóa **không nhất thiết là lỗi**. Nếu A kết thúc nhanh và B còn đủ thời gian, việc chờ là hành vi bình thường của hệ thống đồng thời.

### 2.2. Deadlock là chu trình phụ thuộc

~~~mermaid
flowchart LR
    A["Transaction A đang giữ Product 101"] -->|"chờ khóa Product 102"| B["Transaction B đang giữ Product 102"]
    B -->|"chờ khóa Product 101"| A
~~~

Vì cả A và B đều đang chờ nhau, chỉ tăng thời gian chờ không thể tự giải quyết. Database thường phát hiện chu trình và **rollback một transaction nạn nhân** để transaction còn lại có cơ hội tiếp tục.

### 2.3. Lock timeout không phải deadlock

Nếu chỉ có A khóa Product 101 và B chờ Product 101, nhưng A không cần tài nguyên nào do B giữ, đó là **chờ khóa một chiều**. B có thể timeout vì A đang xử lý quá lâu; không có chu trình chờ để gọi là deadlock.

**Cách xử lý khác nhau:** deadlock thường gợi ý vấn đề thứ tự khóa; lock timeout còn có thể do transaction dài, query chậm, thiếu index hoặc resource contention. Cả hai đều có thể được retry trong điều kiện phù hợp, nhưng không nên gộp chúng thành “lỗi ngẫu nhiên, retry thật nhiều là xong”.

## 3. Một row lock xuất hiện lúc nào?

Trong Hibernate, sửa một field Java chưa chắc đồng nghĩa database đã nhận SQL ngay:

~~~java
Product product = entityManager.find(Product.class, productId);
product.decreaseStock(1);
// Hibernate có thể chưa phát UPDATE cho tới flush.
~~~

Nếu application cần **khóa bi quan trước khi quyết định dựa trên stock**, phải yêu cầu khóa qua truy vấn/EntityManager hoặc thực hiện thao tác SQL atomic thích hợp. Một lệnh Java setter không phải tương đương SELECT FOR UPDATE.

Khóa hàng có thể được lấy khi PostgreSQL thực thi các statement như UPDATE, DELETE hoặc SELECT ... FOR UPDATE. Khóa được giữ đến khi transaction kết thúc theo cơ chế tương ứng; nhả connection khỏi tay lập trình viên mà **không commit/rollback** không phải cách giải phóng một transaction đang mở an toàn.

### 3.1. EntityManager.find với PESSIMISTIC_WRITE

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;

Product product = entityManager.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);

if (product == null) {
    throw new IllegalArgumentException("Không tìm thấy sản phẩm");
}

product.decreaseStock(quantity);
~~~

Đoạn này phải chạy trong transaction hợp lệ. Hibernate thường chuyển yêu cầu PESSIMISTIC_WRITE thành một dạng locking SELECT tương ứng với dialect, chẳng hạn **FOR UPDATE** trong PostgreSQL. Một số mapping/fetch plan phức tạp có thể khiến cách render SQL khác nhau, nên quan sát log thay vì khẳng định mọi query có đúng một câu FOR UPDATE.

### 3.2. Spring Data JPA với @Lock

~~~java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> lockById(@Param("id") Long id);
}
~~~

Lời gọi **lockById()** cần nằm trong một transaction **thực sự đang hoạt động**. Không lấy khóa trong một method @Transactional rồi trả entity về để sửa trong transaction khác với kỳ vọng khóa cũ còn giữ nguyên.

### 3.3. PESSIMISTIC_WRITE không giải quyết mọi tranh chấp

Khóa row là hữu ích khi có thao tác đọc–kiểm tra–ghi trên **một hay một nhóm row**. Nhưng các bất biến trải trên nhiều row, nhiều bảng hoặc resource bên ngoài vẫn cần:

- Constraint như UNIQUE, CHECK, FOREIGN KEY ở DB.
- Thứ tự khóa nhất quán giữa các transaction.
- Isolation/locking đủ mạnh cho invariant liên quan.
- Kiểm tra số hàng bị ảnh hưởng khi dùng SQL conditional update.
- Idempotency nếu request có thể được gửi lại.

Ví dụ hai transaction cùng thấy “chưa có reservation” rồi cùng INSERT một reservation mới: không có row cũ để khóa bằng SELECT FOR UPDATE. **UNIQUE theo business key** hoặc thiết kế khóa trên một row owner thích hợp mới bảo vệ được cuộc đua ấy.

## 4. PostgreSQL: lock_timeout, NOWAIT và các lớp thời hạn

PostgreSQL hỗ trợ cấu hình thời gian chờ lấy khóa bằng **lock_timeout**. Khi statement không lấy được một lock trong thời gian giới hạn, PostgreSQL hủy statement với lỗi phù hợp.

### 4.1. SET LOCAL lock_timeout

~~~sql
BEGIN;

SET LOCAL lock_timeout = '750ms';

SELECT id, stock_quantity
FROM products
WHERE id = 101
FOR UPDATE;

-- Thực hiện thao tác nghiệp vụ nếu đã khóa thành công.

COMMIT;
~~~

**SET LOCAL** thay đổi cấu hình trong phạm vi transaction hiện tại; sau commit/rollback, cấu hình này không rò rỉ sang những transaction kế tiếp trên connection pool. Đây là cách phù hợp để đặt timeout theo use case trên PostgreSQL khi cần kiểm soát ở tầng database.

Một số điểm quan trọng:

- **lock_timeout** áp dụng khi statement phải đợi lấy một lock, không phải đồng hồ giới hạn mọi công việc SQL.
- PostgreSQL có thể chờ nhiều lock trong một statement; giới hạn lock_timeout được xét cho từng lần đợi lock theo semantics của DB.
- **lock_timeout = 0** ở PostgreSQL nghĩa là **không đặt giới hạn lock wait bằng tham số này**, **không phải NOWAIT**.
- Không dùng **SET lock_timeout** ở cấp session một cách tùy tiện trên connection được pool tái sử dụng, vì có thể ảnh hưởng request sau.
- Nếu **statement_timeout** nhỏ hơn hoặc bằng lock_timeout, câu SQL có thể hết statement timeout trước; hai loại giới hạn cần được lựa chọn nhất quán.

**Cảnh báo:** đặt timeout cực nhỏ như 1ms có thể biến những chờ khóa bình thường thành lỗi liên tục. Chọn giới hạn theo latency budget, mức tranh chấp và đặc điểm xử lý thực tế.

### 4.2. NOWAIT: thất bại ngay nếu không lấy được khóa

~~~sql
BEGIN;

SELECT id, stock_quantity
FROM products
WHERE id = 101
FOR UPDATE NOWAIT;

COMMIT;
~~~

Nếu một transaction khác đang giữ row lock xung đột, NOWAIT có thể lập tức báo **lock_not_available** (SQLSTATE **55P03**) thay vì xếp hàng chờ. Điều này hữu ích cho thao tác “thử lấy khóa, nếu bận thì người dùng quay lại sau”.

**NOWAIT không đồng nghĩa hệ thống sẽ không bao giờ chờ bất kỳ loại lock nào.** Trong PostgreSQL, NOWAIT cho phần row lock không thay thế mọi hành vi lấy table-level lock hoặc tài nguyên khác. Khi cần giới hạn tổng thời gian, phải phối hợp lock_timeout, statement_timeout và request deadline.

### 4.3. JPA lock timeout hint

Jakarta Persistence có query hint chuẩn:

~~~java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(@QueryHint(
    name = "jakarta.persistence.lock.timeout",
    value = "0"
))
@Query("select p from Product p where p.id = :id")
Optional<Product> tryLockById(@Param("id") Long id);
~~~

Ví dụ trên đặt trên repository cùng import **Optional** và **@Param** như phần trước. Với API JPA, giá trị **0** của lock timeout hint biểu đạt yêu cầu **không đợi**; một giá trị dương biểu đạt thời gian chờ tính bằng mili giây theo contract API. **Đừng nhầm với PostgreSQL lock_timeout = 0**, vốn có nghĩa tắt timeout.

**Giới hạn quan trọng:** việc provider hỗ trợ giá trị timeout cụ thể và chuyển nó thành SQL đúng như mong muốn **phụ thuộc Hibernate version và dialect/database**. Không coi annotation hint là lời hứa hard deadline chính xác tới mili giây trong mọi DB. Nếu PostgreSQL là database mục tiêu và cần bảo đảm ngân sách lock wait, kiểm chứng SQL được render và cân nhắc **SET LOCAL lock_timeout** ở trong transaction.

### 4.4. Một số lớp timeout khác

| Timeout | Phạm vi | Ví dụ triệu chứng |
|---|---|---|
| **PostgreSQL lock_timeout** | Thời gian chờ lấy lock | SQLSTATE 55P03 khi không lấy được khóa |
| **PostgreSQL statement_timeout** | Thời gian thực thi một statement tính cả chờ theo cơ chế DB | SQLSTATE 57014 khi bị hủy do statement timeout |
| **Spring @Transactional(timeout = N)** | Giới hạn transaction được framework quản lý, thường đơn vị giây | Statement timeout/rollback tùy transaction manager và tài nguyên |
| **JPA query timeout hint** | Gợi ý giới hạn thời gian thực thi query | Provider/dialect có thể hủy statement hoặc báo query timeout |
| **JDBC socket/network timeout** | Thời gian chờ I/O ở connection/driver | Lỗi driver/connection, có thể chưa biết server đã commit hay chưa |
| **Connection pool acquisition timeout** | Chờ lấy connection từ pool | Request thất bại trước khi gửi SQL |
| **HTTP deadline** | Toàn bộ request/operation của API | Proxy/client timeout ngay cả khi DB còn làm việc |
| **idle_in_transaction_session_timeout** (PostgreSQL) | Session mở transaction nhưng nhàn rỗi quá lâu | Server đóng connection đang idle trong transaction |

Các giới hạn có thể **chồng lên nhau**. Nếu HTTP deadline là 2 giây, transaction timeout là 20 giây và lock_timeout là 10 giây, cấu hình đó không bảo đảm response trong 2 giây. Thiết kế cần một **end-to-end latency budget** rồi phân bổ cho connection acquisition, lock wait, SQL execution, retry và serialization.

### 4.5. statement_timeout và deadlock_timeout khác nhau

~~~sql
BEGIN;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '1500ms';
-- Các SQL tiếp theo được giới hạn theo hai cơ chế trên.
COMMIT;
~~~

**statement_timeout** có thể hủy một truy vấn chậm do scan, sort, I/O hoặc khóa; không nên gắn nhãn mọi SQLSTATE 57014 là “deadlock”.

PostgreSQL còn có tham số **deadlock_timeout**, là khoảng chờ trước khi server chạy kiểm tra deadlock cho tình huống chờ khóa (và liên quan log lock waits). Nó **không phải** hạn mức mà transaction được phép chờ trước khi luôn bị abort. Tuning tham số này là vận hành database, không phải cách thay thế retry hoặc sửa thứ tự khóa của ứng dụng.

## 5. PostgreSQL SQLSTATE: phân loại đúng trước khi quyết định retry

Khi một câu SQL thất bại, SQLException/PSQLException thường cung cấp **SQLSTATE**, có ý nghĩa ổn định hơn việc so khớp chuỗi thông báo lỗi ngôn ngữ tự nhiên.

| SQLSTATE | Tên phổ biến | Tình huống | Retry toàn transaction? |
|---|---|---|---|
| **40P01** | deadlock_detected | DB chọn transaction làm nạn nhân để phá deadlock | **Thường có**, với giới hạn và thao tác idempotent |
| **55P03** | lock_not_available | NOWAIT hoặc lock_timeout khi không lấy được lock | **Có điều kiện**, nếu tranh chấp dự kiến ngắn |
| **40001** | serialization_failure | Transaction bị hủy do xung đột serializability | **Thường có**, phải retry cả transaction |
| **57014** | query_canceled | Statement bị hủy, ví dụ statement_timeout hoặc user cancel | **Không tự động**; xác định nguyên nhân/latency budget |
| **23505** | unique_violation | Vi phạm khóa duy nhất | **Không retry mù quáng**; có thể là duplicate request hoặc lỗi nghiệp vụ |
| **23503** | foreign_key_violation | Tham chiếu không hợp lệ | Thường không; sửa dữ liệu/nghiệp vụ |
| **23514** | check_violation | Giá trị vi phạm CHECK constraint | Thường không; sửa logic/input |

**40P01** và **40001** đặc biệt thích hợp với retry **toàn transaction** sau khi rollback. **55P03** có thể thích hợp với retry ngắn hoặc trả kết quả “bận” ngay, tùy SLA. Mã **57014** có thể đến từ timeout, cancel do người dùng hoặc nguyên nhân khác; retry ngay một truy vấn vốn đã vượt thời gian thường làm hệ thống bận thêm.

**SQLSTATE không đủ để suy ra tính an toàn nghiệp vụ.** Một transaction rollback ở DB có thể đã gọi API thanh toán hoặc gửi email trước khi thất bại. Retry transaction ấy có thể **thu tiền hoặc gửi email lần thứ hai** nếu không có idempotency.

### 5.1. Exception ở tầng JPA/Hibernate

Các exception mà ứng dụng có thể gặp gồm:

- **jakarta.persistence.LockTimeoutException**: JPA mô tả trường hợp lock acquisition failure làm rollback statement thay vì toàn transaction theo contract API.
- **jakarta.persistence.PessimisticLockException**: dùng cho lock failure khiến transaction phải rollback theo contract API.
- **jakarta.persistence.OptimisticLockException**: version/update conflict; khác lock wait/deadlock.
- Các exception của Hibernate từ JDBC exception conversion.
- Spring **PessimisticLockingFailureException**, **CannotAcquireLockException**, **QueryTimeoutException**, hoặc exception tầng data access khác tùy provider/translation.

**Rất quan trọng với PostgreSQL:** khi một SQL statement lỗi bên trong transaction, transaction thường chuyển sang trạng thái **aborted**; các SQL tiếp theo nhận thông báo transaction is aborted cho đến khi ROLLBACK. Vì vậy đừng dựa duy nhất vào tên JPA **LockTimeoutException** để kết luận có thể tiếp tục dùng transaction cũ. Với PostgreSQL, **rollback transaction rồi thực hiện attempt mới** là hướng an toàn thông thường.

### 5.2. Không phân loại bằng thông báo lỗi

Tránh:

~~~java
if (ex.getMessage().contains("deadlock")) {
    retry();
}
~~~

Thông báo có thể bị thay đổi theo driver, version và ngôn ngữ. Trong hệ thống có PostgreSQL, hãy unwrap nguyên nhân xuống SQLException và xét **getSQLState()**, hoặc dùng exception translation được cấu hình/kiểm thử rõ ràng. Nếu không xác định được lỗi retryable, **thất bại an toàn** thay vì retry mọi RuntimeException.

## 6. Transaction sau lỗi khóa: không sửa tiếp rồi commit

Xét service sai về nguyên tắc:

~~~java
@Transactional
public void incorrectTransfer(Long sourceId, Long destinationId) {
    try {
        lockAndTransfer(sourceId, destinationId);
    } catch (Exception ex) {
        log.warn("Khóa bận, thử tiếp trong transaction hiện tại", ex);
        // Tiếp tục các lệnh database khác.
    }
    saveAuditAsSuccess();
}
~~~

Có ít nhất ba vấn đề:

1. Khi PostgreSQL báo lỗi statement, transaction có thể đã **aborted** và không thể tiếp tục SQL bình thường.
2. Spring/Hibernate có thể đánh dấu transaction **rollback-only**; cuối cùng nhận UnexpectedRollbackException hoặc một lỗi persistence khác.
3. Dù không có lỗi DB, việc nuốt exception rồi ghi audit **thành công** làm sai kết quả nghiệp vụ.

**Phương án đúng:** để exception làm transaction hiện tại rollback, sau đó **ở một scope bên ngoài** quyết định tạo transaction mới cho retry. Mỗi attempt phải là một unit of work đầy đủ, đọc state hiện tại và kiểm tra lại mọi điều kiện.

~~~mermaid
flowchart TD
    A[Nhận yêu cầu] --> B[Attempt #1: transaction mới]
    B --> C{Kết quả}
    C -->|Commit thành công| Z[Trả thành công]
    C -->|Lỗi retryable| D[Rollback attempt]
    C -->|Lỗi không retryable| F[Trả lỗi tương ứng]
    D --> E{Còn attempts và deadline?}
    E -->|Có| G[Backoff + jitter ngoài transaction]
    G --> H[Attempt kế tiếp: transaction mới]
    H --> C
    E -->|Không| I[Trả thất bại có giới hạn]
~~~

Không sleep bên trong transaction đang giữ connection/lock. Không tiếp tục dùng EntityManager/Session sau transaction đã hỏng để “cứu vãn” attempt. **Thay đổi object Java** trong attempt thất bại cũng không tự hoàn tác về trạng thái ban đầu, nên attempt mới phải đọc state DB mới trong persistence context mới.

## 7. Giảm deadlock bằng thứ tự khóa nhất quán

Một kỹ thuật hiệu quả là mọi workflow cùng cần khóa nhiều Product phải lấy khóa theo **một thứ tự cố định**, chẳng hạn theo productId tăng dần.

### 7.1. Hai cách lấy khóa

**Nguy cơ deadlock:**

~~~text
Transaction A: khóa Product 101 -> sau đó Product 102
Transaction B: khóa Product 102 -> sau đó Product 101
~~~

**Giảm nguy cơ:**

~~~text
Transaction A: khóa Product 101 -> Product 102
Transaction B: khóa Product 101 -> Product 102
~~~

Với cùng thứ tự, B phải đợi A ở Product 101 trước khi được giữ Product 102, nên hai giao dịch không tạo chu trình đối nghịch trên chính hai khóa đó.

### 7.2. Minh họa bằng EntityManager

~~~java
public void lockProductsInOrder(EntityManager em, Collection<Long> ids) {
    var sortedIds = ids.stream()
        .distinct()
        .sorted()
        .toList();

    for (Long id : sortedIds) {
        Product product = em.find(
            Product.class, id, LockModeType.PESSIMISTIC_WRITE);
        if (product == null) {
            throw new IllegalArgumentException("Sản phẩm không tồn tại: " + id);
        }
    }
}
~~~

Giả định method chạy trong một transaction, Collection/EntityManager/LockModeType được import. Ứng dụng nên validate ID không null trước khi sort. Nếu các transaction còn khóa bảng khác (Order, Reservation, Ledger...), phải quy ước **thứ tự khóa xuyên tất cả tài nguyên**, không chỉ hai Product.

**Thứ tự khóa ổn định giảm nguy cơ, không bảo đảm không bao giờ có deadlock.** Trigger, foreign key, index update, các workflow khác, range/predicate locks hoặc truy vấn khóa theo kế hoạch DB khác có thể tạo phụ thuộc mới. Vì thế production vẫn cần retry bounded và monitoring.

### 7.3. Khóa từng ID hay một SELECT IN (...)?

Một câu:

~~~sql
SELECT id FROM products
WHERE id IN (101, 102)
ORDER BY id
FOR UPDATE;
~~~

thường diễn đạt ý định thứ tự. Nhưng **thứ tự thực tế lấy lock** có thể chịu tác động của plan/query shape; nếu việc bảo đảm thứ tự là điều kiện quan trọng, khóa tuần tự từng ID theo order đã chuẩn hóa là cách dễ quan sát và kiểm thử hơn. Đừng khẳng định rằng chỉ thêm ORDER BY vào mọi kiểu query phức tạp sẽ loại bỏ hoàn toàn deadlock.

## 8. Thiết kế ví dụ domain: chuyển số lượng giữa hai kho sản phẩm

Để nhìn thấy khóa hai row và retry, ta dùng thao tác **chuyển một số lượng tồn kho** giữa Product A và Product B. Đây là tình huống học tập; trong domain thật thường có entity **WarehouseStock** theo (warehouseId, productId) và một bảng ghi lịch sử chuyển kho.

### 8.1. Schema PostgreSQL có ràng buộc cuối cùng

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

INSERT INTO products(sku, stock_quantity)
VALUES ('KB-01', 20), ('MS-02', 15);
~~~

CHECK **stock_quantity >= 0** bảo vệ database trước code ngoài Hibernate hoặc lỗi concurrent update. Ràng buộc **UNIQUE(sku)** bảo vệ danh tính sản phẩm, không thay thế khóa giao dịch.

### 8.2. Entity với @Version

~~~java
package com.example.shop.inventory;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Version
    private long version;

    protected Product() {}

    public Long getId() { return id; }
    public int getStockQuantity() { return stockQuantity; }

    public void take(int quantity) {
        if (quantity <= 0 || quantity > stockQuantity) {
            throw new IllegalArgumentException("Không đủ số lượng");
        }
        stockQuantity -= quantity;
    }

    public void put(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        stockQuantity = Math.addExact(stockQuantity, quantity);
    }
}
~~~

**@Version** phục vụ optimistic version check khi Hibernate ghi managed entity. Kết hợp @Version với pessimistic lock không phải điều cấm, nhưng mỗi loại giải quyết một khía cạnh: pessimistic lock điều phối truy cập trước khi sửa, còn version có thể phát hiện ghi đè dựa trên state cũ. Không coi @Version là cơ chế giới hạn thời gian chờ khóa.

### 8.3. Một attempt trong transaction riêng

~~~java
package com.example.shop.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Statement;

@Service
public class StockTransferAttempt {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void transfer(Long fromId, Long toId, int quantity) {
        if (fromId == null || toId == null || fromId.equals(toId)) {
            throw new IllegalArgumentException("Hai sản phẩm phải khác nhau");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        // Chỉ dành cho PostgreSQL: giới hạn trong transaction hiện tại.
        em.unwrap(Session.class).doWork(connection -> {
            try (Statement statement = connection.createStatement()) {
                statement.execute("SET LOCAL lock_timeout = '400ms'");
                statement.execute("SET LOCAL statement_timeout = '1500ms'");
            }
        });

        long firstId = Math.min(fromId, toId);
        long secondId = Math.max(fromId, toId);

        Product first = em.find(
            Product.class, firstId, LockModeType.PESSIMISTIC_WRITE);
        Product second = em.find(
            Product.class, secondId, LockModeType.PESSIMISTIC_WRITE);

        if (first == null || second == null) {
            throw new IllegalArgumentException("Sản phẩm không tồn tại");
        }

        Product source = fromId.equals(first.getId()) ? first : second;
        Product target = toId.equals(first.getId()) ? first : second;

        source.take(quantity);
        target.put(quantity);
        // Dirty checking cập nhật cả hai entity khi flush/commit.
        // Không gọi HTTP hay sleep trong transaction.
    }
}
~~~

Ở đây:

- **SET LOCAL** chạy trên chính JDBC connection đang tham gia transaction thông qua Session.doWork; không đặt timeout ở cấp session lâu dài của pool.
- Hai Product được lock theo **ID tăng dần** ngay cả khi lệnh chuyển từ 102 sang 101.
- Thao tác take/put thuộc cùng transaction; nếu lỗi ở bất kỳ bước nào, thay đổi DB đã flush cũng phải rollback.
- **Không** giữ transaction trong lúc chờ API bên ngoài.
- **400ms/1500ms chỉ là thông số minh họa**, không phải giá trị khuyến nghị cho mọi hệ thống.

Nếu ứng dụng dùng database khác hoặc nhiều transaction manager, không bê nguyên **SET LOCAL**. Cần cơ chế timeout tương đương và xác nhận cùng datasource/connection với transaction chính.

**Lưu ý tên Product:** ví dụ này dùng hai Product như hai row có số lượng có thể chuyển; trong nghiệp vụ kho thực, chuyển số lượng giữa các **WarehouseInventory** row thường hợp lý hơn, nhưng kỹ thuật khóa và retry giống nhau.

## 9. Retry có giới hạn: attempts, deadline, backoff và jitter

Một retry policy tốt không phải:

~~~java
while (true) {
    try {
        transfer();
        break;
    } catch (Exception ignored) {
        // Thử lại vô hạn.
    }
}
~~~

Vòng lặp này có thể làm hệ thống tệ hơn:

- Một database đã nghẽn tiếp tục nhận thêm request cạnh tranh.
- Client chờ vô hạn hoặc đến khi HTTP gateway tự cắt.
- Nguy cơ lặp thao tác có side effect bên ngoài.
- Không phân biệt lỗi dữ liệu nghiệp vụ với lỗi tạm thời.
- Dùng cùng transaction/EntityManager lỗi để thử lại.

Thay vào đó, policy cần có:

| Thành phần | Vai trò |
|---|---|
| **maxAttempts** | Trần số lần chạy transaction, ví dụ 3 (bao gồm lần đầu) |
| **overall deadline** | Không bắt đầu attempt mới khi ngân sách request đã hết |
| **per-attempt timeout** | Giới hạn chờ lock/statement cho từng attempt |
| **exponential backoff** | Sau mỗi lỗi tạm thời, chờ lâu hơn trước lần thử tiếp |
| **jitter** | Random hóa thời gian chờ để nhiều request không cùng retry một lúc |
| **retryable classification** | Chỉ retry SQLSTATE/exception thực sự có khả năng hồi phục |
| **new transaction each attempt** | Rollback và bỏ persistence context cũ trước attempt mới |
| **idempotency** | Bảo vệ hệ thống khi request/event bị thực thi lại hoặc kết quả commit không chắc chắn |
| **error budget/fallback** | Khi hết attempts/deadline, trả lỗi có ý nghĩa thay vì che giấu |

### 9.1. Ví dụ coordinator nằm ngoài transaction

~~~java
package com.example.shop.inventory;

import org.springframework.stereotype.Service;

import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

@Service
public class StockTransferCoordinator {
    private static final int MAX_ATTEMPTS = 3;
    private static final long OPERATION_BUDGET_NANOS =
        TimeUnit.SECONDS.toNanos(2);

    private final StockTransferAttempt attempt;

    public StockTransferCoordinator(StockTransferAttempt attempt) {
        this.attempt = attempt;
    }

    // Cố ý KHÔNG @Transactional ở coordinator.
    public void transfer(Long fromId, Long toId, int quantity) {
        long deadline = System.nanoTime() + OPERATION_BUDGET_NANOS;
        RuntimeException lastFailure = null;

        for (int number = 1; number <= MAX_ATTEMPTS; number++) {
            if (System.nanoTime() >= deadline) {
                break;
            }

            try {
                // Qua Spring proxy: mỗi lời gọi mở transaction mới.
                attempt.transfer(fromId, toId, quantity);
                return;
            } catch (RuntimeException failure) {
                if (!isRetryableDatabaseFailure(failure)) {
                    throw failure;
                }
                lastFailure = failure;

                if (number == MAX_ATTEMPTS) {
                    break;
                }

                long remainingNanos = deadline - System.nanoTime();
                if (remainingNanos <= 0) {
                    break;
                }

                long baseMillis = 40L << (number - 1);
                long jitterMillis = ThreadLocalRandom.current()
                    .nextLong(0, 41);
                long desiredMillis = baseMillis + jitterMillis;
                long remainingMillis = TimeUnit.NANOSECONDS
                    .toMillis(remainingNanos);
                if (remainingMillis <= 0) {
                    break;
                }

                try {
                    Thread.sleep(Math.min(desiredMillis, remainingMillis));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Đã hủy retry vì thread bị interrupt", interrupted);
                }
            }
        }

        throw new OperationBusyException(
            "Hệ thống đang bận, thao tác chưa hoàn tất", lastFailure);
    }

    private static boolean isRetryableDatabaseFailure(Throwable error) {
        for (Throwable cause = error; cause != null;
             cause = cause.getCause()) {
            if (cause instanceof SQLException sql) {
                String state = sql.getSQLState();
                if ("40P01".equals(state)
                        || "55P03".equals(state)
                        || "40001".equals(state)) {
                    return true;
                }
            }
        }
        return false;
    }
}

class OperationBusyException extends RuntimeException {
    OperationBusyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đoạn code là minh họa retry đồng bộ trong Spring. Coordinator nằm **ngoài transaction**, gọi **StockTransferAttempt** ở một bean riêng qua proxy. Khi method @Transactional của attempt ném exception, Spring rollback/hoàn tất transaction của attempt **trước khi coordinator bắt lỗi và sleep**.

**Không đặt @Transactional ở coordinator** và không gọi cùng method attempt bằng **this.transfer(...)** bên trong cùng bean: self-invocation có thể bỏ qua Spring transaction proxy.

### 9.2. Giới hạn của overall deadline trong ví dụ

Deadline ở coordinator là **điều kiện không bắt đầu attempt mới sau khi hết ngân sách**. Nó **không tự ngắt giữa chừng** một statement đang chạy. Per-attempt lock_timeout/statement_timeout, timeout từ transaction manager và deadline request là các lớp bổ sung cần được bố trí để đạt end-to-end SLA. Tổng thời gian thực có thể vượt 2 giây một chút nếu attempt bắt đầu sát deadline, thời gian rollback, logging hoặc network chậm.

Vì thế ví dụ **không được quảng bá như một hard realtime deadline**. Muốn kiểm soát chặt, cần cân nhắc timeout của DB/driver/pool/request và kiến trúc asynchronous phù hợp.

### 9.3. Không retry mọi RuntimeException

Hàm phân loại trong ví dụ chỉ retry khi tìm được SQLException có SQLSTATE thuộc tập đã lựa chọn. Những lỗi như:

- Không đủ tồn kho.
- Product không tồn tại.
- Unique constraint bị vi phạm.
- Validation thất bại.
- Một method nghiệp vụ từ chối chuyển trạng thái.

phải **thất bại ngay**, không tạo thêm DB attempts. Với Spring exception translation, đôi khi nguyên nhân đã bị wrap hoặc SQLSTATE không nằm trong cause chain theo cách đơn giản trên; khi dùng production cần kiểm thử thực tế và có lớp classifier bao quát provider/database được sử dụng.

**Mã 55P03 không mặc nhiên retry mọi nơi.** Nếu client cố ý dùng NOWAIT để kiểm tra “bận thì trả ngay”, retry đồng bộ nhiều lần có thể trái UX/SLA. Classifier nên còn xét **loại use case** và policy của endpoint.

## 10. Retry và idempotency là hai vấn đề khác nhau

Trong một transaction DB local, khi server báo lỗi deadlock hoặc serialization failure và rollback thành công, có thể chạy lại toàn transaction vì thay đổi DB của attempt bị hủy.

Nhưng hãy xét:

~~~java
@Transactional
public void purchase() {
    paymentProvider.chargeCard(); // Side effect ngoài database.
    reserveStock();               // Có thể deadlock.
}
~~~

Nếu chargeCard đã thành công nhưng reserveStock gặp deadlock, **retry toàn method sẽ gọi chargeCard thêm lần nữa**. DB rollback không rollback tiền đã thu.

### 10.1. Phân loại thao tác

| Loại thao tác | Retry sau rollback DB | Điều kiện cần |
|---|---|---|
| Chuyển số lượng giữa hai row cùng DB | Thường có thể | Toàn bộ update trong transaction, không side effect ngoài DB |
| Tạo đơn có requestId unique | Có thể, nhưng phải kiểm tra duplicate | Business idempotency key, transaction mới sau unique conflict |
| Gửi email trong method rồi update DB | **Không an toàn nếu chạy lại mù quáng** | Outbox/đưa email ra sau commit, deduplicate |
| Gọi cổng thanh toán | Chỉ khi provider hỗ trợ idempotency theo key và workflow có đối soát | Idempotency key bền vững, trạng thái thanh toán |
| Publish message | Có thể tạo trùng khi retry/crash | Outbox + consumer idempotent |
| Ghi nhật ký audit phải phản ánh thành công | Cần chọn đúng thời điểm commit | Outbox hoặc audit transaction theo semantics rõ |

Một nguyên tắc thiết kế quan trọng: **attempt transaction nên chứa các thay đổi DB có thể rollback cùng nhau**. Side effect bên ngoài nên đi qua **transactional outbox**, message worker, hoặc một saga có compensation/idempotency.

### 10.2. Idempotency key và kết quả commit không rõ

Không phải mọi lỗi connection xảy ra sau COMMIT đều cho phép client biết chắc transaction đã rollback. Nếu kết nối đứt đúng lúc DB đang commit, client có thể không biết thay đổi đã bền vững hay chưa.

Trong trường hợp **outcome unknown**:

- Không mặc định thực hiện lại một thao tác không idempotent.
- Dùng **requestId / operationId duy nhất** được lưu trong cùng DB transaction với thay đổi.
- Truy vấn lại kết quả theo operationId trong transaction mới trước khi quyết định làm gì.
- Nếu dùng payment gateway, hỏi trạng thái giao dịch bằng idempotency key hoặc provider transaction ID.

Retry ở tầng transport của HTTP, broker hoặc load balancer có thể xảy ra độc lập với retry policy ở tầng database; tất cả phải đồng thuận về idempotency.

## 11. Chiến lược thay thế: optimistic locking và atomic SQL

Không phải use case nào cũng cần giữ PESSIMISTIC_WRITE. Khóa bi quan giảm một số race condition nhưng tăng chờ khóa, vì vậy cần so sánh với hai chiến lược khác.

### 11.1. Optimistic locking bằng @Version

~~~java
@Version
private long version;
~~~

Hibernate có thể sinh SQL:

~~~sql
UPDATE products
SET stock_quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu version đã đổi, update không khớp row và Hibernate báo optimistic lock conflict. Đây **không phải lock timeout**; ứng dụng vẫn có thể cân nhắc retry toàn business unit khi việc đọc lại và tính toán phù hợp. Với tỷ lệ tranh chấp thấp và transaction ngắn, optimistic locking có thể giảm thời gian giữ khóa trước khi ghi.

**Không tự động retry OptimisticLockException vô hạn.** Nó có thể thể hiện tranh chấp nghiệp vụ thực sự; retry phải đọc lại state và có giới hạn, có thể trả 409 Conflict nếu client đang sửa cùng một tài nguyên.

### 11.2. Atomic conditional UPDATE

Với phép trừ tồn kho một row, có thể dùng:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - :qty,
    version = version + 1
WHERE id = :productId
  AND stock_quantity >= :qty;
~~~

Nếu **row count = 1**, cập nhật đã diễn ra. Nếu **row count = 0**, sản phẩm không tồn tại hoặc không đủ tồn kho; ứng dụng có thể query để phân biệt theo nhu cầu. Câu UPDATE là một thao tác DB atomic, tránh mẫu **SELECT quantity → tính trong Java → UPDATE** thiếu kiểm soát cạnh tranh.

Tuy nhiên:

- UPDATE vẫn có thể **chờ khóa** trên row khi có transaction khác đang ghi.
- Nếu đang có một Product managed trong persistence context, JPQL/native bulk UPDATE có thể làm state Java của nó **bị cũ**.
- Việc tăng version bằng SQL phải phù hợp cách Hibernate quản lý version trong những đường ghi khác.
- Với nhiều Product và invariant chung, vẫn cần transaction, thứ tự thao tác, idempotency và xử lý deadlock.

**Kết luận:** atomic UPDATE có thể làm vùng critical section nhỏ hơn, nhưng không “tắt” hết deadlock/lock contention của cơ sở dữ liệu.

## 12. NOWAIT hay SKIP LOCKED: đừng dùng sai mục đích

Hai tùy chọn PostgreSQL thường được nhắc cùng khi xây hệ thống có concurrency cao:

### 12.1. NOWAIT cho thao tác tương tác nhanh

~~~sql
SELECT id, stock_quantity
FROM products
WHERE id = 101
FOR UPDATE NOWAIT;
~~~

Nếu đang bận, ứng dụng có thể trả kết quả “tài nguyên đang được xử lý” thay vì chờ lâu. Phù hợp cho những endpoint cần phản hồi nhanh và không muốn tự động xếp hàng.

### 12.2. SKIP LOCKED cho hàng đợi công việc

~~~sql
BEGIN;

SELECT id, status
FROM jobs
WHERE status = 'PENDING'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 20;

-- Đánh dấu các job đã chọn thành PROCESSING trong cùng transaction.
COMMIT;
~~~

**SKIP LOCKED** bỏ qua những row đang bị khóa bởi transaction khác, cho phép worker lấy những job khả dụng mà không chờ. Đây là cách phù hợp cho queue/table processing nơi **không bắt buộc** phải lấy đúng row đang bận tại lần poll đó.

Nhưng nếu use case là “chuyển tiền từ tài khoản A sang B”, **bỏ qua tài khoản A vì nó đang khóa rồi xử lý phần còn lại** là sai về tính nguyên tử. SKIP LOCKED không được dùng để che giấu thiếu dữ liệu trong một business transaction bắt buộc phải thấy đủ các row.

### 12.3. Claim job nguyên tử với PostgreSQL

~~~sql
WITH selected AS (
    SELECT id
    FROM outbox_events
    WHERE status = 'PENDING'
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 20
)
UPDATE outbox_events e
SET status = 'PROCESSING',
    claimed_until = now() + INTERVAL '30 seconds'
FROM selected s
WHERE e.id = s.id
RETURNING e.id, e.event_type, e.payload;
~~~

Giả định bảng outbox_events đã có các cột **status**, **claimed_until**, **payload**. Statement claim nên chạy trong transaction ngắn rồi commit. Sau đó worker mới thực hiện I/O bên ngoài; không giữ row lock trong suốt thời gian gọi API.

Hệ thống còn cần:

- Cơ chế reclaim job khi **claimed_until** hết hạn.
- **Idempotency** khi một job bị xử lý lại sau crash.
- Retry/backoff có giới hạn cho từng job và dead-letter/quarantine khi vượt ngưỡng.
- Monitoring job bị kẹt/starvation.

**SKIP LOCKED cố ý cung cấp một cái nhìn không đầy đủ về hàng đang bị khóa**, vì vậy không dùng nó cho báo cáo nhất quán hoặc các phép kiểm tra toàn bộ dữ liệu. Một row luôn bị worker khác chiếm hoặc liên tục lỗi có thể bị bỏ qua lâu nếu không có chính sách lease/retry/fairness.

## 13. Tránh giữ transaction mở trong lúc chờ API ngoài

Một lỗi phổ biến:

~~~java
@Transactional
public void checkout(Long productId) {
    Product product = repository.lockById(productId).orElseThrow();
    product.reserve(1);
    paymentGateway.charge(); // Chờ HTTP 3–10 giây.
    saveOrder();
}
~~~

Trong thời gian paymentGateway.charge() chạy, transaction có thể đang giữ row lock trên Product và có thể giữ JDBC connection/resource. Request khác phải chờ; lock timeout xuất hiện nhiều hơn. Nếu gateway thành công nhưng database transaction rollback, hệ thống có thể thu tiền nhưng không có đơn.

Thiết kế thay thế:

~~~mermaid
flowchart TD
    A[Transaction 1: kiểm tra và giữ hàng] --> B[COMMIT; ghi outbox trong cùng transaction]
    B --> C[Worker gọi cổng thanh toán; không giữ DB transaction cũ]
    C --> D{Kết quả}
    D -->|Thành công| E[Transaction 2: xác nhận thanh toán]
    D -->|Thất bại| F[Transaction 3: hủy và giải phóng hàng]
    E --> G[Publish event giao hàng]
    F --> H[Thông báo hủy / retry theo chính sách]
~~~

Đây là **business transaction nhiều bước**. Mỗi bước DB ngắn có trạng thái bền vững, idempotency và compensation khi cần. Không cố kéo dài một transaction ACID qua payment gateway chỉ để giữ cảm giác “mọi thứ xảy ra cùng lúc”.

## 14. Deadlock thực tế có thể liên quan hơn hai row

Ví dụ cập nhật đơn hàng gồm:

1. Khóa PurchaseOrder.
2. Cập nhật Product stock.
3. Thêm OrderItem.
4. Ghi PaymentAttempt.
5. Cập nhật một bảng tổng hợp.

Một workflow khác có thể đi theo thứ tự ngược:

1. Khóa Product.
2. Ghi PaymentAttempt.
3. Khóa PurchaseOrder.

Ngay cả khi mọi Product đều được khóa theo ID tăng dần, hai workflow vẫn có thể tạo vòng chờ **PurchaseOrder ↔ Product**.

### 14.1. Quy ước thứ tự khóa toàn hệ thống

Ví dụ quy ước:

~~~text
1. Khóa PurchaseOrder nếu thao tác phụ thuộc trạng thái order.
2. Khóa Product / WarehouseStock theo ID tăng dần.
3. Khóa Reservation theo ID.
4. Ghi ledger/event/outbox.
5. Commit và nhả khóa.
~~~

Tất cả use case có cùng tập resource phải tuân thủ thứ tự hoặc có lý do được kiểm chứng để khác. Nhưng một số thao tác, trigger hoặc FK check có thể tự lấy khóa trong database mà code không nhìn thấy rõ, nên retry vẫn cần tồn tại.

### 14.2. Index ảnh hưởng thời gian giữ khóa

Một câu UPDATE/DELETE thiếu điều kiện index phù hợp có thể scan nhiều hàng, chạm nhiều row/lock hơn cần thiết hoặc giữ transaction lâu. Thêm chỉ mục đúng có thể giảm thời gian truy cập, nhưng quá nhiều index cũng làm INSERT/UPDATE phải duy trì thêm cấu trúc và có thể tạo đường khóa khác.

Ví dụ:

~~~sql
UPDATE purchase_orders
SET status = 'EXPIRED'
WHERE status = 'PENDING_PAYMENT'
  AND expires_at < now();
~~~

Nếu update cùng lúc hàng trăm nghìn đơn, transaction có thể giữ nhiều lock và gây contention. Một chiến lược batch theo ID/limit có kiểm soát, index phục vụ WHERE và mỗi batch commit riêng thường phù hợp hơn.

### 14.3. Foreign key và unique constraint cũng tham gia lock

Việc INSERT OrderItem tham chiếu Product hoặc DELETE Product có thể gây lock/cạnh tranh để bảo đảm referential integrity. INSERT các hàng có cùng unique key cũng có thể phải chờ transaction khác quyết định commit hay rollback.

Vì vậy “chỉ có SELECT FOR UPDATE mới có lock” là sai. **Mọi ghi SQL có thể lấy khóa**, và những ràng buộc DB có thể tạo phụ thuộc không hiển nhiên từ code Java.

## 15. Xây chính sách thất bại có giới hạn ở tầng API

Khi hết maxAttempts hoặc deadline, ứng dụng phải **kết thúc** thay vì tiếp tục vòng retry không xác định.

### 15.1. Trả lỗi đúng theo ý nghĩa

| Tình huống | Phản hồi API có thể phù hợp | Ý nghĩa với client |
|---|---|---|
| Request hợp lệ nhưng tài nguyên đang tranh chấp tạm thời | **503 Service Unavailable** hoặc mã ứng dụng “temporarily busy” | Có thể retry theo Retry-After khi server cho phép |
| Một hành động không thể thực hiện vì version/trạng thái đã thay đổi | **409 Conflict** | Client cần đọc lại state hoặc điều chỉnh request |
| Không đủ tồn kho | **409 Conflict** / lỗi nghiệp vụ có cấu trúc | Retry y nguyên thường không giải quyết |
| Client gửi quá nhiều request | **429 Too Many Requests** | Backoff theo rate-limit contract |
| Request chờ quá SLA tại gateway | Có thể thấy 504 ở proxy/gateway | Client cần query lại kết quả bằng requestId, không đoán rollback |

Không có một ánh xạ HTTP status bắt buộc cho mọi ORM exception. Quan trọng là:

- Không lộ stack trace/SQL/bind value cho client.
- Có **error code máy đọc được**, message phù hợp và correlationId.
- Có quy tắc **retryable** rõ ràng, chỉ dẫn backoff/Retry-After khi thích hợp.
- Với kết quả commit không chắc chắn, cung cấp endpoint truy vấn theo **operationId/idempotency key**.

Ví dụ response:

~~~json
{
  "code": "RESOURCE_BUSY",
  "message": "Yêu cầu chưa được xử lý vì tài nguyên đang bận",
  "retryable": true,
  "requestId": "transfer-2026-001"
}
~~~

**retryable:true** chỉ được trả nếu contract bảo đảm client gửi lại đúng **requestId** sẽ không thực hiện một thao tác logic hai lần. Nếu API chưa có idempotency, thông tin “hãy retry” có thể gây double-processing.

### 15.2. Circuit breaker và backpressure

Nếu database bắt đầu có hàng trăm request chờ cùng row, mỗi request retry ba lần có thể tăng tải gấp nhiều lần. Ngoài attempts/deadline, hệ thống có thể cần:

- Hạn chế số request cùng xử lý trên một resource hoặc tenant.
- Queue công việc khi không cần phản hồi đồng bộ.
- Rate limit/bulkhead để giữ pool connection và thread không cạn.
- Circuit breaker khi dependency bị lỗi dài hơn giới hạn tạm thời.
- Giảm đồng thời hoặc chuyển sang optimistic/atomic UPDATE nếu workload phù hợp.

Không nên dùng retry như cách che giấu nguyên nhân root: transaction quá dài, thứ tự khóa khác nhau, một job update hàng loạt hoặc thiếu index.

## 16. Chẩn đoán PostgreSQL: tìm ai đang chặn ai

Khi lock timeout tăng, câu hỏi đầu tiên là: **request nào đang chờ, nó chờ transaction nào, và transaction giữ khóa đang làm gì?**

### 16.1. pg_stat_activity và pg_blocking_pids

Một câu query quan sát:

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    age(clock_timestamp(), a.xact_start) AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 180) AS sql_text
FROM pg_stat_activity a
WHERE a.datname = current_database()
  AND a.pid <> pg_backend_pid()
ORDER BY a.xact_start NULLS LAST;
~~~

Ý nghĩa:

- **wait_event_type = 'Lock'** khi backend đang chờ loại lock được PostgreSQL báo cáo.
- **pg_blocking_pids(pid)** cho biết PID có thể đang chặn process đó.
- **transaction_age** dài có thể chỉ ra transaction giữ lock quá lâu.
- **state = 'idle in transaction'** thường đáng chú ý: ứng dụng mở transaction rồi không làm SQL tiếp nhưng vẫn giữ trạng thái/lock.

Quyền xem query và thông tin đầy đủ có thể bị giới hạn theo role; SQL text có thể chứa dữ liệu nhạy cảm. Không tự động **pg_terminate_backend** của process chỉ vì nó giữ lock mà chưa đánh giá tác động rollback/nghiệp vụ.

### 16.2. pg_locks

~~~sql
SELECT pid, locktype, mode, granted,
       relation::regclass AS relation_name
FROM pg_locks
WHERE pid <> pg_backend_pid()
ORDER BY pid, granted;
~~~

Đây là một góc nhìn về lock đang giữ/chờ. Trong PostgreSQL, **không phải mọi row-level lock đều luôn được hiển thị trực tiếp như một hàng tuple trong pg_locks**, vì nhiều thông tin row lock nằm trong dữ liệu tuple trên disk. Hãy dùng **pg_blocking_pids** và log/plan cùng pg_locks thay vì chỉ tìm row lock bằng mắt rồi kết luận không có.

### 16.3. Deadlock logs và tham số vận hành

PostgreSQL có thể ghi log deadlock với thông tin process và câu lệnh liên quan; cấu hình log phù hợp, **log_lock_waits** và **deadlock_timeout** giúp quan sát việc chờ. Ngoài ra, **pg_stat_database.deadlocks** là counter ở mức database, giúp phát hiện xu hướng nhưng không chỉ ra đúng endpoint gây lỗi.

Khi phân tích, kết hợp:

- Error log có **SQLSTATE 40P01/55P03**.
- Trace/correlationId của request.
- Tên use case, thứ tự resource/ID cần khóa.
- Thời gian bắt đầu/kết thúc transaction.
- Trạng thái connection pool và wait time.
- Câu SQL và EXPLAIN plan nếu có query chậm.

Không bật bind parameter logging ở production mặc định nếu dữ liệu có thông tin khách hàng, thanh toán hoặc bí mật. Các log điều tra cần masking/retention và quyền truy cập phù hợp.

### 16.4. Đo SQL thực tế từ Hibernate

~~~yaml
spring:
  jpa:
    open-in-view: false
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.transaction: TRACE
~~~

Chỉ bật TRACE ở môi trường phù hợp và trong thời gian ngắn. **Hibernate Statistics** cho biết số entity update/statement/flush, nhưng không trực tiếp đo thời gian một row lock bị giữ. Để xác định lock wait cần DB metrics và tracing quanh transaction.

### 16.5. Metrics nên thu thập

| Chỉ số | Dùng để phát hiện |
|---|---|
| Số lỗi SQLSTATE 40P01 theo endpoint/use case | Deadlock tăng ở workflow nào? |
| Số lỗi SQLSTATE 55P03 | Lock không lấy được trong timeout/NOWAIT |
| Số serialization failures 40001 | Tranh chấp dưới isolation mạnh |
| Lock-wait latency p50/p95/p99 | Tài nguyên thường xuyên bị chờ bao lâu |
| Transaction duration p95/p99 | Có transaction giữ lock quá lâu? |
| Retry attempts/success/exhausted | Retry có thực sự giúp hay chỉ tăng tải |
| Connection pool utilization/wait | Bị khóa DB hay thiếu connection? |
| Deadlock count PostgreSQL | Xu hướng deadlock ở cấp database |
| HTTP latency/timeout/queue depth | Ảnh hưởng thực tế tới người dùng |
| Số duplicate operationId và các lần deduplicate | Idempotency đang hoạt động đúng? |

**Phải phân biệt retry success rate và hiệu năng tổng thể.** Một endpoint retry thành công 99% nhưng p99 latency vượt nhiều giây và nhân tải DB lên ba lần vẫn là vấn đề cần cải tiến.

## 17. Thử nghiệm deadlock bằng hai session PostgreSQL

Đây là bài thực hành để hiểu hiện tượng, **chỉ thực hiện trên database test** với hai connection/transaction độc lập.

### 17.1. Chuẩn bị

~~~sql
CREATE TABLE lock_demo (
    id BIGINT PRIMARY KEY,
    counter INTEGER NOT NULL DEFAULT 0
);
INSERT INTO lock_demo(id) VALUES (1), (2);
~~~

Mở hai cửa sổ psql hoặc hai JDBC connections.

### 17.2. Trình tự tạo vòng chờ

| Thời điểm | Session A | Session B |
|---|---|---|
| T1 | BEGIN | BEGIN |
| T2 | UPDATE lock_demo SET counter = counter + 1 WHERE id = 1; | — |
| T3 | — | UPDATE lock_demo SET counter = counter + 1 WHERE id = 2; |
| T4 | UPDATE lock_demo SET counter = counter + 1 WHERE id = 2; (chờ B) | — |
| T5 | — | UPDATE lock_demo SET counter = counter + 1 WHERE id = 1; (chờ A) |
| T6 | PostgreSQL phát hiện deadlock và abort một giao dịch | Giao dịch còn lại có cơ hội tiếp tục |

Một session có thể nhận:

~~~text
ERROR: deadlock detected
SQLSTATE: 40P01
~~~

Sau lỗi, transaction bị abort phải **ROLLBACK**; session còn lại có thể tiếp tục và COMMIT. Nếu bạn đã đặt **lock_timeout quá thấp**, một transaction có thể bị hủy do 55P03 **trước khi** PostgreSQL phát hiện deadlock, nên để quan sát 40P01 cần bố trí timeout/thời điểm cho hợp lý.

### 17.3. Thử sửa thứ tự khóa

Chạy lại nhưng cả A và B đều UPDATE **id = 1 trước, id = 2 sau**. B có thể chờ id=1, nhưng không còn giữ id=2 trước khi lấy id=1 theo đường đã thiết kế. Thí nghiệm này minh họa lợi ích của lock ordering, **không phải bằng chứng rằng toàn hệ thống sẽ không bao giờ deadlock**.

## 18. Thử nghiệm lock timeout và NOWAIT

Trên database test có lock_demo:

**Session A:**

~~~sql
BEGIN;
UPDATE lock_demo SET counter = counter + 1 WHERE id = 1;
-- Chưa COMMIT, giữ transaction mở tạm thời để thử nghiệm.
~~~

**Session B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '250ms';
UPDATE lock_demo SET counter = counter + 1 WHERE id = 1;
-- Có thể lỗi 55P03 sau khi chờ quá giới hạn.
ROLLBACK;
~~~

Sau đó Session A COMMIT hoặc ROLLBACK. Lặp phép thử bằng:

~~~sql
BEGIN;
SELECT * FROM lock_demo WHERE id = 1 FOR UPDATE NOWAIT;
ROLLBACK;
~~~

Khi A còn giữ lock, B thường thất bại ngay với 55P03. So sánh thời gian chờ của hai trường hợp.

**Không mở transaction rồi để ngủ/quên trên production để “test lock”.** Nó có thể chặn request khác và tạo sự cố. Dùng dữ liệu và database test biệt lập, đặt timeout cho cả hai session, bảo đảm finally rollback/close dù assertion thất bại.

## 19. Integration test Hibernate/Spring với hai transaction thật

### 19.1. Vì sao test một thread không đủ?

Test đơn giản:

~~~java
@Transactional
@Test
void transferWorks() {
    // Gọi transfer và assert stock.
}
~~~

có thể chứng minh logic chức năng nhưng **không chứng minh deadlock/timeout dưới concurrency**. Một transaction không thể tự tạo xung đột row lock thật giữa hai session chỉ bằng cách gọi cùng repository hai lần trong một persistence context.

### 19.2. Thiết kế test hai worker

Dùng PostgreSQL Testcontainers, hai threads/connections độc lập và barrier để điều khiển:

1. T1 mở transaction A, lấy lock Product 101.
2. T2 mở transaction B, lấy lock Product 102.
3. Barrier cho phép cả hai tiếp tục tới lần lấy khóa thứ hai.
4. A đòi 102, B đòi 101.
5. Assert một bên nhận SQLSTATE 40P01 hoặc tình huống timeout phù hợp cấu hình; bên còn lại commit được.
6. Rollback/close tất cả session ở finally.

Với test NOWAIT, giữ Product 101 bị khóa trong A và để B dùng **PESSIMISTIC_WRITE/NOWAIT** trên 101. Assert B thất bại nhanh và trạng thái DB không có một transaction B commit dở dang.

### 19.3. Không dùng test transaction bao ngoài sai cách

Nếu test method chạy trong Spring **@Transactional**, các service con có REQUIRED có thể cùng tham gia transaction bao ngoài và cuối test tự rollback. Điều này có thể che việc transaction boundary thực sự nằm ở đâu. Đối với integration test concurrency:

- Không để test runner vô tình bao cả phép thử trong một transaction duy nhất.
- Dùng hai transaction/EntityManager riêng hoặc hai lời gọi worker bean được transaction manager kiểm soát.
- Dùng CountDownLatch/Phaser/barrier có timeout để tránh test treo mãi.
- Dùng **Future.get(timeout)** cho các thread.
- Kiểm tra dữ liệu cuối cùng **trong transaction/context mới**, không dựa vào object managed cũ.

Test có deadlock là test khó ổn định nếu chỉ dựa vào Thread.sleep(100); barrier điều phối chính xác thời điểm đã lấy khóa là quan trọng.

### 19.4. Test retry budget

Tách logic classifier và retry coordinator khỏi code SQL bằng interface/bean để có thể kiểm thử:

| Test | Kết quả mong muốn |
|---|---|
| Attempt đầu thành công | Thực hiện đúng 1 lần |
| Attempt 1 lỗi 40P01, attempt 2 thành công | Rollback attempt 1, thử transaction mới, tổng 2 attempts |
| Ba attempts đều 55P03 | Dừng đúng maxAttempts, trả OperationBusyException |
| Một lỗi IllegalArgumentException | Dừng ngay, không sleep/retry |
| Đã hết deadline trước attempt kế | Không mở thêm transaction |
| Thread bị interrupt khi backoff | Khôi phục interrupt flag và kết thúc |
| Two requests cùng operationId | Một thao tác logic, duplicate được nhận diện |
| Lỗi kết nối ngay lúc commit không rõ kết quả | Query theo operationId, không thực hiện mù quáng lần hai |

Nếu muốn test deadline không phụ thuộc đồng hồ thật, thiết kế inject **Clock/ticker/sleeper** qua abstraction; tránh benchmark timing cực ngắn trong CI quá tải. Điều quan trọng là **không có retry vô hạn hoặc transaction bị giữ trong lúc backoff**.

## 20. Checklist quyết định retry trong production

Trước khi bật retry cho một endpoint, trả lời các câu sau:

1. **Lỗi có thực sự tạm thời không?** Deadlock 40P01, serialization 40001 hoặc lock_not_available 55P03 theo policy? Hay là lỗi validation/constraint không thể tự hết?
2. **Transaction cũ đã rollback xong chưa?** Có dùng EntityManager mới/transaction mới cho attempt tiếp theo không?
3. **Có side effect bên ngoài không?** Email, cổng thanh toán, HTTP, broker có idempotency/outbox/compensation không?
4. **Có operationId bền vững không?** Nếu client retry do timeout không biết commit, làm sao xác nhận kết quả cũ?
5. **Số attempts và deadline là bao nhiêu?** Ai chịu trách nhiệm giới hạn tổng ngân sách?
6. **Backoff có jitter không?** Retry có diễn ra bên ngoài transaction không?
7. **Lock order có nhất quán không?** Có tài nguyên ngoài Product (Order, Reservation, FK) khiến chu trình vẫn có thể xảy ra?
8. **Có đo tỷ lệ lock wait/deadlock không?** Có biết endpoint và SQL gây cạnh tranh hay chỉ biết “database chậm”?
9. **Có trả lỗi hợp lý khi hết budget không?** Client biết tình huống retryable hay business conflict?
10. **Có test trên database thật không?** Cơ chế khóa và SQLSTATE của H2 không đại diện đầy đủ cho PostgreSQL.

### 20.1. Quy tắc lựa chọn nhanh

| Mục tiêu | Cơ chế đáng cân nhắc |
|---|---|
| Không cho hai request đồng thời vượt qua kiểm tra stock | Atomic UPDATE / row lock / @Version theo thiết kế |
| Chờ khóa tối đa một khoảng ngắn | PostgreSQL SET LOCAL lock_timeout, timeout phù hợp ở tầng JPA/Spring |
| Nếu bận thì phản hồi ngay | NOWAIT và thông báo resource busy |
| Nhiều worker lấy job độc lập | SKIP LOCKED + claim lease + idempotency |
| Tránh deadlock khi khóa nhiều row | Thứ tự khóa toàn hệ thống + transaction ngắn |
| Khôi phục từ deadlock/serialization conflict | Retry **toàn transaction mới**, có maxAttempts/deadline/backoff |
| Phối hợp DB với payment/email/broker | Outbox, saga/compensation, idempotency |
| Giao dịch dài do gọi HTTP | Tách I/O ngoài transaction và lưu state trung gian |
| Xác định blocker | pg_stat_activity, pg_blocking_pids, pg_locks, DB logs |

## 21. Những nhầm lẫn thường gặp

| Nhận định sai hoặc triệu chứng | Vì sao sai | Cách xử lý |
|---|---|---|
| “Chờ khóa lâu nghĩa là deadlock.” | Có thể chỉ là một transaction giữ lock lâu, không có chu trình. | Xem SQLSTATE, blocking PIDs và log. |
| “PostgreSQL lock_timeout = 0 là NOWAIT.” | Trong PostgreSQL 0 nghĩa là không giới hạn bởi lock_timeout. | Dùng FOR UPDATE NOWAIT hoặc hint được hỗ trợ. |
| “JPA lock timeout hint luôn chính xác 500ms.” | Provider/dialect và loại lock quyết định khả năng thực thi. | Kiểm tra generated SQL, kết hợp DB timeout. |
| “Deadlock sẽ hết nếu chờ lâu hơn.” | Chu trình chờ không tự tiến nếu không có transaction bị hủy. | Lock ordering, retry bounded sau rollback. |
| “Catch SQL exception rồi có thể tiếp tục transaction.” | PostgreSQL thường đánh dấu transaction aborted sau lỗi. | Rollback, mở transaction mới. |
| “Retry chỉ cần gọi lại repository method.” | May be cùng transaction lỗi, stale entity, hoặc side effect lặp. | Retry toàn use case trong context mới, idempotency. |
| “Ba lần retry thì chắc chắn xong.” | Lock vẫn có thể bận; lỗi có thể vĩnh viễn. | Có deadline, fallback, metrics và xử lý exhausted. |
| “JDBC batch làm hết deadlock.” | Batch không thay thế lock order/transaction boundary. | Xem thứ tự SQL và conflict thực tế. |
| “@Version là PESSIMISTIC_WRITE.” | Version chủ yếu phát hiện update conflict, không khóa row từ lúc đọc. | Chọn optimistic/pessimistic theo workload. |
| “SKIP LOCKED lấy đủ dữ liệu mà không chờ.” | Nó cố ý bỏ qua row đang khóa, kết quả không đầy đủ. | Chỉ dùng cho queue/claim phù hợp. |
| “Lỗi SQLSTATE 57014 luôn retry được.” | Có thể là query chậm, cancel do user hay deadline đã hết. | Phân loại nguyên nhân và ngân sách. |
| “HTTP request timeout nghĩa là DB rollback.” | DB có thể đã commit nhưng response bị mất. | OperationId và API kiểm tra kết quả. |
| “Thu tiền xong mà DB rollback thì tiền tự hoàn.” | API thanh toán ngoài local DB transaction. | Idempotency, outbox và compensation. |
| “Tăng connection pool luôn giảm lock wait.” | Nhiều connection hơn còn có thể tăng số transaction tranh chấp. | Giảm transaction dài, backpressure và tối ưu truy vấn. |
| “Một endpoint retry thành công là đủ tốt.” | Retry có thể tăng p99 latency và DB load nghiêm trọng. | Theo dõi exhausted, attempts, DB waits và business outcomes. |

## 22. Bài thực hành tổng hợp

Xây dựng ứng dụng Spring Boot + Hibernate + PostgreSQL có Product và một service chuyển số lượng giữa hai hàng để quan sát locking. Không gọi payment gateway thật hoặc chạy phép thử tạo deadlock trên production.

### Phần A — Phân biệt bốn lỗi

1. Tạo Product 101 và 102, giữ row lock 101 trong session A.
2. Session B dùng **FOR UPDATE NOWAIT**, ghi nhận thời gian và SQLSTATE.
3. Session B dùng **SET LOCAL lock_timeout = '300ms'**, thử khóa 101, quan sát khác biệt về thời gian chờ.
4. Tạo vòng chờ A:101→102 và B:102→101, ghi nhận deadlock victim với SQLSTATE 40P01.
5. Cho một query chậm bị statement_timeout để phân biệt SQLSTATE 57014 với lỗi lock timeout.

### Phần B — Cải thiện workflow

1. Tạo service chuyển số lượng mà khóa theo thứ tự input (dễ deadlock).
2. Đổi sang khóa theo ID tăng dần.
3. Thêm **@Version** và ràng buộc CHECK(stock_quantity >= 0).
4. Giới hạn lock_timeout trong transaction bằng SET LOCAL.
5. Thêm retry coordinator với tối đa 3 attempts, overall budget và jitter.
6. Xác nhận mỗi attempt thất bại đã rollback, không sleep trong transaction.

### Phần C — Đảm bảo kết quả nghiệp vụ

1. Cấp **operationId** duy nhất cho mỗi yêu cầu chuyển số lượng.
2. Thêm bảng ghi transfer_operations và unique constraint theo operationId trong cùng DB transaction.
3. Gửi lại cùng operationId nhiều lần và chứng minh không chuyển số lượng hai lần.
4. Giả lập mất kết nối sau khi transaction có thể đã commit; query theo operationId trước khi retry.
5. Thử gọi hệ thống ngoài trong transaction rồi phân tích rủi ro; thiết kế lại bằng outbox.

### Phần D — Monitoring và kết luận

1. Thu SQLSTATE 40P01/55P03/40001 theo tên use case.
2. Thu transaction duration và retry attempts.
3. Quan sát pg_blocking_pids, state idle in transaction và connection pool wait.
4. Chạy nhiều requests đồng thời ở mức kiểm soát, so sánh p95/p99 latency trước/sau lock ordering.
5. Viết bản giải thích: lỗi nào phải retry, lỗi nào phải trả ngay, vì sao maxAttempts/deadline cần cùng tồn tại.

**Kết quả cần đạt:** một thao tác đồng thời không làm sai tồn kho, không treo vô hạn, không tiếp tục transaction đã lỗi, không nhân đôi side effect, và trả kết quả rõ ràng khi tài nguyên tạm thời không khả dụng.

## 23. Nguyên tắc ghi nhớ

**Khóa là công cụ bảo đảm tính đúng, nhưng việc chờ khóa phải có ngân sách.** Khi hệ thống có nhiều transaction đồng thời:

1. **Lock contention bình thường** có thể kết thúc khi transaction giữ khóa commit/rollback.
2. **Lock timeout** là thất bại do vượt ngân sách chờ; **NOWAIT** chủ động từ chối chờ.
3. **Deadlock** là chu trình chờ giữa transaction; database phải phá vòng, thường bằng cách abort một transaction.
4. **Statement timeout, transaction timeout, pool timeout và HTTP timeout** là các lớp khác nhau; không trộn chúng thành một chính sách duy nhất.
5. Với PostgreSQL, **40P01, 55P03, 40001 và 57014** giúp phân loại nguyên nhân, nhưng retry còn phải xét semantics nghiệp vụ.
6. **Rollback transaction cũ trước khi retry**. Mỗi attempt mới phải có transaction/persistence context mới, đọc lại state và kiểm tra invariants.
7. **Giới hạn số lần, deadline, backoff và jitter**; hết ngân sách phải trả lỗi có kiểm soát thay vì retry mãi.
8. **Thứ tự khóa ổn định và transaction ngắn** thường giảm contention/deadlock hiệu quả hơn việc chỉ tăng timeout.
9. **Idempotency** bảo vệ kết quả khi cùng yêu cầu được gửi lại, đặc biệt khi một commit hoặc API call đã thành công nhưng client không nhận được phản hồi.
10. **Quan sát SQL thực tế, PostgreSQL blockers và thử nghiệm hai transaction** để hiểu hệ thống đang chờ gì trước khi tối ưu.

Một hệ thống dùng Hibernate vững vàng không phải hệ thống “không bao giờ có deadlock”. Đó là hệ thống **giảm xác suất deadlock bằng thiết kế nhất quán, phát hiện và rollback đúng khi nó xảy ra, thử lại có giới hạn khi an toàn, rồi kết thúc minh bạch khi vẫn không thể hoàn tất**.
