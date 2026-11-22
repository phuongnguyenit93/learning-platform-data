# Ảnh hưởng của xóa kiểu khi đọc List và Map

Khi đọc một JSON object đơn lẻ, ta thường truyền `Order.class` cho Jackson để chỉ rõ kiểu Java cần tạo. Nhưng khi dữ liệu là `List<Order>` hoặc `Map<String, Order>`, việc truyền `List.class` hay `Map.class` lại không cung cấp đủ thông tin về kiểu phần tử hoặc kiểu value.

Nguyên nhân nằm ở **type erasure** (xóa kiểu) của Java Generics. Thông tin tham số generic như `Order` trong `List<Order>` chủ yếu phục vụ kiểm tra kiểu lúc biên dịch; tại runtime, đối tượng collection thông thường không mang theo thông tin đầy đủ rằng nó là `List<Order>` hay `List<Customer>`. Jackson cần được cung cấp kiểu generic đích bằng một cách khác để ánh xạ chính xác dữ liệu.

Bài học này giải thích vì sao đọc `List` và `Map` bằng raw class có thể tạo ra các cấu trúc `Map`/`List` lồng nhau thay vì DTO, cách dùng `TypeReference` và `JavaType`, cùng những tình huống nên chọn từng cách.

## 1. Type erasure ảnh hưởng thế nào đến Java Generics?

Trong mã nguồn, ta có thể khai báo:

```java
List<Order> orders;
Map<String, Order> ordersById;
```

Trình biên dịch biết `orders` là danh sách `Order` và `ordersById` là map có key `String`, value `Order`. Nhờ đó, code có thể gọi `orders.get(0).getAmount()` mà không cần cast thủ công.

Tuy nhiên, Java sử dụng type erasure. Ở runtime, generic type argument không được giữ trực tiếp trên instance collection. Một đối tượng `ArrayList` không tự lưu thông tin để phân biệt nó được tạo từ `List<Order>`, `List<Customer>` hay `List<String>`. Tương tự, `HashMap` không tự cho biết kiểu key/value đã dùng lúc khai báo.

Vì vậy, `List.class` chỉ đại diện cho kiểu raw `List`; `Map.class` chỉ đại diện cho raw `Map`. Chúng không thể diễn đạt:

```text
List.class  ≠  List<Order>
Map.class   ≠  Map<String, Order>
```

Khi gọi API nhận `Class<T>`, bạn chỉ truyền được một `Class` token như `Order.class`, `List.class` hoặc `Map.class`. Java không cho viết `List<Order>.class` vì kiểu tham số generic không phải một class token có thể lấy theo cách đó.

## 2. Đọc JSON array bằng List.class

Giả sử JSON đầu vào chứa danh sách đơn hàng:

```json
[
  {
    "id": "DH-1001",
    "amount": 129.50
  },
  {
    "id": "DH-1002",
    "amount": 250.00
  }
]
```

Mô hình Java:

```java
import java.math.BigDecimal;

public record Order(String id, BigDecimal amount) {}
```

Nếu đọc bằng raw class:

```java
ObjectMapper mapper = new ObjectMapper();

List<?> values = mapper.readValue(json, List.class);

Object first = values.get(0);
System.out.println(first.getClass());
```

Jackson biết cần tạo một `List`, nhưng không biết phần tử phải là `Order`. Với JSON object không có kiểu đích cụ thể, Databind thường tạo cấu trúc Java tự nhiên, chẳng hạn `LinkedHashMap` cho object, `ArrayList` cho array, `String`, `Boolean` và các kiểu `Number` cho giá trị nguyên thủy.

Do đó, phần tử đầu tiên trong ví dụ thường là `LinkedHashMap`, có các cặp key/value như `id` và `amount`, chứ không phải `Order`.

### 2.1. Vì sao lỗi có thể xuất hiện muộn?

Đoạn code sau có thể biên dịch với cảnh báo unchecked conversion/cast tùy cách viết:

```java
@SuppressWarnings("unchecked")
List<Order> orders = (List<Order>) mapper.readValue(json, List.class);

Order first = orders.get(0); // Có thể ném ClassCastException
```

Cast ở đây chỉ ép kiểu tham chiếu collection tại runtime. Nó không duyệt các phần tử để biến `LinkedHashMap` thành `Order`. Khi lấy phần tử và gán vào biến `Order`, JVM thực hiện cast phần tử thực tế; nếu phần tử vẫn là `LinkedHashMap`, code có thể ném `ClassCastException`.

Đây là lý do không nên dùng unchecked cast để khắc phục việc thiếu generic type khi deserialize. Cần truyền cho Jackson đầy đủ kiểu đích ngay từ đầu.

## 3. Đọc JSON object bằng Map.class

Vấn đề tương tự xảy ra với `Map`.

JSON:

```json
{
  "DH-1001": {
    "id": "DH-1001",
    "amount": 129.50
  },
  "DH-1002": {
    "id": "DH-1002",
    "amount": 250.00
  }
}
```

Mục tiêu của ứng dụng là:

```java
Map<String, Order> ordersById;
```

Nhưng nếu đọc như sau:

```java
Map<?, ?> values = mapper.readValue(json, Map.class);
Object firstValue = values.values().iterator().next();

System.out.println(firstValue.getClass());
```

Jackson chỉ biết kết quả ngoài cùng là một `Map`. Vì không có thông tin rằng value là `Order`, mỗi JSON object lồng bên trong thường được biểu diễn thành `LinkedHashMap`. Map ngoài thường là `LinkedHashMap`, key là tên trường JSON và value là kiểu Java tự nhiên tương ứng.

Nếu ép kiểu toàn bộ kết quả thành `Map<String, Order>`, các value không tự chuyển thành `Order`. Lỗi tương tự sẽ xuất hiện khi chương trình lấy một value và sử dụng nó như DTO.

## 4. Dùng TypeReference để giữ thông tin generic

Jackson cung cấp `TypeReference<T>` để truyền một kiểu generic đầy đủ vào API đọc dữ liệu. Cách dùng phổ biến là tạo anonymous subclass:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

ObjectMapper mapper = new ObjectMapper();

List<Order> orders = mapper.readValue(
        json,
        new TypeReference<List<Order>>() {}
);
```

`TypeReference` dựa vào generic type được khai báo trên anonymous subclass để giữ metadata về `List<Order>`. Jackson có thể đọc metadata này và xây dựng mô tả kiểu nội bộ tương ứng. Vì thế, khi gặp mỗi JSON object trong array, Databind biết cần tạo một `Order`.

Với `Map<String, Order>`, cách làm tương tự:

```java
Map<String, Order> ordersById = mapper.readValue(
        json,
        new TypeReference<Map<String, Order>>() {}
);
```

Jackson biết key có kiểu `String` và value có kiểu `Order`. Mỗi JSON object làm value sẽ được ánh xạ thành `Order` thay vì `LinkedHashMap` không định kiểu.

### 4.1. Generic lồng nhau

`TypeReference` cũng mô tả được cấu trúc nhiều tầng, ví dụ:

```java
Map<String, List<Order>> ordersByCustomer = mapper.readValue(
        json,
        new TypeReference<Map<String, List<Order>>>() {}
);
```

Trong trường hợp này, Jackson cần biết cả ba phần:

- Kiểu key của map là `String`.
- Kiểu value của map là `List<Order>`.
- Kiểu phần tử trong list là `Order`.

Nếu chỉ truyền `Map.class`, cả thông tin kiểu value lẫn kiểu phần tử bên trong list đều bị thiếu. Khi đó, các tầng object/array lồng nhau thường trở thành `Map`/`List` chứa các kiểu Java tự nhiên.

## 5. Dùng JavaType khi kiểu được xây dựng động

`TypeReference` rất tiện khi kiểu generic đã biết ngay trong mã nguồn. Trong một số ứng dụng, kiểu đích được quyết định lúc runtime, chẳng hạn một hàm dùng chung nhận class phần tử từ tham số hoặc cấu trúc generic được lắp ghép theo cấu hình. Khi đó, Jackson cung cấp `JavaType` và `TypeFactory`.

Ví dụ, tạo kiểu `List<Order>` từ các thành phần kiểu:

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

ObjectMapper mapper = new ObjectMapper();

JavaType orderType = mapper.getTypeFactory().constructType(Order.class);
JavaType orderListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, orderType);

List<Order> orders = mapper.readValue(json, orderListType);
```

Để tạo `Map<String, List<Order>>`, có thể ghép các kiểu thành phần:

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.type.TypeFactory;

TypeFactory typeFactory = mapper.getTypeFactory();

JavaType stringType = typeFactory.constructType(String.class);
JavaType orderType = typeFactory.constructType(Order.class);
JavaType orderListType = typeFactory.constructCollectionType(List.class, orderType);
JavaType resultType = typeFactory.constructMapType(
        Map.class,
        stringType,
        orderListType
);

Map<String, List<Order>> result = mapper.readValue(json, resultType);
```

`JavaType` là mô tả kiểu mà Jackson hiểu được, bao gồm thông tin generic. Nó hữu ích khi ứng dụng phải lắp ghép kiểu đích từ nhiều tham số runtime mà không thể viết một `TypeReference` cố định.

### 5.1. Viết hàm generic dùng chung

Một hàm nhận `Class<T>` chỉ đủ cho kiểu không có tham số generic hoặc khi không cần thông tin generic bên trong:

```java
public <T> T read(String json, Class<T> targetType) throws IOException {
    return mapper.readValue(json, targetType);
}
```

Nếu muốn hàm dùng chung hỗ trợ cả `List<Order>` hoặc `Map<String, Order>`, hãy nhận `TypeReference<T>` hoặc `JavaType`:

```java
public <T> T read(String json, TypeReference<T> targetType) throws IOException {
    return mapper.readValue(json, targetType);
}
```

Khi gọi:

```java
List<Order> orders = read(json, new TypeReference<List<Order>>() {});
```

generic type được giữ trong `TypeReference` để Jackson sử dụng. Không nên cố tạo `List<T>.class`, vì Java không cung cấp class literal cho kiểu generic đã tham số hóa.

## 6. Khi nào type erasure không gây vấn đề?

Type erasure không có nghĩa Jackson luôn mất mọi thông tin generic. Khi kiểu generic được khai báo trong chữ ký thành phần của một class, Java thường giữ metadata generic trong thông tin phản chiếu.

Ví dụ:

```java
public class OrderBatch {
    private List<Order> orders;

    public List<Order> getOrders() {
        return orders;
    }

    public void setOrders(List<Order> orders) {
        this.orders = orders;
    }
}
```

Khi deserialize thành `OrderBatch.class`, Jackson introspection có thể đọc thông tin khai báo `List<Order>` của property `orders` và ánh xạ các phần tử thành `Order`. Bạn không phải truyền riêng `TypeReference<List<Order>>` cho property đó.

Điểm khác biệt nằm ở cách gọi API:

- Đọc thành `OrderBatch.class`: Jackson có thể introspect chữ ký generic của property `orders`.
- Đọc trực tiếp thành `List.class`: class token không chứa thông tin `Order`.

Tương tự, nếu method nhận tham số `List<Order>` và framework có metadata generic của method parameter, framework có thể chuyển kiểu đó cho converter. Nhưng khi code tự gọi `readValue(json, List.class)`, thông tin generic không còn trong đối số kiểu mà bạn đã truyền.

## 7. Kiểu dữ liệu không định kiểu và khi nào dùng chúng?

Không phải lúc nào việc nhận `List<Map<String, Object>>` cũng là sai. Đôi khi ứng dụng thực sự cần đọc JSON linh hoạt, chưa biết trước cấu trúc hoặc muốn xử lý dữ liệu theo tên trường.

Ví dụ:

```java
Map<String, Object> payload = mapper.readValue(
        json,
        new TypeReference<Map<String, Object>>() {}
);

Object eventType = payload.get("eventType");
Object data = payload.get("data");
```

Trong trường hợp này, kiểu `Object` là lựa chọn có chủ đích. JSON object lồng nhau có thể thành `Map`, array thành `List`, còn các giá trị đơn giản thành kiểu Java tương ứng. Ứng dụng phải kiểm tra kiểu thực tế trước khi cast hoặc truy cập sâu.

Nếu muốn truy cập cây JSON có API rõ ràng hơn, hãy cân nhắc `JsonNode`:

```java
JsonNode root = mapper.readTree(json);
String eventType = root.path("eventType").asText();
JsonNode data = root.path("data");
```

Tree model giữ cấu trúc JSON dưới dạng node và cho phép kiểm tra object, array, giá trị thiếu hoặc null mà không cần định nghĩa DTO trước. Khi hợp đồng đã rõ ràng, ánh xạ vào DTO có kiểu cụ thể thường giúp code dễ kiểm soát hơn.

## 8. Map có cả kiểu key và value

Với `Map<K, V>`, cần cung cấp cả kiểu key lẫn kiểu value nếu chúng không phải kiểu tự nhiên mà Jackson có thể suy ra. JSON object biểu diễn tên trường bằng chuỗi, nhưng Jackson có thể chuyển chuỗi đó thành kiểu key đích thông qua key deserializer phù hợp.

Ví dụ map dùng enum làm key:

```java
enum Region {
    NORTH,
    SOUTH
}

Map<Region, Order> ordersByRegion = mapper.readValue(
        json,
        new TypeReference<Map<Region, Order>>() {}
);
```

JSON cần có tên property tương ứng với giá trị enum mà Jackson có thể chuyển đổi, ví dụ `NORTH` hoặc `SOUTH`. Nếu tên key không hợp lệ, quá trình chuyển key có thể thất bại. Vì vậy, generic type của map quan trọng cả với key, không chỉ value.

## 9. Những lỗi thường gặp khi đọc collection và map

### 9.1. Dùng raw class rồi cast

```java
List<Order> orders = (List<Order>) mapper.readValue(json, List.class);
```

Cast không biến các `LinkedHashMap` thành `Order`. Hãy dùng `TypeReference<List<Order>>` hoặc `JavaType`.

### 9.2. Chỉ khai báo kiểu phần tử mà bỏ qua generic lồng nhau

Với `Map<String, List<Order>>`, cung cấp `Map.class` vẫn thiếu cả kiểu list lẫn kiểu `Order`. Hãy mô tả đầy đủ toàn bộ cấu trúc generic.

### 9.3. Dùng Object khi thực ra cần DTO

`Map<String, Object>` tiện cho payload động, nhưng code phải tự kiểm tra kiểu ở runtime. Nếu cấu trúc ổn định, hãy dùng DTO hoặc `TypeReference` để Jackson thực hiện ánh xạ có kiểu.

### 9.4. Nhầm lỗi kiểu với lỗi dữ liệu

Nếu đã truyền đúng generic type nhưng một trường có giá trị không tương thích, Jackson vẫn có thể ném lỗi chuyển đổi. `TypeReference` giải quyết việc thiếu thông tin kiểu đích, không làm cho dữ liệu sai trở nên hợp lệ. Validation nghiệp vụ vẫn cần được thực hiện sau khi deserialize.

## 10. Quy tắc lựa chọn

| Tình huống | Kiểu đích nên dùng |
| --- | --- |
| Một object cụ thể như `Order` | `Order.class` |
| Một array Java như `Order[]` | `Order[].class` |
| `List<Order>` hoặc `Set<Order>` | `TypeReference<List<Order>>` hoặc `JavaType` |
| `Map<String, Order>` | `TypeReference<Map<String, Order>>` hoặc `JavaType` |
| Generic lồng nhau như `Map<String, List<Order>>` | `TypeReference` đầy đủ hoặc ghép `JavaType` |
| Kiểu generic nằm trong property của DTO đã khai báo | Đọc DTO bằng class/record đích; Databind có thể introspect generic signature của property |
| Payload thực sự động, chưa biết DTO | `Map<String, Object>` hoặc `JsonNode` |
| Hàm generic cần nhận kiểu từ runtime | `TypeReference<T>` hoặc `JavaType` |

Khi đọc `List` và `Map`, hãy nhớ rằng collection runtime không giữ generic argument của instance. `List.class` chỉ cho Jackson biết kiểu container; `Map.class` chỉ cho biết kết quả ngoài cùng là map. Muốn các phần tử hoặc value trở thành DTO cụ thể, hãy truyền đầy đủ kiểu generic bằng `TypeReference` hoặc `JavaType`. Đây là cách tránh dữ liệu bị ánh xạ thành cấu trúc động và tránh các lỗi cast xuất hiện muộn khi chương trình sử dụng phần tử.
