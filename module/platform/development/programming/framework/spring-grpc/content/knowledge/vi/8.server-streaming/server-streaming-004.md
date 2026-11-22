# Thứ tự response trong một stream

## 1. Vì sao thứ tự response quan trọng?

Trong module **SPRING_GRPC**, chúng ta xây dựng các dịch vụ gRPC trong hệ sinh thái Spring từ hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC. Với chương **Server streaming**, client gửi **một request** và nhận **nhiều response** trên cùng một lời gọi RPC. Một tính chất cốt lõi của kiểu giao tiếp này là **thứ tự các message trong chính stream đó được bảo toàn**.

Giả sử dịch vụ gửi tiến độ nhập dữ liệu. Client nhận:

~~~text
Response 1: Đã đọc tệp
Response 2: Đã kiểm tra dữ liệu
Response 3: Đã ghi cơ sở dữ liệu
Response 4: Hoàn thành
~~~

Nếu response 3 đến trước response 2, giao diện hoặc hệ thống nhận có thể hiển thị tiến độ sai. Server streaming giúp client nhận tuần tự các message **theo thứ tự mà chúng được gửi hợp lệ vào cùng một RPC**. Nhưng gRPC không tự đoán thứ tự nghiệp vụ mà ứng dụng mong muốn: khi nhiều nguồn xử lý chạy song song, server phải thiết kế cách sắp xếp trước khi gửi.

Mục tiêu của bài:

- Phân biệt **thứ tự gửi**, **thứ tự nhận**, **thứ tự sinh dữ liệu** và **thứ tự xử lý nghiệp vụ**.
- Hiểu chính xác phạm vi bảo đảm thứ tự của gRPC.
- Xây dựng ví dụ Spring gRPC server streaming với số thứ tự rõ ràng.
- Tránh race condition khi nhiều thread cùng tạo response.
- Kiểm tra thứ tự, mất kết nối, hủy và xử lý trùng qua kiểm thử.

## 2. gRPC bảo đảm điều gì trong một stream?

Trong một RPC server streaming, mỗi lần server gọi `onNext(response)` tạo ra một thông điệp gRPC riêng. Khi các lời gọi được thực hiện **tuần tự, theo đúng thứ tự**, client quan sát các message nhận được theo cùng thứ tự trong RPC đó.

~~~mermaid
sequenceDiagram
    participant S as Spring gRPC server
    participant T as HTTP/2 stream của RPC
    participant C as Java client
    S->>T: onNext(A)
    S->>T: onNext(B)
    S->>T: onNext(C)
    T-->>C: onNext(A)
    T-->>C: onNext(B)
    T-->>C: onNext(C)
    S->>T: onCompleted()
    T-->>C: onCompleted() / status OK
~~~

Mỗi message Protocol Buffers được gRPC đóng khung trên HTTP/2. Các byte/frame được truyền theo cơ chế của HTTP/2 và gRPC để client tái tạo các message theo thứ tự thuộc **một stream**. Việc một message lớn bị chia thành nhiều frame không làm nó trở thành nhiều response ở tầng ứng dụng.

| Phát biểu | Đúng hay sai? | Giải thích |
|---|---|---|
| Trong một RPC, các message đã được gửi tuần tự sẽ được client nhận theo thứ tự đó. | **Đúng** | Đây là tính chất bảo đảm thứ tự trong từng stream của gRPC. |
| gRPC tự sắp response theo thời gian tạo ra dữ liệu từ các worker. | **Sai** | Ứng dụng quyết định thứ tự gọi `onNext`. |
| Hai RPC khác nhau luôn có thứ tự tổng thể thống nhất. | **Sai** | Các stream độc lập; tốc độ mạng, scheduler và xử lý có thể khác nhau. |
| Nếu client nhận message 4 thì chắc chắn server đã gọi gửi message 1–3 trước đó trên cùng RPC hợp lệ. | **Đúng** | Với một luồng server gửi tuần tự các message 1–4 theo thứ tự. |
| Server đã gọi `onNext` thì message chắc chắn đã đến và được client lưu thành công. | **Sai** | `onNext` không phải xác nhận xử lý nghiệp vụ hay ghi bền của client. |
| Nếu RPC kết thúc lỗi, client chắc chắn nhận toàn bộ message đã phát. | **Sai** | Dữ liệu cuối có thể không đến; RPC không hoàn thành thành công. |
| gRPC đảm bảo client xử lý kết quả công việc nền theo đúng thứ tự. | **Sai** | Client có thể tự tách xử lý sang các thread khác và làm thay đổi thứ tự hoàn tất nghiệp vụ. |

**Phạm vi quan trọng:** Thứ tự được bảo đảm **trong từng RPC**. Không có thứ tự toàn cục tự động giữa các RPC, giữa nhiều service, hoặc giữa nhiều lần kết nối lại sau sự cố.

## 3. Bốn khái niệm thứ tự dễ bị nhầm

### 3.1. Thứ tự tạo kết quả

Là thời điểm producer, tác vụ bất đồng bộ hoặc nguồn sự kiện tạo ra dữ liệu. Ví dụ worker A bắt đầu xử lý bản ghi số 1 trước, nhưng worker B xử lý bản ghi số 2 nhanh hơn:

~~~text
09:00:00  Worker A bắt đầu xử lý bản ghi 1
09:00:01  Worker B bắt đầu xử lý bản ghi 2
09:00:02  Worker B tạo xong kết quả 2
09:00:05  Worker A tạo xong kết quả 1
~~~

Nếu server phát ngay khi từng worker hoàn thành thì client nhận thứ tự **2 rồi 1**. Đây không phải lỗi mạng hay lỗi gRPC. Thứ tự gửi đã phản ánh thứ tự hoàn thành của worker.

### 3.2. Thứ tự gửi vào stream

Là thứ tự các lời gọi `StreamObserver.onNext(...)` được thực hiện tuần tự. Server chịu trách nhiệm quyết định và bảo vệ thứ tự này. Với một producer tuần tự, việc bảo đảm thường rất đơn giản; với nhiều producer, cần hợp nhất kết quả theo quy tắc nghiệp vụ.

### 3.3. Thứ tự client nhận message

Khi server gửi hợp lệ trên cùng RPC, client nhận các response **theo thứ tự gửi**. Client async nhận lần lượt qua callback `onNext`; client blocking có thể duyệt các response bằng `Iterator`.

Điều này chỉ nói về message thực sự được nhận. Nếu kết nối bị gián đoạn, gRPC không biến một stream đã lỗi thành một danh sách đầy đủ có thể phục hồi tự động.

### 3.4. Thứ tự client hoàn tất xử lý

Giả sử client nhận A, B, C theo thứ tự rồi chuyển từng item sang thread pool. A mất 500 ms, B mất 50 ms, C mất 100 ms. Kết quả xử lý có thể hoàn tất theo **B, C, A**. gRPC không kiểm soát logic bất đồng bộ sau callback.

Muốn áp dụng các thay đổi đúng thứ tự, client phải xử lý tuần tự hoặc có cơ chế theo sequence/checkpoint khi kết quả xử lý song song.

~~~mermaid
flowchart LR
    A["Producer A: kết quả #1"] --> M["Bộ sắp thứ tự nghiệp vụ"]
    B["Producer B: kết quả #2"] --> M
    C["Producer C: kết quả #3"] --> M
    M --> S["Một sender tuần tự"]
    S --> G["gRPC stream: #1 → #2 → #3"]
    G --> R["Client nhận: #1 → #2 → #3"]
    R --> P["Xử lý / lưu theo chính sách của client"]
~~~

## 4. Khai báo hợp đồng Protocol Buffers có số thứ tự

Để thấy được thứ tự trong log, kiểm thử và cơ chế tiếp tục sau ngắt kết nối, ta thêm trường `sequence` vào mỗi response. Giả sử ứng dụng theo dõi các bước xử lý của một đơn hàng:

~~~proto
syntax = "proto3";

package order.v1;

option java_multiple_files = true;
option java_package = "com.example.order.rpc";
option java_outer_classname = "OrderProto";

service OrderProgressService {
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderUpdate);
}

message WatchOrderRequest {
  string order_id = 1;
}

enum OrderPhase {
  ORDER_PHASE_UNSPECIFIED = 0;
  ACCEPTED = 1;
  PAID = 2;
  PACKED = 3;
  SHIPPED = 4;
}

message OrderUpdate {
  string order_id = 1;
  int64 sequence = 2;
  OrderPhase phase = 3;
  int64 created_at_epoch_ms = 4;
}
~~~

Trong method `WatchOrder`, từ khóa `stream` ở kiểu **response** xác định server streaming. `protoc` và plugin `protoc-gen-grpc-java` sinh mã message và các class gRPC Java như `OrderUpdate`, `WatchOrderRequest`, `OrderProgressServiceGrpc`.

Trường `sequence` có tác dụng:

1. Biểu diễn thứ tự **nghiệp vụ** mà client có thể kiểm tra, không chỉ thứ tự đến mạng.
2. Cho phép client phát hiện response bị lặp hoặc bị thiếu trong luồng sự kiện **theo hợp đồng ứng dụng**.
3. Là nền tảng cho checkpoint/replay **nếu** server có lưu lịch sử và API tiếp tục thích hợp.
4. Hỗ trợ log và tracing khi điều tra sự cố.

**Không nên nhầm:** có `sequence` không tự làm message được sắp thứ tự, không tự thêm retry, và không tự bảo đảm exactly-once. Trong ví dụ, sequence là số tăng theo từng đơn hàng và server phải duy trì quy tắc này.

## 5. Server Spring gRPC gửi response theo thứ tự

Ví dụ sau chủ ý phát từ một luồng gọi tuần tự để minh họa chính xác quan hệ `onNext` → thứ tự client. Đây là dữ liệu mô phỏng, không phải workflow thanh toán thực.

~~~java
package com.example.order;

import com.example.order.rpc.OrderPhase;
import com.example.order.rpc.OrderProgressServiceGrpc;
import com.example.order.rpc.OrderUpdate;
import com.example.order.rpc.WatchOrderRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class OrderProgressServiceImpl
        extends OrderProgressServiceGrpc.OrderProgressServiceImplBase {

    @Override
    public void watchOrder(
            WatchOrderRequest request,
            StreamObserver<OrderUpdate> responses) {

        String orderId = request.getOrderId().trim();
        if (orderId.isEmpty()) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("order_id must not be blank")
                    .asRuntimeException());
            return;
        }

        List<OrderPhase> phases = List.of(
                OrderPhase.ACCEPTED,
                OrderPhase.PAID,
                OrderPhase.PACKED,
                OrderPhase.SHIPPED);

        for (int index = 0; index < phases.size(); index++) {
            OrderUpdate response = OrderUpdate.newBuilder()
                    .setOrderId(orderId)
                    .setSequence(index + 1L)
                    .setPhase(phases.get(index))
                    .setCreatedAtEpochMs(System.currentTimeMillis())
                    .build();

            responses.onNext(response);
        }

        responses.onCompleted();
    }
}
~~~

Kết quả kỳ vọng cho `order_id = "ORD-101"`:

~~~text
sequence=1, phase=ACCEPTED
sequence=2, phase=PAID
sequence=3, phase=PACKED
sequence=4, phase=SHIPPED
gRPC status: OK
~~~

Đoạn code trên gọi `onNext` theo thứ tự cố định trong một vòng lặp. `onCompleted` chỉ được gọi sau khi phát hết bốn message. Nếu request sai, `onError(INVALID_ARGUMENT)` kết thúc RPC và server không phát thêm.

Với những bản cập nhật từ hệ thống thật, bốn trạng thái có thể xuất hiện cách nhau hàng phút hoặc nhiều giờ. **Không** giữ một thread RPC bận chờ bằng `Thread.sleep` giữa từng trạng thái. Thay vào đó, subscribe nguồn dữ liệu bất đồng bộ, cho một sender tuần tự phát message khi có sự kiện, và hủy subscription khi RPC đóng.

Tùy phiên bản/bộ tích hợp Spring gRPC, bean `@Service` có thể được tự phát hiện là một `BindableService` hoặc cần cơ chế đăng ký tương ứng. Quy tắc thứ tự của `StreamObserver` là API gRPC Java, không thay đổi theo cách đăng ký bean.

## 6. Client Java kiểm tra thứ tự đã nhận

Client sử dụng **blocking stub** có thể duyệt `Iterator<OrderUpdate>` theo thứ tự response:

~~~java
import com.example.order.rpc.OrderProgressServiceGrpc;
import com.example.order.rpc.OrderUpdate;
import com.example.order.rpc.WatchOrderRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;

import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class OrderProgressClient {
    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext() // Chỉ dùng cho ví dụ dev/trong môi trường tin cậy.
                .build();

        try {
            WatchOrderRequest request = WatchOrderRequest.newBuilder()
                    .setOrderId("ORD-101")
                    .build();

            Iterator<OrderUpdate> stream = OrderProgressServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(10, TimeUnit.SECONDS)
                    .watchOrder(request);

            long expectedSequence = 1;
            while (stream.hasNext()) {
                OrderUpdate update = stream.next();

                if (update.getSequence() != expectedSequence) {
                    throw new IllegalStateException(
                            "Expected sequence " + expectedSequence
                            + " but received " + update.getSequence());
                }

                System.out.println(
                        update.getSequence() + ": " + update.getPhase());
                expectedSequence++;
            }
        } catch (StatusRuntimeException error) {
            System.err.println("RPC failed: " + error.getStatus());
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

`expectedSequence` kiểm chứng **hợp đồng nghiệp vụ** của ví dụ: response phải có sequence 1, 2, 3, 4. Nếu server gửi 1, 3, 2 thì gRPC vẫn có thể truyền đúng **1, 3, 2** theo thứ tự đã gọi `onNext`, nhưng client phát hiện thứ tự nghiệp vụ không đúng.

Cổng 9090 là ví dụ, cần phù hợp cấu hình gRPC server của dự án. Trong ứng dụng Spring, nên tái sử dụng channel do container quản lý và cấu hình **TLS** cho môi trường thật.

### Async stub cũng nhận theo thứ tự stream

Client async nhận từng message qua `StreamObserver.onNext`:

~~~java
WatchOrderRequest request = WatchOrderRequest.newBuilder()
        .setOrderId("ORD-101")
        .build();

OrderProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchOrder(request, new StreamObserver<OrderUpdate>() {
            private long expected = 1;

            @Override
            public void onNext(OrderUpdate update) {
                if (update.getSequence() != expected) {
                    System.err.println("Unexpected sequence: " + update.getSequence());
                }
                expected = update.getSequence() + 1;
                processInOrder(update);
            }

            @Override
            public void onError(Throwable error) {
                System.err.println(Status.fromThrowable(error));
            }

            @Override
            public void onCompleted() {
                System.out.println("Stream completed");
            }
        });
~~~

Đoạn async giả định `channel`, `processInOrder(update)` và các imports tương ứng đã tồn tại. `processInOrder` là hàm ứng dụng minh họa; nếu nó chuyển xử lý sang thread pool, việc **hoàn tất** các tác vụ được chuyển đi có thể đảo thứ tự. Khi trạng thái phải được áp dụng tuần tự, dùng một hàng đợi xử lý có thứ tự hoặc điều phối theo sequence.

Không được gọi `onError` hay `onCompleted` thủ công trên observer nhận của client để điều khiển thứ tự trên server. Chúng là callback đầu ra của RPC tại client.

## 7. Nguồn dữ liệu song song: gRPC không tự sắp theo sequence

Đây là sai lầm phổ biến nhất khi triển khai server streaming. Giả sử server phân tích ba phần của báo cáo cùng lúc:

~~~text
Producer 1: tạo message #1 sau 300 ms
Producer 2: tạo message #2 sau 100 ms
Producer 3: tạo message #3 sau 200 ms

Nếu gửi ngay khi hoàn thành: #2 → #3 → #1
~~~

Client sẽ nhận `#2, #3, #1` nếu server phát chúng tuần tự theo thứ tự đó. **gRPC đã giữ thứ tự gửi, nhưng thứ tự nghiệp vụ bị sai.**

Ngoài ra, không được để nhiều worker trực tiếp gọi `responseObserver.onNext(...)` đồng thời. `StreamObserver` không mặc định thread-safe cho các lời gọi ghi song song; thứ tự giữa các lời gọi concurrent cũng không được định nghĩa theo số thứ tự trong payload.

### 7.1. Thiết kế một sender tuần tự

Hãy tách **việc tạo dữ liệu** khỏi **việc phát lên RPC**:

~~~mermaid
flowchart TD
    A["Worker A tạo event #1"] --> Q["Bộ đệm có giới hạn / reorder buffer"]
    B["Worker B tạo event #2"] --> Q
    C["Worker C tạo event #3"] --> Q
    Q --> R{"Đã có nextExpected?"}
    R -- "Chưa" --> W["Giữ hoặc chờ, áp dụng timeout/chính sách lỗi"]
    W --> R
    R -- "Có" --> S["Single sender: onNext(nextExpected)"]
    S --> I["Tăng nextExpected; kiểm tra phần tử tiếp theo"]
    I --> R
    S --> G["gRPC stream"]
    G --> H["Client: #1, #2, #3"]
~~~

Một phương án thực hiện:

1. **Ấn định sequence** theo quy tắc nghiệp vụ trước khi thực thi công việc song song (ví dụ thứ tự bản ghi trong truy vấn đã có ORDER BY).
2. Các worker hoàn thành thì nộp `(sequence, result)` vào bộ gom (aggregator); không gọi observer.
3. Bộ gom giữ kết quả đến sớm trong một buffer **có giới hạn**.
4. Một sender duy nhất chỉ gửi phần tử có `sequence == nextExpected` rồi tăng `nextExpected`.
5. Khi tất cả phần tử cần gửi đã được xác nhận hoàn thành, sender gọi `onCompleted()`. Nếu không thể lấy một phần tử bắt buộc, chọn chính sách timeout/retry hoặc kết thúc `onError(...)`.
6. Khi client hủy, dừng producer, bỏ subscription và giải phóng buffer.

Ví dụ pseudocode:

~~~text
nextExpected = 1
pending = bounded_map()

onWorkerResult(sequence, event):
    enqueueIntoSingleSender(() -> {
        pending.put(sequence, event)
        while pending.contains(nextExpected) and transportCanAcceptMore():
            responseObserver.onNext(pending.remove(nextExpected))
            nextExpected += 1
    })

onAllWorkersFinished():
    enqueueIntoSingleSender(() -> {
        if pending.isEmpty() and nextExpected == totalExpected + 1:
            responseObserver.onCompleted()
        else:
            waitOrFailAccordingToPolicy()
    })

onCancellation():
    stopProducers()
    stopSenderAndReleaseBuffers()
~~~

Đây là **pseudocode về kiến trúc**, không phải Java để sao chép nguyên trạng. Với gRPC Java, `transportCanAcceptMore()` có thể dựa trên `ServerCallStreamObserver.isReady()` và callback `setOnReadyHandler`; cả việc nhận sự kiện ready và nhận kết quả worker cũng phải được điều phối trên sender tuần tự. Producer phải chịu backpressure hoặc có cơ chế lưu/replay khi buffer đạt giới hạn. Không quay vòng busy-wait và không bỏ bản cập nhật quan trọng chỉ vì `isReady()` đang false.

### 7.2. Khi nào được phép gửi theo thứ tự hoàn thành?

Không phải mọi stream đều cần sequence 1, 2, 3 phản ánh thứ tự khởi tạo. Với **kết quả độc lập**, gửi theo thứ tự tác vụ hoàn thành có thể đúng nghiệp vụ, giúp giảm độ trễ:

~~~text
SearchResults(request) → result B → result A → result C
~~~

Khi đó, hợp đồng nên nói rõ kết quả **không có thứ tự nghiệp vụ cố định**. gRPC vẫn bảo toàn thứ tự các message đã phát, nhưng client không được ngầm hiểu result A phải đến trước result B. Nếu client cần thứ tự theo điểm số, thời điểm sự kiện hoặc ID, server phải tự sắp theo tiêu chí đó.

## 8. Cơ chế HTTP/2, flow control và deadline tác động ra sao?

### 8.1. HTTP/2 có thể xen kẽ các stream, nhưng không đảo message trong một RPC

Trên một kết nối HTTP/2 có thể có nhiều stream độc lập:

~~~text
RPC A: A1 -------- A2 ------ A3
RPC B: ---- B1 -------- B2

Một thời điểm truyền có thể xen kẽ A1, B1, A2, B2, A3.
Thứ tự nội bộ của RPC A vẫn A1, A2, A3.
Thứ tự nội bộ của RPC B vẫn B1, B2.
Không có bảo đảm A2 đến trước B2 hay ngược lại.
~~~

Việc song song hóa giữa các RPC là lợi ích của HTTP/2 multiplexing. Nó không cung cấp thứ tự giữa các RPC cho ứng dụng. Nếu nghiệp vụ phải phối hợp nhiều stream, cần timestamp logic, sequence toàn cục hoặc giao thức hợp nhất rõ ràng.

### 8.2. Flow control ảnh hưởng tốc độ, không thay đổi thứ tự

Nếu client đọc chậm, gRPC/HTTP/2 có thể làm giảm tốc độ gửi. Message thứ 2 sẽ không vì thế vượt qua message thứ 1 trong cùng một stream; nhưng độ trễ và lượng message đang chờ có thể tăng.

`ServerCallStreamObserver.isReady()` báo mức sẵn sàng của đường ghi theo cơ chế flow control; nó **không** phải xác nhận message đã được client xử lý. Với stream dài, cần giới hạn buffer, kết hợp `setOnReadyHandler` hoặc publisher có backpressure, và chính sách mất dữ liệu/khôi phục minh bạch.

### 8.3. Deadline hoặc cancellation có thể làm stream dừng giữa chừng

Giả sử server định phát 1, 2, 3, 4 nhưng client hủy sau 2:

~~~text
Server dự định: 1 → 2 → 3 → 4 → onCompleted()
Client thấy:    1 → 2 → CANCELLED (hoặc kết thúc theo nguyên nhân thực tế)
~~~

Thứ tự được bảo toàn đối với các response **thực sự nhận được**, nhưng không có cam kết nhận đủ cả bốn response. Deadline áp dụng cho **toàn RPC**, không được làm mới sau mỗi message. Server phải dừng producer/subscription khi call bị hủy hoặc deadline hết, thông qua tín hiệu cancellation của gRPC Java.

### 8.4. onError và onCompleted là hai kết cục khác nhau

Server có thể phát nhiều `onNext` rồi kết thúc bằng:

- `onCompleted()`: hết message, RPC hoàn thành thành công.
- `onError(Status...asRuntimeException())`: RPC thất bại; client cần xử lý status, không coi những response trước đó là bằng chứng của thành công toàn RPC.

Không gọi `onNext` sau khi đã có terminal callback, không gọi cả `onError` và `onCompleted`, và phải tuần tự hóa những lời gọi này cùng các thao tác phát message. Đối với client, callback `onError` có thể xảy ra sau khi client đã nhận một số message, còn message đang chờ có thể không được giao.

## 9. Thứ tự sau khi reconnect: cần hợp đồng nghiệp vụ

Khi một RPC cũ kết thúc vì lỗi mạng rồi một RPC mới được tạo, đó là **hai stream độc lập**. gRPC không bảo đảm stream mới tự nhận tiếp từ response còn thiếu của stream trước. Đặc biệt, việc client đã nhìn thấy `sequence = 7` không đủ để suy ra mọi cập nhật đã được xử lý và lưu bền thành công.

Một hợp đồng resumable có thể thêm cursor:

~~~proto
message WatchOrderRequest {
  string order_id = 1;
  int64 after_sequence = 2;
}
~~~

Khi client kết nối lại với `after_sequence = 7`, server cần có khả năng đọc lịch sử **sau** sequence 7 và chuyển tiếp sang sự kiện mới mà không tạo lỗ hổng. Điều này yêu cầu kho sự kiện có lưu trữ, quy tắc cấp sequence, giới hạn retention, và thao tác snapshot/subscribe nhất quán.

Client cần:

1. Chỉ ghi checkpoint sau khi đã xử lý thành công event.
2. Bỏ event trùng khi replay nếu đã có bản ghi được xử lý.
3. Phát hiện khoảng thiếu, ví dụ mong đợi 8 nhưng nhận 10, rồi yêu cầu đồng bộ lại theo hợp đồng.
4. Không coi toàn bộ dữ liệu là hoàn chỉnh cho đến khi nhận được kết thúc phù hợp.

Ví dụ kiểm tra:

~~~java
// Nằm bên trong callback nhận message, dùng một executor xử lý tuần tự.
long receivedSequence = update.getSequence();
if (receivedSequence <= lastAppliedSequence) {
    return; // Bản ghi trùng sau retry/replay.
}
if (receivedSequence != lastAppliedSequence + 1) {
    throw new IllegalStateException("Missing event before " + receivedSequence);
}

applyEvent(update); // Chỉ cập nhật checkpoint sau khi xử lý thành công.
lastAppliedSequence = receivedSequence;
~~~

Đoạn trên là snippet minh họa, giả định `update`, `lastAppliedSequence` và `applyEvent` đã được định nghĩa; trong ứng dụng thật, việc update trạng thái và lưu checkpoint nên được phối hợp nhất quán, ví dụ trong một transaction khi dữ liệu cùng kho. Việc ném exception từ callback client **không thay thế** một chính sách hủy RPC/resync; code thực tế cần xử lý lỗi ứng dụng và hủy/tạo call mới có kiểm soát.

## 10. Metadata, TLS và quan sát thứ tự

Trong hệ sinh thái Spring gRPC, metadata/interceptor thường dùng cho xác thực, phân quyền, correlation ID và tracing. Đối với luồng có thứ tự, nên đưa `order_id` và `sequence` trong payload hoặc các trường dữ liệu quan sát thích hợp để chẩn đoán gap/duplicate; metadata là thông tin ở cấp RPC, không phải nơi cập nhật sequence cho từng message.

Trên mạng thực, dùng TLS để bảo vệ transport; xác thực quyền truy cập `order_id` trước khi stream mở và kiểm soát số stream mỗi caller. Nếu log hoặc trace ghi chuỗi sự kiện, tránh lộ payload nhạy cảm hoặc access token.

Các chỉ số giúp chẩn đoán vấn đề thứ tự:

| Chỉ số | Giá trị vận hành |
|---|---|
| `messages_sent` và `messages_received` | Xác định lưu lượng; so sánh cần gắn cùng RPC và hiểu giới hạn thu thập. |
| `last_sequence` / `expected_sequence` | Phát hiện gap, duplicate hoặc vi phạm thứ tự nghiệp vụ. |
| Kích thước reorder buffer | Phát hiện producer đến chênh lệch tốc độ, nguy cơ tăng bộ nhớ. |
| Thời gian chờ `nextExpected` | Phát hiện worker chậm hoặc sự kiện thiếu. |
| `isReady()` / độ sâu queue | Đánh giá backpressure và client tiêu thụ chậm. |
| `CANCELLED`, `DEADLINE_EXCEEDED`, `UNAVAILABLE` | Phân biệt nguyên nhân stream bị dừng. |
| Thời gian từ sinh dữ liệu đến khi client áp dụng | Đo tính kịp thời của thứ tự nghiệp vụ. |

Vì log của nhiều thread và nhiều host không nhất thiết hiện theo thứ tự xảy ra thực tế, hãy dùng sequence/correlation ID, không chỉ nhìn timestamp của hai log rồi kết luận gRPC đảo thứ tự.

## 11. Kiểm thử thứ tự trên gRPC transport

Có thể kiểm chứng chuỗi event bằng **gRPC in-process transport**: sử dụng lớp service thật, serialization/stub Java và status gRPC mà không mở cổng mạng. Ví dụ JUnit 5 cho service ở mục 5:

~~~java
import com.example.order.OrderProgressServiceImpl;
import com.example.order.rpc.OrderPhase;
import com.example.order.rpc.OrderProgressServiceGrpc;
import com.example.order.rpc.OrderUpdate;
import com.example.order.rpc.WatchOrderRequest;
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

class OrderProgressServiceTest {

    @Test
    void responsesKeepServiceSendOrder() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderProgressServiceImpl())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            var stub = OrderProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS);
            var request = WatchOrderRequest.newBuilder()
                    .setOrderId("ORD-101")
                    .build();

            List<OrderUpdate> events = new ArrayList<>();
            stub.watchOrder(request).forEachRemaining(events::add);

            assertEquals(List.of(1L, 2L, 3L, 4L),
                    events.stream().map(OrderUpdate::getSequence).toList());
            assertEquals(List.of(
                    OrderPhase.ACCEPTED,
                    OrderPhase.PAID,
                    OrderPhase.PACKED,
                    OrderPhase.SHIPPED),
                    events.stream().map(OrderUpdate::getPhase).toList());

            var invalid = WatchOrderRequest.newBuilder()
                    .setOrderId(" ")
                    .build();
            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.watchOrder(invalid).hasNext());
            assertEquals(Status.Code.INVALID_ARGUMENT,
                    error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Kiểm thử này xác minh **thứ tự các response mà service gửi** và nhánh lỗi `INVALID_ARGUMENT`. Nó không chứng minh hệ thống có thể ghép đúng message từ nhiều producer thật hoặc bảo toàn thứ tự giữa các stream khác nhau. Những tình huống đó cần kiểm thử ở tầng ứng dụng và kiểm thử tích hợp Spring.

Một bộ kiểm thử đầy đủ hơn nên bao gồm:

1. **Gửi tuần tự:** 1, 2, 3, 4 đến client cùng thứ tự, stream kết thúc `OK`.
2. **Nguồn song song:** worker #2 hoàn thành trước #1 nhưng client vẫn nhận 1, 2 khi hợp đồng đòi hỏi thứ tự ID.
3. **Thiếu một phần tử:** không gọi `onCompleted` thành công nếu hợp đồng bắt buộc đủ dữ liệu mà event #3 không tồn tại.
4. **Client chậm:** producer không làm buffer tăng vô hạn; sau khi client bắt kịp vẫn giữ đúng thứ tự.
5. **Hủy/deadline:** ngắt giữa chừng; dừng sender/worker, giải phóng queue và không phát terminal trùng.
6. **Retry/reconnect:** phát lại một số message, client deduplicate và tiếp tục từ checkpoint theo hợp đồng.
7. **Nhiều RPC đồng thời:** không áp đặt nhầm thứ tự tổng thể cho hai stream độc lập.
8. **Spring integration:** xác minh service đăng ký, interceptor, TLS và cấu hình proxy phù hợp khi chạy trong môi trường thực tế.

## 12. Các lỗi thiết kế phổ biến

| Lỗi | Vì sao xảy ra | Cách khắc phục |
|---|---|---|
| Nhầm thứ tự hoàn thành của worker với thứ tự nghiệp vụ | Producer chạy song song và gửi ngay | Gán sequence rõ ràng, dùng reorder buffer và sender tuần tự. |
| Nhiều thread cùng gọi `onNext` | Observer bị chia sẻ giữa các worker | Tuần tự hóa mọi lời gọi ghi của một RPC. |
| Client xử lý song song rồi ghi trạng thái sai thứ tự | Callback nhận đúng nhưng các task hoàn tất khác nhau | Dùng queue xử lý theo thứ tự hoặc transaction/checkpoint theo sequence. |
| Giả định hai RPC có thứ tự chung | HTTP/2 multiplex nhiều stream độc lập | Thiết kế sequence toàn cục nếu nghiệp vụ thực sự cần. |
| Coi `onNext` là xác nhận đã lưu dữ liệu | API gửi không phải ACK nghiệp vụ | Thiết kế xác nhận/checkpoint theo nhu cầu. |
| Luôn chờ phần tử thiếu mà không giới hạn | Reorder buffer không có timeout và quota | Giới hạn hàng đợi, timeout và chính sách lỗi/replay. |
| Kết thúc thành công sau khi bỏ sót event bắt buộc | Không kiểm tra sequence trước `onCompleted` | Xác minh đủ phần tử theo hợp đồng trước terminal callback. |
| Không xử lý hủy khi client rời đi | Producer vẫn chạy và giữ tài nguyên | Đăng ký cancel handler và cleanup theo vòng đời RPC. |

### Câu hỏi tự kiểm tra

1. Server phát `onNext(B)` rồi `onNext(A)`; gRPC có tự sắp lại thành A rồi B vì timestamp của A nhỏ hơn không?
2. Client nhận đúng A, B, C rồi xử lý trong thread pool. Nó có chắc ghi xong A trước B không?
3. Vì sao nhiều RPC cùng chạy trên một HTTP/2 connection không có thứ tự toàn cục?
4. `sequence` trong protobuf giải quyết vấn đề gì, và điều gì nó **không** tự giải quyết?
5. Nếu worker #4 xong trước worker #3, server phải làm gì nếu yêu cầu gửi theo thứ tự 1, 2, 3, 4?
6. Khi connection ngắt sau message #7, điều kiện nào giúp một RPC mới tiếp tục an toàn từ #8?

**Ghi nhớ:** gRPC giữ thứ tự **các message được gửi tuần tự trong cùng một stream**. Server vẫn phải xác định thứ tự nghiệp vụ trước khi gọi `onNext`, tuần tự hóa việc ghi từ nhiều thread, kiểm soát backpressure và xử lý lỗi/hủy. Client nhận đúng thứ tự truyền nhưng phải tự bảo vệ thứ tự xử lý và khôi phục dữ liệu khi RPC gián đoạn.
