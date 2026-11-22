# Xử lý bảng mã, BOM và Unicode ở biên byte

JSON thường được nhắc đến như một định dạng văn bản, nhưng khi đi qua HTTP, message broker, file hoặc socket, dữ liệu thực tế được truyền dưới dạng **byte**. Jackson phải xử lý ranh giới giữa byte và ký tự trước khi có thể phân tích cú pháp JSON hoặc tạo JSON đầu ra. Nếu charset bị chọn sai, BOM không được xử lý đúng hoặc chuỗi Unicode bị biến đổi ở một tầng khác, kết quả có thể là lỗi parse, ký tự thay thế `�` hoặc văn bản mojibake dù cấu trúc JSON vẫn hợp lệ.

Để xử lý đúng, cần phân biệt ba việc: **giải mã byte thành ký tự**, **phân tích cú pháp và escape theo JSON**, và **mã hóa ký tự thành byte**. `ObjectMapper` có thể tự quản lý một phần việc này khi nhận `InputStream` hoặc ghi ra `OutputStream`. Khi ứng dụng truyền `Reader`, `Writer` hoặc `String`, trách nhiệm chọn charset thường đã thuộc về tầng gọi. Hiểu ranh giới này giúp tránh giải mã hai lần, dùng charset mặc định của máy và làm hỏng dữ liệu Unicode.

## 1. Ba lớp khác nhau: byte, ký tự và cú pháp JSON

Một luồng JSON đi từ hệ thống này sang hệ thống khác có thể được mô hình hóa như sau:

```text
Khi đọc:

byte[] / InputStream
        |
        v
Giải mã theo charset (UTF-8, UTF-16, ...)
        |
        v
Chuỗi ký tự Unicode
        |
        v
JSON parser: nhận diện object, array, string, number, boolean, null
        |
        v
Jackson databind: chuyển cấu trúc JSON thành kiểu Java


Khi ghi:

Object Java
        |
        v
Jackson databind: chọn serializer và thuộc tính
        |
        v
JSON generator: phát cú pháp JSON và escape ký tự cần thiết
        |
        v
Chuỗi ký tự JSON
        |
        v
Mã hóa theo charset
        |
        v
byte[] / OutputStream
```

Ba lớp này giải quyết ba nhóm vấn đề khác nhau:

| Lớp | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Encoding/decoding | Những byte này đại diện cho ký tự nào? | UTF-8 bị đọc nhầm thành Windows-1252. |
| JSON syntax | Chuỗi ký tự có phải JSON hợp lệ không? | Thiếu dấu nháy, dấu phẩy sai vị trí, escape không hợp lệ. |
| Databinding | Giá trị JSON được ánh xạ vào kiểu Java nào? | JSON object không khớp kiểu đích hoặc field không được nhận diện. |

Một lỗi ở lớp byte không nhất thiết là lỗi cú pháp JSON. Chẳng hạn, chuỗi tiếng Việt có thể bị giải mã sai nhưng vẫn tạo thành một JSON string hợp lệ. Ngược lại, byte có thể được giải mã đúng thành ký tự nhưng phần JSON lại thiếu dấu ngoặc. Vì vậy, khi điều tra lỗi, hãy xác định tầng nào đã tạo ra dữ liệu sai trước khi thay đổi cấu hình `ObjectMapper`.

## 2. Charset và quy tắc mã hóa JSON

Charset (bảng mã ký tự) quy định cách ánh xạ giữa chuỗi ký tự và dãy byte. Một ký tự có thể được biểu diễn bằng số byte khác nhau tùy charset.

Ví dụ, chữ `A` trong UTF-8 chỉ cần một byte `41` ở hệ thập lục phân. Một ký tự tiếng Việt như `ế` cần nhiều byte trong UTF-8. Nếu bên gửi mã hóa UTF-8 nhưng bên nhận giải mã bằng một charset khác, byte vẫn tồn tại nhưng ký tự được tạo ra không còn đúng.

### 2.1. UTF-8 là lựa chọn trao đổi JSON

Theo quy tắc của JSON được chuẩn hóa trong RFC 8259, JSON trao đổi giữa các hệ thống bên ngoài một môi trường đóng phải được mã hóa UTF-8. UTF-8 tương thích với ASCII ở vùng ký tự cơ bản, hỗ trợ toàn bộ Unicode và được sử dụng phổ biến trong HTTP API, message broker và file JSON.

Một số parser, trong đó có Jackson, có thể nhận diện các dạng Unicode khác như UTF-16 hoặc UTF-32 khi đọc từ nguồn byte. Khả năng đọc nhiều encoding không có nghĩa ứng dụng nên tùy tiện phát JSON bằng mọi encoding. Với giao tiếp liên hệ thống, hãy thống nhất UTF-8 để các nền tảng có thể trao đổi dữ liệu dự đoán được.

Các quy tắc thực hành:

- Mã hóa JSON gửi ra ngoài bằng UTF-8.
- Không dựa vào charset mặc định của hệ điều hành hoặc JVM.
- Nếu dữ liệu đầu vào có hợp đồng UTF-8, hãy xác định rõ cách xử lý byte sai encoding.
- Chỉ chuyển đổi encoding ở một tầng có trách nhiệm rõ ràng.
- Không giải mã byte thành `String` rồi lại coi `String` đó như byte gốc.

### 2.2. UTF-8, UTF-16 và UTF-32

Jackson core có cơ chế nhận diện encoding cho nguồn byte JSON. Các encoding Unicode thường được nhắc đến gồm:

| Encoding | Đặc điểm | Ví dụ biểu diễn BOM |
|---|---|---|
| UTF-8 | Ký tự được mã hóa bằng 1 đến 4 byte; tương thích ASCII. | `EF BB BF` |
| UTF-16BE | Đơn vị mã hóa 16 bit, byte cao đứng trước. | `FE FF` |
| UTF-16LE | Đơn vị mã hóa 16 bit, byte thấp đứng trước. | `FF FE` |
| UTF-32BE | Đơn vị mã hóa 32 bit, byte cao đứng trước. | `00 00 FE FF` |
| UTF-32LE | Đơn vị mã hóa 32 bit, byte thấp đứng trước. | `FF FE 00 00` |

BOM là một cách nhận biết encoding/byte order ở đầu luồng; một số encoding còn có thể được nhận diện qua mẫu byte đầu tiên ngay cả khi không có BOM. Không phải mọi charset cũ đều được Jackson tự nhận diện. Ví dụ Windows-1252, ISO-8859-1 hoặc một charset riêng của hệ thống cần được chuyển đổi rõ ràng trước khi đưa vào pipeline JSON.

### 2.3. Charset không được suy ra từ nội dung tiếng Việt

Không nên đoán charset chỉ vì dữ liệu trông giống tiếng Việt, tiếng Nhật hoặc một ngôn ngữ cụ thể. Cùng một chuỗi có thể được biểu diễn bằng nhiều encoding; một dãy byte sai charset đôi khi vẫn tạo thành các ký tự hợp lệ nhưng sai nghĩa.

Nguồn đáng tin cậy để xác định encoding là hợp đồng giao tiếp, cấu hình của hệ thống gửi, metadata của file hoặc giao thức đang sử dụng. Nếu nguồn không cung cấp thông tin đáng tin cậy, cần thống nhất lại hợp đồng hoặc xây dựng bước phát hiện/chuyển đổi riêng có kiểm soát; không nên thử nhiều charset ngẫu nhiên cho đến khi chuỗi “trông có vẻ đúng”.

## 3. Jackson nhận byte và nhận ký tự khác nhau như thế nào?

Điểm gọi API quyết định ai chịu trách nhiệm giải mã byte. Đây là khác biệt quan trọng nhất khi xử lý encoding.

| API đầu vào | Dữ liệu Jackson nhận | Ai quyết định charset? |
|---|---|---|
| `readValue(InputStream, Class)` | Byte từ stream | Jackson nhận diện encoding JSON ở biên byte. |
| `readValue(byte[], Class)` | Mảng byte | Jackson nhận diện encoding JSON ở biên byte. |
| `readValue(File, Class)` | Byte từ file | Jackson mở và xử lý nguồn byte. |
| `readValue(Reader, Class)` | Ký tự Java | Tầng tạo `Reader` đã quyết định charset. |
| `readValue(String, Class)` | Ký tự Java trong `String` | Tầng tạo `String` đã giải mã byte trước đó, nếu có. |

### 3.1. Truyền InputStream để Jackson xử lý biên byte

Khi nhận `InputStream`, Jackson core dùng cơ chế bootstrap để nhận diện encoding JSON từ BOM hoặc mẫu byte đầu vào. Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

try (InputStream input = Files.newInputStream(Path.of("request.json"))) {
    UserRequest request = mapper.readValue(input, UserRequest.class);
    handle(request);
}
```

Với `byte[]`, cách gọi tương tự:

```java
UserRequest request = mapper.readValue(payloadBytes, UserRequest.class);
```

Đây là lựa chọn tự nhiên khi ứng dụng nhận byte từ file, HTTP body hoặc message broker và muốn Jackson thực hiện việc nhận diện encoding JSON. Đối với JSON liên hệ thống, nguồn vẫn nên tuân theo UTF-8.

### 3.2. Truyền Reader nghĩa là charset đã được chọn trước

Khi nhận `Reader`, Jackson không còn nhìn thấy byte ban đầu. Ví dụ:

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("request.json"), StandardCharsets.UTF_8)) {
    UserRequest request = mapper.readValue(reader, UserRequest.class);
}
```

Ở đây `Files.newBufferedReader` đã giải mã byte bằng UTF-8. Jackson chỉ nhận ký tự từ `Reader` để phân tích JSON.

Nếu dùng sai charset ở bước tạo reader, Jackson không thể khôi phục byte gốc để đoán lại encoding. Cấu trúc JSON có thể vẫn parse được trong khi nội dung string đã bị biến dạng.

### 3.3. Truyền String nghĩa là dữ liệu đã ở dạng ký tự

```java
String json = "{\"name\":\"Tiếng Việt\"}";
UserRequest request = mapper.readValue(json, UserRequest.class);
```

`String` là chuỗi ký tự Java. Jackson không biết chuỗi đó ban đầu đến từ UTF-8, UTF-16 hay một nguồn khác. Nếu chuỗi được tạo từ byte sai charset, lỗi đã xảy ra trước khi gọi `readValue`.

Không nên viết:

```java
// Charset mặc định của nền tảng có thể khác nhau.
String json = new String(payloadBytes);
```

Nếu thật sự cần tạo `String` từ byte, hãy chỉ rõ charset:

```java
String json = new String(payloadBytes, StandardCharsets.UTF_8);
```

Tuy nhiên, nếu mục tiêu chỉ là deserialize JSON, truyền trực tiếp `payloadBytes` hoặc `InputStream` thường tránh được một lần tạo chuỗi trung gian.

## 4. BOM là gì và tại sao xuất hiện trong file JSON?

BOM (Byte Order Mark) là một dấu hiệu ở đầu luồng byte có thể dùng để nhận biết encoding và thứ tự byte. Trong UTF-16 và UTF-32, BOM có vai trò xác định byte order. Trong UTF-8, byte order không có ý nghĩa, nhưng một số công cụ vẫn thêm ba byte BOM như một chữ ký nhận diện file.

Các chuỗi byte BOM thường gặp:

| Encoding | Hex bytes | Ý nghĩa |
|---|---|---|
| UTF-8 | `EF BB BF` | Chữ ký UTF-8 tùy chọn. |
| UTF-16BE | `FE FF` | UTF-16 big-endian. |
| UTF-16LE | `FF FE` | UTF-16 little-endian. |
| UTF-32BE | `00 00 FE FF` | UTF-32 big-endian. |
| UTF-32LE | `FF FE 00 00` | UTF-32 little-endian. |

Một số editor trên Windows có thể lưu file UTF-8 kèm BOM. Một hệ thống xuất file có thể tạo UTF-16 với BOM. Nếu byte BOM đi vào một parser không xử lý nó ở tầng byte, ký tự BOM có thể bị xem như ký tự lạ trước dấu `{` hoặc `[`, dẫn tới lỗi parse.

### 4.1. BOM chỉ có ý nghĩa ở đầu luồng

BOM là chữ ký ở vị trí đầu dữ liệu. Không được xóa mọi ký tự `U+FEFF` xuất hiện trong nội dung JSON. Một ký tự `U+FEFF` nằm bên trong giá trị string là dữ liệu của trường đó và cần được giữ nếu hợp đồng cho phép.

Với một file hoặc JSON document, chỉ kiểm tra BOM ở byte đầu tiên. Với luồng chứa nhiều record, không chèn BOM trước từng record trừ khi giao thức riêng quy định rõ. BOM ở giữa một JSON document không phải cách khai báo lại charset.

### 4.2. Jackson xử lý BOM khi đọc từ nguồn byte

Khi Jackson nhận `InputStream` hoặc `byte[]`, cơ chế bootstrap có thể nhận diện BOM phổ biến và chọn encoding tương ứng. Với UTF-8 BOM, parser byte-source của Jackson xử lý chữ ký ở đầu luồng để nội dung JSON bắt đầu tại token thực tế.

```java
try (InputStream input = Files.newInputStream(path)) {
    // Để Jackson xử lý BOM/encoding ở biên byte.
    Config config = mapper.readValue(input, Config.class);
}
```

Hành vi chi tiết cần được kiểm chứng với phiên bản Jackson đang dùng và kiểu nguồn cụ thể. Nếu chuyển byte thành `Reader` trước, cơ chế nhận diện byte-level không còn được áp dụng vì Reader chỉ cung cấp ký tự.

### 4.3. BOM khi đã có Reader hoặc String

Nếu UTF-8 BOM được giải mã thành ký tự `U+FEFF` trước khi gọi Jackson, parser nhận ký tự đó chứ không nhận ba byte gốc. Không nên giả định mọi đường đọc `Reader` hoặc `String` sẽ tự loại bỏ ký tự này giống byte-source parser.

Nếu hợp đồng cho phép BOM ở đầu nội dung, có thể loại bỏ đúng một ký tự đầu tiên tại biên tạo `Reader`/`String`:

```java
String json = decodedText;
if (!json.isEmpty() && json.charAt(0) == '\uFEFF') {
    json = json.substring(1);
}

Config config = mapper.readValue(json, Config.class);
```

Đối với Reader, có thể dùng `PushbackReader` để chỉ kiểm tra ký tự đầu tiên:

```java
static Reader skipLeadingBom(Reader source) throws IOException {
    PushbackReader reader = new PushbackReader(source, 1);
    int first = reader.read();
    if (first != -1 && first != '\uFEFF') {
        reader.unread(first);
    }
    return reader;
}
```

Chỉ loại bỏ BOM khi đó là quy tắc của nguồn đầu vào. Nếu hợp đồng yêu cầu dữ liệu không có BOM, có thể từ chối thay vì âm thầm sửa. Không dùng `trim()` hoặc thay thế toàn bộ `U+FEFF`, vì thao tác đó có thể làm thay đổi nội dung string hợp lệ.

## 5. Đọc UTF-8 có kiểm soát

Nếu hệ thống quy định JSON đầu vào luôn là UTF-8, có hai cách triển khai phổ biến.

### 5.1. Để Jackson đọc trực tiếp InputStream

```java
try (InputStream input = Files.newInputStream(path)) {
    UserRequest request = mapper.readValue(input, UserRequest.class);
}
```

Đây là cách ngắn gọn và tận dụng cơ chế nhận diện encoding của Jackson. Tuy nhiên, nếu ứng dụng muốn **bắt buộc** UTF-8 thay vì chấp nhận các encoding Unicode mà parser nhận diện, hãy giải mã byte bằng một decoder UTF-8 tường minh.

### 5.2. Dùng CharsetDecoder ở chế độ strict

Một decoder có thể được cấu hình để báo lỗi khi gặp byte không hợp lệ thay vì thay thế bằng ký tự `U+FFFD`:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(inputStream, decoder)) {
    UserRequest request = mapper.readValue(reader, UserRequest.class);
}
```

`CodingErrorAction.REPORT` giúp ứng dụng nhận biết byte không tạo thành chuỗi UTF-8 hợp lệ. Nếu dùng decoder mặc định có hành vi thay thế, byte sai có thể biến thành `�`; nếu ký tự đó nằm trong JSON string, parser vẫn có thể đọc được JSON nhưng dữ liệu nghiệp vụ đã bị đổi.

Khi dùng cách này, ứng dụng chịu trách nhiệm xử lý BOM ở byte đầu vào trước khi tạo Reader. Nếu nguồn có thể mang UTF-8 BOM và hợp đồng cho phép, hãy loại bỏ đúng ba byte `EF BB BF` ở đầu stream trước khi decoder đọc. Nếu nguồn không cho phép BOM, hãy phát hiện và báo lỗi. Không chuyển sang `Reader` trước rồi mong Jackson tự nhận diện lại byte order.

### 5.3. Ví dụ loại bỏ UTF-8 BOM ở biên byte

Đoạn helper sau đọc tối đa ba byte đầu tiên. Nếu chúng là UTF-8 BOM, helper bỏ qua; nếu không, nó trả lại các byte đã đọc vào stream bằng `PushbackInputStream`:

```java
static InputStream skipUtf8Bom(InputStream source) throws IOException {
    PushbackInputStream input = new PushbackInputStream(source, 3);
    byte[] prefix = new byte[3];
    int count = 0;

    while (count < prefix.length) {
        int read = input.read(prefix, count, prefix.length - count);
        if (read < 0) {
            break;
        }
        count += read;
    }

    boolean hasBom = count == 3
        && (prefix[0] & 0xFF) == 0xEF
        && (prefix[1] & 0xFF) == 0xBB
        && (prefix[2] & 0xFF) == 0xBF;

    if (!hasBom) {
        input.unread(prefix, 0, count);
    }

    return input;
}
```

Sử dụng cùng decoder strict:

```java
InputStream raw = Files.newInputStream(path);
InputStream bomAware = skipUtf8Bom(raw);

CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(bomAware, decoder)) {
    UserRequest request = mapper.readValue(reader, UserRequest.class);
    handle(request);
}
```

Reader đóng stream bọc bên dưới khi hoàn tất. Nếu triển khai helper trong thư viện dùng chung, cần ghi rõ chính sách ownership và hành vi khi BOM không được phép. Ví dụ trên chỉ xử lý UTF-8 BOM; nó không phải bộ phát hiện hay chuyển đổi UTF-16/UTF-32.

## 6. Ghi JSON và chọn encoding đầu ra

Chiều ghi cũng có ranh giới byte/ký tự. Chọn overload phù hợp với đích cuối cùng.

### 6.1. Ghi trực tiếp ra OutputStream

```java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, response);
}
```

Khi ghi JSON ra `OutputStream`, Jackson sử dụng UTF-8 theo mặc định cho output byte của JSON. Có thể lấy byte trực tiếp:

```java
byte[] jsonBytes = mapper.writeValueAsBytes(response);
```

Đây là lựa chọn phù hợp cho HTTP body, message broker hoặc file JSON khi hợp đồng yêu cầu UTF-8. Jackson không tự thêm UTF-8 BOM vào JSON output theo mặc định; không nên tự nối ba byte BOM vào đầu payload để “đánh dấu UTF-8”.

### 6.2. Ghi ra Writer

Khi gọi `writeValue(Writer, value)`, Jackson ghi ký tự vào Writer. Charset được quyết định bởi Writer đã tạo:

```java
try (Writer writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    mapper.writeValue(writer, response);
}
```

Nếu Writer được tạo từ một charset khác, byte cuối cùng trên đĩa sẽ theo charset đó. Jackson không thể thay đổi charset của một Writer đã được cung cấp.

### 6.3. Ghi ra String rồi chuyển thành byte

```java
String json = mapper.writeValueAsString(response);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
```

`writeValueAsString` tạo một chuỗi Java, chưa phải byte. Chỉ khi gọi `getBytes` hoặc ghi qua Writer nối với stream thì encoding mới được áp dụng. Luôn chỉ rõ `StandardCharsets.UTF_8` nếu chuỗi sẽ được chuyển thành byte để trao đổi.

### 6.4. Không thêm BOM tùy tiện vào JSON output

UTF-8 không cần BOM để xác định byte order. JSON trao đổi giữa các hệ thống theo RFC 8259 dùng UTF-8 và generator không nên phát BOM. Một số phần mềm đọc file cũ có thể mong đợi BOM, nhưng đó là yêu cầu tương thích của hệ thống cụ thể; hãy xử lý ở adapter dành riêng cho hệ thống đó thay vì thay đổi output chung của API.

## 7. Unicode trong JSON: ký tự trực tiếp và escape `\\u`

JSON string có thể chứa ký tự Unicode trực tiếp hoặc biểu diễn một số ký tự bằng escape Unicode. Hai cách có thể biểu diễn cùng một giá trị ký tự.

```json
{
  "plain": "Tiếng Việt",
  "escaped": "Ti\u1ebfng Vi\u1ec7t"
}
```

Hai giá trị trong ví dụ biểu diễn cùng nội dung văn bản. Escape `\\uXXXX` là cú pháp của JSON, không phải tên charset và cũng không phải một lần mã hóa byte khác. Khi parser đọc JSON, escape được chuyển thành ký tự trong chuỗi Java.

Jackson generator mặc định có thể ghi nhiều ký tự Unicode trực tiếp ở dạng UTF-8 khi ghi ra byte. Một số cấu hình có thể yêu cầu escape các ký tự ngoài ASCII, chẳng hạn để tạo JSON chỉ gồm ký tự ASCII hoặc tương thích với hệ thống cũ. Dù chọn cách biểu diễn nào, nội dung ký tự vẫn là Unicode; khi ghi ra `OutputStream`, byte vẫn được mã hóa theo encoding của generator.

Không nên tự thay ký tự tiếng Việt bằng chuỗi `\\u...` bằng các thao tác replace. Jackson đã xử lý quoting, escaping dấu nháy, dấu gạch chéo ngược và ký tự điều khiển theo quy tắc JSON. Tự escape thủ công dễ dẫn đến double escaping, ví dụ một giá trị vốn là `\u` bị biến thành chuỗi literal khác với ý định.

## 8. Unicode và mô hình chuỗi trong Java

Java `String` biểu diễn văn bản theo mô hình UTF-16. Một `char` là một code unit 16 bit, không phải lúc nào cũng là một Unicode code point hoàn chỉnh.

### 8.1. Code unit, code point và byte length

Một ký tự trong vùng BMP thường dùng một code unit UTF-16. Ký tự ngoài BMP, ví dụ emoji, được biểu diễn bằng một cặp surrogate gồm high surrogate và low surrogate.

```java
String emoji = "😀";

int utf16Units = emoji.length();
int codePoints = emoji.codePointCount(0, emoji.length());
int utf8Bytes = emoji.getBytes(StandardCharsets.UTF_8).length;

System.out.println(utf16Units); // 2
System.out.println(codePoints); // 1
System.out.println(utf8Bytes);  // 4
```

Ba con số đo ba thứ khác nhau:

- `String.length()` đếm UTF-16 code unit.
- `codePointCount` đếm Unicode code point.
- Độ dài mảng byte sau `getBytes(UTF_8)` đếm byte UTF-8.

Không dùng `String.length()` để tính `Content-Length`, giới hạn dung lượng message hoặc kích thước file JSON. Các giới hạn ở tầng truyền tải phải tính trên byte sau khi mã hóa.

### 8.2. Surrogate pair trong JSON escape

JSON escape `\\uXXXX` biểu diễn một code unit 16 bit. Với ký tự ngoài BMP, cần một cặp escape tương ứng high surrogate và low surrogate:

```json
{
  "symbol": "\uD83D\uDE00"
}
```

Parser JSON chuyển cặp escape này thành cùng một ký tự emoji trong chuỗi Java. Nếu chỉ có một surrogate không ghép cặp, hành vi liên hệ thống có thể không nhất quán. Dữ liệu đầu vào và code tạo chuỗi nên tránh sinh chuỗi Unicode không hợp lệ.

### 8.3. Duyệt chuỗi theo code point

Nếu nghiệp vụ cần xử lý từng ký tự hiển thị ở mức code point, không nên duyệt `char` rồi giả định mỗi `char` là một ký tự hoàn chỉnh:

```java
String value = "A😀B";

for (int offset = 0; offset < value.length();) {
    int codePoint = value.codePointAt(offset);
    System.out.printf("U+%04X%n", codePoint);
    offset += Character.charCount(codePoint);
}
```

Đoạn code này duyệt code point, nhưng code point vẫn không đồng nghĩa với grapheme cluster (đơn vị ký tự người dùng nhìn thấy). Một chữ có dấu có thể gồm nhiều code point kết hợp. Nếu nghiệp vụ cần đếm ký tự hiển thị hoặc cắt văn bản theo grapheme, cần dùng cơ chế phân đoạn văn bản phù hợp thay vì `length()` hay `codePointCount()`.

## 9. Unicode normalization và văn bản tiếng Việt

Unicode cho phép một số ký tự hiển thị giống nhau được biểu diễn bằng nhiều chuỗi code point. Ví dụ, chữ `é` có thể được lưu dưới dạng ký tự dựng sẵn U+00E9 hoặc dạng `e` cộng dấu kết hợp U+0301. Tương tự, chữ `ế` có thể ở dạng dựng sẵn U+1EBF hoặc chuỗi `e` + dấu mũ kết hợp + dấu sắc kết hợp.

Hai chuỗi có thể hiển thị giống nhau nhưng so sánh bằng `String.equals` lại trả về `false` vì dãy code unit khác nhau.

```java
String composed = "ế";
String decomposed = "e\u0302\u0301";

System.out.println(composed.equals(decomposed)); // Có thể là false

String normalizedA = Normalizer.normalize(
    composed, Normalizer.Form.NFC);
String normalizedB = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC);

System.out.println(normalizedA.equals(normalizedB)); // true
```

Jackson đọc và ghi chuỗi Unicode theo nội dung được cung cấp; Jackson không tự động chuẩn hóa toàn bộ string sang NFC hoặc NFD. Nếu ứng dụng cần so sánh, tìm kiếm, khử trùng lặp hoặc tạo khóa từ văn bản Unicode, chính sách normalization phải được xác định ở tầng nghiệp vụ.

Không nên tự động normalize mọi dữ liệu chỉ vì JSON có Unicode. Việc thay đổi chuỗi code point có thể ảnh hưởng chữ ký số, HMAC, hash, dữ liệu kiểm toán hoặc hệ thống coi chuỗi gốc là dữ liệu chính xác. Nếu cần normalization, hãy quy định dạng chuẩn tại ranh giới phù hợp, áp dụng nhất quán trước khi so sánh hoặc lưu trữ và kiểm thử với dữ liệu thực tế.

## 10. Nhận diện và xử lý mojibake

Mojibake là văn bản bị hiển thị sai do byte được giải mã bằng charset không đúng. Ví dụ, byte UTF-8 của `Tiếng Việt` bị giải mã theo một charset kiểu Windows-1252 có thể tạo ra chuỗi giống `Tiáº¿ng Viá»‡t`.

```java
String original = "Tiếng Việt";
byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

// Minh họa lỗi: byte UTF-8 bị giải mã bằng charset khác.
String corrupted = new String(
    utf8, Charset.forName("windows-1252"));

System.out.println(corrupted);
```

Nếu chuỗi `corrupted` được đưa vào `ObjectMapper.writeValueAsString`, Jackson có thể tạo ra JSON hoàn toàn hợp lệ chứa nội dung đã sai. Jackson không thể biết chuỗi ban đầu từng được mã hóa bằng UTF-8 để tự phục hồi.

### 10.1. Cách khoanh vùng

Khi phát hiện mojibake, hãy kiểm tra theo thứ tự:

1. Xem byte gốc tại nguồn, ưu tiên biểu diễn hex cho một đoạn ngắn không chứa dữ liệu nhạy cảm.
2. Xác định charset mà bên gửi cam kết sử dụng.
3. Xác định tầng đầu tiên chuyển byte thành `String` hoặc `Reader`.
4. Kiểm tra charset được truyền rõ ràng tại tầng đó.
5. So sánh chuỗi ngay sau decoding với chuỗi trước khi serialize JSON.
6. Kiểm tra tiếp byte output và cách client giải mã response.

Nếu chuỗi đã sai trước khi gọi Jackson, sửa cấu hình ở tầng tạo chuỗi. Không cố sửa mojibake bằng các chuỗi replace như thay `Ã`, `áº` hoặc `â€™` trên mọi payload; những ký tự đó có thể là dữ liệu hợp lệ trong ngôn ngữ khác và phép thay thế có thể làm hỏng thêm dữ liệu.

### 10.2. Phân biệt byte sai với JSON escape sai

Hai tình huống thường bị nhầm:

- Byte UTF-8 đúng nhưng được giải mã bằng charset sai: ký tự Java đã sai trước khi parser chạy.
- Byte và ký tự được giải mã đúng nhưng JSON có escape sai: parser báo lỗi cú pháp hoặc tạo ra giá trị khác với dự kiến.

Nếu JSON chứa `\\u00E9`, đó là escape hợp lệ cho một code unit. Nếu chứa `\\uZZZZ`, escape không hợp lệ. Nếu JSON chứa ký tự `é` trực tiếp trong UTF-8, parser cũng có thể đọc bình thường. Không nên đổi encoding để sửa lỗi escape JSON.

## 11. Xử lý byte theo chunk và giới hạn kích thước

Trong HTTP hoặc socket, dữ liệu có thể được chia thành nhiều chunk. Một code point UTF-8 có thể trải qua ranh giới giữa hai chunk. Ví dụ, byte đầu của một ký tự có thể nằm ở cuối chunk trước và các byte tiếp theo nằm ở đầu chunk sau.

Không nên giải mã từng chunk độc lập bằng cách tạo `new String(chunk, UTF_8)` cho mỗi phần rồi nối lại. Nếu một ký tự nhiều byte bị chia giữa hai chunk, từng lần decoding có thể tạo ký tự thay thế hoặc làm mất byte. Hãy để một `InputStream` liên tục được parser đọc, hoặc dùng một `CharsetDecoder` có trạng thái được giữ qua các lần gọi `decode`.

```text
Một code point UTF-8:  [byte 1] [byte 2] [byte 3]

Chunk A:               [byte 1]
Chunk B:                         [byte 2] [byte 3]

Không giải mã A và B độc lập.
Giữ decoder/parser xuyên suốt luồng để ghép đúng chuỗi byte.
```

### 11.1. Đếm dung lượng theo byte

Nếu cần giới hạn body hoặc tính dung lượng message sau khi serialize, hãy tính trên byte:

```java
byte[] payload = mapper.writeValueAsBytes(response);
int contentLengthInBytes = payload.length;
```

Không dùng `response.toString().length()` hoặc `jsonString.length()` để thay thế kích thước byte. Với Unicode, một code point có thể chiếm nhiều byte UTF-8 và một số code point còn dùng nhiều UTF-16 code unit.

### 11.2. Không cắt payload tại vị trí byte tùy ý

Nếu cắt mảng byte UTF-8 ở giữa một chuỗi nhiều byte, phần còn lại có thể không còn là UTF-8 hợp lệ. Nếu cần giới hạn dữ liệu, hãy giới hạn theo hợp đồng ở tầng ứng dụng hoặc cắt theo ranh giới ký tự trước khi mã hóa. Với JSON lớn, ưu tiên streaming và giới hạn kích thước đầu vào thay vì cắt payload đã serialize.

## 12. HTTP và message broker ở biên byte

Jackson thường nằm sau một framework HTTP hoặc message converter. Cần xác định rõ tầng nào đang giải mã body.

### 12.1. HTTP request/response

Với JSON API, nội dung trao đổi nên là UTF-8. Media type phổ biến là `application/json`. Nếu framework nhận body dưới dạng `InputStream`, Jackson có thể xử lý byte; nếu framework đã chuyển body thành `String`, charset đã được áp dụng trước đó.

Tránh các chuỗi chuyển đổi không cần thiết:

```text
HTTP body bytes
    -> String với charset mặc định
    -> byte[] với charset khác
    -> Jackson
```

Thay vào đó, để message converter hoặc Jackson đọc body theo một quy tắc UTF-8 thống nhất. Khi trả response, dùng output byte UTF-8 hoặc Writer được cấu hình UTF-8. Đừng thêm BOM vào đầu HTTP JSON response.

### 12.2. Message broker

Một message broker thường truyền payload dạng byte. Producer và consumer cần thống nhất encoding trong schema hoặc metadata của message. Nếu producer ghi UTF-8, consumer nên đọc bằng cùng quy tắc. Nếu payload được đóng gói trong Avro, Protobuf hoặc một định dạng nhị phân khác, không được coi toàn bộ payload là JSON chỉ vì bên trong có trường văn bản.

Với message JSON, có thể truyền trực tiếp byte cho Jackson:

```java
Event event = mapper.readValue(message.getBody(), Event.class);
```

Nếu framework đã cung cấp `String` từ message, cần kiểm tra serializer/deserializer của framework đã chọn charset nào. Không decode lần nữa theo một charset khác.

## 13. Kiểm thử biên encoding và Unicode

Kiểm thử mapping thông thường chỉ dùng JSON ASCII sẽ không phát hiện nhiều lỗi encoding. Nên tạo các trường hợp riêng cho biên byte và ký tự.

### 13.1. Kiểm thử UTF-8 có và không có BOM

```java
byte[] json = "{\"name\":\"Tiếng Việt\"}"
    .getBytes(StandardCharsets.UTF_8);

User user = mapper.readValue(json, User.class);
assertEquals("Tiếng Việt", user.getName());
```

Nếu hợp đồng nguồn cho phép UTF-8 BOM, tạo payload có ba byte BOM ở đầu và xác nhận hành vi của đúng phiên bản Jackson đang dùng:

```java
byte[] bom = {(byte) 0xEF, (byte) 0xBB, (byte) 0xBF};
byte[] body = "{\"name\":\"Tiếng Việt\"}"
    .getBytes(StandardCharsets.UTF_8);

byte[] withBom = new byte[bom.length + body.length];
System.arraycopy(bom, 0, withBom, 0, bom.length);
System.arraycopy(body, 0, withBom, bom.length, body.length);

User user = mapper.readValue(withBom, User.class);
assertEquals("Tiếng Việt", user.getName());
```

Nếu hệ thống không chấp nhận BOM, test nên xác nhận ứng dụng từ chối payload đó theo hợp đồng thay vì âm thầm loại bỏ.

### 13.2. Kiểm thử ký tự ngoài BMP và combining mark

```java
String input = """
    {"text":"Tiếng Việt 😀 e\\u0302\\u0301"}
    """;

Message message = mapper.readValue(input, Message.class);
String output = mapper.writeValueAsString(message);
Message roundTrip = mapper.readValue(output, Message.class);

assertEquals(message.getText(), roundTrip.getText());
```

Test này xác nhận nội dung chuỗi được giữ qua vòng đọc/ghi, bao gồm emoji và chuỗi có dấu kết hợp. Nếu ứng dụng có quy tắc normalization, cần test riêng cả dạng NFC và NFD.

### 13.3. Kiểm thử byte output

```java
byte[] output = mapper.writeValueAsBytes(message);

// UTF-8 output của JSON bắt đầu bằng ký tự JSON đầu tiên,
// không có UTF-8 BOM theo mặc định.
assertFalse(output.length >= 3
    && (output[0] & 0xFF) == 0xEF
    && (output[1] & 0xFF) == 0xBB
    && (output[2] & 0xFF) == 0xBF);

String decoded = new String(output, StandardCharsets.UTF_8);
assertEquals(message.getText(),
    mapper.readValue(decoded, Message.class).getText());
```

Trong test thực tế, nên xác nhận encoding byte bằng các byte mong đợi cho một chuỗi có dấu và kiểm tra round-trip. Chỉ kiểm tra chuỗi sau `writeValueAsString` không chứng minh tầng output byte đã dùng UTF-8.

### 13.4. Kiểm thử byte UTF-8 lỗi

Nếu hợp đồng yêu cầu UTF-8 strict, tạo test với chuỗi byte không hợp lệ và xác nhận decoder strict báo lỗi. Ví dụ một byte continuation đứng riêng không tạo thành chuỗi UTF-8 hợp lệ:

```java
byte[] malformedUtf8 = {
    '{', '"', 'x', '"', ':', '"', (byte) 0x80, '"', '}'
};
```

Kết quả mong đợi phụ thuộc đường đọc: byte-source parser của Jackson có thể báo lỗi encoding; nếu ứng dụng tự dùng `CharsetDecoder` với `REPORT`, decoder phải báo lỗi malformed input. Không viết test chỉ chấp nhận ký tự `�` vì điều đó có thể che giấu dữ liệu hỏng.

## 14. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `Unexpected character` ngay trước `{` hoặc `[` | BOM được chuyển thành ký tự trong Reader/String hoặc byte đầu không đúng encoding. | Kiểm tra hex đầu vào; ưu tiên byte-source API hoặc xử lý BOM đúng ở biên tạo Reader. |
| Tiếng Việt thành `Tiáº¿ng...` | UTF-8 bị giải mã bằng charset khác. | Kiểm tra tầng tạo `String`/`Reader`; dùng UTF-8 rõ ràng. |
| Có ký tự `�` nhưng JSON vẫn parse | Decoder đã thay byte lỗi bằng replacement character. | Dùng decoder strict với `CodingErrorAction.REPORT`; kiểm tra byte gốc. |
| JSON parse được nhưng dữ liệu so sánh không khớp | NFC/NFD hoặc chuỗi code point khác nhau. | So sánh code point; áp dụng normalization theo hợp đồng nghiệp vụ nếu cần. |
| Nội dung đúng trong log nhưng sai khi gửi HTTP | Writer hoặc tầng HTTP dùng charset khác. | Kiểm tra byte response, message converter và encoding của Writer. |
| `Content-Length` không khớp | Đếm ký tự thay vì byte sau encoding. | Tính độ dài trên `byte[]` đã serialize hoặc để framework quản lý. |
| Ký tự lỗi khi đọc theo chunk | Mỗi chunk UTF-8 bị giải mã độc lập. | Dùng stream liên tục hoặc decoder giữ trạng thái giữa các chunk. |
| Emoji bị tách hoặc đếm sai | Duyệt `char`/dùng `String.length()` như số ký tự hiển thị. | Dùng code point hoặc grapheme segmentation tùy nghiệp vụ. |

## 15. Những nguyên tắc nên giữ ở biên byte

1. Thống nhất UTF-8 cho JSON trao đổi giữa các hệ thống.
2. Truyền `InputStream` hoặc `byte[]` cho Jackson khi muốn Jackson xử lý encoding JSON ở biên byte.
3. Khi dùng `Reader` hoặc `String`, tự chịu trách nhiệm giải mã byte bằng charset rõ ràng.
4. Không dùng charset mặc định của JVM để chuyển đổi byte và string.
5. Chỉ xử lý BOM ở đầu luồng; không xóa mọi `U+FEFF` trong nội dung.
6. Với UTF-8 strict, dùng decoder ở chế độ `REPORT` nếu tầng giải mã của ứng dụng phải phát hiện byte malformed.
7. Khi ghi JSON ra byte, dùng UTF-8 và không tự thêm BOM.
8. Phân biệt JSON escape `\\uXXXX` với encoding byte; hai khái niệm giải quyết hai tầng khác nhau.
9. Không giả định một `char` là một Unicode code point hoặc `String.length()` là số byte.
10. Jackson không tự normalization Unicode; chính sách NFC/NFD thuộc hợp đồng dữ liệu của ứng dụng.
11. Không decode từng chunk độc lập nếu một ký tự UTF-8 có thể bị chia qua ranh giới chunk.
12. Kiểm thử cả payload Unicode hợp lệ, BOM, byte malformed, output UTF-8 và round-trip.

Khi hiểu rõ nơi byte được chuyển thành ký tự và nơi ký tự được mã hóa trở lại, Jackson có thể xử lý JSON Unicode một cách ổn định. Hãy để mỗi tầng làm đúng một việc: giao thức xác định encoding, decoder chuyển byte thành ký tự, Jackson xử lý cú pháp và mapping JSON, còn generator/output layer phát byte theo encoding đã thống nhất. Cách phân chia này giúp lỗi encoding được phát hiện tại đúng ranh giới và tránh các bản sửa chuỗi tùy tiện làm mất dữ liệu.
