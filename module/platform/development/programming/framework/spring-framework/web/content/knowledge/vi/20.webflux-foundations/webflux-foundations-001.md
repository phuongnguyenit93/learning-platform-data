# Reactive Streams: Publisher, Subscriber và Subscription trong Spring WebFlux

## 1. Mục tiêu và phạm vi

Ứng dụng WebFlux có thể nhận, xử lý và trả về các luồng dữ liệu không đồng bộ mà không bắt buộc chiếm một thread riêng chỉ để chờ I/O. Đằng sau `Mono`, `Flux` và phần lớn pipeline phản ứng trong WebFlux là **Reactive Streams**, một giao thức nhỏ để thành phần phát dữ liệu và thành phần tiêu thụ dữ liệu trao đổi tín hiệu với **backpressure** — khả năng bên nhận kiểm soát nhu cầu nhận phần tử.

Bài này giải thích đúng bản chất ba giao diện `Publisher<T>`, `Subscriber<T>` và `Subscription`; đi từ trình tự tín hiệu, `request(n)`, `cancel()` tới ví dụ Java 17, Project Reactor và Spring WebFlux. Nội dung tương thích về mặt khái niệm với **Spring Framework 6.x, Spring Boot 3.x, Java 17+**, tập trung ở nền tảng Reactive Streams JVM và HTTP reactive stack.

Sau khi học, bạn có thể:

- Nêu chính xác vai trò Publisher, Subscriber, Subscription và phân biệt chúng với các HTTP request/controller.
- Vẽ được trình tự `onSubscribe → onNext* → (onError | onComplete)?`; biết khi nào chuỗi kết thúc hay bị hủy.
- Phân tích `request(n)` dương, nhu cầu tích lũy, `Long.MAX_VALUE` và tính chất không phát vượt nhu cầu.
- Giải thích tại sao `request(0)`/`request(-1)` là vi phạm hợp đồng, tại sao `cancel` không bảo đảm dừng ngay.
- Hiểu backpressure **không đồng nghĩa** non-blocking, async, tự sinh thread, queue vô hạn hoặc dừng nguồn nóng.
- Sử dụng Reactor `Flux`/`Mono`, `BaseSubscriber`, `StepVerifier`, các toán tử `map`/`filter`/`flatMap`/`publishOn`/`subscribeOn` đúng kỳ vọng.
- Viết ứng dụng WebFlux ngắn với `Flux`/`Mono` và HTTP streaming; biết không tự `subscribe()` trong controller để tạo response.
- Kiểm thử tín hiệu, demand, cancellation, lỗi, terminal signal và phần HTTP boundary qua `curl`/`WebTestClient`.

**Không nhầm WebFlux với Spring MVC async.** MVC cũng có thể trả một số reactive types nhưng xử lý HTTP qua Servlet stack; WebFlux xây trên reactive contract và non-blocking I/O. Không phải mọi dependency bên trong pipeline tự nhiên trở thành non-blocking: gọi JDBC hay `Thread.sleep` trên event loop vẫn có thể chặn.

## 2. Tại sao Reactive Streams ra đời?

Trong synchronous pull model, bên tiêu thụ gọi `iterator.next()` khi sẵn sàng; producer không đẩy vô hạn. Với asynchronous push, producer có thể nhanh hơn consumer:

```text
Publisher:  100,000 events/second
       |
       v
Unbounded buffer: grow -> GC pressure -> OOM
       |
       v
Subscriber: 100 events/second
```

Reactive Streams định nghĩa một **điểm giao ước** để subscriber gửi nhu cầu `request(n)` và publisher không phát `onNext` vượt tổng demand đã nhận. Một consumer chậm có thể yêu cầu ít phần tử trước, xử lý xong mới yêu cầu tiếp.

```text
Subscriber                            Publisher
    |                                     |
    |  subscribe(...)                     |
    |------------------------------------>|
    |  onSubscribe(subscription)          |
    |<------------------------------------|
    |  subscription.request(2)            |
    |------------------------------------>|
    |  onNext(A)                          |
    |<------------------------------------|
    |  onNext(B)                          |
    |<------------------------------------|
    |  [chưa có demand cho C]             |
    |  subscription.request(1)            |
    |------------------------------------>|
    |  onNext(C)                          |
    |<------------------------------------|
    |  onComplete()                       |
    |<------------------------------------|
```

Mô hình trên là **giao thức logic**, không bảo đảm mỗi request tương ứng một packet mạng, mỗi phần tử chạy thread riêng hoặc mỗi `request(n)` phải phát đủ n phần tử. Publisher có thể phát ít hơn và kết thúc, lỗi, hoặc chờ I/O. Ngược lại, `onError`/`onComplete` có thể đến **không cần demand**.

Reactive Streams tập trung bốn nguyên tắc: xử lý dữ liệu tiềm năng bất đồng bộ, truyền nhu cầu ngược từ consumer, truyền tín hiệu theo thứ tự, và không buộc consumer giữ một hàng đợi vô hạn. Đặc tả không tự tạo cơ chế CPU scheduling, quota hoặc database backpressure thay cho bạn.

## 3. Bốn giao diện lõi trong JVM specification

Reactive Streams JVM định nghĩa `org.reactivestreams` interfaces:

```java
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

public interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T element);
    void onError(Throwable error);
    void onComplete();
}

public interface Subscription {
    void request(long n);
    void cancel();
}

public interface Processor<T, R>
        extends Subscriber<T>, Publisher<R> {
}
```

Đây là **bản chép lại chữ ký API để học**, không phải source file được thêm vào dự án: `org.reactivestreams` đã được thư viện cung cấp. Không tự định nghĩa trùng package/interface trong project.

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| `Publisher<T>` | Cung cấp các phần tử kiểu T cho subscriber đúng protocol | Reactor `Flux`/`Mono` |
| `Subscriber<T>` | Nhận signals, quyết định demand và xử lý dữ liệu/lỗi | `BaseSubscriber<T>` |
| `Subscription` | Liên kết **một quan hệ Publisher–Subscriber**, điều khiển `request`/`cancel` | Đối tượng truyền qua `onSubscribe` |
| `Processor<T,R>` | Đồng thời nhận upstream và phát downstream; có thể biến đổi T thành R | Nền tảng một số operator, không phải mọi operator là Processor object hiển lộ |

**Điểm cốt lõi:** `Publisher.subscribe(...)` trả `void` theo spec; `Subscription` đến với subscriber qua `onSubscribe(subscription)`. Trong Reactor, một số overload tiện ích của `Flux.subscribe(...)` trả `Disposable` để dễ hủy; không nhầm API tiện ích Reactor với chữ ký chuẩn Reactive Streams.

Không phải `Publisher` là nơi biết bạn muốn nhận bao nhiêu phần tử *trước khi đăng ký*. Nhu cầu được truyền qua `Subscription` tương ứng sau `onSubscribe`.

## 4. Publisher: nguồn tín hiệu theo nhu cầu

`Publisher<T>` chịu trách nhiệm chấp nhận subscriber qua `subscribe(Subscriber<? super T>)`, cung cấp `Subscription` và phát các tín hiệu theo protocol.

Các quy tắc quan trọng:

1. Số `onNext` đã phát **không bao giờ lớn hơn** tổng demand đã được chấp nhận trên subscription.
2. Publisher **có thể phát ít hơn** số đã yêu cầu và kết thúc bằng `onComplete` hoặc `onError`.
3. Các signals tới một subscriber phải **serialized**, không đồng thời gọi hai `onNext`/terminal callbacks bất chấp thứ tự.
4. `onSubscribe` luôn được gửi **trước** `onNext`, `onError` hoặc `onComplete` (đối với subscriber không null).
5. Sau terminal signal `onComplete` hoặc `onError`, không được phát tiếp `onNext` hay terminal thứ hai.
6. Sau `cancel`, Publisher phải **cuối cùng ngừng** gửi tín hiệu; dừng có thể trễ do các signals đang bay trong pipeline.
7. Publisher có thể hỗ trợ nhiều subscribers, multicast hoặc unicast; spec **không bắt buộc** mọi publisher là cold/replayable.

Ví dụ Reactor:

```java
Flux<Integer> numbers = Flux.range(1, 3);
```

`Flux.range` là nguồn hữu hạn. **Tạo biến `numbers` không có nghĩa đã chạy một pipeline tiêu thụ**; tín hiệu thường được khởi phát khi có subscriber. Tuy vậy, không được suy “mọi code trong biểu thức tạo Flux đều lazy”, vì phép tính ở arguments của `just(...)` có thể chạy ngay khi tạo object.

### Publisher và dữ liệu không giới hạn

`Flux.interval`, event bus, log tailing, WebSocket hoặc SSE có thể phát dữ liệu lâu dài. Bounded subscriber demand không tự giới hạn nguồn ngoài đời (thiết bị, message broker) nếu nguồn không hỗ trợ pause. Lúc đó adapter phải chọn chính sách buffer hữu hạn, drop/sampling, fail hoặc hạn chế upstream bằng cơ chế riêng. Không thể biến một thiết bị đẩy vô hạn thành backpressure-aware chỉ bằng chữ `Flux`.

## 5. Subscriber: bộ nhận và người quyết định demand

Một `Subscriber<T>` thực thi bốn callbacks:

| Callback | Khi nào được gọi | Nhiệm vụ |
| --- | --- | --- |
| `onSubscribe(Subscription)` | Một lần khi thiết lập subscription | Lưu subscription, quyết định `request(n)` hoặc `cancel()` |
| `onNext(T)` | Khi có phần tử được cấp theo demand | Tiêu thụ phần tử, có thể yêu cầu thêm |
| `onError(Throwable)` | Luồng kết thúc với lỗi | Cleanup, báo lỗi; **terminal** |
| `onComplete()` | Luồng hữu hạn kết thúc thành công | Cleanup/kết thúc; **terminal** |

Một subscriber **phải gửi demand** thông qua `request(n)` để nhận `onNext`. Nhưng `onError` và `onComplete` có thể xảy ra ngay cả khi chưa request. Các signals luôn phải có thứ tự hợp lệ.

**Không nên mặc định tạo nhiều subscriber cho cùng một instance tùy ý**: Reactive Streams yêu cầu Publisher có thể được subscribe nhiều lần với **các Subscriber instance khác nhau**, nhưng publisher được quyền quyết định unicast/multicast và có thể reject các subscriptions không hỗ trợ theo protocol. Không gọi lại `subscribe` cùng một Subscriber instance đang active rồi kỳ vọng framework tự an toàn.

Trong manual implementation, nhận thêm một `onSubscribe` khi đã có subscription phải hủy subscription đến sau theo quy tắc spec. Đối với phần lớn code nghiệp vụ WebFlux, nên dùng Reactor operators và `BaseSubscriber` khi cần custom demand thay vì tự viết raw Subscriber.

## 6. Subscription: cầu nối và quyền kiểm soát

`Subscription` được gắn riêng cho một quan hệ Publisher–Subscriber:

```java
subscription.request(5);
subscription.request(2);
subscription.cancel();
```

- `request(5)` cấp quyền phát **tối đa 5 phần tử**.
- `request(2)` bổ sung thêm **2 phần tử**, không reset số demand thành 2.
- Mỗi `onNext` được phát sử dụng một đơn vị demand.
- `cancel()` yêu cầu ngừng phát và giải phóng resources khi có thể.
- Sau cancel, các `request`/`cancel` tiếp theo trên subscription phải là no-op theo spec.
- `request` và `cancel` cần xử lý thread-safe/serialized đúng hợp đồng; subscriber không tùy tiện gọi hai method này đồng thời không kiểm soát.
- Request/cancel không phải lời hứa sẽ tạo dữ liệu hoặc chấm dứt I/O ngay.

Giả sử:

```text
Initial outstanding demand = 0
request(3) -> outstanding = 3
onNext(A)  -> outstanding = 2
onNext(B)  -> outstanding = 1
request(2) -> outstanding = 3
onNext(C)  -> outstanding = 2
onNext(D)  -> outstanding = 1
onNext(E)  -> outstanding = 0
```

Ở mọi thời điểm `emitted <= total requested`. Một nguồn hữu hạn có thể `onComplete` khi hết dữ liệu; completion signal không tiêu tốn một “phần tử dữ liệu” theo cách `onNext` tiêu tốn demand.

### request(0), request(-1) là sai

Theo Subscription rule 3.9: với subscription chưa bị hủy, `request(n)` có `n <= 0` là vi phạm protocol và **phải signal `onError` với `IllegalArgumentException`**, thay vì xem là “tạm dừng” bình thường. Đừng dùng `request(0)` để chờ; chỉ cần **chưa request thêm**, hoặc chủ động cancel nếu không còn cần luồng.

### Long.MAX_VALUE và cộng dồn nhu cầu

`request(Long.MAX_VALUE)` được phép coi là **nhu cầu thực tế vô hạn**. Implementations phải chịu được nhiều lần request mà không tràn bộ đếm `long` sang số âm; Reactor thường dùng cơ chế cộng demand có giới hạn ở `Long.MAX_VALUE`. Đây không phải “publisher sẽ sinh vô hạn data”: source finite vẫn có thể kết thúc, error hoặc không có data.

Reactor các overload `subscribe()` tiện ích thường request unbounded. Nếu mục tiêu là học backpressure, hãy dùng `BaseSubscriber`/`StepVerifier` với demand được điều khiển thay vì chỉ viết `flux.subscribe(System.out::println)` rồi nói đã kiểm thử request từng phần tử.

## 7. Protocol signals: thứ tự hợp lệ và bất hợp lệ

Hình thức trừu tượng:

```text
onSubscribe → onNext* → (onError | onComplete)?
```

Dấu `*` = 0 hoặc nhiều `onNext`; `?` = 0 hoặc 1 terminal signal. Không có terminal signal là khả dĩ khi stream vô hạn, nguồn chưa xong hoặc subscription bị cancel.

| Chuỗi | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `onSubscribe → onNext(A) → onComplete` | Có, nếu có demand ≥1 | Luồng hữu hạn |
| `onSubscribe → onComplete` | Có | Luồng rỗng có thể hoàn tất không cần request |
| `onSubscribe → onError(ex)` | Có | Lỗi có thể đến trước onNext, không cần request |
| `onSubscribe → onNext(A) → onNext(B)` | Có nếu đủ demand và chưa kết thúc | Stream còn hoạt động |
| `onNext(A) → onSubscribe` | Không | Thiếu onSubscribe trước data |
| `onSubscribe → onNext(A)` khi demand=0 | Không | Vượt nhu cầu |
| `onSubscribe → onComplete → onNext(A)` | Không | Signal sau terminal |
| `onSubscribe → onError(x) → onComplete` | Không | Có hai terminal signals |
| Hai `onNext` chạy đồng thời tới một Subscriber | Không | Signals phải serialized |

“Serialized” **không bắt buộc tất cả callbacks chạy cùng một Thread**. Chúng có thể đến từ các threads khác nhau nếu được đồng bộ để có quan hệ happens-before và không chồng lấn. Đừng dùng shared mutable state giữa callbacks một cách tùy tiện mà không xét thread handoff, dù protocol giữ thứ tự signals tới subscriber.

### Tại sao null không phải một phần tử hợp lệ?

Reactive Streams không cho phép `onNext(null)`; null làm hỏng contract và có thể biểu thị nhầm “không có dữ liệu”. Dùng `Mono.empty()` để biểu diễn hoàn tất không có value, `Optional<T>` được phát như một đối tượng non-null nếu hợp đồng API phù hợp, hoặc xây domain type rõ ràng.

Trong Reactor, `Mono.just(null)` không hợp lệ, `Mono.justOrEmpty(nullable)` có thể tạo Mono rỗng khi giá trị null. Một nguồn không có phần tử vẫn có thể hoàn tất bằng `onComplete`.

## 8. Backpressure là pull-controlled delivery, không phải backpressure ở mọi nơi

Subscriber là phía điều khiển demand, nhưng cần phân biệt ba mức:

1. **Reactive Streams demand:** số `onNext` Publisher được phép gửi cho Subscriber.
2. **Operator demand:** các toán tử có thể request **nhiều hơn** upstream để thực thi `buffer`, `flatMap` hoặc prefetch.
3. **Transport/storage backpressure:** TCP flow control, file/network buffering, database driver, message broker có cơ chế riêng.

Một final subscriber gọi `request(1)` không bảo đảm **chỉ có đúng một database row được đọc**, hoặc chỉ một network packet được nhận. `flatMap` có thể subscribe nhiều inner publishers và prefetch; `buffer(10)` có thể request 10 nguồn để tạo một `List<T>` downstream. Đó không trái spec nếu mỗi boundary gửi không vượt nhu cầu trên boundary của nó.

Ví dụ:

```text
Final Subscriber: request(1) List
          |
          v
Flux.buffer(10): request(10) items upstream
          |
          v
Source: emits 10 items -> buffer returns one List
```

Giải pháp kiểm soát memory không chỉ là “dùng Flux”. Hãy chọn `prefetch`, concurrency, bounded buffer, rate/size limits, timeout và resource ownership đúng.

### Khi nguồn không thể chậm lại

Với event bus nóng không hỗ trợ pause, adapter phải xác định:

- Buffer có giới hạn và xử lý khi đầy.
- Drop/sampling với observability rõ.
- Fail/close connection khi consumer quá chậm.
- Dùng broker có ack/credits/pause-consumer nếu hỗ trợ.

Các lựa chọn Reactor như `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest` cần dùng có chủ đích, hiểu mất dữ liệu và memory footprint. **Unbounded buffer không phải backpressure giải pháp an toàn.**

## 9. Cold Publisher và Hot Publisher

Reactive Streams specification **không áp đặt** một Publisher phải cold hay hot. Đây là tính chất cách nguồn được thiết kế:

**Cold:** mỗi lần subscribe có thể bắt đầu một chuỗi riêng; `Flux.range(1,3)` là ví dụ. Nếu nguồn cold gọi HTTP/DB khi subscribe, hai subscriptions có thể kích hoạt công việc hai lần.

**Hot:** dữ liệu được phát theo thời gian và có thể chia sẻ qua subscribers. Subscriber đăng ký muộn có thể bỏ lỡ sự kiện trước đó; backpressure policy tùy source. Reactor `Sinks.Many` là công cụ tạo hot signal source (với các biến thể và overflow policy).

```text
Cold source A:  subscribe1 -> 1 2 3 (riêng)
                subscribe2 -> 1 2 3 (riêng)

Hot broadcast:  time ------  A B C D E F --->
                sub1          ^ B C D E F
                sub2              ^ D E F
```

Sơ đồ mang tính minh họa: replay hot source có thể phát lại lịch sử theo cấu hình; không phải mọi hot publisher đều mất dữ liệu cũ. WebFlux không tự đảm bảo một browser reconnect SSE sẽ nhận lại tất cả events; phải có replay ID, broker retention và chính sách reconnect riêng.

### Tạo Flux chưa chắc đã lazy hết mọi thứ

```java
String value = compute();       // Chạy NGAY.
Mono<String> eager = Mono.just(value);

Mono<String> lazy = Mono.defer(
        () -> Mono.just(compute())); // Chạy khi subscribe.
```

Đây là snippet trong class có method `compute()`. Nếu gọi `Mono.just(expensiveServiceCall())`, phép gọi trong argument chạy ngay lúc dựng pipeline. Dùng `Mono.defer(...)` hoặc `Mono.fromCallable(...)` khi cần hoãn tạo dữ liệu, và phải xét blocking vs non-blocking của công việc.

## 10. Reactor: Flux, Mono và Subscriber tiện ích

Project Reactor là thư viện reactive được Spring WebFlux sử dụng:

| Loại | Số phần tử hợp lệ | Một số factory |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 rồi terminal | `just`, `empty`, `error`, `fromCallable`, `defer` |
| `Flux<T>` | 0..N rồi terminal hoặc luồng chưa kết thúc | `just`, `range`, `fromIterable`, `interval`, `defer` |
| `BaseSubscriber<T>` | Helper để viết Subscriber có kiểm soát `request/cancel` | Hook `hookOnSubscribe`, `hookOnNext` |
| `StepVerifier` | Test signals và demand theo scenario | `expectNext`, `thenRequest`, `verifyComplete` |

`Flux<T>` và `Mono<T>` thực thi các contract reactive cần thiết; khi truyền vào WebFlux handler, framework subscribe và quản lý response lifecycle cho bạn.

Một số `Flux.subscribe(...)` overload là terminal operation tiện ích: **mặc định thường request unbounded**, đặc biệt `subscribe()` và các overload lambda tiêu chuẩn. Đừng nhầm chúng với tự triển khai `Subscriber` nhận `Subscription`.

**Điểm quan trọng:** `Mono` có tối đa một `onNext`, nhưng không có nghĩa Mono không có demand hoặc luôn synchronous. `Mono.error(...)`/`Mono.empty()` có thể gửi terminal mà không phát giá trị. Một Mono cũng có thể chạy network I/O bất đồng bộ.

## 11. Java 17 độc lập: Flow API gần tương ứng Reactive Streams

Java 9+ có `java.util.concurrent.Flow` với `Publisher`, `Subscriber`, `Subscription` và `Processor` **tương đồng về thiết kế** với `org.reactivestreams`. Đây là **hai tập Java interfaces khác package**, không phải cùng object cast trực tiếp. Khi tích hợp, cần adapter phù hợp, ví dụ `reactor.adapter.JdkFlowAdapter` (dependency `reactor-adapter` tùy dự án).

Để quan sát callbacks bằng **Java 17 chuẩn không cần Maven**, dùng `SubmissionPublisher`:

Tệp `FlowDemandDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowDemandDemo {

    public static void main(String[] args) throws Exception {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>()) {

            publisher.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    this.subscription = s;
                    System.out.println("onSubscribe");
                    s.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("onNext=" + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable throwable) {
                    System.out.println("onError=" +
                            throwable.getClass().getSimpleName());
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No terminal signal before timeout");
            }
        }
    }
}
```

Lệnh:

```bash
javac FlowDemandDemo.java
java FlowDemandDemo
```

Stdout khi chương trình hoàn tất bình thường:

```text
onSubscribe
onNext=A
onNext=B
onComplete
```

`CountDownLatch` đợi terminal signal, nên main thread không kết thúc trước callback. `SubmissionPublisher` có thể **buffer** dữ liệu và chạy callbacks bất đồng bộ qua executor; hai lệnh `submit` không cần đợi từng `request(1)`. Chính `Subscription` mới giới hạn việc **giao onNext cho subscriber**, không nhất thiết chặn producer tạo/buffer dữ liệu ngay lập tức. Dự án thực cần chọn bounded buffer và chính sách khi quá tải.

Lưu ý kỹ: Ví dụ dùng `Flow` để minh họa protocol trên JDK thuần. Với WebFlux, tiếp tục dùng Reactor `Flux`/`Mono`; không được cast `Flow.Publisher` thành `org.reactivestreams.Publisher` mà không adapter.

## 12. Reactor demo: điều khiển từng phần tử bằng BaseSubscriber

Trong Maven project có Reactor Core (Spring Boot WebFlux starter cung cấp), tạo:

Tệp `src/main/java/com/example/demo/DemandDemo.java`:

```java
package com.example.demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {

    public static void main(String[] args) {
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                private int received;

                @Override
                protected void hookOnSubscribe(
                        Subscription subscription) {
                    System.out.println("subscribed");
                    request(1);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("next=" + value);
                    received++;

                    if (received == 3) {
                        System.out.println("cancel");
                        cancel();
                    } else {
                        request(1);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("complete");
                }
            });
    }
}
```

Để chạy class này trên classpath Maven dependencies, dùng IDE “Run main” hoặc thiết lập Maven exec plugin thích hợp. Nếu chỉ dùng `javac` trực tiếp không có Reactor jars, code **không biên dịch**. Mã này là complete Java class, chạy trong Spring WebFlux Maven project có Reactor dependency.

Stdout cho `Flux.range` synchronous ở ví dụ:

```text
subscribed
next=1
next=2
next=3
cancel
```

Không có `complete` vì subscriber chủ động cancel sau phần tử thứ ba. `BaseSubscriber` quản lý reentrant request một cách phù hợp Reactor contract. Nếu đổi thành subscriber request đủ cả năm phần tử và không cancel, `Flux.range` có thể phát `onComplete` sau phần tử cuối.

**Quan sát:** `request(1)` được gọi ngay trong hook, dữ liệu có thể đến đồng bộ trên thread hiện tại. Reactive Streams không buộc asynchronous execution; “reactive” mô tả giao thức tín hiệu và demand, không tự phát sinh thread.

## 13. StepVerifier: kiểm soát demand trong test

Reactor cung cấp `reactor-test` và `StepVerifier`. Thêm dependency test scope `io.projectreactor:reactor-test` nếu project chưa kéo theo. Ví dụ kiểm thử source hữu hạn:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveDemandTest {

    @Test
    void doesNotEmitMoreThanInitialDemand() {
        StepVerifier.create(Flux.range(1, 3), 0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .verifyComplete();
    }

    @Test
    void aFluxCanBeCancelledBeforeCompletion() {
        StepVerifier.create(Flux.range(1, 10), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenCancel()
            .verify();
    }

    @Test
    void emptyMonoCompletesWithoutOnNext() {
        StepVerifier.create(
                reactor.core.publisher.Mono.empty(), 0)
            .expectSubscription()
            .verifyComplete();
    }

    @Test
    void errorIsTerminal() {
        StepVerifier.create(
                Flux.error(new IllegalStateException("boom")))
            .expectErrorMessage("boom")
            .verify();
    }
}
```

Đây là một class JUnit 5 có thể chạy trong Spring Boot project khi `spring-boot-starter-test`/`reactor-test` có trên test classpath. Các test trên không giả định lập lịch scheduler hay thời gian thực; `Flux.range` phát phần tử đồng bộ đúng demand, còn `Mono.empty` có thể hoàn tất dù request=0.

**Không viết** `StepVerifier.create(Flux.range(1,3), 0).expectNext(1)` ngay sau subscription mà chưa `thenRequest(...)`: source đúng contract sẽ không phát value, test có thể timeout/chờ. Đừng lầm kiểm tra “không có value” với `expectNoEvent(...)` khi đang chờ đến thời điểm không có scheduling phù hợp.

Đối với nguồn dùng timer, có thể dùng `StepVerifier.withVirtualTime` khi thích hợp để tránh test chậm/timing flaky. Nhưng khi test chính là protocol request/cancel, nguồn `range` và demand tường minh thường rõ hơn.

## 14. Tự viết Publisher chuẩn có khó không?

Có. Một `Publisher` tuân chuẩn phải xử lý:

- `subscribe(null)` và đường đi báo lỗi đúng.
- `onSubscribe` đúng một lần, trước mọi tín hiệu khác.
- `request(n)` hợp lệ, cộng dồn an toàn, saturation `Long.MAX_VALUE`.
- `request(n<=0)` signal `onError(IllegalArgumentException)` theo spec; không chỉ ném ra từ `request`.
- Serialize signals và tránh reentrant `onNext → request → onNext` đệ quy vô hạn/stack overflow.
- Tôn trọng cancellation eventually và cleanup references.
- Không phát null, không phát sau terminal, không gửi hai terminal signals.
- Race giữa `request`, `cancel`, phát giá trị, error và completion trên nhiều threads.
- Nếu không có dữ liệu, có thể hoàn tất/lỗi ngay; nếu có nguồn chậm, không spin-wait trên event loop.

Đừng tự viết Publisher chỉ bằng:

```java
subscriber.onSubscribe(subscription);
for (T item : items) {
    subscriber.onNext(item); // SAI: không kiểm tra request(n).
}
subscriber.onComplete();
```

Đây là **phản ví dụ**, không phải tệp compile; biến `subscriber`/`subscription`/`items` chỉ mang ý nghĩa minh họa. Nó vi phạm quy tắc demand khi subscriber chưa request.

Thay vì tự xây giao thức, dùng `Flux.fromIterable`, `Flux.generate` (khi phù hợp synchronous stateful generation), `Flux.create`/`Sinks.Many` theo hướng dẫn Reactor, và đọc rõ overflow/backpressure semantics. Khi tự xây integration Publisher mới, dùng **Reactive Streams Technology Compatibility Kit (TCK)** để kiểm tuân thủ protocol.

## 15. Operator có thể thay đổi demand

Ví dụ:

```java
Flux.range(1, 100)
    .filter(n -> n % 2 == 0)
    .buffer(5)
    .take(2);
```

Các toán tử không chỉ chuyển giá trị, mà còn tạo quan hệ Publisher–Subscriber bên trong pipeline.

- `map` thường giữ tỷ lệ một vào/một ra cho mỗi item được phát thành công.
- `filter` có thể cần nhiều upstream items hơn downstream demand vì một số item bị loại.
- `buffer(5)` cần tới 5 phần tử đầu vào để tạo một list đầu ra.
- `flatMap` có thể subscribe nhiều publishers song song, prefetch và interleave kết quả; cần giới hạn `concurrency`/`prefetch`.
- `concatMap` giữ trật tự nhiều inner streams theo cách khác, có chi phí throughput/queue riêng.
- `publishOn` chuyển xử lý sang scheduler khác và có queue/prefetch boundary.
- `limitRate` hỗ trợ điều chỉnh cách request upstream theo đợt, **không** tự giới hạn CPU/memory của mọi downstream.
- `take(n)` thường hủy upstream khi đã lấy đủ n phần tử, nhưng cancellation có thể đến với độ trễ.

**Không kỳ vọng mỗi phép `request(1)` của terminal subscriber sẽ trùng chính xác một `doOnRequest(1)` ở source** khi có các operator trung gian reshape requests. Dùng `doOnRequest` ở các vị trí hợp lý để quan sát demand thực tế từng boundary.

```java
Flux.range(1, 20)
    .doOnRequest(n -> System.out.println("source demand=" + n))
    .buffer(5)
    .doOnRequest(n -> System.out.println("list demand=" + n))
    .take(2);
```

Đây là pipeline minh họa; chưa subscribe nên không có stdout. Nếu subscribe, thứ tự/số lượng request phụ thuộc từng operator và Reactor version. Đừng hardcode log sequence trong tài liệu mà không có test phù hợp.

## 16. Scheduler và threads: subscribeOn, publishOn

Reactive Streams **không chỉ định một thread model cụ thể**. Nguồn như `Flux.range` thường đồng bộ, còn `WebClient`/Reactor Netty tạo tín hiệu từ event loop I/O bất đồng bộ. Reactor cung cấp `Scheduler` để chuyển execution context khi cần.

| Toán tử | Ý nghĩa khái quát |
| --- | --- |
| `subscribeOn(scheduler)` | Ảnh hưởng nơi subscription/request/upstream work bắt đầu; vị trí tương đối có quy tắc riêng |
| `publishOn(scheduler)` | Chuyển phần downstream sau nó sang worker của scheduler, tới khi có boundary khác |
| `Schedulers.parallel()` | Pool tối ưu cho CPU-bound ngắn, không dành cho blocking lâu |
| `Schedulers.boundedElastic()` | Pool bounded dành cho blocking legacy tasks khi buộc phải tích hợp |
| `delayElements(...)` | Đưa asynchronous time boundary và scheduling cho từng phát item |

Ví dụ legacy blocking call:

```java
Mono<String> value = Mono.fromCallable(
        () -> legacyJdbcService.fetchText())
    .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet trong class có `legacyJdbcService` và imports `reactor.core.publisher.Mono`, `reactor.core.scheduler.Schedulers`. Nó giúp **đẩy blocking call ra khỏi event loop**, nhưng JDBC vẫn blocking, vẫn dùng connection và boundedElastic workers. Không được diễn giải “bọc JDBC vào Mono” thành database reactive driver.

**Không gọi `block()` trong WebFlux handler/event-loop thread**; nó có thể chặn pipeline, và Reactor có thể báo lỗi khi block trong thread non-blocking. Ở boundary ứng dụng đồng bộ (CLI, tests) `block()` có thể hợp lý có kiểm soát, nhưng không dùng để phá vỡ end-to-end reactive chain trong handler.

## 17. WebFlux HTTP boundary liên quan Publisher thế nào?

Trong WebFlux annotated controller:

```java
@GetMapping("/api/numbers")
public Flux<NumberDto> numbers() {
    return Flux.range(1, 3).map(NumberDto::new);
}
```

**Controller trả Publisher**, không tự gọi `subscribe()`. WebFlux HTTP infrastructure trở thành bên tiêu thụ downstream, đăng ký subscription, áp dụng codecs và ghi response khi network I/O cho phép.

```text
Reactive DB / Flux.range / WebClient       HTTP response writer
                Publisher                      Subscriber
                  |                               |
                  | <------ subscribe ------------|
                  | ------ onSubscribe ---------->|
                  | <------ request(n) ------------|
                  | ------ onNext(record) -------->|
                  |                         JSON encoding/network
                  | ------ onComplete ------------>|
```

Sơ đồ rút gọn: WebFlux có nhiều operator, codecs và internal subscribers trung gian; không nhất thiết một `request(n)` bằng một JSON document hoặc một network packet. Reactor Netty/WebFlux xây trên non-blocking I/O và backpressure. Một HTTP client tải chậm có thể tạo áp lực ngược qua response writing, nhưng memory cũng phụ thuộc codecs, buffering, data source và giới hạn ứng dụng.

### Mono/Flux và cách HTTP phản hồi

- `Mono<Dto>`: 0 hoặc 1 object; thường phù hợp GET resource đơn.
- `Flux<Dto>`: stream nhiều giá trị; HTTP JSON array được serialize theo cách có thể cần buffering/format phù hợp; với `text/event-stream` thì mỗi event có thể được gửi theo thời gian.
- `Mono<Void>`: biểu thị xử lý completion không có value, thường kết hợp status thích hợp.
- `Flux<DataBuffer>`: raw bytes, phải quản lý memory/ref-counting và cleanup theo `DataBuffer` API.
- Lỗi trước khi response commit có thể ánh xạ thành HTTP status/body; lỗi sau khi stream commit **không thể luôn đổi** thành JSON error hoặc HTTP 500 mới.

Đừng tự tạo `flux.subscribe(value -> response.getWriter().write(...))` trong handler rồi trả `Mono.empty()`, vì framework không còn quản lý completion/cancellation/backpressure của response đúng cách.

## 18. Ứng dụng Spring Boot WebFlux chạy được

Tạo Maven project bằng Spring Initializr với **Java 17+, Spring Boot 3.x**, dependencies:

- `spring-boot-starter-webflux` (không thêm `spring-boot-starter-web` nếu muốn Boot chọn reactive WebFlux app type một cách rõ ràng).
- `spring-boot-starter-test` (test scope).
- `reactor-test` (test scope, nếu starter-test chưa có).

Ví dụ không cần database. Các file:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  NumbersController.java
src/test/java/com/example/demo/
  NumbersControllerTest.java
  ReactiveDemandTest.java
```

### 18.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. NumbersController.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class NumbersController {

    @GetMapping(path = "/numbers",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<NumberDto> numbers(
            @RequestParam(defaultValue = "3") int count) {

        if (count < 1 || count > 20) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "count must be between 1 and 20");
        }

        return Flux.range(1, count)
                .map(NumberDto::new)
                .delayElements(Duration.ofMillis(80));
    }

    @GetMapping(path = "/numbers/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<NumberDto> one(@PathVariable int id) {
        if (id < 1 || id > 20) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "number not found"));
        }
        return Mono.just(new NumberDto(id));
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<EchoResponse> echo(@RequestBody Mono<EchoInput> input) {
        // Không tự subscribe: WebFlux quản lý subscription.
        return input.map(v -> new EchoResponse(v.message()));
    }

    public record NumberDto(int value) {}
    public record EchoInput(String message) {}
    public record EchoResponse(String message) {}
}
```

**Giải thích:**

- `numbers` trả một `Flux` hữu hạn, được render thành Server-Sent Events nhờ `produces=text/event-stream`. `delayElements` tạo độ trễ minh họa; không bảo đảm chính xác 80ms trên mọi hệ thống.
- `one` trả `Mono<NumberDto>` hoặc `Mono.error(...)`; lỗi trước response commit có thể thành 404.
- `echo` nhận request body dưới dạng `Mono<EchoInput>` để minh họa WebFlux reactive request-body argument; response hoàn tất khi input được decode và map xong.
- Controller **không gọi `subscribe()` hoặc `block()`**. HTTP infrastructure sở hữu demand/cancel/completion.
- Endpoint count được giới hạn từ 1..20 để demo không xuất luồng vô hạn và không tiêu thụ tài nguyên không kiểm soát.
- Nếu muốn dùng R2DBC/repository reactive thật, chọn driver cung cấp reactive contract, không tự wrap JDBC rồi tuyên bố non-blocking.

### 18.3. Khởi động

Tại project Maven có Wrapper:

```bash
./mvnw spring-boot:run
```

Trên PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Mặc định app nghe cổng `8080` nếu chưa đổi `server.port`. Đây là Spring Boot source cần classpath Spring WebFlux/Reactor/Jackson; `javac NumbersController.java` đơn độc không đủ dependency.

## 19. curl: quan sát HTTP response của WebFlux

### Server-Sent Events

```bash
curl -N -i 'http://localhost:8080/api/numbers?count=3'
```

Với `Accept` mặc định phù hợp, response thường có `Content-Type: text/event-stream` và ba events được gửi theo thứ tự; phần dữ liệu có dạng:

```text
data:{"value":1}

data:{"value":2}

data:{"value":3}

```

Các header, khoảng thời gian và chi tiết format có thể phụ thuộc codec/server, nhưng số `value` và thứ tự 1–3 là contract của `Flux.range`. `curl -N` tắt output buffering ở curl để quan sát từng event.

Không suy “request count=3 → client gọi Subscription.request(3) đúng một lần”. WebFlux writer và codecs có buffering/prefetch nội bộ; chỉ nên assert response là ba events đúng thứ tự.

### Lấy một phần tử

```bash
curl -i 'http://localhost:8080/api/numbers/2'
```

Kỳ vọng HTTP 200:

```json
{"value":2}
```

`GET /api/numbers/99` trả 404 nếu lỗi được xử lý trước khi response commit. App không có database; rule 1..20 chỉ để minh họa `Mono.error`.

### Đọc JSON body như Mono

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Xin chào WebFlux"}'
```

Kỳ vọng HTTP 200 và JSON:

```json
{"message":"Xin chào WebFlux"}
```

Không có code nào tự subscribe một lần để “kích hoạt echo”, rồi lại trả một Mono khác; nếu làm vậy sẽ tạo side effects/hai subscriptions ngoài lifecycle HTTP.

### Thử input không hợp lệ

```bash
curl -i 'http://localhost:8080/api/numbers?count=1000'
```

Kỳ vọng HTTP 400 trước khi gửi streaming body vì controller validate ngay. Trong ứng dụng thực, body lỗi tùy Spring Boot error handling và cấu hình Problem Details, không nên hardcode một response JSON chi tiết nếu không cấu hình.

## 20. WebTestClient: kiểm thử HTTP reactive

Tệp `src/test/java/com/example/demo/NumbersControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NumbersControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void oneNumberReturnsMonoValueAsJson() {
        client.get()
            .uri("/api/numbers/2")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.value").isEqualTo(2);
    }

    @Test
    void rejectsInvalidCount() {
        client.get()
            .uri("/api/numbers?count=1000")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void echoJsonBody() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"message\":\"hello\"}")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void receivesThreeSseItemsThenCompletes() {
        Flux<String> body = client.get()
            .uri("/api/numbers?count=3")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .returnResult(String.class)
            .getResponseBody();

        StepVerifier.create(body)
            .expectNextMatches(s -> s.contains("\"value\":1"))
            .expectNextMatches(s -> s.contains("\"value\":2"))
            .expectNextMatches(s -> s.contains("\"value\":3"))
            .verifyComplete();
    }
}
```

**Lưu ý test SSE:** việc decode `String.class` dưới `text/event-stream` có thể phụ thuộc codec và cách tách events trong Spring version/client. Nếu codec của project map body thành đối tượng khác hoặc cần kiểm event metadata, thay `String.class` bằng `ServerSentEvent<NumberDto>`/DTO với `ParameterizedTypeReference` tương ứng và assert giá trị. Đừng mặc định mỗi TCP chunk là một event độc lập.

Chạy:

```bash
./mvnw test
```

Hoặc PowerShell:

```powershell
.\mvnw.cmd test
```

Đây là **mẫu test có thể chạy trong project Boot 3 với dependencies phù hợp**, không phải kết quả đã thực thi trong repository người dùng. Với endpoints có Spring Security, phải cấp identity/CSRF đúng policy hoặc request có thể nhận 401/403 trước controller.

## 21. Lỗi, cancel, resource cleanup và HTTP disconnect

Khi Publisher phát `onError(error)`, đây là tín hiệu **terminal**: không được sau đó phát `onComplete` hoặc `onNext`. Reactor operators như `onErrorResume` có thể chuyển luồng lỗi thành một Publisher fallback mới, nhưng phải hiểu đây là **chuyển hướng pipeline**, không phải tiếp tục phát tín hiệu sau terminal của cùng subscription gốc.

Ví dụ:

```java
Mono<String> result = remoteCall()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(java.util.concurrent.TimeoutException.class,
                   e -> Mono.just("fallback"));
```

Đoạn trên là snippet cần method `remoteCall()` và imports; chưa là file chạy độc lập. `timeout` kết thúc/cancel một phần upstream nhưng **không chắc** network/database operation vật lý đã dừng tức thì hoặc side effect đã rollback. Fallback có thể che lỗi quan trọng nếu dùng bừa bãi.

Với HTTP streaming, khi client disconnect, downstream WebFlux có thể cancel subscription. Hãy đảm bảo source giải phóng database cursor, file handle, broker consumer và reference trong `doFinally`/resource-managed operators theo đúng signal type.

```java
Flux<Integer> source = Flux.range(1, 100)
    .doFinally(signal ->
        System.out.println("terminated=" + signal));
```

Snippet trên chỉ quan sát khi source có subscription thực, terminal/cancel phụ thuộc cách subscribe/consume. `doFinally` có thể nhận `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`; không coi cancel là thành công trong domain logic.

`Subscription.cancel()` phải thread-safe/idempotent và eventually ngừng phát; subscriber vẫn phải sẵn sàng cho một số `onNext` đang in flight ngay sau khi yêu cầu cancel. Không phụ thuộc cancel như một phép kill thread hoặc rollback transaction.

## 22. Reactive Streams khác Java Stream, Future và Iterator

| Khái niệm | Mô hình tiêu thụ | Điểm khác Reactive Streams |
| --- | --- | --- |
| `java.util.Iterator` | Consumer đồng bộ gọi `next()` | Pull trực tiếp, thường blocking nếu lấy data chậm |
| `java.util.stream.Stream` | Pipeline thường đồng bộ trên collection/spliterator | Không phải Reactive Streams Publisher, không có `Subscription.request(n)` |
| `CompletableFuture<T>` | Một kết quả/lỗi eventual | Không biểu diễn tự nhiên 0..N signals/backpressure |
| `Flow.Publisher<T>` | JDK reactive protocol tương tự | Khác package interface với `org.reactivestreams.Publisher` |
| `Mono<T>` | 0..1 asynchronous/synchronous publisher | Reactor type giàu operators |
| `Flux<T>` | 0..N signals, supports demand | Reactor type giàu operators, không luôn có data vô hạn |

`parallelStream()` không phải đường tắt thành WebFlux non-blocking. `CompletableFuture.supplyAsync` có executor semantics riêng và không mặc nhiên có backpressure từ HTTP subscriber. Reactor không thay thế Java Stream trong mọi tác vụ collection CPU nhỏ.

**Reactor không bảo đảm tối ưu mọi throughput**: nguồn event-driven non-blocking giúp sử dụng ít threads hơn khi có nhiều I/O chờ, nhưng code reactive khó debug hơn, có chi phí scheduler/operators và vẫn có bottleneck dữ liệu.

## 23. Những sai lầm phổ biến

1. **Nghĩ `subscribe()` trả Subscription trong spec:** nó trả `void`; Subscription được truyền qua `onSubscribe`.
2. **Không gọi `request(n)`:** source đúng giao thức không gửi `onNext` khi chưa có demand.
3. **Dùng `request(0)` để pause:** sai theo rule 3.9, phải error khi active.
4. **Nghĩ request(2) phải phát đúng hai giá trị:** source có thể phát ít hơn hoặc complete/error.
5. **Phát `onNext` trước `onSubscribe`:** vi phạm protocol.
6. **Phát tiếp sau `onError`/`onComplete`:** vi phạm terminal contract.
7. **Phát `onNext(null)` để biểu thị không có dữ liệu:** không hợp lệ, dùng empty/completion.
8. **Hai luồng đồng thời gọi onNext trên cùng subscriber:** vi phạm serialized signals.
9. **Không hủy subscription không còn dùng:** tốn resources, có thể leak.
10. **Nghĩ cancel dừng tức thì mọi network I/O:** semantics eventually, không bảo đảm rollback.
11. **Nghĩ Flux đồng nghĩa non-blocking:** nguồn bên trong vẫn có thể gọi JDBC/Thread.sleep.
12. **Gọi `block()` ngay trong WebFlux event-loop handler:** chặn event loop hoặc ném lỗi.
13. **Tự `subscribe()` trong controller và trả `Mono.empty()`:** tách producer khỏi HTTP lifecycle.
14. **Nghĩ lambda `subscribe(...)` demo kiểm được backpressure từng phần tử:** thường request unbounded.
15. **Nghĩ Mono chỉ có một giá trị nên không cần terminal/error handling:** Mono có thể empty/error.
16. **Cho rằng mọi Flux là cold và mỗi subscriber nhận đầy đủ dữ liệu:** hot/unicast/replay khác nhau.
17. **Nghĩ operator map/filter/flatMap giữ request(1) upstream:** có thể reshape/pre-fetch.
18. **Tạo buffer không giới hạn cho nguồn nóng:** có thể OOM khi consumer chậm.
19. **Nghĩ client HTTP đọc chậm chỉ làm Publisher chậm, không có buffer:** network/codecs có giới hạn riêng.
20. **Dùng onErrorResume để nuốt mọi lỗi:** có thể che outage và trả business data sai.
21. **Dùng `Mono.just(blockingCall())` và tưởng call lazy:** argument đã được đánh giá khi tạo Mono.
22. **Bọc JDBC vào Mono mà không chọn scheduler phù hợp:** blocking work có thể lên event loop.
23. **Tự viết Publisher không kiểm TCK:** dễ sai demand, cancellation và concurrency.
24. **Dùng StepVerifier initialRequest=0 rồi expectNext ngay:** source không có quyền phát, test có thể chờ.
25. **Nghĩ WebFlux và Servlet MVC luôn chung request context/thread-local:** stack và context khác.
26. **Không kiểm soát resource cleanup trên cancel/disconnect:** giữ cursors, subscriptions, handles.
27. **Đánh đồng backpressure với rate limit/quota:** demand là per-subscription data flow, khác hạn mức API.
28. **Không phân biệt Flow API với org.reactivestreams package:** cần adapter nếu kết hợp trực tiếp.
29. **Bỏ qua operator prefetch/concurrency:** downstream request nhỏ vẫn có thể khiến upstream work lớn.
30. **Nghĩ streaming HTTP event = một TCP packet:** transport framing và codec khác object signals.

## 24. Checklist thực hành và production

### Protocol

- [ ] Publisher phát `onSubscribe` trước signals khác và tối đa một lần?
- [ ] `onNext` luôn non-null và không vượt total requested?
- [ ] Signals serialized, không có terminal thứ hai hoặc signal sau terminal?
- [ ] `request(n)` dương, demand additive, xử lý `Long.MAX_VALUE`/overflow?
- [ ] `request(0)`/âm phát IllegalArgumentException terminal theo spec?
- [ ] `cancel` an toàn, idempotent và eventual cleanup?
- [ ] Đã dùng Reactor built-ins/TCK thay vì tự triển khai Publisher thủ công khi không cần?

### WebFlux/Reactor

- [ ] Controller trả Flux/Mono cho framework subscribe, không tự subscribe?
- [ ] Không dùng blocking I/O trên Netty event-loop; có boundedElastic hoặc reactive driver phù hợp?
- [ ] Không tự giả định cold/hot khi có nhiều subscribers hoặc reconnect?
- [ ] Operator prefetch/concurrency/buffers có giới hạn?
- [ ] Các nguồn nóng có policy khi downstream chậm?
- [ ] Resource cleanup được kiểm trên complete/error/cancel?
- [ ] Timeout không được coi là tự rollback side effect?
- [ ] Security/authentication/authorization và per-user quotas độc lập backpressure?

### Kiểm thử và vận hành

- [ ] Test `request(1)`, request theo đợt, cancellation, empty, error và completion?
- [ ] Dùng `StepVerifier` với initial request rõ khi học demand?
- [ ] Test HTTP SSE/JSON qua `WebTestClient` và `curl -N`?
- [ ] Quan sát buffer/queue, memory, event-loop blocking, dropped events, timeouts?
- [ ] Không lấy thứ tự TCP chunks làm thứ tự business messages?
- [ ] Có tài liệu giới hạn số events/request, idle timeout và reconnect/replay policy cho streaming?
- [ ] Không lộ dữ liệu nhạy cảm qua event stream, logs, trace hoặc error message?

## 25. Câu hỏi tự kiểm tra

**1.** Ai quyết định số phần tử Publisher được phép giao cho Subscriber?

**Đáp án:** Subscriber gọi `Subscription.request(n)`; Publisher không phát `onNext` vượt demand đã được chấp nhận.

**2.** `Publisher.subscribe(s)` trả về kiểu gì theo đặc tả Reactive Streams JVM?

**Đáp án:** `void`. Subscription được truyền qua `Subscriber.onSubscribe(subscription)`.

**3.** Tại sao cần `onSubscribe` trước `onNext`?

**Đáp án:** Subscriber cần nhận Subscription để chủ động request/cancel, tạo một điểm khởi tạo nhất quán.

**4.** `request(2)` rồi `request(3)` có nghĩa gì?

**Đáp án:** Nhu cầu cộng dồn, tối đa thêm năm phần tử được phép phát trừ số đã dùng; không reset thành ba.

**5.** Có thể gọi `onComplete` khi chưa có `request` không?

**Đáp án:** Có. Terminal signals không đòi hỏi demand như onNext.

**6.** `request(0)` có phải pause không?

**Đáp án:** Không; khi Subscription còn active, đó là request không hợp lệ và phải onError(IllegalArgumentException).

**7.** Có thể có `onError` rồi `onComplete` trên cùng một subscription không?

**Đáp án:** Không. Cả hai là terminal signals và loại trừ nhau.

**8.** Reactive Streams có luôn chạy async trên thread khác không?

**Đáp án:** Không. `Flux.range` có thể phát đồng bộ ngay trong lời gọi request; Scheduler là lựa chọn riêng.

**9.** Vì sao `subscribe(System.out::println)` không chứng minh custom backpressure?

**Đáp án:** Những overload đơn giản trong Reactor thường request unbounded; cần `BaseSubscriber` hoặc StepVerifier điều khiển demand.

**10.** `cancel()` có luôn ngắt network call hoặc rollback transaction ngay không?

**Đáp án:** Không. Nó yêu cầu ngừng và cleanup eventual; downstream I/O/transaction có semantics riêng.

**11.** Một final subscriber chỉ request(1) có bảo đảm nguồn upstream chỉ tính đúng một item không?

**Đáp án:** Không. `buffer`, `flatMap`, prefetch có thể reshape demand, mỗi boundary có quy tắc riêng.

**12.** WebFlux controller nên return Flux hay tự gọi subscribe?

**Đáp án:** Trả Flux/Mono. WebFlux infrastructure sẽ subscribe, demand, xử lý response và cancellation.

**13.** Có phải `Mono.just(service.get())` luôn lazy?

**Đáp án:** Không. `service.get()` được đánh giá trước khi truyền vào `just`; dùng defer/fromCallable và scheduler phù hợp nếu cần.

**14.** Java `Flow.Publisher` có thể cast thẳng thành `org.reactivestreams.Publisher` không?

**Đáp án:** Không. Hai interface khác package, cần adapter có chủ đích.

## 26. Nguồn tham khảo

- Reactive Streams JVM specification, API và các quy tắc Publisher/Subscriber/Subscription: https://github.com/reactive-streams/reactive-streams-jvm
- Reactive Streams official website: https://www.reactive-streams.org/
- Spring Framework — Spring WebFlux overview: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — Reactive Core và HTTP backpressure: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Project Reactor Core reference, `subscribe`, `BaseSubscriber` và demand: https://projectreactor.io/docs/core/release/reference/
- Project Reactor Core reference — backpressure and request reshaping: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor — testing `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
- Project Reactor — schedulers and threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Java 17 `java.util.concurrent.Flow`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html
- Java 17 `SubmissionPublisher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
