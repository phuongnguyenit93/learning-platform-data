# Cấu hình kích thước mảnh và giới hạn payload được chấp nhận

## Mục tiêu bài học

Một payload RSocket có thể lớn hơn kích thước phù hợp cho một frame. RSocket hỗ trợ chia payload thành nhiều fragment ở tầng giao thức và ghép chúng lại ở phía nhận. Tuy nhiên, chia nhỏ frame không đồng nghĩa payload có thể lớn vô hạn: phía nhận vẫn cần giới hạn kích thước payload sau khi ghép để bảo vệ bộ nhớ và tài nguyên.

Sau bài này, bạn có thể:

- Phân biệt payload, RSocket frame, fragment và gói tin của transport.
- Giải thích cách RSocket chia REQUEST/PAYLOAD frame bằng cờ Follows.
- Cấu hình kích thước fragment ở phía gửi.
- Cấu hình giới hạn payload inbound sau khi reassembly ở phía nhận.
- Phối hợp cấu hình client, server và transport.
- Chọn kích thước fragment theo đặc điểm payload và môi trường triển khai.
- Kiểm thử payload lớn, metadata lớn và trường hợp vượt giới hạn.

## Payload, frame và fragment là gì?

Một RSocket payload có thể chứa hai phần:

- **Data:** dữ liệu ứng dụng, ví dụ JSON, protobuf hoặc nội dung nhị phân.
- **Metadata:** thông tin phụ trợ, ví dụ route, MIME type, thông tin xác thực hoặc tracing.

RSocket đóng payload vào frame để truyền qua transport. Một frame có header giao thức và phần dữ liệu của frame. Nếu request hoặc payload lớn hơn ngưỡng fragment đã cấu hình, implementation có thể chia nó thành nhiều frame nhỏ hơn.

Cần phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Payload | Data và metadata của một thông điệp ở tầng RSocket | Một yêu cầu tải báo cáo |
| RSocket frame | Đơn vị khung của giao thức, gồm header và nội dung frame | REQUEST_RESPONSE hoặc PAYLOAD |
| Fragment | Một phần của payload được đặt trong frame để truyền | Fragment 1/4 của payload lớn |
| Transport packet | Đơn vị truyền ở TCP, WebSocket hoặc tầng mạng | TCP segment hoặc WebSocket frame |

RSocket fragmentation là chia nhỏ ở tầng giao thức RSocket. TCP vẫn có thể chia byte stream thành nhiều segment riêng, còn WebSocket có framing riêng. RSocket fragment không đồng nghĩa với TCP segment, WebSocket frame hay Ethernet MTU. Vì vậy, không nên lấy kích thước MTU của card mạng rồi áp thẳng vào cấu hình fragment mà không đo đạc.

## Cơ chế fragmentation và reassembly

Khi một REQUEST frame hoặc PAYLOAD frame cần chia nhỏ, fragment đầu tiên mang cờ **Follows (F)** để báo rằng còn fragment tiếp theo. Các fragment tiếp tục được gửi theo đúng stream ID. Phía nhận ghép các phần lại thành payload hoàn chỉnh trước khi chuyển payload cho tầng ứng dụng.

Có hai trường hợp chính:

- **Fragmented REQUEST:** frame đầu tiên vẫn là REQUEST_RESPONSE, REQUEST_FNF, REQUEST_STREAM hoặc REQUEST_CHANNEL. Nếu còn fragment, frame này bật Follows; các phần tiếp theo được truyền bằng PAYLOAD frame.
- **Fragmented PAYLOAD:** một payload đang được phát trên stream được chia thành chuỗi PAYLOAD frame. Các frame dùng cùng stream ID và cờ Follows cho biết còn phần tiếp theo hay không.

Metadata phải được truyền hoàn chỉnh trước Data trong một chuỗi fragment. Do đó, metadata lớn cũng có thể chiếm nhiều fragment trước khi phần Data bắt đầu.

Sơ đồ đơn giản:

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant R as Receiver
    S->>R: REQUEST_* / PAYLOAD, Follows=1
    S->>R: PAYLOAD fragment 2, Follows=1
    S->>R: PAYLOAD fragment 3, Follows=0
    Note over R: Reassemble các fragment
    R-->>R: Tạo payload hoàn chỉnh
    R->>R: Chuyển payload cho handler
~~~

Từ góc nhìn handler Spring, ứng dụng thường nhận một payload hoàn chỉnh. Handler không phải tự ghép từng fragment. Điều này làm API dễ dùng hơn, nhưng cũng có nghĩa phía nhận phải giữ dữ liệu trong bộ nhớ cho đến khi reassembly hoàn tất.

Một fragment sequence chưa hoàn tất không thể được xem là payload hoàn chỉnh. Nếu người gửi hủy việc gửi fragment, stream bị cancel hoặc transport mất kết nối giữa chừng, implementation phải xử lý trạng thái chưa hoàn tất theo vòng đời stream/kết nối.

## Fragmentation không thay thế flow control

Fragmentation chia một payload lớn thành các frame nhỏ hơn. Backpressure điều tiết số phần tử mà bên nhận yêu cầu trong một stream. Hai cơ chế xử lý hai vấn đề khác nhau.

Ví dụ, một request-stream phát 100 payload, mỗi payload có kích thước 2 MB. Fragmentation có thể chia từng payload 2 MB thành nhiều frame nhỏ. Backpressure điều tiết số payload 2 MB mà consumer muốn nhận. Nếu consumer yêu cầu quá nhiều phần tử cùng lúc, tổng bộ nhớ vẫn có thể tăng cao dù từng frame nhỏ.

Fragmentation cũng không làm tăng số request hoặc demand credit:

- Một request lớn bị chia thành nhiều frame vẫn chỉ là một request mới.
- Một payload bị chia thành nhiều fragment không tiêu thụ thêm một demand credit cho mỗi fragment.
- Các payload tiếp theo trong cùng stream vẫn tuân theo flow control của stream.

Do đó, hệ thống vẫn cần giới hạn số stream đồng thời, số payload đang được xử lý, queue và kích thước payload sau reassembly.

## Hai cấu hình quan trọng trong RSocket Java

RSocket Java cung cấp hai cấu hình cần phân biệt:

| API | Phía áp dụng | Tác dụng |
|---|---|---|
| fragment(mtu) | Phía gửi | Chia frame lớn thành các fragment không vượt ngưỡng cấu hình |
| maxInboundPayloadSize(bytes) | Phía nhận | Giới hạn kích thước payload tối đa được phép ghép lại |

### fragment(mtu)

Phương thức fragment(mtu) cấu hình ngưỡng fragment cho frame gửi đi. Ví dụ, đặt 64 KiB khiến các frame lớn hơn ngưỡng này được chia nhỏ theo cơ chế fragmentation của implementation.

Trong RSocket Java 1.1.5, giá trị MTU truyền vào phải tối thiểu 64 byte. Nếu không cấu hình fragmentation, payload có thể được gửi nguyên vẹn trong một frame cho đến giới hạn frame tối đa của giao thức, là 16.777.215 byte. Transport hoặc intermediary có thể đặt giới hạn thấp hơn.

Tên tham số là MTU, nhưng đây là ngưỡng fragment ở tầng RSocket implementation. Hãy xem tài liệu phiên bản thư viện và transport đang dùng trước khi lựa chọn giá trị.

### maxInboundPayloadSize(bytes)

Phương thức maxInboundPayloadSize(bytes) giới hạn kích thước payload sau khi reassembly ở phía nhận. Đây là hàng rào bảo vệ quan trọng khi peer gửi payload lớn.

Trong RSocket Java 1.1.5:

- Giá trị phải tối thiểu 64 byte.
- Giá trị phải lớn hơn hoặc bằng Transport.maxFrameLength() của transport tương ứng.
- Nếu không cấu hình, giới hạn kích thước payload sau reassembly không được đặt bởi thuộc tính này.

Giới hạn inbound không tự chia nhỏ payload ở phía gửi. Ngược lại, cấu hình fragment ở phía gửi không quyết định payload tối đa mà phía nhận chấp nhận. Hai phía cần phối hợp các giới hạn này.

## Cấu hình client bằng RSocketConnector

Ví dụ dưới đây dùng TCP và RSocket Java. Client chia frame outbound thành các fragment khoảng 64 KiB và chấp nhận payload inbound tối đa 16 MiB sau reassembly.

~~~java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import reactor.core.publisher.Mono;

class RSocketClientFactory {

    private static final int FRAGMENT_SIZE = 64 * 1024;
    private static final int MAX_INBOUND_PAYLOAD = 16 * 1024 * 1024;

    Mono<RSocket> connect() {
        return RSocketConnector.create()
            .fragment(FRAGMENT_SIZE)
            .maxInboundPayloadSize(MAX_INBOUND_PAYLOAD)
            .connect(TcpClientTransport.create("localhost", 7000));
    }
}
~~~

Trong ví dụ:

- fragment(FRAGMENT_SIZE) áp dụng cho frame mà client gửi sang server.
- maxInboundPayloadSize(MAX_INBOUND_PAYLOAD) giới hạn payload mà client nhận từ server sau khi ghép.
- 16 MiB lớn hơn giới hạn frame tối đa theo giao thức một byte, nhưng vẫn phải xác nhận giá trị này không nhỏ hơn Transport.maxFrameLength() thực tế của transport đã cấu hình.

Nếu server trả về payload lớn, fragment phía client không giúp server tự chia nhỏ response. Server cũng phải được cấu hình fragmentation cho chiều gửi của nó.

## Cấu hình server bằng RSocketServer

Phía server cũng có cấu hình tương ứng. Ví dụ này minh họa API RSocket Java trực tiếp; SocketAcceptor đại diện cho handler tiếp nhận request của ứng dụng.

~~~java
import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;

class RSocketServerFactory {

    private static final int FRAGMENT_SIZE = 64 * 1024;
    private static final int MAX_INBOUND_PAYLOAD = 16 * 1024 * 1024;

    void start(SocketAcceptor acceptor) {
        RSocketServer.create(acceptor)
            .fragment(FRAGMENT_SIZE)
            .maxInboundPayloadSize(MAX_INBOUND_PAYLOAD)
            .bind(TcpServerTransport.create("localhost", 7000))
            .subscribe();
    }
}
~~~

Cấu hình này có hai tác dụng:

- Server chia nhỏ frame outbound khi response hoặc request do server khởi tạo vượt ngưỡng fragment.
- Server từ chối payload inbound vượt giới hạn reassembly đã đặt.

Trong ứng dụng thực tế, cần quản lý subscription hoặc handle đóng server theo vòng đời ứng dụng, thay vì gọi subscribe() rời rạc mà không giữ handle quản lý.

## Tích hợp cấu hình với Spring Boot

Khi tạo client bằng Spring RSocketRequester, có thể cấu hình RSocketConnector thông qua callback rsocketConnector. Ví dụ:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector
        .fragment(64 * 1024)
        .maxInboundPayloadSize(16 * 1024 * 1024)
    )
    .tcp("localhost", 7000);
~~~

Callback cho phép tùy chỉnh connector bên dưới. Cấu hình cụ thể có thể thay đổi theo phiên bản Spring Framework và RSocket Java.

Ở phía server, nếu ứng dụng dùng Spring Boot auto-configuration, hãy nối cấu hình fragmentation và giới hạn inbound vào API hoặc customizer được phiên bản Spring/RSocket đang dùng hỗ trợ. Không nên sao chép một property name từ phiên bản khác nếu chưa xác nhận property đó tồn tại. Khi cần kiểm soát chính xác, cấu hình underlying RSocketServer bằng API tương ứng.

Điều quan trọng là cấu hình cả hai chiều:

| Thành phần | Outbound fragmentation | Inbound payload cap |
|---|---|---|
| Client | Chia request và payload client gửi | Giới hạn response/payload server gửi về |
| Server | Chia response và payload server gửi | Giới hạn request/payload client gửi đến |

Nếu client chỉ cấu hình fragment còn server không cấu hình, request lớn từ client có thể được chia nhỏ nhưng response lớn từ server vẫn có thể vượt giới hạn frame hoặc giới hạn intermediary. Ngược lại, giới hạn inbound ở client không bảo vệ bộ nhớ của server.

## Chọn kích thước fragment phù hợp

Không có một giá trị tối ưu cho mọi hệ thống. Kích thước fragment nên được chọn dựa trên:

- Kích thước payload thực tế và phân bố payload nhỏ/lớn.
- Giới hạn frame của transport, proxy, gateway và môi trường triển khai.
- Số stream hoạt động đồng thời.
- Độ trễ mạng và chi phí xử lý frame.
- Mức sử dụng CPU, bộ nhớ và buffer.
- Tần suất payload lớn và mức độ quan trọng của latency.

Một số giá trị có thể dùng làm điểm bắt đầu thử nghiệm:

| Kích thước fragment | Đặc điểm |
|---|---|
| 16 KiB | Frame nhỏ hơn, nhiều fragment hơn; có thể tăng overhead |
| 32 KiB | Điểm cân bằng để bắt đầu đo đạc |
| 64 KiB | Ít fragment hơn với payload lớn, mỗi frame lớn hơn |
| 256 KiB | Có thể giảm số frame nhưng cần kiểm tra giới hạn transport và buffer |

Các giá trị trên là ví dụ để benchmark, không phải khuyến nghị cố định. Fragment nhỏ làm tăng số frame, header và công việc reassembly. Fragment lớn giảm số frame nhưng cần buffer lớn hơn và có thể không phù hợp với giới hạn của proxy hoặc transport.

Hãy đo trên cả TCP và WebSocket nếu hệ thống hỗ trợ hai transport. Cùng một kích thước fragment có thể cho kết quả khác nhau khi đi qua proxy hoặc gateway khác nhau.

## Chọn giới hạn inbound payload

Giới hạn inbound phải đủ lớn cho payload hợp lệ lớn nhất mà ứng dụng cần nhận, nhưng vẫn phải bảo vệ hệ thống trước payload quá lớn.

Ví dụ, nếu nghiệp vụ chỉ cần gửi một tài liệu tối đa 8 MiB, có thể đặt giới hạn inbound cao hơn một khoảng dự phòng hợp lý. Không nên đặt giới hạn 16 MiB chỉ vì đó là giá trị ví dụ nếu ứng dụng không cần payload lớn như vậy.

Khi chọn giới hạn, hãy tính đến:

- Data đã serialize có thể lớn hơn object trong bộ nhớ.
- Metadata cũng chiếm dung lượng trong frame và payload.
- Payload sau reassembly có thể cần thêm bộ nhớ cho buffer và object đã deserialize.
- Nhiều payload lớn có thể được reassemble đồng thời trên các stream khác nhau.
- Một payload có thể được sao chép trong quá trình decode tùy PayloadDecoder và implementation.

Ví dụ, giới hạn 16 MiB cho một payload không có nghĩa toàn server chỉ sử dụng tối đa 16 MiB. Nếu 50 stream cùng reassemble payload gần giới hạn, nhu cầu bộ nhớ có thể lớn hơn rất nhiều. Cần phối hợp inbound cap với giới hạn concurrency, số stream, queue và bộ nhớ ứng dụng.

## Khi payload lớn hơn giới hạn

Nếu payload sau reassembly vượt maxInboundPayloadSize, receiver không thể chấp nhận payload đó theo cấu hình. Tùy implementation và phiên bản, stream có thể kết thúc bằng lỗi và được ghi nhận qua error handler hoặc log giao thức.

Không nên giải quyết bằng cách tăng giới hạn vô hạn. Hãy xem xét:

- Có thể giảm kích thước dữ liệu bằng cách chỉ gửi field cần thiết không?
- Có thể dùng định dạng nhị phân hoặc serialization gọn hơn không?
- Có thể chuyển nội dung lớn sang object storage và chỉ gửi URI/ID qua RSocket không?
- Có thể chia dữ liệu thành nhiều thông điệp ứng dụng có sequence number không?
- Có thể dùng request-stream để gửi từng phần dữ liệu có kiểm soát không?

Fragmentation ở tầng RSocket vẫn reassemble một payload hoàn chỉnh trước khi handler nhận nó. Nếu mục tiêu là xử lý file lớn theo từng phần mà không cần giữ toàn bộ file trong bộ nhớ, hãy thiết kế chunking ở tầng ứng dụng hoặc một stream gồm nhiều payload nhỏ. Khi đó, cần thêm sequence number, checksum, kích thước tổng, cơ chế resume và chính sách xử lý chunk trùng hoặc thiếu.

## Ví dụ thiết kế chunking ở tầng ứng dụng

Giả sử client cần gửi một file 200 MiB. Gửi toàn bộ file thành một payload duy nhất rồi dựa vào fragmentation sẽ khiến receiver phải reassemble payload rất lớn. Một cách khác là chia file thành các chunk ở tầng ứng dụng.

~~~java
record FileChunk(
    String uploadId,
    int sequence,
    boolean last,
    byte[] content,
    String checksum
) {}
~~~

Client có thể phát các chunk theo một request-stream hoặc request-channel:

~~~java
Flux<FileChunk> chunks = fileChunkSource
    .map(chunk -> new FileChunk(
        uploadId,
        chunk.sequence(),
        chunk.last(),
        chunk.bytes(),
        chunk.sha256()
    ));

Mono<UploadResult> result = requester
    .route("files.upload")
    .data(chunks)
    .retrieveMono(UploadResult.class);
~~~

Đây là phác thảo hợp đồng ứng dụng; cách chọn interaction type và chữ ký handler cần khớp với mô hình upload của hệ thống. Mỗi chunk vẫn là một payload RSocket riêng và có thể tiếp tục được fragmentation nếu chunk quá lớn.

Server cần xác minh checksum, thứ tự chunk, uploadId, giới hạn kích thước mỗi chunk và tổng kích thước file. Với dữ liệu lớn, hãy ghi từng chunk xuống storage bền vững thay vì giữ tất cả trong RAM. Khi client reconnect, sequence number hoặc trạng thái upload giúp xác định phần nào đã được lưu.

## Metadata cũng cần giới hạn

Metadata có thể chứa route, authentication, tracing và các thông tin định tuyến khác. Metadata lớn có thể khiến payload vượt giới hạn dù phần Data không lớn.

Một số nguyên tắc:

- Chỉ đưa thông tin cần thiết vào metadata.
- Không đưa toàn bộ object nghiệp vụ vào metadata.
- Giới hạn độ dài route, token và các trường metadata theo hợp đồng.
- Tránh lặp lại metadata lớn trên mọi payload trong một stream nếu có thể dùng metadata gắn với connection hoặc thiết kế khác phù hợp.
- Không ghi token, credential hoặc metadata nhạy cảm vào log.

Theo quy tắc fragmentation của RSocket, metadata được truyền hoàn chỉnh trước Data trong một chuỗi fragment. Vì vậy, metadata lớn có thể làm tăng số fragment trước khi Data bắt đầu được truyền.

## Kiểm thử kích thước fragment và payload

Nên kiểm thử ở cả hai hướng và qua transport thực tế:

1. Payload nhỏ hơn fragment size: xác nhận gửi bình thường.
2. Payload lớn hơn fragment size: xác nhận receiver nhận được payload hoàn chỉnh.
3. Payload gần giới hạn inbound: xác nhận được chấp nhận.
4. Payload vượt giới hạn inbound: xác nhận bị từ chối và lỗi được quan sát.
5. Metadata lớn nhưng Data nhỏ.
6. Data lớn nhưng metadata nhỏ.
7. Tổng Data và Metadata gần ngưỡng inbound.
8. Client gửi request lớn và server gửi response lớn.
9. Nhiều stream đồng thời gửi payload lớn để đo bộ nhớ và độ trễ.
10. Hủy stream khi fragment sequence chưa hoàn tất.
11. TCP và WebSocket qua proxy/gateway nếu môi trường triển khai có sử dụng.

Không chỉ kiểm tra một payload lớn duy nhất. Một hệ thống có thể chạy tốt với một stream 10 MiB nhưng gặp sự cố khi hàng chục stream cùng reassemble payload 10 MiB.

Nên kiểm tra cả payload thực tế sau serialization. Kích thước object Java trước serialization không phải kích thước byte cuối cùng được truyền trên wire.

## Quan sát và bảo vệ khi vận hành

Các thông tin hữu ích để theo dõi:

- Kích thước payload inbound và outbound theo route.
- Số payload bị từ chối do vượt giới hạn.
- Lỗi decode hoặc reassembly.
- Số stream đồng thời đang xử lý payload lớn.
- Bộ nhớ heap/direct buffer và áp lực GC.
- Độ trễ từ lúc gửi request đến khi handler nhận payload hoàn chỉnh.
- Tỷ lệ timeout, cancel và lỗi transport khi truyền payload lớn.

Giới hạn inbound payload là một phần của phòng vệ chống tiêu thụ tài nguyên. Kết hợp nó với xác thực sớm, quota theo client/tenant, giới hạn concurrency, timeout và queue hữu hạn. Không cho phép một client không đáng tin cậy mở nhiều stream rồi đồng thời gửi payload gần giới hạn trên tất cả stream.

Nếu sử dụng PayloadDecoder.ZERO_COPY, cần tuân thủ quy tắc quản lý và release Payload của implementation. Zero-copy có thể giảm sao chép bộ nhớ nhưng làm quyền sở hữu buffer trở nên quan trọng hơn. Với decoder mặc định, thư viện có thể sao chép Data và Metadata; điều này đơn giản hơn nhưng có thể tăng chi phí bộ nhớ.

## Checklist cấu hình

Trước khi triển khai, hãy trả lời:

1. Payload lớn nhất hợp lệ của từng route là bao nhiêu byte sau serialization?
2. Metadata có thể lớn đến mức nào?
3. Kích thước fragment outbound là bao nhiêu và dựa trên phép đo nào?
4. Transport.maxFrameLength() thực tế là bao nhiêu?
5. maxInboundPayloadSize có lớn hơn hoặc bằng giới hạn frame của transport không?
6. Client và server đã cấu hình fragmentation cho cả hai chiều chưa?
7. Client và server đã có inbound payload cap riêng chưa?
8. Số stream đồng thời có thể reassemble payload lớn là bao nhiêu?
9. Payload lớn có nên chuyển sang chunking ở tầng ứng dụng không?
10. Có kiểm thử trường hợp vượt giới hạn và giám sát bộ nhớ không?

Fragmentation giúp một payload lớn được truyền qua nhiều RSocket frame nhỏ hơn, còn maxInboundPayloadSize kiểm soát payload hoàn chỉnh mà receiver chấp nhận. Khi phối hợp hai cấu hình ở cả client và server, đồng thời giới hạn concurrency và kiểm thử bằng kích thước dữ liệu thực tế, hệ thống có thể xử lý payload lớn mà vẫn kiểm soát được bộ nhớ và tải.

## Tài liệu tham khảo

- [RSocket Protocol: Fragmentation and Reassembly](https://rsocket.io/about/protocol/#fragmentation-and-reassembly)
- [RSocket Java 1.1.5: RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5: RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [Spring Framework: RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)

