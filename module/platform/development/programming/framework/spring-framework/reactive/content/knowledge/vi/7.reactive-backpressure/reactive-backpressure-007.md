# Lựa chọn buffer có giới hạn, drop, latest hoặc báo lỗi trong Reactor

## 1. Bài toán: khi nơi phát nhanh hơn nơi nhận

Trong ứng dụng Spring WebFlux, một nguồn dữ liệu có thể phát sự kiện nhanh hơn tốc độ hệ thống xử lý: telemetry cập nhật liên tục, thông báo WebSocket, tín hiệu thị trường, log, kết quả đọc dữ liệu hoặc luồng tích hợp từ API callback. Nếu cứ giữ mọi phần tử trong RAM, bộ nhớ có thể tăng không kiểm soát. Nếu bỏ phần tử hoặc kết thúc luồng tùy tiện, hệ thống có thể mất thông tin nghiệp vụ quan trọng.

Reactive Streams dùng **backpressure**: Subscriber gọi `Subscription.request(n)` để khai báo đang sẵn sàng nhận tối đa `n` phần tử. Publisher và các toán tử phải tôn trọng nhu cầu (*demand*) trên từng liên kết. Khi nguồn không thể hoặc không muốn giảm tốc cho vừa downstream, cần một **chính sách quá tải rõ ràng**.

Bài học này so sánh bốn lựa chọn của `Flux` trong Project Reactor:

- **Buffer có giới hạn:** giữ tạm một số phần tử; khi đầy thì lỗi hoặc áp dụng chính sách loại bỏ đã chọn.
- **Drop:** bỏ từng phần tử mới đến khi không có demand downstream.
- **Latest:** chỉ giữ phần tử mới nhất trong lúc downstream chưa sẵn sàng.
- **Error:** phát lỗi ngay khi phần tử tới mà không có demand để chuyển tiếp.

Sau bài, bạn cần hiểu cơ chế, API, dữ liệu nào có thể mất, tác động đến memory và tính đúng đắn nghiệp vụ, ví dụ Java 17+ chạy được và cách kiểm thử có điều khiển `request`.

## 2. Nền tảng: demand không đồng nghĩa với tốc độ phát

Mỗi lần `request(n)` với `n > 0` bổ sung nhu cầu cho subscription; tổng số `onNext` được phát xuống Subscriber không được vượt tổng demand đã nhận. Giá trị `Long.MAX_VALUE` biểu thị nhu cầu không giới hạn. `cancel()` yêu cầu chấm dứt subscription, nhưng việc hủy không nhất thiết loại bỏ ngay những tín hiệu đang truyền.

~~~text
Subscriber                Boundary                 Upstream
    |                      |                         |
    |---- request(2) ----->|                         |
    |<---- onNext(A) ------|<----- onNext(A) ---------|
    |<---- onNext(B) ------|<----- onNext(B) ---------|
    |    demand = 0        |<----- onNext(C) ---------|
    |                      |                         |
    |  buffer/drop/latest/error là cách xử lý C      |
~~~

Sơ đồ là **minh họa một ranh giới nơi upstream có thể đẩy thêm dữ liệu**; với Publisher thật sự tôn trọng nhu cầu và truyền demand nguyên vẹn, nguồn có thể dừng tại B cho đến khi được yêu cầu tiếp, nên không cần áp dụng các chính sách mất dữ liệu.

Một khác biệt cốt lõi: các `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest` và `onBackpressureError` của Reactor **yêu cầu nhu cầu không giới hạn từ upstream của chính toán tử**, sau đó tự xử lý dữ liệu theo demand downstream. Chúng cung cấp chính sách tại **ranh giới đó**; chúng không phải cơ chế gửi lệnh làm chậm nhà sản xuất bên ngoài. Đó là lý do các toán tử này có thể làm tràn buffer hoặc loại bỏ dữ liệu ngay cả khi nguồn `Flux.range` vốn hỗ trợ backpressure.

Với nhiều dạng `subscribe(...)` sử dụng lambda, Reactor mặc định yêu cầu `Long.MAX_VALUE`. Khi muốn kiểm tra quá tải phải **chủ động khống chế demand**, ví dụ dùng `BaseSubscriber` hoặc `StepVerifier.create(publisher, 0)`. Nếu downstream ngay lập tức request unbounded, các tình huống overflow/drop thường không xuất hiện trong ví dụ.

## 3. Bảng so sánh chính sách

| Toán tử | Khi downstream chưa có demand | Bộ nhớ phụ trội ở boundary | Có mất dữ liệu? | Tín hiệu lỗi khi quá tải? | Ví dụ phù hợp |
| --- | --- | --- | --- | --- | --- |
| `onBackpressureBuffer(maxSize)` | Xếp hàng tối đa `maxSize` phần tử, sau đó overflow | Có giới hạn theo **số phần tử** | Phần tử tràn bị từ chối; stream lỗi | Có | Bùng phát ngắn, muốn giữ thứ tự và phát hiện khi vượt ngưỡng |
| `onBackpressureBuffer(maxSize, DROP_OLDEST)` | Hàng đầy thì bỏ phần tử cũ nhất, giữ phần tử mới | Có giới hạn | Có | Không phải do buffer đầy | Hàng đợi ưu tiên dữ liệu gần hiện tại |
| `onBackpressureBuffer(maxSize, DROP_LATEST)` | Hàng đầy thì bỏ **phần tử mới đến** | Có giới hạn | Có | Không phải do buffer đầy | Giữ batch đang chờ, không nhận thêm sự kiện khi đầy |
| `onBackpressureDrop()` | Không có demand thì bỏ phần tử mới đến ngay | Không giữ backlog ở chính toán tử | Có | Không do việc drop | Sự kiện có thể lấy mẫu hoặc bỏ qua |
| `onBackpressureLatest()` | Ghi đè phần tử đang giữ bằng phần tử mới nhất | Tối đa một phần tử chờ ở toán tử này | Có | Không do việc ghi đè | Snapshot trạng thái, giá trị cảm biến hiện thời |
| `onBackpressureError()` | Phát `onError` khi phần tử đến mà không thể chuyển tiếp | Không giữ backlog ở toán tử này | Luồng thất bại | Có | Mất một phần tử là không chấp nhận được |
 
**Lưu ý:** giới hạn trên chỉ áp dụng bộ nhớ/hàng đợi do toán tử cụ thể quản lý; các buffer ở upstream, scheduler, network hay downstream có thể tồn tại độc lập. Một `onBackpressureBuffer(maxSize)` không bảo đảm tổng bộ nhớ cả pipeline có giới hạn.

## 4. Buffer có giới hạn: giữ dữ liệu nhưng có ngưỡng rõ ràng

API cơ bản:

~~~java
Flux<T> bounded = source.onBackpressureBuffer(maxSize);
~~~

Reactor yêu cầu nhiều dữ liệu từ upstream và xếp những phần tử không chuyển ngay được vào hàng đợi tối đa `maxSize`. Khi phần tử tiếp theo tới trong lúc buffer đầy, nguồn upstream bị hủy và pipeline chuyển sang lỗi overflow. **Lỗi này có thể được hoãn gửi xuống Subscriber cho đến khi các phần tử đã đệm được tiêu thụ**. Vì thế không nên giả định tất cả `onBackpressureBuffer` báo lỗi ngay lập tức đến downstream.

Ví dụ ý tưởng với 5 phần tử `1,2,3,4,5`, không có demand ban đầu và `maxSize=2`:

~~~text
Upstream:        1   2   3   4   5
Buffer ban đầu: [1]
Sau phần tử 2:  [1,2]
Phần tử 3:      tràn, nguồn bị cancel, chờ phát lỗi
Downstream:     request(2) → onNext(1), onNext(2), onError(overflow)
~~~

Nguồn đã hủy sau phần tử 3 nên không nhất thiết phát tới 4, 5. Nếu upstream bất đồng bộ, thời điểm cancel và các tín hiệu đang chạy có thể tạo những hiệu ứng timing khác; sơ đồ nhằm mô tả nguyên tắc.

Có overload để biết phần tử gây tràn:

~~~java
Flux<T> bounded = source.onBackpressureBuffer(
        256,
        element -> recordOverflow(element)
);
~~~

`recordOverflow` ở đây là callback của ứng dụng. Nó chạy khi bị tràn, giúp quan sát hoặc giải phóng tài nguyên gắn với phần tử. Không dùng callback như một cách chuyển phần tử sang một luồng thứ hai mà không có chính sách về thứ tự, retry và backpressure.

### 4.1. Khi buffer đầy, lựa chọn ERROR, DROP_OLDEST hoặc DROP_LATEST

Reactor có enum `reactor.core.publisher.BufferOverflowStrategy`:

~~~java
Flux<T> oldest = source.onBackpressureBuffer(
        2, BufferOverflowStrategy.DROP_OLDEST);

Flux<T> newestRejected = source.onBackpressureBuffer(
        2, BufferOverflowStrategy.DROP_LATEST);

Flux<T> failed = source.onBackpressureBuffer(
        2, BufferOverflowStrategy.ERROR);
~~~

Đây là đoạn **minh họa API** với `source`, `T` do ứng dụng cung cấp; nếu đưa vào tệp Java, cần `import reactor.core.publisher.BufferOverflowStrategy;` và khai báo `source` thích hợp.

Trong trường hợp cả năm phần tử được phát khi downstream chưa request và buffer tối đa hai phần tử:

- `DROP_OLDEST`: nhận 1, 2; phần tử 3 thay 1, phần tử 4 thay 2, phần tử 5 thay 3 → cuối cùng còn **4, 5**.
- `DROP_LATEST`: nhận 1, 2; phần tử mới 3, 4, 5 đều bị loại vì buffer đầy → cuối cùng còn **1, 2**.
- `ERROR`: giữ 1, 2; gặp 3 thì chuyển sang trạng thái overflow; phần tử trong buffer vẫn có thể được chuyển xuống trước khi báo lỗi.

Tên `DROP_LATEST` trong `BufferOverflowStrategy` đặc biệt dễ hiểu sai: ở đây nó **loại bỏ phần tử mới đến**, không phải “chỉ giữ giá trị mới nhất” như `onBackpressureLatest()`. Muốn giữ một giá trị mới nhất, dùng chính `onBackpressureLatest`.

Overload mở rộng:

~~~java
source.onBackpressureBuffer(
        2,
        element -> onDiscardedFromFullBuffer(element),
        BufferOverflowStrategy.DROP_OLDEST
);
~~~

Callback được gọi với **phần tử thực sự bị loại**; với `DROP_OLDEST` nó có thể là phần tử cũ đang nằm trong buffer, không nhất thiết là sự kiện mới tới. Nếu dùng `ERROR`, lỗi có thể chỉ đi xuống sau khi backlog đã được xử lý. Việc có callback không thay thế xử lý lỗi với `onError`.

### 4.2. Không dùng buffer không giới hạn cho nguồn không kiểm soát

`source.onBackpressureBuffer()` không có giới hạn dung lượng cụ thể và có thể tăng RAM không giới hạn trong tình huống producer liên tục nhanh hơn consumer. Với nguồn sự kiện lâu dài hoặc dữ liệu có payload lớn, cần tránh mặc định này.

`maxSize` đếm **số phần tử**, không đếm byte. Hai buffer cùng `maxSize` có thể chiếm bộ nhớ rất khác nếu phần tử là số nguyên, chuỗi lớn hay đối tượng chứa bộ đệm byte. Cần đo kích thước payload thực, đặt ngưỡng dựa trên khả năng xử lý đỉnh và thời gian bùng phát, theo dõi dung lượng hàng đợi, tuổi phần tử và số lần overflow.

Một số overload `onBackpressureBuffer(Duration ttl, int maxSize, Consumer onBufferEviction)` bổ sung thời hạn giữ phần tử; chúng phù hợp khi dữ liệu quá cũ mất giá trị, nhưng phải xử lý việc bị loại do hết TTL và bảo đảm hiểu rõ cách eviction diễn ra. Giới hạn thời gian không thay cho giới hạn bộ nhớ.

## 5. Drop: không có demand thì bỏ phần tử mới

Cú pháp:

~~~java
Flux<T> stream = source.onBackpressureDrop();
Flux<T> monitored = source.onBackpressureDrop(
        item -> reportDropped(item)
);
~~~

`onBackpressureDrop` không duy trì backlog của chính toán tử. Nếu downstream còn demand thì chuyển phần tử; nếu đã hết demand thì loại phần tử vừa đến. Dữ liệu bị bỏ **không tự được gửi lại** khi Subscriber request thêm sau này.

Ví dụ không request phần tử nào trong thời gian nguồn phát 1..5:

~~~text
Nguồn phát:   1  2  3  4  5
Demand:       0  0  0  0  0
Drop:         1  2  3  4  5
Downstream:   không có onNext, có thể nhận onComplete
~~~

Phù hợp với bản cập nhật telemetry lấy mẫu, log debug nhiều và tín hiệu mà người dùng không bắt buộc nhìn thấy mọi điểm. **Không phù hợp** nếu từng phần tử là giao dịch, lệnh thanh toán hoặc sự kiện kiểm toán bắt buộc lưu.

Nên đếm số lần drop, theo dõi tỷ lệ mất dữ liệu và dùng callback chỉ làm việc nhẹ, tránh blocking trong đường phát. Nếu phần tử chứa tài nguyên cần giải phóng, chọn hook cleanup hỗ trợ discard và thiết kế việc giải phóng an toàn, idempotent.

## 6. Latest: giữ đúng phần tử mới nhất khi chờ consumer

`source.onBackpressureLatest()` chỉ giữ một phần tử đang chờ; khi không có demand mà có giá trị mới, nó thay phần tử đang giữ bằng giá trị vừa đến. Downstream request lại thì nhận giá trị mới nhất mà boundary đang có, chứ không nhận toàn bộ lịch sử.

Với 1..5 được phát lúc demand = 0:

~~~text
Sau 1: latest = 1
Sau 2: latest = 2 (bỏ 1)
Sau 3: latest = 3 (bỏ 2)
Sau 4: latest = 4 (bỏ 3)
Sau 5: latest = 5 (bỏ 4)
Khi request(1): downstream nhận 5, rồi hoàn thành nếu nguồn đã hoàn tất
~~~

Một phần tử mới đến **khi còn demand** có thể được gửi ngay, không nhất thiết phải qua ô chờ latest. “Latest” cũng không có nghĩa luôn gửi một giá trị mỗi giây hay tự điều chỉnh tần suất; nó chỉ quy định cách xử lý khi downstream thiếu demand.

Phù hợp cho UI hiển thị mức CPU hiện tại, vị trí mới nhất, giá trị đồng hồ hoặc snapshot có thể thay thế nhau. Không phù hợp với event diễn tả **chuyển trạng thái phải được ghi nhận đủ** (chẳng hạn “đã trừ tiền 10 đơn vị”); chỉ giữ chuyển động mới nhất sẽ làm mất các thay đổi trung gian.

**Phân biệt:** `onBackpressureLatest()` giữ tối đa một phần tử chờ. `onBackpressureBuffer(2, DROP_OLDEST)` giữ hai phần tử cuối trong ví dụ; `onBackpressureBuffer(2, DROP_LATEST)` lại giữ hai phần tử đầu. Cả ba không tương đương.

## 7. Error: coi mất dữ liệu là vi phạm bắt buộc xử lý

`source.onBackpressureError()` phát `onError` khi nguồn cố đưa phần tử qua ranh giới mà downstream chưa có demand. Nó không xếp hàng để đợi và không âm thầm làm mất dữ liệu. Reactor sử dụng lỗi overflow, thường có thể xác định bằng `Exceptions.isOverflow(error)`.

~~~java
import reactor.core.Exceptions;
import reactor.core.publisher.Flux;

Flux<Integer> strict = Flux.range(1, 5)
        .onBackpressureError();

strict.subscribe(
        value -> System.out.println("next=" + value),
        error -> System.out.println("overflow=" + Exceptions.isOverflow(error))
);
~~~

**Đoạn này chỉ minh họa callback**. Với overload `subscribe` dạng lambda, downstream thường yêu cầu `Long.MAX_VALUE`, nên ví dụ trên có thể **không phát overflow**; để kiểm tra thật sự cần Subscriber có demand giới hạn hoặc `StepVerifier` (xem mục 8–9).

`onBackpressureError` phù hợp khi mất dữ liệu là không được phép và cần dừng nhánh xử lý để báo lỗi/khôi phục. Tuy nhiên **báo lỗi không tự bảo đảm giao dịch được lưu**. Một khi đã hủy nguồn, cần chiến lược nghiệp vụ rõ ràng như retry có kiểm soát từ nguồn có thể tái đọc, durable queue, dead-letter hoặc phục hồi snapshot. Không tự động dùng `onErrorResume` để bỏ qua overflow rồi báo thành công nếu dữ liệu bị mất là nghiêm trọng.

Khác biệt với `onBackpressureBuffer(maxSize)` hoặc `BufferOverflowStrategy.ERROR`: buffered overflow có thể **chờ xả backlog trước khi chuyển onError**, còn `onBackpressureError()` phát lỗi khi thiếu demand mà không có backlog của toán tử này để xả.

## 8. Chương trình Java 17+ chạy được với nhu cầu bằng 0

Ví dụ tạo nguồn đồng bộ `Flux.range(1,5)`. `BaseSubscriber` được cấu hình **không request trong `hookOnSubscribe`**. Các toán tử onBackpressure tự request upstream không giới hạn nên năm phần tử được đẩy đến boundary, và chính sách quá tải được kích hoạt. Sau khi nguồn phát xong, chương trình mới gọi `request(...)` để xem phần tử còn chờ.

Cấu trúc dự án Gradle:

~~~text
reactor-backpressure-demo/
├── build.gradle
└── src/main/java/BackpressureDemo.java
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
    mainClass = 'BackpressureDemo'
}
~~~

`src/main/java/BackpressureDemo.java`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.Exceptions;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;

public class BackpressureDemo {

    private static void run(
            String label, Flux<Integer> stream, long requestAfter) {

        System.out.println("[" + label + "]");

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                // Cố ý không request ở đây để tạo tình huống quá tải.
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("onNext=" + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("onComplete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println(
                        "overflow=" + Exceptions.isOverflow(error));
            }
        };

        stream.subscribe(subscriber);

        if (requestAfter > 0) {
            subscriber.request(requestAfter);
        }
    }

    public static void main(String[] args) {
        run("bounded", Flux.range(1, 5)
                .onBackpressureBuffer(2), 2);

        run("drop oldest", Flux.range(1, 5)
                .onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_OLDEST), 2);

        run("drop latest incoming", Flux.range(1, 5)
                .onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_LATEST), 2);

        run("drop", Flux.range(1, 5)
                .onBackpressureDrop(), 1);

        run("latest", Flux.range(1, 5)
                .onBackpressureLatest(), 1);

        run("error", Flux.range(1, 5)
                .onBackpressureError(), 1);
    }
}
~~~

Chạy bằng Gradle đã cài trong thư mục dự án:

~~~bash
gradle -q run
~~~

Nếu dự án có Gradle wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows. Với `Flux.range` đồng bộ và request được điều khiển như trên, stdout **do chương trình tạo ra**:

~~~text
[bounded]
onNext=1
onNext=2
overflow=true
[drop oldest]
onNext=4
onNext=5
onComplete
[drop latest incoming]
onNext=1
onNext=2
onComplete
[drop]
onComplete
[latest]
onNext=5
onComplete
[error]
overflow=true
~~~

Diễn giải chính xác:

1. `bounded` giữ 1 và 2, gặp phần tử thứ ba thì overflow, nhưng chuyển lỗi xuống **sau khi** hai phần tử đang chờ được request và tiêu thụ.
2. `drop oldest` thay nội dung buffer khi đầy, nên chỉ còn 4 và 5.
3. `drop latest incoming` giữ hai phần tử cũ 1 và 2, từ chối 3, 4, 5.
4. `drop` không giữ phần tử nào vì demand vẫn bằng 0 khi nguồn phát xong; `request(1)` sau đó không thể phục hồi dữ liệu đã bỏ.
5. `latest` chỉ giữ 5 và hoàn thành khi đã chuyển phần tử chờ.
6. `error` gặp phần tử đầu tiên khi demand = 0 thì overflow ngay.

Các kết quả này cố ý dùng **nguồn đồng bộ và thứ tự thao tác xác định**. Với nguồn từ mạng, scheduler, hot publisher hoặc nhiều subscriptions, không kết luận thứ tự log đa luồng hoặc số phần tử còn chờ chỉ từ một lần chạy ngẫu nhiên.

## 9. Kiểm thử chính sách bằng StepVerifier

Trong dự án có JUnit 5, thêm `reactor-test` cùng họ phiên bản Reactor vào test scope:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/test/java/BackpressurePolicyTest.java`:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.Exceptions;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressurePolicyTest {

    @Test
    void boundedBufferErrorsAfterDrainingQueuedValues() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureBuffer(2), 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .expectErrorMatches(Exceptions::isOverflow)
            .verify();
    }

    @Test
    void dropOldestKeepsTwoMostRecentItems() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_OLDEST), 0)
            .thenRequest(2)
            .expectNext(4, 5)
            .verifyComplete();
    }

    @Test
    void dropLatestRejectsNewItemsWhenFull() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureBuffer(
                        2, BufferOverflowStrategy.DROP_LATEST), 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .verifyComplete();
    }

    @Test
    void dropDiscardsAllWithoutDemand() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureDrop(), 0)
            .verifyComplete();
    }

    @Test
    void latestKeepsOnlyFinalItemWithoutDemand() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureLatest(), 0)
            .thenRequest(1)
            .expectNext(5)
            .verifyComplete();
    }

    @Test
    void errorFailsAtFirstUnrequestedElement() {
        StepVerifier.create(
                Flux.range(1, 5).onBackpressureError(), 0)
            .expectErrorMatches(Exceptions::isOverflow)
            .verify();
    }
}
~~~

`StepVerifier.create(publisher, 0)` tạo Subscriber có **initial request bằng 0**; `thenRequest(n)` chỉ cấp demand ở bước kiểm thử chủ động. Đây là lý do các tình huống trên kiểm tra được overload thật sự; nếu chỉ dùng `subscribe(System.out::println)`, Subscriber thường yêu cầu không giới hạn nên không tạo áp lực.

Khi viết test cho nguồn thật có scheduler, nên kiểm soát thời gian và điểm phát, tránh dựa vào `Thread.sleep` hoặc thứ tự timing ngẫu nhiên. Có thể bổ sung test `cancel`, tài nguyên bị discard và các mức demand khác nhau nếu mã nghiệp vụ yêu cầu.

## 10. Chọn chính sách theo tính chất dữ liệu

### 10.1. Tình huống nên buffer có giới hạn

Dùng khi có **burst ngắn**, downstream vẫn đủ năng lực xử lý trung bình, phần tử cần giữ thứ tự và còn tài nguyên bộ nhớ. Chọn `maxSize` dựa trên đo đạc thực tế, xác định phương án khi đầy: overflow báo lỗi, ưu tiên dữ liệu cũ hoặc mới. Nếu không thể bỏ bất kỳ sự kiện nào, nên để quá tải **hiện rõ** và tính đến hàng đợi bền vững ở tầng phù hợp.

Ví dụ: xử lý danh sách công việc không được phép mất; có thể buffer hữu hạn để hấp thụ tăng tải ngắn, nhưng khi vượt ngưỡng cần dừng nhận mới hoặc trả lỗi, thay vì âm thầm mất việc.

### 10.2. Tình huống nên drop

Dùng khi giá trị trung gian không có tính bắt buộc, ví dụ thông số quan sát phát dày hoặc bản tin debug. Hệ thống chấp nhận rằng khi subscriber bận, phần tử đến lúc đó không được xem. Không chọn drop cho hóa đơn, thay đổi số dư, thông báo nghĩa vụ pháp lý hay message cần xử lý chính xác.

### 10.3. Tình huống nên latest

Dùng cho mô hình **trạng thái hiện tại thay thế trạng thái trước**: nhiệt độ hiện tại, vị trí cuối cùng, mức tiến độ mới nhất, trạng thái dashboard. Nếu người dùng chỉ cần biết “bây giờ là bao nhiêu”, bỏ cập nhật cũ giúp giữ tính mới. Với chuỗi **sự kiện** tích lũy hoặc chuyển trạng thái có ý nghĩa riêng, latest có thể làm sai nghiệp vụ.

### 10.4. Tình huống nên error

Dùng khi mất một phần tử là lỗi phải báo ra để hệ thống dừng/phục hồi và cần tránh tạo cảm giác xử lý thành công. Hãy thiết kế điểm phát hiện overflow, cách trả lỗi cho client, retry nếu nguồn có khả năng phát lại, và khả năng quan sát. Với HTTP/WebFlux, một `onError` cuối luồng có thể khiến phản hồi thất bại hoặc kết nối đóng tùy lúc lỗi đến; không hứa luôn chuyển được thành mã HTTP cụ thể sau khi response đã được gửi.

### 10.5. Bảng quyết định

| Câu hỏi | Gợi ý |
| --- | --- |
| Dữ liệu **không thể mất**? | Ưu tiên truyền demand ngược nguồn hoặc durable queue; cân nhắc `onBackpressureError`/buffer hữu hạn có overflow rõ ràng. |
| Chỉ quá tải trong khoảng ngắn? | Buffer hữu hạn và đo queue depth, overflow count. |
| Có thể bỏ mọi bản tin lúc bận? | `onBackpressureDrop`. |
| Chỉ cần trạng thái mới nhất? | `onBackpressureLatest`. |
| Muốn giữ một số bản tin mới, bỏ bản tin cũ khi đầy? | `onBackpressureBuffer(maxSize, DROP_OLDEST)`. |
| Muốn giữ backlog cũ đã được chấp nhận, từ chối bản tin mới? | `onBackpressureBuffer(maxSize, DROP_LATEST)`. |
| Muốn thiếu demand phát hiện ngay? | `onBackpressureError`. |

## 11. Ranh giới với các API liên quan

Không nhầm `onBackpressure...` với `Flux.create` và `Flux.push`. Khi tự bridge API callback, `FluxSink.OverflowStrategy` có các lựa chọn như `BUFFER`, `DROP`, `LATEST` và `ERROR` ở **cấp sink tạo nguồn**. `FluxSink.OverflowStrategy.BUFFER` mặc định có thể là unbounded; chọn sink strategy đúng từ đầu là quyết định ở producer. Còn `onBackpressureBuffer/Drop/Latest/Error` là các **toán tử gắn vào một Flux** để xử lý chênh lệch demand tại vị trí đó.

`limitRate(n)` và các cấu hình `prefetch` điều chỉnh **mẫu request** được truyền upstream; chúng không tương đương với drop/latest. `publishOn(scheduler)` đưa dữ liệu qua hàng đợi và giới hạn prefetch riêng; nó có thể làm thay đổi nơi backlog được tích lũy, nhưng không thay thế chính sách mất dữ liệu cần thiết. Dùng `subscribeOn`/`publishOn` để chọn thread hợp lý không tự giải quyết quá tải kéo dài.

Các toán tử `sample`, `sampleTimeout` hoặc `throttleLast` (nếu có trong API/version) mang ý nghĩa **lấy mẫu theo thời gian/điều kiện**; chúng không đồng nhất với `onBackpressureDrop` vốn dựa vào demand. Nếu cần tần suất báo cáo cố định, đừng dùng drop như một bộ điều tốc thay cho sampling.

## 12. Quan sát, dọn tài nguyên và lỗi thực tế

Trong production, lựa chọn chính sách phải đi với chỉ số và quy tắc xử lý mất dữ liệu:

- **Theo dõi:** số lần overflow, phần tử bị drop/evict, độ sâu backlog, tuổi phần tử trong queue, tốc độ phát/tiêu thụ, độ trễ và bộ nhớ thực. Không chỉ dựa vào số lượng phần tử nếu payload không đồng đều.
- **Dọn tài nguyên:** các phần tử có thể gắn tài nguyên như `DataBuffer`, byte buffer hoặc handle cần release. Reactor hỗ trợ `doOnDiscard(type, handler)` ở các toán tử có discard support; hãy đặt hook đúng vị trí downstream và kiểm tra Javadoc của từng toán tử. Cleanup nên idempotent và không chặn; nếu đã dùng callback overflow/drop và `doOnDiscard`, tránh release trùng.
- **Lỗi:** xử lý `onError` như một tình huống lỗi thực; đừng dùng `onErrorComplete` hoặc retry vô hạn để che overflow khi yêu cầu không mất dữ liệu. Retry có thể đăng ký lại và phát trùng phần tử nếu nguồn không bảo đảm idempotency.
- **Hủy:** `cancel()` có thể làm mất phần tử còn trong queue; phần tử đã nhận upstream không đồng nghĩa đã được commit ở downstream. Với nghiệp vụ cần xác nhận, dùng acknowledgement hoặc transaction ở ranh giới phù hợp.
- **Đặt toán tử:** vị trí của chính sách so với `map`, `flatMap`, `publishOn` và các buffer khác ảnh hưởng phần tử nào được giữ, chi phí đã bỏ ra và dòng demand đi qua. Đo trên pipeline thực tế, không phỏng đoán từ hình vẽ đơn giản.

Ví dụ tăng metric số lần drop trong một dịch vụ có sẵn bộ đếm:

~~~java
Flux<Event> monitored = events.onBackpressureDrop(
        dropped -> metrics.incrementDroppedEvents()
);
~~~

`Event`, `events` và `metrics` là thành phần do ứng dụng cung cấp; đây là **đoạn minh họa không độc lập**. Nếu muốn kiểm tra kích thước đối tượng/cleanup, thực hiện thêm xử lý theo loại tài nguyên và chính sách thực tế, không giả định việc drop miễn phí.

## 13. Lỗi thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Dùng `onBackpressureBuffer()` không giới hạn với nguồn vô hạn | Backlog tăng liên tục, nguy cơ hết RAM. | Đặt `maxSize`, quan sát và thiết kế overflow. |
| Nghĩ buffer hữu hạn luôn mất phần tử im lặng khi đầy | Overload mặc định `onBackpressureBuffer(maxSize)` gây overflow error. | Hiểu chính xác overload và strategy. |
| Nhầm `DROP_LATEST` với `onBackpressureLatest` | Một bên bỏ **phần tử mới đến**, bên kia giữ **mới nhất**. | Viết test zero-demand phân biệt 1,2 với 5. |
| Nghĩ `onBackpressureDrop` sẽ giữ dữ liệu chờ request sau | Giá trị đã bỏ không thể phục hồi. | Chỉ dùng khi loss hợp lệ, đo drop rate. |
| Gọi `subscribe(System.out::println)` để kiểm thử drop | Subscriber thường request unbounded, khó thấy overflow. | Dùng `BaseSubscriber` hoặc `StepVerifier.create(...,0)`. |
| Dùng `onBackpressureLatest` cho event tài chính | Mất event trung gian, dẫn đến tính toán sai. | Dùng nhu cầu thật, queue bền vững và ack. |
| Nghĩ `onBackpressureError` báo lỗi giống buffer bounded ngay khi source phát | Buffer bounded có thể phải drain backlog trước khi lỗi xuống. | Test chính xác thứ tự phần tử/lỗi. |
| Cho rằng đặt toán tử downstream sẽ làm producer bên ngoài tự chậm lại | Các toán tử này request không giới hạn từ upstream và tự áp policy. | Ưu tiên backpressure xuyên suốt hoặc tác động ở producer nếu có thể. |
| Xử lý drop nhưng quên release pooled buffers | Rò rỉ tài nguyên off-heap hoặc handle. | Dùng đúng callback discard/cleanup idempotent. |
| Retry overflow vô hạn | Quá tải lặp lại, có thể tạo trùng hoặc làm tình hình tệ hơn. | Retry có giới hạn, backoff, idempotency và khả năng tái đọc. |

## 14. Tự kiểm tra

1. Upstream phát `1..5` trong lúc downstream request 0, `onBackpressureBuffer(2, DROP_OLDEST)` giữ gì? **4, 5**.
2. Cùng tình huống nhưng `DROP_LATEST`? **1, 2**, vì loại sự kiện mới khi đầy.
3. `onBackpressureLatest()` giữ gì? **Chỉ 5**.
4. `onBackpressureDrop()` nhận `request(1)` sau khi nguồn đã phát và hoàn tất thì có khôi phục được 1..5 không? **Không**.
5. `onBackpressureError()` khác gì buffer bounded `ERROR`? **Error không giữ backlog chờ; buffer bounded có thể chuyển lỗi sau khi drain backlog.**
6. Vì sao `Long.MAX_VALUE` có thể làm test không kích hoạt drop? **Vì downstream đã yêu cầu không giới hạn; không có thiếu demand tại boundary.**
7. `maxSize` có phải kích thước bộ nhớ theo byte không? **Không, là số phần tử trong buffer; vẫn phải quan sát payload và các queue khác.**
8. Trong hệ thống giao dịch không được phép mất event, chọn drop/latest để tăng throughput có an toàn không? **Không. Cần điều tiết tại nguồn hoặc cơ chế lưu bền vững, retry/ack có kiểm soát.**

**Ghi nhớ:** lựa chọn backpressure là quyết định về **tính đúng đắn dữ liệu**, **trễ**, **bộ nhớ** và **cách thất bại**. Buffer hữu hạn ưu tiên giữ backlog có giới hạn; drop chấp nhận mất các sự kiện lúc bận; latest chỉ giữ trạng thái mới nhất; error nêu rõ việc thiếu demand. Hãy quyết định theo ngữ nghĩa dữ liệu trước, sau đó viết test với demand được điều khiển và đo hành vi trong pipeline thật.

## Tài liệu tham khảo

- [Reactor Flux Javadoc: onBackpressureBuffer, onBackpressureDrop, onBackpressureLatest, onBackpressureError](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Reactor BufferOverflowStrategy Javadoc: ERROR, DROP_OLDEST, DROP_LATEST](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BufferOverflowStrategy.html).
- [Reactor Reference Guide: On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- [Reactor Reference Guide: Programmatically Creating a Sequence và FluxSink OverflowStrategy](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html).
- [Reactor Exceptions Javadoc: isOverflow](https://projectreactor.io/docs/core/release/api/reactor/core/Exceptions.html).
- [Project Reactor Testing: StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
