# Mô hình mệnh lệnh và mô hình reactive trong Spring Transaction Management

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) phân biệt luồng xử lý mệnh lệnh (imperative) và reactive; (2) giải thích Spring gắn trạng thái transaction vào luồng thực thi như thế nào; (3) chọn đúng `PlatformTransactionManager` hoặc `ReactiveTransactionManager`; (4) áp dụng `@Transactional` hoặc API programmatic đúng chỗ; (5) nhận diện lỗi thường gặp khi trộn JDBC/JPA với R2DBC/Reactor.

## 1. Hai mô hình cùng giải quyết bài toán gì?

Transaction gom các thao tác dữ liệu thành một đơn vị công việc: hoặc toàn bộ thay đổi hợp lệ được commit, hoặc những thay đổi chưa commit bị rollback khi thất bại. Chẳng hạn, chuyển 20 đơn vị từ tài khoản A sang B phải đi cùng hai lệnh: trừ A và cộng B. Nếu cộng B thất bại, việc trừ A phải được hoàn tác. Những bảo đảm thực tế (atomicity, isolation, durability, v.v.) còn phụ thuộc database, driver, mức isolation và cấu hình.

Khác biệt giữa *imperative* và *reactive* chủ yếu nằm ở **cách biểu diễn công việc, thời điểm thực thi và cách truyền ngữ cảnh transaction**. Cả hai đều có thể dùng `@Transactional` của Spring, nhưng chúng không dùng cùng một cơ chế quản lý resource.

- **Imperative:** viết các câu lệnh theo thứ tự; lời gọi phương thức thường thực hiện công việc ngay và trả kết quả hoặc ném ngoại lệ. Với JDBC/JPA, tương tác cơ sở dữ liệu thường là blocking.
- **Reactive:** xây dựng một chuỗi `Publisher` (thường là Reactor `Mono<T>` hoặc `Flux<T>`). Chuỗi thường chỉ thực thi khi có subscriber; việc hoàn tất, lỗi và hủy được truyền bằng tín hiệu. Với R2DBC, I/O database có thể không blocking.

“Reactive” không tự động đồng nghĩa với “nhanh hơn” hay “database luôn hỗ trợ transaction”. Nó có lợi khi toàn bộ chuỗi I/O và thư viện hỗ trợ cách xử lý non-blocking, nhất là khi có nhiều yêu cầu đồng thời.

## 2. So sánh trực diện

| Khía cạnh | Imperative | Reactive |
|---|---|---|
| Kiểu hàm service điển hình | `void`, `T`, `List<T>` | `Mono<T>`, `Mono<Void>`, `Flux<T>` |
| Thời điểm công việc DB diễn ra | Khi chạy vào câu lệnh DB trong lời gọi phương thức | Khi publisher DB được subscribe (đối với publisher cold thông thường) |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Cách giữ trạng thái transaction | Chủ yếu `ThreadLocal` của thread thực thi | Reactor `Context` gắn với subscription |
| Công nghệ dữ liệu phổ biến | JDBC, JdbcTemplate, JPA/Hibernate | R2DBC, Spring `DatabaseClient`, reactive driver được hỗ trợ |
| API programmatic thuận tiện | `TransactionTemplate` | `TransactionalOperator` |
| Tín hiệu thành công/thất bại | Trả về / ném exception | `onComplete` / `onError` (và `cancel`) |
| Truyền ngữ cảnh | Giữ trong transaction-bound thread; đổi sang thread mới không tự mang theo | Giữ trong cùng reactive pipeline và Reactor Context, ngay cả khi operator hợp lệ chuyển thread |
| Ranh giới quan trọng | Lời gọi đi qua Spring proxy và thân phương thức | Lời gọi đi qua proxy, publisher được trả về và subscription của pipeline |

**Điểm nhớ:** chọn transaction manager theo **kiểu truy cập dữ liệu và kiểu thực thi**, không chỉ vì controller đang dùng Spring MVC hay WebFlux. Một endpoint WebFlux gọi dịch vụ JDBC vẫn đang dùng công nghệ blocking; chỉ đổi chữ ký trả về thành `Mono` không biến JDBC thành R2DBC.

## 3. Vòng đời transaction của mô hình mệnh lệnh

Khi một bean Spring gọi phương thức được proxy hỗ trợ `@Transactional`:

```text
Caller
  → Spring transactional proxy
  → PlatformTransactionManager lấy/tạo transaction
  → chạy thân service; các thao tác JDBC/JPA tham gia transaction
  → trả về bình thường: commit
  → ném ngoại lệ cần rollback: rollback
  → caller nhận kết quả hoặc ngoại lệ
```

Trong cấu hình JDBC phổ biến, Spring ràng buộc connection và trạng thái transaction vào thread hiện tại. `JdbcTemplate` hoặc repository được Spring quản lý sẽ lấy connection phù hợp để cùng tham gia. `@Transactional` mặc định có propagation `REQUIRED`: nếu có transaction phù hợp thì tham gia, chưa có thì tạo mới.

### Ví dụ Java 17+: chuyển số dư bằng JdbcTemplate

Giả sử có bảng SQL (kiểu `DECIMAL` và cách tạo bảng cần tương thích DB đang dùng):

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL
);

INSERT INTO accounts(id, balance)
VALUES (1, 100.00), (2, 50.00);
```

File `JdbcTransferService.java` (một Spring bean; cần application context, JDBC driver, `DataSource` và transaction manager, **không phải chương trình Java chạy độc lập**):

```java
import java.math.BigDecimal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcTransferService {
    private final JdbcTemplate jdbc;

    public JdbcTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional("jdbcTx")
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Sender missing or insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Recipient missing");
        }
    }
}
```

**Diễn giải:** gọi `transfer(1, 2, new BigDecimal("20.00"))` trên Spring proxy sẽ thực thi hai lệnh UPDATE trong cùng transaction. Nếu thành công, số dư trở thành 80.00 và 70.00; nếu người nhận không tồn tại hoặc lệnh thứ hai báo lỗi, unchecked exception khiến transaction rollback cả lệnh trừ trước đó. Các kết quả này giả định cấu hình đúng transaction manager cùng `DataSource` và không có thay đổi đồng thời khác. Kiểm tra số dòng cập nhật giúp phát hiện nghiệp vụ lỗi trước khi commit.

## 4. Vòng đời transaction của mô hình reactive

Với `ReactiveTransactionManager`, Spring không thể dùng `ThreadLocal` làm “định danh” cho toàn bộ công việc vì các tín hiệu có thể đi qua nhiều thread. Thay vào đó, trạng thái transaction và connection được gắn với **Reactor Context của subscription**. Các bước khái quát:

```text
Caller → Spring transactional proxy → nhận Mono/Flux đã được bọc
                                        (chưa chạy SQL)
Subscriber subscribe
  → ReactiveTransactionManager mở/tham gia transaction
  → đưa trạng thái/connection vào Reactor Context
  → publisher DB thực thi tuần tự theo operator
  → onComplete: commit
  → onError: rollback (theo rollback rules)
  → cancel: rollback đối với reactive transaction
```

Ngữ cảnh đi theo **reactive chain**. Việc dùng các operator Reactor bình thường, kể cả chuyển scheduler, không tự làm mất transaction context; nhưng tạo một subscription rời hoặc gọi một API không nhận biết ngữ cảnh này có thể khiến thao tác chạy ngoài transaction dự định.

### Ví dụ Java 17+: cùng nghiệp vụ bằng R2DBC

File `R2dbcTransferService.java` (Spring bean; cần Reactor, `spring-r2dbc`, R2DBC driver/`ConnectionFactory` và `ReactiveTransactionManager` tương ứng; **không phải chương trình Java chạy độc lập**):

```java
import java.math.BigDecimal;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import reactor.core.publisher.Mono;

@Service
public class R2dbcTransferService {
    private final DatabaseClient db;

    public R2dbcTransferService(DatabaseClient db) {
        this.db = db;
    }

    @Transactional("r2dbcTx")
    public Mono<Void> transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            return Mono.error(new IllegalArgumentException("Invalid transfer"));
        }

        Mono<Long> debit = db.sql(
                "UPDATE accounts SET balance = balance - :amount " +
                "WHERE id = :id AND balance >= :amount")
            .bind("amount", amount)
            .bind("id", fromId)
            .fetch()
            .rowsUpdated();

        Mono<Long> credit = db.sql(
                "UPDATE accounts SET balance = balance + :amount WHERE id = :id")
            .bind("amount", amount)
            .bind("id", toId)
            .fetch()
            .rowsUpdated();

        return debit.flatMap(changed -> {
            if (changed != 1L) {
                return Mono.<Void>error(
                    new IllegalStateException("Sender missing or insufficient funds"));
            }
            return credit.flatMap(updated -> {
                if (updated != 1L) {
                    return Mono.<Void>error(
                        new IllegalStateException("Recipient missing"));
                }
                return Mono.<Void>empty();
            });
        });
    }
}
```

- `db.sql(...).fetch().rowsUpdated()` tạo publisher chứa thao tác SQL; hai UPDATE không thực thi chỉ vì service đã trả về `Mono<Void>`.
- `flatMap` bảo đảm chỉ chạy phần cộng tiền sau khi phần trừ đã xác nhận đúng một dòng. Trả `Mono.error(...)` làm lỗi đi trong cùng pipeline để Spring rollback; trả `Mono.empty()` sau khi thành công khiến pipeline hoàn tất và commit.
- Nếu chẳng ai subscribe, công việc chưa xảy ra. Trong ứng dụng WebFlux, framework thường subscribe khi xử lý phản hồi; **không gọi `subscribe()` thủ công trong service**.
- Số dư dự kiến giống ví dụ JDBC khi chạy với cùng dữ liệu đầu vào và không có thay đổi đồng thời. Ví dụ này không đưa ra stdout vì nó chạy trong Spring/database, không có `main`.

### Cấu hình transaction manager phù hợp

Trong ứng dụng có cả JDBC và R2DBC, có thể phân biệt rõ hai manager (file `TxConfig.java`; cần các bean `DataSource`, `ConnectionFactory` và dependencies tương ứng):

```java
import javax.sql.DataSource;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class TxConfig {
    @Bean("jdbcTx")
    PlatformTransactionManager jdbcTx(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean("r2dbcTx")
    ReactiveTransactionManager r2dbcTx(ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

Tên `jdbcTx` và `r2dbcTx` khớp với `@Transactional("...")` ở hai service. Nếu ứng dụng chỉ có một manager phù hợp, thường có thể dùng `@Transactional` không chỉ định tên. Không giả định hai manager tự chia sẻ connection hoặc cùng một transaction: JDBC và R2DBC là hai hạ tầng quản lý độc lập.

## 5. Khai báo và programmatic: cùng mục đích, API khác nhau

**Declarative**: `@Transactional` mô tả ranh giới transaction trên phương thức Spring bean. Spring AOP/proxy đảm nhận begin/commit/rollback; rất phù hợp khi toàn bộ nghiệp vụ nằm gọn trong một service method.

**Programmatic**: dùng khi muốn chỉ rõ đoạn pipeline/đoạn lệnh nào nằm trong transaction, hoặc đặt thuộc tính transaction động. API Spring khuyến nghị:

| Luồng | API | Hình thức |
|---|---|---|
| Imperative | `TransactionTemplate` với `PlatformTransactionManager` | `template.execute(status -> { ... })` |
| Reactive | `TransactionalOperator` với `ReactiveTransactionManager` | `pipeline.as(operator::transactional)` hoặc `operator.transactional(pipeline)` |

Ví dụ reactive, giả sử `debit(...)` và `credit(...)` đã là các phương thức trả về `Mono<Void>`, dùng đúng R2DBC client:

```java
// Đoạn mã bên trong một Spring component đã có reactiveTx,
// debit(...) và credit(...); không phải file độc lập.
TransactionalOperator operator = TransactionalOperator.create(reactiveTx);

Mono<Void> work = debit(fromId, amount)
    .then(credit(toId, amount));

return operator.transactional(work);
```

Chỉ các thao tác được **chaining trong `work`** mới nằm trong transaction này. Nếu có một publisher khác thực hiện bằng `subscribe()` riêng, publisher đó có subscription/context riêng. Không thể mặc nhiên coi nó là bước thứ ba trong cùng transaction.

**Thứ tự operator có ý nghĩa.** Chẳng hạn, `work.onErrorResume(ex -> Mono.empty())` đặt *trước* `operator.transactional(...)` biến tín hiệu lỗi thành hoàn tất bình thường, nên các cập nhật trước lỗi có thể được commit. Nếu muốn rollback, hãy để lỗi truyền ra khỏi phạm vi transaction, hoặc chủ động đánh dấu rollback-only bằng API thích hợp.

## 6. Những điểm giống nhau về quy tắc transaction

- Mặc định `@Transactional` dùng `Propagation.REQUIRED`, isolation mặc định của hệ thống dữ liệu và rollback đối với `RuntimeException`/`Error`; checked exception không mặc nhiên rollback (có thể cấu hình `rollbackFor` hoặc chính sách mặc định của ứng dụng).
- `readOnly = true` là gợi ý cho hạ tầng, không phải cơ chế bảo vệ tuyệt đối ngăn mọi lệnh ghi; mức hỗ trợ tùy driver và database.
- Propagation, isolation, timeout và savepoint **không có mức hỗ trợ giống hệt nhau** ở mọi manager/driver. Đặc biệt đừng giả định `NESTED` luôn khả dụng với R2DBC chỉ vì JDBC có thể dùng savepoint.
- Một transaction database không tự bao gồm email, lời gọi HTTP hay broker khác. Khi phải đồng bộ các side effect, cân nhắc outbox hoặc thiết kế eventual consistency thay vì mặc nhiên xem nhiều resource là một giao dịch nguyên tử.

## 7. Những bẫy cần nhận diện

### 7.1. Gắn `@Transactional` lên một phương thức rồi gọi nội bộ cùng class

Ở chế độ proxy mặc định, `this.innerMethod()` không đi qua proxy, nên `@Transactional` trên `innerMethod` không được interceptor áp dụng cho lời gọi này. Gọi từ bean khác qua Spring proxy, hoặc đặt ranh giới transaction ở phương thức được gọi từ ngoài.

### 7.2. Đổi JDBC/JPA thành `Mono.just(...)` rồi cho rằng đã reactive

```java
// Sai về mặt lazy execution: jdbc.update(...) đã chạy trước khi tạo Mono.
Mono<Integer> changed = Mono.just(jdbc.update("DELETE FROM temp_rows"));
```

`Mono.defer(...)` có thể trì hoãn việc gọi code, nhưng không biến JDBC blocking thành non-blocking và không làm JDBC tự tham gia R2DBC transaction. Hãy dùng manager và driver phù hợp; nếu bắt buộc dùng JDBC, bố trí thread/scheduler cho blocking workload và xem transaction JDBC là ranh giới riêng.

### 7.3. Tự `subscribe()` hoặc `block()` bên trong service reactive

Tự subscribe tạo luồng thực thi tách khỏi publisher trả về, khiến thao tác phụ có thể chạy sau commit/rollback hoặc ngoài Reactor Context mong muốn. Gọi `block()` trên event-loop cũng có thể gây lỗi và làm nghẽn thread phục vụ nhiều request. Trong service reactive, hãy **trả về** chuỗi `Mono/Flux` đã ghép đầy đủ; giao việc subscribe cho layer ngoài cùng.

### 7.4. Nuốt lỗi trước ranh giới transaction

Nếu `onErrorResume` đổi lỗi thành một kết quả thành công *bên trong* transactional pipeline, manager có thể nhìn thấy `onComplete` và commit. Với imperative, việc bắt exception rồi không ném lại cũng có rủi ro tương tự. Cần phân biệt “đã xử lý lỗi nghiệp vụ” với “phải rollback thay đổi DB”.

### 7.5. Bỏ qua cancellation của reactive stream

Một subscriber có thể `cancel` (ví dụ một số trường hợp `take`, `next`, `timeout`). Từ Spring Framework 5.3, cancellation của reactive transaction dẫn đến **rollback**. Khi muốn transaction commit toàn bộ xử lý của `Flux`, cần thiết kế để publisher được consume đến terminal completion, tránh operator cắt sớm ngoài ý muốn.

### 7.6. Trộn resource, ngữ cảnh hoặc transaction manager

Trong reactive transaction, thao tác dữ liệu phải dùng driver/API tham gia được cùng Reactor Context, ví dụ Spring `DatabaseClient` với `R2dbcTransactionManager`. Tự tạo một R2DBC connection mới bằng API thô không bảo đảm nó dùng connection đã được transaction bind. Ngược lại, transaction `PlatformTransactionManager` dựa vào thread-bound state và không tự đi theo thread mới. Hai loại manager không phối hợp thành transaction phân tán chỉ vì cùng đặt `@Transactional`.

## 8. Kiểm chứng bằng tích hợp và lựa chọn mô hình

Với dữ liệu khởi tạo `(id=1, balance=100.00)` và `(id=2, balance=50.00)`, nên kiểm thử tối thiểu:

1. **Success:** chuyển 20.00, đợi service hoàn tất, kiểm tra bằng truy vấn mới rằng cả hai tài khoản lần lượt có 80.00 và 70.00.
2. **Failure/rollback:** khởi tạo lại dữ liệu; gọi chuyển tới một `toId` không tồn tại. Xác nhận nhận exception (imperative) hoặc `onError` (reactive), rồi kiểm tra lại số dư vẫn 100.00 và 50.00.
3. **Lazy execution:** với reactive, chỉ tạo `Mono` nhưng chưa subscribe thì chưa có thay đổi DB. Khi kiểm thử reactive, có thể dùng `StepVerifier.create(service.transfer(...)).verifyComplete()` hoặc `verifyError(...)` với dependency `reactor-test`.
4. **Ranh giới/context:** nếu có nhiều manager hoặc nhiều service, thử một ca lỗi sau thao tác thứ nhất để xác nhận cả hai thao tác thực sự thuộc **cùng** transaction.

| Tình huống | Hướng lựa chọn |
|---|---|
| Ứng dụng đang dùng JPA/Hibernate hoặc JDBC, nghiệp vụ đồng bộ | Imperative + `PlatformTransactionManager` |
| Toàn chuỗi request → service → database dùng non-blocking R2DBC, cần xử lý nhiều kết nối đồng thời | Reactive + `ReactiveTransactionManager` |
| Ứng dụng hỗn hợp JDBC và R2DBC | Tách ranh giới, đặt tên manager rõ ràng, kiểm thử rollback từng bên; đừng kỳ vọng một local transaction bao trùm cả hai |
| Cần kiểm soát một đoạn nhỏ trong luồng xử lý | `TransactionTemplate` (imperative) hoặc `TransactionalOperator` (reactive) |

**Tự kiểm tra kiến thức:** (a) vì sao `ThreadLocal` không đủ cho reactive pipeline? (b) chuyện gì xảy ra nếu `Mono` trả về nhưng không có subscriber? (c) vì sao hai lệnh UPDATE nằm trong hai lời gọi `subscribe()` riêng có thể không cùng transaction? (d) gọi `this.save()` với `@Transactional` trên `save` có được Spring proxy chặn không?

## Tài liệu tham khảo

- Spring Framework — Declarative transaction implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Programmatic transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — Data access with R2DBC: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Blog — Reactive Transactions with Spring: https://spring.io/blog/2019/05/16/reactive-transactions-with-spring/
