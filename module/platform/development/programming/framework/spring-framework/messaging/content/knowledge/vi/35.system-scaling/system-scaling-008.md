# Dừng có kiểm soát và xử lý thông điệp đang thực thi

## Mục tiêu

Một ứng dụng messaging không chỉ cần xử lý request đúng khi đang chạy. Nó còn phải dừng an toàn khi nhận SIGTERM, deploy phiên bản mới, scale down hoặc gặp sự cố. Nếu process dừng ngay trong lúc một request hoặc stream đang thực thi, consumer có thể nhận timeout dù server đã commit một phần nghiệp vụ. Những message chỉ tồn tại trong bộ nhớ cũng có thể bị mất.

Bài học này trình bày cách thiết kế graceful shutdown cho ứng dụng Spring sử dụng RSocket và Reactor. Sau bài này, bạn có thể:

- Phân biệt shutdown tức thời với shutdown có drain.
- Ngăn request mới trong khi cho request đang chạy hoàn tất.
- Theo dõi in-flight Request-Response, Request-Stream và Channel.
- Xử lý completion, error và cancellation để giải phóng bộ đếm chính xác.
- Đặt deadline drain và quyết định việc cần làm khi hết thời gian.
- Phối hợp readiness, Spring lifecycle, transport và Kubernetes.
- Đóng RSocketRequester hoặc server sau khi công việc cần thiết đã kết thúc.
- Bảo đảm retry, idempotency và trạng thái bền vững khi kết nối bị ngắt.

## 1. Vì sao cần graceful shutdown?

Giả sử một client gửi lệnh tạo đơn hàng. Server đã ghi đơn hàng vào database nhưng chưa gửi response thì process nhận SIGTERM. Nếu server đóng kết nối ngay, client có thể chỉ nhìn thấy lỗi transport hoặc timeout. Client không biết đơn hàng đã được tạo hay chưa.

Một stream có thể gặp tình huống tương tự: server đã phát một số phần tử, sau đó process bị dừng trước khi phát phần còn lại. Với Channel, client và server có thể đang trao đổi theo cả hai chiều. Một tác vụ fire-and-forget cũng có thể đang xử lý sau khi client đã gửi message.

Shutdown tức thời có thể gây:

- Request đang thực thi bị lỗi hoặc bị hủy.
- Response bị mất dù side effect đã commit.
- Consumer retry và tạo side effect trùng lặp.
- Stream bị cắt giữa chừng, khiến client không biết phần nào đã được xử lý.
- Message chỉ nằm trong memory bị mất khi process thoát.
- Transaction, file, connection pool hoặc tài nguyên downstream không được giải phóng đúng cách.
- Deployment mới khởi động trong khi instance cũ vẫn chưa hoàn tất việc rời hệ thống.

Graceful shutdown tạo một khoảng thời gian để ứng dụng ngừng nhận công việc mới, hoàn tất công việc đã nhận, ghi trạng thái cần thiết và đóng tài nguyên theo thứ tự.

### 1.1. Phân biệt các tín hiệu kết thúc

Trong Reactor và RSocket, cần phân biệt:

| Tín hiệu | Ý nghĩa | Điều cần làm |
|---|---|---|
| onComplete | Publisher hoàn tất bình thường. | Giảm số in-flight và giải phóng tài nguyên. |
| onError | Publisher kết thúc do lỗi. | Ghi nhận lỗi, lưu trạng thái và giảm số in-flight. |
| cancel | Subscriber yêu cầu dừng stream. | Hủy upstream phù hợp, chạy cleanup và giữ lại side effect đã commit. |
| Process shutdown | Ứng dụng bắt đầu dừng. | Từ chối công việc mới, drain công việc đang chạy rồi đóng transport. |

Cancellation không phải rollback. Nếu server đã commit một thay đổi trước khi nhận CANCEL, thay đổi đó vẫn tồn tại. Tương tự, một request kết thúc bằng error không chứng minh toàn bộ nghiệp vụ chưa được thực hiện.

### 1.2. In-flight là gì?

Một request được xem là in-flight từ lúc ứng dụng chấp nhận xử lý đến khi publisher tương ứng kết thúc bằng complete, error hoặc cancel.

Với Request-Response, thời gian này thường bao gồm validate, gọi service, ghi dữ liệu và tạo response. Với Request-Stream hoặc Channel, thời gian có thể kéo dài cho đến khi stream kết thúc hoặc bị hủy.

Không chỉ đếm thời gian xử lý trước khi phát payload đầu tiên. Một stream đã phát vài phần tử vẫn còn in-flight cho đến khi terminal signal xuất hiện.

Cũng cần phân biệt request đã được nhận với message đã được lưu bền vững. Nếu công việc được chuyển sang queue hoặc worker chạy nền, publisher của handler có thể hoàn tất ngay sau khi lưu message vào outbox/queue. Khi đó, worker phải có cơ chế drain và checkpoint riêng.

## 2. Trình tự shutdown an toàn

Một trình tự tổng quát:

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Spring Application
    participant C as RSocket Clients
    participant S as RSocket Server
    participant D as Database / Queue

    O->>A: SIGTERM / shutdown signal
    A->>A: Mark instance NOT_READY
    A->>A: Stop admission of new work
    C->>S: Existing requests and streams continue
    S->>D: Complete and persist in-flight work
    D-->>S: Commit / durable checkpoint
    S-->>C: Final response or stream completion
    A->>A: Wait for in-flight count = 0
    A->>S: Close listener and connections
    A->>C: Dispose outbound requester
    A->>D: Close remaining resources
    A-->>O: Process exits
~~~

Các bước cần thực hiện:

1. **Rời khỏi traffic mới:** đánh dấu instance không còn sẵn sàng nhận traffic và chờ service discovery/load balancer cập nhật.
2. **Đóng admission:** từ chối request mới, kể cả request đến qua một RSocket connection đã mở từ trước.
3. **Drain:** chờ publisher đang chạy complete hoặc error; xử lý cancellation và lưu trạng thái cần phục hồi.
4. **Áp dụng deadline:** nếu drain quá thời hạn, dừng có kiểm soát theo chính sách và bảo đảm phần chưa hoàn tất có thể được reconciliation.
5. **Đóng transport:** dừng listener, đóng connection và giải phóng requester.
6. **Đóng dependency:** flush outbox/checkpoint, đóng connection pool và các tài nguyên khác.
7. **Thoát process:** hoàn tất trước khi orchestrator buộc kết thúc process.

Thứ tự chính xác giữa các thành phần phụ thuộc cách ứng dụng sở hữu server, queue và worker. Điều quan trọng là không đóng một dependency mà request đang chạy vẫn cần sử dụng.

## 3. Readiness không thay thế admission control

Readiness cho biết instance có nên nhận traffic mới qua service discovery hoặc load balancer hay không. Nó không tự động chặn mọi request đến trên connection hiện tại.

RSocket multiplex nhiều stream trên cùng một connection. Một client có thể mở connection trước thời điểm shutdown rồi tiếp tục gửi request mới trên connection đó. Khi endpoint bị loại khỏi load balancer, connection đã mở vẫn có thể tồn tại.

Vì vậy, ứng dụng cần hai lớp:

- **Readiness:** ngừng định tuyến kết nối mới tới instance.
- **Admission control:** kiểm tra trạng thái shutdown tại ranh giới handler và từ chối công việc mới trên cả connection cũ.

Nếu dùng Spring Boot Actuator Availability, ứng dụng có thể chuyển readiness sang REFUSING_TRAFFIC khi bắt đầu shutdown. Ví dụ:

~~~java
AvailabilityChangeEvent.publish(
    applicationContext,
    this,
    ReadinessState.REFUSING_TRAFFIC
);
~~~

Đoạn code giả định có ApplicationContext và đã import các lớp availability tương ứng từ Spring Boot. Hãy phát tín hiệu khi bắt đầu quy trình shutdown, đủ sớm để endpoint routing có thời gian cập nhật.

Không dựa vào readiness một mình để kết luận rằng không còn request mới. Admission gate trong ứng dụng vẫn phải bảo vệ các route.

## 4. Theo dõi request đang thực thi bằng Reactor

Một cách đơn giản là duy trì bộ đếm in-flight. Mỗi request được chấp nhận sẽ tăng bộ đếm một lần; khi publisher complete, error hoặc cancel, bộ đếm giảm một lần.

Điều quan trọng là đăng ký theo kiểu lazy. Bộ đếm chỉ tăng khi publisher được subscribe và thực sự bắt đầu công việc. Nếu chỉ tạo Mono hoặc Flux nhưng chưa subscribe, chưa có request nào được thực thi.

### 4.1. InFlightRequests

Ví dụ sau cung cấp hai wrapper cho Request-Response và stream:

~~~java
package com.example.messaging;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public class InFlightRequests {

    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final AtomicInteger active = new AtomicInteger();
    private final Sinks.One<Void> drained = Sinks.one();

    public <T> Mono<T> trackMono(Supplier<Mono<T>> work) {
        return Mono.defer(() -> {
            if (!enter()) {
                return Mono.error(new ServiceStoppingException());
            }

            return Mono.defer(work)
                .doFinally(signal -> leave());
        });
    }

    public <T> Flux<T> trackFlux(Supplier<Flux<T>> work) {
        return Flux.defer(() -> {
            if (!enter()) {
                return Flux.error(new ServiceStoppingException());
            }

            return Flux.defer(work)
                .doFinally(signal -> leave());
        });
    }

    private boolean enter() {
        if (!accepting.get()) {
            return false;
        }

        active.incrementAndGet();

        // Kiểm tra lại để tránh race với beginDrain().
        if (accepting.get()) {
            return true;
        }

        leave();
        return false;
    }

    private void leave() {
        if (active.decrementAndGet() == 0 && !accepting.get()) {
            drained.tryEmitEmpty();
        }
    }

    public Mono<Void> beginDrain() {
        accepting.set(false);

        if (active.get() == 0) {
            drained.tryEmitEmpty();
        }

        return drained.asMono();
    }

    public int activeCount() {
        return active.get();
    }

    public static final class ServiceStoppingException
            extends RuntimeException {

        public ServiceStoppingException() {
            super("Service is shutting down");
        }
    }
}
~~~

Bộ đếm được cập nhật theo các quy tắc:

- enter() chỉ cho phép request khi accepting còn true.
- Sau khi tăng bộ đếm, enter() kiểm tra lại trạng thái để xử lý race với beginDrain().
- doFinally chạy khi publisher complete, error hoặc cancel, vì vậy leave() được gọi trên cả ba đường kết thúc.
- beginDrain() chuyển admission sang false và hoàn tất tín hiệu drained khi active bằng 0.
- Request đến sau khi drain bắt đầu nhận ServiceStoppingException.

Việc kiểm tra accepting hai lần là cần thiết. Nếu chỉ kiểm tra một lần rồi tăng bộ đếm, shutdown có thể thấy active bằng 0 và kết thúc drain ngay trước khi request mới được đăng ký.

Sinks.One phát một tín hiệu hoàn tất duy nhất khi không còn công việc. Ví dụ này giả định một ApplicationContext chỉ trải qua một chu kỳ shutdown; nếu ứng dụng có cơ chế stop/start lại cùng bean, cần thiết kế lại việc khởi tạo drain signal theo từng chu kỳ.

### 4.2. Bọc các handler Spring RSocket

Request-Response:

~~~java
@Controller
public class OrderController {

    private final InFlightRequests inFlight;
    private final OrderService service;

    public OrderController(
        InFlightRequests inFlight,
        OrderService service
    ) {
        this.inFlight = inFlight;
        this.service = service;
    }

    @MessageMapping("orders.submit")
    public Mono<OrderAccepted> submit(
        @Payload SubmitOrder command
    ) {
        return inFlight.trackMono(
            () -> service.submit(command)
        );
    }
}
~~~

Request-Stream:

~~~java
@MessageMapping("orders.events")
public Flux<OrderEvent> events(
    @Payload OrderQuery query
) {
    return inFlight.trackFlux(
        () -> service.events(query)
    );
}
~~~

Ví dụ giả định OrderService trả Mono<OrderAccepted> và Flux<OrderEvent>. Các import DTO, service và annotation được lược khỏi snippet thứ hai để tập trung vào cách bọc publisher.

Với Channel, handler nhận một Flux đầu vào và trả Flux đầu ra. Hãy bọc toàn bộ publisher của handler để bộ đếm giữ nguyên trong thời gian trao đổi còn hoạt động. Cần kiểm tra cancellation và completion của cả chiều dữ liệu theo semantics mà handler công bố.

Không tăng/giảm bộ đếm ở nhiều tầng lồng nhau cho cùng một logical request. Chọn một ranh giới rõ ràng, thường là handler hoặc application service entry point, để tránh đếm hai lần.

### 4.3. Không bỏ quên lỗi đồng bộ và publisher rỗng

Supplier có thể ném exception trước khi trả về publisher. Mono.defer và Flux.defer chuyển lỗi đồng bộ đó thành onError, nên doFinally vẫn giải phóng bộ đếm.

Mono.empty() vẫn hoàn tất bình thường và làm bộ đếm giảm. Publisher bị cancel cũng làm bộ đếm giảm. Không cần viết ba nhánh cleanup riêng nếu doFinally bao phủ toàn bộ publisher.

Không tự subscribe bên trong handler để chạy tác vụ nền rồi trả Mono.empty(). Nếu ứng dụng thực sự cần xử lý nền, hãy ghi công việc vào queue/outbox bền vững trước khi kết thúc handler và theo dõi worker bằng một lifecycle riêng.

## 5. Drain khi Spring ApplicationContext đóng

Với server được Spring Boot quản lý theo vòng đời ApplicationContext, có thể dùng ContextClosedEvent để đóng admission và chờ các request đang chạy trước khi các bean lifecycle và transport bị dừng.

Ví dụ:

~~~java
package com.example.messaging;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class DrainOnContextClose {

    private static final Logger log =
        LoggerFactory.getLogger(DrainOnContextClose.class);

    private final InFlightRequests inFlight;

    public DrainOnContextClose(InFlightRequests inFlight) {
        this.inFlight = inFlight;
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        inFlight.beginDrain()
            .timeout(Duration.ofSeconds(25))
            .doOnError(error -> log.warn(
                "Drain deadline reached; active requests: {}",
                inFlight.activeCount(),
                error
            ))
            .onErrorResume(error -> Mono.empty())
            .block();
    }
}
~~~

Trong cấu hình Spring mặc định, event listener được gọi đồng bộ trong quá trình đóng context. Handler chuyển admission sang false, chờ tín hiệu drained tối đa 25 giây rồi cho phép quá trình đóng context tiếp tục.

Nếu ứng dụng thay đổi ApplicationEventMulticaster sang async, không giả định listener này vẫn chặn quá trình shutdown. Khi đó, dùng một lifecycle coordinator có callback và phase ordering được kiểm tra rõ ràng.

Timeout ở đây chỉ giới hạn thời gian chờ drain. Nó không tự động hủy các request đang chạy hoặc rollback database. Khi hết 25 giây, ứng dụng tiếp tục đóng context; transport có thể khiến stream còn lại bị ngắt. Những operation chưa hoàn tất phải có trạng thái bền vững, checkpoint hoặc quy trình reconciliation để phục hồi.

Không dùng ContextClosedEvent làm nơi khởi động một tác vụ nền mới. Nó là thời điểm để ngừng nhận công việc và hoàn tất những gì đã được chấp nhận.

## 6. Cấu hình graceful shutdown của Spring Boot

Với ứng dụng có embedded web server như Tomcat, Jetty, Reactor Netty hoặc Undertow, Spring Boot hỗ trợ graceful shutdown:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

server.shutdown=graceful yêu cầu embedded web server ngừng nhận request mới ở tầng mạng và cho request đang được xử lý có cơ hội hoàn tất. spring.lifecycle.timeout-per-shutdown-phase đặt thời gian chờ cho mỗi lifecycle phase của Spring.

Cần phân biệt phạm vi:

- Với HTTP endpoint thông thường, graceful shutdown của embedded web server giúp xử lý request đang hoạt động.
- Với RSocket qua WebSocket, HTTP server quản lý transport và handshake; các RSocket session sau handshake là kết nối dài hạn, có nhiều stream. Không giả định timeout HTTP tự động drain mọi RSocket stream đang chạy.
- Với RSocket TCP listener độc lập, server.shutdown không phải cấu hình chung để drain RSocket TCP. Cần admission gate và lifecycle quản lý server phù hợp.

Ngay cả khi Spring Boot quản lý server tự động, ứng dụng vẫn nên theo dõi in-flight ở cấp handler nếu cần bảo đảm nghiệp vụ. Hãy kiểm tra transport cụ thể và thử shutdown trong integration test.

## 7. Xử lý khi drain không hoàn tất đúng deadline

Không phải request nào cũng kết thúc trong thời gian shutdown. Một stream có thể chạy hàng giờ, downstream có thể bị treo hoặc một tác vụ có thể đang chờ người dùng.

Cần đặt giới hạn rõ ràng:

- **Request deadline:** thời gian tối đa cho một thao tác nghiệp vụ.
- **Stream lifetime:** thời gian tối đa cho stream dài hạn nếu contract cho phép.
- **Drain deadline:** thời gian instance chờ công việc hiện tại kết thúc khi shutdown.
- **Process termination deadline:** thời gian orchestrator cho phép trước khi buộc dừng process.

Drain deadline phải nhỏ hơn thời gian termination còn lại sau khi trừ thời gian preStop, propagation và cleanup. Không đặt drain deadline dài hơn thời gian process được phép sống.

Khi hết deadline:

1. Ghi metric và log số lượng request còn hoạt động.
2. Lưu checkpoint hoặc trạng thái operation nếu chưa được lưu.
3. Đảm bảo client có thể truy vấn kết quả theo operation ID.
4. Không phát xác nhận thành công nếu chưa commit.
5. Cho phép orchestrator kết thúc process theo deadline cuối cùng.

Không cố giữ process vô hạn để chờ một publisher không bao giờ kết thúc. Cũng không tự đánh dấu mọi request còn lại là thất bại nếu chưa xác minh side effect.

### 7.1. Xử lý theo loại message

| Loại message | Chính sách drain |
|---|---|
| Request-Response | Cho phép handler hoàn tất và commit trước khi gửi response. |
| Request-Stream | Chờ stream complete/error hoặc client cancel; giới hạn lifetime nếu cần. |
| Channel | Ngừng nhận công việc mới theo policy, hoàn tất các item đã nhận và phát kết quả cuối cùng nếu có thể. |
| Fire-and-Forget | Không coi việc gửi frame là xác nhận nghiệp vụ; cần lưu công việc bền vững và có trạng thái truy vấn nếu caller cần bảo đảm. |
| Background worker | Ngừng lấy message mới, hoàn tất hoặc checkpoint message đang xử lý, rồi đóng consumer. |

### 7.2. Poison message và tác vụ không thể phục hồi

Một message có thể lỗi lặp lại do dữ liệu không hợp lệ hoặc dependency không tương thích. Không để một message như vậy chặn toàn bộ drain.

Thiết kế worker cần:

- Giới hạn số lần retry.
- Phân biệt lỗi tạm thời với lỗi vĩnh viễn.
- Ghi message không xử lý được vào dead-letter queue hoặc vùng quarantine nếu kiến trúc hỗ trợ.
- Lưu nguyên nhân, số lần thử và correlation ID.
- Không acknowledge message trước khi trạng thái bền vững được ghi nhận.

Khi shutdown, worker nên ngừng nhận message mới và hoàn tất hoặc trả lại message đang xử lý theo semantics của broker. Chi tiết ack/nack phụ thuộc message broker; RSocket tự nó không cung cấp một durable queue hay delivery guarantee cho nghiệp vụ.

## 8. Đóng client RSocketRequester đúng thứ tự

RSocketRequester là client API và triển khai Disposable. Gọi dispose() sẽ giải phóng requester và connection bên dưới.

Nếu dispose quá sớm, request đang chạy có thể bị lỗi hoặc stream bị cancel. Vì vậy, phía client cũng cần drain:

1. Ngừng tạo request mới.
2. Chờ publisher outbound đang hoạt động complete/error/cancel.
3. Ghi nhận request có kết quả chưa rõ để truy vấn lại sau.
4. Gọi requester.dispose().
5. Đóng các dependency khác.

Ví dụ đóng requester ở bean lifecycle:

~~~java
@Component
public class OrderRSocketClient {

    private final RSocketRequester requester;

    public OrderRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("order-service", 7000);
    }

    public Mono<OrderAccepted> submit(SubmitOrder command) {
        return requester
            .route("orders.submit")
            .data(command)
            .retrieveMono(OrderAccepted.class);
    }

    @PreDestroy
    public void close() {
        requester.dispose();
    }
}
~~~

Đây là ví dụ tối giản. Trong production, đặt việc chờ outbound in-flight ở shutdown coordinator trước khi bean bị destroy. @PreDestroy chỉ nên thực hiện bước dispose cuối cùng sau khi coordinator đã drain; nó không tự biết các publisher khác đang chạy.

Không dispose một requester dùng chung sau mỗi request. Một requester có thể phục vụ nhiều stream đồng thời.

## 9. Đóng RSocket server và listener

Với Spring Boot auto-configuration, RSocket server được quản lý theo vòng đời ApplicationContext. Hãy bảo đảm admission gate đã drain trước khi context dừng server và các bean mà handler cần dùng.

Nếu ứng dụng tự tạo RSocket server bằng RSocket Java, giữ lại handle server trả về khi bind. Sau khi admission đã đóng và in-flight bằng 0 hoặc đã xử lý theo deadline, dispose handle để ngừng listener và giải phóng transport.

Không giả định việc đóng listener tự động làm các request đang chạy hoàn tất. Cần kiểm thử xem transport và server implementation xử lý connection/stream còn mở như thế nào. Với custom lifecycle, sắp xếp phase để admission/drain coordinator chạy trước thao tác đóng listener; nếu hai bean cùng phase, chúng có thể được stop trong cùng nhóm và việc drain có thể không diễn ra trước khi listener đóng.

Với RSocket qua WebSocket, shutdown của web server cũng ảnh hưởng đến connection. Hãy xác định cách đóng session dài hạn và thông báo cho client về việc reconnect hoặc tiếp tục operation.

## 10. Phối hợp với Kubernetes và deployment

Kubernetes gửi tín hiệu dừng khi Pod bị terminate. Ứng dụng có một khoảng thời gian giới hạn trước khi process bị buộc kết thúc.

Một quy trình triển khai nên có:

- Readiness probe để loại instance khỏi endpoint routing.
- preStop hook hoặc cơ chế tương đương để cho routing cập nhật trước khi process dừng nếu hạ tầng cần propagation time.
- SIGTERM handler và Spring lifecycle để đóng admission.
- Drain deadline nhỏ hơn terminationGracePeriodSeconds.
- Checkpoint, idempotency và reconciliation cho công việc có thể vượt deadline.
- Shutdown metrics để biết instance có thực sự drain hay không.

Ví dụ cấu hình thời gian:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

Đây chỉ là thời gian ví dụ. Phải tính tổng thời gian cho preStop, propagation, drain, Spring lifecycle shutdown và cleanup. Nếu tổng thời gian có thể vượt 60 giây, cần điều chỉnh deadline hoặc cấu hình orchestrator theo yêu cầu thực tế.

Không dùng sleep cố định như giải pháp duy nhất. Delay chỉ cho endpoint routing cập nhật; nó không chứng minh không còn request đang chạy. Admission gate và in-flight tracker mới kiểm soát công việc bên trong process.

## 11. Quan sát quá trình shutdown

Nên ghi nhận các metric sau:

- Số request in-flight hiện tại.
- Số request mới bị từ chối do shutdown.
- Thời gian từ lúc bắt đầu drain đến khi active bằng 0.
- Số request còn lại khi drain deadline hết.
- Số stream bị cancel trong shutdown.
- Số operation được checkpoint hoặc chuyển sang retry.
- Số requester/server connection đã dispose.
- Số lỗi phát sinh trong lúc shutdown.

Log nên có correlation ID, operation ID và route để truy vết. Không log payload nhạy cảm hoặc credentials.

Một log hữu ích có thể ghi:

~~~text
shutdown_started accepting=false active=12
shutdown_draining active=4 elapsed_ms=8200
shutdown_completed active=0 elapsed_ms=10450
~~~

Đây là output minh họa, không phải log do Spring tự phát. Ứng dụng cần tự instrument các mốc lifecycle và tracker.

Nếu drain thường xuyên chạm deadline, cần tìm nguyên nhân: stream không có giới hạn, downstream chậm, consumer không cancel, worker bị treo hoặc timeout nghiệp vụ quá dài. Chỉ tăng termination grace period mà không tìm nguyên nhân có thể che giấu vấn đề.

## 12. Kiểm thử graceful shutdown

Cần kiểm tra cả hành vi publisher lẫn vòng đời transport.

### 12.1. Unit test cho tracker

Các kịch bản quan trọng:

1. Request được nhận khi accepting=true.
2. Request mới bị từ chối sau beginDrain().
3. Drain chưa complete khi một request còn active.
4. Drain complete sau khi request complete.
5. Drain complete sau khi request error.
6. Drain complete sau khi subscriber cancel.
7. Race giữa enter() và beginDrain() không làm bộ đếm âm hoặc bỏ sót request.

Có thể dùng TestPublisher để giữ publisher mở và chủ động complete/cancel trong test. StepVerifier giúp kiểm tra chính xác thời điểm drain kết thúc.

### 12.2. Kiểm tra cancellation

Ví dụ xác nhận tracker giải phóng bộ đếm khi subscriber cancel:

~~~java
TestPublisher<String> work = TestPublisher.create();
InFlightRequests tracker = new InFlightRequests();

StepVerifier.create(
        tracker.trackMono(work::mono)
    )
    .then(() -> {
        assertEquals(1, tracker.activeCount());
    })
    .thenCancel()
    .verify();

assertEquals(0, tracker.activeCount());
~~~

Ví dụ giả định có JUnit assertEquals và reactor-test trong test scope. TestPublisher giữ publisher mở cho đến khi subscriber hủy; doFinally trong tracker phải chạy và giảm active về 0.

### 12.3. Integration test với RSocket

Unit test không xác nhận transport thật đã drain đúng. Integration test nên:

- Mở RSocket connection và gửi một request có thể điều khiển thời gian hoàn tất.
- Bắt đầu shutdown trong khi request đang chạy.
- Gửi thêm request trên connection cũ và xác nhận bị từ chối.
- Hoàn tất request đầu tiên và xác nhận response được nhận.
- Xác nhận server đóng listener sau drain.
- Xác nhận client nhận lỗi phù hợp khi request mới bị từ chối.
- Kiểm tra behavior của Request-Stream/Channel khi cancel hoặc khi drain deadline hết.

Đối với Kubernetes, chạy test deployment thực tế hoặc test môi trường staging để xác nhận readiness propagation, SIGTERM và termination deadline.

### 12.4. Những điều cần xác nhận trong test

- Bộ đếm tăng đúng một lần cho mỗi logical request.
- Bộ đếm giảm trên complete, error và cancel.
- Không chấp nhận request mới sau khi admission đóng.
- Không đóng database/queue trước khi handler hoàn tất.
- Request có side effect không bị retry trùng sau khi response bị mất.
- Stream dài có policy timeout hoặc checkpoint.
- Shutdown không vượt termination grace period trong kịch bản bình thường.
- Khi hết deadline, operation còn lại có thể được tra cứu và phục hồi.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ đánh dấu readiness false | Request mới vẫn có thể đến qua connection RSocket cũ. | Dùng admission gate ở handler. |
| Đóng requester trước khi drain | Request outbound đang chạy bị lỗi hoặc cancel. | Chờ outbound in-flight rồi mới dispose. |
| Chỉ giảm counter khi complete | Counter bị kẹt khi publisher error hoặc cancel. | Dùng doFinally. |
| Tăng counter khi tạo Mono | Publisher chưa subscribe nhưng đã bị tính là đang chạy. | Dùng Mono.defer và tăng khi subscribe. |
| Chỉ theo dõi đến payload đầu tiên | Stream vẫn chạy nhưng drain nghĩ đã hoàn tất. | Theo dõi đến terminal signal. |
| Xem cancel là rollback | Side effect đã commit bị bỏ qua trong trạng thái. | Lưu kết quả bền vững và hỗ trợ reconciliation. |
| Chờ drain vô hạn | Pod không thoát trước termination deadline. | Đặt drain deadline và checkpoint công việc còn lại. |
| Dùng server.shutdown cho mọi RSocket TCP server | Listener TCP độc lập không được quản lý như embedded web server. | Dùng lifecycle và transport-specific shutdown. |
| Dựa vào @PreDestroy để bắt đầu drain | Dependency có thể đã bắt đầu bị destroy. | Bắt đầu drain trước giai đoạn destroy bean. |
| Không theo dõi background worker | Handler kết thúc nhưng worker vẫn chạy khi process dừng. | Drain worker và queue consumer riêng. |
| Ack message trước khi commit | Message có thể mất dù nghiệp vụ chưa bền vững. | Commit/checkpoint trước acknowledgement. |
| Retry request sau timeout với key mới | Side effect có thể xảy ra hai lần. | Giữ idempotency key và truy vấn trạng thái. |

## 14. Checklist triển khai

- [ ] Readiness chuyển sang REFUSING_TRAFFIC khi shutdown bắt đầu.
- [ ] Admission gate từ chối request mới trên cả connection đã mở.
- [ ] Mỗi handler được theo dõi từ lúc subscribe đến complete/error/cancel.
- [ ] Bộ đếm không tăng khi publisher chưa được subscribe.
- [ ] Request-Stream và Channel được drain đến terminal signal hoặc deadline.
- [ ] Background worker và queue consumer có quy trình drain riêng.
- [ ] Side effect được commit hoặc checkpoint trước khi xác nhận.
- [ ] Có operation ID/idempotency để xử lý kết quả không xác định.
- [ ] Drain deadline nhỏ hơn process termination deadline.
- [ ] Timeout drain không bị hiểu là rollback hoặc thất bại chắc chắn.
- [ ] RSocketRequester chỉ dispose sau khi outbound request đã được drain.
- [ ] RSocket server/listener chỉ đóng sau khi admission và drain đã hoàn tất theo policy.
- [ ] Đã kiểm tra khác biệt giữa TCP, WebSocket và embedded web server.
- [ ] Có metric, log và runbook cho shutdown timeout.
- [ ] Unit test và integration test bao phủ complete, error, cancel và request đến trong lúc drain.

## Tài liệu tham khảo

- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): cấu hình graceful shutdown cho embedded web server và timeout lifecycle.
- [Spring Framework Reference — Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle callback và quản lý vòng đời bean.
- [Spring Framework Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html): start, stop, callback và phase ordering.
- [Spring Boot Reference — Availability](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): application availability và readiness state.
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, TestPublisher và virtual time.
- [RSocket Protocol](https://rsocket.io/about/protocol/): stream lifecycle, CANCEL, ERROR và connection semantics.
