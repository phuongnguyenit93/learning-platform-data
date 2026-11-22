# Sử dụng TypeReference để giữ thông tin kiểu tổng quát

Java sử dụng **type erasure** để triển khai generic. Khi chương trình chạy, thông tin tham số kiểu như `User` trong `List<User>` thường không còn được giữ trong đối tượng `List` theo cách một overload nhận `Class` có thể đọc trực tiếp. Vì vậy, nếu yêu cầu Jackson đọc JSON thành `List<User>` nhưng chỉ truyền `List.class`, mapper chỉ biết kiểu container là `List`; kiểu phần tử có thể bị xử lý như `Object`.

Jackson cung cấp `TypeReference<T>` để giữ lại thông tin kiểu tổng quát ở thời điểm khai báo. Bằng cách tạo một anonymous subclass với kiểu cụ thể, ứng dụng có thể truyền cả cấu trúc generic như `List<User>`, `Map<String, List<Order>>` hoặc `ApiResponse<List<User>>` cho API data binding.

Bài này tập trung vào cách khai báo, sử dụng và truyền `TypeReference`, đồng thời chỉ ra giới hạn của nó trong generic method và khi kiểu chỉ được biết ở runtime.

## 1. Vì sao Class<T> chưa đủ cho kiểu tổng quát?

Với kiểu không có generic parameter, `Class<T>` là đủ:

```java
User user = mapper.readValue(json, User.class);
```

Nhưng với collection:

```java
List<User> users = mapper.readValue(json, List.class);
```

Compiler cho phép gán kết quả vì overload nhận `Class<T>` không thể biết kiểu phần tử của `List`. Jackson nhìn thấy raw type `List` và thường tạo các phần tử dạng `LinkedHashMap` nếu JSON object được đọc thành `Object`.

Ví dụ JSON:

```json
[
  {
    "id": 1,
    "name": "An"
  },
  {
    "id": 2,
    "name": "Binh"
  }
]
```

Nếu đọc bằng `List.class`, kết quả có thể là một `List` chứa các map:

```java
List<?> values = mapper.readValue(json, List.class);

Object first = values.get(0);
System.out.println(first.getClass()); // class java.util.LinkedHashMap
```

Khi ép phần tử thành `User`, ứng dụng có thể gặp `ClassCastException`:

```java
User user = (User) values.get(0); // Không phải User
```

Nguyên nhân không nằm ở JSON thiếu dữ liệu. Kiểu đích đã bị cung cấp không đầy đủ: `List.class` không mang thông tin `User`.

### 1.1. Type erasure trong Java

Xét khai báo:

```java
List<User> users = new ArrayList<>();
List<Order> orders = new ArrayList<>();
```

Ở cấp bytecode và runtime, hai biến đều có raw class là `java.util.List`. Generic parameter hỗ trợ compiler kiểm tra kiểu lúc biên dịch, nhưng không tạo ra hai class runtime riêng là `List<User>` và `List<Order>`.

Do đó:

```java
users.getClass() == orders.getClass(); // true
```

Từ một object list bất kỳ, Jackson không thể luôn suy ra các phần tử bên trong phải là `User` hay `Order`. Nếu API chỉ nhận `List.class`, thông tin này chưa được truyền đến mapper.

### 1.2. Khi nào cần TypeReference?

`TypeReference` hữu ích nhất ở những API cần truyền kiểu đích qua một đối số kiểu:

- Đọc root collection như `List<User>` hoặc `Set<Order>`.
- Đọc map có kiểu key/value như `Map<String, User>`.
- Đọc generic lồng nhau như `Map<String, List<Order>>`.
- Đọc wrapper generic như `ApiResponse<User>` hoặc `Page<List<Product>>`.
- Viết helper method nhận kiểu đích tổng quát mà không làm mất metadata.

Nếu Jackson đang đọc một field đã khai báo `List<User>` bên trong DTO, databind thường có thể lấy generic signature của field/property qua reflection. Trường hợp đó không nhất thiết phải dùng `TypeReference`. Nhu cầu nổi bật của `TypeReference` là khi ứng dụng gọi API ở root và cần cung cấp đầy đủ kiểu đích.

## 2. TypeReference giữ thông tin generic như thế nào?

Trong Jackson 2.x, lớp `TypeReference<T>` nằm trong package:

```java
com.fasterxml.jackson.core.type.TypeReference
```

Đây là một abstract class. Cách sử dụng thông dụng là tạo anonymous subclass:

```java
TypeReference<List<User>> userListType =
        new TypeReference<List<User>>() {};
```

Cặp dấu ngoặc nhọn cuối cùng rất quan trọng. Nó tạo một lớp con ẩn danh có khai báo generic superclass là `TypeReference<List<User>>`. Thông tin tham số kiểu được ghi trong generic signature của lớp con và có thể được Jackson đọc qua reflection.

Có thể hình dung:

```text
TypeReference<List<User>>
          |
          | anonymous subclass
          v
class ẩn danh extends TypeReference<List<User>>
          |
          | generic superclass signature
          v
Jackson lấy được List<User>
          |
          v
TypeFactory xây dựng JavaType tương ứng
          |
          v
Deserializer đọc List và tạo từng phần tử User
```

Vì vậy, cú pháp đúng là:

```java
new TypeReference<List<User>>() {}
```

Không phải:

```java
new TypeReference<List<User>>(); // TypeReference là abstract
```

### 2.1. Đọc List<User>

Ví dụ đầy đủ:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
);
```

Jackson nhận được kiểu đích bao gồm cả container và phần tử. Mỗi JSON object trong mảng được deserialize thành một instance `User`, không phải `LinkedHashMap`.

Nếu `User` có constructor/setter hoặc creator hợp lệ, mapper sẽ dùng cơ chế tương ứng để tạo từng phần tử.

### 2.2. Đọc Map<String, User>

`TypeReference` không chỉ dành cho collection. Nó giữ cả kiểu key và kiểu value:

```java
Map<String, User> usersById = mapper.readValue(
        json,
        new TypeReference<Map<String, User>>() {}
);
```

Ví dụ JSON:

```json
{
  "u-100": {
    "id": 100,
    "name": "An"
  },
  "u-200": {
    "id": 200,
    "name": "Binh"
  }
}
```

Kết quả là map có key kiểu `String` và value kiểu `User`.

JSON object quy định tên field là chuỗi. Nếu kiểu key Java là kiểu khác, chẳng hạn `Long`, Jackson cần key deserializer tương ứng để chuyển tên field JSON thành key Java:

```java
Map<Long, User> usersById = mapper.readValue(
        json,
        new TypeReference<Map<Long, User>>() {}
);
```

Giá trị key phải có dạng chuyển đổi hợp lệ. `TypeReference` truyền kiểu key mong muốn, còn khả năng chuyển đổi thực tế phụ thuộc key deserializer.

### 2.3. Kiểu generic lồng nhau

Có thể lồng nhiều cấp generic trong cùng một khai báo:

```java
Map<String, List<Order>> ordersByCustomer = mapper.readValue(
        json,
        new TypeReference<Map<String, List<Order>>>() {}
);
```

Jackson có đủ thông tin để xây dựng:

- Một `Map` ở ngoài.
- Key là `String`.
- Value là `List<Order>`.
- Mỗi phần tử trong list được deserialize thành `Order`.

Ví dụ khác:

```java
List<Map<String, User>> groupedUsers = mapper.readValue(
        json,
        new TypeReference<List<Map<String, User>>>() {}
);
```

Cấu trúc generic trong `TypeReference` nên khớp với hợp đồng JSON. Nếu JSON có mảng chứa object, dùng `List<...>`; nếu JSON có object chứa các key động, dùng `Map<String, ...>`.

## 3. Dùng TypeReference với generic DTO

Một trường hợp thường gặp là API trả về wrapper có tham số kiểu:

```java
public class ApiResponse<T> {
    private boolean success;
    private T data;
    private String message;

    public ApiResponse() {
    }

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
```

Nếu JSON có dạng:

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "id": 10,
    "name": "An"
  }
}
```

Có thể đọc thành `ApiResponse<User>`:

```java
ApiResponse<User> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<User>>() {}
);

User user = response.getData();
```

Nếu `data` là danh sách:

```java
ApiResponse<List<User>> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<List<User>>>() {}
);
```

Điểm quan trọng là phải khai báo đầy đủ toàn bộ cấu trúc generic. Nếu chỉ dùng `ApiResponse.class`, kiểu của `data` bị mất; Jackson thường deserialize object bên trong thành map hoặc collection không có element type cụ thể.

Generic wrapper có thể lồng nhiều tầng:

```java
Page<ApiResponse<List<User>>> page = mapper.readValue(
        json,
        new TypeReference<Page<ApiResponse<List<User>>>>() {}
);
```

Mỗi tầng generic đều được giữ lại trong type signature, miễn là kiểu được khai báo cụ thể tại vị trí tạo `TypeReference`.

## 4. Dùng TypeReference với ObjectReader

Nếu cùng một kiểu đích được đọc nhiều lần, có thể tạo `ObjectReader` một lần:

```java
ObjectReader userListReader = mapper.readerFor(
        new TypeReference<List<User>>() {}
);

List<User> firstBatch = userListReader.readValue(firstJson);
List<User> secondBatch = userListReader.readValue(secondJson);
```

`ObjectReader` lưu kiểu đích và cấu hình đọc tương ứng. Nó bất biến và có thể được tái sử dụng. Cách này hữu ích khi ứng dụng đọc nhiều payload cùng một schema, ví dụ message từ một topic hoặc response từ một API.

Có thể kết hợp với feature riêng cho reader:

```java
ObjectReader tolerantReader = mapper.readerFor(
        new TypeReference<List<User>>() {}
).without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Cấu hình này chỉ áp dụng cho reader được tạo; mapper gốc không bị thay đổi.

## 5. TypeReference và JavaType

`TypeReference` là API tiện dụng để biểu diễn generic type bằng cú pháp Java. Bên dưới, Jackson sử dụng `JavaType` để mô hình hóa kiểu đích.

Với kiểu biết trước lúc viết code, `TypeReference` thường dễ đọc nhất:

```java
List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
);
```

Với kiểu chỉ biết ở runtime, có thể dùng `TypeFactory` để tạo `JavaType`:

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory.constructCollectionType(
        List.class,
        User.class
);

List<User> users = mapper.readValue(json, userListType);
```

### 5.1. Tạo kiểu Map lồng nhau bằng JavaType

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory.constructCollectionType(
        List.class,
        User.class
);

JavaType mapType = typeFactory.constructMapType(
        Map.class,
        String.class,
        userListType
);

Map<String, List<User>> result = mapper.readValue(json, mapType);
```

### 5.2. Tạo generic wrapper bằng JavaType

Với `ApiResponse<List<User>>`:

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory.constructCollectionType(
        List.class,
        User.class
);

JavaType responseType = typeFactory.constructParametricType(
        ApiResponse.class,
        userListType
);

ApiResponse<List<User>> response = mapper.readValue(json, responseType);
```

Dùng `JavaType` khi kiểu được lắp ghép từ tham số runtime, ví dụ client nhận class phần tử từ cấu hình hoặc một generic framework. `TypeReference` không thể tự đoán class mà chương trình chỉ biết khi chạy.

## 6. Giới hạn quan trọng trong generic method

Một lỗi dễ gặp là tạo `TypeReference<List<T>>` bên trong generic method rồi kỳ vọng Jackson tự biết `T` thực tế:

```java
public static <T> List<T> readList(
        ObjectMapper mapper,
        String json
) throws JsonProcessingException {
    return mapper.readValue(
            json,
            new TypeReference<List<T>>() {}
    );
}
```

Cách viết này **không bảo đảm giữ được kiểu runtime cụ thể của T**. Anonymous subclass chỉ giữ được kiểu generic mà compiler ghi nhận tại vị trí khai báo. Bên trong generic method, `T` vẫn là type variable chưa được thay bằng `User` hay `Order` trong generic signature. Do type erasure, Jackson không thể tự suy ra kiểu cụ thể từ kết quả mà caller mong muốn.

Hệ quả thường thấy là phần tử được đọc như `Object`, chẳng hạn JSON object trở thành `LinkedHashMap`.

### 6.1. Truyền TypeReference từ caller

Một cách tốt là để caller cung cấp type token cụ thể:

```java
public static <T> T read(
        ObjectMapper mapper,
        String json,
        TypeReference<T> targetType
) throws JsonProcessingException {
    return mapper.readValue(json, targetType);
}
```

Caller tạo type cụ thể:

```java
List<User> users = read(
        mapper,
        json,
        new TypeReference<List<User>>() {}
);

ApiResponse<List<User>> response = read(
        mapper,
        json,
        new TypeReference<ApiResponse<List<User>>>() {}
);
```

Generic helper không cần tự đoán kiểu; nó nhận metadata đã được caller tạo ở vị trí còn biết kiểu cụ thể.

### 6.2. Truyền Class khi kiểu phần tử không generic

Nếu helper chỉ cần đọc một object đơn lẻ, có thể nhận `Class<T>`:

```java
public static <T> T read(
        ObjectMapper mapper,
        String json,
        Class<T> targetClass
) throws JsonProcessingException {
    return mapper.readValue(json, targetClass);
}
```

Cách này phù hợp với `User.class`, `Order.class`, `Integer.class` và các class không cần generic parameter. Nó không đủ cho `List<User>` hoặc `ApiResponse<User>`.

### 6.3. Truyền Class phần tử và dựng JavaType

Nếu helper cần đọc collection và caller có class phần tử:

```java
public static <T> List<T> readList(
        ObjectMapper mapper,
        String json,
        Class<T> elementClass
) throws JsonProcessingException {
    JavaType listType = mapper.getTypeFactory()
            .constructCollectionType(List.class, elementClass);

    return mapper.readValue(json, listType);
}
```

Cách này hoạt động vì caller truyền `User.class` hoặc `Order.class` trực tiếp. Với generic lồng nhau phức tạp, hãy truyền `JavaType` đã dựng hoặc `TypeReference<T>` từ caller.

## 7. TypeReference không thay thế type metadata trong JSON

`TypeReference` cho Jackson biết **kiểu đích mà ứng dụng muốn tạo**. Nó không tự ghi thêm thông tin class vào JSON, cũng không giải quyết mọi trường hợp polymorphism.

Ví dụ:

```java
List<Animal> animals = mapper.readValue(
        json,
        new TypeReference<List<Animal>>() {}
);
```

Jackson biết các phần tử có kiểu khai báo `Animal`, nhưng nếu `Animal` là abstract class hoặc interface, nó vẫn cần biết implementation nào cần tạo. Khi đó, cần một cơ chế polymorphic như `@JsonTypeInfo` và subtype registration, hoặc custom deserializer.

Ví dụ:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = Dog.class, name = "dog"),
        @JsonSubTypes.Type(value = Cat.class, name = "cat")
})
public abstract class Animal {
}
```

JSON có thể mang type discriminator:

```json
[
  {
    "kind": "dog",
    "name": "Milo"
  },
  {
    "kind": "cat",
    "name": "Luna"
  }
]
```

`TypeReference<List<Animal>>` giữ kiểu collection và kiểu khai báo phần tử; `@JsonTypeInfo` cung cấp thông tin để chọn subtype cụ thể. Hai cơ chế bổ sung cho nhau.

## 8. TypeReference trong serialization

Nhu cầu phổ biến nhất của `TypeReference` là deserialize generic root type. Khi serialize, Jackson thường có thể suy luận kiểu từ object runtime:

```java
String json = mapper.writeValueAsString(users);
```

Tuy nhiên, nếu muốn chỉ rõ declared root type để writer dùng trong quá trình serialization, có thể tạo `ObjectWriter` với `TypeReference`:

```java
ObjectWriter writer = mapper.writerFor(
        new TypeReference<List<User>>() {}
);

String json = writer.writeValueAsString(users);
```

Điều này có ý nghĩa trong những trường hợp declared type ảnh hưởng đến serializer được chọn, generic content type hoặc polymorphic handling. Không cần tạo writer với `TypeReference` cho mọi list đơn giản nếu runtime type đã đủ và không có yêu cầu declared-type cụ thể.

## 9. Những lỗi sử dụng thường gặp

**Dùng raw class cho collection.** `List.class` không chứa `User`; phần tử JSON object thường trở thành map. Dùng `new TypeReference<List<User>>() {}` hoặc JavaType.

**Quên cặp ngoặc nhọn tạo anonymous subclass.** `new TypeReference<List<User>>()` không hợp lệ vì `TypeReference` là abstract. Cặp `{}` cho phép Jackson đọc generic superclass signature.

**Tạo TypeReference với T chưa được giải quyết.** `new TypeReference<List<T>>() {}` bên trong generic method không thể tự biết kiểu thực tế của T. Truyền type token từ caller hoặc dựng JavaType bằng class runtime.

**Nghĩ TypeReference xác định subtype.** `TypeReference<List<Animal>>` chỉ cho biết kiểu khai báo; abstract/interface element vẫn cần polymorphic type information hoặc custom deserializer.

**Nhầm kiểu generic với tên property.** `TypeReference` giữ cấu trúc kiểu Java, không đổi tên key JSON. Naming strategy và `@JsonProperty` mới điều khiển tên property.

**Cho rằng TypeReference xác thực payload.** Nó chỉ cung cấp kiểu đích. Dữ liệu vẫn có thể sai format, thiếu field bắt buộc theo nghiệp vụ hoặc vi phạm validation. Cần xử lý mapping exception và validate object sau deserialize.

**Dùng một TypeReference mutable hoặc chia sẻ không rõ ràng.** `TypeReference` chỉ là type token; nên khai báo bằng anonymous subclass cụ thể, không cố sửa hay tái sử dụng nó như một vùng chứa trạng thái runtime.

## 10. Lựa chọn giữa Class, TypeReference và JavaType

| Tình huống | Nên dùng |
|---|---|
| Đọc object đơn giản như `User` | `User.class` |
| Đọc `List<User>`, `Map<String, User>` đã biết lúc compile | `TypeReference<T>` |
| Đọc generic wrapper lồng nhau đã biết lúc compile | `TypeReference<T>` |
| Xây dựng collection/map từ class phần tử biết ở runtime | `JavaType` qua `TypeFactory` |
| Generic helper nhận kiểu cụ thể do caller quyết định | Nhận `TypeReference<T>` hoặc `JavaType` làm tham số |
| Đọc interface/abstract class có nhiều subtype | Kết hợp kiểu đích với polymorphic metadata hoặc custom deserializer |

Quy tắc thực tế: dùng `Class` cho kiểu cụ thể không generic; dùng `TypeReference` cho generic type đã biết ở compile time; dùng `JavaType` khi phải lắp ghép type từ thông tin runtime.

## 11. Kết luận

`TypeReference` giải quyết giới hạn của overload nhận `Class` khi kiểu đích có generic parameter. Anonymous subclass giữ lại generic signature như `List<User>`, giúp Jackson dựng đúng kiểu collection, map hoặc wrapper lồng nhau và deserialize phần tử thành đúng kiểu Java.

Nó không khôi phục một type variable đã bị erasure trong generic method và không tự quyết định subtype cho interface/abstract class. Khi kiểu chỉ biết ở runtime, hãy dùng `TypeFactory` để dựng `JavaType`; khi viết helper generic, nhận type token từ caller. Chọn đúng biểu diễn kiểu đích giúp Jackson binding chính xác và tránh các lỗi ép kiểu xuất hiện muộn ở phía ứng dụng.

## Tài liệu tham khảo

- [Jackson Core — TypeReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/type/TypeReference.html)
- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson Databind — TypeFactory API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/type/TypeFactory.html)
- [Jackson Databind — JavaType API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JavaType.html)

