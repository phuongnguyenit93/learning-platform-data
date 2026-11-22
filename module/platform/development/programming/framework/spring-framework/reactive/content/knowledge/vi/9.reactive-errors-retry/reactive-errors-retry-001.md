# `onError` là tín hiệu kết thúc chuỗi trong Reactor và Spring WebFlux

## 1. Bản chất của tín hiệu `onError`

Project Reactor dùng `Mono<T>` (0..1 giá trị) và `Flux<T>` (0..N giá trị) để biểu diễn các publisher tuân theo **Reactive Streams**. Khi một subscriber đăng ký, nó được thông báo bằng `onSubscribe(Subscription)`, sau đó có thể nhận các phần tử bằng `onNext(T)`. Một luồng hữu hạn kết thúc theo **một trong hai cách**:

- `onComplete()`: kết thúc **thành công**.
- `onError(Throwable)`: kết thúc **thất bại**.

**`onError` là tín hiệu terminal**. Sau `onError`, **cùng subscription đó** không thể phát thêm `onNext`, không có `onComplete`, và cũng không có `onError` thứ hai. Lỗi không phải là một phần tử dữ liệu bình thường được đẩy qua `map` để có thể “xử lý rồi đi tiếp”.

Ví dụ các chuỗi tín hiệu:

~~~text
Thành công:
onSubscribe -> onNext(A) -> onNext(B) -> onComplete

Thất bại:
onSubscribe -> onNext(A) -> onNext(B) -> onError(ex)

Thành công nhưng không có phần tử:
onSubscribe -> onComplete

Lỗi trước khi có phần tử:
onSubscribe -> onError(ex)
~~~

Lưu ý: `onNext` không nhận `null`. Một `Mono.empty()` phát `onComplete` mà không có dữ liệu; đó là **thành công rỗng**, không phải lỗi. `Mono.error(ex)` phát lỗi, không có giá trị. Cả hai đều có thể chưa từng phát `onNext`, nhưng ý nghĩa nghiệp vụ rất khác nhau.

Hành động `Subscription.cancel()` từ downstream là một trường hợp **riêng**: nó yêu cầu upstream ngừng gửi dữ liệu. Cancel **không phải** là callback `onError` hoặc `onComplete` bắt buộc gửi cho subscriber. Một toán tử `take(2)` có thể gửi completion cho downstream sau hai phần tử đồng thời hủy upstream; vì vậy phải phân biệt **tín hiệu ở từng vị trí pipeline**.

## 2. Exception biến thành onError như thế nào?

Hãy xem một luồng số:

~~~java
// Ví dụ minh họa, cần Reactor Core và import Flux.
Flux<Integer> numbers = Flux.range(1, 5)
    .map(n -> {
        if (n == 3) {
            throw new IllegalStateException("bad 3");
        }
        return n * 10;
    });

numbers.subscribe(
    value -> System.out.println("next: " + value),
    error -> System.out.println("error: " + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Nguồn đồng bộ này in:

~~~text
next: 10
next: 20
error: bad 3
~~~

Khi hàm `map` gặp `3` và ném exception, Reactor chuyển nó thành `onError`. Pipeline dừng tại đó. Không có `next: 40`, `next: 50` hay `complete`. Một `Flux` chứa nhiều phần tử không có nghĩa nó luôn cố chạy hết các phần tử khi đã lỗi.

Bạn cũng có thể tạo publisher phát lỗi có chủ ý:

~~~java
Mono<String> invalid = Mono.error(
    new IllegalArgumentException("Invalid request")
);

Flux<Integer> unavailable = Flux.error(
    new IllegalStateException("Service unavailable")
);
~~~

Hai biểu thức này là **publisher**, chứ không ném exception ngay khi khai báo. Tín hiệu lỗi thường xuất hiện khi có subscription. Biến thể `Mono.error(() -> new IllegalStateException("failed"))` cho phép tạo exception mới theo mỗi subscription.

Một sai lầm thường gặp là đặt `try/catch` quanh lời khai báo `Flux` rồi tưởng sẽ bắt được mọi lỗi. Với publisher lazy, exception nảy sinh **khi thực thi operator sau subscription** được phát qua `onError` và cần xử lý trong pipeline hoặc error callback. `try/catch` Java vẫn hữu ích đối với các exception xảy ra **ngay trong lúc tạo biểu thức**, nhưng không thay thế cho reactive error handling.

## 3. Phân biệt onComplete, onError và cancel

| Trường hợp | Kết quả quan sát | Có thêm phần tử sau đó không? |
| --- | --- | --- |
| `Flux.just("A", "B")` | A, B, `onComplete` | Không, đã kết thúc thành công |
| `Flux.empty()` | `onComplete` | Không, thành công rỗng |
| `Flux.error(ex)` | `onError(ex)` | Không, kết thúc thất bại |
| `Flux.never()` | Có thể không phát gì và không kết thúc | Không thể suy ra nó đã hoàn tất |
| Downstream `cancel()` | Upstream nhận yêu cầu dừng | Không có terminal mới bắt buộc gửi downstream |
| `take(2)` trên Flux dài | Downstream có thể complete sau hai phần tử; upstream bị cancel | Tùy vị trí quan sát trong pipeline |

Với một subscription, thứ tự `onNext` và terminal phải tuân hợp đồng Reactive Streams. Khi lỗi xảy ra, Reactor thường hủy những phần công việc upstream đang còn hoạt động. Tuy nhiên, **lỗi trong Reactor không tự động đóng mọi tài nguyên tùy biến của SDK**; bridge callback, socket, listener hoặc transaction phải có logic cleanup gắn với vòng đời publisher.

Có thể quan sát nguyên nhân kết thúc bằng `doFinally(signalType -> ...)`, với các dạng `SignalType.ON_COMPLETE`, `ON_ERROR` và `CANCEL`. Vị trí gắn `doFinally` rất quan trọng: hook đặt **trước** toán tử recovery có thể quan sát lỗi upstream, trong khi hook đặt **sau** recovery có thể quan sát completion thành công của nhánh fallback.

## 4. Xử lý lỗi không hồi sinh chuỗi upstream

Reactor có nhiều operator xử lý lỗi, nhưng chúng **thay thế hoặc chuyển tín hiệu terminal** cho downstream; không làm luồng đã lỗi tiếp tục phát các phần tử bị bỏ lại.

| Operator | Khi upstream phát lỗi | Ý nghĩa |
| --- | --- | --- |
| `doOnError(callback)` | Gọi callback, rồi **vẫn truyền lỗi** | Log/metrics, không nuốt lỗi |
| `onErrorReturn(fallback)` | Phát một giá trị dự phòng, sau đó complete | Giá trị mặc định hợp lệ |
| `onErrorResume(fn)` | Chuyển sang publisher dự phòng được chọn theo lỗi | Fallback cache hoặc dịch vụ khác |
| `onErrorComplete()` | Biến `onError` thành `onComplete` | Bỏ qua thất bại khi nghiệp vụ cho phép |
| `onErrorMap(fn)` | Chuyển đổi exception, vẫn phát `onError` | Lỗi hạ tầng thành lỗi domain |
| `retry(n)` | Subscribe lại nguồn khi lỗi, tối đa `n` lượt bổ sung | Thử lại lỗi tạm thời |

Ví dụ `Flux.range(1, 5).map(...)` phát `10, 20` rồi lỗi tại phần tử thứ ba:

~~~text
Nguồn cũ:   10 -> 20 -> onError
onErrorReturn: 10 -> 20 -> 999 -> onComplete
onErrorResume: 10 -> 20 -> phần tử của fallback -> onComplete / onError
onErrorComplete: 10 -> 20 -> onComplete
~~~

**Không có operator nào trong ba cách recovery trên quay lại xử lý phần tử 4 và 5 của nguồn ban đầu.** Nếu cần tiếp tục xử lý các mục khác sau khi một mục lỗi, phải thiết kế ranh giới lỗi trên **từng tác vụ/inner publisher**, không đợi cả outer Flux phát `onError` rồi mới xử lý.

### `doOnError` chỉ quan sát

~~~java
// Pseudocode service: source, logger, consume và notifyFailure được định nghĩa ở ứng dụng.
source.doOnError(ex -> logger.warn("Upstream failed", ex))
    .subscribe(
        item -> consume(item),
        error -> notifyFailure(error)
    );
~~~

`doOnError` thực thi side effect, nhưng subscriber vẫn nhận lỗi. Nếu dùng `subscribe(onNext)` mà bỏ error consumer, lỗi có thể được báo dưới dạng error callback chưa được xử lý. Trong ứng dụng Spring WebFlux, thông thường nên **trả `Mono`/`Flux` cho framework** để framework quản lý subscription và mapping lỗi.

### `onErrorMap` vẫn là lỗi terminal

~~~java
// Đoạn minh họa với kiểu lỗi domain do ứng dụng tự định nghĩa.
Mono<Item> item = client.fetch(id)
    .onErrorMap(IOException.class,
        ex -> new CatalogUnavailableException("Catalog I/O failure", ex));
~~~

Khi `IOException` xảy ra, downstream nhận `onError(CatalogUnavailableException)` chứ không nhận một `Item` hợp lệ. Lựa chọn `onErrorMap` thích hợp khi muốn giữ trạng thái thất bại và cải thiện ngữ nghĩa lỗi.

## 5. Ví dụ Java 17+ chạy được: terminal, fallback và retry

Ví dụ console dưới đây dùng Reactor Core trực tiếp. Nguồn hoàn toàn đồng bộ để thứ tự stdout có thể xác định chính xác. Tạo cấu trúc:

~~~text
reactor-onerror-demo/
├── pom.xml
└── src/main/java/OnErrorTerminalDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-onerror-demo</artifactId>
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

File `src/main/java/OnErrorTerminalDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;

public class OnErrorTerminalDemo {
    private static Flux<Integer> numbers() {
        return Flux.range(1, 5)
            .map(n -> {
                if (n == 3) {
                    throw new IllegalStateException("bad 3");
                }
                return n * 10;
            });
    }

    private static void show(String title, Flux<Integer> flux) {
        System.out.println("== " + title + " ==");
        flux.subscribe(
            n -> System.out.println("onNext " + n),
            e -> System.out.println("onError " + e.getMessage()),
            () -> System.out.println("onComplete")
        );
    }

    public static void main(String[] args) {
        show("terminal", numbers());

        show("onErrorReturn", numbers().onErrorReturn(999));

        show("onErrorResume",
            numbers().onErrorResume(e -> Flux.just(70, 80)));

        show("onErrorComplete", numbers().onErrorComplete());

        AtomicInteger attempts = new AtomicInteger();

        Flux<Integer> retrying = Flux.defer(() -> {
            int attempt = attempts.incrementAndGet();
            System.out.println("attempt " + attempt);

            return Flux.range(1, 3).map(n -> {
                if (n == 2 && attempt == 1) {
                    throw new IllegalStateException("temporary");
                }
                return n;
            });
        }).retry(1);

        show("retry", retrying);
    }
}
~~~

Từ thư mục `reactor-onerror-demo`, chạy với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=OnErrorTerminalDemo
~~~

**Output do chương trình in** (không tính thông báo Maven nếu có):

~~~text
== terminal ==
onNext 10
onNext 20
onError bad 3
== onErrorReturn ==
onNext 10
onNext 20
onNext 999
onComplete
== onErrorResume ==
onNext 10
onNext 20
onNext 70
onNext 80
onComplete
== onErrorComplete ==
onNext 10
onNext 20
onComplete
== retry ==
attempt 1
onNext 1
attempt 2
onNext 1
onNext 2
onNext 3
onComplete
~~~

**Giải thích kết quả:**

1. Ở `terminal`, `numbers()` phát 10, 20 rồi `onError bad 3`. Nó **không** phát 40, 50 hoặc `onComplete`.
2. `onErrorReturn` thay lỗi bằng **một** giá trị 999, sau đó hoàn tất. Phần dữ liệu chưa xử lý của `numbers()` không quay lại.
3. `onErrorResume` dùng một **publisher fallback mới**, phát 70, 80 rồi hoàn tất. Fallback cũng có thể tự thất bại nếu nó có lỗi.
4. `onErrorComplete` biến thất bại thành completion, giữ 10, 20 và bỏ phần còn lại. Điều này có thể gây thất thoát dữ liệu nếu dùng vô điều kiện.
5. `retry(1)` tạo subscription lần thứ hai khi lần đầu lỗi. Số `1` được phát **hai lần** vì nguồn cold bắt đầu lại từ đầu, cho thấy retry có thể gây trùng dữ liệu hoặc side effect.

Ví dụ sử dụng `subscribe` có error consumer chỉ để minh họa. Nếu chương trình có nguồn bất đồng bộ, `main` có thể kết thúc trước khi callback chạy; cần kỹ thuật chờ phù hợp trong console/test. Không dùng `block()` trên event-loop Spring WebFlux.

## 6. `retry` hoạt động bằng cách đăng ký lại

`retry(n)` **không hồi sinh** một subscription đã lỗi. Nó tạo một lần subscription mới tới publisher upstream khi chính sách cho phép. Vì vậy:

- `retry(1)` có tối đa **hai lượt chạy**: lượt đầu và một lượt thử lại.
- Với publisher cold, mọi logic của nguồn có thể chạy lại từ đầu.
- Một `Flux` đã phát vài phần tử trước khi lỗi có thể phát lại chúng sau retry. Consumer có thể nhận bản ghi **trùng**.
- Lệnh ghi, chuyển tiền, gọi API thay đổi trạng thái hoặc gửi thông báo có side effect phải có **idempotency key**, transactional outbox hoặc cơ chế chống thực hiện trùng phù hợp; retry không tự cung cấp exactly-once.
- Nguồn hot không nhất thiết có replay; đăng ký lại không bảo đảm thu hồi sự kiện đã bỏ lỡ.
- Lỗi xác thực, validation và dữ liệu không hợp lệ thường không được cải thiện bởi retry, nên cần lọc lỗi có thể phục hồi.

`retryWhen` dùng chiến lược nâng cao như giới hạn lượt, exponential backoff và lọc exception:

~~~java
// Đoạn minh họa trong service; TransientNetworkException là loại lỗi
// do ứng dụng định nghĩa, cần import java.time.Duration và Retry.
Mono<Response> result = remoteCall()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .filter(ex -> ex instanceof TransientNetworkException)
    );
~~~

Đây là **mã minh họa** chưa chạy độc lập vì các loại `Response`, `TransientNetworkException`, `remoteCall()` và import thuộc ngữ cảnh ứng dụng. `Retry.backoff(3,...)` cho phép **tối đa ba lần retry** sau lần đầu. Nếu hết lượt vẫn lỗi, downstream nhận một lỗi tương ứng chiến lược retry exhausted; cần xử lý cause khi mapping lỗi nghiệp vụ.

### Vị trí của retry so với recovery

~~~java
// Thử lại nguồn trước, rồi mới fallback nếu còn lỗi:
source.retry(2).onErrorResume(ex -> fallback());

// Fallback được ưu tiên; retry phía sau chỉ có cơ hội nếu
// nhánh recovery vẫn phát lỗi:
source.onErrorResume(ex -> fallback()).retry(2);
~~~

Với đoạn thứ hai, `retry` có thể subscribe lại **toàn bộ đoạn `source.onErrorResume(...)`** nếu fallback phát lỗi. Thứ tự operator là một phần của hợp đồng nghiệp vụ; không nên đặt retry một cách tùy tiện chỉ để “hết lỗi” trong demo.

## 7. Xử lý lỗi theo từng phần tử mà không kết thúc toàn luồng

Một câu hỏi hay gặp: “Nếu bản ghi thứ ba lỗi, tôi vẫn muốn xử lý bản ghi thứ tư, thứ năm thì sao?”. Nếu một operator phát `onError` cho **outer Flux**, subscription outer đã kết thúc. `onErrorReturn` ở cuối không biến nó thành vòng lặp tiếp tục.

Giải pháp rõ ràng hơn là tạo **inner publisher riêng** cho từng bản ghi, với recovery ở bên trong:

~~~java
// Ví dụ trong service: ids, saveOne và logger do ứng dụng định nghĩa.
Flux<Result> saved = Flux.fromIterable(ids)
    .flatMap(id ->
        saveOne(id)
            .onErrorResume(ex -> {
                logger.warn("Skip id {}", id, ex);
                return Mono.empty();
            })
    );
~~~

Mỗi `saveOne(id)` được xử lý như một inner publisher. Nếu một inner phát `onError`, `onErrorResume` tại chính inner đó đổi lỗi thành **hoàn tất rỗng**, nên các ID khác có thể tiếp tục theo logic outer. Cách này chỉ hợp lệ khi nghiệp vụ **cho phép bỏ qua một ID**; nếu mọi bản ghi phải được lưu, cần chiến lược khác như fail cả batch và rollback/retry phù hợp.

Với `flatMap`, nhiều inner có thể hoạt động đồng thời và thứ tự kết quả có thể thay đổi. Nếu cần đảm bảo xử lý từng ID theo thứ tự, xem `concatMap`.

### Cẩn thận với `onErrorContinue`

Reactor hỗ trợ `onErrorContinue` trong một số operator có cơ chế lỗi phù hợp: nó có thể bỏ phần tử gây exception **trong operator đó** và tiếp tục phần tử khác. Tuy vậy, nó **không thể hồi sinh một `onError` terminal đã phát ra từ publisher tùy ý**. Hành vi còn phụ thuộc operator upstream, có thể lan qua thư viện khác và gây bất ngờ. Thực tế nên ưu tiên recovery tại từng inner publisher hoặc xử lý lỗi cục bộ có ranh giới rõ ràng.

## 8. Logging, cleanup và observability

`onError` thường phải được ghi nhận cho vận hành, nhưng **ghi log không đồng nghĩa với xử lý lỗi**.

| Công cụ | Dùng để | Lưu ý |
| --- | --- | --- |
| `doOnError` | Ghi log, metrics khi lỗi đi qua | Không thay đổi terminal signal |
| `doOnNext` | Quan sát giá trị thành công | Không chạy với riêng onError |
| `doOnComplete` (`Flux`) | Quan sát hoàn tất thành công | Không chạy khi kết thúc lỗi |
| `doFinally` | Dọn tài nguyên/metrics khi complete, error hoặc cancel | Vị trí đặt hook quyết định tín hiệu nhìn thấy |
| `using` / `usingWhen` | Quản lý resource quanh publisher | Cần thiết với connection, transaction/resource async |
| `checkpoint` | Bổ sung ngữ cảnh operator khi debug | Không dùng để thay error handling |
| `StepVerifier` (`reactor-test`) | Kiểm thử onNext, terminal và cancel | Xác nhận cả error/completion chính xác |

Ví dụ minh họa:

~~~java
// Trong service, logger và metrics là đối tượng giả định:
Flux<Result> observed = source
    .doOnError(ex -> logger.error("Failed to stream", ex))
    .doFinally(signal -> {
        if (signal == SignalType.ON_ERROR) {
            metrics.recordFailure();
        } else if (signal == SignalType.CANCEL) {
            metrics.recordCancel();
        }
    });
~~~

`SignalType` được import từ Reactor, còn `source`/logger/metrics tùy ứng dụng. Nếu thêm `onErrorResume` **sau** đoạn này, metric vẫn có thể ghi nhận lỗi upstream dù kết quả cuối cùng của request thành công nhờ fallback. Hãy quyết định cần đo **thất bại nguồn** hay **thất bại cuối cùng** để chọn chỗ đặt hook.

Với nguồn gắn listener/socket, một `onError` đã đến subscriber **không tự chứng minh** SDK đã tháo mọi callback. Bridge `Flux.create` nên đăng ký `sink.onDispose(...)`; với tài nguyên quản lý qua publisher, cân nhắc `using`/`usingWhen`. Cancellation từ client cần một nhánh cleanup riêng trong quản lý lifecycle.

## 9. Ý nghĩa trong Spring WebFlux và HTTP

Một controller WebFlux thông thường trả về `Mono<T>` hoặc `Flux<T>`. Khi publisher phát `onError`, framework xử lý theo exception mapping và tình trạng HTTP response. **`onError` không tự đồng nghĩa với HTTP 500**: Spring có thể chuyển `ResponseStatusException` thành 4xx/5xx, dùng `@ExceptionHandler` hoặc cơ chế lỗi toàn cục.

Ví dụ controller minh họa:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
class CatalogController {
    private final CatalogService service;

    CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/catalog/{id}")
    Mono<ItemDto> get(@PathVariable String id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Item not found")))
            .onErrorMap(ExternalCatalogException.class, ex ->
                new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Catalog unavailable", ex));
    }
}
~~~

Đây là mã **phụ thuộc dự án Spring Boot WebFlux**: `CatalogService`, `ItemDto`, `ExternalCatalogException` phải được ứng dụng định nghĩa, nên không chạy độc lập như ví dụ console.

- Nếu `findById` phát `ItemDto`, response có dữ liệu.
- Nếu `findById` hoàn tất **empty**, `switchIfEmpty` đổi “không tìm thấy” thành lỗi HTTP 404.
- Nếu `findById` lỗi với `ExternalCatalogException`, `onErrorMap` chuyển sang `ResponseStatusException` mang ý nghĩa HTTP 502.
- Lỗi khác tiếp tục qua cơ chế error handling được cấu hình. Không mặc định thay mọi exception bằng response thành công.

**Giới hạn streaming:** khi server đã gửi HTTP headers và một phần body (ví dụ SSE), nếu publisher mới phát `onError` thì **không thể đổi mã HTTP đã gửi thành 500**. Endpoint cần thiết kế cách thông báo stream bị lỗi, đóng kết nối và/hoặc cơ chế reconnect/replay, tùy hợp đồng client. Client disconnect cũng thường tạo **cancellation**, không được tự động xem là lỗi nghiệp vụ ở mọi metric.

Không gọi `subscribe()` chỉ để buộc controller chạy nghiệp vụ; hãy **trả publisher** để WebFlux quản lý subscription và cancellation.

## 10. Kiểm thử tín hiệu terminal

Thêm dependency `reactor-test` trong test scope, sau đó dùng `StepVerifier` để xác thực **giá trị trước lỗi và terminal**:

~~~java
// Đoạn test minh họa, cần reactor-test và import StepVerifier, Flux.
StepVerifier.create(
    Flux.just(10, 20)
        .concatWith(Flux.<Integer>error(
            new IllegalStateException("bad 3"))))
    .expectNext(10, 20)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && "bad 3".equals(ex.getMessage()))
    .verify();

StepVerifier.create(
    Flux.just(10, 20)
        .concatWith(Flux.<Integer>error(
            new IllegalStateException("bad 3")))
        .onErrorReturn(999))
    .expectNext(10, 20, 999)
    .verifyComplete();
~~~

Bài test đầu kỳ vọng `onError`, nên không có `verifyComplete`. Bài test sau kỳ vọng `onComplete` vì lỗi được thay thế bởi 999. Để kiểm thử cancel, có thể dùng `thenCancel()` và một hook `doFinally` để xác nhận upstream đã được dọn.

Với pipeline thật, nên có các ca:

1. `empty` → complete không có giá trị, không error.
2. Lỗi trước giá trị đầu tiên → chỉ nhận `onError`.
3. Lỗi sau N phần tử → không nhận phần tử hoặc complete sau error.
4. Fallback → nhận giá trị fallback và completion/error đúng hợp đồng.
5. Retry → giới hạn số lần, không retry lỗi permanent, kiểm chứng side effects/idempotency.
6. Cancel/disconnect → dừng nguồn và cleanup, phân loại khác error.
7. SSE đã commit rồi lỗi → client phát hiện stream dừng hoặc nhận sự kiện lỗi theo protocol dự án.

## 11. Những hiểu nhầm cần tránh

- **“Lỗi chỉ là một phần tử nên Flux tự đi tiếp.”** Sai. `onError` là terminal đối với subscription đó.
- **“Sau onError còn onComplete.”** Sai. Một subscription nhận một đường terminal.
- **“Mono.empty() là lỗi.”** Sai. Đó là completion thành công không giá trị.
- **“doOnError đã xử lý lỗi.”** Sai. Hook chỉ quan sát; lỗi vẫn được truyền.
- **“onErrorResume phục hồi phần còn lại của upstream.”** Sai. Nó chuyển sang nhánh fallback.
- **“onErrorComplete không có rủi ro.”** Sai. Nó có thể che giấu thất bại và bỏ dữ liệu chưa xử lý.
- **“retry nối tiếp từ item vừa lỗi.”** Sai. Nó subscribe lại; có thể phát trùng hoặc lặp side effect.
- **“retry luôn xử lý được mọi lỗi.”** Sai. Cần lọc lỗi retryable, giới hạn lượt và bảo đảm an toàn nghiệp vụ.
- **“onErrorContinue dùng được với mọi terminal error.”** Sai. Cơ chế này chỉ áp dụng cho một số operator hỗ trợ.
- **“Cancel của client là onError.”** Không nhất thiết. Cần quan sát `SignalType.CANCEL`.
- **“Chỉ cần try/catch quanh lời khai báo Flux.”** Sai với lỗi xuất hiện sau subscribe.
- **“onError luôn trả HTTP 500 trong WebFlux.”** Sai. Mapping phụ thuộc error handler và response đã commit.

## 12. Tự kiểm tra

**1.** `Flux.just(1, 2).concatWith(Flux.error(ex))` có gọi `onComplete` không? **Không**, nó nhận `onError(ex)`.

**2.** `Mono.empty()` có phải thất bại? **Không**, completion rỗng vẫn là thành công.

**3.** `onErrorReturn(99)` có xử lý các phần tử tiếp theo của nguồn đã error không? **Không**, chỉ phát fallback rồi complete.

**4.** `doOnError` có biến lỗi thành thành công không? **Không**, nó chỉ thực hiện side effect.

**5.** `retry(2)` có tổng tối đa bao nhiêu lượt subscription nếu tất cả đều lỗi? **Ba**: lần đầu và tối đa hai lần thử lại.

**6.** Vì sao retry có thể tạo dữ liệu trùng? **Nguồn cold được subscribe lại từ đầu** nên phần tử/side effect trước lỗi có thể lặp lại.

**7.** Khi muốn tiếp tục xử lý các ID khác dù một ID lỗi, nên đặt `onErrorResume` ở đâu? **Trong inner publisher của riêng ID đó**, với điều kiện nghiệp vụ cho phép bỏ qua.

**8.** SSE đã gửi một số chunk, sau đó lỗi, server có đổi được mã HTTP ban đầu không? **Không khi headers đã commit**; cần chiến lược thông báo/ngắt stream phù hợp.

**Ghi nhớ:** `onError` là **tín hiệu kết thúc thất bại của một subscription**, khác `onComplete` thành công và khác `cancel` do downstream yêu cầu. `onErrorReturn`, `onErrorResume`, `onErrorMap`, `onErrorComplete` hoặc `retry` tạo các cách xử lý **tiếp theo sau khi upstream lỗi**, nhưng không cho subscription đã lỗi phát tiếp. Trong Spring WebFlux, thiết kế ranh giới lỗi, fallback, idempotency, cleanup và HTTP error mapping theo ý nghĩa nghiệp vụ.

**Tài liệu chính thức:** [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html), [Reactor — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html), [Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).