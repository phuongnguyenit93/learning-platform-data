# Giới hạn inbound message size

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích giới hạn kích thước inbound message của gRPC và phạm vi áp dụng theo từng message.
- Cấu hình giới hạn nhận ở server và client bằng gRPC Java.
- Phân biệt message size với HTTP/2 frame size, flow-control window, metadata size và tổng dung lượng của một stream.
- Chọn giới hạn phù hợp với payload, streaming chunk và ngân sách bộ nhớ.
- Xử lý lỗi khi message vượt giới hạn và kiểm thử cả hai chiều truyền.
- Kết hợp message-size limit với quota, concurrency limit và validation để bảo vệ dịch vụ Spring gRPC.

## 1. Vì sao phải giới hạn inbound message?

Một RPC gRPC có thể mang message Protobuf chứa nhiều field, danh sách lớn hoặc dữ liệu nhị phân. Nếu server chấp nhận một message có kích thước tùy ý, một client có thể buộc server cấp phát nhiều bộ nhớ để nhận, giải mã và xử lý payload. Khi nhiều client làm việc này đồng thời, heap và CPU có thể cạn trước khi logic nghiệp vụ kịp từ chối request.

**Inbound message size limit** đặt giới hạn cho kích thước của từng message mà một endpoint chấp nhận nhận vào. Nó là một lớp bảo vệ ở tầng gRPC, trước khi ứng dụng xử lý đầy đủ nội dung message.

Trong **SPRING_GRPC**, giới hạn này cần được cân nhắc cho unary request lớn, từng chunk của client-streaming, từng response của server-streaming và từng message ở cả hai chiều của bidirectional streaming. Không nên tăng giới hạn chỉ để làm biến mất lỗi **RESOURCE_EXHAUSTED**; cần xác định payload hợp lệ lớn đến đâu và hệ thống có đủ bộ nhớ để xử lý đồng thời hay không.

## 2. Giới hạn được áp dụng cho từng message

Một stream có thể truyền nhiều message. Giới hạn inbound message size áp dụng riêng cho từng message được nhận, không phải tổng số byte tích lũy trong toàn bộ RPC.

Ví dụ, nếu giới hạn là 4 MiB:

- Một message 3 MiB có thể được chấp nhận.
- Một message 5 MiB vượt giới hạn và bị từ chối.
- Một stream gồm 100 message, mỗi message 1 MiB, vẫn có thể truyền tổng cộng khoảng 100 MiB nếu các giới hạn khác cho phép.

Vì vậy, message-size limit không phải tổng quota của upload hoặc subscription. Với streaming dài hạn, ứng dụng còn cần giới hạn tổng byte trên mỗi RPC, số message, thời gian hoạt động, tốc độ gửi và số stream đồng thời.

## 3. Server và client có giới hạn inbound riêng

Inbound luôn được hiểu theo góc nhìn của endpoint đang nhận:

| Endpoint | Dữ liệu inbound | Giới hạn bảo vệ |
| --- | --- | --- |
| gRPC server | Request từ client | Kích thước mỗi request message mà server nhận. |
| gRPC client/channel | Response từ server | Kích thước mỗi response message mà client nhận. |

Ví dụ:

- Với client-streaming, giới hạn inbound của server áp dụng cho từng request chunk.
- Với server-streaming, giới hạn inbound của client áp dụng cho từng response.
- Với bidirectional streaming, server giới hạn message đi từ client lên; client giới hạn message đi từ server xuống.

Hai phía không tự động chia sẻ cùng một cấu hình. Server chấp nhận response/request lớn không có nghĩa client cũng chấp nhận kích thước đó. Nếu hợp đồng cho phép message lớn, cần cấu hình và kiểm thử giới hạn nhận ở cả hai endpoint.

## 4. Cấu hình bằng gRPC Java

gRPC Java cung cấp phương thức **maxInboundMessageSize(int)** trên builder của server và channel. Tham số là số byte tối đa cho một inbound message.

Ví dụ cấu hình server nhận tối đa 8 MiB:

~~~java
import io.grpc.Server;
import io.grpc.ServerBuilder;

final int MAX_INBOUND_BYTES = 8 * 1024 * 1024;

Server server = ServerBuilder.forPort(9090)
    .maxInboundMessageSize(MAX_INBOUND_BYTES)
    .addService(new UploadService())
    .build()
    .start();
~~~

Ví dụ cấu hình client channel nhận response tối đa 8 MiB:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

final int MAX_INBOUND_BYTES = 8 * 1024 * 1024;

ManagedChannel channel = ManagedChannelBuilder
    .forAddress("localhost", 9090)
    .maxInboundMessageSize(MAX_INBOUND_BYTES)
    .build();
~~~

Trong ví dụ, server limit kiểm soát request inbound và channel limit kiểm soát response inbound. Hãy dùng cùng đơn vị byte khi chuyển từ cấu hình ứng dụng sang builder; tránh nhầm MB thập phân với MiB nhị phân.

Các builder cụ thể như Netty cũng cung cấp cấu hình tương ứng. Nếu ứng dụng dùng Spring Boot auto-configuration, hãy cấu hình builder/factory do starter đang sử dụng quản lý. Tên property và điểm mở rộng phụ thuộc thư viện tích hợp và phiên bản; không có một property Spring chung áp dụng cho mọi gRPC starter. Không tạo thêm server hoặc channel riêng chỉ để đặt giới hạn nếu ứng dụng đã dùng builder do Spring quản lý.

## 5. Giá trị mặc định và cách chọn giới hạn

Các builder gRPC Java thông dụng thường có mặc định inbound message size là **4 MiB**. Giá trị thực tế có thể phụ thuộc phiên bản, transport và lớp tích hợp; hãy xác minh cấu hình đang chạy thay vì dựa vào mặc định ngầm.

Chọn giới hạn dựa trên:

- Kích thước lớn nhất của payload hợp lệ theo nghiệp vụ.
- Số RPC có thể nhận đồng thời.
- Số message có thể đang chờ trong queue.
- Số bản sao dữ liệu có thể xuất hiện khi parse, validate hoặc chuyển đổi.
- Ngân sách heap dành cho gRPC và các thành phần khác.
- Độ trễ và chi phí CPU khi giải mã/giải nén payload.

Ví dụ, nếu một request 8 MiB có thể tạo thêm một bản sao trong DTO và một bản sao trong queue, chi phí bộ nhớ thực tế lớn hơn nhiều so với 8 MiB. Giới hạn phải được chọn từ tải đồng thời dự kiến, không chỉ từ kích thước một request đơn lẻ.

## 6. Message size khác HTTP/2 frame size và flow control

Một message gRPC không nhất thiết nằm trong một HTTP/2 DATA frame. Message có framing gRPC riêng và có thể được chia thành nhiều DATA frame; transport ghép các byte lại trước khi chuyển message lên tầng gRPC.

| Cơ chế | Giới hạn điều gì? |
| --- | --- |
| **Inbound message size** | Kích thước một message gRPC mà endpoint nhận cho phép. |
| **HTTP/2 maximum frame size** | Kích thước payload tối đa của một HTTP/2 frame. |
| **HTTP/2 flow-control window** | Lượng DATA có thể đang được gửi trên stream và connection trước khi cần WINDOW_UPDATE. |
| **Inbound metadata size** | Kích thước metadata/header được nhận. |
| **Application quota** | Tổng byte, số message hoặc thời gian xử lý mà nghiệp vụ cho phép. |

Tăng HTTP/2 frame size không làm tăng giới hạn inbound message. Tăng flow-control window cũng không cho phép một message vượt **maxInboundMessageSize**. Ngược lại, một message hợp lệ về kích thước vẫn có thể phải chờ vì flow-control window chưa đủ.

Metadata cũng là phần riêng. Không đặt nội dung file, JSON lớn hoặc dữ liệu nhị phân vào metadata để né giới hạn message; metadata có giới hạn và phục vụ thông tin điều khiển như token, trace ID hoặc correlation ID.

## 7. Điều gì xảy ra khi message vượt giới hạn?

Khi endpoint nhận phát hiện một message vượt giới hạn, gRPC kết thúc RPC bằng lỗi. Status thường thấy là **RESOURCE_EXHAUSTED** với mô tả liên quan đến message vượt kích thước tối đa.

Điểm quan trọng:

- Message bị từ chối ở tầng nhận; service method có thể không được gọi cho message đó.
- Với streaming, các message trước đó có thể đã được xử lý; message vượt giới hạn không được chuyển cho callback nghiệp vụ như một message hợp lệ.
- Client quan sát status của RPC qua callback lỗi hoặc exception của blocking stub.
- Không nên retry cùng một payload không đổi với cùng giới hạn; retry chỉ có ý nghĩa nếu giảm kích thước, chia chunk hoặc thay đổi chính sách nhận.

Không bắt **RESOURCE_EXHAUSTED** rồi âm thầm bỏ qua để tiếp tục xử lý một stream như thể message đã được nhận. Ứng dụng cần xác định rõ RPC có thể kết thúc hay có cơ chế khôi phục ở tầng nghiệp vụ.

## 8. Kiểm tra kích thước trước khi gửi

Giới hạn ở receiver là lớp bảo vệ bắt buộc, nhưng sender cũng nên kiểm tra để tránh tạo một RPC chắc chắn bị từ chối.

Với message Protobuf Java, **getSerializedSize()** trả kích thước serialized của message:

~~~java
final int MAX_REQUEST_BYTES = 8 * 1024 * 1024;

UploadRequest request = buildRequest();
int serializedSize = request.getSerializedSize();

if (serializedSize > MAX_REQUEST_BYTES) {
    throw new IllegalArgumentException(
        "Upload request exceeds the configured message limit");
}

stub.upload(request);
~~~

Kiểm tra này hữu ích ở client do chính ứng dụng kiểm soát. Server vẫn phải tự cấu hình giới hạn và validate request vì client bên ngoài có thể bỏ qua kiểm tra.

**getSerializedSize()** ước lượng kích thước Protobuf serialized, không phải tổng bộ nhớ heap của object. Nó cũng không thay thế kiểm tra giới hạn ở receiver hoặc giới hạn nghiệp vụ như số phần tử tối đa trong một danh sách.

## 9. Payload lớn: tăng limit hay chia chunk?

Tăng giới hạn có thể phù hợp nếu payload lớn là yêu cầu thực sự, tần suất thấp và ngân sách bộ nhớ đã được tính. Với dữ liệu lớn hoặc truyền liên tục, chia chunk qua streaming thường dễ kiểm soát hơn.

Ví dụ hợp đồng upload:

~~~proto
syntax = "proto3";

message UploadChunk {
  string upload_id = 1;
  uint64 sequence = 2;
  int64 offset = 3;
  bytes data = 4;
  bytes checksum = 5;
  bool last = 6;
}

message UploadResult {
  string upload_id = 1;
  int64 bytes_received = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
~~~

Mỗi chunk vẫn phải nằm dưới inbound message limit. Ngoài ra, server cần quy định:

- Kích thước chunk tối đa và tổng kích thước upload tối đa.
- Thứ tự qua **sequence** hoặc **offset**.
- Cách kiểm tra checksum và phát hiện chunk lặp/thiếu.
- Hành vi khi retry hoặc reconnect.
- Thời hạn upload và quota theo user/tenant.
- Khi nào xác nhận chunk đã được lưu bền vững.

Nếu cần chuyển tệp rất lớn, một lựa chọn khác là lưu file ở object storage và chỉ truyền URI, metadata cùng checksum qua gRPC. Cách này tránh đưa toàn bộ nội dung file qua message Protobuf, nhưng cần thiết kế quyền truy cập, thời hạn URL và xác minh nội dung.

## 10. Giới hạn message chưa đủ để chống quá tải

Một client có thể gửi nhiều message nhỏ thay vì một message lớn. Vì vậy, message-size limit cần đi cùng các giới hạn khác:

| Giới hạn | Mục tiêu |
| --- | --- |
| **Per-message size** | Ngăn một message quá lớn. |
| **Per-RPC total bytes** | Ngăn stream gửi tổng dữ liệu không giới hạn. |
| **Message count** | Giới hạn số chunk hoặc event trong một RPC. |
| **Concurrent RPCs** | Giới hạn số stream đang hoạt động đồng thời. |
| **Queue capacity/byte budget** | Giới hạn dữ liệu chờ xử lý trong heap. |
| **Deadline/idle timeout** | Ngăn RPC giữ tài nguyên quá lâu. |
| **Rate limit/quota** | Giới hạn tốc độ và tổng mức sử dụng theo client/tenant. |

Với payload nén, kích thước trên wire và kích thước sau giải nén có thể khác nhau đáng kể. Compression giảm lưu lượng mạng nhưng vẫn tiêu tốn CPU và bộ nhớ khi giải nén. Hãy kiểm thử với transport/runtime đang dùng và bảo đảm có biện pháp giới hạn dữ liệu sau giải nén hoặc giới hạn tài nguyên tương ứng; không xem compression là cách né message-size limit.

## 11. Kiểm thử giới hạn inbound

Nên kiểm thử ở mức integration qua channel/server thật hoặc test harness tương đương. Ma trận tối thiểu:

1. Message nhỏ hơn giới hạn được nhận và xử lý.
2. Message đúng tại giới hạn được kiểm tra theo semantics của implementation.
3. Message lớn hơn giới hạn bị từ chối với status phù hợp.
4. Server limit được kiểm tra riêng với request inbound.
5. Client limit được kiểm tra riêng với response inbound.
6. Streaming chunk vượt giới hạn làm RPC kết thúc theo hợp đồng.
7. Nhiều message nhỏ không vượt per-message limit nhưng vẫn bị giới hạn bởi tổng quota nếu vượt chính sách ứng dụng.
8. Payload có và không có compression được kiểm tra trên đúng transport/version production.

Ví dụ logic kiểm tra phía client:

~~~java
try {
    UploadResult result = blockingStub.upload(oversizedRequest);
    fail("Expected the server to reject the oversized request");
} catch (StatusRuntimeException ex) {
    assertEquals(
        Status.Code.RESOURCE_EXHAUSTED,
        ex.getStatus().getCode());
}
~~~

Đoạn kiểm thử giả định server được cấu hình giới hạn nhỏ hơn payload và request đi qua transport thật. Với streaming, dùng observer/test client và xác minh terminal callback; không chỉ kiểm tra một exception đồng bộ.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ cấu hình server, quên client | Response lớn vẫn bị client từ chối | Cấu hình inbound limit ở cả hai endpoint khi cần. |
| Nhầm giới hạn mỗi message với tổng stream | Nhiều chunk nhỏ có thể truyền tổng dữ liệu quá lớn | Thêm per-RPC byte quota và message-count limit. |
| Tăng limit rất cao để hết lỗi | Tăng nguy cơ heap exhaustion khi nhiều RPC đồng thời | Tính ngân sách theo payload và concurrency. |
| Nhầm HTTP/2 frame size với gRPC message size | Chỉnh sai tầng, lỗi vẫn còn | Cấu hình **maxInboundMessageSize** ở endpoint nhận. |
| Đưa payload vào metadata | Tăng header size và dùng sai mục đích metadata | Dùng message field hoặc streaming payload. |
| Chỉ kiểm tra ở client | Client không đáng tin có thể bỏ qua kiểm tra | Luôn enforce limit ở server. |
| Nghĩ **getSerializedSize()** là heap size | Ước lượng thiếu bộ nhớ thực tế | Cộng thêm overhead, bản sao và queue budget. |
| Bỏ qua compression và concurrency | Một tải nhỏ trên wire vẫn tiêu tốn tài nguyên lớn | Kiểm thử giải nén và áp dụng quota/concurrency limit. |

## 13. Bài tập thực hành

Một dịch vụ nhận tài liệu có giới hạn inbound message 8 MiB:

1. Cấu hình server nhận request tối đa 8 MiB bằng builder gRPC Java.
2. Cấu hình client channel nhận response tối đa 8 MiB.
3. Dùng **getSerializedSize()** kiểm tra request trước khi gửi.
4. Viết integration test cho payload dưới ngưỡng và trên ngưỡng; xác nhận lỗi **RESOURCE_EXHAUSTED** ở trường hợp vượt giới hạn.
5. Thiết kế client-streaming upload với chunk tối đa 1 MiB và tổng quota theo upload.
6. Định nghĩa cách kiểm tra sequence, offset, checksum, retry và cancellation.
7. Giải thích vì sao message-size limit không thay thế giới hạn tổng byte, số RPC đồng thời và deadline.

**Tiêu chí hoàn thành:** cấu hình đúng giới hạn ở receiver, phân biệt per-message với per-stream quota, xử lý lỗi vượt ngưỡng và chọn được chiến lược chunking cho payload lớn.

## 14. Ghi nhớ

- **maxInboundMessageSize(int)** giới hạn kích thước mỗi message nhận vào ở endpoint gRPC.
- Server limit bảo vệ request inbound; client/channel limit bảo vệ response inbound.
- Giới hạn message khác HTTP/2 frame size, flow-control window, metadata size và tổng quota của stream.
- Message vượt giới hạn thường làm RPC kết thúc với **RESOURCE_EXHAUSTED**; service method có thể không nhận được message đó.
- Dùng **getSerializedSize()** để kiểm tra trước khi gửi, nhưng vẫn phải enforce ở receiver.
- Với payload lớn, cân nhắc client-streaming theo chunk hoặc object storage; mỗi chunk vẫn phải nằm dưới giới hạn.
- Kết hợp per-message limit với tổng byte, message count, concurrency, queue budget, rate limit và deadline.

Giới hạn inbound message size được tính toán phù hợp giúp dịch vụ Spring gRPC từ chối payload quá lớn sớm, bảo vệ bộ nhớ khi nhiều RPC đồng thời và duy trì khả năng mở rộng của cả unary lẫn streaming API.
