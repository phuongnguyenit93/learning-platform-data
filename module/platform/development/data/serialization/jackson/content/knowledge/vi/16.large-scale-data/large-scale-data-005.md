# Thiết kế ranh giới bản ghi khi trao đổi JSON Lines

JSON thường được trao đổi như một tài liệu hoàn chỉnh: một object gốc hoặc một array chứa nhiều object. Nhưng với log, event stream, dữ liệu xuất theo lô và message liên tục, việc đóng gói tất cả bản ghi vào một JSON array có thể gây bất tiện. **JSON Lines** giải quyết bài toán này bằng cách đặt mỗi JSON value trên một dòng riêng. Ký tự xuống dòng trở thành ranh giới giữa các bản ghi.

Trong hệ sinh thái Jackson, việc serialize từng object thành JSON compact rồi ghi thêm dấu xuống dòng khá đơn giản. Phần cần thiết kế cẩn thận là framing: xác định chính xác một record bắt đầu và kết thúc ở đâu, xử lý dòng cuối chưa có newline, không nhầm newline trong nội dung chuỗi với delimiter, phát hiện record bị cắt hoặc chứa nhiều JSON value, và phục hồi lỗi mà không làm lệch các record phía sau.

Bài này tập trung vào ranh giới bản ghi khi trao đổi JSON Lines (thường được gọi là NDJSON), cách đọc/ghi bằng Jackson, cách xử lý stream và file lớn, cùng các quy tắc vận hành để dữ liệu không bị ghép nhầm hoặc mất record.

## 1. JSON Lines là gì?

JSON Lines là định dạng văn bản trong đó mỗi dòng chứa một JSON value độc lập. Mỗi record được phân cách bởi newline.

Ví dụ file `events.jsonl`:

```jsonl
{"id":"evt-1","type":"user.created","userId":42}
{"id":"evt-2","type":"invoice.paid","invoiceId":"INV-900","amount":125000.50}
{"id":"evt-3","type":"user.disabled","userId":42}
```

Mỗi dòng có thể được parse độc lập bằng Jackson. Không cần dấu phẩy giữa các record và không cần một array bao quanh toàn bộ nội dung.

Các tên gọi thường gặp:

- **JSON Lines**: tên định dạng và phần mở rộng phổ biến là `.jsonl`.
- **NDJSON (Newline Delimited JSON)**: tên khác thường dùng cho cùng kiểu framing.
- **JSONL**: cách viết tắt khác.

Trong thực tế, các hệ thống có thể có quy ước riêng về schema, encoding, dòng trống và record lỗi. Vì vậy, ngoài việc nói “file là JSON Lines”, hợp đồng trao đổi vẫn cần mô tả các quy tắc cụ thể.

## 2. Ranh giới record được xác định bằng newline

Điểm cốt lõi của JSON Lines là mỗi record phải nằm gọn trên một dòng vật lý. Ký tự LF (line feed, byte `0x0A`) là delimiter thông dụng; CRLF (`0x0D 0x0A`) cũng thường được chấp nhận khi file được tạo trên Windows.

```text
{"id":1,"name":"An"}\n
{"id":2,"name":"Binh"}\n
{"id":3,"name":"Chi"}\n
```

Khi đọc, ứng dụng tách input theo delimiter rồi parse từng đoạn như một JSON document riêng.

Ranh giới này khác với dấu phẩy hoặc dấu ngoặc của JSON array. Trong JSON Lines, newline thuộc về framing của luồng record, còn dấu ngoặc và dấu phẩy bên trong mỗi dòng thuộc cú pháp JSON của record đó.

### 2.1. Mỗi dòng là một JSON value hoàn chỉnh

Một record có thể là object:

```json
{"id":1,"status":"ok"}
```

Theo cú pháp JSON, một JSON value cũng có thể là array, string, number, boolean hoặc null. JSON Lines không bắt buộc mọi dòng phải là object. Tuy nhiên, các ứng dụng event/log thường quy định mỗi record là object để có schema field rõ ràng.

Ví dụ các dòng dưới đây đều là JSON value hợp lệ:

```jsonl
{"id":1}
["a","b"]
42
"ready"
true
null
```

Nếu ứng dụng chỉ chấp nhận object, hãy kiểm tra root shape hoặc deserialize vào DTO; đừng nhầm tính linh hoạt của định dạng với hợp đồng dữ liệu của ứng dụng.

### 2.2. Không có dấu phẩy giữa các dòng

Đây là JSON Lines hợp lệ:

```jsonl
{"id":1}
{"id":2}
```

Đây không phải JSON Lines hợp lệ theo cách framing một record mỗi dòng:

```text
{"id":1},
{"id":2}
```

Dấu phẩy ở cuối dòng đầu là token thừa sau JSON value. Một reader strict nên từ chối record này.

### 2.3. Không bọc toàn bộ file trong array

Một JSON array thông thường:

```json
[
  {"id":1},
  {"id":2}
]
```

là một JSON document duy nhất. JSON Lines:

```jsonl
{"id":1}
{"id":2}
```

là hai JSON document được ghép thành một luồng bằng delimiter newline.

Sự khác biệt ảnh hưởng đến cách đọc, append và phục hồi lỗi. Với array, parser phải xử lý cấu trúc array chung; với JSON Lines, có thể đọc từng dòng và xử lý độc lập.

## 3. Quy tắc framing quan trọng

Khi thiết kế producer và consumer, cần thống nhất các điểm sau:

| Quy tắc | Ý nghĩa |
|---|---|
| Encoding | Dùng UTF-8; tránh BOM ở đầu file |
| Record | Mỗi dòng không trống chứa đúng một JSON value |
| Delimiter | Dùng LF; có thể chấp nhận CRLF theo hợp đồng |
| JSON compact | Không pretty-print nhiều dòng cho một record |
| Dòng cuối | Nên kết thúc bằng newline; reader có thể xử lý record cuối ở EOF dù thiếu newline |
| Dòng trống | Không phải JSON value; quy định rõ bỏ qua hay từ chối |
| Record lỗi | Quy định dừng toàn bộ stream, bỏ qua có log hoặc đưa vào quarantine |
| Kích thước | Có giới hạn line/record size và giới hạn parser phù hợp |

JSON Lines thường yêu cầu UTF-8 và không dùng BOM. Với hệ thống cần khả năng tương tác, hãy phát UTF-8 không BOM, một JSON value mỗi dòng và newline sau mỗi record.

### 3.1. Tại sao newline an toàn làm delimiter?

Trong JSON string, ký tự điều khiển newline không được phép xuất hiện dưới dạng ký tự xuống dòng thô. Nó phải được escape thành hai ký tự văn bản `\n`:

```json
{"message":"Line one\nLine two"}
```

Byte của chuỗi JSON ở trên chứa dấu backslash và chữ `n`, không chứa byte LF làm delimiter giữa hai record. Vì thế, khi producer tạo JSON hợp lệ theo quy tắc escaping, newline vật lý có thể được dùng làm ranh giới record.

Nếu một producer tự ghép chuỗi JSON và chèn newline thô vào bên trong string, record không còn là JSON hợp lệ. Không nên tự xử lý bằng cách đoán xem newline đó thuộc nội dung hay delimiter; hãy sửa producer để serializer escape đúng.

### 3.2. Pretty printing phá vỡ framing một record mỗi dòng

Pretty printer có thể phát một object thành nhiều dòng:

```json
{
  "id": 1,
  "name": "An"
}
```

Nếu ghi nguyên văn output này vào JSON Lines, consumer sẽ nhìn thấy bốn dòng thay vì một record. Dòng đầu `{` không phải JSON value hoàn chỉnh, các dòng tiếp theo cũng không thể parse độc lập.

Vì vậy, writer JSON Lines phải dùng output compact. Không bật `SerializationFeature.INDENT_OUTPUT` cho mapper/writer tạo record JSONL.

## 4. JSON Lines khác gì JSON array và chuỗi JSON nối tiếp?

| Tiêu chí | JSON array | JSON Lines | Nhiều JSON value nối tiếp |
|---|---|---|---|
| Cấu trúc | Một JSON document có root array | Mỗi dòng là một JSON document | Nhiều root value trong một stream |
| Ranh giới record | Dấu phẩy và cấu trúc array | Newline | Khoảng trắng/token kết thúc value |
| Append record | Cần sửa array hoặc ghi theo cơ chế riêng | Thêm một dòng ở cuối | Có thể nối value theo quy ước parser |
| Phục hồi lỗi | Lỗi cú pháp có thể ảnh hưởng phần còn lại của array | Có thể bỏ qua/quarantine dòng lỗi rồi tiếp tục | Khó xác định ranh giới phục hồi sau lỗi |
| Xử lý từng record | Có thể cần parse array hoặc streaming qua phần tử | Đọc từng dòng độc lập | Dùng sequence parser/iterator |
| Pretty print | Hỗ trợ tự nhiên | Không phù hợp nếu một record trải nhiều dòng | Có thể gây mơ hồ nếu không có framing rõ |

Jackson có API đọc nhiều root value qua `ObjectReader.readValues(...)` và `MappingIterator`. API này hữu ích cho stream nhiều JSON value được phân cách bằng whitespace. Tuy nhiên, nó không đồng nghĩa với việc xác nhận nghiêm ngặt “mỗi dòng đúng một record”: parser có thể xem newline chỉ là whitespace và không dùng nó như boundary để phục hồi lỗi hoặc áp dụng chính sách theo dòng.

Nếu hợp đồng là JSON Lines, reader nên giữ được line boundary bằng cách đọc từng dòng hoặc dùng một framing layer tương đương.

## 5. Ghi JSON Lines bằng Jackson

Cách đơn giản và dễ kiểm soát là:

1. Dùng Jackson serialize một object thành JSON compact.
2. Ghi chuỗi JSON đó vào writer UTF-8.
3. Ghi một ký tự LF.
4. Lặp lại cho record tiếp theo.

Ví dụ:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class JsonLinesWriter {
    public static <T> void write(
            Path path,
            Iterable<T> records,
            ObjectMapper mapper
    ) throws IOException {
        ObjectWriter writer = mapper.writer();

        try (BufferedWriter output = Files.newBufferedWriter(
                path,
                StandardCharsets.UTF_8
        )) {
            for (T record : records) {
                String json = writer.writeValueAsString(record);

                output.write(json);
                output.write('\n');
            }
        }
    }
}
```

Mỗi lần gọi `writeValueAsString()` tạo một JSON document độc lập. Sau đó writer thêm LF làm delimiter. Dùng `output.write('\n')` giúp định dạng file nhất quán; `BufferedWriter.newLine()` sẽ dùng line separator của nền tảng, có thể là CRLF trên Windows.

### 5.1. Không tự nối JSON bằng string

Không nên viết:

```java
output.write("{\"id\":" + record.getId() + ",\"name\":\"" + record.getName() + "\"}");
```

Cách ghép chuỗi thủ công dễ sai khi dữ liệu chứa dấu nháy, backslash, ký tự điều khiển, Unicode hoặc giá trị null. Jackson đã xử lý escaping và quy tắc biểu diễn kiểu; ứng dụng chỉ cần thêm delimiter giữa các document.

### 5.2. Đảm bảo writer không pretty-print

Có thể tạo writer không indent tường minh:

```java
ObjectWriter jsonLineWriter = mapper.writer()
        .without(SerializationFeature.INDENT_OUTPUT);
```

Nếu mapper có cấu hình pretty printer ở nơi khác, hãy kiểm tra writer thực tế dùng để ghi JSON Lines. Mỗi lần serialize phải cho ra một dòng vật lý.

### 5.3. Ghi file ở chế độ append

Khi thêm record vào file hiện có:

```java
try (BufferedWriter output = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND
)) {
    String line = writer.writeValueAsString(record);
    output.write(line);
    output.write('\n');
}
```

Nếu file hiện tại không kết thúc bằng newline, record mới có thể bị nối vào cuối record trước và làm hỏng framing. Trước khi append vào file do hệ thống khác tạo, cần bảo đảm file kết thúc ở boundary hợp lệ. Có thể kiểm tra byte cuối file hoặc thiết kế writer sở hữu file từ đầu để luôn ghi newline sau mỗi record.

### 5.4. Xử lý flush và durability

Không nhất thiết flush sau mỗi record. Flush liên tục có thể làm giảm throughput đáng kể. Với batch/file writer, thường nên buffer nhiều record rồi flush theo batch hoặc theo chính sách ứng dụng.

Nếu yêu cầu durability cao, cần xác định rõ thời điểm dữ liệu phải được đẩy xuống hệ điều hành và thiết bị lưu trữ. `flush()` đẩy dữ liệu qua buffer của writer/stream nhưng không đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống đĩa. Với file quan trọng, cần xem xét `FileChannel.force(...)` hoặc cơ chế transactional phù hợp.

## 6. Đọc JSON Lines theo từng dòng

Với file hoặc stream vừa phải, `BufferedReader.readLine()` là cách trực quan để giữ ranh giới record:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class JsonLinesReader {
    public static <T> void read(
            Path path,
            Class<T> type,
            ObjectMapper mapper
    ) throws IOException {
        ObjectReader reader = mapper.readerFor(type)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

        try (BufferedReader input = Files.newBufferedReader(
                path,
                StandardCharsets.UTF_8
        )) {
            String line;
            long lineNumber = 0;

            while ((line = input.readLine()) != null) {
                lineNumber++;

                if (line.isBlank()) {
                    continue; // Hoặc từ chối, theo hợp đồng
                }

                try {
                    T record = reader.readValue(line);
                    process(record);
                } catch (IOException ex) {
                    throw new IOException(
                            "JSON Lines record lỗi tại dòng " + lineNumber,
                            ex
                    );
                }
            }
        }
    }

    private static <T> void process(T record) {
        // Xử lý record
    }
}
```

Ở ví dụ này:

- `readLine()` tách record theo line terminator và loại bỏ delimiter.
- `ObjectReader` tái sử dụng cấu hình và kiểu đích.
- `FAIL_ON_TRAILING_TOKENS` yêu cầu chỉ có một JSON value trong dòng; dữ liệu thừa sau value bị từ chối.
- `lineNumber` giúp xác định record lỗi.
- `try-with-resources` đóng reader do method mở.

Nếu hợp đồng yêu cầu mỗi dòng là một object, có thể kiểm tra root object hoặc đọc vào DTO. Nếu dòng có thể là các loại JSON value khác nhau, đọc thành `JsonNode` rồi kiểm tra root shape.

### 6.1. Vì sao cần FAIL_ON_TRAILING_TOKENS?

Giả sử một dòng chứa:

```text
{"id":1} {"id":2}
```

Dòng này có hai JSON value. Nếu chỉ đọc một value và không kiểm tra phần còn lại, record thứ hai có thể bị bỏ qua âm thầm. Bật `DeserializationFeature.FAIL_ON_TRAILING_TOKENS` giúp reader từ chối dữ liệu thừa sau root value.

Tương tự, một dòng có dấu phẩy thừa hoặc ký tự rác ở cuối cũng phải bị từ chối thay vì được xem là record hợp lệ.

### 6.2. Dòng trống và dòng chỉ chứa whitespace

Dòng trống không phải JSON value. Các hệ thống cần thống nhất chính sách:

- Bỏ qua dòng trống để chịu được file có blank line ngoài ý muốn.
- Từ chối dòng trống để bảo đảm producer tuân thủ định dạng nghiêm ngặt.
- Đếm và ghi metric số dòng trống để theo dõi chất lượng dữ liệu.

Nếu bỏ qua, nên phân biệt dòng trống với JSON literal `null`. Dòng `null` là một JSON value hợp lệ, dù DTO không nullable có thể không chấp nhận nó.

### 6.3. Dòng cuối không có newline

Một file có thể kết thúc ngay sau dấu `}` mà không có LF cuối cùng. `BufferedReader.readLine()` vẫn trả về nội dung dòng cuối đó trước khi trả null ở lần đọc tiếp theo. Reader nên parse record cuối ở EOF, thay vì bỏ nó chỉ vì thiếu delimiter cuối.

Producer nên ghi newline sau mỗi record để append dễ dàng và giảm khả năng nối nhầm, nhưng consumer có thể chấp nhận dòng cuối hợp lệ không có newline nếu hợp đồng cho phép.

## 7. Đọc từng record thành JsonNode

Khi schema record chưa cố định, dùng `JsonNode` làm kiểu đích:

```java
ObjectReader nodeReader = mapper.readerFor(JsonNode.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

try (BufferedReader input = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = input.readLine()) != null) {
        if (line.isBlank()) {
            continue;
        }

        JsonNode record = nodeReader.readValue(line);

        if (!record.isObject()) {
            throw new IllegalArgumentException("Mỗi record phải là object");
        }

        String type = record.path("type").asText(null);
        processByType(type, record);
    }
}
```

Tree model hữu ích khi từng dòng có chung envelope nhưng payload có thể thay đổi. Mỗi record được parse độc lập, nên có thể kiểm tra discriminator, chuyển một nhánh thành DTO và giữ phần mở rộng dưới dạng node.

Không cần đọc toàn bộ file thành một `ArrayNode`; làm như vậy sẽ mất lợi ích bộ nhớ của JSON Lines.

## 8. Xử lý record lỗi và phục hồi theo boundary

Một lợi ích lớn của JSON Lines là lỗi có thể được cô lập theo từng dòng. Nếu record thứ 20 sai cú pháp, consumer vẫn có thể tiếp tục từ record thứ 21 vì delimiter đã xác định vị trí bắt đầu của bản ghi tiếp theo.

Tuy nhiên, chỉ có thể phục hồi an toàn nếu framing còn nguyên. Nếu một record bị xuống dòng thô bên trong JSON string hoặc producer ghi một JSON object nhiều dòng, consumer không thể biết chính xác các dòng tiếp theo thuộc record hỏng hay record mới.

### 8.1. Ba chính sách xử lý lỗi phổ biến

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| Fail-fast | Dừng toàn bộ file/stream ở record lỗi đầu tiên | Import có tính toàn vẹn giao dịch, không được bỏ record |
| Skip and continue | Ghi nhận lỗi, bỏ dòng lỗi, tiếp tục dòng sau | Log/event analytics, dữ liệu độc lập từng record |
| Quarantine/dead-letter | Chuyển record lỗi và metadata sang nơi riêng để điều tra | Pipeline cần tiếp tục nhưng không muốn mất dữ liệu lỗi |

Ví dụ skip and continue:

```java
while ((line = input.readLine()) != null) {
    lineNumber++;

    if (line.isBlank()) {
        continue;
    }

    try {
        Event event = reader.readValue(line);
        process(event);
    } catch (JsonProcessingException ex) {
        logInvalidRecord(lineNumber, ex);
        writeToDeadLetter(lineNumber, line, ex);
    }
}
```

Trong production, cần cân nhắc lỗi I/O khác lỗi JSON. Nếu stream hỏng giữa chừng, tiếp tục đọc có thể không còn an toàn. Thường chỉ nên skip lỗi parse/mapping của một dòng khi reader vẫn có thể xác định ranh giới dòng kế tiếp.

### 8.2. Không log payload nhạy cảm

Log số dòng, loại exception, vị trí parser và correlation ID thường đủ để điều tra. Tránh ghi toàn bộ JSON nếu record có token, mật khẩu, dữ liệu cá nhân hoặc thông tin thanh toán.

Nếu cần lưu raw record vào dead-letter storage, áp dụng quyền truy cập, thời hạn lưu, mã hóa và masking phù hợp. Không nên để log ứng dụng trở thành nơi phát tán payload nhạy cảm.

### 8.3. Không tự ghép các dòng tiếp theo để sửa JSON lỗi

Một cách xử lý nguy hiểm là khi parse một dòng thất bại, nối thêm dòng tiếp theo cho đến khi dấu ngoặc cân bằng. Điều này phá vỡ hợp đồng JSON Lines và có thể ghép hai record độc lập thành một tài liệu giả. Nếu producer cần gửi pretty JSON nhiều dòng, hãy dùng một framing khác như JSON array hoặc một protocol có length-prefix.

## 9. Phân biệt lỗi record với lỗi transport

JSON Lines thường chạy trên file, HTTP response dạng streaming, pipe hoặc message transport. Cần phân biệt delimiter record với ranh giới của transport.

### 9.1. TCP chunk không phải record boundary

TCP là byte stream. Một lần `read()` có thể trả về:

- Một phần của record.
- Đúng một record.
- Nhiều record cùng lúc.
- Phần cuối của record này và phần đầu của record kế tiếp.

Không được giả định mỗi packet hoặc mỗi lần đọc socket tương ứng một JSON line. Cần buffer byte cho đến khi gặp LF, sau đó mới parse record. Phần byte còn lại được giữ cho lần đọc tiếp theo.

### 9.2. HTTP chunk cũng không phải JSONL record

Transfer chunking của HTTP chỉ là cơ chế vận chuyển. Một HTTP chunk có thể chứa nhiều dòng hoặc một phần dòng. Client phải tái lắp byte stream và áp dụng newline framing ở tầng ứng dụng.

### 9.3. Message broker có thể đã cung cấp boundary riêng

Nếu mỗi message của broker chứa đúng một JSON object, message boundary đã là framing. Không cần thêm JSON Lines bên trong message trừ khi một message cố ý chứa batch nhiều record.

Nếu broker message chứa JSON Lines batch, consumer vẫn phải tách từng dòng sau khi nhận payload.

## 10. UTF-8, CRLF và BOM

Encoding và line ending ảnh hưởng trực tiếp đến cách tách record.

### 10.1. Dùng UTF-8

JSON Lines nên dùng UTF-8. Với file:

```java
BufferedReader input = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
);
```

Khi ghi:

```java
BufferedWriter output = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8
);
```

Không dùng charset mặc định của hệ điều hành vì cùng file có thể được đọc khác nhau trên các máy.

### 10.2. LF và CRLF

LF là byte `0x0A`; CRLF là hai byte `0x0D 0x0A`. `BufferedReader.readLine()` xử lý các line ending phổ biến và trả nội dung không gồm delimiter.

Nếu tự viết byte framer, hãy tách theo LF và loại bỏ một byte CR ngay trước LF nếu chấp nhận CRLF. Không loại bỏ mọi ký tự CR ở giữa record; chúng có thể là dữ liệu không hợp lệ hoặc một phần nội dung được escape, tùy cách biểu diễn.

### 10.3. BOM ở đầu file

UTF-8 BOM là chuỗi byte `EF BB BF`. JSON Lines khuyến nghị không có BOM. Một số parser có thể xử lý BOM ở đầu input, nhưng không nên phụ thuộc vào hành vi này.

Nếu tích hợp với producer có BOM, xử lý rõ ở boundary đầu file hoặc từ chối theo hợp đồng. Không xóa chuỗi ký tự `\uFEFF` tùy tiện khỏi mọi record vì có thể thay đổi dữ liệu thực tế.

## 11. Xử lý stream lớn mà không đọc toàn bộ file vào bộ nhớ

JSON Lines phù hợp với dữ liệu lớn vì consumer có thể đọc và xử lý từng dòng. Bộ nhớ chủ yếu phụ thuộc kích thước record lớn nhất và trạng thái xử lý hiện tại, thay vì tổng kích thước file.

```text
InputStream
    |
    v
UTF-8 decoder / line buffer
    |
    v
Một dòng JSON hoàn chỉnh
    |
    v
Jackson ObjectReader
    |
    v
Một object Java
    |
    v
Xử lý / ghi DB / publish
    |
    v
Bỏ tham chiếu record, đọc dòng tiếp theo
```

Không nên làm:

```java
String all = Files.readString(path);
List<Event> events = mapper.readValue(
        all,
        new TypeReference<List<Event>>() {}
);
```

Code trên giả định toàn bộ file là một JSON array và giữ toàn bộ nội dung cùng danh sách object trong bộ nhớ. Với JSON Lines, hãy đọc từng record.

### 11.1. Line size limit

Dù đọc từng dòng, một dòng duy nhất vẫn có thể dài hàng trăm MB. `BufferedReader.readLine()` có thể cấp phát một chuỗi lớn trước khi ứng dụng kiểm tra độ dài. Với dữ liệu không tin cậy, cần giới hạn line length ở tầng byte framing hoặc dùng bounded line reader.

Ngoài giới hạn line, cấu hình Jackson `StreamReadConstraints` cho độ sâu lồng nhau, độ dài token và giới hạn liên quan trong phiên bản đang dùng. Hai lớp giới hạn giải quyết hai vấn đề khác nhau:

- Line limit kiểm soát tổng kích thước một record.
- Parser constraints kiểm soát cấu trúc và token bên trong JSON record.

### 11.2. Backpressure

Nếu tốc độ đọc file cao hơn tốc độ xử lý database hoặc downstream service, hàng đợi record có thể tăng vô hạn. Dùng bounded queue, batch có kích thước rõ ràng hoặc cơ chế backpressure để giới hạn số record đang chờ.

Không nên parse toàn bộ file thành list chỉ để chuyển sang một executor; điều đó đưa toàn bộ payload trở lại bộ nhớ.

### 11.3. Batch processing và checkpoint

Với file lớn, có thể xử lý theo batch và lưu checkpoint:

- Tên file hoặc stream partition.
- Số dòng/record đã xử lý.
- Offset byte hoặc vị trí an toàn tại boundary record.
- Trạng thái thành công/thất bại.
- ID record hoặc sequence number nếu producer cung cấp.

Không nên checkpoint giữa một dòng. Khi resume, phải bắt đầu từ boundary record đã xác định. Với file có thể bị thay đổi trong lúc xử lý, cần snapshot hoặc cơ chế khóa/đổi tên file để đảm bảo offset còn có ý nghĩa.

## 12. Ghi JSON Lines bằng JsonGenerator hoặc SequenceWriter

Cách serialize từng object thành String rồi ghi newline dễ hiểu và thường đủ tốt. Nếu cần giảm việc tạo String trung gian, có thể làm việc ở tầng streaming. Tuy nhiên, phải đảm bảo generator phát đúng một JSON document compact cho mỗi record và delimiter giữa các root value là newline.

Một hướng dễ kiểm soát là serialize từng record vào buffer nhỏ, sau đó ghi byte JSON và LF vào stream:

```java
ObjectWriter writer = mapper.writer();

try (OutputStream output = Files.newOutputStream(path)) {
    for (Event event : events) {
        byte[] json = writer.writeValueAsBytes(event);

        output.write(json);
        output.write('\n');
    }
}
```

Cách này tránh chuyển qua String nhưng vẫn tạo byte array cho từng record. Với record có kích thước vừa phải, nó là một trade-off rõ ràng.

Jackson có `SequenceWriter` để ghi nhiều root value qua một generator. Nếu dùng API này cho JSON Lines, phải cấu hình root value separator thành LF và xác nhận writer không bọc sequence trong array:

```java
JsonFactory factory = JsonFactory.builder()
        .rootValueSeparator("\n")
        .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();

try (SequenceWriter sequence = mapper.writer()
        .writeValues(outputStream)) {
    for (Event event : events) {
        sequence.write(event);
    }
}
```

Cấu hình root separator là chi tiết quan trọng: separator mặc định của generator có thể là khoảng trắng, không phải newline. `SequenceWriter` là sequence of root values; JSON Lines yêu cầu newline cụ thể làm framing. Hãy kiểm tra output thực tế và phiên bản Jackson vì API builder và cách quản lý tài nguyên có thể khác giữa các major version.

Nếu không cần tối ưu allocation, cách `writeValueAsString() + '\n'` thường dễ đọc và dễ kiểm thử hơn.

## 13. JSON Lines trên HTTP và event stream

Một HTTP endpoint có thể trả nhiều record liên tục dưới dạng JSON Lines, thường dùng content type như `application/x-ndjson` hoặc `application/jsonl` theo quy ước hệ thống. Cần thống nhất MIME type với consumer vì không phải mọi client framework tự động nhận diện giống nhau.

Ví dụ response body:

```jsonl
{"event":"connected","sequence":1}
{"event":"progress","sequence":2,"percent":25}
{"event":"progress","sequence":3,"percent":75}
{"event":"completed","sequence":4}
```

Client đọc response như byte stream, buffer đến newline, parse từng record và xử lý. Một HTTP response có thể kéo dài; không cần đợi toàn bộ response hoàn tất mới xử lý record đầu tiên.

### 13.1. Flush theo chính sách

Nếu endpoint cần gửi event gần thời gian thực, server có thể flush sau từng record hoặc theo batch nhỏ. Flush mỗi dòng giảm latency nhưng tăng số lần I/O; flush theo batch tăng throughput nhưng có thể tăng độ trễ.

Đây là lựa chọn vận hành, không thay đổi framing: mỗi record vẫn kết thúc bằng LF.

### 13.2. Client disconnect và record dang dở

Nếu kết nối bị đóng giữa một record, consumer có thể nhận một dòng cuối không đầy đủ. JSON parser sẽ báo lỗi. Không được coi record dở là thành công hoặc tự nối với dữ liệu của một kết nối khác.

Nếu server có thể resume, cần protocol bổ sung như sequence number, cursor hoặc event ID. JSON Lines tự nó chỉ định dạng record, không cung cấp cơ chế xác nhận, retry hay exactly-once delivery.

## 14. Tính nguyên tử và nhiều writer đồng thời

Nếu nhiều thread hoặc process cùng append vào một file JSON Lines, các đoạn ghi có thể xen kẽ. Một record được serialize thành chuỗi rồi ghi bằng nhiều thao tác I/O không nhất thiết được hệ điều hành đảm bảo atomic như một đơn vị.

Các lựa chọn an toàn hơn:

- Một writer thread sở hữu file; producer gửi object qua bounded queue.
- Dùng lock bao quanh toàn bộ thao tác ghi một record.
- Ghi file riêng theo partition/process rồi merge ở bước sau.
- Dùng message broker hoặc storage có cơ chế append/transaction phù hợp thay cho nhiều writer cùng ghi một file.

Ngay cả khi dùng `synchronized` trong Java, nó chỉ đồng bộ các thread trong cùng JVM. Nó không bảo vệ khỏi process khác hoặc máy khác cùng append file.

Nếu file được dùng như log bền vững, cần thêm quy tắc recovery khi process chết giữa lúc ghi. Dòng cuối có thể bị truncate; consumer cần phát hiện parse failure và xử lý theo chính sách recovery thay vì giả định mọi byte đã được ghi hoàn chỉnh.

## 15. Record bị cắt, file đang được ghi và tail -f

Một consumer theo dõi file đang được producer append có thể đọc khi record cuối chưa hoàn chỉnh. Đây là tình huống khác với file đã đóng.

Ví dụ file tạm thời kết thúc:

```text
{"id":1,"status":"done"}\n
{"id":2,"status":"pend
```

Dòng thứ hai chưa hoàn chỉnh. Reader theo dõi file cần giữ buffer và đợi thêm byte, thay vì báo record lỗi ngay lập tức. Chỉ khi producer đóng file hoặc xác nhận kết thúc stream mới có thể xem EOF là cuối dữ liệu.

Với file hoàn chỉnh, dòng cuối không có newline vẫn có thể là record hợp lệ nếu JSON value đã đầy đủ. Với file đang tăng trưởng, EOF hiện tại chỉ có thể là tạm thời.

Các chiến lược:

- Producer chỉ publish/rename file sau khi ghi xong; consumer chỉ đọc file đã hoàn tất.
- Ghi vào file tạm, flush/close rồi atomic rename sang tên chính thức nếu filesystem hỗ trợ.
- Với tailing liên tục, giữ partial line trong buffer và chờ dữ liệu mới.
- Theo dõi inode/file identity và rotation để không bỏ lỡ hoặc đọc lặp record.

## 16. Kiểm tra một record đúng một JSON value

Để bảo đảm ranh giới record, cần kiểm tra cả hai chiều:

1. Dòng có chứa một JSON value hợp lệ.
2. Sau JSON value không còn token khác ngoài whitespace hợp lệ của cùng dòng.

Dùng `FAIL_ON_TRAILING_TOKENS` trên ObjectReader là cách đơn giản:

```java
ObjectReader strictReader = mapper.readerFor(Event.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

Event event = strictReader.readValue(line);
```

Ví dụ:

| Dòng | Kết quả |
|---|---|
| `{"id":1}` | Hợp lệ |
| `{"id":1}   ` | Hợp lệ; trailing whitespace được chấp nhận |
| `{"id":1} {"id":2}` | Từ chối vì có root value thứ hai |
| `{"id":1},` | Từ chối vì có token thừa |
| `{"id":` | Từ chối vì JSON không hoàn chỉnh |
| ` ` | Dòng trống; xử lý theo policy |
| `null` | JSON value hợp lệ, nhưng có thể không hợp lệ với schema Event |

Nếu dùng `JsonNode`, kiểm tra root shape sau khi parse:

```java
JsonNode node = strictNodeReader.readValue(line);

if (!node.isObject()) {
    throw new IllegalArgumentException("Record phải là object");
}
```

## 17. Ví dụ hoàn chỉnh: import JSON Lines theo batch

Ví dụ sau đọc file event từng dòng, bỏ qua blank line, parse strict, gom một batch nhỏ và xử lý. Lỗi record được ghi nhận riêng; lỗi I/O làm dừng quá trình.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class EventJsonLinesImporter {
    private static final int BATCH_SIZE = 500;

    private final ObjectReader reader;

    public EventJsonLinesImporter(ObjectMapper mapper) {
        this.reader = mapper.readerFor(Event.class)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    }

    public void importFile(Path path) throws IOException {
        List<Event> batch = new ArrayList<>(BATCH_SIZE);
        long lineNumber = 0;

        try (BufferedReader input = Files.newBufferedReader(
                path,
                StandardCharsets.UTF_8
        )) {
            String line;

            while ((line = input.readLine()) != null) {
                lineNumber++;

                if (line.isBlank()) {
                    continue;
                }

                try {
                    Event event = reader.readValue(line);
                    batch.add(event);
                } catch (JsonProcessingException ex) {
                    recordInvalidLine(lineNumber, ex);
                    continue;
                }

                if (batch.size() == BATCH_SIZE) {
                    persistBatch(batch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            persistBatch(batch);
        }
    }

    private void recordInvalidLine(
            long lineNumber,
            JsonProcessingException error
    ) {
        // Ghi line number, error type và vị trí parser.
        // Tránh log raw JSON nếu có dữ liệu nhạy cảm.
    }

    private void persistBatch(List<Event> batch) {
        // Persist theo transaction hoặc batch API.
    }

    public static class Event {
        private String id;
        private String type;

        public Event() {
        }

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }
    }
}
```

Trong ví dụ, batch chỉ giữ tối đa 500 event đã parse. Nếu một dòng sai JSON, importer ghi nhận lỗi và tiếp tục từ dòng sau vì line framing vẫn xác định được boundary.

Trong hệ thống cần tính toàn vẹn cao, có thể thay skip bằng fail-fast hoặc dead-letter. Nếu persist batch thất bại, cần quy định rõ checkpoint và retry để tránh ghi trùng hoặc mất record.

## 18. Kiểm thử producer và consumer

JSON Lines cần test ở cấp byte/file, không chỉ test từng object serialize riêng. Những trường hợp quan trọng:

- Nhiều record được ghi liên tiếp, mỗi record đúng một dòng.
- Chuỗi có newline được escape thành `\n`, không tạo thêm physical line.
- Unicode tiếng Việt và emoji được ghi/đọc bằng UTF-8.
- CRLF được đọc đúng nếu consumer hỗ trợ.
- Dòng trống theo đúng policy.
- Dòng cuối không có newline.
- Dòng chứa hai JSON value bị từ chối.
- Record JSON hỏng không làm lệch boundary record kế tiếp.
- Record quá dài bị giới hạn theo hợp đồng.
- Pretty printer không được bật trong JSONL writer.

Ví dụ JUnit kiểm tra output có ba dòng và round-trip:

```java
@Test
void shouldWriteOneCompactJsonValuePerLine() throws Exception {
    Path file = tempDir.resolve("events.jsonl");

    List<Event> events = List.of(
            new Event("1", "created", "Line one\nLine two"),
            new Event("2", "updated", "Tiếng Việt"),
            new Event("3", "deleted", "done")
    );

    writeEvents(file, events, mapper);

    List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);

    assertEquals(3, lines.size());

    ObjectReader reader = mapper.readerFor(Event.class)
            .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    List<Event> restored = new ArrayList<>();
    for (String line : lines) {
        restored.add(reader.readValue(line));
    }

    assertEquals(events, restored);
}
```

Test thực tế nên dùng DTO có `equals/hashCode` phù hợp hoặc so sánh field quan trọng. Đặc biệt, kiểm tra file dưới dạng text/byte để bảo đảm một record không bị pretty-print thành nhiều dòng.

## 19. Chọn JSON Lines hay định dạng khác?

JSON Lines phù hợp khi record độc lập và cần đọc/ghi tuần tự. Nhưng không phải mọi batch JSON đều nên dùng JSONL.

| Nhu cầu | Lựa chọn gợi ý |
|---|---|
| File chứa nhiều record độc lập, cần append và xử lý từng dòng | JSON Lines |
| Một tài liệu có quan hệ cấu trúc rõ, cần một root array | JSON array |
| Record có thể chứa format nhiều dòng hoặc cần framing nhị phân | Length-prefixed protocol hoặc container format |
| Dữ liệu lớn cần schema cột, nén và scan phân tích | Định dạng cột như Parquet |
| Stream sự kiện có partition, offset, retry và retention | Message broker; payload có thể là JSON hoặc JSON Lines tùy envelope |
| Cần xác thực schema độc lập với Java | JSON Schema hoặc schema registry phù hợp |

JSON Lines chỉ giải quyết cách phân tách record. Nó không cung cấp schema registry, compression, checksum, transaction, ordering toàn cục, retry hay exactly-once semantics. Những yêu cầu đó cần cơ chế ở tầng transport hoặc storage.

## 20. Các lỗi thiết kế thường gặp

**Ghi pretty JSON nhiều dòng vào JSONL.** Consumer đọc từng dòng sẽ thấy các fragment không phải JSON document. Dùng output compact cho mỗi record.

**Nối JSON object liên tiếp mà không có delimiter.** Hai object dính liền không tạo thành một JSONL stream hợp lệ. Ghi LF sau mỗi record.

**Thêm dấu phẩy như array.** JSON Lines không dùng dấu phẩy phân cách record. Mỗi dòng là một document độc lập.

**Giả định một lần socket read là một record.** TCP và HTTP chunking không giữ ranh giới JSONL. Buffer đến LF trước khi parse.

**Bỏ qua kiểm tra trailing tokens.** Một dòng có thể chứa hai root JSON value; bật `FAIL_ON_TRAILING_TOKENS` để từ chối.

**Bỏ record cuối vì thiếu newline.** Reader file hoàn chỉnh nên parse dòng cuối ở EOF nếu nội dung là JSON hợp lệ.

**Xem EOF tạm thời của file đang được ghi là record lỗi.** Với tailing stream, giữ partial line và chờ byte tiếp theo; chỉ chốt record khi gặp LF hoặc producer xác nhận kết thúc.

**Cho phép line size không giới hạn.** Một record cực lớn có thể gây cạn heap dù đọc theo dòng. Đặt giới hạn framing và parser.

**Nhiều writer cùng append không đồng bộ.** Các đoạn JSON và newline có thể xen kẽ. Dùng một writer owner hoặc cơ chế khóa/partition.

**Dùng JSONL như thể nó là message broker.** JSONL không tự cung cấp acknowledgment, offset, retry hoặc durability. Thiết kế những thuộc tính này ở tầng vận chuyển/lưu trữ.

## 21. Quy trình thiết kế ranh giới record

Khi triển khai producer/consumer JSON Lines, hãy xác định tuần tự:

1. **Chốt schema record:** mỗi dòng là object hay JSON value bất kỳ; field bắt buộc và versioning ra sao?
2. **Chốt encoding:** UTF-8 không BOM; line ending LF hay chấp nhận CRLF?
3. **Chốt compact output:** serializer không pretty-print; một root JSON value trên một dòng.
4. **Chốt delimiter cuối:** producer luôn ghi LF sau record; consumer xử lý EOF cuối file như thế nào?
5. **Chốt reader strictness:** có bật `FAIL_ON_TRAILING_TOKENS` không; dòng trống được bỏ qua hay từ chối?
6. **Chốt error policy:** fail-fast, skip hay quarantine; lỗi parse khác lỗi I/O ra sao?
7. **Chốt giới hạn:** line size, token size, nesting depth, batch size và queue capacity.
8. **Chốt concurrency:** một writer hay nhiều writer; ai sở hữu file/stream?
9. **Chốt recovery:** file rotation, partial final record, checkpoint và retry được xử lý thế nào?
10. **Kiểm thử ở cấp file/byte:** không chỉ test mapper với một JSON string; kiểm tra nhiều record liên tiếp và lỗi ở giữa luồng.

## 22. Kết luận

JSON Lines dùng newline làm ranh giới giữa các JSON value độc lập. Với Jackson, producer serialize mỗi object thành JSON compact rồi ghi LF; consumer đọc từng dòng, parse bằng `ObjectReader` và kiểm tra trailing tokens để bảo đảm mỗi dòng chỉ chứa một record. Newline bên trong JSON string phải được escape, còn pretty printing nhiều dòng sẽ phá vỡ framing.

Ranh giới record cần được giữ xuyên suốt file, HTTP và TCP stream: chunk transport không phải record boundary, dòng cuối ở EOF cần được xử lý theo trạng thái stream, và record lỗi chỉ có thể được bỏ qua an toàn khi delimiter còn nguyên. Khi kết hợp UTF-8, giới hạn kích thước, chính sách lỗi, kiểm soát writer đồng thời và kiểm thử ở cấp file, JSON Lines trở thành cách đơn giản để trao đổi dữ liệu lớn theo từng bản ghi.

## Tài liệu tham khảo

- [JSON Lines — format definition and conventions](https://jsonlines.org/)
- [NDJSON Specification](https://github.com/ndjson/ndjson-spec)
- [Jackson Databind — ObjectReader API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectReader.html)
- [Jackson Databind — SequenceWriter API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/SequenceWriter.html)
- [Jackson Core — JsonFactory API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonFactory.html)
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)

