# Vai trò của JavaType và TypeFactory

Khi Jackson deserialize JSON vào một kiểu Java đơn giản như `User.class`, ta có thể truyền trực tiếp đối tượng `Class`. Nhưng với kiểu generic lồng nhau như `Map<String, List<User>>`, `List<User>` hoặc `ApiResponse<Page<User>>`, `Class` không đủ để mô tả toàn bộ kiểu dữ liệu. Java xóa phần lớn thông tin generic ở runtime, nên `List.class` chỉ cho biết đây là một danh sách, không cho biết phần tử phải là `User`.

Jackson giải quyết vấn đề này bằng hai thành phần: **`JavaType`** và **`TypeFactory`**.

- `JavaType` là mô tả kiểu dữ liệu mà Jackson dùng trong quá trình serialize và deserialize. Nó có thể chứa raw class, generic bindings, kiểu phần tử, kiểu key/value và quan hệ kế thừa.
- `TypeFactory` tạo các mô tả `JavaType` từ `Class`, `Type`, `TypeReference` hoặc từ những kiểu thành phần khác đã được xây dựng.

`ObjectMapper` sử dụng `JavaType` để biết cần chuyển JSON thành kiểu Java nào. Nói cách khác, `TypeFactory` xây dựng thông tin kiểu, `JavaType` giữ thông tin đó, còn `ObjectMapper` dùng nó để thực hiện data binding.

## 1. Vì sao Class không đủ cho generic?

Với một kiểu không generic, ta có thể truyền trực tiếp class:

```java
User user = mapper.readValue(json, User.class);
```

Nhưng Java không cho phép viết `List<User>.class`:

```java
// Không hợp lệ trong Java:
List<User>.class
```

Nếu truyền `List.class`, Jackson chỉ biết đích là một `List` mà không có thông tin phần tử là `User`:

```java
List users = mapper.readValue(json, List.class);
```

Khi JSON chứa object, các phần tử có thể được đọc thành cấu trúc Map/List tổng quát (thường là `LinkedHashMap` và `ArrayList` theo cấu hình mặc định). Chúng không tự trở thành `User` chỉ vì dữ liệu có các field trùng với lớp đó.

Ví dụ JSON:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
```

Nếu muốn kết quả là `List<User>`, Jackson phải nhận được cả raw type `List` lẫn kiểu phần tử `User`. `JavaType` cung cấp cách mô tả đầy đủ đó tại runtime.

## 2. JavaType là gì?

`JavaType` thuộc Jackson Databind và đại diện cho kiểu dữ liệu đã được phân giải. Nó không phải object chứa dữ liệu JSON và cũng không phải một collection thực tế. Đây là metadata mô tả kiểu mà Jackson cần để chọn deserializer, serializer và cách xử lý các thành phần con.

Ví dụ, một `JavaType` có thể mô tả:

- `User` — một lớp Java thông thường.
- `List<User>` — collection có phần tử là `User`.
- `Map<String, User>` — map có key là `String` và value là `User`.
- `Map<String, List<User>>` — map có value là danh sách `User`.
- `ApiResponse<Page<User>>` — một kiểu generic lồng nhau nhiều cấp.

Với kiểu collection, Jackson cần biết content type. Với map, Jackson cần cả key type và value/content type. Với generic wrapper, Jackson cần biết kiểu được truyền vào từng tham số generic.

### 2.1. Các thông tin thường đọc từ JavaType

Một số phương thức hữu ích:

| Phương thức | Thông tin |
|---|---|
| `getRawClass()` | Lớp Java gốc, ví dụ `List.class` hoặc `Map.class`. |
| `getRawClass().getName()` | Tên đầy đủ của raw class. |
| `hasGenericTypes()` | Kiểu có thông tin generic hay không. |
| `containedTypeCount()` | Số kiểu tham số được chứa trong kiểu hiện tại. |
| `containedType(index)` | Kiểu tham số generic tại vị trí được chỉ định. |
| `getContentType()` | Kiểu phần tử của collection/array hoặc kiểu value của một số kiểu chứa. |
| `getKeyType()` | Kiểu key của map-like type. |
| `isCollectionLikeType()` | Kiểm tra kiểu có được Jackson xem là collection-like hay không. |
| `isMapLikeType()` | Kiểm tra kiểu có được Jackson xem là map-like hay không. |
| `isArrayType()` | Kiểm tra kiểu là array. |
| `isReferenceType()` | Kiểm tra kiểu thuộc nhóm reference type được Jackson nhận diện. |

Ví dụ kiểm tra kiểu collection:

```java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

System.out.println(userListType.getRawClass());
System.out.println(userListType.getContentType().getRawClass());
System.out.println(userListType.isCollectionLikeType());
```

Với map:

```java
JavaType userMapType = mapper.getTypeFactory()
    .constructMapType(Map.class, String.class, User.class);

System.out.println(userMapType.getKeyType().getRawClass());
System.out.println(userMapType.getContentType().getRawClass());
```

Không nên dùng `getRawClass()` một mình để kết luận kiểu generic đầy đủ. Với `List<User>` và `List<Order>`, raw class đều là `List.class`; điểm khác biệt nằm ở generic/content type.

## 3. TypeFactory làm nhiệm vụ gì?

`TypeFactory` là thành phần tạo `JavaType`. Trong ứng dụng dùng Jackson, cách thông thường là lấy factory từ mapper đang sử dụng:

```java
ObjectMapper mapper = new ObjectMapper();
TypeFactory typeFactory = mapper.getTypeFactory();
```

Sử dụng factory của mapper giúp việc xây dựng kiểu thống nhất với cấu hình type resolution mà mapper đang dùng. Khi ứng dụng dùng một mapper được framework cấu hình, hãy lấy `TypeFactory` từ chính mapper đó thay vì tự tạo một mapper mặc định khác.

### 3.1. Tạo JavaType từ một Class

Với kiểu không generic:

```java
JavaType userType = mapper.getTypeFactory().constructType(User.class);
```

Sau đó dùng kiểu này với `ObjectMapper`:

```java
User user = mapper.readValue(json, userType);
```

Với kiểu đơn giản, truyền `User.class` trực tiếp thường ngắn gọn hơn. `constructType()` hữu ích khi chương trình đang làm việc với mô tả kiểu tổng quát hoặc nhận `java.lang.reflect.Type` từ reflection.

### 3.2. Tạo collection type

`constructCollectionType()` tạo mô tả cho collection có kiểu phần tử xác định:

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory.constructCollectionType(
    List.class,
    User.class
);

List<User> users = mapper.readValue(json, userListType);
```

Có thể truyền `JavaType` làm kiểu phần tử khi phần tử cũng là kiểu generic phức tạp:

```java
JavaType userType = typeFactory.constructType(User.class);
JavaType userListType = typeFactory.constructCollectionType(
    List.class,
    userType
);
```

Đối với array Java, có thể dùng `constructArrayType()`:

```java
JavaType userArrayType = typeFactory.constructArrayType(User.class);
User[] users = mapper.readValue(json, userArrayType);
```

### 3.3. Tạo map type

Map có hai tham số kiểu: key và value. Dùng `constructMapType()` để mô tả cả hai:

```java
JavaType userMapType = typeFactory.constructMapType(
    Map.class,
    String.class,
    User.class
);

Map<String, User> usersById = mapper.readValue(json, userMapType);
```

Nếu value là kiểu generic khác, hãy xây dựng `JavaType` cho value trước rồi truyền vào overload nhận `JavaType`:

```java
JavaType userType = typeFactory.constructType(User.class);
JavaType userListType = typeFactory.constructCollectionType(List.class, userType);

JavaType groupedUsersType = typeFactory.constructMapType(
    Map.class,
    typeFactory.constructType(String.class),
    userListType
);

Map<String, List<User>> groupedUsers = mapper.readValue(json, groupedUsersType);
```

Đây là cách mô tả kiểu lồng nhau mà không cần giữ một `TypeReference` dài. Nó cũng hữu ích khi kiểu phần tử hoặc key được quyết định ở runtime.

### 3.4. Tạo kiểu generic bằng constructParametricType()

`constructParametricType()` dùng để tạo kiểu generic tổng quát khi biết raw class và các tham số kiểu:

```java
JavaType responseType = typeFactory.constructParametricType(
    ApiResponse.class,
    User.class
);
```

Với wrapper:

```java
public class ApiResponse<T> {
    private T data;
    private String status;

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Có thể đọc JSON thành `ApiResponse<User>`:

```java
JavaType apiResponseUserType = typeFactory.constructParametricType(
    ApiResponse.class,
    User.class
);

ApiResponse<User> response = mapper.readValue(json, apiResponseUserType);
User user = response.getData();
```

Nếu tham số generic là kiểu đã được xây dựng trước, truyền `JavaType` thay vì chỉ truyền `Class`:

```java
JavaType userListType = typeFactory.constructCollectionType(List.class, User.class);

JavaType responseWithUsersType = typeFactory.constructParametricType(
    ApiResponse.class,
    userListType
);

ApiResponse<List<User>> response = mapper.readValue(json, responseWithUsersType);
```

`constructParametricType()` nhận các tham số generic theo thứ tự khai báo của lớp. Số lượng và loại tham số phải phù hợp với raw class.

### 3.5. Tạo kiểu từ reflection Type

Đôi khi kiểu generic được khai báo trên field hoặc method và chỉ có thể lấy được qua reflection. Dùng `getGenericType()` thay cho `getType()` để giữ thông tin generic:

```java
public class Batch {
    private Map<String, List<User>> users;
}
```

```java
Field field = Batch.class.getDeclaredField("users");
Type genericType = field.getGenericType();

JavaType javaType = mapper.getTypeFactory().constructType(genericType);
```

`Field.getType()` chỉ trả về raw class `Map.class`; `Field.getGenericType()` trả về metadata generic như `Map<String, List<User>>`. `TypeFactory.constructType()` chuyển metadata reflection đó thành `JavaType` mà Jackson có thể dùng.

## 4. TypeReference và JavaType khác nhau thế nào?

`TypeReference<T>` là cách tiện lợi để giữ generic type trong mã nguồn. Nó dùng anonymous subclass để giữ thông tin kiểu tham số trong generic superclass, giúp Jackson đọc lại kiểu đó khi runtime.

Ví dụ:

```java
List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);
```

Ở phía dưới, Jackson có thể chuyển mô tả từ `TypeReference` thành `JavaType` thông qua `TypeFactory`.

So sánh:

| Tiêu chí | TypeReference | JavaType |
|---|---|---|
| Cách tạo | Thường dùng anonymous subclass với generic cụ thể | Tạo từ `TypeFactory` hoặc reflection Type |
| Độ tiện lợi | Rất gọn cho kiểu generic biết trước khi viết code | Linh hoạt khi kiểu được xây dựng ở runtime |
| Kiểu lồng nhau | Có thể viết trực tiếp `new TypeReference<Map<String, List<User>>>() {}` | Xây dựng từng tầng rồi ghép lại |
| Tái sử dụng | Có thể giữ instance TypeReference | Thường thuận tiện giữ mô tả JavaType để dùng với nhiều API Jackson |
| Dùng với ObjectMapper | Có overload nhận TypeReference | Có overload nhận JavaType |

Ví dụ `TypeReference` cho map lồng nhau:

```java
Map<String, List<User>> groups = mapper.readValue(
    json,
    new TypeReference<Map<String, List<User>>>() {}
);
```

Ví dụ cùng kiểu bằng `JavaType`:

```java
TypeFactory tf = mapper.getTypeFactory();
JavaType userList = tf.constructCollectionType(List.class, User.class);
JavaType groupsType = tf.constructMapType(
    Map.class,
    String.class,
    userList
);

Map<String, List<User>> groups = mapper.readValue(json, groupsType);
```

Nếu kiểu đã biết tĩnh và không cần thao tác với type descriptor, `TypeReference` thường dễ đọc. Nếu kiểu được ghép từ nhiều lựa chọn runtime, lấy từ reflection hoặc cần truyền qua nhiều tầng API, `JavaType` thuận tiện hơn.

## 5. Dùng JavaType với ObjectMapper và ObjectReader

Sau khi tạo `JavaType`, có thể dùng nó ở nơi API Jackson cần thông tin kiểu đích.

### 5.1. Đọc JSON bằng readValue()

```java
JavaType type = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

List<User> users = mapper.readValue(json, type);
```

`ObjectMapper` dùng type descriptor để chọn deserializer cho collection và từng phần tử. Không cần cast từng phần tử từ `Object` sang `User`.

### 5.2. Tạo reader có kiểu đích cố định

Nếu cùng một kiểu được dùng để đọc nhiều lần, tạo `ObjectReader`:

```java
JavaType type = mapper.getTypeFactory()
    .constructMapType(Map.class, String.class, User.class);

ObjectReader reader = mapper.readerFor(type);

Map<String, User> first = reader.readValue(firstJson);
Map<String, User> second = reader.readValue(secondJson);
```

Reader giữ kiểu đích đã xác định, giúp code gọi ngắn gọn và có thể tái sử dụng. `ObjectReader` là đối tượng cấu hình bất biến; tạo reader mới từ mapper không làm thay đổi mapper nền.

### 5.3. Dùng JavaType khi serialize

`ObjectWriter` cũng có thể nhận `JavaType`:

```java
JavaType type = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

ObjectWriter writer = mapper.writerFor(type);
String json = writer.writeValueAsString(users);
```

Với serialize một object cụ thể, Jackson có thể suy ra kiểu từ runtime object. Nhưng khi cần ràng buộc kiểu khai báo, xử lý generic hoặc làm việc với polymorphism, `writerFor(JavaType)` giúp mô tả kiểu đích rõ ràng.

## 6. Đọc cấu trúc JavaType lồng nhau

Một lợi ích của `JavaType` là có thể kiểm tra từng tầng của kiểu. Ví dụ:

```java
TypeFactory tf = mapper.getTypeFactory();
JavaType userType = tf.constructType(User.class);
JavaType userListType = tf.constructCollectionType(List.class, userType);
JavaType resultType = tf.constructMapType(
    Map.class,
    tf.constructType(String.class),
    userListType
);
```

Có thể truy vấn cấu trúc:

```java
System.out.println(resultType.getRawClass());
System.out.println(resultType.getKeyType().getRawClass());

JavaType valueType = resultType.getContentType();
System.out.println(valueType.getRawClass());
System.out.println(valueType.getContentType().getRawClass());
```

Kết quả về mặt kiểu tương ứng:

```text
Map.class
String.class
List.class
User.class
```

`getContentType()` trả kiểu nội dung của collection hoặc value của map-like type. `getKeyType()` trả kiểu key của map. Với generic wrapper không phải collection/map, có thể dùng `containedType(index)` để truy vấn tham số generic theo vị trí.

Ví dụ:

```java
JavaType responseType = tf.constructParametricType(ApiResponse.class, User.class);

JavaType dataType = responseType.containedType(0);
System.out.println(dataType.getRawClass()); // User.class
```

Không nên giả định mọi kiểu đều có content type hoặc key type. Hãy kiểm tra loại JavaType trước khi truy vấn các thành phần đặc thù:

```java
if (type.isMapLikeType()) {
    JavaType keyType = type.getKeyType();
    JavaType valueType = type.getContentType();
}

if (type.isCollectionLikeType() || type.isArrayType()) {
    JavaType elementType = type.getContentType();
}
```

## 7. Các API TypeFactory hữu ích khác

Ngoài `constructType()`, `constructCollectionType()`, `constructMapType()` và `constructParametricType()`, `TypeFactory` còn cung cấp các phương thức cho kiểu chuyên biệt.

| API | Mục đích |
|---|---|
| `constructArrayType(elementType)` | Mô tả array có kiểu phần tử xác định. |
| `constructCollectionLikeType(rawClass, elementType)` | Mô tả kiểu collection-like tùy chỉnh được Jackson nhận diện. |
| `constructMapLikeType(rawClass, keyType, valueType)` | Mô tả kiểu map-like tùy chỉnh. |
| `constructSpecializedType(baseType, subclass)` | Tạo mô tả kiểu subtype dựa trên kiểu cơ sở. |
| `constructGeneralizedType(subType, superClass)` | Tạo mô tả kiểu tổng quát hơn từ subtype. |
| `constructType(typeReference)` | Chuyển `TypeReference` thành `JavaType`. |

### 7.1. Kiểu collection-like và map-like

Với các kiểu chuẩn như `List` và `Map`, ưu tiên `constructCollectionType()` và `constructMapType()`. Nếu ứng dụng có kiểu tùy chỉnh được Jackson xem là collection-like hoặc map-like, có thể dùng các API tương ứng:

```java
JavaType customCollectionType = tf.constructCollectionLikeType(
    CustomBag.class,
    User.class
);
```

Chỉ dùng API này khi Jackson có thể xử lý kiểu tùy chỉnh đó thông qua serializer/deserializer hoặc introspection tương ứng. Việc tạo được JavaType không tự động làm một lớp bất kỳ trở thành collection mà Jackson có thể đọc/ghi.

### 7.2. Chuyển đổi giữa kiểu cha và kiểu con

Trong một số tình huống polymorphism, cần mô tả subtype của một kiểu cơ sở:

```java
JavaType paymentType = tf.constructType(Payment.class);
JavaType cardPaymentType = tf.constructSpecializedType(
    paymentType,
    CardPayment.class
);
```

`constructSpecializedType()` giúp xây dựng mô tả kiểu cụ thể hơn dựa trên kiểu cơ sở. Đây là thao tác về metadata kiểu; việc Jackson có thể deserialize subtype nào còn phụ thuộc cấu hình polymorphic typing, annotation như `@JsonTypeInfo`, subtype đã đăng ký và chính sách bảo mật của ứng dụng.

## 8. Chọn TypeFactory từ đúng ObjectMapper

Jackson có thể tạo `TypeFactory` mặc định, nhưng trong ứng dụng thực tế nên lấy từ mapper đang thực hiện binding:

```java
TypeFactory typeFactory = applicationMapper.getTypeFactory();
```

Điều này giúp dùng cùng type-resolution context mà mapper đang sử dụng. Đặc biệt trong ứng dụng framework, mapper được inject có thể đã được cấu hình module, mix-in hoặc các thiết lập khác. Tạo một `new ObjectMapper()` chỉ để lấy `TypeFactory` có thể khiến phần mô tả kiểu và phần binding không còn dùng chung cấu hình.

`JavaType` là mô tả kiểu, không chứa dữ liệu JSON. Có thể tạo một JavaType rồi dùng nó cho nhiều lần đọc với cùng cấu trúc. Khi cần kiểu khác, hãy tạo descriptor khác thay vì cố thay đổi ý nghĩa của descriptor đã dùng.

## 9. Lựa chọn cách mô tả generic type

| Tình huống | Cách nên dùng |
|---|---|
| Kiểu không generic, ví dụ `User` | Truyền `User.class` trực tiếp hoặc `constructType(User.class)` |
| `List<User>` đã biết khi viết code | `TypeReference<List<User>>` hoặc `constructCollectionType()` |
| `Map<String, User>` | `constructMapType()` |
| `Map<String, List<User>>` | Xây `JavaType` cho `List<User>` rồi dùng `constructMapType()` |
| `ApiResponse<User>` | `constructParametricType()` |
| `ApiResponse<List<User>>` | Xây `JavaType` cho list rồi truyền vào `constructParametricType()` |
| Kiểu generic lấy từ field/method reflection | `getGenericType()` rồi `constructType()` |
| Kiểu cần tái sử dụng với nhiều lần đọc | Tạo `JavaType`, sau đó tạo `ObjectReader` |

Một nguyên tắc thực tế: nếu kiểu generic được biết đầy đủ tại compile time, `TypeReference` thường dễ đọc; nếu kiểu được ghép động từ các class hoặc type descriptor khác, `JavaType` và `TypeFactory` linh hoạt hơn.

## 10. Những lỗi thường gặp

**Dùng raw `List.class` rồi cast phần tử thành DTO.** Raw type không giữ thông tin phần tử. Hãy cung cấp `TypeReference<List<User>>` hoặc `JavaType` của `List<User>` để Jackson tạo đúng kiểu phần tử.

**Dùng `Field.getType()` thay vì `getGenericType()`.** `getType()` chỉ trả raw class đối với field generic. Dùng `getGenericType()` để giữ thông tin như `Map<String, List<User>>`.

**Quên kiểu value hoặc key của Map.** Một map có hai tham số kiểu. Hãy mô tả cả key và value bằng `constructMapType()`.

**Xây dựng nested generic bằng raw class ở mọi tầng.** Nếu chỉ truyền `List.class` làm value type, Jackson không biết phần tử bên trong phải là `User`. Hãy xây `JavaType` từ trong ra ngoài.

**Tạo mapper khác chỉ để lấy TypeFactory.** Điều này có thể tách biệt cấu hình type resolution khỏi mapper đang thực hiện binding. Dùng `applicationMapper.getTypeFactory()`.

**Cho rằng JavaType tự tạo ra serializer/deserializer cho kiểu tùy chỉnh.** JavaType chỉ mô tả kiểu. Jackson vẫn cần serializer/deserializer phù hợp hoặc cơ chế introspection hỗ trợ kiểu đó.

## Kết luận

`JavaType` giúp Jackson giữ thông tin kiểu generic mà `Class` không thể biểu diễn đầy đủ ở runtime. `TypeFactory` tạo các descriptor này từ class, reflection type, TypeReference hoặc từ những kiểu thành phần đã xây dựng. Khi cần đọc hoặc ghi collection, map hay generic wrapper lồng nhau, hãy tạo JavaType đúng cấu trúc rồi truyền cho `ObjectMapper`, `ObjectReader` hoặc `ObjectWriter`. Cách này giúp Jackson biết chính xác kiểu phần tử và tham số generic, tránh deserialize thành các cấu trúc raw như `Map` và `List` tổng quát.
