# Quản lý vòng đời mapper và tính an toàn khi sử dụng đồng thời

Trong Jackson, **ObjectMapper** là thành phần trung tâm dùng để chuyển đổi giữa JSON và đối tượng Java. Mapper giữ cấu hình cho quá trình đọc, ghi và ánh xạ kiểu dữ liệu; đồng thời duy trì các bộ nhớ đệm serializer và deserializer để tăng hiệu năng. Vì vậy, cách tạo, cấu hình, chia sẻ và tái sử dụng mapper ảnh hưởng trực tiếp đến hiệu năng cũng như tính đúng đắn của ứng dụng khi có nhiều request chạy đồng thời.

Nguyên tắc quan trọng nhất là: **tạo mapper, hoàn tất toàn bộ cấu hình, sau đó mới chia sẻ và sử dụng mapper**. Một ObjectMapper đã được cấu hình xong có thể được dùng đồng thời từ nhiều luồng. Không nên thay đổi cấu hình của mapper dùng chung trong khi các luồng đang đọc hoặc ghi dữ liệu.

## 1. Vòng đời điển hình của ObjectMapper

Một mapper thường có vòng đời gắn với ứng dụng hoặc một vùng chức năng lớn, thay vì gắn với từng request:

~~~text
Khởi tạo ứng dụng
       │
       ▼
Tạo ObjectMapper / JsonMapper
       │
       ▼
Đăng ký module, naming strategy,
annotation policy và các feature
       │
       ▼
Hoàn tất cấu hình
       │
       ▼
Chia sẻ mapper đã cấu hình
       │
       ├──────── Request A ──► đọc / ghi JSON
       ├──────── Request B ──► đọc / ghi JSON
       └──────── Request C ──► đọc / ghi JSON
       │
       ▼
Ứng dụng kết thúc
~~~

Có thể chia vòng đời này thành các giai đoạn:

| Giai đoạn | Công việc | Lưu ý |
|---|---|---|
| Khởi tạo | Tạo ObjectMapper hoặc JsonMapper | Chọn cấu hình phù hợp với miền dữ liệu hoặc tích hợp. |
| Cấu hình | Đăng ký module, naming strategy, mix-in, serializer/deserializer và feature | Hoàn tất trước khi mapper được sử dụng. |
| Công bố | Đưa mapper vào singleton, dependency injection hoặc một thành phần quản lý chung | Chỉ công bố sau khi cấu hình hoàn tất. |
| Sử dụng | Nhiều request có thể gọi read/write đồng thời | Mỗi thao tác tạo parser/generator riêng khi cần xử lý luồng dữ liệu. |
| Kết thúc | Đóng tài nguyên I/O do ứng dụng sở hữu | Thông thường không cần đóng ObjectMapper sau mỗi request. |

Việc tái sử dụng mapper giúp Jackson giữ lại cache và tránh lặp lại chi phí khởi tạo, khám phá thuộc tính cũng như xây dựng serializer/deserializer.

## 2. Tạo và cấu hình mapper một lần

Với Jackson Databind 2.x hiện đại, có thể dùng JsonMapper builder để khai báo cấu hình ngay khi tạo đối tượng:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JacksonConfig {

    private JacksonConfig() {
    }

    public static JsonMapper createMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .enable(SerializationFeature.INDENT_OUTPUT)
            .build();
    }
}
~~~

Builder cho phép khai báo các quy tắc trước khi mapper được tạo hoàn chỉnh. Sau đó, ứng dụng có thể giữ một instance dùng chung:

~~~java
public final class JsonSupport {

    private static final ObjectMapper MAPPER =
        JacksonConfig.createMapper();

    private JsonSupport() {
    }

    public static ObjectMapper mapper() {
        return MAPPER;
    }
}
~~~

Trong ví dụ thực tế, phương thức tạo mapper có thể trả về ObjectMapper hoặc JsonMapper tùy kiểu mà ứng dụng muốn công bố. Điểm cốt yếu là instance chỉ được đưa vào sử dụng sau khi các module và feature đã được thiết lập.

Nếu không dùng builder, vẫn có thể cấu hình theo cách tuần tự:

~~~java
ObjectMapper mapper = new ObjectMapper();

mapper.registerModule(new JavaTimeModule());
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
mapper.enable(SerializationFeature.INDENT_OUTPUT);

// Chỉ chia sẻ mapper sau các bước cấu hình ở trên.
~~~

Cả hai cách đều hợp lệ. Builder làm rõ cấu hình ban đầu và giúp tránh việc một mapper chưa hoàn chỉnh bị đưa vào sử dụng quá sớm.

## 3. Vì sao nên tái sử dụng ObjectMapper?

ObjectMapper không chỉ là một lớp tiện ích bao quanh thao tác parse JSON. Nó còn quản lý cấu hình và các cache nội bộ:

- **Serializer cache:** lưu serializer đã được tìm và xây dựng cho các kiểu Java để dùng lại khi ghi.
- **Deserializer cache:** lưu deserializer đã được tìm và xây dựng cho các kiểu Java để dùng lại khi đọc.
- **Metadata về kiểu và thuộc tính:** Jackson khám phá getter, setter, field, constructor, annotation và quy tắc đặt tên để xác định cách chuyển đổi.
- **JsonFactory:** cung cấp parser và generator phục vụ việc đọc hoặc ghi JSON.
- **Module và cấu hình mở rộng:** bổ sung cách xử lý kiểu dữ liệu, serializer, deserializer và các quy tắc ánh xạ.

Nếu tạo mapper mới cho từng request, ứng dụng phải lặp lại nhiều công việc khởi tạo và mất lợi ích từ cache được tích lũy trong mapper trước đó. Ví dụ sau thường không phù hợp trong một endpoint được gọi thường xuyên:

~~~java
public User readUser(String json) throws JsonProcessingException {
    ObjectMapper mapper = new ObjectMapper();
    mapper.registerModule(new JavaTimeModule());
    return mapper.readValue(json, User.class);
}
~~~

Nên giữ mapper đã cấu hình ở một thành phần dùng chung:

~~~java
public User readUser(String json) throws JsonProcessingException {
    return JsonSupport.mapper().readValue(json, User.class);
}
~~~

Tái sử dụng mapper thường giảm chi phí tạo đối tượng và cho phép Jackson tận dụng cache. Ứng dụng cũng có một điểm cấu hình tập trung, dễ duy trì quy tắc JSON nhất quán.

## 4. ObjectMapper an toàn khi dùng đồng thời trong điều kiện nào?

Theo hợp đồng sử dụng của Jackson, ObjectMapper an toàn khi nhiều luồng cùng truy cập **nếu toàn bộ cấu hình đã được hoàn tất trước khi mapper được đọc hoặc ghi lần đầu**. Sau thời điểm đó, các luồng có thể gọi những thao tác như readValue, writeValueAsString hoặc tạo ObjectReader/ObjectWriter từ mapper dùng chung.

Ví dụ, nhiều request có thể dùng chung một mapper:

~~~java
private static final ObjectMapper MAPPER = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();

public User parse(String json) throws JsonProcessingException {
    return MAPPER.readValue(json, User.class);
}

public String render(User user) throws JsonProcessingException {
    return MAPPER.writeValueAsString(user);
}
~~~

Các request gọi parse và render có thể chạy đồng thời. Jackson quản lý những cấu trúc nội bộ cần thiết cho hoạt động đọc và ghi; ứng dụng không cần đặt synchronized quanh mọi lời gọi mapper thông thường.

Tính an toàn này phụ thuộc vào việc cấu hình đã ổn định. ObjectMapper vẫn có các phương thức thay đổi trạng thái cấu hình như enable, disable, registerModule, setDateFormat, setPropertyNamingStrategy hoặc addMixIn. Gọi các phương thức thay đổi cấu hình sau khi mapper đã bắt đầu được sử dụng có thể gây hành vi không nhất quán, đặc biệt khi nhiều luồng đang hoạt động và cache serializer/deserializer đã được tạo.

Do đó, không nên hiểu thread-safe là có thể tùy ý vừa đọc/ghi vừa chỉnh cấu hình trên cùng một instance. Hãy xem mapper dùng chung là một đối tượng đã hoàn tất cấu hình.

## 5. Những cách sử dụng gây lỗi đồng thời

### Thay đổi feature theo từng request

Đoạn mã sau có nguy cơ tạo race condition:

~~~java
public String toJson(Object value, boolean pretty)
        throws JsonProcessingException {
    if (pretty) {
        mapper.enable(SerializationFeature.INDENT_OUTPUT);
    } else {
        mapper.disable(SerializationFeature.INDENT_OUTPUT);
    }

    return mapper.writeValueAsString(value);
}
~~~

Giả sử request A muốn JSON có thụt lề và request B muốn JSON gọn. Hai request có thể xen kẽ giữa bước bật/tắt feature và bước ghi. Kết quả của một request có thể chịu ảnh hưởng từ cấu hình mà request còn lại vừa thay đổi.

Giải pháp phù hợp là tạo ObjectWriter riêng cho từng chính sách:

~~~java
private final ObjectWriter prettyWriter =
    mapper.writer().with(SerializationFeature.INDENT_OUTPUT);

private final ObjectWriter compactWriter =
    mapper.writer().without(SerializationFeature.INDENT_OUTPUT);

public String toJson(Object value, boolean pretty)
        throws JsonProcessingException {
    ObjectWriter writer = pretty ? prettyWriter : compactWriter;
    return writer.writeValueAsString(value);
}
~~~

Mỗi request chọn writer theo nhu cầu. Việc chọn writer không làm thay đổi cấu hình của mapper hoặc writer mà request khác đang dùng.

### Đăng ký module trong lúc xử lý request

Không nên đăng ký module theo từng request trên mapper dùng chung:

~~~java
public String serialize(Object value) throws JsonProcessingException {
    mapper.registerModule(new JavaTimeModule());
    return mapper.writeValueAsString(value);
}
~~~

Module nên được đăng ký trong giai đoạn khởi tạo. Việc thay đổi danh sách module sau khi mapper đã được dùng có thể làm cấu hình và cache không còn đồng nhất. Nếu hai nhóm chức năng thật sự cần các tập module khác nhau, hãy tạo hai mapper độc lập và hoàn tất cấu hình cho từng mapper trước khi chia sẻ.

### Chia sẻ đối tượng xử lý luồng

Mapper có thể được chia sẻ, nhưng không nên dùng chung một JsonParser hoặc JsonGenerator đang hoạt động giữa nhiều request. Parser và generator đại diện cho trạng thái của một luồng dữ liệu cụ thể; mỗi thao tác cần tài nguyên riêng phù hợp với input hoặc output của nó.

Ví dụ, có thể dùng cùng mapper để đọc hai chuỗi khác nhau:

~~~java
User first = mapper.readValue(firstJson, User.class);
User second = mapper.readValue(secondJson, User.class);
~~~

Mỗi lần đọc sẽ sử dụng trạng thái parser phù hợp cho dữ liệu của lần gọi đó. Không nên tự tạo một parser rồi chia sẻ parser đó cho nhiều luồng cùng tiêu thụ token.

## 6. Dùng ObjectReader và ObjectWriter cho chính sách theo thao tác

ObjectReader và ObjectWriter được thiết kế để cung cấp cấu hình đọc hoặc ghi cụ thể dựa trên mapper. Chúng bất biến: các phương thức như with và without trả về một reader hoặc writer mới với cấu hình tương ứng, thay vì thay đổi instance hiện tại.

| Thành phần | Trách nhiệm | Tính chất |
|---|---|---|
| ObjectMapper | Quản lý cấu hình chung, module và cơ chế ánh xạ | Có các phương thức thay đổi cấu hình; nên cấu hình xong trước khi dùng |
| ObjectReader | Thực hiện đọc với kiểu đích và chính sách đọc cụ thể | Bất biến, an toàn khi tái sử dụng giữa nhiều luồng |
| ObjectWriter | Thực hiện ghi với kiểu và chính sách đầu ra cụ thể | Bất biến, an toàn khi tái sử dụng giữa nhiều luồng |

Ví dụ, cùng một mapper có thể cung cấp reader nghiêm ngặt và reader dễ tiếp nhận trường lạ:

~~~java
ObjectReader strictUserReader = mapper.readerFor(User.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader tolerantUserReader = mapper.readerFor(User.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Tương tự, có thể dùng writer cho JSON dễ đọc và writer cho JSON gọn:

~~~java
ObjectWriter prettyUserWriter = mapper.writerFor(User.class)
    .with(SerializationFeature.INDENT_OUTPUT);

ObjectWriter compactUserWriter = mapper.writerFor(User.class)
    .without(SerializationFeature.INDENT_OUTPUT);
~~~

Các reader và writer có thể được tạo ở giai đoạn khởi tạo rồi lưu thành field dùng chung. Nếu một thao tác chỉ cần chính sách mặc định, có thể gọi trực tiếp mapper hoặc dùng reader/writer mặc định.

Ngoài feature, reader và writer còn hỗ trợ các thiết lập theo thao tác như kiểu đích, view, filter, root type hoặc attribute theo ngữ cảnh. Đây là nơi thích hợp để biểu diễn khác biệt giữa các API mà không phải sửa mapper dùng chung.

## 7. Khi nào cần nhiều ObjectMapper?

Một ứng dụng không nhất thiết chỉ có đúng một mapper. Nên dùng một mapper dùng chung khi các luồng dữ liệu có cùng chính sách ánh xạ cơ bản. Có thể cần các mapper độc lập khi hai miền tích hợp có quy tắc nền tảng khác nhau, chẳng hạn:

- Một API dùng snake_case, API khác dùng tên thuộc tính Java mặc định.
- Một nguồn dữ liệu cần module hoặc serializer/deserializer riêng.
- Hai định dạng JSON có quy tắc subtype, visibility hoặc annotation policy khác nhau.
- Một hệ thống cần cấu hình parser/generator khác biệt ở tầng JsonFactory.

Mỗi mapper độc lập cần được cấu hình hoàn chỉnh trước khi sử dụng. Không nên tạo mapper mới chỉ để thay đổi một feature nhỏ cho một lần gọi; ObjectReader hoặc ObjectWriter thường là lựa chọn nhẹ và rõ trách nhiệm hơn.

### Sao chép mapper bằng copy()

ObjectMapper cung cấp phương thức copy() để tạo mapper mới dựa trên cấu hình hiện tại:

~~~java
ObjectMapper baseMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();

ObjectMapper partnerMapper = baseMapper.copy();
partnerMapper.setPropertyNamingStrategy(
    PropertyNamingStrategies.SNAKE_CASE
);
~~~

Mapper được sao chép có thể được cấu hình độc lập sau khi tạo. Tuy nhiên, copy() không phải thao tác rẻ để gọi theo từng request; chi phí của nó tương đương đáng kể với việc tạo mapper mới. Hãy dùng khi thật sự cần một cấu hình mapper độc lập, ổn định cho một miền dữ liệu hoặc tích hợp riêng.

Nếu chỉ khác feature đọc hoặc ghi, ưu tiên tạo ObjectReader hoặc ObjectWriter từ mapper gốc.

## 8. Serializer và deserializer tùy chỉnh cũng phải an toàn khi chia sẻ

Thread-safety của ObjectMapper không tự động làm mọi đối tượng do ứng dụng đăng ký vào mapper trở nên an toàn. Jackson có thể tái sử dụng serializer và deserializer, vì vậy custom serializer/deserializer thường nên được thiết kế không có trạng thái thay đổi theo request.

Ví dụ, một serializer không nên lưu dữ liệu của lần gọi trước vào field rồi dùng lại ở lần gọi tiếp theo:

~~~java
public class UserSerializer extends JsonSerializer<User> {

    // Tránh lưu dữ liệu riêng của request vào field có thể bị thay đổi.

    @Override
    public void serialize(
            User value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeStartObject();
        generator.writeStringField("name", value.getName());
        generator.writeEndObject();
    }
}
~~~

Các biến cục bộ trong serialize hoặc deserialize phù hợp để giữ trạng thái tạm thời của một lần chuyển đổi. Nếu cần dữ liệu theo ngữ cảnh, hãy dùng cơ chế context mà Jackson cung cấp hoặc truyền dữ liệu qua đối tượng theo request; không biến serializer dùng chung thành nơi lưu trạng thái nghiệp vụ có thể thay đổi.

Tương tự, module, naming strategy, subtype resolver, injectable values và các thành phần mở rộng do ứng dụng tự viết cần được xem xét về khả năng chia sẻ. Nếu một thành phần giữ tham chiếu tới collection hoặc cấu hình mutable, ứng dụng không nên thay đổi collection đó sau khi đã đưa thành phần vào mapper đang được sử dụng.

## 9. Quản lý tài nguyên khi đọc và ghi

ObjectMapper được tái sử dụng lâu dài, còn stream, parser và generator gắn với từng thao tác I/O. Cần phân biệt vòng đời của mapper với vòng đời của tài nguyên dữ liệu:

- Với chuỗi JSON, mapper nhận chuỗi và thực hiện chuyển đổi mà không yêu cầu ứng dụng quản lý một stream bên ngoài.
- Với InputStream hoặc Reader do ứng dụng mở, ứng dụng cần xác định rõ quyền sở hữu và đóng tài nguyên theo hợp đồng của API đang dùng.
- Với OutputStream hoặc Writer, ứng dụng cần bảo đảm tài nguyên được flush/close đúng lúc và không dùng lại sau khi đã đóng.
- Không đóng tài nguyên dùng chung khi một request hoàn tất nếu request khác vẫn cần sử dụng tài nguyên đó.

Ví dụ quản lý stream do phương thức sở hữu:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    User user = mapper.readValue(input, User.class);
}
~~~

Trong ví dụ này, stream được đóng khi thoát khỏi khối try-with-resources. Mapper vẫn có thể được tái sử dụng cho lần đọc tiếp theo. Khi làm việc với API đọc/ghi stream, hãy kiểm tra tùy chọn tự đóng nguồn hoặc đích của parser/generator và quy định quyền sở hữu tài nguyên của ứng dụng để tránh đóng nhầm stream mà bên gọi còn cần dùng.

Thông thường không cần tạo rồi đóng một ObjectMapper sau mỗi lần đọc hoặc ghi. Mapper là thành phần cấu hình và cache có thể tồn tại suốt vòng đời ứng dụng; stream và parser/generator mới là tài nguyên gắn với từng lần xử lý.

## 10. Tích hợp trong ứng dụng Spring

Trong ứng dụng Spring hoặc Spring Boot, framework thường quản lý ObjectMapper được dùng bởi các bộ chuyển đổi HTTP message converter. Nếu muốn JSON của REST API tuân theo cấu hình chung, nên tùy chỉnh mapper do framework quản lý thông qua cơ chế cấu hình Jackson mà phiên bản Spring Boot đang sử dụng cung cấp, chẳng hạn đăng ký Module bean hoặc Jackson2ObjectMapperBuilderCustomizer ở các phiên bản tương ứng.

Ví dụ một module có thể được Spring Boot tự động phát hiện:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    public JavaTimeModule javaTimeModule() {
        return new JavaTimeModule();
    }
}
~~~

Khi ứng dụng khởi động, Spring xây dựng mapper và các converter dựa trên cấu hình. Các controller và service nên nhận mapper qua dependency injection khi thật sự cần thao tác trực tiếp, hoặc để converter thực hiện việc chuyển đổi request/response.

Tránh tự tạo một ObjectMapper mới trong từng controller nếu mục đích là thay đổi JSON của toàn bộ ứng dụng. Mapper tự tạo có thể không nhận các module, customizer hoặc quy tắc mà framework đã cấu hình. Nếu một tích hợp ngoài cần chính sách riêng, hãy khai báo mapper riêng như một bean có tên và phạm vi rõ ràng, cấu hình xong trước khi đưa vào sử dụng.

Tên API tùy chỉnh Jackson trong Spring phụ thuộc phiên bản Spring Boot và Jackson. Cần dùng cơ chế tương ứng với phiên bản dự án thay vì trộn cấu hình từ các thế hệ framework khác nhau.

## 11. Các nguyên tắc thiết kế nên áp dụng

Khi thiết kế lớp hỗ trợ JSON, có thể dựa vào những nguyên tắc sau:

1. Tạo mapper ở giai đoạn khởi tạo ứng dụng hoặc khởi tạo thành phần tích hợp.
2. Đăng ký toàn bộ module, mix-in, naming strategy, serializer/deserializer và feature trước lần đọc/ghi đầu tiên.
3. Chỉ công bố mapper sau khi cấu hình hoàn tất; sau đó coi cấu hình của nó là cố định.
4. Tái sử dụng mapper giữa các request thay vì tạo mapper mới cho mỗi lần chuyển đổi.
5. Dùng ObjectReader và ObjectWriter bất biến cho chính sách riêng theo thao tác hoặc theo API.
6. Dùng mapper riêng khi cần một bộ quy tắc ánh xạ nền tảng khác biệt và ổn định.
7. Không chia sẻ parser hoặc generator đang hoạt động giữa các luồng.
8. Thiết kế custom serializer, deserializer và module sao cho an toàn khi được gọi đồng thời.
9. Quản lý stream theo quyền sở hữu của ứng dụng; không nhầm vòng đời stream với vòng đời mapper.

Với cách tổ chức này, ObjectMapper đóng vai trò cấu hình JSON dùng chung và giữ cache trong suốt vòng đời phù hợp của ứng dụng. ObjectReader và ObjectWriter biểu diễn chính sách cho từng thao tác. Các request có thể chạy đồng thời mà không phải tranh chấp việc bật/tắt cấu hình trên một mapper mutable.
