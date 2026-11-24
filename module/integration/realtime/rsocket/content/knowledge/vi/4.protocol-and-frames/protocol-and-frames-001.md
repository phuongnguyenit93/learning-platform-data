# Cấu trúc frame: độ dài, Stream ID, loại và cờ điều khiển

RSocket trao đổi dữ liệu bằng các **frame**. Mỗi frame có phần đầu chung để bên nhận xác định độ dài, luồng liên quan, loại thông điệp và các cờ điều khiển. Phần thân thay đổi theo loại frame, mang payload hoặc thông tin điều khiển của giao thức.

Hiểu cấu trúc frame giúp bạn đọc được dữ liệu trên TCP hoặc WebSocket, phân tích log và packet capture, phát hiện lỗi giao thức, cũng như hiểu cách request-response, fire-and-forget, stream và channel được ghép thành các luồng độc lập. Đây cũng là nền tảng để làm việc với metadata, fragmentation, flow control, keepalive và phục hồi kết nối trong RSocket.

Sau bài học này, bạn có thể:

- Mô tả cấu trúc header và vai trò của từng trường.
- Phân biệt tiền tố độ dài trên TCP với ranh giới message của WebSocket.
- Giải thích cách cấp phát Stream ID và nhận biết frame ở cấp kết nối hay cấp stream.
- Đọc Frame Type và các control flag phổ biến.
- Theo dõi một ví dụ frame trên wire và nhận diện một số lỗi định dạng thường gặp.

## 1. Frame là đơn vị thông điệp của RSocket

RSocket là giao thức nhị phân. Thay vì gửi các câu lệnh văn bản có dấu phân cách, hai đầu kết nối trao đổi frame với cấu trúc byte được quy định. Một frame có hai phần:

1. **Header**: thông tin chung để xác định frame và cách diễn giải phần thân.
2. **Body**: trường dữ liệu riêng của loại frame, có thể chứa payload ứng dụng, metadata hoặc thông tin điều khiển.

Header cho phép bên nhận biết frame thuộc stream nào và frame đang thực hiện hành động gì trước khi giải mã body. Ví dụ, REQUEST_STREAM khởi tạo một stream; REQUEST_N yêu cầu thêm phần tử; PAYLOAD mang dữ liệu hoặc tín hiệu kết thúc; CANCEL yêu cầu hủy stream.

Một kết nối RSocket có thể đồng thời mang nhiều stream. Các frame của nhiều stream có thể xen kẽ trên cùng một kết nối vật lý. Stream ID trong header giúp bên nhận ghép mỗi frame vào đúng cuộc tương tác.

~~~mermaid
flowchart TD
    A[Kết nối TCP hoặc WebSocket] --> B[Nhận frame]
    B --> C[Đọc header]
    C --> D[Độ dài]
    C --> E[Stream ID]
    C --> F[Frame Type và Flags]
    D --> G[Kiểm tra ranh giới frame]
    E --> H[Chọn stream hoặc cấp kết nối]
    F --> I[Chọn cách giải mã body]
    G --> J[Giải mã body theo loại frame]
    H --> J
    I --> J
    J --> K[Cập nhật trạng thái giao thức]
~~~

Không nên xem một frame luôn tương ứng với một đối tượng nghiệp vụ hoàn chỉnh. Một request có thể tạo ra nhiều frame trong suốt vòng đời stream; một payload lớn có thể được chia thành nhiều frame; và một số frame chỉ điều khiển luồng mà không mang dữ liệu nghiệp vụ.

## 2. Header chung và thứ tự các trường

Phần header cốt lõi của RSocket có 6 byte:

| Trường | Kích thước | Vai trò |
|---|---:|---|
| Stream ID | 32 bit (4 byte) | Xác định stream mà frame thuộc về |
| Frame Type và Flags | 16 bit (2 byte) | Xác định loại frame và các cờ điều khiển |

Với TCP, trước header 6 byte này có thêm **tiền tố độ dài 24 bit (3 byte)**. Vì vậy, phần đầu được truyền trên TCP có tổng cộng 9 byte trước body. Tiền tố độ dài không được tính vào giá trị độ dài mà nó mô tả.

~~~text
TCP transport
+----------------------+----------------------+----------------------+-------------------+
| Frame Length         | Stream ID            | Frame Type + Flags   | Frame Body        |
| 24 bit / 3 byte      | 32 bit / 4 byte      | 16 bit / 2 byte      | thay đổi          |
+----------------------+----------------------+----------------------+-------------------+
       3 byte                 4 byte                 2 byte
       <----------------------- Frame Length ---------------------->
                                Không tính 3 byte tiền tố
~~~

Với WebSocket, mỗi WebSocket binary message mang một RSocket frame. Ranh giới message của WebSocket đã xác định điểm bắt đầu và kết thúc frame, vì vậy không cần tiền tố độ dài 24 bit của TCP:

~~~text
Một WebSocket binary message
+----------------------+----------------------+-------------------+
| Stream ID            | Frame Type + Flags   | Frame Body        |
| 32 bit / 4 byte      | 16 bit / 2 byte      | thay đổi          |
+----------------------+----------------------+-------------------+
       4 byte                 2 byte
~~~

Các trường số được mã hóa theo thứ tự byte mạng (big-endian): byte có trọng số cao được truyền trước. Khi đọc packet capture, cần xác định transport trước để biết ba byte đầu có phải tiền tố độ dài RSocket hay không. Không được tự động diễn giải ba byte đầu của một WebSocket message như frame length.

### TCP và WebSocket cung cấp ranh giới frame theo cách khác nhau

TCP là luồng byte, không bảo toàn ranh giới lần ghi của ứng dụng. Một lần đọc từ socket có thể nhận một phần frame, đúng một frame hoặc nhiều frame liên tiếp. Receiver phải dùng tiền tố độ dài để đợi đủ byte và tách từng frame.

WebSocket cung cấp ranh giới message ở tầng transport. Với RSocket over WebSocket, một message nhị phân chứa một frame RSocket; không thêm tiền tố độ dài TCP vào đầu message. WebSocket có thể phân mảnh message ở tầng riêng của nó, nhưng điều đó khác với fragmentation do giao thức RSocket điều khiển bằng cờ F.

Hai kiểu fragmentation này thuộc hai tầng khác nhau:

- **WebSocket fragmentation** chia một WebSocket message thành các WebSocket frame theo quy tắc của WebSocket.
- **RSocket fragmentation** chia payload giao thức thành nhiều RSocket frame; cờ F và quy tắc ghép fragment của RSocket điều khiển việc tái tạo payload.

## 3. Frame Length: độ dài của frame trên TCP

Tiền tố độ dài TCP là một số nguyên không dấu 24 bit, được mã hóa big-endian. Nó cho biết số byte theo sau tiền tố, bao gồm header RSocket 6 byte và body, nhưng không bao gồm chính 3 byte tiền tố.

Vì trường có 24 bit nên giá trị lớn nhất có thể biểu diễn là:

\[
2^{24} - 1 = 16\,777\,215 \text{ byte}
\]

Đây là giới hạn biểu diễn của trường độ dài. Ứng dụng vẫn nên áp dụng giới hạn frame tối đa phù hợp với cấu hình và tài nguyên của hệ thống.

Ví dụ, nếu tiền tố chứa giá trị 8:

~~~text
00 00 08
~~~

thì receiver cần đọc thêm đúng 8 byte để có một frame hoàn chỉnh. Tám byte này gồm 6 byte header cốt lõi và 2 byte body. Tổng số byte trên TCP là 3 + 8 = 11 byte.

Các tình huống cần xử lý khi đọc TCP:

- Chưa nhận đủ 3 byte tiền tố: tiếp tục chờ dữ liệu.
- Đã đọc tiền tố nhưng chưa nhận đủ số byte được khai báo: giữ dữ liệu đã nhận và chờ phần còn lại.
- Đã nhận đủ frame: chuyển frame cho bộ giải mã rồi tiếp tục đọc frame tiếp theo nếu buffer còn dữ liệu.
- Độ dài nhỏ hơn header cốt lõi 6 byte: frame không hợp lệ.
- Độ dài vượt giới hạn cho phép của ứng dụng: từ chối frame theo chính sách giao thức và tài nguyên.

Không nên giả định một lần đọc TCP sẽ trả về đúng một frame. Một buffer có thể chứa phần cuối của frame trước và toàn bộ hoặc một phần của frame sau. Bộ giải mã phải duy trì trạng thái buffer qua nhiều lần đọc.

### Vì sao độ dài không nằm trong WebSocket message?

WebSocket đã đóng gói message và cung cấp chiều dài của message ở tầng transport. Nếu thêm tiền tố độ dài TCP vào một message WebSocket, receiver sẽ diễn giải sai vị trí Stream ID và các trường tiếp theo. Do đó, quy tắc giải mã cần gắn với transport:

| Transport | Cách xác định ranh giới RSocket frame |
|---|---|
| TCP | Đọc tiền tố 24 bit, sau đó đọc đủ số byte được khai báo |
| WebSocket | Dùng ranh giới của binary message; bắt đầu RSocket header ngay tại byte đầu message |

## 4. Stream ID: định tuyến frame vào đúng cuộc tương tác

Stream ID chiếm 32 bit trong header, nhưng chỉ 31 bit thấp được dùng làm giá trị ID. Bit cao nhất được dành riêng và phải bằng 0. Vì vậy, Stream ID là một số nguyên không âm trong phạm vi 31 bit.

Stream ID có hai vai trò chính:

- Giá trị **0** dành cho frame ở cấp kết nối, không thuộc một stream ứng dụng cụ thể.
- Giá trị **khác 0** xác định một stream cụ thể.

Hai bên sử dụng quy tắc chẵn/lẻ để tránh cấp trùng ID cho các stream do mỗi bên khởi tạo:

| Bên khởi tạo | Quy tắc Stream ID | Ví dụ |
|---|---|---|
| Client | Số lẻ dương | 1, 3, 5, 7, ... |
| Server | Số chẵn dương | 2, 4, 6, 8, ... |
| Cấp kết nối | 0 | 0 |

Mỗi bên tăng ID của mình theo bước 2 khi tạo stream mới. ID đã sử dụng không được tái sử dụng trong cùng kết nối. Quy tắc này giúp hai bên xác định bên khởi tạo stream và tránh nhầm lẫn khi nhiều request đang chạy đồng thời.

### Ví dụ nhiều stream trên cùng một kết nối

Giả sử client mở hai tương tác:

- Stream 1 dùng cho request-response lấy thông tin sản phẩm.
- Stream 3 dùng cho request-stream theo dõi giá.

Server có thể gửi response cho hai stream xen kẽ. Frame mang Stream ID 1 được chuyển tới state của stream 1; frame mang Stream ID 3 được chuyển tới state của stream 3. Cả hai cùng đi qua một kết nối TCP hoặc WebSocket.

~~~text
Client                                  Server
  |                                       |
  |--- REQUEST_RESPONSE, stream=1 -------->|
  |--- REQUEST_STREAM, stream=3 ---------->|
  |<-- PAYLOAD, stream=3 ------------------|
  |<-- PAYLOAD, stream=1 ------------------|
  |<-- PAYLOAD, stream=3 ------------------|
  |<-- PAYLOAD + COMPLETE, stream=3 -------|
  |                                       |
~~~

Các frame thuộc cùng một stream được ghép theo Stream ID, không phải theo thứ tự chúng xuất hiện cạnh nhau trong packet capture. Các stream độc lập có thể tiến triển đồng thời.

### Stream ID 0 không phải một stream rỗng

Stream ID 0 biểu thị phạm vi kết nối. Các frame như SETUP, KEEPALIVE, LEASE, METADATA_PUSH và các frame RESUME sử dụng phạm vi kết nối theo quy tắc của từng loại. Ngược lại, REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL, REQUEST_FNF, REQUEST_N, CANCEL và các PAYLOAD thông thường gắn với stream cụ thể.

ERROR có thể biểu thị lỗi ở cấp stream hoặc cấp kết nối tùy Stream ID và ngữ cảnh. Khi đọc log, hãy xem Stream ID cùng Frame Type; chỉ nhìn tên ERROR sẽ chưa đủ để xác định phạm vi lỗi.

Không được tự ý đổi Stream ID khi một tương tác đang diễn ra. Các frame phản hồi, payload tiếp theo, tín hiệu hoàn tất và hủy phải tham chiếu đúng stream đã được khởi tạo.

## 5. Frame Type: loại thông điệp cần diễn giải

Frame Type chiếm 6 bit cao của trường 16 bit kết hợp với Flags. Nó cho biết body phải được giải mã theo cấu trúc nào và frame thực hiện hành động gì.

Một số loại frame thường gặp:

| Mã hex | Frame Type | Phạm vi thường dùng | Vai trò |
|---:|---|---|---|
| 0x01 | SETUP | Kết nối | Khởi tạo phiên RSocket và thương lượng tham số |
| 0x02 | LEASE | Kết nối | Cấp quyền hoặc quota khởi tạo request theo cơ chế lease |
| 0x03 | KEEPALIVE | Kết nối | Duy trì kết nối và hỗ trợ phát hiện mất kết nối |
| 0x04 | REQUEST_RESPONSE | Stream | Khởi tạo request có tối đa một response |
| 0x05 | REQUEST_FNF | Stream | Khởi tạo fire-and-forget |
| 0x06 | REQUEST_STREAM | Stream | Khởi tạo request có chuỗi response |
| 0x07 | REQUEST_CHANNEL | Stream | Khởi tạo tương tác có luồng dữ liệu hai chiều |
| 0x08 | REQUEST_N | Stream | Yêu cầu thêm số lượng phần tử từ publisher |
| 0x09 | CANCEL | Stream | Hủy một stream đang hoạt động |
| 0x0A | PAYLOAD | Stream | Mang payload hoặc tín hiệu điều khiển kết thúc |
| 0x0B | ERROR | Stream hoặc kết nối | Báo lỗi ở phạm vi tương ứng |
| 0x0C | METADATA_PUSH | Kết nối | Gửi metadata ở cấp kết nối |
| 0x0D | RESUME | Kết nối | Yêu cầu tiếp tục phiên đã được lưu |
| 0x0E | RESUME_OK | Kết nối | Xác nhận yêu cầu tiếp tục phiên |
| 0x3F | EXT | Theo extension | Mang dữ liệu mở rộng theo thỏa thuận giữa hai bên |

Mã trong bảng là giá trị 6 bit của Frame Type, không phải toàn bộ 16 bit Frame Type và Flags. Khi giải mã, cần tách riêng hai trường.

### Frame khởi tạo và frame tiếp diễn

Các frame REQUEST_RESPONSE, REQUEST_FNF, REQUEST_STREAM và REQUEST_CHANNEL thường là frame khởi tạo stream từ một bên. Sau đó, các frame như PAYLOAD, REQUEST_N, CANCEL hoặc ERROR điều khiển hoặc kết thúc stream theo mô hình tương tác.

| Mô hình | Frame khởi tạo | Frame tiếp diễn thường gặp |
|---|---|---|
| Request-response | REQUEST_RESPONSE | PAYLOAD hoặc ERROR |
| Fire-and-forget | REQUEST_FNF | Không có response payload; bên gửi không chờ xác nhận nghiệp vụ từ server |
| Request-stream | REQUEST_STREAM | PAYLOAD, REQUEST_N, CANCEL, ERROR |
| Request-channel | REQUEST_CHANNEL | PAYLOAD, REQUEST_N, CANCEL, ERROR |

Bảng mô tả các loại frame tiêu biểu. Trình tự thực tế còn phụ thuộc trạng thái stream, hướng truyền, yêu cầu dữ liệu và tín hiệu kết thúc. Ví dụ, request-stream cần được cấp quyền phát thêm phần tử bằng cơ chế demand; REQUEST_N mang số lượng phần tử bên nhận sẵn sàng tiêu thụ.

### Body phụ thuộc vào Frame Type

Header chung không đủ để giải mã toàn bộ frame. Mỗi loại frame quy định body riêng. Một vài ví dụ:

- SETUP chứa phiên bản giao thức, các tham số keepalive, MIME type cho metadata và data, cùng payload khởi tạo nếu có.
- REQUEST_STREAM và REQUEST_CHANNEL chứa thông tin số lượng phần tử ban đầu được yêu cầu, cùng payload ban đầu.
- REQUEST_N chứa số lượng phần tử bổ sung mà bên nhận yêu cầu.
- ERROR chứa mã lỗi và thông tin mô tả lỗi.
- KEEPALIVE chứa thông tin phục vụ keepalive và dữ liệu tùy chọn.
- PAYLOAD chứa metadata nếu được đánh dấu, sau đó là data.

Do đó, không được coi mọi byte sau 6 byte header đều là data nghiệp vụ. Bộ giải mã phải dựa trên Frame Type, Flags và các trường độ dài bên trong body nếu loại frame quy định.

## 6. Flags: các cờ điều khiển trong header

Flags chiếm 10 bit thấp của trường 16 bit kết hợp với Frame Type. Cờ bổ sung ý nghĩa cho frame mà không cần tạo một Frame Type mới cho mọi biến thể.

Một số cờ phổ biến:

| Cờ | Tên thường dùng | Ý nghĩa trong ngữ cảnh áp dụng |
|---|---|---|
| M | Metadata | Frame có phần metadata trong payload hoặc cấu trúc tương ứng |
| F | Follows | Còn fragment tiếp theo của payload |
| C | Complete | Stream được đánh dấu hoàn tất |
| N | Next | Frame mang một payload tiếp theo |
| R | Respond hoặc Resume | Ý nghĩa phụ thuộc loại frame; ví dụ KEEPALIVE yêu cầu phản hồi |
| I | Ignore | Cho phép bỏ qua extension frame nếu bên nhận không hiểu |
| L | Lease | Trong SETUP, cho biết khả năng sử dụng cơ chế lease |

Không phải cờ nào cũng có ý nghĩa với mọi Frame Type. Một bit có thể được diễn giải khác nhau theo loại frame; vì vậy, không được đọc Flags tách rời khỏi Frame Type. Các bit không được định nghĩa cho loại frame tương ứng phải tuân theo quy tắc của giao thức và không được tự gán ý nghĩa.

### Metadata (M)

Khi M được bật, frame có phần metadata theo cấu trúc của loại frame đó. Với payload thông thường, metadata được đặt trước data và có trường độ dài metadata 24 bit để bên nhận xác định ranh giới.

~~~text
PAYLOAD body khi có M
+----------------------+----------------------+-------------------+
| Metadata Length      | Metadata             | Data              |
| 24 bit / 3 byte      | số byte được khai báo| phần còn lại      |
+----------------------+----------------------+-------------------+
~~~

Metadata có thể chứa routing, MIME type hoặc thông tin phục vụ xử lý ứng dụng tùy quy ước hai bên. M cho biết phần metadata hiện diện; nó không nói nội dung metadata là gì. Bên nhận cần biết metadata encoding hoặc MIME type đã thỏa thuận để giải mã chính xác.

### Follows (F) và fragmentation

F cho biết payload đang được phân mảnh và còn fragment tiếp theo. Bên nhận phải ghép các phần theo quy tắc fragmentation của RSocket trước khi xử lý payload hoàn chỉnh.

~~~text
Frame fragment 1: F = 1  ---> còn fragment
Frame fragment 2: F = 1  ---> còn fragment
Frame fragment cuối: F = 0 ---> đã hết fragment
~~~

Fragmentation giúp truyền payload lớn trong giới hạn frame. Bên nhận cần giữ trạng thái ghép fragment đúng stream, kiểm tra kích thước tổng và xử lý trường hợp chuỗi fragment bị gián đoạn hoặc kết nối mất giữa chừng.

F là cờ ở tầng RSocket. Không nhầm nó với việc TCP chia byte thành nhiều segment hoặc WebSocket chia message thành nhiều WebSocket frame.

### Next (N) và Complete (C)

Trong PAYLOAD, N và C biểu diễn hai tín hiệu khác nhau:

- N cho biết frame mang một payload tiếp theo.
- C cho biết stream hoàn tất.

Hai cờ có thể kết hợp. Khi một PAYLOAD mang cả N và C, bên nhận xử lý payload cuối cùng rồi ghi nhận stream đã hoàn tất. Khi C được bật mà N không bật, frame biểu diễn tín hiệu hoàn tất mà không có payload tiếp theo.

Điều này tương ứng với cách Reactor biểu diễn chuỗi tín hiệu: một publisher có thể phát phần tử rồi hoàn tất, hoặc hoàn tất mà không phát phần tử. Cờ giao thức cho phép RSocket truyền đạt các trạng thái này trên wire.

### Respond (R), Ignore (I) và Lease (L)

Một số cờ chỉ dùng trong một số loại frame:

- Trong KEEPALIVE, cờ Respond yêu cầu peer gửi phản hồi keepalive.
- Trong SETUP, các cờ có thể thông báo khả năng resume hoặc lease được bật cho phiên.
- Trong EXT, cờ Ignore cho biết extension frame có thể được bỏ qua nếu peer không hỗ trợ extension đó.

Tên gọi và ý nghĩa cụ thể cần được đọc theo Frame Type. Ví dụ, ký hiệu R trong KEEPALIVE mang nghĩa yêu cầu phản hồi; R trong ngữ cảnh SETUP liên quan đến khả năng resume. Cùng một vị trí bit không đồng nghĩa với cùng một hành vi ở mọi frame.

## 7. Đọc một header cụ thể

Xét frame TCP minh họa sau:

~~~text
00 00 08 | 00 00 00 01 | 10 00 | 68 69
^^^^^^^^   ^^^^^^^^^^^   ^^^^^   ^^^^^
Length     Stream ID     Type    Body
                       + Flags
~~~

Giải mã lần lượt:

1. Ba byte đầu là 00 00 08, tức frame có 8 byte theo sau tiền tố.
2. Bốn byte tiếp theo là 00 00 00 01, tức Stream ID bằng 1.
3. Hai byte tiếp theo là 10 00, tức trường Frame Type và Flags có giá trị 0x1000.
4. Sáu bit cao của 0x1000 cho Frame Type 0x04, tức REQUEST_RESPONSE.
5. Mười bit thấp bằng 0, nghĩa là không có cờ nào được bật.
6. Hai byte body 68 69 là dữ liệu UTF-8 minh họa cho chuỗi “hi”.

Frame có 6 byte header cốt lõi và 2 byte body, tổng cộng 8 byte sau tiền tố. Trên TCP, tổng số byte truyền là 11.

Đây là ví dụ giải mã header và body tối giản để minh họa cách tính offset. Payload thực tế có thể cần metadata, trường body riêng hoặc cấu trúc dữ liệu theo hợp đồng ứng dụng.

### Công thức tách Frame Type và Flags

Gọi hai byte chứa Frame Type và Flags là một số nguyên không dấu 16 bit:

\[
word = (byte_1 \ll 8) \;|\; byte_2
\]

Khi đó:

\[
frameType = (word \gg 10) \;\&\; 0x3F
\]

\[
flags = word \;\&\; 0x03FF
\]

Sáu bit cao là Frame Type; mười bit thấp là Flags. Phép AND với 0x3F và 0x03FF giúp loại bỏ các bit không thuộc trường đang lấy.

## 8. Ví dụ đọc header bằng Java

Đoạn mã sau minh họa cách đọc header từ một buffer TCP đã có đủ ít nhất 9 byte. Mã chỉ tách trường header; việc kiểm tra body theo Frame Type cần được thực hiện ở bước tiếp theo.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class RSocketHeaderReader {

    private static final int CORE_HEADER_LENGTH = 6;
    private static final int TCP_LENGTH_PREFIX = 3;
    private static final int MAX_FRAME_LENGTH = 1024 * 1024;

    public static Header readTcpHeader(ByteBuffer source) {
        ByteBuffer buffer = source.slice()
            .order(ByteOrder.BIG_ENDIAN);

        if (buffer.remaining() < TCP_LENGTH_PREFIX) {
            throw new IllegalArgumentException(
                "Chưa đủ byte để đọc frame length"
            );
        }

        int frameLength =
            ((buffer.get() & 0xFF) << 16)
            | ((buffer.get() & 0xFF) << 8)
            | (buffer.get() & 0xFF);

        if (frameLength < CORE_HEADER_LENGTH) {
            throw new IllegalArgumentException(
                "Frame length nhỏ hơn header tối thiểu"
            );
        }

        if (frameLength > MAX_FRAME_LENGTH) {
            throw new IllegalArgumentException(
                "Frame vượt giới hạn cấu hình"
            );
        }

        if (buffer.remaining() < frameLength) {
            throw new IllegalArgumentException(
                "Buffer chưa chứa đủ toàn bộ frame"
            );
        }

        int streamId = buffer.getInt();

        if (streamId < 0) {
            throw new IllegalArgumentException(
                "Bit cao dành riêng của Stream ID phải bằng 0"
            );
        }

        int typeAndFlags = buffer.getShort() & 0xFFFF;
        int frameType = (typeAndFlags >>> 10) & 0x3F;
        int flags = typeAndFlags & 0x03FF;

        return new Header(
            frameLength,
            streamId,
            frameType,
            flags
        );
    }

    public record Header(
        int frameLength,
        int streamId,
        int frameType,
        int flags
    ) {}
}
~~~

Trong parser dùng thực tế, cần phân biệt lỗi “buffer chưa đủ dữ liệu” với lỗi frame không hợp lệ. Với TCP, trường hợp chưa đủ dữ liệu là bình thường: decoder nên giữ lại byte đã nhận và chờ lần đọc tiếp theo thay vì đóng kết nối ngay. Ví dụ trên ném exception để làm rõ các bước kiểm tra, không phải một decoder streaming hoàn chỉnh.

Ngoài ra, MAX_FRAME_LENGTH trong ví dụ là giới hạn ứng dụng tự chọn, thấp hơn giới hạn biểu diễn 24 bit. Không nên sao chép con số này mà không cân nhắc kích thước payload, bộ nhớ và chính sách vận hành của hệ thống.

## 9. Kiểm tra tính hợp lệ và xử lý frame an toàn

Một decoder cần xác minh cả header lẫn body. Các kiểm tra cơ bản gồm:

| Kiểm tra | Điều cần xác minh |
|---|---|
| Ranh giới frame | Đã nhận đủ prefix và đủ số byte của frame chưa? |
| Frame Length | Có ít nhất 6 byte header cốt lõi và không vượt giới hạn cấu hình không? |
| Stream ID | Bit cao dành riêng có bằng 0 không? Giá trị 0 có phù hợp với Frame Type không? |
| Frame Type | Loại frame có được hỗ trợ và có đúng phạm vi stream/kết nối không? |
| Flags | Các cờ có hợp lệ đối với Frame Type này không? |
| Body | Các trường có đủ byte và đúng thứ tự theo định nghĩa frame không? |
| Metadata | Metadata length có nằm trong body và không vượt ranh giới frame không? |
| Fragmentation | Chuỗi fragment có đúng thứ tự và nằm trong giới hạn kích thước không? |

Một vài lỗi phổ biến khi tự phân tích frame:

- Đọc tiền tố độ dài TCP khi transport thực tế là WebSocket.
- Tính Frame Length bao gồm cả 3 byte tiền tố, dẫn đến lệch ranh giới frame tiếp theo.
- Đọc Stream ID như số có dấu rồi không kiểm tra bit cao dành riêng.
- Dùng toàn bộ 16 bit làm Frame Type thay vì tách 6 bit type và 10 bit flags.
- Diễn giải một cờ mà không xét Frame Type.
- Giả định mọi body đều bắt đầu bằng data, trong khi metadata hoặc trường điều khiển có thể đứng trước.
- Coi mỗi lần đọc socket là một frame hoàn chỉnh.
- Ghép fragment thuộc các stream khác nhau hoặc không giới hạn tổng kích thước dữ liệu ghép.

Frame Length và metadata length đến từ dữ liệu trên wire. Khi xử lý kết nối không đáng tin cậy, phải xác minh giá trị trước khi cấp phát bộ nhớ hoặc sao chép dữ liệu. Giới hạn kích thước frame, kích thước metadata, kích thước payload sau ghép và số lượng fragment giúp tránh tiêu thụ tài nguyên quá mức.

Nếu nhận một Frame Type mở rộng mà peer không hiểu, khả năng bỏ qua phụ thuộc quy tắc extension và cờ Ignore. Không được bỏ qua tùy ý một frame điều khiển cốt lõi mà hệ thống cần để duy trì trạng thái stream hoặc kết nối.

## 10. Liên hệ header với vòng đời tương tác RSocket

Khi một client gọi request-response, request ban đầu tạo một stream với ID mới. Server gửi PAYLOAD hoặc ERROR trên cùng Stream ID. Header giúp cả hai bên biết frame phản hồi thuộc request nào.

Với request-stream, client gửi REQUEST_STREAM kèm số lượng phần tử ban đầu muốn nhận. Khi cần thêm dữ liệu, client gửi REQUEST_N. Server gửi PAYLOAD cho từng phần tử và dùng tín hiệu Complete khi stream kết thúc. Nếu client không còn cần dữ liệu, client có thể gửi CANCEL.

Với request-channel, hai hướng dữ liệu cùng gắn với một stream ID. Các frame PAYLOAD có thể đi từ client sang server và từ server về client; demand và completion được quản lý theo quy tắc channel.

Fire-and-forget dùng REQUEST_FNF để gửi một thông điệp không yêu cầu response payload. Header vẫn mang Stream ID để giao thức nhận diện tương tác. Vì bên gửi không chờ response nghiệp vụ, nếu ứng dụng cần xác nhận rằng server đã xử lý thành công thì nên dùng một mô hình tương tác có response hoặc thiết kế cơ chế xác nhận riêng.

Các frame cấp kết nối như KEEPALIVE không đại diện cho một request nghiệp vụ riêng. Chúng dùng Stream ID 0 và giúp hai bên theo dõi trạng thái kết nối. SETUP cũng thuộc giai đoạn thiết lập kết nối, mang các tham số cần thiết trước khi trao đổi request thông thường.

Có thể hình dung mối liên hệ như sau:

~~~mermaid
flowchart TD
    A[SETUP - Stream ID 0] --> B[Kết nối sẵn sàng]
    B --> C[REQUEST_RESPONSE - Stream 1]
    B --> D[REQUEST_STREAM - Stream 3]
    C --> E[PAYLOAD hoặc ERROR - Stream 1]
    D --> F[PAYLOAD - Stream 3]
    F --> G[REQUEST_N - Stream 3]
    G --> H[PAYLOAD tiếp theo]
    H --> I[COMPLETE hoặc CANCEL]
    B --> J[KEEPALIVE - Stream ID 0]
~~~

Header là lớp định tuyến và điều khiển cơ bản. Để hiểu toàn bộ hành vi, cần kết hợp Stream ID và Frame Type với trạng thái stream, demand, metadata và các quy tắc body tương ứng.

## 11. Quy trình đọc frame trong packet capture

Khi điều tra một phiên RSocket, hãy thực hiện theo trình tự sau:

1. Xác định transport là TCP hay WebSocket.
2. Nếu là TCP, đọc 3 byte Frame Length và tách frame theo đúng số byte khai báo.
3. Đọc 4 byte Stream ID; xác minh giá trị và bên khởi tạo stream theo quy tắc chẵn/lẻ.
4. Đọc 2 byte Frame Type và Flags; tách 6 bit type và 10 bit flags.
5. Tra cấu trúc body theo Frame Type, rồi kiểm tra các cờ có ảnh hưởng đến cách đọc body.
6. Ghép các frame có cùng Stream ID để dựng lại trình tự tương tác.
7. Theo dõi các tín hiệu terminal, demand, cancellation, lỗi và keepalive để hiểu trạng thái cuối cùng.

Ví dụ, nếu thấy REQUEST_STREAM với Stream ID 5, sau đó là nhiều PAYLOAD cùng ID, xen giữa là REQUEST_N cũng cùng ID, đó là một tương tác stream đang được điều tiết theo nhu cầu. Nếu một PAYLOAD trên cùng ID mang cờ Complete, stream đã kết thúc bình thường. Nếu xuất hiện ERROR, cần đọc phạm vi và mã lỗi trong body để xác định nguyên nhân.

Nếu thấy KEEPALIVE với Stream ID 0, hãy phân tích nó ở cấp kết nối. Không ghép nó vào stream gần nhất chỉ vì nó xuất hiện ngay sau frame của stream đó trong packet capture.

## 12. Ghi nhớ

- Header cốt lõi của RSocket gồm Stream ID 32 bit và Frame Type + Flags 16 bit.
- TCP có tiền tố độ dài 24 bit ở trước header; giá trị độ dài không tính ba byte tiền tố.
- WebSocket dùng ranh giới binary message và không thêm tiền tố độ dài TCP.
- Stream ID dùng 31 bit; 0 dành cho phạm vi kết nối, client khởi tạo stream bằng ID lẻ và server bằng ID chẵn.
- Frame Type chiếm 6 bit cao; Flags chiếm 10 bit thấp của trường 16 bit.
- Body thay đổi theo Frame Type; cần giải mã theo cấu trúc cụ thể của từng loại.
- Ý nghĩa Flags phụ thuộc Frame Type; không được diễn giải một bit độc lập với loại frame.
- Khi đọc TCP, phải xử lý partial read và nhiều frame trong cùng buffer.
- Luôn xác minh độ dài, Stream ID, Flags và trường độ dài trong body trước khi xử lý hoặc cấp phát bộ nhớ.

Khi nắm được cấu trúc frame, bạn có thể theo dõi cách RSocket thiết lập kết nối, khởi tạo stream, truyền payload, điều tiết dữ liệu, kết thúc tương tác và duy trì phiên. Đây là cơ sở để học sâu hơn về payload, metadata, session setup, flow control, fragmentation và resume.

