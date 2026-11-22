# Khởi tạo mảng và kiểu collection trong SpEL

## Mục tiêu

Spring Expression Language (SpEL) có thể tạo mảng Java, tạo instance của class bằng constructor và tạo collection ngay trong biểu thức. Ba cách này có kết quả và đặc tính khác nhau: array construction tạo array có component type xác định; constructor invocation tạo instance của class được chỉ định; inline list/map tạo collection literal do SpEL cung cấp.

Chủ đề này hữu ích khi một biểu thức cần tạo dữ liệu trung gian, truyền một danh sách tham số cho method, khởi tạo giá trị cấu hình hoặc tạo object nhỏ từ dữ liệu runtime. Cú pháp chính đều dùng `new` cho array/constructor, còn `{...}` và `{key:value}` là inline collection literal.

## 1. Khởi tạo mảng với kích thước xác định

SpEL dùng cú pháp gần giống Java để tạo array:

```spel
new int[4]
new java.lang.String[3]
new boolean[2]
```

Biểu thức tạo array mới với kích thước đã chỉ định. Các phần tử được khởi tạo theo quy tắc mặc định của Java:

| Kiểu phần tử | Giá trị ban đầu |
| --- | --- |
| `int`, `long`, `double` và primitive số khác | `0` hoặc `0.0` tương ứng. |
| `boolean` | `false`. |
| `char` | Ký tự null (`\u0000`). |
| Kiểu tham chiếu như `String` hoặc object | `null`. |

Ví dụ đánh giá trong Java:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

int[] numbers = parser.parseExpression("new int[4]")
        .getValue(context, int[].class);

String[] names = parser.parseExpression("new java.lang.String[3]")
        .getValue(context, String[].class);
```

`numbers` có bốn phần tử ban đầu bằng `0`; `names` có ba phần tử ban đầu bằng `null`. Array có kích thước cố định sau khi được tạo, giống array Java thông thường.

## 2. Khởi tạo mảng với initializer

Nếu đã biết các phần tử cần có, có thể truyền initializer ngay khi tạo array:

```spel
new int[] {1, 2, 3}
new java.lang.String[] {'red', 'green', 'blue'}
new boolean[] {true, false, true}
```

Initializer được đánh giá để điền giá trị vào array mới. Kiểu phần tử của array được xác định bởi type đứng trước `[]`; các giá trị initializer phải tương thích hoặc có thể chuyển đổi sang kiểu đó.

Ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

int[] primes = parser.parseExpression("new int[] {2, 3, 5, 7, 11}")
        .getValue(context, int[].class);

String[] roles = parser.parseExpression(
        "new java.lang.String[] {'READER', 'EDITOR'}")
        .getValue(context, String[].class);
```

Array initializer đặc biệt hữu ích khi một API yêu cầu `int[]`, `String[]` hoặc một array có component type cụ thể. Inline list `{2, 3, 5}` tạo `List`, còn `new int[] {2, 3, 5}` tạo `int[]`; hai kết quả không thể xem là cùng một kiểu.

## 3. Mảng nhiều chiều

SpEL hỗ trợ tạo array nhiều chiều bằng cách khai báo kích thước của từng chiều:

```spel
new int[4][5]
new java.lang.String[2][3]
```

Ví dụ Java:

```java
int[][] matrix = parser.parseExpression("new int[4][5]")
        .getValue(context, int[][].class);
```

Biểu thức tạo một array ngoài có bốn hàng, mỗi hàng là một array `int` có năm phần tử. Các phần tử primitive ban đầu bằng `0`.

SpEL hiện không cho phép cung cấp initializer khi tạo array nhiều chiều. Vì vậy, dạng như `new int[2][2] {{1, 2}, {3, 4}}` không được hỗ trợ. Nếu cần một ma trận có dữ liệu ban đầu, hãy tạo array trong Java hoặc khởi tạo từng phần tử bằng code ứng dụng.

## 4. Kích thước mảng được tính động

Kích thước mỗi chiều là một biểu thức được đánh giá khi tạo array. Có thể dùng biến hoặc property trong `EvaluationContext`:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("new int[#size]");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("size", 5);

int[] values = expression.getValue(context, int[].class);
```

Ở lần đánh giá này, `#size` là `5`, nên array có năm phần tử. Có thể tái sử dụng expression với kích thước khác bằng context mới hoặc cập nhật biến trước lần đánh giá tiếp theo.

Giá trị kích thước phải là số nguyên hợp lệ và nằm trong giới hạn bộ nhớ của ứng dụng. Kích thước âm, giá trị không chuyển đổi được hoặc array quá lớn có thể khiến evaluation thất bại hoặc gây áp lực bộ nhớ. Hãy xác thực kích thước trước khi đưa vào context.

## 5. Gọi constructor để tạo object

Toán tử `new` cũng dùng để gọi constructor của class. Với class ngoài `java.lang`, cần dùng tên class đầy đủ gồm package:

```spel
new java.math.BigDecimal('19.95')
new java.util.Date()
new com.example.Point(10, 20)
```

Với các kiểu trong `java.lang`, có thể dùng tên ngắn như `new String('hello')` hoặc `new Integer('42')` nếu class/constructor còn phù hợp với JDK đang chạy. Trong code mới, nên tránh wrapper constructor đã deprecated và dùng factory như `Integer.valueOf` khi phù hợp.

Ví dụ Java:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

BigDecimal price = parser.parseExpression(
        "new java.math.BigDecimal('19.95')")
        .getValue(context, BigDecimal.class);
```

SpEL tìm constructor phù hợp trên class được chỉ định, rồi chuyển đổi đối số nếu `TypeConverter` của context hỗ trợ. Constructor được gọi phải có thể truy cập theo cơ chế reflection được cấu hình.

## 6. Truyền đối số động vào constructor

Đối số constructor có thể là literal, biến, property, phép toán hoặc kết quả của một expression khác:

```spel
new java.math.BigDecimal(#amount)
new com.example.Range(#minimum, #maximum)
new com.example.UserProfile(#userId, #displayName)
```

Ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "new java.math.BigDecimal(#amount)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("amount", "125000.50");

BigDecimal amount = expression.getValue(context, BigDecimal.class);
```

SpEL đánh giá `#amount` rồi truyền giá trị đó cho constructor. Dữ liệu đầu vào vẫn là dữ liệu, không cần nối nó vào source expression. Cách truyền bằng biến tránh lỗi cú pháp khi input chứa dấu nháy hoặc ký tự đặc biệt.

Nếu class có nhiều constructor overload, SpEL chọn constructor dựa trên số lượng và kiểu đối số cùng khả năng chuyển đổi của context. Khi nhiều chữ ký có thể phù hợp, hãy truyền đối số có kiểu rõ ràng hoặc thiết kế constructor/API ít mơ hồ hơn.

## 7. Tạo các kiểu collection bằng constructor

Muốn có một collection Java cụ thể, hãy gọi constructor của implementation mong muốn:

```spel
new java.util.ArrayList()
new java.util.LinkedList()
new java.util.HashSet()
new java.util.LinkedHashSet()
new java.util.HashMap()
new java.util.LinkedHashMap()
```

Ví dụ:

```java
List<?> list = parser.parseExpression("new java.util.ArrayList()")
        .getValue(context, List.class);

Set<?> set = parser.parseExpression("new java.util.LinkedHashSet()")
        .getValue(context, Set.class);

Map<?, ?> map = parser.parseExpression("new java.util.LinkedHashMap()")
        .getValue(context, Map.class);
```

Việc chọn implementation ảnh hưởng đến hành vi của collection:

| Kiểu | Đặc tính thường dùng |
| --- | --- |
| `ArrayList` | List có thứ tự, truy cập theo index nhanh, cho phép phần tử trùng. |
| `LinkedList` | List có thứ tự, hỗ trợ thêm/xóa ở hai đầu; truy cập theo index thường chậm hơn ArrayList. |
| `HashSet` | Không giữ thứ tự iteration; loại bỏ phần tử trùng theo `equals`/`hashCode`. |
| `LinkedHashSet` | Giữ insertion order và loại bỏ phần tử trùng. |
| `HashMap` | Map key/value không cam kết thứ tự iteration. |
| `LinkedHashMap` | Giữ thứ tự insertion của entry theo cấu hình mặc định. |

Constructor phải tồn tại và có thể truy cập. Dùng tên class đầy đủ cho các kiểu như `java.util.ArrayList` và `java.util.LinkedHashMap`.

## 8. Khởi tạo collection có phần tử ban đầu

Constructor có thể nhận một collection khác làm đối số. Có thể kết hợp inline list hoặc inline map với constructor của collection:

```spel
new java.util.ArrayList({'READ', 'WRITE'})
new java.util.LinkedHashSet({'RED', 'GREEN', 'BLUE'})
new java.util.LinkedHashMap({'primary': 'blue', 'secondary': 'green'})
```

Trong các ví dụ này, inline list/map tạo collection nguồn; constructor của `ArrayList`, `LinkedHashSet` hoặc `LinkedHashMap` nhận collection đó và tạo instance mới của kiểu được yêu cầu.

Ví dụ Java:

```java
List<?> permissions = parser.parseExpression(
        "new java.util.ArrayList({'READ', 'WRITE'})")
        .getValue(context, List.class);

Set<?> colors = parser.parseExpression(
        "new java.util.LinkedHashSet({'RED', 'GREEN', 'BLUE'})")
        .getValue(context, Set.class);

Map<?, ?> palette = parser.parseExpression(
        "new java.util.LinkedHashMap({'primary': 'blue', 'secondary': 'green'})")
        .getValue(context, Map.class);
```

Đây là cách tạo một collection implementation cụ thể khi expression cần một `List`, `Set` hoặc `Map` có semantics nhất định. Nếu chỉ cần collection literal đơn giản, `{...}` hoặc `{key:value}` ngắn gọn hơn và không cần gọi constructor.

## 9. Phân biệt array construction, inline collection và collection constructor

Ba cách tạo dữ liệu này không thay thế lẫn nhau:

| Cú pháp | Kiểu kết quả | Khi nên dùng |
| --- | --- | --- |
| `new int[] {1, 2, 3}` | `int[]` | API yêu cầu array primitive hoặc array có component type cụ thể. |
| `new String[] {'a', 'b'}` | `String[]` | Cần array object có kiểu phần tử cụ thể. |
| `{1, 2, 3}` | SpEL inline `List` | Danh sách literal nhỏ, không cần chỉ định implementation. |
| `{'a': 1, 'b': 2}` | SpEL inline `Map` | Map literal nhỏ, không cần chỉ định implementation. |
| `new java.util.ArrayList({'a', 'b'})` | `ArrayList` | Cần một List mutable hoặc implementation cụ thể. |
| `new java.util.LinkedHashSet({'a', 'b'})` | `LinkedHashSet` | Cần loại duplicate và giữ insertion order. |

Inline list có thể được SpEL tối ưu thành constant collection khi tất cả phần tử là literal cố định. Constructor collection tạo instance theo constructor được gọi; không nên giả định nó có cùng caching behavior với inline constant list.

## 10. Dùng trong Spring `@Value`

SpEL có thể khởi tạo array hoặc collection trong annotation `@Value`. Cặp `#{...}` bên ngoài là delimiter để Spring đánh giá biểu thức; phần `new ...` bên trong là cú pháp khởi tạo SpEL:

```java
@Component
public class FeatureConfiguration {

    @Value("#{new int[] {1, 2, 3}}")
    private int[] retryDelays;

    @Value("#{new java.util.ArrayList({'READ', 'WRITE'})}")
    private List<String> permissions;

    @Value("#{new java.util.LinkedHashMap({'primary': 'blue', 'secondary': 'green'})}")
    private Map<String, String> palette;
}
```

Spring thực hiện conversion/binding kết quả vào property đích. Kiểu generic như `List<String>` hoặc `Map<String, String>` thuộc khai báo Java và metadata của property; cú pháp constructor SpEL không viết tham số generic kiểu Java.

## 11. Cấu hình parser và giới hạn compiler

Array construction là một phần của cú pháp constructor reference trong SpEL. Tuy nhiên, expression có array construction hiện không được SpEL compiler biên dịch thành bytecode. Expression vẫn có thể được parse và đánh giá theo cơ chế thông dịch; giới hạn này chỉ có nghĩa là compiler không hỗ trợ loại expression đó.

Nếu ứng dụng bật compiler mode (`SpelCompilerMode.IMMEDIATE` hoặc `MIXED`), hãy lưu ý các expression chứa `new int[4]`, `new int[] {1, 2, 3}` hoặc array construction khác sẽ không được compile. Nếu cần hiệu năng cho đoạn xử lý tạo array lặp lại nhiều lần, cân nhắc tạo array trong Java và truyền qua root object/biến.

`SpelParserConfiguration` có thể điều khiển một số hành vi parser như auto-grow null references và collections khi index vào phần tử phù hợp. Auto-grow không thay đổi quy tắc constructor array: array được tạo bằng `new` có kích thước theo biểu thức khởi tạo và array Java không tự tăng kích thước sau khi đã tạo.

## 12. Kiểm soát quyền tạo object

Constructor invocation có thể tạo instance của class mà `TypeLocator` và `ConstructorResolver` cho phép tìm thấy. Không nên đánh giá expression không đáng tin cậy bằng một `StandardEvaluationContext` có toàn quyền reflection và khả năng tạo object tùy ý.

Các nguyên tắc nên áp dụng:

- Chỉ cho phép những class cần thiết trong expression.
- Dùng type locator và constructor resolver tùy chỉnh nếu cần allowlist class/constructor.
- Tránh expose constructor có side effect, mở file, kết nối mạng hoặc tiêu thụ tài nguyên lớn.
- Xác thực kích thước array, số phần tử và đối số trước khi đánh giá.
- Truyền dữ liệu runtime qua biến context thay vì ghép input vào source expression.
- Với expression do người dùng cung cấp, cân nhắc một API helper hẹp hoặc context giới hạn thay vì constructor invocation tùy ý.

`SimpleEvaluationContext` được thiết kế với tập tính năng hạn chế cho data binding và không hỗ trợ type references; nếu cần tạo object bằng `new`, hãy xác định rõ context và quyền constructor mà ứng dụng cho phép.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Array có giá trị mặc định thay vì dữ liệu mong đợi | Dùng `new Type[size]` mà không có initializer. | Dùng `new Type[] { ... }` nếu muốn điền giá trị ngay. |
| Nhận List khi API yêu cầu array | Dùng inline list `{...}` thay vì array construction. | Dùng `new int[] { ... }` hoặc array component type phù hợp. |
| Không tìm thấy class khi gọi constructor | Tên class thiếu package hoặc classloader/type locator không tìm thấy class. | Dùng tên đầy đủ, ví dụ `new java.util.ArrayList()`. |
| Không tìm thấy constructor phù hợp | Sai số đối số, kiểu không tương thích hoặc constructor không truy cập được. | Kiểm tra chữ ký constructor; truyền đối số có kiểu rõ ràng. |
| Constructor overload được chọn không như mong đợi | Nhiều constructor có thể nhận các đối số sau chuyển đổi. | Tránh overload mơ hồ; chuyển đổi đối số rõ ràng hoặc tạo factory/helper riêng. |
| Không khởi tạo được array nhiều chiều có initializer | SpEL hiện không hỗ trợ initializer cho array nhiều chiều. | Tạo array và điền phần tử trong Java. |
| Expression array không được compiler biên dịch | Array construction nằm trong nhóm compiler limitations của SpEL. | Cho expression chạy interpreted hoặc tạo array ở Java. |
| Array size gây lỗi hoặc tốn bộ nhớ | Kích thước âm, không hợp lệ hoặc quá lớn. | Xác thực giới hạn size trước khi đánh giá. |
| Collection không giữ thứ tự mong đợi | Dùng `HashSet`/`HashMap` nhưng kỳ vọng insertion order. | Dùng `LinkedHashSet`/`LinkedHashMap` nếu cần giữ thứ tự thêm. |

## Ghi nhớ

- `new int[4]` tạo array có bốn phần tử mặc định; `new int[] {1, 2, 3}` tạo array có initializer.
- Array nhiều chiều có thể tạo bằng `new int[4][5]`; SpEL hiện không hỗ trợ initializer cho array nhiều chiều.
- Kích thước array có thể lấy từ biến/property runtime; luôn xác thực size.
- `new fully.qualified.ClassName(args)` gọi constructor của class; `java.lang` và primitive có thể dùng tên ngắn theo cú pháp SpEL.
- Có thể tạo `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, `HashMap` hoặc `LinkedHashMap` bằng constructor.
- Kết hợp constructor collection với inline list/map để tạo implementation cụ thể có dữ liệu ban đầu.
- `{...}` tạo inline List; `{key:value}` tạo inline Map; `new Type[] {...}` tạo array.
- Cú pháp SpEL không khai báo generic type parameter như Java; kiểu generic được xử lý ở property/binding hoặc code Java.
- Array construction không được SpEL compiler biên dịch; expression vẫn có thể chạy bằng interpreter.
- Giới hạn type locator/constructor resolver và xác thực input nếu expression đến từ nguồn không tin cậy.

## Tài liệu tham khảo

- [Spring Framework Reference — Array Construction](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/array-construction.html)
- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Inline Lists](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html)
- [Spring Framework Reference — Inline Maps](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-maps.html)
- [Spring Framework Reference — Evaluation and Compiler Limitations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — ConstructorResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)