# PublisherProbe để xác nhận nhánh dự phòng được đăng ký

## 1. Vấn đề kiểm thử: kết quả đúng chưa đủ chứng minh nhánh đã chạy

Trong một luồng Reactor, chương trình thường có nhiều đường xử lý:

- Tìm trong cache; khi không có kết quả thì tra cơ sở dữ liệu.
- Gọi dịch vụ chính; khi phát lỗi hợp lệ thì chuyển sang nguồn dự phòng.
- Có command thì thực hiện tác vụ; không có command thì chạy logic mặc định.
- Lấy danh sách từ nguồn ưu tiên; khi nguồn phát rỗng thì lấy danh sách từ nguồn khác.

Ví dụ:

~~~java
Mono<String> result = cacheLookup("A-01")
    .switchIfEmpty(databaseLookup("A-01"));
~~~

Nếu kiểm thử chỉ dùng:

~~~java
StepVerifier.create(result)
    .expectNext("value")
    .verifyComplete();
~~~

thì đã kiểm tra giá trị cuối cùng và tín hiệu complete, nhưng **chưa chứng minh trực tiếp database fallback có được subscribe hay không**. Khi hai nhánh cùng trả giá trị giống nhau, assertion dựa vào output có thể bỏ sót việc chọn nhầm nhánh.

Tình huống khó hơn là cả nhánh chính lẫn dự phòng chỉ trả `Mono<Void>`. Cả hai đều không phát `onNext`, nên:

~~~java
StepVerifier.create(resultVoid).verifyComplete();
~~~

không phân biệt được nhánh nào thật sự được sử dụng.

`PublisherProbe` từ thư viện `reactor-test` được thiết kế để giải quyết vấn đề này. Nó tạo một Publisher được gắn công cụ quan sát và cho phép khẳng định **subscription, request và cancellation** sau khi StepVerifier thực thi kịch bản.

**Trọng tâm của cụm “được đăng ký” trong bài:** một Publisher được *subscribe*. Điều này không đồng nghĩa Publisher đã được tạo, đã có mặt trong chuỗi code, đã nhận demand, đã phát dữ liệu hay đã thực hiện xong business side effect.

## 2. PublisherProbe là gì?

### 2.1. Package và dependency

`PublisherProbe<T>` thuộc:

~~~java
import reactor.test.publisher.PublisherProbe;
~~~

`StepVerifier` thuộc:

~~~java
import reactor.test.StepVerifier;
~~~

Cả hai đều nằm trong dependency **`reactor-test`**, thường dùng ở test scope:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Production code vẫn phụ thuộc `reactor-core` để dùng `Mono`, `Flux` và các toán tử. Không import `PublisherProbe` vào service production chỉ để phân nhánh.

### 2.2. Các factory method

| API | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `PublisherProbe.empty()` | Tạo probe mà Publisher kết thúc rỗng, nhưng vẫn ghi nhận subscription/request/cancel | Test nhánh `Mono<Void>` hoặc kết quả trống |
| `PublisherProbe.of(Publisher<? extends T>)` | Bọc một Publisher thật, giữ tín hiệu nó phát và quan sát cách được sử dụng | Test nhánh dự phòng phải phát giá trị, lỗi, stream hoặc không hoàn tất |
| `probe.mono()` | Lấy bản `Mono<T>` được probe | Gắn vào `Mono.switchIfEmpty`, `Mono.onErrorResume` |
| `probe.flux()` | Lấy bản `Flux<T>` được probe | Gắn vào `Flux.switchIfEmpty` hoặc nhánh nhiều item |

Ví dụ:

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("from-db"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());
~~~

Với `empty()`:

~~~java
PublisherProbe<Void> cleanup = PublisherProbe.empty();
Mono<Void> flow = Mono.<Void>empty()
    .switchIfEmpty(cleanup.mono());
~~~

Trong trường hợp này, cả nguồn chính và fallback đều trống. Nhưng probe vẫn giúp kiểm tra nhánh nào đã được subscribe.

### 2.3. Các assertion

| Assertion | Điều kiện được kiểm tra |
| --- | --- |
| `assertWasSubscribed()` | Probe đã nhận ít nhất một subscription |
| `assertWasNotSubscribed()` | Probe chưa từng được subscribe |
| `assertWasRequested()` | Đã có ít nhất một yêu cầu dữ liệu từ downstream |
| `assertWasNotRequested()` | Chưa có yêu cầu dữ liệu |
| `assertWasCancelled()` | Subscription qua probe đã nhận cancellation |
| `assertWasNotCancelled()` | Không quan sát cancellation |

API cũng có các truy vấn boolean như `wasSubscribed()`, `wasRequested()`, `wasCancelled()` và ở các phiên bản phù hợp có `subscribeCount()`. Tuy nhiên, phần lớn unit test nên dùng các phương thức `assertWas...`: khi sai, chúng ném `AssertionError`.

**Giới hạn rất quan trọng:** `assertWasRequested()` chỉ xác minh đã có yêu cầu dữ liệu, **không kiểm tra chính xác số lượng n**. Nếu cần kiểm tra demand cụ thể hoặc tín hiệu vi phạm Reactive Streams, sử dụng `StepVerifier` kết hợp `TestPublisher` hoặc công cụ đo riêng.

### 2.4. Probe không tạo ra business result

`PublisherProbe.empty()` không phát dữ liệu. Nếu nghiệp vụ phải trả một fallback value, hãy dùng `PublisherProbe.of(Mono.just(value))` thay vì empty.

`PublisherProbe` cũng không bảo đảm “database đã commit”, “HTTP request đã tới server” hay “message đã lưu”. Nó xác nhận **control flow tại ranh giới reactive Publisher**. Cần test tích hợp riêng để chứng minh side effect thực tế.

## 3. Kết hợp StepVerifier và PublisherProbe đúng trình tự

Mô hình chuẩn gồm ba bước:

1. **Arrange:** tạo nguồn chính và probe cho nhánh dự phòng.
2. **Act:** dùng StepVerifier subscribe Publisher cuối, xác minh giá trị/error/completion/cancellation.
3. **Assert branch:** kiểm tra probe sau khi StepVerifier đã kết thúc.

~~~java
PublisherProbe<String> database =
    PublisherProbe.of(Mono.just("db-value"));

Mono<String> output = Mono.<String>empty()
    .switchIfEmpty(database.mono());

StepVerifier.create(output)
    .expectNext("db-value")
    .verifyComplete();

database.assertWasSubscribed();
database.assertWasRequested();
database.assertWasNotCancelled();
~~~

Tại sao phải gọi `verifyComplete()` trước các assertion probe? Vì Reactor lazy: nếu chỉ tạo `Mono` mà chưa subscribe, fallback chưa có cơ hội được chọn.

~~~java
PublisherProbe<String> probe =
    PublisherProbe.of(Mono.just("db"));

Mono<String> output = Mono.<String>empty()
    .switchIfEmpty(probe.mono());

// SAI: chưa có subscriber nào cho output.
probe.assertWasSubscribed(); // AssertionError
~~~

Điểm cuối cùng: hãy sử dụng **probe mới cho mỗi test case**. Nếu dùng chung probe qua nhiều test hoặc nhiều subscription, trạng thái quan sát tích lũy có thể khiến assertion `assertWasSubscribed` xanh vì một lần thực thi khác, che đi bug của scenario hiện tại.

### 3.1. Trạng thái subscription, request, cancel là ba việc khác nhau

~~~text
Assembly       Subscribe         Request(n)           Cancel/Complete
    |              |                 |                      |
    v              v                 v                      v
create probe -> probe.mono() -> source subscribed -> demand -> terminal
    |              |                 |                      |
    |              |                 |                      +-- cancellation?
    |              |                 +-- assertWasRequested
    |              +-- assertWasSubscribed
    +-- chưa chứng minh nhánh đã được dùng
~~~

Một Publisher có thể được subscribe nhưng chưa nhận demand (ví dụ StepVerifier khởi đầu với request 0), hoặc được subscribe rồi cancel trước khi phát dữ liệu. Vì vậy:

- `assertWasSubscribed` trả lời câu hỏi **nhánh có được đăng ký không?**
- `assertWasRequested` trả lời **nhánh có nhận request(n) không?**
- `assertWasCancelled` trả lời **nhánh có bị cancel không?**
- `expectNext` và `verifyComplete` trả lời **subscriber đã thấy những tín hiệu nào?**

Không dùng một assertion thay thế cho tất cả các câu hỏi này.

## 4. switchIfEmpty: nhánh fallback được subscribe khi nào?

### 4.1. Nguồn chính trống: fallback phải được dùng

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("database")
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

`switchIfEmpty` chỉ đăng ký fallback khi upstream **complete mà chưa phát item nào**. Publisher trong `switchIfEmpty` phải có cùng kiểu dữ liệu tương thích với upstream.

### 4.2. Nguồn chính có giá trị: fallback không được subscribe

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result = Mono.just("cache")
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("cache")
    .verifyComplete();

fallback.assertWasNotSubscribed();
fallback.assertWasNotRequested();
fallback.assertWasNotCancelled();
~~~

Đây là test nhánh phủ định rất quan trọng. Chỉ test cache miss mà không test cache hit có thể bỏ sót code vô tình subscribe fallback ngay cả khi đã có cache data.

### 4.3. Upstream bị filter thành rỗng

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result = Mono.just("stale")
    .filter(value -> value.startsWith("valid-"))
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("database")
    .verifyComplete();

fallback.assertWasSubscribed();
~~~

`filter` loại bỏ item làm upstream hoàn tất rỗng. Đó vẫn là nhánh `switchIfEmpty`, dù nguồn ban đầu từng phát một giá trị trước khi filter.

### 4.4. Upstream phát lỗi: switchIfEmpty không chạy

~~~java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("database"));

Mono<String> result =
    Mono.<String>error(new IllegalStateException("cache unavailable"))
        .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectErrorMessage("cache unavailable")
    .verify();

fallback.assertWasNotSubscribed();
~~~

`switchIfEmpty` xử lý **empty completion**, không xử lý `onError`. Nếu muốn fallback khi có lỗi, dùng `onErrorResume` với predicate/exception type phù hợp.

### 4.5. defaultIfEmpty không có Publisher fallback

~~~java
Mono<String> result = Mono.<String>empty()
    .defaultIfEmpty("default");
~~~

`defaultIfEmpty` phát một giá trị thay thế, không subscribe một Publisher phụ. Không có Publisher phụ để gắn `PublisherProbe`. Muốn test operator này, dùng `StepVerifier.expectNext("default")`.

### 4.6. Nguồn được tạo không đồng nghĩa nguồn được subscribe

Một biểu thức Java có thể gọi factory để **tạo** Publisher dự phòng ngay khi lắp ráp chuỗi:

~~~java
Mono<String> alternate = databaseClient.findById("A-01");
Mono<String> result = cacheLookup("A-01")
    .switchIfEmpty(alternate);
~~~

Trong reactive API đúng chuẩn, `findById` thường trả cold Publisher và SQL chưa chạy. Nhưng phương thức tạo Publisher có thể làm công việc eager như tăng bộ đếm, đọc file hoặc gọi API đồng bộ trước khi trả Mono.

Dùng `Mono.defer` khi muốn **hoãn cả việc gọi factory** cho tới lúc nhánh được subscribe:

~~~java
Mono<String> result = cacheLookup("A-01")
    .switchIfEmpty(
        Mono.defer(() -> databaseClient.findById("A-01"))
    );
~~~

`PublisherProbe` quan sát subscription. Nó **không kiểm tra trực tiếp thời điểm factory được gọi**. Muốn test factory thật sự lazy, có thể thêm `AtomicInteger` hoặc spy/mock cho factory, đồng thời dùng probe để xác nhận subscription.

## 5. Trường hợp đặc biệt: Mono<Void> và nhánh dự phòng rỗng

### 5.1. Vì sao giá trị trả về không đủ?

Giả sử một method xử lý command, nếu không có command thì chạy action dự phòng. Cả hai action trả `Mono<Void>` vì chỉ cần hoàn tất, không trả giá trị:

~~~java
Mono<Void> doDefaultAction() { ... }
Mono<Void> process(String command) { ... }
~~~

Khi test chạy:

~~~java
StepVerifier.create(operation)
    .verifyComplete();
~~~

thì dù `process` hay `doDefaultAction` được dùng, kết quả đều là complete. `PublisherProbe<Void>` giải quyết bằng cách quan sát nhánh action.

### 5.2. Cạm bẫy: flatMap trả Mono<Void> rồi switchIfEmpty

Cách viết sai thường gặp:

~~~java
public Mono<Void> processOrFallback(
    Mono<String> source,
    Function<String, Mono<Void>> process,
    Mono<Void> fallback
) {
    return source
        .flatMap(process)
        .switchIfEmpty(fallback);
}
~~~

Dù `source` có phát String và `process` đã chạy, `flatMap(process)` vẫn trở thành `Mono<Void>`, không phát `onNext`. `switchIfEmpty` nhìn thấy empty completion nên **luôn dùng fallback**, kể cả khi command tồn tại.

Cách sửa là giữ lại một marker có giá trị trong nhánh đã xử lý, rồi mới xóa marker ở cuối:

~~~java
public Mono<Void> processOrFallback(
    Mono<String> source,
    Function<String, Mono<Void>> process,
    Mono<Void> fallback
) {
    return source
        .flatMap(value -> process.apply(value).thenReturn(Boolean.TRUE))
        .switchIfEmpty(fallback.thenReturn(Boolean.FALSE))
        .then();
}
~~~

`thenReturn(Boolean.TRUE)` phát marker khi `process` hoàn tất, giúp upstream không còn rỗng. Fallback chỉ được subscribe khi `source` không có command. `then()` cuối cùng biến kết quả Boolean nội bộ thành `Mono<Void>` đúng hợp đồng nghiệp vụ.

### 5.3. Test nhánh dự phòng dùng PublisherProbe.empty()

~~~java
PublisherProbe<Void> fallback = PublisherProbe.empty();

Mono<Void> operation = processOrFallback(
    Mono.empty(),
    command -> Mono.empty(),
    fallback.mono()
);

StepVerifier.create(operation)
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

`PublisherProbe.empty()` không phát item nhưng vẫn ghi nhận nhánh. Đây là lý do probe có giá trị đặc biệt khi hai nhánh cùng trả `Mono<Void>`.

### 5.4. Test nhánh chính và bảo đảm fallback không chạy

~~~java
PublisherProbe<Void> fallback = PublisherProbe.empty();

Mono<Void> operation = processOrFallback(
    Mono.just("approve"),
    command -> Mono.empty(),
    fallback.mono()
);

StepVerifier.create(operation)
    .verifyComplete();

fallback.assertWasNotSubscribed();
fallback.assertWasNotRequested();
~~~

Nếu thay implementation đã sửa bằng implementation sai ở mục 5.2, assertion `assertWasNotSubscribed` sẽ fail — dù `verifyComplete` vẫn pass. Test như vậy phát hiện **bug control flow**, không chỉ kiểm tra output.

### 5.5. Nếu fallback cần phát lỗi

`PublisherProbe.of(Mono.error(new SomeException()))` có thể bọc một fallback phát lỗi. Khi `StepVerifier` kiểm tra error, probe vẫn xác nhận nhánh đó đã được subscribe.

Chỉ dùng `empty()` khi bản thân fallback rỗng/void là đúng hợp đồng. Đừng thay một fallback trả dữ liệu thật bằng empty rồi vô tình thay đổi hành vi của method đang test.

## 6. onErrorResume và những operator khác

### 6.1. Recovery khi gặp lỗi

`onErrorResume` chọn fallback nếu nguồn phát error phù hợp:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Mono.just("backup-ok"));

Mono<String> result =
    Mono.<String>error(new IllegalStateException("service down"))
        .onErrorResume(IllegalStateException.class, error -> backup.mono());

StepVerifier.create(result)
    .expectNext("backup-ok")
    .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
~~~

Nếu nguồn hoàn tất rỗng chứ không lỗi, `onErrorResume` không được gọi:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Mono.just("backup-ok"));

Mono<String> result = Mono.<String>empty()
    .onErrorResume(IllegalStateException.class, error -> backup.mono());

StepVerifier.create(result).verifyComplete();
backup.assertWasNotSubscribed();
~~~

Khi dùng `onErrorResume` với predicate/exception type, test cả lỗi được phép recovery và lỗi không được phép recovery, tránh vô tình che giấu bug.

### 6.2. doOnError không phải nhánh recovery

`doOnError` chỉ quan sát error. Nó không thay error thành fallback. Nếu gọi `onErrorResume` sau đó, mới có nguồn backup để probe.

### 6.3. timeout với fallback

`timeout(Duration, fallback)` có thể chuyển sang alternate Publisher khi timeout xảy ra. `PublisherProbe` giúp xác nhận alternate đã được subscribe, còn `StepVerifier.withVirtualTime` có thể giảm thời gian chờ thực tế.

Cần tạo source **lazily** bên trong supplier được truyền cho `withVirtualTime` để virtual scheduler được cài đặt trước khi operator dùng timer được lắp ráp.

### 6.4. firstWithSignal và các toán tử chọn nhánh khác

Không phải operator nào có nhiều Publisher cũng đợi nguồn trước thất bại mới subscribe nguồn thứ hai. Chẳng hạn, `firstWithSignal` có thể subscribe nhiều candidate rồi chọn publisher phát tín hiệu đầu tiên, cancel các candidate còn lại.

Trong tình huống như vậy, `probe.assertWasSubscribed()` chỉ chứng minh **candidate đã được subscribe**, không chứng minh nó “thắng cuộc” hoặc output cuối cùng đến từ candidate đó. Phải kết hợp assertion dữ liệu, signal và cancellation.

### 6.5. Side effect thật và mock

Probe trả lời câu hỏi “branch Publisher đã được dùng hay chưa?”. Nếu cần xác minh “repository.findById được gọi mấy lần” hoặc “message đã publish thành công”, hãy dùng mock/spy hoặc integration test ở boundary phù hợp.

Đặc biệt, nhiều service method chỉ **tạo cold Mono** khi được gọi. Mock xác minh “method được gọi” và PublisherProbe xác minh “Mono đã được subscribe” là hai bằng chứng **khác nhau**.

## 7. Flux fallback, demand và cancellation

### 7.1. Flux.switchIfEmpty

`Flux.switchIfEmpty` chọn fallback Publisher nếu upstream Flux hoàn tất mà không phát item:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Flux.just("db-1", "db-2"));

Flux<String> output = Flux.<String>empty()
    .switchIfEmpty(backup.flux());

StepVerifier.create(output)
    .expectNext("db-1", "db-2")
    .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
backup.assertWasNotCancelled();
~~~

Nếu upstream có bất kỳ `onNext` nào, fallback **không** được dùng, dù upstream phát ít item hơn dự kiến. `switchIfEmpty` khác `concatWith`: `concatWith` subscribe publisher tiếp theo sau khi nguồn đầu hoàn tất, bất kể nguồn đầu rỗng hay không.

### 7.2. Test backpressure cơ bản

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Flux.just("db-1", "db-2"));

Flux<String> result = Flux.<String>empty()
    .switchIfEmpty(backup.flux());

StepVerifier.create(result, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("db-1")
    .thenRequest(1)
    .expectNext("db-2")
    .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
~~~

Giá trị `0` ở `StepVerifier.create(result, 0)` đặt initial request bằng 0. `thenRequest(1)` cấp demand theo từng bước. Đây là ví dụ phối hợp StepVerifier để kiểm tra output và probe để xác nhận nhánh.

`assertWasRequested()` không chứng minh chính xác “đã request 2”. Nó chỉ ghi nhận có request; số lượng và trình tự demand được kiểm soát trong kịch bản StepVerifier.

### 7.3. Kiểm tra cancellation

Một fallback không phát dữ liệu và không complete:

~~~java
PublisherProbe<String> backup =
    PublisherProbe.of(Flux.never());

Flux<String> result = Flux.<String>empty()
    .switchIfEmpty(backup.flux());

StepVerifier.create(result, 0)
    .expectSubscription()
    .thenRequest(1)
    .thenCancel()
    .verify();

backup.assertWasSubscribed();
backup.assertWasRequested();
backup.assertWasCancelled();
~~~

`Flux.never()` giúp giữ stream hoạt động cho tới khi downstream cancel. Nếu chỉ dùng `Flux.just("value")`, source có thể complete ngay và test sẽ không chứng minh nhánh cancellation.

### 7.4. Không diễn giải quá mức

- `assertWasSubscribed`: nhánh có subscriber.
- `assertWasRequested`: có demand, không xác định số lượng.
- `assertWasCancelled`: có tín hiệu cancellation, không có nghĩa source đã “lỗi”.
- `assertWasNotCancelled`: test không quan sát cancellation, không tự chứng minh connection/database đã đóng.
- `verifyComplete`: Publisher phát complete; không chứng minh side effect transaction đã commit.

Nếu cần kiểm tra chính xác số lượng request(n), dùng `TestPublisher` hoặc test subscriber chuyên biệt; nếu cần resource cleanup, kiểm tra `doFinally` và tích hợp thực tế.

## 8. Ví dụ Maven đầy đủ: Java 17 và reactor-test

Project sau minh họa các trường hợp quan trọng nhất mà không cần khởi động Spring ApplicationContext. Spring Boot parent chỉ cung cấp dependency management cho Reactor/JUnit; lớp nghiệp vụ sử dụng `reactor-core` thuần.

### 8.1. Cấu trúc

~~~text
publisher-probe-demo/
├── pom.xml
├── src/main/java/example/probe/
│   └── LookupPipeline.java
└── src/test/java/example/probe/
    └── LookupPipelineTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>publisher-probe-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`reactor-test` chỉ xuất hiện ở test scope. `spring-boot-starter-test` cung cấp JUnit Jupiter và các tiện ích test. Project không dùng `@SpringBootTest` vì không cần Spring container hoặc HTTP server để kiểm tra các toán tử Reactor.

### 8.3. LookupPipeline.java

~~~java
package example.probe;

import java.util.Objects;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class LookupPipeline {

    public Mono<String> resolve(
        Mono<String> cache,
        Mono<String> database
    ) {
        Objects.requireNonNull(cache, "cache");
        Objects.requireNonNull(database, "database");
        return cache.switchIfEmpty(database);
    }

    public Flux<String> resolveMany(
        Flux<String> cache,
        Flux<String> database
    ) {
        Objects.requireNonNull(cache, "cache");
        Objects.requireNonNull(database, "database");
        return cache.switchIfEmpty(database);
    }

    public Mono<String> recover(
        Mono<String> remote,
        Mono<String> backup
    ) {
        Objects.requireNonNull(remote, "remote");
        Objects.requireNonNull(backup, "backup");

        return remote.onErrorResume(
            IllegalStateException.class,
            error -> backup
        );
    }

    public Mono<Void> processOrFallback(
        Mono<String> command,
        Function<String, Mono<Void>> process,
        Mono<Void> fallback
    ) {
        Objects.requireNonNull(command, "command");
        Objects.requireNonNull(process, "process");
        Objects.requireNonNull(fallback, "fallback");

        return command
            .flatMap(value ->
                process.apply(value).thenReturn(Boolean.TRUE))
            .switchIfEmpty(fallback.thenReturn(Boolean.FALSE))
            .then();
    }
}
~~~

**Giải thích hành vi:**

- `resolve` chỉ subscribe database Publisher khi cache hoàn tất không có item.
- `resolveMany` làm điều tương tự với Flux.
- `recover` chỉ xử lý error thuộc `IllegalStateException`; source rỗng không kích hoạt recovery.
- `processOrFallback` nhận command và action trả `Mono<Void>`. Marker Boolean nội bộ đảm bảo fallback chỉ được subscribe khi command không có item, không bị ảnh hưởng bởi việc `process.apply` trả Void.

Không cần tạo `PublisherProbe` trong lớp này. Probe được đưa vào test như một Publisher thông thường.

### 8.4. LookupPipelineTest.java

~~~java
package example.probe;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class LookupPipelineTest {

    private LookupPipeline pipeline;

    @BeforeEach
    void setUp() {
        pipeline = new LookupPipeline();
    }

    @Test
    void cacheMissSubscribesFallbackMono() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-A01"));

        StepVerifier.create(
                pipeline.resolve(Mono.empty(), database.mono()))
            .expectNext("db-A01")
            .verifyComplete();

        database.assertWasSubscribed();
        database.assertWasRequested();
        database.assertWasNotCancelled();
    }

    @Test
    void cacheHitDoesNotSubscribeFallbackMono() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-unused"));

        StepVerifier.create(
                pipeline.resolve(Mono.just("cache-A01"), database.mono()))
            .expectNext("cache-A01")
            .verifyComplete();

        database.assertWasNotSubscribed();
        database.assertWasNotRequested();
        database.assertWasNotCancelled();
    }

    @Test
    void cacheErrorDoesNotTriggerSwitchIfEmpty() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-unused"));

        StepVerifier.create(
                pipeline.resolve(
                    Mono.error(new IllegalStateException("cache down")),
                    database.mono()))
            .expectErrorMessage("cache down")
            .verify();

        database.assertWasNotSubscribed();
    }

    @Test
    void filteringOutItemTriggersFallback() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("db-valid"));

        Mono<String> source = Mono.just("stale")
            .filter(value -> value.startsWith("valid-"));

        StepVerifier.create(pipeline.resolve(source, database.mono()))
            .expectNext("db-valid")
            .verifyComplete();

        database.assertWasSubscribed();
    }

    @Test
    void monoVoidFallbackIsObservedWhenCommandMissing() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        StepVerifier.create(
                pipeline.processOrFallback(
                    Mono.empty(),
                    command -> Mono.empty(),
                    fallback.mono()))
            .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void monoVoidFallbackIsNotUsedWhenCommandPresent() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        StepVerifier.create(
                pipeline.processOrFallback(
                    Mono.just("approve"),
                    command -> Mono.empty(),
                    fallback.mono()))
            .verifyComplete();

        fallback.assertWasNotSubscribed();
        fallback.assertWasNotRequested();
    }

    @Test
    void onErrorResumeUsesBackupForMatchingError() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Mono.just("backup-ok"));

        StepVerifier.create(
                pipeline.recover(
                    Mono.error(new IllegalStateException("remote down")),
                    backup.mono()))
            .expectNext("backup-ok")
            .verifyComplete();

        backup.assertWasSubscribed();
        backup.assertWasRequested();
    }

    @Test
    void onErrorResumeDoesNotUseBackupForEmptySource() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Mono.just("backup-unused"));

        StepVerifier.create(
                pipeline.recover(Mono.empty(), backup.mono()))
            .verifyComplete();

        backup.assertWasNotSubscribed();
    }

    @Test
    void fluxFallbackHandlesDemand() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Flux.just("db-1", "db-2"));

        StepVerifier.create(
                pipeline.resolveMany(Flux.empty(), backup.flux()), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext("db-1")
            .thenRequest(1)
            .expectNext("db-2")
            .verifyComplete();

        backup.assertWasSubscribed();
        backup.assertWasRequested();
        backup.assertWasNotCancelled();
    }

    @Test
    void cancellingFluxFallbackIsRecorded() {
        PublisherProbe<String> backup =
            PublisherProbe.of(Flux.never());

        StepVerifier.create(
                pipeline.resolveMany(Flux.empty(), backup.flux()), 0)
            .expectSubscription()
            .thenRequest(1)
            .thenCancel()
            .verify();

        backup.assertWasSubscribed();
        backup.assertWasRequested();
        backup.assertWasCancelled();
    }

    @Test
    void deferredFallbackFactoryIsNotCalledOnCacheHit() {
        AtomicInteger factoryCalls = new AtomicInteger();

        PublisherProbe<String> backup = PublisherProbe.of(
            Mono.defer(() -> {
                factoryCalls.incrementAndGet();
                return Mono.just("db-value");
            })
        );

        StepVerifier.create(
                pipeline.resolve(Mono.just("cache-value"), backup.mono()))
            .expectNext("cache-value")
            .verifyComplete();

        backup.assertWasNotSubscribed();
        assertEquals(0, factoryCalls.get());
    }

    @Test
    void deferredFallbackFactoryRunsOnCacheMiss() {
        AtomicInteger factoryCalls = new AtomicInteger();

        PublisherProbe<String> backup = PublisherProbe.of(
            Mono.defer(() -> {
                factoryCalls.incrementAndGet();
                return Mono.just("db-value");
            })
        );

        StepVerifier.create(
                pipeline.resolve(Mono.empty(), backup.mono()))
            .expectNext("db-value")
            .verifyComplete();

        backup.assertWasSubscribed();
        assertEquals(1, factoryCalls.get());
    }
}
~~~

**Điểm quan trọng của bộ test:**

- Hai test cache hit/miss xác minh **hai chiều điều kiện** của `switchIfEmpty`.
- Test cache error chứng minh lỗi không bị nhầm với empty completion.
- Hai test `Mono<Void>` phân biệt nhánh bằng probe, dù kết quả bên ngoài đều chỉ là completion.
- Hai test `onErrorResume` chứng minh recovery xảy ra vì error, không phải source rỗng.
- Test Flux dùng initial request 0 và `thenRequest` để kiểm tra demand.
- Test cancellation sử dụng `Flux.never()` để fallback không hoàn tất trước khi downstream cancel.
- Hai test `Mono.defer` kiểm tra **factory invocation** bằng AtomicInteger, một điều mà PublisherProbe đơn lẻ không khẳng định trực tiếp.

### 8.5. Chạy test

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn test
~~~

Ví dụ kết quả dự kiến nếu tất cả test pass:

~~~text
Tests run: 12, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả kỳ vọng**, không phải log đã chạy. Project không có HTTP controller hoặc `main` cần chạy. Toàn bộ ví dụ là unit tests trực tiếp trên Reactor.

### 8.6. Thực hành làm test thất bại có chủ đích

Sửa `LookupPipeline.processOrFallback` thành phiên bản lỗi:

~~~java
return command
    .flatMap(process)
    .switchIfEmpty(fallback);
~~~

Chạy lại `mvn test`. Test `monoVoidFallbackIsNotUsedWhenCommandPresent` sẽ thất bại vì `fallback.assertWasNotSubscribed()` phát hiện fallback đã bị subscribe dù command có giá trị.

Khôi phục implementation dùng `thenReturn(Boolean.TRUE)` và `thenReturn(Boolean.FALSE)`. Test phải pass trở lại.

Bài tập này chứng minh rõ giá trị của `PublisherProbe`: một test chỉ gọi `verifyComplete()` sẽ không bắt được regression này.

## 9. PublisherProbe so với StepVerifier, TestPublisher và mock

| Công cụ | Trả lời câu hỏi | Phù hợp với |
| --- | --- | --- |
| `StepVerifier` | Publisher phát những onNext, onError, onComplete và phản ứng với demand/cancel ra sao? | Mọi test reactive logic |
| `PublisherProbe` | Một nhánh Publisher đã được subscribe/request/cancel chưa? | switchIfEmpty, onErrorResume và branch selection |
| `TestPublisher` | Có thể chủ động phát tín hiệu và kiểm tra vi phạm/spec, request(n) cụ thể hay không? | Test custom operator, race và backpressure |
| Mockito/mock | Một method/adapter được gọi với tham số gì? | Service/repository invocation |
| Integration test | Side effect thực tế có xảy ra hay không? | DB commit, HTTP request, message publication |

### 9.1. Khi nào probe là lựa chọn tốt nhất?

PublisherProbe đặc biệt tốt khi:

1. Có fallback được biểu diễn bằng một Publisher riêng.
2. Bạn muốn kiểm tra fallback **đã hoặc chưa** được subscribe.
3. Các nhánh cùng kết thúc rỗng (nhất là `Mono<Void>`).
4. Bạn muốn giữ test ít boilerplate hơn việc tạo nhiều `AtomicBoolean` với `doOnSubscribe`/`doOnRequest`/`doOnCancel`.
5. Có thể thay Publisher dự phòng bằng một probe mà không thay semantics nghiệp vụ mong muốn.

### 9.2. Khi nào probe chưa đủ?

- Muốn đo chính xác request(n): kết hợp `TestPublisher` hoặc subscriber test.
- Muốn biết factory được gọi ở assembly time: dùng spy/`AtomicInteger`.
- Muốn khẳng định fallback là nguồn tạo ra onNext: kết hợp StepVerifier và dữ liệu có thể phân biệt.
- Muốn xác nhận request HTTP thực sự tới downstream: dùng MockWebServer, WireMock hoặc test network.
- Muốn xác nhận bản ghi DB đã commit: integration test với DB.
- Muốn kiểm tra nhiều subscription: tạo probe riêng cho mỗi scenario, cân nhắc đo subscription count khi API phiên bản hỗ trợ và có yêu cầu test riêng.

### 9.3. Không dùng TestPublisher chỉ để làm probe

`TestPublisher` cũng có liên quan đến PublisherProbe API nhưng đòi hỏi quản lý tín hiệu phát. Với bài toán chỉ cần biết một nhánh được subscribe, tạo `PublisherProbe.empty()` hoặc `PublisherProbe.of(source)` sẽ ngắn gọn và ít rủi ro hơn.

Nếu dùng TestPublisher để kiểm tra assertion sau terminal signal, cần hiểu chế độ violation/cleanup của nó. Không nên chọn TestPublisher chỉ vì muốn thử `assertWasSubscribed`.

## 10. Những lỗi dễ gặp và cách khắc phục

**Lỗi 1 — Chỉ tạo Mono mà không subscribe.** Probe không quan sát gì. Luôn chạy `StepVerifier...verify()` trước khi assert probe.

**Lỗi 2 — Nhầm “đã được tạo” với “đã subscribe”.** `switchIfEmpty(fallback)` có thể được lắp ráp khi fallback chưa được đăng ký. Probe kiểm tra subscription, không kiểm tra factory invocation.

**Lỗi 3 — Chỉ kiểm tra fallback được subscribe mà quên nhánh ngược.** Test cả cache miss lẫn cache hit bằng `assertWasSubscribed` và `assertWasNotSubscribed`.

**Lỗi 4 — Dùng switchIfEmpty cho lỗi.** `switchIfEmpty` chỉ xử lý complete rỗng. Dùng `onErrorResume` nếu cần recovery từ onError.

**Lỗi 5 — Dùng onErrorResume để xử lý Mono.empty.** Empty không phải error. Dùng `switchIfEmpty` hoặc `defaultIfEmpty`.

**Lỗi 6 — Dùng PublisherProbe.empty() cho fallback phải trả dữ liệu.** Probe empty sẽ đổi semantics. Dùng `PublisherProbe.of(Mono.just(value))`.

**Lỗi 7 — Hiểu sai Mono<Void>.flatMap.** Khi processor trả Mono<Void>, upstream sau flatMap rỗng, fallback có thể bị gọi sai. Dùng marker `thenReturn(...)` trước khi switchIfEmpty.

**Lỗi 8 — Assert probe trước StepVerifier.verifyComplete.** Chuỗi lazy chưa chạy. Đợi verification hoàn tất rồi kiểm tra nhánh.

**Lỗi 9 — Tái sử dụng một probe qua nhiều tests.** Trạng thái subscription tích lũy có thể làm test false positive. Mỗi case tạo probe mới.

**Lỗi 10 — Nghĩ assertWasRequested kiểm tra số phần tử.** Nó chỉ ghi nhận đã có request. Dùng StepVerifier demand scripting hoặc TestPublisher khi cần số lượng.

**Lỗi 11 — Nghĩ assertWasSubscribed chứng minh fallback tạo output.** Một Publisher có thể được subscribe rồi cancel ngay. Cần kiểm tra output/signal bằng StepVerifier.

**Lỗi 12 — Dùng Flux.just cho test cancellation nhưng Flux complete trước cancel.** Chọn `Flux.never()` để giữ subscription hoạt động tới khi StepVerifier phát cancel.

**Lỗi 13 — Dùng StepVerifier.thenCancel rồi lại expectComplete.** Cancellation là terminal expectation của kịch bản verification; không yêu cầu complete sau cancel.

**Lỗi 14 — Quên request khi initial request = 0.** Với nguồn cần demand để phát item, StepVerifier có thể chờ mãi. Dùng `thenRequest(n)` phù hợp.

**Lỗi 15 — Kiểm tra nhánh sau một operator subscribe nhiều candidate.** Với `firstWithSignal`, subscribe không chứng minh nhánh thắng. Kiểm tra thêm tín hiệu và cancellation.

**Lỗi 16 — Dùng probe để khẳng định DB commit.** Probe chỉ thấy subscription/demand/cancel. Phải query DB hoặc dùng integration test.

**Lỗi 17 — Bỏ qua sự khác nhau giữa assembly và subscription.** Factory có side effect eager có thể chạy dù fallback không subscribe. Dùng `Mono.defer` và test AtomicInteger/spy.

**Lỗi 18 — Dùng subscribe() trong unit test rồi assert tức thì.** Async Publisher có thể chưa phát hoặc chưa tới fallback. StepVerifier cung cấp kịch bản và điểm kết thúc rõ ràng.

**Lỗi 19 — Nhầm lỗi assertion của StepVerifier và PublisherProbe.** StepVerifier kiểm tra tín hiệu, PublisherProbe kiểm tra nhánh; khi fail đọc cả hai để xác định lỗi data hay control flow.

**Lỗi 20 — Cố gắn probe vào production.** `reactor-test` thuộc test scope; logic production nên nhận cold Publisher/Publisher abstractions chứ không phụ thuộc công cụ kiểm thử.

## 11. Checklist viết test PublisherProbe

1. Nhánh nào cần được chứng minh có hoặc không subscribe?
2. Nhánh được chọn vì empty, error, timeout hay một điều kiện khác?
3. Probe dùng `empty()` hay `of(source)` để giữ đúng tín hiệu của fallback?
4. Đã gắn `probe.mono()` hoặc `probe.flux()` vào đúng chỗ chưa?
5. Đã chạy `StepVerifier.verifyComplete/verify/thenCancel` trước assertion probe?
6. Test có assert output/error/complete phù hợp với hợp đồng method?
7. Có cả test positive và negative cho fallback?
8. Có kiểm tra `assertWasRequested` hoặc cancel khi các thuộc tính đó có ý nghĩa?
9. Có tránh dùng một probe qua nhiều scenario không?
10. Với Mono<Void>, có tránh bug `flatMap(...).switchIfEmpty(...)` không?
11. Với source/error, có phân biệt `switchIfEmpty` và `onErrorResume`?
12. Có cần kiểm tra factory invocation ngoài subscription không?
13. Test cần đo demand chính xác hay chỉ cần biết đã request?
14. Có operator nào subscribe nhiều candidate rồi cancel nhánh không được chọn?
15. Nếu có side effect thật, đã có integration test riêng chưa?

## 12. Bài tập tự kiểm tra

1. `PublisherProbe` thuộc module nào? **reactor-test**.
2. Import là gì? **`reactor.test.publisher.PublisherProbe`**.
3. Mục đích chính của probe? **Quan sát subscription/request/cancellation của một Publisher nhánh.**
4. `PublisherProbe.empty()` phát gì? **Không có onNext; chỉ complete nhưng ghi nhận tương tác.**
5. `PublisherProbe.of(Mono.just("x"))` khác empty ở đâu? **Giữ tín hiệu và giá trị từ Publisher bọc bên trong.**
6. API lấy Mono từ probe? **`probe.mono()`.**
7. API lấy Flux từ probe? **`probe.flux()`.**
8. Assertion nhánh đã subscribe? **`assertWasSubscribed()`.**
9. Assertion nhánh không subscribe? **`assertWasNotSubscribed()`.**
10. Assertion nhánh có nhận demand? **`assertWasRequested()`.**
11. Assertion nhánh bị cancel? **`assertWasCancelled()`.**
12. Phải chạy StepVerifier.verify trước assertion probe vì sao? **Publisher lazy và chưa có subscription trước verify.**
13. `switchIfEmpty` chuyển fallback khi nào? **Nguồn complete mà không emit onNext.**
14. `switchIfEmpty` xử lý onError không? **Không; dùng onErrorResume.**
15. `onErrorResume` có chạy khi nguồn complete rỗng không? **Không.**
16. Vì sao Mono<Void>.flatMap(...).switchIfEmpty(...) có thể gọi fallback sai? **Vì Mono<Void> không phát item nên downstream thấy nguồn rỗng.**
17. Cách giữ marker khi process là Mono<Void>? **`process(value).thenReturn(Boolean.TRUE)` trước switchIfEmpty rồi `then()` cuối.**
18. Probe có kiểm tra chính xác request(7) không? **Không; chỉ kiểm tra có request, dùng công cụ khác nếu cần count.**
19. Flux.never hữu ích gì khi test? **Giữ Publisher mở để quan sát cancellation.**
20. Subscribe một candidate có chứng minh candidate thắng firstWithSignal không? **Không, nhiều candidate có thể được subscribe rồi cancel.**
21. Probe có chứng minh database commit không? **Không; dùng integration test.**
22. Vì sao nên kết hợp Mono.defer với probe? **Hoãn việc tạo nguồn fallback đến subscription và tách kiểm tra factory invocation khỏi subscription.**

## 13. Tóm tắt và tài liệu tham khảo

- `PublisherProbe` là tiện ích của `reactor-test` để xác minh một nhánh Publisher **được hoặc không được subscribe**, đã nhận request và có bị cancel.
- Gắn `probe.mono()`/`probe.flux()` vào nhánh cần quan sát; chạy `StepVerifier` đến terminal expectation rồi mới assert probe.
- `PublisherProbe.empty()` rất phù hợp với `Mono<Void>` khi output của hai nhánh không phân biệt được.
- `PublisherProbe.of(source)` bọc Publisher thật để giữ onNext/onError/onComplete trong test.
- `switchIfEmpty` chạy khi nguồn complete rỗng; `onErrorResume` chạy với error; hai điều kiện khác nhau.
- `Mono<Void>.flatMap(...).switchIfEmpty(...)` có thể kích hoạt fallback sai; dùng marker `thenReturn` nếu cần phân biệt nhánh chính đã xử lý.
- `assertWasRequested` không đo số lượng demand; `assertWasSubscribed` không chứng minh nghiệp vụ đã commit.
- Với `Flux`, StepVerifier có thể phát `thenRequest(n)` và `thenCancel()` để điều khiển và quan sát lifecycle.
- Test cả nhánh positive/negative; tạo probe mới cho mỗi test và dùng integration test cho side effect thực tế.

**Tài liệu tham khảo chính thức:**

1. [Project Reactor Reference — Testing, Checking the Execution Path with PublisherProbe](https://projectreactor.io/docs/core/3.7.16/reference/testing.html): kịch bản switchIfEmpty, Mono<Void> và ba assertion chính.
2. [Project Reactor Javadoc — PublisherProbe](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): empty, of, mono, flux, assertWasSubscribed/Requested/Cancelled.
3. [Project Reactor Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): create, verify, expectNext, thenRequest, thenCancel.
4. [Project Reactor Javadoc — Mono.switchIfEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): fallback khi completion không có item.
5. [Project Reactor Javadoc — Flux.switchIfEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): fallback Publisher cho Flux rỗng.
6. [Project Reactor Reference — Testing and TestPublisher](https://projectreactor.io/docs/core/release/reference/testing.html): phân biệt StepVerifier, PublisherProbe và TestPublisher.
7. [Spring Boot 3.5 — Reference](https://docs.spring.io/spring-boot/3.5/reference/): quản lý dependency JUnit/Reactor và Maven plugin trong project mẫu.
