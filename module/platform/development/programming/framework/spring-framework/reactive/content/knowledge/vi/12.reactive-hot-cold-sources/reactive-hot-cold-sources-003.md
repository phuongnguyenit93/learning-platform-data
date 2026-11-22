# Chia sẻ subscription bằng `share()` và `publish()` trong Project Reactor

## 1. Vấn đề: nhiều subscriber có cần chạy lại cùng một nguồn?

Trong Reactor, một `Flux<T>` thường là một **Publisher**. Khi một subscriber đăng ký, publisher cung cấp dữ liệu theo hợp đồng Reactive Streams. Với nguồn **cold**, mỗi subscription thường tạo một lần chạy nguồn riêng. Điều đó phù hợp khi mỗi người gọi cần kết quả độc lập, nhưng có thể lãng phí nếu nhiều subscriber muốn cùng nghe một luồng sự kiện hoặc cùng sử dụng một thao tác I/O đắt tiền đang diễn ra.

Ví dụ một nguồn cold đếm ba số:

~~~java
Flux<Integer> source = Flux.range(1, 3);

source.subscribe(v -> System.out.println("A: " + v));
source.subscribe(v -> System.out.println("B: " + v));
~~~

Mỗi lần `subscribe()` kích hoạt một subscription riêng. Nguồn `range` chạy hai lần: subscriber A nhận 1, 2, 3; sau đó subscriber B cũng nhận 1, 2, 3. Nếu nguồn là một HTTP request, truy vấn database hoặc kết nối thiết bị, mỗi subscriber có thể khiến công việc nguồn được thực hiện lại.

Khi muốn **một subscription upstream chia sẻ dữ liệu cho nhiều subscriber**, Reactor cung cấp các cơ chế multicast như `share()` và `publish()`. Hai cách này có cùng mục tiêu chia sẻ một luồng đang chạy, nhưng khác cách bắt đầu kết nối, theo dõi subscriber và quản lý vòng đời.

Điều cần xác định trước khi chọn toán tử:

- Nguồn có nên chạy một lần cho mỗi subscriber hay chỉ một lần cho cả nhóm đang nghe?
- Khi nào nguồn bắt đầu: ngay khi subscriber đầu tiên tới hay sau khi ta chủ động kết nối?
- Subscriber tới muộn có cần nhận lại các phần tử đã phát không?
- Khi mọi subscriber rời đi, nguồn có nên bị hủy?
- Nguồn có phải dữ liệu riêng theo user/tenant/request không, hay thật sự có thể chia sẻ an toàn?

## 2. Cold publisher và hot publisher

**Cold publisher** tạo hoặc đọc dữ liệu khi có subscription. Mỗi subscriber thường nhận một lần chạy độc lập từ đầu. Ví dụ thường gặp:

- `Flux.range(1, 5)`, `Flux.fromIterable(list)`: mỗi subscription duyệt nguồn lại.
- `Flux.defer(() -> ...)`: gọi supplier tạo publisher mới theo từng subscription.
- `Mono.fromCallable(...)`: thực thi callable theo subscription.
- Một publisher HTTP/database được dựng theo cách mỗi subscription khởi chạy một request/query riêng.

**Hot publisher** có thể phát dữ liệu độc lập với từng subscriber. Một subscriber mới tham gia khi nguồn đang chạy thường chỉ thấy những phần tử phát sau thời điểm nó đăng ký; dữ liệu đã trôi qua không tự được phát lại, trừ khi nguồn có cơ chế replay/cache.

Ví dụ nguồn hot có thể đến từ `Sinks.Many`, một event bus, thiết bị cảm biến hoặc một `ConnectableFlux` đã được kết nối.

Một chi tiết dễ nhầm: `Flux.just(...)` và `Mono.just(...)` chụp các giá trị ngay khi publisher được tạo rồi phát lại các giá trị đã chụp cho mỗi subscriber. Chúng không gọi lại một supplier hoặc thực hiện lại HTTP request như `defer`. Nếu muốn tạo giá trị riêng cho mỗi subscriber, dùng `defer`:

~~~java
Mono<String> captured = Mono.just(loadValueNow());

Mono<String> perSubscription = Mono.defer(
    () -> Mono.just(loadValueNow())
);
~~~

Đây là ví dụ cấu trúc; `loadValueNow()` là hàm đồng bộ giả định. Ở dòng đầu, Java gọi hàm ngay khi tạo `Mono.just`; ở dòng sau, hàm chỉ được gọi khi subscribe. **Cold/hot mô tả cách nguồn gắn với subscriber, không nói rằng publisher có hoặc không có thread riêng.**

## 3. `share()`: tự động chia sẻ khi có subscriber đầu tiên

`Flux.share()` tạo một publisher multicast. Khi subscriber đầu tiên đăng ký, nguồn upstream được subscribe và bắt đầu phát. Các subscriber khác tham gia trong lúc luồng còn hoạt động sẽ nhận những phần tử tiếp theo từ cùng subscription upstream, thay vì tạo thêm một subscription mới.

Hành vi quan trọng:

1. **Tự kết nối:** không cần gọi `connect()`; subscriber đầu tiên làm nguồn bắt đầu chạy.
2. **Chia sẻ đồng thời:** nhiều subscriber đang cùng nghe một instance `shared` nhận chung các phần tử upstream trong khoảng thời gian đăng ký chồng lấp.
3. **Không replay lịch sử:** subscriber tới sau không tự nhận lại các phần tử đã phát trước khi nó tham gia.
4. **Hủy theo số subscriber:** khi tất cả subscriber đã hủy, `share()` hủy subscription upstream. Điều này giúp dừng nguồn khi không còn người nghe.
5. **Nguồn kết thúc:** nếu upstream complete/error, các subscriber hiện tại nhận terminal signal tương ứng. `share()` không phải cơ chế lưu lịch sử để subscriber tương lai đọc lại toàn bộ dữ liệu.

Trong Reactor, `share()` tương đương cách dùng `publish().refCount()` với ngưỡng một subscriber. Có thể hình dung:

~~~text
Subscriber A ----                  Subscriber B ------> Flux.share() ---- một subscription ----> Source
                  /
Subscriber C ----/

A, B, C tham gia khi nguồn đang phát: cùng nhận phần tử mới.
Không có subscriber nào: upstream được hủy.
~~~

**Ví dụ khái niệm:**

~~~java
Flux<Event> sharedEvents = eventSource().share();

sharedEvents.subscribe(this::sendToDashboard);
sharedEvents.subscribe(this::updateMetrics);
~~~

Đoạn trên minh họa service có `eventSource()`; hai subscriber phải dùng **cùng một instance** `sharedEvents`. Nếu mỗi nơi gọi lại `eventSource().share()` và tạo hai publisher khác nhau, chúng không chia sẻ một subscription với nhau.

`share()` phù hợp khi nhiều người cùng nghe một nguồn đang hoạt động, ví dụ một luồng sự kiện chung, một kết nối upstream có thể chia sẻ, hoặc một stream cảm biến dùng chung. Không dùng nó như cache kết quả hoặc hàng đợi lưu mọi sự kiện cho người đến muộn.

## 4. `publish()`: điều khiển kết nối bằng ConnectableFlux

`publish()` trả về **`ConnectableFlux<T>`**, khác với `Flux<T>` thông thường. Subscriber có thể đăng ký trước, nhưng nguồn upstream **chưa được subscribe** cho đến khi gọi `connect()` hoặc chọn một chính sách tự kết nối như `autoConnect(n)` hay `refCount(n)`.

Ví dụ:

~~~java
ConnectableFlux<Integer> connectable =
    Flux.range(1, 3).publish();

connectable.subscribe(v -> System.out.println("A: " + v));
connectable.subscribe(v -> System.out.println("B: " + v));

// Nguồn bắt đầu tại đây; hai subscriber đã sẵn sàng.
connectable.connect();
~~~

Trình tự này giúp bảo đảm A và B đều được đăng ký trước khi nguồn đồng bộ bắt đầu phát. Khi `connect()` chạy, nguồn được subscribe một lần và các phần tử được multicast cho các subscriber đã tham gia.

Các phương thức quản lý kết nối:

| Phương thức | Khi nào upstream bắt đầu? | Khi subscriber rời đi |
| --- | --- | --- |
| `publish().connect()` | Khi code gọi `connect()` | Kết nối tồn tại cho đến khi upstream kết thúc hoặc Disposable kết nối bị hủy |
| `publish().autoConnect(n)` | Khi đủ `n` subscriber | Không tự ngắt chỉ vì số subscriber giảm; kết nối được giữ cho đến khi nguồn kết thúc hoặc bị quản lý riêng |
| `publish().refCount(n)` | Khi có ít nhất `n` subscriber | Theo dõi subscriber; khi số lượng giảm dưới ngưỡng, ngắt upstream |
| `publish().refCount(n, gracePeriod)` | Khi đủ `n` subscriber | Có thời gian chờ trước khi ngắt sau khi subscriber rời đi, để subscriber mới có thể tham gia |

Với `connect()`, có thể giữ `Disposable` mà nó trả về để ngắt kết nối thủ công:

~~~java
Disposable connection = connectable.connect();

// Khi ứng dụng quản lý nguồn muốn dừng:
connection.dispose();
~~~

Đây là đoạn minh họa API. Hủy connection có thể dừng nguồn chung và ảnh hưởng **tất cả subscriber** đang nghe nó; chỉ người quản lý lifecycle của nguồn mới nên thực hiện thao tác đó.

### Khi nào dùng publish?

- Cần chờ một nhóm subscriber đăng ký xong rồi mới bắt đầu nguồn.
- Muốn điều khiển chính xác thời điểm nguồn bắt đầu.
- Muốn đặt ngưỡng subscriber bằng `autoConnect(n)` hoặc `refCount(n)`.
- Cần tách việc đăng ký downstream khỏi thời điểm subscribe upstream.

`publish()` không lưu lịch sử. Subscriber đến sau khi nguồn đã bắt đầu chỉ nhận dữ liệu từ thời điểm tham gia, không nhận lại những giá trị đã phát.

## 5. So sánh `share()`, `publish()`, `autoConnect()` và `refCount()`

| Tiêu chí | `share()` | `publish()` | `publish().autoConnect(n)` | `publish().refCount(n)` |
| --- | --- | --- | --- | --- |
| Kết quả | `Flux<T>` multicast | `ConnectableFlux<T>` | `Flux<T>` tự kết nối | `Flux<T>` kết nối theo số subscriber |
| Bắt đầu nguồn | Subscriber đầu tiên | Gọi `connect()` | Đủ `n` subscriber | Đủ `n` subscriber |
| Điều khiển thời điểm | Tự động | Chủ động | Tự động theo ngưỡng | Tự động theo ngưỡng |
| Theo dõi số subscriber để hủy nguồn | Có, hủy khi mọi subscriber rời đi | Không tự động theo cách refCount | Không tự ngắt chỉ vì subscriber giảm | Có, ngắt khi số lượng dưới ngưỡng |
| Replay phần tử cũ | Không | Không | Không | Không |
| Dùng điển hình | Chia sẻ nguồn khi có người nghe | Cần tự quyết định lúc connect | Nguồn phải bắt đầu khi đủ người nghe và tiếp tục chạy | Nguồn chỉ cần hoạt động khi đủ người nghe |

Một cách nhớ:

- **`share()`**: “Có người nghe thì bắt đầu; không còn ai nghe thì hủy.”
- **`publish()`**: “Tập hợp người nghe trước, rồi tôi tự gọi connect.”
- **`autoConnect(n)`**: “Đủ người nghe thì tự kết nối và giữ kết nối.”
- **`refCount(n)`**: “Đủ người nghe thì kết nối; dưới ngưỡng thì ngắt.”

`share()` thường phù hợp cho một subscriber tối thiểu. Nếu cần chờ hai hay nhiều subscriber cùng sẵn sàng, dùng `publish().refCount(n)` hoặc `publish().autoConnect(n)` tùy chính sách sau khi kết nối.

## 6. `publish` phối hợp backpressure như thế nào?

Khi multicast, nhiều subscriber có thể có tốc độ tiêu thụ khác nhau. `publish()` điều phối nhu cầu (`request(n)`) của các subscriber và chuyển nhu cầu đó về upstream. Theo tài liệu Reactor, nếu một subscriber đang có demand bằng 0, `publish` có thể tạm dừng yêu cầu thêm dữ liệu từ nguồn để tôn trọng subscriber đó.

Hệ quả: **subscriber chậm có thể làm chậm nguồn chung và ảnh hưởng các subscriber khác**. Đây là trade-off của việc dùng chung một luồng với backpressure phối hợp. Nếu một subscriber không bao giờ yêu cầu thêm dữ liệu, multicast có thể ngừng kéo nguồn cho toàn nhóm.

Cần cân nhắc:

- Subscriber có cùng khả năng xử lý không?
- Có thể bỏ sự kiện cũ hay không?
- Có cần queue/buffer riêng cho từng người nhận không?
- Nguồn có hỗ trợ pause/resume hay replay không?
- Khi subscriber chậm, nên làm chậm toàn nguồn, bỏ phần tử, hay ngắt subscriber đó?

Không nên giải quyết mọi trường hợp bằng cách tăng buffer vô hạn. Buffer lớn chỉ trì hoãn thời điểm cạn bộ nhớ và có thể làm tăng latency. Nếu cần mỗi subscriber có chính sách backpressure độc lập, có thể cần kiến trúc fan-out/queue riêng thay vì một multicast backpressure phối hợp đơn giản.

## 7. Subscriber đến muộn: share/publish không phải replay

Đây là khác biệt quan trọng nhất khi lựa chọn toán tử:

~~~text
Nguồn phát:       A ---- B ---- C ---- D ---- E ---- complete
Subscriber 1:     ^ nhận A, B, C, D, E
Subscriber 2:                 ^ nhận D, E nếu tham gia sau C

share/publish: không phát lại A, B, C cho Subscriber 2.
replay/cache: có thể phát lại lịch sử đã lưu theo giới hạn cấu hình.
~~~

Nếu subscriber đến muộn cần nhận dữ liệu cũ, xem:

- `replay()`: trả về `ConnectableFlux` có khả năng lưu và phát lại lịch sử; có thể giới hạn số phần tử hoặc thời gian giữ.
- `replay(n)`: giữ tối đa `n` phần tử gần nhất để phát lại.
- `replay(Duration)`: giữ phần tử trong thời gian TTL.
- `cache()` hoặc các biến thể `cache(history, ttl)`: tự động lưu tín hiệu để subscriber sau có thể nhận lại; cần chọn giới hạn để tránh giữ dữ liệu vô hạn.

Ví dụ:

~~~java
Flux<Event> recent = eventSource().replay(100).autoConnect(1);
~~~

Nguồn sẽ bắt đầu khi subscriber đầu tiên tới; các subscriber sau có thể nhận lại tối đa 100 phần tử gần nhất, theo chính sách replay. Đây là **ví dụ cấu trúc**; nếu cần điều khiển connect thủ công, giữ kiểu `ConnectableFlux` và gọi `connect()`.

Đừng dùng `share()` khi yêu cầu là “mọi client mới phải đọc lại toàn bộ sự kiện từ đầu”. Nó không phải message broker có durable log. Với dữ liệu cần đảm bảo không mất khi client offline, cần persistence, event log, offset hoặc broker có replay theo consumer.

## 8. Ví dụ Java 17+ chạy được: cold, share và publish

Ví dụ sau sử dụng **Reactor Core 3.8.6** trực tiếp, không cần Spring Boot. Nó minh họa:

1. Nguồn cold được chạy lại cho từng subscriber.
2. `share()` dùng một subscription upstream cho hai subscriber đăng ký gần nhau.
3. `publish()` cho phép đăng ký hai subscriber trước rồi mới `connect()`.

Cấu trúc:

~~~text
reactor-share-publish/
├── pom.xml
└── src/main/java/SharingDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-share-publish</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.6</version>
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

File `src/main/java/SharingDemo.java`:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class SharingDemo {
    public static void main(String[] args) throws InterruptedException {
        // 1. Cold source: mỗi subscription chạy supplier một lần.
        AtomicInteger coldRuns = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            int run = coldRuns.incrementAndGet();
            System.out.println("cold source run " + run);
            return Flux.just(1, 2);
        });

        cold.subscribe(value -> System.out.println("A: " + value));
        cold.subscribe(value -> System.out.println("B: " + value));

        // 2. share(): hai subscriber cùng tham gia trước tick đầu tiên.
        AtomicInteger sharedStarts = new AtomicInteger();

        Flux<Long> shared = Flux.interval(Duration.ofMillis(500))
            .take(3)
            .doOnSubscribe(s -> sharedStarts.incrementAndGet())
            .share();

        List<Long> first = new CopyOnWriteArrayList<>();
        List<Long> second = new CopyOnWriteArrayList<>();
        CountDownLatch finished = new CountDownLatch(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        shared.subscribe(
            first::add,
            error -> {
                failure.compareAndSet(null, error);
                finished.countDown();
            },
            finished::countDown
        );

        shared.subscribe(
            second::add,
            error -> {
                failure.compareAndSet(null, error);
                finished.countDown();
            },
            finished::countDown
        );

        if (!finished.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out waiting for share()");
        }
        if (failure.get() != null) {
            throw new IllegalStateException("share() failed", failure.get());
        }

        System.out.println("share upstream subscriptions = " + sharedStarts.get());
        System.out.println("share subscriber A = " + first);
        System.out.println("share subscriber B = " + second);

        // 3. publish(): đăng ký cả hai subscriber trước khi connect.
        AtomicInteger publishStarts = new AtomicInteger();

        ConnectableFlux<Integer> connectable = Flux.range(1, 3)
            .doOnSubscribe(s -> publishStarts.incrementAndGet())
            .publish();

        List<Integer> publishA = new java.util.ArrayList<>();
        List<Integer> publishB = new java.util.ArrayList<>();

        connectable.subscribe(publishA::add);
        connectable.subscribe(publishB::add);

        System.out.println("publish before connect = " + publishStarts.get());
        connectable.connect();

        System.out.println("publish upstream subscriptions = " + publishStarts.get());
        System.out.println("publish subscriber A = " + publishA);
        System.out.println("publish subscriber B = " + publishB);
    }
}
~~~

Chạy từ thư mục `reactor-share-publish` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SharingDemo
~~~

**Output do chương trình in** (không tính thông báo Maven nếu môi trường hiển thị thêm):

~~~text
cold source run 1
A: 1
A: 2
cold source run 2
B: 1
B: 2
share upstream subscriptions = 1
share subscriber A = [0, 1, 2]
share subscriber B = [0, 1, 2]
publish before connect = 0
publish upstream subscriptions = 1
publish subscriber A = [1, 2, 3]
publish subscriber B = [1, 2, 3]
~~~

Phân tích:

- Với nguồn cold, `Flux.defer` được gọi hai lần: một lần cho A và một lần cho B. Bộ đếm chứng minh hai subscription upstream.
- Với `share()`, nguồn `interval` có lần phát đầu sau 500 ms. Hai subscriber được đăng ký liên tiếp trước tick đầu nên cùng nhận 0, 1, 2. `doOnSubscribe` nằm **trước share**, do đó đếm subscription upstream và kết quả là 1.
- Với `publish()`, hai subscriber đăng ký nhưng nguồn chưa chạy; bộ đếm trước `connect()` là 0. Sau khi kết nối, nguồn chạy đúng một lần và multicast ba phần tử cho cả A và B.
- Ví dụ dùng `CountDownLatch` để đợi hai subscriber hoàn tất trong chương trình console. Đây là chờ dành cho demo; không dùng `block()` hoặc `Thread.sleep()` trong event-loop của ứng dụng WebFlux.

Để kiểm tra trường hợp subscriber đến muộn, có thể đăng ký subscriber thứ hai **sau khi** nguồn đã phát một vài phần tử; subscriber đó chỉ nhận phần tử mới từ thời điểm tham gia. Nếu cần nhận cả dữ liệu trước đó, thay bằng `replay(...)` hoặc cache có giới hạn.

## 9. Chọn share/publish trong ứng dụng Spring WebFlux

Giả sử nhiều client SSE muốn nghe một luồng sự kiện dùng chung. Một service có thể giữ **một publisher instance**:

~~~java
// Mẫu cấu trúc trong Spring Boot WebFlux.
// Event, eventSdk và các dependency cần được định nghĩa trong ứng dụng.
@Service
class EventService {
    private final Flux<Event> sharedEvents;

    EventService(EventSdk eventSdk) {
        this.sharedEvents = eventSdk.events().share();
    }

    Flux<Event> events() {
        return sharedEvents;
    }
}
~~~

Controller trả publisher cho WebFlux:

~~~java
@RestController
class EventController {
    private final EventService eventService;

    EventController(EventService eventService) {
        this.eventService = eventService;
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<Event> events() {
        return eventService.events();
    }
}
~~~

Hai đoạn trên là **mẫu tích hợp phụ thuộc SDK và domain**, không phải chương trình Java độc lập. Điểm quan trọng:

- Service giữ **cùng một instance** `sharedEvents`, do đó nhiều request có thể tham gia cùng luồng nếu thời gian subscribe chồng lấp.
- Subscriber đầu tiên bắt đầu nguồn; subscriber tới sau chỉ nhận sự kiện mới.
- Khi mọi client đã ngắt và server hủy tất cả subscription, `share()` hủy nguồn upstream. SDK cần hỗ trợ cancellation/cleanup đúng cách.
- Controller **trả Flux** cho framework; không gọi `subscribe()` thủ công để tạo một luồng tách khỏi vòng đời HTTP.

### Lưu ý bảo mật và phạm vi chia sẻ

Không chia sẻ một publisher chứa dữ liệu riêng theo user, tenant, token hoặc quyền truy cập nếu nhiều request có thể nhận dữ liệu của nhau. Việc đưa `share()` vào một singleton service làm nguồn chung ở phạm vi service; mọi subscriber trong nhóm đó có thể nhìn thấy cùng sự kiện. Nếu dữ liệu cần lọc theo user, phải phân vùng nguồn và authorization trước khi multicast, hoặc giữ publisher riêng cho từng scope.

Cũng không nên dùng `share()` để bảo đảm một side effect tiếp tục dù client rời đi. Khi subscriber cuối cùng cancel, upstream có thể bị hủy. Nếu nghiệp vụ cần xử lý nền độc lập với HTTP, hãy quản lý nó bằng lifecycle service/queue/job riêng, không phụ thuộc vào việc còn client nghe hay không.

Nếu muốn đợi đủ số client cùng đăng ký rồi mới bắt đầu phát, có thể dùng:

~~~java
Flux<Event> group = eventSdk.events()
    .publish()
    .refCount(2);
~~~

Nguồn chỉ kết nối khi có hai subscriber. Khi số subscriber giảm dưới ngưỡng, upstream có thể bị ngắt. Với khoảng ngắt ngắn khi client reconnect, cân nhắc overload `refCount(2, Duration.ofSeconds(2))` để cho một subscriber mới có thời gian quay lại trước khi ngắt kết nối.

## 10. Các lỗi thường gặp

1. **Tưởng `share()` lưu lại lịch sử:** sai; subscriber tới muộn không nhận các phần tử đã phát. Dùng `replay` hoặc cache có giới hạn nếu cần lịch sử.
2. **Tạo `source.share()` mới ở mỗi lần gọi service:** mỗi instance có nhóm subscriber riêng, không chia sẻ giữa các instance. Giữ một instance chung trong scope phù hợp.
3. **Subscribe subscriber thứ hai sau khi nguồn đồng bộ đã chạy xong:** subscriber thứ hai có thể kích hoạt một subscription mới theo semantics nguồn/ref-count thay vì chia sẻ lần chạy trước. Dùng nguồn async có thời gian tham gia, hoặc `publish()` rồi đăng ký đủ subscriber trước `connect()`.
4. **Quên gọi `connect()` với `ConnectableFlux`:** subscriber chờ nhưng upstream không bắt đầu. Gọi `connect()` hoặc dùng `autoConnect`/`refCount`.
5. **Gọi `connect()` quá sớm:** nguồn có thể phát trước khi các subscriber mong muốn được đăng ký; các subscriber đến sau bỏ lỡ phần tử đầu. Đăng ký trước, kết nối sau.
6. **Dùng `autoConnect` nhưng kỳ vọng tự ngắt khi mọi người rời:** `autoConnect` không theo dõi số lượng để tự disconnect khi subscriber giảm. Dùng `refCount` hoặc tự giữ Disposable connection.
7. **Dùng `refCount(n)` mà không hiểu ngưỡng:** nếu chưa đủ subscriber, nguồn chưa chạy; khi xuống dưới ngưỡng, nguồn có thể bị ngắt và lần kết nối sau bắt đầu lại.
8. **Một subscriber chậm làm cả nhóm bị chậm:** `publish` phối hợp demand và có thể tạm dừng upstream nếu một subscriber không có demand. Xem xét buffering, tách queue hoặc chính sách bỏ dữ liệu rõ ràng.
9. **Dùng share cho side effect phải hoàn tất độc lập:** subscriber cuối cancel có thể hủy upstream. Dùng job/queue/service quản lý nền.
10. **Chia sẻ dữ liệu nhiều tenant:** publisher chung có thể phát cùng sự kiện cho mọi subscriber. Đảm bảo phân vùng và kiểm tra quyền trước multicast.
11. **Hiểu hot là tự động replay:** hot source thường chỉ phát dữ liệu mới cho subscriber đến muộn, trừ khi cấu hình replay.
12. **Không xử lý lỗi/cancel của nguồn:** một lỗi upstream sẽ kết thúc luồng chung cho các subscriber đang tham gia; cancellation cuối cùng có thể dừng nguồn. Cần cleanup, retry/fallback và observability theo lifecycle.
13. **Gọi `subscribe()` bên trong controller:** tạo subscription riêng không do WebFlux quản lý, làm cancellation và error mapping khó kiểm soát. Trả publisher cho framework.

## 11. Bảng quyết định nhanh

| Yêu cầu | Lựa chọn |
| --- | --- |
| Mỗi subscriber phải chạy nguồn độc lập | Giữ publisher cold; không share |
| Nhiều subscriber đồng thời nghe cùng nguồn; tự động bắt đầu khi người đầu tiên tới | `share()` |
| Đăng ký tất cả subscriber rồi mới bắt đầu nguồn | `publish()` + `connect()` |
| Tự kết nối khi đủ một số subscriber, sau đó giữ kết nối | `publish().autoConnect(n)` |
| Kết nối khi đủ subscriber và ngắt khi số lượng thấp hơn ngưỡng | `publish().refCount(n)` |
| Cho phép reconnect trong một khoảng grace period | `publish().refCount(n, duration)` |
| Subscriber đến muộn cần nhận lại một số sự kiện gần nhất | `replay(n)` hoặc `replay(Duration)` |
| Muốn cache kết quả để các subscription sau dùng lại | `cache(...) ` với giới hạn history/TTL phù hợp |
| Công việc phải tiếp tục dù không còn subscriber | Tách lifecycle thành background job/service, không phụ thuộc share/refCount |

## 12. Tự kiểm tra kiến thức

**1.** Hai lần subscribe vào một `Flux.range(1, 3)` cold có bao nhiêu lần chạy nguồn? **Hai**, một cho mỗi subscription.

**2.** Hai subscriber cùng subscribe vào một instance `source.share()` khi nguồn đang phát có bao nhiêu subscription upstream? **Một** trong nhóm subscriber đang chia sẻ.

**3.** Subscriber đến muộn vào `share()` có nhận lại A, B đã phát không? **Không**; chỉ nhận các phần tử từ lúc tham gia.

**4.** `publish()` trả về loại gì? **`ConnectableFlux<T>`**, cần `connect()` hoặc chính sách tự kết nối.

**5.** Muốn đăng ký hai subscriber trước khi nguồn chạy thì làm sao? Tạo `ConnectableFlux`, subscribe cả hai, sau đó gọi `connect()`; hoặc dùng `autoConnect(2)` nếu muốn tự kết nối theo ngưỡng.

**6.** `autoConnect(2)` có tự ngắt khi subscriber cuối rời không? **Không**, không theo dõi giảm subscriber để disconnect như `refCount`.

**7.** `share()` làm gì khi mọi subscriber cancel? **Hủy upstream** trong khi nguồn đang hoạt động.

**8.** Cần subscriber mới nhận lại 100 sự kiện gần nhất thì chọn gì? **`replay(100)`** hoặc cache có giới hạn phù hợp, không dùng share.

**9.** Có thể dùng một `sharedFlux` chứa dữ liệu riêng của từng user cho mọi request không? **Không**, trừ khi đã phân vùng/ủy quyền bảo đảm mỗi subscriber chỉ thấy dữ liệu được phép.

**10.** Tại sao `publish` có thể bị subscriber chậm ảnh hưởng? Vì nó điều phối demand chung; nếu một subscriber có demand bằng 0, upstream có thể tạm dừng phát.

**Ghi nhớ:** `share()` là cách multicast tự động, phù hợp khi các subscriber cùng nghe một nguồn đang hoạt động; nó bắt đầu khi subscriber đầu tiên đến và hủy upstream khi mọi subscriber rời. `publish()` trả về `ConnectableFlux` để chủ động gọi `connect()`, hoặc chọn `autoConnect`/`refCount` theo ngưỡng. Cả hai không replay lịch sử. Nếu cần dữ liệu cho subscriber đến muộn, dùng `replay`/cache có giới hạn; nếu cần công việc sống độc lập với client, quản lý lifecycle ở tầng service/queue riêng.

**Tài liệu chính thức:** [Project Reactor 3.8 — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html), [Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html), [Flux API — share/publish](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).