# max outbound message size

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích max outbound message size giới hạn kích thước của một gRPC message mà endpoint gửi đi.
- Phân biệt giới hạn outbound ở sender với max inbound message size ở receiver.
- Cấu hình giới hạn gửi cho client call bằng API grpc-java phù hợp với phiên bản.
- Xác định giới hạn nhận response của client và request của server.
- Kiểm tra kích thước protobuf trước khi gửi hoặc phát response.
- Phân biệt kích thước message với HTTP/2 frame, compression và tổng dữ liệu streaming.
- Thiết kế chunking, quota và kiểm thử boundary để tránh gửi message quá lớn.

## 1. max outbound message size là gì?

Trong **SPRING_GRPC**, một RPC gửi request hoặc response dưới dạng gRPC message được serialize từ Protocol Buffers. Một message có thể chứa bytes, chuỗi, nested message hoặc collection. Nếu endpoint tạo message quá lớn, việc serialize, giữ buffer và truyền dữ liệu có thể làm tăng memory, CPU, latency và áp lực lên network.

**max outbound message size** là giới hạn kích thước tối đa của một message mà sender được phép gửi trên một RPC. Nó kiểm soát chiều dữ liệu đi ra khỏi endpoint hiện tại. Khái niệm này cần được hiểu cùng với giới hạn nhận ở đầu bên kia:

- **Outbound limit:** giới hạn message do sender tạo và gửi.
- **Inbound limit:** giới hạn message mà receiver chấp nhận nhận vào.

Hai giới hạn có liên quan nhưng không đồng nhất. Cấu hình outbound ở client không tự tăng khả năng nhận của server; cấu hình inbound ở client không hạn chế request client gửi đi.

Ví dụ, client gửi một request lớn tới server. Client là sender của request, server là receiver. Khi server trả response, server trở thành sender và client là receiver. Mỗi chiều có thể có giới hạn khác nhau.

## 2. Hiểu đúng giới hạn theo chiều request và response

| Message | Sender | Receiver | Giới hạn cần quan tâm |
| --- | --- | --- | --- |
| Unary request | gRPC client | gRPC server | Client outbound và server inbound |
| Unary response | gRPC server | gRPC client | Server-side send behavior và client inbound |
| Client-streaming request | gRPC client | gRPC server | Client outbound từng message và server inbound từng message |
| Server-streaming response | gRPC server | gRPC client | Server-side send behavior và client inbound từng message |
| Bidirectional request | gRPC client | gRPC server | Client outbound và server inbound |
| Bidirectional response | gRPC server | gRPC client | Server-side send behavior và client inbound |

Trong grpc-java, receive limit thường được cấu hình trên endpoint nhận dữ liệu:

- Server inbound limit giới hạn request mà server nhận từ client.
- Client inbound limit giới hạn response mà client nhận từ server.

Một số phiên bản grpc-java cung cấp per-call outbound limit qua CallOptions và generated stub, ví dụ **withMaxOutboundMessageSize(int)**. API cụ thể cần khớp phiên bản grpc-java mà dự án sử dụng. Nếu phiên bản không cung cấp per-call outbound option, có thể cần giới hạn ở application trước khi gửi và dựa vào receive limit được cấu hình ở receiver.

Không suy ra rằng mọi server builder hoặc Spring gRPC starter đều có một property tên max-outbound-message-size. Cấu hình nhận và cấu hình gửi có thể nằm ở các API khác nhau. Kiểm tra API của transport/starter đang dùng và xác minh bằng integration test.

## 3. Cấu hình outbound limit cho client call

Khi grpc-java version cung cấp API outbound option trên generated stub, có thể đặt giới hạn cho các message client gửi trong call:

~~~java
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

ManagedChannel channel = NettyChannelBuilder
        .forAddress("orders.internal", 9090)
        .maxInboundMessageSize(4 * 1024 * 1024)
        .build();

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel)
                .withMaxOutboundMessageSize(2 * 1024 * 1024);
~~~

Trong ví dụ:

- maxInboundMessageSize trên channel giới hạn response client nhận từ server.
- withMaxOutboundMessageSize trên stub giới hạn message client gửi đi trong call, nếu API có trong phiên bản đang dùng.
- Hai con số độc lập vì request và response có thể có kích thước khác nhau.

Không nhầm cấu hình channel inbound với outbound request. Nếu request lớn hơn giới hạn nhận của server, server vẫn có thể từ chối dù client outbound option cho phép gửi message lớn hơn. Vì vậy, contract phải thống nhất giữa giới hạn gửi ở client và giới hạn nhận ở server.

Nếu ứng dụng tạo stub qua Spring bean hoặc factory, đặt CallOptions ở nơi tạo stub phù hợp với từng loại RPC. Với API yêu cầu nhiều nhóm giới hạn, có thể tạo factory riêng cho upload, batch và request thông thường thay vì dùng một ngưỡng lớn cho mọi method.

## 4. Server gửi response: client inbound limit là hàng rào phía nhận

Khi server gửi response, client là receiver. Client có thể cấu hình receive limit trên channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress("orders.internal", 9090)
        .maxInboundMessageSize(8 * 1024 * 1024)
        .build();
~~~

Giới hạn này bảo vệ client khỏi response vượt ngưỡng. Nó không phải một cấu hình outbound trên server.

Ở phía server, application có thể kiểm tra kích thước serialized response trước khi gọi onNext:

~~~java
private void sendResponse(
        GetReportResponse response,
        StreamObserver<GetReportResponse> observer) {

    int serializedBytes = response.getSerializedSize();

    if (serializedBytes > MAX_REPORT_BYTES) {
        observer.onError(
                Status.RESOURCE_EXHAUSTED
                        .withDescription("Response exceeds the message-size contract")
                        .asRuntimeException());
        return;
    }

    observer.onNext(response);
    observer.onCompleted();
}
~~~

Đây là kiểm tra ở application boundary, hữu ích để trả lỗi có chủ đích trước khi gửi. Nó không thay thế receive limit của client: một client khác có thể bỏ qua quy ước của ứng dụng hoặc gọi bằng raw gRPC client. Receiver vẫn phải tự bảo vệ.

Nếu server cần gửi nhiều response lớn, cân nhắc server-streaming với mỗi response nhỏ hơn thay vì một response chứa toàn bộ kết quả. Client vẫn phải có inbound limit phù hợp cho từng response message.

## 5. Kiểm tra kích thước protobuf trước khi gửi

Generated protobuf message cung cấp getSerializedSize() để lấy kích thước serialized payload theo byte:

~~~java
int serializedBytes = request.getSerializedSize();

if (serializedBytes > MAX_REQUEST_BYTES) {
    throw Status.RESOURCE_EXHAUSTED
            .withDescription("Request exceeds the message-size contract")
            .asRuntimeException();
}

blockingStub.submitOrder(request);
~~~

Kiểm tra này giúp ứng dụng từ chối sớm trước khi gọi transport và cung cấp thông báo phù hợp với API contract. Tuy nhiên, đây không phải ranh giới bảo mật duy nhất. Caller có thể dùng client khác và bỏ qua validation. Server inbound limit vẫn phải được cấu hình ở server.

Với response, server cũng có thể kiểm tra getSerializedSize() trước khi gọi onNext. Với client-streaming, kiểm tra từng message trước khi gửi; với server-streaming, kiểm tra từng response trước khi phát.

Kích thước serialized protobuf không nhất thiết bằng toàn bộ số byte trên wire. gRPC có framing, compression và HTTP/2 transport. Hãy xem getSerializedSize() là phép đo payload protobuf hữu ích cho contract và kiểm thử, không phải phép đo HTTP/2 frame.

## 6. Outbound limit, inbound limit và HTTP/2 framing

Một gRPC message được đóng khung trong gRPC message envelope và truyền qua HTTP/2 DATA frame. Một message có thể đi qua nhiều frame; một frame không tương đương một protobuf message.

Các giới hạn có ý nghĩa khác nhau:

- **Outbound message limit:** sender giới hạn message mà nó tạo để gửi.
- **Inbound message limit:** receiver giới hạn message mà nó chấp nhận.
- **HTTP/2 frame size:** giới hạn tầng transport của frame, không phải kích thước protobuf message.
- **Metadata limit:** giới hạn metadata/header, tách biệt với message body.
- **Stream quota:** giới hạn tổng bytes hoặc số message trong một RPC dài.

Không dùng HTTP/2 frame size để suy ra max outbound message size. Không giả định một message 5 MiB sẽ nằm trong một frame 5 MiB; transport có thể chia message thành nhiều frame.

Khi client và server có cấu hình không tương thích, message có thể được sender cho phép nhưng receiver từ chối. Đặt outbound limit ở sender bằng hoặc thấp hơn receive limit đã công bố của receiver để lỗi được phát hiện sớm, đồng thời giữ receiver limit làm hàng rào cuối cùng.

## 7. Compression và kích thước message

Compression giảm số byte truyền trên network, nhưng không có nghĩa message lớn trở nên miễn phí. Receiver cần giải nén và parse nội dung; payload sau giải nén có thể lớn hơn nhiều so với dữ liệu trên wire.

Khi đánh giá outbound limit:

- Kiểm tra kích thước serialized protobuf mà sender tạo.
- Xác định outbound limit của grpc-java được áp dụng ở giai đoạn nào theo phiên bản/transport.
- Không dựa vào kích thước sau nén để thay thế giới hạn payload.
- Ở receiver, cấu hình inbound limit và theo dõi memory sau giải nén.
- Thử payload nén có tỷ lệ nở lớn trong test có kiểm soát.

Compression có thể giảm bandwidth nhưng vẫn cần CPU để nén/giải nén và memory để giữ protobuf object. Không tăng outbound limit chỉ vì bật gzip.

## 8. Streaming: giới hạn từng message không giới hạn tổng stream

Với streaming RPC, outbound message limit thường được áp dụng cho từng message gửi đi. Một stream có thể gửi hàng nghìn message hợp lệ về kích thước nhưng tổng dữ liệu vẫn rất lớn.

Cần phối hợp nhiều giới hạn:

| Giới hạn | Mục đích |
| --- | --- |
| **Max outbound message size** | Kích thước tối đa mỗi message sender gửi |
| **Receiver max inbound message size** | Kích thước tối đa mỗi message receiver nhận |
| **Maximum messages per stream** | Số message tối đa trong một RPC |
| **Total bytes per stream** | Tổng dữ liệu truyền trong stream |
| **Maximum stream lifetime** | Thời gian stream được phép tồn tại |
| **Concurrent stream limit** | Số stream đồng thời theo server/tenant |
| **Rate limit** | Tốc độ gửi message hoặc byte |
| **Flow control/backpressure** | Điều tiết producer theo khả năng consumer |

Bộ đếm tổng byte nên dùng kiểu số đủ lớn như long và cập nhật an toàn khi nhiều callback có thể chạy đồng thời. Quota theo tenant cần được cập nhật nguyên tử để nhiều stream không cùng vượt hạn mức.

Khi stream vượt quota tổng, service có thể kết thúc bằng RESOURCE_EXHAUSTED theo contract. Không dùng max outbound message size để thay thế quota tổng hoặc rate limit.

## 9. Dữ liệu lớn nên chia chunk

Nếu một response hoặc request cần chứa file lớn, batch lớn hoặc tập dữ liệu lớn, cân nhắc streaming theo chunk thay vì gửi một message duy nhất.

Ví dụ contract upload/download theo chunk:

~~~proto
message DataChunk {
  string transfer_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

message TransferResult {
  string transfer_id = 1;
  int64 total_bytes = 2;
}

service TransferService {
  rpc Upload(stream DataChunk) returns (TransferResult);
  rpc Download(DownloadRequest) returns (stream DataChunk);
}
~~~

Mỗi chunk có kích thước giới hạn rõ ràng, thấp hơn outbound và inbound limit của hai phía. Ngoài ra cần:

1. Giới hạn tổng byte và số chunk.
2. Kiểm tra sequence để phát hiện thiếu hoặc lặp chunk.
3. Xác minh quyền truy cập transfer ID và tenant.
4. Dùng checksum để xác minh nội dung sau khi ghép.
5. Hỗ trợ retry/resume bằng transfer ID và sequence.
6. Cleanup dữ liệu tạm khi cancel hoặc hết hạn.
7. Không ghép toàn bộ dữ liệu vào một byte array lớn trong heap nếu có thể stream trực tiếp tới storage.

Chunking cải thiện memory, progress và khả năng resume, nhưng không tự giới hạn tổng dữ liệu. Cần quota và deadline riêng.

## 10. Chọn ngưỡng outbound theo contract và tài nguyên

Không có một ngưỡng phù hợp cho mọi method. Một response chi tiết order có thể chỉ cần vài KiB; export report có thể cần nhiều MiB; dữ liệu file nên dùng chunk.

Khi chọn outbound limit, cân nhắc:

- Kích thước payload hợp lệ lớn nhất theo API contract.
- Receive limit của endpoint đối diện.
- Heap và object overhead sau serialize/parse.
- Số RPC đồng thời và số stream đang mở.
- Compression, CPU và network bandwidth.
- Deadline và thời gian serialize.
- Khả năng tương thích của client cũ.
- Quota theo tenant và giới hạn deployment.

Không tính concurrency bằng phép chia heap cho message size đơn thuần. Protobuf object, byte array, buffer, copy khi serialize, domain object và response có thể làm memory thực tế lớn hơn payload. Đo bằng load test với message gần ngưỡng và số RPC đồng thời gần production.

Nếu thay đổi limit, công bố rõ giới hạn mới cho client. Tăng receive limit phía server mà không xem xét memory hoặc giảm outbound limit phía client có thể làm một số client cũ thất bại.

## 11. Status và xử lý lỗi khi message quá lớn

Nếu outbound option của sender từ chối message vượt ngưỡng, hoặc receiver inbound limit từ chối message, RPC thường kết thúc với RESOURCE_EXHAUSTED. Chi tiết thời điểm phát hiện và nội dung description có thể phụ thuộc grpc-java version và transport.

Phân biệt các tình huống:

| Nguyên nhân | Status/hành vi thường gặp | Hướng xử lý |
| --- | --- | --- |
| Sender outbound limit bị vượt | Thường RESOURCE_EXHAUSTED ở call | Giảm message hoặc chia chunk |
| Receiver inbound limit bị vượt | Thường RESOURCE_EXHAUSTED ở receiver | Thỏa receive contract hoặc điều chỉnh có kiểm soát |
| Field vi phạm quy tắc API | INVALID_ARGUMENT hoặc lỗi contract | Sửa input/schema |
| Tổng stream vượt quota | RESOURCE_EXHAUSTED | Giảm tổng dữ liệu hoặc xin quota phù hợp |
| Caller thiếu quyền gửi dữ liệu | PERMISSION_DENIED | Thực hiện quy trình cấp quyền |
| Deadline hết khi serialize/truyền | DEADLINE_EXCEEDED | Tối ưu payload hoặc timeout theo contract |

Không parse status description tự do để quyết định logic client; dùng Status.Code và reason code ổn định nếu API cung cấp. Không retry nguyên payload đã vượt limit vì retry không làm payload nhỏ hơn. Với mutation hoặc upload, dùng idempotency/sequence để xử lý trường hợp kết nối mất sau khi một phần dữ liệu đã được nhận.

## 12. Quan sát outbound message size

Theo dõi kích thước message gửi theo method và loại RPC:

- Serialized size p50/p95/p99 và tỷ lệ gần ngưỡng.
- Số call kết thúc bằng RESOURCE_EXHAUSTED.
- Số message và tổng byte mỗi stream.
- Thời gian serialize, compression và truyền.
- Heap allocation, GC pause và CPU.
- Số stream đồng thời và thời lượng stream.
- Số lần client retry/resume upload.

Không ghi toàn bộ payload hoặc bytes nhạy cảm vào log. Chỉ ghi method, serialized size, status, trace ID và tenant identifier đã được xử lý theo chính sách. Tránh dùng request ID hoặc tenant ID cardinality cao làm metric label.

Nếu sender thường xuyên chạm ngưỡng, xem lại contract và schema trước khi tăng limit. Một response chứa hàng chục nghìn record có thể nên được phân trang hoặc chuyển sang streaming thay vì cho phép message lớn hơn.

## 13. Kiểm thử outbound và receiver boundary

Test phải kiểm tra cả sender lẫn receiver vì hai giới hạn bảo vệ hai phía khác nhau.

Giả sử contract đặt outbound tối đa 1 MiB và receiver inbound tối đa 1 MiB:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Client gửi request nhỏ hơn limit | Server nhận và xử lý |
| Client tạo request lớn hơn outbound option | Client call bị từ chối theo behavior của grpc-java version |
| Client gửi request được outbound option cho phép nhưng lớn hơn server inbound | Server từ chối nhận |
| Server trả response nhỏ hơn client inbound limit | Client nhận response |
| Server trả response lớn hơn client inbound limit | Client từ chối nhận |
| Nhiều message nhỏ vượt quota tổng stream | Application kết thúc stream theo quota |
| Chunk nằm trong giới hạn nhưng tổng transfer vượt quota | Transfer bị từ chối và cleanup |
| Compression bật | Boundary vẫn được enforce theo semantics của runtime |

Dùng generated protobuf message và getSerializedSize() để tạo payload dưới, sát và vượt ngưỡng. Độ dài bytes field không bằng serialized size toàn message vì protobuf còn có tag và length prefix.

Ví dụ test payload size:

~~~java
DataRequest request = DataRequest.newBuilder()
        .setPayload(ByteString.copyFrom(payload))
        .build();

int serializedBytes = request.getSerializedSize();
assertTrue(serializedBytes > 0);
~~~

Không chỉ test application precheck. Dùng grpc-java in-process hoặc transport integration test để xác minh outbound option và receiver inbound limit được thực thi bởi runtime. Với Spring gRPC, khởi động cấu hình channel/server thực tế trong test để xác minh các customizer/bean đã đặt đúng receive limit.

Các assertion quan trọng:

1. Sender không phát message vượt outbound limit đã cấu hình.
2. Receiver từ chối message vượt inbound limit.
3. Server response lớn bị client receive limit chặn.
4. Service handler không xử lý message bị transport từ chối.
5. Stream quota tổng hoạt động độc lập với message limit.
6. Compression không làm vô hiệu resource guard.
7. Status code được kiểm tra mà không phụ thuộc description.

## 14. Lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Nhầm outbound với inbound | Cấu hình sai chiều dữ liệu | Xác định sender và receiver cho từng RPC |
| Tưởng channel inbound limit giới hạn request gửi đi | Request vẫn có thể lớn hơn server nhận được | Cấu hình sender outbound nếu API hỗ trợ và server inbound |
| Cho rằng server builder luôn có outbound property | Dùng property/API không tồn tại trong transport | Kiểm tra API version; dùng receiver limit và application guard |
| Chỉ kiểm tra getSerializedSize ở client | Raw client bỏ qua validation | Enforce tại transport receiver |
| Chỉ giới hạn từng message trong stream | Tổng stream vẫn có thể rất lớn | Thêm total bytes/messages quota |
| Dùng compression để cho phép message lớn hơn | Heap/CPU sau giải nén tăng | Giới hạn payload và theo dõi decompression |
| Gửi một response khổng lồ | Memory, latency và retry kém | Pagination hoặc streaming chunk |
| Retry payload vượt limit | Lặp lỗi không thể tự hết | Giảm payload hoặc thay đổi contract |
| Chỉ test stub mà không test server thật | Bỏ sót receive limit/wiring | Integration test qua gRPC runtime và Spring configuration |

## 15. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Đặt client outbound limit theo API grpc-java version đang dùng nếu generated stub hỗ trợ.
2. Cấu hình server inbound limit để bảo vệ request nhận từ client.
3. Cấu hình client inbound limit để bảo vệ response nhận từ server.
4. Tạo protobuf request/response có bytes field và đo getSerializedSize().
5. Viết test payload dưới, sát và vượt outbound option; lặp lại với receiver inbound limit.
6. Tạo server-streaming hoặc client-streaming theo chunk, giới hạn mỗi chunk và tổng transfer.
7. Thêm quota stream, deadline, cancellation và cleanup khi vượt giới hạn.
8. Viết Spring integration test xác minh channel/server builder được cấu hình đúng chiều.

### Câu hỏi tự kiểm tra

**1. max outbound message size giới hạn điều gì?**  
Kích thước tối đa của một gRPC message mà sender được phép gửi trong một call.

**2. Outbound limit có thay thế inbound limit của receiver không?**  
Không. Sender limit kiểm soát message gửi đi; receiver inbound limit là hàng rào cuối cùng khi nhận.

**3. Client gửi request thì ai là receiver?**  
Server. Server inbound message limit kiểm soát request mà server chấp nhận.

**4. Server gửi response thì ai là receiver?**  
Client. Client inbound message limit kiểm soát response client chấp nhận.

**5. getSerializedSize() có đo HTTP/2 frame không?**  
Không. Nó đo serialized protobuf payload; gRPC framing và HTTP/2 transport có cấu trúc riêng.

**6. Giới hạn từng message có giới hạn tổng streaming không?**  
Không. Cần thêm total bytes, message count, lifetime, concurrency và rate quota.

**7. Status nào thường gặp khi outbound/inbound message limit bị vượt?**  
Thường là RESOURCE_EXHAUSTED; behavior chi tiết phụ thuộc grpc-java version và transport.

**8. Vì sao cần integration test qua runtime?**  
Để xác minh outbound option, receiver inbound limit và Spring wiring thực sự được áp dụng, không chỉ kiểm tra application precheck.

## Tổng kết

max outbound message size giới hạn kích thước của từng gRPC message do sender gửi. Cần xác định đúng chiều request/response: client gửi request tới server thì server inbound limit bảo vệ phía nhận; server gửi response tới client thì client inbound limit bảo vệ phía nhận. grpc-java version có thể cung cấp per-call outbound option trên CallOptions/generated stub; hãy xác minh API thực tế thay vì giả định mọi server builder có outbound property. Kết hợp giới hạn gửi, receive limit, kiểm tra serialized payload, chunking và quota tổng stream để kiểm soát memory, latency và resource exhaustion. Integration test phải kiểm tra cả sender lẫn receiver trong cấu hình Spring thực tế.

