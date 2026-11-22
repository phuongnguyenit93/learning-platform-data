# when, and và phối hợp tín hiệu hoàn tất trong Reactor

## 1. Vấn đề: đợi nhiều công việc reactive kết thúc

Trong Spring WebFlux, có những tác vụ **độc lập** cần cùng hoàn thành trước khi hệ thống chuyển sang bước kế tiếp. Ví dụ: ghi nhật ký kiểm toán và cập nhật chỉ mục, xóa nhiều đối tượng tạm, gửi yêu cầu cập nhật tới nhiều dịch vụ, hoặc chạy một loạt tác vụ không cần gom dữ liệu trả về.

Điều kiện nghiệp vụ là **"chỉ báo hoàn tất khi tất cả các nguồn đều hoàn tất thành công"**. Đây là tình huống điển hình cho hai API trong Project Reactor:

- **Mono.when(Publisher<?>... sources)**: phối hợp **nhiều Publisher**; trả về **Mono<Void>**, hoàn tất khi mọi nguồn hoàn tất thành công.
- **someMono.and(Publisher<?> other)**: kết hợp tín hiệu kết thúc của **một Mono hiện tại và một Publisher khác**; cũng trả về **Mono<Void>**.

Cả hai tập trung vào **tín hiệu kết thúc**, không dùng dữ liệu kết quả để tạo giá trị mới. Nếu cần lấy kết quả của các nguồn, hãy dùng cơ chế khác như **Mono.zip**; nếu cần bắt đầu công việc B **sau khi A hoàn thành**, dùng **then**. Đây là ba nhu cầu khác nhau mà việc nhầm lẫn có thể gây sai luồng thực thi.

Bài học sẽ giải thích tín hiệu **onComplete/onError**, sự khác biệt giữa **when**, **and**, **whenDelayError**, **then** và **zip**, cơ chế đăng ký, lỗi/hủy, cách áp dụng trong WebFlux và ví dụ Java 17 chạy được.

## 2. Nền tảng: kết thúc một Publisher nghĩa là gì?

Trong Reactive Streams, Publisher giao tiếp với Subscriber qua chuỗi tín hiệu:

~~~text
onSubscribe(Subscription)
  ├── onNext(value) ... [không hoặc nhiều lần]
  └── onComplete()  hoặc  onError(error)
~~~

- **onComplete**: nguồn không còn phần tử và đã kết thúc **thành công**.
- **onError**: nguồn kết thúc vì **lỗi**; không còn onComplete sau đó.
- **cancel()**: yêu cầu hủy từ downstream; đây là thao tác điều khiển, **không đồng nghĩa** onComplete.
- **Mono<T>** phát tối đa một phần tử rồi kết thúc. **Flux<T>** có thể phát nhiều phần tử.
- **Mono<Void>** không phát giá trị có ý nghĩa; khi thành công nó chỉ gửi **onComplete**. Khi lỗi, nó gửi **onError**.

Ví dụ:

~~~java
Mono<Void> save = repository.save(entity).then();
~~~

Đây là snippet trong một service với **repository** và **entity** có sẵn. **save** hoàn tất thành công sau khi Mono lưu đối tượng hoàn thành, nhưng giá trị của kết quả lưu đã được bỏ đi bởi **then()**. Nếu nguồn lỗi, tín hiệu **onError** vẫn được truyền tiếp.

Khi nói "đợi tất cả", Reactor đợi **tín hiệu kết thúc của những Publisher được đưa vào**, không đoán trạng thái của một tác vụ được khởi chạy tách rời bằng **subscribe()** hoặc một Future đã chạy bên ngoài pipeline.

## 3. Mono.when: phối hợp nhiều nguồn hoàn tất

Cú pháp phổ biến:

~~~java
Mono<Void> allDone = Mono.when(taskA, taskB, taskC);
~~~

Trong đó **taskA/taskB/taskC** có thể là **Mono<?>** hoặc **Flux<?>**. Khi có người subscribe vào **allDone**, Reactor đăng ký những nguồn được cung cấp rồi phối hợp các terminal signals. **allDone**:

1. Chỉ gửi **onComplete** khi tất cả nguồn đã hoàn tất thành công.
2. Không phát các giá trị onNext của các nguồn xuống downstream; kết quả là **Mono<Void>**.
3. Nếu một nguồn **onError**, trong chế độ mặc định nó chuyển lỗi xuống downstream ngay và yêu cầu hủy những nguồn còn đang hoạt động.
4. Nếu downstream **cancel**, nó yêu cầu hủy các nguồn đang đăng ký.
5. Nếu một nguồn **không bao giờ hoàn tất** và không có lỗi/hủy/timeout, **allDone** cũng không hoàn tất thành công.

Minh họa hai công việc không phụ thuộc nhau:

~~~text
taskA:      subscribe ────── onComplete ──────┐
                                              ├── when ── onComplete
taskB:      subscribe ───────────── onComplete┘
~~~

Một nguồn hoàn thành trước **không đủ** để kết thúc **when**. Nguồn nào hoàn tất sớm hay muộn không làm thay đổi điều kiện thành công: **mọi nguồn** đều phải xong.

### 3.1. when có chạy song song không?

**when có thể cho phép các nguồn hoạt động đồng thời**, vì nó không chủ động nối chúng thành từng bước như **then**. Tuy nhiên, **when tự nó không tạo thread, không chuyển scheduler và không biến mã chặn đồng bộ thành I/O bất đồng bộ**. Khi các nguồn là Mono bất đồng bộ (WebClient, timer, I/O reactive), tiến trình của chúng thường có thể chồng lấn. Nếu các nguồn chạy đồng bộ và chặn trong quá trình subscribe, việc có thực sự chạy song song hay không phụ thuộc nguồn và scheduler.

Không nên diễn giải **Mono.when(A,B)** thành "hai hàm Java luôn chạy song song trên hai thread". Điều được bảo đảm là **điều kiện hoàn tất của Mono trả về** và chính sách lỗi/hủy đã nêu.

### 3.2. Dữ liệu bị bỏ đi

~~~java
Mono<Void> done = Mono.when(
    Mono.just("alpha"),
    Mono.just("beta")
);
~~~

Khi **done** hoàn thành, nó không có kết quả kiểu **Tuple2<String,String>** hay một danh sách chuỗi. Các giá trị **alpha** và **beta** chỉ là tín hiệu nội bộ bị loại khỏi kết quả kết hợp. Nếu cần trả về cả hai giá trị, dùng **Mono.zip**:

~~~java
Mono<Tuple2<String, String>> values = Mono.zip(
    Mono.just("alpha"),
    Mono.just("beta")
);
~~~

Đoạn trên yêu cầu import **reactor.util.function.Tuple2**. **zip** đợi các nguồn phát **giá trị**, nên khác với **when** khi nguồn thành công rỗng. Không chuyển cơ học một workflow **Mono<Void>** sang **zip**.

## 4. Mono.and: nối điều kiện hoàn tất của hai nguồn

**and** là phương thức trên một Mono:

~~~java
Mono<Void> bothDone = taskA.and(taskB);
~~~

Ý nghĩa: **bothDone** hoàn thành khi **taskA** và **taskB** đều hoàn thành thành công; nó không truyền dữ liệu của hai nguồn. Ví dụ:

~~~java
Mono<Void> refreshCache = cache.refresh(key);
Mono<Void> writeAudit = auditStore.append(event);

return refreshCache.and(writeAudit);
~~~

Đây là snippet service giả định các lời gọi trả **Mono<Void>**. Hai tác vụ có thể tiến triển độc lập; kết quả chung thành công chỉ sau khi cả hai kết thúc. Trường hợp lỗi sẽ khiến kết quả chung lỗi và yêu cầu hủy nguồn còn lại, tương tự ý nghĩa phối hợp của **when**.

Có thể viết tương đương về mục đích:

~~~java
Mono<Void> bothByAnd = taskA.and(taskB);
Mono<Void> bothByWhen = Mono.when(taskA, taskB);
~~~

**Khác biệt chủ yếu là hình thức gọi**:

- **and** thuận tiện khi đang có một Mono và muốn ghép thêm một nguồn.
- **when** rõ ràng khi tập hợp 3, 4 hoặc nhiều nguồn độc lập, hoặc danh sách Publisher động.
- Với nhiều nguồn, **Mono.when(taskA, taskB, taskC)** thường dễ đọc hơn một chuỗi **taskA.and(taskB).and(taskC)**.

**and không có nghĩa là thứ tự "A rồi B"**. Từ *and* ở đây biểu diễn quan hệ logic **cả A và B đều kết thúc**, không phải thứ tự thực thi.

## 5. Sơ đồ phối hợp tín hiệu: thành công, lỗi và hủy

### 5.1. Tất cả nguồn thành công

~~~text
Nguồn A: onSubscribe ── onNext(A) ── onComplete ───┐
                                                   ├── when/and ── onComplete
Nguồn B: onSubscribe ────────────── onComplete ────┘
~~~

Bởi vì **when/and** chỉ quan tâm terminal signal, onNext(A) không được phát ra ở kết quả **Mono<Void>**. Nguồn B có thể là **Mono.empty()**; hoàn thành rỗng vẫn được xem là hoàn thành thành công.

### 5.2. Một nguồn thất bại

~~~text
Nguồn A: onSubscribe ─────────── onError(A failed)
                                              │
Nguồn B: onSubscribe ── đang xử lý ───────────┼── cancel được yêu cầu
                                              │
when/and:            onError(A failed) <──────┘
~~~

Đây là **fail-fast**: lỗi đầu tiên được truyền xuống kết quả ngay, và Reactor yêu cầu hủy nguồn khác còn hoạt động. Vì hủy là yêu cầu, những side effect **đã gửi tới mạng**, **đã commit vào database** hoặc **không hỗ trợ hủy tức thì** có thể vẫn hoàn tất. **when/and không phải transaction phân tán, không có rollback tự động.**

Một nguồn lỗi đồng bộ rất sớm có thể khiến nguồn khác chưa thực hiện phần việc mong đợi. Do đó, không dùng **when** để bảo đảm "mọi nguồn chắc chắn đã chạy ít nhất một lần" khi có lỗi.

### 5.3. Hủy từ downstream

Khi HTTP client ngắt kết nối, timeout ở downstream, hoặc người sở hữu Disposable gọi **dispose()**, subscription kết hợp có thể bị hủy; **when/and** yêu cầu hủy các subscription nguồn. Không tự sinh **onComplete**. Nên theo dõi **doFinally(signalType)** nếu cần phân biệt **ON_COMPLETE**, **ON_ERROR** và **CANCEL** ở đúng vị trí pipeline.

## 6. whenDelayError: vẫn đợi các nguồn còn lại sau khi có lỗi

**Mono.whenDelayError(...)** có cùng mục tiêu "phối hợp hoàn tất" nhưng khác chính sách lỗi:

~~~java
Mono<Void> allAttempted = Mono.whenDelayError(taskA, taskB, taskC);
~~~

- Nếu tất cả nguồn thành công, kết quả **onComplete**.
- Nếu một hoặc nhiều nguồn thất bại, Reactor **trì hoãn phát onError** đến khi các nguồn còn lại cũng kết thúc. Những nguồn khác **không bị hủy sớm chỉ vì một nguồn lỗi** như chính sách fail-fast của when.
- Nếu nhiều nguồn lỗi, chúng được kết hợp để không mất toàn bộ thông tin; cần kiểm tra exception gốc và các **suppressed exceptions** phù hợp phiên bản Reactor.
- Nếu một nguồn treo mãi, **kết quả có thể treo mãi cả khi đã ghi nhận lỗi ở nguồn khác**. Dùng deadline/timeout thích hợp.
- Việc downstream tự hủy vẫn là thao tác hủy; **DelayError không ngăn cancellation từ downstream**.

So sánh:

| Tình huống | **Mono.when** / **and** | **Mono.whenDelayError** |
| --- | --- | --- |
| Tất cả thành công | Hoàn tất sau tất cả | Hoàn tất sau tất cả |
| Một nguồn lỗi | Lỗi sớm; yêu cầu hủy phần còn lại | Đợi những nguồn còn lại kết thúc rồi mới báo lỗi |
| Nhiều nguồn lỗi | Không bảo đảm thu đủ mọi lỗi sau lỗi đầu | Có thể tập hợp các lỗi để báo sau |
| Một nguồn không bao giờ hoàn tất | Có thể chờ vô hạn nếu không lỗi/hủy | Có thể chờ vô hạn kể cả khi nguồn khác đã lỗi |
| Dữ liệu nguồn có được giữ không? | Không, trả Mono<Void> | Không, trả Mono<Void> |

**whenDelayError không tự phục hồi lỗi**. Nếu một nguồn thất bại và những nguồn khác xong, kết quả cuối vẫn là **onError**. Nếu nghiệp vụ chấp nhận lỗi ở một bước để vẫn coi toàn bộ workflow là thành công, cần xử lý lỗi rõ ràng tại nguồn đó, chẳng hạn **onErrorResume(... -> Mono.empty())**, đồng thời lưu trạng thái thất bại ở nơi có thể kiểm tra.

## 7. Phân biệt when, and, then, zip và merge

| Toán tử | Mục tiêu | Phối hợp chạy các nguồn | Kết quả |
| --- | --- | --- | --- |
| **Mono.when(A,B,C)** | Đợi nhiều nguồn hoàn tất | Không yêu cầu A xong rồi mới B bắt đầu | **Mono<Void>** |
| **A.and(B)** | Đợi A và B hoàn tất | Không yêu cầu thực thi tuần tự | **Mono<Void>** |
| **Mono.whenDelayError(A,B,C)** | Đợi mọi nguồn, kể cả khi một nguồn lỗi | Trì hoãn lỗi đến khi các nguồn kết thúc | **Mono<Void>** hoặc onError |
| **A.then(B)** | **B bắt đầu sau khi A hoàn tất thành công** | Tuần tự hai bước | **Mono<V>** theo kết quả B |
| **Mono.zip(A,B)** | Đợi và **kết hợp giá trị** A/B | Có thể phối hợp các nguồn độc lập | **Mono<Tuple2<...>>**; cần giá trị từ cả hai |
| **Flux.merge(A,B)** | Trộn **phần tử** được phát từ các nguồn | Các phần tử có thể xen kẽ | **Flux<T>** |

Hãy đặt câu hỏi trước khi chọn:

1. **Cần giữ kết quả A và B?** Dùng **zip** (hoặc operator phối hợp giá trị phù hợp).
2. **Chỉ cần xác nhận mọi bước đã xong?** Dùng **when** hoặc **and**.
3. **Cần chạy bước B sau khi A xong?** Dùng **then**.
4. **Cần mọi bước được thử xong dù một bước lỗi?** Cân nhắc **whenDelayError** cùng timeout và chính sách báo lỗi.
5. **Cần gom và phát các phần tử của nhiều Flux?** Xem xét **merge**, **concat** hoặc operator tương ứng, không dùng when để chuyển tiếp onNext.

### 7.1. then bảo đảm thứ tự, when thì không

~~~java
Mono<Void> sequential = updateDatabase()
    .then(sendNotification());

Mono<Void> coordinated = Mono.when(
    updateDatabase(),
    sendNotification()
);
~~~

Các hàm trong snippet là ví dụ giả định trả **Mono<Void>** và tạo công việc theo mô hình cold/deferred. Với **sequential**, Reactor subscribe vào notification sau khi phần update thành công. Với **coordinated**, cả hai nguồn được phối hợp theo terminal signal mà không có quan hệ phụ thuộc thứ tự. Nếu thông báo yêu cầu dữ liệu đã commit, dùng **then**, không dùng **when**.

**Cẩn thận với side effect eager:** nếu một hàm tạo và khởi chạy **CompletableFuture** ngay lúc được gọi, thì truyền kết quả vào **then(...)** không ngăn công việc đã bắt đầu. Hãy đưa phần khởi chạy vào **Mono.defer(...)** hoặc dùng publisher cold phù hợp để bảo đảm lúc subscribe mới thực hiện.

### 7.2. zip không thay thế when cho Mono<Void>

~~~java
Mono<Void> save = repository.save(record).then();
Mono<Void> notify = notifier.send(event).then();

// Cần đợi hoàn tất, không cần giá trị:
// Mono.when(save, notify)

// Không phù hợp nếu muốn đợi cả hai tác vụ Void để lấy tuple:
// Mono.zip(save, notify)
~~~

Từng Mono<Void> hoàn tất **không phát phần tử**; **zip** đòi hỏi mỗi nguồn có một giá trị để kết hợp. Khi một nhánh rỗng, zip có thể kết thúc sớm và hủy nhánh khác, đôi khi các nguồn còn chưa được subscribe. **when** mới là operator được thiết kế cho việc đợi hoàn tất mà không cần dữ liệu.

## 8. Ví dụ Java 17+ chạy được: when, and, lỗi và delay error

Ví dụ Maven dưới đây sử dụng Reactor Core 3.6.6. Nó phân biệt **đợi hai Mono bất đồng bộ**, **ghép hai tác vụ**, **fail-fast hủy nguồn chưa hoàn tất** và **delay error**. Chương trình dùng các bộ đếm **AtomicInteger/AtomicBoolean** để tránh phụ thuộc thứ tự log giữa nhiều scheduler.

Cấu trúc thư mục:

~~~text
completion-coordination-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── CompletionCoordinationDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>completion-coordination-demo</artifactId>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tệp **src/main/java/CompletionCoordinationDemo.java**:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public class CompletionCoordinationDemo {

    public static void main(String[] args) {
        AtomicInteger completed = new AtomicInteger();

        Mono<Void> slow = Mono.delay(Duration.ofMillis(100))
            .doOnNext(tick -> completed.incrementAndGet())
            .then();

        Mono<Void> fast = Mono.delay(Duration.ofMillis(20))
            .doOnNext(tick -> completed.incrementAndGet())
            .then();

        Mono.when(slow, fast).block(Duration.ofSeconds(5));
        System.out.println("when finished = " + completed.get());

        AtomicInteger pairCount = new AtomicInteger();
        Mono<Void> first = Mono.fromRunnable(
            () -> pairCount.incrementAndGet()
        );
        Mono<Void> second = Mono.fromRunnable(
            () -> pairCount.incrementAndGet()
        );

        first.and(second).block();
        System.out.println("and finished = " + pairCount.get());

        AtomicBoolean cancelSeen = new AtomicBoolean();
        Mono<Void> pending = Mono.<Void>never()
            .doOnCancel(() -> cancelSeen.set(true));
        Mono<Void> failed = Mono.error(
            new IllegalStateException("boom")
        );

        Mono.when(pending, failed)
            .onErrorResume(error -> Mono.empty())
            .block();

        System.out.println(
            "when cancelled remaining = " + cancelSeen.get()
        );

        AtomicInteger delayedCount = new AtomicInteger();
        Mono<Void> otherWork = Mono.fromRunnable(
            () -> delayedCount.incrementAndGet()
        );

        Mono.whenDelayError(
                Mono.error(new IllegalArgumentException("invalid")),
                otherWork
            )
            .onErrorResume(error -> Mono.empty())
            .block();

        System.out.println(
            "whenDelayError other finished = " + delayedCount.get()
        );
    }
}
~~~

Chạy bằng JDK 17+ và Maven tại thư mục dự án:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CompletionCoordinationDemo
~~~

**Stdout mong đợi** (không tính thông báo riêng của Maven):

~~~text
when finished = 2
and finished = 2
when cancelled remaining = true
whenDelayError other finished = 1
~~~

Giải thích từng đoạn:

1. **when**: hai Mono sử dụng timer, có thời gian 100 ms và 20 ms. Bộ đếm tăng khi mỗi timer phát phần tử; **then()** biến mỗi chuỗi thành tín hiệu hoàn tất. Khi **when** thành công thì cả hai đã chạy xong, nên bộ đếm bằng 2. Không suy ra thời gian hoàn tất tổng là đúng 100 ms tuyệt đối; scheduler có thể ảnh hưởng.
2. **and**: hai Mono dùng **fromRunnable** và trả về **Mono<Void>**. Việc đăng ký vào kết quả **and** thực hiện cả hai và chỉ hoàn tất khi bộ đếm thành 2.
3. **when fail-fast**: nguồn **pending** sẽ không tự hoàn thành. Nguồn **failed** báo lỗi ngay; khi đó **when** yêu cầu hủy **pending**. **doOnCancel** đặt cờ true. **onErrorResume** chỉ được dùng ở biên demo để tránh dừng chương trình vì exception.
4. **whenDelayError**: dù một nguồn lỗi ngay, Reactor vẫn cho **otherWork** hoàn thành rồi mới truyền lỗi. Sau xử lý lỗi ở biên demo, bộ đếm otherWork bằng 1.
5. **block(...)** được dùng riêng trong phương thức **main** của ứng dụng CLI để chờ kết thúc và in kết quả. **Không dùng block trên event-loop WebFlux**.

Điểm kiểm chứng: hai trường hợp cuối đều có lỗi nguồn. Khác biệt không phải **có hay không có lỗi**, mà là **when yêu cầu hủy công việc còn lại** trong khi **whenDelayError tiếp tục đợi các công việc còn lại kết thúc**.

## 9. Cách dùng trong Spring WebFlux

### 9.1. Đợi nhiều tác vụ độc lập rồi trả HTTP response

Giả sử endpoint cần kích hoạt hai tác vụ trả **Mono<Void>**. Nếu chỉ muốn trả thành công khi cả hai xong:

~~~java
@PostMapping("/orders/{id}/refresh")
public Mono<Void> refresh(@PathVariable String id) {
    Mono<Void> refreshCache = cacheService.refresh(id);
    Mono<Void> publishEvent = eventService.publishRefresh(id);

    return Mono.when(refreshCache, publishEvent);
}
~~~

Đây là snippet trong Spring controller giả định **cacheService** và **eventService** đã có, cả hai phương thức trả **Mono<Void>**. Spring WebFlux sẽ subscribe vào Mono được controller trả về trong quá trình xử lý HTTP. Nếu cả hai hoàn thành thành công, response có thể hoàn tất. Nếu một nguồn lỗi, lỗi được truyền vào pipeline xử lý lỗi của framework, và nguồn còn lại có thể bị yêu cầu hủy.

**Cần cân nhắc nghiệp vụ:** nếu việc publish event chỉ đúng sau khi cập nhật cache thành công, hai công việc **phụ thuộc nhau**; khi đó hãy dùng **refreshCache.then(eventService.publishRefresh(id))** để phản ánh thứ tự.

### 9.2. Khi tất cả tác vụ phải được thử dù một tác vụ lỗi

Ví dụ yêu cầu kiểm tra/xóa nhiều tài nguyên độc lập và muốn chờ các thao tác còn lại kể cả khi một thao tác thất bại:

~~~java
public Mono<Void> cleanup(String id) {
    return Mono.whenDelayError(
        sessionStore.delete(id),
        cacheStore.evict(id),
        auditStore.markCleanup(id)
    );
}
~~~

Snippet giả định cả ba dịch vụ trả Publisher có thể hoàn tất. **whenDelayError** giúp kết quả cuối được báo sau khi cả ba nguồn kết thúc, kể cả khi có lỗi. Nó **không bảo đảm tất cả thao tác thành công**: nếu có lỗi, response vẫn có thể báo lỗi. Muốn trả báo cáo chi tiết từng bước, cần **biến lỗi và thành công thành dữ liệu trạng thái riêng** và tổng hợp chúng bằng cơ chế phù hợp, thay vì chỉ dựa vào **Mono<Void>**.

### 9.3. Không tự subscribe từng task trong controller

Cách dễ mất kiểm soát:

~~~java
@PostMapping("/bad-refresh")
public Mono<Void> refreshWrong() {
    cacheService.refreshAll().subscribe();
    eventService.publishAll().subscribe();
    return Mono.empty();
}
~~~

**Lỗi thiết kế:** controller đã tự khởi chạy hai subscription, rồi trả **Mono.empty()** hoàn tất ngay. Spring không thể đợi chúng qua Mono trả về; lỗi có thể không được xử lý đúng ngữ cảnh, và cancellation của HTTP request không còn bao trùm hai tác vụ.

Cách ghép:

~~~java
@PostMapping("/refresh")
public Mono<Void> refreshCorrect() {
    return Mono.when(
        cacheService.refreshAll(),
        eventService.publishAll()
    );
}
~~~

Trong môi trường WebFlux, ưu tiên **return pipeline** để framework sở hữu subscription. Không gọi **subscribe()** lồng bên trong một Mono rồi kỳ vọng **when** sẽ theo dõi phần việc đã bị tách khỏi chain.

### 9.4. Chọn ranh giới giao dịch phù hợp

**Mono.when** không cung cấp transaction và không điều phối commit nguyên tử qua nhiều dịch vụ. Nếu một ghi dữ liệu đã commit, rồi ghi thứ hai lỗi, Reactor có thể báo lỗi và hủy phần việc còn lại nhưng **không tự rollback side effect đã hoàn tất**. Với các thao tác dùng chung một kết nối transaction reactive hoặc phụ thuộc trạng thái, chạy phối hợp không tuần tự có thể không phù hợp. Khi cần thứ tự, dùng **then**; khi cần nhất quán đa dịch vụ, thiết kế idempotency, outbox/saga hoặc chính sách bù trừ tùy nghiệp vụ.

## 10. Timeout, cancellation và backpressure

### 10.1. Một nguồn không hoàn thành

~~~java
Mono<Void> all = Mono.when(
    Mono.<Void>never(),
    Mono.delay(Duration.ofMillis(100)).then()
);
~~~

Nguồn thứ hai hoàn tất, nhưng nguồn thứ nhất **never** không phát terminal signal. **all** sẽ chờ mãi nếu không có cơ chế hủy/timeout.

Có thể đặt thời hạn:

~~~java
Mono<Void> bounded = Mono.when(taskA, taskB)
    .timeout(Duration.ofSeconds(5));
~~~

Khi hết 5 giây mà kết quả chưa kết thúc, **timeout** phát lỗi và hủy upstream kết hợp theo giao thức. Việc hủy **không bảo đảm** chấm dứt ngay một HTTP request, tác vụ blocking hoặc side effect ở hệ thống bên ngoài. Giới hạn thời gian ở ví dụ chỉ là minh họa; cần đặt dựa trên SLA và đặc điểm dịch vụ.

### 10.2. Quan sát trạng thái sau kết hợp

~~~java
Mono<Void> coordinated = Mono.when(taskA, taskB)
    .doOnSuccess(ignored -> log("all complete"))
    .doOnError(error -> logError(error))
    .doFinally(signal -> log("finished with " + signal));
~~~

Đây là snippet có các hàm ghi log giả định. **doOnSuccess** với Mono<Void> được gọi khi hoàn thành thành công, và đối số sẽ là **null** vì không có giá trị; đây **không phải onNext(null)**. **doFinally** quan sát cả **ON_COMPLETE**, **ON_ERROR** và **CANCEL**, hữu ích để theo dõi pipeline. Cần lưu ý doFinally có thể chạy sau khi terminal signal đã được chuyển tới downstream, nên không dùng nó thay cơ chế chờ đồng bộ.

### 10.3. Nhu cầu nhận và dữ liệu bị bỏ qua

**when/and** subscribe vào các Publisher nguồn và xử lý hoàn tất; nếu nguồn là **Flux** nhiều phần tử, các giá trị của Flux không được đưa vào kết quả **Mono<Void>**. Điều này không có nghĩa Flux không được subscribe hoặc bỏ qua việc thực thi side effect; nguồn vẫn phải đi qua quá trình kết thúc. Vì vậy, đưa một Flux vô hạn vào **when** có thể khiến kết quả không bao giờ thành công.

Do mục tiêu là **terminal coordination**, người dùng không nên dựa vào **when** như cơ chế backpressure/chuyển tiếp giá trị. Nếu cần phát dữ liệu theo tốc độ downstream, chọn operator quản lý **Flux** như **concatMap**, **flatMap**, **merge**, **zip** tùy yêu cầu thay vì trả một Mono<Void> làm mất payload.

## 11. Những nhầm lẫn thường gặp

| Nhận định/hiện tượng | Cách hiểu đúng |
| --- | --- |
| "when(A,B) thực thi A rồi mới B" | when phối hợp các nguồn **độc lập**, không bảo đảm thứ tự phụ thuộc. Dùng **A.then(B)** khi cần tuần tự. |
| "and khác when vì giữ dữ liệu" | **and** và **when** đều trả **Mono<Void>** và chỉ phối hợp hoàn tất. |
| "when trả danh sách kết quả" | Không; các onNext bị bỏ. Dùng **Mono.zip** hoặc cơ chế gom kết quả nếu cần giá trị. |
| "Mono.empty là lỗi với when" | **Mono.empty()** hoàn tất thành công; nó không cung cấp payload nhưng vẫn đạt điều kiện hoàn tất. |
| "zip thay thế được when khi cả hai nguồn Mono<Void>" | Zip cần mỗi nguồn phát giá trị; với Mono<Void>, nó có thể hoàn tất sớm và hủy nguồn khác. |
| "when tự tạo hai thread chạy song song" | when không cấp thread/scheduler. Mức độ đồng thời do Publisher và scheduler quyết định. |
| "Một nguồn lỗi, nguồn còn lại luôn hoàn thành" | Với when/and, Reactor yêu cầu hủy nguồn còn lại; không bảo đảm hoàn thành. |
| "whenDelayError nuốt lỗi" | Nó trì hoãn lỗi, **không xóa lỗi**; kết quả cuối vẫn lỗi nếu nguồn lỗi. |
| "cancel là onComplete" | Cancellation là yêu cầu dừng, không phải terminal success. |
| "when bảo đảm rollback nếu một việc thất bại" | Reactor không tự đảo ngược side effect đã xảy ra. |
| "Một Mono.never không ảnh hưởng" | when có thể chờ vô hạn nếu nguồn không kết thúc; cần timeout/hủy. |
| "subscribe từng task rồi trả Mono.when(...)" | Chỉ Publisher nằm trong pipeline mới được phối hợp. Không tự subscribe tách rời. |
| "whenDelayError luôn chạy hết dù client hủy" | Downstream cancel vẫn có thể hủy các nguồn; delayError chỉ điều chỉnh phản ứng với **lỗi nguồn**. |

## 12. Bài tập và tự kiểm tra

**Câu 1.** Có hai Mono<Void> là **writeAudit()** và **evictCache()**, không phụ thuộc nhau. HTTP request chỉ được hoàn tất khi cả hai xong. Dùng operator nào?  
**Trả lời:** **Mono.when(writeAudit(), evictCache())** hoặc **writeAudit().and(evictCache())**.

**Câu 2.** Nếu việc gửi email yêu cầu dữ liệu phải được lưu thành công trước, có nên dùng when?  
**Trả lời:** không nên. Dùng **save().then(sendEmail())**, với công việc gửi email được biểu diễn bằng một Publisher cold/deferred.

**Câu 3.** Một nguồn Mono.empty() và một nguồn Mono.delay(...).then() được đưa vào Mono.when. Kết quả hoàn thành lúc nào?  
**Trả lời:** khi nguồn delay cũng hoàn tất; **Mono.empty()** đã hoàn thành thành công nhưng không thể làm when kết thúc trước nguồn còn lại.

**Câu 4.** Trong Mono.when(A,B), A lỗi sớm, B đang xử lý. B có chắc hoàn thành không?  
**Trả lời:** không. when yêu cầu cancel B và chuyển lỗi xuống downstream. Tác vụ I/O ngoài hệ thống có thể không dừng ngay, nhưng không được dựa vào việc B hoàn thành trong pipeline.

**Câu 5.** Muốn thử tất cả tác vụ rồi mới báo lỗi, nhưng không cần kết quả chi tiết. Dùng gì?  
**Trả lời:** **Mono.whenDelayError(...)**, kết hợp timeout nếu có nguồn có thể treo.

**Câu 6.** Vì sao Mono.zip(Mono<Void>, Mono<Void>) không phù hợp để đợi mọi tác vụ hoàn tất?  
**Trả lời:** zip cần giá trị từ mỗi nguồn. Mono<Void> hoàn thành mà không có onNext; zip có thể kết thúc sớm và không bảo đảm subscribe/thực hiện mọi nhánh.

**Bài thực hành:** thay **Mono.when** trong phần 8 thành **Mono.whenDelayError** cho ví dụ pending/failed. Vì pending là Mono.never(), điều gì xảy ra? Kết quả sẽ không tự kết thúc. Hãy thêm **timeout(Duration.ofMillis(200))** và quan sát lỗi timeout/hủy. Sau đó thay pending bằng một Mono hoàn thành sau 100 ms để so sánh chính sách khi có lỗi.

## 13. Quy tắc áp dụng

Muốn chọn đúng toán tử, hãy bắt đầu từ **điều kiện hoàn tất của nghiệp vụ**:

- Nếu các bước **độc lập**, cần **tất cả hoàn tất thành công**, **Mono.when** cho nhiều nguồn hoặc **and** cho cặp Mono + Publisher.
- Nếu các bước **phụ thuộc thứ tự**, dùng **then**.
- Nếu cần **giá trị** để kết hợp, dùng **zip** và kiểm tra hành vi khi nguồn rỗng.
- Nếu cần **đợi tất cả nguồn có cơ hội kết thúc trước khi báo lỗi**, dùng **whenDelayError** và chủ động xử lý timeout.
- Nếu cần **báo cáo chi tiết mỗi bước**, tạo kết quả có cấu trúc cho từng Publisher, giữ cả trạng thái thành công/lỗi, rồi mới tổng hợp.

Kết quả **Mono<Void>** diễn đạt điều kiện "đã xong" của một pipeline. Để pipeline phản ánh đúng nghiệp vụ, cần thêm ranh giới subscription rõ ràng, xử lý lỗi/hủy và bảo đảm rằng các thao tác cần được chờ đã nằm **bên trong** các Publisher được phối hợp.

## 14. Tài liệu tham khảo

- Project Reactor, **Mono API** (when, whenDelayError, and, then, zip): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Reference Guide, **Operator Choice**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Reference Guide, **Handling Errors**: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Reference Guide, **Mono.zipWith or zipWhen is never called**: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Framework, **Reactive Core**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
