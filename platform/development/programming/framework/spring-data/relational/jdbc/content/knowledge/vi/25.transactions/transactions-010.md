# Quản lý giao dịch lập trình bằng TransactionTemplate

Spring Data JDBC thường phối hợp với transaction khai báo bằng `@Transactional` ở service hoặc repository. Tuy nhiên, có những use case cần điều khiển rõ ràng điểm bắt đầu, kết thúc, commit và rollback của transaction ngay trong code. Spring cung cấp **`TransactionTemplate`** để thực hiện việc đó.

`TransactionTemplate` là API quản lý transaction theo kiểu imperative. Nó nhận một `PlatformTransactionManager`, mở hoặc tham gia transaction theo cấu hình, chạy callback và hoàn tất transaction khi callback kết thúc. Nếu callback ném exception thuộc loại cần rollback, template yêu cầu transaction manager rollback rồi truyền lỗi ra caller.

Trong Spring Data JDBC, các lời gọi repository thực hiện bên trong callback có thể tham gia cùng transaction nếu chúng dùng chung transaction manager và DataSource. Nhờ vậy, nhiều thao tác ghi có thể được commit hoặc rollback như một use case duy nhất.

Bài học trình bày cách cấu hình, gọi `execute`/`executeWithoutResult`, kiểm soát rollback, propagation, isolation và timeout, cùng các lưu ý về connection, exception và kiểm thử.

## 1. Khi nào cần TransactionTemplate?

Với một service thông thường, `@Transactional` thường là lựa chọn đơn giản và dễ đọc:

```java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    PurchaseOrder order = new PurchaseOrder(command.orderNumber());
    return orders.save(order).getId();
}
```

Annotation phù hợp khi transaction bao trọn một method với ranh giới rõ ràng. Nhưng có những trường hợp code cần chọn transaction boundary trong một method lớn hơn, hoặc cần thực hiện một callback trong transaction rồi tiếp tục công việc bên ngoài transaction.

Ví dụ checkout cần:

1. Giữ số lượng tồn kho.
2. Tạo đơn hàng.
3. Ghi lịch sử thay đổi.
4. Nếu một bước thất bại, rollback các thay đổi database đã thực hiện trong use case.

`TransactionTemplate` cho phép xác định chính xác khối lệnh nằm trong transaction:

```java
transactionTemplate.execute(status -> {
    inventory.reserve(command.sku(), command.quantity());
    PurchaseOrder saved = orders.save(createOrder(command));
    history.save(OrderHistory.created(saved.getId()));
    return saved.getId();
});
```

Nếu ba repository cùng dùng transaction manager/DataSource đó, các thao tác sẽ tham gia cùng transaction. Khi callback hoàn tất bình thường, template commit; khi có lỗi cần rollback, các thay đổi thuộc transaction được rollback.

### 1.1. So sánh @Transactional và TransactionTemplate

| Tiêu chí | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Cách khai báo | Annotation trên class/method | Callback trong code |
| Ranh giới transaction | Theo method invocation qua Spring proxy hoặc cơ chế tương ứng | Theo lời gọi `execute` |
| Commit/rollback | Spring AOP/transaction interceptor quản lý | Template quản lý quanh callback |
| Cấu hình propagation/isolation | Annotation hoặc transaction manager | Thuộc tính trên template |
| Chọn transaction theo nhánh code | Có thể, nhưng thường cần tách method | Có thể gọi template ở đúng nhánh |
| Đọc luồng xử lý | Ranh giới thường thể hiện ở annotation | Ranh giới hiện ngay trong code |

Không cần thay toàn bộ `@Transactional` bằng `TransactionTemplate`. Hãy dùng annotation cho service method có transaction boundary ổn định; dùng template khi điều khiển lập trình tường minh mang lại lợi ích thực tế.

## 2. Các thành phần chính

`TransactionTemplate` thuộc Spring Framework:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;
```

Các thành phần có vai trò:

| Thành phần | Vai trò |
| --- | --- |
| `PlatformTransactionManager` | Abstraction điều phối transaction cho công nghệ persistence. |
| `TransactionTemplate` | Chạy callback trong transaction và quản lý commit/rollback. |
| `TransactionCallback<T>` | Callback trả về kết quả kiểu `T`. |
| `TransactionStatus` | Cho phép xem trạng thái và yêu cầu rollback. |
| `TransactionOperations` | Interface mô tả các thao tác thực thi transaction; `TransactionTemplate` triển khai interface này. |

Trong ứng dụng Spring Data JDBC, transaction manager cần quản lý đúng DataSource mà các repository sử dụng. Spring Boot thường tự cấu hình transaction manager cho datasource đã cấu hình. Nếu ứng dụng có nhiều datasource, cần chọn đúng manager cho từng nhóm repository.

## 3. Cấu hình TransactionTemplate

Cách phổ biến là tạo bean từ `PlatformTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class TransactionConfiguration {

    @Bean
    TransactionTemplate transactionTemplate(
            PlatformTransactionManager transactionManager) {
        return new TransactionTemplate(transactionManager);
    }
}
```

Spring Boot có thể tự cung cấp transaction manager nếu ứng dụng đã cấu hình datasource và transaction support phù hợp. Việc tạo bean `TransactionTemplate` tường minh giúp application service inject và sử dụng trực tiếp.

Service:

```java
@Service
public class CheckoutService {

    private final TransactionTemplate transactionTemplate;
    private final InventoryRepository inventory;
    private final PurchaseOrderRepository orders;

    public CheckoutService(
        TransactionTemplate transactionTemplate,
        InventoryRepository inventory,
        PurchaseOrderRepository orders
    ) {
        this.transactionTemplate = transactionTemplate;
        this.inventory = inventory;
        this.orders = orders;
    }
}
```

Nếu Spring context có nhiều `PlatformTransactionManager`, hãy dùng `@Qualifier` hoặc cấu hình bean rõ ràng để bảo đảm template gắn với manager đúng.

### 3.1. Cấu hình một lần trước khi sử dụng

`TransactionTemplate` giữ các thuộc tính transaction như propagation, isolation, timeout và read-only. Có thể cấu hình chúng trước khi bean được chia sẻ cho các service.

Sau khi cấu hình xong, có thể tái sử dụng template. Không nên thay đổi các thuộc tính của một template singleton theo từng request vì nhiều luồng có thể sử dụng cùng lúc.

Nếu hai use case cần cấu hình khác nhau, tạo hai bean/template riêng hoặc tạo template riêng theo cấu hình ổn định cho từng mục đích.

## 4. execute(): thực thi callback và trả kết quả

Phương thức `execute` nhận một callback và trả về kết quả do callback cung cấp:

```java
Long orderId = transactionTemplate.execute(status -> {
    PurchaseOrder order = orders.save(
        new PurchaseOrder("PO-2026-001")
    );

    return order.getId();
});
```

Luồng xử lý:

1. Template yêu cầu transaction manager bắt đầu transaction mới hoặc tham gia transaction hiện có theo propagation.
2. Callback được chạy.
3. Các repository call bên trong callback sử dụng transaction đang hoạt động nếu cùng transaction context.
4. Callback trả về kết quả.
5. Template hoàn tất transaction theo trạng thái commit/rollback.
6. Kết quả callback được trả về caller sau khi transaction được xử lý thành công.

Generic `T` của `TransactionCallback<T>` quyết định kiểu trả về. Nếu callback trả về `Long`, `execute` trả về `Long`.

### 4.1. Ví dụ hoàn chỉnh với nhiều repository

Giả sử use case cần giữ hàng rồi tạo đơn:

```java
@Service
public class CheckoutService {

    private final TransactionTemplate tx;
    private final InventoryRepository inventory;
    private final PurchaseOrderRepository orders;
    private final OrderHistoryRepository history;

    public CheckoutService(
        TransactionTemplate tx,
        InventoryRepository inventory,
        PurchaseOrderRepository orders,
        OrderHistoryRepository history
    ) {
        this.tx = tx;
        this.inventory = inventory;
        this.orders = orders;
        this.history = history;
    }

    public Long checkout(CheckoutCommand command) {
        return tx.execute(status -> {
            int reserved = inventory.reserve(
                command.sku(),
                command.quantity()
            );

            if (reserved != 1) {
                throw new InsufficientStockException(
                    command.sku()
                );
            }

            PurchaseOrder saved = orders.save(
                PurchaseOrder.create(
                    command.orderNumber(),
                    command.sku(),
                    command.quantity()
                )
            );

            history.save(
                OrderHistory.created(saved.getId())
            );

            return saved.getId();
        });
    }
}
```

Đoạn code thể hiện một transaction boundary duy nhất. Nếu giữ hàng thành công nhưng việc lưu đơn hàng hoặc lịch sử phát sinh runtime exception, template rollback các thay đổi đã thực hiện trong transaction đó.

Ví dụ giả định ba repository cùng dùng một DataSource và transaction manager. Nếu chúng trỏ tới các datasource/transaction manager khác nhau, một `TransactionTemplate` không tự tạo transaction phân tán bao trùm tất cả.

## 5. executeWithoutResult(): callback không cần giá trị trả về

Nếu use case chỉ cần thực hiện thao tác và không trả kết quả, dùng `executeWithoutResult`:

```java
transactionTemplate.executeWithoutResult(status -> {
    inventory.reserve("BOOK-01", 2);
    orders.save(PurchaseOrder.create("PO-2026-002"));
});
```

Callback nhận `TransactionStatus` để có thể yêu cầu rollback nếu cần. API này giúp tránh việc trả về một giá trị giả chỉ để thỏa mãn `execute`.

Có thể dùng `executeWithoutResult` cho:

- Cập nhật nhiều bảng.
- Đồng bộ một nhóm aggregate trong cùng database.
- Ghi lịch sử/audit cùng với thao tác nghiệp vụ.
- Xóa dữ liệu theo nhiều bước cần atomicity.

Nếu cần trả ID, số hàng bị ảnh hưởng hoặc một kết quả nghiệp vụ, dùng `execute`.

## 6. Commit và rollback mặc định

Theo mặc định, transaction được commit khi callback hoàn tất bình thường. Nếu callback ném `RuntimeException` hoặc `Error`, template yêu cầu rollback rồi truyền exception ra caller.

Ví dụ:

```java
Long id = transactionTemplate.execute(status -> {
    PurchaseOrder saved = orders.save(
        PurchaseOrder.create("PO-2026-003")
    );

    if (!isAllowed(saved)) {
        throw new IllegalStateException(
            "Đơn hàng không hợp lệ"
        );
    }

    return saved.getId();
});
```

Nếu `isAllowed` trả false và exception được ném, thao tác lưu đơn hàng trong cùng transaction bị rollback.

### 6.1. Không nuốt exception nếu muốn rollback tự động

Đoạn sau có vấn đề:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        inventory.reserve("BOOK-01", 2);
        orders.save(PurchaseOrder.create("PO-2026-004"));
    } catch (RuntimeException ex) {
        log.error("Checkout failed", ex);
        // Callback kết thúc bình thường nên transaction có thể commit.
    }
});
```

Khi exception bị bắt và không được ném tiếp, template thấy callback kết thúc bình thường. Transaction có thể commit các thay đổi đã thực hiện trước lỗi.

Nếu muốn rollback, hãy ném lại exception:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        inventory.reserve("BOOK-01", 2);
        orders.save(PurchaseOrder.create("PO-2026-004"));
    } catch (RuntimeException ex) {
        log.error("Checkout failed", ex);
        throw ex;
    }
});
```

Hoặc đánh dấu rollback-only trước khi trả về nếu use case có chủ đích xử lý lỗi và không ném exception ra ngoài.

### 6.2. Checked exception

Callback `TransactionCallback` không khai báo ném checked exception. Nếu một thao tác trong callback phát sinh checked exception, code cần xử lý nó bên trong callback.

Một lựa chọn là bọc thành unchecked exception:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        importService.importData();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
});
```

Exception unchecked thoát khỏi callback và kích hoạt rollback theo mặc định.

Nếu ứng dụng cần trả một kết quả nghiệp vụ thay vì ném exception, có thể gọi `status.setRollbackOnly()` rồi trả kết quả lỗi. Hãy bảo đảm không tiếp tục các thao tác ghi sau khi đã quyết định rollback.

## 7. Đánh dấu rollback-only bằng TransactionStatus

Có những tình huống callback cần hoàn tất phần xử lý để trả về một kết quả có cấu trúc, nhưng transaction vẫn phải rollback.

Dùng:

```java
transactionTemplate.execute(status -> {
    int reserved = inventory.reserve("BOOK-01", 2);

    if (reserved == 0) {
        status.setRollbackOnly();
        return CheckoutResult.rejected("Không đủ tồn kho");
    }

    PurchaseOrder order = orders.save(
        PurchaseOrder.create("PO-2026-005")
    );

    return CheckoutResult.accepted(order.getId());
});
```

`setRollbackOnly` đánh dấu transaction hiện tại cần rollback khi template hoàn tất. Callback vẫn có thể trả về `CheckoutResult`.

Kết quả nghiệp vụ bị từ chối vẫn được trả cho caller, nhưng các thay đổi database trong transaction không được commit.

### 7.1. isRollbackOnly()

`TransactionStatus` có thể được kiểm tra:

```java
if (status.isRollbackOnly()) {
    // Transaction đã được đánh dấu rollback-only.
}
```

Thông thường không cần kiểm tra liên tục. Dùng trạng thái này khi logic callback có nhiều nhánh và cần hiểu transaction đã bị đánh dấu rollback hay chưa.

### 7.2. Rollback-only không giống rollback ngay tại dòng code

`setRollbackOnly` đánh dấu quyết định rollback. Việc rollback thực tế xảy ra khi template hoàn tất callback và xử lý transaction. Không nên tiếp tục tạo thêm side effect bên ngoài database với giả định các thao tác đó cũng được rollback.

Ví dụ, gửi email hoặc gọi API ngoài không được database transaction tự hoàn tác. Hãy thực hiện side effect sau commit hoặc dùng outbox/event pattern phù hợp.

## 8. Cấu hình propagation

Propagation quyết định cách một lời gọi transaction tham gia vào transaction đang tồn tại.

`TransactionTemplate` mặc định dùng `PROPAGATION_REQUIRED`.

| Propagation | Hành vi |
| --- | --- |
| `REQUIRED` | Tham gia transaction hiện có; nếu chưa có thì tạo transaction mới. |
| `REQUIRES_NEW` | Tạm treo transaction hiện có và tạo transaction độc lập mới. |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không transaction. |
| `MANDATORY` | Yêu cầu transaction đã tồn tại; nếu không có thì lỗi. |
| `NOT_SUPPORTED` | Tạm treo transaction hiện có và chạy không transaction. |
| `NEVER` | Yêu cầu không có transaction; nếu đang có thì lỗi. |
| `NESTED` | Chạy transaction lồng nhau nếu transaction manager hỗ trợ, thường dựa trên savepoint. |

### 8.1. REQUIRED: lựa chọn mặc định

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);
// Default propagation: PROPAGATION_REQUIRED
```

Nếu service đang chạy trong transaction do `@Transactional` tạo, callback thường tham gia transaction đó. Nếu chưa có, template tạo transaction mới.

Điều này giúp các repository call trong callback phối hợp với transaction bên ngoài.

### 8.2. REQUIRES_NEW: transaction độc lập

Có thể tạo template riêng:

```java
@Bean
TransactionTemplate independentTransactionTemplate(
        PlatformTransactionManager transactionManager) {
    TransactionTemplate template =
        new TransactionTemplate(transactionManager);

    template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW
    );

    return template;
}
```

Khi được gọi trong một transaction đang hoạt động, transaction bên ngoài bị suspend, template mở transaction mới, hoàn tất nó rồi mới tiếp tục transaction bên ngoài.

Ví dụ có thể dùng cho một ghi nhận độc lập mà nghiệp vụ muốn giữ lại ngay cả khi transaction ngoài rollback. Tuy nhiên, cần cân nhắc kỹ vì dữ liệu được ghi trong transaction REQUIRES_NEW có thể tồn tại dù thao tác nghiệp vụ chính thất bại.

Ngoài ra, transaction ngoài có thể đang giữ connection trong khi transaction mới cần một connection khác. Với connection pool nhỏ và nhiều request lồng nhau, điều này có thể gây cạn pool hoặc chờ đợi.

### 8.3. NESTED và savepoint

`PROPAGATION_NESTED` có thể dùng savepoint trong một transaction vật lý nếu transaction manager hỗ trợ. Nó không tương đương với một transaction độc lập như `REQUIRES_NEW`.

Khả năng nested transaction phụ thuộc transaction manager và cấu hình database. Không giả định mọi DataSource transaction manager đều hỗ trợ nested behavior theo cùng cách.

## 9. Isolation level, timeout và read-only

Ngoài propagation, template có thể cấu hình isolation, timeout và read-only.

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

tx.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
tx.setTimeout(30);
tx.setReadOnly(false);
```

### 9.1. Isolation level

Các mức isolation JDBC/Spring thường gặp:

| Isolation | Ý nghĩa khái quát |
| --- | --- |
| `ISOLATION_DEFAULT` | Dùng mặc định của database/transaction manager. |
| `ISOLATION_READ_UNCOMMITTED` | Có thể cho phép dirty read nếu database hỗ trợ. |
| `ISOLATION_READ_COMMITTED` | Chỉ đọc dữ liệu đã commit theo semantics database. |
| `ISOLATION_REPEATABLE_READ` | Bảo vệ tính nhất quán của các lần đọc cùng hàng theo semantics database. |
| `ISOLATION_SERIALIZABLE` | Mức nghiêm ngặt nhất; database có thể phải khóa hoặc abort transaction để duy trì serializability. |

Không nên chọn isolation cao nhất theo thói quen. Nó có thể tăng lock contention, giảm throughput hoặc làm transaction bị abort khi xung đột. Hãy bắt đầu với mặc định database, sau đó chọn mức isolation dựa trên invariant và workload thực tế.

### 9.2. Isolation chỉ có ý nghĩa khi transaction mới được tạo

Nếu template tham gia transaction đang tồn tại theo `REQUIRED`, isolation của transaction bên ngoài thường được giữ. Cấu hình isolation trên template không tự nâng cấp một transaction đã mở.

Muốn kiểm soát hành vi khi tham gia transaction có isolation khác, transaction manager có thể được cấu hình để validate existing transaction. Hãy tránh kỳ vọng một template có thể thay đổi isolation giữa chừng của transaction hiện tại.

### 9.3. Timeout

`setTimeout(30)` đặt thời gian timeout theo giây cho transaction mới nếu transaction manager/database hỗ trợ. Timeout không phải lúc nào cũng ngắt ngay một câu SQL đang chạy; query timeout và transaction timeout là các cơ chế liên quan nhưng khác nhau.

Với query dài, có thể cần cấu hình query timeout riêng ở JDBC/template/repository hoặc database statement.

### 9.4. Read-only

`setReadOnly(true)` biểu thị transaction chỉ đọc:

```java
TransactionTemplate readOnlyTx =
    new TransactionTemplate(transactionManager);

readOnlyTx.setReadOnly(true);
```

Nó có thể cho phép transaction manager/driver/database áp dụng tối ưu phù hợp. Đây không phải cơ chế phân quyền tuyệt đối; khả năng từ chối lệnh ghi phụ thuộc database và transaction manager.

Dùng template read-only riêng cho các use case đọc dài hoặc đọc nhiều repository khi cần transaction chung. Không đổi thuộc tính `readOnly` trên template singleton dùng chung theo từng request.

## 10. TransactionTemplate với Spring Data JDBC repositories

Spring Data JDBC repository sử dụng transaction abstraction của Spring. Khi repository được gọi bên trong `TransactionTemplate.execute` và cùng tham gia một transaction manager/DataSource, các câu SQL dùng chung transaction đó.

Ví dụ:

```java
transactionTemplate.executeWithoutResult(status -> {
    Customer customer = customers.save(
        new Customer(null, "Mai", "mai@example.test")
    );

    orders.save(
        PurchaseOrder.forCustomer(customer.id())
    );

    audit.save(
        AuditEntry.customerCreated(customer.id())
    );
});
```

Nếu bất kỳ thao tác nào ném unchecked exception và exception thoát khỏi callback, transaction rollback cả ba thay đổi.

Điều kiện quan trọng:

- Các repository phải dùng cùng DataSource hoặc một transaction setup có thể phối hợp.
- Template phải gắn với transaction manager quản lý đúng datasource.
- Repository calls phải diễn ra trên cùng luồng thực thi đồng bộ trong transaction context.
- Không chuyển phần công việc database sang thread mới rồi giả định transaction được truyền tự động.

### 10.1. Query method và @Modifying

Các method ghi SQL tùy chỉnh như `@Modifying` cũng có thể tham gia transaction do template mở:

```java
transactionTemplate.executeWithoutResult(status -> {
    int updated = inventory.reserve("BOOK-01", 2);

    if (updated != 1) {
        throw new InsufficientStockException("BOOK-01");
    }

    orders.save(PurchaseOrder.create("PO-2026-006"));
});
```

Direct modifying query không tự chạy entity callbacks hoặc auditing như đường save aggregate. TransactionTemplate chỉ quản lý transaction; nó không biến câu SQL trực tiếp thành aggregate persistence.

### 10.2. Repository CRUD có transaction mặc định

Các phương thức CRUD kế thừa của repository Spring Data có cấu hình transaction mặc định. Query method được khai báo riêng có thể cần transaction boundary rõ ràng ở service hoặc template.

Khi đã có transaction bên ngoài từ template, các repository call tham gia transaction đó theo propagation và cấu hình tương ứng.

## 11. Kết hợp TransactionTemplate và @Transactional

Hai cơ chế có thể dùng cùng nhau. Ví dụ service method có transaction khai báo và callback dùng template mặc định REQUIRED:

```java
@Transactional
public void updateOrder(Long orderId) {
    transactionTemplate.executeWithoutResult(status -> {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

        order.markConfirmed();
        orders.save(order);
    });

    notifications.recordConfirmation(orderId);
}
```

Vì `REQUIRED` tham gia transaction đang có, callback chạy trong transaction bên ngoài. Khi service method kết thúc, transaction bên ngoài mới commit.

Tuy nhiên, dùng cả hai cho cùng một ranh giới có thể khiến code khó hiểu nếu không có lý do rõ. Chọn một nơi làm owner của transaction boundary chính để người đọc biết thao tác nào commit/rollback cùng nhau.

Nếu template dùng `REQUIRES_NEW`, nó tạo transaction độc lập trong khi transaction ngoài bị suspend. Điều này có thể là chủ đích nhưng cần giải thích bằng semantics nghiệp vụ.

## 12. Không để transaction vượt qua thread boundary

Transaction JDBC imperative của Spring thường gắn với thread hiện tại thông qua transaction synchronization và connection binding.

Vì vậy, đoạn code:

```java
transactionTemplate.executeWithoutResult(status -> {
    executor.submit(() -> orders.save(order));
});
```

không làm cho thao tác trong thread của executor tự động tham gia transaction của callback. Thread mới có transaction context riêng hoặc không có transaction, tùy cách gọi.

Nếu cần xử lý bất đồng bộ:

1. Commit transaction hiện tại.
2. Gửi công việc qua cơ chế queue/event/outbox phù hợp.
3. Worker mở transaction riêng cho công việc của nó.

Không giữ connection/transaction mở rồi chờ một future hoặc tác vụ async hoàn thành nếu tác vụ đó cần chính connection pool đang bị giữ.

Với reactive stack như R2DBC, transaction context được quản lý theo reactive context và cần API phù hợp như `TransactionalOperator`; `TransactionTemplate` là API imperative, không dùng thay thế cho reactive transaction management.

## 13. Xử lý lỗi và kết quả sau transaction

`execute` chỉ trả kết quả callback sau khi transaction hoàn tất thành công. Nếu commit/rollback gặp lỗi, exception tương ứng được truyền ra caller.

Ví dụ:

```java
CheckoutResult result;

try {
    result = transactionTemplate.execute(status -> {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("PO-2026-007")
        );
        return CheckoutResult.accepted(saved.getId());
    });
} catch (DataAccessException ex) {
    // Xử lý lỗi persistence sau khi template rollback theo quy tắc.
    throw new CheckoutFailedException(ex);
}
```

Nên bắt lỗi ở nơi có đủ ngữ cảnh để chuyển thành lỗi nghiệp vụ hoặc API response. Không bắt và bỏ qua lỗi bên trong callback nếu cần rollback.

### 13.1. Side effect ngoài database

Email, gọi HTTP, gửi message trực tiếp hoặc ghi file không nằm trong transaction JDBC. Database rollback không thể thu hồi các side effect đó.

Nếu cần phát sự kiện chỉ khi transaction commit, cân nhắc:

- Transactional event listener với phase phù hợp.
- Outbox pattern ghi event cùng transaction database, sau đó worker phát event.
- Một cơ chế retry/idempotency cho hệ thống bên ngoài.

Không gửi email thành công trước khi database commit rồi kỳ vọng rollback sẽ thu hồi email.

## 14. Kiểm thử commit và rollback

Một integration test cần xác nhận thay đổi đã thực sự được rollback sau khi callback thất bại.

Ví dụ service:

```java
public void createThenFail() {
    transactionTemplate.executeWithoutResult(status -> {
        orders.save(PurchaseOrder.create("PO-ROLLBACK"));
        throw new IllegalStateException("Simulated failure");
    });
}
```

Test:

```java
@SpringBootTest
class TransactionTemplateIntegrationTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void rollsBackRepositoryChangesWhenCallbackFails() {
        assertThatThrownBy(() -> checkout.createThenFail())
            .isInstanceOf(IllegalStateException.class);

        assertThat(orders.findByOrderNumber("PO-ROLLBACK"))
            .isEmpty();
    }
}
```

Test này cần chạy với database và transaction manager thực tế của ứng dụng. Không đánh dấu test method `@Transactional` nếu muốn quan sát kết quả sau khi transaction của service đã kết thúc; test transaction bao ngoài có thể làm thay đổi cách đọc/commit/rollback được quan sát.

### 14.1. Kiểm thử rollback-only

Nếu callback đánh dấu rollback-only nhưng trả kết quả bình thường:

```java
CheckoutResult result = transactionTemplate.execute(status -> {
    orders.save(PurchaseOrder.create("PO-ROLLBACK-ONLY"));
    status.setRollbackOnly();
    return CheckoutResult.rejected("Cancelled");
});
```

Test cần xác nhận:

- Caller nhận `CheckoutResult.rejected`.
- Hàng `PO-ROLLBACK-ONLY` không tồn tại sau transaction.
- Không có side effect ngoài database nào được giả định là rollback.

### 14.2. Kiểm thử nhiều repository cùng transaction

Tạo dữ liệu ở hai repository rồi ném exception sau thao tác thứ hai. Sau khi transaction kết thúc, xác nhận cả hai thay đổi đều không còn.

Điều này chứng minh hai repository thực sự tham gia cùng transaction manager/DataSource. Nếu chỉ một phần dữ liệu rollback, hãy kiểm tra datasource, transaction manager và propagation của từng thành phần.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dữ liệu vẫn commit sau khi bắt exception | Exception bị nuốt trong callback và callback kết thúc bình thường. | Ném lại exception hoặc gọi `setRollbackOnly`. |
| Một repository rollback, repository khác không rollback | Hai repository dùng datasource/transaction manager khác nhau. | Dùng transaction manager phù hợp hoặc thiết kế phối hợp rõ ràng. |
| Template không tham gia transaction ngoài | Cấu hình propagation không như mong đợi hoặc dùng manager khác. | Kiểm tra `REQUIRED`, manager và transaction boundary. |
| Transaction ngoài rollback nhưng dữ liệu REQUIRES_NEW vẫn còn | Transaction mới đã commit độc lập. | Xác nhận đây là semantics nghiệp vụ mong muốn. |
| Connection pool bị cạn | Transaction/Stream giữ connection lâu hoặc REQUIRES_NEW cần connection thứ hai. | Rút ngắn transaction và đánh giá pool/concurrency. |
| Update chạy trong read-only transaction | Template hoặc transaction ngoài được cấu hình read-only. | Dùng transaction ghi phù hợp. |
| Checked exception không kích hoạt rollback | Callback không ném được checked exception trực tiếp hoặc lỗi bị xử lý như bình thường. | Bọc thành unchecked exception hoặc đánh dấu rollback-only. |
| Code async không rollback cùng callback | Transaction context không tự truyền sang thread khác. | Mở transaction riêng trong worker hoặc dùng outbox. |
| Email đã gửi dù database rollback | Side effect ngoài database không thuộc transaction JDBC. | Phát sự kiện sau commit hoặc dùng outbox. |
| Thay đổi isolation nhưng không có tác dụng | Callback tham gia transaction đã tồn tại. | Cấu hình isolation trên transaction mới và hiểu propagation. |

## 16. Quy trình sử dụng TransactionTemplate

Khi cần transaction lập trình trong Spring Data JDBC:

1. Xác định use case cần những thao tác database nào cùng commit/rollback.
2. Chọn đúng `PlatformTransactionManager` quản lý datasource của repository.
3. Tạo và cấu hình `TransactionTemplate` một lần.
4. Dùng `execute` khi cần trả kết quả hoặc `executeWithoutResult` khi không cần.
5. Đặt các repository call thuộc cùng atomic unit bên trong callback.
6. Để exception cần rollback thoát khỏi callback hoặc đánh dấu `setRollbackOnly`.
7. Chọn propagation, isolation, timeout và read-only theo yêu cầu thực tế.
8. Không thay đổi cấu hình template dùng chung theo từng request.
9. Không chuyển database work sang thread khác và giả định transaction được kế thừa.
10. Đưa side effect ngoài database ra sau commit hoặc dùng outbox/event pattern.
11. Kiểm thử commit, rollback và việc nhiều repository dùng chung transaction.
12. Giữ transaction ngắn để giảm thời gian giữ connection và lock.

> **TransactionTemplate mở hoặc tham gia transaction, chạy callback rồi commit/rollback theo kết quả.** Trong Spring Data JDBC, nó là cách tường minh để gom nhiều repository operation vào cùng transaction khi chúng dùng chung transaction manager và DataSource. Hãy để lỗi cần rollback thoát khỏi callback hoặc đánh dấu rollback-only, cấu hình propagation có chủ đích và giữ công việc database trong cùng thread-bound transaction.

### Tài liệu tham khảo

- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): sử dụng `TransactionTemplate` và transaction callback.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): abstraction transaction, PlatformTransactionManager và declarative transactions.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): các propagation behavior và transaction boundary.
- [Spring Framework — Transaction Isolation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-isolation.html): isolation level và hành vi transaction.
- [Spring Data JDBC — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction support trong Spring Data JDBC.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình datasource và transaction manager trong Spring Boot.
