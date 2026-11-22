# Backpressure khi client chậm

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận biết dấu hiệu server tạo response nhanh hơn tốc độ client tiêu thụ.
- Dùng outbound readiness của gRPC Java để điều tiết việc gửi response.
- Kết hợp inbound demand ở client với queue có giới hạn để tạo backpressure xuyên suốt.
- Thiết kế producer có thể tạm dừng/tiếp tục và xử lý nguồn dữ liệu không thể pause.
- Chọn chính sách khi queue đầy, client hủy RPC hoặc deadline hết hạn.
- Kiểm thử và giám sát streaming khi client đọc chậm mà không làm tăng bộ nhớ vô hạn.

## 1. Vì sao client chậm gây áp lực lên server?

Trong server-streaming hoặc bidirectional streaming, server có thể tạo response liên tục. Client có thể đọc chậm vì xử lý nghiệp vụ tốn thời gian, ghi dữ liệu xuống ổ đĩa, gọi một dịch vụ khác hoặc bị giới hạn băng thông mạng.

Nếu server tiếp tục tạo và xếp response nhanh hơn khả năng gửi, dữ liệu chờ sẽ tích lũy trong bộ nhớ. Khi nhiều RPC cùng gặp tình trạng này, heap tăng, garbage collection hoạt động nhiều và các request khác có thể bị ảnh hưởng.

**Backpressure** là cách truyền tín hiệu ngược về phía producer rằng consumer chưa sẵn sàng nhận thêm dữ liệu. Producer giảm tốc, tạm dừng hoặc từ chối tiếp tục khi đạt giới hạn. Trong Spring gRPC, cần phối hợp cơ chế readiness của gRPC, flow control của HTTP/2 và queue ở tầng ứng dụng.

## 2. Luồng backpressure từ client về server

Với server-streaming, dữ liệu đi từ server tới client. Khi client đọc chậm, các lớp vận chuyển dần hạn chế lượng dữ liệu server có thể gửi. Ở tầng ứng dụng, **ServerCallStreamObserver.isReady()** giúp server biết khi nào gRPC sẵn sàng nhận thêm response.

~~~mermaid
flowchart LR
  P["Server producer"] --> Q["Bounded outbound queue"]
  Q --> D["gRPC response writer"]
  D --> T["HTTP/2 transport"]
  T --> C["Client"]
  C -. "Đọc chậm / giảm demand" .-> T
  T -. "Readiness giảm" .-> D
  D -. "Tạm dừng drain" .-> Q
  Q -. "Đạt ngưỡng" .-> P
~~~

Một luồng xử lý an toàn có các bước:

1. Producer tạo response và đưa vào outbound queue có giới hạn.
2. Writer chỉ lấy message khỏi queue khi observer sẵn sàng.
3. Khi observer không ready, writer tạm dừng; queue giữ lượng dữ liệu chờ trong giới hạn.
4. Khi readiness trở lại, writer tiếp tục drain queue.
5. Nếu queue đầy, ứng dụng pause producer hoặc áp dụng chính sách overflow đã công bố.

Backpressure có hiệu quả khi tín hiệu readiness/demand cuối cùng làm giảm tốc độ tạo dữ liệu. Nếu chỉ dừng gửi nhưng vẫn tiếp tục tạo và giữ response ở một queue không giới hạn, bộ nhớ vẫn tăng.

## 3. isReady() và on-ready callback ở server

Server có thể ép kiểu response observer thành **ServerCallStreamObserver<T>**:

~~~java
ServerCallStreamObserver<PriceUpdate> outbound =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;
~~~

Hai API quan trọng:

- **isReady()**: cho biết gRPC hiện có thể nhận thêm outbound message theo ngưỡng buffer/readiness của implementation.
- **setOnReadyHandler(...)**: đăng ký callback khi trạng thái readiness chuyển sang sẵn sàng để gửi tiếp.

Ví dụ:

~~~java
outbound.setOnReadyHandler(this::scheduleDrain);

// Cần kích hoạt lần drain ban đầu nếu observer đã ready.
scheduleDrain();
~~~

Không hiểu **isReady() == true** là client đã đọc hoặc xử lý xong response trước. Đây là tín hiệu khả năng tiếp nhận ở tầng gửi/transport, không phải xác nhận nghiệp vụ hay ACK cho từng message. Tương tự, false cho biết nên dừng gửi thêm để tránh tích lũy buffer; nó không nhất thiết chứng minh client code đang bị treo.

Không dùng vòng lặp bận như **while (!outbound.isReady()) {}**. Hãy trả quyền điều khiển cho executor và đợi callback khi readiness thay đổi.

## 4. Outbound queue có giới hạn

Một queue riêng cho mỗi RPC giúp giới hạn lượng response đang chờ:

~~~java
BlockingQueue<PriceUpdate> pending =
    new ArrayBlockingQueue<>(128);
~~~

Khi producer tạo response:

~~~java
boolean accepted = pending.offer(update);
if (!accepted) {
    // Pause producer hoặc chuyển RPC sang chính sách overflow.
}
~~~

**offer()** không chặn lâu khi queue đầy. Tránh gọi **put()** trên thread tạo dữ liệu hoặc callback gRPC nếu việc chờ có thể giữ executor dùng chung.

Giới hạn theo số message chưa đủ nếu payload có kích thước rất khác nhau. Với dữ liệu lớn, cần thêm **byte budget**:

- Số message tối đa đang chờ.
- Tổng kích thước serialized tối đa đang chờ, có thể ước lượng bằng **getSerializedSize()**.
- Kích thước tối đa của một response.
- Số tác vụ producer đang chạy đồng thời.

Byte budget phải được cập nhật đồng bộ khi enqueue/dequeue. Kích thước serialized chỉ ước lượng payload Protobuf; nó không bao gồm toàn bộ overhead của object, queue node và buffer transport.

## 5. Drain response theo readiness

Chỉ một writer nên gọi **onNext()** trên cùng response observer. Mọi producer đưa response vào queue; writer lấy ra khi observer ready:

~~~java
void drain() {
    while (!cancelled.get() && outbound.isReady()) {
        PriceUpdate next = pending.poll();
        if (next == null) {
            break;
        }
        outbound.onNext(next);
    }
}
~~~

Đăng ký **setOnReadyHandler(this::scheduleDrain)** và gọi **scheduleDrain()** sau mỗi lần enqueue. Hàm scheduleDrain nên bảo đảm chỉ có một drain task hoạt động tại một thời điểm, ví dụ dùng AtomicBoolean cùng một executor tuần tự.

Đây là phần cốt lõi, không phải một service hoàn chỉnh. Trong triển khai thực tế:

- Gọi **onNext**, **onError** và **onCompleted** tuần tự trên cùng writer.
- Không để hai thread cùng drain một queue cho cùng observer.
- Sau khi drain kết thúc, kiểm tra lại readiness và queue để tránh bỏ lỡ tín hiệu khi producer enqueue đúng lúc writer nhường quyền.
- Nếu executor từ chối task hoặc producer lỗi, kết thúc RPC theo một đường terminal duy nhất.

Không phát **onCompleted()** chỉ vì producer đã kết thúc. Cần đợi outbound queue rỗng và không còn response đang chờ drain.

## 6. Pause và resume producer

Readiness chỉ hữu ích nếu producer có thể phản ứng. Nếu producer truy vấn database theo từng trang, đọc file theo chunk hoặc nhận dữ liệu từ một nguồn có thể pause, hãy nối trạng thái queue/readiness với việc tiếp tục tạo dữ liệu.

Ví dụ luồng producer:

~~~text
produce page/chunk
      |
      v
enqueue response
      |
      v
queue gần đầy hoặc outbound not-ready?
      |                 |
     No                Yes
      |                 |
produce next       pause source
                        |
                 readiness returns
                        |
                   resume source
~~~

Nên dùng API pause/resume của nguồn dữ liệu nếu có. Không tạo trước hàng nghìn response rồi mới kiểm tra **isReady()**. Nếu nguồn chỉ có thể đọc tuần tự, giữ cursor hoặc offset để tiếp tục sau khi consumer sẵn sàng.

Với producer bất đồng bộ, tránh chặn thread event loop hoặc executor gRPC trong lúc đợi queue có chỗ. Dùng signal, semaphore hoặc scheduler để tiếp tục khi có capacity.

## 7. Client có thể điều tiết inbound demand

Client streaming response cũng có thể dùng manual inbound flow control để chỉ yêu cầu thêm message sau khi xử lý xong message trước. Với gRPC Java, **ClientResponseObserver** cung cấp **ClientCallStreamObserver** trong **beforeStart(...)**.

Ví dụ client chỉ yêu cầu một response ban đầu:

~~~java
ClientResponseObserver<SubscribeRequest, PriceUpdate> observer =
    new ClientResponseObserver<>() {

        private ClientCallStreamObserver<SubscribeRequest> call;

        @Override
        public void beforeStart(
                ClientCallStreamObserver<SubscribeRequest> requestStream) {
            this.call = requestStream;
            requestStream.disableAutoRequestWithInitial(1);
        }

        @Override
        public void onNext(PriceUpdate update) {
            consumerExecutor.execute(() -> {
                process(update);
                call.request(1);
            });
        }

        @Override
        public void onError(Throwable error) {
            handleFailure(error);
        }

        @Override
        public void onCompleted() {
            finishConsumption();
        }
    };
~~~

Ở đây client chỉ yêu cầu message đầu tiên; sau khi worker xử lý xong một response, client mới gọi **request(1)** để cho phép nhận tiếp. Trong code thực tế, cần bảo vệ việc request khi call đã kết thúc/cancel và xử lý lỗi từ consumer executor.

Khi client giảm demand, gRPC và HTTP/2 có thể làm chậm việc chuyển DATA từ server. Server thường quan sát tác động đó qua readiness sau khi buffer/cửa sổ truyền bị sử dụng. Đây là backpressure theo tầng; không có nghĩa một lần request(1) được chuyển thành một frame WINDOW_UPDATE tương ứng.

## 8. Queue đầy: không được để producer tiếp tục vô hạn

Queue đầy là tín hiệu cho biết tốc độ tạo dữ liệu vượt khả năng tiêu thụ trong một khoảng thời gian. Chọn chính sách theo ý nghĩa dữ liệu:

| Chính sách | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| **Pause producer** | Nguồn có thể dừng và tiếp tục | Ưu tiên khi cần giữ mọi message. |
| **Reject RPC** | Không thể giữ thêm dữ liệu và không thể pause | Có thể trả **RESOURCE_EXHAUSTED**; client cần xử lý lỗi. |
| **Drop newest** | Dữ liệu mới không quan trọng bằng dữ liệu đang chờ | Phải đo và công bố số message bị bỏ. |
| **Drop oldest** | Chỉ cần trạng thái gần nhất, ví dụ snapshot | Không phù hợp với event cần bảo toàn lịch sử. |
| **Persist** | Cần hấp thụ tải dài hơn và có yêu cầu độ bền | Cần quota, retention và cơ chế resume. |

Với sự kiện nghiệp vụ, giao dịch hoặc dữ liệu cần kiểm toán, không tự ý drop. Có thể dừng nguồn hoặc kết thúc RPC bằng **RESOURCE_EXHAUSTED**. Không retry vô hạn; cần deadline, backoff và giới hạn số lần thử.

Nếu client cần tiếp tục sau khi reconnect, thiết kế cursor/sequence number và cơ chế resume ở tầng ứng dụng. Một queue trong bộ nhớ gắn với RPC đã kết thúc không thể bảo đảm giao hàng lại.

## 9. Client chậm, mạng chậm và client đã hủy

Ba tình huống có thể tạo dấu hiệu tương tự nhưng cần cách xử lý khác:

- **Client xử lý chậm**: client nhận message nhưng ứng dụng tiêu thụ chậm; manual demand có thể làm giảm lượng message được yêu cầu.
- **Mạng chậm hoặc mất gói**: transport/TCP bị hạn chế dù ứng dụng client có thể đang sẵn sàng. Readiness vẫn có thể giảm vì dữ liệu gửi đi chưa thoát khỏi buffer.
- **Client hủy RPC hoặc mất kết nối**: server cần dừng producer và giải phóng tài nguyên thay vì tiếp tục chờ readiness.

Trên server, dùng **setOnCancelHandler(...)** để nhận tín hiệu call bị hủy:

~~~java
outbound.setOnCancelHandler(() -> {
    cancelled.set(true);
    cancelUpstreamProducer();
    pending.clear();
});
~~~

Đoạn mã minh họa việc phát tín hiệu dừng. Nếu queue có byte budget, cleanup cũng phải giải phóng bộ đếm; nếu producer có subscription hoặc file handle, cần hủy/đóng chúng đúng cách.

Deadline hết hạn cũng phải dừng việc tạo response. Không tiếp tục truy vấn hoặc tính toán chỉ để đưa dữ liệu vào một stream mà client không còn chờ.

## 10. Một RPC chậm không được chiếm tài nguyên toàn hệ thống

Queue nên được giới hạn theo từng RPC và toàn service:

- **Per-RPC limit** ngăn một client chiếm quá nhiều bộ nhớ.
- **Global limit** ngăn hàng nghìn RPC mỗi RPC dùng đúng quota nhưng tổng cộng vượt heap.
- **Concurrency limit** giới hạn số producer/worker đang hoạt động.
- **Fair scheduling** tránh một stream liên tục chiếm writer hoặc executor.

Không đặt một queue lớn cho mỗi RPC rồi bỏ qua số RPC đồng thời. Ví dụ, 1.000 RPC với queue 128 message có thể giữ tới 128.000 message, chưa kể byte payload và object overhead.

Khi global quota cạn, từ chối RPC mới hoặc áp dụng admission control rõ ràng. Không giữ semaphore hoặc permit mãi sau cancellation; giải phóng tài nguyên trong cleanup path.

## 11. Kiểm thử với client tiêu thụ chậm

Một bài kiểm thử có ích cần chủ động làm client đọc chậm thay vì chỉ gửi một vài message nhỏ:

1. Tạo server-streaming RPC phát số lượng lớn response có kích thước đã biết.
2. Dùng client **ClientResponseObserver** với **disableAutoRequestWithInitial(1)**.
3. Trong consumer, trì hoãn xử lý mỗi message rồi mới **request(1)**.
4. Quan sát server readiness, queue depth và byte budget.
5. Xác nhận producer pause/resume hoặc RPC bị reject theo chính sách khi queue đầy.
6. Hủy client giữa stream và xác nhận producer, worker cùng queue được dọn.
7. Chạy nhiều RPC chậm đồng thời để kiểm tra global quota và tính công bằng.

Không nên khẳng định **isReady()** sẽ chuyển false ngay khi client ngừng gọi **request(1)**. Transport có thể còn buffer và window cho phép một lượng dữ liệu tiếp tục đi qua trước khi áp lực truyền tải biểu hiện ở server. Kiểm thử nên xác nhận giới hạn bộ nhớ và hành vi cuối cùng, không phụ thuộc một thời điểm readiness tuyệt đối.

Metric nên theo dõi:

- Queue depth và queued bytes theo RPC.
- Số lần queue chạm ngưỡng/cạn capacity.
- Thời gian producer bị pause.
- Thời gian outbound không ready.
- Số message được gửi, xử lý, từ chối hoặc drop.
- Số RPC bị cancel, deadline exceeded hoặc resource exhausted.
- Số producer/worker đang hoạt động và tổng bộ nhớ queue.

Không ghi payload đầy đủ vào log chỉ để xác định client chậm. Dùng request ID, sequence number, kích thước message và metric tổng hợp.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tiếp tục tạo response khi **isReady()** false | Outbound queue tăng dù transport đang nghẽn | Pause producer hoặc giới hạn queue. |
| Dùng queue không giới hạn | Client chậm làm heap tăng liên tục | Bounded queue và byte budget. |
| Xem **isReady()** như ACK của client | Suy luận sai rằng message đã được xử lý | Dùng acknowledgement ở tầng ứng dụng nếu cần xác nhận. |
| Chỉ dùng readiness mà không có giới hạn queue | Dữ liệu vẫn tích lũy trước writer | Giới hạn queue và tốc độ producer. |
| Chặn callback gRPC để đợi client | Chiếm executor và ảnh hưởng RPC khác | Dùng callback/signal bất đồng bộ. |
| Nhiều thread cùng ghi observer | Race condition, sai thứ tự hoặc terminal event lặp | Một outbound writer tuần tự. |
| Không xử lý cancellation/deadline | Producer vẫn chạy cho client đã rời đi | Hủy upstream và cleanup tài nguyên. |
| Retry streaming vô hạn sau overflow | Tạo thêm tải và có thể gửi trùng | Backoff, giới hạn retry, idempotency và resume cursor. |

## 13. Bài tập thực hành

Thiết kế RPC server-streaming gửi cập nhật giá cho client:

1. Định nghĩa **SubscribePricesRequest** và **PriceUpdate**.
2. Tạo outbound queue giới hạn cả số message và tổng byte.
3. Dùng **ServerCallStreamObserver.isReady()** và on-ready handler để drain.
4. Khi queue gần đầy, pause subscription nguồn; khi queue giảm, resume.
5. Ở client, dùng manual inbound flow control và chỉ **request(1)** sau khi xử lý xong update.
6. Định nghĩa hành vi khi client chậm quá lâu, queue đầy, deadline hết hạn hoặc client hủy.
7. Thiết kế metric để phân biệt producer nhanh, consumer chậm và mạng chậm.
8. Viết integration test với client trì hoãn xử lý và kiểm tra queue không vượt quota.

**Tiêu chí hoàn thành:** backpressure tác động ngược tới producer, queue có giới hạn rõ ràng, response được gửi theo readiness, và mọi tài nguyên được giải phóng khi RPC kết thúc.

## 14. Ghi nhớ

- Client chậm khiến response chờ tích lũy; backpressure phải làm giảm tốc producer chứ không chỉ dừng writer.
- **ServerCallStreamObserver.isReady()** và **setOnReadyHandler()** điều tiết outbound ở tầng gRPC; readiness không phải ACK nghiệp vụ.
- Client có thể dùng **ClientResponseObserver** và **disableAutoRequestWithInitial(n)** để điều tiết inbound demand.
- Dùng queue có giới hạn theo số message và byte; xác định pause, reject, drop hoặc persist theo semantics.
- Chỉ một writer tuần tự gọi observer; không chặn callback gRPC để chờ queue hoặc readiness.
- Cancellation và deadline phải dừng producer, worker và giải phóng quota.
- Kiểm thử với client đọc chậm và nhiều RPC đồng thời để xác nhận giới hạn bộ nhớ ở cả per-RPC lẫn toàn service.

Backpressure được thiết kế đúng giúp Spring gRPC thích ứng với client có tốc độ tiêu thụ khác nhau, bảo vệ bộ nhớ server và duy trì độ tin cậy của streaming RPC khi tải tăng.
