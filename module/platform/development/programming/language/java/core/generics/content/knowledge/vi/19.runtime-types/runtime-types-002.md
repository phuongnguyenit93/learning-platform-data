# Phân loại kiểu thông thường, raw type, wildcard không giới hạn và kiểu mảng ở runtime

## 1. Vì sao cần phân loại kiểu khi làm việc với Java Generics?

Java Generics kiểm tra quan hệ kiểu rất chặt ở **thời điểm biên dịch**, nhưng nhiều thông tin về tham số kiểu bị xóa (*type erasure*) khi mã nguồn chuyển thành bytecode. Vì vậy câu hỏi “Java có biết kiểu này lúc chạy không?” phải được trả lời chính xác theo **từng loại kiểu**.

Ví dụ:

```java
List<String> names = List.of("Lan", "Minh");
Object object = names;
```

Ở source, `names` có kiểu `List<String>`. Ở runtime, đối tượng `List` vẫn có class cụ thể của nó, nhưng không có một class riêng cho `List<String>` bên cạnh `List<Integer>` chỉ vì chúng dùng type argument khác nhau.

Trái lại, một mảng `String[]` vẫn giữ thành phần runtime là `String`, nên JVM có thể ngăn việc ghi `Integer` vào mảng này qua một alias `Object[]`.

Khái niệm trung tâm của bài là **reifiable type** — kiểu mà biểu diễn runtime còn đủ để dùng trong những thao tác yêu cầu kiểu có thể xác định ở runtime, theo quy tắc của Java Language Specification (JLS). Bài tập trung vào bốn nhóm trong tên đề:

1. **Kiểu thông thường**: kiểu primitive và các class/interface không generic như `int`, `String`, `Runnable`.
2. **Raw type**: tên generic được dùng không có type argument, như raw `List` hoặc `Map`.
3. **Parameterized type chỉ có wildcard không giới hạn**: ví dụ `List<?>`, `Map<?, ?>`.
4. **Kiểu mảng**: `String[]`, `int[]`, `List<?>[]`, `List<String>[]`, `T[]` và tác động của kiểu thành phần.

Sau bài này bạn sẽ biết phân loại các kiểu thành **reifiable** hay **non-reifiable**, hiểu sự khác nhau giữa `instanceof`, `Class`, Reflection `Type` và kiểm tra phần tử mảng, đồng thời giải thích được các lỗi `generic array creation` và unchecked cast.

## 2. Phải phân biệt ba mức thông tin kiểu

Một biến Java có thể liên quan đến ba lớp thông tin khác nhau:

| Mức | Ví dụ | Điều nó biểu đạt |
| --- | --- | --- |
| **Kiểu tại source (compile time)** | `List<String>` | Compiler kiểm tra các lời gọi `add`, `get`, phép gán và quan hệ generic dựa trên `String`. |
| **Kiểu/class runtime** | Đối tượng thuộc một implementation của `List` | JVM xác định class thật của đối tượng, dùng cho dispatch, `instanceof`, reflection, cast; type argument `String` không tự trở thành một class specialization. |
| **Metadata khai báo generic** | Field khai báo `List<String>` hoặc `T[]` | Class file có thể giữ Signature attribute; Reflection đọc lại *khai báo* này qua `getGenericType()`, không phải chuyên biệt hóa của từng instance. |

Ba mức đó không mâu thuẫn nhau:

```java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
```

`a` và `b` khác kiểu tại source nhưng `a.getClass() == b.getClass()` là `true`: hai đối tượng đều được tạo từ class `ArrayList` thông thường. Thông tin generic của **khai báo** vẫn có thể hiện diện ở field/method/class qua metadata, song không chứng minh runtime biết phần tử của từng `ArrayList` thuộc kiểu nào.

### 2.1. Reifiable không có nghĩa “không dùng generic”

`List<?>` là một kiểu generic với wildcard nhưng **reifiable**. Ngược lại `List<String>` là một kiểu tham số hóa có type argument cụ thể nhưng **không reifiable**.

Tính reifiable nói về **dạng thông tin runtime được Java cho phép kiểm tra**, không phải “mã này có generic hay không”, “collection đang chứa phần tử gì”, hoặc “có thể thêm mọi đối tượng hay không”.

### 2.2. Reifiable cũng không đồng nghĩa kiểm tra hết dữ liệu bên trong

Một biểu thức `object instanceof List<?>` có thể xác minh đối tượng là một `List` runtime. Nó **không** duyệt từng phần tử để xác minh cùng kiểu, và không bảo đảm collection hoàn toàn không chứa `null`.

Dù `List<?>` reifiable, Java vẫn không biết `?` đại diện cho `String`, `Integer` hay một loại tham chiếu khác ở một instance cụ thể. Vì vậy reifiable là điều kiện về **kiểu được kiểm tra**; muốn bảo đảm dữ liệu đầu vào thì còn cần hợp đồng và kiểm tra phần tử.

## 3. Danh sách các kiểu reifiable theo Java

Các nhóm reifiable cơ bản của JLS gồm:

- Kiểu class hoặc interface **không generic**, ví dụ `String`, `Number`, `Runnable`.
- Parameterized type mà **mọi** type argument là wildcard không giới hạn `?`, ví dụ `List<?>`, `Map<?, ?>`.
- **Raw type** của class/interface generic, ví dụ `List`, `Map`.
- **Primitive type**, ví dụ `int`, `boolean`, `double`.
- **Kiểu mảng** có kiểu thành phần reifiable, ví dụ `String[]`, `int[]`, `List<?>[]`, `List[][]`.
- Các dạng kiểu lồng nhau đáp ứng điều kiện reifiable của từng phần trong tên kiểu theo các quy tắc JLS.

Ngoài ra `Object`, `String[]` hay `List<?>` có thể là reifiable; type variable `T`, `List<String>` và `List<? extends Number>` **không** thuộc nhóm này.

### 3.1. Bảng phân loại cụ thể

| Kiểu viết trong Java | Reifiable? | Giải thích ngắn |
| --- | --- | --- |
| `int` | Có | Primitive có kiểu runtime xác định. |
| `boolean`, `double` | Có | Primitive. |
| `String`, `Integer`, `Object` | Có | Class thông thường, không có type parameter tại chính kiểu này. |
| `Runnable` | Có | Interface không generic. |
| `String[]`, `int[]` | Có | Thành phần reifiable, JVM biết component type. |
| `List` | Có | Raw type của `List<E>`; hợp lệ về khả năng xác định runtime nhưng không an toàn như `List<T>` có tham số kiểu. |
| `Map` | Có | Raw type. |
| `List<?>` | Có | Mọi type argument là wildcard **không giới hạn**. |
| `Map<?, ?>` | Có | Hai type argument đều là `?`. |
| `List<?>[]`, `Map<?, ?>[]` | Có | Thành phần là kiểu reifiable. |
| `List[]` | Có | Mảng của raw type `List`; có thể sinh cảnh báo `rawtypes`. |
| `List<String>` | Không | Tham số `String` bị xóa, không tạo một specialization runtime riêng. |
| `Map<String, Integer>` | Không | Các type argument cụ thể không reifiable. |
| `List<? extends Number>` | Không | Wildcard **có giới hạn**, không thuộc nhóm “mọi argument đều là wildcard không giới hạn”. |
| `List<? super Integer>` | Không | Wildcard có giới hạn dưới. |
| `T` trong `<T>` | Không | Type variable không phải một kiểu reifiable. |
| `T[]` | Không | Kiểu thành phần `T` không reifiable, dù erasure của nó có thể là `Object`. |
| `List<String>[]` | Không | Thành phần `List<String>` không reifiable. |
| `List<?>[][]` | Có | Mỗi tầng mảng có thành phần reifiable. |
| `List<String>[][]` | Không | Thành phần cuối `List<String>` không reifiable. |

Với `T extends Number`, `T` và `T[]` **vẫn không reifiable**; erasure của `T` có thể thành `Number` và erasure của `T[]` thành `Number[]`, nhưng erasure không biến một type variable thành một kiểu bạn có thể dùng trực tiếp với `new T[5]`.

### 3.2. Một wildcard giới hạn làm thay đổi kết luận

Đối chiếu:

```java
List<?> a;                      // Reifiable
List<? extends Number> b;       // Non-reifiable
List<? super Integer> c;        // Non-reifiable
Map<?, ?> d;                    // Reifiable
Map<String, ?> e;               // Non-reifiable
```

`? extends Number` có nghĩa “một subtype chưa biết của `Number`”; đây là ràng buộc compile time có ý nghĩa khác với `?` không giới hạn. Việc JVM có thể thấy `List` hoặc `Map` sau erasure không đủ để giữ toàn bộ thông tin type argument có giới hạn ở mỗi object.

## 4. Nhóm A — Kiểu class, interface và primitive thông thường

Những kiểu như:

```java
String text = "Java";
int count = 10;
Runnable action = () -> {};
```

có biểu diễn runtime tương ứng. Ví dụ:

```java
Object x = "Java";

System.out.println(x instanceof String);  // true
System.out.println(String.class.getName()); // java.lang.String
```

Một `String` thực sự là một instance class `String`, và toán tử `instanceof` kiểm tra kiểu runtime phù hợp.

Với primitive, không thể viết `x instanceof int`; `instanceof` hoạt động với **reference types** trong các dạng hợp lệ của toán tử, và primitive không là object để kiểm tra như vậy. Tuy nhiên `int.class` là class literal hợp lệ, trả về một đối tượng `Class` đại diện cho primitive `int`.

```java
System.out.println(int.class.isPrimitive()); // true
```

Cần phân biệt `int` với wrapper `Integer`: `Integer` là một class tham chiếu, có thể kiểm tra qua `instanceof Integer`, trong khi `int` là primitive. Boxing/unboxing có thể chuyển đổi giữa hai dạng trong những ngữ cảnh Java cho phép, nhưng chúng không phải một kiểu duy nhất.

### 4.1. Kiểu thông thường vẫn có thể triển khai generic API

`String` không có type parameter của chính nó, nhưng nó triển khai các interface như `Comparable<String>`. Điều đó không khiến `String` trở thành một class generic không reifiable.

Một class/interface **không generic** có thể sử dụng generic trong method hoặc implement generic interface. Phân loại reifiable cần nhìn vào **kiểu đang được hỏi**, không suy luận rằng “đã đụng Generics thì toàn bộ class không reifiable”.

## 5. Nhóm B — Raw type

Raw type xuất hiện khi bỏ toàn bộ type argument của một khai báo generic:

```java
List rawList;
Map rawMap;
```

Cả raw `List` và raw `Map` là reifiable. Điều này giải thích tại sao các thao tác liên quan runtime có thể dùng dạng raw:

```java
Object value = List.of("Java");

boolean isList = value instanceof List;    // Hợp lệ
Class<?> type = List.class;                 // Hợp lệ
```

Nhưng **reifiable không chứng minh type safety** khi dùng API generic. Raw type có thể gây cảnh báo `[rawtypes]` khi khai báo và `[unchecked]` khi gọi member bằng đối số mà compiler không thể kiểm tra.

```java
List raw = new ArrayList();
raw.add("Java");
raw.add(99); // Unchecked call có thể xảy ra
```

Khi cần nhận một danh sách bất kỳ mà chỉ đọc dữ liệu, `List<?>` thường tốt hơn:

```java
static int count(List<?> values) {
    return values.size();
}
```

`List<?>` giữ ràng buộc generic, tránh quyền ghi tùy tiện mà raw type vô tình cho phép.

### 5.1. Raw type không phải `List<Object>`

`List<Object>` là parameterized type có argument cụ thể `Object`, **không reifiable**. `List<?>` và raw `List` là reifiable nhưng có quy tắc compile time khác nhau.

```java
List<String> names = List.of("Lan");
List<?> unknown = names;             // Hợp lệ
// List<Object> objects = names;      // Không hợp lệ: generic bất biến
```

Khi viết API, chọn `List<?>` vì muốn đọc phần tử chưa biết kiểu; chọn `List<Object>` khi thật sự cần một list có thể chứa `Object` và có quyền ghi tương ứng; tránh raw `List` trong code mới trừ tương thích legacy có lý do.

### 5.2. Runtime class không phân biệt raw và parameterized instances

```java
List<String> texts = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

boolean sameClass = texts.getClass() == numbers.getClass(); // true
```

Một `ArrayList` không mang class runtime riêng cho `String` và `Integer`; generic type argument không được chuyên biệt hóa thành hai implementation class khác nhau.

`List<?>` có thể được kiểm tra runtime như một `List`, nhưng điều đó không xác định type argument nguồn. Reflection trên **khai báo** `List<?> field` có thể ghi nhận dấu `?`, điều này khác với việc một object tự lưu “tôi là List<?>”.

## 6. Nhóm C — Wildcard không giới hạn `?`

`List<?>` là một parameterized type với argument wildcard không giới hạn. Đây là một trong những ví dụ quan trọng vì nó vừa reifiable vừa giữ được nhiều quy tắc kiểm tra generics.

```java
Object value = List.of("A", 17);

if (value instanceof List<?> items) {
    System.out.println(items.size());
}
```

`instanceof List<?>` hợp lệ; pattern variable `items` được xem là một `List<?>`. Bạn có thể:

- Gọi `size`, `isEmpty`, duyệt các phần tử dưới dạng `Object`.
- Đọc phần tử: `Object element = items.get(0)`.
- Không được `items.add("text")` hay `items.add(17)`, vì compiler không biết kiểu phần tử cụ thể của danh sách được capture.
- Có thể thêm `null` theo quy tắc kiểu trong một list mutable; nhưng list thực tế có thể không hỗ trợ thêm hoặc không chấp nhận null. Ví dụ `List.of(...)` là unmodifiable.

### 6.1. Wildcard không giới hạn và `instanceof`

Cách kiểm tra từ một `Object`:

```java
Object incoming = List.of("a", "b");

if (incoming instanceof List<?> list) {
    for (Object item : list) {
        System.out.println(item);
    }
}
```

Bạn không thể dùng `incoming instanceof List<String>` trong ngữ cảnh này để kiểm tra tất cả phần tử là `String`. Với biến `Object` và Java 17, compiler từ chối phép kiểm tra kiểu tham số hóa đó vì runtime không thể xác minh argument `String`.

```java
// Với biến có kiểu Object: lỗi biên dịch trên Java 17.
// if (incoming instanceof List<String>) { ... }
```

Chi tiết cú pháp `instanceof` với một số kiểu tham số hóa đã được Java điều chỉnh qua các phiên bản ngôn ngữ, đặc biệt với quan hệ kiểu đã chứng minh được ở compile time. Điều này **không làm cho JVM bắt đầu kiểm tra type argument của một `List` runtime**. Khi cần kiểm tra dữ liệu nhận từ nguồn chưa tin cậy, `instanceof List<?>` rồi xác minh từng phần tử.

Ví dụ một hàm chấp nhận duy nhất danh sách chuỗi:

```java
static List<String> checkStrings(Object incoming) {
    if (!(incoming instanceof List<?> rawValues)) {
        throw new IllegalArgumentException("Expected a List");
    }

    List<String> result = new ArrayList<>();
    for (Object value : rawValues) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Non-String element: " + value);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
```

Đây là **đoạn method minh họa**, cần đặt trong một class và import `java.util.List`, `java.util.ArrayList`. Hàm tạo bản sao đã kiểm tra từng phần tử; `List.copyOf` từ chối null và trả list unmodifiable. Nếu contract cho phép null hoặc yêu cầu mutable, phải chọn chiến lược copy thích hợp.

### 6.2. `Class<?>` cũng là một kiểu reifiable

```java
Class<?> runtimeClass = incoming.getClass();
```

`Class<?>` chứa một wildcard không giới hạn, nên bản thân kiểu `Class<?>` reifiable. Tuy nhiên một `Class<?>` chỉ cho bạn biết runtime class của object — ví dụ implementation `List` — mà không tự suy ra type argument `String` của một biến source đã bị erase.

Một `Class<String>` có type argument cụ thể, nên không phải kiểu reifiable theo quy tắc tổng quát cho parameterized types. Dù có thể viết `String.class` và gán cho `Class<String>` nhờ chữ ký API của class literal, đừng kết luận điều đó tạo nên một runtime class riêng đại diện cho *tham số hóa của `Class`*.

## 7. Nhóm D — Mảng: kiểu thành phần tồn tại ở runtime

Java mảng là object và JVM giữ một **runtime component type** xác định. Ví dụ:

```java
String[] names = new String[2];

System.out.println(names.getClass().isArray());               // true
System.out.println(names.getClass().getComponentType());      // class java.lang.String
System.out.println(names instanceof String[]);                // true
```

Mảng còn có đặc tính **covariance**:

```java
String[] strings = new String[1];
Object[] objects = strings;     // Hợp lệ
```

Dù tham chiếu `objects` có kiểu tĩnh là `Object[]`, đối tượng thực vẫn là `String[]`. Nếu ghi sai kiểu:

```java
objects[0] = 42; // ArrayStoreException lúc chạy
```

JVM có đủ thông tin runtime để ngăn `Integer` bị ghi vào mảng có component type `String`.

### 7.1. Mảng của kiểu reifiable

| Cách tạo | Hợp lệ? | Runtime component type |
| --- | --- | --- |
| `new int[3]` | Có | `int` |
| `new String[3]` | Có | `String` |
| `new Object[3]` | Có | `Object` |
| `new List[3]` | Có, raw-type warning có thể xuất hiện | `List` |
| `new List<?>[3]` | Có | `List` |
| `new Map<?, ?>[3]` | Có | `Map` |
| `new List<String>[3]` | Không | Component `List<String>` không reifiable. |
| `new List<? extends Number>[3]` | Không | Component không reifiable do wildcard có giới hạn. |
| `new T[3]` trong method `<T>` | Không | `T` là type variable không reifiable. |

Từ góc nhìn runtime, mảng được tạo bằng `new List<?>[3]` vẫn là mảng có component class `List`. Điều này giải thích tại sao một `List<?>[]` có thể chứa một `List<String>` và một `List<Integer>` ở hai phần tử khác nhau mà không có kiểm tra wildcard argument riêng tại runtime.

### 7.2. Mảng wildcard và raw array có cùng runtime class

```java
List<?>[] wildcardArray = new List<?>[2];
List[] rawArray = new List[2];

boolean sameRuntimeClass =
        wildcardArray.getClass() == rawArray.getClass(); // true
```

Ở source, `List<?>[]` giữ nhiều ràng buộc generic hơn raw `List[]`. Nhưng kiểu phần tử runtime của cả hai là `List`, nên chúng dùng cùng array class. Có thể kiểm tra bằng:

```java
wildcardArray.getClass().getComponentType() == List.class
```

Mỗi ô của `wildcardArray` chỉ được JVM kiểm tra xem object được ghi có là một `List` phù hợp hay không. Nó không có cách xác minh type argument của phần tử list như `String` hay `Integer`.

### 7.3. Vì sao `new List<String>[2]` bị cấm?

Giả sử Java cho phép một mảng như thế:

```java
// Đây là giả định không hợp lệ ở Java:
List<String>[] strings = new List<String>[2];
Object[] objects = strings;
objects[0] = List.of(42);
String first = strings[0].get(0);
```

Do generic argument `String` không được kiểm tra ở runtime, việc ghi `List<Integer>` vào array class chỉ có component raw `List` sẽ không bị array store check chặn theo generic argument. Sau đó đoạn đọc `String` có thể ném `ClassCastException`.

Vì vậy Java **cấm trực tiếp cấp phát** mảng có component là `List<String>` (một loại không reifiable). Cấm tạo không đồng nghĩa kiểu khai báo hoàn toàn bị cấm:

```java
List<String>[] reference; // Khai báo biến được phép
```

Nhưng `new List<String>[2]` vẫn là lỗi `generic array creation`. Các phép cast unchecked có thể khiến giá trị kiểu này xuất hiện qua API cũ, và cần tránh giả định chúng an toàn.

### 7.4. `T[]` với type variable vẫn là trường hợp đặc biệt

Trong một class generic:

```java
class Buffer<T> {
    T[] data;

    // T[] create(int size) {
    //     return new T[size]; // Lỗi: generic array creation
    // }
}
```

Khi `T` không bound, erasure của nó là `Object`; với `<T extends Number>`, erasure là `Number`. Nhưng class không biết runtime component class cụ thể mà caller muốn, nên compiler không cho cấp phát `new T[size]`.

Một cách nhận mảng đúng type là **factory**:

```java
static <T> T[] create(int size, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(size);
}

// String[] names = create(3, String[]::new);
```

Đoạn trên là method minh họa cần đặt trong một class. Bên gọi cung cấp mảng có component thật `String`. Cách khác dùng `Array.newInstance` với type token `Class<T>`, nhưng cast sang `T[]` cần được đóng gói cẩn thận và có thể sinh unchecked warning.

### 7.5. Reifiable array vẫn có thể gây ArrayStoreException

Tính reifiable giúp array runtime biết component class; nó **không chứng minh mọi lệnh ghi vào alias đều an toàn**. Cú pháp `Object[] alias = new String[1]` cho phép alias rộng hơn, nhưng runtime có store check.

Đồng thời `List<?>[]` reifiable không ngăn bạn tạo alias rồi ghi một **List có kiểu phần tử khác**: tất cả đều là `List` theo component runtime. Nếu thiết kế cần một tập các `List<String>` thực sự an toàn, cân nhắc `List<List<String>>` hoặc kiểm tra element/nested element khi xây dữ liệu.

## 8. Reflection: kiểu sau erasure và generic declaration

`java.lang.reflect.Field` có hai API dễ bị nhầm:

```java
field.getType()        // Class<?> của kiểu field ở runtime, sau erasure
field.getGenericType() // java.lang.reflect.Type từ khai báo generic, nếu có
```

Nếu một field khai báo `List<String>`, `getType()` cho biết raw `List`, còn `getGenericType()` có thể trả một `ParameterizedType` đại diện cho `List<String>` từ Signature metadata. Điều này mô tả **kiểu đã khai báo cho field**, không xác minh rằng các phần tử của một object được gán vào field đúng kiểu.

### 8.1. Ví dụ đối chiếu các field

```java
static final class Examples<T> {
    String plain;
    List raw;
    List<?> unknown;
    List<String> names;
    String[] plainArray;
    List<?>[] wildcardArray;
    List<String>[] parameterizedArray;
    T element;
    T[] variableArray;
}
```

Đây là một lớp lồng được đưa vào chương trình hoàn chỉnh bên dưới. Khi duyệt từng field bằng `getType()` và `getGenericType()`:

| Khai báo field | `getType()` biểu diễn | `getGenericType()` biểu diễn |
| --- | --- | --- |
| `String plain` | `String` | `String` |
| `List raw` | `List` | `List` |
| `List<?> unknown` | `List` | `List<?>` |
| `List<String> names` | `List` | `List<String>` |
| `String[] plainArray` | `String[]` | `String[]` |
| `List<?>[] wildcardArray` | `List[]` | `List<?>[]` |
| `List<String>[] parameterizedArray` | `List[]` | `List<String>[]` |
| `T element` | `Object` nếu `T` không bound | `T` |
| `T[] variableArray` | `Object[]` nếu `T` không bound | `T[]` |

Với một method generic, tương tự có `getParameterTypes()`/`getGenericParameterTypes()` và `getReturnType()`/`getGenericReturnType()`. Đó là thông tin hữu ích cho framework phân tích API nhưng không thay thế việc xác minh dữ liệu runtime.

### 8.2. `Type` có nhiều dạng

Một `Type` từ `getGenericType()` có thể là:

- `Class<?>` cho kiểu thông thường hoặc raw/array class thích hợp.
- `ParameterizedType` cho khai báo như `List<String>` hoặc `List<?>`.
- `TypeVariable<?>` cho `T`.
- `GenericArrayType` cho các mảng chứa thành phần generic không thể biểu diễn trực tiếp như một `Class` tương ứng, ví dụ `T[]` hoặc `List<String>[]`.
- `WildcardType` khi đi vào type argument wildcard của một `ParameterizedType`.

Đừng dùng cách ép `(Class<?>) field.getGenericType()` cho mọi field: nó có thể ném `ClassCastException` khi thực tế là `ParameterizedType` hoặc `GenericArrayType`. Khi làm framework, kiểm tra `instanceof` từng nhánh của `Type` và xem bound/type arguments với API tương ứng.

### 8.3. Metadata không biến thành validation runtime

Giả sử field khai báo `List<String> names`, Reflection trả `ParameterizedType` có argument `String`, nhưng một raw alias có thể làm nhiễm phần tử sai kiểu vào list được gán. Khi đó metadata vẫn nói đúng rằng **field đã được khai báo** là `List<String>` — nó không kiểm tra mọi phần tử hiện có.

Nếu cần nhận dữ liệu từ JSON, JDBC hoặc legacy API, bạn phải dùng parser, schema hoặc kiểm tra từng phần tử đúng với cấu trúc generic mong đợi. Chỉ đọc `getGenericType()` không làm dữ liệu tự type-safe.

## 9. Chương trình Java 17 hoàn chỉnh để tự phân loại

Tệp **`ReifiableTypesDemo.java`** sau kết hợp `instanceof List<?>`, mảng wildcard/raw, runtime component check và Reflection. Bản thân nó cố ý chứa hai chỗ raw type để so sánh, nên khi bật `-Xlint:rawtypes` sẽ có cảnh báo; các cảnh báo đó là một phần của minh họa.

```java
import java.lang.reflect.Field;
import java.util.List;

public class ReifiableTypesDemo {
    static final class Examples<T> {
        String plain;
        List raw;
        List<?> unknown;
        List<String> names;
        String[] plainArray;
        List<?>[] wildcardArray;
        List<String>[] parameterizedArray;
        T element;
        T[] variableArray;
    }

    public static void main(String[] args) throws Exception {
        Object mixed = List.of("Java", 17);
        System.out.println("instanceof-List<?>=" + (mixed instanceof List<?>));

        List<?>[] wildcardArray = new List<?>[2];
        wildcardArray[0] = List.of("Java");
        wildcardArray[1] = List.of(17);
        List[] rawArray = new List[2];
        System.out.println("same-array-class="
                + (wildcardArray.getClass() == rawArray.getClass()));
        System.out.println("array-component="
                + wildcardArray.getClass().getComponentType().getTypeName());
        System.out.println("elements="
                + wildcardArray[0].get(0) + "," + wildcardArray[1].get(0));

        Object[] alias = new String[1];
        try {
            alias[0] = 99;
        } catch (ArrayStoreException e) {
            System.out.println("store-check=" + e.getClass().getSimpleName());
        }

        String[] fields = {"plain", "raw", "unknown", "names", "plainArray",
                "wildcardArray", "parameterizedArray", "element", "variableArray"};
        for (String name : fields) {
            Field field = Examples.class.getDeclaredField(name);
            System.out.println(name + ": raw=" + field.getType().getTypeName()
                    + "; generic=" + field.getGenericType().getTypeName());
        }
    }
}
```

Biên dịch bằng Java 17 hoặc JDK hỗ trợ `--release 17`:

```bash
javac --release 17 -Xlint:rawtypes ReifiableTypesDemo.java
java ReifiableTypesDemo
```

Compiler phát **3 cảnh báo `rawtypes`** với source trên: một ở field `List raw`, hai ở dòng `List[] rawArray = new List[2]` (tại cả khai báo và biểu thức tạo mảng). Chúng là cảnh báo, không phải lỗi biên dịch.

Stdout chính xác của chương trình:

```text
instanceof-List<?>=true
same-array-class=true
array-component=java.util.List
elements=Java,17
store-check=ArrayStoreException
plain: raw=java.lang.String; generic=java.lang.String
raw: raw=java.util.List; generic=java.util.List
unknown: raw=java.util.List; generic=java.util.List<?>
names: raw=java.util.List; generic=java.util.List<java.lang.String>
plainArray: raw=java.lang.String[]; generic=java.lang.String[]
wildcardArray: raw=java.util.List[]; generic=java.util.List<?>[]
parameterizedArray: raw=java.util.List[]; generic=java.util.List<java.lang.String>[]
element: raw=java.lang.Object; generic=T
variableArray: raw=java.lang.Object[]; generic=T[]
```

Đọc ba nhóm kết quả:

- `instanceof-List<?>=true` chỉ xác nhận `mixed` là một `List`, không kiểm tra đồng nhất kiểu phần tử.
- `same-array-class=true`, `array-component=java.util.List` cho thấy cả mảng raw và mảng wildcard có thành phần runtime là `List`.
- `getType()` cho các field generic là kiểu đã xóa (`List`, `Object`, `Object[]`), trong khi `getGenericType()` hiển thị khai báo có `?`, `String`, `T` từ metadata.

Dòng `store-check=ArrayStoreException` chứng minh một `String[]` có component runtime `String` dù alias của nó là `Object[]`: JVM kiểm tra phần tử được ghi vào.

## 10. Các lỗi biên dịch dự kiến khi dùng kiểu không reifiable

Đây là **đoạn mã cố tình sai**, chỉ dùng để quan sát diagnostic. Không đặt chung với chương trình chạy thành công phía trên.

Tệp **`InvalidReifiable.java`**:

```java
import java.util.List;

class InvalidReifiable {
    static <T> void run(Object x) {
        List<String>[] a = new List<String>[2];
        T[] b = new T[2];
        if (x instanceof List<String>) {
            System.out.println(x);
        }
    }
}
```

Biên dịch:

```bash
javac --release 17 InvalidReifiable.java
```

Compiler từ chối ba chỗ:

```text
error: generic array creation
    List<String>[] a = new List<String>[2];

error: generic array creation
    T[] b = new T[2];

error: Object cannot be safely cast to List<String>
    if (x instanceof List<String>) {
```

Giải thích:

1. `List<String>` không reifiable nên không được làm component cho biểu thức `new List<String>[2]`.
2. `T` là type variable không reifiable nên không cấp phát `new T[2]`.
3. Từ một giá trị tĩnh kiểu `Object`, JVM không có cách kiểm tra đầy đủ type argument `String` của một `List` bằng `instanceof List<String>`.

Đừng “sửa” thành unchecked cast `List<String>[] a = (List<String>[]) new List<?>[2]` mà không có invariant chứng minh. Cast ấy không làm JVM biết `String` trong component type và có thể dẫn tới heap pollution.

## 11. Cách sử dụng kiểu reifiable trong một số API

### 11.1. Với `instanceof`

Dùng kiểm tra kiểu có thể xác định ở runtime:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}

if (value instanceof List<?> elements) {
    System.out.println(elements.size());
}
```

Với array:

```java
if (value instanceof String[] words) {
    System.out.println(words.length);
}
```

Các ví dụ là **mảnh code để đặt trong method**, với `value` có kiểu tham chiếu thích hợp và import `java.util.List`. Nếu muốn phân loại chi tiết hơn một `List<?>`, cần kiểm tra phần tử hoặc dùng metadata/protocol từ nguồn dữ liệu.

### 11.2. Với `Class` object và reflection

Một `Class<?>` có thể mô tả `String.class`, `List.class` hoặc `String[].class`. Nhưng không có class literal `List<String>.class` đại diện cho một specialization runtime của list.

```java
Class<?> stringClass = String.class;
Class<?> listClass = List.class;
Class<?> arrayClass = String[].class;
```

Nếu một framework cần giữ **cả cây kiểu** `List<String>` hoặc `Map<String,List<Integer>>`, nó cần một `Type`, `ParameterizedType`, hoặc cơ chế *type token* dựa trên khai báo generic. Việc đó phục vụ mô tả/giải mã kiểu; bản thân `Class` object của một `ArrayList` đã tạo vẫn không tự ghi nhớ tham số kiểu của biến source.

### 11.3. Với mảng và generic varargs

Varargs trong bytecode dựa trên mảng. Một method như:

```java
static <T> void examine(List<T>... lists) {
    // ...
}
```

có component generic không reifiable nên có thể xuất hiện warning về heap pollution hoặc unchecked array creation. Không nên gắn `@SafeVarargs` chỉ để im compiler: annotation là lời cam kết về cách method sử dụng mảng, không làm kiểu `List<T>` reifiable.

Khi chỉ cần giữ nhiều danh sách cùng loại, cân nhắc collection lồng nhau:

```java
List<List<String>> groups = new ArrayList<>();
groups.add(List.of("a", "b"));
```

Điều này loại bỏ nhu cầu tạo một `List<String>[]` trực tiếp. Nhưng một `List<List<String>>` vẫn không phải kiểu reifiable khi xét toàn bộ type arguments; tính an toàn của nó đến từ kiểm tra generic ở compile time và việc kiểm soát dữ liệu, không phải có `List<List<String>>` class riêng ở runtime.

## 12. Các ngộ nhận và lỗi thường gặp

### 12.1. “Raw type reifiable nghĩa là raw type tốt cho type safety”

Sai. Raw `List` reifiable về **hình dạng runtime** nhưng bỏ type argument khỏi kiểm tra compile time, cho phép unchecked operation. Chọn `List<?>` khi cần nhận list không biết kiểu phần tử và không cần thêm phần tử tùy ý.

### 12.2. “`List<?>` reifiable nghĩa là biết kiểu các phần tử”

Sai. `?` chính là một kiểu chưa biết. JVM nhận diện được `List` nhưng không suy ra một type argument cụ thể. Nếu cần `List<String>`, hãy kiểm tra từng phần tử rồi tạo một danh sách có hợp đồng rõ ràng.

### 12.3. “`List<String>` không reifiable nghĩa là không được khai báo biến này”

Sai. `List<String>` là nền tảng generic type safety khi biên dịch. Bạn hoàn toàn có thể khai báo `List<String>` hoặc method trả `List<String>`, chỉ không thể dùng một số thao tác runtime yêu cầu reifiable type như `new List<String>[n]` và một số dạng runtime type check.

### 12.4. “Mảng chỉ là list cũ nên JVM không biết kiểu phần tử”

Sai. Mảng có component class runtime. `String[]` bảo vệ việc ghi nhầm bằng `ArrayStoreException`. Tuy vậy mảng có component `List` không biết type argument của **từng list bên trong**.

### 12.5. “`T extends Number` làm `T` reifiable”

Sai. Bound cho compiler biết phép toán nào được phép trên `T` và quyết định erasure; nó không tạo `Class<T>` runtime mới cho type variable. `new T[n]` vẫn không hợp lệ. Dùng factory hoặc class token nếu cần cấp phát.

### 12.6. “Reflection đọc ra `List<String>` nên JVM kiểm tra element type ở runtime”

Sai. `Field.getGenericType()` đọc khai báo generic từ class metadata. Nếu dữ liệu bị ghi sai qua raw alias hoặc được nạp từ nguồn bên ngoài không kiểm tra, metadata ấy vẫn tồn tại mà các phần tử có thể sai kiểu.

### 12.7. “`List<?>[]` và `List[]` cùng class nên phải dùng raw type”

Sai. Hai kiểu có thể cùng array class runtime nhưng có **quy tắc kiểm tra source khác nhau**. Dùng `List<?>[]` diễn đạt rằng phần tử là các List không biết generic argument; raw `List[]` bỏ nhiều kiểm tra và có thể tạo warning.

### 12.8. “Erasure biến runtime `String[]` thành `Object[]`”

Sai. Erasure áp dụng cho **biểu diễn generic của chữ ký**, không tự động đổi component runtime của object array đã được tạo. Với `<T> T[] echo(T[] array)`, descriptor có thể dùng `Object[]`, song nếu bên gọi truyền `String[]`, đối tượng vẫn là một `String[]` thật.

## 13. Checklist phân loại khi đọc code hoặc sửa lỗi

Với bất kỳ kiểu nghi vấn nào, làm theo thứ tự:

1. **Xem cấu trúc kiểu:** primitive, class/interface không generic, raw type, parameterized type, type variable hay array?
2. Nếu là parameterized type, **mọi argument có đúng là `?` không giới hạn?** Nếu có, đó là trường hợp reifiable; nếu có `String`, `? extends Number` hay `? super Integer`, không.
3. Nếu là array, **phân loại component type** trước rồi lặp lại quy tắc theo từng chiều; `List<?>[]` reifiable, `List<String>[]` không.
4. Nếu là `T`, **đừng nhầm erasure với reifiability**. Bound chỉ cho biết kiểu thay thế của `T` trong erasure, không làm `T` trở thành một class runtime cụ thể.
5. Nếu cần `instanceof` hoặc cấp phát array, kiểm tra quy tắc ngôn ngữ cho biểu thức đó trước khi viết code.
6. Nếu xem Reflection, **tách `Class<?>` runtime khỏi `Type`/Signature metadata**.
7. Nếu chuyển dữ liệu generic từ nguồn bên ngoài, **kiểm tra từng phần tử** hoặc dùng parser/schema rõ ràng khi cần hợp đồng chặt hơn.
8. Nếu gặp unchecked cast, raw alias hay generic array creation, ưu tiên sửa thiết kế API và bảo toàn thông tin kiểu từ nguồn đến đích.

Bảng tra nhanh:

| Nhu cầu | Kiểu/API nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Chỉ cần biết một object có phải `List` | `instanceof List<?>` | Không chứng minh phần tử là `String`. |
| Nhận mọi danh sách để đọc | `List<?>` | Tránh raw type khi không cần khả năng ghi. |
| Lưu danh sách chuỗi có kiểm tra compile time | `List<String>` | Non-reifiable không làm mất giá trị type safety. |
| Mảng chuỗi thật ở runtime | `String[]` | Store check có thể gây `ArrayStoreException` khi ghi sai. |
| Mảng các list chưa rõ type argument | `List<?>[]` | Runtime chỉ kiểm tra phần tử là `List`. |
| Cần tạo mảng `T[]` | `IntFunction<T[]>`, array factory | Bên gọi tạo mảng có component runtime mong muốn. |
| Cần đọc khai báo generic của field | `Field.getGenericType()` | Là metadata khai báo, không validate instance data. |
| Cần đọc class thực hoặc component array | `getClass()`, `getComponentType()` | Thấy erasure của generic và component class runtime. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Trong bốn kiểu `List`, `List<?>`, `List<String>` và `List<? extends Number>`, kiểu nào reifiable?

<details>
<summary>Đáp án</summary>

Raw `List` và `List<?>` reifiable. `List<String>` không reifiable vì có argument cụ thể; `List<? extends Number>` không reifiable vì wildcard bị giới hạn.

</details>

**Câu 2.** `new List<?>[2]` và `new List<String>[2]` khác nhau ở đâu?

<details>
<summary>Đáp án</summary>

`List<?>` reifiable nên có thể làm component của array creation; JVM dùng component runtime `List`. `List<String>` không reifiable, nên biểu thức `new List<String>[2]` bị từ chối với lỗi `generic array creation`.

</details>

**Câu 3.** Vì sao `String[]` có thể ném `ArrayStoreException` khi tham chiếu là `Object[]`?

<details>
<summary>Đáp án</summary>

Mảng là covariant; `Object[]` có thể trỏ tới một `String[]`. JVM giữ component runtime là `String`, do đó từ chối ghi `Integer` vào mảng dù kiểu tĩnh của alias là `Object[]`.

</details>

**Câu 4.** `Field.getGenericType()` trả `java.util.List<java.lang.String>`. Điều đó có xác nhận danh sách hiện tại chỉ chứa `String` không?

<details>
<summary>Đáp án</summary>

Không. Nó mô tả kiểu khai báo của field qua generic Signature metadata. Nội dung hiện tại vẫn có thể bị heap pollution nếu code dùng raw type, unchecked cast hoặc nguồn dữ liệu không được kiểm tra.

</details>

**Câu 5.** Với `<T extends Number>`, vì sao không tạo `new T[5]` ngay trong generic method dù `T` có erasure là `Number`?

<details>
<summary>Đáp án</summary>

`T` vẫn là type variable không reifiable. Erasure về `Number` không cho biết caller cần `Integer[]`, `Double[]` hay một subtype array nào khác. Dùng `IntFunction<T[]>` hoặc cơ chế cấp phát có runtime component type cụ thể khi cần mảng.

</details>

**Câu 6.** `List<?>[]` và `List[]` có thể cùng runtime class không? Nếu có, nên dùng kiểu nào trong code mới?

<details>
<summary>Đáp án</summary>

Có: mảng runtime của cả hai có component `List`. Trong code mới, `List<?>[]` thường có hợp đồng compile time rõ hơn nếu các phần tử là List có type argument chưa biết; raw `List[]` có thể phát sinh `rawtypes`/`unchecked` warnings.

</details>

## 15. Ghi nhớ trọng tâm

Một kiểu **reifiable** là kiểu có biểu diễn runtime phù hợp với các thao tác cần xác định kiểu ở runtime. Các nhóm chính là primitive, class/interface không generic, raw type, parameterized type chỉ chứa wildcard **không giới hạn**, và array có component reifiable.

`List<String>` có giá trị lớn ở compile time dù non-reifiable; `List<?>` reifiable nhưng không cho biết type argument cụ thể; raw `List` reifiable nhưng có thể làm mất kiểm tra generic; `String[]` reifiable và được JVM kiểm tra component khi ghi, còn `List<String>[]` không thể cấp phát trực tiếp.

Khi debug, hãy luôn tách **kiểu khai báo ở source**, **class/array component thực sự tại runtime** và **metadata generic mà Reflection đọc được**. Sự phân biệt này giúp bạn chọn đúng `instanceof`, tránh mảng generic không hợp lệ, và thiết kế các ranh giới kiểm tra dữ liệu type-safe.