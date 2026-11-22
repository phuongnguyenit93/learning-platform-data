# Nuốt status code thành INTERNAL

## 1. Vì sao làm mất gRPC status là lỗi nghiêm trọng?

Trong **SPRING_GRPC**, gRPC status là một phần của contract giữa server và client. Status code cho biết RPC thất bại theo cách nào để caller quyết định sửa request, xác thực lại, chờ dependency phục hồi, retry hay dừng thao tác.

Một lỗi thường gặp là server nhận được lỗi đã có status cụ thể nhưng bắt exception rồi tạo một lỗi INTERNAL chung. Ví dụ service downstream trả UNAVAILABLE, application wrapper bắt lỗi rồi ném RuntimeException mới; exception mapper không nhận diện nguyên nhân và trả INTERNAL. Client mất tín hiệu rằng lỗi có thể tạm thời phục hồi.

Các hệ quả:

- Client không phân biệt được lỗi request với lỗi hạ tầng.
- Retry policy không hoạt động đúng vì UNAVAILABLE/ABORTED/RESOURCE_EXHAUSTED bị đổi thành INTERNAL.
- DEADLINE_EXCEEDED hoặc CANCELLED bị che khuất, khiến caller tiếp tục công việc không còn hữu ích.
- Rich error details và metadata trailers có thể bị mất.
- Dashboard ghi nhận INTERNAL tăng nhưng không thể xác định lỗi bắt đầu ở đâu.
- Client có thể retry lỗi nghiệp vụ vĩnh viễn hoặc không retry lỗi transient cần phục hồi.

**INTERNAL không phải status mặc định cho mọi exception.** Chỉ dùng nó cho lỗi không dự kiến mà server không có mapping cụ thể. Khi exception đã mang gRPC status, cần giữ nguyên status và trailers qua các tầng xử lý.

## 2. Status code là contract điều khiển hành vi client

Client thường dựa vào status để quyết định bước tiếp theo. Một số mã quan trọng:

| Status | Ý nghĩa điển hình | Hành động caller thường cân nhắc |
| --- | --- | --- |
| INVALID_ARGUMENT | Request không hợp lệ | Sửa input, không retry nguyên request |
| NOT_FOUND | Resource không tồn tại | Kiểm tra ID hoặc xử lý resource vắng mặt |
| ALREADY_EXISTS | Resource đã tồn tại | Đọc resource hiện có hoặc chọn key khác |
| PERMISSION_DENIED | Caller không có quyền | Không retry nếu quyền không thay đổi |
| UNAUTHENTICATED | Thiếu/sai authentication | Làm mới credential theo policy |
| FAILED_PRECONDITION | Trạng thái hiện tại không cho phép thao tác | Chờ hoặc thay đổi trạng thái nghiệp vụ |
| ABORTED | Xung đột trong workflow/concurrency | Đọc lại và thử lại toàn bộ workflow nếu contract cho phép |
| RESOURCE_EXHAUSTED | Hết quota hoặc tài nguyên | Backoff, giảm tải hoặc chờ quota |
| UNAVAILABLE | Service/dependency tạm thời không sẵn sàng | Có thể retry với backoff và deadline |
| DEADLINE_EXCEEDED | Hết ngân sách thời gian | Xác định outcome; command cần idempotency |
| CANCELLED | Caller hủy lời gọi | Dừng công việc còn có thể hủy |
| INTERNAL | Lỗi nội bộ không dự kiến | Điều tra server; không mặc định retry |

Status không chỉ phục vụ hiển thị lỗi. Nó ảnh hưởng retry, circuit breaker, telemetry, alert và cách client phục hồi.

## 3. Anti-pattern: bắt mọi exception rồi trả INTERNAL

Ví dụ mapper sai:

```java
public StatusRuntimeException toStatus(Throwable error) {
    return Status.INTERNAL
        .withDescription("Request failed")
        .asRuntimeException();
}
```

Cách này biến mọi lỗi thành cùng một status, kể cả RequestValidationException, ResourceNotFoundException, StatusRuntimeException từ downstream hoặc lỗi deadline.

Một biến thể cũng nguy hiểm:

```java
try {
    return downstreamStub
        .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
        .getOrder(request);
} catch (Exception ex) {
    throw new RuntimeException("Order lookup failed");
}
```

Exception mới không giữ nguyên status như một contract có chủ đích. Nếu cause không được giữ hoặc mapper chỉ nhìn lớp exception ngoài cùng, UNAVAILABLE/DEADLINE_EXCEEDED có thể bị đổi thành INTERNAL. Message chung cũng làm mất thông tin chẩn đoán cần thiết.

Không bắt Exception hoặc Throwable chỉ để đổi tất cả lỗi thành INTERNAL. Hãy bắt đúng loại lỗi mà tầng đó có thể xử lý; lỗi không xử lý được nên được truyền tiếp cùng nguyên nhân.

## 4. Giữ nguyên StatusRuntimeException và StatusException

gRPC Java dùng StatusRuntimeException và StatusException để mang status, description cùng optional metadata trailers.

Nếu application hoặc adapter nhận được một trong hai loại này, thông thường nên truyền tiếp nguyên exception:

```java
public Throwable preserveOrMap(Throwable error) {
    if (error instanceof StatusRuntimeException
            || error instanceof StatusException) {
        return error;
    }

    return mapApplicationError(error);
}
```

Việc trả nguyên exception giữ status và trailers gốc. Không tạo một Status.INTERNAL mới chỉ vì exception được ném từ service khác hoặc từ client stub.

Nếu cần bổ sung log context, hãy log method, correlation ID và cause ở server; không nhất thiết phải thay exception. Nếu thật sự cần chuyển đổi wrapper, giữ nguyên status code, description đã được phép công khai và trailers theo contract.

## 5. Xử lý exception bị bọc trong CompletionException hoặc ExecutionException

Trong code bất đồng bộ, lỗi có thể bị bọc:

- CompletableFuture thường hoàn tất exceptional với CompletionException.
- Future.get() có thể ném ExecutionException.
- Reflection có thể bọc lỗi trong InvocationTargetException.
- Framework/application wrapper có thể tạo exception khác và giữ cause.

Nếu mapper chỉ kiểm tra lớp ngoài cùng, nó có thể bỏ sót StatusRuntimeException ở cause chain.

Một cách tiếp cận là tìm status exception trong cause chain trước khi phân loại domain exception:

```java
private Throwable findGrpcStatus(Throwable error) {
    Set<Throwable> seen =
        Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = error;
    while (current != null && seen.add(current)) {
        if (current instanceof StatusRuntimeException
                || current instanceof StatusException) {
            return current;
        }
        current = current.getCause();
    }
    return null;
}
```

Sau đó mapper ưu tiên giữ status đã có:

```java
public Throwable toGrpcError(Throwable error) {
    Throwable grpcStatus = findGrpcStatus(error);
    if (grpcStatus != null) {
        return grpcStatus;
    }

    Throwable cause = unwrapAsyncWrappers(error);
    return mapApplicationError(cause);
}
```

unwrapAsyncWrappers chỉ nên bỏ những wrapper kỹ thuật đã biết và chỉ khi có cause. Không duyệt cause chain vô hạn hoặc bỏ qua exception gốc một cách tùy tiện. Nếu application wrapper mang ý nghĩa nghiệp vụ riêng, hãy xử lý theo type của wrapper đó.

gRPC Java còn cung cấp Status.fromThrowable và Status.trailersFromThrowable để trích xuất status/trailers từ throwable có chứa gRPC status trong cause chain. Tuy nhiên, đừng dùng kết quả UNKNOWN của một throwable thông thường như bằng chứng rằng lỗi gốc chắc chắn là status UNKNOWN; cần phân biệt lỗi gRPC có chủ đích với exception Java thông thường.

## 6. Ánh xạ domain exception theo loại

Exception nghiệp vụ không mang sẵn gRPC status có thể được ánh xạ tại biên transport:

```java
public Throwable mapApplicationError(Throwable error) {
    if (error instanceof RequestValidationException) {
        return Status.INVALID_ARGUMENT
            .withDescription("Request validation failed")
            .asRuntimeException();
    }

    if (error instanceof ResourceNotFoundException) {
        return Status.NOT_FOUND
            .withDescription("Resource not found")
            .asRuntimeException();
    }

    if (error instanceof BusinessPreconditionException) {
        return Status.FAILED_PRECONDITION
            .withDescription("Operation is not allowed")
            .asRuntimeException();
    }

    if (error instanceof AccessDeniedException) {
        return Status.PERMISSION_DENIED
            .withDescription("Permission denied")
            .asRuntimeException();
    }

    if (error instanceof TransientDependencyException) {
        return Status.UNAVAILABLE
            .withDescription("Dependency temporarily unavailable")
            .asRuntimeException();
    }

    return Status.INTERNAL
        .withDescription("Unexpected server error")
        .asRuntimeException();
}
```

Đây là ví dụ policy; exception type và status cần khớp contract của hệ thống. Không map mọi DataAccessException thành UNAVAILABLE: lỗi constraint, SQL syntax hoặc mapping có thể là lỗi permanent. Cũng không map mọi IllegalStateException thành FAILED_PRECONDITION nếu đó thực ra là bug lập trình.

Thứ tự xử lý quan trọng: giữ status gRPC đã tồn tại trước; sau đó mới ánh xạ exception nghiệp vụ; cuối cùng mới dùng INTERNAL cho lỗi không nhận diện.

## 7. Phân biệt lỗi ở server với lỗi từ downstream

Một service SPRING_GRPC có thể gọi service khác. Khi downstream trả status, service trung gian cần quyết định giữ nguyên hay chuyển đổi theo contract của API hiện tại.

Giữ nguyên status thường phù hợp khi:

- RPC trung gian là proxy/facade và status downstream có cùng ý nghĩa với caller.
- UNAVAILABLE hoặc DEADLINE_EXCEEDED phản ánh dependency mà caller cần biết.
- Rich details có ý nghĩa và an toàn để chuyển tiếp.

Chuyển đổi có chủ đích phù hợp khi:

- API hiện tại có contract riêng, không muốn lộ chi tiết nội bộ.
- Downstream status không có cùng semantics với public API.
- Cần ánh xạ lỗi domain nội bộ thành status public ổn định.

Khi chuyển đổi, không nên biến mọi lỗi downstream thành INTERNAL. Ví dụ, downstream NOT_FOUND có thể tương ứng ResourceNotFound ở API hiện tại; downstream PERMISSION_DENIED có thể cần xử lý theo authorization boundary; downstream UNAVAILABLE thường vẫn là lỗi dependency tạm thời.

Không forward nguyên description hoặc trailers của hệ thống nội bộ ra public client nếu chúng chứa hostname, SQL, service name, tenant data hay thông tin vận hành nhạy cảm. Có thể giữ code nhưng thay description/details bằng nội dung public đã kiểm soát.

## 8. Giữ metadata trailers và rich error details

gRPC error có thể mang trailers ngoài status code và description. Ứng dụng có thể dùng rich error model như google.rpc.BadRequest, ErrorInfo hoặc RetryInfo để cung cấp field violation, reason hay retry delay.

Nếu mapper tạo exception mới mà không chuyển trailers, client mất các details đó. Khi cần giữ nguyên lỗi, truyền nguyên StatusException/StatusRuntimeException. Khi cần chuyển đổi, chỉ xây dựng details mới sau khi đã quyết định contract và kiểm tra dữ liệu được phép công khai.

Ví dụ tạo rich INVALID_ARGUMENT detail:

```java
BadRequest detail = BadRequest.newBuilder()
    .addFieldViolations(
        BadRequest.FieldViolation.newBuilder()
            .setField("customer_id")
            .setDescription("customer_id is required")
    )
    .build();

com.google.rpc.Status richStatus =
    com.google.rpc.Status.newBuilder()
        .setCode(Code.INVALID_ARGUMENT_VALUE)
        .setMessage("Request validation failed")
        .addDetails(Any.pack(detail))
        .build();

throw StatusProto.toStatusRuntimeException(richStatus);
```

Client tương thích có thể dùng StatusProto.fromThrowable để đọc details. Nếu client không hiểu rich detail type, nó vẫn phải xử lý status code cơ bản. Không đặt dữ liệu nhạy cảm hoặc stack trace trong error details.

## 9. Không nuốt status trong callback bất đồng bộ

Với CompletableFuture, lỗi có thể được chuyển qua exceptionally/handle rồi bị đổi thành giá trị mặc định hoặc RuntimeException chung:

```java
future.exceptionally(error -> {
    log.error("Downstream failed", error);
    throw new CompletionException(error);
});
```

Nếu chỉ log rồi trả null/default, caller có thể nhận response thành công giả. Nếu bọc lỗi mà không giữ cause, status gRPC gốc biến mất.

Trong async gRPC service, khi hoàn tất lỗi, chuyển throwable đã được preserve/map vào observer.onError:

```java
future.whenComplete((reply, error) -> {
    if (error != null) {
        observer.onError(exceptionMapper.toGrpcError(error));
        return;
    }

    observer.onNext(reply);
    observer.onCompleted();
});
```

Đảm bảo chỉ có một terminal path cho mỗi RPC. Không gọi onNext hoặc onCompleted sau onError; không gọi onError nhiều lần từ các callback cạnh tranh. Nếu future bị cancel do client hủy, giữ semantics CANCELLED và không biến nó thành INTERNAL.

## 10. Streaming RPC cũng phải giữ status

Với server-streaming hoặc bidirectional streaming, lỗi có thể xảy ra sau khi server đã gửi một số message. Khi đó observer.onError kết thúc stream với status; các message đã gửi không thể thu hồi.

Một số nguyên tắc:

- Không gửi INTERNAL chung nếu lỗi gốc đã có status cụ thể.
- Gọi onError đúng một lần và dừng producer.
- Hủy subscription/task upstream khi client cancel.
- Không gửi message tiếp sau terminal signal.
- Ghi rõ semantics partial result trong API; status lỗi không đồng nghĩa các message đã gửi chưa được client xử lý.
- Với command stream có side effect, dùng sequence/idempotency/checkpoint để client biết phần nào đã commit.

Không cố “sửa” một stream đã lỗi bằng cách gửi một message lỗi trong response rồi gọi onCompleted nếu contract quy định lỗi transport phải là gRPC status. Dùng status/trailers nhất quán với client contract.

## 11. Cancellation và deadline không phải INTERNAL

Deadline hết và client cancel là các trạng thái bình thường trong hệ thống phân tán, không nhất thiết là lỗi server:

- DEADLINE_EXCEEDED: caller hết ngân sách thời gian.
- CANCELLED: caller không còn muốn tiếp tục call.
- UNAVAILABLE: service/dependency không sẵn sàng tạm thời.
- RESOURCE_EXHAUSTED: giới hạn tài nguyên/quota đã đạt.

Không bắt các lỗi này rồi trả INTERNAL. Giữ status giúp client dừng, retry hoặc giảm tải đúng cách.

Nếu cancellation xuất hiện trong worker thread, truyền cancellation signal và dừng công việc có thể hủy. JDBC driver có thể cần query timeout riêng; gRPC cancellation không bảo đảm query tự dừng ngay. Không giả định một command chưa commit chỉ vì client đã hủy.

## 12. Logging và observability khi mapping lỗi

Status mapping tốt cần quan sát được từ server tới client. Ghi nhận:

- RPC method và status code cuối.
- Exception class gốc và cause chain đã được mask dữ liệu nhạy cảm.
- Downstream target/service khi lỗi bắt nguồn từ dependency.
- Correlation/trace ID.
- Deadline remaining hoặc thời gian xử lý tại thời điểm lỗi.
- Retry attempt và dependency outcome.
- Rich detail type hoặc application error code nếu contract có dùng.

Không log bearer token, private key, request payload đầy đủ hoặc SQL chứa dữ liệu nhạy cảm. Status description trả client nên ngắn, ổn định và không lộ stack trace/hostname nội bộ.

Không alert chỉ theo tổng số exception. Theo dõi tỷ lệ status theo method và dependency: INTERNAL tăng có thể là bug mới; UNAVAILABLE tăng có thể là outage; INVALID_ARGUMENT tăng đột biến có thể là client regression.

## 13. Kiểm thử status mapping end-to-end

Unit test mapper chưa đủ. Cần gọi RPC qua server thật hoặc integration harness để xác nhận status thực tế tới client:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Application validation exception | Client nhận INVALID_ARGUMENT |
| Resource missing | Client nhận NOT_FOUND |
| Business precondition fail | Client nhận FAILED_PRECONDITION |
| Downstream StatusRuntimeException UNAVAILABLE | Status được giữ hoặc chuyển đổi theo public contract |
| StatusException có trailers | Rich details được giữ khi policy yêu cầu |
| CompletionException bọc status | Mapper tìm đúng status ở cause chain |
| Unknown Java exception | Chỉ trường hợp này mới fallback INTERNAL |
| Client deadline hết | DEADLINE_EXCEEDED không bị đổi thành INTERNAL |
| Client cancel | CANCELLED được giữ và công việc dừng theo khả năng |
| Streaming lỗi sau một số message | onError một lần; không có message sau terminal |
| Error description | Không chứa SQL, stack trace, secret hoặc hostname nội bộ |

Ví dụ assertion ở client:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> blockingStub.getOrder(request)
);

assertEquals(
    Status.Code.UNAVAILABLE,
    Status.fromThrowable(error).getCode()
);
```

Với rich details, kiểm tra cả code và detail type/content được phép công khai. Test một lỗi wrapper thực tế như CompletionException để tránh chỉ xác minh mapper với exception trực tiếp.

## 14. Checklist review

- Không bắt mọi exception rồi đổi thành INTERNAL.
- StatusRuntimeException và StatusException được giữ nguyên khi contract cho phép.
- Cause chain được kiểm tra khi lỗi đi qua async/framework wrapper.
- Status và trailers không bị mất khi unwrap hoặc chuyển đổi.
- Domain exception được map theo type và public API contract.
- INTERNAL chỉ dùng cho lỗi không dự kiến chưa có mapping cụ thể.
- Downstream status được giữ hoặc chuyển đổi có chủ đích, không che outage.
- Rich error details không chứa secret/stack trace.
- Async callback không nuốt lỗi hoặc trả response thành công giả.
- Streaming observer chỉ phát một terminal signal.
- DEADLINE_EXCEEDED và CANCELLED không bị đổi thành INTERNAL.
- Log có correlation, method, status và cause an toàn.
- Có gRPC integration tests cho direct, wrapped, async và streaming errors.

Trong **SPRING_GRPC**, nuốt status code rồi trả INTERNAL làm client mất khả năng phân loại lỗi và phục hồi đúng cách. Hãy giữ nguyên StatusException/StatusRuntimeException cùng trailers khi có thể, xử lý cause chain của wrapper bất đồng bộ và chỉ ánh xạ domain exception tại biên transport. Dành INTERNAL cho lỗi thực sự không dự kiến; xác minh status cuối cùng bằng integration test qua gRPC server.
