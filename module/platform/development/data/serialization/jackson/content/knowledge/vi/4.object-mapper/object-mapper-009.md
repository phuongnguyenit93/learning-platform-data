# Sao chép cấu hình và tránh thay đổi mapper dùng chung ngoài ý muốn

Trong ứng dụng Java dùng Jackson, `ObjectMapper` thường được tạo một lần rồi dùng lại ở nhiều service hoặc request. Cách tổ chức này giúp tái sử dụng module, annotation, naming strategy và các cấu hình chung. Tuy nhiên, `ObjectMapper` là đối tượng có API cấu hình thay đổi được. Nếu một thành phần thay đổi cấu hình của mapper dùng chung sau khi ứng dụng đã bắt đầu serialize hoặc deserialize, những thành phần khác có thể nhận hành vi khác với dự kiến.

Jackson cung cấp ba hướng xử lý chính cho nhu cầu cấu hình khác nhau:

- Cấu hình `ObjectMapper` một lần trước khi dùng chung.
- Tạo `ObjectReader` hoặc `ObjectWriter` cho một kiểu đọc/ghi hoặc một thao tác có tùy chọn riêng.
- Dùng `ObjectMapper.copy()` khi thực sự cần một mapper độc lập với cấu hình nền.

Chọn đúng cách giúp giữ cấu hình chung ổn định, tránh ảnh hưởng giữa các request và vẫn đáp ứng được những trường hợp cần định dạng JSON riêng.

## 1. Vì sao cần tránh thay đổi ObjectMapper dùng chung?

`ObjectMapper` là điểm vào chính của Jackson Databind. Nó giữ cấu hình serialize, deserialize, module đã đăng ký, mix-in, naming strategy, subtype resolver, factory và nhiều thành phần phục vụ ánh xạ dữ liệu.

Trong ứng dụng có dependency injection, mapper thường được tạo như một singleton bean và được nhiều thành phần sử dụng. Ví dụ trong Spring Boot, ứng dụng thường nhận mapper đã được framework cấu hình thông qua constructor injection:

```java
@Service
public class UserJsonService {
    private final ObjectMapper mapper;

    public UserJsonService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String toJson(User user) throws JsonProcessingException {
        return mapper.writeValueAsString(user);
    }
}
```

Đây là cách dùng phù hợp khi service chỉ thực hiện serialize theo cấu hình chung. Rủi ro xuất hiện khi một request thay đổi mapper trước khi sử dụng:

```java
// Không nên làm với mapper được chia sẻ giữa nhiều request.
mapper.enable(SerializationFeature.INDENT_OUTPUT);
String json = mapper.writeValueAsString(value);
```

Lệnh `enable()` thay đổi cấu hình của chính mapper. Nếu mapper được chia sẻ, request khác có thể nhận JSON có định dạng khác sau thời điểm thay đổi. Trong môi trường nhiều thread, việc thay đổi cấu hình đồng thời với hoạt động đọc/ghi còn có thể tạo ra hành vi khó dự đoán.

### 1.1. Thread-safe không có nghĩa là có thể cấu hình tùy ý bất cứ lúc nào

Jackson cho phép tái sử dụng `ObjectMapper` đồng thời từ nhiều thread **khi toàn bộ cấu hình của mapper đã hoàn tất trước lần đọc hoặc ghi đầu tiên**. Điều kiện về thời điểm cấu hình rất quan trọng.

Một mapper được cấu hình ở giai đoạn khởi tạo rồi dùng để đọc/ghi đồng thời là mô hình thông thường. Nhưng gọi các phương thức thay đổi cấu hình như `enable()`, `disable()`, `configure()`, `registerModule()`, `setDateFormat()` hoặc `addMixIn()` trong lúc mapper đang được dùng không phải là cách tạo tùy chọn riêng cho một thao tác.

Ngoài ra, cấu hình sau khi mapper đã xử lý dữ liệu có thể không có hiệu lực như mong muốn vì Jackson có cache serializer và deserializer. Không nên dựa vào việc đổi cấu hình giữa các lần gọi để tạo ra hành vi riêng cho từng request.

## 2. Phân biệt cấu hình nền và tùy chọn của một lần đọc/ghi

Trước khi chọn API, hãy xác định phạm vi mà cấu hình cần áp dụng:

| Phạm vi | Ví dụ | Cách phù hợp |
|---|---|---|
| Toàn ứng dụng | Đăng ký module Java Time, naming strategy chung | Cấu hình mapper lúc khởi tạo, trước khi dùng |
| Một kiểu đọc | Bỏ qua field JSON không biết khi đọc `User` | Tạo `ObjectReader` từ mapper |
| Một kiểu ghi | In đẹp JSON của báo cáo | Tạo `ObjectWriter` từ mapper |
| Một nhóm xử lý có cấu hình riêng | Bộ quy tắc serialize cho hệ thống tích hợp khác | Tạo và tái sử dụng mapper bằng `copy()` |
| Một thao tác rất đặc thù | Ghi theo view hoặc root name riêng | Tạo writer chuyên biệt cho thao tác |

Không nên thay đổi cấu hình nền chỉ để đáp ứng một lần đọc hoặc ghi. `ObjectReader` và `ObjectWriter` được thiết kế để tạo các biến thể bất biến từ mapper, còn `copy()` dùng khi cần một mapper khác có cấu hình ban đầu tương tự.

## 3. Dùng ObjectReader cho cấu hình deserialize riêng

`ObjectReader` là đối tượng đọc bất biến. Các phương thức cấu hình của reader trả về một reader mới; chúng không sửa mapper gốc. Vì vậy, có thể tạo reader với quy tắc riêng rồi tái sử dụng reader đó.

### 3.1. Chọn kiểu đích và feature riêng

Ví dụ, một API nhận payload có thể bổ sung field theo thời gian. Chỉ luồng nhập dữ liệu này cần bỏ qua thuộc tính chưa biết:

```java
ObjectReader tolerantUserReader = mapper
    .readerFor(User.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

User user = tolerantUserReader.readValue(json);
```

`without()` tạo reader mới với feature được tắt cho reader đó. Cấu hình mặc định của `ObjectMapper` không bị thay đổi. Một thành phần khác vẫn có thể sử dụng reader hoặc mapper với chính sách nghiêm ngặt hơn.

Chiều ngược lại, nếu muốn bật một feature chỉ cho một luồng đọc:

```java
ObjectReader strictReader = mapper
    .readerFor(User.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Reader có thể được giữ trong field `final` của service nếu kiểu đích và chính sách đọc ổn định:

```java
@Service
public class UserImportService {
    private final ObjectReader userReader;

    public UserImportService(ObjectMapper mapper) {
        this.userReader = mapper
            .readerFor(User.class)
            .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }

    public User read(String json) throws JsonProcessingException {
        return userReader.readValue(json);
    }
}
```

### 3.2. Tạo reader theo kiểu dữ liệu

`readerFor()` giúp xác định kiểu đích trước:

```java
ObjectReader userReader = mapper.readerFor(User.class);
ObjectReader userListReader = mapper.readerFor(
    new TypeReference<List<User>>() {}
);

User user = userReader.readValue(userJson);
List<User> users = userListReader.readValue(usersJson);
```

Có thể tạo reader từ `JavaType` nếu kiểu generic được xây dựng lúc chạy:

```java
JavaType listType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

ObjectReader reader = mapper.readerFor(listType);
List<User> users = reader.readValue(json);
```

Reader giữ kiểu đích và cấu hình đọc đã chọn, giúp các lời gọi sau ngắn gọn hơn và tránh phải cấu hình lại mapper chung.

### 3.3. Gắn thuộc tính cho một lần đọc

Reader hỗ trợ attributes để truyền dữ liệu ngữ cảnh cho serializer hoặc deserializer có sử dụng cơ chế injectable/attribute phù hợp:

```java
ObjectReader reader = mapper
    .readerFor(User.class)
    .withAttribute("source", "partner-api");

User user = reader.readValue(json);
```

Attribute không tự động trở thành field của DTO. Custom deserializer hoặc thành phần xử lý deserialize tương ứng phải chủ động đọc attribute đó. Đây là dữ liệu ngữ cảnh của thao tác, không phải cách thêm thuộc tính JSON vào object.

## 4. Dùng ObjectWriter cho cấu hình serialize riêng

`ObjectWriter` cũng là đối tượng bất biến. Có thể tạo writer cho một kiểu dữ liệu, một serialization feature hoặc một quy tắc hiển thị mà không sửa `ObjectMapper`.

### 4.1. In đẹp JSON cho một thao tác

Giả sử phần lớn API trả JSON compact, nhưng chức năng xuất báo cáo cần JSON dễ đọc:

```java
ObjectWriter prettyWriter = mapper
    .writer()
    .with(SerializationFeature.INDENT_OUTPUT);

String reportJson = prettyWriter.writeValueAsString(report);
```

Các lời gọi khác qua `mapper.writeValueAsString()` vẫn sử dụng cấu hình nền của mapper. Không cần bật `INDENT_OUTPUT` trên mapper dùng chung.

Nếu cần kiểu đích cố định, có thể dùng `writerFor()`:

```java
ObjectWriter userWriter = mapper.writerFor(User.class);
String json = userWriter.writeValueAsString(user);
```

### 4.2. Dùng pretty printer riêng

Có thể yêu cầu writer dùng default pretty printer:

```java
ObjectWriter prettyWriter = mapper.writer()
    .withDefaultPrettyPrinter();
```

Hoặc cung cấp một `PrettyPrinter` cụ thể nếu ứng dụng có định dạng xuất riêng:

```java
ObjectWriter writer = mapper.writer(customPrettyPrinter);
String json = writer.writeValueAsString(value);
```

Hãy lưu ý trạng thái của đối tượng tùy chỉnh. Reader/writer bất biến không làm cho một `PrettyPrinter` có mutable state trở nên thread-safe. Nếu writer được chia sẻ giữa nhiều thread, đối tượng được truyền vào cũng cần an toàn khi dùng đồng thời hoặc cần được tạo riêng theo cách phù hợp.

### 4.3. Dùng JSON View cho một đầu ra

Nếu lớp DTO sử dụng `@JsonView`, có thể tạo writer cho view cụ thể:

```java
public class Views {
    public static class Public {}
    public static class Internal extends Public {}
}

public class User {
    @JsonView(Views.Public.class)
    public String name;

    @JsonView(Views.Internal.class)
    public String email;
}
```

Tạo writer cho public view:

```java
ObjectWriter publicWriter = mapper.writerWithView(Views.Public.class);
String publicJson = publicWriter.writeValueAsString(user);
```

Writer chuyên biệt giúp chính sách hiển thị của một endpoint không làm thay đổi cấu hình serialize chung. Khi dùng view, cần hiểu cấu hình `DEFAULT_VIEW_INCLUSION` và cách annotation được áp dụng trong model của ứng dụng.

### 4.4. Root name và attributes

Writer cũng có thể áp dụng root name hoặc attributes cho một lần serialize:

```java
ObjectWriter writer = mapper
    .writer()
    .withRootName("user")
    .withAttribute("source", "admin-export");

String json = writer.writeValueAsString(user);
```

Root wrapping còn phụ thuộc cấu hình `SerializationFeature.WRAP_ROOT_VALUE` và quy tắc tên root. Attribute chỉ hữu ích khi serializer hoặc thành phần mở rộng có đọc attribute đó; nó không tự thêm field vào JSON.

## 5. Khi nào nên dùng ObjectMapper.copy()?

`ObjectMapper.copy()` tạo một mapper mới với cấu hình nền tương tự mapper nguồn. Mapper mới có thể được cấu hình độc lập cho một nhóm công việc.

Ví dụ, ứng dụng dùng mapper chung cho API nhưng cần một mapper riêng cho định dạng xuất dữ liệu nội bộ:

```java
ObjectMapper exportMapper = applicationMapper.copy();
exportMapper.enable(SerializationFeature.INDENT_OUTPUT);
exportMapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

String exportJson = exportMapper.writeValueAsString(exportData);
```

Việc gọi `enable()` và `setPropertyNamingStrategy()` tác động lên `exportMapper`. Cấu hình của `applicationMapper` không bị thay đổi bởi những thay đổi cấu hình mapper mới.

### 5.1. copy() khác với new ObjectMapper()

Hai cách tạo mapper có ý nghĩa khác nhau:

```java
ObjectMapper independentDefaults = new ObjectMapper();
ObjectMapper basedOnApplication = applicationMapper.copy();
```

`new ObjectMapper()` tạo mapper mới với cấu hình mặc định của Jackson và những module/configuration mà ứng dụng tự đăng ký sau đó. Nó không tự kế thừa cấu hình framework từ mapper đã được inject.

`applicationMapper.copy()` tạo mapper dựa trên cấu hình hiện tại của mapper nguồn. Đây thường là lựa chọn phù hợp khi muốn giữ module, naming strategy, mix-in và các quy tắc chung đã được thiết lập, sau đó điều chỉnh một số cấu hình cho một mục đích riêng.

### 5.2. copy() không phải thao tác miễn phí

Việc sao chép mapper có chi phí đáng kể, tương đương việc tạo và cấu hình một mapper mới. Không nên gọi `copy()` cho từng request hoặc từng object chỉ để thay đổi một serialization feature.

Nếu cần mapper riêng cho một luồng công việc ổn định, hãy tạo bản sao một lần khi service được khởi tạo rồi tái sử dụng:

```java
@Service
public class ExportService {
    private final ObjectMapper exportMapper;

    public ExportService(ObjectMapper applicationMapper) {
        this.exportMapper = applicationMapper.copy();
        this.exportMapper.enable(SerializationFeature.INDENT_OUTPUT);
    }

    public String export(Object value) throws JsonProcessingException {
        return exportMapper.writeValueAsString(value);
    }
}
```

Service singleton chỉ tạo bản sao trong constructor một lần. Mapper chuyên biệt được cấu hình trước khi phương thức `export()` sử dụng nó.

Nếu chỉ cần thay đổi định dạng của một lần ghi, `ObjectWriter` vẫn là lựa chọn gọn nhẹ hơn.

### 5.3. Hiểu giới hạn của bản sao

`copy()` tạo cấu hình mapper độc lập theo cơ chế của Jackson, nhưng không có nghĩa mọi object mà ứng dụng từng đăng ký đều được deep-copy. Các thành phần mở rộng do ứng dụng cung cấp có thể chứa state hoặc tham chiếu đến service bên ngoài, ví dụ custom serializer, custom deserializer, injectable values, handler hoặc collaborator khác.

Nếu những thành phần đó có mutable state, cần tự bảo đảm cách chia sẻ và thread-safety của chúng. Sao chép mapper không tự biến một custom serializer không an toàn thành thread-safe, cũng không sao chép sâu mọi object mà serializer đang tham chiếu.

## 6. Cấu hình mapper dùng chung đúng thời điểm

Một mapper dùng chung nên được cấu hình tập trung trong giai đoạn khởi tạo ứng dụng. Những thay đổi mang tính toàn cục như đăng ký module, mix-in, naming strategy hoặc chính sách xử lý feature cần được thực hiện trước khi mapper bắt đầu đọc/ghi.

Ví dụ tạo và cấu hình mapper độc lập trong ứng dụng Java không dùng container:

```java
public final class JsonMappers {
    private static final ObjectMapper SHARED = createMapper();

    private JsonMappers() {
    }

    private static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }

    public static ObjectMapper shared() {
        return SHARED;
    }
}
```

Sau khi `SHARED` được tạo và cấu hình xong, các thành phần chỉ sử dụng nó để đọc/ghi. Không bổ sung module hoặc đổi feature trong các phương thức xử lý request.

Trong framework có dependency injection, ưu tiên dùng mapper đã được framework cấu hình thay vì tự tạo một mapper mặc định mới ở từng service. Cách này giữ lại các module và quy tắc mà framework đã thiết lập.

### 6.1. Tránh cấu hình theo request trên singleton

Một anti-pattern dễ gặp là thay đổi mapper trước khi serialize:

```java
public String export(Object value, boolean pretty) throws JsonProcessingException {
    mapper.configure(SerializationFeature.INDENT_OUTPUT, pretty);
    return mapper.writeValueAsString(value);
}
```

Hai request có giá trị `pretty` khác nhau có thể chạy đồng thời. Một request bật feature trong khi request kia tắt feature trên cùng mapper. Kết quả không còn gắn chắc chắn với tham số của từng request.

Thay bằng writer riêng:

```java
public String export(Object value, boolean pretty) throws JsonProcessingException {
    ObjectWriter writer = mapper.writer();
    if (pretty) {
        writer = writer.with(SerializationFeature.INDENT_OUTPUT);
    }
    return writer.writeValueAsString(value);
}
```

Mỗi lần gọi tạo một cấu hình writer bất biến từ mapper nền. Request không cần thay đổi trạng thái cấu hình chung.

### 6.2. Tránh tạo mapper mới ở mọi nơi

Một anti-pattern khác là:

```java
public String toJson(User user) throws JsonProcessingException {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.writeValueAsString(user);
}
```

Đoạn mã tạo mapper mới mỗi lần gọi. Điều này tốn chi phí khởi tạo, làm mất cấu hình đã được framework đăng ký và có thể tạo ra hành vi khác nhau giữa các thành phần của ứng dụng.

Hãy inject mapper dùng chung đã cấu hình hoặc giữ một mapper chuyên biệt được tạo một lần. Nếu cần thay đổi chỉ ở một lần đọc/ghi, tạo `ObjectReader` hoặc `ObjectWriter` từ mapper nền.

## 7. Tình huống thực tế và cách chọn API

### Tình huống A: API trả JSON compact, chức năng export cần JSON dễ đọc

Không bật `INDENT_OUTPUT` trên mapper singleton. Tạo một `ObjectWriter` có feature này và tái sử dụng cho export:

```java
private final ObjectWriter exportWriter;

public ExportService(ObjectMapper mapper) {
    this.exportWriter = mapper.writer()
        .with(SerializationFeature.INDENT_OUTPUT);
}
```

### Tình huống B: Một endpoint cần bỏ qua field mới từ đối tác

Giữ chính sách mặc định của mapper cho các endpoint khác. Tạo reader chuyên biệt:

```java
private final ObjectReader partnerReader;

public PartnerImportService(ObjectMapper mapper) {
    this.partnerReader = mapper.readerFor(PartnerPayload.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
}
```

### Tình huống C: Một hệ thống tích hợp dùng naming strategy khác

Nếu chỉ thay đổi tên field cho đầu ra của một nhóm tích hợp, có thể dùng mapper bản sao được tạo một lần:

```java
ObjectMapper partnerMapper = applicationMapper.copy();
partnerMapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
```

Nếu sự khác biệt chỉ nằm ở serialize và có thể biểu diễn bằng annotation/view hoặc writer phù hợp, cân nhắc dùng `ObjectWriter` thay vì tạo mapper riêng.

### Tình huống D: Một kiểu dữ liệu cần module đặc biệt trên toàn ứng dụng

Nếu mọi thành phần đều cần hỗ trợ `LocalDate`, module Java Time là cấu hình nền. Đăng ký module trước khi mapper được sử dụng, thông qua cấu hình trung tâm hoặc cơ chế tích hợp của framework. Không đăng ký module lại mỗi khi một service cần serialize ngày tháng.

## 8. Bảng quyết định

| Nhu cầu | Nên dùng | Lý do |
|---|---|---|
| Thiết lập module và quy tắc chung | Cấu hình `ObjectMapper` lúc khởi tạo | Áp dụng thống nhất trước khi mapper được chia sẻ |
| Đọc một DTO với feature riêng | `ObjectReader` | Cấu hình đọc bất biến, không sửa mapper nền |
| Ghi JSON với pretty print | `ObjectWriter` | Tùy chọn chỉ thuộc thao tác ghi |
| Ghi theo JSON View hoặc root name | `ObjectWriter` | Tạo chính sách đầu ra chuyên biệt |
| Cần một nhóm quy tắc mapper độc lập, dùng lâu dài | `ObjectMapper.copy()` một lần | Giữ cấu hình nền rồi thay đổi bản sao |
| Tạo mapper mới cho từng request | Tránh cách này | Chi phí cao và dễ mất cấu hình framework |
| Thay đổi singleton mapper theo từng request | Tránh cách này | Có thể ảnh hưởng request khác và gây race condition |

## 9. Một số lưu ý về thread-safety và thành phần mở rộng

### ObjectReader và ObjectWriter bất biến

`ObjectReader` và `ObjectWriter` là các đối tượng cấu hình bất biến, được thiết kế để tái sử dụng an toàn giữa nhiều thread. Mỗi phương thức như `with()` hoặc `without()` trả về một biến thể mới. Có thể tạo chúng lúc khởi tạo service và lưu trong field `final`.

Tuy vậy, thread-safety của reader/writer không tự động bảo đảm mọi custom serializer, deserializer, pretty printer hoặc collaborator mà ứng dụng truyền vào đều an toàn. Trạng thái mutable bên trong các thành phần mở rộng vẫn cần được quản lý đúng cách.

### DateFormat và formatter tùy chỉnh

Các formatter có thể có trạng thái mutable. Tránh chia sẻ một formatter không thread-safe giữa các thao tác mà không hiểu cách Jackson sử dụng hoặc sao chép nó. Khi một định dạng chỉ cần cho một lần ghi, ưu tiên cấu hình trên writer:

```java
ObjectWriter writer = mapper.writer()
    .with(new SimpleDateFormat("yyyy-MM-dd"));
```

Nếu formatter được tái sử dụng, hãy xem xét thread-safety của loại formatter và vòng đời của nó. Với Java Time, các formatter thuộc `java.time.format` thường bất biến và an toàn khi dùng đồng thời.

### Module và custom serializer

Đăng ký module trước khi mapper được dùng. Một module có thể cung cấp serializer/deserializer tùy chỉnh; nếu các instance đó giữ state, hãy thiết kế chúng an toàn khi tái sử dụng hoặc tạo cấu trúc phù hợp với phạm vi sử dụng. Không nên đăng ký module lặp đi lặp lại để thay đổi hành vi cho một request.

### Nhiều mapper trong dependency injection

Nếu ứng dụng cần nhiều mapper có mục đích riêng, hãy đặt tên bean hoặc dùng qualifier để tránh inject nhầm:

```java
@Service
public class ExportService {
    private final ObjectMapper exportMapper;

    public ExportService(@Qualifier("exportObjectMapper") ObjectMapper exportMapper) {
        this.exportMapper = exportMapper;
    }
}
```

Việc có nhiều mapper không phải vấn đề nếu mỗi mapper có trách nhiệm rõ ràng, được cấu hình trước khi sử dụng và được tái sử dụng. Khó khăn xuất hiện khi không xác định được thành phần nào sở hữu cấu hình hoặc khi các mapper có chính sách khác nhau nhưng tên và nơi inject không rõ ràng.

## Kết luận

Hãy xem `ObjectMapper` dùng chung như cấu hình nền đã được hoàn tất trước khi ứng dụng bắt đầu xử lý dữ liệu. Dùng `ObjectReader` cho tùy chọn deserialize, `ObjectWriter` cho tùy chọn serialize và chỉ dùng `ObjectMapper.copy()` khi cần một mapper độc lập được tạo một lần rồi tái sử dụng. Cách tổ chức này giữ cấu hình chung ổn định, tránh việc một request vô tình thay đổi hành vi của request khác và vẫn cho phép từng luồng công việc có chính sách JSON riêng.
