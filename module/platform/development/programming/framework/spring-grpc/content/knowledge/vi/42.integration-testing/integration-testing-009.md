# Kiểm thử message size limit

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích giới hạn kích thước message gRPC và phân biệt nó với giới hạn metadata.
- Xác định endpoint nào kiểm tra message trong từng chiều request/response.
- Cấu hình maxInboundMessageSize cho gRPC server và client.
- Dùng Protobuf getSerializedSize() để tạo test dữ liệu sát ngưỡng theo byte.
- Kiểm thử message dưới ngưỡng, đúng ngưỡng và vượt ngưỡng qua TCP.
- Kiểm thử giới hạn cho unary và streaming RPC.
- Xử lý status RESOURCE_EXHAUSTED, memory pressure và giới hạn tổng tài nguyên của stream.

## 1. Vì sao cần giới hạn kích thước message?

gRPC truyền message Protobuf qua HTTP/2. Một request hoặc response quá lớn có thể tiêu thụ nhiều bộ nhớ khi nhận, giải mã, parse thành object và giữ trong hàng đợi xử lý. Khi nhiều RPC lớn đến cùng lúc, server có thể tăng heap nhanh, tạo GC pressure hoặc cạn tài nguyên.

maxInboundMessageSize đặt giới hạn cho kích thước của một message mà endpoint nhận. Đây là giới hạn ở phía nhận: server kiểm tra request từ client; client kiểm tra response từ server. Giới hạn này bảo vệ transport khỏi một message đơn quá lớn, nhưng không tự giới hạn tổng số byte của cả stream hoặc toàn bộ công việc đang chờ trong ứng dụng.

Trong **SPRING_GRPC**, cần kiểm tra giới hạn bằng integration test qua generated stub và server đang chạy. Gọi trực tiếp service method sẽ bỏ qua transport và không xác minh được hành vi từ chối message quá lớn.

## 2. Message size khác payload size và metadata size

Một Protobuf message được serialize thành chuỗi byte theo wire format. Kích thước serialized bao gồm tag, length prefix, giá trị field và các byte encoding cần thiết. Vì vậy, độ dài của một bytes field hoặc chuỗi UTF-8 không nhất thiết bằng getSerializedSize().

Các khái niệm cần phân biệt:

| Giới hạn | Nội dung được giới hạn | Cấu hình gRPC Java thường dùng |
| --- | --- | --- |
| Inbound message size | Một message Protobuf nhận vào | maxInboundMessageSize(...) |
| Inbound metadata size | Metadata/header của call | maxInboundMetadataSize(...) |
| Application queue/buffer | Tổng dữ liệu ứng dụng đang giữ | Bounded queue, byte budget, admission control |
| Stream/business quota | Tổng số message hoặc tổng byte của một phiên | Logic nghiệp vụ và state theo call |

Không dùng maxInboundMetadataSize để giới hạn request body. Ngược lại, tăng message limit không cho phép metadata tùy ý lớn. Hai loại giới hạn bảo vệ hai vùng dữ liệu khác nhau.

## 3. Giới hạn được áp dụng ở phía nhận

Mỗi chiều truyền có endpoint nhận riêng:

| RPC direction | Endpoint nhận message | Giới hạn cần kiểm tra |
| --- | --- | --- |
| Client gửi request tới server | gRPC server | Server maxInboundMessageSize |
| Server gửi response tới client | gRPC client channel | Client maxInboundMessageSize |
| Client-streaming request | gRPC server, cho từng request message | Server limit |
| Server-streaming response | gRPC client, cho từng response message | Client limit |
| Bidirectional stream | Cả server và client | Cấu hình limit ở cả hai phía |

Server inbound limit không phải giới hạn outbound response của server. Nếu server gửi một response quá lớn, giới hạn inbound của client mới là nơi quyết định client có chấp nhận message đó hay không.

Với stream, giới hạn thường áp dụng cho từng message, không phải tổng byte của cả phiên. Một stream gồm nhiều message nhỏ vẫn có thể tích lũy lượng dữ liệu lớn; ứng dụng phải đặt thêm quota theo stream, queue và thời gian.

## 4. Cấu hình server inbound message size

Với gRPC Java Netty server tự quản lý, cấu hình giới hạn trước khi build:

~~~java
private static final int SERVER_MAX_MESSAGE_BYTES = 1024 * 1024;

Server server = NettyServerBuilder.forPort(0)
    .maxInboundMessageSize(SERVER_MAX_MESSAGE_BYTES)
    .addService(inventoryService)
    .build()
    .start();
~~~

Giá trị trong ví dụ là 1 MiB để minh họa; production phải chọn theo kích thước payload hợp lệ, memory budget và concurrency dự kiến. Không tăng giới hạn chỉ để làm một test lớn pass.

Trong Spring gRPC, server có thể do starter auto-configure. Hãy đặt property hoặc customizer đúng theo starter và phiên bản thực tế. Tên property không đồng nhất giữa mọi starter; không sao chép một key cấu hình chưa được xác minh. Integration test nên lấy port từ server do Spring quản lý, không tạo server thứ hai chỉ để đổi giới hạn.

## 5. Cấu hình client inbound message size

Client channel kiểm soát kích thước response mà nó nhận:

~~~java
private static final int CLIENT_MAX_MESSAGE_BYTES = 1024 * 1024;

ManagedChannel channel = NettyChannelBuilder
    .forAddress("127.0.0.1", grpcServer.port())
    .maxInboundMessageSize(CLIENT_MAX_MESSAGE_BYTES)
    .usePlaintext()
    .build();
~~~

Nếu dùng transport builder khác, kiểm tra API tương ứng của phiên bản gRPC Java. Đặt giới hạn rõ ràng ở client test để kết quả không phụ thuộc default của dependency.

Không nhầm client inbound limit với giới hạn message mà client gửi đi. Khi client gửi request lớn, server là endpoint nhận và server limit mới quyết định request có được chấp nhận hay không.

## 6. Đo đúng kích thước Protobuf

Dùng getSerializedSize() trên generated message để biết kích thước wire-format của message:

~~~java
UploadRequest request = UploadRequest.newBuilder()
    .setUploadId("batch-17")
    .setPayload(ByteString.copyFrom(payload))
    .build();

int serializedBytes = request.getSerializedSize();
~~~

payload.length chỉ là kích thước riêng của field bytes. Message còn có field tag, length prefix và các field khác. Test boundary nên so sánh getSerializedSize() với configured limit.

Không cần gọi toByteArray() chỉ để đo kích thước vì thao tác đó tạo thêm một bản sao byte array. Với message lớn, bản sao tạm có thể làm tăng memory pressure ngay trong test.

## 7. Thiết kế message test sát ngưỡng

Một test nên có ít nhất ba trường hợp:

- Message nhỏ hơn limit: được chấp nhận.
- Message có serialized size bằng limit: được chấp nhận nếu transport/API quy định giới hạn bao gồm giá trị bằng ngưỡng.
- Message lớn hơn limit ít nhất một byte: bị từ chối.

Ví dụ helper tạo request và xác nhận size trước khi gửi:

~~~java
UploadRequest requestWithPayload(byte[] payload) {
    return UploadRequest.newBuilder()
        .setUploadId("boundary-test")
        .setPayload(ByteString.copyFrom(payload))
        .build();
}

assertTrue(requestWithPayload(payloadBelow)
    .getSerializedSize() < SERVER_MAX_MESSAGE_BYTES);

assertEquals(SERVER_MAX_MESSAGE_BYTES,
    requestAtLimit.getSerializedSize());

assertTrue(requestWithPayload(payloadAbove)
    .getSerializedSize() > SERVER_MAX_MESSAGE_BYTES);
~~~

Không giả định payload length bằng message size. Nếu cần tạo chính xác message N byte, tăng/giảm payload và đo lại getSerializedSize() cho đến khi đạt ngưỡng. Cũng nên kiểm tra nhiều kiểu field như string, bytes và repeated field vì varint/length prefix có thể làm kích thước tăng theo bậc.

## 8. Kiểm thử request vượt giới hạn ở server

Khi client gửi request lớn hơn server inbound limit, server transport từ chối message trước khi service handler xử lý. Client thường nhận status RESOURCE_EXHAUSTED.

~~~java
@Test
void rejectsRequestLargerThanServerLimit() {
    UploadRequest oversized = requestWithPayload(payloadAboveLimit);
    assertTrue(oversized.getSerializedSize() > SERVER_MAX_MESSAGE_BYTES);

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.uploadUnary(oversized));

    assertEquals(
        Status.Code.RESOURCE_EXHAUSTED,
        Status.fromThrowable(error).getCode());
    assertEquals(0, uploadService.invocationCount());
}
~~~

Counter/spy xác nhận handler không được gọi là bằng chứng quan trọng: request đã bị transport từ chối trước business logic. Không chỉ assert rằng client nhận exception, vì lỗi có thể đến từ validation trong service thay vì size limit.

Status và mô tả lỗi cụ thể có thể khác theo transport/version; nên assert status code và hành vi handler, không phụ thuộc toàn bộ error string.

## 9. Kiểm thử response vượt giới hạn ở client

Để kiểm tra client inbound limit, server trả response lớn hơn giới hạn client channel. Server có thể đã chạy business method và tạo response; client transport mới là phía từ chối message.

~~~java
ManagedChannel smallLimitChannel = NettyChannelBuilder
    .forAddress("127.0.0.1", grpcServer.port())
    .maxInboundMessageSize(CLIENT_MAX_MESSAGE_BYTES)
    .usePlaintext()
    .build();

InventoryGrpc.InventoryBlockingStub smallLimitStub =
    InventoryGrpc.newBlockingStub(smallLimitChannel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);

StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> smallLimitStub.download(
        DownloadRequest.getDefaultInstance()));

assertEquals(
    Status.Code.RESOURCE_EXHAUSTED,
    Status.fromThrowable(error).getCode());
~~~

Đóng smallLimitChannel trong finally hoặc teardown. Test này chứng minh client từ chối response quá lớn; nó không chứng minh server không thực hiện nghiệp vụ. Với operation có side effect, cần xem xét idempotency và không retry mù quáng sau lỗi nhận response.

## 10. Kiểm thử streaming message size

Giới hạn inbound message áp dụng cho từng message trong stream:

- Client-streaming: server kiểm tra từng request message.
- Server-streaming: client kiểm tra từng response message.
- Bidirectional: mỗi phía kiểm tra message nhận từ phía kia.

Một test client-streaming có thể gửi message nhỏ trước, sau đó gửi một message vượt ngưỡng. Stream phải kết thúc bằng lỗi; server không được tiếp tục xử lý message tiếp theo sau khi transport đã đóng call.

Với server-streaming, test cần ghi nhận response hợp lệ trước message quá lớn (nếu có), rồi xác nhận terminal error. Client không nên coi stream hoàn tất bình thường chỉ vì đã nhận một vài message đầu.

Message limit không giới hạn tổng số message. Nếu mỗi message 100 KiB và stream gửi hàng nghìn message, tổng dữ liệu vẫn có thể rất lớn dù từng message nằm dưới ngưỡng.

## 11. Compression và kích thước sau giải nén

Compression làm giảm số byte truyền trên mạng nhưng không làm cho message sau giải nén nhỏ đi. Khi đánh giá giới hạn, cần quan tâm kích thước message mà receiver phải giải mã và parse, không chỉ số byte nén trên wire.

Nếu ứng dụng bật gzip hoặc compressor khác, hãy thêm test có compression và payload có tỷ lệ nén cao. Xác nhận receiver vẫn áp dụng message limit phù hợp và không chấp nhận dữ liệu sau giải nén vượt quá ngân sách thiết kế.

Không tự viết test dựa trên kích thước frame HTTP/2 hoặc kích thước byte nén để thay thế getSerializedSize(). Protobuf message size, compression và HTTP/2 framing là các lớp khác nhau.

## 12. Message size không thay thế memory budget

Serialized size không bằng heap footprint. Khi nhận message, runtime có thể giữ buffer, bản giải mã và object graph Protobuf; ứng dụng còn có thể copy dữ liệu vào queue hoặc domain object.

Do đó:

- Chọn message limit theo heap budget và số RPC đồng thời.
- Dùng bounded queue và byte budget cho công việc chờ.
- Giới hạn tổng byte hoặc số phần tử trong một stream.
- Áp dụng deadline và cancellation để giải phóng call kéo dài.
- Tránh copy message lớn nhiều lần; dùng streaming/chunking khi phù hợp.
- Ghi metric về message size, rejection count và queue depth mà không log payload nhạy cảm.

Nếu nghiệp vụ cần truyền file hoặc blob lớn, thường nên chia thành chunk có sequence/offset và giới hạn từng chunk. Server cần kiểm tra tổng kích thước upload, số chunk, quota user và thời gian hoàn tất.

## 13. Phân biệt message limit với metadata limit

Metadata được gửi trong HTTP/2 headers/trailers và có giới hạn riêng. Ví dụ authorization token, trace ID hoặc tenant ID là metadata; chúng không thuộc Protobuf message body.

Nếu metadata vượt giới hạn, call có thể bị từ chối trước khi method handler chạy, nhưng đó không phải bằng chứng maxInboundMessageSize hoạt động. Tương tự, request body vượt message limit không nên được xử lý bằng cách tăng maxInboundMetadataSize.

Test hai giới hạn riêng biệt nếu ứng dụng cần kiểm tra cả hai. Với auth metadata, giữ token ngắn và không dùng message limit lớn để che một metadata/header quá lớn.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ cấu hình server limit | Client vẫn có thể từ chối response lớn theo limit riêng | Cấu hình inbound limit ở cả hai receiver. |
| Nghĩ server inbound limit giới hạn response outbound | Test response không phản ánh cấu hình client | Dùng client maxInboundMessageSize cho response. |
| So payload length với message limit | Tính sai do tag/length prefix/field khác | Dùng getSerializedSize(). |
| Chỉ test message rất lớn | Bỏ sót lỗi tại boundary | Test dưới ngưỡng, đúng ngưỡng và vượt ngưỡng. |
| Chỉ assert exception | Không biết transport hay business handler từ chối | Assert status và invocation counter. |
| Coi stream limit là tổng byte toàn stream | Nhiều message nhỏ có thể tích lũy quá nhiều dữ liệu | Thêm quota tổng stream và byte budget. |
| Bỏ qua compression | Không kiểm tra kích thước sau giải nén | Test compressor và payload nén cao. |
| Nhầm message limit với metadata limit | Cấu hình sai lớp bảo vệ | Kiểm tra maxInboundMetadataSize riêng. |
| Tăng limit để làm test pass | Tăng memory pressure và rủi ro DoS | Chọn giới hạn theo contract và ngân sách tài nguyên. |

## 15. Ma trận kiểm thử message size

Một bộ integration test nên có:

1. Unary request nhỏ hơn server limit: thành công.
2. Unary request đúng server limit: xác nhận hành vi boundary.
3. Unary request lớn hơn server limit: RESOURCE_EXHAUSTED, handler không chạy.
4. Unary response lớn hơn client limit: client nhận lỗi size, xác nhận server method đã được gọi.
5. Client-streaming có một request message vượt limit: stream kết thúc bằng lỗi.
6. Server-streaming có một response message vượt client limit: client không nhận stream completion bình thường.
7. Bidirectional stream kiểm tra limit độc lập ở cả hai chiều.
8. Compression-enabled test kiểm tra payload sau giải nén.
9. Metadata vượt ngưỡng được test riêng với inbound metadata limit.
10. Queue/stream quota được kiểm tra riêng để giới hạn tổng dữ liệu tích lũy.

Mỗi test cần đặt deadline, đóng channel và dùng server lifecycle ổn định. Không chia sẻ mutable counter giữa các test song song nếu không có đồng bộ hoặc reset rõ ràng.

## 16. Bài tập thực hành

Tạo integration test cho một service upload/download:

1. Cấu hình server inbound message limit và client inbound message limit bằng giá trị tường minh.
2. Tạo request Protobuf có bytes payload và đo bằng getSerializedSize().
3. Gửi request dưới ngưỡng, đúng ngưỡng và vượt ngưỡng; kiểm tra response/status.
4. Dùng invocation counter xác nhận request vượt ngưỡng không đi vào service handler.
5. Tạo response lớn hơn client limit và xác nhận client từ chối.
6. Lặp lại với client-streaming/server-streaming để kiểm tra từng message.
7. Thử compression và kiểm tra giới hạn khi receiver giải mã message.
8. Đặt giới hạn tổng upload/queue riêng với per-message limit.
9. Đóng channel và để Spring quản lý server shutdown.

**Tiêu chí hoàn thành:** test xác định đúng receiver áp dụng limit, đo đúng serialized size, phân biệt message với metadata, xác nhận status/rejection ở transport và kiểm soát tổng tài nguyên của stream.

## 17. Ghi nhớ

- maxInboundMessageSize giới hạn một message ở endpoint nhận; server kiểm tra request, client kiểm tra response.
- Client và server cần cấu hình inbound limit độc lập theo hướng dữ liệu.
- Dùng Protobuf getSerializedSize() để kiểm tra byte wire-format; payload length không phải toàn message size.
- Test dưới ngưỡng, tại ngưỡng và vượt ngưỡng; xác minh status cùng việc handler có được gọi hay không.
- Với streaming, giới hạn áp dụng theo từng message; cần quota riêng cho tổng stream và queue.
- Compression không loại bỏ nhu cầu giới hạn message sau giải nén.
- Metadata có giới hạn riêng, ví dụ maxInboundMetadataSize.
- Message size không đại diện heap footprint; thiết kế thêm byte budget, backpressure, deadline và cancellation.
- Chọn limit theo hợp đồng API và ngân sách tài nguyên, không tăng tùy tiện để vượt qua test.

Kiểm thử message size limit giúp dịch vụ Spring gRPC từ chối payload vượt khả năng tiếp nhận ở đúng endpoint, bảo vệ bộ nhớ và giữ hành vi unary/streaming nhất quán khi tải dữ liệu lớn.
