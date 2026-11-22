# Kiểu của thành viên khi được truy cập qua raw type trong Java Generics

## 1. Vấn đề: cùng một class, nhưng kiểu của lời gọi có thể khác

Xét class generic:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T next) {
        value = next;
    }
}
```

Khi truy cập qua `Box<String>`, compiler biết `T` tương ứng với `String`: `get()` được nhìn nhận là trả `String`, còn `set(...)` nhận `String`.

Nhưng nếu dùng **raw type** `Box` (bỏ phần đối số kiểu `<...>`), kiểu của các thành viên có thể thay đổi ngay trong quá trình **kiểm tra mã nguồn tại vị trí truy cập**:

```java
Box<String> typed = new Box<>("Java");
Box raw = typed;

String a = typed.get();  // Hợp lệ: kết quả kiểu String
Object b = raw.get();    // Hợp lệ: T đã xóa thành Object
raw.set(42);             // Có thể biên dịch, nhưng cảnh báo unchecked
```

Đây là **đoạn mã minh họa**, đặt trong một phương thức để biên dịch. Việc dùng raw `Box` không tạo ra class runtime khác; nó làm mất một phần bảo đảm generic mà compiler có được khi biết đối số kiểu.

> **Quy tắc chính:** Đối với constructor, instance method và non-static field được khai báo trên kiểu generic `C` (không phải thành viên kế thừa từ superclass/superinterface), khi truy cập qua **raw type `C`**, kiểu của thành viên được tính theo **erasure** của kiểu thành viên trong khai báo generic `C`. Có những ngoại lệ quan trọng cho static members và inherited members.

Do đó, câu hỏi “thành viên này có kiểu gì?” phải xét **kiểu tĩnh của biểu thức nhận** (*receiver*), không chỉ nhìn vào khai báo class và không chỉ nhìn vào class runtime của đối tượng.

## 2. Raw type là gì, khác gì với kiểu tham số hóa?

Một class được khai báo:

```java
class Holder<T> { }
```

Có thể được dùng ở nhiều dạng:

| Cách dùng | Ý nghĩa |
|---|---|
| `Holder<String>` | Kiểu tham số hóa; `T` là `String` trong quá trình kiểm tra kiểu |
| `Holder<Integer>` | Kiểu tham số hóa; `T` là `Integer` |
| `Holder<?>` | Kiểu tham số hóa với wildcard: một đối số kiểu chưa biết, vẫn giữ các ràng buộc generic |
| `Holder` | **Raw type**: bỏ đối số kiểu, tương thích mã Java trước generics |
| `Holder<Object>` | Kiểu tham số hóa với `T` đúng là `Object`; không giống raw `Holder` |

Không thể tùy ý gán `Holder<String>` cho `Holder<Object>`, vì generic Java mặc định **bất biến** (*invariant*). Trong khi đó, vì lý do tương thích mã cũ, raw type có các quy tắc chuyển đổi ít chặt chẽ hơn và có thể phát sinh cảnh báo `rawtypes` hoặc `unchecked`.

`Holder<?>` và raw `Holder` đều có thể đọc giá trị của `T` như `Object` nếu `T` không có bound, nhưng chúng **khác nhau rõ rệt khi gọi method nhận `T`**, dùng generic method hoặc truy cập một thành viên có type argument riêng.

### Tại sao Java còn có raw type?

Generics được thêm vào Java sau khi nhiều API và thư viện đã tồn tại. Raw type hỗ trợ **migration compatibility**: code cũ dùng `List`, `Map`, `Class` có thể tiếp tục biên dịch và tương tác với code generic. Đổi lại, compiler không thể bảo đảm toàn bộ các lời gọi đó thỏa hợp đồng kiểu mới.

Trong code mới, khi không biết đối số kiểu, `Holder<?>` thường phù hợp và an toàn hơn `Holder`. Raw type chủ yếu nên xuất hiện ở ranh giới với mã cũ, khi làm việc với những API có chủ đích dùng kiểu thô, hoặc trong ví dụ giải thích cơ chế type erasure.

## 3. Quy tắc về instance field, method và constructor

Theo Java Language Specification §4.8, đối với raw type `C`:

1. **Constructor của `C`** được nhìn theo kiểu đã xóa của constructor trong khai báo generic `C`.
2. **Instance method do `C` khai báo**, nếu không phải inherited member, được nhìn theo erasure của kiểu method đó.
3. **Non-static field do `C` khai báo**, nếu không phải inherited member, được nhìn theo erasure của kiểu field đó.
4. **Static method và static field của `C`** giữ kiểu như trong khai báo generic; chúng không bị “raw hóa” chỉ vì `C` là class generic.
5. **Inherited instance methods và fields** có quy tắc riêng: kiểu thành viên được xét trong *supertype của `C` mà khai báo thành viên đó*. Vì vậy không được phát biểu rằng mọi inherited member trên raw receiver đều tự động biến thành raw theo cùng một cách.

Erasure của các thành phần cơ bản:

| Kiểu trong khai báo | Kiểu sau erasure |
|---|---|
| `T` khi `<T>` | `Object` |
| `T` khi `<T extends Number>` | `Number` |
| `T` khi `<T extends Number & Comparable<T>>` | `Number` (giới hạn đứng đầu) |
| `List<T>` | Raw `List` |
| `List<String>` | Raw `List` |
| `Map<String, T>` | Raw `Map` |
| `T[]` khi `<T>` | `Object[]` |
| `T[]` khi `<T extends Number>` | `Number[]` |
| `String` | `String` (không thay đổi) |
| `int` | `int` (không thay đổi) |

**Điểm dễ sai:** Một instance method trong `Box<T>` có kiểu trả `List<String>` vẫn có thể được nhìn là trả raw `List` nếu được truy cập qua raw `Box`. Quy tắc không chỉ xóa những vị trí chứa `T`; nó áp dụng erasure cho **kiểu của thành viên** trong bối cảnh raw type.

Đồng thời, việc compiler nhìn thấy erasure tại nơi gọi không phải là thao tác sửa lại khai báo mã nguồn `Box<T>` và cũng không làm thay đổi những nơi khác đang dùng `Box<String>`.

## 4. Ví dụ chạy được: cùng một object qua receiver typed và raw

Tạo tệp `RawMemberTypesDemo.java`:

```java
import java.util.List;

public class RawMemberTypesDemo {

    static class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }

        List<String> fixedLabels() {
            return List.of("A", "B");
        }

        <U> U ownEcho(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> typed = new Box<>("start");

        String first = typed.get();
        List<String> labels = typed.fixedLabels();
        String echo = typed.ownEcho("hello");

        System.out.println(first);
        System.out.println(labels.get(1));
        System.out.println(echo);

        Box raw = typed;

        Object rawValue = raw.get();
        List rawLabels = raw.fixedLabels();
        Object rawEcho = raw.ownEcho("hello");

        System.out.println(rawValue);
        System.out.println(rawLabels.get(0));
        System.out.println(rawEcho);

        raw.set(123);
        System.out.println(raw.get());

        try {
            String result = typed.get();
            System.out.println(result);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RawMemberTypesDemo.java
java RawMemberTypesDemo
```

Stdout:

```text
start
B
hello
start
A
hello
123
ClassCastException
```

Chương trình có thể xuất hiện thông báo về thao tác không kiểm tra kiểu khi biên dịch. Để yêu cầu compiler in chi tiết các cảnh báo raw/unchecked, chạy:

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawMemberTypesDemo.java
```

Dòng `Box raw = typed;` dùng raw type. Dòng `raw.set(123)` là lời gọi nguy hiểm vì phương thức `set(T)` có tham số sau erasure là `Object`; compiler không còn kiểm tra rằng `123` tương thích với `String` mà đối tượng `typed` vốn dự định chứa.

### Diễn giải từng giai đoạn

**Giai đoạn dùng receiver `typed`:**

- `typed` có kiểu `Box<String>`.
- `typed.get()` có kiểu tĩnh `String`.
- `typed.fixedLabels()` có kiểu tĩnh `List<String>`.
- `typed.ownEcho("hello")` là lời gọi generic method; compiler có thể suy luận `U = String`, nên kết quả là `String`.

**Giai đoạn dùng receiver `raw`:**

- `raw` có kiểu thô `Box`.
- `raw.get()` có kiểu tĩnh `Object` vì erasure của `T` không giới hạn là `Object`.
- `raw.fixedLabels()` có kiểu raw `List`, dù method nguồn khai báo `List<String>`.
- `raw.ownEcho("hello")` có kiểu `Object`; sự suy luận `U = String` của generic instance method do class khai báo không còn được cung cấp trong bối cảnh raw receiver.

**Giai đoạn gây lỗi runtime:**

- `raw.set(123)` ghi một `Integer` vào cùng object được biến `typed` tham chiếu.
- `raw.get()` trả `Object` nên có thể in `123`.
- Khi chương trình gán `typed.get()` vào `String`, compiler đã biên dịch lời gọi theo kiểu `Box<String>` và chèn kiểm tra/cast tương ứng với `String`.
- Đối tượng thực được lưu là `Integer`, nên cast thất bại với `ClassCastException`.

Đây là một ví dụ về **heap pollution**: trạng thái runtime không còn phù hợp với hợp đồng generic của tham chiếu `Box<String>`. Raw type giúp lỗi lọt qua quá trình biên dịch nhưng không làm `Integer` tự biến thành `String`.

## 5. Tại sao phương thức không dùng `T` vẫn có thể bị raw hóa?

Đây là phần nhiều người bất ngờ nhất.

Xét đoạn khai báo:

```java
class Repository<T> {
    java.util.List<String> names() {
        return java.util.List.of("Lan", "Mai");
    }
}
```

Đây là class hợp lệ nhưng không có `main`. Method `names()` **không dùng `T` trong return type**, vậy tại sao truy cập qua raw `Repository` vẫn có kiểu `List`, thay vì `List<String>`?

Bởi quy tắc raw member xét **kiểu của instance method** trong khai báo generic class. Erasure của return type `List<String>` là raw `List`. Compiler áp dụng erasure cho signature tương ứng của method khi receiver là raw `Repository`.

Phân biệt:

```java
Repository<Integer> typed = new Repository<>();
java.util.List<String> good = typed.names(); // Hợp lệ

Repository raw = typed;
java.util.List unchecked = raw.names();      // Kiểu tĩnh raw List
```

Nếu viết:

```java
// Ví dụ biên dịch với cảnh báo unchecked conversion.
java.util.List<String> risky = raw.names();
```

Java có thể cho phép **unchecked conversion** từ raw `List` về `List<String>` và phát cảnh báo; không có bằng chứng runtime nào chứng minh toàn bộ phần tử đều là `String`. Dù `names()` thực tế trả chuỗi ở đây, compiler áp dụng quy tắc tổng quát của raw type.

Không nên xóa cảnh báo bằng `@SuppressWarnings("unchecked")` chỉ để giữ code biên dịch “sạch”. Hãy sửa luồng kiểu để tiếp tục dùng receiver có parameterized type.

## 6. Một generic instance method tự khai báo `<U>` cũng bị ảnh hưởng

Phương thức generic có thể khai báo tham số kiểu riêng, độc lập với tham số của class:

```java
class Converter<T> {
    <U> U identity(U value) {
        return value;
    }
}
```

Trên receiver `Converter<String>`:

```java
Converter<String> typed = new Converter<>();
String text = typed.identity("abc"); // U được suy luận là String
```

Trên receiver raw `Converter`:

```java
Converter raw = typed;
Object result = raw.identity("abc"); // Kết quả theo erasure là Object
```

Những dòng trên chỉ minh họa và cần được đặt trong class/method phù hợp nếu muốn chạy. Điểm quan trọng là method **do class generic `Converter<T>` khai báo** thuộc phạm vi quy tắc raw member, dù `<U>` không dựa vào `T`.

Tham số kiểu của chính generic method cũng bị xóa trong bối cảnh này. Nếu `<U>` không có bound thì `U` có erasure `Object`; nếu method khai báo `<U extends Number>` thì `U` có erasure là `Number`.

**Dự đoán kiểu trước khi viết code** là kỹ năng hữu ích:

| Biểu thức | Kiểu tĩnh của kết quả |
|---|---|
| `typed.identity("abc")` | `String` (compiler suy luận `U`) |
| `raw.identity("abc")` | `Object` |
| `typed.identity(12)` | `Integer` |
| `raw.identity(12)` | `Object` |

Dùng đối số kiểu tường minh không phải biện pháp sửa thiết kế raw type:

```java
// Cố ý không hợp lệ: instance generic method của raw receiver đã bị xóa.
String s = raw.<String>identity("abc");
```

Cách đúng là giữ một tham chiếu đã được parameterize khi có thể, ví dụ `Converter<?>`, hoặc tách thuật toán generic thành một utility thích hợp.

## 7. Trường hợp type variable có bound: kết quả không nhất thiết là `Object`

Mốc quan trọng của erasure là **leftmost bound** (giới hạn đứng đầu) của type variable. `<T>` không có bound ngầm định là `Object`, nhưng `<T extends Number>` có erasure là `Number`.

Ví dụ chương trình chạy được, tệp `BoundedRawMemberDemo.java`:

```java
public class BoundedRawMemberDemo {

    static class NumberBox<T extends Number> {
        private T value;

        NumberBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }

        double doubled() {
            return value.doubleValue() * 2;
        }
    }

    public static void main(String[] args) {
        NumberBox<Integer> typed = new NumberBox<>(5);
        NumberBox raw = typed;

        Number number = raw.get();
        System.out.println(number.intValue());
        System.out.println(raw.doubled());

        raw.set(2.5);
        System.out.println(raw.get().doubleValue());

        try {
            Integer integer = typed.get();
            System.out.println(integer);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BoundedRawMemberDemo.java
java BoundedRawMemberDemo
```

Stdout:

```text
5
10.0
2.5
ClassCastException
```

Giải thích:

- `T extends Number` nên `NumberBox` ở dạng raw nhìn `get()` như trả `Number`, `set(...)` như nhận `Number`.
- Dù `typed` là `NumberBox<Integer>`, `raw.set(2.5)` vẫn qua được tham số `Number` (với cảnh báo unchecked). Hợp đồng `Integer` bị phá vỡ.
- `raw.get()` cho `Number` và có thể gọi `doubleValue()` trực tiếp.
- `typed.get()` ở nguồn được nhìn là `Integer`; khi cần cast, runtime phát hiện giá trị thực là `Double` và ném `ClassCastException`.

Nếu giới hạn là `<T extends Number & Comparable<T>>`, erasure vẫn là `Number`. Interface `Comparable<T>` ở vị trí tiếp theo trong intersection bound không làm kiểu đã xóa của `T` đổi thành `Comparable`.

Đừng kết luận từ ví dụ đầu rằng raw `get()` **luôn** trả `Object`; phải xem bound của type variable.

## 8. Constructor nhìn theo erasure khi tạo object bằng raw type

Constructor là trường hợp thường gặp khi chuyển đổi mã cũ. Nếu class khai báo:

```java
class Envelope<T> {
    Envelope(T content) {
    }
}
```

Thì cách tạo có khai báo đối số kiểu:

```java
Envelope<String> typed = new Envelope<>("hello");
```

cho phép compiler kiểm tra `T = String`. Ngược lại:

```java
Envelope raw = new Envelope("hello");
```

dùng raw `Envelope`. Constructor nhận `T` được nhìn qua erasure `Object`, và compiler có thể phát cảnh báo cho lời gọi vì formal parameter đã thay đổi khi xóa.

Ví dụ **không được hiểu** rằng `new Envelope("hello")` runtime tạo class khác với `new Envelope<String>("hello")`. Cả hai là instance của `Envelope` được mô tả bằng cùng tên class. Điểm khác biệt nằm ở việc compiler còn theo dõi đối số generic hay không.

Với constructor có generic type parameter riêng, cùng logic erasure áp dụng cho các trường hợp phù hợp của raw `Envelope`; static factory method không chịu đúng quy tắc này chỉ vì nó nằm trong class generic, xem phần static members tiếp theo.

## 9. Static field và static method: ngoại lệ quan trọng

Một static member không phụ thuộc vào từng instance generic. Java cũng không cho static member tham chiếu trực tiếp tới type parameter `T` của class bao ngoài như một kiểu instance riêng.

Xét chương trình `RawStaticMemberDemo.java`:

```java
import java.util.List;

public class RawStaticMemberDemo {

    static class Container<T> {
        static List<String> labels = List.of("red", "blue");

        static <U> U staticEcho(U value) {
            return value;
        }

        <U> U instanceEcho(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Container raw = new Container();

        List<String> names = Container.labels;
        String first = Container.staticEcho("hello");

        Object instanceResult = raw.instanceEcho("hello");

        System.out.println(names.get(0));
        System.out.println(first);
        System.out.println(instanceResult);
    }
}
```

Biên dịch và chạy:

```bash
javac RawStaticMemberDemo.java
java RawStaticMemberDemo
```

Stdout:

```text
red
hello
hello
```

`Container.labels` tiếp tục có kiểu `List<String>`, và `Container.staticEcho("hello")` tiếp tục dùng generic method để compiler suy luận `U = String`. Trong khi đó, `raw.instanceEcho("hello")` trả `Object` theo quy tắc raw instance method.

Kết luận chính xác:

- **Raw receiver** làm thay đổi kiểu của một số **instance members** thuộc phạm vi §4.8.
- **Static members** của generic class không bị xóa thêm theo việc bạn sử dụng raw receiver.
- Các static field/method vẫn có erasure trong bytecode theo quy tắc chung của Java Generics, nhưng ở **mã nguồn** người gọi vẫn nhận khai báo generic đầy đủ của static member.

Nên truy cập static member bằng tên class `Container.staticEcho(...)`, không qua biến instance: cách này rõ ràng và không gây nhầm lẫn về receiver.

## 10. Thành viên kế thừa: không thể áp dụng một quy tắc “xóa hết” chung

JLS §4.8 nêu riêng rằng kiểu của một **inherited instance method hoặc non-static field** phải xét theo **supertype của raw `C` mà khai báo thành viên đó**. Điều này tạo ra những tình huống mà generic method kế thừa vẫn giữ generic signature của nó.

Tạo tệp `InheritedRawMemberDemo.java`:

```java
public class InheritedRawMemberDemo {

    static class Base {
        <U> U inheritedEcho(U input) {
            return input;
        }
    }

    static class Container<T> extends Base {
        <U> U ownEcho(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Container raw = new Container();

        String inherited = raw.inheritedEcho("kept");
        Object own = raw.ownEcho("erased");

        System.out.println(inherited);
        System.out.println(own);
    }
}
```

Chạy:

```bash
javac InheritedRawMemberDemo.java
java InheritedRawMemberDemo
```

Stdout:

```text
kept
erased
```

`inheritedEcho` được khai báo trong `Base`, là một **non-generic superclass**. Việc receiver có kiểu raw `Container` không buộc phương thức generic này trở thành raw, bởi thành viên được kế thừa qua supertype `Base` vẫn có hợp đồng generic của riêng `Base`.

Ngược lại, `ownEcho` được khai báo **trên class generic `Container<T>`**: khi dùng `Container` raw, kiểu method được nhìn theo erasure, nên `raw.ownEcho("erased")` trả `Object`.

### Khi superclass tự là generic

Không nên suy ra rằng mọi inherited generic method đều luôn giữ nguyên. Xét:

```java
class Parent<X> {
    X read() {
        return null;
    }
}

class Child<T> extends Parent<T> {
}
```

Đây là đoạn class hợp lệ, chưa có `main`. Nếu dùng raw `Child`, supertype tương ứng của `Parent<T>` cũng bị xóa theo quy tắc supertypes của raw type. Vì vậy, thành viên `read()` kế thừa từ `Parent` trong ngữ cảnh đó có thể được nhìn theo erasure của `Parent`, ở đây là `Object`.

**Cách kiểm tra đúng:** Tìm class/interface **khai báo gốc** của member, rồi xét supertype tương ứng của receiver. Đừng tự mặc định rằng chỉ cần biết receiver raw là mọi generic method kế thừa đều mất type parameter của nó.

## 11. So sánh receiver raw với wildcard `<?>`

Raw `Box` và parameterized `Box<?>` có thể đều đọc `get()` thành `Object` khi `T` không giới hạn. Nhưng wildcard vẫn bảo vệ tính nhất quán generic.

Tệp `WildcardInsteadOfRawDemo.java`:

```java
import java.util.List;

public class WildcardInsteadOfRawDemo {

    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        List<String> fixedLabels() {
            return List.of("A", "B");
        }

        <U> U echo(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Box<String> strings = new Box<>("Java");
        Box<?> unknown = strings;

        Object value = unknown.get();
        List<String> labels = unknown.fixedLabels();
        String echoed = unknown.echo("safe");

        System.out.println(value);
        System.out.println(labels.get(1));
        System.out.println(echoed);
    }
}
```

Chạy:

```bash
javac WildcardInsteadOfRawDemo.java
java WildcardInsteadOfRawDemo
```

Stdout:

```text
Java
B
safe
```

Khác biệt thực tế:

- `Box<?>` vẫn là **parameterized type**, nên `fixedLabels()` còn kiểu `List<String>`.
- Method generic riêng `<U> U echo(U)` vẫn cho phép suy luận `U = String`.
- Giá trị `get()` có kiểu `Object` khi `T` không bound, vì đối số thật của `T` chưa biết.
- Nếu `Box<T>` có `void set(T)` thì trên `Box<?>` compiler **không cho** truyền tùy tiện `"hello"` hay `123` vào `set`, vì không chứng minh được chúng phù hợp với kiểu được wildcard đại diện. Thông thường chỉ có thể truyền `null` vào `set(T)` trong bối cảnh này.

Một đoạn cố ý **không biên dịch**:

```java
Box<?> unknown = new Box<String>("Java");
unknown.set("other"); // Không biết T thực tế là gì
```

`Box<?>` giữ an toàn khi không biết `T`; raw `Box` bỏ qua hàng rào kiểu, có thể cho phép lời gọi ghi dữ liệu không phù hợp với cảnh báo unchecked. Vì vậy wildcard phù hợp hơn khi API chỉ muốn “bất kỳ Box nào” và không cần thao tác gán phần tử mới.

## 12. Các trường hợp truy cập field: đọc, gán và warning

Một field khai báo bằng `T` hoặc `List<T>` cũng chịu raw member typing nếu được truy cập qua raw receiver.

```java
import java.util.List;

class Row<T> {
    T item;
    List<T> items;
    List<String> names;
}
```

Đây là đoạn class hợp lệ để phân tích, không có `main`.

Với `Row<Integer> typed`:

- `typed.item` có kiểu `Integer`.
- `typed.items` có kiểu `List<Integer>`.
- `typed.names` có kiểu `List<String>`.

Với `Row raw`:

- `raw.item` có kiểu `Object` do erasure của `T`.
- `raw.items` có kiểu raw `List` do erasure của `List<T>`.
- `raw.names` cũng có kiểu raw `List`, dù nó không phụ thuộc trực tiếp vào `T`.

Các tình huống cảnh báo không hoàn toàn giống nhau:

1. **Gán qua field của raw receiver** như `raw.item = "text"` hoặc `raw.items = someList` có thể được báo là thao tác unchecked nếu erasure làm thay đổi kiểu field.
2. **Gọi method của raw receiver** có thể bị báo unchecked khi erasure làm thay đổi kiểu các tham số hình thức của method. Chẳng hạn `raw.set("text")` khi khai báo là `set(T)`.
3. **Đọc một giá trị raw và gán sang kiểu tham số hóa**, ví dụ `List<String> names = raw.names`, có thể phát sinh **unchecked conversion** từ raw `List` sang `List<String>`.
4. Không phải **mọi** thao tác trên raw receiver đều luôn tạo cảnh báo `unchecked`. Việc đọc một kết quả đã bị xóa thành `Object` thường chỉ đơn giản cho kiểu `Object`; compiler có thể cảnh báo ở phần khai báo raw type (`rawtypes`) nhưng đó là một loại cảnh báo khác.

Sự khác biệt giữa `rawtypes` và `unchecked` hữu ích khi sửa code: một cảnh báo báo việc **bỏ đối số kiểu**, còn cảnh báo kia thường chỉ ra **thao tác không được compiler xác minh đầy đủ**. Chỉ ẩn cảnh báo khi đã chứng minh một biên giới legacy an toàn và khoanh vùng thật nhỏ.

## 13. Method return type và parameter type có thể bị ảnh hưởng khác nhau

Xét khai báo:

```java
class Service<T> {
    T get() {
        return null;
    }

    void accept(T input) {
    }

    java.util.List<String> names() {
        return java.util.List.of();
    }

    void print(String message) {
        System.out.println(message);
    }
}
```

Các đoạn dưới đây dùng để suy luận kiểu, cần đặt trong method phù hợp.

| Thành viên | Qua `Service<String>` | Qua raw `Service` |
|---|---|---|
| `get()` | Trả `String` | Trả `Object` |
| `accept(...)` | Nhận `String` | Nhận `Object` |
| `names()` | Trả `List<String>` | Trả raw `List` |
| `print(...)` | Nhận `String` | Vẫn nhận `String` |
| `getClass()` | Trả `Class<? extends ...>` theo quy tắc `Object.getClass()` | Theo khai báo kế thừa từ `Object`, không áp dụng máy móc quy tắc raw member của `Service` |

Đối với `print(String)`, erasure của `String` vẫn là `String`, nên lời gọi không tự biến thành `print(Object)`.

Một API có thể mất **kiểu trả về generic** ngay cả khi method không nhận tham số; nhưng cảnh báo unchecked của **method invocation** theo quy tắc raw type liên quan trực tiếp đến việc erasure làm thay đổi **formal parameter types**. Vì thế việc không thấy cảnh báo tại `raw.names()` **không chứng minh** kết quả còn là `List<String>`.

## 14. Type erasure trong bytecode và kiểu ở lời gọi

Nên phân biệt hai bước:

1. **Mã nguồn:** Compiler biết receiver là `Box<String>`, `Box<?>` hay raw `Box`, từ đó xác định kiểu tĩnh của biểu thức và các thao tác được phép.
2. **Bytecode:** Các kiểu generic được thể hiện qua erasure trong descriptor, cùng các lệnh chuyển kiểu thích hợp; compiler có thể ghi metadata generic `Signature` để công cụ/reflection truy xuất thông tin khai báo.

Ví dụ khai báo trong `Box<T>`:

```java
T get() { return value; }
void set(T value) { this.value = value; }
java.util.List<String> fixedLabels() {
    return java.util.List.of("A", "B");
}
```

Với `<T>` không bound, các descriptor tương ứng về mặt JVM là:

```text
get:         ()Ljava/lang/Object;
set:         (Ljava/lang/Object;)V
fixedLabels: ()Ljava/util/List;
```

Nếu biên dịch class `RawMemberTypesDemo` ở phần trước, có thể dùng:

```bash
javap -p -s 'RawMemberTypesDemo$Box'
javap -p -v 'RawMemberTypesDemo$Box'
```

`javap -s` cho thấy descriptor. `javap -v` có thể cho thấy generic `Signature` mang dấu vết `T` và `List<String>` ở phần khai báo. Các ký hiệu `#` trỏ tới constant pool hoặc offset lệnh có thể thay đổi giữa các bản JDK; điều cần quan sát là **mối quan hệ giữa descriptor đã xóa và generic metadata**.

Cùng một descriptor `get(): Object` trong class file vẫn có thể được Java source nhìn thành `String` khi receiver là `Box<String>` nhờ kiểm tra kiểu và cast compiler chèn ở nơi sử dụng. Với raw `Box`, thông tin `String` đã bị loại khỏi kiểu của biểu thức nhận, nên trình biên dịch không gán kết quả cho biến `String` nếu không có cast thích hợp.

**Không có bản sao method `get()` riêng cho từng `T`** chỉ vì gọi qua `Box<String>` hoặc `Box<Integer>`. Chính việc compiler giữ hoặc bỏ generic information ở nơi gọi tạo nên khác biệt.

## 15. Mối liên hệ với bridge method và override

Raw type có thể tạo điều kiện cho một lời gọi có tham số sau erasure đi vào **bridge method** do compiler sinh để giữ hành vi override sau generic erasure. Một ví dụ rõ ràng:

Tạo `RawBridgeDemo.java`:

```java
public class RawBridgeDemo {

    static class Parent<T> {
        void save(T value) {
            System.out.println("parent");
        }
    }

    static final class StringChild extends Parent<String> {
        @Override
        void save(String value) {
            System.out.println(value.toUpperCase());
        }
    }

    public static void main(String[] args) {
        Parent<String> typed = new StringChild();
        typed.save("ok");

        Parent raw = typed;
        try {
            raw.save(42);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac RawBridgeDemo.java
java RawBridgeDemo
```

Stdout:

```text
OK
ClassCastException
```

Giải thích:

- `Parent<T>.save(T)` bị xóa thành method có tham số `Object`.
- `StringChild.save(String)` là override hợp lệ sau khi xét `Parent<String>`.
- Compiler có thể tạo trong `StringChild` một **bridge method** nhận `Object`, chuyển kiểu sang `String` rồi chuyển tiếp đến `save(String)`.
- Khi gọi qua raw `Parent`, compiler cho phép `raw.save(42)` theo tham số `Object` và có cảnh báo unchecked; lúc runtime bridge phải ép `Integer` thành `String`, dẫn tới `ClassCastException`.

Bridge method **không phải lỗi của Java Generics** và cũng không làm raw type an toàn hơn. Nó duy trì đa hình theo hợp đồng Java ở nơi lời gọi được biên dịch hợp lệ; raw reference có thể làm lọt một giá trị sai hợp đồng generic đến chỗ cast runtime.

Để quan sát bridge, dùng:

```bash
javap -p -v 'RawBridgeDemo$StringChild'
```

Tìm `save(java.lang.Object)` được đánh dấu `ACC_BRIDGE` và `ACC_SYNTHETIC` bên cạnh `save(java.lang.String)`.

## 16. Làm sao đọc lỗi compiler và sửa đúng nguyên nhân?

### Lỗi “Object cannot be converted to String”

Mã cố ý không hợp lệ:

```java
Box raw = new Box("abc");
String text = raw.get();
```

Giả sử `Box<T>` có `T get()`, việc `raw.get()` được nhìn thành `Object` giải thích lỗi. **Sửa nguyên nhân** bằng cách khai báo kiểu của receiver:

```java
Box<String> box = new Box<>("abc");
String text = box.get();
```

Hai đoạn cần có định nghĩa `Box<T>` và nằm trong một phương thức; chúng nhằm minh họa lỗi và cách sửa, không phải chương trình độc lập.

### Cảnh báo “unchecked call to set(T)”

Mã raw:

```java
Box raw = new Box("abc");
raw.set(99);
```

Compiler không còn biết `T = String`; gọi `set(...)` với tham số erasure `Object` gây unchecked warning. Không thể sửa triệt để bằng cách **ép kiểu giá trị** ngẫu nhiên hoặc tắt warning.

Đổi sang:

```java
Box<String> box = new Box<>("abc");
box.set("new value");
```

giúp compiler kiểm tra lời gọi. `box.set(99)` sẽ bị từ chối.

### Cảnh báo “unchecked conversion” khi gán raw collection

Mã:

```java
java.util.List<String> labels = raw.fixedLabels();
```

khi `raw` là `Box` và `fixedLabels()` là một instance method của class generic, kết quả static type là raw `List`. Compiler cho phép chuyển sang `List<String>` ở một số bối cảnh nhưng **không thể xác minh**, nên cảnh báo unchecked.

Sửa bằng cách dùng receiver parameterized:

```java
Box<String> box = new Box<>("abc");
java.util.List<String> labels = box.fixedLabels();
```

### Bẫy “Tôi đã thêm generic vào method, vậy sẽ an toàn”

Mã:

```java
class Api<T> {
    <U> U convert(U input) {
        return input;
    }
}
```

Qua raw `Api`, generic instance method này có thể bị nhìn theo erasure. Bổ sung `<U>` trong khai báo **không khôi phục được** kiểu `String` tại `raw.convert("abc")`. Cần sửa kiểu receiver hoặc chuyển phương thức thành static generic utility nếu hợp đồng thiết kế cho phép.

## 17. Quy trình phân tích kiểu thành viên khi gặp raw receiver

Khi phải đánh giá một đoạn Java dùng raw type, hãy theo thứ tự:

1. **Xác định kiểu tĩnh của receiver**, không dựa vào class runtime của object. `Box<String>` và `Box` có quy tắc member typing khác nhau.
2. **Xem receiver có thực sự raw không**; `Box<?>` không phải raw.
3. **Tìm nơi khai báo thành viên.** Nó là instance method/field khai báo trực tiếp ở `Box`, inherited member từ superclass/interface hay static member?
4. **Nếu thuộc phạm vi raw member của class đó, áp dụng erasure lên kiểu thành viên.** Không chỉ thay `T` bằng `Object`; phải xóa cả những parameterized types như `List<String>`.
5. **Nếu type variable có bound**, dùng erasure của giới hạn đứng đầu, ví dụ `<T extends Number>` cho `Number`.
6. **Nếu là inherited member**, xét member trong supertype tương ứng mà khai báo nó; không phán đoán từ receiver raw một cách máy móc.
7. **Nếu static**, dùng khai báo generic bình thường của static member, không xóa kiểu thêm vì receiver raw.
8. **Kiểm tra chiều đọc/ghi.** Việc đọc có thể cho `Object`/`List`, còn ghi hoặc gọi method với kiểu đầu vào đã bị erasure có thể tạo unchecked warning và phá hợp đồng generic.
9. **Phân biệt compile time với runtime.** Raw không tạo runtime type argument; cast và bridge method có thể ném `ClassCastException` về sau.
10. **Ưu tiên sửa API/khai báo kiểu**, thay raw bằng `Box<T>`, `Box<?>` hoặc một abstraction phù hợp thay vì tắt cảnh báo.

Một bảng nhận diện nhanh:

| Biểu thức | Kết quả/kết luận chủ yếu |
|---|---|
| `Box<String> b; b.get()` | `String` khi `T` không bound |
| `Box b; b.get()` | `Object` khi `T` không bound |
| `NumberBox b; b.get()` | `Number` nếu `T extends Number` |
| `Box b; b.fixedLabels()` | Raw `List` dù khai báo return là `List<String>` |
| `Box<?> b; b.fixedLabels()` | `List<String>` được giữ lại |
| `Box<?> b; b.echo("x")` | Method generic vẫn có thể suy luận `U = String` |
| `Box b; b.echo("x")` | Method generic do `Box` khai báo bị xem theo erasure |
| `Container.staticEcho("x")` | Static generic method vẫn generic |
| `Container raw; raw.inheritedEcho("x")` | Xét kiểu ở superclass khai báo method |
| `Box raw; raw.set("x")` | Có thể gây unchecked warning và heap pollution |

## 18. Bài tập có đáp án

**Bài 1 — Kiểu của method trả về**

```java
class C<T> {
    java.util.List<String> result() {
        return java.util.List.of("x");
    }
}
```

Với `C<Integer> typed`, `typed.result()` có kiểu gì? Với raw `C raw`, `raw.result()` có kiểu gì?

**Đáp án:** Lần lượt là `List<String>` và raw `List`. Việc method không nhắc đến `T` không làm nó đứng ngoài quy tắc raw instance member của class `C<T>`.

**Bài 2 — Bound ảnh hưởng như thế nào?**

```java
class C<T extends Number & Comparable<T>> {
    T value;
    T get() { return value; }
}
```

Với raw `C`, kiểu của `get()` là gì?

**Đáp án:** `Number`, là erasure của giới hạn đứng đầu `T extends Number & ...`.

**Bài 3 — Generic method tự khai báo kiểu**

```java
class C<T> {
    <U> U identity(U input) { return input; }
}
```

`String x = new C<String>().identity("a")` và `String y = new C().identity("a")` có cùng hợp lệ không?

**Đáp án:** Dòng thứ nhất hợp lệ nhờ suy luận `U = String`. Dòng thứ hai không thể gán trực tiếp kết quả đã bị nhìn như `Object` cho `String` trong Java source.

**Bài 4 — Inherited method**

```java
class Base {
    <U> U keep(U value) { return value; }
}
class Child<T> extends Base { }
```

Với raw `Child raw = new Child();`, `String s = raw.keep("a")` có hợp lệ không?

**Đáp án:** Có. `keep` được khai báo trong non-generic superclass `Base`, nên receiver raw `Child` không làm method này tự nhiên bị erasure theo cách của instance method được khai báo trực tiếp trên `Child<T>`.

**Bài 5 — Static field**

```java
class C<T> {
    static java.util.List<String> defaults = java.util.List.of("ok");
}
```

`C.defaults` còn kiểu `List<String>` ở mã nguồn không?

**Đáp án:** Có; static member giữ kiểu khai báo của nó. Compiler vẫn dùng erasure trong field descriptor của class file theo quy tắc JVM, nhưng đây không phải “raw member conversion” do receiver instance.

**Bài 6 — Chọn giải pháp**

Bạn nhận `Box<?> unknown` và muốn chép toàn bộ dữ liệu ra log, không cần thêm phần tử. Có nên ép về raw `Box` để tránh cast?

**Đáp án:** Không. Sử dụng `Box<?>` để đọc bằng `Object` và làm việc với các thành viên generic còn nguyên. Việc đổi sang raw chỉ khiến compiler bỏ qua các hàng rào kiểm tra kiểu không cần thiết.

**Bài 7 — Dự đoán lỗi runtime**

Có `Box<String> typed = new Box<>("a")`, sau đó `Box raw = typed; raw.set(1);`. Khi gán `String s = typed.get();`, điều gì có thể xảy ra?

**Đáp án:** Sau unchecked call qua raw receiver, object lưu `Integer`. Lời gọi typed có thể phát sinh `ClassCastException` khi kết quả được kiểm tra thành `String`.

## 19. Tổng kết và tài liệu chuẩn

Raw type là công cụ tương thích với code Java cũ, nhưng nó thay đổi cách compiler xác định **kiểu của một số thành viên**. Với constructor, instance method và non-static field được khai báo trực tiếp trên một generic class/interface, truy cập qua raw type khiến kiểu member được nhìn theo **erasure**; hậu quả có thể gồm kết quả bị hạ từ `T` xuống `Object`/bound, từ `List<String>` xuống raw `List`, cùng cảnh báo unchecked khi ghi hoặc gọi method có tham số mất kiểm tra kiểu.

Hai ngoại lệ cần luôn nhớ: **static members không bị raw hóa theo receiver**, còn **inherited members phải xét kiểu của member trong supertype khai báo nó**. So với raw type, một wildcard như `Box<?>` vẫn giữ các quan hệ generic và thường an toàn hơn khi chưa biết tham số kiểu.

Tài liệu đối chiếu:

- [Java Language Specification §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): quy tắc chính thức cho kiểu của constructor, instance fields/methods, inherited/static members và unchecked warnings.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): cách tính erasure cho type variable, parameterized type và method signature.
- [Java Language Specification §4.5.2 — Members and Constructors of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.2): thành viên của kiểu tham số hóa.
- [Java Language Specification §5.1.9 — Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.9): chuyển đổi không thể được kiểm tra đầy đủ ở compile time.
- Công cụ JDK `javac` với `-Xlint:rawtypes -Xlint:unchecked` và `javap -p -s/-v`: hỗ trợ kiểm tra warning, descriptor và bridge method thực tế.