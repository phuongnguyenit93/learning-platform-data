# Phân biệt kết thúc phương thức với hoàn tất commit trong Spring Framework

## 1. Hai thời điểm khác nhau

Trong Spring Transaction Management, câu "phương thức `@Transactional` đã chạy xong" có thể chỉ **thân phương thức Java (target method) đã đi tới `return`**. Điều đó **chưa khẳng định dữ liệu đã `COMMIT` thành công**.

Cần phân biệt ít nhất ba mốc:

1. **Thân phương thức kết thúc:** các lệnh trong phương thức đã chạy tới cuối hoặc `return`; kết quả tạm thời được trả cho transaction interceptor/proxy. SQL có thể đã được gửi xuống cơ sở dữ liệu, nhưng transaction còn đang mở.
2. **Transaction vật lý hoàn tất:** transaction manager đã yêu cầu cơ sở dữ liệu `COMMIT` và nhận kết quả thành công, hoặc đã `ROLLBACK`. Trước commit vẫn có thể có flush, callback, kiểm tra ràng buộc, lỗi kết nối, đánh dấu `rollback-only`...
3. **Lời gọi qua Spring proxy kết thúc:** caller nhận giá trị trả về hoặc exception sau khi interceptor xử lý transaction. Nếu proxy **tự sở hữu transaction vật lý** trong một lời gọi đồng bộ thông thường, caller chỉ nhận kết quả thành công sau khi commit thành công và các callback đồng bộ liên quan đã chạy. Nếu phương thức chỉ **tham gia transaction của caller**, việc nó trả về không phải mốc commit cuối cùng.

Đó là lý do `return orderId;` trong service không đồng nghĩa với "đơn hàng đã lưu bền vững" ngay tại dòng `return`, và log "save completed" đặt trước `return` không phải bằng chứng commit thành công.

| Dấu hiệu quan sát | Kết luận hợp lệ |
| --- | --- |
| Đã tới `return` bên trong service `@Transactional` | Thân phương thức hoàn tất; commit có thể chưa bắt đầu. |
| `repository.save(...)` trả về | Lệnh lưu đã được tiếp nhận theo ngữ nghĩa repository; chưa xác nhận commit. |
| `entityManager.flush()` hoặc `saveAndFlush(...)` thành công | Đồng bộ các thay đổi đang chờ xuống DB; **flush không phải commit**. |
| `TransactionSynchronization.afterCommit()` được gọi | Commit của transaction tương ứng đã thành công. |
| Caller nhận kết quả thành công từ proxy đang **tạo và kết thúc** transaction vật lý | Thông thường commit đã thành công trước khi proxy trả kết quả. |
| Phương thức `REQUIRED` bên trong một transaction ngoài đã trả về | Transaction ngoài vẫn có thể rollback sau đó. |
| Một exception xuất hiện ở caller | Phải xác định exception xảy ra trước hay sau commit; không mặc định mọi exception đều nghĩa là rollback. |

## 2. Cơ chế thực thi của `@Transactional`

Với Spring transaction **đồng bộ, imperative, sử dụng proxy AOP** (trường hợp phổ biến khi dùng JDBC/JPA), luồng điển hình là:

```text
Caller
  |
  v
Spring transactional proxy / interceptor
  |-- Bắt đầu transaction mới hoặc tham gia transaction hiện có
  |-- Gọi thân phương thức service
  |     |-- Thao tác repository / JDBC / JPA
  |     |-- Log, xây kết quả và return
  |     '-- [Thân phương thức kết thúc tại đây]
  |
  |-- Nếu proxy chịu trách nhiệm hoàn tất transaction:
  |     |-- beforeCommit / flush và beforeCompletion (nếu có)
  |     |-- COMMIT hoặc ROLLBACK tại transaction manager / DB
  |     |-- afterCommit (chỉ khi commit thành công)
  |     |-- afterCompletion và cleanup
  |
  '-- Trả kết quả hoặc ném exception cho caller
```

Điều quan trọng là **Spring không thực thi `COMMIT` tại câu lệnh `return` trong thân service**. Với transaction mới, interceptor xử lý sau khi thân phương thức thoát. Nếu thân phương thức ném exception, interceptor áp dụng quy tắc rollback/commit tương ứng trước khi chuyển exception ra caller. Nếu phương thức được gọi mà không qua proxy hoặc chỉ tham gia một transaction đang có, mốc xử lý khác đi.

### Vì sao thân phương thức trả về bình thường nhưng commit vẫn có thể thất bại?

- Flush SQL xảy ra gần commit và gặp vi phạm ràng buộc khóa ngoại, unique constraint, optimistic locking hoặc lỗi khác.
- `TransactionSynchronization.beforeCommit(...)` hoặc một tác vụ chuẩn bị commit ném exception.
- Một nhánh xử lý trước đó đã đánh dấu transaction là `rollback-only`. Ở ranh giới commit, Spring có thể báo `UnexpectedRollbackException`.
- DB hoặc hệ thống quản lý transaction gặp sự cố ở bước commit.

Ví dụ, `return "OK";` trong thân service chỉ tạo giá trị dự kiến trả về. Nếu commit thất bại, caller có thể nhận exception thay vì `"OK"`.

## 3. Ví dụ chạy được: phương thức kết thúc trước commit

Ví dụ sử dụng **Java 17+, Spring Boot 3.5.16, Spring JDBC và H2**. Hai lần gọi cho thấy: một lần commit thành công và một lần thân phương thức đã kết thúc nhưng callback `beforeCommit` gây rollback. Đây là cơ chế được dùng để minh họa thứ tự; trong ứng dụng thực tế không nên cố tình ném exception trong callback chỉ để kiểm soát nghiệp vụ.

Cấu trúc:

```text
tx-boundary-demo/
  pom.xml
  src/main/java/com/example/tx/TransactionDemoApplication.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tx-boundary-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

**`src/main/java/com/example/tx/TransactionDemoApplication.java`**

```java
package com.example.tx;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
public class TransactionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JdbcTemplate jdbc, TxWriter writer) {
        return args -> {
            jdbc.execute("CREATE TABLE IF NOT EXISTS tx_demo "
                    + "(id INT PRIMARY KEY, label VARCHAR(40))");
            jdbc.update("DELETE FROM tx_demo");

            System.out.println("caller: before, rows=" + count(jdbc));
            writer.write(1, false);
            System.out.println("caller: after success, rows=" + count(jdbc));

            try {
                writer.write(2, true);
            } catch (IllegalStateException ex) {
                System.out.println("caller: caught " + ex.getMessage());
            }
            System.out.println("caller: after failure, rows=" + count(jdbc));
        };
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM tx_demo", Integer.class);
    }
}

@Service
class TxWriter {
    private final JdbcTemplate jdbc;

    TxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void write(int id, boolean rejectBeforeCommit) {
        jdbc.update(
                "INSERT INTO tx_demo (id, label) VALUES (?, ?)",
                id, "row-" + id);
        System.out.println("target: inserted id=" + id);

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void beforeCommit(boolean readOnly) {
                        if (rejectBeforeCommit) {
                            throw new IllegalStateException("commit blocked");
                        }
                    }

                    @Override
                    public void afterCommit() {
                        System.out.println("callback: committed id=" + id);
                    }
                });

        System.out.println("target: about to return id=" + id);
    }
}
```

Chạy trong thư mục `tx-boundary-demo`:

```bash
mvn spring-boot:run
```

Các dòng `System.out` chính, **bỏ qua banner và log khởi động của Spring**:

```text
caller: before, rows=0
target: inserted id=1
target: about to return id=1
callback: committed id=1
caller: after success, rows=1
target: inserted id=2
target: about to return id=2
caller: caught commit blocked
caller: after failure, rows=1
```

**Phân tích:**

- Lần `write(1, false)`: dòng `target: about to return` được in **trong thân phương thức**, trước callback `afterCommit`. Proxy bắt đầu transaction, target chạy xong, Spring commit, callback `afterCommit` in ra rồi caller mới in `after success`. DB có một hàng.
- Lần `write(2, true)`: thân phương thức vẫn đi tới dòng cuối; nhưng `beforeCommit` ném `IllegalStateException` khi proxy xử lý transaction. Spring rollback, không có dòng `callback: committed id=2`, và số hàng vẫn là `1`. Caller không nhận một lời gọi thành công.
- Thí nghiệm chứng minh mốc "target chạy tới cuối" và mốc "transaction commit thành công" **khác nhau về thời gian và kết quả**. Trong code thật, failure cũng có thể đến từ flush, ràng buộc DB hoặc rollback-only, không riêng callback.

## 4. Trả về từ phương thức con chưa chắc là transaction đã kết thúc

`@Transactional` mặc định có `propagation = REQUIRED`. Khi không có transaction, lời gọi qua proxy có thể tạo transaction mới. Khi đã có transaction bên ngoài, phương thức con **tham gia cùng transaction vật lý**, và chỉ người sở hữu ranh giới ngoài mới quyết định commit sau cùng.

```java
@Service
class CheckoutService {
    private final StockService stockService;

    CheckoutService(StockService stockService) {
        this.stockService = stockService;
    }

    @Transactional
    public void checkout() {
        stockService.reserveStock(); // Hoàn tất lời gọi này chưa phải commit
        // Nếu phần tiếp theo thất bại và transaction rollback,
        // cả thay đổi trong reserveStock() cũng có thể bị rollback.
    }
}

@Service
class StockService {
    @Transactional // REQUIRED theo mặc định
    public void reserveStock() {
        // Thay đổi dữ liệu trong cùng transaction vật lý của checkout().
    }
}
```

Đoạn này **minh họa cấu trúc service**; chưa phải chương trình độc lập vì không chứa thao tác DB và ứng dụng khởi động. Hai service cần là Spring bean và lời gọi đi qua proxy.

| Propagation | Khi phương thức con trả về |
| --- | --- |
| `REQUIRED` (mặc định), đang có transaction ngoài | Chưa commit riêng; kết quả phụ thuộc transaction ngoài. |
| `REQUIRES_NEW` | Tạo transaction vật lý độc lập, tạm treo transaction ngoài; khi lời gọi qua proxy kết thúc thành công, transaction mới đã commit riêng. Transaction ngoài có thể rollback sau đó. |
| `NESTED` (khi transaction manager/DB hỗ trợ) | Thường dùng savepoint trong cùng transaction vật lý; thoát scope con không tương đương commit vật lý độc lập. |

**Trường hợp dễ bỏ sót:** scope con `REQUIRED` đánh dấu `rollback-only` rồi return hoặc exception đã được bên ngoài bắt. Scope ngoài vẫn cố commit thì có thể nhận `UnexpectedRollbackException` và toàn transaction bị rollback. Việc một phương thức con "đã xong và không còn exception tại dòng caller" không xóa trạng thái rollback-only.

## 5. Ngoại lệ, rollback và ý nghĩa của kết quả caller nhìn thấy

Theo cấu hình mặc định của Spring `@Transactional`, `RuntimeException` và `Error` gây rollback; checked exception thường **không tự động** gây rollback. Có thể điều chỉnh bằng `rollbackFor` hoặc `noRollbackFor`. Vì vậy không thể suy ra chỉ từ việc "có/không có exception trong thân phương thức" rằng transaction đã commit hay rollback.

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importData() throws java.io.IOException {
    // Nếu IOException thoát ra, transaction cũng được đánh dấu rollback.
}
```

Đây là **mã minh họa cấu hình**, không phải chương trình độc lập. Cũng cần nhớ:

- **Bắt và nuốt exception** trong transaction có thể khiến phương thức kết thúc bình thường và Spring tiếp tục thử commit, trừ khi transaction đã bị đánh dấu rollback-only hoặc xảy ra lỗi khác. Không dùng `catch` rồi log như thể mọi thay đổi chắc chắn đã rollback.
- **Lỗi trong `afterCommit`** xảy ra **sau khi commit DB thành công**; callback đồng bộ có thể ném exception tới caller nhưng không thể đảo ngược commit vừa xảy ra. Khi xử lý lỗi, đừng thực hiện retry ghi dữ liệu một cách mù quáng chỉ vì caller nhận exception.
- **Commit của DB không bảo đảm email, HTTP call hoặc message gửi ra ngoài đã thành công.** Đó là kết quả của hệ thống khác, cần cơ chế nhất quán riêng.

## 6. Đặt tác vụ phụ ở thời điểm phù hợp

Giả sử tạo đơn hàng rồi gửi thông báo. Nếu gửi email/message ngay trước `return` trong `@Transactional`, người nhận có thể thấy đơn hàng **sau đó bị rollback**. Nếu nghiệp vụ yêu cầu chỉ thông báo về bản ghi đã commit, có thể gắn listener vào giai đoạn commit:

```java
public record OrderCreated(long orderId) {}

@Component
class OrderNotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        // Chỉ chạy sau commit thành công của transaction gắn với event.
        // Gửi tín hiệu cho kênh thông báo / xử lý tiếp.
    }
}
```

Đây là **minh họa thiết kế**; cần import `@Component`, `@TransactionalEventListener`, `TransactionPhase`, và phát event trong transaction. `AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`; `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION` có mục đích khác. Nếu không có transaction, listener mặc định không được gọi trừ khi cấu hình `fallbackExecution = true`.

Có thể dùng `TransactionSynchronization.afterCommit()` khi cần callback gắn trực tiếp với transaction hiện tại. Nếu callback sau commit cần **ghi dữ liệu mới bằng transaction riêng**, dùng một service được gọi qua proxy với `Propagation.REQUIRES_NEW`; tài nguyên transaction cũ đôi khi vẫn còn gắn với thread trong giai đoạn callback, nên không nên mặc định việc ghi mới sẽ được commit.

**Giới hạn độ tin cậy:** `AFTER_COMMIT` callback không tự biến việc gửi message/email thành giao dịch nguyên tử với DB. Nếu tiến trình chết ngay sau DB commit nhưng trước khi gửi thông báo, tín hiệu có thể bị mất. Khi cần bảo đảm giao nhận, dùng **transactional outbox**: ghi bản ghi nghiệp vụ và bản ghi outbox trong cùng transaction; worker/relay gửi sau commit với retry và xử lý trùng lặp.

## 7. Khi quan sát và kiểm thử, xác minh đúng mốc

1. **Phân biệt vị trí log.** Log trong target trước `return` chỉ xác nhận thân phương thức chạy tới đó. Log trong `afterCommit` hoặc callback transaction thực sự xác nhận commit của transaction tương ứng. Log ngoài lời gọi proxy chỉ có ý nghĩa commit khi proxy sở hữu transaction vật lý.
2. **Kiểm tra bằng một transaction/connection khác sau khi ranh giới ngoài hoàn tất.** Đừng dùng cùng persistence context hay cùng transaction đang mở rồi kết luận dữ liệu đã commit chỉ vì có thể đọc lại dữ liệu vừa ghi.
3. **Test lỗi xảy ra lúc commit.** Kiểm tra optimistic locking, unique constraint, rollback-only và failure từ callback; assert DB cuối cùng, không chỉ assert dòng log trong method.
4. **Chú ý `@Transactional` trên test.** Spring TestContext thường rollback transaction của test sau test; `save()` chạy xong trong test không chứng minh transaction đã commit. Có thể dùng `TestTransaction` để chủ động kết thúc một transaction test khi cần xác minh commit.
5. **Xác nhận proxy thực sự được áp dụng.** Trong proxy mode, lời gọi `this.innerMethod()` trong cùng object thường **không được interceptor chặn**; gắn `@Transactional` lên `innerMethod` không tự tạo transaction mới. Gọi qua Spring bean/proxy hoặc thiết kế lại ranh giới service.
6. **Nhận diện lập trình bất đồng bộ/reactive.** `@Async` chạy ở thread khác và reactive transaction dùng Reactor context; mốc hoàn tất của công việc hoặc stream không nhất thiết là lúc phương thức Java trả về publisher/future. Không áp dụng máy móc sơ đồ đồng bộ ở trên cho mọi loại API.

## 8. Tình huống tự kiểm tra

**Tình huống A.** Service `@Transactional` gọi `repository.save`, in "DONE" rồi `return`. Sau đó DB báo lỗi unique constraint lúc flush/commit. Bản ghi có được coi đã commit vì có "DONE" không?

**Đáp án:** Không. "DONE" được in trước khi transaction manager hoàn tất; caller có thể nhận exception, transaction rollback.

**Tình huống B.** `outer()` đang có `@Transactional`; `inner()` dùng `REQUIRED` trả về bình thường. `outer()` tiếp tục ném `RuntimeException`. Dữ liệu từ `inner()` có chắc tồn tại không?

**Đáp án:** Không. `inner()` tham gia transaction vật lý của `outer()`; outer rollback thì thay đổi của inner cũng bị rollback.

**Tình huống C.** Callback `afterCommit` in "COMMITTED", rồi một tác vụ gửi email ném exception. Có thể kết luận DB rollback không?

**Đáp án:** Không. Commit DB đã thành công trước khi `afterCommit` chạy. Phải xử lý thất bại của email riêng, tránh ghi lặp thiếu idempotency.

**Tình huống D.** `entityManager.flush()` đã hoàn tất trước `return`. Transaction ngoài vẫn mở. Một client khác có được bảo đảm nhìn thấy dữ liệu mới không?

**Đáp án:** Không. Flush không phải commit; khả năng nhìn thấy dữ liệu còn tùy mức isolation, trạng thái transaction và cơ chế DB.

## Ghi nhớ

- **Kết thúc thân phương thức ≠ commit thành công.**
- **Commit thuộc ranh giới transaction vật lý**, không gắn máy móc với mọi `return` của mọi phương thức được annotate.
- Cần phân biệt `target return`, `proxy return` và **transaction ngoài**; chỉ dựa trên log trong method, `save` hoặc `flush` là chưa đủ.
- Khi cần hành động sau commit, dùng hook/transaction event phù hợp; khi cần giao nhận bền vững xuyên hệ thống, cân nhắc outbox.

## Tài liệu tham khảo chính thức

- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- Spring Framework — [`TransactionSynchronization` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- Spring Boot — [Java và Maven requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
