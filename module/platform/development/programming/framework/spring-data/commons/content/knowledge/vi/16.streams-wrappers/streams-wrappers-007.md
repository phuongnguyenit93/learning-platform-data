# Phân biệt Java Stream, bất đồng bộ với @Async và Reactive Streams

Một repository có thể trả về `Stream<Order>`, `CompletableFuture<List<Order>>` hoặc `Flux<Order>`. Cả ba đều có thể xuất hiện trong mã đọc dữ liệu, nhưng chúng không biểu diễn cùng một cơ chế thực thi.

`Stream` mô tả một chuỗi thao tác duyệt dữ liệu. `@Async` yêu cầu Spring chuyển lời gọi được hỗ trợ sang executor. Reactive Streams định nghĩa giao thức trao đổi nhiều phần tử với tín hiệu nhu cầu, lỗi và hoàn tất. Chỉ nhìn thấy các từ “stream”, “async” hoặc “reactive” chưa đủ để kết luận truy vấn không chặn, chạy song song hay tiết kiệm bộ nhớ.

Trong phạm vi Spring Data Commons, bài học tập trung vào hợp đồng kiểu trả về và cách sử dụng repository. Khả năng truy xuất cụ thể còn phụ thuộc module như Spring Data JPA, R2DBC hoặc MongoDB, driver và phiên bản dự án. Không thể thay kiểu trả về tùy ý rồi mong mọi kho dữ liệu thực thi giống nhau.

Sau bài học, bạn có thể:

- Phân biệt duyệt lười, chạy bất đồng bộ, chạy song song và I/O không chặn.
- Chọn kiểu trả về theo số lượng kết quả và cách bên gọi tiếp nhận chúng.
- Đóng đúng tài nguyên khi repository trả Java `Stream`.
- Nhận biết truy vấn blocking vẫn tồn tại phía sau `@Async`.
- Giải thích backpressure và giới hạn của việc đổi wrapper sang `Flux` hoặc `Mono`.
- Đặt transaction, xử lý lỗi và giới hạn tải đúng theo mô hình thực thi.

## 1. Bốn câu hỏi cần tách riêng

Khi đọc một chữ ký repository, nên đặt bốn câu hỏi:

1. **Kết quả có hình dạng nào?** Một phần tử, một danh sách, một luồng nhiều phần tử hay một kết quả sẽ có trong tương lai?
2. **Khi nào công việc bắt đầu?** Khi gọi phương thức, khi thực hiện terminal operation hay khi có subscription?
3. **Ai thực hiện công việc?** Thread gọi, một worker của executor hay thread do nguồn và scheduler phối hợp?
4. **Khi phải đợi I/O, thread có bị giữ lại không?** Câu trả lời phụ thuộc driver và chuỗi xử lý thực tế.

Các khái niệm tương ứng không đồng nghĩa với nhau:

| Khái niệm | Ý nghĩa | Điều chưa thể suy ra |
|---|---|---|
| Lazy | Trì hoãn một phần công việc đến lúc cần | Không bảo đảm chạy ở thread khác |
| Asynchronous | Bên gọi có thể nhận quyền điều khiển trước khi công việc hoàn tất | Không bảo đảm I/O không chặn |
| Parallel | Có nhiều phần việc thực hiện đồng thời | Không bảo đảm phù hợp với tài nguyên database |
| Non-blocking I/O | Không giữ một thread chỉ để đợi mỗi thao tác I/O hoàn tất | Không bảo đảm toàn bộ ứng dụng không có đoạn blocking |
| Backpressure | Bên nhận có thể báo nhu cầu để điều phối việc phát phần tử | Không thay thế giới hạn truy vấn hay mọi giới hạn bộ nhớ |

Một Java Stream có thể lazy mà vẫn chạy đồng bộ. Một truy vấn `@Async` có thể trả future ngay nhưng giữ một worker chờ JDBC. Một `Flux` cũng có thể phát đồng bộ trên thread đăng ký nếu nguồn không có ranh giới bất đồng bộ.

## 2. So sánh tổng thể ba mô hình

| Tiêu chí | Java `Stream<T>` | `@Async` và `CompletableFuture<T>` | Reactive Streams, thường qua `Flux<T>` hoặc `Mono<T>` |
|---|---|---|---|
| Vai trò chính | Pipeline duyệt và biến đổi nhiều phần tử | Đại diện kết quả hoàn tất sau khi công việc được giao đi | Giao thức phát phần tử theo nhu cầu và tín hiệu vòng đời |
| Hình dạng kết quả | Nhiều phần tử qua terminal operation | Một lần hoàn tất với một giá trị hoặc một lỗi | `Mono`: 0 hoặc 1; `Flux`: 0 đến nhiều phần tử |
| Cơ chế bắt đầu | Pipeline lazy; repository có thể mở tài nguyên trước khi duyệt | Sau khi lời gọi qua proxy được executor tiếp nhận | Nguồn truy vấn reactive thường bắt đầu khi có subscription |
| Thread | Thường là thread gọi khi dùng stream tuần tự | Worker của executor đã cấu hình | Do nguồn, driver và scheduler quyết định |
| I/O database | Có thể blocking, ví dụ JPA/JDBC | Vẫn có thể blocking ở worker | Có thể không chặn khi module và driver hỗ trợ thực sự |
| Backpressure chuẩn Reactive Streams | Không | Không | Có giao thức `request(n)` giữa các thành phần |
| Tài nguyên | Cần đóng stream nếu gắn với tài nguyên | Quản lý trong công việc thực thi; future không thay việc đóng tài nguyên | Hạ tầng nguồn quản lý theo subscription, hoàn tất, lỗi và hủy |
| Transaction | Thường là transaction imperative bao quanh việc tiêu thụ | Cần xác định transaction ở thread thực hiện công việc | Dùng transaction manager reactive và ngữ cảnh của pipeline |
| Cách báo lỗi | Thường ném exception tại lời gọi hoặc lúc duyệt | Future hoàn tất exceptionally; cũng có thể lỗi khi giao việc | Tín hiệu `onError` trong subscription, cộng lỗi có thể xảy ra khi dựng pipeline |

`CompletableFuture<List<Order>>` là một kết quả tương lai chứa cả danh sách. Nó không phải một chuỗi phát từng `Order` với nhu cầu riêng cho từng phần tử.

Reactive Streams là đặc tả giao thức, còn Reactor là một thư viện triển khai với các kiểu `Mono` và `Flux`. Java `Stream` thuộc Java API khác, dù cùng dùng từ “stream”.

## 3. Java Stream: pipeline duyệt dữ liệu, không tự chuyển thread

### 3.1. Lazy ở các thao tác trung gian

Một pipeline Java thông thường:

```java
var names = users.stream()
    .filter(User::isActive)
    .map(User::getName);
```

Các thao tác `filter` và `map` chưa duyệt dữ liệu chỉ vì pipeline đã được khai báo. Một terminal operation như `forEach`, `collect` hoặc `toList` sẽ kích hoạt việc tiêu thụ tương ứng.

Tuy nhiên, với repository, không nên suy rằng kết nối và truy vấn chỉ bắt đầu tại terminal operation. Lời gọi repository có thể đã tạo truy vấn, lấy cursor hoặc chuẩn bị tài nguyên trước khi trả stream. Thời điểm chính xác phụ thuộc module và driver.

### 3.2. Repository trả Stream không cam kết fetch từng dòng từ server

Một module có thể dùng cursor hoặc cơ chế stream của driver. Driver cũng có thể buffer dữ liệu, hoặc một cấu hình fetch không phù hợp có thể làm tải nhiều dữ liệu hơn dự kiến.

Vì vậy:

- Kiểu `Stream<T>` không tự bảo đảm bộ nhớ hằng số.
- `stream.limit(100)` không phải cam kết truy vấn được sinh với giới hạn 100 dòng ở database.
- `stream.filter(...)` là phép lọc của Java, không tự biến thành điều kiện truy vấn.
- `stream.sorted(...)` có thể cần giữ nhiều phần tử trong bộ nhớ.

Nếu biết điều kiện lọc, thứ tự và giới hạn từ đầu, nên biểu diễn chúng ở truy vấn repository khi phù hợp. Sau đó dùng Stream cho phần xử lý cần diễn ra trong ứng dụng.

### 3.3. Ví dụ Spring Data JPA với transaction và đóng tài nguyên

Ví dụ giả định `PurchaseOrder` là entity JPA đã được ánh xạ, có các thuộc tính `id`, `tenantId`, `status`. Các đoạn ví dụ trong bài minh họa từng module độc lập; một entity JPA không tự trở thành mapping R2DBC chỉ bằng cách đổi interface repository.

```java
import java.util.stream.Stream;
import org.springframework.data.repository.Repository;

public interface OrderStreamRepository
        extends Repository<PurchaseOrder, Long> {

    Stream<PurchaseOrder>
    findByTenantIdAndStatusOrderByIdAsc(
        String tenantId,
        String status
    );
}
```

Tiêu thụ trong một service được gọi qua Spring proxy:

```java
import java.util.function.Consumer;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderExportService {
    private final OrderStreamRepository repository;

    public OrderExportService(OrderStreamRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public void export(
            String tenantId,
            String status,
            Consumer<PurchaseOrder> writeRow) {

        try (Stream<PurchaseOrder> orders = repository
                .findByTenantIdAndStatusOrderByIdAsc(
                    tenantId, status)) {

            orders.forEach(writeRow);
        }
    }
}
```

Điểm quan trọng trong ví dụ:

- Stream được tiêu thụ khi transaction của service còn hiệu lực.
- `try-with-resources` gọi `close()` cả khi xử lý thành công lẫn khi có lỗi.
- `writeRow` xử lý đồng bộ trong phạm vi lời gọi này.
- Service trả về sau khi việc duyệt kết thúc; đây chưa phải bất đồng bộ.

`readOnly = true` không có nghĩa truy vấn không chặn hoặc database tự tạo snapshot theo mọi cấu hình. Nó cũng không tự giới hạn thời gian giữ kết nối.

Nếu `writeRow` thực hiện công việc chậm, kết nối và transaction có thể tồn tại lâu. Nếu persistence context giữ nhiều entity đã đọc, bộ nhớ vẫn có thể tăng. Với job dài, cần đánh giá fetch, vòng đời entity hoặc chuyển sang đọc theo batch/window phù hợp.

### 3.4. Không trả Stream ra khỏi phạm vi đã đóng

Mẫu sau sai về vòng đời tài nguyên:

```java
public Stream<PurchaseOrder> broken(String tenantId, String status) {
    try (Stream<PurchaseOrder> orders = repository
            .findByTenantIdAndStatusOrderByIdAsc(tenantId, status)) {
        return orders;
    }
}
```

Stream đã bị đóng trước khi bên gọi tiêu thụ. Một mẫu khác cũng dễ lỗi là trả stream ra khỏi service transaction rồi mới duyệt ở controller.

Cần xác định rõ bên nào sở hữu và đóng stream. Tiêu thụ trong cùng phạm vi mở tài nguyên thường dễ kiểm soát hơn so với chuyển stream qua nhiều tầng.

### 3.5. `parallel()` không biến JDBC thành I/O không chặn

`parallel()` yêu cầu Java Stream thực hiện pipeline theo cơ chế song song khi có thể. Nó không thay JDBC driver, không tạo reactive repository và không làm `EntityManager` an toàn để dùng đồng thời từ nhiều thread.

Không dùng parallel stream như cách mặc định để tăng tốc stream từ JPA. Việc chia việc phải tính đến khả năng chia nguồn, transaction, tài nguyên và tính an toàn của từng thao tác.

Một tập DTO đã được materialize, có kích thước kiểm soát và chỉ xử lý CPU độc lập là bài toán khác. Khi đó vẫn cần đo xem lợi ích có vượt overhead hay không.

## 4. @Async: chuyển công việc sang executor, trả một kết quả tương lai

### 4.1. Mô hình thực thi

Với phương thức async được hỗ trợ và lời gọi đi qua proxy:

```text
Thread gọi
  → Spring proxy
  → giao task cho executor
  → nhận CompletableFuture

Worker của executor
  → thực hiện truy vấn
  → chờ I/O nếu driver blocking
  → hoàn tất future bằng kết quả hoặc lỗi
```

Sự thay đổi nằm ở vị trí thread phải chờ. Bên gọi không cần đứng chờ toàn bộ truy vấn, nhưng một worker vẫn có thể bị giữ lại trong thời gian chờ database.

### 4.2. Cấu hình executor minh họa

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "repositoryExecutor")
    public ThreadPoolTaskExecutor repositoryExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("repository-");
        return executor;
    }
}
```

Bean này được Spring quản lý vòng đời. Các giá trị pool và queue chỉ là ví dụ; phải chọn theo tải, thời gian truy vấn, connection pool và giới hạn của hệ thống.

Queue hữu hạn giúp biểu diễn giới hạn nhận việc, nhưng vẫn cần chính sách khi hết khả năng tiếp nhận. Không thể tăng vô hạn số request đang chờ rồi coi đó là khả năng xử lý đồng thời.

### 4.3. Async repository vẫn có thể dùng JPA blocking

Giả sử module JPA đang dùng hỗ trợ async query và interface projection sau:

```java
import java.math.BigDecimal;

public interface OrderSummaryView {
    Long getId();
    BigDecimal getTotalAmount();
}
```

Repository minh họa:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.data.repository.Repository;
import org.springframework.scheduling.annotation.Async;

public interface OrderAsyncRepository
        extends Repository<PurchaseOrder, Long> {

    @Async("repositoryExecutor")
    CompletableFuture<List<OrderSummaryView>>
    findFirst100ByTenantIdAndStatusOrderByIdAsc(
        String tenantId,
        String status
    );
}
```

Chữ ký mô tả một future chứa danh sách tối đa 100 phần tử theo derived query. Giới hạn đến từ `First100`, không đến từ `CompletableFuture`.

Trong mô hình này, JPA/JDBC vẫn có thể chặn worker trong thời gian thực thi. Async query không đồng nghĩa với reactive query. Transaction và cách tải dữ liệu của phương thức vẫn cần được cấu hình theo nhu cầu; annotation `@Async` không tự bổ sung một transaction nghiệp vụ.

### 4.4. Lấy kết quả và xử lý lỗi

```java
CompletableFuture<List<OrderSummaryView>> future = repository
    .findFirst100ByTenantIdAndStatusOrderByIdAsc(tenantId, status);

future.whenComplete((orders, failure) -> {
    if (failure != null) {
        reportFailure(failure);
    } else {
        display(orders);
    }
});
```

`reportFailure` và `display` là thao tác ứng dụng tự định nghĩa. Callback ở ví dụ nên ngắn; không mặc định nó chạy trên thread giao diện hoặc một executor riêng.

Các điểm cần hiểu:

- `join()` hoặc `get()` có thể chặn thread gọi nếu future chưa hoàn tất.
- Gọi `join()` ngay sau mỗi lời gọi có thể làm mất lợi ích đối với bên gọi đó.
- Callback không có hậu tố `Async` có thể chạy trên thread hoàn tất future, hoặc ngay tại thread đăng ký nếu future đã hoàn tất.
- Lỗi truy vấn có thể làm future hoàn tất exceptionally.
- Lỗi khi giao task hoặc đối số không hợp lệ cũng có thể xuất hiện trước khi có một future để xử lý.

Một handler quan sát lỗi như `whenComplete` không mặc nhiên biến kết quả thất bại thành thành công. Nếu dùng cơ chế trả giá trị thay thế, phải cân nhắc ý nghĩa nghiệp vụ; danh sách rỗng có thể có ý nghĩa khác với truy vấn thất bại.

### 4.5. Proxy và transaction là hai ranh giới cần hiểu

Trong chế độ proxy thông thường, một phương thức gọi nội bộ phương thức `@Async` trên cùng đối tượng có thể bỏ qua proxy, nên không được chuyển sang executor như mong đợi. Tương tự, không đánh giá hành vi async bằng cách tự `new` một service vốn cần Spring quản lý.

Transaction imperative đang gắn với thread gọi không tự được truyền sang worker async. Nếu công việc async cần transaction, hãy thiết kế transaction trong phần công việc chạy ở worker.

Một cách tổ chức rõ ràng là:

```text
Bean A: phương thức @Async nhận request
    ↓ chạy trong worker
Bean B: phương thức @Transactional tải và xử lý dữ liệu
    ↓ hoàn tất bên trong worker
Bean A: hoàn tất future bằng DTO/kết quả đã chuẩn bị
```

Cách tách này cũng làm ranh giới proxy dễ nhận biết. Không nên giả định một entity được trả qua future vẫn giữ sẵn môi trường để tải lazy ở bất kỳ thread nào sau đó.

### 4.6. Future chứa Stream thường làm vòng đời phức tạp hơn

`CompletableFuture<Stream<T>>` không tự giải quyết được việc tài nguyên thuộc thread và transaction nào, ai đóng stream và lúc nào bên gọi bắt đầu duyệt.

Một worker có thể hoàn tất future và kết thúc transaction trước khi bên gọi tiêu thụ stream. Khi đó, việc truy cập dữ liệu có thể diễn ra sau khi tài nguyên cần thiết đã hết hiệu lực.

Nếu cần một kết quả hữu hạn, có thể materialize DTO trong phạm vi transaction của worker với kích thước kiểm soát. Nếu cần xử lý nhiều dữ liệu, cân nhắc batch, window hoặc cơ chế streaming được hỗ trợ với vòng đời rõ ràng.

## 5. Reactive Streams: giao thức phát phần tử theo nhu cầu

### 5.1. Các thành phần và tín hiệu chính

Giao thức Reactive Streams có các vai trò như `Publisher`, `Subscriber` và `Subscription`:

```text
Subscriber đăng ký với Publisher
    ↓
onSubscribe(subscription)
    ↓
Subscriber gọi request(n), với n > 0
    ↓
Publisher phát onNext(...) trong giới hạn nhu cầu đã được cấp
    ↓
onComplete() hoặc onError(...)
```

Subscriber có thể gọi `request` nhiều lần để bổ sung nhu cầu. Nó cũng có thể gọi `cancel()` để báo không còn cần dữ liệu.

`onComplete` và `onError` là tín hiệu kết thúc thay thế nhau cho một subscription; sau khi kết thúc, không tiếp tục phát dữ liệu bình thường trong subscription đó.

Cơ chế này khác với một future: future biểu diễn một lần hoàn tất, còn publisher có thể biểu diễn một chuỗi nhiều giá trị được điều phối bằng nhu cầu.

### 5.2. Reactor cung cấp Mono và Flux

- `Mono<T>` biểu diễn khả năng phát 0 hoặc 1 giá trị rồi hoàn tất, hoặc kết thúc bằng lỗi.
- `Flux<T>` biểu diễn khả năng phát 0 đến nhiều giá trị rồi hoàn tất, hoặc kết thúc bằng lỗi; một số nguồn có thể không kết thúc.
- `Mono<List<T>>` vẫn là một lần phát chứa cả danh sách, khác với `Flux<T>` phát các phần tử riêng.
- Reactive Streams không dùng `null` làm một phần tử bình thường; không tìm thấy một kết quả thường được biểu diễn bằng hoàn tất rỗng khi hợp đồng phương thức cho phép.

Các kiểu này không tự khẳng định thread thực thi. Một nguồn `Flux.just(...)` có thể phát đồng bộ khi đăng ký. Scheduler và nguồn I/O quyết định nơi công việc chạy; việc có một publisher không đồng nghĩa luôn tạo thêm thread.

### 5.3. Ví dụ repository reactive với R2DBC

Ví dụ độc lập sau giả định `PurchaseOrder` được ánh xạ phù hợp cho R2DBC, có driver R2DBC và cấu hình kết nối tương ứng:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderReactiveRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByTenantIdAndStatusOrderByIdAsc(
        String tenantId,
        String status
    );

    Mono<PurchaseOrder> findByTenantIdAndId(
        String tenantId,
        Long id
    );
}
```

Ý nghĩa hợp đồng:

- Phương thức thứ nhất có thể phát nhiều đơn hàng.
- Phương thức thứ hai có thể phát một đơn hàng hoặc hoàn tất rỗng khi không tìm thấy, theo hợp đồng truy vấn một kết quả.
- Việc thực thi và quản lý kết nối do module reactive và driver phối hợp.
- `ReactiveCrudRepository` không biến một JPA repository thành reactive repository.

Với truy vấn reactive thông thường, việc dựng pipeline chưa phải là việc đã tiêu thụ kết quả. Khi có subscription, nguồn truy vấn mới được thực thi theo cơ chế của module. Không suy rộng điều này cho mọi publisher: nguồn hot hoặc một công việc đã được khởi động trước có vòng đời khác.

### 5.4. Trả pipeline cho tầng sở hữu subscription

Một DTO đơn giản:

```java
import java.math.BigDecimal;

public record OrderView(Long id, BigDecimal totalAmount) {}
```

Tạo pipeline:

```java
public Flux<OrderView> paidOrders(String tenantId) {
    return repository
        .findByTenantIdAndStatusOrderByIdAsc(tenantId, "PAID")
        .map(order -> new OrderView(
            order.getId(),
            order.getTotalAmount()
        ));
}
```

Đoạn này giả định `repository` là `OrderReactiveRepository` và domain có các getter tương ứng. `map` phù hợp với phép chuyển đổi đồng bộ, ngắn và không chặn như tạo DTO.

Trong một request WebFlux, controller có thể trả publisher để framework đăng ký và điều phối tín hiệu. Thường không nên tự `subscribe()` trong service rồi trả về một kết quả tách rời, vì làm vậy dễ tách việc xử lý khỏi lỗi, hủy request và transaction của pipeline chính.

Không cần thêm `@Async` chỉ để một phương thức trả `Flux` trở nên reactive. Việc kết hợp hai cơ chế phải có lý do cụ thể và hỗ trợ tương ứng, không phải thao tác mặc định.

### 5.5. Backpressure không phải SQL LIMIT

Nhu cầu `request(100)` mô tả số phần tử được phép phát ở một ranh giới của giao thức. Nó không tự có nghĩa database đã được gửi `LIMIT 100`.

Tương tự, một operator như `limitRate(100)` có thể điều chỉnh cách yêu cầu dữ liệu từ upstream. Nó không thay thế derived limit, pagination hoặc bộ lọc ở kho dữ liệu.

Giữa ứng dụng và server có thể tồn tại buffer, prefetch và fetch theo batch. Mức độ nhu cầu được truyền xuống driver và tác động đến tài nguyên database tùy từng triển khai.

Reactive backpressure giúp phối hợp tốc độ phát và nhận, nhưng vẫn phải chọn giới hạn dữ liệu, độ đồng thời và bộ nhớ phù hợp.

## 6. Đổi wrapper không thay đổi bản chất I/O

### 6.1. Bọc danh sách JPA trong Flux

Mẫu sau vẫn thực hiện truy vấn blocking trước khi tạo publisher:

```java
Flux<PurchaseOrder> orders = Flux.fromIterable(
    jpaRepository.findAll()
);
```

Theo thứ tự đánh giá biểu thức Java, `findAll()` phải trả danh sách để truyền vào `fromIterable`. Khi publisher được tạo, công việc truy vấn blocking đã diễn ra và danh sách đã được materialize.

Trì hoãn lời gọi bằng `defer` có thể đổi thời điểm bắt đầu, nhưng không tự đổi driver blocking thành non-blocking. Nếu chạy trên một event-loop, lời gọi blocking vẫn có thể giữ thread đó và ảnh hưởng nhiều request khác.

### 6.2. Cô lập một công việc blocking khi cần tích hợp

Một cầu nối có thể có dạng:

```java
import java.util.List;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<List<OrderView>> result = Mono
    .fromCallable(() -> blockingOrderReader.loadFirst100(
        tenantId, status
    ))
    .subscribeOn(Schedulers.boundedElastic());
```

Giả sử `blockingOrderReader` là service tải một danh sách DTO hữu hạn, quản lý transaction và tài nguyên bên trong phương thức blocking.

Đoạn mã trì hoãn việc gọi service đến subscription và sắp xếp phần công việc đó trên scheduler dành cho các công việc có thể chặn. Tuy vậy:

- Driver vẫn blocking.
- Danh sách vẫn được tạo đầy đủ trước khi Mono phát nó.
- Connection pool vẫn là giới hạn thực tế.
- Cần quản lý tải, hàng đợi, timeout và kích thước kết quả.

Đây là cách tích hợp một đoạn blocking vào pipeline khi cần, không phải chứng minh hệ thống đã có truy vấn reactive theo từng dòng.

Nếu tiếp tục chuyển danh sách này thành Flux, downstream có thể nhận từng phần tử theo nhu cầu, nhưng việc tải toàn bộ danh sách ở upstream đã xảy ra.

### 6.3. Bọc kết quả đã tính trong future cũng không làm nó async

Trong service imperative:

```java
return CompletableFuture.completedFuture(loadOrders());
```

`loadOrders()` được đánh giá trước khi tạo completed future. Nếu không có ranh giới executor khác bao quanh, bên gọi vẫn phải chờ việc tải hoàn tất.

Ngược lại, trong một phương thức `@Async` thực sự được proxy chuyển sang worker, việc dùng `completedFuture` để trả kết quả đã được worker tính xong có ý nghĩa khác. Phải xác định công việc chạy ở đâu, thay vì chỉ nhìn factory tạo future.

## 7. Transaction và tài nguyên theo từng mô hình

### 7.1. Với Stream: bao quanh toàn bộ việc tiêu thụ

Một transaction chỉ bao quanh lời gọi tạo stream nhưng kết thúc trước terminal operation có thể không bao quanh việc đọc dữ liệu thực tế.

Cần thống nhất:

- Nơi mở và đóng stream.
- Phạm vi transaction còn hiệu lực khi duyệt.
- Thời điểm truy cập các thuộc tính lazy.
- Giới hạn thời gian giữ kết nối và entity trong persistence context.

Java Stream thường chỉ được tiêu thụ một lần. Không lưu nó như một danh sách có thể duyệt lại tùy ý.

### 7.2. Với Async: đặt phạm vi ở worker

Không truyền ngầm một stream đang mở, `EntityManager` hoặc trạng thái transaction gắn với thread sang task khác.

Thay vào đó, giao các giá trị đầu vào cần thiết cho worker, mở phạm vi đọc/xử lý tại đó và trả kết quả có vòng đời rõ ràng. Với dữ liệu nhỏ, DTO hoặc giá trị scalar thường dễ chuyển qua ranh giới thread hơn entity còn cần lazy loading.

Một future bị hủy hoặc hết thời gian đợi không bảo đảm truy vấn database đã dừng ngay. Cần phân biệt thời gian chờ của bên gọi, thời hạn task và cơ chế hủy/timeout của nguồn.

### 7.3. Với Reactive: transaction đi cùng pipeline và subscription

Transaction reactive không dựa vào giả định mọi bước chạy trên một thread cố định. Với Reactor, ngữ cảnh transaction có thể được truyền theo reactive context của pipeline.

Nếu cần transaction, phải có reactive transaction manager tương ứng với nguồn dữ liệu và đặt phạm vi bằng cơ chế được hỗ trợ, chẳng hạn `TransactionalOperator` hoặc annotation với cấu hình phù hợp.

Không giả định một transaction manager JPA imperative sẽ quản lý một chuỗi R2DBC chỉ vì hai phần cùng nằm trong một service. Cũng không coi việc gọi `subscribe()` thủ công để tạo một nhánh riêng là tự động tham gia transaction của chuỗi bên ngoài.

Khi nguồn kết thúc, lỗi hoặc bị hủy, hạ tầng reactive cần giải phóng tài nguyên theo giao thức của nó. Việc hủy và giải phóng ở server có thể không hoàn tất tức thời; mức hỗ trợ tùy driver và thao tác.

## 8. Lỗi, hủy và thử lại

| Tình huống | Java Stream | Async với future | Reactive pipeline |
|---|---|---|---|
| Truy vấn thất bại | Có thể ném khi gọi repository hoặc khi duyệt | Thường hoàn tất exceptionally nếu lỗi trong task | Thường phát `onError` trong subscription |
| Xử lý một phần tử bị lỗi | Terminal operation có thể dừng bằng exception | Task hoặc callback có thể thất bại | Operator có thể chuyển lỗi thành tín hiệu kết thúc |
| Dọn tài nguyên | `try-with-resources` cho stream có tài nguyên | Thực hiện bên trong task | Theo cơ chế nguồn và vòng đời subscription |
| Bên nhận không còn cần kết quả | Dừng duyệt và đóng stream | Cancellation không mặc định hủy được I/O đang chạy | Gửi cancel; tác động đến nguồn tùy khả năng triển khai |
| Thử lại | Cần tạo lại nguồn và xác định công việc đã làm | Có thể phải giao lại task, không chỉ đọc lại cùng future | Retry có thể đăng ký lại và thực hiện lại nguồn |

Thử lại có thể lặp truy vấn và tác động nghiệp vụ. Với thao tác ghi, phải xác định idempotency và điều kiện thử lại; operator hay wrapper không cung cấp bảo đảm exactly-once.

Một `catch` chỉ bao quanh việc dựng Flux chưa chắc bắt được lỗi xảy ra sau đó trong subscription. Cần xử lý ở pipeline hoặc tầng sở hữu subscription. Ngược lại, không phải mọi lỗi đều bị trì hoãn: việc kiểm tra đầu vào hoặc dựng biểu thức Java vẫn có thể ném ngay.

Tương tự, thêm một handler trả danh sách rỗng cho mọi lỗi có thể làm mất phân biệt giữa “không có dữ liệu” và “không đọc được dữ liệu”.

## 9. Độ đồng thời, bộ nhớ và giới hạn tải

### 9.1. Stream không tự giới hạn mọi tài nguyên

Dù duyệt từng phần tử, ứng dụng vẫn có thể giữ chúng trong một collection khác, tải nhiều quan hệ hoặc dùng operator cần buffer. Đo bộ nhớ thực tế thay vì suy từ tên kiểu trả về.

### 9.2. Executor không tạo thêm khả năng xử lý của database

Nếu executor có nhiều worker hơn số kết nối hoặc khả năng phục vụ của database, nhiều task có thể chỉ chờ tài nguyên. Queue tăng làm tăng thời gian chờ và bộ nhớ giữ đầu vào/request.

Theo dõi ít nhất số task đang chạy, số task chờ, thời gian chờ lấy kết nối, thời gian truy vấn và số task bị từ chối. Async có thể giúp thread gọi tiếp tục công việc, nhưng không làm database xử lý vô hạn truy vấn cùng lúc.

### 9.3. Reactive vẫn có thể buffer lớn hoặc thực hiện công việc blocking

Những thao tác như `collectList()` giữ toàn bộ phần tử cho đến khi nguồn hoàn tất. Một phép `flatMap` tạo nhiều công việc con cần được đánh giá về độ đồng thời, thứ tự và tài nguyên; tăng độ đồng thời không tự làm tăng thông lượng hữu ích.

Không đặt lời gọi JPA, truy cập file blocking hoặc chờ khóa dài trong một `map` rồi coi pipeline đã không chặn chỉ vì kiểu ngoài cùng là Flux.

Backpressure có tác dụng trong phạm vi giao thức và cách các thành phần thực hiện nó. Nó không thay thế việc chọn truy vấn hữu hạn, tránh gom dữ liệu vô hạn và quản lý tác vụ phụ.

## 10. Chọn mô hình theo nhu cầu

| Nhu cầu | Lựa chọn đáng cân nhắc | Điều kiện cần giữ |
|---|---|---|
| Xử lý dữ liệu đồng bộ từ nguồn hỗ trợ Stream | Java Stream từ repository | Đóng tài nguyên, transaction đúng phạm vi, kiểm tra fetch và bộ nhớ |
| Giao một tác vụ blocking hữu hạn cho worker | `@Async` với future | Executor có giới hạn, xử lý lỗi, transaction nằm trong công việc |
| Phối hợp nhiều kết quả hữu hạn trong mô hình imperative | Future và các phép kết hợp tương ứng | Không chặn vô ý, kiểm soát tải và timeout |
| Phục vụ nhiều I/O đồng thời trên stack reactive | Reactive repository với driver phù hợp | Chuỗi xử lý không chặn, quản lý nhu cầu, transaction và tài nguyên |
| Tích hợp thư viện blocking vào ứng dụng reactive | Cầu nối được cô lập trên scheduler phù hợp | Vẫn tính chi phí thread, kết nối và materialize dữ liệu |
| Quét dữ liệu lớn với checkpoint | Batch/window hoặc cơ chế quét của store | Thiết kế ranh giới tiếp tục, tính nhất quán và xử lý lại |

Không cần chọn một mô hình duy nhất cho mọi module trong ứng dụng. Tuy nhiên, tại mỗi ranh giới cần nêu rõ kiểu dữ liệu, ai sở hữu tài nguyên, nơi công việc chạy và cách lỗi được chuyển tiếp.

Ví dụ, một hệ thống JPA phục vụ tốt bằng mô hình imperative không tự có lợi chỉ vì đổi mọi kết quả sang Flux. Ngược lại, một ứng dụng R2DBC theo mô hình reactive sẽ mất lợi ích nếu thường xuyên gọi `block()` hoặc chèn truy vấn JDBC ngay trên event-loop.

## 11. Những hiểu lầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “Stream nghĩa là async” | Stream Java mô tả duyệt dữ liệu; stream tuần tự thường chạy đồng bộ |
| “Lazy nghĩa là chưa mở database” | Repository có thể đã lấy tài nguyên trước khi terminal operation bắt đầu |
| “@Async nghĩa là non-blocking” | Worker vẫn có thể bị chặn bởi JDBC hoặc các thao tác khác |
| “CompletableFuture tự tạo thread” | Future là abstraction kết quả; cần xem nơi task được giao và thực hiện |
| “Flux luôn chạy ở thread khác” | Nguồn có thể phát đồng bộ; thread phụ thuộc nguồn và scheduler |
| “Flux từ List là đọc database theo backpressure” | Danh sách có thể đã được tải đầy đủ từ trước |
| “request(100) là LIMIT 100” | Nhu cầu phát phần tử khác giới hạn query ở store |
| “parallel làm JPA nhanh hơn một cách an toàn” | Tính an toàn thread, transaction và nguồn cần được đánh giá riêng |
| “Cancel bảo đảm query đã dừng” | Hủy yêu cầu và dừng công việc phía nguồn không nhất thiết tức thời |
| “Reactive không cần quản lý tài nguyên” | Nguồn, subscription và transaction vẫn có vòng đời cần quản lý |

## 12. Bài tập vận dụng

### Bài tập 1: Future nhưng request vẫn phải chờ

Một controller gọi repository async rồi lập tức `join()` để lấy danh sách. Có phải truy vấn đã trở thành non-blocking không?

**Gợi ý lời giải:** Không. Truy vấn có thể chạy ở worker nhưng thread controller lại chờ future. Driver blocking vẫn có thể giữ worker. Cần phân biệt chuyển việc sang thread khác và cách bên gọi tiếp nhận kết quả.

### Bài tập 2: Trả stream từ service transaction

Service được gắn `@Transactional` trả một `Stream<PurchaseOrder>`. Controller duyệt stream sau khi phương thức service kết thúc. Điều gì cần kiểm tra?

**Gợi ý lời giải:** Transaction và tài nguyên cần thiết có thể đã hết phạm vi. Cần xác định bên sở hữu stream, giữ transaction phù hợp trong lúc tiêu thụ và bảo đảm đóng stream. Không chỉ nhìn annotation của phương thức tạo stream.

### Bài tập 3: Flux từ JPA

Một service dùng `Flux.fromIterable(jpaRepository.findAll())`. Vì sao backpressure của downstream không chứng minh query JPA đọc từng dòng theo nhu cầu?

**Gợi ý lời giải:** Lời gọi JPA được đánh giá trước khi tạo Flux và đã materialize danh sách. Downstream có thể điều phối việc phát từ danh sách, nhưng việc truy vấn upstream đã xảy ra theo mô hình blocking đó.

### Bài tập 4: Stream với limit

Ứng dụng nhận Stream từ repository rồi gọi `.limit(10)`. Có thể kết luận database chỉ xử lý đúng 10 dòng không?

**Gợi ý lời giải:** Không. Limit này thuộc pipeline Java. Số dòng được truy vấn, fetch hoặc buffer tùy module và driver. Nếu cần giới hạn ở truy vấn, dùng cơ chế giới hạn được repository/module hỗ trợ và kiểm tra hành vi tương ứng.

### Bài tập 5: Không thấy query chạy

Một phương thức tạo pipeline từ reactive repository rồi bỏ kết quả, không trả nó cho framework và không có subscriber. Tại sao truy vấn có thể chưa chạy?

**Gợi ý lời giải:** Nguồn truy vấn reactive thông thường thực thi khi có subscription. Cần để tầng phù hợp sở hữu và tiêu thụ publisher, thay vì bỏ pipeline hoặc tự tạo subscription tách rời mà không quản lý vòng đời.

### Bài tập 6: Async và lazy loading

Một worker trả entity qua future. Sau khi worker kết thúc, callback ở một thread khác truy cập quan hệ lazy. Có nên giả định transaction của bên gọi ban đầu bảo vệ thao tác này không?

**Gợi ý lời giải:** Không. Transaction imperative không tự lan qua ranh giới thread, và vòng đời entity có thể đã tách khỏi tài nguyên cần thiết. Nên xác định fetch plan hoặc chuẩn bị DTO trong phạm vi đọc phù hợp.

### Bài tập 7: Reactive nhưng bộ nhớ vẫn tăng

Một pipeline đọc nhiều bản ghi rồi `collectList()` trước khi ghi file. Backpressure có bảo đảm không giữ toàn bộ dữ liệu không?

**Gợi ý lời giải:** Không. `collectList()` cần tích lũy toàn bộ kết quả trước khi phát danh sách. Cần thiết kế bước tiêu thụ, buffer và kích thước dữ liệu theo nhu cầu thực tế.

## 13. Những điều cần ghi nhớ

- Java Stream, async task và Reactive Streams giải quyết những khía cạnh khác nhau của việc nhận và xử lý dữ liệu.
- Lazy, asynchronous, parallel và non-blocking không phải các từ thay thế cho nhau.
- Stream từ repository cần được tiêu thụ và đóng trong phạm vi tài nguyên phù hợp; nó không tự chuyển việc sang thread khác.
- `@Async` chuyển công việc qua executor khi lời gọi được cơ chế Spring tương ứng xử lý; nó không thay đổi bản chất driver blocking.
- Future chứa danh sách là một kết quả hoàn tất, khác với publisher phát nhiều phần tử theo nhu cầu.
- Reactive repository cần module và driver tương ứng; đổi wrapper không biến JPA/JDBC thành nguồn non-blocking.
- Backpressure điều phối phát phần tử, không tự thay SQL LIMIT, query filter hay mọi giới hạn bộ nhớ.
- Transaction, xử lý lỗi, hủy và tài nguyên phải đi theo mô hình thực thi thực tế, thay vì suy từ tên kiểu trả về.
