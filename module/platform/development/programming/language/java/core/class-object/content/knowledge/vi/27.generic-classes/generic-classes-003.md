# Tạo đối tượng với đối số kiểu và toán tử diamond (`<>`) — Java 17

## Mục tiêu

Khi làm việc với generic classes trong Java, lập trình viên thường gặp hai cách tạo object trông gần giống nhau:

```java
Box<String> explicit = new Box<String>("Java");
Box<String> inferred = new Box<>("Java");
```

Cách thứ nhất **ghi rõ đối số kiểu** `String` tại biểu thức `new`. Cách thứ hai sử dụng **diamond operator `<>`** để Java compiler **suy luận đối số kiểu** dựa trên ngữ cảnh và đối số constructor. Cả hai đều là các đối tượng `Box`; diamond không tạo một class đặc biệt hay trì hoãn việc quyết định kiểu đến runtime.

Bài này hướng dẫn đầy đủ cách viết generic class, truyền đối số kiểu khi tạo object, target typing, diamond inference, mối liên hệ với `var`, constructors, generic constructors, bounds, wildcards, invariance, collections, anonymous classes từ Java 9, các lỗi do raw types/unchecked conversions, type erasure, khả năng mở rộng API, kỹ thuật kiểm thử và bài tập Java 17. Tất cả ví dụ được gắn nhãn **chương trình độc lập** hoặc **đoạn minh họa** để không nhầm mã cố ý lỗi với mã chạy được.

**Điều cần ghi nhớ từ đầu:**

- `Box<T>`: **`T` là tham số kiểu** (*type parameter*) trong khai báo generic class.
- `Box<String>`: **`String` là đối số kiểu** (*type argument*) khi sử dụng class.
- `new Box<String>(...)`: viết **tường minh** đối số kiểu tại chỗ tạo object.
- `new Box<>(...)`: dùng diamond để **suy luận** đối số kiểu, không phải raw type.
- `new Box(...)`: bỏ toàn bộ type arguments trên một generic class là **raw-type use**, khác hẳn diamond; có thể tạo unchecked warnings và giảm kiểm tra kiểu.
- Dù viết tường minh hay diamond, **Java generics chủ yếu được kiểm tra tại compile time và sử dụng type erasure ở runtime**.

## 1. Khai báo một lớp generic

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` ở đây là một **type parameter**, được khai báo trong `class Box<T>`. Trong thân class, compiler dùng `T` như một kiểu có ràng buộc nhất định, không phải một đối tượng `Class` và không phải String tên kiểu.

Một instance có thể được sử dụng như:

```java
Box<String> words = new Box<String>("hello");
Box<Integer> count = new Box<Integer>(17);
```

Compiler đảm bảo:
- `words.get()` có compile-time type `String`.
- `count.get()` có compile-time type `Integer`.
- `new Box<String>(123)` không phù hợp với constructor nhận `String`.
- Không cần bạn cast `words.get()` thành String trong code sử dụng.

**Generic class không tự sao chép thành một class JVM riêng cho mỗi kiểu.** Java áp dụng type erasure cho phần lớn generic type information tại runtime.

## 2. Runnable: tạo object bằng đối số kiểu tường minh

Lưu **`ExplicitTypeArgumentsDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

public class ExplicitTypeArgumentsDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<String>("Java");
        Box<Integer> number = new Box<Integer>(17);

        String a = text.get();
        Integer b = number.get();

        System.out.println(a);
        System.out.println(b);
        System.out.println(text.getClass() == number.getClass());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

Stdout:

```text
Java
17
true
```

Dòng cuối quan trọng: tại runtime, cả hai objects có cùng runtime class `Box`. Sự khác nhau `String`/`Integer` là thông tin compile-time giúp type checking, không nhất thiết có hai runtime classes tách biệt.

## 3. Cú pháp diamond operator

Cách tường minh:

```java
List<String> names = new ArrayList<String>();
```

Cách dùng diamond:

```java
List<String> names = new ArrayList<>();
```

Cú pháp `<>` chứa **hai dấu ngoặc nhọn của generic type argument list nhưng không ghi tên type argument ở giữa**. Compiler sẽ suy luận phù hợp, dựa trên các constraints từ biểu thức, constructor arguments và target type nếu có.

Không nhầm với:

```java
List names = new ArrayList();
```

Đoạn sau dùng raw `List` và raw `ArrayList`, bỏ qua phần type checking quan trọng của generics.

**Cách nhớ:** diamond là **yêu cầu compiler suy luận kiểu**, còn raw type là **cố tình hoặc vô tình không dùng đầy đủ generic type checking**.

## 4. Runnable: explicit và diamond cho kết quả giống nhau

Lưu **`DiamondBasicsDemo.java`**:

```java
final class Holder<T> {
    private final T item;

    Holder(T item) {
        this.item = item;
    }

    T item() {
        return item;
    }
}

public class DiamondBasicsDemo {
    public static void main(String[] args) {
        Holder<String> first = new Holder<String>("hello");
        Holder<String> second = new Holder<>("hello");

        System.out.println(first.item());
        System.out.println(second.item());
        System.out.println(first.item().equals(second.item()));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondBasicsDemo.java
java DiamondBasicsDemo
```

Stdout:

```text
hello
hello
true
false
```

`first` và `second` là hai distinct objects do hai lệnh `new`, không phải compiler dùng chung một instance vì chúng có cùng generic type.

## 5. Phân biệt ba chỗ ghi kiểu

```java
class Pair<K, V> {
    Pair(K key, V value) {
    }
}
```

Và:

```java
Pair<String, Integer> p =
        new Pair<String, Integer>("age", 20);
```

Có ba cấp thông tin:
1. `<K,V>` sau **tên class trong khai báo** là **formal type parameters**.
2. `<String,Integer>` bên trái `p` là **parameterized type** của biến.
3. `<String,Integer>` bên phải, sau `new Pair`, là **explicit type arguments** cho việc tạo instance.

Thay bên phải bằng diamond:

```java
Pair<String, Integer> p = new Pair<>("age", 20);
```

Compiler suy luận chúng. Không phải bạn đã xóa generic typing khỏi object.

### Hai tham số kiểu có thể khác nhau

`Pair<String,Integer>` khác `Pair<Integer,String>` tại compile time; `Pair<String,Integer>` không tự tương thích với `Pair<Object,Object>`. Đây là **invariance** của các generic type arguments thông thường trong Java.

## 6. Runnable: nhiều đối số kiểu

Lưu **`DiamondPairDemo.java`**:

```java
record Pair<K, V>(K key, V value) {
}

public class DiamondPairDemo {
    public static void main(String[] args) {
        Pair<String, Integer> first =
                new Pair<String, Integer>("age", 20);
        Pair<String, Integer> second =
                new Pair<>("height", 180);

        System.out.println(first);
        System.out.println(second.key());
        System.out.println(second.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondPairDemo.java
java DiamondPairDemo
```

Stdout:

```text
Pair[key=age, value=20]
height
180
```

Record `Pair<K,V>` trong Java 17 cũng là generic class. Constructor của record gắn với components `K key` và `V value`. Diamond inference hoạt động cho generic record class instance creation.

## 7. Diamond không có nghĩa runtime tự nhận dạng đối số kiểu

Nếu bạn viết:

```java
Box<String> box = new Box<>("A");
```

compiler xác định `T` phù hợp khi biên dịch. Khi chạy chương trình, JVM không “nhìn vào String object rồi chọn một phiên bản Box<String>” theo mô hình chuyên biệt hóa từng class.

Thông tin generic types thường bị erasure:
- Runtime `box.getClass()` là `Box.class`, không phải một `Box<String>.class`.
- `instanceof Box<String>` không hợp lệ do generic type parameterized không reifiable.
- `instanceof Box<?>` có thể dùng để kiểm tra shape runtime phù hợp, nhưng không xác thực kiểu của dữ liệu bên trong.
- Nếu phải xác thực element type ở runtime, truyền một `Class<T>` hoặc type token phù hợp và chủ động kiểm tra.

`<>` là cú pháp cho **compile-time inference**, không phải runtime reflection feature.

## 8. Mục đích lịch sử và lợi ích thực tiễn

Trước khi có diamond (được bổ sung từ Java 7), người dùng generic collections thường lặp lại toàn bộ arguments:

```java
Map<String, List<Integer>> map =
        new HashMap<String, List<Integer>>();
```

Với diamond:

```java
Map<String, List<Integer>> map = new HashMap<>();
```

Lợi ích:
- Ít lặp tên kiểu dài.
- Ít khả năng gõ nhầm type arguments giữa hai phía.
- Khi đổi target type, có thể chỉ cần sửa phía khai báo.
- Cải thiện khả năng đọc các generic constructors/collections.

Nhưng diamond không phải mục tiêu tự thân. Nếu inference không rõ hoặc lập trình viên cần thấy một lựa chọn kiểu cụ thể tại call site, **explicit type arguments vẫn hoàn toàn hợp lệ**.

## 9. Target typing là gì?

Một số biểu thức Java là **poly expressions**, nghĩa là type inference có thể chịu ảnh hưởng từ **target type** trong ngữ cảnh như assignment, initializer, method invocation hoặc return statement.

Ví dụ:

```java
List<String> names = new ArrayList<>();
```

Target type `List<String>` cung cấp constraint để compiler suy ra type argument `String` cho `ArrayList`.

Ví dụ khác:

```java
Box<Number> box = new Box<>(Integer.valueOf(7));
```

Dù argument value có compile-time type `Integer`, target type có thể khiến generic class type argument là `Number`, miễn mọi constraints hợp lệ.

**Không nên nghĩ compiler chỉ “nhìn vào object được truyền trong ngoặc” rồi luôn chọn đúng concrete class của object đó.** Inference kết hợp target typing và applicability constraints theo JLS `18`.

## 10. Runnable: target type ảnh hưởng inference

Lưu **`DiamondTargetTypingDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondTargetTypingDemo {
    public static void main(String[] args) {
        Box<Number> number = new Box<>(Integer.valueOf(7));
        Box<String> word = new Box<>("Java");

        Number n = number.value();
        String s = word.value();

        System.out.println(n.intValue());
        System.out.println(s.length());
        System.out.println(n.getClass().getSimpleName());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondTargetTypingDemo.java
java DiamondTargetTypingDemo
```

Stdout:

```text
7
4
Integer
```

Static type của `n` là `Number`, còn object bên trong là một `Integer`. **Static generic type** và **runtime concrete object class** là hai lớp thông tin khác nhau.

## 11. Inference có thể dựa vào constructor arguments

Nếu không có target type cụ thể, compiler có thể suy luận từ đối số truyền cho constructor:

```java
var text = new Box<>("Java");
```

Ở Java 17, `var` suy luận compile-time type của local variable từ initializer expression. Ở ví dụ này, argument `"Java"` cho phép inference theo hướng `Box<String>`.

Với:

```java
var count = new Box<>(42);
```

Argument `42` là primitive `int`; generic type arguments phải là reference types, nên việc boxing cho phép inference liên quan `Integer`.

### Không phải runtime “tự động ép kiểu”

`var` cũng là compile-time local variable type inference, không phải dynamic typing. Sau khi compiler suy luận type của `text`, bạn vẫn chịu Java static type checking.

## 12. Runnable: diamond kết hợp `var`

Lưu **`DiamondVarDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondVarDemo {
    public static void main(String[] args) {
        var title = new Box<>("Java");
        var count = new Box<>(17);

        String word = title.value();
        Integer number = count.value();

        System.out.println(word.toUpperCase());
        System.out.println(number + 1);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondVarDemo.java
java DiamondVarDemo
```

Stdout:

```text
JAVA
18
```

Nếu thay thành `var title = new Box<>(17)` rồi cố `String word = title.value()`, compiler từ chối; `var` không làm phép gán sang kiểu tùy ý hợp lệ.

## 13. Diamond với constructor không nhận arguments

Xét:

```java
class Bag<T> {
    Bag() {
    }
}
```

Khi viết:

```java
Bag<String> a = new Bag<>();
```

không có constructor argument để cho biết `T`. Nhưng target type `Bag<String>` là constraint giúp compiler suy ra `String`.

Ngược lại:

```java
var b = new Bag<>();
```

không có target parameterized type từ `var`, cũng không có arguments ràng buộc `T`. Với generic type parameter không bị bounds khác, compiler có thể suy ra `Object`.

### Bẫy lớn

Không nên viết `var list = new ArrayList<>()` rồi mặc định tin `list` là `ArrayList<String>` chỉ vì sau này bạn định thêm Strings. Biến đã có static type từ **initializer**, không phụ thuộc code xuất hiện về sau.

## 14. Runnable: empty diamond và `var`

Lưu **`DiamondEmptyConstructorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondEmptyConstructorDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");

        var mixed = new ArrayList<>();
        mixed.add("Java");
        mixed.add(17);

        System.out.println(names);
        System.out.println(mixed);
        System.out.println(mixed.get(1) instanceof Integer);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondEmptyConstructorDemo.java
java DiamondEmptyConstructorDemo
```

Stdout:

```text
[An]
[Java, 17]
true
```

Trong ví dụ, `mixed` được suy ra `ArrayList<Object>` (không bounds hẹp và không context đích cụ thể), nên thêm cả String lẫn Integer hợp lệ. Nếu ý định là danh sách chỉ chứa Strings, viết `List<String> mixed = new ArrayList<>()` hoặc `var mixed = new ArrayList<String>()`.

## 15. `var` không phải thay thế cho mọi explicit type argument

So sánh:

| Cách viết | Kiểu tĩnh đáng chú ý | Ý nghĩa |
| --- | --- | --- |
| `List<String> xs = new ArrayList<>();` | Biến kiểu `List<String>` | Target typing rõ, abstraction interface |
| `var xs = new ArrayList<String>();` | `ArrayList<String>` | Inference của `var` từ expression đã parameterize |
| `var xs = new ArrayList<>();` | Thường `ArrayList<Object>` | Không có String constraint khi constructor rỗng |
| `var xs = new ArrayList<>(List.of("A"));` | Inference dựa vào nguồn String | Có constructor argument hữu ích |
| `List xs = new ArrayList();` | Raw `List` | Mất type checking cho elements |

**Khuyến nghị:** khi constructor không có arguments mà element type quan trọng, để type rõ ở **ít nhất một phía** của declaration.

## 16. Diamond với collection constructors

Các class phổ biến:

```java
List<String> list = new ArrayList<>();
Set<Integer> numbers = new HashSet<>();
Map<String, Integer> counts = new HashMap<>();
Deque<String> queue = new ArrayDeque<>();
```

Đây là các **snippets**; thêm `import java.util.*;` và code sử dụng nếu cần runnable.

Lưu ý:
- `List`/`Set`/`Map`/`Deque` là interfaces, thường **không thể new trực tiếp**.
- `ArrayList`/`HashSet`/`HashMap`/`ArrayDeque` là concrete generic classes có constructors phù hợp.
- Diamond gắn với **class being instantiated**, không phải type của biến trên trái.
- Inference có thể đưa tới subtype-specific parameterization phù hợp với target interface type.

### Viết `new List<>()` có được không?

Không. `List` là interface. Lỗi xuất phát từ việc cố instantiate interface, **không** phải từ diamond. Chọn một implementation như `new ArrayList<>()`.

## 17. Runnable: collections với diamond

Lưu **`DiamondCollectionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DiamondCollectionsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Binh");

        Map<String, Integer> scores = new HashMap<>();
        scores.put("An", 8);
        scores.put("Binh", 9);

        System.out.println(names);
        System.out.println(scores.get("An"));
        System.out.println(scores.get("Binh"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondCollectionsDemo.java
java DiamondCollectionsDemo
```

Stdout:

```text
[An, Binh]
8
9
```

Không in trực tiếp toàn bộ `HashMap` để tránh vô tình phụ thuộc iteration order. `get(key)` trả rõ các values đã đưa vào.

## 18. Invariance: `Box<Integer>` không phải subtype của `Box<Number>`

Ngay cả khi `Integer extends Number`, hai parameterized types sau **không** có quan hệ subtype theo cách nhiều người đoán:

```java
Box<Integer> ints = new Box<>(7);

// Compile-negative:
// Box<Number> numbers = ints;
```

Java generic classes thông thường **invariant** theo type arguments. Nếu assignment kia được phép, caller có thể qua `Box<Number>` truyền một Double vào nơi vốn chỉ được phép Integer (với một mutable Box), phá type safety.

Cách nhận mọi Box chứa subtype Number:

```java
Box<? extends Number> view = new Box<Integer>(7);
```

`? extends Number` là wildcard với upper bound; có thể đọc Number, nhưng không được coi là nơi tự do ghi mọi Number vì underlying Box có thể là Box<Integer>.

### Diamond vẫn dùng với wildcard target

```java
Box<? extends Number> view = new Box<>(7);
```

Compiler chọn parameterization phù hợp với constructor arguments/target. Wildcard nằm trong **target type**; không phải bạn đã xin tạo một object có runtime element class “?” hay bỏ type safety.

## 19. Runnable: wildcard target và diamond

Lưu **`DiamondWildcardDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondWildcardDemo {
    public static void main(String[] args) {
        Box<? extends Number> number = new Box<>(7);
        Number n = number.value();

        System.out.println(n.intValue());
        System.out.println(number.value().getClass().getSimpleName());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondWildcardDemo.java
java DiamondWildcardDemo
```

Stdout:

```text
7
Integer
```

`? extends Number` giúp consumer đọc một Number. Nó không biến wildcard thành một argument type cụ thể có thể tùy tiện viết sau `new Box<? extends Number>`.

## 20. Bounded type parameters đặt ràng buộc cho inference

Một generic class có thể yêu cầu `T` là subtype của một class/interface:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T extends Number` là **bound**. Diamond phải suy ra một type argument thỏa bound đó:

```java
NumericBox<Integer> a = new NumericBox<>(10);
NumericBox<Double> b = new NumericBox<>(2.5);
```

Không hợp lệ:

```java
// Compile-negative:
// NumericBox<String> c = new NumericBox<>("bad");
```

`String` không extends Number. Diamond không bỏ qua bounds.

### Bound là type checking, không phải ép dữ liệu

Java không tự parse String `"10"` thành Number để thỏa bound. Muốn chuyển dữ liệu, gọi `Integer.parseInt` hoặc factory/constructor nhận String rồi parse theo contract riêng.

## 21. Runnable: diamond giữ generic bounds

Lưu **`DiamondBoundsDemo.java`**:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}

public class DiamondBoundsDemo {
    public static void main(String[] args) {
        NumericBox<Integer> count = new NumericBox<>(10);
        NumericBox<Double> price = new NumericBox<>(2.5);

        System.out.println(count.asDouble());
        System.out.println(price.asDouble());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondBoundsDemo.java
java DiamondBoundsDemo
```

Stdout:

```text
10.0
2.5
```

Compiler suy ra `Integer` và `Double` sao cho ràng buộc `extends Number` đều đúng. Thao tác runtime `doubleValue()` do Number API hỗ trợ.

## 22. Generic class parameters khác generic constructor parameters

Xét:

```java
class Box<T> {
    <U extends Number> Box(T item, U initialCount) {
        // ...
    }
}
```

Ở đây:
- `T` là type parameter của **class**.
- `U` là type parameter của **constructor riêng**.
- Tạo `new Box<String>("A", 3)`: `T=String` từ class type argument, `U` có thể suy ra Integer từ constructor argument `3`.
- `new Box<>("A", 3)`: compiler cũng phải suy luận **class type argument** từ diamond cùng với type variable của generic constructor.

**Không nên nhập nhằng** `new Box<String>(...)` với **explicit type arguments của một generic constructor**; chúng xuất hiện ở vị trí cú pháp khác và có mục đích khác. Diamond `<>` sau tên class là cách suy luận **class parameterization**.

### Constructor không generic vẫn nhận T

`Box(T item)` không tự là một generic constructor chỉ vì parameter type là `T`. Nó dùng class type parameter đã khai báo ở `class Box<T>`.

## 23. Runnable: class type variable và constructor type variable

Lưu **`GenericConstructorDiamondDemo.java`**:

```java
final class Entry<T> {
    private final T value;
    private final Number weight;

    <U extends Number> Entry(T value, U weight) {
        this.value = value;
        this.weight = weight;
    }

    T value() {
        return value;
    }

    Number weight() {
        return weight;
    }
}

public class GenericConstructorDiamondDemo {
    public static void main(String[] args) {
        Entry<String> first = new Entry<>("A", 7);
        Entry<Integer> second = new Entry<>(42, 2.5);

        System.out.println(first.value() + ":" + first.weight());
        System.out.println(second.value() + ":" + second.weight());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 GenericConstructorDiamondDemo.java
java GenericConstructorDiamondDemo
```

Stdout:

```text
A:7
42:2.5
```

Compiler kiểm tra `T` cho value và suy ra `U` bounded Number cho weight. Không phải cùng một type variable điều khiển cả hai vị trí.

## 24. Constructor overload resolution và diamond tương tác thế nào?

Generic constructors của một generic class có thể overload. Khi gặp `new Container<>(args)`, compiler cần xét:
1. Đối số của biểu thức `new`.
2. Constructors applicable (arity/types, widening, boxing, varargs).
3. Bounds và type inference variables.
4. Target type khi expression là poly expression.
5. Most-specific overload và potential ambiguity.

Không nên cho rằng `<>` làm mọi overload được chọn dựa trên **runtime class** của đối số. Lựa chọn được quyết định tại compile time.

### Null có thể gây ambiguity

Một class có `Container(String)` và `Container(Integer)`:
- `new Container<>("A")` chọn String nếu hợp lệ.
- `new Container<>(1)` chọn Integer nếu hợp lệ.
- `new Container<>(null)` có thể ambiguous do String và Integer không có quan hệ subtype phù hợp.

Cách sửa có thể là cast `(String) null` hoặc dùng named factory có semantic rõ, không phải bỏ diamond thành raw type.

## 25. Ví dụ compile-negative: ambiguity giữa constructors

Đây là một **snippet cố ý không biên dịch**:

```java
class Choice<T> {
    Choice(String label) { }
    Choice(Integer count) { }
}

Choice<Object> c = new Choice<>(null);
```

`null` phù hợp cả hai overloads. Compiler không thể chọn một constructor đặc hiệu nhất giữa String và Integer.

Sửa:

```java
Choice<Object> c = new Choice<>((String) null);
```

Hoặc đặt một API không cần truyền null để chọn semantics, ví dụ `Choice.fromLabel(...)` và `Choice.fromCount(...)`.

**Bài học:** vấn đề là **constructor overload ambiguity**, không phải riêng diamond.

## 26. Không truyền primitive type làm generic type argument

Hợp lệ:

```java
Box<Integer> count = new Box<>(3);
Box<Double> price = new Box<>(2.5);
```

Sai:

```java
// Compile-negative:
Box<int> primitive = new Box<int>(3);
```

Java generics sử dụng **reference types** làm type arguments. Các primitive `int`, `double`, `boolean` không được viết trong `<...>` như type arguments.

Autoboxing có thể chuyển `int` argument thành `Integer` khi cần, nhưng không tạo ra `Box<int>`.

### Chi phí cần cân nhắc

Boxing tạo/use wrapper objects trong những điều kiện nhất định. Với dữ liệu primitive lớn và hiệu năng nhạy cảm, cân nhắc arrays primitives hoặc specialized APIs như `IntStream`. Không chọn raw type để “tối ưu boxing”; raw type không làm Java generics hỗ trợ primitive type arguments.

## 27. Không phải mọi generic syntax sau `new` đều hợp lệ

Những đoạn sau là **compile-negative snippets**:

```java
// Interface không thể instantiate:
List<String> a = new List<>();

// Primitive type argument không hợp lệ:
Box<int> b = new Box<int>(1);

// Không được tạo array của generic parameterized type:
List<String>[] c = new List<String>[3];

// T không phải concrete class được new trực tiếp:
class Factory<T> {
    T create() {
        return new T();
    }
}
```

Thay bằng:
- `new ArrayList<>()` thay vì `new List<>()`.
- `Integer` thay `int`.
- `List<List<String>>` hoặc collection/typed-array strategy thay generic array creation khi phù hợp.
- `Supplier<T>`, `Class<T>`/reflection hay factory object khi phải tạo giá trị kiểu T.

Diamond không bỏ bất kỳ ràng buộc cơ bản nào của Java generics.

## 28. Wildcard không giống diamond

Cùng có dấu `?` hoặc `<>` trong tài liệu generics nhưng hai cơ chế hoàn toàn khác:

- `<>` sau một generic class name trong `new X<>(...)` là **diamond type inference**.
- `?` trong `List<?>` là **wildcard type argument**, biểu diễn một loại phần tử chưa biết với các ràng buộc.
- `? extends Number` và `? super Integer` mô tả quan hệ đọc/ghi từ các parameterized references.
- `?` không đại diện một Java class có thể sử dụng tùy ý làm kiểu cụ thể khi tạo object.

Ví dụ:

```java
List<? extends Number> source = new ArrayList<Integer>();
List<? super Integer> sink = new ArrayList<Number>();
```

Với diamond bạn thường viết gọn hơn:

```java
List<? extends Number> source = new ArrayList<>();
List<? super Integer> sink = new ArrayList<>();
```

Trong những trường hợp đặc biệt, constraints của wildcard target và constructor arguments có thể cho inference khác suy đoán thông thường, nên compiler chính là nguồn xác nhận cuối cùng.

## 29. Runnable: PECS với type arguments rõ ràng

Lưu **`WildcardBoxDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardBoxDemo {
    public static void main(String[] args) {
        List<? extends Number> source =
                new ArrayList<Integer>(List.of(1, 2));

        List<? super Integer> sink =
                new ArrayList<Number>();

        Number first = source.get(0);
        sink.add(3);
        sink.add(4);

        System.out.println(first.intValue());
        System.out.println(sink);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WildcardBoxDemo.java
java WildcardBoxDemo
```

Stdout:

```text
1
[3, 4]
```

Quy tắc **PECS**: Producer Extends, Consumer Super. Đây là quy tắc sử dụng wildcard references; nó **khác** với quyết định ghi `<>` hay explicit type arguments ở biểu thức new.

## 30. Diamond khi truyền vào method parameter

Target typing cũng có thể xuất hiện khi tạo object ngay ở argument cho một method:

```java
static void printNames(List<String> names) {
    System.out.println(names);
}

printNames(new ArrayList<>());
```

Đây là **snippet** bên trong một class/method phù hợp. Compiler biết method parameter cần `List<String>` và có thể dùng constraint đó khi suy luận cho `new ArrayList<>()`.

Lợi ích: không bắt buộc khai báo một biến trung gian chỉ để đặt type argument, khi ngữ cảnh đã rõ.

### Tuy nhiên, method overload có thể làm inference phức tạp

Nếu hai overloads có parameterized types gần nhau, constructor argument inference và method overload resolution tương tác; có thể gây ambiguity hoặc compiler diagnostic phức tạp. Khi source khó đọc, hãy tách:

```java
List<String> names = new ArrayList<>();
printNames(names);
```

Kiểu rõ ràng tại một biến trung gian thường giúp người đọc và công cụ phân tích.

## 31. Runnable: target type qua method parameter

Lưu **`DiamondMethodArgumentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondMethodArgumentDemo {
    static void inspect(List<String> values) {
        values.add("Java");
        System.out.println(values);
    }

    public static void main(String[] args) {
        inspect(new ArrayList<>());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondMethodArgumentDemo.java
java DiamondMethodArgumentDemo
```

Stdout:

```text
[Java]
```

Ở thời điểm compile method call, parameter type `List<String>` góp phần ràng buộc inference cho diamond creation expression.

## 32. Diamond trong return statement

Ví dụ:

```java
static List<String> makeNames() {
    return new ArrayList<>();
}
```

Target type của `return` là `List<String>`, giúp compiler suy luận type arguments cho `ArrayList`.

Áp dụng tương tự với:
- Generic record: `return new Pair<>(left,right);`.
- Class chứa value: `return new Box<>(value);`.
- Mapping: `return new HashMap<>();`.

**Không được suy rằng mọi biểu thức new luôn poly**. Java có những điều kiện cụ thể về diamond và target typing. Hãy phân biệt các bối cảnh standalone/poly theo JLS 15.9 và JLS 18.

## 33. Runnable: target typing trong return

Lưu **`DiamondReturnDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondReturnDemo {
    static List<String> makeNames() {
        return new ArrayList<>();
    }

    public static void main(String[] args) {
        List<String> names = makeNames();
        names.add("An");

        System.out.println(names);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondReturnDemo.java
java DiamondReturnDemo
```

Stdout:

```text
[An]
```

Không cần ghi `new ArrayList<String>()`, vì method return type đã công bố `List<String>`.

## 34. Diamond và anonymous class: thay đổi kể từ Java 9

Từ Java 9, diamond có thể được dùng khi tạo **anonymous class** trong những điều kiện inference hợp lệ.

Java 17 cho phép:

```java
java.util.function.Supplier<String> supplier =
        new java.util.function.Supplier<>() {
            @Override
            public String get() {
                return "Java";
            }
        };
```

Compiler suy luận type arguments cho interface `Supplier`, đồng thời anonymous class implements `Supplier<String>`.

### Có khác với Java 7 và Java 8 không?

Có. Các phiên bản cũ không cho dùng diamond với anonymous class declarations; phải ghi explicit type arguments ở chỗ `new`. Khi đọc tutorial cũ nói “diamond không dùng với anonymous classes”, hãy kiểm tra version. Với Java 17, tuyên bố tuyệt đối đó **không còn chính xác**.

### Giới hạn đáng chú ý

Khi dùng diamond với anonymous class, Java áp thêm quy tắc cho những methods được khai báo trong anonymous body: một non-private method phải override/implement method từ supertype. Nếu chỉ muốn helper nội bộ, cân nhắc khai báo nó `private`, hoặc dùng named implementation phù hợp.

## 35. Runnable: diamond + anonymous implementation

Lưu **`DiamondAnonymousDemo.java`**:

```java
import java.util.function.Supplier;

public class DiamondAnonymousDemo {
    public static void main(String[] args) {
        Supplier<String> supplier = new Supplier<>() {
            @Override
            public String get() {
                return "hello";
            }

            private String helper() {
                return "internal";
            }
        };

        System.out.println(supplier.get());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondAnonymousDemo.java
java DiamondAnonymousDemo
```

Stdout:

```text
hello
```

`get()` là method override của Supplier. `helper()` private và không ảnh hưởng contract bên ngoài. Không cần phụ thuộc tên compiler-generated của anonymous class.

## 36. Compile-negative: method phụ non-private trong diamond anonymous body

Đây là **snippet cố ý sai**:

```java
import java.util.function.Supplier;

Supplier<String> supplier = new Supplier<>() {
    @Override
    public String get() {
        return "hello";
    }

    public String extra() {
        return "not an override";
    }
};
```

Trong anonymous declaration dùng diamond, `extra()` non-private nhưng không override/implement method của Supplier, nên Java 17 từ chối. Đổi thành `private String extra()` nếu chỉ là helper, hoặc viết named class khi cần API mở rộng.

**Phân biệt:** vấn đề này không có nghĩa mọi anonymous class đều cấm methods mới; đây là ràng buộc **riêng cho anonymous class dùng diamond**. Nếu dùng explicit generic type arguments, các quy tắc có thể khác.

## 37. Anonymous subclass của generic class

Ngoài interface, bạn có thể tạo anonymous subclass của generic superclass:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

Holder<String> value = new Holder<>("Java") {
    @Override
    String value() {
        return super.value().toUpperCase();
    }
};
```

Đây là một **snippet** phù hợp Java 17 nếu cùng một compilation context với class Holder. Constructor argument truyền vào superclass constructor, còn diamond suy luận class type arguments ở anonymous subclass creation.

Cẩn trọng:
- Generic superclass phải cho phép subclassing; không phải final.
- Constructor superclass phải accessible.
- Anonymous class không tự đặt tên source constructor.
- Các non-private methods trong diamond anonymous body chịu quy tắc override đã nhắc.
- Các thông tin type arguments không trở thành runtime new Class phiên bản String.

## 38. Runnable: anonymous generic superclass với diamond

Lưu **`DiamondAnonymousSubclassDemo.java`**:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondAnonymousSubclassDemo {
    public static void main(String[] args) {
        Holder<String> value = new Holder<>("java") {
            @Override
            String value() {
                return super.value().toUpperCase();
            }
        };

        System.out.println(value.value());
        System.out.println(value.getClass() == Holder.class);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondAnonymousSubclassDemo.java
java DiamondAnonymousSubclassDemo
```

Stdout:

```text
JAVA
false
```

Runtime class khác `Holder.class` vì đây là một anonymous subclass instance. Điều này do **anonymous class** tạo subtype, không phải do diamond tạo chuyên biệt hóa generic class.

## 39. Đối số kiểu suy luận phải denotable trong các ngữ cảnh quy định

Java có những điều kiện về **denotable types** và accessibility khi suy luận type cho anonymous class dùng diamond. Một số type inference results quá phức tạp/không thể biểu đạt theo quy tắc ngôn ngữ sẽ làm compilation fail.

Bài nhập môn không cần dự đoán mọi capture/intersection type của JLS `18`. Khi gặp lỗi:
1. Xem compiler diagnostic với `javac --release 17`.
2. Thêm target type rõ ở biến/argument.
3. Ghi explicit type arguments ở `new Generic<Args>(...)` nếu dễ hiểu hơn.
4. Đổi anonymous class thành named class hoặc lambda (nếu phù hợp functional interface semantics).
5. Giảm overload ambiguity hoặc wildcard nesting.

**Đừng sửa bằng raw type để “đè” warning/error**: raw type có thể xóa lợi ích type safety mà compiler đang cố bảo vệ.

## 40. Raw types và unchecked warnings

Xét:

```java
List values = new ArrayList();
values.add("A");
values.add(12);
```

`List`/`ArrayList` ở đây là raw types. Compiler có thể cảnh báo unchecked operations khi thêm phần tử. Lúc truy xuất vào context kỳ vọng String có thể gặp `ClassCastException` ở runtime.

So sánh:

```java
List<String> values = new ArrayList<>();
values.add("A");
// values.add(12); // Compile error.
```

Diamond giữ static type checking của `String`. Raw type làm mất phần lớn generic safety.

### Dùng compiler flags để nhìn warning

```bash
javac --release 17 -Xlint:rawtypes,unchecked -encoding UTF-8 RawExample.java
```

Các thông báo warning cụ thể có thể khác theo JDK/build/line numbers; không nên đưa toàn bộ diagnostic như một stdout cố định.

## 41. Runnable: dùng diamond thay raw type

Lưu **`DiamondTypeSafetyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondTypeSafetyDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        words.add("Generics");

        String first = words.get(0);

        System.out.println(first);
        System.out.println(words.size());
    }
}
```

```bash
javac --release 17 -Xlint:rawtypes,unchecked -encoding UTF-8 DiamondTypeSafetyDemo.java
java DiamondTypeSafetyDemo
```

Stdout:

```text
Java
2
```

Trong ví dụ đúng này không có raw/unchecked conversion; cờ lint giúp phát hiện những chỗ khác trong dự án có thể đang mất type safety.

## 42. Heap pollution xảy ra khi nào?

**Heap pollution** là tình huống một variable có parameterized type tham chiếu tới object không tương thích với parameterization đã khai báo, thường thông qua raw/unchecked code hoặc unsafe varargs.

Diamond **không tạo heap pollution một cách tự nhiên**. Ngược lại, dùng raw types để né generic compiler error dễ đưa dữ liệu sai kiểu vào collection rồi phát nổ ở chỗ đọc.

Ví dụ minh họa compile được nhưng có unchecked warning:

```java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList();
raw.add(123);

List<String> strings = raw; // Unchecked conversion warning.
String text = strings.get(0); // Có thể ClassCastException.
```

Đây là **snippet** trong một scope hợp lệ. Đừng biến một warning thành bình thường trong code production nếu có giải pháp parameterized type rõ ràng.

## 43. Type erasure: `new Box<String>()` có khác runtime `new Box<Integer>()` không?

Trong generic Java thông thường, type arguments không tạo một class riêng ở runtime:

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(1);

System.out.println(a.getClass() == b.getClass());
```

Kết quả true với `Box` bình thường (không anonymous subclasses). Hai objects **khác nhau**, nhưng runtime class identity giống nhau.

Các hệ quả:
- Không viết `Box<String>.class`.
- Không viết `new T()` dựa trên generic parameter đơn thuần.
- Không dựa vào `instanceof Box<String>`.
- Khi cần runtime type validation, đưa vào `Class<T>` hoặc explicit factory/type token.
- Java vẫn thêm casts/checks tại những vị trí cần thiết để duy trì type semantics sau erasure.

`<>` không làm type arguments “biến mất thêm một lần nữa”; type erasure là semantics tổng quát của Java generics.

## 44. Runnable: type erasure không làm mất giá trị thật

Lưu **`DiamondErasureDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondErasureDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<>("A");
        Box<Integer> count = new Box<>(1);

        System.out.println(text.getClass() == count.getClass());
        System.out.println(text.value());
        System.out.println(count.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondErasureDemo.java
java DiamondErasureDemo
```

Stdout:

```text
true
A
1
```

Compile-time typing vẫn cho `String` và `Integer` khi gọi `value()` trên references được parameterize phù hợp.

## 45. Object creation vs generic factory methods

Hai cú pháp có thể cho kết quả tương tự:

**Constructor + diamond:**

```java
List<String> names = new ArrayList<>();
```

**Generic factory method:**

```java
List<String> names = List.of();
```

`List.of` là generic **method** và áp dụng method type inference, không phải diamond operator. Trong Java 17, `List.of()` trả unmodifiable list; `new ArrayList<>()` tạo mutable ArrayList. Vì vậy **chọn API khác là chọn semantics khác**, không chỉ cú pháp.

Đối với Map:
- `new HashMap<>()` là mutable.
- `Map.of()` trả unmodifiable map.
- `Map.copyOf(map)` tạo unmodifiable map từ nguồn theo contract.

Đừng thay constructor bằng factory chỉ để “ngắn hơn” nếu mutability, null allowance, ordering, performance và ownership khác.

## 46. Runnable: List factory khác mutable list

Lưu **`FactoryVsDiamondDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FactoryVsDiamondDemo {
    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>();
        List<String> fixed = List.of("A", "B");

        mutable.add("C");

        System.out.println(mutable);
        System.out.println(fixed);

        try {
            fixed.add("D");
        } catch (UnsupportedOperationException error) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FactoryVsDiamondDemo.java
java FactoryVsDiamondDemo
```

Stdout:

```text
[C]
[A, B]
unmodifiable
```

Factory API semantics khác constructor, dù cả hai dùng generic type inference ở những cách khác nhau.

## 47. Generic constructor không tự tạo object type argument

Một generic wrapper:

```java
final class FactoryBox<T> {
    private final T value;

    FactoryBox(T value) {
        this.value = value;
    }
}
```

Muốn tự tạo một instance T mà không có argument, bạn **không thể** viết `new T()` vì T là type variable, không phải concrete class token/constructor reference ở runtime.

Cách rõ hơn:

```java
static <T> T create(java.util.function.Supplier<T> factory) {
    return factory.get();
}
```

Caller có thể truyền constructor reference/lambda thích hợp:

```java
java.util.ArrayList<String> list =
        create(java.util.ArrayList::new);
```

Đây là snippet không phụ thuộc `<>` trực tiếp; generic inference ở method `create` cùng target typing của method reference mới thực hiện công việc.

**Tách hai câu hỏi:** “Tôi muốn object có static type gì?” khác “Tôi có cách nào thật sự cấp phát object T lúc runtime?”.

## 48. Runnable: Supplier thay `new T()`

Lưu **`GenericFactorySupplierDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class GenericFactorySupplierDemo {
    static <T> T create(Supplier<T> constructor) {
        return constructor.get();
    }

    public static void main(String[] args) {
        List<String> values = create(ArrayList::new);
        values.add("Java");

        System.out.println(values);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 GenericFactorySupplierDemo.java
java GenericFactorySupplierDemo
```

Stdout:

```text
[Java]
```

Không thể thay thân `create` bằng `return new T();`. Supplier cung cấp hành vi tạo concrete object.

## 49. Diamond với interface reference: static API vs implementation

```java
List<String> list = new ArrayList<>();
```

Kiểu tĩnh của biến là `List<String>`; concrete class được tạo là `ArrayList`. Đây là cách lập trình phụ thuộc abstraction interface.

Ngược lại:

```java
var list = new ArrayList<String>();
```

Kiểu tĩnh của `list` là `ArrayList<String>`. Với API lớn, điều này có thể làm caller vô tình phụ thuộc methods chỉ có ở implementation concrete.

**Không có một đáp án luôn đúng**. Nếu API/caller chỉ cần List operations, declaring interface type giúp linh hoạt thay implementation sau này. Với local variable rất ngắn hoặc cần methods concrete, `var` có thể giúp code súc tích.

### Đừng nhầm target type với runtime object type

Dù declared type `List<String>`, runtime instance vẫn là `ArrayList` nếu tạo bằng `new ArrayList<>()`. Diamond không làm instantiate interface.

## 50. Diamond với nested generic types

Có thể dùng parameterized type lồng nhau:

```java
Map<String, List<Integer>> grouped =
        new HashMap<>();
```

Khi thêm values:

```java
grouped.put("A", new ArrayList<>());
grouped.get("A").add(1);
```

Compiler có thể suy luận element type của new ArrayList từ method invocation `put`/target argument type.

### Runnable

Lưu **`NestedDiamondDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NestedDiamondDemo {
    public static void main(String[] args) {
        Map<String, List<Integer>> grouped =
                new HashMap<>();

        grouped.put("A", new ArrayList<>());
        grouped.get("A").add(1);
        grouped.get("A").add(2);

        System.out.println(grouped.get("A"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NestedDiamondDemo.java
java NestedDiamondDemo
```

Stdout:

```text
[1, 2]
```

Đây là một ví dụ type inference lồng nhau, nhưng khá rõ vì map value type đã được công bố là `List<Integer>`.

## 51. Lỗi thường gặp khi kết hợp `<>` và `null`

```java
Box<String> a = new Box<>(null);
```

Nếu constructor `Box(T)` cho phép null, compiler có thể suy luận `T=String` từ target type dù argument expression null không tự cung cấp kiểu concrete.

Ngược lại:

```java
var b = new Box<>(null);
```

không có target parameterized type rõ. Với unbounded T, inferred type có thể là `Object`; không nên giả định `String` chỉ vì dự định xử lý text.

Nếu class có nhiều constructors nhận unrelated reference types, `null` còn có thể làm constructor call ambiguous.

### Quy tắc làm code dễ đọc

- Nếu giá trị null có nghĩa domain, nêu target type rõ.
- Tốt hơn, hạn chế null bằng validation/factory.
- Nếu `null` dùng để chọn overload, cast một reference type cụ thể hoặc sửa API tránh ambiguity.
- Không dùng raw type để “giải quyết” inference: nó chỉ bỏ đi checks.

## 52. Runnable: null được ràng buộc bởi target type

Lưu **`NullDiamondDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class NullDiamondDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<>(null);

        System.out.println(text.value() == null);
        System.out.println(text.getClass().getSimpleName());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NullDiamondDemo.java
java NullDiamondDemo
```

Stdout:

```text
true
Box
```

Target type giữ ý định compile-time `Box<String>`, nhưng runtime vẫn là class `Box`. Không gọi method trên `text.value()` nếu nó có thể null.

## 53. Diamond và các type arguments lồng nhiều cấp

Một declaration như:

```java
Map<String, Map<Long, List<String>>> index =
        new HashMap<>();
```

là hợp lệ. Diamond chỉ làm ngắn **class instance creation** hiện tại, không xoá các parameterizations khỏi target type.

Nếu tại constructor argument hoặc `var` không có đủ constraints, compiler có thể suy ra types khác người đọc kỳ vọng. Trong code phức tạp, explicit generic types tại boundary của method/field thường giúp duy trì API contract.

### Khi nào explicit đáng giá hơn diamond?

- Khi cần thể hiện một API guarantee ở ngay call site.
- Khi compiler error khó hiểu do nested inference.
- Khi mixed numeric types có thể suy ra một common supertype rộng.
- Khi `var` và no-arg constructor làm type quá rộng.
- Khi muốn reviewer nhận diện chỗ mutable vs immutable collections, constructor overload và target contract.

Không có quy tắc “luôn dùng diamond” bất kể readability.

## 54. Method overload không chỉ khác generic type arguments do erasure

Đoạn sau cố ý sai:

```java
class BadOverload {
    void handle(java.util.List<String> strings) {
    }

    void handle(java.util.List<Integer> integers) {
    }
}
```

Hai methods có cùng erased signature tương ứng `handle(List)`, nên Java không cho overload chỉ khác generic type argument theo cách này.

Điều này **không phải lỗi của diamond**. Nếu bạn gặp compiler diagnostic vì generic erasure, thay đổi overload API bằng tên methods khác, các parameter types thực sự khác sau erasure hoặc một phương thức generic được thiết kế phù hợp.

Ví dụ rõ:

```java
void handleStrings(List<String> strings) { ... }
void handleIntegers(List<Integer> integers) { ... }
```

Các dòng trên là pseudocode snippets với method bodies rút gọn, không phải standalone Java programs.

## 55. Không tạo generic array bằng diamond

```java
// Compile-negative:
List<String>[] rows = new ArrayList<>[5];
```

Java array creation không hỗ trợ cú pháp diamond `new ArrayList<>[5]`. Việc tạo array của non-reifiable parameterized type cũng bị hạn chế bởi generic array creation rules.

Nếu muốn collection các collections:

```java
List<List<String>> rows = new ArrayList<>();
rows.add(new ArrayList<>());
```

Đây là lựa chọn thường an toàn hơn: outer list quản lý danh sách inner lists, thay vì ép tạo generic array khó kiểm tra kiểu runtime.

### Array `new String[5]` vẫn hợp lệ

Arrays và generic collections có type rules khác nhau. `String[]` là reifiable array element type; `List<String>[]` không thể đơn giản tạo theo cách tương đương.

## 56. `Class<T>` token là giải pháp cho nhu cầu runtime type

Nếu một API thực sự cần bảo đảm object chứa giá trị runtime thuộc kiểu T, có thể nhận `Class<T>`:

```java
final class TypedBox<T> {
    private final Class<T> type;
    private final T value;

    TypedBox(Class<T> type, T value) {
        this.type = type;
        this.value = type.cast(value);
    }
}
```

`String.class` là class token `Class<String>`. Token tồn tại runtime; diamond tự nó không đưa một token vào object.

### Lưu ý generics nested

`Class<List<String>>` không thể được viết thành `List<String>.class`. Một Class token cho raw runtime `List.class` không xác nhận kiểu mọi element của list. Muốn validate `List<String>`, phải kiểm tra elements hoặc dùng một type-token framework phù hợp.

## 57. Runnable: `Class<T>` với diamond

Lưu **`ClassTokenDiamondDemo.java`**:

```java
final class TypedBox<T> {
    private final Class<T> type;
    private final T value;

    TypedBox(Class<T> type, T value) {
        this.type = type;
        this.value = type.cast(value);
    }

    T value() {
        return value;
    }

    String typeName() {
        return type.getSimpleName();
    }
}

public class ClassTokenDiamondDemo {
    public static void main(String[] args) {
        TypedBox<String> text =
                new TypedBox<>(String.class, "Java");

        System.out.println(text.typeName());
        System.out.println(text.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ClassTokenDiamondDemo.java
java ClassTokenDiamondDemo
```

Stdout:

```text
String
Java
```

Class token có vai trò riêng: runtime validation/metadata. Diamond xử lý class type inference ở compile time.

## 58. Khi refactor constructor signatures, inference có thể thay đổi

Code hôm nay:

```java
Box<String> box = new Box<>("A");
```

Khi sửa class `Box` để thêm constructor overload hoặc generic bounds, compiler có thể lựa chọn overload khác, báo ambiguity hoặc inference constraints khác. Vì thế:
- Mỗi overload có contract riêng phải kiểm thử.
- Không dựa vào inference mơ hồ khi có nhiều `null` arguments.
- Trong public libraries, thêm overload có thể ảnh hưởng source compatibility.
- Nếu muốn semantics riêng, đặt tên factory methods.
- Dùng `javac --release 17 -Xlint:all` trong CI khi phù hợp (không bắt mọi dự án bật mọi cảnh báo ngay).

Diamond không phải “hộp đen tự chọn constructor đúng ý định”; compiler chọn theo static language rules.

## 59. Nên viết explicit hay diamond trong code thực tế?

**Thường ưu tiên diamond** khi target type rõ:

```java
List<String> names = new ArrayList<>();
Map<String, Long> prices = new HashMap<>();
Box<Integer> value = new Box<>(7);
```

**Ưu tiên explicit** khi suy luận có thể làm mất ý định:

```java
var names = new ArrayList<String>();
var box = new Box<Integer>(7);
```

**Có thể dùng `var` với diamond** khi constructor argument ràng buộc được type rõ:

```java
var box = new Box<>("hello");
```

**Tránh raw:**

```java
Box box = new Box("hello");
```

### Đưa abstraction vào biến khi phù hợp

`List<String> names = new ArrayList<>()` có thể là lựa chọn tốt hơn `var names = new ArrayList<String>()` nếu phần còn lại của code nên phụ thuộc List API chứ không phải ArrayList implementation.

## 60. Bài tập 1 — Xác định type parameter

```java
class Cache<K, V> {
}
```

**Câu hỏi:** `K`, `V` là type parameters hay type arguments?

**Đáp án:** Type parameters trong khai báo generic class.

## 61. Bài tập 2 — Type arguments tường minh

```java
Cache<String, Integer> cache;
```

**Đáp án:** String và Integer là type arguments của parameterized type `Cache<String,Integer>`.

## 62. Bài tập 3 — Ý nghĩa diamond

```java
List<String> names = new ArrayList<>();
```

Compiler bỏ generic checking vì `<>` trống không?

**Đáp án:** Không. Compiler suy luận type arguments phù hợp target; khác raw `new ArrayList()`.

## 63. Bài tập 4 — Raw type

```java
List values = new ArrayList();
```

**Đáp án:** Đây là raw-type usage, không phải diamond. Nó giảm compile-time element type checks và có thể phát warnings.

## 64. Bài tập 5 — Type sau `var`

```java
var names = new ArrayList<>();
```

Không có constructor arguments hay target parameterized type. `names` được suy ra dạng gì?

**Đáp án:** Thông thường `ArrayList<Object>` với ArrayList không có bounds hẹp hơn.

## 65. Bài tập 6 — Ghi kiểu rõ khi `var`

Muốn var nhưng danh sách chỉ chứa String:

```java
var names = new ArrayList<String>();
```

**Đáp án:** Hợp lệ; static type được suy ra là `ArrayList<String>`.

## 66. Bài tập 7 — Boxing

```java
var box = new Box<>(17);
```

Trong một Box unbounded nhận T, kiểu T được suy luận theo hướng nào?

**Đáp án:** `Integer` (boxed int), không phải `int` làm generic type argument.

## 67. Bài tập 8 — Primitive generic argument

`Box<int> box = new Box<int>(1);` có hợp lệ không?

**Đáp án:** Không. Generic type arguments phải là reference types; dùng `Integer`.

## 68. Bài tập 9 — Invariance

`Box<Integer> ints = new Box<>(7);`. Có gán trực tiếp nó cho `Box<Number>` được không?

**Đáp án:** Không. `Box<Integer>` không là subtype của `Box<Number>` do invariance.

## 69. Bài tập 10 — Wildcard

`Box<? extends Number> n = new Box<>(7);` có thể đọc `Number` từ `n.value()` không?

**Đáp án:** Có, theo upper bound; không nên coi nó là mutable Box có thể nhận bất kỳ Number.

## 70. Bài tập 11 — Generic bound

`NumericBox<T extends Number>`. Có dùng `new NumericBox<String>("A")` không?

**Đáp án:** Không; String không thỏa Number bound, dù có hay không dùng diamond.

## 71. Bài tập 12 — Tạo interface

`List<String> xs = new List<>();` có biên dịch không?

**Đáp án:** Không. List là interface; dùng concrete implementation như ArrayList.

## 72. Bài tập 13 — Target typing

`List<String> xs = new ArrayList<>();`, không truyền elements. Compiler lấy thông tin String từ đâu?

**Đáp án:** Từ target type `List<String>` của assignment.

## 73. Bài tập 14 — Method argument

Method nhận `List<String>`, caller truyền `new ArrayList<>()`. Diamond có thể suy luận String không?

**Đáp án:** Có, khi method invocation và constraints phù hợp; target parameter type tham gia inference.

## 74. Bài tập 15 — Return context

Method khai báo `List<String> create()` và trả `new ArrayList<>()`.

**Đáp án:** Hợp lệ; return target type giúp suy luận.

## 75. Bài tập 16 — Constructor generic riêng

`class Entry<T> { <U extends Number> Entry(T value,U weight){} }`.

**Đáp án:** T thuộc class; U thuộc constructor. Diamond trên `Entry` giải quyết class type argument T, constructor inference giải quyết U theo rules tương ứng.

## 76. Bài tập 17 — Null và target

`Box<String> box = new Box<>(null);`, constructor Box(T) cho phép null.

**Đáp án:** Có thể hợp lệ; target `Box<String>` định hướng T=String dù argument null.

## 77. Bài tập 18 — Null và overloads

`Choice(String)` và `Choice(Integer)` cùng tồn tại, `new Choice<>(null)`.

**Đáp án:** Có thể ambiguous; cast `(String)null` hoặc dùng named factory.

## 78. Bài tập 19 — Runtime class

`new Box<String>("x")` và `new Box<Integer>(1)` có runtime class tách biệt cho hai type arguments không?

**Đáp án:** Không theo Java generics erasure bình thường; cả hai instances có runtime `Box.class`.

## 79. Bài tập 20 — `instanceof` với parameterized type

`obj instanceof Box<String>` hợp lệ không?

**Đáp án:** Không vì `Box<String>` không phải reifiable type trong kiểm tra instanceof theo cú pháp này. Dùng `Box<?>` nếu chỉ muốn kiểm tra raw runtime class phù hợp.

## 80. Bài tập 21 — Generic array

`new List<String>[3]` hợp lệ không?

**Đáp án:** Không; generic array creation bị Java cấm cho parameterized element type không reifiable.

## 81. Bài tập 22 — `new T()`

`class Factory<T> { T create(){ return new T(); } }` hợp lệ?

**Đáp án:** Không. Type variable T không trực tiếp cung cấp concrete constructor/runtime class; dùng Supplier/factory.

## 82. Bài tập 23 — Anonymous diamond từ Java mấy?

Cú pháp `new Supplier<>() { @Override public String get(){return "A";} }` có được Java 17 hỗ trợ không?

**Đáp án:** Có, diamond trong anonymous class được cho phép từ Java 9 với các hạn chế thích hợp.

## 83. Bài tập 24 — Anonymous method riêng

Trong diamond anonymous class, có thể thêm một public method hoàn toàn mới không override/implement không?

**Đáp án:** Không trong ngữ cảnh bị quy tắc Java 17 ràng buộc; non-private methods phải override/implement appropriate supertype methods. Dùng private helper hoặc named class.

## 84. Bài tập 25 — Anonymous subclass runtime

`new Holder<>("A") { @Override String value(){...} }` có runtime class bằng `Holder.class` không?

**Đáp án:** Không. Đây là anonymous subclass; runtime class khác. Khác biệt do anonymous subclass declaration, không do diamond.

## 85. Bài tập 26 — `List.of` và `new ArrayList<>()`

Hai biểu thức đều có generic type inference nhưng cho cùng mutability semantics không?

**Đáp án:** Không. `List.of` cho unmodifiable list theo JDK contract; ArrayList là mutable.

## 86. Bài tập 27 — Nested generics

`Map<String,List<Integer>> map = new HashMap<>();` có cần lặp `<String,List<Integer>>` phía sau HashMap không?

**Đáp án:** Không khi compiler suy luận được từ target type; diamond giúp tránh lặp.

## 87. Bài tập 28 — Generic erasure overload

Có overload được `handle(List<String>)` và `handle(List<Integer>)` trong cùng class không?

**Đáp án:** Không; cả hai erasure thành `handle(List)` và xung đột signature.

## 88. Bài tập 29 — Class token

Diamond tự mang `Class<String>` runtime token vào object không?

**Đáp án:** Không. Nếu cần runtime type token, truyền explicit `String.class`/factory hoặc type-token abstraction thích hợp.

## 89. Bài tập 30 — Chọn cú pháp tối ưu

Bạn cần danh sách String rỗng, API chỉ thao tác List, code phải type-safe và rõ.

**Đáp án:** `List<String> values = new ArrayList<>();` là lựa chọn thông dụng. Không dùng raw `List` hoặc `var values = new ArrayList<>()` nếu muốn element type String rõ ngay từ đầu.

## 90. Bài tập 31 — Mục đích target type

`Box<Number> box = new Box<>(Integer.valueOf(3));`. Điều gì khiến bạn không nên luôn suy T=Integer?

**Đáp án:** Target type `Box<Number>` cũng tham gia constraints; compiler có thể suy parameterization phù hợp Number, trong khi runtime value vẫn Integer.

## 91. Bài tập 32 — Đọc compiler diagnostic

Compiler báo type inference failed khi `new Pair<>(...)` với wildcard và overload phức tạp.

**Đáp án:** Kiểm tra constructor overloads/bounds/target; tách biến trung gian, ghi explicit type arguments hoặc đổi API. Không vội chuyển sang raw type/cast unchecked.

## 92. Bài tập 33 — Câu hỏi Đúng/Sai

1. `<>` là raw type.
2. `new Box<String>("A")` ghi tường minh class type argument.
3. Diamond inference chỉ phụ thuộc runtime class của object được truyền.
4. `var xs = new ArrayList<>()` luôn suy String vì tên biến xs.
5. Type arguments của generics có thể dùng primitive `int`.
6. `Box<Integer>` không tự là subtype của `Box<Number>`.
7. `List<String> xs = new ArrayList<>()` là parameterized, type-safe.
8. Java 17 cho diamond với anonymous class trong điều kiện hợp lệ.
9. `new T()` hợp lệ khi T là generic type variable.
10. Hai Box với type arguments khác nhau có thể cùng runtime class do erasure.
11. `List.of()` và `new ArrayList<>()` luôn có mutability giống nhau.
12. Bounded generic type inference phải thỏa bounds.

**Đáp án:** 1 sai; 2 đúng; 3 sai; 4 sai; 5 sai; 6 đúng; 7 đúng; 8 đúng; 9 sai; 10 đúng; 11 sai; 12 đúng.

## 93. Những sai lầm và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi `new Box<>()` là raw type | Hiểu sai compiler inference | Phân biệt với `new Box()` |
| Coi diamond là kiểu động runtime | Kỳ vọng sai type validation/runtime classes | Hiểu static inference + erasure |
| `var xs = new ArrayList<>()` rồi giả định String | Inference rộng thành Object | `var xs = new ArrayList<String>()` hoặc `List<String> xs = new ArrayList<>()` |
| `new List<>()` | Không thể instantiate interface | `new ArrayList<>()` |
| `new Box<int>()` | Primitive type argument không hợp lệ | Dùng Integer |
| `Box<Number> x = new Box<Integer>(1)` | Generic invariance | Tạo `new Box<Number>(1)` hoặc wildcard khi đọc |
| `new T()` | T bị erasure và không là concrete type | Supplier/Factory/Class token |
| `new List<String>[3]` | Generic array creation lỗi | List of lists hoặc thiết kế array hợp lệ |
| `new Box<>(null)` rồi kỳ vọng String khi không target | Type inference có thể rộng hoặc overload ambiguous | Target/explicit type/cast/factory |
| Coi `Supplier<>` anonymous luôn bị cấm | Áp quy tắc Java 7/8 lên Java 17 | Kiểm tra Java 9+ support/constraints |
| Non-private new method trong anonymous diamond | Có thể bị compiler từ chối | Private helper/override/named class |
| Dùng raw để thoát lỗi bounds | Mất type safety/unchecked warnings | Sửa actual generic constraints |
| Tưởng `<>` có runtime `Class<T>` | Không thể runtime validate T như mong muốn | Truyền Class token riêng |
| Coi factory `List.of` như ArrayList constructor | Nhầm immutable/unmodifiable/mutable behavior | Đọc API contract |
| Overload methods chỉ khác `List<String>`/`List<Integer>` | Erasure signature clash | Đổi method names hoặc API design |
| Không test inference sau đổi constructors | Source compatibility/overload behavior khác | Compiler/CI tests với đúng JDK release |

## 94. Checklist code review

- [ ] Generic class khai báo đúng formal type parameters và bounds.
- [ ] Đối số kiểu tường minh được sử dụng ở vị trí `Class<Type>` thích hợp.
- [ ] Diamond được viết chính xác là `<>` tại class instance creation.
- [ ] Không nhầm raw `new Generic()` với diamond `new Generic<>()`.
- [ ] Target type rõ khi constructor arguments không đủ inference.
- [ ] Nếu dùng `var` với no-arg diamond, đã xác nhận inferred type mong muốn.
- [ ] Nếu dùng `var` với arguments, inferred class/element type được kiểm tra.
- [ ] Không truyền primitive type làm generic type argument.
- [ ] Generic bounds thỏa những type arguments đã chọn.
- [ ] Không vi phạm invariance `Generic<Sub>` vs `Generic<Super>`.
- [ ] Wildcards `extends`/`super` được chọn theo producer/consumer behavior.
- [ ] Không nhầm wildcard `?` với diamond `<>`.
- [ ] Constructor overloads không ambiguous với `null`.
- [ ] Static type của arguments và target context được xét, không dựa vào runtime class.
- [ ] Không instantiate interface/abstract class trực tiếp khi không hợp lệ.
- [ ] Không dùng `new T()` mà thiếu factory/runtime type mechanism.
- [ ] Không tạo array của non-reifiable parameterized type.
- [ ] Không dùng generic type arguments để kỳ vọng runtime subclass specialization.
- [ ] Không dùng `instanceof Generic<String>` không reifiable.
- [ ] Nếu cần runtime validation, có Class token/checked mapper phù hợp.
- [ ] Generic constructor type variables và generic class type variables được phân biệt.
- [ ] Diamond với anonymous class tuân Java 9+ restrictions.
- [ ] Các non-private methods trong anonymous diamond body thực sự override/implement.
- [ ] Nếu chọn anonymous class, đã xét subclass access, constructor và maintainability.
- [ ] Nếu dùng raw types vì legacy API, warning/unchecked casts được cô lập và kiểm chứng.
- [ ] Không có heap pollution do raw assignment không được kiểm soát.
- [ ] Collections chọn constructor hay factory theo mutability/ownership đúng contract.
- [ ] Với mutable collections, đã xem xét defensive copy nếu yêu cầu.
- [ ] Method parameter/return target typing không làm API overload khó hiểu.
- [ ] Nếu inference khó đọc, thêm type rõ tại boundary hoặc local variable.
- [ ] Không overload methods chỉ khác generic args bị erasure trùng signature.
- [ ] Không phụ thuộc tên generated runtime class để xác định type argument.
- [ ] Source build/test dùng `javac --release 17`.
- [ ] Mọi runnable example có file name trùng public class và stdout xác định.
- [ ] Compile-negative snippets được phân biệt rõ.
- [ ] API consumers được kiểm tra khi thêm/chỉnh constructor overload/generic bounds.

## 95. Tổng kết

**Khi tạo đối tượng generic trong Java 17**, có thể viết rõ đối số kiểu:

```java
Box<String> a = new Box<String>("A");
```

hoặc dùng diamond cho compiler suy luận:

```java
Box<String> b = new Box<>("B");
```

Diamond phù hợp khi ngữ cảnh đã cung cấp đủ constraints, chẳng hạn target type `List<String>`, constructor arguments hoặc method return/argument context. Nhưng với `var` và constructor rỗng, inference có thể chọn type rộng như Object, nên cần thể hiện type rõ nếu ý định không hiển nhiên.

**Phân biệt không thể bỏ qua:** `new Box<>()` **không phải** raw `new Box()`. Generics và type checking vẫn hoạt động. Diamond cũng không khôi phục concrete type arguments ở runtime sau erasure, không cho phép primitive type arguments, không vượt bounds, không tạo instance của interfaces và không cho phép `new T()`.

Với anonymous classes, Java 17 hỗ trợ diamond theo quy tắc từ Java 9, kèm những hạn chế đáng nhớ về non-private methods. Với collections/factories, luôn xét type safety, mutability và API semantics thay vì chỉ nhìn cú pháp ngắn.

**Cách nhớ:** `<>` nghĩa là **“compiler, hãy suy luận những type arguments hợp lệ từ constraints hiện có”**; không phải **“bỏ generic typing”** hoặc **“để runtime đoán kiểu”**.

## Nguồn chuẩn Java SE 17

- **JLS `15.9 — Class Instance Creation Expressions`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9
- **JLS `15.9.1 — Determining the Class being Instantiated`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.1
- **JLS `15.9.3 — Choosing the Constructor and its Arguments`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.3
- **JLS `15.9.5 — Anonymous Class Declarations`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5
- **JLS `18 — Type Inference`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html
- **JLS `4.5 — Parameterized Types`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5
- **JLS `4.8 — Raw Types`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8
- **JLS `4.6 — Type Erasure`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6
