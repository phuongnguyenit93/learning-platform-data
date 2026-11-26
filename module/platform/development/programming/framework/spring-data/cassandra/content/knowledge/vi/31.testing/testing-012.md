# Kiểm thử CompletableFuture và chuỗi phản ứng bằng StepVerifier trong Spring Data Cassandra

Trong ứng dụng sử dụng **Spring Data Cassandra**, dữ liệu có thể được truy cập qua `CassandraRepository`/`CassandraTemplate` theo kiểu đồng bộ, qua Java Driver theo kiểu bất đồng bộ hoặc qua `ReactiveCassandraRepository`/`ReactiveCassandraTemplate` theo mô hình phản ứng. Khi kiểm thử, mỗi cách trả kết quả đòi hỏi một phương pháp quan sát riêng:

- `CompletionStage`/`CompletableFuture`: xác minh **khi nào tác vụ hoàn tất**, giá trị nhận được và nguyên nhân hoàn tất bất thường.
- Reactor `Mono`/`Flux`: dùng **`StepVerifier`** để xác minh thứ tự tín hiệu `onNext`, `onError`, `onComplete`, cũng như yêu cầu dữ liệu (`request`), hủy (`cancel`) và thời gian.
- Với Cassandra thật: bổ sung kiểm thử tích hợp về khóa phân vùng, ánh xạ entity, CQL, consistency level và phân trang; mock đơn thuần không thể chứng minh các yếu tố này.

Mục tiêu là xây dựng các bài kiểm thử **có thể lặp lại**, không dựa vào `Thread.sleep()` hay thời gian mạng ngẫu nhiên, đồng thời không che giấu lỗi database bằng kết quả rỗng.

## 1. Phân biệt API và kiểu kết quả

| Điểm truy cập | Kết quả thường gặp | Cách kiểm thử phù hợp |
| --- | --- | --- |
| `CassandraTemplate.selectOneById(...)` | Entity hoặc `null`, theo kiểu đồng bộ | JUnit assertions; kiểm thử tích hợp khi cần xác minh CQL/ánh xạ. |
| Java Driver `CqlSession.executeAsync(...)` | `CompletionStage<AsyncResultSet>` | `CompletableFuture` được điều khiển thủ công trong test; chặn có giới hạn thời gian ở **mã test**. |
| `ReactiveCassandraRepository.findById(...)` | `Mono<Entity>` | `StepVerifier` kiểm tra giá trị, hoàn tất, rỗng hoặc lỗi. |
| Truy vấn reactive nhiều bản ghi | `Flux<Entity>` | `StepVerifier` kiểm tra thứ tự, số phần tử, `request`, hủy và sự hoàn tất. |

**`CompletionStage` không đồng nghĩa `CompletableFuture`.** Java Driver 4.x thường công bố giao diện `CompletionStage`; khi cần API chờ kết quả trong test, gọi `toCompletableFuture()`. Còn `Mono` và `Flux` là `Publisher`: thông thường truy vấn chỉ được thực thi khi có subscriber. Không dùng `block()`/`blockLast()` để kiểm thử chuỗi phản ứng nếu có thể dùng `StepVerifier`.

### Mô hình dữ liệu ví dụ

Một API đọc trạng thái đơn hàng theo `order_id` nên có bảng phù hợp với chính truy vấn đó:

~~~sql
CREATE TABLE IF NOT EXISTS orders_by_id (
    order_id uuid PRIMARY KEY,
    state text
);

SELECT state
FROM orders_by_id
WHERE order_id = ?;
~~~

`order_id` chính là partition key, nên phép đọc theo khóa có thể nhắm tới đúng replica set thay vì lọc trên toàn bộ bảng. Ví dụ này chỉ lấy tối đa một hàng; truy vấn nhiều hàng và phân trang sẽ được kiểm thử riêng. Trong ứng dụng thật, keyspace, replication factor và consistency level phải được cấu hình phù hợp với môi trường.

## 2. Kiểm thử CompletableFuture của Java Driver

### 2.1. Đối tượng cần kiểm thử

`CqlSession.executeAsync` trả về một `CompletionStage<AsyncResultSet>`. Service dưới đây biến phản hồi thành `CompletionStage<Optional<String>>`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

final class AsyncOrderGateway {
    private final CqlSession session;

    AsyncOrderGateway(CqlSession session) {
        this.session = session;
    }

    CompletionStage<Optional<String>> findState(UUID orderId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT state FROM orders_by_id WHERE order_id = ?")
            .addPositionalValue(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true) // Truy vấn chỉ đọc có thể được thử lại an toàn.
            .build();

        return session.executeAsync(query)
            .thenApply(result -> Optional.ofNullable(result.one())
                .map(row -> row.getString("state")));
    }
}
~~~

`AsyncResultSet.one()` đọc hàng đầu tiên của **trang hiện tại**; điều này hợp lý vì `order_id` là khóa chính nên truy vấn trả tối đa một hàng. Nếu đang kiểm thử API trả nhiều hàng, **không dùng `one()` làm bằng chứng đã duyệt hết dữ liệu**; cần xử lý `currentPage()` và `fetchNextPage()` hoặc luồng reactive tương ứng.

### 2.2. Điều khiển thời điểm hoàn tất, không ngủ chờ

Trong unit test, tạo một `CompletableFuture` chưa hoàn tất, để gateway gọi `executeAsync` rồi tự quyết định thời điểm giả lập server trả kết quả. Ví dụ dùng JUnit 5 và Mockito:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.Statement;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AsyncOrderGatewayTest {
    @Mock CqlSession session;
    @Mock AsyncResultSet resultSet;
    @Mock Row row;

    @Test
    void completesAfterDriverReturnsData() throws Exception {
        CompletableFuture<AsyncResultSet> driverReply =
            new CompletableFuture<>();
        when(session.executeAsync(any(Statement.class)))
            .thenReturn(driverReply);
        when(resultSet.one()).thenReturn(row);
        when(row.getString("state")).thenReturn("PAID");

        CompletionStage<Optional<String>> stage =
            new AsyncOrderGateway(session).findState(UUID.randomUUID());

        assertFalse(stage.toCompletableFuture().isDone());

        driverReply.complete(resultSet);

        assertEquals(Optional.of("PAID"),
            stage.toCompletableFuture().get(1, TimeUnit.SECONDS));
        verify(session).executeAsync(any(Statement.class));
    }

    @Test
    void noRowIsACompletedEmptyResult() throws Exception {
        when(session.executeAsync(any(Statement.class)))
            .thenReturn(CompletableFuture.completedFuture(resultSet));
        when(resultSet.one()).thenReturn(null);

        CompletionStage<Optional<String>> stage =
            new AsyncOrderGateway(session).findState(UUID.randomUUID());

        assertEquals(Optional.empty(),
            stage.toCompletableFuture().get(1, TimeUnit.SECONDS));
    }

    @Test
    void databaseFailureCompletesExceptionally() {
        CompletableFuture<AsyncResultSet> driverReply =
            new CompletableFuture<>();
        when(session.executeAsync(any(Statement.class)))
            .thenReturn(driverReply);
        RuntimeException databaseError =
            new IllegalStateException("simulated Cassandra error");

        CompletionStage<Optional<String>> stage =
            new AsyncOrderGateway(session).findState(UUID.randomUUID());
        driverReply.completeExceptionally(databaseError);

        CompletionException thrown = assertThrows(
            CompletionException.class,
            () -> stage.toCompletableFuture().join());
        assertSame(databaseError, thrown.getCause());
    }
}
~~~

**Điểm kiểm chứng được:** trước khi hoàn tất `driverReply`, stage đang pending; sau đó nó hoàn tất với dữ liệu đúng, hoàn tất rỗng khi không có hàng, hoặc hoàn tất bất thường với nguyên nhân ban đầu. Cách này không cần Cassandra đang chạy và không cần `Thread.sleep()`.

Đoạn `join()` trong test lỗi chỉ được gọi **sau** `completeExceptionally()` nên không treo. Với một future chưa biết lúc nào hoàn tất, trong test nên dùng `get(timeout, unit)` hoặc cơ chế giới hạn thời gian của JUnit; `get()` và `join()` không giới hạn thời gian có thể khiến bộ kiểm thử treo vô hạn.

### 2.3. Các tình huống cần bổ sung

| Tình huống | Cách kích hoạt trong test | Kỳ vọng |
| --- | --- | --- |
| Thành công | `complete(resultSet)` | Stage trả giá trị, không ném lỗi. |
| Không tìm thấy | `resultSet.one() == null` | `Optional.empty()`; khác với lỗi truy cập dữ liệu. |
| `Unavailable`/`ReadTimeout` | `completeExceptionally(cassandraError)` | Giữ đúng loại hoặc nguyên nhân lỗi; không đổi thành kết quả rỗng. |
| Ghi bị `WriteTimeout` | Hoàn tất bất thường ở gateway ghi | Không tự khẳng định ghi thất bại hoàn toàn hoặc tự động retry thao tác không idempotent. |
| Nhiều request đồng thời | Tạo một future riêng cho mỗi request | Kết quả không bị trộn giữa các `order_id`; số request đang chờ được giới hạn. |
| Client hủy | Hủy future hoặc stage trả về | Xác minh hợp đồng hủy tại tầng ứng dụng; **không giả định** server Cassandra đã hủy CQL. |

Lưu ý khi test `CompletionStage`:

- `thenApply` chỉ biến đổi kết quả; `exceptionally`, `handle` và `whenComplete` có ý nghĩa khác nhau. Một `exceptionally(error -> Optional.empty())` có thể **che giấu lỗi Cassandra** và làm API trả “không tìm thấy”.
- `get()` bọc lỗi trong `ExecutionException`; `join()` thường bọc trong `CompletionException`. Assertion phải kiểm tra `getCause()`.
- Không khẳng định callback chạy trên một thread cụ thể khi chưa chủ động cung cấp `Executor`. `thenApply` có thể chạy trong thread hoàn tất future.
- Việc gọi `cancel(true)` lên `CompletableFuture` không bảo đảm Java Driver hoặc coordinator dừng thao tác CQL đang xử lý.

## 3. Kiểm thử chuỗi phản ứng Spring Data Cassandra bằng StepVerifier

### 3.1. Entity, repository và service

Ví dụ sau minh họa `ReactiveCassandraRepository` đọc theo khóa chính và ánh xạ thành `Mono<String>`. Truy vấn thành công nhưng không có hàng phải cho kết quả nghiệp vụ khác với một lỗi truy cập Cassandra.

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import reactor.core.publisher.Mono;

@Table("orders_by_id")
class OrderById {
    @PrimaryKey("order_id")
    private UUID orderId;
    private String state;

    protected OrderById() {}

    OrderById(UUID orderId, String state) {
        this.orderId = orderId;
        this.state = state;
    }

    String getState() {
        return state;
    }
}

interface OrderRepository
        extends ReactiveCassandraRepository<OrderById, UUID> {
}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(UUID id) {
        super("Order not found: " + id);
    }
}

final class ReactiveOrderService {
    private final OrderRepository repository;

    ReactiveOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Mono<String> state(UUID id) {
        return repository.findById(id)
            .map(OrderById::getState)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
    }
}
~~~

Khi repository phát `onError` (ví dụ server read timeout), `switchIfEmpty` **không** chạy: lỗi đi tiếp trên chuỗi. Đây là khác biệt cơ bản giữa `Mono.empty()` (đọc thành công và không có hàng) với `Mono.error(...)` (không có kết quả tin cậy).

### 3.2. Ba phép kiểm thử StepVerifier cốt lõi

Thêm dependency `reactor-test` ở scope `test` cùng JUnit 5 và Mockito. `StepVerifier` cho phép nêu rõ giao thức tín hiệu mong đợi mà không gọi `block()`.

~~~java
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReactiveOrderServiceTest {
    @Mock OrderRepository repository;
    @InjectMocks ReactiveOrderService service;
    private final UUID id = UUID.fromString(
        "e55e66bd-7d0d-48e6-8730-ce97c6b91110");

    @Test
    void emitsStateThenCompletes() {
        when(repository.findById(id))
            .thenReturn(Mono.just(new OrderById(id, "PAID")));

        StepVerifier.create(service.state(id))
            .expectNext("PAID")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void emptyRowBecomesDomainNotFound() {
        when(repository.findById(id)).thenReturn(Mono.empty());

        StepVerifier.create(service.state(id))
            .expectError(OrderNotFoundException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void propagatesDatabaseError() {
        RuntimeException databaseError =
            new IllegalStateException("simulated read timeout");
        when(repository.findById(id))
            .thenReturn(Mono.error(databaseError));

        StepVerifier.create(service.state(id))
            .expectErrorMatches(error -> error == databaseError)
            .verify(Duration.ofSeconds(2));
    }
}
~~~

Những gì test trên xác minh:

1. **`onNext("PAID")` rồi `onComplete`** khi đọc được hàng và ánh xạ thành công.
2. **`onError(OrderNotFoundException)`** khi repository phát `onComplete` mà không có `onNext`.
3. **`onError(databaseError)`**, với nguyên nhân được giữ lại, khi Cassandra/repository thất bại.

`verify(Duration.ofSeconds(2))` là **giới hạn chờ của phép kiểm thử**, không phải timeout CQL hay timeout driver. Không nên dùng cùng một giá trị cố định làm quy tắc cho mọi môi trường: test thuần mock thường có thể chờ ngắn, còn test tích hợp với Cassandra thật cần một ngân sách rõ ràng và hợp lý hơn.

### 3.3. Flux, thứ tự phần tử và backpressure

`StepVerifier.create(publisher, initialRequest)` cho phép kiểm soát `request(n)`. Điều này hữu ích khi service xử lý một luồng nhiều hàng:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<String> states = Flux.just("NEW", "PAID", "SHIPPED");

StepVerifier.create(states, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("NEW")
    .thenRequest(2)
    .expectNext("PAID", "SHIPPED")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Test xác minh **hợp đồng Reactive Streams của publisher được kiểm thử**: chỉ phát dữ liệu theo yêu cầu của subscriber, đúng thứ tự đã định, rồi kết thúc. Với `Flux` sinh từ repository mock như `Flux.just(...)`, test này **không chứng minh Cassandra thực sự tải trang theo số lượng `request`**. Driver có thể prefetch, buffer và chọn fetch size riêng; phải dùng test tích hợp và metric/quan sát driver nếu muốn xác minh hành vi thực tế.

Đối với truy vấn đọc dữ liệu có nhiều bản ghi, nên kiểm thử thêm trường hợp subscription bị hủy:

~~~java
StepVerifier.create(Flux.just("NEW", "PAID", "SHIPPED"), 0)
    .thenRequest(1)
    .expectNext("NEW")
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

`thenCancel()` chứng minh subscriber hủy luồng theo kịch bản; không đủ để kết luận mọi truy vấn CQL đang chạy tại replica đều dừng tức thời.

### 3.4. Kiểm thử toán tử timeout bằng thời gian ảo

Chờ thực tế nhiều giây làm test chậm và dễ không ổn định. Với **thời gian do Reactor scheduler điều khiển**, dùng `StepVerifier.withVirtualTime`:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(30))
            .map(tick -> "PAID")
            .timeout(Duration.ofSeconds(5)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));
~~~

Đặt việc **tạo publisher bên trong lambda** truyền cho `withVirtualTime` để Reactor thay scheduler trước khi các toán tử sử dụng nó. `thenAwait` tiến thời gian ảo; không cần `Thread.sleep`.

**Giới hạn:** `withVirtualTime` chỉ điều khiển các toán tử dùng scheduler ảo của Reactor. Nó **không giả lập hoặc tăng tốc** timeout TCP, timeout server Cassandra, timeout của Java Driver, thao tác I/O thật hay `CompletableFuture.orTimeout(...)`. Nếu yêu cầu test phải kiểm tra `driver.request.timeout`, cần môi trường tích hợp có khả năng tạo độ trễ/lỗi thực sự hoặc điều khiển một abstraction riêng của ứng dụng.

## 4. Kết nối CompletableFuture với Mono đúng cách

Ứng dụng có thể nhận `CompletionStage` từ Java Driver hoặc một SDK khác rồi chuyển thành `Mono`. Để không phát lệnh CQL trước khi có subscriber, nên truyền **supplier** cho `Mono.fromCompletionStage(...)`:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;

final class AsyncToReactiveOrderService {
    private final AsyncOrderGateway gateway;

    AsyncToReactiveOrderService(AsyncOrderGateway gateway) {
        this.gateway = gateway;
    }

    Mono<String> findState(UUID id) {
        return Mono.fromCompletionStage(() -> gateway.findState(id))
            .flatMap(value -> Mono.justOrEmpty(value));
    }
}
~~~

`gateway.findState(id)` trong supplier được gọi khi có subscription. `Optional.empty()` trở thành `Mono.empty()`, còn exceptional completion trở thành `onError`. Mỗi lần subscription lại có thể phát sinh một yêu cầu mới; nếu kết quả cần được chia sẻ giữa các subscriber thì phải có thiết kế cache/memoization rõ ràng.

Ví dụ kiểm thử sự chuyển đổi, dùng một future được điều khiển trong test:

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

CompletableFuture<Optional<String>> future = new CompletableFuture<>();
Mono<String> mono = Mono.fromCompletionStage(() -> future)
    .flatMap(optional -> Mono.justOrEmpty(optional));

StepVerifier.create(mono)
    .then(() -> future.complete(Optional.of("PAID")))
    .expectNext("PAID")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Đoạn trên chứng minh **tín hiệu Reactor** được phát khi future hoàn tất. Khi giả lập lỗi, thay `future.complete(...)` bằng `future.completeExceptionally(cause)` và xác minh `expectErrorMatches(...)`; không viết `onErrorResume(error -> Mono.empty())` nếu việc mất dữ liệu và lỗi hạ tầng có ý nghĩa khác nhau.

## 5. Kiểm thử thời điểm subscribe, fallback và tác dụng phụ

Chuỗi reactive là mô tả việc xử lý. Một phép gọi repository có thể được xây dựng ở thời điểm tạo `Mono`, nhưng việc đọc dữ liệu thường xảy ra lúc có subscriber. Với mã có tác dụng phụ, dùng `Mono.defer` để buộc **khởi tạo thao tác** tại subscription:

~~~java
Mono<String> deferred = Mono.defer(
    () -> repository.findById(id).map(OrderById::getState));
~~~

Để kiểm tra chuỗi có subscribe vào publisher phụ hay không, có thể dùng `PublisherProbe` từ `reactor-test`:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.publisher.PublisherProbe;
import reactor.test.StepVerifier;

PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("CACHED"));
Mono<String> result =
    Mono.<String>empty().switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("CACHED")
    .verifyComplete();
fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

Trong ứng dụng Cassandra, fallback cần hợp đồng nghiệp vụ rõ ràng. `switchIfEmpty` thích hợp khi truy vấn **thành công nhưng không có hàng**, còn fallback sau `onErrorResume` phải quyết định rõ liệu dữ liệu cache cũ có được chấp nhận khi database bị lỗi hay không. Các test nên đảm bảo lỗi `ReadTimeout`, `Unavailable` hoặc `Overloaded` không bị âm thầm xem như “không có dữ liệu”.

## 6. Kiểm thử tích hợp với Cassandra thật

Mock `CqlSession` hoặc `ReactiveCassandraRepository` giúp kiểm tra logic chuyển đổi và lỗi **ở tầng ứng dụng**. Chúng không chứng minh rằng bảng tồn tại, câu CQL hợp lệ, trường ánh xạ đúng, partition key phân bố hợp lý hoặc consistency level hoạt động như mong muốn.

Với kiểm thử tích hợp, chạy Cassandra thử nghiệm độc lập, chẳng hạn container do **Testcontainers Cassandra** quản lý; cấu hình connection details cho Spring Boot/Spring Data, tạo keyspace và schema trước khi chạy. Ví dụ schema tối thiểu trong môi trường **một node**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS training
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS training.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text
);
~~~

Giả sử test Spring đã có `OrderRepository` nối tới keyspace `training` và bảng đã được tạo, có thể thực hiện:

~~~java
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class OrderRepositoryIntegrationTest {
    @Autowired OrderRepository repository;

    @Test
    void writesAndReadsTheSamePrimaryKey() {
        UUID id = UUID.randomUUID();

        StepVerifier.create(
                repository.save(new OrderById(id, "PAID"))
                    .then(repository.findById(id)))
            .assertNext(order -> assertEquals("PAID", order.getState()))
            .expectComplete()
            .verify(Duration.ofSeconds(15));
    }
}
~~~

Đây là **phần thân kiểm thử tích hợp**, cần kèm cấu hình container/kết nối và khởi tạo schema trong dự án thực tế; nó không tự dựng Cassandra. `then(repository.findById(id))` giữ thứ tự ghi rồi đọc trong cùng một subscription. Trong môi trường nhiều replica, cần chú ý consistency level, khả năng đọc dữ liệu cũ và ảnh hưởng của lỗi mạng; thành công trên một node RF = 1 **không chứng minh** khả năng chịu lỗi hoặc quorum của RF = 3.

### Các bất biến nên kiểm tra khi có truy vấn nhiều trang

Với bảng thiết kế theo partition key, ví dụ `orders_by_customer` có partition key `customer_id`, truy vấn nhiều hàng nên giới hạn đúng partition. Khi test paging, hãy tạo nhiều bản ghi hơn fetch size và xác minh:

1. **Không thiếu và không lặp hàng** trong lần duyệt trang đã hoàn tất, với dữ liệu thử nghiệm không bị thay đổi đồng thời.
2. **Thứ tự hợp lệ** nếu bảng có clustering columns và truy vấn yêu cầu một thứ tự cụ thể; không giả định thứ tự toàn cục giữa nhiều partition.
3. **Phân biệt kết thúc trang với kết thúc luồng**: một page có thể có ít hàng hơn fetch size; chỉ đánh giá hết dữ liệu dựa trên thông tin paging của driver hoặc terminal signal của `Flux`.
4. **Lỗi giữa các trang** phát `onError`; không tự coi luồng đã hoàn tất bình thường hoặc nuốt các hàng chưa tải được.
5. **Hủy sớm** không bị biến thành các tác dụng phụ nghiệp vụ không mong muốn; chỉ khẳng định mức hỗ trợ hủy thực tế mà driver cung cấp.

Nếu cần kiểm chứng `LOCAL_QUORUM` khi replica mất kết nối, bắt buộc dùng cụm đa node với RF phù hợp, fault injection có kiểm soát và đo kết quả theo CL. Một container một node chỉ phù hợp với các phép kiểm tra schema, serialization, CQL, entity mapping và đường đọc/ghi cơ bản.

## 7. Ma trận kiểm thử thực tế

| Lớp test | Kịch bản | Kết quả cần khẳng định |
| --- | --- | --- |
| Unit / future | Future chưa hoàn tất | Gateway chưa trả kết quả trước khi phản hồi được hoàn tất. |
| Unit / future | `completeExceptionally(...)` | Exception được chuyển tiếp, giữ nguyên nguyên nhân để phân loại. |
| Unit / reactive | `Mono.just(entity)` | Đúng `onNext` rồi `onComplete`. |
| Unit / reactive | `Mono.empty()` | Nhánh not found được kích hoạt, không nhầm với lỗi. |
| Unit / reactive | `Mono.error(cause)` | `onError` được giữ lại; không trả kết quả rỗng. |
| Unit / Flux | `request(1)` rồi `request(2)` | Thứ tự và lượng tín hiệu hợp lệ theo demand. |
| Unit / scheduler | `timeout` với virtual time | Phát `TimeoutException` mà không chờ đồng hồ thật. |
| Integration | Ghi rồi đọc theo primary key | CQL, schema, mapping và truy vấn theo khóa thực sự hoạt động. |
| Integration | Nhiều trang, lỗi ở trang sau | Không thiếu/trùng dữ liệu trong điều kiện thử nghiệm; lỗi trang sau không bị che giấu. |
| Cluster / fault injection | Replica lỗi, timeout hoặc quá tải | Quan sát timeout/consistency/retry theo đúng cơ chế của Cassandra thật. |

### Lỗi thường gặp khi viết test

- **Dùng `Thread.sleep(...)` để “chờ đủ lâu”**: khiến test phụ thuộc tốc độ máy và dễ flaky. Hãy điều khiển `CompletableFuture` hoặc dùng virtual time cho toán tử Reactor.
- **`StepVerifier.create(...)` rồi không gọi `verify...()`**: kịch bản chỉ mới được mô tả, chưa thực thi xác minh.
- **Chỉ gọi `expectNext(...)` mà không kiểm tra terminal signal**: có thể bỏ qua lỗi hoặc luồng treo về sau; xác minh `expectComplete()` hoặc `expectError(...)`.
- **Nuốt `onError` để biến thành `Mono.empty()`**: khiến timeout đọc bị diễn giải thành đơn hàng không tồn tại.
- **Dùng mock và gọi đó là kiểm thử CQL**: mock chỉ chứng minh các tín hiệu service giả lập, không xác minh giao thức hay thao tác Cassandra.
- **Test `Flux.just(...)` và khẳng định Cassandra paging/backpressure chính xác**: publisher giả lập không chứng minh fetch size, prefetch hay số round-trip thực.
- **Retry ghi sau `WriteTimeout` rồi khẳng định chỉ thực hiện một lần**: Cassandra có thể đã ghi dù client bị timeout; phải thiết kế idempotency và đối soát.
- **Truy vấn không có partition key trong test hiệu năng**: có thể tạo kết quả sai lệch so với workload thật; tránh `ALLOW FILTERING` để bù cho mô hình dữ liệu không phù hợp.

## 8. Tổng kết

Kiểm thử bất đồng bộ với Spring Data Cassandra cần hiểu đúng **hai lớp ngữ nghĩa**. `CompletableFuture` mô tả trạng thái hoàn tất của một thao tác Java Driver; `StepVerifier` mô tả giao thức tín hiệu của `Mono`/`Flux`. Unit test nên tự điều khiển future và publisher để khẳng định thứ tự, dữ liệu, lỗi, timeout và hủy mà không phụ thuộc thời gian mạng. Integration test với Cassandra thật bổ sung bằng chứng về CQL, entity mapping, khóa phân vùng và paging. Khi test liên quan consistency, replica hoặc lỗi mạng, phải dựng cụm phù hợp và kiểm soát điều kiện gây lỗi.

### Tài liệu tham khảo

- [Spring Data Cassandra — Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/).
- [Project Reactor — Testing với StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Project Reactor — reactor-test Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).
- [Apache Cassandra Java Driver — Asynchronous API](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/async/).
- [Testcontainers — Cassandra Module](https://java.testcontainers.org/modules/databases/cassandra/).
