# Luồng dữ liệu, tín hiệu và xử lý theo sự kiện trong Spring Reactive

Trong Spring WebFlux, dữ liệu không nhất thiết được trả về một lần sau khi toàn bộ công việc kết thúc. Ứng dụng có thể biểu diễn công việc thành một **luồng phản ứng**: nguồn phát sinh phần tử khi có nhu cầu, các toán tử biến đổi chúng, và bên tiêu thụ phản ứng với dữ liệu, lỗi hoặc sự kết thúc. Project Reactor là thư viện thường dùng để xây dựng luồng này qua `Flux` và `Mono`.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Vẽ được đường đi **Publisher → operators → Subscriber** và giải thích lúc nào luồng bắt đầu chạy.
- Phân biệt **phần tử dữ liệu** (`onNext`) với **tín hiệu vòng đời** (`onSubscribe`, `onError`, `onComplete`, `cancel`).
- Giải thích cơ chế `Subscription.request(n)`, backpressure, luồng lạnh/luồng nóng và tác động của việc hủy đăng ký.
- Chọn `map`, `filter`, `flatMap`, `concatMap`, các toán tử xử lý lỗi cho một pipeline đơn giản.
- Đọc được ví dụ Reactor chạy được và liên hệ với xử lý HTTP theo sự kiện trong Spring WebFlux.

## 2. Tư duy về luồng dữ liệu

Trong lập trình mệnh lệnh thông thường, ta dễ hình dung lời gọi `result = service.load()` chờ kết quả rồi thực hiện dòng tiếp theo. Trong mô hình reactive, một phương thức có thể trả về **mô tả của công việc sẽ diễn ra** dưới dạng `Publisher`. Việc tạo pipeline (assembly) và việc thực thi pipeline (subscription) là hai giai đoạn khác nhau.

```text
Nguồn dữ liệu (Publisher)
    │ phát dữ liệu hoặc tín hiệu khi có đăng ký và nhu cầu
    ▼
filter → map → flatMap → doOnNext    (chuỗi toán tử)
    │
    ▼
Subscriber / HTTP response writer   (bên tiêu thụ)
    ▲
    └──── Subscription.request(n), cancel()  (điều khiển ngược lên)
```

**Dòng dữ liệu** thường đi từ nguồn xuống subscriber. **Yêu cầu số lượng phần tử** và **hủy luồng** đi từ subscriber về phía nguồn. Lỗi và hoàn thành cũng được truyền về phía subscriber. Mỗi toán tử có thể vừa đóng vai trò subscriber của phần trước, vừa là publisher của phần sau.

Hai kiểu Reactor cơ bản:

| Kiểu | Số phần tử `onNext` | Dùng khi |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Một kết quả, không có kết quả, hoặc chỉ cần tín hiệu hoàn tất (`Mono<Void>`) |
| `Flux<T>` | 0 đến nhiều | Danh sách, nhiều bản ghi, sự kiện kéo dài theo thời gian |

`Mono`/ `Flux` không bảo đảm dữ liệu luôn đến bất đồng bộ: `Flux.just(1, 2)` có thể chạy đồng bộ trên thread hiện tại; `Flux.interval(...)` phát theo lịch và dùng scheduler. **Reactive không đồng nghĩa với “mỗi phần tử có một thread”.** Đồng thời, `Flux` không tương đương với `java.util.stream.Stream`: Reactor có giao thức tín hiệu, yêu cầu phần tử và hủy đăng ký, đồng thời có thể tích hợp I/O không chặn.

## 3. Tín hiệu trong Reactive Streams

Giao thức nền tảng định nghĩa bốn giao diện: `Publisher<T>` (nguồn), `Subscriber<T>` (người nhận), `Subscription` (quyền yêu cầu/hủy) và `Processor<T,R>` (một thành phần vừa nhận vừa phát). Phần lớn mã ứng dụng Spring làm việc ở mức `Mono`/`Flux` thay vì tự triển khai các giao diện này.

Một đăng ký có chu trình khái quát:

1. `subscriber` đăng ký với `publisher` qua `subscribe(...)`.
2. Publisher gửi **`onSubscribe(subscription)`** để cung cấp quyền điều khiển.
3. Subscriber gọi **`request(n)`** với `n > 0`; nguồn được phép phát tối đa số phần tử chưa được yêu cầu hết (đối với nguồn tuân thủ backpressure).
4. Mỗi phần tử dữ liệu được gửi qua **`onNext(value)`**. Giá trị `null` không hợp lệ với tín hiệu `onNext` của Reactive Streams.
5. Luồng kết thúc bằng đúng một trong hai tín hiệu cuối: **`onComplete()`** (thành công) hoặc **`onError(cause)`** (thất bại). Sau tín hiệu kết thúc không còn `onNext` nào hợp lệ.
6. Subscriber có thể gọi **`cancel()`** để ngừng quan tâm đến luồng; hủy không đồng nghĩa với việc subscriber nhận `onComplete`.

```text
Có dữ liệu:  onSubscribe → request(3) → onNext(A) → onNext(B) → onComplete
Luồng rỗng:  onSubscribe → onComplete
Bị lỗi:      onSubscribe → request(2) → onNext(A) → onError(E)
Bị hủy:      onSubscribe → request(10) → onNext(A) → cancel
```

Các mũi tên mô tả thứ tự logic, không bắt buộc tất cả xảy ra trên cùng một thread hay trong cùng một thời điểm. `request(n)` có thể xuất hiện nhiều lần, và phần tử sẽ đến từng đợt. `onSubscribe`, `onNext`, `onComplete`, `onError` là **tín hiệu của giao thức**; một bản ghi nghiệp vụ tên “OrderCreated” lại là **dữ liệu của ứng dụng** được mang trong `onNext`. Phân biệt này giúp tránh nhầm “sự kiện nghiệp vụ” với “tín hiệu vòng đời luồng”.

### Ba tình huống cần nhớ

- `Mono.empty()` không phát `onNext`, nhưng hoàn thành bình thường. `Mono.error(e)` kết thúc bằng lỗi.
- Trong `Flux.just(1, 2, 3).map(...)`, việc khai báo `map` chưa tiêu thụ phần tử. Với nguồn lạnh thông dụng, cần có đăng ký để công việc chạy.
- Nếu nguồn phát `onError` ở phần tử thứ hai, phần tử tiếp theo trong cùng nhánh nguồn sẽ không được xử lý; `onErrorResume` có thể **chuyển sang publisher dự phòng**, không hồi sinh phần còn lại của nguồn cũ.

## 4. Ví dụ chạy được: dữ liệu đi qua các toán tử

Tạo một project Maven Java 17+ có cấu trúc:

```text
reactive-flow/
├── pom.xml
└── src/main/java/ReactiveFlowDemo.java
```

Nội dung `pom.xml` (dùng Reactor độc lập để quan sát cơ chế; trong Spring Boot nên ưu tiên phiên bản do BOM của Boot quản lý):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactive-flow</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
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
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Nội dung `src/main/java/ReactiveFlowDemo.java`:

```java
import reactor.core.publisher.Flux;

public class ReactiveFlowDemo {
    public static void main(String[] args) {
        Flux.range(1, 4)
            .doOnSubscribe(s -> System.out.println("subscribed"))
            .doOnNext(n -> System.out.println("source: " + n))
            .filter(n -> n % 2 == 0)
            .map(n -> "event-" + n)
            .doOnNext(s -> System.out.println("handled: " + s))
            .doOnComplete(() -> System.out.println("completed"))
            .blockLast();
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=ReactiveFlowDemo
```

Stdout của chương trình:

```text
subscribed
source: 1
source: 2
handled: event-2
source: 3
source: 4
handled: event-4
completed
```

Giải thích theo thứ tự thực tế:

- `Flux.range(1, 4)` là nguồn phát 1, 2, 3, 4. Chưa có đăng ký thì chưa in gì.
- `blockLast()` tạo một đăng ký và chờ luồng kết thúc, phù hợp cho **demo console** này. Trong WebFlux handler/event loop, không dùng `block()`/`blockLast()` để chờ I/O.
- `doOnSubscribe` quan sát bước đăng ký; `doOnNext` đầu tiên quan sát mọi giá trị đến từ nguồn.
- `filter` loại 1 và 3; `map` đổi 2 và 4 thành `event-2`, `event-4`.
- `doOnComplete` quan sát tín hiệu kết thúc sau khi cả bốn phần tử nguồn đã đi qua pipeline. `doOnNext` chỉ phù hợp cho logging, đo đạc, quan sát; logic biến đổi dữ liệu nên viết bằng `map`/`flatMap`.

Đây là một nguồn đồng bộ nên thứ tự stdout ổn định. Khi nguồn hoặc toán tử chuyển việc qua scheduler, không được suy ra thứ tự giữa **nhiều luồng độc lập** chỉ từ ví dụ này.

## 5. Backpressure: bên tiêu thụ chủ động yêu cầu dữ liệu

Giả sử nguồn tạo 100.000 sự kiện/giây nhưng consumer chỉ xử lý được 1.000 sự kiện/giây. Nếu nguồn cứ đẩy không giới hạn, hàng đợi tăng, bộ nhớ tăng và độ trễ trở nên khó kiểm soát. **Backpressure** cho phép downstream thông báo mức nhu cầu qua `Subscription.request(n)` và upstream điều tiết việc phát khi có thể.

Ví dụ sau dùng `BaseSubscriber` để nhìn rõ hai lần yêu cầu, thay vì kiểu `subscribe(value -> ...)` thường yêu cầu không giới hạn:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 4).subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("request 2");
                request(2);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("next " + value);
                if (value == 2) {
                    System.out.println("request 2");
                    request(2);
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

Lưu dưới `src/main/java/DemandDemo.java` trong cùng project và chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=DemandDemo
```

Stdout:

```text
request 2
next 1
next 2
request 2
next 3
next 4
complete
```

`request(2)` ban đầu cho phép hai phần tử. Sau khi nhận 2, subscriber xin thêm hai phần tử, nên 3 và 4 mới được phát. Nếu không xin thêm, luồng còn dữ liệu nhưng có thể đứng chờ nhu cầu mãi. Gọi `request(Long.MAX_VALUE)` có nghĩa yêu cầu không giới hạn; nhiều cách đăng ký bằng lambda và `block*` dùng dạng này. Các toán tử như `buffer`, `flatMap` hoặc `limitRate` có thể **biến đổi lượng request** khi truyền ngược upstream, vì thế không nên giả định mọi chặng đều request đúng từng phần tử.

Reactive Streams định nghĩa cơ chế truyền nhu cầu, không hứa rằng mọi nguồn thực tế đều có thể tự giảm tốc. Nguồn nóng, callback ngoại vi hay hệ thống đẩy sự kiện không thể dừng có thể cần chính sách **buffer, drop hoặc error**. Buffer không giới hạn có nguy cơ tràn bộ nhớ; nên đo tốc độ nguồn/đích và đặt chính sách dung lượng rõ ràng.

## 6. Luồng lạnh, luồng nóng và việc đăng ký

**Cold publisher** thường tạo lại chuỗi sự kiện cho *mỗi* subscriber. Chẳng hạn `Flux.defer(() -> Flux.just(loadValue()))` gọi `loadValue()` theo từng lần đăng ký; với `WebClient`, mỗi lần subscribe vào publisher HTTP lạnh thông dụng có thể kích hoạt một request mới. Cần đặc biệt lưu ý tác dụng phụ: hai subscriber có thể gây hai thao tác tải dữ liệu.

**Hot publisher** có thể phát độc lập với việc một subscriber bắt đầu lắng nghe; subscriber đến muộn có thể bỏ lỡ sự kiện đã phát. Ví dụ một luồng được chia sẻ bằng `share()` hoặc nguồn được nối với `Sinks.Many` có đặc tính nóng tùy cấu hình. Phân phối lại dữ liệu, replay và giữ cache là các lựa chọn riêng; không mặc định nguồn nóng luôn lưu đủ quá khứ cho người đăng ký mới.

Hình dung:

```text
Cold: Sub A → [1, 2, 3]    Sub B đăng ký sau → [1, 2, 3]
Hot:        ...1...2...3...4...
             Sub A ↑         Sub B ↑ (có thể chỉ nhận phần sau)
```

**Cancellation** quan trọng cho cả hai loại nguồn. Khi client đóng kết nối SSE hoặc subscriber gọi `Disposable.dispose()`, luồng có thể được hủy, giúp dừng lịch phát, xử lý hoặc giải phóng tài nguyên theo đường hủy. Nếu một thao tác bên ngoài đã xảy ra thì cancel không tự động hoàn tác thao tác đó. `doFinally(signalType -> ...)` có thể quan sát `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL` để dọn dẹp/đo đạc.

## 7. Chọn toán tử theo ý định xử lý sự kiện

| Toán tử | Vai trò | Lưu ý |
| --- | --- | --- |
| `map` | Đồng bộ biến đổi một phần tử thành một phần tử | Hàm biến đổi không trả `null` |
| `filter` | Chỉ cho phần tử thỏa điều kiện đi tiếp | Phần tử bị loại không phải lỗi |
| `flatMap` | Mỗi phần tử thành một publisher khác, rồi gộp các kết quả | Có thể xen kẽ và đổi thứ tự hoàn thành |
| `concatMap` | Xử lý các publisher con lần lượt | Hữu ích khi thứ tự đầu vào bắt buộc được bảo toàn |
| `zip` | Ghép phần tử từ các nguồn theo cặp | Có thể hoàn thành sớm nếu một nhánh hết dữ liệu |
| `buffer(n)` | Gom các phần tử thành từng danh sách tối đa `n` phần tử | Tăng lượng dữ liệu giữ trong bộ nhớ |
| `doOnNext`, `doOnError` | Quan sát tín hiệu cho log/metrics | Không phải toán tử thay thế dữ liệu hoặc phục hồi lỗi |
| `onErrorResume` | Chuyển sang publisher dự phòng khi có lỗi | Nhánh nguồn ban đầu đã kết thúc |
| `timeout` | Báo lỗi khi không có tín hiệu theo điều kiện thời gian | Cần chọn timeout theo SLA thực tế |

Ví dụ giao dịch: `Flux<OrderEvent>` nhận sự kiện đơn hàng → `filter` chọn sự kiện hợp lệ → `map` chuẩn hóa → `flatMap` gọi dịch vụ I/O không chặn → trả kết quả cho bên tiêu thụ. Nếu các sự kiện cùng một đơn hàng phải được xử lý theo đúng trình tự, cân nhắc `concatMap` hoặc phương án phân vùng theo khóa; đừng dùng `flatMap` rồi mặc định thứ tự ổn định. Một pipeline không trở nên non-blocking nếu hàm bên trong `map` hoặc `flatMap` gọi trực tiếp API I/O chặn.

## 8. Lỗi là tín hiệu kết thúc, không phải phần tử bình thường

Ví dụ thứ ba sử dụng cùng project Maven:

```java
import reactor.core.publisher.Flux;

public class ErrorSignalDemo {
    public static void main(String[] args) {
        Flux.just(2, 0, 5)
            .map(n -> 10 / n)
            .subscribe(
                n -> System.out.println("next " + n),
                e -> System.out.println("error " + e.getClass().getSimpleName()),
                () -> System.out.println("complete")
            );
    }
}
```

Chạy `mvn -q compile exec:java -Dexec.mainClass=ErrorSignalDemo`. Stdout:

```text
next 5
error ArithmeticException
```

Số 0 gây chia cho 0 nên `onError` kết thúc luồng. Giá trị 5 ở **cuối nguồn** không được xử lý, và `onComplete` không được gọi. Nếu thêm `onErrorResume(e -> Flux.just(-1))` ngay sau `map`, subscriber sẽ nhận 5 rồi -1, sau đó hoàn thành; đây là dữ liệu từ publisher dự phòng, không phải xử lý tiếp phần tử 5 cũ.

Thực hành xử lý lỗi:

- Dùng `doOnError` để ghi nhận lỗi; dùng `onErrorResume` hoặc `onErrorReturn` khi thật sự muốn giá trị thay thế.
- Chọn `retry`/ `retryWhen` có điều kiện, giới hạn lần thử và chỉ áp dụng khi việc lặp lại thao tác an toàn. Retry có thể **đăng ký lại nguồn** và tái thực thi tác dụng phụ.
- Tránh che mọi lỗi thành giá trị mặc định vì sẽ làm mất dấu lỗi nghiệp vụ và lỗi hạ tầng.
- Dùng xử lý lỗi HTTP phù hợp ở ranh giới WebFlux; đừng hiểu `onError` như một item JSON nghiệp vụ được gửi tiếp cùng stream.

## 9. Xử lý theo sự kiện trong Spring WebFlux

Một HTTP request đến server non-blocking thường được xử lý theo các mốc: socket sẵn sàng đọc → server nhận request → framework chọn handler → handler **trả về** `Mono`/`Flux` → framework đăng ký và ghi dữ liệu khi có thể → thành công, lỗi hoặc client ngắt kết nối. Thread xử lý I/O không cần bị giữ lại chỉ để chờ một truy vấn mạng hay sự kiện tiếp theo, miễn là toàn bộ đường I/O liên quan tuân thủ thiết kế không chặn.

Ví dụ **bên trong một ứng dụng Spring WebFlux** (đây là controller, không phải chương trình Java độc lập có `main`):

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/events")
public class EventController {
    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> ticks() {
        return Flux.interval(Duration.ofSeconds(1))
                   .map(i -> "tick-" + i)
                   .take(3);
    }
}
```

Với WebFlux starter và ứng dụng đang chạy, `curl -N http://localhost:8080/events/ticks` sẽ nhận các bản tin SSE chứa `tick-0`, `tick-1`, `tick-2` theo thời gian, rồi kết nối kết thúc. `Flux.interval` tạo nguồn phát theo lịch; `take(3)` giới hạn ba phần tử; `text/event-stream` giúp HTTP truyền lần lượt từng sự kiện. Nếu client ngắt kết nối, subscription tương ứng có thể bị hủy. **Không gọi `subscribe()` thủ công trong controller chỉ để “kích hoạt” Flux**: hãy trả publisher để WebFlux quản lý subscription, backpressure, lỗi và vòng đời kết nối.

Một `Flux` trả về qua HTTP không tự động tạo streaming hiển thị từng phần tử với mọi media type. Ví dụ đáp ứng JSON thông thường có thể được tổng hợp/encode theo cách khác với SSE. Muốn gửi từng sự kiện cho client, chọn đúng giao thức và media type như SSE hoặc WebSocket theo nhu cầu giao tiếp.

### Ví dụ gắn với WebClient

Trong một thành phần đã có `WebClient` và kiểu dữ liệu phù hợp, chuỗi sau chỉ mô tả pipeline, chưa tự kích hoạt HTTP request:

```java
Flux<EventDto> events =
    webClient.get()
             .uri("/events")
             .retrieve()
             .bodyToFlux(EventDto.class)
             .filter(EventDto::isValid);
```

Đoạn mã này minh họa API, cần có khai báo `webClient` và `EventDto` trong ứng dụng thật. Khi một thành phần downstream đăng ký, WebClient thực hiện trao đổi HTTP; `filter` xử lý các phần tử nhận được. Dữ liệu/điểm kết thúc thực tế còn tùy server và loại response. Cần quản lý timeout, mã trạng thái, lỗi decode và vòng đời subscription.

## 10. Event loop, scheduler và giới hạn của non-blocking

Spring WebFlux (đặc biệt khi chạy với Reactor Netty) dùng số lượng thread I/O hạn chế theo mô hình event loop. Một thread xử lý nhiều kết nối bằng cách phản ứng khi có sự kiện I/O, thay vì chờ chặn ở từng request. Vì vậy, một `Thread.sleep(...)`, JDBC/JPA đồng bộ, `Future.get()` hay `block()` trong event loop có thể làm chậm cả những request khác cùng dùng thread đó.

- `subscribeOn(scheduler)` tác động đến **ngữ cảnh đăng ký và quá trình phát upstream**.
- `publishOn(scheduler)` đổi ngữ cảnh thực thi cho **các toán tử downstream** kể từ vị trí gọi.
- Scheduler không tự làm thư viện I/O blocking trở thành non-blocking. Khi buộc phải tích hợp lời gọi đồng bộ, cô lập nó có kiểm soát bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, đặt timeout/giới hạn và theo dõi tải; về lâu dài ưu tiên API có hỗ trợ non-blocking.

Ví dụ sau là **mảnh ghép minh họa** phụ thuộc vào một API cũ do ứng dụng cung cấp:

```java
Mono<Result> result =
    Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

`Result`, `legacyRepository`, `id` phải được định nghĩa trong ứng dụng. Không đặt trực tiếp `legacyRepository.load(id)` trong `map` chạy trên event loop. Đừng thêm scheduler tùy tiện cho mọi toán tử: chuyển thread có chi phí và có thể khiến việc suy luận thứ tự/khả năng đồng thời khó hơn.

## 11. Những lỗi tư duy và lỗi triển khai thường gặp

1. **Tạo pipeline nhưng bỏ giá trị trả về.** `source.map(fn);` tạo publisher mới; nếu vẫn dùng `source`, biến đổi `fn` không nằm trong pipeline mà downstream sẽ nhận. Hãy kết nối/return publisher mới.
2. **Gọi `subscribe()` bên trong service rồi trả `Mono.empty()`.** Công việc trở thành “fire and forget”, rời khỏi luồng lỗi/cancel của người gọi. Ưu tiên `return repository.save(...).then(...)` hoặc compose bằng `flatMap`.
3. **Tưởng `doOnNext` luôn chạy chính xác một lần.** Nó chạy theo mỗi subscription và có thể lặp khi retry/resubscribe. Side effect không idempotent cần được thiết kế riêng.
4. **Nhầm `onComplete` với `cancel`.** Client rời đi giữa stream là hủy; không nên ghi nhận “đã hoàn thành xử lý” chỉ từ việc callback dừng.
5. **Giả định `flatMap` luôn giữ thứ tự.** Các publisher con có thời gian hoàn thành khác nhau. Dùng `concatMap` khi cần tuần tự; cân nhắc thông lượng.
6. **Dùng buffer không giới hạn để chữa mọi vấn đề backpressure.** Buffer chỉ dời điểm quá tải sang bộ nhớ; cần kiểm soát tốc độ, giới hạn, chính sách overflow và metrics.
7. **Đưa blocking I/O vào event loop.** Kiểm tra toàn bộ chuỗi gọi, không chỉ chữ ký phương thức trả về `Mono`/`Flux`.
8. **Không khai báo nhánh lỗi.** `onError` là một kết cục thật; log, HTTP error mapping, retry và chiến lược phục hồi cần rõ ràng.
9. **Nhầm reactive stream với message broker.** Reactive Streams là giao thức giữa publisher và subscriber trong quá trình xử lý; Kafka/RabbitMQ có semantics lưu trữ, xác nhận, phân phối và retry riêng. Có thể tích hợp hai mô hình nhưng không đánh đồng backpressure với broker acknowledgement.
10. **Dùng `block()` để kiểm tra trong code production reactive.** Trong hàm `main` hoặc một phép thử cô lập có thể chấp nhận; trong WebFlux handler hãy trả publisher cho framework.

## 12. Kiểm thử và quan sát luồng

Trong các bài test Reactor, `StepVerifier` (dependency `reactor-test`, dùng cùng phiên bản với `reactor-core`) cho phép kiểm chứng **thứ tự phần tử và terminal signal**:

```java
StepVerifier.create(Flux.just(1, 2).map(n -> n * 2))
            .expectNext(2, 4)
            .verifyComplete();
```

Đây là một mảnh ghép test; cần import `reactor.test.StepVerifier`, `reactor.core.publisher.Flux` và thêm dependency test phù hợp. Với luồng lỗi, dùng `expectError(...)`/ `expectErrorMatches(...)`; với luồng thời gian, xem virtual time để kiểm thử có tính quyết định. Không nên kiểm thử luồng bất đồng bộ bằng `Thread.sleep` và giả định các tác vụ đã chạy xong.

Khi quan sát production, dùng `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnError`, `doFinally` đúng điểm cần thiết và metrics phù hợp. Ghi log có chọn lọc, tránh log dữ liệu nhạy cảm hay toàn bộ payload lớn; chú ý một pipeline có thể được subscribe nhiều lần. Để theo dõi context xuyên qua thao tác bất đồng bộ, tìm hiểu Reactor `Context` và cơ chế observability của Spring thay vì luôn dựa vào `ThreadLocal`.

## 13. Bài tập tự kiểm tra

**Tình huống A.** `Flux.just("A", "B").map(String::toLowerCase)` được tạo rồi không ai đăng ký. Có `onNext` không?  
**Đáp án:** Không có quá trình tiêu thụ. Đây là pipeline từ nguồn lạnh; cần đăng ký mới phát các phần tử.

**Tình huống B.** Nguồn phát 1 → 2 → lỗi → 3. Subscriber có thể nhận 3 sau `onError` không?  
**Đáp án:** Không; lỗi là terminal signal. Muốn dữ liệu thay thế, phải chuyển sang nhánh dự phòng bằng toán tử thích hợp.

**Tình huống C.** Subscriber chỉ gọi `request(1)`, nguồn tuân thủ backpressure có 10 phần tử. Điều gì xảy ra?  
**Đáp án:** Tối đa một `onNext` được phép phát theo nhu cầu hiện tại; nếu chưa có thêm request, luồng có thể chờ. Có ngoại lệ về tín hiệu kết thúc khi nguồn đã có thể xác định kết thúc; không được suy ra nó phải phát đủ 10 phần tử.

**Tình huống D.** Một endpoint WebFlux trả `Flux<String>` từ SSE. Có nên gọi `subscribe()` trong handler trước khi `return` không?  
**Đáp án:** Không. Trả lại publisher để framework đăng ký theo vòng đời HTTP và xử lý yêu cầu, lỗi, hủy một cách nhất quán.

**Tình huống E.** Mỗi phần tử kích hoạt một HTTP call không chặn và yêu cầu giữ thứ tự kết quả bằng thứ tự đầu vào. Chọn `flatMap` hay `concatMap`?  
**Đáp án:** `concatMap` nếu cần tuần tự chắc chắn; `flatMap` có thể hoàn thành xen kẽ, có lợi về đồng thời nhưng không bảo đảm thứ tự đó.

## 14. Ghi nhớ

**Dữ liệu** đi qua `onNext`; **vòng đời** được xác định bằng `onSubscribe`, `request`, `onError`, `onComplete`, `cancel`. Trong Reactor, ta ghép các toán tử để mô tả phản ứng đối với sự kiện, rồi để subscriber hoặc Spring WebFlux vận hành pipeline. Muốn hệ thống thực sự mở rộng theo mô hình non-blocking, phải bảo toàn khả năng không chặn qua các tầng I/O, quản lý nhu cầu và tác dụng phụ, và xử lý đúng cả lỗi lẫn hủy đăng ký.

### Tài liệu tham khảo

- Spring Framework, [Spring WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html).
- Spring Framework, [Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Project Reactor, [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Reactive Streams specification](https://www.reactive-streams.org/).
