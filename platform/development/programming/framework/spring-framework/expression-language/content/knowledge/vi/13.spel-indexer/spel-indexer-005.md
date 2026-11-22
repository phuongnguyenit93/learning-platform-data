# Biểu thức chỉ số và giá trị được tính động trong SpEL

## Mục tiêu

Indexer là cú pháp dấu ngoặc vuông `[...]` của Spring Expression Language (SpEL), dùng để lấy một phần tử hoặc property từ cấu trúc đang được truy cập. Index không bắt buộc phải là một con số hay key viết cố định: nội dung bên trong `[...]` là một biểu thức SpEL được đánh giá khi biểu thức bên ngoài chạy.

Nhờ vậy, ứng dụng có thể chọn phần tử theo biến, property, phép tính hoặc giá trị tra cứu tại runtime. Ví dụ, `items[#selectedIndex]` chọn phần tử theo biến `selectedIndex`, còn `officers[#role]` tra map theo key do context cung cấp.

## 1. Cú pháp cơ bản và chỉ số bắt đầu từ 0

Indexer dùng dấu ngoặc vuông sau đối tượng hoặc property cần truy cập:

```spel
items[0]
officers['president']
members[0].name
```

Với mảng và cấu trúc được đánh chỉ số theo vị trí, index bắt đầu từ `0`: phần tử đầu tiên là `[0]`, phần tử thứ hai là `[1]`. Không dùng quy ước bắt đầu từ `1` như số thứ tự hiển thị cho người dùng.

SpEL hỗ trợ indexer trên nhiều loại cấu trúc:

| Cấu trúc | Cách truy cập | Giá trị trả về |
| --- | --- | --- |
| Array | `inventions[3]` | Phần tử ở vị trí thứ tư. |
| `List` | `members[0]` | Phần tử đầu tiên. |
| Collection khác như `Set` | `members[0]` | Phần tử đầu tiên theo thứ tự iterator trả về. |
| `Map` | `officers['president']` | Giá trị ứng với key `president`. |
| `String` | `name[7]` | Ký tự ở vị trí thứ tám, dưới dạng `String`. |
| Object | `#root['name']` | Property có tên `name`. |

Với `List`, SpEL truy cập trực tiếp theo vị trí. Với Collection không phải `List`, chẳng hạn `Set`, SpEL đi qua `Iterator` để lấy phần tử thứ n. Vì thứ tự của một số collection không được bảo đảm, không nên dùng index theo vị trí với collection không có thứ tự ổn định nếu kết quả phải xác định.

## 2. Index bên trong ngoặc vuông là một biểu thức

Phần nằm trong `[...]` được phân tích như một biểu thức SpEL. Vì vậy, index có thể là literal, biến, property hoặc một phép tính:

```spel
items[2]
items[#selectedIndex]
items[#page * #pageSize]
items[#page * #pageSize + #offset]
```

Ở ví dụ cuối, SpEL tính `#page * #pageSize + #offset` trước, rồi dùng kết quả làm index. Khi các biến thay đổi, cùng một biểu thức đã parse có thể chọn phần tử khác.

Đối với `Map`, biểu thức bên trong ngoặc vuông tạo ra key:

```spel
officers['president']
officers[#selectedRole]
prices[#productCode]
```

Key có thể là chuỗi, số, enum hoặc kiểu khác phù hợp với kiểu key của map. Nếu map có kiểu key được khai báo, SpEL có thể dùng `TypeConverter` của evaluation context để chuyển key sang kiểu đó. Nên truyền key đúng kiểu ngay từ đầu để biểu thức rõ ràng và tránh phụ thuộc vào chuyển đổi ngầm.

## 3. Tính index động từ EvaluationContext

Cách dễ kiểm soát nhất là đưa giá trị index vào evaluation context bằng biến. Không cần tạo lại chuỗi biểu thức mỗi khi index thay đổi.

Giả sử root object `Order` có property `items`, mỗi item có `productName`. Ứng dụng muốn đọc item theo vị trí người dùng chọn:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("items[#selectedIndex].productName");

StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("selectedIndex", requestedIndex);

String productName = expression.getValue(context, String.class);
```

`requestedIndex` được cung cấp như một giá trị dữ liệu. SpEL đánh giá biến `#selectedIndex`, dùng kết quả để lấy phần tử từ `items`, rồi đọc property `productName` của phần tử đó.

Ví dụ, với danh sách `items` có các tên `Keyboard`, `Mouse`, `Monitor` và `requestedIndex = 1`, kết quả là `Mouse`.

Biến trong SpEL có dấu `#`. Tên truyền vào `setVariable` không có dấu `#`:

```java
context.setVariable("selectedIndex", 1);
```

```spel
items[#selectedIndex]
```

Đừng ghép `requestedIndex` trực tiếp vào source expression bằng nối chuỗi. Truyền nó qua context giúp tách dữ liệu khỏi cú pháp biểu thức, tránh lỗi khi input có ký tự đặc biệt và giúp tái sử dụng biểu thức đã parse.

## 4. Kết hợp index với property và biểu thức khác

Indexer có thể nối tiếp property navigation, method invocation và các indexer khác:

```spel
members[#memberIndex].name
orders[#orderIndex].items[#itemIndex].productName
products[#productIndex].price * #quantity
names[#position].toUpperCase()
```

Các biểu thức trên lần lượt:

- Chọn một member rồi đọc `name`.
- Chọn một order, sau đó chọn item bên trong order và đọc tên sản phẩm.
- Lấy giá sản phẩm rồi nhân với số lượng được truyền qua biến.
- Chọn một ký tự từ chuỗi rồi gọi `toUpperCase()` trên chuỗi ký tự đó.

Indexer của chuỗi trả về một `String`, không phải `Character`. Điều này hữu ích khi cần nối ký tự, gọi method chuỗi hoặc so sánh kết quả với một string literal.

Index cũng có thể được tính bằng biểu thức điều kiện hoặc phép toán khác:

```spel
items[#useLast ? #itemsCount - 1 : #selectedIndex]
```

Ví dụ này chọn phần tử cuối nếu `#useLast` là true; nếu không, dùng `#selectedIndex`. Hãy bảo đảm các biến tồn tại và biểu thức trả về kiểu index phù hợp với cấu trúc đích.

## 5. Ví dụ với Map và key được tính động

Giả sử root object có map `officers` với key kiểu `String`. Ứng dụng xác định role tại runtime:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("officers[#role]");

StandardEvaluationContext context = new StandardEvaluationContext(society);
context.setVariable("role", requestedRole);

Inventor officer = expression.getValue(context, Inventor.class);
```

Nếu `requestedRole` là `president`, SpEL lấy giá trị của `officers['president']`. Khi role thay đổi thành `secretary`, cùng expression sẽ tra key khác.

Với map có key không phải chuỗi, hãy cung cấp giá trị đúng kiểu. Ví dụ map dùng enum `Color` làm key có thể được truy cập bằng type reference:

```spel
fruitMap[T(example.Color).RED]
```

Trong biểu thức thực tế, package của enum phải khớp với class trong ứng dụng và type locator phải cho phép tham chiếu class đó. Nếu key đến từ biến context, có thể truyền enum instance vào `#color` rồi dùng `fruitMap[#color]`.

Nếu key không tồn tại, `Map.get(key)` thường trả về `null`. Điều đó khác với index ngoài phạm vi của list/array. Nếu cần phân biệt key không tồn tại với key có giá trị null, hãy kiểm tra `containsKey` trên map.

## 6. Đọc property của object bằng indexer

Ngoài map, cú pháp indexer còn có thể đọc property của object theo tên:

```spel
#root['name']
#root['placeOfBirth']
```

Điều này tương tự truy cập property bằng dấu chấm:

```spel
name
placeOfBirth
```

Indexer dạng property có ích khi tên property được tính động:

```java
context.setVariable("propertyName", requestedProperty);
```

```spel
#root[#propertyName]
```

Chỉ sử dụng cách này khi property accessor của context cho phép truy cập property đó. Không coi việc property name là một biến động đồng nghĩa với việc mọi property đều nên được expose cho biểu thức.

## 7. Kiểm soát null và index ngoài phạm vi

Indexer thông thường cần target tồn tại và index hợp lệ. Một số tình huống thường gặp:

| Tình huống | Hành vi cần lưu ý |
| --- | --- |
| List/array/string có index hợp lệ | Trả về phần tử hoặc ký tự tương ứng. |
| Index âm hoặc vượt giới hạn | Thường phát sinh `SpelEvaluationException` do index không hợp lệ hoặc ngoài phạm vi. |
| Map không có key | `Map.get` thường trả về `null`. |
| Target collection/map là null | Indexer thông thường không thể truy cập target null. |
| Index expression trả về null hoặc kiểu không chuyển đổi được | Không thể tạo index hợp lệ; evaluation có thể thất bại. |

Với Spring Framework 6.2 trở lên, có thể dùng null-safe indexing bằng cú pháp `?.[`:

```spel
members?.[0]
officers?.['president']
customer?.orders?.[#selectedIndex]
```

Nếu target ngay trước `?.[` là null, kết quả của indexer là null thay vì ném lỗi chỉ vì target null. Null-safe indexing không biến index ngoài phạm vi thành giá trị hợp lệ và không tự áp dụng giá trị mặc định cho kết quả null.

Với Spring Framework 7.0, null-safe indexing còn hỗ trợ cấu trúc được chứa trong `Optional`: nếu Optional là null hoặc empty, kết quả truy cập null-safe là null; nếu có giá trị, SpEL index vào giá trị bên trong.

Nếu muốn dùng kết quả với giá trị mặc định, có thể kết hợp Elvis operator:

```spel
members?.[#selectedIndex] ?: #fallbackMember
```

Ở đây `#fallbackMember` chỉ được dùng khi kết quả truy cập null. Cần phân biệt trường hợp target null, map không có key và một phần tử thực sự có giá trị null nếu nghiệp vụ cần xử lý riêng.

## 8. Indexing và thay đổi dữ liệu

Indexer không chỉ dùng để đọc. Với expression có thể ghi, `setValue` có thể cập nhật phần tử của cấu trúc được hỗ trợ, ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("items[#selectedIndex].status");

StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("selectedIndex", 1);

expression.setValue(context, "SHIPPED");
```

Việc ghi thành công phụ thuộc vào target và accessor có hỗ trợ ghi hay không. List và map có thể cập nhật phần tử/key; array có thể cập nhật phần tử hiện có; string không thể sửa trực tiếp vì `String` là immutable. Với cấu trúc custom, cần đăng ký accessor hỗ trợ write.

Nếu bật `autoGrowCollections` trong `SpelParserConfiguration`, một số thao tác ghi vào List có thể tự mở rộng list khi index nằm sau phần tử cuối, trong giới hạn `maximumAutoGrowSize`. Đây là hành vi cấu hình dành cho trường hợp ghi; không nên dựa vào nó để che lỗi index khi đọc. Array không thể tự mở rộng kích thước.

## 9. IndexAccessor cho cấu trúc tùy chỉnh

Từ Spring Framework 6.2, ứng dụng có thể triển khai và đăng ký `IndexAccessor` để SpEL hỗ trợ cấu trúc không phải array, collection, map, string hoặc object property thông thường.

Ví dụ một kiểu `FruitMap` có API `getFruit(Color)` và `setFruit(Color, String)` nhưng không implement `Map`. Có thể đăng ký `ReflectiveIndexAccessor`:

```java
IndexAccessor accessor = new ReflectiveIndexAccessor(
        FruitMap.class, Color.class, "getFruit", "setFruit");
context.addIndexAccessor(accessor);
context.setVariable("fruitMap", new FruitMap());
```

Sau khi đăng ký, biểu thức có thể đọc và ghi theo cú pháp indexer:

```spel
#fruitMap[T(example.Color).RED]
#fruitMap[T(example.Color).RED] = 'strawberry'
```

`ReflectiveIndexAccessor` dùng public read-method và, nếu cấu hình, public write-method theo chữ ký đã cung cấp. Nếu cần hỗ trợ compilation của expression dùng custom accessor, accessor cần implement `CompilableIndexAccessor`; reflective accessor có sẵn cũng hỗ trợ compilation cho trường hợp đọc đáp ứng điều kiện của API.

## 10. Tái sử dụng expression với index thay đổi

Không cần parse lại expression mỗi lần index thay đổi. Có thể parse một lần rồi cập nhật biến trong context:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("items[#index].productName");

StandardEvaluationContext context = new StandardEvaluationContext(order);

context.setVariable("index", 0);
String first = expression.getValue(context, String.class);

context.setVariable("index", 2);
String third = expression.getValue(context, String.class);
```

Expression đã parse giữ cấu trúc cú pháp; biến `#index` được đọc lại khi `getValue` chạy. Điều này giảm công việc parse và làm cho dữ liệu thay đổi không cần biến thành một phần của source expression.

Nếu context được dùng đồng thời từ nhiều thread, không nên chia sẻ một context mutable rồi thay biến `#index` giữa các lần đánh giá. Tạo context riêng cho từng lần đánh giá hoặc từng request để tránh các request ghi đè biến của nhau.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Lấy sai phần tử | Nhầm index bắt đầu từ 1 hoặc dùng thứ tự không ổn định của Set. | Dùng index zero-based; với Set, chuyển sang List có thứ tự xác định nếu cần vị trí ổn định. |
| Index ngoài phạm vi | Giá trị tính động âm hoặc lớn hơn kích thước cấu trúc. | Kiểm tra index và kích thước trước khi đánh giá, hoặc chọn phần tử theo rule có kiểm soát. |
| Map trả về null | Key không tồn tại hoặc value được map tới key đó là null. | Kiểm tra `containsKey` nếu cần phân biệt hai trường hợp. |
| Không chuyển được map key | Kiểu key của map khác kiểu giá trị index. | Truyền key đúng kiểu hoặc cấu hình TypeConverter phù hợp. |
| Null-safe index vẫn cho kết quả null | Target là null, map key thiếu hoặc phần tử có giá trị null. | Xác định nguồn null; dùng Elvis/default hoặc kiểm tra riêng theo nghiệp vụ. |
| `?.[` không parse được | Ứng dụng chạy Spring Framework trước 6.2. | Dùng kiểm tra null tường minh hoặc nâng phiên bản framework nếu cần cú pháp này. |
| Custom object không index được | Chưa có `IndexAccessor` tương thích trong evaluation context. | Đăng ký `IndexAccessor` hoặc `ReflectiveIndexAccessor` phù hợp. |
| Biểu thức chạy sai khi có nhiều request | Context mutable dùng chung và biến index bị ghi đè. | Dùng evaluation context riêng cho từng request/lần đánh giá. |

## Ghi nhớ

- `[...]` là một index expression; nội dung bên trong được đánh giá tại runtime.
- Index số của array, list, collection và string bắt đầu từ `0`.
- List được truy cập theo vị trí; collection khác List được duyệt theo Iterator nên thứ tự có thể không ổn định.
- Map dùng biểu thức trong ngoặc vuông làm key; có thể truyền key động qua `#variable`.
- String indexer trả về ký tự dưới dạng `String`; object indexer có thể truy cập property theo tên.
- Dùng `items[#selectedIndex]` và `map[#key]` để truyền dữ liệu động qua `EvaluationContext` thay vì nối chuỗi expression.
- Spring Framework 6.2 bổ sung null-safe indexing `?.[` và `IndexAccessor` cho cấu trúc custom; Spring 7.0 mở rộng null-safe indexing cho cấu trúc trong Optional.
- Index ngoài phạm vi vẫn là lỗi; null-safe indexing chỉ xử lý target null.
- Có thể dùng `setValue` để ghi nếu target/accessor hỗ trợ; auto-grow collection chỉ áp dụng theo cấu hình và giới hạn.
- Parse expression một lần rồi tái sử dụng với context phù hợp; không chia sẻ context mutable giữa các request đồng thời.

## Tài liệu tham khảo

- [Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers](https://www.springframework.org/spring/reference/core/expressions/language-ref/properties-arrays.html)
- [Spring Framework Reference — Safe Navigation Operator](https://springframework.org/spring-framework/reference/7.1/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework API — IndexAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/IndexAccessor.html)
- [Spring Framework API — ReflectiveIndexAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/ReflectiveIndexAccessor.html)
- [Spring Framework source — Indexer](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/Indexer.java)