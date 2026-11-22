# Quản lý kiểu tổng quát trong API tiện ích tự xây dựng

Khi viết một tiện ích JSON dùng chung, ta thường muốn một phương thức có thể đọc nhiều kiểu dữ liệu khác nhau: `User`, `List<User>`, `Map<String, User>` hoặc một wrapper như `ApiResponse<List<User>>`. Với kiểu đơn giản, truyền `User.class` cho Jackson là đủ. Nhưng với kiểu tổng quát, Java đã xóa phần lớn thông tin tham số kiểu ở runtime (type erasure), nên chỉ truyền `List.class` không cho Jackson biết phần tử bên trong phải là `User`.

Jackson cung cấp hai công cụ chính để giữ thông tin kiểu tổng quát: **`TypeReference<T>`** và **`JavaType`**. Khi xây dựng API tiện ích riêng, nên thiết kế phương thức nhận một trong hai kiểu thông tin này, bên cạnh overload nhận `Class<T>` cho kiểu đơn giản. Nhờ đó, API có thể đọc đúng cấu trúc lồng nhau mà không phải ép kiểu thủ công hoặc dựa vào `LinkedHashMap`.

## 1. Vì sao `Class<T>` chưa đủ cho kiểu tổng quát?

Với một kiểu cụ thể, Jackson có thể nhận kiểu đích trực tiếp:

```java
User user = mapper.readValue(json, User.class);
```

Nhưng `List<User>` là một kiểu tham số hóa. Ở runtime, `List.class` chỉ biểu diễn lớp `List`, không chứa tham số `User`:

```java
List<?> values = mapper.readValue(json, List.class);
```

Khi JSON chứa object, Jackson thường tạo các phần tử dạng `LinkedHashMap`, vì không có thông tin cho biết cần tạo `User`. Việc ép kiểu danh sách thành `List<User>` không biến các map đó thành đối tượng `User`; lỗi có thể chỉ xuất hiện sau đó khi lấy phần tử và ép kiểu.

Vấn đề rõ hơn với kiểu lồng nhau:

```java
ApiResponse<List<User>> response;
Map<String, List<User>> usersByGroup;
```

Các kiểu này chứa nhiều lớp tham số. `ApiResponse.class`, `Map.class` hoặc `List.class` riêng lẻ không mô tả đầy đủ kiểu đích.

| Kiểu cần đọc | Thông tin kiểu cần cung cấp |
|---|---|
| `User` | `User.class` |
| `List<User>` | Collection `List` với phần tử `User` |
| `Map<String, User>` | Map có key `String`, value `User` |
| `ApiResponse<User>` | Wrapper `ApiResponse` có tham số `User` |
| `ApiResponse<List<User>>` | Wrapper `ApiResponse` có tham số là collection `List<User>` |
| `Map<String, List<User>>` | Map có key `String`, value là collection `List<User>` |

## 2. Dùng `TypeReference<T>` ở nơi gọi API

`TypeReference<T>` của Jackson giữ thông tin generic thông qua kiểu của lớp con ẩn danh. Khi tạo một instance với kiểu cụ thể, Java reflection có thể cung cấp `Type` chứa cả tham số generic.

```java
import com.fasterxml.jackson.core.type.TypeReference;
import java.util.List;

TypeReference<List<User>> userListType =
        new TypeReference<List<User>>() {};

List<User> users = mapper.readValue(json, userListType);
```

Jackson đọc `Type` được lưu trong `TypeReference` và tạo từng phần tử thành `User`. Cách này đặc biệt tiện khi kiểu đích được biết rõ tại nơi gọi.

Với wrapper tổng quát:

```java
TypeReference<ApiResponse<List<User>>> responseType =
        new TypeReference<ApiResponse<List<User>>>() {};

ApiResponse<List<User>> response = mapper.readValue(json, responseType);
```

`TypeReference` mô tả toàn bộ cấu trúc `ApiResponse<List<User>>`, không chỉ lớp ngoài cùng. Jackson có thể tạo wrapper, danh sách và từng `User` theo đúng kiểu đã khai báo.

### 2.1. Vì sao phải tạo lớp con ẩn danh?

Không thể trông chờ `List<User>.class`, vì Java không có cú pháp class literal cho một kiểu tham số hóa. Biểu thức:

```java
new TypeReference<List<User>>() {}
```

tạo một lớp con ẩn danh mà generic superclass của nó giữ lại kiểu `List<User>`. `TypeReference` đọc metadata đó trong quá trình khởi tạo.

Có thể khai báo hằng số nếu một kiểu được dùng lặp lại:

```java
private static final TypeReference<List<User>> USER_LIST_TYPE =
        new TypeReference<List<User>>() {};
```

Sau đó dùng lại:

```java
List<User> users = mapper.readValue(json, USER_LIST_TYPE);
```

## 3. Dùng `JavaType` để xây dựng kiểu động

`TypeReference` thuận tiện khi kiểu được viết tường minh trong source code. Trong một API tiện ích, đôi khi kiểu phần tử hoặc kiểu wrapper chỉ được biết lúc chạy chương trình. Khi đó, `JavaType` và `TypeFactory` cho phép xây dựng mô tả kiểu từ các thành phần.

Lấy `TypeFactory` từ mapper:

```java
TypeFactory typeFactory = mapper.getTypeFactory();
```

### 3.1. Collection và array

Tạo kiểu `List<User>`:

```java
JavaType userListType = typeFactory.constructCollectionType(
        List.class,
        User.class
);

List<User> users = mapper.readValue(json, userListType);
```

Tạo kiểu collection tổng quát khác cũng dùng `constructCollectionType()` với lớp collection cụ thể phù hợp. Với mảng, dùng `constructArrayType()`:

```java
JavaType userArrayType = typeFactory.constructArrayType(User.class);
User[] users = mapper.readValue(json, userArrayType);
```

### 3.2. Map

Để đọc `Map<String, User>`:

```java
JavaType userMapType = typeFactory.constructMapType(
        Map.class,
        String.class,
        User.class
);

Map<String, User> usersById = mapper.readValue(json, userMapType);
```

`constructMapType()` nhận lớp map, kiểu key và kiểu value. Với kiểu map lồng collection, trước hết xây dựng `JavaType` cho value rồi truyền nó vào map type.

### 3.3. Wrapper có tham số tổng quát

Giả sử ứng dụng có lớp wrapper:

```java
public class ApiResponse<T> {
    private boolean success;
    private String message;
    private T data;

    public ApiResponse() {
    }

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
```

Tạo `ApiResponse<User>`:

```java
JavaType userResponseType = typeFactory.constructParametricType(
        ApiResponse.class,
        User.class
);

ApiResponse<User> response = mapper.readValue(json, userResponseType);
```

Tạo `ApiResponse<List<User>>` cần xây dựng kiểu danh sách trước:

```java
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

Overload `constructParametricType(Class<?>, JavaType...)` cho phép truyền một kiểu tham số đã được xây dựng sẵn, vì vậy có thể ghép nhiều lớp tổng quát thành cấu trúc lồng nhau.

### 3.4. Kết hợp nhiều kiểu lồng nhau

Ví dụ tạo `Map<String, List<User>>`:

```java
JavaType userListType = typeFactory.constructCollectionType(
        List.class,
        User.class
);

JavaType groupedUsersType = typeFactory.constructMapType(
        Map.class,
        typeFactory.constructType(String.class),
        userListType
);

Map<String, List<User>> groupedUsers = mapper.readValue(
        json,
        groupedUsersType
);
```

Khi cấu trúc sâu hơn, hãy xây dựng từ kiểu trong cùng ra ngoài. Mỗi `JavaType` có thể được tái sử dụng làm tham số của một kiểu collection, map hoặc wrapper khác.

## 4. Thiết kế API tiện ích JSON có hỗ trợ generic

Một API tiện ích tự xây dựng nên cung cấp các overload cho ba mức thông tin kiểu:

- `Class<T>` cho kiểu đơn giản như `User` hoặc `String`.
- `TypeReference<T>` cho kiểu generic được khai báo tại nơi gọi.
- `JavaType` cho kiểu được xây dựng động hoặc tái sử dụng.

Ví dụ một lớp `JsonCodec`:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;

import java.util.Objects;

public final class JsonCodec {
    private final ObjectMapper mapper;

    public JsonCodec(ObjectMapper mapper) {
        this.mapper = Objects.requireNonNull(mapper);
    }

    public <T> T read(String json, Class<T> targetType)
            throws JsonProcessingException {
        return mapper.readValue(json, targetType);
    }

    public <T> T read(String json, TypeReference<T> targetType)
            throws JsonProcessingException {
        return mapper.readValue(json, targetType);
    }

    public <T> T read(String json, JavaType targetType)
            throws JsonProcessingException {
        return mapper.readValue(json, targetType);
    }

    public String write(Object value) throws JsonProcessingException {
        return mapper.writeValueAsString(value);
    }

    public String write(Object value, JavaType declaredType)
            throws JsonProcessingException {
        ObjectWriter writer = mapper.writerFor(declaredType);
        return writer.writeValueAsString(value);
    }
}
```

Các overload `read()` có cùng mục tiêu nhưng nhận ba cách mô tả kiểu khác nhau. Caller không cần tự ép kiểu kết quả hoặc tự phân tích JSON thành map. Constructor nhận mapper đã cấu hình để tiện ích dùng chung chính sách Jackson của ứng dụng.

### 4.1. Cách gọi với kiểu đơn giản và generic

```java
JsonCodec codec = new JsonCodec(mapper);

User user = codec.read(userJson, User.class);

List<User> users = codec.read(
        usersJson,
        new TypeReference<List<User>>() {}
);

ApiResponse<List<User>> response = codec.read(
        responseJson,
        new TypeReference<ApiResponse<List<User>>>() {}
);
```

Kiểu trả về `T` được suy ra từ đối số `Class<T>` hoặc `TypeReference<T>`. Cấu trúc kiểu được giữ xuyên suốt lời gọi, nên mã gọi có thể sử dụng kết quả với kiểu cụ thể.

### 4.2. API helper cho danh sách và map

Nếu tiện ích thường đọc collection, có thể bổ sung phương thức tiện lợi nhận lớp phần tử:

```java
public <T> List<T> readList(String json, Class<T> elementType)
        throws JsonProcessingException {
    JavaType listType = mapper.getTypeFactory()
            .constructCollectionType(List.class, elementType);
    return mapper.readValue(json, listType);
}

public <T> Map<String, T> readMap(String json, Class<T> valueType)
        throws JsonProcessingException {
    JavaType mapType = mapper.getTypeFactory()
            .constructMapType(Map.class, String.class, valueType);
    return mapper.readValue(json, mapType);
}
```

Các helper này dễ dùng khi key luôn là `String` và phần tử/value là một lớp cụ thể. Nếu caller cần `List<Map<String, User>>`, `Map<UUID, List<User>>` hoặc wrapper lồng nhau, hãy dùng overload nhận `TypeReference<T>` hoặc `JavaType` tổng quát hơn.

## 5. Không tạo `TypeReference<List<T>>` một cách mù quáng trong generic method

Một lỗi thường gặp là viết tiện ích như sau:

```java
public <T> List<T> readList(String json) throws JsonProcessingException {
    return mapper.readValue(
            json,
            new TypeReference<List<T>>() {}
    );
}
```

Đoạn code này nhìn có vẻ giữ được `T`, nhưng `T` ở đây là type variable của generic method. Type erasure khiến phương thức không tự biết caller muốn `User`, `Order` hay kiểu nào khác tại runtime. `TypeReference` chỉ giữ lại thông tin mà nó thực sự nhìn thấy; nó không thể suy ra kiểu cụ thể từ biến nhận kết quả ở phía caller.

Hãy thay bằng một trong các API tường minh:

**Cách 1: nhận `Class<T>` khi phần tử là kiểu cụ thể.**

```java
public <T> List<T> readList(String json, Class<T> elementType)
        throws JsonProcessingException {
    JavaType listType = mapper.getTypeFactory()
            .constructCollectionType(List.class, elementType);
    return mapper.readValue(json, listType);
}
```

**Cách 2: nhận `TypeReference<T>` khi kiểu đầy đủ có thể lồng nhau.**

```java
public <T> T read(String json, TypeReference<T> targetType)
        throws JsonProcessingException {
    return mapper.readValue(json, targetType);
}
```

**Cách 3: nhận `JavaType` khi caller đã xây dựng kiểu động.**

```java
public <T> T read(String json, JavaType targetType)
        throws JsonProcessingException {
    return mapper.readValue(json, targetType);
}
```

Điểm cốt lõi là thông tin kiểu phải được truyền vào API tại runtime. Chỉ khai báo `<T>` ở chữ ký phương thức không đủ để phục hồi tham số generic đã bị xóa.

## 6. Xây dựng `JavaType` từ `Type` hoặc `TypeReference`

Đôi khi API nội bộ nhận một đối tượng `java.lang.reflect.Type`, hoặc muốn chuẩn hóa các kiểu đầu vào thành `JavaType`. `TypeFactory.constructType()` có thể chuyển `Type` thành `JavaType`:

```java
TypeReference<Map<String, List<User>>> typeReference =
        new TypeReference<Map<String, List<User>>>() {};

JavaType javaType = mapper.getTypeFactory()
        .constructType(typeReference.getType());

Map<String, List<User>> result = mapper.readValue(json, javaType);
```

Điều này hữu ích khi các lớp tiện ích cần lưu hoặc truyền một mô tả kiểu đã chuẩn hóa. Có thể dùng `JavaType.toCanonical()` để xem biểu diễn tên kiểu trong log debug, nhưng không nên dùng chuỗi canonical như một cơ chế tùy ý để nạp lớp từ dữ liệu JSON không tin cậy.

## 7. Dùng `ObjectReader` và `ObjectWriter` với kiểu generic

Khi một tiện ích thường xuyên đọc cùng một kiểu tổng quát, có thể tạo `ObjectReader` một lần từ `JavaType`:

```java
JavaType userListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);

ObjectReader userListReader = mapper.readerFor(userListType);

List<User> firstBatch = userListReader.readValue(firstJson);
List<User> secondBatch = userListReader.readValue(secondJson);
```

`ObjectReader` đã gắn với kiểu đích nên caller không cần truyền lại mỗi lần. Với đầu ra, `ObjectWriter` có thể được tạo bằng `writerFor(JavaType)`:

```java
ObjectWriter responseWriter = mapper.writerFor(responseType);
String output = responseWriter.writeValueAsString(response);
```

`writerFor()` cung cấp kiểu gốc đã khai báo cho quá trình tuần tự hóa. Trong nhiều trường hợp Jackson vẫn có thể tuần tự hóa theo kiểu runtime của object; tuy nhiên, kiểu gốc tường minh hữu ích khi cần kiểm soát hợp đồng kiểu ở root, đặc biệt với kiểu tổng quát, polymorphic typing hoặc static typing.

## 8. Kiểu tổng quát trong custom serializer và deserializer

Jackson hỗ trợ các collection và wrapper generic phổ biến mà không cần viết serializer/deserializer riêng. Chỉ nên viết custom handler khi cấu trúc JSON có quy tắc đặc biệt.

Nếu cần serializer/deserializer cho một lớp generic như `Envelope<T>`, hãy lưu ý rằng handler được chọn dựa trên kiểu đầy đủ mà Jackson phân giải. Khi triển khai deserializer phụ thuộc vào tham số kiểu `T`, không nên giả định `Envelope.class` tự chứa được kiểu phần tử. Cần dùng thông tin kiểu đã phân giải trong `JavaType` hoặc `DeserializationContext` để tìm deserializer của content type.

Một số API hỗ trợ việc này:

- `JavaType.containedType(0)` lấy kiểu tham số đầu tiên của một kiểu tham số hóa đã được giải quyết.
- `JavaType.getContentType()` lấy kiểu phần tử của collection/array hoặc kiểu value của một số container.
- `DeserializationContext.findContextualValueDeserializer(JavaType, BeanProperty)` tìm deserializer phù hợp với kiểu và ngữ cảnh property.
- `SerializerProvider.findValueSerializer(JavaType, BeanProperty)` tìm serializer phù hợp với kiểu đầu ra.

Các API contextual cho phép Jackson cung cấp handler phù hợp với property và kiểu đã biết. Đây là cách tiếp cận cần thiết khi một custom handler thực sự phải xử lý tham số generic; với `List<T>` hoặc `Map<K,V>` thông thường, serializer/deserializer tích hợp của Jackson đã đảm nhiệm việc này.

## 9. Các giới hạn và lỗi thường gặp

### 9.1. Ép kiểu danh sách raw thành danh sách generic

Đọc bằng `List.class` rồi ép thành `List<User>` không chuyển các map thành `User`. Hãy cung cấp `TypeReference<List<User>>` hoặc `JavaType` ngay tại lúc đọc.

### 9.2. Quên một lớp generic ở bên trong

Nếu tạo `ApiResponse.class`, Jackson chỉ biết lớp wrapper. Phải mô tả tham số `T` bằng `TypeReference<ApiResponse<User>>` hoặc `constructParametricType()`.

### 9.3. Mong đợi Jackson suy luận kiểu từ biến nhận kết quả

Java không truyền kiểu generic đích ngược vào phương thức ở runtime. Dù code có viết `List<User> users = readList(json)`, phương thức không tự nhận được `User.class`. Kiểu cần được truyền qua đối số.

### 9.4. Nhầm generic type với polymorphic type

`TypeReference<List<Animal>>` cho Jackson biết phần tử thuộc kiểu khai báo `Animal`. Nó không tự cho biết mỗi phần tử là `Dog` hay `Cat`. Nếu cần tạo subtype cụ thể, phải định nghĩa cơ chế polymorphic typing có kiểm soát, ví dụ `@JsonTypeInfo` và `@JsonSubTypes` với danh sách subtype được cho phép.

Không bật default typing rộng cho JSON từ nguồn không tin cậy chỉ để giải quyết vấn đề generic. Tham số generic và metadata subtype là hai thông tin khác nhau.

### 9.5. Không kiểm tra kiểu đầu vào của API tiện ích

Các phương thức nhận `TypeReference`, `JavaType` hoặc JSON cần xử lý null argument và lỗi parse phù hợp. Nếu tiện ích dùng trong nhiều module, hãy thống nhất cách ném hoặc chuyển tiếp `JsonProcessingException`; tránh nuốt lỗi rồi trả `null`, vì điều đó làm mất nguyên nhân và dễ tạo lỗi ở bước sau.

## 10. Chọn cách biểu diễn kiểu cho API tự xây dựng

| Nhu cầu của caller | Kiểu tham số nên nhận |
|---|---|
| Đọc `User`, `Order`, `String` | `Class<T>` |
| Đọc `List<User>` hoặc `ApiResponse<Map<String, User>>` được biết tại compile time | `TypeReference<T>` |
| Xây dựng `Map<K,V>`, collection hoặc wrapper từ các class/type runtime | `JavaType` qua `TypeFactory` |
| Đọc cùng một kiểu lặp lại nhiều lần | `ObjectReader` đã tạo từ `JavaType` hoặc `TypeReference` |
| Ghi với kiểu root được khai báo tường minh | `ObjectWriter` qua `writerFor(JavaType)` |
| Viết custom handler cho wrapper generic | Dùng `JavaType` đã phân giải và context/provider để tìm handler cho kiểu con |

Một API tiện ích tốt không cố đoán tham số generic từ chữ ký `<T>` của phương thức. Nó yêu cầu caller cung cấp thông tin kiểu đầy đủ bằng `Class<T>`, `TypeReference<T>` hoặc `JavaType`, rồi giao việc ánh xạ cho `ObjectMapper`. `TypeReference` thuận tiện cho kiểu khai báo tường minh; `JavaType` linh hoạt khi xây dựng cấu trúc động; còn `Class<T>` vẫn là lựa chọn đơn giản và rõ ràng cho kiểu không tham số hóa. Khi thiết kế đúng từ đầu, tiện ích JSON có thể hỗ trợ kiểu lồng nhau mà vẫn giữ được kiểu trả về an toàn và dễ sử dụng.
