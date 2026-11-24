# Thực hiện giao dịch dữ liệu phản ứng và kiểm thử đường lỗi

Trong Reactive Programming, một thao tác dữ liệu thường được biểu diễn bằng một publisher thay vì trả kết quả đồng bộ. `Mono` mô tả một kết quả bất đồng bộ có thể hoàn tất, phát lỗi hoặc không phát giá trị; `Flux` mô tả một chuỗi gồm nhiều phần tử. Subscriber đăng ký để nhận tín hiệu từ Publisher, còn backpressure giúp điều tiết lượng phần tử được yêu cầu khi xử lý luồng dữ liệu lớn.

Bài thực hành này áp dụng các khái niệm đó vào một giao dịch chuyển tiền giữa hai tài khoản. Ta dùng Spring Data R2DBC để truy cập cơ sở dữ liệu không chặn, `TransactionalOperator` để đặt ranh giới giao dịch phản ứng và Reactor Test với `StepVerifier` để kiểm tra cả đường thành công lẫn đường lỗi. Trọng tâm là bảo đảm hai cập nhật cùng thành công hoặc cùng được hoàn tác.

## Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Mô hình hóa một thao tác ghi dữ liệu bằng chuỗi `Mono` và chỉ thực hiện thao tác khi publisher được subscribe.
- Ghép các lệnh ghi theo đúng thứ tự bằng `then`, để lệnh ghi thứ hai chỉ chạy sau khi lệnh thứ nhất hoàn tất.
- Dùng `TransactionalOperator` với reactive transaction manager để commit khi publisher hoàn tất và rollback khi publisher phát lỗi.
- Phân biệt lỗi nghiệp vụ như tài khoản không tồn tại hoặc không đủ số dư với lỗi hạ tầng.
- Viết kiểm thử bằng `StepVerifier` để xác minh kết quả và trạng thái dữ liệu sau khi giao dịch lỗi.
- Nhận ra vị trí đặt toán tử xử lý lỗi có thể làm thay đổi kết quả commit hoặc rollback.

## Bối cảnh và quy tắc nghiệp vụ

Một lệnh chuyển tiền gồm hai cập nhật:

1. Trừ số tiền cần chuyển khỏi tài khoản nguồn.
2. Cộng cùng số tiền đó vào tài khoản nhận.

Giao dịch chỉ hợp lệ khi hai tài khoản tồn tại, hai tài khoản khác nhau, số tiền lớn hơn 0 và tài khoản nguồn có đủ số dư. Nếu bước cộng tiền thất bại sau khi bước trừ tiền đã thành công, số dư tài khoản nguồn phải được khôi phục. Không được để dữ liệu ở trạng thái đã trừ tiền nhưng chưa cộng tiền.

Ta sử dụng bảng PostgreSQL sau:

```sql
CREATE TABLE account (
    id UUID PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0)
);
```

Ràng buộc `CHECK` bảo vệ quy tắc số dư không âm ngay tại cơ sở dữ liệu. Câu lệnh trừ tiền cũng kiểm tra số dư trong điều kiện `WHERE`; nhờ đó việc kiểm tra và cập nhật số dư diễn ra trong cùng một câu lệnh SQL, tránh kiểu đọc số dư rồi ghi đè bằng một giá trị tính từ dữ liệu đã cũ.

Bài tập giả định ứng dụng dùng Java 17 trở lên, Spring Boot WebFlux, Spring Data R2DBC, driver R2DBC cho PostgreSQL và Reactor. Phần kiểm thử cần `reactor-test` và một cơ sở dữ liệu PostgreSQL dùng riêng cho test, chẳng hạn PostgreSQL chạy bằng Testcontainers. Các phiên bản thư viện nên theo Spring Boot dependency management của dự án.

## Thiết lập ranh giới giao dịch phản ứng

Spring Boot có thể cấu hình `ConnectionFactory` và reactive transaction manager khi ứng dụng đã khai báo driver R2DBC. Ta tạo `TransactionalOperator` từ manager đó:

```java
@Configuration
class ReactiveTransactionConfig {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

Hãy chắc chắn bean được tạo từ `ReactiveTransactionManager` dành cho R2DBC. Transaction manager kiểu JDBC đồng bộ không thể quản lý các thao tác R2DBC trong cùng reactive transaction.

Một reactive transaction được gắn với Reactor Context trong quá trình subscribe. Vì vậy, các thao tác R2DBC trong cùng chuỗi publisher có thể tham gia cùng giao dịch dù chúng không nhất thiết chạy trên cùng một thread. Không gọi `block()` trong service để chờ kết quả: thao tác đó phá vỡ luồng bất đồng bộ và có thể gây deadlock hoặc làm nghẽn thread xử lý request.

## Cài đặt dịch vụ chuyển tiền

Đoạn mã sau dùng `DatabaseClient` để thể hiện rõ từng câu lệnh SQL và số dòng được cập nhật. Các exception nghiệp vụ được dùng trong ví dụ là `AccountNotFoundException` và `InsufficientFundsException`; hãy định nghĩa chúng thành các lớp kế thừa `RuntimeException` trong dự án.

```java
@Service
class TransferService {

    private final DatabaseClient databaseClient;
    private final TransactionalOperator transactionalOperator;

    TransferService(
            DatabaseClient databaseClient,
            TransactionalOperator transactionalOperator) {
        this.databaseClient = databaseClient;
        this.transactionalOperator = transactionalOperator;
    }

    public Mono<Void> transfer(
            UUID sourceId,
            UUID destinationId,
            BigDecimal amount) {

        return Mono.defer(() -> {
            if (sourceId == null
                    || destinationId == null
                    || amount == null
                    || amount.signum() <= 0
                    || sourceId.equals(destinationId)) {
                return Mono.<Void>error(
                        new IllegalArgumentException(
                                "Invalid transfer request"));
            }

            return debit(sourceId, amount)
                    .then(credit(destinationId, amount));
        }).as(transactionalOperator::transactional);
    }

    private Mono<Void> debit(UUID accountId, BigDecimal amount) {
        return databaseClient.sql("""
                UPDATE account
                SET balance = balance - :amount
                WHERE id = :id AND balance >= :amount
                """)
                .bind("amount", amount)
                .bind("id", accountId)
                .fetch()
                .rowsUpdated()
                .flatMap(updated -> {
                    if (updated == 1L) {
                        return Mono.<Void>empty();
                    }

                    return accountExists(accountId)
                            .flatMap(exists -> exists
                                    ? Mono.<Void>error(
                                            new InsufficientFundsException(
                                                    accountId))
                                    : Mono.<Void>error(
                                            new AccountNotFoundException(
                                                    accountId)));
                });
    }

    private Mono<Void> credit(UUID accountId, BigDecimal amount) {
        return databaseClient.sql("""
                UPDATE account
                SET balance = balance + :amount
                WHERE id = :id
                """)
                .bind("amount", amount)
                .bind("id", accountId)
                .fetch()
                .rowsUpdated()
                .flatMap(updated -> updated == 1L
                        ? Mono.<Void>empty()
                        : Mono.<Void>error(
                                new AccountNotFoundException(accountId)));
    }

    private Mono<Boolean> accountExists(UUID accountId) {
        return databaseClient.sql("""
                SELECT EXISTS (
                    SELECT 1 FROM account WHERE id = :id
                ) AS present
                """)
                .bind("id", accountId)
                .map((row, metadata) ->
                        Boolean.TRUE.equals(
                                row.get("present", Boolean.class)))
                .one();
    }
}
```

Có một số điểm cần chú ý trong cách cài đặt:

- `Mono.defer` trì hoãn việc kiểm tra đầu vào và tạo chuỗi thao tác cho đến khi có subscriber. Những thao tác dữ liệu vì thế không chạy ngay tại thời điểm gọi phương thức.
- `debit(...).then(credit(...))` giữ đúng thứ tự. Nếu `debit` phát lỗi, `credit` không được subscribe.
- `rowsUpdated()` cho biết câu lệnh đã cập nhật bao nhiêu dòng. Nếu câu lệnh trừ tiền cập nhật 0 dòng, truy vấn `accountExists` giúp phân biệt tài khoản không tồn tại với tài khoản không đủ số dư.
- `credit` cũng kiểm tra số dòng cập nhật. Nếu tài khoản nhận không tồn tại, nó phát `AccountNotFoundException`.
- `as(transactionalOperator::transactional)` đặt toàn bộ chuỗi ghi trong một giao dịch. Khi chuỗi hoàn tất bình thường, giao dịch commit. Khi một publisher bên trong phát lỗi, giao dịch rollback rồi lỗi tiếp tục được truyền tới subscriber.

Việc dùng `Mono<Void>` phù hợp vì lệnh chuyển tiền chỉ cần báo hoàn tất hoặc lỗi; nó không cần phát một đối tượng kết quả trung gian. Nếu API cần trả biên nhận, có thể tạo một publisher kết quả sau khi các lệnh ghi hoàn tất, nhưng publisher đó vẫn phải nằm trong ranh giới giao dịch phù hợp.

## Kiểm thử cả kết quả lẫn trạng thái dữ liệu

Một kiểm thử chỉ xác nhận rằng publisher phát lỗi là chưa đủ. Ta cần kiểm tra dữ liệu sau lỗi để chứng minh rollback thực sự xảy ra. Hãy chạy kiểm thử tích hợp với PostgreSQL thật hoặc PostgreSQL Testcontainers; mock `DatabaseClient` không thể chứng minh hành vi transaction của cơ sở dữ liệu.

Ví dụ dưới đây giả định test context đã cung cấp `TransferService` và `DatabaseClient`, đồng thời schema ở trên đã được tạo. Mỗi test chuẩn bị tài khoản nguồn có 100.00 và tài khoản nhận có 50.00.

```java
@SpringBootTest
class TransferServiceIntegrationTest {

    private static final UUID SOURCE =
            UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final UUID DESTINATION =
            UUID.fromString("00000000-0000-0000-0000-000000000002");
    private static final UUID MISSING =
            UUID.fromString("00000000-0000-0000-0000-000000000099");

    @Autowired
    TransferService transferService;

    @Autowired
    DatabaseClient databaseClient;

    @BeforeEach
    void seedAccounts() {
        databaseClient.sql("DELETE FROM account")
                .fetch()
                .rowsUpdated()
                .then(insertAccount(SOURCE, "Nguồn", "100.00"))
                .then(insertAccount(DESTINATION, "Đích", "50.00"))
                .block();
    }

    private Mono<Long> insertAccount(
            UUID id, String owner, String balance) {
        return databaseClient.sql("""
                INSERT INTO account (id, owner_name, balance)
                VALUES (:id, :owner, :balance)
                """)
                .bind("id", id)
                .bind("owner", owner)
                .bind("balance", new BigDecimal(balance))
                .fetch()
                .rowsUpdated();
    }

    private Mono<BigDecimal> balance(UUID accountId) {
        return databaseClient.sql("""
                SELECT balance FROM account WHERE id = :id
                """)
                .bind("id", accountId)
                .map((row, metadata) ->
                        row.get("balance", BigDecimal.class))
                .one();
    }

    @Test
    void commitsBothAccountUpdates() {
        StepVerifier.create(
                        transferService.transfer(
                                SOURCE,
                                DESTINATION,
                                new BigDecimal("30.00")))
                .verifyComplete();

        StepVerifier.create(balance(SOURCE))
                .assertNext(value ->
                        assertThat(value)
                                .isEqualByComparingTo("70.00"))
                .verifyComplete();

        StepVerifier.create(balance(DESTINATION))
                .assertNext(value ->
                        assertThat(value)
                                .isEqualByComparingTo("80.00"))
                .verifyComplete();
    }

    @Test
    void rollsBackDebitWhenDestinationDoesNotExist() {
        StepVerifier.create(
                        transferService.transfer(
                                SOURCE,
                                MISSING,
                                new BigDecimal("30.00")))
                .expectError(AccountNotFoundException.class)
                .verify();

        StepVerifier.create(balance(SOURCE))
                .assertNext(value ->
                        assertThat(value)
                                .isEqualByComparingTo("100.00"))
                .verifyComplete();
    }

    @Test
    void keepsBothBalancesWhenSourceHasInsufficientFunds() {
        StepVerifier.create(
                        transferService.transfer(
                                SOURCE,
                                DESTINATION,
                                new BigDecimal("150.00")))
                .expectError(InsufficientFundsException.class)
                .verify();

        StepVerifier.create(balance(SOURCE))
                .assertNext(value ->
                        assertThat(value)
                                .isEqualByComparingTo("100.00"))
                .verifyComplete();

        StepVerifier.create(balance(DESTINATION))
                .assertNext(value ->
                        assertThat(value)
                                .isEqualByComparingTo("50.00"))
                .verifyComplete();
    }
}
```

Trong ví dụ, `block()` chỉ xuất hiện ở bước chuẩn bị dữ liệu của test, tại ranh giới giữa mã kiểm thử đồng bộ và publisher. Không đưa cách gọi đó vào `TransferService` hoặc controller. Nếu muốn toàn bộ phần chuẩn bị cũng theo kiểu phản ứng, có thể trả về `Mono<Void>` từ fixture và dùng `StepVerifier` để kích hoạt nó.

Ba test trên kiểm tra ba kết quả khác nhau:

| Tình huống | Kết quả publisher | Số dư nguồn | Số dư nhận |
|---|---|---:|---:|
| Chuyển 30.00 thành công | Hoàn tất | 70.00 | 80.00 |
| Tài khoản nhận không tồn tại | `AccountNotFoundException` | 100.00 sau rollback | Không có tài khoản |
| Nguồn chỉ có 100.00 nhưng chuyển 150.00 | `InsufficientFundsException` | 100.00 | 50.00 |

Test tài khoản nhận không tồn tại đặc biệt quan trọng: lệnh trừ tiền đã có cơ hội chạy thành công trước khi lệnh cộng tiền phát lỗi. Việc số dư nguồn vẫn là 100.00 chứng minh hai cập nhật cùng thuộc một giao dịch và rollback đã hoàn tác bước đầu tiên.

## Kiểm tra đường lỗi và vị trí xử lý lỗi

Reactive Streams truyền lỗi như một tín hiệu kết thúc. Khi một publisher phát `onError`, các toán tử phía sau có thể quan sát lỗi, chuyển lỗi thành kết quả khác hoặc tiếp tục bằng publisher thay thế. Điều đó ảnh hưởng trực tiếp đến transaction.

Ví dụ sau có rủi ro:

```java
return debit(sourceId, amount)
        .then(credit(destinationId, amount))
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

Nếu `credit` lỗi, `onErrorResume` chuyển lỗi thành hoàn tất bình thường trước khi publisher đi tới `TransactionalOperator`. Transaction operator nhìn thấy một chuỗi hoàn tất thành công và có thể commit phần trừ tiền. Đây là lỗi logic nghiêm trọng dù subscriber không nhận được exception.

Nếu cần chuyển lỗi thành phản hồi ở tầng gọi, hãy đặt bước phục hồi bên ngoài ranh giới giao dịch:

```java
return transferService.transfer(sourceId, destinationId, amount)
        .thenReturn(TransferResult.success())
        .onErrorResume(
                InsufficientFundsException.class,
                error -> Mono.just(TransferResult.rejected(
                        "Insufficient funds")));
```

Trong trường hợp này, publisher giao dịch phát lỗi và rollback trước; tầng gọi mới chuyển lỗi nghiệp vụ thành một kết quả phản hồi. Không dùng `onErrorResume` để nuốt lỗi bên trong chuỗi ghi nếu việc hoàn tất bình thường có thể khiến transaction commit dữ liệu dở dang.

Các toán tử thường gặp có vai trò khác nhau:

| Toán tử | Vai trò trong bài thực hành |
|---|---|
| `then(next)` | Chạy publisher tiếp theo sau khi publisher trước hoàn tất bình thường; lỗi sẽ dừng chuỗi. |
| `onErrorResume` | Thay publisher lỗi bằng publisher khác; vị trí đặt nó quyết định transaction có còn nhìn thấy lỗi hay không. |
| `doOnError` | Quan sát hoặc ghi log lỗi; không tự phục hồi và không biến lỗi thành hoàn tất. |
| `timeout` | Phát lỗi nếu thao tác vượt quá thời hạn; cần xác định timeout có làm transaction bị rollback hay không. |
| `retryWhen` | Subscribe lại khi có lỗi phù hợp; chỉ retry lỗi tạm thời và cần xem xét tính lặp an toàn của thao tác. |

Không retry mù quáng các lỗi nghiệp vụ như không đủ số dư. Với lỗi kết nối hoặc deadlock có thể retry, nhưng cần bảo đảm lệnh chuyển tiền có cơ chế idempotency nếu client hoặc tầng gọi có thể gửi lại cùng yêu cầu. Một mã yêu cầu duy nhất được lưu cùng giao dịch là cách phổ biến để ngăn một yêu cầu bị ghi nhận hai lần.

## Mở rộng với Flux và backpressure

Một lần chuyển tiền là một thao tác đơn nên `Mono` diễn tả tự nhiên. Khi nhận một luồng nhiều yêu cầu chuyển tiền, nguồn dữ liệu có thể là `Flux`. Ví dụ, xử lý tuần tự từng yêu cầu:

```java
Flux.fromIterable(transferRequests)
        .concatMap(request ->
                transferService.transfer(
                        request.sourceId(),
                        request.destinationId(),
                        request.amount()));
```

`concatMap` chỉ chuyển sang yêu cầu tiếp theo sau khi publisher của yêu cầu hiện tại hoàn tất. Cách này giữ thứ tự và giới hạn số giao dịch đang chạy đồng thời ở mức một trong chuỗi đó. Nếu dùng `flatMap`, có thể xử lý nhiều yêu cầu song song; hãy đặt giới hạn concurrency rõ ràng và đánh giá tải cơ sở dữ liệu, xung đột cập nhật và thứ tự nghiệp vụ.

Backpressure điều tiết số phần tử mà subscriber yêu cầu từ publisher. Nó không thay thế transaction, không tự giới hạn thời gian giữ khóa trong cơ sở dữ liệu và cũng không bảo đảm một batch là nguyên tử. Nếu yêu cầu toàn bộ batch phải cùng thành công hoặc cùng rollback, cần thiết kế một ranh giới transaction bao quanh batch và cân nhắc thời gian giao dịch, số lượng bản ghi cũng như khả năng khóa tài nguyên. Với batch lớn, nhiều giao dịch nhỏ có thể an toàn và dễ phục hồi hơn một giao dịch kéo dài.

## Các lỗi thường gặp cần tự kiểm tra

- **Dùng JDBC hoặc `block()` trong chuỗi R2DBC:** thao tác đồng bộ có thể chặn event loop và không tham gia reactive transaction đang mở.
- **Dùng sai transaction manager:** `TransactionalOperator` phải nhận reactive transaction manager tương ứng với `ConnectionFactory`.
- **Đặt `onErrorResume` quá sớm:** lỗi bị chuyển thành hoàn tất trước transaction boundary, khiến dữ liệu đã ghi có thể được commit.
- **Không kiểm tra số dòng cập nhật:** một câu lệnh `UPDATE` cập nhật 0 dòng có thể biểu thị tài khoản không tồn tại hoặc điều kiện nghiệp vụ không thỏa mãn.
- **Chỉ kiểm tra exception:** test cần đọc lại dữ liệu để xác minh rollback, đặc biệt khi lỗi xảy ra sau khi một lệnh ghi đã thành công.
- **Dùng `flatMap` không giới hạn cho batch:** quá nhiều thao tác đồng thời có thể gây áp lực lên connection pool và tăng xung đột dữ liệu.
- **Retry mọi loại lỗi:** retry lỗi nghiệp vụ không làm yêu cầu hợp lệ hơn và có thể lặp lại tác dụng phụ nếu thao tác không idempotent.

Khi xử lý hai tài khoản trong các giao dịch đồng thời theo hai chiều ngược nhau, cơ sở dữ liệu cũng có thể phát hiện deadlock do thứ tự khóa khác nhau. Nếu nghiệp vụ cần mức đồng thời cao, hãy thiết kế thứ tự khóa nhất quán cho các tài khoản và chỉ retry lỗi deadlock hoặc lỗi tạm thời theo chính sách có giới hạn.

## Nhiệm vụ thực hành

Hãy hoàn thiện dịch vụ và bộ kiểm thử trong dự án của bạn theo thứ tự sau:

1. Tạo bảng `account` và thêm hai tài khoản mẫu có số dư 100.00 và 50.00.
2. Cấu hình reactive transaction manager cùng `TransactionalOperator`.
3. Cài đặt `transfer`, `debit`, `credit` và kiểm tra tài khoản tồn tại như ví dụ.
4. Chạy test chuyển tiền thành công; xác minh cả hai số dư thay đổi đúng.
5. Chạy test thiếu số dư; xác minh publisher phát đúng exception và cả hai số dư giữ nguyên.
6. Chạy test tài khoản nhận không tồn tại; xác minh lệnh trừ tiền đã được hoàn tác.
7. Thử đặt `onErrorResume` bên trong transaction boundary, quan sát test rollback thất bại, sau đó chuyển xử lý lỗi ra tầng gọi và chạy lại test.
8. Thêm test cho số tiền bằng 0, số tiền âm, ID null và trường hợp tài khoản nguồn trùng tài khoản nhận.
9. Nếu mở rộng sang `Flux`, thử `concatMap` và `flatMap` có giới hạn concurrency; quan sát số thao tác đồng thời và kiểm tra dữ liệu sau khi một phần tử phát lỗi.

## Tiêu chí hoàn thành

Bài thực hành đạt yêu cầu khi:

- Các thao tác truy cập dữ liệu đều dùng API R2DBC và không chặn trong service.
- Hai cập nhật của một lệnh chuyển tiền nằm trong cùng reactive transaction.
- Lỗi ở bước ghi thứ hai làm rollback bước ghi thứ nhất.
- Lỗi nghiệp vụ được truyền rõ ràng tới subscriber và có thể được ánh xạ thành phản hồi ở tầng gọi.
- Kiểm thử dùng `StepVerifier` để kích hoạt publisher, kiểm tra tín hiệu và đọc lại số dư từ cơ sở dữ liệu.
- Các trường hợp đầu vào không hợp lệ không làm thay đổi dữ liệu.

Hãy giữ test rollback như một kiểm thử hồi quy. Nó xác minh hợp đồng quan trọng nhất của giao dịch dữ liệu phản ứng: mọi thao tác ghi thuộc cùng một nghiệp vụ phải cùng commit hoặc cùng rollback, kể cả khi lỗi xuất hiện sau khi một phần công việc đã hoàn tất.

