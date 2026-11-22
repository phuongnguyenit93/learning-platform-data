# Kiểu có đầy đủ thông tin lúc chạy (reifiable type) là gì trong Java?

Trong Java, **reifiable type** là kiểu có biểu diễn đầy đủ tại thời điểm chạy (*runtime*) để JVM thực hiện các phép kiểm tra kiểu phù hợp với kiểu đó. Ngược lại, nhiều kiểu liên quan đến generic, ví dụ `List<String>` hoặc biến kiểu `T`, là **non-reifiable**: sau quá trình *type erasure*, JVM không có đủ thông tin về đối số kiểu cụ thể để kiểm tra trực tiếp toàn bộ kiểu generic như trình biên dịch đã kiểm tra ở mã nguồn.

Ví dụ, một đối tượng `ArrayList<String>` và một đối tượng `ArrayList<Integer>` đều có runtime class `ArrayList`. JVM có thể kiểm tra chúng có phải `List` hay không, nhưng không thể chỉ dùng `instanceof` trên một tham chiếu `Object` để xác nhận danh sách thứ nhất thực sự tuân thủ `List<String>`.

Khái niệm này quan trọng khi học `instanceof`, class literal, generic array, raw type, wildcard và reflection.

> Điểm dễ nhầm: **`List<?>` là reifiable**, nhưng điều đó **không có nghĩa JVM biết kiểu phần tử của danh sách**. `List<?>` chỉ yêu cầu kiểm tra đây là một `List`, không yêu cầu xác định đối số kiểu cụ thể.

## 1. “Có đầy đủ thông tin lúc chạy” là đầy đủ cho phép kiểm tra nào?

Ở mã nguồn, `List<String>` giúp `javac` biết rằng một lời gọi `add` phải nhận `String` và kết quả `get` được xem là `String`. Nhưng JVM dùng runtime class và các descriptor đã xóa kiểu để hoạt động. Đối số `String` của biến `List<String>` thông thường không được lưu thành một class riêng mang tên `List<String>`.

Xét đoạn minh họa:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

boolean sameClass = names.getClass() == numbers.getClass(); // true
```

Đây là snippet đặt trong một phương thức Java hợp lệ. Cả hai đối tượng đều được tạo bằng `ArrayList`; khác biệt đối số generic thuộc thông tin kiểu ở nguồn, không tạo hai runtime classes riêng.

Vì vậy, **reifiable** không có nghĩa “lưu đầy đủ mọi chi tiết kiểu xuất hiện trong mã nguồn”, mà là kiểu có đủ cấu trúc runtime cần thiết theo định nghĩa ngôn ngữ. `List<?>` chỉ mô tả kiểu tham số hóa mà đối số kiểu không bị ràng buộc; runtime không cần phân biệt `String`, `Integer` hay kiểu phần tử cụ thể nào khác để kiểm tra một đối tượng là `List<?>`.

Đối chiếu với **`List<String>`**, để kiểm tra đúng nghĩa thì phải xác định cả tham số `String`. Loại kiểm tra ấy không được bảo đảm bằng phép kiểm tra runtime thông thường trên một đối tượng danh sách đã xóa kiểu.

## 2. Nhận diện nhanh các nhóm reifiable

Theo **JLS §4.7**, các nhóm reifiable thường gặp là primitive, class/interface không generic, raw type, parameterized type mà **tất cả đối số** đều là wildcard không giới hạn `?`, và mảng có component type reifiable. Kiểu lồng nhau còn cần xét các thành phần tên kiểu theo quy tắc JLS.

| Kiểu ví dụ | Reifiable? | Giải thích |
| --- | --- | --- |
| `int`, `String`, `Runnable`, `String[]` | Có | Primitive, kiểu không generic hoặc mảng có component runtime phù hợp |
| Raw `List`, `Map` | Có | Có runtime class/interface nhưng thao tác raw có thể phát cảnh báo unchecked |
| `List<?>`, `Map<?, ?>`, `List<?>[]` | Có | Wildcard không bound và kiểu thành phần reifiable |
| `List<String>`, `Map<String,Integer>` | Không | Type arguments cụ thể không được kiểm tra bởi runtime class của instance |
| `List<? extends Number>`, `List<? super Integer>` | Không | Wildcard có cận, khác `?` không giới hạn |
| `T`, `T[]`, `List<String>[]` | Không | Type variable hoặc component type non-reifiable |

Ba bẫy quan trọng: `List<? extends Object>` không thuộc nhóm unbounded wildcard như `List<?>`; `List<List<?>>` không reifiable vì type argument ngoài là `List<?>` chứ không phải một dấu `?`; và bound `<T extends Number>` **không biến T thành reifiable**.

Bảng này chỉ phục vụ nhận diện khái niệm. Bài phân loại kiểu tiếp theo triển khai chi tiết trường hợp raw/wildcard/mảng cùng runtime array component, Reflection và tác động lên API.


## 3. So sánh kiểu reifiable và non-reifiable qua `instanceof`

Giả sử dữ liệu chỉ có kiểu tĩnh là `Object`:

```java
Object value = java.util.List.of("Java", "Generics");

boolean a = value instanceof java.util.List<?>; // Hợp lệ
boolean b = value instanceof java.util.List;    // Hợp lệ, dùng raw type
// boolean c = value instanceof java.util.List<String>; // Lỗi biên dịch
```

Lời gọi `instanceof List<?>` hỏi **đối tượng có phải một `List` không?** Không phải “mọi phần tử có phải `String` không?”. `instanceof List` cũng kiểm tra được class/interface sau erasure, nhưng nên ưu tiên `List<?>` để giữ cách diễn đạt phù hợp với generic.

Một phản chứng quan trọng:

```java
Object value = java.util.List.of(10, 20, 30);

System.out.println(value instanceof java.util.List<?>); // true
```

Kết quả là `true` mặc dù các phần tử ở đây là `Integer`, hoàn toàn không phải `String`. `List<?>` không khẳng định một kiểu phần tử nào.

Dạng kiểm tra thông dụng trong mã Java 17+ là pattern matching:

```java
if (value instanceof java.util.List<?> items) {
    System.out.println("So phan tu: " + items.size());
}
```

`items` có kiểu `List<?>`; đọc một phần tử sẽ cho một giá trị dùng được dưới kiểu `Object`, và không thể thêm tùy ý `String` hoặc `Integer` qua biến này.

**Lưu ý về kiểm tra kiểu có generic:** diễn đạt “mọi lần viết `instanceof List<String>` đều lỗi trong bất kỳ ngữ cảnh nào” là quá đơn giản; Java hiện đại còn xét *cast compatibility* và kiểu tĩnh của biểu thức. Trường hợp cần ghi nhớ để kiểm tra một đối tượng chưa rõ kiểu, như `Object value` ở trên, là **không thể xác minh một đối số generic cụ thể bằng `instanceof`**. Đừng sử dụng một trường hợp compiler đã biết kiểu tĩnh để suy diễn rằng runtime có thể đọc `String` bên trong một `List`.

## 4. Vì sao `List<?>` là reifiable nhưng `List<String>` thì không?

Hai kiểu đều sử dụng interface `List` ở runtime, song yêu cầu kiểm tra khác nhau:

```text
Object value = ...

value instanceof List<?>
  -> Kiểm tra đối tượng implements List
  -> Không yêu cầu xác định kiểu phần tử

value instanceof List<String>
  -> Muốn kiểm tra cả đối số String
  -> Runtime class List không lưu đối số String riêng cho instance
  -> Không có kiểm tra runtime trực tiếp tương ứng
```

Sự khác biệt nằm ở **mức khẳng định của kiểu**. `List<?>` đưa ra yêu cầu yếu hơn: “là danh sách của một kiểu phần tử chưa biết”. JVM có thể kiểm tra phần thô `List` và đủ đáp ứng kiểm tra. Ngược lại, `List<String>` yêu cầu ràng buộc cụ thể không được lưu đầy đủ trong runtime class.

Điều này cũng giải thích tại sao `Map<?, ?>` reifiable: cả kiểu khóa và kiểu giá trị đều không được ràng buộc, nên kiểm tra runtime chỉ cần xác nhận đây là `Map`.

Không được diễn giải dấu `?` là “chấp nhận ghi mọi loại phần tử”. Trong `List<?>`, compiler coi kiểu phần tử là một kiểu chưa biết; bạn có thể đọc giá trị như `Object` nhưng **không được thêm đối tượng tùy ý** (thông thường chỉ có thể thêm `null` qua phương thức `add`). Đây là khác biệt căn bản so với raw `List`, nơi các thao tác ghi có thể tạo **unchecked warning** và heap pollution.

## 5. Mảng là ví dụ trực quan nhất về runtime type checks

Mảng Java mang thông tin **component type** ở runtime. Vì vậy mảng `String[]` có thể được kiểm tra như `String[]`, dù được giữ trong biến kiểu `Object` hoặc `Object[]`.

```java
Object value = new String[] { "An", "Binh" };

System.out.println(value instanceof String[]); // true
System.out.println(value instanceof Object[]); // true
```

Array là **covariant**, nên một `String[]` có thể được tham chiếu qua `Object[]`. Nhưng runtime vẫn biết array thực có component type `String` và có thể từ chối một thao tác ghi sai kiểu:

```java
Object[] slots = new String[1];

try {
    slots[0] = 42;
} catch (ArrayStoreException exception) {
    System.out.println("ArrayStoreException");
}
```

Kết quả là `ArrayStoreException`: `Integer` không thể lưu vào array runtime `String[]`.

Đối chiếu với generic collection:

```java
java.util.List<String> values = new java.util.ArrayList<>();
// values.add(42); // Bị compiler từ chối ngay khi có thông tin generic đúng
```

Array kiểm tra component type ở runtime; generic collection chủ yếu dựa vào kiểm tra kiểu ở nguồn. Khi chương trình dùng raw type hoặc unchecked conversion để lách generic, lỗi có thể chỉ lộ ra dưới dạng `ClassCastException` khi đọc phần tử, thay vì `ArrayStoreException` lúc ghi.

## 6. Vì sao `new List<?>[2]` được phép còn `new List<String>[2]` thì không?

Đây là hệ quả thực tế quan trọng của reifiability.

```java
// Hợp lệ:
java.util.List<?>[] groups = new java.util.List<?>[2];
groups[0] = java.util.List.of("Java");
groups[1] = java.util.List.of(17);

// Không biên dịch:
// java.util.List<String>[] strings = new java.util.List<String>[2];
```

Phần tử của `List<?>[]` có type `List<?>`, thuộc nhóm reifiable. Tại runtime, array đó có component class là **`List`**, nên mọi đối tượng thực hiện `List` đều phù hợp với kiểu phần tử của array.

Còn `List<String>` là non-reifiable. Nếu cho tạo trực tiếp array `List<String>[]`, kiểm tra gán phần tử vào array không thể xác minh đối số `String` của từng danh sách. Java từ chối **generic array creation** với kiểu thành phần như vậy để tránh tạo cảm giác an toàn kiểu sai.

Điều đáng chú ý là `List<?>[]` cho phép đặt cả `List<String>` lẫn `List<Integer>`, vì nó không ràng buộc kiểu phần tử bên trong từng list. Nó không làm các phần tử trở thành `List<Object>`, cũng không cho phép tùy ý ghi một `Integer` vào một `List<String>` thông qua tham chiếu `List<?>`.

Ngoài ra, **không tạo được `new List<String>[2]` không có nghĩa một biến khai báo `List<String>[]` tuyệt đối không bao giờ tồn tại**. Mã cũ hoặc unchecked cast có thể tạo ra các biến mang kiểu đó; chúng đòi hỏi kiểm soát heap pollution cẩn thận. Quy tắc cần nhớ ở đây là Java **cấm trực tiếp tạo array có component type non-reifiable**.

## 7. Type variable `T` có reifiable không?

Không. Cho dù có upper bound, type variable vẫn không chứa một kiểu cụ thể duy nhất tại runtime để dùng như một component type hay class literal:

```java
// Snippet: ba dòng có chú thích lỗi không thể bật lên để biên dịch.
class Container<T extends Number> {
    void inspect(Object value) {
        // if (value instanceof T) { } // Không hợp lệ
        // Class<?> type = T.class;      // Không hợp lệ
        // T[] elements = new T[10];     // Generic array creation không hợp lệ
    }
}
```

Ở tầng erasure, `T extends Number` được xóa về `Number`. Nhưng điều đó **không biến `T` thành `Number` về mặt nghĩa của kiểu tham số hóa ở nguồn**: một `Container<Integer>` vẫn muốn `T = Integer`, trong khi một `Container<Double>` dùng `T = Double`.

Nếu yêu cầu thực tế chỉ là hỏi “`value` có phải `Number` không?”, có thể viết `value instanceof Number`; nhưng câu trả lời đó không chứng minh `value` là **kiểu cụ thể `T`**.

Một cách phổ biến để kiểm tra một kiểu class cụ thể do caller cung cấp là truyền **type token**:

```java
static <T> boolean matches(Class<T> token, Object value) {
    return token.isInstance(value);
}

// matches(String.class, "Java") -> true
// matches(Integer.class, "Java") -> false
```

`Class<T>` giúp API giữ thông tin kiểu của **class cụ thể** khi caller truyền `String.class` hoặc `Integer.class`. Nhưng không thể dùng một class literal `List<String>.class` để nhận token đại diện đầy đủ cho `List<String>`; `List.class` chỉ đại diện cho raw runtime interface `List`.

Khi cần dựng `T`, thay vì `new T()` có thể yêu cầu `Supplier<T>` hoặc factory; đây là giải pháp cho vấn đề **không biết constructor/kiểu cụ thể**, không phải cách làm cho mọi kiểu generic tự nhiên trở thành reifiable.

## 8. Chương trình Java 17+ quan sát reifiable type trực tiếp

Lưu toàn bộ mã sau vào **`ReifiableTypeDemo.java`**:

```java
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ReifiableTypeDemo {
    static final class Fields {
        List<String> named;
        List<?> unknown;
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Object names = new ArrayList<String>(List.of("An", "Binh"));
        Object numbers = new ArrayList<Integer>(List.of(1, 2));
        Object map = Map.of("a", 1);

        System.out.println("List<?> runtime check: "
                + (names instanceof List<?>));
        System.out.println("Map<?, ?> runtime check: "
                + (map instanceof Map<?, ?>));
        System.out.println("Same ArrayList class: "
                + (names.getClass() == numbers.getClass()));

        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("Java");
        groups[1] = List.of(17);

        System.out.println("List<?>[] runtime check: "
                + (groups instanceof List<?>[]));
        System.out.println("Array component: "
                + groups.getClass().getComponentType().getTypeName());

        Object[] slots = new String[1];
        try {
            slots[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("Array store: ArrayStoreException");
        }

        Class<?> token = String.class;
        System.out.println("Class token checks String: "
                + token.isInstance("ok"));

        Field field = Fields.class.getDeclaredField("named");
        System.out.println("Field erased type: "
                + field.getType().getTypeName());
        System.out.println("Field generic metadata: "
                + field.getGenericType().getTypeName());

        Object mixed = List.of("Java", 42);
        System.out.println("Mixed list matches List<?>: "
                + (mixed instanceof List<?>));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ReifiableTypeDemo.java
java ReifiableTypeDemo
```

Kết quả chuẩn:

```text
List<?> runtime check: true
Map<?, ?> runtime check: true
Same ArrayList class: true
List<?>[] runtime check: true
Array component: java.util.List
Array store: ArrayStoreException
Class token checks String: true
Field erased type: java.util.List
Field generic metadata: java.util.List<java.lang.String>
Mixed list matches List<?>: true
```

Giải thích theo thứ tự:

1. `List<?>` và `Map<?, ?>` cho phép kiểm tra interface runtime mà không đòi nhận diện type argument.
2. `ArrayList<String>` và `ArrayList<Integer>` đều là `ArrayList`, nên `getClass()` bằng nhau. Đối số kiểu generic không khiến JVM tự sinh hai runtime classes.
3. `new List<?>[2]` hợp lệ; array runtime có component type là interface `java.util.List`.
4. `Object[] slots = new String[1]` giữ nguyên runtime array type `String[]`; ghi số nguyên bị từ chối bằng `ArrayStoreException`.
5. `String.class` là class token mang thông tin `String` thực sự; `Class.isInstance("ok")` kiểm tra thành công.
6. `Field.getType()` cho kiểu đã xóa `List`, còn `Field.getGenericType()` có thể đọc metadata khai báo trường `List<String>`.
7. Một danh sách có lẫn `String` và `Integer` vẫn thỏa `instanceof List<?>`; điều này minh họa rằng **reifiable không phải xác thực loại phần tử**.

Chương trình cố tình dùng `List.of("Java", 42)` trong ví dụ cuối để chứng minh phép kiểm tra `List<?>` chấp nhận danh sách có phần tử nhiều kiểu. Nó không tuyên bố đây là `List<String>`.

## 9. Reflection vẫn thấy generic: có mâu thuẫn với non-reifiable không?

Không. Java phân biệt **metadata khai báo generic** với **runtime type identity của một đối tượng**.

Trong ví dụ:

```java
class Example {
    java.util.List<String> names;
}
```

Nếu class được biên dịch với metadata `Signature` tương ứng, reflection qua `Field.getGenericType()` có thể đọc `List<String>`. Nhưng `Field.getType()` chỉ cho runtime class `List`.

Metadata cho biết **trường được khai báo** có type argument `String`. Nó không tự động bảo đảm rằng một đối tượng được đặt vào trường qua mã thiếu an toàn luôn chỉ chứa `String`. Tương tự, việc một subclass được khai báo rõ `extends Parent<String>` có thể được phản chiếu ở `getGenericSuperclass()`; không có nghĩa mọi instance của `Parent<T>` đều mang một runtime class riêng theo `T`.

Đối với một đối tượng thông thường:

```java
Object value = new java.util.ArrayList<String>();
Class<?> runtime = value.getClass(); // java.util.ArrayList
```

Bạn không thể suy ra `String` chỉ từ `runtime` theo cơ chế `getClass()` thông thường. Một `ArrayList<Integer>` cũng trả class ấy.

**Vì vậy:** một non-reifiable parameterized type có thể xuất hiện trong **metadata của khai báo**, nhưng vẫn không đủ để JVM thực hiện trực tiếp phép kiểm tra kiểu `List<String>` trên một biến `Object`.

## 10. Reifiable type, raw type, wildcard và erasure khác nhau thế nào?

Bốn khái niệm dễ gặp cùng lúc nhưng trả lời bốn câu hỏi khác nhau:

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Type erasure** | Compiler biến kiểu generic thành descriptor/kiểu đã xóa ra sao? | `List<String>` → `List`, `T` → `Object` hoặc bound |
| **Reifiable type** | JVM có đủ biểu diễn runtime để kiểm tra kiểu này không? | `String[]`, `List<?>`, `Map<?, ?>` |
| **Raw type** | Có đang dùng một class/interface generic mà không ghi type argument không? | `List`, `Map` |
| **Unbounded wildcard** | Kiểu tham số hóa có chấp nhận một type argument chưa biết không? | `List<?>`, `Map<?, ?>` |

Raw `List` là reifiable, nhưng raw type có thể gây **unchecked warnings** khi thao tác dữ liệu generic. `List<?>` cũng reifiable, đồng thời vẫn giữ quy tắc generic giúp ngăn thêm phần tử không rõ kiểu.

Điểm đáng nhớ: **reifiable không đồng nghĩa “an toàn hơn trong mọi thao tác”**. Một raw `List` reifiable mà vẫn có thể cho phép `raw.add(42)` vào một đối tượng thực chất đang được mã khác xem như `List<String>`. Ngược lại, `List<String>` non-reifiable nhưng có kiểm tra kiểu mạnh ở mã nguồn Java thông thường.

## 11. `Class<String>` có phải reifiable type không?

Đây là trường hợp thú vị: `String.class` là một biểu thức class literal hợp lệ, và **kiểu tĩnh của biểu thức** thường được trình biên dịch biểu diễn là `Class<String>`. Nhưng chính kiểu tham số hóa `Class<String>` lại **không phải** một parameterized type có toàn bộ đối số là unbounded wildcard, nên không thuộc nhóm reifiable generic type.

Điều này không mâu thuẫn: class literal `String.class` tạo/tham chiếu đối tượng `Class` mô tả **class runtime `String`**, không mô tả một runtime class riêng tên `Class<String>`. Mệnh đề `Class<String>` non-reifiable nói về việc kiểm tra nguyên cả kiểu generic `Class<String>` trên một đối tượng không rõ kiểu; nó không làm mất khả năng dùng `String.class` làm token.

Ví dụ:

```java
Class<String> stringType = String.class;
System.out.println(stringType.isInstance("text")); // true

Class<?> unknownClass = stringType; // Hợp lệ
```

Không có cú pháp class literal `List<String>.class` tương ứng để JVM biểu diễn đầy đủ một `List` có phần tử kiểu `String`. Nếu thư viện serialization cần giữ cả `List<String>`, nó thường yêu cầu `java.lang.reflect.Type`, `ParameterizedType` hoặc một cấu trúc *type token* riêng có thể giữ metadata cấp khai báo; việc kiểm tra/chuyển đổi từng phần tử vẫn phụ thuộc hợp đồng của thư viện.

## 12. Những giới hạn thực tế do kiểu non-reifiable

### 12.1. `instanceof` không thay thế kiểm tra phần tử

```java
Object value = java.util.List.of(1, 2);

// Hợp lệ:
if (value instanceof java.util.List<?> list) {
    for (Object element : list) {
        System.out.println(element);
    }
}

// Không hợp lệ nếu value có kiểu tĩnh Object:
// if (value instanceof java.util.List<String>) { ... }
```

Nếu phải xác thực một danh sách chỉ chứa `String`, cần kiểm tra thực tế các phần tử hoặc dùng đối tượng do một API đáng tin đã bảo đảm loại dữ liệu. Chỉ biết `instanceof List<?>` là chưa đủ.

### 12.2. Không tạo generic array có component type non-reifiable

```java
// Không hợp lệ:
// java.util.List<String>[] array = new java.util.List<String>[3];

// Hợp lệ:
java.util.List<?>[] array = new java.util.List<?>[3];
```

Nếu thuật toán phải chứa nhiều danh sách kiểu `String`, thường dễ giữ an toàn kiểu hơn bằng **`List<List<String>>`** thay vì cố tạo `List<String>[]`.

### 12.3. Không dùng type variable như một class runtime cụ thể

```java
// Trong một generic class:
class Sample<T> {
    // Class<?> cls = T.class;      // Không hợp lệ
    // T value = new T();           // Không hợp lệ
    // T[] values = new T[4];       // Không hợp lệ
}
```

Với các trường hợp cần tạo đối tượng, truyền `Supplier<T>` hoặc factory. Với trường hợp cần runtime class check, truyền `Class<T>` nếu `T` được đại diện bằng một class cụ thể, hoặc cơ chế `Type` có thông tin rộng hơn cho loại dữ liệu generic phức tạp.

### 12.4. Không suy ra an toàn generic từ một cast unchecked

```java
Object input = java.util.List.of(42);

// Chỉ minh họa hành vi chưa an toàn, có unchecked cast:
java.util.List<String> strings = (java.util.List<String>) input;
// String s = strings.get(0); // Có thể ném ClassCastException
```

Cast có thể thành công vì runtime chỉ kiểm tra được `List`, không kiểm tra type argument `String`. Khi cần một `String` từ collection đang chứa `Integer`, thao tác đọc lại thất bại.

Đó là lý do compiler cảnh báo **unchecked**: có một phần của cam kết generic mà runtime không chứng minh được.

## 13. Những nhầm lẫn thường gặp

**“Reifiable nghĩa là runtime lưu toàn bộ generic type argument.”** Sai. `List<?>` reifiable nhưng không lưu và xác nhận một loại phần tử cụ thể.

**“`List<String>` không reifiable nghĩa là compiler không thể kiểm tra an toàn kiểu.”** Sai. `List<String>` vẫn được compiler kiểm tra chặt chẽ; hạn chế nằm ở biểu diễn và kiểm tra runtime của kiểu parameterized đầy đủ.

**“Chỉ class không generic mới reifiable.”** Sai. Raw types, primitive types, mảng có element type reifiable và kiểu như `List<?>` hoặc `Map<?, ?>` đều có thể reifiable.

**“`List<? extends Number>` reifiable vì vẫn kiểm tra được `List`.”** Sai theo định nghĩa: đối số wildcard bị bound, không phải unbounded `?`; bản thân kiểu parameterized đầy đủ không thuộc nhóm reifiable.

**“Mọi array có generic đều bị cấm.”** Sai. `new List<?>[2]` hợp lệ; bị cấm là tạo trực tiếp array với component type non-reifiable như `List<String>`.

**“Reflection đọc được `List<String>` nên mọi instance đều biết mình là `List<String>`.”** Sai. Reflection có thể đọc metadata **khai báo** dù runtime class của một `ArrayList` không chứa đối số kiểu riêng cho từng instance.

**“`List<?>` tương đương raw `List`.”** Sai. Cả hai reifiable nhưng kiểm tra generic khi **ghi dữ liệu** rất khác nhau: `List<?>` giữ cơ chế capture type, raw type bỏ một phần bảo đảm.

**“Chỉ cần `Class<T>` thì có thể kiểm tra `List<String>` như một class runtime riêng.”** Sai. `Class<T>` phù hợp với một class cụ thể như `String`; một kiểu generic lồng với type arguments phải được mô tả và xác thực bằng cơ chế khác nếu cần.

## 14. Bài tập tự kiểm tra

**Câu 1.** `String[]` có reifiable không? Vì sao?

Có. `String` có runtime class rõ ràng và array mang runtime component type `String`.

**Câu 2.** `Map<?, ?>` có reifiable không?

Có. Cả hai đối số kiểu đều là wildcard không bound.

**Câu 3.** `List<? extends Number>` có reifiable không?

Không. Đây không phải `List<?>`; wildcard có upper bound cụ thể.

**Câu 4.** `List<?>[]` có thể tạo bằng `new List<?>[3]` không?

Có. Component type `List<?>` reifiable nên tạo array dạng này hợp lệ.

**Câu 5.** Vì sao `List<String>[]` không thể được tạo trực tiếp bằng `new List<String>[3]`?

Vì component type `List<String>` non-reifiable. Array runtime không thể kiểm tra đầy đủ type argument `String` khi lưu phần tử.

**Câu 6.** Một trường khai báo `List<String>` được reflection báo `ParameterizedType`. Điều đó có biến `List<String>` thành reifiable không?

Không. Metadata về khai báo khác với khả năng runtime kiểm tra đầy đủ kiểu của một đối tượng bất kỳ.

**Câu 7.** `Object x = List.of(42); x instanceof List<?>;` có kết quả gì?

`true`, bởi `x` là một `List`. Phép kiểm tra không yêu cầu phần tử là `String` hay bất kỳ type argument cụ thể nào.

## 15. Cách ghi nhớ và áp dụng

Hãy tự hỏi hai câu trước khi dùng một kiểu generic trong biểu thức runtime:

1. **Runtime cần kiểm tra gì?** Chỉ là đối tượng thuộc `List`, thuộc class `String`, hay còn cần chứng minh từng type argument cụ thể?
2. **Thông tin ấy nằm ở runtime object/class hay chỉ ở khai báo generic?** `String[]` có runtime component class; `List<String>` thông thường không có runtime class riêng kèm tham số `String`.

Khi chỉ cần hỏi đối tượng có phải một collection không, dùng `instanceof List<?>`. Khi cần xác nhận mỗi phần tử đúng kiểu, hãy kiểm tra từng phần tử hoặc giữ dữ liệu trong một API có hợp đồng generic an toàn. Khi cần tạo array, chọn element type reifiable hoặc cân nhắc dùng collection thay thế. Khi cần reflection, phân biệt `Class` của runtime và `Type` metadata mô tả khai báo generic.

**Kết luận:** một **reifiable type** có đủ biểu diễn tại runtime để thực hiện phép kiểm tra kiểu tương ứng. Trong Java, kiểu nguyên thủy, kiểu không generic, raw type, tham số hóa chỉ bằng wildcard không bound và array của kiểu reifiable là các nhóm quan trọng. Các kiểu như `List<String>`, `List<? extends Number>` và type variable `T` là non-reifiable. Hiểu sự khác biệt giúp giải thích chính xác các quy tắc của `instanceof`, generic array creation, type erasure, unchecked cast và reflection.