# onNext, onError và onCompleted

## 1. Ba callback quyết định vòng đời server streaming

Trong module **SPRING_GRPC**, chúng ta phát triển dịch vụ gRPC bằng hợp đồng Protocol Buffers, sinh mã Java và tích hợp server/client vào hệ sinh thái Spring. Khi làm việc với **server streaming**, một request của client có thể tạo ra nhiều response; lập trình viên phía server điều khiển việc phát các response đó thông qua một đối tượng `StreamObserver<ResponseT>`. Ba phương thức cốt lõi của observer là:

- **`onNext(value)`:** phát **một** message; có thể được gọi không lần nào hoặc nhiều lần.
- **`onCompleted()`:** thông báo server đã phát xong và kết thúc RPC thành công; không mang thêm message.
- **`onError(cause)`:** kết thúc RPC vì lỗi; truyền một `Throwable` thường biểu diễn gRPC `Status` thích hợp.

Ở chương **Server streaming**, phải hiểu cả ba phương thức như một **giao thức vòng đời**, chứ không chỉ như ba hàm riêng lẻ. Một server có thể gọi `onNext` nhiều lần, nhưng khi đã gọi một trong hai callback kết thúc, nó không được tiếp tục phát message hoặc phát thêm một callback kết thúc khác.

Ví dụ server cập nhật tiến độ xử lý báo cáo:

~~~mermaid
sequenceDiagram
    participant C as gRPC Java client
    participant S as Spring gRPC server
    C->>S: WatchProgress(job_id = "job-17")
    S-->>C: onNext(10%)
    S-->>C: onNext(60%)
    S-->>C: onNext(100%)
    S-->>C: onCompleted() / status OK
~~~

Nếu server gặp lỗi sau khi gửi `10%` và `60%`:

~~~mermaid
sequenceDiagram
    participant C as gRPC Java client
    participant S as Spring gRPC server
    C->>S: WatchProgress(job_id = "job-17")
    S-->>C: onNext(10%)
    S-->>C: onNext(60%)
    S--xC: onError(Status.UNAVAILABLE)
    Note over C: Có thể đã nhận một phần dữ liệu; RPC thất bại
~~~

**Lưu ý:** Các tên callback mô tả thao tác ở API Java, không phải những chuỗi ký tự được truyền nguyên văn qua mạng. Runtime gRPC đóng gói message bằng Protocol Buffers trên HTTP/2 và gửi trạng thái kết thúc bằng cơ chế status/trailers của gRPC.

## 2. Quy tắc thứ tự và tính kết thúc

Với một RPC do server phát bình thường, chuỗi callback phía server có dạng:

~~~text
onNext(message1) → onNext(message2) → ... → onNext(messageN) → onCompleted()
                                                    hoặc → onError(cause)
~~~

Cho phép **N = 0**: server có thể kết thúc thành công mà không gửi response nào, hoặc báo lỗi trước response đầu tiên.

| Tình huống | Hợp lệ? | Giải thích |
|---|---|---|
| `onNext(A) → onNext(B) → onCompleted()` | Có | Hai message, một kết thúc thành công |
| `onCompleted()` | Có | Không có message, RPC vẫn thành công |
| `onError(Status.INVALID_ARGUMENT...)` | Có | Tham số sai trước khi gửi dữ liệu |
| `onNext(A) → onError(Status.UNAVAILABLE...)` | Có | Đã phát một phần rồi gặp lỗi |
| `onNext(A) → onCompleted() → onNext(B)` | Không | Không được phát thêm sau khi hoàn thành |
| `onError(...) → onCompleted()` | Không | Không được phát hai tín hiệu kết thúc |
| `onCompleted() → onCompleted()` | Không | Kết thúc phải đúng một lần |

~~~mermaid
stateDiagram-v2
    [*] --> Active: Nhận request
    Active --> Active: onNext(value), 0..N lần
    Active --> Completed: onCompleted()
    Active --> Failed: onError(cause)
    Active --> Cancelled: Client hủy / deadline / transport đóng
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

Trạng thái `Cancelled` trong sơ đồ biểu diễn trường hợp **runtime hoặc client chấm dứt RPC**. Server không nhất thiết phải gọi `onError` của response observer khi client đã hủy; thay vào đó cần dừng công việc và giải phóng tài nguyên của luồng.

Những quy tắc cần ghi nhớ:

1. **`onNext` không phải lời xác nhận đã được client xử lý.** Nó chuyển message cho runtime gRPC để gửi, không bảo đảm message đã được phía nhận tiêu thụ hay ghi bền.
2. **`onCompleted` là kết thúc thành công từ góc nhìn server.** Client chỉ kết luận RPC thành công sau khi **thực sự nhận** tín hiệu kết thúc thành công. Lỗi mạng xảy ra sau lúc server gọi `onCompleted` vẫn có thể khiến client không thấy thành công.
3. **`onError` là terminal signal.** Khi gọi phương thức này, server không được gọi `onCompleted` hoặc `onNext` thêm.
4. **Các lời gọi ghi phải được tuần tự hóa.** `StreamObserver` không mặc nhiên an toàn nếu nhiều thread cùng gọi `onNext`/`onError`/`onCompleted` cho một RPC.
5. **Không có bảo đảm phát lại tự động ở tầng nghiệp vụ.** Nếu client đã nhận ba event rồi gặp lỗi, việc lấy lại hay bỏ qua event trùng cần hợp đồng sequence/checkpoint phù hợp.

## 3. Hợp đồng Protocol Buffers cho ví dụ thực hành

Ta xây dựng phương thức `WatchProgress`: một request yêu cầu tối đa năm bản cập nhật tiến độ, server gửi lần lượt các `ProgressEvent` và kết thúc.

File `src/main/proto/progress.proto`:

~~~proto
syntax = "proto3";

package progress.v1;

option java_multiple_files = true;
option java_package = "com.example.progress.rpc";
option java_outer_classname = "ProgressProto";

service ProgressService {
  rpc WatchProgress(ProgressRequest) returns (stream ProgressEvent);
}

message ProgressRequest {
  string job_id = 1;
  int32 limit = 2;
}

message ProgressEvent {
  string job_id = 1;
  int32 step = 2;
  int32 percent = 3;
  string detail = 4;
}
~~~

Từ khóa `stream` nằm **trước kiểu response**. Khi `protoc` và plugin `protoc-gen-grpc-java` sinh mã, ta có các lớp message `ProgressRequest`, `ProgressEvent` và service/stub `ProgressServiceGrpc`. API observer dưới đây là API của **gRPC Java**; cách cấu hình plugin build, starter, và đăng ký service trong Spring có thể khác nhau tùy phiên bản tích hợp đang dùng.

## 4. Server Java: phân biệt ba callback bằng một service cụ thể

Đây là một triển khai **hữu hạn, dùng dữ liệu mô phỏng**. Mỗi message được tạo nhanh, không có `sleep` hay truy vấn chặn trong thread xử lý RPC. Mã minh họa luồng đúng và nhánh request không hợp lệ:

~~~java
package com.example.progress;

import com.example.progress.rpc.ProgressEvent;
import com.example.progress.rpc.ProgressRequest;
import com.example.progress.rpc.ProgressServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class ProgressServiceImpl
        extends ProgressServiceGrpc.ProgressServiceImplBase {

    @Override
    public void watchProgress(
            ProgressRequest request,
            StreamObserver<ProgressEvent> responses) {

        String jobId = request.getJobId().trim();
        int limit = request.getLimit();

        if (jobId.isEmpty() || limit < 1 || limit > 5) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription(
                            "job_id must not be blank; limit must be 1..5")
                    .asRuntimeException());
            return; // onError là terminal: không phát thêm message.
        }

        for (int step = 1; step <= limit; step++) {
            ProgressEvent event = ProgressEvent.newBuilder()
                    .setJobId(jobId)
                    .setStep(step)
                    .setPercent(step * 100 / limit)
                    .setDetail("Finished step " + step)
                    .build();

            responses.onNext(event);
        }

        responses.onCompleted(); // Chỉ khi đã gửi xong tất cả bước.
    }
}
~~~

Nếu gửi request `job_id = "job-17"` và `limit = 3`, client dự kiến nhận:

~~~text
onNext(ProgressEvent{step=1, percent=33})
onNext(ProgressEvent{step=2, percent=66})
onNext(ProgressEvent{step=3, percent=100})
onCompleted()
~~~

Nếu gửi `limit = 0`, server gọi `onError(INVALID_ARGUMENT)` rồi `return`, **không** có event nào và **không** gọi `onCompleted`.

Trong một ứng dụng Spring gRPC có cơ chế tự đăng ký `BindableService` từ Spring context, bean `@Service` được quản lý bởi Spring. Nếu dự án dùng starter tích hợp khác, cần sử dụng cơ chế đăng ký service đúng với starter đó; ba phương thức của `StreamObserver` vẫn hoạt động theo cùng nguyên tắc.

**Giới hạn của ví dụ:** vòng lặp này phù hợp để minh họa một luồng nhỏ hữu hạn. Không dùng cách đẩy hàng triệu message không kiểm soát, gọi I/O lâu hoặc chặn thread RPC bằng `Thread.sleep` trong hệ thống thật. Với producer bất đồng bộ, phải quản lý cancellation, flow control, thứ tự và số callback terminal.

## 5. Khi nào gọi onNext?

`onNext(T value)` được gọi mỗi khi **một response hợp lệ đã sẵn sàng** cho client. Trong server streaming, response có thể là trạng thái mới, một batch kết quả, đoạn dữ liệu, một log entry hay dấu mốc tiến độ.

Một số quy tắc thực tế:

- **Một lần gọi ứng với một message protobuf.** Không cần chờ gom tất cả event thành danh sách `repeated`.
- **Có thể không có event.** Ví dụ bộ lọc không trả kết quả; server vẫn có thể `onCompleted()` thành công.
- **Thứ tự gửi trên một RPC được bảo toàn.** Nhưng thứ tự logic của nhiều nguồn producer song song cần do ứng dụng tự xác định trước khi phát.
- **Không xem `onNext` là thao tác lưu trữ bền.** Server cần thiết kế idempotency và resume riêng nếu client phải xử lý đầy đủ mọi event.
- **Cân bằng tốc độ phát với tốc độ đọc.** Một producer không giới hạn có thể khiến buffer ứng dụng phình to, dù HTTP/2 hỗ trợ flow control.

Với server gRPC Java, có thể dùng `ServerCallStreamObserver<ProgressEvent>` để biết khi client không còn nhận được và quan sát readiness:

~~~java
ServerCallStreamObserver<ProgressEvent> out =
        (ServerCallStreamObserver<ProgressEvent>) responses;

if (out.isCancelled()) {
    return; // Ngừng sản xuất dữ liệu cho RPC đã bị hủy.
}

if (out.isReady()) {
    out.onNext(event); // event đã được xây dựng từ nguồn dữ liệu.
} else {
    // Chờ tín hiệu onReady, làm chậm upstream hoặc buffer có giới hạn.
}
~~~

Đoạn trên chỉ minh họa các phép kiểm tra trong **hàm phát sự kiện**, với `responses` và `event` có sẵn. `isReady()` là một tín hiệu của API flow control, **không phải** xác nhận client đã xử lý message. Không được âm thầm bỏ qua event nghiệp vụ bắt buộc khi observer chưa ready; cần hàng đợi có giới hạn, điều tiết upstream hoặc lưu để phát lại theo hợp đồng. Nếu có callback `setOnReadyHandler`, tránh vòng lặp busy-wait; chỉ phát khi điều kiện gửi lại phù hợp và vẫn kiểm tra trạng thái hủy.

## 6. Khi nào gọi onCompleted?

Gọi `onCompleted()` **một lần** khi server đã phát đủ message và không còn dữ liệu nào thuộc RPC đó. Callback này biểu thị **hoàn thành RPC thành công**, tương ứng với status `OK` được gRPC truyền khi kết thúc bình thường.

Ví dụ:

~~~java
// Trong phương thức service đã kiểm tra request hợp lệ:
for (ProgressEvent event : events) {
    responses.onNext(event);
}
responses.onCompleted();
~~~

Trường hợp `events` rỗng vẫn hoàn toàn hợp lệ: `onCompleted()` báo rằng truy vấn không có phần tử, nhưng việc truy vấn đã thành công.

Cần phân biệt **thành công về truyền thông** với **thành công nghiệp vụ**. Chẳng hạn job đã chạy và **thất bại theo nghiệp vụ**, nhưng server vẫn có thể phát một event có trạng thái `FAILED` rồi `onCompleted()` nếu hợp đồng coi đó là kết quả quan sát hợp lệ. Ngược lại, không tìm được job, không được truy cập hoặc không thể đọc nguồn dữ liệu là những trường hợp hợp lý để trả gRPC status lỗi.

Không dùng `onCompleted()` để:

- Xác nhận một message vừa được gửi qua `onNext` đã được client xử lý.
- Che giấu lỗi bằng cách đóng stream thành công rồi tiếp tục xử lý lỗi ở nơi khác.
- Kết thúc luồng khi vẫn còn task khác có thể phát trên cùng RPC nhưng chưa được đồng bộ hóa.

## 7. Khi nào gọi onError?

`onError(Throwable t)` kết thúc stream khi server **không thể tiếp tục đáp ứng RPC theo hợp đồng**. Thay vì ném exception tùy ý lên thread RPC, mã server nên chuyển lỗi có chủ đích thành `StatusRuntimeException`:

~~~java
responses.onError(Status.NOT_FOUND
        .withDescription("Job does not exist")
        .asRuntimeException());
return;
~~~

Đây là kết thúc lỗi, vì vậy phải `return` hoặc bảo đảm các nhánh khác không còn phát message. Một số mã trạng thái thường gặp:

| Status | Tình huống gợi ý |
|---|---|
| `INVALID_ARGUMENT` | `job_id` rỗng, tham số giới hạn sai |
| `NOT_FOUND` | Không tồn tại công việc được yêu cầu |
| `PERMISSION_DENIED` | Caller đã xác thực nhưng không được xem công việc |
| `UNAUTHENTICATED` | Thiếu hoặc không hợp lệ thông tin xác thực |
| `RESOURCE_EXHAUSTED` | Vượt hạn mức stream, bộ nhớ hoặc quota |
| `UNAVAILABLE` | Nguồn dữ liệu hoặc phụ thuộc tạm không khả dụng |
| `INTERNAL` | Lỗi nội bộ không thuộc lỗi đầu vào |

Ví dụ nguồn dữ liệu không đọc được **sau khi đã gửi một số message**:

~~~java
// Đây là một nhánh trong producer đang xử lý RPC.
if (sourceUnavailable) {
    responses.onError(Status.UNAVAILABLE
            .withDescription("Progress source unavailable")
            .asRuntimeException());
    return;
}
~~~

`sourceUnavailable` là điều kiện nghiệp vụ minh họa. Nếu đã nhận event bước 1 và 2, client có thể nhận `onError` mà không nhận bước 3. Thậm chí các message đang đệm khi xảy ra lỗi có thể không đến được client. Vì vậy **nhận được một vài `onNext` chưa có nghĩa toàn RPC thành công**.

Không nên gửi trực tiếp stack trace, token hoặc thông tin nội bộ nhạy cảm vào `Status.description`. Những chi tiết dùng để chẩn đoán nên đặt trong log/trace nội bộ có kiểm soát. Với lỗi kỹ thuật, server có thể log nguyên nhân thực và trả mô tả an toàn cho client.

**Sai lầm thường gặp:**

~~~java
responses.onError(Status.INTERNAL.asRuntimeException());
responses.onCompleted(); // SAI: đã có một terminal signal.
~~~

Hoặc:

~~~java
responses.onCompleted();
responses.onNext(event); // SAI: RPC đã kết thúc.
~~~

Khi gọi `onError`, dùng status phản ánh đúng loại lỗi. Không dùng `Status.OK` với `onError`; với thành công thì dùng `onCompleted`.

## 8. Ba callback phía client và ý nghĩa thực tế

Ở client async Java, ta cũng cung cấp một `StreamObserver<ProgressEvent>`, nhưng nó dùng để **nhận** message và tín hiệu kết thúc do runtime gRPC gọi. Server chủ động gọi các callback trên observer response ở server; client không tự gọi `onNext` trên response observer để yêu cầu gửi thêm message.

~~~java
import com.example.progress.rpc.ProgressEvent;
import com.example.progress.rpc.ProgressRequest;
import com.example.progress.rpc.ProgressServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

// channel là ManagedChannel đã được tạo và quản lý ở lớp gọi.
ProgressRequest request = ProgressRequest.newBuilder()
        .setJobId("job-17")
        .setLimit(3)
        .build();

CompletableFuture<Void> finished = new CompletableFuture<>();

ProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchProgress(request, new StreamObserver<ProgressEvent>() {
            @Override
            public void onNext(ProgressEvent value) {
                System.out.printf("step=%d, percent=%d%%%n",
                        value.getStep(), value.getPercent());
            }

            @Override
            public void onError(Throwable error) {
                System.err.println(
                        "Stream failed: " + Status.fromThrowable(error));
                finished.completeExceptionally(error);
            }

            @Override
            public void onCompleted() {
                System.out.println("Stream completed successfully");
                finished.complete(null);
            }
        });

// Chờ kết thúc chỉ để minh họa trong ứng dụng console/test.
// Không chặn event-loop hoặc thread xử lý request của ứng dụng web.
finished.get(12, TimeUnit.SECONDS);
~~~

Với request hợp lệ, callback được gọi theo hướng:

~~~text
onNext(step=1) → onNext(step=2) → onNext(step=3) → onCompleted()
~~~

Với `limit = 0`:

~~~text
onError(StatusRuntimeException: INVALID_ARGUMENT)
~~~

`CompletableFuture` ở ví dụ giúp chương trình demo đợi kết quả; nếu nhận lỗi, `get` ném `ExecutionException` chứa nguyên nhân. Trong ứng dụng Spring, client nên tái sử dụng channel và tổ chức vòng đời async thông qua bean/service phù hợp. Không nên đóng channel ngay sau lời gọi `watchProgress` vì lời gọi async trả quyền điều khiển về ngay trong khi stream còn đang chạy.

Client **không** cần đợi callback `onCompleted` nếu đã nhận `onError`. Đây là hai kết cục thay thế nhau. Nếu cần dừng stream chủ động, dùng API cancellation của gRPC, chẳng hạn `ClientCallStreamObserver.cancel(...)` trong mẫu client thích hợp, hoặc quản lý deadline. Không gọi thủ công `onError` của observer client để “hủy RPC”; cách đó chỉ tác động lên code callback của chính ứng dụng và không yêu cầu gRPC cancel call.

### Nếu dùng blocking stub thì sao?

Blocking stub server streaming trả về một `Iterator<ProgressEvent>`:

~~~java
var iterator = ProgressServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchProgress(request);

while (iterator.hasNext()) {
    ProgressEvent value = iterator.next();
    System.out.println(value.getPercent());
}
// Nếu vòng lặp hết bình thường: client đã quan sát hoàn thành thành công.
~~~

Blocking API không yêu cầu người dùng truyền trực tiếp callback. Nhưng ý nghĩa gRPC không đổi: các message tương ứng `onNext`, kết thúc thành công khiến iterator hết phần tử, lỗi có thể làm `hasNext`/`next` ném `StatusRuntimeException`. Thread gọi có thể bị chặn trong lúc chờ message tiếp theo.

## 9. Hủy, deadline và luồng kéo dài

Server streaming thường sống lâu hơn unary RPC. Một client có thể rời trang, ngắt mạng, hết deadline hoặc yêu cầu hủy khi server vẫn đang chờ dữ liệu tiếp theo. Khi đó, **không tiếp tục phát lên observer đã hủy**; cần hủy timer, subscription, listener, cursor hoặc tác vụ xử lý dành riêng cho RPC.

Ở phía server gRPC Java, `ServerCallStreamObserver` cung cấp API nhận tín hiệu hủy:

~~~java
ServerCallStreamObserver<ProgressEvent> out =
        (ServerCallStreamObserver<ProgressEvent>) responses;

out.setOnCancelHandler(() -> {
    // Hủy subscription/timer và giải phóng tài nguyên thuộc RPC.
    stopProducingForThisCall();
});
~~~

`stopProducingForThisCall()` ở đây là hàm do ứng dụng tự cài đặt. Với producer chạy trên thread/executor khác, callback hủy và callback phát có thể giao nhau. Cần cờ trạng thái/điều phối đồng bộ để không gửi `onNext` cùng lúc với thao tác kết thúc hoặc sau khi hủy. Không tự động gọi `onCompleted` sau hủy.

**Deadline áp dụng cho toàn RPC**, không khởi động lại mỗi khi server gửi `onNext`. Vì vậy một stream phát dữ liệu đều đặn vẫn có thể kết thúc do `DEADLINE_EXCEEDED` khi vượt thời hạn đã đặt. Client có thể thấy `CANCELLED` do chủ động hủy, `DEADLINE_EXCEEDED` do hết hạn hoặc `UNAVAILABLE` khi kết nối có vấn đề; status quan sát được phụ thuộc nguyên nhân và thời điểm lỗi.

Để vận hành ổn định, hệ thống nên có chính sách:

- Giới hạn số stream mở đồng thời và kích thước buffer.
- Đặt deadline/idle timeout phù hợp, thống nhất với cấu hình proxy hoặc load balancer.
- Giải phóng resource trong mọi nhánh kết thúc: thành công, lỗi và cancellation.
- Khi cần tiếp tục sau mất kết nối, thiết kế `sequence`/cursor, replay và deduplication ở tầng dữ liệu; gRPC không tự bảo đảm giao sự kiện nghiệp vụ **exactly once**.

## 10. Tránh race condition khi phát từ nhiều thread

Xem tình huống sau: một thread đọc dữ liệu muốn gọi `onNext(event)`, trong khi thread khác phát hiện lỗi và gọi `onError(cause)`. Nếu không có cơ chế phối hợp, cả hai phương thức có thể chạy đồng thời hoặc `onNext` xảy ra sau terminal callback.

Nguyên tắc triển khai:

1. **Đặt một nơi chịu trách nhiệm phát tín hiệu:** mọi message và terminal signal cho một RPC được đẩy qua một hàng đợi/executor tuần tự, hoặc được bảo vệ bằng cơ chế đồng bộ tương đương.
2. **Đánh dấu trạng thái trước khi kết thúc:** sau khi chọn `onError` hay `onCompleted`, bỏ qua các event đến muộn.
3. **Tách worker nghiệp vụ và sender:** worker đưa event vào hàng đợi có giới hạn; sender duy nhất tiêu thụ theo thứ tự, tôn trọng readiness và phát terminal đúng lúc.
4. **Xử lý hủy độc lập với kết thúc bình thường:** khi client đã hủy, việc dọn dẹp không được tiếp tục phát callback thành công.

Ví dụ pseudocode cho bộ phát tuần tự:

~~~text
producer threads --enqueue--> bounded event queue
                               |
                               v
                         single sender
                         | onNext(event) khi ready
                         | onCompleted() khi nguồn kết thúc thành công
                         | onError(status) khi nguồn lỗi
                         + stop + cleanup khi cancel
~~~

Không giả định rằng chỉ kiểm tra một cờ `AtomicBoolean` quanh hai lời gọi riêng rẽ là đủ để bảo đảm `onNext` và `onError` không đan xen. Nếu các lời gọi ở hai thread khác nhau, cần phối hợp nguyên tử cho **cả thao tác phát**, chẳng hạn executor tuần tự.

## 11. Kiểm thử đúng vòng đời callback

Ngoài unit test logic tạo message, có thể kiểm thử bằng gRPC **in-process transport** để sử dụng stub, protobuf serialization và status thật mà không cần cổng mạng. Ví dụ JUnit 5 dưới đây kiểm tra cả luồng thành công lẫn luồng lỗi:

~~~java
import com.example.progress.ProgressServiceImpl;
import com.example.progress.rpc.ProgressEvent;
import com.example.progress.rpc.ProgressRequest;
import com.example.progress.rpc.ProgressServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProgressServiceImplTest {
    @Test
    void streamingCallbacksAndTerminalStatus() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new ProgressServiceImpl())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            var stub = ProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS);

            ProgressRequest valid = ProgressRequest.newBuilder()
                    .setJobId("job-17")
                    .setLimit(3)
                    .build();
            List<ProgressEvent> received = new ArrayList<>();
            stub.watchProgress(valid).forEachRemaining(received::add);

            // Iterator kết thúc bình thường: client thấy status OK.
            assertEquals(List.of(1, 2, 3),
                    received.stream().map(ProgressEvent::getStep).toList());
            assertEquals(100, received.get(2).getPercent());

            ProgressRequest invalid = ProgressRequest.newBuilder()
                    .setJobId("job-17")
                    .setLimit(0)
                    .build();
            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.watchProgress(invalid).hasNext());
            assertEquals(Status.Code.INVALID_ARGUMENT,
                    error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Để chạy đoạn test trên, dự án cần JUnit 5 cùng dependency gRPC in-process tương thích với gRPC Java. Kiểm thử in-process chưa xác minh việc Spring thực sự đăng ký service, interceptor, TLS hoặc hành vi khi qua proxy. Cần bổ sung integration test dùng Spring context và bài thử mạng thật khi triển khai.

Các tình huống nên kiểm thử thêm:

| Test case | Kỳ vọng |
|---|---|
| Stream có 0 event | `onCompleted` thành công, client không nhận event |
| Stream có nhiều event | Số lượng và thứ tự message đúng |
| Lỗi trước event đầu | Client nhận đúng gRPC status, không có message |
| Lỗi sau vài event | Client nhận status lỗi; không coi dữ liệu từng phần là RPC thành công |
| Client hủy khi producer đang chờ | Không còn timer/subscription của RPC; không phát thêm |
| Deadline ngắn hơn thời gian stream | Client nhận lỗi hạn chót, server dừng công việc |
| Producer song song | Không ghi observer đồng thời; chỉ có một terminal signal |
| Client tiêu thụ chậm | Buffer và số tác vụ được giới hạn, không bùng nổ bộ nhớ |

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`onNext` gửi xong là client đã xử lý thành công” | `onNext` mới chuyển message cho runtime gRPC; muốn xác nhận nghiệp vụ cần cơ chế riêng |
| “`onCompleted` gửi message cuối” | Message cuối phải được gửi qua `onNext`; `onCompleted` chỉ báo kết thúc thành công |
| “Sau `onError` có thể `onCompleted` cho sạch luồng” | `onError` đã kết thúc RPC; không gọi thêm terminal khác |
| “Không có event nghĩa là lỗi” | Zero event rồi `onCompleted` có thể là kết quả hợp lệ |
| “Nếu đã có vài `onNext` thì RPC thành công một phần” | Dữ liệu có thể được xử lý từng phần nhưng **toàn RPC** vẫn có trạng thái lỗi |
| “Exception Java tự tạo ra status tốt” | Nên chủ động ánh xạ sang `Status` phù hợp và trả mô tả an toàn |
| “`isReady()` false thì có thể bỏ qua mọi event” | Phải dựa vào hợp đồng mất dữ liệu, buffer và replay |
| “Client hủy thì server gọi `onCompleted`” | Client hủy yêu cầu server **dừng sản xuất và dọn tài nguyên** |

### Câu hỏi tự luyện

1. Vì sao `onCompleted()` và `onError(...)` không thể cùng xuất hiện trong một luồng?
2. Khi request hợp lệ nhưng không có bản ghi, nên dùng `onCompleted()` hay `onError(NOT_FOUND)`? Điều gì trong hợp đồng quyết định lựa chọn?
3. Nếu server gửi hai event rồi gặp lỗi database, client có thể quan sát những kết cục nào?
4. Vì sao không thể gọi `onNext` từ nhiều thread lên cùng một observer mà không điều phối?
5. Sau khi client đóng ứng dụng, tài nguyên nào trên server phải được giải phóng?
6. Deadline 10 giây có được làm mới sau mỗi `onNext` hay không?

**Ghi nhớ:** Trong server streaming của Spring gRPC, **`onNext` phát từng message**, **`onCompleted` kết thúc thành công**, còn **`onError` kết thúc với lỗi**. Hợp đồng đúng yêu cầu các lần phát được tuần tự hóa, chỉ một terminal signal, và có xử lý cancellation, deadline, backpressure, status, bảo mật cũng như kiểm thử đầy đủ. Đây là nền tảng để luồng response có thể vận hành tin cậy trong hệ thống thực tế.
