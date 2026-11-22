# Đặt message quá lớn để tránh thiết kế schema

## 1. Vì sao một Protobuf message quá lớn là vấn đề?

Trong **SPRING_GRPC**, Protobuf định nghĩa contract giữa client và server. Một lỗi thiết kế thường gặp là gom quá nhiều dữ liệu vào một request/response: hàng chục nghìn record, nhiều trường lặp không giới hạn, hoặc cả file nhị phân lớn. Cách này có vẻ đơn giản vì client chỉ cần một RPC, nhưng nó đẩy chi phí bộ nhớ, serialization, network, queueing và xử lý database lên một lần gọi.

Một message lớn có thể gây:

- Tăng allocation và garbage collection trên cả client lẫn server.
- Tăng latency trước khi server xử lý được record đầu tiên vì toàn message phải được nhận và parse.
- Tăng áp lực heap khi nhiều RPC lớn chạy đồng thời.
- Tạo burst network và làm các RPC nhỏ phải cạnh tranh tài nguyên.
- Khó retry vì gửi lại một payload lớn tốn thời gian và có thể lặp side effect.
- Tạo response lớn đến mức client, proxy hoặc server không chấp nhận.
- Khi schema tiếp tục thêm field để phục vụ nhiều use case, message trở thành một contract khó hiểu và khó tiến hóa.

Không nên tăng message limit chỉ để tránh quyết định cách chia resource, phân trang hoặc streaming. Hãy thiết kế contract thể hiện kích thước công việc hợp lý và giới hạn được tài nguyên mà mỗi RPC tiêu thụ.

## 2. Message size khác HTTP/2 frame size và flow control

Một gRPC message được đóng khung trong gRPC framing rồi truyền qua HTTP/2 DATA frames. Một message lớn có thể được chia thành nhiều frame; giới hạn frame của HTTP/2 không đồng nghĩa giới hạn kích thước toàn message.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Protobuf message size | Kích thước dữ liệu đã serialize cho một message gRPC |
| HTTP/2 frame size | Kích thước một frame trên transport |
| HTTP/2 flow control | Cơ chế điều tiết lượng DATA đang được truyền/nhận |
| gRPC max inbound message size | Giới hạn message mà endpoint chấp nhận khi nhận |
| Application quota | Giới hạn nghiệp vụ như số item, tổng byte hoặc số dòng được xử lý |

Flow control giúp điều tiết truyền dữ liệu, nhưng không làm một message khổng lồ trở thành payload nhỏ. Khi message được reassemble và parse, receiver vẫn cần bộ nhớ cho dữ liệu và object graph tương ứng.

Giới hạn inbound được cấu hình riêng ở client và server. Một phía chấp nhận message lớn không có nghĩa phía kia cũng chấp nhận. Contract nên quy định kích thước tối đa nhỏ hơn hoặc bằng giới hạn cấu hình của các endpoint và proxy liên quan.

## 3. Dấu hiệu schema đang gom quá nhiều dữ liệu

Một message có thể đang quá lớn hoặc quá đa dụng khi:

- Request chứa một collection không có giới hạn số phần tử.
- Response trả toàn bộ lịch sử thay vì một trang.
- Một field bytes chứa file, archive hoặc payload JSON lớn.
- Message có nhiều nhóm field chỉ phục vụ các operation khác nhau.
- Client phải gửi lại toàn bộ object dù chỉ cập nhật một phần.
- Một response chứa nhiều loại dữ liệu mà caller chỉ cần một loại.
- Tăng kích thước message limit thường xuyên là cách duy nhất để một RPC chạy thành công.

Không phải message có nhiều field luôn sai. Một command cần nhiều field nghiệp vụ có thể hoàn toàn hợp lý. Vấn đề là kích thước và phạm vi dữ liệu không bị chặn, hoặc contract gom nhiều luồng công việc khác nhau vào một message.

## 4. Thiết kế request/response nhỏ và có giới hạn

Với collection lớn, API nên hỗ trợ pagination thay vì trả tất cả record trong một message:

```proto
message ListOrdersRequest {
  string customer_id = 1;
  int32 page_size = 2;
  string page_token = 3;
}

message ListOrdersResponse {
  repeated OrderSummary orders = 1;
  string next_page_token = 2;
}

message OrderSummary {
  string order_id = 1;
  string status = 2;
  int64 created_at_epoch_ms = 3;
}
```

Server phải áp dụng giới hạn cứng cho page_size. Ví dụ client yêu cầu 10.000 item nhưng API chỉ cho phép tối đa 200, server có thể clamp theo contract hoặc trả INVALID_ARGUMENT. Quy tắc phải nhất quán và được tài liệu hóa.

Page token nên opaque đối với client và mang đủ thông tin để tiếp tục truy vấn, chẳng hạn cursor/sort key cùng filter scope. Không dùng offset pagination tùy tiện khi dữ liệu thay đổi nhanh nếu có nguy cơ bỏ sót hoặc lặp record; cursor pagination thường ổn định hơn.

Response chỉ nên chứa field caller cần. Nếu caller cần summary, không gửi toàn bộ entity với blob, audit trail và quan hệ lồng nhau.

## 5. Không dùng một message khổng lồ cho nhiều operation

Một request kiểu “god message” có thể chứa field cho create, update, search, import và export cùng lúc. Client phải biết tổ hợp field nào có ý nghĩa, server phải kiểm tra nhiều nhánh và schema trở nên khó hiểu.

Thay vào đó:

- Tạo request/response theo operation và use case.
- Dùng message con để tái sử dụng cấu trúc ổn định.
- Dùng oneof khi các lựa chọn thực sự loại trừ lẫn nhau.
- Dùng FieldMask cho update một phần nếu contract cần semantics patch.
- Tách metadata điều khiển khỏi payload nghiệp vụ.
- Không thêm field chỉ để né thiết kế một RPC riêng khi semantics khác nhau.

Ví dụ oneof phù hợp khi một nguồn dữ liệu có thể là URL hoặc inline text, nhưng không thể đồng thời là cả hai:

```proto
message ImportSource {
  oneof source {
    string object_uri = 1;
    bytes inline_data = 2;
  }
}
```

Dù dùng oneof, inline_data vẫn cần giới hạn kích thước. Oneof giải quyết lựa chọn schema, không tự giới hạn payload.

## 6. File và binary lớn nên đi qua object storage

Không nên gửi video, archive, ảnh gốc hoặc file nhiều megabyte/giabtye trong một gRPC message chỉ vì Protobuf có kiểu bytes.

Một pattern thường phù hợp:

1. Client yêu cầu server tạo upload session hoặc nhận thông tin upload.
2. Server xác thực caller, kiểm tra quota và cấp upload ID cùng URL/token có thời hạn.
3. Client upload file trực tiếp tới object storage qua kênh phù hợp.
4. Client gọi RPC finalize với upload ID, object key, kích thước và checksum.
5. Server xác minh object tồn tại, metadata và quyền truy cập.
6. Application service ghi resource metadata vào database.

RPC có thể mang reference tới object, không phải toàn bộ file:

```proto
message CompleteUploadRequest {
  string upload_id = 1;
  string object_key = 2;
  int64 content_length = 3;
  bytes sha256 = 4;
}

message CompleteUploadReply {
  string resource_id = 1;
  string state = 2;
}
```

Object key không nên được client tự do chọn nếu điều đó cho phép ghi đè object của tenant khác. Server phải ràng buộc upload session với tenant, user, loại resource, expiry và quota. Không log presigned URL hoặc token upload.

Nếu file nhỏ và contract có giới hạn thấp, inline bytes vẫn có thể hợp lý. Hãy quyết định theo kích thước tối đa, concurrency và memory budget chứ không theo sự tiện lợi của một ví dụ.

## 7. Khi cần truyền liên tục, dùng streaming với chunk có giới hạn

gRPC streaming phù hợp khi dữ liệu được tạo hoặc tiêu thụ theo từng phần. Mỗi message trong stream vẫn cần có kích thước giới hạn; streaming không đồng nghĩa một message không giới hạn.

Ví dụ client-streaming upload:

```proto
message UploadChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bytes checksum = 4;
  bool final_chunk = 5;
}

message UploadResult {
  string resource_id = 1;
  int64 bytes_received = 2;
}

service UploadService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
```

Server xử lý từng chunk, không gom toàn bộ file vào heap. Mỗi chunk nên có maximum byte size rõ ràng; giới hạn cần chừa chỗ cho field metadata, protobuf overhead và compression behavior.

Với bidirectional streaming, server có thể gửi receipt/ack cho từng sequence để client biết chunk nào đã được lưu bền vững. Với client-streaming chỉ trả một response cuối, client cần cơ chế resume/status query nếu kết nối bị ngắt giữa chừng.

## 8. Thiết kế chunk protocol có thể resume

Một upload nhiều chunk cần semantics rõ ràng:

- upload_id định danh session.
- sequence tăng đơn điệu theo thứ tự chunk.
- checksum xác minh dữ liệu chunk.
- server lưu checkpoint/receipt sau khi chunk đã được ghi bền vững.
- duplicate sequence cùng checksum trả lại receipt cũ.
- duplicate sequence nhưng nội dung khác bị từ chối.
- finalization chỉ thành công khi đủ chunk và tổng byte/checksum hợp lệ.
- session có expiry, quota và cleanup cho upload bỏ dở.

Không chỉ dựa vào thứ tự message trong một stream nếu client có thể reconnect. Sequence number giúp server phát hiện chunk thiếu, trùng hoặc đến sai thứ tự.

Nếu chunk được ghi vào object storage, checkpoint database phải phản ánh trạng thái thực tế của object. Cần xử lý crash giữa khi lưu object và ghi checkpoint bằng object key ổn định, checksum và quy trình reconciliation.

## 9. Backpressure và bounded buffering

Streaming giảm nhu cầu giữ toàn bộ payload trong memory, nhưng chỉ khi ứng dụng xử lý từng phần và kiểm soát tốc độ.

Nếu server đọc nhanh hơn database/object storage ghi được, hoặc producer tạo message nhanh hơn consumer xử lý, queue nội bộ có thể tăng vô hạn. Khi đó streaming vẫn gây OutOfMemoryError.

Thực hành:

- Dùng bounded queue nếu tách nhận và xử lý chunk sang worker.
- Chỉ yêu cầu/đọc thêm message khi downstream có capacity.
- Áp dụng flow control của gRPC khi dùng async streaming.
- Không tích lũy toàn bộ chunk trong List/ByteArrayOutputStream cho file lớn.
- Giới hạn số stream đồng thời và tổng byte đang được buffer.
- Cancel stream khi client mất quyền, vượt quota hoặc deadline.
- Theo dõi queue depth, in-flight bytes và thời gian xử lý mỗi chunk.

HTTP/2 flow control điều tiết byte trên transport; application backpressure vẫn cần để bảo vệ database, object storage và heap.

## 10. Cấu hình inbound message limit có chủ đích

gRPC Java cho phép cấu hình giới hạn message nhận vào. Ví dụ với Netty server:

```java
int maxInboundBytes = 8 * 1024 * 1024;

NettyServerBuilder server = NettyServerBuilder
    .forPort(8443)
    .maxInboundMessageSize(maxInboundBytes)
    .addService(uploadService);
```

Client cũng có inbound limit riêng cho response:

```java
ManagedChannel channel = NettyChannelBuilder
    .forAddress("orders.internal", 8443)
    .maxInboundMessageSize(8 * 1024 * 1024)
    .useTransportSecurity()
    .build();
```

Ví dụ minh họa API gRPC Java Netty; package/import và cách gắn builder vào Spring Boot phụ thuộc starter đang dùng. Trong Spring, cấu hình server/channel qua builder customizer hoặc properties được starter hỗ trợ để giữ lifecycle nhất quán.

Server inbound limit áp dụng cho request nhận từ client; client inbound limit áp dụng cho response nhận từ server. Tăng limit ở client không làm server tự chấp nhận request lớn hơn, và ngược lại.

Chọn giới hạn dựa trên contract và capacity test. Đừng đặt hàng trăm megabyte chỉ vì một request hiện tại bị RESOURCE_EXHAUSTED. Nếu cần giới hạn lớn cho một loại operation, cân nhắc endpoint/service riêng hoặc streaming thay vì nới giới hạn cho mọi RPC.

## 11. Compression không thay thế thiết kế payload

gzip hoặc compression khác có thể giảm số byte truyền qua network đối với dữ liệu nén tốt. Nhưng compression không loại bỏ chi phí:

- Client vẫn cần serialize message.
- Server vẫn cần decompress và parse.
- Payload sau giải nén vẫn tiêu thụ memory.
- CPU tăng do compress/decompress.
- Dữ liệu đã nén hoặc entropy cao có thể giảm rất ít.
- Payload không tin cậy có thể tạo áp lực tài nguyên khi giải nén.

Không tăng message size chỉ vì compressed bytes nhỏ. Cần hiểu limit áp dụng ở layer nào trong thư viện/driver đang dùng và test với payload nén thực tế. Giới hạn application theo uncompressed logical bytes và record count vẫn cần thiết.

Compression cũng có thể làm tăng latency cho message nhỏ; chỉ bật khi benchmark cho thấy lợi ích.

## 12. Giới hạn nghiệp vụ và bảo vệ tài nguyên

Transport message limit không thay thế application quota. Một message nhỏ vẫn có thể yêu cầu server làm công việc lớn, ví dụ page_size cực lớn, filter phức tạp hoặc lặp truy vấn tốn kém.

Đặt giới hạn cho:

- Số item tối đa trong repeated field.
- Tổng kích thước bytes/string trong request.
- Page size và page token validity.
- Số chunk, kích thước mỗi chunk và tổng upload size.
- Số stream/upload đồng thời theo principal/tenant.
- Thời gian xử lý và deadline.
- Số record được export/import trong một operation.
- Tổng memory/buffer có thể tiêu thụ.

Vượt giới hạn request có thể là INVALID_ARGUMENT nếu caller gửi giá trị vượt contract; vượt quota hoặc capacity có thể là RESOURCE_EXHAUSTED. Không dùng một status cho mọi loại giới hạn; chọn theo semantics công bố.

## 13. Schema evolution khi tách message

Khi refactor message lớn thành các request/response nhỏ hơn hoặc thêm pagination/streaming, cần giữ compatibility:

- Không đổi field number đã phát hành.
- Không tái sử dụng field number/name đã xóa; đánh dấu reserved.
- Thêm field mới theo hướng additive và có default semantics rõ.
- Giữ old RPC trong giai đoạn migration nếu client cũ còn dùng.
- Tạo RPC mới cho semantics khác thay vì âm thầm đổi ý nghĩa của field cũ.
- Dùng versioned package/service khi contract cần thay đổi không tương thích.
- Có telemetry về client version và usage trước khi loại bỏ API cũ.

Một migration có thể thêm ListOrdersPaged bên cạnh ListAllOrders cũ, chuyển client theo từng đợt rồi mới deprecate API cũ. Không thay response cũ từ “toàn bộ danh sách” sang “một trang” mà không đổi contract.

## 14. Quan sát message size và hiệu năng

Theo dõi kích thước request/response theo RPC method và phân vị, không chỉ trung bình:

- Serialized message bytes p50/p95/p99.
- Số item trong repeated fields.
- Chunk size và total upload bytes.
- RESOURCE_EXHAUSTED/message-too-large errors.
- Serialization/deserialization CPU và latency.
- Heap allocation, GC pause và in-flight bytes.
- Stream concurrency, queue depth và backpressure wait.
- RPC latency/deadline/cancellation theo method.

Không dùng user ID, resource ID hoặc upload ID làm metric label. Nếu cần điều tra một request cụ thể, dùng trace/log correlation với dữ liệu được mask.

Cảnh báo khi p99 message size tiến sát giới hạn, số lỗi message-too-large tăng hoặc heap/GC tăng theo concurrency. Một message lớn đơn lẻ có thể hợp lệ; nhiều message lớn đồng thời mới làm lộ rõ capacity issue.

## 15. Kiểm thử giới hạn và tải

Một bộ kiểm thử hữu ích nên bao gồm:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Request dưới giới hạn | RPC xử lý bình thường |
| Request vượt inbound limit server | Bị từ chối trước application handler theo behavior của runtime |
| Response vượt inbound limit client | Client nhận lỗi phù hợp, không treo call |
| Page size vượt quota | Server clamp hoặc trả INVALID_ARGUMENT theo contract |
| Repeated field rất lớn | Application giới hạn record count/bytes |
| Chunk đúng giới hạn | Streaming nhận và ghi từng phần |
| Chunk vượt giới hạn | Bị từ chối mà không làm cạn heap |
| Client chậm đọc | Backpressure không làm queue tăng vô hạn |
| Client ngắt giữa upload | Checkpoint cho phép resume không ghi trùng |
| Checksum sai | Chunk/finalize bị từ chối |
| Compression bật/tắt | CPU, latency và message limit được đo |
| Concurrent large RPC | Heap, GC, pool và p99 vẫn trong SLO |

Dùng payload sinh có kích thước xác định và load test với concurrency thực tế. Kiểm tra cả server và client inbound limit; test một phía không chứng minh phía còn lại được cấu hình đúng.

## 16. Checklist review

- Mỗi RPC có giới hạn số record, bytes hoặc page size rõ ràng.
- Request/response chỉ chứa dữ liệu cần cho use case.
- Collection lớn dùng cursor pagination hoặc streaming phù hợp.
- Binary lớn dùng object storage/reference hoặc chunked stream.
- Streaming chunk có size cap, sequence, checksum và resume semantics.
- Application backpressure và bounded buffering được triển khai.
- Client và server inbound message limits được cấu hình có chủ đích.
- Không nhầm message size với HTTP/2 frame size hoặc flow control.
- Compression được benchmark và không dùng để che payload không giới hạn.
- Quota theo tenant/principal bảo vệ CPU, heap, database và storage.
- Schema refactor giữ field number và compatibility.
- Metrics theo dõi message size, GC, stream concurrency và RESOURCE_EXHAUSTED.
- Có tests cho oversize, concurrency, slow consumer và interrupted upload.

Trong **SPRING_GRPC**, đặt message quá lớn để né thiết kế schema làm tăng memory pressure, latency và rủi ro lỗi dưới tải. Hãy giới hạn payload theo use case, dùng pagination cho collection, object storage cho file lớn và streaming chunk có checkpoint khi cần truyền liên tục. Cấu hình inbound message limit như hàng rào bảo vệ cuối cùng; nó không thay thế quota, backpressure hoặc một contract được thiết kế tốt.
