# Deadline của server stream

## 1. Deadline giới hạn thời gian nào?

Trong module **SPRING_GRPC**, chúng ta phát triển dịch vụ gRPC bằng hợp đồng Protocol Buffers, sinh mã Java và tích hợp client/server với Spring. Khi học **Server streaming**, client gửi một request rồi nhận nhiều response theo thời gian. Luồng có thể trả một danh sách dài, cập nhật tiến độ hoặc theo dõi sự kiện liên tục. Một RPC như vậy có nguy cơ giữ kết nối, bộ đệm và tác vụ server quá lâu nếu không có giới hạn thời gian.

**Deadline** là thời điểm muộn nhất mà một RPC được phép tiếp tục trước khi bị coi là quá hạn. Trong gRPC Java, client thường đặt deadline bằng `withDeadlineAfter(...)` trước khi gọi RPC. Thời hạn này áp dụng cho **toàn bộ lời gọi**, từ khi RPC bắt đầu cho đến khi kết thúc, **không được đặt lại sau mỗi response**.

Ví dụ client mở stream theo dõi tiến độ với deadline 5 giây:

~~~text
Thời điểm:    0s       1s       2s       3s       4s       5s
              |--------|--------|--------|--------|--------|
Client:       WatchProgress(request)
Server:                #1       #2                #3
                                                   |
Deadline:                                              X
Client:       onNext   onNext   onNext       ...    onError(DEADLINE_EXCEEDED)
~~~

Đây là sơ đồ minh họa: thời điểm message tùy hệ thống. Dù server đã gửi vài message và vẫn còn khả năng gửi tiếp, khi deadline của RPC hết thì client thường nhận status `DEADLINE_EXCEEDED`; server cần ngừng những công việc dành riêng cho phiên theo dõi.

**Mấu chốt:** deadline không phải khoảng thời gian tối đa *giữa hai message*. Nếu đặt deadline 5 giây, việc cứ 1 giây nhận một response cũng không làm đồng hồ quay lại 5 giây.

Sau bài này, người học cần có thể:

- Đặt deadline cho blocking và asynchronous stub của gRPC Java.
- Phân biệt deadline, timeout khi chờ một message, cancellation và giới hạn thời gian do nghiệp vụ quy định.
- Hiểu cách gRPC truyền ngân sách thời gian đến server và các lời gọi phụ thuộc.
- Xử lý stream hết hạn ở client và dừng producer trên Spring gRPC server.
- Thiết kế retry/reconnect, kiểm thử và đo lường khi RPC dài có thể trả dữ liệu một phần.

## 2. Deadline, timeout, idle timeout và cancellation khác nhau

| Khái niệm | Phạm vi | Ví dụ | Hành vi khi xảy ra |
|---|---|---|---|
| **Deadline của RPC** | Toàn bộ một RPC, tính từ lúc bắt đầu cho đến khi có kết cục | `withDeadlineAfter(5, SECONDS)` | Runtime hủy RPC quá hạn; client thường thấy `DEADLINE_EXCEEDED` |
| **Timeout chờ một message** | Khoảng chờ cho message tiếp theo | Ứng dụng yêu cầu phải có event ít nhất mỗi 10 giây | Phải tự thiết kế timer/giám sát; không đồng nghĩa deadline gRPC |
| **Idle timeout của kết nối/proxy** | Kết nối hoặc luồng không có hoạt động theo chính sách hạ tầng | Load balancer đóng kết nối quá lâu không có lưu lượng | Có thể tạo lỗi transport như `UNAVAILABLE` hoặc dẫn đến hủy |
| **Cancellation chủ động** | Client quyết định ngừng một RPC đang mở | Người dùng đóng màn hình theo dõi | Client gọi API cancel; server dọn tài nguyên |
| **Giới hạn thời gian nghiệp vụ** | Tác vụ hoặc phiên xử lý độc lập với kết nối | Job phải hoàn tất trong 30 phút | Nghiệp vụ quyết định fail, retry, ghi trạng thái hoặc tiếp tục |

Một tác vụ xuất báo cáo có thể chạy 15 phút, trong khi mỗi phiên `WatchProgress` chỉ tồn tại 30 giây rồi kết nối lại. Như vậy, **tuổi thọ job** và **tuổi thọ RPC quan sát job** là hai khái niệm độc lập. Deadline của `WatchProgress` không tự động hủy job nền nếu hệ thống không gắn hành vi đó vào nghiệp vụ.

Ví dụ người dùng ngừng xem tiến độ ở giây thứ ba trong một RPC có deadline 10 giây: client nên **cancel ngay** thay vì chờ đến giây thứ mười. Ngược lại, client muốn duy trì theo dõi qua nhiều phút phải có chính sách kết nối lại, deadline phù hợp và nguồn sự kiện có thể khôi phục.

## 3. Hợp đồng Protocol Buffers minh họa

Ta dùng một phương thức server streaming theo dõi tiến độ:

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
  int32 max_updates = 2; // Chỉ dùng giới hạn nhỏ cho ví dụ hữu hạn.
}

message ProgressEvent {
  string job_id = 1;
  int64 sequence = 2;
  int32 percent = 3;
  string detail = 4;
}
~~~

`returns (stream ProgressEvent)` nghĩa là client gửi một `WatchProgressRequest`, còn server có thể gọi `onNext` nhiều lần. Sau khi chạy `protoc` và plugin `protoc-gen-grpc-java`, dự án có các lớp Java như `WatchProgressRequest`, `ProgressEvent` và `JobProgressServiceGrpc`.

**Deadline không phải một field bắt buộc trong protobuf.** Client gRPC truyền thông tin thời gian qua cơ chế deadline/timeout ở cấp RPC. Không nên tự thêm `deadline_ms` vào message chỉ để thay thế deadline chuẩn, trừ khi hợp đồng nghiệp vụ thực sự cần một tham số thời gian độc lập.

Trường `sequence` giúp client nhận biết phần tiến độ đã xử lý và phát hiện trùng/sót khi kết nối lại. Tuy nhiên, bản thân gRPC không lưu lịch sử hay phát lại response bị mất. Muốn resume cần thiết kế API cursor và nguồn dữ liệu lưu bền.

## 4. Client Java đặt deadline cho blocking stub

Blocking stub server streaming trả về `Iterator<ProgressEvent>`. Client có thể đọc từng message bằng `hasNext()` và `next()`; những thao tác này có thể chặn thread trong khi đợi dữ liệu tiếp theo. Deadline áp dụng cả khi đang chờ ở iterator.

~~~java
package com.example.jobs.client;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public final class BlockingDeadlineClient {

    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext() // Chỉ dùng trong môi trường dev đáng tin cậy.
                .build();

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("report-42")
                    .setMaxUpdates(20)
                    .build();

            // Tạo stub có deadline ngay trước khi gọi RPC này.
            var stub = JobProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(3, TimeUnit.SECONDS);

            Iterator<ProgressEvent> updates = stub.watchProgress(request);

            while (updates.hasNext()) {
                ProgressEvent update = updates.next();
                System.out.printf("event=%d, progress=%d%%%n",
                        update.getSequence(), update.getPercent());
            }

            System.out.println("RPC completed successfully");
        } catch (StatusRuntimeException error) {
            Status status = error.getStatus();
            if (status.getCode() == Status.Code.DEADLINE_EXCEEDED) {
                System.err.println("WatchProgress exceeded its deadline");
            } else {
                System.err.println("WatchProgress failed: " + status);
            }
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

Ở ví dụ này, server có thể gửi một số message rồi client gặp `DEADLINE_EXCEEDED`. Client chỉ in `RPC completed successfully` nếu iterator kết thúc bình thường. **Nhận được vài response không có nghĩa toàn bộ RPC đã thành công**.

`withDeadlineAfter(3, TimeUnit.SECONDS)` trả về **một stub mới** với thời hạn tương đối được chuyển thành deadline khi cấu hình. Đừng tạo một stub có deadline ngắn từ rất sớm rồi tái sử dụng nó cho nhiều RPC trong thời gian dài: các lời gọi về sau có thể bắt đầu với deadline đã hết. Thông thường hãy tạo stub có deadline ngay trước từng lời gọi và tái sử dụng `ManagedChannel`.

Cổng `9090` chỉ là ví dụ; dùng đúng cổng Spring gRPC server trong dự án. `usePlaintext()` không thích hợp cho môi trường production phải bảo vệ bằng TLS.

## 5. Async client: xử lý dữ liệu trước deadline và kết cục khi hết hạn

Với asynchronous stub, `watchProgress(...)` trả quyền điều khiển ngay và client nhận dữ liệu qua `StreamObserver<ProgressEvent>`:

~~~java
import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

// channel là ManagedChannel đã được tạo và được quản lý bên ngoài.
WatchProgressRequest request = WatchProgressRequest.newBuilder()
        .setJobId("report-42")
        .setMaxUpdates(20)
        .build();

CompletableFuture<Void> done = new CompletableFuture<>();

JobProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS)
        .watchProgress(request, new StreamObserver<ProgressEvent>() {
            @Override
            public void onNext(ProgressEvent event) {
                System.out.println("Progress " + event.getPercent() + "%");
            }

            @Override
            public void onError(Throwable error) {
                System.err.println("Terminal status: "
                        + Status.fromThrowable(error));
                done.completeExceptionally(error);
            }

            @Override
            public void onCompleted() {
                done.complete(null);
            }
        });

// Chỉ dùng chờ đồng bộ để minh họa trong console hoặc test.
// Không block event-loop/request thread của ứng dụng web.
try {
    done.get(5, TimeUnit.SECONDS);
} catch (java.util.concurrent.ExecutionException error) {
    System.err.println("RPC did not complete successfully");
} catch (java.util.concurrent.TimeoutException error) {
    System.err.println("Local wait timed out");
}
~~~

Ở đây có **hai bộ đếm thời gian khác nhau**:

- `withDeadlineAfter(3, SECONDS)` là deadline của **gRPC RPC**. Khi quá hạn, runtime thường gọi `onError` với `DEADLINE_EXCEEDED`.
- `done.get(5, SECONDS)` là **giới hạn chờ của đoạn mã Java**. Nếu nó hết hạn, chỉ lời gọi `get` ném `TimeoutException`; điều này **không tự động hủy RPC**. Muốn ngừng RPC phải gọi API cancel thích hợp.

Trong hệ thống async có thể dùng `ClientResponseObserver`, lưu `ClientCallStreamObserver` từ `beforeStart` và gọi `cancel(...)` khi người dùng không cần dữ liệu hoặc khi logic xử lý client thất bại. Không tự gọi `onError` trên observer client như một lệnh hủy.

### Deadline không phải phép đo “bao lâu từ message cuối”

Giả sử client đặt deadline 60 giây để theo dõi sự kiện. Server gửi đều một message mỗi 2 giây. Tại giây thứ 60, RPC vẫn có thể hết hạn dù message cuối vừa đến tại giây thứ 58.

Nếu yêu cầu là **“không có sự kiện mới trong 15 giây thì cảnh báo hoặc kết nối lại”**, hãy bổ sung cơ chế **idle-message timer** ở ứng dụng. Timer này được đặt lại khi nhận event hợp lệ, khác với deadline gRPC vốn giới hạn tuổi thọ tổng thể của RPC.

## 6. Deadline đi từ client đến server thế nào?

gRPC hỗ trợ truyền ngân sách thời gian ở cấp RPC. Khi client đặt deadline, runtime có thể truyền thời gian **còn lại** đến server qua metadata điều khiển của gRPC (trong giao thức HTTP/2, có header `grpc-timeout`). Header này do thư viện quản lý; ứng dụng thường **không tự tạo hoặc tự sửa** header dự trữ đó.

Truyền khoảng thời gian còn lại giúp tránh phụ thuộc hoàn toàn vào việc đồng hồ hệ thống của client và server có trùng khớp tuyệt đối hay không. Khi request đi qua mạng, proxy hoặc các lời gọi phụ thuộc, phần ngân sách còn lại có thể giảm.

Ở server Java, có thể kiểm tra deadline của ngữ cảnh RPC:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (deadline == null) {
    System.out.println("No deadline supplied to this RPC");
} else {
    long remainingMs = deadline.timeRemaining(TimeUnit.MILLISECONDS);
    System.out.println("Remaining RPC budget: " + remainingMs + " ms");
}
~~~

`deadline == null` nghĩa là ngữ cảnh hiện tại không có deadline; không nên mặc định mọi client đều đã đặt thời hạn. `remainingMs` có thể bằng 0 hoặc âm khi deadline đã hết. Đừng đọc deadline một lần lúc RPC mở rồi giả định giá trị còn lại không đổi trong suốt stream.

Khi RPC hết deadline, runtime sẽ đánh dấu/cancel ngữ cảnh liên quan. Code server có thể dùng:

~~~java
Context context = Context.current(); // Lấy trong ngữ cảnh xử lý RPC.

if (context.isCancelled()) {
    // Dừng đọc nguồn dữ liệu và giải phóng phần việc của RPC này.
    return;
}
~~~

Nếu công việc được gửi sang một executor khác, `Context.current()` gọi trong worker có thể không còn là context của RPC ban đầu nếu không có propagation. Có thể **capture** context lúc nhận request và kiểm tra đối tượng đã capture, hoặc dùng các API bọc executor/callback của gRPC `Context` để truyền đúng ngữ cảnh.

**Client và server không nhất thiết báo cùng status.** Client hết deadline thường thấy `DEADLINE_EXCEEDED`, còn server thường quan sát **cancellation** của RPC qua context hoặc `ServerCallStreamObserver`. Server không nên chờ nhận một sự kiện `onError(DEADLINE_EXCEEDED)` trên response observer rồi mới cleanup.

## 7. Spring gRPC server phải dừng producer khi RPC hết hạn

Trách nhiệm chính của server là dừng việc phát response, ngừng timer/subscription và thu hồi tài nguyên khi RPC bị hủy bởi deadline hoặc client. Không nên coi deadline chỉ là vấn đề phía client.

Ví dụ service tạo một bản cập nhật giả lập mỗi 250 ms. Task tiếp tục đến khi đã gửi đủ message hoặc RPC bị hủy. Dùng scheduler để không chặn thread xử lý RPC trong khi chờ bản cập nhật.

~~~java
package com.example.jobs;

import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.Context;
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
        int limit = request.getMaxUpdates();

        if (jobId.isEmpty() || limit < 1 || limit > 20) {
            responseObserver.onError(Status.INVALID_ARGUMENT
                    .withDescription("job_id required; max_updates must be 1..20")
                    .asRuntimeException());
            return;
        }

        ServerCallStreamObserver<ProgressEvent> out =
                (ServerCallStreamObserver<ProgressEvent>) responseObserver;
        Context rpcContext = Context.current(); // Capture trước khi rời RPC thread.

        Object gate = new Object();
        AtomicBoolean closed = new AtomicBoolean(false);
        AtomicInteger sent = new AtomicInteger(0);
        AtomicReference<ScheduledFuture<?>> taskRef = new AtomicReference<>();

        out.setOnCancelHandler(() -> {
            synchronized (gate) {
                closed.set(true);
            }
            cancel(taskRef.get());
            // Ứng dụng thật còn phải unsubscribe nguồn tiến độ của RPC này.
        });

        Runnable sendTick = () -> {
            synchronized (gate) {
                if (closed.get() || out.isCancelled()
                        || rpcContext.isCancelled()) {
                    closed.set(true);
                    cancel(taskRef.get());
                    return;
                }

                // Demo tạo dữ liệu ngay lúc gửi nên có thể bỏ qua nhịp.
                // Với event nghiệp vụ thật, phải giữ/replay nếu không được mất.
                if (!out.isReady()) {
                    return;
                }

                try {
                    int step = sent.incrementAndGet();
                    ProgressEvent event = ProgressEvent.newBuilder()
                            .setJobId(jobId)
                            .setSequence(step)
                            .setPercent(step * 100 / limit)
                            .setDetail("Generated step " + step)
                            .build();

                    out.onNext(event);

                    if (step == limit) {
                        closed.set(true);
                        out.onCompleted();
                        cancel(taskRef.get());
                    }
                } catch (RuntimeException failure) {
                    if (!closed.get() && !out.isCancelled()
                            && !rpcContext.isCancelled()) {
                        closed.set(true);
                        try {
                            out.onError(Status.INTERNAL
                                    .withDescription("Cannot send progress")
                                    .asRuntimeException());
                        } finally {
                            cancel(taskRef.get());
                        }
                    } else {
                        closed.set(true);
                        cancel(taskRef.get());
                    }
                }
            }
        };

        ScheduledFuture<?> task = scheduler.scheduleWithFixedDelay(
                sendTick, 0, 250, TimeUnit.MILLISECONDS);
        taskRef.set(task);

        // Cancel có thể đến trước khi future được lưu vào taskRef.
        if (closed.get()) {
            task.cancel(false);
        }
    }

    private static void cancel(ScheduledFuture<?> task) {
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

Trong phiên bản Spring gRPC tự đăng ký các Spring bean triển khai `BindableService`, `@Service` giúp service tham gia gRPC server. Với starter hoặc thư viện tích hợp khác, hãy áp dụng cách đăng ký service của thư viện đó. Việc dùng `StreamObserver` và `Context` là API gRPC Java, độc lập với cơ chế đăng ký bean.

### Vì sao cần cả Context, cancel handler và khóa đồng bộ?

1. **`rpcContext`** được lấy ngay khi xử lý request và được giữ để tác vụ scheduler kiểm tra trạng thái hủy, kể cả khi chạy trên thread khác.
2. **`setOnCancelHandler`** dừng task khi runtime thông báo RPC bị hủy, bao gồm hủy chủ động và thường cả deadline đã hết.
3. **`gate`** phối hợp việc phát event và callback cancellation, tránh để tác vụ đang `onNext` chạy đồng thời với cleanup ở mức ứng dụng.
4. **`closed`** là cờ trạng thái kết thúc giúp tránh phát thêm sau completion/cancel và xử lý trường hợp future chưa được lưu lúc cancel xảy ra.
5. **`@PreDestroy`** dừng scheduler khi Spring context đóng; một service không nên tạo thread không giới hạn cho mỗi subscriber.

Các ví dụ có scheduler, timer hoặc callback từ broker cần thiết kế **idempotent cleanup**: gọi giải phóng nhiều lần vẫn an toàn. Nếu client đã hủy, server không cần cố phát `onCompleted` hoặc `onError` cho RPC đã kết thúc ở phía nhận.

### Vai trò của backpressure

`ServerCallStreamObserver.isReady()` cho biết đường gửi đang sẵn sàng nhận thêm dữ liệu theo runtime; nó không xác nhận client đã áp dụng xong event. Trong ví dụ, event được **tạo mới tại nhịp gửi**, nên bỏ qua một nhịp khi chưa ready không làm mất event từ nguồn bên ngoài.

Với nguồn sự kiện thật, **không tự bỏ event chỉ vì `isReady() == false`**. Cần hàng đợi có giới hạn, tích hợp upstream có backpressure, lưu sự kiện để replay hoặc chính sách lấy trạng thái mới nhất được mô tả trong hợp đồng. Backpressure và deadline giải quyết hai câu hỏi khác nhau: client có theo kịp không, và RPC được phép sống đến lúc nào.

## 8. Deadline khi server gọi tiếp một dịch vụ khác

Giả sử `WatchProgress` trên Spring server cần gọi một downstream RPC để lấy dữ liệu. Nếu upstream còn 800 ms, việc gọi downstream với timeout 10 giây **không giúp upstream có thêm thời gian**. Deadline của lời gọi cha vẫn hết sau khoảng thời gian còn lại, bất kể service con đã xong hay chưa.

Cần có ngân sách thời gian cho toàn chuỗi:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring gRPC service A
    participant B as gRPC service B
    C->>A: WatchProgress (deadline 3s)
    Note over A: Deadline/Context còn ~2.6s khi xử lý
    A->>B: FetchStage (deadline không vượt budget còn lại)
    B-->>A: Stage response
    A-->>C: ProgressEvent
    Note over C,A: Nếu quá 3s tính cho toàn RPC, client có thể nhận DEADLINE_EXCEEDED
~~~

Trong gRPC Java, context và deadline có thể được truyền cho các lời gọi con khi giữ đúng **Context**; stub cũng có thể được tạo với deadline chặt hơn. Đừng giả định context của RPC cha tự đi theo mọi worker/executor bất kỳ. Hãy truyền context đúng cách, kiểm tra deadline đã được áp dụng ở downstream, và đặt một **ngân sách nhỏ dự phòng** cho phần xử lý còn lại.

Ví dụ nguyên tắc:

~~~java
// Thực hiện trong context đúng của RPC cha, trước downstream call.
Deadline incoming = Context.current().getDeadline();
if (incoming != null) {
    long remainMs = incoming.timeRemaining(TimeUnit.MILLISECONDS);
    long reserveMs = 100; // Minh họa phần thời gian dành cho xử lý sau.

    if (remainMs <= reserveMs) {
        // Không khởi tạo downstream call đã gần hết thời gian.
        throw Status.DEADLINE_EXCEEDED
                .withDescription("Insufficient remaining deadline")
                .asRuntimeException();
    }

    var downstreamStub = downstreamBaseStub
            .withDeadlineAfter(remainMs - reserveMs, TimeUnit.MILLISECONDS);
    // Gọi downstream ngay với stub mới, trong context đã được truyền đúng.
}
~~~

Đoạn này là snippet minh họa: `downstreamBaseStub` và hành động gọi tiếp do ứng dụng định nghĩa. Nếu cần xử lý lỗi ngay trong `StreamObserver` của server streaming, hãy chuyển tình huống hết ngân sách thành **một** terminal `onError(Status.DEADLINE_EXCEEDED...)` (nếu RPC còn hoạt động), dừng producer và cleanup. Không để exception rò rỉ qua thread scheduler rồi tiếp tục gửi response.

## 9. Chọn deadline cho stream hữu hạn và stream theo dõi lâu

Không có một deadline chung phù hợp cho mọi server streaming RPC. Hãy bắt đầu từ nhu cầu nghiệp vụ và chỉ số thực tế.

| Loại server streaming | Mục tiêu | Hướng lựa chọn |
|---|---|---|
| Trả dần một tập kết quả nhỏ | Nhận đủ dữ liệu nhanh và có điểm kết thúc | Deadline tổng thể dựa trên latency mục tiêu cùng thời gian dự phòng |
| Truy vấn quét dữ liệu lớn | Trả dần các phần đã xử lý | Deadline đủ cho quét; nếu rất dài, thiết kế cursor/phân trang tiếp tục |
| Theo dõi tiến độ job chạy vài phút | UI luôn có thông tin mới | Phiên theo dõi ngắn vừa phải và reconnect theo checkpoint; job tồn tại độc lập |
| Nhận sự kiện liên tục không có điểm kết thúc | Duy trì subscription khi còn cần | Quy định thời hạn/refresh session, idle timeout, hủy và reconnect; không phụ thuộc một RPC vô hạn |
| Luồng có thể gây chi phí lớn | Kiểm soát số RPC mở và tài nguyên | Deadline hợp lý cùng giới hạn buffer, quota, concurrent streams |

Ví dụ hệ thống có mục tiêu UI phản hồi trong 2 giây, nhưng công việc nền thường mất 20 phút. Một RPC unary `StartJob` trả `job_id` nhanh, sau đó client mở `WatchJob` streaming với deadline mỗi phiên khoảng vài chục giây và tái kết nối theo hợp đồng có thể dễ vận hành hơn giữ một RPC duy nhất suốt 20 phút. Các con số chỉ mang tính thiết kế minh họa, phải đo trên hạ tầng thực.

Nếu **không có deadline**, RPC có thể sống rất lâu khi nguồn không phát event và không có bên nào đóng; tuy nhiên proxy, mạng và các timeout khác vẫn có thể làm nó kết thúc. Vì vậy không đặt deadline không phải cách chắc chắn để bảo đảm stream sống mãi.

### Khi client nhận chậm

Một stream mất 2 giây để server tạo hết message nhưng client cần 12 giây để xử lý tuần tự thì deadline 5 giây vẫn có thể làm RPC kết thúc trước khi ứng dụng hoàn tất. Đối với gRPC Java, việc client dùng manual inbound flow control như `ClientResponseObserver` cùng `request(1)` có thể hạn chế tốc độ giao callback, nhưng **không kéo dài deadline**.

Nếu mọi event phải được giữ, cần nguồn lưu bền và checkpoint. Nếu client không theo kịp liên tục, chọn chiến lược batch, compression, điều tiết producer, giảm kích thước message hoặc chủ động chấm dứt và resume; chỉ tăng deadline không giải quyết bộ nhớ tăng vô hạn.

## 10. Deadline ảnh hưởng gì đến dữ liệu đã nhận?

Giả sử client đã xử lý các event có sequence 1, 2, 3 rồi quá hạn:

~~~text
Server dự kiến: #1 -> #2 -> #3 -> #4 -> #5 -> onCompleted()
Client thấy:   #1 -> #2 -> #3 -> onError(DEADLINE_EXCEEDED)
~~~

Những event 1–3 có thể đã tạo side effect như lưu database. **Deadline không tự rollback** các thao tác client đã làm; đồng thời những event 4–5 có thể chưa đến client dù server đã gọi `onNext`. Client phải phân biệt:

- **Tiến độ đã quan sát:** những event đã đọc.
- **Tiến độ đã xử lý và ghi bền:** những event thật sự được áp dụng thành công.
- **Kết thúc RPC:** nhận `onCompleted`/`OK`, hoặc nhận status lỗi như `DEADLINE_EXCEEDED`.

Nếu nghiệp vụ cần xử lý đủ mọi sự kiện và tránh lặp:

1. Server cấp sequence theo quy tắc ổn định và lưu lịch sử cần thiết.
2. Client chỉ lưu checkpoint **sau khi xử lý thành công** event.
3. API cho phép gửi `after_sequence` khi mở phiên mới; server bảo đảm đọc backlog và theo dõi sự kiện mới không tạo khoảng trống.
4. Client deduplicate/idempotent khi nhận lại event đã xử lý; kiểm tra gap nếu yêu cầu thứ tự liên tục.

Đây là thiết kế **ở tầng ứng dụng**. gRPC không tự bảo đảm xử lý đúng một lần (*exactly once processing*) sau retry/reconnect.

### Retry có luôn phù hợp sau DEADLINE_EXCEEDED?

Không. Với RPC truy vấn read-only và nguồn replay có cursor, retry có kiểm soát thường khả thi. Nhưng nếu request kích hoạt một side effect, deadline tại client **không chứng minh phía server chưa thực hiện side effect đó**. Retry mù có thể tạo việc trùng. Với lệnh ghi cần idempotency key, trạng thái job và cơ chế kiểm tra kết quả trước khi gọi lại.

Khi muốn reconnect để tiếp tục theo dõi, xác định rõ người dùng còn muốn nhận dữ liệu hay không. Nếu họ đã chủ động dừng xem, **không** tự động bắt đầu stream mới chỉ vì thấy `CANCELLED`.

## 11. Kiểm thử deadline bằng gRPC in-process

Để kiểm tra deadline chính xác, nên có test không phụ thuộc vào việc scheduler và mạng gửi được bao nhiêu event trước khi hết hạn. Một cách là tạo server stream **giữ mở và không gửi response**, sau đó đặt deadline ngắn ở client và xác minh gRPC thực sự kết thúc RPC.

Ví dụ JUnit 5 dùng transport in-process của gRPC Java:

~~~java
import com.example.jobs.rpc.JobProgressServiceGrpc;
import com.example.jobs.rpc.ProgressEvent;
import com.example.jobs.rpc.WatchProgressRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class ServerStreamDeadlineTest {

    @Test
    void deadlineEndsOpenServerStreamAndCancelsServerCall()
            throws Exception {
        CountDownLatch serverCancelled = new CountDownLatch(1);
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new JobProgressServiceGrpc
                        .JobProgressServiceImplBase() {
                    @Override
                    public void watchProgress(
                            WatchProgressRequest request,
                            StreamObserver<ProgressEvent> observer) {
                        ServerCallStreamObserver<ProgressEvent> out =
                                (ServerCallStreamObserver<ProgressEvent>) observer;
                        out.setOnCancelHandler(serverCancelled::countDown);
                        // Cố ý không gửi onNext/onCompleted:
                        // RPC chỉ kết thúc do client deadline.
                    }
                })
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            WatchProgressRequest request = WatchProgressRequest.newBuilder()
                    .setJobId("report-42")
                    .setMaxUpdates(1)
                    .build();

            var stub = JobProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.watchProgress(request).hasNext());

            assertEquals(Status.Code.DEADLINE_EXCEEDED,
                    error.getStatus().getCode());
            assertTrue(serverCancelled.await(2, TimeUnit.SECONDS));
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Kiểm thử này xác nhận **client thấy deadline exceeded** và **server nhận sự kiện hủy**. Nó chưa xác minh Spring context, interceptor, TLS, proxy hay việc dọn dẹp một nguồn dữ liệu thật. Khi dùng server bất đồng bộ, cần thêm test kiểm tra timer, cursor, subscription và buffer được giải phóng sau deadline.

Những tình huống kiểm thử nên bổ sung:

| Test case | Kết quả kỳ vọng |
|---|---|
| Deadline dài hơn thời gian phát hữu hạn | Client nhận đủ event và `onCompleted` thành công |
| Deadline ngắn hơn tổng thời gian phát | Client nhận `DEADLINE_EXCEEDED`, có thể có dữ liệu từng phần |
| Stream có message đều trước deadline | Vẫn hết hạn đúng thời hạn tổng thể, không reset theo event |
| Deadline hết trước response đầu | Không nhận event; server cleanup |
| Client cancel trước deadline | Thường thấy `CANCELLED`, không chờ hết deadline |
| Hủy và completion xảy ra gần nhau | Chỉ có một kết cục hợp lệ, cleanup an toàn |
| Producer chậm và client đọc chậm | Quota/buffer ổn định, deadline được tuân thủ |
| Gọi service downstream | Không chạy quá ngân sách upstream còn lại; context propagation đúng |
| Qua proxy/TLS thực | Deadline và mã lỗi được quan sát đúng trong điều kiện mạng tương ứng |
| Retry sau deadline | Có deduplication/checkpoint; không tạo side effect trùng |

Với Spring gRPC, cần thêm kiểm thử tích hợp khởi động Spring Boot để kiểm tra service registration, metadata/interceptor và cấu hình endpoint. Kiểm thử mạng thật giúp phát hiện ảnh hưởng của proxy idle timeout, TLS và ngắt kết nối; in-process không mô phỏng toàn bộ các điều kiện đó.

## 12. Giám sát và bảo mật cho stream có deadline

Deadline là một công cụ bảo vệ độ tin cậy, nhưng cần **observability** để biết đã đặt phù hợp chưa. Trong hệ sinh thái Spring gRPC, interceptor, tracing và metrics có thể ghi lại thời lượng RPC, mã kết thúc, số response và số stream đang mở.

| Chỉ số cần quan sát | Ý nghĩa |
|---|---|
| `DEADLINE_EXCEEDED` theo method/client | Stream thường quá hạn hay một nhóm client đặt deadline quá ngắn |
| `CANCELLED` và `UNAVAILABLE` | Phân biệt hủy chủ động và lỗi truyền thông |
| Thời gian RPC thực tế | Phân bố latency và duration của stream |
| Số response trước khi hết hạn | Đánh giá lượng dữ liệu client thực sự nhận được |
| Ngân sách deadline còn lại khi server nhận request | Phát hiện chờ mạng, proxy hoặc gọi downstream quá lâu |
| Số producer/timer còn sống sau khi call kết thúc | Phát hiện rò rỉ tài nguyên |
| Queue depth, `isReady()`, số stream đồng thời | Phát hiện backpressure hoặc tải vượt năng lực |
| Số lần reconnect, gap/duplicate theo sequence | Kiểm tra độ tin cậy khi dùng phiên có thời hạn |

**Đừng tự suy ra mọi `DEADLINE_EXCEEDED` là server lỗi.** Client có thể chọn deadline quá ngắn, đường truyền có độ trễ cao, client xử lý response chậm hoặc hệ thống đang quá tải. Phải quan sát dữ liệu hai phía và phân tích nguyên nhân trước khi điều chỉnh.

Về bảo mật:

- Sử dụng **TLS** trong production, xác minh chứng chỉ server; có thể dùng mTLS nếu chính sách yêu cầu.
- Dùng metadata/interceptor để xác thực và phân quyền theo `job_id` hoặc chủ đề stream, không dùng deadline như cơ chế phân quyền.
- Giới hạn concurrent streams, kích thước message và quota theo caller để tránh client giữ nhiều RPC lâu.
- Không ghi token hoặc nội dung nhạy cảm vào log deadline/status. Metadata điều khiển của gRPC chỉ nên được thư viện và middleware tương thích xử lý.

## 13. Những hiểu lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Deadline là timeout của từng response.” | Deadline gRPC áp dụng cho **toàn RPC**; message đến không reset đồng hồ. |
| “Server gửi đều nên stream không thể hết deadline.” | Stream vẫn có thể quá hạn đúng thời điểm đã ấn định. |
| “`onNext` thành công nghĩa client đã lưu event.” | Đây không phải ACK xử lý dữ liệu cấp nghiệp vụ. |
| “`CompletableFuture.get(timeout)` tự hủy gRPC.” | Nó chỉ giới hạn chờ ở Java; muốn hủy RPC phải gọi cancel. |
| “Deadline hết thì server gọi `onCompleted` cho sạch.” | Server dừng producer, cleanup; không cố phát thành công cho RPC đã hủy. |
| “Client báo `DEADLINE_EXCEEDED` thì server cũng luôn báo y hệt.” | Phía server thường thấy cancellation của context/RPC. |
| “Thêm `deadline_ms` trong protobuf là đủ.” | Deadline chuẩn của gRPC được thiết lập ở call/stub và transport. |
| “Đặt deadline rất dài sẽ giải quyết client chậm.” | Vẫn phải có backpressure, buffer giới hạn và quota. |
| “Retry sau deadline luôn an toàn.” | Có thể gây lặp side effect nếu không có idempotency/cursor. |
| “Một stub có deadline đặt từ trước dùng mãi được.” | Deadline gắn với thời điểm đã cấu hình; nên đặt gần lúc gọi. |

### Câu hỏi tự luyện

1. Với deadline 5 giây và server phát response mỗi giây, stream có tự kéo dài sau mỗi response không?
2. `withDeadlineAfter(3, SECONDS)` khác gì với `future.get(3, SECONDS)`?
3. Vì sao client thấy `DEADLINE_EXCEEDED` nhưng server có thể chỉ nhận cancellation?
4. Khi server chạy worker trên executor khác, vì sao cần truyền/capture gRPC `Context`?
5. Vì sao deadline của stream theo dõi job không nhất thiết làm job nền kết thúc?
6. Client đã xử lý sequence 1–3 trước khi hết hạn. Cần bổ sung gì để tiếp tục từ 4 an toàn?
7. Nếu proxy đóng stream vì idle timeout trước deadline, lỗi này có nhất thiết là `DEADLINE_EXCEEDED` không?
8. Những phép đo nào giúp phân biệt deadline quá ngắn với server quá tải?

**Ghi nhớ:** Deadline của server streaming là giới hạn thời gian **cho toàn bộ RPC**, được client đặt khi gọi và có thể được server quan sát qua gRPC `Context`. Deadline không reset sau `onNext`, không bảo đảm mọi response đã phát sẽ được nhận, và không thay thế flow control hay cancellation chủ động. Trong Spring gRPC, server cần ngừng producer và cleanup khi stream hết hạn; client cần xử lý dữ liệu từng phần, status, retry có kiểm soát, bảo mật TLS cùng giám sát độ tin cậy.
