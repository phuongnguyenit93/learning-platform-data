# Hủy stream giữa chừng

## 1. Vì sao cần hủy một server streaming RPC?

Trong module **SPRING_GRPC**, người học xây dựng dịch vụ gRPC trên hệ sinh thái Spring: định nghĩa hợp đồng **Protocol Buffers**, sinh mã Java, triển khai unary và streaming RPC, quản lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Ở chương **Server streaming**, client gửi **một request** và server lần lượt trả **nhiều response** trong một RPC. Luồng này có thể còn hoạt động khi client không cần nhận thêm dữ liệu.

Hãy hình dung một màn hình theo dõi tiến độ tạo báo cáo. Người dùng mở màn hình để xem các cập nhật 10%, 20%, 30%... rồi chuyển sang trang khác khi báo cáo mới đạt 40%. Nếu client bỏ mặc RPC đang mở, server có thể tiếp tục giữ subscription, bộ đệm và tác vụ phát dữ liệu dù không ai cần phần cập nhật còn lại.

**Hủy stream giữa chừng (cancellation)** là yêu cầu kết thúc một RPC đang hoạt động trước khi server tự hoàn thành. Các tình huống phổ biến:

- Người dùng đóng màn hình, hủy thao tác theo dõi hoặc đổi bộ lọc.
- Một tác vụ cha bị hủy nên những lời gọi gRPC phụ thuộc cũng không còn cần thiết.
- Client phát hiện dữ liệu đã đủ cho quyết định hiện tại.
- Client xử lý một response thất bại và không thể tiếp tục an toàn.
- Client đặt deadline; khi vượt thời hạn, runtime chấm dứt RPC và phía server phải dừng công việc liên quan.

**Phân biệt quan trọng:** hủy **RPC theo dõi** không nhất thiết đồng nghĩa hủy **công việc nghiệp vụ nền**. Ví dụ người dùng thôi xem tiến độ nhưng tác vụ xuất báo cáo vẫn cần chạy đến khi xong. Quyết định có hủy cả job hay không phải được thiết kế riêng trong hợp đồng nghiệp vụ.

## 2. Vòng đời RPC: hoàn thành, lỗi, hủy và deadline

Server streaming dùng các callback của `StreamObserver<ResponseT>` để gửi response:

- `onNext(response)`: gửi một message; có thể gọi nhiều lần khi RPC còn hoạt động.
- `onCompleted()`: kết thúc stream thành công; server không gửi thêm response.
- `onError(error)`: kết thúc do lỗi; không gửi thêm message hoặc tín hiệu kết thúc khác.

Hủy do client khởi tạo là **một đường kết thúc khác**. Server thường nhận tín hiệu cancellation từ gRPC runtime qua `ServerCallStreamObserver` hoặc `Context`, rồi giải phóng tài nguyên. Server **không cần và không nên cố** gọi `onCompleted()` chỉ để phản hồi cho một client đã hủy.

~~~mermaid
stateDiagram-v2
    [*] --> Active: Client mở WatchProgress
    Active --> Active: Server onNext(response)
    Active --> Success: Server onCompleted()
    Active --> Error: Server onError(status)
    Active --> Cancelled: Client chủ động cancel
    Active --> Deadline: Hết deadline
    Active --> Disconnected: Kết nối bị lỗi
    Success --> [*]
    Error --> [*]
    Cancelled --> [*]
    Deadline --> [*]
    Disconnected --> [*]
~~~

| Nguyên nhân | Phía client thường quan sát | Phía server cần làm |
|---|---|---|
| Server gửi đủ response và đóng bình thường | `onCompleted()` / status `OK` | Kết thúc việc phát, giải phóng tài nguyên |
| Server không xử lý được request | `onError(...)`, ví dụ `INVALID_ARGUMENT` | Trả status phù hợp, dọn tài nguyên |
| Client chủ động hủy khi RPC còn mở | Thường `onError` với `CANCELLED` | Ngừng gửi, bỏ subscription, hủy timer/buffer |
| Deadline của client hết | Thường `DEADLINE_EXCEEDED` tại client | Nhận tín hiệu RPC bị hủy và dừng công việc liên quan |
| Mất kết nối/transport bị lỗi | Có thể `UNAVAILABLE` hoặc mã tương ứng | Dọn tài nguyên khi runtime thông báo đóng/hủy |

Các mã trạng thái thực tế phụ thuộc phía quan sát, nguyên nhân và thời điểm sự kiện. Ví dụ client có thể chủ động hủy gần đúng lúc server hoàn thành; kết quả cuối cùng có thể là thành công hoặc cancellation tùy sự kiện nào thắng cuộc đua. Đừng viết logic yêu cầu cả hai phía luôn báo cùng một mã.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant G as Spring gRPC server
    participant P as Producer
    C->>G: WatchProgress(job_id)
    G->>P: Subscribe
    P-->>G: Progress 10%
    G-->>C: onNext(10%)
    P-->>G: Progress 40%
    G-->>C: onNext(40%)
    C-xG: cancel("User closed view")
    G->>P: Unsubscribe / stop timer
    Note over G: Không phát tiếp cho RPC đã hủy
    Note over P: Job nền có thể tiếp tục chạy
~~~

## 3. Định nghĩa Protocol Buffers cho bài thực hành

Giả sử dịch vụ Spring gRPC phát tiến độ theo mã công việc. File `src/main/proto/job_progress.proto`:

~~~proto
syntax = "proto3";

package jobs.v1;

option java_multiple_files = true;
option java_package = "com.example.jobs.rpc";
option java_outer_classname = "JobProgressProto";

service JobProgressService {
  rpc WatchProgress(WatchProgressRequest) returns (stream ProgressEvent);
}

message WatchProgressRequest {
  string job_id = 1;
  int32 max_updates = 2;
}

message ProgressEvent {
  string job_id = 1;
  int64 sequence = 2;
  int32 percent = 3;
  string description = 4;
}
~~~

`returns (stream ProgressEvent)` khai báo **một request, nhiều response**. Trong build Java, `protoc` và `protoc-gen-grpc-java` sinh các class message, `JobProgressServiceGrpc.JobProgressServiceImplBase` và các stub client. Cấu hình plugin protobuf, gRPC Java và starter Spring phải tương thích với phiên bản dự án.

`max_updates` chỉ tạo luồng **hữu hạn** dễ quan sát trong ví dụ; giả định giá trị hợp lệ từ 1 đến 20. Trong hệ thống thực, server thường subscribe vào nguồn dữ liệu theo `job_id` và có thể phát tiến độ đến khi job kết thúc. Tính năng cancellation vẫn cần ngay cả với RPC hữu hạn.

## 4. Client Java hủy stream bằng ClientCallStreamObserver

Với **asynchronous stub**, client gRPC Java có thể dùng `ClientResponseObserver<RequestT, ResponseT>`. Phương thức `beforeStart(...)` nhận `ClientCallStreamObserver<RequestT>` đại diện cho lời gọi hiện tại. Client giữ đối tượng này để có thể gọi:

~~~java
call.cancel("User no longer needs progress updates", null);
~~~

Đây là API **hủy RPC thật** trong runtime gRPC. Nó khác với việc tự gọi `onError(...)` của observer client, đóng cửa sổ giao diện, hoặc chỉ ngừng cập nhật UI. Các thao tác đó không tự đảm bảo RPC phía server bị hủy.

### 4.1. Ví dụ client tự hủy sau message thứ ba

~~~java
package com.example.jobs.client;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class CancelProgressClient {

    public static void main(String[] args) throws InterruptedException {
        // Plaintext chỉ dành cho môi trường phát triển tin cậy.
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .build();

        CountDownLatch terminated = new CountDownLatch(1);

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("job-731")
                    .setMaxUpdates(10)
                    .build();

            JobProgressServiceGrpc.newStub(channel)
                    .withDeadlineAfter(20, TimeUnit.SECONDS)
                    .watchProgress(
                            request,
                            new ClientResponseObserver<WatchProgressRequest,
                                                       ProgressEvent>() {

                                private ClientCallStreamObserver<
                                        WatchProgressRequest> call;
                                private int received;

                                @Override
                                public void beforeStart(
                                        ClientCallStreamObserver<
                                                WatchProgressRequest> stream) {
                                    this.call = stream;
                                }

                                @Override
                                public void onNext(ProgressEvent event) {
                                    received++;
                                    System.out.printf("#%d progress=%d%%%n",
                                            event.getSequence(),
                                            event.getPercent());

                                    if (received == 3) {
                                        // Giải phóng RPC khi không cần theo dõi nữa.
                                        call.cancel("Stopped watching progress", null);
                                    }
                                }

                                @Override
                                public void onError(Throwable error) {
                                    System.out.println(
                                            "RPC ended: " + Status.fromThrowable(error));
                                    terminated.countDown();
                                }

                                @Override
                                public void onCompleted() {
                                    System.out.println("RPC completed normally");
                                    terminated.countDown();
                                }
                            });

            if (!terminated.await(25, TimeUnit.SECONDS)) {
                System.err.println("No terminal callback observed in time");
            }
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

Với server phát một response khoảng mỗi nửa giây, client nhận các message 1, 2, 3 rồi gọi `cancel`. Thông thường callback `onError` của client sẽ thấy status `CANCELLED`, còn `onCompleted` không xuất hiện. Nếu server đã kịp hoàn thành trước khi cancellation được thực hiện, client có thể thấy `onCompleted`; ví dụ có deadline và mười bản cập nhật để giảm khả năng này.

**Giải thích mã:**

1. `beforeStart` được runtime gọi trước khi RPC bắt đầu nhận response; client lưu `ClientCallStreamObserver` cho **đúng RPC này**.
2. `onNext` nhận từng `ProgressEvent` và tăng bộ đếm.
3. Sau message thứ ba, client gọi `call.cancel(...)`. Runtime thực hiện hủy; client không gửi thêm request protobuf.
4. `onError` là nơi quan sát kết thúc do cancellation/lỗi; `onCompleted` là nơi quan sát hoàn thành bình thường. Client nên xử lý đúng **một** kết cục theo callback thực tế.
5. `CountDownLatch` chỉ giúp chương trình console giữ channel còn sống đến khi callback kết thúc. Không dùng `await` để chặn event loop hoặc thread xử lý request trong ứng dụng Spring.

`ClientCallStreamObserver.cancel(message, cause)` nhận thông điệp giải thích và nguyên nhân tùy chọn. Không đặt access token, thông tin người dùng nhạy cảm hoặc dữ liệu nghiệp vụ bí mật vào chuỗi lỗi có thể được ghi log.

### 4.2. Hủy khi người dùng rời màn hình

Trong UI hoặc một service Spring, hủy nên gắn với **vòng đời đối tượng theo dõi**. Ví dụ:

~~~text
Mở trang tiến độ:
    - tạo WatchProgress RPC
    - lưu handle ClientCallStreamObserver của call hiện tại

Đổi trang / bấm Dừng theo dõi:
    - lấy handle của call đang hoạt động
    - gọi cancel("view disposed", null) đúng một lần theo chính sách ứng dụng
    - bỏ reference đến observer, giải phóng subscription của UI

Nhận onError / onCompleted:
    - cập nhật trạng thái cuối của phiên theo dõi
    - không tự khởi chạy lại nếu người dùng đã chủ động hủy
~~~

Không dùng `channel.shutdownNow()` như cách hủy thường xuyên **một** RPC: channel có thể được tái sử dụng bởi nhiều lời gọi khác. `shutdownNow()` dành cho trường hợp ứng dụng thật sự muốn dừng channel và có thể ảnh hưởng đến các RPC đang dùng chung channel.

## 5. Server phát hiện client hủy và dọn tài nguyên

Ở server gRPC Java, `ServerCallStreamObserver<ResponseT>` cung cấp các API quan trọng:

- `isCancelled()`: kiểm tra RPC đã bị hủy hay chưa.
- `setOnCancelHandler(Runnable)`: đăng ký callback để thực hiện cleanup khi cancellation được báo.
- `isReady()` và `setOnReadyHandler(...)`: tín hiệu hỗ trợ flow control khi client nhận chậm; **khác** cancellation.

Với server streaming, một nguồn sự kiện có thể nằm trên thread khác so với thread RPC. Vì vậy không nên giữ một thread đang ngủ/chờ cả buổi để phát một message mỗi vài giây. Thay vào đó hãy dùng publisher hoặc scheduler có vòng đời rõ ràng, và bỏ subscription/tác vụ dành riêng cho call khi client hủy.

### 5.1. Ví dụ server Spring gRPC dùng scheduler

Service dưới đây mô phỏng cập nhật tiến độ mỗi 500 ms. Scheduler được chia sẻ ở cấp service; từng RPC chỉ giữ một tác vụ định kỳ và hủy tác vụ đó khi không còn cần thiết.

~~~java
package com.example.jobs;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class JobProgressServiceImpl
        extends JobProgressServiceGrpc.JobProgressServiceImplBase {

    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(4);

    @Override
    public void watchProgress(
            WatchProgressRequest request,
            StreamObserver<ProgressEvent> responseObserver) {

        String jobId = request.getJobId().trim();
        int maxUpdates = request.getMaxUpdates();

        if (jobId.isEmpty() || maxUpdates < 1 || maxUpdates > 20) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                    .withDescription("job_id required; max_updates must be 1..20")
                    .asRuntimeException());
            return;
        }

        ServerCallStreamObserver<ProgressEvent> out =
                (ServerCallStreamObserver<ProgressEvent>) responseObserver;

        // Gate điều phối giữa callback cancel và scheduler của RPC.
        Object gate = new Object();
        AtomicBoolean closed = new AtomicBoolean(false);
        AtomicInteger sent = new AtomicInteger(0);
        AtomicReference<ScheduledFuture<?>> scheduled = new AtomicReference<>();

        out.setOnCancelHandler(() -> {
            synchronized (gate) {
                closed.set(true);
            }
            stop(scheduled.get());
            // Thực tế: bỏ subscription nguồn sự kiện của riêng RPC này.
        });

        Runnable emit = () -> {
            synchronized (gate) {
                if (closed.get() || out.isCancelled()) {
                    closed.set(true);
                    stop(scheduled.get());
                    return;
                }

                try {
                    int next = sent.incrementAndGet();
                    ProgressEvent event = ProgressEvent.newBuilder()
                            .setJobId(jobId)
                            .setSequence(next)
                            .setPercent(next * 100 / maxUpdates)
                            .setDescription("Demo progress " + next)
                            .build();

                    out.onNext(event);

                    if (next == maxUpdates) {
                        closed.set(true);
                        out.onCompleted();
                        stop(scheduled.get());
                    }
                } catch (RuntimeException failure) {
                    if (!closed.get() && !out.isCancelled()) {
                        closed.set(true);
                        // Không đưa chi tiết nội bộ của exception ra client.
                        try {
                            out.onError(Status.INTERNAL
                                    .withDescription("Cannot produce progress")
                                    .asRuntimeException());
                        } finally {
                            stop(scheduled.get());
                        }
                    } else {
                        closed.set(true);
                        stop(scheduled.get());
                    }
                }
            }
        };

        ScheduledFuture<?> future = scheduler.scheduleWithFixedDelay(
                emit, 0, 500, TimeUnit.MILLISECONDS);
        scheduled.set(future);

        // Tín hiệu cancel/hoàn thành có thể đến trước lúc lưu future.
        if (closed.get()) {
            future.cancel(false);
        }
    }

    private static void stop(ScheduledFuture<?> task) {
        if (task != null) {
            task.cancel(false);
        }
    }

    @PreDestroy
    public void shutdown() {
        scheduler.shutdownNow();
    }
}
~~~

Ở bộ tích hợp Spring gRPC có cơ chế tìm các bean `BindableService`, `@Service` giúp Spring quản lý triển khai server. Nếu dự án dùng starter có cách đăng ký khác, cần áp dụng đúng cơ chế đăng ký của starter. `@PreDestroy` dừng executor khi ứng dụng ngừng hoạt động.

**Điểm cần quan sát trong server:**

1. Callback cancel chỉ đánh dấu `closed`, hủy timer và dọn tài nguyên. Nó không cố phát thêm `onCompleted` hay `onError` cho client đã hủy.
2. `gate` phối hợp sender và callback cancel để việc phát response không chạy đồng thời với xử lý cancellation ở cấp ứng dụng.
3. Mỗi task `scheduleWithFixedDelay` chạy tuần tự đối với chính task đó; ứng dụng lớn vẫn cần giới hạn số RPC mở và chi phí scheduler, producer, subscription.
4. Khi đủ số update, server gọi `onCompleted()` đúng một lần và dừng timer. Khi lỗi nội bộ trước khi kết thúc, server gọi `onError(Status.INTERNAL...)` nếu RPC vẫn còn hoạt động.
5. `isCancelled()` giúp phát hiện trạng thái runtime ngay cả khi callback cleanup chưa kịp chạy.
6. `scheduled` có thể chưa được gán nếu callback đến rất sớm; kiểm tra `closed` sau khi đăng ký future tránh để timer chạy mãi.

Các ví dụ chỉ dùng dữ liệu nhỏ. Trong ứng dụng thật, nguồn tiến độ thường là một event bus hoặc bảng dữ liệu dùng chung, còn việc **hủy subscription theo dõi** cần tách khỏi **hủy công việc tạo báo cáo**. Nếu client đọc chậm, server còn phải dùng flow control (`isReady()`, `setOnReadyHandler(...)`), buffer có giới hạn và chính sách backpressure phù hợp.

### 5.2. Nếu có nhiều nguồn phát cùng lúc

Một callback nhận event từ broker, một tác vụ định kỳ và một handler báo lỗi có thể cùng cố ghi lên `StreamObserver`. `StreamObserver` không mặc nhiên an toàn cho các lời gọi ghi từ nhiều thread.

Thiết kế ổn định thường gồm:

~~~text
Database/Broker event -> bounded queue --+
Timer/status event ----> bounded queue ---+--> single sender --> onNext(...)
                                         |                   --> onCompleted/onError
Client cancellation ----------------------+--> stop sender + unsubscribe + clear queue
~~~

Một **sender tuần tự** chịu trách nhiệm phát các message và một terminal signal; các nguồn khác chỉ nộp event hoặc thay đổi trạng thái. Khi cancel xảy ra, không còn event mới được đưa vào hàng đợi; sender hủy phần việc còn chờ, giải phóng buffer, gỡ listener và đóng tài nguyên liên quan đến call. Các thao tác cleanup nên an toàn khi được gọi nhiều lần vì cancellation và shutdown có thể gần như đồng thời.

## 6. Hủy RPC khác với hủy công việc nghiệp vụ

Giả sử `StartExport` tạo một job xuất báo cáo và trả `job_id`, còn `WatchProgress` trả trạng thái job theo server streaming:

~~~proto
service ExportService {
  rpc StartExport(StartExportRequest) returns (StartExportReply);
  rpc WatchProgress(WatchProgressRequest) returns (stream ProgressEvent);
  rpc CancelExport(CancelExportRequest) returns (CancelExportReply);
}
~~~

Ở sơ đồ này, `StartExportRequest`, `StartExportReply`, `CancelExportRequest` và `CancelExportReply` là các message bổ sung cần khai báo trong proto thực tế. Đoạn trên chỉ minh họa cách chia trách nhiệm API.

| Hành động | Ý nghĩa | Ảnh hưởng đến job |
|---|---|---|
| Client cancel `WatchProgress` | Không cần nhận các event theo dõi nữa | **Không tự động** dừng job |
| Client gọi `CancelExport(job_id)` | Yêu cầu hủy công việc nghiệp vụ | Server quyết định có thể hủy và trả kết quả |
| Stream tự `onCompleted` | Phiên theo dõi đã kết thúc bình thường | Không nhất thiết là job được hủy |
| Stream `onError` do lỗi mạng | Không truyền được kết quả theo dõi | Job có thể vẫn tiếp tục |

Tách biệt hai hành động tránh mất dữ liệu hoặc dừng một batch job quan trọng chỉ vì trình duyệt đóng tab. Ngược lại, với tính toán chỉ tồn tại để phục vụ một request (không cần giữ kết quả), cancellation có thể được **lan truyền có chủ đích** xuống tác vụ xử lý để tiết kiệm CPU và I/O.

### Lan truyền cancellation xuống tác vụ con

Khi server đang gọi thêm các service khác hoặc truy vấn một nguồn có hỗ trợ hủy, hãy bảo đảm tác vụ con có thể quan sát cancellation. gRPC Java cung cấp `io.grpc.Context` để truyền ngữ cảnh RPC qua các lời gọi gRPC, và `Context.current().isCancelled()` giúp code liên quan kiểm tra cancellation khi context được truyền đúng qua các thread.

Tuy nhiên, một worker chạy qua executor không phải lúc nào cũng mang theo context của RPC nếu ứng dụng không bọc tác vụ đúng cách. Có thể dùng `Context.currentContextExecutor(executor)` hoặc các API context propagation tương ứng; cần bảo đảm tác vụ con thực sự mang đúng `Context` và kiểm tra/có listener hủy. Đối với job nghiệp vụ độc lập, đừng gắn job với context của phiên theo dõi.

## 7. Hủy chủ động, deadline và mất kết nối: khác nhau thế nào?

### 7.1. Chủ động cancel

Client quyết định không cần response tiếp theo và gọi `ClientCallStreamObserver.cancel(...)`. Runtime thường trả `CANCELLED` ở phía client, còn server thấy RPC bị hủy khi cơ chế thông báo đến nơi. Cancellation không đảm bảo mọi byte/message đang đệm lập tức biến mất khỏi mạng hoặc callback đã bắt đầu sẽ bị dừng đồng bộ. Do đó, ứng dụng cần xử lý khả năng callback và cancellation xảy ra gần nhau.

### 7.2. Deadline hết

Client dùng:

~~~java
JobProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchProgress(request, observer);
~~~

Deadline giới hạn **tổng thời gian RPC**, không được làm mới sau mỗi `onNext`. Khi deadline hết, runtime hủy RPC; client thường thấy `DEADLINE_EXCEEDED`, server được báo cancellation và cần dừng tác vụ liên quan. Một stream vẫn phát đều đặn vẫn có thể hết deadline sau 10 giây.

### 7.3. Mất kết nối

Đứt mạng, proxy đóng HTTP/2 stream hoặc transport bị lỗi có thể kết thúc RPC với `UNAVAILABLE` hoặc một status khác. Thời điểm server phát hiện có thể trễ hơn lúc client thực tế mất kết nối. Vì vậy cần có giới hạn tài nguyên, deadline/timeout, và dọn dẹp khi runtime biết RPC đã bị chấm dứt.

**Không nên tự động retry một stream vừa bị hủy có chủ ý.** Retry chỉ phù hợp khi người dùng hoặc nghiệp vụ **vẫn muốn tiếp tục** và hợp đồng hỗ trợ cách khôi phục an toàn. Với sự cố mạng, muốn tiếp tục các sự kiện từ một checkpoint phải dùng sequence/cursor cùng nguồn dữ liệu có thể phát lại.

## 8. Những message đã nhận trước khi hủy sẽ ra sao?

Giả sử client đã xử lý ba event rồi hủy:

~~~text
Server định gửi: #1 → #2 → #3 → #4 → #5 → onCompleted()
Client đã nhận:  #1 → #2 → #3
Client gọi:      cancel("User closed view", null)
Kết quả thường:  onError(CANCELLED)
~~~

Client có thể **đã thực hiện side effect** cho các event 1–3, ví dụ cập nhật database hoặc UI. Việc hủy RPC không tự hoàn tác những thao tác đó. Ngược lại, server đã gọi `onNext(#4)` không có nghĩa client chắc chắn nhận hoặc xử lý #4. Khi client hủy, những response còn đệm có thể không tới nơi.

Nếu nghiệp vụ yêu cầu đầy đủ mọi event, nên bổ sung:

1. `sequence` tăng theo phạm vi được định nghĩa (ví dụ theo mỗi `job_id`).
2. Checkpoint lưu **sau khi** xử lý thành công event.
3. API resume với `after_sequence`/cursor và nguồn dữ liệu lưu lịch sử.
4. Cơ chế xử lý trùng (idempotency/deduplication), phát hiện khoảng thiếu và đồng bộ lại.

gRPC **không tự bảo đảm exactly-once processing** của event nghiệp vụ. `onCompleted` của server cũng không đồng nghĩa client đã ghi bền các event; với tính toán nhạy cảm cần một cơ chế xác nhận ở cấp ứng dụng.

## 9. Backpressure khi client quyết định dừng

Client có thể chọn **không muốn nhận nữa** hoặc **chỉ tạm thời không xử lý kịp**; hai tình huống phải xử lý khác nhau:

- **Không muốn nhận nữa:** gọi cancel. Server ngừng phát và giải phóng tài nguyên.
- **Muốn nhận nhưng quá chậm:** điều chỉnh nhu cầu nhận với `ClientResponseObserver`/`ClientCallStreamObserver.request(n)`, xử lý message xong mới cấp thêm nhu cầu; server cũng phải kiểm soát tốc độ tạo dữ liệu và buffer.

Client manual flow control ví dụ:

~~~java
// Trong ClientResponseObserver.beforeStart(...)
stream.disableAutoRequestWithInitial(1);

// Sau khi onNext(event) xử lý thành công:
control.request(1);

// Khi người dùng thật sự dừng xem:
control.cancel("Viewer stopped", null);
~~~

`request(1)` là điều khiển **số response được giao tới observer phía client**, không phải thêm một request protobuf lên server; nó không phải ACK client đã lưu dữ liệu. Nó cũng không buộc producer bên server chỉ tạo một message. Với stream có throughput cao, cần hàng đợi có giới hạn, `ServerCallStreamObserver.isReady()`, callback `setOnReadyHandler(...)` và cơ chế điều tiết nguồn phù hợp.

Nếu ứng dụng chỉ ngừng gọi `request(n)` mà **không cancel**, RPC có thể vẫn mở và giữ tài nguyên cho đến deadline/hủy khác. Khi không còn cần stream, hãy cancel có chủ đích.

## 10. Kiểm thử cancellation từ client đến server

Có thể kiểm thử bằng **gRPC in-process transport** của gRPC Java mà không phải mở cổng mạng. Để kiểm tra cancellation thật sự lan tới server, tạo một service test gửi **một message và cố ý giữ RPC mở**, rồi client hủy ngay khi nhận message đó.

Ví dụ JUnit 5:

~~~java
import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class CancelProgressStreamTest {

    @Test
    void clientCancellationReachesServer() throws Exception {
        CountDownLatch serverCancelled = new CountDownLatch(1);
        CountDownLatch firstReceived = new CountDownLatch(1);
        CountDownLatch clientTerminal = new CountDownLatch(1);
        AtomicReference<Status.Code> finalStatus = new AtomicReference<>();

        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new JobProgressServiceGrpc.JobProgressServiceImplBase() {
                    @Override
                    public void watchProgress(
                            WatchProgressRequest request,
                            StreamObserver<ProgressEvent> observer) {

                        ServerCallStreamObserver<ProgressEvent> out =
                                (ServerCallStreamObserver<ProgressEvent>) observer;
                        out.setOnCancelHandler(serverCancelled::countDown);
                        out.onNext(ProgressEvent.newBuilder()
                                .setJobId(request.getJobId())
                                .setSequence(1)
                                .setPercent(10)
                                .build());
                        // Giữ stream mở để client có thể hủy giữa chừng.
                    }
                })
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("job-731")
                    .setMaxUpdates(10)
                    .build();

            JobProgressServiceGrpc.newStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .watchProgress(
                            request,
                            new ClientResponseObserver<WatchProgressRequest,
                                                       ProgressEvent>() {
                                private ClientCallStreamObserver<
                                        WatchProgressRequest> call;

                                @Override
                                public void beforeStart(
                                        ClientCallStreamObserver<
                                                WatchProgressRequest> stream) {
                                    call = stream;
                                }

                                @Override
                                public void onNext(ProgressEvent response) {
                                    firstReceived.countDown();
                                    call.cancel("Test requested cancellation", null);
                                }

                                @Override
                                public void onError(Throwable error) {
                                    finalStatus.set(Status.fromThrowable(error).getCode());
                                    clientTerminal.countDown();
                                }

                                @Override
                                public void onCompleted() {
                                    finalStatus.set(Status.Code.OK);
                                    clientTerminal.countDown();
                                }
                            });

            assertTrue(firstReceived.await(2, TimeUnit.SECONDS));
            assertTrue(serverCancelled.await(2, TimeUnit.SECONDS));
            assertTrue(clientTerminal.await(2, TimeUnit.SECONDS));
            assertEquals(Status.Code.CANCELLED, finalStatus.get());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**Tại sao test giữ server stream mở?** Nếu server đã gọi `onCompleted()` trước khi client cancel, client hoàn toàn có thể thấy `OK` và server không còn một phiên đang hoạt động để nhận callback cancel. Bằng cách giữ stream mở có chủ đích, test xác minh đúng sự kiện **client chủ động chấm dứt RPC đang chạy**, đồng thời kiểm tra server được thông báo qua `setOnCancelHandler`.

Đây là kiểm thử giao thức gRPC in-process, chưa kiểm thử Spring bean registration, interceptor, TLS hay proxy thực. Với hệ thống thật, nên bổ sung kiểm thử tích hợp Spring Boot, test ngắt kết nối mạng và kiểm tra subscription/worker được đóng.

### Bộ kiểm thử nên có trong dự án

| Tình huống | Kết quả cần xác minh |
|---|---|
| Client cancel sau event đầu | Client kết thúc theo cancellation; server nhận tín hiệu và dọn tài nguyên |
| Cancel gần thời điểm `onCompleted` | Không có double terminal; xử lý cuộc đua kết thúc hợp lệ |
| Client cancel trước event đầu | Producer không tiếp tục chạy vô ích; không rò rỉ listener |
| Deadline ngắn | Client thường nhận `DEADLINE_EXCEEDED`; server dừng công việc theo dõi |
| Server lỗi sau vài event | Client nhận status lỗi; không coi RPC thành công |
| Nhiều stream cùng mở trên một channel | Hủy một stream không làm hủy các RPC còn lại |
| Nguồn job chạy độc lập | Hủy theo dõi không tự làm job dừng nếu nghiệp vụ không yêu cầu |
| Client đọc chậm | Backpressure có giới hạn; có thể hủy an toàn khi còn buffer |
| Retry/resume sau ngắt mạng | Không xử lý trùng hoặc bỏ sót event nếu hợp đồng yêu cầu lịch sử đầy đủ |

## 11. Metadata, interceptor, TLS và quan sát vận hành

Trong hệ sinh thái Spring gRPC, metadata thường mang thông tin xác thực, correlation ID hoặc dữ liệu điều khiển **ở cấp RPC**. Interceptor có thể xác thực, phân quyền `job_id`, ghi mã kết thúc và đo thời lượng RPC. Khi client chủ động hủy, cần phân biệt status `CANCELLED` với lỗi server và deadline để có cảnh báo vận hành có ý nghĩa.

Đối với stream dài, cần chú ý:

- **TLS/mTLS:** sử dụng kết nối mã hóa và xác minh danh tính server trong production; `usePlaintext()` trong ví dụ chỉ phù hợp dev đáng tin cậy.
- **Phân quyền:** chỉ caller có quyền xem tiến độ công việc mới được đăng ký theo dõi. Biết `job_id` không mặc nhiên được phép đọc.
- **Quyền và token hết hạn:** xác định chính sách đối với stream tồn tại lâu sau khi token truy cập hết hạn hoặc quyền truy cập bị thu hồi.
- **Không tiết lộ dữ liệu nhạy cảm:** log nguyên nhân cancellation an toàn; tránh ghi token, thông tin cá nhân hoặc payload nhạy cảm.

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| RPC đang mở theo phương thức/caller | Sức chứa và tài nguyên cần duy trì |
| Số RPC kết thúc `OK`, `CANCELLED`, `DEADLINE_EXCEEDED`, `UNAVAILABLE` | Phân biệt người dùng dừng, timeout và lỗi mạng |
| Độ trễ từ client cancel đến server cleanup | Phát hiện subscription hoặc tác vụ không được hủy kịp |
| Số timer/producer/listener còn sống sau cancel | Phát hiện rò rỉ tài nguyên |
| Số response gửi trước khi cancel | Hiểu hành vi người dùng và lưu lượng |
| Buffer size, readiness, message/giây | Đánh giá tác động client đọc chậm |
| Tỷ lệ reconnect/replay và event bị trùng | Đánh giá cơ chế tiếp tục của nghiệp vụ |

Đừng gộp mọi `CANCELLED` thành lỗi hệ thống: có những cancellation hoàn toàn bình thường khi người dùng rời màn hình. Tuy nhiên nếu tỷ lệ cancellation tăng bất thường sau khi thay đổi cấu hình proxy hoặc deadline, cần phân tích thêm bằng trace và metrics.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ dừng cập nhật UI, không cancel RPC | Server còn giữ stream, worker và tài nguyên | Gọi API cancel của lời gọi gRPC thực |
| Đóng shared channel để hủy một stream | Ảnh hưởng các RPC khác đang hoạt động | Cancel đúng `ClientCallStreamObserver` của RPC |
| Server gọi `onCompleted` sau khi client cancel | Phát terminal không còn cần thiết, dễ gây race | Dừng producer và cleanup khi nhận cancellation |
| Không gỡ subscription/timer khi cancel | Rò rỉ bộ nhớ, thread và kết nối nguồn dữ liệu | Dùng `setOnCancelHandler` và cleanup idempotent |
| Coi cancellation luôn là lỗi nghiệp vụ | Cảnh báo sai, khó giám sát | Tách cancellation, deadline, transport và lỗi domain |
| Hủy theo dõi đồng thời hủy job nền mà không có hợp đồng | Làm dừng công việc quan trọng ngoài ý muốn | Tách `WatchProgress` và lệnh `CancelJob` |
| Đã cancel nhưng vẫn phát `onNext` từ thread khác | Race, lỗi transport và lãng phí công việc | Điều phối sender, kiểm tra trạng thái, ngừng subscription |
| Không có checkpoint cho dữ liệu bắt buộc đầy đủ | Ngắt stream có thể dẫn đến thiếu/trùng event | Thiết kế sequence, cursor, replay và idempotency |
| Dùng `request(0)` hoặc ngừng `request(n)` như cách cancel | RPC có thể tiếp tục giữ tài nguyên | Khi không còn cần dữ liệu, chủ động cancel |

### Câu hỏi tự kiểm tra

1. Vì sao đóng màn hình theo dõi chưa chắc làm server biết phải ngừng stream?
2. `ClientCallStreamObserver.cancel(...)` khác gì với việc tự gọi `onError(...)` của observer client?
3. Vì sao server không cần `onCompleted()` sau khi nhận thông báo client hủy?
4. Hủy `WatchProgress` có nên dừng job tạo báo cáo không? Quyết định này thuộc tầng nào?
5. Khi `onNext` và cancel xảy ra gần như cùng lúc trên hai thread, cần bảo vệ điều gì?
6. `CANCELLED` và `DEADLINE_EXCEEDED` khác nhau như thế nào theo quan sát của client?
7. Nếu client xử lý được ba event rồi cancel, làm thế nào để tiếp tục từ event thứ tư mà không xử lý trùng?
8. Vì sao test cancellation nên giữ RPC mở cho đến khi client phát lệnh hủy?

**Ghi nhớ:** Hủy server streaming là việc **chấm dứt một RPC đang hoạt động** khi client không còn cần response. Client dùng API cancellation của gRPC, server nhận tín hiệu để dừng sender, bỏ subscription và giải phóng tài nguyên; ứng dụng phải quản lý tranh chấp giữa cancel, phát event và kết thúc luồng. Hãy phân biệt cancellation với deadline, lỗi transport và lệnh hủy nghiệp vụ, đồng thời kiểm soát backpressure, status, metadata, TLS, kiểm thử và giám sát.
