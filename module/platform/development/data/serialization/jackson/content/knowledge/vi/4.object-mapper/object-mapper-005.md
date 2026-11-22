# Tạo ObjectReader theo kiểu dữ liệu đích

Khi đọc JSON, Jackson cần biết dữ liệu đầu vào sẽ được ánh xạ thành kiểu Java nào. Kiểu đích quyết định cách Jackson tạo object, chuyển đổi từng thuộc tính, xử lý collection và lựa chọn deserializer. Với những thao tác đọc cần một cấu hình riêng hoặc được thực hiện nhiều lần, `ObjectMapper` cung cấp `readerFor(...)` để tạo `ObjectReader` gắn với kiểu dữ liệu đích.

`ObjectReader` là đối tượng đọc đã được chuẩn bị trước. Nó giữ kiểu Java cần nhận và cấu hình deserialize tương ứng, sau đó có thể được dùng nhiều lần với các nguồn JSON khác nhau. Cách này đặc biệt hữu ích khi cùng một loại dữ liệu được đọc lặp lại hoặc khi một luồng dữ liệu cần chính sách đọc riêng.

## 1. Vì sao ObjectReader cần kiểu dữ liệu đích?

JSON chỉ có một số kiểu cấu trúc cơ bản như object, array, string, number, boolean và null. Một JSON object không tự mang đầy đủ thông tin để Jackson biết nó phải trở thành class Java nào.

Ví dụ JSON:

```json
{
  "id": 101,
  "name": "An",
  "active": true
}
```

Để chuyển nội dung này thành object Java, Jackson cần một kiểu đích, chẳng hạn `User.class`:

```java
User user = mapper.readValue(json, User.class);
```

Ở cách gọi trên, `ObjectMapper` vừa nhận kiểu đích, vừa thực hiện thao tác đọc. Nếu muốn giữ cấu hình đọc đó để dùng lại, có thể tách hai việc thành hai bước:

```java
ObjectReader userReader = mapper.readerFor(User.class);

User user = userReader.readValue(json);
```

`readerFor(User.class)` tạo một reader biết kiểu đích là `User`. Khi `readValue(...)` được gọi, reader dùng kiểu đã chọn để yêu cầu Jackson tìm deserializer phù hợp và ánh xạ JSON thành object `User`.

Kiểu đích không chỉ ảnh hưởng kiểu của biến nhận kết quả. Nó còn ảnh hưởng cách Jackson xử lý cấu trúc lồng nhau, kiểu phần tử trong collection, constructor hoặc factory method, annotation, custom deserializer và thông tin đa hình được khai báo trên kiểu Java.

## 2. Tạo ObjectReader bằng Class<T>

Với một kiểu Java cụ thể, cách trực tiếp nhất là truyền `Class` vào `readerFor(...)`.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

ObjectMapper mapper = new ObjectMapper();

ObjectReader userReader = mapper.readerFor(User.class);
```

Ví dụ một model đơn giản:

```java
public record User(Long id, String name, boolean active) {
}
```

Đọc nhiều JSON bằng cùng reader:

```java
String firstJson = """
        {"id": 101, "name": "An", "active": true}
        """;

String secondJson = """
        {"id": 102, "name": "Binh", "active": false}
        """;

User first = userReader.readValue(firstJson);
User second = userReader.readValue(secondJson);
```

Reader giữ cùng kiểu đích `User` cho cả hai lần đọc. Mỗi lần gọi `readValue` nhận một nguồn JSON riêng và tạo kết quả riêng.

`readerFor(Class<T>)` phù hợp với các kiểu không cần tham số generic tại runtime, ví dụ:

```java
ObjectReader orderReader = mapper.readerFor(Order.class);
ObjectReader eventReader = mapper.readerFor(Event.class);
ObjectReader settingsReader = mapper.readerFor(ApplicationSettings.class);
```

Không cần tạo `ObjectReader` cho mọi lần đọc nếu thao tác chỉ xuất hiện một lần và không có cấu hình đặc biệt. `mapper.readValue(json, User.class)` vẫn là API ngắn gọn cho trường hợp đó. Reader phát huy tác dụng khi kiểu đích hoặc chính sách đọc được dùng lặp lại.

## 3. Tạo ObjectReader cho kiểu generic bằng TypeReference

Java sử dụng type erasure: tại runtime, thông tin tham số generic của một biểu thức như `List<User>` không được giữ đầy đủ trong đối tượng `Class`. Vì vậy, không thể viết `List<User>.class`.

Nếu chỉ truyền `List.class`, Jackson biết kết quả là một danh sách nhưng không biết kiểu cụ thể của từng phần tử. Trong trường hợp mặc định, object JSON bên trong danh sách có thể được ánh xạ thành `Map` thay vì `User`.

### 3.1. Đọc List<User>

Jackson cung cấp `TypeReference` để giữ lại thông tin kiểu generic thông qua lớp con ẩn danh:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectReader;

ObjectReader<List<User>> usersReader = mapper.readerFor(
        new TypeReference<List<User>>() { }
);

String json = """
        [
          {"id": 101, "name": "An", "active": true},
          {"id": 102, "name": "Binh", "active": false}
        ]
        """;

List<User> users = usersReader.readValue(json);
```

Ở đây, `TypeReference<List<User>>` giữ cả kiểu collection `List` lẫn kiểu phần tử `User`. Jackson có đủ thông tin để tạo danh sách các object `User`.

Có thể viết ngắn bằng cách truyền `TypeReference` trực tiếp cho mapper:

```java
List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() { }
);
```

Hai cách đều cung cấp thông tin generic cho Jackson. Cách dùng `ObjectReader` thuận tiện khi muốn giữ kiểu đích và cấu hình đọc để tái sử dụng.

### 3.2. Đọc Map<String, User>

`TypeReference` cũng xử lý được kiểu map có tham số generic:

```java
ObjectReader userMapReader = mapper.readerFor(
        new TypeReference<Map<String, User>>() { }
);

String json = """
        {
          "primary": {"id": 101, "name": "An", "active": true},
          "backup": {"id": 102, "name": "Binh", "active": false}
        }
        """;

Map<String, User> usersByRole = userMapReader.readValue(json);
```

Kiểu đích mô tả rõ key là `String` và value là `User`. Nếu chỉ dùng `Map.class`, Jackson không có thông tin kiểu value cụ thể và thường tạo map lồng nhau cho các object JSON.

### 3.3. Đọc kiểu generic do ứng dụng tự định nghĩa

Giả sử API trả về một wrapper có tham số kiểu:

```java
public record ApiResponse<T>(T data, String requestId) {
}
```

Có thể tạo reader cho `ApiResponse<User>`:

```java
ObjectReader responseReader = mapper.readerFor(
        new TypeReference<ApiResponse<User>>() { }
);

ApiResponse<User> response = responseReader.readValue(responseJson);
```

Với kiểu lồng nhau phức tạp hơn, `TypeReference` vẫn giữ toàn bộ cấu trúc generic mà Java không thể biểu diễn bằng một đối tượng `Class` thông thường.

## 4. Tạo ObjectReader bằng JavaType

`JavaType` là mô hình kiểu của Jackson. Nó biểu diễn được kiểu Java thông thường, kiểu generic, collection, map và các kiểu tham số lồng nhau. Có thể tạo `JavaType` bằng `TypeFactory`, sau đó truyền vào `readerFor(JavaType)`.

### 4.1. Tạo JavaType cho collection

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectReader;

JavaType usersType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);

ObjectReader<List<User>> usersReader = mapper.readerFor(usersType);
```

`constructCollectionType(...)` nhận class collection và kiểu phần tử. Cách này hữu ích khi kiểu phần tử được quyết định ở runtime hoặc khi kiểu được ghép từ metadata cấu hình.

### 4.2. Tạo JavaType cho map

```java
JavaType userMapType = mapper.getTypeFactory()
        .constructMapType(Map.class, String.class, User.class);

ObjectReader<Map<String, User>> userMapReader = mapper.readerFor(userMapType);
```

Ở đây, Jackson biết cấu trúc đích là `Map<String, User>`. Với map phức tạp hơn, `TypeFactory` cũng có thể nhận `JavaType` cho key và value để ghép các kiểu đã được xây dựng trước.

### 4.3. Tạo kiểu lồng nhau

Ví dụ cần đọc `Map<String, List<User>>`:

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory.constructCollectionType(
        List.class,
        User.class
);

JavaType groupedUsersType = typeFactory.constructMapType(
        Map.class,
        typeFactory.constructType(String.class),
        userListType
);

ObjectReader groupedUsersReader = mapper.readerFor(groupedUsersType);

Map<String, List<User>> groupedUsers = groupedUsersReader.readValue(json);
```

Việc xây dựng từ trong ra ngoài giúp thể hiện chính xác cấu trúc: trước hết tạo kiểu `List<User>`, sau đó dùng kiểu đó làm value của `Map<String, ...>`. `JavaType` đặc biệt hữu ích khi cấu trúc generic chỉ được biết khi chương trình chạy.

### 4.4. Chọn giữa Class, TypeReference và JavaType

| Kiểu đích | Cách tạo reader phù hợp |
|---|---|
| `User` | `mapper.readerFor(User.class)` |
| `List<User>` được biết tại compile time | `mapper.readerFor(new TypeReference<List<User>>() {})` |
| `Map<String, User>` được biết tại compile time | `mapper.readerFor(new TypeReference<Map<String, User>>() {})` |
| `List<User>` được ghép động ở runtime | Tạo `JavaType` bằng `TypeFactory`, rồi gọi `readerFor(javaType)` |
| Kiểu generic lồng nhau được cấu hình từ metadata | Dựng các `JavaType` thành phần rồi kết hợp thành kiểu tổng |

Hãy chọn API thể hiện rõ nhất kiểu đích. Không cần chuyển mọi kiểu đơn giản sang `JavaType`; `Class<T>` dễ đọc hơn khi kiểu không có generic.

## 5. Kiểu đích ảnh hưởng đến quá trình deserialize như thế nào?

Khi `ObjectReader` nhận kiểu đích, Jackson sử dụng thông tin đó để chọn deserializer và xử lý cấu trúc JSON.

### 5.1. Ánh xạ thuộc tính

Với kiểu `User`, Jackson tìm các thuộc tính có thể deserialize dựa trên constructor, record component, setter, field được phép truy cập, getter phù hợp và annotation theo cấu hình. Ví dụ:

```java
public class Customer {
    private Long customerId;
    private String fullName;

    @JsonCreator
    public Customer(
            @JsonProperty("id") Long customerId,
            @JsonProperty("name") String fullName
    ) {
        this.customerId = customerId;
        this.fullName = fullName;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public String getFullName() {
        return fullName;
    }
}
```

Reader được tạo cho `Customer.class` sẽ dùng metadata của kiểu và annotation để ánh xạ JSON:

```java
ObjectReader customerReader = mapper.readerFor(Customer.class);

Customer customer = customerReader.readValue(
        "{\"id\": 10, \"name\": \"Lan\"}"
);
```

Tên thuộc tính JSON không bắt buộc phải giống tên field Java nếu model đã định nghĩa quy tắc ánh xạ như `@JsonProperty`.

### 5.2. Kiểu phần tử trong collection

Với JSON array, kiểu đích quyết định kiểu của từng phần tử:

```json
[
  {"id": 101, "name": "An", "active": true},
  {"id": 102, "name": "Binh", "active": false}
]
```

- Reader có kiểu `List<User>` tạo các phần tử `User`.
- Reader chỉ biết `List.class` thường tạo phần tử object tổng quát như `LinkedHashMap`.

Sự khác biệt này có thể không biểu hiện ngay khi in dữ liệu, nhưng sẽ xuất hiện khi code gọi phương thức riêng của `User` hoặc ép kiểu phần tử.

### 5.3. Kiểu đích và polymorphism

Nếu kiểu đích là một kiểu cha hoặc interface, Jackson cần quy tắc để xác định kiểu con thực tế. Ứng dụng có thể khai báo subtype và metadata đa hình bằng `@JsonTypeInfo`, `@JsonSubTypes` hoặc cấu hình subtype tương ứng.

Ví dụ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public interface Payment {
}

public record CardPayment(String cardNumber) implements Payment {
}

public record CashPayment(String receiptCode) implements Payment {
}
```

Tạo reader theo kiểu hợp đồng `Payment`:

```java
ObjectReader paymentReader = mapper.readerFor(Payment.class);

Payment payment = paymentReader.readValue(
        "{\"kind\":\"card\",\"cardNumber\":\"****1234\"}"
);
```

JSON có trường `kind` để Jackson chọn subtype đã đăng ký. Reader vẫn khai báo kiểu đích là `Payment`, còn kiểu thực tế của object được quyết định bởi thông tin đa hình. Khi đọc dữ liệu không đáng tin cậy, chỉ cấu hình các subtype được phép; không bật cơ chế default typing rộng một cách tùy tiện.

## 6. Cấu hình ObjectReader sau khi chọn kiểu đích

Sau khi xác định kiểu đích, có thể cấu hình thêm chính sách deserialize ngay trên reader. Các phương thức cấu hình trả về reader mới, vì vậy có thể tạo nhiều biến thể cho cùng một kiểu Java.

Ví dụ, một nguồn đối tác có thể thêm thuộc tính mà model hiện tại chưa sử dụng:

```java
ObjectReader partnerUserReader = mapper.readerFor(User.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

User user = partnerUserReader.readValue(partnerJson);
```

Một nguồn khác cần bật xử lý giá trị đơn như collection một phần tử:

```java
ObjectReader flexibleUsersReader = mapper.readerFor(
        new TypeReference<List<User>>() { }
).with(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
```

Các feature này chỉ áp dụng cho reader được tạo ra. Reader khác có thể giữ chính sách mặc định hoặc dùng một chính sách khác.

Có thể gắn attribute để custom deserializer hoặc thành phần xử lý có thể đọc dữ liệu theo ngữ cảnh:

```java
ObjectReader tenantReader = mapper.readerFor(User.class)
        .withAttribute("tenant", tenantId);
```

Attribute không tự thay đổi model hoặc ánh xạ thuộc tính. Nó chỉ cung cấp ngữ cảnh cho những thành phần deserialize được thiết kế để đọc attribute đó.

Các cấu hình thường gặp khác gồm:

- `with(...)` và `without(...)` để bật hoặc tắt `DeserializationFeature`.
- `withView(...)` để chọn JSON View khi deserialize.
- `with(InjectableValues)` để cung cấp giá trị inject cho property hoặc creator đã cấu hình.
- `with(schema)` để gắn schema phù hợp với định dạng/parser hỗ trợ.
- `forType(...)` để tạo reader mới với kiểu đích khác.

Hãy cấu hình reader ở nơi khởi tạo thành phần xử lý, sau đó tái sử dụng reader đã hoàn chỉnh. Không nên thay đổi `ObjectMapper` dùng chung theo từng request chỉ để phục vụ một trường hợp đọc riêng.

## 7. Sử dụng ObjectReader để đọc từ nhiều nguồn dữ liệu

Sau khi tạo reader với kiểu đích, có thể đọc từ nhiều loại input source mà Jackson hỗ trợ, chẳng hạn `String`, byte array, `File`, `InputStream`, `Reader` hoặc `JsonParser`.

```java
ObjectReader userReader = mapper.readerFor(User.class);

User fromString = userReader.readValue(jsonString);
User fromBytes = userReader.readValue(jsonBytes);
User fromFile = userReader.readValue(jsonFile);
User fromStream = userReader.readValue(inputStream);
```

Các biến trong ví dụ đại diện cho input source tương ứng. Trong mã thực tế, cần quản lý việc đóng tài nguyên theo quyền sở hữu của ứng dụng. Nếu ứng dụng mở `InputStream` hoặc `Reader`, ứng dụng thường phải đóng chúng bằng try-with-resources. Không đóng tài nguyên một cách tùy tiện nếu nó được quản lý bởi thành phần gọi hoặc framework.

Khi đã có `JsonParser`, reader có thể đọc từ parser đó:

```java
try (JsonParser parser = mapper.getFactory().createParser(jsonString)) {
    User user = userReader.readValue(parser);
}
```

Đọc từ parser hữu ích khi ứng dụng cần kiểm soát tầng streaming, xử lý một phần luồng JSON hoặc tích hợp với pipeline token. Reader vẫn quyết định kiểu Java đích.

### 7.1. Đọc một giá trị gốc hay đọc nhiều giá trị liên tiếp

`readValue(...)` thường dùng để đọc một giá trị JSON gốc thành một object. Nếu input là một chuỗi nhiều JSON value liên tiếp theo định dạng sequence, có thể dùng `readValues(...)` để nhận `MappingIterator<T>`:

```java
ObjectReader eventReader = mapper.readerFor(Event.class);

try (JsonParser parser = mapper.getFactory().createParser(eventStream)) {
    MappingIterator<Event> events = eventReader.readValues(parser);

    while (events.hasNextValue()) {
        Event event = events.nextValue();
        process(event);
    }
}
```

`readValues(...)` phù hợp với nhiều root value liên tiếp. Nếu JSON đầu vào là một array duy nhất và mục tiêu là tạo `List<Event>`, hãy dùng reader có kiểu đích `List<Event>` thay vì nhầm hai tình huống này với nhau.

## 8. Thay đổi kiểu đích bằng forType

Khi đã có một reader và muốn tạo reader khác cho kiểu đích mới, có thể dùng `forType(...)`:

```java
ObjectReader baseReader = mapper.reader();

ObjectReader userReader = baseReader.forType(User.class);
ObjectReader orderReader = baseReader.forType(Order.class);
```

`forType(...)` trả về reader mới. Nó hữu ích khi một cấu hình đọc chung được xây dựng trước rồi áp dụng cho nhiều kiểu đích. Với code đơn giản, `mapper.readerFor(User.class)` thường rõ ý hơn vì thể hiện trực tiếp cả mapper và kiểu đích trong cùng một biểu thức.

Không nhầm `forType(...)` với việc thay đổi kiểu của reader hiện tại. Reader cũ vẫn giữ cấu hình và kiểu đích ban đầu.

## 9. Phân biệt readerFor và readerForUpdating

`readerFor(User.class)` yêu cầu Jackson tạo một object mới từ JSON. Trong khi đó, `readerForUpdating(existingUser)` tạo reader có mục đích cập nhật một object đã tồn tại.

```java
User existingUser = new User(101L, "An", true);

ObjectReader updateReader = mapper.readerForUpdating(existingUser);

updateReader.readValue("{\"name\":\"An Nguyen\"}");
```

Hai API có ý nghĩa khác nhau:

| API | Mục đích |
|---|---|
| `readerFor(User.class)` | Deserialize thành một object mới có kiểu `User` |
| `readerForUpdating(existingUser)` | Deserialize và cập nhật object đã cung cấp theo quy tắc cập nhật của Jackson |

Không dùng `readerForUpdating` chỉ vì muốn tái sử dụng reader. Nếu yêu cầu là tạo một object mới từ mỗi JSON, hãy dùng `readerFor(...)`. Cập nhật object có thể có ngữ nghĩa riêng với collection, thuộc tính null và cấu trúc lồng nhau; cần hiểu rõ hành vi đó trước khi áp dụng cho dữ liệu nghiệp vụ.

## 10. Tái sử dụng ObjectReader và an toàn đa luồng

`ObjectReader` là đối tượng cấu hình bất biến và an toàn khi dùng đồng thời giữa nhiều luồng. Các lời gọi cấu hình như `with`, `without`, `forType` trả về instance mới, không sửa reader ban đầu.

Ví dụ giữ reader trong service:

```java
public class UserJsonService {
    private final ObjectReader userReader;

    public UserJsonService(ObjectMapper mapper) {
        this.userReader = mapper.readerFor(User.class)
                .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }

    public User parse(String json) throws JsonProcessingException {
        return userReader.readValue(json);
    }
}
```

Nhiều request có thể gọi `parse(...)` đồng thời vì reader không giữ trạng thái kết quả của lần đọc trước. Mỗi lần đọc tạo context xử lý riêng.

Điều kiện quan trọng là mapper nền phải được cấu hình đầy đủ trước khi bắt đầu sử dụng. `ObjectReader` bất biến không làm cho việc thay đổi cấu hình mapper dùng chung sau đó trở nên an toàn. Hãy đăng ký module, cấu hình serializer/deserializer và feature chung trong giai đoạn khởi tạo ứng dụng.

## 11. Các lỗi thường gặp khi chọn kiểu đích

### 11.1. Dùng List.class cho List<User>

```java
// Mất thông tin kiểu phần tử.
ObjectReader reader = mapper.readerFor(List.class);
```

Jackson chỉ biết kết quả là một list. Với JSON object bên trong, phần tử thường là `LinkedHashMap`, không phải `User`. Hãy dùng `TypeReference<List<User>>` hoặc `JavaType`.

### 11.2. Chọn sai kiểu root so với cấu trúc JSON

Nếu JSON root là array mà reader được tạo cho `User.class`, Jackson không thể tự coi toàn bộ array là một `User`. Tương tự, JSON root là object không thể được đọc trực tiếp thành `List<User>` nếu không có cấu trúc phù hợp.

Hãy xác định hình dạng root của JSON trước khi chọn kiểu đích:

| JSON root | Kiểu đích thường dùng |
|---|---|
| Object `{...}` | `User.class`, `Order.class`, `ApiResponse<User>` |
| Array `[...]` | `List<User>`, `User[]` |
| Object có value là object | `Map<String, User>` |
| Object có value là array | `Map<String, List<User>>` |

### 11.3. Dùng raw type làm mất kiểu generic

`List.class`, `Map.class` hoặc `ApiResponse.class` không chứa đầy đủ tham số generic. Nếu code phụ thuộc kiểu phần tử, value hoặc payload cụ thể, hãy cung cấp `TypeReference` hoặc `JavaType`.

### 11.4. Tưởng reader tự kiểm tra mọi quy tắc nghiệp vụ

Reader chỉ thực hiện deserialize theo cấu hình Jackson. Việc JSON chuyển thành `User` thành công không đồng nghĩa dữ liệu thỏa mãn quy tắc nghiệp vụ như email hợp lệ, tuổi trong phạm vi cho phép hoặc quyền truy cập phù hợp. Các quy tắc đó cần được kiểm tra ở tầng validation/domain/service tương ứng.

### 11.5. Nhầm kiểu đích với kiểu nguồn

`readerFor(...)` nhận kiểu Java mà ứng dụng muốn tạo ra, không phải kiểu của nguồn JSON. Nguồn có thể là `String`, `File` hoặc `InputStream`, còn kiểu đích có thể là `User`, `List<User>` hoặc `Map<String, User>`.

## 12. Ví dụ tổng hợp: bộ đọc JSON cho nhiều kiểu dữ liệu

Một thành phần tích hợp có thể nhận nhiều loại payload. Thay vì lặp lại việc xây dựng kiểu và cấu hình reader ở từng phương thức, có thể tạo reader một lần trong constructor:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

import java.io.IOException;
import java.util.List;
import java.util.Map;

public class PartnerJsonReaders {
    private final ObjectReader userReader;
    private final ObjectReader usersReader;
    private final ObjectReader usersByCodeReader;

    public PartnerJsonReaders(ObjectMapper mapper) {
        this.userReader = mapper.readerFor(User.class);

        this.usersReader = mapper.readerFor(
                new TypeReference<List<User>>() { }
        );

        this.usersByCodeReader = mapper.readerFor(
                new TypeReference<Map<String, User>>() { }
        );
    }

    public User readUser(String json) throws IOException {
        return userReader.readValue(json);
    }

    public List<User> readUsers(String json) throws IOException {
        return usersReader.readValue(json);
    }

    public Map<String, User> readUsersByCode(String json) throws IOException {
        return usersByCodeReader.readValue(json);
    }
}
```

Ví dụ cho thấy ba reader dùng cùng một `ObjectMapper` nhưng có kiểu đích khác nhau. Mỗi reader thể hiện một hợp đồng đầu vào cụ thể và có thể được tái sử dụng ở nhiều lần gọi. `ObjectMapper` được truyền từ bên ngoài để thành phần này dùng chung cấu hình module và serializer/deserializer của ứng dụng.

## 13. Quy trình chọn và tạo ObjectReader

Khi xây dựng luồng đọc JSON, có thể thực hiện theo thứ tự sau:

1. Xác định JSON root là object, array hay một cấu trúc lồng nhau.
2. Chọn kiểu Java cần nhận sau deserialize.
3. Nếu kiểu không có generic, dùng `readerFor(Class<T>)`.
4. Nếu kiểu generic được biết khi viết code, dùng `readerFor(TypeReference<T>)`.
5. Nếu kiểu generic được ghép động khi runtime, tạo `JavaType` bằng `TypeFactory` rồi truyền vào `readerFor(JavaType)`.
6. Áp dụng các feature hoặc attribute riêng cho reader nếu cần.
7. Tái sử dụng reader đã cấu hình để đọc các input source cùng hợp đồng.
8. Xử lý lỗi parse/deserialize và kiểm tra dữ liệu nghiệp vụ ở tầng phù hợp.

Ví dụ lựa chọn nhanh:

```java
// Kiểu cụ thể.
ObjectReader oneUser = mapper.readerFor(User.class);

// Collection có kiểu phần tử generic.
ObjectReader manyUsers = mapper.readerFor(
        new TypeReference<List<User>>() { }
);

// Kiểu được dựng từ metadata runtime.
JavaType runtimeType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);
ObjectReader runtimeReader = mapper.readerFor(runtimeType);
```

## 14. Ghi nhớ

`ObjectReader` mô tả cách Jackson đọc JSON thành một kiểu Java đích. `readerFor(Class<T>)` là lựa chọn trực tiếp cho kiểu cụ thể; `TypeReference<T>` giữ thông tin generic ở compile time; `JavaType` biểu diễn kiểu phức tạp hoặc được tạo động ở runtime.

Kiểu đích quyết định cách Jackson ánh xạ object, collection, map, kiểu generic và subtype đa hình. Hãy khớp kiểu đích với cấu trúc JSON root, tránh raw type khi cần kiểu phần tử, và cấu hình reader một lần rồi tái sử dụng. Khi đã có reader, có thể đọc từ nhiều nguồn như String, byte array, file, stream hoặc parser mà vẫn giữ cùng hợp đồng kiểu dữ liệu.
