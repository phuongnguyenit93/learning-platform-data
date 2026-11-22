# subscribe, Disposable và quyền kiểm soát subscription trong Reactor

## 1. Bài toán: ai bắt đầu và ai dừng một luồng Mono/Flux?

Trong Project Reactor, **Mono<T>** biểu diễn một luồng có tối đa một phần tử, còn **Flux<T>** biểu diễn luồng từ 0 đến nhiều phần tử. Việc tạo đối tượng Mono/Flux hoặc ghép các toán tử như **map**, **filter**, **flatMap** thường mới là bước **mô tả pipeline**. Với nguồn cold, các công việc trong pipeline chưa được thực hiện cho tới khi có **Subscriber** đăng ký. Phương thức **subscribe(...)** kích hoạt quá trình đăng ký và xử lý tín hiệu.

Vấn đề không chỉ là “làm sao chạy Flux”: một ứng dụng còn phải biết **ai chịu trách nhiệm đăng ký**, **ai nhận lỗi**, **ai được quyền hủy** và **nên quản lý nhu cầu dữ liệu (demand/backpressure) như thế nào**. Đây là trọng tâm của bài.

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa **Publisher**, **Subscriber**, **Subscription** và **Disposable**.
- Phân biệt **subscribe() trả về Disposable** với tín hiệu **onSubscribe(Subscription)**.
- Dùng các overload của **subscribe(...)** để xử lý dữ liệu, lỗi và hoàn thành.
- Dùng **dispose()** để yêu cầu hủy subscription còn hoạt động.
- Dùng **BaseSubscriber** để kiểm soát **request(n)**, **cancel()** và các callback vòng đời.
- Xác định khi nào nên để **Spring WebFlux** tự subscribe thay vì tự gọi subscribe trong mã ứng dụng.

## 2. Ba đối tượng thường bị nhầm lẫn

| Thành phần | Vai trò | Ai tạo hoặc sử dụng? | Thao tác chính |
| --- | --- | --- | --- |
| **Publisher** (Mono/Flux) | Cung cấp một chuỗi tín hiệu theo hợp đồng Reactive Streams | Code tạo pipeline; operator kết hợp nguồn | Được đăng ký bằng **subscribe(...)** |
| **Subscription** (**org.reactivestreams.Subscription**) | Quan hệ đăng ký giữa Publisher và Subscriber, đồng thời điều khiển **demand** | Publisher truyền vào **Subscriber.onSubscribe(subscription)** | **request(n)**, **cancel()** |
| **Disposable** (**reactor.core.Disposable**) | Tay nắm quản lý vòng đời, thường dùng để yêu cầu hủy subscription từ bên ngoài | Các overload **subscribe(...)** nhận lambda trả về | **dispose()**, **isDisposed()** |

**Subscription** là giao diện thuộc Reactive Streams và có quyền **yêu cầu số phần tử**. **Disposable** là giao diện của Reactor có ý nghĩa hủy/dọn dẹp; bản thân Disposable không có **request(n)**. Một subscription có thể được bọc trong Disposable để bên ngoài dừng quá trình nhận dữ liệu. Khi dùng **BaseSubscriber**, đối tượng Subscriber đó cũng hỗ trợ gọi **request**, **cancel** và **dispose**.

Một cách nhìn về luồng điều khiển:

~~~text
Ứng dụng:
Flux/Mono ── subscribe(subscriber) ──> đăng ký

Publisher ── onSubscribe(Subscription) ──> Subscriber
Publisher ── onNext(item) ───────────> Subscriber
Publisher ── onError(err) / onComplete() ──> Subscriber

Subscriber ── Subscription.request(n) ──> Publisher
Subscriber ── Subscription.cancel() ─────> Publisher

Ứng dụng giữ Disposable từ subscribe(lambda)
    └── dispose() ──> yêu cầu hủy subscription
~~~

**onSubscribe** phải đến trước **onNext**, **onError** và **onComplete**. Trong một subscription, **onError** và **onComplete** là hai kết thúc loại trừ nhau. **cancel/dispose** là thao tác điều khiển, không phải một **onComplete** được gửi đến Subscriber. Khi subscription đã kết thúc bình thường hoặc kết thúc lỗi, yêu cầu hủy sau đó thường không còn tác dụng đáng kể.

## 3. subscribe(...) làm gì và khi nào có tác dụng?

Ví dụ:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .map(number -> {
        System.out.println("map " + number);
        return number * 10;
    });

// Chỉ xây dựng pipeline; chưa có "map 1", "map 2", "map 3".
numbers.subscribe(value -> System.out.println("receive " + value));
~~~

Với **Flux.range** và **map** đồng bộ, phần xử lý được thực hiện khi gọi **subscribe**. Đầu ra:

~~~text
map 1
receive 10
map 2
receive 20
map 3
receive 30
~~~

Có ba điểm quan trọng:

1. **subscribe** bắt đầu một **lần đăng ký**. Đối với nguồn cold, gọi **subscribe** lần thứ hai thường kích hoạt việc tạo/phát dữ liệu thêm lần nữa, độc lập với lần thứ nhất. Điều này có thể làm lặp thao tác I/O, truy vấn hoặc side effect nếu không kiểm soát.
2. **subscribe** không đồng nghĩa luôn chặn cho tới khi chạy xong. Nguồn đồng bộ như **Flux.range** có thể hoàn thành ngay trong lời gọi; nguồn bất đồng bộ như **Flux.interval** hay I/O có thể trả quyền điều khiển trước khi phần tử đầu tiên đến.
3. **Mono/Flux** có thể được subscribe bởi **framework**, **StepVerifier** hoặc một operator khác. Không phải lúc nào code ứng dụng cũng trực tiếp gọi **subscribe()**.

**Cold và hot:** ví dụ **Flux.range** là cold, mỗi subscription có chuỗi phần tử riêng. Với nguồn hot (ví dụ một luồng sự kiện đang phát), Subscriber có thể chỉ nhận phần dữ liệu phát sau thời điểm đăng ký; việc đăng ký không nhất thiết phát lại toàn bộ lịch sử.

## 4. Những overload subscribe thường dùng

Các overload lambda của **Flux** và **Mono** thường gặp gồm:

~~~java
publisher.subscribe();

publisher.subscribe(value -> handleValue(value));

publisher.subscribe(
    value -> handleValue(value),
    error -> handleError(error)
);

publisher.subscribe(
    value -> handleValue(value),
    error -> handleError(error),
    () -> onCompleted()
);

publisher.subscribe(
    value -> handleValue(value),
    error -> handleError(error),
    () -> onCompleted(),
    subscription -> subscription.request(1)
);
~~~

Các tên **handleValue**, **handleError** và **onCompleted** trong đoạn trên là tên hàm giả định để giải thích chữ ký, **không phải chương trình Java độc lập**. Phương án viết **subscribe(value, error, complete)** có callback cho phần tử, lỗi và hoàn thành. Overload thứ tư bổ sung callback nhận **Subscription** để chủ động gửi request.

| Dạng | Tín hiệu ứng dụng có thể xử lý trực tiếp | Demand ban đầu |
| --- | --- | --- |
| **subscribe()** | Không truyền callback | Thông thường yêu cầu không giới hạn |
| **subscribe(onNext)** | Mỗi phần tử | Thông thường không giới hạn |
| **subscribe(onNext, onError)** | Phần tử và lỗi | Thông thường không giới hạn |
| **subscribe(onNext, onError, onComplete)** | Phần tử, lỗi và hoàn thành | Thông thường không giới hạn |
| **subscribe(onNext, onError, onComplete, onSubscribe)** | Thêm khả năng điều khiển Subscription ngay từ đầu | **Do callback onSubscribe quyết định** |

Đa số overload lambda sẽ gửi **request(Long.MAX_VALUE)** từ đầu; nghĩa là Subscriber không áp mức demand hữu hạn. **Đây không phải bảo đảm xử lý hiệu quả hoặc vô hạn bộ nhớ**: từng operator và nguồn có thể giới hạn, điều chỉnh hoặc đệm dữ liệu, còn tốc độ xử lý và tài nguyên hệ thống vẫn là ràng buộc thực tế.

Nếu dùng overload bốn callback mà chỉ lưu Subscription và **không gọi request(n)**, Publisher có thể chờ demand mãi và không gửi **onNext**. Với điều khiển request theo từng phần tử, **BaseSubscriber** thường rõ ràng và dễ bảo trì hơn.

**Luôn xử lý lỗi ở ranh giới subscribe thủ công.** Nếu không có callback **onError**, một lỗi bất đồng bộ có thể bị chuyển tới cơ chế báo lỗi mặc định/hook của Reactor, khiến lỗi khó quản lý hoặc bị mất ngữ cảnh nghiệp vụ. Callback **onError** cuối luồng chỉ *tiêu thụ lỗi*, không biến lỗi thành phần tử phục hồi; để phục hồi trong pipeline, dùng operator như **onErrorResume** hoặc **onErrorReturn**.

## 5. Disposable: lấy tay nắm để hủy

Khi dùng overload lambda, phương thức **subscribe(...)** trả về một **Disposable**:

~~~java
Disposable disposable = Flux.interval(Duration.ofSeconds(1))
    .subscribe(
        value -> System.out.println("tick " + value),
        error -> System.err.println("interval failed: " + error)
    );

// Ví dụ: khi màn hình bị đóng, phiên làm việc kết thúc
// hoặc tác vụ đã không còn cần thiết:
disposable.dispose();
~~~

Đoạn trên là snippet, cần import **reactor.core.Disposable**, **reactor.core.publisher.Flux** và **java.time.Duration**. **Flux.interval** phát bất đồng bộ; ở ứng dụng thật, lưu Disposable vào đối tượng sở hữu tác vụ và gọi dispose khi vòng đời kết thúc. Nếu gọi dispose ngay sau subscribe, có thể không kịp nhận tick nào.

Cần hiểu chính xác **dispose()**:

- Đây là **yêu cầu hủy** subscription đang hoạt động, thường chuyển thành **Subscription.cancel()** ở upstream.
- **dispose() không phát onComplete** và không biến hủy thành thành công nghiệp vụ.
- Hủy **không nhất thiết tức thì**: dữ liệu đã phát, callback đang chạy hoặc một nguồn không hỗ trợ dừng tức thời có thể còn tiếp diễn trong thời gian ngắn.
- Gọi dispose nhiều lần về mặt sử dụng phải được xem như thao tác dọn dẹp an toàn; nó không khởi động lại một subscription.
- Nếu source đã kết thúc, gọi dispose không “chạy lại”, không đổi kết quả **onComplete/onError** đã xảy ra.
- Bỏ biến tham chiếu Disposable không phải thao tác hủy có kiểm soát; với nguồn sống lâu hoặc vô hạn, việc không giữ tay nắm có thể khiến tác vụ tồn tại ngoài vòng đời mong muốn.

**isDisposed()** cho biết trạng thái disposed theo đối tượng/triển khai Disposable; đừng coi nó là nguồn sự thật cho trạng thái nghiệp vụ “thành công”, “thất bại” hoặc “đã lưu dữ liệu”. Để quan sát kết thúc, sử dụng tín hiệu Reactor hoặc mô hình kết quả nghiệp vụ phù hợp.

### 5.1. Chọn đúng chủ sở hữu

Với tác vụ tồn tại qua nhiều callback của ứng dụng desktop, event listener hoặc service nền, thành phần **khởi tạo subscription** phải có nơi **giữ Disposable và dọn dẹp khi không còn cần**. Ví dụ quản lý một subscription đang hoạt động:

~~~java
private Disposable active;

void start() {
    stop();
    active = Flux.interval(Duration.ofSeconds(1))
        .subscribe(
            tick -> onTick(tick),
            error -> reportError(error)
        );
}

void stop() {
    if (active != null) {
        active.dispose();
        active = null;
    }
}
~~~

Đây là đoạn minh họa trong một class có sẵn các phương thức **onTick** và **reportError**. Đừng dùng nguyên mẫu trên làm giải pháp an toàn đa luồng: nếu **start/stop** có thể chạy đồng thời, cần cơ chế đồng bộ hoặc **Disposables.swap()** để thay subscription nguyên tử.

Reactor cung cấp **Disposables.composite(...)** để gom nhiều tay nắm và hủy cùng nhau; **Disposables.swap()** hữu ích khi thay tác vụ cũ bằng tác vụ mới (chẳng hạn tìm kiếm mới thay tìm kiếm đang chạy). Cần nhớ: các helper này quản lý hủy, không thay thế logic xử lý lỗi hoặc kết quả nghiệp vụ.

## 6. BaseSubscriber: kiểm soát request(n) và cancel()

**BaseSubscriber<T>** của Reactor thích hợp khi cần tự điều tiết tốc độ nhận dữ liệu. Khác overload subscribe lambda thường yêu cầu không giới hạn, BaseSubscriber cho phép ghi rõ chiến lược demand qua các hook:

- **hookOnSubscribe(Subscription)**: nhận subscription và gửi request ban đầu.
- **hookOnNext(T)**: xử lý một phần tử, quyết định yêu cầu thêm hay hủy.
- **hookOnError(Throwable)**: xử lý lỗi terminal.
- **hookOnComplete()**: xử lý hoàn thành terminal.
- **hookOnCancel()**: phản ứng khi Subscriber chủ động hủy.
- **hookFinally(SignalType)**: dọn dẹp hoặc quan sát lý do kết thúc, gồm hoàn thành, lỗi hoặc hủy.

Ví dụ ý tưởng nhận mỗi lần một phần tử:

~~~java
Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);     // Hàm nghiệp vụ giả định
        request(1);         // Chỉ xin phần tử tiếp theo sau khi xử lý
    }

    @Override
    protected void hookOnError(Throwable error) {
        reportError(error); // Hàm nghiệp vụ giả định
    }
});
~~~

Đoạn này là snippet; **process** và **reportError** cần được tự định nghĩa. Trong hook **request(1)** làm tăng nhu cầu nhận một phần tử; sau khi xử lý một phần tử, gọi tiếp request(1) cho phép phát thêm. Nếu bỏ request ban đầu, một Publisher tôn trọng backpressure có thể không gửi dữ liệu nào.

**request(n)** với **n > 0** là yêu cầu tối đa n phần tử bổ sung, không phải cam kết Publisher chắc chắn phát đủ n. **request(0)** hoặc số âm vi phạm hợp đồng Reactive Streams. Một số operator như **buffer**, **flatMap**, **publishOn** có thể điều chỉnh lượng request ở upstream; số lượng yêu cầu bạn nhìn thấy tại một vị trí không nhất thiết giống ở vị trí khác.

**Một BaseSubscriber chỉ nên sử dụng cho một subscription.** Không tái sử dụng cùng một instance để đăng ký nhiều nguồn độc lập; Reactor có cơ chế hủy subscription cũ nếu dùng lại, nhằm bảo vệ hợp đồng tín hiệu tuần tự. Với mỗi subscription mới, tạo Subscriber mới.

## 7. Ví dụ Java 17+ chạy được: hoàn thành, lỗi, dispose và request hữu hạn

Ví dụ dưới đây hoạt động với **reactor-core 3.8.8**, sử dụng bốn nguồn đồng bộ và một nguồn không phát dữ liệu để giữ output dễ dự đoán. Nó minh họa tách biệt việc **subscribe**, tín hiệu **terminal**, thao tác **dispose** và kiểm soát demand.

Tạo cấu trúc tệp:

~~~text
reactor-subscribe-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── SubscriptionControlDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-subscribe-demo</artifactId>
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
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tệp **src/main/java/SubscriptionControlDemo.java**:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.Disposable;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class SubscriptionControlDemo {

    public static void main(String[] args) {
        System.out.println("=== 1. Complete ===");
        Flux.just(10, 20)
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .subscribe(
                value -> System.out.println("onNext(" + value + ")"),
                error -> System.out.println("onError(" + error + ")"),
                () -> System.out.println("onComplete")
            );

        System.out.println("=== 2. Error ===");
        Flux.<Integer>error(new IllegalStateException("boom"))
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .subscribe(
                value -> System.out.println("onNext(" + value + ")"),
                error -> System.out.println(
                    "onError(" + error.getMessage() + ")"
                ),
                () -> System.out.println("onComplete")
            );

        System.out.println("=== 3. Dispose ===");
        Disposable handle = Flux.<Integer>never()
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .doOnCancel(() -> System.out.println("doOnCancel"))
            .subscribe(
                value -> System.out.println("onNext(" + value + ")"),
                error -> System.out.println("onError(" + error + ")"),
                () -> System.out.println("onComplete")
            );

        handle.dispose();

        System.out.println("=== 4. Manual demand ===");
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("onSubscribe");
                    request(1);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext(" + value + ")");
                    if (value == 2) {
                        cancel();
                    } else {
                        request(1);
                    }
                }

                @Override
                protected void hookOnCancel() {
                    System.out.println("hookOnCancel");
                }
            });
    }
}
~~~

Chạy trong thư mục chứa **pom.xml** (máy có JDK 17+ và Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SubscriptionControlDemo
~~~

Stdout của chương trình:

~~~text
=== 1. Complete ===
onSubscribe
onNext(10)
onNext(20)
onComplete
=== 2. Error ===
onSubscribe
onError(boom)
=== 3. Dispose ===
onSubscribe
doOnCancel
=== 4. Manual demand ===
onSubscribe
onNext(1)
onNext(2)
hookOnCancel
~~~

Phân tích từng phần:

1. **Complete**: **Flux.just** phát hai phần tử, sau đó **onComplete**. Subscriber lambda mặc định yêu cầu đủ demand để nhận chúng.
2. **Error**: **Flux.error** gửi **onError**, không gọi **onComplete**; callback lỗi nhận **IllegalStateException("boom")**.
3. **Dispose**: **Flux.never** không tự phát phần tử hay terminal signal. Sau khi subscribe trả về Disposable, lệnh **dispose()** gây hủy và kích hoạt **doOnCancel**; không xuất hiện **onComplete**.
4. **Manual demand**: **BaseSubscriber** yêu cầu từng phần tử một; khi nhận giá trị 2 thì gọi **cancel()**. Vì nguồn **Flux.range** đồng bộ và tuân thủ demand, các giá trị 3–5 không được gửi đến Subscriber.

Từng phần dùng **một subscription riêng**. Chương trình không sử dụng sleep hoặc đồng bộ thời gian vì nguồn được chọn đều đồng bộ hoặc không phát, nên kết quả trên không phụ thuộc việc scheduler phát tick kịp hay không.

## 8. Quan sát subscription bằng các operator lifecycle

Các operator **doOn...** giúp log và theo dõi pipeline nhưng không tự thay thế việc sở hữu Disposable:

| Operator | Khi nào được gọi? | Có thấy cancel không? |
| --- | --- | --- |
| **doOnSubscribe(s)** | Khi upstream nhận subscription | Không phải callback cho cancel |
| **doOnRequest(n)** | Khi có tín hiệu demand được yêu cầu ở vị trí quan sát | Không |
| **doOnNext(value)** | Khi một phần tử đi qua | Không |
| **doOnError(error)** | Khi có tín hiệu lỗi | Không |
| **doOnComplete()** | Khi Flux hoàn thành bình thường | Không |
| **doOnCancel(action)** | Khi tín hiệu cancel đi qua | **Có** |
| **doFinally(signalType)** | Khi kết thúc bằng complete, error hoặc cancel | **Có**, với **SignalType.CANCEL** |

Ví dụ:

~~~java
Flux<Integer> source = Flux.range(1, 10)
    .doOnSubscribe(s -> log("subscribed"))
    .doOnRequest(n -> log("requested: " + n))
    .doOnCancel(() -> log("cancelled"))
    .doFinally(signal -> log("finally: " + signal));
~~~

Đây là snippet (hàm **log** giả định). Các operator ở vị trí khác nhau có thể thấy **request(n)** khác nhau, do operator ở giữa điều chỉnh demand. **doOnComplete** và **doOnError** không thay thế **doOnCancel**. Nếu cần một điểm dọn dẹp chung cho cả ba đường đi, **doFinally** thường là lựa chọn phù hợp; với tài nguyên có vòng đời phụ thuộc publisher, còn có thể dùng **using/usingWhen**.

**Lưu ý thứ tự và thread:** nhiều nguồn hoàn thành đồng bộ, nhưng pipeline dùng I/O, scheduler hoặc các toán tử bất đồng bộ không bảo đảm callback xảy ra trên thread gọi subscribe. Không coi **doFinally** là cơ chế đợi đồng bộ; mọi thao tác dọn dẹp nên an toàn khi chạy theo ngữ cảnh thực tế của nguồn.

## 9. Với Mono: hoàn thành rỗng và hủy cũng có ý nghĩa

Một **Mono** có thể:

- **Mono.just(value)**: gửi một **onNext(value)** rồi **onComplete**.
- **Mono.empty()**: không có **onNext**, chỉ có **onComplete**.
- **Mono.error(error)**: gửi **onError** và không có **onComplete**.
- **Mono.never()**: không tự gửi phần tử hoặc terminal signal; bên sở hữu có thể gọi **dispose()** để hủy.

Ví dụ **Mono.fromCallable** hoặc **Mono.defer** có thể dùng để hoãn tính toán cho đến lúc subscription; việc gọi subscribe hai lần trên Mono cold có thể kích hoạt tính toán hai lần. **Mono** không có nghĩa “hàm sẽ luôn hoàn thành ngay” hoặc “không cần Disposable”; một Mono đại diện cho yêu cầu mạng vẫn có thể đang chờ và cần cancel nếu kết quả không còn cần thiết.

Trong Mono, **doOnSuccess(value)** nhận **null** khi Mono hoàn thành rỗng (đây là đối số của callback quan sát thành công, **không phải onNext(null)**). Nếu muốn quan sát tín hiệu complete/error/cancel thống nhất, dùng **doFinally**.

## 10. Spring WebFlux: để framework sở hữu subscription ở HTTP boundary

Trong controller WebFlux, cách thông thường là **trả về Mono/Flux**, để Spring WebFlux/Reactor Netty đăng ký đúng thời điểm, nối kết quả với HTTP response, truyền cancellation khi client ngắt kết nối và xử lý lỗi qua pipeline/framework.

Ví dụ controller trả dữ liệu:

~~~java
@GetMapping("/orders/{id}")
public Mono<Order> getOrder(@PathVariable String id) {
    return orderRepository.findById(id);
}
~~~

Snippet giả định có **Order**, **orderRepository** và các import Spring tương ứng. Framework sẽ subscribe khi thực hiện yêu cầu HTTP. Nếu tự gọi **subscribe()** bên trong rồi trả về **Mono.empty()**, có nguy cơ HTTP response kết thúc trước khi tác vụ nền xong; lỗi, context và cancellation của request cũng không còn được nối đúng với tác vụ đó.

So sánh:

~~~java
// Dễ tách công việc khỏi request: cần tránh trong luồng HTTP bình thường.
public Mono<Void> saveWrong(Order order) {
    repository.save(order).subscribe(); // Không truyền lỗi, không quản lý hủy
    return Mono.empty();
}

// Thành phần gọi quyết định khi nào subscribe, hủy và xử lý lỗi.
public Mono<Void> saveCorrect(Order order) {
    return repository.save(order).then();
}
~~~

Hai đoạn trên là ví dụ minh họa trong service có **repository**; tên kiểu cần được cung cấp từ ứng dụng thật. Với **saveCorrect**, lỗi và cancellation vẫn là một phần của chain. Nếu cần hai thao tác liên tiếp, hãy ghép bằng **flatMap**, **then**, **zipWhen**, v.v., thay vì lồng **subscribe** vào **subscribe**.

Tuy nhiên, **subscribe thủ công vẫn có chỗ dùng**: một event listener, công cụ CLI, ứng dụng UI, job do thành phần tự quản hoặc một điểm biên imperative cần chủ động bắt đầu luồng. Khi đó nên xác định chủ sở hữu, truyền callback lỗi, giữ **Disposable** nếu tác vụ có thể kéo dài, và dọn dẹp lúc kết thúc vòng đời.

**Đừng dùng block() trong event-loop WebFlux** để “đợi cho subscribe xong”. **block()** chuyển thành thao tác đồng bộ chờ kết quả, có thể làm nghẽn thread xử lý I/O; quy trình reactive nên được ghép bằng operator.

## 11. Các lỗi phổ biến và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Xây Mono/Flux rồi không thấy gì chạy | Không có Subscriber; nguồn cold chưa được đăng ký | Trả pipeline cho framework hoặc subscribe tại ranh giới thích hợp |
| Một thao tác I/O bị chạy hai lần | Subscribe hai lần vào nguồn cold có side effect | Chỉ subscribe đúng nơi; khi cần chia sẻ kết quả, xem xét operator chia sẻ/cache và vòng đời tương ứng |
| Có phần tử đầu tiên rồi luồng “đứng” | Subscriber chỉ request(1) mà không request tiếp | Kiểm tra demand, **hookOnNext** và operator có thay đổi demand |
| Đóng màn hình nhưng tick nền vẫn tiếp tục | Mất Disposable, không có cleanup | Giữ handle và **dispose()** lúc đóng/stop |
| Gọi dispose nhưng vẫn thấy một callback cuối | Cancel là tín hiệu bất đồng bộ hoặc có phần tử đang trên đường truyền | Thiết kế logic idempotent, không giả định dừng tuyệt đối tức thời |
| Gọi dispose rồi chờ onComplete vô hạn | Cancel không đồng nghĩa complete | Theo dõi **doFinally(CANCEL)** hoặc hook hủy, không chờ terminal thành công |
| Lỗi không được xử lý đúng nơi | **subscribe()** thiếu error consumer hoặc subscribe lồng | Giữ lỗi trong pipeline bằng **onErrorResume**, thêm error consumer tại biên imperative |
| Khó phân biệt “hủy” và “hoàn tất” | Chỉ log doOnComplete/doOnError | Thêm **doOnCancel**, **doFinally** và correlation id nếu cần |
| Tái sử dụng một BaseSubscriber | Subscriber có vòng đời một lần đăng ký | Tạo instance BaseSubscriber mới cho từng subscription |
| Xử lý mất kiểm soát tốc độ | subscribe lambda mặc định yêu cầu unbounded demand | Dùng **BaseSubscriber**, operator backpressure và giới hạn concurrency phù hợp |

Để điều tra một luồng, hãy lần lượt trả lời: **(1) ai subscribe, (2) có onSubscribe không, (3) demand bao nhiêu, (4) ai giữ Disposable, (5) đường đi kết thúc do onComplete, onError hay cancel, (6) có nguồn cold bị đăng ký lặp hay không?** Với pipeline có nhiều nhánh, ghi log theo từng subscription hoặc request id để tránh trộn các sự kiện khác nhau.

## 12. Tự kiểm tra và bài tập

**Câu 1.** Tạo **Flux.interval(Duration.ofSeconds(1))**, gọi subscribe rồi bỏ qua Disposable. Rủi ro là gì?  
**Gợi ý:** nguồn sống lâu có thể tiếp tục phát dù nơi dùng không còn cần dữ liệu; cần quản lý vòng đời và hủy.

**Câu 2.** Một **BaseSubscriber** gửi **request(2)** và nhận hai phần tử. Có chắc nhận phần tử thứ ba không?  
**Đáp án:** không. Nếu không gửi request mới, nguồn tuân thủ backpressure không được phát onNext thứ ba; ngoài ra nguồn có thể kết thúc sớm hoặc thất bại.

**Câu 3.** Phân biệt ba sự kiện **onComplete**, **onError** và **dispose()**.  
**Đáp án:** hai sự kiện đầu là terminal signal từ upstream đến Subscriber (thành công/lỗi); sự kiện cuối là yêu cầu hủy từ bên sở hữu, không tự sinh onComplete.

**Câu 4.** Khi nào gọi **subscribe()** trong controller WebFlux?  
**Đáp án:** với pipeline tạo response, thông thường không gọi thủ công; trả về **Mono/Flux** để framework sở hữu subscription. Chỉ tự đăng ký khi có một ranh giới imperative được thiết kế rõ ràng và có kế hoạch xử lý lỗi/cancel.

**Bài tập mở rộng:** sửa phần **Manual demand** trong ví dụ để yêu cầu lần lượt từng phần tử cho đến giá trị 5, rồi hoàn thành. Thêm **hookOnComplete()** và so sánh output với trường hợp hủy tại giá trị 2. Thử thêm **doFinally** để quan sát **ON_COMPLETE** và **CANCEL**.

## 13. Tài liệu tham khảo

- Project Reactor — Simple Ways to Create a Flux or Mono and Subscribe to It: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor — BaseSubscriber API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html
- Project Reactor — Disposable API: https://projectreactor.io/docs/core/release/api/reactor/core/Disposable.html
- Reactive Streams Specification for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
- Spring Framework — Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
