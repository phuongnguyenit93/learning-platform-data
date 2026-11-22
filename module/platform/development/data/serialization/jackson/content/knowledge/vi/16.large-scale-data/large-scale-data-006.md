# Kiểm tra dữ liệu nhiều dòng mà không tách bản ghi sai

Khi xử lý JSON quy mô lớn, một nguồn dữ liệu có thể chứa hàng nghìn hoặc hàng triệu bản ghi. Đọc toàn bộ file vào một String, sau đó parse thành List, có thể làm bộ nhớ tăng mạnh. Chia file thành từng dòng rồi parse từng dòng có vẻ đơn giản, nhưng chỉ đúng khi định dạng nguồn quy định rõ mỗi dòng là một JSON document độc lập.

JSON object có thể được trình bày trên nhiều dòng. Một JSON array có thể chứa nhiều object, mỗi object lại được format nhiều dòng. Nếu dùng ký tự xuống dòng làm ranh giới bản ghi cho mọi loại JSON, ứng dụng sẽ cắt một record thành nhiều mảnh và parse thất bại hoặc xử lý sai dữ liệu.

Nguyên tắc quan trọng là: **xác định framing của dữ liệu trước khi streaming; ranh giới bản ghi phải đến từ cấu trúc JSON hoặc giao thức truyền tải, không được suy đoán từ xuống dòng tùy ý.**

## 1. Bản ghi và dòng vật lý là hai khái niệm khác nhau

Một dòng vật lý là đoạn văn bản kết thúc bằng ký tự xuống dòng. Một bản ghi JSON là một JSON value hoàn chỉnh theo hợp đồng dữ liệu.

Hai khái niệm này chỉ trùng nhau khi định dạng quy định rõ điều đó, chẳng hạn JSON Lines.

Ví dụ một object được format nhiều dòng:

~~~json
{
  "id": 101,
  "name": "An",
  "status": "ACTIVE"
}
~~~

Đây là một JSON document, dù nó chiếm nhiều dòng vật lý.

Ngược lại, JSON Lines có thể chứa ba bản ghi trên ba dòng:

~~~json
{"id":101,"name":"An","status":"ACTIVE"}
{"id":102,"name":"Binh","status":"ACTIVE"}
{"id":103,"name":"Chi","status":"PENDING"}
~~~

Ở định dạng này, mỗi dòng không rỗng là một JSON value hoàn chỉnh. Việc đọc từng dòng rồi parse riêng là hợp lệ vì giao thức đã quy định ranh giới như vậy.

| Định dạng | Một record có thể nhiều dòng? | Có thể dùng readLine() làm ranh giới? |
|---|---:|---:|
| Một JSON object pretty-printed | Có | Không |
| Một JSON array chứa nhiều object | Có | Không |
| JSON Lines / NDJSON | Không, theo hợp đồng một JSON text mỗi dòng | Có |
| Nhiều JSON root value nối tiếp, phân cách bằng whitespace | Có thể | Không |
| JSON Text Sequences có Record Separator | Có | Không dùng newline đơn lẻ; dùng framing RS |
| Dữ liệu chia thành các network chunk | Không liên quan đến dòng | Không |

Trước khi viết code, cần biết producer gửi loại nào. Tên file có đuôi .json hoặc .jsonl không đủ để chứng minh framing nếu không có hợp đồng rõ ràng.

## 2. Vì sao không được tách JSON tùy ý theo newline?

JSON cho phép whitespace giữa các token. Whitespace có thể là dấu cách, tab, carriage return hoặc line feed. Vì vậy, một object hợp lệ có thể xuống dòng giữa các field:

~~~json
{
  "customer": {
    "id": 10,
    "name": "An"
  },
  "items": [
    {"code": "A01"},
    {"code": "B02"}
  ]
}
~~~

Nếu gọi readLine() và parse từng dòng, ứng dụng sẽ nhận những mảnh như:

~~~text
{
  "customer": {
    "id": 10,
~~~

Đây không phải JSON document hoàn chỉnh. Parser sẽ báo lỗi vì object chưa kết thúc.

Một newline giữa các token chỉ là whitespace định dạng. Nó không đánh dấu kết thúc một JSON value.

### 2.1. Newline bên trong chuỗi JSON

JSON string không được chứa ký tự điều khiển xuống dòng thô. Nếu nội dung cần biểu diễn newline, JSON dùng escape sequence như hai ký tự backslash và n:

~~~json
{
  "message": "First line\nSecond line"
}
~~~

Khi parse, giá trị Java có thể chứa ký tự xuống dòng thực tế. Nhưng trong JSON source, escape sequence vẫn nằm trong cùng một JSON string và không tạo ranh giới bản ghi.

Một parser streaming hiểu được trạng thái string, escape và cấu trúc lồng nhau. Việc tìm dấu xuống dòng bằng thao tác chuỗi không có đủ thông tin để xác định một JSON object đã hoàn tất hay chưa.

### 2.2. Byte chunk cũng không phải ranh giới record

Khi đọc từ socket, HTTP body hoặc file, một lần InputStream.read() có thể trả về một phần dữ liệu bất kỳ. Một chunk có thể kết thúc:

- Giữa tên field.
- Giữa một chuỗi.
- Giữa escape sequence.
- Giữa chữ số của một số.
- Giữa object hoặc array.
- Ngay trước hoặc sau dấu phẩy.

Không được giả định một lần read() tương ứng một dòng hoặc một JSON record. JsonParser được thiết kế để xử lý luồng byte/ký tự và giữ trạng thái qua các lần đọc.

## 3. Chọn framing trước khi chọn API Jackson

Có bốn kiểu nguồn phổ biến:

1. **Một JSON document:** một object hoặc array ở root. Dùng ObjectMapper hoặc JsonParser theo cấu trúc.
2. **JSON array lớn:** một root array chứa nhiều record. Dùng JsonParser để đọc từng phần tử.
3. **JSON Lines / NDJSON:** mỗi dòng là một JSON value hoàn chỉnh. Dùng BufferedReader hoặc một reader có giới hạn dòng, parse từng dòng.
4. **Nhiều root JSON value hoặc sequence có delimiter:** dùng MappingIterator hoặc parser theo giao thức framing đã quy định.

Sơ đồ lựa chọn:

~~~text
Nguồn dữ liệu JSON
        |
        v
Hợp đồng quy định record boundary?
        |
        +-- Một JSON array
        |       |
        |       v
        |   JsonParser đọc từng phần tử
        |
        +-- Một JSON object/document
        |       |
        |       v
        |   readValue/readTree hoặc parser
        |
        +-- Một JSON value mỗi dòng (JSONL)
        |       |
        |       v
        |   Đọc dòng rồi parse từng dòng
        |
        +-- Nhiều root value / sequence
                |
                v
            MappingIterator hoặc
            parser theo delimiter
~~~

Không nên chọn cách đọc chỉ dựa trên việc file có nhiều newline. Cần biết producer có cam kết một JSON value trên mỗi dòng hay không.

## 4. Đọc JSON array lớn bằng JsonParser

Đây là lựa chọn phù hợp khi file có một root array và mỗi phần tử là một record. Các phần tử có thể được pretty-print trên nhiều dòng; parser vẫn xác định được ranh giới nhờ token START_OBJECT và END_OBJECT.

Ví dụ file:

~~~json
[
  {
    "id": 101,
    "name": "An"
  },
  {
    "id": 102,
    "name": "Binh"
  },
  {
    "id": 103,
    "name": "Chi"
  }
]
~~~

Code đọc từng phần tử:

~~~java
public void importUsers(
    Path path,
    ObjectMapper mapper,
    Consumer<User> handler
) throws IOException {

    try (JsonParser parser = mapper.getFactory()
            .createParser(path.toFile())) {

        JsonToken first = parser.nextToken();

        if (first != JsonToken.START_ARRAY) {
            throw new IOException("Expected a root JSON array");
        }

        JsonToken token;
        while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
            if (token == null) {
                throw new IOException("Unexpected end of JSON array");
            }

            User user = mapper.readValue(parser, User.class);
            handler.accept(user);
        }

        if (parser.nextToken() != null) {
            throw new IOException("Unexpected content after root array");
        }
    }
}
~~~

Vòng lặp tiến parser đến token bắt đầu của phần tử kế tiếp. ObjectMapper đọc hết phần tử hiện tại thành User. Phần tử có thể trải qua nhiều dòng; parser không cần biết dòng nào kết thúc record.

### 4.1. Vì sao cách này tiết kiệm bộ nhớ?

Nếu đọc cả file thành List<User>, bộ nhớ tăng theo tổng số record. Với streaming, ứng dụng chỉ cần giữ:

- Buffer nội bộ của parser.
- Object User hiện tại.
- Dữ liệu mà handler đang cần.
- Các batch hoặc queue được ứng dụng chủ động giữ.

Nếu handler xử lý xong rồi giải phóng tham chiếu, ứng dụng không cần giữ toàn bộ danh sách.

Streaming không tự động làm bộ nhớ hằng số trong mọi trường hợp. Nếu handler thêm mọi User vào một List khác, hoặc queue không giới hạn, bộ nhớ vẫn tăng theo số record.

### 4.2. Kiểm tra root và trailing content

Một file có root array hợp lệ nên kết thúc sau END_ARRAY và whitespace. Nếu sau array còn một JSON object khác, đó là nội dung ngoài hợp đồng của một document đơn.

Đọc token tiếp theo sau END_ARRAY giúp phát hiện dữ liệu thừa. Tùy phiên bản và cấu hình, có thể dùng DeserializationFeature.FAIL_ON_TRAILING_TOKENS khi đọc qua databind; với parser thủ công, tự kiểm tra token còn lại giúp ý định rõ ràng.

### 4.3. Record lỗi ở giữa array

Nếu một phần tử không deserialize được, có thể dừng import và báo lỗi với vị trí parser. Không nên mặc định bỏ qua vài byte rồi tìm object tiếp theo vì parser có thể đang ở giữa một cấu trúc lồng nhau.

Nếu nghiệp vụ cần tiếp tục sau lỗi record, cần có cơ chế framing hoặc định dạng có thể xác định ranh giới record an toàn. JSON array đơn thuần không cung cấp delimiter độc lập cho từng object ngoài cấu trúc JSON; việc phục hồi sau cú pháp sai có thể không đáng tin cậy.

## 5. JSON Lines / NDJSON: khi nào đọc từng dòng là đúng?

JSON Lines (thường gọi JSONL hoặc NDJSON) là quy ước trong đó mỗi dòng chứa một JSON value hoàn chỉnh. Nhiều hệ thống log và pipeline dữ liệu dùng định dạng này vì dễ append, stream, grep và xử lý theo record.

Ví dụ:

~~~json
{"eventId":"e-1","type":"CREATED","userId":10}
{"eventId":"e-2","type":"UPDATED","userId":10}
{"eventId":"e-3","type":"DELETED","userId":11}
~~~

Trong định dạng này:

- Mỗi dòng chứa một JSON document độc lập.
- Một dòng không được chứa JSON document bị ngắt qua dòng kế tiếp.
- Line ending thường là LF; CRLF cũng cần được xử lý theo hợp đồng.
- Dòng cuối có thể kết thúc bằng EOF mà không có newline cuối.
- Blank line cần được quy định là bỏ qua hay báo lỗi.
- Mỗi dòng phải được parse độc lập.

Đây là trường hợp hợp lệ để dùng BufferedReader.readLine().

### 5.1. Ví dụ đọc JSON Lines

~~~java
public void importEvents(
    Path path,
    ObjectMapper mapper,
    Consumer<Event> handler
) throws IOException {

    ObjectReader reader = mapper.readerFor(Event.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    try (BufferedReader input = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {

        String line;
        long lineNumber = 0;

        while ((line = input.readLine()) != null) {
            lineNumber++;

            if (line.isBlank()) {
                continue; // Chỉ bỏ dòng rỗng nếu hợp đồng cho phép.
            }

            try {
                Event event = reader.readValue(line);
                handler.accept(event);
            } catch (JsonProcessingException ex) {
                throw new InvalidRecordException(
                    "Invalid JSONL record at line " + lineNumber,
                    ex
                );
            }
        }
    }
}
~~~

Mỗi dòng được đưa cho ObjectReader như một JSON document độc lập. FAIL_ON_TRAILING_TOKENS giúp phát hiện trường hợp một dòng chứa thêm token sau giá trị đầu tiên, thay vì âm thầm chỉ đọc phần đầu.

Nếu blank line không được phép, thay continue bằng lỗi có line number. Không nên tự chọn chính sách bỏ qua dòng rỗng nếu producer không cam kết điều đó.

### 5.2. Vì sao cần FAIL_ON_TRAILING_TOKENS?

Giả sử một dòng chứa:

~~~text
{"id":1} {"id":2}
~~~

Đây không phải một JSON Lines record đơn lẻ theo quy ước một JSON value mỗi dòng. Nếu reader chỉ đọc root value đầu tiên mà không kiểm tra trailing token, record thứ hai có thể bị bỏ qua âm thầm.

Bật FAIL_ON_TRAILING_TOKENS giúp đảm bảo một dòng chỉ chứa một JSON value hoàn chỉnh cùng whitespace được phép.

### 5.3. readLine() có giới hạn kích thước không?

BufferedReader.readLine() tạo String cho toàn bộ dòng. Nếu file không tin cậy có một dòng cực lớn, phương thức này có thể cấp phát một lượng bộ nhớ rất lớn trước khi parser được gọi.

Với dữ liệu do bên ngoài kiểm soát, cần giới hạn kích thước record. Có thể:

- Giới hạn tổng kích thước upload/request ở tầng HTTP hoặc storage.
- Dùng một line reader có giới hạn số ký tự.
- Từ chối record vượt giới hạn và ghi nhận vị trí.
- Chọn JSON array streaming nếu record framing phù hợp hơn.

Không nên chỉ kiểm tra line.length() sau readLine() rồi cho rằng đã bảo vệ được bộ nhớ, vì String lớn đã được tạo trước khi kiểm tra.

## 6. JSONL không phải JSON pretty-printed

Một object nhiều dòng:

~~~json
{
  "eventId": "e-1",
  "type": "CREATED"
}
~~~

không phải một record JSONL hợp lệ theo quy ước một JSON text trên mỗi dòng. Dòng đầu tiên chỉ có dấu mở object và các dòng tiếp theo là phần còn lại của cùng document.

Nếu producer muốn tạo JSONL, hãy serialize mỗi object thành một dòng compact:

~~~java
ObjectWriter compactWriter = mapper.writer();

try (BufferedWriter output = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {

    for (Event event : events) {
        output.write(compactWriter.writeValueAsString(event));
        output.newLine();
    }
}
~~~

Không bật INDENT_OUTPUT cho JSONL writer. Pretty-print tạo line break bên trong object và phá vỡ quy tắc một record mỗi dòng.

Nếu mỗi record cần nhiều dòng để dễ đọc, hãy chọn một framing khác như JSON array hoặc JSON Text Sequences thay vì gọi dữ liệu đó là JSONL.

## 7. Nhiều root JSON value nối tiếp

Một số nguồn chứa nhiều JSON value ở root, mỗi value được phân cách bằng whitespace:

~~~text
{"id":1,"name":"An"}
{"id":2,"name":"Binh"}
{"id":3,"name":"Chi"}
~~~

Trong ví dụ này, mỗi value tình cờ chiếm một dòng. Nhưng ranh giới được xác định bởi cú pháp JSON và whitespace giữa các root value, không phải bởi dòng vật lý. Một root object có thể được pretty-print trên nhiều dòng.

Jackson có thể đọc chuỗi root value bằng ObjectReader.readValues() và MappingIterator.

~~~java
public void importRootValues(
    InputStream input,
    ObjectMapper mapper,
    Consumer<User> handler
) throws IOException {

    ObjectReader reader = mapper.readerFor(User.class);

    try (MappingIterator<User> values = reader.readValues(input)) {
        while (values.hasNextValue()) {
            handler.accept(values.nextValue());
        }
    }
}
~~~

Cách này phù hợp khi nguồn thực sự là sequence các root JSON value và Jackson có thể xác định ranh giới qua parser. MappingIterator quản lý việc đọc từng value mà không cần tạo List<User>.

Hãy xác định rõ ownership của InputStream và MappingIterator. Khi iterator tạo parser từ InputStream và được đóng, parser/nguồn có thể được đóng theo hợp đồng của ObjectReader. Nếu caller cần giữ nguồn mở, hãy dùng parser do caller tạo, tắt AUTO_CLOSE_SOURCE trước khi tạo iterator và đóng parser theo một ownership duy nhất.

Không nên dùng cách đọc root values nối tiếp thay cho JSON array nếu hợp đồng đã định nghĩa một root array. Hai framing này khác nhau và cần được producer/consumer thống nhất.

## 8. JSON Text Sequences và Record Separator

Một định dạng khác là JSON Text Sequences theo RFC 7464. Mỗi JSON text được mở đầu bằng ký tự Record Separator (RS, byte 0x1E), và thường kết thúc bằng line feed.

Hình dung:

~~~text
RS {"id":1,"name":"An"} LF
RS {
     "id":2,
     "name":"Binh"
   } LF
RS {"id":3,"name":"Chi"} LF
~~~

Điểm quan trọng là RS là delimiter của record. JSON text có thể chứa newline để pretty-print; newline không phải delimiter chính.

Cách framing này hữu ích khi stream có thể chứa JSON text nhiều dòng và consumer cần tìm điểm bắt đầu record rõ ràng. RS là ký tự điều khiển không được xuất hiện thô bên trong JSON string hợp lệ; nếu cần biểu diễn ký tự tương ứng, JSON phải escape nó.

Jackson Core parser không tự biến mọi giao thức sequence thành một record API giống JSONL. Ứng dụng cần xử lý framing RS theo đặc tả, sau đó đưa từng JSON text hoàn chỉnh vào parser. Khi triển khai, cần kiểm tra trường hợp RS bị chia giữa các byte chunk, record cuối bị cắt, LF cuối bị thiếu và dữ liệu rác giữa các record.

Không tự thay delimiter của producer hoặc tự split theo newline nếu giao thức đã chọn RS.

## 9. Không dùng đếm dấu ngoặc để tách record

Một giải pháp tự viết thường gặp là đếm dấu { và } để biết khi nào object kết thúc. Cách này rất dễ sai.

Ví dụ:

~~~json
{
  "message": "Text contains { and } characters",
  "nested": {
    "id": 10
  }
}
~~~

Dấu ngoặc nhọn trong string không mở hoặc đóng object. Một bộ đếm đơn giản sẽ hiểu sai nếu không theo dõi trạng thái string và escape.

Còn phải xử lý:

- Dấu ngoặc trong string.
- Escape sequence trước dấu quote.
- Object lồng nhau.
- Array lồng nhau.
- Scalar root value.
- Whitespace giữa token.
- Unicode và byte encoding.
- JSON sai cú pháp hoặc bị cắt.

JsonParser đã thực hiện việc nhận diện token và trạng thái cú pháp. Hãy dùng parser thay vì tự viết bộ tách JSON dựa trên ký tự.

## 10. Đọc theo byte chunk không làm mất ranh giới JSON

Với network stream, một lần đọc có thể chỉ trả một phần dữ liệu. Không nên parse mỗi chunk thành JSON độc lập.

Ví dụ một record JSON có thể bị chia như sau:

~~~text
Chunk 1: {"eventId":"e-
Chunk 2: 100","status":"PRO
Chunk 3: CESSED"}
~~~

Ba chunk không phải ba record. Parser cần nhận dữ liệu liên tục và giữ trạng thái qua các lần đọc.

Nếu tự xây dựng buffer cho socket hoặc asynchronous channel, cần ghép các byte theo framing của giao thức trước khi parse. Với JSON array hoặc root-value sequence, dùng parser trực tiếp trên InputStream thường đơn giản hơn. Với JSONL, cần tích lũy cho đến line terminator nhưng vẫn phải áp dụng giới hạn kích thước dòng.

## 11. Xử lý lỗi record mà không làm mất đồng bộ

Chính sách lỗi phụ thuộc framing:

| Framing | Có thể xác định record tiếp theo sau lỗi không? | Chiến lược thường dùng |
|---|---|---|
| JSON array | Khó nếu cú pháp một phần tử làm hỏng cấu trúc | Dừng document hoặc quarantine toàn bộ file |
| JSON Lines | Có thể chuyển sang dòng kế tiếp sau lỗi parse của một dòng | Ghi nhận line number, quarantine dòng lỗi và tiếp tục nếu hợp đồng cho phép |
| Root values nối tiếp | Không phải lúc nào cũng an toàn sau lỗi cú pháp | Dừng sequence trừ khi framing cho phép đồng bộ lại |
| JSON Text Sequences | RS tiếp theo có thể tạo điểm đồng bộ | Bỏ record lỗi đến RS tiếp theo theo đặc tả |
| Network chunk không có framing | Không có ranh giới record rõ | Không thể tự phục hồi an toàn |

JSONL có lợi thế là mỗi dòng độc lập. Nếu một dòng sai cú pháp, consumer có thể ghi nhận dòng đó và thử dòng tiếp theo vì line ending là ranh giới hợp đồng.

Tuy nhiên, cần phân biệt lỗi record với lỗi nguồn: file bị cắt, encoding hỏng hoặc I/O exception có thể làm phần còn lại không đáng tin. Không nên tiếp tục vô điều kiện.

### 11.1. Quarantine record lỗi

Với pipeline import, có thể lưu record lỗi vào vùng quarantine cùng metadata:

- Tên file hoặc partition nguồn.
- Số dòng hoặc số thứ tự record.
- Lý do parse/validation thất bại.
- Raw line nếu được phép lưu.
- Thời điểm tiếp nhận.
- Version schema hoặc producer nếu có.

Raw payload có thể chứa dữ liệu cá nhân hoặc bí mật. Cần giới hạn quyền truy cập và thời gian lưu trữ; không ghi toàn bộ payload nhạy cảm vào log ứng dụng.

### 11.2. Phân biệt parse error và validation error

Một dòng JSON có thể parse thành Event nhưng không đạt nghiệp vụ, ví dụ quantity âm. Với JSONL, có thể ghi nhận validation error của record đó và tiếp tục dòng sau nếu hợp đồng import cho phép.

Nếu JSON sai cú pháp, Jackson không thể tạo DTO. Hai loại lỗi nên có mã lỗi và báo cáo khác nhau để producer biết cần sửa cú pháp hay dữ liệu.

## 12. Kiểm soát line length, record count và tổng kích thước

Streaming không đồng nghĩa không giới hạn tài nguyên. Một JSONL file có thể chứa một dòng dài hàng gigabyte; một JSON array có thể có hàng trăm triệu phần tử.

Cần đặt giới hạn:

- Tổng kích thước file hoặc HTTP body.
- Kích thước tối đa của một record.
- Số record trong một import.
- Độ sâu lồng nhau và độ dài string/number.
- Thời gian xử lý một record và toàn bộ job.
- Kích thước batch ghi database.
- Số record lỗi được phép trước khi dừng.

Với Jackson 2 có hỗ trợ, StreamReadConstraints có thể giới hạn độ sâu và kích thước một số token. Nhưng giới hạn token không thay thế giới hạn tổng request hoặc giới hạn record của giao thức.

Ví dụ cấu hình giới hạn parser:

~~~java
StreamReadConstraints constraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxStringLength(1_000_000)
        .maxNumberLength(1_000)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Các con số trên chỉ là ví dụ. Chọn giới hạn theo dữ liệu thực tế và phiên bản Jackson được quản lý trong dự án.

## 13. Đọc JSONL với giới hạn kích thước dòng

Nếu nguồn không tin cậy, BufferedReader.readLine() có thể cấp phát String rất lớn. Có thể dùng một hàm đọc dòng giới hạn số ký tự. Ví dụ sau nhận BufferedReader để dùng mark/reset khi xử lý CRLF:

~~~java
static String readBoundedLine(
    BufferedReader reader,
    int maxChars
) throws IOException {

    StringBuilder line = new StringBuilder();
    boolean readAny = false;

    while (true) {
        int value = reader.read();

        if (value == -1) {
            return readAny ? line.toString() : null;
        }

        readAny = true;

        if (value == '\n') {
            return line.toString();
        }

        if (value == '\r') {
            reader.mark(1);
            int next = reader.read();

            if (next != '\n' && next != -1) {
                reader.reset();
            }

            return line.toString();
        }

        if (line.length() >= maxChars) {
            throw new IOException("JSONL record exceeds the size limit");
        }

        line.append((char) value);
    }
}
~~~

Hàm trả null khi đã đến EOF mà không còn ký tự nào. Một dòng cuối không có newline vẫn được trả về bình thường. CRLF được xem là một line terminator.

Khi dùng hàm này, cần kiểm tra maxChars lớn hơn 0 và chọn giới hạn phù hợp. Đây là giới hạn theo số ký tự Java, không phải số byte UTF-8. Nếu hợp đồng giới hạn theo byte, cần đếm byte ở tầng đọc byte hoặc giới hạn kích thước nguồn trước khi decode.

Có thể dùng trong importer:

~~~java
try (BufferedReader input = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {

    String line;
    long lineNumber = 0;

    while ((line = readBoundedLine(input, 1_000_000)) != null) {
        lineNumber++;

        if (line.isBlank()) {
            continue;
        }

        Event event = reader.readValue(line);
        handler.accept(event);
    }
}
~~~

Nếu dòng vượt giới hạn, hàm ném IOException. Với một file import, thường nên dừng hoặc chuyển file sang trạng thái lỗi thay vì cố đọc phần còn lại của dòng như một record mới.

## 14. Thiết kế writer theo đúng framing

Producer phải ghi đúng định dạng mà consumer mong đợi.

### 14.1. Ghi JSON array

~~~java
try (JsonGenerator generator = mapper.getFactory()
        .createGenerator(output)) {

    generator.writeStartArray();

    for (User user : users) {
        mapper.writeValue(generator, user);
    }

    generator.writeEndArray();
}
~~~

Mỗi User là một phần tử của cùng root array. Consumer đọc bằng JsonParser và không cần dựa vào dòng vật lý.

Nếu output stream do caller sở hữu và cần giữ mở, tắt AUTO_CLOSE_TARGET trên generator trước khi đóng nó; caller sẽ đóng stream sau.

### 14.2. Ghi JSON Lines

~~~java
ObjectWriter writer = mapper.writer();

try (BufferedWriter output = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {

    for (Event event : events) {
        output.write(writer.writeValueAsString(event));
        output.newLine();
    }
}
~~~

Không bật pretty printing cho mỗi event. Mỗi JSON value phải nằm gọn trên một dòng theo hợp đồng.

### 14.3. Không trộn hai định dạng

Không ghi một phần file theo JSON array rồi thêm các object JSON độc lập ở cuối. Cũng không ghi JSONL nhưng thỉnh thoảng serialize một object pretty-printed nhiều dòng.

Consumer chỉ có thể tách record đúng nếu producer tuân thủ một framing duy nhất đã công bố.

## 15. Kiểm thử ranh giới bản ghi

Test nên chứng minh parser xử lý đúng từng loại framing và không cắt record theo dòng sai.

### 15.1. Pretty-printed JSON array vẫn là một document

~~~java
@Test
void readsMultilineObjectsInsideJsonArray() throws Exception {
    String json = """
        [
          {
            "id": 1,
            "name": "An"
          },
          {
            "id": 2,
            "name": "Binh"
          }
        ]
        """;

    List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
    );

    assertEquals(2, users.size());
    assertEquals("Binh", users.get(1).name());
}
~~~

Test này bảo vệ việc không dùng newline để chia object trong một array.

### 15.2. JSON Lines parse từng dòng

~~~java
@Test
void readsOneJsonValuePerLine() throws Exception {
    String input = """
        {"id":1,"name":"An"}
        {"id":2,"name":"Binh"}
        """;

    List<User> users = new ArrayList<>();

    try (BufferedReader reader = new BufferedReader(
            new StringReader(input))) {

        String line;
        while ((line = reader.readLine()) != null) {
            if (!line.isBlank()) {
                users.add(mapper.readerFor(User.class)
                    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                    .readValue(line));
            }
        }
    }

    assertEquals(2, users.size());
}
~~~

### 15.3. Dòng có thêm root value phải bị từ chối

~~~java
@Test
void rejectsTwoJsonValuesOnOneJsonlLine() {
    ObjectReader reader = mapper.readerFor(User.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    assertThrows(JsonProcessingException.class, () ->
        reader.readValue("{\"id\":1} {\"id\":2}")
    );
}
~~~

### 15.4. Dòng cuối không có newline vẫn được đọc

Test với StringReader hoặc file fixture không có newline ở cuối để bảo đảm record cuối không bị bỏ sót.

### 15.5. Test lỗi và giới hạn

Nên bổ sung trường hợp:

- CRLF và LF.
- Dòng rỗng theo chính sách.
- JSON string có escape sequence newline.
- Một record pretty-printed nhiều dòng trong array.
- JSONL có một dòng sai cú pháp.
- Dòng vượt giới hạn kích thước.
- File bị cắt giữa một record.
- Array kết thúc thiếu dấu ngoặc.
- Nội dung thừa sau root document.
- Handler ném exception và parser/stream vẫn được đóng.

## 16. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Parse từng dòng của JSON pretty-printed | Nhầm newline với record boundary | Dùng JsonParser theo cấu trúc JSON |
| Cắt object theo dấu ngoặc bằng String split | Không xử lý string, escape và nesting | Dùng parser token |
| Coi một lần InputStream.read() là một record | Network chunk không có framing | Dùng parser hoặc giao thức delimiter |
| JSONL có object nhiều dòng | Producer vi phạm one-value-per-line | Ghi compact JSONL hoặc đổi framing |
| Bỏ sót record cuối | Giả định file luôn có newline cuối | Xử lý dòng cuối tại EOF |
| Bỏ qua JSON value thứ hai trên cùng dòng | Không kiểm tra trailing tokens | Bật FAIL_ON_TRAILING_TOKENS |
| Một dòng cực lớn làm tăng RAM | readLine() không giới hạn kích thước | Bounded line reader và giới hạn upload |
| Tiếp tục sau lỗi JSON array bằng cách tìm dấu } | Không có điểm đồng bộ an toàn | Dừng document hoặc dùng framing riêng |
| Pretty-print JSONL | Newline trong record phá framing | Tắt INDENT_OUTPUT |
| Gộp nhiều định dạng trong một file | Consumer không biết framing | Chọn và công bố một định dạng |

## 17. Quy trình lựa chọn và xử lý dữ liệu nhiều dòng

1. Xác định producer đang gửi JSON document, JSON array, JSONL hay sequence có delimiter.
2. Xác định ranh giới record theo hợp đồng, không theo cách file được hiển thị trong editor.
3. Nếu là JSON array, dùng JsonParser đọc từng phần tử.
4. Nếu là JSONL, đọc từng dòng với giới hạn kích thước và parse từng dòng.
5. Nếu là nhiều root value, dùng ObjectReader/MappingIterator hoặc parser theo framing đã công bố.
6. Nếu dùng Record Separator, xử lý RS theo đặc tả trước khi parse từng JSON text.
7. Kiểm tra trailing content, EOF và record bị cắt.
8. Quy định xử lý blank line, malformed record, retry và quarantine.
9. Đặt giới hạn file, record, token, số lượng và thời gian xử lý.
10. Viết test chứng minh record nhiều dòng không bị tách sai và record một dòng không bị gộp với record kế tiếp.

## 18. Nguyên tắc nên giữ

- Newline chỉ là ranh giới record khi định dạng cam kết điều đó, chẳng hạn JSON Lines.
- JSON object và array có thể trải qua nhiều dòng; dùng cấu trúc token để nhận biết điểm kết thúc.
- Network read chunk không phải record.
- Không tự tách JSON bằng đếm dấu ngoặc hoặc String.split().
- Dùng JsonParser cho JSON array lớn và MappingIterator cho sequence root value phù hợp.
- Với JSONL, parse từng dòng hoàn chỉnh và kiểm tra trailing token.
- Giới hạn kích thước dòng trước khi cấp phát String lớn.
- Quy định rõ blank line, CRLF, dòng cuối không có newline và lỗi record.
- Producer và consumer phải thống nhất cùng một framing.
- Test cả pretty-printed JSON, JSONL, record lỗi và dữ liệu bị cắt.

Muốn xử lý dữ liệu nhiều dòng an toàn, trước hết phải xác định bản ghi được phân tách bằng cấu trúc JSON hay bằng quy ước truyền tải. JsonParser hiểu cấu trúc object/array và có thể đọc từng phần tử dù mỗi record trải qua nhiều dòng. BufferedReader.readLine() chỉ phù hợp khi producer cam kết JSON Lines, mỗi dòng là một JSON value hoàn chỉnh. Giữ ranh giới này rõ ràng giúp pipeline streaming tiết kiệm bộ nhớ mà không làm hỏng record hoặc âm thầm bỏ dữ liệu.

