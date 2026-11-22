# Tái sử dụng mapper, reader và writer có cấu hình ổn định

Jackson được thiết kế để xử lý JSON hiệu quả khi các thành phần cấu hình được tái sử dụng. Trong ứng dụng Java, ObjectMapper quản lý cấu hình, module, serializer/deserializer và các cache metadata cần thiết để chuyển đổi giữa JSON với object. Nếu tạo mapper mới cho từng request hoặc từng lần gọi, ứng dụng phải lặp lại nhiều công việc khởi tạo và mất lợi ích từ các cache này.

Một cách tổ chức hiệu quả là **tạo và cấu hình ObjectMapper một lần ở giai đoạn khởi động, sau đó tái sử dụng nó; tạo sẵn ObjectReader và ObjectWriter cho những kiểu và chính sách thường dùng**. Reader và writer là các đối tượng cấu hình bất biến, nhẹ và an toàn để chia sẻ giữa nhiều thread. Khi cần một biến thể nhỏ cho một thao tác, có thể tạo reader/writer mới bằng các phương thức with(...) mà không thay đổi mapper dùng chung.

Hiệu năng không chỉ đến từ việc giữ một biến ObjectMapper static. Cần hoàn tất cấu hình trước khi mapper được sử dụng, tránh thay đổi cấu hình toàn cục theo từng request, phân biệt reader/writer có thể chia sẻ với reader đang giữ một object mutable để cập nhật, và đo lường bằng workload thực tế trước khi tối ưu thêm.

## 1. Các thành phần trong vòng đời xử lý JSON

Jackson cung cấp nhiều lớp ở các mức trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Cách sử dụng điển hình |
|---|---|---|
| JsonFactory | Tạo parser và generator cho một định dạng JSON | Tái sử dụng cùng mapper/factory đã cấu hình |
| ObjectMapper | Cấu hình databinding, module, serializer/deserializer và đọc/ghi object | Tạo một lần cho mỗi bộ cấu hình ổn định |
| ObjectReader | Cấu hình đọc cho kiểu đích và các tùy chọn deserialization | Tái sử dụng cho một loại request/message |
| ObjectWriter | Cấu hình ghi cho kiểu nguồn và các tùy chọn serialization | Tái sử dụng cho một loại response/event |
| JsonParser | Đọc token từ một input cụ thể | Tạo cho mỗi document/stream, đóng sau khi dùng |
| JsonGenerator | Ghi token vào một output cụ thể | Tạo cho mỗi document/stream, đóng sau khi dùng |

Một luồng xử lý thường có dạng:

~~~text
Ứng dụng khởi động
      |
      v
Tạo JsonFactory / ObjectMapper
      |
      +-- đăng ký module
      +-- cấu hình feature
      +-- cấu hình naming, mix-in, subtype...
      |
      v
Tạo ObjectReader / ObjectWriter thường dùng
      |
      v
Nhiều request hoặc message
      |
      +-- reader.readValue(input)
      +-- writer.writeValue(output)
      |
      v
Đóng input/output theo quyền sở hữu tài nguyên
~~~

ObjectMapper giữ cấu hình dùng chung và cache các serializer/deserializer đã phân giải. Reader và writer giữ cấu hình cho một thao tác đọc/ghi cụ thể. Parser và generator là các đối tượng làm việc với dữ liệu của từng lần đọc/ghi; không giữ một parser đang mở rồi dùng chung cho nhiều request.

## 2. Vì sao không tạo ObjectMapper cho mỗi lần xử lý?

Một đoạn code có vẻ tiện nhưng không phù hợp với đường xử lý thường xuyên:

~~~java
public OrderResponse handle(String json) throws IOException {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.readValue(json, OrderResponse.class);
}
~~~

Mỗi lần gọi method, ứng dụng tạo mapper mới. Mapper phải thiết lập factory, cấu hình và các cấu trúc nội bộ. Các cache serializer/deserializer của instance mới chưa được tận dụng từ những lần gọi trước. Nếu mapper còn phải đăng ký module, mix-in hoặc custom serializer, phần cấu hình đó cũng bị lặp lại.

Cách này có thể chấp nhận trong một đoạn script nhỏ hoặc test cô lập, nhưng không nên dùng cho controller, consumer, batch processor hoặc service được gọi liên tục.

Thay vào đó, tạo mapper ở phạm vi ứng dụng:

~~~java
public final class JsonSupport {
    private JsonSupport() {
    }

    public static final ObjectMapper MAPPER = new ObjectMapper();
}
~~~

Rồi tái sử dụng:

~~~java
public OrderResponse handle(String json) throws IOException {
    return JsonSupport.MAPPER.readValue(json, OrderResponse.class);
}
~~~

Ví dụ trên minh họa vòng đời, nhưng trong ứng dụng thật nên dùng một điểm cấu hình tập trung, không nhất thiết phải public một mutable mapper toàn cục. Dependency injection hoặc một factory cấu hình mapper thường dễ kiểm soát hơn.

## 3. ObjectMapper thread-safe sau khi cấu hình hoàn tất

ObjectMapper được thiết kế để có thể dùng đồng thời từ nhiều thread, với điều kiện **toàn bộ cấu hình được thực hiện trước khi bắt đầu các thao tác đọc/ghi**.

Các thao tác cấu hình thường bao gồm:

- Đăng ký module.
- Đăng ký mix-in và subtype.
- Bật/tắt SerializationFeature hoặc DeserializationFeature.
- Cấu hình naming strategy.
- Cấu hình visibility, coercion và inclusion.
- Cấu hình serializer/deserializer tùy biến.
- Cấu hình type resolver và các chính sách liên quan.

Một cấu hình khởi tạo điển hình:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonConfiguration {
    private JsonConfiguration() {
    }

    public static ObjectMapper createMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .build();
    }
}
~~~

Sau khi createMapper() trả về mapper đã hoàn chỉnh, ứng dụng có thể chia sẻ instance đó. Không nên thay đổi feature hoặc đăng ký module trong lúc request đang chạy.

### 3.1. Không thay cấu hình mapper theo từng request

Một anti-pattern là bật/tắt feature trên mapper singleton tùy request:

~~~java
// Không làm như vậy trên mapper được nhiều request dùng chung.
mapper.enable(SerializationFeature.INDENT_OUTPUT);
String json = mapper.writeValueAsString(response);
mapper.disable(SerializationFeature.INDENT_OUTPUT);
~~~

Nếu hai thread chạy đồng thời, một request có thể quan sát cấu hình do request khác vừa thay đổi. Kết quả trở nên phụ thuộc thời điểm và khó tái hiện.

Dùng ObjectWriter làm biến thể cục bộ:

~~~java
ObjectWriter compactWriter = mapper.writer();
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();

String compact = compactWriter.writeValueAsString(response);
String pretty = prettyWriter.writeValueAsString(response);
~~~

Tương tự, dùng ObjectReader cho các chính sách đọc khác nhau thay vì đổi feature trên mapper dùng chung.

### 3.2. Cấu hình custom serializer/deserializer cũng cần an toàn đồng thời

Mapper thread-safe không tự làm mọi custom component trở nên thread-safe. Serializer/deserializer có thể được cache và dùng đồng thời. Vì vậy:

- Ưu tiên implementation stateless.
- Không lưu dữ liệu của request hiện tại trong field mutable.
- Không dùng chung SimpleDateFormat hoặc object mutable không an toàn giữa các lần gọi.
- Nếu cần cache nội bộ, dùng cấu trúc đồng thời và giới hạn kích thước phù hợp.
- Không sửa cấu hình serializer sau khi đã đăng ký.

Các biến cục bộ trong serialize() hoặc deserialize() thường là lựa chọn phù hợp. Nếu custom component có state cấu hình, hãy tạo instance bất biến khi cấu hình mapper.

## 4. ObjectReader và ObjectWriter là cấu hình bất biến

ObjectReader và ObjectWriter được thiết kế để tái sử dụng. Chúng giữ cấu hình đọc/ghi như kiểu gốc, feature, format, injectable values hoặc các tùy chọn khác. Các phương thức như with(...) và without(...) trả về một reader/writer mới với cấu hình biến thể; instance ban đầu không bị thay đổi.

Ví dụ:

~~~java
ObjectReader strictOrderReader = mapper.readerFor(OrderRequest.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter orderWriter = mapper.writerFor(OrderResponse.class)
        .without(SerializationFeature.INDENT_OUTPUT);
~~~

Có thể dùng hai instance này từ nhiều thread khi cấu hình của chúng ổn định và serializer/deserializer được sử dụng cũng an toàn đồng thời.

### 4.1. Tạo reader theo kiểu đích

~~~java
ObjectReader orderReader = mapper.readerFor(OrderRequest.class);
ObjectReader eventReader = mapper.readerFor(DomainEvent.class);
~~~

Sau đó đọc nhiều input:

~~~java
OrderRequest first = orderReader.readValue(firstJson);
OrderRequest second = orderReader.readValue(secondJson);
~~~

Reader đã biết kiểu đích và cấu hình cần dùng. Điều này giúp code thể hiện rõ contract của từng đường đọc và tránh lặp lại lựa chọn kiểu trong nhiều nơi.

Với generic type:

~~~java
ObjectReader pageReader = mapper.readerFor(
        new TypeReference<ApiEnvelope<List<OrderResponse>>>() {}
);
~~~

Hoặc tạo JavaType một lần:

~~~java
JavaType pageType = mapper.getTypeFactory()
        .constructParametricType(
                ApiEnvelope.class,
                mapper.getTypeFactory().constructCollectionType(
                        List.class,
                        OrderResponse.class
                )
        );

ObjectReader pageReader = mapper.readerFor(pageType);
~~~

Dùng reader đã gắn generic type giúp tránh lặp lại logic dựng kiểu và làm rõ kiểu dữ liệu mong đợi. Nếu kiểu generic được dùng thường xuyên trên đường nóng, có thể giữ reader tương ứng như một field dùng chung.

### 4.2. Tạo writer theo kiểu gốc

~~~java
ObjectWriter responseWriter = mapper.writerFor(OrderResponse.class);
ObjectWriter eventWriter = mapper.writerFor(DomainEvent.class);
~~~

Ghi output:

~~~java
String responseJson = responseWriter.writeValueAsString(response);
String eventJson = eventWriter.writeValueAsString(event);
~~~

writerFor() khai báo root type cho serialization. Điều này đặc biệt hữu ích khi muốn serialization tuân theo kiểu contract, ví dụ một interface đa hình. Hãy chọn đúng kiểu root mà hợp đồng yêu cầu.

### 4.3. Reader/writer cho nhiều định dạng output

Có thể tạo writer riêng cho output compact và pretty:

~~~java
ObjectWriter compact = mapper.writerFor(OrderResponse.class);
ObjectWriter pretty = mapper.writerFor(OrderResponse.class)
        .withDefaultPrettyPrinter();
~~~

Output compact phù hợp cho trao đổi giữa service hoặc lưu trữ có giới hạn; pretty output phù hợp cho log phát triển, file cấu hình hoặc tài liệu. Không bật pretty printing cho mọi payload production nếu không cần vì nó làm tăng kích thước output và chi phí ghi.

## 5. Mẫu cấu hình ổn định ở cấp ứng dụng

Một cách tổ chức đơn giản là gom mapper, reader và writer thường dùng vào một component:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonCodec {
    private final ObjectMapper mapper;
    private final ObjectReader orderRequestReader;
    private final ObjectReader eventReader;
    private final ObjectWriter orderResponseWriter;
    private final ObjectWriter eventWriter;

    public JsonCodec() {
        this.mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .build();

        this.orderRequestReader = mapper.readerFor(OrderRequest.class);
        this.eventReader = mapper.readerFor(DomainEvent.class);
        this.orderResponseWriter = mapper.writerFor(OrderResponse.class);
        this.eventWriter = mapper.writerFor(DomainEvent.class);
    }

    public OrderRequest readOrderRequest(String json) throws IOException {
        return orderRequestReader.readValue(json);
    }

    public DomainEvent readEvent(String json) throws IOException {
        return eventReader.readValue(json);
    }

    public String writeOrderResponse(OrderResponse response) throws IOException {
        return orderResponseWriter.writeValueAsString(response);
    }

    public String writeEvent(DomainEvent event) throws IOException {
        return eventWriter.writeValueAsString(event);
    }
}
~~~

JsonCodec có thể được tạo một lần và inject vào các service. Mapper và reader/writer là các field final, không thay đổi trong lúc xử lý request. Những method chỉ dùng reader/writer đã cấu hình.

Trong ứng dụng Spring, component này có thể là singleton bean. Nếu dự án đã dùng ObjectMapper do Spring Boot cấu hình, hãy tái sử dụng mapper được framework quản lý hoặc inject ObjectMapper đó vào codec. Tránh tạo một mapper thủ công khác bên trong từng service vì nó có thể bỏ qua module, customizer, naming strategy và các thiết lập của framework.

## 6. Cấu hình bằng dependency injection

Trong ứng dụng có framework, nơi phù hợp để cấu hình mapper là composition root hoặc cấu hình bean.

Ví dụ Spring:

~~~java
@Configuration
public class JacksonConfiguration {
    @Bean
    public ObjectMapper applicationObjectMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .build();
    }

    @Bean
    public ObjectReader orderRequestReader(ObjectMapper mapper) {
        return mapper.readerFor(OrderRequest.class);
    }

    @Bean
    public ObjectWriter orderResponseWriter(ObjectMapper mapper) {
        return mapper.writerFor(OrderResponse.class);
    }
}
~~~

Nếu Spring Boot đã cung cấp mapper auto-configured, cần kiểm tra cơ chế cấu hình hiện có trước khi khai báo một ObjectMapper bean mới. Khai báo bean riêng có thể thay đổi hoặc thay thế auto-configuration tùy phiên bản và điều kiện. Trong nhiều dự án, dùng Jackson2ObjectMapperBuilderCustomizer, các bean Module, hoặc cơ chế tùy chỉnh được framework hỗ trợ sẽ giữ cấu hình nhất quán hơn.

Không tạo mapper trong constructor của từng request-scoped controller hoặc trong method service. Mapper nên có vòng đời ứng dụng; reader/writer thường dùng có thể là singleton bean hoặc field final của codec.

## 7. Tạo biến thể reader mà không sửa mapper

ObjectReader có các phương thức tạo biến thể theo feature, schema, injectable values và các tùy chọn khác. Vì reader bất biến, có thể tạo biến thể tại nơi cần:

~~~java
ObjectReader baseReader = mapper.readerFor(ImportRecord.class);

ObjectReader tolerantReader = baseReader
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader strictReader = baseReader
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Ví dụ này giữ cùng mapper và cùng kiểu đích, nhưng hai reader có chính sách unknown-property khác nhau. Nên dùng hai chính sách như vậy chỉ khi có hai hợp đồng đầu vào thực sự khác nhau, ví dụ một integration cũ cho phép field mở rộng còn request nội bộ yêu cầu schema chặt.

Không tạo hàng nghìn biến thể tùy theo dữ liệu người dùng. Reader/writer nhẹ, nhưng một cache vô hạn theo key do client kiểm soát vẫn có thể gây giữ bộ nhớ không cần thiết. Cache các cấu hình hữu hạn, có tên rõ ràng; còn biến thể ít dùng có thể tạo tại chỗ.

## 8. Tạo biến thể writer mà không sửa mapper

Tương tự, ObjectWriter có thể tạo biến thể theo feature:

~~~java
ObjectWriter baseWriter = mapper.writerFor(AuditEvent.class);

ObjectWriter compactWriter = baseWriter
        .without(SerializationFeature.INDENT_OUTPUT);

ObjectWriter prettyWriter = baseWriter
        .with(SerializationFeature.INDENT_OUTPUT);
~~~

Hoặc:

~~~java
ObjectWriter prettyWriter = mapper.writerFor(AuditEvent.class)
        .withDefaultPrettyPrinter();
~~~

Mỗi biến thể có cấu hình riêng, không làm thay đổi writer gốc hay mapper dùng chung. Đây là cách phù hợp để chọn output format theo mục đích mà không tạo race condition.

Không nên bật/tắt SerializationFeature trên mapper singleton trong một method. Việc thay đổi cấu hình toàn cục trong lúc các thread khác serialize có thể khiến output không nhất quán.

## 9. readerForUpdating() là trường hợp cần thận trọng

Một ObjectReader thông thường có thể được chia sẻ vì nó giữ cấu hình bất biến. Nhưng reader được tạo bằng:

~~~java
ObjectReader updateReader = mapper.readerForUpdating(existingObject);
~~~

sẽ giữ tham chiếu tới object đích cần cập nhật. Nếu existingObject là mutable và được nhiều thread truy cập, reader đó không còn là một cấu hình thuần túy độc lập với request. Chia sẻ nó có thể khiến nhiều thao tác ghi vào cùng một object.

Không giữ một reader đang gắn với một entity/user object mutable làm singleton. Tạo reader update tại nơi xử lý object cụ thể:

~~~java
public void applyPatch(UserProfile profile, String patchJson)
        throws IOException {
    mapper.readerForUpdating(profile).readValue(patchJson);
}
~~~

Hoặc giữ reader base theo kiểu rồi dùng API update riêng theo từng target nếu phù hợp. Điều quan trọng là không chia sẻ target mutable ngoài phạm vi đồng bộ hóa và vòng đời nghiệp vụ của nó.

ObjectReader bất biến về cấu hình không có nghĩa object đích mà nó tham chiếu cũng bất biến hoặc an toàn đồng thời.

## 10. ObjectMapper.copy() không phải cách tạo biến thể rẻ cho mỗi request

Có thể sao chép mapper:

~~~java
ObjectMapper copy = mapper.copy();
~~~

Cách này tạo mapper mới với cấu hình được sao chép, nhưng không nên dùng trong đường xử lý thường xuyên để bật/tắt một feature. Việc copy mapper tốn kém và tương đương một thao tác khởi tạo mapper mới về mặt chi phí tương đối; nó không phải một reader/writer nhẹ.

Nếu chỉ cần thay đổi feature đọc/ghi, dùng:

~~~java
ObjectReader reader = mapper.readerFor(Request.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter writer = mapper.writerFor(Response.class)
        .withDefaultPrettyPrinter();
~~~

Nếu ứng dụng thật sự cần hai bộ cấu hình độc lập, ví dụ mapper JSON công khai và mapper đọc snapshot nội bộ, hãy tạo hai mapper riêng một lần lúc khởi động. Không copy mapper cho mỗi message.

## 11. Tái sử dụng JsonFactory và tránh tạo parser/generator thừa

ObjectMapper thường quản lý JsonFactory của nó. Factory tạo JsonParser để đọc input và JsonGenerator để ghi output. Tái sử dụng mapper cũng giúp tái sử dụng factory và các cơ chế buffer nội bộ.

Không cần tạo factory mới cho mỗi lần serialize:

~~~java
// Không cần tạo factory mới trong từng lần gọi.
JsonFactory factory = new JsonFactory();
ObjectMapper mapper = new ObjectMapper(factory);
~~~

Thay vào đó, tạo mapper một lần:

~~~java
JsonFactory factory = new JsonFactory();
ObjectMapper mapper = new ObjectMapper(factory);
~~~

Sau đó gọi readValue() hoặc writeValue() cho mỗi input/output. Mapper sẽ tạo parser/generator cần thiết cho thao tác và quản lý vòng đời theo API được gọi.

Nếu ứng dụng tự tạo parser/generator để streaming, hãy tạo một instance cho mỗi stream và đóng đúng cách. Không chia sẻ cùng một parser/generator giữa các request đồng thời. Cấu hình factory (ví dụ stream constraints, feature parser/generator) phải hoàn tất trước khi dùng.

## 12. Module và custom configuration chỉ đăng ký một lần

Việc đăng ký module thường diễn ra ở giai đoạn khởi động:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .addModule(new Jdk8Module())
        .build();
~~~

Không gọi registerModule() mỗi lần request. Việc này vừa lặp cấu hình vừa làm thay đổi mapper đang được sử dụng. Nếu cần module khác cho một ranh giới tin cậy khác, hãy tạo mapper riêng với bộ module xác định.

findAndRegisterModules() có thể tự tìm module qua Java ServiceLoader:

~~~java
ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
~~~

Có thể dùng khi muốn auto-discovery lúc khởi động. Với hệ thống cần cấu hình dễ kiểm tra, đăng ký tường minh thường rõ ràng hơn vì thể hiện trực tiếp module nào được phép tham gia. Dù chọn cách nào, chỉ thực hiện một lần trước khi mapper được sử dụng.

## 13. Cache serializer/deserializer không phải cache kết quả JSON

ObjectMapper có cache nội bộ cho serializer và deserializer đã được xây dựng/phân giải. Cache này giữ metadata và logic chuyển đổi theo kiểu Java, giúp các lần xử lý sau tránh lặp lại một số công việc introspection và khởi tạo.

Điều đó không có nghĩa Jackson tự cache kết quả JSON của một object. Nếu serialize một object thay đổi liên tục, mapper vẫn phải đọc trạng thái object và ghi output mới. Nếu ứng dụng muốn cache payload đã serialize, đó là một lớp cache khác, cần có key, invalidation và chính sách nhất quán riêng.

Cũng không nên tự xây một cache serializer/deserializer khác nếu không có lý do cụ thể. Hãy tận dụng cache của mapper trước và chỉ tối ưu sau khi profiling cho thấy phần chi phí đó thực sự đáng kể.

## 14. Reader/writer typed giúp code rõ ràng và giảm công việc lặp

Ví dụ không tạo reader sẵn:

~~~java
OrderRequest request = mapper.readValue(json, OrderRequest.class);
~~~

Ví dụ dùng reader typed:

~~~java
private final ObjectReader orderReader =
        mapper.readerFor(OrderRequest.class);

OrderRequest request = orderReader.readValue(json);
~~~

Cả hai đều dùng cơ chế cache của mapper. Reader typed chủ yếu mang lại cấu hình đọc tái sử dụng và thể hiện contract rõ ràng; nó không đảm bảo mọi lần gọi nhanh hơn đáng kể trong mọi workload. Lợi ích thực tế phụ thuộc số lần đọc, kiểu dữ liệu, module và chi phí xử lý payload.

Tương tự với writer:

~~~java
private final ObjectWriter responseWriter =
        mapper.writerFor(OrderResponse.class);

String json = responseWriter.writeValueAsString(response);
~~~

Đừng xem reader/writer như một phép tối ưu tự động thay thế profiling. Chúng hữu ích vì cấu hình ổn định, dễ chia sẻ và giảm lặp code; lợi ích hiệu năng cụ thể cần đo.

## 15. Dùng đúng API cho dữ liệu lớn

Tái sử dụng mapper không loại bỏ chi phí tạo toàn bộ object graph. Nếu payload rất lớn, đọc cả document thành một List hoặc JsonNode có thể tiêu tốn nhiều bộ nhớ. Trong trường hợp đó, streaming hoặc đọc theo từng record có thể phù hợp hơn.

Ví dụ đọc một stream gồm nhiều JSON value tương thích với API sequence:

~~~java
try (MappingIterator<OrderLine> rows = mapper
        .readerFor(OrderLine.class)
        .readValues(inputStream)) {
    while (rows.hasNextValue()) {
        OrderLine row = rows.nextValue();
        process(row);
    }
}
~~~

MappingIterator cho phép xử lý từng giá trị mà không cần giữ toàn bộ danh sách trong bộ nhớ. Cần xác định rõ framing của input; một JSON array đơn, nhiều root JSON value và NDJSON là các format khác nhau. Chọn API/parser phù hợp với format thực tế.

Streaming cũng cần kiểm soát tài nguyên và lỗi giữa chừng. Nếu xử lý hàng triệu record, hãy cân nhắc batch size, transaction, backpressure và cách resume khi một record lỗi.

## 16. Tránh tạo String trung gian khi có thể dùng stream/byte

Một đường xử lý có thể tạo nhiều bản sao dữ liệu:

~~~java
String json = mapper.writeValueAsString(event);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
outputStream.write(bytes);
~~~

Đường này tạo String rồi chuyển String thành byte array. Nếu consumer cuối cùng nhận stream hoặc byte array, có thể ghi trực tiếp:

~~~java
mapper.writeValue(outputStream, event);
~~~

Hoặc:

~~~java
byte[] bytes = mapper.writeValueAsBytes(event);
~~~

Chọn API theo nơi nhận dữ liệu. Nếu cần log/debug hoặc xử lý string, writeValueAsString() phù hợp. Nếu cần gửi HTTP body qua OutputStream, ghi trực tiếp có thể tránh một bước trung gian. Cần đo lường vì framework HTTP có thể có cơ chế buffering riêng.

Ở chiều đọc, nếu dữ liệu đã là InputStream, dùng overload nhận stream thay vì đọc hết thành String rồi mới parse, trừ khi ứng dụng thật sự cần giữ nội dung text.

## 17. Tránh convert qua JSON khi không cần

Một anti-pattern khác là chuyển object thành JSON string rồi parse lại để đổi kiểu:

~~~java
String json = mapper.writeValueAsString(source);
Target target = mapper.readValue(json, Target.class);
~~~

Nếu chỉ cần chuyển đổi một object Java sang kiểu khác theo quy tắc Jackson, có thể dùng:

~~~java
Target target = mapper.convertValue(source, Target.class);
~~~

convertValue() dùng cơ chế databinding nội bộ và tránh việc ứng dụng tạo rồi parse một chuỗi JSON trung gian. Tuy nhiên, đây vẫn là một lần chuyển đổi có chi phí; không dùng nó như một cơ chế copy object miễn phí. Với mapping nghiệp vụ quan trọng, mapper DTO tường minh có thể dễ kiểm soát hơn.

Nếu source và target có semantics khác nhau, hãy validate và ánh xạ rõ ràng thay vì dựa vào coercion ngầm.

## 18. Đừng tạo cache reader/writer vô hạn

Reader và writer nhẹ, nhưng cache chúng theo mọi tổ hợp có thể dẫn tới số lượng instance lớn:

~~~java
// Không tạo cache vô hạn dựa trên dữ liệu client.
Map<String, ObjectReader> readersByClientOption;
~~~

Nếu client có thể gửi tùy ý kiểu, feature hoặc tên format rồi tạo một entry mới, cache sẽ tăng liên tục. Chỉ cache các biến thể có tập hữu hạn và được xác định bởi code ứng dụng.

Một bộ cache hợp lý có thể gồm:

- Reader cho từng DTO request phổ biến.
- Reader cho một số schema/version đã công bố.
- Writer cho từng response/event root type.
- Writer compact và pretty nếu cả hai thực sự được dùng.

Không cần cache mọi biến thể một lần. ObjectReader.with(...) và ObjectWriter.with(...) được thiết kế để tạo cấu hình mới nhẹ khi cần.

## 19. Cấu hình theo trust boundary và định dạng

Không nên dùng một mapper với chính sách quá rộng chỉ để tiện tái sử dụng cho mọi nguồn. Một ứng dụng có thể cần:

- Mapper cho JSON API công khai.
- Mapper cho message nội bộ.
- Mapper cho YAML config.
- Mapper cho file import có schema khác.

Mỗi mapper có thể được cấu hình một lần và tái sử dụng. Ví dụ JSON và YAML dùng hai factory khác nhau:

~~~java
ObjectMapper jsonMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();

ObjectMapper yamlMapper = new ObjectMapper(new YAMLFactory())
        .registerModule(new JavaTimeModule());
~~~

Hai mapper có thể dùng chung DTO nhưng parser và scalar semantics khác nhau. Không đổi factory hoặc format của mapper sau khi đã sử dụng; tạo instance riêng cho từng format ở giai đoạn khởi động.

Nếu mapper public và mapper internal có subtype allowlist, coercion hoặc unknown-property policy khác nhau, hãy cấu hình chúng riêng. Tái sử dụng nghĩa là tái sử dụng instance trong đúng phạm vi chính sách, không phải ép mọi nguồn dữ liệu dùng cùng một cấu hình.

## 20. Cấu hình reader/writer cho version của contract

Nếu một service hỗ trợ nhiều version request, có thể tạo reader riêng cho từng DTO/version:

~~~java
private final ObjectReader v1Reader =
        mapper.readerFor(CreateOrderV1.class);

private final ObjectReader v2Reader =
        mapper.readerFor(CreateOrderV2.class);
~~~

Tương tự writer:

~~~java
private final ObjectWriter v1Writer =
        mapper.writerFor(OrderResponseV1.class);

private final ObjectWriter v2Writer =
        mapper.writerFor(OrderResponseV2.class);
~~~

Việc phân tách reader/writer làm rõ contract và tránh đổi naming strategy hoặc feature toàn cục giữa các request. Nếu chỉ một vài feature khác nhau, có thể tạo reader/writer variant bằng with(...); nếu schema khác nhau đáng kể, DTO riêng thường dễ quản lý hơn.

Không suy luận version từ một field tùy ý rồi bật cấu hình mapper toàn cục. Hãy chọn reader/DTO theo route, media type hoặc version đã xác thực trong protocol.

## 21. Đo hiệu năng đúng cách

Không nên kết luận mapper dùng chung nhanh hơn bao nhiêu lần chỉ từ một lần gọi System.nanoTime(). Kết quả dễ bị ảnh hưởng bởi JIT warmup, class loading, GC, kích thước payload và trạng thái cache.

Khi cần benchmark:

1. Dùng workload đại diện cho payload production.
2. So sánh mapper mới mỗi lần với mapper được tái sử dụng.
3. Tách thời gian khởi tạo mapper khỏi thời gian đọc/ghi.
4. Có warmup và nhiều fork nếu dùng JMH.
5. Đo cả throughput, latency và allocation/GC.
6. Bao gồm module, custom serializer/deserializer và cấu hình thật.
7. Kiểm tra output/đối tượng kết quả để tránh benchmark bị tối ưu bỏ.
8. Đo riêng trường hợp payload nhỏ và payload lớn.

Ví dụ benchmark nên dùng JMH thay vì một vòng lặp đo thời gian thủ công:

~~~java
@State(Scope.Benchmark)
public class JacksonBenchmark {
    private ObjectMapper sharedMapper;
    private ObjectReader reader;
    private String input;

    @Setup(Level.Trial)
    public void setup() {
        sharedMapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();

        reader = sharedMapper.readerFor(OrderRequest.class);
        input = loadRepresentativeJson();
    }

    @Benchmark
    public OrderRequest reuseMapperAndReader() throws IOException {
        return reader.readValue(input);
    }

    @Benchmark
    public OrderRequest createMapperPerCall() throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        return mapper.readValue(input, OrderRequest.class);
    }
}
~~~

Benchmark này chỉ minh họa cách bố trí so sánh; trong dự án thực tế cần dùng dependency JMH, chuẩn bị input phù hợp và kiểm tra cả cấu hình module tương đương ở hai nhánh. Không nên coi con số từ benchmark mẫu là kết quả áp dụng cho mọi ứng dụng.

## 22. Theo dõi allocation và payload, không chỉ thời gian CPU

Một thay đổi có thể giảm CPU nhưng tăng bộ nhớ, hoặc tăng throughput nhưng làm latency tail xấu đi. Với Jackson, các yếu tố thường đáng quan sát gồm:

- Số mapper được tạo trong một khoảng thời gian.
- Số parser/generator và lượng buffer được cấp phát.
- Số byte của input/output.
- Số object được tạo trong quá trình binding.
- Tỷ lệ payload được đọc vào JsonNode hoặc String toàn bộ.
- Số lần gọi custom serializer/deserializer.
- GC pause và allocation rate.
- Latency p50, p95, p99 của endpoint hoặc consumer.

Mapper reuse giúp tránh khởi tạo mapper lặp lại, nhưng không loại bỏ allocation của DTO, collection, string và parser cho từng lần xử lý. Nếu allocation vẫn cao, hãy xem cấu trúc payload, cách dùng Tree Model, việc copy collection hoặc chuyển đổi qua nhiều representation.

## 23. Những lỗi thường gặp

### 23.1. Tạo ObjectMapper trong controller/service method

Mỗi request tạo mapper mới, bỏ lỡ cache và lặp cấu hình. Tạo mapper ở startup và inject/reuse.

### 23.2. Đăng ký module sau khi đã bắt đầu đọc/ghi

Thay đổi cấu hình mapper trong lúc các thread đang dùng có thể tạo hành vi khó đoán. Hoàn tất cấu hình trước khi publish mapper cho ứng dụng.

### 23.3. Bật/tắt feature trên singleton mapper

Đây là thay đổi trạng thái toàn cục. Dùng reader/writer variant bất biến.

### 23.4. Chia sẻ readerForUpdating() gắn với object mutable

Reader có thể giữ target update. Tạo reader update theo từng object hoặc đồng bộ target theo đúng vòng đời.

### 23.5. Dùng ObjectMapper.copy() cho mỗi thao tác

Copy mapper không nhẹ như tạo reader/writer variant. Chỉ tạo mapper riêng một lần khi thật sự cần bộ cấu hình độc lập.

### 23.6. Tạo parser/generator và không đóng

Parser/generator làm việc với stream và tài nguyên. Dùng try-with-resources khi tự tạo; không giữ instance qua nhiều request.

### 23.7. Dùng một mapper cho mọi trust boundary

Mapper nội bộ có thể có cấu hình khác mapper public. Tạo mapper riêng theo chính sách và tái sử dụng từng instance trong đúng phạm vi.

### 23.8. Cache mọi reader/writer không giới hạn

Cache cấu hình hữu hạn, do ứng dụng kiểm soát. Tránh key cache đến từ input tùy ý.

### 23.9. Nghĩ reader/writer loại bỏ mọi chi phí chuyển đổi

Reader/writer giúp tái sử dụng cấu hình và kiểu gốc; payload vẫn cần parse, allocate object và serialize. Đo hiệu năng thực tế trước khi khẳng định mức cải thiện.

### 23.10. Benchmark khi chưa warmup

Đo một lần thường phản ánh class loading/JIT hơn là hiệu năng ổn định. Dùng JMH hoặc công cụ benchmark phù hợp.

## 24. Mẫu triển khai gọn cho ứng dụng

Ví dụ sau thể hiện các nguyên tắc chính trong một codec:

~~~java
public final class ApplicationJsonCodec {
    private final ObjectMapper mapper;
    private final ObjectReader createOrderReader;
    private final ObjectWriter orderResponseWriter;
    private final ObjectWriter prettyOrderResponseWriter;

    public ApplicationJsonCodec() {
        mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .build();

        createOrderReader = mapper.readerFor(CreateOrderRequest.class);

        ObjectWriter baseWriter = mapper.writerFor(OrderResponse.class);
        orderResponseWriter = baseWriter;
        prettyOrderResponseWriter = baseWriter.withDefaultPrettyPrinter();
    }

    public CreateOrderRequest readCreateOrder(String json) throws IOException {
        return createOrderReader.readValue(json);
    }

    public String writeOrderResponse(OrderResponse response) throws IOException {
        return orderResponseWriter.writeValueAsString(response);
    }

    public String writePrettyOrderResponse(OrderResponse response) throws IOException {
        return prettyOrderResponseWriter.writeValueAsString(response);
    }
}
~~~

Tạo ApplicationJsonCodec một lần ở startup và chia sẻ nó qua dependency injection. Các field mapper/reader/writer không thay đổi sau constructor. Nếu cần một reader/writer với cấu hình khác, tạo biến thể từ base reader/writer mà không mutate mapper dùng chung.

## 25. Checklist quyết định

Trước khi đưa Jackson vào một đường xử lý thường xuyên, hãy xác định:

- Mapper được tạo ở đâu và có được tái sử dụng không?
- Module, mix-in, feature và naming strategy đã được cấu hình trước lần đọc/ghi đầu tiên chưa?
- Có method nào đang bật/tắt feature trên mapper singleton không?
- Reader/writer cho DTO hoặc event thường dùng đã được tạo sẵn chưa?
- Có reader update nào giữ tham chiếu đến object mutable được chia sẻ không?
- Parser/generator tự tạo có được đóng đúng cách không?
- Có tạo JSON String trung gian trong khi có thể ghi trực tiếp vào stream/byte không?
- Có đọc payload lớn thành toàn bộ List/JsonNode khi streaming phù hợp hơn không?
- Các mapper cho JSON/YAML hoặc trust boundary khác nhau có được tách rõ không?
- Benchmark có đại diện payload và cấu hình production không?

## 26. Kết luận

Tái sử dụng Jackson hiệu quả bắt đầu từ vòng đời cấu hình ổn định. Hãy tạo ObjectMapper một lần cho mỗi bộ chính sách ở giai đoạn khởi động, đăng ký module và cấu hình feature trước khi dùng, rồi chia sẻ mapper giữa các thread. Với các kiểu dữ liệu và contract thường gặp, tạo sẵn ObjectReader và ObjectWriter; chúng là cấu hình bất biến, nhẹ và có thể tái sử dụng. Khi cần thay đổi nhỏ cho một thao tác, tạo biến thể bằng with(...) hoặc without(...) thay vì thay đổi mapper singleton.

Cần giữ ranh giới rõ: reader/writer thông thường có thể chia sẻ, nhưng reader từ readerForUpdating() có thể giữ object mutable cụ thể; mapper đã cấu hình xong có thể dùng đồng thời, nhưng custom serializer/deserializer vẫn phải an toàn thread; mapper reuse giảm chi phí khởi tạo nhưng không thay thế streaming, giảm allocation hoặc benchmark. Cấu hình tập trung, reader/writer typed, quản lý tài nguyên đúng cách và đo bằng workload thực tế sẽ giúp hệ thống có hiệu năng ổn định, output nhất quán và code dễ bảo trì.

