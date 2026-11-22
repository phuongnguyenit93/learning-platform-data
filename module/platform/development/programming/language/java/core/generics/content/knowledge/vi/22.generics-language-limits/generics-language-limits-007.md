# Không cung cấp giá trị mặc định cho tham số kiểu trong Java Generics

## 1. Giới hạn ngôn ngữ cần nhớ

Trong Java, khi khai báo một generic class, interface, record hoặc generic method, ta có thể khai báo **tham số kiểu** (*type parameter*) và đặt **giới hạn** (*bound*) cho tham số đó. Nhưng Java **không có cú pháp khai báo giá trị mặc định cho type parameter**, chẳng hạn “nếu caller không viết đối số kiểu thì tự coi `T` là `String`”.

Các đoạn sau **cố ý không hợp lệ** trong Java 17:

```java
// CỐ Ý KHÔNG BIÊN DỊCH — Java không hỗ trợ default type argument.
class Box<T = String> { }

interface Repository<T = Object> { }

record Pair<K, V = String>(K key, V value) { }

class Utility {
    static <T = String> T make() {
        return null;
    }
}
```

`T = String`, `V = String` hay `<T = String>` không thuộc cú pháp hợp lệ của khai báo generic Java. Không thể sửa bằng cách thay `String` thành `Object`, dùng một wrapper khác hoặc thêm annotation.

Dạng hợp lệ là:

```java
class Box<T> { }

interface Repository<T> { }

record Pair<K, V>(K key, V value) { }

class Utility {
    static <T> T make() {
        return null;
    }
}
```

Nếu muốn giới hạn các kiểu được chấp nhận, Java cung cấp `extends`, ví dụ `<T extends Number>`. Nếu muốn bỏ bớt việc viết đối số kiểu ở **vị trí gọi**, Java cung cấp **type inference** và **diamond operator `<>`**. Nếu muốn một lựa chọn mặc định có **ngữ nghĩa nghiệp vụ** như “dùng `String`”, hãy tạo factory method hoặc subtype chuyên biệt.

> **Điểm phân biệt cốt lõi:** *Default type argument* là quy tắc gắn ngay trong khai báo tham số kiểu; *type inference* là quá trình compiler tìm kiểu thích hợp cho **mỗi biểu thức/lời gọi** dựa trên ngữ cảnh và các ràng buộc. Java hỗ trợ cơ chế thứ hai, không hỗ trợ cơ chế thứ nhất.

## 2. Thuật ngữ: type parameter, type argument, bound và inference

Xét:

```java
class Holder<T> {
    T value;
}
```

- `T` trong `class Holder<T>` là **type parameter** được khai báo.
- `String` trong `Holder<String>` là **type argument** được cung cấp khi sử dụng.
- Trong `Holder<T extends Number>`, `Number` là **upper bound**, ràng buộc những kiểu có thể dùng thay `T`.
- Trong `new Holder<>()`, `<>` yêu cầu compiler **suy luận type arguments** tại biểu thức tạo đối tượng.
- Trong `Holder<?>`, `?` là **wildcard**, biểu diễn type argument chưa xác định, không phải default `Object`.

Các cách sử dụng có ý nghĩa khác nhau:

| Cú pháp | Hợp lệ? | Ý nghĩa |
|---|---|---|
| `class Holder<T> {}` | Có | Khai báo một type parameter `T` |
| `class Holder<T = String> {}` | Không | Java không hỗ trợ default type argument |
| `class Holder<T extends Number> {}` | Có | Giới hạn `T` là subtype của `Number` |
| `Holder<String> h;` | Có | Dùng type argument tường minh `String` |
| `Holder<?> h;` | Có | Dùng wildcard cho đối số kiểu chưa biết |
| `Holder h;` | Có, không khuyến khích | Dùng **raw type** và bỏ kiểm tra generic tại nhiều chỗ |
| `Holder<> h;` | Không | Diamond không dùng trong tên kiểu ở khai báo biến |
| `Holder<String> h = new Holder<>();` | Có | Diamond suy luận từ target type |
| `var h = new Holder<>();` | Có nếu constructor phù hợp | `var` lấy kiểu từ initializer, không đặt default `String` |

Đừng đánh đồng việc compiler “đoán” được một kiểu với việc class đã khai báo kiểu mặc định.

## 3. Vì sao thiếu đối số kiểu không có nghĩa “dùng mặc định”?

Giả sử class:

```java
class Container<T> {
    T value;
}
```

Có ba cách nhìn:

```java
Container<String> typed = new Container<>();
Container raw = new Container();
var inferred = new Container<>();
```

Trong ví dụ này, constructor mặc định do Java tạo ra có thể được gọi không đối số vì class không khai báo constructor riêng.

- `typed` có kiểu tĩnh `Container<String>` nhờ khai báo bên trái.
- `raw` có kiểu thô `Container`; compiler không biết đối số `T`, và một số thao tác có thể tạo cảnh báo `rawtypes`/`unchecked`.
- `inferred` không có `String` làm ngữ cảnh đích và constructor cũng không nhận đối số. Với một `T` không bị ràng buộc như trên, compiler suy luận `Object`; biến có kiểu tĩnh `Container<Object>`.

Kết quả `Object` trong tình huống cuối là **kết quả của suy luận kiểu không có ràng buộc cụ thể hơn**, không phải default type argument do `Container<T>` khai báo. Nếu constructor có tham số hoặc biểu thức có target type khác, kết quả có thể khác.

Câu “Java tự mặc định mọi `T` thành `Object`” cũng **không đúng**. Type variables có thể có bounds; type inference dùng ngữ cảnh và quy tắc lựa chọn kiểu. `Object` chỉ là một trường hợp thường gặp với type parameter không bound và biểu thức thiếu ràng buộc cụ thể.

## 4. Ví dụ chạy được: diamond không đồng nghĩa default type

Tạo tệp **`NoDefaultTypeArgumentDemo.java`**:

```java
public class NoDefaultTypeArgumentDemo {

    static class Box<T> {
        private T value;

        Box() {
        }

        Box(T value) {
            this.value = value;
        }

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> targeted = new Box<>();
        targeted.set("Java");

        var inferred = new Box<>(42);
        Integer n = inferred.get();

        var noTarget = new Box<>();
        noTarget.set("first");
        noTarget.set(3);
        Object last = noTarget.get();

        System.out.println(targeted.get());
        System.out.println(n);
        System.out.println(last);
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên:

```bash
javac NoDefaultTypeArgumentDemo.java
java NoDefaultTypeArgumentDemo
```

Stdout:

```text
Java
42
3
```

Phân tích:

1. `Box<String> targeted = new Box<>()` có ngữ cảnh đích `Box<String>`; constructor không nhận tham số vẫn suy luận được `T = String`.
2. `var inferred = new Box<>(42)` không có target type do `var`, nhưng **đối số constructor** `42` góp phần suy luận `T = Integer` (qua boxing).
3. `var noTarget = new Box<>()` không có ràng buộc cho type variable `T` không giới hạn, nên suy luận kiểu phần tử là `Object`.
4. `noTarget.set("first")` và `noTarget.set(3)` đều hợp lệ vì `String` và `Integer` đều là các reference types gán được cho `Object`.
5. Các lệnh `set(...)` **sau** khai báo không khiến kiểu `noTarget` “học” từ `String` rồi đổi sang `Integer`; kiểu được quyết định ngay tại initializer.

Để tự kiểm tra compiler, thêm thử dòng dưới vào cuối `main`:

```java
// CỐ Ý LỖI, không thêm vào phiên bản chạy được:
// targeted.set(10); // Compiler từ chối vì T của targeted là String.
```

Diamond chỉ **lược bỏ việc viết lại** type argument khi compiler có thể suy luận được; nó không thêm cú pháp mặc định vào class `Box`.

## 5. `var` không cung cấp type argument mặc định

`var` là cơ chế **suy luận kiểu của biến cục bộ** (Java 10+), không phải ký hiệu cho một generic type argument tùy chọn.

So sánh:

```java
java.util.List<String> a = new java.util.ArrayList<>();
var b = new java.util.ArrayList<String>();
var c = new java.util.ArrayList<>();
```

Các kiểu tĩnh sau suy luận:

| Biến | Kiểu tĩnh |
|---|---|
| `a` | `List<String>` |
| `b` | `ArrayList<String>` |
| `c` | `ArrayList<Object>` khi không có thông tin cụ thể hơn |

Điều khác biệt giữa `a` và `b` không chỉ là cú pháp ngắn/dài: `a` khai báo qua interface `List`, còn `b` suy ra class triển khai cụ thể `ArrayList`.

Một hiểu nhầm phổ biến là:

> “Tôi viết `var list = new ArrayList<>()`, sau đó `list.add("A")`, vậy compiler sẽ mặc định kiểu của list là String.”

Sai: `list` đã được xác định là `ArrayList<Object>` trong trường hợp constructor không đối số và không có target type. Việc `add("A")` không sửa kiểu tĩnh của biến.

Nếu yêu cầu là một danh sách chuỗi, nên ghi rõ ý định bằng một trong hai cách:

```java
java.util.List<String> list = new java.util.ArrayList<>();
var another = new java.util.ArrayList<String>();
```

Hai dạng giúp compiler từ chối việc thêm `Integer` vào một danh sách dự định chỉ chứa `String`.

## 6. Type argument suy luận từ constructor khác với default

Một constructor có thể cung cấp thông tin cho compiler qua **kiểu các đối số được truyền vào**.

Tạo tệp **`ConstructorInferenceDemo.java`**:

```java
public class ConstructorInferenceDemo {

    record Pair<L, R>(L left, R right) {
    }

    public static void main(String[] args) {
        Pair<String, Integer> a = new Pair<>("age", 21);

        var b = new Pair<>("score", 99);

        String label = b.left();
        Integer score = b.right();

        System.out.println(a.left() + "=" + a.right());
        System.out.println(label + "=" + score);
    }
}
```

Lệnh:

```bash
javac ConstructorInferenceDemo.java
java ConstructorInferenceDemo
```

Stdout:

```text
age=21
score=99
```

Ở `new Pair<>("score", 99)`, compiler thấy các constructor arguments là `String` và `int` (được boxing thành `Integer` trong quá trình suy luận), vì vậy có thể suy ra type arguments `L = String`, `R = Integer` ngay cả khi vế trái là `var`.

Ở `new Pair<>("age", 21)`, target type `Pair<String, Integer>` cũng đóng góp ngữ cảnh suy luận.

Đây là hai nguồn ràng buộc khác nhau nhưng đều **thuộc lời gọi cụ thể**. Chúng không làm record `Pair<L,R>` nhận được hai default type arguments trong khai báo.

## 7. Upper bound không phải giá trị mặc định

Java hỗ trợ:

```java
class NumericBox<T extends Number> {
    T value;
}
```

Dòng `T extends Number` có nghĩa **`T` phải là `Number` hoặc subtype hợp lệ của `Number`**, không có nghĩa “`T` mặc định là `Number` mỗi khi bỏ `<...>`”.

Các cách dùng hợp lệ:

```java
NumericBox<Integer> a = new NumericBox<>();
NumericBox<Double> b = new NumericBox<>();
NumericBox<Number> c = new NumericBox<>();
```

Còn:

```java
// CỐ Ý KHÔNG HỢP LỆ:
NumericBox<String> bad = new NumericBox<>();
```

bị compiler từ chối vì `String` không kế thừa `Number`.

### Bound ảnh hưởng kết quả suy luận khi thiếu ràng buộc

Với một class như `NumericBox<T extends Number>`, nếu viết `var x = new NumericBox<>()` và không có dữ liệu để ràng buộc `T` cụ thể, compiler có thể chọn `Number` làm kiểu thích hợp theo các bounds. Điều này là **quy tắc type inference dựa trên upper bound**, không phải generic default được khai báo bằng cú pháp kiểu `T = Number`.

### Ví dụ chạy được với bound

Tệp **`BoundIsNotDefaultDemo.java`**:

```java
public class BoundIsNotDefaultDemo {

    static class NumericBox<T extends Number> {
        private T value;

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> integers = new NumericBox<>();
        integers.set(8);

        var inferred = new NumericBox<>();
        inferred.set(2.5);

        Number asNumber = inferred.get();

        System.out.println(integers.get());
        System.out.println(asNumber);
    }
}
```

Chạy:

```bash
javac BoundIsNotDefaultDemo.java
java BoundIsNotDefaultDemo
```

Stdout:

```text
8
2.5
```

Bất kể ví dụ dùng `<Integer>` tường minh hay suy luận từ `<>`, compiler vẫn kiểm tra giới hạn `T extends Number`. Upper bound làm **hẹp tập kiểu được phép**, còn default type argument (không tồn tại trong Java) sẽ là quy tắc **chọn một kiểu khi thiếu thông tin**.

Nếu có nhiều bounds, chẳng hạn `<T extends Number & Comparable<T>>`, cũng không có tham số kiểu mặc định. Thứ tự bounds ảnh hưởng erasure và những phương thức được phép gọi qua `T`, chứ không bổ sung cú pháp `= SomeType`.

## 8. Generic method cũng không có default type parameter

Giới hạn này không chỉ áp dụng cho class hoặc record. Phương thức generic được khai báo dạng:

```java
static <T> T identity(T value) {
    return value;
}
```

Không thể khai báo:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
static <T = String> T identity(T value) {
    return value;
}
```

Khi gọi `identity("hello")`, compiler có thể suy luận `T = String` từ đối số. Khi một lời gọi không có đủ thông tin, compiler tiếp tục áp dụng quy tắc inference, chứ không đọc một default type argument từ khai báo.

Một generic method có thể được gọi bằng **explicit type witness**:

```java
Utility.<String>identity("hello")
```

Nếu `identity` là static method khả kiến của `Utility` theo ngữ cảnh, `<String>` ở lời gọi **đặt type argument của method**. Nó không thay đổi cách method được khai báo và không phải phép cast.

## 9. Ví dụ chạy được: target typing và type witness của method

Tạo tệp **`GenericMethodInferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericMethodInferenceDemo {

    static <T> List<T> empty() {
        return new ArrayList<>();
    }

    static <T> T echo(T value) {
        return value;
    }

    public static void main(String[] args) {
        List<String> targetTyped = empty();
        targetTyped.add("A");

        var inferredWithoutTarget = empty();
        inferredWithoutTarget.add(10);
        inferredWithoutTarget.add("B");

        var explicitlyTyped =
                GenericMethodInferenceDemo.<String>empty();
        explicitlyTyped.add("C");

        String echoed = echo("Java");

        System.out.println(targetTyped);
        System.out.println(inferredWithoutTarget);
        System.out.println(explicitlyTyped);
        System.out.println(echoed);
    }
}
```

Biên dịch/chạy:

```bash
javac GenericMethodInferenceDemo.java
java GenericMethodInferenceDemo
```

Stdout:

```text
[A]
[10, B]
[C]
Java
```

Giải thích:

- `List<String> targetTyped = empty()` cung cấp target type để compiler suy luận `T` phù hợp với `String`.
- `var inferredWithoutTarget = empty()` không có target type `List<String>` và `empty()` không nhận tham số. Với `T` không bound trong ví dụ, `T` được suy luận thành `Object`.
- `GenericMethodInferenceDemo.<String>empty()` đặt type witness tường minh, khiến kết quả có kiểu `List<String>`.
- `echo("Java")` suy luận từ đối số `String` của method; không cần type witness.

`<String>` ở lời gọi static method chính là một cách **người gọi chọn type argument**, không phải một default được định nghĩa bởi `<T>`.

## 10. Không thể “bỏ đối số kiểu cuối” của một generic class

Trong một số ngôn ngữ có default generic parameters, có thể viết một kiểu nhiều tham số rồi lược bỏ một vài đối số phía sau. **Java không hỗ trợ quy ước đó.**

Cho:

```java
record Pair<K, V>(K key, V value) {
}
```

Các cách dùng:

```java
Pair<String, Integer> valid =
        new Pair<>("age", 20);
```

Và:

```java
// CỐ Ý KHÔNG HỢP LỆ:
Pair<String> missingOne;
Pair<String, Integer, Boolean> tooMany;
```

Ở tên kiểu `Pair<K,V>`, Java yêu cầu **đúng số lượng type arguments** tương ứng với khai báo nếu chọn dùng dạng parameterized type. Nó không tự bổ sung `V = Object`, `V = String` hoặc một kiểu nào khác để hoàn thành `Pair<String>`.

Nếu không viết type arguments ở kiểu biến:

```java
Pair raw;
```

thì đây là **raw type**, không phải “`Pair<Object,Object>` theo default”. Raw types được giữ để tương thích mã cũ nhưng có các hạn chế an toàn kiểu.

Lưu ý: Java có thể cho phép **suy luận toàn bộ type arguments** tại biểu thức tạo bằng diamond `new Pair<>(...)`. Điều này khác với việc viết thiếu một đối số trong tên kiểu `Pair<String>`.

## 11. `<>` không phải generic arguments tùy chọn ở mọi vị trí

Diamond `<>` là cú pháp dùng ở một số **class instance creation expressions** để suy luận type arguments. Nó không phải ký hiệu chung cho “bỏ các type arguments trong mọi nơi”.

So sánh:

```java
java.util.List<String> values = new java.util.ArrayList<>();
```

Dòng hợp lệ vì `<>` xuất hiện ở **vế phải tạo object**.

Nhưng:

```java
// CỐ Ý KHÔNG HỢP LỆ:
java.util.List<> values;
```

`List<>` không phải cú pháp khai báo generic type của biến. Khi cần một kiểu có đối số chưa biết, dùng `List<?>`:

```java
java.util.List<?> values = java.util.List.of("A");
```

`List<?>` có ý nghĩa “danh sách với type argument chưa xác định”, không có nghĩa “mặc định là `Object`” và không có nghĩa raw `List`.

### Wildcard cũng không phải default

`List<?>` chỉ mô tả giới hạn điều compiler có thể biết về một danh sách bất kỳ. Bạn có thể đọc phần tử như `Object`, nhưng không được thêm tùy tiện một `String` hoặc `Integer` vào danh sách có wildcard unknown.

`List<Object>` lại là một kiểu tham số hóa có đối số **cụ thể** `Object`; nó không thay thế trực tiếp được cho `List<String>` vì Java Generics invariant.

## 12. Constructor overload không đặt default cho T

Java hỗ trợ overload constructors hoặc tham số **giá trị** mặc định qua việc cung cấp overload, nhưng điều đó **không tương đương default type argument**.

Ví dụ:

```java
class Result<T> {
    private final T value;

    Result() {
        this.value = null;
    }

    Result(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Đây là class hợp lệ. Có hai constructor:

- `Result()` tạo object với field `value = null`.
- `Result(T value)` tạo object với một giá trị được truyền vào.

**Không có constructor nào nói `T` mặc định là `String`.** Nếu caller viết:

```java
Result<String> a = new Result<>();
Result<Integer> b = new Result<>();
```

cả hai dùng được constructor không đối số mà vẫn có type arguments khác nhau.

Một phương thức nhận một **giá trị mặc định** như `Result(T initialValue)` cũng không khai báo “kiểu `T` mặc định”. Type parameter và giá trị chứa trong object là hai cấp khái niệm khác nhau.

## 13. Thiết kế thay thế 1: static factory method trả kiểu cụ thể

Nếu yêu cầu nghiệp vụ là “khi muốn một kho chuỗi, có một cách gọi ngắn dễ hiểu”, hãy tạo factory có **return type cụ thể** thay vì tìm cú pháp `class Box<T = String>`.

Tạo tệp **`NamedFactoryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NamedFactoryDemo {

    static final class Box<T> {
        private final List<T> elements = new ArrayList<>();

        void add(T item) {
            elements.add(item);
        }

        List<T> items() {
            return List.copyOf(elements);
        }
    }

    static Box<String> strings() {
        return new Box<>();
    }

    static Box<Integer> integers() {
        return new Box<>();
    }

    static <T> Box<T> empty() {
        return new Box<>();
    }

    public static void main(String[] args) {
        var text = strings();
        text.add("A");

        var numbers = integers();
        numbers.add(10);

        Box<Long> longs = empty();
        longs.add(20L);

        System.out.println(text.items());
        System.out.println(numbers.items());
        System.out.println(longs.items());
    }
}
```

Chạy:

```bash
javac NamedFactoryDemo.java
java NamedFactoryDemo
```

Stdout:

```text
[A]
[10]
[20]
```

`strings()` có kiểu trả về tường minh `Box<String>`, `integers()` trả `Box<Integer>`. Method `empty()` là generic factory để caller chọn type argument thông qua target type hoặc type witness.

**Ưu điểm:** API dễ hiểu, caller không phải nhắc lại type argument trong những trường hợp phổ biến.

**Giới hạn:** Tên factory được thiết kế cụ thể cho một lựa chọn nghiệp vụ. Nó **không** làm khai báo `Box<T>` nhận một default type argument do ngôn ngữ quản lý.

Nếu dữ liệu `null` được cho phép, `List.copyOf(elements)` sẽ từ chối `null` khi tạo kết quả. Chương trình này chỉ thêm các phần tử không null.

## 14. Thiết kế thay thế 2: factory có một kiểu mặc định theo quy ước API

Đôi khi muốn có một “đường gọi mặc định” và một “đường gọi linh hoạt”. Có thể thiết kế hai method với **tên rõ ràng**, hoặc overload bằng tham số đầu vào khác nhau.

Tạo tệp **`FactoryChoiceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FactoryChoiceDemo {

    static final class Bucket<T> {
        private final List<T> items = new ArrayList<>();

        void add(T value) {
            items.add(value);
        }

        List<T> snapshot() {
            return List.copyOf(items);
        }
    }

    static Bucket<String> defaultTextBucket() {
        return new Bucket<>();
    }

    static <T> Bucket<T> bucketOf(T first) {
        Bucket<T> result = new Bucket<>();
        result.add(first);
        return result;
    }

    static <T> Bucket<T> emptyBucket() {
        return new Bucket<>();
    }

    public static void main(String[] args) {
        var defaultText = defaultTextBucket();
        defaultText.add("hello");

        var numbers = bucketOf(7);
        numbers.add(8);

        var explicit =
                FactoryChoiceDemo.<Double>emptyBucket();
        explicit.add(2.5);

        System.out.println(defaultText.snapshot());
        System.out.println(numbers.snapshot());
        System.out.println(explicit.snapshot());
    }
}
```

Biên dịch/chạy:

```bash
javac FactoryChoiceDemo.java
java FactoryChoiceDemo
```

Stdout:

```text
[hello]
[7, 8]
[2.5]
```

Lưu ý tên `defaultTextBucket()` chỉ diễn đạt **mặc định do tác giả API tự chọn**. Nó không làm `Bucket<T>` hỗ trợ `T = String` trong khai báo.

Không nên đặt tên hai overload chỉ khác generic return type:

```java
// CỐ Ý KHÔNG HỢP LỆ — return type không dùng để overload:
static Bucket<String> create() { return new Bucket<>(); }
static <T> Bucket<T> create() { return new Bucket<>(); }
```

Hai method cùng tên, cùng danh sách tham số rỗng không thể phân biệt chỉ bằng kiểu kết quả hoặc type parameter. Dùng tên khác, hoặc chữ ký tham số thực sự khác khi có ý nghĩa.

## 15. Thiết kế thay thế 3: subtype cố định type argument

Một cách khác là định nghĩa **class con không generic** cố định kiểu của class cha:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
```

Đây là các khai báo class hợp lệ, không chứa `main`.

`StringBox` không khai báo `T` của riêng nó; nó **kế thừa** `Box<String>`. Caller có thể viết `new StringBox("hello")` thay vì `new Box<String>("hello")`, và compiler biết `get()` trả `String` khi nhìn từ `StringBox`.

Điều này khác với default generic argument:

- `Box<Integer>` vẫn là một cách dùng hợp lệ của `Box<T>`.
- `StringBox` là **một class khác** với `Box<T>` và có tên/quan hệ kế thừa riêng.
- Java không cho viết `Box` rồi tự động hiểu nó là `StringBox` hoặc `Box<String>`.

### Ví dụ chạy được

Tệp **`SpecializedSubtypeDemo.java`**:

```java
public class SpecializedSubtypeDemo {

    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class StringBox extends Box<String> {
        StringBox(String value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        StringBox text = new StringBox("ready");
        Box<Integer> number = new Box<>(12);

        String message = text.get();

        System.out.println(message);
        System.out.println(number.get());
    }
}
```

Lệnh:

```bash
javac SpecializedSubtypeDemo.java
java SpecializedSubtypeDemo
```

Stdout:

```text
ready
12
```

Subclass specialization hữu ích nếu `StringBox` thật sự là một khái niệm miền nghiệp vụ hoặc cần API/validation bổ sung. Nếu chỉ cần cách tạo nhanh một object generic, factory method ở phần trước thường ít class hơn.

## 16. Thiết kế thay thế 4: dùng target type ở ranh giới API

Thường không cần tạo factory riêng để “mặc định” một kiểu. Chỉ cần caller ghi rõ **kiểu mà chương trình mong muốn** ở bên trái hoặc ở return type.

Ví dụ:

```java
static <T> java.util.List<T> emptyList() {
    return new java.util.ArrayList<>();
}

static java.util.List<String> names() {
    return emptyList();
}
```

Hai method này cần đặt trong class.

`names()` khai báo kết quả `List<String>`, nên compiler có target type rõ ràng cho lời gọi generic `emptyList()`. Một caller dùng `names()` không cần viết type witness nữa.

Tương tự:

```java
static void consumeStrings(java.util.List<String> values) {
    System.out.println(values.size());
}

static void demo() {
    consumeStrings(new java.util.ArrayList<>());
}
```

Parameter type của `consumeStrings` cung cấp context cho diamond ở biểu thức tạo `ArrayList`.

Đây là **target typing**, không phải việc Java tạo default generic parameter. Nó giữ ý định kiểu tại **ranh giới sử dụng** và giúp code client ngắn khi compiler có đủ ngữ cảnh.

## 17. Kiểu raw không phải sự thay thế cho default type argument

Một anti-pattern là bỏ hẳn `<...>`:

```java
java.util.List values = new java.util.ArrayList();
values.add("text");
values.add(100);
```

Dòng này có thể biên dịch với cảnh báo raw/unchecked. Nhưng `values` là **raw `List`**, không phải một `List<String>` có đối số mặc định.

Rủi ro:

- Compiler không kiểm tra đầy đủ loại phần tử trong thao tác `add`.
- Khi gán dữ liệu raw sang biến `List<String>` qua unchecked conversion, có thể tạo **heap pollution**.
- Lỗi `ClassCastException` có thể xuất hiện sau đó khi phần tử bị đọc như `String`.

`List<Object>` cũng không phải đồng nghĩa với raw `List`:

```java
java.util.List<Object> values =
        new java.util.ArrayList<>();
```

Dòng trên có generic type argument rõ ràng là `Object`. Compiler kiểm tra nhất quán rằng các phần tử dùng như `Object`, dù danh sách có thể chứa cả `String` và `Integer`.

**Khi chưa biết type argument mà chỉ cần đọc**, `List<?>` thường phù hợp hơn raw `List`, vì wildcard vẫn duy trì các ràng buộc kiểu ở compile time.

## 18. Default type argument không giải quyết type erasure

Giả sử Java có default type argument (thực tế **không có**), việc chọn một type argument lúc biên dịch vẫn sẽ không tự biến Generics thành reified types. Với Java thực tế:

```java
var a = new Box<>("A");
var b = new Box<>(10);
```

nếu cả hai object là instance trực tiếp của cùng generic class `Box`, `getClass()` thường trả về cùng class runtime, vì type arguments bị erasure.

Tạo tệp **`GenericRuntimeIdentityDemo.java`**:

```java
public class GenericRuntimeIdentityDemo {

    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>("A");
        Box<Integer> number = new Box<>(10);

        System.out.println(
                text.getClass() == number.getClass());
        System.out.println(
                Box.class.getTypeParameters()[0].getName());
    }
}
```

Chạy:

```bash
javac GenericRuntimeIdentityDemo.java
java GenericRuntimeIdentityDemo
```

Stdout:

```text
true
T
```

`getClass()` chỉ cho thấy runtime class của object; `getTypeParameters()` cho thấy `Box` khai báo một type variable tên `T`. Nó không cho thấy mỗi instance đã được tạo với một default type argument nào — bởi Java không có default đó, và thông thường object không tự mang type argument đã dùng trong mã nguồn.

Dùng subclass `StringBox extends Box<String>` có thể khiến reflection đọc được generic superclass được khai báo trên **class con**, nhưng điều đó không biến type argument thành một mặc định tự động trên mọi `Box`.

## 19. Phân biệt các khái niệm “mặc định” dễ bị nhầm

Trong Java, cùng từ “default” có thể chỉ những tính năng khác nhau.

| Khái niệm | Java có hỗ trợ? | Có phải default type argument? |
|---|---|---|
| Giá trị mặc định của field reference là `null` | Có | Không |
| Giá trị mặc định của field primitive như `int` là `0` | Có | Không |
| Constructor không đối số | Có thể có hoặc khai báo tường minh | Không |
| Overload method để cung cấp giá trị mặc định | Có thể tự thiết kế | Không |
| `default` method trong interface | Có (Java 8+) | Không |
| Diamond `new Box<>()` | Có | Không; là type inference |
| `var x = expression` | Có (local inference) | Không |
| Upper bound `<T extends Number>` | Có | Không |
| Raw type `Box` | Có để tương thích | Không |
| Wildcard `Box<?>` | Có | Không |
| Khai báo `class Box<T = String>` | **Không** | Đây chính là cú pháp không hỗ trợ |

### `default` method trong interface không liên quan đến type arguments

Ví dụ:

```java
interface Printer<T> {
    void print(T value);

    default void printTwice(T value) {
        print(value);
        print(value);
    }
}
```

Đây là interface hợp lệ. Từ khóa `default` ở đây khai báo **triển khai mặc định của một instance method trong interface**, không cung cấp mặc định `T = String`.

Một interface có default methods vẫn phải được dùng như `Printer<String>`, `Printer<Integer>`, `Printer<?>` hoặc trong ngữ cảnh raw type theo quy tắc bình thường.

## 20. Type inference không phải lúc nào cũng chọn `Object`

Một kết luận quá rộng là:

> “Không có default type argument nên cứ thiếu `<T>` thì compiler tự chọn `Object`.”

Sai vì compiler có thể suy luận từ nhiều nguồn:

1. **Target type:** `Box<String> x = new Box<>()` gợi `String`.
2. **Constructor arguments:** `var x = new Box<>(123)` gợi `Integer`.
3. **Method arguments:** `identity("A")` gợi `String`.
4. **Return context:** `List<String> names() { return Collections.emptyList(); }` cung cấp kiểu đích trong biểu thức return.
5. **Bounds:** `<T extends Number>` giới hạn tập kiểu ứng viên.
6. **Explicit type witness:** `Factory.<String>empty()` đặt `String` tại lời gọi.

Suy luận kiểu Java là một hệ thống ràng buộc, không phải một câu lệnh “nếu vắng thì gán Object”. Chỉ trong những trường hợp cụ thể **không có ràng buộc hữu ích khác**, chẳng hạn `var x = new Box<>()` với type parameter không bound và constructor không đối số, `Object` mới là một kết quả điển hình.

Ngược lại, nếu viết **raw type** `Box x`, compiler không suy luận `T = Object` theo cùng cách như `Box<Object> x`; đây là một kiểu thô có các quy tắc riêng.

## 21. Những lỗi phổ biến và cách sửa

**Lỗi 1 — Viết `class Box<T = String>`.** Java không hỗ trợ. Sửa thành `Box<T>`, rồi tạo `static Box<String> strings()` nếu muốn lựa chọn nghiệp vụ cụ thể.

**Lỗi 2 — Dùng `<T extends String>` để mô phỏng default `String`.** `extends` là **bound**, không phải default. Ngoài ra `String` là final, nên việc chọn bound này có nghĩa hẹp về tập subtype; nó không tạo cú pháp bỏ type argument để mặc định `String`.

**Lỗi 3 — Nghĩ `new Box<>()` luôn chọn `String` nếu chương trình thường làm việc với chuỗi.** Compiler không suy luận từ sở thích nghiệp vụ. Phải có target type, constructor arguments, type witness hoặc factory trả kiểu cụ thể.

**Lỗi 4 — Viết `Box<> x;`.** Diamond không dùng làm tên kiểu của biến. Viết `Box<String> x;`, `Box<?> x;`, hoặc khai báo `var x = new Box<>()` nếu hiểu rõ kiểu được suy luận.

**Lỗi 5 — Dùng `Box` raw như “default”.** Raw type bỏ thông tin generic và có thể dẫn đến unchecked operations; nó không tương đương `Box<Object>` hoặc `Box<String>`.

**Lỗi 6 — Dùng `Box<?>` như `Box<Object>`.** Wildcard chưa biết cho phép đọc theo bound an toàn nhưng hạn chế việc truyền tùy ý một `T` mới vào các phương thức nhận `T`.

**Lỗi 7 — Cho rằng `var` suy ra kiểu dựa trên lệnh `set` gọi sau.** Type của biến được xác định ở initializer; các lệnh sau không làm nó thay đổi.

**Lỗi 8 — Bỏ một đối số của `Pair<K,V>` và kỳ vọng mặc định.** `Pair<String>` không hợp lệ nếu `Pair` khai báo hai type parameters. Ghi đủ arguments hoặc dùng diamond tại class instance creation expression.

**Lỗi 9 — Nghĩ explicit type witness là cast.** `<String>` trong `Factory.<String>empty()` tham gia kiểm tra kiểu; nó không ép một object tùy ý thành `String`.

**Lỗi 10 — Dùng return type khác nhau để overload hai factory cùng tên, không tham số.** Java không dùng return type để phân biệt overload. Hãy đặt tên khác hoặc thay đổi hợp đồng tham số có ý nghĩa.

**Lỗi 11 — Tạo constructor không đối số rồi nghĩ `T` đã mặc định.** Constructor chỉ chọn cách khởi tạo **giá trị**, không cung cấp type argument mặc định.

**Lỗi 12 — Nhầm default interface method với default generic parameter.** Cùng từ “default” nhưng hoàn toàn khác vai trò cú pháp.

**Lỗi 13 — Dùng unchecked cast để giả vờ có generic default.** Cast không được kiểm tra đầy đủ có thể che lỗi compile time và chuyển thành `ClassCastException` muộn hơn; giải pháp tốt hơn là đặt type ở API boundary.

**Lỗi 14 — Cho rằng runtime `getClass()` sẽ báo `Box<String>` được “mặc định”.** Type erasure khiến nhiều instantiations generic dùng cùng runtime class; thông tin đó thường không thể suy từ object một cách tổng quát.

## 22. Chọn thiết kế API theo nhu cầu

| Nhu cầu | Cách viết hợp lý | Lý do |
|---|---|---|
| Mỗi caller biết type argument | `Box<String> box = new Box<>();` | Diamond dùng target type |
| Kiểu có thể suy ra từ giá trị | `var box = new Box<>(42);` | Constructor argument gợi `Integer` |
| Muốn biến có type argument rõ với `var` | `var box = new Box<String>();` | Initializer ghi tường minh `String` |
| Muốn một cách tạo “mặc định dùng String” | `static Box<String> strings()` | Quy ước ở API, không phụ thuộc cú pháp generic không hỗ trợ |
| Muốn generic factory trả kiểu do caller chọn | `static <T> Box<T> empty()` | Target typing hoặc type witness |
| Cần class với hợp đồng cố định String | `class StringBox extends Box<String>` | Subtype chuyên biệt |
| Chỉ đọc từ một Box không biết T | `Box<?>` | Bảo toàn giới hạn generic an toàn |
| Cần ràng buộc T phải là số | `Box<T extends Number>` | Bound, không phải default |
| Muốn nhiều type parameters | `Pair<K,V>` với đủ args | Không có partial type argument default |
| Muốn chọn một giá trị khởi tạo | Constructor/factory nhận giá trị | Giá trị mặc định khác type argument |
| Muốn hỗ trợ mã legacy | Chỉ dùng raw type ở ranh giới bất khả kháng | Khoanh vùng unchecked warning |

Không nên cố mô phỏng default generic parameter bằng nhiều tầng unchecked casts, raw types hoặc overload chỉ khác return type. API có tên factory rõ ràng thường dễ đọc và dễ kiểm thử hơn.

## 23. Bài thực hành có đáp án

### Bài 1 — Phân biệt loại cú pháp

Trong các dòng dưới đây, dòng nào không hợp lệ?

```java
class Box<T> { }                // A
class Other<T = String> { }     // B
class Numeric<T extends Number> { } // C
```

**Đáp án:** B không hợp lệ vì Java không có default type argument. A và C hợp lệ; C dùng upper bound.

### Bài 2 — Suy luận qua vế trái

```java
Box<String> a = new Box<>();
```

`T` được xác định thế nào, giả sử `Box` có constructor không đối số?

**Đáp án:** Compiler suy luận `String` từ target type `Box<String>`. Không cần default type argument.

### Bài 3 — `var` và constructor rỗng

```java
var b = new Box<>();
```

Nếu `Box<T>` không có bound và constructor không nhận dữ liệu để suy luận, kiểu tĩnh của `b` là gì?

**Đáp án:** `Box<Object>` trong trường hợp được mô tả. Đó là kết quả type inference, không phải raw `Box`.

### Bài 4 — Constructor có đối số

```java
var c = new Box<>(10);
```

Nếu `Box` có constructor `Box(T value)`, `T` thường là gì?

**Đáp án:** `Integer` sau boxing `10` và inference từ constructor argument.

### Bài 5 — Generic method rỗng

```java
static <T> java.util.List<T> empty() {
    return new java.util.ArrayList<>();
}
```

Làm sao có `List<String>` mà không thay khai báo method?

**Đáp án:** Dùng `List<String> list = empty();` hoặc `var list = Factory.<String>empty();` nếu method static thuộc `Factory`.

### Bài 6 — Raw type có phải default không?

```java
Box raw = new Box();
```

Có đồng nghĩa với `Box<String>` không?

**Đáp án:** Không. Đây là raw type; compile-time generic checking bị suy giảm.

### Bài 7 — Multiple type parameters

```java
record Pair<K, V>(K key, V value) { }
```

`Pair<String>` có hợp lệ không?

**Đáp án:** Không. Đã sử dụng dạng parameterized type thì cần đúng hai arguments. Có thể dùng `Pair<String,Integer>` hoặc diamond ở biểu thức tạo nếu compiler suy luận được.

### Bài 8 — Bounds

`<T extends Number>` có nghĩa “`T` mặc định là `Number`” không?

**Đáp án:** Không. Nó quy định giới hạn trên; type inference có thể dựa vào bound nhưng không có default type argument.

### Bài 9 — Factory dùng kiểu phổ biến

Nếu hệ thống thường tạo `Box<String>`, nên làm thế nào để caller không phải lặp `String`?

**Đáp án:** Cung cấp `static Box<String> strings()` hoặc subtype `StringBox` khi có lý do nghiệp vụ; vẫn giữ `Box<T>` generic bình thường.

### Bài 10 — Wildcard

`Box<?>` có phải cách ghi “đối số T mặc định là Object” không?

**Đáp án:** Không. `?` biểu diễn một type argument chưa biết và hạn chế các thao tác ghi phụ thuộc `T`.

### Bài 11 — Return-type-only overload

Hai method `Box<String> create()` và `<T> Box<T> create()` cùng tên, cùng không tham số có thể tồn tại bên cạnh nhau không?

**Đáp án:** Không. Return type và type parameter không đủ phân biệt hai method signatures trùng nhau.

### Bài 12 — Runtime

`new Box<String>("a").getClass()` và `new Box<Integer>(1).getClass()` có thể cùng trả class nào?

**Đáp án:** Cùng class runtime `Box`, do type erasure. Đối số kiểu trong mã nguồn không tạo runtime class riêng cho mỗi instantiation.

## 24. Quy trình kiểm tra khi gặp yêu cầu “mặc định T là String”

1. **Xác định yêu cầu là kiểu hay giá trị.** “T mặc định là String” khác “giá trị ban đầu là chuỗi rỗng”.
2. **Xem caller có target type không.** Nếu có, dùng diamond/generic factory inference.
3. **Xem constructor hoặc method có đối số mang thông tin kiểu không.** Có thể suy luận từ input.
4. **Nếu không có target type và không có input**, việc suy luận có thể ra `Object` hoặc kiểu chịu bounds; cần ghi rõ type argument nếu muốn loại cụ thể.
5. **Nếu nhiều callers cùng cần `String`**, tạo factory có return type `Box<String>` để gom ý đồ vào một nơi.
6. **Nếu subtype riêng có ý nghĩa**, tạo `StringBox extends Box<String>` thay vì cố biến `Box` raw thành String.
7. **Nếu API có nhiều type parameters**, không kỳ vọng Java cho lược bớt tham số phía cuối như cú pháp defaults của một số ngôn ngữ khác.
8. **Tránh raw type và unchecked cast** để mô phỏng mặc định.
9. **Thử compiler với trường hợp sai:** một `Box<String>` phải từ chối giá trị khác String ở method nhận `T`.
10. **Kiểm tra phiên bản Java thực tế:** diamond và local-variable inference đã có từ các phiên bản khác nhau; các ví dụ dùng Java 17+.

### Câu hỏi tự kiểm tra nhanh

Nếu thấy một dòng:

```java
var items = new java.util.ArrayList<>();
```

hãy tự hỏi: “Compiler đã có bằng chứng nào để suy luận `String` chưa?” Trong ví dụ này chưa có, nên kết quả thông thường là `ArrayList<Object>`. Nếu ý định là danh sách chuỗi, hãy viết rõ type ở một vị trí hợp lệ thay vì kỳ vọng default generic parameter không tồn tại.

## 25. Tổng kết và nguồn tài liệu

**Java Generics không hỗ trợ giá trị mặc định cho tham số kiểu trong khai báo.** Không thể viết `class Box<T = String>` hoặc `<T = String>` cho generic method. `extends` chỉ đặt bounds; raw type bỏ type arguments, wildcard diễn đạt kiểu chưa biết, còn diamond, `var` và generic method inference suy luận kiểu tại **điểm sử dụng**.

Khi muốn caller không phải lặp một type argument, lựa chọn thiết kế phù hợp thường là:

- **Diamond + target typing:** `Box<String> x = new Box<>()`.
- **Đối số kiểu rõ trong initializer:** `var x = new Box<String>()`.
- **Suy luận từ dữ liệu:** `var x = new Box<>("text")`.
- **Generic static factory:** `List<String> x = empty()` hoặc `Factory.<String>empty()`.
- **Named factory cho kiểu phổ biến:** `Box<String> strings()`.
- **Subtype chuyên biệt khi cần:** `StringBox extends Box<String>`.

Các giải pháp này giữ kiểm tra kiểu ở compile time mà không dựa vào raw types hoặc casts không an toàn. Không giải pháp nào biến default generic argument thành một tính năng mà Java chưa hỗ trợ.

Nguồn tham khảo:

- [Java Language Specification §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): khai báo type variables và bounds.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments và kiểu tham số hóa.
- [Java Language Specification §8.1.2 — Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): quy tắc type parameters của class.
- [Java Language Specification §8.4.4 — Generic Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.4): generic methods.
- [Java Language Specification §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): constructor invocation và diamond.
- [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18): suy luận kiểu bằng ràng buộc.
- [Java Language Specification §14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): `var` và local-variable type inference.
- [Java Language Specification §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): raw type không đồng nghĩa parameterized type có default.