# Kiểm tra kiểu kết quả thay vì dựa vào ép kiểu không an toàn

Khi đọc JSON bằng Jackson, ứng dụng thường biết trước kiểu dữ liệu mong muốn: một `User`, một `List<Order>` hoặc một `Map<String, List<Product>>`. Nếu chỉ yêu cầu Jackson trả về `Object` rồi ép kiểu bằng cast, code có thể biên dịch nhưng lỗi chỉ xuất hiện khi chạy, đôi khi ở một vị trí rất xa nơi dữ liệu được đọc.

Java còn có type erasure: thông tin generic như `List<User>` không tồn tại đầy đủ dưới dạng `Class` tại runtime. Vì vậy, truyền `List.class` cho Jackson chỉ cho biết kết quả là một List, không cho biết từng phần tử phải là `User`. Muốn ánh xạ đúng kiểu generic và kiểm tra kết quả an toàn, cần cung cấp đầy đủ thông tin kiểu cho Jackson và dùng các phép kiểm tra kiểu phù hợp.

Các ví dụ trong bài sử dụng Jackson 2.x với package `com.fasterxml.jackson`. Khi dùng Jackson major version khác, hãy đối chiếu API tương ứng.

## 1. Vì sao ép kiểu trực tiếp không an toàn?

Xét đoạn code:

```java
Object result = mapper.readValue(json, Object.class);
User user = (User) result;
```

Khi target là `Object.class`, Jackson thường chọn kiểu Java tự nhiên cho JSON:

| JSON | Kiểu Java thường nhận được |
|---|---|
| Object `{...}` | `Map` (thường là `LinkedHashMap`) |
| Array `[...]` | `List` (thường là `ArrayList`) |
| String | `String` |
| Số nguyên | `Integer`, `Long` hoặc kiểu số phù hợp với giá trị/cấu hình |
| Số thập phân | `Double` hoặc kiểu số phù hợp với cấu hình |
| Boolean | `Boolean` |
| `null` | `null` |

Nếu JSON là object, `result` có thể là `LinkedHashMap`, nên cast sang `User` sẽ ném `ClassCastException`.

Một biến thể khác trông có vẻ hợp lý nhưng vẫn không an toàn:

```java
List<User> users = (List<User>) mapper.readValue(json, List.class);
```

Jackson chỉ được yêu cầu tạo một `List` thô. Các phần tử bên trong thường là `LinkedHashMap`; phép cast `List<User>` không kiểm tra từng phần tử vì generic type đã bị xóa ở runtime. Lỗi có thể xuất hiện sau đó khi ứng dụng lấy phần tử và coi nó là `User`.

```java
User first = users.get(0); // Có thể phát sinh ClassCastException tại đây
```

Điều quan trọng là phân biệt hai câu hỏi:

1. Đối tượng bên ngoài có phải là `List` hay không?
2. Mỗi phần tử bên trong có thực sự là `User` hay không?

`List.class` chỉ trả lời câu hỏi thứ nhất.

## 2. Truyền `Class<T>` khi kiểu đích là một lớp cụ thể

Nếu kiểu kết quả không cần generic parameter, hãy truyền `Class<T>` trực tiếp cho `readValue()`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

User user = mapper.readValue(json, User.class);
```

Jackson biết target là `User`, nên tạo object `User` và ánh xạ các property JSON vào property tương ứng. Kiểu trả về của overload này cũng là `T`, giúp compiler kiểm tra kiểu ở phía gọi.

Có thể viết một phương thức dùng lại cho các lớp cụ thể:

```java
public <T> T read(String json, Class<T> targetType) throws IOException {
    return mapper.readValue(json, targetType);
}
```

Sử dụng:

```java
User user = read(json, User.class);
Product product = read(productJson, Product.class);
```

`Class<T>` phù hợp với `User`, `Product`, `String`, `Order[]` hoặc một kiểu không cần giữ generic argument. Nó không thể biểu diễn đầy đủ `List<User>` hay `ApiResponse<User>` vì `List<User>.class` và `ApiResponse<User>.class` không phải cú pháp Java hợp lệ.

## 3. Dùng `TypeReference<T>` để giữ thông tin generic

Jackson cung cấp `TypeReference<T>` để ghi lại kiểu generic thông qua generic superclass của một anonymous subclass. Đây là cách phổ biến khi target là collection hoặc kiểu lồng nhau.

### 3.1. Đọc `List<User>`

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

ObjectMapper mapper = new ObjectMapper();

List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
);
```

Đoạn `new TypeReference<List<User>>() {}` tạo một lớp con ẩn danh có khai báo generic cụ thể. Jackson đọc được `List<User>` từ thông tin kiểu được giữ trong superclass, nên có thể deserialize từng phần tử thành `User` thay vì một map tùy ý.

### 3.2. Đọc `Map<String, User>`

```java
Map<String, User> usersById = mapper.readValue(
        json,
        new TypeReference<Map<String, User>>() {}
);
```

Jackson biết key là `String` và value là `User`. Với JSON object, mỗi property value được ánh xạ thành một `User`.

### 3.3. Đọc kiểu generic lồng nhau

`TypeReference` có thể mô tả nhiều tầng generic:

```java
Map<String, List<Order>> ordersByCustomer = mapper.readValue(
        json,
        new TypeReference<Map<String, List<Order>>>() {}
);
```

Kết quả có kiểu tĩnh là `Map<String, List<Order>>`; các phần tử của từng list được tạo thành `Order`.

Một ví dụ khác là response wrapper:

```java
ApiResponse<User> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<User>>() {}
);
```

Để Jackson ánh xạ wrapper, lớp `ApiResponse<T>` cần có property và constructor/setter phù hợp với cấu trúc JSON. `TypeReference` cung cấp thông tin `T = User` cho quá trình deserialize.

## 4. Không tạo `TypeReference<T>` mù quáng bên trong generic method

Một lỗi dễ gặp là viết helper như sau:

```java
public <T> List<T> readList(String json) throws IOException {
    return mapper.readValue(json, new TypeReference<List<T>>() {});
}
```

Nhìn qua, code có vẻ giữ được `T`, nhưng tại nơi tạo anonymous subclass, `T` vẫn là một type variable đã bị erasure. Jackson không thể suy ra caller thực sự muốn `List<User>` hay `List<Order>` chỉ từ `T`.

Giải pháp là truyền type token từ caller vào helper:

```java
public <T> List<T> readList(
        String json,
        TypeReference<List<T>> targetType) throws IOException {
    return mapper.readValue(json, targetType);
}
```

Caller cung cấp kiểu cụ thể:

```java
List<User> users = readList(
        json,
        new TypeReference<List<User>>() {}
);

List<Order> orders = readList(
        orderJson,
        new TypeReference<List<Order>>() {}
);
```

Quy tắc cần nhớ: generic helper không tự biết kiểu cụ thể của `T` ở runtime. Caller phải truyền thông tin kiểu có thể quan sát được, thường qua `Class<T>`, `TypeReference<T>` hoặc `JavaType`.

## 5. Dùng `JavaType` khi kiểu đích được xây dựng động

`TypeReference` tiện cho kiểu đã biết tại thời điểm viết code. Khi kiểu đích được quyết định trong runtime, có thể dùng `JavaType` và `TypeFactory`.

### 5.1. Tạo kiểu collection

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.type.TypeFactory;

TypeFactory typeFactory = mapper.getTypeFactory();
JavaType usersType = typeFactory.constructCollectionType(List.class, User.class);

List<User> users = mapper.readValue(json, usersType);
```

`constructCollectionType()` tạo mô tả kiểu collection có element type là `User`. Overload của `readValue()` nhận `JavaType`, nên Jackson vẫn biết kiểu phần tử dù Java không có `List<User>.class`.

### 5.2. Tạo kiểu map có value là collection

```java
JavaType orderListType = typeFactory.constructCollectionType(List.class, Order.class);

JavaType ordersByCustomerType = typeFactory.constructMapType(
        Map.class,
        typeFactory.constructType(String.class),
        orderListType
);

Map<String, List<Order>> ordersByCustomer =
        mapper.readValue(json, ordersByCustomerType);
```

Mỗi tầng kiểu được xây dựng riêng: kiểu list của `Order`, rồi kiểu map có key `String` và value là list đó. Cách này hữu ích khi một phần kiểu đến từ cấu hình, registry hoặc metadata runtime.

### 5.3. Tạo kiểu wrapper generic

Giả sử API trả về:

```json
{
  "success": true,
  "data": {
    "id": 10,
    "name": "An"
  }
}
```

Wrapper Java:

```java
public class ApiResponse<T> {
    private boolean success;
    private T data;

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
}
```

Tạo `JavaType` cho `ApiResponse<User>`:

```java
JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, User.class);

ApiResponse<User> response = mapper.readValue(json, responseType);
User user = response.getData();
```

Với kiểu lồng nhau, có thể truyền một `JavaType` làm tham số generic khác:

```java
JavaType userListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);

JavaType responseOfUsersType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, userListType);

ApiResponse<List<User>> responseOfUsers =
        mapper.readValue(json, responseOfUsersType);
```

`JavaType` là mô tả kiểu do Jackson quản lý. Nó giữ được thông tin collection element, map key/value và generic parameter mà một `Class<?>` đơn lẻ không thể biểu diễn.

## 6. Chọn giữa `Class<T>`, `TypeReference<T>` và `JavaType`

| Cách truyền kiểu | Phù hợp khi | Ví dụ |
|---|---|---|
| `Class<T>` | Kiểu cụ thể, không cần generic argument | `User.class` |
| `TypeReference<T>` | Kiểu generic đã biết khi viết code | `new TypeReference<List<User>>() {}` |
| `JavaType` | Cần xây dựng kiểu động hoặc lồng nhiều tầng từ metadata runtime | `constructCollectionType(...)` |

Đừng chọn `Object.class` chỉ vì không biết cách truyền generic type. Nếu biết schema của response, hãy mô tả nó đầy đủ cho Jackson. Nếu thực sự không biết shape, đọc thành `JsonNode` rồi kiểm tra cấu trúc trước khi quyết định ánh xạ.

## 7. Kiểm tra kiểu runtime an toàn với `Class.isInstance()` và `Class.cast()`

Đôi khi ứng dụng nhận object từ API tổng quát hoặc một thư viện trả về `Object`. Nếu cần xác nhận kiểu runtime, hãy kiểm tra trước khi dùng:

```java
Object value = someApiCall();

if (!User.class.isInstance(value)) {
    throw new IllegalArgumentException("Expected User result");
}

User user = User.class.cast(value);
```

`Class.isInstance(value)` kiểm tra object có phải instance của kiểu được đại diện bởi `Class` hay không. `Class.cast(value)` thực hiện phép cast có kiểm tra và ném `ClassCastException` ngay tại vị trí cast nếu kiểu không phù hợp.

Trong code hiện đại, có thể dùng pattern matching cho `instanceof`:

```java
if (value instanceof User user) {
    System.out.println(user.getName());
} else {
    throw new IllegalArgumentException("Expected User result");
}
```

Với Jackson, cách tốt hơn thường là truyền `User.class` ngay cho `readValue()` để Jackson tạo đúng kiểu từ đầu. Runtime check hữu ích khi kiểu chỉ được biết sau khi nhận kết quả từ một API tổng quát.

### 7.1. Kiểm tra collection chỉ xác nhận được kiểu collection bên ngoài

Java không cho phép:

```java
if (value instanceof List<User>) { // Không hợp lệ do type erasure
    // ...
}
```

Có thể kiểm tra raw container:

```java
if (!(value instanceof List<?> list)) {
    throw new IllegalArgumentException("Expected a list");
}
```

Nhưng `List<?>` chỉ nói rằng đây là list có phần tử thuộc kiểu chưa biết. Nếu cần kiểm tra mỗi phần tử là `User`, phải duyệt:

```java
List<User> users = new ArrayList<>();

for (Object item : list) {
    if (item == null || !User.class.isInstance(item)) {
        throw new IllegalArgumentException("List contains a non-User value");
    }
    users.add(User.class.cast(item));
}
```

Ví dụ trên chủ động từ chối phần tử null. Nếu nghiệp vụ cho phép null, hãy quy định rõ và xử lý riêng thay vì vô tình bỏ qua.

Việc duyệt và kiểm tra thủ công là phương án phòng vệ khi dữ liệu đã được tạo từ một nguồn không có type metadata. Với JSON, nên dùng `TypeReference<List<User>>` hoặc `JavaType` để Jackson deserialize đúng kiểu phần tử ngay từ đầu.

## 8. Dùng `ObjectReader` khi muốn tái sử dụng target type

Nếu nhiều lần đọc cùng một kiểu, có thể tạo `ObjectReader` từ mapper:

```java
import com.fasterxml.jackson.databind.ObjectReader;

ObjectReader userListReader = mapper.readerFor(
        new TypeReference<List<User>>() {}
);

List<User> users1 = userListReader.readValue(json1);
List<User> users2 = userListReader.readValue(json2);
```

Hoặc dùng `JavaType`:

```java
ObjectReader responseReader = mapper.readerFor(responseType);
ApiResponse<User> response = responseReader.readValue(json);
```

`ObjectReader` là đối tượng cấu hình đọc bất biến, phù hợp để tái sử dụng cho một target type hoặc một nhóm thiết lập đọc. Nó giúp tránh phải truyền lại `TypeReference`/`JavaType` ở mọi lời gọi.

## 9. `convertValue()` cũng cần target type cụ thể

`convertValue()` chuyển một giá trị Java đang có sang kiểu đích thông qua cơ chế databinding của Jackson. Nó hữu ích khi dữ liệu hiện có là `Map`, POJO khác hoặc cây dữ liệu và cần chuyển sang DTO.

```java
Map<String, Object> raw = Map.of(
        "id", 10,
        "name", "An"
);

User user = mapper.convertValue(raw, User.class);
```

Với collection generic:

```java
List<User> users = mapper.convertValue(
        rawList,
        new TypeReference<List<User>>() {}
);
```

Hoặc:

```java
List<User> users = mapper.convertValue(rawList, usersType);
```

Không nên cast kết quả của `convertValue()` sang một kiểu generic không được mô tả. Truyền target type rõ ràng giúp Jackson thực hiện chuyển đổi từng phần tử theo kiểu mong muốn.

Lưu ý `convertValue()` không phải cách thay thế cho mọi trường hợp serialize rồi deserialize. Nó không tạo JSON text trung gian theo cách API tên gọi có thể khiến người đọc suy luận; nó dùng cơ chế chuyển đổi nội bộ của Databind. Lỗi ánh xạ thường được biểu diễn qua `IllegalArgumentException` với nguyên nhân gốc liên quan đến mapping.

## 10. Dữ liệu không có schema cố định: dùng `JsonNode` trước khi chọn kiểu

Nếu JSON có nhiều shape khác nhau và kiểu kết quả phụ thuộc vào một discriminator, có thể đọc thành cây JSON rồi kiểm tra trước:

```java
import com.fasterxml.jackson.databind.JsonNode;

JsonNode root = mapper.readTree(json);
JsonNode typeNode = root.path("type");

if (!typeNode.isTextual()) {
    throw new IllegalArgumentException("Missing textual type field");
}

switch (typeNode.asText()) {
    case "user" -> {
        User user = mapper.treeToValue(root, User.class);
        // Xử lý user
    }
    case "order" -> {
        Order order = mapper.treeToValue(root, Order.class);
        // Xử lý order
    }
    default -> throw new IllegalArgumentException("Unsupported payload type");
}
```

Ở đây, ứng dụng chủ động chọn một trong các kiểu được cho phép. `treeToValue()` vẫn nhận target class cụ thể. Đây là cách hữu ích khi làm việc với webhook hoặc message có một số biến thể được định nghĩa trước.

Không nên bật default typing rộng hoặc cho phép JSON tùy ý chỉ định tên class Java để Jackson khởi tạo. Dữ liệu ngoài không được quyền quyết định mọi class có thể được nạp. Nếu cần polymorphic deserialization, hãy giới hạn subtype bằng allowlist và cấu hình `PolymorphicTypeValidator` phù hợp với version.

## 11. Xử lý lỗi mapping và lỗi kiểu kết quả

Khi target type không khớp cấu trúc JSON, Jackson có thể ném các exception như `MismatchedInputException`, `InvalidDefinitionException` hoặc một `JsonMappingException` cụ thể. Chúng giúp xác định lỗi xảy ra ở đâu trong cây dữ liệu.

Ví dụ:

```java
try {
    List<User> users = mapper.readValue(
            json,
            new TypeReference<List<User>>() {}
    );
} catch (JsonMappingException ex) {
    // Ghi nhận đường dẫn property/index mà Jackson cung cấp.
    throw new IllegalArgumentException("Response does not match List<User>", ex);
}
```

Một số tình huống thường gặp:

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| `ClassCastException` sau deserialize | Đọc thành `Object` hoặc raw collection rồi cast ở nơi sử dụng |
| Phần tử list là `LinkedHashMap` | Dùng `List.class` thay vì truyền `TypeReference<List<User>>` hoặc `JavaType` |
| Không tạo được wrapper generic | Không cung cấp generic parameter cho `ApiResponse<T>` |
| `MismatchedInputException` | JSON có shape hoặc kiểu giá trị không phù hợp target type |
| `InvalidDefinitionException` | Jackson không tìm được cách tạo/ánh xạ kiểu đích theo cấu hình hiện tại |
| Generic helper trả về kiểu không như mong đợi | Type variable bị erasure; helper tự tạo `TypeReference<T>` không chứa kiểu cụ thể của caller |

Không bắt `Exception` rồi cast lại theo phỏng đoán. Hãy ghi nhận target type mong đợi, đường dẫn JSON và nguyên nhân gốc. Với dữ liệu từ bên ngoài, chuyển lỗi mapping thành phản hồi có kiểm soát; không để stack trace nội bộ lộ ra client.

## 12. Ví dụ tổng hợp: client đọc API response có generic wrapper

Giả sử một API trả về danh sách user trong wrapper:

```json
{
  "success": true,
  "data": [
    {"id": 1, "name": "An"},
    {"id": 2, "name": "Binh"}
  ]
}
```

Model:

```java
public class User {
    private long id;
    private String name;

    public User() {
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

public class ApiResponse<T> {
    private boolean success;
    private T data;

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
}
```

Đọc response:

```java
ApiResponse<List<User>> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<List<User>>>() {}
);

if (!response.isSuccess()) {
    throw new IllegalStateException("Remote API reported failure");
}

List<User> users = response.getData();
```

Jackson nhận đầy đủ kiểu lồng nhau nên `data` được tạo thành `List<User>`. Ứng dụng vẫn cần kiểm tra ý nghĩa của `success`, nullability của `data` và các quy tắc nghiệp vụ của từng user. Type-safe deserialization bảo đảm kiểu cấu trúc được ánh xạ; nó không tự chứng minh mọi giá trị đều hợp lệ về nghiệp vụ.

## 13. Quy tắc thực hành

- Với một lớp cụ thể, truyền `User.class` hoặc kiểu tương ứng cho `readValue()`.
- Với collection hoặc wrapper generic, dùng `TypeReference<T>` có generic argument cụ thể.
- Khi target type được tạo từ thông tin runtime, dùng `JavaType` và `TypeFactory`.
- Khi viết generic helper, nhận `Class<T>`, `TypeReference<T>` hoặc `JavaType` từ caller; không tự tạo `TypeReference<T>` bên trong rồi mong Java giữ lại kiểu đã bị erasure.
- Không cast raw `List` thành `List<User>`; `instanceof List<?>` cũng không xác minh kiểu phần tử.
- Nếu phải nhận object động, kiểm tra bằng `Class.isInstance()`/`Class.cast()` hoặc duyệt từng phần tử trước khi dùng.
- Nếu JSON có nhiều shape đã biết, đọc `JsonNode`, kiểm tra discriminator và chọn kiểu đích từ allowlist.
- Không cho dữ liệu ngoài tùy ý chọn class Java để deserialize.

## 14. Kết luận

Ép kiểu không an toàn chỉ trì hoãn lỗi đến lúc runtime và thường che giấu việc Jackson đã tạo sai kiểu dữ liệu ngay từ đầu. Hãy mô tả target type đầy đủ khi deserialize: dùng `Class<T>` cho kiểu cụ thể, `TypeReference<T>` cho generic đã biết và `JavaType` cho kiểu được xây dựng động. Khi thật sự nhận một object chưa rõ kiểu, kiểm tra nó bằng API phản ánh kiểu của Java trước khi sử dụng. Cách làm này giúp compiler, Jackson và các kiểm tra runtime cùng bảo vệ ranh giới kiểu dữ liệu của ứng dụng.
