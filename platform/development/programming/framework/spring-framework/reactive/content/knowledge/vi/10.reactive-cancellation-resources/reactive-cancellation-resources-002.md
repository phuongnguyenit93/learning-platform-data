# Hủy không đồng nghĩa với dừng công việc bên ngoài ngay lập tức

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Hủy và tài nguyên. Bài học trình bày tín hiệu `cancel()` trong Reactive Streams, giới hạn của việc hủy một Publisher và lý do công việc bên ngoài (HTTP request, database, executor, queue, job server, payment gateway) vẫn có thể hoàn thành. Có Java 17+ chạy được, bài kiểm thử Reactor, ví dụ Spring WebFlux và checklist triển khai.

## 1. Hiểu đúng vấn đề

Sau bài học bạn có thể:
1. Giải thích `Subscription.cancel()`, `Disposable.dispose()` và phân biệt hủy với `onComplete`/`onError`.
2. Nhận ra nơi cancellation phát sinh qua `take`, `timeout`, `switchMap`, các toán tử race, dispose của subscriber và client disconnect.
3. Phân biệt ba tầng: **ngừng chuyển kết quả xuống subscriber**, **báo nguồn upstream ngừng tạo dữ liệu**, và **thực sự dừng/hoàn tác công việc bên ngoài**.
4. Dùng `doOnCancel`, `doFinally`, `MonoSink/FluxSink.onCancel/onDispose`, `using` và `usingWhen` để quản lý tài nguyên đúng vòng đời.
5. Kiểm thử cancellation, cleanup, callback đến muộn và tác vụ độc lập vẫn hoàn tất mà không dùng các giả định timing mơ hồ.
6. Thiết kế idempotency, status lookup, deadline, retry và business cancellation khi có database transaction hoặc lệnh ghi từ xa.
7. Áp dụng vào Spring WebFlux khi người dùng đóng tab, SSE ngắt kết nối hoặc HTTP request bị timeout.

**Nguyên tắc quan trọng nhất:** `cancel()` là **yêu cầu dừng subscription**, không phải một lệnh hoàn tác mọi side effect đã bắt đầu. Chỉ khi nguồn/driver/hệ thống từ xa hỗ trợ cơ chế hủy phù hợp thì một phần công việc mới có thể dừng, và ngay cả khi hỗ trợ, **không thể mặc định rằng mọi công việc dừng ngay lập tức**.

## 2. Tín hiệu cancellation đi hướng nào?

Theo mô hình Reactive Streams, Subscriber đăng ký vào Publisher, nhận `Subscription`, dùng `request(n)` để báo demand và `cancel()` khi không còn cần dữ liệu. Publisher chuyển `onNext`, `onError` hoặc `onComplete` về Subscriber. Cancellation là tín hiệu điều khiển **đi ngược về upstream**, khác với tín hiệu kết thúc **đi xuống downstream**.

~~~text
Dữ liệu và kết quả:
Publisher / upstream ── onNext, onError, onComplete ──> Subscriber / downstream

Điều khiển:
Subscriber ── request(n), cancel() ──> các operator ──> Subscription của nguồn

Có thể xảy ra:
client cancel → Reactor hủy upstream → client HTTP cố ngắt kết nối
                                         |
                                         +→ remote server vẫn đã nhận request
                                         +→ DB đã hoặc đang commit
                                         +→ thread bên ngoài vẫn chạy
                                         +→ cleanup có thể tiếp tục bất đồng bộ
~~~

`Mono<T>` có 0 hoặc 1 giá trị; `Flux<T>` có 0 đến nhiều giá trị. **onComplete** là kết thúc thành công; **onError** là lỗi; còn **cancel** biểu diễn phía tiêu thụ không muốn đợi nữa. Đừng viết một API mong rằng sau cancellation sẽ nhận `onComplete` như bằng chứng hủy thành công. Đặc biệt, `doOnComplete` không thay thế `doOnCancel` hoặc cleanup tài nguyên được kích hoạt trên mọi đường kết thúc.

Có thể có race: một callback hoặc tín hiệu đã được đưa vào queue khi `cancel()` xảy ra. Sau hủy, Reactor có thể bỏ tín hiệu đến muộn hoặc ghi nhận dropped signal tùy operator/hook. Không dùng thứ tự log của hai thread để suy ra chắc chắn “nguồn chưa thực thi”.

### 2.1. `dispose()` là hủy subscription cục bộ

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
Disposable subscription = ticks.subscribe(System.out::println);

// Khi không muốn tiếp tục nhận tick:
subscription.dispose();
~~~

Đây là fragment, cần import `Flux`, `Disposable`, `Duration`. `subscribe()` trả `Disposable` đại diện subscription, gọi `dispose()` tương ứng yêu cầu hủy. Nó không trả chứng từ remote server đã dừng. Ví dụ dùng subscriber tự quản lý trong ứng dụng CLI; **trong controller Spring WebFlux, thường trả Mono/Flux cho framework thay vì tự subscribe**. Nếu controller vừa subscribe để tạo side effect rồi vừa trả một Publisher khác, công việc có thể mất ràng buộc với lifecycle HTTP, lỗi bị bỏ qua và retry có thể tạo trùng.

### 2.2. Ba tầng cancellation

| Tầng | Điều cancel có thể thực hiện | Điều không thể tự suy ra |
| --- | --- | --- |
| Downstream | Ngừng chờ/nhận thêm dữ liệu từ subscription đã hủy | Không chứng minh mọi callback đã chạy xong. |
| Upstream/reactive client | Truyền yêu cầu ngừng source; cancel timer, giải phóng queue, đóng hoặc ngắt request nếu driver hỗ trợ | Không bảo đảm blocking call hoặc I/O đã gửi dừng ngay. |
| Side effect bên ngoài | API có thể hỗ trợ hủy request, rollback giao dịch chưa commit, unregister listener | Không thể tự động hoàn tác một commit, thanh toán, email hoặc job đã hoàn thành. |

**Ví dụ:** trình duyệt gửi POST, server gọi hệ thống thanh toán. Trình duyệt timeout và đóng kết nối ở giây thứ hai; gateway có thể commit charge ở giây thứ ba. Nếu người dùng retry POST với id mới, có nguy cơ thanh toán hai lần. Đây là vấn đề **idempotency và xác minh trạng thái giao dịch**, không giải quyết được chỉ bằng Reactor cancel.

## 3. Cancellation có thể xuất hiện trong những operator nào?

| Nguồn cancellation | Vì sao xảy ra | Lưu ý về công việc ngoài |
| --- | --- | --- |
| `take(n)` | Đã nhận đủ n phần tử | Downstream có thể complete; upstream bị cancel để dừng phát phần còn lại. |
| `Flux.next()` | Chỉ lấy phần tử đầu tiên | Không chờ cả Flux hoàn thành. |
| `timeout(Duration)` | Hết ngân sách chờ | Có thể hủy upstream dù remote vẫn đang xử lý. |
| `switchMap` | Publisher inner mới thay thế inner cũ | Hủy inner cũ không bảo đảm request cũ chưa thực thi. |
| `firstWithSignal` / `firstWithValue` | Winner được chọn, các loser đã subscribe có thể bị cancel | Hai hệ thống có thể đều đã nhận request. |
| `flatMap` kết thúc lỗi | Các inner khác có thể bị hủy theo chính sách lỗi | Các side effect inner đã bắt đầu không nhất thiết được hoàn tác. |
| `Disposable.dispose()` | Subscriber tự ngừng quan tâm | Chỉ hủy subscription được nắm giữ. |
| Client disconnect trong WebFlux | Framework có thể ngắt Publisher của response | Khả năng remote dừng phụ thuộc connector, proxy, timing. |

Đừng khẳng định mọi trường hợp trên đều sinh đúng một callback `doOnCancel` cho mọi nguồn trong mọi race hoặc tối ưu hóa. Quan sát vị trí operator, trạng thái subscription và khả năng nguồn tôn trọng cancel.

### 3.1. `take(1)`: complete ở dưới, cancel ở trên

~~~java
Flux<Integer> stream = Flux.range(1, 100)
    .doFinally(type -> System.out.println("upstream: " + type))
    .take(1)
    .doFinally(type -> System.out.println("downstream: " + type));
~~~

Fragment minh họa sự khác nhau của đường kết thúc: downstream sau `take(1)` có thể thấy **ON_COMPLETE** vì đã lấy đủ phần tử, trong khi nguồn phía trước có thể nhận **CANCEL** vì không cần 99 phần tử nữa. **Không dựa vào thứ tự chính xác các dòng log** của `doFinally` làm đồng bộ nghiệp vụ. `doFinally` chạy sau khi terminal signal được chuyển tới downstream và có thể được thực thi ở thread khác.

### 3.2. Timeout không phải rollback

~~~java
Mono<Response> result = remoteWrite()
    .timeout(Duration.ofSeconds(2));
~~~

Đây là fragment có `remoteWrite()` do ứng dụng định nghĩa. Hết 2 giây, downstream nhận lỗi timeout và Reactor hủy upstream. Nếu bên ngoài đã nhận lệnh ghi thì vẫn có thể commit sau đó. Khi một POST timeout, **không tự retry không giới hạn** hoặc gửi lệnh mới với khóa khác; trước hết phải biết giao thức idempotency và trạng thái remote.

## 4. Tín hiệu hủy không phải kết thúc thành công

### 4.1. `doOnCancel`

~~~java
Mono<String> result = callRemote()
    .doOnCancel(() -> metrics.incrementCancellation());
~~~

`doOnCancel` là hook **chỉ khi cancel**. Theo Javadoc, hook chạy trước khi tín hiệu cancel được truyền về upstream của operator đó. Nó có thể ghi metric hoặc yêu cầu tài nguyên stop; nhưng câu “hook đã chạy” **không có nghĩa** remote task đã dừng. Callback nên nhanh, idempotent, thread-safe, tránh blocking hoặc khởi chạy một Mono rồi bỏ mặc không quản lý.

### 4.2. `doFinally` và `SignalType`

~~~java
Flux<String> events = eventSource()
    .doFinally(type -> {
        if (type == SignalType.CANCEL) {
            metrics.cancelled();
        } else if (type == SignalType.ON_ERROR) {
            metrics.failed();
        } else if (type == SignalType.ON_COMPLETE) {
            metrics.completed();
        }
    });
~~~

Fragment giả định `eventSource()` và `metrics` đã có. `doFinally` thích hợp ghi metric cho **mọi** kết thúc (hoàn thành, lỗi, hủy). Với complete/error, callback thực hiện **sau khi terminal signal được truyền xuống downstream**. Nếu test cần khẳng định side effect trong doFinally, thiết kế đồng bộ phù hợp; đừng tự động suy rằng `block()` vừa trả kết quả thì mọi hook đều đã hoàn tất.

**So sánh:**
- `doOnComplete` của Flux chỉ cho hoàn tất thành công, không phải cleanup đầy đủ khi lỗi/hủy.
- `doOnError` chỉ cho lỗi.
- `doOnCancel` chỉ cho hủy.
- `doFinally` cho cả hoàn tất/lỗi/hủy, phù hợp đếm và quan sát.
- `doOnDiscard` dành cho một số operator có phần tử bị loại trong queue/buffer; hook discard nên idempotent và không đồng nghĩa đã cancel external task.
- `MonoSink.onCancel`/`FluxSink.onCancel` phù hợp tích hợp cancellation handle của một SDK bên ngoài.
- `onDispose` của sink bao phủ cả cancel và terminal signal để đóng resource.

Nếu cleanup phải chạy bất đồng bộ, ví dụ `connection.close()` trả Publisher, việc gọi `connection.close()` trong một `doFinally` rồi bỏ qua Publisher sẽ **không bảo đảm cleanup được chạy**. Dùng `usingWhen` hoặc resource manager có lifecycle rõ ràng thay vì `.subscribe()` không được kiểm soát ở callback.

## 5. Callback SDK: gắn tài nguyên vào MonoSink/FluxSink

Nhiều SDK legacy trả kết quả qua callback và một handle để hủy/unregister. Reactor có `Mono.create`/`Flux.create` để nối API đó vào pipeline.

### 5.1. Một callback trả một kết quả

~~~java
Mono<Result> result = Mono.create(sink -> {
    CancelHandle handle = client.fetchAsync(
        value -> sink.success(value),
        error -> sink.error(error)
    );

    sink.onCancel(handle::cancel);
    sink.onDispose(handle::close);
});
~~~

**Đây là fragment**, `Result`, `CancelHandle`, `client` và các method tương ứng do ứng dụng định nghĩa. `onCancel` chuyển yêu cầu hủy đến handle; `onDispose` dọn resource khi hoàn tất, lỗi hoặc cancel. Nên bảo đảm `cancel`/`close` idempotent và chịu được race callback đến đúng lúc hủy. **Mỗi loại callback trên một sink chỉ nên đăng ký một lần**; nếu có nhiều tài nguyên thì gộp cleanup có thứ tự.

**Quan trọng:** `handle.cancel()` có thể chỉ hủy việc đợi callback, có thể đóng kết nối hoặc có thể không thực sự ngăn server xử lý. Phải đọc hợp đồng của thư viện và kiểm thử bằng server giả lập hoặc integration test.

### 5.2. Nguồn nhiều sự kiện: unregister listener

~~~java
Flux<Event> events = Flux.create(sink -> {
    ListenerHandle registration = externalClient.register(
        event -> sink.next(event),
        error -> sink.error(error)
    );

    sink.onDispose(registration::unregister);
}, FluxSink.OverflowStrategy.ERROR);
~~~

Đây cũng là fragment, cần kiểu `Event`, `ListenerHandle` và `externalClient`. Khi hoàn tất/lỗi/cancel, đăng ký callback được tháo. **Một callback đã nằm trong queue của SDK vẫn có thể chạy** sau unregister; do đó xử lý cạnh tranh và làm cleanup idempotent. `OverflowStrategy.ERROR` biểu thị một chính sách khi upstream không đáp ứng backpressure; đây không phải lựa chọn bắt buộc cho mọi nguồn sự kiện. Với nguồn nóng và subscriber chậm, cần chính sách buffer hữu hạn/drop/latest/broker phù hợp, tránh bộ đệm vô hạn.

### 5.3. `sink.success` sau cancel

Nếu external callback gọi `sink.success("done")` sau khi downstream cancel, kết quả không nhất thiết được giao cho subscriber đã hủy; Reactor có thể bỏ tín hiệu đến muộn. Nhưng external callback **đã chạy** và tác vụ bên ngoài có thể đã commit. Vì vậy không dùng “không có onNext” làm bằng chứng “không có giao dịch”.

## 6. Java 17+ chạy được: subscription đã hủy nhưng job ngoài vẫn hoàn thành

Ví dụ này dùng `ExecutorService` mô phỏng một **remote job độc lập**. Một `CountDownLatch` giữ worker lại cho đến khi `Disposable.dispose()` đã được gọi, nên kết quả không phụ thuộc timing ngẫu nhiên giữa hai thread. **Chúng ta cố ý không kết nối cancel với task ngoài**, để quan sát giới hạn của Reactor cancellation.

### 6.1. Cấu trúc dự án

~~~text
reactor-cancellation/
├── pom.xml
├── src/main/java/com/example/cancel/CancellationDemo.java
└── src/test/java/com/example/cancel/CancellationTest.java
~~~

**pom.xml** — Java 17, Reactor Core 3.8.8, Reactor Test và JUnit Jupiter:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-cancellation</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. `CancellationDemo.java`

**src/main/java/com/example/cancel/CancellationDemo.java**

~~~java
package com.example.cancel;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.Disposable;
import reactor.core.publisher.Mono;

public final class CancellationDemo {
    private CancellationDemo() {}

    public static void main(String[] args) throws Exception {
        ExecutorService remoteJob = Executors.newSingleThreadExecutor();
        CountDownLatch releaseJob = new CountDownLatch(1);
        CountDownLatch finishedJob = new CountDownLatch(1);

        AtomicInteger started = new AtomicInteger();
        AtomicInteger cancelHooks = new AtomicInteger();
        AtomicInteger remoteCompleted = new AtomicInteger();
        AtomicInteger delivered = new AtomicInteger();

        try {
            Mono<String> operation = Mono.create(sink -> {
                started.incrementAndGet();

                // Công việc bên ngoài chạy độc lập với Subscription.
                remoteJob.execute(() -> {
                    try {
                        releaseJob.await();
                        remoteCompleted.incrementAndGet();
                        sink.success("done");
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        sink.error(ex);
                    } finally {
                        finishedJob.countDown();
                    }
                });

                sink.onCancel(() -> cancelHooks.incrementAndGet());
            });

            Disposable subscription = operation.subscribe(
                value -> delivered.incrementAndGet());

            // Hủy trước, rồi mới cho external job hoàn tất.
            subscription.dispose();
            releaseJob.countDown();

            if (!finishedJob.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("job did not finish");
            }

            System.out.println("started=" + started.get());
            System.out.println("cancelHooks=" + cancelHooks.get());
            System.out.println("remoteCompleted=" + remoteCompleted.get());
            System.out.println("delivered=" + delivered.get());
        } finally {
            releaseJob.countDown();
            remoteJob.shutdownNow();
        }
    }
}
~~~

**Giải thích:** `Mono.create` chạy callback khi subscribe, tăng `started` và lên lịch worker riêng. `Disposable.dispose()` hủy subscription và kích hoạt `sink.onCancel`; sau đó latch mới cho worker tiếp tục. Worker vẫn tăng `remoteCompleted` và gọi `sink.success`, nhưng subscriber đã hủy nên không nhận kết quả. Việc `remoteJob.shutdownNow()` trong `finally` chỉ cleanup ví dụ CLI, không chứng minh hủy subscription có thể dừng external job.

### 6.3. Lệnh chạy

Trong thư mục dự án:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.cancel.CancellationDemo
~~~

**Stdout từ các dòng System.out.println trong main**:

~~~text
started=1
cancelHooks=1
remoteCompleted=1
delivered=0
~~~

Mã dùng latch để bảo đảm thứ tự, không dựa vào `Thread.sleep` hoặc hy vọng scheduler chạy đúng mili-giây. **Kết quả chứng minh rõ:** việc không giao kết quả cho subscriber là chuyện khác với công việc bên ngoài đã kết thúc. Trong ứng dụng WebFlux, không tự tạo một executor riêng trong mỗi request; cần resource manager/job service có giới hạn và trạng thái bền vững.

## 7. Nếu external API hỗ trợ cancel thì sao?

Khi SDK trả về cancellation handle, `Future`, `ScheduledFuture`, hoặc `AutoCloseable`, hãy gắn nó với subscription. Ví dụ minh họa một timer mà việc đã xếp lịch **có thể được ngăn nếu chưa chạy**:

~~~java
Mono<String> timerResult = Mono.create(sink -> {
    ScheduledFuture<?> future = timer.schedule(
        () -> sink.success("ready"),
        10, TimeUnit.SECONDS
    );
    sink.onCancel(() -> future.cancel(false));
});
~~~

Đây là fragment cần `ScheduledExecutorService timer` và import. `cancel(false)` cố hủy công việc **chưa bắt đầu**, không interrupt công việc đang thực thi. `cancel(true)` có thể gửi yêu cầu interrupt tới thread nhưng **không có cam kết tác vụ sẽ lập tức dừng**: code có thể bỏ qua interrupt, đang kẹt ở API không interruptible hoặc thao tác đã chuyển sang máy chủ khác.

**Cooperative cancellation:** nếu sở hữu code tác vụ dài, truyền cờ hủy/token và kiểm tra ở điểm an toàn, đồng thời đóng tài nguyên trong `finally`. Token cần gắn đúng scope subscription/job, không dùng một cờ toàn cục khiến hủy request A làm dừng request B.

~~~java
AtomicBoolean stop = new AtomicBoolean();

Mono<Result> computation = Mono.fromCallable(() -> {
    for (int i = 0; i < 100; i++) {
        if (stop.get() || Thread.currentThread().isInterrupted()) {
            throw new CancellationException("stopped cooperatively");
        }
        processChunk(i);
    }
    return assembleResult();
})
.subscribeOn(Schedulers.boundedElastic())
.doOnCancel(() -> stop.set(true));
~~~

**Fragment**, cần `Result`, các hàm nghiệp vụ và imports Java/Reactor. Mục đích là code *hợp tác* bằng cách kiểm tra cờ/interrupt; không tự chứng minh hệ thống bên ngoài đã rollback. Với nguồn blocking, boundedElastic giúp tránh giữ event-loop nhưng vẫn có giới hạn thread/queue và không biến blocking I/O thành non-blocking.

## 8. Quản lý tài nguyên: `using` và `usingWhen`

### 8.1. Cleanup đồng bộ với `Flux.using`

~~~java
Flux<Integer> values = Flux.using(
    () -> openHandle(),
    handle -> readValues(handle),
    handle -> handle.close()
);
~~~

Fragment giả định `openHandle()` trả resource có `close()` không ném checked exception và `readValues` trả Publisher. `using` tạo resource **theo subscription**, bao phạm vi dùng và cleanup trên complete/error/cancel. Khác với `try-with-resources` quanh lời gọi **tạo** Mono: nếu đóng resource ngay khi phương thức return, Mono có thể chưa được subscribe và bước đọc về sau dùng resource đã đóng.

Nếu `close()` có checked exception, cần xử lý trong cleanup callback theo hợp đồng hệ thống. Cleanup đồng bộ cũng có thể blocking: tránh đưa việc đóng I/O dài lên event-loop.

### 8.2. Cleanup bất đồng bộ với `usingWhen`

~~~java
Mono<Result> result = Mono.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> doQuery(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
~~~

**Fragment** cho driver R2DBC-like: `connectionFactory.create()` và `connection.close()` trả Publisher, `doQuery(connection)` trả Mono<Result>. `usingWhen` liên kết resource với chuỗi xử lý và **Publisher cleanup riêng** khi complete, error hoặc cancel. Ở production, nhánh error/cancel có thể cần rollback transaction chưa commit rồi mới close; ví dụ chỉ close vì chưa thể giả định chi tiết transaction.

**Điểm quan trọng:** cleanup bất đồng bộ khi cancel có thể còn chạy sau khi subscriber ngừng đợi; cần metric/log về lỗi cleanup. `usingWhen` giúp quản lý lifecycle resource, nhưng **không phải một giao dịch phân tán**: commit đã hoàn tất thì không có rollback ma thuật. Nếu cần đảm bảo nghiệp vụ qua nhiều dịch vụ, dùng trạng thái bền vững, idempotency, outbox, inbox/dedup hoặc compensation.

### 8.3. Chọn đúng cơ chế

| Cơ chế | Phù hợp | Giới hạn |
| --- | --- | --- |
| `doOnCancel` | Ghi metric hủy, kích hoạt cancellation handle | Hook chạy không chứng minh external đã dừng. |
| `doFinally` | Phân loại complete/error/cancel, telemetry | Không tự chạy cleanup Publisher nếu chỉ tạo nó. |
| `MonoSink/FluxSink.onCancel` | Liên kết `CancelHandle` từ callback API | Chất lượng hủy tùy API ngoài. |
| `MonoSink/FluxSink.onDispose` | Unregister/close resource trên mọi kết thúc | Callback đang in-flight có thể vẫn chạy. |
| `Flux.using` / `Mono.using` | Resource có cleanup đồng bộ | Chưa tự giải quyết I/O cleanup bất đồng bộ. |
| `Flux.usingWhen` / `Mono.usingWhen` | Resource và cleanup bất đồng bộ kể cả cancel | Không thể undo external commit đã xảy ra. |
| Business cancellation API | Hủy job và nhận trạng thái xác minh | Cần giao thức, lưu trạng thái và kiểm tra race. |

## 9. Kiểm thử hành vi cancel bằng Reactor Test

`StepVerifier` giúp kiểm tra Reactor có chuyển cancel và cleanup tại đúng boundary. Các test này **không thay thế integration test với remote server** khi muốn biết công việc ngoài có ngừng thật hay không.

**src/test/java/com/example/cancel/CancellationTest.java**

~~~java
package com.example.cancel;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CancellationTest {

    @Test
    void cancelIsDifferentFromCompletion() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.create(
                Flux.<Long>never().doFinally(type -> {
                    if (type == SignalType.CANCEL) {
                        cancelled.set(true);
                    }
                }))
            .expectSubscription()
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void takeOneReleasesUsingResource() {
        AtomicInteger closed = new AtomicInteger();

        Flux<Integer> source = Flux.using(
            () -> "handle",
            handle -> Flux.concat(
                Flux.just(1), Flux.<Integer>never()),
            handle -> closed.incrementAndGet()
        );

        StepVerifier.create(source.take(1))
            .expectNext(1)
            .verifyComplete();

        assertEquals(1, closed.get());
    }

    @Test
    void timeoutCancelsUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofHours(2))
                    .doOnCancel(() -> cancelled.set(true))
                    .timeout(Duration.ofHours(1)))
            .expectSubscription()
            .thenAwait(Duration.ofHours(1))
            .expectError(TimeoutException.class)
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void cancelDoesNotInvokeOnComplete() {
        AtomicInteger cancels = new AtomicInteger();
        AtomicInteger completions = new AtomicInteger();

        Flux<Integer> never = Flux.<Integer>never()
            .doOnCancel(cancels::incrementAndGet)
            .doOnComplete(completions::incrementAndGet);

        StepVerifier.create(never)
            .expectSubscription()
            .thenCancel()
            .verify();

        assertEquals(1, cancels.get());
        assertEquals(0, completions.get());
    }
}
~~~

**Giải thích test:**
- Test 1 xác minh `SignalType.CANCEL` được quan sát khi chính subscriber hủy.
- Test 2 xác minh `Flux.using` đóng resource khi `take(1)` ngừng phần còn lại dù downstream đã complete.
- Test 3 dùng **virtual time**, tạo `Mono.delay` **trong supplier** của `withVirtualTime`, hủy upstream sau một giờ ảo thay vì chờ thật.
- Test 4 chứng minh cancel không đồng nghĩa `doOnComplete`.

Nếu phải kiểm thử cleanup **bất đồng bộ** của `usingWhen`, hãy chờ Publisher cleanup hoặc có latch kiểm soát, tránh assert tức thì sau cancel rồi gặp flaky timing. Với test HTTP thực, dùng server giả lập có barrier xác nhận đã **nhận request** trước lúc bạn cancel để kiểm chứng outcome chính xác hơn `Thread.sleep`.

## 10. Tích hợp Spring WebFlux khi client ngắt kết nối

Trong WebFlux, controller **trả Mono/Flux** để framework quản lý subscription và viết HTTP response. Khi client rời đi hoặc mạng bị ngắt, framework/connector **có thể** chuyển cancellation về Publisher của response. Điều gì xảy ra tại remote endpoint phụ thuộc vào network, HTTP client, driver và thời điểm request đã tới server hay chưa.

**Fragment controller** (cần Spring Boot WebFlux, một bean `JobStatusService` và DTO `JobStatus`):

~~~java
package com.example.web;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@RestController
@RequestMapping("/api/jobs")
public class JobStatusController {
    private final JobStatusService jobs;

    public JobStatusController(JobStatusService jobs) {
        this.jobs = jobs;
    }

    @GetMapping("/{id}/status")
    public Mono<JobStatus> status(@PathVariable String id) {
        return jobs.readStatus(id)
            .timeout(Duration.ofSeconds(2))
            .doFinally(type -> {
                if (type == SignalType.CANCEL) {
                    jobs.recordSubscriberCancellation(id);
                }
            });
    }
}
~~~

`recordSubscriberCancellation` ở đây nên là ghi metric nhanh, non-blocking và không phụ thuộc việc client còn kết nối. Nếu phải ghi DB bất đồng bộ, hãy dùng cơ chế telemetry/job với lifecycle riêng, tránh `.subscribe()` trong callback một cách tùy tiện. Hook CANCEL **chỉ nói về subscription tới response status**, không có nghĩa job đã được hủy.

### 10.1. Phân biệt tác vụ có thể bỏ và công việc phải tiếp tục

- **GET/search/SSE/stream tạm thời:** khi người đọc rời đi, thường nên hủy truy vấn/timer/listener để tiết kiệm tài nguyên, đặt timeout và release connection. Cần test driver hỗ trợ hủy đến đâu.
- **Lệnh nghiệp vụ đã nhận:** tạo hóa đơn, thanh toán, phát hành chứng từ, gửi thông báo hoặc chạy báo cáo nền. Người dùng đóng tab không có nghĩa nghiệp vụ được phép ngừng tùy ý; tác vụ có thể cần hoàn tất hoặc ghi nhận kết quả để tra cứu.

Với job dài, thiết kế một API **submit → lưu job trong storage/queue → trả 202 Accepted + jobId → GET status**. Nếu hỗ trợ hủy job, thêm endpoint yêu cầu hủy và trả trạng thái **cancellation requested** rồi **cancelled/finished/failed** sau khi worker xác nhận. Không coi đóng kết nối HTTP là API hủy nghiệp vụ. Trả 202 chỉ sau khi job đã được ghi nhận đáng tin cậy, không chỉ tạo một Publisher rồi bỏ đó.

### 10.2. Retry sau timeout cần idempotency

~~~text
POST /payments với Idempotency-Key = k
   |
   v
Backend → Payment gateway
   |
   +-- Client timeout / đóng kết nối
   |
   +-- Gateway vẫn commit charge thành công
           |
           +-- Client retry POST cùng k
                   |
                   +-- Trả outcome đã ghi nhận, không charge lần hai
~~~

Để có tính đúng đắn, hệ thống phải lưu kết quả/idempotency key hoặc tra cứu transaction ID với gateway. `timeout`, `cancel`, `doFinally` hoặc `onErrorResume` **không tự bảo đảm exactly-once**. Nếu không biết remote đã commit chưa, không mặc định request đã thất bại; có thể cần trạng thái “đang xác minh” và quy trình reconcile.

## 11. Transaction, rollback và tác vụ bên ngoài

Với database reactive, một transaction có thể hỗ trợ rollback khi chuỗi thất bại hoặc bị hủy **trước khi commit** tùy transaction manager và driver; nhưng cần kiểm chứng thời điểm và hành vi thực tế:
1. Lệnh **chưa gửi**: cancel có thể tránh thực thi.
2. Lệnh đã gửi và đang xử lý: driver/backend có thể nhận yêu cầu hủy, hoặc có thể đã thực hiện bước không thể đảo ngược.
3. Transaction **đã commit**: cancel đến sau không tự rollback được.
4. External service **đã nhận lệnh**: rollback DB local không đảo ngược email, charge, publish message ở hệ thống khác.

Dùng ReactiveTransactionManager/TransactionalOperator hoặc transaction phù hợp của R2DBC khi cần, thiết kế transaction boundary rõ ràng. Không trộn JDBC blocking và R2DBC rồi mặc định chúng chia sẻ một reactive transaction nguyên tử. Với side effect xuyên dịch vụ, dùng outbox, inbox/deduplication, idempotent consumer, saga/compensation hoặc trạng thái bền vững tùy domain.

**Lưu ý về cancellation token:** nếu một tác vụ CPU hoặc blocking do bạn sở hữu, có thể kiểm tra cờ hủy/interrupt ở các điểm an toàn. Nhưng cờ của JVM không thể làm remote server dừng nếu thiếu giao thức truyền yêu cầu hủy. Với `Future.cancel(true)`, interrupt chỉ là **yêu cầu**, code phải hợp tác mới dừng; với `cancel(false)`, công việc đã bắt đầu có thể tiếp tục chạy.

## 12. Tình huống và cách xử lý

### 12.1. Client đóng SSE

Một `Flux.interval` phát sự kiện SSE liên tục. Client đóng kết nối, Publisher bị cancel, timer nguồn có thể được ngừng. Nếu SSE kết nối tới broker có registration bên ngoài, cần `onDispose`/`usingWhen` để unsubscribe và release tài nguyên. **Một sự kiện đã xếp hàng trước cancel vẫn có thể chạy** trên thread producer; callback cần kiểm tra lifecycle và hỗ trợ cleanup idempotent.

### 12.2. Polling WebClient timeout

Một WebClient gọi API phụ, `.timeout(2s)` phát lỗi. Request HTTP local có thể được hủy/connection đóng tùy connector; nhưng server phụ **có thể tiếp tục xử lý**. Với GET đọc/idempotent, retry có giới hạn đôi khi chấp nhận được; với POST ghi, cần idempotency. Đo cả `clientCancelled`, `remoteCompleted`, `remoteFailed` ở những nơi có thể đo, không gộp hết thành “failed”.

### 12.3. `firstWithValue` đua hai replica

Hai nguồn cùng được subscribe; một nguồn phát dữ liệu trước làm winner, nguồn thua bị cancel. Request tới loser có thể **đã ra khỏi máy**; race phù hợp cho đọc/idempotent, không dùng cho hai lệnh chuyển tiền. Nếu cần dữ liệu từ cả hai, chọn zip/merge thay vì race.

### 12.4. Công việc xử lý file lớn

Một task xử lý file từ SDK blocking có thể chạy trên boundedElastic. Khi client hủy, token hủy nên được truyền vào vòng xử lý và kiểm tra giữa các chunk; dọn file tạm và stream trong finally hoặc resource manager. Nếu SDK không hỗ trợ interruption, nó có thể tiếp tục đến khi tự hoàn tất. Dùng giới hạn concurrency và queue; boundedElastic không biến I/O blocking thành non-blocking.

### 12.5. Người dùng bấm “Cancel job”

Đây là hành động nghiệp vụ **có trạng thái riêng**, khác với đóng kết nối. Hệ thống cần ghi nhận yêu cầu hủy, chuyển nó tới worker/job service, kiểm tra trạng thái đã bắt đầu/đã commit, xác nhận `cancelled`, `tooLate`, `finished` hoặc `failed` theo domain. Không thể cam kết “cancelled” trước khi worker báo đã dừng ở điểm an toàn.

## 13. Các lỗi thường gặp

| Lỗi hiểu / triển khai | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `dispose()` được coi như rollback DB | DB/remote vẫn có thể commit | Phân biệt Subscription và transaction outcome. |
| `doOnCancel` chạy nên cho rằng server đã dừng | Chỉ biết hook đã kích hoạt | Test cancellation của SDK và trạng thái server. |
| Timeout xong retry POST không có idempotency | Dữ liệu/charge có thể trùng | Idempotency key, status lookup, dedup. |
| Chỉ đóng tài nguyên tại `doOnComplete` | Leak khi lỗi/hủy | `using`, `usingWhen`, `onDispose` hoặc cleanup cho mọi nhánh. |
| Gọi `.subscribe()` để chạy async cleanup ngay trong hook | Lỗi và lifecycle khó quan sát | `usingWhen` hoặc resource manager chuyên trách. |
| Dùng `Future.cancel(true)` như lệnh kill chắc chắn | Tác vụ bỏ qua interrupt và tiếp tục | Cooperative cancellation, deadline, thực nghiệm. |
| Tin rằng không thấy `onNext` nghĩa là remote chưa chạy | Phân tích sai trạng thái nghiệp vụ | Đo state của remote, transaction ID. |
| Gắn tên “cancel” cho `onComplete` | Metric completion/cancel sai | Dùng `doFinally` và `SignalType`. |
| Tạo worker/executor theo từng HTTP request | Cạn thread, queue, heap | Pool có giới hạn, job service, backpressure. |
| `Flux.create` phát quá nhanh, không cleanup listener | Tăng RAM và callback bị treo | Chiến lược backpressure, `onDispose`. |
| Ngắt HTTP rồi tin job nền đã hủy | Hành vi không được xác nhận | API yêu cầu hủy job riêng và trạng thái. |
| Chia sẻ cancellation token giữa nhiều subscriber | Một cancel ảnh hưởng request khác | Token đúng scope subscription/job. |

## 14. Checklist trước khi đưa vào production

- [ ] Biết ai sở hữu **subscription, remote operation và tài nguyên** ở từng tầng.
- [ ] Không coi `cancel` là `onComplete`, `onError`, transaction rollback hay business cancellation.
- [ ] Kiểm tra onCancel/onDispose và cleanup trên complete/error/cancel bằng test rõ ràng.
- [ ] Với external SDK, có cancellation handle hoặc ghi rõ giới hạn khi không hỗ trợ.
- [ ] Với callback/hot source, có unsubscribe idempotent và chính sách backpressure.
- [ ] Async resource dùng `usingWhen`/resource manager; lỗi cleanup được theo dõi.
- [ ] Ghi dữ liệu từ xa có idempotency key, transaction ID, status lookup hoặc dedup.
- [ ] Client disconnect và retry được test ở **trước/sau remote receive**, **trước/sau commit**.
- [ ] Có timeout và deadline ở từng hop, đồng thời không dùng timeout làm bằng chứng rollback.
- [ ] Không block Reactor Netty event-loop; boundedElastic có giới hạn tải và được giám sát.
- [ ] Theo dõi metric `cancelled`, `timedOut`, `completed`, external job result, cleanup failure và leak.
- [ ] Nếu sản phẩm cần hủy job thật, có API và trạng thái xác minh riêng: requested, cancelled, too late, finished.

## 15. Tài liệu tham khảo

1. Reactor Core 3.8.8 — `Mono`, `doOnCancel`, `doFinally`, `usingWhen`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
2. Reactor Core 3.8.8 — `Flux`, `using`, `usingWhen`, `doOnDiscard`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
3. Reactor `MonoSink` — `onCancel`, `onDispose`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/MonoSink.html
4. Reactor `FluxSink` — lifecycle và callback: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/FluxSink.html
5. Reactor Test — `StepVerifier`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
6. Reactive Streams Specification: https://www.reactive-streams.org/
7. Spring Framework WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
8. Spring Data R2DBC: https://docs.spring.io/spring-data/relational/reference/r2dbc.html

**Tự đánh giá:** Nếu một client đặt hàng bị timeout sau khi server gửi lệnh thanh toán, `doFinally(CANCEL)` chạy, liệu bạn có thể khẳng định tiền chưa bị trừ? **Không.** Bạn chỉ biết subscription cục bộ không còn chờ. Phải kiểm tra outcome của gateway, idempotency key, trạng thái transaction và cơ chế hủy nghiệp vụ có xác nhận. Đó là khác biệt quyết định khi xây dựng hệ thống reactive an toàn.
