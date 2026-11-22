# Phân biệt nguồn cold với nguồn hot trong Project Reactor

## 1. Vì sao phải phân biệt?

Trong Spring WebFlux, `Mono<T>` và `Flux<T>` mô tả một chuỗi tín hiệu reactive. Nhưng khi có nhiều Subscriber đăng ký vào cùng Publisher, một câu hỏi quan trọng xuất hiện: **mỗi Subscriber có kích hoạt một lần xử lý dữ liệu mới, hay tất cả cùng quan sát một nguồn dữ liệu đang chạy?**

Project Reactor gọi hai mô hình phổ biến là **cold publisher** và **hot publisher**:

- Nguồn **cold** bắt đầu công việc cho từng subscription. Mỗi Subscriber thường có một lượt phát độc lập; không có subscription thì công việc chưa bắt đầu.
- Nguồn **hot** có vòng đời phát dữ liệu độc lập hơn với từng Subscriber. Subscriber đến muộn thường chỉ nhận những tín hiệu phát sau thời điểm họ đăng ký; một số nguồn hot có thể lưu và phát lại lịch sử.

Đây là khác biệt về **thời điểm tạo/phát dữ liệu và cách chia sẻ chuỗi tín hiệu**. Nó không đồng nghĩa cold = đồng bộ, hot = bất đồng bộ, cold = một thread hay hot = nhiều thread. Một Publisher cold có thể gọi HTTP bất đồng bộ; một hot sink có thể được phát đồng bộ ngay trên thread gọi nó.

Sau bài này, bạn có thể nhận diện nguồn cold/hot, giải thích hiệu ứng của `just` và `defer`, chuyển một nguồn cold thành multicast bằng `publish`/`share`, chọn replay/cache khi cần dữ liệu lịch sử, phát sự kiện với `Sinks.Many`, áp dụng trong WebFlux và kiểm thử hành vi của Subscriber đến sớm/đến muộn.

## 2. Cold publisher: mỗi subscription khởi động một lượt mới

Một cold sequence tạo dữ liệu mới cho mỗi Subscriber. Khi hai Subscriber đăng ký cùng một nguồn cold, mỗi Subscriber có một lần subscription riêng đến upstream. Với nguồn hữu hạn, cả hai thường nhìn thấy toàn bộ chuỗi từ đầu.

Ví dụ:

~~~java
Flux<String> source = Flux.just("blue", "green", "orange")
        .map(String::toUpperCase);

source.subscribe(value -> System.out.println("S1: " + value));
source.subscribe(value -> System.out.println("S2: " + value));
~~~

Stdout:

~~~text
S1: BLUE
S1: GREEN
S1: ORANGE
S2: BLUE
S2: GREEN
S2: ORANGE
~~~

Mỗi lần `subscribe` chạy pipeline cold một lần nữa. Điều này rất hữu ích khi nguồn đại diện cho một thao tác cần thực hiện cho từng người dùng: gọi HTTP, truy vấn repository reactive, đọc file, tính toán theo request hoặc tạo một sequence mới.

### 2.1. Các nguồn thường dùng theo kiểu cold

- `Flux.range(start, count)`: mỗi subscription phát lại dãy số.
- `Flux.fromIterable(iterable)`: mỗi subscription tạo iterator và duyệt nguồn.
- `Mono.fromCallable(callable)` / `Flux.fromIterable` kết hợp với `defer`: thực thi phần tạo giá trị khi subscribe.
- `Mono.defer(supplier)` / `Flux.defer(supplier)`: gọi supplier cho mỗi subscription để lấy Publisher mới.
- `WebClient` request pipeline: khi được tạo và trả về dưới dạng Publisher mà chưa subscribe, request chưa được gửi; mỗi subscription thông thường khởi chạy một lần request mới.

Không nên suy luận rằng **mọi nguồn cold luôn tạo bản sao sâu của dữ liệu**. Ví dụ, `Flux.fromIterable(sharedList)` có thể duyệt cùng một List object ở nhiều subscription; nếu List bị sửa đồng thời thì vẫn có vấn đề thread safety. Cold nói về việc tạo/phát chuỗi theo từng subscription, không phải cơ chế clone mọi object Java.

### 2.2. Dùng defer khi cần tính lại giá trị theo subscription

`Flux.just(value)` nhận giá trị đã được Java tính tại thời điểm lắp ghép. Nếu biểu thức bên trong là lời gọi hàm, hàm đó chạy trước khi `just` được tạo:

~~~java
Mono<String> captured = Mono.just(loadCurrentValue());
~~~

`loadCurrentValue()` chạy ngay tại assembly. Subscriber sau nhận giá trị đã chụp đó.

Nếu muốn mỗi subscription gọi lại thao tác:

~~~java
Mono<String> fresh = Mono.defer(
        () -> Mono.just(loadCurrentValue())
);
~~~

Bây giờ `loadCurrentValue()` chạy trong supplier của từng subscription. Nếu hàm có thể trả `null`, hãy dùng `Mono.justOrEmpty(loadCurrentValue())` bên trong `defer`; `Mono.just(null)` không hợp lệ.

**Một nuance của Reactor:** tài liệu Reactor xếp `just` vào nhóm một số ít operator có tính hot vì nó chụp giá trị ở assembly và phát lại giá trị đã chụp cho Subscriber đến sau. Điều đó không có nghĩa `just` tự gọi `onNext` trước khi có subscription; tín hiệu vẫn được gửi trong subscription. Điểm cần nhớ là giá trị **không được tính lại** cho mỗi Subscriber. `defer` là cách trì hoãn việc tạo nguồn để biến thao tác này thành per-subscription.

### 2.3. Ví dụ HTTP và repository

Trong service:

~~~java
Mono<User> findUser(String id) {
    return webClient.get()
            .uri("/users/{id}", id)
            .retrieve()
            .bodyToMono(User.class);
}
~~~

Đây là dạng pipeline lazy: khi caller subscribe, WebClient thực hiện request. Nếu cùng Mono được subscribe hai lần, thông thường sẽ có hai request. Nếu muốn nhiều downstream cùng chia sẻ một request đang chạy, phải chủ động dùng cơ chế chia sẻ hoặc cache; không tự giả định Mono tự memoize kết quả.

Với một API blocking trả về object ngay lúc gọi:

~~~java
// Thao tác blocking xảy ra ngay tại assembly:
Mono<User> wrong = Mono.just(legacyDao.findUser(id));

// Hoãn thao tác đến subscription và chuyển blocking work khỏi event-loop:
Mono<User> adapted = Mono.fromCallable(() -> legacyDao.findUser(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đoạn trên minh họa nguồn blocking; trong hệ thống thực tế nên ưu tiên driver/client reactive. `fromCallable` giúp trì hoãn và chuyển việc thực thi theo subscription, còn `subscribeOn` chọn scheduler phù hợp. Cold không tự có nghĩa là non-blocking.

## 3. Hot publisher: nguồn có nhịp phát riêng

Hot sequence không bắt đầu lại toàn bộ lịch sử cho từng Subscriber. Nguồn có thể tiếp tục phát khi Subscriber đến hoặc rời đi; Subscriber mới thường chỉ nhận dữ liệu được phát sau lúc họ đăng ký.

Ví dụ điển hình:

- Sự kiện từ thiết bị, cảm biến hoặc message broker đang chạy.
- Bảng giá hoặc tỷ giá được cập nhật liên tục.
- Thông báo trong ứng dụng được broadcast tới các phiên WebSocket/SSE.
- Một `Sinks.Many` nhận sự kiện do ứng dụng chủ động đẩy vào.
- Một nguồn cold được chuyển thành hot bằng `share()` hoặc `replay()` sau khi bắt đầu subscription.

~~~text
Thời gian ───────────────────────────────────────────►

Nguồn phát:       E1       E2       E3       E4
Subscriber A:     ├────────────── nhận E1,E2,E3,E4
Subscriber B:                       ├────── nhận E3,E4
Subscriber C:                                  ├── nhận E4

B và C không tự nhận lại E1,E2 nếu nguồn không replay lịch sử.
~~~

Một hot publisher có thể chạy khi không có Subscriber, nhưng không phải mọi loại hot source đều lưu dữ liệu trong khoảng không có người nghe. Multicast sink thường chỉ chuyển các phần tử mới đến những Subscriber hiện tại; replay sink mới lưu lịch sử theo cấu hình.

### 3.1. Hot không đồng nghĩa với nhiều thread

`Sinks.Many` có thể được gọi đồng bộ:

~~~java
sink.tryEmitNext("event");
~~~

Sự kiện được chuyển tới các Subscriber đang nghe ngay trong đường gọi, nếu điều kiện demand/overflow cho phép. Một nguồn hot khác có thể được phát từ callback I/O hoặc scheduler. Tính hot/cold và việc chọn thread là hai trục độc lập.

### 3.2. Subscriber đến muộn và lịch sử

Với hot multicast không replay:

- Subscriber đã đăng ký trước khi E1 được phát có thể nhận E1.
- Subscriber đăng ký sau E1 thường chỉ nhận E2 trở đi.
- Nếu nguồn đã complete trước khi Subscriber đến, Subscriber mới thường nhận terminal theo hợp đồng của nguồn; nó không tự nhận lại dữ liệu đã mất.

Nếu nghiệp vụ cần Subscriber mới nhìn thấy lịch sử, chọn replay/cache hoặc lưu sự kiện bền vững. Không nên coi một hot stream thông thường là event log có thể phát lại.

## 4. So sánh cold và hot

| Tiêu chí | Cold | Hot |
| --- | --- | --- |
| Thời điểm công việc bắt đầu | Khi có subscription | Có thể độc lập với subscription |
| Subscriber thứ hai | Thường kích hoạt một lượt mới | Thường tham gia nguồn đang chạy |
| Lịch sử trước lúc subscribe | Nguồn cold phát lại sequence từ đầu | Thường không nhận lịch sử nếu không replay |
| Nguồn điển hình | HTTP request, truy vấn reactive, range, iterable, defer | Sink multicast, event bus, shared live feed |
| Tài nguyên upstream | Có thể nhân lên theo Subscriber | Có thể dùng chung một nguồn upstream |
| Hủy một Subscriber | Thường hủy lượt upstream riêng đó nếu không có chia sẻ | Thường chỉ rời nhóm; nguồn còn có thể phục vụ Subscriber khác |
| Câu hỏi thiết kế | Mỗi request có cần chạy lại không? | Ai sở hữu nguồn, ai được nhận sự kiện và có replay không? |

Bảng này mô tả xu hướng chung. Operator như `share`, `cache`, `replay`, `publish` và nguồn gốc hot/cold có thể làm thay đổi hành vi; phải đọc vị trí toán tử trong toàn pipeline.

## 5. Chuyển nguồn cold thành hot: share và cache

Reactor có thể biến một nguồn cold thành nguồn được chia sẻ giữa nhiều Subscriber. Hai lựa chọn thường gặp là `share()` và `cache()`; chúng không có cùng ngữ nghĩa.

### 5.1. share: multicast dữ liệu mới cho nhóm Subscriber hiện tại

~~~java
Flux<Long> shared = Flux.interval(Duration.ofMillis(500))
        .share();
~~~

`share()` bắt đầu kết nối upstream khi có Subscriber đầu tiên. Các Subscriber đang tham gia dùng chung lượt phát. Subscriber đến muộn thường chỉ nhận các tick phát sau khi họ đăng ký, không nhận lại toàn bộ tick trước đó. Khi nhóm Subscriber rời đi, `share` có thể ngắt kết nối upstream theo ngữ nghĩa ref-count; các hành vi reset/reconnect phụ thuộc phiên bản và trạng thái nguồn.

Phù hợp khi nhiều client cùng xem một live feed và việc chạy nhiều nguồn upstream giống nhau là lãng phí. Không dùng nếu mỗi client cần kết quả độc lập, hoặc cần chắc chắn nhận lại toàn bộ sự kiện cũ.

### 5.2. cache: lưu và phát lại tín hiệu cho Subscriber sau

~~~java
Mono<Config> cachedConfig = loadConfig()
        .cache();
~~~

`cache()` lưu tín hiệu từ upstream để Subscriber sau có thể nhận lại giá trị và terminal đã cache. Với `Flux`, cache có thể giữ nhiều phần tử; cần xem overload giới hạn số lượng và TTL để tránh giữ dữ liệu vô hạn. Với dữ liệu nhạy cảm hoặc cần luôn mới, cache không thời hạn có thể gây lỗi logic.

`cache` hữu ích cho một kết quả dùng chung, ví dụ tải cấu hình hoặc metadata chỉ cần tính một lần trong lifetime của cache. Nó không thay thế cache chuyên dụng có invalidation, giới hạn bộ nhớ, phân vùng theo key và chính sách hết hạn của ứng dụng.

### 5.3. Chọn nhanh

| Nhu cầu | Lựa chọn |
| --- | --- |
| Nhiều Subscriber nhận sự kiện mới từ cùng một nguồn | `share()` |
| Subscriber muộn nhận lại dữ liệu đã lưu | `cache()` hoặc `replay()` |
| Mỗi Subscriber chạy lại toàn bộ nguồn | Giữ cold; dùng `defer` nếu cần tạo mới |
| Chỉ chia sẻ sau khi đủ N Subscriber đăng ký | `publish().autoConnect(N)` hoặc `refCount(N)` |
| Cần điều khiển thời điểm bắt đầu thủ công | `publish()` / `replay()` kết hợp `connect()` |

## 6. ConnectableFlux: kiểm soát thời điểm bắt đầu broadcast

`publish()` và `replay()` có thể trả về `ConnectableFlux<T>`. Khác với Flux thường, ConnectableFlux cho phép gắn Subscriber trước, sau đó mới chủ động gọi `connect()` để bắt đầu upstream.

~~~java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A:" + value));
shared.subscribe(value -> System.out.println("B:" + value));

shared.connect();
~~~

Stdout:

~~~text
A:1
B:1
A:2
B:2
A:3
B:3
~~~

Với nguồn đồng bộ và hai Subscriber đã đăng ký trước `connect()`, cả hai nhận cùng một lượt phát. `publish` điều phối demand của nhiều Subscriber; nếu một Subscriber không có demand, nó có thể làm nguồn tạm dừng để bảo đảm backpressure cho nhóm.

### 6.1. autoConnect và refCount

- `publish().autoConnect(n)` tự gọi connect khi có đủ `n` Subscriber. Sau khi kết nối, nó không dùng số Subscriber hiện tại làm điều kiện tự ngắt như refCount.
- `publish().refCount(n)` kết nối khi đủ `n` Subscriber và quản lý việc hủy kết nối upstream khi số Subscriber giảm dưới ngưỡng theo hợp đồng.
- `share()` là lựa chọn ngắn gọn cho kiểu chia sẻ bắt đầu với Subscriber đầu tiên; cần đọc semantics cụ thể của phiên bản Reactor đang dùng.

Nếu cần một nhóm hai Subscriber cùng bắt đầu nguồn đồng thời, `autoConnect(2)` hoặc `refCount(2)` hữu ích. Với nguồn đồng bộ chạy rất nhanh, đăng ký Subscriber thứ hai sau khi Subscriber đầu tiên đã kích hoạt nguồn có thể là quá muộn; hãy chọn ngưỡng hoặc connect thủ công để tránh race về thời điểm.

### 6.2. replay: ConnectableFlux có lịch sử

`replay()` giữ lại các phần tử đã thấy và phát lại cho Subscriber đến sau theo giới hạn cấu hình. Ví dụ `replay(2)` chỉ giữ tối đa hai phần tử cuối:

~~~java
ConnectableFlux<Integer> replayed = Flux.range(1, 5).replay(2);

replayed.connect(); // nguồn đồng bộ phát xong, lịch sử giữ 4 và 5
replayed.subscribe(value -> System.out.println("late:" + value));
~~~

Stdout:

~~~text
late:4
late:5
~~~

Trong ứng dụng live, có thể dùng giới hạn số phần tử hoặc thời gian để Subscriber mới có snapshot gần đây. Replay có bộ nhớ; replay không giới hạn trên nguồn vô hạn sẽ tích lũy dữ liệu mãi. Nếu cần event history lâu dài và khả năng phục hồi sau restart, dùng broker/log/database bền vững thay vì chỉ dựa vào RAM của Publisher.

## 7. Sinks.Many: tạo nguồn hot do ứng dụng điều khiển

`Sinks.Many<T>` cho phép ứng dụng chủ động đẩy dữ liệu vào một nguồn và cung cấp view `Flux<T>` cho Subscriber. Ba nhóm phổ biến:

| Sink | Hành vi với Subscriber mới | Số Subscriber |
| --- | --- | --- |
| `Sinks.many().multicast()` | Chỉ phát phần tử mới kể từ lúc đăng ký; không replay lịch sử | Nhiều |
| `Sinks.many().unicast()` | Chỉ cho một Subscriber; có thể buffer phần tử trước khi Subscriber đầu tiên đăng ký | Một |
| `Sinks.many().replay()` | Phát lại lịch sử theo giới hạn cấu hình rồi tiếp tục live | Nhiều |

Ví dụ tạo multicast sink:

~~~java
Sinks.Many<Event> sink = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Flux<Event> events = sink.asFlux();
~~~

Ứng dụng có thể giữ `sink` trong một service singleton để nhận sự kiện từ nhiều nơi và cung cấp `events` cho các client. Vì sink là shared resource, cần xác định chính sách backpressure, buffer, lỗi phát và vòng đời terminal.

### 7.1. Kiểm tra kết quả phát

~~~java
Sinks.EmitResult result = sink.tryEmitNext(event);

if (result.isFailure()) {
    // Xử lý thất bại theo loại result và chính sách của ứng dụng.
}
~~~

Các lỗi có thể gồm `FAIL_NON_SERIALIZED` khi nhiều producer tranh chấp phát đồng thời, `FAIL_OVERFLOW` khi vượt khả năng buffer, `FAIL_TERMINATED` khi sink đã complete/error, hoặc `FAIL_ZERO_SUBSCRIBER` ở cấu hình không chấp nhận phát khi không có Subscriber. Kết quả cụ thể phụ thuộc loại sink.

Không bỏ qua `EmitResult` rồi giả định event đã được broadcast. Với nhiều producer, dùng safe sink và xử lý tranh chấp bằng retry có giới hạn/điều phối qua một hàng đợi một đầu phát. `Sinks.unsafe()` chỉ phù hợp khi caller tự bảo đảm serialize việc phát.

### 7.2. Multicast và replay sink

~~~java
Sinks.Many<Event> live = Sinks.many()
        .multicast()
        .onBackpressureBuffer();

Sinks.Many<Event> history = Sinks.many()
        .replay()
        .limit(100);
~~~

`live` chỉ chuyển sự kiện mới tới Subscriber hiện tại; `history` giữ tối đa 100 sự kiện để phát lại cho Subscriber muộn. Chọn sink theo nghiệp vụ: live telemetry có thể không cần lịch sử; dashboard có thể cần snapshot gần nhất; hệ thống giao dịch cần log bền vững/ack thay vì một replay buffer trong RAM.

## 8. Ứng dụng Spring WebFlux: request riêng hay broadcast?

### 8.1. Endpoint trả dữ liệu riêng cho từng request

Một controller có thể trả cold Publisher:

~~~java
@GetMapping("/users/{id}")
Mono<User> getUser(@PathVariable String id) {
    return userRepository.findById(id);
}
~~~

Đây là snippet trong ứng dụng Spring WebFlux đã có repository reactive. Mỗi request được WebFlux subscribe; repository reactive thường thực hiện truy vấn cho subscription tương ứng. Nếu cùng Mono bị subscribe thêm lần nữa, đừng mặc định kết quả được cache.

### 8.2. Endpoint Server-Sent Events từ nguồn sự kiện chung

Giả sử một service phát event toàn ứng dụng:

~~~java
@Service
class EventHub {
    private final Sinks.Many<ServerEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    Flux<ServerEvent> stream() {
        return sink.asFlux();
    }

    void publish(ServerEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            throw new IllegalStateException("Event publish failed: " + result);
        }
    }
}
~~~

Controller:

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerEvent> events() {
    return eventHub.stream();
}
~~~

Đây là hai đoạn minh họa cần dependency Spring WebFlux và các kiểu ứng dụng `ServerEvent`, `eventHub`. Mỗi client SSE tạo một Subscriber vào cùng sink multicast. Client kết nối muộn chỉ nhận event mới từ thời điểm đăng ký; nếu client ngắt kết nối, Subscriber của nó rời stream, nhưng sink có thể tiếp tục phục vụ các client khác.

Nếu cần client mất mạng kết nối lại và nhận sự kiện bị bỏ lỡ, cần event ID, replay có giới hạn hoặc broker có offset/ack. Một sink multicast trong bộ nhớ không đảm bảo durable delivery.

### 8.3. Không tự subscribe trong controller

Hãy trả `Mono`/`Flux` để WebFlux quản lý subscription, cancellation và backpressure. Không gọi `subscribe()` thủ công trong controller chỉ để “bắt đầu stream”, vì sẽ tách vòng đời khỏi HTTP request và làm khó xử lý lỗi, hủy kết nối, dọn tài nguyên.

## 9. Ví dụ Java 17+ chạy độc lập: cold phát lại, hot multicast không replay

Ví dụ dưới dùng Reactor Core và nguồn đồng bộ để stdout xác định. Cold source dùng `Flux.defer` để ghi nhận mỗi lần tạo subscription. Hot source dùng multicast sink: Subscriber A đăng ký trước event thứ nhất; B đăng ký sau event thứ nhất nên chỉ nhận event thứ hai.

Cấu trúc dự án:

~~~text
cold-hot-demo/
├── build.gradle
└── src/main/java/ColdHotDemo.java
~~~

`build.gradle`:

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
    mainClass = 'ColdHotDemo'
}
~~~

`src/main/java/ColdHotDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

public class ColdHotDemo {

    private static void emit(Sinks.Many<String> sink, String value) {
        Sinks.EmitResult result = sink.tryEmitNext(value);
        if (result.isFailure()) {
            throw new IllegalStateException("Emit failed: " + result);
        }
    }

    private static void complete(Sinks.Many<String> sink) {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result.isFailure()) {
            throw new IllegalStateException("Complete failed: " + result);
        }
    }

    public static void main(String[] args) {
        AtomicInteger runs = new AtomicInteger();

        Flux<String> cold = Flux.defer(() -> {
            int run = runs.incrementAndGet();
            System.out.println("cold run #" + run);
            return Flux.just("A", "B");
        });

        System.out.println("[cold]");
        cold.subscribe(value -> System.out.println("S1:" + value));
        cold.subscribe(value -> System.out.println("S2:" + value));

        System.out.println("[hot multicast]");
        Sinks.Many<String> sink =
                Sinks.many().multicast().onBackpressureBuffer();
        Flux<String> hot = sink.asFlux();

        hot.subscribe(value -> System.out.println("A:" + value));
        emit(sink, "one");

        hot.subscribe(value -> System.out.println("B:" + value));
        emit(sink, "two");
        complete(sink);

        System.out.println("[assembly capture]");
        AtomicInteger version = new AtomicInteger(1);
        Mono<Integer> captured = Mono.just(version.get());
        Mono<Integer> deferred =
                Mono.defer(() -> Mono.just(version.get()));

        version.set(2);
        captured.subscribe(value -> System.out.println("just:" + value));
        deferred.subscribe(value -> System.out.println("defer:" + value));
    }
}
~~~

Từ thư mục chứa `build.gradle`, chạy bằng Gradle đã cài:

~~~bash
gradle -q run
~~~

Nếu dự án có wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows. Stdout chính xác của chương trình đồng bộ này:

~~~text
[cold]
cold run #1
S1:A
S1:B
cold run #2
S2:A
S2:B
[hot multicast]
A:one
A:two
B:two
[assembly capture]
just:1
defer:2
~~~

Phân tích:

1. `cold.subscribe` thứ nhất gọi supplier lần đầu, phát A và B cho S1.
2. Subscription thứ hai gọi supplier lại, tạo lượt phát mới cho S2.
3. A đăng ký sink trước khi event `one` được phát, nên nhận event đó.
4. B đăng ký sau `one`, nên multicast sink không phát lại event cũ cho B. Cả A và B nhận event `two`.
5. `Mono.just(version.get())` chụp số 1 ở assembly. `Mono.defer(...)` đọc version khi subscribe nên phát số 2 sau khi biến đã đổi.

Ví dụ không dùng scheduler hoặc I/O bất đồng bộ, nên thứ tự output xác định. Với nguồn live thực tế, event có thể phát đồng thời với lúc client đăng ký; cần xác định ranh giới đăng ký và chính sách replay rõ ràng.

## 10. Kiểm thử bằng StepVerifier

Trong dự án có JUnit 5, thêm `reactor-test` cùng phiên bản Reactor vào test scope:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/test/java/ColdHotTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

class ColdHotTest {

    @Test
    void coldSourceRunsAgainForEachSubscription() {
        AtomicInteger runs = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() ->
                Flux.just(runs.incrementAndGet()));

        StepVerifier.create(cold)
                .expectNext(1)
                .verifyComplete();

        StepVerifier.create(cold)
                .expectNext(2)
                .verifyComplete();

        assertEquals(2, runs.get());
    }

    @Test
    void replaySinkReplaysHistoryToLateSubscriber() {
        Sinks.Many<Integer> sink = Sinks.many().replay().all();

        sink.tryEmitNext(10).orThrow();
        sink.tryEmitNext(20).orThrow();
        sink.tryEmitComplete().orThrow();

        StepVerifier.create(sink.asFlux())
                .expectNext(10, 20)
                .verifyComplete();

        StepVerifier.create(sink.asFlux())
                .expectNext(10, 20)
                .verifyComplete();
    }

    @Test
    void multicastSinkDoesNotReplayEarlierEvents() {
        Sinks.Many<Integer> sink =
                Sinks.many().multicast().onBackpressureBuffer();
        Flux<Integer> hot = sink.asFlux();

        StepVerifier.create(hot)
                .then(() -> sink.tryEmitNext(1).orThrow())
                .expectNext(1)
                .thenCancel()
                .verify();

        StepVerifier.create(hot)
                .then(() -> sink.tryEmitNext(2).orThrow())
                .expectNext(2)
                .then(() -> sink.tryEmitComplete().orThrow())
                .verifyComplete();
    }
}
~~~

Các test xác minh ba hợp đồng khác nhau: cold source tạo lượt mới cho mỗi subscription; replay sink lưu lịch sử và phát lại; multicast sink chỉ chuyển sự kiện mới trong thời gian Subscriber đăng ký. Test sink sử dụng `tryEmit...` và kiểm tra kết quả bằng `orThrow`, tránh âm thầm bỏ qua lỗi phát.

Khi kiểm thử nguồn có scheduler hoặc thời gian, dùng `StepVerifier.withVirtualTime` khi toán tử hỗ trợ virtual scheduler; không dựa vào `Thread.sleep`. Với sink có backpressure, thêm test cho subscriber demand bằng 0 và overflow policy.

## 11. Lựa chọn mô hình theo yêu cầu nghiệp vụ

| Câu hỏi | Hướng chọn |
| --- | --- |
| Mỗi request phải thực hiện truy vấn/gọi HTTP riêng? | Cold Publisher; dùng `defer` nếu thao tác tạo nguồn phải chạy khi subscribe |
| Nhiều client cùng xem một live feed? | Hot multicast qua `share` hoặc `Sinks.Many.multicast` |
| Client muộn phải nhận lại vài event gần nhất? | `replay(limit)`, `cache(history)` hoặc replay sink có giới hạn |
| Cần mọi Subscriber sẵn sàng trước khi nguồn bắt đầu? | `ConnectableFlux.publish()` và `connect()` sau khi đăng ký, hoặc `autoConnect(n)` |
| Cần tự kết nối khi đủ Subscriber và ngắt khi nhóm rời đi? | `refCount(n)` |
| Chỉ cần một kết quả dùng chung và phát lại về sau? | `Mono.cache()` hoặc cache có TTL khi phù hợp |
| Event phải tồn tại qua restart/mất mạng? | Broker/event log/database bền vững; hot sink trong RAM không đủ |
| Nhiều producer đẩy cùng một sink? | Safe sink, xử lý `EmitResult` và serialize/retry có giới hạn |
| Mỗi Subscriber phải có state riêng? | Cold source/`defer`; tránh biến mutable bị capture ngoài assembly |

Quyết định cold/hot cần xét cả chi phí lẫn ngữ nghĩa: cold có thể nhân request hoặc công việc theo số Subscriber; hot có thể tiết kiệm upstream nhưng làm các Subscriber phụ thuộc vào cùng một nhịp phát và chính sách mất/replay dữ liệu.

## 12. Lỗi thường gặp

1. **Cho rằng mọi Flux đều cold:** `Mono.just`/`Flux.just` chụp giá trị ở assembly theo cách Reactor mô tả là một trong số operator hot đặc biệt. Nếu cần đọc giá trị mới mỗi subscription, dùng `defer`.
2. **Cho rằng hot luôn phát lại lịch sử:** multicast source thường không replay. Dùng replay/cache hoặc event store khi cần history.
3. **Cho rằng cold luôn tạo bản sao object:** `fromIterable(sharedList)` vẫn có thể dùng chung collection. Cold không đảm bảo deep copy.
4. **Gọi `share()` nhưng mong mỗi Subscriber gọi upstream riêng:** share chủ ý chia sẻ một lượt upstream cho nhóm Subscriber.
5. **Dùng `cache()` không giới hạn cho nguồn vô hạn:** bộ nhớ giữ lịch sử tăng liên tục. Chọn history/TTL hoặc một sink có giới hạn.
6. **Đăng ký Subscriber sau khi nguồn đồng bộ đã chạy xong:** Subscriber đến muộn không thể nhận dữ liệu nếu nguồn không replay. Đăng ký đủ Subscriber trước `connect` hoặc dùng replay.
7. **Cho rằng hủy một Subscriber luôn hủy nguồn hot:** nếu còn Subscriber khác, nguồn multicast vẫn có thể tiếp tục. Với `refCount`, kiểm tra threshold và hành vi disconnect.
8. **Bỏ qua lỗi của `tryEmitNext`:** event có thể không được nhận do overflow, sink đã terminal hoặc producer tranh chấp.
9. **Dùng sink trong singleton nhưng không giới hạn buffer:** nguồn nhanh hơn consumer có thể tăng backlog hoặc overflow.
10. **Dùng in-memory hot stream làm event log bền vững:** process restart có thể mất lịch sử. Cần broker hoặc storage có persistence.
11. **Tự gọi `subscribe()` trong controller/service chỉ để khởi động luồng:** tách lifecycle khỏi caller, khó cancel và xử lý lỗi. Trả Publisher để framework/caller quản lý.
12. **Đánh đồng cold/hot với đồng bộ/bất đồng bộ:** hãy kiểm tra riêng thời điểm subscription, scheduler, nguồn dữ liệu và chính sách broadcast.

## 13. Tự kiểm tra

1. Hai Subscriber subscribe cùng `Flux.defer(() -> Flux.range(1, 3))` sẽ nhận gì? **Mỗi Subscriber có một lượt 1, 2, 3 độc lập.**
2. `Mono.just(loadConfig())` gọi `loadConfig` lúc nào? **Khi Java lắp ghép biểu thức, trước subscription.**
3. Làm sao để gọi `loadConfig` mỗi lần subscribe? **`Mono.defer(() -> Mono.just(loadConfig()))` hoặc `fromCallable` nếu thao tác có thể ném lỗi.**
4. Subscriber B đăng ký sau khi multicast sink đã phát event E1, B có nhận E1 không? **Không, trừ khi nguồn có replay.**
5. `replay(2)` giữ tối đa bao nhiêu phần tử lịch sử? **Hai phần tử gần nhất.**
6. `publish()` khác `share()` ở điểm nào? **publish trả ConnectableFlux cho phép chủ động connect; share tự kết nối theo Subscriber và chia sẻ lượt phát.**
7. `cache()` có phù hợp vô điều kiện cho Flux vô hạn? **Không, phải giới hạn history/TTL và xem bộ nhớ.**
8. Cold source có chắc chắn thread-safe không? **Không; nó có thể capture object mutable dùng chung hoặc truy cập resource không thread-safe.**
9. Hot source có chắc chắn phải chạy trên thread nền không? **Không; nguồn hot có thể phát đồng bộ hoặc bất đồng bộ.**
10. Một endpoint SSE phải gửi event bị lỡ khi client reconnect. Multicast sink đơn giản có đủ không? **Không; cần replay/event ID hoặc nguồn lưu bền vững phù hợp.**

**Ghi nhớ:** Cold tạo lượt phát theo từng subscription; hot chia sẻ một nhịp phát và Subscriber đến muộn thường chỉ thấy dữ liệu mới. `defer` điều khiển thời điểm tạo nguồn, `share` multicast dữ liệu đang phát, `cache`/`replay` lưu lịch sử, còn `Sinks.Many` cho ứng dụng chủ động phát event. Chọn theo việc mỗi client cần dữ liệu riêng, dữ liệu live hay lịch sử có thể phát lại.

## Tài liệu tham khảo

- [Project Reactor Reference Guide — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html).
- [Project Reactor Reference Guide — Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html).
- [Project Reactor Reference Guide — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- [Project Reactor Flux Javadoc — publish, replay, share, cache, refCount](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Spring Framework Reference — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
