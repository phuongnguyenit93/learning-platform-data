# Tạo TransactionTemplate từ PlatformTransactionManager trong Spring Framework

> **Spring Framework — Transaction Management → TransactionTemplate.** Bài học trình bày đầy đủ cách tạo và cấu hình `org.springframework.transaction.support.TransactionTemplate` từ một `org.springframework.transaction.PlatformTransactionManager`, cách chạy khối nghiệp vụ qua callback, đọc `TransactionStatus`, điều khiển commit/rollback, quản lý nhiều cấu hình và chọn đúng transaction manager. Trọng tâm là **lifecycle và wiring thực tế**: một template không tự kết nối database; nó điều phối transaction thông qua manager mà ta cung cấp.

## 1. Mục tiêu sau bài học

Sau khi học, bạn có thể:

1. Nói rõ quan hệ giữa `DataSource`, `PlatformTransactionManager`, `TransactionTemplate`, `JdbcTemplate` và `TransactionStatus`.
2. Tạo `TransactionTemplate` bằng constructor nhận một `PlatformTransactionManager`; biết hai cách thay thế: constructor nhận thêm `TransactionDefinition` và no-arg constructor cộng `setTransactionManager(...)`.
3. Đặt transaction definition gồm propagation, isolation, timeout, read-only và transaction name, đồng thời hiểu giới hạn khi scope đã tham gia một transaction bên ngoài.
4. Đưa template vào Spring bean qua constructor injection hoặc định nghĩa template như một `@Bean` dùng lại.
5. Sử dụng `execute(TransactionCallback<T>)` để trả về giá trị, `executeWithoutResult(Consumer<TransactionStatus>)` cho thao tác không trả về và `status.setRollbackOnly()` khi nghiệp vụ chủ động yêu cầu rollback.
6. Hiểu exception handling: runtime exception/error thoát callback dẫn đến rollback, checked exception cần tự xử lý trong callback theo Java type rules.
7. Phân biệt việc dùng template ở code imperative với `@Transactional` dựa trên AOP proxy và với `TransactionalOperator` cho reactive flows.
8. Xác minh hành vi qua ví dụ **Java 17+, Maven, Spring JDBC và H2** chạy được: commit, rollback bởi exception, rollback-only với return bình thường, và `REQUIRES_NEW` commit độc lập.

## 2. Một câu nhớ cốt lõi

`TransactionTemplate` là **bộ điều phối một phạm vi transaction bằng callback**, còn `PlatformTransactionManager` là **bộ phận thật sự điều khiển begin, commit, rollback và resource binding**.

Mô hình:

```text
               Ứng dụng / Spring Bean
                        |
                        v
         TransactionTemplate.execute(callback)
                        |
                đã được cấu hình với
                        |
                        v
             PlatformTransactionManager
               /       |          \
              /        |           \
   getTransaction   commit      rollback
              \        |           /
               \       |          /
                physical transaction
                        |
                JDBC Connection / JPA
                        |
                Spring-aware data access
                  ví dụ JdbcTemplate
```

Lệnh:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
```

**Chưa bắt đầu một transaction**. Nó chỉ tạo đối tượng template gắn với manager. Transaction được yêu cầu khi gọi:

```java
Integer result = template.execute(status -> {
    // Code cần nằm trong transaction.
    return 42;
});
```

Khi callback kết thúc hoặc ném exception, template yêu cầu manager hoàn tất transaction phù hợp. Với propagation `REQUIRED` mặc định, nếu có transaction bên ngoài, callback **tham gia** physical transaction đó thay vì tự tạo/commit một physical transaction độc lập.

## 3. Các lớp và vai trò

| Thành phần | Vai trò chính | Điều không làm |
| --- | --- | --- |
| `PlatformTransactionManager` | API imperative với `getTransaction(definition)`, `commit(status)`, `rollback(status)`; implementation thực thi trên resource tương ứng | Không tự “đoán” datasource của mọi JDBC operation trong ứng dụng |
| `JdbcTransactionManager` | Một implementation Spring JDBC điều khiển transaction trên `DataSource`; thường dùng cho Spring JDBC | Không biến nhiều datasources khác nhau thành distributed atomic transaction |
| `JpaTransactionManager` | Điều phối transaction qua JPA `EntityManagerFactory` và resource liên quan | Không tự điều khiển độc lập mọi database ngoài phạm vi JPA resources được cấu hình |
| `TransactionTemplate` | Nhận manager, giữ transaction definition, tạo callback boundary và xử lý lifecycle/exception | Không thay database manager và không yêu cầu AOP proxy để chính `execute` chạy |
| `TransactionDefinition` | Hợp đồng về propagation, isolation, timeout, read-only và name | Không chứa dữ liệu giao dịch hoặc quyết định kết quả của SQL |
| `TransactionStatus` | Trạng thái của scope đang được xử lý; hỗ trợ `setRollbackOnly()`, `isRollbackOnly()`, `isNewTransaction()` | Không đại diện một transaction toàn cục duy nhất cho mọi thread |
| `JdbcTemplate` | Thực thi SQL thông qua Spring JDBC/resource synchronization | Không tự mở/commit transaction riêng cho toàn bộ một nhóm SQL khi thiếu boundary |
| `TransactionOperations` | Interface của `execute(...)`, `executeWithoutResult(...)`, hữu ích làm contract/injection seam | Không phơi bày đầy đủ các setters cấu hình của `TransactionTemplate` |

**Tên package quan trọng:**

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.support.DefaultTransactionDefinition;
```

Đoạn trên là nhóm imports, chưa phải chương trình độc lập.

### 3.1. Vì sao không chỉ cần JdbcTemplate?

Một `JdbcTemplate` riêng lẻ có thể chạy SQL với autocommit khi không có transaction hiện hành. Nếu nghiệp vụ cần **hai câu lệnh thành công hoặc cùng thất bại**, phải có một transaction boundary:

```java
return transactionTemplate.execute(status -> {
    jdbc.update("UPDATE ...");  // phần 1
    jdbc.update("INSERT ...");  // phần 2
    return "done";
});
```

Đây là fragment; SQL cần thay bằng bảng thật. Nếu manager điều phối đúng `DataSource` mà `JdbcTemplate` sử dụng, hai calls cùng tham gia transaction được ràng buộc bởi Spring. Nếu manager và JdbcTemplate dùng **hai datasources không liên quan**, không được suy ra hai câu SQL cùng rollback chỉ vì chúng nằm trong lambda.

## 4. Ba cách khởi tạo TransactionTemplate

### 4.1. Cách khuyến nghị phổ biến: constructor nhận manager

```java
PlatformTransactionManager manager = /* Spring-injected manager */;
TransactionTemplate template = new TransactionTemplate(manager);
```

Hai dòng là fragment minh họa dependency injection, không phải khai báo Java có thể biên dịch nguyên văn vì comment chỗ gán manager. Trong Spring bean thực tế:

```java
@Service
public class PaymentService {
    private final TransactionTemplate tx;

    public PaymentService(PlatformTransactionManager manager) {
        this.tx = new TransactionTemplate(manager);
    }

    public void markPaid() {
        tx.executeWithoutResult(status -> {
            // SQL / repository operations...
        });
    }
}
```

Đây là fragment class: cần imports, logic truy cập dữ liệu và bean manager tương ứng. Constructor injection bảo đảm service nhận manager đã cấu hình qua Spring container. Không cần `@Transactional` trên `markPaid()` vì chính lệnh `tx.executeWithoutResult(...)` đã mở một programmatic boundary.

### 4.2. Constructor nhận manager và TransactionDefinition

Khi cần tái sử dụng một bộ cấu hình cụ thể:

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
def.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(15); // seconds
def.setName("independent-audit");

TransactionTemplate auditTx =
        new TransactionTemplate(manager, def);
```

Fragment này giả định `manager` đã được cung cấp. Constructor copy các settings ban đầu từ `TransactionDefinition`; template vẫn có thể được cấu hình bổ sung trước khi sử dụng.

**Đừng nhầm:** `REQUIRES_NEW` có thể **suspend** outer transaction và tạo một physical transaction độc lập; nó không phải phương án “an toàn hơn” một cách mặc định. Nếu audit phải commit cùng order, `REQUIRED` mới là semantics thích hợp.

### 4.3. No-argument constructor + setter

```java
TransactionTemplate tx = new TransactionTemplate();
tx.setTransactionManager(manager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
```

Cách này hợp lệ, đặc biệt khi container cấu hình properties sau khi xây bean. Nhưng một template không có manager **không sẵn sàng** để chạy `execute`. Khi được Spring quản lý như bean, `afterPropertiesSet()` thực hiện validation cần manager.

Với code Java viết trực tiếp, dùng constructor nhận manager thường dễ đọc hơn, giảm nguy cơ quên setter. **Không chọn no-arg constructor chỉ để tránh dependency injection.**

### 4.4. Một ngữ nghĩa, nhiều cách wiring

Ba cách trên đều tạo ra **imperative TransactionTemplate**. Chúng không quyết định SQL/transaction resource nằm ở đâu; điều đó phụ thuộc manager. Một template có thể là field private của service hoặc một bean chia sẻ giữa nhiều services. Khi có nhiều transaction definitions, nên đặt tên bean rõ ràng để tránh chọn nhầm.

## 5. Dùng Spring Bean để chia sẻ TransactionTemplate

Thay vì mỗi service tự tạo template, có thể định nghĩa bean:

```java
@Configuration(proxyBeanMethods = false)
public class TransactionConfig {

    @Bean
    public TransactionTemplate transactionTemplate(
            PlatformTransactionManager transactionManager) {

        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(30);

        return template;
    }
}
```

Đây là fragment Spring configuration: cần imports và đã có bean `PlatformTransactionManager` đúng resource. Spring tự truyền manager vào factory method. Sau đó service:

```java
@Service
public class OrderService {
    private final TransactionTemplate tx;

    public OrderService(TransactionTemplate tx) {
        this.tx = tx;
    }

    public void submit() {
        tx.executeWithoutResult(status -> {
            // Ghi order và stock cùng transaction.
        });
    }
}
```

Fragment. **Không cần tạo một `PlatformTransactionManager` mới cho mỗi service**. Manager thường là singleton bean cấu hình cùng datasource/entity manager factory. Template cũng có thể dùng lại.

### 5.1. Nhiều TransactionTemplate beans

Khi service cần hai semantics:

```java
@Bean("orderTx")
TransactionTemplate orderTx(PlatformTransactionManager manager) {
    TransactionTemplate t = new TransactionTemplate(manager);
    t.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
    return t;
}

@Bean("auditTx")
TransactionTemplate auditTx(PlatformTransactionManager manager) {
    TransactionTemplate t = new TransactionTemplate(manager);
    t.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    return t;
}
```

Fragment cần đặt trong `@Configuration`. Khi inject:

```java
public OrderService(
        @Qualifier("orderTx") TransactionTemplate orderTx,
        @Qualifier("auditTx") TransactionTemplate auditTx) {
    this.orderTx = orderTx;
    this.auditTx = auditTx;
}
```

Nếu có nhiều beans cùng type `TransactionTemplate` mà không có `@Qualifier`, `@Primary` hoặc quy tắc resolve phù hợp, container có thể báo ambiguity. Đừng chọn ngẫu nhiên template nào có thể inject được; **propagation khác nhau dẫn tới kết quả dữ liệu khác nhau**.

### 5.2. Template dùng chung có an toàn khi nhiều thread gọi execute?

Theo tài liệu Spring, các instances `TransactionTemplate` **thread-safe để dùng chung** vì không giữ conversational transaction state của từng lời gọi. Transaction state thực tế do manager và resource synchronization quản lý cho execution context.

Nhưng template **có configuration state có thể thay đổi** qua setters. Vì vậy:

- Cấu hình các fields một lần lúc khởi tạo bean.
- Không gọi `template.setPropagationBehavior(...)` hoặc `template.setIsolationLevel(...)` theo từng HTTP request trên một singleton template đang dùng chung.
- Nếu có hai transaction settings, tạo **hai template objects** cấu hình khác nhau; đặt tên bean dễ hiểu.
- Không lưu `TransactionStatus` từ callback để dùng ở thread khác hoặc sau khi callback kết thúc.

Ví dụ **không nên**:

```java
public void run(boolean independent) {
    // Nguy hiểm nếu tx là singleton dùng bởi nhiều requests:
    tx.setPropagationBehavior(
            independent
                ? TransactionDefinition.PROPAGATION_REQUIRES_NEW
                : TransactionDefinition.PROPAGATION_REQUIRED);

    tx.executeWithoutResult(status -> {
        // Request khác có thể thay đổi config của tx cùng lúc.
    });
}
```

Đây là fragment anti-pattern. Dùng hai immutable-after-setup template references `requiredTx` và `independentTx` sẽ rõ ràng, dễ kiểm thử hơn.

## 6. Các defaults mà constructor một tham số kế thừa

`TransactionTemplate` mở rộng `DefaultTransactionDefinition`. Mặc định phổ biến khi không cấu hình thêm:

| Setting | Default | Ý nghĩa |
| --- | --- | --- |
| `propagationBehavior` | `PROPAGATION_REQUIRED` | Nếu đã có transaction thì tham gia, nếu chưa thì tạo transaction mới |
| `isolationLevel` | `ISOLATION_DEFAULT` | Dùng isolation mặc định của DB/resource |
| `timeout` | `TIMEOUT_DEFAULT` | Dùng timeout mặc định của transaction manager/resource |
| `readOnly` | `false` | Không tuyên bố read-only ở transaction definition |
| `name` | `null` | Không đặt tên riêng cho transaction definition |

Cách in kiểm tra programmatically:

```java
System.out.println(
        template.getPropagationBehavior()
                == TransactionDefinition.PROPAGATION_REQUIRED);
System.out.println(
        template.getIsolationLevel()
                == TransactionDefinition.ISOLATION_DEFAULT);
System.out.println(
        template.getTimeout()
                == TransactionDefinition.TIMEOUT_DEFAULT);
System.out.println(!template.isReadOnly());
```

Nếu template mới tạo từ constructor một tham số và chưa cấu hình, các dòng này thường đều `true`. Đây là fragment cần biến `template` hợp lệ và imports.

**Isolation.DEFAULT không có nghĩa READ_COMMITTED trong mọi database.** `TIMEOUT_DEFAULT` không có nghĩa transaction tồn tại vô hạn và cũng không tự thay thế database/HTTP/query timeouts. `readOnly=true` thông thường là hint/optimization, không phải rào chắn ghi tuyệt đối trên mọi manager.

## 7. Tùy chỉnh propagation, isolation, timeout, read-only và name

Các setters trên template là API của `DefaultTransactionDefinition`:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
tx.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(20);      // 20 giây, tùy manager/resource
tx.setReadOnly(false);
tx.setName("orders.create");
```

Đây là fragment, giả định manager đã có. Một số cấu hình có các biến thể setter theo tên:

```java
tx.setPropagationBehaviorName("PROPAGATION_REQUIRES_NEW");
tx.setIsolationLevelName("ISOLATION_SERIALIZABLE");
```

Các string constants phải tương ứng đúng tên mà `DefaultTransactionDefinition` chấp nhận; không dùng enum name như `"REQUIRES_NEW"` tùy tiện khi method yêu cầu tên constant.

### 7.1. Khi tham gia existing transaction, inner config không tự nâng isolation

Giả sử outer `@Transactional(isolation=READ_COMMITTED)` đã mở physical T1. Bên trong gọi `TransactionTemplate` với `PROPAGATION_REQUIRED` và `ISOLATION_SERIALIZABLE`.

Template vẫn yêu cầu manager tham gia T1; manager thông thường không tạo một physical isolation level thứ hai trong cùng T1. Với các manager có default lenient handling, isolation riêng của inner **không tự nâng T1**. Nếu bật `validateExistingTransaction=true` và cấu hình không tương thích, manager có thể báo `IllegalTransactionStateException`.

Nếu thật sự cần transaction riêng với isolation riêng, `REQUIRES_NEW` có thể mở T2, nhưng đồng nghĩa thay đổi atomicity/visibility và thêm connection/locks. **Không đổi propagation chỉ để tránh một isolation mismatch** nếu business data phải commit/rollback cùng nhau.

### 7.2. Read-only và rollback rules

`tx.setReadOnly(true)` là transaction-definition hint. Tùy manager/DB, nó có thể điều chỉnh connection mode hoặc tối ưu provider. Không dựa vào nó thay database permission để cấm update.

`TransactionTemplate` **không có attributes** `rollbackFor` / `noRollbackFor` như `@Transactional`. Theo interface callback imperatively, một `RuntimeException` hoặc `Error` thoát callback được template xử lý bằng rollback. Với checked exception, callback method không khai báo `throws Exception` nên phải catch/wrap/đánh dấu rollback và quyết định cách truyền lỗi có chủ đích. Xem mục 9.

### 7.3. Tên transaction để quan sát log

`tx.setName("orders.create")` gắn name vào transaction definition. Nó hữu ích trong diagnostics/tracing, nhất là khi method dùng programmatic boundary. Tên chỉ mang tính mô tả và không thay đổi durability/isolation.

## 8. Sử dụng execute(TransactionCallback<T>)

`execute` là method cốt lõi của `TransactionTemplate`:

```java
String receipt = tx.execute(status -> {
    jdbc.update(
            "INSERT INTO receipts(id, label) VALUES (?, ?)",
            7, "paid");

    return "receipt-7";
});
```

Đây là fragment cần biến `tx` và `jdbc`, bảng `receipts`. Callback được chạy trong transaction theo definition đã cấu hình.

- Callback nhận `TransactionStatus`; có thể xem `isRollbackOnly()`, `isNewTransaction()` hoặc gọi `setRollbackOnly()`.
- Giá trị `return` của callback được trả cho caller từ `execute` nếu transaction hoàn tất thích hợp.
- Không có `return` nghĩa là phải dùng callback void hoặc return `null`.
- Nếu callback throw unchecked exception, template yêu cầu rollback appropriate transaction scope và chuyển exception ra caller.
- Nếu database commit thất bại sau callback, caller vẫn có thể nhận transaction exception thay vì giá trị bình thường. Không ghi log “đã commit” **trước khi execute trả về thành công**.

### 8.1. Callback có thể trả số, DTO hoặc kết quả query

```java
int insertedId = tx.execute(status -> {
    jdbc.update("INSERT INTO items(id, label) VALUES(10, 'new')");
    return 10;
});
```

Fragment. Chú ý `execute` trả generic `T` có thể null theo contract; nếu callback trả null, việc unboxing sang `int` sẽ lỗi. Với code thực, nên chọn non-null value hoặc kiểm tra rõ ràng.

### 8.2. Callback chạy đúng boundary, không phụ thuộc self-invocation

Vì gọi `tx.execute(...)` trực tiếp, cách này **không cần Spring AOP proxy** cho chính đoạn callback. Một method cùng class gọi method khác của nó vẫn có thể dùng template trong body. Khác với:

```java
this.otherMethodAnnotatedTransactional(); // Có thể bypass AOP advice.
```

Tuy nhiên transaction manager và datasource vẫn cần được cấu hình đúng; việc không phụ thuộc AOP không có nghĩa template có thể tạo transaction từ bất kỳ `DataSource` không liên quan.

## 9. executeWithoutResult và chủ động rollback-only

### 9.1. Không cần return: executeWithoutResult

`TransactionOperations` có convenience method `executeWithoutResult(Consumer<TransactionStatus>)`:

```java
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE orders SET status = 'PAID' WHERE id = ?", 17);
    jdbc.update("INSERT INTO outbox(event_id) VALUES(?)", 1001);
});
```

Fragment cần schema thật. Khi callback return bình thường và không yêu cầu rollback, manager đi theo đường commit (nếu scope là owner); nếu xảy ra `RuntimeException`/`Error`, transaction scope được rollback theo semantics manager.

Nếu đang tham gia một physical transaction do outer mở, callback **không tự commit** transaction vật lý ngay lúc thoát; hoàn tất commit do owner của physical transaction quyết định.

### 9.2. setRollbackOnly() — được phép return bình thường nhưng dữ liệu rollback

```java
String outcome = tx.execute(status -> {
    jdbc.update("INSERT INTO reservations(id) VALUES(99)");

    if (businessRuleRejected()) {
        status.setRollbackOnly();
        return "rejected";
    }

    return "accepted";
});
```

Fragment, cần `businessRuleRejected()` và bảng `reservations`. Khi callback tự đặt local rollback-only trên root transaction status, manager có thể rollback và `execute` **vẫn trả về** chuỗi `"rejected"`. Đó không phải bằng chứng dữ liệu đã commit. Cần phân biệt kết quả nghiệp vụ với trạng thái dữ liệu.

**Điểm quan trọng:** `status.setRollbackOnly()` chỉ đánh dấu transaction status của scope hiện hành. Nó không mở rollback vật lý tức thì ngay tại dòng gọi. Manager xử lý dấu đó khi scope hoàn tất.

### 9.3. Catch exception bên trong callback: không nuốt lỗi rồi commit nhầm

Ví dụ sai:

```java
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE accounts SET balance = balance - 100 WHERE id=1");
    try {
        chargeExternalGateway();
    } catch (RuntimeException ignored) {
        // Nếu không mark rollback-only, callback trả về bình thường.
    }
});
```

Đây là fragment anti-pattern. Nếu ngoại lệ bị bắt **bên trong** callback mà không gọi `status.setRollbackOnly()`, template không còn thấy exception đó thoát ra. Nếu database chưa tự rollback-only, giao dịch có thể commit phần debit dù gateway thất bại.

Cách xử lý có chủ đích:

```java
tx.executeWithoutResult(status -> {
    try {
        performAllRequiredOperations();
    } catch (RecoverableBusinessException ex) {
        status.setRollbackOnly();
        // Phản hồi nghiệp vụ được xử lý ở caller, không giả commit.
    }
});
```

Đây là fragment, cần định nghĩa exception và operation tương ứng. Nếu muốn caller biết lỗi, cân nhắc rethrow một unchecked domain exception thay vì nuốt. Khi operation đã làm external side effects, DB rollback cũng không tự hoàn tác tác vụ bên ngoài; cần idempotency/outbox/saga khi phù hợp.

### 9.4. RuntimeException, Error và checked Exception

`TransactionTemplate.execute(...)` xử lý các `RuntimeException` và `Error` thoát callback bằng rollback, rồi truyền lỗi lại; nếu manager xử lý rollback thất bại, transaction exception có thể thay thế hoặc bổ sung thông tin gốc.

Callback API không khai báo checked exception, nên mã sau **không biên dịch** khi `readFile()` khai báo `throws IOException` mà không có catch:

```java
tx.execute(status -> {
    readFile();   // Giả sử throws IOException: phải handle tại đây.
    return null;
});
```

Đây là **fragment minh họa lỗi biên dịch có chủ đích**, không phải đoạn chương trình runnable. Cách hợp lệ:

```java
tx.executeWithoutResult(status -> {
    try {
        readFile();
        jdbc.update("INSERT INTO imports(id) VALUES(1)");
    } catch (IOException ex) {
        throw new UncheckedIOException("File import failed", ex);
    }
});
```

Đây là fragment, cần imports `java.io.IOException`, `java.io.UncheckedIOException` và biến/hàm thật. `UncheckedIOException` kế thừa `RuntimeException`; template sẽ nhận exception thoát callback và rollback. Khi checked exception biểu thị tình huống nghiệp vụ bình thường, có thể `status.setRollbackOnly()` và trả result rõ ràng thay vì luôn wrap.

**Không áp dụng máy móc** `@Transactional(rollbackFor = Exception.class)` vào template; thuộc tính annotation đó là một cơ chế declarative khác. Với programmatic callback, xử lý exception/rollback được viết trong code.

## 10. Trường hợp có @Transactional ở outer

Ví dụ outer đã có `@Transactional(REQUIRED)`, inner dùng template mặc định `REQUIRED`:

```java
@Service
public class OuterService {
    private final TransactionTemplate tx;

    public OuterService(PlatformTransactionManager manager) {
        this.tx = new TransactionTemplate(manager); // REQUIRED default
    }

    @Transactional
    public void placeOrder() {
        tx.executeWithoutResult(status -> {
            // Chạy trong physical transaction của outer
            // nếu dùng đúng manager/resource.
        });
    }
}
```

Fragment class cần imports và code nghiệp vụ. Trong kịch bản phổ biến:

1. `@Transactional` advice của outer mở physical transaction T1.
2. `tx.executeWithoutResult` yêu cầu transaction `REQUIRED` qua cùng manager.
3. Template tạo logical scope tham gia T1, không mở physical T2.
4. Callback hoàn tất bình thường không đồng nghĩa T1 commit ngay.
5. Khi outer method return, outer interceptor mới quyết định commit/rollback T1.

Nếu callback đánh dấu rollback-only hoặc ném unchecked exception dẫn đến participating rollback, **physical T1 có thể bị global rollback-only**. Outer có thể nhận `UnexpectedRollbackException` khi cố commit dù đã catch inner exception. Không sửa bằng `REQUIRES_NEW` trừ khi nghiệp vụ chấp nhận independent commit.

### 10.1. Khi cố ý cần commit độc lập

```java
TransactionTemplate auditTx = new TransactionTemplate(manager);
auditTx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
```

Khi chạy `auditTx.execute(...)` bên trong outer transaction, Spring tạm treo context T1 rồi bắt đầu physical T2 (khi manager hỗ trợ). Inner T2 có thể commit ngay; T1 vẫn còn mở và có thể rollback về sau. Đây là semantics phù hợp cho **audit của một lần thử** cần lưu dù outer fail, không phù hợp cho bản audit tuyên bố order đã commit trước khi order thực sự commit.

**Rủi ro tài nguyên:** outer có thể vẫn giữ JDBC connection và row locks, còn inner cần connection mới. Pool exhaustion hoặc lock waits có thể xảy ra. T2 cũng không tự nhìn thấy inserts chưa commit của T1; tránh foreign key/predicate phụ thuộc dữ liệu đó.

## 11. Một bean manager, nhiều templates: quy ước naming rõ ràng

Một application có thể cấu hình:

```text
ordersDataSource
     |
     v
ordersTransactionManager  (JdbcTransactionManager)
     |
     +-- requiredOrderTx       (PROPAGATION_REQUIRED)
     |
     +-- independentAuditTx    (PROPAGATION_REQUIRES_NEW)

auditDataSource
     |
     v
auditTransactionManager   (JdbcTransactionManager)
     |
     +-- externalAuditTx      (một manager/DB khác)
```

Có hai trục **độc lập**:

- **Manager** chọn resource/transaction system nào được điều phối.
- **Template definition** chọn propagation/isolation/timeout/read-only cho transaction của manager đó.

Nếu hai template cùng manager với `REQUIRED` và `REQUIRES_NEW`, chúng vẫn chia sẻ **cùng datasource**, nhưng tạo scope khác nhau. Nếu hai managers điều phối hai datasources, thay đổi propagation trên một manager không làm hai databases tự đồng bộ commit.

### 11.1. @Qualifier khi có nhiều managers

```java
@Bean("ordersTxTemplate")
TransactionTemplate ordersTxTemplate(
        @Qualifier("ordersTransactionManager")
        PlatformTransactionManager ordersManager) {
    return new TransactionTemplate(ordersManager);
}

@Bean("auditTxTemplate")
TransactionTemplate auditTxTemplate(
        @Qualifier("auditTransactionManager")
        PlatformTransactionManager auditManager) {
    return new TransactionTemplate(auditManager);
}
```

Fragments cần Spring `@Configuration`, imports, và beans managers tương ứng. Dùng `@Qualifier` trên **manager** lẫn template injection khi cần. Không dựa vào tên biến Java để khẳng định manager được chọn đúng ở runtime.

Nếu hai resources cần commit atomically, cần thiết kế distributed transaction phù hợp hoặc saga/outbox/idempotency. Một `TransactionTemplate` không thể biến hai local transaction managers độc lập thành global atomic transaction.

### 11.2. Không nên tạo manager mới từ một datasource tùy tiện ở mỗi call

```java
// Anti-pattern cấu hình theo từng request:
PlatformTransactionManager m =
        new JdbcTransactionManager(new SomeDataSource());
TransactionTemplate tx = new TransactionTemplate(m);
```

Đây là fragment minh họa **thiết kế không nên dùng** (SomeDataSource không phải type thật). Nó dễ bỏ qua resource/cấu hình có sẵn của ứng dụng và tạo sai manager/pool.

Thông thường, khai báo một transaction manager bean chính thức, inject nó; cần thay đổi `TransactionTemplate` settings thì tạo các template beans riêng.

## 12. Bài tập runnable: Spring 6.2.8 + JDBC + H2 + Maven + Java 17

Ta xây ứng dụng console nhỏ **không phụ thuộc Spring Boot**, dùng programmatic transaction boundaries. Không cần `@EnableTransactionManagement` vì không dùng `@Transactional` để demarcate transaction trong demo.

**Các kịch bản:**

1. `TransactionTemplate` bean `requiredTemplate` mặc định `REQUIRED` commit một insert và trả kết quả.
2. Callback throw `IllegalStateException`; template rollback và truyền exception cho caller.
3. Callback gọi `status.setRollbackOnly()` nhưng trả về chuỗi bình thường; thay đổi SQL vẫn rollback.
4. Outer `REQUIRED` ghi một order rồi gọi `REQUIRES_NEW` template để ghi audit vào bảng **khác**, sau đó outer tự rollback; bản audit đã commit của inner vẫn tồn tại.
5. Sau từng kịch bản, dùng `JdbcTemplate` ngoài transaction để truy vấn số hàng, kiểm chứng transaction đã được commit/rollback thực tế.

### 12.1. Cấu trúc thư mục

```text
transaction-template-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TransactionTemplateDemo.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>transaction-template-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TransactionTemplateDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. src/main/java/dev/learning/TransactionTemplateDemo.java

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionTemplateDemo {

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:transaction_template;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        // Cách 1: tạo TransactionTemplate từ manager ngay trong @Bean.
        @Bean("requiredTemplate")
        TransactionTemplate requiredTemplate(
                PlatformTransactionManager manager) {
            TransactionTemplate template =
                    new TransactionTemplate(manager);

            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);
            template.setIsolationLevel(
                    TransactionDefinition.ISOLATION_READ_COMMITTED);
            template.setName("demo.required");
            return template;
        }

        // Cách 2: constructor manager + TransactionDefinition.
        @Bean("auditTemplate")
        TransactionTemplate auditTemplate(
                PlatformTransactionManager manager) {
            DefaultTransactionDefinition definition =
                    new DefaultTransactionDefinition();

            definition.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            definition.setName("demo.independent-audit");

            return new TransactionTemplate(manager, definition);
        }

        @Bean
        OrderOperations orderOperations(
                JdbcTemplate jdbc,
                @Qualifier("requiredTemplate")
                TransactionTemplate required,
                @Qualifier("auditTemplate")
                TransactionTemplate audit) {
            return new OrderOperations(jdbc, required, audit);
        }
    }

    public static class OrderOperations {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate required;
        private final TransactionTemplate audit;

        public OrderOperations(
                JdbcTemplate jdbc,
                TransactionTemplate required,
                TransactionTemplate audit) {
            this.jdbc = jdbc;
            this.required = required;
            this.audit = audit;
        }

        // execute trả một giá trị do callback tạo.
        public int commitAndCount() {
            Integer count = required.execute(status -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    1, "committed");

                return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders",
                    Integer.class);
            });
            return count;
        }

        // RuntimeException thoát callback => template rollback.
        public void failAndRollback() {
            required.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    2, "should rollback");

                throw new IllegalStateException("simulated failure");
            });
        }

        // Có thể trả result bình thường dù yêu cầu rollback.
        public String markRollbackAndReturn() {
            return required.execute(status -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    3, "rolled back by status");

                status.setRollbackOnly();
                return "business rejected";
            });
        }

        // T2 commit audit độc lập; T1 bị rollback theo quyết định outer.
        public void auditPersistsAfterOuterRollback() {
            required.executeWithoutResult(outer -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    4, "outer should rollback");

                audit.executeWithoutResult(inner -> {
                    jdbc.update(
                        "INSERT INTO audits(id, label) VALUES(?, ?)",
                        40, "attempt recorded");
                });

                outer.setRollbackOnly();
            });
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table,
                Integer.class);
    }

    private static void showCounts(
            JdbcTemplate jdbc, String phase) {
        System.out.println(
                phase
                + " orders=" + count(jdbc, "orders")
                + " audits=" + count(jdbc, "audits"));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE orders (
                        id INT PRIMARY KEY,
                        label VARCHAR(100) NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE audits (
                        id INT PRIMARY KEY,
                        label VARCHAR(100) NOT NULL
                    )
                    """);

            OrderOperations operations =
                    context.getBean(OrderOperations.class);

            System.out.println(
                    "commit.insideCount="
                    + operations.commitAndCount());
            showCounts(jdbc, "afterCommit");

            try {
                operations.failAndRollback();
            } catch (IllegalStateException ex) {
                System.out.println(
                        "failure.message=" + ex.getMessage());
            }
            showCounts(jdbc, "afterFailure");

            System.out.println(
                    "explicit.result="
                    + operations.markRollbackAndReturn());
            showCounts(jdbc, "afterExplicit");

            operations.auditPersistsAfterOuterRollback();
            showCounts(jdbc, "afterIndependent");
        }
    }
}
```

### 12.4. Biên dịch và chạy

Yêu cầu JDK 17+ và Maven 3.x. Trong thư mục `transaction-template-demo`, lần đầu chạy Maven cần truy cập kho dependencies:

```bash
mvn -q clean compile exec:java
```

Các dòng **chính chương trình** in ra theo thứ tự kỳ vọng, không bao gồm log từ Maven/Spring:

```text
commit.insideCount=1
afterCommit orders=1 audits=0
failure.message=simulated failure
afterFailure orders=1 audits=0
explicit.result=business rejected
afterExplicit orders=1 audits=0
afterIndependent orders=1 audits=1
```

### 12.5. Diễn giải từng kịch bản

**Kịch bản 1 — commit với giá trị trả về.** `commitAndCount()` gọi `required.execute`. Callback insert order ID=1 rồi truy vấn count trong cùng transaction, trả `1`. Template yêu cầu manager commit T1 khi callback trả bình thường. Sau khi method kết thúc, query bên ngoài cho biết có một order và chưa có audit.

**Kịch bản 2 — rollback vì unchecked exception.** Callback insert ID=2 rồi ném `IllegalStateException`. Template catch để yêu cầu rollback T2 rồi rethrow lỗi. Caller nhận `simulated failure`; query sau đó cho thấy vẫn chỉ có order ID=1.

**Kịch bản 3 — rollback-only nhưng return bình thường.** Callback insert ID=3, gọi `status.setRollbackOnly()`, trả `"business rejected"`. Template thấy rollback-only và manager hoàn tất scope bằng rollback. Caller vẫn có chuỗi result, nhưng order count không tăng. Điều này chứng minh **result không đồng nghĩa committed**.

**Kịch bản 4 — hai templates với hai semantics.** Outer dùng `requiredTemplate` mở T4 và insert order ID=4, sau đó `auditTemplate` dùng `REQUIRES_NEW` mở T5 trên connection khác, ghi bảng `audits` và commit. Outer đặt rollback-only và cuối cùng rollback order ID=4. Audit ID=40 vẫn còn. Hai bảng **không có foreign key** với nhau để tránh inner transaction phụ thuộc một row chưa commit của outer.

**Cơ chế JDBC:** Spring `JdbcTransactionManager` và `JdbcTemplate` được cấu hình cùng bean `DataSource`, nên `JdbcTemplate` truy cập connection gắn với transaction context đúng cách. Demo dùng H2 `JdbcDataSource` đơn giản để cấp nhiều physical connections; đó không phải production connection pool. Trong production cần sizing pool phù hợp, đặc biệt với nested `REQUIRES_NEW`.

**Giới hạn kiểm chứng:** Output được thiết kế theo semantics Spring/H2 đã nêu, không phải kết quả chạy Maven trong môi trường của bài học. Để xác nhận trực tiếp, hãy chạy project trong JDK/Maven rồi so sánh stdout và queries.

### 12.6. Tự sửa ví dụ để thấy mối liên hệ manager - template

**Thử A — đổi `auditTemplate` propagation thành `REQUIRED`.** Khi audit chạy dưới outer T4, nó tham gia cùng physical transaction. Outer rollback thì audit ID=40 cũng rollback. Output cuối sẽ là `afterIndependent orders=1 audits=0`. Điều này cho thấy **định nghĩa template** chứ không phải tên phương thức `audit` quyết định commit độc lập.

**Thử B — bỏ `status.setRollbackOnly()` trong `markRollbackAndReturn`.** Order ID=3 sẽ được commit. Caller vẫn nhận cùng chuỗi `"business rejected"`, nên đây là một mismatch nghiệp vụ nếu người dùng kỳ vọng dữ liệu không được ghi khi từ chối.

**Thử C — dùng `new TransactionTemplate()` nhưng quên `setTransactionManager(...)`.** Khi template được quản lý như bean, initialization validation có thể fail; khi dùng trực tiếp mà chưa set manager, nó không thể thực hiện `execute`. Đây là lý do nên dùng constructor nhận manager.

**Thử D — đổi manager bean thành một manager dùng datasource khác.** `JdbcTemplate` không tự tham gia transaction của datasource khác. Test query sau commit/rollback có thể cho thấy các statements chạy ngoài scope mong muốn. Trong thực tế, phải bảo đảm manager, datasource và data access layer thống nhất.

**Thử E — đặt `auditTemplate` isolation riêng.** Vì audit dùng `REQUIRES_NEW`, T5 có thể nhận isolation mới theo manager/DB support. Nếu đổi sang `REQUIRED` tham gia T4, isolation declaration của inner không tự nâng isolation của T4.

## 13. Ví dụ cấu hình theo service, không tạo bean template chung

Khi chỉ một service cần template với cấu hình riêng, tạo ngay constructor vẫn là cách hợp lệ:

```java
@Service
public final class InvoiceService {
    private final TransactionTemplate invoiceTx;
    private final JdbcTemplate jdbc;

    public InvoiceService(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.jdbc = jdbc;

        TransactionTemplate template =
                new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setTimeout(10);
        template.setName("invoice.close");

        this.invoiceTx = template;
    }

    public int closeInvoice(long id) {
        return invoiceTx.execute(status -> jdbc.update(
                "UPDATE invoices SET closed = TRUE WHERE id = ? "
                + "AND closed = FALSE",
                id));
    }
}
```

Đây là **fragment Spring service**, cần imports, schema, và manager bean. `jdbc.update(...)` trả affected row count; nếu kết quả = 0, invoice không tồn tại hoặc đã đóng. Trong nghiệp vụ thật, cần quyết định rõ 0 rows là idempotent success hay failure. Dù `execute` trả 0, transaction vẫn có thể commit bình thường; **commit thành công không đồng nghĩa business update thành công**.

**Không tạo template mới sau mỗi request nếu cấu hình không đổi**; khởi tạo một lần trong constructor hoặc Spring `@Bean` là đơn giản và đủ an toàn.

## 14. Tạo template từ một TransactionDefinition dùng chung

Có thể tách transaction settings khỏi code khởi tạo:

```java
DefaultTransactionDefinition settings =
        new DefaultTransactionDefinition();
settings.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
settings.setReadOnly(true);
settings.setTimeout(5);
settings.setName("report.read");

TransactionTemplate reportTx =
        new TransactionTemplate(manager, settings);
```

Fragment. Cách này phù hợp khi nhiều templates cần phần lớn settings giống nhau nhưng manager/resource khác nhau. Tuy nhiên đừng dùng **cùng một mutable definition object** rồi kỳ vọng mọi template tự theo các thay đổi về sau: constructor được mô tả là lấy/copy defaults ban đầu; nên coi settings và template là cấu hình lúc khởi tạo.

Nếu chỉ muốn một biến cho các operations `execute` mà không cần setters ở consuming service, có thể expose `TransactionOperations` interface:

```java
@Bean("reportTransactions")
TransactionOperations reportTransactions(
        PlatformTransactionManager manager) {
    TransactionTemplate template = new TransactionTemplate(manager);
    template.setReadOnly(true);
    return template;
}
```

Fragment cần import `org.springframework.transaction.support.TransactionOperations`. Client inject `@Qualifier("reportTransactions") TransactionOperations tx`. Cách này thu hẹp API client, hữu ích cho testing, nhưng **đừng tự hiểu interface là một manager mới**; vẫn cùng implementation/template.

## 15. TransactionTemplate và @Transactional: chọn đúng lúc

| Câu hỏi | `TransactionTemplate` | `@Transactional` |
| --- | --- | --- |
| Cách đặt boundary | Code trực tiếp gọi `execute(callback)` | AOP advice khi method được gọi qua proxy/aspect |
| Cần Spring proxy cho chính boundary? | Không; explicit method call | Thường cần trong proxy mode |
| Thao tác trong một phần của method | Dễ bao một đoạn code cụ thể | Thường áp dụng quanh method đã intercept |
| Cấu hình propagation/isolation | Template setters hoặc definition | Annotation attributes |
| Rollback theo exception | RuntimeException/Error thoát callback => rollback; tự dùng `setRollbackOnly` | Rollback rules configurable qua `rollbackFor`/`noRollbackFor` |
| Code coupling | Phụ thuộc Spring transaction APIs | Annotation-based, ít imperative boilerplate |
| Testability | Có thể inject `TransactionOperations`/mock hoặc fake và verify DB | Test qua Spring context/proxy và transaction infrastructure |
| Khi có outer transaction | Phụ thuộc propagation template | Phụ thuộc propagation annotation |
| Reactive | Dùng `TransactionalOperator` thay vì dùng imperative template cho Reactor flows | Reactive annotations có semantics manager/context tương ứng |

Không phải chọn một trong hai cho toàn ứng dụng. Có thể dùng `@Transactional` ở nhiều use cases và dùng `TransactionTemplate` cho đoạn đặc biệt muốn boundary explicit. Nhưng tránh đặt hai cơ chế chồng chéo không có chủ đích vì dễ hiểu nhầm thời điểm commit.

### 15.1. Tách đoạn transaction nhỏ trong method lớn

```java
public ProcessResult process(Request request) {
    NormalizedInput input = validateOutsideTransaction(request);

    return tx.execute(status -> {
        // Chỉ phần DB atomic có transaction.
        return persistAtomically(input);
    });
}
```

Fragment. Việc validate/CPU-heavy trước transaction có thể giảm thời gian giữ connection/locks. Nhưng **đừng** chuyển các checks có race-sensitive invariant ra ngoài mà không revalidate dưới transaction/lock: việc “đọc tồn kho rồi quyết định” trước transaction vẫn có thể stale.

### 15.2. Không dùng @Transactional trên method gọi qua this chỉ để bù cho việc bỏ template

Trong proxy mode mặc định:

```java
public void entry() {
    this.write(); // Không đi qua transactional proxy.
}

@Transactional
public void write() {
    // ...
}
```

Fragment anti-pattern. Nếu cần direct boundary, một lời gọi `tx.execute(...)` không gặp self-invocation bypass cho chính callback. Hoặc tách boundary sang Spring bean khác và gọi qua injected proxy.

### 15.3. Không trộn API imperative và reactive

`TransactionTemplate` làm việc với `PlatformTransactionManager` và imperative/thread-bound transaction management. Với R2DBC/WebFlux non-blocking, Spring khuyến nghị `TransactionalOperator` với `ReactiveTransactionManager`, sử dụng Reactor context. Không đưa `TransactionTemplate` vào một `Mono` rồi giả định các queries chạy sau đó trên threads khác vẫn ở JDBC transaction context ban đầu.

## 16. Các lỗi cấu hình phổ biến

### 16.1. “No transaction manager configured”

Nguyên nhân: dùng no-arg constructor mà chưa set manager, hoặc Spring container chưa inject manager. Cách sửa: inject `PlatformTransactionManager` và dùng `new TransactionTemplate(manager)`, hoặc cấu hình bean property đúng. Không thể tạo transaction chỉ bằng tên class.

### 16.2. Multiple PlatformTransactionManager beans

Nếu có `ordersTransactionManager` và `billingTransactionManager`, injection theo type có thể ambiguity. Chọn đúng manager bằng `@Qualifier`, đặt tên bean rõ, và test resource mà manager quản lý. Không chỉ đánh dấu một manager `@Primary` rồi mong nó phù hợp với mọi datasources.

### 16.3. Transaction manager không tương ứng JdbcTemplate datasource

Ví dụ `JdbcTransactionManager(dsA)` nhưng `JdbcTemplate(dsB)`. Gọi template có thể mở transaction trên A, trong khi SQL thực thi trên B ngoài transaction đó. Kết quả là rollback template không hoàn tác dữ liệu trên B. Cần cấu hình manager và datasource/data access layer đúng cặp.

### 16.4. Đổi propagation trên singleton template trong giờ chạy

Những setters cấu hình có mutable state. Nếu đồng thời nhiều HTTP requests chia sẻ một instance rồi lần lượt gọi `setPropagationBehavior` trước `execute`, có thể gây race semantic: request A tưởng `REQUIRED` nhưng request B đã đổi sang `REQUIRES_NEW`. Dùng hai templates đã cấu hình cố định.

### 16.5. Trả về success dù setRollbackOnly

Nếu callback gọi `status.setRollbackOnly()` rồi trả `"ok"`, template có thể trả `"ok"` sau khi rollback chủ động. Caller cần phân biệt result nghiệp vụ và transaction outcome. Không báo “đã lưu” chỉ vì method không ném exception.

### 16.6. Nuốt exception bên trong callback

Nếu exception được catch trước khi thoát callback và không set rollback-only, manager có thể commit các ghi trước đó. Exception translation/DB failure có thể vẫn khiến resource không thể commit; không dùng catch-and-ignore như một transaction strategy.

### 16.7. Mang TransactionStatus ra khỏi callback

`TransactionStatus` gắn với scope đang active. Không lưu nó vào field hay async task để gọi `setRollbackOnly()` sau khi callback đã hoàn tất; status lúc đó có thể completed, và transaction context không tự đi theo thread mới.

### 16.8. Cố sửa transaction đã rollback-only bằng REQUIRES_NEW

Inner `REQUIRED` có thể đánh dấu shared physical transaction rollback-only; outer cố commit nhận `UnexpectedRollbackException`. Chuyển inner sang `REQUIRES_NEW` chỉ vì muốn tránh exception có thể làm inner commit độc lập và phá invariants. Hãy xác định dữ liệu nào phải cùng rollback.

### 16.9. Quên pool sizing khi dùng REQUIRES_NEW

Outer transaction vẫn giữ connection/locks trong lúc inner xin connection mới. Nếu pool quá nhỏ, nhiều concurrent requests cùng giữ outer connections rồi chờ inner có thể bị connection timeout. Nếu inner chạm row outer đang khóa, lock wait vẫn xảy ra ngay cả khi pool đủ lớn.

### 16.10. Cho rằng readOnly=true bảo đảm SELECT nhất quán

`readOnly` là một hint; isolation và query semantics mới quyết định snapshot/visibility. Nếu report cần nhất quán xuyên nhiều SELECT, đặt transaction boundary, isolation và snapshot requirements theo DBMS.

### 16.11. Cho rằng timeout trên template giới hạn HTTP call bên trong callback

`TransactionTemplate.setTimeout(10)` là transaction definition gửi tới manager, không phải một timer tự động cắt mọi HTTP/file/network operation. Cần timeouts riêng cho client/database statement và ứng dụng.

## 17. Kiểm thử các thuộc tính cấu hình

### 17.1. Unit test cấu hình đơn giản

Khi chỉ cần xác minh template được cấu hình theo manager và defaults:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
tx.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(15);
tx.setReadOnly(true);

assert tx.getTransactionManager() == manager;
assert tx.getPropagationBehavior()
        == TransactionDefinition.PROPAGATION_REQUIRES_NEW;
assert tx.getIsolationLevel()
        == TransactionDefinition.ISOLATION_READ_COMMITTED;
assert tx.getTimeout() == 15;
assert tx.isReadOnly();
```

Đây là **Java fragment** với `manager` giả định, dùng keyword `assert` (chỉ hoạt động khi bật assertions `-ea`). Trong JUnit thực, nên dùng `Assertions.assertSame`/`assertEquals` và inject bean thật khi cần kiểm thử configuration.

**Unit test setters không chứng minh actual DB commit.** Cần integration test.

### 17.2. Integration test transaction outcome

Checklist:

| Tình huống | Action | Quan sát sau boundary |
| --- | --- | --- |
| Return bình thường | Callback insert + return | Row tồn tại |
| Runtime exception | Callback insert + throw | Row không tồn tại, caller nhận exception |
| Explicit rollback-only | Callback insert + setRollbackOnly + return | Row không tồn tại dù caller nhận return value |
| Joined REQUIRED | Outer T1 đang active, inner template REQUIRED ghi | Inner không tự commit vật lý; outer rollback kéo theo inner |
| REQUIRES_NEW | Outer T1 ghi, inner template T2 ghi độc lập, outer rollback | Chỉ T2 còn, nếu không có FK/lock dependency |
| Wrong manager | Manager dsA, JdbcTemplate dsB | Test phát hiện rollback không bảo vệ B như kỳ vọng |
| Two template configs | Required và RequiresNew bean rõ tên | Không xảy ra settings mutation giữa requests |
| Checked exception | Callback catch checked exception, wrap hoặc mark | Rollback/response theo thiết kế |
| Isolation mismatch | Outer READ_COMMITTED, inner REQUIRED SERIALIZABLE | Không kỳ vọng tự nâng isolation; validate manager nếu cần |

Với Spring TestContext, một test method có `@Transactional` thường bị rollback cuối test và có thể **che** dữ liệu commit của service. Để test template commit thực tế, không nên vô tình bao toàn test bằng test-managed transaction, hoặc dùng `TestTransaction` có chủ đích.

### 17.3. Test với hai managers

Nếu muốn bảo đảm orders và audit kết nối đúng DB:

- Tạo hai datasources/test schemas hoặc hai H2 databases khác tên.
- Tạo `ordersTransactionManager` và `auditTransactionManager`.
- Tạo templates inject qua `@Qualifier`.
- Thực hiện transaction ở mỗi bên.
- Query độc lập từ từng datasource sau commit/rollback.
- Xác nhận rollback ở DB A **không tự** rollback DB B nếu đây là hai local managers không có coordination chung.

Nếu nghiệp vụ yêu cầu đồng bộ atomic trên hai DB, test này sẽ phơi bày rằng chỉ có hai templates không đủ. Khi đó cần giải pháp như distributed transaction hoặc saga/outbox, không phải đổi propagation tùy ý.

## 18. Một luồng thiết kế chuẩn cho dự án Spring

### Bước 1 — cấu hình DataSource và manager

```text
DataSource đúng database
       |
       v
PlatformTransactionManager bean
       |
       v
TransactionTemplate bean(s)
       |
       v
Service constructor injection
       |
       v
transactionTemplate.execute(callback)
```

Khi dùng Spring Boot, Boot có thể tự cấu hình `DataSource` và transaction manager theo starters/configuration phù hợp. Trước khi tự tạo mới, xác định beans đã được Boot cung cấp. Tránh có hai managers vô tình khiến injection ambiguous.

### Bước 2 — ghi rõ business semantics trong tên template

Tên như `orderRequiredTx`, `auditIndependentTx`, `reportReadOnlyTx` tốt hơn tên chung `tx1`/`tx2`. Với code review, việc thấy template nào được dùng quan trọng vì hai templates có thể quyết định sự tồn tại của dữ liệu sau outer rollback.

### Bước 3 — giữ callback ngắn, tập trung vào DB atomic unit

Không giữ transaction xuyên HTTP, chờ queue hoặc quá trình CPU dài nếu không cần. Transaction kéo dài làm giữ connection/locks lâu và tăng contention.

### Bước 4 — xử lý rollback theo kết quả nghiệp vụ

Nếu nghiệp vụ từ chối có thể coi là một kết quả bình thường, `status.setRollbackOnly()` và return domain result rõ ràng là hợp lệ; nếu có lỗi nghiêm trọng, rethrow unchecked exception để caller biết. Không nuốt lỗi rồi báo thành công.

### Bước 5 — bảo vệ invariants đồng thời

Template **không tự thay thế** optimistic version, atomic update predicate, database constraint hoặc pessimistic lock. Nếu hai transactions cạnh tranh tồn kho, một `execute` đúng boundary vẫn có thể chứa read-modify-write sai cách. Kết hợp đúng isolation/locking/constraint và retry trên transaction mới khi cần.

### Bước 6 — quan sát kết quả sau boundary

Log/bộ đếm/metrics trước khi callback kết thúc không chứng minh database commit. Khi tích hợp external effects, cần đảm bảo event được gửi theo chính sách sau commit/outbox, tránh gửi trước rồi outer rollback.

## 19. Hỏi đáp để kiểm tra kiến thức

**Câu 1.** `new TransactionTemplate(manager)` có mở JDBC transaction ngay không?

Không. Constructor chỉ tạo/configure template. Transaction được yêu cầu khi gọi `execute(...)` hoặc `executeWithoutResult(...)`.

**Câu 2.** Có thể dùng template mà không có `@EnableTransactionManagement` không?

Có, đối với programmatic `TransactionTemplate`. `@EnableTransactionManagement` chủ yếu kích hoạt annotation-driven transaction advice. Template gọi manager trực tiếp, không cần AOP proxy cho bản thân callback.

**Câu 3.** `TransactionTemplate` tự biết database cần commit không?

Không. Nó nhận một `PlatformTransactionManager`; manager được cấu hình cho resource thật. Nếu manager dùng dsA còn SQL dùng dsB thì semantics không được bảo đảm như mong muốn.

**Câu 4.** Khi callback trả giá trị bình thường nhưng gọi `status.setRollbackOnly()`, kết quả thế nào?

Với root transaction scope, manager thường rollback, còn `execute` vẫn có thể trả về giá trị bình thường. Return value không chứng minh commit.

**Câu 5.** Một singleton `TransactionTemplate` có dùng chung cho nhiều threads không?

Có theo tài liệu Spring, khi **cấu hình được cố định**. Không mutate propagation/isolation/timeout settings trong khi các requests đang gọi execute.

**Câu 6.** Vì sao nên dùng hai templates khi có hai propagation modes?

Vì template giữ mutable configuration, và semantics khác nhau. Hai instances cấu hình sẵn `REQUIRED`/`REQUIRES_NEW` tránh race và giúp code review nhận ra independent commit.

**Câu 7.** `execute(...)` và `executeWithoutResult(...)` khác gì?

`execute` dùng `TransactionCallback<T>` có thể trả giá trị kiểu `T`. `executeWithoutResult` tiện cho callback void; cả hai dùng transaction boundary của template.

**Câu 8.** Checked `IOException` có tự đi qua callback và kích hoạt `rollbackFor` không?

Không theo mô hình annotation `rollbackFor`, vì `TransactionTemplate` không có attribute đó. Java callback không khai báo checked exception, nên phải catch và wrap unchecked hoặc gọi `setRollbackOnly()`, rồi xử lý nghiệp vụ có chủ đích.

**Câu 9.** Nếu outer `@Transactional` và inner template đều `REQUIRED`, inner có tự commit khi callback return không?

Không nếu inner đang tham gia physical transaction T1 của outer. Manager chỉ hoàn tất logical scope; physical commit thuộc outer owner.

**Câu 10.** Nếu inner `REQUIRES_NEW` commit, rồi outer rollback thì inner có còn không?

Có thể còn, vì T2 độc lập. Điều đó chỉ nên được dùng khi business semantics chấp nhận dữ liệu inner tồn tại độc lập.

**Câu 11.** Khi có hai `PlatformTransactionManager` beans, sửa injection thế nào?

Dùng `@Qualifier` hoặc cấu hình resolution rõ ràng để chọn đúng manager cho datasource/provider tương ứng; đặt tên template beans và test effect trên DB thật.

**Câu 12.** Có nên tạo transaction template mới trong mỗi lambda?

Không cần khi settings không đổi. Dùng field/bean chia sẻ đã cấu hình trước giúp đơn giản, dễ test và tránh tạo mutable settings per-call.

**Câu 13.** `readOnly=true` trên template có đảm bảo không ghi được trong mọi database không?

Không. Đây thường là hint/cấu hình được manager/resource diễn giải theo khả năng. Muốn cấm write chắc chắn cần database permissions/constraints phù hợp.

**Câu 14.** Khi nào dùng `TransactionalOperator` thay cho template?

Khi flow thực sự là reactive (Reactor/R2DBC) với `ReactiveTransactionManager`. `TransactionTemplate` dành cho imperative `PlatformTransactionManager`.

**Câu 15.** Nếu callback bị failure sau khi gửi email thì DB rollback có thu hồi email không?

Không. Transaction manager chỉ điều phối những resources nó quản lý; external side effects cần outbox/idempotency/compensation phù hợp.

## 20. Checklist cuối trước khi áp dụng

- [ ] `PlatformTransactionManager` là Spring bean đúng datasource/entity manager factory.
- [ ] `TransactionTemplate` được tạo với manager hợp lệ, thường bằng constructor injection.
- [ ] Mục đích của mỗi template bean rõ qua tên `REQUIRED`/`REQUIRES_NEW` hoặc read-only.
- [ ] Setters của shared template chỉ chạy khi khởi tạo, không mutate giữa requests.
- [ ] Có template riêng nếu semantics propagation/isolation/timeout khác nhau.
- [ ] Code gọi `execute(...)` hoặc `executeWithoutResult(...)`, không tưởng constructor tự mở transaction.
- [ ] Spring data-access operations dùng đúng resource, ví dụ cùng `DataSource` cho `JdbcTransactionManager` và `JdbcTemplate`.
- [ ] Callback chỉ bao atomic DB work cần thiết, tránh giữ transaction qua slow HTTP/CPU.
- [ ] Checked/unchecked exceptions được xử lý đúng; không nuốt failure rồi commit một phần.
- [ ] `status.setRollbackOnly()` được dùng có chủ đích và result trả về không báo commit giả.
- [ ] Inner `REQUIRED` không bị hiểu nhầm tự commit độc lập.
- [ ] `REQUIRES_NEW` chỉ chọn khi nghiệp vụ chấp nhận independent commit và pool/locks đủ đáp ứng.
- [ ] Isolation/read-only/timeout phù hợp manager và DB, không dựa trên annotation khác để thay đổi physical transaction đang có.
- [ ] Tests xác nhận data commit/rollback sau khi boundary thực sự hoàn tất.
- [ ] Nếu có nhiều managers, đã dùng qualifiers và tests để tránh transaction bao sai DB.

## 21. Kết luận

**Cách tạo đơn giản nhất**:

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);
tx.executeWithoutResult(status -> {
    // Thao tác database cần transaction.
});
```

Nhưng viết đúng production code cần hiểu:

- `PlatformTransactionManager` quyết định transaction resources thật, còn `TransactionTemplate` chỉ giữ definition và điều phối callback.
- `execute` tạo **scope theo propagation**, không luôn mở physical transaction mới.
- Template dùng chung được nếu **cấu hình cố định**; các settings khác nhau cần những instances khác nhau.
- `RuntimeException`/`Error` thoát callback thường rollback; explicit `setRollbackOnly()` có thể rollback dù callback trả về bình thường.
- `REQUIRED` và `REQUIRES_NEW` là hai semantics khác nhau về việc dữ liệu có thể tồn tại sau outer rollback; không thay tùy tiện chỉ để chữa exception.
- Spring JDBC data access phải cùng resource với transaction manager; có manager bean sai thì template đúng syntax vẫn không tạo atomicity mong đợi.
- Với reactive transactions, dùng `TransactionalOperator` chứ không giả lập JDBC thread-bound behavior.

## Tài liệu chính thức

1. [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): hướng dẫn constructor injection, `execute`, `setRollbackOnly`, settings và tính thread-safe của `TransactionTemplate`.
2. [Spring Framework 6.2 — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): constructors, `setTransactionManager`, `afterPropertiesSet` và callbacks.
3. [Spring Framework 6.2 — TransactionOperations Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html): `execute` và `executeWithoutResult`.
4. [Spring Framework 6.2 — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): imperative manager contract.
5. [Spring Framework 6.2 — DefaultTransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html): propagation, isolation, timeout, read-only và name setters.
6. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW` và nested scopes.
7. [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): datasource, `DataSourceUtils` và JDBC resource synchronization.
8. [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): khác biệt giữa annotation/AOP boundaries và programmatic management.
