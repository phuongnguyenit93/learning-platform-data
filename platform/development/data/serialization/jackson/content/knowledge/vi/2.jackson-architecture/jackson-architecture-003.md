# Mối quan hệ giữa ObjectMapper, ObjectReader và ObjectWriter

Trong Jackson Databind, `ObjectMapper`, `ObjectReader` và `ObjectWriter` cùng tham gia vào quá trình chuyển đổi giữa đối tượng Java và JSON, nhưng mỗi lớp đảm nhiệm một vai trò khác nhau:

- `ObjectMapper` là trung tâm cấu hình và điều phối việc ánh xạ dữ liệu.
- `ObjectReader` là cấu hình đọc JSON thành kiểu dữ liệu Java đã chọn.
- `ObjectWriter` là cấu hình ghi đối tượng Java thành JSON theo cách đã chọn.

Có thể hình dung `ObjectMapper` là nền tảng dùng chung của ứng dụng, còn `ObjectReader` và `ObjectWriter` là những cách sử dụng nền tảng đó với chính sách đọc hoặc ghi cụ thể. Cách tổ chức này giúp tái sử dụng cấu hình và bộ nhớ đệm của Jackson, đồng thời tránh phải thay đổi cấu hình toàn cục mỗi khi một thao tác có yêu cầu riêng.

## 1. Vị trí của ba lớp trong quá trình xử lý JSON

Jackson thường được sử dụng qua hai tầng chính:

1. **Streaming** đọc và ghi luồng token JSON. `JsonFactory` tạo `JsonParser` để đọc và `JsonGenerator` để ghi.
2. **Databind** ánh xạ token JSON với object Java. `ObjectMapper`, `ObjectReader` và `ObjectWriter` cung cấp API ở tầng này.

Luồng xử lý khái quát:

```text
Đọc JSON
String / File / InputStream / JsonParser
                 |
                 v
           ObjectReader
                 |
                 v
       Jackson Databind
                 |
                 v
       Deserializer + JavaType
                 |
                 v
             Java object

Ghi JSON
          Java object
                 |
                 v
           ObjectWriter
                 |
                 v
       Jackson Databind
                 |
                 v
        Serializer + JavaType
                 |
                 v
       JsonGenerator / output
                 |
                 v
             JSON

ObjectMapper cung cấp cấu hình và hạ tầng dùng chung cho Reader/Writer.
```

Sơ đồ này mô tả trách nhiệm ở mức khái niệm. Trong thực tế, `ObjectMapper` cũng cung cấp các phương thức đọc và ghi trực tiếp; các phương thức đó là lối sử dụng thuận tiện khi không cần tạo một chính sách đọc hoặc ghi riêng để tái sử dụng.

## 2. ObjectMapper: trung tâm cấu hình và điều phối

`ObjectMapper` thuộc package `com.fasterxml.jackson.databind`. Đây là API thường được ứng dụng khởi tạo một lần rồi chia sẻ cho nhiều nơi sử dụng.

Mapper tập hợp những thành phần Jackson cần để ánh xạ dữ liệu, chẳng hạn:

- Cấu hình đọc (`DeserializationConfig`) và cấu hình ghi (`SerializationConfig`).
- `JsonFactory` dùng để tạo parser và generator.
- Cơ chế tìm serializer và deserializer cho từng kiểu dữ liệu.
- Thông tin kiểu (`JavaType`), module đã đăng ký, quy tắc nhận diện thuộc tính và các bộ nhớ đệm liên quan.

Nhờ có mapper, ứng dụng không phải tự tạo serializer hoặc deserializer cho từng lần gọi thông thường. Jackson có thể tìm và tái sử dụng chúng theo kiểu dữ liệu và cấu hình tương ứng.

### 2.1. Khởi tạo và cấu hình

Ví dụ cấu hình một mapper dùng chung:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();

// Đăng ký hỗ trợ các kiểu ngày giờ của java.time.
mapper.registerModule(new JavaTimeModule());

// Ví dụ chính sách áp dụng chung cho ứng dụng.
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
mapper.enable(SerializationFeature.INDENT_OUTPUT);
```

`JavaTimeModule` thuộc dependency `jackson-datatype-jsr310`. Chỉ đăng ký module này khi ứng dụng có dependency tương ứng. Các module khác cũng cần được đăng ký trước khi mapper bắt đầu xử lý dữ liệu.

Ứng dụng có thể tạo mapper bằng builder, ví dụ `JsonMapper.builder()` ở các phiên bản Jackson hỗ trợ API này. Builder hữu ích khi muốn khai báo cấu hình theo chuỗi và tạo mapper sau khi đã hoàn tất các lựa chọn.

### 2.2. Đọc và ghi trực tiếp bằng ObjectMapper

Mapper có các phương thức tiện ích như `readValue`, `writeValue`, `writeValueAsString` và `writeValueAsBytes`:

```java
ObjectMapper mapper = new ObjectMapper();

User user = mapper.readValue(json, User.class);

String result = mapper.writeValueAsString(user);
```

Đây là lựa chọn dễ đọc cho những thao tác đơn giản, dùng cấu hình mặc định của mapper. Khi một loại dữ liệu cần chính sách riêng, hoặc một chính sách được sử dụng lặp lại ở nhiều nơi, nên tạo `ObjectReader` hoặc `ObjectWriter` tương ứng.

### 2.3. Vòng đời và tính an toàn khi dùng nhiều luồng

`ObjectMapper` có thể được chia sẻ giữa nhiều luồng nếu toàn bộ cấu hình được hoàn tất trước khi mapper được sử dụng lần đầu để đọc hoặc ghi. Đây là cách dùng phổ biến trong ứng dụng máy chủ: tạo mapper ở giai đoạn khởi tạo, đăng ký module và thiết lập feature, sau đó tái sử dụng.

Không nên thay đổi cấu hình mapper dùng chung trong lúc các luồng khác đang xử lý dữ liệu. Ví dụ, việc bật một feature trước request A rồi tắt nó trước request B có thể khiến các request chạy đồng thời quan sát cấu hình không như mong muốn. Với yêu cầu chỉ áp dụng cho một nhóm thao tác, hãy tạo reader hoặc writer riêng.

## 3. ObjectReader: chính sách đọc JSON

`ObjectReader` đại diện cho một cấu hình đọc cụ thể được tạo từ mapper. Reader thường xác định kiểu đích và có thể mang theo các lựa chọn như feature đọc, view, schema hoặc attribute dành cho quá trình deserialize.

### 3.1. Tạo reader theo kiểu dữ liệu

```java
ObjectReader userReader = mapper.readerFor(User.class);

User user = userReader.readValue(json);
```

Khi kiểu đích là kiểu generic, có thể tạo `JavaType` bằng `TypeFactory`:

```java
JavaType usersType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);

ObjectReader usersReader = mapper.readerFor(usersType);

List<User> users = usersReader.readValue(json);
```

Việc khai báo `JavaType` giúp Jackson biết cả kiểu phần tử bên trong collection. Nếu chỉ truyền `List.class`, thông tin kiểu `User` có thể bị mất và phần tử được ánh xạ thành kiểu tổng quát như `Map`.

### 3.2. Tạo chính sách riêng mà không sửa mapper

Giả sử phần lớn dữ liệu của ứng dụng tuân theo cấu hình chung, nhưng một nguồn dữ liệu bên ngoài có thể gửi thêm thuộc tính mà ứng dụng chưa biết. Có thể tạo reader riêng:

```java
ObjectReader externalUserReader = mapper.readerFor(User.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

User user = externalUserReader.readValue(externalJson);
```

`without(...)` tạo một reader mới với feature được tắt cho thao tác đọc đó. Các reader khác và cấu hình gốc của mapper vẫn giữ chính sách của chúng.

Tương tự, có thể bật một feature chỉ cho reader cần nó:

```java
ObjectReader flexibleListReader = mapper.readerFor(usersType)
        .with(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
```

Trong ví dụ này, reader chấp nhận đầu vào là một giá trị đơn ở vị trí Jackson cho phép xử lý như một mảng một phần tử. Không nên bật feature này toàn cục nếu chỉ một nguồn dữ liệu có định dạng như vậy.

### 3.3. Reader có thể được tái sử dụng

`ObjectReader` là đối tượng cấu hình bất biến: các phương thức như `with`, `without`, `forType` hoặc `withAttribute` trả về reader mới thay vì thay đổi reader hiện tại. Vì vậy, một reader đã được cấu hình có thể được lưu lại và dùng cho nhiều lần đọc, kể cả trong môi trường nhiều luồng.

```java
private final ObjectReader userReader = mapper.readerFor(User.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

public User parseUser(String json) throws IOException {
    return userReader.readValue(json);
}
```

Không cần tạo reader mới cho mọi chuỗi JSON nếu các lần đọc dùng cùng kiểu đích và cùng chính sách. Nếu chính sách khác nhau, tạo reader khác từ cùng mapper để thể hiện rõ ranh giới cấu hình.

## 4. ObjectWriter: chính sách ghi JSON

`ObjectWriter` là cấu hình ghi được tạo từ mapper. Writer có thể xác định kiểu gốc và các lựa chọn serialize như feature, view, pretty printer, root name hoặc schema.

### 4.1. Tạo writer theo kiểu dữ liệu

```java
ObjectWriter userWriter = mapper.writerFor(User.class);

String json = userWriter.writeValueAsString(user);
```

Có thể ghi ra các đích khác nhau bằng những phương thức `writeValue` tương ứng, chẳng hạn `File`, `OutputStream` hoặc `JsonGenerator`.

### 4.2. Áp dụng cách trình bày hoặc chính sách riêng

Ví dụ, một luồng xuất dữ liệu cần JSON dễ đọc khi kiểm tra thủ công:

```java
ObjectWriter prettyUserWriter = mapper.writerFor(User.class)
        .withDefaultPrettyPrinter();

String formattedJson = prettyUserWriter.writeValueAsString(user);
```

Một trường hợp khác là dùng JSON View để giới hạn những thuộc tính được xuất:

```java
public class UserViews {
    public static class PublicView { }
}

ObjectWriter publicUserWriter = mapper.writerFor(User.class)
        .withView(UserViews.PublicView.class);

String publicJson = publicUserWriter.writeValueAsString(user);
```

Các thuộc tính của `User` phải được đánh dấu view phù hợp bằng `@JsonView` thì view mới tạo ra sự khác biệt. Ví dụ:

```java
public class User {
    @JsonView(UserViews.PublicView.class)
    private String displayName;

    private String internalNote;

    // Constructor, getter và setter.
}
```

Khi dùng `publicUserWriter`, Jackson chỉ đưa các thuộc tính phù hợp với view theo quy tắc JSON View và cấu hình liên quan. Đây là chính sách trình bày dữ liệu; nó không thay thế việc kiểm soát quyền truy cập ở tầng nghiệp vụ.

### 4.3. Kiểu gốc và hợp đồng JSON

`writerFor(...)` cho phép khai báo kiểu gốc mà writer dùng khi serialize. Điều này hữu ích khi hợp đồng đầu ra yêu cầu Jackson xử lý theo một kiểu khai báo cụ thể, đặc biệt với kiểu cha, kiểu generic hoặc cấu hình serializer phụ thuộc kiểu. Nếu không cần kiểm soát kiểu gốc, `mapper.writer()` hoặc `mapper.writeValueAsString(...)` thường đã đủ.

`ObjectWriter` cũng bất biến. Các lời gọi như `with`, `without`, `withView`, `withRootName` và `withDefaultPrettyPrinter` tạo ra writer mới. Vì thế, nhiều chính sách ghi có thể cùng được xây dựng từ một mapper và tái sử dụng độc lập.

## 5. Mối quan hệ giữa ObjectMapper, ObjectReader và ObjectWriter

| Thành phần | Trách nhiệm chính | Hướng chuyển đổi | Cách dùng điển hình |
|---|---|---|---|
| `ObjectMapper` | Quản lý cấu hình và hạ tầng Databind dùng chung; cung cấp API đọc/ghi tổng quát | Cả hai chiều | Khởi tạo một lần, đăng ký module và cấu hình chung |
| `ObjectReader` | Giữ chính sách deserialize cho một kiểu hoặc một nhóm thao tác | JSON → Java | Đọc một loại message với feature hoặc view riêng |
| `ObjectWriter` | Giữ chính sách serialize cho một kiểu hoặc một nhóm thao tác | Java → JSON | Xuất DTO theo view, pretty printer hoặc root name riêng |

Quan hệ có thể biểu diễn như sau:

```text
                    ObjectMapper
                   /            \
        readerFor(...)          writerFor(...)
              |                       |
              v                       v
         ObjectReader             ObjectWriter
              |                       |
       Chính sách đọc           Chính sách ghi
              |                       |
       JSON -> Java              Java -> JSON
```

Reader và writer được tạo từ mapper nên sử dụng cùng nền tảng cấu hình và các cơ chế ánh xạ mà mapper cung cấp. Chúng không phải hai mapper độc lập được khởi tạo lại từ đầu. Điểm khác biệt nằm ở cấu hình cho một thao tác đọc hoặc ghi cụ thể.

Một cách phân chia trách nhiệm dễ nhớ:

- Mapper trả lời câu hỏi: **Ứng dụng hiểu JSON và object Java theo những quy tắc chung nào?**
- Reader trả lời câu hỏi: **Lần đọc này cần kiểu đích và chính sách deserialize nào?**
- Writer trả lời câu hỏi: **Lần ghi này cần kiểu gốc và chính sách serialize nào?**

## 6. Ví dụ kết hợp trong một ứng dụng

Giả sử ứng dụng có một chính sách đọc `User` từ hệ thống đối tác và hai cách ghi `User`: JSON đầy đủ cho lưu trữ nội bộ, JSON giới hạn thuộc tính cho API công khai.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public class UserJsonCodec {
    private final ObjectMapper mapper;
    private final ObjectReader partnerUserReader;
    private final ObjectWriter internalUserWriter;
    private final ObjectWriter publicUserWriter;

    public UserJsonCodec() {
        // 1. Tạo và cấu hình nền tảng dùng chung trước khi sử dụng.
        this.mapper = new ObjectMapper();
        this.mapper.registerModule(new JavaTimeModule());

        // 2. Tạo các chính sách đọc/ghi từ cùng mapper.
        this.partnerUserReader = mapper.readerFor(User.class)
                .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        this.internalUserWriter = mapper.writerFor(User.class);

        this.publicUserWriter = mapper.writerFor(User.class)
                .withView(UserViews.PublicView.class);
    }

    public User readPartnerUser(String json) throws IOException {
        return partnerUserReader.readValue(json);
    }

    public String writeInternalUser(User user) throws JsonProcessingException {
        return internalUserWriter.writeValueAsString(user);
    }

    public String writePublicUser(User user) throws JsonProcessingException {
        return publicUserWriter.writeValueAsString(user);
    }
}
```

Trong ví dụ này:

1. Mapper được cấu hình một lần, bao gồm module cần thiết.
2. Reader riêng xử lý quy tắc đầu vào của đối tác.
3. Hai writer thể hiện hai hợp đồng đầu ra khác nhau.
4. Các phương thức nghiệp vụ chỉ chọn đúng reader hoặc writer; chúng không phải bật/tắt feature trên mapper dùng chung.

Các lớp `User`, `UserViews` và import `IOException`, `JsonProcessingException` được lược bớt phần khai báo không liên quan. Trong mã thực tế, cần bổ sung import và mô hình dữ liệu tương ứng.

## 7. Những nhầm lẫn và cách dùng nên tránh

### 7.1. Nghĩ rằng ObjectReader và ObjectWriter là mapper mới

Reader và writer là đối tượng cấu hình chuyên biệt được tạo từ mapper. Chúng không tạo một bộ hạ tầng Databind độc lập cho mỗi lần gọi. Nhờ vậy, ứng dụng có thể tạo nhiều chính sách đọc/ghi mà vẫn tái sử dụng mapper nền.

### 7.2. Thay đổi mapper dùng chung theo từng request

Ví dụ không nên dùng:

```java
// Không nên thay đổi cấu hình của mapper dùng chung theo từng request.
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
User user = mapper.readValue(json, User.class);
mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Nếu hai request chạy đồng thời, một request có thể chịu cấu hình do request kia vừa thay đổi. Cách phù hợp là tạo reader với chính sách riêng:

```java
ObjectReader reader = mapper.readerFor(User.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

User user = reader.readValue(json);
```

### 7.3. Tạo ObjectMapper mới cho từng lần đọc hoặc ghi

Việc tạo mapper liên tục làm tăng chi phí khởi tạo và giảm khả năng tái sử dụng các bộ nhớ đệm serializer/deserializer. Với ứng dụng thông thường, hãy cấu hình mapper ở giai đoạn khởi tạo rồi dùng lại. Chỉ tạo mapper khác khi thực sự cần một cấu hình nền tảng độc lập.

### 7.4. Cho rằng mọi cấu hình đều phải đặt trên ObjectMapper

Các quy tắc chung như module, naming strategy hoặc serializer/deserializer dùng toàn ứng dụng thuộc cấu hình mapper. Những khác biệt theo kiểu dữ liệu hoặc theo luồng xử lý thường phù hợp hơn với reader/writer. Chọn đúng cấp cấu hình giúp hành vi của mỗi thao tác rõ ràng và tránh tác động ngoài ý muốn.

## 8. Cách chọn API trong từng tình huống

| Nhu cầu | API phù hợp |
|---|---|
| Thiết lập module và quy tắc chung của ứng dụng | `ObjectMapper` |
| Đọc nhanh một JSON bằng cấu hình chung | `mapper.readValue(...)` |
| Đọc lặp lại một kiểu với chính sách cố định | `mapper.readerFor(... )` rồi tái sử dụng `ObjectReader` |
| Đọc collection hoặc kiểu generic | Tạo `JavaType`, sau đó dùng `readerFor(JavaType)` |
| Ghi nhanh một object bằng cấu hình chung | `mapper.writeValueAsString(...)` hoặc `mapper.writeValue(...)` |
| Ghi lặp lại với view, root name hoặc pretty printer riêng | `mapper.writerFor(... )` rồi tái sử dụng `ObjectWriter` |
| Có nhiều hợp đồng JSON cho cùng một kiểu Java | Dùng nhiều reader/writer được cấu hình từ cùng mapper |

Khi thiết kế một thành phần chuyển đổi JSON, hãy bắt đầu bằng một mapper đã được cấu hình hoàn chỉnh. Sau đó tạo reader cho những dạng đầu vào cần chính sách riêng và writer cho những dạng đầu ra cần chính sách riêng. Nếu thao tác chỉ xảy ra một lần và dùng cấu hình chung, phương thức trực tiếp trên mapper vẫn là lựa chọn đơn giản, dễ hiểu.

## 9. Ghi nhớ về tính bất biến và vòng đời

Ba điểm cần giữ nhất quán khi sử dụng:

1. **Cấu hình mapper trước khi dùng.** Đăng ký module và đặt các feature chung trong giai đoạn khởi tạo. Sau khi mapper đã được đưa vào sử dụng, tránh thay đổi cấu hình dùng chung.
2. **Tạo reader/writer theo chính sách cần thiết.** Dùng `readerFor` và `writerFor` để diễn đạt rõ kiểu đích, kiểu gốc và những lựa chọn riêng cho từng luồng dữ liệu.
3. **Tái sử dụng các đối tượng cấu hình.** `ObjectReader` và `ObjectWriter` bất biến, phù hợp để lưu giữ và dùng lại. Các phương thức cấu hình trả về đối tượng mới, nên reader/writer ban đầu vẫn giữ nguyên.

Khi áp dụng đúng cách, `ObjectMapper` giữ vai trò nền tảng dùng chung, `ObjectReader` mô tả cách ứng dụng tiếp nhận JSON, còn `ObjectWriter` mô tả cách ứng dụng xuất JSON. Ba lớp bổ sung cho nhau để cấu hình Jackson rõ ràng, dễ tái sử dụng và an toàn hơn trong ứng dụng nhiều luồng.
