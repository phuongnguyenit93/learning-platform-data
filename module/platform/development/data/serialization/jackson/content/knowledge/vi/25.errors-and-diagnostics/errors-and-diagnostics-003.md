# Nhận diện dữ liệu bị cắt dở hoặc token không đúng kỳ vọng

Khi đọc JSON bằng Jackson, lỗi không phải lúc nào cũng xuất phát từ dữ liệu sai cú pháp. Có trường hợp request bị cắt giữa chừng do kết nối đóng sớm; có trường hợp JSON hoàn chỉnh nhưng code gọi `nextToken()` sai thời điểm; cũng có trường hợp cú pháp hợp lệ nhưng token thực tế không đúng kiểu mà DTO hoặc custom deserializer mong đợi.

Để chẩn đoán đúng, cần phân biệt ba nhóm tình huống:

- **Input bị thiếu hoặc bị cắt dở:** parser cần thêm byte nhưng nguồn đã kết thúc, hoặc document chưa hoàn chỉnh khi EOF xuất hiện.
- **Token không đúng kỳ vọng:** parser đọc được token hợp lệ, nhưng token đó không phù hợp với trạng thái xử lý hiện tại, ví dụ code mong `START_OBJECT` nhưng nhận `START_ARRAY`.
- **Lỗi ánh xạ dữ liệu:** JSON có cú pháp hợp lệ, nhưng giá trị không thể chuyển thành kiểu Java đích hoặc vi phạm cấu trúc DTO.

Nhìn vào loại exception, vị trí parser, token hiện tại và đường dẫn property sẽ giúp xác định lỗi nằm ở tầng truyền dữ liệu, cú pháp JSON, trạng thái đọc hay Databind.

## 1. Một JSON document hoàn chỉnh có những ranh giới nào?

JSON document thường là một giá trị gốc: object, array hoặc scalar. Ví dụ:

```json
{"id":"ORD-1001","total":125.50}
```

Khi parser đọc document này, token flow cơ bản là:

```text
START_OBJECT
  FIELD_NAME "id"
  VALUE_STRING "ORD-1001"
  FIELD_NAME "total"
  VALUE_NUMBER_FLOAT 125.50
END_OBJECT
```

Parser đã hoàn tất document khi token gốc kết thúc và không còn nội dung JSON cần đọc. Khoảng trắng sau giá trị gốc được phép. Nhưng nếu object chưa có `END_OBJECT`, array chưa có `END_ARRAY`, string chưa đóng dấu nháy hoặc number có exponent chưa hoàn chỉnh, input có thể bị cắt dở hoặc không hợp lệ.

Một số ví dụ:

| Input | Tình trạng |
| --- | --- |
| `{"id":"A"}` | JSON object hoàn chỉnh |
| `{"id":"A"` | Object chưa đóng; có thể bị cắt dở |
| `[1,2,3]` | JSON array hoàn chỉnh |
| `[1,2,` | Array chưa hoàn chỉnh |
| `{"name":"An}` | String chưa có dấu nháy đóng đúng vị trí |
| `1e` | Number có exponent chưa hoàn chỉnh |
| `{"id":}` | Cú pháp sai: thiếu value sau dấu hai chấm |

Không nên kết luận mọi lỗi EOF đều là lỗi mạng. Input có thể bị cắt do producer ghi thiếu, file bị truncate, framing sai hoặc code đọc nhầm số byte.

## 2. EOF và JsonEOFException

Với parser blocking đọc từ `InputStream`, nếu nguồn kết thúc khi parser vẫn cần thêm ký tự/byte để hoàn thành một cấu trúc, Jackson thường ném lỗi parse mô tả unexpected end-of-input. Trong một số tình huống, loại exception chuyên biệt `JsonEOFException` được dùng để biểu diễn EOF xảy ra khi parser đang ở trong một cấu trúc chưa hoàn chỉnh.

Ví dụ input bị cắt:

```java
String json = "{\"orderId\":\"ORD-1001\",\"items\":[1,2";

try (JsonParser parser = new JsonFactory().createParser(json)) {
    while (parser.nextToken() != null) {
        // Xử lý token.
    }
}
```

Parser có thể đọc được nhiều token đầu, nhưng đến cuối nguồn vẫn đang ở trong array và object chưa đóng. Lúc đó Jackson báo lỗi thay vì coi phần JSON chưa hoàn chỉnh là document hợp lệ.

Với `ObjectMapper.readValue()`, lỗi thường được bọc trong hệ exception của Jackson, ví dụ `JsonParseException` hoặc một kiểu `JsonProcessingException` tương ứng. Thông điệp có thể cho biết parser đang mong đợi thêm dấu ngoặc, dấu nháy hoặc value.

### 2.1. Input rỗng khác với input bị cắt giữa chừng

Input rỗng:

```text
<không có byte JSON nào>
```

Không có token gốc để ánh xạ. Khi gọi `ObjectMapper.readValue()` cho một kiểu DTO, Jackson thường báo lỗi không có nội dung để map (ví dụ `MismatchedInputException`).

Input bị cắt giữa cấu trúc:

```json
{"id":"A"
```

Parser đã bắt đầu một document nhưng không thể hoàn tất cấu trúc. Đây là tình huống EOF trong khi parse, thường dẫn đến lỗi parse về unexpected end-of-input.

Input chỉ có khoảng trắng cũng không chứa JSON value. Vì vậy, cần phân biệt empty body, body chỉ có whitespace và document bắt đầu rồi bị cắt.

## 3. Phân biệt NOT_AVAILABLE với EOF trong non-blocking parser

Nếu dùng non-blocking parser, `JsonToken.NOT_AVAILABLE` không có nghĩa JSON bị cắt hoặc sai cú pháp. Nó chỉ có nghĩa parser đã xử lý hết phần byte hiện có nhưng chưa đủ dữ liệu để tạo token tiếp theo.

Ví dụ một JSON string bị chia thành nhiều chunk:

```text
Chunk 1: {"message":"hel
Chunk 2: lo"}
```

Sau chunk đầu, parser có thể trả `NOT_AVAILABLE` vì string chưa hoàn chỉnh. Khi chunk tiếp theo được cấp, parser tiếp tục và phát token còn lại.

Khi nguồn thực sự kết thúc, ứng dụng phải gọi `feeder.endOfInput()`. Sau đó:

- Nếu dữ liệu đã tạo thành document hoàn chỉnh, parser có thể phát hết token và cuối cùng trả `null`.
- Nếu cấu trúc vẫn dang dở, parser báo lỗi EOF/parse tương ứng.

| Kết quả | Ý nghĩa |
| --- | --- |
| Token JSON thông thường | Có đủ dữ liệu để tạo token |
| `JsonToken.NOT_AVAILABLE` | Cần thêm input; nguồn có thể vẫn tiếp tục |
| `null` sau khi kết thúc input hợp lệ | Không còn token; document đã được tiêu thụ đến EOF |
| Parse exception sau `endOfInput()` | Input kết thúc khi cấu trúc JSON chưa hoàn chỉnh hoặc cú pháp không hợp lệ |

Không xử lý `NOT_AVAILABLE` như một lỗi dữ liệu. Ngược lại, cũng không được bỏ qua parse exception sau khi nguồn đã báo EOF.

## 4. Nhận diện token không đúng kỳ vọng

Parser có thể đọc một JSON hoàn toàn hợp lệ nhưng code lại mong một token khác. Ví dụ:

```json
{"items":[{"id":"A"}]}
```

Code mong `items` là object nhưng thực tế nó là array. Đây không phải lỗi cú pháp JSON; đó là sự không khớp giữa cấu trúc dữ liệu và giả định của chương trình.

Ví dụ kiểm tra token:

```java
JsonToken token = parser.nextToken();

if (token != JsonToken.START_OBJECT) {
    throw JsonMappingException.from(
            parser,
            "Root phải là JSON object, nhưng nhận được: " + token
    );
}
```

Thông báo có cả token thực tế sẽ hữu ích hơn một `NullPointerException` phát sinh sau đó khi code gọi phương thức dành cho object.

Các cặp kỳ vọng thường gặp:

| Code đang chờ | Token thực tế có thể gặp | Vấn đề |
| --- | --- | --- |
| `START_OBJECT` | `START_ARRAY` | Object bị thay bằng array hoặc contract không đúng |
| `START_ARRAY` | `START_OBJECT` | Collection bị gửi thành object |
| `FIELD_NAME` | `END_OBJECT` | Object đã kết thúc, không còn field tiếp theo |
| `VALUE_STRING` | `VALUE_NUMBER_INT` | Kiểu JSON khác với kiểu mong đợi |
| `VALUE_NUMBER_INT` | `VALUE_STRING` | Client gửi số dưới dạng chuỗi |
| `END_ARRAY` | `END_OBJECT` | Trạng thái lồng nhau hoặc giả định cấu trúc sai |

Trước khi đọc giá trị, hãy kiểm tra `parser.currentToken()` hoặc token vừa nhận từ `nextToken()`.

## 5. Kiểm tra token flow đúng cách

Trong Streaming API, `nextToken()` vừa di chuyển parser vừa trả về token mới. Một lần gọi dư có thể bỏ qua token cần xử lý.

Ví dụ object đơn giản:

```java
JsonToken token = parser.nextToken();
if (token != JsonToken.START_OBJECT) {
    throw JsonMappingException.from(parser, "Expected START_OBJECT");
}

while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
    if (token == null) {
        throw JsonMappingException.from(parser, "Unexpected end of JSON object");
    }

    if (token != JsonToken.FIELD_NAME) {
        throw JsonMappingException.from(
                parser,
                "Expected FIELD_NAME but received " + token
        );
    }

    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();
    if (valueToken == null) {
        throw JsonMappingException.from(
                parser,
                "Missing value for field " + fieldName
        );
    }

    // Xử lý value theo fieldName và valueToken.
}
```

Trong parser blocking, nếu EOF xảy ra khi object chưa đóng, parser thường ném parse exception ngay trong `nextToken()` thay vì luôn trả `null`. Kiểm tra `null` vẫn giúp code biểu đạt điều kiện kết thúc, nhưng không thay thế việc xử lý exception parse.

### 5.1. Đừng gọi getText() trước khi xác nhận token

`getText()` trả văn bản của token hiện tại. Nếu token hiện tại là `START_OBJECT` hoặc `START_ARRAY`, kết quả không phải toàn bộ JSON subtree theo cách mà code có thể mong đợi. Với number, string và field name, hãy gọi phương thức lấy dữ liệu phù hợp.

Ví dụ:

```java
if (token == JsonToken.FIELD_NAME) {
    String name = parser.currentName();
} else if (token == JsonToken.VALUE_STRING) {
    String value = parser.getText();
} else if (token == JsonToken.VALUE_NUMBER_INT) {
    int value = parser.getIntValue();
} else if (token == JsonToken.VALUE_NUMBER_FLOAT) {
    BigDecimal value = parser.getDecimalValue();
} else if (token == JsonToken.VALUE_NULL) {
    // Xử lý null riêng.
}
```

Code xử lý theo loại token giúp lỗi được phát hiện tại đúng điểm thay vì để một phép chuyển đổi ngầm tạo kết quả không mong muốn.

## 6. Lỗi cú pháp JSON và lỗi ánh xạ Databind

Jackson có nhiều nhóm exception. Phân biệt chúng giúp tìm đúng tầng gây lỗi:

| Exception | Tầng | Ví dụ |
| --- | --- | --- |
| `JsonParseException` | Parser/cú pháp | Thiếu dấu phẩy, dấu nháy chưa đóng, token không hợp lệ |
| `JsonEOFException` (trong các trường hợp parser dùng kiểu chuyên biệt) | Parser/EOF | Nguồn kết thúc khi string, object hoặc array chưa hoàn tất |
| `MismatchedInputException` | Databind/kiểu đích | JSON array được đọc vào một DTO đơn, hoặc không có nội dung để map |
| `InvalidFormatException` | Databind/chuyển đổi giá trị | Chuỗi ngày hoặc số không chuyển được sang kiểu Java đích |
| `UnrecognizedPropertyException` | Databind/property | JSON có field không được DTO nhận diện khi strict unknown-property handling bật |
| `InvalidDefinitionException` | Cấu hình/định nghĩa kiểu | Không có cách tạo hoặc xử lý kiểu Java theo cấu hình hiện tại |

Ví dụ JSON sai cú pháp:

```json
{"id":"A" "status":"PAID"}
```

Thiếu dấu phẩy giữa hai property, nên parser không thể tạo token hợp lệ cho phần tiếp theo.

Ví dụ JSON hợp lệ nhưng sai kiểu đích:

```json
{"items":[1,2,3]}
```

Nếu DTO khai báo `items` là một object đơn thay vì collection, lỗi xảy ra ở tầng Databind do cấu trúc không khớp kiểu Java.

Ví dụ JSON hợp lệ nhưng giá trị không chuyển được:

```json
{"createdAt":"not-a-date"}
```

Nếu `createdAt` là `Instant` và module/configuration ngày giờ không thể parse chuỗi này, lỗi thường là `InvalidFormatException` hoặc lỗi mapping liên quan, không phải lỗi cú pháp JSON.

## 7. Lấy vị trí lỗi bằng JsonLocation

Khi Jackson báo lỗi parse hoặc mapping, thông tin vị trí giúp xác định vùng input gây lỗi. `JsonLocation` có thể cung cấp:

- `getLineNr()`: số dòng, thường bắt đầu từ 1.
- `getColumnNr()`: số cột.
- `getCharOffset()`: offset ký tự nếu có.
- `getByteOffset()`: offset byte nếu có.
- Thông tin nguồn qua source reference tùy phiên bản và cấu hình.

Ví dụ bắt lỗi:

```java
try {
    Order order = mapper.readValue(json, Order.class);
} catch (JsonProcessingException e) {
    JsonLocation location = e.getLocation();

    if (location != null) {
        System.err.printf(
                "JSON error at line %d, column %d, byte offset %d: %s%n",
                location.getLineNr(),
                location.getColumnNr(),
                location.getByteOffset(),
                e.getOriginalMessage()
        );
    } else {
        System.err.println("JSON error: " + e.getOriginalMessage());
    }
}
```

Offset byte có thể không có giá trị hữu ích trong mọi trường hợp, chẳng hạn khi parser đọc từ `Reader` hoặc nguồn không cung cấp offset byte. Khi đó, line/column hoặc character offset có thể phù hợp hơn.

Không nên dựa vào chuỗi thông báo exception để phân tích máy móc nếu có thể dùng kiểu exception và location API. Nội dung thông báo có thể thay đổi giữa các phiên bản Jackson.

## 8. Xem đường dẫn property khi lỗi xảy ra trong DTO lồng nhau

Lỗi parse chỉ rõ vị trí cú pháp, nhưng lỗi Databind thường cần thêm đường dẫn property. `JsonMappingException` lưu path gồm các field/index mà Jackson đã đi qua.

Ví dụ DTO:

```java
public class Order {
    private Customer customer;
}

public class Customer {
    private Address address;
}

public class Address {
    private int postalCode;
}
```

JSON:

```json
{
  "customer": {
    "address": {
      "postalCode": "not-a-number"
    }
  }
}
```

Khi chuyển `postalCode` sang `int` thất bại, exception có thể chứa đường dẫn như `Order["customer"] -> Customer["address"] -> Address["postalCode"]`.

Có thể lấy path:

```java
try {
    mapper.readValue(json, Order.class);
} catch (JsonMappingException e) {
    System.err.println(e.getPathReference());
    System.err.println(e.getOriginalMessage());
}
```

`getPathReference()` hữu ích cho log và chẩn đoán. Đối với custom deserializer, hãy tạo lỗi bằng `JsonMappingException.from(parser, message)` hoặc API báo lỗi của `DeserializationContext` để Jackson có thể bổ sung context/path khi exception đi qua Databind.

## 9. Nhận diện input bị cắt ở tầng truyền dữ liệu

Jackson chỉ nhìn thấy byte được cấp cho parser. Nếu HTTP request body bị cắt do mạng, proxy, client hoặc code đọc stream sai, parser thường chỉ phát hiện hậu quả: EOF bất ngờ hoặc JSON không hoàn chỉnh.

Các nguyên nhân thường gặp:

- Client đóng kết nối trước khi gửi hết request body.
- Server đọc body một lần rồi một filter/interceptor khác cố đọc lại cùng stream.
- `Content-Length` hoặc framing của giao thức không khớp dữ liệu thực tế.
- Chunked transfer bị kết thúc không đúng hoặc stream bị đóng sớm.
- File JSON bị truncate trong lúc copy, upload hoặc ghi.
- Giải nén gzip thất bại hoặc nguồn giải nén kết thúc sớm.
- Code chỉ đọc một phần buffer nhưng nhầm đó là toàn bộ nội dung.
- Một giới hạn kích thước ở gateway hoặc application cắt payload.

Vì vậy, khi thấy EOF, hãy kiểm tra cả tầng vận chuyển:

1. Số byte thực tế đã nhận.
2. `Content-Length` hoặc framing nếu giao thức có cung cấp.
3. Trạng thái kết nối và lý do stream kết thúc.
4. Kết quả giải nén nếu request được nén.
5. Mã tạo JSON ở phía producer và thời điểm đóng output.
6. Có thành phần nào đọc trước hoặc tiêu thụ một phần stream không.

Không nên chỉ tăng timeout hoặc tăng giới hạn parser nếu nguyên nhân thực tế là producer gửi thiếu byte.

## 10. Phân biệt dữ liệu bị cắt với giới hạn parser

Jackson có thể từ chối input vì vượt giới hạn bảo vệ, ví dụ nesting quá sâu, string quá dài hoặc number token quá dài. Đây không giống EOF bất ngờ.

Với các phiên bản hỗ trợ `StreamReadConstraints`, có thể cấu hình giới hạn đọc:

```java
JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
                StreamReadConstraints.builder()
                        .maxNestingDepth(100)
                        .maxStringLength(1_000_000)
                        .maxNumberLength(1_000)
                        .build()
        )
        .build();
```

Nếu input vượt một giới hạn, Jackson báo lỗi constraint/read limit. Nếu input bị cắt, parser báo EOF hoặc lỗi cú pháp do cấu trúc chưa hoàn chỉnh. Hai trường hợp cần hướng xử lý khác nhau:

- **Vượt giới hạn:** xem xét hợp đồng kích thước, cấu hình giới hạn và khả năng payload bất thường.
- **Bị cắt:** điều tra nguồn byte, framing và vòng đời stream.

Không nên tăng giới hạn vô điều kiện để làm lỗi biến mất. Giới hạn là một phần bảo vệ tài nguyên trước payload không tin cậy.

## 11. Token sai do code đọc lệch trạng thái

Không phải mọi token bất ngờ đều do producer gửi sai JSON. Chính code parser có thể làm lệch trạng thái.

Ví dụ sai:

```java
JsonToken token = parser.nextToken(); // START_OBJECT
token = parser.nextToken();           // FIELD_NAME
token = parser.nextToken();           // VALUE_STRING
token = parser.nextToken();           // Đã sang field/token kế tiếp

String value = parser.getText();      // Không còn là value ban đầu
```

Mỗi lần gọi `nextToken()` làm parser tiến lên. Nếu code gọi thêm một lần để kiểm tra rồi quên rằng token đã đổi, nó có thể đọc nhầm property tiếp theo.

Các lỗi trạng thái thường gặp:

- Gọi `nextToken()` hai lần cho một value.
- Gọi `skipChildren()` rồi vẫn xử lý như parser còn ở `START_OBJECT`/`START_ARRAY`.
- Hàm con đọc hết object nhưng caller lại gọi thêm token và bỏ qua token kế tiếp.
- Dùng một biến `currentField` chung cho nhiều object lồng nhau.
- Nhầm `FIELD_NAME` với token value đứng sau nó.
- Không phân biệt `END_OBJECT`/`END_ARRAY` ở cấp lồng nhau khác nhau.

Hãy ghi rõ hợp đồng cho mỗi hàm parser: hàm nhận parser ở token nào, tiêu thụ đến token nào và trả về khi parser đang đứng ở đâu. Đây là cách giảm lỗi trạng thái trong code streaming.

## 12. Dùng parsing context để hiểu parser đang ở đâu

`parser.getParsingContext()` trả về `JsonStreamContext` mô tả ngữ cảnh hiện tại. Nó giúp quan sát parser đang ở object hay array, tên field hiện tại, index array và context cha.

Ví dụ debug:

```java
while (parser.nextToken() != null) {
    JsonToken token = parser.currentToken();
    JsonStreamContext context = parser.getParsingContext();

    System.out.printf(
            "token=%s, object=%s, array=%s, field=%s, index=%d%n",
            token,
            context.inObject(),
            context.inArray(),
            context.getCurrentName(),
            context.getCurrentIndex()
    );
}
```

Context đặc biệt hữu ích khi parser báo token không đúng kỳ vọng trong một cấu trúc lồng sâu. Nó cho biết vị trí parse; ứng dụng vẫn phải quản lý trạng thái nghiệp vụ của riêng mình.

Không nên log toàn bộ payload để debug nếu dữ liệu có thông tin cá nhân, token, thông tin thanh toán hoặc bí mật. Token type, field path, line/column và một request correlation id thường đủ để khoanh vùng.

## 13. Kiểm tra document có token thừa sau root value

Một JSON document chuẩn có một root value. Parser cấp thấp có thể tiếp tục đọc các root value khác nếu input chứa chúng nối tiếp, nhưng một API thường chỉ muốn đúng một document.

Ví dụ:

```text
{"id":"A"} {"id":"B"}
```

Mỗi object riêng lẻ có cú pháp hợp lệ, nhưng cả chuỗi có hai root value. Nếu hợp đồng chỉ chấp nhận một JSON document, phần thứ hai là dữ liệu thừa.

Với Databind, có thể bật:

```java
mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Feature này yêu cầu kiểm tra không còn token JSON không phải whitespace sau root value đã bind. Với Streaming API, có thể tự kiểm tra:

```java
try (JsonParser parser = factory.createParser(input)) {
    Order order = mapper.readValue(parser, Order.class);

    JsonToken trailing = parser.nextToken();
    if (trailing != null) {
        throw JsonMappingException.from(
                parser,
                "Có token thừa sau JSON root value: " + trailing
        );
    }
}
```

Hãy phân biệt token thừa với khoảng trắng sau document. Parser tự bỏ qua whitespace hợp lệ nên `nextToken()` trả `null` nếu không còn JSON token.

Nếu giao thức cho phép nhiều JSON record nối tiếp, đừng bật kiểm tra một-root-document một cách máy móc. Hãy dùng framing rõ ràng như NDJSON hoặc length-prefix và xử lý từng record theo hợp đồng.

## 14. Bật kiểm tra duplicate field khi cần

Một object có thể chứa cùng một tên property nhiều lần:

```json
{
  "role": "user",
  "role": "admin"
}
```

Đây không nhất thiết là lỗi cú pháp theo cách mọi parser xử lý, nhưng có thể tạo kết quả khác nhau giữa consumer. Nếu ứng dụng cần phát hiện duplicate field, có thể bật strict duplicate detection trên factory/parser:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
```

Khi đó parser kiểm tra tên field trùng trong cùng object và báo lỗi thay vì âm thầm tiếp tục. Chi phí kiểm tra có thể tăng, vì vậy hãy bật theo yêu cầu an toàn và hợp đồng dữ liệu.

Duplicate field khác với token sai kỳ vọng và khác với input bị cắt. Đây là một quy tắc kiểm tra cấu trúc bổ sung.

## 15. Xử lý exception ở đúng tầng

Không nên bắt mọi exception rồi trả một thông báo chung “Invalid JSON”. Điều đó làm mất thông tin giúp phân biệt lỗi client, lỗi producer, lỗi cấu hình và lỗi code.

Một cách phân loại ở tầng ứng dụng:

```java
try {
    Order order = mapper.readValue(input, Order.class);
    process(order);
} catch (JsonParseException e) {
    // JSON syntax/EOF problem.
    reportInvalidJson(e.getOriginalMessage(), e.getLocation());
} catch (JsonMappingException e) {
    // JSON hợp lệ nhưng không map được vào model/cấu hình.
    reportMappingProblem(e.getPathReference(), e.getOriginalMessage());
} catch (IOException e) {
    // Lỗi đọc nguồn hoặc I/O khác.
    reportInputFailure(e);
}
```

Thứ tự catch quan trọng vì exception chuyên biệt có thể kế thừa từ loại rộng hơn. `JsonParseException` và `JsonMappingException` đều thuộc hệ exception xử lý JSON; cần bắt trước `IOException` nếu muốn phân loại riêng.

Trong API HTTP, có thể ánh xạ lỗi parse/mapping của request thành phản hồi client phù hợp, nhưng không nên trả stack trace hoặc chi tiết nội bộ. Lỗi I/O do kết nối bị ngắt cũng không nhất thiết cần gửi một JSON error response nếu client đã đóng socket.

## 16. Có nên tiếp tục parse sau lỗi?

Với một JSON document đơn, sau khi parser gặp lỗi cú pháp nghiêm trọng hoặc EOF trong cấu trúc, thường không nên cố tiếp tục từ token tiếp theo. Parser có thể không còn trạng thái đáng tin cậy để xác định ranh giới value tiếp theo.

Nếu giao thức truyền nhiều record, hãy cô lập từng record bằng framing:

- **NDJSON:** mỗi dòng là một JSON document riêng theo quy tắc NDJSON.
- **Length-prefix:** header cho biết chính xác số byte của một JSON payload.
- **Message frame:** mỗi message từ broker/socket là một đơn vị JSON độc lập.

Khi một record lỗi, bỏ record đó theo chính sách và tạo parser mới cho record kế tiếp. Đừng quét byte tùy tiện để tìm dấu `{` tiếp theo trong một JSON document hỏng; dấu ngoặc có thể xuất hiện trong string hoặc dữ liệu lồng nhau, và việc phục hồi không đáng tin cậy.

Với non-blocking parser, `NOT_AVAILABLE` là trạng thái chờ thêm input nên parser vẫn tiếp tục được. Nhưng một parse exception sau khi đã xác nhận EOF hoặc cú pháp sai là lỗi của document/frame đó; hãy kết thúc và giải phóng parser tương ứng.

## 17. Quy trình chẩn đoán từng bước

Khi gặp lỗi đọc JSON, hãy đi theo trình tự:

1. **Xác định loại exception.** `JsonParseException` thường chỉ cú pháp/token; `MismatchedInputException` hoặc `InvalidFormatException` thường thuộc Databind; lỗi I/O có thể đến từ nguồn.
2. **Đọc location.** Ghi line, column và byte/character offset nếu có.
3. **Kiểm tra parser state.** Xác định token hiện tại, field name và parsing context.
4. **Kiểm tra input thực tế.** So sánh số byte nhận được, framing, EOF và payload do producer tạo.
5. **Phân biệt EOF với NOT_AVAILABLE.** Non-blocking parser chưa có đủ byte không đồng nghĩa document bị hỏng.
6. **Kiểm tra kiểu đích.** JSON có đúng cú pháp nhưng object/array/scalar có đúng kiểu DTO mong đợi không?
7. **Kiểm tra code gọi token.** Tìm lần gọi `nextToken()`, `skipChildren()` hoặc hàm con có thể làm parser lệch trạng thái.
8. **Kiểm tra giới hạn đọc và feature.** Phân biệt constraint violation, duplicate field và trailing token với lỗi truncate.
9. **Tạo test nhỏ tái hiện.** Dùng chính input bị lỗi và đúng `JsonFactory`/`ObjectMapper` production.
10. **Quyết định chính sách phục hồi.** Từ chối document, yêu cầu gửi lại hoặc bỏ record lỗi theo framing của giao thức.

## 18. Ví dụ ghi log chẩn đoán mà không lộ payload

Một helper có thể ghi nhận loại lỗi và vị trí mà không log toàn bộ JSON:

```java
static void logJsonFailure(JsonProcessingException exception, String requestId) {
    JsonLocation location = exception.getLocation();

    if (location == null) {
        logger.warn(
                "JSON processing failed; requestId={}, type={}, message={}",
                requestId,
                exception.getClass().getSimpleName(),
                exception.getOriginalMessage()
        );
        return;
    }

    logger.warn(
            "JSON processing failed; requestId={}, type={}, line={}, column={}, byteOffset={}, message={}",
            requestId,
            exception.getClass().getSimpleName(),
            location.getLineNr(),
            location.getColumnNr(),
            location.getByteOffset(),
            exception.getOriginalMessage()
    );
}
```

Nếu là `JsonMappingException`, có thể log thêm `getPathReference()` để xác định property. Hãy lọc hoặc chuẩn hóa thông báo nếu nó có thể chứa dữ liệu đầu vào nhạy cảm. Không nên log raw body, access token, mật khẩu hoặc nội dung tài liệu chỉ để chẩn đoán parser.

## 19. Bảng phân biệt nhanh

| Dấu hiệu | Nhóm lỗi có khả năng | Việc cần kiểm tra |
| --- | --- | --- |
| `Unexpected end-of-input` khi object/array/string chưa đóng | Input bị cắt hoặc producer tạo JSON chưa hoàn chỉnh | EOF, số byte, framing và vòng đời stream |
| `NOT_AVAILABLE` từ non-blocking parser | Chưa nhận đủ chunk | Chờ thêm byte; chỉ báo EOF khi nguồn thật sự kết thúc |
| Mong `START_OBJECT` nhưng nhận `START_ARRAY` | Token hợp lệ nhưng sai shape mong đợi | JSON contract và trạng thái code |
| Mong `FIELD_NAME` nhưng nhận token đóng | Object hiện tại đã hết hoặc parser bị gọi lệch | Token flow và cấp lồng nhau |
| `InvalidFormatException` | Giá trị không chuyển được sang kiểu Java | Kiểu JSON, format, coercion và DTO |
| `UnrecognizedPropertyException` | Field không được DTO nhận diện | Tên field, version contract và unknown-property policy |
| Lỗi nesting/string/number constraint | Input vượt giới hạn bảo vệ | Kích thước payload và `StreamReadConstraints` |
| Token còn lại sau root | Nhiều root value hoặc dữ liệu thừa | Framing, `FAIL_ON_TRAILING_TOKENS` |
| Duplicate field detection failure | Tên property xuất hiện nhiều lần | Producer và chính sách duplicate detection |

## 20. Ghi nhớ

- EOF khi JSON chưa hoàn chỉnh khác với input rỗng và khác với `JsonToken.NOT_AVAILABLE` của non-blocking parser.
- `NOT_AVAILABLE` có nghĩa cần thêm input; sau `endOfInput()`, cấu trúc còn dang dở mới trở thành lỗi EOF/parse.
- Token có thể hợp lệ về cú pháp nhưng không đúng trạng thái mà code mong đợi; kiểm tra `JsonToken` trước khi đọc value.
- `nextToken()` làm parser tiến lên; gọi dư hoặc dùng sai `skipChildren()` có thể làm bỏ qua token.
- `JsonParseException` thường chỉ lỗi cú pháp/parser; `MismatchedInputException`, `InvalidFormatException` và `UnrecognizedPropertyException` thường chỉ lỗi Databind.
- Dùng `JsonLocation` để lấy line, column và offset; dùng `JsonMappingException.getPathReference()` để xem đường dẫn property.
- Khi EOF xuất hiện, kiểm tra cả tầng transport/framing, không chỉ Jackson.
- Phân biệt lỗi vượt `StreamReadConstraints` với input bị cắt.
- `FAIL_ON_TRAILING_TOKENS` giúp từ chối token thừa sau root value; strict duplicate detection giúp phát hiện tên field lặp.
- Không cố phục hồi tùy tiện sau lỗi cú pháp trong một document; dùng framing riêng nếu cần xử lý nhiều record độc lập.
- Log loại exception, location và path; tránh ghi toàn bộ payload nhạy cảm.

Khi chẩn đoán lỗi JSON, hãy xác định parser đang thiếu dữ liệu, đang nhận token khác với giả định hay đã đọc được JSON hợp lệ nhưng không thể ánh xạ vào kiểu Java. Phân loại đúng tầng lỗi sẽ giúp tìm nguyên nhân nhanh hơn, tránh sửa sai bằng cách nới lỏng parser hoặc bỏ qua dữ liệu không hợp lệ.
