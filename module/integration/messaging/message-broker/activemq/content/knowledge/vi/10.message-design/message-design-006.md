# JSON, encoding và chuyển đổi kiểu dữ liệu giữa các ứng dụng

> **Chương:** Thiết kế thông điệp  
> **Bối cảnh:** ActiveMQ Classic/Artemis vận chuyển message bất đồng bộ giữa producer và consumer Java/JMS, JavaScript, Python hoặc các dịch vụ khác.  
> **Mục tiêu:** Thiết kế **payload JSON có hợp đồng kiểu dữ liệu rõ ràng**, mã hóa/giải mã đúng UTF-8 và chứng minh bên nhận tái tạo đúng ý nghĩa dữ liệu, kể cả khi hai ứng dụng dùng ngôn ngữ hoặc giao thức khác nhau.

## 1. Vấn đề thật: message đến broker thành công nhưng dữ liệu ở consumer bị sai

Một dịch vụ Java phát sự kiện thanh toán:

```json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "eventId": "evt-20261117-00042",
  "orderId": "9007199254740993",
  "occurredAt": "2026-11-17T07:30:00Z",
  "currency": "USD",
  "totalAmount": "129.90",
  "quantity": 2,
  "customerNote": "Giao tới quán Cà phê ☕",
  "promotionCode": null
}
```

Broker có thể lưu và giao message đúng, nhưng hệ nhận vẫn có thể sai:

- JavaScript chuyển `orderId` thành `Number` và làm tròn `9007199254740993` thành `9007199254740992`.
- Một service parse `totalAmount` thành số dấu phẩy động, rồi tính tiền bằng kiểu `double`.
- Consumer đọc chuỗi UTF-8 bằng charset khác, làm `Cà phê ☕` biến thành ký tự lỗi.
- Service A coi `promotionCode: null` là “không áp dụng mã”; service B lại coi field vắng mặt là lỗi schema và tự gán mã mặc định.
- Service C deserialize timestamp thành giờ địa phương nhưng bỏ offset `Z`, dẫn đến lệch thời điểm.
- Producer phát JSON dạng `TextMessage`; consumer viết cho `BytesMessage` dùng protocol khác không nhận đúng loại body.

Các vấn đề này thuộc **hợp đồng payload, encoding và type mapping**; đổi số broker hoặc thêm consumer không chữa được nguyên nhân.

Mục tiêu thực tế phải là **semantic round-trip**:

```text
Domain object (Java)
  -> JSON model + schema
  -> Unicode text
  -> UTF-8 bytes (nếu chọn binary payload)
  -> JMS Message / broker transport
  -> UTF-8 decode
  -> JSON parser + type validation
  -> Domain object (JavaScript/Python/Java)
```

**Bảo toàn byte** và **bảo toàn ý nghĩa** là hai tiêu chí khác nhau. JSON có thể được format lại, thay thứ tự field hoặc escape Unicode khác mà vẫn tương đương về cấu trúc; nhưng thay `"129.90"` thành `129.9` có thể làm mất quy ước độ chính xác của hợp đồng tiền tệ.

## 2. Phải thống nhất contract trước khi chọn thư viện JSON

Không nên định nghĩa contract bằng câu “body là JSON” rồi để các service tự đoán loại dữ liệu. Hãy mô tả ít nhất các thuộc tính:

| Trường | JSON type | Ví dụ | Quy tắc bên nhận |
| --- | --- | --- | --- |
| `eventType` | string | `"OrderPlaced"` | Enum có tập giá trị được hỗ trợ |
| `schemaVersion` | integer trong miền an toàn | `1` | Xác định schema/handler, không tự đoán |
| `eventId` | string | `"evt-..."` | Định danh ổn định để chống xử lý trùng |
| `orderId` | string | `"9007199254740993"` | **Định danh**, không được tính toán như số |
| `occurredAt` | string | `"2026-11-17T07:30:00Z"` | ISO 8601/RFC 3339 có offset, chuẩn hóa UTC khi cần |
| `currency` | string | `"USD"` | Mã tiền tệ theo quy ước thống nhất |
| `totalAmount` | string | `"129.90"` | Decimal chính xác, thỏa định dạng và scale |
| `quantity` | integer | `2` | Giá trị nguyên trong khoảng nghiệp vụ |
| `customerNote` | string | `"Cà phê ☕"` | Unicode, giới hạn độ dài, không tự biến đổi ký tự |
| `promotionCode` | string hoặc null | `null` | Null có nghĩa tường minh; phân biệt field bị thiếu |

Ví dụ trên chọn **string cho ID lớn và tiền tệ** để tránh ép kiểu ngoài ý muốn trong JavaScript/JSON tooling. Đây là quyết định của **hợp đồng ứng dụng**, không phải hạn chế bắt buộc của cú pháp JSON.

### 2.1. Quy tắc thiết kế field

1. Đặt tên và kiểu field ổn định; ví dụ thống nhất `camelCase`, không lúc `order_id` lúc `orderId`.
2. Mỗi field phải có mô tả về **đơn vị, miền giá trị, nullability và giới hạn độ dài**.
3. Với money, chọn **decimal string + currency** hoặc **integer minor units + quy định scale**. Không truyền số `double` rồi kỳ vọng mọi hệ thống tái tạo đúng giá trị thập phân.
4. Với thời gian, chọn **một chuẩn timestamp có offset** và quy định cách xử lý độ chính xác giây/millisecond/nanosecond; không truyền chuỗi mơ hồ như `17/11/26 14:30`.
5. Với ID, dù ID chỉ chứa chữ số, hãy giữ kiểu `string` nếu mục đích là **so sánh định danh**.
6. Quy định field nào bắt buộc, field nào tùy chọn, ý nghĩa của `null` và giá trị mặc định.
7. Các service phải kiểm tra `schemaVersion` và từ chối/định tuyến vào xử lý tương thích khi gặp bản chưa hỗ trợ.

### 2.2. JSON chỉ có một tập kiểu nền tảng nhỏ

Theo RFC 8259, các kiểu JSON là **object, array, string, number, boolean, null**. JSON không có kiểu native dành riêng cho:

- Java `BigDecimal`, `BigInteger` hay `UUID`.
- Java `Instant`/`LocalDateTime` hoặc đối tượng ngày của JavaScript.
- Binary byte array.
- Enum có version và semantic cụ thể.
- Monetary amount kèm currency và quy tắc làm tròn.
- Integer 64 bit có bảo đảm portable qua mọi ngôn ngữ.

Vì vậy cần một **quy ước ánh xạ kiểu** được mọi consumer tuân theo. Ví dụ `occurredAt` là string có định dạng RFC 3339; nó **không tự** là một đối tượng thời gian sau `JSON.parse`.

## 3. Chuyển đổi number: lỗi khó phát hiện nhất giữa Java và JavaScript

### 3.1. JSON number không có “kiểu long” chung

JSON có cú pháp number, nhưng mỗi parser ánh xạ khác nhau:

| Hệ nhận | Cách parse thường gặp | Rủi ro |
| --- | --- | --- |
| Java + Jackson | `int`, `long`, `BigInteger`, `BigDecimal` hoặc `double` tùy target/configuration | Tràn miền, mất scale/độ chính xác nếu ép về `double` |
| JavaScript | `Number` (IEEE-754 binary64) | Không biểu diễn chính xác mọi integer lớn; sai số thập phân |
| Python | `int` độ dài tùy ý; `float` binary64 mặc định cho phân số | Số nguyên thường an toàn; số thập phân có thể bị làm tròn nếu parse `float` |
| Go / thư viện generic | Thường mặc định `float64` khi decode vào `interface{}` | Mất chính xác số nguyên lớn, cần decoder/kiểu cụ thể |

Trong JavaScript, các integer chỉ được bảo đảm chính xác khi nằm trong khoảng:

\[
-(2^{53}-1) \le n \le 2^{53}-1
\]

tức từ `-9007199254740991` đến `9007199254740991`.

Ví dụ:

```javascript
const wrong = JSON.parse('{"orderId":9007199254740993}');
console.log(wrong.orderId);
// Có thể in 9007199254740992 vì Number mất độ chính xác.

const correct = JSON.parse('{"orderId":"9007199254740993"}');
const id = BigInt(correct.orderId);
console.log(id.toString()); // "9007199254740993"
```

**Lưu ý:** `JSON.stringify` không serialize trực tiếp `BigInt` trong JavaScript; nếu định dạng hợp đồng là string, hãy xuất `bigIntValue.toString()`.

### 3.2. Tiền tệ: `0.1 + 0.2` không phải 0.3 chính xác theo binary64

```javascript
console.log(0.1 + 0.2 === 0.3); // false
```

Với tiền tệ, thường chọn một trong hai contract:

**A. Decimal string với scale tường minh**

```json
{"currency":"USD","totalAmount":"129.90"}
```

- Java: `new BigDecimal("129.90")`.
- Python: `Decimal("129.90")`.
- JavaScript: thư viện decimal chính xác, hoặc parse có kiểm tra thành `BigInt` của đơn vị nhỏ nhất nếu scale cố định.
- Không dùng `new BigDecimal(0.1)` trong Java vì đối số đã là số nhị phân không chính xác; dùng constructor từ **string** hoặc `BigDecimal.valueOf(...)` tùy nguồn.

**B. Minor units nguyên với giới hạn rõ ràng**

```json
{"currency":"USD","totalMinorUnits":"12990","minorUnitScale":2}
```

Ví dụ `12990` cents ứng với `129.90` USD. Để giữ đúng qua mọi runtime, dùng string cho minor units khi giá trị có thể vượt miền integer an toàn của JavaScript. **Không giả định mọi tiền tệ có 2 chữ số thập phân**; scale phải được định nghĩa bởi contract hoặc chính sách tiền tệ.

### 3.3. Đừng dựa vào việc parser “tự ép kiểu”

Phân biệt:

```json
{"quantity": 2}
```

với:

```json
{"quantity": "2"}
```

Hai giá trị **khác type**, dù một số thư viện cho phép coercion. Nếu contract yêu cầu integer thì nên **reject** `"2"`, không âm thầm đổi thành `2`. Ngược lại `orderId` là định danh string thì không tự ép sang number chỉ vì toàn chữ số.

Bên nhận cần kiểm tra **kiểu trước rồi mới kiểm tra miền**, ví dụ integer, `1 ≤ quantity ≤ 10000`, không nhận số phân số `2.5` hoặc boolean.

## 4. Unicode và UTF-8: chuẩn hóa ranh giới byte

### 4.1. Tách string logic khỏi byte trên mạng

JSON text gồm các ký tự Unicode. Khi vận chuyển dưới dạng **bytes**, hệ thống cần chọn encoding; với JSON trao đổi giữa các hệ thống mở, **UTF-8** là lựa chọn bắt buộc theo RFC 8259.

Chuỗi:

```text
Cà phê ☕
```

khi mã hóa UTF-8 gồm các byte theo quy tắc Unicode; ký tự ASCII thường dùng một byte, nhiều ký tự tiếng Việt dùng nhiều byte, emoji có thể dùng ba hoặc bốn byte tùy code point. Ví dụ ký tự `é` (U+00E9) là byte hex `C3 A9` trong UTF-8.

**Không** coi “một ký tự = một byte” hoặc “Java `String.length()` = số ký tự nhìn thấy”. Java `String` lưu các code unit UTF-16; emoji ngoài BMP có thể chiếm hai code unit, còn một grapheme hiển thị có thể gồm nhiều code point.

### 4.2. Chọn rõ điểm encode/decode

Trong Java:

```java
import java.nio.charset.StandardCharsets;

String json = "{\"note\":\"Cà phê ☕\"}";
byte[] utf8 = json.getBytes(StandardCharsets.UTF_8);

// Khi đọc payload bytes từ bên ngoài:
String restored = new String(utf8, StandardCharsets.UTF_8);
```

Đoạn trên minh họa round-trip dữ liệu **hợp lệ**. Để phát hiện byte UTF-8 sai thay vì âm thầm thay ký tự bằng `U+FFFD`, dùng decoder nghiêm ngặt:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] raw)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(raw))
            .toString();
}
```

Bên JavaScript nhận raw `Uint8Array` tương đương:

```javascript
const decoder = new TextDecoder("utf-8", { fatal: true });
const jsonText = decoder.decode(rawBytes);
const event = JSON.parse(jsonText);
```

Nếu thư viện đã trả về **chuỗi Unicode được decode đúng**, không encode/decode lại một cách tùy tiện. Đặc biệt không dùng charset mặc định của máy vì cùng một byte stream có thể bị hiểu khác trên hai host.

### 4.3. BOM, escape và chuẩn hóa Unicode

- JSON trao đổi giữa các hệ thống **không nên phát BOM** (Byte Order Mark). RFC 8259 yêu cầu generator không thêm BOM; parser có thể chọn bỏ qua BOM để tương thích. Đối với contract nghiêm ngặt, có thể từ chối UTF-8 BOM `EF BB BF` trước khi parse.
- `"Cà phê"` và `"C\u00e0 ph\u00ea"` tương đương về giá trị string sau JSON parse; escape là **cách biểu diễn JSON**, không phải encoding khác.
- Unicode cho phép các chuỗi có vẻ giống nhau nhưng byte khác nhau do dạng tổ hợp (*combining marks*). Nếu dùng string làm key định danh hoặc cần so sánh chữ ký, quy định có chuẩn hóa **NFC** trước khi tạo ID/hash hay không; không tự chuẩn hóa mọi nội dung người dùng khi contract không cho phép.
- Đừng parse JSON bằng cách tách dấu phẩy hoặc dấu nháy thủ công: chuỗi JSON có escaping và Unicode. Dùng JSON parser chuẩn.
- Với dữ liệu nhị phân thực sự (PDF/ảnh), không nhét byte trực tiếp vào JSON string; chọn **Base64** có mô tả encoding hoặc chuyển sang binary message có content type tương ứng.

### 4.4. Compression là vấn đề khác charset

Nếu payload lớn và dùng gzip:

```text
JSON object -> UTF-8 bytes -> gzip bytes -> broker -> gunzip -> UTF-8 decode -> JSON parse
```

Metadata phải phân biệt **content type `application/json`** và **content encoding `gzip`**. Consumer không được thử `new String(gzipBytes, UTF_8)` vì gzip bytes không phải JSON UTF-8.

Trong JMS, các application property như `payloadContentType`, `payloadCharset`, `payloadEncoding` chỉ là **quy ước tự thiết kế**, không phải bộ header chuẩn JMS được mọi bridge/protocol tự ánh xạ sang các header AMQP/STOMP/MQTT. Phải kiểm thử đường đi thực tế.

## 5. `TextMessage` và `BytesMessage`: chọn một hợp đồng vận chuyển

Cùng JSON có thể được đóng gói bằng hai cách chính:

| Tiêu chí | JMS `TextMessage` | JMS `BytesMessage` |
| --- | --- | --- |
| Body ứng dụng nhận | `String` Unicode qua `getText()` | `byte[]` đọc từ `readBytes(...)` |
| Encoding do code ứng dụng kiểm soát? | Không trực tiếp; provider mã hóa string thành wire format | **Có**: tự chọn `UTF-8`, gzip, framing |
| Phù hợp | Hai đầu cùng dùng JMS text semantics và broker/client tương thích | Muốn hợp đồng byte UTF-8 tường minh hoặc nhiều consumer/protocol |
| Rủi ro | Cross-protocol mapping có thể trả body khác kiểu dự kiến | Đọc sai charset, đọc thiếu bytes hoặc quên decompress |
| Quan trọng khi tích hợp | Test mapping `TextMessage` sang AMQP/STOMP body | Test raw bytes và metadata khi qua protocol bridge |

### 5.1. `TextMessage`: tiện nhưng không quy định byte trên wire

```java
TextMessage message =
        session.createTextMessage("{\"eventType\":\"OrderPlaced\"}");
message.setStringProperty("payloadContentType", "application/json");
producer.send(message);
```

Một JMS consumer tương thích gọi:

```java
Message incoming = consumer.receive(5_000);
if (!(incoming instanceof TextMessage)) {
    throw new IllegalStateException("Cần TextMessage");
}
String json = ((TextMessage) incoming).getText();
```

Ở đây ứng dụng đọc **Java String**, không cần gọi `new String(bytes, "UTF-8")`. Provider xử lý encoding bên dưới. Không suy luận rằng mọi AMQP client nhận cùng message sẽ thấy một AMQP `data` section UTF-8 hoặc cùng metadata mà không cần translation.

### 5.2. `BytesMessage`: contract byte tường minh

```java
String json = "{\"eventType\":\"OrderPlaced\"}";
byte[] raw = json.getBytes(StandardCharsets.UTF_8);

BytesMessage message = session.createBytesMessage();
message.writeBytes(raw);
message.setStringProperty("payloadContentType", "application/json");
message.setStringProperty("payloadCharset", "UTF-8");
producer.send(message);
```

Khi đọc, phải lấy **đủ số byte** từ `BytesMessage` và kiểm tra payload size trước khi cấp phát bộ nhớ. Một `readBytes(...)` có thể đọc chưa hết body; không giả định một lần read là đủ.

**Không đặt cả hai loại body vào một message.** Consumer cần thỏa thuận contract: `TextMessage` chứa JSON string hay `BytesMessage` chứa UTF-8 JSON bytes, thay vì tự thử các phép ép kiểu không kiểm soát.

### 5.3. Những message type khác không phù hợp làm mặc định liên ngôn ngữ

- `MapMessage` là convenience API JMS có mapping kiểu riêng; không phải JSON object phổ quát.
- `ObjectMessage` serialize Java object theo quy tắc provider/JVM, khó tương tác với JavaScript/Python và tiềm ẩn rủi ro deserialization khi đọc dữ liệu không tin cậy. Không dùng làm contract trao đổi nhiều ngôn ngữ.
- `StreamMessage` cũng có contract JMS riêng; không mặc nhiên là JSON array.

Khi cần nhiều runtime khác nhau, JSON text/UTF-8 bytes và schema rõ ràng thường dễ kiểm thử hơn Java serialization.

## 6. Phân biệt JSON body với JMS headers/properties

Một sự kiện có thể có:

```text
JMSMessageID          : broker/provider cấp
JMSCorrelationID      : giá trị tương quan request/response (nếu dùng)
JMSDestination        : queue/topic đích
application property  : eventType="OrderPlaced"
application property  : schemaVersion=1
application property  : payloadContentType="application/json"
Body                  : JSON chứa eventId, schemaVersion, eventType, dữ liệu...
```

### 6.1. Dùng metadata để route/observe, body để giữ sự thật nghiệp vụ

Ví dụ producer:

```java
BytesMessage message = session.createBytesMessage();
message.writeBytes(json.getBytes(StandardCharsets.UTF_8));
message.setStringProperty("eventType", "OrderPlaced");
message.setIntProperty("schemaVersion", 1);
message.setStringProperty("payloadContentType", "application/json");
message.setStringProperty("payloadCharset", "UTF-8");
message.setJMSCorrelationID("trace-17-abc");
producer.send(queue, message);
```

- `schemaVersion` trong body giúp payload độc lập và còn ý nghĩa khi export/replay từ file.
- `schemaVersion` trong property có thể giúp selector, routing hoặc observability; nếu có cả hai, **phải bằng nhau**.
- `JMSMessageID` là metadata do provider/broker cấp, không nên dùng thay `eventId` nghiệp vụ qua retry/migration.
- `JMSCorrelationID` phù hợp request/response hoặc trace tùy quy ước, không bắt buộc là business identity.
- JMS property có tập kiểu nhất định, khác JSON nested object/array; không cố đưa mọi payload vào headers.

**Lưu ý giao thức:** Artemis có thể nhận Core, AMQP 1.0, STOMP hoặc MQTT. Mapping message type, content-type và properties **phụ thuộc protocol adapter**. Một application property tự đặt tên `payloadContentType` không tự biến thành trường `content-type` chuẩn của AMQP 1.0 hoặc header STOMP `content-type`. Khi tích hợp chéo protocol, xác nhận bằng message trace và consumer thật.

### 6.2. Hợp đồng cho consumer

Consumer nên thực hiện theo thứ tự:

1. Kiểm tra **destination/loại message** mong đợi.
2. Kiểm tra kích thước và encoding/metadata theo contract, giải nén nếu có.
3. Decode UTF-8 (nếu body là bytes); từ chối malformed bytes.
4. Parse JSON và kiểm tra object top-level, required fields, type, miền giá trị.
5. Đối chiếu `schemaVersion`/`eventType` giữa body và application properties nếu cả hai có mặt.
6. Chuyển string decimal/date/ID sang kiểu nội bộ **có kiểm tra**.
7. Chỉ ack/commit khi đã xử lý nghiệp vụ thành công; với lỗi vĩnh viễn dùng chính sách retry có giới hạn/DLQ.

Đừng ack chỉ vì `JSON.parse` không ném exception: JSON có thể hợp lệ về cú pháp nhưng vi phạm hợp đồng, ví dụ `quantity: -3` hay `totalAmount: 1.2` (sai JSON type).

## 7. Thực hành ActiveMQ Artemis: phát JSON bytes UTF-8 và kiểm chứng round-trip

Lab dùng **JMS 2.0 / `javax.jms`**, **Apache ActiveMQ Artemis** Java client và **Jackson** cho JSON. Mục tiêu là kiểm chứng schema cơ bản, unicode, decimal string và giới hạn byte. Chạy broker Artemis có CORE listener tại `tcp://localhost:61616`, quyền tạo temporary queue và gửi/nhận. Có thể dùng credential theo biến môi trường cho broker bật authentication.

### 7.1. Dependency Maven minh họa

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.artemis</groupId>
        <artifactId>artemis-jms-client</artifactId>
        <version>2.50.0</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>
</dependencies>
```

Ví dụ dùng **`org.apache.artemis:artemis-jms-client`** từ Artemis 2.50.0; các release cũ dùng Maven groupId khác, còn ứng dụng `jakarta.jms` cần client/import Jakarta tương ứng. Chọn phiên bản đã được dự án kiểm tra bảo mật khi sử dụng ngoài lab.

### 7.2. Code Java đầy đủ: kiểm tra body trước khi ack

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import javax.jms.BytesMessage;
import javax.jms.Connection;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.TemporaryQueue;

import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;

public final class JsonUtf8JmsProbe {
    private static final int MAX_BYTES = 1024 * 1024;

    // Không chấp nhận key trùng trong một JSON object.
    private static final ObjectMapper JSON = new ObjectMapper(
            JsonFactory.builder()
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                .build());

    private static void require(boolean ok, String why) {
        if (!ok) throw new IllegalArgumentException(why);
    }

    private static byte[] readBody(BytesMessage message) throws Exception {
        long length = message.getBodyLength();
        require(length > 0 && length <= MAX_BYTES,
                "Payload vượt hạn mức hoặc rỗng: " + length);

        byte[] body = new byte[(int) length];
        int offset = 0;

        while (offset < body.length) {
            byte[] chunk = new byte[Math.min(8192, body.length - offset)];
            int read = message.readBytes(chunk);
            require(read > 0, "EOF trước khi đọc đủ body");
            System.arraycopy(chunk, 0, body, offset, read);
            offset += read;
        }
        return body;
    }

    private static JsonNode parseStrictUtf8(byte[] body) throws Exception {
        // JSON text interchange nên không có UTF-8 BOM.
        require(!(body.length >= 3
                && (body[0] & 0xff) == 0xef
                && (body[1] & 0xff) == 0xbb
                && (body[2] & 0xff) == 0xbf),
                "Không chấp nhận UTF-8 BOM");

        String text = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(body)).toString();

        JsonNode root = JSON.readTree(text);
        require(root != null && root.isObject(), "Root phải là JSON object");
        return root;
    }

    private static String requiredText(JsonNode root, String key) {
        JsonNode node = root.get(key);
        require(node != null && node.isTextual() && !node.asText().isBlank(),
                "Sai string field: " + key);
        return node.textValue();
    }

    private static void validate(JsonNode root) {
        JsonNode version = root.get("schemaVersion");
        require(version != null && version.isInt()
                && version.intValue() == 1,
                "Chỉ hỗ trợ schemaVersion=1");

        require("OrderPlaced".equals(requiredText(root, "eventType")),
                "Sai eventType");
        requiredText(root, "eventId");
        requiredText(root, "orderId");
        require("USD".equals(requiredText(root, "currency")),
                "Sai currency trong lab");

        JsonNode quantity = root.get("quantity");
        require(quantity != null && quantity.isIntegralNumber()
                && quantity.canConvertToInt()
                && quantity.intValue() >= 1
                && quantity.intValue() <= 10000,
                "Sai quantity");

        String amountText = requiredText(root, "totalAmount");
        require(amountText.matches("(0|[1-9][0-9]*)\\.[0-9]{2}"),
                "totalAmount cần đúng 2 chữ số thập phân");
        BigDecimal amount = new BigDecimal(amountText);
        require(amount.signum() >= 0, "Amount âm");

        Instant.parse(requiredText(root, "occurredAt"));

        JsonNode note = root.get("customerNote");
        require(note == null || note.isTextual(),
                "customerNote phải là string hoặc bị lược bỏ");
    }

    public static void main(String[] args) throws Exception {
        String url = args.length == 0
                ? "tcp://localhost:61616" : args[0];

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        String user = System.getenv("ARTEMIS_USER");
        String password = System.getenv("ARTEMIS_PASSWORD");
        Connection connection = user == null
                ? factory.createConnection()
                : factory.createConnection(user, password);

        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            TemporaryQueue queue = session.createTemporaryQueue();

            ObjectNode order = JSON.createObjectNode();
            order.put("eventType", "OrderPlaced");
            order.put("schemaVersion", 1);
            order.put("eventId", "evt-" + UUID.randomUUID());
            order.put("orderId", "9007199254740993");
            order.put("occurredAt", "2026-11-17T07:30:00Z");
            order.put("currency", "USD");
            order.put("totalAmount", "129.90");
            order.put("quantity", 2);
            order.put("customerNote", "Giao tới quán Cà phê ☕");

            String jsonText = JSON.writeValueAsString(order);
            byte[] utf8 = jsonText.getBytes(StandardCharsets.UTF_8);

            BytesMessage outbound = session.createBytesMessage();
            outbound.writeBytes(utf8);
            outbound.setStringProperty(
                    "payloadContentType", "application/json");
            outbound.setStringProperty("payloadCharset", "UTF-8");
            outbound.setStringProperty("eventType", "OrderPlaced");
            outbound.setIntProperty("schemaVersion", 1);

            MessageProducer producer = session.createProducer(queue);
            MessageConsumer consumer = session.createConsumer(queue);
            connection.start();

            producer.send(outbound);
            Message incoming = consumer.receive(5_000);
            require(incoming instanceof BytesMessage,
                    "Không nhận BytesMessage");

            require("application/json".equals(incoming.getStringProperty(
                    "payloadContentType")), "Sai content type");
            require("UTF-8".equals(incoming.getStringProperty(
                    "payloadCharset")), "Sai charset");

            JsonNode decoded = parseStrictUtf8(
                    readBody((BytesMessage) incoming));
            validate(decoded);

            require(incoming.getIntProperty("schemaVersion")
                    == decoded.get("schemaVersion").intValue(),
                    "Header/schemaVersion không khớp");
            require("9007199254740993".equals(
                    decoded.get("orderId").textValue()),
                    "orderId bị mất chính xác");

            System.out.println("PASS JSON UTF-8 round-trip");
            System.out.println(decoded.toPrettyString());
        } finally {
            connection.close();
        }
    }
}
```

**Kỳ vọng:** log `PASS JSON UTF-8 round-trip`, giữ nguyên `"9007199254740993"`, `"129.90"` và chuỗi tiếng Việt có emoji. `TemporaryQueue` tách bài lab khỏi dữ liệu nghiệp vụ và được xóa khi connection đóng.

**Giới hạn của ví dụ:** `AUTO_ACKNOWLEDGE` dùng để demo vòng phát/nhận; message có thể đã được JMS ack khi `receive()` hoàn tất, **trước khi** hàm `validate` chạy. Trong consumer sản xuất, chọn transaction hoặc acknowledgment phù hợp và commit/ack **sau khi** parse, validate và xử lý nghiệp vụ thành công. Đồng thời phải có xử lý lỗi và DLQ cho payload không thể sửa bằng retry.

Với broker áp dụng bảo mật, `ARTEMIS_USER` và `ARTEMIS_PASSWORD` phải có trong môi trường thử nghiệm hoặc thay bằng phương thức cấp credential của hệ thống. Nếu không cho tạo temporary destination, cấu hình một queue lab riêng ở broker và dùng tên cụ thể.

### 7.3. Cấu hình queue cố định nếu muốn thử Java → JavaScript qua AMQP

Nếu cần hai process dùng **cùng một queue vật lý**, một fragment `broker.xml` của Artemis:

```xml
<!-- Fragment trong <addresses> của Artemis broker.xml -->
<address name="lab.json.orders">
    <anycast>
        <queue name="lab.json.orders" durable="true"/>
    </anycast>
</address>
```

Ví dụ acceptor protocol ở lab:

```xml
<!-- Fragment trong <acceptors>; hai cổng minh họa -->
<acceptor name="core">
    tcp://127.0.0.1:61616?protocols=CORE
</acceptor>
<acceptor name="amqp">
    tcp://127.0.0.1:5672?protocols=AMQP
</acceptor>
```

Java dùng Artemis JMS client (Core wire protocol) để gửi `BytesMessage` đến queue này; service khác dùng AMQP 1.0 client để nhận. Khi chuyển protocol, cần xác nhận mapping **JMS message body/type, application properties, content-type** trên Artemis đang dùng. Một địa chỉ/queue cùng tên không tự bảo đảm thư viện phía AMQP expose payload ở đúng dạng `Uint8Array`; adapter phải trích xuất **binary body** theo contract đã thống nhất.

Không đưa code kiểm thử lên queue production: consumer test có thể lấy mất message của worker thật.

## 8. Bên nhận JavaScript: validate trước khi đổi kiểu

Giả sử một AMQP client adapter đã lấy được **raw JSON bytes** từ `lab.json.orders` (việc lấy body cụ thể phụ thuộc SDK). Phần xử lý hợp đồng trong Node.js có thể viết độc lập:

```javascript
function decodeOrderPlaced(rawBytes) {
  const text = new TextDecoder("utf-8", { fatal: true })
    .decode(rawBytes);
  const event = JSON.parse(text);

  if (event === null || Array.isArray(event) ||
      typeof event !== "object") {
    throw new Error("JSON root phải là object");
  }

  if (event.schemaVersion !== 1 ||
      event.eventType !== "OrderPlaced") {
    throw new Error("Không hỗ trợ schema/eventType");
  }

  if (typeof event.orderId !== "string" ||
      !/^[0-9]+$/.test(event.orderId)) {
    throw new Error("orderId phải là string chữ số");
  }

  if (!Number.isSafeInteger(event.quantity) ||
      event.quantity < 1 || event.quantity > 10000) {
    throw new Error("quantity không hợp lệ");
  }

  if (typeof event.totalAmount !== "string") {
    throw new Error("totalAmount phải là decimal string");
  }
  const m = /^(0|[1-9][0-9]*)\.([0-9]{2})$/
    .exec(event.totalAmount);
  if (!m) throw new Error("Sai định dạng amount");

  // Đếm chính xác theo cents, không dùng Number để tính tiền.
  const amountInCents = BigInt(m[1]) * 100n + BigInt(m[2]);

  if (typeof event.occurredAt !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T/.test(event.occurredAt)) {
    throw new Error("occurredAt cần timestamp có format rõ ràng");
  }
  // Phải dùng parser/validator RFC 3339 thật trước khi ghi DB.

  return {
    eventId: event.eventId,
    orderId: event.orderId,
    amountInCents,
    occurredAt: event.occurredAt
  };
}

// Demo độc lập với SDK AMQP:
const payload = new TextEncoder().encode(
  '{"eventType":"OrderPlaced","schemaVersion":1,' +
  '"orderId":"9007199254740993","totalAmount":"129.90",' +
  '"quantity":2,"occurredAt":"2026-11-17T07:30:00Z"}'
);
const parsed = decodeOrderPlaced(payload);
console.log(parsed.orderId);                // 9007199254740993
console.log(parsed.amountInCents.toString()); // 12990
```

Đoạn Node.js **không tự kết nối Artemis**; nó là phần **payload adapter** cần cắm sau callback nhận message của thư viện AMQP được chọn. Điều này giúp phép thử type mapping không bị che bởi vấn đề kết nối/settlement. Khi tích hợp, chỉ **ack/accept** delivery sau khi validation và xử lý nghiệp vụ thành công; với lỗi schema cố định, phân loại riêng để tránh redelivery vô hạn.

**Chú ý:** Regex trong ví dụ chỉ kiểm tra một phần định dạng timestamp; validation thời gian thật cần kiểm tra ngày hợp lệ, offset và phạm vi thời gian. `Date.parse` có những hành vi khác nhau theo format; ứng dụng nên tuân theo RFC 3339 và dùng thư viện đã chọn để tránh lỗi diễn giải timezone.

## 9. Schema: phát hiện lỗi sớm và nâng cấp có kiểm soát

### 9.1. JSON Schema kiểm tra type và contract tối thiểu

Ví dụ schema theo JSON Schema Draft 2020-12:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/order-placed/v1",
  "type": "object",
  "required": [
    "eventType",
    "schemaVersion",
    "eventId",
    "orderId",
    "occurredAt",
    "currency",
    "totalAmount",
    "quantity"
  ],
  "properties": {
    "eventType": { "const": "OrderPlaced" },
    "schemaVersion": { "const": 1 },
    "eventId": { "type": "string", "minLength": 1 },
    "orderId": { "type": "string", "pattern": "^[0-9]+$" },
    "occurredAt": { "type": "string", "format": "date-time" },
    "currency": { "enum": ["USD"] },
    "totalAmount": {
      "type": "string",
      "pattern": "^(0|[1-9][0-9]*)\\.[0-9]{2}$"
    },
    "quantity": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10000
    },
    "customerNote": { "type": "string", "maxLength": 2000 },
    "promotionCode": { "type": ["string", "null"] }
  },
  "additionalProperties": true
}
```

- `required` phân biệt **field vắng mặt** với `null`. Nếu `promotionCode` không required, thiếu field là hợp lệ theo schema này; ứng dụng phải quy định cách hiểu.
- `additionalProperties: true` cho phép các field mới mà consumer cũ bỏ qua. Nếu contract nghiêm ngặt yêu cầu từ chối mọi field lạ, đổi thành `false` nhưng việc tiến hóa schema sẽ khó hơn.
- `format: "date-time"` trong Draft 2020-12 có thể chỉ là **annotation**; validator phải bật hỗ trợ format assertion nếu muốn lỗi ngày giờ bị phát hiện.
- Schema này minh họa USD; production cần quản lý danh sách currency và quy tắc scale theo nghiệp vụ, thay vì cố định một loại tiền.

JSON Schema xác nhận hình dạng dữ liệu; validation nghiệp vụ (mã đơn hàng tồn tại, tổng tiền đúng, quyền tenant) là lớp khác.

### 9.2. Quy tắc tiến hóa schema

| Thay đổi | Tương thích với consumer cũ? | Hướng triển khai |
| --- | --- | --- |
| Thêm field **tùy chọn** có default hợp lý | Thường có, nếu consumer bỏ qua unknown fields | Kiểm tra consumer chấp nhận field lạ |
| Đổi `totalAmount` từ string thành number | **Breaking** | Tăng `schemaVersion`, viết adapter |
| Đổi `orderId` từ string thành number | **Breaking và mất precision** | Không đổi ngầm; giữ string |
| Đổi ý nghĩa của `promotionCode: null` | Có thể breaking dù type không đổi | Ghi contract mới, version |
| Đổi `occurredAt` từ UTC string sang số epoch milliseconds | Breaking | Dùng version mới và migrate có kiểm tra |
| Thêm giá trị mới cho `eventType`/enum | Có thể breaking với consumer dùng exhaustive switch | Quy định unknown enum policy |
| Đổi tên `customerNote` | Breaking nếu field bắt buộc | Hỗ trợ chuyển tiếp hoặc version rõ |

Cách rollout an toàn cho message bất đồng bộ:

1. Xác định các consumer đang đọc version nào.
2. Triển khai consumer hỗ trợ phiên bản mới **trước khi** producer phát payload mới, nếu cần tương thích hai chiều.
3. Có thể **dual-read** v1/v2 với validator riêng; không silently parse bằng một DTO rồi mặc định unknown field.
4. Phát `schemaVersion=2` khi thay đổi breaking, có metric nhận diện version chưa hỗ trợ.
5. Kiểm thử cả message **đang tồn trong queue/DLQ** ở version cũ trước khi xóa nhánh xử lý v1.

Khi replay message từ DLQ, **đừng dùng decoder mới một cách mặc định** nếu payload còn là version cũ; handler phải chọn đúng schema.

## 10. Null, missing, enum và kiểu collection

### 10.1. Ba trạng thái khác nhau của một thuộc tính

```json
{}
```

```json
{"promotionCode": null}
```

```json
{"promotionCode": ""}
```

Ba payload trên có thể mang ý nghĩa khác nhau:

- **Missing:** producer chưa biết trường này, hoặc client cũ chưa gửi.
- **Null:** producer chủ động nói “không có giá trị”.
- **Empty string:** có mặt nhưng là chuỗi rỗng (có thể không hợp lệ).

Trong Java, DTO mapping không phân biệt được missing và explicit null nếu chỉ dùng trường `String` mặc định `null`. Khi contract cần phân biệt, dùng `JsonNode.has(...)` và `JsonNode.get(...).isNull()` hoặc kiểu wrapper hỗ trợ presence.

### 10.2. Boolean, enum và array phải giữ type

```json
{
  "isGift": false,
  "fulfillment": "DELIVERY",
  "items": [
    {"sku":"SKU-1","quantity":2},
    {"sku":"SKU-2","quantity":1}
  ]
}
```

- `false` khác `"false"` và khác `0`.
- `"DELIVERY"` phải được kiểm tra trong tập enum được hỗ trợ; đừng âm thầm map unknown thành default nguy hiểm.
- `items` phải là **array**; từng phần tử phải là object hợp lệ, không nhận `null` lẫn trong mảng nếu schema cấm.
- Với map/object có key động, cần giới hạn số entry, độ sâu và kích thước để tránh payload cực lớn.

### 10.3. Unicode trong property và key

Tên JSON key có thể chứa Unicode, nhưng với hợp đồng công khai giữa nhiều runtime nên dùng key ASCII ổn định (`eventId`, `customerNote`); **giá trị string** vẫn hỗ trợ tiếng Việt và đa ngôn ngữ. Nếu key được dùng để map DTO hoặc query, tránh thay đổi chính tả/chuẩn hóa key một cách vô tình.

## 11. Kiểm thử dữ liệu xuyên ứng dụng: đừng chỉ test “nhận được message”

### 11.1. Ma trận kiểm thử tối thiểu

| Test case | Payload / điều kiện | Kỳ vọng |
| --- | --- | --- |
| Unicode tiếng Việt và emoji | `"Cà phê ☕"` | Đọc lại đúng code point và hiển thị |
| Integer vượt JavaScript safe range | `orderId="9007199254740993"` | Vẫn là string, không bị làm tròn |
| Decimal có số 0 cuối | `"129.90"` | Parse thành giá trị chính xác và scale theo contract |
| Sai kiểu number | `totalAmount: 129.90` | **Reject** nếu schema yêu cầu string |
| Sai kiểu integer | `quantity: "2"` hoặc `2.5` | **Reject**, không ép ngầm |
| Field null/missing | `promotionCode: null`, không có key | Phân biệt theo quy ước |
| Timestamp có offset | `"2026-11-17T14:30:00+07:00"` | Quy đổi cùng instant với `"2026-11-17T07:30:00Z"` |
| Timestamp không có timezone | `"2026-11-17T14:30:00"` | Reject nếu contract yêu cầu offset |
| Invalid UTF-8 | Body chứa chuỗi byte sai | Decoder nghiêm ngặt báo lỗi |
| UTF-8 BOM | Body bắt đầu `EF BB BF` | Tuân theo policy đã chọn; lab reject |
| JSON duplicate key | `{"quantity":1,"quantity":9}` | Reject; không để parser “last wins” im lặng |
| JSON root sai | `[]` hoặc `"hello"` | Reject nếu contract yêu cầu object |
| Compression mismatch | Header gzip nhưng body chưa gzip | Detect, không parse bytes như text |
| Schema mới chưa hỗ trợ | `schemaVersion=99` | Reject/route đến luồng xử lý phù hợp, có metric |
| Body và header mâu thuẫn | Property version=1, body version=2 | Reject vì contract không nhất quán |

### 11.2. Kiểm thử thực sự qua broker và protocol

Để chứng minh liên thông, tạo các phép thử riêng biệt:

1. Java Artemis JMS producer → Java Artemis JMS consumer: kiểm tra serializer/validator cơ bản.
2. Java Artemis JMS producer (Core) → consumer AMQP 1.0 của ngôn ngữ khác trên **cùng queue Artemis**: kiểm tra body type, content type, Unicode và numeric contract.
3. Consumer ngôn ngữ khác phát lại cùng payload → Java consumer: phát hiện JSON serializer thay đổi biểu diễn và date/decimal mapping.
4. Tạm ngắt consumer, gửi message persistent, kết nối lại rồi parse: kiểm tra encoding **không thay đổi qua lưu/đọc broker**.
5. Đưa payload lỗi vào queue thử nghiệm: xác nhận phân loại poison message, retry có giới hạn và DLQ theo policy; không tái gửi vô hạn một JSON vốn sai schema.

Ghi lại **eventId, schemaVersion, content-type, size bytes, checksum payload trong lab** và kết quả validation. Đừng log nguyên body nếu có PII hoặc credential. Dùng event ID ổn định để đối chiếu số đã phát, đã xử lý, bị từ chối và đang nằm trong DLQ.

### 11.3. Byte equality không phải tiêu chí duy nhất

Hai producer có thể tạo:

```json
{"quantity":2,"eventType":"OrderPlaced"}
```

và:

```json
{"eventType":"OrderPlaced","quantity":2}
```

Cả hai có cùng giá trị JSON object dù byte và hash thô khác nhau. Nếu cần ký số/dedup dựa trên payload, hãy định nghĩa **canonical JSON** hoặc ký trên field/business ID đã chuẩn hóa, không hash chuỗi serializer tùy ý rồi kỳ vọng trùng giữa các ngôn ngữ.

Nếu muốn test **byte-for-byte** khi truyền `BytesMessage` qua broker, hãy đo raw bytes trước/sau; để test **ngữ nghĩa**, parse/validate JSON rồi so sánh các giá trị theo contract, nhất là decimal string, datetime và ID lớn.

## 12. Xử lý lỗi JSON trong consumer, không biến DLQ thành bãi retry vô hạn

Phân loại lỗi:

| Loại lỗi | Ví dụ | Hành động điển hình |
| --- | --- | --- |
| **Transport tạm thời** | Mất kết nối broker/DB | Retry có backoff, giữ semantics ack/transaction |
| **Encoding vĩnh viễn** | Invalid UTF-8/BOM bị cấm | Ghi metric, tách message lỗi, DLQ/quarantine |
| **JSON syntax vĩnh viễn** | Thiếu dấu ngoặc, duplicate key theo policy | Không retry vô hạn; DLQ/quarantine |
| **Schema/type mismatch** | Amount là number thay vì string | DLQ/quarantine, sửa producer hoặc adapter |
| **Version chưa hỗ trợ** | `schemaVersion=3` | Route đúng handler hoặc quarantine và báo nâng cấp |
| **Business validation** | `quantity=-1`, currency không hỗ trợ | Reject có mã lỗi rõ ràng |
| **Lỗi downstream tạm thời** | DB timeout, rate limit | Retry giới hạn với idempotency |

Mẫu xử lý:

```text
receive message
  -> giới hạn size
  -> decode UTF-8 nghiêm ngặt
  -> parse JSON
  -> validate schema & business types
      +-- invalid: ghi reason + eventId -> quarantine/DLQ theo policy
      |
      +-- valid: xử lý idempotent -> commit/ack
                                   |
                              lỗi tạm thời -> rollback/retry có giới hạn
```

**Tránh cách làm:** Mọi exception đều `rollback()` vô hạn. Một payload `"quantity":"abc"` sẽ không tự biến thành số sau 100 lần retry, nhưng có thể chiếm tài nguyên broker/consumer và làm trễ message tốt.

Đối với xử lý đồng bộ với JMS transaction, cần bảo đảm bước gửi sang DLQ/quarantine và ack message gốc tuân theo chính sách giao dịch/độ tin cậy phù hợp; không “nuốt” lỗi rồi ack khi chưa giữ được bản lỗi cần điều tra.

## 13. Bảo mật và giới hạn tài nguyên khi parse JSON

Payload từ broker không mặc nhiên đáng tin: quyền publish có thể sai, ứng dụng producer lỗi hoặc dữ liệu đi qua nhiều bridge. Một số biện pháp thiết yếu:

- **Giới hạn kích thước byte trước khi parse**; ví dụ lab 1 MiB. Hạn mức thực tế dựa trên SLA, memory và message size của broker.
- Giới hạn **nesting depth**, số phần tử array/map, độ dài string và tổng số event trong batch. Parser có thể cấp phát rất nhiều object cho JSON nhỏ nhưng lồng sâu.
- Từ chối duplicate key nếu duplicate làm thay đổi ý nghĩa bảo mật/nghiệp vụ.
- Tắt các cơ chế deserialize tùy ý theo tên class từ payload nếu không có allowlist và lý do cụ thể; tránh polymorphic type injection.
- Kiểm tra loại thông điệp, schema version và field ID trước khi gọi API nhạy cảm.
- Không nhét thông tin bí mật, access token hoặc dữ liệu cá nhân vào message/log ngoài phạm vi được phép.
- Đặt quyền gửi/nhận tại Artemis address/queue; JSON Schema chỉ kiểm tra **hình dạng dữ liệu**, không thay thế authorization.

JSON hợp lệ vẫn có thể chứa dữ liệu độc hại đối với nơi sử dụng tiếp theo (SQL query, HTML, command argument). Việc parse JSON không thay cho escaping và parameterization ở sink.

## 14. Checklist thiết kế trước khi bàn giao contract

- [ ] Có ví dụ JSON payload và tài liệu field: type, bắt buộc/tùy chọn, null, miền giá trị, đơn vị.
- [ ] ID dài được giữ là **string**; không chuyển qua JavaScript `Number`.
- [ ] Tiền tệ dùng **decimal string** hoặc integer minor units có scale, không tính bằng binary floating point.
- [ ] Timestamp có offset hoặc chuẩn UTC; parse bằng kiểu thời gian thực, không bỏ timezone.
- [ ] Tất cả bytes JSON dùng UTF-8 và có quyết định rõ về BOM, malformed UTF-8, compression.
- [ ] Chọn rõ JMS `TextMessage` hay `BytesMessage`; kiểm thử body type khi qua AMQP/STOMP bridge.
- [ ] Có metadata `eventType`/`schemaVersion`/content type và quy tắc đồng bộ với body.
- [ ] Bên nhận validate **type trước khi coercion**, giới hạn payload và đối chiếu schema version.
- [ ] Có chiến lược evolve v1/v2, unknown enum/unknown field, replay message cũ.
- [ ] Đã test Unicode, large integer, decimal, null/missing, malformed payload và invalid schema.
- [ ] Có phân loại retry/DLQ, logging an toàn và idempotency theo `eventId`.
- [ ] Kết quả cross-language được chứng minh bằng **message thực tế trên broker**, không chỉ unit test serializer.

## 15. Câu hỏi tự kiểm tra

1. Vì sao JSON `{"orderId":9007199254740993}` có thể sai ở JavaScript dù Java `long` lưu được số này?
2. Khi Java JMS producer gửi `TextMessage`, ai chịu trách nhiệm chuyển Java `String` thành bytes trên wire?
3. Nếu dùng `BytesMessage` chứa JSON, tại sao phải khai báo và decode UTF-8 tường minh?
4. `totalAmount: 129.90` khác gì với `totalAmount: "129.90"` theo schema và xử lý tiền tệ?
5. `promotionCode` bị thiếu khác `promotionCode: null` ở điểm nào?
6. Field `occurredAt` có đuôi `Z` mang ý nghĩa gì? Vì sao không bỏ offset khi parse?
7. Nếu body `schemaVersion=2` nhưng JMS property `schemaVersion=1`, consumer nên làm gì?
8. Vì sao message JSON sai kiểu nên đi DLQ/quarantine thay vì rollback vô hạn?
9. Hai JSON object có field order khác nhau nhưng cùng giá trị có bắt buộc cùng bytes không?
10. Một client MQTT hoặc AMQP nhận được bytes từ broker Artemis có tự động hiểu tất cả JMS headers và application properties không?

**Gợi ý:** (1) JS `Number` an toàn tối đa `2^53−1`; (2) JMS provider; (3) byte không mang charset mặc định đáng tin; (4) number có nguy cơ mất precision/scale, string giữ decimal contract; (5) presence semantics; (6) UTC, tránh đổi instant; (7) từ chối/kiểm tra inconsistency; (8) lỗi không thể tự sửa qua retry; (9) không, so giá trị hoặc canonical form; (10) không, cần kiểm thử protocol mapping.

## 16. Tài liệu đối chiếu

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): kiểu JSON, cú pháp number/string, UTF-8 và BOM.
- [RFC 3339 — Date and Time on the Internet: Timestamps](https://www.rfc-editor.org/rfc/rfc3339): timestamp có offset, tương tác thời gian giữa hệ thống.
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12): `type`, `required`, `properties`, `format` và các cơ chế validation.
- [Oracle Java EE 7 — `TextMessage`](https://docs.oracle.com/javaee/7/api/javax/jms/TextMessage.html): JMS text payload.
- [Oracle Java EE 7 — `BytesMessage`](https://docs.oracle.com/javaee/7/api/javax/jms/BytesMessage.html): message byte, `getBodyLength()`, `readBytes()` và `writeBytes()`.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): mapping address/queue/routing.
- [Apache ActiveMQ Artemis — Protocols & Interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html): trao đổi message giữa protocol/client.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): JSON tree/model binding, strict parsing options.

> **Điểm cần nhớ:** Broker vận chuyển message, còn **hợp đồng payload** mới bảo vệ ý nghĩa dữ liệu. Một tích hợp bền vững phải xác định rõ **JSON type → UTF-8 bytes → JMS message body → protocol adapter → parser/DTO của consumer**, và có kiểm thử chính xác với **ID lớn, decimal, timestamp, Unicode, null/missing và schema version**.
