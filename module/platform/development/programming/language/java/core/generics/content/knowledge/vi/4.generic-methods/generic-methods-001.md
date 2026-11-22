# Khai báo `<T>` trước kiểu trả về trong phương thức generic Java

Phương thức generic (*generic method*) là phương thức **tự khai báo một hoặc nhiều tham số kiểu**, nhờ vậy cùng một cách cài đặt có thể áp dụng với nhiều kiểu dữ liệu mà vẫn giữ thông tin kiểu ở thời điểm biên dịch. Dấu hiệu cú pháp quan trọng nhất là phần khai báo `<T>` **đặt sau các modifier và trước kiểu trả về**:

```java
public static <T> T identity(T value) {
    return value;
}
```

Trong chữ ký trên, `<T>` là **nơi khai báo** tham số kiểu `T`; chữ `T` tiếp theo là **kiểu trả về**, còn `T value` là **kiểu của tham số đầu vào**. Không có hai kiểu `T` khác nhau: cùng một ký hiệu mô tả mối liên hệ giữa đầu vào và đầu ra của một lời gọi.

## 1. Đọc cú pháp từng thành phần

Khuôn dạng phổ biến của một phương thức generic có thân:

```java
[modifiers] <TypeParameters> ReturnType methodName(Parameters)
        [throws Exceptions] {
    // Thân phương thức
}
```

Các dấu ngoặc vuông ở đây chỉ là ký hiệu **mô tả phần tùy chọn**, không phải cú pháp Java có thể sao chép nguyên xi. Trong mã thực:

```java
public static <T> T identity(T value) {
    return value;
}
```

| Thành phần | Ý nghĩa |
|---|---|
| `public static` | Modifier: phạm vi truy cập và tính chất static |
| `<T>` | Khai báo tham số kiểu thuộc **chính phương thức** |
| `T` sau `<T>` | Kiểu trả về; ở đây phương thức trả về giá trị thuộc kiểu được suy luận cho `T` |
| `identity` | Tên phương thức |
| `T value` | Tham số có kiểu `T` và tên biến `value` |
| `return value;` | Trả lại đúng giá trị đầu vào, nên phù hợp với kiểu trả về `T` |

Khi người gọi truyền một `String`, trình biên dịch có thể suy luận `T = String` cho lời gọi đó; khi truyền `Integer`, `T` có thể là `Integer` cho lời gọi khác. Bạn **không phải viết một phương thức riêng** cho từng kiểu.

Ví dụ cách gọi (các dòng này cần nằm trong một method và nhìn thấy `identity`):

```java
String text = identity("Java");
Integer count = identity(10);
```

Hai phép gán đều được kiểm tra kiểu; không cần cast từ `Object`. Literal `10` có kiểu primitive `int`, nhưng tham số kiểu Java generics là kiểu tham chiếu: autoboxing cho phép suy luận `Integer`.

**Quy tắc nhận diện:** nếu dấu `<...>` trong một khai báo phương thức đứng **trước kiểu trả về**, đó thường là phần khai báo type parameter của chính phương thức. Nếu `<...>` đứng sau tên lớp lúc khai báo `class Box<T>`, nó thuộc lớp. Còn `List<String>` ở kiểu trả về hoặc tham số là một **parameterized type sử dụng type argument**, không phải đang khai báo một tên `T` mới.

## 2. Vì sao `<T>` phải đứng trước kiểu trả về?

Java cần biết `T` là **tên kiểu được khai báo** trước khi bạn sử dụng nó trong kiểu trả về hoặc danh sách tham số. Đặt type parameter list ở vị trí đúng giúp trình biên dịch phân biệt khai báo generic method với phương thức thông thường.

Cú pháp hợp lệ:

```java
static <T> T id(T input) {
    return input;
}

public <T> void print(T input) {
    System.out.println(input);
}

private static <T> java.util.List<T> one(T input) {
    return java.util.List.of(input);
}
```

Đây là **các phương thức minh họa**, cần được đặt trong một class. Ba biến thể minh họa ba tình huống:

1. `static <T> T id(...)` trả về chính kiểu `T`.
2. `public <T> void print(...)` khai báo `T` dù kiểu trả về là `void`; type parameter **không buộc** phải xuất hiện ở kết quả.
3. `private static <T> List<T> one(...)` dùng kiểu trả về có chứa `T`. Phần khai báo `<T>` vẫn đứng trước toàn bộ `List<T>`.

Cách viết **không hợp lệ**:

```java
// static T <T> id(T input) { return input; }
// Sai thứ tự: <T> không thể đặt sau kiểu trả về.

// static T id(T input) { return input; }
// Sai nếu không có khai báo T trong phạm vi phù hợp.

// static T id<T>(T input) { return input; }
// Java không khai báo type parameter của method sau tên method.
```

Đoạn trên chỉ là **ví dụ lỗi được comment**, không phải tệp chương trình chạy độc lập. Ở một ngôn ngữ khác, cú pháp tương tự `methodName<T>` có thể là cú pháp khai báo generic; Java dùng vị trí riêng của nó là `<T>` trước kiểu trả về.

### Vị trí của annotation và modifier

Thông thường modifier xuất hiện trước phần khai báo tham số kiểu:

```java
public final <T> T convert(T value) {
    return value;
}
```

Trong class không phải `final`, phương thức instance `final` này có thể khai báo `<T>` và trả về `T`. Nếu có chú thích như `@Deprecated`, nó cũng thuộc phần khai báo/phương thức và đứng trước phần cú pháp phương thức phù hợp:

```java
@Deprecated
public static <T> T oldIdentity(T value) {
    return value;
}
```

Không cần thêm `extends Object` sau mọi `T`; nếu không ghi bound, `Object` là upper bound ngầm định theo ngữ nghĩa erasure.

## 3. Type parameter khác return type và type argument như thế nào?

Ba vai trò rất dễ lẫn khi bắt đầu học:

- **Type parameter declaration:** `<T>` trong `static <T> T id(T input)`; đây là **khai báo tên kiểu** cho method.
- **Return type:** `T` ngay sau `<T>`; đây là **nơi dùng** tên kiểu đã khai báo để mô tả kiểu của kết quả.
- **Type argument:** `<String>` ở lời gọi có chỉ rõ tham số kiểu như `Demo.<String>id("hi")`; đây là **giá trị kiểu được chọn cho tham số `T`**, không phải khai báo tên mới.

Phân biệt hai chữ ký:

```java
static <T> T echo(T x) {
    return x;
}

static String literal() {
    return "fixed";
}
```

`echo` là generic method vì nó **tự khai báo** `<T>`. `literal` không phải generic method vì không khai báo type parameter, dù kiểu trả về của nó là kiểu tham chiếu `String`.

Chữ ký sau dùng generic class chuẩn nhưng **không tự khai báo type parameter của method**:

```java
static java.util.List<String> words() {
    return java.util.List.of("a", "b");
}
```

Đây là method thông thường, có kiểu trả về là **parameterized type `List<String>`**. Ngược lại, `static <T> List<T> singleton(T value)` là generic method vì method có phần khai báo `<T>`.

Một phương thức generic cũng có thể trả về kiểu cố định:

```java
static <T> int sizeOf(java.util.List<T> items) {
    return items.size();
}
```

`sizeOf` vẫn là generic method dù trả về `int`. Ở các thiết kế khác, nếu `T` không tạo thêm quan hệ kiểu cần thiết, có thể đơn giản hóa thành `int sizeOf(List<?> items)`; đó là quyết định thiết kế API, không phải giới hạn cú pháp.

## 4. Ví dụ Java 17 chạy độc lập: static, instance và nhiều tham số kiểu

Lưu toàn bộ chương trình sau vào tệp **`GenericMethodDeclarationDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class GenericMethodDeclarationDemo {

    static <T> T identity(T value) {
        return value;
    }

    static <T> void display(T value) {
        System.out.println("display: " + value);
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    static <A, B> Map.Entry<A, B> pair(A left, B right) {
        return Map.entry(left, right);
    }

    static <T extends Number> double twice(T number) {
        return number.doubleValue() * 2;
    }

    static <T> List<T> duplicate(T value) {
        return List.of(value, value);
    }

    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <U> U echo(U input) {
            return input;
        }

        static <V> V echoStatic(V input) {
            return input;
        }
    }

    public static void main(String[] args) {
        String word = identity("Java");
        System.out.println("identity: " + word);

        Integer number =
                GenericMethodDeclarationDemo.<Integer>identity(7);
        System.out.println("explicit: " + number);

        display(3.5);
        System.out.println("first: " + first(List.of("red", "blue")));

        Map.Entry<String, Integer> entry = pair("age", 36);
        System.out.println("pair: " + entry.getKey()
                + "=" + entry.getValue());

        System.out.println("twice: " + twice(4));
        System.out.println("duplicate: " + duplicate("Hi"));

        Holder<String> holder = new Holder<>("box");
        System.out.println("holder: " + holder.get());
        System.out.println("instance generic: " + holder.echo(42));
        System.out.println("static generic: " + Holder.echoStatic(true));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac GenericMethodDeclarationDemo.java
java GenericMethodDeclarationDemo
```

**Stdout chính xác:**

```text
identity: Java
explicit: 7
display: 3.5
first: red
pair: age=36
twice: 8.0
duplicate: [Hi, Hi]
holder: box
instance generic: 42
static generic: true
```

Giải thích theo từng cách khai báo:

1. `static <T> T identity(T value)` khai báo `T` ở **mức method**. `identity("Java")` cho phép suy luận `T = String`; `GenericMethodDeclarationDemo.<Integer>identity(7)` chọn `T = Integer` một cách tường minh. Số `7` được boxing phù hợp.
2. `static <T> void display(T value)` minh họa generic method **không trả về `T`**. Ở lời gọi `display(3.5)`, đối số primitive `double` được biểu diễn qua `Double` cho type parameter.
3. `static <T> T first(List<T> items)` giữ quan hệ **kiểu phần tử ↔ kiểu trả về**. `List.of("red", "blue")` tạo danh sách chứa chuỗi, nên kết quả `first(...)` có kiểu tĩnh `String`. Hàm giả định danh sách không rỗng: nếu rỗng, `get(0)` ném `IndexOutOfBoundsException`.
4. `static <A, B> Map.Entry<A, B> pair(A left, B right)` khai báo **hai type parameter**; `A` và `B` có thể độc lập. `Map.entry` trả entry không hỗ trợ `setValue` và không chấp nhận khóa hay giá trị `null`.
5. `static <T extends Number> double twice(T number)` khai báo type parameter với **upper bound**. Vì vậy `T` được bảo đảm có phương thức `doubleValue()`; hàm trả về `double` cố định, không phải `T`.
6. `static <T> List<T> duplicate(T value)` trả về **kiểu tham số hóa chứa `T`**, không trả về trực tiếp `T`. `List.of(value, value)` không chấp nhận `null` và tạo danh sách không hỗ trợ thay đổi.
7. `Holder<T>` khai báo `T` ở **mức class**. `get()` dùng `T` của class nhưng không khai báo type parameter mới, nên **không phải generic method theo nghĩa tự khai báo `<...>`**.
8. `<U> U echo(U input)` là **instance generic method**: `U` thuộc riêng lời khai báo method. Dù `holder` là `Holder<String>`, `holder.echo(42)` vẫn có thể làm việc với `Integer`.
9. `static <V> V echoStatic(V input)` khai báo type parameter riêng cho method static. Nó không cần một đối tượng `Holder<T>` cụ thể.

Chú ý `<T>`, `<U>`, `<A, B>` và `<V>` là những **phần khai báo trước kiểu trả về**. Đây là điểm thống nhất trong mọi biến thể trên.

## 5. Suy luận kiểu và cách chỉ định type argument khi gọi method

Trong phần lớn lời gọi generic method, không cần gõ type argument tường minh:

```java
String s = identity("hello");
Integer n = identity(5);
```

Trình biên dịch suy luận các type argument bằng thông tin từ **kiểu đối số** và, khi thích hợp, **ngữ cảnh kiểu đích (target typing)**. Việc suy luận là một quá trình kiểm tra ràng buộc kiểu của Java, không chỉ đơn giản thay `T` bằng lớp runtime của đối tượng.

Nếu cần chọn kiểu một cách tường minh, cú pháp thường là:

```java
String text = GenericMethodDeclarationDemo.<String>identity("hello");
Integer number = GenericMethodDeclarationDemo.<Integer>identity(5);
```

Đây là những dòng minh họa có thể đặt trong method của chương trình đầy đủ. Phần `<String>` hoặc `<Integer>` **ở lời gọi** là *type argument tường minh*; khác với `<T>` **ở khai báo**. Đối với static method, dùng tên lớp để chỉ rõ nơi gọi giúp cú pháp dễ đọc.

Một cách suy luận hữu ích với kiểu đích:

```java
static <T> java.util.List<T> empty() {
    return java.util.List.of();
}
```

Khi dùng `List<String> strings = empty();`, trình biên dịch có thể suy luận `T = String` từ kiểu của biến bên trái, dù phương thức không có tham số đầu vào. Với `var strings = empty();`, không có `List<String>` làm kiểu đích, nên kết quả có thể được suy luận rộng hơn, chẳng hạn `List<Object>` trong ví dụ này. Nếu cần `String`, viết kiểu đích tường minh hoặc chỉ định type argument: `var strings = GenericMethodDeclarationDemo.<String>empty();` (sau khi thêm method `empty` vào lớp).

**Hạn chế của `var`:** `var` là suy luận kiểu của **biến cục bộ**, không phải khai báo generic parameter. `var` không tự biến method thành generic và không làm type argument xuất hiện ở runtime.

## 6. Phạm vi của `T`: method và class độc lập

Phân biệt hai nơi **khai báo** là đủ để dùng đúng cú pháp:

```java
class Box<T> {
    T get() { throw new UnsupportedOperationException(); }

    <U> U echo(U input) { return input; }

    static <V> V staticEcho(V input) { return input; }
}
```

- `T` thuộc `Box<T>`: `get()` chỉ **sử dụng** type variable của lớp, không tự khai báo generic method.
- `U` thuộc riêng `echo`: mỗi lời gọi có thể suy luận `U` khác nhau; không phụ thuộc vào type argument `T` của instance.
- `V` thuộc riêng static method. Static context **không dùng trực tiếp `T` của lớp**; cần type parameter thuộc chính method nếu muốn generic.
- Một method khai báo `<T>` trùng tên với type parameter class có thể **che khuất tên**, nhưng cách viết khác như `<U>` dễ đọc hơn.

Đây là **ranh giới phạm vi** cần nhớ khi viết đúng thứ tự khai báo; việc phối hợp kiểu lớp, kiểu method và shadowing được phân tích sâu ở bài riêng trong chương.

## 7. Nhiều tham số kiểu và type bound đều đặt trước kiểu trả về

Một method có thể khai báo nhiều tham số kiểu cách nhau bởi dấu phẩy:

```java
static <K, V> java.util.Map.Entry<K, V> entry(K key, V value) {
    return java.util.Map.entry(key, value);
}
```

Thứ tự `K, V` trong phần khai báo có ý nghĩa xác lập các **tên và vị trí**; method sử dụng đúng các tên này trong kiểu trả về và tham số. Hai tham số độc lập: có thể truyền `String` và `Integer`, hoặc cùng là `String`.

Khi cần giới hạn kiểu của một tham số, dùng **bound** ngay tại khai báo:

```java
static <N extends Number> double doubled(N value) {
    return value.doubleValue() * 2;
}
```

`N extends Number` cho phép gọi `doubleValue()`. Type argument phải đáp ứng upper bound `Number` hoặc subtype; một `String` không phù hợp.

Có thể dùng nhiều bound:

```java
static <T extends Number & Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là method minh họa cần đặt trong class; một số wrapper số như `Integer` thỏa các bound. Nếu một class xuất hiện ở nhiều bound của cùng tham số kiểu, **class bound phải đứng đầu**, sau đó mới đến interface bound phân tách bằng `&`. Không đặt `super` như một lower bound của named type parameter: `? super T` là cú pháp wildcard ở nơi dùng kiểu, không phải `<T super Number>`.

Các chữ ký minh họa:

```java
static <T> void consume(T value) { }

static <T, R> R transform(T input, java.util.function.Function<T, R> fn) {
    return fn.apply(input);
}

static <T extends CharSequence> int length(T value) {
    return value.length();
}
```

Chúng cho thấy `<...>` trước kiểu trả về là **phần khai báo**, còn kiểu trả về có thể là `void`, một tham số kiểu khác (`R`) hoặc kiểu cố định (`int`). Bound cho phép bên trong method sử dụng những khả năng được hợp đồng kiểu bảo đảm.

## 8. Phương thức generic và constructor generic: cùng vị trí khai báo, khác kiểu trả về

Một constructor cũng có thể tự khai báo type parameter nhưng **không có return type**:

```java
class Message {
    private final String text;
    <U> Message(U value) { text = String.valueOf(value); }
    String text() { return text; }
}
```

So sánh `<U> Message(U value)` (constructor) với `<T> T identity(T x)` (method). Với **method**, danh sách type parameters nằm **trước kiểu trả về**; với **constructor**, nó nằm **trước tên constructor** vì không có kiểu trả về. Hai trường hợp có thể cùng xuất hiện trong một chương trình, nhưng không nên gọi constructor là “method không có return type”.

## 9. Type erasure và giới hạn ở runtime

Tham số kiểu `<T>` bảo đảm các quan hệ type-safe tại **compile time**; trong Java 17, kiểu generic thông thường được biên dịch theo **type erasure**. Với `T` không có bound, chữ ký JVM thường sử dụng `Object`, còn compiler có thể chèn casts ở caller.

Vì `T` không tự mang một class token ở runtime, không được dùng tùy tiện `T.class`, `new T()` hoặc `new T[10]`; khi cần, caller phải cung cấp `Class<T>`, array factory hay `Supplier<T>` phù hợp. Hai overload chỉ khác một `List<String>` và `List<Integer>` cũng có thể đụng nhau sau erasure.

Đối với bài này, hãy nhớ **erasure không thay đổi vị trí cú pháp `<T>`**. Những giới hạn runtime là bối cảnh quan trọng nhưng không thay thế quy tắc khai báo trước return type.

## 10. Khi nào cần khai báo `<T>`, khi nào dùng kiểu cụ thể hay wildcard?

Không cần biến mọi method thành generic. Hỏi: **`T` kết nối những vị trí kiểu nào?**

| Mục tiêu | Chữ ký tiêu biểu | Lý do |
| --- | --- | --- |
| Giữ kiểu đầu vào ở kết quả | `static <T> T identity(T x)` | Input và output cùng `T` |
| Lấy một phần tử mà giữ kiểu | `static <T> T first(List<T> xs)` | Danh sách và kết quả liên kết |
| Chỉ in một object | `static void print(Object x)` | Không cần quan hệ generic |
| Đếm phần tử list bất kỳ | `static int size(List<?> xs)` | Không cần đặt tên element type |
| Dùng một bound cụ thể để tính | `static double twice(Number n)` | Kiểu `Number` đủ để gọi `doubleValue()` |

Các chữ ký trên là mẫu **thiết kế**, không phải một source file độc lập. `static <T> void print(T x)` vẫn hoàn toàn hợp lệ; chỉ là thường thừa nếu `T` không thêm quan hệ kiểu có ích. Chọn chữ ký đơn giản nhất mà không đánh mất những bảo đảm compiler cần giữ.

## 11. Lỗi thường gặp về vị trí khai báo `<T>`

**Lỗi 1 — Đặt `<T>` sau kiểu trả về.** Viết `static T <T> echo(T x)` là sai thứ tự cú pháp; viết `static <T> T echo(T x)`.

**Lỗi 2 — Quên khai báo `<T>` trong method độc lập.** Viết `static T echo(T x)` khi `T` không được khai báo phù hợp sẽ gây lỗi không tìm thấy kiểu `T`; sửa bằng `static <T> T echo(T x)`.

**Lỗi 3 — Nghĩ `List<String>` trong kết quả đã biến phương thức thành generic.** `static List<String> names()` trả về parameterized type cụ thể, nhưng không tự khai báo tham số kiểu nào. Generic method thực sự có phần khai báo `<T>`, `<K,V>`... riêng.

**Lỗi 4 — Nghĩ kiểu trả về bắt buộc phải là `T`.** `static <T> void print(T x)`, `static <T> List<T> one(T x)` và `static <T extends Number> double twice(T x)` đều là generic method hợp lệ.

**Lỗi 5 — Dùng class `T` trong static method.** `class Box<T> { static T get(...); }` không hợp lệ vì static không gắn với một cách tham số hóa instance. Static generic method phải khai báo type parameter của chính nó.

**Lỗi 6 — Lẫn type parameter của class và của method cùng tên `T`.** `class Box<T> { <T> T echo(T x) { return x; } }` có thể tạo shadowing khiến `T` method khác `T` class. Dùng `<U>` khi muốn rõ sự độc lập.

**Lỗi 7 — Tưởng literal primitive biến `T` thành `int`.** `identity(5)` dùng boxing và `Integer` trong ngữ cảnh generic. Không viết `<int>`; type argument Java generics phải là reference type.

**Lỗi 8 — Dùng `<T>` để overload method vốn trùng erasure.** `void log(Object)` và `<T> void log(T)` không cùng tồn tại hợp lệ trong một lớp nếu tạo name clash như ví dụ ở trên.

**Lỗi 9 — Dùng type argument tường minh ở lời gọi sai vị trí.** Khi cần chỉ định type argument của static method, dùng `ClassName.<String>method(...)`; đừng viết kiểu khai báo `method<String>(...)` theo cú pháp ngôn ngữ khác.

**Lỗi 10 — Tưởng generic method luôn tạo hoặc biết kiểu runtime của `T`.** Erasure ngăn `new T()` hoặc `T.class` trực tiếp. Nếu bài toán yêu cầu tạo đối tượng, có thể truyền `Supplier<T>` hoặc factory; nếu cần kiểm tra runtime type, truyền `Class<T>` và kiểm tra cẩn thận.

## 12. Câu hỏi tự kiểm tra kèm đáp án

1. **Trong `static <T> T identity(T value)`, chỗ nào khai báo `T`?** Phần `<T>` đứng trước kiểu trả về.
2. **Chữ `T` ngay sau `<T>` nghĩa là gì?** Kiểu trả về, sử dụng tham số kiểu vừa khai báo.
3. **`static <T> void print(T x)` có phải generic method không?** Có, vì method tự khai báo `<T>`; không bắt buộc trả `T`.
4. **`static List<String> words()` có phải generic method không?** Không, method không khai báo tham số kiểu mới; nó chỉ trả về một parameterized type.
5. **`class Box<T> { T get() {...} }` thì `get()` có tự khai báo generic parameter không?** Không; `get()` dùng `T` thuộc lớp. Bản thân `Box` là generic class.
6. **`class Box<T> { static <U> U echo(U x) {...} }` hợp lệ không?** Có; `U` do static method tự khai báo.
7. **Từ `identity("A")`, compiler suy luận gì?** Có thể suy luận `T = String` cho lời gọi; kết quả dùng được dưới kiểu `String`.
8. **Viết type argument tường minh của static method ở đâu?** Sau tên lớp/dấu chấm và trước tên method, ví dụ `Demo.<String>identity("A")`.
9. **Đổi `static <T> T first(List<T> xs)` thành `static <T> Object first(List<T> xs)` có gì mất?** Kiểu trả về không còn thể hiện trực tiếp `T`; người gọi chỉ thấy `Object`, mất bảo đảm kiểu đầu ra cụ thể.
10. **`<K, V> Map.Entry<K, V> pair(K k,V v)` có phải hai phương thức generic không?** Không; một phương thức generic khai báo hai type parameter `K` và `V`.
11. **Vì sao không viết `new T()` trong một method chỉ có `<T>`?** Do erasure và không có thông tin constructor của kiểu cụ thể; cần nhận factory/`Supplier<T>` hoặc thông tin runtime bổ sung.
12. **Một constructor generic đặt `<T>` ở đâu?** Trước tên constructor vì constructor không có kiểu trả về; khác với method có dạng `<T> ReturnType name(...)`.

Hãy nhớ mẫu cú pháp trọng tâm: **`[modifier] <T> ReturnType methodName(...)`**. Phần `<T>` **khai báo tên kiểu** cho phương thức; phần `ReturnType` **mô tả thứ method trả về** và có thể là `T`, `List<T>`, `void` hoặc kiểu cố định. Khi phân biệt đúng hai vị trí này, bạn sẽ đọc và viết được generic method với một hay nhiều tham số kiểu mà vẫn giữ an toàn kiểu.
