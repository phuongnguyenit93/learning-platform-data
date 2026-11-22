# Tích hợp API callback qua `Flux.create` và xử lý yêu cầu hủy

## 1. Bài toán: callback truyền thống gặp lập trình reactive

Trong Spring WebFlux, nhiều thành phần xử lý dữ liệu dưới dạng `Mono<T>` hoặc `Flux<T>`. Tuy nhiên, một SDK, thư viện mạng, thiết bị IoT hoặc API Java đời cũ có thể dùng **callback/listener**:

- `onData(value)` được gọi mỗi lần nguồn có dữ liệu.
- `onComplete()` được gọi khi công việc kết thúc thành công.
- `onError(error)` được gọi khi công việc thất bại.
- `register(listener)`, `start(listener)` hoặc `subscribe(listener)` trả về một handle để ngừng công việc và gỡ listener.

Mục tiêu là biến các callback phát **0 đến nhiều sự kiện** thành một `Flux<T>`, đồng thời chuyển **tín hiệu hủy từ downstream** về SDK. Nếu thiếu bước thứ hai, khi người dùng đóng trang hoặc HTTP client ngắt kết nối, SDK có thể tiếp tục làm việc, giữ socket/timer và giữ listener không cần thiết.

`Flux.create` chính là công cụ của Project Reactor để tạo `Flux` bằng các tín hiệu chủ động, đặc biệt hữu ích khi tích hợp API callback bất đồng bộ có thể phát nhiều sự kiện, kể cả từ nhiều thread. Nhưng `create` **không tự động tạo thread, không biến code blocking thành non-blocking, và không tự biết cách hủy tài nguyên của SDK**.

## 2. Ánh xạ callback sang tín hiệu Flux

Giả sử một API bên ngoài định nghĩa:

~~~java
// Chỉ minh họa hợp đồng SDK, chưa phải chương trình độc lập.
interface EventListener {
    void onData(String value);
    void onComplete();
    void onError(Throwable error);
}
~~~

Bên trong `Flux.create(sink -> ...)`, Reactor cung cấp một `FluxSink<T>`. Ta ánh xạ:

| Sự kiện | Hành động trong bridge | Tín hiệu nhìn từ subscriber |
| --- | --- | --- |
| Callback nhận một giá trị hợp lệ | `sink.next(value)` | `onNext(value)` |
| SDK kết thúc thành công | `sink.complete()` | `onComplete()` |
| SDK báo lỗi | `sink.error(error)` | `onError(error)` |
| Subscriber yêu cầu hủy | `sink.onCancel(...)` | Chuyển yêu cầu dừng về nguồn |
| Bất kỳ kết thúc/hủy nào | `sink.onDispose(...)` | Thu hồi listener và tài nguyên |

Một `Flux` có thể phát **0, 1 hoặc N lần `onNext`** rồi kết thúc bằng **một trong hai** tín hiệu terminal: `onComplete` hoặc `onError`. Sau terminal không phát tiếp phần tử; `null` không được phép làm giá trị `onNext`. Nếu nguồn không có phần tử nào và kết thúc thành công, `sink.complete()` là hợp lệ.

Mẫu bridge đơn giản:

~~~java
// Chỉ là cấu trúc minh họa; SDK, Handle và các callback phải được triển khai.
Flux<String> stream = Flux.create(sink -> {
    Handle handle = sdk.start(
        value -> sink.next(value),
        error -> sink.error(error),
        () -> sink.complete()
    );
    sink.onCancel(handle::cancel);
    sink.onDispose(handle::close);
});
~~~

Khác với một callback chỉ trả về **một kết quả**, có thể dùng `Mono.create` và `MonoSink`. `Flux.create` dành cho trường hợp có thể nhận **nhiều** giá trị. `Flux.push` phù hợp hơn nếu tất cả tín hiệu có **một producer thread**; `Flux.create` hỗ trợ nguồn nhiều thread. `Flux.generate` có mô hình phát đồng bộ theo từng lượt và chỉ cho tối đa một `next` trong mỗi lần gọi hàm generator, vì vậy không tương đương với bridge listener bất đồng bộ.

### Đăng ký xảy ra khi nào?

`Flux.create` tạo ra một publisher mà lambda emitter thường được thực thi **cho mỗi lần subscribe**. Vì vậy, việc gọi `Flux<String> flux = adapt(api)` chỉ xây dựng nguồn; một `flux.subscribe(...)` mới bắt đầu đăng ký listener tương ứng. Hai subscriber mặc định sẽ có **hai lần đăng ký** nếu lambda gọi `api.start(...)` mỗi lần.

Điều này quan trọng khi tích hợp với HTTP: vòng đời listener phải gắn với **từng subscription**, không dùng nhầm một biến handle toàn cục khiến subscriber A hủy công việc của B. Nếu cần một nguồn sự kiện **hot** dùng chung cho nhiều client, hãy thiết kế cơ chế chia sẻ và đếm người đăng ký riêng; không giả định `Flux.create` tự chia sẻ một listener duy nhất.

## 3. Phân biệt `onCancel` và `onDispose`

Hai hook này giải quyết các phần khác nhau trong vòng đời:

| Kết thúc subscription theo đường nào? | `sink.onCancel(...)` | `sink.onDispose(...)` |
| --- | --- | --- |
| Downstream gọi `cancel()` | Có | Có |
| `Disposable` do `subscribe()` trả về được `dispose()` | Có | Có |
| Toán tử `take(n)` hủy upstream sau khi nhận đủ | Có ở upstream bị hủy | Có |
| SDK gọi `sink.complete()` | Không | Có |
| SDK gọi `sink.error(e)` | Không | Có |

Khi **hủy**, `onCancel` chạy **trước** `onDispose`. Còn khi hoàn tất/lỗi tự nhiên, **chỉ** `onDispose` được kích hoạt. Vì vậy nên tách trách nhiệm:

- **`onCancel`**: gửi lệnh *stop/cancel* đến hoạt động đang chạy ở SDK nếu handle đó hỗ trợ hủy. Đây là tín hiệu riêng cho tình huống downstream không còn cần dữ liệu.
- **`onDispose`**: *unregister/close/detach* listener và giải phóng những resource mà một subscription sở hữu, bất kể cancel, error hay complete.
- **`sink.error` / `sink.complete`**: biểu diễn cách nguồn kết thúc; không gọi `onCancel` bằng tay để giả lập lỗi hoặc kết thúc thông thường.

`onCancel` và `onDispose` mỗi loại chỉ nhận một callback chính cho từng `FluxSink`. Nếu phải thu hồi nhiều thứ, hãy gộp những thao tác liên quan vào callback quản lý một cách nhất quán. Cleanup nên **idempotent**: nếu có cạnh tranh giữa các thread hoặc SDK báo terminal đúng lúc client hủy, việc gọi dọn dẹp không làm lỗi hay đóng nhầm tài nguyên.

Một khác biệt dễ nhầm: `Disposable.dispose()` của đối tượng do `subscribe()` trả về thường **gửi cancel**. Còn `sink.onDispose` là **hook cleanup** có thể chạy sau terminal tự nhiên, ngay cả khi không có cancel.

## 4. Ví dụ Java 17+ chạy được: callback, hủy và dọn listener

Ví dụ độc lập dưới đây chỉ cần **Reactor Core** và Maven; nó mô phỏng một SDK có khả năng đăng ký nhiều listener. `main` phát sự kiện theo thứ tự cố định để kiểm tra chính xác output. Mỗi lần đăng ký trả về một `Registration`, trong đó `cancel()` dừng công việc của subscription đó và `close()` tháo listener ra khỏi danh sách. `AtomicBoolean` giúp hai thao tác không bị thực hiện lặp lại; `CopyOnWriteArrayList` cho phép thay đổi danh sách trong khi callback đang được duyệt.

Tạo cấu trúc:

~~~text
callback-bridge/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── CallbackBridgeDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>callback-bridge</artifactId>
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

File `src/main/java/CallbackBridgeDemo.java`:

~~~java
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public class CallbackBridgeDemo {
    interface Listener {
        void onData(String value);
        void onCompleted();
        void onFailure(Throwable error);
    }

    static final class CallbackApi {
        private final CopyOnWriteArrayList<Registration> registrations =
                new CopyOnWriteArrayList<>();

        Registration start(Listener listener) {
            Registration registration = new Registration(this, listener);
            registrations.add(registration);
            return registration;
        }

        void emit(String value) {
            for (Registration registration : registrations) {
                if (!registration.cancelled.get()) {
                    registration.listener.onData(value);
                }
            }
        }

        void finish() {
            for (Registration registration : registrations) {
                if (!registration.cancelled.get()) {
                    registration.listener.onCompleted();
                }
            }
        }

        int activeCount() {
            return registrations.size();
        }

        static final class Registration {
            private final CallbackApi api;
            private final Listener listener;
            private final AtomicBoolean cancelled = new AtomicBoolean();
            private final AtomicBoolean closed = new AtomicBoolean();

            Registration(CallbackApi api, Listener listener) {
                this.api = api;
                this.listener = listener;
            }

            void cancel() {
                if (cancelled.compareAndSet(false, true)) {
                    System.out.println("API: cancel work");
                }
            }

            void close() {
                if (closed.compareAndSet(false, true)) {
                    api.registrations.remove(this);
                    System.out.println("API: unregister listener");
                }
            }
        }
    }

    static Flux<String> adapt(CallbackApi api) {
        return Flux.<String>create(sink -> {
            Listener listener = new Listener() {
                @Override
                public void onData(String value) {
                    if (!sink.isCancelled()) {
                        sink.next(value);
                    }
                }

                @Override
                public void onCompleted() {
                    sink.complete();
                }

                @Override
                public void onFailure(Throwable error) {
                    sink.error(error);
                }
            };

            CallbackApi.Registration registration = api.start(listener);

            // Chỉ chạy khi downstream hủy subscription.
            sink.onCancel(registration::cancel);

            // Chạy sau complete, error hoặc cancel.
            sink.onDispose(registration::close);
        }, FluxSink.OverflowStrategy.ERROR);
    }

    public static void main(String[] args) {
        CallbackApi api = new CallbackApi();
        Flux<String> events = adapt(api);

        Disposable first = events.subscribe(
                item -> System.out.println("first: " + item),
                error -> System.out.println("first error: " + error.getMessage()),
                () -> System.out.println("first complete")
        );
        api.emit("A");
        api.emit("B");
        first.dispose();       // Hủy subscription thứ nhất.
        api.emit("C");         // Không còn listener thứ nhất.
        System.out.println("active: " + api.activeCount());

        events.subscribe(
                item -> System.out.println("second: " + item),
                error -> System.out.println("second error: " + error.getMessage()),
                () -> System.out.println("second complete")
        );
        api.emit("D");
        api.finish();          // API hoàn tất tự nhiên.
        System.out.println("active: " + api.activeCount());
    }
}
~~~

Trong thư mục `callback-bridge`, với JDK 17+ và Maven chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CallbackBridgeDemo
~~~

**Output chương trình** (bỏ qua thông báo thêm của Maven nếu môi trường có):

~~~text
first: A
first: B
API: cancel work
API: unregister listener
active: 0
second: D
second complete
API: unregister listener
active: 0
~~~

Diễn giải:

1. `subscribe()` thứ nhất đăng ký listener. Hai callback `api.emit("A")` và `api.emit("B")` được chuyển thành `sink.next` và subscriber nhận `first: A`, `first: B`.
2. `first.dispose()` tạo **cancel từ downstream**. Reactor gọi `onCancel` để `registration.cancel()` báo dừng, rồi gọi `onDispose` để `registration.close()` tháo listener. Bởi vậy sự kiện `C` không còn được nhận.
3. Lần subscribe thứ hai tạo một `Registration` độc lập, sau đó nhận `D`. Khi `api.finish()` gọi callback `onCompleted()`, adapter gọi `sink.complete()`; subscriber nhận `second complete` và `onDispose` tháo listener.
4. Lần thứ hai không in `API: cancel work` vì nguồn **hoàn tất tự nhiên**, không bị downstream hủy. Hai dòng `active: 0` chứng minh danh sách listener được dọn sau mỗi nhánh.

Trong ví dụ, `CallbackApi` là **mô phỏng đơn giản**: `main` gọi callback cùng thread để có output xác định. Trong thực tế, SDK có thể gọi callback từ worker thread, thread pool hoặc thread mạng. `Flux.create` được thiết kế cho cả trường hợp nhiều producer thread, nhưng adapter và handle của SDK vẫn cần thread-safety.

## 5. Dòng chảy khi subscriber hủy

~~~text
downstream subscribe()
       |
       v
Flux.create(...) chạy cho subscription này
       |
       v
api.start(listener) -> Registration
       |
       +-- SDK data callback -----> sink.next(value) -----> onNext(value)
       |
       +-- SDK finish callback ---> sink.complete() -------> onComplete
       |                                |
       |                                +--> onDispose: unregister
       |
       +-- SDK error callback ----> sink.error(error) ----> onError
       |                                |
       |                                +--> onDispose: unregister
       |
       +-- downstream cancel()
              |
              +--> onCancel: cancel upstream work
              |
              +--> onDispose: unregister listener
~~~

Những tình huống kích hoạt cancel thường gặp: gọi `Disposable.dispose()`, subscriber dùng `Subscription.cancel()`, một toán tử như `take(3)` đã lấy đủ phần tử rồi hủy upstream, hoặc HTTP client bỏ stream khiến server hủy subscription khi phát hiện disconnect.

Cần nhớ rằng **`sink.isCancelled()` không ngừng SDK**. Nó chỉ trả về trạng thái mà sink thấy lúc đọc; cancel có thể đua với callback đến muộn. Adapter phải gọi cơ chế `cancel/stop/unregister` thực sự ở API ngoài, đồng thời tránh phát tiếp sau terminal. Khi SDK không có cách hủy tác vụ, tối thiểu cần gỡ callback và ngăn giữ tài nguyên vô hạn; có thể phải chấp nhận tác vụ nền hoàn thành dù client không còn nghe.

Các lưu ý triển khai thực tế:

- Đăng ký listener và hook cleanup **theo từng subscription**, giữ handle cục bộ trong lambda.
- Dọn tài nguyên khi hoàn tất/lỗi **và** khi hủy; riêng `onCancel` không bao phủ cả ba đường.
- Viết cleanup idempotent; kiểm soát race giữa việc gỡ listener, SDK gọi callback cuối cùng và downstream cancel.
- SDK có thể gọi callback ngay trong lúc `start/register`. Khi gắn `onDispose` sau khi lấy được handle, Reactor có thể gọi hook ngay nếu sink đã disposed. Cần xác nhận hợp đồng SDK để không rò rỉ tài nguyên trong trường hợp đăng ký đồng bộ/throw giữa chừng.
- Nếu callback có thể gửi lại terminal hoặc gửi `onNext` sau terminal, cần chặn ở biên SDK và không giả định mọi sự kiện lỗi thời đều được xử lý theo ý muốn.
- Không đóng kết nối hoặc dừng tài nguyên **dùng chung toàn ứng dụng** chỉ vì một subscriber hủy; phân biệt nguồn riêng từng subscription với nguồn hot chia sẻ.

## 6. Backpressure: callback push nhanh hơn khả năng tiêu thụ

Reactive Streams cho phép downstream yêu cầu số lượng phần tử qua `request(n)`. Nhưng SDK callback kiểu push có thể phát theo tốc độ riêng. `Flux.create` cho phép chọn `FluxSink.OverflowStrategy` để xử lý tín hiệu vượt nhu cầu:

| Chiến lược | Hành vi | Rủi ro/lựa chọn |
| --- | --- | --- |
| `BUFFER` (mặc định) | Tích lũy các tín hiệu khi chưa đủ demand | **Đệm không giới hạn**; nguồn nhanh vô hạn có thể làm hết RAM |
| `DROP` | Bỏ giá trị mới khi downstream không sẵn sàng | Mất một phần sự kiện; chỉ dùng nếu nghiệp vụ chấp nhận |
| `LATEST` | Giữ giá trị mới nhất để giao khi có demand | Phù hợp cập nhật trạng thái có thể bỏ bản trung gian |
| `ERROR` | Phát lỗi khi downstream không theo kịp | Hợp khi không thể mất dữ liệu và phải fail nhanh |
| `IGNORE` | Bỏ qua demand ở sink, tiếp tục đẩy | Downstream có thể lỗi do queue đầy, cần cân nhắc kỹ |

Trong ví dụ dùng `ERROR` để tránh việc giữ mọi giá trị trong bộ nhớ. `subscribe(onNext, onError, onComplete)` mặc định yêu cầu lượng dữ liệu không giới hạn, nên ví dụ đơn giản không gây overflow. Với subscriber giới hạn demand, `ERROR` có thể dẫn đến `onError` và kích hoạt cleanup.

**Tốt nhất nếu SDK hỗ trợ điều tiết tại nguồn:** dùng `sink.onRequest(n -> api.requestMore(n))` để chủ động yêu cầu thêm dữ liệu, hoặc cơ chế pause/resume của SDK. Đây là **minh họa** vì `api.requestMore` không phải method có sẵn trong Reactor. `requestedFromDownstream()` cho biết lượng demand còn lại tại thời điểm đọc; không coi việc đọc số này là khóa đồng bộ giữa nhiều thread. Với nguồn không thể giảm tốc độ, cần policy mất dữ liệu, bounded queue hoặc báo lỗi rõ ràng, tùy loại sự kiện.

**Đừng hiểu lầm:** `Flux.create` có backpressure strategy không có nghĩa bản thân SDK sẽ ngừng sinh dữ liệu. Muốn tiết kiệm công việc upstream phải kết nối demand/cancel với cơ chế tương ứng của SDK.

## 7. Đưa Flux callback vào Spring WebFlux

Với streaming HTTP, có thể trả `Flux` trực tiếp từ controller:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

@RestController
class SensorController {
    private final SensorSdk sdk;

    SensorController(SensorSdk sdk) {
        this.sdk = sdk;
    }

    @GetMapping(value = "/sensor/updates",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<String> updates() {
        return Flux.<String>create(sink -> {
            SensorHandle handle = sdk.subscribe(
                value -> sink.next(value),
                error -> sink.error(error),
                () -> sink.complete()
            );
            sink.onCancel(handle::cancel);
            sink.onDispose(handle::close);
        }, FluxSink.OverflowStrategy.LATEST);
    }
}
~~~

**Đây là mẫu minh họa đặt trong ứng dụng Spring Boot WebFlux có `SensorSdk` và `SensorHandle` do SDK cung cấp**, không biên dịch độc lập như ví dụ Maven ở trên. Các tên API callback có thể khác trong thư viện thực tế. Chỉ chọn `LATEST` khi stream cảm biến có thể bỏ qua cập nhật cũ, không dùng nếu mỗi event là giao dịch cần nhận đủ.

Vì controller **trả publisher** cho WebFlux, framework sẽ quản lý subscription theo việc viết HTTP response. Khi client đóng SSE và phía server nhận ra kết nối mất, cancel thường lan về source rồi kích hoạt hook; thời điểm phát hiện disconnect còn phụ thuộc môi trường, mạng và lần ghi dữ liệu. Kiểm chứng hành vi này bằng log số listener còn hoạt động hoặc một phép thử đóng client giữa chừng.

Không gọi `subscribe()` thủ công bên trong controller để khởi chạy adapter rồi trả một publisher khác: cách đó tách công việc nguồn khỏi vòng đời HTTP và có thể khiến cancel của client không ngừng SDK.

## 8. Những sai lầm phổ biến

1. **Không đăng ký cleanup**: SDK giữ listener dù client rời đi. Sửa bằng `onDispose`, và `onCancel` để ngừng công việc nếu có thể.
2. **Chỉ dùng `onCancel`**: nhánh `complete` và `error` không chạy hook đó, dễ rò resource. Gắn `onDispose` cho cleanup chung.
3. **Dùng `sink.error` cho yêu cầu hủy**: cancel là tín hiệu downstream, còn error là kết thúc thất bại từ nguồn. Giữ hai chiều riêng biệt.
4. **Dùng chung một handle cho mọi subscriber**: hủy A làm mất dữ liệu của B. Tạo registration trên mỗi subscription hoặc thiết kế chia sẻ có quản lý.
5. **Tin `Flux.create` tự làm SDK bất đồng bộ**: nếu lambda gọi blocking API, thread vẫn bị chặn. Không chờ I/O hoặc chạy vòng lặp vô hạn trong emitter trên event loop.
6. **Phát `null` hoặc phát sau terminal**: Reactive Streams không chấp nhận `null` và không có phần tử sau `onComplete/onError`. Chuẩn hóa callback tại adapter.
7. **Giữ `BUFFER` cho callback tốc độ cao, vô hạn**: nguy cơ OutOfMemoryError. Chọn strategy rõ ràng và điều tiết nguồn khi có thể.
8. **Chỉ kiểm tra `isCancelled`**: kiểm tra có race và không tự đóng socket. Cần thực thi hủy/gỡ đăng ký từ SDK.
9. **Không kiểm tra đường lỗi**: khi SDK thất bại, bridge cần `sink.error` để subscriber nhận lỗi và `onDispose` chạy cleanup.
10. **Tưởng mọi `Flux.create` là hot shared stream**: lambda thường chạy lại mỗi subscription. Quyết định rõ adapter tạo nguồn riêng hay chia sẻ thật.

## 9. Kịch bản QA nên thử trước khi dùng với SDK thật

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Nguồn hoàn tất mà chưa phát phần tử | `onComplete`; listener được gỡ, không chạy `onCancel` |
| Nguồn phát nhiều phần tử rồi hoàn tất | Từng `onNext` đúng thứ tự được SDK bảo đảm; cleanup một lần |
| Nguồn phát một vài phần tử rồi lỗi | `onError`; không có `onComplete` sau lỗi; cleanup một lần |
| Subscriber cancel ngay sau khi đăng ký | SDK nhận stop/cancel nếu hỗ trợ, listener được gỡ |
| `take(2)` nhận đủ hai phần tử | Upstream bị hủy, SDK dừng và cleanup, downstream kết thúc đúng hợp đồng |
| Cancel xảy ra cùng lúc với callback | Không rò listener, không lỗi do cleanup lặp, không phát sai hợp đồng |
| Hai subscriber cùng nghe | Hai registration phù hợp; hủy một không ảnh hưởng người còn lại |
| Callback nhanh hơn demand | Chính sách BUFFER/DROP/LATEST/ERROR đúng nghiệp vụ và đã kiểm tra bộ nhớ |
| Client SSE ngắt kết nối | Sau khi server phát hiện cancel, số handle/listener còn hoạt động giảm |

**Ghi nhớ:** Tích hợp API callback qua `Flux.create` có **hai chiều bắt buộc**: các sự kiện từ SDK đi vào `sink.next/error/complete`, và hủy từ subscriber đi ngược về SDK qua `onCancel`. Hook `onDispose` bảo đảm thu hồi listener/tài nguyên trên **cả ba** đường kết thúc: hoàn tất, lỗi và hủy. Chỉ khi quản lý đầy đủ vòng đời, bridge mới phù hợp với các luồng dữ liệu WebFlux có nhiều client và các kết nối bị ngắt giữa chừng.

**Tài liệu chính thức:** [Project Reactor – Programmatically Creating a Sequence](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html), [FluxSink API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/FluxSink.html), [FluxSink.OverflowStrategy](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/FluxSink.OverflowStrategy.html).