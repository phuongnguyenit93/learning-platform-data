# Chuyển exception trong interceptor

Trong Spring gRPC, lỗi có thể xuất hiện khi interceptor khởi tạo call, khi service xử lý request hoặc trong callback của một RPC streaming. Nếu mỗi endpoint tự chuyển exception sang gRPC status theo cách riêng, client sẽ nhận lỗi không nhất quán; nếu để exception thoát khỏi callback, transport có thể chỉ trả một status chung khó chẩn đoán.

**Exception-mapping interceptor** đặt một ranh giới tập trung để chuyển exception đồng bộ ở server thành gRPC status, giữ nguyên status đã được chủ động tạo và bảo đảm call chỉ đóng một lần. Tuy vậy, interceptor chỉ bắt được exception phát sinh trong lời gọi/callback mà nó bọc. Công việc bất đồng bộ tiếp tục sau callback cần tự chuyển lỗi trước khi gọi `StreamObserver.onError`. Phía client nhận status qua `onClose`; nó không nhận trực tiếp exception Java được ném trên server.

## 1. Exception và gRPC status là hai lớp khác nhau

Exception mô tả lỗi trong code Java; gRPC status là kết quả RPC được truyền qua wire. Không nên để loại exception nội bộ hoặc stack trace trở thành hợp đồng API.

| Lỗi trong ứng dụng | gRPC status thường dùng | Ý nghĩa với client |
| --- | --- | --- |
| Request sai định dạng hoặc tham số không hợp lệ | `INVALID_ARGUMENT` | Client cần sửa request |
| Không tìm thấy tài nguyên | `NOT_FOUND` | Tài nguyên không tồn tại hoặc không được công bố |
| Caller chưa xác thực | `UNAUTHENTICATED` | Cần credential hợp lệ |
| Caller không có quyền | `PERMISSION_DENIED` | Caller đã xác thực nhưng không được phép |
| Trạng thái nghiệp vụ xung đột | `ALREADY_EXISTS` hoặc `FAILED_PRECONDITION` | Client cần xử lý trạng thái hiện tại |
| Tài nguyên tạm thời bận/quá tải | `RESOURCE_EXHAUSTED` hoặc `UNAVAILABLE` | Có thể thử lại theo policy phù hợp |
| Lỗi không dự kiến phía server | `INTERNAL` | Lỗi server; không tiết lộ chi tiết nội bộ |

Chọn status theo semantics mà client cần hiểu, không theo tên class exception. Ví dụ, `IllegalStateException` không tự động luôn là `FAILED_PRECONDITION`; cần biết trạng thái nào của nghiệp vụ đã không thỏa điều kiện.

## 2. Tách exception mapper khỏi interceptor

Mapper là nơi duy nhất định nghĩa cách chuyển exception của ứng dụng sang status. Ví dụ:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;

public final class GrpcExceptionMapper {

    public MappedGrpcError map(Throwable error) {
        if (error instanceof StatusRuntimeException statusError) {
            return new MappedGrpcError(
                    statusError.getStatus(),
                    trailersOrEmpty(statusError.getTrailers()));
        }
        if (error instanceof StatusException statusError) {
            return new MappedGrpcError(
                    statusError.getStatus(),
                    trailersOrEmpty(statusError.getTrailers()));
        }
        if (error instanceof ProductNotFoundException) {
            return error(Status.NOT_FOUND, "Product not found");
        }
        if (error instanceof InvalidCatalogRequestException) {
            return error(Status.INVALID_ARGUMENT, "Invalid catalog request");
        }
        if (error instanceof AccessDeniedException) {
            return error(Status.PERMISSION_DENIED, "Permission denied");
        }
        return error(Status.INTERNAL, "Unexpected server error");
    }

    private static MappedGrpcError error(Status status, String description) {
        return new MappedGrpcError(
                status.withDescription(description), new Metadata());
    }

    private static Metadata trailersOrEmpty(Metadata trailers) {
        return trailers == null ? new Metadata() : trailers;
    }

    public record MappedGrpcError(Status status, Metadata trailers) {
    }
}
```

`ProductNotFoundException`, `InvalidCatalogRequestException` và `AccessDeniedException` là các exception minh họa do ứng dụng định nghĩa hoặc sử dụng. Mapper giữ status/trailers nếu code phía dưới đã chủ động ném `StatusException` hoặc `StatusRuntimeException`; các exception nghiệp vụ được ánh xạ theo bảng policy; lỗi không nhận diện được trả `INTERNAL` với mô tả an toàn.

Không dùng `Status.fromThrowable(error)` như chính sách duy nhất cho mọi exception. Hàm đó hữu ích để tìm status trong cause chain, nhưng exception Java thông thường không mang gRPC status có thể trở thành `UNKNOWN`. Mapper tường minh giúp phân biệt lỗi nghiệp vụ đã biết với lỗi server bất ngờ.

## 3. Server interceptor chuyển exception đồng bộ

Server interceptor cần bao hai vùng:

1. `next.startCall`, vì interceptor hoặc service binding có thể ném exception ngay khi tạo listener.
2. Các callback trên `ServerCall.Listener`, vì code xử lý request có thể ném exception khi `onMessage`, `onHalfClose` hoặc callback khác được gọi.

Ví dụ rút gọn dưới đây bọc `ServerCall` và listener, dùng cờ per-call để tránh đóng call hai lần:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ExceptionMappingServerInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ExceptionMappingServerInterceptor.class);

    private final GrpcExceptionMapper mapper;

    public ExceptionMappingServerInterceptor(GrpcExceptionMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        AtomicBoolean closed = new AtomicBoolean();
        Consumer<Throwable> fail = error -> {
            if (!closed.compareAndSet(false, true)) {
                log.debug("Ignoring exception after RPC was closed");
                return;
            }
            GrpcExceptionMapper.MappedGrpcError mapped = mapper.map(error);
            call.close(mapped.status(), mapped.trailers());
        };

        ServerCall<ReqT, RespT> wrappedCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (closed.compareAndSet(false, true)) {
                            super.close(status, trailers);
                        }
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(wrappedCall, headers);
        } catch (RuntimeException error) {
            fail.accept(error);
            return new ServerCall.Listener<>() {};
        }

        Consumer<Runnable> guard = action -> {
            try {
                action.run();
            } catch (RuntimeException error) {
                fail.accept(error);
            }
        };

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                guard.accept(() -> super.onMessage(message));
            }

            @Override
            public void onHalfClose() {
                guard.accept(super::onHalfClose);
            }

            @Override
            public void onReady() {
                guard.accept(super::onReady);
            }

            @Override
            public void onComplete() {
                guard.accept(super::onComplete);
            }

            @Override
            public void onCancel() {
                closed.set(true);
                try {
                    super.onCancel();
                } catch (RuntimeException error) {
                    log.debug("Exception during cancelled RPC callback", error);
                }
            }
        };
    }
}
```

Các quyết định quan trọng:

- `closed` là state riêng của từng RPC, không phải field dùng chung của interceptor singleton.
- `close` được bọc để interceptor biết call đã kết thúc bình thường hoặc bằng status nào.
- Exception trong `startCall` hoặc listener callback được mapper chuyển thành status và đóng call nếu call chưa kết thúc.
- `onCancel` đánh dấu call đã terminal; không cố gửi thêm status sau khi client đã hủy.
- Exception phát sinh sau khi call đã đóng không được dùng để đóng lần hai.

Đây là mẫu xử lý exception đồng bộ tại callback boundary. Trong triển khai thật, cần quyết định logging/metrics cho exception bị bỏ qua sau terminal và kiểm thử với phiên bản gRPC Java đang dùng. Không bắt `Throwable` chung để nuốt cả `Error` như `OutOfMemoryError`; các lỗi JVM nghiêm trọng cần được xử lý theo chính sách runtime.

## 4. Exception trong tác vụ bất đồng bộ cần xử lý ở nơi hoàn tất

Interceptor không thể bắt exception xảy ra sau khi callback đã trả về, ví dụ:

```java
executor.execute(() -> {
    Product product = catalogService.loadProduct(productId);
    observer.onNext(toProto(product));
    observer.onCompleted();
});
```

Nếu `loadProduct` ném exception trên executor, stack đó không còn nằm trong lời gọi `onMessage` mà interceptor đang bọc. Phải chuyển lỗi ngay trong tác vụ:

```java
executor.execute(() -> {
    try {
        Product product = catalogService.loadProduct(productId);
        observer.onNext(toProto(product));
        observer.onCompleted();
    } catch (RuntimeException error) {
        GrpcExceptionMapper.MappedGrpcError mapped =
                exceptionMapper.map(error);
        observer.onError(mapped.status().asRuntimeException(
                mapped.trailers()));
    }
});
```

Với future/reactive pipeline, đặt mapping ở `exceptionally`, `onErrorMap` hoặc error handler tương ứng trước khi kết thúc `StreamObserver`. Bảo đảm chỉ có một terminal signal: không gọi `onError` sau `onCompleted`, và không phát thêm message sau terminal.

## 5. Giữ nguyên lỗi gRPC đã được chủ động tạo

Một service có thể chủ động trả status:

```java
observer.onError(
        Status.NOT_FOUND
                .withDescription("Product not found")
                .asRuntimeException());
```

Đây không phải exception bất ngờ cần đổi thành `INTERNAL`. Interceptor nên giữ nguyên status code và trailers đã được service xác định. Nếu cần thêm error details có cấu trúc, dùng trailer đã được chuẩn hóa, chẳng hạn `google.rpc.Status` và các detail type được client hỗ trợ; không nhét stack trace hoặc dữ liệu nhạy cảm vào description.

Khi service gọi `StreamObserver.onError(...)`, status được gửi như terminal signal của RPC chứ không phải exception ném ngược ra khỏi listener callback. Vì vậy, exception-mapping interceptor không remap đường đi này; service hoặc error handler tạo `onError` phải chọn status đúng ngay tại nơi đó.

`StatusException` là checked exception; `StatusRuntimeException` là unchecked exception. Cả hai mang status và có thể mang trailers. Khi chuyển từ mapper, giữ trailers nếu chúng chứa error detail được phép công bố. Chỉ cho phép các key/detail đã được kiểm soát, vì trailers cũng là dữ liệu gửi về client.

## 6. Phía client nhận status, không nhận exception server

Với async stub, kết quả lỗi đến trong callback `ClientCall.Listener.onClose` dưới dạng `Status`:

```java
@Override
public void onClose(Status status, Metadata trailers) {
    if (!status.isOk()) {
        log.warn("Catalog RPC failed with status={}", status.getCode());
    }
    delegate.onClose(status, trailers);
}
```

Blocking stub thường ném `StatusRuntimeException` cho status khác `OK`; future stub hoàn tất future ở trạng thái exceptional. Client interceptor nên quan sát và giữ nguyên status/trailers để caller xử lý theo hợp đồng.

Nếu cần chuyển status thành exception nghiệp vụ của client, thực hiện ở adapter/application boundary nơi gọi stub. Không đổi `NOT_FOUND` thành `INTERNAL` trong client interceptor chỉ để thống nhất log; việc đó làm mất semantics mà application cần.

## 7. Status mapping và thứ tự interceptor

Một chain server thường được tổ chức theo hướng:

```text
Tracing / Context
  -> Metrics / Logging
      -> Exception mapping
          -> Authentication / Authorization
              -> Service handler
```

Exception mapper cần bao quanh các interceptor/handler có thể ném exception để chuyển lỗi trước khi call đóng. Metrics/logging nằm ngoài mapper có thể quan sát status cuối đã được ánh xạ. Thứ tự thực tế phụ thuộc cách đăng ký interceptor của gRPC Java và Spring gRPC; phải kiểm tra bằng integration test, không suy luận chỉ từ thứ tự bean.

Authentication interceptor có thể chủ động `close(UNAUTHENTICATED)` mà không ném exception; exception mapper không cần đổi status đó. Metrics ở ngoài vẫn có thể ghi nhận status nếu chain được compose đúng.

## 8. Bảo mật thông tin lỗi

Status description và trailers là dữ liệu gửi tới client. Chỉ công bố nội dung client cần để xử lý:

- Dùng mô tả ngắn, ổn định như `Product not found` hoặc `Invalid request`.
- Không gửi stack trace, SQL, tên bảng, file path, hostname nội bộ hoặc token.
- Ghi stack trace ở server log với correlation/trace ID, sau khi đã loại bỏ credential và dữ liệu nhạy cảm.
- Không ghi toàn bộ trailers nếu chúng có thể chứa error detail hoặc dữ liệu từ caller.
- Dùng status phù hợp để client quyết định retry; ví dụ không retry mù quáng với `INVALID_ARGUMENT` hoặc `PERMISSION_DENIED`.

Với lỗi hạ tầng tạm thời, chọn status và retry policy nhất quán. Không chuyển mọi exception thành `UNAVAILABLE` vì client có thể retry một thao tác vốn không thể thành công; cũng không trả `INTERNAL` cho lỗi request mà client có thể sửa.

## 9. Kiểm thử exception mapping

| Ca kiểm thử | Kết quả cần xác minh |
| --- | --- |
| Exception nghiệp vụ not found | Client nhận `NOT_FOUND` |
| Request không hợp lệ | Client nhận `INVALID_ARGUMENT` |
| Credential sai | Giữ `UNAUTHENTICATED` do auth interceptor trả |
| Caller thiếu quyền | Giữ `PERMISSION_DENIED` |
| `StatusRuntimeException` có trailers | Status và trailers được giữ theo policy |
| Runtime exception bất ngờ | Client nhận `INTERNAL` với mô tả an toàn |
| Exception trong listener callback | Call đóng bằng status đã map, không bị treo |
| Exception trong executor/future | Error handler bất đồng bộ gọi đúng một terminal signal |
| Call đã đóng rồi mới phát sinh lỗi | Không đóng call lần hai |
| Nhiều RPC đồng thời | State và status của các call không bị trộn |
| Log/trailers | Không có stack trace hoặc credential bị lộ |

Test interceptor bằng in-process server/channel để kiểm tra status qua wire. Test mapper riêng để xác minh từng loại exception; test Spring integration để xác nhận interceptor thật sự được đăng ký. Đừng chỉ gọi trực tiếp hàm mapper rồi kết luận toàn bộ RPC pipeline đã được bảo vệ.

## 10. Checklist triển khai

- [ ] Có mapper tập trung cho exception nghiệp vụ và lỗi không dự kiến.
- [ ] Giữ nguyên `StatusException`/`StatusRuntimeException` đã được chủ động tạo.
- [ ] Dùng `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED`, `PERMISSION_DENIED` và `INTERNAL` theo đúng semantics.
- [ ] Bọc `next.startCall` và listener callback cần thiết.
- [ ] Dùng state per-call để bảo đảm chỉ đóng call một lần.
- [ ] Không bắt/nuốt `Error` của JVM.
- [ ] Xử lý exception trong executor/future/reactive pipeline tại nơi tác vụ hoàn tất.
- [ ] Không gửi stack trace, SQL hoặc dữ liệu nhạy cảm trong status/trailers.
- [ ] Client interceptor giữ nguyên status; chuyển thành exception nghiệp vụ ở application adapter nếu cần.
- [ ] Kiểm thử status, trailers, cancellation, async failure, concurrency và Spring registration.

**Tự kiểm tra**

**Câu 1.** Vì sao không nên chuyển mọi exception thành `INTERNAL`?

*Đáp án:* Client cần phân biệt lỗi request, không tìm thấy tài nguyên, thiếu xác thực, thiếu quyền và lỗi server. Ánh xạ một mã chung làm mất semantics và khiến client xử lý sai.

**Câu 2.** `Status.fromThrowable` có thay thế được exception mapper không?

*Đáp án:* Không. Nó tìm gRPC status trong cause chain; exception Java thông thường có thể thành `UNKNOWN`. Mapper tường minh cần ánh xạ exception nghiệp vụ và lỗi không dự kiến.

**Câu 3.** Server interceptor có bắt được exception ném từ executor sau khi listener callback đã trả về không?

*Đáp án:* Không. Tác vụ đã chạy ngoài callback boundary; cần catch và chuyển lỗi tại executor/future/reactive completion trước khi gọi `StreamObserver.onError`.

**Câu 4.** Client async interceptor nhận lỗi server dưới dạng gì?

*Đáp án:* Callback `onClose` nhận `Status` và trailers. Blocking stub thường chuyển status lỗi thành `StatusRuntimeException` cho caller.

**Câu 5.** Vì sao cần cờ per-call khi chuyển exception trong listener?

*Đáp án:* Call có thể đã đóng hoặc bị hủy trước khi callback khác ném lỗi. Cờ per-call ngăn interceptor gọi close lần hai và tránh trộn trạng thái giữa các RPC đồng thời.

Exception-mapping interceptor giúp chuẩn hóa lỗi đồng bộ tại ranh giới gRPC, nhưng không thay thế xử lý lỗi trong tác vụ bất đồng bộ. Dùng mapper tập trung, giữ nguyên status đã được chủ động tạo, đóng call đúng một lần và không để lộ chi tiết nội bộ; client khi đó nhận được lỗi ổn định để quyết định cách xử lý.
