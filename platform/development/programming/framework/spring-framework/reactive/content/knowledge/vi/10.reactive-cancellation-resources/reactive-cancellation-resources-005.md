# Dọn dẹp khi hoàn tất, lỗi hoặc hủy đăng ký trong Spring Reactive

## 1. Vì sao quản lý tài nguyên là một phần của lập trình reactive?

Trong **Project Reactor** và **Spring WebFlux**, một `Mono<T>` hoặc `Flux<T>` thường đại diện cho công việc chỉ thực sự diễn ra khi có người **subscribe**. Công việc đó có thể giữ kết nối, phiên giao dịch, stream tệp, listener, timer, HTTP request hoặc một handle của SDK bên ngoài. Khi downstream không còn cần dữ liệu, hoặc nguồn đã kết thúc, những thứ này cần được giải phóng.

Lập trình reactive có **ba đường kết thúc quan trọng**:

1. **Hoàn tất thành công — `onComplete`**: nguồn phát hết dữ liệu, kể cả trường hợp không phát phần tử nào.
2. **Thất bại — `onError`**: nguồn gặp lỗi; `onError` kết thúc subscription, không có thêm `onNext` hay `onComplete` sau đó.
3. **Hủy đăng ký — `cancel`**: subscriber hoặc toán tử downstream yêu cầu dừng upstream trước khi nó hoàn tất tự nhiên; cancel là lệnh trên `Subscription`, **không phải** tín hiệu `onComplete` hoặc `onError` gửi cho subscriber.

**Dọn dẹp đúng nghĩa là tài nguyên phải được thu hồi trên cả ba đường**, chứ không chỉ ở nhánh “chạy xong”. Nếu chỉ đóng tài nguyên trong callback thành công, một kết nối SSE bị ngắt hoặc một database query lỗi có thể để lại listener và socket. Ngược lại, nếu chỉ dùng `doOnCancel`, nhánh thành công và thất bại tự nhiên có thể chưa được dọn.

Phân biệt ba thuật ngữ:

| Khái niệm | Vai trò | Điều không được nhầm |
| --- | --- | --- |
| **Kết thúc** (`onComplete` hoặc `onError`) | Nguồn gửi terminal signal | Không phải mọi thao tác bị dừng đều là lỗi |
| **Hủy** (`cancel`) | Downstream yêu cầu upstream ngừng gửi/không xử lý tiếp | Không đảm bảo subscriber nhận một terminal signal mới |
| **Dọn tài nguyên** (cleanup/dispose/close) | Gỡ listener, đóng stream, giải phóng handle, hoàn tất phiên giao dịch | Không tự xảy ra với mọi API ngoài nếu không gắn logic |

Một publisher `Flux.never()` có thể không phát giá trị hoặc terminal nào; nó vẫn cần **dọn khi subscriber hủy** nếu đang giữ tài nguyên. Vì vậy lifecycle không thể chỉ dựa vào `onComplete` và `onError`.

## 2. Dòng đời của một subscription

Mô hình đơn giản:

~~~text
Subscriber.subscribe()
       |
       v
onSubscribe(subscription)
       |
       +-- onNext(value) ... onNext(value)
       |
       +-- onComplete() ---> COMPLETE ---> cleanup
       |
       +-- onError(error) -> ERROR ------> cleanup
       |
       +-- subscription.cancel() -------> CANCEL ---> cleanup
~~~

`onComplete` và `onError` là hai terminal signal **loại trừ lẫn nhau** cho cùng một subscription. Cancel có thể cạnh tranh về thời điểm với hoàn tất hoặc lỗi: chẳng hạn client đóng kết nối đúng lúc nguồn vừa kết thúc. Adapter/tài nguyên ngoài phải chịu được **race**, không giả định chỉ có một thread và chỉ một callback có thể đến.

Các trường hợp thực tế:

- Một HTTP client nhận hết response thành công → hoàn tất.
- Driver R2DBC trả lỗi truy vấn → lỗi.
- Người dùng đóng tab trình duyệt đang nghe SSE → server có thể phát hiện disconnect rồi hủy upstream.
- `take(3)` nhận đủ ba giá trị → toán tử có thể **hủy upstream** và gửi hoàn tất **cho downstream**.
- `timeout(...)` có thể hủy upstream đã vượt thời gian, rồi báo lỗi timeout cho downstream hoặc chuyển sang fallback.

**Vị trí quan sát ảnh hưởng tín hiệu quan sát được.** Nếu `doFinally` nằm trước `take(3)`, nó có thể thấy `CANCEL` từ `take`; hook sau `take(3)` thường thấy `ON_COMPLETE`. Không có mâu thuẫn: đó là hai đoạn của cùng pipeline, một bên hủy upstream, bên kia hoàn tất downstream.

## 3. `doFinally`: tương đương tinh thần với `finally`

`doFinally(Consumer<SignalType>)` cho phép thực hiện side effect khi chuỗi kết thúc bằng **complete, error hoặc cancel**. Nó nhận loại kết thúc qua `reactor.core.publisher.SignalType`:

- `SignalType.ON_COMPLETE`: nguồn/chuỗi được quan sát hoàn tất thành công.
- `SignalType.ON_ERROR`: nguồn/chuỗi được quan sát kết thúc bằng lỗi.
- `SignalType.CANCEL`: upstream của vị trí hook bị hủy.

Ví dụ:

~~~java
// Đoạn minh họa; requestCounter và timer là đối tượng ứng dụng.
Flux<Event> events = eventSource()
    .doOnSubscribe(subscription -> timer.start())
    .doFinally(signal -> {
        timer.stopAndRecord();
        if (signal == SignalType.CANCEL) {
            requestCounter.incrementCancelled();
        }
    });
~~~

Đây là đoạn **minh họa trong dự án**, không phải class chạy độc lập vì các loại `Event`, `eventSource`, `timer`, `requestCounter` do ứng dụng định nghĩa. Logic đo thời gian sẽ chạy khi complete, error hoặc cancel.

Có hai chi tiết dễ bỏ sót:

1. **`doFinally` được gọi sau khi tín hiệu terminal/cancel được truyền tới phía tương ứng.** Do đó subscriber có thể đã nhận `onComplete` trước khi callback `doFinally` chạy. Nếu một pipeline có nhiều `doFinally` nối nhau, callback có thể chạy theo **thứ tự ngược** với thứ tự khai báo do cách lan truyền terminal.
2. **`doFinally` chỉ là side effect, không phải cơ chế tự mở/đóng resource có scope.** Nó rất hợp để ghi metric, dọn một handle đã được quản lý đúng, nhưng khi phải cấp một tài nguyên riêng cho mỗi subscriber, dùng `using` hoặc `usingWhen` thường thể hiện vòng đời chặt chẽ hơn.

Đối với kiểm thử, không nên dựa vào việc ngay sau `block()`/signal completion thì mọi side effect `doFinally` đã chắc chắn hiện hữu trong một nguồn bất đồng bộ. Hãy dùng một điều kiện đồng bộ hoặc một StepVerifier/test hook phù hợp khi cần xác nhận cleanup.

## 4. Những hook có vẻ giống nhau nhưng phạm vi khác nhau

| Operator/hook | Khi chạy | Khi **không** chạy | Dùng cho |
| --- | --- | --- | --- |
| `doOnComplete` trên `Flux` | Ngay trước khi tín hiệu complete đi xuống downstream | Error hoặc cancel | Quan sát kết thúc thành công |
| `doOnError` | Khi lỗi đi qua pipeline tại vị trí hook | Complete hoặc cancel | Log lỗi, metrics |
| `doOnTerminate` | Trước `onComplete` hoặc `onError` | **Cancel thuần túy** | Theo dõi hai terminal signal |
| `doAfterTerminate` | Sau `onComplete` hoặc `onError` được truyền xuống | **Cancel thuần túy** | Side effect sau terminal |
| `doOnCancel` | Khi downstream hủy; trước khi cancel lan upstream qua vị trí đó | Complete hoặc error tự nhiên | Phản ứng riêng với hủy |
| `doFinally` | Sau complete, error **hoặc cancel** | Không chạy nếu chuỗi vẫn hoạt động mãi và không bị hủy | Cleanup/metric cho cả ba nhánh |
| `FluxSink.onCancel` | Khi subscription của bridge callback bị hủy | Complete hoặc error tự nhiên | Ra lệnh SDK dừng hoạt động |
| `FluxSink.onDispose` | Khi sink được dispose vì complete, error hoặc cancel | Không phải hook đếm từng `onNext` | Gỡ listener/handle dùng chung cho mọi đường kết thúc |

Các hook `doOnError` và `doFinally` không biến lỗi thành thành công; `onErrorResume` mới là toán tử tạo fallback. Và `doOnTerminate` **không** phải “finally” cho cả ba đường.

Ví dụ dễ mắc lỗi:

~~~java
// Sai nếu muốn giải phóng tài nguyên cả khi client bỏ đi:
source.doOnTerminate(resource::close);

// Tốt hơn nếu resource đã được quản lý theo đúng một subscription:
source.doFinally(signal -> resource.close());
~~~

Đây là ví dụ **chỉ về sự khác nhau giữa hook**, chưa phải mô hình tạo resource an toàn. Nếu `resource` được tạo một lần bên ngoài và `source` được nhiều subscriber dùng chung, nhiều callback có thể cố đóng cùng một đối tượng; thay vào đó hãy tạo và quản lý resource **trong một scope subscription** bằng `using`/`usingWhen`.

## 5. `Flux.using` và `Mono.using`: cấp và đóng resource đồng bộ

`using(resourceSupplier, sourceSupplier, resourceCleanup)` là tương đương reactive của `try-with-resources`: **tạo tài nguyên khi có subscriber**, dùng nó để tạo publisher, rồi gọi cleanup khi publisher hoàn tất, lỗi hoặc bị hủy.

Mẫu:

~~~java
// Mã cấu trúc minh họa; openReader và readAsFlux do ứng dụng cung cấp.
Flux<String> lines = Flux.using(
    () -> openReader(),
    reader -> readAsFlux(reader),
    reader -> reader.close(),
    true // eager cleanup
);
~~~

Ở đây `openReader()` phải cung cấp một reader **riêng cho subscription này**, tránh chia sẻ sai tài nguyên giữa các client. Hàm `readAsFlux(reader)` phải phát dữ liệu **khi reader còn mở**. Khi có kết thúc/hủy, cleanup đóng reader.

Tham số `eager` trong phiên bản 4 đối số có nghĩa:

- `eager = true`: cleanup được thực hiện **trước khi terminal signal được gửi downstream**. Nếu cleanup ném exception, nó có thể **thay thế** tín hiệu terminal gốc. Điều này hữu ích khi thành công chỉ được công nhận sau khi resource đóng sạch.
- `eager = false`: cleanup chạy **sau khi terminal đã được chuyển xuống**; exception trong cleanup thường không thể thay đổi kết quả đã gửi và có thể bị báo là dropped theo hook ứng dụng. Không nên mặc định bỏ qua lỗi dọn tài nguyên.
- Đối với **cancel**, không còn terminal downstream để gửi, nhưng resource vẫn cần được đóng.

Trong ứng dụng thật, một số resource thuộc sở hữu của database connection pool, HTTP client hoặc framework. **Chỉ đóng tài nguyên mình sở hữu**, không đóng pool toàn ứng dụng khi một request kết thúc. Cần biết resource là mỗi subscription, mỗi request, hay một singleton dùng chung.

`using` phù hợp khi thao tác cleanup **đồng bộ** (ví dụ `AutoCloseable.close()`). Nếu cleanup là publisher bất đồng bộ, như `session.rollback()` trả `Mono<Void>`, không nên gọi `block()` bên trong hook để chờ. Dùng `usingWhen`.

## 6. Ví dụ Java 17+ chạy được: chứng minh cleanup ở ba nhánh

Ví dụ này sử dụng **Reactor Core** (không cần khởi động Spring Boot), mô phỏng một tài nguyên có phương thức `close()`. Ba luồng độc lập lần lượt: hoàn tất tự nhiên, lỗi sau một phần tử, và chờ vô hạn cho đến khi subscriber hủy. Chương trình gom các mốc vào một danh sách rồi in **sau khi thao tác hoàn tất/hủy**, tránh phụ thuộc tên thread.

Cấu trúc:

~~~text
reactor-resource-lifecycle/
├── pom.xml
└── src/main/java/ResourceLifecycleDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-resource-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/ResourceLifecycleDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

public class ResourceLifecycleDemo {
    private static final class Resource implements AutoCloseable {
        private final List<String> events;
        private final AtomicBoolean closed = new AtomicBoolean();

        Resource(List<String> events) {
            this.events = events;
            events.add("open");
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                events.add("close");
            }
        }
    }

    private static void run(String name, Flux<Integer> body, boolean cancel) {
        List<String> events = new ArrayList<>();

        Flux<Integer> stream = Flux.using(
            () -> new Resource(events),
            resource -> body,
            Resource::close,
            true // Gọi cleanup trước terminal downstream.
        ).doFinally(signal -> events.add("finally:" + signal.name()));

        Disposable subscription = stream.subscribe(
            value -> events.add("next:" + value),
            error -> events.add("error:" + error.getMessage()),
            () -> events.add("complete")
        );

        if (cancel) {
            subscription.dispose();
        }

        System.out.println(name + " => " + String.join(" | ", events));
    }

    public static void main(String[] args) {
        run("success", Flux.just(1, 2), false);

        run("error",
            Flux.concat(
                Flux.just(7),
                Flux.<Integer>error(
                    new IllegalArgumentException("bad"))),
            false);

        run("cancel", Flux.<Integer>never(), true);
    }
}
~~~

Trong thư mục `reactor-resource-lifecycle`, với **JDK 17+** và **Maven**, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ResourceLifecycleDemo
~~~

**Stdout do chương trình in** (không tính thông báo của Maven):

~~~text
success => open | next:1 | next:2 | close | complete | finally:ON_COMPLETE
error => open | next:7 | close | error:bad | finally:ON_ERROR
cancel => open | close | finally:CANCEL
~~~

Giải thích:

1. **Thành công:** `Flux.just(1, 2)` phát hai giá trị rồi hoàn tất. Do `using(..., true)` đặt cleanup eager, `close` được ghi **trước** callback `complete`. `doFinally` chạy sau terminal với loại `ON_COMPLETE`.
2. **Lỗi:** nguồn `Flux.concat` phát 7 rồi phát lỗi. Resource vẫn được đóng, subscriber nhận `error:bad`, và `doFinally` quan sát `ON_ERROR`. Không có `complete` sau lỗi.
3. **Hủy:** `Flux.never()` không phát phần tử hoặc terminal. `subscribe()` trả về `Disposable`; khi gọi `dispose()`, subscription bị hủy, resource được đóng và `doFinally` quan sát `CANCEL`. Không có dòng `complete` hay `error` trong nhánh này.
4. `AtomicBoolean` bảo vệ `close()` khỏi thao tác lặp. Với SDK bất đồng bộ, việc cleanup cần thêm cơ chế thread-safety, đồng bộ đăng ký/hủy và giới hạn callback muộn.

Ví dụ này không có scheduler hoặc I/O bất đồng bộ, nên các nguồn synchronous và thao tác `dispose` đều thực hiện trong thread gọi; dòng output có thứ tự xác định. Trong ứng dụng mạng thực tế, không nên giả định callback cleanup chạy trên đúng một thread hoặc xuất hiện ngay khi HTTP client đóng tab.

## 7. `usingWhen`: cleanup bất đồng bộ theo từng đường kết thúc

Với driver reactive, việc “đóng” hoặc “rollback” có thể là **một publisher bất đồng bộ**, chẳng hạn `Mono<Void>` từ thao tác database. Nếu gọi một phương thức trả `Mono<Void>` mà **không subscribe hoặc không ghép vào pipeline**, cleanup có thể không chạy; còn nếu gọi `block()` trên event-loop WebFlux thì lại gây blocking.

`Mono.usingWhen` / `Flux.usingWhen` được thiết kế cho trường hợp này. Chữ ký đầy đủ có các nhánh riêng:

~~~java
// Mã mẫu khái niệm: resourcePublisher, work và các hàm cleanup
// phải được triển khai bằng publisher từ thư viện reactive.
Mono<Result> result = Mono.usingWhen(
    resourcePublisher,         // Publisher<Session>: cấp resource
    session -> work(session),  // Mono<Result>: dùng resource
    session -> close(session), // Khi hoàn tất thành công
    (session, error) -> rollbackAndClose(session, error), // Khi lỗi
    session -> cancelAndClose(session)   // Khi bị hủy
);
~~~

Đây là **ví dụ khung API**, không phải tệp Java độc lập; `Session`, `Result` và các hàm tương ứng được định nghĩa bởi ứng dụng. Mỗi hàm cleanup cần trả `Publisher<?>` thực sự thực thi công việc dọn dẹp khi được subscribe.

Các đặc tính quan trọng:

- Nhánh **complete**: resource closure hoàn tất thành công → Reactor subscribe publisher cleanup của `asyncComplete`.
- Nhánh **error**: resource closure lỗi → Reactor gọi `asyncError` với cả resource và exception, để rollback/giải phóng theo ngữ nghĩa lỗi.
- Nhánh **cancel**: downstream hủy → Reactor chạy publisher cleanup của `asyncCancel` khi resource đã được cấp. Nếu hủy trước lúc resource được cấp, subscription cấp resource cũng cần được hủy đúng cách.
- **`Mono.usingWhen` hoãn phát tín hiệu kết quả của `Mono` cho đến khi cleanup phù hợp hoàn tất.** Nếu cleanup thất bại, kết quả cuối có thể trở thành `onError` thay vì giá trị ban đầu.
- **`Flux.usingWhen` có thể chuyển nhiều `onNext` trước khi cleanup hoàn tất, nhưng trì hoãn terminal signal** cho đến khi cleanup xong. Nếu cleanup lỗi, nó có thể thay đổi kết quả terminal, nhưng không “thu hồi” được những phần tử đã được gửi tới client.
- Khi cấp resource thất bại hoặc hoàn tất rỗng **trước khi có resource**, không có tài nguyên để cleanup; main publisher được xử lý theo tín hiệu tương ứng.

**Lưu ý nghiệp vụ về giao dịch:** với một transaction, “complete” có thể có nghĩa **commit** chứ không chỉ close; “error/cancel” có thể yêu cầu rollback. Hãy dựa vào hợp đồng driver và transaction manager thật. Không gọi close và rollback nhiều lần ở các hook chồng nhau nếu không biết tính idempotent. Spring reactive transaction có cơ chế riêng; không tự mở transaction thủ công khi framework đã quản lý.

## 8. `Flux.create`, callback SDK và xử lý hủy

API listener/callback từ bên ngoài thường giữ một registration hoặc handle cho tới khi `unregister` được gọi. Khi chuyển callback sang `Flux` bằng `Flux.create`, nên quản lý **hai chiều**: SDK gửi dữ liệu về `sink.next`, và downstream hủy thì gửi lệnh dừng về SDK.

~~~java
// Ví dụ minh họa, không biên dịch độc lập vì SensorSdk
// và Registration phụ thuộc SDK bên ngoài.
Flux<String> updates = Flux.<String>create(sink -> {
    Registration registration = sdk.register(
        value -> sink.next(value),
        error -> sink.error(error),
        () -> sink.complete()
    );

    sink.onCancel(registration::cancel);
    sink.onDispose(registration::unregister);
});
~~~

Trong đó:

- `sink.onCancel` chỉ kích hoạt khi **subscription bị cancel**; dùng nó để ra lệnh SDK ngừng việc dành cho subscription đó nếu API hỗ trợ.
- `sink.onDispose` chạy khi **complete, error hoặc cancel**, nên phù hợp cho việc gỡ callback/listener.
- Với cancel, `onCancel` chạy **trước** `onDispose`.
- Hai hook này không có nghĩa `sink.next` chấp nhận `null` hoặc callback sau terminal; adapter cần bảo vệ các tình huống đó.
- Nếu API `register` có thể gọi callback đồng bộ hoặc throw trước khi trả handle, phải xử lý trường hợp initialization chưa hoàn tất/race; hook cleanup đăng ký muộn có thể được thực thi ngay khi sink đã disposed.

Nên dùng một registration **riêng cho từng subscription**, trừ khi cố ý triển khai nguồn hot được chia sẻ với quản lý vòng đời độc lập. Nếu hai HTTP client dùng cùng một handle mà một client hủy và đóng toàn bộ nguồn, client còn lại có thể bị ảnh hưởng.

Với API thật, cần kết hợp cancellation với **backpressure**, không để callback phát quá nhanh tích lũy bộ đệm vô hạn. `Flux.create` có `FluxSink.OverflowStrategy`, nhưng chọn `BUFFER`, `DROP`, `LATEST` hoặc `ERROR` phải theo khả năng mất dữ liệu của nghiệp vụ. Dọn listener đúng không tự giải quyết vấn đề quá tải.

## 9. Hủy đăng ký trong Spring WebFlux

Trong Spring WebFlux sử dụng Reactor Netty, nhiều request được phục vụ trên nhóm **event-loop thread** dùng chung. Một controller thường trả thẳng `Mono` hoặc `Flux` để framework nắm subscription và điều khiển vòng đời khi response đang được gửi.

Ví dụ một endpoint SSE **phụ thuộc vào SDK thực tế**:

~~~java
// Đoạn controller minh họa trong dự án Spring Boot WebFlux;
// sensorService.stream() trả Flux<Event> đã quản lý listener.
@GetMapping(value = "/sensors", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<Event> events() {
    return sensorService.stream()
        .doFinally(signal -> metrics.record(signal));
}
~~~

Đây không phải lớp Java độc lập vì `sensorService`, `metrics`, `Event` và annotations thuộc dự án Spring. Mục tiêu minh họa là **trả publisher** cho framework và gắn metric theo vòng đời. `sensorService.stream()` phải tự quản lý tài nguyên của nó, ví dụ bằng `usingWhen`, `using` hoặc callback cleanup.

Khi trình duyệt đóng SSE, server **có thể** phát hiện kết nối bị đóng và hủy subscription, dẫn đến cleanup. Nhưng thời điểm phát hiện tùy hệ điều hành, mạng, container và thời điểm server thử gửi dữ liệu; đừng hứa cleanup xảy ra ngay đúng mili-giây người dùng đóng tab.

Tránh hai anti-pattern:

~~~java
// Sai: tách tác vụ khỏi vòng đời HTTP request:
Flux<Event> events() {
    sensorService.stream().subscribe(event -> save(event));
    return Flux.empty();
}

// Sai: blocking call ngay trên event-loop vì tưởng dùng Mono/Flux là đủ:
Mono<Result> result = Mono.just(blockingClient.fetch());
~~~

Hai đoạn chỉ minh họa lỗi thiết kế, không phải code độc lập. Với API blocking bắt buộc phải dùng, cân nhắc `Mono.fromCallable(() -> blockingClient.fetch()).subscribeOn(Schedulers.boundedElastic())` và kiểm soát concurrency, thay vì chặn event-loop. Nhưng **cleanup** của resource vẫn phải được quản lý đúng, không tự có chỉ vì dùng scheduler.

Nếu một tác vụ nghiệp vụ **bắt buộc tiếp tục dù client mất kết nối** (ví dụ thanh toán, ghi nhận giao dịch), không thể dựa vào vòng đời của một HTTP subscription để bảo đảm hoàn thành. Cần thiết kế transaction, outbox/queue và idempotency phù hợp. Cancellation của response không nên vô tình hủy một tác vụ nền quan trọng được quản lý độc lập.

## 10. Ranh giới giữa cleanup và xử lý lỗi

Cleanup cũng có thể **thất bại**: đóng file thất bại, rollback gặp lỗi, kết nối database mất hoặc SDK không cho gỡ listener. Tránh hai suy luận sai: “pipeline đã complete nên cleanup chắc chắn thành công” và “cleanup thất bại nhưng vẫn luôn có thể đổi HTTP response”.

Với `using(..., eager=true)`, exception từ cleanup có thể thay thế terminal trước khi downstream nhận terminal đó. Với `usingWhen`, publisher cleanup thất bại có thể làm downstream nhận error tương ứng; trong `Mono.usingWhen`, giá trị còn đang chờ cleanup có thể bị bỏ đi nếu cleanup lỗi. Với `Flux.usingWhen`, các phần tử đã gửi trước cleanup **không thể rút lại**.

`doFinally` lại chủ yếu dùng cho side effect **sau khi terminal/cancel đã được lan truyền**. Nếu logging/metric trong hook ném exception, đừng kỳ vọng nó sẽ thay đổi một HTTP status đã trả. Hãy thiết kế cleanup có xử lý lỗi và ghi nhận riêng, hạn chế ném exception từ các hook side effect không thể recovery đáng tin cậy.

**Nguyên tắc thực tế:** nếu resource là điều kiện quan trọng để khẳng định thành công (commit transaction, gửi acknowledgment cuối cùng), hãy đặt cleanup/commit vào **luồng reactive chính** bằng `usingWhen` hoặc toán tử ghép appropriate để kết quả chỉ được công nhận sau khi thao tác đó hoàn tất, thay vì chỉ dùng `doFinally` làm “fire-and-forget”.

Ngoài ra, `cancel` là tình huống downstream không còn lắng nghe; không phải lúc nào còn subscriber để nhận một lỗi cleanup. Vì vậy cần log/metric lỗi dọn tài nguyên và có cơ chế thu hồi/reconciliation ở tầng resource nếu nghiệp vụ cần.

## 11. So sánh nhanh các cách làm

| Nhu cầu | Cách nên chọn | Vì sao |
| --- | --- | --- |
| Đo thời gian, đếm completion/error/cancel | `doFinally` | Một hook quan sát cả ba nhánh |
| Log lỗi nhưng giữ nguyên lỗi | `doOnError` | Không thay tín hiệu terminal |
| Gửi thông báo riêng khi subscriber hủy | `doOnCancel` | Chạy ở nhánh cancellation |
| Cấp một resource đồng bộ cho mỗi subscriber, sau đó đóng | `Flux.using` / `Mono.using` | Resource có scope rõ từ cấp tới cleanup |
| Cấp resource và commit/rollback/close bất đồng bộ | `Flux.usingWhen` / `Mono.usingWhen` | Cleanup là một publisher có lifecycle |
| Tích hợp API listener/callback nhiều sự kiện | `Flux.create` với `sink.onCancel` và `sink.onDispose` | Vừa chuyển event, vừa truyền hủy và gỡ listener |
| Chỉ cần log sau complete/error, không có cancel | `doAfterTerminate` | Không thay thế cleanup trên cancel |
| Xử lý cancellation của SSE/HTTP | Trả publisher cho WebFlux + nguồn có cleanup | Framework kiểm soát subscription, nguồn giải phóng handle |
| Quản lý tài nguyên dùng chung nhiều subscriber | Shared lifecycle/ref counting do ứng dụng định nghĩa | Hủy một subscriber không được đóng resource chung tùy tiện |

Trường hợp chỉ có một callback `onComplete` không đủ để quản lý tất cả; trường hợp chỉ có một `onCancel` cũng không đủ nếu nguồn có thể hoàn tất hoặc lỗi.

## 12. Lỗi phổ biến và cách phòng tránh

1. **Chỉ dọn khi complete:** bỏ sót error/cancel, dễ leak listener, socket hoặc reader. Dùng `doFinally`, `using` hay `usingWhen` theo nhu cầu.
2. **Dùng `doOnTerminate` làm finally:** toán tử này không xử lý nhánh cancel thuần túy. Dùng `doFinally` khi cần bao phủ cả ba nhánh.
3. **Chỉ dùng `FluxSink.onCancel` để gỡ listener:** complete/error không gọi hook cancel; nên gỡ listener trong `onDispose`.
4. **Đóng resource khi xây dựng publisher:** resource có thể bị đóng trước cả khi subscription thực sự đọc xong. Cấp và đóng trong cùng reactive scope.
5. **`try-with-resources` bên ngoài một publisher lazy:** khối `try` có thể kết thúc trước khi subscriber dùng resource. Sử dụng `using`/ `usingWhen` thay vì trả một Flux phụ thuộc resource đã đóng.
6. **Gọi `block()` để chờ cleanup async trên event-loop:** dễ làm nghẽn request khác. Dùng `usingWhen` với publisher cleanup.
7. **Bỏ qua lỗi cleanup:** kết quả được báo thành công dù transaction chưa commit hoặc resource chưa đóng. Xác định eager/delayed semantics và cách báo lỗi.
8. **Đóng một tài nguyên dùng chung khi một người hủy:** có thể phá stream của subscriber khác. Phân biệt resource riêng theo subscription với singleton/pool.
9. **Không quản lý race giữa cancel và callback:** dọn nhiều lần hoặc callback muộn truy cập tài nguyên đã đóng. Cleanup idempotent và thread-safe, kiểm tra hợp đồng SDK.
10. **Xem cancel như HTTP error 500:** cancel không mặc nhiên là `onError`; ghi metrics phân biệt.
11. **Tự `subscribe()` trong controller:** tách vòng đời xử lý khỏi HTTP, client hủy không còn điều khiển được đúng upstream. Trả publisher cho WebFlux.
12. **Tin rằng `dispose()` luôn chờ tác vụ ngoài ngừng hoàn toàn:** cancel là yêu cầu; SDK blocking hoặc hệ thống bên ngoài có thể cần cơ chế stop, timeout và xác nhận riêng.
13. **Dựa vào thứ tự toàn cục của nhiều hook:** `doFinally` chạy sau terminal downstream và nhiều hook có thể thực thi thứ tự ngược. Test với luồng đồng bộ/bất đồng bộ thực tế.
14. **Không đo resource leak:** không theo dõi active listener/connection/handle nên leak chỉ lộ ra khi tải cao. Dùng metric counter tăng khi acquire và giảm khi cleanup, kiểm chứng cân bằng trên cả ba nhánh.

## 13. Checklist kiểm thử resource lifecycle

Đối với mỗi publisher gắn tài nguyên, nên kiểm thử:

- **Hoàn tất rỗng (`Mono.empty`/`Flux.empty`)**: resource được đóng dù không có giá trị `onNext`.
- **Hoàn tất có nhiều phần tử**: phát đúng dữ liệu, close đúng một lần, callback thấy `ON_COMPLETE`.
- **Báo lỗi ngay sau subscribe**: vẫn dọn đúng resource, downstream nhận lỗi theo hợp đồng.
- **Báo lỗi sau vài phần tử**: resource được đóng, không thêm `onNext` sau terminal.
- **Hủy ngay khi subscribe**: subscription bị dừng, resource đã cấp được dọn, không giả lập onComplete.
- **`take(n)` hủy upstream**: upstream cleanup nhìn thấy cancel, downstream có thể complete bình thường.
- **HTTP client mất kết nối giữa SSE**: sau khi server phát hiện, active registration trở về ngưỡng cân bằng.
- **Cleanup tự ném exception**: xác định liệu lỗi cleanup thay thế terminal hay được báo dropped/log tùy operator.
- **Hai subscriber đồng thời**: không đóng nhầm tài nguyên dùng chung; resource mỗi subscription có owner rõ ràng.
- **Cancel và error xảy ra đồng thời**: resource release idempotent, không xuất hiện callback trễ truy cập handle đã giải phóng.
- **Cleanup async chậm**: kiểm chứng terminal của `usingWhen` chỉ được xem là hoàn tất theo đúng semantics đã chọn.
- **Nguồn chạy vô hạn (`Flux.never`, SSE)**: có thể kích hoạt cancel chủ động và xác nhận cleanup không cần đợi complete.

Với `reactor-test` có thể sử dụng `StepVerifier` để kiểm tra `expectNext`, `verifyComplete`, `expectError` hoặc `thenCancel`. Để xác nhận cleanup, có thể dùng `AtomicBoolean`/counter hoặc await condition phù hợp thay vì chỉ dựa vào timing ngẫu nhiên.

Ví dụ kiểm chứng ý tưởng (mã test minh họa; cần `reactor-test` ở test scope):

~~~java
AtomicBoolean closed = new AtomicBoolean();
Flux<Integer> stream = Flux.using(
    () -> "resource",
    ignored -> Flux.just(1, 2),
    ignored -> closed.set(true),
    true
);

StepVerifier.create(stream)
    .expectNext(1, 2)
    .verifyComplete();

assertTrue(closed.get()); // JUnit assertion: cleanup eager đã chạy.
~~~

Ở đây `assertTrue` thuộc JUnit và các import cần có trong dự án test. Với `doFinally`, do callback có thể chạy sau terminal, cần đồng bộ hợp lý trước khi kiểm tra side effect. Không biến ví dụ test này thành một `main` rồi gọi `assertTrue` khi chưa có JUnit.

**Ghi nhớ:** Muốn quản lý resource đáng tin cậy, phải tính đủ **complete, error và cancel**. `doFinally` thích hợp để quan sát cả ba; `using` quản lý tài nguyên với cleanup đồng bộ; `usingWhen` quản lý cleanup bất đồng bộ; `FluxSink.onCancel` và `onDispose` cần thiết khi nối API callback. Trong Spring WebFlux, **trả publisher cho framework**, giữ cleanup gắn đúng subscription, và không coi việc kết thúc HTTP là bảo đảm rằng mọi tác vụ/resource ngoài đã dừng tức thì.

**Nguồn chính thức:** [Reactor Reference — Handling Errors: Using Resources and the Finally Block](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html); [Reactor Flux Javadoc — using, usingWhen, doFinally](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html); [Reactor Mono Javadoc — usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).