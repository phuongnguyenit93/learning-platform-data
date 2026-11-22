# Kiểm tra thứ tự phần tử và dữ liệu bị loại bỏ trong luồng Reactive

Khi kiểm thử `Flux` trong Spring Boot WebFlux, việc biết **đã nhận đủ số lượng phần tử** là chưa đủ. Một pipeline có thể phát cùng ba giá trị nhưng **sai thứ tự**, loại nhầm một event hợp lệ, giữ lại event bị cấm, hoặc không cleanup object đã bị operator bỏ qua. Các lỗi này thường bị che nếu test chỉ dùng `expectNextCount`, chuyển kết quả thành `Set`, hoặc gọi `block()` rồi chỉ so số lượng.

**Project Reactor** cung cấp `reactor-test` và **`StepVerifier`** để kiểm chuỗi tín hiệu `onNext`, `onComplete`, `onError`, cancellation và các trạng thái sau khi chạy. Với những phần tử không xuất hiện ở downstream, điều quan trọng là phân biệt:

- **Discarded**: phần tử được operator xử lý rồi **loại bỏ có chủ đích** trong luồng hợp lệ, ví dụ không thỏa `filter`, bị `skip` hoặc được dọn khỏi queue của operator sau cancellation. Reactor có local discard hooks và `StepVerifier.Assertions.hasDiscarded(...)`.
- **Dropped**: tín hiệu `onNext` không còn được phép xử lý, ví dụ một publisher sai hợp đồng cố phát sau tín hiệu kết thúc; operator có thể chuyển nó qua `Hooks.onNextDropped`. Không dùng `hasDropped` để kiểm các giá trị bị `filter` loại bình thường.
- **Chưa phát/chưa được yêu cầu**: phần tử chưa bao giờ vào operator do backpressure hoặc cancel. **Không có cơ sở** để nói nó đã bị discard hoặc dropped.

Bài này trình bày cách viết assertion cho đúng thứ tự, kiểm discarded data và điều kiện kết thúc; hướng dẫn chọn `expectNext`, `expectNextSequence`, `verifyThenAssertThat`, `doOnDiscard`, `TestPublisher`; có dự án **Java 17 + Spring Boot 3.5** với JUnit Jupiter runnable, cùng các lưu ý về concurrency và WebFlux HTTP boundary.

## 1. Tín hiệu của Flux và ý nghĩa thứ tự

Một Publisher đúng Reactive Streams có thể gửi những tín hiệu sau:

```text
Subscriber                    Publisher
    |                             |
    |<---- onSubscribe(S) --------|
    |---- request(n) ------------>|
    |<---- onNext(A) -------------|
    |<---- onNext(B) -------------|
    |<---- onNext(C) -------------|
    |<---- onComplete() ----------|
    |       hoặc onError(e)       |
```

`onComplete` và `onError` là **terminal signals** thay thế nhau; một Publisher tuân thủ không tiếp tục gửi `onNext` sau terminal. Subscriber cũng có thể hủy `Subscription` bằng `cancel`. Cần kiểm cả các tín hiệu chứ không chỉ danh sách `onNext`.

Ví dụ contract yêu cầu output **A → B → C**. Có ba tình huống khác nhau:

| Output | Phần tử có đủ? | Đúng thứ tự? | Đúng terminal? |
|---|---|---|---|
| A, B, C, complete | Có | Có | Có |
| A, C, B, complete | Có | **Không** | Có |
| A, B, C, error | Có | Có | **Không** |
| A, B, C, D, complete | Không đúng số lượng | Prefix đúng | Có |

Một test chỉ dùng `expectNextCount(3)` không thấy đảo vị trí A,C,B. Một test chỉ kiểm `expectNext(A,B,C)` nhưng quên terminal expectation có thể chưa bắt phần tử D hoặc lỗi phát sinh sau prefix.

## 2. API StepVerifier dành cho thứ tự và terminal signals

### `expectNext` và `expectNextSequence`

Hai cách cùng chứng minh **giá trị lẫn vị trí**:

```java
StepVerifier.create(Flux.just(10, 20, 30))
        .expectNext(10, 20, 30)
        .verifyComplete();

StepVerifier.create(Flux.just(10, 20, 30))
        .expectNextSequence(List.of(10, 20, 30))
        .verifyComplete();
```

Đây là snippet đặt trong test có imports `Flux`, `StepVerifier`, `List`. Nếu nguồn phát `10,30,20`, cả hai test phải FAIL tại thứ tự mong đợi.

### `expectNextCount` không kiểm giá trị

```java
StepVerifier.create(Flux.just(10, 30, 20))
        .expectNextCount(3)
        .verifyComplete();
```

Test này PASS vì chỉ khẳng định có **ba** tín hiệu `onNext` và stream hoàn tất. Nó hợp lý khi thứ tự/giá trị không thuộc yêu cầu; nếu thứ tự là contract thì **không đủ bằng chứng**.

### `assertNext` và `expectNextMatches`

Để kiểm nhiều field của từng event:

```java
StepVerifier.create(events)
        .assertNext(event -> {
            assertEquals("E-1", event.id());
            assertEquals(200, event.amount());
        })
        .expectNextMatches(event -> event.id().equals("E-2"))
        .verifyComplete();
```

Đây là snippet **không độc lập**, biến `events` và type của `event` là dữ liệu của test cụ thể. `assertNext` nhận phần tử ở **vị trí hiện tại** và cho phép assertion JUnit/AssertJ. `expectNextMatches` xác minh predicate trên **một phần tử tiếp theo**; predicate quá lỏng có thể cho qua field sai.

### Không quên `verify`

`StepVerifier.create(...).expectNext(...)` chỉ **khai báo kịch bản**. Cần `verifyComplete()`, `verifyError()`, `expectComplete().verify()`, `thenCancel().verify()` hoặc `verifyThenAssertThat()` để chạy thật. Với publisher có thể không kết thúc, dùng `verify(Duration)` hoặc timeout phù hợp; các shortcut không timeout có thể chờ vô hạn.

## 3. Phân biệt filter, skip, take, discard, drop

| Tình huống | Subscriber thấy gì? | Giá trị không thấy được phân loại ra sao? |
|---|---|---|
| `Flux.range(1, 6).filter(i -> i % 2 == 0)` | 2, 4, 6 | 1,3,5 là **discarded** bởi operator hỗ trợ discard |
| `Flux.just(10,20,30).skip(1)` | 20, 30 | 10 là **discarded** khi `skip` xử lý nó |
| `Flux.range(1, 100).take(2)` | 1, 2 | 3..100 **có thể chưa được phát**; không khẳng định discard |
| Source prefetch vào queue rồi downstream cancel | Prefix đã được emit | Phần tử đang trong queue **có thể** bị discard khi operator cleanup |
| Nguồn lỗi phát `onNext` sau `onComplete` | Giá trị mới không được chấp nhận | Có thể báo **dropped** qua `Hooks.onNextDropped` |
| `Flux.never()` không phát gì | Không có `onNext`, không complete | Không phải tự động discarded/dropped |

**Discard** là khái niệm của đường dữ liệu bình thường được operator hỗ trợ, **drop** qua hook thường chỉ sự cố tín hiệu bất hợp lệ. Đừng suy luận rằng một phần tử không thấy ở subscriber nhất định đã đi qua discard hook. Reactor Javadoc ghi rõ **Discard Support** của các toán tử có hỗ trợ; kiểm mục đó nếu test phụ thuộc chi tiết cleanup.

### Vì sao `take(2)` không nên assert discard 3..100?

`take` có thể yêu cầu vừa đủ hai phần tử rồi cancel upstream, nên nguồn `Flux.range` chưa phát 3..100. Chúng **không được tạo thành `onNext` để bị loại**. Ngược lại, một operator có prefetch/queue và bị cancel giữa chừng có thể đã giữ các phần tử chưa gửi xuống dưới; chúng có thể cần cleanup qua discard hook. Đây là hành vi phụ thuộc operator, kích thước prefetch, timing và version, không phải quy tắc `take` luôn discard tất cả phần còn lại.

## 4. Assertions sau khi chạy: `verifyThenAssertThat()`

Một mẫu đầy đủ cho `filter`:

```java
Flux<Integer> evenNumbers = Flux.range(1, 6)
        .filter(n -> n % 2 == 0);

StepVerifier.create(evenNumbers)
        .expectNext(2, 4, 6)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDiscardedExactly(1, 3, 5)
        .hasNotDroppedElements();
```

Đây là snippet cho phương thức test có imports Reactor. Nó kiểm:

1. **Output:** đúng 2 rồi 4 rồi 6, không đảo.
2. **Terminal:** `onComplete`, không thêm giá trị hoặc error.
3. **Discarded:** hook đã ghi nhận **chính xác** các giá trị 1,3,5.
4. **Dropped:** không có `onNext` bị báo qua dropped hook.

**Lưu ý quan trọng:** `hasDiscardedExactly(1,3,5)` kiểm **tập/multiset giá trị** và không có discard khác, **không ràng buộc thứ tự discard**. Nếu thứ tự của callback cleanup là yêu cầu riêng, phải quan sát nó bằng cách có kiểm soát trong pipeline đồng bộ và có nguồn thứ tự rõ.

Các API liên quan:

| Method | Phép kiểm |
|---|---|
| `hasDiscarded(a,b)` | Đã discard ít nhất các giá trị này |
| `hasDiscardedExactly(a,b)` | Chỉ discard đúng các giá trị yêu cầu, không có discarded value khác; **không kiểm thứ tự** |
| `hasDiscardedElements()` | Có ít nhất một discarded value |
| `hasNotDiscardedElements()` | Không có discarded value ghi nhận qua hook |
| `hasDropped(a)` | Có ít nhất các giá trị bị `onNextDropped` báo |
| `hasDroppedExactly(a)` | Đúng các dropped values, không có giá trị khác |
| `hasNotDroppedElements()` | Không có `onNextDropped` nào ghi nhận |
| `hasDroppedErrors()` | Có lỗi bị báo `onErrorDropped`, **khác** error terminal của stream |

`verifyThenAssertThat()` **vừa verify vừa trả `StepVerifier.Assertions`**. Không gọi `verifyComplete()` rồi mới cố truy cập post-assertions từ builder đã kết thúc; thay bằng `expectComplete().verifyThenAssertThat()`.

## 5. Local discard hook: `doOnDiscard`

Reactor cho phép dọn/quan sát các object được operator hỗ trợ loại bỏ:

```java
List<Integer> discarded = new ArrayList<>();

Flux<Integer> even = Flux.range(1, 6)
        .filter(n -> n % 2 == 0)
        .doOnDiscard(Integer.class, discarded::add);

StepVerifier.create(even).expectNext(2, 4, 6).verifyComplete();
assertEquals(List.of(1, 3, 5), discarded);
```

Đoạn này thuộc test có imports `List`, `ArrayList`, `assertEquals`, `Flux`, `StepVerifier`. **Đặt `doOnDiscard` phía sau filter** để hook có thể hoạt động trên operator **upstream**. Với nguồn và filter đồng bộ như trên, thứ tự callback là deterministic; với `flatMap`/parallel/bất đồng bộ, không mặc định callback chạy theo thứ tự input.

Nếu object mang tài nguyên thực như Netty `ByteBuf`, local hook có thể thực hiện cleanup, nhưng callback **phải idempotent** và an toàn nếu được gọi nhiều lần. Không viết hook cleanup trực tiếp trong một `Stream` có nhiều operator/hook cùng release một object mà không có cơ chế bảo vệ. Không phải mọi operator có discard support, hãy kiểm Javadoc đúng version.

**Không nhầm `doOnDiscard` với `Hooks.onNextDropped`:** cái đầu là local hook cho discard được hỗ trợ, cái sau là global hook để xử lý tín hiệu bị rơi bất thường. Đừng cài global hooks trong test rồi quên reset, vì có thể làm nhiễu những test khác khi chạy song song.

## 6. Ví dụ runnable Java 17 trong Spring Boot module

Giả sử hệ thống nhận event có `id`, `priority` và `state`:

- `approved(source)` chỉ giữ event trạng thái `APPROVED`, **giữ thứ tự tương đối** của event còn lại.
- `approvedSortedByPriority(source)` cố ý `sort` theo priority tăng dần sau khi lọc.
- Event `REJECTED` phải được filter bỏ; test muốn thấy **đúng event bị discard** chứ không chỉ “output có 2 phần tử”.
- Subscription có thể bị `cancel`; test cần xác minh **hủy không phải onComplete**.

Ví dụ chạy trên **Java 17**, Spring Boot **3.5.0**, JUnit Jupiter 5 và Reactor. Ở đây ta **không** dùng `@SpringBootTest` vì chỉ kiểm logic operator, không yêu cầu DI, database hay HTTP; đó là lựa chọn tốt trong dự án Spring WebFlux.

### 6.1. Cây thư mục

```text
reactive-sequence/
├── pom.xml
└── src/
    ├── main/java/com/example/reactive/
    │   └── EventPipeline.java
    └── test/java/com/example/reactive/
        └── EventPipelineTest.java
```

### 6.2. Cấu hình Maven hoàn chỉnh

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-sequence</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Dòng `reactor-test` được khai báo rõ để có `StepVerifier`/`TestPublisher`. Version của `reactor-core` và `reactor-test` được Spring Boot BOM quản lý cho tương thích; không pin một bản Reactor lạ chỉ để sửa lỗi compile. `spring-boot-starter-webflux` là ngữ cảnh ứng dụng reactive, còn các test thuần operator **không khởi động web server**.

### 6.3. File production: EventPipeline

Tạo **`src/main/java/com/example/reactive/EventPipeline.java`**:

```java
package com.example.reactive;

import java.util.Comparator;
import java.util.Objects;

import reactor.core.publisher.Flux;

public final class EventPipeline {

    public enum State {
        APPROVED, REJECTED
    }

    public record Event(String id, int priority, State state) {
        public Event {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(state, "state");
        }
    }

    public Flux<Event> approved(Flux<Event> source) {
        return Objects.requireNonNull(source, "source")
                .filter(e -> e.state() == State.APPROVED);
    }

    public Flux<Event> approvedSortedByPriority(Flux<Event> source) {
        return approved(source)
                .sort(Comparator.comparingInt(Event::priority));
    }
}
```

`record` có `equals` theo các thành phần, nên `StepVerifier.expectNext` so sánh đúng nội dung của event. `approved(...)` chỉ `filter` và **giữ thứ tự nguồn** của event được chọn; `approvedSortedByPriority` chủ động đổi thứ tự khi có dữ liệu. `sort` cần publisher hoàn tất để có đủ dữ liệu sắp xếp; **không áp dụng nguyên xi cho Flux vô hạn** mà muốn phát dần.

### 6.4. File test đầy đủ: 9 phương thức JUnit

Tạo **`src/test/java/com/example/reactive/EventPipelineTest.java`**:

```java
package com.example.reactive;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;

import com.example.reactive.EventPipeline.Event;

import static com.example.reactive.EventPipeline.State.APPROVED;
import static com.example.reactive.EventPipeline.State.REJECTED;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EventPipelineTest {
    private final EventPipeline pipeline = new EventPipeline();

    private final Event a = new Event("A", 3, APPROVED);
    private final Event b = new Event("B", 1, REJECTED);
    private final Event c = new Event("C", 2, APPROVED);
    private final Event d = new Event("D", 4, REJECTED);

    @Test
    void approvedEventsKeepRelativeSourceOrder() {
        StepVerifier.create(pipeline.approved(Flux.just(a, b, c, d)))
                .expectNext(a, c)
                .verifyComplete();
    }

    @Test
    void capturesExactlyWhichEventsWereDiscarded() {
        StepVerifier.create(pipeline.approved(Flux.just(a, b, c, d)))
                .expectNextSequence(List.of(a, c))
                .expectComplete()
                .verifyThenAssertThat()
                .hasDiscardedExactly(b, d)
                .hasNotDroppedElements();
    }

    @Test
    void localHookSeesDiscardOrderForThisSynchronousSource() {
        List<Event> discarded = new ArrayList<>();

        Flux<Event> output = pipeline.approved(Flux.just(a, b, c, d))
                .doOnDiscard(Event.class, discarded::add);

        StepVerifier.create(output)
                .expectNext(a, c)
                .verifyComplete();

        assertEquals(List.of(b, d), discarded);
    }

    @Test
    void explicitSortChangesOrderByPriority() {
        StepVerifier.create(
                        pipeline.approvedSortedByPriority(Flux.just(a, b, c, d)))
                .expectNext(c, a)
                .verifyComplete();
    }

    @Test
    void allRejectedEventsAreDiscardedAndStreamCompletes() {
        StepVerifier.create(pipeline.approved(Flux.just(b, d)))
                .expectComplete()
                .verifyThenAssertThat()
                .hasDiscardedExactly(b, d);
    }

    @Test
    void aNormalSourceWithoutFilteringHasNoDiscardedItems() {
        StepVerifier.create(Flux.just(a, c))
                .expectNext(a, c)
                .expectComplete()
                .verifyThenAssertThat()
                .hasNotDiscardedElements()
                .hasNotDroppedElements();
    }

    @Test
    void requestsOneByOneStillPreserveOrdering() {
        StepVerifier.create(
                        Flux.just(a, c),
                        StepVerifierOptions.create().initialRequest(0))
                .thenRequest(1)
                .expectNext(a)
                .thenRequest(1)
                .expectNext(c)
                .verifyComplete();
    }

    @Test
    void cancellingSourceIsDifferentFromReceivingComplete() {
        TestPublisher<Event> source = TestPublisher.create();

        StepVerifier.create(source.flux())
                .then(() -> source.next(a))
                .expectNext(a)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        source.assertWasCancelled();
    }

    @Test
    void customAssertionsCheckFieldsInEachPosition() {
        StepVerifier.create(pipeline.approved(Flux.just(a, b, c)))
                .assertNext(event -> {
                    assertEquals("A", event.id());
                    assertEquals(3, event.priority());
                })
                .assertNext(event -> {
                    assertEquals("C", event.id());
                    assertTrue(event.priority() > 0);
                })
                .verifyComplete();
    }
}
```

Đây là hai Java source file đầy đủ cùng `pom.xml`; chúng không cần Spring context, không đòi network hay database. Với dữ liệu fixture cố định, **9 test dự kiến PASS, 0 FAIL**. Bài cancellation có timeout 2 giây để không treo khi publisher không kết thúc; riêng các bài dùng `Flux.just` và `Flux.range` đều hữu hạn/đồng bộ.

### 6.5. Những gì từng test chứng minh

| Test | Kết quả và ranh giới |
|---|---|
| `approvedEventsKeepRelativeSourceOrder` | B,D bị lọc; output **A rồi C**, không đảo |
| `capturesExactlyWhichEventsWereDiscarded` | Verifier hook thấy **B,D**, không có unexpected dropped `onNext` |
| `localHookSeesDiscardOrderForThisSynchronousSource` | Với luồng đồng bộ, hook quan sát **B trước D** |
| `explicitSortChangesOrderByPriority` | Sau sorting priority, **C trước A**, khác thứ tự input |
| `allRejectedEventsAreDiscardedAndStreamCompletes` | Output rỗng nhưng **có completion** và đủ discarded events |
| `aNormalSourceWithoutFilteringHasNoDiscardedItems` | Nguồn bình thường không có discard/drop |
| `requestsOneByOneStillPreserveOrdering` | Demand 1 mỗi lần cho kết quả theo thứ tự A,C |
| `cancellingSourceIsDifferentFromReceivingComplete` | Subscriber cancel và `TestPublisher` ghi nhận cancellation |
| `customAssertionsCheckFieldsInEachPosition` | Assert `id`/`priority` từng vị trí sau filtering |

`hasDiscardedExactly(b,d)` **không** kiểm thứ tự B,D, nhưng `doOnDiscard(...)` kết hợp `List` có thể quan sát thứ tự callback trong chính nguồn tuần tự này. Với nguồn parallel, không nên lấy logic về thứ tự `doOnDiscard` từ test đồng bộ rồi áp bừa.

### 6.6. Cách chạy

Tại thư mục Maven project có `pom.xml`:

```bash
mvn test
```

Hoặc chạy đúng class:

```bash
mvn -Dtest=EventPipelineTest test
```

Nếu dự án có Maven Wrapper thì thay bằng `./mvnw test` hoặc `./mvnw -Dtest=EventPipelineTest test`; trên Windows dùng `mvnw.cmd` khi có wrapper. Không chạy class JUnit như một chương trình `java EventPipelineTest` vì không có `main` và cần runner/dependency Reactor. Với duy nhất class ở ví dụ, kết quả dự kiến **Tests run: 9, Failures: 0, Errors: 0**; cấu trúc stdout của Surefire tùy version, không có stdout nghiệp vụ cố định.

## 7. Các operator có hoặc không đảm bảo output ordering

| Operator | Cách đọc ordering |
|---|---|
| `Flux.just`, `Flux.range` | Phát theo thứ tự nguồn trong đường xử lý tuần tự thông thường |
| `map`, `filter` đồng bộ | Không tự đảo thứ tự; `filter` chỉ bỏ phần tử không khớp |
| `sort(comparator)` | Cố ý reorder sau khi nguồn hoàn tất |
| `flatMap` với các inner async | Có thể interleave kết quả các inner, **không bảo đảm output theo nguồn** |
| `concatMap` | Thực thi/nối từng inner theo thứ tự đầu vào |
| `flatMapSequential` | Có thể subscribe inner sớm, nhưng emit kết quả theo thứ tự inner từ nguồn |
| `merge` nhiều nguồn | Trộn theo thời điểm phát, không có total order mặc định |
| `zip` | Ghép theo vị trí giữa các source, không tự sort theo timestamp |
| `skip`, `distinct` | Có thể loại dữ liệu, thường giữ thứ tự tương đối của dữ liệu qua được |
| `take(n)` | Phát một prefix rồi kết thúc/cancel, không chứng minh phần còn lại bị discard |
| `parallel().runOn(...).sequential()` | Có thể interleave theo rails; không tự coi là duy trì total order gốc |

**Tránh tạo test flaky bằng thời gian.** Ví dụ snippet minh họa:

```java
Flux<Integer> async = Flux.just(1, 2, 3)
        .flatMap(i -> Mono.just(i)
                .delayElement(Duration.ofMillis((4 - i) * 20L)));
```

Đoạn này **không độc lập**; cần `Mono`/`Flux` imports và test method. Do inner hoàn tất ở thời điểm khác nhau, output thường có thể ra `3,2,1`, nhưng không nên viết expected tuyệt đối dựa vào scheduler/CPU thực rồi kết luận đó là contract. Nếu nghiệp vụ cần output 1,2,3, hãy chọn `concatMap` hoặc `flatMapSequential` theo mục tiêu concurrency và kiểm bằng nguồn deterministic/virtual time phù hợp.

## 8. Backpressure và cancellation không đồng nghĩa discard

`request(n)` là demand từ subscriber. StepVerifier có thể đặt ban đầu bằng 0:

```java
StepVerifier.create(
                Flux.just("A", "B", "C"),
                StepVerifierOptions.create().initialRequest(0))
        .thenRequest(1)
        .expectNext("A")
        .thenRequest(2)
        .expectNext("B", "C")
        .verifyComplete();
```

Test này chứng minh demand và thứ tự, **không** thể suy luận “đã có giá trị bị discard” chỉ vì source ban đầu chưa emit gì khi chưa được request.

Khi cancel:

1. Phần tử **chưa được nguồn tạo hoặc chưa được yêu cầu**: không phải discarded.
2. Phần tử **đã được filter/skip xử lý và loại**: có thể báo discarded qua hook.
3. Phần tử **đã prefetch vào queue và bị dọn khi cancel**: có thể bị discard nếu operator có discard support.
4. Publisher lỗi **tiếp tục phát sau terminal**: có thể bị dropped theo hook, không thuộc discard bình thường.

Nếu test yêu cầu kiểm cancellation, `TestPublisher.assertWasCancelled()` như file thực hành là bằng chứng tốt hơn `hasDiscarded(3..100)` đoán mò. Trong ứng dụng có đối tượng tài nguyên, cần kiểm cleanup đúng API/ownership và idempotence, không chỉ kiểm lượng giá trị biến mất.

## 9. Kiểm dữ liệu dropped đúng mục đích

`StepVerifier.Assertions.hasDropped(...)` kiểm `onNext` được chuyển tới **`Hooks.onNextDropped`**. Nó dành cho tình huống cố tình thử một publisher/operator có hành vi bất thường, ví dụ phát sau termination. `hasDroppedErrors(...)` liên quan các error bị đưa tới `onErrorDropped`, **khác** stream phát `onError` bình thường.

Khung tư duy (không phải test độc lập vì cần tạo `malformedPublisher` chủ động vi phạm giao thức):

```java
StepVerifier.create(malformedPublisher)
        .expectNext("ok")
        .expectComplete()
        .verifyThenAssertThat()
        .hasDropped("late");
```

Đừng chép snippet trên và mặc định PASS: nếu nguồn chặn giá trị `"late"` ngay trong publisher hoặc giá trị ấy không tới dropped hook, `hasDropped` phải FAIL. Có thể dùng `TestPublisher.createNoncompliant` với violation phù hợp để kiểm hành vi sai hợp đồng; test phải xác nhận cơ chế hook thực sự nhận tín hiệu. **Đối với bài kiểm `filter`**, hãy dùng `hasDiscardedExactly` thay vì cố tạo một dropped event giả.

Không bật `Hooks.onNextDropped` global tùy tiện trong suite chạy song song. Nếu buộc phải cấu hình hook toàn cục để kiểm custom source, cô lập test và reset hook trong `finally`; đừng để state Reactor global làm ảnh hưởng test class khác.

## 10. Áp dụng vào Spring WebFlux: StepVerifier khác WebTestClient

Một controller Spring WebFlux có thể trả `Flux<EventDto>`, nhưng một HTTP test và một operator test chứng minh những điều khác nhau:

| Điều cần chứng minh | Công cụ |
|---|---|
| Service pipeline phát đúng event, đúng order và complete/error | `StepVerifier` trực tiếp trên `Flux` |
| Operator loại đúng phần tử và cleanup hook nhận giá trị đó | `StepVerifier.verifyThenAssertThat`/`doOnDiscard` |
| URL/route, status, headers, JSON serialization | `WebTestClient` với controller/router context tương ứng |
| HTTP socket, codec và embedded server thật | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` |
| Reactor publisher timing/backoff | `StepVerifier.withVirtualTime` khi dùng scheduler hỗ trợ virtual time |
| SSE/Flux streaming, chỉ kiểm prefix và hủy | `WebTestClient.returnResult(...).getResponseBody()` + StepVerifier `thenCancel` |

Giả sử `GET /api/events` trả các event đã lọc. `WebTestClient` có thể kiểm HTTP 200/JSON và thứ tự các phần tử **đã được gửi ra**, nhưng **không tự nhìn thấy các event bị filter loại trong service**. Nếu mục tiêu là kiểm “event REJECTED nào bị loại”, nên test chính pipeline với StepVerifier/hook, không suy luận từ việc JSON chỉ chứa event APPROVED.

Với Server-Sent Events hoặc Flux vô hạn, đừng gọi `expectBodyList` rồi chờ đến completion không bao giờ xảy ra. Dùng stream response và StepVerifier kiểm số lượng hữu hạn rồi `thenCancel`, với timeout. Test không nên `block()` trên Reactor Netty event-loop hoặc dùng `Thread.sleep` để thay cho kiểm tín hiệu/timing có chủ đích.

## 11. Lỗi thường gặp và điều chỉnh

| Sai lầm | Điều bị bỏ sót | Cách sửa |
|---|---|---|
| Dùng `expectNextCount(3)` khi yêu cầu thứ tự | Đảo A,C,B vẫn pass | `expectNext(A,B,C)` |
| Gom stream vào `Set` hoặc `containsExactlyInAnyOrder` | Che lỗi ordering | Kiểm `expectNextSequence` hoặc list giữ thứ tự |
| Bỏ `expectComplete`/`expectError` | Không kiểm tín hiệu kết thúc | Verify đúng terminal signal |
| Quên `verify` | Không có subscription/kiểm thật | `verifyComplete`, `verify(Duration)`, `verifyThenAssertThat` |
| Gán `filter` vào nhóm dropped | Lẫn discard bình thường và onNextDropped | `hasDiscardedExactly` |
| Yêu cầu `take(2)` discard toàn bộ phần dư | Phần dư có thể chưa phát | Kiểm cancel và demand |
| Đặt `doOnDiscard` trước `filter` | Hook không thấy operator downstream | Đặt hook sau operator cần cleanup |
| Dùng hook cleanup không idempotent | Có thể giải phóng tài nguyên sai hoặc trùng | Đảm bảo idempotent và ownership rõ |
| Dựa vào thứ tự discard khi dùng `flatMap` song song | Callback có thể khác thứ tự | Kiểm tập phần tử, chỉ assert thứ tự nếu contract bảo đảm |
| Dùng `Thread.sleep` để “ổn định” async | Dễ flaky trên CI | Virtual time/scheduler có kiểm soát |
| Dùng `verifyComplete` cho Flux vô hạn | Test có thể treo | `thenCancel` và timeout |
| Tưởng StepVerifier đã kiểm HTTP status | Chỉ kiểm Publisher, không kiểm WebFlux routing | Bổ sung WebTestClient |
| Để global `Hooks` qua nhiều test | Cross-test interference | Cô lập và reset hook |
| Không có `reactor-test` trong test classpath | Compile lỗi `reactor.test.StepVerifier` | Thêm dependency test do BOM quản lý |

## 12. Checklist trước khi hoàn thành test

- [ ] Tôi xác định contract **cần đúng order** hay chỉ đúng số lượng/tập giá trị.
- [ ] Nếu cần order, tôi dùng `expectNext`/`expectNextSequence`, không chỉ `expectNextCount`.
- [ ] Mỗi test kiểm đúng terminal signal: complete, error hoặc cancel.
- [ ] Verifier có gọi `verify`/shortcut để thực thi.
- [ ] Tôi phân biệt **discard**, **drop** và **chưa được phát**.
- [ ] Với filter/skip hỗ trợ discard, tôi kiểm đúng discarded values.
- [ ] `hasDiscardedExactly` được hiểu là **đúng các giá trị**, không khẳng định thứ tự.
- [ ] Nếu cần kiểm thứ tự cleanup callback, nguồn/operator được thiết kế đồng bộ, deterministic.
- [ ] Tôi không mặc định dữ liệu sau `take` đã bị discard.
- [ ] Với `flatMap`/merge/parallel, tôi biết rõ thứ tự nào được bảo đảm.
- [ ] Với backpressure/cancel, tôi kiểm subscription state chứ không đoán discarded values.
- [ ] Cleanup hook an toàn, idempotent; không gây ảnh hưởng global hooks.
- [ ] Test có timeout nếu publisher có thể không kết thúc.
- [ ] Tôi dùng StepVerifier cho **pipeline**, WebTestClient cho **HTTP contract**.
- [ ] Dependency Reactor Core/reactor-test nhất quán với Spring Boot version của module.

**Kết luận:** Test luồng Reactive phải kiểm **đúng phần tử, đúng thứ tự, đúng tín hiệu kết thúc và đúng loại dữ liệu bị loại bỏ**. `expectNext`/ `expectNextSequence` kiểm thứ tự; `hasDiscardedExactly` và `doOnDiscard` kiểm dữ liệu filter/skip bỏ; `hasDropped` dành cho tín hiệu `onNextDropped` bất thường. Không đồng nhất “không xuất hiện ở downstream” với “đã bị discard”.

### Tài liệu chính thức

- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html)
- [Reactor Test Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Reactor Test Javadoc — Assertions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html)
- [Reactor Core Javadoc — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
