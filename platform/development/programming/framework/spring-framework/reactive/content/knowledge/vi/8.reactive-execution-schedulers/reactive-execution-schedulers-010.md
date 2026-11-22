# Trạng thái dùng chung và tính an toàn luồng giữa nhiều subscription

## 1. Vấn đề cần hiểu

Trong Spring WebFlux và Project Reactor, cùng một `Flux<T>` hoặc `Mono<T>` có thể được nhiều Subscriber đăng ký: hai HTTP request, hai nhánh tiêu thụ dữ liệu, một lần thử lại, hoặc nhiều client của một luồng sự kiện. Ứng dụng cũng có thể chuyển thread khi dùng `subscribeOn`, `publishOn`, scheduler, I/O bất đồng bộ và các toán tử đồng thời.

Hai câu hỏi phải được trả lời riêng:

1. **Trạng thái này thuộc về ai?** Mỗi subscription cần một bản riêng, hay mọi subscription cố ý dùng chung?
2. **Ai có thể truy cập trạng thái ấy đồng thời?** Nếu có nhiều thread, thao tác đọc/ghi phải bảo đảm nguyên tử, visibility và các bất biến nghiệp vụ như thế nào?

Nếu bỏ qua câu thứ nhất, một subscription có thể kế thừa bộ đếm, collection hoặc kết quả tạm của subscription khác dù chạy tuần tự. Nếu bỏ qua câu thứ hai, các cập nhật cùng lúc có thể bị mất hoặc làm cấu trúc dữ liệu không nhất quán. Một `AtomicInteger` có thể giải quyết race của một counter nhưng **không** tự cô lập dữ liệu theo Subscriber.

Bài học bao gồm ranh giới Publisher–Subscription, biến được lambda capture, Java Memory Model, cách dùng `Flux.defer`, `generate`, `transformDeferred`, toán tử stateful, Reactor `Context`, shared/hot publishers, Spring singleton, concurrency-safe sinks, ví dụ Java 17+ và kiểm thử.

## 2. Một Publisher có thể được subscribe nhiều lần

Publisher mô tả quy trình phát dữ liệu. Subscriber gọi `subscribe` để thiết lập một `Subscription`, sau đó dùng `request(n)` hoặc `cancel()` để điều phối. Với nguồn *cold* như `Flux.range` và `Flux.just`, mỗi lượt đăng ký thường nhận một lượt phát dữ liệu mới; tuy nhiên **các closure Java đã tạo trước đó không tự được nhân bản**.

~~~text
                    Flux được lắp ghép
                           |
                  +--------+--------+
                  |                 |
              subscribe A       subscribe B
                  |                 |
            Subscription A    Subscription B
              demand A          demand B
              cancel A          cancel B
                  |                 |
                  +------ cùng tham chiếu? -----+
                                               |
                                  object mutable dùng chung
~~~

Reactive Streams quy tắc Publisher 1.3 yêu cầu `onSubscribe`, `onNext`, `onError`, `onComplete` được gửi **tuần tự trong từng subscription**, tức không có hai callback đồng thời xâm nhập Subscriber của cùng subscription; nếu chuyển thread, cần đảm bảo *happens-before* giữa các tín hiệu. **Quy tắc này không đồng bộ hóa các subscription khác nhau.**

~~~text
Subscription A: onNext(1) ── onNext(2) ── onComplete
Subscription B:      onNext(X) ── onNext(Y) ── onComplete

Hai dòng có thể cùng hoạt động trên các thread khác nhau.
~~~

Hơn nữa, dù tín hiệu tới một downstream Subscriber được serialize, side effect do hai inner publisher trong `flatMap` gây ra vẫn có thể chạy đồng thời. Đừng coi thứ tự callback downstream là khóa bảo vệ chung cho field trong singleton service hoặc tài nguyên bên ngoài.

## 3. Các loại trạng thái và phạm vi sở hữu

| Loại trạng thái | Ví dụ | Phạm vi thông thường | Quy tắc |
| --- | --- | --- | --- |
| Biến tạo tại assembly rồi bị lambda capture | `AtomicInteger counter` khai báo trước `map` | Cùng tham chiếu có thể được nhiều subscriptions dùng | Chỉ chia sẻ khi chủ đích |
| Biến tạo trong factory mỗi subscription | Biến trong `Flux.defer` hoặc `transformDeferred` | Riêng từng subscription nếu factory tạo đối tượng mới | Dùng cho tiến độ, đếm thứ tự, xử lý request |
| Trạng thái do operator Reactor quản lý | `distinct`, `scan`, `buffer`, `collectList` | Thường theo subscription theo hợp đồng toán tử | Ưu tiên toán tử chuẩn thay vì collection ngoài |
| Field của Spring bean singleton | Cache, counter, `Map`, helper mutable | Nhiều request/subscriptions cùng thấy | Bất biến hoặc đồng bộ đúng |
| Hot/multicast publisher, sink, cache | `Sinks.Many`, `share`, `cache` | Có thể chia sẻ source, tín hiệu hoặc payload | Kiểm tra vòng đời và quy tắc ownership |

**Cần phân biệt biến và đối tượng.** Một biến tham chiếu `final` chỉ không thể gán lại; nếu nó trỏ đến `ArrayList` hoặc `AtomicInteger`, nội dung đối tượng vẫn có thể thay đổi. Một biến local nằm trong thân `map(value -> { ... })` được tạo mỗi lần lambda chạy, nhưng biến local đặt **bên ngoài** lambda và được capture có thể tồn tại qua nhiều lượt đăng ký.

Ví dụ:

~~~java
AtomicInteger counter = new AtomicInteger();

Flux<Integer> counts = Flux.just(10, 20)
        .map(value -> counter.incrementAndGet());
~~~

Mỗi `subscribe` vào `counts` chạy lại các `onNext`, nhưng `counter` chỉ được tạo một lần khi xây `counts`. Nếu subscribe hai lần tuần tự, lượt đầu nhận 1, 2; lượt sau nhận 3, 4. Counter là thread-safe nhưng **shared**. Đây có thể đúng nếu là metric toàn cục, và sai nếu là chỉ số riêng của mỗi request.

## 4. Data race và Java Memory Model

Xét một bean giữ counter mutable:

~~~java
class UnsafeCounter {
    private int count;

    void increment() {
        count++;   // đọc → cộng → ghi, không nguyên tử
    }

    int get() {
        return count;
    }
}
~~~

Hai thread có thể cùng đọc `count = 7`, cùng tính 8 và cùng ghi 8. Hai lần tăng bị gộp thành một (*lost update*). Không có đồng bộ thích hợp còn gây vấn đề *visibility*: thread này chưa chắc quan sát được cập nhật mới của thread khác.

Đánh dấu `volatile int count` hỗ trợ visibility và ordering cho truy cập field nhưng **không biến `count++` thành thao tác nguyên tử**. Để có một counter tổng cố ý dùng chung:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SafeCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

Nếu cập nhật rất thường xuyên và chỉ cần một metric tổng, `LongAdder` có thể giảm tranh chấp, nhưng `sum()` đang chạy đồng thời với cập nhật không phải ảnh chụp tuyến tính hóa của toàn bộ hệ thống. Nếu hai field phải thay đổi như **một bất biến** (ví dụ số dư và phiên bản), hai `AtomicInteger` độc lập chưa đủ; cần một thuật toán CAS trên immutable snapshot, khóa bảo vệ trạng thái, actor/queue xử lý tuần tự hoặc transaction thích hợp.

`ConcurrentHashMap` hỗ trợ truy cập concurrent, nhưng chuỗi `get → tính toán → put` không đương nhiên nguyên tử cho cùng key. Khi cần cập nhật có điều kiện theo key, dùng `compute`/`merge` hoặc cơ chế nhất quán khác theo hợp đồng ứng dụng. Với thao tác nghiệp vụ trải nhiều database/service, khóa trong JVM không thay thế transaction và concurrency control ngoài tiến trình.

## 5. Isolation đúng chỗ với Flux.defer

`Flux.defer(Supplier<? extends Publisher<T>>)` gọi Supplier khi **mỗi lần subscribe** vào Flux kết quả. Đây là nơi phù hợp để cấp phát một counter hoặc một đối tượng state cho từng lượt:

~~~java
Flux<String> local = Flux.defer(() -> {
    AtomicInteger index = new AtomicInteger();
    return Flux.just("A", "B")
            .map(s -> index.incrementAndGet() + ":" + s);
});
~~~

Subscriber S1 và S2 đều nhận `1:A`, `2:B` (với nguồn cold này). Trạng thái được tạo trong supplier rồi capture bởi các lambda thuộc chính Publisher tạo ra cho lượt ấy.

So sánh trường hợp vẫn sai:

~~~java
AtomicInteger shared = new AtomicInteger();

Flux<String> stillShared = Flux.defer(() ->
        Flux.just("A", "B")
            .map(s -> shared.incrementAndGet() + ":" + s)
);
~~~

`defer` gọi Supplier nhiều lần, nhưng `shared` nằm **ngoài Supplier**, nên vẫn là object duy nhất. Từ khóa `defer` không sao chép các object được closure bắt giữ.

Khi muốn tái sử dụng cả đoạn xử lý trên một source cho mỗi subscription, dùng `transformDeferred`:

~~~java
Flux<String> numbered = Flux.just("A", "B")
        .transformDeferred(source -> {
            AtomicInteger index = new AtomicInteger();
            return source.map(s -> index.incrementAndGet() + ":" + s);
        });
~~~

`transformDeferred` áp dụng transformer với từng subscription, giúp khởi tạo state trong thân transformer. Trái lại, `transform` áp dụng transformer ngay khi lắp ghép pipeline, khiến state được tạo trong transformer có thể bị dùng chung khi Subscribe lặp. `defer` trì hoãn **tạo source hoặc pipeline**, còn `transformDeferred` trì hoãn **ghép đoạn toán tử** nhận một source đã có. Không nhất thiết dùng cả hai ở mọi nơi.

Lưu ý `retry` và `repeat` có thể đăng ký lại upstream. Cụm từ “per subscription” phải chỉ rõ **subscription tại toán tử nào**. Nếu kết quả `defer` được đưa qua `cache()` hoặc `share()`, số lần subscribe upstream có thể khác số Subscriber downstream.

## 6. Ưu tiên stateful operator chuẩn

### 6.1. scan thay cho biến cộng dồn bên ngoài

~~~java
Flux<Integer> sums = Flux.just(1, 2, 3)
        .scan(0, Integer::sum);

sums.subscribe(System.out::println);
~~~

Stdout:

~~~text
0
1
3
6
~~~

`scan` phát seed 0 trước, sau đó tổng 1, 3, 6. Với các giá trị kiểu bất biến `Integer`, state tích lũy được quản lý theo subscription. Điều này giảm nguy cơ lẫn dữ liệu giữa subscriptions so với viết `doOnNext(n -> sharedTotal += n)`.

Nếu seed là một **đối tượng mutable được tạo sẵn và capture**, vẫn cần phân tích khả năng chia sẻ reference; ưu tiên immutable accumulator hoặc overload cung cấp state bằng supplier nếu API yêu cầu.

### 6.2. distinct và collectList

~~~java
Flux<String> unique =
        Flux.just("A", "A", "B").distinct();

Mono<java.util.List<String>> list =
        Flux.just("A", "B").collectList();
~~~

Theo Javadoc Reactor, `distinct` theo dõi phần tử đã thấy **cho mỗi Subscriber**, còn `collectList` gom dữ liệu của lượt đăng ký đó. Không thay bằng một `ArrayList` khai báo ngoài pipeline rồi `doOnNext(list::add)`: các subscriptions có thể làm danh sách lẫn nội dung và ghi đồng thời không an toàn.

### 6.3. Flux.generate cho state riêng

Khi tự tạo một luồng đồng bộ dựa trên trạng thái, overload `Flux.generate(stateSupplier, generator)` gọi stateSupplier cho **từng Subscriber**:

~~~java
Flux<Integer> generated = Flux.generate(
        () -> 1,
        (state, sink) -> {
            if (state <= 3) {
                sink.next(state);
                return state + 1;
            }
            sink.complete();
            return state;
        }
);
~~~

Mỗi Subscriber nhận 1, 2, 3 rồi complete. `Flux.generate` dùng `SynchronousSink`, phát tối đa một tín hiệu dữ liệu trong mỗi lần gọi generator. Không phát nhiều `onNext` đồng thời từ các thread khác nhau trong generator. Có overload với consumer giải phóng state; tài nguyên có vòng đời theo subscription cũng có thể được quản lý bằng `Flux.using` / `usingWhen`.

**Không có quy tắc mọi toán tử Reactor đều tạo state riêng:** `share`, `cache`, `replay` và một số cơ chế multicast chủ động thay đổi cách nguồn được dùng chung.

## 7. Ví dụ Java 17+ chạy độc lập: shared vs per-subscription

Ví dụ chủ động dùng hai subscriptions **tuần tự** để chứng minh sự rò trạng thái mà không phụ thuộc vào race hoặc timing ngẫu nhiên.

Tạo dự án:

~~~text
reactor-state-demo/
├── build.gradle
└── src/main/java/SubscriptionStateDemo.java
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'SubscriptionStateDemo'
}
~~~

Tệp `src/main/java/SubscriptionStateDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;

public class SubscriptionStateDemo {

    private static void show(String label, Flux<String> source) {
        System.out.print(label + ": ");
        source.collectList().subscribe(System.out::println);
    }

    public static void main(String[] args) {
        AtomicInteger sharedCounter = new AtomicInteger();

        Flux<String> shared = Flux.just("A", "B")
                .map(value ->
                        sharedCounter.incrementAndGet() + ":" + value);

        Flux<String> isolated = Flux.defer(() -> {
            AtomicInteger localCounter = new AtomicInteger();
            return Flux.just("A", "B")
                    .map(value ->
                            localCounter.incrementAndGet() + ":" + value);
        });

        show("shared S1", shared);
        show("shared S2", shared);
        show("isolated S1", isolated);
        show("isolated S2", isolated);

        System.out.println("shared total: " + sharedCounter.get());
    }
}
~~~

Ở thư mục chứa `build.gradle`, chạy với Gradle đã cài:

~~~bash
gradle -q run
~~~

Hoặc dùng wrapper `./gradlew -q run` nếu dự án có wrapper trên Linux/macOS, `gradlew.bat -q run` trên Windows. Stdout do **chương trình** phát ra:

~~~text
shared S1: [1:A, 2:B]
shared S2: [3:A, 4:B]
isolated S1: [1:A, 2:B]
isolated S2: [1:A, 2:B]
shared total: 4
~~~

`Flux.just`/`collectList` trong chương trình không có scheduler bất đồng bộ nên `subscribe` xử lý ngay, thứ tự đầu ra cố định. Counter `sharedCounter` là cùng object qua S1 và S2; counter ở trong `defer` được cấp phát riêng. Dùng `AtomicInteger` ở shared branch giúp một phép tăng atomic nếu có concurrency, nhưng nó không biến shared branch thành per-subscription branch.

Đừng chứng minh thread safety bằng việc thấy stdout “có vẻ đúng” trong một lần chạy. Kiểm thử hành vi isolation và metric global ở mục 11 dùng các bất biến xác định.

## 8. Scheduler, ThreadLocal và Reactor Context

`Flux`/`Mono` không tự đồng nghĩa với một thread chuyên dụng. Nhiều toán tử chạy trên thread phát của upstream. `subscribeOn` thay đổi ngữ cảnh đăng ký/nguồn; `publishOn` chuyển phần downstream sang scheduler được chọn. Một subscription có thể đổi thread trong vòng đời và cùng một worker thread có thể xử lý nhiều subscription khác nhau.

~~~text
Request A: event-loop-1 → publishOn → parallel-2 → Subscriber A
Request B: event-loop-1 → publishOn → parallel-1 → Subscriber B
~~~

Đây là **sơ đồ minh họa**, thread thực tế phụ thuộc scheduler và ứng dụng. Tín hiệu của cùng subscription vẫn phải tuân theo quy tắc serialize, nhưng hai subscriptions có thể chạy đồng thời và cùng đọc/ghi một object mà chúng được cấp.

**ThreadLocal không phải subscription-local state.** Khi chuyển thread, giá trị ThreadLocal không tự đi cùng subscription; khi thread pool tái sử dụng thread có nguy cơ giữ thông tin request cũ nếu quản lý sai. Trong mã Reactor, dùng `Context` để mang metadata như trace ID/correlation ID theo subscription.

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> source = Mono.deferContextual(context ->
        Mono.just("trace=" + context.get("traceId")));

source.contextWrite(Context.of("traceId", "req-100"))
      .subscribe(System.out::println);
~~~

Với nguồn đồng bộ này, stdout:

~~~text
trace=req-100
~~~

`contextWrite` thêm giá trị vào Context nhìn thấy ở phía upstream; `deferContextual` đọc nó theo subscription. Context là cấu trúc key/value bất biến về thao tác thêm/xóa key, **nhưng object được lưu trong value vẫn có thể mutable và bị chia sẻ** nếu nhiều subscriptions nhận cùng reference. Không đặt `ArrayList` dùng chung vào Context rồi nghĩ đã được isolation.

Những tích hợp MDC/ThreadLocal có cơ chế propagation đặc thù có thể hoạt động khi được cấu hình đúng; không giả định ThreadLocal sẽ luôn đúng sau `publishOn` nếu không có cơ chế propagation cụ thể.

## 9. Nguồn cold, hot, share và cache

Một nguồn cold như `Flux.range` thường tạo quá trình phát cho từng Subscriber, nhưng không clone object ứng dụng capture tại assembly. Một hot source như `Sinks.Many` có thể phát cùng sự kiện cho nhiều Subscriber hiện đang lắng nghe. Nếu payload là object mutable, các Subscriber có thể tác động **cùng một object** ở các thread khác nhau.

`share()` kết nối nhiều Subscriber downstream với một upstream đang hoạt động; người subscribe sau có thể bỏ lỡ sự kiện đã phát. `cache()` có thể ghi nhớ dữ liệu/terminal để phát lại cho Subscriber sau, và có thể chỉ subscribe upstream một lần. Nguồn có state theo subscription **trước cache** sẽ không đương nhiên được tái chạy cho mỗi downstream Subscriber.

~~~java
Flux<String> upstream = Flux.defer(() -> {
    AtomicInteger n = new AtomicInteger();
    return Flux.just("x", "y")
            .map(s -> n.incrementAndGet() + ":" + s);
});

Flux<String> cached = upstream.cache();
~~~

Đây là snippet minh họa, cần import `Flux`/`AtomicInteger` trong ứng dụng. Sau khi `cached` đã được subscribe và cache lưu dữ liệu, những Subscriber tiếp theo có thể nhận lại kết quả đã cache mà không tạo counter mới ở `upstream`. Vì vậy hãy xác định **vị trí operator và vòng đời kết nối** trước khi bảo đảm state độc lập.

Nếu một payload chứa List/Map mutable, ưu tiên gửi bản immutable hoặc defensive copy cần thiết (ví dụ `List.copyOf` trong Java 17) để tránh hai Subscribers sửa cùng reference. Java `record` chỉ cố định tham chiếu field; một record chứa List mutable vẫn có thể cần copy bảo vệ.

## 10. Nhiều producer và Sinks.Many

Khi kết nối nhiều producer callback vào một Flux, **serial signaling** và **tính đúng đắn dữ liệu dùng chung** đều phải được xử lý. Reactor `Sinks.Many` có API kiểm soát phát và báo thất bại:

~~~java
import reactor.core.publisher.Sinks;

Sinks.Many<String> sink = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Sinks.EmitResult result = sink.tryEmitNext("event");
if (result.isFailure()) {
    // Xử lý lỗi phát theo chính sách của ứng dụng.
}
~~~

Đây là đoạn minh họa API, không có `main` độc lập. Với safe sinks, khi nhiều thread tranh chấp phát cùng lúc, `tryEmitNext` có thể trả `FAIL_NON_SERIALIZED`. Các kết quả như `FAIL_OVERFLOW`, `FAIL_TERMINATED`, `FAIL_ZERO_SUBSCRIBER` báo các tình huống thất bại khác tùy cấu hình sink. **Đừng bỏ qua EmitResult** rồi mặc định sự kiện đã được chuyển đi.

Khi cần, dùng một hàng đợi/actor có một producer phát vào sink, hoặc `emitNext` với handler retry đúng loại thất bại và có giới hạn. Không dùng spin vô hạn hoặc resend không kiểm tra vì có thể tạo tải hay phát trùng. `Sinks.unsafe()` không bảo vệ phát đồng thời như safe sinks, chỉ dành cho nơi caller tự đảm bảo serialization.

Một sink serialize tín hiệu chưa chắc giải quyết được **backpressure**: producer nhanh hơn consumer vẫn có thể gặp overflow, mất dữ liệu hoặc dồn buffer. Cần kế hoạch demand, giới hạn bộ nhớ và chính sách nghiệp vụ độc lập.

## 11. Kiểm thử isolation và concurrent shared metric

Trong dự án có `reactor-test` và JUnit 5 ở test scope, có thể bổ sung Gradle:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/test/java/SubscriptionStateTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class SubscriptionStateTest {
    @Test
    void freshStatePerSubscribe() {
        Flux<Integer> isolated = Flux.defer(() -> {
            AtomicInteger n = new AtomicInteger();
            return Flux.just("A", "B")
                    .map(value -> n.incrementAndGet());
        });

        StepVerifier.create(isolated)
                .expectNext(1, 2)
                .verifyComplete();
        StepVerifier.create(isolated)
                .expectNext(1, 2)
                .verifyComplete();
    }

    @Test
    void capturedStateRemainsShared() {
        AtomicInteger count = new AtomicInteger();
        Flux<Integer> shared = Flux.just("A", "B")
                .map(value -> count.incrementAndGet());

        StepVerifier.create(shared)
                .expectNext(1, 2)
                .verifyComplete();
        StepVerifier.create(shared)
                .expectNext(3, 4)
                .verifyComplete();
    }

    @Test
    void atomicMetricCountsUpdatesFromTwoPipelines() {
        AtomicInteger total = new AtomicInteger();

        Mono<Void> a = Flux.range(1, 1_000)
                .publishOn(Schedulers.parallel())
                .doOnNext(value -> total.incrementAndGet())
                .then();

        Mono<Void> b = Flux.range(1, 1_000)
                .publishOn(Schedulers.parallel())
                .doOnNext(value -> total.incrementAndGet())
                .then();

        StepVerifier.create(Mono.when(a, b)).verifyComplete();
        assertEquals(2_000, total.get());
    }
}
~~~

Test 1 chứng minh state ở `defer` reset cho mỗi lượt. Test 2 chứng minh captured counter chung, ngay cả khi không chạy đồng thời. Test 3 kiểm tra tổng phép cập nhật nguyên tử khi hai pipelines có thể chạy ở các worker khác nhau và đã hoàn thành. Tùy máy, scheduler có thể dùng ít thread; **một test xanh không chứng minh mọi truy cập shared trong ứng dụng đều thread-safe**.

Đừng tạo test kỳ vọng `int count++` luôn mất update: race xảy ra tùy lịch trình và có thể không tái hiện ở lần chạy cụ thể. Kiểm thử bất biến và dùng công cụ stress/concurrency phù hợp khi có nguy cơ race thực.

## 12. Spring WebFlux và singleton service

Spring service theo mặc định thường là singleton trong application context, nên nhiều HTTP request có thể gọi cùng instance. Field mutable trong service là shared state giữa các request; state của **mỗi subscription** nên được cấp phát riêng.

Ví dụ trong dự án Spring Boot WebFlux:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public final class EventLabelService {

    // Metric toàn ứng dụng: cố ý chia sẻ.
    private final LongAdder totalProcessed = new LongAdder();

    public Flux<String> label(Flux<String> events) {
        return Flux.defer(() -> {
            // Chỉ số theo subscription.
            AtomicInteger perSubscription = new AtomicInteger();

            return events.map(event -> {
                totalProcessed.increment();
                return perSubscription.incrementAndGet() + ":" + event;
            });
        });
    }

    public long approximateTotal() {
        return totalProcessed.sum();
    }
}
~~~

Đây là lớp service minh họa, **không phải chương trình có `main`**. `totalProcessed` là metric chủ ý dùng chung; `LongAdder` hỗ trợ cập nhật concurrent. `sum()` không phải ảnh chụp nhất quán tuyệt đối trong lúc có updates, nên không dùng như số dư giao dịch. `perSubscription` đặt trong `Flux.defer` nên mỗi subscription vào kết quả `label` có counter riêng.

Khi controller trả `Mono` hoặc `Flux`, Spring WebFlux quản lý subscription/cancellation. Không gọi `subscribe()` thủ công trong handler chỉ để cập nhật một field rồi trả response; side effect cần nằm đúng trong pipeline hoặc workflow riêng có hợp đồng rõ. Nếu state là tài nguyên có vòng đời (connection, cursor, session), dùng `using`/`usingWhen` để cleanup khi complete, error **và cancel**, thay vì giữ trong field singleton.

Khi retry, repeat hoặc một request thực sự được subscribe nhiều lần, side effect trong `doOnNext` có thể chạy lặp. `doOnNext` không tạo bảo đảm exactly-once. Nếu side effect là thanh toán/ghi DB, dùng idempotency key, transaction, message acknowledgement hoặc thiết kế lưu trữ phù hợp.

## 13. Bảng quyết định kỹ thuật

| Mục tiêu | Cách làm | Giới hạn |
| --- | --- | --- |
| Bộ đếm/tập trạng thái riêng của từng subscription | `defer`, `generate(stateSupplier)`, `transformDeferred`, toán tử `scan`/`distinct` | Cấp phát state bên trong factory, xem `cache/share` |
| Truyền đối tượng giữa các thread/subscribers | Immutable value, defensive copy nếu cần | Record chứa collection mutable vẫn có thể bị sửa |
| Bộ đếm metric toàn cục | `AtomicLong`, `LongAdder` | Không thay thế transaction nghiệp vụ |
| Map cache dùng chung | `ConcurrentHashMap`, cập nhật qua `compute/merge` | Nhiều bước liên quan nhau vẫn cần bất biến |
| Nhiều field cập nhật thống nhất | Immutable snapshot/CAS, khóa, actor hoặc transaction | Nhiều atomic độc lập không tạo transaction |
| Trace id theo subscription qua scheduler | Reactor `Context` và API contextual | Context value vẫn có thể dùng chung nếu là object mutable |
| Nhiều producer cùng gửi sự kiện | Safe `Sinks.Many`, xử lý `EmitResult`, queue một đầu phát | Cần thêm chính sách backpressure |
| State quản lý resource | `using`/`usingWhen` | Cleanup cả khi lỗi, hủy và retry |

Không coi mọi thứ là shared state cần khóa. Nếu có thể giải bài toán bằng **dữ liệu bất biến + hàm thuần + state theo subscription**, mã thường dễ suy luận và kiểm thử hơn. Nếu phải dùng chung, xác định chính xác bất biến nào cần bảo vệ, phạm vi đồng bộ và hiệu quả dưới tải.

## 14. Lỗi phổ biến và cách khắc phục

1. **Dùng `ArrayList` làm field của Spring singleton rồi `doOnNext(list::add)`:** các subscriptions trộn dữ liệu và có thể ghi đồng thời. Chọn `collectList` cho từng subscription hoặc concurrent storage với ownership rõ.
2. **Cho rằng per-subscription serialized signals bảo vệ field dùng chung:** hai subscriptions có thể chạy đồng thời. Cần state riêng hoặc cơ chế đồng bộ.
3. **Dùng `volatile` để làm `count++` nguyên tử:** volatile không giải quyết lost update. Dùng atomic increment hoặc lock.
4. **Đưa `AtomicInteger` bên ngoài `Flux.defer` rồi nghĩ đã reset:** object vẫn bị lambda capture. Cấp phát bên trong Supplier.
5. **Dùng `ThreadLocal` làm request state với `publishOn`:** thông tin có thể không đi theo subscription. Dùng Reactor `Context` hoặc propagation được cấu hình đúng.
6. **Dùng `share` hoặc `cache` và mong upstream chạy riêng cho từng Subscriber:** nguồn upstream có thể đã được chia sẻ hoặc cache. Xác định ranh giới đặt toán tử.
7. **Cho rằng immutable record làm toàn bộ object graph immutable:** field collection mutable vẫn cần defensive copy.
8. **Dùng `ConcurrentHashMap` nhưng thao tác get-then-put vẫn có race nghiệp vụ:** dùng atomic map methods hoặc cơ chế tổng thể.
9. **Bỏ qua `FAIL_NON_SERIALIZED` khi phát từ nhiều producer:** event có thể không được chấp nhận. Xử lý kết quả và serialize phát khi cần.
10. **Ghi DB ở `doOnNext` rồi retry vô hạn:** side effect có thể lặp, gây dữ liệu trùng. Thiết kế idempotency, giới hạn retry và kiểm soát commit.
11. **Chỉ chạy test với một Subscriber:** state leakage có thể không lộ ra. Kiểm thử hai lần subscribe cùng Publisher, rồi concurrency cho tài nguyên thật sự shared.
12. **Tưởng `subscribeOn`/`publishOn` tự khiến mutable object thread-safe:** scheduler chỉ điều khiển nơi chạy, không thêm atomicity hoặc isolation.

Quan sát production bằng metric, log gắn correlation id theo Context và test có ít nhất hai subscriptions. Muốn tìm nguồn leak, kiểm tra **nơi biến được tạo và reference được capture**, chứ không chỉ số thread đang xuất hiện trong log.

## 15. Tự kiểm tra

1. Một Flux có counter tạo ngoài `map` được subscribe hai lần tuần tự: counter có tự reset không? **Không; các lượt dùng chung reference.**
2. Counter `AtomicInteger` dùng chung có giải quyết yêu cầu “mỗi request bắt đầu từ 1” không? **Không; nó chỉ giúp tăng nguyên tử.**
3. `Flux.defer` có tự sao chép các object nằm ngoài Supplier không? **Không.**
4. Vì sao các callback `onNext` serialize trong một subscription mà field singleton vẫn race? **Vì hai subscriptions khác có thể chạy cùng lúc trên field đó.**
5. `volatile int count` có làm `count++` atomic không? **Không.**
6. `Flux.generate(stateSupplier, generator)` tạo state khi nào? **Theo mỗi lần Subscriber đăng ký.**
7. `distinct` trong một Flux cold theo dõi các giá trị đã thấy của ai? **Theo từng Subscriber.**
8. Khi thêm `cache` sau `defer`, có chắc mỗi Subscriber downstream kích hoạt Supplier mới không? **Không.**
9. Muốn truyền correlation id qua thread hops theo subscription dùng gì? **Reactor `Context`.**
10. `FAIL_NON_SERIALIZED` ở `Sinks.EmitResult` báo gì? **Phát vào sink không được tuần tự hóa.**
11. Hai atomic counters cho `balance` và `version` có đủ để cập nhật cả cặp như một giao dịch không? **Không.**
12. Vì sao `doOnNext` không đảm bảo side effect exactly-once? **Retry/repeat hoặc subscribe lại có thể thực thi callback nhiều lần.**

**Ghi nhớ:** Subscription là phạm vi bảo đảm giao thức tín hiệu, không phải cơ chế tự động cô lập tất cả object Java. Dùng factory theo subscription hoặc toán tử stateful chuẩn khi state thuộc một Subscriber; với tài nguyên cần dùng chung, chủ động chọn thiết kế bất biến, nguyên tử, đồng bộ, và cơ chế nhất quán nghiệp vụ.

## Tài liệu tham khảo

- [Reactive Streams JVM specification — rule 1.3, serial signaling và happens-before](https://github.com/reactive-streams/reactive-streams-jvm).
- [Project Reactor Flux Javadoc — defer, generate, distinct, share, cache, using](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor Reference Guide — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
- [Project Reactor Reference Guide — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor Sinks.EmitResult — FAIL_NON_SERIALIZED và các lỗi phát](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html).
- [Project Reactor Reference Guide — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
