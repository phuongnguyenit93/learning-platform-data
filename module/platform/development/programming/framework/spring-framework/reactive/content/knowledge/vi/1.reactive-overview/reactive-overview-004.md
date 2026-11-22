# Điều tiết nhu cầu (backpressure) giữa bên phát và bên nhận

Trong **Spring WebFlux** và **Project Reactor**, *backpressure* là cơ chế để bên nhận thông báo cho bên phát biết mình sẵn sàng nhận **bao nhiêu phần tử tiếp theo**. Đây là một phần của giao thức Reactive Streams, giúp luồng dữ liệu có thể phản ứng với tốc độ tiêu thụ thực tế mà không mặc định đẩy mọi phần tử vào bộ nhớ.

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Giải thích vai trò của `Publisher`, `Subscriber`, `Subscription` và tín hiệu `request(n)`.
- Theo dõi số lượng phần tử đã yêu cầu nhưng chưa nhận (*outstanding demand*), hiểu khi nào luồng tạm dừng, hoàn tất hoặc bị hủy.
- Phân biệt điều tiết nhu cầu với hàng đợi, giới hạn tốc độ, kiểm soát tải và cơ chế bất đồng bộ.
- Dùng Reactor để yêu cầu dữ liệu theo đợt, kiểm tra nhu cầu, và chọn chính sách phù hợp khi nguồn không thể chậm lại.
- Nhận biết phạm vi mà backpressure có thể truyền qua một ứng dụng Spring WebFlux và những giới hạn ở nguồn/đích bên ngoài.

## 1. Tại sao cần backpressure?

Giả sử một dịch vụ nhận 10.000 sự kiện/giây nhưng xử lý được 200 sự kiện/giây. Nếu nguồn cứ phát tự do và mỗi sự kiện đều phải giữ lại, số sự kiện chờ có thể tăng khoảng **9.800/giây** (khi tốc độ ổn định). Bộ nhớ, độ trễ hoặc cả hai sẽ tăng theo thời gian. Chạy bất đồng bộ chỉ chuyển nơi công việc diễn ra; bản thân nó không giải quyết sự chênh lệch tốc độ.

Có ba hướng xử lý khác nhau cần phân biệt:

1. **Điều tiết từ nguồn:** bên nhận yêu cầu từng lượng phần tử; nguồn có khả năng tôn trọng yêu cầu thì chỉ phát trong giới hạn đó.
2. **Chứa hoặc loại bớt:** nếu nguồn từ bên ngoài vẫn đẩy dữ liệu, hệ thống có thể dùng bộ đệm có giới hạn, bỏ phần tử cũ/mới, chỉ giữ giá trị cuối, hoặc báo lỗi.
3. **Điều khiển tốc độ ở tầng khác:** giới hạn request/giây, giới hạn số tác vụ đồng thời, tạm dừng đọc từ broker, hoặc trả tín hiệu quá tải cho client.

Backpressure thuộc hướng thứ nhất. Hai hướng còn lại có thể cần thiết để xây dựng đường truyền có khả năng chịu tải thật sự.

## 2. Hợp đồng Reactive Streams

Trong mô hình Reactive Streams, các vai trò chính là:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Publisher<T>` | Cung cấp chuỗi phần tử hoặc tín hiệu kết thúc/lỗi sau khi có đăng ký. |
| `Subscriber<T>` | Đăng ký nhận dữ liệu và xử lý `onNext`, `onError`, `onComplete`. |
| `Subscription` | Liên kết giữa một lần đăng ký và nguồn; cho phép `request(n)` hoặc `cancel()`. |
| `Processor<T,R>` | Khái niệm vừa nhận vừa phát, thường được thay thế trong code Reactor bằng chuỗi operator. |

Trình tự cơ bản:

1. `Subscriber` gọi `publisher.subscribe(subscriber)`.
2. `Publisher` cung cấp `Subscription` qua `onSubscribe(subscription)`.
3. `Subscriber` gọi `subscription.request(n)` với **n > 0** để cấp thêm nhu cầu.
4. `Publisher` phát tối đa số phần tử tương ứng với nhu cầu còn lại qua `onNext(item)`. Mỗi `onNext` tiêu thụ một đơn vị nhu cầu.
5. Nhu cầu có thể được cộng thêm nhiều lần; `request(2)` rồi `request(3)` tương đương yêu cầu thêm tổng cộng năm phần tử, miễn chưa có phần tử nào được giao.
6. Sau khi phát hết hoặc xảy ra lỗi, nguồn gửi **một** tín hiệu cuối: `onComplete()` hoặc `onError(error)`. `cancel()` yêu cầu dừng đăng ký và giải phóng công việc/tài nguyên liên quan.

Ví dụ diễn tiến của một nguồn có năm phần tử:

| Hành động | Nhu cầu còn lại | Phần tử bên nhận đã thấy |
| --- | ---: | --- |
| Bắt đầu, trước khi yêu cầu | 0 | — |
| `request(2)` | 2 | — |
| `onNext(1)`, `onNext(2)` | 0 | 1, 2 |
| `request(3)` | 3 | 1, 2 |
| `onNext(3)`, `onNext(4)`, `onNext(5)` | 0 | 1, 2, 3, 4, 5 |
| `onComplete()` | — | Kết thúc |

**Các bất biến quan trọng:**

- Không được phát thêm `onNext` vượt quá tổng nhu cầu đã cấp mà chưa được tiêu thụ. Nguồn hợp chuẩn có thể tạm chờ khi demand bằng 0.
- `request(0)` hoặc số âm là yêu cầu không hợp lệ; theo đặc tả, đăng ký phải kết thúc bằng `onError` báo lỗi `IllegalArgumentException`.
- `request(Long.MAX_VALUE)` thường biểu thị nhu cầu không giới hạn (*unbounded demand*).
- `onComplete` và `onError` là tín hiệu kết thúc, không tiêu thụ một đơn vị demand; sau khi đã kết thúc không còn `onNext` hợp lệ.
- `cancel()` không phải `onComplete()`: việc hủy thể hiện bên nhận không muốn tiếp tục; đừng dựa vào việc sau đó luôn có callback hoàn tất.
- Mỗi lần `subscribe` có `Subscription` riêng. Với nguồn *cold*, mỗi đăng ký thường nhận một luồng thực thi riêng; nguồn *hot* có thể chia sẻ luồng phát và các subscriber có nhu cầu khác nhau.

Java có API `java.util.concurrent.Flow` với những giao diện tương tự, còn Reactor sử dụng các kiểu từ `org.reactivestreams`. Không nhầm hai bộ interface khi khai báo phương thức.

## 3. Ví dụ chạy được: yêu cầu hai phần tử, rồi thêm ba

`Flux` biểu diễn 0..N phần tử; `Mono` biểu diễn 0..1 phần tử. Trong Reactor, `BaseSubscriber` cho phép kiểm soát demand rõ ràng. Đoạn sau dùng `Flux.range` là nguồn *cold* phát đồng bộ và tôn trọng nhu cầu.

Tạo file `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
}

application {
    mainClass = 'BackpressureDemo'
}
~~~

Tạo file `src/main/java/BackpressureDemo.java`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class BackpressureDemo {
    public static void main(String[] args) {
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                private int received;

                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("request(2)");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext(" + value + ")");
                    received++;

                    if (received == 2) {
                        System.out.println("request(3)");
                        request(3);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("onComplete()");
                }

                @Override
                protected void hookOnError(Throwable error) {
                    error.printStackTrace();
                }
            });
    }
}
~~~

Trong thư mục dự án, chạy `gradle run` (hoặc `./gradlew run` khi có Gradle Wrapper; trên Windows dùng `gradlew.bat run`). Phần stdout do chương trình in ra, bỏ qua thông báo riêng của Gradle:

~~~text
request(2)
onNext(1)
onNext(2)
request(3)
onNext(3)
onNext(4)
onNext(5)
onComplete()
~~~

**Giải thích:** `hookOnSubscribe` chỉ yêu cầu hai phần tử. Khi nhận phần tử thứ hai, `hookOnNext` yêu cầu thêm ba. `Flux.range` đáp ứng đủ năm phần tử rồi hoàn tất. Không cần hàng đợi không giới hạn để xử lý nguồn đồng bộ có thể đáp ứng demand. Trong `BaseSubscriber`, nếu không ghi đè `hookOnSubscribe` thì hành vi mặc định là yêu cầu không giới hạn, nên ví dụ phải chủ động gọi `request(2)`.

Đoạn minh họa trên chọn phiên bản Reactor cụ thể để có thể chạy độc lập. Trong ứng dụng Spring Boot có `spring-boot-starter-webflux`, nên sử dụng các phiên bản Reactor do BOM của Spring Boot quản lý để tránh xung đột phụ thuộc.

## 4. Demand được truyền qua các operator như thế nào?

Trong một chuỗi như:

~~~java
Flux<Integer> numbers = Flux.range(1, 100)
    .map(n -> n * 2)
    .filter(n -> n % 3 == 0)
    .doOnRequest(n -> System.out.println("requested upstream: " + n));
~~~

Subscription được nối từ cuối chuỗi về phía nguồn. Subscriber ở cuối cấp nhu cầu; operator trung gian có thể chuyển nguyên số yêu cầu, **biến đổi yêu cầu**, tích lũy hoặc yêu cầu thêm để bù cho phần tử bị lọc. Ví dụ `filter` có thể phải nhận nhiều phần tử từ nguồn hơn số phần tử thực sự đến subscriber. Vì vậy không nên suy diễn rằng một lần `request(5)` từ cuối chuỗi sẽ luôn tạo chính xác một `request(5)` ở mọi khâu.

Các điểm dễ nhầm:

- `subscribe(item -> ...)` thông thường yêu cầu không giới hạn. Để quan sát điều tiết từng đợt, dùng `BaseSubscriber` hoặc kiểm thử `StepVerifier` với nhu cầu ban đầu bằng 0.
- `limitRate(10)` biến nhu cầu lớn từ downstream thành các đợt request nhỏ hơn gửi upstream; nó **không** giới hạn thành 10 phần tử/giây. `limitRate(10, 0)` sử dụng các đợt đầy đủ thay vì nạp bù sớm.
- `publishOn(scheduler, prefetch)` mở một ranh giới bất đồng bộ và có bộ đệm/nhu cầu nạp trước. `flatMap`, `buffer`, `window` cũng có thể thay đổi số phần tử được yêu cầu hoặc lượng dữ liệu đang giữ. Số `request` quan sát được ở upstream có thể cao hơn con số subscriber vừa yêu cầu.
- `subscribeOn` quyết định ngữ cảnh lập lịch cho quá trình subscription/phát phù hợp; chuyển sang scheduler khác không tự động hạn chế demand hoặc giải quyết nguồn phát quá nhanh.
- `take(n)` chỉ lấy tối đa n phần tử rồi thường hủy upstream; đó là giới hạn tổng số phần tử, khác với điều tiết nhu cầu từng đợt.
- Những operator có hàng đợi hoặc prefetch vẫn dùng bộ nhớ. Cần tính cả số tác vụ đồng thời và kích thước mỗi phần tử khi chọn giá trị.

Khi debug, đặt `doOnRequest` **ở các vị trí cụ thể** của chuỗi để biết đang quan sát yêu cầu của đoạn nào:

~~~java
Flux.range(1, 100)
    .doOnRequest(n -> System.out.println("source demand = " + n))
    .limitRate(10)
    .doOnRequest(n -> System.out.println("downstream demand = " + n))
    .subscribe(System.out::println);
~~~

Ở đây subscriber yêu cầu không giới hạn, còn `limitRate` chia request lên nguồn thành các đợt. Log thể hiện các tín hiệu request đi qua từng vị trí; không đồng nghĩa với tốc độ thực thi cố định.

## 5. Nếu nguồn không thể chậm lại thì sao?

Backpressure phát huy hiệu quả nhất khi nguồn có thể dừng/tạm dừng theo demand, ví dụ một `Flux.range` hoặc một pipeline đọc dữ liệu có khả năng lấy thêm khi được yêu cầu. Ngược lại, callback từ thiết bị, dữ liệu thị trường, socket, một nguồn *hot* hoặc tác vụ phát theo đồng hồ có thể tạo dữ liệu dù subscriber chưa yêu cầu. Khi đó phải nêu rõ chính sách quá tải.

| Chính sách Reactor | Hành vi khi downstream chưa theo kịp | Thường phù hợp |
| --- | --- | --- |
| `onBackpressureBuffer` | Giữ phần tử chờ; phải chọn giới hạn và cách xử lý tràn. | Dữ liệu không muốn mất trong khoảng chậm ngắn, với ngân sách bộ nhớ rõ ràng. |
| `onBackpressureDrop` | Bỏ các phần tử đến khi không có demand. | Đo mẫu/hiển thị có thể mất bớt cập nhật. |
| `onBackpressureLatest` | Giữ cập nhật mới nhất để giao khi có demand. | Trạng thái hiện tại quan trọng hơn từng thay đổi trung gian. |
| `onBackpressureError` | Báo lỗi khi xuất hiện phần tử không có demand. | Cần fail-fast và để tầng trên áp dụng retry/kiểm soát tải. |

Ví dụ cách chọn operator, với giả định `fastSource` là một `Flux<Event>` đã được khai báo trong ứng dụng:

~~~java
Flux<Event> bounded = fastSource.onBackpressureBuffer(128);
Flux<Event> sampled = fastSource.onBackpressureDrop();
Flux<Event> currentState = fastSource.onBackpressureLatest();
Flux<Event> failFast = fastSource.onBackpressureError();
~~~

Đây là **đoạn minh họa tích hợp**, không phải chương trình Java độc lập: `Event` và `fastSource` cần được định nghĩa theo nguồn thật. Với `onBackpressureBuffer(128)`, nếu phần tử đến nhanh hơn tốc độ tiêu thụ và vùng đệm đầy, luồng có thể thất bại do tràn; cần quyết định rõ hành vi xử lý lỗi. Tránh gọi `onBackpressureBuffer()` không giới hạn trên dòng dữ liệu có thể tăng vô hạn.

Đừng dùng chiến lược làm mất dữ liệu cho thanh toán, giao dịch hay audit log khi mọi sự kiện phải được xử lý. Khi dữ liệu không thể mất, cần cơ chế lưu trữ bền vững, xác nhận nhận dữ liệu, phân vùng/tạm dừng nguồn, retry có kiểm soát hoặc từ chối tải, thay vì kỳ vọng bộ đệm trong RAM tự giải quyết.

Với `Flux.create` hoặc `Flux.push`, người viết bridge từ callback sang Reactor phải cân nhắc `FluxSink.OverflowStrategy`. Việc tự gọi `sink.next(...)` liên tục không làm nguồn bên ngoài tự động hiểu `request(n)`. Nên kiểm tra `sink.requestedFromDownstream()` hoặc dùng callback `onRequest` và có chiến lược điều tiết thích hợp ở nơi tạo dữ liệu.

## 6. Backpressure trong Spring WebFlux có phạm vi nào?

Spring WebFlux sử dụng mô hình Publisher để kết nối handler, các operator Reactor và phần ghi response. Ví dụ endpoint dưới đây nằm trong **một ứng dụng Spring Boot đã thêm `spring-boot-starter-webflux`**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class NumberController {
    @GetMapping(value = "/numbers", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 1_000)
            .doOnRequest(n -> System.out.println("requested = " + n))
            .doOnCancel(() -> System.out.println("client cancelled"));
    }
}
~~~

Ứng dụng chạy xong có thể thử `curl -N http://localhost:8080/numbers`. `text/event-stream` cho phép gửi nhiều phần tử trong một HTTP response; `-N` ngăn curl tự đệm đầu ra. Số request quan sát trong log phụ thuộc đường đi thật qua WebFlux, bộ đệm, encoder và transport; không được mặc định coi mỗi lần client đọc một dòng sẽ tạo một `request(1)`.

**Giới hạn quan trọng:** demand trong pipeline Reactor **không đồng nghĩa** tất cả thành phần bên ngoài đều hỗ trợ backpressure từ đầu đến cuối. HTTP client/server, driver cơ sở dữ liệu, message broker, WebSocket, callback SDK và bộ đệm hệ điều hành có những cách điều tiết khác nhau. Nếu phía nguồn đã đọc trọn dữ liệu vào `List` hoặc buffer trước khi tạo `Flux`, demand phía sau không thể lấy lại bộ nhớ đã cấp phát trước đó. Khi tích hợp hệ thống, hãy kiểm tra cách nguồn thực sự lấy dữ liệu, chiến lược prefetch, queue, kích thước payload, cancellation và việc đóng kết nối.

## 7. Kiểm thử demand thay vì chỉ kiểm tra kết quả

Thêm vào `build.gradle` của ví dụ Reactor ở mục 3:

~~~groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo `src/test/java/DemandTest.java`:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {
    @Test
    void receivesOnlyAfterRequesting() {
        StepVerifier.create(Flux.range(1, 5), 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` hoặc Gradle Wrapper tương ứng. Giá trị `0` trong `StepVerifier.create(..., 0)` đặt **initial request = 0**; test tự cấp hai đơn vị rồi ba đơn vị. Nếu nguồn phát trái phép khi chưa có nhu cầu, test có thể phát hiện tín hiệu ngoài kỳ vọng. Đối với nguồn bất đồng bộ, còn cần kiểm thử thời gian, hủy subscription, tải cao và chính sách tràn bộ đệm; bài test này chủ yếu xác nhận hợp đồng demand của nguồn đồng bộ.

## 8. Những sai lầm thường gặp

1. **Coi `Flux` là bảo đảm không bao giờ tràn bộ nhớ.** Dữ liệu đã được nạp trước, queue của operator và nguồn *hot* vẫn có thể gây áp lực bộ nhớ.
2. **Nhầm `request(n)` với giới hạn tốc độ.** `request(100)` cho phép tối đa 100 phần tử tiếp theo, không có nghĩa là 100 phần tử/giây.
3. **Dùng `subscribe(item -> ...)` rồi kỳ vọng thấy demand theo từng đợt.** Kiểu subscribe này thường yêu cầu không giới hạn.
4. **Dùng buffer vô hạn để xử lý nguồn luôn nhanh hơn bên nhận.** Chênh lệch tốc độ kéo dài sẽ làm hàng đợi lớn mãi; cần giới hạn, tín hiệu quá tải hoặc điều tiết nguồn.
5. **Dùng drop/latest khi mọi bản ghi đều bắt buộc.** Mất phần tử có thể xảy ra theo đúng thiết kế của operator.
6. **Nghĩ `publishOn`, `subscribeOn` hay thêm thread là đủ.** Chúng thay đổi thực thi nhưng không thay thế kiểm soát demand, queue hay tải nguồn.
7. **Chặn luồng sự kiện bằng `block()` hoặc xử lý I/O đồng bộ kéo dài.** Việc chặn có thể làm nghẽn event-loop; nếu buộc phải dùng API blocking, cô lập phần đó bằng scheduler/tầng tích hợp phù hợp và giới hạn concurrency.
8. **Không xử lý `cancel` và terminal signal.** Hủy kết nối không đồng nghĩa phần upstream tự giải phóng mọi resource; bridge/driver cần hợp tác hủy và cleanup.

## 9. Quy trình chọn giải pháp trong thực tế

Trước khi thêm operator, lần lượt xác định:

1. **Nguồn có thể tạm dừng không?** Nếu có, ưu tiên truyền `request(n)` ngược lên nguồn và chỉ đọc/phát khi được yêu cầu.
2. **Có được phép mất sự kiện không?** Nếu có, cân nhắc drop/latest theo ý nghĩa dữ liệu; nếu không, cần lưu trữ hoặc điều tiết nguồn bảo toàn dữ liệu.
3. **Có giới hạn bộ nhớ và độ trễ chưa?** Tính kích thước phần tử, queue, prefetch, concurrency và tổng số subscriber; chọn buffer hữu hạn cùng chính sách khi đầy.
4. **Làm sao quan sát?** Theo dõi lượng request, queue depth, thời gian chờ, tỷ lệ drop/overflow, lỗi, cancellation và tốc độ phát/tiêu thụ.
5. **Đã thử với bên nhận chậm chưa?** Kiểm thử demand bằng `StepVerifier`, rồi thử tải với downstream chậm, nguồn *hot*, ngắt kết nối, timeout và retry.

**Ghi nhớ:** `request(n)` là ngôn ngữ của nhu cầu trong Reactive Streams. Nó giúp nguồn hợp tác chỉ phát khi bên nhận sẵn sàng; với nguồn không hợp tác, ứng dụng vẫn phải chọn chính sách điều tiết, đệm, bỏ bớt hoặc báo lỗi rõ ràng.

## Tài liệu đối chiếu

- Reactive Streams — đặc tả giao thức: https://www.reactive-streams.org/
- Project Reactor — tài liệu chính thức: https://projectreactor.io/docs/core/release/reference/
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
