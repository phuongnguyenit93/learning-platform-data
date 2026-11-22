# Kiểu nội dung, MIME type và charset

Khi gửi message giữa các thành phần, hai bên cần thống nhất không chỉ dữ liệu có những field nào mà còn phải biết payload được biểu diễn theo định dạng nào và các byte được giải mã ra ký tự bằng charset nào. Một JSON, chuỗi văn bản và byte array có thể cùng mang thông tin nghiệp vụ, nhưng consumer phải xử lý chúng theo cách khác nhau.

**MIME type** mô tả loại nội dung và định dạng biểu diễn. **Content-Type** là metadata cho biết payload hiện tại dùng MIME type nào. **Charset** chỉ định bảng mã ký tự dùng để chuyển đổi giữa văn bản và byte. Trong Spring Messaging, content type có thể được đặt trong Message headers dưới dạng MimeType để message converter lựa chọn cách chuyển đổi phù hợp.

Nếu producer ghi sai content type hoặc hai bên dùng charset khác nhau, consumer có thể chọn nhầm converter, parse thất bại hoặc hiển thị văn bản sai dấu. Vì vậy, content type và charset là một phần của hợp đồng message và cần được thiết kế, kiểm thử như payload schema.

## 1. MIME type và cấu trúc media type

MIME (Multipurpose Internet Mail Extensions) ban đầu được dùng để mô tả nội dung trong email. Trong các giao thức và framework hiện đại, media type theo cú pháp MIME được dùng rộng rãi để mô tả định dạng dữ liệu.

Một media type có cấu trúc tổng quát:

~~~text
type/subtype; parameter=value
~~~

Trong đó:

- **type:** nhóm nội dung cấp cao, ví dụ text, image, audio, video hoặc application.
- **subtype:** định dạng cụ thể trong nhóm đó, ví dụ plain, html, json, xml hoặc octet-stream.
- **parameter:** thông tin bổ sung cho cách biểu diễn, ví dụ charset, boundary hoặc profile.

Một số ví dụ:

| Media type | Ý nghĩa |
|---|---|
| text/plain | Văn bản thuần |
| text/html | Tài liệu HTML |
| application/json | Dữ liệu JSON |
| application/problem+json | JSON theo cấu trúc problem details |
| application/xml | Dữ liệu XML |
| application/octet-stream | Dữ liệu nhị phân không chỉ rõ định dạng cụ thể |
| image/png | Ảnh PNG |
| application/vnd.acme.order.v1+json | JSON theo media type riêng, có tên miền nghiệp vụ và phiên bản |

Media type không phải tên file. Một file có đuôi .json thường có thể được gửi với application/json, nhưng consumer nên dựa vào content type và hợp đồng giao tiếp thay vì chỉ suy luận từ tên file.

Tên type và subtype không phân biệt chữ hoa/chữ thường theo quy tắc media type. Dù vậy, nên dùng chữ thường để thống nhất. Các parameter có quy tắc riêng; tên charset và các alias charset cũng được chuẩn hóa theo cơ chế của nền tảng.

### 1.1. Wildcard và structured syntax suffix

Trong một số cơ chế lựa chọn định dạng, có thể gặp wildcard:

- application/*: chấp nhận hoặc mô tả một subtype bất kỳ thuộc application.
- */*: chấp nhận mọi media type trong ngữ cảnh thương lượng nội dung.

Wildcard thường hữu ích trong header thương lượng như Accept. Với một message đã được tạo và gửi, content type nên chỉ rõ định dạng thực tế của payload, chẳng hạn application/json, thay vì dùng wildcard.

Một số media type dùng structured syntax suffix như +json hoặc +xml. Ví dụ application/vnd.acme.order.v1+json cho biết đây là media type riêng nhưng payload có cấu trúc JSON. Converter có hỗ trợ application/*+json có thể xử lý các loại JSON có suffix này, tùy cấu hình và phiên bản thư viện.

## 2. Content-Type khác MIME type như thế nào?

MIME type là tên media type mô tả định dạng nội dung. Content-Type là tên header hoặc metadata field mang giá trị media type đó.

Trong HTTP, header thường được viết:

~~~http
Content-Type: application/json
~~~

Với văn bản có charset rõ ràng:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

Trong Spring Messaging, header tương ứng dùng key **MessageHeaders.CONTENT_TYPE** và thường mang một đối tượng **MimeType**. Khi message được gửi qua adapter tới broker hoặc transport khác, adapter có thể ánh xạ header này sang metadata tương ứng của giao thức. Cách ánh xạ phụ thuộc integration.

Content-Type mô tả định dạng của payload hiện tại. Nó không tự mô tả toàn bộ message envelope, không xác định routing destination và không đảm bảo message được lưu bền vững.

Cần phân biệt thêm:

- **Content-Type:** định dạng nội dung, ví dụ application/json.
- **Content-Encoding:** cách nội dung được mã hóa hoặc nén ở tầng vận chuyển, ví dụ gzip trong HTTP.
- **Charset:** cách chuyển byte thành ký tự cho nội dung dạng văn bản.
- **Accept:** trong HTTP, client nêu các định dạng response mà nó có thể nhận. Đây không phải header bắt buộc hoặc semantics chung cho mọi message broker.

Nén gzip và charset là hai vấn đề khác nhau. Một payload có thể là JSON UTF-8 và đồng thời được nén gzip; khi giải mã phải xử lý content encoding và charset theo đúng thứ tự.

## 3. Charset là gì?

Charset xác định tập ký tự và cách mã hóa chúng thành byte. Trong Java, String biểu diễn văn bản bằng các code unit UTF-16; khi gửi qua mạng hoặc lưu vào file, ứng dụng thường phải encode String thành byte theo một charset cụ thể.

Một số charset thường gặp:

- **UTF-8:** mã hóa Unicode có độ dài biến thiên từ 1 đến 4 byte cho mỗi code point. Đây là lựa chọn phổ biến cho giao tiếp web và message hiện đại.
- **UTF-16:** mã hóa Unicode bằng một hoặc hai code unit 16-bit cho mỗi code point, tùy ký tự.
- **ISO-8859-1:** bộ ký tự một byte thường gặp trong hệ thống cũ; không thể biểu diễn toàn bộ Unicode.
- **Windows-1252:** bộ mã một byte thường gặp trong các tài liệu và hệ thống Windows cũ; khác ISO-8859-1 ở một số vị trí.

Khi encode và decode, hai bên cần dùng charset tương thích. Ví dụ, producer encode chuỗi tiếng Việt bằng UTF-8 nhưng consumer decode các byte đó bằng ISO-8859-1 sẽ tạo ra ký tự sai (mojibake). Byte vẫn được truyền đầy đủ; lỗi nằm ở cách diễn giải byte thành văn bản.

### 3.1. Luôn chỉ rõ charset khi làm việc với byte

Trong Java, tránh dùng các overload phụ thuộc charset mặc định của máy:

~~~java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
~~~

Nên chỉ định charset tường minh:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Không dựa vào Charset.defaultCharset() để quyết định hợp đồng giữa hai hệ thống. Cấu hình máy chạy, môi trường triển khai hoặc phiên bản runtime có thể khác nhau; hợp đồng message phải xác định cách mã hóa một cách rõ ràng.

### 3.2. Khi nào charset có ý nghĩa?

Charset có ý nghĩa khi payload là dữ liệu văn bản được biểu diễn dưới dạng byte, ví dụ text/plain hoặc JSON được serialize thành byte array.

Với payload nhị phân như ảnh PNG, PDF hoặc dữ liệu protobuf ở dạng binary, charset không có ý nghĩa. Không được cố chuyển byte nhị phân thành String theo UTF-8 chỉ để tiện truyền.

Nếu payload trong Java đang là String, các ký tự đã được giải mã trong bộ nhớ. Tuy nhiên, khi serializer chuyển String thành byte để gửi qua transport, encoding vẫn cần được xác định theo hợp đồng và converter.

## 4. Quy tắc UTF-8 đối với JSON

JSON là định dạng văn bản. Theo quy tắc trao đổi JSON hiện đại, nội dung JSON được truyền giữa các hệ thống cần được mã hóa bằng UTF-8. Media type chuẩn là application/json; parameter charset thường không cần thiết cho JSON.

Ví dụ content type phổ biến:

~~~http
Content-Type: application/json
~~~

Không nên tự giả định rằng mọi converter đều xử lý mọi charset parameter giống nhau. Một số thư viện có thể chấp nhận parameter charset, nhưng producer và consumer vẫn nên thống nhất UTF-8 cho JSON và kiểm thử bằng payload byte thực tế.

JSON text không nên được gửi với byte order mark (BOM). Nếu consumer nhận dữ liệu có BOM hoặc encoding không đúng quy ước, parser có thể từ chối hoặc xử lý khác nhau tùy thư viện.

Với text/plain, việc khai báo charset rõ ràng thường hữu ích:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

Với XML, charset có thể được thể hiện trong HTTP/message metadata và trong XML declaration. Nếu hai nơi khai báo khác nhau, cần tuân theo quy tắc của giao thức và parser đang dùng; tốt nhất là tránh mâu thuẫn.

## 5. Content type trong Spring Messaging

Spring Messaging cung cấp các kiểu dữ liệu để tạo message và gắn metadata:

- **Message<T>:** payload có kiểu T và headers.
- **MessageHeaders:** tập hợp metadata của message.
- **MessageHeaders.CONTENT_TYPE:** key header dành cho content type.
- **MimeType:** biểu diễn media type và các parameter.
- **MimeTypeUtils:** tiện ích tạo, parse và cung cấp một số MIME type phổ biến.
- **MessageBuilder:** hỗ trợ tạo message và thêm headers.

Ví dụ tạo message JSON:

~~~java
String json = "{\"orderId\":\"ORD-42\",\"quantity\":3}";

Message<String> message = MessageBuilder
        .withPayload(json)
        .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        )
        .build();
~~~

Trong ví dụ, payload là String chứa JSON và header mô tả định dạng là application/json. Nếu payload đã là byte array, hãy encode nó theo UTF-8 trước khi tạo message.

Ví dụ tạo media type text/plain với charset:

~~~java
MimeType textUtf8 = MimeTypeUtils.parseMimeType(
        "text/plain;charset=UTF-8"
);

byte[] body = "Đơn hàng ORD-42 đã tạo"
        .getBytes(StandardCharsets.UTF_8);

Message<byte[]> message = MessageBuilder
        .withPayload(body)
        .setHeader(MessageHeaders.CONTENT_TYPE, textUtf8)
        .build();
~~~

Khi đọc message, ứng dụng có thể lấy MimeType từ headers:

~~~java
MimeType contentType = message.getHeaders().get(
        MessageHeaders.CONTENT_TYPE,
        MimeType.class
);
~~~

Nếu content type có charset, có thể lấy bằng **contentType.getCharset()**. Nếu không có charset, ứng dụng cần áp dụng quy ước rõ ràng của contract. Không nên tự lấy charset mặc định của máy.

## 6. MessageConverter sử dụng content type như thế nào?

MessageConverter chuyển đổi giữa Spring Message và object. Một converter có thể xét payload class, content type, MIME type được hỗ trợ và conversion hint để quyết định cách chuyển đổi.

Ví dụ, converter JSON có thể nhận message với content type application/json và tạo DTO:

~~~java
MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

Message<String> incoming = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\",\"quantity\":3}")
        .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        )
        .build();

OrderCreated event = (OrderCreated) converter.fromMessage(
        incoming,
        OrderCreated.class
);
~~~

Đoạn mã cần Spring Messaging, Jackson và DTO OrderCreated. Converter được cấu hình để chuyển JSON thành object. Nếu content type không được hỗ trợ hoặc JSON không khớp target class, conversion có thể thất bại.

Khi gửi object, converter có thể tạo message chứa payload đã serialize và header content type phù hợp:

~~~java
OrderCreated event = new OrderCreated("ORD-42", 3);

Message<?> outgoing = converter.toMessage(
        event,
        new MessageHeaders(Map.of(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
        ))
);
~~~

Trong một số luồng, adapter hoặc transport có thể tự chọn converter theo cấu hình riêng. Đừng giả định chỉ cần đặt MessageHeaders.CONTENT_TYPE là mọi broker đều tự hiểu hoặc tự ánh xạ metadata giống nhau. Hãy kiểm tra adapter và transport cụ thể.

## 7. Kiểm tra và chuẩn hóa content type

Khi nhận message từ nguồn ngoài, cần xác thực content type trước khi parse:

1. Kiểm tra header có tồn tại không.
2. Parse media type bằng parser phù hợp, tránh so sánh chuỗi thủ công quá đơn giản.
3. Xác định subtype có nằm trong danh sách được hỗ trợ không.
4. Kiểm tra charset nếu payload là văn bản byte.
5. Xác định payload thực tế có phù hợp content type không.
6. Từ chối hoặc đưa message vào error channel/DLQ nếu định dạng không hợp lệ theo chính sách.

Ví dụ, không nên nhận mọi application/* rồi cố deserialize tất cả thành cùng một DTO. Một application/octet-stream có thể là dữ liệu nhị phân; application/xml cần parser XML; application/json cần parser JSON.

Một số lưu ý:

- Media type không hợp lệ nên được xem là lỗi đầu vào.
- Content type thiếu có thể được xử lý theo default đã quy định trong contract, nhưng không nên âm thầm đoán định dạng.
- Với charset không hỗ trợ hoặc không được phép, cần từ chối hoặc áp dụng quy tắc fallback đã công bố.
- Tránh tin cậy content type do client cung cấp như một bảo đảm rằng payload an toàn; vẫn phải validate nội dung và giới hạn kích thước.
- Khi hỗ trợ vendor media type, hãy ghi rõ phiên bản và cách tương thích.

## 8. Các lỗi thường gặp

### 8.1. Khai báo sai MIME type

Producer gửi JSON nhưng đặt content type text/plain. Consumer có thể nhận String thay vì DTO hoặc chọn converter không phù hợp.

Cách khắc phục: thống nhất media type trong contract, kiểm tra header ở producer và consumer, viết test với message thực tế.

### 8.2. Mismatch charset

Producer encode UTF-8 nhưng consumer decode ISO-8859-1 hoặc charset khác. Văn bản tiếng Việt có thể hiển thị thành ký tự sai.

Cách khắc phục: dùng UTF-8 nhất quán, khai báo charset rõ với text payload và dùng StandardCharsets.UTF_8 trong Java.

### 8.3. Dùng charset mặc định của máy

Code dùng getBytes() hoặc new String(byte[]) có thể hoạt động trên máy phát triển nhưng lỗi ở môi trường khác.

Cách khắc phục: chỉ định charset tường minh và kiểm thử byte-level.

### 8.4. Gắn charset vào payload nhị phân

Một payload ảnh hoặc PDF không phải văn bản. Việc decode nó thành String có thể làm hỏng byte.

Cách khắc phục: giữ payload ở dạng byte[] và dùng media type phù hợp như image/png hoặc application/octet-stream.

### 8.5. Nhầm Content-Type với Content-Encoding

Content-Type mô tả định dạng dữ liệu; Content-Encoding mô tả phép biến đổi ở tầng truyền tải, thường là nén. Ghi gzip vào charset hoặc xem UTF-8 là kiểu MIME là sai khái niệm.

Cách khắc phục: tách riêng media type, charset và content encoding.

### 8.6. Dùng wildcard làm content type thực tế

application/* có thể hữu ích trong thương lượng nhưng không xác định payload đang là JSON, XML hay binary.

Cách khắc phục: producer gửi media type cụ thể; consumer có thể dùng wildcard trong quy tắc chấp nhận nếu transport hỗ trợ.

## 9. Ví dụ Java 17: encode và decode văn bản UTF-8

Ví dụ sau mô phỏng việc producer chuyển văn bản tiếng Việt thành byte UTF-8 và consumer giải mã bằng cùng charset. Đây là chương trình JDK thuần, không cần Spring dependency.

Tạo file **CharsetMessageDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetMessageDemo {

    public static void main(String[] args) {
        String original = "Đơn hàng ORD-42 đã tạo";

        byte[] payload = original.getBytes(StandardCharsets.UTF_8);

        String contentType = "text/plain; charset=UTF-8";

        String received = new String(
                payload,
                StandardCharsets.UTF_8
        );

        System.out.println("Content-Type: " + contentType);
        System.out.println("Encoded bytes: " + payload.length);
        System.out.println("Decoded text: " + received);
        System.out.println("Round trip: " + original.equals(received));
        System.out.println(
                "Same UTF-8 bytes: " +
                        Arrays.equals(
                                payload,
                                received.getBytes(StandardCharsets.UTF_8)
                        )
        );
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac CharsetMessageDemo.java
java CharsetMessageDemo
~~~

Kết quả:

~~~text
Content-Type: text/plain; charset=UTF-8
Encoded bytes: 29
Decoded text: Đơn hàng ORD-42 đã tạo
Round trip: true
Same UTF-8 bytes: true
~~~

Ví dụ cho thấy cùng một chuỗi được encode và decode bằng UTF-8 sẽ giữ nguyên nội dung và byte sau vòng chuyển đổi. Trong ứng dụng Spring, content type có thể được đặt trong MessageHeaders; converter hoặc adapter chịu trách nhiệm serialize payload theo cấu hình tương ứng.

## 10. Checklist thiết kế content type cho message

Trước khi phát hành message contract, hãy xác định:

- Media type cụ thể của payload là gì?
- Payload là text, JSON, XML hay binary?
- Nếu là byte văn bản, charset nào được dùng?
- JSON có được encode UTF-8 theo quy ước không?
- Header content type được biểu diễn và ánh xạ qua adapter như thế nào?
- Converter có hỗ trợ media type và target class không?
- Có vendor media type hoặc schema version cần công bố không?
- Consumer sẽ xử lý content type thiếu, sai hoặc không hỗ trợ ra sao?
- Có test với ký tự tiếng Việt, ký tự ngoài ASCII, byte thực tế và payload không hợp lệ chưa?

Content type và charset là một phần của hợp đồng truyền dữ liệu. MIME type cho biết payload thuộc định dạng nào; charset cho biết byte văn bản được diễn giải thành ký tự ra sao. Trong Spring Messaging, đặt content type đúng vào headers giúp converter lựa chọn cách xử lý phù hợp, còn việc encode/decode phải dùng charset thống nhất. Thiết kế rõ ba yếu tố này giúp message được đọc đúng giữa các hệ thống và tránh lỗi khó phát hiện như sai dấu tiếng Việt, chọn nhầm converter hoặc hỏng dữ liệu nhị phân.