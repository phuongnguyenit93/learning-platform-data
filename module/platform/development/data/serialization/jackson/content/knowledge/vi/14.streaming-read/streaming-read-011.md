# Quản lý parser và vòng đời nguồn dữ liệu

Jackson Streaming API đọc JSON theo từng token thông qua JsonParser. Cách này phù hợp khi file lớn, luồng dữ liệu liên tục hoặc ứng dụng chỉ cần xử lý một phần payload mà không muốn tạo toàn bộ cây JsonNode hay object graph trong bộ nhớ.

Khi làm việc theo luồng, cần quản lý hai vòng đời riêng biệt:

- **Vòng đời parser:** parser được tạo khi bắt đầu đọc, giữ trạng thái token trong lúc xử lý và phải được đóng khi hoàn tất hoặc khi có lỗi.
- **Vòng đời nguồn dữ liệu:** InputStream, Reader, file hoặc HTTP body có chủ sở hữu riêng. Đóng parser có thể đồng thời đóng nguồn bên dưới tùy cấu hình và cách tạo parser.

Hiểu đúng mối quan hệ này giúp tránh rò rỉ file/socket, đóng nhầm HTTP body, giữ tài nguyên quá lâu hoặc vô tình dừng một pipeline vẫn cần sử dụng nguồn dữ liệu.

## 1. JsonParser nằm ở đâu trong luồng đọc JSON?

JsonParser là API cấp thấp của Jackson Core. Nó đọc dữ liệu và phát ra các token theo thứ tự xuất hiện trong JSON. ObjectMapper/Databind có thể sử dụng parser để ánh xạ token thành Java object.

Ví dụ JSON:

~~~json
{
  "id": 1001,
  "name": "An",
  "active": true,
  "tags": ["java", "jackson"]
}
~~~

Parser sẽ lần lượt cung cấp các token tương ứng:

~~~text
START_OBJECT
FIELD_NAME("id")
VALUE_NUMBER_INT(1001)
FIELD_NAME("name")
VALUE_STRING("An")
FIELD_NAME("active")
VALUE_TRUE
FIELD_NAME("tags")
START_ARRAY
VALUE_STRING("java")
VALUE_STRING("jackson")
END_ARRAY
END_OBJECT
~~~

Luồng tổng quát:

~~~text
File / InputStream / Reader
            |
            v
         JsonFactory
            |
            v
         JsonParser
            |
            +---- nextToken()
            |
            +---- đọc field/value
            |
            +---- skipChildren()
            |
            v
      xử lý từng record
            |
            v
        đóng parser
            |
            v
      giải phóng nguồn theo policy
~~~

JsonFactory tạo parser và có thể được tái sử dụng. JsonParser gắn với một nguồn dữ liệu cụ thể, chứa trạng thái đọc và không nên được dùng đồng thời cho nhiều request.

## 2. Tạo parser từ các loại nguồn khác nhau

Thông thường lấy JsonFactory từ ObjectMapper đang được ứng dụng sử dụng:

~~~java
JsonFactory factory = mapper.getFactory();
~~~

Cách này giúp parser dùng chung cấu hình factory của mapper, chẳng hạn các feature ở cấp streaming, symbol table và cấu hình liên quan.

### 2.1. Đọc trực tiếp từ File

Nếu Jackson có thể mở và quản lý file, tạo parser từ File:

~~~java
Path path = Path.of("data/orders.json");

try (JsonParser parser = mapper.getFactory()
        .createParser(path.toFile())) {
    // Đọc token và xử lý dữ liệu.
}
~~~

Parser được tạo cho file này và được đóng khi khối try kết thúc. Nguồn file do Jackson mở được quản lý cùng vòng đời parser.

Đây là lựa chọn gọn khi toàn bộ thao tác đọc thuộc về parser. Không cần tự mở thêm FileInputStream nếu không có lý do cần kiểm soát stream riêng.

### 2.2. Đọc từ InputStream do ứng dụng mở

Khi ứng dụng mở stream, ứng dụng thường là chủ sở hữu nguồn:

~~~java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);

    // Đọc và xử lý dữ liệu.
}
~~~

Thứ tự đóng tài nguyên của try-with-resources là ngược với thứ tự khai báo:

1. Parser được đóng trước.
2. InputStream được đóng sau.

AUTO_CLOSE_SOURCE được tắt để parser không tự đóng stream. Ứng dụng vẫn đóng stream trong khối try bên ngoài.

Cách này hữu ích khi stream còn được quản lý bởi một thành phần khác hoặc cần bảo đảm chính lớp mở stream chịu trách nhiệm đóng nó.

### 2.3. Đọc từ Reader

Nếu nguồn đã là ký tự, có thể tạo parser từ Reader:

~~~java
try (Reader reader = Files.newBufferedReader(
         path, StandardCharsets.UTF_8);
     JsonParser parser = mapper.getFactory().createParser(reader)) {

    parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);

    // Đọc token.
}
~~~

Reader cần dùng encoding đúng với dữ liệu. JSON thường được truyền dưới dạng UTF-8; nếu tự tạo Reader, hãy xác định charset rõ ràng thay vì phụ thuộc encoding mặc định của máy.

### 2.4. Đọc từ String

Với JSON nhỏ đã có trong bộ nhớ, có thể tạo parser từ String:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    // Đọc token.
}
~~~

Không có InputStream bên ngoài để caller đóng, nhưng parser vẫn cần được đóng để kết thúc vòng đời xử lý và giải phóng tài nguyên nội bộ.

Nếu mục tiêu chỉ là ánh xạ một JSON document nhỏ thành DTO, mapper.readValue(String, Type.class) hoặc readTree(String) thường đơn giản hơn việc tự quản lý parser.

## 3. Vòng đời parser: tạo, đọc, kết thúc và đóng

Một parser thường đi qua các bước:

1. Tạo parser từ JsonFactory và nguồn dữ liệu.
2. Đọc token đầu tiên bằng nextToken().
3. Xác định cấu trúc JSON và xử lý token.
4. Đọc tiếp cho đến khi hoàn tất document hoặc phần dữ liệu cần thiết.
5. Đóng parser trong mọi đường đi, kể cả khi có exception.

Ví dụ:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(file)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        // Xử lý token hiện tại.
    }
}
~~~

nextToken() trả token tiếp theo hoặc null khi hết nội dung. Không nên giả định file luôn có một JSON object; token đầu tiên có thể là START_ARRAY, START_OBJECT hoặc một scalar tùy hợp đồng.

### 3.1. Parser có trạng thái

JsonParser giữ vị trí hiện tại trong nguồn dữ liệu. Một số phương thức quan trọng:

| Phương thức | Vai trò |
|---|---|
| nextToken() | Chuyển đến token tiếp theo |
| currentToken() | Lấy token hiện tại |
| currentName() | Lấy tên field hiện tại nếu đang ở ngữ cảnh field |
| getText() | Lấy nội dung dạng text của token hiện tại |
| getIntValue()/getLongValue() | Đọc giá trị số nguyên |
| getDecimalValue() | Đọc số dưới dạng BigDecimal |
| getBooleanValue() | Đọc boolean |
| skipChildren() | Bỏ qua toàn bộ nội dung object/array con |
| getCurrentLocation() | Lấy vị trí hiện tại trong nguồn |
| isClosed() | Kiểm tra parser đã đóng hay chưa |
| close() | Đóng parser và áp dụng chính sách đóng nguồn |

Các phương thức lấy value phải được gọi ở token phù hợp. Ví dụ getIntValue() cần token số nguyên hoặc dạng mà parser hỗ trợ chuyển đổi; gọi trên FIELD_NAME hoặc START_OBJECT sẽ gây lỗi.

### 3.2. Không gọi nextToken() tùy tiện

Mỗi lần gọi nextToken() sẽ làm parser tiến lên. Nếu code helper tự gọi thêm một lần mà caller cũng gọi tiếp, có thể bỏ qua token hoặc record.

Ví dụ cấu trúc array:

~~~java
if (parser.nextToken() != JsonToken.START_ARRAY) {
    throw new IOException("Expected an array");
}

while (parser.nextToken() != JsonToken.END_ARRAY) {
    // Parser đang ở đầu một phần tử.
    // Xử lý phần tử hiện tại.
}
~~~

Nếu phần tử là object, parser đang ở START_OBJECT. Nếu phần tử là scalar, parser đang ở token scalar tương ứng.

Hãy quy định rõ method nào chịu trách nhiệm tiến parser đến token tiếp theo. Điều này đặc biệt quan trọng khi tách code đọc thành nhiều helper.

## 4. Đọc từng object trong JSON array

Một ứng dụng thường nhận file chứa danh sách record:

~~~json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"},
  {"id": 3, "name": "Chi"}
]
~~~

Có thể dùng JsonParser để đọc từng object và nhờ ObjectMapper ánh xạ object hiện tại thành DTO:

~~~java
public void processUsers(
    Path path,
    ObjectMapper mapper,
    Consumer<User> handler
) throws IOException {

    try (JsonParser parser = mapper.getFactory()
            .createParser(path.toFile())) {

        if (parser.nextToken() != JsonToken.START_ARRAY) {
            throw new IOException("Expected a JSON array");
        }

        while (parser.nextToken() != JsonToken.END_ARRAY) {
            User user = mapper.readValue(parser, User.class);
            handler.accept(user);
        }
    }
}
~~~

Ở vòng lặp, nextToken() đưa parser đến token bắt đầu của phần tử kế tiếp. mapper.readValue(parser, User.class) đọc phần tử hiện tại thành User. Khi phần tử là object, databind tiêu thụ cấu trúc object đó; vòng lặp tiếp tục với token tiếp theo.

Lợi ích:

- Không cần tạo List<User> chứa toàn bộ file.
- Có thể ghi từng record vào database hoặc xử lý ngay.
- Bộ nhớ chủ yếu phụ thuộc vào một record và phần buffer parser.
- Dễ dừng sớm nếu đã tìm thấy dữ liệu cần thiết.

Nếu handler ghi database, hãy thiết kế batch/transaction phù hợp. Streaming giúp giảm bộ nhớ nhưng không tự quyết định cách commit, retry hoặc xử lý lỗi từng record.

## 5. Dùng skipChildren() để bỏ qua phần không cần thiết

Khi chỉ cần một số field, không cần ánh xạ toàn bộ object. Parser có thể bỏ qua một object hoặc array lồng nhau bằng skipChildren().

Ví dụ:

~~~json
{
  "id": 1001,
  "debugPayload": {
    "large": ["many", "values"]
  },
  "status": "READY"
}
~~~

Nếu không cần debugPayload:

~~~java
while (parser.nextToken() != JsonToken.END_OBJECT) {
    if (parser.currentToken() != JsonToken.FIELD_NAME) {
        throw new IOException("Expected a field name");
    }

    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if ("id".equals(fieldName)) {
        long id = parser.getLongValue();
    } else if ("status".equals(fieldName)) {
        String status = parser.getValueAsString();
    } else {
        parser.skipChildren();
    }
}
~~~

skipChildren() hữu ích khi value hiện tại là START_OBJECT hoặc START_ARRAY. Với scalar, không có subtree cần bỏ qua.

Khi viết parser thủ công, cần giữ đúng trạng thái token. Nếu bỏ qua một field, skipChildren() đưa parser đến token kết thúc của subtree; vòng lặp bên ngoài sẽ gọi nextToken() để tiếp tục.

## 6. Ai sở hữu parser và ai sở hữu nguồn dữ liệu?

Có hai tài nguyên khác nhau:

- JsonParser được tạo bởi code nào thì code đó cần có trách nhiệm đóng parser.
- InputStream/Reader được mở bởi ai hoặc được chuyển giao theo hợp đồng nào thì chủ sở hữu đó chịu trách nhiệm đóng nguồn.

Có thể chọn một trong hai mô hình chính:

### 6.1. Parser sở hữu nguồn

Dùng khi parser được tạo từ File hoặc khi caller chuyển giao quyền đóng stream cho parser.

~~~java
try (JsonParser parser = mapper.getFactory().createParser(file)) {
    // Parser đọc file.
}
~~~

Khi parser đóng, nguồn do Jackson quản lý được đóng theo vòng đời parser.

Với InputStream do caller cung cấp, AUTO_CLOSE_SOURCE mặc định bật trong Jackson 2.x. Do đó, khi parser được đóng, stream bên dưới thường cũng được đóng. Nếu chọn mô hình chuyển giao này, caller không được tiếp tục dùng stream sau khi parser kết thúc.

### 6.2. Caller sở hữu nguồn

Dùng khi ứng dụng cần kiểm soát stream:

~~~java
try (InputStream input = openInput();
     JsonParser parser = mapper.getFactory().createParser(input)) {

    parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);
    readDocument(parser);
}
~~~

Parser được đóng trước, nhưng không đóng input. Caller đóng input sau đó.

Đây là mô hình phù hợp khi nguồn thuộc về một pipeline lớn hơn, một wrapper hoặc một thành phần quản lý tài nguyên bên ngoài.

### 6.3. Không bỏ đóng parser khi giữ nguồn mở

Tắt AUTO_CLOSE_SOURCE chỉ thay đổi việc đóng nguồn bên dưới. Nó không loại bỏ trách nhiệm đóng parser.

Parser có thể giữ buffer, trạng thái đọc và tài nguyên nội bộ. Hãy đóng parser khi hoàn tất dù stream vẫn được caller giữ mở.

Tương tự, không nên để parser sống lâu hơn nguồn dữ liệu. Nếu caller đóng stream trước khi parser kết thúc, lần đọc tiếp theo có thể thất bại.

## 7. AUTO_CLOSE_SOURCE và cấu hình đóng nguồn

Jackson 2.x có JsonParser.Feature.AUTO_CLOSE_SOURCE. Feature này bật việc đóng InputStream hoặc Reader bên dưới khi parser được đóng.

~~~java
JsonParser parser = mapper.getFactory().createParser(input);

parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);
~~~

Có thể cấu hình ở cấp JsonFactory trong các phiên bản hỗ trợ StreamReadFeature:

~~~java
JsonFactory factory = JsonFactory.builder()
    .disable(StreamReadFeature.AUTO_CLOSE_SOURCE)
    .build();
~~~

Sau đó tạo mapper hoặc parser dùng factory đó:

~~~java
ObjectMapper mapper = new ObjectMapper(factory);
~~~

Một số điểm cần lưu ý:

- Feature trên parser/factory quyết định hành vi khi parser đóng.
- Việc tạo parser từ File có thể đánh dấu nguồn do Jackson quản lý; Jackson sẽ đóng tài nguyên mà nó tự mở.
- InputStream/Reader truyền từ bên ngoài có thể được đóng theo AUTO_CLOSE_SOURCE mặc định.
- Tắt feature không làm parser tự động đóng nguồn sau khi đọc xong; caller phải đóng nguồn.
- Không thay đổi cấu hình factory dùng chung theo từng request. Nếu cần policy khác, tạo factory/mapper có cấu hình riêng hoặc cấu hình parser cụ thể trước khi sử dụng.

StreamReadFeature là API cấu hình mới hơn so với JsonParser.Feature trong một số dòng Jackson 2. Hãy dùng API phù hợp với phiên bản dependency của dự án và tránh trộn ví dụ giữa các phiên bản mà chưa kiểm tra compile.

## 8. Đọc một phần dữ liệu rồi dừng

Có thể dừng parser khi đã tìm thấy record cần thiết:

~~~java
public Optional<User> findUser(Path path, long targetId)
        throws IOException {

    try (JsonParser parser = mapper.getFactory()
            .createParser(path.toFile())) {

        if (parser.nextToken() != JsonToken.START_ARRAY) {
            throw new IOException("Expected array");
        }

        while (parser.nextToken() != JsonToken.END_ARRAY) {
            User user = mapper.readValue(parser, User.class);

            if (user.id() == targetId) {
                return Optional.of(user);
            }
        }

        return Optional.empty();
    }
}
~~~

Khi return bên trong try-with-resources, parser vẫn được đóng. Nguồn file do parser quản lý cũng được kết thúc theo chính sách đóng.

Dừng sớm giúp tiết kiệm thời gian và I/O, nhưng không kiểm tra phần còn lại của JSON. Nếu ứng dụng phải xác nhận toàn bộ document hợp lệ, cần đọc đến cuối hoặc có bước validation riêng.

Nếu dừng giữa một record hoặc giữa một subtree, không tái sử dụng parser như thể nó đang ở ranh giới record. Muốn tiếp tục, phải biết chính xác trạng thái token hiện tại và cấu trúc còn lại.

## 9. Xử lý lỗi trong quá trình đọc

Lỗi có thể xuất hiện khi:

- File không tồn tại hoặc không đọc được.
- Stream bị đóng từ bên ngoài.
- JSON sai cú pháp hoặc bị cắt giữa chừng.
- Token có kiểu không đúng với code đang đọc.
- Deserializer của DTO ném lỗi.
- Consumer/handler xử lý record thất bại.
- Nguồn dữ liệu bị ngắt hoặc network timeout.

Try-with-resources bảo đảm parser được đóng khi có exception:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    readRecords(parser);
} catch (JsonProcessingException ex) {
    throw new InvalidImportFileException(
        "The JSON document is invalid",
        ex
    );
} catch (IOException ex) {
    throw new ImportReadException(
        "Could not read the input source",
        ex
    );
}
~~~

JsonProcessingException là nhánh lỗi xử lý JSON, còn IOException có thể đại diện lỗi I/O. Tùy API và phiên bản, các exception này có quan hệ kế thừa; hãy đặt catch theo thứ tự cụ thể trước tổng quát nếu cần xử lý riêng.

Không nên bắt Exception rồi bỏ qua. Nếu một record lỗi, quyết định rõ:

- Dừng toàn bộ import.
- Ghi nhận lỗi record và tiếp tục record sau nếu parser còn ở trạng thái có thể phục hồi.
- Đưa payload lỗi vào vùng cách ly để xử lý lại.
- Rollback batch/transaction đã xử lý.

Không phải mọi lỗi parse đều có thể phục hồi. JSON sai cú pháp giữa một object có thể khiến parser không thể tìm ranh giới record an toàn. Không nên tự dò chuỗi tiếp theo bằng cách bỏ qua byte ngẫu nhiên.

## 10. Nguồn dữ liệu do framework quản lý

Không phải stream nào cũng do code ứng dụng mở. Với HTTP, framework thường kiểm soát vòng đời body.

### 10.1. Spring MVC và Servlet InputStream

Trong Spring MVC, HttpMessageConverter thường đọc request body và đóng/hoàn tất vòng đời chuyển đổi theo cơ chế của framework. Controller thông thường nên nhận DTO qua @RequestBody.

Nếu filter hoặc adapter cần đọc raw body, cần tuân theo hợp đồng của Servlet API và wrapper được sử dụng. Khi truyền HttpServletRequest.getInputStream() vào JsonParser, cần quyết định parser có được phép đóng stream hay không.

Ví dụ parser không đóng stream container-managed:

~~~java
JsonParser parser = mapper.getFactory()
    .createParser(request.getInputStream());

parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);

try (parser) {
    // Đọc dữ liệu theo hợp đồng của filter/adapter.
}
~~~

Không nên tự đóng request stream trong controller nếu framework còn cần xử lý request. Với request body đã bị tiêu thụ, cũng không thể mặc định rằng controller hoặc converter khác có thể đọc lại từ đầu.

### 10.2. Spring WebFlux và DataBuffer

WebFlux dùng DataBuffer và codec trong pipeline reactive. Buffer có thể được quản lý theo reference counting và cần được release đúng thời điểm.

Không chuyển DataBuffer thành InputStream rồi đóng tùy tiện nếu pipeline vẫn còn dùng buffer. Khi viết custom decoder, hãy tuân thủ hợp đồng cấp phát/release của DataBuffer và xử lý cả lỗi lẫn cancellation.

Với luồng thông thường, để Jackson decoder do Spring quản lý là lựa chọn đơn giản nhất.

### 10.3. WebClient response body

Khi dùng WebClient, nên để codec chuyển JSON thành DTO:

~~~java
Mono<OrderResponse> result = webClient.get()
    .uri("/orders/{id}", orderId)
    .retrieve()
    .bodyToMono(OrderResponse.class);
~~~

Nếu truy cập raw response hoặc body stream, cần tiêu thụ hoặc release body theo API WebClient. Bỏ qua body có thể làm giữ connection hoặc buffer. Đừng tự đóng tài nguyên bên dưới khi reactive pipeline còn đang sử dụng.

## 11. Nhiều document hoặc nhiều record trong cùng một nguồn

Một JSON document chuẩn có một root value. Một số định dạng streaming có thể chứa nhiều root value liên tiếp, nhưng đó phải là giao thức được producer và consumer thống nhất.

Các dạng framing thường gặp:

- Một JSON array chứa nhiều record.
- JSON Lines: mỗi dòng là một JSON document riêng.
- Nhiều root JSON value liên tiếp theo quy ước riêng.
- Một định dạng bao ngoài có length prefix hoặc delimiter.

Nếu nguồn là một JSON array, đọc START_ARRAY, từng phần tử và END_ARRAY như ví dụ trước.

Nếu nguồn là JSON Lines, có thể đọc từng dòng bằng BufferedReader rồi tạo parser/mapper cho từng dòng, hoặc dùng cơ chế streaming phù hợp. Khi đọc từng dòng, cần giới hạn độ dài dòng và xử lý dòng rỗng theo hợp đồng.

Không nên giả định nhiều object nối tiếp không có delimiter là một JSON document hợp lệ. Parser có thể hỗ trợ đọc multiple root values trong một số cấu hình, nhưng consumer vẫn cần biết ranh giới record và cách xử lý lỗi.

## 12. MappingIterator và vòng đời parser

ObjectMapper/ObjectReader có thể đọc nhiều value từ một JsonParser thông qua MappingIterator. Cách này hữu ích khi nguồn chứa nhiều root value theo giao thức đã xác định.

Ví dụ khung:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input);
     MappingIterator<User> users =
         mapper.readerFor(User.class).readValues(parser)) {

    while (users.hasNextValue()) {
        User user = users.nextValue();
        process(user);
    }
}
~~~

Khi dùng MappingIterator, cần hiểu rõ ai sở hữu parser. Một số cách tạo iterator có thể được cấu hình để đóng parser khi iterator đóng; nếu parser cũng được khai báo riêng trong try-with-resources, cần kiểm soát việc đóng lặp và ownership theo API cụ thể của phiên bản đang dùng.

Cách đơn giản là chọn một chủ sở hữu duy nhất cho parser và để iterator tuân theo hợp đồng đó. Nếu cần caller giữ nguồn mở, tắt AUTO_CLOSE_SOURCE trên parser trước khi tạo iterator và vẫn đóng parser/iterator theo đúng API.

Đối với một JSON array thông thường, vòng lặp token thủ công hoặc đọc một List<T> có thể rõ ràng hơn MappingIterator. Chọn API theo framing của dữ liệu.

## 13. Giới hạn tài nguyên khi đọc nguồn không tin cậy

Streaming giúp giảm nhu cầu giữ toàn bộ document trong RAM, nhưng không tự động bảo vệ ứng dụng khỏi payload quá lớn hoặc độc hại.

Cần xem xét:

- Giới hạn tổng kích thước request/file.
- Giới hạn số record và số phần tử trong array.
- Giới hạn độ sâu lồng nhau.
- Giới hạn kích thước string hoặc binary field.
- Timeout khi đọc từ network.
- Chính sách xử lý token không mong đợi.
- Giới hạn thời gian xử lý từng record.
- Hành vi khi handler chậm hơn tốc độ nguồn dữ liệu.

Jackson có các giới hạn stream read constraints trong những phiên bản hỗ trợ, có thể cấu hình qua StreamReadConstraints, chẳng hạn độ sâu lồng nhau và độ dài chuỗi/number. Ngoài giới hạn parser, ứng dụng vẫn cần giới hạn request ở HTTP server, gateway hoặc tầng upload.

Ví dụ cấu hình giới hạn đọc trong các phiên bản Jackson 2 có hỗ trợ:

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
~~~

Các con số trên chỉ là ví dụ minh họa. Chọn giới hạn theo payload thực tế và phiên bản Jackson; không sao chép máy móc vào production.

## 14. Không chia sẻ parser giữa nhiều luồng

ObjectMapper và JsonFactory thường được cấu hình xong rồi tái sử dụng. JsonParser thì khác: nó có vị trí đọc, token hiện tại và trạng thái gắn với một nguồn cụ thể.

Không làm:

~~~java
static JsonParser sharedParser;
~~~

Hai request dùng chung parser có thể làm vị trí đọc của nhau bị thay đổi, gây mất token, dữ liệu lẫn lộn hoặc lỗi khó tái hiện.

Quy tắc:

- Một nguồn đọc có parser riêng.
- Một parser chỉ được một luồng xử lý điều khiển tại một thời điểm.
- Không giữ parser trong singleton để phục vụ nhiều request.
- Đóng parser ngay khi thao tác đọc kết thúc.
- Có thể tái sử dụng mapper/factory đã cấu hình, không tái sử dụng parser đã đóng.

## 15. Kiểm thử vòng đời parser và nguồn

Không chỉ test dữ liệu trả về. Nên test xem nguồn có được đóng đúng theo policy hay không.

Có thể tạo InputStream ghi nhận trạng thái close:

~~~java
class TrackingInputStream extends ByteArrayInputStream {

    private boolean closed;

    TrackingInputStream(byte[] data) {
        super(data);
    }

    @Override
    public void close() throws IOException {
        closed = true;
        super.close();
    }

    boolean isClosed() {
        return closed;
    }
}
~~~

Test caller giữ quyền sở hữu nguồn:

~~~java
@Test
void parserCanCloseWithoutClosingCallerOwnedSource() throws Exception {
    byte[] json = "{\"id\":1}".getBytes(StandardCharsets.UTF_8);
    TrackingInputStream input = new TrackingInputStream(json);

    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);
        while (parser.nextToken() != null) {
            // Đọc hết document.
        }
    }

    assertFalse(input.isClosed());

    input.close();
    assertTrue(input.isClosed());
}
~~~

Test parser đóng nguồn theo policy mặc định:

~~~java
@Test
void parserClosesSourceWhenAutoCloseSourceIsEnabled() throws Exception {
    byte[] json = "{\"id\":1}".getBytes(StandardCharsets.UTF_8);
    TrackingInputStream input = new TrackingInputStream(json);

    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        assertTrue(parser.isEnabled(JsonParser.Feature.AUTO_CLOSE_SOURCE));
        while (parser.nextToken() != null) {
            // Đọc hết document.
        }
    }

    assertTrue(input.isClosed());
}
~~~

Ngoài test close, cần test:

- Parser được đóng khi deserialize ném exception.
- Parser được đóng khi handler ném exception.
- Đọc hết file và dừng sớm đều giải phóng tài nguyên.
- Stream bị đóng từ bên ngoài tạo lỗi có thể xử lý.
- Nguồn bị cắt giữa document không được coi là thành công.
- Framework-managed stream không bị đóng sớm.
- Cancellation/timeout của pipeline reactive giải phóng buffer đúng hợp đồng.

Test vòng đời nên kiểm tra đúng chủ sở hữu. Không nên chỉ kiểm tra close() được gọi một lần nếu API cho phép wrapper đóng lặp; quan trọng là tài nguyên không bị rò rỉ và không bị đóng trước khi consumer hoàn tất.

## 16. Các lỗi quản lý parser thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không đóng parser | Buffer/tài nguyên giữ lâu, nguồn không được giải phóng | Dùng try-with-resources |
| Đóng stream trước parser | Lần đọc tiếp theo thất bại | Đóng parser trước, stream sau |
| Parser tự đóng stream của framework | Request/response pipeline bị kết thúc sớm | Tắt AUTO_CLOSE_SOURCE khi caller/framework sở hữu nguồn |
| Tắt auto-close nhưng quên đóng stream | Rò rỉ file/socket | Ghi rõ caller là chủ sở hữu và đóng ở lớp mở nguồn |
| Chia sẻ parser giữa request | Trạng thái token bị tranh chấp | Tạo parser riêng cho mỗi nguồn |
| Gọi nextToken() dư | Bỏ qua field hoặc record | Quy định rõ helper nào tiến parser |
| Dừng sớm rồi tái sử dụng parser sai trạng thái | Đọc nhầm phần còn lại | Chỉ tiếp tục khi biết ranh giới token |
| Bắt lỗi rồi tiếp tục trên parser hỏng | Dữ liệu sai hoặc mất đồng bộ | Dừng/đưa record vào quarantine theo framing |
| Dùng mapper mới cho mỗi record | Tốn chi phí và cấu hình không nhất quán | Tái sử dụng mapper, tạo parser riêng |
| Đọc file lớn thành String trước khi parse | Tốn bộ nhớ và mất lợi ích streaming | Tạo parser trực tiếp từ File/InputStream |

## 17. Quy trình thiết kế một luồng đọc

~~~text
Xác định nguồn và chủ sở hữu
             |
             v
Chọn File / InputStream / Reader
             |
             v
Tạo JsonParser từ JsonFactory
             |
             v
Chọn AUTO_CLOSE_SOURCE phù hợp
             |
             v
Đọc token theo cấu trúc JSON
             |
             v
Xử lý từng record hoặc subtree
             |
             v
Đọc đến hết hoặc dừng có chủ đích
             |
             v
Đóng parser
             |
             v
Đóng nguồn bởi đúng chủ sở hữu
~~~

Trước khi triển khai, cần trả lời:

- Nguồn do ứng dụng, Jackson hay framework mở?
- Parser có được phép đóng nguồn không?
- Parser được tạo ở đâu và ai đóng?
- Dữ liệu là một document, array, JSON Lines hay nhiều root value?
- Có thể dừng sớm không, và phần còn lại có cần kiểm tra không?
- Nếu lỗi giữa chừng, có thể tiếp tục hay phải hủy toàn bộ import?
- Có giới hạn kích thước, độ sâu, số record và timeout không?

## 18. Nguyên tắc nên giữ

1. Tạo một JsonParser riêng cho mỗi nguồn đọc.
2. Dùng try-with-resources để parser luôn được đóng.
3. Xác định rõ ai sở hữu InputStream/Reader.
4. Dùng AUTO_CLOSE_SOURCE theo ownership; không để parser đóng nguồn do framework quản lý.
5. Nếu tắt auto-close, caller phải đóng nguồn sau khi parser kết thúc.
6. Không đóng ObjectMapper sau mỗi thao tác; mapper/factory có thể được tái sử dụng.
7. Không chia sẻ parser giữa các request hoặc thread.
8. Giữ quy ước rõ ràng về token hiện tại và việc gọi nextToken().
9. Dùng skipChildren() khi cần bỏ qua subtree lớn.
10. Kiểm tra framing và ranh giới record trước khi đọc nhiều document.
11. Xử lý exception, timeout và cancellation để tài nguyên luôn được giải phóng.
12. Đặt giới hạn kích thước, độ sâu và số record cho nguồn không tin cậy.
13. Viết test xác nhận parser và nguồn được đóng đúng thời điểm.

Quản lý parser là quản lý cả trạng thái đọc lẫn quyền sở hữu nguồn dữ liệu. JsonParser phải được đóng sau khi hoàn tất, còn InputStream/Reader được đóng bởi thành phần có trách nhiệm theo hợp đồng. Khi dùng File do Jackson mở, parser thường có thể quản lý toàn bộ vòng đời; khi dùng stream do caller hoặc framework sở hữu, hãy cấu hình AUTO_CLOSE_SOURCE phù hợp và đóng nguồn ở đúng lớp. Một ownership rõ ràng giúp streaming vừa tiết kiệm bộ nhớ vừa an toàn trong ứng dụng chạy lâu dài.

