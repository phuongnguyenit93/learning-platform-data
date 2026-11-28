# Functional interface và annotation @FunctionalInterface

Trong Java 27, **functional interface** là một interface biểu diễn một hợp đồng hành vi có thể được triển khai bằng **lambda expression** hoặc **method reference**. Thay vì buộc mã gọi tạo một lớp chỉ để định nghĩa một thao tác nhỏ như lọc, biến đổi, kiểm tra hay xử lý sự kiện, API có thể nhận một giá trị mang hành vi đó.

Ví dụ, phương thức lọc một danh sách chỉ cần biết cách kiểm tra từng phần tử:

```java
import java.util.List;
import java.util.function.Predicate;

List<String> languages = List.of("Java", "Go", "Kotlin");
Predicate<String> longerThanThree = s -> s.length() > 3;

List<String> selected = languages.stream()
        .filter(longerThanThree)
        .toList();

System.out.println(selected); // [Java, Kotlin]
```

`Predicate<String>` là một functional interface có một thao tác cốt lõi là `boolean test(String value)`. Lambda `s -> s.length() > 3` cung cấp phần triển khai hành vi đó.

Bài học thuộc chương **Lambda và interface hàm** của module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung dựa trên các quy tắc vẫn áp dụng trong Java SE 27, tập trung vào định nghĩa functional interface, vai trò của annotation `@FunctionalInterface`, việc dùng lambda/method reference và cách thiết kế API an toàn. Không cần bật preview để dùng những tính năng này.

## 1. Functional interface là gì?

Theo Java Language Specification (JLS) 9.8, functional interface là một interface **không được khai báo `sealed`** và có **một phương thức trừu tượng về mặt hợp đồng chức năng**, sau khi áp dụng các quy tắc dành cho những phương thức `public` của `Object` và các phương thức kế thừa có chữ ký tương đương.

Một ví dụ tối giản:

```java
@FunctionalInterface
interface TextRule {
    boolean test(String value);
}
```

Đây là một **Single Abstract Method interface (SAM)**. Trong Java, phương thức không có body trong một interface thông thường được coi là `public abstract` nếu không có khai báo đặc biệt khác. Vì vậy, `TextRule` mô tả một thao tác:

```text
Input: String
         |
         v
    test(String)
         |
         v
Output: boolean
```

Có thể triển khai hợp đồng đó bằng lambda:

```java
TextRule nonBlank = text -> text != null && !text.isBlank();

System.out.println(nonBlank.test("Java")); // true
System.out.println(nonBlank.test("   "));  // false
```

Điểm quan trọng là **functional interface vẫn là một interface Java bình thường**. Nó có thể được triển khai bằng class, bằng lambda hoặc bằng method reference phù hợp. Lambda không khai báo thêm phương thức mới; nó cung cấp cách triển khai phương thức chức năng mà interface yêu cầu.

## 2. Quy tắc đếm phương thức trừu tượng: không chỉ đếm dòng code

Cách nói “functional interface có đúng một abstract method” là quy tắc ghi nhớ hữu ích, nhưng phải hiểu đúng phương thức nào được tính và cách xử lý kế thừa.

| Loại thành viên | Có tính là phương thức trừu tượng chức năng? | Ghi chú |
| --- | --- | --- |
| Một phương thức `abstract` không thuộc nhóm phương thức công khai của `Object` | **Có** | Ví dụ `boolean test(T value)` |
| Phương thức `default` có body | Không | Cung cấp hành vi dùng chung cho các implementation |
| Phương thức `static` trong interface | Không | Gọi qua tên interface, không phải contract instance |
| Phương thức `private` trong interface | Không | Có body, làm helper nội bộ cho interface |
| `boolean equals(Object)` tương ứng với public method của `Object` | Không | Không làm tăng số SAM |
| Hai abstract methods kế thừa có chữ ký tương đương và return type tương thích | Có thể chỉ tính thành một hợp đồng | Phải thỏa quy tắc subsignature và return-type-substitutability |
| Abstract method mới, khác chữ ký và không tương đương | Có | Thường làm interface không còn functional |

### 2.1. `default`, `static` và `private` không phá SAM

```java
import java.util.Objects;

@FunctionalInterface
interface MessageRule {
    boolean test(String text); // Một SAM

    default boolean testTrimmed(String text) {
        return test(normalize(text));
    }

    static MessageRule minLength(int length) {
        if (length < 0) {
            throw new IllegalArgumentException("Negative length");
        }
        return text -> text != null && text.length() >= length;
    }

    private static String normalize(String text) {
        return Objects.requireNonNull(text, "text").strip();
    }
}
```

`MessageRule` vẫn là functional interface dù có bốn method được khai báo. Chỉ `test` là abstract instance method cần implementation; `default` có body, `static` có body và `private static` cũng có body.

Sử dụng:

```java
MessageRule rule = MessageRule.minLength(3);
System.out.println(rule.testTrimmed("  Java  ")); // true
System.out.println(rule.testTrimmed(" Go "));     // false
```

Điều kiện đáng nhớ: `private` interface methods phải có implementation, không thể là abstract method public dành cho mã gọi triển khai. Tính năng private interface methods và default methods đều đã ổn định trong Java hiện đại; chúng không biến interface thành class.

### 2.2. Phương thức `Object` công khai không được tính

Ví dụ này vẫn hợp lệ:

```java
@FunctionalInterface
interface Matcher {
    boolean matches(String text);

    boolean equals(Object other);
}

Matcher containsJava = text -> text.contains("Java");
```

`equals(Object)` có chữ ký khớp public instance method của `Object` nên không được tính như một hành vi chức năng thứ hai. Tương tự, các khai báo tương ứng `hashCode()` hoặc `toString()` không làm tăng số SAM.

Ngược lại, các method không công khai của `Object`, chẳng hạn `clone()`, **không** thuộc ngoại lệ này. Nếu một interface công khai thêm `Object clone()` làm abstract method bên cạnh `test()`, interface đó không còn là functional interface.

### 2.3. Kế thừa hai khai báo nhưng chỉ có một hành vi

Hai superinterfaces có thể cùng mô tả một phương thức:

```java
interface TaskA {
    void execute();
}

interface TaskB {
    void execute();
}

@FunctionalInterface
interface CombinedTask extends TaskA, TaskB {
}

CombinedTask task = () -> System.out.println("done");
task.execute(); // done
```

Mặc dù `CombinedTask` kế thừa hai khai báo `execute()`, chúng có cùng chữ ký và diễn đạt một phương thức cần triển khai. Với trường hợp chữ ký không trùng hoàn toàn, JLS còn xét **subsignature** và kiểu trả về có thể thay thế cho nhau (*return-type-substitutability*).

Ví dụ kiểu trả về hiệp biến:

```java
interface GeneralSource {
    CharSequence read();
}

interface StringSource {
    String read();
}

@FunctionalInterface
interface UnifiedSource extends GeneralSource, StringSource {
}

UnifiedSource source = () -> "Java 27";
String text = source.read();
```

`String` là subtype của `CharSequence`, nên khai báo trả về `String` phù hợp với cả hai hợp đồng. Nhưng nếu hai method kế thừa có kiểu trả về không tương thích, interface có thể bị lỗi biên dịch hoặc không thỏa quy tắc functional interface. Đừng chỉ đếm số dòng có từ khóa `abstract`.

## 3. Interface nào **không** phải functional interface?

### 3.1. Không có SAM

```java
interface Marker {
    // Không có phương thức trừu tượng chức năng
}
```

`Marker` có thể là marker interface thông thường, nhưng không phải một functional interface. Gắn `@FunctionalInterface` vào nó sẽ gây lỗi biên dịch.

Khai báo chỉ có `boolean equals(Object value);` cũng không có SAM vì phương thức đó thuộc nhóm public methods của `Object` và không được tính.

### 3.2. Có hai phương thức abstract độc lập

```java
interface Operation {
    void start();
    void stop();
}
```

`start()` và `stop()` khác chữ ký, nên không thể triển khai toàn bộ `Operation` bằng một lambda. Annotation `@FunctionalInterface` không hợp lệ với interface như vậy.

### 3.3. Khai báo `sealed`

Trong JLS Java SE 27, một interface **được khai báo `sealed` không phải functional interface**, ngay cả khi chỉ có một abstract method:

```java
sealed interface RestrictedAction permits SaveAction {
    void execute();
}

final class SaveAction implements RestrictedAction {
    @Override
    public void execute() {
        System.out.println("saved");
    }
}
```

`RestrictedAction` dùng cơ chế hạn chế các kiểu triển khai trực tiếp. Không được đặt `@FunctionalInterface` trên interface `sealed` này, cũng không thể dùng lambda làm instance của nó. Nếu cần nhận lambda, hãy sử dụng một functional interface không `sealed` để mô tả callback, rồi đưa callback đó vào mô hình phân cấp nếu cần.

## 4. Annotation `@FunctionalInterface` có vai trò gì?

`java.lang.FunctionalInterface` là annotation được cung cấp sẵn trong `java.lang`. Nó tuyên bố **ý định thiết kế**: interface này phải giữ một hợp đồng chức năng hợp lệ.

```java
@FunctionalInterface
public interface PriceRule {
    boolean allowed(long priceCents);
}
```

Compiler kiểm tra interface có đáp ứng định nghĩa functional interface không. Nếu sau này ai đó thêm một abstract method độc lập:

```java
@FunctionalInterface
interface PriceRule {
    boolean allowed(long priceCents);
    // String description(); // Nếu bỏ comment, lỗi biên dịch
}
```

Việc kiểm tra xảy ra **khi biên dịch**, giúp phát hiện sớm thay đổi phá hợp đồng SAM mà mã gọi đang sử dụng.

### 4.1. Annotation không phải điều kiện để lambda hoạt động

```java
interface Adder {
    int add(int left, int right);
}

Adder adder = (left, right) -> Math.addExact(left, right);
System.out.println(adder.add(2, 3)); // 5
```

`Adder` vẫn là functional interface dù không ghi `@FunctionalInterface`. Ngược lại, annotation **không thể ép** một interface có hai abstract methods độc lập thành functional interface.

**Khuyến nghị:** dùng `@FunctionalInterface` cho interface do ứng dụng hoặc thư viện tự thiết kế và thực sự có ý định làm SAM công khai. Nó vừa truyền đạt mục đích cho người đọc vừa buộc compiler bảo vệ cấu trúc hợp đồng.

### 4.2. Phạm vi và thời gian tồn tại của annotation

Trong Java SE 27, `@FunctionalInterface` được khai báo với các meta-annotations `@Target(TYPE)`, `@Retention(RUNTIME)` và `@Documented`.

- Có thể đặt nó trên **khai báo interface hợp lệ**, không phải trên một method, class thường hay bản thân lambda.
- Thông tin annotation có thể được nhìn thấy bằng reflection tại runtime vì retention là `RUNTIME`.
- **Ý nghĩa chính** vẫn là kiểm tra hợp lệ ở compile time. Nó không khiến JVM tự chọn một method khác, không thay đổi quyền truy cập, và không bật một cơ chế thực thi đặc biệt khi gọi lambda.

Không cần tự kiểm tra annotation bằng reflection để quyết định một interface có dùng được với lambda hay không. Việc đó là trách nhiệm của type system/compiler theo quy tắc JLS.

## 5. SAM và target typing của lambda

Lambda không tự mang một class hoặc functional interface cố định chỉ dựa vào cú pháp. Java xác định **target type** từ ngữ cảnh và kiểm tra body của lambda với **function type** tương ứng của SAM.

Ví dụ:

```java
import java.util.function.*;

Predicate<String> nonEmpty = text -> !text.isEmpty();
Function<String, Integer> length = text -> text.length();
Consumer<String> printer = text -> System.out.println(text);
Supplier<String> greeting = () -> "Xin chào";
Runnable job = () -> System.out.println("Running");
```

Cùng một cú pháp lambda tổng quát nhưng ý nghĩa phụ thuộc vào kiểu đích:

| Target type | SAM | Dạng lambda phù hợp |
| --- | --- | --- |
| `Predicate<String>` | `boolean test(String)` | `text -> !text.isBlank()` |
| `Function<String, Integer>` | `Integer apply(String)` | `text -> text.length()` |
| `Consumer<String>` | `void accept(String)` | `text -> System.out.println(text)` |
| `Supplier<String>` | `String get()` | `() -> "hello"` |
| `Runnable` | `void run()` | `() -> doWork()` |

Kiểu tham số và kiểu kết quả của lambda phải phù hợp với SAM (bao gồm các quy tắc tương thích kiểu, boxing/unboxing và checked exceptions).

### 5.1. Lambda cần target type phù hợp

Các ngữ cảnh thường tạo target type:

```java
// Ngữ cảnh gán
Predicate<String> present = s -> s != null;

// Ngữ cảnh đối số phương thức
List<String> values = List.of("Java", "Go", "Kotlin");
List<String> result = values.stream()
        .filter(s -> s.length() > 2)
        .toList();

// Ngữ cảnh ép kiểu
Object action = (Runnable) () -> System.out.println("Run");
```

Không thể viết:

```java
// var action = () -> System.out.println("Run"); // Lỗi biên dịch
```

`var` không tự cung cấp đủ target type cho một lambda đứng riêng. Cách dùng hợp lệ là khai báo target interface trước:

```java
Runnable action = () -> System.out.println("Run");
var copy = action; // Hợp lệ: kiểu của expression action đã biết
```

### 5.2. Khớp số lượng tham số, kiểu trả về và body

```java
@FunctionalInterface
interface Difference {
    long between(long left, long right);
}

Difference difference = (left, right) -> left - right;
System.out.println(difference.between(9, 4)); // 5
```

Lambda dành cho `Difference` phải có **hai tham số** và trả về một giá trị tương thích với `long`. Một lambda không có tham số hoặc chỉ có một tham số không phù hợp.

Với block body, cần `return` trên đường thực thi tạo kết quả:

```java
Difference checked = (left, right) -> {
    long result = Math.subtractExact(left, right);
    return result;
};
```

Với `void` SAM, lambda có thể gồm statements không trả kết quả:

```java
Consumer<String> log = text -> {
    String cleaned = text.strip();
    System.out.println(cleaned);
};
```

Lambda không thực thi body ngay khi tạo; body chỉ chạy khi method của functional interface được gọi (trực tiếp hay gián tiếp bởi API).

## 6. Method reference và constructor reference cũng dùng SAM

Ngoài lambda, Java hỗ trợ cú pháp `::` để chỉ tới một method hoặc constructor phù hợp:

```java
import java.util.ArrayList;
import java.util.function.*;

Function<String, Integer> length = String::length;
Consumer<String> log = System.out::println;
Supplier<ArrayList<String>> create = ArrayList::new;

System.out.println(length.apply("Java")); // 4
log.accept("hello");                     // hello
ArrayList<String> list = create.get();   // Một ArrayList mới
```

Ba hình thức trong ví dụ:

1. `String::length`: tham chiếu tới instance method của một đối tượng sẽ được truyền vào tại lời gọi `Function.apply`.
2. `System.out::println`: tham chiếu tới method trên một đối tượng nhận đã xác định.
3. `ArrayList::new`: constructor reference, dùng làm nguồn tạo object.

Method reference được kiểm tra tương thích với **target functional interface**, không phải chỉ dựa vào tên method. Khi method bị overload, compiler phải chọn overload thích hợp từ target type và quy tắc suy luận kiểu.

Khi phần triển khai chỉ chuyển tiếp nguyên một method có sẵn, `::` thường ngắn gọn hơn lambda; khi cần điều kiện, nhiều bước hoặc log xử lý lỗi, lambda thường rõ ràng hơn.

## 7. Những functional interfaces chuẩn nên biết trong Java 27

Trước khi tự tạo interface mới, hãy kiểm tra những kiểu chuẩn phù hợp trong `java.util.function` và các package liên quan.

| Interface | SAM chính | Trường hợp dùng |
| --- | --- | --- |
| `Runnable` | `void run()` | Hành động không nhận tham số, không trả kết quả |
| `Callable<V>` | `V call() throws Exception` | Tác vụ trả kết quả, cho phép checked exception |
| `Supplier<T>` | `T get()` | Cung cấp/lười tạo giá trị |
| `Consumer<T>` | `void accept(T)` | Nhận và xử lý giá trị |
| `BiConsumer<T,U>` | `void accept(T,U)` | Xử lý hai giá trị |
| `Predicate<T>` | `boolean test(T)` | Kiểm tra điều kiện |
| `BiPredicate<T,U>` | `boolean test(T,U)` | Kiểm tra hai giá trị |
| `Function<T,R>` | `R apply(T)` | Biến đổi `T` thành `R` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Biến đổi hai đối số thành kết quả |
| `UnaryOperator<T>` | `T apply(T)` | Biến đổi kiểu `T` thành chính `T` |
| `BinaryOperator<T>` | `T apply(T,T)` | Kết hợp hai giá trị cùng kiểu |
| `Comparator<T>` | `int compare(T,T)` | Định nghĩa thứ tự sắp xếp |

`Runnable` ở `java.lang`; `Callable` ở `java.util.concurrent`; `Comparator` ở `java.util`; các interface `Supplier`/`Consumer`/`Predicate`/`Function` thuộc `java.util.function`.

Ví dụ dùng API chuẩn:

```java
import java.util.List;
import java.util.function.*;

Predicate<String> nonBlank = text -> !text.isBlank();
Function<String, String> normalize = String::strip;
UnaryOperator<String> uppercase = String::toUpperCase;
BinaryOperator<Integer> max = Integer::max;

List<String> result = List.of(" Java ", " ", " Go ")
        .stream()
        .map(normalize)
        .filter(nonBlank)
        .map(uppercase)
        .toList();

System.out.println(result);    // [JAVA, GO]
System.out.println(max.apply(3, 8)); // 8
```

### 7.1. Các dạng chuyên biệt cho primitive

Với dữ liệu primitive và các tác vụ tính toán lớn, hãy cân nhắc những functional interfaces chuyên biệt như `IntPredicate`, `IntConsumer`, `IntSupplier`, `IntUnaryOperator`, `ToIntFunction<T>`, `LongUnaryOperator` hoặc `DoubleUnaryOperator`.

```java
import java.util.function.IntPredicate;
import java.util.function.IntUnaryOperator;

IntPredicate even = n -> n % 2 == 0;
IntUnaryOperator twice = n -> Math.multiplyExact(n, 2);

System.out.println(even.test(8));        // true
System.out.println(twice.applyAsInt(7)); // 14
```

Những kiểu này tránh phải biểu diễn mọi phép tính primitive bằng đối tượng wrapper `Integer`/`Long`/`Double` và có thể giảm boxing/unboxing không cần thiết. Đừng tự định nghĩa `@FunctionalInterface` giống hệt một kiểu chuẩn khi không cần hợp đồng nghiệp vụ riêng.

## 8. Khi nào nên tạo functional interface riêng?

Tạo kiểu riêng khi **tên và hợp đồng nghiệp vụ** quan trọng hơn việc chỉ mô tả hình dạng input/output. Một interface tên `EligibilityRule` có thể truyền đạt yêu cầu tốt hơn `Predicate<Customer>` nếu codebase cần một abstraction với tài liệu, phương thức kết hợp và quy ước lỗi riêng.

Ví dụ một quy tắc xác thực chuỗi có khả năng kết hợp:

```java
import java.util.Objects;

@FunctionalInterface
interface TextRule {
    boolean test(String value);

    default TextRule and(TextRule other) {
        Objects.requireNonNull(other, "other");
        return value -> test(value) && other.test(value);
    }

    static TextRule minimumLength(int minLength) {
        if (minLength < 0) {
            throw new IllegalArgumentException("Negative minimum length");
        }
        return value -> value != null && value.length() >= minLength;
    }
}
```

Sử dụng:

```java
TextRule nonBlank = s -> s != null && !s.isBlank();
TextRule longEnough = TextRule.minimumLength(3);
TextRule valid = nonBlank.and(longEnough);

System.out.println(valid.test("Java")); // true
System.out.println(valid.test("Go"));   // false
System.out.println(valid.test(null));   // false
```

Vì `and` dùng toán tử `&&`, quy tắc thứ hai chỉ được kiểm tra khi quy tắc thứ nhất trả `true`. Điều này có thể hữu ích cho kiểm tra tốn chi phí, nhưng API nên mô tả rõ thứ tự và việc **short-circuit** nếu điều đó ảnh hưởng tới kết quả hoặc side effects.

Khi định nghĩa functional interface riêng, nên xác định rõ:

- Ý nghĩa tên method và giá trị trả về: `true` có nghĩa “hợp lệ”, “được phép” hay “khớp”?
- Chính sách `null`: từ chối bằng `false` hay ném exception?
- Checked exceptions có được phép hay không?
- Hành vi gọi lại nhiều lần có cần idempotent/thread-safe không?
- Default methods có duy trì đúng ngữ nghĩa của SAM ban đầu không?

## 9. Generic functional interfaces và kiểu phương thức chức năng

Functional interface có thể được parameterized bằng generics:

```java
@FunctionalInterface
interface Converter<T, R> {
    R convert(T input);
}

Converter<String, Integer> length = String::length;
Converter<Integer, String> render = Object::toString;

System.out.println(length.convert("Java")); // 4
System.out.println(render.convert(27));      // 27
```

Kiểu `Converter<String, Integer>` có function type tương ứng `(String) -> Integer`. Kiểu `Converter<Integer, String>` lại có function type `(Integer) -> String`. Generic type parameters ở **cấp interface** được thay bởi type arguments tại nơi sử dụng.

### 9.1. Generic SAM và generic abstract method là hai chuyện khác nhau

Ví dụ khai báo sau thỏa tiêu chí về **một abstract method**:

```java
@FunctionalInterface
interface GenericIdentity {
    <T> T identity(T value);
}
```

Tuy nhiên, một lambda thông thường **không** thể dùng làm implementation cho function type có chính các **type parameters của phương thức SAM**; JLS 15.27.3 yêu cầu function type của lambda không có type parameters. Một class triển khai thông thường có thể cài đặt generic abstract method đó.

Nếu mục tiêu chỉ là chuyển đổi một kiểu `T` đã biết ở call site, thiết kế với type parameter của interface thường dễ dùng cho lambda hơn:

```java
@FunctionalInterface
interface Identity<T> {
    T identity(T value);
}

Identity<String> identity = value -> value;
```

Đây là khác biệt giữa **functional interface declaration** và việc một **functional interface type cụ thể** có thể làm target của một lambda hay không.

### 9.2. Wildcards giúp nhận callback linh hoạt

Ví dụ, API lọc danh sách có thể chấp nhận predicate dùng một supertype của `T`:

```java
import java.util.List;
import java.util.function.Predicate;

static <T> List<T> select(
        List<T> values, Predicate<? super T> rule) {
    return values.stream().filter(rule).toList();
}

Predicate<CharSequence> hasText = s -> !s.isEmpty();
List<String> result = select(List.of("A", "BC"), hasText);
```

`Predicate<? super T>` phù hợp vì predicate **nhận** các giá trị `T`. Trong các API chuyển đổi, mẫu `Function<? super T, ? extends R>` thể hiện cả chiều nhận dữ liệu lẫn chiều tạo kết quả.

Tuy nhiên, không nên biến mọi API thành một tập wildcard khó đọc. Nếu một callback chỉ nhận và trả cùng kiểu, hoặc nhiều tham số phải gắn với nhau, hãy dùng named type parameter để diễn đạt ràng buộc đó rõ ràng.

## 10. Checked exceptions và hợp đồng của SAM

Phương thức chức năng có thể khai báo `throws` clause. Điều này ảnh hưởng trực tiếp tới checked exceptions mà body lambda hoặc method reference được phép phát sinh.

Ví dụ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

@FunctionalInterface
interface PathReader {
    String read(Path path) throws IOException;
}

PathReader reader = Files::readString;
```

`Files.readString(Path)` có thể ném `IOException`; vì `PathReader.read` khai báo `throws IOException`, method reference này tương thích.

Ngược lại, `Function<Path, String>` có SAM `apply` **không** khai báo checked exception:

```java
// Function<Path, String> reader = Files::readString;
// Lỗi biên dịch: checked IOException không được khai báo bởi Function.apply
```

Có thể xử lý checked exception bên trong lambda, hoặc dùng một functional interface có `throws` phù hợp. Không nên tùy tiện bắt exception rồi trả `null` hoặc bỏ qua lỗi, bởi điều đó che khuất sự cố I/O và có thể làm sai hợp đồng.

Với tác vụ gọi `Callable<V>`, SAM `V call() throws Exception` cho phép checked exception. Nhưng `Callable` có hợp đồng rộng hơn và thường gắn với tác vụ có kết quả; không phải lúc nào nó cũng là thay thế tốt cho một interface mang ngữ nghĩa nghiệp vụ cụ thể.

## 11. Lambda capture: biến cục bộ phải final hoặc effectively final

Lambda có thể tham chiếu tới các local variables trong phạm vi bao quanh. Những biến đó phải là `final` hoặc **effectively final** (được gán theo quy tắc sao cho không bị gán lại sau khi xác định giá trị).

```java
int minimum = 3;
Predicate<String> enough = s -> s.length() >= minimum;

System.out.println(enough.test("Java")); // true

// minimum = 5; // Nếu bỏ comment: lỗi vì minimum không còn effectively final
```

Quy tắc này không có nghĩa mọi object mà lambda giữ tham chiếu đều immutable:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> messages = new ArrayList<>();
Consumer<String> save = value -> messages.add(value);

save.accept("first");
save.accept("second");
System.out.println(messages); // [first, second]
```

Biến `messages` không bị gán lại, nhưng **nội dung list** vẫn bị thay đổi. Điều này tạo ra side effects và yêu cầu xem xét riêng khi callback chạy đồng thời hoặc bị gọi lại nhiều lần.

### 11.1. Lambda không bảo đảm thread safety hay phép gọi đúng một lần

Một API nhận `Runnable`, `Consumer` hay `Predicate` có thể gọi callback một lần, nhiều lần, không gọi, hoặc chạy trên thread khác tùy hợp đồng API. Lambda chỉ là cách cung cấp implementation của method chức năng; nó **không** tự định nghĩa chính sách concurrency hoặc retry.

Nếu callback cập nhật state dùng chung, cần đồng bộ hoặc dùng dữ liệu immutable/phương án thread-safe thích hợp. Với pipeline Stream, ưu tiên các phép biến đổi ít side effects, đặc biệt khi cân nhắc parallel stream.

### 11.2. `this` và danh tính đối tượng lambda

`this` bên trong lambda tham chiếu tới **enclosing instance** theo quy tắc phạm vi từ vựng của Java, không phải một “this” riêng đại diện cho một anonymous class mới. Đây là khác biệt đáng chú ý khi chuyển code sử dụng anonymous class sang lambda.

Ngoài ra, không nên dựa vào tên class sinh ra, `==`, `System.identityHashCode` hoặc object monitor của lambda để xác định ý nghĩa nghiệp vụ. Java không hứa mỗi lần đánh giá lambda sẽ sinh ra một đối tượng mới; chi tiết instance có thể được runtime tái sử dụng.

## 12. Functional interface và method overloading

Nếu có nhiều overload nhận các functional interfaces khác nhau, một lambda có thể thiếu target type đủ rõ hoặc cần compiler xét thêm hình dạng body và kiểu trả về:

```java
import java.util.function.Consumer;
import java.util.function.Function;

static void applyText(Consumer<String> action) {
    action.accept(" Java ");
}

static void applyText(Function<String, String> transform) {
    System.out.println(transform.apply(" Java "));
}
```

Cách truyền có target type rõ ràng:

```java
Function<String, String> trim = String::strip;
applyText(trim);

Consumer<String> print = System.out::println;
applyText(print);
```

Với lambda làm đối số trực tiếp, đừng đoán overload chỉ dựa vào tên method hay cho rằng mọi lambda khớp kiểu đầu vào đều có thể dùng. Khi thông báo compiler chỉ ra overload không rõ ràng, hãy gán lambda cho biến có functional interface cụ thể, dùng một cast phù hợp hoặc thiết kế API có tên method phân biệt hơn.

Chữ ký SAM gồm **số tham số, kiểu tham số, kiểu trả về và `throws` tương thích**. Annotation `@FunctionalInterface` không tham gia vào việc “ưu tiên” overload nào.

## 13. Sai lầm thường gặp

| Nhận định/cách làm | Vì sao chưa đúng | Cách xử lý |
| --- | --- | --- |
| “Có một method trong source nên chắc chắn là functional” | Kế thừa và phương thức của `Object` có quy tắc riêng | Xét toàn bộ abstract methods hữu hiệu theo JLS 9.8 |
| “Có `@FunctionalInterface` mới dùng lambda được” | Annotation không bắt buộc | Dùng annotation để bảo vệ ý định thiết kế |
| “Gắn annotation sẽ biến interface hai SAM thành một SAM” | Compiler báo lỗi | Chỉ giữ một hợp đồng abstract hợp lệ |
| “Có `default` method là không còn functional” | `default` có body, không được tính như SAM | Dùng default method khi cần hành vi dùng chung |
| “`equals(Object)` là một SAM thứ hai” | Public `Object.equals` bị loại khỏi tập đếm | Chỉ xét các abstract methods có ý nghĩa chức năng |
| “`sealed interface` một method vẫn nhận lambda” | JLS 9.8 loại interface khai báo `sealed` | Dùng callback interface không sealed |
| “Lambda luôn tự suy ra kiểu khi viết `var`” | Lambda cần target functional interface | Khai báo `Predicate<T>`, `Runnable`, v.v. |
| “Mọi method reference đều khớp mọi SAM cùng số tham số” | Còn kiểu tham số/kết quả/checked exception | Đọc chữ ký method và target type |
| “Lambda chạy ngay khi gán” | Body chỉ chạy khi SAM được gọi | Phân biệt tạo callback và gọi callback |
| “Lambda luôn tạo object mới” | Runtime có quyền tái sử dụng instance | Không dựa vào identity của lambda |
| “Bắt checked exception rồi bỏ qua cho vừa `Function`” | Che giấu lỗi, phá hợp đồng xử lý | Dùng SAM `throws` hoặc xử lý lỗi rõ ràng |
| “Lambda capture biến local sửa tự do được” | Local captured phải final/effectively final | Giữ giá trị local ổn định; quản lý mutable state riêng |
| “Predicate/Consumer tự thread-safe” | Callback có thể chứa side effects | Tuân thủ hợp đồng gọi và đồng bộ khi cần |
| “Tự tạo interface mới cho mọi lambda” | Trùng lặp API chuẩn, tăng số type không cần thiết | Ưu tiên `java.util.function` nếu đủ diễn đạt |

## 14. Ví dụ chạy được: kết hợp SAM, default, static và method reference

Tạo file `Demo.java` với nội dung sau. Ví dụ sử dụng **một nested functional interface** để code tự chứa, các giá trị đầu vào an toàn và không cần bất kỳ framework bên ngoài nào.

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class Demo {
    @FunctionalInterface
    interface TextRule {
        boolean test(String value);

        default TextRule and(TextRule other) {
            Objects.requireNonNull(other, "other");
            return value -> test(value) && other.test(value);
        }

        static TextRule minimumLength(int length) {
            if (length < 0) {
                throw new IllegalArgumentException("Negative length");
            }
            return value -> value != null && value.length() >= length;
        }

        default boolean testTrimmed(String value) {
            return test(normalize(value));
        }

        private static String normalize(String value) {
            return Objects.requireNonNull(value, "value").strip();
        }
    }

    public static void main(String[] args) {
        TextRule nonBlank =
                value -> value != null && !value.isBlank();
        TextRule longEnough = TextRule.minimumLength(3);
        TextRule valid = nonBlank.and(longEnough);

        List<String> values =
                List.of("Java", " ", "Go", "Kotlin");

        List<String> accepted = values.stream()
                .filter(valid::test)
                .toList();

        System.out.println(accepted); // [Java, Kotlin]
        System.out.println(valid.testTrimmed("  Java  ")); // true
        System.out.println(valid.testTrimmed(" Go "));     // false

        Function<String, Integer> length = String::length;
        System.out.println(length.apply("Java")); // 4
    }
}
```

Biên dịch và chạy bằng JDK 27:

```shell
javac Demo.java
java Demo
```

Điểm cần quan sát:

1. `@FunctionalInterface` được đặt trên `TextRule`; method `test` là SAM duy nhất.
2. `and` và `testTrimmed` là `default methods`; `minimumLength` là `static`; `normalize` là `private static` — chúng không tạo thêm abstract methods.
3. `nonBlank` là lambda triển khai `test`. `valid` là kết quả của một default method trả về lambda mới.
4. `valid::test` là method reference dùng làm `Predicate<? super String>` cho `Stream.filter`.
5. `String::length` là method reference dùng làm `Function<String,Integer>`.
6. `Stream.toList()` trả list không sửa được; ví dụ chỉ in kết quả, không tìm cách thêm phần tử.

## 15. Checklist khi thiết kế functional interface trong ứng dụng

1. **Có thực sự đúng một hợp đồng hành vi trừu tượng không?** Tính cả phương thức kế thừa và loại các public methods của `Object` theo JLS.
2. **Interface có được khai báo `sealed` không?** Nếu có, không dùng nó như functional interface.
3. **`@FunctionalInterface` đã được thêm cho SAM tự thiết kế chưa?** Annotation giúp phát hiện các sửa đổi vô ý phá hợp đồng.
4. **API chuẩn đã có loại phù hợp chưa?** Xem `Predicate`, `Function`, `Supplier`, `Consumer`, `Runnable`, `Callable` và các dạng primitive.
5. **Tên SAM nói đúng ý nghĩa nghiệp vụ chưa?** Ví dụ `isEligible` hay `validate` có thể rõ hơn một `apply` chung chung trong domain API.
6. **Input/output/generics có khớp target type không?** Đặc biệt khi method reference bị overload hoặc sử dụng wildcard.
7. **Checked exceptions có được mô tả rõ trong SAM không?** Đừng cố nhét callback có I/O vào `Function` bằng cách nuốt lỗi.
8. **`null` được xử lý thế nào?** Chọn trả giá trị, ném exception hoặc yêu cầu non-null theo hợp đồng rõ ràng.
9. **Có side effects không?** Nếu có, cần quy định số lần gọi, thứ tự gọi, retry và khả năng chạy đồng thời.
10. **Các default methods có giữ đúng semantics không?** Đặc biệt với `and`, `or`, `negate`, chaining và short-circuit.
11. **Có đang dựa vào identity/class name của lambda không?** Nếu có, hãy thiết kế lại để dựa vào dữ liệu/hợp đồng thay vì chi tiết runtime.
12. **Đã có test cho hành vi cơ bản và trường hợp lỗi chưa?** Tách kiểm thử callback và kiểm thử API gọi callback khi cần.

## 16. Tổng kết

**Functional interface** là cách Java biểu diễn một hợp đồng hành vi có thể sử dụng làm target type cho lambda và method reference. Định nghĩa chính xác hơn việc “đếm đúng một dòng abstract”: cần xét phương thức kế thừa, loại những public methods tương ứng của `Object` và bảo đảm interface **không `sealed`**.

**`@FunctionalInterface`** là annotation khuyến nghị cho những interface cố ý được thiết kế làm SAM. Nó **không bắt buộc** để lambda hoạt động và không thêm semantics runtime cho lambda; giá trị chính là giúp compiler kiểm tra hợp đồng khi code thay đổi.

Trong Java 27, hãy ưu tiên các interface chuẩn như `Predicate`, `Function`, `Consumer` và `Supplier` cho các callback thông dụng. Tạo interface riêng khi cần truyền đạt ý nghĩa nghiệp vụ, quy tắc lỗi hoặc hành vi kết hợp rõ ràng. Một API tốt làm rõ **target type, input/output, exception và side effects**, thay vì chỉ cố viết lambda ngắn nhất.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — JLS 9.8 Functional Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.8) — định nghĩa functional interface, ngoại lệ phương thức `Object`, kế thừa và giới hạn với `sealed`.
- [Java Language Specification, Java SE 27 — JLS 9.9 Function Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.9) — function type và các ràng buộc tham số, kiểu trả về, `throws`.
- [Java Language Specification, Java SE 27 — JLS 9.6.4.9 @FunctionalInterface](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.4.9) — kiểm tra annotation ở compile time.
- [Java Language Specification, Java SE 27 — JLS 15.27 Lambda Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27) — cú pháp, target typing, captured variables và runtime evaluation.
- [Java Language Specification, Java SE 27 — JLS 15.13 Method Reference Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.13) — method/constructor reference.
- [FunctionalInterface (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/FunctionalInterface.html) — `@Target(TYPE)`, `@Retention(RUNTIME)`, `@Documented` và ý nghĩa annotation.
- [Package java.util.function (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/package-summary.html) — `Predicate`, `Function`, `Consumer`, `Supplier` và các kiểu chuyên biệt.
- [Stream (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html) — `filter`, `map` và `toList`.
