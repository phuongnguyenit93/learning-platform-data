# Supplier<Flux<T>> và vòng đời đăng ký luồng

Trong Spring Cloud Stream, một Supplier là nguồn phát dữ liệu. Khi Supplier trả về một giá trị đơn, framework có thể gọi phương thức get() theo lịch polling để lấy từng giá trị và gửi tới broker. Khi Supplier trả về Flux<T>, ý nghĩa thay đổi: giá trị trả về là một luồng dữ liệu phản ứng có thể phát nhiều phần tử theo thời gian. Framework cần biết đó là luồng liên tục chỉ đăng ký một lần hay là kết quả hữu hạn cần truy vấn định kỳ.

Hiểu đúng vòng đời đăng ký giúp tránh hai lỗi thường gặp: một luồng hữu hạn chỉ chạy một lần rồi kết thúc dù ứng dụng mong muốn polling, hoặc một luồng liên tục bị tạo lại theo từng nhịp poll khiến dữ liệu phát trùng. Spring Cloud Stream hỗ trợ cả hai trường hợp, nhưng cách khai báo khác nhau.

## 1. Supplier<T> và Supplier<Flux<T>> khác nhau ở đâu?

Supplier thông thường trả về một giá trị cho mỗi lần gọi:

~~~java
@Bean
public Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat(Instant.now());
}
~~~

Spring Cloud Stream dùng poller mặc định để gọi Supplier này. Theo cấu hình mặc định hiện tại, poller gọi mỗi giây một lần và mỗi lần lấy một giá trị để gửi qua output binding.

Với reactive Supplier, phương thức get() trả về một Publisher thay vì một giá trị đơn:

~~~java
@Bean
public Supplier<Flux<Heartbeat>> heartbeatStream() {
    return () -> Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> new Heartbeat(sequence, Instant.now()));
}
~~~

Ở đây, một lần gọi get() tạo ra một Flux có thể phát nhiều heartbeat. Với Supplier phản ứng thông thường, Spring Cloud Stream nhận diện kiểu trả về này và gọi get() một lần để lấy luồng. Framework đăng ký vào Publisher và để các phần tử được phát đi theo thời gian. Nó không gọi lại get() mỗi giây như với Supplier<Heartbeat>.

| Đặc điểm | Supplier<T> | Supplier<Flux<T>> thông thường |
|---|---|---|
| Giá trị trả về | Một đối tượng mỗi lần gọi. | Một Publisher có thể phát nhiều đối tượng. |
| Cách kích hoạt | Poller gọi get() định kỳ. | Framework lấy Publisher một lần rồi đăng ký vào luồng. |
| Ví dụ | Một heartbeat cho mỗi lần polling. | Luồng heartbeat phát liên tục mỗi giây. |
| Khi luồng kết thúc | Lần polling tiếp theo gọi Supplier lại. | Publisher hoàn tất; Supplier không tự được gọi lại chỉ vì Flux đã hoàn tất. |
| Trường hợp phù hợp | Lấy một bản ghi hoặc một giá trị theo chu kỳ. | Nguồn sự kiện liên tục hoặc luồng sống lâu. |

Điểm cần ghi nhớ: **một lần gọi Supplier không đồng nghĩa một thông điệp**. Với Supplier<Flux<T>>, một lần gọi có thể cung cấp một luồng phát ra không, một hoặc nhiều thông điệp.

## 2. Đăng ký luồng diễn ra như thế nào?

Với một reactive Supplier được binding tới broker, vòng đời khái quát gồm các bước:

~~~mermaid
flowchart TD
    A[Spring khởi tạo ApplicationContext] --> B[Đăng ký bean Supplier]
    B --> C[Chọn function definition]
    C --> D[Tạo output binding]
    D --> E[Gọi Supplier.get một lần]
    E --> F[Nhận Publisher Flux]
    F --> G[Framework đăng ký subscription]
    G --> H[Flux phát các phần tử]
    H --> I[Output binding gửi thông điệp tới broker]
    G --> J[Ứng dụng hoặc binding dừng]
    J --> K[Subscription được kết thúc theo vòng đời endpoint]
~~~

Tên function vẫn tuân theo quy tắc binding của Spring Cloud Stream. Nếu bean tên **heartbeatStream**, output binding mặc định là **heartbeatStream-out-0**.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeatStream
    stream:
      bindings:
        heartbeatStream-out-0:
          destination: heartbeat-events
          content-type: application/json
~~~

Khi ứng dụng khởi động, binding đầu ra được kết nối tới destination **heartbeat-events**. Framework lấy Flux từ Supplier và đăng ký luồng để các phần tử phát ra được gửi qua binding đó.

Không cần tự gọi subscribe() bên trong Supplier. Hãy trả về Publisher để framework quản lý subscription của binding. Nếu tự subscribe trong Supplier rồi trả về một Flux khác, luồng tự tạo có thể không liên quan tới output binding; lỗi và việc hủy subscription cũng khó được quản lý cùng vòng đời ứng dụng.

## 3. Luồng liên tục và luồng hữu hạn

Một reactive Supplier thường được dùng làm nguồn liên tục. Ví dụ Flux.interval phát một giá trị theo chu kỳ và tiếp tục cho tới khi bị hủy:

~~~java
@Bean
public Supplier<Flux<Heartbeat>> heartbeatStream() {
    return () -> Flux.interval(Duration.ofSeconds(2))
            .map(sequence -> new Heartbeat(sequence, Instant.now()));
}
~~~

Ngược lại, Flux.just chỉ phát các phần tử đã khai báo rồi hoàn tất:

~~~java
@Bean
public Supplier<Flux<String>> startupMessages() {
    return () -> Flux.just("service-started", "service-ready");
}
~~~

Với Supplier phản ứng thông thường, framework chỉ gọi get() một lần. Vì vậy, startupMessages phát hai phần tử rồi hoàn tất; nó không tự chạy lại sau mỗi giây. Nếu mục tiêu là định kỳ truy vấn một nguồn dữ liệu và trả về một lô hữu hạn, hãy dùng @PollableBean.

### Dùng @PollableBean cho Flux hữu hạn

@PollableBean (thuộc gói **org.springframework.cloud.function.context**) là annotation đánh dấu Supplier phản ứng tạo ra luồng hữu hạn cần được polling. Annotation này là một dạng khai báo bean; framework tích hợp Spring Cloud Stream sử dụng dấu hiệu đó để gọi Supplier theo lịch poller.

Ví dụ một repository trả về các đơn hàng đang chờ:

~~~java
@Configuration
public class PendingOrderSource {

    @PollableBean(splittable = true)
    public Supplier<Flux<OrderEvent>> pendingOrders(
            OrderRepository repository) {
        return () -> Flux.defer(() ->
                Flux.fromIterable(repository.fetchNextBatch()))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Chọn bean này làm function và cấu hình output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: pendingOrders
    stream:
      bindings:
        pendingOrders-out-0:
          destination: pending-order-events
          content-type: application/json
~~~

Mỗi lần poll, Supplier trả về một Flux hữu hạn đại diện cho lô đơn hàng hiện có. Flux.defer trì hoãn việc gọi fetchNextBatch() cho tới khi Publisher được đăng ký, nhờ đó mỗi lần poll có thể lấy một lô mới. subscribeOn(Schedulers.boundedElastic()) phù hợp khi thao tác truy vấn repository là blocking; nếu repository đã reactive thì không cần chuyển sang scheduler này.

Cấu hình poller mặc định:

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 5000
      max-messages-per-poll: 1
~~~

Ví dụ trên đặt khoảng chờ mặc định giữa các lần poll là 5 giây. Thuộc tính max-messages-per-poll giới hạn số message được phát trong mỗi poll event theo cơ chế poller. Nếu chỉ muốn thay đổi lịch polling của output binding cụ thể, có thể dùng cấu hình theo binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        pendingOrders-out-0:
          producer:
            poller:
              fixed-delay: 5000
              max-messages-per-poll: 1
~~~

Các thuộc tính poller điều khiển tần suất gọi Supplier. Chúng không điều khiển tốc độ phát từng phần tử bên trong một Flux liên tục. Hai khái niệm cần được tách riêng:

- **Polling:** thời điểm framework gọi Supplier.get() để lấy một Publisher mới.
- **Subscription:** việc đăng ký vào Publisher để nhận các phần tử mà Publisher phát ra.

### Thuộc tính splittable

@PollableBean có thuộc tính splittable, mặc định là true. Khi bật, framework tách các phần tử của Flux được trả về thành các thông điệp riêng biệt gửi qua output binding.

~~~java
@PollableBean(splittable = true)
public Supplier<Flux<OrderEvent>> pendingOrders(
        OrderRepository repository) {
    return () -> Flux.fromIterable(repository.fetchNextBatch());
}
~~~

Nếu đặt splittable = false, framework không tách các phần tử thành từng thông điệp riêng theo cơ chế này; kết quả Flux được giữ như một kết quả duy nhất của lần poll. Chỉ chọn cách đó khi kiểu payload và converter/binder ở phía gửi, nhận đã được thiết kế để xử lý biểu diễn này. Với luồng sự kiện thông thường, splittable = true thường phù hợp hơn vì mỗi phần tử trở thành một message độc lập.

## 4. Chọn đúng nguồn Flux

Flux có thể là cold publisher hoặc hot publisher. Sự khác biệt này ảnh hưởng đến thời điểm dữ liệu được tạo và việc có bỏ lỡ sự kiện trước khi framework đăng ký hay không.

| Loại Publisher | Hành vi | Ví dụ |
|---|---|---|
| Cold | Công việc bắt đầu khi có subscription; mỗi subscription thường tạo một lần thực thi độc lập. | Flux.just, Flux.fromIterable, Flux.defer, Flux.interval. |
| Hot | Nguồn có thể phát độc lập với subscriber; subscriber đến muộn có thể bỏ lỡ phần tử đã phát. | Một số nguồn sự kiện dùng Sinks.Many hoặc event bus. |

Với cold publisher, framework đăng ký một lần và nguồn bắt đầu phát khi có subscription. Ví dụ:

~~~java
Supplier<Flux<String>> source = () ->
        Flux.defer(() -> {
            log.info("Bắt đầu tạo luồng");
            return Flux.just("A", "B", "C");
        });
~~~

Flux.defer hữu ích khi cần tạo nguồn tại thời điểm subscription thay vì khi khởi tạo bean. Tuy nhiên, với reactive Supplier liên tục được framework đăng ký một lần, defer không biến luồng thành cơ chế polling định kỳ.

Với hot publisher, hãy bảo đảm nguồn không phát dữ liệu quan trọng trước khi subscription được thiết lập, hoặc chọn cơ chế lưu đệm/replay phù hợp. Một Sinks.Many multicast không replay các phần tử đã phát cho subscriber đến sau trừ khi dùng loại sink có chính sách lưu/replay tương ứng.

Không dùng một hot source trong bộ nhớ như kho lưu trữ bền vững. Khi tiến trình dừng, dữ liệu và trạng thái của sink trong bộ nhớ có thể mất.

## 5. Không chặn luồng xử lý phản ứng

Reactor cho phép biểu diễn các thao tác bất đồng bộ theo chuỗi toán tử. Với Supplier liên tục, tránh gọi API blocking trực tiếp trên scheduler chuyên xử lý tín hiệu thời gian hoặc event loop.

Ví dụ nguồn phát sự kiện nhẹ:

~~~java
@Bean
public Supplier<Flux<SystemMetric>> metricsStream() {
    return () -> Flux.interval(Duration.ofSeconds(5))
            .map(tick -> new SystemMetric(
                    tick,
                    Instant.now(),
                    Runtime.getRuntime().freeMemory()
            ));
}
~~~

Nếu nguồn dữ liệu là API blocking hoặc JDBC, hãy trì hoãn lời gọi và chuyển phần blocking sang boundedElastic:

~~~java
Supplier<Flux<CustomerEvent>> customerEvents(
        LegacyCustomerClient client) {
    return () -> Flux.defer(() ->
            Flux.fromIterable(client.fetchEvents()))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Không đặt Thread.sleep() trong map của một luồng phản ứng. Nếu cần tạo nhịp định kỳ, dùng Flux.interval. Nếu cần truy vấn định kỳ một nguồn blocking, dùng @PollableBean cùng poller và thực thi truy vấn trên scheduler phù hợp.

## 6. Backpressure và giới hạn của binder

Reactor hỗ trợ backpressure qua giao thức Reactive Streams: subscriber có thể biểu thị nhu cầu nhận dữ liệu và publisher có thể điều tiết việc phát theo nhu cầu đó. Tuy nhiên, việc dùng Flux trong chữ ký function không tự động làm toàn bộ đường đi từ nguồn tới broker trở thành reactive end-to-end.

Với các binder message-channel thông thường, chẳng hạn Kafka binder thông thường hoặc Rabbit binder, nguồn và đích không nhất thiết là Reactive Streams Publisher/Subscriber. Ứng dụng có thể dùng toán tử Reactor để biến đổi dữ liệu, nhưng không nên mặc định rằng broker sẽ truyền ngược demand tới Supplier.

Tài liệu hiện hành ghi nhận reactive Kafka binder đã bị deprecated từ Spring Cloud Stream 4.3.0 và dự kiến bị loại bỏ trong phiên bản tương lai. Với dự án mới, không nên mặc định chọn binder đó chỉ để có backpressure. Hãy dùng binder được hỗ trợ cho phiên bản dự án và tự thiết kế giới hạn tốc độ, buffer, concurrency, retry và khả năng chịu tải theo cơ chế thực tế của binder.

Nếu nguồn phát nhanh hơn khả năng gửi của broker, cần có chiến lược rõ ràng:

- Giới hạn tốc độ hoặc số phần tử được tạo.
- Dùng buffer có dung lượng hữu hạn và định nghĩa hành vi khi buffer đầy.
- Có thể bỏ dữ liệu chỉ khi nghiệp vụ cho phép, ví dụ metric không quan trọng.
- Với sự kiện nghiệp vụ, lưu nguồn ở hệ thống bền vững và phát lại khi cần.
- Theo dõi queue depth, producer error, thời gian gửi và số phần tử bị loại.

Không dùng buffer vô hạn để che giấu tình trạng downstream chậm. Buffer tăng không giới hạn có thể làm đầy heap và khiến tiến trình bị dừng.

## 7. Lỗi, retry và hoàn tất Publisher

Reactive Supplier được framework khởi tạo để lấy một Publisher. Sau khi kết nối luồng, việc xử lý lỗi của từng phần tử nằm trong các toán tử Reactor mà ứng dụng xây dựng. Cơ chế retry dành cho imperative function không tự động bao bọc mọi tín hiệu của reactive stream.

Ví dụ xử lý lỗi có retry:

~~~java
@Bean
public Supplier<Flux<PriceTick>> priceTicks(PriceClient client) {
    return () -> Flux.defer(client::streamTicks)
            .retryWhen(Retry.backoff(
                    Long.MAX_VALUE,
                    Duration.ofSeconds(1))
                    .maxBackoff(Duration.ofSeconds(30)))
            .doOnError(error ->
                    log.error("Luồng giá không thể phục hồi", error));
}
~~~

retryWhen đăng ký lại nguồn khi có lỗi theo chính sách đã khai báo. Nếu không có retry hoặc phục hồi bằng onErrorResume, một lỗi không được xử lý sẽ kết thúc Publisher. Với reactive Supplier thông thường, framework không tự gọi lại get() chỉ vì Publisher phát tín hiệu lỗi.

Có thể dùng onErrorResume khi ứng dụng có nguồn thay thế:

~~~java
return () -> primarySource()
        .onErrorResume(error -> {
            log.warn("Chuyển sang nguồn dự phòng", error);
            return fallbackSource();
        });
~~~

Hãy chọn retry có giới hạn hoặc backoff phù hợp. Retry vô hạn có thể giữ subscription hoạt động nhưng cũng có thể che giấu lỗi cấu hình hoặc lỗi vĩnh viễn. Nên phân loại lỗi có thể phục hồi và lỗi không thể phục hồi, ghi metric cho số lần retry và phát cảnh báo khi luồng liên tục chuyển sang fallback.

### Khi Flux hoàn tất

Một Flux hữu hạn phát hết phần tử rồi gửi tín hiệu onComplete. Với reactive Supplier thông thường, Supplier không tự được gọi lại sau khi hoàn tất. Nếu cần phát một lô mới theo chu kỳ, dùng @PollableBean.

Một Flux liên tục như Flux.interval thường không tự hoàn tất. Nó tiếp tục phát cho tới khi bị hủy hoặc gặp lỗi. Khi ứng dụng dừng, binding/endpoint được dừng theo vòng đời ứng dụng; không nên coi trạng thái nội bộ của Publisher là trạng thái bền vững được tự động khôi phục.

Có thể dùng doFinally để quan sát kết thúc, lỗi hoặc hủy subscription:

~~~java
return () -> Flux.interval(Duration.ofSeconds(1))
        .map(this::toHeartbeat)
        .doFinally(signal ->
                log.info("Heartbeat subscription kết thúc: {}", signal));
~~~

doFinally phục vụ quan sát và dọn dẹp tài nguyên. Không đặt công việc blocking kéo dài trong callback này.

## 8. Vòng đời khi khởi động lại và chạy nhiều instance

Một Supplier<Flux<T>> thông thường được khởi tạo theo vòng đời ứng dụng. Khi tiến trình khởi động, framework tạo binding và đăng ký vào Publisher. Khi tiến trình dừng, endpoint và subscription tương ứng được dừng. Khi khởi động lại, ứng dụng tạo Supplier/Publisher và subscription mới.

Điều đó có nghĩa:

- Bộ đếm trong Flux.interval thường bắt đầu lại từ đầu ở tiến trình mới.
- Buffer trong bộ nhớ, biến đếm và trạng thái tạm của Flux không tự được phục hồi.
- Một hot source trong bộ nhớ có thể mất dữ liệu khi tiến trình dừng.
- Nếu cần tiếp tục từ một vị trí dữ liệu, ứng dụng phải lưu checkpoint hoặc dùng nguồn dữ liệu có cursor bền vững.

### Chạy nhiều replica

Mỗi replica của ứng dụng thường có một ApplicationContext và một subscription riêng tới Supplier. Nếu Supplier phát heartbeat hoặc tạo sự kiện nghiệp vụ, tăng số replica có thể làm số luồng phát tăng tương ứng.

Ví dụ, chạy ba replica với Flux.interval có thể tạo ba chuỗi heartbeat. Đây là hành vi phù hợp nếu muốn mỗi instance tự phát trạng thái sống; nhưng không phù hợp nếu chỉ muốn một sự kiện nghiệp vụ duy nhất cho toàn cluster.

Nếu chỉ một instance được phép phát, cần một cơ chế phối hợp ở cấp cluster, chẳng hạn leader election, distributed lock hoặc phân vùng công việc. Không dùng một biến static hoặc singleton trong JVM để giả định tính duy nhất giữa các replica.

## 9. Đảm bảo dữ liệu khi phát từ nguồn phản ứng

Flux mô tả cách dữ liệu được phát trong tiến trình. Nó không tự bảo đảm dữ liệu đã được lưu bền vững trước khi binder gửi thành công.

Giả sử Supplier đọc các bản ghi từ cơ sở dữ liệu:

1. Supplier lấy một lô bản ghi.
2. Flux phát các bản ghi.
3. Output binding gửi từng thông điệp tới broker.
4. Tiến trình dừng trước khi cập nhật checkpoint.

Khi khởi động lại, ứng dụng có thể đọc lại lô cũ. Đây là lý do consumer nên idempotent và nguồn cần có cursor/checkpoint rõ ràng. Ngược lại, nếu checkpoint được cập nhật trước khi thông điệp được broker xác nhận, tiến trình dừng giữa hai thao tác có thể làm mất dữ liệu.

Với dữ liệu nghiệp vụ quan trọng, hãy cân nhắc:

- Transactional outbox để ghi sự kiện cùng transaction nghiệp vụ rồi phát lại từ outbox.
- CDC hoặc log thay đổi bền vững nếu nguồn dữ liệu hỗ trợ.
- Cursor theo khóa hoặc thời gian có tính duy nhất, được cập nhật sau khi đã bảo đảm publish theo quy trình phù hợp.
- Idempotency ở consumer để chịu được giao nhận lại.
- Dead-letter và quy trình phát lại cho thông điệp không xử lý được.

Không coi Flux.interval, Sinks.Many hoặc một collection trong bộ nhớ là hàng đợi bền vững. Độ bền sau khi gửi còn phụ thuộc producer configuration, broker, acknowledgement và cách ứng dụng quản lý tiến độ nguồn.

## 10. Kiểm thử Supplier<Flux<T>>

Kiểm thử nên tách ba lớp:

1. Kiểm thử Publisher độc lập bằng Reactor StepVerifier.
2. Kiểm thử bean Supplier và số lần gọi get().
3. Integration test Spring Cloud Stream để xác nhận binding nhận các phần tử và gửi tới destination đúng.

### Kiểm thử một Flux hữu hạn

~~~java
Supplier<Flux<Integer>> source = () -> Flux.range(1, 3);

StepVerifier.create(source.get())
        .expectNext(1, 2, 3)
        .verifyComplete();
~~~

### Kiểm thử thời gian với virtual time

Với Flux.interval, dùng virtual time để kiểm tra mà không phải chờ thật:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3))
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
~~~

### Kiểm tra Supplier chỉ được lấy Publisher một lần

~~~java
AtomicInteger supplierCalls = new AtomicInteger();

Supplier<Flux<String>> source = () -> {
    supplierCalls.incrementAndGet();
    return Flux.just("one", "two");
};

Flux<String> publisher = source.get();

StepVerifier.create(publisher)
        .expectNext("one", "two")
        .verifyComplete();

assertThat(supplierCalls.get()).isEqualTo(1);
~~~

Đoạn test trên xác nhận cách Supplier được gọi trong bài kiểm thử đơn vị. Để xác nhận framework chỉ lấy Publisher một lần trong ứng dụng thật, cần khởi động ApplicationContext với function definition và test binder, sau đó quan sát số lần Supplier được gọi trong suốt vòng đời binding.

### Ma trận kiểm thử tích hợp

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Reactive Supplier liên tục | Khởi động ứng dụng và quan sát output binding. | Supplier được gọi một lần; Flux tiếp tục phát nhiều thông điệp. |
| Flux hữu hạn không pollable | Dùng Flux.just trong Supplier thường. | Các phần tử được phát một lần rồi Publisher hoàn tất. |
| Flux hữu hạn có PollableBean | Dùng @PollableBean và poller delay ngắn trong test. | Supplier được gọi lại theo lịch; mỗi lần tạo lô mới. |
| Splittable true | Trả về Flux có ba phần tử. | Ba phần tử được gửi thành ba message riêng. |
| Splittable false | Trả về Flux và tắt tách phần tử. | Kết quả không được tách thành từng message theo cấu hình này. |
| Lỗi giữa luồng | Tạo nguồn phát lỗi sau một số phần tử. | Retry hoặc fallback chạy theo toán tử Reactor đã cấu hình. |
| Dừng ứng dụng | Đóng ApplicationContext khi Flux đang phát. | Subscription và endpoint được dừng theo vòng đời ứng dụng. |
| Khởi động lại | Khởi động lại context. | Supplier và subscription mới được tạo; trạng thái nguồn được phục hồi theo thiết kế ứng dụng. |
| Nhiều replica | Chạy nhiều instance cùng cấu hình. | Số luồng phát và tác động trùng được hiểu, kiểm soát theo yêu cầu cluster. |

Khi kiểm thử với broker thật, xác nhận số message nhận được, thứ tự, retry, lỗi publish và hành vi sau restart. Test binder hữu ích cho kiểm tra binding trong tiến trình nhưng không thay thế kiểm thử độ bền, xác nhận và giới hạn tải của Kafka, RabbitMQ hoặc Pulsar.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Supplier chỉ phát một lô rồi dừng | Flux hữu hạn được dùng như reactive Supplier liên tục. | Dùng @PollableBean nếu cần polling định kỳ. |
| Supplier bị gọi lặp ngoài ý muốn | Dùng @PollableBean cho nguồn liên tục hoặc cấu hình poller không phù hợp. | Bỏ @PollableBean với luồng liên tục. |
| Không có message đầu ra | Chưa chọn function, sai binding name hoặc Flux không phát phần tử. | Kiểm tra definition, output binding và Publisher. |
| Luồng không bắt đầu | Supplier trả về Publisher nhưng không có binding hoạt động hoặc Publisher phụ thuộc subscription khác. | Xác minh binding và để framework đăng ký Publisher trả về. |
| Dữ liệu mất trước khi subscriber xuất hiện | Dùng hot publisher không có replay/buffer phù hợp. | Dùng cold source, replay hoặc nguồn lưu bền vững. |
| Luồng chết sau một lỗi | onError kết thúc Publisher và không có retry/fallback. | Thêm retryWhen hoặc onErrorResume theo loại lỗi. |
| Ứng dụng bị tăng heap | Buffer không giới hạn hoặc nguồn phát nhanh hơn downstream. | Giới hạn buffer, điều tiết nguồn và giám sát backlog. |
| Tạo sự kiện trùng khi scale | Mỗi replica chạy một Supplier độc lập. | Dùng leader election, phân vùng hoặc idempotency. |
| Dữ liệu bị đọc lại sau restart | Flux không lưu checkpoint và nguồn phát lại từ đầu. | Quản lý cursor/checkpoint và làm consumer idempotent. |
| Backpressure không điều tiết được broker | Binder đang dùng không hỗ trợ Reactive Streams end-to-end. | Kiểm tra khả năng binder; tự giới hạn tốc độ và concurrency. |

Khi điều tra, hãy xác định Supplier thuộc loại liên tục hay hữu hạn trước. Sau đó kiểm tra annotation @PollableBean, function definition, output binding, số lần gọi get(), thời điểm subscription và các tín hiệu onError, onComplete hoặc cancel. Cuối cùng kiểm tra binder, broker và số replica để tìm nguyên nhân ở ranh giới gửi.

## 12. Quy trình lựa chọn

Trước khi triển khai một Supplier<Flux<T>>, hãy trả lời:

1. Nguồn dữ liệu là liên tục hay mỗi lần truy vấn trả về một lô hữu hạn?
2. Framework cần lấy Publisher một lần hay cần gọi Supplier theo chu kỳ?
3. Publisher là cold hay hot; có thể bỏ lỡ dữ liệu trước subscription không?
4. Nguồn có blocking I/O hay cần scheduler riêng?
5. Flux có thể lỗi hoặc hoàn tất; retry/fallback được định nghĩa thế nào?
6. Một hay nhiều replica được phép phát cùng loại sự kiện?
7. Dữ liệu và checkpoint có cần tồn tại qua restart không?
8. Binder có hỗ trợ backpressure đầu cuối hay cần giới hạn tốc độ ở ứng dụng?

Chọn cách triển khai theo câu trả lời:

- **Luồng liên tục:** dùng Supplier<Flux<T>> thông thường, trả về Publisher sống lâu và để framework đăng ký.
- **Luồng hữu hạn cần chạy định kỳ:** dùng @PollableBean, cấu hình poller và chọn splittable theo cách muốn gửi phần tử.
- **Nguồn blocking:** trì hoãn thao tác và dùng scheduler phù hợp, hoặc chuyển sang API reactive thực sự.
- **Nguồn hot:** quản lý thời điểm khởi động, replay/buffer và hành vi khi không có subscriber.
- **Nguồn nghiệp vụ cần độ bền:** lưu cursor/checkpoint hoặc dùng outbox/CDC; không dựa vào trạng thái Flux trong bộ nhớ.

Supplier<Flux<T>> là cách biểu diễn nguồn dữ liệu phản ứng trong Spring Cloud Stream. Với luồng liên tục, framework lấy Publisher và đăng ký một lần; với luồng hữu hạn cần truy vấn định kỳ, @PollableBean đánh dấu Supplier để poller gọi lại theo lịch. Khi thiết kế rõ ranh giới giữa polling và subscription, kiểm soát lỗi bằng Reactor và xác định cách phục hồi nguồn dữ liệu, ứng dụng có thể phát sự kiện ổn định hơn trong suốt vòng đời triển khai.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
