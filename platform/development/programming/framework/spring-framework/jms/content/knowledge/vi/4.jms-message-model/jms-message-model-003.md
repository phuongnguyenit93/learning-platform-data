# BytesMessage và nội dung nhị phân

> **Module:** Spring Framework – JMS  
> **Nhóm:** Mô hình Message  
> **Chủ đề:** Khi nào dùng `BytesMessage`, cách mã hóa và đọc payload nhị phân, hợp đồng định dạng dữ liệu và cách tích hợp với Spring JMS.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `jakarta.jms.BytesMessage` là gì và phân biệt nó với `TextMessage`, `StreamMessage`, `MapMessage` và `ObjectMessage`.
2. Tạo một message nhị phân bằng `Session.createBytesMessage()`, ghi bằng `writeBytes()` hoặc các phương thức ghi giá trị nguyên thủy, rồi đọc đúng trạng thái bằng `readBytes()`, `getBody(byte[].class)` và `getBodyLength()`.
3. Hiểu hai trạng thái **write-only** và **read-only**, vị trí con trỏ đọc, `reset()`, `clearBody()` và những ngoại lệ liên quan.
4. Định nghĩa một hợp đồng nhị phân rõ ràng (byte order, encoding, version, length, content type); tự kiểm tra một frame bằng Java 17.
5. Dùng `JmsTemplate` và `@JmsListener` của Spring JMS để gửi/nhận `byte[]` hoặc `BytesMessage`, kiểm soát dung lượng và xử lý lỗi.
6. Nhận ra các đánh đổi về khả năng tương tác, bộ nhớ, kích thước message, bảo mật và độ tin cậy khi truyền dữ liệu nhị phân qua broker.

## 1. BytesMessage là gì?

Trong JMS/Jakarta Messaging, mỗi message có **header**, **properties** và **body**. `BytesMessage` là loại message có **body là một luồng byte không được JMS tự diễn giải theo một schema nghiệp vụ**. Producer quyết định byte nào được ghi; consumer phải biết cách đọc đúng những byte đó.

Ví dụ body có thể chứa:

- Một đoạn PNG, JPEG, PDF hoặc một tập byte đã được nén.
- Payload Protocol Buffers, CBOR, Avro binary hoặc một định dạng nhị phân do hai dịch vụ thỏa thuận.
- Một khung dữ liệu chứa mã nhận dạng, phiên bản, độ dài và nội dung.
- Dữ liệu nguyên thủy được ghi tuần tự bằng `writeInt()`, `writeLong()`, `writeBoolean()`, `writeUTF()`, v.v.

```text
             JMS message
+--------------------------------------------+
| Header: JMSMessageID, JMSDestination, ...  |
+--------------------------------------------+
| Properties: contentType, schemaVersion, ...|
+--------------------------------------------+
| Body: 89 50 4E 47 0D 0A 1A 0A ...         |
|       (các byte, ví dụ chữ ký PNG)        |
+--------------------------------------------+
```

**JMS không tự suy ra "đây là ảnh PNG" hay "đây là protobuf version 2" từ kiểu `BytesMessage`.** Nếu consumer cần thông tin đó, ứng dụng phải định nghĩa định dạng byte và metadata tương ứng. Một mảng byte hợp lệ ở mức truyền tải chưa chắc là dữ liệu nghiệp vụ hợp lệ.

Jakarta Messaging hiện đại dùng package `jakarta.jms`. Nhiều ví dụ JMS cũ dùng `javax.jms`; không được trộn hai loại API này trong cùng ví dụ Java/Spring hiện đại. Spring Framework 6+ dùng Jakarta.

## 2. Khi nào dùng BytesMessage?

| Nhu cầu | Dạng message thường phù hợp | Ghi chú |
| --- | --- | --- |
| Gửi nội dung văn bản có charset/ý nghĩa rõ | `TextMessage` | Thuận tiện cho JSON, XML, văn bản; payload chính là String |
| Gửi mảng byte hoặc định dạng nhị phân có sẵn | **`BytesMessage`** | Giữ nguyên chuỗi byte theo định dạng đã quy ước |
| Gửi các giá trị nguyên thủy theo thứ tự tuần tự | `StreamMessage` hoặc `BytesMessage` | `StreamMessage` có ngữ nghĩa typed stream; `BytesMessage` dành cho byte layout cụ thể |
| Gửi các cặp key/value kiểu nguyên thủy | `MapMessage` | Body là map; các tên trường được lưu như tên mục dữ liệu |
| Gửi một object Java Serializable | `ObjectMessage` | Ràng buộc Java serialization; cần đánh giá bảo mật và tương thích phiên bản |

**Dùng `BytesMessage` khi binary là một phần thực chất của hợp đồng**, ví dụ dữ liệu cảm biến cấu trúc fixed-width, thumbnail nhỏ, protobuf được hai hệ thống hiểu hoặc frame của một protocol cũ. Đừng mặc định mọi dữ liệu “phức tạp” phải là bytes: JSON text có thể dễ quan sát và nâng cấp hơn nếu yêu cầu không đòi binary.

### Không nhầm binary payload với “streaming file” vô hạn

Tên `BytesMessage` chứa từ “bytes” nhưng bản thân JMS message vẫn là một đơn vị gửi/nhận do broker quản lý. `readBytes()` cho phép *đọc dần body ở phía client*, song **không mặc nhiên biến JMS thành dịch vụ stream file lớn hoặc đảm bảo bộ nhớ broker dùng hằng số**. Mỗi provider có giới hạn kích thước message, quota và chi phí lưu trữ riêng.

Với video, bản sao database, ZIP hàng gigabyte hay file lớn, kiến trúc thường tốt hơn là **lưu blob vào object storage** và gửi qua JMS một message nhỏ chứa định danh object, vị trí có kiểm soát truy cập, kích thước, checksum và version. Kiểm soát lifetime và quyền truy cập object riêng biệt với acknowledgment của JMS.

## 3. Body nhị phân và metadata là hai phần khác nhau

Các thành phần chuẩn của một message:

- **Header JMS:** `JMSMessageID`, `JMSCorrelationID`, `JMSTimestamp`, `JMSDestination`, `JMSDeliveryMode`, `JMSExpiration`, `JMSRedelivered`, v.v. Những header này phục vụ giao nhận, định tuyến và tương quan.
- **Properties ứng dụng:** các tên/giá trị do ứng dụng đặt, ví dụ `contentType="application/octet-stream"`, `schemaVersion=1`, `jobId="job-42"`. Đây là **quy ước của ứng dụng**, không phải header HTTP tự động hay schema JMS mặc định.
- **Body:** các byte thực sự cần truyền, ví dụ `0xCA 0xFE 0x01 ...`.

Ví dụ một hợp đồng gửi thumbnail nhỏ:

```text
JMS destination : thumbnail.generate
JMSCorrelationID: request-42

Properties:
  contentType    = application/vnd.example.image-task
  schemaVersion  = 1
  objectId       = image-42

Body (binary):
  magic (2 bytes) + version (1 byte)
  + payloadLength (4 bytes, big-endian)
  + raw image bytes (payloadLength bytes)
```

Trong ví dụ này, phần version xuất hiện **cả trong property và frame** chỉ để giúp phân loại sớm và kiểm tra nhất quán. Ứng dụng thực không bắt buộc nhân đôi: phải chọn một nguồn tin cậy cho schema và quy tắc kiểm tra nếu có hai bản. Header/properties có thể tiện cho **message selector** và quan sát broker, còn body có thể giúp codec xử lý độc lập với vận chuyển JMS.

Không nhầm `JMSMessageID` với business ID hoặc checksum. JMSMessageID do provider gán để nhận diện message ở hệ thống messaging; nếu cùng một tác vụ nghiệp vụ được gửi lại bằng một message khác, message ID có thể thay đổi. Nếu cần idempotency, thiết kế một khóa nghiệp vụ ổn định riêng.

## 4. API đọc/ghi BytesMessage

Tạo một message chưa có dữ liệu:

```java
BytesMessage message = session.createBytesMessage();
```

`session` ở đây là `jakarta.jms.Session` do một JMS provider và connection đang hoạt động cấp. Đoạn mã minh họa **cần môi trường JMS**, không phải chương trình Java chỉ cần `javac`.

### 4.1. Ghi byte nguyên trạng

```java
byte[] payload = new byte[] {
        (byte) 0xCA, (byte) 0xFE, 0x01, 0x02, 0x03
};

BytesMessage message = session.createBytesMessage();
message.writeBytes(payload);
message.setStringProperty("contentType", "application/octet-stream");
message.setIntProperty("schemaVersion", 1);

producer.send(message);
```

`producer` là một `jakarta.jms.MessageProducer` đã gắn đúng destination, hoặc được gọi qua hàm `send(destination, message)` tùy cách tạo. Những lệnh trên chỉ mô tả phần tạo/gửi trong ứng dụng đã có connection, session, broker. `writeBytes(byte[])` sao chép byte vào body; **nó không biến mảng thành một Java object serialization**.

Có biến thể:

```java
message.writeBytes(payload, 1, 3); // Ghi 3 byte từ offset 1: FE 01 02
```

Cần kiểm tra offset, length và giới hạn body trước khi gửi; không gửi vùng mảng không thuộc payload.

### 4.2. Ghi giá trị nguyên thủy theo thứ tự

`BytesMessage` cũng có các cặp kiểu:

| Ghi | Đọc tương ứng | Ý nghĩa |
| --- | --- | --- |
| `writeBoolean(boolean)` | `readBoolean()` | Giá trị boolean |
| `writeByte(byte)` | `readByte()` / `readUnsignedByte()` | Byte có dấu hoặc không dấu khi đọc |
| `writeShort(short)` | `readShort()` / `readUnsignedShort()` | Giá trị 16 bit |
| `writeChar(char)` | `readChar()` | Một `char` Java |
| `writeInt(int)` | `readInt()` | Giá trị 32 bit |
| `writeLong(long)` | `readLong()` | Giá trị 64 bit |
| `writeFloat(float)` | `readFloat()` | Floating-point 32 bit |
| `writeDouble(double)` | `readDouble()` | Floating-point 64 bit |
| `writeUTF(String)` | `readUTF()` | Chuỗi theo **modified UTF-8** của phương thức |
| `writeBytes(byte[])` | `readBytes(byte[])` | Byte array thô, không kèm tên trường |

Ví dụ:

```java
BytesMessage m = session.createBytesMessage();
m.writeInt(42);
m.writeBoolean(true);
m.writeUTF("DONE");
```

Consumer phải đọc đúng **thứ tự và kiểu**: `readInt()` → `readBoolean()` → `readUTF()`. Nếu bên gửi thay đổi thứ tự nhưng không cập nhật hợp đồng, các byte vẫn đến đầy đủ nhưng decoder có thể hiểu sai hoặc ném ngoại lệ.

**Đặc biệt:** `writeUTF()` / `readUTF()` dùng biến thể *modified UTF-8*, có thông tin độ dài theo định dạng của API; nó **không tương đương** với `writeBytes(text.getBytes(StandardCharsets.UTF_8))`. Khi tích hợp với Python, Go hoặc một protocol quy định “UTF-8 thô”, nên mã hóa rõ bằng `StandardCharsets.UTF_8` và tự định nghĩa độ dài. Đừng xem `writeUTF` là một codec UTF-8 tùy ý.

### 4.3. Body có trạng thái write-only và read-only

Đây là điểm khác biệt quan trọng so với thao tác đọc trên `byte[]` thuần.

```text
createBytesMessage()
        |
        v
 [ WRITE-ONLY ] -- writeBytes/writeInt/... --> [ WRITE-ONLY ]
        |
        | reset()
        v
 [ READ-ONLY; cursor = 0 ] -- readBytes/readInt/... --> [ READ-ONLY ]
        |
        | reset(): cursor trở lại 0
        +-----------------------------------> [ READ-ONLY ]
        |
        | clearBody(): xóa body
        v
 [ WRITE-ONLY; body rỗng ]
```

- Message mới tạo bắt đầu ở chế độ **write-only**. Ghi được, nhưng cố đọc body trước khi `reset()` sẽ gây `MessageNotReadableException`.
- `reset()` đưa body về **read-only** và đặt vị trí đọc ở **đầu luồng byte**. Nó không xóa dữ liệu, không tạo message mới và không phải “acknowledgment”.
- Message nhận được từ provider đã ở chế độ **read-only** với con trỏ ở đầu. Listener thường đọc ngay, **không cần tự `reset()` lần đầu**.
- Cố ghi vào body đã read-only gây `MessageNotWriteableException`.
- `clearBody()` **xóa toàn bộ body** và đưa nó về write-only. Phương thức này **không xóa header hay properties**; muốn xóa properties có `clearProperties()` với ý nghĩa khác.
- Khi cần đọc lại từ đầu một `BytesMessage` vẫn còn trong quyền sử dụng, `reset()` đặt cursor về 0. Đây là thao tác trên message object phía client, không yêu cầu broker gửi lại.

Không dùng `clearBody()` để “reset con trỏ cho đọc lại”: nó phá hủy body. Không dùng `reset()` để cố mở lại quyền ghi: nó thiết lập read-only.

### 4.4. Đọc BytesMessage bằng readBytes

Trên message **đã nhận** (read-only):

```java
long n = message.getBodyLength();
if (n < 0 || n > 1_048_576) {
    throw new IllegalArgumentException("Unexpected body size: " + n);
}

byte[] data = new byte[(int) n];
int total = 0;
while (total < data.length) {
    byte[] chunk = new byte[Math.min(8192, data.length - total)];
    int count = message.readBytes(chunk);
    if (count < 0) {
        throw new IllegalStateException("Truncated BytesMessage");
    }
    System.arraycopy(chunk, 0, data, total, count);
    total += count;
}
```

Ở đây `message` là `BytesMessage` nhận được từ broker; ví dụ có giới hạn 1 MiB **chỉ để minh họa cách chặn payload không mong đợi**. Mảng cấp phát theo `getBodyLength()` sau khi so giới hạn; hàm trả `long`, vì thế không ép `long` sang `int` trước khi kiểm tra. Trong thực tế, vòng đọc cần điều khoản bảo vệ nếu provider trả 0 lặp bất thường; một consumer production cũng phải có giới hạn thời gian và chiến lược lỗi.

`readBytes(buffer)` trả **số byte thực sự được sao chép**, không phải độ dài của buffer; khi hết byte, trả **-1**. Nếu body còn ít byte hơn buffer, chỉ phần đầu buffer được cập nhật. Luôn xử lý đúng số byte trả về. Sau khi `readBytes` đã di chuyển cursor, các phép đọc tiếp theo bắt đầu từ vị trí mới.

Với payload nhỏ và muốn API tiện dụng, có cách khác:

```java
byte[] data = message.getBody(byte[].class);
```

JMS/Jakarta Messaging hỗ trợ `Message.getBody(byte[].class)` để lấy toàn bộ body của `BytesMessage` mà không cần ép kiểu xuống `BytesMessage` trong các trường hợp phù hợp. Lựa chọn này **cấp phát mảng chứa toàn bộ body**, nên vẫn phải kiểm soát kích thước và chi phí bộ nhớ. Nếu cần duy trì định dạng byte cho hệ thống khác, không biến body thành String tùy tiện chỉ để log.

### 4.5. Khi đọc kiểu nguyên thủy có thể lỗi gì?

- `MessageNotReadableException`: đọc trong lúc body đang write-only.
- `MessageNotWriteableException`: ghi khi body read-only.
- `MessageEOFException`: cố đọc dữ liệu nguyên thủy vượt cuối luồng.
- `MessageFormatException`: đọc sai định dạng/kiểu hoặc nội dung không thỏa quy tắc decode theo phương thức gọi.
- `JMSException`: lỗi provider hoặc hoạt động JMS; kiểm tra thêm nguyên nhân và chính sách retry.

Không phải lỗi nào cũng nên retry vô hạn. Một payload sai định dạng lặp lại thường là **poison message**; cần phân loại theo nguyên nhân, log metadata phù hợp và áp dụng retry/dead-letter theo broker.

## 5. Hợp đồng nhị phân phải xác định “byte nào có nghĩa gì”

Nếu hai dịch vụ tự định nghĩa một binary frame, tài liệu định dạng tối thiểu phải chốt:

1. **Magic/version:** cách phát hiện đúng định dạng và cách phát triển phiên bản.
2. **Độ dài:** số byte, vị trí và kiểu số của trường length; giới hạn tối đa chấp nhận.
3. **Byte order:** big-endian/little-endian cho số nhiều byte.
4. **Charset:** UTF-8, UTF-16 hoặc không có text; không suy luận theo charset mặc định hệ điều hành.
5. **Phân đoạn:** vị trí header, payload, checksum, chữ ký, phần mở rộng.
6. **Nén/mã hóa:** thuật toán, thứ tự thực hiện, cách lấy khóa và xử lý lỗi.
7. **Tương thích:** có cho phép bỏ qua field chưa biết, trường bắt buộc nào, cách nhận schema cũ.
8. **Giới hạn:** message size, decompressed size, nesting depth, tổng bản ghi; quyền truy cập dữ liệu.

Giả sử định dạng minh họa:

| Offset byte | Độ dài | Ý nghĩa |
| --- | --- | --- |
| `0..1` | 2 | Magic `0xCAFE`, big-endian |
| `2` | 1 | Version, giá trị `1` |
| `3..6` | 4 | Payload length, signed 32-bit integer, big-endian; phải không âm |
| `7..` | Theo length | Payload UTF-8 trong demo; ở hệ thống thật có thể là binary tùy schema |

Với payload “HELLO” (5 byte ASCII cũng là UTF-8), frame là:

```text
CA FE | 01 | 00 00 00 05 | 48 45 4C 4C 4F
magic | ver| payload len | H  E  L  L  O
```

Tổng độ dài **12 byte**. Đây là **một định dạng mẫu tự xây**, không phải cấu trúc bắt buộc của `BytesMessage`. Bản thân BytesMessage **không tự thêm magic, version hay length như bảng**; producer phải ghi, consumer phải parse nếu đã thỏa thuận.

## 6. Ví dụ Java 17 chạy độc lập: mã hóa và giải mã binary frame

Ví dụ này sử dụng Java I/O thuần để bạn kiểm tra **định dạng body** trước khi thêm JMS. Nó **không mở broker, không tạo BytesMessage**, và có đầu ra xác định để kiểm chứng. Khi đưa vào JMS, có thể gửi toàn bộ `frame` bằng `writeBytes(frame)`.

Tạo tệp **`BinaryFrameDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class BinaryFrameDemo {
    private static final int MAGIC = 0xCAFE;
    private static final int VERSION = 1;
    private static final int MAX_BODY_BYTES = 1024;

    public static void main(String[] args) throws IOException {
        byte[] payload = "HELLO".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeShort(MAGIC);           // 2 byte, big-endian
            out.writeByte(VERSION);          // 1 byte
            out.writeInt(payload.length);   // 4 byte, big-endian
            out.write(payload);             // byte của payload
        }

        byte[] frame = buffer.toByteArray();

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(frame))) {

            int magic = in.readUnsignedShort();
            int version = in.readUnsignedByte();
            int length = in.readInt();

            if (magic != MAGIC || version != VERSION) {
                throw new IOException("Unsupported frame");
            }
            if (length < 0 || length > MAX_BODY_BYTES) {
                throw new IOException("Invalid payload length");
            }

            byte[] decoded = in.readNBytes(length);
            if (decoded.length != length || in.read() != -1) {
                throw new IOException("Truncated or trailing frame");
            }

            System.out.printf("Magic: %04X%n", magic);
            System.out.println("Version: " + version);
            System.out.println("Payload length: " + decoded.length);
            System.out.println("Payload: " +
                    new String(decoded, StandardCharsets.UTF_8));
            System.out.println("Frame bytes: " + frame.length);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac BinaryFrameDemo.java
java BinaryFrameDemo
```

Đầu ra chính xác:

```text
Magic: CAFE
Version: 1
Payload length: 5
Payload: HELLO
Frame bytes: 12
```

Các điểm cần hiểu:

- `DataOutputStream`/`DataInputStream` được cặp code này sử dụng để quy định thứ tự ghi/đọc. Việc chọn **big-endian** là một phần của hợp đồng demo, không phụ thuộc máy chạy.
- `readUnsignedShort()` đọc magic không dấu; nếu gọi `readShort()`, `0xCAFE` sẽ được biểu diễn bằng số âm, dù hai byte không thay đổi.
- `readNBytes(length)` trả số byte đọc được; chương trình **kiểm tra đủ length và không có byte thừa** để tránh chấp nhận frame lỗi.
- `MAX_BODY_BYTES` chặn khai báo length quá lớn trước khi cấp phát. Khi parse từ nguồn không đáng tin, không cấp phát `new byte[length]` ngay khi mới đọc length.
- Nếu payload là PNG hoặc protobuf, code phải chuyển phần `decoded` sang codec tương ứng; **không** mặc định `new String(...)` cho dữ liệu không phải text.

**Chú ý về giới hạn mẫu:** demo chỉ mô tả một frame nhỏ đã có trong RAM. Không thay thế giải pháp kiểm tra checksum/authentication, phân mảnh file hoặc schema evolution của hệ thống thật.

## 7. Tích hợp với Spring JMS

Spring Framework 6+ cung cấp `JmsTemplate` để gửi và `@JmsListener` để nhận. Cần một JMS provider tương thích, `jakarta.jms.ConnectionFactory`, cấu hình destination và dependency Spring JMS. Ví dụ sau là **các lớp thuộc cùng một ứng dụng Spring**; không thể chạy từng file chỉ bằng `javac` vì còn dependency/framework và broker.

Có hai cách:

- **Tự tạo `BytesMessage`** khi cần kiểm soát properties và cách ghi: `JmsTemplate.send(destination, session -> session.createBytesMessage())`.
- **Dùng conversion** khi chỉ có `byte[]`: `JmsTemplate.convertAndSend(destination, byte[])`. Với `SimpleMessageConverter` mặc định, Spring chuyển `byte[]` thành `BytesMessage`; ở chiều nhận có thể chuyển lại thành `byte[]`.

### 7.1. Cấu hình listener có local JMS transaction

**Tệp `BinaryJmsConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class BinaryJmsConfig {

    @Bean(name = "binaryListenerFactory")
    public DefaultJmsListenerContainerFactory binaryListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Ví dụ dùng **queue** tên `binary.jobs` (Spring JMS mặc định là queue khi không bật pub/sub). `setSessionTransacted(true)` giúp listener container sử dụng local JMS transaction để commit/rollback việc nhận. Nó **không tự gộp** transaction JMS với transaction database hoặc tác dụng phụ bên ngoài. Nếu xử lý thất bại, hành vi redelivery, số lần retry và dead-letter phụ thuộc provider và cấu hình ứng dụng.

### 7.2. Producer tự tạo BytesMessage

**Tệp `BinaryJobPublisher.java`:**

```java
import jakarta.jms.BytesMessage;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

import java.util.Objects;

@Service
public class BinaryJobPublisher {
    private static final int MAX_BYTES = 1_048_576;

    private final JmsTemplate jmsTemplate;

    public BinaryJobPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(byte[] payload, String jobId) {
        Objects.requireNonNull(payload, "payload");
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is required");
        }
        if (payload.length > MAX_BYTES) {
            throw new IllegalArgumentException("Payload too large");
        }

        jmsTemplate.send("binary.jobs", session -> {
            BytesMessage message = session.createBytesMessage();
            message.writeBytes(payload);
            message.setStringProperty(
                    "contentType", "application/octet-stream");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("jobId", jobId);
            return message;
        });
    }
}
```

`publish` chỉ thành công khi thao tác gửi đã hoàn tất theo hợp đồng JMS/provider. Nó **không chứng minh consumer đã xử lý xong công việc**. Trong sản phẩm thực, quyết định TTL, delivery mode và atomicity giữa DB update với JMS send dựa theo nghiệp vụ. Không đưa secret vào properties hay log.

Tại đây `payload` là byte của một format đã thỏa thuận. Nếu cần gửi chính frame “CA FE ...” ở phần 6, producer truyền **mảng `frame`** do codec tạo; `writeBytes` giữ nguyên byte. Việc producer đặt `schemaVersion=1` chỉ hữu ích khi consumer kiểm tra và hiểu schema tương ứng.

### 7.3. Listener nhận trực tiếp BytesMessage

**Tệp `BinaryJobListener.java`:**

```java
import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BinaryJobListener {
    private static final long MAX_BYTES = 1_048_576L;

    @JmsListener(
            destination = "binary.jobs",
            containerFactory = "binaryListenerFactory")
    public void onBinaryJob(BytesMessage message) throws JMSException {
        String type = message.getStringProperty("contentType");
        int version = message.getIntProperty("schemaVersion");
        String jobId = message.getStringProperty("jobId");

        if (!"application/octet-stream".equals(type) || version != 1) {
            throw new IllegalArgumentException("Unknown binary schema");
        }
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("Missing jobId");
        }

        long length = message.getBodyLength();
        if (length < 0 || length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid body length");
        }

        byte[] body = message.getBody(byte[].class);
        if (body.length != length) {
            throw new IllegalStateException("Body length mismatch");
        }

        // Ở ứng dụng thật, chuyển body tới codec nghiệp vụ đã kiểm chứng.
        System.out.println(
                "Received " + body.length + " bytes for job " + jobId);
    }
}
```

Spring cho phép phương thức `@JmsListener` nhận raw `jakarta.jms.Message` hoặc subtype phù hợp như `BytesMessage`. Bằng cách nhận nguyên message, listener kiểm tra size và metadata **trước khi lấy body ra mảng**. Đây là minh họa chặn payload nhỏ; với dữ liệu nhị phân không đáng tin, còn phải kiểm tra **định dạng bên trong body**.

Nếu gọi `publish(new byte[] {1, 2, 3}, "job-42")` và broker, queue, listener đều hoạt động đúng, một lần xử lý thành công có thể in:

```text
Received 3 bytes for job job-42
```

Đây là output **điều kiện**, không phải kết quả được bảo đảm ở mỗi lần khởi động: còn phụ thuộc connection, transaction, delivery, trạng thái broker, retry và consumer. Không suy ra “chính xác một lần” từ log.

### 7.4. Cách ngắn gọn bằng conversion của JmsTemplate

Với `SimpleMessageConverter` mặc định và chỉ cần body nhị phân:

```java
byte[] bytes = new byte[] {1, 2, 3, 4};
jmsTemplate.convertAndSend("binary.jobs", bytes);
```

Spring sẽ tạo `BytesMessage` từ `byte[]`. Một listener có thể nhận payload sau conversion:

```java
@JmsListener(destination = "binary.jobs",
             containerFactory = "binaryListenerFactory")
public void receive(byte[] bytes) {
    System.out.println("Received " + bytes.length + " bytes");
}
```

**Hai đoạn chỉ là lựa chọn thay thế**, không được đăng ký song song ở cùng queue nếu muốn một consumer duy nhất quan sát tất cả message: các listener cạnh tranh trên queue sẽ chia nhau message. Với tự động chuyển `byte[]`, converter có thể đọc toàn bộ body để tạo mảng trước khi method chạy, nên không thích hợp khi cần kiểm tra size từ raw message **trước khi cấp phát**. Nếu ứng dụng dùng custom `MessageConverter`, phải xác nhận lại mapping.

## 8. Đọc theo chunk: khi nào nên dùng?

Với `BytesMessage` nhận được, `getBodyLength()` trả `long`, `readBytes(buffer)` cho phép đọc từng phần:

```java
byte[] buffer = new byte[8192];
int count;
while ((count = message.readBytes(buffer)) != -1) {
    if (count == 0) {
        throw new IllegalStateException("No forward progress");
    }
    // Chỉ xử lý buffer[0..count), không dùng toàn bộ buffer.
}
```

Đoạn này là **mẫu xử lý trong listener**: biến `message` phải ở trạng thái read-only và tùy codec, logic ở comment phải được thay bằng xử lý thật. Code không độc lập; đây chỉ là mẫu API để giải thích con trỏ.

Trước vòng lặp nên đặt ngưỡng từ `getBodyLength()` và theo dõi tổng số byte. Nếu đưa từng chunk đến một `OutputStream` có kiểm soát, có thể tránh **tạo thêm một bản copy toàn body tại tầng ứng dụng**. Tuy nhiên, JMS provider vẫn có thể buffer toàn message hoặc có giới hạn broker khác; **không** cam kết streaming end-to-end chỉ nhờ vòng lặp `readBytes()`.

Sử dụng `getBody(byte[].class)` khi payload nhỏ, tin cậy và bạn muốn đơn giản. Dùng `readBytes()` có giới hạn khi cần kiểm soát quá trình đọc hoặc tránh cấp phát một mảng rất lớn. Với file lớn, cân nhắc object storage và message chứa tham chiếu.

## 9. Các vấn đề thiết kế quan trọng của nội dung nhị phân

### 9.1. Charset và binary không phải một thứ

- `byte[]` không mang charset.
- `new String(bytes)` dùng charset mặc định nếu không chỉ rõ; có thể biến dữ liệu thành chuỗi sai.
- Chuyển văn bản sang bytes nên dùng `text.getBytes(StandardCharsets.UTF_8)`; chiều ngược lại dùng `new String(bytes, StandardCharsets.UTF_8)` **khi biết chắc body là UTF-8**.
- Với payload PNG/PDF/protobuf, không áp dụng decoder văn bản để “xem thử” rồi gửi lại; thao tác này có thể làm thay đổi dữ liệu.
- Base64 mã hóa bytes thành ký tự để chuyển qua kênh văn bản nhưng tăng kích thước. Nếu JMS đã dùng `BytesMessage`, không cần Base64 **chỉ để gửi mảng byte**.

### 9.2. Byte order và cách parse primitive

Trong frame tự định nghĩa, producer/consumer cần thống nhất big-endian hoặc little-endian. `DataOutputStream`/`DataInputStream` của Java là một cặp tiện để minh họa big-endian; các client ở ngôn ngữ khác cần đọc đúng byte order đó.

Không trộn vô ý:

```text
writeInt(0x01020304) -> 01 02 03 04  (big-endian theo demo)
raw byte sequence   -> 04 03 02 01  (little-endian khác)
```

Một decoder được viết cho little-endian có thể hiểu sai length, sinh lỗi hoặc yêu cầu cấp phát bộ nhớ bất thường. Vì thế kiểm tra magic, version và max length **trước** khi đọc/cấp phát payload.

### 9.3. Thay đổi schema mà không làm hỏng consumer cũ

Nhị phân thường khó đọc bằng mắt; càng cần version và tài liệu rõ. Ví dụ v1 dùng frame `magic + version + length + bytes`. Nếu v2 thêm compression flag, có thể:

- Định nghĩa version mới và decoder v2 rõ ràng.
- Giữ reader tương thích v1 trong một giai đoạn chuyển đổi.
- Không tái sử dụng version 1 cho layout mới mà decoder cũ không hiểu.
- Có bài kiểm tra bằng file “golden bytes” cho từng phiên bản, ngôn ngữ và broker/provider cần hỗ trợ.
- Gắn schema ID/version trong properties nếu dùng selector hay công cụ quản lý, nhưng không chỉ dựa vào property chưa kiểm tra.

Với protobuf/Avro, **BytesMessage chỉ vận chuyển bytes**; compatibility rules nằm ở schema registry/codec ứng dụng, không phải JMS tự giải quyết.

### 9.4. Nén, mã hóa và toàn vẹn dữ liệu

Nén trước khi gửi có thể giảm byte truyền nhưng tăng CPU, làm trễ và tạo rủi ro **decompression bomb**. Trường khai báo `compressedSize` có thể nhỏ trong khi dữ liệu giải nén rất lớn; đặt ngưỡng cả trên *encoded size* lẫn *decoded size*.

TLS và xác thực broker bảo vệ kênh truyền theo cấu hình. Nếu cần end-to-end encryption hoặc message-level signatures, thiết kế khóa, version và cách xác thực riêng; đừng coi `BytesMessage` tự mã hóa payload.

Checksum phát hiện lỗi vô ý nhưng không thay chữ ký hoặc MAC chống giả mạo khi dữ liệu đi qua miền tin cậy khác. Không log payload nhị phân chứa thông tin cá nhân/secret; ghi metadata đủ để truy vết (message ID, job ID, content type, kích thước, schema, hash có kiểm soát).

### 9.5. Không lấy dữ liệu không tin cậy làm thao tác nguy hiểm

Dù nhận được body hợp lệ qua broker, consumer vẫn phải coi nguồn dữ liệu là **untrusted input** ở ranh giới nghiệp vụ:

1. Kiểm tra kích thước message và kích thước sau giải nén.
2. Kiểm tra schema, version, magic, length, checksum/signature khi cần.
3. Dùng parser an toàn; giới hạn nesting, số trường và số phần tử.
4. Không tự động Java-deserialize payload bytes thành object tùy ý.
5. Nếu nhận tên file/đường dẫn, không ghép thẳng vào đường dẫn hệ thống; xác thực và chuẩn hóa theo quy tắc ứng dụng.
6. Phân loại lỗi dữ liệu vĩnh viễn, tránh retry vô hạn cùng một poison message.
7. Đưa message vào DLQ/quarantine theo chính sách broker để điều tra có kiểm soát.

### 9.6. Độ tin cậy, acknowledgement và xử lý trùng

`BytesMessage` **không mang cơ chế reliability riêng** khác các JMS message type. `PERSISTENT`/`NON_PERSISTENT`, queue/topic, transaction, TTL, acknowledgment, retry và dead-letter đều là các trục thiết kế độc lập với format của body.

Ví dụ một message yêu cầu xử lý ảnh được consumer nhận, lưu thumbnail thành công rồi JVM chết **trước khi JMS transaction commit**. Broker có thể redeliver message. Nếu consumer tạo file mới ở mỗi lần nhận, có thể có bản ghi trùng. Dùng business ID ổn định để kiểm tra idempotency, ghi kết quả theo khóa duy nhất hoặc lưu trạng thái xử lý và tác động nghiệp vụ trong một giao dịch phù hợp.

Bật `setSessionTransacted(true)` không biến database transaction và JMS transaction thành một; vẫn cần thiết kế nhất quán khi một trong hai bước thành công và bước kia thất bại.

## 10. Quy trình kiểm thử BytesMessage

Để phân biệt lỗi encoding và lỗi broker, kiểm tra từ nhỏ đến lớn.

### Thử nghiệm A — Round-trip codec thuần

1. Chạy `BinaryFrameDemo`; kết quả frame dài 12 byte và payload “HELLO”.
2. Tạo thêm các trường hợp: payload rỗng, payload chứa byte `0x00`, `0xFF` và ký tự tiếng Việt đã encode UTF-8.
3. Thay một byte magic hoặc version: decoder phải từ chối.
4. Thay length thành số âm, quá lớn, nhỏ hơn hoặc lớn hơn số byte thật: decoder phải từ chối.
5. Gửi golden frame qua codec Java và một client ngôn ngữ khác nếu hệ thống liên ngôn ngữ.

### Thử nghiệm B — JMS round-trip

1. Khởi động provider và tạo queue `binary.jobs`.
2. Gửi `byte[]` bằng `convertAndSend`, xác minh consumer nhận đúng giá trị từng byte.
3. Dùng producer `send` với `BytesMessage` để thêm `contentType`/`schemaVersion`/`jobId`; consumer xác minh properties và body.
4. Gửi message có `schemaVersion` sai và thử payload vượt ngưỡng, xác nhận listener từ chối có chủ đích.
5. Quan sát cấu hình transaction/ack và DLQ khi decoder ném ngoại lệ.

### Thử nghiệm C — Lỗi vận hành

- Consumer tạm dừng, producer vẫn gửi: quan sát số message chờ; kiểm tra TTL và delivery mode phù hợp nhu cầu.
- Consumer crash sau khi xử lý side effect nhưng trước ack: xác minh idempotency trên cùng job ID.
- Broker nhận message lớn: theo dõi giới hạn producer/broker, heap, network và backlog; kiểm tra hành vi “message too large”.
- Xác minh message lỗi không retry vô tận, DLQ có đủ metadata để điều tra nhưng không phơi payload nhạy cảm.

### Các số liệu đáng quan sát

| Metric / tín hiệu | Ý nghĩa |
| --- | --- |
| Body bytes theo type/version | Phát hiện payload tăng kích thước bất thường |
| Queue backlog và tuổi message | Consumer không kịp xử lý hoặc bị ngừng |
| Rate lỗi parse/schema | Producer và consumer không tương thích |
| Retry/redelivery count | Lỗi logic, thiếu tài nguyên hoặc side effect không ổn định |
| DLQ count | Message không thể xử lý sau chính sách retry |
| Processing latency | Độ trễ từ khi broker chuyển giao đến khi nghiệp vụ hoàn thành |

Không log toàn bộ body vào production log chỉ để dễ debug; dữ liệu có thể lớn, khó đọc và chứa thông tin cần bảo vệ.

## 11. Các lỗi phổ biến và cách sửa

**“BytesMessage là file upload.”** Sai. Nó là một loại body của JMS message. File lớn thường nên lưu ngoài broker và chỉ gửi tham chiếu có metadata/chính sách truy cập.

**“writeBytes sẽ tự ghi length và schema.”** Sai. Nó ghi byte được cung cấp; nếu format cần length/version, ứng dụng phải xác định và mã hóa chúng.

**“Tạo message rồi có thể readBytes ngay.”** Sai. Message mới là write-only. Phải `reset()` để chuyển sang read-only, hoặc đọc message nhận từ provider vốn đã ở read-only.

**“reset() xóa body.”** Sai. `reset()` đặt lại vị trí đọc và chuyển read-only. `clearBody()` mới xóa body để ghi lại.

**“getBodyLength() trả int.”** Sai. Nó trả `long`; cấp phát mảng phải kiểm tra giới hạn trước khi ép sang `int`.

**“readBytes(buffer) luôn lấp đầy buffer.”** Sai. Phương thức trả số byte đã sao chép; có thể nhỏ hơn buffer và sẽ trả -1 ở cuối stream.

**“writeUTF bằng UTF-8 thô của file.”** Sai. `writeUTF/readUTF` dùng modified UTF-8 của API; khi định dạng ngoài yêu cầu UTF-8 bytes, nên dùng `StandardCharsets.UTF_8` và giao ước length.

**“Chỉ cần set contentType là mọi consumer giải mã được.”** Sai. Property là metadata; consumer vẫn cần codec/schema tương ứng và kiểm tra dữ liệu thực tế.

**“Khi converter đã biến thành byte[] thì không tốn bộ nhớ.”** Sai. Chuyển `BytesMessage` thành `byte[]` thường cấp phát toàn body. Chặn size từ raw message hoặc chọn cơ chế truyền file phù hợp.

**“BytesMessage loại trừ nhận trùng.”** Sai. Format không quyết định delivery/ack; cần idempotency và transaction đúng phạm vi.

**“Byte nhị phân có thể in như String để xem mà không ảnh hưởng gì.”** Không nên. Việc decode bằng charset sai có thể làm mất thông tin khi encode trở lại, còn log raw binary có thể lộ dữ liệu.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Trong `BytesMessage`, `writeBytes(new byte[]{0x01, 0x02})` có tự thêm JSON field names hoặc độ dài payload không?

**Trả lời:** Không. Nó ghi đúng các byte của mảng. Nếu hợp đồng cần header/length, producer phải mã hóa riêng.

**Câu 2.** Sau `session.createBytesMessage()`, gọi `getBodyLength()` ngay có hợp lệ không?

**Trả lời:** Không khi body vẫn ở write-only. `getBodyLength()` cần trạng thái read-only; có thể gọi `reset()` sau khi ghi, hoặc trên message đã được nhận.

**Câu 3.** `reset()` và `clearBody()` khác nhau điều gì?

**Trả lời:** `reset()` chuyển read-only, đặt cursor về đầu và giữ body. `clearBody()` xóa body, đưa về write-only, giữ nguyên properties.

**Câu 4.** Gọi `readBytes(buffer)` với buffer 8 byte nhưng chỉ còn 3 byte; phải xử lý như thế nào?

**Trả lời:** Dựa trên số byte trả về (3), chỉ sử dụng `buffer[0..3)`. Lần đọc tiếp theo khi đã hết stream trả -1; không xử lý phần còn lại của buffer như dữ liệu mới.

**Câu 5.** Một frame có magic 2 byte, version 1 byte, length 4 byte, payload 5 byte. Tổng body bao nhiêu byte?

**Trả lời:** 12 byte, theo chính định dạng ứng dụng đã định nghĩa; không phải overhead tự động của JMS.

**Câu 6.** Vì sao nên có `schemaVersion` khi dùng protobuf hoặc binary custom?

**Trả lời:** Decoder cần biết cách hiểu layout và xử lý tương thích phiên bản; `BytesMessage` tự nó không mang schema nghiệp vụ.

**Câu 7.** Spring `JmsTemplate.convertAndSend("binary.jobs", byte[])` thường tạo message type nào với converter mặc định?

**Trả lời:** `BytesMessage` qua `SimpleMessageConverter`. Nếu thay converter bằng custom implementation, phải xác minh lại.

**Câu 8.** Một message gửi chứa 200 MiB nhưng listener nhận `byte[]` và sau đó kiểm tra “độ dài phải nhỏ hơn 1 MiB”. Kiểm tra này có phòng tránh cấp phát lớn từ converter không?

**Trả lời:** Không chắc. Converter có thể tạo mảng 200 MiB **trước** khi vào method. Với policy hạn kích thước, cần chặn tại broker/client và/hoặc tiếp nhận raw `BytesMessage`, kiểm tra `getBodyLength()` trước khi lấy toàn body; cân nhắc tham chiếu object storage.

**Câu 9.** Consumer lưu dữ liệu nhị phân thành công rồi chết trước JMS ack; liệu message có thể quay lại không?

**Trả lời:** Có. Đây là vấn đề acknowledgment/transaction, độc lập với format; cần idempotency trên business key ổn định.

## Ghi nhớ

`BytesMessage` là **một luồng byte không tự mô tả ngữ nghĩa nghiệp vụ**. Dùng nó khi producer và consumer có hợp đồng rõ ràng về binary format. Hãy phân biệt trạng thái write-only/read-only, đọc đúng số byte được trả về, kiểm soát kích thước trước khi cấp phát và định nghĩa schema/version/charset/byte order bằng văn bản và test. Trong Spring JMS, `JmsTemplate` và `@JmsListener` giúp gửi nhận, còn độ tin cậy cuối cùng vẫn phụ thuộc broker, transaction, retry và logic xử lý trùng.

### Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `BytesMessage`, message body, gửi/nhận và các ví dụ `createBytesMessage/writeBytes/readBytes/getBody`.
- [Jakarta Messaging BytesMessage API](https://jakarta.ee/specifications/messaging/3.0/apidocs/jakarta/jms/BytesMessage.html): trạng thái read-only/write-only, `reset`, `clearBody`, primitive readers/writers và ngoại lệ.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate` và `SimpleMessageConverter` cho `byte[]`/`BytesMessage`.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, tham số raw JMS message và listener factory.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener container và xử lý message.