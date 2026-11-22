# Kích thước response và giới hạn bộ nhớ

## 1. Giới hạn kích thước từng response khác với giới hạn toàn stream

Trong **SPRING_GRPC**, một server streaming RPC gửi một request rồi trả nhiều response Protocol Buffers. Việc chia kết quả thành nhiều message giúp client xử lý dần, nhưng không tự động bảo đảm bộ nhớ luôn thấp. Một response quá lớn vẫn có thể cần nhiều bộ nhớ để tạo object, serialize, buffer, truyền, deserialize và xử lý. Nhiều response nhỏ cũng có thể làm bộ nhớ tăng nếu ứng dụng giữ tất cả trong một danh sách hoặc hàng đợi không giới hạn.

Vì vậy cần tách hai khái niệm:

- **Kích thước một response:** số byte của một message protobuf sau serialization. Đây là giới hạn message mà cấu hình inbound của phía nhận có thể áp dụng.
- **Tổng dữ liệu của stream:** tổng kích thước của mọi response trong suốt RPC. Một stream có thể truyền nhiều gigabyte qua hàng nghìn message nhỏ mà không có một message đơn lẻ nào vượt giới hạn.

Ví dụ một dịch vụ tải tài liệu:

~~~text
Một RPC DownloadDocument
  response #1: chunk 256 KiB
  response #2: chunk 256 KiB
  response #3: chunk 256 KiB
  ...
  response #400: chunk 256 KiB

Kích thước mỗi message: 256 KiB
Tổng dữ liệu: khoảng 100 MiB
~~~

Giới hạn message 1 MiB không có nghĩa tổng stream bị giới hạn 1 MiB. Ngược lại, nếu server gửi một response chứa cả file 100 MiB, client có thể phải tiếp nhận một message rất lớn dù đó là stream chỉ có một response.

**Mục tiêu thiết kế:** giới hạn kích thước từng message, giới hạn lượng dữ liệu đang chờ trong mỗi stream, và giới hạn số stream đồng thời để bộ nhớ có thể dự đoán được.

## 2. Một message lớn tiêu tốn bộ nhớ ở nhiều lớp

Khi server tạo một response protobuf, dữ liệu có thể tồn tại đồng thời ở nhiều dạng:

1. Object protobuf và các object con trong heap Java.
2. Payload byte được serialize hoặc buffer do marshaller/runtime quản lý.
3. Buffer của gRPC và transport HTTP/2.
4. Bản message đã deserialize ở client.
5. Buffer hoặc queue do ứng dụng client tạo ra để xử lý sau.

Số bản sao và thời gian giữ từng bản phụ thuộc implementation, transport và cách ứng dụng sử dụng message. Không nên giả định kích thước heap của một object bằng chính xác số byte protobuf trên mạng.

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu"] --> B["Protobuf object"]
    B --> C["Serialization buffer"]
    C --> D["gRPC / HTTP/2 buffers"]
    D --> E["Client protobuf object"]
    E --> F["Client processing queue"]
    F --> G["Xử lý / lưu kết quả"]
~~~

Nếu ứng dụng đọc toàn bộ kết quả vào `List<LargeResponse>` rồi mới xử lý, bộ nhớ tăng theo tổng số response, không còn theo kích thước một message. Nếu callback `onNext` chỉ thêm message vào một queue không giới hạn, client vẫn có thể hết bộ nhớ dù server gửi các message nhỏ.

## 3. Đặt giới hạn cho message ở đúng phía nhận

gRPC Java có cấu hình giới hạn **inbound message size**. Từ “inbound” rất quan trọng: giới hạn được đặt ở phía đang **nhận** message.

| Cấu hình | Giới hạn áp dụng cho |
|---|---|
| `ManagedChannelBuilder.maxInboundMessageSize(bytes)` | Message client nhận từ server, bao gồm response của server streaming |
| `ServerBuilder.maxInboundMessageSize(bytes)` hoặc builder transport tương ứng | Message server nhận từ client, ví dụ request |

Vì thế, cấu hình `maxInboundMessageSize` trên server không phải là cách đặt giới hạn trực tiếp cho response outbound mà server gửi. Đối với server streaming, client cần có inbound limit phù hợp; server đồng thời nên đặt giới hạn ứng dụng cho response trước khi phát.

Ví dụ client gRPC Java giới hạn mỗi inbound response ở 512 KiB:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .usePlaintext() // Chỉ dùng trong môi trường phát triển tin cậy.
        .maxInboundMessageSize(512 * 1024)
        .build();
~~~

Nếu client nhận một message vượt giới hạn, RPC sẽ kết thúc bằng lỗi thay vì tiếp tục nhận message đó. Mã status cụ thể nên được quan sát ở client và không nên tự suy luận chỉ từ một log phía server.

Ví dụ cấu hình inbound request ở server:

~~~java
Server server = NettyServerBuilder.forPort(9090)
        .maxInboundMessageSize(1024 * 1024)
        .addService(progressService)
        .build()
        .start();
~~~

Đoạn này giới hạn message **server nhận vào** ở 1 MiB. Nó hữu ích để bảo vệ server khỏi request quá lớn, nhưng không thay thế giới hạn response ở client. Trong ứng dụng Spring gRPC, cấu hình builder/transport phải được đặt qua extension point của starter đang dùng; không nên tự giả định tên property cấu hình giống nhau giữa các starter và phiên bản.

Không nên dựa vào giá trị mặc định của thư viện để làm chính sách bộ nhớ. Hãy chọn giới hạn tường minh, phù hợp với payload, số stream đồng thời và ngân sách bộ nhớ của service.

## 4. Giới hạn ở tầng ứng dụng trước khi gọi onNext

Transport limit bảo vệ phía nhận, nhưng server vẫn cần quy định kích thước response tối đa theo hợp đồng. Protobuf message Java có phương thức `getSerializedSize()` để ước lượng chính xác số byte serialized của message đó.

~~~java
private static final int MAX_RESPONSE_BYTES = 256 * 1024;

private void emit(
        FeedEvent event,
        StreamObserver<FeedEvent> responses) {

    int serializedBytes = event.getSerializedSize();
    if (serializedBytes > MAX_RESPONSE_BYTES) {
        responses.onError(Status.RESOURCE_EXHAUSTED
                .withDescription("Response exceeds the application size limit")
                .asRuntimeException());
        return;
    }

    responses.onNext(event);
}
~~~

Đây là giới hạn **do ứng dụng tự đặt** cho từng response. `getSerializedSize()` đo kích thước protobuf serialized, không đo toàn bộ heap, object graph, transport buffer hay queue. Nếu message đã được tạo từ một mảng byte rất lớn, kiểm tra sau khi tạo message không ngăn được phần bộ nhớ đã cấp phát.

Với payload lớn, hãy kiểm tra kích thước nguồn **trước khi tạo protobuf object**:

~~~java
if (sourcePayload.length > MAX_CHUNK_BYTES) {
    throw new IllegalArgumentException("Source payload exceeds chunk limit");
}

ByteString payload = ByteString.copyFrom(sourcePayload);
DataChunk chunk = DataChunk.newBuilder()
        .setPayload(payload)
        .build();
~~~

`ByteString.copyFrom` tạo dữ liệu bất biến nhưng cũng có thể tạo một bản sao. Nếu nguồn dữ liệu đã lớn, nên đọc theo từng đoạn có giới hạn thay vì tải toàn bộ vào `byte[]` rồi mới chia nhỏ. Chỉ chia nhỏ sau khi đã đọc cả file vào heap không giải quyết được peak memory lúc đọc.

## 5. Chia payload lớn thành các response nhỏ

Nếu một bản ghi hoặc file có thể lớn hơn giới hạn một message, hãy thiết kế chunk ở tầng ứng dụng. Mỗi response chứa một phần payload và thông tin nhận diện để client ghép lại:

~~~proto
syntax = "proto3";

package files.v1;

option java_multiple_files = true;
option java_package = "com.example.files.rpc";

service FileDownloadService {
  rpc Download(DownloadRequest) returns (stream DataChunk);
}

message DownloadRequest {
  string file_id = 1;
}

message DataChunk {
  string file_id = 1;
  uint64 sequence = 2;
  bytes payload = 3;
  bool last = 4;
}
~~~

Giả sử giới hạn ứng dụng cho một message là 256 KiB. Server đọc nguồn theo từng khối tối đa 256 KiB, gắn `file_id` và `sequence`, rồi phát từng `DataChunk`. Client ghi từng chunk vào file hoặc storage đích ngay khi nhận thay vì ghép tất cả vào một `ByteArrayOutputStream`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as gRPC server
    participant F as File source
    C->>S: Download(file_id)
    loop Mỗi chunk có kích thước giới hạn
        S->>F: Read next chunk
        F-->>S: bytes
        S-->>C: DataChunk(sequence, payload)
        Note over C: Ghi chunk xuống storage
    end
    S-->>C: onCompleted()
~~~

Chunking cần xác định rõ:

- Kích thước chunk tối đa và cách xử lý chunk cuối ngắn hơn.
- `sequence` bắt đầu từ đâu và có tăng liên tục không.
- Cách xác định kết thúc: `last`, số chunk đã biết, hoặc terminal `onCompleted`.
- Cách kiểm tra toàn vẹn: checksum theo chunk hoặc checksum toàn file.
- Cách tiếp tục khi lỗi: cursor/sequence, file tạm và quy tắc ghi đè/ghép nối.

Không nhất thiết phải có cả `last` lẫn `onCompleted` nếu hợp đồng không cần cả hai. `onCompleted` biểu thị RPC kết thúc thành công; `last` là dữ liệu trong payload và có thể hữu ích khi giao thức cần mô tả phần cuối rõ ràng. Nếu stream lỗi sau chunk #8, client không được coi file hoàn chỉnh chỉ vì đã nhận một số chunk.

Với file rất lớn hoặc nội dung cần lưu bền, cân nhắc lưu file trong object storage và dùng gRPC để trả metadata, URL có kiểm soát hoặc các chunk nhỏ. gRPC streaming không bắt buộc phải trở thành kênh truyền mọi byte của một file rất lớn.

## 6. Giới hạn bộ nhớ của queue và số stream đồng thời

Giới hạn message đơn lẻ chưa đủ. Hãy lập ngân sách bộ nhớ theo số stream đang mở và số message có thể nằm chờ.

Một mô hình ước lượng đơn giản:

\[
M \approx S \times (B + Q \times B_q + W) + M_{\text{shared}}
\]

Trong đó:

- \(S\): số stream đồng thời.
- \(B\): bộ nhớ ước lượng cho message đang được xử lý trên mỗi stream.
- \(Q\): số message tối đa trong queue mỗi stream.
- \(B_q\): kích thước trung bình của message trong queue.
- \(W\): bộ nhớ công việc phụ trên mỗi stream.
- \(M_{\text{shared}}\): buffer/cache dùng chung và chi phí nền.

Ví dụ giả định 200 stream đồng thời, mỗi stream có một message đang xử lý và queue tối đa bốn message, tất cả đều khoảng 256 KiB. Riêng phần payload ước lượng là:

~~~text
200 streams × (1 + 4) messages × 256 KiB
≈ 250 MiB
~~~

Con số này chưa tính object overhead, bản sao khi serialize/deserialize, queue node, TLS/transport buffers, cache và các request khác. Nó cho thấy chỉ một queue bốn message trên mỗi stream đã có thể tiêu tốn đáng kể bộ nhớ khi số stream tăng.

**Giới hạn queue theo cả số lượng và số byte.** Queue 100 phần tử có thể an toàn với message 1 KiB nhưng rất nguy hiểm nếu mỗi message gần 10 MiB. Một weighted queue có thể từ chối thêm message khi tổng byte vượt ngân sách.

Khi queue đầy, chính sách phải rõ:

| Loại dữ liệu | Chính sách có thể chọn |
|---|---|
| Event bắt buộc giữ đầy đủ | Tạm dừng upstream nếu có thể, ghi bền để replay, hoặc kết thúc RPC có status phù hợp |
| Trạng thái chỉ cần giá trị mới nhất | Gộp/coalesce các cập nhật cũ theo hợp đồng |
| Telemetry best-effort | Sampling hoặc bỏ dữ liệu theo chính sách công bố |
| Tác vụ vượt quota | Từ chối thêm tải, giới hạn stream đồng thời hoặc trả `RESOURCE_EXHAUSTED` |

Không để queue tăng vô hạn với hy vọng garbage collector sẽ xử lý. GC không thể giải phóng message còn được tham chiếu trong queue.

## 7. Kết hợp flow control với giới hạn bộ đệm

Server gRPC Java có thể dùng `ServerCallStreamObserver.isReady()` và `setOnReadyHandler(...)` để biết khi đường ghi có thể tiếp nhận thêm dữ liệu. Điều này giúp sender không liên tục đẩy message khi transport chưa sẵn sàng:

~~~java
ServerCallStreamObserver<DataChunk> out =
        (ServerCallStreamObserver<DataChunk>) responseObserver;

out.setOnReadyHandler(() -> scheduleDrain());

private void drain() {
    while (!queue.isEmpty() && out.isReady() && !out.isCancelled()) {
        out.onNext(queue.remove());
    }
}
~~~

Đoạn code chỉ minh họa ý tưởng; `queue` phải có giới hạn và `scheduleDrain()` phải điều phối sender tuần tự. Không gọi `onNext` đồng thời từ producer và callback readiness. Khi queue đầy, phải điều tiết producer hoặc áp dụng chính sách dữ liệu; `isReady() == false` không tự dừng một broker hay thread đang tạo event.

Ở client, callback `onNext` mặc định có thể tiếp tục được gọi trong khi ứng dụng chuyển message sang một queue riêng. Nếu consumer xử lý chậm, queue đó vẫn tăng. Khi cần liên kết tốc độ nhận với tốc độ xử lý, có thể dùng `ClientResponseObserver` và manual inbound flow control:

~~~java
stream.disableAutoRequestWithInitial(1);

@Override
public void onNext(DataChunk chunk) {
    writeChunkAndFinish(chunk, error -> {
        if (error == null) {
            control.request(1); // Chỉ yêu cầu thêm sau khi xử lý xong.
        } else {
            control.cancel("Cannot persist chunk", error);
        }
    });
}
~~~

Đây là pseudocode: `control` là `ClientCallStreamObserver` lưu trong `beforeStart`, còn `writeChunkAndFinish` là hàm bất đồng bộ của ứng dụng. Không gọi `request(1)` ngay sau khi enqueue vào một queue không giới hạn; hãy trả demand sau khi công việc thật sự hoàn thành hoặc sau khi có chỗ trống trong queue có giới hạn.

Flow control và giới hạn bộ nhớ bổ sung cho nhau:

- Flow control điều tiết lượng dữ liệu được chuyển qua transport.
- Manual demand giới hạn số response được giao tới callback client.
- Queue có giới hạn bảo vệ bộ nhớ ứng dụng.
- Producer backpressure hoặc storage/replay kiểm soát dữ liệu ở nguồn.

## 8. Compression không thay thế giới hạn message

gRPC có thể nén message để giảm lượng byte truyền qua mạng. Tuy nhiên, không nên coi compression là giải pháp cho response quá lớn:

- Server và client vẫn phải tạo/giải nén nội dung để xử lý.
- Payload có thể khó nén hoặc đã được nén (ảnh, video, file archive).
- Nén làm tăng chi phí CPU và có thể tạo peak memory khi xử lý.
- Kích thước dữ liệu sau giải nén và kích thước protobuf logic vẫn cần được kiểm soát.

Compression phù hợp khi payload có tính lặp và lợi ích băng thông đáng kể. Nó không thay thế giới hạn kích thước ứng dụng, giới hạn inbound message, chunking hoặc queue có giới hạn.

## 9. Kiểm thử kích thước response và bộ nhớ

Nên kiểm tra riêng giới hạn message, giới hạn tổng stream và giới hạn queue:

| Test case | Kết quả cần xác minh |
|---|---|
| Response nhỏ hơn giới hạn | Client nhận bình thường |
| Response đúng sát giới hạn ứng dụng | Được chấp nhận theo chính sách kích thước |
| Response lớn hơn giới hạn ứng dụng | Server không gọi `onNext`; kết thúc bằng status đã quy định |
| Response vượt inbound limit của client | Client không tiếp nhận message quá lớn và RPC kết thúc lỗi |
| Nhiều response nhỏ, tổng stream lớn | Stream vẫn chạy nếu từng message hợp lệ và tài nguyên được xử lý dần |
| Client chậm | Queue không vượt giới hạn byte/số phần tử |
| Nhiều stream đồng thời | Tổng bộ nhớ nằm trong ngân sách thử tải |
| Chunk cuối ngắn hơn chunk chuẩn | Client ghi đúng kích thước và kết thúc file |
| Stream lỗi giữa các chunk | File chưa bị đánh dấu hoàn chỉnh; resume theo sequence nếu được hỗ trợ |
| Payload khó nén | CPU và memory không tăng ngoài ngân sách khi bật compression |

Test in-process hữu ích để xác minh logic chia chunk, thứ tự và status. Để đo memory, throughput và tác động của transport, cần bài kiểm thử tải có nhiều stream đồng thời, payload với kích thước phân bố thực tế, client đọc nhanh/chậm và quan sát heap/queue. Không chỉ đo số byte trên mạng rồi kết luận heap an toàn.

## 10. Checklist thiết kế

- [ ] Đã đặt giới hạn byte cho **mỗi response** ở tầng ứng dụng.
- [ ] Client đặt inbound message limit phù hợp với kích thước response tối đa.
- [ ] Server đặt inbound request limit riêng; không nhầm nó với giới hạn response outbound.
- [ ] Payload lớn được chia thành chunk trước khi tải toàn bộ vào heap.
- [ ] Queue được giới hạn theo cả số phần tử và tổng byte.
- [ ] Đã giới hạn số stream đồng thời và tính ngân sách memory theo tải.
- [ ] Producer có thể dừng/chậm lại hoặc có cơ chế lưu bền khi consumer chậm.
- [ ] Client không tích lũy mọi response trong một collection nếu không cần.
- [ ] Có sequence/checksum và chính sách resume nếu dữ liệu phải được truyền đầy đủ.
- [ ] Đã kiểm thử response sát/vượt giới hạn, client chậm và nhiều stream đồng thời.

**Ghi nhớ:** Server streaming giảm nhu cầu gom toàn bộ kết quả vào một response, nhưng không tự giới hạn bộ nhớ. Hãy giới hạn kích thước **từng message**, chia payload lớn thành chunk, giới hạn queue theo byte và số phần tử, kiểm soát số stream đồng thời và điều tiết producer theo khả năng tiêu thụ. Cấu hình inbound message size phải đặt ở đúng phía nhận; giới hạn ở server cho request không tự giới hạn response mà client nhận.
