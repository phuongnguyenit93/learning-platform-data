# Tránh block() và subscribe() thủ công trong luồng xử lý yêu cầu

## 1. Mục tiêu và phạm vi

Trong ứng dụng **Spring Boot WebFlux**, Controller thường trả về **Mono<T>** (không có hoặc có một giá trị) hay **Flux<T>** (không có, có một hoặc nhiều giá trị). Thay vì bắt luồng HTTP đợi kết quả, chúng ta mô tả một **chuỗi xử lý reactive (pipeline)** rồi trả Publisher cho framework.

Hai lỗi thiết kế thường phá vỡ cách hoạt động đó:

1. Gọi **block()** trong Controller, WebFilter hay hàm callback đang thực thi trên event loop để đợi dữ liệu đồng bộ.
2. Gọi **subscribe() thủ công** ngay trong luồng xử lý request, biến một phần công việc thành nhánh tự chạy, tách khỏi request chính.

Quy tắc thực hành: **trong đường xử lý request WebFlux, hãy kết hợp Publisher bằng operator và trả Publisher đó cho Spring WebFlux; để framework quản lý subscription, response, lỗi và cancellation**. Khi phải tích hợp API đồng bộ/blocking, cô lập nó trên scheduler phù hợp và trả lại Mono/Flux thay vì đợi kết quả bằng block().

Phạm vi bài là **thực thi reactive cho HTTP request**, đặc biệt với Reactor và WebFlux trên Reactor Netty. Spring MVC có thể dùng WebClient hoặc trả Mono theo cơ chế thích ứng riêng; không nên áp các kết luận về Netty event loop một cách máy móc cho mọi ứng dụng Spring MVC.

## 2. Ai thực sự thực thi Mono/Flux?

Publisher như Mono/Flux mô tả nguồn dữ liệu và các phép biến đổi; phần lớn pipeline là **lazy**: chỉ khi có subscription thì nguồn mới bắt đầu chạy. Theo Reactive Streams, dữ liệu/lỗi/hoàn tất được trao đổi qua các tín hiệu:

- **onSubscribe:** đăng ký subscriber với nguồn; có thể yêu cầu dữ liệu qua request(n).
- **onNext:** phát giá trị; Mono có tối đa một onNext.
- **onError:** kết thúc với lỗi; không có onComplete sau đó.
- **onComplete:** kết thúc thành công; không có onError sau đó.
- **cancel:** subscriber yêu cầu ngừng xử lý khi không cần thêm dữ liệu; việc dừng ngay lập tức còn tùy nguồn và tài nguyên ngoài.

Ví dụ với Controller chuẩn:

~~~java
@GetMapping("/products/{id}")
Mono<ProductDto> getProduct(@PathVariable String id) {
    return productService.findById(id)
            .map(ProductDto::from);
}
~~~

Đây là **đoạn minh họa**, giả định ProductDto và productService đã có. Controller **không** gọi block() hoặc subscribe(). Spring WebFlux nhận Mono, thiết lập subscriber phù hợp với HTTP response, xử lý tín hiệu, áp dụng cơ chế ghi response và dừng/cancel khi cần. Việc subscription cuối cùng nằm ở framework.

Luồng khái niệm:

~~~text
HTTP request
    |
    v
WebFlux gọi phương thức Controller
    |
    v
Controller lắp ghép và TRẢ VỀ Mono/Flux
    |
    v
WebFlux gắn Subscriber và yêu cầu dữ liệu
    |
    +--> nguồn I/O không chặn (WebClient, reactive repository...)
    |       |
    |       +--> map / flatMap / filter / timeout / onErrorResume
    |                       |
    +<---------------------+
    |
    v
Ghi HTTP response, complete/error hoặc xử lý cancellation
~~~

**Lắp ghép chuỗi không phải chờ giá trị.** Ví dụ Mono.just("A").map(String::toLowerCase) là một Publisher mô tả phép biến đổi; không cần block() để lấy giá trị nhằm đưa vào operator tiếp theo.

**Chú ý:** một số thao tác diễn ra ngay lúc *tạo* Publisher: biểu thức đối số của Mono.just(...) được đánh giá trước, nên Mono.just(legacyDao.findById(id)) vẫn có thể gọi DB đồng bộ **ngay trong Controller**. Dùng Mono.defer hoặc Mono.fromCallable khi cần trì hoãn lời gọi cho tới lúc subscription.

## 3. Vì sao block() trong request handler nguy hiểm?

**block()** đăng ký vào Publisher và **đợi** đến khi có kết quả, lỗi hoặc hoàn tất. Nó biến một điểm bất đồng bộ thành lời gọi đồng bộ tại thread gọi block(). Các biến thể blockOptional(), blockFirst(), blockLast(), toIterable() và toStream() cũng có thể gây chờ tương tự.

Với Spring WebFlux chạy trên Reactor Netty, số **event-loop thread** thường nhỏ và được dùng để điều phối nhiều kết nối. Nếu một callback giữ event loop khi đợi I/O, những request khác có thể bị chậm dù CPU chưa cao.

Reactor còn nhận diện nhiều thread đánh dấu **NonBlocking**: gọi các API blocking của Reactor như block() trong đó có thể ném **IllegalStateException**. Thông điệp lỗi thường nhắc rằng thao tác blocking không được hỗ trợ trên thread hiện tại; tên thread cụ thể phụ thuộc môi trường. Không dựa vào exception như một cơ chế kiểm soát đầy đủ: lời gọi JDBC blocking, Thread.sleep() hay CompletableFuture.join() vẫn có thể gây nghẽn mà không ném exception của Reactor.

### 3.1. Ví dụ sai: lấy kết quả WebClient bằng block()

~~~java
// SAI trong WebFlux request handler; chỉ là đoạn minh họa.
@GetMapping("/profiles/{id}")
ProfileDto profile(@PathVariable String id) {
    return webClient.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(ProfileDto.class)
            .block();
}
~~~

Hệ quả:

- Controller giữ thread cho đến khi HTTP downstream phản hồi.
- Trên event loop NonBlocking, block() có thể ném IllegalStateException.
- Tăng timeout không làm cách xử lý thành non-blocking.
- Việc dùng block() tạo thêm một điểm subscribe ẩn trong code, thay vì để framework quản lý chain.
- Nếu chạy trên thread được phép block, ứng dụng vẫn đánh mất lợi ích tiết kiệm thread trong thời gian chờ.

### 3.2. Cách đúng: trả Mono để WebFlux subscribe

~~~java
// ĐÚNG trong WebFlux; giả định đã inject WebClient.
@GetMapping("/profiles/{id}")
Mono<ProfileDto> profile(@PathVariable String id) {
    return webClient.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(ProfileDto.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

Phải import java.time.Duration, reactor.core.publisher.Mono cùng các type được dùng. **Đây là đoạn code trong Controller đã có WebClient**, chưa phải một file Java tự biên dịch. WebClient tạo publisher HTTP, còn framework sẽ subscribe khi xử lý response.

Đặt timeout theo yêu cầu nghiệp vụ; timeout ở cấp Mono là một lớp bảo vệ nhưng cũng cần cấu hình thời gian kết nối/đọc ở HTTP client. Với WebClient.retrieve(), status 4xx/5xx theo mặc định phát tín hiệu lỗi kiểu WebClientResponseException; xử lý mapping lỗi theo API contract thay vì biến tất cả thành 200 hoặc trả null.

### 3.3. Không làm mất tính reactive bằng cách chuyển lỗi chỗ khác

Các cách sau **không** giải quyết vấn đề:

- **Mono.just(blockingCall())**: blockingCall() chạy ngay ở thời điểm tạo Mono.
- **Mono.just(publisher.block())**: vẫn block trên thread hiện tại, trước khi trả Mono.
- **Mono.fromCallable(() -> publisher.block())** nhưng không đưa sang scheduler thích hợp: khi được subscribe, callback vẫn có thể block event loop.
- **Mono.fromCallable(() -> legacyCall()).subscribeOn(Schedulers.parallel())**: parallel phục vụ công việc CPU/ngắn hạn, không dành cho lời gọi I/O blocking.
- **new Thread(...).start() trong mỗi request**: bỏ qua kiểm soát scheduler/queue, khó quan sát, khó hủy và dễ cạn tài nguyên.
- **CompletableFuture.get()/join() hoặc Thread.sleep() trong map/flatMap**: vẫn chặn thread đang chạy callback.

Nếu toàn bộ API được gọi đã hỗ trợ non-blocking, **hãy compose nó trực tiếp**. Nếu nguồn thực sự blocking không thể thay, dùng mẫu cô lập ở phần 7.

## 4. Vì sao subscribe() thủ công trong request handler cũng sai?

**subscribe() không giống subscribeOn().** subscribe() là một thao tác cuối (*terminal operation*) bắt đầu một subscription mới. subscribeOn(scheduler) chỉ cấu hình nơi subscription của nguồn sẽ được thực hiện **khi một subscriber thực sự đến**.

Trong WebFlux, gọi subscribe() tại Controller/Service thường tạo một công việc **nằm ngoài Publisher được trả về cho HTTP framework**.

### 4.1. Ví dụ sai: tự khởi chạy side effect

~~~java
// SAI: ví dụ không độc lập, giả định auditService trả Mono<Void>.
@PostMapping("/orders/{id}/confirm")
Mono<String> confirm(@PathVariable String id) {
    auditService.recordConfirmation(id).subscribe();
    return Mono.just("confirmed");
}
~~~

API có thể báo **confirmed** trước khi ghi audit hoàn tất; lỗi ghi audit không tự chuyển thành lỗi HTTP; request bị cancel không mặc nhiên cancel nhánh audit; và nếu code sau đó cũng trả lại cùng Publisher, có nguy cơ **subscribe hai lần**, làm trùng tác vụ với nguồn cold.

Kể cả khi subscribe() chạy nhanh hoặc nguồn đồng bộ hoàn thành ngay, mẫu này vẫn không biểu đạt được quan hệ “audit phải thành công rồi mới xác nhận”. **Fire-and-forget** cần cơ chế nghiệp vụ độc lập như queue/job/outbox được quản lý, không nên tự tạo bằng subscribe() trong Controller.

### 4.2. Cách đúng: nối side effect vào cùng một chain

~~~java
// ĐÚNG: response chỉ hoàn tất sau khi audit thành công.
@PostMapping("/orders/{id}/confirm")
Mono<String> confirm(@PathVariable String id) {
    return auditService.recordConfirmation(id)
            .thenReturn("confirmed");
}
~~~

**thenReturn(value)** đợi nguồn upstream hoàn tất thành công rồi phát value. Nếu upstream lỗi, chain phát lỗi thay vì ngầm xác nhận thành công. Nếu mục tiêu là trả response rỗng chỉ sau khi side effect thành công, trả **Mono<Void>** bằng then() hoặc trực tiếp Mono<Void> từ service.

### 4.3. Subscribe bên trong doOnNext còn nguy hiểm hơn

~~~java
// SAI: side effect reactive trở thành nhánh độc lập.
return repository.findById(id)
        .doOnNext(user -> auditService.save(user).subscribe())
        .map(UserDto::from);
~~~

~~~java
// ĐÚNG: ghép nhánh audit vào luồng dữ liệu.
return repository.findById(id)
        .flatMap(user ->
                auditService.save(user)
                        .thenReturn(UserDto.from(user))
        );
~~~

Ở hai đoạn này giả định repository.findById trả Mono<User>, auditService.save trả Mono<Void> và UserDto.from là phép chuyển đổi đồng bộ, nhẹ. **doOnNext()** thích hợp cho logging, counters hoặc quan sát tín hiệu **đồng bộ và nhanh**; nó **không đợi Publisher** được tạo bên trong callback. Muốn chờ thao tác async, dùng **flatMap**, **concatMap**, **then**, **when** tùy cấu trúc dữ liệu và thứ tự cần bảo toàn.

## 5. Bảng chọn operator thay cho block()/subscribe()

| Mục tiêu | Operator thường dùng | Lưu ý |
| --- | --- | --- |
| Chuyển một giá trị bằng hàm đồng bộ, nhanh | map | Không gọi I/O blocking trong mapper |
| Hàm chuyển một giá trị thành Mono/Flux khác | flatMap | Kết nối chain, cho framework xử lý subscribe |
| Duy trì thứ tự các tác vụ async theo phần tử | concatMap | Phù hợp khi thứ tự có ý nghĩa, throughput có thể thấp hơn |
| Chờ hoàn tất A rồi chạy B, bỏ qua giá trị A | then(B) hoặc thenMany(B) | Nếu A lỗi, B không chạy |
| Chờ A hoàn tất rồi trả một giá trị cố định | thenReturn(value) | Có ích với Mono<Void> của thao tác ghi |
| Chạy nhiều Mono cùng cần kết quả | Mono.zip(...) | Với Mono.empty(), zip có thể kết thúc rỗng; xem semantics |
| Chờ nhiều tác vụ hoàn tất mà không cần giá trị | Mono.when(...) | Lỗi được truyền về chain; cân nhắc tác động song song |
| Giá trị rỗng cần fallback | defaultIfEmpty hoặc switchIfEmpty | switchIfEmpty(Mono.defer(...)) khi fallback cần lazy |
| Ghi log/metrics khi có tín hiệu | doOnNext, doOnError, doFinally | Không tự xử lý lỗi nếu chỉ gọi doOnError |
| Chuyển tín hiệu lỗi thành Publisher khác | onErrorResume | Chỉ fallback với loại lỗi mong muốn |
| Giới hạn thời gian chờ của pipeline | timeout | Timeout gây cancellation tốt nhất có thể; bên ngoài chưa chắc rollback |
| Quản lý tài nguyên cần đóng | using/usingWhen | Cleanup gắn với success, error và cancel theo hợp đồng operator |

Ví dụ thứ tự thao tác:

~~~java
// Ví dụ cục bộ: cả ba service method đều trả Mono.
Mono<Receipt> confirm(String orderId) {
    return orderService.reserve(orderId)
            .flatMap(reservation ->
                    paymentService.charge(reservation)
                            .flatMap(payment ->
                                    auditService.save(payment)
                                            .thenReturn(new Receipt(payment.id()))
                            )
            );
}
~~~

Đây là **đoạn minh họa, chưa phải chương trình độc lập**. Nó biểu thị “reserve → charge → audit → receipt” trong **một subscription**. Dù đã compose đúng, chuỗi này **không tự tạo transaction phân tán** giữa các service. Nếu có side effect quan trọng cần idempotency/compensation/outbox và xử lý partial failure theo yêu cầu nghiệp vụ.

## 6. Thực hành chạy được: WebFlux Controller không gọi block()/subscribe()

Ứng dụng minh họa sử dụng **Spring Boot 3.3.13, Java 17+, Spring WebFlux và Reactor Netty**. Nó nhận POST để tạo một lời chào và tăng bộ đếm audit trong cùng pipeline, rồi có GET để xem bộ đếm. Dùng dữ liệu in-memory giúp tập trung vào kỹ thuật subscription. Trong production, ghi audit bền vững cần kho dữ liệu/hàng đợi phù hợp.

### 6.1. Cấu trúc dự án

~~~text
reactive-request-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/reactive/
    │   └── ReactiveRequestDemoApplication.java
    └── test/java/com/example/reactive/
        └── AuditServiceTest.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-request-demo</artifactId>
    <version>1.0.0</version>
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
~~~

**src/main/java/com/example/reactive/ReactiveRequestDemoApplication.java**:

~~~java
package com.example.reactive;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveRequestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveRequestDemoApplication.class, args);
    }
}

@Service
class AuditService {
    private final AtomicInteger count = new AtomicInteger();

    Mono<Void> record(String name) {
        return Mono.fromRunnable(() -> {
            count.incrementAndGet();
        }).then();
    }

    int count() {
        return count.get();
    }
}

@RestController
class GreetingController {
    private final AuditService auditService;

    GreetingController(AuditService auditService) {
        this.auditService = auditService;
    }

    @PostMapping("/api/greetings/{name}")
    Mono<String> greet(@PathVariable String name) {
        return Mono.just(name)
                .delayElement(Duration.ofMillis(100))
                .map(value -> "Xin chào, " + value + "!")
                .flatMap(greeting ->
                        auditService.record(name).thenReturn(greeting)
                );
    }

    @GetMapping("/api/audit-count")
    Mono<Integer> auditCount() {
        return Mono.fromSupplier(auditService::count);
    }
}
~~~

Giải thích:

1. **POST** được dùng vì việc ghi audit là side effect, không phù hợp với ý nghĩa an toàn của GET.
2. Mono.just(name) tạo một nguồn giá trị; delayElement mô phỏng hoàn tất bất đồng bộ với scheduler của Reactor, **không dùng Thread.sleep hay block()**.
3. map tạo nội dung lời chào từ giá trị đã được phát.
4. flatMap kết nối Mono<Void> từ AuditService.record với giá trị response qua thenReturn; framework nhận **một Mono<String> duy nhất** để subscribe.
5. AuditService.record dùng Mono.fromRunnable nên **tăng bộ đếm lúc có subscription**, thay vì khi chỉ gọi record(). Thao tác AtomicInteger nhanh, không blocking; in-memory counter chỉ phục vụ minh họa.
6. auditCount dùng Mono.fromSupplier để đọc giá trị hiện tại lúc có subscription. Đây là GET không thay đổi trạng thái.

### 6.2. Kiểm tra lazy execution với StepVerifier

**src/test/java/com/example/reactive/AuditServiceTest.java**:

~~~java
package com.example.reactive;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class AuditServiceTest {

    @Test
    void auditRunsOnlyWhenSubscribed() {
        AuditService service = new AuditService();

        Mono<Void> pending = service.record("An");
        assertEquals(0, service.count());

        StepVerifier.create(pending)
                .verifyComplete();

        assertEquals(1, service.count());
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Kết quả mong đợi: **build thành công, một test đi qua**, không có AssertionError. Maven có thể in nhiều dòng log khác nhau theo phiên bản và máy; không nên cố định toàn bộ stdout của Maven. Test này chứng minh side effect **chưa chạy khi tạo Mono**, và **chạy khi có subscription** thông qua StepVerifier. Ghi nhớ: mỗi lần subscribe thêm vào một cold Publisher có thể kích hoạt thao tác thêm lần nữa.

### 6.3. Chạy HTTP end-to-end

Chạy trong thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Sau khi ứng dụng lắng nghe cổng mặc định 8080, trong terminal khác gọi **một lần duy nhất**:

~~~bash
curl -s -X POST http://localhost:8080/api/greetings/An
curl -s http://localhost:8080/api/audit-count
~~~

Body kết quả tương ứng ở một tiến trình ứng dụng **mới khởi động** và chưa nhận POST khác:

~~~text
Xin chào, An!
1
~~~

Với PowerShell trên Windows, dùng curl.exe nếu alias curl không hỗ trợ tham số. Cả hai response đều phụ thuộc server đang hoạt động, request đầu hoàn tất thành công, và không có yêu cầu đồng thời thay đổi bộ đếm. Nếu gọi POST lần thứ hai, số audit tăng thành 2.

**Điểm học được:** Controller không cần subscribe() để đảm bảo ghi audit diễn ra; khi HTTP framework subscribe vào Mono trả về, toàn bộ pipeline được thực thi, bao gồm record().

## 7. Khi bắt buộc phải dùng thư viện blocking

Một số hệ thống còn dùng **JDBC**, SDK mạng đồng bộ, thư viện đọc file blocking hoặc mã legacy. Chúng không trở nên non-blocking chỉ vì được bao bởi Mono.

### 7.1. Cách sai: gọi blocking trước khi tạo Publisher

~~~java
// SAI: legacyDao.findById(id) chạy ngay trên thread gọi phương thức.
Mono<Customer> find(String id) {
    return Mono.just(legacyDao.findById(id));
}
~~~

Với Mono.just, phép gọi legacyDao.findById(id) được đánh giá **ngay lập tức**. Nếu nó mất 2 giây, Controller có thể giữ event loop 2 giây trước khi trả Mono.

### 7.2. Cách đúng có giới hạn: fromCallable + boundedElastic

~~~java
// Mẫu tích hợp bên trong service có legacyDao; chưa phải chương trình độc lập.
Mono<Customer> find(String id) {
    return Mono.fromCallable(() -> legacyDao.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Import Mono và reactor.core.scheduler.Schedulers. **Mono.fromCallable** trì hoãn lời gọi đồng bộ tới lúc subscription. **subscribeOn(Schedulers.boundedElastic())** chuyển phần tạo nguồn/callable sang nhóm worker phù hợp với mã blocking, thay vì giữ event loop. Đây là **giải pháp chuyển tiếp**; khi có API non-blocking phù hợp (R2DBC hoặc async HTTP client thật sự), thường nên sử dụng trực tiếp.

Cần nêu đúng giới hạn:

- boundedElastic **có giới hạn** số worker và số tác vụ xếp hàng; nó không cung cấp sức chịu tải vô hạn.
- Bản thân JDBC/SDK vẫn blocking, vẫn tốn thread của boundedElastic và connection pool; phải đặt **timeout ở driver/client**, giới hạn concurrency và kiểm soát số replica.
- **Cancellation của reactive chain không đảm bảo dừng tức thì lời gọi blocking đang chạy**; các API blocking có thể không đáp ứng interrupt. Không coi timeout ở Mono là thay thế cleanup/timeout của nguồn.
- Không dùng Schedulers.parallel() hoặc Schedulers.single() cho I/O blocking.
- Không tạo scheduler tùy tiện cho từng request. Dùng tài nguyên có quản lý và giám sát queue/threads.

### 7.3. subscribeOn và publishOn khác nhau

- **subscribeOn(scheduler)** tác động lên quá trình subscribe và các tín hiệu yêu cầu về phía nguồn; thường đặt **ngay sau nguồn blocking** để dễ đọc.
- **publishOn(scheduler)** đổi nơi xử lý **các tín hiệu phía sau operator**; không đảo ngược phần blocking đã chạy ở phía trước. Dùng khi muốn thay đổi execution context của một đoạn chain.
- **Không operator nào tự biến thư viện blocking thành non-blocking**. Chúng chỉ thay đổi vị trí thread chạy công việc.

Đặc biệt, đừng đọc chữ “subscribe” trong subscribeOn rồi tưởng rằng nó **khởi chạy** pipeline. Không có subscriber cuối, source vẫn thường chưa được thực thi.

## 8. Thiết kế HTTP → Service → WebClient → Repository

Một pipeline có thể được giữ reactive từ Controller đến các lớp sau:

~~~java
// Đoạn ghép minh họa; client, repository và DTO đã được khai báo ở lớp của bạn.
Mono<ProfileView> getProfile(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new ProfileNotFoundException(id)))
            .flatMap(profile ->
                    externalClient.getScore(profile.externalId())
                            .map(score -> new ProfileView(profile, score))
            )
            .timeout(Duration.ofSeconds(3))
            .doOnError(error -> log.warn("Cannot get profile {}", id, error));
}
~~~

Ở đây giả định repository và externalClient dùng nguồn reactive thực sự. **flatMap** nối lời gọi HTTP downstream vào một chain; **timeout** đặt ngân sách chờ tổng; **doOnError** chỉ ghi log, không nuốt lỗi. Nếu cần đổi mã lỗi HTTP, hãy xử lý tại Controller advice/WebExceptionHandler hoặc dùng onErrorMap/onErrorResume đúng kiểu lỗi.

### 8.1. Lưu ý về tín hiệu rỗng

Mono.empty() nghĩa là **hoàn tất không có phần tử**, khác với giá trị null hoặc một lỗi. Nếu map được áp dụng cho Mono.empty(), mapper **không chạy**. Nếu sự kiện “không tìm thấy” là kết quả 404, đừng gọi blockOptional() để tự quyết định; compose tiếp bằng switchIfEmpty(Mono.error(...)) hoặc chuyển sang ResponseEntity trong chain.

Ví dụ với Service trả Mono<Product>:

~~~java
@GetMapping("/products/{id}")
Mono<ResponseEntity<Product>> find(@PathVariable String id) {
    return productService.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Đây là đoạn Controller minh họa, giả định type Product và productService tồn tại. Nó biến giá trị thành **200**, nguồn rỗng thành **404**, lỗi vẫn truyền qua cơ chế lỗi của WebFlux. Không sử dụng subscribe() hay block().

### 8.2. Khi nào nên dùng WebClient thay RestTemplate/RestClient?

Trong một **đường WebFlux non-blocking**, WebClient được thiết kế để expose kết quả như Mono/Flux. RestTemplate/RestClient làm việc theo mô hình đồng bộ; gọi trực tiếp từ event loop có thể chặn. Một ứng dụng **Spring MVC** có thể vẫn dùng RestClient hợp lý vì mô hình thread khác; lựa chọn phụ thuộc web stack và mục tiêu hệ thống.

**Tồn tại Mono không đủ để bảo đảm reactive từ đầu đến cuối.** Phải xem nguồn I/O thật, không chỉ kiểu trả về của phương thức.

## 9. Lỗi, timeout, cancellation và ngữ cảnh request

### 9.1. Error là tín hiệu của cùng một pipeline

~~~java
// Ví dụ trong Service; client.fetch(id) trả Mono<Profile>.
return client.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                error -> Mono.error(
                        new IllegalStateException("Profile service timed out", error)
                ));
~~~

Import java.util.concurrent.TimeoutException. Đây là **đoạn minh họa**, không phải file độc lập. Trong dự án thực, chuyển lỗi sang HTTP 504 hoặc một contract phù hợp thông qua tầng xử lý lỗi; không trả thành công giả để che sự cố.

**subscribe() thủ công** làm nhánh lỗi độc lập: lỗi của service phụ có thể chỉ đi tới hook lỗi của Reactor hoặc callback subscriber riêng, không đến HTTP response. Nếu trực tiếp dùng subscribe() ở một **imperative boundary hợp lệ** như event listener ngoài request, phải quản lý **Disposable**, lifecycle, lỗi và cancellation, hoặc chuyển sang cơ chế job/queue được quản lý.

### 9.2. Cancellation không giống rollback

Khi client ngắt kết nối hoặc timeout, framework có thể gửi tín hiệu cancel vào Publisher. Hành vi này thường truyền dọc chain được compose. Nhưng nếu service đã ghi DB, gửi HTTP request ra ngoài hoặc tác vụ blocking đã bắt đầu, **cancel không bảo đảm hoàn tác**. Nên dùng idempotency key, transaction phù hợp với resource, cơ chế retry có giới hạn và xử lý trùng lặp ở ranh giới nghiệp vụ.

Với subscribe() thủ công bên trong request, nhánh phụ có **Disposable riêng** và thường không nhận cancellation của request chính. Đó là một lý do cốt lõi để không tách subscription.

### 9.3. Reactor Context, Security và MDC

Reactive execution có thể chuyển giữa các thread. Vì vậy không nên giả định dữ liệu giữ trong ThreadLocal/MDC luôn đi theo mọi callback. Spring Security reactive và các thư viện hỗ trợ context propagation sử dụng cơ chế phù hợp với Reactor Context; khi tự triển khai, dùng contextWrite/deferContextual hoặc integration được framework hỗ trợ thay vì tự đặt global variable hay đọc ThreadLocal trong một thread khác.

Không đọc HTTP request body/cookie/Principal một cách **eager** bên ngoài các API reactive khi dữ liệu đó chỉ sẵn có trong chain. Không tạo subscribe() riêng với hy vọng nó tự mang theo security/trace/transaction context của request.

## 10. Hai subscription có thể khiến cùng thao tác chạy hai lần

Nhiều Publisher của Reactor là **cold**: mỗi subscription có thể kích hoạt lại nguồn, bao gồm truy vấn DB hoặc gọi HTTP.

~~~java
// SAI: giả định saveInvoice() trả Mono<Invoice>.
Mono<Invoice> save = invoiceService.saveInvoice(input);
save.subscribe();  // subscription số 1
return save;        // WebFlux có thể tạo subscription số 2
~~~

Nếu nguồn cold có side effect, thao tác có thể xảy ra hai lần. Không được khẳng định mọi Mono đều chạy hai lần: nguồn hot, cache, share, replay có semantics khác nhau. Nhưng **nguy cơ là có thật**, nhất là với thao tác ghi.

~~~java
// ĐÚNG: tạo chain và trả cho WebFlux một lần.
return invoiceService.saveInvoice(input);
~~~

Khi muốn **chia sẻ** kết quả giữa nhiều consumer, phải chọn chiến lược cache/share/replay theo vòng đời, memory và tính nhất quán cụ thể. Đừng dùng Mono.cache() để chữa bừa một lỗi do subscribe() thừa, nhất là với thao tác ghi.

## 11. Quan sát và kiểm thử đúng loại lỗi

### 11.1. Điều cần quan sát

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| IllegalStateException đề cập block() trên reactor-http-nio hoặc non-blocking thread | Tìm block(), blockFirst(), blockLast() trong Controller/Filter và callback |
| CPU thấp nhưng p95/p99 tăng, ít event-loop thread bị giữ lâu | Thread dump, blocking JDBC/SDK, Thread.sleep, file I/O |
| API trả 200 trước khi audit/notify hoàn tất | Có subscribe() thủ công hoặc fire-and-forget? |
| Lỗi downstream không đi vào HTTP error handler | Nhánh subscribe() tách rời, onError bị mất, custom error handler |
| Cùng thao tác ghi chạy hai lần | Nhiều subscription trên cold Publisher, retry tự động, request trùng |
| Client đã hủy nhưng công việc nền vẫn chạy | Nhánh subscribe độc lập hoặc nguồn không thể hủy |
| BoundedElastic queue lớn, latency tiếp tục tăng | Blocking source quá nhiều, timeout/giới hạn đồng thời chưa hợp lý |
| Số lượng phản hồi giảm khi tải tăng | Event loop starvation, pool/DB bottleneck, downstream slowdown |

Để điều tra, theo dõi request rate/latency, error rate, kết nối tới downstream, event-loop thread dump, scheduler, pool và logs gắn request id. Không tự kết luận “reactive bị chậm” chỉ vì xuất hiện Flux/Mono; cần phân biệt nguồn I/O, operator CPU, blocking hidden và giới hạn hệ thống.

### 11.2. Kiểm thử pipeline thay vì block() trong production

Trong **unit test**, StepVerifier tạo subscriber có kiểm soát và xác nhận giá trị, lỗi, completion/cancellation. Nó thay thế nhu cầu nhét subscribe() hoặc block() thủ công vào code nghiệp vụ để “xem kết quả”. Trong test tích hợp HTTP, dùng WebTestClient hoặc curl để xác nhận response contract và side effect sau khi request hoàn tất.

Nếu test phải lấy giá trị đồng bộ ở ranh giới kiểm thử, sử dụng block() một cách có kiểm soát trên thread **cho phép blocking**, kèm timeout phù hợp, vẫn là một ngoại lệ khả dụng; điều cấm của bài là **đem cách đó vào event-loop request handler**. Với ứng dụng batch/CLI chạy theo mô hình imperative, block() có thể là một ranh giới chuyển đổi hữu ý; không phải mọi lần gọi block() trên toàn codebase đều là bug.

### 11.3. Một bài tập tự sửa

Đọc đoạn lỗi:

~~~java
@PostMapping("/send/{id}")
Mono<String> send(@PathVariable String id) {
    Mono<String> value = apiClient.get(id);
    auditService.log(id).subscribe();
    return Mono.just(value.block().toUpperCase());
}
~~~

Giả định apiClient.get trả Mono<String>, auditService.log trả Mono<Void>. Có **hai lỗi độc lập**: subscribe() tách audit khỏi request; block() đồng bộ hóa lời gọi API trong thread xử lý HTTP. Viết lại:

~~~java
@PostMapping("/send/{id}")
Mono<String> send(@PathVariable String id) {
    return apiClient.get(id)
            .flatMap(value ->
                    auditService.log(id)
                            .thenReturn(value.toUpperCase())
            );
}
~~~

Khi apiClient.get rỗng, không có value để chuyển tiếp và audit trong ví dụ **không chạy**. Nếu audit phải diễn ra kể cả khi nguồn rỗng, cần thiết kế quy tắc khác một cách chủ ý. Nếu apiClient hoặc audit phát lỗi, Mono trả về phát lỗi; không có HTTP success giả. Hai đoạn là **fragment của Controller đã inject service**, không tự biên dịch riêng.

## 12. Checklist trước khi merge một WebFlux request handler

- **Đường đi:** Controller trả Mono/Flux hoặc một kiểu reactive tương đương; không gọi block()/blockFirst()/blockLast() trên event loop.
- **Nguồn dữ liệu:** phân biệt reactive I/O thật với JDBC/SDK đồng bộ được bọc kiểu Mono; không để blocking call chạy eager trong Mono.just(...).
- **Subscription:** không gọi subscribe() để “kích hoạt” công việc trong Controller, WebFilter, hoặc service thuộc request. Để framework subscribe Publisher được trả về.
- **Side effect:** dùng flatMap/then/thenReturn/Mono.when để biểu diễn thứ tự cần thiết; ghi bền vững/độc lập phải có cơ chế được quản lý.
- **Blocking bắt buộc:** từ nguồn lazy Mono.fromCallable/Mono.fromRunnable và subscribeOn(boundedElastic), cùng timeout/connection limit, budget bộ nhớ/threads và test tải.
- **Lỗi:** error signal của nhánh downstream vẫn đi về HTTP response; doOnError chỉ quan sát, onErrorResume có chủ đích; không bỏ qua lỗi trong subscribe() phụ.
- **Cancellation:** hiểu việc hủy của HTTP request và tính không bảo đảm của side effect đã gửi; áp dụng idempotency nếu cần.
- **Ngữ cảnh:** security, trace id và transaction context phải đi cùng reactive chain; không tùy tiện dựa vào ThreadLocal khi đổi scheduler.
- **Kiểm thử:** dùng StepVerifier/WebTestClient, kiểm tra case empty/error/timeout/cancel và kiểm tra một request có tạo một side effect đúng kỳ vọng.
- **Vận hành:** theo dõi p95/p99, thread dump, scheduler/pool saturation, downstream latency; tránh dùng thread count tăng vô hạn để che blocking.

**Ghi nhớ:** **return Mono/Flux → framework subscribe** là mô hình mặc định của WebFlux. **block()** ép chờ trên thread hiện tại; **subscribe()** tự tạo nhánh thực thi khác. Cách thiết kế đúng là **compose pipeline**, offload blocking legacy khi bắt buộc, rồi để toàn bộ thành công, lỗi và cancellation được quản lý qua cùng một chuỗi.

## Tài liệu tham khảo

- Spring Framework — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient và retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Project Reactor — Schedulers, subscribeOn, publishOn: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — Subscription patterns, lifecycle và cancellation: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor — FAQ về nguồn blocking: https://projectreactor.io/docs/core/release/reference/faq.html
