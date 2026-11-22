# Test RESOURCE_EXHAUSTED

Trong gRPC, **RESOURCE_EXHAUSTED** cho biết một tài nguyên cần thiết đã cạn hoặc một giới hạn được áp dụng đã bị vượt. Với Spring gRPC, nguyên nhân thường gặp là quota theo tenant, rate limit, giới hạn concurrency, dung lượng lưu trữ hoặc kích thước message vượt cấu hình. Kiểm thử cần xác minh đúng status, không thực hiện side effect khi request bị từ chối và phân biệt quota exhaustion với lỗi availability.

RESOURCE_EXHAUSTED không đồng nghĩa server bị down. Server vẫn có thể khỏe và xử lý request của caller khác, trong khi một tenant đã hết quota hoặc một request cụ thể vượt giới hạn message. Vì vậy, test phải kiểm tra đúng phạm vi giới hạn: user, tenant, method, server instance hay transport.

## 1. Các nguyên nhân dẫn tới RESOURCE_EXHAUSTED

| Nguyên nhân | Phạm vi giới hạn | Hành vi thường mong đợi |
| --- | --- | --- |
| Quota theo tenant/user | Một tenant hoặc caller | Từ chối phần sử dụng vượt hạn mức |
| Rate limit | Số request trong cửa sổ thời gian | Từ chối request vượt tốc độ |
| Concurrency limit | Số tác vụ đang chạy đồng thời | Từ chối hoặc xếp hàng theo policy |
| Message size limit | Một request hoặc response | Từ chối message vượt kích thước cấu hình |
| Storage/resource capacity | Dung lượng hoặc tài nguyên hệ thống | Từ chối thao tác cần thêm tài nguyên |

Phân biệt với status khác:

| Status | Ý nghĩa |
| --- | --- |
| RESOURCE_EXHAUSTED | Caller hoặc request đã vượt giới hạn tài nguyên/quota |
| UNAVAILABLE | Service hoặc dependency hiện không thể phục vụ |
| DEADLINE_EXCEEDED | Ngân sách thời gian của RPC đã hết |
| INVALID_ARGUMENT | Dữ liệu request sai theo hợp đồng |
| FAILED_PRECONDITION | Trạng thái hiện tại không cho phép thực hiện thao tác |

Ví dụ: tenant đã dùng hết dung lượng upload thì trả RESOURCE_EXHAUSTED; database mất kết nối khi kiểm tra quota thì trả lỗi availability phù hợp, không giả vờ quota đã cạn. Request chứa file lớn hơn max inbound message size cũng có thể bị transport từ chối bằng RESOURCE_EXHAUSTED trước khi service handler chạy.

## 2. Hợp đồng RPC dùng trong ví dụ

Giả sử service nhận nội dung upload:

~~~proto
syntax = "proto3";

package acme.storage.v1;

option java_multiple_files = true;
option java_package = "com.acme.storage.v1";

service UploadService {
  rpc Upload(UploadRequest) returns (UploadResponse);
}

message UploadRequest {
  string object_name = 1;
  bytes payload = 2;
}

message UploadResponse {
  string object_id = 1;
  int64 stored_bytes = 2;
}
~~~

Tenant được lấy từ principal đã xác thực trong gRPC Context. Không tin tenant ID do client tự gửi trong payload hoặc metadata để quyết định quota.

Khai báo context key mà service và authentication interceptor cùng sử dụng:

~~~java
import io.grpc.Context;

public final class TenantContext {
    public static final Context.Key<String> TENANT_ID =
        Context.key("authenticated-tenant-id");

    private TenantContext() {}
}
~~~

## 3. Ánh xạ quota bị vượt thành RESOURCE_EXHAUSTED

Tách kiểm tra quota và lưu trữ thành hai abstraction:

~~~java
public interface QuotaService {
    boolean allows(String tenantId, long requestedBytes);
}

public interface UploadRepository {
    UploadResponse store(
        String tenantId,
        UploadRequest request);
}
~~~

Service kiểm tra quota trước khi gọi repository:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class UploadGrpcService
        extends UploadServiceGrpc.UploadServiceImplBase {

    private final QuotaService quotaService;
    private final UploadRepository repository;

    public UploadGrpcService(
            QuotaService quotaService,
            UploadRepository repository) {
        this.quotaService = quotaService;
        this.repository = repository;
    }

    @Override
    public void upload(
            UploadRequest request,
            StreamObserver<UploadResponse> responseObserver) {

        if (request.getObjectName().isBlank()
                || request.getPayload().isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("object_name and payload are required")
                    .asRuntimeException());
            return;
        }

        String tenantId = TenantContext.TENANT_ID.get();
        if (tenantId == null) {
            responseObserver.onError(
                Status.UNAUTHENTICATED
                    .withDescription("authentication is required")
                    .asRuntimeException());
            return;
        }

        long requestedBytes = request.getPayload().size();
        if (!quotaService.allows(tenantId, requestedBytes)) {
            responseObserver.onError(
                Status.RESOURCE_EXHAUSTED
                    .withDescription("tenant storage quota exceeded")
                    .asRuntimeException());
            return;
        }

        UploadResponse response = repository.store(tenantId, request);
        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

Đây là ví dụ minh họa ranh giới kiểm tra. Trong hệ thống production, thao tác kiểm tra và giữ quota phải nguyên tử hoặc dùng reservation/lease; nếu chỉ gọi allows rồi mới ghi dữ liệu, hai request đồng thời có thể cùng nhìn thấy phần quota còn lại và vượt hạn mức. Reservation cần được commit khi lưu thành công và release khi lưu thất bại.

Không gọi repository, phát event hoặc gửi message trước khi quota được chấp nhận. Nếu quota service không khả dụng, ánh xạ lỗi theo tình trạng hạ tầng, ví dụ UNAVAILABLE; không đổi lỗi đó thành RESOURCE_EXHAUSTED.

## 4. Truyền tenant context trong test

Test có thể dùng server interceptor để gắn tenant đã xác thực vào gRPC Context. Interceptor này chỉ là fixture cho test service logic:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

final class TestTenantServerInterceptor
        implements ServerInterceptor {

    private final String tenantId;

    TestTenantServerInterceptor(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Context context = Context.current().withValue(
            TenantContext.TENANT_ID, tenantId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Trong production, tenant context phải đến từ authentication layer đã xác minh. Không dùng header tùy ý do client gửi để tạo tenant identity.

## 5. Kiểm thử quota bằng in-process gRPC server

In-process transport phù hợp để kiểm tra logic quota, status mapping và bảo đảm repository không được gọi khi quota đã hết:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import com.google.protobuf.ByteString;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class UploadQuotaTest {

    private Server server;
    private ManagedChannel channel;
    private UploadServiceGrpc.UploadServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        QuotaService exhaustedQuota =
            (tenantId, requestedBytes) -> false;

        UploadRepository repository = (tenantId, request) -> {
            repositoryCalls.incrementAndGet();
            return UploadResponse.newBuilder()
                .setObjectId("object-123")
                .setStoredBytes(request.getPayload().size())
                .build();
        };

        UploadGrpcService service =
            new UploadGrpcService(exhaustedQuota, repository);

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                service,
                new TestTenantServerInterceptor("tenant-a")))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = UploadServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void exhaustedTenantQuotaReturnsResourceExhaustedBeforeStore() {
        UploadRequest request = UploadRequest.newBuilder()
            .setObjectName("archive.bin")
            .setPayload(ByteString.copyFrom(new byte[1024]))
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.upload(request));

        assertEquals(
            Status.Code.RESOURCE_EXHAUSTED,
            error.getStatus().getCode());
        assertEquals(
            "tenant storage quota exceeded",
            error.getStatus().getDescription());
        assertEquals(0, repositoryCalls.get());
    }
}
~~~

Ví dụ test dùng fake quota luôn từ chối để tái hiện tenant đã hết hạn mức. Assertion quan trọng là status code chính xác và repository không được gọi. Có thể bổ sung test quota cho phép để chứng minh request hợp lệ vẫn được lưu và response trả về đúng kích thước.

directExecutor() phù hợp với handler ngắn, không blocking. Nếu quota service gọi database hoặc remote quota server, dùng executor phù hợp và deadline riêng; không chặn transport thread.

## 6. Kiểm thử message vượt maxInboundMessageSize

Quota nghiệp vụ và giới hạn kích thước transport là hai cơ chế khác nhau. Để kiểm tra giới hạn message, chạy server transport thực với max inbound message size nhỏ:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.protobuf.ByteString;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class UploadMessageSizeTest {

    @Test
    void requestLargerThanServerLimitReturnsResourceExhausted()
            throws Exception {
        Server server = ServerBuilder.forPort(0)
            .maxInboundMessageSize(256)
            .addService(new UploadGrpcService(
                (tenantId, bytes) -> true,
                (tenantId, request) -> UploadResponse.getDefaultInstance()))
            .build()
            .start();

        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", server.getPort())
            .usePlaintext()
            .build();

        try {
            UploadServiceGrpc.UploadServiceBlockingStub stub =
                UploadServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(2, TimeUnit.SECONDS);

            UploadRequest request = UploadRequest.newBuilder()
                .setObjectName("large.bin")
                .setPayload(ByteString.copyFrom(new byte[4096]))
                .build();

            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.upload(request));

            assertEquals(
                Status.Code.RESOURCE_EXHAUSTED,
                error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Request có payload lớn hơn giới hạn 256 byte nên bị server transport từ chối trước khi service handler xử lý. Vì vậy test này xác minh giới hạn message, không xác minh quota service. Nếu project dùng Netty shaded, bảo đảm runtime server/channel provider và dependency tương thích; không trộn class shaded với unshaded.

Client cũng có giới hạn inbound message cho response. Nếu response vượt giới hạn nhận của client, client có thể quan sát RESOURCE_EXHAUSTED dù server đã gửi response. Khi chẩn đoán cần xác định giới hạn nằm ở server request, server response, client inbound hay proxy.

## 7. Phân biệt quota, rate limit và concurrency limit

Các policy này đều có thể dùng RESOURCE_EXHAUSTED nhưng cần test khác nhau:

| Policy | Điều kiện kiểm tra | Assertion |
| --- | --- | --- |
| Quota tích lũy | Tổng byte/request trong chu kỳ vượt hạn mức | Request vượt phần còn lại bị từ chối |
| Rate limit | Số call trong cửa sổ thời gian vượt ngưỡng | Call vượt tốc độ nhận RESOURCE_EXHAUSTED |
| Concurrency | Số tác vụ đang chạy đạt giới hạn | Tác vụ mới bị từ chối hoặc chờ theo policy |
| Message size | Serialized message vượt giới hạn | Transport từ chối trước handler |

Với concurrency test, dùng latch/barrier để giữ các call đầu tiên đang chạy, sau đó gửi call vượt giới hạn. Không dựa vào Thread.sleep() để tạo race. Khi giải phóng latch, xác minh permit được trả lại để call sau có thể thành công.

## 8. Retry và hướng dẫn cho client

Không tự động retry mọi RESOURCE_EXHAUSTED:

- Request vượt message size không thể thành công khi gửi lại nguyên payload; caller cần chia nhỏ hoặc thay đổi encoding theo hợp đồng.
- Quota tích lũy cần chờ chu kỳ cấp quota hoặc thay đổi hạn mức.
- Rate limit có thể retry sau thời gian chờ nếu server công bố thời điểm hợp lý.
- Concurrency limit có thể retry sau backoff ngắn nếu deadline tổng còn đủ.
- Storage full cần giải phóng hoặc mở rộng dung lượng trước khi thử lại.

Nếu API có thể xác định thời điểm retry, có thể trả rich error detail google.rpc.RetryInfo. Nếu không có thời điểm cụ thể, client dùng exponential backoff có jitter và giới hạn số lần thử. Không retry dồn dập vì có thể làm quota/rate limit nghiêm trọng hơn.

Đối với RPC ghi, dùng idempotency key để tránh tạo dữ liệu trùng khi server đã nhận request nhưng response bị mất. Retry phải nằm trong deadline tổng của logical operation.

## 9. Rich error detail cho quota failure

Khi client cần biết quota nào bị vượt, có thể dùng rich error model google.rpc.QuotaFailure. Chỉ đưa thông tin caller được phép biết; không tiết lộ quota của tenant khác hoặc cấu hình nội bộ:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.QuotaFailure;
import com.google.rpc.Status;
import io.grpc.protobuf.StatusProto;

QuotaFailure failure = QuotaFailure.newBuilder()
    .addViolations(QuotaFailure.Violation.newBuilder()
        .setSubject("tenant-storage")
        .setDescription("storage quota exceeded")
        .build())
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(io.grpc.Status.Code.RESOURCE_EXHAUSTED.value())
    .setMessage("resource limit exceeded")
    .addDetails(Any.pack(failure))
    .build();

responseObserver.onError(
    StatusProto.toStatusRuntimeException(richStatus));
~~~

Client có thể đọc detail bằng StatusProto.fromThrowable(error) và unpack đúng type. Nếu proxy không giữ trailers, status code và message cơ bản vẫn phải đủ để client xử lý. Không đặt thông tin nhạy cảm như số dư quota của tenant khác vào detail.

## 10. Kiểm thử qua Spring application context

In-process test xác minh service logic và status mapping, nhưng không chứng minh starter đăng ký đúng service, interceptor, quota provider hoặc transport limit. Bổ sung Spring integration test để:

- Khởi động application context với quota provider giả hoặc test implementation.
- Gọi RPC qua server do Spring gRPC starter quản lý.
- Xác minh tenant lấy từ principal đã xác thực.
- Xác minh quota bị từ chối trước repository và event publisher.
- Xác minh max inbound message size được cấu hình đúng ở server.
- Xác minh metadata, rich error details và TLS nếu production sử dụng.

Tên property cấu hình message size và extension point server phụ thuộc starter/version. Dùng API thực tế của dự án; không giả định một property chung cho mọi Spring gRPC starter.

## 11. Ma trận kiểm thử đề xuất

| Kịch bản | Status/kết quả | Side effect |
| --- | --- | --- |
| Tenant còn quota | Thành công | Lưu đúng một lần |
| Tenant vượt quota | RESOURCE_EXHAUSTED | Không lưu |
| Rate limit vượt ngưỡng | RESOURCE_EXHAUSTED | Không xử lý call bị từ chối |
| Concurrency đạt giới hạn | RESOURCE_EXHAUSTED hoặc queue theo policy | Permit được trả khi call hoàn tất |
| Request vượt max inbound size | RESOURCE_EXHAUSTED | Handler không chạy |
| Quota provider không khả dụng | UNAVAILABLE hoặc lỗi hạ tầng phù hợp | Không giả thành quota exhausted |
| Request sai field | INVALID_ARGUMENT | Không kiểm tra quota hoặc lưu |
| Quota được cấp lại | Request mới thành công | Lưu đúng một lần |

Test cần xác minh status code, repository invocation, permit/reservation lifecycle và hành vi phục hồi. Không chỉ assert description vì message có thể thay đổi theo phiên bản.

## 12. Ghi nhớ và tự kiểm tra

**Test RESOURCE_EXHAUSTED** cần bao phủ cả giới hạn nghiệp vụ và giới hạn transport. Dùng in-process server để kiểm tra quota/rate/concurrency và chứng minh không có side effect; dùng transport thực với maxInboundMessageSize để kiểm tra request quá lớn bị từ chối trước handler. Phân biệt RESOURCE_EXHAUSTED với UNAVAILABLE, chỉ retry khi policy cho phép và bảo toàn idempotency cho RPC ghi.

Tự kiểm tra:

1. Vì sao quota hết không đồng nghĩa server unavailable?
2. Vì sao kiểm tra quota phải nguyên tử khi có nhiều request đồng thời?
3. Test nào chứng minh repository không được gọi khi tenant hết quota?
4. Vì sao message vượt max inbound size cần transport test?
5. Khi nào client có thể retry RESOURCE_EXHAUSTED?
6. Vì sao RPC ghi cần idempotency key khi retry sau lỗi tài nguyên?

Kiểm thử RESOURCE_EXHAUSTED đúng giúp Spring gRPC thực thi giới hạn tài nguyên có thể dự đoán, bảo vệ service khỏi quá tải và cung cấp hướng xử lý rõ ràng cho client.
