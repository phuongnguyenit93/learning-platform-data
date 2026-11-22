# Tránh chuyển qua nhiều biểu diễn trung gian không cần thiết

Khi dùng Jackson, một request JSON có thể đi qua nhiều dạng dữ liệu trước khi đến object Java mà ứng dụng cần. Ví dụ, code đọc JSON thành chuỗi, parse thành JsonNode, chuyển thành Map, rồi lại chuyển Map thành DTO. Mỗi bước có thể tạo thêm object, buffer, bản sao chuỗi hoặc một lần duyệt toàn bộ dữ liệu.

Những bước trung gian đôi khi cần thiết, nhưng nếu chúng chỉ phục vụ việc chuyển qua lại giữa các kiểu mà Jackson đã hỗ trợ trực tiếp, chúng làm tăng chi phí CPU, bộ nhớ và garbage collection. Với payload lớn hoặc lưu lượng cao, chi phí này có thể đáng kể.

Nguyên tắc của bài học là **đưa dữ liệu từ nguồn trực tiếp đến kiểu đích khi cấu trúc đã biết; chỉ tạo biểu diễn trung gian khi nó giải quyết một nhu cầu thực sự**. Jackson có API đọc/ghi trực tiếp từ stream, reader, writer và parser/generator. Khi cần cây JSON linh hoạt, JsonNode vẫn là lựa chọn hợp lý. Điều quan trọng là chọn đúng biểu diễn cho công việc, tránh tạo rồi hủy nhiều dạng dữ liệu không cần thiết.

## 1. Một payload có thể bị chuyển đổi qua nhiều lớp

Xét một API nhận JSON và tạo Order:

~~~json
{
  "id": 1001,
  "customerId": 42,
  "total": 250000,
  "currency": "VND"
}
~~~

Cách trực tiếp:

~~~java
Order order = objectMapper.readValue(
        requestBody,
        Order.class
);
~~~

Cách nhiều bước:

~~~java
JsonNode tree = objectMapper.readTree(requestBody);

Map<String, Object> values = objectMapper.convertValue(
        tree,
        new TypeReference<Map<String, Object>>() {}
);

Order order = objectMapper.convertValue(values, Order.class);
~~~

Cả hai cách có thể tạo ra cùng một kết quả, nhưng cách thứ hai thực hiện thêm các công việc:
- Parse JSON thành cây node.
- Duyệt cây để tạo Map và các giá trị lồng nhau.
- Duyệt Map để tạo Order.
- Tạo thêm object trung gian và tham chiếu.
- Có thể thực hiện chuyển đổi kiểu ở nhiều bước.

Nếu ứng dụng không cần đọc cấu trúc động, kiểm tra nhiều nhánh hoặc giữ lại field tùy ý, các bước này không mang lại giá trị tương ứng với chi phí.

### 1.1. Các dạng trung gian thường gặp

| Biểu diễn | Khi nào hữu ích | Chi phí có thể phát sinh |
|---|---|---|
| String JSON | API hoặc hệ thống thực sự yêu cầu text | Giữ toàn bộ nội dung trong bộ nhớ, có thể phải encode/decode |
| byte[] JSON | Cần buffer bytes để truyền/lưu hoặc retry | Cấp phát mảng lớn và sao chép |
| JsonNode tree | Schema động, truy cập field tùy chọn, sửa cây | Tạo node cho toàn bộ cấu trúc |
| Map/List | Cấu trúc linh hoạt hoặc tích hợp API Map-based | Tạo collection, boxing và mất một phần thông tin kiểu |
| TokenBuffer | Cần lưu token để đọc lại hoặc chuyển tiếp | Giữ token và nội dung trong bộ nhớ |
| DTO/POJO | Dữ liệu có schema và kiểu đã biết | Tạo object nghiệp vụ cần thiết |

Không có biểu diễn nào luôn tốt nhất. Chi phí chỉ trở thành lãng phí khi ứng dụng tạo nó mà không dùng được lợi ích của nó.

## 2. Đọc trực tiếp JSON thành POJO

Khi kiểu đích đã biết, dùng readValue trực tiếp:

~~~java
ObjectMapper mapper = new ObjectMapper();

Order order = mapper.readValue(
        jsonInputStream,
        Order.class
);
~~~

Jackson đọc token từ stream và tạo Order theo data binding. Ứng dụng không cần tạo một chuỗi JSON đầy đủ hoặc cây JsonNode trước đó.

Với chuỗi đã có sẵn:

~~~java
Order order = mapper.readValue(jsonText, Order.class);
~~~

Với Reader:

~~~java
try (Reader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
)) {
    Order order = mapper.readValue(reader, Order.class);
}
~~~

Chọn overload theo nguồn dữ liệu hiện có:
- InputStream nếu dữ liệu đang ở dạng bytes.
- Reader nếu ứng dụng đã có character stream.
- String nếu dữ liệu thực sự đang ở dạng String.
- File/URL hoặc nguồn khác nếu API của phiên bản Jackson đang dùng hỗ trợ và quyền sở hữu tài nguyên đã rõ.

Không chuyển InputStream thành String chỉ để gọi readValue(String, Class). Việc đó có thể tạo thêm một buffer ký tự lớn và một bản sao của nội dung.

### 2.1. Dùng ObjectReader khi kiểu đích và cấu hình đã cố định

ObjectReader là cấu hình đọc bất biến dựa trên ObjectMapper:

~~~java
ObjectReader orderReader = mapper.readerFor(Order.class);

Order first = orderReader.readValue(firstInputStream);
Order second = orderReader.readValue(secondInputStream);
~~~

Có thể tạo reader một lần cho một kiểu hoặc một contract cụ thể rồi tái sử dụng. ObjectReader lưu kiểu đích và các tùy chọn đọc, giúp code thể hiện rõ ý định.

Nếu cần cấu hình khác nhau cho từng luồng, tạo reader biến thể bằng with/without thay vì thay đổi ObjectMapper dùng chung.

## 3. Ghi trực tiếp object ra OutputStream

Chiều serialize cũng có thể tạo nhiều bản sao không cần thiết.

Cách trực tiếp:

~~~java
mapper.writeValue(outputStream, order);
~~~

Cách tạo chuỗi rồi chuyển sang bytes:

~~~java
String json = mapper.writeValueAsString(order);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
outputStream.write(bytes);
~~~

Cách thứ hai cần:
1. Serialize object thành String.
2. Giữ String trong bộ nhớ.
3. Encode String thành byte[].
4. Ghi byte[] ra stream.

Nếu đích cuối cùng là OutputStream, hãy để Jackson ghi trực tiếp:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, order);
}
~~~

Với response HTTP, framework thường có thể dùng Jackson message converter để ghi DTO trực tiếp ra response stream. Tránh tự serialize thành String rồi trả String nếu framework vốn đã có thể serialize object.

### 3.1. Khi nào String vẫn hợp lý?

String JSON là phù hợp nếu ứng dụng thật sự cần:
- Trả về một chuỗi cho API yêu cầu String.
- Tạo nội dung để ký hoặc hash theo một quy trình canonicalization cụ thể.
- Đưa payload vào một API chỉ nhận String.
- Hiển thị hoặc lưu nội dung text theo yêu cầu sản phẩm.
- So sánh hoặc xử lý văn bản theo một quy tắc đã xác định.

Không nên loại bỏ String một cách máy móc. Hãy tránh tạo String chỉ để chuyển ngay thành bytes hoặc parse lại thành object.

## 4. Không serialize rồi deserialize lại cùng một object

Một mẫu lãng phí thường gặp là dùng JSON làm cầu nối giữa hai kiểu Java:

~~~java
String json = mapper.writeValueAsString(source);
Target target = mapper.readValue(json, Target.class);
~~~

Đây là một vòng đi qua textual JSON:
- Serialize source thành token.
- Encode token thành ký tự JSON.
- Giữ String.
- Parse String trở lại thành token.
- Deserialize token thành Target.

Nếu mục đích chỉ là chuyển đổi một object Java trong bộ nhớ sang một kiểu Java khác, hãy cân nhắc convertValue:

~~~java
Target target = mapper.convertValue(source, Target.class);
~~~

convertValue không tạo một String JSON trung gian. Trong Jackson Databind, quá trình này sử dụng cơ chế token buffer nội bộ để serialize và deserialize giữa các kiểu. Vì vậy nó tránh bước encode/parse văn bản, nhưng **vẫn thực hiện một lượt chuyển đổi và có chi phí**. Nó không phải phép cast và cũng không phải zero-copy.

### 4.1. convertValue phù hợp khi nào?

Có thể dùng convertValue khi:
- Chuyển giữa hai DTO tương thích trong bộ nhớ.
- Chuyển một object thành Map để gọi một API Map-based.
- Dữ liệu nguồn đã là object Java, không phải request text cần parse.
- Muốn tận dụng annotation và serializer/deserializer của Jackson cho phép chuyển đổi đó.

Ví dụ:

~~~java
CreateOrderCommand command = mapper.convertValue(
        requestDto,
        CreateOrderCommand.class
);
~~~

Tuy nhiên, nếu source và target có thể được tạo trực tiếp từ cùng một input, hãy cân nhắc deserialize thẳng thành kiểu cần dùng. Nếu chỉ cần copy vài field, constructor hoặc mapper chuyên dụng có thể đơn giản và nhanh hơn convertValue.

### 4.2. convertValue không phải công cụ validation

convertValue có thể thực hiện coercion và mapping theo cấu hình Jackson. Nó không chứng minh dữ liệu đáp ứng constraint nghiệp vụ.

Sau khi chuyển đổi, vẫn cần:
- Bean Validation.
- Kiểm tra domain rule.
- Kiểm tra quyền và trạng thái hệ thống.
- Xử lý lỗi mapping theo contract.

Không dùng convertValue để che lỗi bằng cách chuyển mọi input thành một kiểu chung rồi mặc định chấp nhận kết quả.

## 5. treeToValue và valueToTree: dùng khi thực sự cần cây JSON

JsonNode hữu ích khi cấu trúc đầu vào động hoặc chưa biết kiểu đích ngay từ đầu.

Ví dụ cần đọc discriminator trước:

~~~json
{
  "kind": "invoice",
  "payload": {
    "invoiceNumber": "INV-100",
    "amount": 250000
  }
}
~~~

Ứng dụng có thể đọc cây:

~~~java
JsonNode root = mapper.readTree(inputStream);
String kind = root.path("kind").asText();

JsonNode payload = root.path("payload");

if ("invoice".equals(kind)) {
    Invoice invoice = mapper.treeToValue(
            payload,
            Invoice.class
    );
    processInvoice(invoice);
}
~~~

Ở đây tree có ích vì code cần kiểm tra cấu trúc và chọn kiểu đích dựa trên nội dung. treeToValue chuyển một node đã có thành POJO mà không serialize node thành String rồi parse lại.

### 5.1. Không chuyển cả cây qua String

Tránh:

~~~java
JsonNode node = mapper.readTree(inputStream);

String intermediateJson = mapper.writeValueAsString(node);

Invoice invoice = mapper.readValue(
        intermediateJson,
        Invoice.class
);
~~~

Nếu đã có JsonNode, dùng treeToValue:

~~~java
Invoice invoice = mapper.treeToValue(node, Invoice.class);
~~~

Cách trực tiếp tránh tạo text JSON mới rồi parse lại. Tuy nhiên, cây JsonNode ban đầu vẫn đã được materialize trong bộ nhớ.

### 5.2. valueToTree cũng không miễn phí

Khi cần biểu diễn một object thành JsonNode:

~~~java
JsonNode tree = mapper.valueToTree(order);
~~~

valueToTree tránh tạo String JSON trung gian, nhưng Jackson vẫn phải serialize object thành token và xây dựng cây node. Nếu ứng dụng chỉ cần một vài giá trị, gọi getter trực tiếp thường đơn giản và rẻ hơn.

Ví dụ, thay vì:

~~~java
JsonNode tree = mapper.valueToTree(order);
long id = tree.path("id").asLong();
~~~

hãy dùng:

~~~java
long id = order.getId();
~~~

Dùng tree khi cần thao tác trên cấu trúc JSON, không dùng nó chỉ để đọc lại field mà object Java đã cung cấp.

## 6. Đừng parse cùng một request nhiều lần

Một số ứng dụng đọc request thành cây để kiểm tra, sau đó đọc lại cùng nội dung thành DTO:

~~~java
JsonNode root = mapper.readTree(body);

validateShape(root);

Order order = mapper.readValue(body, Order.class);
~~~

Điều này có thể hợp lý nếu validation cần thao tác trên cây và không thể biểu diễn bằng DTO. Nhưng nếu kiểm tra chỉ là:
- Field bắt buộc.
- Kiểu dữ liệu.
- Giới hạn số.
- Chuỗi rỗng.
- Constraint trên object.

thì có thể deserialize một lần thành DTO rồi dùng Bean Validation.

~~~java
OrderRequest request = mapper.readValue(
        inputStream,
        OrderRequest.class
);

Set<ConstraintViolation<OrderRequest>> violations =
        validator.validate(request);

if (!violations.isEmpty()) {
    throw new InvalidRequestException(violations);
}
~~~

Một lần parse và một lần validation trên object thường dễ theo dõi hơn việc parse toàn bộ body thành tree rồi parse lại.

### 6.1. Khi tree và DTO đều có ích

Có những trường hợp cần cả hai:
- Cần giữ extension fields chưa biết.
- Cần chọn subtype dựa trên discriminator tùy biến.
- Cần áp dụng JSON Patch hoặc biến đổi tree.
- Cần lưu một phần payload gốc để chuyển tiếp.
- Cần kiểm tra schema động mà DTO chưa mô tả được.

Khi đó, hãy tạo tree một lần, xử lý trực tiếp trên tree và chỉ chuyển các nhánh cần thiết sang DTO. Tránh lặp lại readTree, writeValueAsString và readValue cho cùng payload.

## 7. Dùng JsonParser để xử lý token theo kiểu streaming

Nếu chỉ cần đọc một vài field hoặc xử lý từng phần tử của một mảng lớn, không nhất thiết phải tạo JsonNode cho toàn bộ document.

Jackson Core cung cấp JsonParser để đọc token tuần tự:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();

        if (token == JsonToken.FIELD_NAME
                && "eventType".equals(parser.currentName())) {
            parser.nextToken();
            String eventType = parser.getText();

            handleEventType(eventType);
        }
    }
}
~~~

Parser tiến qua document theo thứ tự. Ứng dụng chỉ giữ những giá trị cần thiết tại thời điểm đó, thay vì xây dựng toàn bộ cây.

Streaming phù hợp khi:
- File hoặc payload lớn.
- Chỉ cần một tập field.
- Có thể xử lý và giải phóng từng record.
- Muốn giới hạn bộ nhớ.
- Dữ liệu đến từ stream liên tục.

Streaming đòi hỏi code quản lý trạng thái parser cẩn thận. Phải biết token hiện tại, khi nào cần gọi nextToken và khi nào phải bỏ qua subtree bằng skipChildren.

### 7.1. Đọc từng object trong root array

Giả sử file là một JSON array chứa hàng triệu record:

~~~json
[
  {"id": 1, "type": "created"},
  {"id": 2, "type": "updated"},
  {"id": 3, "type": "deleted"}
]
~~~

Không nên đọc toàn bộ array thành List nếu ứng dụng chỉ cần xử lý từng record. Có thể duyệt parser:

~~~java
ObjectReader eventReader = mapper.readerFor(Event.class);

try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new JsonParseException(
                parser,
                "Expected a JSON array"
        );
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        Event event = eventReader.readValue(parser);
        process(event);
    }
}
~~~

Mỗi lần đọc, ObjectReader tạo một Event từ object hiện tại. Sau khi xử lý, ứng dụng có thể bỏ tham chiếu đến event đó và tiếp tục phần tử tiếp theo.

Nếu root array có thể chứa null hoặc kiểu token khác, hãy quy định cách xử lý và kiểm tra token trước khi gọi reader. Với input không tin cậy, cần giới hạn kích thước, độ sâu và số record.

### 7.2. Streaming không có nghĩa là zero-copy

Ngay cả khi đọc trực tiếp từ InputStream, Jackson vẫn cần:
- Đọc bytes vào buffer.
- Giải mã ký tự.
- Tạo token.
- Tạo object Java nếu dùng data binding.
- Tạo String hoặc number object cho những field cần giữ lại.

Streaming giúp tránh giữ toàn bộ document hoặc cây JSON trong bộ nhớ. Nó không loại bỏ mọi allocation.

## 8. Dùng JsonGenerator để ghi trực tiếp token

Khi output có cấu trúc đơn giản hoặc quá lớn để materialize thành một object graph, có thể ghi trực tiếp bằng JsonGenerator:

~~~java
try (JsonGenerator generator =
        mapper.getFactory().createGenerator(outputStream)) {

    generator.writeStartObject();
    generator.writeStringField("status", "accepted");
    generator.writeNumberField("processedCount", 120);
    generator.writeEndObject();
}
~~~

Generator quản lý escape, quote và cấu trúc JSON. Không cần tạo Map rồi serialize nếu output chỉ có một vài field.

Với cấu trúc phức tạp, ObjectWriter thường dễ đọc và ít lỗi hơn. Chỉ chuyển sang generator thủ công khi:
- Cần stream output từng phần.
- Dữ liệu quá lớn để giữ thành object graph.
- Cần điều khiển chính xác thứ tự hoặc cấu trúc token.
- Muốn kết hợp dữ liệu từ nhiều nguồn mà không tạo một object trung gian lớn.

Không nên dùng generator thủ công cho mọi response nhỏ. Code streaming cấp thấp có thể khó bảo trì hơn lợi ích hiệu năng thu được.

## 9. Tránh chuyển InputStream thành byte[] hoặc String nếu không cần

Một mẫu phổ biến:

~~~java
byte[] body = inputStream.readAllBytes();
String json = new String(body, StandardCharsets.UTF_8);
Order order = mapper.readValue(json, Order.class);
~~~

Ở đây ứng dụng giữ byte[] và String, rồi Jackson lại parse String. Với payload lớn, bộ nhớ có thể chứa nhiều bản sao cùng lúc.

Đọc trực tiếp:

~~~java
Order order = mapper.readValue(inputStream, Order.class);
~~~

Nếu nguồn là file:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Order order = mapper.readValue(input, Order.class);
}
~~~

Nếu cần xác minh chữ ký trên bytes gốc hoặc cần retry, buffering có thể là yêu cầu hợp lệ. Khi đó hãy giới hạn kích thước, xác định quyền sở hữu buffer và tránh tạo thêm String không cần thiết.

### 9.1. InputStream và Reader có ý nghĩa khác nhau

InputStream cung cấp bytes; Reader cung cấp characters đã được giải mã. Nếu dữ liệu là JSON UTF-8 từ network hoặc file, đưa InputStream trực tiếp cho Jackson thường cho phép parser xử lý decoding theo byte stream và cấu hình encoding.

Nếu ứng dụng đã có Reader từ một nguồn text, dùng Reader trực tiếp. Đừng chuyển Reader về String chỉ để parse rồi tạo một Reader mới.

## 10. Tái sử dụng ObjectMapper, ObjectReader và ObjectWriter

Tạo ObjectMapper liên tục có thể tốn chi phí vì mapper cần cấu hình factory, module, serializer/deserializer cache và các metadata introspection.

Không nên:

~~~java
public Order parse(String json) throws IOException {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.readValue(json, Order.class);
}
~~~

Nên cấu hình mapper một lần:

~~~java
public final class JsonSupport {
    public static final ObjectMapper MAPPER =
            JsonMapper.builder()
                    .findAndAddModules()
                    .build();

    public static final ObjectReader ORDER_READER =
            MAPPER.readerFor(Order.class);

    private JsonSupport() {
    }
}
~~~

Sau khi cấu hình xong, ObjectMapper có thể được tái sử dụng giữa các thread. Không tiếp tục thay đổi cấu hình mapper trong lúc ứng dụng đang dùng nó.

ObjectReader và ObjectWriter là các đối tượng cấu hình bất biến, thích hợp để tạo sẵn cho từng kiểu hoặc contract:

~~~java
ObjectReader orderReader = mapper.readerFor(Order.class);
ObjectWriter orderWriter = mapper.writerFor(Order.class);
~~~

Có thể tạo biến thể cho một thao tác cụ thể:

~~~java
ObjectWriter prettyWriter = orderWriter.with(
        SerializationFeature.INDENT_OUTPUT
);
~~~

Dùng reader/writer giúp tránh việc mỗi request phải lặp lại cấu hình kiểu và feature.

### 10.1. Cẩn thận với cấu hình theo request

Nếu mỗi request cần một option khác nhau, hãy tạo reader/writer biến thể từ mapper đã cấu hình thay vì mutate mapper dùng chung.

Ví dụ:

~~~java
ObjectReader strictOrderReader = mapper
        .readerFor(Order.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Không bật/tắt feature trên ObjectMapper toàn cục giữa hai request vì có thể gây hành vi khó đoán khi nhiều thread cùng chạy.

## 11. Không chuyển POJO sang Map nếu chỉ cần truy cập property

Map hữu ích cho cấu trúc linh hoạt, nhưng chuyển một DTO thành Map chỉ để đọc vài giá trị sẽ tạo thêm collection và boxing.

Tránh:

~~~java
Map<String, Object> values = mapper.convertValue(
        order,
        new TypeReference<Map<String, Object>>() {}
);

String currency = (String) values.get("currency");
~~~

Dùng getter:

~~~java
String currency = order.getCurrency();
~~~

Map phù hợp khi:
- Schema không cố định.
- Consumer nhận field động.
- Cần biểu diễn extension data.
- Tích hợp với API thực sự yêu cầu Map.
- Cần xử lý generic key/value.

Nếu schema đã biết, DTO thường cho type safety tốt hơn và tránh lookup key bằng String.

## 12. Chỉ materialize JsonNode khi cần khả năng thao tác cây

JsonNode rất hữu ích cho:
- JSON Patch.
- So sánh hai cấu trúc JSON.
- Truy cập field tùy chọn theo path.
- Giữ unknown properties.
- Chọn kiểu đích theo discriminator tùy biến.
- Chỉnh sửa payload trước khi serialize lại.

Nhưng nếu chỉ cần kiểm tra một field cố định, có thể dùng DTO hoặc streaming parser.

Ví dụ cần sửa một field trong payload động:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(inputStream);
root.put("processed", true);

mapper.writeValue(outputStream, root);
~~~

Tree là lựa chọn hợp lý vì ứng dụng thực sự cần thay đổi cấu trúc JSON.

Ngược lại, nếu chỉ cần thêm một field vào object đã biết, có thể thêm property vào DTO và serialize DTO đó. Không cần chuyển DTO sang tree rồi sửa tree.

## 13. Tránh parse, convert và serialize lặp lại trong vòng lặp

Một anti-pattern khác là tạo mapper hoặc chuyển đổi nhiều lần cho mỗi phần tử:

~~~java
for (String json : messages) {
    ObjectMapper mapper = new ObjectMapper();
    JsonNode node = mapper.readTree(json);
    Event event = mapper.treeToValue(node, Event.class);
    process(event);
}
~~~

Nếu kiểu đích cố định, đọc trực tiếp bằng reader đã cấu hình:

~~~java
ObjectReader eventReader = mapper.readerFor(Event.class);

for (String json : messages) {
    Event event = eventReader.readValue(json);
    process(event);
}
~~~

Nếu messages là một nguồn stream hoặc file chứa nhiều record, tốt hơn là dùng parser/reader tuần tự để tránh giữ tất cả String trong List.

Điều cần tránh:
- Tạo ObjectMapper trong vòng lặp.
- Parse thành tree rồi chuyển ngay thành POJO.
- Serialize object thành String rồi parse lại.
- Tạo Map chỉ để đọc field đã có getter.
- Giữ nhiều bản sao payload trong một batch.

## 14. Custom serializer/deserializer có thể loại bỏ bước hậu xử lý

Đôi khi ứng dụng serialize DTO thành JsonNode hoặc Map, sau đó sửa tên field, format ngày hoặc cấu trúc lồng nhau bằng một vòng lặp hậu xử lý.

Nếu format đó là hợp đồng ổn định, có thể dùng annotation hoặc custom serializer/deserializer để định nghĩa representation trực tiếp.

Ví dụ custom serializer ghi một kiểu ngày theo định dạng cụ thể:

~~~java
public class LocalDateSerializer
        extends JsonSerializer<LocalDate> {

    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public void serialize(
            LocalDate value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {

        generator.writeString(FORMATTER.format(value));
    }
}
~~~

Đăng ký serializer qua module hoặc annotation phù hợp. Khi đó, object được serialize theo wire format ngay từ đầu, không cần tạo tree rồi đổi từng field sau đó.

Tuy nhiên, custom serializer tăng độ phức tạp và có thể ảnh hưởng đến nhiều API dùng chung kiểu đó. Chỉ dùng khi representation là một phần của contract và không thể diễn đạt rõ bằng annotation hoặc DTO riêng.

## 15. Khi cần đọc lại token, TokenBuffer có thể hợp lý

JsonParser là forward-only: sau khi đã đọc qua token, parser thông thường không thể quay lại token cũ.

Nếu một thành phần cần đọc discriminator trước, sau đó một thành phần khác cần deserialize toàn bộ object từ đầu, có thể cần buffer token.

Jackson có TokenBuffer để giữ token trong bộ nhớ và tạo parser mới đọc lại chúng. Đây là một biểu diễn trung gian, nhưng nó có mục đích cụ thể: cho phép replay token mà không cần serialize thành JSON text.

Sử dụng TokenBuffer khi:
- Một phần của pipeline cần xem trước token.
- Sau đó cần replay cùng token stream.
- Không thể đọc lại nguồn ban đầu.
- Không muốn tạo String JSON trung gian.

Không dùng TokenBuffer nếu có thể:
- Đọc discriminator và chọn subtype bằng @JsonTypeInfo chuẩn.
- Dùng một custom deserializer điều phối việc đọc.
- Đọc trực tiếp nguồn thành kiểu đích.
- Lưu một vài giá trị nhỏ thay vì toàn bộ token stream.

TokenBuffer vẫn dùng bộ nhớ theo số lượng và kích thước token. Nó không phải cơ chế zero-copy.

## 16. Chọn giữa POJO, JsonNode, Map và streaming parser

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Schema cố định, kiểu đích rõ | POJO + ObjectReader | Data binding trực tiếp và type safety |
| JSON động, cần sửa cấu trúc | JsonNode | Truy cập và biến đổi cây thuận tiện |
| Field động theo key/value | Map | Không cần model cố định |
| File rất lớn, xử lý từng record | JsonParser + ObjectReader | Không giữ toàn bộ document |
| Output lớn hoặc tạo token từng phần | JsonGenerator | Ghi tuần tự ra stream |
| Chuyển object Java sang DTO tương thích | convertValue hoặc mapper chuyên dụng | Không cần textual JSON round trip |
| Chuyển JsonNode sang POJO | treeToValue | Không tạo String trung gian |
| Cần replay token đã đọc | TokenBuffer | Giữ token stream trong bộ nhớ |

Không nên chọn streaming chỉ vì nghe nói nó nhanh. Nếu payload nhỏ và POJO đơn giản, readValue thường vừa ngắn vừa hiệu quả. Streaming chỉ đáng dùng khi cần kiểm soát bộ nhớ, xử lý tuần tự hoặc định dạng có kích thước lớn.

## 17. Đo hiệu năng thay vì suy đoán

Một cách chuyển đổi ít bước hơn thường giảm allocation, nhưng mức cải thiện thực tế phụ thuộc:
- Kích thước payload.
- Độ sâu object graph.
- Số lượng field.
- Serializer/deserializer tùy chỉnh.
- Cấu hình mapper.
- Tốc độ nguồn và đích.
- Tần suất request.
- Chi phí xử lý nghiệp vụ sau deserialize.

Không nên kết luận chỉ từ số dòng code hoặc một lần chạy local.

### 17.1. So sánh các pipeline tương đương

Một benchmark có thể so sánh:

1. readValue trực tiếp từ byte[] hoặc InputStream.
2. readTree rồi treeToValue.
3. readTree, convertValue sang Map rồi convertValue sang DTO.
4. String parse lại từ JSON đã serialize.
5. Parser streaming cho file chứa nhiều record.

Đảm bảo mỗi phương án tạo cùng kết quả và thực hiện cùng validation/nghiệp vụ. Nếu một phương án bỏ qua công việc mà phương án khác thực hiện, phép so sánh không công bằng.

### 17.2. Dùng JMH cho microbenchmark

JMH phù hợp để đo throughput, latency và allocation trong một JVM có warmup/fork được kiểm soát.

Các nguyên tắc:
- Dùng payload đại diện cho production.
- Warmup trước khi đo.
- Chạy nhiều fork để giảm ảnh hưởng trạng thái JVM.
- Dùng Blackhole hoặc trả kết quả để tránh dead-code elimination.
- Đo allocation rate và GC, không chỉ thời gian.
- Giữ mapper configuration giống nhau.
- Tách chi phí parse, convert và business processing nếu cần.

Không dùng một vòng lặp System.nanoTime đơn giản làm kết luận cuối cùng. JIT compilation, GC, CPU scaling và cache có thể làm kết quả sai lệch.

### 17.3. Đo end-to-end

Microbenchmark cho biết chi phí của một đoạn code. Production còn có network, database, validation, logging, serialization response và concurrency.

Sau khi tối ưu cục bộ, hãy quan sát:
- Throughput.
- p50/p95/p99 latency.
- Heap allocation.
- GC frequency và pause.
- Payload size.
- CPU utilization.
- Số request đồng thời.

Một pipeline parse nhanh hơn chưa chắc cải thiện đáng kể thời gian request nếu database mới là bottleneck.

## 18. Những trường hợp biểu diễn trung gian là lựa chọn đúng

Không nên loại bỏ mọi bước trung gian. Có những yêu cầu khiến JsonNode, Map, byte[] hoặc TokenBuffer trở thành lựa chọn hợp lý.

**JsonNode** phù hợp khi schema động, cần sửa tree, kiểm tra cấu trúc tùy biến hoặc giữ field chưa biết.

**Map** phù hợp khi làm việc với extension data hoặc API nhận key/value động.

**byte[]** phù hợp khi cần ký trên bytes gốc, retry cùng payload, truyền cho API binary hoặc lưu buffer có giới hạn.

**String** phù hợp khi contract yêu cầu text, cần hiển thị hoặc chuyển cho API chỉ nhận chuỗi.

**TokenBuffer** phù hợp khi cần replay token stream mà không thể đọc lại nguồn.

Hãy hỏi: biểu diễn này mang lại khả năng nào mà đường đi trực tiếp không cung cấp? Nếu không có câu trả lời cụ thể, có thể đang tạo một bước trung gian không cần thiết.

## 19. Những lưu ý khi dùng stream

Đọc trực tiếp từ InputStream giúp tránh buffer trung gian do ứng dụng tự tạo, nhưng cần quản lý tài nguyên và lỗi đúng cách.

- Quy định rõ ai sở hữu và đóng InputStream/OutputStream.
- Không đọc lại một stream đã tiêu thụ trừ khi nguồn hỗ trợ reset/seek hoặc dữ liệu đã được buffer có chủ đích.
- Đặt giới hạn kích thước request, số record và độ sâu JSON.
- Xử lý EOF và JSON bị cắt cụt.
- Không giả định stream luôn có sẵn toàn bộ payload ngay lập tức.
- Nếu cần retry, thiết kế nguồn replayable hoặc lưu buffer có giới hạn.
- Không giữ parser/generator lâu hơn vòng đời request nếu không cần.

Trong web framework, để framework quản lý body stream thường an toàn hơn việc tự đọc body nhiều lần trong filter và controller.

## 20. Quy trình đơn giản hóa pipeline Jackson

Khi gặp code có nhiều bước chuyển đổi, hãy lần theo đường đi của payload:

1. Xác định nguồn dữ liệu ban đầu: bytes, stream, Reader hay String.
2. Xác định kiểu đích cuối cùng và schema có cố định không.
3. Ghi lại mọi bước tạo String, byte[], JsonNode, Map hoặc TokenBuffer.
4. Với schema cố định, thử readValue trực tiếp vào DTO.
5. Với object Java trong bộ nhớ, cân nhắc convertValue hoặc mapping tường minh thay cho JSON text round trip.
6. Với JsonNode đã có, dùng treeToValue nếu cần chuyển node sang POJO.
7. Với output stream, dùng writeValue thay cho writeValueAsString rồi encode bytes.
8. Với file lớn, xử lý token hoặc record theo streaming.
9. Chỉ giữ biểu diễn trung gian khi cần inspect, transform, replay hoặc forward dữ liệu.
10. Tái sử dụng ObjectMapper và reader/writer đã cấu hình.
11. Đo allocation, GC và latency trên payload thực tế.
12. Kiểm tra lại error handling, validation, resource ownership và tương thích dữ liệu sau thay đổi.

## 21. Các anti-pattern thường gặp

| Anti-pattern | Chi phí hoặc rủi ro | Cách đơn giản hơn |
|---|---|---|
| readTree rồi treeToValue ngay lập tức | Tạo toàn bộ cây rồi tạo POJO | readValue trực tiếp |
| writeValueAsString rồi readValue | Serialize, encode, parse lại | convertValue hoặc mapping tường minh |
| writeValueAsString rồi getBytes | Tạo String và byte[] | writeValue(OutputStream, value) |
| readAllBytes rồi tạo String rồi parse | Giữ nhiều bản sao payload | readValue(InputStream, Type) |
| POJO sang Map chỉ để gọi getter | Tạo Map và boxing | Dùng getter |
| ObjectMapper mới trong mỗi request | Lặp cấu hình và mất cache | Tái sử dụng mapper |
| Parse request hai lần | Đọc và materialize payload lặp lại | Deserialize một lần rồi validate DTO |
| JsonNode chỉ để đọc field cố định | Tạo tree không cần thiết | DTO hoặc JsonParser |
| readAll cho file rất lớn | Giữ toàn bộ record trong heap | Duyệt tuần tự |
| Custom tree rewrite cho format cố định | Tạo tree và vòng lặp hậu xử lý | DTO hoặc custom serializer |

## 22. Những điểm cần nhớ

- Đường đi trực tiếp từ InputStream/Reader đến POJO thường phù hợp khi schema đã biết.
- Ghi trực tiếp bằng ObjectWriter hoặc ObjectMapper vào OutputStream giúp tránh String và byte[] trung gian.
- Không serialize rồi deserialize lại cùng object chỉ để chuyển kiểu; cân nhắc convertValue hoặc mapping tường minh.
- convertValue tránh textual JSON round trip nhưng vẫn thực hiện chuyển đổi qua token buffer nội bộ, không phải zero-copy.
- treeToValue chuyển JsonNode đã có thành POJO mà không cần serialize node thành String.
- valueToTree vẫn phải duyệt object và tạo tree; dùng khi cần thao tác cấu trúc JSON.
- JsonNode phù hợp với schema động, tree transformation và extension fields.
- JsonParser/JsonGenerator phù hợp với streaming và xử lý dữ liệu lớn.
- MappingIterator hoặc parser loop giúp tránh giữ toàn bộ file trong List.
- TokenBuffer chỉ nên dùng khi cần replay token stream.
- Tái sử dụng ObjectMapper sau khi cấu hình; dùng ObjectReader/ObjectWriter cho kiểu và contract cụ thể.
- Streaming giảm nhu cầu giữ toàn bộ document nhưng không loại bỏ mọi allocation.
- Đừng tối ưu chỉ dựa trên cảm giác; đo throughput, latency, allocation và GC với dữ liệu đại diện.
- Chỉ loại bỏ biểu diễn trung gian khi nó không cung cấp giá trị cần thiết cho xử lý.

Tối ưu pipeline Jackson bắt đầu bằng việc nhìn rõ dữ liệu đang đi qua những biểu diễn nào. Nếu schema đã biết, hãy đọc thẳng vào DTO và ghi thẳng ra stream. Nếu cần cấu trúc động, dùng JsonNode một lần và thao tác trên cây đó. Nếu cần xử lý dữ liệu lớn, dùng parser/generator theo kiểu streaming. Khi mỗi biểu diễn được tạo vì một lý do cụ thể, ứng dụng giảm allocation và công việc parse/serialize lặp lại mà vẫn giữ code dễ hiểu, an toàn và đúng hợp đồng.

