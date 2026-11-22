# Retry có giới hạn, tính lặp an toàn và giao dịch mới sau lỗi

## Mục tiêu

Trong hệ thống Spring Data JPA, một transaction có thể thất bại tạm thời vì optimistic locking conflict, deadlock, không lấy được lock hoặc lỗi tài nguyên database. Retry giúp ứng dụng thử lại một thao tác khi nguyên nhân có khả năng biến mất. Tuy nhiên, retry không an toàn nếu chạy vô hạn, lặp lại side effect hoặc dùng lại transaction đã rollback.

Ba nguyên tắc phải đi cùng nhau:

1. **Retry có giới hạn:** đặt số lần thử tối đa, thời gian chờ tăng dần, jitter và deadline phù hợp.
2. **Tính lặp an toàn (idempotency):** cùng một yêu cầu được gửi lại nhiều lần vẫn chỉ tạo một hiệu ứng nghiệp vụ và trả lại cùng kết quả đã ghi nhận.
3. **Giao dịch mới sau lỗi:** mỗi lần thử phải chạy trong transaction/persistence context mới; lỗi transaction trước phải được rollback trước khi retry.

Bài này phân loại lỗi có thể retry, giải thích transaction boundary và idempotency key, xử lý trường hợp không biết transaction đã commit hay chưa, trình bày outbox cho side effect bên ngoài và cung cấp ví dụ Java 17+ chạy được với Spring Boot, Spring Data JPA và H2.

## 1. Vì sao cần retry?

Không phải mọi lỗi database đều là lỗi vĩnh viễn. Một số lỗi có thể biến mất nếu thao tác được thực hiện lại sau khi transaction cạnh tranh kết thúc:

- Optimistic locking conflict: một transaction khác đã cập nhật version trước.
- Deadlock: database chọn hủy một transaction để giải phóng vòng chờ khóa.
- Lock timeout hoặc không lấy được lock: tài nguyên đang bị transaction khác giữ.
- Lỗi tài nguyên tạm thời: kết nối bị gián đoạn hoặc database tạm thời không sẵn sàng.

Ví dụ entity có `@Version`: hai transaction cùng đọc version 4. Transaction A cập nhật và commit version 5. Transaction B vẫn cố ghi dựa trên version 4, nên UPDATE của B không khớp hàng nào và JPA báo optimistic locking failure. Nếu nghiệp vụ vẫn hợp lệ sau khi đọc lại dữ liệu mới, ứng dụng có thể chạy lại toàn bộ use case trong transaction mới.

Retry không làm một thao tác sai trở thành đúng. Nếu số dư không đủ, sản phẩm hết hàng, dữ liệu không hợp lệ hoặc người dùng không có quyền, thử lại cùng input thường vẫn thất bại. Các lỗi nghiệp vụ này cần được trả về caller hoặc xử lý theo quy tắc riêng.

## 2. Phân biệt lỗi retry được và lỗi không retry

Chỉ retry những lỗi có khả năng tạm thời và có thể phục hồi bằng cách chạy lại toàn bộ thao tác:

| Nhóm lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Xung đột đồng thời | `OptimisticLockingFailureException`, `PessimisticLockingFailureException` | Có thể retry nếu use case được thiết kế an toàn và còn thời gian. |
| Deadlock/lock tạm thời | `DeadlockLoserDataAccessException`, `CannotAcquireLockException` | Có thể retry transaction mới với backoff. |
| Tài nguyên tạm thời | Một số `TransientDataAccessResourceException` | Chỉ retry khi biết thao tác có thể thực hiện lại an toàn. |
| Vi phạm dữ liệu | `DataIntegrityViolationException`, unique/check/foreign-key violation | Thông thường không retry; sửa dữ liệu hoặc xử lý duplicate theo idempotency. |
| Lỗi nghiệp vụ | Hết hàng, số dư không đủ, reservation đã tồn tại | Không retry tự động với cùng điều kiện. |
| Lỗi đầu vào/quyền | Validation, authentication, authorization | Không retry. |
| Lỗi query/cấu hình | JPQL sai, mapping sai, schema thiếu cột | Không retry; sửa code hoặc schema. |

Spring có hierarchy `DataAccessException`. `TransientDataAccessException` là một nhóm lỗi được xem là có thể tạm thời; optimistic/pessimistic locking failures thường nằm trong nhánh concurrency tương ứng. Dù vậy, không nên bắt mọi `DataAccessException` rồi retry: lỗi không transient có thể lặp lại mãi và che mất nguyên nhân thật.

Phân loại exception cụ thể còn phụ thuộc JPA provider, JDBC driver và database. Hãy quan sát exception thực tế trên database production và chỉ thêm loại lỗi vào retry policy khi đã xác nhận semantics.

## 3. Giới hạn số lần thử

Retry phải có giới hạn. Một policy thường quy định:

- `maxAttempts`: tổng số lần gọi, bao gồm lần đầu tiên.
- `initialDelay`: thời gian chờ sau lần thất bại đầu tiên.
- `maxDelay`: mức chờ tối đa.
- `multiplier`: hệ số tăng delay, thường là 2.
- `jitter`: độ ngẫu nhiên thêm vào delay để nhiều client không retry cùng một thời điểm.
- `deadline`: thời gian tối đa mà request hoặc job được phép tiếp tục.

Ví dụ policy:

```text
maxAttempts = 4
initialDelay = 50 ms
multiplier = 2
maxDelay = 500 ms
jitter = 50% .. 100% của delay
```

Delay cơ sở tăng như sau:

| Lần thất bại | Delay cơ sở trước jitter |
| ---: | ---: |
| 1 | 50 ms |
| 2 | 100 ms |
| 3 | 200 ms |

Với 4 lần thử, sau lần thất bại thứ tư ứng dụng dừng và trả lỗi cuối cùng. Jitter làm thời điểm retry của các client lệch nhau, giảm hiện tượng thundering herd khi database vừa phục hồi.

Không đặt `maxAttempts` quá cao để bù cho transaction thiết kế sai. Cân nhắc latency của API, timeout của HTTP caller, thời gian giữ request và giới hạn tài nguyên database. Một retry có thể kéo dài hơn deadline của request, khiến caller timeout trong khi server vẫn đang làm việc.

## 4. Backoff và jitter

Exponential backoff tăng thời gian chờ theo cấp số nhân:

```java
long delay = Math.min(maxDelay, initialDelay * (1L << failedAttempt));
```

Không nên để tất cả client dùng cùng một delay cố định. Nếu hàng nghìn request cùng thất bại và cùng retry sau 100 ms, chúng lại tạo một đợt tải đồng thời.

Jitter có thể chọn một giá trị ngẫu nhiên trong khoảng 50% đến 100% delay cơ sở:

```java
long actualDelay = ThreadLocalRandom.current()
        .nextLong(Math.max(1, delay / 2), delay + 1);
```

Giới hạn phép nhân để tránh overflow và luôn cap tại `maxDelay`. Khi test, có thể inject clock/sleeper hoặc dùng delay bằng 0 để test số lần gọi mà không làm test chậm.

### Không retry mãi khi database đang quá tải

Retry làm tăng số request gửi tới database. Nếu database đang quá tải, retry vô hạn có thể khiến tình trạng nặng hơn. Dùng số lần thử nhỏ, backoff có jitter, connection pool hợp lý và circuit breaker/bulkhead khi hệ thống cần bảo vệ tài nguyên ở quy mô lớn.

Đối với job nền, có thể lưu trạng thái lần thử và lịch retry vào hàng đợi thay vì giữ một thread ngủ lâu. Với API đồng bộ, nếu đã hết deadline, trả lỗi tạm thời phù hợp để caller quyết định thử lại sau.

## 5. Mỗi lần thử phải có transaction mới

Đây là quy tắc quan trọng nhất khi retry thao tác JPA:

**Không bắt lỗi trong transaction đã thất bại rồi tiếp tục dùng transaction đó.**

Khi optimistic lock, deadlock hoặc lỗi persistence xảy ra, transaction có thể đã bị đánh dấu rollback-only. Persistence context cũng có thể chứa entity với trạng thái không còn phù hợp với database. Việc gọi lại repository trong cùng transaction có thể tiếp tục thất bại hoặc dẫn đến `UnexpectedRollbackException` khi commit.

Luồng đúng:

```text
Retry facade (không giữ transaction)
    |
    +-- attempt 1 --> Transaction mới A --> lỗi --> rollback A
    |
    +-- backoff
    |
    +-- attempt 2 --> Transaction mới B --> đọc lại state --> commit/rollback B
    |
    +-- ... tối đa maxAttempts
```

Có thể triển khai bằng hai Spring bean riêng:

- `RetryFacade`: điều khiển số lần thử và backoff; không mở transaction bao quanh vòng lặp.
- `TransactionalWorker`: thực hiện một lần nghiệp vụ trong `@Transactional(propagation = REQUIRES_NEW)`.

Mỗi lần retry gọi worker qua Spring proxy, nên transaction interceptor tạo transaction mới. Nếu worker ném runtime exception, transaction của lần đó rollback trước khi exception quay lại facade.

### Vì sao tách thành hai bean?

Spring áp dụng `@Transactional` qua proxy. Nếu một method trong class gọi trực tiếp method khác cùng class (self-invocation), lời gọi nội bộ thường không đi qua proxy, nên annotation trên method được gọi có thể không được áp dụng như mong đợi.

Tách retry facade và transactional worker thành hai bean làm ranh giới rõ ràng: facade gọi worker qua proxy ở mỗi lần thử.

### REQUIRES_NEW và NOT_SUPPORTED

`REQUIRES_NEW` tạo transaction mới cho mỗi lần thực hiện, tạm treo transaction đang có nếu có. Retry facade có thể dùng `NOT_SUPPORTED` để bảo đảm vòng lặp không nằm trong một transaction bên ngoài.

Không phải mọi ứng dụng đều cần cả hai annotation. Điều cốt lõi là transaction lỗi đã kết thúc trước khi lần thử mới bắt đầu và lần thử mới có persistence context riêng.

## 6. Idempotency: cùng yêu cầu, cùng hiệu ứng

Retry có thể gửi cùng một lệnh nhiều lần. Nhưng cùng một nghiệp vụ có thể bị gọi lặp do:

- Client timeout và gửi lại request dù server đã commit.
- Gateway hoặc message broker giao lại message.
- Server retry sau lỗi kết nối trong lúc chưa biết commit đã thành công hay chưa.
- Người dùng nhấn nút nhiều lần.

Idempotency nghĩa là xử lý cùng một request identity nhiều lần không nhân đôi hiệu ứng nghiệp vụ. Cách phổ biến là yêu cầu client gửi **idempotency key** duy nhất cho một thao tác logic.

Ví dụ:

```http
POST /purchases
Idempotency-Key: order-2026-000123
```

Server lưu key cùng payload quan trọng và kết quả. Nếu cùng key, cùng payload được gửi lại, server trả kết quả đã lưu mà không trừ tồn kho lần nữa.

### Unique constraint phải ở database

Không chỉ gọi `existsByRequestKey(key)` rồi mới insert. Hai transaction có thể cùng kiểm tra và cùng thấy key chưa tồn tại. Hãy tạo unique constraint trên idempotency key:

```sql
create table processed_requests (
    id bigint generated by default as identity primary key,
    request_key varchar(100) not null unique,
    item_id bigint not null,
    quantity integer not null,
    remaining_after integer not null
);
```

Database là nơi phân xử hai request cùng key. Một transaction insert thành công; transaction còn lại chờ rồi nhận unique violation nếu transaction đầu commit.

Trong hệ thống multi-tenant hoặc có nhiều loại command, key nên được scope theo tenant và operation type, ví dụ unique `(tenant_id, operation_type, request_key)`, để tránh hai khách hàng vô tình dùng cùng chuỗi key.

### Cùng key nhưng payload khác phải bị từ chối

Không được trả kết quả cũ cho một request có cùng key nhưng nội dung khác. Lưu những trường đủ để so sánh hoặc lưu hash của payload đã chuẩn hóa.

Ví dụ key `order-123` lần đầu mua item 10 số lượng 2; lần sau cùng key nhưng mua item 11 số lượng 5. Server phải báo idempotency key reuse conflict, không trả kết quả của đơn hàng đầu như thể request thứ hai đã được thực hiện.

Trong ví dụ cuối bài, payload được so sánh bằng `itemId` và `quantity`. Với request phức tạp, dùng canonical payload hash và đưa user/tenant cùng operation type vào phạm vi key.

## 7. Ghi idempotency record và nghiệp vụ trong cùng transaction

Để bảo đảm database không ghi nhận request thành công nhưng không thực hiện nghiệp vụ (hoặc ngược lại), ghi operation record và cập nhật dữ liệu nghiệp vụ trong **cùng một transaction**:

```text
BEGIN
  INSERT processed_request(request_key, payload...)
  UPDATE inventory ...
  UPDATE processed_request SET result = ...
COMMIT
```

Nếu update tồn kho thất bại hoặc transaction rollback, bản ghi idempotency cũng rollback. Khi retry, transaction mới có thể thử insert cùng key và thực hiện lại.

Nếu commit thành công nhưng response bị mất trên đường về client, lần gọi lại tìm thấy idempotency record đã commit và trả kết quả cũ. Đây là lý do idempotency record phải được commit cùng thay đổi nghiệp vụ.

### Xử lý request trùng đang chạy

Hai request cùng key có thể cùng đọc ban đầu và chưa thấy record. Cả hai thử insert:

1. Transaction đầu insert key và tiếp tục nghiệp vụ.
2. Transaction thứ hai insert cùng key; unique constraint khiến nó chờ transaction đầu.
3. Nếu transaction đầu commit, transaction thứ hai nhận duplicate-key violation.
4. Transaction thứ hai rollback; facade đọc record đã commit bằng transaction đọc mới và trả lại kết quả.

Nếu transaction đầu rollback, transaction thứ hai có thể insert thành công và trở thành request thực hiện nghiệp vụ.

Không bắt duplicate-key rồi tiếp tục truy vấn trong chính transaction đã lỗi. Transaction đó phải rollback trước; sau đó dùng bean đọc riêng hoặc transaction mới để lấy kết quả đã lưu.

### Có nên lưu kết quả thất bại nghiệp vụ?

Ví dụ mua hàng hết tồn kho. Có hai chính sách:

- **Không lưu lỗi nghiệp vụ:** transaction rollback cả idempotency record. Nếu tồn kho được bổ sung, cùng key có thể được thử lại và thành công. Ví dụ cuối bài dùng chính sách này.
- **Lưu kết quả từ chối:** ghi trạng thái REJECTED cùng response theo chính sách idempotency. Khi đó cần thiết kế transaction rõ ràng để lưu kết quả từ chối mà không trừ tồn kho.

Chọn chính sách theo hợp đồng API. Đừng vô tình lưu một request đang dở dang như thể đã hoàn tất.

## 8. Retry khi không biết commit đã xảy ra hay chưa

Một tình huống khó là kết nối bị đứt trong lúc commit. Ứng dụng nhận exception nhưng không biết database đã commit hay chưa.

Không thể giải quyết tình huống này chỉ bằng cách nhìn exception và đoán. Idempotency key cho phép thử lại an toàn:

- Nếu transaction cũ rollback, key chưa tồn tại; lần thử mới có thể thực hiện.
- Nếu transaction cũ commit, key đã tồn tại; lần thử mới gặp duplicate key, rollback rồi đọc lại kết quả cũ.

Facade nên phân biệt duplicate do idempotency key với các vi phạm dữ liệu khác bằng cách đọc record theo key sau rollback và so khớp payload. Nếu không tìm thấy record phù hợp, ném lại lỗi gốc.

Đây là cơ chế phục hồi cho kết quả commit không rõ ràng. Nó không có nghĩa mọi side effect ngoài database tự động exactly-once.

## 9. Side effect bên ngoài và transactional outbox

Giả sử transaction trừ tồn kho và sau đó gửi email hoặc gọi payment gateway. Database transaction không thể rollback email đã gửi hoặc HTTP request đã được hệ thống khác xử lý.

Không nên đặt side effect bên ngoài vào vòng retry một cách ngây thơ:

```text
Attempt 1:
  update database
  charge payment gateway successfully
  database commit fails

Attempt 2:
  update database again
  charge payment gateway again
```

Khách hàng có thể bị tính phí hai lần.

Với side effect cần giao nhận tin cậy, dùng **transactional outbox**:

1. Trong cùng transaction database, ghi thay đổi nghiệp vụ, idempotency result và một outbox event.
2. Commit transaction.
3. Worker riêng đọc outbox và gửi message/API.
4. Đánh dấu event đã gửi hoặc lưu trạng thái giao nhận.
5. Consumer/downstream dùng event ID hoặc idempotency key để loại xử lý trùng.

Outbox bảo đảm thay đổi nghiệp vụ và ý định phát event được ghi nguyên tử trong database. Việc gửi ra ngoài vẫn có thể lặp; consumer cần idempotent. Với payment provider, gửi idempotency key tương ứng nếu API hỗ trợ.

Không tuyên bố exactly-once cho toàn hệ thống chỉ vì đã có outbox. Thực tế thường là at-least-once delivery kết hợp deduplication để đạt hiệu ứng xử lý một lần.

## 10. Những gì không nên retry

- Validation error hoặc dữ liệu đầu vào sai.
- Người dùng không có quyền.
- Business rule từ chối như hết hàng, số dư không đủ, tài khoản đóng.
- Unique violation không liên quan idempotency key.
- Query syntax, mapping hoặc schema error.
- Request vượt deadline hoặc caller đã hủy.
- Side effect không idempotent mà chưa có cơ chế deduplication.

Nếu retry một lỗi không thể tự biến mất, hệ thống chỉ tăng tải, kéo dài latency và che mất lỗi gốc.

## 11. Chọn retry trong code hay thư viện?

### Vòng lặp retry tường minh

Vòng lặp nhỏ tự viết phù hợp khi cần kiểm soát rõ exception, số lần thử, backoff và transaction boundary. Nó dễ đọc trong một use case hẹp và không cần thêm dependency.

### Spring Retry

Spring Retry cung cấp `@Retryable`, `@Recover` và các policy. Dùng khi ứng dụng đã có dependency/cấu hình phù hợp và muốn khai báo retry theo annotation.

Vẫn cần kiểm tra:

- Retry advice phải bao ngoài transaction advice để mỗi lần thử đi qua transaction interceptor mới.
- Method được gọi qua Spring proxy; self-invocation không kích hoạt retry/transaction advice.
- `@Recover` không được dùng để giả vờ nghiệp vụ thành công khi mọi lần thử đều thất bại.
- Exception classifier phải chỉ chọn lỗi thực sự retry được.
- Không để retry và transaction nằm cùng một proxy theo thứ tự khiến nhiều lần thử dùng chung transaction.

### Resilience4j

Resilience4j Retry phù hợp khi hệ thống đã dùng các resilience module của thư viện này. Có thể cấu hình số lần thử, wait interval, exponential backoff và exception predicate.

Dù dùng thư viện nào, nguyên tắc vẫn giữ nguyên: retry facade ở ngoài transaction, worker tạo transaction mới, request có idempotency key và chỉ retry lỗi tạm thời.

## 12. Ví dụ chạy được với Java 17+, Spring Boot 3.4.5 và H2

Ví dụ tạo một sản phẩm tồn kho. Một yêu cầu mua hàng có `requestKey`, `itemId` và `quantity`. Transaction worker:

1. Insert idempotency record với unique request key.
2. Đọc item có `@Version`.
3. Kiểm tra số lượng và giảm tồn kho.
4. Lưu số lượng còn lại vào idempotency record.
5. Commit cả hai thay đổi.

Facade kiểm tra request đã hoàn tất chưa, retry các lỗi transient tối đa ba lần và xử lý duplicate key bằng cách đọc lại kết quả đã commit.

### Cấu trúc dự án

```text
bounded-retry-idempotency/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/retry/
    │   │   ├── RetryApplication.java
    │   │   ├── InventoryItem.java
    │   │   ├── ProcessedRequest.java
    │   │   ├── InventoryRepository.java
    │   │   ├── ProcessedRequestRepository.java
    │   │   ├── PurchaseCommand.java
    │   │   ├── PurchaseResult.java
    │   │   ├── PurchaseReceipt.java
    │   │   ├── BoundedRetryExecutor.java
    │   │   ├── PurchaseTransactionService.java
    │   │   ├── PurchaseLookupService.java
    │   │   └── PurchaseService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/retry/BoundedRetryExecutorTest.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bounded-retry-idempotency</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:retrydb;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `InventoryItem.java`

```java
package com.example.retry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.Check;

@Entity
@Table(name = "inventory_items")
@Check(constraints = "available >= 0")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int available) {
        this.sku = sku;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }

    public void decrease(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new OutOfStockException("Insufficient stock");
        }
        available -= quantity;
    }
}
```

### `ProcessedRequest.java`

```java
package com.example.retry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "processed_requests")
public class ProcessedRequest {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_key", nullable = false, unique = true, length = 100)
    private String requestKey;

    @Column(nullable = false)
    private Long itemId;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false)
    private int remainingAfter;

    protected ProcessedRequest() {
    }

    public ProcessedRequest(String requestKey, Long itemId, int quantity) {
        this.requestKey = requestKey;
        this.itemId = itemId;
        this.quantity = quantity;
    }

    public void complete(int remainingAfter) {
        this.remainingAfter = remainingAfter;
    }

    public String getRequestKey() {
        return requestKey;
    }

    public Long getItemId() {
        return itemId;
    }

    public int getQuantity() {
        return quantity;
    }

    public int getRemainingAfter() {
        return remainingAfter;
    }
}
```

### Repository interfaces

`InventoryRepository.java`:

```java
package com.example.retry;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
}
```

`ProcessedRequestRepository.java`:

```java
package com.example.retry;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProcessedRequestRepository extends JpaRepository<ProcessedRequest, Long> {
    Optional<ProcessedRequest> findByRequestKey(String requestKey);
}
```

### Command and result records

`PurchaseCommand.java`:

```java
package com.example.retry;

public record PurchaseCommand(String requestKey, Long itemId, int quantity) {
}
```

`PurchaseResult.java`:

```java
package com.example.retry;

public record PurchaseResult(String requestKey, int remaining) {
}
```

`PurchaseReceipt.java`:

```java
package com.example.retry;

public record PurchaseReceipt(
        String requestKey, Long itemId, int quantity, int remainingAfter) {
}
```

### `BoundedRetryExecutor.java`

```java
package com.example.retry;

import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Component;

@Component
public class BoundedRetryExecutor {
    private final int maxAttempts;
    private final long initialDelayMillis;
    private final long maxDelayMillis;

    public BoundedRetryExecutor() {
        this(3, 20, 250);
    }

    BoundedRetryExecutor(int maxAttempts, long initialDelayMillis, long maxDelayMillis) {
        if (maxAttempts < 1 || initialDelayMillis < 0 || maxDelayMillis < 0
                || maxDelayMillis < initialDelayMillis) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
        this.maxAttempts = maxAttempts;
        this.initialDelayMillis = initialDelayMillis;
        this.maxDelayMillis = maxDelayMillis;
    }

    public <T> T execute(Supplier<T> operation) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return operation.get();
            } catch (TransientDataAccessException failure) {
                if (attempt == maxAttempts) {
                    throw failure;
                }
                sleep(backoffWithJitter(attempt));
            }
        }
        throw new IllegalStateException("Retry loop ended unexpectedly");
    }

    private long backoffWithJitter(int failedAttempt) {
        if (initialDelayMillis == 0 || maxDelayMillis == 0) {
            return 0;
        }

        long base = initialDelayMillis;
        for (int i = 1; i < failedAttempt && base < maxDelayMillis; i++) {
            base = Math.min(maxDelayMillis, base * 2);
        }

        long lowerBound = Math.max(1, base / 2);
        return ThreadLocalRandom.current().nextLong(lowerBound, base + 1);
    }

    private void sleep(long millis) {
        if (millis == 0) {
            return;
        }
        try {
            Thread.sleep(millis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new RetryInterruptedException("Retry interrupted", interrupted);
        }
    }

    public static class RetryInterruptedException extends RuntimeException {
        public RetryInterruptedException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Executor chỉ bắt `TransientDataAccessException`. `DataIntegrityViolationException`, `OutOfStockException` và `IllegalArgumentException` không thuộc nhóm retry này nên được trả ra ngay.

### `PurchaseTransactionService.java`

```java
package com.example.retry;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseTransactionService {
    private final InventoryRepository inventoryRepository;
    private final ProcessedRequestRepository requestRepository;

    public PurchaseTransactionService(
            InventoryRepository inventoryRepository,
            ProcessedRequestRepository requestRepository) {
        this.inventoryRepository = inventoryRepository;
        this.requestRepository = requestRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public PurchaseResult purchaseOnce(PurchaseCommand command) {
        ProcessedRequest operation = requestRepository.saveAndFlush(
                new ProcessedRequest(
                        command.requestKey(), command.itemId(), command.quantity()));

        InventoryItem item = inventoryRepository.findById(command.itemId())
                .orElseThrow(() -> new ItemNotFoundException(command.itemId()));

        item.decrease(command.quantity());
        inventoryRepository.flush();

        operation.complete(item.getAvailable());
        requestRepository.flush();

        return new PurchaseResult(command.requestKey(), item.getAvailable());
    }

    public static class ItemNotFoundException extends RuntimeException {
        public ItemNotFoundException(Long itemId) {
            super("Inventory item not found: " + itemId);
        }
    }

    public static class OutOfStockException extends RuntimeException {
        public OutOfStockException(String message) {
            super(message);
        }
    }
}
```

`saveAndFlush` claim idempotency key ngay trong transaction. `@Version` trên `InventoryItem` khiến concurrent update cùng version phát sinh optimistic locking conflict. Khi `flush()` thất bại, transaction này rollback; operation record cũng rollback theo.

### `PurchaseLookupService.java`

```java
package com.example.retry;

import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseLookupService {
    private final ProcessedRequestRepository repository;

    public PurchaseLookupService(ProcessedRequestRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true, propagation = Propagation.REQUIRES_NEW)
    public Optional<PurchaseReceipt> find(String requestKey) {
        return repository.findByRequestKey(requestKey)
                .map(row -> new PurchaseReceipt(
                        row.getRequestKey(), row.getItemId(),
                        row.getQuantity(), row.getRemainingAfter()));
    }
}
```

Lookup chạy trong transaction đọc mới. Nó được gọi sau khi transaction ghi thất bại đã rollback, nên không truy vấn bằng persistence context lỗi.

### `PurchaseService.java`

```java
package com.example.retry;

import java.util.Optional;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseService {
    private final PurchaseLookupService lookupService;
    private final PurchaseTransactionService transactionService;
    private final BoundedRetryExecutor retryExecutor;

    public PurchaseService(
            PurchaseLookupService lookupService,
            PurchaseTransactionService transactionService,
            BoundedRetryExecutor retryExecutor) {
        this.lookupService = lookupService;
        this.transactionService = transactionService;
        this.retryExecutor = retryExecutor;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public PurchaseResult purchase(PurchaseCommand command) {
        validate(command);

        Optional<PurchaseReceipt> previous = lookupService.find(command.requestKey());
        if (previous.isPresent()) {
            return replayOrReject(command, previous.get());
        }

        try {
            return retryExecutor.execute(
                    () -> transactionService.purchaseOnce(command));
        } catch (DataIntegrityViolationException possibleDuplicateKey) {
            Optional<PurchaseReceipt> committed =
                    lookupService.find(command.requestKey());
            if (committed.isPresent()) {
                return replayOrReject(command, committed.get());
            }
            throw possibleDuplicateKey;
        }
    }

    private PurchaseResult replayOrReject(
            PurchaseCommand command, PurchaseReceipt receipt) {
        boolean samePayload = receipt.itemId().equals(command.itemId())
                && receipt.quantity() == command.quantity();
        if (!samePayload) {
            throw new IdempotencyKeyReuseException(
                    "Request key was already used with a different payload");
        }
        return new PurchaseResult(receipt.requestKey(), receipt.remainingAfter());
    }

    private void validate(PurchaseCommand command) {
        if (command == null || command.requestKey() == null
                || command.requestKey().isBlank() || command.requestKey().length() > 100
                || command.itemId() == null || command.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid purchase command");
        }
    }

    public static class IdempotencyKeyReuseException extends RuntimeException {
        public IdempotencyKeyReuseException(String message) {
            super(message);
        }
    }
}
```

`PurchaseService` không giữ transaction trong vòng retry. Mỗi lần gọi `purchaseOnce` đi qua proxy của bean `PurchaseTransactionService`, nên nhận transaction mới. Khi gặp duplicate key, service tra lại request đã commit; nếu không tìm thấy record tương ứng thì ném lại lỗi gốc.

### `RetryApplication.java`

```java
package com.example.retry;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RetryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RetryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            InventoryRepository inventoryRepository, PurchaseService purchaseService) {
        return args -> {
            InventoryItem item = inventoryRepository.saveAndFlush(
                    new InventoryItem("SKU-1", 5));

            PurchaseCommand firstCommand =
                    new PurchaseCommand("order-1001", item.getId(), 2);

            PurchaseResult first = purchaseService.purchase(firstCommand);
            PurchaseResult replay = purchaseService.purchase(firstCommand);

            System.out.println("First call remaining: " + first.remaining());
            System.out.println("Replay same key remaining: " + replay.remaining());
            System.out.println("Stock after replay: "
                    + inventoryRepository.findById(item.getId()).orElseThrow().getAvailable());

            PurchaseResult secondOrder = purchaseService.purchase(
                    new PurchaseCommand("order-1002", item.getId(), 2));
            System.out.println("Second order remaining: " + secondOrder.remaining());
        };
    }
}
```

### `BoundedRetryExecutorTest.java`

```java
package com.example.retry;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.dao.TransientDataAccessResourceException;

class BoundedRetryExecutorTest {
    @Test
    void retriesTransientFailureButStopsAfterSuccess() {
        BoundedRetryExecutor executor = new BoundedRetryExecutor(3, 0, 0);
        AtomicInteger calls = new AtomicInteger();

        String result = executor.execute(() -> {
            if (calls.incrementAndGet() < 3) {
                throw new TransientDataAccessResourceException("temporary");
            }
            return "done";
        });

        assertThat(result).isEqualTo("done");
        assertThat(calls.get()).isEqualTo(3);
    }

    @Test
    void doesNotRetryBusinessFailure() {
        BoundedRetryExecutor executor = new BoundedRetryExecutor(3, 0, 0);
        AtomicInteger calls = new AtomicInteger();

        assertThatThrownBy(() -> executor.execute(() -> {
            calls.incrementAndGet();
            throw new IllegalArgumentException("invalid request");
        })).isInstanceOf(IllegalArgumentException.class);

        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    void stopsWhenMaximumAttemptsAreExhausted() {
        BoundedRetryExecutor executor = new BoundedRetryExecutor(3, 0, 0);
        AtomicInteger calls = new AtomicInteger();

        assertThatThrownBy(() -> executor.execute(() -> {
            calls.incrementAndGet();
            throw new TransientDataAccessResourceException("still unavailable");
        })).isInstanceOf(TransientDataAccessResourceException.class);

        assertThat(calls.get()).isEqualTo(3);
    }
}
```

### Chạy chương trình và test

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Stdout:

```text
First call remaining: 3
Replay same key remaining: 3
Stock after replay: 3
Second order remaining: 1
```

Chạy unit test:

```bash
mvn test
```

Ba test xác nhận executor thử lại lỗi transient đúng số lần, không retry lỗi đầu vào và dừng khi hết `maxAttempts`. Demo ứng dụng xác nhận cùng idempotency key không trừ tồn kho lần thứ hai. Đoạn test executor không giả lập deadlock thật; integration test concurrency trên database mục tiêu vẫn cần thiết để kiểm tra locking/version behavior.

## 13. Lưu ý khi áp dụng vào hệ thống thật

### Chọn idempotency key và thời hạn lưu

- Key phải đủ duy nhất trong phạm vi tenant/user và loại nghiệp vụ.
- Lưu payload hash hoặc các trường quan trọng để phát hiện key bị tái sử dụng với nội dung khác.
- Giữ record lâu hơn khoảng thời gian client, gateway hoặc broker có thể retry.
- Có chính sách archive/cleanup; xóa key quá sớm có thể cho phép request cũ tạo hiệu ứng lần nữa.
- Không log token/key nhạy cảm đầy đủ nếu không cần; có thể log hash hoặc correlation ID.

### Retry phải nằm trong ngân sách thời gian

Đặt deadline cho toàn bộ vòng lặp, không chỉ từng lần ngủ. Trước mỗi lần thử, kiểm tra thời gian còn lại; không bắt đầu transaction mới nếu request đã hết deadline. Cấu hình JDBC/query/transaction timeout phù hợp để một attempt không treo vô hạn.

### Retry không thay thế locking hoặc constraint

Retry chỉ phản ứng sau khi phát hiện conflict. Invariant vẫn cần được bảo vệ bằng `@Version`, pessimistic lock, conditional UPDATE, CHECK/UNIQUE constraint hoặc transaction isolation phù hợp. Nếu không có cơ chế bảo vệ, retry có thể chỉ lặp lại một race condition.

### Không retry một phần nghiệp vụ

Nếu một use case gồm debit, credit và ghi ledger, phải retry toàn bộ transaction như một đơn vị. Không retry riêng credit sau khi debit đã commit. Nếu nghiệp vụ trải qua nhiều service/database, dùng saga, outbox và idempotent consumer theo thiết kế phân tán.

## 14. Kiểm thử retry và idempotency

Test cần xác nhận cả số lần gọi, transaction boundary và trạng thái dữ liệu:

1. **Transient failure rồi thành công:** lỗi transient ở các lần đầu, lần sau thành công; số lần gọi không vượt policy.
2. **Hết số lần thử:** mọi attempt đều transient; exception cuối cùng được trả ra.
3. **Lỗi không retry:** validation hoặc business exception chỉ chạy một lần.
4. **Transaction mới:** mỗi attempt có transaction ID/persistence context mới; transaction cũ đã rollback trước khi attempt sau bắt đầu.
5. **Replay cùng key:** gửi lại cùng key và cùng payload; kết quả giống nhau và database chỉ có một hiệu ứng.
6. **Key cùng payload khác:** request bị từ chối và không thay đổi dữ liệu.
7. **Hai request cùng key đồng thời:** chỉ một operation record được commit; request còn lại đọc lại kết quả.
8. **Commit outcome không rõ:** mô phỏng response lỗi sau commit và xác nhận retry không nhân đôi hiệu ứng.
9. **Business failure:** hết hàng hoặc số dư không đủ không bị retry theo policy transient.
10. **Outbox:** transaction rollback không để lại event; transaction commit tạo đúng một outbox record; consumer chịu được giao lại event.

Đừng chỉ kiểm tra mock invocation. Dùng integration test với database để xác nhận unique constraint, `@Version`, rollback và trạng thái cuối.

## 15. Kiểm thử trên database production-like

H2 hữu ích cho ví dụ và unit/integration test nhanh, nhưng lock mode, deadlock, isolation, error code và thời điểm exception có thể khác PostgreSQL, MySQL, SQL Server hoặc Oracle.

Với nghiệp vụ tiền, tồn kho hoặc đặt chỗ, bổ sung Testcontainers hoặc môi trường integration dùng cùng database engine và major version với production. Kiểm tra:

- Exception class thực tế khi optimistic conflict, deadlock và lock timeout.
- Transaction rollback có hoàn tác cả idempotency record và dữ liệu nghiệp vụ.
- Unique constraint phân xử hai request cùng key.
- Lock timeout và query timeout không vượt retry deadline.
- Retry có backoff/jitter và không làm cạn connection pool.
- Outbox event chỉ được ghi khi nghiệp vụ commit.

## 16. Lỗi thường gặp

1. **Retry không giới hạn:** gây tải tăng liên tục và request treo. Đặt max attempts và deadline.
2. **Retry mọi exception:** lặp validation, business hoặc schema error. Chỉ retry exception transient đã xác nhận.
3. **Retry bên trong transaction lỗi:** transaction có thể rollback-only. Đưa vòng retry ra ngoài và gọi transactional worker riêng.
4. **Self-invocation làm mất proxy:** tách facade và worker thành bean riêng hoặc dùng transaction API tường minh.
5. **Dùng lại EntityManager sau rollback:** persistence context có thể không còn nhất quán. Mỗi attempt dùng transaction/persistence context mới.
6. **Không có idempotency key:** timeout sau commit có thể làm request lặp và nhân đôi hiệu ứng.
7. **Chỉ kiểm tra key trước insert:** hai transaction vẫn có thể cùng vượt qua. Dùng unique constraint ở database.
8. **Cùng key nhưng payload khác vẫn trả kết quả cũ:** lưu payload hash/trường quan trọng và từ chối key reuse conflict.
9. **Idempotency record commit riêng với nghiệp vụ:** có thể ghi nhận request nhưng không thực hiện nghiệp vụ hoặc ngược lại. Ghi trong cùng transaction.
10. **Bắt duplicate key trong transaction đã lỗi rồi query tiếp:** transaction có thể đã rollback-only. Đọc lại bằng transaction mới sau rollback.
11. **Gửi email/charge payment bên trong retry loop:** side effect có thể lặp. Dùng outbox và idempotent downstream.
12. **Không phân biệt lỗi business với lỗi transient:** hết hàng không tự hết bằng retry.
13. **Backoff không có jitter:** nhiều client retry cùng lúc và tiếp tục gây quá tải.
14. **Retry vượt deadline của caller:** server tiếp tục làm việc sau khi client đã timeout. Đặt ngân sách thời gian tổng.
15. **Test chỉ bằng mock:** không xác nhận locking và unique constraint thật. Bổ sung integration test trên database mục tiêu.

## 17. Nguyên tắc thực hành

- Retry chỉ lỗi transient có thể phục hồi và thao tác đã được thiết kế an toàn khi chạy lại.
- Đặt max attempts, exponential backoff, jitter và deadline tổng.
- Không retry validation, authorization, business rejection hoặc lỗi schema/query.
- Đưa retry facade ra ngoài transaction; mỗi attempt gọi transactional worker qua Spring proxy.
- Dùng `REQUIRES_NEW` hoặc transaction boundary tương đương để attempt sau có transaction và persistence context mới.
- Ghi idempotency key, payload identity và kết quả trong cùng transaction với thay đổi nghiệp vụ.
- Đặt unique constraint ở database; cùng key cùng payload trả kết quả cũ, cùng key khác payload phải bị từ chối.
- Xử lý duplicate key sau rollback bằng một transaction đọc mới.
- Dùng transactional outbox cho side effect bên ngoài và idempotent consumer để xử lý giao nhận lặp.
- Kiểm thử exception thật, rollback, replay, concurrent duplicate và database giống production.

Điểm cốt lõi: **Retry chỉ an toàn khi có giới hạn, chỉ nhắm vào lỗi tạm thời, và mỗi lần thử chạy trong transaction mới. Idempotency key cùng unique constraint và operation record được commit nguyên tử với thay đổi nghiệp vụ giúp request gửi lại hoặc commit outcome không rõ không tạo hiệu ứng trùng. Side effect bên ngoài cần outbox và xử lý lặp an toàn ở phía nhận.**