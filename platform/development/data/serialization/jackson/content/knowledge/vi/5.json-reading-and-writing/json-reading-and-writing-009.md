# Xác định chủ sở hữu tài nguyên và chính sách đóng luồng

Khi dùng Jackson để đọc hoặc ghi JSON, cần xác định rõ ai chịu trách nhiệm đóng tài nguyên như InputStream, OutputStream, Reader, Writer, JsonParser và JsonGenerator. Việc parse thành công chưa có nghĩa tài nguyên đã được giải phóng; ngược lại, một phương thức tiện ích có thể đóng luồng mà caller vẫn muốn sử dụng cho bước tiếp theo.

Trong Jackson 2.x, các overload nhận trực tiếp InputStream/OutputStream thường tự tạo và đóng parser/generator. Theo mặc định, parser và generator cũng có thể đóng nguồn hoặc đích bên dưới khi chính chúng được đóng. Vì vậy, quy tắc quan trọng là: **biết overload nào đang được gọi, biết ai sở hữu parser/generator, và chọn chính sách đóng source/target phù hợp với vòng đời của luồng.**

## 1. Những tài nguyên tham gia vào quá trình JSON

Jackson làm việc với nhiều lớp tài nguyên khác nhau:

| Tài nguyên | Vai trò | Ví dụ |
|---|---|---|
| InputStream | Đọc byte từ nguồn | File, HTTP body, socket, ZIP entry |
| Reader | Đọc ký tự từ nguồn | File text, StringReader |
| OutputStream | Ghi byte ra đích | File, HTTP response, socket |
| Writer | Ghi ký tự ra đích | File text, StringWriter |
| JsonParser | Đọc token JSON tuần tự | Đọc object, array, field và value |
| JsonGenerator | Ghi token JSON tuần tự | Ghi object, array, field và value |
| ObjectMapper | Điều phối serialization/deserialization | Chuyển JSON thành DTO và ngược lại |
| JsonFactory | Tạo parser và generator | Factory dùng chung cho mapper |

Cần phân biệt tài nguyên bên ngoài với đối tượng xử lý của Jackson:

~~~text
InputStream / Reader
        |
        v
    JsonParser
        |
        v
   ObjectMapper
        |
        v
      DTO


DTO
 |
 v
ObjectMapper
 |
 v
JsonGenerator
 |
 v
OutputStream / Writer
~~~

Đóng parser không giống đóng ObjectMapper. Parser là đối tượng xử lý một luồng đọc cụ thể; generator là đối tượng xử lý một luồng ghi cụ thể. ObjectMapper thường được cấu hình một lần và tái sử dụng trong ứng dụng, không đóng sau mỗi lần đọc/ghi.

## 2. Nguyên tắc xác định chủ sở hữu

Một tài nguyên cần có một chủ sở hữu chịu trách nhiệm kết thúc vòng đời của nó. Chủ sở hữu thường là thành phần mở tài nguyên hoặc thành phần mà hợp đồng API chuyển giao trách nhiệm đóng tài nguyên.

Ví dụ:

- Service mở file bằng Files.newInputStream thì service sở hữu stream và phải đóng nó.
- Một parser được tạo để đọc stream cần được đóng để giải phóng buffer và tài nguyên liên quan.
- Nếu parser được cấu hình tự đóng source, việc đóng parser cũng đóng InputStream bên dưới.
- Nếu Jackson tự tạo parser từ InputStream trong overload readValue(InputStream, ...), mapper quản lý vòng đời parser và parser mặc định đóng source.
- Nếu caller truyền JsonParser đã tạo sẵn vào readValue(JsonParser, ...), caller vẫn quản lý parser và phải đóng nó.
- Nếu framework tạo HTTP body stream, framework hoặc message converter thường là bên quản lý vòng đời; controller không nên tùy tiện đóng stream đó.

Không nên suy luận rằng "tôi truyền stream vào phương thức thì tôi vẫn luôn sở hữu stream". Một số API có hành vi đóng tài nguyên được truyền vào theo mặc định. Hãy đọc hợp đồng của overload cụ thể.

## 3. Chính sách tự đóng source và target của Jackson

Jackson 2.x có hai feature quan trọng:

| Feature | Đối tượng | Ý nghĩa | Mặc định |
|---|---|---|---|
| AUTO_CLOSE_SOURCE | JsonParser | Khi parser đóng, có đóng InputStream/Reader bên dưới hay không | Bật |
| AUTO_CLOSE_TARGET | JsonGenerator | Khi generator đóng, có đóng OutputStream/Writer bên dưới hay không | Bật |

Tên feature có thể được dùng qua JsonParser.Feature và JsonGenerator.Feature. Trong các phiên bản Jackson 2 mới hơn, có các enum StreamReadFeature.AUTO_CLOSE_SOURCE và StreamWriteFeature.AUTO_CLOSE_TARGET tương ứng ở cấp cấu hình factory.

### 3.1. AUTO_CLOSE_SOURCE

Khi AUTO_CLOSE_SOURCE bật, đóng JsonParser sẽ đóng InputStream hoặc Reader mà parser đang đọc.

Ví dụ:

~~~java
JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    // Đọc token hoặc deserialize dữ liệu.
}
~~~

Khi khối try kết thúc, parser được đóng. Theo cấu hình mặc định, inputStream bên dưới cũng được đóng.

Điều này phù hợp nếu parser được tạo để đọc một nguồn độc lập và parser chịu trách nhiệm kết thúc việc đọc nguồn đó.

Tuy nhiên, nếu InputStream thuộc về một thành phần khác hoặc cần tiếp tục được sử dụng, không nên để parser tự đóng source. Có thể tắt feature trên parser:

~~~java
JsonParser parser = mapper.getFactory().createParser(inputStream);
parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);

try (parser) {
    return mapper.readValue(parser, OrderRequest.class);
}
~~~

Trong ví dụ này, parser được đóng và giải phóng tài nguyên nội bộ, nhưng inputStream vẫn mở. Chủ sở hữu bên ngoài phải đóng inputStream khi hoàn tất.

### 3.2. AUTO_CLOSE_TARGET

Khi AUTO_CLOSE_TARGET bật, đóng JsonGenerator sẽ đóng OutputStream hoặc Writer bên dưới.

Ví dụ:

~~~java
JsonFactory factory = new JsonFactory();

try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    generator.writeStartObject();
    generator.writeStringField("status", "created");
    generator.writeEndObject();
}
~~~

Khi generator đóng, outputStream cũng được đóng theo mặc định.

Nếu outputStream thuộc về caller và cần tiếp tục sử dụng, hãy tắt AUTO_CLOSE_TARGET trên generator:

~~~java
JsonGenerator generator =
    mapper.getFactory().createGenerator(outputStream);

generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);

try (generator) {
    mapper.writeValue(generator, response);
}
~~~

Generator vẫn được đóng để hoàn tất thao tác ghi và giải phóng buffer; outputStream không bị đóng. Caller chịu trách nhiệm đóng outputStream.

### 3.3. Đừng nhầm đóng target với đóng cấu trúc JSON

JsonGenerator còn có feature AUTO_CLOSE_JSON_CONTENT. Feature này liên quan đến cấu trúc JSON đang mở, chẳng hạn object hoặc array chưa ghi token kết thúc. Khi generator đóng, Jackson có thể tự ghi token đóng tương ứng để hoàn tất cấu trúc.

Đây là hành vi khác với AUTO_CLOSE_TARGET:

- AUTO_CLOSE_TARGET quyết định có đóng OutputStream/Writer bên dưới hay không.
- AUTO_CLOSE_JSON_CONTENT quyết định cách xử lý cấu trúc JSON chưa hoàn tất khi generator đóng.

Việc tự ghi dấu đóng giúp generator kết thúc cấu trúc, nhưng không chứng minh dữ liệu nghiệp vụ đã được ghi đầy đủ. Nếu quá trình ghi lỗi giữa chừng, file có thể chứa một JSON có cú pháp hợp lệ nhưng chỉ có một phần dữ liệu mong muốn. Với file quan trọng, nên ghi ra file tạm và chỉ thay thế file đích sau khi toàn bộ quá trình thành công.

## 4. Hành vi của các overload ObjectMapper

Đây là điểm dễ nhầm nhất khi quản lý resource. Hai overload cùng làm một việc nhưng có thể có trách nhiệm đóng khác nhau.

| Cách gọi | Ai tạo parser/generator? | Ai đóng parser/generator? | Source/target mặc định |
|---|---|---|---|
| readValue(InputStream, Type) | ObjectMapper/JsonFactory | ObjectMapper | Parser đóng InputStream |
| readValue(Reader, Type) | ObjectMapper/JsonFactory | ObjectMapper | Parser đóng Reader |
| readValue(JsonParser, Type) | Caller | Caller | Parser đóng source nếu AUTO_CLOSE_SOURCE bật |
| readValue(File, Type) | ObjectMapper/JsonFactory | ObjectMapper | File stream được đóng |
| writeValue(OutputStream, value) | ObjectMapper/JsonFactory | ObjectMapper | Generator đóng OutputStream |
| writeValue(Writer, value) | ObjectMapper/JsonFactory | ObjectMapper | Generator đóng Writer |
| writeValue(JsonGenerator, value) | Caller | Caller | Generator đóng target nếu AUTO_CLOSE_TARGET bật |
| writeValue(File, value) | ObjectMapper/JsonFactory | ObjectMapper | File stream được đóng |
| readValue(String, Type) | ObjectMapper tạo parser nội bộ | ObjectMapper | Không có stream bên ngoài cần caller đóng |
| writeValueAsString(value) | ObjectMapper tạo generator nội bộ | ObjectMapper | Không có stream bên ngoài cần caller đóng |

Hai quy tắc cần nhớ:

1. readValue(InputStream, ...) và writeValue(OutputStream, ...) là các overload tiện ích. Jackson tạo và đóng parser/generator cho thao tác đó; chính sách mặc định của parser/generator đóng source/target bên dưới.
2. readValue(JsonParser, ...) và writeValue(JsonGenerator, ...) nhận đối tượng do caller cung cấp. Caller chịu trách nhiệm đóng parser/generator sau khi dùng.

Nếu caller cung cấp parser/generator, mapper không nên bị xem là chủ sở hữu của đối tượng đó. Caller có thể tiếp tục đọc/ghi sau một lần gọi mapper nếu giao thức cho phép.

## 5. Trường hợp Jackson sở hữu tài nguyên

Nếu một thao tác đọc/ghi là toàn bộ vòng đời của file, overload nhận File thường gọn và rõ ràng.

### 5.1. Đọc một file JSON

~~~java
Path path = Path.of("data/order.json");

Order order = mapper.readValue(path.toFile(), Order.class);
~~~

Mapper tạo parser để đọc file và đóng parser sau khi deserialize. File stream do Jackson mở được đóng theo vòng đời parser.

### 5.2. Ghi một file JSON

~~~java
Path path = Path.of("data/order.json");

mapper.writeValue(path.toFile(), order);
~~~

Mapper tạo generator để ghi file và đóng generator sau khi ghi. Output stream do Jackson mở được đóng theo vòng đời generator.

Không cần tự tạo thêm FileInputStream/FileOutputStream nếu không có lý do cần kiểm soát encoding, buffering hoặc vòng đời riêng.

### 5.3. Đọc/ghi bằng InputStream hoặc OutputStream được chuyển giao

Nếu caller chấp nhận chuyển giao quyền đóng cho thao tác Jackson, có thể dùng trực tiếp:

~~~java
Order order = mapper.readValue(inputStream, Order.class);

mapper.writeValue(outputStream, order);
~~~

Theo mặc định Jackson sẽ đóng stream bên dưới sau khi hoàn tất. Hãy ghi rõ điều này trong hợp đồng của method để caller không tiếp tục dùng stream sau lời gọi.

Nếu caller cần giữ stream mở, chuyển sang mô hình parser/generator do caller quản lý ở phần tiếp theo.

## 6. Trường hợp caller sở hữu stream

Một stream có thể được dùng cho nhiều bước. Ví dụ một ZIP archive có nhiều entry; một OutputStream có thể chứa nhiều phần dữ liệu; một HTTP response stream được framework quản lý. Trong các trường hợp này, không nên để thao tác JSON vô tình đóng stream.

### 6.1. Đọc JSON nhưng giữ InputStream mở

~~~java
public static <T> T readWithoutClosingSource(
    ObjectMapper mapper,
    InputStream input,
    Class<T> type
) throws IOException {

    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);
        return mapper.readValue(parser, type);
    }
}
~~~

Caller giữ quyền sở hữu InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Order order = readWithoutClosingSource(
        mapper,
        input,
        Order.class
    );

    // Có thể tiếp tục sử dụng input nếu định dạng nguồn cho phép.
}
~~~

Parser được đóng trong helper, nhưng source vẫn mở. Cuối cùng, khối try bên ngoài đóng InputStream.

Lưu ý: sau khi parser đã đọc một phần hoặc toàn bộ stream, việc tiếp tục sử dụng stream phụ thuộc vào vị trí đọc hiện tại và cấu trúc nguồn. Tắt AUTO_CLOSE_SOURCE chỉ giữ tài nguyên mở; nó không đưa con trỏ đọc trở lại vị trí ban đầu.

### 6.2. Ghi JSON nhưng giữ OutputStream mở

~~~java
public static void writeWithoutClosingTarget(
    ObjectMapper mapper,
    Object value,
    OutputStream output
) throws IOException {

    try (JsonGenerator generator =
             mapper.getFactory().createGenerator(output)) {

        generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);
        mapper.writeValue(generator, value);
    }
}
~~~

Caller có thể tiếp tục ghi vào output sau khi helper hoàn tất:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    writeWithoutClosingTarget(mapper, order, output);

    // Các bước ghi tiếp theo nếu định dạng file cho phép.
}
~~~

Generator được đóng để hoàn tất phần JSON và giải phóng buffer. OutputStream vẫn mở do AUTO_CLOSE_TARGET đã tắt. Khối try bên ngoài là nơi đóng stream.

Không nên tự gọi output.close() trong helper nếu hợp đồng nói rằng caller sở hữu stream.

### 6.3. Vì sao vẫn phải đóng parser/generator?

Tắt AUTO_CLOSE_SOURCE hoặc AUTO_CLOSE_TARGET không có nghĩa là bỏ qua việc đóng parser/generator.

Parser và generator quản lý buffer, symbol table hoặc trạng thái xử lý riêng. Nếu không đóng, tài nguyên nội bộ có thể không được giải phóng đúng lúc và dữ liệu ghi có thể chưa được flush hoàn tất.

Quy tắc là:

- Caller sở hữu stream: caller đóng stream.
- Parser/generator được tạo cho một thao tác: thành phần tạo nó phải đóng parser/generator.
- Nếu parser/generator được cấu hình không đóng source/target, việc đóng đối tượng Jackson vẫn cần thực hiện.
- Không bỏ đóng parser/generator chỉ vì stream bên dưới sẽ được framework đóng sau đó.

## 7. Chính sách đóng khi làm việc với Reader và Writer

Các nguyên tắc tương tự áp dụng cho Reader và Writer.

Ví dụ đọc từ Reader và giữ Reader mở:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(reader)) {
    parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);
    return mapper.readValue(parser, Configuration.class);
}
~~~

Ví dụ ghi ra Writer và giữ Writer mở:

~~~java
try (JsonGenerator generator = mapper.getFactory().createGenerator(writer)) {
    generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);
    mapper.writeValue(generator, configuration);
}
~~~

Nếu dùng mapper.readValue(reader, Type.class) hoặc mapper.writeValue(writer, value), mapper tạo parser/generator và đóng chúng. Với feature mặc định, Reader/Writer bên dưới cũng được đóng.

Không nên dựa vào việc một implementation Reader/Writer cụ thể có cho phép gọi close nhiều lần hay không. Hãy thiết kế một chủ sở hữu rõ ràng và tránh đóng lặp qua nhiều lớp.

## 8. Flush và close khác nhau như thế nào?

flush() và close() không thay thế cho nhau.

| Hành động | Tác dụng | Có kết thúc vòng đời không? |
|---|---|---|
| flush | Đẩy dữ liệu đang buffer xuống stream bên dưới | Không |
| close | Kết thúc parser/generator, giải phóng buffer và áp dụng chính sách đóng source/target | Có |
| AUTO_CLOSE_SOURCE | Quyết định parser close có đóng source hay không | Không tự đóng parser |
| AUTO_CLOSE_TARGET | Quyết định generator close có đóng target hay không | Không tự đóng generator |

Ví dụ, sau khi gọi generator.flush(), caller có thể nhìn thấy dữ liệu đã được đẩy xuống stream, nhưng generator vẫn đang hoạt động và cần được đóng khi hoàn tất.

Trong Jackson, generator thường flush target theo chính sách mặc định khi flush. Feature FLUSH_PASSED_TO_STREAM có thể điều khiển việc flush của generator có truyền xuống stream bên dưới hay không. Tắt feature này không đồng nghĩa với việc target không bị đóng; đó là hai chính sách khác nhau.

Không nên gọi flush sau mỗi field hoặc mỗi token nếu không có yêu cầu về streaming/latency. Flush quá thường xuyên có thể làm giảm hiệu năng do tăng số lần ghi xuống thiết bị hoặc mạng.

## 9. Đọc/ghi luồng trong ứng dụng Spring

Khi dùng Spring MVC hoặc Spring WebFlux, phần lớn ứng dụng không cần tự tạo parser/generator cho HTTP body.

### 9.1. Spring MVC

Spring MVC dùng HttpMessageConverter để đọc request body và ghi response body. Với JSON, converter tích hợp Jackson sẽ quản lý quá trình chuyển đổi và vòng đời parser/generator.

Controller thông thường nên nhận/trả DTO:

~~~java
@PostMapping("/orders")
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Không nên tự đóng HttpServletRequest.getInputStream() hoặc HttpServletResponse.getOutputStream() trong controller. Đây là tài nguyên thuộc vòng đời HTTP request/response do Servlet container và Spring quản lý.

Nếu một filter hoặc adapter bắt buộc phải đọc/ghi trực tiếp body, cần tuân theo hợp đồng của Servlet API và wrapper được sử dụng. Khi truyền stream container-managed vào overload ObjectMapper, cần chú ý rằng các overload tiện ích có thể đóng stream theo mặc định. Với thao tác thủ công, có thể tạo parser/generator và tắt AUTO_CLOSE_SOURCE/AUTO_CLOSE_TARGET để Jackson không kết thúc tài nguyên do container sở hữu.

### 9.2. Spring WebFlux

WebFlux xử lý body theo cơ chế reactive thông qua DataBuffer và codec. Jackson encoder/decoder được framework sử dụng trong pipeline. Ứng dụng nên để codec quản lý việc chuyển đổi và giải phóng buffer theo đúng cơ chế reactive.

Không chuyển DataBuffer thành InputStream tùy tiện rồi tự đóng buffer hoặc stream khi pipeline vẫn còn sử dụng. Nếu phải viết custom codec, cần tuân thủ ownership và release contract của DataBuffer, kể cả khi có lỗi hoặc cancellation.

### 9.3. WebClient

Khi dùng WebClient, hãy để codec đọc response body thành DTO:

~~~java
Mono<PartnerResponse> response =
    webClient.get()
        .uri("/partner/orders/{id}", orderId)
        .retrieve()
        .bodyToMono(PartnerResponse.class);
~~~

Không cần tự mở/đóng InputStream cho JSON response trong luồng sử dụng thông thường. Nếu dùng exchangeToMono hoặc truy cập raw body, phải tiêu thụ hoặc release body theo hợp đồng của WebClient để tránh giữ connection hoặc buffer.

## 10. Stream dùng chung, nhiều JSON value và giới hạn của một lần parse

Một số luồng không chỉ chứa một JSON document. Ví dụ, ứng dụng đọc nhiều JSON object nối tiếp từ một stream hoặc ghi nhiều event vào một output theo giao thức riêng.

Trong trường hợp đó, không nên gọi readValue(InputStream, ...) lặp lại trên cùng stream nếu mỗi lần gọi tạo parser mới và đóng source. Hãy tạo một parser do caller quản lý, sau đó đọc các value theo đúng giao thức.

Ví dụ khung cho nhiều root value liên tiếp:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);

    while (parser.nextToken() != null) {
        Event event = mapper.readValue(parser, Event.class);
        eventHandler.handle(event);
    }
}
~~~

Đoạn code chỉ là khung minh họa; định dạng đầu vào phải thực sự cho phép nhiều root value liên tiếp và vòng lặp cần được kiểm tra với cách parser kết thúc mỗi value. Nếu giao thức dùng JSON array, hãy đọc array token và từng phần tử theo cấu trúc đó. Nếu dùng JSON Lines, mỗi dòng là một JSON document riêng và cần reader theo dòng hoặc parser phù hợp.

Khi ghi nhiều JSON value, hãy chọn một giao thức có framing rõ ràng: JSON array, JSON Lines hoặc một định dạng streaming có quy ước phân tách. Nhiều object JSON nối liền không có dấu phân cách có thể gây khó khăn cho consumer và không phải một JSON document đơn lẻ.

## 11. Ghi file an toàn khi có lỗi giữa chừng

Ghi JSON trực tiếp vào file đích có thể để lại dữ liệu dở dang nếu serialization thất bại, ổ đĩa đầy hoặc ứng dụng bị dừng giữa chừng.

Đối với file cấu hình, snapshot hoặc dữ liệu quan trọng, nên ghi ra file tạm trước:

~~~java
Path target = Path.of("data/order.json");
Path temporary = target.resolveSibling("order.json.tmp");

mapper.writeValue(temporary.toFile(), order);

try {
    Files.move(
        temporary,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.ATOMIC_MOVE
    );
} catch (AtomicMoveNotSupportedException ex) {
    Files.move(
        temporary,
        target,
        StandardCopyOption.REPLACE_EXISTING
    );
}
~~~

Ví dụ này cần import java.nio.file.* và xử lý IOException theo tầng gọi. Atomic move chỉ được bảo đảm khi filesystem hỗ trợ; nhánh fallback thay thế file nhưng không có cùng bảo đảm nguyên tử.

Lợi ích của cách ghi tạm là file đích cũ vẫn còn nguyên nếu serialize thất bại trước bước thay thế. Cần có chính sách dọn file tạm còn sót lại sau crash hoặc lỗi.

Với HTTP response, không thể áp dụng move file. Một khi response body đã được ghi và commit, ứng dụng không thể quay lại để thay toàn bộ body bằng JSON lỗi khác. Vì vậy, hãy validate và chuẩn bị dữ liệu trước khi bắt đầu ghi response; để framework quản lý body stream.

## 12. Xử lý exception và đóng tài nguyên

Try-with-resources là lựa chọn mặc định cho parser, generator và stream do code hiện tại sở hữu.

~~~java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    parser.disable(JsonParser.Feature.AUTO_CLOSE_SOURCE);
    return mapper.readValue(parser, Order.class);

} catch (IOException ex) {
    throw new OrderReadException("Cannot read order JSON", ex);
}
~~~

Java đóng tài nguyên theo thứ tự ngược với thứ tự khai báo: parser được đóng trước, sau đó input stream được đóng. Nếu parser đã tắt AUTO_CLOSE_SOURCE, hai trách nhiệm được tách biệt rõ.

Nếu không tắt AUTO_CLOSE_SOURCE, parser sẽ đóng stream khi parser đóng; khối try bên ngoài sau đó lại gọi close trên stream. Nhiều stream triển khai close theo cách idempotent, nhưng không nên dựa vào điều đó để thiết kế ownership. Một số wrapper hoặc stream đặc biệt có thể có hành vi riêng khi close nhiều lần.

Try-with-resources cũng giữ exception gốc. Nếu thao tác đọc lỗi và việc đóng tài nguyên cũng lỗi, exception khi đóng được lưu dưới dạng suppressed exception. Không nên nuốt exception đóng tài nguyên một cách im lặng.

### 12.1. Không đóng ObjectMapper sau mỗi thao tác

ObjectMapper là đối tượng cấu hình và serializer cache dùng chung. Không cần gọi close sau mỗi lần serialize hoặc deserialize. Tạo mapper mới liên tục có thể làm mất lợi ích cache và khiến cấu hình bị phân tán.

Thông thường, mapper được tạo lúc khởi động ứng dụng và tái sử dụng. Các parser/generator được tạo cho từng thao tác mới là đối tượng cần được đóng đúng vòng đời.

### 12.2. Không giữ parser/generator trong field dùng chung

Parser và generator gắn với một luồng và trạng thái đọc/ghi cụ thể. Không đặt chúng vào static field hoặc singleton để nhiều request dùng chung.

Mỗi thao tác nên có parser/generator riêng. Mapper và factory đã cấu hình có thể dùng chung; parser/generator thì không nên dùng đồng thời cho nhiều request.

## 13. Checklist xác định ownership

Trước khi viết code đọc/ghi JSON, hãy xác nhận:

- [ ] Ai mở InputStream/Reader hoặc OutputStream/Writer?
- [ ] Stream được chuyển giao cho Jackson hay caller vẫn giữ quyền sở hữu?
- [ ] Dùng overload nhận stream hay overload nhận parser/generator?
- [ ] Parser/generator được tạo ở đâu và ai đóng nó?
- [ ] AUTO_CLOSE_SOURCE/AUTO_CLOSE_TARGET có phù hợp với ownership không?
- [ ] Có cần giữ stream mở để xử lý thêm dữ liệu hoặc nhiều JSON value không?
- [ ] Đây có phải stream do Servlet/WebFlux/WebClient quản lý không?
- [ ] Nếu serialize lỗi giữa chừng, dữ liệu đích có bị để lại một phần không?
- [ ] Exception trong quá trình close có được giữ lại và báo cáo không?
- [ ] Có test xác nhận stream vẫn mở hoặc đã đóng đúng như hợp đồng không?

## 14. Kết luận

Quản lý tài nguyên trong Jackson không chỉ là nhớ gọi close(). Cần hiểu parser/generator được tạo bởi ai, mapper có tự đóng parser/generator hay không, và feature AUTO_CLOSE_SOURCE/AUTO_CLOSE_TARGET quyết định điều gì với stream bên dưới.

Hãy dùng overload File hoặc các overload tiện ích khi muốn Jackson sở hữu toàn bộ vòng đời thao tác. Khi caller hoặc framework sở hữu stream, hãy tạo parser/generator rõ ràng, tắt auto-close source/target nếu cần, nhưng vẫn luôn đóng parser/generator sau khi dùng. Với Spring MVC/WebFlux, ưu tiên để message converter và codec quản lý HTTP body. Với file quan trọng, ghi tạm rồi thay thế sau khi serialize thành công.

Một quy tắc ownership rõ ràng giúp tránh đóng nhầm stream, rò rỉ buffer, response bị kết thúc sớm và dữ liệu file bị ghi dở.
