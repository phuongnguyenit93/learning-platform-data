# Không truyền payload lớn qua metadata

gRPC metadata được thiết kế để mang **thông tin điều khiển ngắn gắn với một lời gọi RPC**, chẳng hạn request ID, credentials, locale hoặc trace context. Metadata đi trong HTTP/2 headers/trailers và được xử lý ở ranh giới của call. Nó không phải kênh truyền file, JSON lớn hay dữ liệu nghiệp vụ.

Trong Spring gRPC, payload thuộc message Protocol Buffers. Khi cần truyền dữ liệu lớn hoặc liên tục, hãy cân nhắc message có trường bytes, client/server streaming hoặc lưu payload ở object storage rồi gửi tham chiếu qua RPC. Chọn đúng kênh giúp tránh vượt giới hạn header, giảm áp lực bộ nhớ và giữ cho việc retry, kiểm soát luồng, bảo mật dễ quản lý.

## 1. Metadata và payload có vai trò khác nhau

Một lời gọi gRPC có hai nhóm dữ liệu chính:

| Nhóm | Nơi truyền | Ví dụ | Đặc điểm |
| --- | --- | --- | --- |
| Metadata | Request/response headers và trailers | x-request-id, authorization, traceparent | Nhỏ, gắn với toàn bộ RPC, được xử lý ở ranh giới call |
| Payload | Protobuf request/response message | order, image_chunk, document_content | Dữ liệu nghiệp vụ, có schema và có thể gồm nhiều message |

Ví dụ một yêu cầu tải tài liệu:

```text
Request metadata:
  x-request-id: req-42
  authorization: Bearer <token>

Request message:
  document_id: "doc-100"
  content: <binary document bytes>
```

Request ID và credentials giúp server xác định ngữ cảnh, còn nội dung tài liệu là payload cần xử lý. Nếu đưa toàn bộ tài liệu vào metadata, hệ thống phải vận chuyển dữ liệu nghiệp vụ qua headers trước khi service nhận được request message.

Một nguyên tắc đơn giản: **metadata mô tả lời gọi; message mang nội dung lời gọi**. Nếu value thay đổi theo từng bản ghi trong stream, nó thuộc message Protobuf chứ không thuộc metadata.

## 2. Vì sao payload lớn trong metadata gây vấn đề?

Metadata được vận chuyển qua HTTP/2 headers/trailers. Kích thước của chúng bị giới hạn bởi nhiều thành phần trên đường đi: gRPC client, server, HTTP/2 implementation, reverse proxy, API gateway và load balancer. Giới hạn thực tế có thể khác nhau giữa môi trường phát triển và production.

Các rủi ro chính:

- **Vượt giới hạn header:** request có thể bị từ chối ở transport hoặc proxy trước khi tới server interceptor/service. Ứng dụng không nên giả định luôn nhận được một gRPC status cụ thể; kết quả phụ thuộc thành phần phát hiện giới hạn.
- **Tốn dung lượng hơn dự kiến:** binary metadata dùng biểu diễn Base64 trên đường truyền, làm tăng kích thước so với byte gốc. Base64 không phải mã hóa bảo mật.
- **Lặp dữ liệu ở mỗi RPC:** metadata gắn với từng call. Nếu gửi một cấu hình hoặc payload lớn trong mọi lời gọi, cùng dữ liệu có thể được truyền và xử lý lặp lại.
- **Tăng chi phí xử lý headers:** các thành phần trung gian phải parse, kiểm tra và có thể ghi log headers. Header lớn làm tăng chi phí bộ nhớ, CPU và độ trễ.
- **Khó kiểm soát retry và streaming:** metadata được gửi khi call bắt đầu, không phải cơ chế truyền từng phần có flow control ở cấp message.
- **Rủi ro log và bảo mật:** proxy, tracing agent hoặc debug logger có thể thu thập metadata. Payload nhạy cảm đặt trong headers dễ bị lộ ngoài dự kiến.

HTTP/2 có cơ chế nén header, nhưng điều đó **không biến headers thành nơi lưu payload lớn** và không loại bỏ giới hạn kích thước header list. Không nên dựa vào HPACK để gửi file hoặc dữ liệu nghiệp vụ.

Một số tài liệu gRPC khuyến nghị giới hạn request header ở mức nhỏ (ví dụ khoảng 8 KiB trong một số cấu hình mặc định), nhưng đây không phải con số bảo đảm cho mọi triển khai. Hãy kiểm tra giới hạn thực tế của thư viện và toàn bộ proxy/gateway đang sử dụng.

## 3. Chọn kênh truyền phù hợp

| Nhu cầu | Cách nên dùng | Vì sao |
| --- | --- | --- |
| Request ID, tenant đã được kiểm tra, locale | Metadata ASCII ngắn | Đây là ngữ cảnh của RPC |
| Dữ liệu byte nhỏ, có giới hạn rõ ràng và gắn với một request | Trường bytes trong Protobuf message | Payload nằm đúng vị trí và chịu message-size policy |
| Một payload vừa phải, một lần gửi/nhận | Unary RPC với message Protobuf | Đơn giản, dễ validate và xử lý |
| File lớn hoặc dữ liệu tạo thành nhiều phần | Client streaming hoặc server streaming | Truyền từng message, tận dụng flow control |
| Hai phía trao đổi dữ liệu liên tục | Bidirectional streaming | Mỗi message có thể được xử lý khi đến |
| File rất lớn, cần upload/download bền vững hoặc chia sẻ qua nhiều dịch vụ | Object storage/file service và RPC gửi tham chiếu | Tách đường truyền file khỏi control plane của gRPC |

Không có một ngưỡng byte chung đúng cho mọi hệ thống. Hãy xác định giới hạn theo message-size configuration, giới hạn của hạ tầng, bộ nhớ, độ trễ mục tiêu và số lượng request đồng thời.

## 4. Payload vừa phải: đặt trong Protobuf message

Nếu dữ liệu đủ nhỏ để nằm trong giới hạn message đã cấu hình, hãy khai báo nó trong hợp đồng .proto. Ví dụ:

```protobuf
syntax = "proto3";

service DocumentService {
  rpc StoreDocument(StoreDocumentRequest) returns (StoreDocumentReply);
}

message StoreDocumentRequest {
  string document_id = 1;
  string media_type = 2;
  bytes content = 3;
}

message StoreDocumentReply {
  string document_id = 1;
  int64 stored_bytes = 2;
}
```

Client gửi nội dung trong request message; server validate kích thước, media type, quyền truy cập và xử lý dữ liệu. Metadata vẫn chỉ giữ thông tin call-level như request ID hoặc authorization.

Ví dụ này phù hợp khi payload vừa phải và việc xử lý có thể thực hiện trong một RPC. Trường bytes không làm payload miễn nhiễm với giới hạn: gRPC vẫn áp dụng giới hạn kích thước message, và việc giữ toàn bộ byte trong bộ nhớ có thể gây áp lực khi nhiều request chạy đồng thời.

## 5. Payload lớn: dùng streaming và chia chunk có kiểm soát

Khi file lớn hoặc cần truyền theo từng phần, client streaming thường phù hợp: client gửi nhiều request message trên một RPC, server xử lý từng chunk và trả một kết quả khi hoàn tất.

Một hợp đồng minh họa:

```protobuf
syntax = "proto3";

service UploadService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}

message UploadChunk {
  string upload_id = 1;
  uint64 sequence = 2;
  bytes data = 3;
  bytes chunk_sha256 = 4;
  bool last = 5;
}

message UploadResult {
  string upload_id = 1;
  uint64 stored_bytes = 2;
  bytes content_sha256 = 3;
}
```

Các trường upload_id, sequence, checksum và last là một thiết kế ứng dụng mẫu. Chúng giúp server:

1. Nhận diện phiên upload và kiểm tra caller có quyền ghi vào đích lưu trữ.
2. Phát hiện chunk thiếu, lặp hoặc sai thứ tự theo chính sách đã định nghĩa.
3. Xác minh checksum của từng chunk và checksum toàn nội dung khi hoàn tất.
4. Chỉ đánh dấu upload hoàn tất khi đã nhận đủ dữ liệu và xác minh thành công.

Client streaming trong Java có thể gửi các message qua observer do generated stub cung cấp:

```java
StreamObserver<UploadChunk> request =
    asyncStub.upload(new StreamObserver<UploadResult>() {
        @Override
        public void onNext(UploadResult result) {
            // Kiểm tra kết quả cuối cùng từ server.
        }

        @Override
        public void onError(Throwable error) {
            // Xử lý lỗi; chỉ retry theo chính sách upload.
        }

        @Override
        public void onCompleted() {
            // RPC đã hoàn tất.
        }
    });

long sequence = 0;
while (hasMoreChunks()) {
    byte[] chunk = readNextChunk();
    request.onNext(UploadChunk.newBuilder()
        .setUploadId(uploadId)
        .setSequence(sequence++)
        .setData(ByteString.copyFrom(chunk))
        .build());
}
request.onCompleted();
```

Đoạn code là phác thảo luồng client; hasMoreChunks(), readNextChunk(), uploadId và việc tính checksum thuộc ứng dụng. Với dữ liệu lớn, không đọc toàn bộ file vào một mảng trước khi gửi. Dùng buffer có giới hạn và tuân thủ cơ chế flow control/backpressure của gRPC để không tạo hàng đợi chunk không giới hạn trong bộ nhớ.

### Những điều cần thiết kế cho streaming upload

- **Chunk size:** chọn theo giới hạn message, throughput, bộ nhớ và độ trễ. Chunk quá nhỏ tăng overhead; chunk quá lớn tăng bộ nhớ mỗi call và nguy cơ vượt giới hạn message.
- **Flow control:** không phát chunk nhanh hơn khả năng nhận/ghi của server. Với API async, dùng cơ chế readiness/flow control của gRPC thay vì tự tích lũy vô hạn trong queue.
- **Tính toàn vẹn:** kiểm tra kích thước, sequence và checksum; checksum không thay thế xác thực caller.
- **Retry/resume:** xác định upload ID có idempotent không, chunk đã ghi được nhận diện thế nào và client tiếp tục từ sequence nào sau lỗi.
- **Hủy và timeout:** xử lý client cancel, deadline, server shutdown và dọn phần upload chưa hoàn tất.
- **Giới hạn tài nguyên:** giới hạn kích thước tổng, số upload đồng thời, thời gian tồn tại và dung lượng tạm.

Không cần tự chia chunk nếu payload vừa đủ nhỏ cho một message và không có yêu cầu resume/streaming. Streaming là lựa chọn kiến trúc, không phải lý do để làm mọi request phức tạp hơn.

## 6. Payload rất lớn: lưu ngoài và gửi tham chiếu

Với file rất lớn, cần resume, chia sẻ qua nhiều dịch vụ hoặc lưu lâu dài, thường hiệu quả hơn khi dùng object storage/file service:

1. Client gọi RPC CreateUpload để xin một upload session hoặc URL có phạm vi và thời hạn giới hạn.
2. Client truyền file trực tiếp tới object storage bằng giao thức phù hợp.
3. Client gọi RPC CompleteUpload với upload ID/object key và checksum.
4. Server xác minh quyền, trạng thái upload, checksum và metadata của object trước khi đánh dấu hoàn tất.
5. Các RPC nghiệp vụ sau chỉ truyền document ID hoặc object reference ngắn.

Minh họa:

```text
Client              Spring gRPC service              Object storage
  |                         |                              |
  |-- CreateUpload -------->|                              |
  |<-- upload session ------|                              |
  |                                                       |
  |---------------------- upload file ------------------->|
  |<--------------------- upload result ------------------|
  |                         |                              |
  |-- CompleteUpload ------>|                              |
  |                         |-- verify object/checksum --->|
  |<-- document ID ---------|                              |
  |                         |                              |
  |-- GetDocument(documentId) ---------------------------->|
```

Nếu dùng pre-signed URL, giới hạn method, object key, kích thước, content type và thời hạn; không ghi URL có chữ ký vào log. URL là credential có thời hạn, ai sở hữu URL trong thời gian hiệu lực có thể sử dụng trong phạm vi được cấp. Server cần xác minh quyền ở cả bước tạo session và hoàn tất.

RPC gửi tham chiếu không có nghĩa server tin mọi object key do client cung cấp. Hãy ràng buộc object với upload session, tenant và principal đã xác minh để tránh truy cập chéo dữ liệu.

## 7. Giới hạn metadata và message là hai cấu hình khác nhau

Không nhầm giới hạn header với giới hạn Protobuf message:

| Giới hạn | Áp dụng cho | Cần kiểm soát |
| --- | --- | --- |
| Metadata/header list size | Request headers và response headers/trailers | Tổng key/value, binary metadata sau biểu diễn trên đường truyền và giới hạn proxy |
| Inbound message size | Message nhận vào server/client | Kích thước từng Protobuf message |
| Outbound message size | Message gửi ra server/client | Kích thước từng Protobuf message |
| Tổng upload/download | Toàn phiên truyền | Tổng byte, số chunk, thời lượng và dung lượng tạm |

Tăng maxInboundMessageSize không làm tăng giới hạn metadata. Tăng giới hạn header cũng không phải cách sửa đúng cho một file lớn. Các giới hạn được cấu hình ở transport/server/client và proxy tùy phiên bản; cần đồng bộ chúng nhưng vẫn giữ giá trị hữu hạn.

Nếu hệ thống thực sự cần tăng giới hạn cho một trường hợp có kiểm soát, hãy:

- Đo kích thước thực tế và xác định thành phần nào từ chối request.
- Đặt ngưỡng rõ ràng ở client, server và gateway/proxy.
- Giới hạn số request đồng thời và bộ nhớ dành cho mỗi message.
- Kiểm tra status/transport error khi payload vượt ngưỡng.
- Theo dõi phân vị kích thước message, tỷ lệ bị từ chối và mức sử dụng bộ nhớ.

Đừng đặt giới hạn vô hạn để tránh lỗi; điều đó mở đường cho request quá lớn gây cạn bộ nhớ hoặc làm giảm khả năng phục vụ các call khác.

## 8. Bảo mật, lỗi và kiểm thử

### Bảo mật

- Metadata không phải kênh bí mật. Dùng TLS/mTLS cho kết nối và credentials phù hợp cho xác thực.
- Không đưa access token, dữ liệu cá nhân hoặc payload nhạy cảm vào metadata chỉ vì nó tiện.
- Kiểm tra quyền trước khi ghi file hoặc tạo object reference; tenant ID do client gửi không tự chứng minh quyền.
- Đặt giới hạn tổng byte, chunk size, thời gian upload và số phiên đồng thời để chống DoS.
- Làm sạch file name/content type, kiểm tra nội dung thực tế và không tin extension do client khai báo.
- Không log nội dung payload, pre-signed URL hoặc toàn bộ metadata. Log ID, kích thước, thời lượng và kết quả đã được cho phép.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Server interceptor không được gọi | Proxy/transport từ chối headers trước khi RPC tới server | Kiểm tra log gateway, giới hạn header và kích thước request |
| RPC bị từ chối khi metadata tăng | Tổng headers vượt giới hạn một thành phần | Giảm metadata; chuyển payload vào message/stream |
| Message bị từ chối dù metadata nhỏ | Vượt inbound/outbound message size | Điều chỉnh message size có giới hạn hoặc chuyển sang streaming |
| Bộ nhớ tăng khi upload | Client/server giữ nhiều chunk cùng lúc | Buffer hữu hạn, flow control, ghi theo luồng |
| Retry tạo file trùng | Chunk/upload chưa idempotent | Dùng upload ID, sequence và trạng thái resume |
| File lưu không đầy đủ | Thiếu chunk hoặc không xác minh checksum cuối | Kiểm tra sequence, tổng byte và checksum trước khi complete |
| Tải qua URL truy cập object của tenant khác | Không ràng buộc object với principal/tenant | Kiểm tra quyền ở create, complete và download |

### Ma trận kiểm thử

| Ca kiểm thử | Kết quả cần xác minh |
| --- | --- |
| Metadata nhỏ hợp lệ | Server nhận đúng key/value |
| Metadata tăng dần đến giới hạn | Thành phần giới hạn từ chối có kiểm soát; service không giả định đã nhận request |
| Binary metadata | Dữ liệu byte nhỏ được khôi phục đúng, không Base64 thủ công |
| Unary message dưới ngưỡng | RPC hoàn tất và payload nguyên vẹn |
| Unary message vượt ngưỡng | Nhận lỗi phù hợp; không tạo dữ liệu một phần ngoài ý muốn |
| Streaming nhiều chunk | Thứ tự, tổng byte và checksum đúng |
| Chunk lặp/thiếu/sai checksum | Upload bị từ chối hoặc resume theo chính sách |
| Client hủy/deadline hết | Server dừng công việc và dọn tài nguyên tạm |
| Upload đồng thời nhiều tenant | Không trộn object, session hoặc dữ liệu giữa tenant |
| Object storage URL hết hạn/sai quyền | Upload/download bị từ chối |
| Proxy và TLS | Giới hạn, bảo mật và hành vi lỗi khớp môi trường triển khai |

Nên có cả unit test cho bộ kiểm tra chunk/checksum, integration test cho gRPC streaming và kiểm thử qua proxy thực tế. In-process transport hữu ích để kiểm tra logic message/interceptor nhưng không mô phỏng đầy đủ giới hạn HTTP/2 hoặc gateway.

## 9. Bài tập vận dụng

Một dịch vụ Spring gRPC nhận file PDF để lưu hóa đơn. Client hiện đang gửi toàn bộ file trong metadata x-invoice-bin, khiến một số request bị từ chối ở gateway.

**Yêu cầu:**

1. Giải thích vì sao binary metadata không phù hợp với PDF lớn và vì sao Base64 làm tăng kích thước vận chuyển.
2. Đề xuất schema Protobuf dùng unary message nếu file nhỏ và client streaming với chunk nếu file lớn.
3. Xác định chunk size, tổng dung lượng tối đa, checksum, sequence, upload ID và chính sách resume.
4. Đề xuất object storage/pre-signed URL nếu file rất lớn hoặc cần tải lên bền vững.
5. Phân biệt giới hạn metadata, giới hạn từng Protobuf message và giới hạn tổng upload.
6. Thiết kế test cho metadata vượt ngưỡng, message vượt ngưỡng, chunk thiếu, checksum sai, hủy call và truy cập chéo tenant.

**Câu hỏi tự kiểm tra:**

- Metadata gắn với toàn RPC khác payload Protobuf như thế nào?
- Vì sao HPACK không làm metadata trở thành kênh truyền file?
- Khi nào nên dùng unary bytes, khi nào dùng streaming?
- Binary metadata có thể chứa file lớn an toàn hơn ASCII metadata không?
- Tại sao cần giới hạn cả chunk size lẫn tổng upload size?
- Vì sao tăng message-size limit không giải quyết header-size limit?
- Khi dùng pre-signed URL, cần ràng buộc những quyền và thời hạn nào?

**Ghi nhớ:** Không truyền payload lớn qua metadata. Hãy giữ headers/trailers cho thông tin ngắn của RPC; đặt payload vừa phải trong Protobuf message, dữ liệu lớn trong streaming với flow control và kiểm tra toàn vẹn, hoặc chuyển file rất lớn sang object storage rồi trao đổi tham chiếu qua gRPC. Cấu hình giới hạn hữu hạn ở cả metadata, message và tổng phiên truyền để bảo vệ độ tin cậy của dịch vụ.
