# `concat` và `merge`: ghép các nguồn Reactor có quan hệ thời gian khác nhau

## 1. Mục tiêu và vấn đề cần giải quyết

Trong ứng dụng Spring WebFlux, dữ liệu có thể đến từ nhiều nguồn: hai HTTP API trả lời với tốc độ khác nhau, các truy vấn truy cập dữ liệu, luồng sự kiện liên tục hoặc các tác vụ xử lý theo giai đoạn. Khi ghép các nguồn đó, câu hỏi quan trọng là **nguồn nào được subscribe vào lúc nào, phần tử được phát ra theo thứ tự nào, và điều gì xảy ra khi một nguồn hoàn tất, chậm, lỗi hoặc không bao giờ kết thúc?**

Project Reactor cung cấp hai cách ghép cơ bản:

- **`Flux.concat(a, b)`**: subscribe nguồn `a`, chuyển các phần tử của `a` tới downstream, **đợi `a` hoàn tất thành công** rồi mới subscribe `b`. Kết quả giữ các phần tử của từng nguồn thành từng nhóm theo thứ tự nguồn.
- **`Flux.merge(a, b)`**: subscribe các nguồn **sớm/eager** (trong giới hạn concurrency cho từng overload), chuyển tiếp phần tử khi mỗi nguồn phát ra. Phần tử giữa các nguồn có thể **xen kẽ** theo thời điểm tín hiệu được quan sát; không nhất thiết giống thứ tự nguồn trong lời gọi `merge`.

Bài học này phân tích `concat` và `merge` khi nguồn **nhanh/chậm, xuất hiện trước/sau, hữu hạn/vô hạn, cold/hot hoặc có lỗi**, kèm chương trình kiểm thử Java 17+ bằng **virtual time**. Mục tiêu là chọn đúng ngữ nghĩa xử lý, không dựa vào giả định “merge luôn nhanh hơn” hay “concat luôn chậm”.

## 2. Ôn lại vòng đời và khái niệm thời gian

Một `Publisher<T>` phát dữ liệu theo hợp đồng Reactive Streams. Khi subscriber đăng ký, nguồn có thể phát:

```text
onSubscribe(subscription)
    -> onNext(value1)
    -> onNext(value2)
    -> ...
    -> onComplete()

hoặc:
onSubscribe(subscription)
    -> [có thể có onNext]
    -> onError(exception)
```

`onComplete` và `onError` là **hai terminal signal loại trừ nhau**. Sau tín hiệu terminal, không có `onNext` mới hợp lệ trong cùng một subscription. Subscriber có thể gọi `cancel()` để hủy; cancellation khác với việc nguồn gửi `onComplete`.

Ba mốc thời gian cần phân biệt:

1. **Thời điểm tạo publisher**: mã Java gọi `Flux.just(...)`, `WebClient...bodyToFlux(...)`, v.v. tạo biểu thức mô tả pipeline; nguồn *cold* thông thường chưa thực hiện tác vụ cho đến khi có subscription.
2. **Thời điểm subscribe**: upstream được đăng ký và có thể bắt đầu thao tác I/O hoặc phát dữ liệu. Đây là mốc `concat` và `merge` khác nhau rõ nhất.
3. **Thời điểm nhận tín hiệu**: downstream quan sát `onNext`, `onError` hoặc `onComplete`; có thể khác với thời điểm sự kiện thực tế được sinh ra ở hệ thống bên ngoài.

**Quan hệ thời gian khác nhau** có thể là một nguồn bắt đầu trễ, nguồn A phát mỗi 200 ms còn B phát mỗi 50 ms, hoặc nguồn B đã nóng (*hot*) và phát sự kiện trước khi ta đăng ký. `concat` và `merge` xử lý các tình huống đó theo hai hợp đồng khác nhau.

## 3. `concat`: xử lý lần lượt, đợi hoàn thành rồi mới chuyển nguồn

Đường đi cơ bản khi hai nguồn đều hữu hạn:

```text
Nguồn A:       A1 ---- A2 ---- COMPLETE
                         |
Nguồn B:                  |        B1 -- B2 -- COMPLETE
                          |        ^
Subscribe B:              +--------+ (chỉ sau COMPLETE của A)

concat:        A1 ---- A2 --------- B1 -- B2 -- COMPLETE
```

Với các nguồn cold, khi downstream subscribe `Flux.concat(A, B)`:

1. Reactor subscribe A trước.
2. Khi A phát `onNext`, downstream nhận phần tử của A theo thứ tự nguồn phát.
3. Nếu A hoàn tất rỗng (`Flux.empty()`), concat có thể chuyển sang B ngay.
4. Nếu A phát `onComplete`, Reactor subscribe B; B bắt đầu tạo phần tử theo vòng đời của chính B.
5. Nếu A phát `onError`, concat mặc định kết thúc lỗi và **không** tiếp tục B. Nếu A không bao giờ hoàn tất, B không được subscribe.

Ví dụ đơn giản không có tác vụ bất đồng bộ:

```java
Flux<String> a = Flux.just("A1", "A2");
Flux<String> b = Flux.just("B1", "B2");

Flux<String> combined = Flux.concat(a, b);
```

Subscriber bình thường sẽ thấy thứ tự `A1`, `A2`, `B1`, `B2`, `onComplete`. Đây là đoạn mã minh họa trong ứng dụng đã có dependency Reactor và import `reactor.core.publisher.Flux`, chưa phải file Java độc lập.

Các cách viết thường gặp:

```java
Flux<String> usingConcat = Flux.concat(a, b);
Flux<String> usingConcatWith = a.concatWith(b);
```

Hai biểu thức có cùng ý nghĩa cho hai nguồn này. Với các nguồn định nghĩa dạng `Publisher<Publisher<T>>`, Reactor cũng có overload `Flux.concat(publishers)` để ghép các publisher con tuần tự.

**Thứ tự của concat là thứ tự *nguồn*, không phải sắp xếp timestamp của mọi bản ghi.** Nếu A chứa sự kiện timestamp 10:05 rồi B chứa timestamp 10:02, concat vẫn đưa dữ liệu A ra trước B. Muốn hợp nhất theo *event time*, phải có thiết kế xử lý thời gian, watermark/buffer/sort riêng, không thể coi `concat` là thuật toán sắp xếp.

## 4. `merge`: đăng ký các nguồn sớm và xen kẽ khi tín hiệu đến

`Flux.merge(A, B)` thường đăng ký cả A và B khi downstream subscribe (đối với hai nguồn hữu hạn này). Hai nguồn có thể cùng hoạt động. Downstream nhận phần tử tùy tốc độ phát:

```text
Thời gian (ms):    0       50      100      200              400
Nguồn A (200 ms):                          A1               A2
Nguồn B (50 ms):           B1      B2
merge output:              B1      B2       A1               A2
```

Khác concat, **merge không đợi A hoàn tất để B bắt đầu**. Với nguồn B nhanh và A chậm, B có thể phát trước mặc dù A được truyền vào hàm ở vị trí đầu tiên.

```java
Flux<String> merged = Flux.merge(a, b);
Flux<String> alsoMerged = a.mergeWith(b);
```

Với `a`, `b` chỉ là `Flux.just` đồng bộ, output có thể nhìn giống concat do nguồn đầu phát toàn bộ ngay trong một call stack. Để thấy giao thoa thực sự, cần các nguồn có chờ bất đồng bộ hoặc phát trên những scheduler phù hợp. **`merge` không tự tạo thread riêng cho từng nguồn**; sự xen kẽ phụ thuộc cách nguồn phát tín hiệu và scheduler/runtime của chúng.

Một số ràng buộc:

- `merge` không bảo đảm **thứ tự giữa các nguồn**; khi hai tín hiệu đến gần như cùng lúc, thứ tự quan sát có thể thay đổi theo scheduling.
- Với publisher tuân thủ Reactive Streams, thứ tự `onNext` *bên trong từng nguồn* vẫn được bảo toàn; merge không đảo vị trí A1/A2 trong cùng luồng A.
- Kết quả merge chỉ `onComplete` khi **mọi nguồn liên quan đã hoàn tất thành công**.
- Lỗi từ bất kỳ nguồn nào mặc định có thể làm merge kết thúc lỗi và hủy nguồn khác; không được giả định những phần tử chưa kịp phát vẫn sẽ đến.
- Merge được thiết kế hiệu quả cho nguồn bất đồng bộ hoặc nguồn hữu hạn; nếu một nguồn vô hạn phát đồng bộ liên tục mà không nhường quyền chạy, nguồn khác có thể bị bỏ đói khi merge cố gắng tiêu thụ nó. Cần bố trí nguồn/scheduler phù hợp.

Không dùng `merge` nếu contract API yêu cầu “đọc hết trang 1 rồi mới đọc trang 2” hoặc “bước B chỉ bắt đầu sau khi bước A thành công”. Những yêu cầu phụ thuộc thứ tự đó hợp hơn với `concat` hoặc chuỗi operator tuần tự.

## 5. Ví dụ thời gian: A chậm 200 ms, B nhanh 50 ms

Giả sử hai nguồn **cold, hữu hạn**, mỗi nguồn phát hai phần tử và áp độ trễ cho *từng phần tử*:

```java
Flux<String> slowA() {
    return Flux.just("A1", "A2")
            .delayElements(Duration.ofMillis(200));
}

Flux<String> fastB() {
    return Flux.just("B1", "B2")
            .delayElements(Duration.ofMillis(50));
}
```

Đây là hai phương thức minh họa nằm trong class Java có import `java.time.Duration` và `reactor.core.publisher.Flux`. `delayElements` dùng cơ chế lập lịch Reactor để trì hoãn tín hiệu; nó **không phải `Thread.sleep` giữ event-loop thread**.

Nếu downstream bắt đầu subscribe ở thời điểm tương đối `t=0`, nguồn A/B và pipeline đều không có thêm tải hệ thống:

| Thời gian tương đối | `Flux.concat(slowA(), fastB())` | `Flux.merge(slowA(), fastB())` |
|---|---|---|
| `t = 0` | Subscribe A; B chưa subscribe | Subscribe A và B |
| `t ≈ 50 ms` | Chưa có phần tử | B1 |
| `t ≈ 100 ms` | Chưa có phần tử | B2, B hoàn tất |
| `t ≈ 200 ms` | A1 | A1 |
| `t ≈ 400 ms` | A2, A hoàn tất; **lúc này mới subscribe B** | A2, A hoàn tất; merge hoàn tất |
| `t ≈ 450 ms` | B1 | Đã hoàn tất |
| `t ≈ 500 ms` | B2, concat hoàn tất | Đã hoàn tất |

Bảng trên là **mô hình logic theo scheduler lý tưởng**. Trên máy thật, các mốc ms có jitter và hai sự kiện sát nhau có thể đổi thứ tự. Khi cần kiểm tra thứ tự một cách tái lập, sử dụng **virtual time** như mục 7.

Các hệ quả quan trọng:

1. Concat hoàn tất xấp xỉ sau **tổng** thời gian của các nguồn trong ví dụ: 400 + 100 = 500 ms.
2. Merge hoàn tất xấp xỉ sau **thời gian nguồn chậm nhất**: max(400, 100) = 400 ms, nếu tài nguyên cho phép các nguồn chạy đồng thời.
3. Những con số này chỉ phản ánh **hai nguồn độc lập, cold và không bị giới hạn tài nguyên**. Concurrency có thể làm tăng tải, giảm hiệu quả vì tranh chấp connection pool, hoặc dẫn đến quá tải upstream.
4. Sự khác biệt lớn nhất không chỉ là tốc độ hoàn tất: concat tạo **ranh giới thứ tự**, merge tạo **kênh kết quả hợp nhất theo tiến độ**.

## 6. Xác định thứ tự nào cần giữ

| Yêu cầu nghiệp vụ | Cách xử lý thích hợp | Lý do |
|---|---|---|
| Đọc từng trang dữ liệu liên tiếp, trang sau phụ thuộc trang trước | `concat`/`concatMap` hoặc chain tuần tự | Nguồn sau chỉ bắt đầu khi trước hoàn tất |
| Ghép nhiều danh sách đã biết thứ tự theo nhóm | `concat` | Không xen kẽ các nhóm |
| Gom kết quả từ nhiều API độc lập ngay khi API nào trả lời xong | `merge` | Bắt đầu sớm, phát theo tiến độ |
| Hợp nhất thông báo từ nhiều nguồn sự kiện độc lập | `merge` | Không bị ép đợi một nguồn hoàn tất |
| Cho nhiều nguồn chạy sớm nhưng vẫn xuất hết A trước B | `mergeSequential` | Subscribe sớm nhưng đệm kết quả nguồn đến sau để giữ nhóm |
| Cần ghép *cặp* một phần tử từ A với một phần tử từ B | `zip` | Phép ghép theo cặp, khác nối/xen kẽ |
| Cần phần tử có timestamp toàn cục tăng dần | Xây dựng xử lý event-time riêng | `merge` không tự sắp xếp toàn bộ thời gian |

**Chọn dựa trên hợp đồng dữ liệu**. Một API đọc log theo thứ tự file có thể cần concat; dashboard hiển thị sự kiện mới từ nhiều service có thể cần merge. Nếu yêu cầu thứ tự liên quan tính đúng đắn giao dịch, đừng thay concat bằng merge chỉ để giảm thời gian chờ.

## 7. Ví dụ Java 17+ chạy được: xác minh với `StepVerifier` và virtual time

Chương trình kiểm thử dưới đây chứng minh thứ tự của ba cách ghép trên **cùng hai nguồn có tốc độ khác nhau** mà không phải chờ thời gian thực. Sử dụng Maven, Java 17+ và Project Reactor Core. Phần `StepVerifier` nằm trong `reactor-test`, `JUnit Jupiter` thực thi kiểm thử.

Cấu trúc thư mục:

```text
reactor-combination-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── edu/
                └── demo/
                    └── ConcatMergeTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-combination-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/test/java/edu/demo/ConcatMergeTest.java`:

```java
package edu.demo;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ConcatMergeTest {

    private static Flux<String> slowA() {
        return Flux.just("A1", "A2")
                .delayElements(Duration.ofMillis(200));
    }

    private static Flux<String> fastB() {
        return Flux.just("B1", "B2")
                .delayElements(Duration.ofMillis(50));
    }

    @Test
    void concatWaitsForAThenStartsB() {
        StepVerifier.withVirtualTime(
                    () -> Flux.concat(slowA(), fastB()))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(600))
                .expectNext("A1", "A2", "B1", "B2")
                .verifyComplete();
    }

    @Test
    void mergeInterleavesByObservedArrival() {
        StepVerifier.withVirtualTime(
                    () -> Flux.merge(slowA(), fastB()))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(600))
                .expectNext("B1", "B2", "A1", "A2")
                .verifyComplete();
    }

    @Test
    void mergeSequentialStartsEarlyButKeepsSourceOrder() {
        StepVerifier.withVirtualTime(
                    () -> Flux.mergeSequential(slowA(), fastB()))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(600))
                .expectNext("A1", "A2", "B1", "B2")
                .verifyComplete();
    }
}
```

Chạy tại thư mục dự án:

```bash
mvn test
```

Khi dependency được tải và mã chạy thành công, **cả 3 bài kiểm thử đều PASS** (`Tests run: 3, Failures: 0, Errors: 0, Skipped: 0` trong phần tổng kết Surefire; các dòng build khác tùy môi trường). Các assertion trong code là kết quả chính xác của bài kiểm thử:

```text
concat:          A1, A2, B1, B2 -> complete
merge:           B1, B2, A1, A2 -> complete
mergeSequential: A1, A2, B1, B2 -> complete
```

Giải thích tại sao ví dụ ổn định:

- `StepVerifier.withVirtualTime(...)` kích hoạt scheduler ảo và dùng `thenAwait(...)` cho đồng hồ tiến lên mà không chờ khoảng thời gian thực.
- **Tạo pipeline trong lambda/supplier** truyền vào `withVirtualTime`. Không tạo trước một publisher có toán tử thời gian rồi chuyển vào lambda vì có thể nó đã bắt giữ scheduler thật.
- Không có hai phần tử của hai nguồn được kỳ vọng ở cùng mốc thời gian (B1=50, B2=100, A1=200, A2=400), nên bài kiểm thử merge không dựa vào tie-break scheduling tùy ý.
- Đối với concat, B chỉ được subscribe sau khi A hoàn thành khoảng 400 ms, nên B1 và B2 xuất hiện tương ứng khoảng 450/500 ms.
- Đối với mergeSequential, B có thể hoàn tất sớm và bị buffer, nhưng downstream chỉ thấy B sau khi xuất hết A.

**Giới hạn của ví dụ:** Delay là dữ liệu mô phỏng, không phải benchmark CPU, WebFlux HTTP hay latency của một hệ thống thực. Thứ tự kiểm thử được bảo đảm bởi logic scheduler ảo, không có nghĩa các cuộc gọi I/O độc lập trong môi trường thật sẽ luôn trả theo cùng thứ tự.

## 8. `mergeSequential`: có tiến độ đồng thời nhưng giữ nhóm nguồn

Có tình huống cần bắt đầu các lời gọi HTTP độc lập cùng lúc nhưng trả response dưới dạng “toàn bộ kết quả A, rồi toàn bộ kết quả B”. Reactor có `Flux.mergeSequential(A, B)`:

```java
Flux<String> ordered = Flux.mergeSequential(
        slowA(),
        fastB()
);
```

- **Giống merge:** subscribe các nguồn con sớm, trong giới hạn concurrency; B có thể hoạt động trong khi A chưa xong.
- **Giống concat về output:** downstream vẫn nhận A1, A2, rồi B1, B2.
- **Khác concat về tài nguyên:** nếu B nhanh và A chậm, phần tử B có thể phải **đệm chờ**. Khi nguồn sau phát nhiều dữ liệu, buffer có thể lớn; cần giới hạn concurrency/prefetch, xem nhu cầu backpressure, timeout và dung lượng bộ nhớ.

Đây là sự đánh đổi giữa **giảm thời gian chờ của nguồn sau** và **nhu cầu bộ đệm để giữ thứ tự**. `mergeSequential` không phải một kiểu `sort`: nó giữ *thứ tự nhóm nguồn*, không sắp xếp timestamp của phần tử ở nhiều nguồn.

Các toán tử tương ứng khi nguồn được tạo từ từng phần tử upstream:

```java
Flux<String> ids = Flux.just("A", "B", "C");

// Gọi fetch(id) lần lượt; mỗi publisher trước phải hoàn tất.
Flux<String> sequential = ids.concatMap(id -> fetch(id));

// Có thể subscribe các publisher tạo bởi fetch(id) sớm, xen kẽ kết quả.
Flux<String> interleaved = ids.flatMap(id -> fetch(id));

// Có thể chạy nhiều fetch nhưng xuất theo thứ tự A, B, C.
Flux<String> orderedConcurrent =
        ids.flatMapSequential(id -> fetch(id));
```

Đây là **snippet minh họa**: `fetch(String id)` phải là một phương thức đã được định nghĩa trả `Publisher<String>`/`Mono<String>`/`Flux<String>`; không phải chương trình độc lập. Với nguồn vô hạn hoặc tốn tài nguyên, hãy chọn overload có giới hạn `concurrency` và `prefetch`, đồng thời đo dung lượng queue.

## 9. Cold và hot source: thời gian đăng ký có thể làm mất dữ liệu

Sự khác nhau giữa concat và merge không chỉ là “in ra trước/sau”; nó còn quyết định **khi nào nguồn bắt đầu được theo dõi**.

### Cold publisher

Một nguồn *cold* thường bắt đầu công việc mới cho mỗi subscription. Ví dụ một `Flux.just(...)`, `Flux.range(...)` hoặc một pipeline mạng reactive cold có thể tạo một lần thực thi riêng cho từng subscriber. Trong bài kiểm thử mục 7, A và B là cold.

- Với concat, B **chưa được subscribe** cho đến khi A hoàn tất. Vì vậy độ trễ nội tại của B chỉ bắt đầu tính sau A.
- Với merge, A và B được subscribe sớm và có thể bắt đầu chờ I/O song song.

`Flux.interval(...)` cũng thường là một **nguồn cold theo mỗi subscription**: mỗi subscriber có nhịp thời gian riêng. Không nên gọi tất cả các luồng có timer là hot.

### Hot publisher

Nguồn *hot* có thể phát dữ liệu độc lập với việc một subscriber cụ thể có đến hay không: ví dụ một event bus, thiết bị đang phát tín hiệu, hoặc `Sinks.Many` đã được kích hoạt. Hành vi giữ lịch sử phụ thuộc sink/cơ chế replay.

Giả sử `hotB` phát B1 ở `t=50 ms`, B2 ở `t=100 ms`, nhưng A chỉ hoàn tất ở `t=400 ms`:

```text
hotB:          B1(t=50)  B2(t=100) -------------------->
A:            -------------------------- complete(t=400)
concat(A,B):   subscribe A                 subscribe hotB(t=400)
```

Trong một hot source **không replay**, concat subscribe B quá muộn và **có thể bỏ lỡ B1/B2**. Merge subscribe B sớm hơn nên có cơ hội nhận các sự kiện đó. Nhưng merge cũng không thể lấy lại sự kiện đã phát trước khi chính nó subscribe.

Nếu nghiệp vụ cần không mất sự kiện, hãy quyết định rõ **replay, lưu trữ lịch sử, checkpoint/cursor, hoặc message broker** thay vì mặc định bất cứ operator ghép luồng nào tự lưu dữ liệu.

## 10. Khi nguồn rỗng, lỗi hoặc không bao giờ hoàn tất

### 10.1. Nguồn rỗng (`empty`)

```java
Flux<String> result = Flux.concat(
        Flux.<String>empty(),
        Flux.just("B")
);
```

Với concat, nguồn thứ nhất lập tức `onComplete`, rồi nguồn thứ hai được subscribe; kết quả là `B`, complete.

Với merge, empty không góp phần tử; merge vẫn chờ nguồn còn lại hoàn tất:

```java
Flux<String> result = Flux.merge(
        Flux.<String>empty(),
        Flux.just("B")
);
```

Kết quả cũng là `B`, complete, nhưng cơ chế subscribe khác nhau.

### 10.2. Nguồn lỗi (`error`)

```java
Flux<String> later = Flux.just("B");

Flux<String> concatFailed = Flux.concat(
        Flux.<String>error(new IllegalStateException("A failed")),
        later
);
```

`concatFailed` phát `onError`; nguồn B **không được subscribe** theo luồng thành công bình thường của concat.

```java
Flux<String> mergedFailed = Flux.merge(
        Flux.<String>error(new IllegalStateException("A failed")),
        later
);
```

Trong merge, lỗi là terminal; các nguồn đang hoạt động bị hủy/cắt ngang theo thực thi. **Không dự đoán chắc số phần tử B đã được thấy** nếu có cạnh tranh giữa tín hiệu lỗi và dữ liệu đồng thời. Hãy kiểm thử mã thực tế và thiết kế cách xử lý lỗi rõ ràng.

Nếu cần **phát lỗi sau khi các nguồn khác đã có cơ hội chạy**, Reactor cung cấp các biến thể:

```java
Flux<String> concatDelayedError = Flux.concatDelayError(
        Flux.just("A"),
        Flux.<String>error(new IllegalStateException("failed")),
        Flux.just("B")
);

Flux<String> mergeDelayedError = Flux.mergeDelayError(
        16,
        Flux.just("A"),
        Flux.<String>error(new IllegalStateException("failed")),
        Flux.just("B")
);
```

Đây là snippet có import `Flux`; `16` trong overload `mergeDelayError` là `prefetch` của inner source, **không phải timeout hay số lượng request/giây**. Với `concatDelayError`, dữ liệu sau nguồn lỗi có thể vẫn được xử lý trước khi báo lỗi tổng. Với `mergeDelayError`, lỗi được hoãn đến khi backlog của phép merge xử lý xong; không nên dùng hoãn lỗi cho hệ thống cần fail-fast vì lý do an toàn/đúng đắn.

Lỗi sau cùng vẫn là lỗi: `DelayError` **không tự khắc phục** dependency hỏng và không rollback các phần tử đã phát. Khi cần fallback, có thể dùng `onErrorResume` ở vị trí phù hợp.

### 10.3. Nguồn không bao giờ kết thúc (`never`)

```java
Flux<String> concatNever = Flux.concat(
        Flux.<String>never(),
        Flux.just("B")
);
```

Nguồn thứ nhất không gửi `onComplete`; concat **không bao giờ subscribe B** nếu không có cơ chế timeout hoặc cancel từ bên ngoài.

```java
Flux<String> mergeNever = Flux.merge(
        Flux.<String>never(),
        Flux.just("B")
);
```

Merge vẫn có thể phát `B`, nhưng **không phát `onComplete`** vì nguồn never chưa bao giờ kết thúc. Điều này quan trọng khi dùng `.collectList()`: nó cần `onComplete` để trả danh sách, nên có thể chờ vô hạn.

Có thể giới hạn thời gian ở ranh giới thích hợp:

```java
Flux<String> bounded = Flux.merge(
        Flux.<String>never(),
        Flux.just("B")
).timeout(Duration.ofSeconds(2));
```

`timeout(Duration)` được áp cho **khoảng chờ giữa các tín hiệu `onNext`**, hoặc khoảng chờ từ subscribe đến tín hiệu đầu tiên; sau khi nhận `B`, vẫn có thể timeout nếu không có tín hiệu tiếp theo trong 2 giây. Thời gian cần chọn theo nghiệp vụ. Đôi khi cần **giới hạn toàn bộ thời gian chạy** (overall deadline), khác idle timeout; hãy áp deadline tại tầng request/client hoặc sử dụng toán tử phù hợp như `take(Duration)` khi chấp nhận hoàn tất sớm. Không để `.block()` vô hạn trên nguồn never.

## 11. Backpressure, concurrency và sức chứa bộ nhớ

`concat` và `merge` đều tuân thủ nhu cầu của downstream theo hợp đồng Reactive Streams, nhưng có cách phân phối yêu cầu và khả năng buffer khác nhau.

**Concat**:

- Chỉ một nguồn con đang được subscribe để xuất dữ liệu tại một thời điểm (theo ngữ nghĩa nối tuần tự).
- Đơn giản hóa thứ tự, giảm số nguồn I/O hoạt động cùng lúc.
- Nhược điểm là tổng thời gian chờ lớn khi các nguồn độc lập mà lại buộc thực thi nối tiếp.

**Merge**:

- Có thể có nhiều nguồn hoạt động đồng thời, thường dùng buffer/queue nội bộ và phân phối nhu cầu dữ liệu tới từng nguồn.
- Cần kiểm soát số nguồn cùng subscribe và `prefetch` khi gộp số lượng lớn publisher.
- Nếu upstream phát dữ liệu rất nhanh hoặc downstream chậm, queue, memory, connection pool và giới hạn của nguồn phải được quan sát. Backpressure **không đồng nghĩa** không bao giờ có buffer.
- Merge những nguồn vô hạn phát đồng bộ không nhường scheduler có thể làm nguồn khác thiếu cơ hội tiến triển; phải thiết kế nguồn phát và lịch chạy cho phù hợp.

Ví dụ khi danh sách nguồn được tạo theo yêu cầu:

```java
// sources là Flux<Publisher<String>> đã được tạo ở nơi khác.
Flux<String> limited = Flux.merge(sources, 4, 16);
```

Đây là snippet, chưa biên dịch độc lập. `4` là **mức concurrency tối đa cho các publisher con** theo overload nhận nguồn-of-sources; `16` là **prefetch**, tức số phần tử ban đầu được yêu cầu từ từng nguồn con, không phải giới hạn số byte hoặc số lượng HTTP request thực tế. `Publisher` thuộc `org.reactivestreams.Publisher`.

Với nhiều nguồn mạng, số concurrent requests còn bị tác động bởi connection pool của HTTP client, timeout, retry, quota và rate limit của upstream. Nâng concurrency quá cao không bảo đảm throughput cao hơn.

## 12. Áp dụng trong một service Spring WebFlux

Giả sử ứng dụng cần hợp nhất hai nguồn thông báo riêng biệt: nguồn cảnh báo an ninh chậm hơn và nguồn trạng thái tác vụ cập nhật nhanh hơn. Hai client reactive trả về `Flux<Notice>`:

```java
// Snippet trong một @Service đã inject hai client reactive.
public Flux<Notice> allNotices() {
    Flux<Notice> security = securityClient.streamNotices();
    Flux<Notice> operations = operationsClient.streamNotices();

    return Flux.merge(security, operations);
}
```

Đây là **snippet kiến trúc**, không phải file Spring Boot độc lập: `Notice`, `securityClient`, `operationsClient` là các kiểu/bean của ứng dụng, và phương thức `streamNotices()` phải thật sự trả publisher. Dùng merge nếu mục tiêu là **hiển thị thông báo từ bất kỳ nguồn nào khi thông báo đến**, không phải đợi nguồn cảnh báo kết thúc.

Nếu hợp đồng API quy định “trả toàn bộ dữ liệu cũ từ nguồn A trước, sau đó tiếp tục dữ liệu B”, dùng concat chỉ hợp lý khi A **sẽ hoàn tất** và việc subscribe muộn vào B **không làm mất sự kiện quan trọng**:

```java
return Flux.concat(
        securityClient.loadHistory(),
        operationsClient.loadRecentBatch()
);
```

Cả hai phương thức trong snippet phải trả `Publisher<Notice>` phù hợp. Nếu nguồn B là hot stream không replay, phải giải quyết vấn đề bỏ lỡ sự kiện khi subscribe trễ (ví dụ cơ chế cursor/replay) trước khi sử dụng concat.

Với API cần **trả JSON một lần sau khi các nguồn hoàn tất**, có thể ghép `Flux` rồi `.collectList()`, nhưng nếu bất kỳ nguồn nào vô hạn thì không bao giờ có danh sách hoàn chỉnh. Với **SSE**, merged `Flux` hữu ích để stream phần tử theo tiến độ:

```java
@GetMapping(value = "/notices",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Notice> notices() {
    return noticeService.allNotices();
}
```

Đây cũng là snippet cần đặt trong một `@RestController` đã inject `noticeService` và import `org.springframework.http.MediaType`, `org.springframework.web.bind.annotation.GetMapping`, `reactor.core.publisher.Flux`. HTTP streaming còn phụ thuộc codec, timeout, cách ngắt kết nối và khả năng xử lý backpressure của transport/client.

**Không gọi `.block()` hay `.subscribe()` trong WebFlux controller để “ép” merge chạy.** Trả publisher cho Spring quản lý subscription, chuyển tín hiệu thành HTTP response, thực hiện xử lý lỗi và quan sát cancellation khi client ngắt kết nối.

## 13. Quan sát thời điểm subscribe và tín hiệu trong thực tế

Một cách gỡ lỗi đáng tin hơn việc chỉ nhìn output là gắn `doOnSubscribe`, `doOnNext` và `doFinally` vào từng nguồn:

```java
Flux<String> observedA = slowA()
        .doOnSubscribe(s -> System.out.println("A subscribed"))
        .doOnNext(v -> System.out.println("A next: " + v))
        .doFinally(s -> System.out.println("A finally: " + s));

Flux<String> observedB = fastB()
        .doOnSubscribe(s -> System.out.println("B subscribed"))
        .doOnNext(v -> System.out.println("B next: " + v))
        .doFinally(s -> System.out.println("B finally: " + s));

Flux<String> result = Flux.concat(observedA, observedB);
// Có thể thay bằng Flux.merge(observedA, observedB) để so sánh.
```

Các đoạn trên là snippet; `slowA()` và `fastB()` định nghĩa trong mục 7. Khi **có subscriber**:

- Concat: log `B subscribed` chỉ xuất hiện sau khi A phát terminal `onComplete`.
- Merge: hai log subscribe thường xuất hiện gần nhau trước khi nhận các phần tử bất đồng bộ.
- `doFinally` phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL`; nó cũng hữu ích khi subscriber hủy stream hoặc downstream `take(n)` đã đủ phần tử.
- Log từ nhiều scheduler có thể xen kẽ ở thời điểm rất gần nhau; không dùng thứ tự log sát nút để giả lập bằng chứng đảm bảo event-time.

Cần chú ý **mã nằm ngoài pipeline có thể chạy ngay**, ngay cả khi nguồn B chưa subscribe:

```java
Flux<String> b = buildPublisher(); // method này được gọi ngay trong Java
Flux<String> c = Flux.concat(slowA(), b);
```

`concat` trì hoãn **subscribe** vào `b`, chứ không bảo đảm trì hoãn mọi side effect xảy ra trong `buildPublisher()` khi khởi tạo đối tượng. Nếu cần hoãn việc tạo nguồn cho đến lúc được subscribe, cân nhắc:

```java
Flux<String> delayedBuild = Flux.defer(() -> buildPublisher());
Flux<String> c = Flux.concat(slowA(), delayedBuild);
```

`Flux.defer` gọi supplier khi subscription bắt đầu, tránh thực hiện khởi tạo có side effect quá sớm. Tuy vậy, vẫn cần tránh các side effect không kiểm soát trong phương thức tạo publisher.

## 14. Các hiểu lầm và lỗi thường gặp

| Hiểu lầm/lỗi | Điều thực sự xảy ra | Cách xử lý |
|---|---|---|
| “`concat` và `merge` khác nhau chỉ ở tốc độ” | Khác cả **thời điểm subscribe**, thứ tự phát, lỗi và tác động đến hot source | Chọn theo hợp đồng thứ tự và vòng đời |
| “Truyền A trước vào merge thì A luôn ra trước B” | B nhanh có thể phát trước | Không dựa vào thứ tự nguồn khi dùng merge |
| “`merge` luôn tạo hai thread” | Operator không tự cấp thread riêng cho mỗi nguồn | Xem scheduler, I/O client và cách upstream phát |
| “`concat` tự sắp xếp sự kiện theo timestamp” | Concat giữ nhóm nguồn, không sort event time | Dùng thiết kế xử lý event-time thích hợp |
| “`merge` luôn làm kết quả nhanh hơn” | Concurrency bị giới hạn bởi CPU, pool, mạng, backend | Benchmark cùng workload và giám sát tài nguyên |
| “Nguồn B hot vẫn giữ lịch sử khi concat subscribe muộn” | Một số hot source không replay; dữ liệu đã phát có thể bị mất | Dùng replay/cursor/broker khi cần |
| “`merge` hoàn tất ngay khi nguồn đầu tiên xong” | Mọi nguồn liên quan phải hoàn tất thành công | Tách các luồng vô hạn nếu muốn kết quả hữu hạn |
| “`Flux.never()` có thể được `concat` bỏ qua” | Never không `onComplete`, nên concat không chuyển nguồn | Timeout/cancel, hoặc thay đúng nguồn empty |
| “Merge giữ thứ tự nhóm giống concat” | Merge cho phép xen kẽ | Dùng concat hoặc mergeSequential |
| “`mergeSequential` miễn phí về bộ nhớ” | Nguồn sau có thể phải buffer trong lúc chờ nguồn trước | Giới hạn concurrency/prefetch, kiểm thử tải |
| “`delayError` biến lỗi thành thành công” | Lỗi chỉ bị hoãn, vẫn là lỗi terminal | Dùng fallback có chủ ý khi nghiệp vụ cho phép |
| “Một test dùng clock thật sẽ luôn ra thứ tự B1,B2,A1,A2” | Scheduling và tải hệ thống có thể tạo jitter | Kiểm thử thời gian với StepVerifier virtual time |

## 15. Bài tập suy luận

**Bài 1.** Hai nguồn đều cold: A phát `A1` sau 3 giây rồi complete, B phát `B1` sau 1 giây rồi complete. Nếu subscribe ở `t=0`, concat/merge có thứ tự và tổng thời gian lý tưởng nào?

- `concat(A,B)`: A1 khoảng `t=3s`, sau đó subscribe B, B1 khoảng `t=4s`, rồi complete.
- `merge(A,B)`: B1 khoảng `t=1s`, A1 khoảng `t=3s`, rồi complete.

**Bài 2.** A = `Flux.just("A").concatWith(Flux.never())`; B = `Flux.just("B")`. Điều gì xảy ra?

- `Flux.concat(A,B)` phát A rồi chờ mãi, không subscribe B.
- `Flux.merge(A,B)` có thể phát cả A và B, nhưng không complete do A chứa `never()`; trật tự A/B giữa hai nguồn không được bảo đảm tuyệt đối.

**Bài 3.** Một nguồn hot phát bản tin tại `t=100ms`, trong khi concat chỉ subscribe nó ở `t=500ms`. Có lấy lại bản tin được không?

- Không có bảo đảm. Với hot source không replay, bản tin có thể đã mất. Muốn lấy lại cần cơ chế lưu trữ/replay/cursor được thiết kế trước.

**Bài 4.** Bạn cần gọi ba API độc lập đồng thời nhưng trình bày kết quả theo thứ tự A → B → C. Chọn toán tử nào?

- Cân nhắc `mergeSequential` hoặc `flatMapSequential`, với giới hạn concurrency/buffer thích hợp. `concat` cũng giữ thứ tự nhưng trì hoãn subscription của API sau; `merge` không giữ nhóm nguồn.

**Bài 5.** Nguồn A phát lỗi trước khi B kịp hoàn tất trong `merge(A,B)`. Có chắc tất cả phần tử B đã sinh ra đều vào kết quả không?

- Không. Lỗi terminal có thể cắt ngang/cancel B. Nếu muốn đợi kết quả khác, xem xét cách xử lý lỗi từng nguồn hoặc `mergeDelayError` theo yêu cầu nghiệp vụ.

## 16. Kết luận lựa chọn

Khi có nhiều nguồn dữ liệu với quan hệ thời gian khác nhau, hãy trả lời ba câu hỏi theo thứ tự: **nguồn nào được phép bắt đầu ngay, output cần giữ thứ tự nào, và điều kiện nào kết thúc toàn bộ chuỗi?**

- Dùng **`concat`** khi phải xử lý hết một nguồn và nhận `onComplete` trước khi bắt đầu nguồn tiếp theo; giữ thứ tự nhóm nguồn.
- Dùng **`merge`** khi nhiều nguồn độc lập được phép chạy sớm và kết quả có thể hiển thị theo tiến độ, không yêu cầu thứ tự nhóm.
- Dùng **`mergeSequential`** khi muốn bắt đầu sớm nhưng vẫn giữ thứ tự nhóm, chấp nhận thêm bộ đệm và cần kiểm soát tài nguyên.

Sau đó kiểm tra thêm rủi ro **hot source không replay**, nguồn **không bao giờ hoàn tất**, cách **phát lỗi**, timeout/cancellation và mức **concurrency/backpressure**. Đây là các yếu tố quyết định tính đúng đắn của chương trình reactive trong Spring WebFlux.

## Tài liệu chính thức

- Project Reactor, **Flux API: concat, merge, mergeSequential, delayElements**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor, **Which operator do I need?**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Project Reactor, **Testing with StepVerifier and virtual time**: https://projectreactor.io/docs/core/release/reference/testing.html
- Project Reactor, **Hot Versus Cold**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html
- Spring Framework, **WebFlux overview**: https://docs.spring.io/spring-framework/reference/web/webflux.html