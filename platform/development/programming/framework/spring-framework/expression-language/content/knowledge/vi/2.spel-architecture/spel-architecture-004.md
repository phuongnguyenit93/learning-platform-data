# Root object, active context object và biến trong SpEL

## Mục tiêu

Khi SpEL đánh giá một biểu thức, nó cần biết biểu thức đang bắt đầu từ đối tượng nào, đối tượng nào đang được xử lý ở vị trí hiện tại và các giá trị bên ngoài nào được truyền vào. Ba khái niệm này tương ứng với root object, active object và expression variables.

Điểm cần nhớ: `EvaluationContext` là nơi cung cấp các thông tin và cơ chế cần cho việc đánh giá; bản thân nó không phải root object. Trong biểu thức, `#root` trỏ đến đối tượng gốc, `#this` trỏ đến đối tượng đang được xử lý, còn `#tenBien` truy cập một biến đã đăng ký trong context.

## 1. Ba nguồn dữ liệu trong một biểu thức

| Thành phần | Cú pháp | Ý nghĩa |
| --- | --- | --- |
| Root object | `#root` | Đối tượng gốc mà lần đánh giá bắt đầu từ đó. Giá trị này giữ nguyên trong suốt lần đánh giá. |
| Active object | `#this` | Đối tượng hiện đang được biểu thức xử lý. Ở cấp cao nhất, nó thường trùng với root object; trong selection hoặc projection, nó chuyển sang từng phần tử. |
| Expression variable | `#minPrice` | Giá trị được ứng dụng đưa vào `EvaluationContext` bằng tên biến. |
| Property của object hiện tại | `price` | Property được phân giải trên active object hiện tại. |

Vì vậy, `price` và `#price` có thể mang ý nghĩa khác nhau: `price` tìm property trên object đang hoạt động, còn `#price` tìm biến tên `price` trong evaluation context.

## 2. Root object: đối tượng gốc của lần đánh giá

Root object là điểm bắt đầu để SpEL phân giải property, method và các phép truy cập khác. Có thể đặt root object khi tạo `StandardEvaluationContext`:

```java
Order order = orderService.findById(42L);
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext(order);

String customerName = parser.parseExpression("customer.name")
        .getValue(context, String.class);

String explicitCustomerName = parser.parseExpression("#root.customer.name")
        .getValue(context, String.class);
```

Ở cấp cao nhất, `customer.name` được phân giải từ root object. Viết `#root.customer.name` cho kết quả tương ứng nhưng làm rõ rằng đường dẫn bắt đầu từ object gốc. Cách viết tường minh hữu ích khi biểu thức đi sâu vào một collection hoặc có nhiều cấp object.

Có thể tạo context trước rồi đặt root object bằng `setRootObject`:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setRootObject(order);
```

Ngoài ra, overload `getValue(context, rootObject)` cho phép cung cấp root object cho một lần đánh giá cụ thể:

```java
String id = parser.parseExpression("#root.id")
        .getValue(context, anotherOrder, String.class);
```

Trong lần gọi này, `anotherOrder` là root object được dùng để đánh giá biểu thức. Nếu không truyền root object ở lần gọi, SpEL sử dụng root object đã được đặt trong context.

## 3. Active object: đối tượng hiện tại qua `#this`

`#this` đại diện cho object mà SpEL đang xử lý tại vị trí hiện tại. Khi bắt đầu đánh giá, `#this` thường trùng với `#root`. Điểm khác biệt xuất hiện rõ trong các toán tử selection (`.?[]`) và projection (`.![]`) trên collection.

- Selection lọc các phần tử thỏa điều kiện.
- Projection biến mỗi phần tử thành một giá trị hoặc object kết quả.
- Trong phần điều kiện hoặc biểu thức của từng phần tử, `#this` trỏ đến phần tử đang được xử lý.
- `#root` vẫn trỏ đến object gốc ban đầu.

Giả sử root object là một `Order` có property `items`, và mỗi phần tử là một `LineItem`:

```spel
items.?[price >= 100]
```

Trong điều kiện trên, `price` được tìm trên từng `LineItem` đang xét. Có thể viết tường minh bằng `#this`:

```spel
items.?[#this.price >= 100]
```

Nếu cần so sánh với một property của `Order`, hãy dùng `#root`:

```spel
items.?[#this.price >= #root.minimumPrice]
```

Ở đây `#this.price` là giá của dòng hàng hiện tại, còn `#root.minimumPrice` là ngưỡng giá trên đơn hàng gốc. Khi chuyển sang projection, `#this` tiếp tục đại diện cho từng phần tử:

```spel
items.![#this.productName]
```

Biểu thức trên trả về danh sách tên sản phẩm. Trong các selection hoặc projection lồng nhau, hãy hiểu `#this` theo phạm vi đang hoạt động tại vị trí biểu thức được đánh giá; `#root` vẫn là điểm gốc của toàn bộ lần đánh giá.

## 4. Expression variables: truyền dữ liệu vào bằng `#tenBien`

Ứng dụng có thể truyền tham số vào biểu thức thông qua `EvaluationContext`. Với `StandardEvaluationContext`, dùng `setVariable` để đăng ký biến:

```java
context.setVariable("minPrice", new BigDecimal("100.00"));
```

Trong SpEL, tham chiếu biến bằng dấu `#`:

```spel
items.?[#this.price >= #minPrice].![#this.productName]
```

Ví dụ hoàn chỉnh:

```java
Order order = orderService.findById(42L);
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("minPrice", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "items.?[#this.price >= #minPrice].![#this.productName]");
List<?> productNames = expression.getValue(context, List.class);
```

Trong ví dụ này:

- `order` là root object.
- `#this` lần lượt là từng `LineItem` khi selection và projection chạy.
- `#minPrice` là giá trị do ứng dụng truyền vào context.
- Kết quả là danh sách `productName` của các dòng hàng có giá ít nhất bằng ngưỡng được truyền vào.

Tên truyền cho `setVariable` không có dấu `#`; dấu `#` chỉ xuất hiện khi tham chiếu biến trong biểu thức. Có thể đọc lại giá trị đã đăng ký bằng `lookupVariable`:

```java
Object minPrice = context.lookupVariable("minPrice");
```

Biến có thể chứa object, chuỗi, số, ngày tháng hoặc giá trị khác mà biểu thức cần dùng. Nếu tên biến trùng với property của object, hãy phân biệt rõ: `price` truy cập property trên active object, còn `#price` truy cập biến trong context.

## 5. Phân biệt biến, function và Spring bean

Các cú pháp có dấu `#` không phải lúc nào cũng chỉ đến một biến thông thường:

- `#minPrice`: biến được đăng ký bằng `setVariable("minPrice", value)`.
- `#root` và `#this`: các biến đặc biệt do SpEL cung cấp cho root object và active object.
- `#calculateTax(...)`: lời gọi function được đăng ký trong evaluation context, ví dụ bằng `registerFunction`.
- `@pricingService`: tham chiếu đến Spring bean khi context có `BeanResolver` phù hợp. Đây là cơ chế bean reference, không phải expression variable.

Khi đọc một biểu thức, hãy kiểm tra cách tên được đăng ký trong context thay vì suy luận rằng mọi tên đều là property của root object.

## 6. Chọn EvaluationContext phù hợp

`StandardEvaluationContext` cung cấp nhiều khả năng phân giải property, method, type, constructor, bean và function. Nó phù hợp khi ứng dụng cần các tính năng SpEL đầy đủ và kiểm soát rõ những khả năng được bật.

`SimpleEvaluationContext` được thiết kế cho các tình huống data binding cần giới hạn tính năng. Có thể cấu hình property accessor và mức hỗ trợ method invocation cần thiết; context này loại bỏ một số khả năng mạnh như type reference, constructor và bean reference.

Nếu biểu thức đến từ người dùng hoặc nguồn không đáng tin cậy, hãy giới hạn các property accessor và method resolver được phép sử dụng. Tránh đánh giá biểu thức không tin cậy với một `StandardEvaluationContext` có đầy đủ quyền truy cập. Với dữ liệu đầu vào, nên truyền giá trị qua biến của context thay vì nối chuỗi trực tiếp vào nội dung biểu thức. Chỉ đưa vào context những dữ liệu mà biểu thức được phép đọc.

Khi đánh giá cho nhiều người dùng hoặc nhiều request, cần quản lý vòng đời context và các biến theo đúng phạm vi. Không để giá trị biến của request trước vô tình được dùng trong request sau.

## 7. Cách đọc và xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `price` đọc sai object bên trong `.?[]` | `#this` đã chuyển sang phần tử collection hiện tại. | Dùng `#this.price` cho phần tử hoặc `#root.price` cho object gốc. |
| `#minPrice` không có giá trị mong đợi | Biến chưa được đăng ký, sai tên hoặc context đang dùng không phải context đã được cấu hình. | Gọi `setVariable` trước `getValue` và kiểm tra tên biến. |
| Property trùng tên với biến gây khó hiểu | `name` và `#name` được phân giải theo hai cơ chế khác nhau. | Dùng dấu `#` rõ ràng khi muốn lấy biến. |
| Kết quả selection hoặc projection khác dự kiến | Biểu thức đang chạy trong phạm vi active object của phần tử collection. | Xác định object hiện tại tại từng bước; dùng `#root` khi cần quay về object gốc. |
| So sánh số không như mong đợi | Hai giá trị có kiểu số hoặc quy tắc chuyển đổi khác nhau. | Truyền giá trị có kiểu phù hợp, ví dụ dùng `BigDecimal` cho dữ liệu tiền tệ. |

## Ghi nhớ

- `#root` là object gốc của lần đánh giá và giữ nguyên trong các selection/projection.
- `#this` là object đang được xử lý; nó thường bằng root object ở cấp cao nhất và chuyển sang từng phần tử trong selection/projection.
- `#tenBien` là giá trị được ứng dụng đăng ký trong `EvaluationContext`.
- Property không có `#` được phân giải trên active object hiện tại.
- `EvaluationContext` chứa root object, biến và các cơ chế phân giải; nó không đồng nghĩa với root object.