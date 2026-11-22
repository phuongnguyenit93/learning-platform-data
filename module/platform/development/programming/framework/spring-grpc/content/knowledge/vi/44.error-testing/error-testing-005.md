# Test DEADLINE_EXCEEDED

Trong gRPC, deadline xác định thời điểm muộn nhất mà một RPC được phép tiếp tục. Khi ngân sách thời gian đã hết, client nhận status **DEADLINE_EXCEEDED**; server được thông báo call đã bị hủy và nên dừng công việc còn có thể dừng. Với Spring gRPC, kiểm thử cần xác minh cả status ở client, hành vi cancellation ở server và việc tài nguyên được giải phóng.

Deadline bao gồm thời gian chờ xử lý và trao đổi qua transport, không chỉ thời gian chạy câu lệnh trong service. Vì vậy, một method có thể hết hạn trước khi handler bắt đầu nếu request phải chờ queue hoặc connection. Deadline cũng không chứng minh thao tác chưa tạo side effect: server có thể đã commit dữ liệu ngay trước khi response tới client.

## 1. Phân biệt deadline, timeout và cancellation

- **Deadline** là mốc thời gian tuyệt đối mà call phải hoàn tất trước đó.
- **Timeout** thường là khoảng thời gian tương đối dùng để tạo deadline, ví dụ 300 ms tính từ lúc chuẩn bị RPC.
- **Cancellation** là tín hiệu dừng call, có thể do caller chủ động hủy, deadline hết hoặc một call cha bị hủy.

Các trạng thái thường gặp:

| Tình huống | Status phía client | Ý nghĩa |
| --- | --- | --- |
| Deadline của RPC hết hạn | DEADLINE_EXCEEDED | Ngân sách thời gian của call đã cạn |
| Caller chủ động cancel trước deadline | CANCELLED | Caller không còn cần kết quả |
| Server chủ động trả lỗi quá thời gian theo logic riêng | Có thể là DEADLINE_EXCEEDED | Cần phân biệt với deadline do runtime áp dụng |
| Dependency tạm thời không khả dụng | UNAVAILABLE | Lỗi availability, không mặc nhiên là hết deadline |

Không nên suy luận nguyên nhân chỉ từ một status nếu service có thể tự trả status cùng mã. Trong test deadline thực, đặt deadline ngắn ở client và giữ server xử lý lâu hơn để chứng minh runtime hủy call.

## 2. Cấu hình deadline cho generated stub

Generated stub là immutable. Phương thức withDeadlineAfter trả về stub mới có deadline tính từ thời điểm gọi phương thức:

~~~java
ReportServiceGrpc.ReportServiceBlockingStub callStub =
    reportStub.withDeadlineAfter(250, TimeUnit.MILLISECONDS);

ReportResponse response = callStub.generateReport(request);
~~~

Không bỏ qua stub dẫn xuất:

~~~java
// Sai: stub mới bị bỏ đi, RPC bên dưới vẫn dùng reportStub.
reportStub.withDeadlineAfter(250, TimeUnit.MILLISECONDS);
ReportResponse response = reportStub.generateReport(request);
~~~

Tạo stub có deadline tương đối gần thời điểm bắt đầu từng logical RPC. Không lưu stub đã cấu hình withDeadlineAfter trong Spring singleton để dùng cho các request sau, vì deadline vẫn tiếp tục trôi trong lúc stub được giữ.

## 3. Hợp đồng RPC dùng trong ví dụ

Giả sử service tạo báo cáo và có thể mất nhiều thời gian:

~~~proto
syntax = "proto3";

package acme.reports.v1;

option java_multiple_files = true;
option java_package = "com.acme.reports.v1";

service ReportService {
  rpc GenerateReport(GenerateReportRequest)
      returns (GenerateReportResponse);
}

message GenerateReportRequest {
  string report_id = 1;
}

message GenerateReportResponse {
  string report_id = 1;
  bytes content = 2;
}
~~~

Client chỉ chờ tối đa 100 ms trong test, trong khi server cố ý trì hoãn response 500 ms. Test sẽ xác minh client nhận DEADLINE_EXCEEDED trước khi server gửi kết quả.

## 4. Tạo server test có thể quan sát cancellation

Với unary RPC, gRPC Java cung cấp ServerCallStreamObserver để service biết call đã bị cancel. Ví dụ service test dùng scheduler để mô phỏng xử lý chậm:

~~~java
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

final class SlowReportService
        extends ReportServiceGrpc.ReportServiceImplBase {

    private final ScheduledExecutorService scheduler;
    private final long responseDelayMillis;
    final CountDownLatch handlerStarted = new CountDownLatch(1);
    final CountDownLatch cancellationObserved = new CountDownLatch(1);
    final AtomicInteger responseExecutions = new AtomicInteger();

    SlowReportService(
            ScheduledExecutorService scheduler,
            long responseDelayMillis) {
        this.scheduler = scheduler;
        this.responseDelayMillis = responseDelayMillis;
    }

    @Override
    public void generateReport(
            GenerateReportRequest request,
            StreamObserver<GenerateReportResponse> responseObserver) {

        ServerCallStreamObserver<GenerateReportResponse> serverObserver =
            (ServerCallStreamObserver<GenerateReportResponse>)
                responseObserver;

        handlerStarted.countDown();

        ScheduledFuture<?> task = scheduler.schedule(() -> {
            if (serverObserver.isCancelled()) {
                return;
            }

            responseExecutions.incrementAndGet();
            responseObserver.onNext(
                GenerateReportResponse.newBuilder()
                    .setReportId(request.getReportId())
                    .build());
            responseObserver.onCompleted();
        }, responseDelayMillis, TimeUnit.MILLISECONDS);

        serverObserver.setOnCancelHandler(() -> {
            task.cancel(false);
            cancellationObserved.countDown();
        });
    }
}
~~~

Service này chỉ dành cho test. Ứng dụng production cần gắn cancellation với tác vụ thực tế: cancel future, đóng stream hoặc statement nếu API hỗ trợ, và kiểm tra trạng thái call trước khi phát response. Không tiếp tục ghi response sau khi client đã hủy call.

Việc hủy task không đảm bảo mọi thư viện blocking lập tức dừng. Driver hoặc downstream call phải hỗ trợ interrupt/cancel; nếu không, công việc có thể tiếp tục chạy dù client đã nhận DEADLINE_EXCEEDED.

## 5. Kiểm thử deadline bằng in-process gRPC server

In-process transport chạy server và client trong cùng JVM, phù hợp để kiểm tra deadline, status và cancellation ở tầng gRPC mà không cần mở TCP port. JUnit 5 test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ReportDeadlineTest {

    private Server server;
    private ManagedChannel channel;
    private ScheduledExecutorService scheduler;
    private SlowReportService service;
    private ReportServiceGrpc.ReportServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        scheduler = Executors.newSingleThreadScheduledExecutor();
        service = new SlowReportService(scheduler, 500);

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(service)
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = ReportServiceGrpc.newBlockingStub(channel);
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
        if (scheduler != null) {
            scheduler.shutdownNow();
            assertTrue(scheduler.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void expiredDeadlineReturnsDeadlineExceededAndCancelsServerWork()
            throws InterruptedException {
        GenerateReportRequest request =
            GenerateReportRequest.newBuilder()
                .setReportId("report-42")
                .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.withDeadlineAfter(100, TimeUnit.MILLISECONDS)
                .generateReport(request));

        assertEquals(
            Status.Code.DEADLINE_EXCEEDED,
            error.getStatus().getCode());
        assertTrue(service.handlerStarted.await(1, TimeUnit.SECONDS));
        assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));
        assertEquals(0, service.responseExecutions.get());
    }

    @Test
    void sufficientDeadlineAllowsResponse() {
        GenerateReportResponse response = stub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .generateReport(
                GenerateReportRequest.newBuilder()
                    .setReportId("report-42")
                    .build());

        assertEquals("report-42", response.getReportId());
        assertEquals(1, service.responseExecutions.get());
    }
}
~~~

Test deadline ngắn xác minh ba điều: handler đã bắt đầu, client nhận đúng status và server nhận cancellation trước khi task tạo response. Test deadline đủ dài chứng minh service không bị đánh dấu lỗi chỉ vì có xử lý chậm.

directExecutor() phù hợp ở đây vì handler chỉ đăng ký task rồi trả về; phần chờ được thực hiện bởi scheduler riêng. Không dùng direct executor cho handler blocking dài hoặc cho tác vụ chờ latch trong cùng luồng dispatch.

## 6. Deadline của request cha và lời gọi downstream

Một service có thể gọi service khác trong khi đang xử lý RPC. Ngân sách call con không nên vượt thời gian còn lại của request cha. Chọn deadline sớm hơn giữa deadline cha và ngân sách riêng:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

private ReportServiceGrpc.ReportServiceBlockingStub
        downstreamStub(Duration childBudget) {

    if (childBudget.isNegative() || childBudget.isZero()) {
        throw new IllegalArgumentException("childBudget must be positive");
    }

    Deadline child = Deadline.after(
        childBudget.toNanos(), TimeUnit.NANOSECONDS);
    Deadline parent = Context.current().getDeadline();

    if (parent != null && parent.isBefore(child)) {
        child = parent;
    }

    return reportStub.withDeadline(child);
}
~~~

Nếu parent deadline đã hết, call con cũng hết hạn ngay; không tạo ngân sách mới để kéo dài request cha. Nếu service cha cần thời gian serialize response hoặc commit công việc cuối cùng, hãy trừ phần dự phòng khỏi child budget.

Khi chuyển tác vụ sang executor khác, cần truyền gRPC Context bằng Context.wrap(...) hoặc executor gắn context. Nếu context bị mất, task có thể không quan sát được cancellation của RPC cha.

## 7. Xác minh server dừng công việc sau cancellation

Client nhận DEADLINE_EXCEEDED không đồng nghĩa server đã dừng hoàn toàn. Một handler có thể tiếp tục truy vấn database hoặc gọi downstream nếu không kết nối cancellation với công việc.

Trong test cần xác minh:

- Cancellation handler được gọi.
- Future hoặc scheduled task bị cancel.
- Không phát response sau cancellation.
- Tài nguyên được giải phóng trong finally hoặc callback hoàn tất.
- Không bắt đầu thêm downstream call sau khi context đã bị cancel.

Với JDBC, dùng query timeout hoặc cancel statement nếu driver hỗ trợ. Với HTTP/gRPC downstream, giữ call handle để cancel khi request cha kết thúc. Với stream, dừng producer và giải phóng buffer. Không giữ lock hoặc permit sau khi tác vụ bị hủy.

## 8. Deadline hết không có nghĩa transaction đã rollback

Một tình huống nguy hiểm:

1. Server nhận command tạo payment.
2. Database commit thành công.
3. Response bị chậm trên đường về hoặc client hết deadline.
4. Client nhận DEADLINE_EXCEEDED và không biết thao tác đã commit hay chưa.

Do đó, không tự động gửi lại command tạo/cập nhật chỉ vì deadline hết. Với thao tác có side effect, dùng idempotency key hoặc operation ID. Caller có thể truy vấn trạng thái operation bằng cùng key để xác định kết quả thay vì tạo giao dịch trùng.

Test nên mô phỏng cả hai trường hợp: deadline hết trước khi side effect bắt đầu và deadline hết sau khi side effect đã commit nhưng response chưa về. Kết quả nghiệp vụ phải có cách truy vấn/đối soát rõ ràng.

## 9. Phân biệt DEADLINE_EXCEEDED với lỗi server tự trả

Một handler có thể chủ động trả Status.DEADLINE_EXCEEDED theo rule riêng. Để kiểm tra runtime deadline, test phải:

- Đặt deadline hữu hạn trên client stub.
- Cho handler chờ lâu hơn deadline.
- Xác minh cancellation callback được gọi.
- Xác minh task phía server không phát response.

Chỉ assert mã DEADLINE_EXCEEDED không chứng minh deadline runtime đã hủy call. Nếu cần chẩn đoán production, ghi nhận deadline còn lại lúc handler bắt đầu, thời gian xử lý, cancellation signal và dependency đang chờ; không log dữ liệu nhạy cảm của request.

## 10. Không retry mù khi deadline hết

Retry có thể hữu ích với lỗi tạm thời, nhưng mỗi attempt phải dùng chung ngân sách của logical operation. Không gọi withDeadlineAfter với toàn bộ timeout ban đầu ở đầu mỗi attempt, vì tổng thời gian có thể vượt SLA caller.

Trước retry:

1. Kiểm tra status có thuộc nhóm retryable theo policy không.
2. Kiểm tra deadline tổng còn đủ cho backoff và attempt mới không.
3. Xác định thao tác có idempotent hoặc có idempotency key không.
4. Giới hạn số attempt và tổng thời gian.
5. Không retry INVALID_ARGUMENT, UNAUTHENTICATED hoặc PERMISSION_DENIED như lỗi tạm thời.

DEADLINE_EXCEEDED thường cho biết ngân sách đã cạn; retry ngay bằng ngân sách mới có thể che giấu downstream chậm và tạo tải lớn hơn. Nếu caller có thể thử lại, hãy tạo một logical operation mới theo policy nghiệp vụ và giữ idempotency.

## 11. Ma trận kiểm thử đề xuất

| Kịch bản | Assertion phía client | Assertion phía server |
| --- | --- | --- |
| Deadline ngắn hơn thời gian xử lý | DEADLINE_EXCEEDED | Cancellation được nhận, task bị hủy |
| Deadline đủ dài | Thành công | Response được phát đúng một lần |
| Caller chủ động cancel trước deadline | CANCELLED | Cancellation handler chạy |
| Deadline cha hết trong lúc gọi downstream | Call con bị giới hạn theo cha | Không tiếp tục công việc sau cancellation |
| Server commit rồi response bị trễ | Client có thể nhận DEADLINE_EXCEEDED | Operation ID/idempotency cho phép truy vấn kết quả |
| Queue chậm trước handler | Deadline có thể hết trước khi xử lý | Handler không thực hiện công việc nếu call đã bị hủy |
| Retry policy được kích hoạt | Tổng thời gian không vượt ngân sách logical call | Không tạo side effect trùng |

In-process test xác minh gRPC deadline/cancellation trong JVM. Cần thêm integration test qua Netty/TLS hoặc proxy nếu muốn kiểm tra timeout ở load balancer, gateway, network và server production-like.

## 12. Ghi nhớ và tự kiểm tra

**Test DEADLINE_EXCEEDED** cần xác minh deadline hữu hạn làm client nhận đúng status, server quan sát cancellation và công việc còn có thể dừng được hủy an toàn. Dùng generated stub với withDeadlineAfter, in-process server có tác vụ trì hoãn và assertion cho cả client lẫn server. Bảo toàn deadline cha cho downstream, quản lý tài nguyên khi cancellation và dùng idempotency cho command có side effect.

Tự kiểm tra:

1. Vì sao deadline bao gồm cả thời gian chờ trước khi handler chạy?
2. DEADLINE_EXCEEDED khác CANCELLED như thế nào?
3. Vì sao chỉ assert status không chứng minh server đã dừng công việc?
4. Làm thế nào giới hạn deadline của call con theo request cha?
5. Vì sao client không thể kết luận transaction đã rollback khi nhận DEADLINE_EXCEEDED?
6. Cần kiểm tra gì trước khi retry một logical operation đã hết deadline?

Kiểm thử deadline đầy đủ giúp Spring gRPC giới hạn latency, giải phóng tài nguyên sau cancellation và bảo vệ hệ thống khỏi công việc tiếp tục chạy hoặc side effect bị lặp sau khi caller đã timeout.
