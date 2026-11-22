# Đăng ký nhiều lần và trạng thái riêng của mỗi bên nhận

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Reactive Streams

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích điều gì xảy ra khi gọi `subscribe()` nhiều lần trên cùng một `Publisher`/`Flux`.
- Phân biệt đối tượng pipeline dùng chung với `Subscription`, nhu cầu dữ liệu (demand), tiến độ và trạng thái thuộc từng bên nhận.
- Tạo trạng thái riêng cho mỗi lần đăng ký bằng `Flux.defer` hoặc `Flux.generate`; nhận ra lỗi dùng biến mutable bên ngoài pipeline.
- Phân biệt các nguồn **cold** và **hot**, cũng như tác động của `share()`, `cache()`, hủy đăng ký và side effect.
- Dự đoán đầu ra của ví dụ Reactor và chọn cách triển khai an toàn trong Spring WebFlux.

## 1. Một Publisher, nhiều lần subscribe: cái gì được tạo mới?

Trong Reactive Streams, `Publisher<T>` mô tả nguồn phát, `Subscriber<T>` nhận tín hiệu, còn `Subscription` là quan hệ đăng ký cụ thể giữa nguồn và một bên nhận. Giao thức thông thường của một lần đăng ký:

```text
publisher.subscribe(subscriber)
       │
       └── onSubscribe(subscription)
                ├── subscriber gọi request(n)  → có thể nhận onNext(value)
                ├── subscriber gọi request(m)  → có thể nhận thêm onNext(value)
                ├── onComplete() HOẶC onError(error) → kết thúc
                └── cancel() → yêu cầu dừng, không phát onComplete chỉ vì cancel
```

`onSubscribe` đi trước `onNext`; số `onNext` không được vượt tổng demand đã yêu cầu. Một luồng có thể gửi ít phần tử hơn demand rồi kết thúc. `request(n)` phải có `n > 0`; `request(0)` hoặc số âm vi phạm giao thức và phải được báo lỗi theo Reactive Streams. `cancel()` yêu cầu ngừng phát và có thể có độ trễ lan truyền trong hệ bất đồng bộ.

Có thể gọi `subscribe` nhiều lần trên một đối tượng `Flux`. **Không đồng nghĩa với việc sử dụng lại cùng một `Subscription` hoặc cùng một đối tượng `Subscriber`.** Mỗi lần đăng ký được chấp nhận có quan hệ điều khiển riêng; đối với Reactor `BaseSubscriber`, hãy tạo instance mới cho mỗi lần đăng ký. Đặc tả cho phép `Publisher` lựa chọn hỗ trợ một hoặc nhiều subscriber, unicast hoặc multicast; không phải nguồn nào cũng nhận vô hạn lượt đăng ký.

Phân biệt ba lớp trạng thái:

| Phạm vi | Ví dụ | Có tách riêng mặc định? |
| --- | --- | --- |
| **Đối tượng assembly** – pipeline tạo khi viết `Flux<Integer> f = ...` | Biến được capture từ bên ngoài, đối tượng mutable do ứng dụng tự giữ | **Không.** Các subscription có thể dùng chung chính đối tượng này. |
| **Mỗi subscription** – khi nối pipeline với subscriber | Demand, tiến độ của `range`, toán tử `take`, tín hiệu hoàn tất/hủy, state supplier của `generate` | **Thường có** với cold pipeline; mỗi bên nhận có `Subscription` và trạng thái toán tử riêng. |
| **Nguồn dữ liệu bên dưới** | Kết nối socket, queue, sink, một upstream được `share()` | **Tùy nguồn.** Có thể là tài nguyên chung, đa phát hoặc chỉ chấp nhận một subscriber. |

Hình dung một cold `Flux.range(1, 3)` được hai bên nhận đăng ký:

```text
               Flux.range(1, 3)  (cùng đối tượng mô tả pipeline)
                    /       \
       subscribe(A)           subscribe(B)
          │                         │
     Subscription A             Subscription B
     demand A, vị trí A         demand B, vị trí B
     [1, 2, 3]                 [1, 2, 3]
```

Nếu A mới yêu cầu một phần tử thì A nhận `1` và dừng chờ demand tiếp theo; B vẫn có thể yêu cầu cả ba phần tử và đi đến `onComplete`. A không bị “đẩy” tới `2` chỉ vì B đã nhận `2`. Ví dụ `range` là nguồn đồng bộ, hữu hạn và cold; kết quả này không tự áp dụng cho mọi hot publisher.

## 2. Ví dụ chạy được: demand độc lập và subscriber mới

Ví dụ dùng **Java 17+**, **Maven** và **Project Reactor Core 3.8.8**. Tạo hai tệp như bên dưới; cần Java và Maven để tải dependency lần đầu.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>subscription-isolation</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/MultipleSubscriptionsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class MultipleSubscriptionsDemo {
    static final class NamedSubscriber extends BaseSubscriber<Integer> {
        private final String name;

        NamedSubscriber(String name) {
            this.name = name;
        }

        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            System.out.println(name + ": subscribe");
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(name + ": " + value);
        }

        @Override
        protected void hookOnComplete() {
            System.out.println(name + ": complete");
        }
    }

    public static void main(String[] args) {
        Flux<Integer> numbers = Flux.range(1, 3);
        NamedSubscriber a = new NamedSubscriber("A");
        NamedSubscriber b = new NamedSubscriber("B");

        numbers.subscribe(a);  // A nhận 1; chưa yêu cầu thêm
        numbers.subscribe(b);  // B cũng bắt đầu từ 1
        a.request(2);          // A nhận 2, 3 rồi hoàn tất
        b.request(1);          // B nhận 2
        b.request(1);          // B nhận 3 rồi hoàn tất

        AtomicInteger shared = new AtomicInteger();
        Flux<Integer> wrong = Flux.range(1, 3)
                .map(ignored -> shared.incrementAndGet());
        System.out.println("Shared A: " + wrong.collectList().block());
        System.out.println("Shared B: " + wrong.collectList().block());

        Flux<Integer> isolated = Flux.defer(() -> {
            AtomicInteger local = new AtomicInteger();
            return Flux.range(1, 3)
                    .map(ignored -> local.incrementAndGet());
        });
        System.out.println("Local A: " + isolated.collectList().block());
        System.out.println("Local B: " + isolated.collectList().block());
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=MultipleSubscriptionsDemo
```

**Stdout của chương trình** (không dùng scheduler, do đó thứ tự ví dụ này xác định):

```text
A: subscribe
A: 1
B: subscribe
B: 1
A: 2
A: 3
A: complete
B: 2
B: 3
B: complete
Shared A: [1, 2, 3]
Shared B: [4, 5, 6]
Local A: [1, 2, 3]
Local B: [1, 2, 3]
```

**Đọc kết quả:**

1. Hai lần `numbers.subscribe(...)` dùng cùng biến `numbers`, nhưng A và B nhận `Subscription` riêng và có demand riêng. Việc A hoàn thành không làm B tự hoàn thành.
2. `collectList().block()` tạo một lần đăng ký mới để lấy kết quả của cold `Flux`. Biến `shared` được tạo **ngoài** pipeline và được cả hai lượt dùng chung, nên bộ đếm tiếp tục từ `4` ở lần thứ hai.
3. `Flux.defer` gọi supplier khi từng subscription diễn ra. Mỗi lượt tạo `AtomicInteger local` mới, nên cùng bắt đầu ở `0` rồi cho `[1, 2, 3]`. `AtomicInteger` trong ví dụ sai vẫn an toàn về thao tác tăng trong cạnh tranh, nhưng **sai về ranh giới trạng thái**: thread-safe không có nghĩa là subscription-isolated.
4. `BaseSubscriber` cung cấp `request(n)`/`cancel()` và các lifecycle hook. Đối tượng này được thiết kế cho một subscription; tái sử dụng chính instance `a` cho một lượt khác là lỗi mô hình.

## 3. Cách cô lập state đúng chỗ

### 3.1. `defer`: tạo đối tượng hoặc side effect ở thời điểm đăng ký

Khi trạng thái, request ID, kết nối, phép tính hoặc nguồn dữ liệu phải mới theo từng lần đăng ký, đặt việc tạo chúng **bên trong** supplier:

```java
Flux<Integer> perSubscription = Flux.defer(() -> {
    AtomicInteger count = new AtomicInteger();
    return Flux.range(10, 12)
               .map(value -> count.incrementAndGet());
});
```

Đây là **đoạn mã minh họa**, dùng các import của chương trình trên. Mỗi lần subscribe, `count` mới được tạo. `Flux.range(10, 12)` phát 12 phần tử bắt đầu từ 10, còn `map` ở đây biến chúng thành bộ đếm `1..12`. `defer` không tự làm một nguồn ngoại vi thành không chia sẻ; nếu supplier trả lại cùng publisher hot hoặc cùng tài nguyên mutable, trạng thái vẫn có thể dùng chung.

Phân biệt thời điểm thực thi:

```java
Flux<String> captured = Flux.just(fetchValue()); // fetchValue() chạy ngay khi assembly
Flux<String> deferred = Flux.defer(
        () -> Flux.just(fetchValue()));          // fetchValue() chạy mỗi lần subscribe
```

Đây là đoạn minh họa, giả sử `fetchValue()` được ứng dụng định nghĩa và trả `String`. `just` giữ giá trị đã tính; mọi subscriber nhận giá trị đã giữ. Điều quan trọng là **thời điểm tạo giá trị**, không chỉ là số subscriber. Với I/O bất đồng bộ, ưu tiên API reactive trả `Mono`/`Flux` thay vì bọc lời gọi blocking không kiểm soát.

### 3.2. `generate`: state machine riêng cho từng bên nhận

`Flux.generate(stateSupplier, generator)` có state supplier được gọi cho **từng subscription**. Ví dụ độc lập về logic:

```java
Flux<Integer> sequence = Flux.<Integer, Integer>generate(
    () -> 1,
    (state, sink) -> {
        sink.next(state);
        if (state == 3) {
            sink.complete();
        }
        return state + 1;
    }
);
// Mỗi sequence.collectList().block() trả [1, 2, 3].
```

`state` của lượt A và B không trộn nhau. Với `generate`, mỗi lần gọi generator phát **tối đa một `onNext`** qua `SynchronousSink`; nguồn chịu demand nên không tự phát vượt khả năng bên nhận. Dùng `generate` khi dữ liệu được tính tuần tự từ state, còn `defer` khi cần tạo pipeline hoặc đối tượng theo mỗi lượt.

### 3.3. `Context`: dữ liệu gắn với subscription khi đi qua operator

Trong một chuỗi Reactor bất đồng bộ, không nên dùng `ThreadLocal` làm nơi lưu request ID hoặc thông tin người dùng xuyên suốt pipeline: toán tử có thể chuyển thread. Reactor `Context` gắn với subscription, có tính bất biến và được truyền theo ngữ cảnh của chuỗi.

```java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> label = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "unknown")));

System.out.println(label.contextWrite(Context.of("requestId", "REQ-A")).block());
System.out.println(label.contextWrite(Context.of("requestId", "REQ-B")).block());
```

Đây là đoạn mã Java đặt **bên trong một phương thức** (với các import ở đầu tệp); đầu ra là `REQ-A`, rồi `REQ-B`. `contextWrite` cung cấp ngữ cảnh cho các toán tử upstream và mỗi lần `block()` ở đây tạo subscription mới. `Context` thích hợp cho metadata, tracing, correlation; không nên dùng để chứa mutable business state tùy tiện.

## 4. Cold và hot thay đổi điều gì khi subscribe nhiều lần?

| Tiêu chí | Cold publisher | Hot/shared publisher |
| --- | --- | --- |
| Phát sinh dữ liệu | Thường tạo/đọc lại cho từng subscription | Có thể dùng chung một upstream đang chạy |
| Subscriber đến muộn | Thường bắt đầu từ logic ban đầu | Có thể chỉ nhận dữ liệu mới, trừ khi có replay/cache |
| Tài nguyên và side effect | Có thể lặp mỗi lần subscribe | Có thể chia sẻ; phụ thuộc toán tử và vòng đời kết nối |
| Demand/cancel | Quan hệ đăng ký vẫn riêng | Quan hệ đăng ký riêng nhưng upstream chung có chính sách phối hợp |
| Ví dụ Reactor | `Flux.range`, `Flux.defer` | `share()`, một `Sinks.Many` multicast, `replay`/`cache` với quy tắc replay |

**Không có quy luật “cùng Flux = cùng dữ liệu đang chạy”.** Một `Flux` chỉ là đối tượng mô tả chuỗi xử lý, và kiểu nguồn quyết định semantics:

- `Flux.range(1, 3)` là cold: mỗi subscriber nhận `1, 2, 3` nếu yêu cầu đủ.
- `Flux.just(x)` capture `x` lúc assembly rồi phát lại giá trị này cho các lần đăng ký; nếu việc tính `x` có side effect, side effect đó xảy ra trước subscribe.
- `source.share()` đa phát tín hiệu từ upstream chung khi đang kết nối. Subscriber đến muộn có thể bỏ lỡ những phần tử trước đó; khi người nhận cuối rời đi, kết nối upstream có thể bị hủy theo cơ chế reference counting.
- `source.cache()` giữ các tín hiệu để phát lại theo cấu hình cache; tiện tránh tính lại nhưng đánh đổi bộ nhớ, vòng đời và tính mới của dữ liệu. Đừng tự áp `cache()` lên dữ liệu phân quyền/người dùng khi chưa chọn rõ phạm vi cache.
- `Sinks.many().multicast()` phù hợp luồng sự kiện đẩy tới nhiều subscriber; `Sinks.many().unicast()` chỉ cho phép một bên nhận. `Sinks.many().replay()` có thể phát lại lịch sử theo chính sách đã chọn. Cần kiểm tra hành vi buffer, backpressure và subscriber đến muộn của từng biến thể sink.

**Ví dụ suy luận:** Tạo `Flux<Integer> f = Flux.range(1, 3)`, gọi `f.subscribe(A)` và sau đó `f.subscribe(B)`: A và B đều có thể nhận ba số. Nhưng với `Flux.interval(...).share()`, B đăng ký sau lúc upstream đã phát số đầu thì không thể mặc định B sẽ nhận lại số đầu. Kết quả hot phụ thuộc thời điểm subscribe, kết nối, demand và replay.

## 5. Hủy, lỗi, tài nguyên và backpressure

- **Hủy riêng:** A gọi `cancel()` thì A yêu cầu ngừng nhận; B vẫn có thể tiếp tục nếu nguồn hỗ trợ nhiều subscriber và upstream chung vẫn còn cần thiết. `cancel` tự nó không phát `onComplete` tới A; cũng không đảm bảo lập tức dừng mọi tác vụ đã lên lịch.
- **Kết thúc riêng:** cold nguồn hữu hạn thường có tín hiệu `onComplete` theo từng subscription. Lỗi ở một pipeline không tự động báo lỗi cho pipeline khác, trừ khi chúng dùng chung một nguồn có lỗi/chính sách terminal chung.
- **Dọn tài nguyên:** tài nguyên cấp theo lượt đăng ký nên được mở và đóng theo vòng đời lượt đó (cân nhắc `Flux.using`/`usingWhen`, `doFinally`). Với upstream dùng chung, vòng đời kết nối có thể chịu ảnh hưởng bởi số subscriber còn hoạt động.
- **Backpressure riêng:** mỗi subscriber gửi `request(n)` qua `Subscription` của mình. Trong pipeline nhiều toán tử, `prefetch`, `buffer`, `flatMap`, `publishOn` và các toán tử khác có thể thay đổi request upstream, nên số request ghi log ở một đoạn pipeline không nhất thiết bằng demand downstream từng phần tử.
- **Không đảm bảo công bằng tuyệt đối:** một nguồn hot chung phải có chính sách với subscriber chậm. Có thể buffer, drop, báo lỗi, chặn hoặc áp chiến lược khác tùy cấu hình; không suy ra “A chậm thì B luôn không bị ảnh hưởng”.

Trong ví dụ `Flux.range`, khi A chỉ `request(1)`, đừng chờ `onComplete` ngay: nguồn còn phần tử nhưng A chưa yêu cầu tiếp. Nếu không tăng demand hoặc cancel, subscription có thể tiếp tục ở trạng thái chờ. Ngược lại, các dạng `subscribe(value -> ...)` thông dụng của Reactor thường yêu cầu `Long.MAX_VALUE`, nên ví dụ demand có kiểm soát dùng `BaseSubscriber`.

## 6. Liên hệ Spring WebFlux

Một handler WebFlux thường **trả về** `Mono`/`Flux` và để framework quản lý subscription, demand và hủy khi client ngắt kết nối:

```java
@GetMapping("/items")
public Flux<ItemDto> items() {
    return itemService.findItems();
}
```

Đây là **đoạn trích minh họa trong Spring controller**: `ItemDto`, `itemService` và import `@GetMapping` cần được định nghĩa bởi ứng dụng. Không đặt `subscribe()` thủ công trong handler chỉ để “kích hoạt” chuỗi rồi trả một kết quả khác: dễ sinh tác vụ chạy ngoài vòng đời HTTP, khó truyền lỗi và hủy. Trả publisher cho framework; dùng `map`, `flatMap`, `then`... để ghép xử lý.

Nếu code sử dụng cùng một cold publisher cho hai yêu cầu hoặc hai nơi tiêu thụ, mỗi lượt subscribe **có thể lặp lại** truy vấn database, HTTP call hoặc side effect. Để tránh tính lại, phải lựa chọn cơ chế chia sẻ/cache với phạm vi hợp lệ và chính sách hết hạn phù hợp; không được mặc định mọi dữ liệu là an toàn để cache chung. Đối với request ID và metadata riêng của HTTP request, dùng Reactor `Context` khi cần truyền qua pipeline bất đồng bộ.

## 7. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| B nhận bộ đếm tiếp theo A (`4, 5, 6` thay vì `1, 2, 3`) | Mutable variable được capture bên ngoài chuỗi | Tạo state trong `defer` hoặc `generate` state supplier. |
| Tưởng A đã request thì B tự nhận dữ liệu | Nhầm demand của mỗi `Subscription` thành demand chung | Theo dõi request/cancel của từng subscriber. |
| Tái sử dụng một đối tượng `BaseSubscriber` | Instance giữ subscription hiện tại, không thiết kế để dùng lại | Tạo đối tượng subscriber mới cho mỗi lần subscribe. |
| Có request nhưng không thấy giá trị mới | Demand chưa đủ, nguồn chưa có dữ liệu hoặc chiến lược hot/backpressure | Quan sát `doOnRequest`, lifecycle, nguồn và operator; không đoán từ pipeline tổng quát. |
| Dữ liệu không giống nhau giữa hai lượt | Hot source, nguồn ngoài thay đổi, nondeterminism hoặc side effect | Xác định rõ cold/hot, thời điểm subscribe và chính sách replay. |
| API/database được gọi hai lần | Hai subscription của nguồn cold | Chỉ subscribe tại boundary thực sự; cân nhắc chia sẻ có chủ đích nếu cần. |
| Cancel ở một client ảnh hưởng kết nối khác | Nguồn dùng chung và lifecycle do `refCount`/chính sách upstream chi phối | Chọn cách share, số subscriber và phạm vi tài nguyên phù hợp. |
| Metadata request bị lẫn giữa các yêu cầu | Shared mutable state hoặc `ThreadLocal` trong xử lý bất đồng bộ | Tạo state per-subscription; dùng `Context` cho metadata. |

## 8. Tự kiểm tra

**Tình huống A.** `Flux<Integer> x = Flux.range(1, 3);` Sau khi subscriber thứ nhất nhận đủ ba giá trị, subscriber thứ hai đăng ký và yêu cầu ba giá trị. B nhận gì?  
**Đáp án:** Với nguồn cold này, B cũng nhận `1, 2, 3`. Subscription của A không làm cạn nguồn của B.

**Tình huống B.** Một `AtomicInteger` được khai báo ngoài `Flux.range(...).map(...)`. Hai lần subscribe tăng cùng bộ đếm. Đó có phải state per-subscription?  
**Đáp án:** Không. Đây là state chung nằm trong closure; dùng `Flux.defer` tạo bộ đếm mới trong supplier để cô lập.

**Tình huống C.** A gọi `cancel()` và B vẫn đăng ký vào một hot `share()`. Có chắc upstream bị hủy?  
**Đáp án:** Không. Với cơ chế chia sẻ theo số subscriber, upstream có thể còn hoạt động vì B vẫn cần dữ liệu. Chi tiết phụ thuộc toán tử chia sẻ và nguồn bên dưới.

## Ghi nhớ

**Một publisher có thể được đăng ký nhiều lần; mỗi subscription được chấp nhận có giao thức demand/cancel riêng.** Với nguồn cold, tiến độ tính toán và state tạo đúng ở thời điểm subscribe thường tách riêng. Nhưng biến mutable capture ngoài pipeline, kết nối hot, sink và cache có thể được chia sẻ. Thiết kế theo đúng phạm vi của state và vòng đời nguồn, thay vì giả định mỗi lần `subscribe` đều tự động cô lập mọi thứ.

### Tài liệu tham khảo

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm) – hợp đồng `Publisher`, `Subscriber` và `Subscription`.
- [Project Reactor – Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) – hành vi cold/hot, `defer` và `share`.
- [Project Reactor – On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) – demand, `BaseSubscriber` và request upstream.
