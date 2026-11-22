# `request(n)` và số phần tử đang được yêu cầu trong Reactive Streams

## 1. Bài toán: phía tiêu thụ quyết định được nhận bao nhiêu

Reactive Streams là giao thức xử lý luồng bất đồng bộ có **backpressure**: phía nhận có thể thông báo cho phía phát biết lượng dữ liệu mình sẵn sàng tiêu thụ. Trong hệ sinh thái Spring WebFlux, Project Reactor hiện thực ý tưởng này qua `Flux`, `Mono` và các loại `Publisher`/`Subscriber`.

Hạt nhân của cơ chế là `Subscription.request(long n)`. Khi subscriber gọi `request(n)` với `n > 0`, nó **cấp thêm quyền phát tối đa n tín hiệu `onNext`**, không yêu cầu phát ngay chính xác n phần tử. Nguồn có thể chưa có dữ liệu, phát ít hơn, hoặc kết thúc hợp lệ.

Sau bài này, người học sẽ biết tính pending demand, xử lý request cộng dồn, phân biệt hết quota với hủy, quan sát demand đi qua operator và tự viết subscriber request theo đợt trong Java 17+.

## 2. Publisher, Subscriber, Subscription

| Thành phần | Trách nhiệm |
| --- | --- |
| `Publisher<T>` | Cung cấp chuỗi phần tử `T`, cho phép đăng ký bằng `subscribe`. |
| `Subscriber<T>` | Nhận `onSubscribe`, `onNext`, `onError`, `onComplete`. |
| `Subscription` | Quan hệ đăng ký giữa một subscriber và publisher; cung cấp `request(long n)`, `cancel()`. |
| `Processor<T,R>` | Vừa nhận từ upstream, vừa phát xuống downstream; nhiều operator Reactor làm vai trò trung gian tương tự. |

Trình tự điển hình:

~~~text
Subscriber                         Publisher
    | -------- subscribe() ----------> |
    | <------- onSubscribe(s) --------- |
    | -------- s.request(3) ----------> |  quyền phát: 3
    | <---------- onNext(A) ----------- |  còn 2
    | <---------- onNext(B) ----------- |  còn 1
    | -------- s.request(2) ----------> |  còn 3, không phải 2
    | <---------- onNext(C) ----------- |  còn 2
    | <---------- onNext(D) ----------- |  còn 1
    | <---------- onNext(E) ----------- |  còn 0
    | <---------- onComplete() -------- |  nếu nguồn hoàn tất
~~~

`request` và `cancel` đi từ downstream về upstream. Các tín hiệu dữ liệu/kết thúc đi từ upstream xuống downstream. Một request có thể dẫn đến `onNext` đồng bộ ngay khi gọi, hoặc phần tử được gửi bất đồng bộ sau đó. `request(n)` là **giới hạn trên của số `onNext` được phép phát**, không phải lời hứa phát đủ n phần tử.

## 3. Pending/outstanding demand: quota còn lại

**Pending demand** (hay outstanding demand) là số quyền phát `onNext` đã cấp nhưng chưa dùng tại một `Subscription`. Với quota hữu hạn:

~~~text
D_mới = D_cũ + n                  sau request(n), n > 0
D_mới = D_cũ - 1                  sau một onNext hợp lệ
D = tổng số đã request - tổng onNext đã phát
~~~

Bảng ví dụ:

| Sự kiện | Tổng đã request | Tổng đã phát | Demand còn lại |
| --- | ---: | ---: | ---: |
| `onSubscribe`, chưa request | 0 | 0 | 0 |
| `request(3)` | 3 | 0 | 3 |
| `onNext(A)` | 3 | 1 | 2 |
| `onNext(B)` | 3 | 2 | 1 |
| `request(2)` | 5 | 2 | 3 |
| `onNext(C)` | 5 | 3 | 2 |
| `onNext(D)` | 5 | 4 | 1 |
| `onNext(E)` | 5 | 5 | 0 |

Tại hàng `request(2)`, quota đang là 1 nên tăng thành **3**. `request` mang tính **cộng dồn**, không gán lại quota. Ví dụ hai lần `request(2)` liên tiếp sẽ cấp tổng cộng 4 quyền, trước khi trừ các `onNext` phát xen kẽ.

Phân biệt ba khái niệm:

- **Tổng yêu cầu**: tổng quyền được subscriber cấp từ đầu.
- **Tổng phát**: số `onNext` đã đến subscriber.
- **Demand còn lại**: hiệu của hai tổng khi quota còn hữu hạn; không phải số phần tử trong queue, số tác vụ đang xử lý async hay số byte trong bộ nhớ.

Mỗi `Subscription` có quota riêng. Hai subscriber dùng chung một `Flux` không tự động chia sẻ bộ đếm request. Từng đoạn nối giữa các operator cũng có thể ghi nhận demand khác nhau.

## 4. Những quy tắc cốt lõi của đặc tả

1. **Không phát vượt request:** trong mọi thời điểm, tổng `onNext` gửi cho một subscriber phải nhỏ hơn hoặc bằng tổng phần tử subscriber đã request (Reactive Streams Publisher 1.1). Khi demand bằng 0, publisher không được gửi `onNext` mới.
2. **Request phải dương:** `request(0)` hoặc `request(-1)` là không hợp lệ khi subscription còn hoạt động. Subscription phải phát `onError` với `IllegalArgumentException` theo Subscription 3.9. Đừng dùng `request(0)` như lệnh tạm dừng và đừng chờ một exception được ném trực tiếp từ `request`.
3. **Cộng dồn:** `request(n > 0)` đăng ký thêm n phần tử (Subscription 3.8). Một subscriber có thể gọi nhiều lần, kể cả từ `onNext`.
4. **Có thể phát ít hơn:** nguồn còn bốn phần tử dù subscriber request mười thì được gửi bốn `onNext` rồi `onComplete` (Publisher 1.2). Không có nghĩa request 10 sẽ luôn nhận đúng 10.
5. **Có thể phát đồng bộ:** `request` có thể gây `onNext` trước khi `request` trả về (Subscription 3.10). Implementation tuân chuẩn cần quản lý reentrancy để tránh đệ quy `request → onNext → request` làm đầy stack.
6. **Giới hạn số nguyên:** Reactive Streams hỗ trợ quota đến `Long.MAX_VALUE` (Subscription 3.17). Reactor chặn cộng demand tại ngưỡng này và coi `Long.MAX_VALUE` là **unbounded**. Không tự cộng hai số `long` để quản lý demand mà bỏ qua overflow và truy cập đồng thời.
7. **Hết quota khác hủy:** quota 0 nghĩa là chờ subscriber cấp thêm quyền; `cancel()` nghĩa là subscriber không muốn nhận thêm và cho phép thu hồi tài nguyên. Các race bất đồng bộ có thể tồn tại với tín hiệu đã được xử lý/sắp lịch khi hủy xảy ra.
8. **Terminal không dùng quota dữ liệu:** `onComplete` và `onError` kết thúc chuỗi, không chiếm một quyền `onNext`; nguồn có thể kết thúc khi pending demand bằng 0. Sau terminal không phát `onNext` hợp lệ.

Với `request(Long.MAX_VALUE)`, Reactor xem như không giới hạn demand tại subscriber. Điều đó **không tạo ra bộ nhớ vô hạn** và cũng không ép publisher phải phát vô hạn phần tử.

## 5. Chương trình Java 17+ chạy được với Reactor

Tạo dự án Gradle, nội dung `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
}

application {
    mainClass = 'DemandDemo'
}
~~~

Tạo tệp `src/main/java/DemandDemo.java`:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public final class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 5)
            .subscribe(new BaseSubscriber<Integer>() {
                private int received;

                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("onSubscribe: request(2)");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    received++;
                    System.out.println("onNext: " + value);
                    if (received % 2 == 0) {
                        System.out.println("request(2) them");
                        request(2);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("onComplete");
                }

                @Override
                protected void hookOnError(Throwable error) {
                    System.err.println("onError: " + error);
                }
            });
    }
}
~~~

Chạy `gradle run --quiet` hoặc `./gradlew run --quiet` nếu dự án có wrapper. Với `Flux.range` đồng bộ, stdout chính xác:

~~~text
onSubscribe: request(2)
onNext: 1
onNext: 2
request(2) them
onNext: 3
onNext: 4
request(2) them
onNext: 5
onComplete
~~~

Phân tích:

- Ban đầu `hookOnSubscribe` cấp 2 quyền. Nhận 1 và 2 làm quota về 0.
- Trong `hookOnNext` của phần tử thứ hai, request thêm 2. Nhận 3 và 4, quota trở lại 0.
- Phần tử thứ tư kích hoạt request thêm 2. Nguồn chỉ còn 5, nên phát 5 và hoàn tất. **Tổng yêu cầu là 6 nhưng thực nhận 5**, hợp lệ.
- `BaseSubscriber` mặc định yêu cầu unbounded nếu không override `hookOnSubscribe`. Khi override, phải chủ động cấp một request dương để luồng có thể tiến.
- Việc gọi request trong `onNext` là hợp đồng cho phép; Reactor xử lý cách phát đồng bộ an toàn. Đoạn mã đang yêu cầu theo **lô hai phần tử**, không tạo danh sách hai phần tử như `buffer(2)`.

## 6. Kiểm thử demand bằng StepVerifier

Kiểm thử rằng khi chưa yêu cầu, một nguồn đồng bộ có dữ liệu chưa thể phát `onNext`. Thay khối `dependencies` ở `build.gradle` trên bằng khối sau và thêm `test` (chỉ giữ một khối `dependencies`):

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
    testImplementation 'io.projectreactor:reactor-test:3.8.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Tệp `src/test/java/DemandTest.java`:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {
    @Test
    void onlyEmitsWhenRequested() {
        StepVerifier.create(Flux.range(1, 5), 0)
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(20))
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();
    }
}
~~~

Chạy `gradle test`. Tham số `0` nghĩa là **initial request = 0**. `expectSubscription()` phải đứng trước `expectNoEvent` vì sự kiện đăng ký cũng được coi là một sự kiện. `thenRequest(2)` cho phép hai phần tử đầu; `thenRequest(3)` cho phép ba phần tử còn lại. Bài test chứng minh request cấp thêm quota theo từng đợt.

## 7. Các chiến lược request và điểm cần cân nhắc

| Cách tiêu thụ | Ví dụ request | Khi nào hợp lý | Rủi ro |
| --- | --- | --- | --- |
| Từng phần tử | `request(1)` rồi xử lý xong lại `request(1)` | Muốn quota nhỏ, dễ theo dõi | Overhead nhiều lượt request |
| Theo lô | `request(32)` rồi request bù khi tiêu thụ | Thông lượng tốt hơn, còn có giới hạn | Chọn ngưỡng quá cao gây backlog |
| Không giới hạn | `request(Long.MAX_VALUE)` | Nguồn nhỏ/hữu hạn, downstream đủ nhanh | Không giới hạn sản lượng bằng demand tại subscriber |

Nếu `onNext` chỉ khởi chạy một tác vụ I/O bất đồng bộ rồi trả về, request bù ngay sau đó **không đảm bảo** số tác vụ đang chạy đồng thời bị giới hạn. Phải tính cả thời điểm tác vụ thật sự hoàn thành, concurrency và queue ở những tầng liên quan.

`request(10)` **không** có nghĩa 10 phần tử/giây. Nó là quota phần tử, không phải giới hạn theo thời gian. Rate limiting và backpressure giải quyết hai khía cạnh khác nhau, có thể cần phối hợp.

## 8. Operator có thể đổi demand đi ngược upstream

Một pipeline Reactor có thể thay đổi kích thước yêu cầu ở từng chặng:

- `map` thường bảo toàn một đầu vào tương ứng một đầu ra.
- `filter` có thể loại bớt dữ liệu; để trả đủ hai phần tử đạt điều kiện, upstream có thể phải phát và được request hơn hai phần tử.
- `buffer(10)` đổi **10 phần tử nguồn thành một `List`**. Downstream `request(2)` có thể cần **20 phần tử nguồn** để tạo hai list đầy đủ.
- `flatMap` xử lý các inner publisher; concurrency và prefetch tác động request. `publishOn` cũng dùng cơ chế queue/prefetch riêng.
- `limitRate(highTide, lowTide)` chia/tái phân phối request upstream thành các đợt. `limitRate(10, 0)` là cách yêu cầu theo lô chặt hơn với ngưỡng 10. `limitRequest(N)` lại giới hạn **tổng** số phần tử được phép tới downstream rồi hoàn tất luồng khi đạt N.

Snippet sau cần được đặt trong một class/method Java có import `Flux`, `BaseSubscriber` và `Subscription`; nó không phải chương trình chạy độc lập:

~~~java
Flux.range(1, 100)
    .buffer(10)
    .subscribe(new BaseSubscriber<java.util.List<Integer>>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2); // hai List, không phải hai Integer
        }

        @Override
        protected void hookOnNext(java.util.List<Integer> batch) {
            System.out.println(batch);
        }
    });
~~~

Subscriber nhận hai `List<Integer>` đầu chứa 1–10 và 11–20. Đây là **hai `onNext` downstream nhưng 20 phần tử upstream**; không có request tiếp thì các list còn lại không được phát xuống subscriber.

Dùng `doOnRequest(n -> System.out.println(n))` ở các vị trí khác nhau để kiểm tra **lượt request tới chặng đó**. Đừng đọc một log request như pending demand toàn pipeline, vì operator có thể đã phát dữ liệu, refill hoặc giữ phần tử trong queue.

## 9. Liên hệ với Spring WebFlux

Khi controller Spring WebFlux trả một `Flux<T>`, framework chịu trách nhiệm đăng ký và yêu cầu dữ liệu thông qua chuỗi chuyển đổi/HTTP. Thông thường controller **không tự cầm `Subscription` gọi `request`**.

Snippet endpoint Server-Sent Events trong ứng dụng Spring WebFlux:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventController {
    @GetMapping(value = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> events() {
        return Flux.range(1, 100)
            .map(i -> "event-" + i)
            .limitRate(16, 0);
    }
}
~~~

`limitRate(16, 0)` tác động việc truyền request **upstream** thành những đợt ngưỡng 16. Nó **không đảm bảo** HTTP gửi chính xác 16 sự kiện/giây hay buffer mạng chỉ chứa 16 phần tử. Tầng serialize, vận chuyển HTTP, nguồn dữ liệu và tốc độ client đọc còn có cơ chế riêng.

Với nguồn tuân thủ Reactive Streams, nên giữ chuỗi operator phù hợp để truyền backpressure và chọn concurrency/prefetch có chủ đích. Với nguồn callback “push” cứ phát bất chấp request, chỉ bọc bằng `Flux` không tự làm hệ thống an toàn: cần chính sách buffer có giới hạn, drop/latest hoặc phản hồi từ chối phù hợp nghiệp vụ. Backpressure cũng **không biến I/O blocking thành non-blocking**; tránh chặn event-loop WebFlux bằng tác vụ I/O blocking trong `map` hoặc `onNext`.

## 10. Các lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Thực tế | Cách sửa |
| --- | --- | --- |
| `request(n)` bắt nguồn phát đúng n ngay | Chỉ cấp tối đa n quyền phát `onNext` | Theo dõi cả tín hiệu kết thúc |
| Gọi `request(2)` lần nữa để đặt quota về 2 | Request cộng dồn | Tính tổng request trừ `onNext` |
| `request(0)` là nút tạm dừng | Là request bất hợp lệ | Không request thêm; `cancel()` nếu muốn hủy |
| Phát `onNext` khi quota 0 | Vi phạm giới hạn subscriber | Sửa publisher/nguồn không tuân chuẩn |
| Dùng `subscribe(value -> ...)` để giữ demand nhỏ | Các overload lambda phổ biến của Reactor request unbounded | Dùng `BaseSubscriber` hoặc operator kiểm soát |
| `request(10)` giữ mọi queue ≤10 | Prefetch và async operator có queue riêng | Đo/giới hạn từng tầng |
| Override `hookOnSubscribe` nhưng quên request | Source có thể không phát dữ liệu | Gọi `request(n > 0)` khi sẵn sàng |
| `Long.MAX_VALUE` an toàn bộ nhớ | Là demand không giới hạn theo giao thức | Chỉ dùng khi downstream đủ khả năng |
| Tự cộng `long` demand mà không chống overflow | Có thể thành số âm | Dùng phép cộng bão hòa và đồng bộ hóa phù hợp |
| Nhầm `cancel` với hết demand | Hủy khác việc đang chờ request | Phân biệt kết thúc và tạm chờ |

Khi một `Flux` dường như đứng yên, kiểm tra: có `onSubscribe` không; request dương đã được gửi chưa; operator nào biến đổi/giữ nhu cầu; có `onComplete`, `onError` hoặc `cancel` không; nguồn còn dữ liệu hay đang blocking? Dùng `doOnSubscribe`, `doOnRequest`, `doOnNext`, `doOnCancel`, `doFinally` tại đúng vị trí để quan sát.

## 11. Bài tập có đáp án

**Câu 1:** `request(4)`, nhận ba `onNext`, rồi `request(2)`. Pending demand còn bao nhiêu?

**Đáp án:** `4 - 3 + 2 = 3`.

**Câu 2:** `request(5)` nhưng nguồn chỉ có hai phần tử rồi `onComplete`. Có vi phạm không?

**Đáp án:** Không. Publisher được phát ít hơn số request và kết thúc.

**Câu 3:** Subscriber `request(3)` sau `buffer(4)`. Có thể cần bao nhiêu phần tử upstream để đủ ba buffer?

**Đáp án:** 12 phần tử nếu nguồn không kết thúc sớm; mỗi list downstream dùng bốn phần tử upstream.

**Câu 4:** Có nên `request(0)` để tạm dừng không?

**Đáp án:** Không. Khi subscription còn hoạt động, đó là lỗi phải dẫn tới `onError(IllegalArgumentException)`. Không gửi thêm request để chờ, hoặc `cancel` để hủy.

**Câu 5:** Vì sao một `doOnRequest` ở trước `buffer(10)` có thể ghi 20 khi subscriber cuối gọi `request(2)`?

**Đáp án:** Hai list downstream cần tối đa 20 phần tử upstream.

## 12. Ghi nhớ và tài liệu tham khảo

- `request(n)`, `n > 0`, cấp thêm **n quyền phát `onNext`** trên một subscription.
- Pending demand hữu hạn tăng khi request và giảm khi publisher phát `onNext`; nhiều request là **cộng dồn**.
- Publisher không được phát vượt quota, nhưng được phát **ít hơn** và kết thúc.
- `request(0)` và số âm là sai; `Long.MAX_VALUE` đại diện unbounded demand trong Reactor.
- Operator có thể thay đổi demand giữa các chặng; request ở subscriber cuối không luôn bằng request ở nguồn.

Nguồn chuẩn:

1. [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification) — Publisher 1.1/1.2, Subscription 3.8/3.9/3.17.
2. [Reactor: Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) — `BaseSubscriber`, `limitRate`, `limitRequest` và prefetch.
3. [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `Flux`, `Mono`, operator.
4. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — Reactive Streams trong Spring HTTP stack.
