# Gói hoặc bỏ lớp tên gốc theo hợp đồng dữ liệu

Trong JSON, object gốc thường được gửi trực tiếp:

```json
{
  "id": 42,
  "name": "An"
}
```

Một số API hoặc hệ thống tích hợp lại yêu cầu một lớp object bên ngoài chứa tên kiểu dữ liệu:

```json
{
  "user": {
    "id": 42,
    "name": "An"
  }
}
```

Lớp ngoài này được gọi là **root wrapper**. Jackson hỗ trợ đóng gói và bỏ lớp root bằng `SerializationFeature.WRAP_ROOT_VALUE` và `DeserializationFeature.UNWRAP_ROOT_VALUE`. Annotation `@JsonRootName` cung cấp tên cho lớp wrapper. Ba thành phần này phối hợp để đáp ứng hợp đồng dữ liệu của API hoặc hệ thống legacy.

Điểm cần nhớ là tên root và việc bật wrapping là hai việc riêng: `@JsonRootName` chỉ khai báo tên; nó không tự động khiến JSON được bọc. Tương tự, khai báo tên không khiến Jackson tự bỏ wrapper khi đọc. Producer và consumer phải thống nhất cấu trúc cũng như cấu hình tương ứng.

## 1. Root wrapper là gì?

Root là giá trị JSON ngoài cùng của một tài liệu. Nếu tài liệu bắt đầu bằng object, object đó là root object. Root wrapper là một object ngoài cùng có một property mang tên kiểu hoặc tên tài nguyên, bên trong property đó là dữ liệu thực.

Ví dụ DTO:

```java
public class User {
    private long id;
    private String name;

    public User() {
    }

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Không dùng root wrapping, JSON có dạng:

```json
{
  "id": 42,
  "name": "An"
}
```

Dùng root wrapping với tên `user`, JSON có dạng:

```json
{
  "user": {
    "id": 42,
    "name": "An"
  }
}
```

Trong ví dụ thứ hai:

- `user` là tên root wrapper.
- Object bên trong là dữ liệu của instance `User`.
- `id` và `name` vẫn là các property của DTO.
- Wrapper chỉ bao quanh root value; nó không tự động được thêm vào mọi object lồng nhau.

Root wrapper có thể xuất hiện trong API cũ, giao thức tích hợp, định dạng message có tên resource hoặc hợp đồng cần phân biệt kiểu root. Với API JSON hiện đại, root object trực tiếp thường phổ biến hơn, nhưng Jackson cho phép hỗ trợ cả hai.

## 2. @JsonRootName khai báo tên root

Annotation `@JsonRootName` thuộc package `com.fasterxml.jackson.annotation` trong Jackson 2.x. Nó khai báo tên được dùng khi root value được wrap hoặc unwrap:

```java
import com.fasterxml.jackson.annotation.JsonRootName;

@JsonRootName("user")
public class User {
    private long id;
    private String name;

    // Constructor, getter và setter
}
```

Khi serialize với root wrapping được bật, Jackson có thể tạo:

```json
{
  "user": {
    "id": 42,
    "name": "An"
  }
}
```

Khi deserialize với root unwrapping được bật, Jackson mong đợi wrapper có tên `user`.

### 2.1. Annotation không tự bật wrapping

Chỉ thêm:

```java
@JsonRootName("user")
public class User {
    // ...
}
```

không làm cho lệnh:

```java
String json = mapper.writeValueAsString(user);
```

tự động sinh root wrapper. Nếu mapper chưa bật `WRAP_ROOT_VALUE`, kết quả vẫn là JSON object trực tiếp:

```json
{
  "id": 42,
  "name": "An"
}
```

Tương tự, `@JsonRootName` không tự khiến Jackson bỏ wrapper khi đọc. Cần bật `UNWRAP_ROOT_VALUE` ở mapper hoặc reader.

### 2.2. Tên mặc định khi không có @JsonRootName

Nếu root wrapping được bật mà class không khai báo `@JsonRootName`, Jackson có thể dùng tên mặc định suy ra từ kiểu root, thường là tên class đơn giản. Không nên phụ thuộc vào tên suy ra nếu đó là hợp đồng tích hợp với hệ thống bên ngoài: đổi tên class Java có thể làm thay đổi tên wrapper.

Khi root name là một phần của API contract, hãy khai báo rõ bằng `@JsonRootName` hoặc đặt tên trên writer/reader.

### 2.3. Giá trị namespace

`@JsonRootName` có thuộc tính `namespace` ngoài `value`. Namespace hữu ích với dataformat có khái niệm namespace như XML. JSON không có namespace trong cú pháp object property, vì vậy không nên kỳ vọng thuộc tính `namespace` tạo thêm một thành phần trong root JSON.

Ví dụ:

```java
@JsonRootName(value = "user", namespace = "urn:example:users")
public class User {
    // ...
}
```

Với JSON root wrapping, tên cần quan tâm là `user`. Nếu đang làm việc với XML, cần kiểm tra annotation và cấu hình của Jackson XML, chẳng hạn `@JacksonXmlRootElement`, vì quy tắc root element của XML có những đặc điểm riêng.

## 3. Bật root wrapping khi serialize

Trong Jackson 2.x, bật `SerializationFeature.WRAP_ROOT_VALUE` để đặt root value bên trong một object có property là root name.

### 3.1. Cấu hình trên ObjectMapper

```java
ObjectMapper mapper = new ObjectMapper();

mapper.enable(SerializationFeature.WRAP_ROOT_VALUE);

User user = new User(42L, "An");
String json = mapper.writeValueAsString(user);
```

Với class có `@JsonRootName("user")`, kết quả:

```json
{"user":{"id":42,"name":"An"}}
```

Nếu tắt feature:

```java
mapper.disable(SerializationFeature.WRAP_ROOT_VALUE);
```

Jackson ghi object trực tiếp, không có property wrapper.

### 3.2. Cấu hình bằng JsonMapper.Builder

Với Jackson 2.10 trở lên, có thể cấu hình ngay khi tạo mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.WRAP_ROOT_VALUE)
        .build();
```

Builder giúp tập trung chính sách serialization tại thời điểm khởi tạo. Sau khi cấu hình mapper xong, tái sử dụng mapper thay vì bật/tắt feature trên một mapper dùng chung theo từng request.

### 3.3. Chỉ wrap cho một lần ghi bằng ObjectWriter

Nếu phần lớn API cần JSON không wrapper nhưng một endpoint legacy yêu cầu wrapper, không nhất thiết phải bật feature trên mapper dùng chung:

```java
ObjectWriter wrappedWriter = mapper.writer()
        .with(SerializationFeature.WRAP_ROOT_VALUE);

String wrappedJson = wrappedWriter.writeValueAsString(user);
String plainJson = mapper.writeValueAsString(user);
```

`ObjectWriter` giữ cấu hình ghi riêng cho thao tác. Mapper gốc không bị thay đổi. Đây là cách phù hợp khi chỉ một luồng xuất dữ liệu cần root wrapper.

Có thể đặt tên root cụ thể cho writer:

```java
ObjectWriter userWriter = mapper.writer()
        .with(SerializationFeature.WRAP_ROOT_VALUE)
        .withRootName("user");

String json = userWriter.writeValueAsString(user);
```

Tên được chỉ định ở writer giúp hợp đồng output không phụ thuộc tên class Java. Khi dùng root name tường minh, hãy giữ cùng tên ở phía reader.

## 4. Bỏ root wrapper khi deserialize

Khi nhận JSON đã wrap, Jackson cần biết rằng object ngoài cùng là wrapper chứ không phải property của DTO.

### 4.1. Cấu hình trên ObjectMapper

Bật `DeserializationFeature.UNWRAP_ROOT_VALUE`:

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.UNWRAP_ROOT_VALUE)
        .build();

User user = mapper.readValue(json, User.class);
```

Với JSON:

```json
{
  "user": {
    "id": 42,
    "name": "An"
  }
}
```

Jackson kiểm tra tên wrapper mong đợi, bỏ lớp ngoài và deserialize object bên trong thành `User`.

Nếu JSON là object trực tiếp nhưng feature unwrapping vẫn bật, dữ liệu không khớp cấu trúc mong đợi và Jackson sẽ báo lỗi root name/wrapper thay vì tự đoán định dạng.

### 4.2. Cấu hình bằng ObjectReader

Nếu chỉ một luồng đọc cần bỏ wrapper:

```java
ObjectReader userReader = mapper.readerFor(User.class)
        .with(DeserializationFeature.UNWRAP_ROOT_VALUE);

User user = userReader.readValue(json);
```

Reader có thể được tái sử dụng cho nhiều payload cùng kiểu và cùng hợp đồng. Cách này hữu ích khi một ứng dụng tích hợp cả API mới (không wrapper) và API cũ (có wrapper).

Có thể đặt root name tường minh cho reader:

```java
ObjectReader userReader = mapper.readerFor(User.class)
        .with(DeserializationFeature.UNWRAP_ROOT_VALUE)
        .withRootName("user");
```

Nếu reader mong đợi tên `user`, payload có wrapper tên khác như `customer` sẽ bị từ chối. Việc kiểm tra tên này giúp phát hiện producer gửi sai hợp đồng.

## 5. Bật wrap và unwrap đồng bộ

Một mapper có thể bật cả hai feature nếu ứng dụng muốn round-trip theo cùng một hợp đồng:

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.WRAP_ROOT_VALUE)
        .enable(DeserializationFeature.UNWRAP_ROOT_VALUE)
        .build();
```

DTO:

```java
@JsonRootName("user")
public class User {
    private long id;
    private String name;

    public User() {
    }

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Round-trip:

```java
User original = new User(42L, "An");

String json = mapper.writeValueAsString(original);
User restored = mapper.readValue(json, User.class);
```

JSON trung gian:

```json
{
  "user": {
    "id": 42,
    "name": "An"
  }
}
```

Hai feature độc lập về chức năng:

- `WRAP_ROOT_VALUE` tác động đến serialization.
- `UNWRAP_ROOT_VALUE` tác động đến deserialization.

Bật một feature không tự động bật feature còn lại. Nếu producer và consumer nằm ở hai ứng dụng khác nhau, mỗi bên phải cấu hình đúng theo vai trò của mình.

## 6. Tên wrapper không khớp sẽ gây lỗi

Giả sử class khai báo:

```java
@JsonRootName("user")
public class User {
    // ...
}
```

Reader mong đợi wrapper `user`. Nhưng producer gửi:

```json
{
  "customer": {
    "id": 42,
    "name": "An"
  }
}
```

Khi `UNWRAP_ROOT_VALUE` bật, Jackson không coi `customer` là một alias tự động. Tên root không khớp với tên mong đợi nên quá trình deserialize thất bại.

Cần kiểm tra các nguyên nhân thường gặp:

- Producer và consumer dùng tên wrapper khác nhau.
- Annotation `@JsonRootName` chưa được khai báo hoặc bị thay đổi.
- Writer/reader đặt `withRootName(...)` khác với hợp đồng.
- Consumer bật `UNWRAP_ROOT_VALUE` nhưng producer gửi object trực tiếp.
- Consumer không bật unwrapping nhưng producer gửi wrapper.
- Class Java bị đổi tên trong khi hệ thống đang phụ thuộc tên root mặc định.

Không nên xử lý lỗi bằng cách tắt strictness rồi bỏ qua wrapper tùy tiện. Hãy xác định payload nào thuộc contract nào và cấu hình reader phù hợp.

## 7. Root wrapper khác với DTO envelope

Một điểm dễ nhầm là root wrapper do Jackson tạo ra và envelope là một phần của mô hình dữ liệu ứng dụng.

### 7.1. Root wrapper do Jackson tạo

```java
@JsonRootName("user")
public class User {
    private long id;
    private String name;
}
```

Khi bật `WRAP_ROOT_VALUE`, JSON có dạng:

```json
{
  "user": {
    "id": 42,
    "name": "An"
  }
}
```

Property `user` không phải field của class `User`; nó được thêm ở tầng root serialization.

### 7.2. Envelope là class Java thật

```java
public class ApiResponse<T> {
    private boolean success;
    private T data;
    private String message;

    // Getter/setter
}
```

Serialize `ApiResponse<User>` sẽ tạo object có các property `success`, `data`, `message`:

```json
{
  "success": true,
  "data": {
    "id": 42,
    "name": "An"
  },
  "message": "ok"
}
```

Đây là cấu trúc nghiệp vụ thật của DTO. Nó không phụ thuộc vào `WRAP_ROOT_VALUE`.

### 7.3. Hai cơ chế có thể cùng xuất hiện

Nếu vừa dùng envelope vừa bật root wrapping, JSON có thể có hai lớp:

```json
{
  "apiResponse": {
    "success": true,
    "data": {
      "id": 42,
      "name": "An"
    },
    "message": "ok"
  }
}
```

Chỉ làm vậy khi hợp đồng yêu cầu rõ cả hai lớp. Nếu không, payload sẽ bị lồng wrapper thừa và consumer có thể không đọc được.

## 8. Root wrapper chỉ áp dụng cho root value

Giả sử một DTO có object lồng nhau:

```java
public class Order {
    private long id;
    private User customer;

    // Getter/setter
}
```

Khi bật `WRAP_ROOT_VALUE` cho một instance `Order`, Jackson chỉ bọc root:

```json
{
  "order": {
    "id": 100,
    "customer": {
      "id": 42,
      "name": "An"
    }
  }
}
```

Nó không tự bọc từng object lồng nhau thành:

```json
{
  "order": {
    "id": 100,
    "customer": {
      "user": {
        "id": 42,
        "name": "An"
      }
    }
  }
}
```

Nếu cần wrapper cho property lồng nhau, đó là một yêu cầu cấu trúc khác. Có thể mô hình hóa bằng DTO envelope, custom serializer hoặc annotation dành cho cấu trúc property tương ứng; root wrapping không giải quyết yêu cầu đó.

## 9. Root name khi serialize collection và generic type

Một tình huống cần chú ý là root value không phải một POJO đơn lẻ mà là collection:

```java
List<User> users = List.of(
        new User(1L, "An"),
        new User(2L, "Binh")
);
```

Khi bật root wrapping, root value là list. Jackson không tự hiểu rằng phải dùng `@JsonRootName("user")` của từng phần tử để đặt tên wrapper. Root name được xác định cho kiểu root mà mapper đang serialize, thường dựa trên kiểu container hoặc cấu hình root name.

Nếu hợp đồng yêu cầu wrapper tên `users`, hãy đặt tên rõ trên writer:

```java
ObjectWriter usersWriter = mapper.writer()
        .with(SerializationFeature.WRAP_ROOT_VALUE)
        .withRootName("users");

String json = usersWriter.writeValueAsString(users);
```

Kết quả mong muốn:

```json
{
  "users": [
    {
      "id": 1,
      "name": "An"
    },
    {
      "id": 2,
      "name": "Binh"
    }
  ]
}
```

Phía đọc phải cung cấp kiểu generic đầy đủ và tên wrapper tương ứng:

```java
ObjectReader usersReader = mapper.readerFor(
        new TypeReference<List<User>>() {}
).with(DeserializationFeature.UNWRAP_ROOT_VALUE)
 .withRootName("users");

List<User> restored = usersReader.readValue(json);
```

Không dùng `List.class` nếu cần giữ kiểu phần tử `User`; root wrapping không thay thế metadata generic.

## 10. Root wrapping và naming strategy

Naming strategy như snake_case thường điều khiển tên property bên trong object, ví dụ `firstName` thành `first_name`. Root name là một lớp tên riêng.

Nếu hợp đồng root name là `user-profile`, khai báo tường minh:

```java
@JsonRootName("user-profile")
public class UserProfile {
    private String firstName;

    // Getter/setter
}
```

Đừng giả định naming strategy của property sẽ tự chuyển root name theo cùng cách. Với root name là một phần của hợp đồng bên ngoài, hãy kiểm tra JSON thực tế hoặc đặt tên tường minh qua writer/reader.

Ngoài ra, `@JsonProperty` trên field/getter đặt tên property bên trong DTO; nó không thay thế `@JsonRootName` để định nghĩa wrapper của toàn bộ tài liệu.

## 11. Dùng root wrapping theo từng hợp đồng API

Một ứng dụng có thể kết nối nhiều hệ thống với quy ước khác nhau. Ví dụ:

- API A yêu cầu JSON object trực tiếp.
- API B yêu cầu object có wrapper `user`.
- API C yêu cầu wrapper `customer` dù dùng cùng class Java `User`.

Không nên liên tục bật/tắt feature trên một mapper singleton. Dùng writer/reader riêng cho từng contract:

```java
ObjectMapper mapper = new ObjectMapper();

ObjectWriter apiAWriter = mapper.writer()
        .without(SerializationFeature.WRAP_ROOT_VALUE);

ObjectWriter apiBWriter = mapper.writer()
        .with(SerializationFeature.WRAP_ROOT_VALUE)
        .withRootName("user");

ObjectWriter apiCWriter = mapper.writer()
        .with(SerializationFeature.WRAP_ROOT_VALUE)
        .withRootName("customer");
```

Phía deserialize:

```java
ObjectReader apiAReader = mapper.readerFor(User.class)
        .without(DeserializationFeature.UNWRAP_ROOT_VALUE);

ObjectReader apiBReader = mapper.readerFor(User.class)
        .with(DeserializationFeature.UNWRAP_ROOT_VALUE)
        .withRootName("user");

ObjectReader apiCReader = mapper.readerFor(User.class)
        .with(DeserializationFeature.UNWRAP_ROOT_VALUE)
        .withRootName("customer");
```

Cách này làm rõ contract tại nơi tích hợp. Mỗi reader/writer có thể được tạo một lần và tái sử dụng, thay vì thay đổi trạng thái mapper dùng chung giữa các request.

Nếu contract khác nhau nhiều hơn chỉ root name, chẳng hạn module, date format, unknown field policy hoặc custom serializer, có thể cần mapper riêng cho từng boundary.

## 12. Jackson 2.x và Jackson 3.x

Các ví dụ ở trên sử dụng tên package Jackson 2.x như `com.fasterxml.jackson.databind`. Từ Jackson 2.10, có thể cấu hình bằng `JsonMapper.builder()`. Cách dùng `SerializationFeature.WRAP_ROOT_VALUE`, `DeserializationFeature.UNWRAP_ROOT_VALUE`, `@JsonRootName`, `ObjectWriter` và `ObjectReader` là các API quen thuộc của databind.

Jackson 3 thay đổi package chính của databind sang `tools.jackson.databind` và chuyển mapper/factory sang mô hình bất biến. Vì vậy, cấu hình tùy chỉnh nên được xây dựng qua builder, sau đó chia sẻ mapper đã hoàn tất cấu hình. Annotation package vẫn thuộc hệ sinh thái `com.fasterxml.jackson.annotation`.

Ví dụ cấu hình builder theo phong cách Jackson 3:

```java
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.json.JsonMapper;

JsonMapper mapper = JsonMapper.builder()
        .enable(SerializationFeature.WRAP_ROOT_VALUE)
        .enable(DeserializationFeature.UNWRAP_ROOT_VALUE)
        .build();
```

Khi nâng cấp major version, hãy xác nhận các feature và overload đang dùng trong Javadoc của đúng phiên bản. Không trộn `ObjectMapper` từ Jackson 2 với mapper hoặc feature class từ Jackson 3 trong cùng đoạn code.

## 13. Khi nào nên wrap root và khi nào nên bỏ?

| Tình huống | Cách chọn |
|---|---|
| API yêu cầu object trực tiếp | Tắt `WRAP_ROOT_VALUE`; không bật `UNWRAP_ROOT_VALUE` |
| API legacy yêu cầu wrapper có tên class/resource | Dùng `@JsonRootName` và bật wrap/unwrap tương ứng |
| Cùng DTO nhưng nhiều đối tác yêu cầu tên wrapper khác nhau | Dùng `ObjectWriter`/`ObjectReader` với root name riêng |
| Root là collection | Đặt root name rõ ràng, ví dụ `users`; truyền generic type đầy đủ khi đọc |
| Cần envelope có metadata như success, message, data | Tạo DTO envelope thật |
| Chỉ muốn đổi tên property bên trong object | Dùng `@JsonProperty` hoặc naming strategy |
| Đang dùng XML | Xem xét XML root element annotation/cấu hình riêng |

Root wrapping hữu ích khi phải tuân thủ contract đã tồn tại. Với thiết kế API mới, nên quyết định dựa trên yêu cầu consumer và tính rõ ràng của schema. Không thêm wrapper chỉ vì tên class Java cần xuất hiện trong JSON.

## 14. Những lỗi thường gặp

**Chỉ thêm @JsonRootName và chờ JSON tự được bọc.** Annotation chỉ cung cấp tên. Phải bật `WRAP_ROOT_VALUE` để serialize có wrapper.

**Bật WRAP_ROOT_VALUE nhưng không khai báo root name ổn định.** Jackson có thể suy ra tên từ kiểu root. Đổi tên class hoặc đổi kiểu root có thể làm contract thay đổi. Dùng `@JsonRootName` hoặc `withRootName()` nếu tên là một phần giao thức.

**Bật UNWRAP_ROOT_VALUE khi input không có wrapper.** Jackson sẽ tìm wrapper theo tên mong đợi và báo lỗi nếu cấu trúc không khớp.

**Tên wrapper giữa producer và consumer khác nhau.** `user`, `User` và `customer` là các tên khác nhau. Cần thống nhất chữ hoa/thường và tên chính xác.

**Nhầm root wrapper với property envelope.** Wrapper được tạo bởi feature Jackson, còn `ApiResponse.data` là field thật trong class. Hai cơ chế có thể tạo hai lớp lồng nhau.

**Cho rằng mọi object lồng nhau cũng được bọc.** Root feature chỉ áp dụng cho root value của lần serialize/deserialize đó.

**Cho rằng @JsonRootName trên phần tử sẽ đặt tên wrapper của List.** Root value là collection; tên root phải được xác định cho collection, thường nên đặt tường minh.

**Dùng chung mapper rồi bật/tắt feature theo request.** Điều này làm cấu hình phụ thuộc thứ tự thao tác và không phù hợp khi mapper được chia sẻ nhiều luồng. Dùng reader/writer riêng.

**Dùng root wrapping để giải quyết polymorphism.** Root name không tự cung cấp subtype metadata cho abstract class/interface. Nếu cần chọn subtype, dùng `@JsonTypeInfo`, subtype registration hoặc custom deserializer.

## 15. Kiểm thử hợp đồng root wrapper

Nên kiểm tra cả JSON đầu ra, quá trình đọc lại và hành vi khi sai tên wrapper.

### 15.1. Kiểm tra serialize có wrapper

```java
@Test
void shouldWrapRootWithConfiguredName() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .enable(SerializationFeature.WRAP_ROOT_VALUE)
            .build();

    User user = new User(42L, "An");

    String json = mapper.writeValueAsString(user);

    JsonNode root = mapper.readTree(json);

    assertTrue(root.has("user"));
    assertEquals(42L, root.path("user").path("id").asLong());
}
```

Test này giả định `User` được đánh dấu `@JsonRootName("user")`.

### 15.2. Kiểm tra deserialize bỏ wrapper

```java
@Test
void shouldUnwrapExpectedRootName() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.UNWRAP_ROOT_VALUE)
            .build();

    User user = mapper.readValue(
            """
            {
              "user": {
                "id": 42,
                "name": "An"
              }
            }
            """,
            User.class
    );

    assertEquals(42L, user.getId());
    assertEquals("An", user.getName());
}
```

### 15.3. Kiểm tra tên wrapper không khớp

```java
@Test
void shouldRejectUnexpectedRootName() {
    ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.UNWRAP_ROOT_VALUE)
            .build();

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                    """
                    {
                      "customer": {
                        "id": 42,
                        "name": "An"
                      }
                    }
                    """,
                    User.class
            )
    );
}
```

Test này xác nhận reader không tự chấp nhận tên `customer` khi class mong đợi `user`.

### 15.4. Kiểm tra reader/writer theo contract riêng

Nếu một class phục vụ nhiều API, hãy test mỗi writer/reader:

- API không wrapper phải phát object trực tiếp.
- API có wrapper phải phát đúng tên.
- Reader của API đó chỉ chấp nhận wrapper đúng tên.
- Payload sai cấu trúc phải trả lỗi rõ ràng.
- Root collection phải dùng tên wrapper đã quy định và kiểu generic đầy đủ.

Test contract giúp phát hiện thay đổi vô tình khi đổi tên class, nâng Jackson hoặc thay cấu hình mapper.

## 16. Quy trình triển khai

Khi tích hợp root wrapping vào một API:

1. **Xác định contract:** producer/consumer mong đợi object trực tiếp hay object bọc một property?
2. **Chọn root name:** dùng tên ổn định theo schema, không phụ thuộc tên class nếu contract bên ngoài yêu cầu cố định.
3. **Đánh dấu kiểu:** dùng `@JsonRootName` nếu tên thuộc class; dùng root name trên writer/reader nếu mỗi API cần tên riêng.
4. **Bật đúng chiều:** serialize dùng `WRAP_ROOT_VALUE`; deserialize dùng `UNWRAP_ROOT_VALUE`.
5. **Tách cấu hình theo contract:** dùng reader/writer riêng hoặc mapper riêng; không đổi feature động trên mapper dùng chung.
6. **Xử lý collection:** đặt tên root cho container và truyền `TypeReference`/JavaType khi đọc generic type.
7. **Kiểm thử cả hai chiều:** xác nhận output, input, root name sai và trường hợp không wrapper.
8. **Kiểm tra consumer:** bảo đảm hệ thống nhận thực sự mong đợi wrapper; không thêm lớp tên chỉ vì Jackson hỗ trợ.

## 17. Kết luận

Jackson hỗ trợ đóng gói root value bằng `SerializationFeature.WRAP_ROOT_VALUE` và bỏ wrapper khi đọc bằng `DeserializationFeature.UNWRAP_ROOT_VALUE`. `@JsonRootName` cung cấp tên root, còn `ObjectWriter` và `ObjectReader` cho phép chọn feature và root name theo từng hợp đồng tích hợp.

Root wrapper chỉ bao quanh giá trị ngoài cùng; nó không phải property của DTO và không thay thế một envelope class. Annotation cũng không tự bật wrap/unwrap. Khi thiết kế API, hãy chốt cấu trúc và tên wrapper rõ ràng, cấu hình producer/consumer đồng bộ, dùng tên tường minh cho collection root và kiểm thử payload thực tế. Như vậy, ứng dụng có thể đáp ứng cả contract JSON trực tiếp lẫn contract legacy có lớp tên gốc mà không làm cấu hình mapper dùng chung trở nên khó kiểm soát.

## Tài liệu tham khảo

- [Jackson Annotations — JsonRootName API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonRootName.html)
- [Jackson Databind — SerializationFeature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/SerializationFeature.html)
- [Jackson Databind — DeserializationFeature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [Jackson Databind — ObjectWriter API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectWriter.html)
- [Jackson Databind — ObjectReader API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectReader.html)

