# Phân phối dữ liệu thời gian thực tới nhiều bên nhận có tốc độ khác nhau

Trong một hệ thống realtime, cùng một luồng dữ liệu có thể được gửi tới nhiều bên nhận: dashboard vận hành, màn hình khách hàng, bộ cảnh báo và dịch vụ phân tích. Các bên nhận không xử lý nhanh như nhau. Dashboard có thể cập nhật ngay, dịch vụ phân tích có thể xử lý theo lô, còn một trình duyệt chạy trên thiết bị yếu có thể tiêu thụ dữ liệu chậm hơn nhiều.

Nếu tất cả bên nhận dùng chung một hàng đợi không giới hạn, một consumer chậm có thể làm bộ nhớ tăng liên tục. Nếu dùng một cơ chế multicast mà tốc độ chậm nhất quyết định nhịp chung, các consumer nhanh cũng bị ảnh hưởng. Dự án này xây dựng một bộ phân phối event bằng Spring Boot và RSocket, trong đó mỗi subscription có một queue hữu hạn riêng.

Chính sách của dự án:

- Mỗi bên nhận có một RSocket request-stream và một queue độc lập.
- Consumer nhanh tiếp tục nhận event mà không chờ consumer chậm.
- Khi queue riêng của một consumer đầy, hệ thống kết thúc stream đó bằng lỗi SlowConsumerException và giải phóng subscription.
- Event có sequence number để client nhận biết khoảng dữ liệu bị bỏ lỡ.
- Nếu nghiệp vụ yêu cầu không mất event, client phải đọc lại từ event store hoặc broker bền vững bằng cursor; queue RAM không thay thế lưu trữ bền vững.

## 1. Mục tiêu và kết quả cần đạt

Sau bài thực hành, bạn sẽ có một service phân phối telemetry event tới nhiều client RSocket có tốc độ xử lý khác nhau. Bạn sẽ:

1. Tạo event có sequence number và timestamp.
2. Đăng ký nhiều subscriber độc lập qua route RSocket.
3. Tạo bounded queue riêng cho từng subscriber.
4. Phát hiện queue overflow và ngắt riêng consumer chậm.
5. Xác minh consumer nhanh vẫn nhận event bình thường.
6. Kiểm tra cancellation và dọn dẹp subscription.
7. Theo dõi queue overflow, số subscriber và tốc độ phân phối.
8. Xác định cách replay event cho consumer cần tính đầy đủ dữ liệu.

Tiêu chí hoàn thành: khi một subscriber chậm vượt quá capacity của queue riêng, subscriber đó nhận lỗi và bị loại khỏi hub; subscriber nhanh vẫn nhận đủ các event đã phát trong thời gian thử nghiệm.

## 2. Kiến trúc tổng thể

Ứng dụng có một producer phát telemetry event và một FanoutHub quản lý các subscriber. Mỗi lần client gọi route telemetry.subscribe, hub tạo một channel unicast mới. Khi producer phát event, hub gửi bản event đó tới từng channel.

~~~mermaid
flowchart TD
    P[Telemetry producer]
    H[FanoutHub]
    Q1[Queue client nhanh]
    Q2[Queue client chậm]
    Q3[Queue client phân tích]
    C1[Fast dashboard]
    C2[Slow browser]
    C3[Analytics consumer]
    P --> H
    H --> Q1 --> C1
    H --> Q2 --> C2
    H --> Q3 --> C3
    Q2 -. Queue đầy .-> X[Ngắt riêng subscriber chậm]
    H -. Metric .-> M[Micrometer]
~~~

Không dùng một Flux multicast duy nhất với semantics để subscriber chậm điều khiển nhịp của toàn nhóm. FanoutHub tạo một queue độc lập cho từng subscription. Đây là điểm cốt lõi giúp cô lập consumer.

Mỗi queue có capacity theo số event. Nếu event có kích thước thay đổi lớn, cần bổ sung giới hạn byte hoặc giới hạn kích thước payload để kiểm soát bộ nhớ tổng thể.

## 3. Chính sách phân phối và đánh đổi

Không có một chính sách phù hợp cho mọi loại event. Dự án chọn ngắt consumer chậm khi queue đầy, nhưng cần hiểu các lựa chọn khác:

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| Queue riêng, giới hạn, overflow thì disconnect | Consumer chậm bị ngắt; consumer khác tiếp tục | Client có thể reconnect và lấy snapshot hoặc replay |
| Drop event mới | Bỏ event không thể nhận đúng lúc | Telemetry không quan trọng hoặc dữ liệu có thể tổng hợp |
| Latest/coalesce | Chỉ giữ trạng thái mới nhất | Dashboard chỉ cần snapshot hiện tại |
| Pause producer | Tạm dừng nguồn khi consumer chậm | Producer hỗ trợ pause/resume và có thể điều tiết |
| Durable log + cursor | Consumer đọc lại event sau sequence cuối | Audit, thanh toán hoặc dữ liệu cần đầy đủ |

Không dùng drop hoặc latest cho command thanh toán, audit hay thay đổi tồn kho nếu yêu cầu nghiệp vụ là không mất event. Với các luồng đó, hãy ghi event vào broker/log bền vững và để mỗi consumer đọc theo cursor riêng.

## 4. Cấu trúc dự án

Một cấu trúc package có thể dùng:

~~~text
src/main/java/com/example/realtime/
  event/
    TelemetryEvent.java
    SlowConsumerException.java
    SubscriberLimitException.java
  fanout/
    SubscriberChannel.java
    FanoutHub.java
  rsocket/
    TelemetryRSocketController.java
  producer/
    TelemetryProducer.java
  client/
    FastTelemetryClient.java
    SlowTelemetryClient.java
src/test/java/com/example/realtime/
  fanout/
    FanoutHubTest.java
    FanoutIsolationTest.java
~~~

Tên package và class có thể điều chỉnh theo ứng dụng. Các phần tiếp theo trình bày code chính và thứ tự tích hợp.

## 5. Khởi tạo ứng dụng Spring Boot

Tạo một ứng dụng Spring Boot có RSocket server và Actuator/Micrometer để quan sát. Dependency minh họa với Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Để chạy RSocket qua TCP trong môi trường server-to-server, cấu hình:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Nếu client là trình duyệt, có thể expose WebSocket transport trên endpoint riêng và bảo vệ bằng TLS/authentication phù hợp. Bài thực hành tập trung vào phân phối và cô lập subscriber; transport không làm thay đổi chính sách queue của FanoutHub.

## 6. Định nghĩa event và lỗi slow consumer

Mỗi event có sequence tăng dần. Client dùng sequence để phát hiện khoảng trống sau khi reconnect:

~~~java
package com.example.realtime.event;

import java.time.Instant;

public record TelemetryEvent(
    long sequence,
    Instant occurredAt,
    String source,
    String metric,
    double value
) {
}
~~~

Khi queue của một subscriber đầy, server kết thúc riêng stream đó bằng lỗi:

~~~java
package com.example.realtime.event;

public class SlowConsumerException extends RuntimeException {

    public static final String CODE = "SLOW_CONSUMER";

    public SlowConsumerException(
        String subscriptionId,
        int capacity,
        int discardedEvents
    ) {
        super(CODE + ": subscriber " + subscriptionId
            + " exceeded queue capacity " + capacity
            + "; discarded pending events=" + discardedEvents);
    }
}
~~~

Trong hệ thống production, không đưa thông tin nhạy cảm vào thông điệp lỗi. Có thể dùng error code ổn định như SLOW_CONSUMER để client quyết định reconnect hoặc chuyển sang đọc snapshot.

Hub cũng cần giới hạn tổng số subscription để tổng ngân sách queue không tăng vô hạn theo số client:

~~~java
package com.example.realtime.event;

public class SubscriberLimitException extends RuntimeException {

    public static final String CODE = "SUBSCRIBER_LIMIT";

    public SubscriberLimitException(int maximum) {
        super(CODE + ": maximum active subscriptions is " + maximum);
    }
}
~~~

## 7. Tạo channel riêng cho mỗi subscriber

SubscriberChannel bọc một unicast sink. Unicast bảo đảm một channel chỉ phục vụ một subscriber. Queue được cung cấp bằng ArrayBlockingQueue để giới hạn số event đang chờ.

~~~java
package com.example.realtime.fanout;

import java.util.concurrent.ArrayBlockingQueue;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import com.example.realtime.event.SlowConsumerException;
import com.example.realtime.event.TelemetryEvent;

final class SubscriberChannel {

    private final String id;
    private final int capacity;
    private final Object emissionLock = new Object();
    private final ArrayBlockingQueue<TelemetryEvent> queue;
    private final Sinks.Many<TelemetryEvent> sink;
    private boolean closed;

    SubscriberChannel(String id, int capacity) {
        this.id = id;
        this.capacity = capacity;
        this.queue = new ArrayBlockingQueue<>(capacity);
        this.sink = Sinks.many()
            .unicast()
            .onBackpressureBuffer(queue);
    }

    String id() {
        return id;
    }

    Flux<TelemetryEvent> flux() {
        return sink.asFlux();
    }

    Sinks.EmitResult emit(TelemetryEvent event) {
        synchronized (emissionLock) {
            if (closed) {
                return Sinks.EmitResult.FAIL_TERMINATED;
            }

            Sinks.EmitResult result = sink.tryEmitNext(event);
            if (result == Sinks.EmitResult.OK) {
                return result;
            }

            closed = true;
            if (result == Sinks.EmitResult.FAIL_OVERFLOW) {
                int discardedEvents = queue.size();
                queue.clear();
                Sinks.EmitResult terminal = sink.tryEmitError(
                    new SlowConsumerException(
                        id,
                        capacity,
                        discardedEvents
                    )
                );
                if (terminal.isFailure()) {
                    // Ghi metric/log: terminal signal không được chấp nhận.
                }
            } else {
                // FAIL_CANCELLED/FAIL_TERMINATED: channel không còn hoạt động.
                // FAIL_NON_SERIALIZED không mong đợi vì mọi emission đã khóa.
            }
            return result;
        }
    }

    void complete() {
        synchronized (emissionLock) {
            if (!closed) {
                closed = true;
                sink.tryEmitComplete();
            }
        }
    }
}
~~~

Khóa emissionLock tuần tự hóa thao tác emit và complete trên cùng channel. Nếu producer có nhiều thread, không để nhiều thread phát đồng thời vào một sink mà bỏ qua kết quả FAIL_NON_SERIALIZED.

Khi tryEmitNext trả về FAIL_OVERFLOW, event hiện tại không được xếp vào queue. Channel bỏ các event đang chờ rồi phát SlowConsumerException để terminal signal không phải đợi một consumer đã ngừng request. Đây là chính sách ngắt ngay: các event trong queue cũng bị bỏ và được đếm gần đúng trong thông điệp lỗi. Client cần dùng sequence/cursor để phát hiện và khôi phục khoảng dữ liệu bị thiếu. FanoutHub loại channel này khỏi danh sách nhận event mới.

## 8. Xây dựng FanoutHub

Hub quản lý tập subscriber đang hoạt động. Mỗi lần subscribe tạo một channel mới; mỗi lần publish, hub phát event tới từng channel và chỉ loại channel gặp lỗi:

~~~java
package com.example.realtime.fanout;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicLong;
import java.time.Instant;
import java.util.function.Consumer;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import com.example.realtime.event.TelemetryEvent;
import com.example.realtime.event.SubscriberLimitException;

public class FanoutHub {

    private final int queueCapacity;
    private final int maxSubscribers;
    private final Semaphore subscriberSlots;
    private final ConcurrentMap<String, SubscriberChannel> subscribers =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();
    private final Consumer<String> overflowReporter;

    public FanoutHub(
        int queueCapacity,
        int maxSubscribers,
        Consumer<String> overflowReporter
    ) {
        if (queueCapacity < 1) {
            throw new IllegalArgumentException("queueCapacity must be positive");
        }
        if (maxSubscribers < 1) {
            throw new IllegalArgumentException("maxSubscribers must be positive");
        }
        this.queueCapacity = queueCapacity;
        this.maxSubscribers = maxSubscribers;
        this.subscriberSlots = new Semaphore(maxSubscribers);
        this.overflowReporter = overflowReporter;
    }

    public Flux<TelemetryEvent> subscribe() {
        return Flux.defer(() -> {
            if (!subscriberSlots.tryAcquire()) {
                return Flux.error(
                    new SubscriberLimitException(maxSubscribers)
                );
            }

            String id = UUID.randomUUID().toString();
            SubscriberChannel channel =
                new SubscriberChannel(id, queueCapacity);
            subscribers.put(id, channel);

            return channel.flux()
                .doFinally(signal -> {
                    subscribers.remove(id, channel);
                    channel.complete();
                    subscriberSlots.release();
                });
        });
    }

    public TelemetryEvent publish(
        String source,
        String metric,
        double value
    ) {
        TelemetryEvent event = new TelemetryEvent(
            sequence.incrementAndGet(),
            Instant.now(),
            source,
            metric,
            value
        );

        subscribers.forEach((id, channel) -> {
            Sinks.EmitResult result = channel.emit(event);
            if (result != Sinks.EmitResult.OK) {
                subscribers.remove(id, channel);
                if (result == Sinks.EmitResult.FAIL_OVERFLOW) {
                    overflowReporter.accept(id);
                }
            }
        });

        return event;
    }

    public int subscriberCount() {
        return subscribers.size();
    }
}
~~~

Flux.defer tạo channel khi có subscription thật. Mỗi lần subscribe vào route sẽ có một ID và queue riêng. doFinally chạy khi complete, error hoặc cancel, vì vậy channel được gỡ khỏi map khi client ngắt kết nối.

Việc xóa dùng remove(id, channel) để tránh xóa nhầm channel mới nếu một thao tác cleanup chạy muộn. ID được sinh ngẫu nhiên trong ví dụ nên không bị trùng trong thực tế.

## 9. Expose stream qua RSocket

Controller trả Flux từ hub. RSocket chuyển demand và cancellation của request-stream tới subscription tương ứng:

~~~java
package com.example.realtime.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

import com.example.realtime.event.TelemetryEvent;
import com.example.realtime.fanout.FanoutHub;

@Controller
public class TelemetryRSocketController {

    private final FanoutHub hub;

    public TelemetryRSocketController(FanoutHub hub) {
        this.hub = hub;
    }

    @MessageMapping("telemetry.subscribe")
    public Flux<TelemetryEvent> subscribe() {
        return hub.subscribe();
    }
}
~~~

Mỗi request-stream tạo một subscription riêng. Không gọi subscribe() bên trong handler; hãy trả Publisher để framework quản lý demand, cancellation và lỗi của interaction.

## 10. Tạo producer phát telemetry

Để demo, có thể tạo một producer định kỳ. Subscription này thuộc lifecycle của bean, vì vậy phải giữ Disposable và dispose khi ứng dụng dừng:

~~~java
package com.example.realtime.producer;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.stereotype.Component;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

import com.example.realtime.fanout.FanoutHub;

@Component
public class TelemetryProducer {

    private final FanoutHub hub;
    private Disposable generator;

    public TelemetryProducer(FanoutHub hub) {
        this.hub = hub;
    }

    @PostConstruct
    void start() {
        generator = Flux.interval(Duration.ofMillis(20))
            .subscribe(tick -> hub.publish(
                "sensor-01",
                "temperature",
                20 + ThreadLocalRandom.current().nextDouble(10)
            ));
    }

    @PreDestroy
    void stop() {
        if (generator != null) {
            generator.dispose();
        }
    }
}
~~~

Producer demo phát khoảng 50 event/giây. Trong hệ thống thật, thay nguồn interval bằng broker, thiết bị hoặc domain event publisher. Nếu nguồn thật không hỗ trợ backpressure, phải kiểm soát tốc độ hoặc dùng adapter có queue hữu hạn trước khi gọi hub.

## 11. Đăng ký consumer nhanh

Client nhanh nhận stream và xử lý ngắn. Ví dụ dùng RSocketRequester:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.Disposable;

import com.example.realtime.event.TelemetryEvent;

public class FastTelemetryClient {

    private final RSocketRequester requester;
    private Disposable subscription;

    public FastTelemetryClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public void start() {
        subscription = requester.route("telemetry.subscribe")
            .retrieveFlux(TelemetryEvent.class)
            .doOnNext(event ->
                System.out.println("FAST " + event.sequence())
            )
            .subscribe(
                event -> updateDashboard(event),
                error -> handleStreamError(error)
            );
    }

    public void stop() {
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
~~~

Các hàm updateDashboard và handleStreamError là phần xử lý của ứng dụng. Khi gọi stop, dispose hủy subscription; connection RSocket có thể tiếp tục được dùng bởi các interaction khác.

## 12. Đăng ký consumer chậm

Consumer chậm xử lý mỗi event trong một khoảng thời gian. Dùng concatMap với prefetch nhỏ để chỉ xử lý tuần tự và không yêu cầu trước một lượng lớn event:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

import com.example.realtime.event.TelemetryEvent;

public class SlowTelemetryClient {

    private final RSocketRequester requester;
    private Disposable subscription;

    public SlowTelemetryClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public void start() {
        subscription = requester.route("telemetry.subscribe")
            .retrieveFlux(TelemetryEvent.class)
            .concatMap(event ->
                Mono.delay(Duration.ofMillis(250))
                    .doOnNext(tick -> processSlowly(event))
                    .then()
            , 1)
            .subscribe(
                ignored -> { },
                error -> handleStreamError(error)
            );
    }

    public void stop() {
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
~~~

Producer phát khoảng 50 event/giây, trong khi consumer chỉ xử lý khoảng 4 event/giây. Queue của consumer chậm sẽ nhanh chóng đầy và stream đó bị kết thúc. Consumer nhanh có subscription và queue khác nên không bị chặn bởi consumer chậm.

## 13. Đăng ký bean và cấu hình capacity

Đăng ký FanoutHub dưới dạng singleton để controller và producer dùng chung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import com.example.realtime.fanout.FanoutHub;

@Configuration
public class FanoutConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(FanoutConfiguration.class);

    @Bean
    FanoutHub fanoutHub() {
        int perSubscriberCapacity = 128;
        int maximumSubscribers = 500;
        return new FanoutHub(
            perSubscriberCapacity,
            maximumSubscribers,
            subscriberId -> log.warn(
                "Disconnected slow subscriber: {}", subscriberId
            )
        );
    }
}
~~~

Capacity 128 chỉ là giá trị khởi đầu cho demo. Cần chọn dựa trên burst dự kiến, kích thước event, tốc độ tiêu thụ và ngân sách bộ nhớ. Với N subscriber và capacity C, số slot tối đa xấp xỉ N × C, chưa kể object overhead và payload. Giới hạn tổng số subscriber cũng cần được cấu hình để tránh tổng bộ nhớ tăng theo số client không kiểm soát.

### Kết nối hai client thử nghiệm

Khởi động server bằng Gradle:

~~~bash
./gradlew bootRun
~~~

Tạo hai RSocketRequester riêng để mô phỏng hai client độc lập:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester fastRequester = RSocketRequester.builder()
    .connectTcp("localhost", 7000)
    .block(Duration.ofSeconds(5));

RSocketRequester slowRequester = RSocketRequester.builder()
    .connectTcp("localhost", 7000)
    .block(Duration.ofSeconds(5));

FastTelemetryClient fastClient =
    new FastTelemetryClient(fastRequester);
SlowTelemetryClient slowClient =
    new SlowTelemetryClient(slowRequester);

fastClient.start();
slowClient.start();
~~~

API connectTcp có thể khác theo phiên bản Spring Framework; dùng phương thức kết nối TCP tương ứng với dependency của dự án. Hai client mở hai request-stream riêng, vì vậy hub tạo hai queue độc lập. Dừng từng client bằng stop() khi kết thúc thử nghiệm; connection manager của ứng dụng chịu trách nhiệm đóng socket khi không còn interaction nào sử dụng.

## 14. Kiểm thử queue riêng và overflow

Trước tiên kiểm tra một subscription có capacity bằng hai. Khi downstream chưa request, hai event đầu được giữ trong queue; event thứ ba làm stream kết thúc bằng lỗi slow consumer.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.test.StepVerifier;
import com.example.realtime.fanout.FanoutHub;
import com.example.realtime.event.SlowConsumerException;
import com.example.realtime.event.SubscriberLimitException;

class FanoutHubTest {

    @Test
    void shouldFailWhenQueueCapacityIsExceeded() {
        FanoutHub hub = new FanoutHub(2, 10, ignored -> { });

        StepVerifier.create(hub.subscribe(), 0)
            .then(() -> {
                hub.publish("sensor-01", "temperature", 21);
                hub.publish("sensor-01", "temperature", 22);
                hub.publish("sensor-01", "temperature", 23);
            })
            .expectError(SlowConsumerException.class)
            .verify();

        StepVerifier.create(hub.subscribe())
            .then(() -> hub.publish("sensor-01", "temperature", 24))
            .expectNextMatches(event -> event.value() == 24)
            .thenCancel()
            .verify();
    }

    @Test
    void shouldRejectSubscriptionWhenHubIsFull() {
        FanoutHub hub = new FanoutHub(2, 1, ignored -> { });
        Disposable first = hub.subscribe().subscribe();

        StepVerifier.create(hub.subscribe())
            .expectError(SubscriberLimitException.class)
            .verify();

        first.dispose();
        assertEquals(0, hub.subscriberCount());
    }
}
~~~

Test xác nhận queue có giới hạn và channel báo đúng lỗi khi vượt capacity. Việc cô lập giữa hai subscriber được kiểm tra riêng ở phần tiếp theo.

Không dựa vào thời gian sleep để tạo consumer chậm. Điều khiển demand ban đầu bằng StepVerifier hoặc Subscriber tùy chỉnh giúp test lặp lại ổn định.

## 15. Kiểm thử hai subscriber đồng thời

Dùng BaseSubscriber để giữ một subscriber không request và một subscriber request không giới hạn. Cả hai subscribe vào hai channel riêng trước khi producer phát event:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.util.ArrayList;
import java.util.List;
import org.reactivestreams.Subscription;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.BaseSubscriber;
import com.example.realtime.event.SlowConsumerException;
import com.example.realtime.event.TelemetryEvent;
import com.example.realtime.fanout.FanoutHub;

final class ControlledSubscriber<T> extends BaseSubscriber<T> {

    private final List<T> received = new ArrayList<>();
    private final long initialRequest;
    private Throwable failure;

    ControlledSubscriber(long initialRequest) {
        this.initialRequest = initialRequest;
    }

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        if (initialRequest > 0) {
            request(initialRequest);
        }
    }

    @Override
    protected void hookOnNext(T value) {
        received.add(value);
    }

    @Override
    protected void hookOnError(Throwable error) {
        failure = error;
    }

    List<T> received() {
        return received;
    }

    Throwable failure() {
        return failure;
    }

    void cancelSubscription() {
        cancel();
    }
}

class FanoutIsolationTest {

    @Test
    void slowSubscriberDoesNotBlockFastSubscriber() {
        FanoutHub hub = new FanoutHub(2, 10, ignored -> { });
        ControlledSubscriber<TelemetryEvent> fast =
            new ControlledSubscriber<>(Long.MAX_VALUE);
        ControlledSubscriber<TelemetryEvent> slow =
            new ControlledSubscriber<>(0);

        hub.subscribe().subscribe(fast);
        hub.subscribe().subscribe(slow);

        TelemetryEvent first =
            hub.publish("sensor-01", "temperature", 21);
        TelemetryEvent second =
            hub.publish("sensor-01", "temperature", 22);
        TelemetryEvent third =
            hub.publish("sensor-01", "temperature", 23);

        assertEquals(List.of(first, second, third), fast.received());
        assertEquals(List.of(), slow.received());
        assertInstanceOf(SlowConsumerException.class, slow.failure());
        assertEquals(1, hub.subscriberCount());

        fast.cancelSubscription();
        assertEquals(0, hub.subscriberCount());
    }
}
~~~

Test phát ba event khi capacity của slow subscriber là hai, rồi xác nhận:

- Fast subscriber đã nhận các event theo demand của nó.
- Slow subscriber bị ngắt ngay khi queue overflow; các event đang chờ bị bỏ theo chính sách đã chọn.
- Hub còn giữ fast subscriber nhưng đã loại slow subscriber.
- Khi fast subscriber cancel, hub giảm subscriber count.

Các thao tác phát và request trong test chạy tuần tự trên cùng thread để kết quả xác định, không cần sleep hoặc dựa vào timing của scheduler.

## 16. Xử lý reconnect và phát hiện event bị bỏ lỡ

Khi queue đầy, event làm overflow không được giao cho subscriber chậm. Client cần nhận biết đây là lỗi slow consumer, không retry vô hạn với cùng tốc độ xử lý.

Event có sequence number để client phát hiện khoảng trống. Sau khi reconnect, có hai cách:

1. **Snapshot:** client lấy trạng thái mới nhất từ API khác rồi tiếp tục stream mới.
2. **Replay:** client gửi lastSeenSequence và server đọc lại event từ durable store trước khi chuyển sang live stream.

Không thể bảo đảm replay chỉ bằng queue RAM trong FanoutHub. Muốn replay an toàn, cần lưu event bền vững và xử lý ranh giới giữa lịch sử và live stream để không mất event trong lúc chuyển chế độ.

Khi lỗi đi qua RSocket, client thường nhận lỗi ứng dụng đã được transport/framework ánh xạ, không deserialize trực tiếp class Java SlowConsumerException của server. Dùng mã lỗi ổn định SLOW_CONSUMER trong nội dung lỗi hoặc cơ chế error mapping của ứng dụng để client nhận diện; không phụ thuộc tên class exception ở server.

Ví dụ request có cursor:

~~~java
public record SubscribeRequest(long afterSequence) {
}
~~~

Route có thể nhận request payload thay vì method không tham số:

~~~java
@MessageMapping("telemetry.subscribe")
public Flux<TelemetryEvent> subscribe(SubscribeRequest request) {
    return replayService.replayThenLive(request.afterSequence());
}
~~~

replayThenLive cần được triển khai bằng event store có thứ tự và cơ chế nối lịch sử/live không có gap. Đây là phần mở rộng cho yêu cầu độ tin cậy cao; không nên giả định Flux.concat(replay, live) tự động an toàn nếu event mới có thể đến giữa hai lần truy vấn.

## 17. Quan sát và cảnh báo

Trong production, cần quan sát theo từng subscription hoặc theo nhóm subscriber:

| Metric | Mục đích |
|---|---|
| active_subscribers | Số stream hiện đang đăng ký |
| subscriber_overflow_total | Số stream bị ngắt do queue đầy |
| subscriber_queue_capacity | Capacity được cấu hình |
| subscriber_queue_depth | Số event đang chờ, nếu adapter có thể đo |
| events_published_total | Tổng event producer phát |
| events_delivered_total | Tổng event được enqueue thành công |
| events_dropped_total | Tổng event bị loại bỏ |
| subscriber_lifetime_seconds | Thời gian stream tồn tại |

Không dùng subscriber ID hoặc user ID làm label metric có cardinality cao. Đưa ID cụ thể vào log có kiểm soát; metric nên nhóm theo route, loại consumer hoặc lý do overflow.

Đặt cảnh báo khi overflow tăng đột biến, subscriber count tăng bất thường hoặc event processing lag kéo dài. Một vài overflow có thể là hành vi bảo vệ dự kiến; tỷ lệ overflow liên tục cao thường cho thấy client, mạng hoặc capacity cần được xem xét.

## 18. Kiểm thử tải và các kịch bản thực tế

Sau unit test, chạy thử nhiều client với tốc độ khác nhau:

| Client | Tốc độ xử lý giả lập | Kỳ vọng |
|---|---:|---|
| Dashboard nhanh | 100 event/s | Nhận liên tục |
| Browser trung bình | 20 event/s | Nhận khi producer không vượt capacity dài hạn |
| Consumer chậm | 4 event/s | Queue đầy thì stream bị ngắt riêng |
| Consumer ngắt kết nối | 0 event/s sau cancel | Subscription được gỡ khỏi hub |

Thử thêm:

- Nhiều client chậm cùng lúc.
- Một client reconnect liên tục.
- Event payload lớn.
- Producer phát burst rồi trở lại tốc độ bình thường.
- Producer duy trì tốc độ cao lâu hơn thời gian queue có thể hấp thụ.
- Server shutdown trong khi stream còn hoạt động.
- Một client hủy stream trong lúc producer đang publish.

Đo heap, direct memory, queue depth, CPU, event rate và overflow. Kiểm tra rằng số subscriber trong hub trở về mức dự kiến sau cancel, error hoặc disconnect.

## 19. Các giới hạn cần xử lý trước production

FanoutHub trong bài là implementation trong bộ nhớ của một instance. Khi triển khai production, cần bổ sung:

- Giới hạn tổng số subscriber và xác thực quyền subscribe theo tenant/user.
- Giới hạn kích thước payload và byte budget theo subscriber.
- Metric queue depth thực tế và cảnh báo overflow.
- Chính sách shutdown để hoàn tất hoặc hủy các stream đang hoạt động.
- Event store/broker bền vững nếu cần replay hoặc không được mất dữ liệu.
- Cơ chế chống một client mở nhiều subscription để chiếm tài nguyên.
- Chính sách rate limit và quota theo người dùng.
- Kiểm thử nhiều instance; mỗi instance trong ví dụ chỉ biết subscriber kết nối tới chính nó.

Nếu chạy nhiều server instance, cần quyết định producer phát event tới tất cả instance hay dùng broker để fan-out. Một local FanoutHub không tự đồng bộ subscriber giữa các instance.

Sequence được tạo bằng AtomicLong trong ví dụ chỉ duy nhất trong vòng đời của một FanoutHub. Khi process restart hoặc chạy nhiều instance, sequence này không còn là cursor toàn cục. Với replay production, dùng offset của partition trong durable log hoặc một sequence được cấp phát bền vững và có phạm vi rõ ràng.

## 20. Checklist nghiệm thu

- [ ] Mỗi request-stream có channel unicast và queue riêng.
- [ ] Queue có capacity hữu hạn.
- [ ] Consumer chậm bị ngắt riêng khi overflow.
- [ ] Consumer nhanh tiếp tục nhận event.
- [ ] Client cancel làm hub gỡ channel.
- [ ] Không có subscription bị tạo tách rời khỏi lifecycle RSocket.
- [ ] Event có sequence để phát hiện khoảng dữ liệu bị bỏ lỡ.
- [ ] Metric ghi nhận overflow và subscriber count.
- [ ] Chính sách replay/snapshot được xác định cho dữ liệu cần đầy đủ.
- [ ] Tổng số subscriber và bộ nhớ được giới hạn.

## 21. Kết luận

Phân phối realtime tới nhiều bên nhận có tốc độ khác nhau cần cô lập trạng thái tiêu thụ của từng subscriber. Một queue riêng, có giới hạn cho mỗi request-stream giúp consumer nhanh tiếp tục hoạt động khi consumer khác chậm. Khi queue đầy, hệ thống có thể ngắt riêng stream chậm và ghi nhận overflow.

Chính sách này bảo vệ bộ nhớ và độ trễ của các consumer còn lại, nhưng event bị overflow không tự được khôi phục. Với dữ liệu cần đầy đủ, hãy kết hợp sequence number với durable event store hoặc broker và replay theo cursor. Khi triển khai RSocket, luôn quản lý subscription, demand, cancellation và tổng ngân sách queue như các phần của cùng một thiết kế realtime.
