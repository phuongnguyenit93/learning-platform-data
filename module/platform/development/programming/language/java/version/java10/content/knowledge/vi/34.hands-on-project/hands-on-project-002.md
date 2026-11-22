# Kiểm tra var với diamond, generic và phương thức nạp chồng — Thực hành tổng hợp Java 10+

## 1. Mục tiêu và tình huống thực tế

Java 10 bổ sung **local-variable type inference**, cho phép khai báo biến cục bộ bằng `var` (JEP 286). Tính năng làm mã ít lặp kiểu hơn, nhưng có thể làm thay đổi kiểu generic mà compiler suy luận nếu ta thay đồng thời **kiểu vế trái** bằng `var` và **type arguments vế phải** bằng diamond `<>`.

Xét hai khai báo nhìn khá giống nhau:

```java
List<String> names = new ArrayList<>();
var names2 = new ArrayList<>();
```

Trong Java, kiểu của chúng **không tương đương**:

- `names` có kiểu tĩnh `List<String>`.
- `names2` có kiểu tĩnh `ArrayList<Object>` trong ví dụ này.

Nếu có các overload:

```java
static String classify(List<String> values) { return "List<String>"; }
static String classify(Object value) { return "Object"; }
```

thì `classify(names)` và `classify(names2)` có thể gọi **hai phương thức khác nhau**, dù cả hai đều trỏ tới object `ArrayList` khi chạy.

**Đây là vấn đề trọng tâm:** `var` là **suy luận kiểu tĩnh tại compile time**, không phải kiểu động; diamond và generic method inference phụ thuộc ngữ cảnh; overload resolution cũng dùng kiểu tĩnh. Một refactor “rút gọn cú pháp” có thể làm đổi overload được chọn mà **không có compile error**.

Sau bài này, bạn sẽ:

1. Suy luận đúng kiểu của `var` trong các trường hợp có và không có generic type information.
2. Biết diamond `<>` khác raw types và khác generic method inference thế nào.
3. Hiểu **target typing** trong `List<String> names = new ArrayList<>();` và lý do nó không còn khi viết `var names = new ArrayList<>();`.
4. Nhận ra `ArrayList<Object>` không thể truyền vào `List<String>`.
5. Kiểm tra lời gọi overload có tham số `List<String>` hoặc `Object`.
6. Kiểm tra overload `int`, `long`, `Integer` và overload theo loại tham chiếu.
7. Dùng generic method `Collections.emptyList()`, `List.of()`, type witness và generic method do mình viết.
8. Phân biệt lỗi generic erasure, overload ambiguity và initializer không đủ kiểu.
9. Biên dịch/chạy chương trình **Java 10** trên JDK mới, so khớp stdout.
10. Viết regression tests chống rủi ro khi refactor code dùng `var`.

Nội dung tập trung vào **cơ chế còn áp dụng trên JDK hiện đại**, không đề xuất sử dụng raw types, unchecked casts hoặc cấu hình compiler legacy.

## 2. var: kiểu được chốt tại vị trí khai báo

**JEP 286 — Local-Variable Type Inference** cho phép compiler dùng kiểu của biểu thức khởi tạo để xác định kiểu tĩnh của một local variable.

```java
var integer = 1;                 // int
var bigger = 1L;                 // long
var text = "java";               // String
var boxed = Integer.valueOf(1);  // Integer
var values = new int[] {1, 2};  // int[]
```

Khi compiler hoàn tất suy luận, chương trình được kiểm tra như có khai báo tường minh của kiểu vừa suy được.

```java
var value = "hello"; // String
value = "world";     // hợp lệ
// value = 42;       // lỗi: không thể gán int cho String
```

**Compiler không nhìn vào các câu lệnh sử dụng biến xuất hiện về sau để thay đổi kiểu đã được suy luận.**

### Không phải dynamic typing

Hai biến có thể tham chiếu tới object có class `String` lúc chạy nhưng có kiểu tĩnh khác:

```java
var narrow = "hello";          // String
var broad = (Object) "hello";  // Object
```

Khi có overload `print(String)` và `print(Object)`, lời gọi với `narrow` chọn phương thức nhận String, còn lời gọi với `broad` chọn phương thức nhận Object. Việc object của `broad` thật ra là String **không làm compiler đổi overload đã chọn**.

### Những giới hạn vẫn tồn tại

- Dùng `var` cho local variable **có initializer phù hợp**; có thể dùng trong for/enhanced-for/try-with-resources khi ngữ pháp cho phép.
- Không dùng `var` làm kiểu của field hoặc method return type.
- Không dùng `var x;` nếu chưa có initializer.
- `var x = null;` không có kiểu suy luận hợp lệ.
- `var f = () -> 42;` không hợp lệ nếu lambda thiếu target functional interface.
- `var` là tên kiểu được dành riêng theo ngữ cảnh, không phải lời khai báo “kiểu bất kỳ”.

**Phân biệt phiên bản:** JDK 11 bổ sung cú pháp `(var x) -> ...` cho **tham số lambda** (JEP 323). Nó **không** khiến `var f = () -> ...` trở thành hợp lệ trong Java 10 hay Java mới.

## 3. Diamond <> và target typing

Diamond xuất hiện trong generic constructor expression:

```java
List<String> names = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
```

Khi vế trái có kiểu tường minh, compiler có **target type**. Với khai báo đầu, target type `List<String>` cung cấp thông tin để generic argument `E` của `ArrayList<E>` là `String`.

**Lưu ý:** diamond `<>` **không phải raw type**. `new ArrayList<>()` tham gia generic inference và giữ type safety. `new ArrayList()` bỏ generic arguments, tạo **raw type** và có thể gây warning unchecked; không khuyến nghị dùng trong code mới.

### Khi thay cả hai vế bằng var + diamond

```java
var items = new ArrayList<>();
```

Ở đây không còn target type nói rằng `E=String`, và constructor không có đối số ràng buộc `E`. Kết quả thông thường của trường hợp này là:

```java
ArrayList<Object> items = new ArrayList<>();
```

Vì vậy:

```java
items.add("java");
items.add(42);
```

đều hợp lệ. **Đừng suy rằng biến sẽ thành ArrayList<String> vì lần add đầu tiên là String.**

Ngược lại:

```java
var names = new ArrayList<String>();
```

cho kiểu tĩnh `ArrayList<String>` vì vế phải đã cung cấp generic argument.

### Cách chọn cú pháp đúng ý định

| Cú pháp | Kiểu tĩnh | Nhận xét |
| --- | --- | --- |
| `List<String> a = new ArrayList<>();` | `List<String>` | Rõ kiểu phần tử và interface abstraction |
| `ArrayList<String> a = new ArrayList<>();` | `ArrayList<String>` | Rõ kiểu phần tử và implementation |
| `var a = new ArrayList<String>();` | `ArrayList<String>` | Có thể rút gọn vế trái mà không mất String |
| `var a = new ArrayList<>();` | `ArrayList<Object>` | Dễ ngoài ý muốn nếu đang cần List<String> |
| `var a = new ArrayList<>(List.of("java"));` | `ArrayList<String>` | Constructor argument cung cấp type evidence |

**Khi muốn lập trình theo interface**, giữ `List<String> a = new ArrayList<>();` thường có ý nghĩa hơn, vì kiểu tĩnh của `var a = new ArrayList<String>();` là implementation `ArrayList<String>`.

## 4. Constructor argument có thể giúp suy luận

Trường hợp:

```java
var names = new ArrayList<>(List.of("java"));
```

khác `var names = new ArrayList<>()`. `List.of("java")` tạo một `List<String>` nhờ đối số String. Constructor của `ArrayList` nhận `Collection<? extends E>`, cho compiler ràng buộc để suy luận `E=String`.

Trong bài test đã biên dịch với `javac --release 10`, biến `names` có thể truyền vào phương thức nhận `List<String>`.

**Không suy rộng một công thức duy nhất cho mọi generic constructor**. Kết quả phụ thuộc chữ ký constructor, bounds, nested expression và target typing. Điều quan trọng là kiểm tra **nguồn thông tin kiểu** thực sự tồn tại ở initializer.

### Không được dựa vào những lệnh ở dòng sau

```java
var names = new ArrayList<>();  // ArrayList<Object>
names.add("first");
names.add("second");
```

Hai lời gọi add không làm compiler suy ngược `String` vào constructor. Nó đã khóa `ArrayList<Object>` tại khai báo.

## 5. Generics invariant: vì sao List<Object> không phải List<String>?

`String extends Object` là đúng. Nhưng:

```text
List<String> không phải subtype của List<Object>.
List<Object> không phải subtype của List<String>.
```

Generic parameterization mặc định **invariant** trong Java. Nếu cho gán tự do `List<Object>` sang `List<String>`, người khác có thể thêm Integer vào danh sách mà một đoạn code khác đang giả định chỉ chứa String.

Ví dụ **cố tình không biên dịch**:

```java
import java.util.ArrayList;
import java.util.List;

class InvalidDiamond {
    static void onlyStrings(List<String> xs) {}

    void test() {
        var xs = new ArrayList<>();
        onlyStrings(xs); // error: ArrayList<Object> != List<String>
    }
}
```

Compiler đã suy luận `xs` có kiểu `ArrayList<Object>` nên lời gọi không hợp lệ.

**Sửa đúng:**

```java
List<String> xs = new ArrayList<>();
// hoặc:
var xs2 = new ArrayList<String>();
```

Đừng dùng unchecked cast qua `List<?>` hoặc raw `List` để che vấn đề. Cách sửa an toàn là **cung cấp lại type arguments phù hợp**.

### Wildcard là một thiết kế API khác

Một hàm chỉ cần đọc dữ liệu theo kiểu Object có thể nhận `List<?>`. Nhưng nó không cho phép thêm tùy ý phần tử khác null vào list. Không nên thay method nhận `List<String>` bằng `List<?>` chỉ để một khai báo `var + <>` lỗi biên dịch trở nên hợp lệ.

## 6. Generic method inference cũng cần xem ngữ cảnh

Xét generic method có sẵn:

```java
Collections.emptyList()
```

Ở khai báo:

```java
List<String> a = Collections.emptyList();
```

vế trái cung cấp target type `List<String>`, nên generic method invocation được suy luận tương thích với String.

Nhưng:

```java
var a = Collections.emptyList();
```

không cung cấp target type từ vế trái. Trong ngữ cảnh này, kết quả được suy ra là `List<Object>`.

Tương tự:

```java
var a = List.of();          // List<Object>
var b = List.of("java");    // List<String>
```

Lời gọi không có đối số thiếu bằng chứng về element type; lời gọi có String argument cho phép suy luận String.

**Lưu ý riêng:** `List.of(...)` tạo danh sách unmodifiable. Không nhầm tính unmodifiable với kiểu generic được suy luận: đó là hai thuộc tính khác nhau.

### Cách giữ String với factory không có đối số

```java
List<String> a = Collections.emptyList();
var b = Collections.<String>emptyList();
var c = List.<String>of();
```

Ba khai báo trên đều cho kiểu phần tử String. Hai khai báo sau dùng **explicit method type witness** `<String>`.

### Một generic method do mình viết

```java
static <T> List<T> singleton(T element) {
    return List.of(element);
}
```

Khi gọi `var words = singleton("hello");`, compiler có type evidence từ đối số String, suy `T=String` và cho biến có kiểu `List<String>`. **Kết hợp var với generic method không phải lúc nào cũng rơi về Object**: nó phụ thuộc initializer có đủ ràng buộc hay không.

## 7. Method overloading: compiler quyết định trước runtime

Xét hai phương thức:

```java
static String classify(List<String> values) { return "List<String>"; }
static String classify(Object value) { return "Object"; }
```

Đây là hai overload **hợp lệ**: phần signature sau erasure dùng parameter types `List` và `Object`.

Giờ đặt:

```java
var broad = new ArrayList<>();       // ArrayList<Object>
var narrow = new ArrayList<String>(); // ArrayList<String>
```

Ở `classify(broad)`:

- `List<String>` không áp dụng vì `ArrayList<Object>` bất biến về generic type argument.
- `Object` áp dụng.
- Compiler chọn `classify(Object)`.

Ở `classify(narrow)`:

- Cả `List<String>` và `Object` đều có thể nhận đối số.
- `List<String>` cụ thể hơn đối với đối số này.
- Compiler chọn `classify(List<String>)`.

**Hậu quả thực tế:** thay `List<String> names = new ArrayList<>();` thành `var names = new ArrayList<>();` có thể làm code vẫn compile nhưng chọn **overload khác**, thay đổi hành vi.

### Overloading không giống overriding

- **Overloading:** cùng tên, nhiều signatures; chọn phương thức áp dụng theo static types và JLS overload resolution.
- **Overriding:** subclass thay implementation của một instance method; implementation được dispatch theo runtime object type trong trường hợp có dynamic dispatch.

Đừng dùng runtime `getClass()` để đoán overload được chọn cho generic caller. Generic type arguments của `ArrayList<String>` và `ArrayList<Object>` không phải class runtime khác nhau.

## 8. Bảng dự đoán overload khi dùng var và generics

Với `classify(List<String>)` và `classify(Object)`:

| Biểu thức | Kiểu của biến | Phương thức được chọn |
| --- | --- | --- |
| `var xs = new ArrayList<>();` | `ArrayList<Object>` | `Object` |
| `var xs = new ArrayList<String>();` | `ArrayList<String>` | `List<String>` |
| `List<String> xs = new ArrayList<>();` | `List<String>` | `List<String>` |
| `var xs = new ArrayList<>(List.of("java"));` | `ArrayList<String>` | `List<String>` |
| `var xs = Collections.emptyList();` | `List<Object>` | `Object` |
| `List<String> xs = Collections.emptyList();` | `List<String>` | `List<String>` |
| `var xs = Collections.<String>emptyList();` | `List<String>` | `List<String>` |
| `var xs = singleton("hello");` | `List<String>` | `List<String>` |

Bảng này được kiểm chứng bằng chương trình đầy đủ ở mục 9. Đây là **kiểu tĩnh Java**, không phải cấu trúc runtime của collection.

## 9. Chương trình hoàn chỉnh Java 10+: VarDiamondGenericOverloadDemo

Tạo file **`VarDiamondGenericOverloadDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class VarDiamondGenericOverloadDemo {
    private VarDiamondGenericOverloadDemo() {}

    static String classify(List<String> values) { return "List<String>"; }
    static String classify(Object value) { return "Object"; }

    static String numeric(int value) { return "int"; }
    static String numeric(long value) { return "long"; }
    static String numeric(Integer value) { return "Integer"; }
    static String numeric(Object value) { return "Object"; }

    static String reference(String value) { return "String"; }
    static String reference(CharSequence value) { return "CharSequence"; }
    static String reference(Object value) { return "Object"; }

    static <T> List<T> singleton(T element) {
        return List.of(element);
    }

    static <T> T identity(T element) {
        return element;
    }

    public static void main(String[] args) {
        var diamond = new ArrayList<>();
        diamond.add("java");
        diamond.add(42);
        System.out.println("diamondContents=" + diamond);
        System.out.println("diamondOverload=" + classify(diamond));

        var explicitRight = new ArrayList<String>();
        explicitRight.add("java");
        System.out.println("explicitRightOverload=" + classify(explicitRight));

        List<String> typedLeft = new ArrayList<>();
        typedLeft.add("java");
        System.out.println("typedLeftOverload=" + classify(typedLeft));

        var evidenceInCtor = new ArrayList<>(List.of("java"));
        System.out.println("ctorEvidenceOverload=" + classify(evidenceInCtor));

        var noTargetEmpty = Collections.emptyList();
        System.out.println("noTargetEmptyOverload=" + classify(noTargetEmpty));

        List<String> targetEmpty = Collections.emptyList();
        System.out.println("targetEmptyOverload=" + classify(targetEmpty));

        var explicitWitness = Collections.<String>emptyList();
        System.out.println("witnessEmptyOverload=" + classify(explicitWitness));

        var genericFromArg = singleton("hello");
        System.out.println("genericArgumentOverload=" + classify(genericFromArg));

        var primitive = 1;
        var boxed = Integer.valueOf(1);
        var wide = 1L;
        var objectNumber = (Object) Integer.valueOf(1);
        System.out.println("numericPrimitive=" + numeric(primitive));
        System.out.println("numericBoxed=" + numeric(boxed));
        System.out.println("numericWide=" + numeric(wide));
        System.out.println("numericObject=" + numeric(objectNumber));

        var asString = identity("hello");
        var asSequence = (CharSequence) "hello";
        var asObject = (Object) "hello";
        System.out.println("refString=" + reference(asString));
        System.out.println("refSequence=" + reference(asSequence));
        System.out.println("refObject=" + reference(asObject));
    }
}
```

Chạy bằng một JDK hiện đại còn hỗ trợ target Java 10:

```bash
javac --release 10 -Xlint:all -encoding UTF-8 VarDiamondGenericOverloadDemo.java
java VarDiamondGenericOverloadDemo
```

**Stdout chính xác đã được kiểm chứng:**

```text
diamondContents=[java, 42]
diamondOverload=Object
explicitRightOverload=List<String>
typedLeftOverload=List<String>
ctorEvidenceOverload=List<String>
noTargetEmptyOverload=Object
targetEmptyOverload=List<String>
witnessEmptyOverload=List<String>
genericArgumentOverload=List<String>
numericPrimitive=int
numericBoxed=Integer
numericWide=long
numericObject=Object
refString=String
refSequence=CharSequence
refObject=Object
```

Lệnh `javac --release 10 -Xlint:all` đã chạy thành công không có cảnh báo generics cho class này, và `java` xuất đúng 16 dòng trên.

### Giải thích từng nhóm kết quả

**Nhóm diamond:** `diamondContents=[java, 42]` và `diamondOverload=Object` xác nhận biến là `ArrayList<Object>`. Nếu nó là `ArrayList<String>`, việc `add(42)` đã bị compiler từ chối.

**Nhóm generic có kiểu rõ:** `explicitRightOverload` và `typedLeftOverload` gọi overload `List<String>` vì `String` được cung cấp ở vế phải hoặc vế trái. `ctorEvidenceOverload` làm vậy nhờ constructor argument `List.of("java")`.

**Nhóm generic factory:** `noTargetEmptyOverload=Object` vì `Collections.emptyList()` không có target type cụ thể. `targetEmptyOverload` dùng vế trái `List<String>`, còn `witnessEmptyOverload` dùng explicit type witness. `singleton("hello")` tự có thông tin từ argument.

**Nhóm numeric:** các biến có static types `int`, `Integer`, `long`, `Object` tương ứng, nên chọn các overloads exact match.

**Nhóm reference:** `identity("hello")` suy ra String, còn casts sang `CharSequence` và `Object` quyết định overload tương ứng, dù object runtime đều là String.

**Không suy rằng static type `List<Object>` chỉ là cảnh báo IDE.** Nó có hệ quả thật đối với type checking và overload resolution.

## 10. Overload với int, long, Integer và Object

Trong class chính có:

```java
static String numeric(int value) { return "int"; }
static String numeric(long value) { return "long"; }
static String numeric(Integer value) { return "Integer"; }
static String numeric(Object value) { return "Object"; }
```

Phân biệt:

| Khởi tạo | Static type | Lời gọi chọn |
| --- | --- | --- |
| `var x = 1;` | `int` | `numeric(int)` |
| `var x = 1L;` | `long` | `numeric(long)` |
| `var x = Integer.valueOf(1);` | `Integer` | `numeric(Integer)` |
| `var x = (Object) Integer.valueOf(1);` | `Object` | `numeric(Object)` |

`var` **không tự boxing int thành Integer** khi initializer là literal int. Tương tự, cast một Integer thành Object làm static type của biến là Object cho overload resolution.

Theo **JLS §15.12.2**, việc xác định applicability của overload diễn ra qua các giai đoạn: strict invocation (không cần boxing/unboxing/variable arity), loose invocation (cho phép boxing/unboxing), rồi variable-arity invocation nếu các giai đoạn trước không tìm được phương thức áp dụng. Nếu có nhiều ứng viên phù hợp, compiler tìm phương thức cụ thể nhất theo những quy tắc của ngôn ngữ.

**Không coi** “Java luôn chọn Integer trước long” hoặc “số parameter ít hơn sẽ thắng” là quy tắc tổng quát. Kết quả phụ thuộc bộ overload thực tế và các kiểu tĩnh của đối số.

## 11. Generic type erasure không có nghĩa static generic checking biến mất

Java generics dùng **type erasure**. Ví dụ hai biến:

```java
var a = new ArrayList<>();
var b = new ArrayList<String>();
```

đều có runtime class `java.util.ArrayList`. Khi gọi `a.getClass()` hoặc `b.getClass()`, bạn không nhận được một class runtime riêng tên `ArrayList<Object>` hoặc `ArrayList<String>`.

Nhưng compiler vẫn dùng **parameterized types** để kiểm tra an toàn:

- `a` là `ArrayList<Object>`.
- `b` là `ArrayList<String>`.
- `a` không thể đưa vào một lời gọi đòi `List<String>`.
- `b` có thể.

Vì vậy phải phân biệt:

1. **Compile-time generic checking**: kiểm soát type arguments, subtype compatibility và overload applicability.
2. **Runtime erasure**: phần lớn thông tin type arguments không tạo class runtime riêng.

Đừng dựa vào `getClass()` để kiểm tra suy luận generic. Hãy dùng compiler hoặc những lời gọi được type checker xác nhận.

## 12. Bài thử compiler lỗi: thiếu generic type information

Ví dụ **cố tình lỗi**, tách file riêng khỏi chương trình chính.

**File InvalidDiamond.java:**

```java
import java.util.*;
class InvalidDiamond {
    static void onlyStrings(List<String> xs) {}
    void test() {
        var xs = new ArrayList<>();
        onlyStrings(xs); // compile error
    }
}
```

Biên dịch:

```bash
javac --release 10 InvalidDiamond.java
```

**Kết quả:** compiler từ chối truyền `ArrayList<Object>` vào `List<String>`. Phép thử trên JDK hiện đại dùng `-XDrawDiagnostics` cho mã chẩn đoán nhóm `compiler.err.cant.apply.symbol` và exit code 1.

**Sửa:** `List<String> xs = new ArrayList<>();` hoặc `var xs = new ArrayList<String>();`.

### Generic method thiếu target type

**File InvalidEmpty.java:**

```java
import java.util.*;
class InvalidEmpty {
    void test() {
        var xs = Collections.emptyList();
        List<String> expected = xs; // compile error
    }
}
```

Lệnh:

```bash
javac --release 10 InvalidEmpty.java
```

**Kết quả:** `xs` có kiểu `List<Object>`, không gán được cho `List<String>`. Phép thử trả exit code 1, diagnostic nhóm `compiler.err.prob.found.req`.

**Sửa:** `List<String> xs = Collections.emptyList();` hoặc `var xs = Collections.<String>emptyList();`.

**Không dùng unchecked casts hoặc raw types để che lỗi này.**

## 13. Bài thử compiler lỗi: null, lambda và field

Các ví dụ sau cũng là **negative compile tests**, không đặt chung với chương trình chạy chính.

**InvalidNull.java:**

```java
class InvalidNull {
    void test() {
        var value = null; // không suy ra local variable type
    }
}
```

**InvalidLambda.java:**

```java
class InvalidLambda {
    void test() {
        var f = () -> 42; // lambda cần functional interface target type
    }
}
```

**InvalidField.java:**

```java
class InvalidField {
    private var state = 1; // var không hợp lệ cho field
}
```

Biên dịch từng file:

```bash
javac --release 10 InvalidNull.java
javac --release 10 InvalidLambda.java
javac --release 10 InvalidField.java
```

Các ví dụ đã được kiểm thử, **cả ba trả exit code 1**. Các nhóm mã diagnostic:

| File | Nhóm lỗi đã quan sát |
| --- | --- |
| InvalidNull.java | `compiler.err.cant.infer.local.var.type` |
| InvalidLambda.java | `compiler.err.cant.infer.local.var.type` |
| InvalidField.java | `compiler.err.restricted.type.not.allowed.here` |

Để sửa:

```java
String value = null;
java.util.function.Supplier<Integer> f = () -> 42;
```

Field phải có kiểu tường minh, ví dụ `private int state = 1;`. Nếu thật sự muốn khai báo local `var value = (String) null;`, cast cung cấp type nhưng thường kém rõ ràng hơn `String value = null;`.

**Đừng nhầm với Java 11**: cú pháp `(var x) -> ...` cho lambda parameters không phải giải pháp để gán lambda chưa có target type vào `var`.

## 14. Bài thử compiler lỗi: erasure làm trùng chữ ký overload

Hai phương thức sau **không thể** cùng tồn tại trong một class:

**InvalidOverloadsByGeneric.java:**

```java
import java.util.*;
class InvalidOverloadsByGeneric {
    void handle(List<String> a) {}
    void handle(List<Integer> a) {} // name clash, same erasure
}
```

Biên dịch:

```bash
javac --release 10 InvalidOverloadsByGeneric.java
```

**Kết quả:** compiler trả exit code 1, diagnostic nhóm `compiler.err.name.clash.same.erasure`.

Nguyên nhân: cả hai parameter types có erasure là `List`, dẫn tới hai methods cùng tên/cùng parameter erasure. **Đây không phải lỗi của var** ở caller.

Nếu hai method thật sự làm hai công việc khác nhau, đặt tên khác nhau theo nghiệp vụ. Nếu hành vi giống nhau, một generic method có thể hợp lý:

```java
static <T> int count(List<T> values) {
    return values.size();
}
```

Một method `count` generic đủ phục vụ `List<String>` và `List<Integer>` mà không tạo overload trùng nhau.

## 15. Bài thử compiler lỗi: gọi overload với null bị mơ hồ

Có thể khai báo hai overloads:

```java
static String choose(String value) { return "String"; }
static String choose(Integer value) { return "Integer"; }
```

Nhưng lời gọi `choose(null)` có thể không có một overload cụ thể nhất, vì `String` và `Integer` không thuộc quan hệ subtype với nhau.

**InvalidNullOverload.java:**

```java
class InvalidNullOverload {
    static String choose(String x) { return "String"; }
    static String choose(Integer x) { return "Integer"; }
    void test() {
        choose(null); // ambiguous overload
    }
}
```

Biên dịch:

```bash
javac --release 10 InvalidNullOverload.java
```

**Kết quả đã kiểm chứng:** exit code 1, diagnostic nhóm `compiler.err.ref.ambiguous`.

Nếu mục đích thật sự là gọi một overload cụ thể, kiểu tham số có thể được xác định rõ bằng cast hoặc biến tường minh:

```java
choose((String) null);  // choose(String)
choose((Integer) null); // choose(Integer)
```

Ví dụ chỉ nhằm giải thích overload resolution. Truyền null vào method vẫn có thể gây NPE trong implementation; **không mặc nhiên coi null là đầu vào hợp lệ**.

`var x = null` không sửa được lỗi ambiguity vì tự nó không biên dịch.

## 16. Refactor: một thay đổi nhỏ có thể gây regression âm thầm

Giả sử API có:

```java
static String process(List<String> values) { return "string-data"; }
static String process(Object values) { return "generic-data"; }
```

**Trước refactor:**

```java
List<String> names = new ArrayList<>();
String route = process(names); // "string-data"
```

**Sau một refactor thiếu kiểm tra:**

```java
var names = new ArrayList<>();
String route = process(names); // "generic-data"
```

Điều đáng lo không phải chương trình lỗi compile. Nó **vẫn compile**, nhưng nhánh overload đã thay đổi. Unit test có thể bắt được sai khác mà compile check không bắt.

### Hai refactor có chủ đích

Giữ interface type:

```java
List<String> names = new ArrayList<>();
```

Hoặc giữ generic type argument trong initializer:

```java
var names = new ArrayList<String>();
```

Lựa chọn nào phù hợp tùy API design. Nếu muốn static type trừu tượng `List<String>` để tránh gắn với implementation, nên giữ khai báo kiểu tường minh.

### Checklist code review khi chuyển sang var

- Có diamond `<>` ở initializer mà không còn target type không?
- Generic method invocation có thiếu arguments để suy element type không?
- Mọi thao tác `add` có phù hợp với generic type compiler vừa suy không?
- Có overloads nhận `List<String>`, `List<?>` hoặc `Object` không?
- Có overload giữa primitive và wrapper không?
- Có chỗ đang cast sang Object làm mất static type cụ thể không?
- Có generic erasure clash trong API định thêm không?
- Cần viết regression test nào để xác nhận nhánh được chọn?
- Có chỗ nào nên ưu tiên interface type rõ thay vì rút gọn cú pháp không?

## 17. Phân biệt các cơ chế suy luận để tránh ngộ nhận

| Cơ chế | Nó quyết định gì? | Dữ liệu chính |
| --- | --- | --- |
| **Local-variable type inference** | Static type của biến local dùng `var` | Initializer |
| **Diamond generic inference** | Type arguments khi tạo generic class | Target type, constructor arguments, constraints |
| **Generic method inference** | Type arguments cho generic method invocation | Method arguments, target context, bounds |
| **Overload resolution** | Chữ ký method được gọi | Static types, applicability, specificity |
| **Overriding dispatch** | Implementation của instance method được override | Runtime receiver type khi cần dynamic dispatch |
| **Type erasure** | Runtime representation của generic types | Erasure theo JLS |

Các cơ chế này liên quan nhưng **không thay thế nhau**. Một statement như `var xs = new ArrayList<>();` có thể đồng thời dùng local-variable type inference và diamond inference; một lời gọi `classify(xs)` sau đó mới dùng overload resolution.

### Vì sao var với generic method không luôn rơi về Object?

Vì đôi khi initializer có đủ thông tin từ arguments:

```java
var values = List.of("A", "B"); // List<String>
```

Trong khi factory không có arguments:

```java
var values = List.of(); // List<Object> trong ngữ cảnh này
```

Nếu type inference cần target type mà code không cung cấp, bạn phải bổ sung type witness hoặc khai báo kiểu rõ ràng.

### Vì sao compiler không dự đoán từ tên biến?

Biến tên `stringList` hay `customers` là lời gợi ý cho con người, không phải type constraint trong Java Language Specification. Compiler không biến `var stringList = new ArrayList<>();` thành `ArrayList<String>` dựa trên tên.

## 18. Hướng dẫn luyện tập từng bước

**Bước 1 — dự đoán mà không chạy.** Với mỗi dòng trong bảng ở mục 8, ghi static type và overload bạn nghĩ sẽ chọn.

**Bước 2 — biên dịch chương trình chính.** Dùng `javac --release 10 -Xlint:all`; chương trình phải compile không có unchecked/raw warnings.

**Bước 3 — so stdout.** Kiểm tra đủ 16 dòng, đặc biệt `diamondOverload=Object` và `noTargetEmptyOverload=Object`.

**Bước 4 — đổi một khai báo.** Trong bản copy của bài lab, đổi `var diamond = new ArrayList<>();` thành `var diamond = new ArrayList<String>();`. Lúc này lệnh `diamond.add(42)` phải bị compiler từ chối; đó là minh chứng kiểu phần tử đã được khóa chặt.

**Bước 5 — thử generic witness.** Đổi factory `Collections.emptyList()` thành `Collections.<String>emptyList()`; overload phải chuyển từ Object sang List<String>.

**Bước 6 — thử target type.** Giữ `List<String> targetEmpty = Collections.emptyList();` để thấy vế trái cung cấp thông tin String.

**Bước 7 — thử overload numeric.** Thay `Integer.valueOf(1)` thành `1` trong initializer của boxed variable, rồi quan sát overload thay đổi.

**Bước 8 — chạy negative compile tests riêng.** Mỗi file ở mục 12–15 phải lỗi compile theo lý do đã giải thích.

**Bước 9 — rút kết luận.** Viết thành một câu: “static type của var đến từ initializer; generic target typing khác nhau; overload được chọn theo static type”.

**Bước 10 — áp dụng vào code review.** Khi IDE đề xuất “replace explicit type with var”, kiểm tra generic arguments và overloads trước khi chấp nhận hàng loạt.

## 19. Hai lỗi logic cần phân biệt khi làm bài

### Lỗi compile-time rõ ràng

```java
var xs = new ArrayList<>();
acceptStrings(xs); // method đòi List<String>
```

Compiler phát hiện kiểu không phù hợp. Cách sửa là khôi phục type information.

### Lỗi đổi overload nhưng vẫn compile

```java
var xs = new ArrayList<>();
classify(xs); // overload Object hợp lệ
```

Compiler không có lý do báo lỗi: chương trình đã xác định một overload hợp lệ. Nhưng nếu ý định nghiệp vụ là xử lý List<String>, đây là lỗi **thiết kế/refactor**, không phải lỗi type checker.

**Đây là lý do kiểm thử hành vi quan trọng ngang với việc biên dịch thành công.**

## 20. Những anti-pattern cần tránh

**Sai 1.** “`var a = new ArrayList<>()` sẽ thành `ArrayList<String>` vì các lệnh add sau đó đều là String.” Không: kiểu được chốt tại initializer.

**Sai 2.** “Diamond `<>` giống raw constructor `new ArrayList()`.” Không: diamond tham gia generic inference; raw types bỏ kiểm tra generic ở mức cần thiết.

**Sai 3.** “`ArrayList<Object>` truyền vào `List<String>` được vì String extends Object.” Không: generic invariance.

**Sai 4.** “`var xs = Collections.emptyList()` sẽ nhìn vào method nhận xs ở dòng sau để suy String.” Không: suy luận local var không hồi cứu như vậy.

**Sai 5.** “Vì Java có type erasure, compile-time generic types không có ý nghĩa.” Không: compiler vẫn kiểm tra parameterized types.

**Sai 6.** “Có thể overload `handle(List<String>)` và `handle(List<Integer>)`.” Không: same erasure gây name clash.

**Sai 7.** “Lời gọi overload nhìn runtime class của argument.” Không: overload là compile-time selection.

**Sai 8.** “`var n = 1` mặc định suy thành Integer.” Không: initializer là primitive int.

**Sai 9.** “`var n = Integer.valueOf(1)` mặc định suy thành int.” Không: initializer có reference type Integer.

**Sai 10.** “`var f = () -> 42` suy ra Supplier<Integer>.” Không: lambda cần target functional interface type.

**Sai 11.** “`var x = null` suy ra Object.” Không: compiler từ chối null-only initializer.

**Sai 12.** “Có thể viết `private var state` trong class.” Không: var local inference không áp dụng cho fields.

**Sai 13.** “Một overload nhận Object luôn thắng List<String> khi runtime là ArrayList.” Không: static parameterized type mới là điều quyết định.

**Sai 14.** “Có thể sửa lỗi generic bằng unchecked cast mà không có rủi ro.” Không: cast có thể che sai kiểu và đẩy lỗi về runtime.

**Sai 15.** “Nếu refactor với var vẫn compile là hành vi không đổi.” Không: overload có thể thay đổi và chỉ được phát hiện qua test.

**Sai 16.** “Càng viết nhiều var thì code càng rõ.” Không: đôi khi `List<String>` hoặc interface type tường minh là tài liệu có giá trị về contract.

**Sai 17.** “Java 11 var lambda parameters đồng nghĩa var là keyword kiểu dynamic.” Không: hai ngữ cảnh cú pháp đều có kiểm tra kiểu tĩnh.

**Sai 18.** “Có thể xác định ArrayList<String> bằng `getClass()`.” Không: runtime class là ArrayList cho các parameterizations.

**Sai 19.** “`List.of()` và `new ArrayList<>()` có tính mutable giống nhau.” Không: `List.of()` unmodifiable, còn ArrayList mutable.

**Sai 20.** “Chỉ cần học var, không cần biết target typing và overload resolution.” Không: ba cơ chế tương tác trực tiếp trong bài này.

## 21. Checklist trước khi đưa code var vào production

- [ ] Biết static type compiler suy ra cho từng local `var`.
- [ ] Không dựa vào biến/đối số được sử dụng **sau** declaration để suy luận ngược.
- [ ] Kiểm tra `new ArrayList<>()` khi không có target type.
- [ ] Khi cần `List<String>`, đã khai báo type arguments rõ ràng.
- [ ] Không nhầm `<>` với raw generic usage.
- [ ] Không dùng unchecked cast để che sai generic type.
- [ ] Có type witness khi dùng generic factory không có đối số mà cần type cụ thể.
- [ ] Có unit tests cho overload nhạy cảm với static type.
- [ ] Biết Java chọn method overload ở compile time.
- [ ] Không nhầm overload với override runtime dispatch.
- [ ] Đã kiểm tra primitive vs boxed wrapper inference.
- [ ] Không dùng `var` cho field, method return type, null-only hoặc lambda-only initializer.
- [ ] Không overload chỉ bằng generic arguments dẫn tới same erasure.
- [ ] Khi có null, kiểm tra overload ambiguity và API null contract.
- [ ] Dùng compiler warnings và negative compile tests khi học tình huống mới.
- [ ] Review xem kiểu interface tường minh có dễ hiểu hơn var không.
- [ ] Đảm bảo `List.of` unmodifiable và caller không mutate ngoài hợp đồng.
- [ ] Chạy cùng toolchain/JDK feature mục tiêu trong CI.
- [ ] Không dựa vào class runtime để thay thế compile-time generics.
- [ ] Không mang raw/unchecked legacy techniques vào code mới.

## 22. Câu hỏi tự kiểm tra và đáp án

**1.** `var names = new ArrayList<>()` có kiểu gì nếu không có ràng buộc khác? — **`ArrayList<Object>`**.

**2.** `List<String> names = new ArrayList<>()` khác điểm nào? — Vế trái có target type String, giữ kiểu `List<String>`.

**3.** `var names = new ArrayList<String>()` suy ra kiểu nào? — `ArrayList<String>`.

**4.** Vì sao hai lời gọi `add("A")` và `add("B")` không làm kiểu `ArrayList<Object>` đổi sang String? — Kiểu được chốt từ initializer, không suy từ những statement về sau.

**5.** `var names = new ArrayList<>(List.of("A"))` có kiểu nào trong ví dụ? — `ArrayList<String>` nhờ constructor argument.

**6.** `var xs = Collections.emptyList()` suy ra gì? — `List<Object>` trong ngữ cảnh này.

**7.** Dùng `var` nhưng muốn `List<String>` từ emptyList thì viết sao? — `var xs = Collections.<String>emptyList();`.

**8.** `var xs = singleton("hello")` có kiểu gì? — `List<String>`.

**9.** Khi truyền `ArrayList<Object>` vào hai overloads nhận List<String> và Object, chọn overload nào? — `Object`.

**10.** Khi truyền `ArrayList<String>` vào hai overloads đó, chọn overload nào? — `List<String>`.

**11.** `var n = 1` chọn overload int hay Integer nếu cả hai tồn tại? — `int`.

**12.** `var n = Integer.valueOf(1)` chọn overload nào? — `Integer`.

**13.** Cast một String thành Object rồi lưu trong var, compiler chọn overload String hay Object? — `Object`.

**14.** Overload dựa trên static type hay runtime class? — Static type; overriding là một cơ chế khác.

**15.** Có thể có hai overloads chỉ khác List<String> và List<Integer> không? — Không; same erasure.

**16.** `var x = null` có hợp lệ không? — Không, thiếu kiểu suy luận.

**17.** `var fn = () -> 42` có hợp lệ không? — Không, lambda cần target functional interface.

**18.** Dùng var cho class field có được không? — Không.

**19.** Vì sao `getClass()` không xác nhận generic element type? — Type erasure không tạo runtime class riêng cho các parameterizations.

**20.** Nếu refactor sang var vẫn compile, có cần regression test không? — Có, vì overload được chọn có thể đổi dù compile vẫn pass.

## 23. Nguồn chính thức và kiến thức hiện hành

1. [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286): cú pháp và phạm vi local-variable type inference Java 10.
2. [OpenJDK — Local Variable Type Inference FAQ](https://openjdk.org/projects/amber/guides/lvti-faq): Java vẫn static typing, inference dựa vào initializer.
3. [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): rủi ro var kết hợp diamond, generic methods và cách viết rõ ý định.
4. [Oracle Java SE 25 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/25/language/local-variable-type-inference.html): var vẫn có mặt ở JDK mới.
5. [Java Language Specification 25 — §14.4 Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): luật về khai báo biến cục bộ.
6. [Java Language Specification 25 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): applicability, overload resolution và most-specific.
7. [Java Language Specification 25 — §18 Type Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html): generic method inference và ràng buộc.
8. [Java Language Specification 25 — §4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6): vì sao chỉ khác generic type arguments không đủ overload.
9. [dev.java — Type Inference](https://dev.java/learn/generics/type-inference/): diamond, generic constructor/method type inference, target types.
10. [Java SE 25 API — Collections.emptyList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#emptyList()): generic empty-list factory.
11. [Java SE 25 API — List.of](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#of()): generic factories và unmodifiable collections.
12. [OpenJDK — JEP 323: Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): Java 11, không nhầm với Java 10 var declaration.

**Kết luận:** `var` chỉ suy luận **static type từ initializer**. Khi kết hợp `var` với diamond `<>` hoặc generic factory không có đủ type evidence, compiler có thể suy type argument rộng thành `Object`. Điều đó tác động cả generic assignability và **overload resolution**. Hãy dùng target type hoặc explicit type arguments khi quan trọng, tránh raw/unchecked casts và kiểm tra regression behavior mỗi khi rút gọn các khai báo trong code có overloads.
