# StringMessageConverter và ByteArrayMessageConverter trong Spring Messaging

## 1. Vì sao cần converter?

Spring Messaging biểu diễn dữ liệu bằng `Message<?>`. Một message có payload và headers; payload có thể là object Java, chuỗi, byte array hoặc kiểu khác. Khi message đi qua một adapter, giao thức hoặc ranh giới ứng dụng, hai bên cần thống nhất cách biểu diễn payload.

`MessageConverter` là abstraction chuyển đổi giữa object Java và message:

- `toMessage(payload, headers)` tạo message từ object cùng metadata.
- `fromMessage(message, targetClass)` đọc message và chuyển payload về kiểu Java mà caller yêu cầu.

Hai converter cơ bản thường gặp:

- **StringMessageConverter:** xử lý payload dạng `String`, phù hợp với nội dung văn bản.
- **ByteArrayMessageConverter:** xử lý payload dạng `byte[]`, phù hợp với dữ liệu nhị phân hoặc dữ liệu cần giữ nguyên byte.

Chúng giải quyết hai nhu cầu khác nhau. Chuỗi là văn bản cần được giải mã theo charset; byte array là dãy byte cần được giữ nguyên. Chọn sai converter có thể làm sai nội dung, mất byte hoặc khiến bước chuyển đổi không được hỗ trợ.

Sau bài học, bạn cần có thể:

- Phân biệt MessageConverter với Message, payload và headers.
- Chọn StringMessageConverter hoặc ByteArrayMessageConverter theo kiểu payload.
- Hiểu vai trò của MIME type, Content-Type và charset.
- Dùng converter để đọc payload từ message và tạo message từ object.
- Nhận diện trường hợp converter không hỗ trợ target type hoặc content type.
- Kiểm thử nội dung văn bản, Unicode và dữ liệu nhị phân.

## 2. MessageConverter và luồng chuyển đổi

Interface `MessageConverter` thuộc package `org.springframework.messaging.converter`. Hai thao tác cốt lõi là:

~~~java
Message<?> toMessage(Object payload, MessageHeaders headers);

<T> T fromMessage(Message<?> message, Class<T> targetClass);
~~~

Khi chuyển object thành message, converter có thể tạo hoặc bổ sung headers phù hợp. Khi chuyển message thành object, converter kiểm tra kiểu đích và metadata để quyết định có thể chuyển đổi hay không.

Một luồng inbound thường có dạng:

~~~text
Message từ channel / adapter
          |
          v
MessageConverter.fromMessage(...)
          |
          v
Object Java theo target type
          |
          v
Controller / handler / service
~~~

Luồng outbound đi theo chiều ngược lại:

~~~text
Object Java
    |
    v
MessageConverter.toMessage(...)
    |
    v
Message<?> = payload + headers
    |
    v
MessageChannel / adapter
~~~

Converter chỉ chịu trách nhiệm biểu diễn dữ liệu. Nó không xác thực nghiệp vụ, không kiểm tra quyền truy cập, không quyết định retry và không bảo đảm message đã được broker giao thành công.

## 3. StringMessageConverter: chuyển đổi văn bản

### 3.1 Phạm vi hỗ trợ

`StringMessageConverter` hỗ trợ payload kiểu `String`. MIME type mặc định của converter là `text/plain`. Khi đọc dữ liệu byte thành String, converter sử dụng charset trong Content-Type nếu có; charset mặc định là UTF-8.

Ví dụ, message có payload là byte array chứa văn bản UTF-8 và Content-Type là `text/plain;charset=UTF-8`. Converter có thể giải mã thành String để handler làm việc với văn bản.

Converter này phù hợp với:

- Nội dung text thuần.
- Dữ liệu văn bản UTF-8 hoặc charset được khai báo rõ.
- Giao thức hoặc adapter có payload là chuỗi.
- Tích hợp cần truyền chuỗi mà không cần ánh xạ thành DTO.

`StringMessageConverter` không phải JSON object mapper. Nếu payload chứa JSON và ứng dụng cần chuyển thành DTO, hãy dùng converter JSON phù hợp, chẳng hạn converter dựa trên Jackson. Đọc JSON thành String chỉ tạo ra một chuỗi; nó không phân tích JSON thành object nghiệp vụ.

### 3.2 Ví dụ giải mã byte thành String

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

import java.nio.charset.StandardCharsets;

public class StringConversionDemo {

    public static void main(String[] args) {
        byte[] payload = "Xin chào".getBytes(StandardCharsets.UTF_8);

        Message<byte[]> message = MessageBuilder
                .withPayload(payload)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.parseMimeType(
                                "text/plain;charset=UTF-8"))
                .build();

        String text = new StringMessageConverter()
                .fromMessage(message, String.class);

        System.out.println(text);
    }
}
~~~

Kết quả:

~~~text
Xin chào
~~~

Content-Type cung cấp cả loại nội dung và charset. Nếu byte được mã hóa theo UTF-8 nhưng bị giải mã bằng charset khác, ký tự có dấu hoặc ký tự ngoài ASCII có thể bị sai. Khi giao tiếp qua mạng, hai bên cần thống nhất encoding thay vì dựa vào charset mặc định ngầm định.

### 3.3 Payload String và payload byte[]

Cần phân biệt hai tình huống:

- Payload đã là String: ứng dụng đang làm việc với văn bản.
- Payload là byte[] chứa văn bản: ứng dụng cần giải mã byte theo charset để có String.

Không nên gọi một byte array bất kỳ là văn bản. Nếu payload chứa ảnh, file nén, dữ liệu mã hóa hoặc giao thức nhị phân, hãy giữ nó ở dạng byte array. Giải mã byte nhị phân như UTF-8 có thể tạo ký tự thay thế và làm mất khả năng khôi phục dữ liệu gốc.

## 4. ByteArrayMessageConverter: giữ nguyên dữ liệu nhị phân

### 4.1 Phạm vi hỗ trợ

`ByteArrayMessageConverter` hỗ trợ payload kiểu `byte[]` và MIME type mặc định là `application/octet-stream`. Converter này phù hợp khi ứng dụng cần giữ nguyên dãy byte, ví dụ:

- Nội dung file hoặc ảnh.
- Dữ liệu nhị phân từ thiết bị.
- Payload đã được nén hoặc mã hóa.
- Nội dung cần chuyển tiếp tới thành phần khác mà không giải mã thành text.

Converter không tự hiểu cấu trúc dữ liệu bên trong byte array. Nó không giải nén, giải mã encryption, parse protocol nhị phân hoặc chuyển byte thành DTO. Các bước đó thuộc logic codec hoặc serializer riêng của ứng dụng.

### 4.2 Ví dụ giữ nguyên byte

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.ByteArrayMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

import java.util.Arrays;

public class ByteArrayConversionDemo {

    public static void main(String[] args) {
        byte[] original = new byte[] {0, 1, 2, (byte) 255};

        Message<byte[]> message = MessageBuilder
                .withPayload(original)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_OCTET_STREAM)
                .build();

        byte[] decoded = new ByteArrayMessageConverter()
                .fromMessage(message, byte[].class);

        System.out.println(Arrays.equals(original, decoded));
    }
}
~~~

Kết quả:

~~~text
true
~~~

Kiểm tra bằng `Arrays.equals` để xác nhận toàn bộ byte được giữ nguyên. Không chuyển byte array sang String chỉ để log hoặc kiểm tra, vì cách đó có thể làm biến đổi cách biểu diễn dữ liệu.

## 5. So sánh hai converter

| Tiêu chí | StringMessageConverter | ByteArrayMessageConverter |
|---|---|---|
| Kiểu payload chính | `String` | `byte[]` |
| MIME type mặc định | `text/plain` | `application/octet-stream` |
| Charset | Có ý nghĩa khi giải mã byte thành text | Không áp dụng; giữ nguyên byte |
| Mục đích | Nội dung văn bản | Nội dung nhị phân |
| JSON thành DTO | Không tự parse JSON | Không parse JSON |
| Ví dụ | Văn bản, dòng lệnh, text payload | File, ảnh, binary frame |

Lựa chọn dựa trên hợp đồng payload và kiểu dữ liệu đích. Đừng chọn converter chỉ dựa trên tên destination hoặc vì payload “trông giống chuỗi” khi chưa biết encoding.

## 6. Content-Type và charset ảnh hưởng thế nào?

### 6.1 Content-Type là metadata của message

Trong Spring Messaging, Content-Type thường được đặt ở header `MessageHeaders.CONTENT_TYPE`. Giá trị có thể là `MimeType` hoặc dạng tương thích mà API hỗ trợ.

Ví dụ:

- `text/plain;charset=UTF-8`: nội dung văn bản và charset UTF-8.
- `application/octet-stream`: dữ liệu byte tổng quát.
- `application/json`: nội dung JSON.

Converter sử dụng supported MIME types cùng kiểu đích để quyết định có thể chuyển đổi hay không. `StringMessageConverter` mặc định hỗ trợ `text/plain`; `ByteArrayMessageConverter` mặc định hỗ trợ `application/octet-stream`.

Có thể cấu hình thêm MIME type được hỗ trợ cho converter nếu hợp đồng ứng dụng yêu cầu. Tuy nhiên, mở rộng MIME type không tự thêm khả năng parse nội dung. Ví dụ, cho phép StringMessageConverter nhận `application/json` vẫn chỉ có nghĩa là nhận văn bản JSON thành String, không biến nó thành DTO.

### 6.2 Charset và dữ liệu Unicode

Charset quy định cách ánh xạ byte thành ký tự. Khi gửi và nhận văn bản:

1. Chọn charset, thường là UTF-8.
2. Đặt Content-Type có charset phù hợp.
3. Bảo đảm phía nhận dùng cùng charset.
4. Kiểm thử tiếng Việt, ký tự ngoài ASCII và nội dung có dấu.
5. Không giải mã binary payload bằng charset văn bản.

UTF-8 là lựa chọn phổ biến cho giao tiếp hiện đại. Nhưng nếu giao thức bên ngoài quy định charset khác, cần tuân theo hợp đồng của giao thức.

### 6.3 Content-Type thiếu hoặc không khớp

Khi Content-Type không có, khả năng converter được chọn phụ thuộc cấu hình và chính sách strict content-type matching của converter. Khi Content-Type hiện diện nhưng không tương thích, converter có thể từ chối chuyển đổi và kết quả là không có converter phù hợp.

Để tránh hành vi khó đoán:

- Đặt Content-Type rõ ràng ở nơi tạo message hoặc adapter.
- Đặt đúng target class khi gọi fromMessage.
- Không dùng một MIME type để che giấu payload có cấu trúc khác.
- Kiểm tra converter được đăng ký và thứ tự lựa chọn khi dùng nhiều converter.

## 7. Dùng converter trong luồng ứng dụng

### 7.1 Gọi converter trực tiếp

Có thể dùng converter trực tiếp khi cần kiểm soát rõ bước chuyển đổi:

~~~java
StringMessageConverter converter = new StringMessageConverter();

String text = converter.fromMessage(message, String.class);
~~~

Nếu kết quả không thể chuyển đổi, API có thể trả về `null`. Hãy kiểm tra kết quả trước khi dùng. Nếu ứng dụng yêu cầu bắt buộc phải có String, hãy chuyển trường hợp không hỗ trợ thành lỗi đầu vào rõ ràng.

### 7.2 Kết hợp nhiều converter

Spring cung cấp `CompositeMessageConverter` để kết hợp danh sách converter. Composite thử các converter theo thứ tự cho tới khi tìm được converter hỗ trợ việc chuyển đổi.

Ví dụ khởi tạo:

~~~java
import java.util.List;

import org.springframework.messaging.converter.ByteArrayMessageConverter;
import org.springframework.messaging.converter.CompositeMessageConverter;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.messaging.converter.StringMessageConverter;

List<MessageConverter> converters = List.of(
        new StringMessageConverter(),
        new ByteArrayMessageConverter()
);

MessageConverter composite =
        new CompositeMessageConverter(converters);
~~~

Thứ tự converter quan trọng khi có converter hỗ trợ các kiểu hoặc MIME type chồng lấn. Đặt converter phù hợp với hợp đồng cụ thể và kiểm thử trường hợp payload có thể được nhiều converter nhận.

Trong các thành phần Spring khác, danh sách converter có thể được cấu hình qua registry hoặc auto-configuration riêng. Đừng giả định việc tạo một CompositeMessageConverter sẽ tự động đăng ký nó cho mọi controller, channel hay adapter trong ứng dụng.

### 7.3 Converter và MessagingTemplate

Các template messaging hỗ trợ thao tác gửi/nhận và các biến thể chuyển đổi object. Khi dùng các phương thức convert, template dựa vào MessageConverter đã được cấu hình để chuyển object thành message hoặc ngược lại.

Hãy phân biệt:

- Gửi một `Message<?>` đã có payload và headers: không nhất thiết cần chuyển đổi object lần nữa.
- Gửi một object: template có thể gọi converter để tạo message.
- Nhận một message: converter chuyển payload sang target type nếu converter hỗ trợ.
- Request-reply: converter chỉ xử lý biểu diễn payload; nó không quyết định timeout, correlation hoặc việc phản hồi có đến hay không.

## 8. Khi nào nên dùng converter khác?

Hai converter trong bài chỉ xử lý text và byte array. Những kiểu dữ liệu khác cần converter tương ứng:

- JSON thành DTO: converter dựa trên Jackson hoặc serializer JSON phù hợp.
- XML: converter hoặc marshaller hỗ trợ XML.
- Avro, Protobuf hoặc định dạng schema: serializer/deserializer chuyên biệt.
- Dữ liệu domain phức tạp: định nghĩa hợp đồng payload và chuyển đổi có version.
- Dữ liệu nén hoặc mã hóa: codec thực hiện giải nén/giải mã sau khi nhận byte array.

Không nên viết logic parse JSON, XML hoặc binary protocol vào StringMessageConverter hay ByteArrayMessageConverter. Giữ converter tập trung vào đúng nhiệm vụ giúp kiểm thử và thay đổi serializer dễ hơn.

## 9. Lỗi thường gặp và cách xử lý

- **Dùng StringMessageConverter cho file nhị phân:** byte có thể bị giải mã sai hoặc mất khả năng khôi phục.
- **Dùng ByteArrayMessageConverter cho DTO:** converter không tự serialize object tùy ý thành byte.
- **Không khai báo charset:** hai phía có thể giải mã văn bản khác nhau.
- **Content-Type không tương thích:** converter không được chọn hoặc trả về kết quả không chuyển đổi được.
- **Nghĩ JSON thành String là JSON thành object:** chuỗi JSON vẫn cần parser để thành DTO.
- **Không kiểm tra null:** fromMessage có thể không tìm được converter phù hợp.
- **Đăng ký converter sai thứ tự:** converter tổng quát có thể nhận payload trước converter chuyên biệt.
- **Giả định converter được đăng ký toàn cục:** từng adapter hoặc endpoint có thể có danh sách converter riêng.
- **Chuyển byte sang String để log:** làm sai dữ liệu nhị phân và có thể tạo log không an toàn.
- **Bỏ qua kích thước payload:** message quá lớn có thể gây áp lực bộ nhớ, độ trễ và chi phí sao chép.
- **Không kiểm tra schema/version:** converter thành công về mặt kiểu Java không bảo đảm payload tương thích về mặt nghiệp vụ.

## 10. Kiểm thử converter

Nên kiểm thử các trường hợp sau:

1. String payload chuyển thành message với Content-Type phù hợp.
2. Byte UTF-8 được giải mã thành String giữ đúng ký tự tiếng Việt.
3. ByteArrayMessageConverter giữ nguyên mọi byte, bao gồm byte có giá trị ngoài ASCII.
4. Content-Type không khớp được xử lý có chủ đích.
5. Target type không được hỗ trợ không bị coi là kết quả hợp lệ.
6. CompositeMessageConverter chọn converter theo danh sách và MIME type dự kiến.
7. Payload rỗng, payload lớn và dữ liệu lỗi được xử lý đúng.
8. Integration test xác minh adapter thực tế truyền Content-Type và payload như mong đợi.

Ví dụ JUnit có thể dùng cùng dữ liệu ở hai demo trên và kiểm tra String bằng assertEquals, byte array bằng assertArrayEquals. Với charset, luôn có test chứa tiếng Việt và ký tự ngoài ASCII để phát hiện lỗi encoding.

## 11. Checklist lựa chọn converter

Trước khi cấu hình converter, hãy trả lời:

- Payload là văn bản, byte array hay object nghiệp vụ?
- Target class của bước nhận là kiểu nào?
- Content-Type có được đặt và có tương thích không?
- Nếu là text, charset có được xác định rõ không?
- Nếu là binary, byte có được giữ nguyên qua mọi adapter không?
- Có cần converter JSON/XML/Protobuf riêng không?
- Có nhiều converter cùng hỗ trợ một payload và thứ tự có rõ ràng không?
- Converter được cấu hình ở đúng endpoint/template/adapter chưa?
- Có kiểm thử Unicode, byte nhị phân, MIME mismatch và payload lỗi không?
- Kích thước payload có giới hạn hợp lý không?

Khi hiểu rõ kiểu payload, MIME type và charset, bạn có thể chọn đúng converter để message được biểu diễn nhất quán ở cả hai phía, giảm lỗi chuyển đổi và giữ nguyên dữ liệu qua các lớp messaging.