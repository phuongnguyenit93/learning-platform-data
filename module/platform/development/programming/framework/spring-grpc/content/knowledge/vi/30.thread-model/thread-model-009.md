# MDC và correlation context

## 1. Vì sao cần correlation context?

Trong Spring gRPC, một logical RPC có thể đi qua client interceptor, server interceptor, service, executor bất đồng bộ, database và các service downstream. Những thành phần này có thể chạy trên nhiều thread khác nhau. Khi lỗi xảy ra, chỉ nhìn một dòng log riêng lẻ thường không đủ để biết nó thuộc request nào.

Correlation context mang một định danh ổn định theo request hoặc logical operation để liên kết log và telemetry giữa các tầng. MDC (Mapped Diagnostic Context) của SLF4J/Logback lưu các cặp key/value gắn với thread hiện tại, giúp logger tự thêm các giá trị như correlation ID vào mỗi dòng log.

Hai khái niệm liên quan nhưng không đồng nhất:

- Correlation context là dữ liệu theo request, cần được truyền qua các ranh giới thực thi.
- MDC là nơi lưu dữ liệu phục vụ logging trên một thread cụ thể.

MDC thường dựa trên ThreadLocal. Nếu callback gRPC hoặc task chuyển sang thread khác, MDC không tự đi theo. Ngược lại, thread pool tái sử dụng thread có thể làm giá trị MDC của request trước rò sang request tiếp theo nếu không khôi phục trạng thái.

## 2. Phân biệt gRPC Context, Reactor Context và MDC

| Cơ chế | Phạm vi | Cách hoạt động | Có tự truyền qua thread bất kỳ? |
| --- | --- | --- | --- |
| gRPC Context | Call/request gRPC | Context scoped, có thể attach/detach và wrap executor/task | Chỉ qua API hoặc executor có hỗ trợ propagation |
| Reactor Context | Một subscription reactive | Dữ liệu bất biến gắn với subscriber chain | Theo reactive chain, không phải ThreadLocal |
| SLF4J MDC | Thread hiện tại | Map dựa trên thread-local | Không |
| OpenTelemetry Context | Trace/span và baggage | Context propagation theo instrumentation/propagator | Qua instrumentation hoặc context-aware executor |

Không nên xem MDC là nguồn dữ liệu nghiệp vụ hoặc cơ chế truyền security principal. Nó chỉ phục vụ log. Principal, tenant đã xác thực và deadline nên nằm trong context có semantics phù hợp như gRPC Context hoặc security context được quản lý.

## 3. Correlation ID và trace ID

Correlation ID thường là định danh ứng dụng dùng để tìm tất cả log thuộc một thao tác. Trace ID thuộc distributed tracing và liên kết span qua nhiều service. Hai ID có thể cùng tồn tại:

- correlationId: ID ổn định do ứng dụng/gateway tạo hoặc chấp nhận sau khi kiểm tra định dạng.
- trace_id và span_id: do tracing SDK quản lý theo W3C Trace Context/OpenTelemetry.

Nếu đã có OpenTelemetry, ưu tiên dùng trace context chuẩn để nối trace giữa service. Correlation ID vẫn hữu ích cho support ticket, log search hoặc liên kết một nghiệp vụ dài hơn một trace.

Không tự tạo traceparent hoặc tự đặt trace ID vào MDC để thay thế tracing SDK. Việc parse, tạo child span, sampling và propagation nên do OpenTelemetry propagator/instrumentation đảm nhiệm.

Correlation ID do client gửi chỉ là dữ liệu để correlation, không phải bằng chứng danh tính hay quyền truy cập. Không đưa tên, email, access token, session secret hoặc dữ liệu cá nhân vào ID.

## 4. Nhận và xác thực correlation ID ở server

Một server interceptor có thể đọc metadata x-correlation-id, kiểm tra định dạng và tạo ID mới nếu thiếu hoặc không hợp lệ. Sau đó đặt ID vào gRPC Context để service và listener callbacks có thể truy cập.

Ví dụ dưới đây giới hạn ID ở 64 ký tự ASCII an toàn cho log:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationContextInterceptor
        implements ServerInterceptor {

    static final Context.Key<String> CORRELATION_ID =
            Context.key("correlation-id");

    static final Metadata.Key<String> CORRELATION_HEADER =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String supplied = headers.get(CORRELATION_HEADER);
        String correlationId =
                supplied != null && SAFE_ID.matcher(supplied).matches()
                        ? supplied
                        : UUID.randomUUID().toString();

        Context requestContext = Context.current()
                .withValue(CORRELATION_ID, correlationId);

        return Contexts.interceptCall(
                requestContext, call, headers, next);
    }
}
~~~

Contexts.interceptCall() gắn gRPC Context trong lúc tạo listener và xử lý các callback của listener. Vì vậy service có thể đọc ID từ CORRELATION_ID.get() trong phạm vi call.

Nếu hệ thống cần giữ ID do gateway cấp, gateway nên tạo ID ở ranh giới tin cậy và xóa/ghi đè header do client bên ngoài gửi. Việc chấp nhận ID do client tự gửi phù hợp để hỗ trợ tìm log, nhưng không được dùng nó làm căn cứ authorization.

## 5. Đưa correlation context vào MDC

gRPC Context không tự động ghi giá trị vào MDC. Cần một bridge đặt MDC quanh đoạn code chạy dưới context của RPC và khôi phục MDC cũ sau khi đoạn code kết thúc.

~~~java
import io.grpc.Context;
import org.slf4j.MDC;
import java.util.Map;
import java.util.function.Supplier;

public final class MdcContext {

    private MdcContext() {}

    public static void run(Context context, Runnable action) {
        call(context, () -> {
            action.run();
            return null;
        });
    }

    public static <T> T call(Context context, Supplier<T> action) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        String correlationId =
                context.get(CorrelationContextInterceptor.CORRELATION_ID);

        try {
            if (correlationId == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", correlationId);
            }
            try {
                return context.call(action::get);
            } catch (RuntimeException | Error error) {
                throw error;
            } catch (Exception error) {
                throw new IllegalStateException(
                        "Unexpected checked exception from MDC action", error);
            }
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
~~~

Helper này thực hiện hai việc độc lập:

1. Đặt correlation ID vào MDC trên thread đang chạy và khôi phục map trước đó trong finally.
2. Attach gRPC Context trong lúc chạy supplier thông qua context.call(...).

Không chỉ gọi MDC.put() rồi bỏ đó. Thread pool có thể tái sử dụng thread cho một RPC khác; nếu không restore/clear, log của request sau có thể mang correlation ID của request trước.

## 6. Bọc listener callbacks để MDC có mặt khi service chạy

Server interceptor có thể dùng Contexts.interceptCall() để propagation gRPC Context, nhưng MDC vẫn cần được đặt quanh callback thực tế. Một cách là bọc các callback của ServerCall.Listener:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.ForwardingServerCallListener;

public final class MdcServerInterceptor
        implements ServerInterceptor {

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String id = CorrelationContextInterceptor.CORRELATION_ID.get();
        Context requestContext = Context.current()
                .withValue(CorrelationContextInterceptor.CORRELATION_ID, id);

        return Contexts.interceptCall(
                requestContext,
                call,
                headers,
                new ServerCallHandler<ReqT, RespT>() {
                    @Override
                    public ServerCall.Listener<ReqT> startCall(
                            ServerCall<ReqT, RespT> serverCall,
                            Metadata metadata) {

                        ServerCall.Listener<ReqT> delegate =
                                MdcContext.call(
                                        requestContext,
                                        () -> next.startCall(serverCall, metadata));

                        return new ForwardingServerCallListener
                                .SimpleForwardingServerCallListener<>(delegate) {
                            @Override
                            public void onMessage(ReqT message) {
                                MdcContext.run(requestContext,
                                        () -> super.onMessage(message));
                            }

                            @Override
                            public void onHalfClose() {
                                MdcContext.run(requestContext,
                                        super::onHalfClose);
                            }

                            @Override
                            public void onCancel() {
                                MdcContext.run(requestContext,
                                        super::onCancel);
                            }

                            @Override
                            public void onComplete() {
                                MdcContext.run(requestContext,
                                        super::onComplete);
                            }

                            @Override
                            public void onReady() {
                                MdcContext.run(requestContext,
                                        super::onReady);
                            }
                        };
                    }
                });
    }
}
~~~

Đây là ví dụ tập trung vào propagation; trong ứng dụng, có thể hợp nhất việc đọc/validate header và bọc listener vào một interceptor để tránh tạo hai lớp riêng. Khi hợp nhất, phải giữ thứ tự: tạo request Context trước, sau đó bọc startCall và từng listener callback bằng MdcContext.

Đăng ký interceptor theo đúng thứ tự của server. Nếu một interceptor khác tạo correlation Context, interceptor bọc MDC phải chạy sau khi ID đã được đặt. Xác minh chain thực tế theo cách Spring gRPC của phiên bản dự án đăng ký global/service interceptors.

## 7. Truyền MDC qua executor bất đồng bộ

Propagation của gRPC Context và MDC là hai việc khác nhau. Context.currentContextExecutor(executor) truyền gRPC Context sang task, nhưng không tự copy MDC. Với Spring TaskExecutor, có thể dùng TaskDecorator để chụp cả hai tại thời điểm submit:

~~~java
import io.grpc.Context;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;
import java.util.Map;

public final class MdcGrpcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Context grpcContext = Context.current();
        Map<String, String> capturedMdc = MDC.getCopyOfContextMap();

        return grpcContext.wrap(() -> {
            Map<String, String> previousMdc = MDC.getCopyOfContextMap();
            try {
                if (capturedMdc == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(capturedMdc);
                }
                task.run();
            } finally {
                if (previousMdc == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousMdc);
                }
            }
        });
    }
}
~~~

Đăng ký với Spring executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor rpcWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("grpc-worker-");
        executor.setTaskDecorator(new MdcGrpcTaskDecorator());
        return executor;
    }
}
~~~

Khi task được submit trong RPC callback, decorator chụp gRPC Context và MDC của thread submit. Khi task chạy trên worker thread, grpcContext.wrap() attach Context và decorator cài MDC đã chụp; sau khi chạy xong, MDC trước đó của worker được khôi phục.

Không dùng một ThreadLocal tùy biến mà không có bước capture/restore. Cũng không giả định InheritableThreadLocal giải quyết propagation cho thread pool: worker thread thường được tạo trước khi request đến và được tái sử dụng.

## 8. Client: tạo và gửi correlation ID

Client có thể tạo correlation ID tại ranh giới của logical operation rồi đưa vào gRPC Context. Client interceptor đọc giá trị đó và thêm metadata vào mỗi RPC:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class CorrelationClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                String id = CorrelationContextInterceptor.CORRELATION_ID.get();
                if (id != null) {
                    headers.put(
                            CorrelationContextInterceptor.CORRELATION_HEADER,
                            id);
                }
                super.start(listener, headers);
            }
        };
    }
}
~~~

Tạo context cho một logical operation:

~~~java
import io.grpc.Context;
import java.util.UUID;

String correlationId = UUID.randomUUID().toString();
Context operationContext = Context.current().withValue(
        CorrelationContextInterceptor.CORRELATION_ID,
        correlationId);

operationContext.run(() -> catalogStub.getItem(request));
~~~

Nếu ứng dụng đã có correlation ID từ HTTP request hoặc message consumer, có thể tái sử dụng ID đó sau khi kiểm tra định dạng. Không tạo ID mới ở mỗi downstream RPC nếu mục tiêu là nối log của cùng một logical operation.

Với async stub, callback có thể chạy trên executor khác. Nếu callback cần log cùng context, dùng context-aware executor và MDC decorator hoặc một bridge tương đương; client interceptor chỉ thêm metadata không tự làm MDC xuất hiện trên callback thread.

## 9. Kết hợp với Reactor Context

Reactor Context đi theo subscription, trong khi MDC đi theo thread. Với reactive pipeline, lấy correlation ID từ Reactor Context tại điểm log và tạm thời đặt vào MDC:

~~~java
import org.slf4j.MDC;
import reactor.core.publisher.Mono;
import reactor.util.context.ContextView;
import java.util.Map;

static void logWithCorrelation(ContextView contextView, Runnable logAction) {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        String id = contextView.getOrDefault("correlationId", null);
        if (id == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", id);
        }
        logAction.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}

Mono<Order> orderMono = orderRepository.findById(orderId)
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                logWithCorrelation(
                        signal.getContextView(),
                        () -> log.info("Order loaded"));
            }
        })
        .contextWrite(context -> context.put(
                "correlationId", correlationId));
~~~

Helper đặt MDC chỉ trong lúc ghi log và luôn restore. Không giữ MDC mở xuyên toàn reactive chain vì chain có thể chuyển thread giữa các operator. Nếu dùng cơ chế automatic context propagation của Reactor, cấu hình và semantics phụ thuộc phiên bản; vẫn cần kiểm tra hành vi thực tế khi đổi scheduler.

## 10. Định dạng log

Với Logback, có thể thêm correlation ID vào pattern:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] [corr=%X{correlationId:-}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ví dụ log:

~~~text
2026-11-19 10:20:30.120 INFO [grpc-worker-4] [corr=6a2f...] OrderService - Order loaded
~~~

Khi MDC không có correlation ID, pattern hiển thị giá trị rỗng thay vì chuỗi null. Không đưa toàn bộ MDC map vào log nếu trong đó có thể chứa token hoặc dữ liệu nhạy cảm.

## 11. Những lỗi propagation thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dùng MDC.put() trong interceptor | Callback ở thread khác không có ID | Bọc listener callback hoặc dùng task decorator |
| Chỉ truyền gRPC Context | Service đọc Context được nhưng pattern MDC trống | Bridge Context sang MDC ở điểm thực thi |
| Chỉ copy MDC, không truyền gRPC Context | Log có ID nhưng principal/deadline Context có thể mất | Capture và wrap cả hai khi submit task |
| Không restore MDC trong finally | Request sau trên cùng worker thread nhận ID cũ | Lưu map cũ và khôi phục/clear |
| Dùng InheritableThreadLocal với thread pool | Không bảo đảm context của từng task | Dùng explicit task decoration |
| Tạo correlation ID mới ở mỗi service | Không tìm được toàn bộ chuỗi request | Truyền cùng ID qua metadata |
| Tin correlation ID như credential | Có thể giả mạo log correlation hoặc gây nhầm lẫn audit | Không dùng ID làm authentication/authorization |
| Đưa ID duy nhất vào metric label | Cardinality tăng cao | Đưa ID vào log/trace, không dùng metric label |

## 12. Kiểm thử correlation context

Nên có integration test chạy nhiều RPC đồng thời qua cùng server và executor để phát hiện rò MDC:

| Kịch bản | Assertion |
| --- | --- |
| Client gửi correlation ID hợp lệ | Server Context và log có cùng ID |
| Client không gửi ID | Server tạo ID mới và dùng nhất quán trong call |
| Client gửi ID chứa newline hoặc ký tự ngoài allowlist | ID bị thay bằng ID mới hoặc từ chối theo policy |
| Hai RPC chạy đồng thời trên thread pool | Log của mỗi RPC chỉ mang ID tương ứng |
| Task được submit sang Spring executor | gRPC Context và MDC được truyền sang worker |
| Task kết thúc rồi worker xử lý RPC khác | MDC cũ được restore/clear |
| Reactor pipeline đổi scheduler | Log vẫn lấy ID từ Reactor Context |
| Async callback chạy sau khi call hoàn tất | Không đọc nhầm MDC của request khác |
| Không có correlation context | Log không hiển thị ID cũ |

Test nên ghi log vào appender kiểm thử hoặc thu thập MDC map tại điểm log, rồi assert ID theo từng RPC. Dùng barrier/latch để ép hai request chạy xen kẽ trên pool nhỏ; test tuần tự thường không phát hiện được context leak.

## 13. Bài tập vận dụng

Với orders.v1.OrderService/GetOrder:

1. Tạo server interceptor đọc x-correlation-id, validate định dạng và đặt ID vào gRPC Context.
2. Bọc listener callback để cài MDC đúng trong onMessage, onHalfClose, onCancel và terminal callbacks.
3. Tạo TaskDecorator truyền cả gRPC Context và MDC sang ThreadPoolTaskExecutor.
4. Thêm client interceptor để gửi correlation ID qua metadata.
5. Cấu hình Logback hiển thị %X{correlationId}.
6. Chạy nhiều RPC đồng thời và xác minh không có ID rò giữa các request.
7. Nếu dùng OpenTelemetry, xác minh trace ID/span ID vẫn được propagator quản lý độc lập với correlation ID.

**Tiêu chí hoàn thành:** người học phân biệt gRPC Context, Reactor Context và MDC; truyền correlation ID qua metadata và thread boundary; khôi phục MDC để tránh thread leak; và kiểm thử được propagation trong callback, executor và reactive pipeline.

### Tài liệu tham khảo

- [gRPC Java Context API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): context propagation, attach và wrap executor.
- [gRPC Java Contexts API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Contexts.html): gắn Context vào server call/listener.
- [SLF4J MDC](https://www.slf4j.org/manual.html#mdc): mapped diagnostic context và thread-local logging.
- [Spring Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor và TaskDecorator.
- [Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context propagation trong reactive sequence.
- [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context và propagation qua service.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
