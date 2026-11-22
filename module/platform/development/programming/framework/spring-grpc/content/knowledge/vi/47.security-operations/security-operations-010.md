# Bảo vệ dịch vụ gRPC trước message quá lớn

Trong một dịch vụ Spring gRPC, giới hạn kích thước message là hàng rào đầu tiên giúp bảo vệ bộ nhớ, CPU và độ ổn định của tiến trình khi nhận dữ liệu từ mạng. Một RPC có thể hợp lệ về mặt cú pháp Protocol Buffers nhưng vẫn chứa payload lớn đến mức gây áp lực lên heap, bộ giải mã và các luồng xử lý. Vì vậy, dịch vụ cần giới hạn kích thước ở tầng gRPC, kiểm tra thêm quy tắc nghiệp vụ và thiết kế luồng truyền dữ liệu phù hợp.

Bài học này tập trung vào cách đặt giới hạn cho message nhận ở server và client, cách chọn ngưỡng, cách xử lý lỗi và cách kiểm thử để xác nhận giới hạn thực sự được áp dụng trong môi trường chạy.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt kích thước của một gRPC message với kích thước của HTTP/2 frame và tổng dữ liệu của một streaming RPC.
- Xác định endpoint nào cần cấu hình giới hạn inbound.
- Cấu hình maxInboundMessageSize bằng Spring Boot hoặc API grpc-java.
- Thiết kế upload/download lớn bằng streaming, chia chunk hoặc lưu trữ ngoài.
- Kiểm thử trường hợp nằm dưới, đúng bằng và vượt ngưỡng; nhận diện lỗi RESOURCE_EXHAUSTED.

## 1. Vì sao message quá lớn là rủi ro?

gRPC dùng Protocol Buffers để tuần tự hóa dữ liệu và truyền qua HTTP/2. Một message lớn có thể làm tăng nhiều loại chi phí:

1. **Bộ nhớ:** dữ liệu nhận vào, buffer trung gian và object Java sau khi giải mã có thể cùng tồn tại. Kích thước object trong heap thường lớn hơn số byte trên đường truyền.
2. **CPU:** giải nén, giải mã Protobuf, sao chép buffer và kiểm tra dữ liệu đều tốn CPU. Payload lớn có thể kéo dài thời gian xử lý của một RPC.
3. **Garbage Collection:** nhiều object lớn hoặc mảng byte lớn làm tăng áp lực cấp phát và thu hồi bộ nhớ.
4. **Khả năng phục vụ đồng thời:** nhiều client cùng gửi message lớn có thể làm cạn bộ nhớ hoặc khiến các request nhỏ phải chờ.
5. **Bề mặt tấn công:** một client đã xác thực vẫn có thể gửi payload bất thường hoặc vượt xa nhu cầu nghiệp vụ. Giới hạn kích thước giúp giảm khả năng một request đơn lẻ tiêu thụ tài nguyên không giới hạn.

Ví dụ, nếu server cho phép một message 8 MiB và có 100 RPC đồng thời đang nhận message ở gần ngưỡng, riêng dữ liệu message đã có thể chiếm khoảng 800 MiB. Đây chỉ là phép ước lượng ban đầu; buffer, object Protobuf, bản sao dữ liệu và logic ứng dụng có thể làm mức sử dụng heap cao hơn.

Giới hạn message vì vậy là một phần của kiểm soát tài nguyên, bên cạnh giới hạn số RPC đồng thời, tốc độ request, deadline, kích thước metadata và quota nghiệp vụ.

## 2. Hiểu đúng phạm vi của giới hạn

### 2.1. Message không phải HTTP/2 frame

Một gRPC message có thể được chia thành nhiều HTTP/2 DATA frame khi truyền trên mạng. Giới hạn kích thước message áp dụng cho message gRPC ở tầng giao thức, không phải giới hạn kích thước của từng HTTP/2 frame. Thay đổi kích thước frame không phải cách phù hợp để giới hạn payload của ứng dụng.

### 2.2. Giới hạn áp dụng cho từng message

maxInboundMessageSize giới hạn kích thước tối đa của **một message được nhận**. Với unary RPC, thường chỉ có một request hoặc response message. Với client-streaming, server-streaming và bidirectional streaming, mỗi message trong luồng được kiểm tra riêng.

Ví dụ, một stream gồm 500 chunk, mỗi chunk 1 MiB, không bị giới hạn tổng cộng ở 4 MiB chỉ vì giới hạn inbound là 4 MiB. Từng chunk đều có thể nằm dưới giới hạn trong khi tổng luồng đạt 500 MiB. Nếu nghiệp vụ cần giới hạn tổng dung lượng upload, số chunk hoặc thời lượng stream, ứng dụng phải tự quản lý các ngân sách đó.

### 2.3. Inbound được tính ở phía nhận

Giới hạn inbound là thuộc tính của phía **nhận** dữ liệu:

| Luồng dữ liệu | Nơi cần đặt giới hạn |
| --- | --- |
| Client gửi request đến server | Server giới hạn message inbound |
| Server trả response cho client | Client giới hạn message inbound |
| Client-streaming | Server giới hạn từng message client gửi |
| Server-streaming | Client giới hạn từng message server gửi |
| Bidirectional streaming | Cả client và server đều đặt giới hạn inbound cho chiều nhận của mình |

Giới hạn inbound trên server không tự động giới hạn response mà server gửi ra. Nếu server gửi một response lớn hơn giới hạn của client, client có thể từ chối response đó. Tương tự, giới hạn inbound trên client không ngăn server nhận một request quá lớn.

maxInboundMetadataSize là một giới hạn riêng dành cho metadata/header của RPC. Nó không thay thế maxInboundMessageSize, vốn áp dụng cho nội dung message Protobuf.

## 3. Cấu hình trong Spring Boot

Tên property phụ thuộc phiên bản Spring Boot và Spring gRPC mà ứng dụng sử dụng. Hãy kiểm tra tài liệu tương ứng với dependency đang chạy; không trộn các tên property giữa những thế hệ cấu hình.

### 3.1. Spring Boot 4.1.x

Trong cấu hình Spring Boot 4.1.x hiện tại, server dùng spring.grpc.server.inbound.message.max-size. Với client, có thể đặt giới hạn trên từng logical channel. Ví dụ sau đặt giới hạn 8 MiB cho server và channel inventory:

~~~yaml
spring:
  grpc:
    server:
      inbound:
        message:
          max-size: 8MB
    client:
      channel:
        inventory:
          target: static://inventory.internal:9090
          inbound:
            message:
              max-size: 8MB
~~~

Property phía server kiểm soát request message mà server nhận. Property phía client kiểm soát response message mà channel inventory nhận. Nếu ứng dụng có nhiều channel, hãy đặt giới hạn cho đúng channel có nhu cầu nhận response lớn.

### 3.2. Spring gRPC 1.0.x

Spring gRPC 1.0.x dùng tên property khác. Với default channel, cấu hình tương ứng có dạng:

~~~yaml
spring:
  grpc:
    server:
      max-inbound-message-size: 8MB
    client:
      default-channel:
        max-inbound-message-size: 8MB
~~~

Hai ví dụ trên là hai kiểu cấu hình theo phiên bản. Trước khi áp dụng, đối chiếu phiên bản trong dependency management và danh sách application properties của dự án. Một property không được phiên bản hiện tại hỗ trợ có thể bị bỏ qua hoặc không tạo ra giới hạn như mong muốn.

## 4. Cấu hình trực tiếp bằng grpc-java

Khi tự tạo server hoặc channel, dùng maxInboundMessageSize(int bytes) trên builder tương ứng. Giá trị truyền vào được tính bằng byte.

~~~java
private static final int MAX_MESSAGE_BYTES = 8 * 1024 * 1024;

Server server = ServerBuilder.forPort(9090)
        .maxInboundMessageSize(MAX_MESSAGE_BYTES)
        .addService(new InventoryService())
        .build();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("inventory.internal", 9090)
        .useTransportSecurity()
        .maxInboundMessageSize(MAX_MESSAGE_BYTES)
        .build();
~~~

Trong ví dụ:

- ServerBuilder.maxInboundMessageSize giới hạn message mà server nhận.
- ManagedChannelBuilder.maxInboundMessageSize giới hạn message mà client nhận.
- 8 * 1024 * 1024 tương đương 8 MiB.

Nếu Spring đang quản lý vòng đời server và channel, hãy cấu hình qua property hoặc extension point của starter đang dùng. Không tạo thêm server/channel thủ công chỉ để đặt giới hạn, vì việc đó có thể khiến ứng dụng có hai cấu hình kết nối hoặc hai vòng đời tài nguyên khác nhau.

Theo API grpc-java, mặc định của ServerBuilder và ManagedChannelBuilder là 4 MiB nếu không cấu hình. Mặc định này có thể khác ở transport hoặc thư viện tích hợp khác; hãy xác nhận bằng tài liệu của phiên bản đang triển khai và bằng kiểm thử thực tế. API cũng cho biết một số transport có thể không thực thi giới hạn này; InProcess transport là ví dụ cần lưu ý khi viết integration test.

## 5. Chọn ngưỡng an toàn

Không nên tăng giới hạn chỉ vì một request đã gặp lỗi. Trước tiên, xác định vì sao message lớn là cần thiết và kích thước thực tế của dữ liệu.

Một quy trình chọn ngưỡng có thể thực hiện như sau:

1. Đo kích thước serialized của các request và response đại diện cho dữ liệu thực tế, bao gồm trường hợp lớn hợp lệ.
2. Xem phân bố kích thước theo endpoint, chẳng hạn p50, p95, p99 và giá trị lớn nhất đã được nghiệp vụ chấp thuận.
3. Chọn ngưỡng cao hơn trường hợp lớn hợp lệ một khoảng dự phòng hợp lý, nhưng vẫn nằm trong ngân sách bộ nhớ và CPU của service.
4. Đánh giá mức tiêu thụ khi nhiều RPC cùng nhận message gần ngưỡng.
5. Ghi lại lý do chọn ngưỡng và đưa nó vào cấu hình triển khai để các môi trường dùng nhất quán.

Ví dụ, nếu request hợp lệ lớn nhất của một API là khoảng 2 MiB, đặt giới hạn 64 MiB chỉ để tránh lỗi là một lựa chọn thiếu căn cứ. Ngược lại, nếu một RPC cần nhận dữ liệu 12 MiB, giữ nguyên giới hạn 4 MiB sẽ khiến request hợp lệ bị từ chối. Hãy xác định đúng nhu cầu và thiết kế lại payload nếu dữ liệu lớn là thường xuyên.

Không nên đặt giới hạn thành giá trị cực lớn hoặc vô hiệu hóa nó trong production. Tăng giới hạn làm tăng mức tài nguyên mà một peer có thể yêu cầu ở mỗi message; nó không tự tạo thêm bộ nhớ hay năng lực xử lý cho service.

## 6. Thiết kế khi nghiệp vụ cần truyền dữ liệu lớn

Nếu payload thường xuyên vượt giới hạn hợp lý của một message, hãy thay đổi cách truyền dữ liệu.

### 6.1. Chia dữ liệu thành chunk trong streaming RPC

Với upload file, client có thể gửi nhiều chunk qua client-streaming RPC. Mỗi chunk cần có kích thước tối đa riêng, số thứ tự và thông tin nhận diện upload.

~~~proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes content = 3;
}

message UploadSummary {
  string upload_id = 1;
  int64 total_bytes = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadSummary);
}
~~~

Trong service, kiểm tra cả kích thước chunk và tổng số byte của một upload. Ví dụ phần kiểm tra tổng dung lượng:

~~~java
private static final long MAX_CHUNK_BYTES = 1024L * 1024L;
private static final long MAX_UPLOAD_BYTES = 100L * 1024L * 1024L;

private long acceptChunk(UploadChunk chunk, long receivedBytes) {
    long chunkBytes = chunk.getContent().size();

    if (chunkBytes > MAX_CHUNK_BYTES
            || chunkBytes > MAX_UPLOAD_BYTES - receivedBytes) {
        throw Status.RESOURCE_EXHAUSTED
                .withDescription("Upload exceeds the allowed size")
                .asRuntimeException();
    }

    // Ghi chunk vào storage hoặc xử lý theo luồng.
    return receivedBytes + chunkBytes;
}
~~~

Gọi acceptChunk từ onNext của StreamObserver và lưu giá trị trả về trong biến receivedBytes thuộc observer đó; mỗi RPC phải có trạng thái riêng, không dùng chung giữa các client. Nếu kiểm tra ném StatusRuntimeException, chuyển lỗi sang responseObserver.onError để kết thúc RPC. Trong triển khai thực tế, cần xử lý thêm thứ tự chunk, chunk trùng, hủy RPC, timeout, xác minh checksum và dọn dữ liệu upload dở dang. Nên ghi chunk ra storage theo luồng thay vì giữ toàn bộ nội dung trong heap.

Giới hạn message gRPC vẫn cần được đặt lớn hơn hoặc bằng kích thước chunk hợp lệ. Giới hạn tổng upload là quy tắc nghiệp vụ riêng và phải được kiểm tra xuyên suốt stream.

### 6.2. Dùng object storage cho file lớn

Với file hàng trăm MiB hoặc nhiều GiB, một mô hình thường phù hợp hơn là:

1. Client gọi RPC để xin quyền upload và nhận URL có thời hạn từ object storage.
2. Client tải file trực tiếp lên object storage theo cơ chế upload phù hợp.
3. Client gọi RPC khác để gửi object key, kích thước, checksum và metadata cần thiết.
4. Server xác minh quyền truy cập, checksum, kích thước và trạng thái file trước khi xử lý.

Cách này giúp gRPC mang dữ liệu điều khiển và trạng thái nghiệp vụ, còn hệ thống lưu trữ chuyên dụng xử lý luồng byte lớn.

### 6.3. Phân trang kết quả và giảm dữ liệu dư thừa

Với response chứa danh sách lớn, hãy dùng pagination hoặc streaming thay vì trả về toàn bộ danh sách trong một unary response. Tránh lặp lại dữ liệu không cần thiết, tránh nhúng file dưới dạng Base64 trong string, và cân nhắc trường bytes khi thật sự cần truyền dữ liệu nhị phân.

## 7. Kết hợp giới hạn giao thức với kiểm tra nghiệp vụ

Giới hạn ở tầng gRPC bảo vệ endpoint trước một message vượt ngưỡng. Nó không thay thế việc kiểm tra cấu trúc và quy tắc nghiệp vụ sau khi message đã được nhận.

Ví dụ, một message 2 MiB có thể vẫn không hợp lệ nếu chứa:

- Quá nhiều phần tử trong một trường repeated.
- Một trường bytes vượt giới hạn của nghiệp vụ.
- Chuỗi UTF-8 quá dài; số ký tự không đồng nghĩa với số byte.
- Cấu trúc lồng nhau quá sâu hoặc dữ liệu không phù hợp với trạng thái hiện tại.
- Tổng dữ liệu của cả stream vượt quota dù từng chunk đều hợp lệ.

Hãy xác định ngân sách theo từng RPC: kích thước message tối đa, số phần tử tối đa, kích thước từng trường quan trọng, tổng byte của stream, số RPC đồng thời và thời gian xử lý. Khi từ chối dữ liệu ở tầng nghiệp vụ, trả status và mô tả đủ rõ để client có thể sửa request.

Compression có thể giảm số byte truyền trên mạng nhưng không nên được xem là cách vượt qua giới hạn message. Payload vẫn cần được giải nén và giải mã, do đó vẫn tiêu tốn tài nguyên. Đặc biệt, không nhận dữ liệu không giới hạn chỉ vì client có thể nén dữ liệu trước khi gửi.

Ngoài message body, hãy giữ giới hạn metadata hợp lý. Metadata thường dùng cho token, trace context và thông tin điều khiển; không dùng metadata để chuyển payload lớn.

Nếu có API gateway, reverse proxy hoặc ingress đứng trước gRPC server, hãy kiểm tra giới hạn của từng lớp. Một request có thể bị từ chối ở proxy trước khi tới ứng dụng, hoặc bị gRPC runtime từ chối sau khi qua proxy. Cần thống nhất ngưỡng và cách quan sát lỗi giữa các lớp.

## 8. Xử lý lỗi và quan sát vận hành

Khi một message vượt giới hạn inbound, grpc-java thường kết thúc RPC với status RESOURCE_EXHAUSTED. Việc từ chối có thể xảy ra trước khi method của service được gọi, vì vậy không nên kỳ vọng logic trong service luôn nhận được request để tự kiểm tra kích thước.

Ở client, xử lý lỗi qua callback onError hoặc exception tương ứng với loại stub đang dùng. Có thể phân loại RESOURCE_EXHAUSTED để hiển thị thông báo rằng request/response vượt giới hạn cho phép. Không tự động retry nguyên payload với cùng kích thước: request xác định vẫn sẽ vượt ngưỡng ở lần thử tiếp theo.

Ở phía vận hành, nên theo dõi:

- Số RPC bị từ chối do message quá lớn, phân theo service và method.
- Status code RESOURCE_EXHAUSTED và tỷ lệ lỗi theo thời gian.
- Phân bố kích thước message ở các endpoint quan trọng.
- Heap usage, GC pause, CPU và số RPC đang hoạt động khi tải tăng.
- Lỗi phát sinh ở gateway/ingress nếu có lớp trung gian.

Log tên RPC, status, kích thước ước lượng và correlation/trace ID khi có thể. Không ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log chỉ để tìm nguyên nhân lỗi.

## 9. Kiểm thử giới hạn

Một bài kiểm thử tốt phải xác nhận cả cấu hình lẫn hành vi ở ranh giới.

### 9.1. Kiểm thử ba trường hợp kích thước

Với giới hạn MAX_MESSAGE_BYTES, tạo message có serialized size:

- Nhỏ hơn giới hạn: RPC phải thành công nếu các điều kiện khác hợp lệ.
- Bằng giới hạn: xác nhận transport và serializer của phiên bản đang dùng chấp nhận đúng giá trị biên.
- Lớn hơn giới hạn: RPC phải bị từ chối; phía nhận không được xử lý message đó.

Protobuf Java cung cấp getSerializedSize() để kiểm tra kích thước đã tuần tự hóa của một message:

~~~java
int serializedBytes = request.getSerializedSize();
assertThat(serializedBytes).isLessThanOrEqualTo(MAX_MESSAGE_BYTES);
~~~

Đây là kiểm tra kích thước message Protobuf trước khi gửi. Để xác nhận giới hạn transport, cần gửi message qua kết nối gRPC thực và kiểm tra status trả về.

### 9.2. Kiểm thử đúng transport

Không chỉ dựa vào InProcess transport để xác nhận giới hạn. Tài liệu grpc-java ghi rõ maxInboundMessageSize có thể không được một số implementation thực thi và nêu InProcess transport là trường hợp như vậy. Hãy có ít nhất một integration test qua transport đang dùng trong production, chẳng hạn Netty hoặc servlet server tương ứng.

### 9.3. Kiểm thử streaming và tải đồng thời

Với streaming RPC, kiểm tra riêng:

- Một chunk vượt giới hạn message.
- Nhiều chunk hợp lệ nhưng tổng stream vượt quota.
- Chunk sai thứ tự, trùng lặp hoặc bị ngắt giữa chừng.
- Nhiều stream đồng thời gửi chunk gần ngưỡng.

Kiểm thử cả chiều client nhận response lớn. Một server có thể gửi response hợp lệ theo cấu hình của nó nhưng vẫn vượt giới hạn inbound trên client.

## 10. Quy trình xử lý khi gặp lỗi message quá lớn

Khi client báo RESOURCE_EXHAUSTED, hãy lần theo các bước sau:

1. Xác định method và chiều truyền dữ liệu đang lỗi: request vào server hay response vào client.
2. Đo kích thước serialized của message thực tế; không suy ra từ số ký tự hoặc kích thước file gốc.
3. Kiểm tra giới hạn ở endpoint nhận và property có thực sự được bind trong phiên bản Spring đang chạy.
4. Kiểm tra gateway/ingress và các lớp trung gian nếu request đi qua chúng.
5. Nếu payload lớn là nhu cầu hợp lệ, cân nhắc tăng giới hạn có kiểm soát hoặc chuyển sang chunked streaming/object storage.
6. Kiểm thử lại trường hợp dưới, bằng và trên ngưỡng bằng đúng transport production.
7. Theo dõi heap, CPU, GC và tỷ lệ lỗi sau khi triển khai cấu hình mới.

## Checklist triển khai

- [ ] Đã xác định giới hạn inbound ở server và client theo đúng chiều nhận.
- [ ] Đã kiểm tra tên property theo phiên bản Spring Boot/Spring gRPC.
- [ ] Giới hạn vẫn là giá trị hữu hạn và có lý do dựa trên dữ liệu thực tế.
- [ ] Đã phân biệt giới hạn một message với quota tổng của streaming RPC.
- [ ] Đã đặt giới hạn nghiệp vụ cho chunk, trường bytes, danh sách và tổng upload.
- [ ] Đã kiểm tra metadata, proxy/ingress và các lớp trung gian liên quan.
- [ ] Đã kiểm thử bằng transport mạng thực tế, không chỉ InProcess transport.
- [ ] Đã theo dõi RESOURCE_EXHAUSTED, kích thước message và tài nguyên tiến trình.

## Tài liệu tham khảo

- [Spring Boot Reference — gRPC](https://docs.spring.io/spring-boot/reference/io/grpc.html): cấu hình server và channel trong Spring Boot 4.x.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): danh sách property gRPC, bao gồm giới hạn inbound message và metadata.
- [Spring gRPC 1.0 — Common Application Properties](https://docs.spring.io/spring-grpc/reference/1.0/appendix.html): tên property của Spring gRPC 1.0.x.
- [grpc-java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): API maxInboundMessageSize phía server.
- [grpc-java — ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): API maxInboundMessageSize phía client.
