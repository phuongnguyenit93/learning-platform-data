# Suy luận kiểu của lambda và tham chiếu phương thức trong Java Generics

## Mục tiêu học tập

Lambda expression và method reference giúp truyền hành vi vào một phương thức mà không cần khai báo lớp ẩn danh dài dòng. Nhưng khi kết hợp với Java Generics, kiểu của một lambda không thể được hiểu chỉ bằng cách nhìn vào biểu thức `s -> s.length()`. Compiler cần một **kiểu đích** (*target type*), thường là một *functional interface*, để xác định kiểu tham số, kiểu kết quả, overload phù hợp và những ràng buộc liên quan.

Sau bài này, bạn có thể:

- Giải thích **target typing**, **functional interface**, phương thức trừu tượng duy nhất (*SAM — single abstract method*) và **poly expression**.
- Phân biệt kiểu được suy luận cho tham số lambda với kiểu generic được suy luận khi gọi phương thức nhận lambda.
- Sử dụng `Function<T,R>`, `Predicate<T>`, `Supplier<T>`, `Consumer<T>`, `Comparator<T>`, `UnaryOperator<T>` và `BinaryOperator<T>` đúng ngữ cảnh.
- Viết method reference kiểu static, instance có receiver đã biết, instance với receiver là tham số đầu và constructor reference.
- Hiểu vì sao cùng một method reference có thể trỏ tới overload khác nhau khi target type khác nhau.
- Xử lý lỗi `lambda expression needs an explicit target-type`, `reference to ... is ambiguous`, suy luận kiểu không tương thích và việc sử dụng `var` trong lambda.
- Đọc và kiểm chứng các ví dụ Java 17+ bằng `javac`/`java`, không đoán đầu ra.

## 1. Nền tảng: functional interface quyết định hợp đồng của lambda

Một lambda cần **functional interface làm target**. Chẳng hạn:

```java
@FunctionalInterface
interface Converter<S, R> {
    R convert(S input);
}
```

Với `Converter<String,Integer>`, compiler biết tham số lambda là `String` và giá trị trả về phải tương thích `Integer`:

```java
Converter<String, Integer> length = text -> text.length();
Integer count = length.convert("Java"); // 4
```

`String.length()` trả `int`, được boxing sang `Integer`. Nếu target là `Converter<Integer,Integer>`, thân `text.length()` sẽ không biên dịch vì `Integer` không có method đó.

**Trọng tâm của bài này là target typing/inference**: compiler suy ra kiểu lambda từ **nơi biểu thức được dùng**, không phải bằng cách đoán một kiểu lambda độc lập. Những interface chuẩn `Function`, `Predicate`, `Supplier`, `Consumer`, `Comparator`, `Callable` là các nguồn target khác nhau; chúng có SAM với số tham số/return/checked exceptions riêng. Functional interface vẫn có thể có method default/static, và annotation `@FunctionalInterface` giúp compiler kiểm tra tính hợp lệ của declaration.

Ở phần sau, ta phân tích suy luận kiểu khi lambda/method reference tham gia **generic method calls** và cách giải overload không rõ ràng; đó là năng lực riêng vượt ngoài việc thuộc bảng các interface chuẩn.

## 2. Target typing: từ nơi dùng quay ngược lại biểu thức

Java coi lambda và method reference là các **poly expression** trong những ngữ cảnh thích hợp: kiểu của chúng phụ thuộc vào vị trí sử dụng.

Ví dụ:

```java
Function<String, Integer> length = s -> s.length();
```

Compiler biết:

1. Biểu thức nằm ở vế phải của phép gán vào `Function<String,Integer>`.
2. SAM `Function.apply` nhận String và trả Integer.
3. Vì vậy `s` được suy luận là `String`.
4. `s.length()` trả `int`, có thể boxing thành `Integer`.
5. Lambda hợp lệ theo target type.

Cùng biểu thức nhưng kiểu đích không tương thích:

```java
// KHÔNG BIÊN DỊCH:
// Function<Integer, Integer> length = s -> s.length();
```

Lý do là `s` lúc này có kiểu Integer, không có method `length()`.

**Target type thường đến từ:** khai báo và phép gán, tham số của lời gọi method, return statement bên trong method có kiểu trả về functional interface, cast sang functional interface, biểu thức điều kiện trong ngữ cảnh có đích và các tình huống khác được JLS quy định.

Ví dụ target từ lời gọi method:

```java
List<Integer> lengths =
        List.of("A", "Java").stream()
            .map(String::length)
            .toList();
```

Compiler dùng chữ ký generic của `Stream.map` và bối cảnh gọi để suy ra method reference `String::length` chuyển String thành Integer (kết quả `int` được boxing). Java 17 hỗ trợ `Stream.toList()`; kết quả không sửa được theo hợp đồng của API này.

**Không có target type, lambda và method reference không thể tự mang một kiểu độc lập như một object thông thường.**

## 3. Tại sao `var fn = s -> s.length()` không hợp lệ?

Từ Java 10, `var` cho phép compiler suy luận kiểu của biến cục bộ từ biểu thức khởi tạo:

```java
var number = 42;              // int
var text = "hello";           // String
var names = List.of("A");     // List<String>
```

Nhưng một lambda không cung cấp target functional interface khi khởi tạo biến bằng `var`:

**Tệp `UntypedLambda.java` — cố ý không biên dịch:**

```java
class UntypedLambda {
    void test() {
        var operation = s -> s.length();
    }
}
```

Lệnh:

```bash
javac --release 17 UntypedLambda.java
```

Thông báo trọng tâm đã kiểm chứng:

```text
cannot infer type for local variable operation
(lambda expression needs an explicit target-type)
```

Tương tự method reference:

**Tệp `UntypedMethodReference.java` — cố ý không biên dịch:**

```java
class UntypedMethodReference {
    void test() {
        var operation = String::trim;
    }
}
```

Lệnh biên dịch cho lỗi:

```text
cannot infer type for local variable operation
(method reference needs an explicit target-type)
```

Cách sửa: cung cấp functional interface ở phía khai báo hoặc cast rõ ràng.

```java
Function<String, Integer> length = s -> s.length();
Function<String, String> trim = String::trim;
```

Nếu rất muốn dùng `var` cho biến lưu lambda, phải tạo target type ở biểu thức khởi tạo bằng một cast hay một lời gọi method có kiểu rõ:

```java
var operation =
        (java.util.function.Function<String, Integer>) (s -> s.length());
```

Cách này dài hơn và thường kém dễ đọc so với khai báo `Function<String,Integer>` trực tiếp. `var` hữu ích ở nhiều chỗ khác, nhưng **không giải quyết chuyện thiếu target type cho lambda/method reference**.

## 4. `var` trong danh sách tham số lambda là chuyện khác

Java 11 cho phép viết `var` ở **tham số** của lambda:

```java
Function<String, Integer> a = (var s) -> s.length();
Function<String, Integer> b = (s) -> s.length();
Function<String, Integer> c = s -> s.length();
```

Cả ba biểu thức đều nhận String và trả Integer vì target type là `Function<String,Integer>`. Việc viết `var s` trong lambda **không** làm biến lambda thành không cần target.

Một ứng dụng của `var` trên tham số lambda là cho phép annotation trên tham số khi cần:

```java
// Dạng minh họa cú pháp nếu @MyAnnotation phù hợp với PARAMETER:
Function<String, Integer> f =
        (@MyAnnotation var s) -> s.length();
```

Không thể chép riêng ví dụ annotation này để biên dịch nếu chưa định nghĩa `MyAnnotation`. Đây chỉ là minh họa hình thức.

### Không trộn `var` và tham số implicit

**Tệp `MixedVarLambdaParameters.java` — cố ý không biên dịch:**

```java
import java.util.function.BiFunction;

class MixedVarLambdaParameters {
    void test() {
        BiFunction<String, String, String> f =
                (var a, b) -> a + b;
    }
}
```

`javac --release 17` báo:

```text
invalid lambda parameter declaration
(cannot mix 'var' and implicitly-typed parameters)
```

Cách sửa:

```java
BiFunction<String, String, String> f =
        (var a, var b) -> a + b;
```

Hoặc:

```java
BiFunction<String, String, String> f =
        (a, b) -> a + b;
```

Cả hai hợp lệ khi được đặt trong method với import `BiFunction`. Quy tắc thống nhất cách khai báo tham số trong cùng một lambda: không trộn khai báo có `var` với tham số implicit hoặc explicit kiểu khác một cách tùy tiện.

## 5. Suy luận kiểu generic khi lambda là đối số method

Phần quan trọng hơn là suy luận kiểu không chỉ xảy ra bên trong lambda. Xét API generic:

```java
static <T, R> List<R> transform(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

Đây là hàm xuất hiện trong chương trình hoàn chỉnh phần 7 và cần import `List`, `ArrayList`, `Function`.

Lời gọi:

```java
List<Integer> sizes =
        transform(List.of("A", "Java"), String::length);
```

Compiler phối hợp nhiều ràng buộc:

1. `source` có các phần tử String, nên T phù hợp với String theo quan hệ subtype/wildcard.
2. `String::length` là method reference cần target `Function<? super T,? extends R>`.
3. Phương thức `String.length()` trả `int`, có thể boxing thành Integer.
4. Biểu thức kết quả được gán cho `List<Integer>`, thêm ngữ cảnh để suy luận R.
5. Do đó chương trình có một danh sách Integer với các giá trị `1` và `4`.

Đây là ví dụ về **inference kết hợp**: suy luận type argument của method generic và kiểm tra lambda/reference tương tác qua các *constraint* của compiler. Bạn không cần viết tường minh toàn bộ type argument trong lời gọi thông thường.

Nếu cần thể hiện ý định rõ ràng hoặc compiler không suy luận như mong muốn, có thể viết type arguments:

```java
List<Integer> sizes =
        LambdaInferenceDemo.<String, Integer>transform(
                List.of("A", "Java"), String::length);
```

Đoạn này nằm trong ngữ cảnh class `LambdaInferenceDemo` ở phần 7. Việc chỉ rõ type argument nên dùng khi thực sự cải thiện tính đúng đắn/khả năng đọc; không phải cách bắt buộc cho mọi generic method.

### Vì sao dùng `? super T` ở mapper?

`Function<? super T, ? extends R>` linh hoạt hơn `Function<T,R>` theo nhu cầu producer/consumer:

- Mapper **tiêu thụ** một đối tượng T, nên có thể chấp nhận một supertype của T.
- Mapper **sản xuất** kết quả tương thích với R, nên có thể trả một subtype của R.

Đây là ứng dụng thực tế của **PECS (Producer Extends, Consumer Super)**. Nó giúp API nhận nhiều dạng Function mà vẫn giữ quan hệ kiểu an toàn.

Ví dụ về chuỗi:

```java
List<String> upper = transform(
        List.of(" a ", " b "),
        LambdaInferenceDemo::normalize);
```

`normalize(String)` trả String, và kiểu R được suy luận phù hợp với `List<String>`. Mã chạy ở phần 7 in `upper=[A, B]`.

### Suy luận kết quả lambda theo target

Một method generic khác:

```java
static <T> T choose(T first, T second, BinaryOperator<T> chooser) {
    return chooser.apply(first, second);
}
```

Gọi:

```java
String longest = choose("AB", "C",
        (a, b) -> a.length() >= b.length() ? a : b);
```

Compiler xác định a và b là String qua T, rồi kiểm tra biểu thức điều kiện trả String, tương thích `BinaryOperator<String>`. Không cần khai báo `(String a, String b)` nếu target đã rõ.

## 6. Các loại method reference và cách suy luận

Method reference không gọi phương thức ngay lập tức. Nó tạo một biểu thức chỉ có nghĩa cụ thể khi compiler biết functional interface đích.

| Dạng | Ví dụ | Ý nghĩa trong target phù hợp |
| --- | --- | --- |
| Static method | `Integer::parseInt` | Nhận String, trả int/Integer theo target. |
| Unbound instance method | `String::length` | Receiver là đối số đầu; nhận String rồi gọi `length()`. |
| Bound instance method | `"An"::equals` | Receiver `"An"` có sẵn; nhận một đối số để so sánh. |
| Bound instance method khác | `"pre-"::concat` | Nhận suffix rồi nối vào receiver cố định. |
| Constructor | `ArrayList::new` | Tạo ArrayList theo signature constructor tương thích. |
| Constructor với đối số | `Member::new` | Nhận String rồi tạo Member. |
| Generic static method | `LambdaInferenceDemo::<String>identity` | Chọn explicit type argument cho method generic. |

### 6.1. Static method reference

`Integer::parseInt` là một method reference tới các overload static. Khi gán:

```java
Function<String, Integer> parse = Integer::parseInt;
```

target có một input String và result Integer, nên compiler chọn method tương thích (ví dụ `parseInt(String)` trả int và kết quả được boxing).

Một reference tới method overloaded như `String::valueOf` cũng cần target để chọn cách gọi:

```java
Function<Integer, String> toStringValue = String::valueOf;
String text = toStringValue.apply(9);
```

`String` có nhiều overload `valueOf`. Target type đóng vai trò ràng buộc số lượng và kiểu tham số. Không nên khẳng định rằng mọi method reference overloaded luôn chọn duy nhất một overload chỉ từ tên method; compiler xét cả chữ ký và ngữ cảnh, và đôi khi báo ambiguous.

### 6.2. Unbound instance method

`String::trim` trong:

```java
Function<String, String> trim = String::trim;
```

có nghĩa là nhận một String làm **receiver** rồi gọi `receiver.trim()`. Đây là method reference loại `ReferenceType::instanceMethod`. Với `String::length`, `Function<String,Integer>` cũng hoạt động dù method `length()` không có tham số tường minh; String đầu vào chính là receiver.

Cũng vì vậy:

```java
Function<Member, String> readName = Member::name;
```

dùng method truy cập record `Member.name()`; đối số duy nhất là instance Member.

### 6.3. Bound instance method

Với:

```java
Predicate<String> isAn = "An"::equals;
Function<String, String> addPrefix = "pre-"::concat;
```

receiver đã được xác định bằng một biểu thức đứng trước dấu `::`. Functional interface chỉ cần cung cấp những đối số còn lại. `isAn.test("An")` trả true; `addPrefix.apply("fix")` trả `"pre-fix"`.

Đừng nhầm hai dạng:

- `String::trim`: receiver được truyền vào như tham số của Function.
- `someString::trim`: receiver đã có; phù hợp với target không tham số như `Supplier<String>`.

Một lưu ý nâng cao: biểu thức receiver ở một bound method reference được đánh giá khi tạo reference, nên nếu việc lấy receiver có side effect thì thời điểm diễn ra side effect có thể khác với lambda trì hoãn việc tính receiver tới lúc gọi. Vì vậy không phải mọi method reference đều có thể thay thế máy móc bằng lambda mà không xét ngữ nghĩa.

### 6.4. Constructor reference

`ArrayList::new` cũng là một poly expression cần target:

```java
Supplier<ArrayList<String>> listFactory = ArrayList::new;
ArrayList<String> result = listFactory.get();
```

Target `Supplier` yêu cầu constructor không đối số. Với `Function<Integer,ArrayList<String>>`, compiler có thể lựa chọn constructor nhận dung lượng ban đầu tùy chữ ký phù hợp; cả hai cùng viết `ArrayList::new` nhưng ngữ cảnh khác nhau.

Trong chương trình phần 7, `Member::new` là constructor reference tạo record Member từ String:

```java
Function<String, Member> memberFactory = Member::new;
Member person = memberFactory.apply("An");
```

Method reference không phải một phép “ép class thành Function” ở runtime; compiler dựng implementation tương thích với target functional interface.

### 6.5. Generic method reference và explicit type argument

Một phương thức generic:

```java
static <T> T identity(T value) {
    return value;
}
```

có thể được dùng:

```java
Function<String,String> id = LambdaInferenceDemo::identity;
```

hoặc chỉ rõ type argument:

```java
Function<String,String> id =
        LambdaInferenceDemo::<String>identity;
```

Cả hai nằm trong ngữ cảnh lớp `LambdaInferenceDemo`. Với phương thức không quá phức tạp, compiler suy luận T từ target. Explicit type argument dùng khi muốn khóa T thành kiểu cụ thể, khi suy luận mơ hồ hoặc để làm rõ ý định.

## 7. Chương trình Java 17 hoàn chỉnh

**Tệp `LambdaInferenceDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaInferenceDemo {
    record Member(String name) {}

    static <T, R> List<R> transform(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    static <T> T choose(T first, T second, BinaryOperator<T> chooser) {
        return chooser.apply(first, second);
    }

    static <T> T identity(T value) {
        return value;
    }

    static String normalize(String s) {
        return s.trim().toUpperCase(Locale.ROOT);
    }

    static String format(Object o) {
        return "Object:" + o;
    }

    static String format(String s) {
        return "String:" + s;
    }

    static void dispatch(Supplier<String> value) {
        System.out.println("dispatch=" + value.get());
    }

    static void dispatch(Callable<String> value) throws Exception {
        System.out.println("callable=" + value.call());
    }

    public static void main(String[] args) {
        Function<String, Integer> length = s -> s.length();
        Function<String, Integer> lengthVar = (var s) -> s.length();
        Function<String, Integer> lengthRef = String::length;
        System.out.println("lengths="
                + length.apply("Java") + ","
                + lengthVar.apply("Hi") + ","
                + lengthRef.apply("A"));

        List<Integer> sizes = transform(List.of("A", "Java"), String::length);
        System.out.println("sizes=" + sizes);

        List<String> upper = transform(
                List.of(" a ", " b "), LambdaInferenceDemo::normalize);
        System.out.println("upper=" + upper);

        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, String> stringify = String::valueOf;
        System.out.println("parse=" + parse.apply("42")
                + ",valueOf=" + stringify.apply(9));

        Predicate<String> isAn = "An"::equals;
        Function<String, String> trim = String::trim;
        Function<String, String> prefix = "pre-"::concat;
        System.out.println("refs=" + isAn.test("An") + ","
                + trim.apply(" x ") + "," + prefix.apply("fix"));

        Supplier<ArrayList<String>> listFactory = ArrayList::new;
        Function<String, Member> memberFactory = Member::new;
        Function<Member, String> nameOf = Member::name;
        List<Member> members = listFactory.get().isEmpty()
                ? List.of(memberFactory.apply("Binh"), memberFactory.apply("An"))
                : List.of();
        List<Member> sorted = new ArrayList<>(members);
        sorted.sort(Comparator.comparing(Member::name));
        System.out.println("sorted=" + transform(sorted, nameOf));

        Function<String, String> selectOverload = LambdaInferenceDemo::format;
        System.out.println("overload=" + selectOverload.apply("x"));

        String longest = choose("AB", "C", (a, b) ->
                a.length() >= b.length() ? a : b);
        System.out.println("chosen=" + longest);

        System.out.println("identity="
                + transform(List.of("ok"),
                        LambdaInferenceDemo::<String>identity));

        dispatch((Supplier<String>) () -> "supplier");
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all LambdaInferenceDemo.java
java LambdaInferenceDemo
```

**Stdout đã được kiểm chứng:**

```text
lengths=4,2,1
sizes=[1, 4]
upper=[A, B]
parse=42,valueOf=9
refs=true,x,pre-fix
sorted=[An, Binh]
overload=String:x
chosen=AB
identity=[ok]
dispatch=supplier
```

`javac --release 17 -Xlint:all` đã biên dịch chương trình không phát sinh warning trong kiểm thử.

### 7.1. Lambda với tham số ngầm và `var`

Ba biến `length`, `lengthVar`, `lengthRef` cùng thỏa `Function<String,Integer>` nhưng được diễn đạt bằng lambda ngầm, lambda có `var` và method reference. Dòng kết quả `lengths=4,2,1` giúp đối chiếu ba cách gọi.

### 7.2. Inference giữa `transform` và mapper

`sizes` chứa Integer từ `String::length`. `upper` chứa String từ `normalize`. Đây là trường hợp compiler kết hợp generics của method với target type của method reference.

### 7.3. Static/bound/unbound references

`Integer::parseInt`, `String::valueOf` là static; `String::trim` là unbound instance; `"An"::equals` và `"pre-"::concat` là bound instance. Kết quả `refs=true,x,pre-fix` cho thấy chúng hoạt động theo kiểu đầu vào/đầu ra target.

### 7.4. Constructor reference và comparator

`ArrayList::new` cung cấp list mới. `Member::new` tạo record. `Member::name` đọc tên. `Comparator.comparing(Member::name)` cần suy luận kiểu key và so sánh chuỗi; chương trình sắp tên thành `[An, Binh]`.

### 7.5. Overloaded method reference được target xác định

Trong lớp có cả `format(Object)` và `format(String)`. Khi gán `LambdaInferenceDemo::format` cho `Function<String,String>`, compiler chọn overload cụ thể tương thích, và ví dụ đã chạy cho `String:x`. Method reference chỉ có tên giống nhau nhưng không hoàn toàn thiếu thông tin về overload: **target signature** hướng dẫn lựa chọn.

### 7.6. Generic method reference explicit type argument

`LambdaInferenceDemo::<String>identity` cho biết rõ phương thức generic `identity` được sử dụng với T=String. Lời gọi `transform` nhận method reference này và in `identity=[ok]`.

## 8. Overload nhận lambda: tại sao dễ mơ hồ?

Một lambda có thể phù hợp nhiều functional interface không có quan hệ subtype. Ví dụ:

**Tệp `AmbiguousLambdaOverload.java` — cố ý không biên dịch:**

```java
import java.util.function.Supplier;
import java.util.concurrent.Callable;

class AmbiguousLambdaOverload {
    static void choose(Supplier<String> callback) {}
    static void choose(Callable<String> callback) {}

    static void test() {
        choose(() -> "ok");
    }
}
```

`Supplier<String>` và `Callable<String>` đều nhận 0 tham số và trả String. Lambda `() -> "ok"` phù hợp về hình dạng và result cho cả hai, compiler không thể chọn một overload duy nhất.

Lệnh:

```bash
javac --release 17 AmbiguousLambdaOverload.java
```

Lỗi chính đã kiểm chứng:

```text
reference to choose is ambiguous
both method choose(Supplier<String>) and method choose(Callable<String>) match
```

### Cách giải quyết 1: biến có kiểu tường minh

```java
Supplier<String> message = () -> "ok";
choose(message);
```

Trong ngữ cảnh lớp `AmbiguousLambdaOverload`, kiểu `message` làm compiler chọn overload nhận Supplier.

### Cách giải quyết 2: cast vào functional interface đích

```java
choose((Supplier<String>) () -> "ok");
```

Đây là cách chương trình chạy phần 7 phân giải overload cho `dispatch`. Dùng cast cục bộ có thể hợp lý nếu API bắt buộc giữ hai overload, nhưng cũng có thể làm lời gọi khó đọc.

### Cách giải quyết 3: thiết kế lại tên hoặc chữ ký API

Nếu hai overload làm các nghiệp vụ khác nhau, đặt tên `chooseSupplier` và `chooseCallable` rõ hơn. Đặc biệt không nên tạo overload chỉ khác `Function<String,Integer>` và `Function<String,String>`: hai kiểu này có **cùng erasure `Function`**, nên tạo `name clash` ở cấp khai báo trước cả bước giải quyết lambda.

**Lưu ý:** không phải mọi overload có tham số functional interface đều mơ hồ. JLS có quy tắc xác định phương thức cụ thể hơn dựa trên tham số và dạng lambda/method reference. Chỉ kết luận “ambiguous” khi compiler thực tế không thể chọn duy nhất một ứng viên theo quy tắc overload resolution. Ví dụ Supplier/Callable ở trên là trường hợp đã được biên dịch và xác nhận lỗi.

## 9. Những ví dụ không biên dịch: hiểu đúng nguyên nhân

### 9.1. Sai kiểu tham số explicit trong lambda

**Tệp `WrongLambdaParam.java`:**

```java
import java.util.function.Function;

class WrongLambdaParam {
    Function<String, Integer> f = (Integer x) -> x + 1;
}
```

Lỗi:

```text
incompatible types: incompatible parameter types in lambda expression
```

Target `Function<String,Integer>` yêu cầu tham số String, nhưng lambda lại khai báo tường minh Integer. Chỉ sửa thân lambda không đủ: phải làm cho chữ ký tham số thực sự tương thích với target.

### 9.2. Không có target type cho method reference

`var operation = String::trim;` bị từ chối như phần 3. Sửa thành `Function<String,String> operation = String::trim;`.

### 9.3. Không có target type cho lambda

`var operation = s -> s.length();` bị từ chối. Sửa bằng functional interface đích có kiểu phù hợp.

### 9.4. Trộn `var` và implicit parameters

`(var a, b) -> a + b` không hợp lệ. Viết cả hai tham số bằng `var` hoặc không dùng `var` cho cả hai.

### 9.5. Mơ hồ do overload

`choose(() -> "ok")` khi có cả `choose(Supplier<String>)` và `choose(Callable<String>)` bị ambiguous. Dùng biến typed, cast hoặc thiết kế API tách tên.

Những tệp lỗi ở các phần trên phải biên dịch **riêng**, không đặt vào tệp `LambdaInferenceDemo.java` chạy thành công rồi mong cả project biên dịch bình thường.

## 10. Những giới hạn khác của inference cần nhớ

### 10.1. Biểu thức và block lambda có quy tắc kết quả

Với `Function<String,Integer>`, lambda phải cung cấp một giá trị tương thích Integer trên mọi đường hoàn tất bình thường theo hợp đồng:

```java
Function<String, Integer> size = text -> {
    return text.length();
};
```

Với `Consumer<String>`, method chức năng trả void:

```java
Consumer<String> printer = text -> System.out.println(text);
```

`System.out.println(text)` là method invocation phù hợp với void-compatible expression lambda. Khi dùng block body, cần phân biệt khối thực hiện tác vụ không trả giá trị và khối trả giá trị đúng yêu cầu. Không phải biểu thức nào có thể dùng trong body Function cũng có thể dùng giống hệt trong Runnable/Consumer.

### 10.2. Biến bên ngoài lambda phải final hoặc effectively final

Một lambda có thể đọc biến cục bộ từ phạm vi ngoài khi biến ấy không bị gán lại sau khi khởi tạo:

```java
String prefix = "ID-";
Function<String, String> addPrefix = value -> prefix + value;
System.out.println(addPrefix.apply("7")); // ID-7
```

Nếu sau đó gán `prefix = "NEW-";` trong cùng phạm vi, compiler không cho capture biến như thế nữa. Đây là giới hạn của biến cục bộ bị capture; không phải “type inference đã sai” hay “generic không hỗ trợ thay đổi”.

Đối với field của object, quy tắc khác với capture local variable, nhưng thay đổi trạng thái chia sẻ cần thiết kế và đồng bộ phù hợp.

### 10.3. Checked exceptions phải tương thích SAM

`Function.apply` không khai báo checked exception. Một lambda cho Function không thể tự do ném `IOException` chưa bắt và chưa khai báo đúng. `Callable.call() throws Exception` lại cho phép checked exception theo hợp đồng.

Không nên giải quyết bằng cách ném unchecked exception tùy tiện nếu có thể thiết kế interface đúng nhu cầu hoặc xử lý checked exception tại boundary.

### 10.4. Overload resolution là quá trình liên quan tới target typing

Khi một lambda được truyền làm argument của lời gọi overloaded, compiler phải xem xét các method ứng viên, kiểu tham số của chúng và tính phù hợp của lambda. Vì thế quá trình không đơn giản là “tính xong kiểu lambda trước rồi mới chọn method” hay “chọn method bằng tên trước rồi mới xem lambda”.

Trong thực tế, khi một lời gọi trở nên khó suy luận, khai báo một biến functional interface typed hoặc tách một generic call thành hai câu lệnh thường cải thiện cả thông báo compiler lẫn tính dễ đọc.

### 10.5. Primitive specialization có thể giúp tránh boxing

`Function<String,Integer>` trả Integer, nhưng `String.length()` trả int. Compiler có thể boxing int thành Integer. Nếu đường xử lý cường độ cao cần tối ưu hóa, có thể dùng `ToIntFunction<String>`:

```java
java.util.function.ToIntFunction<String> length = String::length;
int n = length.applyAsInt("Java");
```

Tương tự có `IntUnaryOperator`, `IntPredicate` và các interface chuyên biệt. Trước khi tối ưu hóa, kiểm tra yêu cầu hiệu năng thực tế; trong phần lớn code nghiệp vụ, dạng rõ ràng nhất là ưu tiên.

## 11. Checklist khi debug lỗi inference

Nếu compiler báo khó suy luận kiểu cho lambda hay method reference:

1. **Tìm target type.** Biến đích, kiểu tham số method, return type hay cast có cung cấp một functional interface không?
2. **Kiểm tra SAM.** Có đúng một phương thức chức năng với arity, parameter types, result và throws phù hợp không?
3. **Kiểm tra kiểu tham số lambda.** Nếu implicit, compiler đang suy luận gì từ SAM? Nếu explicit, khai báo có khớp SAM không?
4. **Tìm generic constraints.** Method nhận `Function<? super T,? extends R>` có những ràng buộc nào từ source, mapper và target kết quả?
5. **Xác định overload candidates.** Có nhiều SAM cùng hình dạng như Supplier/Callable không? Có method overloaded trùng tên trong method reference không?
6. **Thử biến trung gian typed.** Gán lambda/reference cho `Function<String,Integer>` hoặc `Supplier<String>` rồi truyền biến để giảm mơ hồ.
7. **Kiểm tra `var`.** Đừng dùng `var x = lambda` khi chưa có target. `(var x) -> ...` vẫn cần functional interface target.
8. **Đọc kỹ thông điệp và vị trí lỗi.** `cannot infer`, `incompatible parameter types`, `ambiguous reference` là các vấn đề khác nhau.
9. **Xem boxing và checked exceptions.** Kết quả int/Integer hoặc exception khai báo trong SAM có ảnh hưởng khả năng tương thích.
10. **Đơn giản hóa API trước khi cast hàng loạt.** Nếu người gọi phải dùng nhiều cast để chọn overload, cân nhắc đổi tên/thiết kế API.

## 12. Bảng tổng hợp: lambda hay method reference?

| Nhu cầu | Cách viết | Điều kiện cần hiểu |
| --- | --- | --- |
| Chuyển String thành độ dài | `s -> s.length()` | Cần target như Function<String,Integer>. |
| Viết gọn phép gọi receiver | `String::length` | Unbound instance; String làm đối số đầu. |
| Trim một chuỗi được truyền vào | `String::trim` | Target Function<String,String>. |
| So sánh với một giá trị cố định | `"An"::equals` | Bound receiver; target Predicate<String> chẳng hạn. |
| Parse số | `Integer::parseInt` | Static overloaded; target quyết định signature phù hợp. |
| Tạo danh sách mới | `ArrayList::new` | Constructor target Supplier hoặc Function tương ứng. |
| Tạo Member từ tên | `Member::new` | Constructor signature khớp String→Member. |
| Đọc tên của Member | `Member::name` | Unbound instance, receiver Member là tham số. |
| Chuyển generic T thành T | `ClassName::identity` | T suy luận theo target; có thể chỉ rõ type arguments. |
| Logic nhiều bước | `x -> { ...; return result; }` | Lambda có block body thường rõ hơn một method reference phức tạp. |
| Chọn overload bằng SAM rõ ràng | `(Supplier<String>) () -> "A"` | Cast chỉ để phân giải ambiguity, tránh lạm dụng. |

Method reference thường ngắn gọn khi hành vi **chính xác là một lời gọi có sẵn**. Lambda dễ đọc hơn khi có điều kiện, xử lý lỗi, nhiều bước, hoặc cần đổi dữ liệu đầu vào/đầu ra. Không có quy tắc rằng method reference luôn tốt hơn lambda.

## 13. Bài tập tự kiểm tra

### Bài 1

Vì sao dòng này không biên dịch?

```java
var length = s -> s.length();
```

**Đáp án:** Lambda cần target functional interface. `var` yêu cầu initializer có kiểu mà compiler suy luận trực tiếp được, nhưng lambda không có kiểu standalone phù hợp. Dùng `Function<String,Integer> length = s -> s.length();`.

### Bài 2

`Function<String,Integer> f = String::length;` có nghĩa gì?

**Đáp án:** Khi `f.apply(text)` được gọi, String đầu vào là receiver của `length()`. Kết quả int được boxing thành Integer theo target.

### Bài 3

`"pre-"::concat` là bound hay unbound instance reference?

**Đáp án:** Bound; receiver `"pre-"` đã biết, functional interface nhận phần chuỗi thêm vào. `Function<String,String>` là target thích hợp.

### Bài 4

Vì sao `ArrayList::new` có thể gán vào `Supplier<ArrayList<String>>`?

**Đáp án:** Supplier không nhận tham số và cần trả ArrayList<String>. Compiler chọn constructor không tham số của ArrayList phù hợp target.

### Bài 5

Vì sao `choose(() -> "ok")` mơ hồ nếu có hai overload nhận `Supplier<String>` và `Callable<String>`?

**Đáp án:** Cả hai interface có SAM không tham số trả String (Callable còn cho phép checked exception). Lambda phù hợp cả hai và không có ứng viên cụ thể hơn đủ để compiler chọn. Dùng typed Supplier variable hoặc cast.

### Bài 6

`BiFunction<String,String,String> f = (var a,b) -> a+b` có đúng không?

**Đáp án:** Không. Không được trộn tham số `var` với tham số implicit. Đổi thành `(var a,var b)` hoặc `(a,b)`.

### Bài 7

Vì sao `transform(List.of("A","Java"),String::length)` có thể tạo List Integer?

**Đáp án:** Compiler dùng type argument của source, target functional interface của mapper, kiểu trả về int của `length` và ngữ cảnh kết quả để suy luận T/R; int được boxing thành Integer.

### Bài 8

`Function<String,Integer> f = (Integer x) -> x + 1` bị lỗi ở đâu?

**Đáp án:** Kiểu tham số explicit Integer không tương thích String mà SAM yêu cầu. Compiler báo incompatible parameter types in lambda expression.

### Bài 9

Một static method overloaded `format(Object)` và `format(String)` có thể được tham chiếu qua `Function<String,String>` không?

**Đáp án:** Có trong ví dụ phần 7. Compiler chọn overload String phù hợp và cụ thể hơn; output `String:x`.

### Bài 10

Một lambda trong `Function<String,String>` có thể gọi method ném checked IOException chưa xử lý không?

**Đáp án:** Không nếu checked exception không được SAM khai báo/cho phép. Cần catch, chuyển đổi có kiểm soát, hoặc dùng functional interface khai báo throws tương thích.

### Bài 11

Vì sao `String::trim` không thể gán trực tiếp cho `var operation` nhưng có thể làm argument `transform(..., String::trim)`?

**Đáp án:** Ở phép gán `var` không có functional target type. Ở lời gọi `transform`, chữ ký generic của tham số mapper tạo target type cho method reference.

### Bài 12

Khi nào nên dùng `ToIntFunction<String>` thay `Function<String,Integer>`?

**Đáp án:** Khi cần xử lý int chuyên biệt, tránh boxing trong API, và có lý do về performance hay sự rõ ràng của kiểu primitive. Cả hai là hợp lệ cho `String::length` khi target tương ứng.

## 14. Tổng kết

**Suy luận kiểu của lambda và method reference là quá trình dựa vào ngữ cảnh đích.** Functional interface xác định kiểu tham số và kết quả; generic method thêm các quan hệ T/R; overload resolution quyết định phương thức nào có thể nhận biểu thức. Vì vậy cùng một lambda có thể hợp lệ hoặc không hợp lệ tùy nơi dùng, và cùng một method reference overloaded có thể được ràng buộc khác nhau theo target.

Hãy ưu tiên functional interface được khai báo rõ, generic signatures diễn đạt đúng quan hệ producer/consumer và các biến trung gian typed khi inference mơ hồ. Dùng `var` ở lambda parameters đúng cách nhưng đừng nhầm nó với việc không cần target. Khi method reference chỉ làm câu lệnh khó đọc hơn, viết một lambda rõ ràng là lựa chọn tốt.

**Ghi nhớ:** Trước khi hỏi “lambda này có kiểu gì?”, hãy hỏi **“compiler đang kiểm tra lambda này theo functional interface nào?”**.
