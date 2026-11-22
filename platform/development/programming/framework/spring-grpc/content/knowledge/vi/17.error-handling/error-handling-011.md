# Global server exception handling

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào một cơ chế xử lý exception tập trung ở phía server, để các lỗi phát sinh tại ranh giới RPC được phân loại nhất quán và chuyển thành gRPC status an toàn.

## 1. Vì sao cần xử lý exception tập trung?

Một dịch vụ có thể có nhiều RPC: tìm khách hàng, tạo đơn, cập nhật tồn kho, tải batch hoặc streaming dữ liệu. Nếu mỗi handler tự viết khối `try/catch`, cách ánh xạ lỗi dễ không nhất quán:

- Cùng một lỗi domain nhưng RPC này trả `NOT_FOUND`, RPC khác trả `INTERNAL`.
- Exception bất ngờ bị gửi nguyên `getMessage()` cho client.
- Một status đã được tạo có chủ đích ở tầng dưới bị đổi thành status khác.
- Một callback streaming phát terminal signal nhiều lần.
- Một method quên bắt lỗi và kết thúc bằng status mặc định không theo hợp đồng API.

Global server exception handling đặt logic phân loại lỗi tại một ranh giới dùng chung. Mỗi handler vẫn chịu trách nhiệm cho nghiệp vụ; cơ chế tập trung chỉ chuyển lỗi thành status và metadata cuối RPC.

```text
Unary / streaming gRPC service
             |
             v
      Application / domain
             |
             v
      Exception boundary
             |
      +------+------------------+
      |                         |
      v                         v
 Known exception           Unknown exception
      |                         |
      v                         v
 Status mapper             Log nội bộ có kiểm soát
      |                         |
      +------------+------------+
                   |
                   v
       ServerCall.close(status, trailers)
                   |
                   v
             gRPC client
```

Global handler không thay thế validation, authorization hoặc xử lý lỗi domain. Nó cung cấp một nơi nhất quán để những lỗi đã được phân loại đi ra khỏi server.

## 2. Phân loại lỗi tại một mapper dùng chung

Mapper nên có quy tắc rõ ràng:

1. Nếu exception đã chứa gRPC status được tạo có chủ đích, giữ nguyên code và trailers phù hợp.
2. Nếu là lỗi domain hoặc dependency đã biết, ánh xạ theo ngữ nghĩa API.
3. Nếu là lỗi không dự kiến, ghi diagnostic ở server và trả `INTERNAL` với description chung.

Ví dụ mapper:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class GrpcExceptionMapper {

    private static final Logger log =
            LoggerFactory.getLogger(GrpcExceptionMapper.class);

    public StatusRuntimeException map(Throwable failure) {
        // Giữ status đã được tạo ở tầng dưới, kể cả khi exception bị bọc.
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (current instanceof StatusRuntimeException
                    || current instanceof StatusException) {
                Status status = Status.fromThrowable(current);
                Metadata trailers =
                        Status.trailersFromThrowable(current);
                return trailers == null
                        ? status.asRuntimeException()
                        : status.asRuntimeException(trailers);
            }
        }

        if (hasCause(failure, CustomerNotFoundException.class)) {
            return Status.NOT_FOUND
                    .withDescription("Không tìm thấy khách hàng")
                    .asRuntimeException();
        }
        if (hasCause(failure, RequestValidationException.class)) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Dữ liệu yêu cầu không hợp lệ")
                    .asRuntimeException();
        }
        if (hasCause(failure, ConcurrentUpdateException.class)) {
            return Status.ABORTED
                    .withDescription("Dữ liệu đã thay đổi; hãy tải lại và thử lại")
                    .asRuntimeException();
        }
        if (hasCause(failure, DependencyUnavailableException.class)) {
            return Status.UNAVAILABLE
                    .withDescription("Dịch vụ phụ thuộc tạm thời không sẵn sàng")
                    .asRuntimeException();
        }

        // Chỉ lỗi chưa phân loại mới dùng INTERNAL.
        // Không đưa exception message hoặc stack trace vào response.
        log.error("Unhandled exception at gRPC boundary, type={}",
                failure.getClass().getName(), failure);
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }

    private boolean hasCause(
            Throwable failure,
            Class<? extends Throwable> expectedType) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Các exception domain trong ví dụ đại diện cho những loại lỗi đã được định nghĩa ở tầng application. Thay chúng bằng exception thực tế của dự án; không map mọi `RuntimeException` hoặc mọi `DataAccessException` sang cùng một status.

Mapper không lấy `failure.getMessage()` làm description. Thông báo công khai nên ổn định, không chứa SQL, token, PII hoặc chi tiết hạ tầng. Nếu cần support reference hay error code, thêm trailers đã được kiểm soát.

## 3. Dùng ServerInterceptor làm ranh giới toàn server

gRPC Java cung cấp `ServerInterceptor` để bao quanh quá trình nhận RPC. Interceptor có thể:

- Bắt exception phát sinh đồng bộ khi khởi tạo handler.
- Bọc `ServerCall.Listener` để bắt exception đồng bộ trong các callback như `onMessage`, `onHalfClose` và `onReady`.
- Đóng call bằng status được mapper tạo ra.

Ví dụ dưới đây minh họa interceptor tổng quát. Wrapper theo dõi trạng thái đóng để không gọi `ServerCall.close()` nhiều lần:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.concurrent.atomic.AtomicBoolean;

public final class GlobalExceptionInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalExceptionInterceptor.class);

    private final GrpcExceptionMapper exceptionMapper;

    public GlobalExceptionInterceptor(
            GrpcExceptionMapper exceptionMapper) {
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        AtomicBoolean closed = new AtomicBoolean(false);

        ServerCall<ReqT, RespT> guardedCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (closed.compareAndSet(false, true)) {
                            super.close(status, trailers);
                        }
                    }
                };

        try {
            ServerCall.Listener<ReqT> delegate =
                    next.startCall(guardedCall, headers);

            return new ForwardingServerCallListener
                    .SimpleForwardingServerCallListener<>(delegate) {

                private void invoke(Runnable callback) {
                    try {
                        callback.run();
                    } catch (RuntimeException failure) {
                        StatusRuntimeException mapped =
                                exceptionMapper.map(failure);
                        Metadata trailers =
                                Status.trailersFromThrowable(mapped);
                        guardedCall.close(
                                mapped.getStatus(),
                                trailers == null ? new Metadata() : trailers);
                    }
                }

                @Override
                public void onMessage(ReqT message) {
                    invoke(() -> delegate.onMessage(message));
                }

                @Override
                public void onHalfClose() {
                    invoke(delegate::onHalfClose);
                }

                @Override
                public void onReady() {
                    invoke(delegate::onReady);
                }

                @Override
                public void onCancel() {
                    // Call đã bị client hủy: chỉ ghi nhận/cleanup,
                    // không cố gửi thêm status trên call đã cancel.
                    try {
                        delegate.onCancel();
                    } catch (RuntimeException cleanupError) {
                        log.warn("Exception during gRPC cancellation cleanup",
                                cleanupError);
                    }
                }

                @Override
                public void onComplete() {
                    try {
                        delegate.onComplete();
                    } catch (RuntimeException cleanupError) {
                        log.warn("Exception during gRPC completion callback",
                                cleanupError);
                    }
                }
            };
        } catch (RuntimeException failure) {
            StatusRuntimeException mapped =
                    exceptionMapper.map(failure);
            Metadata trailers = Status.trailersFromThrowable(mapped);
            guardedCall.close(
                    mapped.getStatus(),
                    trailers == null ? new Metadata() : trailers);
            return new ServerCall.Listener<>() {};
        }
    }
}
```

Đây là mẫu minh họa cho cơ chế bắt exception đồng bộ. Khi triển khai thực tế, bổ sung logger cho lỗi cleanup, kiểm tra hành vi của server builder đang dùng và bảo đảm interceptor được đăng ký đúng thứ tự. Không bắt `Error` hoặc lỗi JVM nghiêm trọng rồi giả vờ RPC có thể tiếp tục bình thường.

### Vì sao phải theo dõi terminal state?

Một RPC chỉ có một kết quả cuối. Khi service đã gọi `onError` hoặc `onCompleted`, interceptor không được cố đóng call lần thứ hai. Wrapper `guardedCall` dùng `AtomicBoolean` để bảo vệ thao tác close trong trường hợp callback hoặc cancellation cạnh tranh.

Interceptor cũng không nên phát một response message thay cho service. Nhiệm vụ của nó là chuyển lỗi thành status cuối; việc tạo response nghiệp vụ thuộc handler.

## 4. Đăng ký interceptor toàn cục trong Spring gRPC

Tạo interceptor thành Spring bean mới chỉ cung cấp instance; cần **đăng ký instance vào server interceptor chain** để mọi RPC đi qua nó.

Trong Spring gRPC, thực hiện việc đăng ký bằng extension point cấu hình server của starter/version đang dùng (server configurer hoặc global interceptor registration nếu starter cung cấp). Về mặt gRPC Java, thao tác cuối cùng tương đương:

```java
serverBuilder.intercept(globalExceptionInterceptor);
```

Không giả định một bean `@Component` tự động trở thành global interceptor nếu starter không có cơ chế discovery tương ứng. Cũng không dùng `@ControllerAdvice` của Spring MVC như thể nó tự bắt exception từ gRPC service; hai loại request đi qua hai execution pipeline khác nhau.

Nếu dự án dùng một starter có annotation hoặc advice riêng cho gRPC, có thể dùng API đó thay interceptor tự viết. Cần xác minh phạm vi bắt lỗi, thứ tự interceptor và khả năng xử lý streaming callback theo đúng phiên bản; không trộn nhiều cơ chế cùng đóng một call.

## 5. Những lỗi bất đồng bộ cần được xử lý tại nơi phát sinh

Global interceptor bắt được exception chỉ khi exception còn chạy trên call stack mà interceptor bọc. Nó **không thể tự bắt mọi lỗi xảy ra ở bất kỳ thread nào**.

Ví dụ service gửi công việc sang executor:

```java
executor.execute(() -> {
    try {
        Result result = applicationService.process(request);
        responseObserver.onNext(toProto(result));
        responseObserver.onCompleted();
    } catch (Exception failure) {
        responseObserver.onError(exceptionMapper.map(failure));
    }
});
```

Exception trong task bất đồng bộ phải được bắt trong task và chuyển qua `responseObserver.onError()`. Nếu chỉ để exception thoát khỏi thread pool, interceptor ban đầu không còn nằm trên call stack để chuyển nó thành gRPC status.

Với streaming RPC, cùng nguyên tắc áp dụng cho:

- Lỗi trong callback `onNext()`: bắt tại callback hoặc để interceptor bắt nếu callback được gọi đồng bộ trong listener đã bọc.
- Lỗi khi tổng hợp ở `onCompleted()`: chuyển thành terminal status trước khi gửi receipt.
- Lỗi trong future, scheduler hoặc reactive pipeline: gắn error handler tại pipeline đó và kết thúc response observer đúng một lần.
- Client cancellation/deadline: dừng tác vụ và cleanup; không gửi response mới khi call đã bị hủy.

Global handler là lớp bảo vệ chung cho các exception đồng bộ bị bỏ sót, không thay thế xử lý lỗi tường minh trong tác vụ bất đồng bộ.

## 6. Giữ nguyên status và tránh ánh xạ hai lần

Một service có thể chủ động trả `NOT_FOUND`, `INVALID_ARGUMENT` hoặc `PERMISSION_DENIED`. Global handler không được biến những status này thành `INTERNAL` chỉ vì chúng được bọc trong một exception khác.

Quy tắc:

- Tìm status exception trong cause chain và giữ code/trailers nếu nó được tạo có chủ đích.
- Chỉ map domain/dependency exception chưa được chuyển thành gRPC status.
- Nếu call đã đóng, không gửi terminal signal thứ hai.
- Không chuyển exception cancellation thành lỗi server.
- Không đưa exception message, stack trace hoặc cause nội bộ ra client.

Không nên ánh xạ status chỉ dựa trên chuỗi description. Dùng status code và loại exception domain đã định nghĩa.

## 7. Kiểm thử global exception handling

Kiểm thử cần xác nhận cả mapper lẫn hành vi qua server:

| Ca | Kỳ vọng |
| --- | --- |
| Domain not found bị ném đồng bộ | Client nhận `NOT_FOUND` |
| Validation exception | Client nhận `INVALID_ARGUMENT` |
| Status exception đã có | Code/trailers được giữ nguyên |
| Exception không dự kiến | Client nhận `INTERNAL` với description an toàn |
| Exception trong listener callback | Interceptor đóng call bằng status đã map |
| Exception trong executor/future | Task bắt lỗi và gọi observer `onError` |
| Client hủy stream | Cleanup chạy; server không gửi terminal status thứ hai |
| Hai đường lỗi cùng chạy | Chỉ một terminal close được thực hiện |

Unit test mapper:

```java
class GrpcExceptionMapperTest {

    private final GrpcExceptionMapper mapper =
            new GrpcExceptionMapper();

    @Test
    void mapsKnownDomainError() {
        var mapped = mapper.map(
                new CustomerNotFoundException("customer-1"));

        assertEquals(Status.Code.NOT_FOUND,
                mapped.getStatus().getCode());
    }

    @Test
    void mapsUnknownErrorToSafeInternal() {
        var mapped = mapper.map(
                new IllegalStateException("database password leaked"));

        assertEquals(Status.Code.INTERNAL,
                mapped.getStatus().getCode());
        assertEquals("Internal server error",
                mapped.getStatus().getDescription());
    }

    @Test
    void preservesExistingGrpcStatus() {
        var original = Status.PERMISSION_DENIED
                .withDescription("Operation is not permitted")
                .asRuntimeException();

        var mapped = mapper.map(original);

        assertEquals(Status.Code.PERMISSION_DENIED,
                mapped.getStatus().getCode());
    }
}
```

Integration test nên dựng in-process server có đăng ký global interceptor, gọi một service test cố ý ném exception đồng bộ rồi kiểm tra status ở client. Thêm test riêng cho executor để chứng minh lỗi bất đồng bộ được handler tại task, vì interceptor không thể tự quan sát exception đã thoát sang thread khác.

## 8. Quan sát lỗi và vận hành

Global handler là điểm phù hợp để ghi metrics thống nhất:

- Tổng số exception theo gRPC method và status code.
- Số lỗi đã map theo domain/dependency và số lỗi fallback `INTERNAL`.
- Số call bị hủy hoặc hết deadline.
- Số lỗi trong listener callback và lỗi từ tác vụ bất đồng bộ.
- Số lần mapper/terminal close bị gọi nhiều lần.

Log cần có method, status, application error code và correlation ID. Stack trace chỉ được ghi ở diagnostic channel nội bộ có quyền truy cập và retention phù hợp. Không ghi token, payload hoặc PII thô; không đưa exception message vào description.

Nếu tỷ lệ fallback `INTERNAL` tăng, đó là tín hiệu mapper đang thiếu loại lỗi đã biết hoặc xuất hiện lỗi lập trình mới. Không nên khắc phục bằng cách map tất cả exception sang một status “dễ retry”.

## 9. Tự luyện tập

1. Vì sao một Spring bean chứa mapper chưa đủ để bảo đảm mọi RPC đều đi qua global exception handling?
2. Interceptor có thể bắt exception trong `onHalfClose()` nhưng vì sao không thể tự bắt exception trong một task đã chạy trên executor?
3. Một tầng dưới ném `StatusRuntimeException(PERMISSION_DENIED)`. Global mapper nên giữ hay đổi status? Vì sao?
4. Thiết kế test chứng minh callback streaming lỗi chỉ đóng call một lần.
5. Nếu service đã commit dữ liệu rồi lỗi xảy ra khi gửi response, vì sao global handler không thể tự rollback transaction hoặc khẳng định client có thể retry an toàn?

**Ghi nhớ:** Global server exception handling tập trung ánh xạ exception thành gRPC status tại ranh giới RPC, giữ nguyên status đã có và dùng `INTERNAL` an toàn cho lỗi không dự kiến. Server interceptor có thể bắt lỗi đồng bộ trong quá trình khởi tạo và listener callback; lỗi bất đồng bộ vẫn phải được bắt tại task/pipeline phát sinh. Đăng ký interceptor vào server chain, bảo vệ terminal state và kiểm thử cả response lẫn cancellation.
