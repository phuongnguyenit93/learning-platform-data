# Phương thức generic và lựa chọn phương thức overload trong Java

## 1. Bài toán: Khi có nhiều phương thức cùng tên, Java chọn phương thức nào?

Trong Java, **method overloading** (nạp chồng phương thức) cho phép khai báo nhiều phương thức cùng tên nhưng khác danh sách tham số. **Generic method** là phương thức tự khai báo type parameters như `<T>` và cho phép trình biên dịch suy luận kiểu tại mỗi lời gọi. Hai cơ chế này kết hợp với boxing, primitive widening, varargs, lambda và method references tạo ra những trường hợp lựa chọn overload khó đoán.

Ví dụ:

```java
static String choose(Object value) { return "Object"; }
static String choose(String value) { return "String"; }
```

Với `choose("Java")`, compiler chọn `choose(String)`. Nhưng khi có một generic overload:

```java
static <T> String option(T value) {
    return "generic";
}
static String option(CharSequence value) {
    return "CharSequence";
}
```

thì `option("Java")` trên Java 17 chọn phương thức nhận `CharSequence`, dù generic method có thể suy luận `T = String`.

Bạn cần hiểu ba lớp vấn đề độc lập:

1. **Tính hợp lệ của overload declarations**: hai signatures sau type erasure có xung đột không?
2. **Compile-time overload resolution**: ứng viên nào áp dụng được, tại invocation phase nào, và ai là most-specific?
3. **Runtime behavior**: sau khi compiler đã chọn method signature, instance overriding có thể dispatch theo object runtime, nhưng runtime không tự chọn lại overload chỉ vì object thực thuộc class con.

Bài học dùng Java 17, bao gồm ví dụ chạy được, ví dụ cố ý không biên dịch và cách sửa lỗi `ambiguous`, `name clash` hoặc `inference variable ... has incompatible bounds`.

## 2. Overloading khác overriding

**Overloading** chọn một phương thức dựa trên tên và kiểu tĩnh của danh sách đối số tại compile time.

```java
static String render(Object x) { return "Object"; }
static String render(String x) { return "String"; }

Object text = "Java";
System.out.println(render(text)); // Object
```

Object thật là `String`, nhưng biến `text` có kiểu tĩnh `Object`, nên compiler không chọn overload `(String)`. Nếu dùng pattern matching:

```java
if (text instanceof String s) {
    System.out.println(render(s)); // String
}
```

thì `s` có kiểu tĩnh `String`, dẫn đến lựa chọn khác.

**Overriding** lại là việc subclass cung cấp implementation cho method được kế thừa với signature phù hợp. Sau khi overload đã được resolve, lời gọi instance method có thể được runtime dispatch tới override đúng dựa trên class object. Không đánh đồng hai cơ chế.

### 2.1. Return type không tạo overload độc lập

Hai khai báo chỉ khác kiểu trả về không hợp lệ:

```java
// Cố tình không biên dịch:
// static String load(int id) { return "A"; }
// static Integer load(int id) { return id; }
```

Java không cho cùng tên và cùng danh sách tham số chỉ khác return type. Điều này không phủ nhận việc **target type** có thể ảnh hưởng generic type inference trong một biểu thức; đây là hai quy tắc khác nhau.

### 2.2. Candidate phải nhìn thấy và truy cập được

Compiler chỉ xét các candidate phù hợp với scope/accessibility tại lời gọi. Một overload `private` không truy cập được từ code bên ngoài không thể tự dưng trở thành ứng viên. Khi phân tích API, bắt đầu từ những method thực sự khả dụng trong ngữ cảnh caller.

## 3. Generic method tự khai báo type variable

```java
static <T> T identity(T value) {
    return value;
}
```

Type variable `T` là của **method**, không nhất thiết của class chứa method. Caller:

```java
String s = identity("Java");
Integer n = identity(10);
```

Compiler suy luận `T` từ arguments, bounds và khi phù hợp từ **target type** của biểu thức. Generic inference không đồng nghĩa `T` hiện hữu như một class runtime riêng sau erasure.

Một method có bound:

```java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
```

có thể nhận `Integer` hoặc `Double`, nhưng không thể nhận `String`. Khi generic candidate có bound không thỏa, compiler phải loại candidate đó khỏi tập applicable methods.

### 3.1. `<T>` không phải wildcard `?`

`<T>` liên kết cùng type variable giữa nhiều vị trí:

```java
static <T> T first(List<T> items) {
    return items.get(0);
}
```

Trong khi:

```java
static int size(List<?> items) {
    return items.size();
}
```

không cần liên kết kiểu phần tử với return type nên wildcard là phù hợp.

Overload resolution phải xét generic method theo những ràng buộc kiểu thật; không có quy tắc “method có `<T>` luôn được chọn vì nó linh hoạt hơn”.

## 4. Ba giai đoạn kiểm tra applicability

Để hiểu các lựa chọn tiêu biểu, dùng mô hình ba giai đoạn của Java method invocation:

1. **Strict fixed-arity invocation**: xét những method áp dụng với số tham số cố định mà không cần boxing/unboxing theo loose invocation.
2. **Loose fixed-arity invocation**: nếu giai đoạn đầu không có candidate phù hợp, xem xét thêm các conversion như boxing/unboxing.
3. **Variable-arity invocation**: nếu vẫn chưa tìm được candidate, xét những method varargs theo hình thức số đối số thay đổi.

Trong giai đoạn đầu tiên có phương thức applicable, compiler tiếp tục chọn **most-specific method** theo các quy tắc của Java. Không quay sang giai đoạn sau chỉ vì một candidate ở đó có vẻ tiện hơn.

Chi tiết chính xác còn có generic inference, *pertinence to applicability*, wildcard, functional interface specificity và access rules. Mô hình ba giai đoạn là cách tổ chức suy nghĩ, không phải toàn bộ thuật toán JLS.

## 5. Primitive widening, boxing và generic method

Cho:

```java
static String widen(long x) {
    return "long";
}

static <T> String widen(T value) {
    return "generic";
}
```

Với `widen(7)`, argument `7` là primitive `int`, widening `int -> long` được chấp nhận ở strict phase. Generic method nhận `T` là reference type cần boxing `int -> Integer`, vì vậy overload `(long)` được chọn.

Với `widen(Integer.valueOf(7))`, argument đã là `Integer` reference. Generic method có thể nhận nó mà không cần unboxing, còn overload `(long)` cần unboxing/widening. Trong ví dụ đã kiểm thử, compiler chọn generic overload.

Kết quả:

```text
widen=long,generic
```

**Bài học:** không tồn tại quy tắc “generic method luôn thua non-generic method”. Kiểu tĩnh và invocation phase quyết định kết quả.

### 5.1. Đừng tự giả định wrapper conversions

`int -> long` là primitive widening. `int -> Integer` là boxing. Nhưng không phải mọi chuyển đổi giữa primitive và wrapper đều được compiler tự ghép thành một conversion tùy ý. Khi báo `no suitable method found`, hãy kiểm tra **chính xác conversion được phép** cho mỗi overload.

## 6. Most-specific: generic method so với tham số cụ thể

Xét:

```java
static <T> String option(T value) {
    return "generic:" + value.getClass().getSimpleName();
}

static String option(CharSequence value) {
    return "CharSequence";
}
```

`option("Java")` chọn `(CharSequence)` trong trường hợp này. `option(7)` không thể truyền một `Integer` tới `CharSequence` nên chọn generic.

Output đã kiểm chứng:

```text
option=CharSequence,generic:Integer
```

Compiler không chỉ suy luận `T = String` rồi tuyên bố đó là tham số “gần” nhất. Các quy tắc applicable methods và most-specific với generic/non-generic candidates cần được áp dụng theo JLS.

Một ví dụ khác:

```java
static String choose(Object x) { return "Object"; }
static String choose(String x) { return "String"; }
```

`choose("Java")` chọn `(String)` cụ thể hơn `(Object)`. `choose(7)` chọn `(Object)` sau boxing, vì không có overload `(String)` phù hợp.

### 6.1. Khi nào nên đặt overload cụ thể cạnh generic fallback?

Thường chỉ nên làm khi semantics thực sự khác và caller hiểu được. Generic fallback có thể khiến API khó đọc nếu việc chọn overload đổi theo kiểu tĩnh của biến:

```java
CharSequence text = "Java";
option(text); // CharSequence
```

Nếu muốn xử lý theo kiểu object runtime, overloading không phải polymorphism runtime. Cân nhắc visitor, strategy, pattern matching hoặc instance override đúng mục đích.

## 7. Fixed arity và generic varargs

```java
static String shape(String value) {
    return "fixed";
}

@SafeVarargs
static <T> String shape(T... values) {
    return "varargs:" + values.length;
}
```

Khi gọi `shape("x")`, fixed method `(String)` được chọn. Với `shape("x", "y")`, fixed method không nhận hai arguments, nên generic varargs áp dụng.

Kết quả:

```text
shape=fixed,varargs:2
```

**Nhưng:** varargs method vẫn có thể tham gia fixed-arity invocation khi caller truyền một array phù hợp:

```java
static void send(String... values) {
    System.out.println(values.length);
}

String[] existing = {"A", "B"};
send(existing); // Truyền array có sẵn.
```

Vì vậy, không nên rút gọn luật thành “method có `...` luôn bị bỏ qua nếu tồn tại method không có `...`”. Cần kiểm tra giai đoạn áp dụng và số arguments cụ thể.

### 7.1. Generic varargs và cảnh báo

`T...` là một array parameter ở source; `T` non-reifiable. Nếu body hoặc nơi gọi có nguy cơ heap pollution, `javac` có thể phát cảnh báo. `@SafeVarargs` có thể dùng với những method/constructor đủ điều kiện và an toàn thật sự; annotation không làm mọi generic varargs trở thành reifiable.

Trong ví dụ `shape` ở trên, method tĩnh chỉ đọc độ dài và không làm array escape hoặc ghi sai kiểu, nên có cơ sở dùng `@SafeVarargs`.

## 8. Lambda không có type độc lập khỏi target

Một lambda được kiểm tra theo **target functional interface type**, không tự có một lớp function độc lập trong source Java:

```java
UnaryOperator<String> clean = s -> s.strip();
```

Khi lời gọi bị overload:

```java
target(s -> s.strip());
```

compiler phải kiểm tra **từng candidate method** và target functional interface tương ứng trước khi quyết định overload thích hợp. Nếu hai candidate đều có thể nhận lambda nhưng không có một lựa chọn *most specific*, lời gọi có thể ambiguous. `var clean = s -> s.strip();` không hợp lệ vì initializer không cung cấp target functional interface.

Ở chương này, trọng tâm của phần này là **hệ quả đối với overload resolution**; quy trình target typing đầy đủ thuộc bài trước. Bước tiếp theo so sánh những candidate như `Function` và `UnaryOperator` để xem compiler thực sự chọn gì.

## 9. `Function` và `UnaryOperator` trong overload resolution

`UnaryOperator<T>` kế thừa `Function<T,T>`. Xét:

```java
static String target(Function<String, String> action) {
    return "Function:" + action.apply(" hi ");
}

static String target(UnaryOperator<String> action) {
    return "UnaryOperator:" + action.apply(" hi ");
}
```

Với:

```java
target(s -> s.strip());
```

Java chọn `UnaryOperator<String>` trong ví dụ đã kiểm thử vì quan hệ subtype/specificity áp dụng. Output:

```text
target=UnaryOperator:hi
```

Điều này không có nghĩa một tên functional interface cụ thể luôn được ưu tiên; thay đổi quan hệ kiểu giữa các interfaces hoặc lambda body có thể tạo kết quả khác.

### 9.1. Lambda + generic type inference

```java
static <T> T convert(T input, UnaryOperator<T> action) {
    return action.apply(input);
}
```

Call:

```java
String output = convert(" java ", String::strip);
```

Compiler suy luận `T = String`; method reference có target `UnaryOperator<String>` và kết quả là `"java"`.

Nguyên tắc quan trọng: khi compiler phân tích lambda/method reference trong generic invocation, type variables và expected functional interface types ràng buộc nhau. Lỗi inference đôi khi phát sinh ở lời gọi chứa lambda chứ không ở method thân bên trong.

## 10. `Supplier` và `Callable` có thể tạo ambiguity

`Supplier<String>` có abstract method `String get()`. `Callable<String>` có abstract method `String call() throws Exception`. Cả hai đều không nhận tham số và trả giá trị kiểu String.

```java
static String decide(Supplier<String> s) {
    return "Supplier:" + s.get();
}

static String decide(Callable<String> c) throws Exception {
    return "Callable:" + c.call();
}
```

Lời gọi:

```java
// Cố tình không biên dịch:
decide(() -> "ok");
```

trở nên ambiguous, vì lambda phù hợp cả hai target types, không có most-specific winner theo chữ ký này. Compiler báo:

```text
error: reference to decide is ambiguous
```

Cách sửa:

```java
decide((Supplier<String>) () -> "ok");
```

Hoặc:

```java
Supplier<String> supplier = () -> "ok";
decide(supplier);
```

Hai cách đều chỉ rõ target functional interface. Cách đặt biến có tên thường dễ đọc hơn nếu lambda phức tạp hoặc tái sử dụng nhiều lần.

### 10.1. Không ưu tiên `Supplier` chỉ vì không throws checked exception

Việc `Callable.call()` khai báo `throws Exception` không tạo một luật “ưu tiên Supplier” cho mọi lambda trả `String`. Không dùng checked exception signatures như một mẹo phân giải overload.

### 10.2. Dùng tên phương thức khác nếu kiểm soát API

Hai overload nhận unrelated interfaces nhưng có cùng lambda shape thường tạo API khó sử dụng. Nếu một method có nghĩa "cung cấp giá trị" và method kia có nghĩa "thực thi tác vụ có exception", tên như `supply(...)` và `callChecked(...)` có thể tốt hơn hai overload `decide(...)`.

## 11. `Consumer` và `Function`: statement-expression lambda

Một lambda có body là method invocation có thể vừa **void-compatible**, vừa **value-compatible**, vì method invocation là *statement expression*.

Cho:

```java
static void use(Consumer<String> c) { }
static void use(Function<String,String> f) { }
```

Lời gọi:

```java
// Không biên dịch:
use(s -> s.trim());
```

bị `javac --release 17` báo ambiguous. Dù `trim()` trả `String`, biểu thức method invocation vẫn có thể được dùng như statement bỏ kết quả, nên lambda tương thích với `Consumer<String>` lẫn `Function<String,String>`.

### 11.1. Block lambda giúp chỉ rõ ý định

Muốn `Consumer<String>`:

```java
use(s -> {
    s.trim();
});
```

Body không return value.

Muốn `Function<String,String>`:

```java
use(s -> {
    return s.trim();
});
```

Body return `String`.

Trong chương trình kiểm chứng:

```text
function=Function:abc
consumer=Consumer
```

Khi cần tính dễ hiểu lâu dài, nên tránh định nghĩa hai overload nhận `Consumer` và `Function` với cùng input type nếu chúng thường nhận lambda dạng statement expression.

### 11.2. `-Xlint:overloads` cảnh báo API có rủi ro

Với cặp overload trên, `javac --release 17 -Xlint:all` phát warning:

```text
[overloads] ... is potentially ambiguous with ...
```

Ngay cả khi các lời gọi hiện tại đã được viết bằng block rõ ràng, warning này nói về **khả năng API gây ambiguity ở các call sites khác**. Đây không phải lỗi runtime.

## 12. Method reference cũng cần target type

Method reference không phải một method object có sẵn functional interface cố định:

```java
String::strip
```

nó phải được hiểu theo target như `UnaryOperator<String>`.

Nếu class có overloads:

```java
static <T> T echo(T value) {
    return value;
}

static String echo(String value) {
    return "special:" + value;
}
```

thì:

```java
UnaryOperator<String> stringEcho =
        GenericOverloadDemo::echo;

Function<Integer, Integer> intEcho =
        GenericOverloadDemo::echo;
```

có thể resolve cùng tên `echo` sang các phương thức khác nhau. Với target `UnaryOperator<String>`, overload `(String)` được chọn; với target `Function<Integer,Integer>`, generic method phù hợp.

Output đã kiểm chứng:

```text
reference=special:z,5
```

### 12.1. Method reference cũng có thể ambiguous

Nếu có:

```java
static String text() { return "x"; }
static void execute(Supplier<String> s) { }
static void execute(Callable<String> c) { }
```

thì:

```java
// Khi đặt trong cùng class:
// execute(MyClass::text);
```

có thể ambiguous vì cả hai functional interfaces đều phù hợp với static method không tham số trả `String`. Phải chỉ rõ target:

```java
Supplier<String> textSupplier = MyClass::text;
execute(textSupplier);
```

Hoặc dùng cast thích hợp. Đừng kỳ vọng đổi lambda thành method reference sẽ tự loại ambiguity.

## 13. `null` và reference overload

```java
static String select(String x) { return "String"; }
static String select(Integer x) { return "Integer"; }
```

Lời gọi:

```java
// Không biên dịch:
select(null);
```

có hai ứng viên áp dụng (`String` và `Integer`) mà không có quan hệ subtype để chọn ứng viên duy nhất. `javac` báo:

```text
error: reference to select is ambiguous
```

Muốn chọn overload `(String)`:

```java
select((String) null);
```

Hoặc tạo biến có kiểu tĩnh String:

```java
String value = null;
select(value);
```

Lưu ý việc chọn được overload không bảo đảm body sẽ chấp nhận null. Nếu method dereference giá trị null, chương trình vẫn có thể ném `NullPointerException`.

## 14. Type erasure và `name clash`

Generic method:

```java
static <T> void inspect(List<T> items) { }
```

có method parameter type sau erasure về raw `List`. Nếu trong cùng class bạn thêm:

```java
static void inspect(List<String> items) { }
```

compiler báo:

```text
error: name clash: inspect(List<String>) and
<T>inspect(List<T>) have the same erasure
```

Tương tự:

```java
// Cũng không hợp lệ nếu cùng class:
static void read(List<String> strings) { }
static void read(List<Integer> integers) { }
```

Hai phương thức chỉ khác type arguments `String` và `Integer`, nhưng sau erasure đều có tham số `List`. Java không cho định nghĩa hai overload như vậy.

**Khác biệt:** `ambiguous` thường nói về **lời gọi** mà nhiều overload đã hợp lệ có thể nhận; `name clash` nói về **khai báo** không thể cùng tồn tại.

### 14.1. Cách sửa name clash

Không có cast tại caller nào giải quyết được lỗi declaration. Cân nhắc:

- Một generic method dùng chung.
- Các tên method rõ semantics: `inspectStrings`, `inspectNumbers`.
- Một tham số `Class<T>` hoặc strategy/handler nếu thực sự cần chỉ rõ cách xử lý.
- Tách trách nhiệm sang các concrete classes có generic interface.

Bridge methods do compiler sinh phục vụ overriding sau erasure không cho phép bạn viết hai overload cùng-erasure một cách thủ công.

## 15. Ví dụ Java 17 hoàn chỉnh

Tạo file **`GenericOverloadDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.function.*;

public class GenericOverloadDemo {
    static String choose(Object value) {
        return "Object";
    }

    static String choose(String value) {
        return "String";
    }

    static <T> String option(T value) {
        return "generic:" + value.getClass().getSimpleName();
    }

    static String option(CharSequence value) {
        return "CharSequence";
    }

    static String widen(long value) {
        return "long";
    }

    static <T> String widen(T value) {
        return "generic";
    }

    static String shape(String value) {
        return "fixed";
    }

    @SafeVarargs
    static <T> String shape(T... values) {
        return "varargs:" + values.length;
    }

    static <T> T convert(T input, UnaryOperator<T> action) {
        return action.apply(input);
    }

    static String target(Function<String,String> fn) {
        return "Function:" + fn.apply(" hi ");
    }

    static String target(UnaryOperator<String> fn) {
        return "UnaryOperator:" + fn.apply(" hi ");
    }

    static String task(Runnable action) {
        action.run();
        return "Runnable";
    }

    static String task(Callable<String> action) throws Exception {
        return "Callable:" + action.call();
    }

    static String decide(Supplier<String> source) {
        return "Supplier:" + source.get();
    }

    static String decide(Callable<String> source) throws Exception {
        return "Callable:" + source.call();
    }

    static <T> T echo(T value) {
        return value;
    }

    static String echo(String value) {
        return "special:" + value;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("choose="
                + choose("Java") + "," + choose(7));
        System.out.println("option="
                + option("Java") + "," + option(7));
        System.out.println("widen="
                + widen(7) + "," + widen(Integer.valueOf(7)));
        System.out.println("shape="
                + shape("x") + "," + shape("x", "y"));
        System.out.println("convert="
                + convert(" java ", String::strip));
        System.out.println("target="
                + target(s -> s.strip()));
        System.out.println("task="
                + task(() -> "fromCallable"));
        System.out.println("decision="
                + decide((Supplier<String>) () -> "ok"));
        System.out.println("echo="
                + echo("hello") + "," + echo(42));

        UnaryOperator<String> f1 = GenericOverloadDemo::echo;
        Function<Integer,Integer> f2 = GenericOverloadDemo::echo;
        System.out.println("reference="
                + f1.apply("z") + "," + f2.apply(5));
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:all GenericOverloadDemo.java
java GenericOverloadDemo
```

Chương trình đã biên dịch thành công trên Java 17 không có warning với `-Xlint:all`. Stdout chính xác:

```text
choose=String,Object
option=CharSequence,generic:Integer
widen=long,generic
shape=fixed,varargs:2
convert=java
target=UnaryOperator:hi
task=Callable:fromCallable
decision=Supplier:ok
echo=special:hello,42
reference=special:z,5
```

### 15.1. Cách diễn giải từng nhóm output

`choose`: overload String cụ thể hơn Object; khi argument là primitive `7`, boxing đưa nó thành `Integer` thích hợp với Object.

`option`: một generic fallback và một overload `CharSequence` có cách chọn khác nhau cho String và Integer; tính generic không tự tạo ưu tiên tuyệt đối.

`widen`: primitive widening thắng trong strict phase với `7`, còn `Integer` reference chọn generic khi không cần unboxing.

`shape`: method fixed nhận một String; generic varargs nhận hai String.

`convert`: type inference liên kết `String::strip` với `UnaryOperator<String>` và input String.

`target`: `UnaryOperator<String>` cụ thể hơn `Function<String,String>` trong overload set này.

`task`: lambda trả string literal không phải statement expression void-compatible, nên chỉ phù hợp với `Callable<String>` thay vì `Runnable`.

`decision`: cast lambda sang `Supplier<String>` làm rõ overload cần gọi.

`echo`/`reference`: một tên method có generic và non-generic overload được giải quyết theo kiểu argument hoặc target functional interface.

## 16. Năm ví dụ cố ý không biên dịch

Mỗi đoạn dưới là **một tệp riêng**; không đặt chung với chương trình chạy được.

### 16.1. `AmbiguousNull.java`

```java
class AmbiguousNull {
    static String select(String x) { return "s"; }
    static String select(Integer x) { return "i"; }

    static void check() {
        System.out.println(select(null));
    }
}
```

Lệnh `javac --release 17 AmbiguousNull.java` báo:

```text
error: reference to select is ambiguous
```

Sửa bằng `select((String) null)` hoặc một biến có kiểu tĩnh String nếu nghiệp vụ cho phép null.

### 16.2. `AmbiguousLambda.java`

```java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class AmbiguousLambda {
    static void choose(Supplier<String> s) { }
    static void choose(Callable<String> c) { }

    static void check() {
        choose(() -> "hello");
    }
}
```

Lệnh `javac --release 17 AmbiguousLambda.java` báo:

```text
error: reference to choose is ambiguous
```

Sửa bằng `Supplier<String> s = () -> "hello"; choose(s);` hoặc một cast functional interface phù hợp.

### 16.3. `AmbiguousVoidValue.java`

```java
import java.util.function.Consumer;
import java.util.function.Function;

class AmbiguousVoidValue {
    static void use(Consumer<String> fn) { }
    static void use(Function<String, String> fn) { }

    static void test() {
        use(s -> s.trim());
    }
}
```

Lệnh `javac --release 17 AmbiguousVoidValue.java` báo:

```text
error: reference to use is ambiguous
```

Sửa thành `use(s -> { s.trim(); });` nếu muốn Consumer, hoặc `use(s -> { return s.trim(); });` nếu muốn Function.

### 16.4. `NameClash.java`

```java
import java.util.List;

class NameClash {
    static <T> void inspect(List<T> items) { }
    static void inspect(List<String> items) { }
}
```

Lệnh `javac --release 17 NameClash.java` báo:

```text
error: name clash: inspect(List<String>) and
<T>inspect(List<T>) have the same erasure
```

Đây là lỗi declaration; phải sửa chữ ký hoặc tên method.

### 16.5. `MethodRefAmbiguous.java`

```java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class MethodRefAmbiguous {
    static String text() { return "x"; }
    static void run(Supplier<String> s) { }
    static void run(Callable<String> c) { }

    static void check() {
        run(MethodRefAmbiguous::text);
    }
}
```

Lệnh `javac --release 17 MethodRefAmbiguous.java` báo:

```text
error: reference to run is ambiguous
```

Method reference cũng cần target functional interface rõ ràng; có thể gán nó cho `Supplier<String>` trước khi gọi.

Năm trường hợp trên đã được kiểm tra trực tiếp bằng compiler Java 17, đều trả trạng thái biên dịch khác 0 với diagnostics tương ứng.

## 17. Chương trình giải ambiguity có kết quả rõ ràng

Tạo file **`OverloadDisambiguationProof.java`**:

```java
import java.util.concurrent.Callable;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

class OverloadDisambiguationProof {
    static String select(String x) {
        return "String";
    }

    static String select(Integer x) {
        return "Integer";
    }

    static String call(Supplier<String> f) {
        return "Supplier:" + f.get();
    }

    static String call(Callable<String> f) throws Exception {
        return "Callable:" + f.call();
    }

    static String apply(Consumer<String> f) {
        f.accept(" abc ");
        return "Consumer";
    }

    static String apply(Function<String,String> f) {
        return "Function:" + f.apply(" abc ");
    }

    public static void main(String[] args) throws Exception {
        System.out.println("null=" + select((String) null));
        System.out.println("lambda="
                + call((Supplier<String>) () -> "done"));
        System.out.println("function="
                + apply(s -> { return s.trim(); }));
        System.out.println("consumer="
                + apply(s -> { s.trim(); }));

        Supplier<String> ref = () -> "value";
        System.out.println("typed=" + call(ref));
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:all OverloadDisambiguationProof.java
java OverloadDisambiguationProof
```

Stdout đã xác nhận:

```text
null=String
lambda=Supplier:done
function=Function:abc
consumer=Consumer
typed=Supplier:value
```

Compiler **vẫn phát một warning** `[overloads]` tại khai báo `apply(Function<String,String>)` với tùy chọn `-Xlint:all` vì cặp overload `Consumer`/`Function` tiềm ẩn ambiguity. Điều này chứng minh: việc call sites hiện tại được viết rõ ràng không xóa hết rủi ro về **thiết kế API**.

## 18. Phân biệt lỗi inference và ambiguous overload

Một số lỗi dễ gặp:

| Compiler diagnostic | Ý nghĩa chủ đạo | Cách xử lý |
| --- | --- | --- |
| `reference to ... is ambiguous` | Có nhiều applicable candidates, không có winner duy nhất. | Làm rõ kiểu tĩnh/functional target, thay tên API hoặc bớt overload. |
| `no suitable method found` | Không candidate nào áp dụng cho arguments/conversions/bounds. | Kiểm tra overload signatures và kiểu tĩnh thực tế. |
| `inference variable T has incompatible bounds` | Các ràng buộc lên type variables không giải được đồng thời. | Xem generic bounds, target type và các đối số/lambda. |
| `name clash ... same erasure` | Khai báo overload va chạm sau erasure. | Sửa method declarations, không chỉ cast tại call site. |
| `[overloads] ... potentially ambiguous` | API có overloads nhận functional interfaces khó phân biệt. | Cân nhắc tên phương thức khác hoặc thiết kế kiểu target rõ. |
| `ClassCastException` ở runtime | Giá trị bị dùng/cast thành kiểu runtime không tương thích. | Kiểm tra raw aliases, unchecked casts hoặc dữ liệu từ nguồn ngoài. |

**Phân biệt:** lỗi inference và ambiguous thường được phát hiện khi compile một lời gọi; name clash được phát hiện ngay tại declarations. Không chờ runtime “thử” một overload khác sau khi compiler đã báo ambiguous.

### 18.1. Target type có thể ảnh hưởng generic inference

Ví dụ:

```java
static <T> T empty() {
    return null;
}

String s = empty();
Integer i = empty();
```

Compiler có thể dùng target type của assignment để suy luận kiểu kết quả cho invocation. Với nested generic method calls, constraint từ surrounding expression có thể ảnh hưởng inference.

Điều này **không** có nghĩa bạn được định nghĩa hai methods chỉ khác return type. Target-type inference và luật overload declaration là các cơ chế riêng.

### 18.2. Explicit type witness không phải nút chọn overload tuyệt đối

Java cho phép chỉ rõ type arguments trong một số generic invocations:

```java
String value = GenericOverloadDemo.<String>echo("Java");
```

Nhưng đừng suy rằng cách viết `<String>` luôn buộc compiler chọn một implementation generic bất kể overload set. Applicability/specificity vẫn quyết định theo luật ngôn ngữ. Khi một API overload khó hiểu, giải pháp tốt hơn thường là đổi tên hoặc thiết kế chữ ký minh bạch.

## 19. Checklist xác định overload trong code thực

1. **Ghi chính xác kiểu tĩnh** của mọi đối số, kể cả generic type argument và primitive/reference.
2. **Liệt kê các overload khả dụng** tại nơi gọi, xét access/scope.
3. Với generic methods, xem **type variables, bounds và inference constraints** từ arguments/target.
4. Tìm applicable candidates trong **strict fixed-arity phase**.
5. Nếu không có, xét **loose fixed-arity phase** (boxing/unboxing).
6. Nếu vẫn không có, xét **variable-arity phase** cho varargs.
7. Trong phase đầu tiên thành công, so **most-specific** giữa candidates.
8. Với lambda/method reference, xác định **target functional interface**, descriptor parameters/return, void/value compatibility.
9. Với `null`, xác định reference overloads có quan hệ subtype chọn được winner không.
10. Nếu declarations dùng generic arguments khác nhau, kiểm tra **erasure/name clash**.
11. Nếu ambiguous, làm rõ kiểu bằng biến, cast có chủ đích hoặc thiết kế API mới; không dùng raw type để che lỗi.
12. Biên dịch Java 17 với `-Xlint:all`, kiểm tra stdout/diagnostics trên ví dụ tối thiểu.

Bảng tra nhanh:

| Lời gọi hoặc khai báo | Kết quả |
| --- | --- |
| `choose("x")` với `(Object)` và `(String)` | `(String)` cụ thể hơn. |
| `choose(x)` nếu biến x có kiểu `Object` nhưng runtime String | `(Object)` do compile-time type. |
| `widen(7)` với `(long)` và `<T>(T)` | `(long)` trong ví dụ. |
| `widen(Integer.valueOf(7))` | Generic overload trong ví dụ. |
| `shape("x")` với `(String)` và `<T>(T...)` | Fixed `(String)`. |
| `shape("x","y")` | Generic varargs. |
| `target(s -> s.strip())` với `Function` và `UnaryOperator` | `UnaryOperator`. |
| `decide(() -> "x")` với `Supplier<String>` và `Callable<String>` | Ambiguous. |
| `use(s -> s.trim())` với `Consumer` và `Function` | Ambiguous. |
| `select(null)` với `(String)` và `(Integer)` | Ambiguous. |
| `inspect(List<String>)` và `<T>inspect(List<T>)` | Name clash after erasure. |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao biến `Object x = "Java"` gọi overload `(Object)` thay vì `(String)`?

<details>
<summary>Đáp án</summary>

Overload resolution dùng kiểu tĩnh `Object` của biểu thức tại compile time. Class runtime `String` không khiến Java tự chọn lại overload.

</details>

**Câu 2.** Vì sao `widen(7)` có thể chọn `(long)` thay vì generic `<T>(T)`?

<details>
<summary>Đáp án</summary>

Primitive widening `int -> long` áp dụng ở strict fixed-arity phase; generic candidate cần boxing cho argument primitive và được xét ở phase sau.

</details>

**Câu 3.** `List<String>` và `List<Integer>` có đủ khác nhau để định nghĩa hai overload `(List<String>)`, `(List<Integer>)` trong cùng class không?

<details>
<summary>Đáp án</summary>

Không. Erasure của hai parameterized types đều là raw `List`, gây name clash.

</details>

**Câu 4.** Vì sao `() -> "ok"` có thể ambiguous khi có overloads nhận `Supplier<String>` và `Callable<String>`?

<details>
<summary>Đáp án</summary>

Cả hai functional interfaces đều có abstract method không tham số trả `String`; lambda chưa có target type cụ thể, nên hai ứng viên đều phù hợp mà không có winner duy nhất. Dùng typed variable, cast hoặc tên API khác.

</details>

**Câu 5.** Vì sao `s -> s.trim()` có thể khớp cả Consumer và Function?

<details>
<summary>Đáp án</summary>

`trim()` là method invocation, thuộc nhóm statement expression. Expression lambda có thể vừa void-compatible vừa value-compatible. Dùng block không return cho Consumer, block có return cho Function.

</details>

**Câu 6.** Tại sao `UnaryOperator<String>` có thể thắng `Function<String,String>`?

<details>
<summary>Đáp án</summary>

`UnaryOperator<T>` mở rộng `Function<T,T>`, nên có quan hệ subtype/specificity được Java xét khi hai target types đều phù hợp.

</details>

**Câu 7.** Có thể dùng cast ở caller để sửa `name clash` giữa hai generic overload declarations không?

<details>
<summary>Đáp án</summary>

Không. Name clash là lỗi của các method declarations có cùng erasure. Phải sửa tên/signature hoặc thay thiết kế API.

</details>

**Câu 8.** Method reference `SomeClass::echo` có tự quyết định overload mà không cần target type không?

<details>
<summary>Đáp án</summary>

Không. Method reference dùng target functional interface; overload resolution của method được tham chiếu phụ thuộc kiểu tham số/return mà target yêu cầu.

</details>

## 21. Tổng kết

**Overload resolution diễn ra tại compile time**, với kiểu tĩnh, generic inference, applicable invocation phases và most-specific selection. Lambda/method reference còn cần target functional interface nên có thể khiến API overload trở nên ambiguous, dù từng method riêng lẻ hợp lệ.

Khi gặp lỗi, hãy phân biệt ba loại: `ambiguous` ở lời gọi; `name clash` ở declarations sau erasure; `incompatible bounds` ở generic inference. Không sửa bằng cách tùy tiện bỏ `<T>` hoặc dùng raw type. Dùng rõ kiểu tĩnh, lambda block, biến functional interface có tên, hoặc thiết kế lại chữ ký/naming để API dễ hiểu và type-safe.