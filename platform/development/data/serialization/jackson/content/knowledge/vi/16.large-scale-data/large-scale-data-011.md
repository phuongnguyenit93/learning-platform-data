# Phân biệt chưa đủ dữ liệu đầu vào và lỗi cú pháp thực sự

Khi đọc JSON từ mạng, file lớn hoặc một luồng được chia thành nhiều gói dữ liệu, parser có thể nhận được một phần document trước khi phần còn lại đến. Tại thời điểm đó, dữ liệu đang có chưa đủ để kết luận document sai cú pháp.

Cần phân biệt ba trạng thái:

- **Chưa đủ dữ liệu**: nguồn vẫn có thể gửi thêm byte hoặc ký tự. Một chuỗi JSON chưa hoàn chỉnh có thể trở thành hợp lệ khi phần tiếp theo đến.
- **Đã kết thúc nguồn nhưng JSON chưa hoàn chỉnh**: nguồn báo EOF thật sự trong khi object, array, string hoặc giá trị vẫn chưa kết thúc. Đây thường là lỗi JSON bị cắt cụt.
- **Lỗi cú pháp thực sự**: parser đã gặp một cấu trúc không thể trở thành JSON hợp lệ theo cú pháp và cấu hình hiện tại, chẳng hạn thiếu value sau dấu hai chấm hoặc có dấu phẩy sai vị trí.

Với Jackson, sự phân biệt này đặc biệt quan trọng khi dùng Streaming API và non-blocking parser. Trong chế độ non-blocking, JsonToken.NOT_AVAILABLE có nghĩa parser cần thêm input để tiếp tục; nó không phải lỗi cú pháp và cũng không phải một giá trị JSON.

## 1. Một phần dữ liệu chưa chắc là một JSON document sai

Giả sử ứng dụng nhận JSON qua mạng theo từng chunk. Chunk đầu tiên có thể chứa:

~~~json
{"customer":{"name":"An"
~~~

Chunk tiếp theo mới chứa:

~~~json
,"age":25}}
~~~

Ghép hai phần lại, ta có document hoàn chỉnh:

~~~json
{
  "customer": {
    "name": "An",
    "age": 25
  }
}
~~~

Nếu parser được thông báo rằng chunk đầu tiên chính là toàn bộ document, nó có thể báo lỗi vì object chưa đóng. Nhưng nếu nguồn vẫn đang mở và chunk tiếp theo sẽ đến, đây chỉ là trạng thái chưa đủ dữ liệu.

Ranh giới chunk do mạng, file buffer hoặc cơ chế truyền tải tạo ra. Nó không nhất thiết trùng với ranh giới token JSON. Một chunk có thể kết thúc:
- Giữa tên property.
- Giữa một string.
- Giữa một escape sequence.
- Giữa chữ số của number.
- Sau dấu hai chấm nhưng trước value.
- Bên trong một object hoặc array lồng nhau.

~~~mermaid
flowchart TD
    A[Nhận một chunk] --> B[Parser đọc phần dữ liệu hiện có]
    B --> C{Đã đủ token tiếp theo?}
    C -->|Chưa, nguồn còn mở| D[Chờ thêm input]
    D --> A
    C -->|Có token hợp lệ| E[Tiếp tục parse]
    E --> B
    C -->|Gặp cấu trúc sai không thể khắc phục| F[Lỗi cú pháp]
    C -->|Nguồn kết thúc thật sự| G{Document đã hoàn chỉnh?}
    G -->|Có| H[Kết thúc bình thường]
    G -->|Không| I[Lỗi EOF / JSON bị cắt]
~~~

Điểm quyết định không phải parser đã nhận bao nhiêu chunk. Điểm quyết định là nguồn còn khả năng cung cấp dữ liệu hay đã xác nhận kết thúc.

## 2. Ba trạng thái cần phân biệt

| Trạng thái | Ví dụ phần dữ liệu đã nhận | Điều cần làm |
|---|---|---|
| Chưa đủ dữ liệu, nguồn còn mở | {"name":"An" | Chờ thêm input |
| EOF thật khi cấu trúc chưa đóng | {"name":"An" rồi nguồn kết thúc | Báo JSON bị cắt hoặc thiếu dữ liệu cuối |
| Sai cú pháp ngay trong phần đã nhận | {"name": } | Báo lỗi parse |

Hai dòng đầu có cùng chuỗi byte tại một thời điểm. Chúng khác nhau ở trạng thái nguồn:

- Nếu kết nối còn mở, parser phải chờ.
- Nếu transport xác nhận EOF, parser phải kết luận document đã kết thúc.
- Nếu cú pháp đã sai độc lập với phần tiếp theo, parser có thể báo lỗi ngay cả khi nguồn vẫn mở.

Ví dụ {"name": } không thể được sửa bằng cách nối thêm ký tự vào cuối document: sau dấu hai chấm, JSON cần một value, nhưng parser đã gặp dấu đóng object. Ngược lại, {"name":"An" có thể hợp lệ nếu tiếp tục bằng }.

## 3. EOF thật sự khác với ranh giới chunk

### 3.1. InputStream báo EOF như thế nào?

Với Java InputStream, lời gọi read(byte[]) có thể trả về ít byte hơn số byte yêu cầu. Điều đó bình thường và không có nghĩa document đã kết thúc.

EOF được biểu diễn bằng giá trị -1 khi không còn byte nào để đọc:

~~~java
int count;

while ((count = input.read(buffer)) != -1) {
    // Xử lý count byte vừa nhận.
}
~~~

Không được coi một lần đọc trả về ít byte hơn buffer size là EOF. Ví dụ buffer có 8192 byte nhưng read() chỉ trả về 300 byte; nguồn có thể vẫn còn dữ liệu.

Với parser blocking của Jackson, parser tự yêu cầu thêm dữ liệu từ InputStream khi cần. Ứng dụng thường chỉ cần truyền một stream liên tục:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Order order = mapper.readValue(input, Order.class);
}
~~~

Jackson không coi mỗi lần InputStream.read() trả về một phần dữ liệu là một JSON document riêng. Nó tiếp tục đọc cho đến khi hoàn tất giá trị cần ánh xạ hoặc gặp lỗi/EOF.

### 3.2. Không parse từng chunk như một document độc lập

Một lỗi thiết kế thường gặp là lấy từng packet/chunk rồi gọi readValue() riêng:

~~~java
// Cách làm sai nếu chunk chỉ là một phần của cùng JSON document.
Order order = mapper.readValue(chunk, Order.class);
~~~

Nếu chunk kết thúc giữa document, parser nhận một input hoàn chỉnh nhưng bị cắt và báo lỗi. Chunk tiếp theo lại không phải một document độc lập nên cũng không thể được ánh xạ riêng.

Đối với một JSON document được truyền thành nhiều phần, hãy:
- Duy trì một parser trên nguồn liên tục; hoặc
- Dùng non-blocking parser và feeder để cấp từng chunk cho cùng một parser; hoặc
- Tích lũy dữ liệu đến khi có framing/document boundary rõ ràng rồi mới parse, nếu kích thước phù hợp.

Không được tự nối các message khác nhau nếu giao thức không xác định chúng thuộc cùng một document.

## 4. Blocking parser và non-blocking parser khác nhau ra sao?

### 4.1. Blocking parser

Parser blocking đọc từ InputStream hoặc Reader. Khi cần thêm dữ liệu, nó yêu cầu nguồn đọc tiếp. Nếu một lần đọc chỉ nhận được một phần document, parser tiếp tục lấy dữ liệu.

~~~java
JsonFactory factory = new JsonFactory();

try (InputStream input = socketInputStream;
     JsonParser parser = factory.createParser(input)) {

    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        handleToken(parser, token);
    }
}
~~~

Trong ví dụ này:
- Parser đọc token từ cùng một nguồn.
- Khi cần thêm dữ liệu, parser tiếp tục đọc.
- Khi nguồn trả EOF, parser biết không còn input nữa.
- Nếu JSON vẫn chưa hoàn chỉnh, parser có thể ném lỗi unexpected end-of-input.

Ứng dụng không cần tự phân biệt từng lần đọc byte của stream. Parser blocking quản lý buffer và việc đọc tiếp.

### 4.2. Non-blocking parser

Non-blocking parser được thiết kế cho trường hợp ứng dụng nhận dữ liệu theo từng chunk và không muốn chờ đồng bộ bên trong parser. Ứng dụng cấp dữ liệu qua feeder, rồi yêu cầu parser đọc các token hiện có.

Trong Jackson Core, non-blocking parser có thể trả về JsonToken.NOT_AVAILABLE. Token đặc biệt này có nghĩa parser chưa thể tạo token tiếp theo vì cần thêm input. Nó không phải token trong JSON document.

| Kết quả | Ý nghĩa |
|---|---|
| Một JsonToken bình thường | Parser vừa đọc được token |
| JsonToken.NOT_AVAILABLE | Cần thêm input để tiếp tục |
| null | Parser đã kết thúc document/nguồn theo trạng thái hiện tại |
| Exception parse | Cấu trúc dữ liệu không hợp lệ hoặc EOF xảy ra khi document chưa hoàn chỉnh |

Không được chuyển NOT_AVAILABLE cho code xử lý nghiệp vụ như thể nó là token JSON. Hãy dừng vòng đọc token, chờ cấp thêm input rồi tiếp tục cùng parser.

## 5. Ví dụ non-blocking parser với ByteArrayFeeder

Jackson Core cung cấp ByteArrayFeeder để cấp các đoạn byte cho non-blocking byte-array parser.

Ví dụ dưới đây minh họa vòng đời parser khi ứng dụng đã nhận các chunk từ một nguồn bên ngoài:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.async.ByteArrayFeeder;

import java.io.IOException;

public class IncrementalJsonReader {

    private final JsonParser parser;
    private final ByteArrayFeeder feeder;

    public IncrementalJsonReader() throws IOException {
        JsonFactory factory = new JsonFactory();
        this.parser = factory.createNonBlockingByteArrayParser();
        this.feeder = (ByteArrayFeeder) parser.getNonBlockingInputFeeder();
    }

    public void acceptChunk(byte[] bytes) throws IOException {
        if (!feeder.needMoreInput()) {
            throw new IllegalStateException(
                    "Parser still has unconsumed input"
            );
        }

        feeder.feedInput(bytes, 0, bytes.length);
        drainAvailableTokens();
    }

    public void endInput() throws IOException {
        if (!feeder.needMoreInput()) {
            throw new IllegalStateException(
                    "Parser still has unconsumed input"
            );
        }

        feeder.endOfInput();
        drainAvailableTokens();
    }

    private void drainAvailableTokens() throws IOException {
        JsonToken token;

        while ((token = parser.nextToken()) != null) {
            if (token == JsonToken.NOT_AVAILABLE) {
                // Parser cần chunk tiếp theo; đây chưa phải lỗi.
                return;
            }

            handleToken(parser, token);
        }
    }

    private void handleToken(JsonParser parser, JsonToken token)
            throws IOException {
        // Xử lý token theo schema của ứng dụng.
        System.out.println(token);
    }

    public void close() throws IOException {
        parser.close();
    }
}
~~~

Cách sử dụng theo thứ tự:

~~~java
IncrementalJsonReader reader = new IncrementalJsonReader();

reader.acceptChunk("{\"name\":\"An\"".getBytes(StandardCharsets.UTF_8));

// Parser có thể phát ra một số token rồi trả NOT_AVAILABLE.

reader.acceptChunk(",\"age\":25}".getBytes(StandardCharsets.UTF_8));

// Cấp phần còn lại của document.

reader.endInput();

// Chỉ gọi endInput khi transport xác nhận không còn dữ liệu.
reader.close();
~~~

Ví dụ này tập trung vào cách cấp dữ liệu. Trong ứng dụng thực tế, cần quản lý vòng đời parser bằng try-with-resources hoặc cơ chế tương đương; bảo đảm mỗi chunk được cấp đúng thứ tự và không ghi đè input chưa được parser tiêu thụ.

feeder.needMoreInput() cho biết parser đã tiêu thụ hết input hiện được cấp và sẵn sàng nhận chunk tiếp theo. Không gọi feedInput() khi feeder chưa yêu cầu thêm dữ liệu.

### 5.1. Khi nào gọi endOfInput()?

endOfInput() là thông báo rằng nguồn dữ liệu đã kết thúc thật sự. Đây là tín hiệu khác hoàn toàn với việc một chunk vừa được xử lý xong.

- Sau chunk giữa luồng: cấp dữ liệu tiếp theo khi feeder yêu cầu.
- Sau chunk cuối cùng: cấp chunk cuối, để parser tiêu thụ; khi feeder cần thêm dữ liệu và transport xác nhận EOF, gọi endOfInput().
- Sau endOfInput(): tiếp tục drain parser để nó hoàn tất document hoặc báo lỗi nếu cấu trúc chưa đóng.

Nếu gọi endOfInput() quá sớm, parser sẽ coi phần input đã cấp là toàn bộ document. Một JSON hợp lệ nhưng bị chia nhiều chunk có thể bị báo unexpected EOF.

### 5.2. Không dùng NOT_AVAILABLE như bằng chứng dữ liệu sai

Một parser có thể trả NOT_AVAILABLE nhiều lần trong cùng document, tùy ranh giới chunk. Đây là trạng thái bình thường của incremental parsing.

Ví dụ:
- Chunk 1: {"customer":
- Chunk 2: {"name":"An",
- Chunk 3: "age":25}}

Sau chunk 1, parser chưa thể đọc value của customer.
Sau chunk 2, parser có thể đọc thêm một phần object nhưng cần chunk tiếp theo để hoàn tất.
Sau chunk 3, parser có thể hoàn tất document.

Chỉ khi nguồn kết thúc và parser không thể hoàn tất mới có thể kết luận document bị cắt.

## 6. Nhận diện lỗi cú pháp thực sự

Một số cấu trúc sai có thể được phát hiện ngay khi parser nhận token gây mâu thuẫn.

### 6.1. Thiếu value sau dấu hai chấm

~~~json
{
  "name": ,
  "age": 25
}
~~~

Sau dấu hai chấm, parser cần một JSON value. Dấu phẩy không thể bắt đầu value nên đây là lỗi cú pháp.

### 6.2. Dấu phẩy thừa

~~~json
{
  "name": "An",
}
~~~

JSON chuẩn không cho phép dấu phẩy cuối object. Với cấu hình parser mặc định nghiêm ngặt, cấu trúc này gây lỗi parse. Jackson có feature cho phép trailing comma ở một số phiên bản; nếu bật feature đó, kết quả có thể khác. Vì vậy, hãy xét cả cấu hình parser khi xác định cú pháp được chấp nhận.

### 6.3. String có escape không hợp lệ

~~~json
{
  "message": "Hello\q"
}
~~~

q không phải escape sequence hợp lệ trong JSON. Parser có thể báo lỗi ngay khi đọc escape sequence sai.

### 6.4. Thiếu dấu phẩy giữa các property

~~~json
{
  "name": "An"
  "age": 25
}
~~~

Sau value của name, parser mong đợi dấu phẩy hoặc dấu đóng object. Gặp tên property tiếp theo mà không có dấu phân cách là lỗi cú pháp.

### 6.5. Dữ liệu dư sau một document

~~~json
{"id":1} {"id":2}
~~~

Đây là hai JSON value ở root. Nếu giao thức yêu cầu đúng một JSON document, ứng dụng cần kiểm tra token dư sau root và từ chối dữ liệu ngoài document. Nếu giao thức là một chuỗi JSON value hoặc NDJSON, nhiều root value có thể là chủ đích; phải dựa vào framing của giao thức.

## 7. EOF khi JSON chưa hoàn chỉnh: lỗi bị cắt cụt

Một JSON prefix có thể chờ thêm dữ liệu khi nguồn còn mở. Nhưng nếu nguồn đã kết thúc thật sự, phần còn thiếu sẽ không bao giờ đến.

Object chưa đóng:

~~~json
{
  "name": "An"
~~~

Array chưa đóng:

~~~json
{
  "items": [1, 2, 3
}
~~~

String chưa đóng:

~~~json
{
  "message": "hello
}
~~~

Khi InputStream trả -1 hoặc non-blocking feeder nhận endOfInput(), parser biết nguồn đã hết. Nếu cấu trúc đang ở trạng thái cần thêm token, Jackson có thể ném JsonEOFException hoặc một dạng JsonParseException báo unexpected end-of-input, tùy vị trí và phiên bản.

Đây là lỗi dữ liệu bị cắt cụt (truncated input), có thể do:
- File chỉ được ghi một phần.
- Kết nối bị đóng giữa document.
- Producer dừng trước khi ghi dấu đóng object/array.
- Giới hạn kích thước hoặc timeout khiến tầng truyền tải cắt payload.
- Ứng dụng gọi endOfInput() trước khi đã cấp hết chunk.

Cần điều tra cả nguồn truyền tải và logic cấp dữ liệu, không chỉ sửa JSON.

## 8. Phân biệt parse error với lỗi I/O và timeout

Không phải mọi thất bại khi đọc dữ liệu đều là lỗi cú pháp.

| Tình huống | Loại lỗi thường gặp | Cách hiểu |
|---|---|---|
| Gặp dấu phẩy sai vị trí | JsonParseException | Cú pháp sai |
| String/object chưa đóng khi EOF thật | JsonEOFException hoặc JsonParseException | Input bị cắt hoặc kết thúc quá sớm |
| Socket reset giữa document | IOException/SocketException | Lỗi truyền tải; payload có thể bị thiếu |
| Chờ chunk tiếp theo quá lâu | Timeout ở tầng I/O hoặc transport | Chưa có dữ liệu trong thời hạn cho phép |
| Non-blocking parser trả NOT_AVAILABLE | Không phải exception | Cần cấp thêm input |
| JSON hợp lệ nhưng field không ánh xạ vào Java type | JsonMappingException | Lỗi data binding |

Ví dụ xử lý exception:

~~~java
try (InputStream input = socket.getInputStream()) {
    Order order = mapper.readValue(input, Order.class);
    process(order);

} catch (JsonParseException e) {
    // JSON sai cú pháp hoặc bị cắt khi parser đã nhận EOF.
    logParseError(e);

} catch (JsonMappingException e) {
    // JSON không ánh xạ được vào kiểu Java đích.
    logMappingError(e);

} catch (IOException e) {
    // Lỗi đọc nguồn, socket hoặc file.
    logTransportOrFileError(e);
}
~~~

Trong Jackson, JsonMappingException và JsonParseException đều thuộc hệ exception xử lý JSON. Thứ tự catch cụ thể cần theo cây kế thừa của phiên bản đang dùng; nếu cần bắt mọi JsonProcessingException, đặt catch lớp cha sau các lớp con. Một số lỗi I/O có thể được bọc trong exception xử lý JSON, nên hãy giữ nguyên cause để điều tra.

Không nên biến mọi lỗi socket thành "invalid JSON". Nếu kết nối bị ngắt giữa chừng, server có thể chưa bao giờ nhận được toàn bộ document để xác định cú pháp cuối cùng.

## 9. Kiểm tra location để chẩn đoán

JsonProcessingException cung cấp getLocation() để lấy JsonLocation:

~~~java
try {
    Order order = mapper.readValue(input, Order.class);
} catch (JsonProcessingException e) {
    JsonLocation location = e.getLocation();

    System.err.println(e.getOriginalMessage());

    if (location != null) {
        System.err.println("Line: " + location.getLineNr());
        System.err.println("Column: " + location.getColumnNr());
        System.err.println("Byte offset: " + location.getByteOffset());
        System.err.println("Character offset: " + location.getCharOffset());
    }

    throw e;
}
~~~

Với lỗi EOF, location thường gần cuối phần dữ liệu parser nhận được. Với lỗi cú pháp cụ thể, location chỉ vị trí parser phát hiện vấn đề. Vị trí này hữu ích nhưng không phải lúc nào cũng là byte đầu tiên của nguyên nhân.

Với lỗi mapping vào object lồng nhau, JsonMappingException còn có getPathReference() để chỉ property/index liên quan. Location và mapping path trả lời hai câu hỏi khác nhau:
- Location: lỗi được phát hiện ở đâu trong luồng?
- Path: lỗi xảy ra khi ánh xạ vào nhánh/property nào?

## 10. Ranh giới chunk có thể cắt giữa ký tự UTF-8

JSON truyền qua byte stream thường dùng UTF-8. Một ký tự Unicode có thể được mã hóa bằng nhiều byte. Vì thế, ranh giới chunk có thể nằm giữa các byte của cùng một ký tự.

Nếu mỗi chunk được chuyển độc lập thành String bằng cách gọi new String(chunk, UTF_8), chunk đầu có thể kết thúc giữa một ký tự và tạo ra ký tự thay thế hoặc dữ liệu hỏng.

Với non-blocking byte-array parser của Jackson, hãy cấp byte thô theo thứ tự cho cùng parser. Parser duy trì trạng thái decode qua ranh giới input theo cơ chế của nó:

~~~java
feeder.feedInput(buffer, 0, count);
~~~

Nếu ứng dụng cần decode riêng thành Reader/String, hãy dùng một CharsetDecoder có trạng thái giữa các lần decode thay vì tạo String độc lập từ từng mảng byte.

Không nên nhầm lỗi decode/encoding ở tầng ký tự với lỗi cú pháp JSON. Cả hai đều có thể khiến parser không đọc được document, nhưng nguyên nhân và cách sửa khác nhau.

## 11. JSON document, JSON sequence và NDJSON

Muốn phân biệt input chưa đủ với lỗi thực sự, phải biết giao thức định nghĩa ranh giới document như thế nào.

### 11.1. Một JSON document duy nhất

Một request HTTP body thường mang một JSON value. Body kết thúc là parser biết đã hết input. Nếu body kết thúc giữa object, đó là JSON bị cắt.

~~~json
{
  "event": "created",
  "id": 101
}
~~~

### 11.2. JSON Lines / NDJSON

NDJSON thường dùng một JSON value trên mỗi dòng. Mỗi dòng hoàn chỉnh là một record riêng:

~~~text
{"id":1,"event":"created"}
{"id":2,"event":"updated"}
{"id":3,"event":"deleted"}
~~~

Ở đây newline là framing ở cấp record theo quy ước NDJSON. Nếu dòng cuối đang được nhận qua socket nhưng chưa có newline, ứng dụng phải biết giao thức có cho phép record cuối không kết thúc bằng newline hay không.

Không được coi một dòng JSON chưa nhận đủ là lỗi chỉ vì buffer hiện tại chưa chứa newline.

### 11.3. JSON array lớn

Một JSON array là một document duy nhất:

~~~json
[
  {"id":1},
  {"id":2},
  {"id":3}
]
~~~

Không thể mặc nhiên coi mỗi packet chứa một phần array là một document độc lập. Dùng parser liên tục hoặc non-blocking feeder để xử lý các phần tử theo thứ tự.

### 11.4. JSON Text Sequences

Một số giao thức dùng JSON Text Sequences theo RFC 7464, có record separator để phân định các JSON text. Cách xác định record boundary khác với một JSON array và khác với NDJSON. Parser phải được tích hợp với framing đúng của giao thức.

## 12. Cách thiết kế vòng nhận dữ liệu an toàn

Một pipeline nhận JSON chia chunk nên có trạng thái nguồn rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> Receiving
    Receiving --> Receiving: Có chunk mới
    Receiving --> Waiting: Parser cần thêm input
    Waiting --> Receiving: Chunk tiếp theo đến
    Receiving --> ParsingError: Cú pháp không thể hợp lệ
    Waiting --> Ended: Transport xác nhận EOF
    Receiving --> Ended: Transport xác nhận EOF
    Ended --> Complete: Parser hoàn tất document
    Ended --> Truncated: Parser báo unexpected EOF
    ParsingError --> [*]
    Complete --> [*]
    Truncated --> [*]
~~~

Một số nguyên tắc:
1. Giữ một parser cho cùng một document nếu dùng incremental parsing.
2. Cấp chunk theo đúng thứ tự.
3. Chỉ cấp chunk mới khi feeder báo đã sẵn sàng nhận input.
4. Xem NOT_AVAILABLE là cần thêm dữ liệu.
5. Chỉ gọi endOfInput() khi tầng transport xác nhận EOF.
6. Sau EOF, tiếp tục drain parser để phát hiện document hoàn chỉnh hay bị cắt.
7. Phân biệt JsonParseException với IOException/timeout.
8. Đặt timeout, giới hạn tổng kích thước và giới hạn độ sâu phù hợp để nguồn không thể giữ parser mở vô hạn.

Nếu ứng dụng nhận nhiều document trên cùng kết nối, phải dùng framing để biết khi nào một document kết thúc và khi nào document tiếp theo bắt đầu. Không thể suy ra ranh giới chỉ từ việc một lần read() trả về ít byte.

## 13. Một ví dụ kiểm thử ba trường hợp

Giả sử JSON mong đợi:

~~~json
{"name":"An","age":25}
~~~

Có thể mô phỏng ba trường hợp bằng parser blocking trên từng input hoàn chỉnh.

### 13.1. Input hợp lệ

~~~java
String valid = "{\"name\":\"An\",\"age\":25}";

Customer customer = mapper.readValue(valid, Customer.class);
~~~

Parser đọc đủ document và trả về object.

### 13.2. Input bị cắt ở EOF

~~~java
String truncated = "{\"name\":\"An\",\"age\":25";

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(truncated, Customer.class)
);
~~~

Input đã được xem là hoàn chỉnh vì String kết thúc. Parser không thể chờ thêm chunk nên báo lỗi EOF/parse.

### 13.3. Input sai cú pháp

~~~java
String malformed = "{\"name\":,\"age\":25}";

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(malformed, Customer.class)
);
~~~

Parser gặp dấu phẩy tại vị trí cần value. Lỗi có thể được phát hiện trước khi nguồn kết thúc.

Các test này chỉ chứng minh hành vi với ba input hoàn chỉnh. Để kiểm thử incremental parsing, cần cấp cùng JSON thành nhiều chunk cho một non-blocking parser, xác nhận parser có thể trả NOT_AVAILABLE giữa các chunk rồi hoàn tất sau khi nhận phần cuối.

## 14. Các nguyên tắc thực tế khi xử lý JSON lớn hoặc truyền theo chunk

- Không coi một lần read() trả ít byte hơn buffer là EOF.
- Với blocking parser, truyền một InputStream liên tục và để Jackson đọc thêm khi cần.
- Với non-blocking parser, duy trì cùng parser/feeder qua các chunk.
- JsonToken.NOT_AVAILABLE có nghĩa là cần thêm input, không phải JSON sai.
- Chỉ gọi feeder.endOfInput() khi transport xác nhận không còn dữ liệu.
- EOF thật khi object, array hoặc string chưa hoàn tất thường dẫn đến lỗi unexpected end-of-input.
- Lỗi như thiếu value sau dấu hai chấm hoặc escape sai là lỗi cú pháp, không thể khắc phục bằng cách chờ một chunk bất kỳ.
- Giữ byte UTF-8 nguyên vẹn qua ranh giới chunk; tránh decode độc lập từng chunk.
- Phân biệt lỗi parse, lỗi mapping, lỗi I/O và timeout.
- Dựa vào framing của giao thức để xác định một document, một record hay một sequence.
- Giới hạn kích thước, thời gian chờ và độ sâu dữ liệu để bảo vệ ứng dụng.
- Ghi log location, request ID và nguyên nhân; tránh ghi toàn bộ payload nhạy cảm.

Khi đọc JSON theo luồng, một phần input chưa hoàn chỉnh chỉ là trạng thái chờ nếu nguồn còn mở và có thể gửi tiếp. Lỗi cú pháp được xác định khi parser gặp cấu trúc không hợp lệ; lỗi EOF xuất hiện khi nguồn đã kết thúc mà document vẫn chưa hoàn tất. Với Jackson non-blocking parser, NOT_AVAILABLE là tín hiệu yêu cầu thêm dữ liệu, còn endOfInput() là xác nhận kết thúc thật sự. Phân biệt đúng hai tín hiệu này giúp ứng dụng xử lý JSON lớn và dữ liệu truyền theo chunk ổn định hơn.
