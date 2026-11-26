# Kiểm thử reactive/coroutine với điều kiện hoàn thành hoặc hủy

## 1. Kết quả cần kiểm tra không chỉ là dữ liệu nhận được

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, một lời gọi repository reactive hoặc coroutine chỉ được xem là đã kiểm chứng khi bài test quan sát đúng vòng đời thực thi của nó.

Nhận được một entity chưa đủ để kết luận toàn bộ luồng đã hoàn thành. Gửi lệnh hủy chưa đủ để kết luận database đã rollback hoặc connection đã được trả về pool. Một hàm `suspend` trả về null cũng có ý nghĩa khác với việc coroutine bị hủy.

Cần phân biệt ba kết quả chính:

| Kết quả | Reactive | Coroutine/Flow | Câu hỏi kiểm chứng |
| --- | --- | --- | --- |
| Hoàn thành bình thường | `onComplete`, có thể có dữ liệu trước đó | Hàm trả về hoặc collect kết thúc bình thường | Đủ dữ liệu và các bước bắt buộc đã hoàn tất chưa? |
| Thất bại | `onError` | Exception được truyền ra | Có đúng loại lỗi và trạng thái dữ liệu sau lỗi không? |
| Hủy | Subscriber cancel subscription | Job bị cancel hoặc consumer dừng upstream sớm | Hủy tại mốc nào, cleanup và dữ liệu còn lại ra sao? |

Một stream rỗng nhưng hoàn thành bình thường không phải lỗi. Một stream đã phát vài phần tử rồi lỗi không phải thành công hoàn toàn. Hủy là một yêu cầu điều khiển vòng đời, không phải một giá trị “không tìm thấy”.

Theo hợp đồng Reactive Streams, `cancel()` yêu cầu publisher ngừng gửi dữ liệu và cleanup; vẫn có thể có dữ liệu đang trên đường đáp ứng demand đã được cấp trước đó. Không suy rằng mọi tài nguyên bên ngoài đã dừng ngay tại thời điểm gọi cancel. [Subscription API](https://www.reactive-streams.org/reactive-streams-1.0.4-javadoc/org/reactivestreams/Subscription.html).

## 2. Viết điều kiện kết thúc trước khi viết test

Một mô tả tốt cần có ít nhất ba phần:

~~~text
Mốc bắt đầu quan sát
    -> điều kiện để cho phép hoàn thành hoặc gửi hủy
    -> bằng chứng cần có sau đó
~~~

Ví dụ:

- Query phải phát đúng ba bản ghi đã sắp xếp rồi hoàn thành.
- Query cho ID không tồn tại phải hoàn thành rỗng, không đổi lỗi mapping thành rỗng.
- Consumer nhận bản ghi đầu tiên rồi hủy; nguồn kiểm soát trong test phải nhận được cancellation.
- Giao dịch ghi một bản ghi, dừng tại một điểm chưa thể commit, rồi bị hủy; sau rollback không còn bản ghi đó.
- Coroutine đang chờ nguồn reactive bị cancel; adapter phải truyền hủy tới subscription và cleanup cục bộ phải kết thúc.

Không dùng mô tả “chờ một chút rồi hủy” khi có thể tạo một điểm đồng bộ xác định. Tốc độ máy, network và driver khác nhau có thể làm test hủy trước khi tác vụ bắt đầu hoặc sau khi nó đã hoàn tất.

### 2.1. Các tầng bằng chứng

| Tầng | Bằng chứng có thể quan sát | Điều chưa tự chứng minh |
| --- | --- | --- |
| Operator/adapter | Giá trị, lỗi, cancel có đi đúng đường không | Database thực tế đã xử lý ra sao |
| Repository integration | Mapping, query và completion/error trên store thật | Mọi ranh giới service hoặc side effect đều đúng |
| Transaction integration | Commit/rollback và trạng thái dữ liệu sau kết thúc | Tác dụng phụ ngoài tài nguyên giao dịch được thu hồi |
| Tài nguyên | Cursor/connection được tái sử dụng hoặc giải phóng theo hợp đồng | Mọi topology và mọi tải production đều giống test |

Các lớp này bổ sung bằng chứng cho nhau. Một nguồn `Flux.just` được dựng trong test hữu ích để kiểm tra operator, nhưng không thay cho query thật khi mục tiêu là driver, cursor hoặc rollback.

## 3. StepVerifier: kiểm tra đầy đủ tín hiệu kết thúc

Reactor cung cấp `StepVerifier` trong `reactor-test` để mô tả các sự kiện mong đợi. Cần gọi `verify` hoặc một biến thể thực thi verification; chỉ dựng builder chưa chạy bài test. Nên đặt timeout hữu hạn cho verification. [Reactor testing](https://projectreactor.io/docs/core/release/reference/testing.html).

Các ví dụ đầu là test của publisher được kiểm soát, chưa phải repository integration test.

### 3.1. Hoàn thành với dữ liệu

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class PublisherCompletionTest {

    @Test
    void emitsExpectedValuesAndCompletes() {
        Flux<String> source = Flux.just("A100", "B100");

        StepVerifier.create(source)
            .expectNext("A100", "B100")
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }
}
~~~

Nếu chỉ kiểm tra một `onNext` rồi kết thúc test, một lỗi xuất hiện sau dữ liệu có thể bị bỏ sót. Điều kiện `expectComplete` thể hiện rằng không có phần tử hoặc lỗi bất ngờ còn lại trong hợp đồng của stream này.

### 3.2. Hoàn thành rỗng

~~~java
StepVerifier.create(Flux.<String>empty())
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Đây là kết quả hợp lệ nếu hợp đồng cho phép không có bản ghi. Với repository, hãy dùng một fixture chắc chắn không khớp để kiểm chứng đường này; đừng chỉ mock một nguồn rỗng rồi kết luận query đúng.

### 3.3. Phát dữ liệu rồi thất bại

~~~java
Flux<String> source = Flux.just("A100")
    .concatWith(Flux.error(
        new IllegalStateException("mapping bị từ chối")
    ));

StepVerifier.create(source)
    .expectNext("A100")
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().equals("mapping bị từ chối")
    )
    .verify(Duration.ofSeconds(5));
~~~

Lỗi là tín hiệu kết thúc của chuỗi. Một fallback như `onErrorResume` có thể thay đường lỗi bằng một chuỗi khác; bài test cần kiểm tra đúng hợp đồng fallback thay vì vô tình che lỗi. [Reactor error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).

Không đặt `onErrorResume(error -> Flux.empty())` vào test chỉ để nó hoàn thành. Khi đó lỗi kết nối hoặc lỗi materialization có thể bị biến thành kết quả không tìm thấy.

## 4. Hủy publisher tại một điểm xác định

Một nguồn phát một phần tử rồi chờ vô hạn giúp chứng minh đường cancel mà không phụ thuộc tốc độ timer:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean(false);

Flux<String> source = Flux.just("A100")
    .concatWith(Flux.<String>never())
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 0)
    .thenRequest(1)
    .expectNext("A100")
    .thenCancel()
    .verify(Duration.ofSeconds(5));

assertTrue(cancelled.get());
~~~

Mốc hủy ở đây là sau khi đã nhận `A100`. Phần `never` giữ nguồn chưa hoàn thành, nên test không phải chạy đua với một completion tự nhiên.

Bằng chứng thu được là callback cancel của publisher cục bộ đã chạy. Nó chưa chứng minh query server đã dừng, cursor đã đóng hoặc transaction đã rollback.

### 4.1. Demand và số phần tử xử lý không phải cùng một đại lượng

Khởi tạo verifier với demand 0 và dùng `thenRequest` giúp quan sát hợp đồng yêu cầu dữ liệu ở ranh giới đang kiểm tra. Tuy nhiên, operator prefetch, buffering và driver có thể làm lượng công việc upstream khác số phần tử consumer cuối đã nhận.

Vì vậy, với repository thật:

- Có thể kiểm tra consumer nhận đúng tập con rồi dừng.
- Có thể kiểm tra tài nguyên được giải phóng theo cơ chế quan sát phù hợp.
- Không mặc định “nhận một phần tử” nghĩa là database chỉ đọc đúng một row.
- Không dùng backpressure thay cho giới hạn query nếu mục tiêu là giảm lượng dữ liệu truy vấn.

### 4.2. take tạo hai góc nhìn khác nhau

Một operator giới hạn số phần tử có thể làm downstream kết thúc bình thường trong khi upstream bị hủy. Bài test cần chỉ rõ đang quan sát phía nào.

Ví dụ, việc client đã nhận đủ một phần tử và thấy completion không tự chứng minh publisher giao dịch upstream đã được tiêu thụ toàn bộ. Đây là điểm đặc biệt quan trọng khi kết quả stream nằm trong ranh giới transaction.

## 5. Thời gian ảo và timeout là hai công cụ khác nhau

Đối với operator thời gian của Reactor, có thể kiểm tra bằng virtual time:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1))
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(59))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Tạo publisher thời gian bên trong supplier giúp operator sử dụng scheduler của kịch bản virtual time. Ví dụ này kiểm tra timer, không tăng tốc PostgreSQL, MongoDB hay network I/O.

Cần phân biệt:

| Công cụ | Mục đích |
| --- | --- |
| Virtual time | Điều khiển thời gian của code/operator dùng scheduler kiểm thử |
| Timeout nghiệp vụ | Một phần hành vi ứng dụng khi chờ quá lâu |
| Timeout của verifier/test runner | Giới hạn thời gian test được phép treo |
| Điểm đồng bộ | Xác nhận tác vụ đã tới đúng mốc trước khi hủy |

Dùng `verify(Duration)` để test không chờ vô hạn không có nghĩa ứng dụng đã phát sinh lỗi timeout nghiệp vụ. Ngược lại, chèn `timeout` vào publisher sẽ thay đổi chính chuỗi cần kiểm tra.

## 6. Fixture tích hợp: repository R2DBC trên PostgreSQL

Ví dụ tiếp theo chọn một store hỗ trợ truy cập reactive và transaction tương ứng: **Spring Data R2DBC với PostgreSQL**. Không áp dụng kết luận của ví dụ cho mọi repository Spring Data.

Phần Java minh họa dùng Java 17+, Spring Boot 3.5, Reactor, JUnit Jupiter, `reactor-test`, PostgreSQL R2DBC driver, `spring-boot-testcontainers` và PostgreSQLContainer thuộc API Testcontainers 1.x với dependency management tương thích. Phiên bản khác cần đối chiếu package/API.

Các public type được hiểu là nằm trong các file riêng khi triển khai. Ứng dụng test cần có cấu hình Spring Boot gốc và package scan phù hợp.

### 6.1. Model và repository

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("stream_entry")
public record StreamEntry(
    @Id Long id,
    @Column("batch_key") String batchKey,
    String payload
) {
}
~~~

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface StreamEntryRepository
        extends ReactiveCrudRepository<StreamEntry, Long> {

    Flux<StreamEntry> findByBatchKeyOrderByIdAsc(String batchKey);

    Mono<Long> countByBatchKey(String batchKey);
}
~~~

Mỗi tình huống dùng một `batchKey` duy nhất để không phụ thuộc số bản ghi từ test khác. Đây là namespace fixture, không thay thế toàn bộ chiến lược dọn database.

### 6.2. Container, schema và transaction operator

~~~java
import java.nio.charset.StandardCharsets;

import io.r2dbc.spi.ConnectionFactory;

import org.springframework.boot.autoconfigure.r2dbc.R2dbcConnectionDetails;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.r2dbc.connection.init.ConnectionFactoryInitializer;
import org.springframework.r2dbc.connection.init.ResourceDatabasePopulator;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class ReactiveLifecycleFixture {

    @Bean
    @ServiceConnection(type = R2dbcConnectionDetails.class)
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("lifecycle_test")
            .withUsername("lifecycle_test")
            .withPassword("lifecycle_test");
    }

    @Bean
    ConnectionFactoryInitializer fixtureSchema(
            ConnectionFactory connectionFactory) {

        String ddl = """
            CREATE TABLE IF NOT EXISTS stream_entry (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                batch_key VARCHAR(80) NOT NULL,
                payload VARCHAR(200) NOT NULL
            );
            """;

        ConnectionFactoryInitializer initializer =
            new ConnectionFactoryInitializer();
        initializer.setConnectionFactory(connectionFactory);
        initializer.setDatabasePopulator(
            new ResourceDatabasePopulator(
                new ByteArrayResource(
                    ddl.getBytes(StandardCharsets.UTF_8)
                )
            )
        );
        return initializer;
    }

    @Bean
    TransactionalOperator lifecycleBoundary(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Schema được dựng từ một resource trong bộ nhớ cho fixture học tập. Đây không phải kiểm chứng migration của một ứng dụng cụ thể. Cần giữ một cơ chế tạo schema chính trong test, và chỉ chạy thao tác khởi tạo này trên backend test cô lập.

Spring Boot có thể quản lý container như bean và cung cấp connection details cho loại kết nối được hỗ trợ. Trong cấu hình trên, connection details được giới hạn cho R2DBC; container database không tự cung cấp driver R2DBC cho ứng dụng. [Spring Boot Testcontainers integration](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html).

Image là lựa chọn minh họa. Cần chọn version/digest phù hợp môi trường cần kiểm chứng; không suy container một node tái hiện mọi đặc điểm production.

## 7. Giao dịch reactive: chờ rollback rồi mới kiểm tra dữ liệu

Với `TransactionalOperator`, cancellation có ảnh hưởng đến kết quả giao dịch. Spring Framework từ 5.3 xử lý cancel signal bằng rollback trong cơ chế này. Do đó, các operator dừng sớm ở downstream có thể làm giao dịch upstream không commit dù downstream đã nhận đủ dữ liệu nó muốn. [Cancel signals trong transaction lập trình](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).

Điều này không có nghĩa mọi thao tác reactive trên mọi store đều tự rollback khi bị hủy. Ví dụ phải có:

- Reactive transaction manager phù hợp.
- Repository và manager dùng cùng tài nguyên ConnectionFactory.
- Các thao tác nằm trong cùng ranh giới reactive transaction.
- Thời điểm hủy trước khi giao dịch kết thúc.
- Chính sách xử lý lỗi/hủy không làm mất hợp đồng đang kiểm chứng.

### 7.1. Hai mốc quan sát riêng

Đối với test hủy sau khi ghi:

~~~text
Đã ghi trong transaction nhưng chưa commit
    -> gửi cancel
    -> nhận thông báo transaction đã rollback
    -> query mới kiểm tra bản ghi không còn
~~~

Không thay mốc “transaction đã rollback” bằng việc `thenCancel().verify()` đã trả về. Sau cancel, cleanup có thể tiếp tục bất đồng bộ.

Trong fixture test có thể đăng ký reactive transaction synchronization để quan sát completion status. Phải dùng `org.springframework.transaction.reactive.TransactionSynchronizationManager`, gắn với subscriber context, thay vì manager imperative dựa vào thread. [Reactive TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronizationManager.html).

Callback `afterCompletion` cung cấp trạng thái commit/rollback. Nó phục vụ quan sát transaction, không tự chứng minh mọi bước giải phóng pool hoặc công việc ngoài transaction đã xong. [Reactive TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronization.html).

### 7.2. Kiểm tra commit, lỗi và hủy trên cùng fixture

Class sau dùng các model và cấu hình ở phần trước. Không đặt transaction test imperative bao ngoài class này:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.reactive.TransactionSynchronization;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataR2dbcTest
@Import(ReactiveLifecycleFixture.class)
class StreamEntryLifecycleTest {

    @Autowired
    StreamEntryRepository entries;

    @Autowired
    TransactionalOperator lifecycleBoundary;

    @Test
    void completeCommitsBothWrites() throws Exception {
        String batch = UUID.randomUUID().toString();
        CompletableFuture<Integer> finished = new CompletableFuture<>();

        Mono<Void> work = lifecycleBoundary.execute(status ->
            observeCompletion(finished)
                .then(entries.save(
                    new StreamEntry(null, batch, "first")
                ))
                .then(entries.save(
                    new StreamEntry(null, batch, "second")
                ))
                .then()
        ).then();

        StepVerifier.create(work)
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        assertEquals(
            TransactionSynchronization.STATUS_COMMITTED,
            finished.get(5, TimeUnit.SECONDS).intValue()
        );
        assertCount(batch, 2L);

        StepVerifier.create(
                entries.findByBatchKeyOrderByIdAsc(batch)
                    .map(StreamEntry::payload)
            )
            .expectNext("first", "second")
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void errorRollsBackCompletedWrite() throws Exception {
        String batch = UUID.randomUUID().toString();
        CompletableFuture<Integer> finished = new CompletableFuture<>();

        Mono<Void> work = lifecycleBoundary.execute(status ->
            observeCompletion(finished)
                .then(entries.save(
                    new StreamEntry(null, batch, "before-error")
                ))
                .then(Mono.<Void>error(
                    new IllegalStateException("rejected")
                ))
        ).then();

        StepVerifier.create(work)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "rejected".equals(error.getMessage())
            )
            .verify(Duration.ofSeconds(10));

        assertEquals(
            TransactionSynchronization.STATUS_ROLLED_BACK,
            finished.get(5, TimeUnit.SECONDS).intValue()
        );
        assertCount(batch, 0L);
    }

    @Test
    void cancelAfterWriteRollsBackBeforePostcondition()
            throws Exception {

        String batch = UUID.randomUUID().toString();
        CountDownLatch writeReached = new CountDownLatch(1);
        CompletableFuture<Integer> finished = new CompletableFuture<>();

        Mono<Void> work = lifecycleBoundary.execute(status ->
            observeCompletion(finished)
                .then(entries.save(
                    new StreamEntry(null, batch, "before-cancel")
                ))
                .then(Mono.fromRunnable(writeReached::countDown))
                .then(Mono.<Void>never())
        ).then();

        StepVerifier.create(work)
            .then(() -> awaitWrite(writeReached))
            .thenCancel()
            .verify(Duration.ofSeconds(10));

        assertEquals(
            TransactionSynchronization.STATUS_ROLLED_BACK,
            finished.get(5, TimeUnit.SECONDS).intValue()
        );
        assertCount(batch, 0L);
    }

    private Mono<Void> observeCompletion(
            CompletableFuture<Integer> finished) {

        return TransactionSynchronizationManager
            .forCurrentTransaction()
            .doOnNext(manager -> manager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public Mono<Void> afterCompletion(int status) {
                        finished.complete(status);
                        return Mono.empty();
                    }
                }
            ))
            .then();
    }

    private void awaitWrite(CountDownLatch reached) {
        try {
            assertTrue(
                reached.await(5, TimeUnit.SECONDS),
                "Chưa tới mốc ghi dữ liệu trước khi hủy"
            );
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new AssertionError(error);
        }
    }

    private void assertCount(String batch, long expected) {
        StepVerifier.create(entries.countByBatchKey(batch))
            .expectNext(expected)
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }
}
~~~

Các phép đợi bằng latch/future ở đây thuộc **test harness**, có giới hạn thời gian và chạy từ phía kiểm thử. Không chuyển các phép đợi blocking này vào event-loop hoặc code xử lý reactive của ứng dụng.

### 7.3. Vì sao test hủy không chạy đua với commit?

Sau khi `save` hoàn tất trong transaction, `writeReached` được báo hiệu. Tiếp đó `Mono.never` giữ đơn vị công việc chưa thể hoàn thành bình thường. Verifier chỉ gửi cancel sau khi đã xác nhận mốc ghi.

Nếu lỗi xảy ra trước mốc đó, phép chờ thất bại thay vì cho phép test hủy ngay từ đầu rồi kết luận rollback đúng. Nếu giao dịch không báo rollback, future chờ completion không thỏa mãn điều kiện.

Query kiểm tra count là một subscription mới sau khi trạng thái transaction đã được xác nhận. Nó không đọc dữ liệu chưa commit từ chính giao dịch đang bị hủy.

Bộ test chứng minh ba hành vi trong phạm vi PostgreSQL/R2DBC được cấu hình:

1. Hoàn thành bình thường dẫn tới commit và đọc lại được cả hai bản ghi.
2. Lỗi sau lần ghi đầu dẫn tới rollback.
3. Hủy ở điểm treo sau lần ghi đầu dẫn tới rollback.

Nó chưa mô phỏng một câu SQL chậm đang chạy trong server. Nếu mục tiêu là driver gửi yêu cầu hủy SQL hoặc đóng cursor đang đọc, cần một kịch bản và tín hiệu quan sát chuyên biệt ở tầng driver/server.

### 7.4. Đừng suy rộng từ trạng thái transaction sang mọi tài nguyên

Callback `afterCompletion` giúp xác định kết quả transaction. Muốn chứng minh connection được trả về pool, cần thêm bằng chứng như khả năng lấy connection mới trong một pool được giới hạn phù hợp hoặc metric pool đáng tin cậy.

Một query mới thành công trên pool lớn không loại trừ khả năng một connection khác đã bị rò rỉ. Một assertion cờ `cancelled = true` lại càng không đủ để kiểm tra pool.

Nếu quan sát cursor, subscription hoặc tài nguyên ngoài database, xác định riêng mốc cleanup của tài nguyên đó. Không dùng một cờ chung cho các loại cleanup khác nhau.

## 8. Coroutine repository: kiểm tra giá trị, rỗng và lỗi đúng hợp đồng

Trong module hỗ trợ coroutine, repository có thể mở rộng `CoroutineCrudRepository`; method trả một giá trị dùng `suspend`, còn truy vấn nhiều phần tử có thể trả `Flow`. Các repository coroutine dựa trên hạ tầng reactive phù hợp, không biến mọi store blocking thành non-blocking chỉ bằng từ khóa `suspend`. [Coroutines trong Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/kotlin/coroutines.html).

Cần xét các trường hợp riêng:

| API | Hoàn thành bình thường | Tình huống cần kiểm tra thêm |
| --- | --- | --- |
| `suspend fun findById(id): T?` | Có entity hoặc null theo hợp đồng | Lỗi mapping và cancellation phải không bị đổi thành null |
| `suspend fun save(entity): T` | Trả entity kết quả | ID/version của entity bất biến và lỗi ghi |
| `fun findBy...(...): Flow<T>` | Collect đủ dữ liệu rồi kết thúc | Lỗi sau một phần dữ liệu hoặc consumer hủy |
| Hàm service gọi nhiều thao tác suspend | Thực hiện xong các bước bắt buộc | Transaction context và tác vụ con có được giữ đúng không |

Nếu dùng cả repository reactive lẫn coroutine trong một ví dụ thực tế, cần cấu hình discovery cho từng biến thể có chủ đích. Các đoạn coroutine phía sau tập trung kiểm tra vòng đời, không yêu cầu đăng ký thêm một repository trùng phạm vi với fixture Java.

### 8.1. Adapter không được làm mất ý nghĩa lỗi hoặc cancellation

`awaitSingleOrNull` trả null khi Mono hoàn thành rỗng, truyền lỗi của Mono và hủy subscription khi coroutine đang chờ bị hủy. [awaitSingleOrNull API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/await-single-or-null.html).

Vì vậy, một test đúng cần phân biệt:

~~~text
Mono.empty() -> null
Mono.error(...) -> exception
Job bị cancel khi đang chờ -> cancellation
~~~

Không dùng `catch (Exception)` rồi trả null cho cả ba. Nếu code cần bắt một nhóm lỗi nghiệp vụ, nên giữ cancellation đi ra đúng đường, chẳng hạn:

~~~kotlin
try {
    performRepositoryWork()
} catch (cancelled: kotlinx.coroutines.CancellationException) {
    throw cancelled
} catch (business: ReservationRejectedException) {
    handleRejection(business)
}
~~~

Đây là cấu trúc xử lý lỗi minh họa; `performRepositoryWork`, loại lỗi và handler phải được định nghĩa theo nghiệp vụ. Nó không có nghĩa mọi exception khác cũng nên bị nuốt.

## 9. Kiểm thử Flow hoàn thành, lỗi và hủy

Các ví dụ Kotlin sau dùng JUnit Jupiter, `kotlin-test`, `kotlinx-coroutines-core` và `kotlinx-coroutines-test` tương thích. Đây là test nguồn Flow được kiểm soát, chưa phải test database.

### 9.1. Hoàn thành và lỗi sau dữ liệu

~~~kotlin
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.time.Duration.Companion.seconds

class FlowResultTest {

    @Test
    fun collectsAllValuesBeforeReturning() = runTest(
        timeout = 10.seconds
    ) {
        val result = flowOf("A100", "B100").toList()

        assertEquals(listOf("A100", "B100"), result)
    }

    @Test
    fun partialDataDoesNotHideFailure() = runTest(
        timeout = 10.seconds
    ) {
        val observed = mutableListOf<String>()

        val error = assertFailsWith<IllegalStateException> {
            flow {
                emit("A100")
                throw IllegalStateException("mapping bị từ chối")
            }.collect { observed += it }
        }

        assertEquals(listOf("A100"), observed)
        assertEquals("mapping bị từ chối", error.message)
    }
}
~~~

`toList` chỉ phù hợp với một luồng được kỳ vọng hữu hạn và có kích thước chấp nhận được. Dùng nó trên luồng vô hạn sẽ không tạo kết quả hoàn thành.

Bản ghi đầu tiên đã được xử lý không làm lỗi phía sau biến mất. Nếu ứng dụng có tác dụng phụ theo từng phần tử, bài test còn phải xem các tác dụng phụ trước lỗi có cần rollback hay được chấp nhận là xử lý từng phần.

### 9.2. Hủy Job sau khi nguồn đã tới điểm chờ

~~~kotlin
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.seconds

class FlowCancellationTest {

    @Test
    fun cancelWaitsForLocalFinallyToFinish() = runTest(
        timeout = 10.seconds
    ) {
        val reachedWait = CompletableDeferred<Unit>()
        val cleaned = CompletableDeferred<Unit>()
        val observed = mutableListOf<String>()
        var cancellationSeen = false

        val source = flow {
            try {
                emit("A100")
                reachedWait.complete(Unit)
                awaitCancellation()
            } catch (cancelled: CancellationException) {
                cancellationSeen = true
                throw cancelled
            } finally {
                cleaned.complete(Unit)
            }
        }

        val consumer = launch {
            source.collect { observed += it }
        }

        reachedWait.await()
        consumer.cancelAndJoin()

        assertTrue(consumer.isCancelled)
        assertTrue(cancellationSeen)
        assertTrue(cleaned.isCompleted)
        assertEquals(listOf("A100"), observed)
    }
}
~~~

`cancelAndJoin` gửi hủy và chờ Job được hủy hoàn tất. Nó giúp tránh assertion chạy trước `finally` của coroutine cục bộ. [cancelAndJoin API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/cancel-and-join.html).

`reachedWait` xác định điểm hủy sau khi phần tử đã được collect. Cleanup trong ví dụ chỉ hoàn thành một deferred, không thực hiện I/O và không cần một đoạn suspend bổ sung.

Nếu `finally` thực sự phải gọi cleanup suspend khi Job đã bị hủy, cần thiết kế phạm vi cleanup phù hợp và có giới hạn, chẳng hạn dùng một khối `NonCancellable` nhỏ khi cần. Không bọc toàn bộ nghiệp vụ bằng `NonCancellable` để làm test hủy không còn tác dụng.

Job kết thúc cũng chưa chứng minh driver bên ngoài đã hoàn tất mọi cleanup bất đồng bộ. Với repository thật, vẫn cần bằng chứng store/tài nguyên như phần transaction đã chỉ ra.

### 9.3. Consumer take(1) kết thúc bình thường nhưng dừng upstream

~~~kotlin
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FlowTakeTest {

    @Test
    fun takesOneAndStopsOriginalFlow() = runTest {
        var reachedSecondValue = false
        var cleaned = false

        val source = flow {
            try {
                emit("A100")
                reachedSecondValue = true
                emit("B100")
            } finally {
                cleaned = true
            }
        }

        val result = source.take(1).toList()

        assertEquals(listOf("A100"), result)
        assertFalse(reachedSecondValue)
        assertTrue(cleaned)
    }
}
~~~

`take(1)` dừng flow gốc sau phần tử đầu, trong khi phép collect tập con trả về bình thường. Đây là ví dụ khác nhau giữa kết quả của consumer và vòng đời upstream; không nên kiểm tra nó bằng giả định Job ngoài luôn ở trạng thái cancelled. [Flow.take API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/take.html).

Khi upstream có một ranh giới giao dịch, cần kiểm tra semantics thực tế của adapter và transaction API. Không suy rằng collect một phần kết quả đã commit phần dữ liệu tương ứng.

## 10. Kiểm tra cầu nối từ coroutine tới subscription reactive

Một bài test adapter giúp xác nhận cancellation không dừng lại ở Job mà còn được truyền tới nguồn reactive:

~~~kotlin
import java.util.concurrent.atomic.AtomicBoolean

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.reactor.awaitSingleOrNull
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Test
import reactor.core.publisher.Mono
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.seconds

class CoroutineReactorCancellationTest {

    @Test
    fun cancellingAwaitCancelsSubscription() = runTest(
        timeout = 10.seconds
    ) {
        val subscribed = CompletableDeferred<Unit>()
        val sourceCancelled = AtomicBoolean(false)

        val source = Mono.never<String>()
            .doOnSubscribe { subscribed.complete(Unit) }
            .doOnCancel { sourceCancelled.set(true) }

        val task = launch {
            source.awaitSingleOrNull()
        }

        subscribed.await()
        task.cancelAndJoin()

        assertTrue(task.isCancelled)
        assertTrue(sourceCancelled.get())
    }
}
~~~

Cần có `kotlinx-coroutines-reactor` cho adapter này. Nguồn `Mono.never` được chọn để chắc chắn task vẫn đang chờ khi test gửi hủy.

Test chứng minh adapter đã cancel subscription của nguồn kiểm soát. Nếu thay nguồn bằng một repository thực, cần thêm cách biết query đã tới mốc mong muốn và quan sát cleanup đúng loại tài nguyên.

Không dùng một cờ ở đầu method repository làm bằng chứng query server đã bắt đầu. Nó có thể chỉ đánh dấu thời điểm publisher được tạo hoặc method được gọi.

### 10.1. Đưa trường hợp empty và error vào cùng hợp đồng adapter

Với adapter cho phép null, có thể kiểm tra riêng:

~~~kotlin
import kotlinx.coroutines.reactor.awaitSingleOrNull
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Test
import reactor.core.publisher.Mono
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

class CoroutineReactorResultTest {

    @Test
    fun emptyCompletesWithNullButErrorStillThrows() = runTest {
        assertNull(Mono.empty<String>().awaitSingleOrNull())

        assertFailsWith<IllegalArgumentException> {
            Mono.error<String>(
                IllegalArgumentException("invalid fixture")
            ).awaitSingleOrNull()
        }
    }
}
~~~

Không chọn adapter nullable chỉ để tránh kiểm tra “không tìm thấy”. Kiểu trả về phải phản ánh hợp đồng ứng dụng: không có entity, có lỗi và bị hủy là ba trạng thái khác nhau.

## 11. runTest, virtual time và I/O thật

`runTest` cung cấp coroutine test scope, scheduler kiểm thử và giới hạn thời gian của test. Delay dùng scheduler phù hợp có thể được bỏ qua bằng virtual time; delay hoặc I/O ở dispatcher khác không tự tuân theo scheduler đó. [runTest API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-test/kotlinx.coroutines.test/run-test.html).

Một test timeout thuần có thể là:

~~~kotlin
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.jupiter.api.Test
import kotlin.test.assertFailsWith

class CoroutineTimeoutTest {

    @Test
    fun timesOutWorkThatUsesTestScheduler() = runTest {
        assertFailsWith<TimeoutCancellationException> {
            withTimeout(100) {
                delay(1_000)
            }
        }
    }
}
~~~

Đây là kiểm tra coroutine timeout trên code dùng scheduler của test. Nó không mô phỏng PostgreSQL thực hiện một query trong 1.000 ms.

`withTimeout` hủy block bằng `TimeoutCancellationException` khi hết hạn; cancellation vẫn cần code hợp tác để được xử lý. Blocking code không tự biến thành cancellable chỉ vì nằm trong block này. [withTimeout API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/with-timeout.html).

Với database thật:

- Dùng điểm đồng bộ hoặc khả năng quan sát của driver/server để xác định tiến độ.
- Giữ timeout của test hữu hạn để phát hiện treo.
- Không tăng virtual time rồi kết luận database đã thực thi xong.
- Không dùng một chuỗi delay cố định thay cho completion của thao tác.
- Kiểm tra mốc cleanup riêng nếu cancellation từ coroutine kích hoạt cleanup bất đồng bộ bên ngoài Job.

### 11.1. Giữ structured concurrency trong code được kiểm thử

Nếu service tự tạo một scope không thuộc lời gọi, hoặc dùng `GlobalScope` để ghi dữ liệu, việc hủy caller có thể không hủy công việc đã tách ra. Bài test cần quan sát Job thực sự sở hữu thao tác đó.

Nếu ứng dụng cố ý có một tác vụ nền sống lâu hơn request, cần hợp đồng vận hành riêng cho nó. Không biến tác vụ nền thành một phần đã được rollback chỉ vì request coroutine bị hủy.

Một test kết thúc mà vẫn còn tác vụ nền ghi dữ liệu cũng có thể làm bẩn fixture của test sau. Cần sở hữu vòng đời task, chờ kết thúc khi thích hợp và dọn tài nguyên có chủ đích.

## 12. Không đánh đồng hủy với thu hồi mọi tác dụng phụ

Bảng sau cho thấy các kết luận cần tránh:

| Quan sát | Kết luận có thể có | Điều cần bằng chứng bổ sung |
| --- | --- | --- |
| Consumer đã nhận một entity | Một phần dữ liệu đã tới consumer | Stream hoàn thành, transaction commit |
| doOnCancel chạy | Một đường cancellation cục bộ được kích hoạt | Driver/server dừng công việc, tài nguyên đã đóng |
| Job ở trạng thái cancelled | Job kết thúc do hủy | Query bên ngoài đã rollback |
| finally của Flow chạy | Khối finally cục bộ đã thực thi | Mọi cleanup I/O đã hoàn tất |
| afterCompletion báo rollback | Transaction được quan sát đã rollback | Pool/cursor và side effect ngoài transaction |
| Query sau hủy thấy dữ liệu tồn tại | Có dữ liệu nhìn thấy sau mốc quan sát | Dữ liệu do giao dịch nào ghi và thời điểm commit nào |

Nếu một lần ghi chạy autocommit đã thành công trước khi hủy, cancellation sau đó không tự xóa bản ghi. Nếu transaction đã commit trước mốc hủy, một yêu cầu hủy muộn không quay ngược commit.

Tác dụng phụ như gửi email, gọi HTTP hoặc ghi sang store khác cũng không tự được thu hồi bằng rollback của một transaction R2DBC. Kiểm thử cần gắn hậu điều kiện với tài nguyên cụ thể.

Đối với luồng đọc, mục tiêu có thể là đóng cursor và trả connection chứ không phải rollback dữ liệu. Đối với luồng ghi, cần thêm các hậu điều kiện về tính nguyên tử và xử lý phần đã hoàn tất.

### 12.1. Hủy ở từng giai đoạn tạo bằng chứng khác nhau

| Mốc hủy | Tình huống được kiểm tra |
| --- | --- |
| Trước subscribe/collect | Chủ yếu kiểm tra việc chưa bắt đầu hoặc không tiêu thụ |
| Sau subscription nhưng trước thao tác dữ liệu | Hủy khi chuẩn bị/tham gia tài nguyên |
| Trong lúc chờ dữ liệu | Hợp tác của adapter, driver và cleanup |
| Sau một phần dữ liệu | Consumer dừng sớm và lượng công việc đã diễn ra |
| Sau một lần ghi nhưng trước commit | Rollback của đơn vị công việc đang mở |
| Sau khi hoàn tất/commit | Hủy muộn và khả năng không còn công việc để hủy |

Không dùng duy nhất tình huống cancel ngay sau subscribe làm bằng chứng cho tất cả các giai đoạn.

## 13. Phân trang, projection và truy vấn hữu hạn

Các abstraction Spring Data cần được kiểm tra cùng điều kiện kết thúc:

- Với một query có sort, kiểm tra thứ tự dữ liệu rồi xác nhận completion.
- Với projection, kiểm tra từng field cần thiết; lỗi materialization có thể xuất hiện khi phần tử thực sự được đọc.
- Với truy vấn được giới hạn hoặc phân trang, kiểm tra đúng hợp đồng trả về mà module reactive/coroutine hỗ trợ.
- Nếu ứng dụng thực hiện query dữ liệu và query count riêng, kiểm tra completion/error của cả hai thao tác cần dùng.
- Không mặc định mọi module reactive đều hỗ trợ một kiểu trả về Page giống repository blocking.

Sử dụng `take` sau một query không giới hạn không tự chứng minh backend đã áp dụng một giới hạn tương ứng. Nếu mục tiêu là tiết kiệm công việc query, cần chọn khả năng giới hạn/phân trang của store và kiểm chứng query thực tế.

Với một stream dự định vô hạn, tiêu chí thành công có thể là nhận đủ một tập sự kiện rồi hủy và cleanup. Khi ấy `expectComplete` hoặc `toList` toàn bộ stream không phải điều kiện đúng.

Với một stream dự định hữu hạn, hủy sau vài phần tử sẽ bỏ qua lỗi ở phần còn lại. Nên có riêng test tiêu thụ đầy đủ và test dừng sớm nếu ứng dụng có cả hai đường sử dụng.

## 14. Ma trận kiểm thử theo khả năng store

| Stack | Công cụ quan sát tại API | Bằng chứng store cần bổ sung |
| --- | --- | --- |
| Reactive R2DBC | StepVerifier hoặc adapter coroutine | Transaction manager, dữ liệu sau commit/rollback, connection |
| Reactive MongoDB | StepVerifier/Flow theo API hỗ trợ | Session, topology transaction và cursor theo cấu hình |
| Coroutine repository trên module hỗ trợ | runTest, collect, Job lifecycle | Khả năng hủy và cleanup của đường reactive/driver bên dưới |
| Repository blocking được gọi từ coroutine | Kết quả suspend/Job ngoài | Khả năng hợp tác/interrupt của thao tác blocking thực tế |

Bài test cần dùng đúng backend cho mục tiêu. Nếu kiểm tra semantics transaction, chỉ mock repository thường không đủ. Nếu kiểm tra một operator ánh xạ lỗi thuần, khởi động database có thể không tạo thêm bằng chứng cần thiết.

Ngoài assertion kết quả, bộ fixture phải được cô lập:

1. Dùng khóa hoặc namespace riêng cho từng tình huống.
2. Chờ cleanup cần thiết trước khi tái sử dụng tài nguyên.
3. Không xóa dữ liệu chung khi test khác còn đang thực thi.
4. Không mặc định transaction test imperative bao trùm pipeline reactive.
5. Kết thúc container, pool và task theo vòng đời của bộ test.

Các ví dụ trong bài chưa được chạy trên một môi trường dự án cụ thể. Khi đưa vào dự án, cần hoàn thiện dependency, cấu hình module và điều kiện backend theo phiên bản thực tế rồi thực thi các tình huống tương ứng.

## 15. Chẩn đoán test treo hoặc kết quả không ổn định

| Dấu hiệu | Khả năng cần xem xét | Điểm kiểm tra |
| --- | --- | --- |
| Test qua nhưng không có SQL nào chạy | Publisher chưa subscribe hoặc Flow chưa collect | Vị trí verify/terminal operator |
| Nhận dữ liệu rồi test vẫn treo | Stream không hoàn thành hoặc có nguồn never | Hợp đồng hữu hạn/vô hạn và terminal expectation |
| Test hủy đôi khi commit | Mốc hủy chạy đua với completion | Gate trước commit, callback kết thúc transaction |
| Count sau cancel lúc 0 lúc 1 | Đọc trước rollback xong hoặc có lần ghi ngoài transaction | Mốc hậu điều kiện và tài nguyên thực tế |
| Job bị hủy nhưng DB vẫn làm việc | Driver/adapter chưa dừng hoặc công việc đã tách scope | Subscription, task owner, trạng thái server |
| Thêm sleep làm test ít lỗi hơn | Điểm đồng bộ đang thiếu | Tín hiệu tiến độ và completion thật |
| Virtual time không làm test I/O nhanh hơn | Công việc không dùng test scheduler | Driver, dispatcher và thời gian thực |
| Test sau không lấy được connection | Cleanup chưa xong hoặc tài nguyên bị rò rỉ | Pool, transaction completion và vòng đời context |
| Lỗi dữ liệu bị xem là kết quả rỗng | Fallback/catch quá rộng | Loại lỗi và đường xử lý cancellation |

Khi chẩn đoán, hãy ghi nhận sự kiện có tên rõ ràng như “subscription đã tạo”, “write đã hoàn tất trong transaction”, “cancel đã gửi”, “rollback đã báo xong”. Không gộp chúng thành một log “done” duy nhất.

Nếu dùng retry, mỗi subscription có thể tạo thêm công việc. Phải kiểm tra số lần thực hiện và tính chấp nhận được của việc lặp lại, nhất là khi thao tác có tác dụng phụ. Không thêm retry để che một test hủy đang thiếu điểm đồng bộ.

## 16. Tự kiểm tra kiến thức

1. Vì sao nhận đủ dữ liệu chưa chắc chứng minh publisher đã hoàn thành bình thường?
2. Hủy subscription khác với nhận onError ở điểm nào trong hợp đồng kiểm thử?
3. Vì sao thenCancel().verify() chưa đủ để đọc ngay hậu điều kiện rollback?
4. Điểm treo sau lần ghi đầu giúp test cancellation tránh chạy đua với commit như thế nào?
5. Callback afterCompletion chứng minh điều gì và chưa chứng minh điều gì về pool?
6. Vì sao Flow.take(1) có thể trả kết quả bình thường dù upstream bị dừng sớm?
7. cancelAndJoin giải quyết thứ tự assertion nào trong test coroutine cục bộ?
8. Vì sao awaitSingleOrNull cần phân biệt empty, error và cancellation?
9. runTest hoặc StepVerifier virtual time có điều khiển thời gian database thật không?
10. Một thao tác autocommit đã xong có được thu hồi khi caller bị hủy sau đó không?

Kiểm thử vòng đời reactive/coroutine cần xác định rõ thời điểm bắt đầu, điều kiện hoàn thành hoặc hủy, mốc cleanup và hậu điều kiện dữ liệu. Khi các mốc đó được quan sát riêng, repository abstraction của Spring Data có thể được đánh giá theo đúng khả năng của module và store đang sử dụng.
