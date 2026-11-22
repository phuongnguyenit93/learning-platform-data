# content-type, content-length và dữ liệu nhị phân trong STOMP

## 1. Vì sao STOMP cần hai header này?

STOMP là giao thức messaging dạng frame. Một frame có command, các header, một dòng trống ngăn cách header với body và phần body tùy chọn. Các command SEND, MESSAGE và ERROR có thể mang body; những command còn lại không có body.

Hai header mô tả hai khía cạnh khác nhau của body:

- **content-type** cho biết định dạng hoặc kiểu nội dung của body, theo MIME type. Receiver dùng thông tin này để chọn cách giải mã hoặc chuyển đổi payload.
- **content-length** cho biết chính xác số octet (byte) của body. Decoder dùng giá trị này để xác định nơi body kết thúc.

STOMP ban đầu được thiết kế với frame text-oriented, nhưng body có thể là dữ liệu nhị phân. Vì vậy, không được giả định body luôn là chuỗi UTF-8 hoặc có thể tìm điểm kết thúc bằng cách chuyển toàn bộ body thành String.

Hai header này không thay thế nhau. content-type không cho biết độ dài body; content-length không nói body là JSON, văn bản, ảnh hay dữ liệu nhị phân.

## 2. Cấu trúc frame và vị trí body

Cấu trúc STOMP frame:

~~~text
COMMAND
header-name:header-value
header-name:header-value

body bytes
NULL
~~~

Các phần:

1. Command nằm ở dòng đầu, ví dụ SEND hoặc MESSAGE.
2. Mỗi header nằm trên một dòng riêng theo dạng tên:giá trị.
3. Một dòng trống kết thúc phần header.
4. Body bắt đầu ngay sau dòng trống.
5. Frame kết thúc bằng một octet NULL có giá trị 0x00.

STOMP 1.2 mặc định dùng UTF-8 cho command và header. Body có thể là text hoặc byte bất kỳ. Dấu NULL cuối frame là byte phân định giao thức, không mặc nhiên thuộc body.

Ví dụ một frame text:

~~~text
SEND
destination:/queue/orders
content-type:text/plain;charset=utf-8
content-length:8

Xin chào
^@
~~~

Trong ví dụ này, body được mã hóa UTF-8. Dòng ^@ chỉ biểu diễn octet NULL kết thúc frame; nó không phải hai ký tự dấu mũ và @ được gửi đi.

## 3. content-type: mô tả MIME type của body

content-type là header tùy chọn nhưng nên có khi frame mang body. Giá trị của nó phải là MIME type mô tả định dạng body.

Một số giá trị thường dùng:

| content-type | Nội dung | Cách xử lý điển hình |
| --- | --- | --- |
| text/plain;charset=utf-8 | Văn bản UTF-8 | Giải mã thành String |
| application/json | JSON | Parse thành DTO hoặc cấu trúc JSON |
| application/xml;charset=utf-8 | XML UTF-8 | Parse XML |
| application/octet-stream | Byte tổng quát | Giữ payload dưới dạng byte[] |
| image/png | Ảnh PNG | Giữ byte[] hoặc chuyển cho bộ xử lý ảnh |
| application/pdf | Tệp PDF | Giữ byte[] hoặc chuyển cho bộ xử lý PDF |

Nếu MIME type bắt đầu bằng text/, STOMP 1.2 mặc định ngầm định UTF-8. Nếu dùng encoding văn bản khác, hãy khai báo charset, ví dụ text/plain;charset=utf-16.

Một số MIME type không bắt đầu bằng text/ nhưng vẫn chứa dữ liệu văn bản, như application/xml. Khi cần encoding rõ ràng, hãy khai báo charset tương ứng, chẳng hạn application/xml;charset=utf-8.

Nếu body có content-type, receiver dùng MIME type đó để hiểu nội dung. Nếu body không có content-type, theo STOMP 1.2 receiver nên xem body như một binary blob. Vì vậy, đừng dựa vào suy đoán rằng body không có header chắc chắn là UTF-8 text.

### 3.1. content-type không xác thực nội dung

Header content-type chỉ là metadata do sender cung cấp. Nó không chứng minh body thực sự đúng định dạng đã khai báo.

Ví dụ client có thể gửi content-type:image/png nhưng body lại chứa một tệp khác. Server cần kiểm tra kích thước, chữ ký định dạng (magic bytes), cấu trúc và quy tắc nghiệp vụ trước khi lưu hoặc xử lý dữ liệu.

Không dùng MIME type làm ranh giới bảo mật và không tự động tin tên tệp do client gửi.

## 4. content-length: độ dài tính theo octet

content-length là số lượng octet trong body. Một octet tương ứng một byte 8 bit. Giá trị này không tính:

- Command và các header.
- Dòng trống phân cách header với body.
- Octet NULL kết thúc frame.
- Các byte thuộc frame tiếp theo.

Ví dụ:

~~~text
SEND
destination:/queue/binary
content-type:application/octet-stream
content-length:4

[0x41 0x00 0xFF 0x42]
[frame terminator: 0x00]
~~~

Body có đúng bốn byte: 0x41, 0x00, 0xFF và 0x42. Octet NULL cuối frame là byte thứ năm sau body, không được tính vào content-length.

Nếu content-length có mặt, receiver phải đọc chính xác số octet đã khai báo, bất kể body có chứa byte NULL hay không. Sau số byte đó, frame vẫn phải có octet NULL kết thúc.

### 4.1. Khi nào content-length là bắt buộc?

Theo STOMP 1.2:

- SEND, MESSAGE và ERROR nên có content-length khi body tồn tại để việc parse frame dễ dàng hơn.
- Nếu body chứa bất kỳ octet NULL nào, frame bắt buộc phải có content-length.
- Nếu content-length được khai báo, decoder phải đọc đúng số octet đó rồi mới kiểm tra byte NULL kết thúc frame.

Do đó, với dữ liệu nhị phân tùy ý, hãy luôn gửi content-length. Dữ liệu nhị phân có thể chứa 0x00 ở bất kỳ vị trí nào; nếu không có độ dài, decoder có thể hiểu nhầm byte đó là dấu kết thúc body và cắt mất phần còn lại.

## 5. Phân biệt số ký tự và số byte

Đây là lỗi thường gặp khi gửi văn bản có dấu hoặc ký tự ngoài ASCII.

Trong Java:

- String.length() đếm UTF-16 code unit.
- codePointCount() đếm Unicode code point.
- content-length cần số byte thực tế sau khi encode body.

Ví dụ chuỗi Xin chào có 8 UTF-16 code unit nhưng cần 9 byte khi mã hóa UTF-8 vì ký tự à chiếm hai byte.

~~~java
String body = "Xin chào";
byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

System.out.println("textChars=" + body.length());
System.out.println("utf8Bytes=" + bytes.length);
~~~

Stdout:

~~~text
textChars=8
utf8Bytes=9
~~~

Khi tự tạo STOMP frame, hãy tính độ dài từ byte array đã encode:

~~~java
byte[] body = text.getBytes(StandardCharsets.UTF_8);
int contentLength = body.length;
~~~

Không dùng text.length() để điền content-length. Với ảnh, PDF, protobuf hoặc dữ liệu nén, hãy lấy độ dài trực tiếp từ byte array.

## 6. Cách decoder phân định body

Có hai trường hợp:

### 6.1. Frame có content-length

Giả sử header ghi content-length:4. Decoder đọc đúng bốn octet body. Nếu byte thứ hai là 0x00, decoder vẫn giữ nó trong body vì độ dài đã xác định vị trí kết thúc.

Sau bốn byte, decoder yêu cầu octet NULL kết thúc frame. Nếu byte kết thúc không có hoặc frame bị cắt giữa chừng, frame chưa hoàn chỉnh và decoder cần thêm dữ liệu.

### 6.2. Frame không có content-length

Nếu không có content-length, decoder tìm octet NULL đầu tiên sau phần body để xác định điểm kết thúc.

Cách này phù hợp với body text không chứa NULL. Nó không an toàn cho dữ liệu nhị phân tùy ý vì byte 0x00 có thể là một phần dữ liệu.

### 6.3. Hậu quả khi khai báo sai độ dài

| Lỗi | Hậu quả có thể xảy ra |
| --- | --- |
| content-length nhỏ hơn body thật | Phần byte dư có thể bị hiểu nhầm là frame tiếp theo hoặc gây lỗi parse |
| content-length lớn hơn body thật | Decoder tiếp tục chờ byte còn thiếu; frame bị treo hoặc timeout |
| Bỏ content-length khi body có 0x00 | Body bị cắt tại byte NULL đầu tiên |
| Tính theo số ký tự thay vì số byte | Unicode text bị đọc thiếu hoặc thừa byte |
| Tính cả byte NULL kết thúc frame | Decoder chờ thêm một byte terminator và không hoàn tất frame |

Không nên sửa lỗi bằng cách cắt payload hoặc bỏ byte NULL. Hãy sửa phép tính byte length và cách đóng frame ở sender.

## 7. Dữ liệu nhị phân trong STOMP

STOMP 1.2 cho phép body là chuỗi octet bất kỳ. Điều này giúp giao thức có thể mang:

- Ảnh, âm thanh và video.
- PDF, ZIP và các tệp đính kèm.
- Dữ liệu protobuf hoặc định dạng nhị phân tùy chỉnh.
- Các block dữ liệu nén hoặc mã hóa.
- Payload chứa byte NULL và các giá trị không hợp lệ nếu diễn giải như UTF-8.

Ví dụ body bốn byte:

~~~text
0x41 0x00 0xFF 0x42
~~~

Không thể biểu diễn chính xác toàn bộ body này bằng một String UTF-8 thông thường mà không có quy tắc encode/decode bổ sung. Hãy giữ nguyên byte[] ở tầng transport và chỉ chuyển đổi khi biết chính xác định dạng.

### 7.1. Không chuyển binary thành Base64 nếu không cần

Có thể mã hóa binary thành Base64 rồi gửi như text/plain hoặc application/json. Cách đó hữu ích khi hệ thống trung gian chỉ hỗ trợ text, nhưng kích thước dữ liệu tăng khoảng một phần ba và cần thêm bước encode/decode.

Nếu client, broker và server đều hỗ trợ binary body, gửi byte[] trực tiếp với application/octet-stream và content-length sẽ hiệu quả hơn.

### 7.2. Không nhầm WebSocket binary frame với STOMP body

WebSocket có text frame và binary frame. STOMP là sub-protocol được đóng gói bên trong WebSocket message. Một STOMP frame vẫn có command và header; body của nó có thể là byte nhị phân.

Ở tầng Spring, StompSubProtocolHandler có thể nhận WebSocket TextMessage hoặc BinaryMessage rồi chuyển dữ liệu sang decoder STOMP. Vì vậy, ứng dụng không nên tự loại bỏ STOMP header chỉ vì transport dùng binary WebSocket frame.

## 8. Ví dụ Java 17+ tạo STOMP frame có byte NULL

Ví dụ sau dùng Java chuẩn để tạo một SEND frame chứa bốn byte nhị phân. Đây là chương trình độc lập minh họa cách đóng gói frame; nó không mở socket hoặc gửi dữ liệu tới broker.

**StompBinaryFrameDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class StompBinaryFrameDemo {

    public static void main(String[] args) {
        String text = "Xin chào";
        byte[] textBytes = text.getBytes(StandardCharsets.UTF_8);

        byte[] payload = {
            (byte) 0x41,
            (byte) 0x00,
            (byte) 0xFF,
            (byte) 0x42
        };

        String headers =
            "SEND\n" +
            "destination:/queue/binary\n" +
            "content-type:application/octet-stream\n" +
            "content-length:" + payload.length + "\n" +
            "\n";

        ByteArrayOutputStream frame = new ByteArrayOutputStream();
        frame.writeBytes(headers.getBytes(StandardCharsets.UTF_8));
        frame.writeBytes(payload);
        frame.write(0);

        System.out.println("textChars=" + text.length());
        System.out.println("textUtf8Bytes=" + textBytes.length);
        System.out.println("payloadBytes=" + payload.length);
        System.out.println("frameBytes=" + frame.size());
        System.out.println("bodyContainsNul=" + (payload[1] == 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StompBinaryFrameDemo.java
java StompBinaryFrameDemo
~~~

Stdout:

~~~text
textChars=8
textUtf8Bytes=9
payloadBytes=4
frameBytes=92
bodyContainsNul=true
~~~

Trong frame được tạo:

- Header block chiếm 87 byte.
- Body chiếm 4 byte.
- Byte NULL cuối frame chiếm 1 byte.
- Tổng frame là 92 byte.
- content-length chỉ ghi 4, không ghi 5 hoặc 92.

Ví dụ này cho thấy content-length chỉ tính body. Header block và frame terminator nằm ngoài phép tính.

## 9. Đọc content-type và content-length trong Spring

Spring Framework cung cấp StompHeaderAccessor để đọc và ghi STOMP header theo kiểu an toàn hơn so với truy cập Map trực tiếp.

Một số API:

| API | Mục đích |
| --- | --- |
| getContentType() | Đọc MIME type từ header content-type |
| setContentType(MimeType) | Ghi content-type |
| getContentLength() | Đọc content-length, trả về Integer hoặc null nếu không có |
| setContentLength(int) | Ghi content-length |
| getFirstNativeHeader(name) | Đọc giá trị đầu tiên của một native STOMP header |
| setNativeHeader(name, value) | Ghi một native STOMP header |

Ví dụ đọc metadata từ Spring Message:

~~~java
Message<byte[]> message = ...;

StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

MimeType contentType = accessor.getContentType();
Integer contentLength = accessor.getContentLength();

byte[] body = message.getPayload();
~~~

StompHeaderAccessor giữ thông tin native header của STOMP frame và đồng thời ánh xạ content-type vào Spring MessageHeaders.CONTENT_TYPE.

Nếu content-length không có, getContentLength() trả về null. Không tự suy đoán độ dài từ content-type; hãy dùng body.length để biết kích thước byte array đã được decoder tạo ra.

## 10. Spring StompDecoder và payload byte[]

StompDecoder nhận dữ liệu dưới dạng ByteBuffer và giải mã thành danh sách Spring Message có payload kiểu byte[].

Điều này quan trọng vì decoder cần giữ nguyên dữ liệu body trước khi tầng nghiệp vụ quyết định có chuyển đổi hay không.

Quy trình tổng quát:

1. WebSocket transport nhận text hoặc binary frame.
2. StompSubProtocolHandler chuyển dữ liệu sang ByteBuffer.
3. BufferingStompDecoder tích lũy dữ liệu nếu frame chưa đầy đủ.
4. StompDecoder đọc command, headers, content-length và body.
5. Decoder tạo Message<byte[]> cùng native STOMP headers.
6. Spring định tuyến message tới controller hoặc broker.
7. Nếu controller yêu cầu một kiểu payload khác, MessageConverter thực hiện chuyển đổi dựa trên content-type và kiểu đích.

Nếu frame bị chia qua nhiều lần nhận, decoder có thể trả về danh sách rỗng cho đến khi nhận đủ dữ liệu. BufferingStompDecoder sử dụng content-length khi có để xác định lượng dữ liệu còn thiếu và hỗ trợ giới hạn kích thước buffer.

## 11. MessageConverter và content-type trong Spring

Spring MessageConverter chuyển payload từ dạng byte đã serialize sang kiểu Java mà listener hoặc controller yêu cầu, và ngược lại.

Một số converter thường dùng:

| Converter | Kiểu payload | MIME type thường dùng |
| --- | --- | --- |
| ByteArrayMessageConverter | byte[] | application/octet-stream |
| StringMessageConverter | String | text/plain |
| Jackson JSON converter | DTO/JSON object | application/json |
| Converter tùy chỉnh | Kiểu nghiệp vụ hoặc binary riêng | MIME type do ứng dụng định nghĩa |

Converter cần hỗ trợ cả content-type và kiểu đích. Nếu không có converter phù hợp, Spring có thể ném MessageConversionException hoặc lỗi xử lý message.

Không nên yêu cầu Spring chuyển application/octet-stream thành String. Với binary, dùng byte[] hoặc Message<byte[]> để giữ nguyên dữ liệu.

## 12. Nhận binary trong @MessageMapping

Một controller có thể nhận toàn bộ Spring Message<byte[]> để tự kiểm tra header và body:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Controller
public class BinaryUploadController {

    private final BinaryStorage binaryStorage;

    public BinaryUploadController(BinaryStorage binaryStorage) {
        this.binaryStorage = binaryStorage;
    }

    @MessageMapping("/binary.upload")
    public void upload(Message<byte[]> message) {
        StompHeaderAccessor headers = StompHeaderAccessor.wrap(message);

        MimeType contentType = headers.getContentType();
        Integer declaredLength = headers.getContentLength();
        byte[] body = message.getPayload();

        if (!MimeTypeUtils.APPLICATION_OCTET_STREAM.equals(contentType)) {
            throw new IllegalArgumentException("Expected application/octet-stream");
        }

        if (declaredLength != null && declaredLength.intValue() != body.length) {
            throw new IllegalArgumentException("Unexpected binary payload length");
        }

        binaryStorage.store(body);
    }
}
~~~

BinaryStorage là service do ứng dụng cung cấp để kiểm tra và lưu dữ liệu. Ví dụ này giả định service đó đã được đăng ký thành Spring bean.

Client gửi tới destination /app/binary.upload. Spring bỏ prefix /app khi ánh xạ destination đến method @MessageMapping("/binary.upload").

Khi dùng Message<byte[]>, controller truy cập trực tiếp payload byte[] và native STOMP headers. Không có bước chuyển payload thành String hoặc DTO.

Nếu dùng tham số @Payload byte[] thay vì Message<byte[]>, hãy bảo đảm ByteArrayMessageConverter được đăng ký và content-type tương thích với application/octet-stream.

## 13. Gửi binary bằng Spring STOMP client

Spring cung cấp StompSession để gửi và nhận STOMP message. Có thể thiết lập destination và content-type rồi gửi byte[]:

~~~java
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.util.MimeTypeUtils;

public void sendBinary(StompSession session, byte[] payload) {
    StompHeaders headers = new StompHeaders();
    headers.setDestination("/app/binary.upload");
    headers.setContentType(MimeTypeUtils.APPLICATION_OCTET_STREAM);

    session.send(headers, payload);
}
~~~

StompSession dùng MessageConverter để chuyển payload thành byte[] trước khi encoder tạo frame. Với payload byte[], SimpleMessageConverter có thể giữ nguyên mảng byte; có thể cấu hình converter khác nếu ứng dụng cần quy tắc riêng.

Spring StompEncoder chịu trách nhiệm mã hóa Spring Message thành STOMP frame. Khi tự xây dựng frame bằng byte array, ứng dụng phải tự tính content-length chính xác. Khi dùng client encoder của Spring, hãy để encoder tạo framing từ payload đã chuyển đổi và tránh tự tính độ dài theo String.length().

## 14. Gửi JSON và text đúng content-type

Với JSON:

~~~text
SEND
destination:/app/orders.create
content-type:application/json
content-length:34

{"orderId":"A-100","priority":5}
^@
~~~

Body JSON phải được encode theo charset mà hai phía thống nhất, thường là UTF-8. content-length phải bằng số byte sau khi encode JSON, không phải số ký tự trong chuỗi JSON.

Với text:

~~~text
SEND
destination:/app/chat.send
content-type:text/plain;charset=utf-8
content-length:9

Xin chào
^@
~~~

Trong ví dụ text, chuỗi có 8 UTF-16 code unit nhưng 9 byte UTF-8. Nếu bỏ content-length, frame vẫn có thể được phân định bằng NULL vì body không chứa NULL, nhưng STOMP 1.2 khuyến nghị có content-length khi body tồn tại.

## 15. Giới hạn kích thước và xử lý dữ liệu lớn

Binary body có thể rất lớn. STOMP cho phép server áp dụng giới hạn số header, độ dài dòng header và kích thước body để bảo vệ bộ nhớ và tránh tấn công từ client.

Spring cũng có giới hạn buffer cho STOMP frame. BufferingStompDecoder có thể từ chối frame khi content-length vượt giới hạn cấu hình hoặc tổng buffer vượt quá giới hạn.

Khi thiết kế upload:

- Đặt giới hạn kích thước ở cả proxy, WebSocket transport, STOMP decoder và tầng nghiệp vụ.
- Không chỉ tin content-length do client khai báo.
- Kiểm tra body.length sau khi decoder tạo byte[].
- Tránh giữ nhiều bản sao của cùng payload trong bộ nhớ.
- Với tệp lớn, cân nhắc upload qua HTTP/object storage rồi gửi STOMP notification chứa metadata hoặc URL đã được phân quyền.
- Nếu phải truyền chunk qua STOMP, thiết kế chunk ID, sequence, checksum, timeout, retry và cơ chế ghép chunk rõ ràng.
- Giới hạn số upload đồng thời trên mỗi user/session.

content-length giúp phân định frame; nó không phải giới hạn dung lượng tự động và cũng không ngăn client gửi dữ liệu quá lớn.

## 16. Bảo mật khi nhận binary payload

Không coi content-type hoặc tên tệp là bằng chứng an toàn.

- Xác thực người gửi và kiểm tra quyền truy cập destination.
- Kiểm tra MIME type thực tế và magic bytes của file.
- Giới hạn kích thước body, số message và tốc độ gửi.
- Không lưu file trực tiếp bằng tên đường dẫn do client cung cấp.
- Quét malware hoặc kiểm tra nội dung theo chính sách nghiệp vụ.
- Không ghi toàn bộ binary body vào log.
- Không deserialize Java object hoặc dữ liệu tùy chỉnh từ client nếu chưa xác thực và giới hạn schema.
- Dùng TLS/WSS trên môi trường production.
- Kiểm tra content-type và payload type có tương thích trước khi chuyển đổi.

Một client độc hại có thể gửi content-type:application/json nhưng body không phải JSON, hoặc khai báo image/png cho nội dung không phải ảnh. Server phải xử lý lỗi parse an toàn và không làm lộ stack trace.

## 17. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Binary payload bị cắt tại byte 0x00 | Thiếu content-length | Gửi content-length bằng số byte body |
| Frame không hoàn tất | content-length lớn hơn số byte thực gửi hoặc thiếu byte NULL cuối | Tính lại byte length và thêm terminator riêng |
| Decoder hiểu nhầm frame tiếp theo là body | content-length quá lớn | Kiểm tra payload length và giới hạn frame |
| Unicode text bị lỗi hoặc cắt | Dùng String.length() thay cho UTF-8 byte length | Encode trước rồi lấy byte[].length |
| Controller nhận String thay vì byte[] | Converter hoặc content-type chọn sai | Dùng application/octet-stream và ByteArrayMessageConverter |
| Không có converter phù hợp | MIME type không được converter hỗ trợ | Đăng ký MessageConverter phù hợp hoặc nhận Message<byte[]> |
| JSON parse thất bại | content-type không phải application/json hoặc body không phải JSON hợp lệ | Kiểm tra MIME type, charset và schema |
| Spring từ chối frame lớn | Vượt buffer/message size limit | Điều chỉnh giới hạn có kiểm soát hoặc chuyển upload sang HTTP/object storage |
| Client và server tính độ dài khác nhau | Một bên đếm ký tự, bên kia đếm byte | Thống nhất encoding và tính theo octet |
| Header content-type bị bỏ qua | Header sai tên, sai MIME type hoặc custom converter không đọc header | Dùng đúng tên lowercase và kiểm tra native headers |
| Body binary bị chuyển thành text | Ứng dụng gọi String constructor trên byte[] | Giữ byte[] cho tới khi biết encoding |
| Frame chứa byte NULL nhưng không có content-length | Vi phạm quy tắc phân định STOMP 1.2 | Luôn gửi content-length với body chứa 0x00 |

## 18. Checklist thiết kế và kiểm thử

- [ ] Chọn MIME type chính xác cho từng loại body.
- [ ] Dùng charset UTF-8 rõ ràng cho text khi cần interoperability.
- [ ] Tính content-length từ byte array sau khi encode.
- [ ] Không tính header, dòng trống hoặc byte NULL cuối frame vào content-length.
- [ ] Luôn có content-length nếu body chứa byte 0x00.
- [ ] Giữ byte[] cho payload binary và chỉ chuyển đổi theo converter phù hợp.
- [ ] Kiểm tra StompHeaderAccessor.getContentType() và getContentLength().
- [ ] Xác nhận MessageConverter hỗ trợ MIME type và kiểu payload đích.
- [ ] Kiểm thử Unicode có dấu, emoji, byte 0x00, byte 0xFF và body rỗng.
- [ ] Kiểm thử frame bị chia thành nhiều lần nhận và frame bị cắt giữa chừng.
- [ ] Kiểm thử content-length nhỏ hơn, lớn hơn và vượt giới hạn.
- [ ] Giới hạn kích thước, tốc độ gửi, số session và số upload đồng thời.
- [ ] Xác thực nội dung file độc lập với content-type do client khai báo.

## 19. Tài liệu tham khảo

- [STOMP Protocol Specification 1.2 — Frames and Headers](https://stomp.github.io/stomp-specification-1.2.html#Frames_and_Headers)
- [STOMP Protocol Specification 1.2 — SEND Frame](https://stomp.github.io/stomp-specification-1.2.html#SEND)
- [Spring Framework 7.0.10 — STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [Spring Framework 7.0.10 — Flow of Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0.10 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-annotations.html)
- [Spring Framework API — StompDecoder](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)
- [Spring Framework API — StompEncoder](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompEncoder.html)
- [Spring Framework API — StompHeaderAccessor](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework API — ByteArrayMessageConverter](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/converter/ByteArrayMessageConverter.html)
- [Spring Framework API — MessageConverter](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
