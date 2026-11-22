# Kiểm thử rollback mà không giả định cơ chế giao dịch của JDBC test

Khi kiểm thử Spring Data Relational R2DBC, không nên mặc định transaction của test hoạt động giống transaction trong Spring JDBC hoặc JPA. JDBC test truyền thống thường dùng `PlatformTransactionManager` và transaction gắn với thread hiện tại. R2DBC dùng `ReactiveTransactionManager`; transaction được truyền qua Reactor Context và chỉ bao phủ các thao tác reactive thực sự được subscribe trong context đó.

Vì vậy, một test method có `@Transactional` hoặc `@Rollback` không tự chứng minh rằng publisher R2DBC được rollback. Cần xác định transaction manager, `ConnectionFactory` và ranh giới subscribe thực tế. Cách kiểm thử tường minh là dùng `TransactionalOperator` bao quanh toàn bộ publisher ghi dữ liệu, cố ý phát lỗi để kích hoạt rollback, sau đó truy vấn lại bằng một subscription mới ở ngoài transaction để xác minh dữ liệu không được commit.

## 1. Vì sao không thể bê nguyên cách kiểm thử JDBC sang R2DBC?

Trong mô hình JDBC imperative, một test có thể chạy trong transaction do Spring Test quản lý. Connection thường được gắn với thread thông qua cơ chế transaction synchronization. Khi test kết thúc, listener rollback transaction để dữ liệu không tồn tại sau test.

R2DBC là reactive và không dựa vào một thread cố định. Một transaction được quản lý bằng `ReactiveTransactionManager`, còn trạng thái transaction được truyền trong Reactor Context. Các thao tác repository/`DatabaseClient` phải nằm trong reactive chain được transaction bao phủ.

| Khía cạnh | JDBC test truyền thống | R2DBC reactive test |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager`, thường là `R2dbcTransactionManager` |
| Context | Thường gắn với thread hiện tại | Reactor Context |
| API thao tác | JDBC call đồng bộ | `Mono`/`Flux` và subscription |
| Ranh giới hoàn tất | Test method/transaction listener | Publisher hoàn tất, lỗi hoặc bị hủy |
| Cách rollback | Test framework có thể rollback transaction test-managed | Reactive transaction manager rollback theo tín hiệu reactive trong transaction boundary |
| Cách kiểm chứng | Đọc lại sau khi test transaction kết thúc | Subscribe một query mới sau khi `TransactionalOperator` đã kết thúc |

Điểm cốt lõi là `@Transactional` trên test method không tự biến mọi publisher được tạo trong method thành một phần của reactive transaction. Publisher có thể chỉ được subscribe sau đó bởi `StepVerifier`, và transaction của test kiểu JDBC không tự truyền sang subscription reactive đó.

## 2. `@Transactional` và `@Rollback` trong test cần được hiểu đúng

Trong các test JDBC/JPA, mẫu quen thuộc thường là:

```java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Test
    void createsCustomer() {
        // JDBC/JPA thao tác đồng bộ trong test-managed transaction.
        // Spring Test rollback transaction khi test kết thúc.
    }
}
```

Không nên sao chép mẫu này sang R2DBC rồi cho rằng nó tự rollback publisher:

```java
@SpringBootTest
@Transactional
class CustomerR2dbcTest {

    @Test
    void createsCustomer() {
        StepVerifier.create(customerRepository.save(customer))
                .expectNextCount(1)
                .verifyComplete();
    }
}
```

Đoạn code thứ hai không tự chứng minh test-managed transaction đã bao publisher R2DBC. Việc hỗ trợ transaction cho test phụ thuộc Spring Framework/Spring Boot version và cách test infrastructure được cấu hình. Không suy ra behavior từ `@Transactional` hoặc `@Rollback` của JDBC.

Nếu phiên bản và test slice của dự án có hỗ trợ reactive test transaction, hãy kiểm tra tài liệu đúng phiên bản và xác minh bằng một test rollback thực tế. Khi muốn ranh giới rõ ràng, độc lập với giả định về test listener, dùng `TransactionalOperator` trực tiếp trong test.

`@DataR2dbcTest` hữu ích để cấu hình repository và hạ tầng R2DBC cho slice test, nhưng vẫn cần hiểu transaction semantics mà phiên bản cụ thể cung cấp. Annotation test slice không thay thế việc xác minh connection factory và reactive transaction boundary.

## 3. Reactive transaction được gắn với Reactor Context

`R2dbcTransactionManager` quản lý một `ConnectionFactory`. Khi `TransactionalOperator` bắt đầu transaction, manager lấy connection, mở transaction và gắn resource vào reactive context. Các thao tác Spring R2DBC tương thích trong cùng chain có thể dùng connection đang được quản lý.

Ví dụ cấu hình:

```java
@TestConfiguration
class R2dbcTestTransactionConfiguration {

    @Bean
    R2dbcTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            R2dbcTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

Trong ứng dụng đã có transaction manager, có thể inject bean hiện tại thay vì khai báo lại. Điều quan trọng là operator phải dùng cùng `ConnectionFactory` với repository, `R2dbcEntityTemplate` hoặc `DatabaseClient` đang được test.

Không tạo một `TransactionalOperator` với factory A rồi mong repository dùng factory B tự tham gia transaction. Cũng không lấy connection mới trực tiếp từ factory ở giữa transaction nếu thao tác đó bỏ qua cơ chế connection lookup transaction-aware của Spring.

## 4. Kiểm thử rollback tường minh bằng `TransactionalOperator`

Một test rollback đáng tin cậy cần có bốn bước:

1. Tạo publisher ghi dữ liệu.
2. Nối một lỗi có chủ đích sau khi thao tác ghi hoàn tất.
3. Bọc toàn bộ publisher bằng `TransactionalOperator`.
4. Đợi publisher kết thúc bằng lỗi, sau đó truy vấn lại ở ngoài transaction để xác minh dữ liệu không tồn tại.

Ví dụ với `DatabaseClient`:

```java
class ForcedRollbackException extends RuntimeException {
}

@SpringBootTest
class R2dbcRollbackIntegrationTest {

    @Autowired
    DatabaseClient databaseClient;

    @Autowired
    TransactionalOperator transactionalOperator;

    @Test
    void rollsBackInsertWhenPublisherFails() {
        String email = "rollback-" + UUID.randomUUID() + "@example.test";

        Mono<Void> writeThenFail = databaseClient.sql("""
                INSERT INTO customer (email, display_name)
                VALUES (:email, 'Rollback candidate')
                """)
                .bind("email", email)
                .fetch()
                .rowsUpdated()
                .then(Mono.error(new ForcedRollbackException()));

        StepVerifier.create(transactionalOperator.transactional(writeThenFail))
                .expectError(ForcedRollbackException.class)
                .verify();

        Mono<Long> count = databaseClient.sql("""
                SELECT COUNT(*) AS total
                FROM customer
                WHERE email = :email
                """)
                .bind("email", email)
                .map((row, metadata) -> row.get("total", Long.class))
                .one();

        StepVerifier.create(count)
                .expectNext(0L)
                .verifyComplete();
    }
}
```

Test thực hiện insert trong transaction, sau đó phát `ForcedRollbackException`. `TransactionalOperator` thấy publisher kết thúc bằng `onError` nên rollback transaction. Query `COUNT` được subscribe sau khi `verify()` đã đợi transaction kết thúc; query này chạy ngoài transaction vừa rollback và xác minh không có hàng đã commit.

Trong dự án thực tế, bảng và cột phải khớp schema test. Kiểu trả về của `COUNT(*)` cần tương thích với driver/database; nếu driver trả kiểu khác, dùng kiểu mapping phù hợp. Giá trị email ngẫu nhiên giúp test độc lập với dữ liệu seed và tránh va chạm với test chạy song song.

## 5. Tại sao phải kiểm tra bằng subscription mới?

Nếu query xác minh được đặt bên trong cùng transaction, nó có thể nhìn thấy thay đổi chưa commit của transaction đó. Khi đó test không chứng minh rollback sau commit boundary.

Ví dụ ý tưởng không phù hợp:

```java
Mono<Boolean> work = databaseClient.sql("INSERT INTO customer ...")
        .fetch()
        .rowsUpdated()
        .then(databaseClient.sql("SELECT ...")
                .map((row, metadata) -> row.get("exists", Boolean.class))
                .one());
```

Query đọc ở đây chạy trong cùng chain/transaction nếu toàn bộ publisher được bọc bởi cùng operator. Nó có thể thấy dữ liệu vừa insert trước khi transaction rollback.

Để xác minh rollback, chờ `transactionalOperator.transactional(work)` phát terminal signal, rồi mới subscribe một query mới. Cách này kiểm tra trạng thái đã được database quan sát sau khi transaction kết thúc.

Nếu môi trường test có một transaction ngoài khác, ví dụ do test framework tự mở, cần xác định query xác minh đang dùng connection nào và transaction nào. Tránh để một transaction ngoài che khuất kết quả rollback của transaction bên trong.

## 6. Phải để lỗi thoát khỏi transaction boundary

Reactive transaction manager quyết định commit hay rollback dựa trên terminal signal của publisher được bọc. Nếu publisher hoàn tất bình thường, transaction thường commit; nếu publisher phát lỗi, transaction rollback theo quy tắc rollback.

Đúng: phục hồi lỗi ở ngoài `TransactionalOperator`:

```java
Mono<Void> transactionalWork = transactionalOperator.transactional(
        repository.save(entity)
                .then(Mono.error(new ForcedRollbackException())));

Mono<Void> handledForTest = transactionalWork
        .onErrorResume(ForcedRollbackException.class, error -> Mono.empty());
```

Lỗi đi qua transaction boundary trước, khiến transaction rollback. Sau đó `onErrorResume` bên ngoài mới biến lỗi thành hoàn tất rỗng nếu test cần kiểm tra tiếp.

Sai nếu mục tiêu là rollback: nuốt lỗi bên trong transaction:

```java
Mono<Void> wrong = transactionalOperator.transactional(
        repository.save(entity)
                .then(Mono.error(new ForcedRollbackException()))
                .onErrorResume(error -> Mono.empty()));
```

Ở đây lỗi được chuyển thành `onComplete` trước khi tới transaction operator. Transaction manager có thể xem publisher đã hoàn tất thành công và commit thay đổi. Test có thể tưởng đã tạo lỗi nhưng thực tế lại xác minh sai hành vi.

Khi cần bắt lỗi để assert, đặt assertion sau khi transaction operator đã phát lỗi. Đừng nuốt lỗi trong chain bên trong transaction trừ khi chủ động đánh dấu rollback-only bằng API transaction phù hợp.

## 7. Kiểm thử rollback khi service dùng `@Transactional`

Trong ứng dụng, service có thể dùng annotation:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<Customer> createThenFail(Customer customer) {
        return repository.save(customer)
                .flatMap(saved -> Mono.error(
                        new ForcedRollbackException()));
    }
}
```

Test nên gọi service qua Spring bean proxy và subscribe publisher:

```java
StepVerifier.create(customerService.createThenFail(customer))
        .expectError(ForcedRollbackException.class)
        .verify();
```

Sau đó truy vấn lại dữ liệu bằng một publisher mới để xác minh không có hàng đã commit. Không gọi method qua `new CustomerService(...)` trong test nếu muốn kiểm tra transaction interceptor; self-invocation hoặc gọi object không qua proxy có thể bỏ qua `@Transactional`.

Với reactive method, transaction interceptor bao publisher được trả về và gắn transaction vào subscription. Method phải trả `Mono`/`Flux` để transaction reactive hoạt động đúng. Nếu method gọi `subscribe()` nội bộ rồi trả `Mono.empty()`, công việc ghi đã tách khỏi publisher mà interceptor quản lý.

## 8. Không trộn `PlatformTransactionManager` với `ReactiveTransactionManager`

Ứng dụng có thể đồng thời dùng JDBC và R2DBC. Khi đó có thể tồn tại:

- `DataSourceTransactionManager` hoặc `JdbcTransactionManager` cho JDBC.
- `R2dbcTransactionManager` cho R2DBC.

Đây là hai transaction manager khác nhau, quản lý hai loại resource khác nhau. `@Transactional` cần chọn đúng manager khi có nhiều bean:

```java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Customer> saveReactive(Customer customer) {
    return customerRepository.save(customer);
}
```

Một transaction JDBC không tự enlist connection R2DBC. Cũng không thể giả định rollback JDBC test sẽ rollback thao tác được thực hiện bằng R2DBC. Nếu một test dùng cả hai stack, hãy tách ranh giới hoặc thiết kế cơ chế điều phối phù hợp; không coi chúng là cùng một connection chỉ vì trỏ tới cùng database URL.

## 9. `@Sql` và tiện ích test JDBC không tự động là R2DBC

Các tiện ích như `@Sql`, `JdbcTestUtils`, `TestTransaction` và nhiều helper trong Spring Test JDBC làm việc với `DataSource`/JDBC. Chúng không tự động chuyển thành thao tác reactive chỉ vì ứng dụng có `ConnectionFactory`.

Nếu test chỉ có R2DBC:

- Dùng `DatabaseClient`, repository hoặc `R2dbcEntityTemplate` để chuẩn bị và dọn dữ liệu.
- Dùng SQL initialization hoặc migration fixture được cấu hình cho môi trường test.
- Dùng `TransactionalOperator` để kiểm soát transaction reactive.
- Dùng `StepVerifier` hoặc cơ chế subscribe trong test để đợi thao tác hoàn tất.

Nếu ứng dụng có cả JDBC `DataSource` và R2DBC `ConnectionFactory`, `@Sql` có thể chạy qua JDBC connection trong khi test code dùng R2DBC connection. Chúng có thể dùng cùng database nhưng không nhất thiết cùng transaction. Một `@Sql` setup nằm trong JDBC test transaction không bảo đảm R2DBC repository nhìn thấy thay đổi chưa commit đó. Hãy commit fixture trước khi R2DBC đọc hoặc dùng cùng một cơ chế fixture phù hợp.

## 10. Dùng `@DataR2dbcTest` đúng phạm vi

`@DataR2dbcTest` là test slice để tập trung vào mapping và repository R2DBC. Nó thường cấu hình các thành phần như R2DBC repositories, entity mapping và `DatabaseClient` cần thiết cho bài test. Tuy nhiên, đừng suy ra mọi hành vi transaction giống `@DataJpaTest` chỉ từ tên annotation.

Hãy kiểm tra theo phiên bản Spring Boot:

- Test slice có tạo `R2dbcTransactionManager` hay không.
- Có `TransactionalOperator` hay cần tạo trong test configuration.
- Có nhiều `ConnectionFactory` hoặc nhiều transaction manager không.
- Test method có được một cơ chế reactive test transaction cụ thể bao bọc hay không.
- Query xác minh chạy trong transaction nào.

Nếu mục tiêu test là rollback, viết test rollback rõ ràng bằng `TransactionalOperator` và xác minh trạng thái sau khi transaction hoàn tất. Slice test giúp giảm phạm vi context, nhưng không thay thế lập luận về transaction boundary.

## 11. Kiểm tra `ConnectionFactory` có cùng nhau không

Rollback chỉ bao phủ các thao tác dùng connection được transaction manager quản lý. Ví dụ, nếu `TransactionalOperator` dùng factory A nhưng repository dùng factory B, test có thể phát lỗi nhưng dữ liệu ở B vẫn được commit.

Kiểm tra cấu hình:

```java
@Bean
R2dbcTransactionManager r2dbcTransactionManager(
        @Qualifier("applicationConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}

@Bean
DatabaseClient databaseClient(
        @Qualifier("applicationConnectionFactory") ConnectionFactory factory) {
    return DatabaseClient.create(factory);
}
```

Repository, template và `DatabaseClient` cần được cấu hình với factory tương ứng. Nếu có routing factory, transaction manager phải dùng routing factory mà repository sử dụng; route key phải có trước khi transaction lấy connection và giữ ổn định trong suốt transaction.

Với nhiều nguồn dữ liệu, một `R2dbcTransactionManager` chỉ quản lý một `ConnectionFactory`. Rollback của transaction A không rollback transaction B. Test cần kiểm tra từng ranh giới thay vì giả định một operator bao mọi nguồn.

## 12. Kiểm thử nhiều thao tác trong cùng transaction

Một test rollback có giá trị nên ghi ít nhất hai thay đổi trong cùng transaction, rồi phát lỗi sau khi cả hai đã hoàn tất. Sau rollback, kiểm tra cả hai đều không tồn tại.

```java
Mono<Void> writeTwoRowsThenFail =
        databaseClient.sql("""
                INSERT INTO customer (email, display_name)
                VALUES (:email, 'Customer A')
                """)
                .bind("email", emailA)
                .fetch()
                .rowsUpdated()
                .then(databaseClient.sql("""
                        INSERT INTO customer (email, display_name)
                        VALUES (:email, 'Customer B')
                        """)
                        .bind("email", emailB)
                        .fetch()
                        .rowsUpdated())
                .then(Mono.error(new ForcedRollbackException()));

StepVerifier.create(transactionalOperator.transactional(writeTwoRowsThenFail))
        .expectError(ForcedRollbackException.class)
        .verify();
```

Sau đó truy vấn từng email hoặc dùng một query count với cả hai giá trị để xác minh không có hàng nào được commit. Test này chứng minh hai thao tác cùng tham gia một transaction. Nếu một thao tác dùng factory khác, test có thể phát hiện rằng dữ liệu nguồn kia vẫn còn sau lỗi.

## 13. Kiểm thử rollback khi lỗi xảy ra ở thao tác thứ hai

Một kịch bản khác là thao tác đầu thành công nhưng thao tác sau thất bại do constraint. Transaction phải rollback cả thao tác đầu nếu cả hai cùng thuộc một transaction.

Ví dụ:

```java
Mono<Void> work = databaseClient.sql("""
        INSERT INTO customer (email, display_name)
        VALUES (:email, 'First row')
        """)
        .bind("email", uniqueEmail)
        .fetch()
        .rowsUpdated()
        .then(databaseClient.sql("""
                INSERT INTO customer (email, display_name)
                VALUES (:email, 'Duplicate row')
                """)
                .bind("email", uniqueEmail)
                .fetch()
                .rowsUpdated())
        .then();

StepVerifier.create(transactionalOperator.transactional(work))
        .expectError()
        .verify();
```

Hai lệnh dùng cùng email để kích hoạt unique constraint ở lệnh thứ hai. Sau khi lỗi truyền ra và transaction rollback, query mới phải xác nhận không có hàng với email đó. Test này kiểm tra lỗi database thực tế, khác với lỗi giả lập được phát bằng `Mono.error`.

Với một số database, lỗi constraint làm transaction ở trạng thái failed cho tới khi rollback. Đừng cố query xác minh trong cùng transaction sau lỗi; hãy để transaction manager rollback rồi thực hiện query mới.

## 14. Rollback khi publisher bị hủy

Reactive transaction có thể nhận tín hiệu cancellation khi subscriber không còn cần kết quả. Transaction manager xử lý cancellation theo chính sách rollback để tránh commit một công việc bị hủy giữa chừng. Tuy nhiên, driver và database có thể cần thời gian để hủy statement hoặc giải phóng tài nguyên.

Một test cancellation có thể dùng publisher được điều khiển để hủy sau khi một thao tác ghi đã chạy. Ví dụ khái niệm:

```java
Mono<Void> work = databaseClient.sql("""
        INSERT INTO customer (email, display_name)
        VALUES (:email, 'Cancelled write')
        """)
        .bind("email", email)
        .fetch()
        .rowsUpdated()
        .then(Mono.never());
```

`Mono.never()` giữ transaction chưa hoàn tất sau khi insert. Test có thể subscribe, đợi insert được xác nhận qua tín hiệu đồng bộ test hoặc một probe, rồi cancel subscription. Sau đó query bằng subscription mới để kiểm tra hàng không được commit.

Không dùng `Thread.sleep` để đoán thời điểm insert đã chạy. Dùng `Sinks.One`, `CountDownLatch` chỉ cho đồng bộ test ở biên cần thiết, `StepVerifier` với `thenAwait` có kiểm soát hoặc một tín hiệu xác nhận phát sau thao tác ghi. Cancellation behavior nên được kiểm thử trên driver/database thực tế nếu ứng dụng phụ thuộc vào nó.

## 15. Rollback-only và cách xử lý lỗi

Nếu một lỗi cần được xử lý bên trong transaction nhưng transaction vẫn phải rollback, không được chỉ nuốt lỗi rồi hoàn tất bình thường. Có thể dùng API đánh dấu transaction rollback-only phù hợp với reactive transaction context, hoặc để lỗi thoát khỏi boundary rồi xử lý ở ngoài.

Trong test, cách đơn giản và dễ đọc nhất thường là:

```java
Mono<Void> transactionalWork = transactionalOperator.transactional(
        performWrites()
                .then(Mono.error(new ForcedRollbackException())));

return transactionalWork.onErrorResume(error -> {
    // Xử lý/assert sau khi transaction boundary đã rollback.
    return Mono.empty();
});
```

Nếu ứng dụng cần trả một response thành công sau khi đã quyết định rollback, hãy thiết kế rõ ràng việc đánh dấu rollback-only bằng API của `ReactiveTransaction`/`TransactionalOperator` đúng phiên bản. Không dựa vào exception bị bắt ở trong chain để transaction tự hiểu phải rollback.

## 16. Kiểm thử lỗi commit khác lỗi trong thân transaction

Lỗi có thể xảy ra khi chạy statement, khi commit hoặc khi kết nối bị mất. Một test cố ý phát `Mono.error` sau khi insert chứng minh rollback do lỗi trong publisher, nhưng không mô phỏng mọi tình huống commit failure.

Khi commit thất bại hoặc kết nối mất đúng lúc commit, ứng dụng có thể không biết chắc database đã commit hay chưa. Đây là trạng thái kết quả không xác định từ góc nhìn client. Với thao tác có thể retry, dùng idempotency key/unique business key để truy vấn lại trạng thái và tránh tạo hiệu ứng lặp.

Các test quan trọng có thể gồm:

- Lỗi trước khi ghi: không có dữ liệu.
- Lỗi sau một ghi nhưng trước commit: transaction rollback.
- Vi phạm constraint ở thao tác sau: toàn bộ transaction rollback.
- Lỗi commit hoặc connection loss: xác minh trạng thái database và cách ứng dụng phục hồi.
- Retry sau kết quả không rõ: không tạo tài nguyên hoặc side effect trùng.

Không giả lập lỗi commit chỉ bằng cách ném exception trong service rồi kết luận đã kiểm thử driver commit failure. Hai tình huống nằm ở các giai đoạn khác nhau.

## 17. Thiết lập và dọn dữ liệu test bằng R2DBC

Không dùng fixture JDBC rồi giả định nó thuộc cùng transaction với R2DBC. Có thể tạo dữ liệu bằng `DatabaseClient`:

```java
Mono<Long> insertFixture(String email) {
    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, 'Fixture')
            """)
            .bind("email", email)
            .fetch()
            .rowsUpdated();
}
```

Và dọn bằng R2DBC:

```java
Mono<Long> deleteFixture(String email) {
    return databaseClient.sql("DELETE FROM customer WHERE email = :email")
            .bind("email", email)
            .fetch()
            .rowsUpdated();
}
```

Trong test, phải subscribe để thao tác thực thi:

```java
StepVerifier.create(insertFixture(email))
        .expectNext(1L)
        .verifyComplete();
```

`@BeforeEach`/`@AfterEach` của JUnit là callback đồng bộ; nếu gọi một phương thức trả `Mono` rồi bỏ qua publisher, thao tác sẽ không chạy. Dùng `StepVerifier.verify()` hoặc cơ chế chờ test phù hợp để hoàn tất fixture/cleanup trước khi test tiếp tục.

## 18. Cô lập dữ liệu giữa các test

Nếu không dựa vào test-managed rollback, cần chiến lược cô lập dữ liệu:

- Tạo ID/email/key duy nhất cho mỗi test.
- Dùng schema hoặc database riêng cho test suite nếu phù hợp.
- Dọn dữ liệu bằng R2DBC trong `@AfterEach` và đợi publisher hoàn tất.
- Dùng transaction tường minh cho mỗi kịch bản cần rollback.
- Không để test song song cùng dùng một khóa hoặc cùng xóa dữ liệu của nhau.
- Chú ý foreign key và thứ tự cleanup.

Một test rollback có thể dùng dữ liệu có khóa duy nhất, sau đó query kiểm tra row count bằng 0. Test thành công khác nên dùng fixture riêng. Cách này giúp test không phụ thuộc thứ tự chạy và tránh false positive do dữ liệu tồn tại từ lần chạy trước.

## 19. Dùng Testcontainers để xác minh behavior database thật

H2 hoặc mock không thể đại diện đầy đủ cho transaction, locking, constraint và driver của PostgreSQL/MySQL production. Nếu production dùng PostgreSQL R2DBC, integration test nên chạy với PostgreSQL tương thích, ví dụ qua Testcontainers.

Testcontainers giúp kiểm tra:

- R2DBC URL/driver thực tế.
- Transaction begin/commit/rollback.
- Unique/foreign key/check constraint.
- Kiểu dữ liệu và mapping.
- Behavior khi connection bị đóng hoặc statement bị lỗi.
- Cấu hình pool và transaction manager.

Không cần tạo container cho mọi unit test. Dùng test nhanh cho logic thuần Java và integration test có database thật cho các hành vi phụ thuộc driver/database. Cần bảo đảm container/database được khởi động trước khi Spring context tạo `ConnectionFactory` và được dọn sau khi test suite hoàn tất.

## 20. Kiểm thử transaction qua service proxy

Nếu mục tiêu là kiểm tra `@Transactional` trên service, cần gọi bean do Spring quản lý thay vì tự tạo instance. Ví dụ:

```java
@SpringBootTest
class CustomerServiceTransactionTest {

    @Autowired
    CustomerService customerService;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void serviceTransactionRollsBackOnError() {
        Customer customer = new Customer(
                null,
                "rollback-" + UUID.randomUUID() + "@example.test");

        StepVerifier.create(customerService.createThenFail(customer))
                .expectError(ForcedRollbackException.class)
                .verify();

        StepVerifier.create(customerRepository.existsByEmail(customer.getEmail()))
                .expectNext(false)
                .verifyComplete();
    }
}
```

Method `createThenFail` phải được đánh dấu `@Transactional` với reactive transaction manager đúng và trả publisher. Query `existsByEmail` chạy sau khi transaction service đã kết thúc. Nếu service bắt lỗi và trả thành công bên trong transaction, test phải điều chỉnh để xác minh rollback-only behavior đúng với hợp đồng.

## 21. Kiểm tra nhiều transaction manager

Nếu test context có cả JDBC và R2DBC hoặc nhiều `ConnectionFactory`, cần chỉ định đúng manager:

```java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> reactiveOperation() {
    return customerRepository.save(customer).then();
}
```

Một `TransactionalOperator` gắn với manager khác có thể mở transaction trên database khác. Nếu repository dùng factory A nhưng operator dùng factory B, test có thể thấy lệnh insert không rollback như mong đợi.

Mỗi `R2dbcTransactionManager` quản lý một `ConnectionFactory`. Không giả định một transaction reactive bao phủ nhiều database độc lập. Nếu một nghiệp vụ ghi nhiều nguồn, hãy test từng local transaction và cơ chế điều phối như outbox/saga; rollback nguồn này không tự rollback nguồn kia.

## 22. Transaction test và thao tác async ngoài publisher

Một lỗi thường gặp là tạo publisher phụ nhưng subscribe riêng:

```java
Mono<Void> operation = customerRepository.save(customer)
        .doOnNext(saved -> auditRepository.save(
                Audit.created(saved.getId())).subscribe())
        .then();
```

Test có thể đợi `operation` hoàn tất nhưng audit publisher vẫn chạy độc lập. Nó có thể commit ngoài transaction hoặc hoàn tất sau khi test đã cleanup. Khi cần cả hai thao tác cùng transaction, nối chúng:

```java
Mono<Void> operation = customerRepository.save(customer)
        .flatMap(saved -> auditRepository.save(
                Audit.created(saved.getId())))
        .then();
```

Để cùng rollback, cả hai repository phải dùng cùng `ConnectionFactory` được transaction manager quản lý. Nối publisher là điều kiện cần để giữ thứ tự và lỗi, nhưng chưa đủ nếu chúng dùng hai nguồn dữ liệu khác nhau.

## 23. Đọc dữ liệu xác minh ở ngoài transaction

Sau rollback, query xác minh nên:

- Được tạo và subscribe sau khi `TransactionalOperator.transactional(...)` phát terminal signal.
- Dùng cùng database/schema mà thao tác ghi đã dùng.
- Không tham gia một transaction ngoài chưa commit có thể che khuất kết quả.
- Truy vấn theo khóa duy nhất của test, tránh đếm toàn bảng có dữ liệu dùng chung.
- Kiểm tra cả row count và trạng thái liên quan nếu thao tác ghi nhiều bảng.

Ví dụ kiểm tra hai bảng:

```java
Mono<Long> customerCount = customerRepository.countByEmail(email);
Mono<Long> auditCount = auditRepository.countByCorrelationId(correlationId);

StepVerifier.create(Mono.zip(customerCount, auditCount))
        .assertNext(counts -> {
            assertThat(counts.getT1()).isZero();
            assertThat(counts.getT2()).isZero();
        })
        .verifyComplete();
```

Query được chạy sau rollback và kiểm tra cả hai thay đổi không còn. Nếu một repository dùng factory khác, kết quả sẽ cho thấy transaction không bao phủ nó.

## 24. Test rollback không nên chỉ kiểm tra publisher phát lỗi

Một test chỉ làm điều này:

```java
StepVerifier.create(service.createThenFail(command))
        .expectError()
        .verify();
```

chỉ chứng minh publisher phát lỗi theo mong đợi. Nó không chứng minh dữ liệu đã rollback. Service có thể ghi ở một connection ngoài transaction, transaction manager có thể không được chọn đúng hoặc một thao tác phụ đã được subscribe độc lập.

Một test rollback đầy đủ phải xác minh trạng thái database sau transaction. Cũng nên có test thành công để chứng minh cùng pipeline commit khi hoàn tất bình thường; nếu chỉ test rollback, có thể vô tình viết code luôn rollback và vẫn làm test xanh.

## 25. Kiểm thử commit và rollback như hai nhánh đối xứng

Test commit:

```java
StepVerifier.create(transactionalOperator.transactional(
                customerRepository.save(customer)))
        .expectNextCount(1)
        .verifyComplete();

StepVerifier.create(customerRepository.existsByEmail(customer.getEmail()))
        .expectNext(true)
        .verifyComplete();
```

Test rollback:

```java
StepVerifier.create(transactionalOperator.transactional(
                customerRepository.save(customer)
                        .then(Mono.error(new ForcedRollbackException()))))
        .expectError(ForcedRollbackException.class)
        .verify();

StepVerifier.create(customerRepository.existsByEmail(customer.getEmail()))
        .expectNext(false)
        .verifyComplete();
```

Hai test dùng dữ liệu riêng. Nhánh commit chứng minh transaction hoàn tất bình thường sẽ lưu dữ liệu; nhánh rollback chứng minh lỗi trong boundary sẽ không commit thay đổi.

## 26. Isolation level và thứ tự kiểm tra

Khi test rollback, query xác minh cần chạy sau khi transaction kết thúc. Isolation level của transaction ghi và transaction đọc có thể ảnh hưởng khả năng nhìn thấy dữ liệu chưa commit, nhưng không nên dựa vào đọc trong cùng transaction để kết luận commit/rollback.

Nếu test dùng hai connection đồng thời, một query ở connection khác thường không nhìn thấy thay đổi chưa commit theo isolation phổ biến như READ COMMITTED. Tuy nhiên, test không cần suy luận từ trạng thái đang chạy; hãy đợi transaction kết thúc rồi query lại.

Đối với race condition hoặc concurrent transaction, tạo test riêng với hai subscription và barrier phù hợp. Không dùng sleep để giả định thứ tự. Xác minh cuối cùng bằng constraint và dữ liệu bền vững.

## 27. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Giả định `@Transactional` test giống JDBC | Publisher R2DBC có thể không nằm trong transaction test-managed | Dùng `TransactionalOperator` hoặc xác minh reactive test support của đúng phiên bản |
| Dùng `@Rollback` như bằng chứng rollback R2DBC | JDBC test listener có thể không quản lý reactive connection | Kiểm tra transaction manager và xác minh trạng thái database |
| Tạo publisher nhưng không subscribe | SQL không chạy, test có thể cho kết quả giả | Dùng `StepVerifier` hoặc subscriber test phù hợp |
| Bọc sai `ConnectionFactory` | Repository dùng connection ngoài transaction | Dùng cùng factory cho manager và thao tác được test |
| Query xác minh bên trong transaction | Nhìn thấy dữ liệu chưa commit | Chờ transaction kết thúc rồi query bằng subscription mới |
| Nuốt lỗi bên trong transaction | Publisher hoàn tất bình thường và transaction có thể commit | Để lỗi thoát boundary hoặc đánh dấu rollback-only |
| Gọi `subscribe()` trong service | Thao tác phụ chạy ngoài transaction/test lifecycle | Nối publisher bằng `flatMap`/`then` |
| Dùng `@Sql` JDBC để seed rồi đọc R2DBC trong cùng transaction | Hai connection không chia sẻ transaction | Dùng R2DBC fixture hoặc commit setup trước khi đọc |
| Chỉ assert lỗi, không assert database | Không chứng minh dữ liệu đã rollback | Query lại theo khóa duy nhất sau rollback |
| Dùng cùng test key giữa các test song song | Test ảnh hưởng lẫn nhau | Tạo dữ liệu duy nhất và cleanup có kiểm soát |
| Dùng mock để kết luận driver rollback | Không kiểm tra transaction thật | Dùng integration test với database/driver tương thích |
| Cho rằng một manager rollback nhiều datasource | Một nguồn khác có thể đã commit | Test từng local transaction; dùng outbox/saga cho phối hợp |

## 28. Quy trình xây dựng test rollback R2DBC

Một quy trình thực tế:

1. Xác định repository, template và `DatabaseClient` đang dùng `ConnectionFactory` nào.
2. Xác định `ReactiveTransactionManager` quản lý đúng factory đó.
3. Tạo `TransactionalOperator` từ manager tương ứng hoặc gọi service proxy có `@Transactional` reactive.
4. Tạo dữ liệu có khóa duy nhất cho test.
5. Nối tất cả thao tác ghi trong một publisher; không gọi `subscribe()` riêng.
6. Phát lỗi có chủ đích sau thao tác ghi hoặc kích hoạt lỗi database ở bước sau.
7. Để lỗi đi qua transaction boundary để transaction manager rollback.
8. Dùng `StepVerifier` đợi terminal signal trước khi tiếp tục.
9. Tạo query mới ở ngoài transaction để kiểm tra không có thay đổi đã commit.
10. Viết test commit đối xứng để xác nhận luồng thành công vẫn lưu dữ liệu.
11. Chạy integration test với đúng R2DBC driver/database, nhất là khi phụ thuộc constraint, cancellation hoặc commit behavior.
12. Dọn fixture bằng R2DBC và đợi publisher hoàn tất.

## 29. Nguyên tắc thực hành

- Không giả định transaction rollback của JDBC test áp dụng cho R2DBC.
- Phân biệt `PlatformTransactionManager` với `ReactiveTransactionManager`.
- Nhớ rằng transaction reactive được truyền qua Reactor Context, không phải thread-local JDBC context.
- Dùng `TransactionalOperator` để tạo ranh giới transaction rõ ràng trong test.
- Bảo đảm operator và repository/`DatabaseClient` dùng cùng `ConnectionFactory`.
- Để lỗi thoát khỏi publisher nằm trong transaction; không nuốt lỗi trước transaction boundary.
- Chờ transaction hoàn tất bằng `StepVerifier` trước khi query xác minh.
- Xác minh dữ liệu bằng subscription mới ở ngoài transaction.
- Không coi `@Transactional`, `@Rollback`, `@DataR2dbcTest` hoặc `@Sql` là bằng chứng tự động; kiểm tra behavior đúng phiên bản và connection.
- Không gọi `subscribe()` rời rạc hoặc `block()` trong service reactive.
- Dùng khóa test duy nhất, fixture R2DBC và cleanup có subscribe.
- Test cả commit và rollback; chỉ assert exception là chưa đủ.
- Dùng database/driver thật cho hành vi transaction, constraint, cancellation và commit.
- Nếu có nhiều datasource, kiểm thử riêng từng transaction boundary; một R2DBC manager không rollback nguồn khác.

## 30. Kết luận

Kiểm thử rollback trong Spring Data Relational R2DBC cần dựa trên reactive transaction boundary thực tế. JDBC test thường dựa vào `PlatformTransactionManager` và context gắn với thread; R2DBC dùng `ReactiveTransactionManager` và Reactor Context. Vì vậy, không thể mặc định `@Transactional` hoặc `@Rollback` của test sẽ bao publisher được `StepVerifier` subscribe như cách test JDBC truyền thống hoạt động.

Hãy dùng `TransactionalOperator` với cùng `ConnectionFactory` của repository, nối mọi thao tác ghi trong một publisher, để lỗi thoát khỏi transaction boundary và đợi rollback hoàn tất. Sau đó chạy một query mới ở ngoài transaction để xác minh dữ liệu không được commit. Kết hợp test commit đối xứng, fixture R2DBC, integration test trên driver/database thật và kiểm tra từng datasource sẽ giúp test phản ánh đúng semantics reactive thay vì dựa vào giả định của JDBC.
