# Vai trò của parser không chặn và cách cấp thêm dữ liệu

Khi đọc JSON từ một file nhỏ hoặc một `InputStream` thông thường, ứng dụng thường gọi `ObjectMapper.readValue()` hoặc dùng `JsonParser.nextToken()` cho đến khi hết dữ liệu. Trong các API này, thao tác đọc có thể phải chờ nguồn cung cấp thêm byte. Điều đó phù hợp với nhiều chương trình, nhưng có thể không phù hợp với server hoặc ứng dụng mạng cần tiếp tục xử lý công việc khác trong lúc dữ liệu đầu vào chưa đến đủ.

Jackson Core cung cấp **non-blocking parser** (parser không chặn) để phân tích JSON theo từng phần dữ liệu được cấp vào. Khi parser đã xử lý hết phần byte hiện có nhưng chưa đủ dữ liệu để tạo token tiếp theo, nó trả về `JsonToken.NOT_AVAILABLE`. Ứng dụng có thể tạm dừng việc parse, quay lại event loop hoặc xử lý tác vụ khác, rồi cấp thêm byte khi chúng đến.

Điểm quan trọng là parser không chặn không tự mở kết nối mạng, không tự tạo thread và cũng không tự lấy thêm dữ liệu. Ứng dụng chịu trách nhiệm nhận byte từ nguồn bên ngoài và cấp chúng cho parser thông qua một **input feeder**.

## 1. Vì sao cần parser không chặn?

Trong cách đọc blocking thông thường, parser lấy dữ liệu từ `InputStream` hoặc `Reader`. Nếu stream chưa có byte tiếp theo, lời gọi đọc có thể phải chờ. Với một luồng xử lý đơn giản, việc chờ này không phải vấn đề. Nhưng trong server có nhiều kết nối đồng thời, một thread bị giữ lại chỉ để chờ dữ liệu có thể làm giảm khả năng phục vụ các kết nối khác.

Non-blocking parsing phù hợp với mô hình mà nguồn dữ liệu đã có cơ chế báo khi byte mới đến, ví dụ:

- Event loop của server mạng.
- Kết nối socket bất đồng bộ.
- Một giao thức streaming gửi payload thành nhiều chunk.
- Reactive pipeline hoặc callback nhận các buffer dữ liệu.
- Ứng dụng xử lý nhiều kết nối mà không muốn mỗi kết nối giữ một thread chỉ để chờ input.

Luồng xử lý có thể hình dung như sau:

```text
Nguồn dữ liệu / socket / event loop
             │
             │ nhận được một chunk byte
             ▼
       ByteArrayFeeder
             │ feedInput(...)
             ▼
       JsonParser
             │ nextToken()
             ▼
   Các token JSON hoàn chỉnh
             │
             ├── Có token: xử lý token và tiếp tục parse
             │
             └── NOT_AVAILABLE: cần thêm byte
                         │
                         ▼
                 quay lại chờ nguồn
```

Parser giữ trạng thái phân tích giữa các lần cấp dữ liệu. Ví dụ, một chunk có thể kết thúc giữa tên trường, giữa chuỗi hoặc giữa một số. Parser chưa phát token hoàn chỉnh cho phần dữ liệu chưa đủ; khi chunk tiếp theo được cấp, nó tiếp tục phân tích từ trạng thái trước đó.

## 2. Blocking parser và non-blocking parser khác nhau thế nào?

| Đặc điểm | Blocking parser | Non-blocking parser |
| --- | --- | --- |
| Nguồn dữ liệu | Thường đọc trực tiếp từ `InputStream`/`Reader` | Ứng dụng cấp từng chunk qua feeder |
| Khi chưa đủ byte | Lời gọi đọc có thể chờ nguồn | `nextToken()` trả `JsonToken.NOT_AVAILABLE` |
| Ai lấy thêm dữ liệu? | Parser đọc từ stream | Ứng dụng nhận dữ liệu và gọi feeder |
| Quản lý trạng thái | Parser giữ trạng thái trong khi đọc | Parser giữ trạng thái qua nhiều lần feed |
| Tích hợp event loop | Có thể chặn thread nếu nguồn chưa sẵn sàng | Phù hợp hơn vì parser trả quyền điều khiển khi cần thêm byte |
| Mức độ phức tạp | Đơn giản hơn | Cần quản lý chunk, feeder và trạng thái kết thúc input |

Streaming API và non-blocking API cũng không phải hai tên gọi cho cùng một thứ. Blocking `JsonParser` vẫn là streaming parser vì nó phát token tuần tự thay vì tạo toàn bộ cây JSON. Non-blocking parser cũng phát token tuần tự, nhưng có thể tạm dừng khi dữ liệu chưa đủ và yêu cầu ứng dụng cấp thêm input.

## 3. Các API chính của Jackson

Với byte input, các thành phần thường dùng là:

| API | Vai trò |
| --- | --- |
| `JsonFactory.createNonBlockingByteArrayParser()` | Tạo parser không chặn nhận dữ liệu theo mảng byte. |
| `JsonParser.getNonBlockingInputFeeder()` | Lấy feeder để cấp dữ liệu cho parser. |
| `ByteArrayFeeder` | Feeder nhận `byte[]` cùng vị trí bắt đầu và kết thúc. |
| `ByteArrayFeeder.needMoreInput()` | Cho biết parser đã sẵn sàng nhận thêm input hay chưa. |
| `ByteArrayFeeder.feedInput(byte[], start, end)` | Cấp một đoạn byte cho parser; `end` là chỉ số kết thúc không bao gồm. |
| `ByteArrayFeeder.endOfInput()` | Báo rằng sẽ không còn byte nào được cấp thêm. |
| `JsonToken.NOT_AVAILABLE` | Báo parser hiện chưa thể tạo token tiếp theo vì cần thêm input. |

`ByteArrayFeeder` nằm trong package `com.fasterxml.jackson.core.async`. `JsonToken` và `JsonParser` nằm trong `com.fasterxml.jackson.core`.

Non-blocking parser theo byte array được hỗ trợ trong Jackson Core 2.x. Các phiên bản mới cũng có API làm việc với `ByteBuffer`; tên feeder và cách cấp buffer tương ứng khác với `ByteArrayFeeder`. Hãy kiểm tra API của phiên bản Jackson đang dùng trước khi chọn overload cụ thể.

## 4. Tạo non-blocking parser và lấy feeder

Ví dụ khởi tạo:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.async.ByteArrayFeeder;

JsonFactory factory = new JsonFactory();
JsonParser parser = factory.createNonBlockingByteArrayParser();

ByteArrayFeeder feeder = (ByteArrayFeeder) parser.getNonBlockingInputFeeder();
```

Parser được tạo mà chưa cần có toàn bộ JSON. Feeder là cổng để ứng dụng đưa byte vào sau này.

Không tạo parser mới cho mỗi chunk. Hãy giữ cùng parser và feeder trong suốt một JSON document hoặc một đơn vị input mà ứng dụng đang xử lý. Nếu tạo parser mới cho từng chunk, parser sẽ mất trạng thái như đang ở trong object nào, đang đọc chuỗi nào và đã nhận những token nào.

## 5. Cấp dữ liệu bằng feedInput()

Khi nguồn cung cấp một chunk byte, ứng dụng kiểm tra feeder đã sẵn sàng nhận input hay chưa:

```java
if (feeder.needMoreInput()) {
    feeder.feedInput(chunk, 0, chunk.length);
}
```

`feedInput(data, start, end)` nhận một vùng trong mảng byte. `start` là chỉ số đầu tiên được cấp; `end` là chỉ số ngay sau byte cuối cùng, tức không bao gồm.

Ví dụ nếu buffer có 1024 byte nhưng lần đọc hiện tại chỉ nhận được 300 byte:

```java
feeder.feedInput(buffer, 0, 300);
```

Không được cấp thêm chunk khi feeder chưa báo `needMoreInput()`. Trước khi yêu cầu thêm byte, parser phải tiêu thụ phần input hiện tại. Ngoài ra, không sửa hoặc tái sử dụng vùng mảng byte đã feed cho đến khi parser báo cần thêm input; parser có thể vẫn đang tham chiếu đến vùng dữ liệu đó.

Nếu chunk rỗng, không cần gọi `feedInput()` với độ dài bằng 0. Hãy chờ chunk tiếp theo hoặc báo kết thúc input khi nguồn thật sự đã hết.

## 6. Hiểu JsonToken.NOT_AVAILABLE

Với parser không chặn, `nextToken()` có thể trả về ba kết quả quan trọng:

- Một token như `START_OBJECT`, `FIELD_NAME`, `VALUE_STRING` hoặc `END_ARRAY`: parser đã có đủ byte để tạo token đó.
- `JsonToken.NOT_AVAILABLE`: parser cần thêm byte để tiếp tục. Đây không phải token dữ liệu JSON và không được xử lý như một giá trị.
- `null`: parser đã đi đến cuối input sau khi ứng dụng báo kết thúc input và toàn bộ nội dung hợp lệ đã được xử lý.

Mẫu xử lý cơ bản:

```java
JsonToken token = parser.nextToken();

if (token == JsonToken.NOT_AVAILABLE) {
    // Dừng vòng parse hiện tại; chờ ứng dụng cấp thêm byte.
} else if (token == null) {
    // Đã kết thúc document/input.
} else {
    // Xử lý token JSON.
}
```

Không coi `NOT_AVAILABLE` là lỗi cú pháp. Nó chỉ cho biết phần byte hiện có chưa đủ để tạo token tiếp theo. Ngược lại, nếu ứng dụng đã gọi `endOfInput()` mà parser vẫn không thể hoàn thành cấu trúc JSON, đó có thể là input bị cắt cụt và parser sẽ báo lỗi khi hoàn tất việc đọc.

## 7. Vòng lặp parse các token hiện có

Sau khi cấp một chunk, ứng dụng gọi `nextToken()` liên tục để lấy tất cả token có thể tạo ra từ phần dữ liệu đã nhận. Khi parser trả `NOT_AVAILABLE`, vòng lặp dừng và chờ chunk tiếp theo.

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

static void drainAvailableTokens(JsonParser parser) throws IOException {
    while (true) {
        JsonToken token = parser.nextToken();

        if (token == JsonToken.NOT_AVAILABLE) {
            return; // Cần thêm input.
        }

        if (token == null) {
            return; // Input đã kết thúc.
        }

        handleToken(parser, token);
    }
}
```

`handleToken()` là hàm của ứng dụng để xử lý token hiện tại, chẳng hạn lưu tên field, đọc giá trị string/number hoặc quản lý trạng thái object/array. Khi token là `FIELD_NAME`, có thể lấy tên bằng `parser.currentName()`. Khi token là giá trị, dùng phương thức phù hợp như `getText()`, `getIntValue()` hoặc `getBooleanValue()`.

Điều quan trọng là chỉ gọi `handleToken()` cho token dữ liệu thực. `NOT_AVAILABLE` không đại diện cho một phần tử JSON và không nên làm thay đổi trạng thái nghiệp vụ.

## 8. Ví dụ cấp từng chunk và đọc JSON hoàn chỉnh

Ví dụ sau minh họa chu trình cấp từng chunk byte, đọc hết token có thể đọc được, rồi báo kết thúc input. Trong ứng dụng thực tế, các chunk này có thể đến từ callback của socket hoặc event loop; ở đây ta chia một mảng byte có sẵn thành các phần nhỏ để dễ quan sát.

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.async.ByteArrayFeeder;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class NonBlockingJsonExample {
    public static void main(String[] args) throws IOException {
        String json = "{\"id\":\"ORD-1\",\"items\":[1,2,3]}";
        byte[] input = json.getBytes(StandardCharsets.UTF_8);

        JsonFactory factory = new JsonFactory();
        try (JsonParser parser = factory.createNonBlockingByteArrayParser()) {
            ByteArrayFeeder feeder = (ByteArrayFeeder) parser.getNonBlockingInputFeeder();

            int chunkSize = 5;
            for (int offset = 0; offset < input.length; ) {
                int end = Math.min(offset + chunkSize, input.length);

                if (!feeder.needMoreInput()) {
                    throw new IllegalStateException(
                            "Parser chưa tiêu thụ hết chunk trước"
                    );
                }

                feeder.feedInput(input, offset, end);
                offset = end;

                drainAvailableTokens(parser);
            }

            // Báo rõ rằng sẽ không còn chunk nào nữa.
            feeder.endOfInput();

            // Đọc hết token còn lại sau khi input kết thúc.
            while (true) {
                JsonToken token = parser.nextToken();

                if (token == null) {
                    break;
                }

                if (token == JsonToken.NOT_AVAILABLE) {
                    throw new IOException(
                            "Parser vẫn cần input sau khi endOfInput đã được gọi"
                    );
                }

                handleToken(parser, token);
            }
        }
    }

    private static void drainAvailableTokens(JsonParser parser) throws IOException {
        while (true) {
            JsonToken token = parser.nextToken();

            if (token == JsonToken.NOT_AVAILABLE || token == null) {
                return;
            }

            handleToken(parser, token);
        }
    }

    private static void handleToken(JsonParser parser, JsonToken token)
            throws IOException {
        switch (token) {
            case FIELD_NAME -> System.out.println("Field: " + parser.currentName());
            case VALUE_STRING -> System.out.println("String: " + parser.getText());
            case VALUE_NUMBER_INT, VALUE_NUMBER_FLOAT ->
                    System.out.println("Number: " + parser.getNumberValue());
            case VALUE_TRUE -> System.out.println("Boolean: true");
            case VALUE_FALSE -> System.out.println("Boolean: false");
            case VALUE_NULL -> System.out.println("Null");
            case START_OBJECT -> System.out.println("Start object");
            case END_OBJECT -> System.out.println("End object");
            case START_ARRAY -> System.out.println("Start array");
            case END_ARRAY -> System.out.println("End array");
            default -> System.out.println("Token: " + token);
        }
    }
}
```

Ví dụ dùng switch expression syntax của Java hiện đại. Nếu dự án dùng Java 8 hoặc Java 11, có thể đổi switch arrow thành `switch` statement truyền thống. Mục đích của ví dụ là làm rõ luồng điều khiển:

1. Chia input thành chunk.
2. Chỉ cấp chunk khi feeder báo `needMoreInput()`.
3. Sau mỗi lần cấp, đọc liên tục token có sẵn.
4. Dừng khi gặp `NOT_AVAILABLE`.
5. Khi không còn chunk, gọi `endOfInput()`.
6. Đọc đến khi parser trả `null`.

Trong ứng dụng event-driven, bước 1 và 2 diễn ra khi callback nhận dữ liệu; ứng dụng không cần chờ đồng bộ để lấy chunk tiếp theo.

## 9. Cấp thêm dữ liệu từ callback hoặc event loop

Trong một ứng dụng mạng không chặn, parser và feeder thường được giữ trong một object gắn với kết nối. Khi có byte mới, callback cấp byte rồi gọi hàm parse. Khi chưa có byte, callback kết thúc và event loop tiếp tục xử lý kết nối khác.

Mẫu tổ chức đơn giản:

```java
final class JsonConnectionState implements AutoCloseable {
    private final JsonParser parser;
    private final ByteArrayFeeder feeder;
    private boolean ended;

    JsonConnectionState(JsonFactory factory) throws IOException {
        this.parser = factory.createNonBlockingByteArrayParser();
        this.feeder = (ByteArrayFeeder) parser.getNonBlockingInputFeeder();
    }

    void onBytes(byte[] data, int length) throws IOException {
        if (ended) {
            throw new IllegalStateException("Input đã kết thúc");
        }
        if (length == 0) {
            return;
        }
        if (!feeder.needMoreInput()) {
            throw new IllegalStateException("Cần drain parser trước khi feed thêm");
        }

        feeder.feedInput(data, 0, length);
        drainAvailableTokens(parser);
    }

    void onEndOfInput() throws IOException {
        if (ended) {
            return;
        }
        ended = true;
        feeder.endOfInput();

        while (true) {
            JsonToken token = parser.nextToken();
            if (token == null) {
                break;
            }
            if (token == JsonToken.NOT_AVAILABLE) {
                throw new IOException("JSON chưa hoàn chỉnh khi nguồn đã kết thúc");
            }
            handleToken(parser, token);
        }
    }

    @Override
    public void close() throws IOException {
        parser.close();
    }
}
```

Các hàm `drainAvailableTokens()` và `handleToken()` được dùng như ví dụ ở phần trước. Đây là khung tổ chức; trong ứng dụng thật cần bổ sung xử lý lỗi, giới hạn payload, trạng thái kết nối và cơ chế chuyển kết quả đến tầng nghiệp vụ.

Không gọi đồng thời `onBytes()` trên nhiều thread cho cùng parser. Parser là một đối tượng có trạng thái tiến triển theo token; việc feed và parse phải được tuần tự hóa theo đúng thứ tự byte đến. Một parser nên gắn với một luồng JSON riêng.

## 10. Parser có thể nhận một token bị chia giữa hai chunk

Chunk không cần kết thúc tại ranh giới JSON. Ví dụ chuỗi JSON:

```json
{"message":"hello"}
```

có thể được chia thành:

```text
Chunk 1: {"mess
Chunk 2: age":"he
Chunk 3: llo"}
```

Sau chunk 1, parser có thể đã phát `START_OBJECT` nhưng chưa đủ byte để phát `FIELD_NAME` hoàn chỉnh. `nextToken()` trả `NOT_AVAILABLE`. Sau chunk 2, parser vẫn có thể cần thêm byte để hoàn thành string value. Khi chunk 3 đến, parser có thể hoàn tất value và object.

Ứng dụng không được tự ghép từng chunk thành chuỗi rồi giả định mỗi chunk là JSON độc lập. Chunk chỉ là đơn vị truyền dữ liệu; ranh giới token và document do parser xác định.

Điều này đặc biệt quan trọng với UTF-8. Một ký tự Unicode có thể chiếm nhiều byte và bị chia giữa hai chunk. Parser giữ phần byte chưa hoàn chỉnh và tiếp tục khi nhận phần còn lại. Không nên decode từng chunk thành `String` độc lập trước khi cấp vào byte parser, vì có thể làm hỏng ký tự bị chia giữa các chunk.

## 11. Kết thúc input bằng endOfInput()

Parser không thể tự biết một chunk hiện tại là chunk cuối cùng nếu ứng dụng chưa thông báo. Khi nguồn đã kết thúc, phải gọi:

```java
feeder.endOfInput();
```

Sau đó, tiếp tục gọi `nextToken()` để parser phát hết token còn lại và cuối cùng trả `null`.

`endOfInput()` không có nghĩa parser đóng ngay lập tức. Nó thông báo rằng sẽ không có thêm byte nào được cấp. Parser vẫn cần hoàn tất việc xử lý byte đã nhận.

Nếu JSON bị cắt giữa chừng, ví dụ:

```text
{"id":"ORD-1"
```

và ứng dụng gọi `endOfInput()`, parser sẽ phát hiện cấu trúc chưa hoàn chỉnh khi cố đọc đến cuối. Đây là lỗi input bị cắt cụt, khác với `NOT_AVAILABLE` trong lúc vẫn còn khả năng nhận chunk mới.

Không gọi `endOfInput()` sau mỗi chunk. Chỉ gọi một lần khi nguồn thực sự báo EOF hoặc kết nối đã kết thúc phần payload JSON.

## 12. Xử lý nhiều document hoặc framing của giao thức

Một non-blocking parser xử lý một luồng JSON theo cấu hình parser. Nếu giao thức truyền nhiều JSON document nối tiếp, ứng dụng phải xác định ranh giới document và chính sách parser phù hợp.

Ví dụ, NDJSON dùng newline để phân tách từng JSON document. Ứng dụng có thể tạo parser riêng cho mỗi record sau khi tách framing ở tầng giao thức, hoặc dùng cách tổ chức parser phù hợp với yêu cầu của phiên bản Jackson và format. Không nên coi một newline bất kỳ bên trong JSON string là ranh giới document; framing phải được xác định theo đúng quy tắc NDJSON, không phải bằng cách tìm byte newline một cách ngây thơ trong payload có thể chứa escape/string.

Nếu giao thức dùng length-prefix, hãy đọc đúng số byte của một frame rồi cấp cho parser và kết thúc input của frame đó. Framing là trách nhiệm của giao thức truyền; parser JSON chịu trách nhiệm cú pháp và token bên trong frame.

## 13. Non-blocking parser không tự làm mọi thứ bất đồng bộ

Một số hiểu nhầm thường gặp:

- **“Non-blocking parser tự đọc socket.”** Không đúng. Parser chỉ phân tích byte đã được cấp; ứng dụng hoặc thư viện mạng nhận byte và gọi feeder.
- **“Dùng non-blocking parser là có thread riêng.”** Không đúng. Parser không tự tạo thread. Ứng dụng quyết định callback, event loop hoặc executor.
- **“NOT_AVAILABLE nghĩa JSON sai.”** Không đúng. Nó thường chỉ có nghĩa cần thêm input.
- **“Mỗi chunk là một JSON document.”** Không đúng. Chunk có thể kết thúc ở bất kỳ vị trí byte nào.
- **“Có thể feed chunk mới bất cứ lúc nào.”** Không đúng. Chỉ feed khi feeder báo `needMoreInput()`.
- **“Đã feed hết chunk nghĩa JSON đã hoàn chỉnh.”** Không đúng. Cần gọi `endOfInput()` khi nguồn kết thúc và tiếp tục parse đến `null`.

Non-blocking parser là một thành phần hữu ích trong pipeline bất đồng bộ, nhưng hiệu quả của toàn hệ thống còn phụ thuộc cách nhận dữ liệu, quản lý backpressure, giới hạn bộ nhớ và cách xử lý kết quả.

## 14. Backpressure và quản lý bộ nhớ

Nếu nguồn gửi dữ liệu nhanh hơn tốc độ parser hoặc tầng nghiệp vụ xử lý, ứng dụng cần có cơ chế backpressure. Không nên tiếp tục tích lũy vô hạn các chunk chỉ vì parser có thể nhận dữ liệu từng phần.

Một số nguyên tắc:

- Chỉ nhận/cấp chunk tiếp theo khi feeder sẵn sàng và ứng dụng còn khả năng xử lý.
- Giới hạn tổng kích thước payload và kích thước chunk.
- Không giữ lại mọi token hoặc mọi object nếu chỉ cần xử lý từng record.
- Với chuỗi hoặc số cực lớn, cấu hình giới hạn đọc phù hợp của Jackson phiên bản đang dùng.
- Khi tầng nghiệp vụ bị chậm, tạm dừng đọc từ socket hoặc yêu cầu upstream giảm tốc độ nếu giao thức hỗ trợ.
- Khi kết nối bị hủy, đóng parser và giải phóng trạng thái của kết nối.

Non-blocking parser giúp tránh chặn thread trong lúc chờ byte, nhưng không làm cho payload lớn tự tiêu tốn ít bộ nhớ hơn. Nếu ứng dụng giữ toàn bộ object graph sau khi parse, mức sử dụng bộ nhớ vẫn có thể rất lớn.

## 15. Khi nào nên dùng non-blocking parser?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Đọc file local thông thường | Blocking `JsonParser` hoặc `ObjectMapper` đơn giản hơn |
| Đọc HTTP body đã được cung cấp như `InputStream` blocking | Blocking parser thường phù hợp |
| Server dùng event loop, byte đến theo callback | Non-blocking parser có thể phù hợp |
| Dữ liệu đến thành chunk từ reactive/network pipeline | Non-blocking parser nếu tích hợp đúng feeder và backpressure |
| Cần ánh xạ toàn bộ JSON nhỏ vào DTO | `ObjectMapper.readValue()` thường đơn giản hơn |
| Cần xử lý token tuần tự từ dữ liệu chưa đến đủ | Non-blocking `JsonParser` |
| Payload lớn nhưng nguồn blocking và không cần event loop | Blocking streaming parser vẫn có thể tiết kiệm bộ nhớ |

Không nên chọn non-blocking chỉ vì payload lớn. Blocking streaming parser cũng có thể xử lý dữ liệu lớn mà không tạo toàn bộ cây JSON. Lợi ích chính của non-blocking parser là khả năng trả quyền điều khiển khi chưa có đủ input, phù hợp với mô hình I/O không chặn.

## 16. Ghi nhớ

- Non-blocking parser đọc JSON theo từng chunk byte được ứng dụng cấp vào.
- `JsonFactory.createNonBlockingByteArrayParser()` tạo parser nhận dữ liệu qua `ByteArrayFeeder`.
- Chỉ gọi `feedInput()` khi `feeder.needMoreInput()` trả true.
- `JsonToken.NOT_AVAILABLE` có nghĩa parser cần thêm input, không phải token JSON và không mặc định là lỗi.
- Sau mỗi chunk, gọi `nextToken()` để xử lý hết token hiện có cho đến khi gặp `NOT_AVAILABLE`.
- Khi nguồn thật sự kết thúc, gọi `feeder.endOfInput()` đúng một lần rồi đọc đến khi parser trả `null`.
- Parser giữ trạng thái qua các chunk; không tạo parser mới cho từng chunk và không sửa vùng byte đã feed trước khi parser yêu cầu thêm input.
- Parser không tự nhận dữ liệu, tạo thread hay quản lý backpressure; ứng dụng chịu trách nhiệm về nguồn byte và lịch xử lý.
- Với file hoặc stream blocking thông thường, blocking streaming parser thường đơn giản hơn; non-blocking phù hợp với event loop và nguồn dữ liệu bất đồng bộ.

Khi tích hợp non-blocking parser, hãy thiết kế rõ vòng đời của một JSON stream: tạo parser một lần, cấp chunk khi feeder sẵn sàng, xử lý token đến `NOT_AVAILABLE`, báo `endOfInput()` khi nguồn kết thúc và đóng parser khi hoàn tất hoặc hủy kết nối. Quy trình đó giúp parse JSON tăng dần mà không giữ thread chờ dữ liệu chưa đến.
