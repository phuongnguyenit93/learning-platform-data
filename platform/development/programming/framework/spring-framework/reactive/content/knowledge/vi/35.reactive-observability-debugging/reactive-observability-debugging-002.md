# Phân biệt stack trace lúc lắp ghép với lúc thực thi trong Spring WebFlux và Project Reactor

## 1. Mục tiêu của bài học

Một lỗi trong ứng dụng Spring WebFlux có thể xuất hiện trên một thread khác, vào một thời điểm khác, rất xa dòng code đã định nghĩa chuỗi xử lý. Vì vậy, khi đọc lỗi của `Mono` hoặc `Flux`, cần phân biệt hai câu hỏi:

1. **Lúc thực thi (execution/subscription):** Exception được ném hoặc tín hiệu `onError` được phát ở đâu, trong bối cảnh xử lý nào?
2. **Lúc lắp ghép (assembly):** Operator hoặc reactive pipeline dẫn tới lỗi đã được khai báo ở dòng code nào?

Stack trace Java thông thường chủ yếu trả lời câu hỏi thứ nhất. **Assembly traceback** do Reactor hỗ trợ giúp trả lời câu hỏi thứ hai. Hai thông tin bổ sung cho nhau; không được xem assembly traceback là một exception nghiệp vụ khác hoặc là bằng chứng lỗi đã xảy ra khi ứng dụng vừa tạo Mono/Flux.

Bài học này tập trung vào việc hiểu thời điểm lắp ghép so với thời điểm subscribe, cách đọc error và suppressed traceback, lựa chọn `checkpoint`, `Hooks.onOperatorDebug()`, `ReactorDebugAgent` và phương pháp chẩn đoán lỗi trong chuỗi WebFlux.

## 2. Sơ đồ hai thời điểm

~~~text
          ASSEMBLY TIME                             EXECUTION TIME
     (xây mô tả pipeline)                    (subscribe, chạy signal)

   buildOrderPipeline()                              HTTP request
          |                                                |
          v                                                v
    repository.findById(id)                              subscribe
          |                                                |
          v                                                v
    .flatMap(this::enrich)                        subscribe upstream
          |                                                |
          v                                                v
    .map(this::toDto)  --------------------------> mapper receives item
          |                                                |
          v                                                v
    .checkpoint("order-read")                           mapper throws
          |                                                |
          v                                                v
    return Mono<OrderDto>                           onError(exception)
                                                           |
                                                           v
                                                  WebFlux error handler
~~~

Một lời gọi `map(fn)` thường **không chạy fn ngay lúc lắp ghép**. Nó tạo operator lưu hàm `fn` để gọi sau khi có signal. Nếu `fn` ném `IllegalStateException` tại thời điểm dữ liệu đến, Java stack trace sẽ phản ánh lời gọi hàm trong pipeline đang thực thi. Trong khi đó assembly traceback có thể chỉ tới dòng `.map(this::toDto)` của service khi Mono được tạo.

### 2.1. Cần hiểu “thường” thay vì tuyệt đối

Không phải mọi code trong method xây Publisher đều hoàn toàn lazy:

- Biểu thức Java được đánh giá **trước** khi truyền vào `Mono.just(value)` hoặc `Flux.just(values)`.
- Một số operator validate tham số khi được gọi; ví dụ truyền `null` cho mapper có thể bị từ chối ngay lúc assembly.
- `Mono.fromCallable(supplier)` và `Mono.defer(supplier)` trì hoãn thực thi hàm tới lúc có subscription.
- Một hot source, một Future đã khởi chạy hoặc tác vụ bên ngoài có thể bắt đầu trước khi có Reactor subscriber.
- `Mono.defer` có thể lắp ghép **một chuỗi con mới bên trong subscription**, nên assembly của chuỗi con diễn ra muộn hơn.

Do đó, mô hình “assembly trước, execution sau” mô tả phần lớn pipeline cold/declarative nhưng không phải tuyên bố mọi thứ trong chương trình đều lazy.

## 3. Assembly time là gì?

Assembly xảy ra khi code gọi các operator để xây chuỗi:

~~~java
Flux<Integer> numbers = Flux.just("10", "20", "bad")
        .map(Integer::parseInt)
        .filter(number -> number > 10);
~~~

Ở bước này:

- Java gọi `Flux.just`, `map` và `filter`.
- Reactor tạo các đối tượng publisher/operator tương ứng.
- Lambda `Integer::parseInt` chưa chạy trên dữ liệu.
- Lambda `number -> number > 10` chưa chạy trên dữ liệu.
- Chưa có một subscriber yêu cầu các phần tử.

Nếu dòng trên nằm trong method `createReportFlow`, assembly site có thể là những dòng trong `createReportFlow`, dù lỗi sau đó xảy ra khi request từ controller được xử lý trên thread khác.

### 3.1. Assembly site không phải “vị trí tạo exception”

Assembly stack được **ghi nhận trước** (nếu bật tracing thích hợp) để đến lúc lỗi xảy ra Reactor có thể bổ sung:

- Operator nào đã được khởi tạo.
- Class/method và dòng code nào xây operator.
- Những operator nào quan sát tín hiệu lỗi khi nó đi qua.
- Đường dẫn của error signal trong chuỗi.

Assembly traceback không có nghĩa các hàm map/filter đã chạy ở thời điểm assembly. Nó là **ảnh chụp vị trí định nghĩa operator**.

## 4. Execution time là gì?

Execution bắt đầu khi Publisher được subscribe. Với request/response WebFlux, framework thường subscribe Publisher được trả về từ controller/handler. Với code độc lập, subscription có thể được kích hoạt bởi `subscribe()`, `block()` hoặc `StepVerifier`.

~~~java
Flux<Integer> numbers = Flux.just("10", "bad")
        .map(Integer::parseInt);

// Chưa parse bất kỳ chuỗi nào ở trên.

numbers.subscribe(
        value -> System.out.println("value=" + value),
        error -> System.out.println(
                "error=" + error.getClass().getSimpleName()));
~~~

Khi subscribe, Reactor bắt đầu phát dữ liệu; mapper được gọi cho `10` rồi `bad`, lúc đó `NumberFormatException` được chuyển thành `onError`.

Sự kiện đáng nhớ:

| Thời điểm | Việc gì xảy ra? |
| --- | --- |
| Assembly | `map` được thêm vào chain |
| Subscription | Các Subscriber và Subscription được thiết lập |
| Demand | Downstream yêu cầu phần tử bằng `request(n)` |
| onNext | Dữ liệu tới, mapper/filter/flatMap chạy |
| onError | Exception được biến thành error signal |
| onComplete | Nguồn phát thành công và kết thúc |
| cancel | Downstream không muốn nhận thêm dữ liệu |

**Lỗi runtime trong mapper không đồng nghĩa với exception Java bị ném từ lời gọi `.map(...)` ở thời điểm assembly.**

## 5. Stack trace Java bình thường cho thấy điều gì?

Ví dụ:

~~~java
Mono<OrderDto> flow = repository.findById(orderId)
        .map(this::convertToDto);

return flow;
~~~

Nếu `convertToDto` ném exception, phần stack trace runtime có thể chứa:

~~~text
java.lang.IllegalStateException: invalid order data
    at example.orders.OrderService.convertToDto(OrderService.java:87)
    at reactor.core.publisher.FluxMapFuseable$MapFuseableSubscriber.onNext(...)
    at reactor.core.publisher.MonoJust.subscribe(...)
    at ...
~~~

Đây là **mẫu minh họa**; tên lớp Reactor, thứ tự frame và số dòng sẽ thay đổi theo version, fusion, scheduler, loại nguồn và cách logging.

Stack trace runtime giúp xác định:

- Loại lỗi và thông điệp gốc.
- Hàm user code ném lỗi nếu exception được tạo trực tiếp tại đó.
- Operator/subscriber nào đang thực thi.
- Một phần call stack Java tại thời điểm lỗi.

Nhưng nó có thể **không chỉ ra** dòng service/controller nào đã lắp ghép chuỗi nếu luồng chạy qua boundary bất đồng bộ, scheduler, callback, subscription được tạo từ vị trí khác hoặc code dùng shared helper pipelines.

Ví dụ, `Flux.single()` có thể ném `IndexOutOfBoundsException` khi nguồn phát hơn một phần tử. Stack trace có thể chứa rất nhiều frame `MonoSingle`, `FluxFlatMap`, `FluxMap` mà chưa làm rõ application code ở đâu đã thêm `.single()` không phù hợp.

## 6. Assembly traceback bù đắp thông tin còn thiếu

Reactor hỗ trợ **assembly tracing**: ghi lại nơi operator được tạo để bổ sung khi upstream phát lỗi.

Một enhanced error có thể có các phần:

~~~text
java.lang.IndexOutOfBoundsException: Source emitted more than one item
  at reactor.core.publisher.MonoSingle$SingleSubscriber.onNext(...)
  Suppressed: reactor.core.publisher.FluxOnAssembly$OnAssemblyException:
Assembly trace from producer [reactor.core.publisher.MonoSingle]:
  reactor.core.publisher.Flux.single(...)
  example.orders.OrderService.buildPipeline(OrderService.java:42)
Error has been observed at the following site(s):
  *______Flux.single   at example.orders.OrderService.buildPipeline(...)
  |_     Mono.flatMap  at example.orders.OrderController.read(...)
Original Stack Trace:
  ...
~~~

Đây là **hình thức minh họa**, không phải output cố định. Reactor có thể thay đổi định dạng, dấu biểu diễn nhánh và tên operator qua các phiên bản.

Cách đọc:

1. **Exception chính:** `IndexOutOfBoundsException` mô tả loại lỗi thật.
2. **Assembly trace from producer:** dòng code đã tạo operator liên quan (ví dụ `.single()`).
3. **Error has been observed...:** các operator trong đường truyền đã thấy error signal.
4. **Original Stack Trace:** lời gọi thực tế và frame trên đường thực thi.
5. **Suppressed traceback:** dữ liệu debug được đính kèm; thường không phải một lỗi thứ hai.

### 6.1. “Producer” là nơi lỗi phát sinh theo pipeline

Nếu lỗi từ `Flux.single()` vì có quá một phần tử, assembly site đáng xem là nơi gọi `single()`. Nếu map lambda ném, điểm đáng xem là `map` cùng lambda/source dữ liệu. Phần “observed at” còn giúp nhìn đường truyền xuống các operator downstream.

### 6.2. Nhiều nhánh và nhiều lần quan sát

Trong `Mono.when`, `Flux.merge`, `flatMap` hoặc những flow tái sử dụng chung một Publisher, cùng một error có thể đi qua nhiều nhánh. Reactor có thể ghi nhiều observation site hoặc thông tin “observed N times”.

Vì vậy, **đọc phần quan sát như một đồ thị signal**, không coi mỗi dòng trong enhanced trace là một exception độc lập.

## 7. Hooks.onOperatorDebug(): bật assembly tracing toàn cục

Dùng:

~~~java
Hooks.onOperatorDebug();
~~~

Phải bật **trước khi các operator cần quan sát được tạo**. Thường đặt ở lúc application bootstrap:

~~~java
public static void main(String[] args) {
    Hooks.onOperatorDebug();
    SpringApplication.run(MyWebFluxApplication.class, args);
}
~~~

Khi hook được bật, Reactor can thiệp vào việc lắp ghép operator để capture stack trace. Sau này, nếu error signal chạy qua operator đã được instrument, lỗi có thêm traceback.

### 7.1. Tại sao bật trước assembly?

Trình tự sau không cung cấp đầy đủ trace cho pipeline đã tạo trước hook:

~~~java
Flux<Integer> flow = Flux.just("10", "bad")
        .map(Integer::parseInt);

Hooks.onOperatorDebug(); // Quá muộn cho map đã được tạo.

flow.subscribe();
~~~

Hook chỉ ảnh hưởng các operator được **lắp ghép sau khi hook có hiệu lực**. Nó không quay ngược thời gian để tái tạo stack trace của operator cũ.

### 7.2. Chi phí và phạm vi

Global debug:

- Ghi stack trace cho rất nhiều operator mới được lắp ghép.
- Tăng chi phí CPU và allocation.
- Có thể làm thay đổi độ trễ và throughput.
- Tác động đến toàn process và các reactive chain khác, không chỉ một request.
- Có ích khi cần khoanh vùng lỗi khó tái hiện trong môi trường kiểm soát.

**Không bật Hooks.onOperatorDebug vô điều kiện trên production hot path**, nhất là hệ thống nhiều request/giây, mà chưa đo performance. Với production, ưu tiên `checkpoint(String)` có mục tiêu hoặc `ReactorDebugAgent` theo deployment model phù hợp.

### 7.3. Tắt hook trong test/demo

~~~java
Hooks.onOperatorDebug();

try {
    runDiagnostic();
}
finally {
    Hooks.resetOnOperatorDebug();
}
~~~

Hook là global process state; phải cleanup sau test để không ảnh hưởng các case khác. Việc reset hook **không làm các Publisher đã lắp ghép trước đó mất snapshot**. Chỉ các operator tạo về sau không còn được instrument.

Không bật/tắt global hook theo từng HTTP request: nó có thể ảnh hưởng request khác đang lắp ghép đồng thời.

## 8. checkpoint(): gắn dấu tại một vị trí được chọn

`checkpoint` là operator để bổ sung thông tin assembly khi lỗi chạy qua nó.

Ba dạng:

~~~java
Mono<Order> a = source.checkpoint();

Mono<Order> b = source.checkpoint(
        "orders:load-by-id");

Mono<Order> c = source.checkpoint(
        "orders:load-by-id", true);
~~~

| Dạng | Nội dung capture | Chi phí | Khi dùng |
| --- | --- | --- | --- |
| `checkpoint()` | Full assembly stack trace | Cao hơn | Điều tra một pipeline cụ thể cần call site |
| `checkpoint("mô-tả")` | Light marker chỉ mang label | Nhẹ hơn | Production hoặc flow đã biết vị trí |
| `checkpoint("mô-tả", true)` | Mô tả cộng full assembly stack | Cao hơn | Debug sâu, cần cả label và call site |
| `checkpoint("mô-tả", false)` | Tương đương light marker | Nhẹ hơn | Nhãn ổn định, dễ truy vết |

### 8.1. checkpoint(String) không lấy đầy đủ stack trace

~~~java
Mono<Order> result = orderRepository.findById(id)
        .flatMap(this::enrich)
        .map(this::validate)
        .checkpoint("orders:load-v2");
~~~

Nếu upstream phát lỗi, enhanced traceback có thể chứa light checkpoint label `orders:load-v2`. Nó **không nhất thiết ghi file và dòng code** nếu chỉ dùng light marker. Vì vậy, đặt label đủ duy nhất để người vận hành tìm lại method/flow.

Label tốt:

- `orders:load-by-id`
- `inventory:reserve-stock`
- `billing:calculate-total`
- `notifications:send-email`

Label chưa tốt:

- `checkpoint`
- `error`
- `service`

Một label quá chung chung không giải đáp được assembly site.

### 8.2. Vị trí checkpoint quyết định lỗi nào được đánh dấu

Đặt checkpoint ở downstream của các operator muốn theo dõi:

~~~java
return repository.findById(id)
        .flatMap(this::enrich)
        .map(this::convert)
        .checkpoint("order-read");
~~~

Nếu lỗi phát sinh trong `findById`, `enrich` hoặc `convert` rồi đi qua checkpoint, marker được bổ sung.

Nếu checkpoint đứng **trước** operator ném lỗi:

~~~java
return repository.findById(id)
        .checkpoint("repository-read")
        .map(this::convert);
~~~

Lỗi do `convert` phát ra **sau checkpoint** sẽ không đi ngược lại qua checkpoint này. Vì vậy marker có thể không xuất hiện trên lỗi từ mapper.

Quy tắc: **checkpoint quan sát error signal đi từ upstream xuống downstream**. Đặt nó gần cuối đoạn logic bạn cần đánh dấu; có thể dùng nhiều checkpoint ở các boundary có ý nghĩa.

### 8.3. Checkpoint không xử lý lỗi thay bạn

`checkpoint` không retry, không convert HTTP status, không swallow exception, không thay `onErrorResume` hoặc `onErrorMap`. Nó là công cụ quan sát.

~~~java
return callPartnerApi()
        .checkpoint("partner:fetch-offers")
        .onErrorMap(
                WebClientResponseException.class,
                error -> new PartnerApiException(
                        "Partner failure", error));
~~~

Đây là snippet minh họa, cần các kiểu `callPartnerApi` và `PartnerApiException` của ứng dụng. Việc `onErrorMap` tạo exception mới có thể thay đổi stack trace chính; giữ cause gốc để vẫn truy được nơi lỗi thật.

### 8.4. Dùng tên ổn định, tránh dữ liệu nhạy cảm

Checkpoint description là metadata có thể đi vào error logs. Không đưa bearer token, mật khẩu, thông tin thẻ hay raw request body vào label. Có thể dùng static route name hoặc mã lỗi nghiệp vụ không nhạy cảm.

Nếu cần correlation ID, giữ trong log/tracing context và chỉ đưa vào checkpoint khi đã kiểm tra privacy và cardinality. Tạo một label mới dài theo từng request có thể tăng allocation và khó tìm kiếm.

## 9. Suppressed exception và Exceptions.isTraceback

Reactor thường thêm assembly traceback dưới dạng suppressed exception của Throwable chính:

~~~java
Throwable[] suppressed = error.getSuppressed();

for (Throwable candidate : suppressed) {
    if (Exceptions.isTraceback(candidate)) {
        System.out.println("Reactor assembly traceback detected");
    }
}
~~~

Điểm cần nhớ:

- Throwable chính vẫn là lỗi cần điều tra, ví dụ NumberFormatException.
- Assembly traceback mô tả operator construction/observation path.
- Suppressed không nhất thiết đồng nghĩa “thất bại thứ cấp”.
- Một Throwable có thể có các suppressed exception khác không liên quan đến Reactor tracing.
- Reactor cũng có thể thêm suppressed marker cho `block()`; đừng đếm mọi suppressed Throwable là assembly trace.

Trong composite error, chẳng hạn nhiều nhánh thất bại và một operator gộp lỗi, danh sách khi unwrap có thể chứa traceback. Reactor cung cấp `Exceptions.unwrapMultipleExcludingTracebacks(error)` để lọc các phần tử trace khi xử lý composite errors.

### 9.1. Không xóa suppressed trace khi logging

Nếu chỉ log `error.getMessage()`:

~~~java
.doOnError(error ->
        log.warn("Request failed: {}", error.getMessage()))
~~~

bạn có thể bỏ mất cause chain, suppressed assembly trace và phần stack hữu ích.

Trong môi trường logging phù hợp:

~~~java
.doOnError(error ->
        log.error("Order pipeline failed", error))
~~~

SLF4J logger thường in throwable đầy đủ nếu sử dụng overload đúng. Tuy nhiên, cần redact dữ liệu nhạy cảm trong message, tags, headers và body trước khi log.

## 10. ReactorDebugAgent: lựa chọn instrument cho production

Ngoài debug hook toàn cục, Reactor cung cấp `ReactorDebugAgent` từ artifact `reactor-tools`. Cách này instrument code bằng Byte Buddy và cho thông tin assembly với chi phí thấp hơn việc tạo Throwable stack trace cho từng operator lúc runtime.

Thêm dependency (version do Reactor BOM/Spring Boot quản lý):

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-tools</artifactId>
</dependency>
~~~

Khởi tạo sớm:

~~~java
import reactor.tools.agent.ReactorDebugAgent;

public static void main(String[] args) {
    ReactorDebugAgent.init();
    SpringApplication.run(MyWebFluxApplication.class, args);
}
~~~

**Chú ý về vòng đời class loading:** agent instrument những class được load sau khi nó khởi tạo. Nếu đã load class trước đó, có `ReactorDebugAgent.processExistingClasses()` nhưng quá trình retransform có thể tốn thời gian. Không gọi nó trong mỗi request.

### 10.1. Hạn chế môi trường

`ReactorDebugAgent` dùng Byte Buddy agent attach; một số JVM/container hạn chế self-attach. Có thể cần chạy với javaagent tùy môi trường:

~~~bash
java -javaagent:reactor-tools.jar -jar app.jar
~~~

Đây là cú pháp minh họa. Phải cung cấp đúng đường dẫn và phiên bản JAR, đồng thời kiểm thử cơ chế agent trong build, container image và runtime.

Instrument lúc build qua Byte Buddy plugin cũng là một phương án. Không tự thêm agent mà không xem chính sách observability, hiệu năng, JVM flags và quy trình triển khai của tổ chức.

### 10.2. So sánh ba cách

| Công cụ | Phạm vi | Chi phí | Phù hợp |
| --- | --- | --- | --- |
| `checkpoint("label")` | Chỉ một vị trí | Thường thấp | Production flow quan trọng |
| `checkpoint()` | Một vị trí, full stack | Cao hơn light | Điều tra case đã khoanh vùng |
| `Hooks.onOperatorDebug()` | Mọi operator lắp ghép sau khi bật | Cao | Local/dev diagnostic |
| `ReactorDebugAgent` | Code được instrument theo agent | Thấp hơn global stack capture | Production observability khi cấu hình agent phù hợp |

Không có công cụ nào thay thế logging, tracing, metrics, error classification hoặc unit/integration tests.

## 11. Ví dụ nhận biết lỗi thực tế trong WebFlux

Giả sử một service có:

~~~java
Mono<OrderDto> getOrder(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)))
            .flatMap(this::fetchDetails)
            .map(this::toDto)
            .checkpoint("orders:get-order");
}
~~~

Có ít nhất ba nhóm lỗi khác nhau:

1. Repository error hoặc empty được chuyển thành `OrderNotFoundException`.
2. `fetchDetails` có thể gọi WebClient và phát `WebClientRequestException` (kết nối) hoặc `WebClientResponseException` (status).
3. `toDto` có thể ném exception do dữ liệu không hợp lệ.

Trong một HTTP request, operator code có thể chạy trên Netty event loop hoặc một Scheduler khác. Runtime trace có thể có nhiều framework frames; checkpoint giúp biết **flow ứng dụng** nào đã lắp ghép những operator mà error đi qua.

### 11.1. Lỗi runtime không phải lúc nào do network

Một HTTP 200 với body sai có thể gây `DecodingException` khi WebClient giải mã JSON. Bên cạnh lỗi kỹ thuật đó, lỗi Java do mapper của bạn ném sau decode vẫn là lỗi ở tầng ứng dụng.

Chẩn đoán theo thứ tự:

- Throwable type và message là gì?
- Cause chain có lỗi HTTP/network/codec không?
- Runtime stack có user method nào ném lỗi?
- Assembly trace trỏ vào operator nào?
- Error được quan sát qua các stage nào?
- Request trace ID, route và service dependency tương ứng là gì?

Đừng nhìn thấy `FluxMapFuseable` rồi kết luận reactor-core có bug; có thể mapper của ứng dụng mới là nơi ném exception.

### 11.2. Kết hợp WebFlux exception handling

`@RestControllerAdvice` và `@ExceptionHandler` có thể chuyển exception thành HTTP response nhất quán. **Đừng làm mất exception gốc trước khi log**:

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException error) {

        return ResponseEntity.badRequest()
                .body(Map.of("code", "BAD_INPUT"));
    }
}
~~~

Đây là snippet minh họa cho code mapping HTTP, không phải hệ thống exception handling hoàn chỉnh. Trong thực tế cần logging có correlation ID, phân biệt lỗi nội bộ và lỗi input, và không trả stack trace hay internals cho browser/client.

Assembly traceback nên dành cho logs/diagnostics phía server, **không đưa vào response body production**.

## 12. Eager evaluation: lỗi xảy ra khi assembly thật

Hai đoạn sau nhìn tương tự nhưng có timing khác nhau.

### 12.1. Eager value

~~~java
Mono<Integer> value =
        Mono.just(Integer.parseInt("oops"));
~~~

Java phải đánh giá `Integer.parseInt("oops")` trước khi gọi `Mono.just`. Vì vậy `NumberFormatException` được ném ngay ở thời điểm tạo publisher; **chưa có Mono hợp lệ để subscribe**.

### 12.2. Deferred supplier

~~~java
Mono<Integer> value =
        Mono.fromCallable(() -> Integer.parseInt("oops"));
~~~

Lúc assembly, Reactor nhận một Callable. `parseInt` chỉ được gọi sau khi subscribe. Exception được biến thành `onError`; do đó có thể dùng `checkpoint` và Reactor error operators để quan sát.

### 12.3. Defer toàn bộ việc tạo Publisher

~~~java
Mono<Integer> value = Mono.defer(() ->
        Mono.just(Integer.parseInt("oops")));
~~~

`Mono.defer` trì hoãn cả việc tạo inner Mono tới subscribe. Ở subscribe time, Java gọi parseInt, lỗi được phát dưới dạng onError của deferred publisher.

Khác biệt với `Mono.just` xuất hiện ngay ở boundary lắp ghép. Khi debug, cần xác định expression nào thực sự được đánh giá ở thời điểm gọi method, không chỉ nhìn type trả về.

### 12.4. fromFuture có thể là nguồn eager

~~~java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(this::loadValue);

Mono<Integer> mono = Mono.fromFuture(future);
~~~

Future có thể chạy trước subscription. Dù Mono chờ/quan sát kết quả của future, công việc bên ngoài đã bắt đầu. Assembly traceback của Mono không tự mô tả đầy đủ call stack bên trong thread pool của future.

Muốn trì hoãn việc tạo future:

~~~java
Mono<Integer> mono = Mono.defer(() ->
        Mono.fromFuture(
                CompletableFuture.supplyAsync(this::loadValue)));
~~~

Đây là snippet minh họa. Dùng Executor và cancellation policy phù hợp trong production, không dùng Common Pool cho blocking I/O không kiểm soát.

## 13. Một Publisher có thể được subscribe nhiều lần

Ví dụ:

~~~java
Mono<Integer> flow = Mono.fromCallable(
        () -> Integer.parseInt("5"))
        .map(i -> i * 2);

Integer first = flow.block();
Integer second = flow.block();
~~~

Hai lần `block()` tương ứng hai subscription đối với pipeline cold. Assembly của `flow` thường chỉ xảy ra một lần, trong khi Callable có thể thực thi hai lần.

Hệ quả:

- **Cùng một assembly site** có thể liên quan tới nhiều lần chạy khác nhau.
- Runtime stack/trace ID giúp phân biệt request/subscription cụ thể.
- Chỉ assembly traceback không đủ để biết subscription nào gây lỗi.
- Nếu dùng `cache()`, `share()` hoặc hot source, subscription và re-execution có semantics khác.
- Nếu code dùng `Mono.defer`, inner operators có thể được lắp ghép lại cho từng subscription.

Đừng đưa raw request ID vào một Publisher dùng chung rồi xem nó đại diện chính xác mọi subscription. Sử dụng Reactor Context hoặc tracing spans để giữ metadata per-subscription.

## 14. Scheduler và lý do runtime stack khác source code

Ví dụ:

~~~java
Mono<String> flow = Mono.fromCallable(
                () -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::normalize)
        .checkpoint("partner:normalize");
~~~

Đây là snippet minh họa, cần `blockingClient` và `normalize` của ứng dụng.

- `subscribeOn` quyết định Scheduler cho subscription/upstream source ở một boundary.
- `publishOn` có thể chuyển downstream processing sang Scheduler khác.
- Lambda có thể chạy trên thread có tên khác với request thread.
- Runtime call stack được ghi tại thời điểm lỗi trên thread đang chạy.
- Assembly trace vẫn chỉ về nơi code tạo operator (nếu đã instrument).

Với API blocking, cần chuyển sang scheduler phù hợp thay vì block event loop. Nhưng scheduler **không tự sửa lỗi logic**; nó chỉ thay đổi nơi công việc được chạy.

### 14.1. Reactor Context khác call stack

Reactor `Context` lưu metadata theo subscription, không phải Java ThreadLocal thuần:

~~~java
Mono<String> identity = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "unknown")));
~~~

Có thể cung cấp context:

~~~java
Mono<String> withTrace =
        identity.contextWrite(ctx ->
                ctx.put("traceId", "req-123"));
~~~

Context giúp correlation trong reactive chains; nó không làm assembly stack trace tự hiện đầy đủ hoặc thay thế distributed tracing. Với production, dùng tracing framework và context propagation chính thức.

## 15. log(), doOnError và checkpoint phục vụ mục tiêu khác nhau

| API | Quan sát điều gì? | Tác động |
| --- | --- | --- |
| `log("stage")` | subscribe/request/onNext/onError/onComplete/cancel signals | Có chi phí log mỗi tín hiệu |
| `doOnError(error -> ...)` | Side effect khi error chạy qua stage | Không thay đổi signal nếu callback bình thường |
| `checkpoint("stage")` | Label của operator chain cho enhanced traceback | Light assembly marker |
| `checkpoint()` | Assembly site full trace | Snapshot stack cho stage |
| `Hooks.onOperatorDebug()` | Assembly toàn cục của operator mới | Overhead cao hơn |
| Distributed tracing | Request xuyên service, latency/span | Không thay thế source call-site tracing |
| Metrics | Counts, latency, errors, pool saturation | Không chứa full stack |

Ví dụ:

~~~java
return fetchOrders()
        .log("orders-source")
        .flatMap(this::enrichOrder)
        .checkpoint("orders:enrich")
        .doOnError(error ->
                log.error("Orders request failed", error));
~~~

Đoạn minh họa giả định có method `fetchOrders` và `enrichOrder`. Tắt/giảm `log()` ở luồng có PII hoặc nhiều message vì có thể tạo log volume rất lớn. Chỉ log metadata, không log toàn bộ payload có thể chứa secret.

`doOnError` là hook quan sát. Không dùng nó để `subscribe()` một luồng khác hoặc thay đổi contract lỗi; dùng `onErrorMap`, `onErrorResume` nếu thật sự cần biến đổi signal.

## 16. Chương trình Java 17+ chạy được: tự kiểm chứng hai loại stack trace

Chương trình dưới đây so sánh:

1. Pipeline bình thường: error xảy ra ở lúc execute, không có Reactor assembly traceback.
2. Pipeline có `checkpoint("label", true)`: cùng error nhưng có assembly traceback.
3. Pipeline được tạo **sau** `Hooks.onOperatorDebug()`: error có assembly traceback toàn cục.
4. `Mono.just(Integer.parseInt("bad"))`: lỗi xảy ra ngay khi tạo Publisher.
5. `Mono.fromCallable(...)`: lỗi xảy ra khi subscribe.

Chương trình chỉ in **tóm tắt ổn định** thay vì in toàn bộ stack trace vốn phụ thuộc Reactor/JVM version.

### 16.1. Cấu trúc dự án

~~~text
reactor-assembly-trace-demo/
  pom.xml
  src/main/java/example/debug/AssemblyTraceDemo.java
~~~

Yêu cầu JDK 17+, Maven 3.6.3+ và Spring Boot 4.1.2 BOM để quản lý reactor-core.

### 16.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactor-assembly-trace-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.3. AssemblyTraceDemo.java

~~~java
package example.debug;

import java.time.Duration;
import java.util.Arrays;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Hooks;
import reactor.core.publisher.Mono;

public final class AssemblyTraceDemo {

    private static Flux<Integer> build(
            String label, boolean fullCheckpoint) {

        System.out.println("assembly:" + label);

        Flux<Integer> values = Flux.just("12", "bad")
                .map(text -> {
                    System.out.println(
                            "execute:" + label + ":" + text);
                    return Integer.parseInt(text);
                });

        if (fullCheckpoint) {
            return values.checkpoint(
                    "parse-stage-" + label, true);
        }

        return values;
    }

    private static boolean hasTraceback(Throwable error) {
        return Arrays.stream(error.getSuppressed())
                .anyMatch(Exceptions::isTraceback);
    }

    private static void expectParseFailure(
            String label,
            Flux<Integer> pipeline,
            boolean expectAssemblyTrace) {

        try {
            pipeline.collectList()
                    .block(Duration.ofSeconds(3));

            throw new AssertionError(
                    "Expected NumberFormatException");
        }
        catch (NumberFormatException error) {
            boolean traced = hasTraceback(error);

            if (traced != expectAssemblyTrace) {
                throw new AssertionError(
                        "Wrong traceback flag: " + traced, error);
            }

            System.out.println(
                    "error:" + label + ":"
                    + error.getClass().getSimpleName()
                    + ":traceback=" + traced);
        }
    }

    private static void eagerVersusLazy() {
        try {
            Mono<Integer> ignored =
                    Mono.just(Integer.parseInt("bad"));

            throw new AssertionError(
                    "Expected eager parse failure");
        }
        catch (NumberFormatException error) {
            System.out.println("eager:thrown-at-assembly");
        }

        Mono<Integer> lazy =
                Mono.fromCallable(() -> Integer.parseInt("bad"));

        System.out.println("lazy:assembled");

        try {
            lazy.block(Duration.ofSeconds(3));
            throw new AssertionError(
                    "Expected deferred parse failure");
        }
        catch (NumberFormatException error) {
            System.out.println("lazy:thrown-at-subscription");
        }
    }

    public static void main(String[] args) {
        Flux<Integer> baseline = build("base", false);

        System.out.println("before-subscription");
        expectParseFailure("base", baseline, false);

        Flux<Integer> marked = build("checkpoint", true);
        expectParseFailure("checkpoint", marked, true);

        Hooks.onOperatorDebug();

        try {
            Flux<Integer> global = build("global", false);
            expectParseFailure("global", global, true);
        }
        finally {
            Hooks.resetOnOperatorDebug();
        }

        eagerVersusLazy();
    }
}
~~~

### 16.4. Chạy

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.debug.AssemblyTraceDemo
~~~

**Stdout dự kiến (chỉ các dòng do chương trình in, bỏ qua log khác từ Maven/runtime):**

~~~text
assembly:base
before-subscription
execute:base:12
execute:base:bad
error:base:NumberFormatException:traceback=false
assembly:checkpoint
execute:checkpoint:12
execute:checkpoint:bad
error:checkpoint:NumberFormatException:traceback=true
assembly:global
execute:global:12
execute:global:bad
error:global:NumberFormatException:traceback=true
eager:thrown-at-assembly
lazy:assembled
lazy:thrown-at-subscription
~~~

Giải thích:

- `assembly:base` xuất hiện trước khi subscribe; chưa có parse nào.
- `execute:base:...` chỉ xuất hiện khi collectList/block subscribe.
- Baseline không được instrument bằng checkpoint hoặc debug hook, nên không có Reactor assembly traceback.
- Pipeline có full checkpoint bổ sung suppressed traceback, được nhận diện bằng `Exceptions.isTraceback`.
- Global hook được bật trước khi tạo pipeline `global`, nên pipeline mới có assembly tracing.
- `Mono.just(Integer.parseInt("bad"))` đánh giá argument ngay lúc tạo Publisher.
- `Mono.fromCallable(...)` chỉ parse khi subscribe.

Ví dụ dùng `block(Duration)` tại boundary của chương trình command-line để dễ quan sát. Trong controller hoặc service chạy trên Netty event loop, không dùng `block()`; hãy trả Mono/Flux cho WebFlux subscribe.

## 17. Kiểm thử bằng StepVerifier thay vì block trong service

Nếu đang viết JUnit test, có thể kiểm tra lỗi mà không cần blocking service method:

~~~java
@Test
void capturesAssemblyCheckpoint() {
    Flux<Integer> source = Flux.just("1", "oops")
            .map(Integer::parseInt)
            .checkpoint("parse-in-test", true);

    StepVerifier.create(source)
            .expectNext(1)
            .expectErrorSatisfies(error -> {
                assertInstanceOf(
                        NumberFormatException.class, error);

                assertTrue(Arrays.stream(error.getSuppressed())
                        .anyMatch(Exceptions::isTraceback));
            })
            .verify();
}
~~~

Đoạn code giả định có JUnit Jupiter, reactor-test, `assertInstanceOf`, `assertTrue` và imports tương ứng. Nó minh họa kiểm tra cả exception chính và assembly metadata. Đừng assert toàn bộ chuỗi stack trace, vì file/line/operator names có thể đổi khi refactor hoặc nâng version.

Nếu cần kiểm tra nguyên nhân thuộc vùng service code, đặt breakpoint hoặc kết hợp một assertion trên label của checkpoint. Không dùng stack trace text làm business contract.

### 17.1. Test eager vs deferred semantics

~~~java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> lazy = Mono.fromCallable(() ->
        counter.incrementAndGet());

assertEquals(0, counter.get());

StepVerifier.create(lazy)
        .expectNext(1)
        .verifyComplete();

assertEquals(1, counter.get());
~~~

Đây là đoạn test minh họa, cần `reactor-test` và JUnit imports. Nó giúp chứng minh một Callable chỉ được gọi sau subscription, còn assembly không làm tăng counter.

## 18. Cách đọc lỗi Reactor trên production logs

Quy trình ngắn gọn khi gặp log:

1. **Tìm request:** request/trace ID, route, service dependency và timestamp.
2. **Tìm Throwable gốc:** loại lỗi, message, cause chain.
3. **Xem runtime frames:** user mapper/service, I/O/codec/timeout hoặc Reactor internals nào đang chạy?
4. **Tìm Suppressed / Assembly trace:** có `OnAssemblyException` hoặc light checkpoint không?
5. **Xem operator assembly site:** method/dòng user code đã tạo operator.
6. **Đọc observed path:** error chạy qua những operator nào?
7. **Kiểm tra nguồn dữ liệu:** item, điều kiện, request context đã được redact.
8. **Đối chiếu subscription:** request cụ thể, retry count, Scheduler và cancellation.
9. **Tái hiện:** viết StepVerifier/integration test cho case lỗi.
10. **Sửa nguyên nhân:** thay operator, sửa mapper/contract hoặc I/O policy; không chỉ thêm checkpoint để che lỗi.

### 18.1. Phân biệt các loại lỗi trong WebFlux

| Dấu hiệu | Nguyên nhân thường gặp | Bước điều tra |
| --- | --- | --- |
| `NumberFormatException` trong map | Dữ liệu parse không hợp lệ | Kiểm tra mapper, validation |
| `NullPointerException` trong operator | Null từ mapper hoặc user code | Kiểm tra Reactive Streams cấm onNext(null) |
| `IndexOutOfBoundsException` tại single | Nguồn phát nhiều hơn một item | Xem có dùng sai `single()` không |
| `WebClientResponseException` | Server đã trả status lỗi 4xx/5xx | Xem status và body đã redact |
| `WebClientRequestException` | Lỗi thực hiện request/transport | Xem cause DNS/TCP/TLS/timeout |
| `DecodingException` | JSON/body không giải mã được | Kiểm tra Content-Type và DTO |
| `TimeoutException` | Publisher không có signal trong deadline | Xác định timeout scope |
| `IllegalStateException: block() not supported` | Gọi block trên non-blocking event loop | Compose reactive thay vì block |
| `ErrorCallbackNotImplemented` | Subscribe không có error consumer | Truyền error handler hoặc để framework subscribe |
| Composite exception + traceback | Nhiều nhánh lỗi và tracing metadata | Dùng unwrap phù hợp, lọc tracebacks |

Không suy ra user code lỗi từ tên operator nội bộ duy nhất. Assembly site và runtime cause cần được đọc cùng nhau.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| “map thực thi ngay khi gọi map()” | Operator thường chỉ lưu lambda | Phân biệt assembly và subscription |
| “Stack trace runtime luôn chứa controller method xây flow” | Thread/callback/boundary có thể khác | Dùng checkpoint/assembly trace |
| “Assembly traceback là lỗi mới” | Thường là suppressed metadata | Đọc Throwable gốc trước |
| “Bật debug sau khi tạo Mono vẫn truy ra assembly cũ” | Hook không backfill pipeline đã lắp ghép | Bật trước assembly |
| “Bật global hook an toàn miễn phí” | Capture stack trace tốn CPU/memory | Dùng light checkpoint hoặc agent |
| “checkpoint() và checkpoint(String) giống nhau” | Một cái full stack, một cái light label | Chọn theo nhu cầu |
| “checkpoint đặt ở đâu cũng bắt mọi lỗi” | Lỗi downstream không đi ngược upstream | Đặt sau vùng muốn quan sát |
| “checkpoint retry được lỗi” | Nó chỉ bổ sung trace | Dùng onError... nếu cần đổi handling |
| “Giữ nguyên Throwable static để tiết kiệm allocation luôn tốt” | Tracebacks suppressed có thể tích lũy trên cùng instance | Tạo exception theo event khi phù hợp |
| “Thấy suppressed là có nhiều lỗi business” | Traceback là suppressed metadata | Lọc bằng Exceptions.isTraceback |
| “doOnError tự xử lý exception” | Nó chỉ side effect | Dùng onErrorResume/onErrorMap |
| “Chỉ log getMessage() là đủ” | Mất stack, cause, suppressed | Log Throwable đầy đủ và redact |
| “Reactor Context là ThreadLocal” | Context theo subscription | Dùng deferContextual/contextWrite |
| “Scheduler thay đổi nguyên nhân lỗi” | Nó thay thời điểm/thread, không sửa logic | Tìm user mapper và data contract |
| “Hai block() trên một Mono là cùng execution” | Cold publisher thường chạy lại | Theo dõi từng subscription |
| “Nhiều assembly site nghĩa là nhiều request lỗi” | Có thể một error qua nhiều operator/nhánh | Kết hợp request trace ID |
| “Dùng WebFlux thì không cần integration test” | Network/codec errors khác unit error | Test decoder, timeout và HTTP status |

### 19.1. Tránh tái sử dụng exception mutable kèm assembly trace

Reactor có thể thêm suppressed traceback vào Throwable. Nếu một exception object static được phát lại ở nhiều request, các suppressed thông tin có thể tích lũy và gây memory growth.

Thay vì:

~~~java
private static final RuntimeException SHARED =
        new RuntimeException("partner failed");

Mono<String> alwaysError() {
    return Mono.error(SHARED);
}
~~~

có thể tạo exception mới theo subscription:

~~~java
Mono<String> alwaysError() {
    return Mono.error(() ->
            new RuntimeException("partner failed"));
}
~~~

`Mono.error(Supplier)` trì hoãn tạo exception tới lúc có subscription. Nếu dùng message từ dữ liệu người dùng, bảo đảm redaction và không lộ secret trong error logs.

## 20. Nguyên tắc quan sát và bảo mật

Assembly trace giúp điều tra, nhưng có thể tiết lộ tên class/method/path source trong server logs. Không trả trace đó ra HTTP response production. Không đưa request body, bearer token, cookie hoặc thông tin cá nhân vào checkpoint label.

Với hệ thống lưu lượng lớn:

- Đặt light checkpoint tại các boundary quan trọng.
- Bật full checkpoint có chủ đích khi có incident.
- Dùng tracing spans cho correlation giữa HTTP/WebClient/DB.
- Dùng metric latency/error rate cho mức độ ảnh hưởng.
- Log Throwable đầy đủ ở server nhưng giới hạn sampling, cardinality và retention theo policy.
- Không bật global debug trong toàn cluster nếu chưa kiểm tra overhead.
- Cân nhắc ReactorDebugAgent với runtime constraints và performance benchmark.
- Test trong môi trường có Scheduler, fusion, retry và cancellation gần production.

Sự kiện Reactor `onError` chỉ là terminal signal trong một subscription; HTTP mapping và retry policy còn do ứng dụng quyết định. Assembly tracing không cấp quyền truy cập log dữ liệu nhạy cảm.

## 21. Checklist khi debug một Mono/Flux

- [ ] Đã xác định vị trí lắp ghép Publisher.
- [ ] Đã xác định nơi Publisher được subscribe.
- [ ] Biết mapper/flatMap có chạy lazy hay có expression eager.
- [ ] Đã kiểm tra Throwable chính, message và cause chain.
- [ ] Đã đọc suppressed assembly traceback nếu có.
- [ ] Biết checkpoint đặt trước hay sau operator lỗi.
- [ ] Dùng label checkpoint đủ rõ và không nhạy cảm.
- [ ] Không hiểu nhầm error observation path với các exception riêng.
- [ ] Bật Hooks.onOperatorDebug trước assembly nếu cần debug toàn cục.
- [ ] Reset global hook sau test và không bật/tắt theo request.
- [ ] Đánh giá chi phí global stack capture.
- [ ] Có chiến lược agent nếu cần debugging production rộng.
- [ ] Theo dõi request/trace ID và subscription timing.
- [ ] Không block event loop để debug.
- [ ] Có test tái hiện error, empty và cancellation phù hợp.
- [ ] Không log token/PII hoặc trả stack trace cho API client.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Assembly time là lúc nào?

Là lúc code tạo và ghép các Publisher/operator như `map`, `flatMap`, `filter` và `checkpoint` thành pipeline.

**Câu 2.** Execution time bắt đầu khi nào?

Khi Publisher được subscribe; sau đó nguồn nhận demand và phát signals theo cơ chế reactive.

**Câu 3.** Lambda truyền vào map chạy ngay lúc assembly không?

Thông thường không. Nó chạy khi phần tử đi qua map sau subscription.

**Câu 4.** Stack trace runtime trả lời câu hỏi nào tốt nhất?

Lỗi thực sự được tạo/ném trong call stack đang chạy như thế nào và ở đâu.

**Câu 5.** Assembly traceback trả lời câu hỏi nào?

Operator đã được lắp ghép ở file/method/dòng code nào và error đi qua các operator nào.

**Câu 6.** Tại sao Hooks.onOperatorDebug phải bật trước khi tạo pipeline?

Vì hook capture operator construction lúc assembly, không thể tạo ngược stack của operator đã tồn tại.

**Câu 7.** checkpoint(String) khác checkpoint() thế nào?

checkpoint(String) là light marker không capture full stack; checkpoint() capture assembly stack trace đầy đủ.

**Câu 8.** checkpoint("label", true) dùng khi nào?

Khi cần cả mô tả và full assembly call site cho một vị trí được chọn.

**Câu 9.** Vì sao checkpoint trước map có thể không đánh dấu lỗi do map ném?

Vì lỗi phát sinh downstream và không được truyền ngược qua checkpoint upstream đó.

**Câu 10.** Assembly traceback nằm ở đâu trong Throwable?

Thường được đính kèm dưới dạng suppressed exception và nhận diện bằng `Exceptions.isTraceback`.

**Câu 11.** Dùng suppressed exception có nghĩa là có thêm business error không?

Không. Reactor traceback chủ yếu là metadata chẩn đoán.

**Câu 12.** ReactorDebugAgent ưu điểm gì?

Instrument assembly site với overhead thấp hơn việc capture stack trace đầy đủ ở mọi operator lúc runtime; cần kiểm tra hỗ trợ JVM/Byte Buddy.

**Câu 13.** Vì sao Mono.just(Integer.parseInt("bad")) thất bại sớm?

Java đánh giá argument `parseInt` trước khi gọi Mono.just.

**Câu 14.** Mono.fromCallable khác ở điểm nào?

Callable được thực thi khi subscribe, và exception thành error signal.

**Câu 15.** Hai lần subscribe cùng cold Publisher có cùng execution không?

Không nhất thiết. Nguồn cold có thể chạy lại; assembly site có thể giữ nguyên nhưng subscription khác.

**Câu 16.** Nên dùng gì để liên kết nhiều dịch vụ trong một request?

Distributed tracing/correlation ID cùng structured logs; assembly traceback chỉ là công cụ bổ sung để xác định operator call site.

## 23. Tài liệu tham khảo chính thức

- [Project Reactor — Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html): assembly vs execution, global hooks, tracebacks, checkpoint, debug agent và log().
- [Project Reactor — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): checkpoint(), checkpoint(String), checkpoint(String, boolean), defer, fromCallable, error supplier.
- [Project Reactor — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): assembly markers, pipeline operators và error propagation.
- [Project Reactor — Hooks JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Hooks.html): onOperatorDebug, resetOnOperatorDebug và assembly hooks.
- [Project Reactor — Exceptions JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/Exceptions.html): isTraceback, unwrapMultipleExcludingTracebacks và exception utilities.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier và error assertions.
- [Project Reactor — Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): Reactor Context và tracing.
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): lỗi controller và HTTP exception handling.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): HTTP client reactive và error propagation.
- [Spring Blog — Flight of the Flux: Assembly vs Subscription](https://spring.io/blog/2019/03/06/flight-of-the-flux-1-assembly-vs-subscription): cách hiểu hai thời điểm.
- [Spring Blog — Reactor Debugging Experience](https://spring.io/blog/2019/03/28/reactor-debugging-experience/): kinh nghiệm assembly backtracing.

**Ghi nhớ:** Trong WebFlux, assembly là lúc code tạo chuỗi `Mono`/`Flux`; execution là lúc subscribe và xử lý signals. Runtime stack trace cho biết exception được ném trong quá trình chạy; assembly traceback giúp tìm lại operator được khai báo ở đâu. Dùng `checkpoint("label")` để đánh dấu boundary ít overhead, `checkpoint()` hoặc `checkpoint("label", true)` khi cần full stack, `Hooks.onOperatorDebug()` cho debug toàn cục có kiểm soát và `ReactorDebugAgent` khi cần instrumentation phù hợp production. Luôn đọc Throwable chính, cause, suppressed traceback và request trace ID cùng nhau; không coi assembly trace là một lỗi khác.