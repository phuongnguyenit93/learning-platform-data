# Giới hạn đồng thời bằng cơ chế điều tiết yêu cầu trong Spring Data Cassandra

Một ứng dụng dùng **Spring Data Cassandra** có thể gửi nhiều truy vấn CQL cùng lúc thông qua repository, `CassandraTemplate`, `ReactiveCassandraTemplate` hoặc Java Driver. Khi traffic tăng đột ngột, số request đang chờ phản hồi (*in-flight requests*) có thể lớn hơn khả năng xử lý của client, coordinator và các replica Cassandra. Khi đó, tăng số luồng, tăng timeout hoặc retry liên tục thường khiến hàng đợi dài hơn, độ trễ cao hơn và lỗi lan rộng.

**Giới hạn đồng thời** (*concurrency limiting*) là cơ chế chỉ cho phép tối đa một số request nhất định đang thực thi; request đến khi đã hết chỗ được **xếp hàng có giới hạn** hoặc **từ chối sớm**. Đây là một dạng *request throttling* và *bulkhead*: một đợt tăng tải không được chiếm vô hạn tài nguyên của ứng dụng hay database.

Bài này giải thích cách đặt giới hạn ở Java Driver, Spring Data và Reactor, cách phối hợp với timeout, retry, paging, consistency level và cách đo xem giới hạn có thực sự giúp hệ thống ổn định hay không.

## 1. Vì sao Cassandra vẫn cần điều tiết số yêu cầu?

Cassandra phân phối dữ liệu theo **partition key**. Một câu CQL được driver gửi đến một **coordinator**, rồi coordinator phối hợp với replica sở hữu partition và trả kết quả theo **consistency level** (CL). Request có thể cần nhiều hoạt động mạng, đọc đĩa, xử lý tombstone và compaction; truy vấn nhắm vào hot partition còn có thể dồn tải vào một nhóm replica dù toàn cụm vẫn còn node rảnh.

~~~mermaid
flowchart LR
    A["API / Job / Consumer"] --> B["Service Spring Data Cassandra"]
    B --> L["Giới hạn request in-flight"]
    L --> D["Java Driver / CqlSession"]
    D --> C["Coordinator"]
    C --> R1["Replica A"]
    C --> R2["Replica B"]
    C --> R3["Replica C"]
    B -. "Từ chối sớm khi hết chỗ" .-> E["503 / tín hiệu lỗi / retry có kiểm soát"]
~~~

Nếu mỗi request đang chờ Cassandra giữ một lượng bộ nhớ, callback, kết nối hoặc tài nguyên xử lý ở phía ứng dụng, quá nhiều request đồng thời sẽ tăng áp lực lên cả client lẫn cluster. Với mã reactive, ít thread bị chặn **không có nghĩa** số request gửi đi là vô hạn hoặc không tốn tài nguyên.

### Phân biệt các cơ chế thường bị nhầm

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| **Concurrency limiter / bulkhead** | Số thao tác đang thực thi cùng một thời điểm | Tối đa 64 request Cassandra in-flight cho một ứng dụng. |
| **Rate limiter** | Số yêu cầu được chấp nhận theo đơn vị thời gian | Tối đa 500 request/giây từ một nhóm client. |
| **Bounded queue** | Số yêu cầu được phép chờ lấy chỗ thực thi | Đang có 64 request chạy, tối đa thêm 128 request đợi. |
| **Backpressure** | Khả năng downstream báo số phần tử có thể nhận | Subscriber Reactor dùng `request(n)` để điều tiết số phần tử từ upstream. |
| **Timeout/deadline** | Thời gian tối đa một yêu cầu được chờ hoặc thực thi | Hết ngân sách 2 giây thì yêu cầu phải kết thúc với lỗi phù hợp. |
| **Retry policy** | Số lần và điều kiện thử lại sau lỗi | Chỉ retry thao tác an toàn, hữu hạn và có backoff. |

Các cơ chế hỗ trợ nhau nhưng **không thay thế nhau**. Rate limit 500 request/giây vẫn có thể làm in-flight tăng cao khi mỗi yêu cầu bất ngờ chậm từ 40 ms lên 800 ms. Ngược lại, giới hạn 64 in-flight không bảo đảm có đúng 500 request/giây: throughput phụ thuộc độ trễ và năng lực xử lý thực tế.

### Suy luận từ định luật Little

Ở trạng thái tương đối ổn định, định luật Little cho biết:

\[
L = \lambda W
\]

Trong đó `L` là số request trung bình đang có trong hệ thống, `λ` là throughput trung bình (request/giây), còn `W` là thời gian trung bình mỗi request ở trong hệ thống (giây).

Ví dụ workload có **500 request/giây**, thời gian trung bình cho mỗi request là **80 ms = 0,08 giây**:

\[
L = 500 \times 0{,}08 = 40\ \text{request}
\]

Điều này giúp ước lượng một điểm bắt đầu, **không phải công thức tự động chọn giới hạn cuối cùng**. Các đợt burst, p95/p99, độ lệch phân bố partition key, retry, mức CL và số instance ứng dụng đều ảnh hưởng tới giá trị nên dùng. Nếu độ trễ trung bình tăng lên 400 ms mà throughput đầu vào vẫn 500 request/giây, số request phải cùng tồn tại theo cùng công thức sẽ là 200; giới hạn hợp lý giúp tránh hàng trăm request cùng dồn vào database và buộc hệ thống phát tín hiệu quá tải sớm.

## 2. Đặt giới hạn ở đâu trong Spring Data Cassandra?

Có ba lớp thực tế, mỗi lớp có phạm vi khác nhau:

1. **Biên API/job:** giới hạn số công việc được tiếp nhận trước khi gọi database. Phù hợp để bảo vệ deadline HTTP, bộ nhớ, tốc độ nhận thông điệp từ queue và công bằng giữa người dùng.
2. **Service/repository:** đặt bulkhead chung cho một nhóm truy vấn nặng, hoặc giới hạn `flatMap` khi xử lý cả danh sách dữ liệu. Phù hợp với workload đặc thù, chẳng hạn cập nhật hàng loạt theo partition key.
3. **Java Driver:** điều tiết các request CQL trên một phiên driver dùng chung (`CqlSession`), giúp bảo vệ tầng client ngay cả khi nhiều service cùng gọi xuống driver.

Giới hạn ở nhiều lớp là hợp lý khi mỗi lớp bảo vệ một tài nguyên riêng, nhưng cần đo tổng hành vi: request có thể chờ ở API, sau đó lại chờ trong throttler của driver, khiến timeout bị tiêu hao **trước khi** truy vấn thực sự chạy.

| Vị trí giới hạn | Phạm vi thường gặp | Điểm cần chú ý |
| --- | --- | --- |
| Một method dùng `flatMap(..., concurrency)` | Một subscription của một luồng | Nhiều subscriber/request HTTP vẫn có thể tạo nhiều luồng độc lập. |
| Singleton bulkhead ở service | Một instance ứng dụng, nếu mọi truy vấn cần bảo vệ đều đi qua nó | Nhiều pod/instance nhân tổng hạn mức; không bao phủ lối gọi khác. |
| Java Driver request throttler | Các request đi qua `CqlSession` được cấu hình | Cần hiểu cách driver đếm/chờ/từ chối request; không phải hạn mức toàn cluster. |
| API gateway / consumer concurrency | Một nhóm entrypoint hoặc partition của consumer | Nếu còn nguồn truy cập database khác, cần kiểm soát riêng. |

Trong một ứng dụng có 10 pod, mỗi pod cho 64 request Cassandra in-flight thì tổng có thể lên đến khoảng **640** trước khi tính những hệ thống client khác. Không được suy ra cluster chỉ chịu được 64 request vì từng instance có giới hạn 64.

## 3. Cơ chế request throttling của Java Driver 4.x

Java Driver 4.x cung cấp cơ chế **request throttler** được cấu hình cho session. Một lựa chọn là `ConcurrencyLimitingRequestThrottler`, nhằm giới hạn số request đồng thời và số request được giữ chờ trong queue.

Ví dụ cấu hình HOCON **minh họa** cho driver 4.x:

~~~hocon
datastax-java-driver {
  advanced.throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 64
    max-queue-size = 128
  }
  basic.request.timeout = 3 seconds
}
~~~

Hai con số **64 và 128 chỉ là ví dụ để thực nghiệm**; không phải giá trị khuyến nghị mặc định cho mọi hệ thống. Cấu hình thực tế cần đối chiếu phiên bản Java Driver/Spring Boot đang chạy, cách driver nạp `application.conf` và khả năng chịu tải của cluster.

Về mặt hành vi mong muốn:

- Khi số request đang chạy dưới `max-concurrent-requests`, driver có thể đưa request vào xử lý.
- Khi đã đủ request in-flight, request mới có thể chờ, miễn queue chưa đạt `max-queue-size`.
- Khi queue cũng đã đầy, request mới bị từ chối bằng lỗi throttling ở phía client, thường được nhận diện qua `RequestThrottlingException`.
- Request trong queue vẫn tiêu tốn **ngân sách thời gian** của caller. Queue lớn khiến nhiều request hết timeout trước khi có lượt chạy.

`RequestThrottlingException` ở driver **không phải** `OverloadedException` do Cassandra coordinator trả về. Hai lỗi đều có thể liên quan quá tải, nhưng một lỗi thể hiện giới hạn ở client, lỗi kia đến từ server. Phân biệt giúp xác định nên điều chỉnh admission ở ứng dụng hay điều tra tài nguyên Cassandra.

### Chọn độ dài queue

Queue không tự tạo thêm năng lực xử lý, nó chỉ hấp thụ burst ngắn. Nếu tốc độ đến cao hơn tốc độ hoàn tất trong thời gian dài, queue cuối cùng vẫn đầy và latency tiếp tục tăng.

Giả sử mức giới hạn 64 request chạy đồng thời, mỗi request trung bình 80 ms thì năng lực **ước tính rất thô** là khoảng:

\[
\frac{64}{0{,}08} = 800\ \text{request/giây}
\]

Giá trị này chỉ đúng trong điều kiện giả định độ trễ 80 ms còn giữ nguyên và request không vướng nút thắt khác. Ở tải cao, độ trễ thường tăng và throughput thực có thể thấp hơn đáng kể; thử nghiệm thực tế quan trọng hơn phép chia.

Nếu 128 yêu cầu đã xếp hàng, thời gian đợi cuối queue có thể lớn, đặc biệt khi các request phía trước chậm bất thường. Một request có deadline 500 ms khó nhận lợi ích từ queue dài. Vì vậy:

1. Đặt **giới hạn đồng thời** dựa trên điểm mà p95/p99 và lỗi vẫn chấp nhận được.
2. Chỉ cho phép **queue hữu hạn** đủ hấp thụ các đợt ngắn theo SLO.
3. Từ chối sớm khi không còn khả năng hoàn tất trước deadline; không để hàng đợi tăng vô hạn.
4. Quan sát queue wait time, timeout và tỉ lệ bị từ chối sau mỗi lần điều chỉnh.

Không tăng queue chỉ để làm số lỗi từ chối giảm; có thể bạn chỉ đang đổi lỗi nhận ngay thành lỗi timeout xuất hiện vài giây sau.

## 4. Giới hạn đồng thời cho CompletionStage/CompletableFuture

Nếu ứng dụng gọi `CqlSession.executeAsync(...)` hoặc SDK trả về `CompletionStage`, có thể dùng **`Semaphore` không chặn** bằng `tryAcquire()` để tạo bulkhead ở mức service. Đoạn mã sau từ chối ngay khi không còn permit, tránh giữ thêm thread chỉ để chờ:

~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

final class InFlightLimitExceededException extends RuntimeException {
    InFlightLimitExceededException() {
        super("Cassandra in-flight limit reached");
    }
}

final class AsyncInFlightLimiter {
    private final Semaphore permits;

    AsyncInFlightLimiter(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight);
    }

    <T> CompletionStage<T> execute(
            Supplier<? extends CompletionStage<T>> operation) {
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new InFlightLimitExceededException());
        }

        try {
            CompletionStage<T> running =
                Objects.requireNonNull(operation.get());
            return running.whenComplete((value, error) -> permits.release());
        } catch (RuntimeException | Error error) {
            permits.release();
            throw error;
        }
    }
}
~~~

Một permit chỉ được trả khi **tác vụ nguồn hoàn tất**, thành công hoặc thất bại; nếu `operation.get()` ném exception trước khi tạo stage, permit được trả trong `catch`. Dùng `tryAcquire()` tránh gọi `acquire()`/`join()` trên thread phục vụ request.

Tích hợp với câu CQL đọc đúng partition key:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

final class AsyncOrderReader {
    private final CqlSession session;
    private final AsyncInFlightLimiter limiter;

    AsyncOrderReader(CqlSession session, AsyncInFlightLimiter limiter) {
        this.session = session;
        this.limiter = limiter;
    }

    CompletionStage<Optional<String>> findState(UUID orderId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT state FROM orders_by_id WHERE order_id = ?")
            .addPositionalValue(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .build();

        return limiter.execute(() -> session.executeAsync(query))
            .thenApply(result -> Optional.ofNullable(result.one())
                .map(row -> row.getString("state")));
    }
}
~~~

Giả sử bảng `orders_by_id` có `order_id uuid PRIMARY KEY` và cột `state text`; CL trong ví dụ yêu cầu keyspace/cụm có RF đủ để dùng `LOCAL_QUORUM`. Với môi trường thử nghiệm một node RF = 1, phải xem lại thiết lập CL/RF cho đúng.

**Giới hạn phạm vi:** limiter trên chỉ quản lý request đi qua đối tượng đó trong một tiến trình. Nếu một đường code khác gọi thẳng `session.executeAsync`, nó không chịu hạn mức này. Có thể kết hợp service limiter với throttler driver để bảo vệ toàn bộ session.

### Hủy ở tầng ứng dụng không đồng nghĩa dừng CQL

Khi một request HTTP bị client hủy, `CompletableFuture.cancel(...)` hoặc hủy subscriber không bảo đảm coordinator/replica dừng xử lý mutation đã gửi. Nếu trả permit ngay khi HTTP hủy nhưng database vẫn đang xử lý, hệ thống có thể tiếp tục nạp thêm request xuống Cassandra. Vì vậy cần **định nghĩa rõ permit bao phủ giai đoạn nào**. Trong mã trên permit được giải phóng theo completion của stage nguồn; không đưa ra lời hứa rằng việc hủy stage dừng I/O server.

## 5. Giới hạn trong Reactor và Reactive Spring Data Cassandra

### 5.1. Giới hạn `flatMap` cho một chuỗi

Với `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate`, một cách dễ áp dụng là dùng tham số `concurrency` của `Flux.flatMap`:

~~~java
import java.util.UUID;
import reactor.core.publisher.Flux;

// Giả sử repository.findById(UUID) trả về Mono<OrderById>.
Flux<OrderById> loadOrders(Flux<UUID> orderIds,
                          OrderReactiveRepository repository) {
    int maxConcurrent = 16;
    int prefetch = 1;
    return orderIds.flatMap(
        id -> repository.findById(id),
        maxConcurrent,
        prefetch
    );
}
~~~

Trong ví dụ, `flatMap` duy trì tối đa 16 **inner publishers** đang hoạt động cho **một subscription**. Đây là một giới hạn hữu ích khi service đọc danh sách ID, nhưng **không phải giới hạn toàn cục**: nếu 100 request HTTP cùng subscribe vào luồng trên, ứng dụng vẫn có thể tạo rất nhiều truy vấn song song. `prefetch` điều chỉnh demand tới từng inner publisher; nó không phải bộ giới hạn kết nối hay độ lớn trang CQL.

Ngoài ra, `flatMap` có thể phát kết quả theo thứ tự **hoàn tất** thay vì thứ tự input. Khi nghiệp vụ bắt buộc giữ nguyên thứ tự, cân nhắc `flatMapSequential` hoặc `concatMap`, đồng thời đo trade-off giữa độ trễ và throughput. Không cố tăng `parallel()` để chữa timeout khi nút thắt nằm ở replica.

### 5.2. Bulkhead dùng chung ở service reactive

Để giới hạn đồng thời trên **mọi subscription cùng đi qua một instance service**, có thể tạo một limiter sống như singleton Spring bean. `Mono.defer` bảo đảm permit chỉ được xin ở thời điểm có subscription, không phải lúc mã xây dựng pipeline:

~~~java
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;
import reactor.core.publisher.Mono;

final class ReactiveInFlightLimiter {
    private final Semaphore permits;

    ReactiveInFlightLimiter(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight);
    }

    <T> Mono<T> execute(Supplier<Mono<T>> operation) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new InFlightLimitExceededException());
            }
            return Mono.defer(operation)
                .doFinally(signal -> permits.release());
        });
    }
}
~~~

Sử dụng trong service:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;

final class ReactiveOrderReader {
    private final OrderReactiveRepository repository;
    private final ReactiveInFlightLimiter limiter;

    ReactiveOrderReader(OrderReactiveRepository repository,
                        ReactiveInFlightLimiter limiter) {
        this.repository = repository;
        this.limiter = limiter;
    }

    Mono<OrderById> find(UUID orderId) {
        return limiter.execute(() -> repository.findById(orderId));
    }
}
~~~

Giả định `OrderReactiveRepository` là interface kế thừa `ReactiveCassandraRepository<OrderById, UUID>`, entity `OrderById` được ánh xạ tới bảng có partition key `order_id`. Trong ứng dụng Spring thực tế, cấu hình `ReactiveInFlightLimiter` thành **bean dùng chung** với hạn mức từ cấu hình; không tạo limiter mới trong mỗi HTTP request vì như vậy mỗi request sẽ có quota riêng và không bảo vệ hệ thống.

`doFinally` được gọi khi luồng kết thúc thành công, gặp lỗi hoặc bị cancel. Đây là lựa chọn phù hợp để tránh rò permit trong mã reactive, nhưng cần hiểu giới hạn: khi cancellation ở Reactor xảy ra trước lúc driver/server xử lý xong, permit có thể được trả sớm hơn thời điểm tài nguyên ở Cassandra thực sự rảnh. Vì vậy **driver throttler vẫn là hàng rào hữu ích** để bảo vệ các request do driver nhìn thấy.

### 5.3. Backpressure không tự giới hạn mọi truy vấn CQL

`StepVerifier` hoặc subscriber dùng `request(1)` để yêu cầu một phần tử từ publisher. Điều đó điều tiết tín hiệu `onNext`, nhưng không bảo đảm cứ một `request(1)` là Cassandra chỉ đọc đúng một hàng hay chỉ phát một network request. Driver có thể fetch theo page, buffering và các cơ chế prefetch riêng.

Với truy vấn nhiều hàng, chọn `pageSize`/fetch size và số truy vấn đồng thời phù hợp:

- **Page size nhỏ**: giảm bộ nhớ và kích thước mỗi trang, nhưng có thể tăng round-trip nếu có nhiều hàng.
- **Page size lớn**: giảm số lần lấy trang nhưng tăng chi phí mỗi page và bộ nhớ khi nhiều truy vấn cùng hoạt động.
- **Đồng thời quá lớn × page size lớn**: có thể tạo đỉnh bộ nhớ/traffic cao dù subscriber xử lý chậm.

Vì thế kiểm thử backpressure ở `Flux` mock chỉ kiểm tra hợp đồng publisher; muốn chứng minh số lần fetch, bộ nhớ hoặc latency với Cassandra thật, cần metric và kiểm thử tích hợp.

## 6. Điều tiết request và thiết kế dữ liệu theo truy vấn

Request limiter bảo vệ tốc độ đưa công việc vào hệ thống, nhưng không sửa được một câu CQL quá tốn kém. Với Cassandra, hiệu năng chịu ảnh hưởng mạnh của **thiết kế partition key**, clustering columns, kích thước partition và pattern đọc/ghi.

| Hiện tượng | Vì sao limiter đơn lẻ chưa đủ? | Việc cần sửa đồng thời |
| --- | --- | --- |
| Mọi request dồn vào một partition key | Một nhóm replica xử lý nhiều request hơn các nhóm khác. | Phân phối lại mô hình khóa/partition theo yêu cầu truy vấn; xem xét bucket khi đúng với nghiệp vụ. |
| Truy vấn đọc quá nhiều hàng/tombstone | Mỗi request tốn CPU, I/O và thời gian. | Thiết kế lại bảng theo access pattern, kiểm soát TTL/tombstone, paging và phạm vi query. |
| Ghi hàng loạt lớn | Một request có thể chứa nhiều mutation và ảnh hưởng nhiều partition. | Chia workload hợp lý; tránh dùng batch làm công cụ tăng throughput tùy tiện. |
| CL đặt cao hơn khả năng cụm đáp ứng | Chờ replica lâu hoặc gặp `Unavailable`/timeout. | Kiểm tra RF, datacenter, trạng thái replica và yêu cầu nhất quán của nghiệp vụ. |
| Retry dồn dập khi timeout | Tăng số request thực tế trong lúc cluster suy giảm. | Retry có giới hạn, backoff có jitter và ngân sách tổng số lần thử. |
| Một endpoint nặng chiếm hết quota chung | Truy vấn nhẹ cũng bị đói tài nguyên. | Tách quota/bulkhead theo loại truy vấn khi có đủ bằng chứng đo lường. |

Ví dụ nếu một màn hình cần đọc chi tiết đơn hàng theo `order_id`, bảng `orders_by_id` với `order_id` là partition key sẽ phù hợp. Không dùng `ALLOW FILTERING` để quét bảng rồi hy vọng giảm concurrency giải quyết hoàn toàn vấn đề.

### Đừng đánh đổi tính nhất quán để tăng throughput một cách mù quáng

`LOCAL_QUORUM` với RF = 3 trong một datacenter cần hai replica đáp ứng. `LOCAL_ONE` cần một replica. Khi đổi CL, đặc tính đọc/ghi và độ tin cậy khi có node lỗi cũng thay đổi. Trước khi giảm CL vì timeout, cần xác định sản phẩm có chấp nhận các thay đổi về nhất quán hay không; limiter phải được hiệu chỉnh **trên CL mà nghiệp vụ thực sự yêu cầu**.

## 7. Phối hợp limiter, timeout, retry và xử lý quá tải

Một thiết kế chịu tải tốt cần trả lời cả bốn câu hỏi:

1. **Có còn chỗ chạy không?** Nếu không, request được từ chối hay chờ tối đa bao lâu?
2. **Còn đủ thời gian không?** Nếu deadline đã sắp hết, chờ queue thường vô ích.
3. **Thao tác có thể retry an toàn không?** Đọc theo khóa thường có thể retry có giới hạn; ghi không idempotent cần tránh retry mù.
4. **Ai chịu trách nhiệm retry?** Driver, service, HTTP client hay message consumer? Không nên để nhiều tầng lặp vô hạn.

~~~mermaid
flowchart TD
    A["Request đến service"] --> B{"Còn ngân sách deadline?"}
    B -- "Không" --> X["Trả lỗi timeout/deadline"]
    B -- "Có" --> C{"Limiter còn permit?"}
    C -- "Không" --> D["Từ chối sớm / queue hữu hạn"]
    C -- "Có" --> E["Gửi CQL tới driver"]
    E --> F{"Kết quả"}
    F -- "Thành công" --> G["Trả dữ liệu, giải phóng permit"]
    F -- "Lỗi tạm thời" --> H{"An toàn để retry và còn budget?"}
    H -- "Có" --> I["Backoff + jitter rồi thử lại"]
    I --> B
    H -- "Không" --> J["Báo lỗi có ngữ cảnh"]
    F -- "WriteTimeout" --> K["Đối soát trạng thái ghi chưa xác định"]
~~~

Sơ đồ chỉ mô tả nguyên tắc. Với implementation cụ thể, permit thường phải được trả đúng lúc stage/publisher kết thúc; retry có thể giữ một permit cho cả chuỗi hoặc xin lại permit cho mỗi attempt. Cần chọn cách đếm rõ ràng, tránh tính thiếu các request đang thực sự chạy.

### Phân loại lỗi

- **`RequestThrottlingException` / lỗi bulkhead ứng dụng:** không nhận thêm request do giới hạn phía client. Trả HTTP **503 Service Unavailable** khi hạ tầng tạm quá tải; HTTP **429 Too Many Requests** thích hợp hơn với quota/rate limit dành cho một client cụ thể. Giao thức nội bộ có thể dùng mã lỗi khác.
- **`OverloadedException`:** coordinator Cassandra từ chối vì quá tải. Hạn chế retry ngay; giảm concurrency và kiểm tra cluster.
- **`ReadTimeoutException` / `UnavailableException`:** có thể retry phép đọc an toàn với số lần hữu hạn và còn deadline, nhưng phải điều tra CL, replica và latency.
- **`WriteTimeoutException`:** kết quả ghi **chưa xác định**; một hoặc nhiều replica có thể đã ghi. Chỉ retry khi thao tác đã được thiết kế idempotent và có cơ chế đối soát phù hợp.
- **`DriverTimeoutException`:** deadline request phía driver hết; phân biệt với timeout phát ra từ server và thời gian chờ queue.

**Không dùng retry để vượt limiter.** Nếu caller nhận lỗi quota rồi retry tức thì theo vòng lặp, request bị từ chối sẽ quay lại hàng loạt và tiêu thụ CPU/network. Nếu hệ thống trả `Retry-After`, giá trị phải có cơ sở từ chính sách admission hoặc trạng thái hệ thống, không tự hứa thời điểm phục hồi khi chưa biết.

### Ngân sách retry qua nhiều tầng

Giả sử HTTP client thử tối đa 3 lần, service thử tối đa 2 lần và driver có thể thử thêm 2 lần, trong tình huống xấu có thể phát sinh tới **3 × 2 × 2 = 12 lượt xử lý** cho một hành động ban đầu. Tất cả lượt thử đó cạnh tranh cùng giới hạn tài nguyên. Hãy ưu tiên một tầng làm đầu mối kiểm soát retry, đếm tổng số attempt, theo dõi deadline chung và dừng khi cluster đã quá tải rõ rệt.

## 8. Kiểm thử limiter và quan sát hiệu năng

### 8.1. Unit test cho limiter bất đồng bộ

Test tốt không dựa vào `Thread.sleep()`. Với limiter cho `CompletionStage`, có thể giữ request đầu tiên ở trạng thái pending, xác minh request thứ hai bị từ chối, rồi hoàn tất request đầu và kiểm tra permit được tái sử dụng:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AsyncInFlightLimiterTest {
    @Test
    void rejectsWhenFullAndReleasesAfterCompletion() {
        AsyncInFlightLimiter limiter = new AsyncInFlightLimiter(1);
        CompletableFuture<String> firstReply = new CompletableFuture<>();

        var first = limiter.execute(() -> firstReply);
        var rejected = limiter.execute(
            () -> CompletableFuture.completedFuture("SECOND"));

        CompletionException error = assertThrows(
            CompletionException.class,
            () -> rejected.toCompletableFuture().join());
        assertInstanceOf(InFlightLimitExceededException.class,
            error.getCause());

        firstReply.complete("FIRST");
        assertEquals("FIRST", first.toCompletableFuture().join());

        var next = limiter.execute(
            () -> CompletableFuture.completedFuture("THIRD"));
        assertEquals("THIRD", next.toCompletableFuture().join());
    }
}
~~~

Nên có thêm test **supplier ném exception trước khi tạo stage**, **future hoàn tất bất thường**, **cạnh tranh nhiều luồng** và **request bị timeout/cancel** theo hợp đồng riêng. Test phải chứng minh không rò permit và số request nguồn active không vượt quota; không chỉ assert exception message.

### 8.2. StepVerifier cho bulkhead reactive

Với Reactor, kiểm tra tính an toàn khi một subscription đang chiếm permit và subscriber bị hủy:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveInFlightLimiterTest {
    @Test
    void cancelledSubscriptionReleasesPermit() {
        ReactiveInFlightLimiter limiter = new ReactiveInFlightLimiter(1);

        Disposable active = limiter.execute(Mono::<String>never)
            .subscribe();
        try {
            StepVerifier.create(
                    limiter.execute(() -> Mono.just("SECOND")))
                .expectError(InFlightLimitExceededException.class)
                .verify(Duration.ofSeconds(2));
        } finally {
            active.dispose();
        }

        StepVerifier.create(
                limiter.execute(() -> Mono.just("THIRD")))
            .expectNext("THIRD")
            .verifyComplete();
    }
}
~~~

Ở ví dụ trên, toán tử `Mono.never()` giữ subscription đầu chưa hoàn tất và `dispose()` kích hoạt `doFinally(CANCEL)`, qua đó trả permit. Điều này **chỉ kiểm tra limiter trong Reactor**; chưa chứng minh việc hủy CQL tại Cassandra thật.

### 8.3. Đo lường và cảnh báo

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Số request **in-flight** hiện tại và tỷ lệ sử dụng permit | Có thường xuyên chạm giới hạn không? |
| Kích thước queue, thời gian chờ queue (p50/p95/p99) | Hàng đợi có tiêu tốn phần lớn deadline không? |
| Số request bị từ chối bởi client limiter/driver throttler | Có đang thiếu admission capacity hoặc bị burst quá lớn? |
| Throughput thành công theo loại truy vấn/table | Tăng giới hạn có làm nhiều việc hơn hoàn tất không? |
| End-to-end latency và latency Cassandra (p95/p99) | Thời gian tăng ở queue, driver hay server? |
| Timeout, `Unavailable`, `Overloaded`, retry attempt | Cluster suy giảm hay retry đang khuếch đại quá tải? |
| GC, CPU, heap, connection pool, pending tasks, dropped messages | Nút thắt nằm ở JVM/client hay node Cassandra? |
| Partition size, tombstone, số row/page, hot partition | Có truy vấn hoặc phân phối dữ liệu bất hợp lý không? |

Trong Java Driver, cần kích hoạt những metric phù hợp với phiên bản đang dùng; với Spring Boot có thể dùng Micrometer/Actuator để quan sát metric ứng dụng. **Không ghi partition key nhạy cảm hoặc một nhãn theo từng order ID** vào metric: cardinality lớn làm hệ thống quan sát quá tải. Dùng các nhãn hữu hạn như loại operation, keyspace, table và error class.

### 8.4. Thử nghiệm tải có phương pháp

Một vòng tuning có thể thực hiện như sau:

1. **Cố định workload:** tỷ lệ đọc/ghi, partition key distribution, kích thước hàng, page size, CL, RF, số client và deadline. Tạo dữ liệu thử nghiệm đủ phản ánh partition lớn/hotspot nếu có.
2. **Đo baseline:** throughput thành công, latency p50/p95/p99, timeout và tài nguyên khi chưa tới điểm bão hòa; không lấy CPU trung bình làm chỉ số duy nhất.
3. **Tăng tải có kiểm soát:** giữ nguyên workload, tăng lưu lượng đầu vào; quan sát điểm throughput không tăng tương xứng nhưng latency/timeout/queue bắt đầu tăng mạnh.
4. **Thử các mức concurrency:** ví dụ 16, 32, 64, 96; mỗi mức có cùng cách tạo tải. Giá trị là ví dụ, không phải cấu hình mặc định.
5. **Chọn quota có khoảng dự phòng:** ưu tiên mức đáp ứng SLO khi có burst hoặc một replica chậm, không chọn mức tạo throughput cao nhất trong điều kiện lý tưởng.
6. **Kiểm tra từ chối và phục hồi:** khi hết chỗ, request phải bị từ chối hoặc chờ trong queue hữu hạn; sau khi giảm tải, queue, latency và error rate phải trở về mức bình thường.
7. **Đo trên nhiều instance:** tổng quota phải phù hợp năng lực cluster và những consumer khác cũng đang dùng keyspace.

Kiểm thử tải mạnh hoặc mô phỏng replica lỗi cần thực hiện ở môi trường được phép và cách ly. Trên production, triển khai thay đổi quota theo từng phần nhỏ kèm metric và khả năng rollback cấu hình.

## 9. Tình huống thực hành: API đọc đơn hàng tăng tải

**Bối cảnh:** hệ thống lưu `orders_by_id(order_id uuid PRIMARY KEY, state text)`, truy cập qua Spring Data Cassandra tại `LOCAL_QUORUM`. Sau một chiến dịch khuyến mại, API có đợt tăng traffic; nhiều người dùng đồng thời tải trạng thái đơn hàng.

Quan sát ban đầu (số liệu giả định để minh họa):

| Chỉ số | Trước đợt tăng tải | Lúc quá tải |
| --- | ---: | ---: |
| Throughput hoàn tất | 350 request/giây | 360 request/giây |
| Request đồng thời (in-flight) | 30 | 250 |
| Latency p99 | 140 ms | 2.800 ms |
| Timeout | Thấp | Tăng nhanh |

Từ số liệu minh họa, throughput gần như không tăng trong khi in-flight và p99 tăng rất mạnh. Đây là dấu hiệu cần **đo admission và nút thắt**, chứ không nên lập tức tăng số request song song.

Một hướng xử lý có thể là giới hạn ở service/driver, dùng queue hữu hạn và từ chối request dư thừa với HTTP 503 theo hợp đồng API, đồng thời kiểm tra latency từng truy vấn, hot partition, CPU/I/O trên replica và retry rate. Sau đó chạy lại cùng workload để so throughput thành công, p95/p99 và tỷ lệ lỗi. Nếu có thêm retry từ phía HTTP client, cần kiểm tra chúng tuân thủ backoff và deadline.

Để đánh giá **thành công**, không chỉ nhìn việc in-flight giảm: throughput các request hoàn tất cần phù hợp mục tiêu, p99 không vượt SLO và lỗi từ chối phải được client xử lý đúng. Nếu quota quá thấp, hệ thống có thể ổn định về độ trễ nhưng từ chối phần lớn yêu cầu dù database vẫn còn dư năng lực.

## 10. Ghi nhớ

- **Giới hạn đồng thời** kiểm soát số request đang chạy; **rate limit** kiểm soát tốc độ tiếp nhận; **bounded queue** hấp thụ burst ngắn; **backpressure** điều tiết tín hiệu trong publisher. Chúng giải quyết các vấn đề khác nhau.
- Java Driver có **request throttler** để giới hạn request đi qua session. `ConcurrencyLimitingRequestThrottler` kết hợp số request đang chạy và queue hữu hạn; cần nhận diện riêng `RequestThrottlingException` với `OverloadedException` của Cassandra.
- Trong Reactor, `flatMap(..., concurrency)` giới hạn **một subscription**; singleton bulkhead với `Mono.defer` và `doFinally` bảo vệ nhiều subscription cùng đi qua service.
- Deadline, retry và queue phải được tính **cùng nhau**. Retry lặp ngay, queue quá dài hoặc tăng timeout mù quáng có thể biến quá tải thành sự cố lan rộng.
- Thiết kế **partition key theo truy vấn**, paging phù hợp, consistency level và kiểm soát hot partition quyết định sức khỏe Cassandra. Limiter bảo vệ hệ thống trong lúc xử lý áp lực, không thay thế việc thiết kế bảng/truy vấn hiệu quả.
- Chọn hạn mức dựa trên **load test và SLO**: throughput thành công, p95/p99, queue wait, tỷ lệ từ chối, timeout và tài nguyên của cả client lẫn replica.

### Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.x — Request throttling](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/throttling/).
- [Spring Data Cassandra — Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/).
- [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/).
- [Project Reactor — Flux API, flatMap](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/).
