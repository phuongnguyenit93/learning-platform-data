# Lựa chọn TokenBuffer khi cần chuyển tiếp hoặc đọc lại cấu trúc

Trong Jackson, `JsonParser` đọc JSON theo từng token và `JsonGenerator` ghi JSON theo từng token. Cách xử lý streaming này tiết kiệm bộ nhớ khi ứng dụng chỉ cần đi qua dữ liệu một lần. Nhưng có những tình huống ứng dụng cần giữ tạm một phần cấu trúc để xem trước, đọc lại, chuyển cho một bước xử lý khác hoặc ghi ra sau khi đã quyết định cách xử lý. `TokenBuffer` được thiết kế cho nhu cầu đó.

`TokenBuffer` là một vùng đệm token trong bộ nhớ thuộc Jackson Databind (`com.fasterxml.jackson.databind.util.TokenBuffer`). Nó hoạt động như một `JsonGenerator` để nhận token và có thể tạo `JsonParser` mới để đọc lại các token đã ghi. Nhờ vậy, ứng dụng có thể chuyển tiếp cấu trúc JSON giữa streaming API và Databind mà không cần chuyển ngay toàn bộ dữ liệu thành chuỗi JSON hoặc `JsonNode`.

TokenBuffer hữu ích khi cần **ghi tạm rồi đọc lại**, **sao chép một cấu trúc từ parser**, hoặc **chuyển token từ một bước xử lý sang bước khác**. Nó vẫn giữ dữ liệu trong heap; nếu buffer chứa toàn bộ một tài liệu rất lớn, bộ nhớ vẫn tăng theo lượng token được giữ. Vì vậy, TokenBuffer là công cụ trung gian linh hoạt, không phải giải pháp streaming có bộ nhớ hằng số.

## 1. TokenBuffer nằm ở đâu trong kiến trúc Jackson?

Jackson có thể làm việc ở nhiều mức:

- **Streaming:** `JsonParser` đọc token, `JsonGenerator` ghi token.
- **Tree model:** `JsonNode` giữ cấu trúc object/array dưới dạng cây để truy cập và sửa đổi ngẫu nhiên.
- **Databind:** `ObjectMapper`, `ObjectReader` và `ObjectWriter` ánh xạ giữa token JSON với object Java.
- **TokenBuffer:** giữ một chuỗi token trong heap, có thể phát lại chuỗi đó thông qua parser hoặc serialize sang generator khác.

Sơ đồ luồng dữ liệu:

```text
Nguồn JSON
    |
    v
JsonParser -----> TokenBuffer -----> JsonParser mới
                     |                    |
                     |                    +--> ObjectMapper.readValue(...)
                     |                    +--> ObjectMapper.readTree(...)
                     |
                     +------------------------> JsonGenerator khác
                                                (serialize buffer)

Java object / JsonNode ----> ObjectMapper / JsonGenerator
                                   |
                                   v
                              TokenBuffer
```

TokenBuffer giữ token và giá trị tương ứng, không phải một bản sao nguyên văn các byte JSON đầu vào. Nó không được dùng để bảo toàn khoảng trắng, cách xuống dòng, thứ tự escape nguyên bản hoặc chính xác cách viết lexical của tài liệu.

## 2. Tạo TokenBuffer và ghi token vào buffer

`TokenBuffer` nằm trong package `com.fasterxml.jackson.databind.util`, vì vậy project cần Jackson Databind. Một constructor thường dùng nhận `ObjectCodec` và cờ native type IDs:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.util.TokenBuffer;

ObjectMapper mapper = new ObjectMapper();
TokenBuffer buffer = new TokenBuffer(mapper, false);
```

Truyền mapper giúp buffer có codec khi cần xử lý các thao tác liên quan đến object. Tham số `false` cho biết buffer không được cấu hình để lưu native type IDs từ backend streaming hỗ trợ chúng. Với các ứng dụng thông thường chỉ xử lý JSON, đây là cách khởi tạo phổ biến.

`TokenBuffer` có API ghi tương tự `JsonGenerator`, vì vậy có thể tạo cấu trúc trực tiếp:

```java
buffer.writeStartObject();
buffer.writeNumberField("id", 101);
buffer.writeStringField("name", "An");
buffer.writeBooleanField("active", true);
buffer.writeEndObject();
```

Các token được lưu trong buffer thay vì ghi ngay ra file hoặc network. Khi cần sử dụng, ứng dụng có thể tạo parser để đọc lại hoặc phát buffer sang generator đích.

Vì `TokenBuffer` kế thừa `JsonGenerator`, có thể dùng các thao tác như `writeStartObject`, `writeFieldName`, `writeString`, `writeNumber`, `writeStartArray`, `writeEndArray`, `writeObject` và `writeTree` theo ngữ cảnh tương ứng. Các quy tắc grammar JSON vẫn áp dụng: mỗi field name phải có một value, container phải đóng đúng thứ tự.

## 3. Đọc lại buffer bằng asParser

Khi đã ghi xong token, gọi `asParser(...)` để tạo một `JsonParser` đọc lại nội dung buffer:

```java
try {
    buffer.writeStartObject();
    buffer.writeNumberField("id", 101);
    buffer.writeStringField("name", "An");
    buffer.writeEndObject();

    try (JsonParser parser = buffer.asParser(mapper)) {
        JsonNode node = mapper.readTree(parser);
        System.out.println(node.get("name").asText());
    }
} finally {
    buffer.close();
}
```

`asParser(mapper)` tạo parser mới có codec được cung cấp. Có thể dùng parser này với `ObjectMapper.readTree(...)`, `readValue(...)` hoặc API streaming để xử lý từng token.

Điểm quan trọng là `asParser(...)` không trả về parser nguồn ban đầu. Nó tạo một cursor đọc trên dữ liệu đã lưu trong buffer. Vì vậy, có thể tạo parser khác cho một lượt đọc khác khi buffer vẫn còn tồn tại.

## 4. Đọc cùng một cấu trúc nhiều lần

Một use case điển hình là cần xem cấu trúc trước, sau đó deserialize thành kiểu Java cụ thể. Thay vì parse nguồn ban đầu nhiều lần, có thể buffer token một lần rồi tạo nhiều parser độc lập.

```java
TokenBuffer buffer = new TokenBuffer(mapper, false);

try {
    buffer.writeStartObject();
    buffer.writeNumberField("id", 101);
    buffer.writeStringField("name", "An");
    buffer.writeEndObject();

    // Lượt 1: xem cấu trúc như JsonNode.
    try (JsonParser treeParser = buffer.asParser(mapper)) {
        JsonNode tree = mapper.readTree(treeParser);
        System.out.println(tree.fieldNames());
    }

    // Lượt 2: deserialize cùng token thành DTO.
    try (JsonParser userParser = buffer.asParser(mapper)) {
        User user = mapper.readValue(userParser, User.class);
        process(user);
    }
} finally {
    buffer.close();
}
```

Mỗi parser có vị trí đọc riêng. Đọc hết parser thứ nhất không làm parser thứ hai tự động chuyển đến cuối. Buffer phải còn sống trong suốt thời gian các parser cần đọc nó.

Đọc lại hữu ích khi quyết định kiểu đích chỉ được biết sau khi đã xem một phần cấu trúc, hoặc khi một luồng cần kiểm tra metadata trước khi chuyển payload đến bước deserialize tiếp theo. Nếu đã biết kiểu đích từ đầu và chỉ cần một lần đọc, đọc trực tiếp từ parser nguồn thường đơn giản hơn.

## 5. Sao chép một cấu trúc từ JsonParser vào TokenBuffer

TokenBuffer thường được dùng để giữ lại một root value hoặc một nhánh JSON mà parser đang đứng tại đó. Có thể dùng `copyCurrentStructure(...)` để sao chép token hiện tại cùng toàn bộ cấu trúc con.

```java
JsonFactory factory = mapper.getFactory();

try (JsonParser source = factory.createParser(inputStream)) {
    // Đưa parser đến token đầu tiên của value cần giữ.
    JsonToken token = source.nextToken();
    if (token == null) {
        throw new IOException("JSON input is empty");
    }

    TokenBuffer buffer = new TokenBuffer(mapper, false);
    try {
        buffer.copyCurrentStructure(source);

        try (JsonParser replay = buffer.asParser(mapper)) {
            JsonNode copied = mapper.readTree(replay);
            process(copied);
        }
    } finally {
        buffer.close();
    }
}
```

`copyCurrentStructure(source)` bắt đầu từ token hiện tại. Nếu token hiện tại là `START_OBJECT` hoặc `START_ARRAY`, phương thức sao chép cả cấu trúc lồng nhau cho đến token kết thúc tương ứng. Nếu token hiện tại là scalar, nó sao chép scalar đó.

Sau khi sao chép, parser nguồn đã tiến qua cấu trúc vừa copy. Ứng dụng có thể tiếp tục đọc phần còn lại của tài liệu nguồn nếu contract cho phép. Nếu muốn copy từng phần tử của một array, cần điều khiển parser theo token và gọi copy tại đúng token bắt đầu của mỗi phần tử.

Không gọi `copyCurrentStructure` khi parser chưa đứng ở token của value mong muốn. Nếu `getCurrentToken()` là `null`, hãy gọi `nextToken()` và kiểm tra kết quả trước.

## 6. Chuyển tiếp cấu trúc từ TokenBuffer sang JsonGenerator

Sau khi buffer đã chứa token, có thể phát nội dung sang generator khác bằng `serialize(...)`:

```java
TokenBuffer buffer = new TokenBuffer(mapper, false);

try {
    buffer.writeStartObject();
    buffer.writeStringField("code", "A1");
    buffer.writeNumberField("quantity", 5);
    buffer.writeEndObject();

    try (JsonGenerator output = mapper.createGenerator(outputStream)) {
        output.writeStartObject();
        output.writeStringField("source", "inventory-service");
        output.writeFieldName("payload");

        buffer.serialize(output);

        output.writeEndObject();
    }
} finally {
    buffer.close();
}
```

Kết quả có cấu trúc:

```json
{
  "source": "inventory-service",
  "payload": {
    "code": "A1",
    "quantity": 5
  }
}
```

Generator đích chịu trách nhiệm cho object bên ngoài. `buffer.serialize(output)` phát các token đã lưu tại vị trí value của field `payload`. Vì vậy, buffer cần chứa đúng một value hoàn chỉnh cho vị trí đó.

`serialize(...)` hữu ích khi một bước tạo hoặc biến đổi token tách biệt với bước xuất cuối. Nếu có thể ghi trực tiếp token vào generator đích, không cần buffer trung gian.

## 7. Kết hợp TokenBuffer với ObjectMapper và Databind

TokenBuffer có thể làm cầu nối giữa streaming và Databind. Ví dụ, ứng dụng nhận một cấu trúc JSON từ parser, buffer nó, rồi deserialize thành DTO sau khi đã quyết định kiểu đích:

```java
TokenBuffer buffer = new TokenBuffer(mapper, false);

try {
    buffer.copyCurrentStructure(sourceParser);

    try (JsonParser replay = buffer.asParser(mapper)) {
        Order order = mapper.readValue(replay, Order.class);
        process(order);
    }
} finally {
    buffer.close();
}
```

Có thể đọc thành `JsonNode` trước để kiểm tra một số field điều khiển, sau đó tạo parser thứ hai để deserialize thành subtype hoặc DTO phù hợp. Ví dụ, payload có trường `kind` quyết định kiểu message:

```java
String kind;

try (JsonParser parser = buffer.asParser(mapper)) {
    JsonNode header = mapper.readTree(parser);
    kind = header.path("kind").asText();
}

Class<?> targetType = switch (kind) {
    case "created" -> CreatedEvent.class;
    case "cancelled" -> CancelledEvent.class;
    default -> throw new IOException("Unsupported event kind: " + kind);
};

try (JsonParser parser = buffer.asParser(mapper)) {
    Object event = mapper.readValue(parser, targetType);
    process(event);
}
```

Ví dụ trên minh họa quyết định kiểu từ metadata. Trong ứng dụng thực tế, nên dùng registry/allowlist kiểu rõ ràng và không nhận tên class tùy ý từ payload để nạp class hoặc deserialize một kiểu bất kỳ.

## 8. TokenBuffer khác gì JsonNode và byte/string buffer?

Các công cụ này đều có thể giữ dữ liệu tạm, nhưng lưu những thứ khác nhau.

| Cơ chế | Lưu trữ | Điểm mạnh | Hạn chế |
|---|---|---|---|
| `TokenBuffer` | Chuỗi token và giá trị trong heap | Phát lại token, nối streaming với Databind, có thể tạo parser nhiều lần | Không phải bản sao byte JSON; bộ nhớ tăng theo lượng token |
| `JsonNode` | Cây object/array và scalar node | Truy cập ngẫu nhiên, tra field, sửa cây | Tạo node và container; cần giữ toàn bộ cây để truy cập |
| `String` / `StringWriter` | Văn bản JSON | Dễ lưu, log hoặc truyền dưới dạng text | Có thể cần encode/decode lại; không giữ trạng thái token có kiểu |
| `byte[]` / `ByteArrayOutputStream` | Byte JSON đã mã hóa | Giữ byte output và có thể truyền trực tiếp | Có thể cần parse lại; tạo/copy byte array lớn tốn heap |
| File hoặc spool stream | Byte trên storage/stream | Có thể xử lý dữ liệu lớn mà không giữ toàn bộ trong heap | Cần quản lý I/O, lỗi, vòng đời và cleanup |

Chọn theo việc ứng dụng cần làm:

- Cần tra cứu/sửa field nhiều lần: `JsonNode` thường trực quan hơn.
- Cần phát lại token hoặc trì hoãn deserialize: `TokenBuffer` phù hợp.
- Cần giữ nguyên byte để ký số, hash hoặc chuyển tiếp nguyên bản: giữ byte nguồn; TokenBuffer không bảo toàn lexical representation.
- Cần xử lý một lần với bộ nhớ thấp: streaming trực tiếp thường phù hợp hơn.

## 9. TokenBuffer không phải giải pháp bộ nhớ hằng số

Tên gọi “buffer” đôi khi khiến người dùng nghĩ dữ liệu được ghi ra file tạm hoặc bộ nhớ có giới hạn. `TokenBuffer` giữ token trong bộ nhớ JVM. Khi số token tăng, buffer phải lưu thêm segment và các giá trị liên quan.

Ví dụ, nếu một JSON có một triệu phần tử và toàn bộ array được copy vào TokenBuffer, buffer vẫn phải giữ token cho cả triệu phần tử. Việc không tạo `JsonNode` có thể tránh một số chi phí node/container của tree model, nhưng không biến thao tác thành streaming bounded-memory.

Mức tiêu thụ thực tế phụ thuộc số token, tên field, scalar value, cấu trúc lồng nhau, kiểu dữ liệu và phiên bản Jackson. Không có hệ số cố định để kết luận TokenBuffer luôn nhỏ hơn JsonNode hoặc luôn nhanh hơn parse lại nguồn.

Nếu tài liệu quá lớn, hãy cân nhắc:

- Chỉ buffer nhánh cần thiết thay vì toàn bộ root document.
- Xử lý từng record rồi giải phóng buffer tương ứng.
- Dùng streaming trực tiếp nếu không cần đọc lại.
- Spool ra file/byte stream nếu cần trì hoãn xử lý nhưng dữ liệu vượt ngân sách heap.

## 10. TokenBuffer không bảo toàn nguyên văn JSON

TokenBuffer lưu biểu diễn token và giá trị, không lưu toàn bộ ký tự đầu vào theo đúng byte gốc. Khi phát lại qua generator, JSON có thể có khoảng trắng khác, escape khác hoặc cách biểu diễn số khác mà vẫn mang cùng giá trị JSON.

Ví dụ, hai input:

```json
{"amount":1.0}
```

```json
{ "amount" : 1.00 }
```

có thể biểu diễn giá trị tương đương trong nhiều ngữ cảnh, nhưng khác lexical representation. Sau khi parse và buffer token, không nên kỳ vọng output giữ chính xác số chữ số thập phân, khoảng trắng hoặc cách escape ban đầu.

Do đó, không dùng TokenBuffer để bảo toàn byte phục vụ chữ ký số, hash của payload nguyên bản, forensic capture hoặc yêu cầu proxy chuyển tiếp byte-identical. Trong các trường hợp đó, giữ byte gốc hoặc dùng cơ chế lưu trữ raw payload riêng, đồng thời kiểm soát encoding và framing.

## 11. Quản lý vòng đời và parser độc lập

TokenBuffer giữ các object và giá trị trong heap cho đến khi không còn tham chiếu và có thể được GC thu hồi. Hãy đóng buffer sau khi hoàn tất việc ghi/đọc lại, và đóng từng parser tạo ra từ `asParser(...)` theo quy ước tài nguyên.

Một pattern dễ quản lý là:

```java
TokenBuffer buffer = new TokenBuffer(mapper, false);
try {
    // Ghi hoặc copy token vào buffer.

    try (JsonParser replay = buffer.asParser(mapper)) {
        // Đọc lại token.
    }
} finally {
    buffer.close();
}
```

Đóng parser replay không thay thế việc giải phóng tham chiếu đến buffer. Nếu ứng dụng giữ buffer trong cache, queue hoặc field dài hạn, dữ liệu vẫn còn được giữ trong heap. Không nên tạo buffer rồi lưu không giới hạn cho mỗi request.

Sau khi hoàn tất việc ghi buffer, hãy xem nó như dữ liệu chỉ đọc trong giai đoạn replay. Tránh vừa ghi thêm token vừa tạo parser/đọc buffer ở nhiều nơi nếu không có thiết kế đồng bộ rõ ràng. Cách dễ dự đoán là hoàn tất buffer trước, rồi tạo các parser cần thiết.

## 12. Xử lý lỗi khi buffer cấu trúc

TokenBuffer có thể nhận token từ parser nguồn hoặc từ các lời gọi generator. Nếu parser nguồn gặp JSON sai cú pháp trong lúc copy, thao tác copy có thể ném `JsonParseException` hoặc `IOException` trước khi buffer chứa đủ cấu trúc. Nếu code tự ghi token và quên đóng container, dữ liệu buffer có thể không phải một root value hoàn chỉnh.

Một số nguyên tắc:

1. Chỉ copy khi parser đang ở đúng token đầu của value cần giữ.
2. Để `copyCurrentStructure(...)` xử lý toàn bộ cấu trúc con, không tự bỏ qua token kết thúc giữa chừng.
3. Nếu tự ghi token, đóng mọi object/array đã mở.
4. Khi replay, kiểm tra kiểu root và deserialize theo kiểu đích đã chọn.
5. Nếu buffer chứa dữ liệu từ nguồn ngoài, áp dụng giới hạn input và validation schema ở bước phù hợp.
6. Đóng buffer trong `finally` hoặc try-with-resources sau khi mọi parser replay đã hoàn tất.

TokenBuffer chỉ là cơ chế giữ và phát lại token. Nó không tự xác nhận payload đáp ứng quy tắc nghiệp vụ hoặc quyền truy cập.

## 13. Ví dụ tổng hợp: giữ một payload để phân loại rồi deserialize

Giả sử một stream chứa nhiều event JSON trong một array. Mỗi event có trường `type`, và ứng dụng cần đọc metadata trước khi biết class đích. Có thể copy từng object event vào một TokenBuffer, xem `type`, rồi đọc lại thành DTO tương ứng.

```java
public void processEvents(
        InputStream input,
        ObjectMapper mapper
) throws IOException {
    try (JsonParser source = mapper.getFactory().createParser(input)) {
        if (source.nextToken() != JsonToken.START_ARRAY) {
            throw new IOException("Expected an array of events");
        }

        while (source.nextToken() == JsonToken.START_OBJECT) {
            TokenBuffer buffer = new TokenBuffer(mapper, false);
            try {
                // Copy toàn bộ object event hiện tại.
                buffer.copyCurrentStructure(source);

                String type;
                try (JsonParser headerParser = buffer.asParser(mapper)) {
                    JsonNode header = mapper.readTree(headerParser);
                    type = header.path("type").asText();
                }

                switch (type) {
                    case "created" -> {
                        try (JsonParser eventParser = buffer.asParser(mapper)) {
                            CreatedEvent event = mapper.readValue(
                                    eventParser,
                                    CreatedEvent.class
                            );
                            processCreated(event);
                        }
                    }
                    case "cancelled" -> {
                        try (JsonParser eventParser = buffer.asParser(mapper)) {
                            CancelledEvent event = mapper.readValue(
                                    eventParser,
                                    CancelledEvent.class
                            );
                            processCancelled(event);
                        }
                    }
                    default -> throw new IOException(
                            "Unsupported event type: " + type
                    );
                }
            } finally {
                buffer.close();
            }
        }

        if (source.currentToken() != JsonToken.END_ARRAY) {
            throw new IOException("Malformed event array");
        }
    }
}
```

Ví dụ minh họa mô hình copy từng event rồi đọc lại. Trong code production, cần bổ sung kiểm tra trường hợp array kết thúc, token không mong đợi, phần tử null hoặc kiểu scalar; cũng cần kiểm tra trailing token sau root theo contract. Vì mỗi buffer chỉ giữ một event, lượng dữ liệu tạm được giới hạn theo kích thước event lớn nhất thay vì toàn bộ array.

Nếu event có thể rất lớn, ngay cả buffer theo từng event vẫn cần giới hạn kích thước hoặc chuyển sang xử lý streaming trực tiếp. Không nên dùng TokenBuffer như một cách né giới hạn payload.

## 14. Khi nào nên chọn TokenBuffer?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Cần đọc một cấu trúc từ parser rồi deserialize sau | `TokenBuffer` | Giữ token và tạo parser replay |
| Cần xem metadata trước rồi chọn DTO | `TokenBuffer` | Có thể đọc header rồi replay payload |
| Cần ghi token tạm rồi phát vào generator khác | `TokenBuffer` | Hoạt động như generator và có `serialize(...)` |
| Cần truy cập field bất kỳ hoặc sửa cây | `JsonNode` | Tree model thuận tiện cho thao tác ngẫu nhiên |
| Chỉ cần xử lý một lượt, không cần giữ lại | `JsonParser` trực tiếp | Tránh buffer toàn bộ cấu trúc |
| Cần giữ byte JSON nguyên bản | `byte[]`, file hoặc raw stream | TokenBuffer không giữ lexical bytes |
| Cần xử lý payload lớn vượt ngân sách heap | Streaming hoặc spool storage | TokenBuffer vẫn nằm trong heap |

TokenBuffer phù hợp nhất khi cần một điểm trung gian có khả năng replay giữa các bước xử lý. Nếu không có nhu cầu đọc lại hoặc chuyển tiếp token, thêm buffer chỉ làm tăng độ phức tạp và bộ nhớ.

## 15. Ghi nhớ

`TokenBuffer` là một `JsonGenerator` lưu token trong heap và có thể tạo `JsonParser` mới bằng `asParser(...)` để đọc lại. Nó giúp sao chép cấu trúc từ parser bằng `copyCurrentStructure(...)`, đọc cùng token nhiều lần, trì hoãn chọn kiểu đích và chuyển token sang generator khác bằng `serialize(...)`.

TokenBuffer lưu biểu diễn token, không phải byte JSON nguyên bản; nó không giữ whitespace/lexical representation và không phù hợp cho chữ ký hoặc chuyển tiếp byte-identical. Nó cũng không phải giải pháp bộ nhớ hằng số: buffer lớn vẫn giữ lượng token lớn trong heap. Hãy dùng nó cho cấu trúc vừa phải cần replay, giới hạn phạm vi buffer theo từng phần tử khi xử lý dữ liệu lớn, đóng parser/buffer đúng vòng đời và chọn `JsonNode`, streaming trực tiếp hoặc byte/file buffer theo đúng nhu cầu.
