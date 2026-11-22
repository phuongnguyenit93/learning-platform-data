# cache, replay và giới hạn lưu giữ dữ liệu

Trong **Spring WebFlux** và **Project Reactor**, nguồn dữ liệu reactive có thể là *cold* hoặc *hot*. Khi nhiều subscriber cùng cần một luồng dữ liệu, ứng dụng có thể muốn **chia sẻ một lần thực thi**, **phát lại dữ liệu đã phát cho subscriber đến muộn**, hoặc **chỉ giữ một phần lịch sử trong một khoảng thời gian**.

Ba khái niệm thường đi cùng nhau nhưng không đồng nghĩa:

- **`cache`** biến một publisher thành nguồn chia sẻ có lưu tín hiệu đã phát để subscriber sau có thể nhận lại. Các overload cho phép giới hạn số phần tử và/hoặc thời gian lưu giữ.
- **`replay`** tạo một luồng có khả năng phát lại lịch sử cho subscriber đến sau; trong Reactor, `ConnectableFlux.replay(...)` cho phép điều khiển lúc kết nối nguồn và giới hạn lịch sử.
- **Giới hạn lưu giữ dữ liệu** xác định giữ bao nhiêu phần tử, trong bao lâu và với chi phí bộ nhớ nào. Chỉ giới hạn số phần tử chưa chắc giới hạn chính xác số byte.

Bài này giải thích cold/hot, chia sẻ và phát lại, các operator Reactor, cách dùng `Sinks.Many`, và cách chọn chính sách retention an toàn trong ứng dụng thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt nguồn cold và hot; giải thích subscriber đến muộn nhận được gì ở mỗi loại.
2. Phân biệt `share`, `publish`, `replay` và `cache` về chia sẻ subscription, lịch sử được giữ và cách bắt đầu nguồn.
3. Dùng `Flux.cache(history)`, `cache(ttl)` hoặc overload kết hợp để kiểm soát lịch sử.
4. Dùng `ConnectableFlux.replay(history)`, `connect`, `autoConnect` và `refCount` đúng vòng đời.
5. Dùng `Sinks.many().replay().limit(n)` khi cần chủ động phát sự kiện và giữ một số phần tử gần nhất.
6. Hiểu cache giữ cả tín hiệu terminal như completion/lỗi, và biết tác động của việc cache lỗi hoặc nguồn rỗng.
7. Đánh giá memory retention, TTL, kích thước payload, tốc độ phát, subscriber chậm, cancellation và backpressure.
8. Kiểm thử hành vi subscriber đầu tiên và subscriber đến muộn bằng `StepVerifier`.

## 2. Nguồn cold và hot

### 2.1. Cold publisher: mỗi subscriber có một lần thực thi riêng

Một cold publisher thường bắt đầu công việc khi có subscriber. Mỗi lần subscribe mới có thể nhận một chuỗi mới từ đầu:

~~~java
Flux<Integer> cold = Flux.defer(() -> Flux.just(1, 2, 3));
~~~

Hai subscriber độc lập thường nhận:

~~~text
Subscriber A: 1 -> 2 -> 3 -> complete
Subscriber B: 1 -> 2 -> 3 -> complete
~~~

Ví dụ quen thuộc là `Flux.range`, `Flux.fromIterable`, `Mono.fromCallable` và `WebClient` request được tạo cho mỗi lần subscribe. `defer` làm rõ việc tạo nguồn tại thời điểm subscribe. Tuy nhiên cold **không có nghĩa** mọi nguồn đều tạo một tài nguyên hoàn toàn mới: hành vi cụ thể vẫn do publisher nguồn định nghĩa.

Nếu cold publisher đại diện cho HTTP GET, hai subscription có thể tạo hai HTTP request. Nếu đại diện cho `Mono.fromCallable(() -> readFile())`, file có thể được đọc hai lần. Điều này có thể đúng, nhưng nếu nhiều subscriber cần cùng một kết quả thì chi phí bị lặp.

### 2.2. Hot publisher: nguồn phát không phụ thuộc từng subscriber

Một hot publisher có thể phát sự kiện theo thời gian hoặc theo hoạt động của hệ thống, dù hiện tại không có subscriber. Subscriber đến muộn có thể **bỏ lỡ các phần tử đã phát trước khi họ đăng ký**.

~~~text
Nguồn hot:       A ---- B ---- C ---- D ---- E
Subscriber 1:          B ---- C ---- D ---- E
Subscriber 2:                         D ---- E
~~~

Ví dụ điển hình là luồng sự kiện từ thiết bị, giá thị trường, trạng thái kết nối, một nguồn message được chia sẻ hoặc một `Sinks.Many` do ứng dụng chủ động phát.

**Không suy luận loại nguồn chỉ từ tên `Flux` hoặc `Mono`.** Hai kiểu này mô tả số lượng phần tử, không xác định cold/hot. Một `Flux` có thể cold, hot hoặc trở thành nguồn chia sẻ/replay sau khi dùng operator phù hợp.

### 2.3. Bảng so sánh

| Thuộc tính | Cold | Hot |
| --- | --- | --- |
| Khi nào nguồn bắt đầu? | Thường khi mỗi subscriber đăng ký | Có thể bắt đầu độc lập với subscriber |
| Subscription mới | Thường tạo lần thực thi riêng | Có thể tham gia luồng đang chạy |
| Dữ liệu đã phát trước khi subscribe | Thường subscriber mới nhận từ đầu | Có thể bị bỏ lỡ nếu không có replay |
| Chia sẻ công việc upstream | Không mặc định | Có thể chia sẻ cùng một lần phát |
| Ví dụ | `Flux.range`, `Mono.fromCallable` | `Sinks.Many`, publisher sự kiện được chia sẻ |

## 3. Vì sao cần share, cache hoặc replay?

Giả sử nhiều request cùng cần cấu hình ứng dụng hoặc dữ liệu tham chiếu:

~~~text
Request A ----\
Request B -----+----> Tải dữ liệu từ service/database
Request C ----/
~~~

Nếu mỗi request subscribe vào cold publisher, hệ thống có thể gọi nguồn ba lần. Điều này có thể tạo:

- Nhiều I/O giống nhau và tăng tải database/API.
- Kết quả không đồng nhất nếu nguồn thay đổi giữa các lần gọi.
- Độ trễ tăng vì mỗi subscriber phải chờ một lần tải riêng.

Chia sẻ nguồn có thể biến luồng thành:

~~~text
                  +--> Subscriber A
Một upstream -----+--> Subscriber B
                  +--> Subscriber C
~~~

Tuy nhiên, chia sẻ một subscription **không đồng nghĩa** mọi subscriber đều nhận lịch sử giống nhau. Một subscriber đăng ký muộn có thể chỉ nhận phần tử từ thời điểm tham gia; muốn nhận lại dữ liệu cũ cần replay/cache.

Một số câu hỏi cần xác định trước:

1. Có cần chạy nguồn đúng một lần cho nhiều subscriber không?
2. Subscriber đến muộn cần nhận **toàn bộ lịch sử**, **N phần tử cuối**, hay **chỉ dữ liệu mới**?
3. Khi không còn subscriber, nguồn tiếp tục chạy hay được hủy?
4. Khi nguồn lỗi hoặc hoàn tất, subscriber tiếp theo nhận tín hiệu cũ hay tạo lần thực thi mới?
5. Có thể giữ bao nhiêu dữ liệu trong RAM và trong bao lâu?

Không có một operator duy nhất phù hợp cho tất cả các trường hợp.

## 4. `share` và `publish`: chia sẻ luồng mà không phát lại lịch sử

### 4.1. `publish()` tạo ConnectableFlux

`publish()` biến một `Flux` thành `ConnectableFlux`. Subscriber có thể đăng ký trước, rồi ứng dụng gọi `connect()` để bắt đầu upstream:

~~~java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A=" + value));
shared.subscribe(value -> System.out.println("B=" + value));

shared.connect();
~~~

Cả hai subscriber đã đăng ký trước khi kết nối nên nhận cùng các giá trị. `publish()` **không lưu lịch sử để phát lại cho subscriber đến sau**; nó multicast các tín hiệu trong lúc luồng đang hoạt động.

`ConnectableFlux` hữu ích khi ứng dụng muốn kiểm soát chính xác thời điểm bắt đầu nguồn. Nếu subscribe thêm sau khi nguồn đã phát một số giá trị, subscriber mới không tự nhận lại những giá trị trước đó.

### 4.2. `share()` cho trường hợp subscriber chồng lấp

`share()` là cách viết thuận tiện để chia sẻ một nguồn cho các subscriber cùng tham gia, tương đương mô hình `publish().refCount(1)` trong các phiên bản Reactor hiện hành:

~~~java
Flux<Event> events = source.share();
~~~

Nó hữu ích khi nhiều subscriber cùng theo dõi một nguồn đang chạy. `share()` **không phải cache lịch sử**; subscriber đến sau không được đảm bảo nhận những phần tử đã phát trước khi họ tham gia.

Vòng đời reconnect sau khi subscriber hủy hoặc nguồn kết thúc có thể phụ thuộc trạng thái và phiên bản/operator cụ thể. Không dùng `share()` như một hợp đồng lưu trữ kết quả đã hoàn tất; nếu cần replay kết quả, chọn `cache` hoặc `replay` có giới hạn rõ ràng.

### 4.3. `refCount` và `autoConnect`

Hai phương thức điều khiển kết nối thường gặp:

~~~java
Flux<Event> waitForTwo = source.publish().refCount(2);
Flux<Event> startAfterOne = source.publish().autoConnect(1);
~~~

- `refCount(2)` chỉ kết nối upstream khi có đủ hai subscriber. Khi số subscriber giảm dưới ngưỡng, nó có thể ngắt kết nối theo chính sách ref-count.
- `autoConnect(1)` kết nối sau subscriber đầu tiên; sau khi kết nối, nó không tự ngắt upstream chỉ vì subscriber giảm về 0.
- `refCount()` không đối số thường dùng ngưỡng một subscriber.
- `share()` là dạng chia sẻ tự động cho trường hợp ngưỡng một.

**Chọn theo lifecycle:** nguồn cần dừng khi không còn người nghe thường hợp với ref-count; nguồn cần tiếp tục chạy sau subscriber đầu tiên có thể dùng auto-connect. Cần đọc hợp đồng của overload và kiểm thử hành vi reconnect/terminal cho đúng phiên bản Reactor đang dùng.

## 5. `replay`: phát lại lịch sử cho subscriber đến muộn

`replay` tạo `ConnectableFlux` có khả năng giữ một phần lịch sử để subscriber đăng ký muộn có thể nhận lại:

~~~java
ConnectableFlux<Integer> replayLastTwo =
    Flux.range(1, 5).replay(2);
~~~

Nếu subscriber đầu nhận 1, 2, 3, 4, 5, subscriber sau có thể nhận lại hai phần tử cuối là 4, 5 (sau khi nguồn đã phát xong). Những overload thường dùng:

| Cách tạo | Chính sách lịch sử |
| --- | --- |
| `source.replay()` | Replay toàn bộ lịch sử được giữ |
| `source.replay(n)` | Giữ tối đa n phần tử gần nhất |
| `source.replay(ttl)` | Giữ phần tử theo khoảng thời gian TTL |
| `source.replay(n, ttl)` | Kết hợp giới hạn số lượng và thời gian khi overload tương ứng có sẵn |

`replay` trả về `ConnectableFlux`; nguồn chỉ bắt đầu khi được kết nối bằng `connect()`, hoặc qua `autoConnect`/`refCount`:

~~~java
Flux<Integer> lateSubscribers = Flux.range(1, 5)
    .replay(2)
    .autoConnect(1);
~~~

Đây là cách tạo nguồn replay tự kết nối khi có subscriber đầu tiên. Một subscriber đến muộn có thể nhận lại phần lịch sử còn trong buffer.

**Replay có giới hạn không phải lưu trữ bền vững.** Nếu process khởi động lại, dữ liệu trong bộ nhớ biến mất. Nếu nguồn phát nhanh và payload lớn, ngay cả replay một khoảng thời gian ngắn vẫn có thể dùng nhiều RAM.

## 6. `cache`: chia sẻ lần thực thi và lưu tín hiệu đã phát

### 6.1. `Flux.cache()`

`cache()` biến một Flux cold thành nguồn chia sẻ và replay. Subscriber đầu tiên kích hoạt upstream; các subscriber tiếp theo nhận các phần tử đã lưu và tín hiệu terminal:

~~~java
Flux<String> cached = remoteService.loadAll().cache();
~~~

Ở dạng không giới hạn, `Flux.cache()` có thể giữ toàn bộ lịch sử. Với nguồn hữu hạn nhỏ, điều đó có thể tiện lợi. Với nguồn dài hoặc không bao giờ kết thúc, **bộ nhớ có thể tăng liên tục**.

### 6.2. Giới hạn số phần tử

~~~java
Flux<Event> lastHundred = source.cache(100);
~~~

`cache(100)` giữ tối đa 100 phần tử gần nhất cho subscriber đến muộn. Subscriber đầu tiên vẫn nhận luồng đang phát theo hợp đồng của nguồn; giới hạn history điều chỉnh những gì được lưu để replay.

Đối với một Flux không bao giờ kết thúc, giới hạn history theo số phần tử đặc biệt quan trọng. Nhưng 100 phần tử có thể là 100 đối tượng nhỏ hoặc 100 payload rất lớn; số lượng không phải giới hạn byte chính xác.

### 6.3. Giới hạn thời gian (TTL)

~~~java
Flux<Event> recent = source.cache(
    java.time.Duration.ofMinutes(2)
);
~~~

TTL giới hạn tuổi lưu giữ của tín hiệu. Một overload kết hợp history và TTL cho phép đặt cả hai ranh giới:

~~~java
Flux<Event> bounded = source.cache(
    500, java.time.Duration.ofMinutes(2)
);
~~~

Ở đây history tối đa 500 phần tử và TTL hai phút. Các API Reactor có overload TTL tương ứng cho `Flux`/`Mono`; hãy kiểm tra Javadoc đúng phiên bản dependency của dự án khi chọn chữ ký cụ thể.

**TTL không thay thế giới hạn số phần tử.** Nếu nguồn phát hàng trăm nghìn sự kiện mỗi giây, hai phút lịch sử vẫn có thể rất lớn. Kết hợp TTL với giới hạn history khi cần ngân sách bộ nhớ dễ dự đoán hơn.

### 6.4. `Mono.cache()`

Với `Mono`, cache thường lưu một kết quả đơn lẻ hoặc terminal signal:

~~~java
Mono<Config> cachedConfig = configService.load().cache();
~~~

Những subscriber cùng dùng instance này có thể chia sẻ một lần thực thi và nhận lại kết quả đã cache. `Mono.cache()` có thể cache cả:

- Một giá trị được phát thành công.
- Completion rỗng (`Mono.empty()`).
- Lỗi (`Mono.error(...)`).

Vì vậy, nếu lần tải cấu hình đầu tiên thất bại và lỗi được cache, subscriber sau có thể nhận lại lỗi đó thay vì tự động gọi nguồn lại. TTL hoặc chính sách cache theo loại tín hiệu có thể cần thiết để tránh giữ lỗi quá lâu.

### 6.5. `cache` khác `replay` ở điểm nào?

| Tiêu chí | `cache` | `replay` |
| --- | --- | --- |
| API điển hình | `Flux.cache(...)` / `Mono.cache(...)` | `ConnectableFlux.replay(...)` |
| Bắt đầu upstream | Tự kích hoạt khi có subscriber đầu tiên | Chủ động gọi `connect` hoặc dùng `autoConnect`/`refCount` |
| Subscriber đến muộn | Nhận lịch sử đã cache theo giới hạn | Nhận lịch sử còn trong replay buffer |
| Điều khiển kết nối | Đơn giản, tự quản lý | Rõ ràng hơn qua ConnectableFlux |
| Giới hạn lịch sử | History và/hoặc TTL theo overload | History và/hoặc TTL theo overload |
| Trường hợp phù hợp | Chia sẻ kết quả/luồng đã tải | Điều khiển multicast và replay theo lifecycle |

Với nhu cầu thông thường “tải một lần và chia sẻ kết quả cho nhiều subscriber”, `cache` thường đơn giản hơn. Với luồng sự kiện dài hạn cần điều khiển thời điểm connect/disconnect, `replay` hoặc `publish` có thể phù hợp hơn.

## 7. `Sinks.Many`: chủ động phát và chọn chính sách replay

`Sinks` là API để ứng dụng chủ động phát tín hiệu vào Reactor. Nó hữu ích khi nối callback imperative, event producer hoặc thành phần nội bộ vào một `Flux`.

Ví dụ replay giữ ba phần tử cuối:

~~~java
Sinks.Many<Event> sink = Sinks.many()
    .replay()
    .limit(3);

Flux<Event> events = sink.asFlux();
~~~

- `sink.tryEmitNext(event)` gửi một phần tử.
- `sink.tryEmitComplete()` gửi tín hiệu hoàn tất.
- `sink.tryEmitError(error)` gửi lỗi.
- `sink.asFlux()` cung cấp publisher để subscriber theo dõi.

Một sink replay không giới hạn có thể giữ toàn bộ lịch sử; `replay().limit(3)` chỉ giữ ba phần tử gần nhất. Khi dùng `tryEmit...`, kiểm tra `EmitResult`; không bỏ qua lỗi phát tín hiệu như overflow, sink đã terminal hoặc nhiều producer đồng thời không được serialize.

Các loại sink có ý nghĩa khác nhau:

| Sink | Hành vi khái quát |
| --- | --- |
| `many().unicast()` | Một subscriber, có queue cho dữ liệu chờ theo cấu hình |
| `many().multicast()` | Chia sẻ tín hiệu tới các subscriber hiện tại; chính sách backpressure tùy biến thể |
| `many().replay().all()` | Phát lại toàn bộ lịch sử; cần cân nhắc RAM |
| `many().replay().limit(n)` | Phát lại n phần tử gần nhất |

**Không nhầm sink replay với một message broker bền vững.** Sink tồn tại trong process, không cung cấp persistence, replication hay consumer offset sau restart.

## 8. Ví dụ Java 17 chạy được: cold, cache và replay

Ví dụ sau minh họa ba hành vi với đầu ra xác định:

1. Cold source được subscribe hai lần, nên factory chạy hai lần.
2. Cache chỉ subscribe upstream một lần và subscriber sau nhận hai phần tử cuối.
3. Replay buffer giữ hai phần tử cuối cho subscriber đến sau.

Tạo file `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'CacheReplayDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo file `src/main/java/CacheReplayDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class CacheReplayDemo {
    public static void main(String[] args) {
        AtomicInteger subscriptions = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            int run = subscriptions.incrementAndGet();
            System.out.println("cold source subscription #" + run);
            return Flux.just(1, 2, 3);
        });

        System.out.println(
            "cold first = " + cold.collectList().block()
        );
        System.out.println(
            "cold second = " + cold.collectList().block()
        );

        Flux<Integer> cached = cold.cache(2);
        System.out.println(
            "cache first = " + cached.collectList().block()
        );
        System.out.println(
            "cache late = " + cached.collectList().block()
        );

        ConnectableFlux<Integer> replay =
            Flux.range(1, 3).replay(2);

        replay.subscribe(value ->
            System.out.println("replay first = " + value)
        );
        replay.connect();
        replay.subscribe(value ->
            System.out.println("replay late = " + value)
        );
    }
}
~~~

Chạy `gradle run` hoặc Gradle Wrapper: `./gradlew run` (Windows: `gradlew.bat run`). Phần stdout của chương trình, không tính log Gradle:

~~~text
cold source subscription #1
cold first = [1, 2, 3]
cold source subscription #2
cold second = [1, 2, 3]
cold source subscription #3
cache first = [1, 2, 3]
cache late = [2, 3]
replay first = 1
replay first = 2
replay first = 3
replay late = 2
replay late = 3
~~~

**Giải thích:**

- `Flux.defer` tăng bộ đếm mỗi khi có subscriber mới, chứng minh cold source chạy riêng hai lần.
- `cold.cache(2)` là một publisher mới. Subscriber đầu tiên của cache làm upstream cold được subscribe lần thứ ba và nhận cả 1, 2, 3.
- Cache giữ hai phần tử cuối. Subscriber tiếp theo không tạo subscription thứ tư; họ nhận lại 2, 3 từ cache.
- `replay(2)` có subscriber đầu đăng ký trước `connect()`. Khi nguồn đồng bộ phát 1, 2, 3, subscriber đầu nhận đủ. Subscriber đến sau nhận lại 2, 3.
- `block()` ở đây chỉ dùng trong chương trình console để thu kết quả. Trong WebFlux controller/service, trả publisher để framework subscribe; không dùng `block()` trên event loop.

Đây là ví dụ độc lập dùng Java 17+ và Reactor Core. Trong dự án Spring Boot, nên để Spring Boot BOM quản lý phiên bản Reactor tương thích thay vì ghim phiên bản riêng.

## 9. Ví dụ `Sinks.replay().limit` cho subscriber đến muộn

Đoạn sau là ví dụ độc lập về sink replay, có thể đặt trong `main` sau khi import `reactor.core.publisher.Sinks`:

~~~java
Sinks.Many<Integer> sink = Sinks.many().replay().limit(2);

sink.tryEmitNext(10).orThrow();
sink.tryEmitNext(20).orThrow();
sink.tryEmitNext(30).orThrow();
sink.tryEmitComplete().orThrow();

System.out.println(
    "sink late = " + sink.asFlux().collectList().block()
);
~~~

Output:

~~~text
sink late = [20, 30]
~~~

Sink đã phát 10, 20, 30 và hoàn tất trước khi subscriber đăng ký. Vì replay limit bằng 2, subscriber muộn chỉ nhận 20 và 30 rồi completion.

Trong ứng dụng thực tế, không bỏ qua kết quả `tryEmit...`. `orThrow()` sẽ ném exception nếu emission thất bại; với luồng event có nhiều producer, cần quyết định serialization và cách xử lý `EmitResult`. Không phát đồng thời tùy tiện vào sink không hỗ trợ concurrent emission.

## 10. Chính sách retention: giới hạn cái gì và tại sao?

Một cache/replay buffer tiêu thụ bộ nhớ theo số phần tử, kích thước payload và thời gian lưu giữ. Khi thiết kế, cần tách các loại giới hạn:

### 10.1. Giới hạn theo số phần tử

Ví dụ `cache(100)` hoặc `replay(100)` giữ tối đa 100 phần tử gần nhất. Đây là giới hạn dễ dự đoán theo count, nhưng **không phải giới hạn byte**.

100 đối tượng nhỏ có thể nhẹ; 100 đối tượng chứa ảnh, JSON lớn hoặc danh sách lồng nhau có thể rất nặng. Ước lượng bộ nhớ bằng kích thước thực tế của object graph, không chỉ độ dài chuỗi JSON.

### 10.2. Giới hạn theo thời gian

TTL như hai phút phù hợp khi subscriber muộn chỉ cần lịch sử gần đây. Nhưng với nguồn phát nhanh, số phần tử trong hai phút có thể tăng rất lớn. TTL không bảo đảm một ngân sách RAM cố định.

### 10.3. Kết hợp count và TTL

Khi cần cả freshness và giới hạn lịch sử, chọn overload kết hợp history/TTL phù hợp với Reactor version. Ví dụ:

~~~java
Flux<Event> recent = eventSource.cache(
    1_000, java.time.Duration.ofMinutes(1)
);
~~~

Subscriber đến muộn chỉ cần nhận phần lịch sử còn trong giới hạn count và TTL. Hãy kiểm tra chính sách chính xác của overload được dùng trong version dự án; nếu yêu cầu có giới hạn byte nghiêm ngặt, dùng cache chuyên dụng có weight/size eviction thay vì chỉ dựa trên Reactor history count.

### 10.4. Giới hạn vòng đời

Hỏi rõ cache giữ dữ liệu đến khi nào:

- Đến khi nguồn hoàn tất?
- Đến khi TTL hết?
- Khi không còn subscriber?
- Khi một cấu hình hoặc phiên bản dữ liệu thay đổi?
- Khi tenant/session/user bị xóa?

`cache` của Reactor không phải một key-value cache có eviction theo key hoặc chính sách phân vùng tenant. Nếu cần cache nhiều ID, TTL, maximum size, refresh, metrics và invalidation, cân nhắc Caffeine hoặc hệ thống cache chuyên dụng.

### 10.5. Giới hạn dung lượng theo byte

Reactor cache/replay theo history count và/hoặc thời gian không trực tiếp đảm bảo giới hạn chính xác theo byte. Với payload lớn, hãy cân nhắc:

- Chỉ cache DTO nhỏ hoặc ID, không cache toàn bộ blob.
- Dùng cache chuyên dụng có weight function và maximum weight.
- Giới hạn payload trước khi đưa vào buffer.
- Đưa lịch sử dài hạn sang database/object storage/message broker.

## 11. Terminal signals cũng có thể được cache

Cache không chỉ giữ `onNext`. Nó còn có thể giữ tín hiệu terminal của nguồn:

| Nguồn ban đầu | Subscriber sau nhận được |
| --- | --- |
| `Flux.just(1, 2).cache()` đã hoàn tất | Các giá trị đã lưu, rồi `onComplete` |
| `Mono.empty().cache()` | Completion rỗng được cache |
| `Mono.error(ex).cache()` | Lỗi được cache/replay theo TTL/chính sách của API |
| `Flux` chưa hoàn tất | Lịch sử đang giữ; subscriber có thể tiếp tục nhận tín hiệu mới nếu nguồn vẫn hoạt động |

Điều này quan trọng khi cache một request HTTP hoặc truy vấn database. Nếu lần đầu bị lỗi tạm thời, `Mono.cache()` không tự biết đó là lỗi tạm thời; subscriber sau có thể nhận lại lỗi cũ. Nếu cần retry trước khi cache, đặt retry trong upstream:

~~~java
Mono<Config> resilient = configService.load()
    .retryWhen(reactor.util.retry.Retry.max(2))
    .cache();
~~~

Ở đây cache lưu tín hiệu sau khi chính sách retry kết thúc. Nếu retry vẫn thất bại, lỗi cuối cùng cũng có thể được cache. Đừng dùng retry vô hạn trước cache; subscriber đầu có thể chờ mãi và tài nguyên bị giữ.

Ngược lại:

~~~java
Mono<Config> perSubscriberRetry = configService.load()
    .cache()
    .retryWhen(reactor.util.retry.Retry.max(2));
~~~

Retry đặt sau cache có thể subscribe lại vào **cùng kết quả đã cache**; nếu lỗi đang được cache, lần retry không nhất thiết gọi lại nguồn. Muốn thực sự gọi lại nguồn, phải thiết kế TTL/invalidation hoặc tạo publisher/cache instance mới đúng vòng đời.

### Empty result cũng là kết quả cần cân nhắc

Nếu `Mono<User>` rỗng vì không tìm thấy user và được cache lâu, bản ghi mới được tạo sau đó có thể vẫn “không thấy” cho subscriber đến muộn cho đến khi TTL/invalidation cho phép tải lại. Đây là tình huống stale negative cache.

Khi cache kết quả tìm kiếm, hãy xác định TTL riêng cho value và empty nếu API hỗ trợ; hoặc dùng cache chuyên dụng có chính sách negative caching rõ ràng. Không giữ “không tồn tại” quá lâu nếu dữ liệu có thể xuất hiện trong thời gian ngắn.

## 12. Cache/replay, backpressure và subscriber chậm

Backpressure (`request(n)`) điều tiết nhu cầu của subscriber, nhưng **không thay thế chính sách retention**. Một nguồn hot có thể phát độc lập; cache/replay giữ lịch sử trong bộ nhớ để subscriber muộn nhận lại.

Khi subscriber chậm:

- Multicast không replay có thể phải điều phối demand giữa subscriber hiện tại; hành vi cụ thể phụ thuộc operator/sink.
- Replay/cache có thể giữ dữ liệu cho subscriber đến muộn, nhưng buffer có giới hạn hoặc không giới hạn tùy cấu hình.
- Sink có chính sách overflow/backpressure riêng; emission có thể thất bại nếu buffer không nhận thêm được.
- Không có operator nào tự bảo đảm một nguồn ngoài hệ thống chậm lại nếu nguồn đó không hỗ trợ demand.

Không nên dùng `cache()` không giới hạn để “giữ cho khỏi mất event” trên luồng vô hạn. Nếu tốc độ phát lớn hơn khả năng tiêu thụ trong thời gian dài, dữ liệu lưu giữ sẽ tăng và cuối cùng gây áp lực heap/GC/OOM.

### Chọn chính sách cho từng loại dữ liệu

| Dữ liệu | Hướng phù hợp | Lý do |
| --- | --- | --- |
| Cấu hình nhỏ, tải một lần khi khởi động | `Mono.cache()` với invalidation/TTL phù hợp | Chia sẻ một kết quả nhỏ |
| Danh mục hữu hạn, ít thay đổi | `Flux.cache(history)` nếu tổng kích thước được kiểm soát | Tránh truy vấn lặp |
| Dashboard cần vài sự kiện mới nhất | `replay(n)` hoặc `Sinks.replay().limit(n)` | Subscriber mới có snapshot gần đây |
| Luồng telemetry lớn, chỉ cần mẫu gần nhất | Buffer giới hạn hoặc chiến lược drop/latest phù hợp | Tránh giữ mọi sự kiện |
| Audit/event phải lưu bền vững | Database hoặc message broker có persistence | Không phụ thuộc RAM của một process |
| Kết quả HTTP GET cần chia sẻ ngắn hạn | `Mono.cache(TTL)` hoặc cache chuyên dụng theo key | Tránh gọi lặp trong khoảng TTL |
| Kết quả nhạy cảm theo user/tenant | Cache theo key và scope bảo mật rõ | Tránh rò dữ liệu giữa người dùng |

## 13. Cache theo request/key: tránh chia sẻ nhầm dữ liệu

Một publisher đã gọi `cache()` là một instance cụ thể. Nếu giữ nó trong field singleton, mọi subscriber dùng field đó có thể nhận cùng một kết quả. Điều này hữu ích cho cấu hình toàn cục, nhưng **nguy hiểm nếu kết quả phụ thuộc user, tenant hoặc tham số request**.

Ví dụ rủi ro:

~~~java
@Service
class UserService {
    private final Mono<User> cachedUser =
        repository.findById("some-user").cache();
}
~~~

Đây là ví dụ minh họa field singleton. Mọi caller sẽ dùng cùng một user; nếu định danh thực tế phải theo request, đây là thiết kế sai.

Cũng cần cẩn thận khi viết:

~~~java
Mono<User> find(String id) {
    return repository.findById(id).cache();
}
~~~

Mỗi lần gọi `find(id)` tạo một cache instance mới, nên nó chỉ chia sẻ giữa subscriber dùng **chính instance được trả về**. Hai lần gọi `find("u1")` độc lập không tự chia sẻ cache. Muốn cache theo key giữa các request, dùng cache có key (ví dụ Caffeine) hoặc một map/cache service có eviction, TTL, concurrency và invalidation rõ ràng.

Trong ứng dụng đa tenant, key phải bao gồm phạm vi tenant/authorization phù hợp. Không cache dữ liệu cá nhân theo một key quá chung như `"profile"` nếu nhiều người dùng có thể nhận kết quả khác nhau.

## 14. Invalidation, refresh và stale data

Reactor `cache` không phải một cache service đầy đủ với thao tác xóa key tùy ý. Khi dữ liệu thay đổi, cần xác định cách tạo publisher/cache mới hoặc dùng lớp cache ngoài có hỗ trợ invalidation.

Một số chiến lược:

1. **TTL:** dữ liệu hết hạn theo thời gian; đơn giản nhưng có cửa sổ stale.
2. **Versioned key:** khóa cache chứa version/config revision; thay version tạo cache entry mới.
3. **Event invalidation:** khi dữ liệu thay đổi, xóa/đánh dấu cache entry theo key trong cache service.
4. **Refresh-ahead:** tải dữ liệu mới trước khi hết hạn; cần quản lý một refresh publisher và xử lý lỗi riêng.
5. **Không cache:** khi tính đúng đắn quan trọng hơn chi phí truy vấn.

Không giữ một publisher `cache()` trong field rồi kỳ vọng có thể gọi `invalidate()` như Caffeine. Nếu cần invalidation phức tạp, dùng cache chuyên dụng và chỉ đưa publisher vào pipeline khi lấy giá trị.

**Stale-while-revalidate** là một chính sách sản phẩm/ứng dụng: trả giá trị cũ trong lúc tải mới. `cache` tự nó không định nghĩa đầy đủ chính sách này; phải thiết kế trạng thái giá trị cũ/mới, refresh, lỗi refresh và đồng bộ cập nhật.

## 15. Kiểm thử với StepVerifier

Thêm file `src/test/java/CacheReplayTest.java` vào dự án Gradle ở mục 8. Dependency `reactor-test` và JUnit đã có trong `build.gradle`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheReplayTest {

    @Test
    void coldSourceRunsForEachSubscription() {
        AtomicInteger calls = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            calls.incrementAndGet();
            return Flux.just(1, 2, 3);
        });

        StepVerifier.create(cold)
            .expectNext(1, 2, 3)
            .verifyComplete();

        StepVerifier.create(cold)
            .expectNext(1, 2, 3)
            .verifyComplete();

        assertEquals(2, calls.get());
    }

    @Test
    void cacheSharesUpstreamAndReplaysLimitedHistory() {
        AtomicInteger calls = new AtomicInteger();

        Flux<Integer> cached = Flux.defer(() -> {
            calls.incrementAndGet();
            return Flux.just(1, 2, 3, 4);
        }).cache(2);

        StepVerifier.create(cached)
            .expectNext(1, 2, 3, 4)
            .verifyComplete();

        StepVerifier.create(cached)
            .expectNext(3, 4)
            .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void replayConnectableSendsHistoryToLateSubscriber() {
        ConnectableFlux<Integer> replay =
            Flux.range(1, 4).replay(2);

        StepVerifier.create(replay)
            .then(replay::connect)
            .expectNext(1, 2, 3, 4)
            .verifyComplete();

        StepVerifier.create(replay)
            .expectNext(3, 4)
            .verifyComplete();
    }

    @Test
    void monoCacheAlsoCachesAnErrorSignal() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> cachedError = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.error(
                new IllegalStateException("source failed")
            );
        }).cache();

        StepVerifier.create(cachedError)
            .expectErrorMessage("source failed")
            .verify();

        StepVerifier.create(cachedError)
            .expectErrorMessage("source failed")
            .verify();

        assertEquals(1, calls.get());
    }
}
~~~

Chạy `gradle test` hoặc Gradle Wrapper tương ứng. Bốn test được kỳ vọng **PASS**:

- Cold source được subscribe hai lần và factory chạy hai lần.
- Cache source chỉ chạy một lần; subscriber sau chỉ nhận hai phần tử cuối.
- Replay connectable giữ hai phần tử cuối cho subscriber đăng ký sau khi nguồn hoàn tất.
- `Mono.cache()` chia sẻ cả tín hiệu lỗi; subscription sau nhận lỗi đã cache mà không gọi lại supplier.

Test replay dùng nguồn đồng bộ hữu hạn. Với nguồn vô hạn hoặc nguồn bất đồng bộ, cần kiểm thử riêng thời điểm connect, subscriber đến muộn, cancellation, TTL và overflow. Không dùng `Thread.sleep` để phỏng đoán thời điểm dữ liệu xuất hiện.

## 16. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `cache()` mặc định cho Flux vô hạn | Lịch sử có thể tăng không giới hạn | Chọn `cache(history)` hoặc TTL và tính cả payload |
| Nghĩ `share()` phát lại dữ liệu cũ | Subscriber đến muộn có thể bỏ lỡ phần tử trước đó | Dùng `replay`/`cache` với retention cụ thể |
| Dùng `replay()` không giới hạn trên stream dài hạn | Heap tăng theo toàn bộ lịch sử | Giới hạn count/TTL hoặc lưu ngoài process |
| Cho rằng cache là distributed/durable | Restart process làm mất lịch sử; instance khác không chia sẻ | Database, broker hoặc cache phân tán |
| Cache lỗi vô thời hạn | Lỗi tạm thời được phát lại cho subscriber sau | TTL/định nghĩa error policy, retry trước cache nếu phù hợp |
| Không cache negative result có chủ đích | Cache miss có thể gây tải truy vấn lặp | Negative caching với TTL ngắn nếu hợp đồng cho phép |
| Giữ cache theo user trong singleton field | Có thể trả dữ liệu của user khác | Cache theo key/tenant và scope xác thực |
| Nghĩ history=100 là giới hạn 100 KB | Payload lớn có thể tiêu tốn RAM đáng kể | Cache có maximum weight hoặc giới hạn payload |
| Nhầm connect, autoConnect, refCount | Nguồn có thể chạy quá sớm hoặc không dừng như dự kiến | Thiết kế và test lifecycle subscriber |
| Bỏ qua kết quả tryEmit... | Emission có thể thất bại mà ứng dụng không biết | Kiểm tra tryEmit... và xử lý từng loại failure |
| Dùng cache thay cho backpressure | Buffer vẫn có thể đầy và upstream vẫn có thể phát nhanh | Quản lý demand, queue, concurrency và retention riêng |
| Dùng cache để thay cho transaction | Nhiều subscriber thấy cùng kết quả nhưng side effect không nguyên tử | Dùng transaction/idempotency và persistence phù hợp |

## 17. Checklist chọn chiến lược

Trước khi đưa `cache` hoặc `replay` vào pipeline, hãy trả lời:

1. **Nguồn là cold hay hot?** Mỗi subscriber có cần một lần gọi mới hay cần chia sẻ một lần thực thi?
2. **Subscriber muộn cần nhận gì?** Không có lịch sử, giá trị cuối, N sự kiện gần nhất hay toàn bộ lịch sử?
3. **Giới hạn retention nào?** Count, TTL, byte/weight, hay kết hợp? Nếu nguồn không bao giờ kết thúc, phải có giới hạn hữu hạn.
4. **Terminal signal có nên được giữ?** Cache lỗi/empty có thể làm dữ liệu cũ tiếp tục xuất hiện; xác định TTL/invalidation.
5. **Ai quản lý kết nối?** `cache` tự kích hoạt; `ConnectableFlux` cần connect/autoConnect/refCount.
6. **Điều gì xảy ra khi không còn subscriber?** Nguồn có cần tiếp tục chạy hay được phép dừng?
7. **Dữ liệu có theo user/tenant không?** Key và quyền truy cập phải phân tách; tránh cache chung dữ liệu nhạy cảm.
8. **Dữ liệu có cần sống qua restart hoặc chia sẻ nhiều instance?** Nếu có, dùng persistence/distributed cache/broker phù hợp.
9. **Đã đo memory và tải chưa?** Kiểm tra số phần tử, kích thước payload, tốc độ phát, số subscriber, GC và p95/p99.
10. **Đã test subscriber đến muộn và lỗi chưa?** Kiểm tra replay history, TTL, terminal error, cancellation và reconnect.

**Ghi nhớ:** cold publisher thường chạy riêng cho từng subscriber; hot publisher có thể phát trước khi subscriber đăng ký. `share/publish` chia sẻ luồng hiện tại, `replay` và `cache` giữ một phần lịch sử để phát lại. Hãy chọn giới hạn **số phần tử, thời gian và dung lượng thực tế** trước khi cache một nguồn dài hạn. Reactor cache/replay là cơ chế trong bộ nhớ của process, không thay thế persistence hoặc cache service có eviction theo key.

## Tài liệu tham khảo

- Project Reactor Reference — Hot Versus Cold: https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html
- Project Reactor Reference — Broadcasting to Multiple Subscribers with ConnectableFlux: https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html
- Reactor `Flux` API — `cache`, `replay`, `publish`, `share`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor `Mono` API — `cache` and TTL variants: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor `Sinks` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Streams specification: https://www.reactive-streams.org/
