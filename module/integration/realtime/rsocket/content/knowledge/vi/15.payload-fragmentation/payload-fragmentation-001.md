# Phân biệt phân mảnh RSocket với chia gói của TCP

Khi gửi một payload lớn qua RSocket/TCP, dữ liệu có thể được chia ở nhiều tầng. **RSocket fragmentation** chia một payload logic thành nhiều RSocket frame để phù hợp giới hạn kích thước frame. **TCP segmentation** chia luồng byte thành các TCP segment để truyền qua mạng. Hai cơ chế giải quyết hai vấn đề khác nhau và có thể cùng xảy ra trên một kết nối.

Điểm quan trọng là RSocket hiểu ranh giới payload, Stream ID và cờ FOLLOWS; TCP chỉ vận chuyển một luồng byte có thứ tự. TCP không biết payload RSocket bắt đầu hay kết thúc ở đâu, cũng không biết một fragment có phải là phần tiếp theo của payload trước đó hay không.

## 1. Hai tầng chia dữ liệu

Một ứng dụng Java tạo payload, ví dụ một thông điệp JSON có kích thước 200 KB. RSocket cần đóng gói payload đó thành frame theo giao thức. Nếu frame vượt giới hạn mà implementation cho phép, RSocket có thể phân mảnh payload thành nhiều frame nhỏ. Sau đó transport TCP vận chuyển byte của các frame ấy; TCP có thể chia byte thành các segment phù hợp với mạng.

~~~mermaid
flowchart TD
    A[Ứng dụng tạo một payload logic] --> B[RSocket fragmentation]
    B --> C[Frame 1: FOLLOWS]
    B --> D[Frame 2: FOLLOWS]
    B --> E[Frame cuối: FOLLOWS tắt]
    C --> F[TCP byte stream]
    D --> F
    E --> F
    F --> G[TCP segmentation thành các segment]
    G --> H[Mạng truyền và TCP reassembly]
    H --> I[Khôi phục luồng byte của transport]
    I --> J[Đọc ranh giới RSocket frame]
    J --> K[RSocket reassembly]
    K --> L[Một payload logic cho ứng dụng]
~~~

Hai tầng có thể chia theo những ranh giới hoàn toàn khác nhau:

- Một RSocket frame có thể trải qua nhiều TCP segment.
- Một TCP segment có thể chứa byte của nhiều RSocket frame.
- Một payload RSocket có thể được chia thành nhiều RSocket frame; mỗi frame đó lại có thể bị TCP chia nhỏ thêm.
- TCP reassembly chỉ khôi phục luồng byte theo thứ tự. RSocket reassembly mới ghép các fragment thành payload logic.

Vì vậy, không thể đếm số TCP segment để suy ra số payload hoặc số fragment RSocket.

## 2. RSocket fragmentation là gì?

RSocket fragmentation là cơ chế ở tầng giao thức để chia một payload lớn thành nhiều frame. Nó hữu ích khi payload vượt kích thước frame mà transport hoặc cấu hình implementation chấp nhận.

Mỗi fragment thuộc cùng một tương tác và giữ cùng **Stream ID**. Cờ **FOLLOWS** cho biết payload hiện tại còn fragment tiếp theo hay không:

- Các fragment chưa phải fragment cuối bật FOLLOWS.
- Fragment cuối tắt FOLLOWS.
- Receiver thu thập các fragment theo thứ tự và reassemble thành một payload logic trước khi giao lên tầng ứng dụng.

Ví dụ một payload được chia thành ba fragment:

~~~text
Stream ID = 17

Fragment 1: frame đầu, FOLLOWS = 1
Fragment 2: PAYLOAD, FOLLOWS = 1
Fragment 3: PAYLOAD, FOLLOWS = 0
                         |
                         v
                Một payload logic
~~~

Ba fragment không phải ba sự kiện ứng dụng. Với request-stream, consumer nhận một phần tử sau khi toàn bộ payload đã được reassemble. Không được xử lý fragment đầu như một DTO hoàn chỉnh rồi xử lý các fragment sau thành những DTO riêng.

### Frame đầu và các frame tiếp theo

Nếu payload lớn nằm trong frame khởi tạo tương tác, chẳng hạn REQUEST_RESPONSE, REQUEST_STREAM hoặc REQUEST_CHANNEL, frame đầu vẫn mang loại request tương ứng. Những frame tiếp theo tiếp tục mang phần còn lại của payload theo quy tắc fragmentation, thường được biểu diễn bằng PAYLOAD frame.

Nếu payload lớn là một phần tử của stream đang hoạt động, frame đầu là PAYLOAD và các frame sau tiếp tục payload đó. Receiver dựa trên Stream ID cùng FOLLOWS để biết các frame thuộc cùng một payload đang ghép.

## 3. FOLLOWS không phải là TCP segmentation

FOLLOWS là cờ của RSocket frame. Nó có ý nghĩa ở tầng ứng dụng/giao thức: còn fragment của payload logic hiện tại.

TCP segmentation là cách TCP đóng gói byte thành segment. TCP không có cờ FOLLOWS và không biết RSocket payload được chia thành bao nhiêu phần.

| Đặc điểm | RSocket fragmentation | TCP segmentation |
|---|---|---|
| Tầng | Giao thức ứng dụng RSocket | Transport TCP |
| Đơn vị chia | Payload logic thành RSocket frame | Luồng byte thành TCP segment |
| Lý do | Giới hạn kích thước frame, xử lý payload lớn | MSS, MTU đường truyền và điều kiện mạng |
| Nhận biết ranh giới | Stream ID, Frame Type, FOLLOWS | TCP sequence number và độ dài segment |
| Ghép lại ở đâu? | RSocket layer reassemble payload | TCP stack reassemble byte stream |
| Ứng dụng có thấy không? | Thường không thấy fragment nếu reassembly thành công | Không thấy segment trong API socket thông thường |

TCP cung cấp byte stream có thứ tự, tin cậy trong một kết nối. Ứng dụng đọc byte từ socket không nhận được ranh giới message tương ứng với từng lần ghi ở phía gửi. Một lần write có thể được nhận qua nhiều lần read; nhiều lần write cũng có thể được gộp trong dữ liệu mà bên nhận đọc được.

Với RSocket chạy trên TCP, transport có cơ chế đóng khung để khôi phục ranh giới RSocket frame từ byte stream. Việc đóng khung này vẫn khác với segmentation của TCP: length prefix của transport xác định kích thước frame, còn TCP segment chỉ vận chuyển byte.

TCP segmentation cũng không đồng nghĩa với **IP fragmentation**. TCP tạo segment dựa trên MSS và điều kiện đường truyền; IP fragmentation là việc chia một IP packet ở tầng mạng khi cần. Đây là một cơ chế khác nữa, không tạo RSocket frame và không mang cờ FOLLOWS.

## 4. Ví dụ cùng một payload qua hai tầng

Giả sử ứng dụng tạo một payload 90 KB và implementation đặt giới hạn fragment RSocket khoảng 32 KB. RSocket có thể tạo ba fragment logic, ví dụ 32 KB, 32 KB và phần còn lại.

TCP sau đó có thể chia byte của các frame này thành nhiều segment theo MSS của đường truyền. Kích thước segment thực tế còn phụ thuộc TCP options, MTU, TLS và điều kiện mạng.

~~~text
Ứng dụng:
  Payload P (90 KB)
       |
       v
RSocket:
  Frame A (fragment 1, FOLLOWS=1)
  Frame B (fragment 2, FOLLOWS=1)
  Frame C (fragment 3, FOLLOWS=0)
       |
       v
TCP:
  Segment 1: một phần byte của Frame A
  Segment 2: phần còn lại của Frame A + byte tiếp theo
  Segment 3: byte của Frame B
  Segment 4: phần byte của Frame C
  ...
       |
       v
Bên nhận:
  TCP khôi phục byte stream
       |
  Transport tách các RSocket frame
       |
  RSocket ghép A + B + C
       |
  Ứng dụng nhận Payload P (90 KB)
~~~

Các con số chỉ minh họa. Không có quy tắc rằng một fragment RSocket phải tương ứng với một TCP segment. Fragment RSocket được quyết định bởi giới hạn frame của RSocket implementation; TCP segment được quyết định ở tầng transport và mạng.

## 5. Vai trò của giới hạn frame và kích thước fragment

Fragment size cần đủ nhỏ để frame sau khi cộng header và metadata vẫn nằm trong giới hạn mà transport chấp nhận. Khi chọn kích thước, cần xem xét:

- Giới hạn frame của RSocket implementation.
- Overhead của header, length prefix và metadata.
- Giới hạn của transport, proxy hoặc gateway.
- Kích thước payload thường gặp và payload lớn nhất.
- Số stream có thể cùng truyền payload lớn.
- Bộ nhớ cần cho các payload đang reassemble.

Không nên đặt fragment size bằng đúng kích thước payload tối đa nếu header và metadata có thể làm frame vượt giới hạn. Cũng không nên chọn fragment quá nhỏ: số frame tăng, overhead tăng và receiver phải quản lý nhiều mảnh hơn.

Cấu hình fragmentation phụ thuộc implementation và phiên bản thư viện RSocket Java. Hãy dùng API cấu hình max fragment/frame size do phiên bản đang triển khai cung cấp và xác minh cả client lẫn server. Không nên giả định chỉ cần chỉnh MSS của TCP là đã bật RSocket fragmentation.

Một số implementation cho phép cấu hình ngưỡng fragment ở connector/server. Khi dùng Spring Boot, cấu hình thường được thực hiện qua RSocket connector mà ứng dụng sử dụng; tên method và cách truyền cấu hình phụ thuộc phiên bản Spring/RSocket Java. Kiểm tra tài liệu đúng phiên bản trước khi áp dụng cấu hình vào production.

## 6. Metadata và data khi phân mảnh

Một RSocket payload có thể có metadata và data. Khi payload bị phân mảnh, thứ tự logic của hai phần phải được giữ nguyên để receiver tái tạo đúng payload ban đầu.

Metadata được truyền trước data. Nếu metadata cũng vượt giới hạn fragment, các fragment đầu có thể chứa những phần tiếp theo của metadata; sau khi metadata đã được truyền hết mới đến phần data. Cờ M cho biết fragment có mang metadata. Receiver ghép metadata và data theo đúng thứ tự trước khi decode payload.

Điều này có một số hệ quả:

- Không giả định mọi fragment đều chứa cả metadata lẫn data.
- Không parse metadata hoặc decode DTO khi mới nhận fragment đầu.
- Giới hạn kích thước metadata riêng với data.
- Đảm bảo MIME type và codec tương thích giữa hai peer.
- Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết vào metadata.

Metadata lớn bất thường có thể gây tiêu tốn bộ nhớ tương tự data lớn. Vì vậy, tổng payload limit nên đi cùng giới hạn metadata và giới hạn kích thước từng trường.

## 7. Reassembly ở phía nhận

Receiver cần giữ các fragment của một payload cho đến khi nhận fragment cuối, tức fragment không bật FOLLOWS. Sau đó, nó ghép nội dung thành payload logic và chuyển đến handler/subscriber.

~~~mermaid
sequenceDiagram
    participant S as RSocket Sender
    participant T as Transport Receiver
    participant R as RSocket Reassembler
    participant A as Application
    S->>T: Byte stream chứa các frame
    T->>R: Frame 1 (Stream 17, FOLLOWS=1)
    T->>R: Frame 2 (Stream 17, FOLLOWS=1)
    T->>R: Frame 3 (Stream 17, FOLLOWS=0)
    Note over R: Ghép metadata và data
    R->>A: Một payload logic hoàn chỉnh
~~~

Reassembly cần giữ đúng thứ tự và đúng Stream ID. Nếu thiếu fragment hoặc kết nối bị đóng giữa chừng, payload chưa hoàn chỉnh không được chuyển lên ứng dụng như dữ liệu hợp lệ.

Việc reassemble tiêu tốn bộ nhớ. Với nhiều stream cùng gửi payload lớn, lượng bộ nhớ cần thiết có thể xấp xỉ tổng kích thước các payload đang chờ hoàn tất, cộng overhead của buffer và object. Do đó, giới hạn kích thước frame đơn lẻ chưa đủ để bảo vệ ứng dụng.

Nên áp dụng các giới hạn độc lập:

- Kích thước tối đa của payload logic sau reassembly.
- Kích thước tối đa của metadata.
- Số payload đang được reassemble đồng thời.
- Thời gian tối đa một payload được phép ở trạng thái chưa hoàn tất.
- Số fragment hoặc tổng byte được phép tích lũy.
- Cleanup khi stream bị CANCEL, ERROR hoặc connection đóng.

## 8. TCP segmentation có thể gây head-of-line blocking

TCP đảm bảo byte được giao theo thứ tự. Nếu một segment bị mất, TCP phải truyền lại và dữ liệu phía sau trên cùng byte stream có thể phải chờ cho đến khi phần byte thiếu được khôi phục.

Điều này tạo ra head-of-line blocking ở tầng TCP. RSocket multiplex nhiều stream trên một kết nối, nhưng nếu dùng chung một TCP connection thì các byte của những stream đó vẫn đi qua cùng một byte stream có thứ tự. Một packet loss có thể làm chậm việc giao byte cho nhiều stream trên kết nối đó.

RSocket fragmentation và TCP segmentation không loại bỏ hiện tượng này. Fragment nhỏ có thể giúp giới hạn kích thước frame và bộ nhớ reassembly, nhưng không làm TCP mất tính chất byte stream có thứ tự.

Nếu độ trễ do mất gói là vấn đề quan trọng, cần đo RTT, retransmission, packet loss và latency đầu-cuối. Việc đổi transport hoặc chia tải qua nhiều kết nối là quyết định kiến trúc riêng, không phải tác dụng tự động của fragmentation.

## 9. Khi nào dùng RSocket fragmentation, khi nào chia chunk ở tầng ứng dụng?

RSocket fragmentation phù hợp khi ứng dụng muốn gửi một payload logic lớn mà vẫn xem nó như một request hoặc một phần tử stream duy nhất. Fragmentation được xử lý ở tầng giao thức và thường trong suốt với handler.

Chia chunk ở tầng ứng dụng phù hợp khi nghiệp vụ cần kiểm soát từng phần dữ liệu:

| Nhu cầu | RSocket fragmentation | Application-level chunking |
|---|---|---|
| Chỉ cần chuyển một payload lớn | Phù hợp | Có thể không cần |
| Theo dõi tiến độ từng phần | Không biểu đạt tiến độ nghiệp vụ | Phù hợp |
| Retry riêng từng phần | Không phải mục tiêu chính | Có thể thiết kế |
| Resume từ offset sau disconnect | Không tự cung cấp offset nghiệp vụ | Có thể thiết kế cursor/offset |
| Kiểm tra checksum từng chunk | Không tự cung cấp quy tắc nghiệp vụ | Có thể thiết kế |
| Giới hạn bộ nhớ bằng streaming từng phần | Reassembly vẫn giữ payload logic | Có thể xử lý từng chunk rồi giải phóng |

Ví dụ upload tệp 2 GB thường không nên tạo một payload logic duy nhất rồi chờ reassemble toàn bộ trong heap. Có thể chia thành các chunk ở tầng ứng dụng, mỗi chunk có upload ID, offset, kích thước, checksum và trạng thái xác nhận. Server ghi từng chunk vào storage và chỉ giữ bộ nhớ cho phần đang xử lý.

Ví dụ hợp đồng cho một chunk ở tầng ứng dụng:

~~~java
public record UploadChunk(
    UUID uploadId,
    long offset,
    byte[] content,
    String sha256,
    boolean last
) {}

public record ChunkAck(long nextOffset, boolean accepted) {}
~~~

Client có thể gửi từng chunk và chờ xác nhận offset tiếp theo trước khi tiếp tục:

~~~java
Mono<ChunkAck> sendChunk(UploadChunk chunk) {
    return requester
        .route("uploads.chunk")
        .data(chunk)
        .retrieveMono(ChunkAck.class);
}
~~~

Đây chỉ là ví dụ về hợp đồng ứng dụng. Một triển khai hoàn chỉnh cần kiểm tra upload ID, offset, kích thước chunk, checksum, quyền truy cập và tính idempotent khi chunk được gửi lại.

Ngược lại, một request JSON 200 KB cần được xử lý như một đối tượng duy nhất có thể dùng RSocket fragmentation, miễn là giới hạn payload và tài nguyên reassembly được cấu hình phù hợp.

## 10. Kiểm soát tài nguyên và an toàn

Payload lớn có thể được sử dụng để làm tăng bộ nhớ, CPU giải mã hoặc thời gian giữ stream. Kẻ gửi có thể gửi rất nhiều fragment, gửi fragment chậm hoặc mở nhiều stream đồng thời để làm tăng số payload đang reassemble.

Các biện pháp cần cân nhắc:

- Đặt max frame size và max reassembled payload size.
- Giới hạn kích thước data và metadata riêng.
- Giới hạn số stream và số payload đang reassemble đồng thời.
- Đặt timeout cho quá trình reassembly hoặc stream không tiến triển.
- Dọn buffer khi nhận CANCEL, ERROR hoặc khi transport đóng.
- Xác thực và phân quyền peer trước khi thực hiện nghiệp vụ.
- Theo dõi số fragment, tổng byte, thời gian reassembly và overflow.
- Tránh log nội dung payload nhạy cảm.

Backpressure giới hạn số payload logic mà consumer yêu cầu; nó không tự giới hạn kích thước byte của từng payload. Một payload đơn lẻ vẫn có thể rất lớn dù consumer chỉ có một credit. Vì thế demand, payload size limit và reassembly memory limit phải được thiết kế cùng nhau.

## 11. Cách quan sát hai tầng khi debug

Khi phân tích một payload lớn bị lỗi hoặc chậm, cần thu thập thông tin riêng ở từng tầng.

**Ở tầng RSocket:**

- Stream ID và loại frame.
- Số fragment trên mỗi payload.
- Trạng thái FOLLOWS của fragment cuối.
- Kích thước data và metadata.
- Thời gian từ fragment đầu đến khi reassembly xong.
- Số payload đang reassemble và lỗi do vượt giới hạn.

**Ở tầng TCP:**

- Số TCP segment và kích thước segment.
- Retransmission, duplicate ACK và packet loss.
- RTT và thời gian truyền lại.
- Kết nối bị reset hoặc đóng.
- MTU/MSS và ảnh hưởng của TLS hoặc proxy.

Wireshark có thể giúp quan sát TCP segment và byte stream. Để xác định RSocket frame, cần giải mã hoặc tái dựng framing RSocket tương ứng. Không nên suy ra số fragment RSocket chỉ từ số segment TCP trong packet capture.

## 12. Kiểm thử fragmentation và TCP segmentation

Nên kiểm thử riêng từng tầng và kiểm thử tích hợp:

1. Payload nhỏ hơn fragment threshold: không cần fragmentation.
2. Payload vượt threshold một ít: receiver reassemble đúng một payload.
3. Payload lớn hơn nhiều fragment: FOLLOWS bật ở các fragment chưa cuối và tắt ở fragment cuối.
4. Payload có metadata: metadata được ghép đúng và nằm trước data.
5. Nhiều stream gửi payload lớn: reassembly không trộn fragment giữa các Stream ID.
6. Kết nối đóng giữa quá trình gửi fragment: payload chưa hoàn chỉnh bị loại bỏ và buffer được giải phóng.
7. Client hủy stream khi payload đang được reassemble: tài nguyên tạm được cleanup.
8. Payload vượt aggregate size limit: bị từ chối có kiểm soát.
9. Mô phỏng TCP segmentation hoặc packet loss: RSocket vẫn nhận byte stream đúng khi TCP phục hồi, hoặc nhận lỗi transport khi kết nối không thể phục hồi.

Ở tầng unit test, có thể kiểm tra logic xử lý payload và giới hạn kích thước. Ở tầng integration test, dùng RSocket client/server thật với fragment size được cấu hình nhỏ để dễ tạo nhiều fragment. Ở tầng mạng, công cụ mô phỏng packet loss hoặc packet capture giúp quan sát TCP segmentation độc lập.

## 13. Kết luận

RSocket fragmentation chia một payload logic thành nhiều RSocket frame và dùng FOLLOWS để báo còn fragment tiếp theo. Receiver ghép các fragment theo Stream ID, thứ tự và metadata/data trước khi chuyển một payload hoàn chỉnh lên ứng dụng.

TCP segmentation chia byte stream thành các segment để vận chuyển qua mạng. TCP không hiểu Stream ID, payload hoặc FOLLOWS; nó chỉ đảm bảo byte được khôi phục theo thứ tự. Một RSocket frame có thể đi qua nhiều TCP segment và một TCP segment có thể chứa byte của nhiều frame.

Khi thiết kế ứng dụng Java/Spring Boot, hãy dùng fragmentation cho payload cần được xử lý như một đơn vị logic, đặt giới hạn reassembly và metadata, và dùng chunk ở tầng ứng dụng khi cần tiến độ, retry từng phần hoặc resume theo offset. Phân biệt hai tầng này giúp đọc packet capture chính xác, kiểm soát bộ nhớ và chẩn đoán độ trễ realtime hiệu quả hơn.

Tài liệu tham khảo: [RSocket Protocol](https://rsocket.io/about/protocol/) và [RSocket Java](https://github.com/rsocket/rsocket-java).

