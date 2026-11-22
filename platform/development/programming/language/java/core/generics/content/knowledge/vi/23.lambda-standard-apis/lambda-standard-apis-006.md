# Giới hạn dùng lambda cho hợp đồng phương thức tự khai báo generic trong Java

Một **functional interface** của Java là interface có đúng một phương thức trừu tượng theo các quy tắc đếm phương thức của Java (các khai báo tương ứng phương thức `Object`, phương thức `default`, `static` có quy tắc riêng). Lambda biểu diễn hành vi để triển khai **functional descriptor** của một kiểu đích (*target type*). Tuy nhiên, có một giới hạn tinh tế khi phương thức trừu tượng đó **tự khai báo type parameter**:

```java
@FunctionalInterface
interface PolyIdentity {
    <T> T apply(T value);
}
```

Interface trên **vẫn hợp lệ và vẫn là functional interface**, nhưng bạn **không thể** hiện thực trực tiếp phương thức generic `<T> T apply(T)` bằng lambda thông thường:

```java
// KHÔNG BIÊN DỊCH:
PolyIdentity identity = x -> x;
```

Trong Java, **functional descriptor của một lambda không thể là một phương thức tự khai báo type parameter (generic method)** theo cách này. Một lambda không có cú pháp khai báo `<T>` cho chính phương thức mà nó triển khai. `javac` có thể báo: `invalid functional descriptor for lambda expression`, kèm thông tin rằng phương thức đích là generic.

Điều này **khác hoàn toàn** với hai tình huống hợp lệ và rất phổ biến:

1. **Functional interface tự nó generic**, nhưng *single abstract method* không khai báo type parameter riêng, như `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `UnaryOperator<T>`.
2. **Phương thức bên ngoài nhận lambda là generic**, ví dụ `static <T> T transform(T value, UnaryOperator<T> action)`. Compiler suy luận `T` khi gọi, rồi kiểm tra lambda theo một functional descriptor cụ thể.

Ngoài ra, **method reference tới một phương thức generic phù hợp** và **anonymous class tự hiện thực generic method** có thể thực hiện hợp đồng `PolyIdentity`. Vì vậy, giới hạn này thuộc về **biểu thức lambda và cách nó được kiểm tra theo functional descriptor**, không phải lệnh cấm mọi generic method trong functional interface.

## 1. Phân biệt hai vị trí khai báo type parameter

Hãy so sánh hai interface:

```java
// A: T là type parameter của INTERFACE.
@FunctionalInterface
interface Identity<T> {
    T apply(T value);
}

// B: T là type parameter của METHOD apply.
@FunctionalInterface
interface UniversalIdentity {
    <T> T apply(T value);
}
```

Ở A, khi chọn kiểu đích `Identity<String>`, kiểu của phương thức duy nhất là `String apply(String)`. Compiler có thể kiểm tra lambda `s -> s.toUpperCase()` với tham số và kết quả `String`:

```java
Identity<String> upper = s -> s.toUpperCase();
String result = upper.apply("java"); // "JAVA"
```

Ở B, hợp đồng **một đối tượng UniversalIdentity phải chấp nhận mọi cách chọn T trong từng lời gọi**:

```java
UniversalIdentity value = /* một implementation hợp lệ */;
String text = value.apply("An");
Integer number = value.apply(42);
```

Nghĩa vụ của implementation không phải “chọn một `T` khi tạo object”, mà là cung cấp một phương thức generic có thể dùng nhiều kiểu tham chiếu phù hợp trong các lời gọi khác nhau. Java lambda thông thường không thể tự khai báo một phương thức mới mang type parameter `<T>` để thỏa hợp đồng đó.

| Khai báo | Type parameter thuộc về | Đặt lambda làm implementation? |
| --- | --- | --- |
| `interface Identity<T> { T apply(T x); }` với `Identity<String>` | Interface; được chọn ở kiểu đích | Có |
| `interface Mapper<T,R> { R map(T x); }` với `Mapper<String,Integer>` | Interface; hai kiểu được chọn ở kiểu đích | Có |
| `interface Universal { <T> T apply(T x); }` | Chính abstract method; một implementation phải hỗ trợ mọi `T` | Không bằng lambda trực tiếp |
| `static <T> T transform(T x, UnaryOperator<T> f)` | Generic method **nhận** lambda; descriptor của `UnaryOperator<T>` không tự khai báo generic method | Có thể truyền lambda |
| `static <T> T echo(T x)` gán qua `Universal u = ClassName::echo` | Generic method được tham chiếu | Có thể bằng method reference phù hợp |

Không đánh đồng “trong chữ ký có chữ `T`” với “phương thức chức năng tự khai báo `<T>`”. **Dấu `<T>` nằm ở đâu** quyết định rất nhiều.

## 2. Functional interface có generic abstract method vẫn hợp lệ

Interface sau là ví dụ tối thiểu:

```java
@FunctionalInterface
interface Polymorphic {
    <T> T convert(T input);
}
```

Annotation `@FunctionalInterface` được compiler chấp nhận khi interface thỏa định nghĩa functional interface. Tức là quy tắc **đếm một phương thức trừu tượng** và quy tắc **lambda-compatible descriptor** không đồng nhất ở điểm liên quan generic method.

Nếu thử:

```java
// KHÔNG BIÊN DỊCH:
Polymorphic p = input -> input;
```

thì vấn đề **không phải** vì interface có hai abstract methods. Nó có một abstract method, nhưng method đó là **generic method**. Compiler không thể gán lambda vào loại functional descriptor ấy.

Điểm cần giữ chính xác:

- `@FunctionalInterface` kiểm tra hình dạng interface theo quy tắc ngôn ngữ.
- Lambda expression cần một **target functional interface type** có functional descriptor phù hợp với lambda.
- Với đích như `<T> T convert(T)`, không có cách dùng lambda thông thường để khai báo `T` của method và đảm bảo implementation dùng được cho mọi phép thế kiểu.
- Các quy tắc này tồn tại ngay cả khi phần thân dự kiến “chỉ trả input” và trông rất tổng quát.

Không thể sửa bằng cách đổi `input -> input` thành `(Object input) -> input`: lúc đó bạn chỉ mô tả một lời gọi với `Object`, không hiện thực chính xác chữ ký generic `<T> T convert(T)`.

## 3. Vì sao `Function<T,R>` và `UnaryOperator<T>` dùng lambda được?

Xét cách khai báo ý tưởng của API chuẩn:

```java
@FunctionalInterface
interface FunctionLike<T, R> {
    R apply(T value);
}

@FunctionalInterface
interface UnaryLike<T> {
    T apply(T value);
}
```

`T` và `R` thuộc về **interface**, không phải được khai báo lại trên chính abstract method `apply`. Khi target type là `FunctionLike<String,Integer>`, functional descriptor sau khi thay thế type parameters có tham số `String`, trả về `Integer`.

```java
FunctionLike<String, Integer> length = s -> s.length();
System.out.println(length.apply("Java")); // 4
```

Tương tự, các functional interfaces của Java chuẩn:

- `Function<T,R>`: chuyển `T` thành `R`, có thể dùng lambda `x -> ...`.
- `UnaryOperator<T>`: `Function<T,T>`, đầu vào và đầu ra đều kiểu `T`.
- `Predicate<T>`: kiểm tra `T`, trả `boolean`.
- `Consumer<T>`: nhận một `T`, trả `void`.
- `Supplier<T>`: không nhận tham số, trả `T`.
- `BiFunction<T,U,R>`: nhận hai giá trị có kiểu `T` và `U`, trả `R`.

Các interface **generic ở cấp interface** này là những loại đích thường được dùng với lambda. Với Java 17, bạn có thể viết:

```java
java.util.function.Function<String, Integer> length = s -> s.length();
java.util.function.Predicate<String> nonBlank = s -> !s.isBlank();
java.util.function.UnaryOperator<Integer> increment = n -> n + 1;
```

Từng lambda ở đây chỉ phải thỏa kiểu phương thức đã xác định bởi target type của nó. Không cần một lambda duy nhất tự khai báo một generic method có thể gọi với `String` rồi `Integer` như hợp đồng `<T> T apply(T)`.

### Không phải mọi functional interface tự khai báo generic đều bị cấm

Phát biểu “lambda không dùng được với interface generic” là **sai**. Interface `Identity<T>` chính là phản ví dụ. Giới hạn đang nghiên cứu là **generic abstract method descriptor**, không phải sự hiện diện của dấu `<...>` trên interface hoặc trên các kiểu tham số của nó.

## 4. Generic method nhận lambda: hợp lệ vì mỗi lời gọi suy luận kiểu riêng

Một API có thể khai báo type parameter tại **phương thức gọi lambda**, trong khi lambda vẫn có một functional descriptor hợp lệ:

```java
static <T> T transform(
        T value,
        java.util.function.UnaryOperator<T> operation) {
    return operation.apply(value);
}
```

Cách gọi:

```java
String text = transform("hello", s -> s + "!");
Integer count = transform(10, n -> n + 5);
```

Ở lần gọi đầu, compiler có thể suy luận `T = String`; lambda được kiểm tra như `UnaryOperator<String>`. Ở lần gọi thứ hai, nó có thể suy luận `T = Integer`; lambda được kiểm tra như `UnaryOperator<Integer>`.

Điều này **không biến bản thân lambda** thành một method generic `<T> T apply(T)`. Mỗi biểu thức lambda là một implementation theo **một kiểu đích** được xác định trong quá trình type inference của lời gọi.

Ví dụ khác:

```java
static <T, R> R convert(
        T value,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return mapper.apply(value);
}

String result = convert(42, x -> "No." + x); // "No.42"
```

Generic method `convert` tự khai báo `T`, `R`. Type parameters ở **lớp phương thức bao ngoài**, và `Function<? super T, ? extends R>` vẫn có một phương thức `apply` không tự khai báo type parameter. Compiler đủ thông tin để kiểm tra lambda.

### Dấu `<T>` trong method không áp vào lambda theo cách tương tự

Cần phân biệt:

```java
// Hợp lệ:
static <T> void run(T input, java.util.function.Consumer<T> action) {
    action.accept(input);
}
```

với:

```java
// Interface hợp lệ, nhưng không lambda-implementable trực tiếp:
interface UniversalConsumer {
    <T> void accept(T input);
}
```

Với `run`, `T` được suy luận **khi gọi run** và ràng buộc kiểu của callback. Với `UniversalConsumer`, `accept` là generic abstract method của chính đối tượng callback, đòi implementation có tham số kiểu riêng trong mọi lời gọi.

## 5. Dùng method reference trỏ tới generic method

Một điều thú vị: **generic method reference** có thể phù hợp với functional interface có generic abstract method trong những trường hợp được kiểm tra hợp lệ.

```java
@FunctionalInterface
interface PolyIdentity {
    <T> T apply(T value);
}

static <U> U echo(U value) {
    return value;
}

// Đặt trong ngữ cảnh class hợp lệ:
PolyIdentity identity = MyClass::echo;
```

`MyClass::echo` tham chiếu một method **thật sự tự khai báo `<U>`**. Java có cơ chế kiểm tra *method reference* với functional descriptor khác lambda, nên một method reference generic phù hợp có thể đáp ứng hợp đồng mà `x -> x` không đáp ứng.

Sau khi gán:

```java
String text = identity.apply("An");
Integer number = identity.apply(123);
```

Cả hai lời gọi hợp lệ; implementation là một generic method có sẵn, chứ không phải compiler tự “nhân” một lambda thành generic method mới.

**Không phải mọi method reference đều được chấp nhận.** Phương thức được tham chiếu phải có chữ ký, khả năng truy cập, tham số kiểu, kết quả và các ràng buộc phù hợp với functional descriptor. Ví dụ, một method chỉ nhận `String` không tự nhiên hiện thực `<T> T apply(T)` cho mọi `T`.

Một method reference dạng bound tới instance method generic cũng có thể hợp lệ:

```java
class Echoer {
    <T> T echo(T value) {
        return value;
    }
}

PolyIdentity p = new Echoer()::echo;
```

Khác biệt với lambda đến từ **quy tắc riêng của Java cho method references**, không phải từ việc type erasure biến `T` thành `Object` rồi ngầm chấp nhận mọi phép cast.

## 6. Anonymous class: giải pháp trực tiếp khi thực sự cần generic SAM

Nếu logic không có sẵn dưới dạng generic method thích hợp, hãy tạo anonymous class và **khai báo rõ method generic**:

```java
@FunctionalInterface
interface PolyIdentity {
    <T> T apply(T value);
}

PolyIdentity identity = new PolyIdentity() {
    @Override
    public <T> T apply(T value) {
        return value;
    }
};
```

Tại đây, phần thân `apply` được khai báo là một method Java đầy đủ với `<T>`, khác cú pháp lambda. Compiler có thể kiểm tra rằng nó thực sự override generic abstract method `<T> T apply(T)`.

Cách này có thể dài hơn lambda nhưng diễn đạt đúng hợp đồng **đa hình theo từng lời gọi** của method.

Ví dụ nếu muốn giới hạn bound:

```java
@FunctionalInterface
interface NumericIdentity {
    <T extends Number> T apply(T value);
}

NumericIdentity identity = new NumericIdentity() {
    @Override
    public <T extends Number> T apply(T value) {
        return value;
    }
};
```

Lời gọi `identity.apply(42)` hoặc `identity.apply(3.5)` có thể hợp lệ, còn `identity.apply("Java")` không thỏa bound `Number`.

Phần viết anonymous class không làm `T` thành reifiable. Nếu bên trong muốn viết `new T()`, `T.class` hoặc `new T[10]`, các giới hạn khác của generic type variables vẫn tồn tại.

## 7. Chương trình Java 17+ kiểm chứng những trường hợp hợp lệ

Lưu toàn bộ vào file **`GenericLambdaDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.UnaryOperator;

public class GenericLambdaDemo {
    @FunctionalInterface
    interface PolyIdentity {
        <T> T apply(T value);
    }

    @FunctionalInterface
    interface Identity<T> {
        T apply(T value);
    }

    static <T> T echo(T value) {
        return value;
    }

    static <T> T transform(T value, UnaryOperator<T> operation) {
        return operation.apply(value);
    }

    static <T, R> R convert(
            T value, Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }

    static <T> List<T> select(
            List<T> source, Predicate<? super T> test) {
        List<T> result = new ArrayList<>();
        for (T item : source) {
            if (test.test(item)) {
                result.add(item);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        Identity<String> shout =
                s -> s.toUpperCase(Locale.ROOT);
        Identity<Integer> doubleValue = n -> n * 2;

        System.out.println(
                "Lambda String: " + shout.apply("java"));
        System.out.println(
                "Lambda Integer: " + doubleValue.apply(7));

        System.out.println("Generic API String: "
                + transform("hello", s -> s + "!"));
        System.out.println("Generic API Integer: "
                + transform(10, x -> x + 5));

        System.out.println("Generic conversion: "
                + convert(42, x -> "No." + x));

        System.out.println("Filtered: "
                + select(List.of("a", "java", "api"),
                         s -> s.length() > 2));

        // Generic method reference có thể thỏa generic SAM.
        PolyIdentity methodReference = GenericLambdaDemo::echo;
        System.out.println("Reference String: "
                + methodReference.apply("An"));
        System.out.println("Reference Integer: "
                + methodReference.apply(123));

        // Anonymous class trực tiếp khai báo generic method.
        PolyIdentity anonymous = new PolyIdentity() {
            @Override
            public <T> T apply(T value) {
                return value;
            }
        };
        System.out.println("Anonymous Boolean: "
                + anonymous.apply(true));

        int threshold = 3; // Effectively final
        Predicate<String> longWord =
                text -> text.length() > threshold;
        System.out.println("Captured value: "
                + longWord.test("java"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GenericLambdaDemo.java
java GenericLambdaDemo
```

**Standard output chính xác**:

```text
Lambda String: JAVA
Lambda Integer: 14
Generic API String: hello!
Generic API Integer: 15
Generic conversion: No.42
Filtered: [java, api]
Reference String: An
Reference Integer: 123
Anonymous Boolean: true
Captured value: true
```

Giải thích:

1. Hai biến `Identity<String>` và `Identity<Integer>` minh họa interface generic **có lambda hợp lệ** vì `apply(T)` của chúng không tự khai báo `<U>`.
2. `transform`, `convert`, `select` là các **generic methods nhận callback**. Mỗi lần gọi suy luận type arguments rồi kiểm tra lambda theo `UnaryOperator<T>`, `Function<T,R>` hoặc `Predicate<T>`.
3. `GenericLambdaDemo::echo` là method reference đến method generic `<T> T echo(T)`, có thể hiện thực `PolyIdentity` với cả lời gọi `String` và `Integer`.
4. Anonymous class khai báo chính xác `public <T> T apply(T)`; ở ví dụ, Boolean được boxing thành `Boolean` và trả về.
5. Lambda cuối đọc `threshold` từ scope bên ngoài vì biến local đó **effectively final**. Đây là quy tắc capture riêng của lambda, **không** phải việc lambda tự khai báo generic method.

Phần **không biên dịch** `PolyIdentity p = x -> x;` không xuất hiện trong chương trình chạy để tránh làm hỏng bản demo.

## 8. Ví dụ cố ý thất bại và cách đọc compiler diagnostic

Đặt vào file độc lập **`GenericLambdaError.java`** nếu muốn tự kiểm tra lỗi:

```java
public class GenericLambdaError {
    @FunctionalInterface
    interface UniversalIdentity {
        <T> T apply(T value);
    }

    public static void main(String[] args) {
        UniversalIdentity bad = x -> x; // CỐ Ý SAI
        System.out.println(bad.apply("x"));
    }
}
```

Chạy:

```bash
javac GenericLambdaError.java
```

Compiler có thể báo dạng:

```text
incompatible types: invalid functional descriptor for lambda expression
    method <T>(T)T in interface UniversalIdentity is generic
```

Vị trí/dấu câu của thông báo phụ thuộc phiên bản javac, nhưng trọng tâm là **functional descriptor của lambda trỏ tới một generic method**.

Đừng sửa bằng các cách thiếu an toàn:

```java
// KHÔNG phải giải pháp:
// UniversalIdentity p = (Object x) -> (Object) x;
// UniversalIdentity p = x -> (Object) x;
```

Các biểu thức này không khai báo hay thực hiện được hợp đồng `<T> T apply(T)`. Cast sang `Object` không biến một lambda thành polymorphic generic method; compiler cũng không tự tạo overload/bridge cần thiết từ những cast ấy để thỏa interface.

Chọn cách sửa theo **ý nghĩa của API**:

- Nếu một object thật sự phải hỗ trợ nhiều type arguments ở các lần gọi khác nhau: method reference đến generic method phù hợp hoặc anonymous class có method `<T>` rõ ràng.
- Nếu callback chỉ cần một kiểu `T` tại một vị trí dùng: chuyển sang `Identity<T>` hoặc `Function<T,T>` để lambda hoạt động.
- Nếu một thuật toán generic nhận callback ở nhiều lời gọi độc lập: đưa `<T>` lên generic method chứa tham số kiểu `Function`/`UnaryOperator`, thay vì đặt nó trên abstract method của một callback cố định.

## 9. Chuyển generic method trong interface thành generic interface khi phù hợp

Giả sử thiết kế ban đầu là:

```java
@FunctionalInterface
interface UniversalValidator {
    <T> boolean valid(T item);
}
```

Hợp đồng này yêu cầu **cùng một đối tượng validator có thể nhận mọi loại `T` trong mọi lần gọi**. Nếu công việc thực tế chỉ cần kiểm tra `String` ở chỗ này và `Integer` ở chỗ khác, điều đó có thể phức tạp không cần thiết.

Thiết kế thường phù hợp hơn:

```java
@FunctionalInterface
interface Validator<T> {
    boolean valid(T item);
}

Validator<String> notBlank = s -> !s.isBlank();
Validator<Integer> positive = n -> n > 0;
```

Hai instance validator có contract tĩnh rõ ràng. Compiler kiểm tra input, và mỗi lambda có một descriptor không generic.

Dùng interface chuẩn cũng được:

```java
java.util.function.Predicate<String> notBlank = s -> !s.isBlank();
java.util.function.Predicate<Integer> positive = n -> n > 0;
```

**Không phải lúc nào đổi `UniversalValidator` thành `Validator<T>` cũng bảo toàn ý nghĩa.** Trong thiết kế đầu, một implementation phải nhận mọi `T`; trong thiết kế mới, một instance được tham số hóa bởi một `T` xác định. Chỉ refactor khi hợp đồng nghiệp vụ thật sự không cần kiểu đa hình qua các lần gọi cùng object.

## 10. Generic API dùng callback tại từng lần gọi: mẫu thiết kế khuyến nghị

Trong nhiều tình huống, generic method bên ngoài callback là lựa chọn dễ đọc và dễ type-check nhất:

```java
static <T> java.util.List<T> select(
        java.util.List<T> values,
        java.util.function.Predicate<? super T> predicate) {
    java.util.List<T> selected = new java.util.ArrayList<>();
    for (T item : values) {
        if (predicate.test(item)) {
            selected.add(item);
        }
    }
    return selected;
}
```

Với:

```java
java.util.List<String> words =
        select(java.util.List.of("a", "java"), s -> s.length() > 1);

java.util.List<Integer> even =
        select(java.util.List.of(1, 2, 3), n -> n % 2 == 0);
```

`T` của `select` được suy luận riêng cho mỗi lời gọi; lambda bên trong mỗi lời gọi có một target type `Predicate<? super T>` tương ứng. Wildcard `? super T` cho phép chấp nhận các predicate có thể tiêu thụ phần tử kiểu `T` một cách an toàn.

Nếu muốn biến đổi, dùng `Function<? super T, ? extends R>`; nếu muốn hành động không trả kết quả, dùng `Consumer<? super T>`. Đây là cách thiết kế có type inference tốt, tránh tạo một interface mà abstract method của chính nó phải generic chỉ để callback dùng với nhiều kiểu khác nhau tại **các vị trí gọi khác nhau**.

### Generic methods có thể suy luận qua lambda body và target type

Compiler Java thực hiện **type inference** và kiểm tra *poly expressions* theo ngữ cảnh. Ví dụ:

```java
static <T, R> R map(T input, java.util.function.Function<T, R> mapper) {
    return mapper.apply(input);
}

String text = map(42, n -> "number=" + n);
```

Ở đây kiểu `T` được suy luận từ `42`, còn `R` liên quan kiểu kết quả lambda và kiểu đích `String`. Tuy vậy, body lambda không tự khai báo một generic method; nó chỉ được kiểm tra theo descriptor `Function<T,R>` đã được suy luận phù hợp.

Nếu javac không suy luận được kiểu mong muốn, có thể làm rõ kiểu ở target assignment, parameter declaration hoặc thêm type witness ở lời gọi generic method. Không cần — và không thể — “đưa `<T>` vào trước lambda” để biến lambda thành generic method.

## 11. Những giới hạn khác của lambda: liên quan nhưng không đồng nhất

Ngoài generic SAM, Java lambda còn chịu những quy tắc khác:

### 11.1. Lambda cần target type là functional interface phù hợp

```java
// KHÔNG BIÊN DỊCH: không thể gán trực tiếp lambda vào Object.
// Object action = x -> x;

// Hợp lệ:
java.util.function.UnaryOperator<String> action = x -> x;
Object stored = action;
```

Target typing là cơ chế chính của lambda. Bản thân cú pháp `x -> x` không tự cung cấp type parameter hay một function object với mọi type signature có thể tưởng tượng.

### 11.2. Kiểu trả về và tham số phải phù hợp với descriptor

```java
java.util.function.Function<String, Integer> length = s -> s.length();
// java.util.function.Function<String,Integer> invalid = s -> s; // Sai kiểu trả về
```

Đây là giới hạn bình thường do **chữ ký API** đã chọn (`String` sang `Integer`), không phải giới hạn đặc thù của generic abstract method.

### 11.3. Capture biến local cần final hoặc effectively final

```java
int threshold = 3;
java.util.function.Predicate<String> longer =
        text -> text.length() > threshold;

// threshold++; // Nếu bật dòng này, biến không còn effectively final
```

Rule *effectively final* của Java áp dụng khi lambda capture local variable từ scope bao ngoài. Không được nhầm nó với việc generic type parameter có scope riêng.

### 11.4. Checked exceptions cần phù hợp với hợp đồng callback

`Function.apply` chuẩn không khai báo checked exception. Vì vậy lambda truyền vào `Function` không thể ném một checked exception chưa xử lý như `IOException` nếu descriptor không cho phép. Có thể chọn API khác có functional interface khai báo `throws`, hoặc xử lý ngoại lệ trong lambda. Đây là **một giới hạn của descriptor/hợp đồng checked exception**, không đồng nghĩa generic lambda bị cấm.

### 11.5. Overload có thể làm target type của lambda không rõ

Nếu có nhiều overload nhận các functional interface khác nhau mà cùng phù hợp với một lambda, compiler có thể báo *ambiguous method call*. Cần làm rõ đích qua biến có kiểu, cast hợp lệ đến functional interface hoặc đổi thiết kế overload. Đừng coi mọi lỗi lambda đều do abstract method generic.

## 12. Không dùng raw type hoặc unchecked cast để giả lập generic callback

Một giải pháp thiếu an toàn thường xuất phát từ suy nghĩ “nếu compiler không cho lambda gắn vào `<T> T apply(T)`, cứ cast nó qua `Object` hay raw `Function` rồi dùng”.

Vấn đề: một `Function<Object,Object>` có hợp đồng **một kiểu tham số và kết quả Object**, còn `<T> T apply(T)` yêu cầu quan hệ input/output cùng `T` **đối với mọi lần chọn `T`**. Hai hợp đồng này không đồng nhất chỉ vì cùng có erasure liên quan `Object`.

```java
// Cách tiếp cận không nên dùng để "chứng minh" universal contract:
java.util.function.Function<Object, Object> f = input -> input;
```

Dù `f` có thể trả lại input, bản thân nó không cung cấp chữ ký method generic `<T> T apply(T)`. Nếu thêm unchecked casts và raw types để né compiler, bạn có thể chuyển lỗi thành `ClassCastException` ở caller và làm mất hợp đồng kiểu tĩnh.

**Giải pháp đúng** là chọn functional interface thích hợp, hoặc thực hiện generic method rõ ràng bằng anonymous class/method reference. Không dùng `@SuppressWarnings("unchecked")` để thay thế một bằng chứng về tương thích phương thức.

## 13. Khi nào thật sự cần generic abstract method của functional interface?

Nhu cầu thực tế tồn tại khi một object phải cung cấp **hành vi đa hình với mỗi lần gọi**. Ví dụ, một phép identity chung cần giữ kiểu kết quả đúng theo kiểu đầu vào mà không cố định một type argument tại lúc tạo object:

```java
interface PolyIdentity {
    <T> T apply(T value);
}
```

Một implementation có thể nhận cùng lần lượt `String`, `Integer`, `Boolean`, và trả đúng kiểu tương ứng. Method reference `GenericLambdaDemo::echo` đáp ứng khi `echo` là generic method phù hợp.

Nhưng với các phép xử lý **đặc thù cho một kiểu**, ví dụ viết hoa chuỗi hoặc nhân đôi số nguyên, không cần hợp đồng “mọi `T`”:

```java
java.util.function.UnaryOperator<String> upper =
        s -> s.toUpperCase(java.util.Locale.ROOT);

java.util.function.UnaryOperator<Integer> twice =
        n -> n * 2;
```

Nếu bắt chúng phải hiện thực `<T> T apply(T)`, nghĩa vụ phải hoạt động với **bất kỳ `T` nào** sẽ không phù hợp với thuật toán chỉ làm việc với `String` hoặc `Integer`. Thường đây là dấu hiệu **thiết kế interface sai mức tổng quát**, không đơn thuần là thiếu một mẹo cú pháp lambda.

### Bounded generic method không trở thành lambda-compatible

Kể cả khi type parameter có bound:

```java
@FunctionalInterface
interface NumberIdentity {
    <N extends Number> N apply(N value);
}
```

Abstract method vẫn **tự khai báo generic parameter `N`**. Không thể giả định lambda `n -> n` được chấp nhận chỉ vì erasure của `N` là `Number`; giới hạn descriptor vẫn áp dụng.

Có thể dùng anonymous class khai báo `<N extends Number>`, hoặc method reference tới một generic method có bound tương thích. Một giải pháp thay thiết kế khác là `UnaryOperator<Number>`, nhưng nó có hợp đồng **Number → Number**, không bảo toàn chính xác subtype ở mỗi lời gọi như `<N extends Number> N apply(N)`.

## 14. Lỗi thường gặp và lời giải đúng

**Sai lầm 1 — “Interface có `@FunctionalInterface` thì mọi lambda đều dùng được.”** Không. Generic abstract method vẫn có thể là SAM, nhưng không có functional descriptor mà lambda trực tiếp triển khai theo cách này.

**Sai lầm 2 — “Có dấu `<T>` ở đâu cũng cấm lambda.”** Không. `Function<T,R>` và các generic interface chuẩn được dùng với lambda mỗi ngày. Cần xác định `T` thuộc interface hay thuộc chính abstract method.

**Sai lầm 3 — “Một lambda `x -> x` tự động là generic cho mọi kiểu.”** Không. Lambda có target type cụ thể. Nó không khai báo method-level type parameters.

**Sai lầm 4 — “Generic method nhận lambda cũng bị cấm.”** Không. `static <T> T transform(T, UnaryOperator<T>)` là mẫu hợp lệ: `T` được suy luận tại lời gọi, còn descriptor `UnaryOperator<T>` không tự generic.

**Sai lầm 5 — “Method reference và lambda luôn thay thế nhau hoàn toàn.”** Không. Generic method reference có thể hợp lệ với generic SAM khi lambda không hợp lệ, do quy tắc kiểm tra khác nhau.

**Sai lầm 6 — “Dùng anonymous class cũng không được vì interface có generic abstract method.”** Không. Anonymous class khai báo rõ `public <T> T apply(T)` là cách hiện thực hợp lệ.

**Sai lầm 7 — “Erasure của `T` thành `Object` cho phép ép `Function<Object,Object>` thành universal callback.”** Không. Hợp đồng generic về quan hệ kiểu giữa input/output ở từng lời gọi mạnh hơn việc dùng `Object`; cast không thay thế kiểm tra kiểu của compiler.

**Sai lầm 8 — “Lambda nhận `Predicate<? super T>` là một generic method.”** Không. `Predicate` có type parameter ở interface; `test(T)` không tự khai báo generic method. Wildcard là một phần quy tắc tương thích kiểu ở target.

**Sai lầm 9 — “Mọi lỗi biên dịch của lambda đều do generics.”** Không. Scope/capture, overload ambiguity, checked exception, mismatch kiểu trả về hay thiếu functional target type đều có thể là nguyên nhân khác.

## 15. Bài tập tự kiểm tra

**Câu 1.** Interface này có là functional interface không?

```java
interface Universal {
    <T> T apply(T value);
}
```

**Có.** Nó có một abstract method hợp lệ. Nhưng tính functional interface **không đồng nghĩa lambda trực tiếp tương thích** với method descriptor generic đó.

**Câu 2.** `Universal v = x -> x;` có hợp lệ không?

**Không.** `apply` tự khai báo `<T>`. Lambda không thể trực tiếp hiện thực functional descriptor generic đó.

**Câu 3.** `interface Id<T> { T apply(T x); }` và `Id<String> id = x -> x;` có hợp lệ không?

**Có.** `T` thuộc interface; target `Id<String>` có descriptor `String apply(String)`.

**Câu 4.** `static <T> T echo(T x)` có thể được tham chiếu bằng `Universal v = ClassName::echo` không?

**Có**, nếu chữ ký và các điều kiện truy cập/tương thích phù hợp. Đây là method reference tới generic method thật.

**Câu 5.** Phương thức `static <T> T run(T v, UnaryOperator<T> op)` có nhận được `run("a", x -> x + "!")` không?

**Có.** Caller suy luận `T = String`, còn lambda thực hiện `UnaryOperator<String>` theo target type được xác định.

**Câu 6.** Nếu một interface khai báo `<N extends Number> N apply(N n)`, có thể dùng lambda `n -> n` không?

**Không trực tiếp.** Bound không xóa bản chất generic của abstract method. Dùng generic method reference phù hợp hoặc anonymous class với `<N extends Number>`.

**Câu 7.** Tại sao không dùng `Function<Object,Object>` để thay hoàn toàn `<T> T apply(T)`?

Vì `Function<Object,Object>` không bảo đảm compiler biết đầu ra cùng type argument `T` với đầu vào **tại từng lời gọi**; nó có chữ ký `Object apply(Object)`.

**Câu 8.** Cần callback viết hoa `String` và callback nhân đôi `Integer`. Chọn universal generic SAM hay hai `UnaryOperator<...>`?

Thông thường chọn **`UnaryOperator<String>`** và **`UnaryOperator<Integer>`**. Hai hành vi đặc thù không cần và không thỏa hợp đồng phải hỗ trợ mọi `T`.

## 16. Checklist thiết kế API lambda có generics

Trước khi tạo một functional interface hoặc generic callback, hãy kiểm tra:

1. **Abstract method có tự viết `<T>` không?** Nếu có, đừng mặc định lambda trực tiếp tương thích.
2. **`T` thuộc interface hay method?** `interface F<T> { T run(T); }` khác `interface F { <T> T run(T); }`.
3. **Một object phải hỗ trợ nhiều kiểu tại các lần gọi khác nhau không?** Nếu thực sự cần, có thể cần generic method reference hoặc anonymous class.
4. **Hay mỗi callback được dùng với một kiểu ở một vị trí?** Nếu vậy, `Function<T,R>`, `Predicate<T>`, `Consumer<T>` và `UnaryOperator<T>` thường phù hợp hơn.
5. **Type parameter có thể chuyển lên method API bên ngoài không?** Ví dụ `static <T> void process(T input, Consumer<T> consumer)`.
6. **Có thể dùng method reference tới một generic helper đã có không?** Kiểm tra cả bound, tham số, kết quả và overload resolution.
7. **Có cần wildcard PECS?** Sử dụng `? super T` cho consumer, `? extends R` cho producer khi đúng mục tiêu.
8. **Lỗi compiler thuộc loại gì?** Phân biệt generic descriptor không lambda-compatible, lambda body sai kiểu, biến capture không effectively final, checked exceptions và ambiguous overload.
9. **Có đang định dùng raw/cast để lách không?** Dừng lại và soát contract trước khi gây heap pollution hoặc lỗi cast muộn.
10. **Ví dụ đã biên dịch theo đúng Java target chưa?** Chạy `javac` với `--release` phù hợp khi hỗ trợ nhiều phiên bản Java, và kiểm tra cả chương trình hợp lệ lẫn một phản ví dụ bị từ chối riêng.

**Kết luận:** Java hỗ trợ rất tốt **generic interface dùng với lambda** và **generic method nhận lambda**, nhưng một lambda thông thường **không thể trực tiếp triển khai phương thức trừu tượng tự khai báo type parameter** như `<T> T apply(T)`. Interface đó vẫn có thể là functional interface; cách triển khai phù hợp có thể là **generic method reference** hoặc **anonymous class khai báo rõ generic method**. Nếu không thật sự cần một callback đa hình ở mọi lần gọi, thiết kế đơn giản hơn bằng `Function<T,R>`, `UnaryOperator<T>` hoặc một generic API nhận functional interface chuẩn sẽ dễ dùng và an toàn hơn.