# Tái sử dụng reader và writer cho các trường hợp sử dụng ổn định

`ObjectMapper` là thành phần trung tâm của Jackson databind, nhưng trong ứng dụng thực tế, không phải mọi điểm đọc và ghi JSON đều có cùng yêu cầu. Một endpoint có thể cần đọc DTO theo chế độ nghiêm ngặt; một luồng xuất báo cáo cần JSON dễ đọc; một message nội bộ cần giữ quy tắc ngày giờ hoặc tên thuộc tính cố định. Nếu mỗi lần xử lý đều gọi `ObjectMapper` rồi lặp lại các cấu hình, logic chuyển đổi sẽ bị phân tán và khó bảo trì.

Jackson cung cấp **`ObjectReader`** và **`ObjectWriter`** để đóng gói kiểu dữ liệu cùng cấu hình đọc hoặc ghi cho một trường hợp sử dụng. Hai đối tượng này bất biến sau khi được tạo, có thể tái sử dụng và an toàn khi nhiều luồng cùng dùng. Chúng phù hợp để xây dựng các bộ chuyển đổi ổn định như reader cho một loại request, writer cho một loại response, hoặc các biến thể dành cho log, export và tích hợp với hệ thống khác.

## 1. Vì sao cần reader và writer riêng?

Một `ObjectMapper` thường được cấu hình ở cấp ứng dụng. Nó chứa các quy tắc chung như module ngày giờ, naming strategy, annotation introspector, serializer/deserializer và feature mặc định. Tuy nhiên, các điểm đọc/ghi có thể cần những lựa chọn khác nhau.

Ví dụ:

- API nhận `CreateOrderRequest` cần từ chối field không được biết trước để phát hiện client gửi sai tên thuộc tính.
- Một consumer cũ cần chấp nhận một số biến thể dữ liệu để tương thích ngược.
- Response công khai chỉ xuất một nhóm thuộc tính theo serialization view.
- File cấu hình cần được ghi với indentation để con người dễ đọc.
- Message gửi sang đối tác cần tên root hoặc quy tắc format riêng.
- Một luồng đọc nhiều bản ghi cần giữ kiểu phần tử cố định.

Nếu mọi nơi cùng sử dụng mapper và tự cấu hình lại, các quy tắc này dễ bị lặp. `ObjectReader` và `ObjectWriter` cho phép định nghĩa trước từng cách sử dụng, đặt tên rõ ràng và dùng lại ở nhiều lần gọi.

```text
                  ObjectMapper đã cấu hình
                           |
             +-------------+-------------+
             |                           |
             v                           v
      readerFor(Request)           writerFor(Response)
             |                           |
       +-----+-----+               +-----+------+
       |           |               |            |
       v           v               v            v
   Request API  Import job     HTTP response  JSON export
```

Reader chịu trách nhiệm về **cách đọc và chuyển JSON thành giá trị Java**. Writer chịu trách nhiệm về **cách chuyển giá trị Java thành JSON**. Chúng không thay thế `ObjectMapper`; chúng là các cấu hình chuyên biệt được tạo từ mapper.

## 2. Vị trí của reader và writer trong ObjectMapper

Trong Jackson databind, có thể tạo reader và writer trực tiếp từ `ObjectMapper`:

```java
ObjectMapper mapper = new ObjectMapper();

ObjectReader userReader = mapper.readerFor(User.class);
ObjectWriter userWriter = mapper.writerFor(User.class);
```

Các phương thức quan trọng:

| API | Mục đích |
|---|---|
| `readerFor(Class<T>)` | Tạo reader dành cho một kiểu Java cụ thể. |
| `readerFor(TypeReference<T>)` | Tạo reader cho kiểu generic được giữ bằng `TypeReference`. |
| `readerFor(JavaType)` | Tạo reader khi kiểu đích được biểu diễn bằng `JavaType`. |
| `writerFor(Class<?>)` | Tạo writer dành cho kiểu Java cụ thể. |
| `writerFor(TypeReference<?>)` | Tạo writer cho kiểu generic. |
| `writerFor(JavaType)` | Tạo writer cho kiểu được xây dựng bằng `TypeFactory`. |
| `reader()` / `writer()` | Tạo reader hoặc writer không cố định trước kiểu dữ liệu. |

Một reader được tạo bằng `readerFor(User.class)` đã biết kiểu kết quả là `User`. Một writer được tạo bằng `writerFor(User.class)` biết kiểu khai báo cần serialize. Việc chỉ rõ kiểu đặc biệt hữu ích khi làm việc với generic, polymorphic type hoặc khi kiểu runtime không đủ để diễn tả hợp đồng JSON mong muốn.

### 2.1. ObjectReader thực hiện công việc đọc

`ObjectReader` cung cấp các phương thức `readValue` cho nhiều loại nguồn dữ liệu:

```java
User fromString = userReader.readValue(jsonString);
User fromBytes = userReader.readValue(jsonBytes);
User fromStream = userReader.readValue(inputStream);
User fromFile = userReader.readValue(jsonFile);
```

Các overload cụ thể phụ thuộc kiểu nguồn và phiên bản Jackson. Khi nguồn là stream do ứng dụng mở, ứng dụng cần quản lý vòng đời stream đúng nơi sở hữu.

### 2.2. ObjectWriter thực hiện công việc ghi

`ObjectWriter` cung cấp các phương thức ghi object:

```java
String json = userWriter.writeValueAsString(user);
byte[] bytes = userWriter.writeValueAsBytes(user);

userWriter.writeValue(outputStream, user);
userWriter.writeValue(outputFile, user);
```

Writer giữ quy tắc serialize đã chọn. Cùng một writer có thể ghi nhiều object ở các lần gọi khác nhau, miễn là mỗi lần gọi truyền dữ liệu phù hợp với kiểu và cấu hình của writer.

## 3. Tạo mapper một lần, tạo reader/writer theo trường hợp sử dụng

Một mẫu phổ biến là cấu hình `ObjectMapper` ở thời điểm khởi tạo ứng dụng, sau đó tạo các reader/writer có mục đích rõ ràng.

```java
public final class JacksonConfiguration {
    private JacksonConfiguration() {
    }

    public static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }
}
```

Từ mapper đã hoàn tất cấu hình, tạo các đối tượng chuyên biệt:

```java
ObjectMapper mapper = JacksonConfiguration.createMapper();

ObjectReader createOrderReader = mapper
    .readerFor(CreateOrderRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter orderResponseWriter = mapper
    .writerFor(OrderResponse.class)
    .without(SerializationFeature.INDENT_OUTPUT);

ObjectWriter orderExportWriter = mapper
    .writerFor(OrderResponse.class)
    .with(SerializationFeature.INDENT_OUTPUT);
```

Ở đây, reader dùng kiểu request cụ thể và chính sách xử lý field lạ. Hai writer cùng ghi `OrderResponse`, nhưng một writer phục vụ response gọn, writer còn lại phục vụ file export có indentation.

Trong ứng dụng server, có thể đặt mapper và các reader/writer này trong một bean cấu hình hoặc một service codec dùng chung. Không cần tạo một `ObjectMapper` mới cho từng request chỉ để thay đổi một feature nhỏ.

## 4. ObjectReader là cấu hình đọc bất biến

`ObjectReader` là đối tượng bất biến (immutable). Các phương thức cấu hình như `with(...)`, `without(...)`, `withView(...)` hoặc `withAttribute(...)` trả về một reader mới mang cấu hình tương ứng. Chúng không sửa reader ban đầu.

```java
ObjectReader baseReader = mapper.readerFor(User.class);

ObjectReader strictReader = baseReader.with(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);

ObjectReader tolerantReader = baseReader.without(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
```

`baseReader`, `strictReader` và `tolerantReader` là ba cấu hình độc lập. Có thể dùng reader gốc cho trường hợp mặc định, reader nghiêm ngặt cho request có hợp đồng chặt và reader linh hoạt cho nguồn dữ liệu cần tương thích với field mở rộng.

Một lỗi thường gặp là gọi phương thức cấu hình nhưng bỏ qua giá trị trả về:

```java
ObjectReader reader = mapper.readerFor(User.class);

// Không làm reader hiện tại thay đổi:
reader.with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

// Phải giữ reader mới được trả về:
reader = reader.with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Vì API bất biến, cách rõ ràng hơn là tạo biến mới với tên thể hiện mục đích:

```java
ObjectReader strictUserReader = mapper
    .readerFor(User.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

### 4.1. Cố định kiểu đích

Reader chuyên biệt giúp tránh phải truyền lại kiểu ở mỗi lần đọc:

```java
private final ObjectReader orderReader =
    mapper.readerFor(OrderRequest.class);

OrderRequest readOrder(String json) throws IOException {
    return orderReader.readValue(json);
}
```

Với kiểu generic, sử dụng `TypeReference`:

```java
ObjectReader usersReader = mapper.readerFor(
    new TypeReference<List<User>>() {}
);

List<User> users = usersReader.readValue(jsonArray);
```

Hoặc tạo `JavaType` khi cấu trúc kiểu chỉ biết được ở runtime:

```java
JavaType listOfUsers = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

ObjectReader usersReader = mapper.readerFor(listOfUsers);
```

### 4.2. Cố định chính sách deserialize

Có thể tạo các reader khác nhau theo chính sách dữ liệu:

```java
ObjectReader strictRequestReader = mapper
    .readerFor(CreateUserRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader legacyImportReader = mapper
    .readerFor(LegacyUserRecord.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Không nên dùng một reader dễ dãi cho mọi nguồn dữ liệu chỉ để tránh lỗi. Reader strict có thể phát hiện client gửi sai field; reader tolerant có thể cần thiết khi nhập dữ liệu từ hệ thống cũ thường bổ sung thuộc tính. Chính sách phải phản ánh hợp đồng của nguồn đầu vào.

### 4.3. Dùng view và attribute khi cần

Reader có thể được cấu hình với serialization view tương ứng trong các tình huống đọc có sử dụng `@JsonView`, và có thể mang attribute để serializer/deserializer truy cập qua context khi mapping.

```java
ObjectReader publicUserReader = mapper
    .readerFor(User.class)
    .withView(Views.Public.class);
```

Attribute phù hợp với metadata ổn định trong một lần xử lý, chẳng hạn mã nguồn nhập hoặc chế độ chuyển đổi. Không nên nhét dữ liệu thay đổi theo từng request vào một reader singleton rồi sửa trạng thái dùng chung. Nếu attribute khác nhau theo tác vụ, tạo một biến thể reader mới từ reader nền:

```java
ObjectReader importReader = mapper
    .readerFor(ImportRecord.class);

ObjectReader partnerAReader = importReader
    .withAttribute("source", "partner-a");

ObjectReader partnerBReader = importReader
    .withAttribute("source", "partner-b");
```

Các ví dụ view/attribute chỉ có tác dụng khi model hoặc custom deserializer thực sự đọc metadata đó.

## 5. ObjectWriter là cấu hình ghi bất biến

`ObjectWriter` cũng bất biến. Mỗi lần gọi `with(...)`, `without(...)`, `withView(...)`, `withRootName(...)` hoặc cấu hình tương ứng sẽ trả về một writer mới.

```java
ObjectWriter baseWriter = mapper.writerFor(User.class);

ObjectWriter compactWriter = baseWriter.without(
    SerializationFeature.INDENT_OUTPUT
);

ObjectWriter prettyWriter = baseWriter.with(
    SerializationFeature.INDENT_OUTPUT
);
```

Hai writer có thể được dùng độc lập mà không ảnh hưởng nhau. Đây là cách tốt để định nghĩa định dạng ổn định cho từng đích xuất dữ liệu.

### 5.1. Cố định kiểu được serialize

```java
ObjectWriter responseWriter = mapper.writerFor(ApiResponse.class);

String json = responseWriter.writeValueAsString(response);
```

Khi ghi một kiểu khai báo cụ thể, `writerFor` làm rõ hợp đồng serialize. Điều này có thể quan trọng khi object runtime là subclass nhưng API chỉ muốn phát ra thuộc tính của kiểu cơ sở hoặc khi cấu hình polymorphic type có ảnh hưởng đến đầu ra.

### 5.2. Định dạng dễ đọc và định dạng trao đổi

Một file JSON cho người vận hành đọc có thể cần indentation; response HTTP thường ưu tiên dạng compact:

```java
ObjectWriter httpWriter = mapper
    .writerFor(OrderResponse.class)
    .without(SerializationFeature.INDENT_OUTPUT);

ObjectWriter fileWriter = mapper
    .writerFor(OrderResponse.class)
    .with(SerializationFeature.INDENT_OUTPUT);
```

Có thể dùng `writerWithDefaultPrettyPrinter()` khi muốn writer có pretty printer mặc định. Dù dùng cách nào, nên giữ writer riêng cho đích sử dụng ổn định thay vì thay đổi cấu hình mapper dùng chung trước mỗi lần ghi.

### 5.3. Serialization view

Nếu model sử dụng `@JsonView`, có thể tạo writer theo view để giới hạn nhóm thuộc tính xuất ra:

```java
ObjectWriter publicWriter = mapper
    .writerFor(UserResponse.class)
    .withView(Views.Public.class);

ObjectWriter adminWriter = mapper
    .writerFor(UserResponse.class)
    .withView(Views.Admin.class);
```

View phải được khai báo trên các thuộc tính cần kiểm soát. Cần hiểu cấu hình `MapperFeature.DEFAULT_VIEW_INCLUSION`, vì nó quyết định cách xử lý thuộc tính không gắn view. Serialization view là quy tắc định dạng đầu ra, không thay thế kiểm tra quyền truy cập và chính sách bảo mật ở tầng nghiệp vụ.

### 5.4. Root name và filter

Trong một hợp đồng JSON yêu cầu bọc object dưới tên root, có thể tạo writer với root name:

```java
ObjectWriter orderRootWriter = mapper
    .writerFor(OrderResponse.class)
    .withRootName("order")
    .with(SerializationFeature.WRAP_ROOT_VALUE);
```

Đầu ra có dạng:

```json
{
  "order": {
    "id": 1001,
    "status": "PAID"
  }
}
```

Root wrapping cần được bật theo feature tương ứng; chỉ đặt tên root không có nghĩa mọi cấu hình đều tự động bọc object. Nếu ứng dụng dùng `@JsonFilter`, writer cũng có thể mang `FilterProvider` phù hợp cho từng đích xuất. Filter và view cần được kiểm thử như một phần của hợp đồng JSON.

## 6. Các mẫu tái sử dụng trong ứng dụng

### 6.1. Codec cho một DTO hoặc message type

Một codec có thể gom reader và writer thành một đơn vị có trách nhiệm rõ ràng:

```java
public final class OrderJsonCodec {
    private final ObjectReader reader;
    private final ObjectWriter writer;

    public OrderJsonCodec(ObjectMapper mapper) {
        this.reader = mapper.readerFor(OrderMessage.class);
        this.writer = mapper.writerFor(OrderMessage.class);
    }

    public OrderMessage decode(String json) throws IOException {
        return reader.readValue(json);
    }

    public String encode(OrderMessage message)
            throws JsonProcessingException {
        return writer.writeValueAsString(message);
    }
}
```

Lớp codec giữ hợp đồng đọc/ghi của `OrderMessage` tại một nơi. Các service gọi codec không cần lặp lại kiểu Java và cấu hình Jackson. Nếu sau này message có quy tắc ngày giờ hoặc tên field riêng, có thể cấu hình mapper trước khi tạo codec hoặc tạo reader/writer chuyên biệt trong constructor.

### 6.2. Nhiều reader cho các nguồn đầu vào khác nhau

Một hệ thống có thể nhận cùng một kiểu dữ liệu từ nhiều nguồn nhưng có chính sách khác nhau:

```java
public final class UserImportReaders {
    private final ObjectReader internalReader;
    private final ObjectReader partnerReader;

    public UserImportReaders(ObjectMapper mapper) {
        this.internalReader = mapper
            .readerFor(UserImport.class)
            .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        this.partnerReader = mapper
            .readerFor(UserImport.class)
            .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }

    public UserImport readInternal(String json) throws IOException {
        return internalReader.readValue(json);
    }

    public UserImport readPartner(String json) throws IOException {
        return partnerReader.readValue(json);
    }
}
```

Reader được đặt tên theo nguồn và chính sách, giúp người đọc code hiểu vì sao cùng kiểu `UserImport` lại có hai cách xử lý field lạ. Khi cần thay đổi chính sách, chỉ cần chỉnh nơi tạo reader.

### 6.3. Nhiều writer cho các đích xuất khác nhau

Một model có thể được xuất ra response và file lưu trữ:

```java
public final class ReportWriters {
    private final ObjectWriter apiWriter;
    private final ObjectWriter archiveWriter;

    public ReportWriters(ObjectMapper mapper) {
        this.apiWriter = mapper
            .writerFor(ReportResponse.class)
            .without(SerializationFeature.INDENT_OUTPUT);

        this.archiveWriter = mapper
            .writerFor(ReportResponse.class)
            .with(SerializationFeature.INDENT_OUTPUT);
    }

    public String toApiJson(ReportResponse report)
            throws JsonProcessingException {
        return apiWriter.writeValueAsString(report);
    }

    public void writeArchive(OutputStream output, ReportResponse report)
            throws IOException {
        archiveWriter.writeValue(output, report);
    }
}
```

Hai writer thể hiện hai đích sử dụng. Nếu file archive có yêu cầu root name, filter hoặc version schema riêng, các lựa chọn đó cũng nên nằm trong writer archive thay vì thay đổi cấu hình toàn cục.

## 7. Tái sử dụng reader/writer cho kiểu generic

Các collection có generic type thường xuất hiện trong API và message. Vì type erasure, không thể dựa vào `List.class` để giữ thông tin phần tử.

```java
ObjectReader productListReader = mapper.readerFor(
    new TypeReference<List<ProductDto>>() {}
);

ObjectWriter productListWriter = mapper.writerFor(
    new TypeReference<List<ProductDto>>() {}
);

List<ProductDto> products = productListReader.readValue(json);
String output = productListWriter.writeValueAsString(products);
```

Khi kiểu phức tạp được tạo động, có thể dùng cùng một `JavaType` để xây reader/writer:

```java
JavaType mapType = mapper.getTypeFactory().constructMapType(
    Map.class,
    String.class,
    ProductDto.class
);

ObjectReader mapReader = mapper.readerFor(mapType);
ObjectWriter mapWriter = mapper.writerFor(mapType);
```

Đối với cấu trúc generic ổn định, tạo `JavaType` và reader/writer một lần sẽ làm rõ kiểu dữ liệu mong muốn tại ranh giới JSON. Không nên dùng raw type rồi ép kiểu kết quả ở nhiều nơi vì lỗi kiểu chỉ xuất hiện muộn hơn và khó truy vết hơn.

## 8. Đọc và ghi nhiều giá trị theo luồng

Reader/writer không chỉ phục vụ một JSON document đơn lẻ. Chúng có thể phối hợp với API streaming của Jackson khi nguồn hoặc đích chứa nhiều bản ghi.

### 8.1. Đọc nhiều giá trị bằng MappingIterator

`ObjectReader.readValues(...)` có thể tạo `MappingIterator<T>` để đọc tuần tự các giá trị cùng kiểu từ parser:

```java
ObjectReader eventReader = mapper.readerFor(Event.class);

try (JsonParser parser = jsonFactory.createParser(inputStream);
     MappingIterator<Event> events = eventReader.readValues(parser)) {

    while (events.hasNextValue()) {
        Event event = events.nextValue();
        handle(event);
    }
}
```

Mẫu này phù hợp khi định dạng đầu vào và cách parser định vị phần tử đã được xác định rõ. Với một JSON array, cần bảo đảm reader/iterator bắt đầu tại token phù hợp và kiểm thử cấu trúc đầu vào. Việc dùng iterator tránh phải deserialize toàn bộ danh sách thành một collection lớn trước khi xử lý.

### 8.2. Ghi nhiều giá trị bằng SequenceWriter

`ObjectWriter.writeValues(...)` tạo `SequenceWriter` để ghi nhiều object theo cùng một cấu hình:

```java
ObjectWriter eventWriter = mapper.writerFor(Event.class);

try (SequenceWriter sequence = eventWriter.writeValues(outputStream)) {
    for (Event event : events) {
        sequence.write(event);
    }
}
```

`SequenceWriter` phù hợp với xuất dữ liệu theo lô hoặc luồng record. Cần chọn rõ định dạng đích mà bên nhận mong đợi: một chuỗi các JSON value, một JSON array hoặc một giao thức record riêng. Nếu hợp đồng yêu cầu array, dùng API/cấu hình ghi dạng array tương ứng thay vì giả định mọi sequence đều tự có dấu ngoặc array.

Reader/writer có thể được tái sử dụng; parser, generator, iterator và stream của từng lần xử lý vẫn phải tuân theo vòng đời tài nguyên riêng. Không chia sẻ một parser hoặc generator đang hoạt động giữa các request đồng thời.

## 9. An toàn luồng và vòng đời cấu hình

### 9.1. Vì sao reader và writer có thể dùng chung?

`ObjectReader` và `ObjectWriter` được thiết kế bất biến và thread-safe. Sau khi tạo, cấu hình của chúng không bị thay đổi bởi lời gọi `with` hoặc `without`; các lời gọi đó tạo đối tượng mới. Vì vậy, có thể giữ reader/writer trong field `static final` hoặc trong một singleton service để nhiều luồng sử dụng đồng thời.

Ví dụ:

```java
public final class JsonCodecs {
    private static final ObjectMapper MAPPER = createMapper();

    public static final ObjectReader USER_READER =
        MAPPER.readerFor(User.class);

    public static final ObjectWriter USER_WRITER =
        MAPPER.writerFor(User.class);

    private JsonCodecs() {
    }

    private static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        return mapper;
    }
}
```

Điều kiện quan trọng là mapper phải được cấu hình hoàn chỉnh trước khi reader/writer được tạo và trước khi bắt đầu sử dụng đồng thời. `ObjectMapper` có thể được dùng chung sau khi cấu hình xong, nhưng không nên thay đổi cấu hình mapper trong khi các luồng đang đọc/ghi.

### 9.2. Không tái sử dụng tài nguyên I/O đang mở

Thread-safe của reader/writer không có nghĩa stream hoặc parser dùng trong mỗi lần gọi cũng được chia sẻ. Mỗi request nên có nguồn và đích I/O riêng:

```java
try (InputStream input = Files.newInputStream(path)) {
    User user = JsonCodecs.USER_READER.readValue(input);
    process(user);
}
```

Không lưu `InputStream`, `OutputStream`, `JsonParser`, `JsonGenerator` hoặc `MappingIterator` đang hoạt động trong một reader/writer dùng chung. Những đối tượng đó mang trạng thái tiến trình và vòng đời riêng.

### 9.3. Custom serializer/deserializer cũng phải an toàn khi dùng chung

Reader/writer có thể được gọi đồng thời, nhưng custom serializer/deserializer và các dependency mà chúng tham chiếu cũng phải phù hợp với cách dùng đồng thời đó. Tránh giữ mutable state theo request trong field của serializer singleton. Nếu cần dữ liệu theo từng lần gọi, truyền qua context/attribute hoặc cấu trúc bất biến phù hợp.

### 9.4. Tránh thay đổi mapper sau khi đã tạo reader/writer

Hãy cấu hình mapper ở giai đoạn bootstrap:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

ObjectReader reader = mapper.readerFor(User.class);
ObjectWriter writer = mapper.writerFor(User.class);
```

Sau giai đoạn này, giữ mapper ổn định. Nếu một tác vụ cần cấu hình riêng, tạo reader/writer variant. Không dùng `mapper.enable(...)` hoặc `mapper.disable(...)` quanh từng request vì các request đồng thời có thể quan sát cấu hình không mong muốn.

## 10. Reader/writer và ObjectMapper: chọn đúng công cụ

| Nhu cầu | Nên dùng |
|---|---|
| Cấu hình module, naming strategy, mix-in và quy tắc chung cho ứng dụng | `ObjectMapper` trong giai đoạn khởi tạo |
| Đọc lặp lại một kiểu DTO với cùng chính sách | Một `ObjectReader` dùng chung |
| Ghi lặp lại một kiểu DTO với cùng định dạng | Một `ObjectWriter` dùng chung |
| Tạo một biến thể đọc/ghi với một feature khác | `reader.with(...)` hoặc `writer.with(...)` và giữ kết quả mới |
| Đọc/ghi một lần với kiểu không cố định | `ObjectMapper` hoặc reader/writer không cố định kiểu |
| Cần cập nhật một object có sẵn | Reader được tạo bằng `readerForUpdating`, nhưng phải quản lý object đích theo từng thao tác |
| Cần parser/generator và điều khiển token trực tiếp | `JsonFactory`, `JsonParser`, `JsonGenerator` |

`ObjectMapper` vẫn là điểm khởi tạo và điều phối. Reader/writer là lớp cấu hình chuyên biệt cho các hoạt động lặp lại. Nếu một thao tác chỉ xảy ra một lần và không có cấu hình riêng, gọi mapper trực tiếp vẫn hoàn toàn hợp lý; không cần tạo thêm abstraction chỉ để dùng một lần.

## 11. Những điểm cần chú ý khi dùng reader/writer

### Luôn giữ giá trị trả về của phương thức cấu hình

Các phương thức `with` và `without` trả về đối tượng mới. Bỏ qua giá trị trả về đồng nghĩa cấu hình mới không được áp dụng.

### Không đưa dữ liệu biến đổi theo request vào singleton

Reader/writer dùng chung nên giữ cấu hình ổn định. Metadata thay đổi theo request phải được truyền theo lần gọi hoặc tạo biến thể bất biến riêng cho request đó. Không dùng một mutable map dùng chung để làm nơi chứa trạng thái request.

### Không dùng reader cập nhật object dùng chung

`readerForUpdating(existingObject)` tạo reader có mục tiêu cập nhật là object đã cho. Nếu `existingObject` được chia sẻ giữa các request, có thể phát sinh race condition và rò rỉ trạng thái. Hãy tạo reader cập nhật cho object có vòng đời riêng của thao tác, hoặc dùng cách mapping trả về object mới.

### Cấu hình writer có thể làm thay đổi hợp đồng đầu ra

Indentation thường chỉ thay đổi khoảng trắng, nhưng root wrapping, view, filter, inclusion và custom serializer có thể làm thay đổi cấu trúc hoặc tập field được xuất. Tách writer theo đích sử dụng và kiểm thử JSON đầu ra.

### Đừng nhầm immutable với việc mọi dependency đều bất biến

Reader/writer không cho phép sửa cấu hình nội bộ của chúng qua API thông thường, nhưng custom component, attribute object hoặc dữ liệu ứng dụng được tham chiếu vẫn có thể mutable. Chỉ chia sẻ các cấu hình và component an toàn khi dùng đồng thời.

### Chú ý phiên bản Jackson

Các ví dụ import `com.fasterxml.jackson.*` minh họa API của dòng Jackson 2.x. Khi sử dụng major line khác, hãy đối chiếu package, chữ ký method và tài liệu đúng phiên bản. Không nên sao chép import hoặc giả định mọi overload tồn tại giống nhau giữa các major line.

## 12. Ví dụ hoàn chỉnh: service dùng reader và writer ổn định

Ví dụ sau tạo một codec cho request và response. Mapper được cấu hình trước; reader và writer được tạo một lần trong constructor và tái sử dụng cho các lần gọi.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.IOException;

public final class UserJsonCodec {
    private final ObjectReader requestReader;
    private final ObjectWriter responseWriter;
    private final ObjectWriter auditWriter;

    public UserJsonCodec(ObjectMapper configuredMapper) {
        this.requestReader = configuredMapper
            .readerFor(UserRequest.class)
            .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        this.responseWriter = configuredMapper
            .writerFor(UserResponse.class)
            .without(SerializationFeature.INDENT_OUTPUT);

        this.auditWriter = configuredMapper
            .writerFor(UserResponse.class)
            .with(SerializationFeature.INDENT_OUTPUT);
    }

    public UserRequest readRequest(String json) throws IOException {
        return requestReader.readValue(json);
    }

    public String writeResponse(UserResponse response)
            throws JsonProcessingException {
        return responseWriter.writeValueAsString(response);
    }

    public String writeAuditRecord(UserResponse response)
            throws JsonProcessingException {
        return auditWriter.writeValueAsString(response);
    }
}
```

Lớp codec không tự tạo mapper mới. Nó nhận mapper đã được cấu hình từ ứng dụng, sau đó tạo ba cấu hình ổn định. Reader kiểm soát dữ liệu request; response writer tạo JSON compact; audit writer tạo JSON có indentation để thuận tiện đọc khi kiểm tra log hoặc file lưu trữ.

Ví dụ khởi tạo:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

UserJsonCodec codec = new UserJsonCodec(mapper);
```

Trong ứng dụng có dependency injection, mapper nên được cung cấp bởi cấu hình trung tâm hoặc framework. Không tạo mapper riêng trong từng controller/service nếu ứng dụng đã có mapper dùng chung với module và quy tắc nhất quán.

## 13. Kiểm thử reader và writer theo hợp đồng

Reader/writer là cấu hình có thể tái sử dụng, vì vậy nên kiểm thử hành vi của từng cấu hình một cách độc lập. Test nên tập trung vào dữ liệu mà ứng dụng cam kết nhận và phát.

Ví dụ kiểm tra reader nghiêm ngặt:

```java
ObjectReader strictReader = mapper
    .readerFor(UserRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

UserRequest request = strictReader.readValue("""
    { "id": 7, "name": "Mai" }
    """);

assertEquals(7L, request.getId());
assertEquals("Mai", request.getName());
```

Có thể kiểm tra rằng field lạ bị từ chối:

```java
assertThrows(JsonProcessingException.class, () ->
    strictReader.readValue("""
        { "id": 7, "name": "Mai", "unexpected": true }
        """)
);
```

Ví dụ kiểm tra writer:

```java
ObjectWriter writer = mapper
    .writerFor(UserResponse.class)
    .with(SerializationFeature.INDENT_OUTPUT);

String json = writer.writeValueAsString(response);
JsonNode tree = mapper.readTree(json);

assertEquals(response.getId(), tree.path("id").asLong());
assertEquals(response.getName(), tree.path("name").asText());
assertTrue(json.contains("\n"));
```

Kiểm tra cấu trúc bằng `JsonNode` giúp tránh phụ thuộc không cần thiết vào thứ tự field. Nếu format hoặc root wrapping là một phần của hợp đồng, thêm assertion rõ ràng cho các đặc điểm đó.

## 14. Khi nào nên tạo reader/writer mới?

Reader/writer nhẹ hơn việc tạo một mapper mới, nhưng vẫn nên có chủ đích. Tạo và giữ một cấu hình dùng chung khi kiểu dữ liệu và chính sách ổn định, ví dụ reader cho `OrderRequest` hoặc writer cho `AuditEvent`.

Tạo một biến thể mới khi có một khác biệt cấu hình thực sự, chẳng hạn strict/tolerant, public/admin view hoặc compact/pretty. Không cần tạo một field static cho mọi tổ hợp có thể tưởng tượng; chỉ tạo những biến thể có tên, có nơi sử dụng và có hợp đồng rõ.

Nếu khác biệt chỉ là dữ liệu của lần gọi, hãy truyền dữ liệu vào phương thức `readValue`/`writeValue` hoặc dùng context phù hợp. Không tạo reader/writer mới chỉ để lưu một object nghiệp vụ biến đổi theo request nếu API hiện có đã nhận object đó làm đối số.

## 15. Quy trình áp dụng trong dự án

Khi chuẩn hóa việc dùng Jackson trong một ứng dụng, có thể triển khai theo trình tự sau:

1. Xác định mapper trung tâm và cấu hình module, naming strategy, date/time cùng feature chung ở thời điểm khởi tạo.
2. Liệt kê các điểm đọc/ghi có hợp đồng ổn định: request DTO, message type, file import/export và response.
3. Với mỗi kiểu, tạo `ObjectReader` hoặc `ObjectWriter` có kiểu đích rõ ràng.
4. Đặt tên reader/writer theo mục đích hoặc nguồn dữ liệu để thể hiện chính sách mapping.
5. Tạo biến thể immutable cho các trường hợp strict/tolerant, view, filter hoặc format khác nhau.
6. Đưa reader/writer vào service/codec có vòng đời phù hợp và tái sử dụng giữa các lần gọi.
7. Đảm bảo mapper và custom component đã hoàn tất cấu hình trước khi được dùng đồng thời.
8. Không chia sẻ parser, generator, stream hoặc object đích mutable giữa các thao tác độc lập.
9. Kiểm thử dữ liệu đầu vào, đầu ra và các khác biệt cấu hình có ý nghĩa với hợp đồng.

## 16. Những điểm cần ghi nhớ

- `ObjectReader` đóng gói kiểu đích và quy tắc deserialize; `ObjectWriter` đóng gói kiểu và quy tắc serialize.
- Cả hai được tạo từ `ObjectMapper`, giúp giữ một cấu hình nền chung nhưng tách chính sách theo trường hợp sử dụng.
- Reader/writer là immutable và thread-safe; các phương thức `with`/`without` trả về instance mới.
- Giữ giá trị trả về của phương thức cấu hình. Gọi `reader.with(...)` mà bỏ kết quả không làm reader cũ thay đổi.
- Tái sử dụng reader/writer cho DTO, message và định dạng ổn định; không tạo mapper mới cho từng request chỉ để đổi một feature.
- Cấu hình mapper trước khi sử dụng đồng thời; không thay đổi mapper dùng chung trong lúc xử lý request.
- Thread-safe của reader/writer không làm cho stream, parser, generator hoặc custom component mutable tự động an toàn khi chia sẻ.
- Dùng `TypeReference` hoặc `JavaType` để giữ generic type.
- Kiểm thử riêng các chính sách đọc/ghi có thể làm thay đổi hợp đồng JSON như field lạ, view, root name, filter và format.
