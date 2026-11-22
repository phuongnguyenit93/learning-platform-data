# Kiểm thử server chậm và client timeout

Một lỗi timeout chỉ được kiểm thử đầy đủ khi xác minh cả hai phía của RPC: **client nhận status đúng khi server xử lý quá lâu**, và **server dừng công việc hoặc giải phóng tài nguyên sau khi lời gọi bị hủy**. Chỉ kiểm tra client nhận DEADLINE_EXCEEDED chưa chứng minh server đã ngừng truy vấn, worker hoặc lời gọi downstream.

Trong **Spring gRPC**, có thể kiểm thử hành vi này bằng gRPC Java, JUnit và in-process transport. Một server test cố ý chờ trên latch cho tới khi deadline client hết giúp kiểm soát thời điểm, tránh phụ thuộc vào Thread.sleep. Sau đó test xác minh status phía client, cancellation trong context server và cleanup của tác vụ.

## 1. Kịch bản kiểm thử cần xác minh

Giả sử client gọi method GenerateReport với deadline 150 ms, trong khi server chờ một tín hiệu hoàn tất chưa được phát. Test cần chứng minh:

1. Server đã bắt đầu xử lý request.
2. Client kết thúc lời gọi với DEADLINE_EXCEEDED.
3. Context phía server được đánh dấu cancelled.
4. Listener cancellation được kích hoạt và giải phóng worker đang chờ.
5. Server không gửi response sau khi call đã bị hủy.
6. Tài nguyên được cleanup kể cả khi completion và cancellation xảy ra gần nhau.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant C as gRPC client
    participant S as Slow test server
    T->>C: Gọi GenerateReport, deadline 150 ms
    C->>S: Request
    S-->>T: started latch
    Note over C,S: Server chờ release latch
    C-->>C: DEADLINE_EXCEEDED
    S->>S: Context.isCancelled() = true
    S->>S: Cancellation listener mở release latch
    S-->>T: stopped / cleanup latch
~~~

Không cần khẳng định timeout xảy ra đúng 150 ms trên đồng hồ test. Scheduler, JVM và CI có thể làm thời gian quan sát dao động. Test nên xác minh status và các sự kiện đồng bộ trong một giới hạn chờ rộng hơn deadline cấu hình.

## 2. Vì sao dùng latch thay cho Thread.sleep?

Một server test dùng Thread.sleep(1_000) có thể tạo timeout, nhưng thời gian kiểm thử phụ thuộc scheduler và không cho test biết server đã bắt đầu xử lý hay chưa. Nếu client timeout trước khi handler được chạy, test có thể pass sai mà không kiểm tra cancellation trong server.

Dùng hai latch:

- **started:** server báo handler đã nhận request.
- **releaseWork:** server chờ latch này; cancellation listener sẽ mở latch.

Test chờ started trước khi kiểm tra kết quả client. Khi deadline hết, listener mở releaseWork, giúp handler thoát khỏi điểm chờ và xác nhận context đã cancelled. Cách này tạo thứ tự sự kiện rõ ràng mà không phải đoán thời gian bằng sleep.

## 3. Tạo slow service có thể điều khiển

Ví dụ service dưới đây giả định Protobuf đã sinh ReportServiceGrpc, ReportRequest và ReportResponse:

~~~java
import io.grpc.Context;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SlowReportService
        extends ReportServiceGrpc.ReportServiceImplBase {

    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch releaseWork = new CountDownLatch(1);
    final CountDownLatch cancelled = new CountDownLatch(1);
    final CountDownLatch stopped = new CountDownLatch(1);
    final AtomicBoolean responseSent = new AtomicBoolean(false);

    @Override
    public void generate(
            ReportRequest request,
            StreamObserver<ReportResponse> responseObserver) {

        Context rpcContext = Context.current();
        rpcContext.addListener(ignored -> {
            cancelled.countDown();
            releaseWork.countDown();
        }, Runnable::run);

        started.countDown();

        try {
            releaseWork.await();

            if (rpcContext.isCancelled()) {
                return;
            }

            responseObserver.onNext(
                ReportResponse.newBuilder()
                    .setReportId(request.getReportId())
                    .build());
            responseObserver.onCompleted();
            responseSent.set(true);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            stopped.countDown();
        }
    }
}
~~~

Handler giữ RPC ở trạng thái chờ cho đến khi test hoặc cancellation listener mở latch. Trong tình huống deadline hết, listener mở latch, handler kiểm tra context và kết thúc mà không phát response. Trường responseSent cho phép test xác minh server không gửi kết quả sau cancellation.

Đây là fixture dành cho test, không phải mẫu xử lý request production. Trong production, công việc cần được nối với API cancel của database, HTTP client, Future hoặc producer thực tế.

## 4. Kiểm thử bằng in-process server và blocking stub

gRPC Java cung cấp InProcessServerBuilder và InProcessChannelBuilder để test service mà không cần mở cổng TCP. Cần có dependency test tương thích phiên bản gRPC Java đang dùng, thường là grpc-inprocess, cùng JUnit 5.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.Server;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class ReportDeadlineTest {

    @Test
    void slowServerIsCancelledWhenClientDeadlineExpires()
            throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        SlowReportService service = new SlowReportService();

        Server server = InProcessServerBuilder.forName(serverName)
            .addService(service)
            .build()
            .start();

        ManagedChannel channel = InProcessChannelBuilder
            .forName(serverName)
            .build();

        ExecutorService caller = Executors.newSingleThreadExecutor();

        try {
            var stub = ReportServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

            ReportRequest request = ReportRequest.newBuilder()
                .setReportId("report-17")
                .build();

            Future<ReportResponse> result =
                caller.submit(() -> stub.generate(request));

            assertTrue(
                service.started.await(2, TimeUnit.SECONDS),
                "server handler did not start");

            ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> result.get(2, TimeUnit.SECONDS));

            assertEquals(
                Status.Code.DEADLINE_EXCEEDED,
                Status.fromThrowable(failure.getCause()).getCode());

            assertTrue(
                service.cancelled.await(2, TimeUnit.SECONDS),
                "server context was not cancelled");
            assertTrue(
                service.stopped.await(2, TimeUnit.SECONDS),
                "server handler did not stop");
            assertFalse(service.responseSent.get());
        } finally {
            service.releaseWork.countDown();
            caller.shutdownNow();
            channel.shutdownNow();
            server.shutdownNow();
            caller.awaitTermination(2, TimeUnit.SECONDS);
            channel.awaitTermination(2, TimeUnit.SECONDS);
            server.awaitTermination(2, TimeUnit.SECONDS);
        }
    }
}
~~~

Blocking stub được chạy trên executor riêng để test thread có thể chờ latch started trong khi RPC đang chờ response. Khi deadline hết, Future.get ném ExecutionException; test lấy status từ cause gRPC để xác minh DEADLINE_EXCEEDED.

Không dùng directExecutor() cho fixture đang chờ latch trên handler nếu điều đó khiến call bị thực thi đồng bộ trên thread test. Handler cần chạy độc lập để timer deadline và test có thể tiếp tục tiến triển.

## 5. Kiểm thử async stub

Với async stub, status được chuyển tới callback onError. Cách này phù hợp khi ứng dụng production vốn dùng callback:

~~~java
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<Status> failureStatus = new AtomicReference<>();
AtomicBoolean responseReceived = new AtomicBoolean(false);

ReportServiceGrpc.newStub(channel)
    .withDeadlineAfter(150, TimeUnit.MILLISECONDS)
    .generate(request, new StreamObserver<ReportResponse>() {
        @Override
        public void onNext(ReportResponse response) {
            responseReceived.set(true);
        }

        @Override
        public void onError(Throwable error) {
            failureStatus.set(Status.fromThrowable(error));
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    });

assertTrue(completed.await(2, TimeUnit.SECONDS));
assertNotNull(failureStatus.get());
assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    failureStatus.get().getCode());
assertFalse(responseReceived.get());
~~~

Ví dụ cần import AtomicReference và AtomicBoolean. Nó tập trung vào callback client; trong test hoàn chỉnh, vẫn cần giữ tham chiếu tới service fixture để xác minh cancelled, stopped và cleanup phía server. Đừng chỉ đếm callback hoàn tất vì onCompleted và onError đều kết thúc một RPC nhưng có ý nghĩa khác nhau.

## 6. Phân biệt deadline timeout với server tự trả lỗi

Một server có thể chủ động trả DEADLINE_EXCEEDED bằng status, nhưng điều đó không giống việc deadline client hết. Test cần xác định nguồn tạo status:

| Tình huống | Kết quả client | Điều cần kiểm tra |
| --- | --- | --- |
| Client deadline hết trước response | Thường là DEADLINE_EXCEEDED | Context server bị cancelled và worker dừng |
| Server chủ động trả status DEADLINE_EXCEEDED | DEADLINE_EXCEEDED | Server có thể chưa bị client cancel trước khi trả lỗi |
| Client chủ động cancel | Thường là CANCELLED | Server nhận cancellation và cleanup |
| Server xử lý lỗi nghiệp vụ | Status phù hợp như FAILED_PRECONDITION | Không nhầm lỗi nghiệp vụ với timeout |

Vì vậy, chỉ assert status cuối ở client là chưa đủ để chứng minh deadline propagation. Cần xác minh thời gian còn lại/context và tín hiệu cancellation ở server.

## 7. Kiểm thử server thực sự dừng công việc

Fixture latch chứng minh handler có phản ứng với context cancellation. Với code thật, cần kiểm thử adapter của từng tài nguyên:

- **Executor/Future:** listener gọi cancel(true) và task kết thúc trong giới hạn cho phép.
- **JDBC:** query timeout hoặc Statement.cancel() làm truy vấn dừng theo khả năng driver.
- **HTTP client:** request handle nhận cancel và không tiếp tục giữ connection.
- **Downstream gRPC:** call con nhận deadline/cancellation từ context cha.
- **Streaming producer:** subscription đóng, queue được giải phóng và không còn onNext.

Không kết luận database đã dừng chỉ vì server handler đã trả về. Một driver có thể tiếp tục query ở server database dù thread client đã bị interrupt; cần quan sát hoặc test riêng hành vi của driver.

## 8. Kiểm thử deadline propagation qua nhiều tầng

Nếu topology có gateway hoặc proxy, in-process test không xác minh được hành vi của hạ tầng đó. Hãy bổ sung integration test qua đường đi thực tế:

1. Client đặt deadline ngắn và gửi request qua proxy.
2. Proxy chuyển timeout còn lại tới Spring gRPC server.
3. Server ghi nhận deadline còn lại khi request tới handler.
4. Server gọi downstream và giữ ngân sách không vượt deadline cha.
5. Khi client hết hạn, xác minh proxy hủy upstream và server nhận cancellation.
6. Đối chiếu trace ID, timestamp và số lần backend thực thi.

Test qua proxy cần dùng cấu hình HTTP/2/gRPC thực tế. Một HTTP endpoint giả lập hoặc test TCP thường không thể xác minh đầy đủ gRPC trailers, grpc-timeout và cancellation của stream.

## 9. Tránh test timeout không ổn định

Các lỗi thường làm test flaky:

- Dùng Thread.sleep để giả lập server chậm.
- Đặt deadline quá sát thời gian khởi động JVM hoặc tạo channel.
- Không chờ xác nhận server đã bắt đầu xử lý trước khi assert timeout.
- Dùng executor trực tiếp khiến handler chặn thread test.
- Không đóng channel, server hoặc executor trong finally.
- Chỉ kiểm tra status client mà bỏ qua cancellation/cleanup server.

Nên dùng latch để điều khiển trạng thái server, deadline đủ ngắn để test nhanh nhưng có khoảng chờ xác minh rộng hơn, và luôn cleanup trong finally. Không assert chính xác thời gian timeout bằng mili giây; assert trạng thái và thứ tự sự kiện.

## 10. Quan sát timeout trong production

Theo dõi theo full method name và trace ID:

- Số RPC kết thúc bằng DEADLINE_EXCEEDED.
- Latency server so với deadline client cấp.
- Thời gian từ cancellation tới lúc worker dừng.
- Số task/query/downstream call còn chạy sau khi client timeout.
- Số response hoặc message bị cố gửi sau cancellation.
- Thời gian cleanup và số lỗi khi giải phóng tài nguyên.

Nếu client thường timeout nhưng server vẫn chạy lâu, cancellation chưa được nối tới tài nguyên thực tế. Nếu server kết thúc nhanh nhưng client vẫn timeout, kiểm tra network, proxy, queue hoặc response/trailers trên đường về.

## 11. Ghi nhớ và tự kiểm tra

Kiểm thử server chậm và client timeout cần xác minh đồng thời **status ở client** và **cancellation/cleanup ở server**. Dùng in-process transport cùng latch để tạo tình huống xác định; không dựa vào sleep hoặc thời điểm timeout chính xác. Sau đó bổ sung integration test cho database, downstream, proxy và streaming để chứng minh tài nguyên thực sự được giải phóng.

Tự kiểm tra:

1. Vì sao test cần chờ latch started trước khi xác minh client timeout?
2. DEADLINE_EXCEEDED ở client chứng minh điều gì và không chứng minh điều gì?
3. Vì sao server cần kiểm tra Context.isCancelled() hoặc listener sau khi client hết deadline?
4. Khi nào in-process test chưa đủ để xác minh timeout qua proxy?
5. Cần kiểm tra thêm điều gì để chứng minh JDBC query hoặc downstream call thực sự dừng?

Một bài test timeout đáng tin cậy phải chỉ ra được toàn bộ vòng đời: client hết ngân sách, gRPC hủy call, server nhận cancellation, công việc dừng ở điểm an toàn và tài nguyên được giải phóng.
