# Transformer theo content type

> **Chương:** Transformer  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **chọn phép chuyển đổi dựa trên loại nội dung (Content-Type)** nhưng vẫn giữ đúng contract và ý nghĩa nghiệp vụ của message.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `Content-Type` mô tả **biểu diễn dữ liệu** nào, phân biệt với kiểu Java của payload và loại sự kiện nghiệp vụ.
2. Lựa chọn transformer cho message JSON, văn bản hoặc những media type được hỗ trợ, **không suy đoán định dạng** từ nội dung tùy tiện.
3. Xử lý `contentType`, `charset`, contract version, byte payload, validation và giới hạn kích thước theo một chính sách **fail-closed**.
4. Viết mapper thuần Java và kết nối nó với Spring Integration `Transformer` / Java DSL.
5. Hiểu cách **đổi payload từ `byte[]` sang DTO** ảnh hưởng đến ý nghĩa của header `contentType`, correlation và metadata liên quan.
6. Kiểm thử lựa chọn định dạng, mapping đúng giá trị, thiếu/sai header, malformed payload, charset, lỗi kỹ thuật và các ranh giới đồng bộ–bất đồng bộ.

## 2. Bối cảnh: một endpoint, nhiều cách mã hóa dữ liệu

Một nền tảng nhận đơn hàng từ những bên tích hợp có năng lực khác nhau. Đối tác mới gửi JSON; một hệ thống cũ gửi một dòng văn bản theo giao thức nội bộ đã được công bố. Cả hai cần tạo cùng một `CanonicalOrder` trước khi chuyển vào Router và các handler nghiệp vụ.

Message thứ nhất:

~~~http
Content-Type: application/json; charset=UTF-8
X-Contract-Version: v1

{"orderId":"ORD-501","currency":"USD","amountMinor":125050}
~~~

Message thứ hai:

~~~http
Content-Type: text/plain; charset=UTF-8
X-Contract-Version: v1

ORD-502|USD|125050
~~~

Trong **giao thức văn bản minh họa**, dấu `|` ngăn đúng ba trường: mã đơn, tiền tệ và số tiền theo đơn vị nhỏ (cents). Không hỗ trợ dấu `|` nằm trong mã đơn, escape hoặc nhiều dòng. Nếu một hệ thống thực có text/CSV phức tạp, phải sử dụng parser đúng đặc tả của nó thay vì mặc định dùng `split`.

Cả hai được ánh xạ về:

~~~json
{
  "orderId": "ORD-501",
  "currency": "USD",
  "total": 1250.50
}
~~~

Trong Java, `total` sẽ là `BigDecimal("1250.50")`, không phải số chấm động `double`.

~~~mermaid
flowchart LR
    A["Inbound adapter: byte[]"] --> V["Kiểm tra Content-Type, charset, version"]
    V --> T{"Content-Type Transformer"}
    T -->|"application/json"| J["JSON parser"]
    T -->|"text/plain"| P["Text parser của contract v1"]
    T -->|"Loại khác"| E["Reject / error flow"]
    J --> C["CanonicalOrder"]
    P --> C
    C --> R["Router / business handler"]
~~~

**Trọng tâm:** Content-Type quyết định **cách diễn giải bytes**, không phải bên nhận nghiệp vụ. Sau khi được chuyển về một DTO canonical, Router có thể dùng dữ liệu nghiệp vụ để chọn nhánh.

## 3. Phân biệt ba khái niệm thường bị gộp nhầm

| Khái niệm | Được quyết định bởi | Ví dụ | Vai trò |
| --- | --- | --- | --- |
| **Media type / Content-Type** | Hợp đồng transport hoặc metadata message đã được kiểm tra | `application/json`, `text/plain`, `application/xml` | Chọn cách giải mã biểu diễn |
| **Payload Java type** | Adapter, deserializer hoặc Transformer đã chạy | `byte[]`, `String`, `PartnerOrder` | Chọn API và kiểu xử lý trong JVM |
| **Business message type** | Schema/contract của nghiệp vụ | `OrderCreated`, `CancelOrder` | Chọn quy tắc nghiệp vụ/Router |

Một `byte[]` có thể chứa JSON, XML, Protobuf hoặc dữ liệu nén. Vì vậy dùng `payload instanceof byte[]` **không đủ** để quyết định parser.

Ngược lại, một adapter có thể đã deserialize JSON thành `OrderRequest` trước khi message vào Spring Integration; lúc đó không nên parse JSON lần nữa chỉ vì `contentType` vẫn còn `application/json`.

Một message loại nghiệp vụ `CancelOrder` cũng có thể được mã hóa bằng JSON **hoặc** Protobuf. Do đó, **“transformer theo content type” không đồng nghĩa “router theo business event type”**.

### 3.1. Header `contentType` trong Spring Messaging

`MessageHeaders.CONTENT_TYPE` là hằng đại diện cho tên header thường dùng là `contentType` trong Spring Messaging. Giá trị có thể được biểu diễn bằng `MimeType` hoặc một chuỗi MIME type, tùy adapter và cách tạo message. Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<byte[]> incoming = MessageBuilder.withPayload(
        "{\"orderId\":\"ORD-501\"}".getBytes(
            java.nio.charset.StandardCharsets.UTF_8))
    .setHeader(MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.parseMimeType("application/json;charset=UTF-8"))
    .build();
~~~

Message trên chỉ minh họa cách đặt header; payload JSON cố ý chưa đủ trường theo contract đơn hàng của bài nên **chưa thể chuyển thành `CanonicalOrder` hợp lệ**.

Nếu nguồn đầu vào là HTTP, `Content-Type` của HTTP request thường cần được adapter chuyển vào `MessageHeaders` tương ứng; không mặc định mọi header ngoài đều được tự động giữ lại ở mọi bước.

### 3.2. Content-Type khác Content-Encoding

`Content-Type: application/json` cho biết loại dữ liệu; `Content-Encoding: gzip` cho biết một phép mã hóa nén ở tầng truyền tải. Không thể đưa thẳng bytes đã gzip vào JSON parser và kết luận rằng `Content-Type` sai.

Thiết kế đúng cần một bước **giải nén/giải mã có kiểm soát** trước parser nếu hợp đồng cho phép, cùng giới hạn kích thước sau giải nén để ngăn payload nén nhỏ nhưng phình rất lớn.

### 3.3. Content-Type khác charset

`application/json;charset=UTF-8` vừa mang media type vừa mang tham số charset. Đối với hợp đồng chỉ hỗ trợ UTF-8, hệ thống nên chấp nhận UTF-8 đúng quy định và **từ chối charset khác**, thay vì tự dùng bảng mã mặc định của máy.

Nếu charset không khai báo, chỉ được mặc định UTF-8 khi **hợp đồng transport/schema đã quy định như vậy**. Trong ví dụ này, contract v1 quy định UTF-8 ngay cả khi tham số charset không có.

## 4. Bảng lựa chọn transformer theo media type

| Content-Type | Định dạng dự kiến | Cách xử lý | Hành vi của ví dụ |
| --- | --- | --- | --- |
| `application/json` | JSON v1 | Jackson JSON parser + validation | **Hỗ trợ** |
| `application/json;charset=UTF-8` | JSON v1 UTF-8 | Cùng parser | **Hỗ trợ** |
| `text/plain` | Một dòng `ID|CURRENCY|MINOR` v1 | Parser văn bản của contract v1 | **Hỗ trợ** |
| `text/plain;charset=UTF-8` | Giao thức text v1 UTF-8 | Cùng parser | **Hỗ trợ** |
| `application/xml` | XML | Cần XML mapper và cấu hình parser chống XXE | **Không hỗ trợ trong code mẫu** |
| `text/csv` | CSV | Cần parser CSV đúng escaping/quoting | **Không hỗ trợ trong code mẫu** |
| `application/protobuf` | Protobuf | Cần schema/message type cụ thể, decoder tương ứng | **Không hỗ trợ trong code mẫu** |
| `application/vnd.company.order+json` | Vendor JSON | Phải được hợp đồng và version cho phép riêng | **Không tự động chấp nhận** |
| Không có `contentType` | Không biết biểu diễn | Không đoán bừa parser | **Từ chối** |
| `application/json;charset=ISO-8859-1` | JSON nhưng sai encoding của contract | Không tự đổi bảng mã | **Từ chối** |

Bảng trên **không có nghĩa JSON là định dạng chuẩn cho mọi trường hợp**. Ứng dụng có thể hỗ trợ XML, Avro, CBOR, Protobuf hay CSV với các Transformer riêng khi có giao thức và schema cụ thể.

### 4.1. Exact match hay `application/*+json`?

Một số media type có hậu tố `+json` nhưng mang contract riêng. Chẳng hạn, cùng là JSON mà `application/vnd.vendorA.order+json` và `application/vnd.vendorB.order+json` có thể đặt tên field, đơn vị tiền và enum khác nhau.

Không nên định tuyến tất cả `+json` vào một mapper nghiệp vụ trừ khi các schema được xác nhận tương thích. Có thể phân tách:

~~~text
Media type → parser kỹ thuật → DTO theo version → mapper nghiệp vụ
~~~

Với ứng dụng nhiều đối tác, một registry **media type + contract version + source đã xác thực** thường tốt hơn một câu lệnh chỉ xét `subtype.endsWith("+json")`.

### 4.2. Khi `Content-Type` không khớp body

Nếu header báo JSON nhưng body là XML, parser JSON phải thất bại **có kiểm soát**. Không nên cứ thất bại JSON là âm thầm thử XML, CSV rồi text cho đến khi một parser chấp nhận. Cách “thử mọi định dạng” có thể tạo hành vi nhập nhằng, phá hợp đồng và mở ra lỗi bảo mật do parser diễn giải dữ liệu khác nhau.

## 5. Bảng mapping nghiệp vụ sang DTO canonical

Hợp đồng **v1 của bài học** chỉ hỗ trợ đơn hàng với `USD`, `amountMinor` biểu diễn cents và `total` dương. Vì thế cả JSON và text đều phải tuân thủ:

| Trường canonical | JSON v1 | Text v1 | Điều kiện |
| --- | --- | --- | --- |
| `orderId: String` | `orderId` | Phần 1 | Không `null`, không rỗng |
| `currency: String` | `currency` | Phần 2 | Chính xác `USD` |
| `total: BigDecimal` | `amountMinor` | Phần 3 | Số nguyên dương, cents → USD |
| `schemaVersion` | Header `contractVersion` | Header `contractVersion` | Phải là `v1` |

**Không dùng `double` cho tiền.** Với `amountMinor=125050`, phép chuyển chính xác là:

~~~java
import java.math.BigDecimal;

BigDecimal total = BigDecimal.valueOf(125050L, 2);
System.out.println(total.toPlainString()); // "1250.50"
~~~

Scale 2 là **quy định riêng cho USD của ví dụ**; không thể suy rộng cho mọi đồng tiền và mọi hệ thống thanh toán.

### 5.1. Giá trị thiếu không tự trở thành mặc định hợp lệ

Nếu JSON thiếu `currency` hoặc text có `ORD-502||125050`, Transformer phải trả lỗi mapping; không tự chèn `USD` chỉ vì phần lớn traffic trước đó dùng USD.

Nếu input thiếu `amountMinor`, việc gọi những API có giá trị mặc định như `JsonNode.asLong()` mà không kiểm tra kiểu có thể biến lỗi thành số 0 hoặc giá trị đoán được. Hãy kiểm tra **node tồn tại, là số nguyên và nằm trong phạm vi `long`** trước khi chuyển đổi.

### 5.2. Schema version phải rõ ràng

Cùng `application/json`, v2 có thể thay `amountMinor` bằng `amountDecimal` hoặc tách `currency` thành cấu trúc lồng nhau. Một Transformer v1 không nên âm thầm tiếp tục bằng các giá trị mặc định.

Một mô hình an toàn là khóa lựa chọn `(mediaType, contractVersion)`. Khi nâng cấp, thêm mapper v2 và test compatibility thay vì sửa mapper v1 theo cách phá vỡ dữ liệu cũ còn trong queue.

## 6. Java thuần: mapper theo Content-Type và contract version

Ví dụ dùng **Java 17+**, **Spring Messaging** và Jackson Databind. Nếu dùng Spring Boot/Spring Integration trong ứng dụng thực, cần khai báo dependency Jackson tương thích với stack của dự án. Đoạn code sau là **lõi mapper**, chưa bao gồm outbound adapter hay giao tiếp HTTP thực sự.

### 6.1. DTO canonical và lỗi có mã nguyên nhân

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record CanonicalOrder(String orderId,
                      String currency,
                      BigDecimal total) {
    CanonicalOrder {
        if (orderId == null || orderId.isBlank()) {
            throw new MappingFailure("ORDER_ID_MISSING");
        }
        if (!"USD".equals(currency)) {
            throw new MappingFailure("UNSUPPORTED_CURRENCY");
        }
        if (total == null || total.signum() <= 0) {
            throw new MappingFailure("INVALID_TOTAL");
        }
    }
}

final class MappingFailure extends RuntimeException {
    private final String code;

    MappingFailure(String code) {
        super(code);
        this.code = code;
    }

    MappingFailure(String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Canonical model có số tiền **đã chuẩn hóa**. `MappingFailure` tách lỗi dữ liệu/hợp đồng ra khỏi lỗi downstream như kết nối timeout. Trong một ứng dụng production, có thể bổ sung source/schema version, error category, một mã correlation và thông tin vị trí field **không chứa dữ liệu nhạy cảm**.

### 6.2. Đọc, kiểm tra MIME type trước khi parse

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

final class ContentTypeOrderMapper {
    private static final int MAX_BYTES = 64 * 1024;
    private final ObjectMapper json = new ObjectMapper();

    CanonicalOrder decode(Message<?> message) {
        if (message == null || !(message.getPayload() instanceof byte[] bytes)) {
            throw new MappingFailure("PAYLOAD_MUST_BE_BYTES");
        }
        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new MappingFailure("PAYLOAD_SIZE_INVALID");
        }

        MimeType type = parseContentType(
            message.getHeaders().get(MessageHeaders.CONTENT_TYPE));

        if (!"v1".equals(message.getHeaders().get("contractVersion"))) {
            throw new MappingFailure("UNSUPPORTED_CONTRACT_VERSION");
        }

        if (type.getCharset() != null
                && !StandardCharsets.UTF_8.equals(type.getCharset())) {
            throw new MappingFailure("UNSUPPORTED_CHARSET");
        }

        // Decoder nghiêm ngặt: không âm thầm thay byte UTF-8 sai bằng U+FFFD.
        String content = strictUtf8(bytes);

        if (is(type, "application", "json")) {
            return decodeJson(content);
        }
        if (is(type, "text", "plain")) {
            return decodeTextV1(content);
        }
        throw new MappingFailure("UNSUPPORTED_CONTENT_TYPE");
    }

    static MimeType parseContentType(Object header) {
        try {
            if (header instanceof MimeType mime) {
                return mime;
            }
            if (header instanceof String value) {
                return MimeTypeUtils.parseMimeType(value);
            }
        } catch (IllegalArgumentException ex) {
            throw new MappingFailure("INVALID_CONTENT_TYPE", ex);
        }
        throw new MappingFailure("CONTENT_TYPE_MISSING");
    }

    private static boolean is(MimeType mime, String type, String subtype) {
        return type.equalsIgnoreCase(mime.getType())
            && subtype.equalsIgnoreCase(mime.getSubtype());
    }

    private static String strictUtf8(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
        } catch (CharacterCodingException ex) {
            throw new MappingFailure("INVALID_UTF8", ex);
        }
    }

    private CanonicalOrder decodeJson(String text) {
        try {
            JsonNode root = json.readTree(text);
            if (root == null || !root.isObject()) {
                throw new MappingFailure("JSON_OBJECT_REQUIRED");
            }

            String orderId = requiredText(root, "orderId");
            String currency = requiredText(root, "currency");
            JsonNode minor = root.get("amountMinor");

            if (minor == null || !minor.isIntegralNumber()
                    || !minor.canConvertToLong()) {
                throw new MappingFailure("AMOUNT_MINOR_INVALID");
            }

            return fromMinorUnits(orderId, currency, minor.longValue());
        } catch (JsonProcessingException ex) {
            throw new MappingFailure("MALFORMED_JSON", ex);
        }
    }

    private static String requiredText(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw new MappingFailure("INVALID_" + field.toUpperCase(Locale.ROOT));
        }
        return value.textValue();
    }

    private static CanonicalOrder decodeTextV1(String text) {
        // Chỉ dành cho contract text v1: đúng ba trường, không có escaping.
        String[] fields = text.split("\\|", -1);
        if (fields.length != 3) {
            throw new MappingFailure("TEXT_FIELD_COUNT_INVALID");
        }

        long minor;
        try {
            minor = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new MappingFailure("AMOUNT_MINOR_INVALID", ex);
        }
        return fromMinorUnits(fields[0], fields[1], minor);
    }

    private static CanonicalOrder fromMinorUnits(
            String id, String currency, long minor) {
        if (minor <= 0) {
            throw new MappingFailure("AMOUNT_MINOR_INVALID");
        }
        return new CanonicalOrder(
            id, currency, java.math.BigDecimal.valueOf(minor, 2));
    }
}
~~~

Đây là một parser **hẹp và có chủ đích**:

- Chỉ nhận payload `byte[]`; không “cố” deserialize một `Map`, `String` hoặc DTO bất ngờ từ adapter khác.
- Chặn body rỗng hoặc vượt 64 KiB trước khi decode, theo ngưỡng demo (production chọn ngưỡng theo hợp đồng).
- Bắt buộc header `contractVersion=v1`; chưa hỗ trợ v2.
- Chỉ chấp nhận UTF-8: dùng decoder có `CodingErrorAction.REPORT` để không làm mất byte lỗi.
- Nhận chính xác `application/json` hoặc `text/plain` theo contract; các MIME khác bị từ chối.
- JSON cần object và `amountMinor` nguyên; text phải đúng ba trường.
- Không tự động cắt khoảng trắng khỏi ID hoặc currency. Nếu hợp đồng cần trim/normalize, phải định nghĩa điều kiện đó một cách nhất quán ở **cả hai parser**.

### 6.3. Về bảo mật của parser

Ví dụ chỉ parse JSON và text. Nếu bổ sung XML, phải cấu hình parser chống **XXE**, không cho external entities/DTD không cần thiết và giới hạn tài nguyên. Nếu bổ sung CSV, cần parser hỗ trợ đúng dấu nháy, escaping, dòng nhiều trường và giới hạn kích thước; `split(",")` không phải CSV parser tổng quát.

Tương tự, một tài liệu JSON hợp lệ về cú pháp **chưa chắc hợp lệ về schema**. Contract production có thể cần JSON Schema, giới hạn field, version, độ sâu đối tượng và kiểm soát field không được phép. Jackson parser ở ví dụ đọc ba field cần thiết và có thể bỏ qua trường thừa; nếu hệ thống yêu cầu **strict schema**, phải bổ sung bước reject field ngoài hợp đồng.

## 7. Spring Integration: viết Transformer nhận Message có header

Transformer trong Spring Integration có thể đọc cả **payload và headers** để quyết định cách chuyển đổi. Một cách làm rõ ràng là mở rộng `AbstractTransformer`, override `doTransform(Message<?>)`, gọi mapper vừa xây dựng và trả về **message chứa DTO canonical**.

### 7.1. Vì sao nên cập nhật header `contentType`?

Sau khi payload đổi từ bytes JSON/text sang `CanonicalOrder`, nếu cứ giữ `contentType=application/json` ở message nội bộ, một consumer tiếp theo có thể hiểu sai rằng payload vẫn là JSON cần deserialize.

Ở ví dụ, ta:

1. Giữ header business correlation và version nguồn.
2. Gỡ `MessageHeaders.CONTENT_TYPE` vì payload giờ là **Java object canonical chưa serialize**.
3. Gắn `originalContentType` làm thông tin nguồn và `canonicalSchemaVersion` để downstream biết contract hiện tại.

~~~java
import org.springframework.integration.transformer.AbstractTransformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

final class ContentTypeOrderTransformer extends AbstractTransformer {
    private final ContentTypeOrderMapper mapper;

    ContentTypeOrderTransformer(ContentTypeOrderMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    protected Object doTransform(Message<?> message) {
        CanonicalOrder order = mapper.decode(message);
        String sourceType = ContentTypeOrderMapper
            .parseContentType(message.getHeaders()
                .get(MessageHeaders.CONTENT_TYPE))
            .toString();

        return MessageBuilder.withPayload(order)
            .copyHeaders(message.getHeaders())
            .removeHeader(MessageHeaders.CONTENT_TYPE)
            .setHeader("originalContentType", sourceType)
            .setHeader("canonicalSchemaVersion", "v1")
            .build();
    }
}
~~~

Khi Transformer trả một `Message<?>`, Spring Integration dùng thông điệp kết quả theo semantics của endpoint. Ví dụ dùng `MessageBuilder` để điều khiển các header ứng dụng. **Không dựa vào object identity của envelope** để suy ra idempotency hoặc rằng mọi header ở một adapter ngoài sẽ tự động tồn tại ở hệ thống kia.

Trong production, `originalContentType` chỉ là metadata phục vụ kiểm tra/truy vết. Không được xem nó là bằng chứng nguồn xác thực: header MIME gốc có thể do client khai báo và phải được đối chiếu với transport, quyền gửi và schema.

### 7.2. Cấu hình Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ContentTypeTransformerConfiguration {

    @Bean
    ContentTypeOrderMapper contentTypeOrderMapper() {
        return new ContentTypeOrderMapper();
    }

    @Bean
    ContentTypeOrderTransformer contentTypeOrderTransformer(
            ContentTypeOrderMapper mapper) {
        return new ContentTypeOrderTransformer(mapper);
    }

    @Bean("orders.raw.in")
    DirectChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean("orders.canonical.out")
    QueueChannel canonicalOutput() {
        // Queue nội bộ làm điểm thu cho bài học và integration tests.
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeIncomingOrders(
            ContentTypeOrderTransformer transformer) {
        return IntegrationFlow.from("orders.raw.in")
            .transform(transformer)
            .channel("orders.canonical.out")
            .get();
    }
}
~~~

~~~text
orders.raw.in (DirectChannel)
    |
    v
ContentTypeOrderTransformer
    |-- đọc Content-Type + contractVersion
    |-- JSON/text v1 parser → CanonicalOrder
    |-- gỡ header contentType cũ, gắn canonicalSchemaVersion
    v
orders.canonical.out (QueueChannel trong demo)
    |
    v
Router/handler/outbound adapter trong hệ thống thực
~~~

`QueueChannel` ở đầu ra demo chỉ thu message để test; chưa có consumer gửi đến kho, CRM hoặc hệ thống thanh toán. Khi đưa vào production, cần endpoint nhận canonical DTO và policy delivery/error tương ứng.

### 7.3. Ví dụ gửi message

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

String json = """
    {"orderId":"ORD-501","currency":"USD","amountMinor":125050}
    """;

Message<byte[]> raw = MessageBuilder
    .withPayload(json.getBytes(StandardCharsets.UTF_8))
    .setHeader(MessageHeaders.CONTENT_TYPE,
        "application/json;charset=UTF-8")
    .setHeader("contractVersion", "v1")
    .setHeader("businessCorrelationId", "ORD-501")
    .build();

// inputChannel là bean orders.raw.in đã được inject.
// inputChannel.send(raw);
~~~

Nếu adapter của bạn đã tạo `String` hoặc DTO thay vì `byte[]`, đừng đưa thẳng message đó vào flow trên. Hãy xác định **một ranh giới rõ ràng**: adapter cung cấp bytes để transform theo MIME, hoặc adapter đã decode thành kiểu cụ thể và flow tiếp tục từ đó. Tránh parse hai lần.

## 8. Kiến trúc nhiều định dạng: một transformer hay nhiều transformer?

Ví dụ đã dùng **một Transformer lựa chọn parser nội bộ** vì chỉ có hai định dạng đơn giản và một DTO đích. Nhưng có nhiều chiến lược hợp lý.

| Chiến lược | Cách vận hành | Khi nên dùng |
| --- | --- | --- |
| Một Transformer dispatch theo MIME | Một endpoint đọc Content-Type rồi gọi parser tương ứng | Ít format, cùng canonical model, logic nhỏ |
| Content-Type Router trước các Transformer chuyên biệt | Router chọn channel JSON/XML/Protobuf, mỗi nhánh có mapper riêng | Nhiều format, parser phức tạp, cần quan sát lỗi theo định dạng |
| Registry parser được kiểm soát | Tra theo khóa `(mediaType, version)` để lấy parser/mapper | Nhiều partner/version, thêm format liên tục |
| Adapter deserialize trước flow | HTTP/broker adapter chuyển bytes thành DTO | Transport contract đơn giản, muốn nghiệp vụ không biết MIME |

~~~mermaid
flowchart LR
    IN["bytes + validated contentType"] --> CR{"Content-Type Router"}
    CR -->|JSON v1| J["JSON Transformer"]
    CR -->|XML v2| X["XML Transformer"]
    CR -->|Protobuf v1| P["Protobuf Transformer"]
    J --> CAN["Canonical DTO / validation"]
    X --> CAN
    P --> CAN
~~~

Ở mô hình Router trước các Transformer, **định tuyến theo Content-Type chỉ quyết định parser**; sau khi có canonical DTO, một Business Router khác có thể quyết định đối tượng nghiệp vụ đi xử lý ở đâu.

**Không nên** dùng tên channel lấy trực tiếp từ header `Content-Type` do người gửi tự đặt. Hãy ánh xạ media type đã kiểm tra qua **allowlist**, không cho client chọn bean/channel bất kỳ.

## 9. Type conversion khác schema translation

Một message JSON đã được deserialize thành `Map<String,Object>` rồi được chuyển sang `CanonicalOrder` là **type mapping** trong JVM. Ngược lại, việc ánh xạ `amount_minor` sang `total` với thang tiền và rule nghiệp vụ là **schema/semantic translation**.

Spring Integration có nhiều cơ chế Transformer, conversion service và serializer/deserializer. Chọn công cụ theo trách nhiệm:

- **Deserializer/codec:** chuyển bytes thành object biểu diễn nguồn.
- **Schema mapper:** chuyển object nguồn thành canonical DTO hoặc object đích.
- **Header Enricher:** bổ sung metadata như schema version hoặc tenant đã được xác thực.
- **Filter:** chặn message không đủ điều kiện.
- **Router:** chọn đích/nhánh theo format hoặc nghiệp vụ.
- **Gateway/Adapter:** giao tiếp transport/hệ thống ngoài.

Một pipeline có thể là:

~~~text
Inbound adapter (bytes)
  → Validate Content-Type / schemaVersion
  → JSON/XML/Text parser (Transformer)
  → Source DTO
  → Canonical schema mapper (Transformer)
  → Enrich metadata nếu cần gọi dịch vụ ngoài
  → Business Router
  → Handler / Outbound Gateway
~~~

Không nhất thiết mọi bước phải có một channel riêng, nhưng mỗi trách nhiệm nên có **hợp đồng, khả năng kiểm thử và xử lý lỗi riêng**.

## 10. Metadata nguồn, lỗi kiểu và trust boundary

### 10.1. Không tin MIME từ người gửi là bằng chứng bảo mật

`Content-Type` là **tuyên bố về biểu diễn**, không phải chứng thực danh tính, tenant hoặc quyền. Một request ngoài có thể khai `application/json` nhưng chứa bytes không phải JSON; parser sẽ phát hiện sai cú pháp. Tuy nhiên, điều đó chưa bảo đảm người gửi được phép gửi loại event tương ứng.

Cần kiểm tra ở ingress:

1. Xác thực/ký số/mTLS hoặc cơ chế bảo vệ phù hợp.
2. Đối chiếu account/tenant với **loại nội dung và version được phép**.
3. Giới hạn kích thước message và thời gian parse.
4. Không cho phép giá trị MIME tự định nghĩa đường đến internal endpoint.
5. Không dùng header “đã xác thực” do client tự khai.

### 10.2. Thiếu hoặc sai Content-Type

Với contract này:

- Thiếu header → `CONTENT_TYPE_MISSING`.
- Cú pháp MIME không hợp lệ → `INVALID_CONTENT_TYPE`.
- MIME không hỗ trợ → `UNSUPPORTED_CONTENT_TYPE`.
- Charset không phải UTF-8 → `UNSUPPORTED_CHARSET`.
- Bytes không phải UTF-8 hợp lệ → `INVALID_UTF8`.
- JSON hỏng → `MALFORMED_JSON`.
- Thiếu hoặc sai schema version → `UNSUPPORTED_CONTRACT_VERSION`.

Tách các mã lỗi giúp hỗ trợ kỹ thuật phân biệt **người gửi sai hợp đồng** với **tầng hạ tầng lỗi**. Nếu inbound adapter chặn MIME trước khi message tới Transformer, tầng đó cần có lỗi/reply theo contract tương đương.

### 10.3. Không vô tình sửa payload đã dùng chung

Các message bên trong JVM có thể chia sẻ tham chiếu payload. Nếu Transformer nhận một `Map` mutable và chỉnh trực tiếp các trường của nó, một recipient khác có thể nhìn thấy dữ liệu thay đổi. Tạo **canonical DTO bất biến** và không mutate payload đầu vào là lựa chọn dễ kiểm thử hơn.

Với `byte[]`, mảng byte vẫn mutable; một producer có thể thay đổi mảng sau khi gửi vào queue. Ở ranh giới async, cần bảo đảm **snapshot bất biến/copy có chủ đích** nếu không thể tin rằng producer sẽ ngừng sửa mảng.

## 11. Xử lý lỗi và hành vi khi nhiều nhánh hoạt động

### 11.1. Error path của Transformer

Một Transformer có thể gặp:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Malformed payload | JSON sai dấu, text sai số cột | Reject/quarantine theo contract |
| Content-Type/version không hỗ trợ | XML gửi vào flow chỉ hỗ trợ JSON/text | Không tự chọn parser khác |
| Semantic validation | Tiền ≤ 0, mã đơn trống | Từ chối với reason code |
| Bug trong mapper | `NullPointerException` ngoài dự kiến | Lỗi kỹ thuật, cảnh báo, điều tra |
| Lỗi bên ngoài sau Transformer | HTTP 503 khi gửi DTO canonical | Retry/error ở outbound Gateway, không đổ lỗi cho MIME |
| Redelivery | Cùng event được gửi lại | Idempotent handler; không tạo side effect trùng |

Với `DirectChannel`, lỗi Transformer có thể lan ngược tới caller (thường được bọc theo cơ chế Messaging/Spring Integration). Với poller, executor hoặc broker, lỗi có thể xuất hiện muộn và được gửi dưới dạng `ErrorMessage` tới error channel theo cấu hình.

**Đừng** mặc định bất kỳ lỗi parser nào cũng được auto-retry: JSON hỏng không thể “tự lành” nếu gửi lại cùng bytes. Ngược lại, lỗi I/O của một dịch vụ bên ngoài có thể retry hữu hạn theo chính sách khác.

### 11.2. Gateway request–reply

Nếu một Gateway đồng bộ chờ `CanonicalOrder` hoặc kết quả nghiệp vụ, Transformer ném lỗi hoặc luồng từ chối message cần có **exception/reply có kiểm soát**. Không chỉ drop message rồi để caller chờ timeout nếu giao thức yêu cầu phản hồi lỗi.

Nếu đầu vào là Kafka hoặc một queue bất đồng bộ, việc quyết định retry, dead-letter hay ack/nack phải nằm trong hợp đồng consumer/adapter và tránh vòng lặp không giới hạn.

### 11.3. Retry, correlation và idempotency

Một phép map bytes → DTO **không tạo tác dụng phụ** có thể thực hiện lại. Nhưng khi DTO được gửi đi để **tạo đơn hàng**, side effect có thể đã xảy ra trước khi kết nối timeout. Cần dùng idempotency key ổn định như `(sourceSystem, orderId, operation)` hoặc `commandId`, thay vì ID message mới được sinh mỗi lần retry.

`businessCorrelationId` hỗ trợ nối trace qua các Transformer; nó **không thay thế** idempotency. Nếu có Splitter/Aggregator sau canonical DTO, cần giữ hoặc tạo correlation/sequence theo contract cụ thể để tránh gộp nhầm hai đơn khác nhau.

## 12. Kiểm thử mapper Java độc lập

Trước khi kiểm tra Spring context, unit test nên chứng minh **chọn đúng parser** và **trả đúng giá trị canonical**.

### 12.1. JUnit 5 Parameterized Tests cho JSON và text

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class ContentTypeOrderMapperTest {
    private final ContentTypeOrderMapper mapper =
        new ContentTypeOrderMapper();

    private static Message<byte[]> message(String contentType, String body) {
        return MessageBuilder
            .withPayload(body.getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, contentType)
            .setHeader("contractVersion", "v1")
            .build();
    }

    static Stream<Arguments> validRepresentations() {
        return Stream.of(
            Arguments.of(
                "application/json;charset=UTF-8",
                "{\"orderId\":\"ORD-501\",\"currency\":\"USD\","
                    + "\"amountMinor\":125050}",
                "ORD-501"),
            Arguments.of(
                "text/plain;charset=UTF-8",
                "ORD-502|USD|125050",
                "ORD-502")
        );
    }

    @ParameterizedTest
    @MethodSource("validRepresentations")
    void mapsDifferentContentTypesIntoSameCanonicalContract(
            String type, String body, String expectedId) {
        CanonicalOrder order = mapper.decode(message(type, body));

        assertEquals(expectedId, order.orderId());
        assertEquals("USD", order.currency());
        assertEquals(new BigDecimal("1250.50"), order.total());
    }
}
~~~

Test ở đây chứng minh cùng một schema canonical có thể được xây từ hai kiểu biểu diễn. Trong ứng dụng production, nên bổ sung cả **kiểm thử schema đầy đủ**, bao gồm giá trị unknown field, enum, required/null và parser resource limits.

### 12.2. Các negative tests bắt buộc

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class ContentTypeOrderMapperNegativeTest {
    private final ContentTypeOrderMapper mapper =
        new ContentTypeOrderMapper();

    private Message<byte[]> input(String mime, String body) {
        return MessageBuilder.withPayload(
                body.getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, mime)
            .setHeader("contractVersion", "v1")
            .build();
    }

    @Test
    void rejectsUnsupportedMediaTypeInsteadOfGuessingByBody() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input(
                "application/xml",
                "{\"orderId\":\"ORD-501\",\"currency\":\"USD\","
                    + "\"amountMinor\":125050}")));

        assertEquals("UNSUPPORTED_CONTENT_TYPE", ex.code());
    }

    @Test
    void rejectsJsonWithNonIntegralMinorUnits() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input("application/json",
                "{\"orderId\":\"ORD-501\",\"currency\":\"USD\","
                    + "\"amountMinor\":12.50}")));

        assertEquals("AMOUNT_MINOR_INVALID", ex.code());
    }

    @Test
    void rejectsWrongTextFieldCount() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input("text/plain", "ORD-501|USD")));

        assertEquals("TEXT_FIELD_COUNT_INVALID", ex.code());
    }

    @Test
    void rejectsMismatchedCharset() {
        MappingFailure ex = assertThrows(MappingFailure.class, () ->
            mapper.decode(input(
                "application/json;charset=ISO-8859-1",
                "{\"orderId\":\"ORD-501\"}")));

        assertEquals("UNSUPPORTED_CHARSET", ex.code());
    }

    @Test
    void rejectsMissingContractVersion() {
        Message<byte[]> m = MessageBuilder
            .withPayload("ORD-501|USD|125050".getBytes(
                StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, "text/plain")
            .build();

        MappingFailure ex = assertThrows(MappingFailure.class,
            () -> mapper.decode(m));
        assertEquals("UNSUPPORTED_CONTRACT_VERSION", ex.code());
    }
}
~~~

Các test cũng nên có case **thiếu Content-Type**, `byte[]` rỗng, payload quá lớn, UTF-8 sai, số tiền bằng 0, âm, vượt phạm vi `long`, currency khác `USD` và JSON không phải object.

### 12.3. Boundary test cho tiền

| Input `amountMinor` | Kỳ vọng |
| --- | --- |
| `1` | `0.01` |
| `99` | `0.99` |
| `100` | `1.00` |
| `125050` | `1250.50` |
| `0` hoặc âm | Từ chối |
| Số thập phân `12.5` | Từ chối vì contract yêu cầu **số nguyên cents** |
| JSON số nguyên ngoài phạm vi `long` | Từ chối thay vì overflow |

## 13. Integration test: kiểm tra flow và header sau Transformer

Unit test mapper đúng **chưa chứng minh** Java DSL đã wiring đúng. Integration test cần gửi vào `orders.raw.in`, lấy từ `orders.canonical.out`, xác minh DTO và metadata.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ContentTypeTransformerConfiguration.class)
class ContentTypeTransformerFlowTest {
    @Autowired
    @Qualifier("orders.raw.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.canonical.out")
    PollableChannel output;

    @Test
    void transformsAndPreservesBusinessCorrelation() {
        String body =
            "{\"orderId\":\"ORD-601\",\"currency\":\"USD\","
                + "\"amountMinor\":125050}";

        Message<byte[]> raw = MessageBuilder
            .withPayload(body.getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
            .setHeader("contractVersion", "v1")
            .setHeader("businessCorrelationId", "ORD-601")
            .build();

        assertTrue(input.send(raw));

        Message<?> transformed = output.receive(1000);
        assertNotNull(transformed);
        assertInstanceOf(CanonicalOrder.class, transformed.getPayload());

        CanonicalOrder order =
            (CanonicalOrder) transformed.getPayload();

        assertEquals("ORD-601", order.orderId());
        assertEquals(new BigDecimal("1250.50"), order.total());

        assertEquals("ORD-601",
            transformed.getHeaders().get("businessCorrelationId"));
        assertEquals("v1",
            transformed.getHeaders().get("canonicalSchemaVersion"));
        assertNull(transformed.getHeaders().get(
            MessageHeaders.CONTENT_TYPE));

        assertNull(output.receive(0), "No duplicate canonical message");
    }
}
~~~

Kiểm thử trên dùng `QueueChannel` làm output **không có business consumer**. Vì flow từ `DirectChannel` sang queue nội bộ được kích hoạt đồng bộ ở ví dụ, test có thể chờ `receive(1000)` để kiểm tra. Nó **không** xác nhận outbound HTTP/broker hoặc tạo đơn đã thành công.

Nếu output chuyển thành `ExecutorChannel` hoặc broker, cần test với timeout, xử lý race và chờ đúng sự kiện hoàn tất. Nếu Spring Test context tái sử dụng queue giữa nhiều case, cần reset/đảm bảo mỗi test tiêu thụ sạch dữ liệu để tránh ảnh hưởng lẫn nhau.

## 14. Ma trận kiểm thử toàn diện

| Nhóm test | Input | Điều cần xác minh |
| --- | --- | --- |
| JSON v1 | `application/json` + bytes JSON | Đúng DTO canonical |
| Text v1 | `text/plain` + đúng ba trường | Đúng DTO canonical |
| Charset không khai báo | Contract cho phép UTF-8 | Decode UTF-8 theo quy định |
| Charset khác UTF-8 | `charset=ISO-8859-1` | Reject |
| MIME sai so với body | MIME JSON, body text | Không thử parser khác |
| MIME unsupported | XML/CSV/Protobuf chưa cấu hình | Reject có reason |
| Missing Content-Type | Header không tồn tại | Reject, không đoán |
| Version v2 chưa hỗ trợ | Header version v2 | Reject hoặc dùng mapper v2 nếu đã triển khai |
| Header sai kiểu | `contentType` không phải `MimeType` hoặc `String` | Reject |
| Invalid UTF-8 | Byte sequence lỗi | Reject, không thay byte âm thầm |
| JSON malformed | Cú pháp sai | `MALFORMED_JSON` |
| JSON sai kiểu | `amountMinor` là chuỗi hoặc float | Reject |
| Text sai cột | Thiếu trường hoặc dư trường | Reject |
| Money boundary | 1, 100, 125050, 0, âm, overflow | Không mất cents/không overflow |
| Too large payload | Vượt 64 KiB của demo | Reject sớm |
| Source header untrusted | Client tự đặt `contractVersion` hoặc tenant | Được xác thực ở ingress |
| Correlation | `businessCorrelationId` tồn tại | Đi theo message canonical |
| Output header semantics | Payload đã thành Java DTO | Không giữ `application/json` sai nghĩa |
| Mapper exception | Invalid input | Không tạo canonical message giả |
| Downstream timeout | Canonical đã map đúng | Retry/error ở handler ngoài, không đổ lỗi cho parser |
| Replay cùng command | Redelivery | Không tạo side effect trùng ở consumer |

**Chú ý:** Một số case (xác thực ingress, broker, serializer thật) không thể được chứng minh bằng unit test mapper. Cần contract test hoặc end-to-end test phù hợp với ranh giới đó.

## 15. Versioning và tương thích khi số định dạng tăng

Giả sử trong tương lai hệ thống thêm:

- JSON v2: `amountDecimal` thay `amountMinor`.
- XML v1: đối tác cũ chỉ hỗ trợ XML.
- Protobuf v1: hệ thống có lưu lượng lớn và cần schema nhị phân.
- Vendor media type: `application/vnd.example.order+json`.

Có thể dùng bảng ánh xạ:

| Media type | Contract version | Parser/mapper | Trạng thái |
| --- | --- | --- | --- |
| `application/json` | v1 | JSON v1 → CanonicalOrder | Đang hỗ trợ |
| `text/plain` | v1 | Text v1 → CanonicalOrder | Đang hỗ trợ |
| `application/json` | v2 | JSON v2 → CanonicalOrder | Chỉ bật sau khi có test |
| `application/xml` | v1 | XML v1 → CanonicalOrder | Chỉ bật sau khi bảo vệ XML parser |
| `application/vnd.example.order+json` | v1 | Vendor JSON v1 mapper | Contract riêng |

Khi triển khai mapper mới, giữ mapper cũ trong thời gian backlog còn message cũ. Đừng đổi ngữ nghĩa parser v1 trong khi các message cũ vẫn có thể được replay.

### 15.1. Một body, nhiều schema version có thể khác nhau

`Content-Type: application/json` không đủ để xác định `amountMinor` hay `amountDecimal` có hợp đồng gì. Nếu hai version cùng media type, cần chọn dựa trên **contract version đã xác minh**; không nên đoán version bằng cách “field nào tồn tại thì parse field đó” trừ khi đó chính là một quy tắc compatibility đã được phê duyệt và test.

### 15.2. Cẩn thận với unknown fields

Một parser JSON đọc các field cần thiết có thể bỏ qua field thừa. Điều đó có lợi cho forward compatibility trong một số trường hợp, nhưng rủi ro nếu field mới **đổi cách hiểu** của dữ liệu. Ví dụ thêm `taxIncluded=false` có thể khiến `total` mang ý nghĩa khác. Schema validation và consumer-driven contract tests phải bảo vệ **ngữ nghĩa**, không chỉ cấu trúc.

## 16. Observability: vì sao chọn parser này, đã chuyển đúng chưa?

Gợi ý điểm đo trong flow:

| Điểm quan sát | Dữ liệu nên thu thập | Câu hỏi |
| --- | --- | --- |
| Inbound adapter | Media type, kích thước bytes, source đã xác thực | Ai gửi và gửi định dạng gì? |
| Contract gate | `contractVersion`, accepted/rejected, reason code | Phiên bản này có được hỗ trợ? |
| Transformer | Parser selected, latency, success/failure | Parse sai ở định dạng nào? |
| Canonical validation | Field/rule invalid, số dòng, schema version | DTO canonical có đúng hợp đồng? |
| Downstream Router | Lane/decision, version | Message đi nhánh nghiệp vụ nào? |
| Outbound Adapter | Send result, retry, timeout | Message đã tới hệ thống ngoài? |
| Business consumer | Success/error/idempotency outcome | Đơn đã được tạo hay chưa? |

Có thể dùng `ChannelInterceptor`, Wire Tap, metrics và distributed tracing của hệ thống để quan sát. Tuy nhiên:

- Không log nguyên raw bytes nếu payload có PII, token, dữ liệu tài chính hoặc nội dung không đáng tin.
- Với metrics, `mediaType`, `contractVersion`, `mappingResult` và `errorCode` nên có **allowlist/cardinality thấp**.
- `orderId` và `businessCorrelationId` phù hợp cho log/trace có quyền truy cập, **không** là metric tag thông thường.
- Không coi `postSend(sent=true)` ở output queue là bằng chứng hệ thống ngoài đã xử lý xong.
- Lưu bản schema/mapping version hoặc cấu hình parser áp dụng nếu cần tái hiện lỗi khi replay.

## 17. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra `payload instanceof byte[]` rồi đoán JSON | Byte[] có thể chứa mọi định dạng | Xác thực media type + schema version |
| Thử lần lượt JSON, XML, text đến khi parse được | Nhập nhằng contract, nguy cơ parser confusion | Chọn parser từ allowlist, fail closed |
| Nhầm Content-Type với loại sự kiện nghiệp vụ | Chọn nhầm handler/owner | Chia parser selection và business routing |
| Bỏ qua charset và dùng encoding mặc định máy | Mất dữ liệu, sai ký tự Unicode | Contract UTF-8 và strict decoder |
| Dùng `double` cho tiền | Sai precision và boundary | `BigDecimal`, scale theo currency |
| Dùng `split(",")` cho CSV tổng quát | Sai khi field có quote/comma/newline | Dùng CSV parser phù hợp |
| Parse XML không tắt DTD/external entities | XXE hoặc tiêu tốn tài nguyên | XML parser hardening + resource limits |
| Giữ `contentType=application/json` sau khi payload đã là DTO | Downstream deserialize sai | Cập nhật/bỏ header về biểu diễn gốc |
| Dựa vào header Content-Type để cấp quyền | Client có thể giả mạo metadata | AuthN/AuthZ và trust boundary ở ingress |
| Cho mọi vendor `+json` đi cùng mapper | Schema/ngữ nghĩa có thể khác | Mapping theo media type + version được duyệt |
| Drop mọi lỗi parse mà không ghi reason | Khó vận hành, khó sửa hợp đồng | Error/quarantine channel, mã lỗi an toàn |
| Retry vô hạn malformed payload | Tiêu tốn tài nguyên mà không sửa dữ liệu | Reject/DLQ, phân loại lỗi |
| Xem Transformer pass là nghiệp vụ đã hoàn tất | Downstream vẫn có thể lỗi | Theo dõi business completion riêng |
| Test mapper nhưng bỏ integration/serialization test | Channel wiring/JSON output có thể sai | Test các boundary đúng contract |

## 18. Checklist trước khi triển khai

- [ ] Danh sách media type được hỗ trợ và contract version được viết rõ.
- [ ] Header `contentType` được ánh xạ từ transport đúng và kiểm tra định dạng.
- [ ] Nguồn và quyền gửi được xác thực **độc lập** với MIME header.
- [ ] Có quy định khi thiếu MIME, sai charset hoặc body không khớp Content-Type.
- [ ] Parser có giới hạn bytes/depth/time và phòng vệ cho XML, CSV, compressed payload nếu hỗ trợ.
- [ ] Mapper dùng kiểu tiền, ngày giờ, enum và null theo ngữ nghĩa của từng schema.
- [ ] Payload canonical bất biến hoặc có chiến lược copy dữ liệu mutable.
- [ ] Header Content-Type được cập nhật/bỏ khi biểu diễn thay đổi từ bytes sang DTO.
- [ ] Correlation/schema version/trace headers được giữ theo hợp đồng từng boundary.
- [ ] Có unit tests cho parser/mapping và integration tests cho Transformer/channel.
- [ ] Có serialization/contract tests với hệ thống gửi và nhận thực tế.
- [ ] Phân biệt malformed data, unsupported contract, mapper bug và downstream timeout.
- [ ] Retry/idempotency được thiết kế tại consumer có side effect, không nhầm với lỗi parse.
- [ ] Metrics, logs và error/DLQ không làm lộ payload nhạy cảm.
- [ ] Có kế hoạch hỗ trợ v1 khi giới thiệu v2 và khi replay message cũ.

## 19. Bài tập vận dụng

Một hệ thống thanh toán nhận `PaymentNotification` qua hai định dạng:

**JSON v1:**

~~~json
{
  "paymentId": "PAY-42",
  "currency": "USD",
  "amountMinor": 2505,
  "eventType": "AUTHORIZED"
}
~~~

**XML v1:**

~~~xml
<payment>
  <id>PAY-42</id>
  <currencyCode>USD</currencyCode>
  <minorAmount>2505</minorAmount>
  <kind>AUTHORIZED</kind>
</payment>
~~~

**Yêu cầu:**

1. Định nghĩa `CanonicalPayment` bất biến chứa `paymentId`, `currency`, `amount` và enum `eventType`.
2. Lập bảng mapping JSON/XML v1 → canonical, chỉ rõ `amountMinor=2505` thành `BigDecimal("25.05")`.
3. Thiết kế lựa chọn mapper theo `(Content-Type, contractVersion)`; XML không được dùng JSON parser chỉ vì body có trường cùng nghĩa.
4. Cấu hình XML parser chống XXE và giới hạn số lượng entity, chiều sâu/tài nguyên.
5. Viết Spring Integration flow gồm inbound adapter → Transformer → Filter/Router → các handler theo `eventType`.
6. Kiểm thử positive/negative: JSON, XML, MIME không hỗ trợ, header thiếu, sai encoding, số tiền âm, unknown enum và malformed XML.
7. Sau khi chuyển sang `CanonicalPayment`, bạn sẽ xử lý `contentType` và `businessCorrelationId` thế nào?
8. Nếu `PaymentAuthorized` được redeliver hai lần, vì sao Transformer chạy lại không nguy hiểm bằng việc downstream ghi nhận thanh toán hai lần? Hãy đề xuất idempotency key và vị trí áp dụng.

**Gợi ý:** nếu JSON và XML thuộc **cùng một schema nghiệp vụ**, hai parser có thể tạo source DTO tương đương rồi chuyển vào cùng canonical mapper. Tuy nhiên, phải kiểm thử mapping theo contract thật; đừng tự đoán tên field hoặc nội dung XML dựa vào `Content-Type` đơn thuần.

## 20. Tổng kết

**Transformer theo Content-Type** giúp một flow nhận nhiều biểu diễn dữ liệu và đưa chúng về một **schema canonical nhất quán**. Quy trình đúng là **xác minh metadata/contract → chọn parser được hỗ trợ → decode an toàn → kiểm tra ngữ nghĩa → tạo payload canonical → điều phối nghiệp vụ**. `Content-Type` xác định cách giải mã thông điệp, **không phải** quyền truy cập hoặc loại lệnh nghiệp vụ.

Trong Spring Integration, một Transformer có thể xem `MessageHeaders.CONTENT_TYPE` và trả về DTO mới, nhưng cần chủ động xử lý headers khi biểu diễn thay đổi. Để hệ thống dễ mở rộng và chẩn đoán, kết hợp Filter, Enricher, Router, Gateway, Splitter/Aggregator, retry, error channel, correlation, idempotency và kiểm thử từ parser tới adapter ngoài. Đừng chỉ kiểm tra “parse được”; hãy chứng minh **đúng schema, đúng số tiền, đúng phiên bản, đúng nhánh và không tạo side effect trùng**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Message Translator, Content-Based Router, Canonical Data Model); tài liệu Spring Integration về Transformers, Message Channels, Java DSL, Error Handling và Testing; tài liệu Spring Messaging về `MessageHeaders.CONTENT_TYPE`; tài liệu Spring Framework về `MimeType` và `MessageBuilder`; tài liệu Jackson Databind và Java SE về `BigDecimal`, `StandardCharsets`.

