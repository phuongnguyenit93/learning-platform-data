# Truyền đối số kiểu tường minh khi gọi phương thức generic trong Java

Thông thường, khi gọi một phương thức generic, Java tự **suy luận đối số kiểu (type argument)** từ đối số truyền vào và ngữ cảnh. Tuy nhiên, người viết mã cũng có thể **chỉ định trực tiếp kiểu cho tham số kiểu của phương thức**. Kỹ thuật này thường được gọi là *explicit method type arguments* hoặc *type witness*.

Ví dụ, với phương thức:

```java
static <T> T identity(T value) {
    return value;
}
```

hai lời gọi sau đều hợp lệ khi viết trong lớp `Demo` có khai báo phương thức trên:

```java
String a = Demo.identity("Java");           // Compiler suy luận T = String
String b = Demo.<String>identity("Java");   // Chỉ định T = String tường minh
```

Điểm cần ghi nhớ: trong lời gọi tường minh, **`<String>` được viết sau tên lớp/đối tượng và dấu chấm, ngay trước tên phương thức**. Nó là đối số kiểu của **method**, khác với `<T>` nằm trước kiểu trả về trong **khai báo** method.

## 1. Khai báo `<T>` và truyền `<String>` là hai hành động khác nhau

Chữ ký phương thức generic có phần khai báo tham số kiểu:

```java
static <T> T identity(T value) {
    return value;
}
```

- `<T>`: **khai báo** tham số kiểu có tên `T`, dùng bên trong chữ ký và thân phương thức.
- `T` đứng sau `<T>`: **kiểu trả về** của phương thức.
- `T value`: **kiểu của tham số đầu vào**. Hai vị trí `T` biểu diễn cùng một tham số kiểu.
- `Demo.<String>identity("Hello")`: **sử dụng** phương thức bằng cách cung cấp đối số kiểu `String` thay cho `T`.
- `Demo.identity("Hello")`: cũng sử dụng phương thức, nhưng để trình biên dịch suy luận `T` dựa trên ràng buộc.

Tức là một generic method được **khai báo một lần**, rồi có thể được gọi nhiều lần với những kiểu khác nhau. Việc chỉ định `<String>` không tạo phiên bản mã nguồn riêng hay thay đổi class runtime; Java generics thông thường vẫn tuân theo cơ chế **type erasure**.

Bảng đối chiếu:

| Ngữ cảnh | Cú pháp | Vai trò của phần trong `<...>` |
|---|---|---|
| Khai báo generic method | `static <T> T identity(T value)` | Khai báo tên tham số kiểu `T` |
| Gọi để compiler suy luận | `Demo.identity("Hi")` | Không ghi type argument, suy luận khi biên dịch |
| Gọi và chỉ định kiểu | `Demo.<String>identity("Hi")` | Cung cấp `String` cho tham số kiểu `T` |
| Khai báo generic class | `class Box<T> { ... }` | Khai báo `T` thuộc lớp |
| Dùng generic class | `Box<String> box` | Chọn `String` cho `T` thuộc lớp |
| Gọi method nhiều type parameter | `Demo.<String, Integer>entry("age", 36)` | Chọn theo thứ tự `K = String`, `V = Integer` |

Không nên gọi `<T>` trong chữ ký là “truyền đối số kiểu”: đó là **khai báo tham số kiểu**. Ngược lại, `<String>` tại điểm gọi mới là **type argument tường minh**.

## 2. Cú pháp lời gọi tường minh cho static method

Với một static generic method, cách viết dễ hiểu và ổn định nhất là **dùng tên lớp trước dấu chấm**:

```java
Demo.<String>identity("Java");
Demo.<Integer>identity(42);
Demo.<Number>identity(42);
```

Các dòng trên là **minh họa lời gọi**; cần có lớp `Demo` chứa `static <T> T identity(T value)` và đặt lời gọi trong phương thức/khối hợp lệ.

`Demo.<String>identity("Java")` có nghĩa: “gọi `identity` và yêu cầu sử dụng `T = String`”. Trong trường hợp `Demo.<Number>identity(42)`, literal `42` được autobox thành `Integer`; đối tượng `Integer` có thể được sử dụng tại vị trí yêu cầu `Number`. Do đó kiểu trả về ở điểm gọi là `Number`, dù object thực tế là `Integer`.

Cú pháp **sai**:

```java
// Demo.identity<String>("Java"); // Sai thứ tự theo cú pháp Java
// Demo<String>.identity("Java"); // Sai với class Demo không generic
// Demo.<int>identity(42);        // Sai: primitive không phải type argument
```

Trong Java, type argument tường minh **không đặt sau tên phương thức như một số ngôn ngữ khác**. Cần ghi `Demo.<String>identity(...)`, không ghi `Demo.identity<String>(...)`. Type argument cũng phải là kiểu tham chiếu phù hợp; `Integer` được phép, `int` không được phép.

**Có bắt buộc chỉ định không?** Không. `Demo.identity("Java")` thường ngắn, rõ ràng và được compiler suy luận chính xác. Type witness hữu ích khi muốn làm rõ ý định kiểu hoặc khi suy luận mặc định không cho kiểu cần dùng.

## 3. Instance generic method: đặt `<T>` sau dấu chấm của đối tượng

Phương thức instance cũng có thể tự khai báo tham số kiểu:

```java
class Printer {
    <T> String describe(T value) {
        return "value=" + value;
    }
}
```

Khi sử dụng:

```java
Printer printer = new Printer();

String a = printer.describe(10);               // Suy luận T = Integer
String b = printer.<Integer>describe(10);      // Chọn T tường minh
String c = new Printer().<String>describe("x");
```

Đây là các **đoạn code kết hợp minh họa**, cần đặt trong bối cảnh lớp và phương thức thích hợp. Khác biệt giữa static và instance:

- Static: `Utility.<T>method(...)` với qualifier là tên lớp (hoặc kiểu chứa method).
- Instance: `receiver.<T>method(...)` với qualifier là biểu thức/tham chiếu đối tượng có method đó.
- Trong phương thức instance của cùng lớp, có thể dùng `this.<T>method(...)`; với method kế thừa được truy cập phù hợp có thể có `super.<T>method(...)`.

**Type witness gắn với lời gọi method**, không gắn với kiểu của biến receiver. Ví dụ một `Holder<String>` có method `<U> U echo(U x)` vẫn cho phép `holder.<Integer>echo(5)`. `String` là type argument của **lớp Holder**, còn `Integer` là type argument riêng của **echo**.

Một lỗi dễ mắc: viết `printer.<String>describe(10)` chỉ vì muốn kết quả là String. Trả về String cố định của method không quyết định tham số kiểu `T`. Khi chỉ định `T = String`, tham số `value` yêu cầu String; truyền `int` không phù hợp. Type witness luôn tuân theo **vị trí `T` thực sự xuất hiện trong chữ ký**.

## 4. Ví dụ Java 17 chạy độc lập: so sánh suy luận và chỉ định tường minh

Lưu nguyên chương trình thành **`ExplicitTypeArgumentsDemo.java`**:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class ExplicitTypeArgumentsDemo {
    static <T> T identity(T value) {
        return value;
    }

    static <T> List<T> two(T first, T second) {
        return List.of(first, second);
    }

    static <K, V> Map.Entry<K, V> entry(K key, V value) {
        return Map.entry(key, value);
    }

    static <T extends Number> double twice(T number) {
        return number.doubleValue() * 2;
    }

    static final class Holder<T> {
        private final T stored;

        Holder(T stored) {
            this.stored = stored;
        }

        T stored() {
            return stored;
        }

        <U> List<U> duplicate(U value) {
            return List.of(value, value);
        }
    }

    public static void main(String[] args) {
        String inferred = identity("Core");
        String explicit =
                ExplicitTypeArgumentsDemo.<String>identity("Java");
        Number widened =
                ExplicitTypeArgumentsDemo.<Number>identity(42);

        List<Number> numbers =
                ExplicitTypeArgumentsDemo.<Number>two(7, 2.5);

        Map.Entry<String, Integer> record =
                ExplicitTypeArgumentsDemo.<String, Integer>entry(
                        "age", 36);

        Holder<String> holder = new Holder<>("stored");
        List<Integer> repeated = holder.<Integer>duplicate(5);

        var inferredEmpty = Collections.emptyList();
        var typedEmpty = Collections.<String>emptyList();

        System.out.println("inferred: " + inferred);
        System.out.println("explicit: " + explicit);
        System.out.println("widened: " + widened);
        System.out.println("numbers: " + numbers);
        System.out.println("entry: " + record.getKey()
                + "=" + record.getValue());
        System.out.println("class value: " + holder.stored());
        System.out.println("method value: " + repeated);
        System.out.println("empty sizes: "
                + inferredEmpty.size() + "/" + typedEmpty.size());
        System.out.println("bound: "
                + ExplicitTypeArgumentsDemo.<Integer>twice(4));
    }
}
```

Biên dịch/chạy với Java 17 trở lên tại thư mục chứa tệp:

```bash
javac ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

Stdout theo đúng thứ tự:

```text
inferred: Core
explicit: Java
widened: 42
numbers: [7, 2.5]
entry: age=36
class value: stored
method value: [5, 5]
empty sizes: 0/0
bound: 8.0
```

Phân tích những điểm quan trọng:

1. `identity("Core")`: compiler suy luận `T = String` từ đối số mà không cần type witness. `ExplicitTypeArgumentsDemo.<String>identity("Java")` ghi rõ cùng loại ràng buộc.
2. `<Number>identity(42)`: type witness **đặt kiểu tĩnh trả về là `Number`**. Đầu vào `42` được boxing thành `Integer` và có thể truyền cho tham số `Number`. Type witness không biến object runtime thành object `Number` thuần; nó vẫn là instance `Integer`.
3. `<Number>two(7, 2.5)` chọn một kiểu chung `Number` cho cả hai phần tử. `7` và `2.5` được boxing lần lượt thành `Integer` và `Double`, rồi được dùng qua kiểu `Number`. `List.of` ở đây không cho phép sửa nội dung bằng các phương thức thêm/xóa.
4. `<String, Integer>entry("age", 36)` điền **hai type argument theo thứ tự** khai báo `<K, V>`. `Map.entry` tạo một entry không chấp nhận `null` và không hỗ trợ thay `value` qua `setValue`.
5. `Holder<String>` có tham số kiểu lớp `T = String`. Riêng `holder.<Integer>duplicate(5)` chọn `U = Integer` cho method, hoàn toàn độc lập với tham số kiểu của lớp.
6. `Collections.emptyList()` trả danh sách rỗng immutable với method signature `<T> List<T> emptyList()`. Khi dùng `var inferredEmpty`, không có một target type cụ thể để buộc `T = String`, nên type inference chọn `Object` trong ví dụ này. `var typedEmpty = Collections.<String>emptyList()` giữ được kiểu biến là `List<String>` ở compile time. Kích thước hai danh sách đều là 0; khác biệt không hiển thị ở stdout, mà nằm trong **kiểu tĩnh**.
7. `<Integer>twice(4)` cho `T = Integer`, một subtype của `Number`; `doubleValue()` trả `4.0` rồi nhân 2 thành `8.0`.

**Lưu ý:** việc method cho phép chỉ định kiểu rộng hơn (`<Number>`) không đồng nghĩa mọi kiểu bất kỳ đều hợp lệ. `<String>twice("4")` sai vì `String` không thỏa bound `T extends Number`.

## 5. Khi nào explicit type argument thật sự hữu ích?

### 5.1. Khi không có đối số để suy luận `T`

Một ví dụ chuẩn từ Java Collections:

```java
List<String> a = Collections.emptyList();         // Suy luận từ kiểu đích
var b = Collections.<String>emptyList();         // Chọn kiểu tường minh
```

Hai dòng là **đoạn minh họa**, cần import `List` và `Collections` và đặt vào method. Cả hai có kiểu `List<String>`. Với dòng thứ nhất, **target typing** từ bên trái cung cấp ràng buộc; với dòng thứ hai, `<String>` cung cấp ràng buộc ngay tại lời gọi dù kiểu biến được suy luận bằng `var`.

Đặc biệt hữu ích khi generic method **trả về kiểu có `T` nhưng không nhận tham số nào mang `T`**, ví dụ `Collections.<String>emptyList()`. Nếu chỉ gọi `Collections.emptyList()` trong một ngữ cảnh không yêu cầu kiểu phần tử cụ thể, compiler có thể chọn `Object`.

### 5.2. Khi muốn API trả về một kiểu rộng có chủ đích

```java
List<Number> values =
        ExplicitTypeArgumentsDemo.<Number>two(7, 2.5);
```

Trong ví dụ, `Integer` và `Double` đều dùng được qua `Number`. Ghi type witness giúp thể hiện rõ **quyết định dùng một kiểu chung**. Không có nó, compiler vẫn có thể suy luận một common type phù hợp (tùy các ràng buộc/target type); explicit type argument chủ yếu giúp làm rõ hoặc cố định ý định.

`<Number>` không tự ép mọi giá trị thành số hợp lệ: gọi `two("seven", 2.5)` khi yêu cầu `T = Number` sẽ không biên dịch.

### 5.3. Khi ngữ cảnh làm suy luận khó đọc hoặc không đạt kiểu cần dùng

Một lời gọi lồng nhau có thể có nhiều ràng buộc suy luận cùng lúc. Nếu compiler suy luận không như ý, chỉ định type witness **tại chính generic method liên quan** giúp người đọc và trình biên dịch biết kiểu mục tiêu. Ví dụ:

```java
static <T> List<T> empty() {
    return List.of();
}

// Khi dùng:
var texts = Helper.<String>empty();
```

Đây là **minh họa**, giả sử phương thức `empty` nằm trong lớp `Helper` và đã import `List`. `texts` sẽ có kiểu `List<String>`, thay vì để compiler chọn tham số kiểu từ ngữ cảnh nghèo thông tin.

Trước khi thêm explicit type argument, cũng nên cân nhắc **khai báo biến có kiểu đích rõ ràng**:

```java
List<String> texts = Helper.empty();
```

Với kiểu đích có sẵn, compiler thường suy luận được và lời gọi ngắn hơn. Không phải lúc nào type witness cũng giúp chương trình đúng hơn.

### 5.4. Khi viết ví dụ hướng dẫn hoặc kiểm tra generic API

Trong tài liệu API hoặc bài kiểm tra biên dịch, `Utility.<Long>identity(1L)` giúp chỉ ra rằng phương thức đã được gọi với `T = Long`. Tuy nhiên, trong mã sản phẩm, nếu `Utility.identity(1L)` đã rõ và an toàn, thường nên ưu tiên suy luận.

## 6. Explicit type argument phải tuân theo chữ ký method

**Type witness không phải cast**, không dùng để né hợp đồng kiểu.

Xét `static <T> T identity(T input)`, với tệp ví dụ có class `ExplicitTypeArgumentsDemo`:

```java
String text =
        ExplicitTypeArgumentsDemo.<String>identity("hello"); // Hợp lệ

Number number =
        ExplicitTypeArgumentsDemo.<Number>identity(12); // Hợp lệ

// String invalid =
//         ExplicitTypeArgumentsDemo.<String>identity(12); // Không biên dịch
```

Trong trường hợp lỗi, `<String>` yêu cầu tham số đầu vào là `String`, nhưng `12` là `int` và không có chuyển đổi invocation hợp lệ từ `int` sang `String`. Không thể “ra lệnh cho compiler” coi mọi đối số là `String` chỉ bằng cú pháp `<String>`.

Nếu type parameter có bound:

```java
static <T extends Number> double twice(T value) {
    return value.doubleValue() * 2;
}
```

thì chỉ những type argument thỏa bound mới hợp lệ:

```java
double ok = ExplicitTypeArgumentsDemo.<Integer>twice(3);
double alsoOk = ExplicitTypeArgumentsDemo.<Number>twice(3);

// double wrong =
//         ExplicitTypeArgumentsDemo.<String>twice("3"); // Sai bound
```

Các đoạn này là **mã minh họa**; phương thức `twice` ở ví dụ chạy độc lập đã có phần thân đúng. Lưu ý `T = Number` vẫn hợp lệ vì `Number` thỏa upper bound `Number`.

Tương tự, nếu method có **hai tham số kiểu** `<K, V>` thì lời gọi tường minh cần cung cấp cả hai type argument theo đúng thứ tự: `ClassName.<String, Integer>entry(...)`. Không thể chỉ viết `ClassName.<String>entry(...)` và yêu cầu compiler tự điền riêng `V` trong type argument list ấy; Java không cho pha trộn danh sách type argument tường minh không đầy đủ với suy luận các phần còn lại theo cách đó.

## 7. Những ngữ cảnh cần phân biệt

### Generic method khác generic class

```java
class Store<T> {
    T read() {
        return null;
    }

    <U> U echo(U value) {
        return value;
    }
}
```

Trong lớp minh họa, `read()` trả `T` thuộc **class `Store<T>`** và không tự khai báo type parameter mới. Vì vậy `store.<String>read()` **không phải cách chỉ định lại `T` của class**. Kiểu của `T` được chọn khi khai báo biến/đối tượng, ví dụ `Store<Integer> store = new Store<>();`.

Ngược lại, `store.<String>echo("x")` chỉ định type argument riêng cho generic method `echo`, và có thể khác type argument `Integer` của `Store`.

### Generic method có return type cố định

```java
static <T> void print(T value) {
    System.out.println(value);
}
```

Có thể gọi `Utility.<String>print("Hi")` (giả sử method nằm trong `Utility`). Việc method trả `void` không ngăn nó là generic method; type witness vẫn áp dụng lên **tham số đầu vào**. Ngược lại, type witness **không sửa** return type của method: nếu method trả `int`, chọn `<String>` không biến nó thành method trả `String`.

### Generic constructor

Constructor có thể có type parameter riêng; nhưng **cú pháp truyền type argument cho constructor** không giống gọi method sau dấu chấm. Trong lời gọi generic constructor, type arguments có thể đứng sau `new` và trước tên lớp:

```java
class Message {
    <T> Message(T input) {
        System.out.println(input);
    }
}

// new <String> Message("Hi");
```

Đây là **minh họa**, không nằm trong chương trình `ExplicitTypeArgumentsDemo`. Cú pháp `new <String> Message("Hi")` thuộc generic constructor, còn `Utility.<String>method("Hi")` thuộc generic method. Không trộn hai vị trí khai báo/chỉ định này.

### Generic type arguments và primitive

Không thể cung cấp `int` làm type argument: `Utility.<int>identity(5)` sai, `Utility.<Integer>identity(5)` hợp lệ. Nếu gọi `identity(5)` để compiler suy luận, autoboxing cho phép `T` được thể hiện bằng kiểu bao `Integer`, không phải primitive `int`.

## 8. Cú pháp khi gọi instance method qua `this`, `super`, hoặc biểu thức

Bên cạnh tên lớp (static call), lời gọi có receiver cũng nhận type witness:

```java
class Base {
    <T> T copy(T value) {
        return value;
    }
}

class Child extends Base {
    String example() {
        String viaThis = this.<String>copy("one");
        String viaSuper = super.<String>copy("two");
        return viaThis + "/" + viaSuper;
    }
}
```

Hai class trên là **đoạn minh họa**. `Child.example()` trả `"one/two"`. `this.<String>copy(...)` gọi thông qua receiver hiện tại; `super.<String>copy(...)` gọi triển khai có thể truy cập của lớp cha theo quy tắc `super` thông thường. Type witness không thay đổi cơ chế kế thừa hay dispatch mà chỉ làm rõ kiểu cho generic method.

Một biểu thức trả về đối tượng cũng có thể làm receiver:

```java
String a = new Printer().<String>echo("A");
```

Ở đây giả sử `Printer` có một instance method generic `<T> T echo(T value)`. Vị trí quan trọng vẫn là **sau dấu chấm và trước tên method**. Đừng viết `new Printer()<String>.echo("A")`; đó không phải cú pháp method invocation hợp lệ.

## 9. Type inference và overload: đừng dùng type witness như cơ chế ép chọn overload

Khi có nhiều method cùng tên, Java sử dụng các quy tắc **overload resolution** (xét kiểu đối số, phương thức áp dụng được, mức độ cụ thể...) để chọn phương thức tại compile time. Generic type arguments tường minh có thể ảnh hưởng việc một generic candidate có áp dụng được hay không, nhưng **không bảo đảm ép chọn một overload bất kỳ** nếu có các overload khác.

Nếu gặp lời gọi ambiguous hoặc overload không như mong muốn, nên:

1. Kiểm tra **chữ ký** và các bound của những generic method cùng tên.
2. Đọc các kiểu **tĩnh** của đối số và ngữ cảnh trả về.
3. Thử một type witness hợp lệ nếu mục tiêu là đặt type argument cho generic candidate.
4. Khi cần chỉ định overload theo một kiểu tham số rõ ràng, cân nhắc đổi kiểu biểu thức đối số hợp lệ, đổi tên method, hoặc thiết kế lại overload để tránh mơ hồ.

Ví dụ, `<T>` ở một method không tự mang danh tính runtime riêng để overload với `Object`. Hai chữ ký cùng lớp sau **xung đột sau type erasure**, nên không biên dịch:

```java
void log(Object value) { }

<T> void log(T value) { }
```

Đây là **ví dụ lỗi tách biệt**: `T` không bound bị erasure về `Object`, nên hai method có cùng chữ ký JVM. Việc gọi với `<String>` không chữa được lỗi trùng chữ ký ở phần khai báo.

## 10. Type erasure: chỉ định `<T>` không lưu kiểu ở runtime

Khi viết:

```java
String value = Utility.<String>identity("x");
```

trình biên dịch hiểu `T = String` cho lời gọi, dùng để kiểm tra tham số và kiểu trả về. Nhưng generic method trong Java thường được triển khai bằng **type erasure**:

- Type parameter không bound như `T` thường bị erasure thành `Object`.
- Compiler kiểm tra ràng buộc và có thể chèn cast ở nơi lấy kết quả.
- Không tạo một `identity<String>` và một `identity<Integer>` riêng ở runtime chỉ vì type witness khác nhau.
- Không thể hỏi trực tiếp một instance: “method vừa được gọi với `T` nào?” nếu thông tin đó không được mang theo qua cơ chế khác.
- Type witness không biến một phép cast sai thành an toàn; các lỗi kiểu vẫn được phát hiện tại compile time khi có thể.

Để biết một lớp runtime một cách tường minh, API có thể nhận `Class<T>`:

```java
static <T> T checkedCast(Class<T> type, Object value) {
    return type.cast(value);
}
```

Đây là **method minh họa**, phải được khai báo trong class. Cách gọi `Utility.<String>checkedCast(String.class, someObject)` vừa chỉ định type argument `String`, vừa truyền **runtime type token** `String.class`; chính `Class.cast` sẽ kiểm tra object ở runtime. Type witness đơn lẻ không thực hiện bước kiểm tra runtime đó. Khi loại `T` chỉ biểu diễn các kiểu có type argument generic lồng nhau, `Class<T>` cũng không lưu đầy đủ mọi type argument như `List<String>`; cần thiết kế type token phù hợp nếu yêu cầu phức tạp hơn.

## 11. Những lỗi cú pháp và cách dùng thường gặp

**Lỗi 1: Đặt type argument sau tên method.** `Utility.identity<String>("x")` sai cú pháp Java. Sửa thành `Utility.<String>identity("x")`.

**Lỗi 2: Nhầm type argument của class với của method.** `Holder<String>` chọn kiểu cho lớp; `holder.<Integer>duplicate(5)` chọn kiểu riêng cho method. Không thể dùng type witness ở lời gọi để thay đổi tham số kiểu của một class instance đã có.

**Lỗi 3: Chỉ định primitive làm type argument.** `Utility.<int>identity(5)` không hợp lệ. Dùng `<Integer>` hoặc bỏ type witness để compiler suy luận qua boxing.

**Lỗi 4: Chỉ định một phần đối số kiểu của method nhiều tham số kiểu.** Nếu khai báo `<K, V>`, phải ghi đủ `<String, Integer>` khi viết tường minh; không ghi chỉ `<String>`. Nếu muốn suy luận cả hai, bỏ toàn bộ danh sách tường minh.

**Lỗi 5: Chọn type argument không phù hợp kiểu đầu vào.** `Utility.<String>identity(42)` sai vì `42` không truyền được cho tham số `String`. Type witness không phải cast.

**Lỗi 6: Chọn type argument vi phạm bound.** Với `<T extends Number>`, `<String>` không hợp lệ. Bound vẫn được compiler kiểm tra đầy đủ dù type argument được ghi tường minh.

**Lỗi 7: Thêm type witness ở mọi lời gọi mà không có lợi ích.** `Utility.<String>identity("x")` đúng, nhưng `Utility.identity("x")` thường đủ rõ. Explicit type arguments nên giải thích hoặc giải quyết một nhu cầu kiểu thực sự, tránh làm code rối.

**Lỗi 8: Tưởng type witness thay đổi return type cố định.** Với `<T> int size(List<T> input)`, return type luôn là `int`; `Utility.<String>size(...)` không làm return type trở thành `String`.

**Lỗi 9: Lẫn `var` với explicit type argument.** `var x = Collections.emptyList()` để compiler tự suy luận kiểu biến theo lời gọi; `var x = Collections.<String>emptyList()` chỉ định `String` cho method. `var` không tự mang ý nghĩa “`T = String`”.

**Lỗi 10: Hiểu nhầm `List<Integer>` được đổi sang `List<Number>` nhờ witness.** Generics thường invariant. `List<Integer> integers` không thể trực tiếp gán sang `List<Number>`. Type witness ở một method tạo danh sách mới có thể giúp thiết kế **kiểu kết quả** phù hợp, nhưng không biến đổi quan hệ subtype giữa hai kiểu danh sách đã tồn tại.

**Lỗi 11: Nghĩ type argument tường minh làm object runtime tự đổi class.** `<Number>identity(42)` trả về một tham chiếu được nhìn qua `Number` ở compile time; object vẫn thuộc lớp `Integer`. Không có hành vi biến `Integer` thành một instance `Number` riêng.

**Lỗi 12: Tưởng method nào cũng chấp nhận `.<T>`.** Không phải mọi method khai báo type parameter riêng. Nếu chỉ `class Box<T>` mà `T get()` không có `<U>`, không thể dùng `box.<String>get()` để thay `T` của lớp. Xác định đúng **generic method declaration** trước khi gọi.

## 12. Bài luyện tập tự kiểm tra

**Câu 1.** Cho `static <T> T identity(T x)`. Cách nào truyền tường minh `T = String` qua tên lớp `Util`?  
**Đáp án:** `Util.<String>identity("abc")`.

**Câu 2.** `Util.identity("abc")` có khác `Util.<String>identity("abc")` về giá trị trả về trong trường hợp này không?  
**Đáp án:** không; cả hai đều trả chuỗi `"abc"` và có kiểu tĩnh `String` thích hợp. Lời gọi thứ nhất dùng suy luận, lời gọi thứ hai chỉ định.

**Câu 3.** Vì sao `Util.<int>identity(5)` sai?  
**Đáp án:** type argument của generic method trong Java 17 phải là kiểu tham chiếu; dùng `Integer`.

**Câu 4.** Với `static <K, V> Map.Entry<K, V> entry(K k, V v)`, muốn dùng `K = String`, `V = Long` thì viết thế nào?  
**Đáp án:** `Util.<String, Long>entry("id", 1L)`.

**Câu 5.** `Holder<String>` có method `<U> U echo(U x)`. Có thể gọi `holder.<Integer>echo(10)` không?  
**Đáp án:** có; type parameter `U` của method độc lập với type parameter `T` của lớp Holder.

**Câu 6.** Vì sao `var xs = Collections.<String>emptyList()` giữ được `String` ở kiểu tĩnh?  
**Đáp án:** `<String>` chọn `T = String` cho phương thức `<T> List<T> emptyList()`; `var` lấy kiểu biểu thức kết quả là `List<String>`.

**Câu 7.** Có thể viết `Util.<String>identity(42)` để compiler tự biến `42` thành chuỗi không?  
**Đáp án:** không; không có phép chuyển đổi truyền tham số phù hợp từ `int` sang `String`.

**Câu 8.** Với `static <T extends Number> double twice(T value)`, `Util.<Number>twice(5)` hợp lệ không?  
**Đáp án:** có. `Number` thỏa bound; `5` được boxing thành `Integer`, có thể dùng như `Number`.

**Câu 9.** `<String>` ở `Util.<String>identity(...)` có tạo một class/method runtime riêng không?  
**Đáp án:** không; Java generics thông thường dùng type erasure. Type witness phục vụ kiểm tra/suy luận kiểu khi biên dịch.

**Câu 10.** Khi nào nên bỏ type witness?  
**Đáp án:** khi compiler suy luận đúng và lời gọi không gây mơ hồ, ví dụ `identity("abc")`. Chỉ định tường minh khi cần giữ một kiểu cụ thể, làm rõ ý định hoặc giúp kiểm tra ràng buộc.

**Câu 11.** Type argument tường minh được đặt ở đâu khi gọi instance method?  
**Đáp án:** sau biểu thức receiver và dấu chấm, ngay trước tên method: `obj.<String>echo("abc")`.

**Câu 12.** Một method `static List<String> words()` có thể nhận `Util.<Integer>words()` chỉ vì return type là generic `List<String>` không?  
**Đáp án:** không có tham số kiểu method để đặt thành `Integer`; chữ ký `words()` trả một `List<String>` cố định.

Hãy ghi nhớ hai mẫu khác nhau: **khai báo** `static <T> T method(T x)` và **gọi tường minh** `ClassName.<String>method("x")`. Một bên định nghĩa tham số kiểu; bên kia chọn đối số kiểu cho một lời gọi. Trong đa số trường hợp, compiler tự suy luận tốt; khi lựa chọn tường minh, kiểu đã chọn vẫn phải thỏa mọi tham số, bound và quy tắc an toàn kiểu của Java.
