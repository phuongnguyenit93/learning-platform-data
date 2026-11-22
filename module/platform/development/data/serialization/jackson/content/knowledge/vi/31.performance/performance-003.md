# Lựa chọn byte array, String, tree hoặc stream theo nhu cầu

Jackson có nhiều cách đọc và ghi cùng một dữ liệu: nhận toàn bộ JSON dưới dạng byte array, giữ JSON trong một String, chuyển nội dung thành JsonNode để thao tác, hoặc đọc/ghi qua stream. Các cách này khác nhau về bộ nhớ, khả năng xử lý dữ liệu lớn, quyền sở hữu tài nguyên và mức độ linh hoạt.

Không có lựa chọn nào tốt nhất trong mọi tình huống. Nếu payload nhỏ và cần trả byte trực tiếp cho HTTP client, byte array có thể đơn giản. Nếu cần hiển thị hoặc xử lý JSON text, String thuận tiện. Nếu cần kiểm tra và sửa field động, Tree Model phù hợp. Nếu dữ liệu lớn hoặc cần xử lý từng record, Streaming API giúp tránh giữ toàn bộ tài liệu trong bộ nhớ.

Điểm quan trọng là phân biệt **stream làm nguồn/đích I/O** với **streaming xử lý từng token**. Gọi readValue(InputStream, List.class) vẫn có thể tạo toàn bộ List trong RAM. Muốn giới hạn bộ nhớ theo từng record, cần dùng JsonParser/JsonGenerator hoặc một cơ chế đọc sequence phù hợp.

## 1. Bốn cách biểu diễn và xử lý dữ liệu

| Cách | Kiểu dữ liệu chính | API tiêu biểu | Mục tiêu |
|---|---|---|---|
| Byte array | byte[] | writeValueAsBytes(), readValue(byte[]) | Giữ toàn bộ payload ở dạng bytes |
| String | String | writeValueAsString(), readValue(String) | Giữ toàn bộ JSON text trong bộ nhớ |
| Tree | JsonNode, ObjectNode, ArrayNode | readTree(), valueToTree(), treeToValue() | Kiểm tra và biến đổi cấu trúc JSON |
| Stream | InputStream, OutputStream, JsonParser, JsonGenerator | readValue(InputStream), writeValue(OutputStream), Streaming API | Đọc/ghi tuần tự, có thể xử lý dữ liệu lớn |

Có hai mức stream cần phân biệt:

- **I/O stream:** dữ liệu được đọc từ InputStream hoặc ghi vào OutputStream thay vì phải có sẵn một byte[] hoặc String.
- **Token streaming:** ứng dụng điều khiển JsonParser/JsonGenerator và xử lý từng token hoặc từng phần tử, không cần tạo toàn bộ cây hay collection.

ObjectMapper.readValue(InputStream, MyLargeDto.class) dùng parser đọc từ stream nhưng vẫn tạo toàn bộ MyLargeDto. Nếu DTO có một List rất lớn, toàn bộ List vẫn được giữ trong bộ nhớ. I/O streaming tự nó không bảo đảm memory usage thấp.

## 2. Quy tắc chọn nhanh

~~~text
Cần gì sau khi serialize/đọc?
        |
        +-- Cần toàn bộ bytes để gửi, ký, hash hoặc lưu?
        |       -> byte[]
        |
        +-- Cần JSON text để hiển thị hoặc xử lý text?
        |       -> String
        |
        +-- Cần tìm, sửa, thêm, xóa field động?
        |       -> JsonNode tree
        |
        +-- Payload lớn hoặc cần xử lý từng phần tử?
                -> InputStream/OutputStream
                   + JsonParser/JsonGenerator
~~~

Một vài ví dụ:

- Controller cần trả payload JSON nhỏ đã serialize: byte[] hoặc để framework serialize object trực tiếp.
- Test cần so sánh JSON hoặc tạo thông báo lỗi: String hoặc JsonNode.
- Adapter cần thêm một metadata field vào payload không có DTO cố định: ObjectNode.
- Import hàng triệu record từ file JSON array: JsonParser và xử lý từng record.
- Export dữ liệu lớn sang file hoặc HTTP response: JsonGenerator hoặc writer trên OutputStream.
- Ký số trên đúng bytes được gửi: byte[] có thể cần thiết, hoặc dùng streaming digest/signature nếu giao thức hỗ trợ.

## 3. Dùng byte array khi cần toàn bộ payload dạng bytes

ObjectMapper cung cấp writeValueAsBytes() để serialize một Java value thành byte array:

~~~java
ObjectMapper mapper = new ObjectMapper();

byte[] payload = mapper.writeValueAsBytes(order);
~~~

Đọc lại:

~~~java
Order restored = mapper.readValue(payload, Order.class);
~~~

Với JSON mapper mặc định, bytes được tạo theo encoding UTF-8. Đây là lựa chọn tự nhiên khi API tiếp theo nhận byte[], ví dụ HTTP body publisher, message broker hoặc hàm tính hash.

### 3.1. Khi byte[] phù hợp

Dùng byte array khi:

- Payload nhỏ hoặc vừa và cần có toàn bộ nội dung trước khi gửi.
- Thư viện đích yêu cầu byte[].
- Cần tính chữ ký hoặc hash trên toàn bộ payload đã serialize.
- Cần lưu payload vào cache hoặc message envelope dưới dạng bytes.
- Cần đọc lại nhiều lần từ một buffer đã có.
- Cần đo chính xác số byte của payload trước khi gửi.

Ví dụ:

~~~java
byte[] payload = mapper.writeValueAsBytes(event);

String digest = sha256Hex(payload);

messageBroker.send("order-events", payload);
~~~

Nếu chữ ký/hash phải khớp chính xác payload trên wire, hãy ký đúng byte sequence sẽ được gửi. Serialize lại object lần thứ hai có thể tạo bytes khác nếu thứ tự property, timestamp, format hoặc cấu hình generator thay đổi.

### 3.2. Chi phí bộ nhớ của byte[]

writeValueAsBytes() phải tạo toàn bộ kết quả trước khi trả về. Với payload lớn, ứng dụng cần giữ byte array đó trong RAM cho đến khi hoàn tất việc gửi hoặc xử lý.

Trong quá trình tạo, thư viện có thể dùng buffer nội bộ rồi tạo kết quả cuối. Không nên giả định chỉ có đúng một bản sao payload trong bộ nhớ. Khi gọi thêm các API tạo String hoặc copy buffer, số vùng nhớ có thể tăng.

Nếu ứng dụng đang có sẵn byte[] đầu vào, readValue(byte[], Type.class) tránh phải tạo String trung gian:

~~~java
Order order = mapper.readValue(payloadBytes, Order.class);
~~~

Không nên chuyển bytes thành String rồi mới đọc nếu thực sự không cần text:

~~~java
String json = new String(payloadBytes, StandardCharsets.UTF_8);
Order order = mapper.readValue(json, Order.class);
~~~

Việc chuyển bytes thành String tạo thêm đối tượng và phải chọn charset đúng.

### 3.3. byte[] payload khác byte[] property trong DTO

Hai tình huống sau không giống nhau:

~~~java
byte[] jsonDocument = mapper.writeValueAsBytes(order);
~~~

Đây là toàn bộ tài liệu JSON đã serialize thành UTF-8 bytes.

Còn:

~~~java
public record Attachment(String name, byte[] content) {}
~~~

Ở đây byte[] là một property bên trong object. Với JSON serializer mặc định của Jackson, byte[] property thường được biểu diễn dưới dạng Base64 string trong JSON:

~~~json
{
  "name": "sample.bin",
  "content": "AQIDBAU="
}
~~~

Không nhầm byte[] của tài liệu JSON với byte[] của dữ liệu nhị phân bên trong DTO. Các binary dataformat như CBOR có thể biểu diễn byte string theo cách riêng.

## 4. Dùng String khi cần JSON text

writeValueAsString() serialize object thành một Java String:

~~~java
String json = mapper.writeValueAsString(order);
~~~

Đọc:

~~~java
Order restored = mapper.readValue(json, Order.class);
~~~

String hữu ích khi cần:

- Ghi JSON vào log có kiểm soát.
- Hiển thị payload trong công cụ quản trị.
- Gửi JSON qua API chỉ nhận text.
- Ghép hoặc lưu nội dung trong hệ thống text-based.
- Tạo fixture hoặc assertion trong test.
- Dùng thư viện khác có API nhận String.

### 4.1. String không phải lựa chọn tốt chỉ vì JSON là văn bản

String chứa toàn bộ JSON text trong bộ nhớ. Nếu sau đó cần gửi qua network dưới dạng UTF-8 bytes, ứng dụng còn phải mã hóa String thành bytes.

~~~java
String json = mapper.writeValueAsString(order);

byte[] body = json.getBytes(StandardCharsets.UTF_8);
~~~

Đoạn trên hợp lý nếu ứng dụng cần String ở giữa. Nếu chỉ cần HTTP body bytes, dùng writeValueAsBytes() hoặc ghi trực tiếp vào OutputStream sẽ tránh bước String trung gian.

Không dùng getBytes() mà không chỉ định charset. Charset mặc định của môi trường có thể khác nhau. Với JSON qua network, UTF-8 thường là lựa chọn chuẩn và được hỗ trợ rộng rãi.

### 4.2. Không dùng String cho CBOR hoặc Smile

CBOR và Smile là định dạng nhị phân. Không chuyển payload của chúng thành String UTF-8:

~~~java
byte[] cbor = cborMapper.writeValueAsBytes(order);
~~~

Giữ bytes và truyền theo media type tương ứng. Nếu cần debug, hãy parse bytes về object hoặc JsonNode rồi tạo JSON text riêng để quan sát. Bản text debug không phải bytes gốc của payload nhị phân.

### 4.3. String và dữ liệu nhạy cảm

JSON String dễ bị ghi log hoặc đưa vào exception message. Trước khi log, cần redact token, password, dữ liệu cá nhân và field nội bộ. Không ghi toàn bộ payload chỉ vì đã có sẵn String.

Nếu chỉ cần chẩn đoán, log correlation ID, kích thước, loại message và một số field không nhạy cảm. Việc tạo String không làm dữ liệu an toàn hơn.

## 5. Dùng JsonNode tree khi cần thao tác cấu trúc

Tree Model biểu diễn JSON bằng các node:

- ObjectNode: object có property.
- ArrayNode: array có phần tử.
- TextNode: string.
- NumericNode: number.
- BooleanNode: boolean.
- NullNode: JSON null.

Đọc JSON text thành tree:

~~~java
JsonNode root = mapper.readTree(json);
~~~

Chuyển Java object thành tree:

~~~java
JsonNode root = mapper.valueToTree(order);
~~~

Nếu biết root là object:

~~~java
ObjectNode object = (ObjectNode) root;
object.put("source", "checkout");
object.put("schemaVersion", 2);
~~~

Ghi lại JSON:

~~~java
String updatedJson = mapper.writeValueAsString(object);
~~~

Tree phù hợp khi cấu trúc cần kiểm tra hoặc biến đổi trước khi bind hoặc gửi tiếp.

### 5.1. Các trường hợp nên dùng tree

- Thêm metadata vào payload động.
- Kiểm tra field có tồn tại hay không.
- Xử lý JSON có schema thay đổi theo message type.
- Chọn subtype dựa trên discriminator trước khi bind.
- Loại bỏ field không được chuyển tiếp.
- Biến đổi cấu trúc từ API này sang API khác.
- So sánh expected/actual JSON trong test.
- Đọc một phần dữ liệu nhưng vẫn cần truy cập ngẫu nhiên nhiều field.

Ví dụ thêm metadata:

~~~java
ObjectNode payload = mapper.valueToTree(order);

payload.put("source", "order-service");
payload.put("correlationId", correlationId);
payload.remove("internalNote");
~~~

### 5.2. Tree giữ toàn bộ cấu trúc trong bộ nhớ

readTree() tạo node cho tài liệu. Với JSON rất lớn, toàn bộ cây và các node con sẽ cùng tồn tại trong RAM.

Tree có thể dùng nhiều bộ nhớ hơn kích thước JSON text vì mỗi node là object Java có metadata và tham chiếu. Một tài liệu JSON vài chục MB có thể tạo tree lớn hơn đáng kể. Mức tăng cụ thể phụ thuộc số property, số node, string length và JVM.

Nếu chỉ cần đọc một field rồi bỏ qua phần còn lại, tree thường là quá nhiều. Dùng parser streaming và skipChildren() cho nhánh không cần xử lý.

### 5.3. Tree không giữ nguyên văn bản nguồn

Sau khi parse JSON thành JsonNode, các chi tiết như whitespace, indentation, cách escape tương đương hoặc thứ tự định dạng ban đầu không phải là mục tiêu bảo toàn của Tree Model. Khi serialize lại, Jackson tạo JSON mới theo cấu hình mapper.

Nếu cần ký số trên đúng bytes gốc, lưu bytes gốc riêng. Không parse thành tree rồi ghi lại và kỳ vọng chữ ký vẫn hợp lệ.

### 5.4. Tree và convertValue()

Nếu chỉ cần chuyển object này thành một DTO Java khác, dùng convertValue() hoặc treeToValue() theo mục đích. Không tạo tree rồi chuyển ngay sang kiểu khác nếu không cần thao tác trên tree:

~~~java
OrderView view = mapper.convertValue(order, OrderView.class);
~~~

Dùng valueToTree() khi đích thực sự là JsonNode. Dùng readTree() khi nguồn là JSON text/bytes/stream. Dùng treeToValue() khi nguồn đã là JsonNode và cần Java type.

## 6. Dùng InputStream và OutputStream cho I/O tuần tự

ObjectMapper có thể đọc trực tiếp từ InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Order order = mapper.readValue(input, Order.class);
}
~~~

Và ghi trực tiếp vào OutputStream:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, order);
}
~~~

Cách này tránh tạo một byte[] hoặc String trung gian do ứng dụng quản lý. Nó phù hợp với file, HTTP body, message broker và các nguồn dữ liệu I/O khác.

### 6.1. I/O stream vẫn có thể tạo object graph đầy đủ

Đây là điểm dễ nhầm:

~~~java
List<Order> orders = mapper.readValue(
    input,
    new TypeReference<List<Order>>() {}
);
~~~

Input được đọc từ stream, nhưng kết quả là một List chứa tất cả Order. Nếu file có hàng triệu order, toàn bộ list vẫn nằm trong RAM.

Tương tự:

~~~java
JsonNode tree = mapper.readTree(input);
~~~

Parser đọc từ stream nhưng kết quả là toàn bộ tree.

Stream ở đây chỉ thay đổi cách bytes đi vào/ra. Muốn xử lý theo từng phần tử, cần token streaming hoặc API sequence phù hợp.

### 6.2. Khi InputStream/OutputStream phù hợp

- Đọc file lớn.
- Ghi response trực tiếp vào HTTP output.
- Đọc message từ broker.
- Ghi payload vào file hoặc object storage.
- Kết nối với compression stream.
- Không cần giữ JSON text/bytes hoàn chỉnh trong một biến.
- Muốn pipeline dữ liệu qua nhiều thành phần.

Ví dụ đọc file nén:

~~~java
try (InputStream file = Files.newInputStream(path);
     InputStream input = new GZIPInputStream(file)) {

    ImportManifest manifest =
        mapper.readValue(input, ImportManifest.class);
}
~~~

Ở đây Jackson đọc từ stream đã giải nén. Cần giới hạn cả kích thước file nén lẫn kích thước sau giải nén để tránh decompression bomb.

## 7. Token streaming với JsonParser

Nếu cần xử lý dữ liệu lớn mà không tạo toàn bộ collection hoặc tree, dùng JsonParser trực tiếp.

Ví dụ đọc một JSON array chứa nhiều record:

~~~json
[
  {"id": 1, "status": "READY"},
  {"id": 2, "status": "READY"},
  {"id": 3, "status": "DONE"}
]
~~~

Có thể đọc từng object:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new JsonParseException(parser, "Expected a JSON array");
    }

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
        if (token == null) {
            throw new JsonParseException(parser, "Unexpected end of input");
        }

        OrderRecord record = mapper.readValue(parser, OrderRecord.class);
        process(record);
    }
}
~~~

Parser đọc đến đầu mỗi phần tử. readValue(parser, OrderRecord.class) bind một object hiện tại; sau khi xử lý, vòng lặp chuyển sang phần tử tiếp theo.

Bộ nhớ có thể được giới hạn gần với parser buffers và một OrderRecord đang xử lý, cộng với dữ liệu mà process() giữ lại. Nếu process() thêm mọi record vào một List, lợi ích streaming sẽ mất.

### 7.1. Bỏ qua nhánh không cần đọc

JsonParser có skipChildren() để bỏ qua toàn bộ object/array hiện tại:

~~~java
if (parser.currentToken() == JsonToken.START_OBJECT) {
    // Xử lý object
} else if (parser.currentToken() == JsonToken.START_ARRAY) {
    parser.skipChildren();
}
~~~

Điều này hữu ích khi payload có nhiều field nhưng ứng dụng chỉ cần một số nhánh.

### 7.2. Đọc token có kiểm tra shape

Không nên gọi getText(), getIntValue() hoặc readValue() mà không xác nhận token nếu schema yêu cầu kiểu cụ thể.

~~~java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
    throw new JsonParseException(parser, "Expected integer token");
}

int quantity = parser.getIntValue();
~~~

Nếu input có thể vượt int, dùng getLongValue() hoặc getBigIntegerValue() rồi kiểm tra range theo hợp đồng.

### 7.3. Streaming không tự giải quyết validation

Khi xử lý từng record, vẫn cần kiểm tra required field, kiểu dữ liệu, range và precision, quan hệ giữa field, duplicate identifier, unknown field theo policy và quy tắc nghiệp vụ.

Streaming thay đổi cách quản lý dữ liệu, không loại bỏ yêu cầu validation.

## 8. Ghi token với JsonGenerator

JsonGenerator cho phép ghi JSON tuần tự vào OutputStream:

~~~java
try (JsonGenerator generator =
         mapper.getFactory().createGenerator(output)) {

    generator.writeStartArray();

    for (OrderRecord record : records) {
        generator.writeStartObject();
        generator.writeNumberField("id", record.id());
        generator.writeStringField("status", record.status());
        generator.writeEndObject();
    }

    generator.writeEndArray();
}
~~~

Generator ghi token ngay khi ứng dụng gọi writeStartObject(), writeStringField() hoặc writeEndObject(). Không cần tạo toàn bộ JsonNode tree hay String JSON.

Ví dụ trên tự ghi các field để minh họa token API. Nếu object có cấu trúc phức tạp, có thể dùng databind writer hoặc SequenceWriter để serialize từng phần tử vào generator/stream theo API phù hợp.

### 8.1. SequenceWriter cho nhiều giá trị

Jackson ObjectWriter có thể tạo SequenceWriter để ghi một sequence các giá trị:

~~~java
ObjectWriter writer = mapper.writerFor(OrderRecord.class);

try (SequenceWriter sequence =
         writer.writeValuesAsArray(output)) {

    for (OrderRecord record : records) {
        sequence.write(record);
    }
}
~~~

Cách này hữu ích khi muốn Jackson databind từng object nhưng không tạo List/array JSON trong bộ nhớ. SequenceWriter ghi các phần tử vào một JSON array.

Nếu giao thức yêu cầu newline-delimited JSON (NDJSON) hoặc nhiều root value thay vì một JSON array, phải chọn cách ghi sequence tương ứng và thống nhất với consumer. Không thay đổi framing mà không cập nhật hợp đồng.

### 8.2. Generator cho định dạng khác

JsonGenerator API là mô hình chung. Nếu mapper dùng CBORFactory hoặc SmileFactory, generator tạo bytes theo format tương ứng. Code token có thể tái sử dụng, nhưng bytes đầu ra không còn là JSON text.

Luôn dùng factory tương ứng với định dạng payload.

## 9. So sánh memory và allocation

Bảng dưới đây mô tả xu hướng, không phải con số cố định:

| Cách | Dữ liệu cần giữ | Chi phí bộ nhớ thường gặp |
|---|---|---|
| writeValueAsBytes() | Toàn bộ output bytes | Ít nhất một buffer hoàn chỉnh, có thể có buffer/copy trung gian |
| writeValueAsString() | Toàn bộ JSON text | Toàn bộ String và buffer tạo output |
| readTree() | Toàn bộ JsonNode tree | Node object và giá trị của toàn tài liệu |
| readValue(InputStream, DTO) | Toàn bộ DTO đích | Toàn bộ object graph được deserialize |
| JsonParser xử lý từng record | Parser buffer và record hiện tại | Có thể gần với bộ nhớ giới hạn theo record |
| JsonGenerator ghi từng record | Generator buffer và record hiện tại | Có thể tránh buffer toàn bộ output |

### 9.1. Kích thước payload không bằng heap usage

Một JSON text 10 MB không đồng nghĩa ứng dụng chỉ cần 10 MB heap. Khi parse, có thể có parser buffer, String và object cho từng property, collection backing arrays, DTO và nested object, Tree node, buffer của HTTP client hoặc compression, cùng các bản sao byte[] hoặc String trung gian.

Tương tự, String trong Java không nên được ước lượng bằng một công thức cố định số byte trên mỗi ký tự cho mọi JVM; representation nội bộ phụ thuộc implementation và nội dung. Điều quan trọng là tránh tạo nhiều bản sao không cần thiết.

### 9.2. Tránh buffer lặp lại

Một pipeline không hiệu quả:

~~~java
String json = mapper.writeValueAsString(order);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
String copy = new String(bytes, StandardCharsets.UTF_8);
send(copy.getBytes(StandardCharsets.UTF_8));
~~~

Pipeline này tạo nhiều representation liên tiếp. Nếu đích cần bytes:

~~~java
byte[] bytes = mapper.writeValueAsBytes(order);
send(bytes);
~~~

Nếu đích là stream:

~~~java
mapper.writeValue(outputStream, order);
~~~

Nếu cần biến đổi field, dùng tree có chủ đích rồi ghi ra đích phù hợp.

## 10. Charset và encoding: byte[] khác String ở đâu?

JSON qua network thường được trao đổi bằng UTF-8. Khi dùng byte API:

~~~java
byte[] bytes = mapper.writeValueAsBytes(value);
~~~

Jackson ghi JSON bytes theo UTF-8.

Khi dùng String API:

~~~java
String json = mapper.writeValueAsString(value);
~~~

Kết quả là Java String, chưa phải byte sequence của transport. Khi gửi qua network, phải chọn charset rõ ràng:

~~~java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
~~~

Đầu vào cũng tương tự:

- readValue(String, Type) nhận ký tự đã được giải mã.
- readValue(byte[], Type) nhận bytes và parser xử lý encoding theo khả năng format.
- readValue(InputStream, Type) đọc bytes từ stream.
- readValue(Reader, Type) nhận ký tự từ Reader.

Không dùng charset mặc định của máy. Với JSON interchange, UTF-8 là lựa chọn nên thống nhất trừ khi giao thức có quy định khác.

Với CBOR và Smile, bytes là encoding nhị phân chứ không phải văn bản UTF-8. Không gọi new String(binaryBytes, UTF_8) để chuyển đổi.

## 11. Buffering, compression và backpressure

Streaming không có nghĩa mọi tầng đều không buffer. Jackson có buffer nội bộ; BufferedInputStream/BufferedOutputStream, HTTP client, TLS, compression và broker cũng có thể buffer.

### 11.1. Buffering

Có thể bọc stream:

~~~java
try (InputStream input = new BufferedInputStream(
        Files.newInputStream(path))) {

    mapper.readValue(input, ImportConfig.class);
}
~~~

~~~java
try (OutputStream output = new BufferedOutputStream(
        Files.newOutputStream(path))) {

    mapper.writeValue(output, export);
}
~~~

Buffering có thể giảm số lần gọi I/O nhỏ. Nhưng thêm nhiều lớp buffer không tự động nhanh hơn; đo trên nguồn/đích thật và tránh giữ buffer quá lớn cho nhiều request đồng thời.

### 11.2. Compression

Có thể đặt compression stream bên ngoài Jackson:

~~~java
try (OutputStream file = Files.newOutputStream(path);
     OutputStream compressed = new GZIPOutputStream(file)) {

    mapper.writeValue(compressed, largeReport);
}
~~~

Thứ tự xử lý là object → Jackson JSON bytes → gzip bytes → file. Khi đọc, thứ tự ngược lại: file → GZIPInputStream → Jackson parser.

Compression có thể giảm network/storage nhưng tốn CPU và có thể làm tăng latency. Với payload đã nén hoặc binary, mức tiết kiệm có thể nhỏ. Cần giới hạn kích thước sau giải nén và xử lý decompression bomb.

### 11.3. Backpressure

Khi ghi trực tiếp vào network stream, tốc độ ghi phụ thuộc tốc độ nhận của bên kia. Stream có thể block hoặc báo lỗi nếu client ngắt kết nối.

Không tạo toàn bộ payload lớn chỉ để chờ network sẵn sàng nếu có thể serialize trực tiếp theo stream. Tuy nhiên, framework có thể có cơ chế buffering riêng; kiểm tra behavior của HTTP server/client đang dùng.

## 12. Quyền sở hữu và đóng stream

Khi làm việc với InputStream/OutputStream, phải xác định ai chịu trách nhiệm đóng tài nguyên.

Nếu ứng dụng mở file, thường nên dùng try-with-resources:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Config config = mapper.readValue(input, Config.class);
}
~~~

Với stream do framework hoặc caller quản lý, không nên đóng nó tùy tiện. Jackson parser/generator có các feature điều khiển việc tự đóng source/target khi parser/generator được đóng. Các feature thường gặp là AUTO_CLOSE_SOURCE và AUTO_CLOSE_TARGET; API cấu hình cụ thể có thể khác theo phiên bản Jackson.

Ví dụ cấu hình factory để không tự đóng target do caller sở hữu:

~~~java
JsonFactory factory = JsonFactory.builder()
    .disable(StreamWriteFeature.AUTO_CLOSE_TARGET)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Tương tự có thể cấu hình source auto-close theo StreamReadFeature nếu phiên bản đang dùng hỗ trợ API đó.

Hãy xác nhận lifecycle thực tế trong phiên bản Jackson và framework. Không giả định readValue() hoặc writeValue() luôn để stream mở hay luôn đóng stream trong mọi cấu hình. Với stream HTTP do server quản lý, quyền sở hữu thường thuộc framework.

### 12.1. Flush và close

Flush đẩy dữ liệu đang nằm trong buffer xuống tầng dưới; close thường hoàn tất generator/parser và giải phóng tài nguyên.

Nếu ghi một tài liệu JSON hoàn chỉnh, cần bảo đảm generator được hoàn tất trước khi gửi response thành công. Nếu đóng stream quá sớm, payload có thể bị cắt cụt.

Không gọi flush cho từng field nếu không cần; flush quá thường xuyên có thể giảm throughput. Với streaming response có yêu cầu độ trễ, chọn điểm flush theo giao thức và đo thực tế.

## 13. Xử lý lỗi khi đang streaming

Với byte[] hoặc String, ứng dụng thường có toàn bộ payload sau khi serialize thành công. Với OutputStream, bytes có thể đã được ghi một phần trước khi serializer gặp lỗi hoặc client ngắt kết nối.

Điều này ảnh hưởng đến tính nguyên tử:

- Ghi file trực tiếp: file đích có thể chứa payload dở dang.
- Ghi HTTP response: sau khi headers/body đã gửi, khó đổi status code thành lỗi khác.
- Ghi message broker: cần bảo đảm producer không publish message thiếu hoặc chưa commit.
- Ghi object storage: dùng upload/session semantics phù hợp.

### 13.1. Ghi file theo kiểu atomic

Nếu cần file chỉ xuất hiện khi serialize hoàn tất:

1. Ghi vào file tạm cùng filesystem.
2. Đóng generator và stream thành công.
3. Di chuyển file tạm sang tên đích bằng thao tác atomic nếu filesystem hỗ trợ.
4. Xóa file tạm nếu có lỗi.

Không ghi đè file tốt bằng payload dở dang nếu quy trình yêu cầu tính toàn vẹn.

### 13.2. HTTP response và lỗi giữa chừng

Khi server đã gửi một phần body, không thể luôn trả về JSON error body thay thế. Hãy validate dữ liệu trước khi bắt đầu response nếu có thể, hoặc dùng cơ chế streaming protocol có quy tắc kết thúc/lỗi rõ ràng.

Nếu payload được tạo từ database cursor, xác định cách xử lý khi query fail giữa chừng. Client cần biết response đã hoàn chỉnh hay bị ngắt.

## 14. ObjectMapper, ObjectReader và ObjectWriter

ObjectMapper nên được cấu hình xong trước khi sử dụng và tái sử dụng. Không tạo mapper mới cho từng record hoặc từng request nếu không có lý do.

ObjectReader và ObjectWriter là các đối tượng cấu hình theo operation, phù hợp để tái sử dụng:

~~~java
ObjectReader orderReader = mapper.readerFor(Order.class);
ObjectWriter orderWriter = mapper.writerFor(Order.class);

Order order = orderReader.readValue(input);
orderWriter.writeValue(output, order);
~~~

Chúng giúp cố định target type, view, root type hoặc một số tùy chọn mà không cần thay đổi mapper dùng chung.

Nếu cần hai policy khác nhau, ví dụ strict coercion cho API công khai và compatible coercion cho dữ liệu legacy, hãy tạo mapper/reader configuration riêng trước khi xử lý. Không sửa cấu hình mapper dùng chung theo từng request vì ObjectMapper được thiết kế để tái sử dụng sau khi cấu hình hoàn tất.

## 15. Dùng byte[], String, tree hoặc stream với HTTP

Lựa chọn phụ thuộc framework và kích thước payload.

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Response nhỏ, framework serialize DTO tự động | Trả DTO để message converter xử lý |
| Cần byte[] cho API ký/hash hoặc client | writeValueAsBytes() |
| Cần trả JSON text đã tạo sẵn | String, kèm Content-Type/charset rõ |
| Response lớn | Ghi qua OutputStream/streaming response |
| Cần sửa payload trước khi trả | JsonNode rồi serialize |
| Request JSON lớn nhưng xử lý từng record | InputStream + JsonParser |
| Request nhỏ cần DTO đầy đủ | readValue(InputStream, DTO.class) |

Đừng tự serialize thành String rồi trả String từ controller nếu framework có thể serialize DTO trực tiếp. Việc đó có thể khiến JSON text bị quote lần nữa như một JSON string hoặc làm mất content negotiation, tùy kiểu return và converter được chọn.

Nếu controller trả byte[], phải đặt Content-Type đúng. Nếu trả String, phải xác định framework có gửi nguyên text hay serialize String thành JSON string; hành vi phụ thuộc converter được chọn.

## 16. Dùng các lựa chọn với file và message broker

### 16.1. File cấu hình nhỏ

Có thể đọc trực tiếp thành DTO:

~~~java
try (InputStream input = Files.newInputStream(configPath)) {
    AppConfig config = mapper.readValue(input, AppConfig.class);
}
~~~

Nếu cần giữ comment và format gốc của file, Jackson Tree Model không bảo toàn những chi tiết đó. Chọn parser/editor hỗ trợ round-trip syntax nếu cần chỉnh sửa file của người dùng.

### 16.2. File JSON lớn gồm nhiều record

Dùng parser streaming và xử lý từng phần tử. Tránh deserialize thành List toàn bộ nếu số lượng record lớn.

Nếu mỗi record cần được ghi vào database, có thể xử lý theo batch nhỏ để cân bằng transaction, throughput và bộ nhớ.

### 16.3. Message broker

Broker thường nhận byte[]. Với message nhỏ, writeValueAsBytes() đơn giản. Với payload lớn, cân nhắc giới hạn message size, streaming API của client hoặc lưu payload ở object storage rồi gửi reference.

Không phải mọi broker API đều hỗ trợ streaming message body. Nếu API bắt buộc byte[], Jackson streaming có thể giảm buffer nội bộ nhưng cuối cùng vẫn phải có byte[] theo yêu cầu của broker.

### 16.4. HTTP client

Nếu client API hỗ trợ InputStream/Publisher, có thể nối generator với stream để tránh materialize toàn bộ body. Nếu client yêu cầu byte[], phải tạo payload hoàn chỉnh hoặc dùng một cơ chế publisher có thể phát bytes theo từng phần.

Kiểm tra retry semantics: stream một lần có thể không đọc lại được. Nếu request cần retry, có thể cần buffer, lưu file tạm hoặc tạo lại payload từ nguồn có thể replay.

## 17. Chọn cách đọc theo mục tiêu

| Mục tiêu | Cách đọc | Ghi chú |
|---|---|---|
| Đọc JSON text nhỏ | readValue(String, Type) | Có sẵn text |
| Đọc payload bytes | readValue(byte[], Type) | Không cần decode String |
| Đọc file/request stream thành DTO | readValue(InputStream, Type) | DTO vẫn được tạo đầy đủ |
| Kiểm tra field động | readTree(...) | Tạo toàn bộ tree |
| Đọc array rất lớn từng phần tử | JsonParser | Xử lý từng record |
| Bỏ qua nhánh lớn không cần dùng | JsonParser.skipChildren() | Không tạo subtree |
| Đọc nhiều root value | Parser/MappingIterator phù hợp | Cần thống nhất framing |
| Đọc binary format | Mapper với factory tương ứng | Không dùng JSON mapper mặc định |

Nếu input là JSON text trong String, dùng readValue(String, Type) hoặc readTree(String). Nếu input là bytes từ HTTP, dùng byte[] hoặc InputStream trực tiếp. Nếu input là CBOR/Smile, dùng mapper đúng format.

## 18. Chọn cách ghi theo mục tiêu

| Mục tiêu | Cách ghi | Ghi chú |
|---|---|---|
| Cần JSON bytes hoàn chỉnh | writeValueAsBytes() | Buffer toàn payload |
| Cần JSON text | writeValueAsString() | Buffer toàn text |
| Cần ghi file/HTTP stream | writeValue(OutputStream, value) | Tránh String/byte[] trung gian |
| Cần sửa field động rồi ghi | ObjectNode + writeValue(...) | Tree nằm toàn bộ trong RAM |
| Cần ghi array lớn từng record | JsonGenerator hoặc SequenceWriter | Tránh tạo List JSON trung gian |
| Cần ghi CBOR/Smile | Mapper dùng factory đúng format | Output là binary bytes |

Không chọn stream chỉ vì nghe có vẻ nhanh hơn. Nếu payload nhỏ, byte[] hoặc String có thể đơn giản và hiệu quả đủ tốt. Nếu payload lớn, cần đo heap, allocation, latency và throughput.

## 19. Benchmark các lựa chọn

Để so sánh đúng, dùng cùng dữ liệu và cùng mapper configuration.

Các chỉ số nên đo:

- Kích thước output bytes.
- Thời gian serialize/deserialize.
- Allocation và peak heap.
- GC frequency/pause.
- Throughput.
- Latency p50/p95/p99.
- Số bản sao hoặc buffer lớn.
- Hành vi khi client đọc chậm.
- Khả năng retry và replay.

Ví dụ đo kích thước:

~~~java
byte[] bytes = mapper.writeValueAsBytes(value);
String text = mapper.writeValueAsString(value);

System.out.println("bytes length = " + bytes.length);
System.out.println("text length = " + text.length());
~~~

Hai con số này không cùng đơn vị: bytes.length là số byte UTF-8; text.length là số UTF-16 code unit trong Java String. Không so sánh trực tiếp chúng như cùng một đơn vị.

Để benchmark hiệu năng, dùng JMH hoặc harness phù hợp với warm-up, nhiều iteration và dữ liệu đại diện. Không dùng một phép đo System.nanoTime() đơn lẻ làm kết luận production.

### 19.1. So sánh cả trường hợp nóng và lạnh

Mapper tạo mới có chi phí cấu hình và khởi tạo cache. Benchmark phải phản ánh cách ứng dụng sử dụng mapper thực tế: thường là mapper được cấu hình một lần rồi tái sử dụng.

Nếu mỗi request tạo mapper mới, hãy sửa cách dùng đó trước khi kết luận byte[] hay stream chậm. Mapper lifecycle có thể ảnh hưởng kết quả lớn hơn khác biệt API.

## 20. Kiểm thử lựa chọn dữ liệu

Nên kiểm tra rằng các cách biểu diễn cho cùng một data model cho kết quả mong đợi.

### 20.1. String và byte[] biểu diễn cùng JSON

~~~java
@Test
void stringAndBytesRepresentSameJson() throws Exception {
    Order order = sampleOrder();

    String text = mapper.writeValueAsString(order);
    byte[] bytes = mapper.writeValueAsBytes(order);

    JsonNode fromText = mapper.readTree(text);
    JsonNode fromBytes = mapper.readTree(bytes);

    assertEquals(fromText, fromBytes);
}
~~~

### 20.2. Tree chuyển đổi giữ cấu trúc logic

~~~java
@Test
void treeRepresentationMatchesSerializedObject() throws Exception {
    Order order = sampleOrder();

    JsonNode fromValue = mapper.valueToTree(order);
    JsonNode fromText = mapper.readTree(
        mapper.writeValueAsString(order)
    );

    assertEquals(fromText, fromValue);
}
~~~

### 20.3. Stream đọc được cùng DTO

~~~java
@Test
void readsFromInputStream() throws Exception {
    byte[] bytes = mapper.writeValueAsBytes(sampleOrder());

    try (InputStream input = new ByteArrayInputStream(bytes)) {
        Order restored = mapper.readValue(input, Order.class);
        assertEquals(sampleOrder(), restored);
    }
}
~~~

### 20.4. Parser xử lý array từng record

Test một JSON array có nhiều phần tử và xác nhận mỗi record được xử lý đúng, thứ tự không đổi và parser phát hiện array bị cắt cụt.

### 20.5. Test lifecycle stream

Nếu stream do caller sở hữu và cần tiếp tục sử dụng sau mapping, hãy test rằng cấu hình auto-close phù hợp. Đừng chỉ dựa vào giả định về default của phiên bản Jackson.

### 20.6. Test payload lớn và lỗi giữa chừng

- Payload vượt giới hạn request.
- JSON nesting quá sâu.
- String/number token quá dài.
- Output stream ném IOException giữa chừng.
- Client đóng kết nối khi đang ghi.
- Parser gặp EOF giữa một object.
- Bộ xử lý record ném lỗi ở phần tử giữa array.

Test các trường hợp này giúp xác định file tạm, transaction, retry hoặc dead-letter behavior có hoạt động đúng không.

## 21. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng String rồi đổi sang bytes dù không cần text | Tạo representation trung gian | Dùng writeValueAsBytes() hoặc OutputStream |
| Dùng byte[] cho payload rất lớn | Buffer toàn bộ tài liệu | Ghi trực tiếp qua stream |
| Nghĩ readValue(InputStream, List.class) là streaming theo record | Kết quả vẫn là List đầy đủ | Dùng JsonParser hoặc sequence API |
| Dùng readTree() cho payload lớn chỉ để đọc một field | Tạo toàn bộ JsonNode tree | Dùng parser và skipChildren() |
| Dùng tree chỉ để đổi DTO | Thêm bước chuyển đổi | Dùng convertValue() |
| Dùng String cho CBOR/Smile | Binary bytes bị giải mã sai | Giữ byte[]/stream và mapper đúng format |
| Dùng charset mặc định | Có thể tạo sai bytes | Chỉ định StandardCharsets.UTF_8 |
| Gọi getBytes() nhiều lần | Tạo nhiều bản sao | Chọn representation cuối cùng ngay từ đầu |
| Đóng stream do framework sở hữu | Vi phạm lifecycle của caller | Kiểm tra AUTO_CLOSE_SOURCE/TARGET |
| Output file dở dang khi serialize lỗi | Ghi trực tiếp vào file đích | Ghi file tạm rồi atomic move |
| Log toàn bộ JSON | Có thể lộ dữ liệu nhạy cảm | Redact và log field cần thiết |
| Benchmark một lần | JVM warm-up và I/O gây sai lệch | Dùng JMH/dữ liệu đại diện |
| Tạo ObjectMapper cho từng request | Tăng chi phí và mất cache | Cấu hình một lần rồi tái sử dụng |
| So sánh String.length với byte[].length | Hai đơn vị khác nhau | So sánh byte length hoặc encode text sang UTF-8 |

## 22. Quy trình lựa chọn trong một tính năng

1. Xác định dữ liệu có cần được chỉnh sửa theo cấu trúc hay không.
2. Xác định kích thước tối đa và số lượng record.
3. Xác định API đích nhận String, byte[], DTO hay stream.
4. Nếu cần toàn bộ bytes, dùng byte[] và tính đến bộ nhớ.
5. Nếu cần text, dùng String và chọn UTF-8 rõ ràng khi chuyển bytes.
6. Nếu cần thao tác field động, dùng JsonNode tree.
7. Nếu payload lớn, dùng InputStream/OutputStream.
8. Nếu cần memory theo từng record, dùng JsonParser/JsonGenerator hoặc sequence API.
9. Phân biệt I/O streaming với việc materialize toàn bộ DTO/List/tree.
10. Xác định ownership, auto-close, flush và error handling.
11. Cân nhắc compression, backpressure, retry và replay.
12. Tái sử dụng ObjectMapper/ObjectReader/ObjectWriter đã cấu hình.
13. Test cùng data model qua các đường đi dự kiến.
14. Benchmark với payload đại diện trước khi tối ưu.

## 23. Nguyên tắc nên giữ

- Dùng byte[] khi cần toàn bộ payload bytes và kích thước nằm trong giới hạn bộ nhớ.
- Dùng String khi thực sự cần JSON text.
- Dùng UTF-8 tường minh khi chuyển String sang bytes.
- Không chuyển CBOR/Smile bytes thành String UTF-8.
- Dùng JsonNode khi cần truy cập ngẫu nhiên hoặc biến đổi cấu trúc.
- Nhớ rằng Tree Model giữ toàn bộ tài liệu trong bộ nhớ.
- readValue(InputStream, DTO.class) vẫn materialize toàn bộ DTO.
- Dùng JsonParser/JsonGenerator khi cần xử lý token hoặc record tuần tự.
- Phân biệt I/O streaming với token streaming.
- Xác định rõ ai sở hữu và đóng InputStream/OutputStream.
- Xử lý output dở dang bằng file tạm hoặc transaction phù hợp.
- Không tạo String, byte[] và tree liên tiếp nếu không cần.
- Tái sử dụng mapper đã cấu hình xong.
- Benchmark theo payload, concurrency và transport thực tế.
- Giữ dữ liệu nhạy cảm khỏi log và fixture không được kiểm soát.

Lựa chọn byte array, String, tree hay stream là quyết định về mục tiêu xử lý và vòng đời dữ liệu. byte[] phù hợp khi cần toàn bộ bytes; String phù hợp khi cần text; JsonNode phù hợp khi cần quan sát và biến đổi cấu trúc; InputStream/OutputStream phù hợp với I/O tuần tự; JsonParser/JsonGenerator phù hợp khi cần xử lý từng token hoặc record với bộ nhớ giới hạn. Hiểu rõ mức độ materialization, charset, stream ownership và chi phí buffer giúp chọn API đơn giản nhất mà vẫn đáp ứng kích thước, hiệu năng và độ tin cậy của hệ thống.

