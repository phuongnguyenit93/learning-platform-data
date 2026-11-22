# Client đọc từng message và backpressure

## 1. Bài toán: server gửi nhanh hơn client xử lý

Trong module **SPRING_GRPC**, chúng ta phát triển các dịch vụ gRPC trên Spring từ hợp đồng Protocol Buffers, sinh mã Java và triển khai unary hoặc streaming RPC. Phần **Server streaming** xét tình huống client gửi **một request**, rồi server phát **nhiều response** theo thời gian. Client có thể hiển thị hoặc xử lý từng response ngay khi đến, không cần chờ toàn bộ kết quả.

Khả năng nhận từng message rất hữu ích cho theo dõi tiến độ, truyền log, thông báo thay đổi trạng thái, đọc các bản ghi từ một truy vấn dài hoặc gửi từng lô kết quả. Tuy nhiên, một câu hỏi vận hành xuất hiện ngay: **điều gì xảy ra khi server tạo 1.000 message/giây nhưng client chỉ xử lý được 100 message/giây?**

Nếu ứng dụng tiếp tục nhận rồi đẩy tất cả message vào một hàng đợi không giới hạn, backlog sẽ tăng khoảng 900 message/giây. Trong 60 giây, riêng hàng đợi này có thể tích lũy khoảng 54.000 message. Kích thước bộ nhớ thực tế còn phụ thuộc payload, metadata và cấu trúc đối tượng.

**Backpressure** là cách giới hạn hoặc truyền ngược thông tin về khả năng tiêu thụ để nguồn phát không liên tục tạo ra nhiều dữ liệu hơn hệ thống có thể xử lý. Với gRPC Java, cần phân biệt ba lớp:

1. **Client application:** callback, iterator và các tác vụ ghi database, cập nhật giao diện hay xử lý dữ liệu.
2. **gRPC/HTTP/2:** bộ đệm và cơ chế flow control của transport; có thể trì hoãn việc truyền thêm dữ liệu khi phía nhận chưa sẵn sàng.
3. **Server producer:** nơi sự kiện được tạo ra (database cursor, timer, broker, worker hoặc dữ liệu tính toán), nơi ta phải giới hạn hàng đợi, điều tiết upstream hay có cơ chế lưu/phát lại.

~~~mermaid
flowchart LR
    P["Producer trên server"] --> Q["Buffer giới hạn"]
    Q --> S["gRPC server: onNext"]
    S --> H["HTTP/2 flow control"]
    H --> C["gRPC Java client"]
    C --> A["Client xử lý từng message"]
    A -. "Năng lực xử lý / request(n)" .-> C
    H -. "Giới hạn truyền" .-> S
    Q -. "Điều tiết upstream" .-> P
~~~

**Không nên đồng nhất ba lớp.** HTTP/2 flow control không tự giới hạn mọi hàng đợi ứng dụng. Việc gọi `onNext` ở server không phải xác nhận client đã xử lý xong message. Và việc client chỉ yêu cầu một message tiếp theo không tự động làm một nguồn sự kiện độc lập ngừng sản xuất.

## 2. Khái niệm backpressure trong server streaming

Giả sử server phát chuỗi message 1, 2, 3, 4, 5 trên cùng một RPC. gRPC bảo toàn thứ tự các message được gửi tuần tự trong RPC đó. Điều cần kiểm soát là **tốc độ cấp message mới cho mã xử lý phía client**, đồng thời hạn chế lượng dữ liệu đang nằm trong các buffer.

| Tình huống | Điều có thể xảy ra | Cách xử lý phù hợp |
|---|---|---|
| Server và client có tốc độ tương đương | Callback được xử lý đều đặn | Dùng chế độ nhận tự động nếu tài nguyên ổn định |
| Client tạm thời chậm | Có message chờ trong các buffer | Hạn chế số message đang xử lý và số message đệm |
| Client chậm lâu dài | Backlog tăng, latency tăng hoặc hết bộ nhớ | Điều tiết producer, giới hạn queue, hủy hoặc áp dụng chính sách mất dữ liệu |
| Dữ liệu có thể bỏ bản cũ | Chỉ trạng thái mới nhất có giá trị | Coalesce/ghi đè trạng thái cũ theo hợp đồng rõ ràng |
| Mọi event phải được giữ | Không được tự ý bỏ message | Dùng nguồn lưu bền, cursor/replay, quota và backpressure upstream |
| Client không còn cần dữ liệu | Stream vẫn có thể đang mở | Hủy RPC, dừng subscription và dọn tài nguyên |

Backpressure không bảo đảm **không bao giờ có message chờ**: gRPC, HTTP/2, kernel và ứng dụng có thể đã chứa dữ liệu trước khi tín hiệu điều tiết phát huy tác dụng. Mục tiêu thực tế là đưa kích thước hàng đợi và số công việc đang xử lý về giới hạn biết trước, kiểm soát latency và có cách xử lý khi vượt giới hạn.

### Hai câu hỏi cần trả lời trước khi viết mã

- **Message nào bắt buộc không được mất?** Ví dụ một sự kiện thanh toán phải lưu đầy đủ; tiến độ 31%, 32%, 33% có thể chỉ cần cập nhật 33% nếu hợp đồng cho phép.
- **Khi quá tải, nguồn dữ liệu có thể chậm lại không?** Database cursor hoặc publisher có backpressure dễ điều tiết hơn nguồn sự kiện bên ngoài liên tục đẩy mà không chờ consumer. Nguồn không thể chậm lại cần buffer có giới hạn và chính sách ghi bền, gộp hoặc từ chối rõ ràng.

## 3. Hợp đồng Protocol Buffers cho ví dụ

Ta xây dựng một API phát các sự kiện hữu hạn để quan sát cách client đọc từng message. File `src/main/proto/event_feed.proto`:

~~~proto
syntax = "proto3";

package feed.v1;

option java_multiple_files = true;
option java_package = "com.example.feed.rpc";
option java_outer_classname = "EventFeedProto";

service EventFeedService {
  rpc WatchEvents(WatchEventsRequest) returns (stream FeedEvent);
}

message WatchEventsRequest {
  string topic = 1;
  int32 max_events = 2; // Giới hạn 1..5 cho ví dụ.
}

message FeedEvent {
  string topic = 1;
  int64 sequence = 2;
  string payload = 3;
}
~~~

Từ khóa `stream` ở `returns (stream FeedEvent)` xác định **server streaming**: một `WatchEventsRequest` và nhiều `FeedEvent`. `protoc` cùng plugin `protoc-gen-grpc-java` sinh các message Java, `EventFeedServiceGrpc.EventFeedServiceImplBase` và stub client.

Trường `sequence` giúp kiểm tra thứ tự nhận và phát hiện message bị lặp/thiếu ở tầng nghiệp vụ. Tự thêm trường này **không** tạo ra khả năng khôi phục khi mạng đứt; muốn tiếp tục từ một sequence cụ thể phải thiết kế kho sự kiện và hợp đồng cursor/replay.

## 4. Server demo: phát một số message có thứ tự

Ví dụ sau là service Spring gRPC tạo tối đa năm message ngay trong một vòng lặp. Ta cố ý giữ server đơn giản để quan sát việc client kiểm soát **thời điểm giao message đến callback**.

~~~java
package com.example.feed;

import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class EventFeedServiceImpl
        extends EventFeedServiceGrpc.EventFeedServiceImplBase {

    @Override
    public void watchEvents(
            WatchEventsRequest request,
            StreamObserver<FeedEvent> responses) {

        String topic = request.getTopic().trim();
        int count = request.getMaxEvents();

        if (topic.isEmpty() || count < 1 || count > 5) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("topic required; max_events must be 1..5")
                    .asRuntimeException());
            return;
        }

        for (long i = 1; i <= count; i++) {
            FeedEvent event = FeedEvent.newBuilder()
                    .setTopic(topic)
                    .setSequence(i)
                    .setPayload("Event " + i)
                    .build();
            responses.onNext(event);
        }

        responses.onCompleted();
    }
}
~~~

Trong ứng dụng Spring gRPC có cơ chế tự nhận diện các Spring bean triển khai `BindableService`, `@Service` cho phép đăng ký service qua container. Với bộ tích hợp khác, phải cấu hình đăng ký service theo thư viện đang sử dụng; hợp đồng protobuf và `StreamObserver` vẫn như nhau.

**Giới hạn rất quan trọng của demo:** mã này có thể gọi hết năm lần `onNext` trước khi client xử lý xong message đầu tiên. Runtime gRPC có thể đang đệm những message còn lại. **Client manual flow control không buộc producer demo ngừng tạo message ngay sau một lần `onNext`.** Khi số sự kiện lớn hoặc stream kéo dài, server cần theo dõi readiness, dừng producer đúng lúc và có buffer có giới hạn.

## 5. Cách thứ nhất: blocking stub đọc từng message bằng Iterator

Client blocking nhận một `Iterator<FeedEvent>` từ method streaming. `hasNext()` và `next()` cho phép lấy từng response, có thể chặn thread gọi nếu chưa có message tiếp theo.

~~~java
package com.example.feed.client;

import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;

import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class BlockingFeedReader {
    public static void main(String[] args) {
        // Ví dụ dev; triển khai thật cần TLS và địa chỉ/cổng đúng cấu hình.
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .build();

        try {
            WatchEventsRequest request = WatchEventsRequest.newBuilder()
                    .setTopic("stock")
                    .setMaxEvents(5)
                    .build();

            Iterator<FeedEvent> stream = EventFeedServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(15, TimeUnit.SECONDS)
                    .watchEvents(request);

            while (stream.hasNext()) {
                FeedEvent event = stream.next();
                // Cố ý xử lý từng message ở cùng thread.
                process(event);
            }
            System.out.println("Received complete stream");
        } catch (StatusRuntimeException error) {
            System.err.println("RPC failed: " + error.getStatus());
        } finally {
            channel.shutdownNow();
        }
    }

    private static void process(FeedEvent event) {
        System.out.printf("sequence=%d payload=%s%n",
                event.getSequence(), event.getPayload());
    }
}
~~~

Khi `process(event)` xử lý đồng bộ, client không tự tạo một hàng đợi ứng dụng chứa mọi event rồi mới xử lý. Nhưng lời gọi `Iterator` vẫn có thể sử dụng buffer bên dưới, và việc đọc chậm không cam kết server chưa tạo thêm message.

Ưu điểm: dễ đọc, thứ tự xử lý rõ ràng và phù hợp batch job hoặc chương trình console ít kết nối. Nhược điểm: thread bị chặn khi chờ message, khó tích hợp với ứng dụng yêu cầu xử lý bất đồng bộ lớn. Nếu `process` làm I/O lâu, cần giới hạn deadline và kiểm tra khối lượng stream. **Không** chạy vòng lặp blocking này trên event loop hoặc request thread mà hệ thống cần trả về nhanh.

Nếu phía server trả `onError` sau một vài response, `hasNext()`/`next()` có thể ném `StatusRuntimeException`. Client không được coi việc đã nhận ba event là bằng chứng cả RPC thành công.

## 6. Cách thứ hai: async stub nhận message tự động

Với stub bất đồng bộ, client truyền một `StreamObserver<FeedEvent>` nhận các callback:

~~~java
WatchEventsRequest request = WatchEventsRequest.newBuilder()
        .setTopic("stock")
        .setMaxEvents(5)
        .build();

EventFeedServiceGrpc.newStub(channel)
        .withDeadlineAfter(15, TimeUnit.SECONDS)
        .watchEvents(request, new StreamObserver<FeedEvent>() {
            @Override
            public void onNext(FeedEvent value) {
                System.out.println(value.getSequence());
            }

            @Override
            public void onError(Throwable error) {
                System.err.println(Status.fromThrowable(error));
            }

            @Override
            public void onCompleted() {
                System.out.println("Stream finished");
            }
        });
~~~

Đoạn này giả định `channel` cùng các import message, stub, `StreamObserver`, `Status` và `TimeUnit` đã có. Lời gọi async trả về ngay; ứng dụng phải giữ channel còn sống đến khi nhận `onError` hoặc `onCompleted`.

Ở chế độ nhận mặc định, gRPC Java quản lý yêu cầu nhận thêm message cho observer. Cách này phù hợp nếu `onNext` xử lý nhanh và không chuyển dữ liệu sang queue không giới hạn. Tuy nhiên:

~~~java
@Override
public void onNext(FeedEvent value) {
    unboundedQueue.add(value); // Nguy hiểm nếu consumer của queue chậm.
}
~~~

Callback trên kết thúc rất nhanh, nên runtime có thể tiếp tục giao các event trong khi worker xử lý queue bị tụt lại. Đây là ví dụ **đọc mạng nhanh nhưng xử lý nghiệp vụ chậm**. Backpressure cần được liên kết với **số công việc đã xử lý**, không chỉ tốc độ hoàn tất callback.

## 7. Cách thứ ba: ClientResponseObserver điều khiển yêu cầu nhận

gRPC Java cung cấp `ClientResponseObserver<ReqT, RespT>` cho client async muốn điều khiển luồng nhận. Trước khi RPC bắt đầu, runtime gọi:

~~~java
void beforeStart(ClientCallStreamObserver<ReqT> requestStream)
~~~

Trong `beforeStart`, client có thể tắt chế độ tự động yêu cầu message và cấp một **số lượng nhận ban đầu**:

~~~java
requestStream.disableAutoRequestWithInitial(1);
~~~

Sau khi xử lý xong message, client chủ động cho phép thêm:

~~~java
requestStream.request(1);
~~~

Ý nghĩa của `request(1)` ở đây là **cho phép gRPC giao thêm một response đến observer**. Nó không gửi một message ứng dụng mới lên server và không phải ACK lưu dữ liệu. Đây là cách thể hiện *demand* ở phía nhận của API gRPC Java.

### Ví dụ Java: chỉ yêu cầu message tiếp theo sau khi xử lý xong

~~~java
package com.example.feed.client;

import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.util.concurrent.CompletableFuture;

public final class ManualDemandFeedReader {

    public static CompletableFuture<Void> read(
            EventFeedServiceGrpc.EventFeedServiceStub stub,
            WatchEventsRequest request) {

        CompletableFuture<Void> finished = new CompletableFuture<>();

        stub.watchEvents(
                request,
                new ClientResponseObserver<WatchEventsRequest, FeedEvent>() {

                    private ClientCallStreamObserver<WatchEventsRequest> control;

                    @Override
                    public void beforeStart(
                            ClientCallStreamObserver<WatchEventsRequest> stream) {
                        this.control = stream;
                        stream.disableAutoRequestWithInitial(1);
                    }

                    @Override
                    public void onNext(FeedEvent event) {
                        try {
                            // Ví dụ xử lý đồng bộ, không tạo thêm queue.
                            applyEvent(event);

                            // Chỉ sau khi xử lý xong mới yêu cầu response kế.
                            control.request(1);
                        } catch (RuntimeException error) {
                            // Lỗi ở client: chủ động dừng call.
                            control.cancel("Cannot process feed event", error);
                            finished.completeExceptionally(error);
                        }
                    }

                    @Override
                    public void onError(Throwable error) {
                        finished.completeExceptionally(error);
                    }

                    @Override
                    public void onCompleted() {
                        finished.complete(null);
                    }
                });

        return finished;
    }

    private static void applyEvent(FeedEvent event) {
        System.out.printf("Applied #%d: %s%n",
                event.getSequence(), event.getPayload());
    }
}
~~~

Cách gọi từ client đang giữ `ManagedChannel`:

~~~java
WatchEventsRequest request = WatchEventsRequest.newBuilder()
        .setTopic("stock")
        .setMaxEvents(5)
        .build();

EventFeedServiceGrpc.EventFeedServiceStub stub =
        EventFeedServiceGrpc.newStub(channel)
                .withDeadlineAfter(15, TimeUnit.SECONDS);

ManualDemandFeedReader.read(stub, request)
        .get(20, TimeUnit.SECONDS);
~~~

Ở đoạn gọi, `channel` cần được quản lý và đóng khi RPC kết thúc; các import `WatchEventsRequest`, `EventFeedServiceGrpc`, `TimeUnit` cùng `ManualDemandFeedReader` phải có sẵn. Với ứng dụng Spring, thường nên inject/reuse channel hoặc stub được quản lý, thay vì tạo một channel mới cho mỗi request. `CompletableFuture.get` chỉ phù hợp cho ví dụ console/test; đừng block event loop của ứng dụng production.

**Điểm cần hiểu chính xác:**

- `disableAutoRequestWithInitial(1)` phải thực hiện trong `beforeStart`, trước khi việc nhận response bắt đầu.
- `request(1)` không “bật server tạo đúng một event”; server vẫn có thể đã gọi `onNext` nhiều lần và runtime có thể giữ các message đang chờ.
- Trong ví dụ, gọi `request(1)` sau `applyEvent` nối năng lực nhận với việc hoàn tất xử lý **đồng bộ**. Nếu `applyEvent` chỉ enqueue việc sang thread khác rồi trả về, hạn chế này không còn phản ánh tốc độ xử lý thật.
- `onCompleted` và `onError` là hai kết cục thay thế nhau. Khi đã có terminal callback, không cần yêu cầu message tiếp.
- Nếu xử lý client thất bại, phải hủy RPC bằng API gRPC phù hợp và xử lý lỗi của ứng dụng; việc tự ném exception trong `onNext` không thay thế quy trình hủy/cleanup.

### Cửa sổ nhận nhiều message

Đọc từng message một giúp dễ lý giải nhưng có thể giảm thông lượng vì chờ một lần xử lý xong mới yêu cầu message tiếp theo. Một phương án là dùng cửa sổ nhỏ:

~~~java
stream.disableAutoRequestWithInitial(8);
~~~

Sau khi **một** event đã được xử lý xong, cấp lại **một** quyền nhận bằng `request(1)`. Khi ứng dụng duy trì đúng số lượng công việc đang xử lý, cửa sổ này giới hạn số response được giao nhưng chưa xử lý ở tầng client. Giá trị 8 chỉ để minh họa; cần đo độ trễ, kích thước payload, CPU, memory và tốc độ xử lý để điều chỉnh. Không nhầm với kích thước HTTP/2 window tính bằng byte.

## 8. Xử lý bất đồng bộ mà vẫn giữ backpressure

Giả sử ghi một event xuống database mất 200 ms. Nếu thực hiện công việc nặng ngay trong `onNext`, callback của gRPC sẽ bị chặn và có thể ảnh hưởng các lời gọi chia sẻ executor. Cách tốt hơn là chuyển việc xử lý sang executor thích hợp nhưng **chỉ gọi `request(1)` sau khi tác vụ hoàn tất**.

Ví dụ dạng pseudocode, tập trung vào cách phối hợp:

~~~text
beforeStart(stream):
    control = stream
    control.disableAutoRequestWithInitial(1)

onNext(event):
    submit_to_single_worker(() -> {
        try:
            persist_and_apply(event)
            control.request(1)  // Demand được trả lại sau khi đã xử lý.
        catch error:
            control.cancel("processing failed", error)
    })

onCompleted():
    submit_to_single_worker(() -> mark_rpc_completed_after_prior_work())

onError(error):
    submit_to_single_worker(() -> mark_rpc_failed_after_prior_work(error))
~~~

Khi dùng **một executor tuần tự**, việc xử lý message trước đó được hoàn thành trước khi client ghi nhận kết thúc RPC trong cùng hàng đợi. Một cửa sổ nhận `1` cũng khiến số tác vụ đang chờ do luồng này tạo ra được kiểm soát. Nếu áp dụng cửa sổ lớn hơn, cần dùng queue **có giới hạn** và tính đến số message đang xử lý song song.

Pseudocode cần được hoàn thiện khi đưa vào production: bắt lỗi khi executor từ chối nhận việc, đóng executor đúng vòng đời, xử lý cancellation và bảo đảm không gọi `request` sau khi call đã kết thúc. Nếu xử lý bằng nhiều worker song song, kết quả có thể hoàn tất khác thứ tự nhận; nếu nghiệp vụ yêu cầu thứ tự, hãy tuần tự hóa bước áp dụng dữ liệu hoặc gắn sequence để sắp xếp.

**Tránh hai lỗi trái chiều:**

1. **Request quá sớm:** nhận message rồi gọi `request(1)` ngay lập tức, sau đó mới enqueue công việc nặng vào queue không giới hạn. Dòng dữ liệu có thể chạy nhanh hơn consumer thật.
2. **Không request thêm:** tắt auto request, cấp một message ban đầu rồi quên gọi `request(1)` sau khi xử lý. Client có thể nhận message đầu tiên rồi dừng mãi dù server vẫn còn dữ liệu. Chỉ dựa vào deadline thì RPC cuối cùng mới hết hạn.

## 9. Phía server: readiness và điều tiết producer

Client kiểm soát callback nhận là **một nửa bài toán**. Nếu producer server vẫn liên tục đưa sự kiện vào một hàng đợi không giới hạn, memory server vẫn tăng. Với gRPC Java, server có thể chuyển `StreamObserver` thành `ServerCallStreamObserver` để quan sát khả năng ghi:

~~~java
ServerCallStreamObserver<FeedEvent> out =
        (ServerCallStreamObserver<FeedEvent>) responses;

out.setOnCancelHandler(() -> {
    // Unsubscribe nguồn sự kiện, hủy timer, giải phóng tài nguyên RPC.
    stopProducerForThisCall();
});

out.setOnReadyHandler(() -> {
    // Đề nghị sender tuần tự tiếp tục drain buffer có giới hạn.
    scheduleDrainForThisCall();
});
~~~

Ở đoạn trên, `responses` là observer trong service method, còn `stopProducerForThisCall` và `scheduleDrainForThisCall` là các hàm do ứng dụng tự cài đặt. Đây là ví dụ API, **chưa phải** triển khai backpressure đầy đủ.

Trong sender tuần tự, logic thường là:

~~~text
while notCancelled and out.isReady() and boundedQueue.hasNext():
    out.onNext(boundedQueue.removeNext())

if producerFinished and boundedQueue.empty() and notCancelled:
    out.onCompleted()

if producerFailed and notCancelled:
    out.onError(mappedGrpcStatus)
~~~

Các hoạt động phát, báo lỗi và hoàn thành cần được **tuần tự hóa**; không để producer callback, handler `onReady` và handler lỗi đồng thời gọi lên một observer. `ServerCallStreamObserver.isReady()` là một **gợi ý readiness của đường ghi**, không phải xác nhận client đã xử lý. Callback `onReady` có thể xuất hiện nhiều lần; cần tránh vòng lặp bận, rò rỉ job hoặc gửi một message nhiều lần.

| Vị trí | API / tín hiệu | Diễn giải |
|---|---|---|
| Client muốn nhận thêm response | `ClientCallStreamObserver.request(n)` | Cấp thêm nhu cầu nhận cho client observer |
| Client kiểm soát nhận từ đầu | `disableAutoRequestWithInitial(n)` trong `beforeStart` | Tắt tự yêu cầu và đặt nhu cầu ban đầu |
| Server muốn phát response | `ServerCallStreamObserver.isReady()` | Đường ghi đang sẵn sàng nhận thêm dữ liệu theo runtime |
| Server chờ khả năng ghi phục hồi | `setOnReadyHandler(...)` | Tín hiệu để thử drain theo lịch phối hợp |
| Server biết client hủy | `setOnCancelHandler(...)` hoặc `isCancelled()` | Dọn tài nguyên của RPC |
| Transport | HTTP/2 flow control | Điều tiết truyền byte/frame, khác số message nghiệp vụ |

**Lưu ý về hướng dữ liệu:** phía client, `ClientCallStreamObserver.isReady()` chủ yếu liên quan khả năng gửi **request đi**, không phải tín hiệu đo số response mà client đã xử lý. Trong **server streaming**, request ứng dụng ban đầu đã được gửi một lần; hãy dùng `request(n)` để điều khiển lượng **response nhận vào**.

### Chính sách khi client quá chậm

- **Dữ liệu không được mất:** dùng queue giới hạn với producer có thể chậm lại, hoặc ghi nguồn sự kiện ra bộ lưu trữ có thể replay theo sequence. Khi không thể đáp ứng, đóng RPC bằng status phù hợp và cho client đồng bộ lại theo hợp đồng.
- **Trạng thái cập nhật liên tục:** có thể coalesce nhiều thay đổi thành trạng thái mới nhất nếu client không cần từng trạng thái trung gian. Cần mô tả rõ trong hợp đồng API.
- **Dòng telemetry hoặc log best-effort:** có thể giới hạn tốc độ, sampling hoặc bỏ dữ liệu cũ theo chính sách được công bố.
- **Số client lớn:** chia sẻ subscription đến upstream nếu phù hợp và giới hạn stream đồng thời, bộ nhớ, tốc độ response trên từng caller.

Không dùng một thread riêng `Thread.sleep` để chờ mỗi client trong hệ thống có nhiều stream. Dùng scheduler/publisher/executor được quản lý, dọn dẹp khi server/client kết thúc RPC.

## 10. Tương tác với deadline, cancellation và status

Backpressure có thể khiến client cần nhiều thời gian hơn để tiêu thụ hết response. Deadline gRPC **giới hạn toàn bộ RPC**, không tự kéo dài sau mỗi message:

~~~text
0s          3s          6s        10s
|-- #1 xử lý --|-- #2 xử lý --|-- ... --X
                                       DEADLINE_EXCEEDED
~~~

Khi cần xử lý luồng dài, phải chọn deadline phù hợp mục tiêu nghiệp vụ hoặc thiết kế nhiều phiên có checkpoint, thay vì tùy tiện tăng deadline vô hạn. Với luồng theo dõi không có điểm kết thúc cố định, cần chính sách hủy, tái kết nối và giám sát thời lượng.

Các kết quả thường gặp:

| Kết quả | Client quan sát | Server cần làm gì |
|---|---|---|
| Đã nhận toàn bộ event và kết thúc | `onCompleted` hoặc iterator hết bình thường | Phát `onCompleted` đúng một lần; giải phóng subscription |
| Request không hợp lệ | `INVALID_ARGUMENT` | Trả `onError` với status phù hợp |
| Nguồn dữ liệu không khả dụng | `UNAVAILABLE` hoặc status thích hợp | Dừng producer, giải phóng buffer, báo lỗi |
| Client không còn cần stream | `CANCELLED` hoặc kết thúc theo ngữ cảnh hủy | Ngừng gửi và giải phóng tài nguyên thuộc RPC |
| Hết deadline | `DEADLINE_EXCEEDED` tại client | Nhận biết call bị hủy, dừng công việc liên quan |
| Quá hạn mức hoặc bộ đệm | `RESOURCE_EXHAUSTED` nếu API chọn trả mã đó | Giới hạn tải, trả status có ý nghĩa và cho phép retry có kiểm soát |

Với `ClientResponseObserver`, chủ động hủy bằng `ClientCallStreamObserver.cancel(message, cause)` khi ứng dụng không muốn tiếp tục. Không tự gọi callback `onError` của observer nhận để hủy RPC: callback chỉ là điểm thông báo, còn cancel phải được chuyển cho runtime.

**Đã nhận một phần khác với RPC thành công.** Client có thể xử lý sequence 1–3 rồi nhận `DEADLINE_EXCEEDED`. Nếu nghiệp vụ cần không mất dữ liệu, phải ghi checkpoint **sau khi xử lý thành công** và có thể phát lại từ checkpoint. gRPC tự nó không cung cấp bảo đảm giao event exactly-once hay lưu dữ liệu bền.

## 11. Metadata, TLS, interceptor và giám sát

Trong ứng dụng Spring gRPC, metadata của request thường chứa thông tin xác thực, correlation ID hoặc thông số điều khiển ở **cấp RPC**. Các trường thay đổi theo từng message như `sequence` và trạng thái nên nằm trong protobuf payload. Interceptor có thể thực hiện xác thực, phân quyền, ghi trace, đo số message/thời lượng và kết quả cuối cùng.

Luồng tồn tại lâu khiến thông tin về caller, hạn mức và vòng đời kết nối đặc biệt quan trọng:

- Dùng **TLS** cho kết nối thực tế; `usePlaintext()` trong client demo chỉ phù hợp môi trường dev đáng tin cậy. Xác minh chứng chỉ server, dùng mTLS nếu chính sách hệ thống yêu cầu.
- Phân quyền theo `topic`, giới hạn số stream đồng thời, kích thước payload và tốc độ sử dụng theo caller.
- Không ghi access token hoặc payload nhạy cảm vào log.
- Với token có thời hạn, cần chính sách rõ ràng cho stream chạy qua thời điểm token hết hiệu lực.

Các phép đo giúp phát hiện backpressure:

| Chỉ số | Ý nghĩa |
|---|---|
| Response/giây do server tạo và gửi | Nhận biết tốc độ producer và đường truyền |
| Response/giây client đã **xử lý xong** | Biết năng lực consumer thực tế |
| Số response đang xử lý và độ sâu queue | Phát hiện ứng dụng tích lũy backlog |
| Kích thước buffer tại server và client | Cảnh báo nguy cơ tăng bộ nhớ |
| Thời gian một message nằm chờ và xử lý | Phát hiện độ trễ đầu cuối tăng |
| Số lần server `isReady() == false` | Dấu hiệu đường ghi chưa sẵn sàng |
| Số RPC đang mở, thời lượng RPC | Dự báo khả năng chịu tải của service |
| `CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED` | Phân tích vì sao luồng dừng |
| Sequence gap, duplicate và checkpoint | Đánh giá khả năng replay/độ tin cậy dữ liệu |

Chỉ đếm số `onNext` ở server không đủ để khẳng định client đã xử lý. Muốn có chỉ số hoàn tất nghiệp vụ cần đo ngay sau khâu xử lý client, hoặc dùng một cơ chế xác nhận cấp ứng dụng riêng.

## 12. Kiểm thử manual inbound flow control

Gọi `ClientResponseObserver` với `disableAutoRequestWithInitial(1)` cho phép kiểm chứng một điều cụ thể: **client chưa cấp thêm nhu cầu thì các callback `onNext` tiếp theo chưa được giao**. Có thể kiểm thử bằng gRPC **in-process transport**, sử dụng protobuf, stub và service thật mà không mở cổng mạng.

Ví dụ JUnit 5 này dùng server demo ở mục 4:

~~~java
import com.example.feed.EventFeedServiceImpl;
import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class ClientDemandTest {

    @Test
    void onlyDeliversFurtherMessagesWhenRequested() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new EventFeedServiceImpl())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            AtomicReference<ClientCallStreamObserver<WatchEventsRequest>>
                    control = new AtomicReference<>();
            AtomicReference<Throwable> failure = new AtomicReference<>();
            List<Long> received = new ArrayList<>();
            CountDownLatch first = new CountDownLatch(1);
            CountDownLatch second = new CountDownLatch(1);
            CountDownLatch terminal = new CountDownLatch(1);

            WatchEventsRequest request = WatchEventsRequest.newBuilder()
                    .setTopic("stock")
                    .setMaxEvents(3)
                    .build();

            EventFeedServiceGrpc.newStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .watchEvents(
                            request,
                            new ClientResponseObserver<WatchEventsRequest,
                                                       FeedEvent>() {
                                @Override
                                public void beforeStart(
                                        ClientCallStreamObserver<
                                                WatchEventsRequest> stream) {
                                    control.set(stream);
                                    stream.disableAutoRequestWithInitial(1);
                                }

                                @Override
                                public void onNext(FeedEvent event) {
                                    received.add(event.getSequence());
                                    if (received.size() == 1) {
                                        first.countDown();
                                    }
                                    if (received.size() == 2) {
                                        second.countDown();
                                    }
                                    // Không tự gọi request() trong test.
                                }

                                @Override
                                public void onError(Throwable error) {
                                    failure.set(error);
                                    terminal.countDown();
                                }

                                @Override
                                public void onCompleted() {
                                    terminal.countDown();
                                }
                            });

            assertTrue(first.await(2, TimeUnit.SECONDS));
            assertEquals(List.of(1L), received);

            // Test chủ động cho phép giao thêm đúng một message.
            control.get().request(1);
            assertTrue(second.await(2, TimeUnit.SECONDS));
            assertEquals(List.of(1L, 2L), received);

            control.get().request(1);
            assertTrue(terminal.await(2, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(List.of(1L, 2L, 3L), received);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**Phạm vi kiểm thử:** test kiểm tra cơ chế cấp nhu cầu và thứ tự callback tại client. Nó **không** chứng minh server chỉ tạo một message mỗi lần, không đo lượng buffer nội bộ, và cũng không xác minh một hệ thống producer thực sự biết dừng khi client chậm. Với môi trường chạy callback từ executor khác, nên bảo vệ danh sách thu thập message bằng cơ chế đồng bộ hoặc chỉ đọc nó sau khi có quan hệ đồng bộ rõ ràng; ứng dụng thực tế cũng cần giới hạn tài nguyên và cleanup khi test timeout.

Các kiểm thử nên bổ sung:

1. **Không cấp thêm nhu cầu:** sau event đầu, chờ một khoảng ngắn có kiểm soát và xác minh chưa có callback event tiếp theo; sau đó cấp nhu cầu để hoàn tất.
2. **Cửa sổ nhiều message:** cấu hình initial demand 2 hoặc 8; đo số response đang xử lý và độ sâu queue khi xử lý bất đồng bộ.
3. **Client chậm:** xử lý mỗi event lâu hơn nhịp phát; quan sát bộ nhớ, latency, readiness và quota ở cả hai phía.
4. **Ngắt giữa chừng:** cancel từ client sau một message; xác minh server giải phóng subscription/producer.
5. **Deadline:** đặt thời hạn ngắn hơn thời gian xử lý toàn stream; client thấy `DEADLINE_EXCEEDED` và xử lý phần dữ liệu đã nhận theo hợp đồng.
6. **Lỗi xử lý client:** `applyEvent` thất bại; xác minh RPC được hủy, không request vô hạn và lỗi được báo về caller.
7. **Replay:** ngắt sau sequence 3 và tiếp tục từ checkpoint; kiểm tra thiếu/trùng nếu API hỗ trợ phát lại.
8. **Spring integration:** kiểm tra đăng ký service, metadata/interceptor, TLS, các timeout của proxy và giới hạn stream trên môi trường phù hợp.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Tác động | Cách xử lý |
|---|---|---|
| Nhận rồi enqueue vô hạn trong `onNext` | Consumer chậm làm queue phình to | Manual demand hoặc queue giới hạn và chỉ cấp nhu cầu khi xử lý xong |
| Gọi `request(1)` **trước** khi xử lý nặng hoàn tất | Demand không phản ánh năng lực consumer | Chuyển `request(1)` về thời điểm hoàn tất |
| Tắt auto request nhưng quên request tiếp | Stream đứng sau vài message | Cấp nhu cầu theo từng sự kiện xử lý xong và có nhánh lỗi rõ ràng |
| Nghĩ client `request(1)` buộc server chỉ `onNext` một lần | Server vẫn tạo và đệm dữ liệu | Điều tiết cả producer, readiness và buffer phía server |
| Dùng `ClientCallStreamObserver.isReady()` để đo response inbound | Đọc sai hướng dữ liệu | Với inbound, dùng `request(n)`; readiness outbound thuộc phía gửi |
| Đẩy nhiều `onNext` đồng thời từ server | Race và thứ tự không xác định | Một sender tuần tự trên mỗi RPC |
| Bỏ event mỗi khi `isReady() == false` | Mất sự kiện nghiệp vụ bắt buộc | Chọn lưu bền, buffer giới hạn hoặc áp dụng policy mất dữ liệu được công bố |
| Không cleanup khi client hủy | Rò rỉ timer, cursor và subscription | Dùng cancel handler, hủy producer và giải phóng buffer |
| Coi message đã nhận là toàn RPC thành công | Sai khi lỗi xảy ra giữa chừng | Chờ `onCompleted` hoặc status `OK` và quản lý checkpoint |

### Câu hỏi tự kiểm tra

1. Nếu client đọc được 100 message/giây còn server tạo 1.000 message/giây, điều gì xảy ra nếu ứng dụng có queue không giới hạn?
2. `request(1)` của `ClientCallStreamObserver` là một request protobuf gửi thêm lên server hay là nhu cầu nhận thêm response?
3. Vì sao `disableAutoRequestWithInitial(1)` chưa đủ để bảo đảm server không tăng bộ nhớ?
4. Trong ứng dụng dùng thread pool xử lý `FeedEvent`, khi nào mới nên `request(1)` tiếp?
5. `ServerCallStreamObserver.isReady()` khác gì với việc client đã xử lý xong message?
6. Vì sao client đã nhận vài message mà vẫn có thể quan sát `DEADLINE_EXCEEDED`?
7. Khi sự kiện bắt buộc không được mất, cần bổ sung gì ngoài backpressure?

**Ghi nhớ:** Client server streaming có thể **đọc và xử lý từng message** bằng `Iterator` hoặc `StreamObserver`. Khi cần điều khiển tốc độ giao response đến ứng dụng, `ClientResponseObserver` với `disableAutoRequestWithInitial(n)` và `request(n)` cho phép liên kết nhu cầu nhận với năng lực xử lý. Backpressure tin cậy đòi hỏi quản lý **toàn tuyến**: client processing, queue có giới hạn, flow control transport, producer server, cancellation, deadline, status, TLS, kiểm thử và giám sát.
