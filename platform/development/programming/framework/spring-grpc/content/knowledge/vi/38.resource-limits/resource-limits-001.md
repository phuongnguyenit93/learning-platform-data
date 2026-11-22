# max inbound message size

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích max inbound message size giới hạn kích thước của từng gRPC message nhận vào.
- Phân biệt giới hạn ở server với giới hạn ở client và biết cấu hình đúng chiều dữ liệu.
- Đặt giới hạn bằng byte trong grpc-java builder và tích hợp với server do Spring quản lý.
- Phân biệt protobuf payload, gRPC message, HTTP/2 frame và tổng dữ liệu của một stream.
- Đánh giá ảnh hưởng của compression, message lớn và các kiểu streaming.
- Thiết kế chunking, quota và validation cho dữ liệu lớn.
- Kiểm thử message nằm dưới, bằng và vượt ngưỡng để xác minh hành vi ở transport.

## 1. max inbound message size là gì?

Trong **SPRING_GRPC**, một RPC truyền dữ liệu dưới dạng các gRPC message được serialize từ protobuf. Một message có thể chứa chuỗi, bytes, nested message hoặc collection. Nếu server nhận một message quá lớn, việc parse và giữ dữ liệu trong bộ nhớ có thể làm tăng heap, garbage collection và thời gian xử lý; nhiều request lớn đồng thời còn có thể gây cạn tài nguyên.

**max inbound message size** là giới hạn kích thước tối đa của một message mà một endpoint chấp nhận nhận vào. Đây là giới hạn ở tầng gRPC runtime, được kiểm tra khi message được deframe/đọc trước khi service handler xử lý nội dung. Nó tạo một hàng rào sớm để từ chối message vượt ngưỡng.

Cần phân biệt hai hướng:

- **Server inbound limit:** giới hạn message client gửi tới server. Đây thường là giới hạn quan trọng đối với request API.
- **Client inbound limit:** giới hạn message server gửi về client. Nó bảo vệ ứng dụng client khỏi response quá lớn.

Giới hạn của một phía không tự động cấu hình phía còn lại. Nếu client có thể gửi request 8 MiB nhưng server chỉ chấp nhận 2 MiB, client cần biết contract này để tránh gửi dữ liệu chắc chắn bị từ chối. Nếu server trả response lớn, client cũng cần giới hạn inbound phù hợp.

## 2. Cấu hình giới hạn ở server và client

Trong grpc-java, builder cung cấp phương thức maxInboundMessageSize(int) với đơn vị là **byte**. Ví dụ đặt giới hạn server ở 8 MiB:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;

public final class GrpcServerFactory {

    private static final int MAX_INBOUND_BYTES = 8 * 1024 * 1024;

    public Server createServer(int port) {
        return NettyServerBuilder.forPort(port)
                .maxInboundMessageSize(MAX_INBOUND_BYTES)
                .build();
    }
}
~~~

Con số 8 MiB là ví dụ. Chọn ngưỡng theo kích thước request hợp lệ lớn nhất, số request đồng thời, heap/container limit và độ lớn dữ liệu sau giải nén. Không tăng giới hạn chỉ để làm một request bất thường thành công.

Ở client, cấu hình giới hạn response nhận từ server:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

public final class GrpcChannelFactory {

    private static final int MAX_RESPONSE_BYTES = 12 * 1024 * 1024;

    public ManagedChannel createChannel(String host, int port) {
        return NettyChannelBuilder.forAddress(host, port)
                .maxInboundMessageSize(MAX_RESPONSE_BYTES)
                .build();
    }
}
~~~

Ở đây, MAX_RESPONSE_BYTES áp dụng cho message đi từ server về client. Nó không làm server chấp nhận request lớn hơn.

Với transport hoặc builder khác, API cụ thể có thể nằm trên builder tương ứng. Hãy cấu hình builder thực sự tạo server/channel. Trong ứng dụng Spring gRPC, server thường được starter quản lý; áp dụng giới hạn qua server builder customizer/configurer extension point mà phiên bản starter đang hỗ trợ. Tên property hoặc hook có thể khác giữa các starter và phiên bản, vì vậy không sao chép một property không được phiên bản dự án công bố. Xác minh cấu hình bằng integration test trên server thực tế.

Giá trị mặc định có thể phụ thuộc phiên bản grpc-java và transport. Hãy đặt rõ giới hạn của ứng dụng thay vì xem default của thư viện là contract ổn định.

## 3. Giới hạn áp dụng cho một gRPC message, không phải HTTP/2 frame

Một gRPC message được truyền bên trong HTTP/2 DATA frame. Một message có thể được chia qua nhiều frame; ranh giới frame của HTTP/2 không phải ranh giới message của protobuf.

Vì vậy:

- maxInboundMessageSize giới hạn một gRPC message đã được nhận/giải mã theo cơ chế của runtime.
- Nó không phải giới hạn kích thước của một HTTP/2 frame.
- Nó không phải tổng số byte của toàn bộ RPC hoặc stream.
- Một stream có thể chứa nhiều message, mỗi message đều dưới ngưỡng nhưng tổng dữ liệu vẫn rất lớn.
- Metadata/headers là phần riêng của giao thức; không dùng message-size limit để thay thế giới hạn metadata hoặc giới hạn số lượng header.

Ví dụ, một client-streaming RPC gửi 10.000 message, mỗi message 256 KiB. Mỗi message có thể nằm dưới giới hạn 1 MiB, nhưng tổng dữ liệu của stream xấp xỉ 2,5 GiB. Vì vậy, giới hạn message đơn lẻ không thay thế quota tổng cho stream, giới hạn số message, rate limit hoặc deadline.

### 3.1. Protobuf payload và kích thước message

Với generated protobuf message, getSerializedSize() trả về kích thước serialized protobuf payload theo byte:

~~~java
int payloadBytes = request.getSerializedSize();

if (payloadBytes > MAX_INBOUND_BYTES) {
    throw new IllegalArgumentException("Request is too large");
}
~~~

Đây là cách hữu ích để client kiểm tra trước khi gửi hoặc để application ghi metric. Tuy nhiên, kiểm tra ở client không phải hàng rào bảo mật: caller có thể bỏ qua client chính thức và gửi raw gRPC request. Server vẫn phải cấu hình transport limit.

Không đồng nhất getSerializedSize() với kích thước HTTP/2 trên wire. Framing, compression và các lớp transport có overhead riêng. Hãy dùng cùng đơn vị byte và kiểm thử trên đúng grpc-java transport để xác nhận ranh giới thực tế.

## 4. Compression không loại bỏ nhu cầu giới hạn

gRPC có thể nén message để giảm dữ liệu truyền trên network. Một payload nhỏ sau nén có thể nở lớn khi giải nén. Nếu chỉ nhìn số byte trên wire, ứng dụng có thể đánh giá thấp lượng memory cần để parse message.

Khi đặt giới hạn, hãy xem xét kích thước message sau giải nén mà runtime phải xử lý. Không tăng limit chỉ vì bật gzip hoặc một compressor khác. Compression có thể giảm băng thông nhưng không làm giảm tương ứng heap cần thiết cho protobuf object đã giải mã.

Các điểm cần kiểm soát:

- Chọn ngưỡng phù hợp với kích thước nội dung sau giải nén.
- Chỉ bật compressor/decompressor cần thiết.
- Không cho phép các kiểu nén không được hệ thống hỗ trợ hoặc kiểm soát.
- Giới hạn đồng thời và tốc độ request để tránh nhiều message lớn được giải nén cùng lúc.
- Theo dõi CPU, heap và thời gian giải nén khi bật compression.

Một message không vượt ngưỡng vẫn có thể tốn nhiều CPU hoặc tạo object graph lớn. Message-size limit là một lớp bảo vệ, không phải cơ chế chống mọi dạng resource exhaustion.

## 5. Chọn giới hạn dựa trên contract và ngân sách tài nguyên

Không có một ngưỡng phù hợp cho mọi RPC. Một API tra cứu order có thể chỉ cần vài KiB; API gửi batch có thể cần vài MiB; API upload file nên thiết kế theo chunk thay vì tăng một message lên hàng trăm MiB.

Khi chọn ngưỡng, xem xét:

1. **Contract:** request/response hợp lệ lớn nhất mà API thực sự cần.
2. **Memory:** kích thước serialized có thể nhỏ hơn đáng kể hoặc lớn hơn object graph trong heap sau parse.
3. **Concurrency:** số message lớn có thể được xử lý đồng thời trên một instance.
4. **Compression:** kích thước sau giải nén và CPU cần thiết.
5. **Latency:** parse, validate và xử lý một message lớn có thể vượt deadline.
6. **Deployment:** heap limit, container memory, autoscaling và giới hạn tài nguyên của node.
7. **Client population:** khả năng tương thích của client cũ với ngưỡng mới.

Có thể ước lượng thô bộ nhớ từ kích thước message và concurrency, nhưng không nên giả định heap usage bằng đúng số byte serialized. Protobuf object, string, collection, byte array, copy buffer và business object có overhead riêng. Đo bằng load test với payload gần ngưỡng trong môi trường giống production.

Ví dụ, nếu một instance có 1 GiB heap dành cho workload, không thể lấy 1 GiB chia cho 8 MiB rồi kết luận có thể xử lý 128 message đồng thời. Các request còn dùng memory cho channel, connection, cache, thread, domain object và response. Hãy dành headroom và đặt concurrency/quota độc lập.

## 6. Cấu hình không thay thế validation ở cấp ứng dụng

Transport limit bảo vệ kích thước tổng của một message. Nó không bảo đảm từng field có giá trị hợp lệ hoặc phù hợp nghiệp vụ.

Ví dụ request protobuf:

~~~proto
message ImportBatchRequest {
  string tenant_id = 1;
  repeated string external_ids = 2;
  bytes attachment = 3;
}
~~~

Một message nằm dưới ngưỡng vẫn có thể chứa:

- Quá nhiều phần tử trong external_ids.
- Một chuỗi cực dài trong một field.
- Nhiều field lồng nhau gây tốn CPU khi xử lý.
- Một attachment có kích thước không phù hợp với use case.
- Dữ liệu hợp lệ về protobuf nhưng không hợp lệ về business rule.

Sau khi transport chấp nhận message, application vẫn cần kiểm tra kích thước từng field, số lượng phần tử, độ sâu/độ phức tạp theo schema, tenant và quyền truy cập. Đặt các giới hạn nghiệp vụ cụ thể, ví dụ tối đa 500 ID trong một batch hoặc tối đa 256 KiB cho một attachment field, nếu contract yêu cầu.

Không dùng một ngưỡng message rất lớn để thay thế thiết kế schema có giới hạn. Chia các thao tác lớn thành RPC/chunk nhỏ thường giúp retry, progress, flow control và cleanup dễ kiểm soát hơn.

## 7. Dữ liệu lớn: dùng chunking thay vì nâng ngưỡng vô hạn

Với file hoặc payload lớn, thiết kế client-streaming hoặc bidirectional streaming theo chunk. Ví dụ:

~~~proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

message UploadResult {
  string upload_id = 1;
  int64 bytes_received = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
~~~

Mỗi chunk nên có kích thước tối đa rõ ràng, nhỏ hơn giới hạn inbound message của server. Server kiểm tra sequence, upload ownership, tenant, quota và tổng số byte trước khi ghi chunk.

Một luồng upload an toàn có thể:

1. Tạo upload session với quota tổng và thời hạn.
2. Xác minh principal được phép upload vào resource/tenant.
3. Nhận từng chunk có giới hạn kích thước.
4. Kiểm tra sequence và tổng byte trước khi lưu.
5. Ghi chunk vào object storage hoặc staging area theo cơ chế an toàn.
6. Khi hoàn tất, xác minh checksum và metadata rồi finalize.
7. Hủy session và giải phóng dữ liệu tạm khi client cancel hoặc upload hết hạn.

Chunking không tự động giới hạn tổng upload. Cần thêm quota tổng, số chunk, thời gian upload, số upload đồng thời và cleanup các session bỏ dở. Không ghép toàn bộ chunk vào một byte array lớn trong heap nếu có thể ghi theo luồng vào storage.

## 8. Streaming: limit từng message và limit tổng stream

Với streaming RPC, maxInboundMessageSize được áp dụng cho từng message nhận vào. Một client-streaming call có thể gửi rất nhiều message hợp lệ về kích thước nhưng tổng dữ liệu vượt khả năng của service.

Do đó cần phối hợp nhiều lớp:

| Giới hạn | Bảo vệ điều gì |
| --- | --- |
| **max inbound message size** | Kích thước tối đa của một message |
| **Maximum messages per stream** | Số message tối đa trong một RPC |
| **Total bytes per stream** | Tổng dữ liệu nhận trong suốt stream |
| **Deadline/maximum stream lifetime** | Thời gian stream được phép tồn tại |
| **Concurrent stream limit** | Số stream đồng thời theo server/tenant |
| **Rate limit** | Tốc độ gửi message hoặc byte |
| **Flow control/backpressure** | Tốc độ producer so với khả năng consumer |
| **Application quota** | Tổng dung lượng nghiệp vụ, ví dụ kích thước file upload |

Bộ đếm tổng byte phải dùng kiểu số đủ lớn như long, kiểm tra overflow và cập nhật trước khi tạo side effect. Với nhiều stream đồng thời, quota theo tenant cần được cập nhật nguyên tử để hai stream không cùng vượt hạn mức.

Khi một stream vượt quota tổng, service có thể kết thúc bằng RESOURCE_EXHAUSTED theo contract. Khi một message đơn lẻ vượt max inbound limit, transport thường từ chối message trước khi service handler nhận được nó.

## 9. Status khi message vượt giới hạn

Khi một inbound message lớn hơn ngưỡng cấu hình, grpc-java thường kết thúc RPC với status RESOURCE_EXHAUSTED. Service implementation có thể không nhận được request message đó, vì lỗi được phát hiện ở tầng deframer/transport trước khi gọi handler.

Client nên phân biệt:

- **Message vượt giới hạn transport:** kiểm tra kích thước serialized và cấu hình receive limit của server.
- **Quota tổng vượt giới hạn:** kiểm tra tổng byte, số message hoặc quota của operation.
- **Field vi phạm contract:** server đã nhận message nhưng application validation từ chối, thường dùng INVALID_ARGUMENT hoặc status phù hợp với contract.
- **Thiếu quyền upload:** dùng PERMISSION_DENIED, không dùng RESOURCE_EXHAUSTED.

Không dựa vào status description cụ thể của grpc-java vì nội dung có thể thay đổi theo phiên bản/transport. Dùng status code và log phía server để phân loại. Nếu client thấy RESOURCE_EXHAUSTED, không tự động retry cùng payload; retry không làm message nhỏ hơn và có thể lặp request không cần thiết.

Với mutation, cần xem xét idempotency. Khi connection bị ngắt hoặc deadline hết, client không thể luôn biết server đã commit bao nhiêu dữ liệu. Upload chunk nên có upload ID, sequence và cơ chế resume/idempotency rõ ràng.

## 10. Quan sát và vận hành

Để vận hành giới hạn hiệu quả, theo dõi:

- Số RPC bị từ chối do message quá lớn theo method.
- Kích thước serialized message gần ngưỡng và phân vị p50/p95/p99.
- Tổng byte và số message mỗi stream.
- Heap usage, allocation rate, GC pause và OOM.
- CPU khi giải nén/parse protobuf.
- Số stream đồng thời, thời lượng stream và số lần cancel.
- Tỷ lệ RESOURCE_EXHAUSTED phân loại theo nguyên nhân.

Tránh ghi toàn bộ payload hoặc bytes nhạy cảm vào log để chẩn đoán. Chỉ ghi method, kích thước, transport/status, tenant identifier đã được xử lý theo chính sách và trace ID cần thiết. Không đưa request ID hoặc tenant ID cardinality cao vào metric label nếu làm hệ thống metrics phình lớn.

Khi điều chỉnh limit, thay đổi từng bước và so sánh tỷ lệ reject, heap, CPU và latency. Một giới hạn quá thấp làm client hợp lệ bị lỗi; giới hạn quá cao tăng blast radius khi có request lớn hoặc nhiều request đồng thời.

## 11. Kiểm thử ranh giới kích thước

Cần kiểm thử đúng boundary thay vì chỉ gửi một request nhỏ và kết luận cấu hình hoạt động.

Giả sử server limit là 1 MiB:

| Payload | Kỳ vọng |
| --- | --- |
| Nhỏ hơn giới hạn | Server nhận và xử lý |
| Bằng giới hạn | Xác minh hành vi theo kích thước serialized thực tế và transport |
| Lớn hơn giới hạn | Transport từ chối; thường là RESOURCE_EXHAUSTED |
| Nhiều message nhỏ trong stream | Từng message được nhận; quota tổng được kiểm tra riêng |
| Message nén có payload giải nén lớn | Bị giới hạn theo receive-size enforcement của runtime |
| Response vượt client inbound limit | Client từ chối response |

Dùng protobuf generated message và getSerializedSize() để tạo payload sát ngưỡng. Nhớ rằng một field bytes có thêm tag và length prefix trong serialized protobuf, nên độ dài của byte array không bằng toàn bộ serialized size.

Ví dụ kiểm tra ở client trước khi gửi:

~~~java
int serializedBytes = request.getSerializedSize();

if (serializedBytes > configuredServerLimitBytes) {
    throw new IllegalArgumentException(
            "Request exceeds the server message-size contract");
}
~~~

Đây chỉ là validation tiện ích ở client. Test bắt buộc phải gửi request vượt ngưỡng tới server thật hoặc in-process transport có áp dụng cùng receive limit để xác minh server từ chối độc lập với client-side check.

Các test cần bao gồm:

1. Request hợp lệ dưới ngưỡng được xử lý.
2. Request vượt ngưỡng không đi vào service handler.
3. Status code quan sát được ở client phù hợp với transport/version.
4. Client inbound limit được kiểm tra độc lập với server inbound limit.
5. Streaming tổng dữ liệu vượt quota dù từng message nhỏ.
6. Compression không làm vô hiệu giới hạn.
7. Spring application test xác minh cấu hình builder thực tế đã được áp dụng.

## 12. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ server inbound limit giới hạn response | Client nhận response quá lớn | Cấu hình client inbound limit riêng |
| Coi limit là giới hạn HTTP/2 frame | Đặt ngưỡng sai tầng | Hiểu đây là giới hạn một gRPC message |
| Tăng limit rất lớn để upload file | Heap và GC tăng mạnh | Dùng streaming chunk và quota tổng |
| Chỉ nhìn số byte sau nén | Payload nở lớn khi giải nén | Đánh giá kích thước sau giải nén và CPU |
| Cho rằng stream có limit tổng tự động | Nhiều message nhỏ tạo stream khổng lồ | Đếm total bytes/messages và đặt deadline |
| Chỉ validate ở client | Raw client bỏ qua kiểm tra | Server transport limit và application validation |
| Chỉ kiểm tra tổng message size | Một field hoặc collection quá lớn theo nghiệp vụ | Đặt giới hạn riêng cho field và số phần tử |
| Retry payload đã bị từ chối | Lặp lỗi không thể tự hết | Giảm/chia payload hoặc điều chỉnh contract |
| Cấu hình Spring property không đúng starter | Server chạy với default ngoài dự kiến | Dùng builder hook được phiên bản hỗ trợ và integration test |

## 13. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Chọn một server inbound limit cụ thể, ví dụ 1 MiB, và cấu hình trên grpc-java server builder.
2. Cấu hình client inbound limit riêng cho response.
3. Tạo protobuf request có field bytes và dùng getSerializedSize() để tạo payload dưới, sát và vượt ngưỡng.
4. Viết integration test chứng minh request vượt ngưỡng không vào service handler.
5. Tạo client-streaming upload theo chunk, giới hạn bytes mỗi chunk và tổng bytes của upload.
6. Thêm quota số chunk, thời lượng upload, số stream đồng thời và cleanup khi cancel.
7. Bật compression trong test và xác minh receive-size enforcement vẫn bảo vệ message.
8. Trong Spring gRPC application test, xác minh builder customizer/extension point thực sự áp dụng limit.

### Câu hỏi tự kiểm tra

**1. max inbound message size giới hạn điều gì?**  
Kích thước tối đa của một gRPC message mà endpoint nhận vào.

**2. Server inbound limit có giới hạn response server gửi cho client không?**  
Không. Client cần cấu hình inbound limit của chính nó để giới hạn response nhận về.

**3. Đơn vị cấu hình là gì?**  
Byte.

**4. Một stream có thể vượt nhiều GiB dù mỗi message dưới limit không?**  
Có. Limit áp dụng từng message; cần quota tổng byte, số message, thời gian và rate limit cho stream.

**5. Compression có làm payload lớn trở nên an toàn mặc định không?**  
Không. Phải xét kích thước sau giải nén, CPU và memory để parse.

**6. Vì sao upload file lớn nên dùng chunk?**  
Chunk giữ message nhỏ, hỗ trợ retry/resume, progress và flow control; vẫn cần quota tổng và cleanup.

**7. Status nào thường xuất hiện khi inbound message vượt ngưỡng?**  
Thường là RESOURCE_EXHAUSTED; cần dựa vào status code và log, không parse description cụ thể.

**8. Vì sao client-side getSerializedSize check không đủ?**  
Client có thể bị bỏ qua hoặc giả mạo. Server phải enforce receive limit tại transport.

## Tổng kết

max inbound message size giới hạn kích thước của **mỗi gRPC message nhận vào**. Server cấu hình giới hạn request nhận từ client; client cấu hình giới hạn response nhận từ server. Đơn vị là byte, và giới hạn message không đồng nghĩa với giới hạn HTTP/2 frame hay tổng dữ liệu của streaming RPC. Khi chọn ngưỡng, cần xét payload sau giải nén, protobuf object overhead, concurrency, heap và latency. Dữ liệu lớn nên chia chunk và đi kèm quota tổng, flow control, deadline và cleanup. Kiểm thử boundary trên đúng grpc-java transport và xác minh cấu hình Spring thực tế giúp tránh việc ứng dụng vô tình chạy với giới hạn mặc định không phù hợp.

