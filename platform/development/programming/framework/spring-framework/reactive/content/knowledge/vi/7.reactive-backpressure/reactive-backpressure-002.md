# Những cách đăng ký yêu cầu không giới hạn trong Project Reactor

## 1. Mục tiêu và bài toán backpressure

Trong **Spring Framework Reactive**, Project Reactor dùng `Flux<T>` và `Mono<T>` để biểu diễn Publisher theo chuẩn Reactive Streams. Khi một Subscriber đăng ký (`subscribe`), nó phải thông báo cho nguồn biết **được phép nhận bao nhiêu phần tử** bằng `Subscription.request(n)`. Đây là nền tảng của **backpressure**: phía nhận có thể giới hạn nhịp gửi dữ liệu của phía phát.

Nhưng có nhiều cách đăng ký trong Reactor **tự yêu cầu số lượng không giới hạn** ngay từ đầu. Hiểu rõ các đường đi này giúp tránh nhầm lẫn rằng dùng `Flux` đồng nghĩa với luôn có backpressure được kiểm soát từng phần tử.

Sau bài học, bạn cần:

- Hiểu `request(Long.MAX_VALUE)` và ý nghĩa “unbounded demand”.
- Nhận diện các overload `subscribe` mặc định yêu cầu không giới hạn, kể cả khi ta không gọi `request` trong mã ứng dụng.
- Biết thêm `BaseSubscriber` mặc định cũng yêu cầu không giới hạn nếu không ghi đè `hookOnSubscribe`, và dùng `requestUnbounded()` khi muốn thể hiện ý định rõ ràng.
- Phân biệt đường đăng ký có thể **chủ động cấp demand** với cách đăng ký tự động yêu cầu vô hạn.
- Biết rằng demand ở subscriber cuối có thể được **toán tử trung gian thay đổi** trước khi tới nguồn, và yêu cầu không giới hạn không loại bỏ nhu cầu quản lý bộ nhớ, tốc độ và hủy.
- Chọn được cách đăng ký phù hợp khi viết ứng dụng Spring WebFlux.

## 2. Từ Subscription đến `Long.MAX_VALUE`

### 2.1. Demand là quyền phát, không phải tổng số phần tử chắc chắn nhận được

Về khái niệm, tương tác giữa Publisher và Subscriber như sau:

~~~text
Publisher.subscribe(subscriber)
             |
             v
Subscriber.onSubscribe(subscription)
             |
             +-- subscription.request(2) -------------> nguồn
             |<-------------------------- onNext(item1)
             |<-------------------------- onNext(item2)
             |
             +-- subscription.request(1) -------------> nguồn
             |<-------------------------- onNext(item3)
             |<-------------------------- onComplete()
~~~

Một lần `request(2)` cấp quyền nhận **tối đa hai `onNext` nữa** trên nhu cầu hiện có. Nguồn có thể phát ít hơn nếu hết dữ liệu; `onComplete` hoặc `onError` không được tính như một phần tử `onNext` và không cần một đơn vị demand riêng để phát. Demand được cộng dồn giữa các lần yêu cầu.

`request(n)` phải dùng số nguyên dương (`n > 0`); `request(0)` hay `request(-1)` không có nghĩa “chưa muốn nhận” hoặc “không giới hạn”. Đây là request không hợp lệ và giao thức yêu cầu nguồn báo lỗi `IllegalArgumentException` khi subscription đang hoạt động. **Muốn đăng ký mà chưa phát dữ liệu, hãy tạm thời chưa gọi `request`.**

### 2.2. Vì sao `Long.MAX_VALUE` biểu diễn yêu cầu không giới hạn?

Giá trị Java `Long.MAX_VALUE` bằng `9_223_372_036_854_775_807L`. Chuẩn Reactive Streams yêu cầu subscription hỗ trợ demand tới mức này và **cho phép** publisher xem demand bằng ngưỡng đó là *effectively unbounded*. Project Reactor dùng giá trị này làm quy ước yêu cầu không giới hạn.

~~~java
subscription.request(Long.MAX_VALUE); // Demand không giới hạn trong Reactor
~~~

Ý nghĩa thực tế: “Từ giờ, nguồn được phép phát dữ liệu nhanh nhất có thể theo khả năng của pipeline, không cần chờ phía nhận cấp thêm demand từng đợt”. Nó **không** buộc nguồn phải tạo đúng `Long.MAX_VALUE` phần tử, không biến nguồn hữu hạn thành vô hạn, không bảo đảm CPU/I/O đủ nhanh và không có nghĩa dữ liệu được lưu sẵn một lần trong RAM.

Nếu nguồn có ba phần tử, `request(Long.MAX_VALUE)` vẫn chỉ nhận ba `onNext` rồi `onComplete`. Nếu nguồn phát vô hạn, demand không giới hạn có thể dẫn tới hoạt động kéo dài cho đến khi subscriber hủy, pipeline lỗi, hoặc ứng dụng kết thúc. Cách phát thực tế còn phụ thuộc nguồn đồng bộ hay bất đồng bộ, scheduler và các toán tử.

### 2.3. Hai khái niệm thường bị trộn lẫn

| Khái niệm | Nội dung | Không suy ra |
| --- | --- | --- |
| **Unbounded demand** | Subscriber không yêu cầu giới hạn số `onNext` trong phạm vi subscription đó | Nguồn đã tạo mọi item, không còn cancel hoặc không có giới hạn tài nguyên |
| **Unbounded source** | Một nguồn có thể tạo phần tử vô hạn (nếu không bị dừng) | Subscriber nhất thiết sẽ yêu cầu vô hạn |

Một nguồn hữu hạn `Flux.range(1, 3)` có thể nhận request vô hạn. Ngược lại, nguồn có khả năng vô hạn có thể được subscriber điều khiển theo từng `request(1)` hoặc `request(10)`.

## 3. Những overload `subscribe` mặc định yêu cầu không giới hạn

Đây là cách gặp nhiều nhất trong mã Reactor. Khi dùng các overload tiện lợi của `Flux`/`Mono` mà **không tự kiểm soát Subscription**, Reactor thường gửi `request(Long.MAX_VALUE)` tự động khi subscribe.

| Cách gọi | Điều ứng dụng cung cấp | Demand mặc định |
| --- | --- | --- |
| `source.subscribe()` | Không truyền consumer | Không giới hạn |
| `source.subscribe(onNext)` | Callback cho dữ liệu | Không giới hạn |
| `source.subscribe(onNext, onError)` | Callback dữ liệu và lỗi | Không giới hạn |
| `source.subscribe(onNext, onError, onComplete)` | Thêm callback hoàn tất | Không giới hạn |
| `source.subscribe(onNext, onError, onComplete, subscriptionConsumer)` | Callback nhận `Subscription` để request | **Ngoại lệ**: callback tự quyết định demand; overload này đã được đánh dấu deprecated, ưu tiên `BaseSubscriber` |
| `source.subscribe(customSubscriber)` | Một `Subscriber` tùy biến | **Tùy** implementation của `Subscriber` và cách nó gọi `request` |

Nói ngắn gọn: số lượng callback `onNext`/`onError`/`onComplete` không quyết định demand. Khi dùng các overload lambda phổ biến, callback chỉ xử lý tín hiệu; **Reactor đã chủ động cấp demand không giới hạn** cho subscriber đó.

### 3.1. `subscribe()` không tham số

~~~java
Flux.range(1, 3)
    .doOnRequest(n -> System.out.println("request=" + n))
    .doOnNext(n -> System.out.println("upstream=" + n))
    .subscribe();
~~~

Với nguồn đồng bộ `range`, stdout dự kiến:

~~~text
request=9223372036854775807
upstream=1
upstream=2
upstream=3
~~~

Không truyền consumer **không có nghĩa nguồn không chạy**. Callback `doOnNext` là hook của pipeline, vẫn quan sát được dữ liệu ở phía upstream; chỉ là bạn không cài callback nhận dữ liệu trong overload `subscribe()`.

### 3.2. `subscribe(Consumer)`

~~~java
Flux.just("A", "B")
    .subscribe(value -> System.out.println("next=" + value));
~~~

Khi đăng ký, Reactor tự yêu cầu không giới hạn và consumer nhận `A`, `B`. Đối với Publisher bất đồng bộ, `subscribe` thường trả về trước khi mọi phần tử đến. Đối với nguồn đồng bộ nhỏ như `just`/`range` không đổi scheduler, các callback thường chạy ngay trong luồng gọi.

Điểm cần tránh: overload chỉ có `onNext` không cung cấp callback xử lý `onError`; khi nguồn lỗi, Reactor có thể báo lỗi không có handler qua cơ chế xử lý lỗi mặc định. Mã học tập và mã ứng dụng cần đường xử lý lỗi minh bạch.

### 3.3. `subscribe(onNext, onError[, onComplete])`

~~~java
Flux.just(10, 20)
    .subscribe(
        value -> System.out.println("next=" + value),
        error -> System.err.println("error=" + error.getMessage()),
        () -> System.out.println("complete")
    );
~~~

Ba callback này diễn tả rõ tín hiệu dữ liệu, lỗi và hoàn tất. **Chúng không giới hạn demand**: phía đăng ký vẫn thường request `Long.MAX_VALUE` ngay lúc subscribe. Nếu luồng lỗi thì chỉ chạy handler `onError`, không có `onComplete` tiếp theo trên cùng subscription.

### 3.4. Ngoại lệ có `Consumer<Subscription>` và vì sao nên tránh làm mặc định

Một overload `subscribe(onNext, onError, onComplete, subscriptionConsumer)` cho callback cuối nhận `Subscription` để gọi `request(n)`. Với callback này, Reactor **không tự request vô hạn**; nếu callback chỉ ghi log rồi không request thì nguồn có thể đứng chờ.

Trong tài liệu API hiện hành, overload dạng này được đánh dấu **deprecated** vì người dùng dễ quên request. Nên dùng `BaseSubscriber` để kiểm soát demand (mục 5). Đây là đoạn minh họa ý tưởng từ API cũ, **không phải cách khuyến nghị cho mã mới**:

~~~java
// API deprecated: minh họa ngoại lệ, không nên dùng trong mã mới.
flux.subscribe(
    value -> consume(value),
    error -> handle(error),
    () -> completed(),
    subscription -> subscription.request(2)
);
~~~

`consume`, `handle`, `completed`, `flux` ở đoạn trên là tên minh họa và **không phải** chương trình độc lập có thể chạy. Để chạy ví dụ điều khiển demand đầy đủ bằng Java 17+, xem mục 7.

## 4. Những cách tiêu thụ “terminal” khác liên quan đến unbounded request

Tài liệu Reactor “On Backpressure and Ways to Reshape Requests” còn nêu những thao tác ở điểm cuối như `Mono.block()`, `Flux.blockFirst()`, `Flux.blockLast()` là các đường tiêu thụ tạo subscription và yêu cầu dữ liệu tích cực, thường không để lập trình viên tự cấp demand từng phần tử.

~~~java
String value = Mono.just("OK").block();     // Chờ một kết quả, không manual request
Integer first = Flux.range(1, 3).blockFirst(); // Chờ phần tử đầu
Integer last = Flux.range(1, 3).blockLast();   // Chờ kết quả cuối
~~~

Cần phân biệt:

- `block()` và các biến thể là thao tác **chặn thread đang gọi**, không phải biến Publisher thành non-blocking.
- `blockFirst()` có thể hủy khi đã nhận phần tử đầu tiên; vì vậy việc nguồn có được yêu cầu nhiều phần tử **không** có nghĩa mọi phần tử sẽ đến consumer.
- Mỗi lần gọi một blocking terminal như `block()` trên cold Publisher thường tạo một subscription mới; với nguồn có side effect, side effect có thể lặp lại.

Reactor Reference cũng liệt kê các cách lặp `toIterable()` và `toStream()` trong nhóm cần lưu ý về demand lớn. Với API hiện hành, chúng có overload `batchSize` để giới hạn số phần tử prefetch và dùng bộ đệm cho việc lặp blocking. Vì vậy **không suy luận cứng rằng mọi lệnh gọi `toIterable()/toStream()` đều tạo chính xác một request upstream bằng `Long.MAX_VALUE`** trong mọi phiên bản và cấu hình; hãy quan sát `doOnRequest` hoặc cấu hình `batchSize` nếu cần kiểm soát thực tế.

Đặc biệt trong Spring WebFlux, **không gọi `block()` hoặc duyệt `toIterable()` trên thread event-loop/non-blocking**. Cách này có thể gây lỗi runtime và chặn khả năng phục vụ request. Thay vì chặn, kết hợp các Publisher bằng `map`, `flatMap`, `zip`, v.v., và trả Publisher cho framework.

## 5. `BaseSubscriber`: mặc định unbounded và cách cấp demand có chủ đích

`BaseSubscriber<T>` của Reactor là tiện ích triển khai `Subscriber<T>`, cung cấp các hook như `hookOnSubscribe`, `hookOnNext`, `hookOnComplete`, `hookOnError`, `hookOnCancel` và các thao tác `request(n)`, `requestUnbounded()`, `cancel()`.

### 5.1. Không override `hookOnSubscribe`: vẫn request vô hạn

~~~java
Flux.range(1, 3)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnNext(Integer value) {
            System.out.println("next=" + value);
        }
    });
~~~

Mặc định `BaseSubscriber.hookOnSubscribe` sẽ gọi tương đương `request(Long.MAX_VALUE)`. Do đó chỉ override `hookOnNext` **không** biến subscription thành bounded.

### 5.2. Cách thể hiện rõ chủ ý unbounded

~~~java
Flux.range(1, 3)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            requestUnbounded(); // Tương đương request(Long.MAX_VALUE)
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println(value);
        }

        @Override
        protected void hookOnError(Throwable error) {
            System.err.println("error=" + error.getMessage());
        }
    });
~~~

`requestUnbounded()` làm rõ rằng phía nhận cho phép toàn bộ dữ liệu ngay khi có. Lệnh này không đồng nghĩa thao tác `cancel()` đã mất tác dụng; vẫn có thể hủy subscription khi không còn nhu cầu.

### 5.3. Override và request một lượng hữu hạn

~~~java
Flux.range(1, 5)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2); // Chỉ cấp demand cho hai phần tử đầu tiên
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println("next=" + value);
            if (value == 2) {
                request(3); // Cấp tiếp sau khi đã xử lý hai item
            }
        }
    });
~~~

Nguồn phát đủ năm phần tử và hoàn tất. Nếu bỏ `request(3)`, subscriber chỉ nhận hai item, và subscription **vẫn chờ demand** đối với phần còn lại (trừ khi bị cancel hoặc gặp một tín hiệu kết thúc hợp lệ). Đây là khác biệt then chốt với `subscribe(Consumer)`.

**Lưu ý:** Nếu override `hookOnSubscribe` mà chỉ in log và không request thì bạn cũng đã bỏ hành vi unbounded mặc định. `BaseSubscriber` được thiết kế để dùng **một lần cho một subscription**; không tái sử dụng một instance đang hoạt động để đăng ký nhiều nguồn khác nhau. Để giữ handle subscriber và hủy khi cần, có thể dùng `subscribeWith(new BaseSubscriber<...>() { ... })`.

### 5.4. Tự triển khai `Subscriber` không có mặc định chung

Khi gọi `publisher.subscribe(customSubscriber)`, chính phần triển khai `customSubscriber.onSubscribe(Subscription)` quyết định có gọi `request`, gọi bao nhiêu và khi nào. Reactive Streams không tự giả định rằng mọi custom Subscriber đều yêu cầu `Long.MAX_VALUE`. Một subscriber không request có thể không nhận `onNext`, dù đã subscribe thành công.

## 6. Unbounded ở cuối không nhất thiết là unbounded tại nguồn

Demand chạy **ngược** từ subscriber qua chuỗi toán tử về upstream. Một vài toán tử có thể **thay đổi, chia lô, nhân hoặc giới hạn** số item được yêu cầu.

~~~text
Flux nguồn         Toán tử                    Subscriber cuối
     |                |                              |
     |<-- request(5) -|<--- request(Long.MAX_VALUE) --|
     |--- onNext ---> |------------------ onNext --->|
     |<-- request(5) -|                              |
     |--- onNext ---> |------------------ onNext --->|
~~~

Đây là sơ đồ khái niệm khi toán tử chia demand thành lô 5 phần tử; số request thực tế còn phụ thuộc chiến lược replenishment của toán tử.

### 6.1. `limitRate` chia request thành những lô

~~~java
Flux.range(1, 10)
    .doOnRequest(n -> System.out.println("upstream request=" + n))
    .limitRate(5, 0)
    .subscribe(value -> System.out.println("next=" + value));
~~~

Subscriber lambda cuối tự gửi request không giới hạn tới `limitRate`. Nhưng toán tử này yêu cầu upstream **theo lô tối đa 5**; tham số `lowTide = 0` dùng các lô nghiêm ngặt (`5` rồi `5`), không theo cơ chế tái bổ sung ở mốc phần trăm mặc định. Hai lần request của upstream là đủ cho nguồn mười phần tử trong ví dụ.

Với `limitRate(5)` một tham số, chiến lược cấp lại khi đã tiêu thụ một ngưỡng phần tử có thể khiến các request upstream có kích thước khác 5. Vì vậy để học chính xác demand, quan sát vị trí đặt `doOnRequest`.

### 6.2. `buffer` thay đổi đơn vị demand

~~~java
Flux.range(1, 100)
    .doOnRequest(n -> System.out.println("source asked=" + n))
    .buffer(10);
~~~

Nếu downstream yêu cầu `2` **danh sách**, toán tử `buffer(10)` có thể yêu cầu tối đa `20` phần tử đơn từ upstream để tạo hai danh sách. Do đó `request(2)` tại một vị trí không đồng nghĩa `request(2)` ở mọi vị trí.

Tương tự, `flatMap`, `publishOn` và một số toán tử khác có chính sách prefetch, concurrency hoặc queue; có thể phát nhiều request hữu hạn đến nguồn ngay cả khi subscriber cuối đã yêu cầu vô hạn. Kết luận về request phải gắn với **vị trí quan sát**.

### 6.3. `doOnRequest` là công cụ kiểm chứng

Đặt `doOnRequest` ngay cạnh nơi muốn quan sát:

~~~java
Flux<Integer> pipeline = Flux.range(1, 10)
    .doOnRequest(n -> System.out.println("before limitRate=" + n))
    .limitRate(5, 0)
    .doOnRequest(n -> System.out.println("after limitRate=" + n));

pipeline.subscribe(value -> {});
~~~

Log `after limitRate` quan sát demand **từ subscriber xuống toán tử** (sẽ thấy `Long.MAX_VALUE`), còn log `before limitRate` quan sát request **từ toán tử lên nguồn** (các lô hữu hạn). Không nên chỉ nhìn log của một bên rồi khẳng định cả chuỗi pipeline đã được giới hạn hay yêu cầu vô hạn.

## 7. Ví dụ Java 17+ chạy được: quan sát unbounded và bounded

Ví dụ này dùng Reactor Core 3.8.8, Maven và nguồn `Flux.range`/`Mono.just` đồng bộ, không đổi scheduler. Kết quả được thiết kế để stdout có thứ tự ổn định và cho thấy rõ `request`.

Tạo cấu trúc:

~~~text
reactor-unbounded-demo/
├── pom.xml
└── src/main/java/example/UnboundedDemandDemo.java
~~~

**Tệp `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-unbounded-demo</artifactId>
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
                <configuration>
                    <mainClass>example.UnboundedDemandDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tệp `src/main/java/example/UnboundedDemandDemo.java`:**

~~~java
package example;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class UnboundedDemandDemo {

    public static void main(String[] args) {
        System.out.println("== lambda subscribe ==");
        Flux.range(1, 3)
            .doOnRequest(n -> System.out.println("A request=" + n))
            .subscribe(
                n -> System.out.println("A next=" + n),
                error -> System.out.println("A error=" + error.getMessage()),
                () -> System.out.println("A complete")
            );

        System.out.println("== BaseSubscriber default ==");
        Flux.range(10, 2)
            .doOnRequest(n -> System.out.println("B request=" + n))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnNext(Integer n) {
                    System.out.println("B next=" + n);
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("B complete");
                }
            });

        System.out.println("== BaseSubscriber bounded ==");
        Flux.range(20, 3)
            .doOnRequest(n -> System.out.println("C request=" + n))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("C subscribed");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer n) {
                    System.out.println("C next=" + n);
                    if (n == 21) {
                        request(1);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("C complete");
                }
            });

        System.out.println("== blocking Mono ==");
        String value = Mono.just("ready")
            .doOnRequest(n -> System.out.println("D request=" + n))
            .block();
        System.out.println("D value=" + value);
    }
}
~~~

**Chạy từ thư mục `reactor-unbounded-demo`:**

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến:**

~~~text
== lambda subscribe ==
A request=9223372036854775807
A next=1
A next=2
A next=3
A complete
== BaseSubscriber default ==
B request=9223372036854775807
B next=10
B next=11
B complete
== BaseSubscriber bounded ==
C subscribed
C request=2
C next=20
C next=21
C request=1
C next=22
C complete
== blocking Mono ==
D request=9223372036854775807
D value=ready
~~~

Phân tích kết quả:

1. Overload `subscribe(onNext, onError, onComplete)` ở phần A gửi `Long.MAX_VALUE` ngay lập tức; chúng ta không viết `request` nhưng `doOnRequest` vẫn ghi nhận giá trị này.
2. `BaseSubscriber` ở phần B **không override `hookOnSubscribe`**, nên hành vi mặc định cũng là unbounded.
3. `BaseSubscriber` ở phần C **override `hookOnSubscribe`**, ban đầu request 2, sau khi nhận phần tử 21 mới request thêm 1; nguồn chỉ gửi đúng ba phần tử rồi hoàn tất.
4. `Mono.block()` ở phần D cũng đăng ký và chủ động yêu cầu dữ liệu; tuy nhiên nó **chặn thread** cho tới khi có kết quả.
5. Các nguồn đồng bộ nhỏ và không dùng scheduler giúp thứ tự quan sát dễ lặp lại. Với nguồn async, các callback có thể chạy ở thời điểm khác, nên không suy ra mọi `subscribe` đều đồng bộ.

## 8. Tác động hiệu năng và quản lý vòng đời

### 8.1. Khi nào request không giới hạn là phù hợp?

- **Nguồn hữu hạn, nhỏ, nằm trong bộ nhớ** (`Flux.just("a", "b")`, `Flux.range(1, 3)`), consumer xử lý nhanh: unbounded đơn giản và hợp lý.
- **`Mono<T>` chỉ có tối đa một phần tử**: request không giới hạn ít gây rủi ro về **số lượng phần tử của chính Mono**; vẫn cần lưu ý nếu hoạt động upstream tạo dữ liệu lớn hoặc blocking I/O.
- **Một terminal aggregation có giới hạn đầu vào rõ ràng**: có thể dùng unbounded, nhưng vẫn phải tính đến tài nguyên tạo/giữ dữ liệu và kích thước kết quả.

### 8.2. Khi nào cần cân nhắc demand hữu hạn?

- Nguồn có thể phát rất nhiều hoặc vô hạn phần tử.
- Một consumer xử lý chậm hơn nguồn (ghi DB, gọi API, mã hóa dữ liệu).
- Pipeline có queue, prefetch, `buffer`, `collectList` hay hoạt động tích lũy dữ liệu.
- Subscriber cần quyết định khi nào nhận lô tiếp theo dựa trên trạng thái tài nguyên.
- Mỗi phần tử mang tài nguyên phải đóng/release đúng vòng đời.

Unbounded demand **không tự gây tràn bộ nhớ**. Tác hại phụ thuộc nguồn, chiến lược phát, scheduler, buffer và tốc độ tiêu thụ. Nhưng nó loại bỏ cơ chế **giới hạn bởi demand của subscriber cuối**, khiến nguồn có thể phát hết khả năng; vì vậy không nên dùng nó như mặc định vô điều kiện trong các luồng dài hoặc có rủi ro tích lũy.

### 8.3. `Disposable.dispose()` là hủy, không phải hoàn tất

Các overload `subscribe(...)` thường trả về `Disposable`:

~~~java
Disposable disposable = Flux.interval(Duration.ofSeconds(1))
    .subscribe(
        tick -> System.out.println("tick=" + tick),
        error -> System.err.println("error=" + error.getMessage())
    );

// Ở một thời điểm phù hợp do ứng dụng quyết định:
disposable.dispose(); // yêu cầu hủy subscription
~~~

Đoạn này là **minh họa trong ứng dụng đã import `reactor.core.Disposable` và `java.time.Duration`**, không phải toàn bộ chương trình tự chạy. `dispose()` yêu cầu hủy; nó không phát một `onComplete` nhân tạo cho subscriber, cũng không bảo đảm tất cả công việc bất đồng bộ đã khởi động dừng lập tức.

Với nguồn đồng bộ hữu hạn `Flux.range(1, 1000).subscribe(...)`, phần lớn hoặc toàn bộ nguồn có thể đã hoàn tất **trước khi lời gọi `subscribe` trả về**, nên `dispose()` sau đó không thể quay ngược thời gian để dừng các phần tử đã phát. Nếu cần giới hạn, đặt `take(n)`, `limitRequest(n)`, `timeout` hoặc điều khiển demand từ đầu tùy mục tiêu.

### 8.4. `take` giới hạn dữ liệu nhận; `limitRate` giới hạn nhịp request

Không dùng lẫn ba câu hỏi khác nhau:

| Mục tiêu | Công cụ | Tác dụng |
| --- | --- | --- |
| Cấp demand theo từng đợt từ subscriber | `BaseSubscriber.request(n)` | Chủ động điều khiển khi nào cấp quyền cho dữ liệu mới |
| Chia request downstream lớn thành lô upstream | `limitRate(highTide, lowTide)` | Giữ luồng dữ liệu, nhưng thay đổi dạng request tới nguồn |
| Chỉ muốn tối đa N phần tử rồi kết thúc/hủy | `take(n)`, `limitRequest(n)` | Giới hạn tổng số phần tử chuyển xuống, không chỉ chia lô |

Một điểm kỹ thuật: `take(n)` có các overload/chính sách điều chỉnh mức request upstream; nếu cần giới hạn nghiêm ngặt request tới nguồn, kiểm tra variant `take(n, true)` hoặc `limitRequest(n)` theo Javadoc. Không kết luận “`take(n)` luôn yêu cầu đúng N từ mọi upstream” nếu pipeline còn các toán tử khác.

## 9. Ứng dụng trong Spring WebFlux

### 9.1. Handler thường phải trả về Publisher

~~~java
// Đoạn minh họa trong @RestController Spring WebFlux.
@GetMapping("/numbers")
public Flux<Integer> numbers() {
    return Flux.range(1, 100);
}
~~~

Khi Spring WebFlux xử lý HTTP, framework đăng ký vào Publisher khi cần ghi response; lượng dữ liệu nó yêu cầu phụ thuộc cơ chế HTTP, codec, các toán tử và subscriber nội bộ. **Không mặc định** rằng tất cả request thật tới upstream đều là `Long.MAX_VALUE` chỉ vì `Flux` xuất hiện trong kiểu trả về.

Tránh tự gọi `subscribe()` trong controller rồi trả `Mono.just("OK")`: thao tác độc lập có thể vẫn đang chạy khi HTTP đã trả OK, và lỗi/hủy không còn gắn với vòng đời response. Ưu tiên **trả lại Publisher** và kết hợp xử lý bằng `map`/`flatMap`/`then`.

### 9.2. Không xem `subscribe()` là cách “kích hoạt” an toàn cho I/O

~~~java
// Ví dụ có vấn đề nếu đang ở handler WebFlux:
service.save(event).subscribe(); // Mất khả năng gắn lỗi, cancel vào response
return Mono.just("accepted");
~~~

Thay vào đó, nếu phải đợi lưu thành công mới trả xác nhận:

~~~java
return service.save(event).thenReturn("accepted");
~~~

Nếu nghiệp vụ thật sự muốn xử lý background độc lập với request, phải thiết kế kênh công việc và vòng đời rõ ràng, thay vì chỉ gọi `subscribe()` rồi bỏ handle. Trọng tâm ở đây là **demand và ownership của Subscription**: ai đã subscribe thì phải chịu trách nhiệm với lỗi và hủy.

### 9.3. Đừng dùng blocking terminal trên event-loop

`block()`, `blockFirst()`, `blockLast()` và duyệt `toIterable()/toStream()` có thể chặn thread; trong pipeline non-blocking của WebFlux, điều này nguy hiểm cho khả năng đáp ứng và có thể gây `IllegalStateException` trên thread đánh dấu non-blocking. Tổ chức pipeline bằng các toán tử reactive và để framework thực hiện đăng ký.

## 10. Các lỗi phổ biến và cách chẩn đoán

**Lỗi 1 — Cho rằng gọi `subscribe(onNext)` đồng nghĩa `request(1)` từng lần.** Overload lambda phổ biến request `Long.MAX_VALUE`; callback `onNext` chỉ nhận dữ liệu, không tự điều tiết.

**Lỗi 2 — Tưởng một `BaseSubscriber` tự động có backpressure từng phần tử.** Nếu không override `hookOnSubscribe`, base implementation vẫn request unbounded. Muốn bounded phải chủ động gọi `request(n)` dương.

**Lỗi 3 — Override `hookOnSubscribe` nhưng không request.** Với nguồn cần demand để phát `onNext`, subscription có thể đứng yên. Khắc phục: gọi `request(n)` và cấp thêm khi đã xử lý đủ.

**Lỗi 4 — Dùng `request(0)` để tạm dừng.** Đây là request sai theo Reactive Streams, không phải lệnh pause. Muốn tạm thời không nhận dữ liệu mới, đừng gửi thêm demand.

**Lỗi 5 — Nghĩ `request(Long.MAX_VALUE)` buộc nguồn tạo số lượng phần tử khổng lồ.** Nó là **quyền phát** không giới hạn; nguồn có thể kết thúc sau 0, 1 hoặc N phần tử.

**Lỗi 6 — Kết luận demand upstream từ một `doOnRequest` ở downstream.** Các toán tử `limitRate`/`buffer`/`flatMap`/`publishOn` có thể reshape request. Đặt hook ở đúng ranh giới cần quan sát.

**Lỗi 7 — Dùng `subscribe()` nhưng không quản lý lỗi.** Với luồng có thể báo lỗi, cung cấp đường xử lý `onError` hoặc trả Publisher cho framework quản lý vòng đời.

**Lỗi 8 — Nghĩ `Disposable.dispose()` gửi `onComplete`.** `dispose()` hủy subscription; cancellation không đồng nghĩa completion.

**Lỗi 9 — Dùng `block()` trên event-loop để đơn giản hóa xử lý.** Kết quả là chặn thread và có thể gây lỗi; dùng ghép Publisher bất đồng bộ.

**Lỗi 10 — Coi có `limitRate` là tự động giới hạn toàn bộ bộ nhớ.** Nó chủ yếu điều chỉnh request upstream. Queue/buffer/aggregation và nguồn thực tế vẫn quyết định tiêu thụ tài nguyên.

**Lỗi 11 — Đăng ký lại cùng instance `BaseSubscriber` đang hoạt động.** Instance được thiết kế gắn với một subscription; tạo subscriber mới cho mỗi lần đăng ký.

**Lỗi 12 — Nhầm request unbounded với non-blocking.** Demand là điều phối tín hiệu, không tự biến thao tác I/O chặn thành non-blocking.

## 11. Bài tập kiểm tra và đáp án

1. `Flux.range(1, 3).subscribe(System.out::println)` có gửi `request(3)` mặc định không? **Không**. Lambda subscriber phổ biến gửi `Long.MAX_VALUE`, mặc dù nguồn chỉ có ba số.
2. `Flux.range(1, 3).subscribe()` có chạy nguồn không? **Có**, subscription có request unbounded; thiếu consumer cuối không ngăn upstream chạy.
3. `new BaseSubscriber<>() { hookOnNext(...) }` có tự yêu cầu từng item không? **Không**; `hookOnSubscribe` mặc định request unbounded.
4. Override `hookOnSubscribe` để chỉ ghi log rồi không gọi `request` sẽ thế nào? **Nguồn không có demand cho `onNext`, nên thường đứng chờ**. Hãy chủ động request dương.
5. `source.limitRate(4, 0).subscribe(onNext)`: subscriber cuối có yêu cầu vô hạn không? **Có**. Nhưng `limitRate` chia yêu cầu gửi upstream thành các lô tối đa 4.
6. Khi subscriber gọi `request(2)` rồi `request(3)`, tối đa có bao nhiêu phần tử `onNext` được phép phát nếu trước đó không còn demand? **5**, trừ các phần tử đã được phát làm giảm demand; nguồn có thể phát ít hơn nếu hoàn tất hoặc lỗi.
7. Có nên gọi `block()` ngay trong handler WebFlux không? **Không** trên thread non-blocking/event-loop; hãy trả Publisher và ghép chuỗi bằng toán tử.
8. Nếu `Flux.just("A", "B")` đã hoàn tất thì `dispose()` sau khi `subscribe` trả về có thể “thu hồi” item đã phát không? **Không**.
9. `request(-1)` có đồng nghĩa với yêu cầu vô hạn không? **Không**, đây là request không hợp lệ.
10. Nếu muốn dữ liệu chỉ phát tối đa 5 item, dùng `limitRate(5)` có đủ không? **Không**: `limitRate` điều chỉnh kích thước request, không giới hạn tổng số item. Dùng `take(5)`/`limitRequest(5)` đúng mục đích.

## 12. Ghi nhớ và tài liệu tham khảo

Quy tắc thực hành:

- **`subscribe()` và hầu hết overload lambda → request `Long.MAX_VALUE`.**
- **`BaseSubscriber` không override `hookOnSubscribe` → cũng request không giới hạn.**
- **Muốn chủ động điều khiển demand → custom `Subscriber`/`BaseSubscriber` và `request(n)` dương.**
- **Demand quan sát ở cuối pipeline có thể khác demand đi tới nguồn** do toán tử trung gian.
- **Request không giới hạn không thay thế cho giới hạn dữ liệu, cleanup, xử lý lỗi và cancellation.**

Tài liệu tra cứu trực tiếp:

1. [Project Reactor – On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): liệt kê cách đăng ký thường phát unbounded request, `BaseSubscriber`, `limitRate`.
2. [Project Reactor – Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): overload `subscribe`, cách kiểm soát demand và `requestUnbounded()`.
3. [Project Reactor Javadoc – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): các overload `subscribe`, `limitRate`, `toIterable`/`toStream` và chi tiết deprecated.
4. [Project Reactor Javadoc – BaseSubscriber](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html): hook mặc định và phương thức request/cancel.
5. [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): quy tắc `request(n)`, `Long.MAX_VALUE`, tín hiệu terminal và cancel.