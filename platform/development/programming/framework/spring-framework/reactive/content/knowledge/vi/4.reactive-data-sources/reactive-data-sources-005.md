# Nguồn theo thời gian bằng interval và delay trong Project Reactor

> **Chủ đề:** Tạo nguồn dữ liệu · **Module:** Spring Framework – Reactive. Bài học giải thích cách phát tín hiệu theo thời gian và trì hoãn nguồn/tín hiệu bằng Reactor Mono, Flux; có chương trình Java 17+ tự chạy, test thời gian ảo và ví dụ áp dụng với Spring WebFlux.

## 1. Kết quả cần đạt

Hoàn thành bài này, bạn cần:
1. Tạo nguồn **Mono.delay** chỉ phát một giá trị sau một khoảng đợi và **Flux.interval** phát tick theo chu kỳ.
2. Phân biệt **delaySubscription**, **delayElement**, **delayElements**, **delaySequence**; dự đoán chính xác lúc subscribe, onNext và onComplete.
3. Hiểu Scheduler, cold publisher, cancel, take, overflow do thiếu demand; không chặn event-loop bằng Thread.sleep hoặc block trong WebFlux.
4. Viết kiểm thử với **StepVerifier.withVirtualTime** để kiểm tra vài giờ logic mà không đợi vài giờ thật.
5. Đưa nguồn tick vào polling hoặc Server-Sent Events (SSE) với lifecycle, giới hạn tải và cách xử lý client chậm rõ ràng.

**Tư duy cốt lõi:** các phương thức này **mô tả công việc bất đồng bộ theo thời gian**; đồng hồ của pipeline thường bắt đầu khi có subscription, chứ không phải lúc khai báo biến Flux hoặc Mono. Duration là khoảng thời gian tương đối, không phải lịch cố định theo múi giờ.

~~~text
Mono.delay(2s)                 subscribe ─── 2s ─── 0L | complete
Flux.interval(1s)              subscribe ─ 1s ─ 0 ─ 1s ─ 1 ─ 1s ─ 2 ─ ...
Flux.interval(2s, 1s)          subscribe ─── 2s ─── 0 ─ 1s ─ 1 ─ ...
delaySubscription(2s)          subscribe ─── 2s ─── upstream subscribe → dữ liệu
Flux.just(A,B,C).delayElements(1s)   subscribe ─ 1s ─ A ─ 1s ─ B ─ 1s ─ C
Flux.just(A,B,C).delaySequence(1s)   subscribe ─ 1s ─ A,B,C
~~~

Sơ đồ mang ý nghĩa thứ tự và khoảng đợi **xấp xỉ**. Scheduler, tải máy, thời gian thực thi upstream, request demand và bộ đệm có thể ảnh hưởng thời điểm quan sát thực tế. Trong Reactive Streams, một nguồn có thể phát nhiều onNext và cuối cùng onComplete hoặc onError; cancel của subscriber là tín hiệu dừng nguồn đang chạy. Mono có tối đa một onNext, còn Flux có thể có nhiều.

## 2. Mono.delay: phát đúng một tick

**Mono.delay(Duration delay)** tạo một Mono<Long>. Sau khi subscribe và đến hạn, nó phát **0L** rồi hoàn thành. Giá trị 0L là tick đầu tiên theo hợp đồng API, **không phải timestamp** và không phải số giây đã qua.

~~~java
Mono<Long> timer = Mono.delay(Duration.ofSeconds(2));
// subscribe, đợi khoảng 2 giây, onNext(0L), onComplete.
~~~

Biến timer trong fragment này mới chỉ mô tả pipeline, chưa có subscriber nên chưa phát gì. Muốn trả thông điệp sau một khoảng đợi:

~~~java
Mono<String> welcomeLater = Mono.delay(Duration.ofSeconds(2))
    .map(tick -> "Sẵn sàng");
~~~

Muốn chỉ có tín hiệu hoàn tất sau khoảng đợi mà không cần dữ liệu 0L:

~~~java
Mono<Void> finishedLater = Mono.delay(Duration.ofSeconds(2)).then();
~~~

**Khi dùng:** hẹn một tín hiệu một lần, tạo delay có thể test được, mô phỏng phản hồi chậm, phối hợp timeout/fallback. **Không dùng** Mono.delay làm hệ thống job bền vững: nếu không subscribe hoặc tiến trình dừng, không có cơ chế lưu lại job phải chạy sau restart. Để lên lịch theo đồng hồ thực (ví dụ 08:00 mỗi ngày), hãy chọn scheduler theo lịch/cron và persistence tương ứng, thay vì suy luận từ interval/delay.

Mono.delay có overload nhận Scheduler khi cần điều khiển riêng nơi timer chạy. Không cần tạo thread hoặc gọi sleep để hẹn giờ; Scheduler chịu trách nhiệm lập lịch.

## 3. Flux.interval: phát 0, 1, 2... theo chu kỳ

### 3.1. Ba cách viết cơ bản

~~~java
// Phát 0L sau khoảng 1s; 1L sau khoảng 2s; tiếp tục vô hạn.
Flux<Long> oneSecond = Flux.interval(Duration.ofSeconds(1));

// Chờ khoảng 2s trước tick 0, sau đó mỗi 1s một tick.
Flux<Long> withInitialDelay = Flux.interval(
    Duration.ofSeconds(2), Duration.ofSeconds(1));

// Có scheduler thời gian riêng, trong ứng dụng đã quản lý lifecycle:
Flux<Long> customTimer = Flux.interval(
    Duration.ofSeconds(2),
    Duration.ofSeconds(1),
    scheduler);
~~~

Trong fragment cuối, scheduler là biến **Scheduler** đã được tạo/tiêm trong ứng dụng, không phải biến có sẵn trong Reactor. Theo mặc định, các toán tử timer sử dụng Scheduler phù hợp của Reactor, thường là parallel. Không cần tự spawn một thread cho mỗi tick.

**Quy tắc bắt buộc ghi nhớ:**
- Dạng interval(period) phát **tick 0 sau period**, không phải ngay lập tức; dạng interval(initialDelay, period) cho phép đổi mốc đầu.
- Tick có kiểu Long và tăng từ 0, không chứa giờ hệ thống. Muốn kèm timestamp, tạo lúc phát, ví dụ map(tick -> Instant.now()) và hiểu tính không quyết định của wall clock trong test.
- Flux.interval bản thân là **nguồn vô hạn**, thông thường không có onComplete. Trong ví dụ hữu hạn dùng take(n); trong stream thật cần cơ chế cancel khi client rời đi.
- Mỗi subscription vào nguồn interval lạnh (cold) có nhịp riêng. Hai subscriber đăng ký ở hai thời điểm khác nhau sẽ không tự đồng bộ một nhịp toàn cục.

### 3.2. Kết thúc nguồn vô hạn bằng take

~~~java
Flux<Long> firstThree = Flux.interval(Duration.ofMillis(100))
    .take(3); // 0L, 1L, 2L, rồi onComplete ở downstream.
~~~

Khi đủ ba phần tử, take hoàn tất phía downstream và hủy upstream để ngừng tick mới. Với HTTP request bị hủy, Spring WebFlux thường chuyển cancel về Publisher; nhưng mã nghiệp vụ vẫn cần quản lý những tài nguyên không do subscription sở hữu.

Không gọi blockLast() vào Flux.interval vô hạn: thao tác sẽ đợi mãi vì không có terminal signal. Trong controller WebFlux, cũng không gọi block()/blockFirst() ngay cả với chuỗi hữu hạn vì có thể khóa event-loop.

### 3.3. Backpressure: interval không thể dừng thời gian

Reactive Streams cho phép subscriber báo nhu cầu qua request(n). Flux.interval là **nguồn theo đồng hồ**, không thể bắt thời gian “đợi” cho đủ request. Theo Reactor API, nếu đến hạn phát tick mà downstream chưa request đủ, interval có thể phát **onError(IllegalStateException: overflow)**. Đây không phải lỗi mạng hay lỗi thread ngẫu nhiên mà là phản ứng với demand thiếu.

Giải pháp phải theo yêu cầu nghiệp vụ:
- Subscriber cần tick thường xuyên: bảo đảm demand đúng; test với initial request khác 0 và chính sách cancel.
- Chỉ cần trạng thái mới nhất (ví dụ UI heartbeat): cân nhắc **onBackpressureLatest** hoặc **onBackpressureDrop** với chính sách mất tick rõ ràng.
- Cần bảo toàn mọi sự kiện: đừng coi interval là event log; dùng queue/broker/lưu trữ và cơ chế replay/ack.
- Không dùng buffer vô hạn để che overflow, vì có thể gây tăng RAM khi consumer chậm mãi.

Một tick có thể kích hoạt tác vụ I/O. Nếu dùng flatMap để gọi remote API, giới hạn concurrency và đặt timeout; khi xử lý chậm hơn period, công việc có thể chồng lên nhau. Muốn tuần tự, cân nhắc concatMap, nhưng cũng cần chính sách khi nguồn phát nhanh hơn quá trình tiêu thụ.

## 4. Delay không chỉ có một loại

Có sự khác nhau quan trọng giữa **tạo nguồn thời gian** (Mono.delay/Flux.interval) và **tác động thời gian lên Publisher đã có**.

| Phương thức | Điều bị hoãn | Ý nghĩa |
| --- | --- | --- |
| Mono.delay(d) | Tạo một onNext(0L) sau d | Nguồn một lần, rồi hoàn thành. |
| Flux.interval(d) | Tạo chuỗi tick mỗi d | Nguồn định kỳ, vô hạn nếu không take/cancel. |
| source.delaySubscription(d) | Subscription tới upstream | Upstream bắt đầu làm việc muộn. |
| mono.delayElement(d) | Giá trị onNext của Mono có dữ liệu | Mono rỗng/lỗi không đợi d như một giá trị. |
| flux.delayElements(d) | Từng phần tử onNext | Có thể tạo pacing giữa phần tử của nguồn phát tức thì. |
| flux.delaySequence(d) | Dịch toàn chuỗi về sau | Giữ nhịp tương đối giữa các phần tử theo nguồn. |

### 4.1. delaySubscription: đợi trước khi bắt đầu nguồn

~~~java
Mono<String> remote = Mono.defer(() -> {
    System.out.println("Upstream được subscribe");
    return Mono.just("OK");
}).delaySubscription(Duration.ofSeconds(2));
~~~

Mono.defer trì hoãn tạo Publisher cho đến subscription. Với delaySubscription, dòng log chỉ xuất hiện sau khoảng đợi nếu subscription vẫn còn. Đây là khác biệt cốt lõi với delayElement: một nguồn có side effect ở subscribe có thể bắt đầu ngay nếu chỉ hoãn tín hiệu đầu ra. Lưu ý: nếu bên ngoài pipeline đã khởi chạy một tác vụ nóng, delaySubscription không tự trì hoãn tác vụ đó.

### 4.2. Mono.delayElement: đợi trước khi nhận giá trị

~~~java
Mono<String> result = Mono.just("OK")
    .delayElement(Duration.ofSeconds(2));
~~~

Nguồn vẫn được subscribe; **onNext("OK")** đến downstream muộn. Với Mono.empty() hoặc nguồn phát lỗi, không có phần tử để delayElement hoãn, nên việc hoàn thành rỗng/lỗi thường chuyển tiếp không chờ 2 giây. Nếu cần hoãn cả quá trình upstream, dùng delaySubscription. Nếu cần trễ trước khi chuyển sang publisher khác, dùng Mono.delay(d).then(otherPublisher).

### 4.3. Flux.delayElements: hoãn từng onNext

~~~java
Flux<String> paced = Flux.just("A", "B", "C")
    .delayElements(Duration.ofSeconds(1));
~~~

Với nguồn **phát ngay lập tức**, A được thấy sau khoảng 1s, B khoảng 2s, C khoảng 3s. delayElements thường có tác dụng pacing ở downstream, giữ thứ tự; nhưng không nên xem là rate limiter đầy đủ với mọi dạng nguồn bất đồng bộ. Nó chỉ hoãn tín hiệu, không tự tăng khả năng chịu tải của DB/HTTP và không bảo đảm đồng hồ chính xác tuyệt đối. Theo Javadoc, empty/error trực tiếp không bị trì hoãn như onNext.

### 4.4. Flux.delaySequence: dời cả luồng

~~~java
Flux<String> shifted = Flux.just("A", "B", "C")
    .delaySequence(Duration.ofSeconds(1));
~~~

Nguồn được subscribe **ngay**, còn phần downstream được dịch thời gian khoảng 1 giây; các khoảng cách tương đối giữa phần tử được giữ lại. Với nguồn tức thì, A/B/C có thể xuất hiện gần nhau sau 1 giây. Với nguồn đang phát mỗi 500ms, khoảng cách khoảng 500ms được giữ thay vì bị biến thành 1 giây giữa mỗi phần tử.

**So sánh nhanh với cùng nguồn Flux.just(A,B,C):**
- delaySubscription(2s): subscribe upstream sau 2s, A/B/C đến nhanh.
- delayElements(2s): A sau khoảng 2s, B sau 4s, C sau 6s.
- delaySequence(2s): subscribe upstream ngay, A/B/C sau khoảng 2s và gần nhau.
  
Đây là dự đoán cho upstream đồng bộ; với một nguồn vốn đã mất thời gian để tạo giá trị, hãy đo/test tín hiệu thật.

### 4.5. Điều gì không phải delay?

Thread.sleep(1000) **khóa thread** đang chạy. Trong server Netty event-loop, một sleep có thể làm chậm nhiều request khác. Mono.delay và delayElements dùng cơ chế lập lịch và không yêu cầu khóa thread trong lúc chờ. Tuy nhiên **không có phép màu**: nếu map/timer callback làm CPU nặng hoặc gọi JDBC đồng bộ, thread Scheduler vẫn có thể bị bận. Khi cần bridge một thư viện blocking, cô lập bằng boundedElastic có giới hạn hoặc chọn driver reactive; không dùng Schedulers.parallel cho I/O blocking.

## 5. Scheduler và quản lý thời gian

Scheduler đảm nhận việc thực thi/hẹn giờ. Các operator thời gian thường có overload nhận Scheduler; nếu không chỉ định, Reactor cung cấp Scheduler mặc định. subscribeOn ảnh hưởng đường subscribe và nguồn upstream; publishOn chuyển ngữ cảnh cho operator ở phía sau. Chúng không phải cách thay cho delay khi yêu cầu là đợi chính xác một Duration.

~~~java
Scheduler timer = Schedulers.newSingle("app-timer");
// Đặt timer trong bean có lifecycle rõ ràng; không dispose trước subscription.
Flux<Long> ticks = Flux.interval(
    Duration.ofSeconds(1), Duration.ofSeconds(1), timer);
~~~

Fragment trên cần import reactor.core.scheduler.Scheduler và Schedulers; nó không phải chương trình độc lập, và muốn quan sát tick phải subscribe tại boundary phù hợp. Với Scheduler tự tạo, ứng dụng cần dispose khi không còn subscription hoặc khi shutdown; tránh tạo nhiều Scheduler per request. Trong Spring, để framework quản lý hoặc cấu hình bean lifecycle. Không dùng Schedulers.newSingle cho phần I/O blocking nặng.

**Độ chính xác:** timer chịu tác động của thread scheduling, GC pause, CPU, container throttle và tải hệ thống. Tick thứ 100 không chứng minh đã trôi đúng 100 giây. Interval là lịch *tương đối với subscription*, không giải quyết lịch chính xác theo ngày/tháng, DST, múi giờ, chạy bù sau restart và bầu leader giữa nhiều instance.

## 6. Dự án Java 17+ chạy được

Dùng Reactor Core **3.8.8** (release ổn định của Project Reactor lúc biên soạn) và JUnit 5. Các ví dụ chạy trong **CLI**, nơi block() chỉ có vai trò chờ kết quả tại điểm cuối để in output; khi dùng WebFlux, trả Mono/Flux cho framework và không block.

### 6.1. Cấu trúc

~~~text
reactor-timed-sources/
├── pom.xml
├── src/main/java/com/example/timed/TimedDemo.java
└── src/test/java/com/example/timed/TimedDemoTest.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-timed-sources</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/com/example/timed/TimedDemo.java**:

~~~java
package com.example.timed;

import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class TimedDemo {
    public static void main(String[] args) {
        Long once = Mono.delay(Duration.ofMillis(50)).block();
        System.out.println("delay=" + once);

        List<Long> periodic = Flux.interval(Duration.ofMillis(50))
            .take(3).collectList().block();
        System.out.println("interval=" + periodic);

        List<Long> afterInitialWait = Flux.interval(
                Duration.ofMillis(100), Duration.ofMillis(50))
            .take(3).collectList().block();
        System.out.println("initialWait=" + afterInitialWait);

        String message = Mono.just("OK")
            .delayElement(Duration.ofMillis(50)).block();
        System.out.println("delayElement=" + message);

        List<String> paced = Flux.just("A", "B", "C")
            .delayElements(Duration.ofMillis(50)).collectList().block();
        System.out.println("delayElements=" + paced);

        List<String> shifted = Flux.just("A", "B", "C")
            .delaySequence(Duration.ofMillis(50)).collectList().block();
        System.out.println("delaySequence=" + shifted);

        List<Integer> startLater = Flux.range(1, 3)
            .delaySubscription(Duration.ofMillis(50))
            .collectList().block();
        System.out.println("delaySubscription=" + startLater);
    }
}
~~~

Tại thư mục dự án, cần Java 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.timed.TimedDemo
~~~

**Những dòng stdout do main in ra** (không tính log Maven):

~~~text
delay=0
interval=[0, 1, 2]
initialWait=[0, 1, 2]
delayElement=OK
delayElements=[A, B, C]
delaySequence=[A, B, C]
delaySubscription=[1, 2, 3]
~~~

Các giá trị/thứ tự cố định; độ trễ thực tế có thể chênh vài mili-giây hoặc hơn. Các lệnh block() chỉ xuất hiện trong main CLI và **không thuộc API WebFlux**.

## 7. Kiểm thử bằng VirtualTimeScheduler / StepVerifier

Đây là cách kiểm chứng **thời gian logic** mà không chờ thật. StepVerifier.withVirtualTime nhận supplier để dựng Publisher **sau khi virtual scheduler được cài đặt**. Mỗi thenAwait(Duration) tiến clock ảo; expectNext và verifyComplete xác nhận chính xác các tín hiệu.

**src/test/java/com/example/timed/TimedDemoTest.java**:

~~~java
package com.example.timed;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TimedDemoTest {

    @Test
    void intervalStartsWithZeroAndStopsAfterTake() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1)).take(3))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(0L)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(1L)
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(2L)
            .verifyComplete();
    }

    @Test
    void monoDelayCanWaitADayInVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofDays(1)))
            .expectSubscription()
            .thenAwait(Duration.ofDays(1))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void delayElementsPacesSynchronousValues() {
        StepVerifier.withVirtualTime(() ->
                Flux.just("A", "B", "C")
                    .delayElements(Duration.ofSeconds(1)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("A")
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("B")
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("C")
            .verifyComplete();
    }

    @Test
    void delaySubscriptionDefersUpstreamSideEffect() {
        AtomicInteger starts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                    starts.incrementAndGet();
                    return Mono.just("ready");
                }).delaySubscription(Duration.ofHours(2)))
            .expectSubscription()
            .then(() -> assertEquals(0, starts.get()))
            .thenAwait(Duration.ofHours(2))
            .expectNext("ready")
            .verifyComplete();

        assertEquals(1, starts.get());
    }

    @Test
    void intervalWithoutDemandSignalsOverflow() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1)), 0)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Các test minh họa: tick bắt đầu từ 0 và kết thúc nhờ take; chờ 1 ngày ảo; delayElements giãn các phần tử; delaySubscription chặn side effect; interval không có demand ở thời điểm phát sẽ báo lỗi.

**Nguyên tắc test đúng:**
- Dựng Flux.interval/Mono.delay bên **trong lambda** của withVirtualTime, không truyền Flux tạo sẵn dùng Scheduler thật.
- Tiến clock bằng thenAwait hoặc expectNoEvent, không dùng Thread.sleep trong test.
- Nếu test nguồn vô hạn, dùng take(n) hoặc thenCancel, không đợi verifyComplete vô thời hạn.
- Với expectNoEvent, hãy gọi expectSubscription trước, vì event subscription cũng được tính; có thể chọn mốc 999ms để chắc chắn chưa đến tick 1s.
- Với operator dùng Scheduler tự tạo bên ngoài test hoặc I/O thật, VirtualTimeScheduler không tự điều khiển được; mock/fake dependency hoặc thiết kế lại test boundary.

### 7.1. Test cancellation với request hữu hạn

Fragment dưới đây đặt trong một test method, dùng import giống file bên trên:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)), 2)
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(1L)
    .thenCancel()
    .verify();
~~~

Subscriber request hai phần tử và chủ động cancel trước tick thứ ba. Subscription của interval ngừng phát cho subscriber này. Nếu upstream có Future/thư viện bên ngoài đã tự chạy không gắn lifecycle reactive, cancel không bắt buộc tự dừng công việc đó; cần thiết kế khả năng hủy từ nguồn.

### 7.2. Test timeout có fallback

Fragment bên trong test method:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
            .timeout(Duration.ofSeconds(2))
            .onErrorReturn(-1L))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(-1L)
    .verifyComplete();
~~~

Ở đây timeout hủy upstream chờ 5 giây và chuyển sang giá trị fallback -1L khi hết thời gian ảo 2 giây. Trong thực tế phải chọn fallback theo domain; không biến sự cố dữ liệu/tính toàn vẹn thành kết quả “thành công” không kiểm soát.

## 8. Ứng dụng vào Spring WebFlux: SSE

Reactor có thể phát nhịp qua **Server-Sent Events** để trình duyệt/HTTP client nhận dòng cập nhật liên tục. Trong WebFlux, controller **trả Publisher**, framework subscribe và chuyển dữ liệu ra HTTP; không gọi block()/subscribe() trong controller.

Đoạn controller sau là **fragment tích hợp**, không phải chương trình Maven độc lập ở mục 6: cần một Spring Boot app đã có spring-boot-starter-webflux, cấu hình server và các import của WebFlux.

~~~java
package com.example.web;

import java.time.Duration;
import java.time.Instant;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
class ClockController {
    record Tick(long sequence, String time) {}

    @GetMapping(path = "/api/ticks",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Tick>> stream() {
        return Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
            .map(n -> ServerSentEvent.<Tick>builder()
                .id(Long.toString(n))
                .event("tick")
                .data(new Tick(n, Instant.now().toString()))
                .build());
    }
}
~~~

Trên server chạy ở localhost:8080, có thể thử:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/ticks
~~~

Ví dụ khung dữ liệu SSE, **chỉ minh họa** (giá trị thời gian do đồng hồ thực khi chạy quyết định):

~~~text
id:0
event:tick
data:{"sequence":0,"time":"2026-11-08T01:00:00Z"}

id:1
event:tick
data:{"sequence":1,"time":"2026-11-08T01:00:01Z"}
~~~

Những vấn đề cần cân nhắc khi đưa vào production:
- **Mỗi HTTP subscriber có một interval lạnh riêng.** Nếu phải broadcast sự kiện chung, thiết kế multicast/Sinks với replay, client đến muộn và chính sách quá tải cụ thể.
- Client có thể ngắt bất kỳ lúc nào; pipeline cần cancel, cleanup, timeout và metric phù hợp. SSE qua proxy có thể bị buffer hoặc timeout; kiểm tra cấu hình network và reconnect.
- Nếu map() làm CPU nặng hoặc block, timer thread có thể bị nghẽn. Với remote WebClient trả Mono, dùng flatMap với concurrency hữu hạn và chính sách xử lý slow consumer.
- **Instant.now() không bị virtual time thay đổi**. Để kiểm tra timestamp có thể inject java.time.Clock, còn test interval dùng VirtualTimeScheduler.
- SSE phát tick không bảo đảm lưu giữ/replay sự kiện; cần event ID bền và broker/storage nếu nghiệp vụ đòi không mất dữ liệu.
- Cần xác thực, phân quyền, giới hạn kết nối và bảo vệ tài nguyên như các API HTTP khác.

## 9. Polling bất đồng bộ: dùng tick để kích hoạt công việc

Ví dụ fragment cho service với một WebClient/repository có API reactive:

~~~java
Flux<Status> statuses = Flux.interval(Duration.ofSeconds(5))
    .flatMap(tick -> statusClient.fetchStatus(), 2);
~~~

Giả định statusClient.fetchStatus() là phương thức thực của ứng dụng trả **Mono<Status>**. Fragment chỉ minh họa, không chạy độc lập vì Status/statusClient chưa được định nghĩa. flatMap(..., 2) giới hạn tối đa hai inner subscriptions cùng lúc; kết quả có thể khác thứ tự tick. Nếu cần chạy tuần tự, cân nhắc concatMap, đồng thời phải hiểu điều gì xảy ra khi tác vụ mất hơn period. Không dùng interval(5s) rồi mặc nhiên hiểu là đợi lần polling trước hoàn thành mới bắt đầu lượt sau.

**Đặt giới hạn vận hành:** timeout cho remote call và toàn luồng, retry có điều kiện/backoff cho lỗi tạm thời, giới hạn concurrency, kết nối và hàng chờ, ngừng polling khi subscriber cancel. Nếu polling thực hiện ghi dữ liệu, cần idempotency khi retry; nếu yêu cầu không mất mỗi lần trigger, dùng job queue bền vững thay interval. Với lỗi upstream, quyết định onError có kết thúc cả stream hay onErrorResume trong phạm vi từng inner call để tiếp tục kỳ sau; không nuốt lỗi một cách mơ hồ.

## 10. Bảng chọn nhanh

| Tình huống | Chọn | Lưu ý |
| --- | --- | --- |
| Sau 1 giây phát một tín hiệu rồi complete | Mono.delay(1s) | Giá trị là 0L. |
| Mỗi 1 giây tạo tick không giới hạn | Flux.interval(1s) | Tick đầu sau khoảng 1s. |
| Sau 3 giây mới tick, tiếp theo mỗi 500ms | Flux.interval(3s, 500ms) | Initial delay tách khỏi period. |
| Chờ 2 giây trước khi kết nối remote | source.delaySubscription(2s) | Hoãn subscription upstream. |
| Có Mono chứa một giá trị, muốn giao sau 2 giây | mono.delayElement(2s) | Mono rỗng/lỗi không bị hoãn như onNext. |
| Có A,B,C phát tức thì, muốn chúng cách nhau 1 giây | flux.delayElements(1s) | Pacing từng phần tử. |
| Muốn toàn sequence đến muộn 1 giây nhưng vẫn giữ nhịp nguồn | flux.delaySequence(1s) | Upstream subscribe ngay. |
| Muốn đúng 5 tick rồi kết thúc | interval(...).take(5) | Hủy nguồn sau đủ phần tử. |
| Test timer 24 giờ trong vài mili-giây | StepVerifier.withVirtualTime | Dựng Publisher trong lambda. |
| Làm job chính xác vào 08:00 và hồi phục sau restart | Scheduler theo lịch + storage | Không dùng interval thay cho cron bền vững. |

## 11. Sai lầm phổ biến và cách sửa

1. **Không thấy tick:** mới tạo Flux, chưa subscribe. Trong WebFlux trả Flux để framework subscribe; trong test dùng StepVerifier; trong CLI dùng boundary phù hợp.
2. **Chương trình treo:** chờ completion của interval vô hạn. Thêm take, điều kiện dừng hoặc cancel. Không dùng blockLast() với nguồn không kết thúc.
3. **Tick đầu xuất hiện muộn 1 chu kỳ:** interval(period) vốn đợi period. Nếu muốn ban đầu gần như ngay lập tức, dùng initial delay Duration.ZERO.
4. **delaySequence tưởng là delayElements:** delaySequence dời cả chuỗi và giữ nhịp nguồn, còn delayElements hoãn từng giá trị. Với Flux.just, output khác rõ.
5. **Mono.empty().delayElement vẫn kết thúc ngay:** delayElement chỉ hoãn giá trị; chọn delaySubscription hoặc Mono.delay(...).then(...) nếu muốn hoãn thứ khác.
6. **Overflow khi downstream không request:** interval cần demand ở thời điểm tick; thiết kế demand/drop/latest hoặc nguồn có queue, không buffer vô hạn.
7. **Test virtual time treo:** tạo Publisher trước supplier, quên thenAwait, hoặc dùng Scheduler riêng không do virtual time quản lý.
8. **CPU/HTTP bị nghẽn dù đã dùng delay:** có thao tác blocking trong callback. Tách I/O blocking sang boundedElastic có giới hạn hoặc dùng API reactive, đo bằng profiler.
9. **Lệch timestamp hay sai cron:** interval dùng duration tương đối; độ trễ scheduling và wall clock không phải SLA chính xác theo lịch.
10. **Đặt retry cho toàn bộ pipeline có side effect:** retry tái subscribe, có thể tạo lại tick hay gọi ghi lại. Xác định phạm vi retry và idempotency trước khi dùng.

## 12. Bài tập tự kiểm tra

**Bài 1 – 5 tick:** Tạo số 0..4 theo chu kỳ 200ms và kiểm tra kết thúc thành công bằng StepVerifier.withVirtualTime.

~~~java
Flux<Long> five = Flux.interval(Duration.ofMillis(200)).take(5);
~~~

**Bài 2 – Không mở nguồn quá sớm:** Dùng Mono.defer(...) có AtomicInteger tăng khi được subscribe, thêm delaySubscription(3s) và kiểm tra counter vẫn bằng 0 trước hạn, bằng 1 sau 3s ảo.

**Bài 3 – Đổi nhịp:** Nguồn đã phát hai sự kiện cách nhau 500ms. Thử delayElements(2s) và delaySequence(2s); viết test quan sát khoảng cách giữa sự kiện ở downstream để chứng minh sự khác nhau.

**Bài 4 – Dừng stream:** Tạo Flux.interval vô hạn và viết StepVerifier.withVirtualTime(...).thenCancel().verify(); giải thích cancellation khác với onComplete và tại sao không nên gọi blockLast.

**Bài 5 – Thiết kế SSE cho client chậm:** Với 1 tick/100ms và client tiêu thụ 1 tick/s, chọn một trong các chính sách: mất tick cũ/lấy latest, buffer hữu hạn có báo tràn, hoặc lưu sự kiện bền và replay. Viết test demand thấp. Không có một operator nào bảo đảm đồng thời không mất dữ liệu, không tăng tài nguyên và latency bằng 0 cho consumer chậm vô hạn.

## 13. Checklist mang vào ứng dụng

- [ ] Đã phân biệt **nguồn phát theo giờ** với **operator hoãn nguồn/tín hiệu**.
- [ ] Đã xác định tick đầu, period, điều kiện kết thúc và nơi sở hữu subscription.
- [ ] Đã chọn Scheduler phù hợp và đóng Scheduler tự tạo theo lifecycle.
- [ ] Đã xác định hành vi khi downstream demand thiếu và khi callback chậm hơn period.
- [ ] Đã kiểm soát timeout, concurrency, memory buffer và retry; không có blocking trong WebFlux event-loop.
- [ ] Có test với virtual time cho onNext/onComplete/onError và cancel.
- [ ] Với SSE đã kiểm tra disconnect, reconnect, replay/buffering và giới hạn tài nguyên.
- [ ] Với job quan trọng đã thiết kế lịch/persistence thay cho interval thuần.

## 14. Đọc thêm

1. Project Reactor – Flux.interval, delayElements, delaySequence, delaySubscription (API 3.8.8): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
2. Project Reactor – Mono.delay, delayElement, delaySubscription: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
3. Reactor Test – StepVerifier.withVirtualTime: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
4. Reactor Reference – Schedulers, backpressure và testing: https://projectreactor.io/docs/core/release/reference/
5. Spring WebFlux – Reactive web và streaming: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Kết quả cần tự giải thích được:** (a) vì sao Mono.delay(1s) tạo 0L, (b) vì sao interval vô hạn dù có tick 0, (c) khi nào delaySubscription thực sự ngăn side effect, (d) khác nhau giữa delayElements và delaySequence, (e) cách StepVerifier kiểm soát vài giờ ảo và (f) vì sao interval có thể lỗi nếu downstream không request.
