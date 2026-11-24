# Thực hành truyền payload lớn và quan sát các frame

RSocket truyền dữ liệu ứng dụng bên trong các frame. Khi một request hoặc một payload phản hồi lớn hơn kích thước frame mà bên gửi muốn sử dụng, RSocket có thể chia message thành nhiều fragment rồi ghép lại ở bên nhận. Cơ chế này gọi là fragmentation and reassembly.

Fragmentation giúp một message lớn đi qua transport mà không cần đặt toàn bộ dữ liệu vào một frame khổng lồ. Ở tầng ứng dụng, handler vẫn nhận một payload hoàn chỉnh sau khi reassembly. Vì vậy, fragmentation trong giao thức khác với việc ứng dụng chủ động chia một file thành nhiều phần nhỏ và xử lý từng phần.

Trong bài thực hành này, ta cấu hình RSocket Java với MTU 16 KB, gửi một payload khoảng 2 MB qua TCP, quan sát chuỗi frame bằng FrameLogger và xác nhận dữ liệu được ghép lại nguyên vẹn.

## 1. Khi nào cần phân mảnh payload?

Một RSocket frame có giới hạn kích thước theo định dạng giao thức. RSocket cho phép frame mang payload lớn, nhưng nếu một message vượt kích thước frame tối đa hoặc giới hạn MTU do ứng dụng cấu hình, sender cần chia message thành các fragment.

Các tình huống thường gặp:

- Client tải lên ảnh, tài liệu hoặc dữ liệu nhị phân lớn.
- Server trả về nội dung tài liệu, báo cáo hoặc kết quả truy vấn lớn.
- Một request-channel truyền các bản ghi hoặc batch dữ liệu lớn.
- Metadata hoặc data của payload vượt kích thước frame mong muốn.

Fragmentation có thể áp dụng cho PAYLOAD frame và các REQUEST frame: REQUEST_RESPONSE, REQUEST_FNF, REQUEST_STREAM và REQUEST_CHANNEL. Vì vậy, cả request ban đầu lẫn payload phản hồi đều có thể được phân mảnh.

RSocket Java cung cấp phương thức <code>fragment(int mtu)</code> trên <code>RSocketConnector</code> và <code>RSocketServer</code>. Khi bật cấu hình này, các frame lớn hơn ngưỡng MTU được chia thành nhiều frame nhỏ hơn. Nếu không cấu hình, payload được gửi nguyên vẹn trong một frame cho tới giới hạn frame tối đa của giao thức.

## 2. FOLLOWS và quy tắc ghép fragment

RSocket sử dụng cờ FOLLOWS (F) để cho biết còn fragment tiếp theo hay không. Receiver tiếp tục thu thập các fragment cùng stream cho tới khi nhận fragment cuối cùng, sau đó mới chuyển payload hoàn chỉnh lên tầng ứng dụng.

Với một PAYLOAD phản hồi được phân mảnh:

~~~text
Responder                                      Requester
    |                                               |
    |--- PAYLOAD (FOLLOWS=1, fragment 1) ---------->|
    |--- PAYLOAD (FOLLOWS=1, fragment 2) ---------->|
    |--- PAYLOAD (FOLLOWS=0, fragment cuối) ------->|
    |                                               |
    |                  reassembly                   |
    |                                               |
    |                 onNext(payload hoàn chỉnh)    |
~~~

Với request ban đầu được phân mảnh, frame đầu tiên vẫn giữ loại REQUEST tương ứng và đặt FOLLOWS. Những phần tiếp theo được gửi bằng PAYLOAD frame:

~~~text
Requester                                      Responder
    |                                               |
    |--- REQUEST_RESPONSE (FOLLOWS=1) ------------>|
    |--- PAYLOAD (FOLLOWS=1, fragment tiếp) ------>|
    |--- PAYLOAD (FOLLOWS=0, fragment cuối) ------>|
    |                                               |
    |                  reassembly                   |
    |                                               |
    |              gọi handler một lần              |
~~~

Một số quy tắc quan trọng:

- Các fragment thuộc cùng một stream và phải được ghép theo đúng thứ tự.
- Nếu payload có metadata, toàn bộ metadata phải được truyền trước data. Metadata có thể chiếm nhiều fragment; chỉ sau khi metadata hoàn tất, phần data mới tiếp tục.
- Fragment cuối cùng không đặt FOLLOWS.
- Sender có thể gửi CANCEL để dừng một chuỗi fragment chưa truyền xong.
- Một PAYLOAD đã bị chia thành nhiều frame vẫn chỉ tính là một phần tử đối với demand của Reactive Streams. Tương tự, một request bị chia thành nhiều frame vẫn chỉ tính là một request đối với lease.

Ví dụ payload có 20 MB metadata và 25 MB data có thể được truyền thành nhiều frame: các fragment đầu chứa metadata, fragment chuyển tiếp hoàn tất metadata rồi mới bắt đầu data, và fragment cuối kết thúc chuỗi. Kích thước thực tế mỗi phần phụ thuộc MTU và overhead của frame.

## 3. Giới hạn frame và MTU

RSocket dùng trường frame length 24-bit trên transport cần trường độ dài. Giá trị tối đa là 16.777.215 byte cho một frame, chưa tính trường frame-length prefix 3 byte của TCP. Đây là giới hạn giao thức; MTU cấu hình trong thư viện thường nhỏ hơn để kiểm soát kích thước frame trên đường truyền.

Trong RSocket Java:

| Cấu hình | Ý nghĩa |
| --- | --- |
| <code>fragment(mtu)</code> | Chia frame outbound vượt ngưỡng MTU thành các fragment. MTU tối thiểu là 64 byte. |
| <code>maxInboundPayloadSize(size)</code> | Giới hạn kích thước payload tối đa sau khi reassembly ở phía nhận. |
| Transport <code>maxFrameLength()</code> | Giới hạn frame tối đa mà transport chấp nhận. |

<code>maxInboundPayloadSize</code> là giới hạn của message sau khi ghép, không phải kích thước một fragment. Giá trị này phải lớn hơn hoặc bằng <code>Transport.maxFrameLength()</code> của transport đang sử dụng. Nếu đặt quá thấp, một message hợp lệ có thể bị từ chối trước khi ứng dụng nhận được payload.

Ví dụ, MTU 16 KB tạo các frame nhỏ để truyền một message 2 MB. Receiver vẫn cần đủ giới hạn reassembly để chứa toàn bộ 2 MB đó. Fragmentation không làm giảm kích thước cuối cùng của payload sau khi ghép.

## 4. Cấu hình fragmentation ở cả hai phía

Fragmentation được thực hiện ở phía gửi. Nếu client có thể gửi request lớn, hãy cấu hình MTU ở client. Nếu server có thể gửi response lớn, hãy cấu hình MTU ở server. Trong ứng dụng hai chiều, nên cấu hình cả hai phía.

Ví dụ server TCP dùng RSocket Java:

~~~java
import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

public class LargePayloadServer {

    public static void main(String[] args) {
        RSocketServer.create(
            SocketAcceptor.forRequestResponse(request -> {
                try {
                    String body = request.getDataUtf8();
                    return Mono.just(DefaultPayload.create(body));
                } finally {
                    request.release();
                }
            })
        )
        .fragment(16 * 1024)
        .maxInboundPayloadSize(16 * 1024 * 1024)
        .bindNow(TcpServerTransport.create("localhost", 7000));
    }
}
~~~

Server nhận một request-response, đọc nội dung data rồi trả lại payload. Khi client gửi request lớn, server nhận một payload đã được reassembly. Nếu response cũng lớn, cấu hình <code>fragment(16 * 1024)</code> ở server chia response thành các frame nhỏ.

Ví dụ client TCP:

~~~java
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import io.rsocket.util.DefaultPayload;

public class LargePayloadClient {

    public static void main(String[] args) {
        String body = "RSocket ".repeat(250_000); // khoảng 2 MB

        RSocket client = RSocketConnector.create()
            .fragment(16 * 1024)
            .maxInboundPayloadSize(16 * 1024 * 1024)
            .connect(TcpClientTransport.create("localhost", 7000))
            .block();

        try {
            Payload response = client
                .requestResponse(DefaultPayload.create(body))
                .block();

            try {
                int receivedBytes = response.getData().readableBytes();
                System.out.println("Received bytes: " + receivedBytes);
            } finally {
                response.release();
            }
        } finally {
            client.dispose();
        }
    }
}
~~~

Ví dụ dùng <code>String.repeat</code>, có từ Java 11. Nếu dùng Java 8, có thể tạo chuỗi bằng <code>StringBuilder</code>. Đoạn code là chương trình minh họa chạy server và client riêng; trong ứng dụng thật, hãy quản lý vòng đời server bằng lifecycle của Spring hoặc thành phần quản lý transport.

Ở cả hai phía, <code>maxInboundPayloadSize</code> được đặt ở 16 MiB để giới hạn kích thước payload sau reassembly. Giá trị này lớn hơn frame tối đa mặc định 16.777.215 byte một chút, đáp ứng ràng buộc của RSocket Java với transport mặc định. Khi thay đổi transport hoặc <code>maxFrameLength</code>, cần tính lại giới hạn này.

## 5. Thực hành kiểm tra payload lớn

Thực hiện theo các bước sau:

1. Khởi động server ở cổng TCP 7000.
2. Bật logging frame ở cả client và server.
3. Gửi payload nhỏ, ví dụ 1 KB, để quan sát request và response thông thường.
4. Gửi payload khoảng 2 MB như ví dụ trên.
5. So sánh số frame được ghi log ở hai lần gửi.
6. Xác nhận handler nhận được nội dung hoàn chỉnh và client nhận đúng số byte phản hồi.
7. Thay MTU thành 64 KB rồi chạy lại để so sánh số fragment.

Kết quả mong đợi:

| Thử nghiệm | Quan sát |
| --- | --- |
| Payload nhỏ hơn MTU | Request/response thường chỉ cần một frame cho mỗi message. |
| Payload lớn hơn MTU | Một message được truyền bằng nhiều fragment; các fragment trung gian có FOLLOWS. |
| MTU giảm | Số fragment tăng do mỗi frame mang ít dữ liệu hơn. |
| MTU tăng | Số fragment giảm, nhưng mỗi frame lớn hơn. |
| Payload vượt <code>maxInboundPayloadSize</code> | Receiver không thể reassemble message vượt giới hạn; lỗi cụ thể phụ thuộc implementation và transport. |

Không nên kỳ vọng số fragment bằng chính xác <code>payloadBytes / mtu</code>. Mỗi frame còn có header, stream ID, cờ, metadata length và các trường khác. Metadata cũng được tính vào dữ liệu cần truyền. Hãy dùng log frame thực tế để quan sát số lượng và kích thước.

## 6. Quan sát frame bằng FrameLogger

RSocket Java có logger <code>io.rsocket.FrameLogger</code> để in frame phục vụ debug. Trong ứng dụng Spring Boot, có thể bật DEBUG trong <code>application.yml</code>:

~~~yaml
logging:
  level:
    io.rsocket.FrameLogger: DEBUG
~~~

Khi gửi payload lớn, log minh họa có thể có dạng:

~~~text
sending ->
Frame => Stream ID: 1 Type: REQUEST_RESPONSE Flags: FOLLOWS Length: ...

sending ->
Frame => Stream ID: 1 Type: PAYLOAD Flags: FOLLOWS Length: ...

sending ->
Frame => Stream ID: 1 Type: PAYLOAD Flags: ... Length: ...

receiving ->
Frame => Stream ID: 1 Type: NEXT_COMPLETE Flags: ... Length: ...
~~~

Tên flag và cách trình bày chính xác phụ thuộc phiên bản RSocket Java. Hãy tìm các dấu hiệu sau:

- <code>Stream ID</code>: tất cả fragment của cùng một tương tác dùng chung stream ID.
- <code>Type</code>: request đầu tiên giữ loại REQUEST_RESPONSE, REQUEST_FNF, REQUEST_STREAM hoặc REQUEST_CHANNEL; các fragment tiếp theo là PAYLOAD.
- <code>FOLLOWS</code>: được đặt khi còn fragment tiếp theo và bỏ ở fragment cuối.
- <code>Length</code>: độ dài frame, hữu ích để so sánh với MTU đã cấu hình.
- <code>NEXT</code> và <code>COMPLETE</code>: các cờ của PAYLOAD phản ánh việc phát dữ liệu và kết thúc stream; chúng có ý nghĩa khác với FOLLOWS.

FrameLogger quan sát frame ở tầng RSocket, vì vậy dễ đếm fragment hơn việc chỉ nhìn packet TCP. Một frame RSocket có thể bị TCP chia thành nhiều packet hoặc nhiều frame có thể nằm trong cùng một lần đọc socket. Ranh giới packet TCP không đồng nghĩa ranh giới frame RSocket.

Không nên bật log frame chứa dữ liệu nhạy cảm trong production. FrameLogger có thể in metadata và nội dung payload; chỉ dùng dữ liệu thử nghiệm hoặc che thông tin nhạy cảm khi debug.

## 7. TCP và WebSocket khi quan sát frame

Fragmentation là cơ chế của RSocket, nên có thể dùng với các transport được hỗ trợ như TCP và WebSocket. Cách đóng gói frame ở transport khác nhau:

| Transport | Đóng gói frame |
| --- | --- |
| TCP | RSocket sử dụng trường frame-length prefix 3 byte để phân định ranh giới frame trên luồng byte. |
| WebSocket | Mỗi RSocket frame được mang trong message WebSocket; không cần RSocket frame-length prefix bổ sung vì WebSocket đã bảo toàn ranh giới message. |

Khi quan sát TCP bằng Wireshark, cần theo dõi TCP stream và ghép lại luồng byte trước khi suy luận về frame. TCP segmentation, retransmission hoặc coalescing có thể làm số packet khác số frame. Nếu kết nối dùng TLS, nội dung RSocket trên đường truyền được mã hóa; hãy dùng FrameLogger ở ứng dụng để xem frame trước hoặc sau lớp transport mã hóa.

## 8. Fragmentation không thay thế chunking ở tầng ứng dụng

Fragmentation là cơ chế trong suốt ở tầng giao thức. Receiver ghép đủ các fragment rồi mới chuyển một payload hoàn chỉnh lên handler. Vì vậy, khi gửi file 500 MB, server vẫn cần đủ tài nguyên để reassemble payload 500 MB trước khi xử lý.

Nếu dữ liệu rất lớn hoặc cần xử lý từng phần, hãy chia file thành các chunk ở tầng ứng dụng. Mỗi chunk là một message độc lập có thể được lưu, xác nhận, retry hoặc tiếp tục từ vị trí đã nhận.

Ví dụ hợp đồng chunk:

~~~java
public record FileChunk(
    String fileId,
    long sequence,
    boolean last,
    byte[] content,
    String checksum
) {}
~~~

Một giao thức upload/download theo chunk nên có:

- <code>fileId</code> để nhận diện file hoặc phiên truyền.
- <code>sequence</code> để xác định thứ tự chunk.
- <code>last</code> hoặc tổng số chunk để biết thời điểm hoàn tất.
- <code>checksum</code> để xác minh dữ liệu.
- Chính sách xác nhận, retry và loại bỏ chunk trùng.
- Giới hạn kích thước chunk và backpressure để điều tiết tốc độ.

Request-stream phù hợp khi client gửi một yêu cầu và server phát nhiều chunk. Request-channel phù hợp khi client và server cần trao đổi nhiều chunk ở cả hai chiều. Với cả hai mô hình, demand vẫn áp dụng cho các message ứng dụng; một message sau đó có thể tiếp tục được fragmentation ở tầng giao thức nếu nó vượt MTU.

## 9. Ảnh hưởng tới backpressure và tài nguyên

Fragmentation không tạo thêm demand credit. Một payload phản hồi được chia thành 10 frame vẫn chỉ tiêu thụ một credit <code>request(n)</code>. Điều này rất quan trọng khi phân tích throughput: số frame trên dây không phải số phần tử mà Subscriber đã nhận.

Fragmentation cũng không làm message nhỏ hơn sau khi reassembly. Receiver cần buffer để giữ các fragment và ghép thành payload hoàn chỉnh. Vì vậy, cần kiểm soát:

- MTU outbound để giới hạn kích thước frame truyền đi.
- <code>maxInboundPayloadSize</code> để giới hạn payload sau reassembly.
- Số stream đồng thời và tổng dung lượng payload đang được reassemble.
- Kích thước metadata và data.
- Timeout khi gửi hoặc nhận payload lớn.
- Bộ nhớ và số bản sao dữ liệu do serializer, decoder hoặc ứng dụng tạo ra.

Nếu bật <code>PayloadDecoder.ZERO_COPY</code> để giảm sao chép, ứng dụng phải quản lý vòng đời và release Payload đúng cách. Mặc định decoder có thể tạo bản sao độc lập; lựa chọn zero-copy đòi hỏi hiểu rõ reference counting của ByteBuf.

## 10. Kiểm thử và xử lý lỗi

Nên kiểm thử cả kích thước, nội dung và tình huống biên:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Payload nhỏ hơn MTU | Không cần chuỗi fragment. |
| Payload lớn hơn MTU | Receiver reassemble và handler nhận đúng một payload hoàn chỉnh. |
| Metadata lớn hơn một fragment | Metadata được truyền hoàn tất trước data. |
| Request lớn và response lớn | Client và server đều cấu hình fragmentation outbound. |
| Payload vượt giới hạn inbound | Receiver từ chối hoặc kết thúc tương tác theo implementation; không cấp phát vô hạn. |
| Hủy khi chuỗi fragment chưa hoàn tất | Sender dừng chuỗi fragment theo cơ chế CANCEL nếu tương tác cho phép. |
| Nhiều stream gửi payload lớn | Các stream được ghép độc lập, không trộn dữ liệu. |
| TCP và WebSocket | Cùng nhận được payload hoàn chỉnh dù cách đóng gói transport khác nhau. |

Khi kiểm thử nội dung, nên so sánh checksum hoặc hash của dữ liệu gửi và dữ liệu nhận thay vì chỉ kiểm tra số byte. Hai payload có cùng kích thước vẫn có thể chứa dữ liệu khác nhau.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Payload lớn bị lỗi trước khi tới handler | Không bật fragmentation hoặc frame vượt giới hạn. | Cấu hình <code>fragment(mtu)</code> ở phía gửi và kiểm tra transport max frame. |
| Request lớn hoạt động nhưng response lớn thất bại | Chỉ cấu hình fragmentation ở client. | Cấu hình MTU outbound ở server. |
| Frame nhỏ nhưng reassembly vẫn thất bại | <code>maxInboundPayloadSize</code> nhỏ hơn payload hoàn chỉnh. | Tăng giới hạn có kiểm soát và bảo đảm nó không nhỏ hơn <code>Transport.maxFrameLength()</code>. |
| Handler bị gọi với nội dung thiếu | Sai chuỗi fragment, lỗi transport hoặc lỗi implementation. | Kiểm tra stream ID, FOLLOWS, log hai phía và checksum. |
| Bộ nhớ tăng mạnh khi nhiều upload đồng thời | Mỗi stream giữ payload đã reassemble trong bộ nhớ. | Giảm giới hạn payload, giới hạn concurrency hoặc chuyển sang chunking ứng dụng. |
| Đếm frame không khớp số phần tử | Một message bị chia thành nhiều frame. | Phân biệt số frame với số PAYLOAD logic và demand credit. |

## 11. Checklist thực hành

- [ ] Cấu hình <code>fragment(mtu)</code> ở mọi phía có thể gửi payload lớn.
- [ ] Đặt <code>maxInboundPayloadSize</code> phù hợp với kích thước message dự kiến và giới hạn transport.
- [ ] Chạy thử payload nhỏ để lấy log frame làm mốc so sánh.
- [ ] Chạy thử payload lớn hơn MTU và xác nhận xuất hiện FOLLOWS.
- [ ] Kiểm tra fragment cuối cùng không còn FOLLOWS.
- [ ] Xác nhận server/client nhận đủ nội dung bằng byte length và checksum.
- [ ] Kiểm thử metadata lớn và thứ tự metadata trước data.
- [ ] Kiểm thử payload vượt giới hạn inbound và nhiều stream đồng thời.
- [ ] Tắt FrameLogger sau khi debug và không ghi payload nhạy cảm vào log.
- [ ] Dùng chunking tầng ứng dụng cho file hoặc luồng dữ liệu quá lớn cần xử lý từng phần.

## 12. Ghi nhớ

- RSocket fragmentation chia một request hoặc PAYLOAD lớn thành nhiều frame nhỏ; receiver reassemble trước khi chuyển payload lên ứng dụng.
- FOLLOWS cho biết còn fragment tiếp theo; request ban đầu vẫn giữ frame type REQUEST, các fragment tiếp theo dùng PAYLOAD.
- Metadata phải được truyền hoàn tất trước data.
- Một payload bị phân mảnh vẫn chỉ là một message và tiêu thụ một demand credit.
- <code>RSocketConnector.fragment(mtu)</code> và <code>RSocketServer.fragment(mtu)</code> cấu hình fragmentation outbound; <code>maxInboundPayloadSize</code> giới hạn payload sau reassembly.
- FrameLogger với logger <code>io.rsocket.FrameLogger</code> ở DEBUG giúp quan sát stream ID, loại frame, flags và kích thước.
- TCP packet không đồng nghĩa RSocket frame; hãy quan sát ở đúng tầng giao thức.
- Fragmentation không biến một file rất lớn thành luồng xử lý từng phần. Với dữ liệu lớn cần retry, resume hoặc xử lý tăng dần, hãy thiết kế chunking ở tầng ứng dụng.

## Tài liệu tham khảo

- [RSocket Protocol — Fragmentation and Reassembly](https://rsocket.io/about/protocol/#fragmentation-and-reassembly)
- [RSocketConnector API — RSocket Java 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocketServer API — RSocket Java 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java — Debugging and FrameLogger](https://github.com/rsocket/rsocket-java#debugging)
