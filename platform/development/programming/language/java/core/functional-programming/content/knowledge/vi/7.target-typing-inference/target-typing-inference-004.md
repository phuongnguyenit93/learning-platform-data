# Vì sao var không thể tự suy ra kiểu của lambda đứng riêng

Trong Java, `var` ở **khai báo biến cục bộ** yêu cầu compiler suy ra một kiểu cụ thể từ **biểu thức khởi tạo**. Nhưng lambda như `s -> s.length()` không có kiểu độc lập để compiler đọc ra ngay: nó là **poly expression**, cần **kiểu đích (target type)** là một functional interface. Vì vậy, câu lệnh sau **cố ý không hợp lệ**:

```java
var length = (String s) -> s.length(); // LỖI biên dịch
```

Việc viết `String s` chỉ chỉ rõ kiểu tham số của lambda; nó **không chỉ rõ lambda đang triển khai functional interface nào**. Trong Java, một chữ ký giống `String -> int` không phải là một kiểu function chung được ngôn ngữ tự tạo ra. Có nhiều functional interface có thể phù hợp với cùng lambda, chẳng hạn `Function<String, Integer>` hoặc một interface do ứng dụng định nghĩa.

Cách sửa phổ biến và rõ nghĩa nhất là khai báo functional interface ở vế trái:

```java
java.util.function.Function<String, Integer> length = s -> s.length();
```

Ở đây compiler đã biết `Function<String,Integer>` là kiểu đích, nên kiểm tra và diễn giải lambda theo phương thức `Integer apply(String value)`. Bài học này giải thích vì sao `var` không thể tự giải quyết trường hợp lambda trực tiếp, khi nào `var` vẫn có thể dùng được, và cách phân biệt với `var` trong **danh sách tham số lambda**.

## 1. Hai cơ chế khác nhau: local-variable type inference và target typing

### Local-variable type inference với var

Từ Java 10, có thể viết:

```java
var count = 42;                         // int
var text = "Java";                      // String
var names = java.util.List.of("A");    // List<String>
```

Trong các dòng trên, biểu thức bên phải đã có kiểu xác định: literal `42` là `int`, literal chuỗi là `String`, còn `List.of("A")` trả về danh sách được suy luận phần tử là `String`. Compiler sử dụng các kiểu ấy để khai báo biến. `var` **không có nghĩa là kiểu động**; kiểu cục bộ được quyết định tại biên dịch và sau đó không đổi.

Đoạn trên là **mảnh mã minh họa** cần nằm trong một phương thức hoặc khối, không đặt những dòng `var` trực tiếp tại cấp field của class.

### Target typing với lambda

Lambda có dạng:

```java
(parameters) -> expression
(parameters) -> { statements; }
```

Đây là **mẫu cú pháp**, chưa phải một chương trình độc lập. Lambda có thể là implementation của **một functional method**, nhưng phải biết hợp đồng nào cần triển khai. Ví dụ:

```java
java.util.function.Predicate<String> notEmpty =
        s -> s != null && !s.isEmpty();
```

Kiểu đích `Predicate<String>` cho biết đầu vào là `String` và kết quả phải là `boolean`, ứng với phương thức `boolean test(String value)`. Nếu thiếu target type, compiler không có căn cứ để chọn kiểu đối tượng hàm phù hợp.

**Kết luận cơ chế:** `var` cần kiểu có sẵn của initializer để suy luận; lambda lại cần kiểu đích bên ngoài để xác định hợp đồng. Khi viết `var f = s -> ...`, không bên nào cung cấp kiểu đích, nên compiler báo lỗi.

## 2. Vì sao biết kiểu tham số hoặc kiểu trả về vẫn chưa đủ?

Xét các interface sau:

```java
@FunctionalInterface
interface NameLength {
    int getLength(String value);
}

@FunctionalInterface
interface OtherLength {
    int measure(String value);
}
```

Đây là những khai báo top-level hợp lệ trong Java; tên functional method khác nhau nhưng cùng cấu trúc một tham số `String` và kết quả `int`. Lambda:

```java
(String s) -> s.length()
```

**có thể phù hợp với cả hai target types**. Không có quy tắc tự động chọn `NameLength` hay `OtherLength` chỉ vì tham số đã ghi rõ `String`. Lambda không định nghĩa sẵn một class hoặc một kiểu function mang tên do compiler tự đặt.

Vì vậy, cả hai khai báo local sau đều **cố ý sai**:

```java
var first = s -> s.length();
var second = (String s) -> s.length();
```

Khai báo `second` vẫn thiếu target type dù biết kiểu tham số. Phần thân trả một `int` cũng không giải quyết được vấn đề chọn interface nào. Trong bối cảnh target là `Function<String,Integer>`, Java còn có thể boxing `int` thành `Integer`, làm số interface tương thích với cùng lambda càng đa dạng.

Khi dùng kiểu đích tường minh, hai cách sau đều hợp lệ:

```java
NameLength first = (String s) -> s.length();
OtherLength second = (String s) -> s.length();
```

Hai biến nhận những đối tượng tương thích với **hai interface khác nhau** dù phần thân lambda giống nhau. `first.getLength("Java")` và `second.measure("Java")` đều cho giá trị `4`.

## 3. Những khai báo var với lambda trực tiếp bị từ chối

Các đoạn dưới đây **cố ý không biên dịch được**:

```java
// Không có target type cho lambda không tham số.
var task = () -> System.out.println("run");

// Không có target type cho lambda một tham số.
var mapper = text -> text.length();

// Ghi rõ kiểu tham số vẫn không cung cấp target interface.
var mapper2 = (String text) -> text.length();

// Dùng var trong tham số lambda cũng không tạo ra target interface.
var mapper3 = (var text) -> text.length();

// Hai tham số cũng có cùng vấn đề.
var adder = (int left, int right) -> left + right;
```

Tùy ngữ cảnh và phiên bản compiler, thông báo thường thể hiện rằng **lambda expression needs an explicit target type** hoặc không thể suy luận kiểu của biến từ lambda. Thông điệp cốt lõi không phải thiếu ngoặc hay thiếu kiểu tham số, mà là **không có functional interface làm kiểu đích**.

Các dạng method reference đứng riêng cũng có cùng nguyên tắc:

```java
// SAI: method reference cũng cần target type.
var length = String::length;
```

`String::length` có thể phù hợp với `Function<String,Integer>`, một interface tùy chỉnh có phương thức tương đương, hoặc những ngữ cảnh chức năng tương thích khác. Không có kiểu đích, compiler không được tự chọn.

## 4. Cách đúng số 1: khai báo functional interface trực tiếp

Cách dễ đọc và thường được khuyến nghị:

```java
java.util.function.Supplier<String> greeting = () -> "Hello";
java.util.function.Predicate<String> hasText =
        text -> text != null && !text.isBlank();
java.util.function.Function<String, Integer> length =
        text -> text.length();
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (a, b) -> a + b;
```

Đây là mảnh mã minh họa có thể đặt trong phương thức.

| Interface đích | Functional method | Dạng lambda |
| --- | --- | --- |
| `Runnable` | `void run()` | `() -> System.out.println("run")` |
| `Supplier<T>` | `T get()` | `() -> value` |
| `Predicate<T>` | `boolean test(T value)` | `x -> condition` |
| `Consumer<T>` | `void accept(T value)` | `x -> action(x)` |
| `Function<T,R>` | `R apply(T value)` | `x -> transform(x)` |
| `BiFunction<T,U,R>` | `R apply(T x, U y)` | `(x, y) -> combine(x,y)` |

Bảng là các **mẫu minh họa**, các hàm `condition`, `action`, `transform`, `combine` không tự tồn tại nếu ứng dụng chưa khai báo. Nên chọn interface phản ánh đúng ý nghĩa công việc; đừng chỉ chọn một kiểu có chữ ký “trông giống” mà bỏ qua ngữ nghĩa API.

## 5. Cách đúng số 2: var nhận biến đã có kiểu chức năng

`var` hoàn toàn có thể **giữ một lambda thông qua một giá trị đã có kiểu**:

```java
java.util.function.Function<String, Integer> declared =
        text -> text.length();

var inferred = declared; // Function<String, Integer>
int size = inferred.apply("Java"); // 4
```

Khi tới `var inferred = declared`, initializer `declared` có kiểu rõ ràng là `Function<String,Integer>`. Compiler chỉ suy luận kiểu cho **biến mới từ biểu thức biến đã có kiểu**, không cần tìm target type cho lambda đứng riêng nữa.

Tương tự, nếu một factory method có kiểu trả về tường minh là functional interface:

```java
static java.util.function.Predicate<String> nonBlankRule() {
    return text -> text != null && !text.isBlank();
}

// Trong phương thức khác:
var rule = nonBlankRule(); // Predicate<String>
boolean result = rule.test("Java"); // true
```

Đây là hai **mảnh mã ghép theo ngữ cảnh**: `nonBlankRule` là static method trong class, còn phép gán `var rule` ở phương thức gọi. Lambda trong `return` có target type vì **kiểu trả về được khai báo** của `nonBlankRule`. Khi caller dùng `var`, `nonBlankRule()` đã là một lời gọi có kiểu trả về rõ ràng.

## 6. Cách đúng số 3: ép kiểu lambda sang functional interface

Nếu có lý do giữ `var` ở bên trái, có thể cung cấp target type bằng cast **ở ngay biểu thức khởi tạo**:

```java
var length = (java.util.function.Function<String, Integer>)
        (text -> text.length());

var supply = (java.util.function.Supplier<String>) () -> "ready";
```

Phép cast nêu rõ target type cho lambda, vì vậy `var` có thể suy luận từ kiểu của **toàn bộ biểu thức cast**.

Tuy nhiên cách này thường dài và khó đọc hơn so với:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();
```

Sử dụng cast khi cần phân biệt overload hoặc muốn chỉ rõ hợp đồng ở một biểu thức; đừng xem nó là cách buộc `var` tự suy luận lambda. Target type thực tế vẫn do bạn cung cấp.

Với method reference cũng tương tự:

```java
var length = (java.util.function.Function<String, Integer>)
        String::length;
```

Cả lambda và method reference ở những ví dụ này đều được kiểm tra bằng chữ ký functional method của target interface.

## 7. Chương trình Java 17: var hợp lệ sau khi có kiểu đích

Tạo tệp **`LambdaVarInferenceDemo.java`**:

```java
import java.util.Comparator;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaVarInferenceDemo {
    static Predicate<String> hasTextRule() {
        return text -> text != null && !text.isBlank();
    }

    public static void main(String[] args) {
        // Target type nằm ở bên trái.
        Function<String, Integer> length = text -> text.length();

        // var suy luận từ biến đã có kiểu rõ ràng.
        var reused = length;

        // Target type được cung cấp bởi cast.
        var plusOne = (Function<String, Integer>)
                (text -> text.length() + 1);

        // Lambda không tham số cũng cần một functional interface.
        var ready = (Supplier<String>) () -> "ready";

        // Method reference có target type từ cast.
        var sameIgnoreCase = (Comparator<String>)
                String::compareToIgnoreCase;

        // Lời gọi phương thức có kiểu trả về rõ ràng.
        var rule = hasTextRule();

        System.out.println("length=" + reused.apply("Java"));
        System.out.println("plusOne=" + plusOne.apply("Java"));
        System.out.println("ready=" + ready.get());
        System.out.println("sameIgnoreCase="
                + sameIgnoreCase.compare("java", "JAVA"));
        System.out.println("hasText=" + rule.test("Java"));
        System.out.println("blank=" + rule.test("   "));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 LambdaVarInferenceDemo.java
java LambdaVarInferenceDemo
```

**Stdout chính xác:**

```text
length=4
plusOne=5
ready=ready
sameIgnoreCase=0
hasText=true
blank=false
```

Đường suy luận kiểu của từng biến:

1. `length` có kiểu `Function<String,Integer>` được khai báo tường minh; lambda được target typing theo `apply(String)`.
2. `reused` cũng có kiểu `Function<String,Integer>` vì initializer là biến `length`.
3. `plusOne` có kiểu `Function<String,Integer>` từ cast; compiler kiểm tra thân lambda trả `int` có thể boxing thành `Integer`.
4. `ready` có kiểu `Supplier<String>` từ cast; việc tạo lambda chưa thực hiện thân `"ready"`.
5. `sameIgnoreCase` có kiểu `Comparator<String>`, nên `String::compareToIgnoreCase` được diễn giải như phép so sánh hai chuỗi.
6. `rule` có kiểu `Predicate<String>` do `hasTextRule()` khai báo trả về interface này.

**Không có dòng nào yêu cầu var tự tìm ra functional interface từ một lambda hoặc method reference đứng riêng.** Kiểu đích được xác định trước hoặc được nêu ngay trong biểu thức cast.

## 8. var trong tham số lambda là chuyện khác

Từ Java 11, Java cho phép dùng `var` **trong danh sách tham số lambda**, chẳng hạn:

```java
java.util.function.Function<String, String> normalize =
        (var text) -> text.trim().toUpperCase();
```

Ở ví dụ này, `var` là cú pháp cho **tham số lambda** `text`, và compiler suy luận kiểu `String` **từ target type** `Function<String,String>`. Điều này không có nghĩa `var` có thể tự suy luận kiểu của toàn bộ lambda.

Hai vị trí khác nhau:

| Vị trí var | Câu hỏi cần suy luận | Có đủ thông tin từ đâu? |
| --- | --- | --- |
| `var f = expression;` | Biến cục bộ `f` có kiểu gì? | Từ kiểu của initializer `expression`. |
| `Function<String,Integer> f = (var s) -> ...;` | Tham số lambda `s` có kiểu gì? | Từ functional method của kiểu đích `Function<String,Integer>`. |

Khi dùng `var` trong danh sách tham số lambda có nhiều tham số, phải dùng cho **toàn bộ tham số**:

```java
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (var a, var b) -> a + b;
```

Các dạng sau cố ý sai:

```java
// SAI: trộn var và tham số suy luận kiểu.
(var a, b) -> a + b

// SAI: trộn var và kiểu tường minh.
(var a, Integer b) -> a + b

// SAI: tham số có var phải ở trong ngoặc.
var a -> a + 1

// SAI: có var cho tham số nhưng không có kiểu đích cho lambda.
var f = (var a) -> a + 1;
```

Ngoài chức năng làm rõ kiểu suy luận, `var` trong tham số lambda cho phép đặt annotation ở vị trí tham số khi cú pháp và target type phù hợp. `var` vẫn không phải một kiểu Java độc lập có thể dùng thay mọi kiểu dữ liệu.

## 9. Chương trình Java 17: var trong tham số có target type

Tạo tệp **`LambdaParameterVarDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaParameterVarDemo {
    public static void main(String[] args) {
        Function<String, String> normalize =
                (var text) -> text.trim().toUpperCase(Locale.ROOT);

        BiFunction<Integer, Integer, Integer> add =
                (var left, var right) -> left + right;

        Predicate<String> valid =
                (var text) -> text != null && !text.isBlank();

        // Ở vế phải là một biến Function đã có kiểu.
        var sameNormalizer = normalize;

        System.out.println("normalize=" + sameNormalizer.apply(" java "));
        System.out.println("add=" + add.apply(2, 3));
        System.out.println("validNull=" + valid.test(null));
        System.out.println("validJava=" + valid.test("Java"));

        // map cung cấp target type cho method reference.
        var lengths = List.of("a", "java").stream()
                .map(String::length)
                .toList();

        System.out.println("lengths=" + lengths);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 LambdaParameterVarDemo.java
java LambdaParameterVarDemo
```

**Stdout chính xác:**

```text
normalize=JAVA
add=5
validNull=false
validJava=true
lengths=[1, 4]
```

Trong `normalize`, target type `Function<String,String>` quyết định `text` là `String`. Trong `add`, target type `BiFunction<Integer,Integer,Integer>` quyết định cả hai tham số là `Integer`. Còn `List.of(...).stream().map(String::length)` hợp lệ vì `map` nhận `Function<? super T,? extends R>` và do đó cung cấp ngữ cảnh target type cho method reference. Kết quả terminal `toList()` có kiểu `List<Integer>` để `var lengths` suy luận.

## 10. Target typing trong tham số phương thức, return và phép ép kiểu

Lambda có thể nhận target type từ nhiều ngữ cảnh khác ngoài phép gán:

**Truyền vào phương thức:**

```java
static int evaluate(java.util.function.Function<String, Integer> fn) {
    return fn.apply("Java");
}

// Trong phương thức gọi:
int length = evaluate(s -> s.length()); // 4
```

Đây là **hai mảnh code minh họa**: `evaluate` được khai báo trong class, còn lời gọi nằm trong phương thức khác. Tham số `fn` có kiểu `Function<String,Integer>`, nên đối số lambda được kiểm tra theo target type này.

**Trả về từ phương thức có kiểu khai báo:**

```java
static java.util.function.Supplier<String> makeGreeting() {
    return () -> "Xin chào";
}
```

Return type `Supplier<String>` cung cấp target type cho lambda. Caller có thể viết `var supplier = makeGreeting();` vì phép gọi `makeGreeting()` có kiểu trả về đã biết.

**Ép kiểu:**

```java
Object callback = (Runnable) () -> System.out.println("run");
```

Cast `(Runnable)` cung cấp kiểu đích cho lambda. Biến `callback` được khai báo kiểu `Object`, nên muốn gọi `run()` ở nơi khác phải kiểm tra/ép về `Runnable` phù hợp. Tạo lambda hợp lệ và khả năng gọi API qua kiểu của biến tham chiếu là hai vấn đề khác nhau.

## 11. Vì sao không thể “tự chọn” một interface theo chữ ký?

Java sử dụng **nominal types** cho functional interface: một lambda được chuyển đổi sang interface **được chỉ ra trong ngữ cảnh**, không phải sang một cấu trúc `(T) -> R` chung do Java tự tạo. Ngoài chữ ký, interface còn mang thông tin như:

- Tên và ngữ nghĩa hợp đồng, ví dụ `Predicate<T>` kiểm tra điều kiện còn `Function<T,Boolean>` diễn đạt phép chuyển đổi sang wrapper `Boolean`.
- Quy định checked exceptions trong functional method (ví dụ `Runnable.run()` không khai báo checked exception, còn `Callable<V>.call()` khai báo `throws Exception`).
- Các default/static methods bổ sung, như `Predicate.and`, `Function.andThen`.
- Ràng buộc generic, tham số kiểu, kiểu kết quả và các quy tắc tương thích.

Hai interface có abstract method cùng chữ ký không nhất thiết thay thế được nhau trong lời gọi API. Không thể đoán rằng `(String s) -> s.length()` nên tự động là `Function<String,Integer>` chỉ vì interface này quen thuộc.

Hệ quả khi có phương thức overload: nếu hai overload nhận những functional interfaces khác nhau nhưng cùng tương thích một lambda, lời gọi có thể trở nên **mơ hồ (ambiguous)**. Compiler áp dụng quy tắc overload resolution của Java; khi cần, có thể chỉ rõ kiểu bằng biến khai báo tường minh hoặc cast. `var` không tự giải quyết mơ hồ kiểu đích.

## 12. Những ngộ nhận và lỗi phổ biến

1. **“var có thể đoán mọi kiểu.”** Sai. `var` suy luận từ initializer đã có kiểu; nó không phát minh functional interface cho lambda.
2. **“Viết kiểu tham số lambda là đủ.”** Sai. `var f = (String s) -> s.length();` vẫn không có target type.
3. **“Lambda tự mang kiểu `Function`.”** Sai. Nó có thể phù hợp nhiều functional interfaces; `Function` chỉ là một lựa chọn.
4. **“Method reference không cần target type.”** Sai. `var f = String::length;` cũng không hợp lệ.
5. **“Không thể dùng var với bất kỳ giá trị lambda nào.”** Sai. `var f = existingFunction;`, `var f = factory();` và `var f = (Function<String,Integer>) (s -> s.length());` đều có nguồn kiểu rõ ràng.
6. **“Dùng (var x) ở lambda giúp suy luận cả interface.”** Sai. `var` trong danh sách tham số lambda cũng cần target type.
7. **“var là dynamic typing.”** Sai. Kiểu của local được suy luận tĩnh khi biên dịch, khác ngôn ngữ có biến đổi kiểu runtime.
8. **“Nếu compile được sau cast thì có nghĩa var tự suy luận lambda.”** Sai. Cast mới là nơi cung cấp target type.
9. **“Có thể trộn var và kiểu tham số trong lambda.”** Sai. Các tham số trong cùng danh sách phải nhất quán theo quy tắc Java.
10. **“Kiểu suy luận được cũng đồng nghĩa API nhận được.”** Sai. Kiểu của biến quyết định các phương thức có thể gọi; ví dụ `Object callback` không có `run()` cho tới khi kiểm tra và ép kiểu.

## 13. Bảng quyết định nhanh

| Mã | Hợp lệ? | Lý do |
| --- | --- | --- |
| `var x = 42;` | Có | Literal có kiểu `int`. |
| `var f = () -> 42;` | Không | Lambda không có target type. |
| `var f = (String s) -> s.length();` | Không | Chỉ rõ tham số, chưa rõ interface. |
| `var f = String::length;` | Không | Method reference cần target type. |
| `Supplier<Integer> f = () -> 42;` | Có | Target type được khai báo. |
| `var f = (Supplier<Integer>) () -> 42;` | Có | Cast cung cấp target type. |
| `Function<String,Integer> f = s -> s.length(); var g = f;` | Có | `g` suy luận từ biến có kiểu. |
| `var f = makeSupplier();` | Có nếu `makeSupplier()` có kiểu trả về xác định | Initializer là lời gọi có kiểu. |
| `Function<String,Integer> f = (var s) -> s.length();` | Có với Java 11+ | `var s` dùng target type bên ngoài. |

Với `var`, các quy tắc khác của khai báo biến cục bộ cũng cần tuân thủ; ví dụ `var x;` không hợp lệ vì thiếu initializer. Bảng chỉ tập trung vào quan hệ giữa `var`, lambda và target typing.

## 14. Tự kiểm tra

**Câu 1.** Vì sao câu sau không biên dịch, dù `String` đã được ghi tường minh?

```java
var f = (String s) -> s.toUpperCase();
```

**Đáp án:** Chưa có functional interface làm target type cho lambda. `String` mới chỉ là kiểu tham số, không cho biết hợp đồng cần triển khai.

**Câu 2.** Viết lại câu trên sao cho rõ nghĩa:

```java
java.util.function.Function<String, String> f =
        s -> s.toUpperCase();
```

Cách này khai báo kiểu đích `Function<String,String>`; compiler suy luận tham số `s` là `String` và kiểm tra kiểu kết quả.

**Câu 3.** Có thể giữ `var` ở vế trái bằng cách nào?

```java
var f = (java.util.function.Function<String, String>)
        (s -> s.toUpperCase());
```

Hợp lệ vì cast cung cấp target type; không có sự suy luận lambda đứng riêng.

**Câu 4.** `Function<String,Integer> f = (var s) -> s.length();` hợp lệ không?

**Có** với Java 11+. `var` thuộc tham số lambda, nhận kiểu từ target type đã được khai báo.

**Câu 5.** Vì sao đoạn `var f = String::length;` không hợp lệ?

**Đáp án:** Method reference là poly expression, cần functional interface target. Có thể dùng `Function<String,Integer> f = String::length;`.

**Câu 6.** `var f = factory();` có thể nhận giá trị là lambda không?

**Có**, nếu `factory()` trả về một đối tượng có kiểu functional interface xác định. `var` suy luận từ kiểu trả về của phương thức, chứ không suy luận trực tiếp từ cú pháp lambda.

**Ghi nhớ:** `var` ở vế trái cần một initializer **đã có kiểu**; lambda và method reference đứng riêng cần **functional interface làm kiểu đích**. Hãy khai báo interface tường minh, dùng factory trả về interface, hoặc cung cấp target type bằng cast khi phù hợp. `var` trong **tham số lambda** chỉ là cú pháp suy luận kiểu của tham số khi target type đã tồn tại.
