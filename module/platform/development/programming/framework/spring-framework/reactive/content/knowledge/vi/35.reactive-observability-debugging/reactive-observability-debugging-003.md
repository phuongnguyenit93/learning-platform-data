# `checkpoint`, `Hooks.onOperatorDebug` và `ReactorDebugAgent` trong Project Reactor

## 1. Mục tiêu: tìm nơi một reactive chain được tạo ra

Khi một chương trình Java đồng bộ phát sinh exception, stack trace thường cho thấy chuỗi lời gọi dẫn tới dòng code gây lỗi. Với Reactor, luồng xử lý được khai báo thành `Mono` hoặc `Flux`, rồi mới chạy khi có subscription. Các operator có thể phát tín hiệu trên nhiều thread, qua scheduler, callback hoặc thư viện khác. Vì vậy stack trace tại thời điểm lỗi thường mô tả đường đi thực thi bên trong Reactor nhiều hơn vị trí code đã lắp ráp chuỗi operator.

Ba công cụ chính của bài học giải quyết vấn đề đó:

- **`checkpoint(...)`**: đánh dấu một reactive chain hoặc một vị trí quan trọng trong chain. Có biến thể chỉ ghi marker nhẹ và biến thể thu stack trace đầy đủ.
- **`Hooks.onOperatorDebug()`**: bật assembly debugging toàn cục, ghi lại vị trí tạo operator cho các chain được lắp ráp sau khi hook được bật.
- **`ReactorDebugAgent`**: dùng Java Agent/ByteBuddy để instrument call sites trong class, cung cấp thông tin assembly rộng mà không phải tạo stack trace cho mọi operator như global hook.

Sau bài này, bạn có thể:

1. Phân biệt assembly time, subscription time và signal execution time.
2. Hiểu vì sao stack trace thông thường của `Mono`/`Flux` khó truy ra dòng code khai báo chain.
3. Đặt `checkpoint()` đúng vị trí và chọn marker nhẹ hay full stack.
4. Đọc phần Reactor traceback được đính kèm dưới dạng suppressed exception.
5. Bật và reset `Hooks.onOperatorDebug()` đúng thời điểm.
6. Khởi tạo `ReactorDebugAgent` trước khi Spring Boot tạo các reactive chain.
7. Chọn công cụ theo môi trường local, test, staging và production.
8. Dùng `StepVerifier` và `WebTestClient` kiểm tra traceback mà không cần `block()` trong service.
9. Tránh chi phí debug toàn cục, global hook bị rò giữa các test và log lộ dữ liệu nhạy cảm.

Ví dụ thực hành sử dụng Java 17+, Spring Boot 3.3.5, Spring WebFlux và Reactor 3.6.x do Spring Boot quản lý dependency version.

## 2. Ba thời điểm cần phân biệt

Một reactive pipeline có ba giai đoạn khái niệm:

```text
ASSEMBLY
  Khai báo Mono/Flux và gắn operator
       |
       v
SUBSCRIPTION
  Subscriber đăng ký và demand bắt đầu
       |
       v
SIGNAL EXECUTION
  onNext / onError / onComplete chạy qua chain
```

Ví dụ:

```java
Mono<String> result = Mono.just("42")
        .map(this::parseId)
        .flatMap(repository::findName);

return result;
```

- **Assembly**: các lời gọi `just`, `map`, `flatMap` tạo cấu trúc Publisher.
- **Subscription**: framework hoặc caller subscribe vào Publisher.
- **Execution**: các operator xử lý dữ liệu và phát tín hiệu.

Với WebFlux controller, framework subscribe vào publisher được trả về. Không cần gọi `subscribe()` trong controller/service.

### 2.1. Vì sao stack trace thông thường thường khó đọc?

Một exception có thể được phát hiện trong `MonoSingle`, `FluxMap`, `FluxFlatMap` hoặc một callback sau khi scheduler đã đổi thread. Stack trace tại runtime thường cho thấy:

- Operator nội bộ phát hiện vi phạm contract.
- Các lớp `reactor.core.publisher.*`.
- Các lời gọi `subscribe`, `request`, `onNext`.
- Điểm subscribe cuối cùng của ứng dụng.

Nhưng điểm subscribe không nhất thiết là nơi chain được tạo. Một service có thể tạo `Mono` từ trước, lưu trong biến hoặc trả qua nhiều method rồi mới được subscribe ở WebFlux adapter.

Ví dụ lỗi:

```java
Mono<String> oneName = Flux.just("An", "Binh")
        .map(String::toUpperCase)
        .single();
```

`single()` yêu cầu source phát đúng một phần tử. Source ở đây phát hai phần tử nên pipeline lỗi. Stack trace có thể tập trung vào `MonoSingle` và operator internals; người đọc cần tìm được dòng `single()` trong code của ứng dụng.

Assembly traceback bổ sung thông tin về **nơi operator được khai báo**, giúp nối lỗi runtime với source code đã tạo chain.

### 2.2. Assembly traceback không thay thế root cause

Traceback của Reactor giúp trả lời:

- Operator nào được lắp ráp ở file/class/line nào?
- Lỗi được quan sát qua những đoạn chain nào?
- Chain được tạo qua một reusable `transform` ở đâu?

Nó không tự giải thích tại sao dữ liệu sai, database từ chối, upstream timeout hoặc business rule thất bại. Luôn đọc exception gốc và cause chain cùng với assembly traceback.

## 3. Đọc Reactor traceback

Khi có assembly debugging, Reactor có thể thêm một suppressed exception vào exception gốc. Phần bổ sung thường chứa các khu vực như:

1. **Assembly trace from producer**: nơi operator gây lỗi được lắp ráp.
2. **Error has been observed at the following site(s)**: những operator/chain đã nhận tín hiệu lỗi.
3. **Original Stack Trace**: stack trace runtime ban đầu.

Minh họa cấu trúc rút gọn:

```text
java.lang.IllegalStateException: remote store unavailable
    at ...

Suppressed: The stacktrace has been enhanced by Reactor
Assembly trace from producer [reactor.core.publisher.MonoFlatMap]:
    at com.example.OrderService.findById(OrderService.java:42)

Error has been observed at the following site(s):
    |_ Mono.flatMap  at OrderService.findById(OrderService.java:42)
    |_ Mono.checkpoint at OrderService.findById(OrderService.java:43)

Original Stack Trace:
    at ...
```

Đây là hình dạng minh họa, không phải output cố định của mọi phiên bản Reactor. Tên producer, số dòng và các section thay đổi theo operator, phiên bản và cấu trúc chain.

### 3.1. Root marker và observed sites

Khi lỗi đi qua nhiều operator hoặc nhiều nhánh dùng chung một source, traceback có thể đánh dấu nơi lỗi bắt nguồn và liệt kê các điểm đã quan sát lỗi. Nhờ đó có thể phân biệt:

- Operator tạo ra lỗi.
- Operator chuyển tiếp lỗi.
- Chain được ghép từ một reusable transformation.
- Nhiều nhánh cùng quan sát một lỗi.

Không nên chỉ tìm dòng đầu tiên có chữ `reactor`. Hãy tìm phần assembly trace và đối chiếu class/method/line của code ứng dụng.

### 3.2. Traceback thường là suppressed exception

Có thể duyệt các suppressed exceptions:

```java
for (Throwable suppressed : error.getSuppressed()) {
    if (Exceptions.isTraceback(suppressed)) {
        log.debug("Reactor assembly traceback: {}", suppressed.getMessage());
    }
}
```

Import:

```java
import reactor.core.Exceptions;
```

Không cần tự thêm traceback vào message của exception hoặc thay exception gốc chỉ để làm log dễ đọc.

Nếu Reactor tạo composite exception, traceback cũng có thể xuất hiện trong danh sách thành phần khi unwrap. Các API hữu ích gồm:

```java
Exceptions.unwrapMultiple(error);
Exceptions.unwrapMultipleExcludingTracebacks(error);
Exceptions.isTraceback(error);
```

Dùng `unwrapMultipleExcludingTracebacks` khi cần lấy các lỗi thành phần mà không coi assembly traceback là một lỗi nghiệp vụ riêng.

### 3.3. Cẩn thận với exception được tái sử dụng

Không nên giữ một exception có suppressed tracebacks trong static field rồi ném lại nhiều lần. Traceback có thể tiếp tục được thêm vào suppressed list của cùng object, làm thông tin tích lũy và gây tăng bộ nhớ.

Tạo exception mới cho từng failure thường dễ hiểu và an toàn hơn. Tránh tối ưu bằng static exception instance nếu pipeline đang dùng assembly traceback.

## 4. `checkpoint()` đánh dấu một chain cụ thể

`checkpoint` là operator có thể đặt trực tiếp trong một `Mono` hoặc `Flux` chain. Khác với global hook, nó chỉ bổ sung thông tin cho chain nơi operator được sử dụng.

Có ba dạng chính:

| API | Thông tin bổ sung | Chi phí tương đối |
|---|---|---|
| `checkpoint()` | Thu full assembly stack | Cao hơn marker nhẹ |
| `checkpoint("id")` | Chỉ thêm mô tả/marker | Thấp hơn full stack |
| `checkpoint("id", true)` | Mô tả và full assembly stack | Cao hơn marker nhẹ |
| `checkpoint("id", false)` | Tương đương marker nhẹ | Thấp hơn full stack |

### 4.1. Full stack bằng `checkpoint()`

```java
Mono<Order> result = repository.findById(id)
        .map(this::toOrder)
        .flatMap(this::enrich)
        .checkpoint();
```

Khi lỗi đi từ upstream qua checkpoint, Reactor có thể bổ sung stack trace assembly đầy đủ cho vị trí checkpoint.

Dùng khi:

- Đang điều tra lỗi khó tái hiện.
- Cần biết chính xác nơi chain được tạo.
- Chi phí capture stack trên một số chain quan trọng là chấp nhận được.

### 4.2. Marker nhẹ bằng `checkpoint(String)`

```java
Mono<Order> result = repository.findById(id)
        .map(this::toOrder)
        .flatMap(this::enrich)
        .checkpoint("orders.findById");
```

Marker không thu stack trace đầy đủ tại vị trí checkpoint. Nó đưa một description vào traceback để người đọc tìm được operation liên quan.

Description phải đủ cụ thể để phân biệt các chain. Nên dùng tên ổn định như:

```text
orders.findById
billing.calculateInvoice
catalog.refreshCache
```

Tránh mô tả chung chung như `"checkpoint"` hoặc `"error"`.

### 4.3. Chọn full stack có description

```java
Mono<Order> result = repository.findById(id)
        .map(this::toOrder)
        .checkpoint("orders.repository.lookup", true);
```

Tham số boolean `true` yêu cầu full stack trace cùng description. `false` dùng marker nhẹ tương tự `checkpoint(String)`.

Dùng description tĩnh theo operation thường dễ vận hành. Nếu đưa correlation ID vào description, cần bảo đảm giá trị đã được làm sạch và không chứa token, email, dữ liệu cá nhân hoặc secret.

## 5. Đặt checkpoint ở đâu?

Một checkpoint chỉ quan sát lỗi truyền từ upstream qua nó. Lỗi phát sinh ở downstream sau checkpoint không quay ngược lại để được checkpoint đó bổ sung traceback.

Ví dụ:

```java
Mono<String> result = repository.findById(id)
        .map(this::toDto)
        .flatMap(this::enrich)
        .checkpoint("orders.lookup")
        .map(this::render);
```

Checkpoint có thể bổ sung traceback cho lỗi từ `findById`, `toDto` hoặc `enrich`. Nếu `render` ở phía downstream phát lỗi, checkpoint phía trước không quan sát được lỗi đó.

Vì vậy, hãy đặt checkpoint gần cuối đoạn chain mà bạn muốn quan sát:

```java
Mono<String> result = repository.findById(id)
        .map(this::toDto)
        .flatMap(this::enrich)
        .map(this::render)
        .checkpoint("orders.lookup.response");
```

### 5.1. Checkpoint ở ranh giới service

Một pattern dễ đọc:

```java
@Service
public class OrderService {

    public Mono<OrderView> find(String id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(id)))
                .map(this::toView)
                .flatMap(this::attachPricing)
                .checkpoint("orders.find");
    }
}
```

Checkpoint mô tả một use case thay vì thêm marker vào mọi operator. Nếu lỗi vẫn khó định vị, thêm checkpoint hẹp hơn ở adapter hoặc nhánh upstream cụ thể.

### 5.2. Nhiều checkpoint trong một pipeline

```java
Mono<OrderView> result = repository.findById(id)
        .checkpoint("orders.repository")
        .map(this::toView)
        .flatMap(pricingClient::enrich)
        .checkpoint("orders.pricing")
        .map(this::toResponse)
        .checkpoint("orders.response");
```

Các marker giúp phân đoạn các ranh giới quan trọng. Không cần thêm checkpoint sau từng `map` đơn giản; nhiều marker trùng lặp làm traceback dài và giảm giá trị chẩn đoán.

### 5.3. Một method trả Publisher rồi caller nối tiếp operator

```java
Mono<Order> servicePublisher = service.find(id);

Mono<String> response = servicePublisher
        .map(this::render)
        .checkpoint("http.order.response");
```

Checkpoint bên trong `service.find` không thể quan sát lỗi được tạo bởi `render` ở caller. Nếu muốn kiểm tra toàn bộ HTTP response pipeline, đặt checkpoint tại boundary cuối cùng của pipeline đó hoặc thêm checkpoint trong method chứa operator gây lỗi.

### 5.4. Checkpoint không sửa lỗi

Checkpoint không:

- Retry request.
- Khôi phục kết nối.
- Thay đổi backpressure.
- Sửa dữ liệu sai.
- Biến exception thành response thành công.
- Bảo đảm mọi lỗi downstream đều được quan sát.

Nó bổ sung vị trí assembly vào lỗi để điều tra nhanh hơn.

## 6. `Hooks.onOperatorDebug()` bật assembly debugging toàn cục

Nếu chưa biết chain nào có thể lỗi, Reactor cung cấp global debug mode:

```java
Hooks.onOperatorDebug();
```

Hook instrument các lời gọi tạo operator và ghi lại stack trace tại assembly. Khi lỗi xuất hiện sau đó, Reactor có thể đính kèm traceback cho các operator đã được tạo khi hook đang hoạt động.

### 6.1. Phải bật trước khi tạo Publisher

Đúng:

```java
public static void main(String[] args) {
    Hooks.onOperatorDebug();

    SpringApplication.run(Application.class, args);
}
```

Không hiệu quả với các chain đã được assemble trước thời điểm bật hook:

```java
static final Mono<String> PREBUILT =
        Mono.just("value").map(String::toUpperCase);

public static void main(String[] args) {
    Hooks.onOperatorDebug();
    // PREBUILT đã được assemble trước khi hook được bật.
}
```

Đặt hook ở đầu `main` trước khi Spring tạo bean và reactive pipelines giúp tránh trường hợp này.

### 6.2. Tác động hiệu năng

`Hooks.onOperatorDebug()` là global. Nó ảnh hưởng các `Mono`/`Flux` được assemble sau khi hook được bật trong process, không chỉ một request hoặc một service.

Chi phí đáng chú ý là capture stack trace ở các operator assembly. Điều này có thể làm tăng thời gian tạo pipeline và allocation, đặc biệt khi ứng dụng tạo nhiều chain hoặc operator trong hot path.

Dùng global hook cho:

- Local debugging.
- Test có kiểm soát.
- Một lần tái hiện lỗi trên staging.
- Tình huống cần assembly trace rộng và chấp nhận chi phí.

Không bật mặc định trên production chỉ vì muốn log có nhiều thông tin hơn. Hãy cân nhắc `checkpoint(String)` hoặc `ReactorDebugAgent` trước.

### 6.3. Tắt hook bằng `resetOnOperatorDebug()`

```java
Hooks.onOperatorDebug();

try {
    // Assemble và chạy pipeline cần điều tra.
}
finally {
    Hooks.resetOnOperatorDebug();
}
```

`Hooks.resetOnOperatorDebug()` gỡ hook debug được cài bởi `onOperatorDebug`.

Đây là global state, không phải cấu hình theo subscriber. Không bật/tắt hook cho từng HTTP request hoặc trong một reactive callback. Nếu nhiều test chạy song song, một test reset hook có thể ảnh hưởng test khác. Giữ test dùng global hook cô lập, chạy tuần tự hoặc bảo vệ bằng cơ chế đồng bộ thích hợp.

## 7. `ReactorDebugAgent`: instrument call sites bằng Java Agent

`ReactorDebugAgent` thuộc artifact `io.projectreactor:reactor-tools`. Agent sử dụng ByteBuddy để instrument class của ứng dụng tại thời điểm class được load, giúp Reactor thu được thông tin assembly mà không phải capture stack trace ở mọi operator call như `Hooks.onOperatorDebug()`.

### 7.1. Thêm dependency `reactor-tools`

Với Maven và Spring Boot dependency management:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-tools</artifactId>
</dependency>
```

Khi dùng Reactor BOM được Spring Boot quản lý, không cần tự chọn version riêng. Giữ `reactor-tools` tương thích với `reactor-core` đang được BOM chọn; không ghép tùy ý các version Reactor khác release train.

### 7.2. Khởi tạo sớm trong `main`

```java
import reactor.tools.agent.ReactorDebugAgent;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        ReactorDebugAgent.init();
        SpringApplication.run(Application.class, args);
    }
}
```

Gọi `init()` trước `SpringApplication.run(...)` để agent sẵn sàng instrument các class khi chúng được load và các reactive chains được tạo.

Agent phù hợp khi muốn có assembly debugging rộng trong một môi trường chạy dài hơn local debugging nhưng không muốn bật stack capture toàn cục ở từng operator.

### 7.3. Khi class đã được load trước `init()`

Nếu một số class/call sites đã được load trước khi agent khởi tạo, có thể yêu cầu agent xử lý lại các class đang tồn tại:

```java
ReactorDebugAgent.init();
ReactorDebugAgent.processExistingClasses();
```

`processExistingClasses()` phải duyệt các class đã load và áp dụng transformation; thao tác này có thể mất vài giây. Chỉ dùng khi phát hiện call sites đã load chưa được instrument. Cách tốt hơn trong ứng dụng bình thường là gọi `init()` thật sớm.

### 7.4. Giới hạn self-attach và lựa chọn `-javaagent`

`ReactorDebugAgent.init()` dùng ByteBuddy self-attach. Một số JVM/runtime policy có thể không cho phép attach vào chính process. Nếu self-attach không hoạt động, có thể chạy reactor-tools như Java Agent từ lúc JVM khởi động:

```bash
java -javaagent:reactor-tools.jar -jar app.jar
```

Đường dẫn `reactor-tools.jar` phải là file JAR thực tế được phân phối cùng ứng dụng. Khi chạy container, đặt agent JAR ở một vị trí cố định và cấu hình JVM startup command phù hợp.

### 7.5. Instrumentation tại build time

Reactor Tools cũng hỗ trợ ByteBuddy Maven/Gradle plugin để instrument class trong build. Cách này cần cấu hình plugin và dependency `reactor-tools` với classifier thích hợp theo tài liệu của Reactor.

Lưu ý: build-time transformation chỉ áp dụng cho class của project được instrument; thư viện nằm trong dependency classpath không tự động được instrument bởi bước đó. Đây là lựa chọn build/deployment riêng, không cần thêm vào dự án học tập tối thiểu.

### 7.6. Agent khác global hook như thế nào?

- `Hooks.onOperatorDebug()` bắt stack trace khi operator được tạo sau khi hook bật; chi phí capture nằm trong quá trình assembly.
- `ReactorDebugAgent` instrument bytecode để bổ sung thông tin assembly cho call sites trong class; tránh việc capture stack trace ở mọi operator call theo cách global hook thực hiện.
- Cả hai đều không thay thế `checkpoint` khi muốn đánh dấu rõ ràng một use case cụ thể.
- Không cần bật cả Agent và global hook cùng lúc nếu không có lý do chẩn đoán cụ thể.

## 8. So sánh và chọn công cụ

| Công cụ | Phạm vi | Có full stack tại assembly? | Chi phí/điều kiện | Trường hợp phù hợp |
|---|---|---|---|---|
| Không bật debug | Mặc định | Không | Thấp | Production thông thường |
| `checkpoint("id")` | Một chain | Không, marker nhẹ | Thấp hơn full checkpoint | Đánh dấu boundary quan trọng |
| `checkpoint()` | Một chain | Có | Capture stack tại checkpoint | Điều tra lỗi cụ thể |
| `checkpoint("id", true)` | Một chain | Có + description | Capture stack tại checkpoint | Cần stack và nhãn rõ |
| `Hooks.onOperatorDebug()` | Toàn cục | Có, ở operator được assemble sau hook | Cao hơn do capture stack trên các operator | Local/test/reproduction có kiểm soát |
| `ReactorDebugAgent` | Call sites được instrument | Có thông tin assembly | Agent attach/instrument lúc khởi động hoặc class load | Staging/production diagnosis cần trace rộng |

### Gợi ý theo môi trường

**Local development**

- Bắt đầu bằng `checkpoint("service.operation")`.
- Khi chưa biết chain lỗi, bật `Hooks.onOperatorDebug()` từ đầu process.
- Dùng `log()` hoặc `doOnError` để xem signal và cause.

**Unit/integration test**

- Đặt checkpoint ở ranh giới service quan trọng.
- Có thể dùng global hook trong một test cô lập, nhưng phải reset bằng `finally`.
- Assert traceback tồn tại thay vì so sánh toàn bộ stack trace vì line number thay đổi theo build.

**Staging**

- Có thể bật `ReactorDebugAgent` sớm để điều tra lỗi cần assembly information rộng.
- Đo startup, memory và latency trước/sau khi thay đổi.
- Tắt cấu hình debug không còn cần sau khi điều tra.

**Production**

- Ưu tiên checkpoint nhẹ ở các boundary có giá trị vận hành.
- Dùng agent theo quy trình vận hành đã đánh giá khi cần assembly debugging rộng.
- Tránh bật global hook mặc định trên toàn bộ operator của process có tải cao.

## 9. Kiểm tra traceback bằng Java API

Traceback được thêm dưới dạng suppressed exception. Có thể viết helper:

```java
static boolean hasReactorTraceback(Throwable error) {
    return Arrays.stream(error.getSuppressed())
            .anyMatch(Exceptions::isTraceback);
}
```

Imports:

```java
import java.util.Arrays;
import reactor.core.Exceptions;
```

Dùng trong test:

```java
StepVerifier.create(service.find("fail"))
        .expectErrorSatisfies(error -> {
            assertTrue(error instanceof IllegalStateException);
            assertTrue(hasReactorTraceback(error));
        })
        .verify();
```

Không assert toàn bộ chuỗi stack trace. Nó chứa file/line, class nội bộ và nội dung phụ thuộc compiler, version Reactor và vị trí code. Hãy assert những đặc tính ổn định:

- Exception gốc đúng loại.
- Có suppressed traceback.
- Description quan trọng xuất hiện khi API cung cấp description.
- Publisher kết thúc bằng đúng `onError` hoặc response status theo contract.

### 9.1. Cause chain và suppressed list là hai thứ khác nhau

- `getCause()` đi theo nguyên nhân được wrap.
- `getSuppressed()` liệt kê các exception được đính kèm bên cạnh exception gốc.
- Reactor assembly traceback thường nằm trong suppressed list.

Đừng chỉ duyệt `getCause()` rồi kết luận không có traceback. Khi xử lý composite errors, dùng các helper `Exceptions` phù hợp để phân biệt traceback và lỗi nghiệp vụ.

## 10. Quan sát signal bằng `log()`, `doOnError` và metadata

Assembly traceback giúp biết chain được tạo ở đâu. Khi cần biết **signal nào thực sự xảy ra**, có thể dùng các công cụ khác.

### 10.1. `log()`

```java
Flux<Integer> values = Flux.range(1, 5)
        .log("orders.stream")
        .take(2);
```

`log()` có thể ghi các sự kiện như:

- `onSubscribe`
- `request(n)`
- `onNext`
- `onError`
- `onComplete`
- `cancel`

Vị trí đặt `log()` ảnh hưởng operator nào được quan sát. Ví dụ đặt trước `take(2)` giúp thấy downstream yêu cầu giới hạn demand và hủy upstream sau hai phần tử.

`log()` rất hữu ích trong local debugging, nhưng không nên bật bừa bãi trên stream có payload lớn hoặc nhạy cảm. Kiểm tra logger level và cấu hình appender để tránh ghi token, thông tin cá nhân hoặc nội dung request.

### 10.2. `doOnError`

```java
return repository.findById(id)
        .doOnError(error ->
                logger.warn(
                        "order lookup failed: type={}",
                        error.getClass().getSimpleName()))
        .checkpoint("orders.repository.lookup");
```

`doOnError` quan sát lỗi để logging/metrics; nó không tự chuyển lỗi thành thành công. Không nuốt lỗi bằng cách log rồi bỏ publisher.

### 10.3. `name()` và `tag()`

```java
Mono<Order> result = repository.findById(id)
        .name("orders.findById")
        .tag("component", "order-service")
        .checkpoint("orders.findById");
```

`name`/`tag` cung cấp metadata cho introspection/observation khi tooling hỗ trợ. Chúng không tương đương assembly stack trace và không thay thế checkpoint.

## 11. Kết hợp với Spring WebFlux

Trong WebFlux, controller/service thường trả `Mono` hoặc `Flux` cho framework. Vì vậy vị trí assemble chain có thể cách xa thời điểm Netty thread xử lý lỗi.

Một cách tổ chức hữu ích:

```text
HTTP request
    |
    v
Controller
    |
    v
Service reactive chain
    |---- checkpoint("orders.find")
    |
    v
Repository / WebClient
    |---- checkpoint("orders.remote")
    |
    v
onError
    |
    +---- original cause
    +---- Reactor assembly traceback
```

### 11.1. Không dùng `block()` để làm stack trace dễ đọc

Không thêm `.block()` hoặc `.subscribe()` chỉ để exception xuất hiện trong thread hiện tại. Việc đó thay đổi execution model, có thể chặn event loop hoặc tách error/cancellation khỏi request lifecycle.

Giữ reactive composition và bổ sung checkpoint ở nơi cần quan sát.

### 11.2. Spring Boot khởi tạo agent trước khi tạo bean

Với ReactorDebugAgent, gọi `init()` ở đầu `main` trước `SpringApplication.run`. Các bean và service được tạo sau đó sẽ được load trong process đã khởi tạo agent.

Nếu test dùng `@SpringBootTest`, Spring Test có thể bootstrap application context mà không gọi phương thức `main` của ứng dụng. Vì vậy test không nên giả định agent đã được init chỉ vì class main chứa `ReactorDebugAgent.init()`. Unit tests bên dưới dùng checkpoint và global hook cô lập để kiểm tra hành vi.

### 11.3. WebClient và ranh giới thư viện

Khi chain gọi WebClient, checkpoint đặt ở service boundary giúp định vị nơi outbound publisher được lắp ráp. Assembly trace có thể cho biết operator được tạo trong code ứng dụng; nó không tự biến lỗi HTTP 500, DNS hoặc TLS thành nguyên nhân chi tiết. Hãy kết hợp với cause chain, HTTP status, request ID và WebClient observation/metrics.

## 12. Dự án Java 17+ chạy được: Spring Boot WebFlux và Reactor Tools

Dự án mẫu có:

- Spring Boot 3.3.5 và Java 17.
- Spring WebFlux endpoint `/orders/{id}`.
- `OrderService` gắn checkpoint nhẹ ở cuối pipeline.
- `ReactorDebugAgent.init()` trước khi Spring Boot khởi động.
- Unit tests xác nhận checkpoint bổ sung traceback.
- Một test bật `Hooks.onOperatorDebug()` trước khi assemble chain rồi reset trong `finally`.
- Một integration test dùng `WebTestClient` xác nhận lỗi service đi ra HTTP 5xx.

Maven dependency management của Spring Boot chọn các version Reactor tương thích. Không khai báo một version `reactor-tools` tùy ý khác với Reactor Core.

### 12.1. Cấu trúc dự án

```text
reactor-debugging-webflux/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/edu/demo/debug/
    │   │   ├── DebuggingApplication.java
    │   │   ├── OrderService.java
    │   │   └── OrderController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/edu/demo/debug/
            └── OrderDebuggingTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>reactor-debugging-webflux</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-tools</artifactId>
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

`reactor-tools` được thêm để có `ReactorDebugAgent`. Dự án vẫn dùng `checkpoint` độc lập với agent; nếu không cần agent trong một module, có thể bỏ dependency đó và giữ Reactor Core APIs.

### 12.3. `DebuggingApplication.java`

```java
package edu.demo.debug;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import reactor.tools.agent.ReactorDebugAgent;

@SpringBootApplication
public class DebuggingApplication {

    public static void main(String[] args) {
        ReactorDebugAgent.init();
        SpringApplication.run(DebuggingApplication.class, args);
    }
}
```

Agent được khởi tạo trước khi Spring tạo application context và các bean của ứng dụng.

Nếu môi trường không cho phép ByteBuddy self-attach, hãy chạy JVM bằng Java Agent:

```bash
java -javaagent:reactor-tools.jar -jar target/reactor-debugging-webflux-1.0.0.jar
```

Thay `reactor-tools.jar` bằng đường dẫn JAR thực tế. Không cần gọi thêm `Hooks.onOperatorDebug()` nếu đã chọn Agent cho cùng mục tiêu assembly debugging.

### 12.4. `OrderService.java`

```java
package edu.demo.debug;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class OrderService {

    public Mono<String> find(String id) {
        return Mono.just(id)
                .map(String::trim)
                .flatMap(this::load)
                .checkpoint("orders.find");
    }

    private Mono<String> load(String id) {
        if ("fail".equals(id)) {
            return Mono.error(
                    new IllegalStateException(
                            "simulated order store failure"));
        }

        return Mono.just("order:" + id);
    }
}
```

Checkpoint nằm sau `flatMap`, nên có thể quan sát lỗi phát sinh từ `load` ở upstream. Nó dùng marker nhẹ, không capture full stack tại vị trí checkpoint.

### 12.5. `OrderController.java`

```java
package edu.demo.debug;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    public Mono<String> find(@PathVariable String id) {
        return orderService.find(id);
    }
}
```

Controller trả publisher cho WebFlux. Không subscribe hoặc block trong controller.

### 12.6. `application.properties`

```properties
spring.application.name=reactor-debugging-webflux
logging.level.edu.demo.debug=DEBUG
```

Trong production, chọn log level và appender phù hợp. Không bật log payload hoặc header nhạy cảm chỉ để quan sát stack trace.

### 12.7. `OrderDebuggingTests.java`

```java
package edu.demo.debug;

import java.time.Duration;
import java.util.Arrays;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.Exceptions;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Hooks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderDebuggingTests {

    @Autowired
    OrderService orderService;

    @Autowired
    WebTestClient webTestClient;

    @Test
    void checkpointAddsAssemblyTraceToUpstreamFailure() {
        StepVerifier.create(orderService.find("fail"))
                .expectErrorSatisfies(error -> {
                    assertTrue(error instanceof IllegalStateException);
                    assertTrue(hasTraceback(error));
                })
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void globalHookCapturesAssemblyWhenEnabledBeforeAssembly() {
        Hooks.onOperatorDebug();

        try {
            Mono<String> failing = Mono.just("value")
                    .map(value -> {
                        throw new IllegalArgumentException("bad value");
                    });

            StepVerifier.create(failing)
                    .expectErrorSatisfies(error ->
                            assertTrue(hasTraceback(error)))
                    .verify(Duration.ofSeconds(3));
        }
        finally {
            Hooks.resetOnOperatorDebug();
        }
    }

    @Test
    void webFluxEndpointPropagatesServiceFailureAsServerError() {
        webTestClient.get()
                .uri("/orders/fail")
                .exchange()
                .expectStatus().is5xxServerError();
    }

    private static boolean hasTraceback(Throwable error) {
        return Arrays.stream(error.getSuppressed())
                .anyMatch(Exceptions::isTraceback);
    }
}
```

Test global hook bật hook **trước khi** tạo `Mono` lỗi và reset trong `finally`. Global hooks là process-wide state; không chạy test này song song với test khác cũng đang thay đổi Reactor hooks.

Test `checkpoint` kiểm tra có traceback được gắn vào exception. Test HTTP xác nhận WebFlux trả lỗi server khi service phát error. Nội dung response cụ thể có thể phụ thuộc error handling của Spring Boot và cấu hình ứng dụng.

### 12.8. Chạy dự án

Từ thư mục có `pom.xml`:

```bash
mvn test
```

Chạy server:

```bash
mvn spring-boot:run
```

Gọi thành công:

```bash
curl -i http://localhost:8080/orders/42
```

Body mong đợi:

```text
order:42
```

Gọi nhánh lỗi:

```bash
curl -i http://localhost:8080/orders/fail
```

HTTP response mong đợi là một status 5xx; log phía server có exception gốc và có thể kèm Reactor traceback do checkpoint/agent. Stack trace đầy đủ phụ thuộc logger, cấu hình và phiên bản Reactor nên không đưa một output giả định cố định.

**Kiểm thử mẫu có 3 test method.** Đây là kết quả kỳ vọng khi chạy Maven, chưa phải xác nhận Maven đã được thực thi trong môi trường biên soạn.

## 13. Chẩn đoán theo từng bước

Khi một lỗi reactive khó truy ra nguồn, có thể làm theo quy trình:

1. **Tìm exception gốc**: đọc class, message và cause chain. Xác định lỗi do validation, codec, database, timeout hay operator contract.
2. **Xác định thời điểm**: lỗi phát sinh khi assemble chain, khi subscribe, hay trong `onNext`/`onError` execution?
3. **Tìm operator có khả năng vi phạm contract**: ví dụ `single`, `next`, `flatMap`, `zip`, `switchIfEmpty`, `collectList`.
4. **Thêm checkpoint nhẹ** ở ranh giới service/repository/client có liên quan.
5. **Tái hiện với checkpoint full stack** nếu marker chưa đủ.
6. **Bật `Hooks.onOperatorDebug()`** trên một process/test cô lập nếu chưa biết chain nào gây lỗi.
7. **Dùng ReactorDebugAgent** khi cần assembly information rộng mà không muốn global hook capture stack ở mọi operator.
8. **Đối chiếu traceback với source** và sửa nguyên nhân thực tế.
9. **Bỏ cấu hình debug tạm thời** hoặc giữ lại checkpoint nhẹ có giá trị vận hành.
10. **Thêm regression test** tái hiện lỗi để lỗi không quay lại.

### 13.1. Ví dụ: lỗi cardinality

```java
Mono<String> result = Flux.just("one", "two")
        .single();
```

`single()` yêu cầu đúng một item, nhưng source có hai. Hướng sửa tùy nghiệp vụ:

```java
Mono<String> first = Flux.just("one", "two")
        .next();
```

`next()` lấy phần tử đầu tiên và không yêu cầu source chỉ phát một phần tử. Nếu nghiệp vụ cần đúng một item, giữ `single()` và sửa source/contract. Debugging cho biết dòng tạo operator; nó không quyết định semantics đúng thay ứng dụng.

### 13.2. Ví dụ: lỗi nằm trong lambda

```java
Mono<Integer> result = Mono.just(10)
        .map(value -> value / 0)
        .checkpoint("pricing.divide");
```

Root cause là phép chia cho zero trong lambda. Checkpoint giúp tìm vị trí chain được tạo; exception gốc vẫn là `ArithmeticException`.

### 13.3. Ví dụ: lỗi từ upstream

```java
Mono<String> result = remoteClient.fetch()
        .checkpoint("catalog.remote.fetch")
        .onErrorMap(error ->
                new CatalogUnavailableException("catalog unavailable", error));
```

Checkpoint nằm trước `onErrorMap`, nên có thể bổ sung traceback cho lỗi upstream trước khi lỗi được wrap. Nếu cần traceback ở lớp boundary sau mapping, đặt checkpoint cuối chain theo mục tiêu quan sát và kiểm thử cause/suppressed behavior thực tế.

## 14. Lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ đọc stack trace runtime | Chỉ thấy Reactor internals hoặc subscription site | Đọc assembly traceback hoặc thêm checkpoint |
| Bật `Hooks.onOperatorDebug()` sau khi chain đã assemble | Chain cũ không có capture tương ứng | Bật hook thật sớm trước khi tạo Publisher |
| Dùng global hook cho mọi request | Tăng chi phí assembly trên toàn process | Dùng checkpoint nhẹ hoặc Agent |
| Đặt checkpoint trước operator gây lỗi downstream | Checkpoint không quan sát lỗi đó | Đặt checkpoint sau phần chain cần theo dõi |
| Dùng description `"checkpoint"` cho nhiều nơi | Không tìm ra chain cụ thể | Dùng operation ID đủ duy nhất |
| Dùng `checkpoint()` ở mọi operator | Traceback dài và chi phí stack capture tăng | Đặt ở service/adapter boundaries có ý nghĩa |
| Cho rằng checkpoint sửa hoặc retry lỗi | Lỗi gốc vẫn xảy ra | Sửa cause hoặc thiết kế retry riêng |
| Chỉ duyệt `getCause()` | Bỏ sót suppressed traceback | Duyệt `getSuppressed()` và `Exceptions.isTraceback` |
| So sánh nguyên văn toàn bộ stack trace trong test | Test dễ vỡ theo line/version | Assert exception type và có traceback |
| Không reset global hook trong test | Rò global state sang test khác | `try/finally` với `Hooks.resetOnOperatorDebug()` |
| Chạy test thay đổi hook song song | Kết quả phụ thuộc thứ tự | Cô lập test/global resource hoặc chạy tuần tự |
| Dùng `ReactorDebugAgent.init()` sau khi Spring tạo bean | Một số call sites đã load không được instrument | Init trước `SpringApplication.run` |
| Gọi `processExistingClasses()` luôn luôn | Startup/test chậm thêm vài giây | Chỉ dùng khi class đã load và callsite chưa instrument |
| JVM không cho self-attach | Agent init thất bại | Dùng `-javaagent` lúc khởi động |
| Bật cả Agent và global hook không cần thiết | Tăng độ phức tạp và chi phí debug | Chọn một cơ chế toàn cục theo mục tiêu |
| Log toàn bộ payload/headers khi debug | Lộ token hoặc dữ liệu cá nhân | Log route, correlation ID, exception type và metadata đã mask |
| Tái sử dụng exception có suppressed traceback | Suppressed list có thể tích lũy | Tạo exception mới cho mỗi failure |
| Dùng `block()` để giữ stack trace đồng bộ | Có thể chặn event loop và đổi semantics | Giữ reactive pipeline và thêm checkpoint |
| Nghĩ Agent instrument mọi thư viện bên thứ ba | Kỳ vọng sai phạm vi callsite | Xác định class nào được instrument và dùng checkpoint ở boundary |

## 15. Checklist vận hành

### Assembly và checkpoint

- Đã xác định đoạn chain cần quan sát?
- Checkpoint nằm sau phần upstream cần bắt lỗi?
- Description có đủ duy nhất nhưng không chứa secret/PII?
- Chọn marker nhẹ hay full stack dựa trên nhu cầu?
- Có regression test cho lỗi đã phát hiện?

### Global hook

- Hook được bật trước khi assemble Publisher?
- Đã đánh giá chi phí trên toàn process?
- Chỉ bật ở môi trường có chủ đích?
- Có reset trong test hoặc công cụ chẩn đoán?
- Không thay đổi global hook theo từng request?

### ReactorDebugAgent

- `reactor-tools` version tương thích Reactor BOM?
- `init()` chạy trước Spring Boot context?
- JVM có cho phép self-attach?
- Có phương án `-javaagent` nếu self-attach bị chặn?
- Chỉ gọi `processExistingClasses()` khi thực sự cần?
- Đã đo startup/latency và kiểm tra class call sites được instrument?

### Logging và security

- Log giữ nguyên root cause?
- Traceback được nhận diện trong suppressed exceptions?
- Không log raw token, password, cookie hoặc payload nhạy cảm?
- Không dùng static exception có thể tích lũy suppressed tracebacks?
- Log appender không chặn event loop?

### Testing

- Có test success path?
- Có test error path và exception type?
- Có test checkpoint tạo traceback?
- Có test global hook bật trước assembly và reset sau test?
- Có integration test qua WebTestClient nếu lỗi đi qua HTTP?
- Test không phụ thuộc stack trace line number cố định?
- Global hook tests không chạy song song với test thay đổi hook?

## 16. Bài tập tự kiểm tra

**Bài 1.** Vì sao stack trace runtime của Reactor thường không chỉ thẳng tới dòng khai báo `map` hoặc `flatMap`?

**Đáp án:** Vì execution bất đồng bộ; stack trace thường phản ánh nơi tín hiệu được xử lý/subscription và operator internals, còn chain có thể được assemble ở một method khác.

**Bài 2.** `checkpoint()` khác `checkpoint("orders.lookup")` thế nào?

**Đáp án:** `checkpoint()` thu full assembly stack cho chain; `checkpoint(String)` thêm marker description nhẹ và dựa vào description để tìm vị trí, không capture full stack tại checkpoint.

**Bài 3.** `checkpoint("id", true)` có ý nghĩa gì?

**Đáp án:** Thêm description và buộc full stack trace; `false` dùng marker nhẹ.

**Bài 4.** Vì sao checkpoint thường được đặt gần cuối đoạn chain cần theo dõi?

**Đáp án:** Nó chỉ quan sát lỗi truyền từ upstream qua checkpoint; lỗi phát sinh downstream sau checkpoint không được checkpoint đó bổ sung traceback.

**Bài 5.** `Hooks.onOperatorDebug()` phải bật khi nào?

**Đáp án:** Trước khi các `Mono`/`Flux` cần quan sát được assemble; thường bật ở đầu `main`.

**Bài 6.** Vì sao global hook tốn chi phí?

**Đáp án:** Nó capture stack trace tại operator assembly cho các chain được tạo sau khi hook bật, tác động rộng tới process.

**Bài 7.** API nào reset operator debug hook?

**Đáp án:** `Hooks.resetOnOperatorDebug()`.

**Bài 8.** `ReactorDebugAgent.init()` nên chạy ở đâu trong Spring Boot?

**Đáp án:** Trước `SpringApplication.run(...)`, để agent instrument call sites khi class ứng dụng được load.

**Bài 9.** Khi nào gọi `processExistingClasses()`?

**Đáp án:** Khi agent được khởi tạo muộn và cần instrument lại các class đã load; thao tác có thể mất vài giây nên không gọi thường xuyên nếu không cần.

**Bài 10.** Làm sao xác định suppressed exception có phải Reactor traceback?

**Đáp án:** Duyệt `Throwable.getSuppressed()` và dùng `Exceptions.isTraceback(Throwable)`.

**Bài 11.** Nếu self-attach không hoạt động trên JVM thì dùng cách nào?

**Đáp án:** Khởi động JVM với `-javaagent:reactor-tools.jar`.

**Bài 12.** `checkpoint` có làm request tự retry khi remote service lỗi không?

**Đáp án:** Không. Nó chỉ thêm thông tin assembly vào lỗi; retry là chính sách khác và cần được thiết kế theo semantics nghiệp vụ.

## 17. Ghi nhớ

- Reactor phân biệt assembly, subscription và signal execution; runtime stack trace thường không đủ để tìm nơi chain được khai báo.
- Assembly traceback bổ sung vị trí tạo operator và các điểm chain đã quan sát lỗi.
- `checkpoint()` thu full stack cho một chain; `checkpoint(String)` dùng marker nhẹ; `checkpoint(String, true)` có description và full stack.
- Checkpoint chỉ bắt lỗi upstream truyền qua nó; đặt sau phần chain cần quan sát.
- `Hooks.onOperatorDebug()` là global hook, phải bật trước khi assemble chain và có chi phí capture stack trên các operator được tạo sau đó.
- `Hooks.resetOnOperatorDebug()` gỡ global debug hook.
- `ReactorDebugAgent` từ `reactor-tools` instrument call sites qua Java Agent/ByteBuddy; gọi `init()` trước Spring Boot startup.
- `processExistingClasses()` dành cho class đã load, có thể mất vài giây; không dùng thường xuyên nếu init sớm được.
- Nếu JVM không hỗ trợ self-attach, dùng `-javaagent` khi khởi động.
- Traceback thường là suppressed exception; dùng `Exceptions.isTraceback` để nhận diện.
- `log()` quan sát signal/demand/cancel; `checkpoint` giúp tìm assembly site. Hai công cụ phục vụ câu hỏi khác nhau.
- Không log payload/credential nhạy cảm, không giữ static exception có suppressed traceback, và không dùng `block()` để làm code reactive trông đồng bộ.
- Chọn checkpoint cho một chain, global hook cho reproduction có kiểm soát, Agent cho assembly debugging rộng với chi phí runtime thấp hơn global stack capture.

**Quy tắc chẩn đoán:** tìm exception gốc trước, xác định chain được assemble ở đâu, đặt checkpoint ở đúng boundary, rồi chỉ bật global hook hoặc Agent khi phạm vi cần quan sát rộng hơn.

## 18. Tài liệu chính thức

- Project Reactor Reference — **Debugging Reactor**: https://projectreactor.io/docs/core/3.6.11/reference/debugging.html
- Project Reactor 3 Reference — **Activating Debug Mode, checkpoint and ReactorDebugAgent**: https://projectreactor.io/docs/core/release/reference/debugging.html
- Reactor Core 3.6.11 Javadoc — **`Flux.checkpoint()` / `checkpoint(String)` / `checkpoint(String, boolean)`**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html
- Reactor Core Javadoc — **`Hooks.onOperatorDebug()` and `resetOnOperatorDebug()`**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Hooks.html
- Reactor Core Javadoc — **`Exceptions.isTraceback` and composite exception utilities**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/Exceptions.html
- Reactor Tools — **ReactorDebugAgent and ByteBuddy instrumentation**: https://projectreactor.io/docs/core/release/reference/debugging.html#production-ready-global-debugging
- Spring Boot 3.3.5 — **Dependency versions and Reactor BOM**: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-dependencies/3.3.5
- Spring Framework — **WebFlux reactive application infrastructure**: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html