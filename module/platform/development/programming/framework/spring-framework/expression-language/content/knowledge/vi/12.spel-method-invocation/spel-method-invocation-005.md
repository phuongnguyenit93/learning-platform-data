# Method trên root object, property object và collection trong SpEL

## 1. Cách SpEL gọi method

Spring Expression Language (SpEL) cho phép gọi method Java trực tiếp trong biểu thức. Cú pháp gần giống Java:

```text
methodName(argument1, argument2)
object.methodName(argument1, argument2)
```

SpEL có thể gọi method trên:

- **Root object**: đối tượng gốc dùng để đánh giá biểu thức. Method có thể được gọi trực tiếp mà không cần tiền tố đối tượng.
- **Property object**: đối tượng được lấy từ một property hoặc từ chuỗi property lồng nhau. Dùng dấu chấm để truy cập object rồi gọi method trên object đó.
- **Collection hoặc array**: gọi method của chính collection/array, hoặc truy cập một phần tử rồi gọi method của phần tử. Để áp dụng một method lên từng phần tử, dùng collection projection hoặc selection.

Ví dụ gọi method trên string literal:

```java
ExpressionParser parser = new SpelExpressionParser();

String result = parser.parseExpression("'abc'.substring(1, 3)")
        .getValue(String.class);

// result = "bc"
```

Method invocation được phân giải khi expression được đánh giá. `ExpressionParser` phân tích cú pháp; `EvaluationContext` cung cấp root object, method resolver và các chiến lược cần thiết để tìm và gọi method.

## 2. Chuẩn bị root object và EvaluationContext

Một cách dùng phổ biến là phân tích expression một lần rồi đánh giá trên một object cụ thể. Ví dụ, giả sử có các lớp domain sau:

```java
public class Customer {
    private String name;
    private Address address;

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }

    public String displayName(String prefix) {
        return prefix + " " + name;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public String formatLabel() {
        return "City: " + city;
    }
}

public class Order {
    private Customer customer;
    private List<LineItem> items;

    public Customer getCustomer() {
        return customer;
    }

    public List<LineItem> getItems() {
        return items;
    }

    public boolean canShip(int minimumItems) {
        return items != null && items.size() >= minimumItems;
    }

    public String referenceLabel(String prefix) {
        return prefix + "-ORDER";
    }
}

public class LineItem {
    private String sku;
    private boolean available;

    public String getSku() {
        return sku;
    }

    public boolean isAvailable() {
        return available;
    }
}
```

Tạo parser và đặt Order làm root object:

```java
ExpressionParser parser = new SpelExpressionParser();

Order order = loadOrder();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
```

Khi expression được đánh giá với context này, tên property hoặc method không có tiền tố được phân giải trên root object. Ví dụ `canShip(2)` gọi method `canShip(int)` của Order.

Có thể truyền root object trực tiếp vào overload của `getValue()` thay vì đặt nó trong constructor của context:

```java
Expression expression = parser.parseExpression("canShip(2)");

Boolean canShip = expression.getValue(
        context, order, Boolean.class);
```

Hai cách đều giúp SpEL biết object cần đánh giá. Hãy chọn cách phù hợp với việc context có cần lưu thêm variables, functions hoặc resolver hay không.

## 3. Gọi method trên root object

Khi expression được đánh giá trên một root object, có thể gọi method của root trực tiếp bằng tên method và danh sách đối số:

```java
String label = parser.parseExpression(
        "referenceLabel('WEB')")
        .getValue(context, String.class);

// label = "WEB-ORDER"
```

Ví dụ gọi method trả về Boolean:

```java
Boolean canShip = parser.parseExpression("canShip(2)")
        .getValue(context, Boolean.class);
```

Ví dụ dùng method trong một điều kiện:

```java
String status = parser.parseExpression(
        "canShip(2) ? 'READY' : 'WAITING'")
        .getValue(context, String.class);
```

Trong các biểu thức trên, `referenceLabel` và `canShip` được gọi trên root object `order`. Không cần viết `#root` nếu method có thể được phân giải trực tiếp trên root.

Có thể viết rõ đối tượng gốc bằng biến hệ thống `#root`:

```text
#root.canShip(2)
```

`#root` luôn tham chiếu root context object ban đầu. Biến `#this` tham chiếu object hiện tại đang được đánh giá; trong biểu thức thông thường bên ngoài collection operation, `#this` thường trùng với root object.

## 4. Gọi method trên property object

Một property có thể trả về một object khác. Dùng dấu chấm để truy cập property, sau đó gọi method trên object được trả về.

Ví dụ gọi method của Customer thông qua property `customer` của Order:

```java
String displayName = parser.parseExpression(
        "customer.displayName('Customer:')")
        .getValue(context, String.class);

// Customer: Lan
```

Ví dụ gọi method trên object lồng sâu hơn:

```java
String addressLabel = parser.parseExpression(
        "customer.address.formatLabel()")
        .getValue(context, String.class);
```

SpEL lần lượt:

1. Đọc property `customer` trên root Order.
2. Đọc property `address` trên Customer.
3. Gọi `formatLabel()` trên Address.

Có thể gọi method trả về một object rồi tiếp tục truy cập property hoặc gọi method trên kết quả:

```text
customer.getAddress().getCity().toUpperCase()
```

Trong ví dụ này, SpEL gọi `getAddress()`, sau đó gọi `getCity()`, rồi gọi `toUpperCase()` trên String nhận được.

### 4.1. Property access và method invocation khác nhau

Hai cách sau có thể trả về cùng một giá trị:

```text
customer.name
customer.getName()
```

`customer.name` là property access. SpEL dùng cơ chế property accessor để đọc JavaBean property (thông thường thông qua getter). `customer.getName()` là method invocation, được phân giải bằng method resolver.

Nên dùng property syntax khi ý định là đọc dữ liệu. Dùng method syntax khi muốn gọi một hành vi có tên rõ ràng hoặc method nhận đối số. Không nhầm `name` với một lời gọi method không có ngoặc.

## 5. Gọi method trên collection

Collection cũng là object Java, vì vậy SpEL có thể gọi method được cung cấp bởi kiểu collection cụ thể. Với List, các method thông dụng gồm `size()`, `isEmpty()`, `get(index)` và `contains(value)`. Với Map, có thể gọi `size()`, `isEmpty()`, `containsKey(key)`, `containsValue(value)` và `get(key)`.

Ví dụ, gọi method trên property collection của Order:

```java
Integer itemCount = parser.parseExpression("items.size()")
        .getValue(context, Integer.class);

Boolean hasItems = parser.parseExpression("items.isEmpty()")
        .getValue(context, Boolean.class);
```

Ví dụ lấy phần tử rồi gọi method của phần tử:

```java
String firstSku = parser.parseExpression(
        "items.get(0).getSku()")
        .getValue(context, String.class);
```

Ví dụ collection là root object:

```java
List<String> names = List.of("An", "Binh", "Chi");

StandardEvaluationContext listContext =
        new StandardEvaluationContext(names);

Integer count = parser.parseExpression("size()")
        .getValue(listContext, Integer.class);

String firstName = parser.parseExpression("get(0).toUpperCase()")
        .getValue(listContext, String.class);
```

Nếu root object là List, `size()` và `get(0)` được gọi trực tiếp trên list đó. Nếu root object là Map, có thể gọi method map trực tiếp:

```java
Map<String, Object> settings = Map.of(
        "region", "ap-southeast-1",
        "enabled", true);

StandardEvaluationContext mapContext =
        new StandardEvaluationContext(settings);

Boolean hasRegion = parser.parseExpression(
        "containsKey('region')")
        .getValue(mapContext, Boolean.class);

String region = parser.parseExpression(
        "get('region')")
        .getValue(mapContext, String.class);
```

Cũng có thể truy cập map bằng index syntax như `settings['region']`. Method `get('region')` là lời gọi method Java; `settings['region']` là phép truy cập theo key. Chọn cú pháp giúp ý định rõ ràng nhất.

## 6. Gọi method trên từng phần tử collection

Gọi `items.size()` chỉ gọi một method trên collection. Nó không tự gọi một method trên mọi phần tử. Để lọc collection theo method của từng phần tử hoặc biến đổi từng phần tử bằng method, dùng collection selection và projection.

### 6.1. Selection: lọc phần tử theo điều kiện

Selection dùng cú pháp `?[selectionExpression]`. SpEL đánh giá điều kiện trên từng phần tử và trả về collection mới chứa các phần tử phù hợp.

Ví dụ chỉ lấy các LineItem đang available:

```java
List<?> availableItems = parser.parseExpression(
        "items.?[#this.isAvailable()]")
        .getValue(context, List.class);
```

Trong selection, `#this` đại diện phần tử hiện tại. Có thể gọi method trực tiếp trên nó:

```text
items.?[isAvailable()]
```

Hoặc dùng cú pháp tường minh:

```text
items.?[#this.isAvailable()]
```

Dạng có `#this` thường dễ đọc hơn khi biểu thức có nhiều tham chiếu lồng nhau.

### 6.2. Projection: gọi method để tạo collection kết quả

Projection dùng cú pháp `![projectionExpression]`. SpEL đánh giá biểu thức con cho từng phần tử và trả về một collection mới chứa các kết quả.

Ví dụ lấy SKU và chuyển thành chữ hoa:

```java
List<?> skus = parser.parseExpression(
        "items.![#this.getSku().toUpperCase()]")
        .getValue(context, List.class);
```

Mỗi phần tử của kết quả là chuỗi SKU đã được chuyển thành chữ hoa; kết quả không còn là danh sách LineItem.

### 6.3. Kết hợp selection và projection

Có thể lọc trước rồi chiếu kết quả sau:

```java
List<?> availableSkus = parser.parseExpression(
        "items.?[#this.isAvailable()].![#this.getSku().toUpperCase()]")
        .getValue(context, List.class);
```

Quá trình thực hiện:

1. `items.?[#this.isAvailable()]` giữ lại các item có `isAvailable()` trả về true.
2. `![#this.getSku().toUpperCase()]` gọi `getSku()` trên từng item còn lại, sau đó gọi `toUpperCase()` trên SKU.
3. Kết quả là List các chuỗi SKU đã chuẩn hóa.

Selection và projection là cú pháp riêng của SpEL. Chúng không phải là lời gọi một method như `stream().filter(...).map(...)` trong Java, dù có thể giải quyết các nhu cầu tương tự.

### 6.4. Selection và projection trên Map

Khi selection hoặc projection áp dụng lên Map, expression con được đánh giá trên từng entry kiểu `Map.Entry`. Có thể truy cập property `key` và `value`.

Ví dụ lọc các entry có value nhỏ hơn 100:

```text
settings.?[value < 100]
```

Projection tạo list các key:

```text
settings.![key]
```

Projection tạo list các value:

```text
settings.![value]
```

Cần phân biệt collection gốc với collection kết quả. Selection trả về các phần tử hoặc entry được chọn; projection trả về các giá trị được tính từ từng phần tử hoặc entry.

## 7. Method arguments, overload và varargs

SpEL hỗ trợ method có đối số. Đối số có thể là literal, variable, property, phép tính hoặc expression khác:

```java
context.setVariable("prefix", "ORDER");

String label = parser.parseExpression(
        "referenceLabel(#prefix)")
        .getValue(context, order, String.class);
```

SpEL dùng method resolver trong EvaluationContext để tìm method phù hợp với tên và các đối số. Với `StandardEvaluationContext`, method resolver mặc định dựa trên reflection. Type conversion có thể được áp dụng khi đối số có kiểu tương thích thông qua ConversionService.

Nếu class có nhiều method cùng tên (overload), kiểu và số lượng đối số ảnh hưởng đến method được chọn. Ví dụ:

```java
public String format(String value) {
    return "text:" + value;
}

public String format(Integer value) {
    return "number:" + value;
}
```

Các biểu thức `format('12')` và `format(12)` cung cấp đối số có kiểu khác nhau. Khi overload phức tạp hoặc có nhiều converter, hãy kiểm tra rõ kiểu runtime của biến và chọn chữ ký method không gây mơ hồ.

SpEL cũng hỗ trợ varargs:

```java
public String joinLabels(String... labels) {
    return String.join(", ", labels);
}
```

Có thể truyền từng đối số:

```text
joinLabels('NEW', 'PAID', 'SHIPPED')
```

Hoặc truyền một array/inline list làm danh sách đối số biến thiên theo cú pháp mà method yêu cầu. SpEL có thể chuyển đổi từng đối số cho kiểu phần tử varargs nếu converter phù hợp được cấu hình.

## 8. Method invocation với null và safe navigation

Nếu object nhận lời gọi method là null, lời gọi thông thường có thể phát sinh lỗi đánh giá:

```text
customer.getName()
```

Khi `customer` có thể null, dùng safe navigation:

```text
customer?.getName()
```

Nếu customer null, phần gọi method an toàn trả về null thay vì cố gọi method trên null. Với chuỗi truy cập có nhiều đoạn có thể null, hãy áp dụng safe navigation tại từng đoạn có thể null:

```text
customer?.getAddress()?.formatLabel()
```

Safe navigation chỉ xử lý object ngay trước toán tử `?.`. Nếu method trả về null rồi expression tiếp tục gọi method khác bằng dấu chấm thông thường, phần tiếp theo vẫn có thể lỗi.

Trong collection projection, một phần tử có thể null. Có thể dùng safe navigation cho phần tử hiện tại:

```text
items.![#this?.getSku()]
```

Nếu method trả về null, projection có thể giữ giá trị null tương ứng trong collection kết quả. Nếu cần bỏ các phần tử null, hãy selection trước để lọc chúng.

## 9. MethodResolver và EvaluationContext

`EvaluationContext` tham gia giải quyết method invocation. Với `StandardEvaluationContext`, SpEL cung cấp `ReflectiveMethodResolver` để tìm method Java bằng reflection. Context cũng có thể được cấu hình với method resolver tùy chỉnh nếu ứng dụng cần quy tắc gọi method riêng.

Các API thường gặp:

| API | Vai trò |
|---|---|
| `addMethodResolver(resolver)` | Bổ sung resolver vào danh sách hiện có. |
| `setMethodResolvers(resolvers)` | Thay toàn bộ danh sách resolver. |
| `getMethodResolvers()` | Đọc danh sách resolver hiện tại. |
| `registerMethodFilter(type, filter)` | Đăng ký bộ lọc method cho reflective method resolver. |

Khi thay toàn bộ danh sách bằng `setMethodResolvers()`, hãy chắc chắn danh sách mới vẫn chứa resolver cần thiết. Nếu chỉ muốn thêm khả năng mới, `addMethodResolver()` thường phù hợp hơn.

`SimpleEvaluationContext` được thiết kế cho tập tính năng giới hạn và yêu cầu chọn rõ mức hỗ trợ method invocation khi tạo context. Không giả định mọi context đều cho phép gọi method giống nhau.

## 10. Bảo mật khi biểu thức có thể gọi method

Method invocation có thể làm lộ hành vi của object cho expression. Một method có thể đọc dữ liệu, thay đổi trạng thái, truy cập hệ thống bên ngoài hoặc thực hiện thao tác tốn kém. Vì vậy:

- Chỉ đánh giá biểu thức SpEL từ nguồn tin cậy.
- Không dùng `StandardEvaluationContext` để đánh giá expression do người dùng hoặc hệ thống bên ngoài không tin cậy cung cấp.
- Dùng DTO hoặc kiểu chuyên biệt chỉ phơi bày các method cần thiết.
- Tránh đưa entity hoặc infrastructure object có nhiều method nhạy cảm làm root object.
- Kiểm tra các object được trả về từ property, method và phần tử collection; chúng cũng có thể tiếp tục được truy cập từ expression.
- Tránh method có side effect trong biểu thức lọc hoặc projection nếu việc gọi method nhiều lần có thể gây thay đổi ngoài ý muốn.

Việc hạn chế root object không đủ nếu root object trả về một object con có nhiều hành vi nhạy cảm. Quy tắc thiết kế phải áp dụng xuyên suốt object graph mà expression có thể truy cập.

## 11. Ví dụ tổng hợp: root, nested object và collection

Ví dụ sau minh họa ba vị trí gọi method trong cùng một expression:

```java
// Root Order, Customer lồng bên trong và List<LineItem>.
Expression expression = parser.parseExpression(
        "canShip(1) ? " +
        "customer.displayName('For:').toUpperCase() + " +
        "': ' + items.?[#this.isAvailable()].![#this.getSku()] " +
        ": 'WAITING'");

String summary = expression.getValue(
        context, order, String.class);
```

- `canShip(1)` gọi method trên root Order.
- `customer.displayName('For:')` gọi method trên object lấy từ property `customer`.
- `items.?[...]` gọi `isAvailable()` trên từng phần tử LineItem.
- `items.![...]` gọi `getSku()` trên từng phần tử được giữ lại.

Nếu điều kiện `canShip(1)` false, nhánh tạo summary không được đánh giá. Nếu true, các method trong nhánh được chọn mới được thực thi. Ví dụ này cho thấy một expression có thể kết hợp method invocation, property navigation, selection, projection và ternary.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy method | Sai tên, sai số lượng đối số, method không khả dụng qua resolver hoặc object đích không đúng kiểu. | Kiểm tra object đích, chữ ký method và method resolver. |
| Gọi method trên root nhưng không có root object | Expression được đánh giá mà không truyền root/context phù hợp. | Dùng `new StandardEvaluationContext(root)` hoặc overload `getValue(context, root, type)`. |
| Method trên nested object bị lỗi | Property trung gian null hoặc không trả về kiểu mong đợi. | Kiểm tra từng property; dùng safe navigation ở đoạn có thể null. |
| Gọi `items.getName()` không hoạt động | Collection không có method đó; method thuộc về từng phần tử. | Dùng `items.get(0).getName()` hoặc projection `items.![getName()]`. |
| `items.size()` không phải số phần tử mong muốn | Property `items` không phải collection hoặc dữ liệu có thể null. | Kiểm tra kiểu runtime và trạng thái collection trước khi gọi. |
| Projection trả về kiểu khác collection gốc | Projection tạo collection mới từ kết quả expression con. | Kiểm tra kiểu của giá trị trong projection. |
| Selection không lọc đúng | Điều kiện selection không trả về Boolean như mong đợi. | Dùng biểu thức Boolean rõ ràng và kiểm tra method/property của từng phần tử. |
| Overload gọi nhầm method | Nhiều method cùng tên và kiểu đối số có thể chuyển đổi. | Dùng đối số có kiểu rõ ràng hoặc thiết kế chữ ký ít mơ hồ. |
| Varargs không nhận đúng đối số | Cách truyền array/list hoặc kiểu phần tử không phù hợp. | Kiểm tra chữ ký varargs và converter cho từng đối số. |
| Lỗi gọi method trên null | Object nhận lời gọi null. | Dùng safe navigation `?.` hoặc kiểm tra null trước. |
| Method bị gọi nhiều lần trong projection | Projection chạy expression con cho từng phần tử. | Giữ method thuần (không side effect) hoặc chuyển xử lý sang Java. |
| Expression gọi được method ngoài dự kiến | Root/nested object phơi bày quá nhiều hành vi. | Thu hẹp object model và chỉ đánh giá expression tin cậy. |

## 13. Quy trình kiểm thử method invocation

1. Xác định object nhận lời gọi: root object, nested property object, collection hay phần tử collection.
2. Xác nhận kiểu runtime của object đó và method có thể được truy cập.
3. Kiểm tra tên method, số lượng đối số, kiểu đối số và trường hợp overload/varargs.
4. Kiểm thử method trực tiếp bằng một expression đơn giản trước khi ghép vào expression dài.
5. Với nested object, kiểm tra từng đoạn property và trường hợp null.
6. Với collection, kiểm tra collection rỗng, một phần tử, nhiều phần tử và phần tử null nếu có thể.
7. Với selection/projection, kiểm tra từng phần tử và kết quả của expression con.
8. Kiểm tra method có side effect hay không; không giả định expression chỉ được đánh giá một lần.
9. Dùng cùng EvaluationContext và root object như môi trường ứng dụng để xác nhận kết quả cuối.

## 14. Ghi nhớ

- Gọi method theo cú pháp Java: `method(args)` trên root hoặc `object.method(args)` trên object cụ thể.
- Root method có thể gọi không cần tiền tố; dùng `#root` nếu muốn chỉ rõ root context object.
- Property navigation có thể đi qua nhiều object: `customer.address.formatLabel()`.
- `object.name` là property access; `object.getName()` là method invocation.
- Collection có method riêng như `size()`, `get()`, `contains()`; method của phần tử cần truy cập phần tử hoặc dùng selection/projection.
- Selection `.?[...]` lọc; projection `.![...]` tạo collection từ kết quả trên từng phần tử.
- Method arguments có thể là expression; overload và varargs được hỗ trợ.
- Safe navigation `?.` giúp tránh gọi method trên object null.
- `EvaluationContext` và method resolver quyết định những method nào được phân giải.
- Không đánh giá expression không tin cậy trên object graph có thể gọi các hành vi nhạy cảm.

## Tài liệu tham khảo

- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Varargs Invocations](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/varargs.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — EvaluationContext and Security](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
