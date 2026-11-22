# Giới hạn outbound message size

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích giới hạn kích thước outbound message và xác định endpoint nào thực sự kiểm tra giới hạn.
- Phân biệt kích thước message gửi đi với inbound limit của peer, HTTP/2 frame size và flow-control window.
- Kiểm tra kích thước serialized của message Protobuf trước khi gửi bằng Java.
- Thiết kế giới hạn outbound cho unary và streaming RPC, kể cả khi message được tạo bất đồng bộ.
- Chọn cách xử lý payload vượt ngưỡng và thiết kế chunk cho dữ liệu lớn.
- Kết hợp message-size guard với queue, byte budget, compression và kiểm thử để tránh lỗi ở runtime.

## 1. Outbound message size là gì?

Outbound message là message mà endpoint hiện tại gửi cho peer. Ở server, đó thường là response; ở client, đó thường là request. **Outbound message size** là kích thước dữ liệu Protobuf đã serialize mà endpoint chuẩn bị truyền trong một lần gửi.

Một message quá lớn có thể làm tăng bộ nhớ cần cho object, vùng đệm serialize, buffer của gRPC và dữ liệu đang chờ truyền. Nếu peer không chấp nhận kích thước đó, RPC có thể kết thúc bằng lỗi sau khi sender đã bắt đầu gửi. Trong streaming, một message vượt ngưỡng có thể làm hỏng toàn bộ RPC dù các message trước đã được xử lý.

Trong **SPRING_GRPC**, cần xem xét kích thước outbound ở cả client và server. Client có thể gửi request lớn tới server; server có thể trả response lớn cho client. Endpoint gửi nên kiểm tra kích thước trước khi gửi, đồng thời endpoint nhận vẫn phải cấu hình inbound limit để tự bảo vệ.

## 2. Receiver mới là nơi thực thi inbound limit

Kích thước mà sender có thể gửi thành công phụ thuộc giới hạn nhận của peer. Ví dụ:

| Chiều truyền | Outbound ở đâu? | Inbound limit được kiểm tra ở đâu? |
| --- | --- | --- |
| Client gửi request | Client | Server |
| Server gửi response | Server | Client |
| Client-streaming | Client gửi từng request chunk | Server nhận từng chunk |
| Server-streaming | Server gửi từng response | Client nhận từng response |
| Bidirectional | Cả hai phía đều gửi | Mỗi phía kiểm tra message nhận từ phía kia |

Inbound limit là cấu hình cục bộ của endpoint nhận. Không giả định gRPC tự thương lượng một giới hạn message chung giữa hai peer qua HTTP/2. Server có thể không biết trước cấu hình inbound thực tế của client; client cũng không nhất thiết biết giới hạn server.

Do đó, sender nên có giới hạn theo hợp đồng ứng dụng và kiểm tra trước khi gọi send. Receiver vẫn phải enforce inbound limit vì peer có thể là client khác phiên bản hoặc không tuân theo kiểm tra phía sender.

## 3. Kích thước serialized khác kích thước object

Một message Java có thể giữ dữ liệu trong nhiều object và mảng byte. Kích thước heap của object không bằng kích thước Protobuf wire:

- **Heap size** gồm object header, reference, collection backing array, byte array và overhead runtime.
- **Serialized size** là số byte cần để mã hóa message theo binary Protobuf.
- **Wire bytes** còn chịu framing gRPC, HTTP/2 frame và có thể compression.

Với Protobuf Java, các message sinh mã thường cung cấp **getSerializedSize()**. Giá trị này hữu ích để kiểm tra payload trước khi gửi:

~~~java
UploadRequest request = buildRequest();
int serializedBytes = request.getSerializedSize();

System.out.println("Serialized bytes: " + serializedBytes);
~~~

Không dùng kích thước file gốc hoặc độ dài một field làm đại diện cho toàn message. Tag field, length prefix, nested message và các field khác cũng góp phần vào serialized size.

## 4. Đặt giới hạn ứng dụng trước khi gửi

Một cách rõ ràng là định nghĩa ngưỡng outbound theo hợp đồng dịch vụ và kiểm tra message trước khi chuyển cho stub hoặc observer:

~~~java
import com.google.protobuf.MessageLite;

final class MessageSizeGuard {
    private final int maxBytes;

    MessageSizeGuard(int maxBytes) {
        if (maxBytes <= 0) {
            throw new IllegalArgumentException("maxBytes must be positive");
        }
        this.maxBytes = maxBytes;
    }

    void check(MessageLite message) {
        int size = message.getSerializedSize();
        if (size > maxBytes) {
            throw new IllegalArgumentException(
                "Outbound message is " + size
                    + " bytes; limit is " + maxBytes);
        }
    }
}
~~~

Ví dụ client kiểm tra trước khi gọi unary RPC:

~~~java
MessageSizeGuard guard =
    new MessageSizeGuard(4 * 1024 * 1024);

CreateDocumentRequest request = buildRequest();
guard.check(request);

CreateDocumentResponse response = blockingStub.createDocument(request);
~~~

Đây là kiểm tra ở tầng ứng dụng, giúp phát hiện payload quá lớn sớm và tạo lỗi dễ hiểu cho caller. Nó không thay thế inbound limit ở server, vì client khác có thể bỏ qua guard này.

## 5. Server kiểm tra response trước khi onNext

Với server-streaming hoặc bidirectional streaming, kiểm tra từng response trước khi gửi:

~~~java
private static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

void sendUpdate(
        PriceUpdate update,
        StreamObserver<PriceUpdate> responseObserver) {

    int size = update.getSerializedSize();
    if (size > MAX_RESPONSE_BYTES) {
        responseObserver.onError(
            Status.RESOURCE_EXHAUSTED
                .withDescription("Outbound response exceeds service limit")
                .asRuntimeException());
        return;
    }

    responseObserver.onNext(update);
}
~~~

Trong service thực tế, cần bảo đảm lỗi terminal chỉ được phát một lần và producer dừng sau khi gọi onError. Không tiếp tục gọi onNext sau onError hoặc onCompleted. Nếu response được tạo từ nhiều worker, hãy đưa chúng qua một outbound writer tuần tự để kiểm tra kích thước và gửi theo cùng một thứ tự.

Với unary RPC, thực hiện guard trước khi gọi onNext và onCompleted. Nếu response vượt giới hạn ứng dụng, kết thúc call bằng status đã quy định thay vì cố gửi payload mà client có thể từ chối.

## 6. API cấu hình outbound phụ thuộc phiên bản và transport

gRPC Java có cấu hình inbound message size trên builder của server và channel, nhưng không nên giả định mọi builder hoặc mọi transport đều có một setter outbound đối xứng. Một số API/cấu hình theo call hoặc transport có thể khác nhau theo phiên bản thư viện.

Trước khi dùng một tùy chọn outbound cụ thể:

1. Kiểm tra Javadoc của đúng phiên bản grpc-java đang dùng.
2. Xác nhận tùy chọn áp dụng cho client request, server response hay cả hai.
3. Xác nhận transport thực tế có hỗ trợ tùy chọn đó.
4. Kiểm thử trường hợp message vừa dưới và vượt ngưỡng qua channel/server thật.

Không thêm lời gọi giả định như **maxOutboundMessageSize()** vào một **ServerBuilder** chỉ vì API inbound có **maxInboundMessageSize()**. Nếu transport không cung cấp outbound guard, thực hiện kiểm tra ở tầng ứng dụng bằng serialized size và để receiver enforce inbound limit của nó.

Ngay cả khi transport có tùy chọn outbound, application guard vẫn hữu ích để trả lỗi nghiệp vụ rõ ràng, tránh serialize/gửi payload chắc chắn quá lớn và bảo vệ queue trước khi message đi vào transport.

## 7. Outbound message size trong streaming

Giới hạn outbound áp dụng cho từng message, không phải tổng dung lượng của toàn bộ stream. Một server-streaming RPC có thể gửi hàng nghìn response nhỏ mà tổng dữ liệu lớn hơn nhiều lần ngưỡng mỗi message.

Với streaming, cần phân biệt:

- **Per-message limit**: kích thước tối đa của từng message.
- **Per-RPC byte quota**: tổng dữ liệu được phép gửi trong một RPC.
- **Queue byte budget**: tổng payload đang chờ gửi trong bộ nhớ.
- **Rate limit**: tốc độ gửi dữ liệu trong một khoảng thời gian.

Quy tắc này áp dụng cho cả hai chiều: client phải kiểm tra từng chunk trước khi gọi request observer trong client-streaming; server phải kiểm tra từng response trước khi gọi response observer trong server-streaming. Với bidirectional streaming, mỗi endpoint thực hiện guard cho message outbound của chính nó.

Một message có thể nằm dưới per-message limit nhưng vẫn làm queue tăng quá mức nếu producer tạo response nhanh hơn transport gửi. Vì vậy, size guard phải đi cùng outbound readiness và queue có giới hạn.

Ví dụ drain response theo readiness:

~~~java
void drain() {
    while (!cancelled.get() && outbound.isReady()) {
        PriceUpdate next = pending.poll();
        if (next == null) {
            return;
        }

        sizeGuard.check(next);
        outbound.onNext(next);
    }
}
~~~

Đoạn mã giả định queue chỉ chứa message đã được kiểm tra hoặc việc guard có thể phát lỗi theo một terminal path duy nhất. Nếu guard ném exception, writer cần bắt lỗi, dừng producer và kết thúc RPC đúng cách.

## 8. Payload lớn nên chia chunk hay tăng giới hạn?

Tăng giới hạn có thể hợp lý khi payload lớn là yêu cầu nghiệp vụ rõ ràng, số lượng đồng thời thấp và ngân sách bộ nhớ đã được tính. Với file, ảnh hoặc dữ liệu nhị phân lớn, streaming theo chunk thường giúp kiểm soát bộ nhớ và tiến độ tốt hơn.

Ví dụ:

~~~proto
syntax = "proto3";

message DownloadChunk {
  string transfer_id = 1;
  uint64 sequence = 2;
  int64 offset = 3;
  bytes data = 4;
  bytes checksum = 5;
  bool last = 6;
}

service FileService {
  rpc Download(DownloadRequest) returns (stream DownloadChunk);
}
~~~

Mỗi chunk phải nằm dưới outbound limit của server và inbound limit của client. Hợp đồng nên xác định:

- Kích thước chunk mục tiêu và tối đa.
- Sequence/offset để phát hiện thiếu hoặc lặp chunk.
- Checksum theo chunk và checksum toàn file nếu cần.
- Tổng kích thước transfer tối đa.
- Cách resume sau reconnect và xử lý cancellation.
- Thời hạn transfer và quyền truy cập nội dung.

Không chia chunk tùy tiện mà bỏ qua giới hạn receiver. Chunk quá lớn vẫn bị từ chối; chunk quá nhỏ làm tăng framing, callback và chi phí xử lý.

## 9. Compression không thay thế size guard

gRPC có thể nén message để giảm số byte truyền trên mạng. Tuy nhiên, compression không làm thay đổi yêu cầu kiểm soát kích thước dữ liệu ứng dụng:

- **getSerializedSize()** đo message Protobuf trước compression.
- Dữ liệu sau giải nén có thể lớn hơn nhiều so với byte truyền trên wire.
- Compression tiêu tốn CPU và có thể tạo thêm buffer.
- Một message lớn vẫn cần được serialize, giữ trong bộ nhớ và xử lý ở receiver.

Không giả định message vượt ngưỡng ứng dụng sẽ trở nên an toàn chỉ vì nén tốt. Chọn guard dựa trên serialized payload và giới hạn receiver; kiểm thử với cấu hình compression thực tế của client/server.

Với nội dung đã nén sẵn như JPEG, ZIP hoặc video codec, nén gRPC thêm có thể không giảm đáng kể kích thước. Đánh giá lợi ích và chi phí CPU trước khi bật compression cho mọi message.

## 10. Outbound metadata là giới hạn khác

Metadata gRPC được truyền trong HTTP/2 headers/trailers, không phải Protobuf message body. Kích thước metadata thường bị giới hạn riêng ở endpoint nhận.

Không chuyển payload lớn vào metadata để tránh outbound message limit. Metadata phù hợp với:

- Authentication token và credential.
- Trace ID, correlation ID.
- Thông tin định tuyến hoặc phiên bản giao thức nhỏ.
- Status detail hoặc thông tin điều khiển có kích thước hạn chế.

Nội dung tài liệu, JSON lớn, danh sách dài hoặc binary payload phải nằm trong message body hoặc kênh lưu trữ phù hợp. Tăng metadata limit cũng không làm tăng message-size limit.

## 11. Xử lý khi outbound message vượt ngưỡng

Nên xác định lỗi trước khi gửi nếu ứng dụng có đủ thông tin:

- Với unary RPC, trả lỗi có status phù hợp, thường là **RESOURCE_EXHAUSTED** nếu vượt quota/kích thước được phép.
- Với streaming, dừng producer, không phát message vượt ngưỡng và kết thúc stream theo một terminal path.
- Nếu payload có thể chia nhỏ, trả hướng dẫn hoặc dùng RPC streaming chuyên biệt.
- Nếu lỗi đến từ inbound limit của peer, ghi nhận status trả về và không retry nguyên payload không thay đổi.

Không đổi lỗi kích thước thành **INTERNAL** nếu đây là giới hạn tài nguyên hoặc hợp đồng đã biết. Không trả nội dung payload trong status description; chỉ đưa kích thước thực tế, ngưỡng và correlation ID nếu phù hợp.

Nếu client cần biết trước giới hạn server, có thể công bố capability/limit trong API hoặc cấu hình client theo cùng hợp đồng triển khai. Không dựa vào việc gRPC tự trao đổi giới hạn này.

## 12. Kiểm thử outbound message size

Kiểm thử cần xác nhận cả guard ở sender và hành vi của receiver:

1. Message nhỏ hơn application limit được gửi thành công.
2. Message vượt application limit bị chặn trước khi gọi send.
3. Message nằm dưới guard của sender nhưng vượt inbound limit của peer bị peer từ chối.
4. Server response vượt inbound limit của client được kiểm tra từ phía client.
5. Streaming có nhiều message hợp lệ nhưng tổng byte vượt quota bị xử lý theo chính sách per-RPC.
6. Queue không giữ payload vượt byte budget.
7. Compression bật/tắt không làm bỏ qua guard ứng dụng.
8. Cancellation/deadline dừng producer khi một response không thể gửi.

Ví dụ unit test cho guard:

Schema dùng trong ví dụ:

~~~proto
syntax = "proto3";

package learning.documents.v1;
option java_package = "com.example.documents.v1";
option java_multiple_files = true;

message DocumentPayload {
  bytes content = 1;
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.protobuf.ByteString;
import org.junit.jupiter.api.Test;

class MessageSizeGuardTest {
    @Test
    void rejectsMessageAboveLimit() {
        DocumentPayload payload = DocumentPayload.newBuilder()
            .setContent(ByteString.copyFrom(new byte[1024]))
            .build();

        MessageSizeGuard guard = new MessageSizeGuard(512);

        assertThrows(
            IllegalArgumentException.class,
            () -> guard.check(payload));
    }
}
~~~

Unit test xác nhận guard ứng dụng. Integration test vẫn cần channel/server thật để kiểm tra receiver inbound limit và status quan sát được qua RPC.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng sender tự biết inbound limit của peer | Message có thể được gửi rồi mới bị peer từ chối | Chia sẻ limit qua hợp đồng và guard trước khi gửi. |
| Nhầm outbound size với HTTP/2 frame size | Chỉnh frame không giải quyết message quá lớn | Kiểm tra serialized message và receiver limit. |
| Chỉ giới hạn từng message | Tổng stream hoặc queue vẫn có thể quá lớn | Thêm per-RPC quota và byte budget. |
| Dùng kích thước file thay serialized size | Bỏ sót field/tag/framing Protobuf | Dùng getSerializedSize() cho message hoàn chỉnh. |
| Tin compression sẽ làm message hợp lệ | Payload sau giải nén vẫn có thể vượt giới hạn | Kiểm soát payload trước compression và kiểm thử receiver. |
| Giả định mọi builder có maxOutboundMessageSize | Build lỗi hoặc cấu hình không có tác dụng | Kiểm tra API theo phiên bản/transport; dùng application guard. |
| Tiếp tục stream sau khi response bị từ chối | Lỗi terminal, tài nguyên vẫn bị giữ | Dừng producer và kết thúc RPC đúng một lần. |
| Bỏ qua queue khi kiểm tra size | Nhiều message hợp lệ vẫn làm heap tăng | Giới hạn queue theo message count và byte. |

## 14. Bài tập thực hành

Một dịch vụ Spring gRPC gửi báo cáo qua server-streaming:

1. Đặt application outbound limit 2 MiB cho mỗi response.
2. Dùng getSerializedSize() kiểm tra từng response trước khi enqueue và trước khi gửi.
3. Giới hạn outbound queue theo cả số message và tổng byte.
4. Dùng isReady() để drain queue và chỉ có một writer cho response observer.
5. Tạo response lớn hơn 2 MiB và xác nhận server kết thúc RPC bằng status đã quy định.
6. Tạo một response dưới guard của server nhưng lớn hơn inbound limit của client; xác nhận client quan sát lỗi.
7. Thiết kế phiên bản streaming chunk cho báo cáo lớn, có sequence, offset và checksum.
8. Kiểm thử với compression bật/tắt và nhiều RPC đồng thời.

**Tiêu chí hoàn thành:** phân biệt outbound guard với receiver inbound limit, kiểm tra đúng serialized size, giới hạn queue và tổng quota, đồng thời xử lý nhất quán khi message không thể gửi.

## 15. Ghi nhớ

- Outbound là message gửi từ endpoint hiện tại; inbound limit được thực thi ở peer nhận.
- Không giả định gRPC tự thương lượng một giới hạn message chung giữa hai endpoint.
- Dùng **getSerializedSize()** để kiểm tra payload Protobuf trước khi gửi; đây không phải heap size.
- Giới hạn từng message khác tổng byte của stream, queue budget, HTTP/2 frame size và metadata size.
- Với streaming, kiểm tra từng message, giới hạn queue và tổng quota; dùng chunk cho payload lớn.
- Compression giảm byte trên wire nhưng không thay thế guard hoặc giới hạn receiver.
- Không giả định mọi builder/transport có API outbound giống inbound; xác minh phiên bản và vẫn giữ application guard.

Kiểm soát outbound message size giúp dịch vụ Spring gRPC tránh tạo payload mà peer không thể nhận, giảm áp lực bộ nhớ và duy trì hành vi ổn định cho unary lẫn streaming RPC.
