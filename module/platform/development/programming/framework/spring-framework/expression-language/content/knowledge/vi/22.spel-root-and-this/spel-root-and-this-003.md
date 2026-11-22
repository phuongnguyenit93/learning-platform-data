# `#this` và object hiện tại trong scope của SpEL

## Mục tiêu

Trong Spring Expression Language (SpEL), `#this` đại diện cho object đang được đánh giá tại vị trí hiện tại. Object này được gọi là *active evaluation object* hoặc *current object*. Giá trị của `#this` có thể thay đổi khi SpEL đi vào một scope con, đặc biệt trong collection selection (`.?[...]`) và collection projection (`.![...]`).

`#root` đại diện cho root object của toàn bộ lần đánh giá. Root object được giữ ổn định trong suốt lần đánh giá, kể cả khi SpEL đang xử lý từng phần tử trong collection.

Phân biệt hai biến đặc biệt này giúp biểu thức nói rõ property nào thuộc object hiện tại và property nào thuộc object gốc. Ví dụ, trong `members.?[#this.score >= #root.minimumScore]`, `#this.score` là điểm của member đang xét, còn `#root.minimumScore` là ngưỡng trên object gốc.

## 1. `#this` ở cấp cao nhất

Khi một biểu thức bắt đầu được đánh giá, `#this` thường trỏ đến cùng object với `#root`. Nếu root object là một `Person`, các biểu thức sau có ý nghĩa tương đương:

```spel
name
#this.name
#root.name
```

`name` là property được phân giải ngầm trên current object. `#this.name` viết tường minh rằng property thuộc object đang hoạt động. `#root.name` viết tường minh rằng property thuộc root object.

Ví dụ Java:

```java
ExpressionParser parser = new SpelExpressionParser();
Person person = new Person("Lan", 28);
StandardEvaluationContext context = new StandardEvaluationContext(person);

String implicitName = parser.parseExpression("name")
        .getValue(context, String.class);

String currentName = parser.parseExpression("#this.name")
        .getValue(context, String.class);

String rootName = parser.parseExpression("#root.name")
        .getValue(context, String.class);
```

Cả ba biểu thức đều đọc tên của root `person` trong ví dụ này. Ở cấp cao nhất, `#this` và `#root` cùng trỏ đến root object.

## 2. Root object được thiết lập ở đâu?

Root object được cung cấp cho evaluation context hoặc cho lần gọi `getValue` cụ thể. Có thể đặt root khi tạo `StandardEvaluationContext`:

```java
StandardEvaluationContext context = new StandardEvaluationContext(person);
```

Hoặc tạo context trước rồi thiết lập root:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setRootObject(person);
```

Cũng có thể truyền root object trực tiếp vào overload `getValue`:

```java
Expression expression = parser.parseExpression("#root.name");
String name = expression.getValue(context, anotherPerson, String.class);
```

Trong lần đánh giá này, `anotherPerson` là root object được dùng cho biểu thức. Khi không truyền root object ở overload đó, SpEL sử dụng root object đã được đặt trong context.

`EvaluationContext` là nơi chứa root object, biến, property accessor, method resolver, type converter và các cơ chế đánh giá khác. Nó không phải chính root object.

## 3. `#this` thay đổi trong collection selection

Selection dùng `.?[condition]` để lọc các phần tử trong collection. Khi SpEL đánh giá điều kiện cho từng phần tử, `#this` trỏ đến phần tử hiện tại đang được xét.

Giả sử root object `Society` có property `members`, mỗi phần tử là một `Inventor`:

```spel
members.?[nationality == 'Serbian']
```

Trong điều kiện này, `nationality` được phân giải trên từng `Inventor` đang xét. Viết tường minh bằng `#this` cho kết quả tương đương:

```spel
members.?[#this.nationality == 'Serbian']
```

Có thể kết hợp current object với root object:

```spel
members.?[#this.score >= #root.minimumScore]
```

Ở đây:

- `#this` là từng `Inventor` đang được kiểm tra.
- `#this.score` là điểm của inventor hiện tại.
- `#root` vẫn là `Society` ban đầu.
- `#root.minimumScore` là ngưỡng điểm được lấy từ society.

Ví dụ Java:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "members.?[#this.score >= #root.minimumScore]");

StandardEvaluationContext context = new StandardEvaluationContext(society);
List<?> eligibleMembers = expression.getValue(context, List.class);
```

Selection thay đổi active object trong lúc đánh giá từng điều kiện, nhưng không thay đổi root object.

## 4. `#this` thay đổi trong collection projection

Projection dùng `.![projectionExpression]` để tính một giá trị cho mỗi phần tử. Trong biểu thức con, `#this` là phần tử hiện tại đang được chiếu:

```spel
members.![name]
members.![#this.name]
members.![#this.placeOfBirth.city]
```

Trong ví dụ thứ hai, `#this.name` đọc tên của inventor hiện tại. Có thể tham chiếu root object cùng lúc:

```spel
members.![#this.name + ' - ' + #root.name]
```

Giả sử `#root.name` là tên society; mỗi kết quả ghép tên member với tên society. `#this` thay đổi theo từng member, còn `#root` vẫn là society.

Ví dụ Java:

```java
Expression expression = parser.parseExpression(
        "members.![#this.name + ' - ' + #root.name]");

List<?> labels = expression.getValue(
        new StandardEvaluationContext(society), List.class);
```

Projection tạo một giá trị cho mỗi phần tử nguồn. `#this` cho phép biểu thức con truy cập rõ ràng object đang được chuyển đổi.

## 5. Property không có prefix và `#this.property`

Trong scope selection/projection, property không có prefix thường được phân giải trên active object hiện tại. Vì vậy:

```spel
members.?[active == true]
members.?[#this.active == true]
members.![name]
members.![#this.name]
```

là các cách viết tương ứng về mặt truy cập property hiện tại.

Dùng property ngắn gọn khi biểu thức đơn giản. Dùng `#this` tường minh khi:

- Biểu thức đồng thời tham chiếu `#root`.
- Có nhiều cấp object và cần tránh nhầm property thuộc object nào.
- Đọc biểu thức sau này cần thấy rõ current object.
- Một điều kiện hoặc phép chiếu có nhiều toán hạng và lời gọi method.

`#this` không phải tên biến do ứng dụng tự đăng ký. Đây là biến đặc biệt SpEL cung cấp trong quá trình đánh giá; không cần gọi `setVariable("this", ...)`.

## 6. Scope lồng nhau

Selection và projection có thể lồng nhau. Mỗi scope collection con thiết lập active object cho phần tử đang xử lý trong scope đó. Vì vậy, khi đi vào projection hoặc selection bên trong, `#this` biểu diễn phần tử của scope trong cùng.

Ví dụ một society có nhiều department, mỗi department có nhiều employee:

```spel
departments.![employees.![#this.email]]
```

Trong projection trong cùng, `#this` là employee hiện tại. Kết quả là danh sách các danh sách email, mỗi list con thuộc một department.

Ví dụ lồng selection trong projection:

```spel
departments.![employees.?[#this.active == true].![#this.email]]
```

Ở selection bên trong, `#this` là employee đang xét; ở projection sau selection, `#this` tiếp tục là employee được chiếu. `#root` vẫn trỏ đến root object ban đầu của toàn bộ expression.

Không nên giả định `#this` bên trong scope lồng nhau vẫn là phần tử của scope ngoài. Nếu cần dữ liệu của root object, dùng `#root`. Nếu cần dữ liệu của object cha trung gian, hãy truy cập nó qua một đường dẫn từ root hoặc thiết kế expression/helper sao cho object cha được cung cấp rõ ràng qua biến context.

## 7. `#this`, `#root` và expression variables

Ba dạng tham chiếu thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

| Cú pháp | Vai trò | Cách tạo giá trị |
| --- | --- | --- |
| `#root` | Root object của lần đánh giá. | Đặt qua `EvaluationContext` hoặc overload `getValue`. |
| `#this` | Active object tại scope hiện tại. | SpEL tự cập nhật trong quá trình đánh giá, ví dụ mỗi phần tử selection/projection. |
| `#threshold` | Biến do ứng dụng truyền vào expression. | Đăng ký bằng `context.setVariable("threshold", value)`. |

Ví dụ:

```java
StandardEvaluationContext context = new StandardEvaluationContext(society);
context.setVariable("threshold", 80);
```

```spel
members.?[#this.score >= #threshold and #root.enabled]
```

Trong biểu thức này, `#this.score` là điểm của member đang xét, `#threshold` là dữ liệu ứng dụng cung cấp, còn `#root.enabled` là trạng thái trên society.

Đăng ký biến không có dấu `#`; dấu `#` chỉ xuất hiện khi tham chiếu biến trong expression. `#root` và `#this` là hai biến đặc biệt được SpEL cung cấp sẵn.

## 8. `#this` khi gọi method

Trong một scope mà current object là một phần tử collection, có thể gọi method trên phần tử đó qua `#this`:

```spel
members.?[#this.isEligible()]
members.![#this.getDisplayName()]
```

Nếu method là property-style getter, SpEL thường cho phép truy cập theo property name:

```spel
members.![displayName]
```

Method được gọi trên object hiện tại của scope. Nếu method có side effect, nó có thể được gọi nhiều lần khi SpEL duyệt collection; ưu tiên method đọc dữ liệu hoặc tính toán thuần trong selection/projection.

## 9. Phân biệt current object với object được truy cập qua property

`#this` là object hiện tại của evaluation scope. Một property được truy cập từ object đó có thể trả về object khác, nhưng việc đọc property không có nghĩa là root object của toàn bộ lần đánh giá bị thay đổi.

Ví dụ:

```spel
customer.address.city
```

Ở cấp cao nhất, root/current object là customer. `address` là một object được truy cập từ customer, và `city` là property của address. Nếu cần làm rõ đường dẫn, có thể viết:

```spel
#root.customer.address.city
```

Trong selection/projection, active object là phần tử collection. Các property tiếp theo tạo thành đường dẫn từ phần tử đó; root vẫn được giữ nguyên.

Không nhầm `#this` với “object cuối cùng trong một đường dẫn property”. Khi cần nói rõ object thuộc scope nào, hãy dùng `#this` cho phần tử hiện tại và `#root` cho object gốc.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `#this` trả về object khác với mong đợi trong `.?[]` | Trong selection, current object là phần tử đang được kiểm tra. | Dùng `#this.property` cho phần tử; dùng `#root.property` cho root. |
| Dùng `#root` nhưng muốn đọc phần tử hiện tại | `#root` không thay đổi khi collection được duyệt. | Dùng `#this` hoặc property không prefix trong scope selection/projection. |
| Expression lồng nhau đọc nhầm object | `#this` chuyển sang phần tử của scope collection trong cùng. | Xác định scope hiện tại tại vị trí expression; dùng đường dẫn từ `#root` khi cần root. |
| `#this` không có giá trị mong đợi ở cấp cao nhất | Root object chưa được cung cấp hoặc lần `getValue` dùng root khác. | Kiểm tra `StandardEvaluationContext` và overload `getValue(context, rootObject)`. |
| Nhầm `#this` với biến ứng dụng | `#this` là biến đặc biệt do SpEL quản lý. | Không đăng ký biến `this`; dùng tên riêng như `#threshold` cho dữ liệu ứng dụng. |
| Property ngắn gọn khó đọc khi có nhiều object | Property được phân giải trên active object hiện tại. | Viết `#this.property` hoặc `#root.property` tường minh. |
| Method bị gọi nhiều lần trong projection | Expression con được đánh giá một lần cho mỗi phần tử. | Tránh side effect; tính trước dữ liệu hoặc dùng method thuần đọc. |

## Ghi nhớ

- `#this` là active evaluation object tại vị trí expression đang chạy.
- Ở cấp cao nhất, `#this` thường trùng với `#root`.
- `#root` là root object của toàn bộ lần đánh giá và không thay đổi khi SpEL duyệt collection.
- Trong selection `.?[...]`, `#this` là phần tử đang được kiểm tra.
- Trong projection `.![...]`, `#this` là phần tử đang được chiếu.
- Property không prefix trong scope selection/projection được phân giải trên current object; `#this.property` viết tường minh cùng ý nghĩa.
- Trong scope lồng nhau, `#this` thuộc collection scope trong cùng; không giả định nó vẫn là phần tử cha.
- `#threshold` là biến ứng dụng đăng ký trong context; `#this` và `#root` là biến đặc biệt do SpEL cung cấp.
- Đặt root bằng constructor/setter của context hoặc overload `getValue` phù hợp.
- Dùng `#this` và `#root` rõ ràng để tránh nhầm object trong expression phức tạp.

## Tài liệu tham khảo

- [Spring Framework Reference — Variables (`#this` and `#root`)](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework API — EvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)