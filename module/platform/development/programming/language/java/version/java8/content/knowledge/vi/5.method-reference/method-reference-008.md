# Overload và trường hợp cần chỉ rõ kiểu đích trong method reference Java

## 1. Mục tiêu và ý tưởng cốt lõi

**Method reference** (`::`) được Java hỗ trợ từ Java 8 và vẫn dùng phổ biến trong Java hiện đại. Khi một class có **nhiều phương thức cùng tên** (overload), compiler phải chọn chính xác phương thức mà biểu thức như `Integer::parseInt`, `Math::max` hoặc `MyClass::convert` đại diện. Lựa chọn ấy thường phụ thuộc vào **kiểu đích** (*target type*) — tức functional interface tại nơi method reference được sử dụng.

Bài học giúp bạn:

- Phân biệt **overload của phương thức được tham chiếu** với **overload của phương thức nhận lambda/method reference**.
- Giải thích cách **functional interface và chữ ký SAM** cung cấp số lượng/kiểu tham số, kiểu kết quả và ràng buộc ngoại lệ để phân giải method reference.
- Viết cách làm rõ kiểu đích bằng **biến có kiểu tường minh**, **ép kiểu (cast) sang functional interface**, **lambda có tham số tường minh**, hoặc **type witness** khi phương thức generic cần chỉ rõ tham số kiểu.
- Nhận diện các lỗi `ambiguous`, `incompatible types` và `invalid method reference` mà không “sửa mò”.
- Giữ mã tương thích với baseline Java được yêu cầu, đồng thời sử dụng cú pháp và API còn hợp lệ trong JDK hiện hành.

**Nguyên tắc quan trọng nhất:** `SomeType::method` **không tự mang một functional interface cố định**. Method reference là một biểu thức được kiểm tra theo ngữ cảnh (*poly expression*). Cần biết kiểu đích trước khi xác định phương thức phù hợp.

## 2. Target type và chữ ký SAM quyết định điều gì?

Một method reference được gán, truyền làm đối số hoặc ép kiểu tới **functional interface**. Functional interface có một hợp đồng phương thức trừu tượng duy nhất — **SAM** (*single abstract method*). Chữ ký SAM cho compiler biết “hàm mà ta cần” nhận gì và trả về gì.

Ví dụ:

~~~java
import java.util.function.Function;
import java.util.function.BiFunction;

Function<String, Integer> decimal = Integer::parseInt;
BiFunction<String, Integer, Integer> radix = Integer::parseInt;
~~~

`Integer` có các overload:

~~~java
// Chữ ký API minh họa, không phải mã tự định nghĩa của bạn:
static int parseInt(String value);
static int parseInt(String value, int radix);
~~~

Với `Function<String,Integer>`, SAM `Integer apply(String)` tương ứng overload **một tham số**. Với `BiFunction<String,Integer,Integer>`, SAM `Integer apply(String,Integer)` tương ứng overload **hai tham số**, trong đó `Integer` thứ hai được unbox thành `int`; kết quả `int` được box thành `Integer`.

~~~java
int a = decimal.apply("42");     // 42
int b = radix.apply("ff", 16);    // 255
~~~

Đây không phải compiler “đoán xem tham số thứ hai có thích hợp hay không” lúc chạy. Việc chọn overload được kiểm tra **tại compile time**, căn cứ vào target type và các quy tắc overload của Java.

### Không phải mọi ngữ cảnh đều cung cấp target type

Hai dòng sau **không biên dịch**:

~~~java
// Không hợp lệ: Object không phải functional interface.
// Object f = Integer::parseInt;

// Không hợp lệ: kiểu của biến khai báo bằng var cần được suy ra
// từ biểu thức, nhưng method reference cần target type trước.
// var f = Integer::parseInt;
~~~

Cách đúng:

~~~java
Function<String, Integer> f = Integer::parseInt;
~~~

Nếu cần dùng `var` cho biến cục bộ trong Java 10+, có thể chỉ rõ kiểu bằng cast ngay tại biểu thức:

~~~java
var f = (Function<String, Integer>) Integer::parseInt;
~~~

Tuy nhiên, việc khai báo trực tiếp `Function<String,Integer> f` thường **dễ đọc hơn**. Cú pháp `var` của biến cục bộ bắt đầu từ Java 10; riêng method reference đã có từ Java 8. Không cần dùng `var` chỉ để rút ngắn code.

## 3. Overload của phương thức được tham chiếu: ví dụ đơn giản

Một class có thể định nghĩa:

~~~java
static String label(String value) {
    return "text:" + value;
}

static String label(Integer value) {
    return "number:" + value;
}
~~~

Cùng tên `label` nhưng hai chữ ký khác nhau. Giả sử class tên `LabelService`, những biểu thức có target type rõ ràng này hợp lệ:

~~~java
Function<String, String> textLabel = LabelService::label;
Function<Integer, String> numberLabel = LabelService::label;
~~~

Compiler phân giải `LabelService::label` lần đầu thành `label(String)`, lần sau thành `label(Integer)`. Cả hai đều trả về `String`, nhưng **kiểu tham số SAM khác nhau** giúp chọn overload thích hợp.

Việc thêm overload mới vào class có thể làm thay đổi hoặc khiến việc phân giải lời gọi cũ trở nên mơ hồ trong một số ngữ cảnh. Đây là lý do cần chạy compile/test khi thay đổi API overload, nhất là với các method reference trong mã người dùng.

### Phân giải không chỉ dựa vào tên hay kiểu trả về

Khi phân tích:

~~~java
Function<String, String> textLabel = LabelService::label;
~~~

Hãy hỏi lần lượt:

1. Functional interface mục tiêu là gì? `Function<String,String>`.
2. SAM sau khi thay generic là gì? `String apply(String)`.
3. `LabelService` có những `label` nào truy cập được?
4. Overload nào tương thích với số lượng và kiểu tham số?
5. Kiểu kết quả, checked exception, generic/boxing và các quy tắc khác có thỏa không?

**Không** thể phân biệt hai overload trong chính một class **chỉ bằng kiểu trả về** nếu danh sách tham số giống hệt nhau; Java không cho phép khai báo hai phương thức chỉ khác return type. Nhưng khi xét **phương thức đã chọn** có tương thích với SAM hay không, kiểu kết quả vẫn là một yếu tố kiểm tra quan trọng.

## 4. Overload của phương thức *nhận* functional interface: hai tầng lựa chọn

Đây là tình huống dễ nhầm nhất. Xét một API có hai overload **nhận các functional interface khác nhau**:

~~~java
@FunctionalInterface
interface TextRenderer {
    String render(String value);
}

@FunctionalInterface
interface NumberRenderer {
    String render(Integer value);
}

static void report(TextRenderer renderer) {
    System.out.println(renderer.render("Java"));
}

static void report(NumberRenderer renderer) {
    System.out.println(renderer.render(7));
}
~~~

Giả sử class còn có:

~~~java
static String label(String value) {
    return "text:" + value;
}

static String label(Integer value) {
    return "number:" + value;
}
~~~

Lời gọi:

~~~java
// Không hợp lệ: lời gọi report(...) có thể phù hợp cả
// report(TextRenderer) và report(NumberRenderer).
// report(MyClass::label);
~~~

Vấn đề không chỉ là chọn `label(String)` hay `label(Integer)`. Trước hết compiler phải chọn **`report(TextRenderer)` hay `report(NumberRenderer)`**. Cả hai đều là ứng viên, và không có cái nào đương nhiên cụ thể hơn cái kia. Biểu thức `MyClass::label` có nhiều overload nên **chưa có một đích xác định**; compiler không thể dùng nó để tự quyết định tùy ý một overload của `report`.

Đây là sự khác biệt giữa hai tình huống:

| Trường hợp | Thứ cần phân giải | Có thể dùng cách nào? |
| --- | --- | --- |
| `Function<String,String> f = MyClass::label` | Overload của `label` | Target type `Function<String,String>` đã rõ |
| `report(MyClass::label)` với hai `report` khác nhau | Overload của `report` **và** `label` | Chỉ rõ functional interface đích cho đối số |
| `someList.stream().map(MyClass::label)` | Overload của `label` trong ngữ cảnh `map` | Dựa vào element type và target type; nếu vẫn mơ hồ, chỉ rõ kiểu |
| `var f = MyClass::label` | Chưa có functional interface đích | Khai báo/cast thành functional interface cụ thể |

Lưu ý: không phải **mọi** lời gọi overload có lambda hoặc method reference đều mơ hồ. Java có những quy tắc chọn phương thức cụ thể hơn; chỉ trong trường hợp như ví dụ trên, các ứng viên vẫn không phân biệt được. Quy tắc đầy đủ được trình bày trong JLS `15.12.2 và `15.13.

## 5. Cách giải quyết 1: khai báo biến có kiểu rõ ràng

Đây thường là cách **rõ nhất và dễ bảo trì nhất**:

~~~java
TextRenderer textRenderer = MyClass::label;
NumberRenderer numberRenderer = MyClass::label;

report(textRenderer);
report(numberRenderer);
~~~

Ở phép gán đầu tiên, `TextRenderer` buộc tham số SAM là `String`; ở phép gán thứ hai, `NumberRenderer` buộc tham số là `Integer`. Sau đó `report(textRenderer)` và `report(numberRenderer)` đã có **kiểu đối số chính xác** để overload resolution làm việc.

Ưu điểm của biến trung gian:

- Kiểu đích hiện rõ ở khai báo và có thể đặt tên theo ý nghĩa nghiệp vụ.
- Dễ debug, đặt breakpoint ở nơi gọi SAM và chia nhỏ biểu thức dài.
- Không phải gắn cast khó đọc vào nhiều lời gọi.
- Giữ an toàn kiểu tĩnh; không có “ép kiểu không kiểm tra” hay điều phối động lúc chạy.

Dạng này phù hợp khi dùng một method reference nhiều lần hoặc khi API có nhiều overload cùng nhận callback.

## 6. Cách giải quyết 2: cast trực tiếp sang functional interface

Trong invocation context, một cast có thể tạo **kiểu đích cụ thể cho method reference**:

~~~java
report((TextRenderer) MyClass::label);
report((NumberRenderer) MyClass::label);
~~~

Điều này cũng hợp lệ trong các lời gọi nhận functional interface chuẩn:

~~~java
static void run(java.util.function.Function<String, Integer> parser) {
    System.out.println(parser.apply("123"));
}

run((java.util.function.Function<String, Integer>)
        Integer::parseInt);
~~~

Khi đã có kiểu đích rõ ràng, compiler biết method reference phải tương thích với SAM nào.

**Cast ở đây không phải thủ thuật chuyển giá trị runtime không an toàn.** Nó là **casting context** giúp compiler xác lập functional interface mục tiêu cho method reference. Một cast sang functional interface có chữ ký không tương thích vẫn **bị lỗi biên dịch**.

Ví dụ:

~~~java
// Sai vì Integer.parseInt(String) trả int/Integer, không
// tạo chuỗi String theo kiểu Function<String,String>.
// Function<String, String> wrong =
//         (Function<String, String>) Integer::parseInt;
~~~

**Chỉ cast khi cần.** Nếu `report` không overload, hoặc target type đã rõ, cast thêm có thể làm rối biểu thức hơn mà không tăng tính an toàn.

## 7. Cách giải quyết 3: lambda ghi rõ kiểu tham số

Một lựa chọn khác là viết lambda tường minh thay cho method reference:

~~~java
report((String value) -> label(value));
report((Integer value) -> label(value));
~~~

Khai báo `(String value)` cho phép compiler thấy function descriptor phù hợp với `TextRenderer`, không phù hợp với `NumberRenderer`; tương tự với `(Integer value)`. Bên trong lambda, lời gọi `label(value)` cũng có tham số kiểu cụ thể để chọn overload.

Cách này đặc biệt hữu ích khi bạn:

- Cần **chuẩn hóa**, **validate** hoặc **biến đổi tham số** trước khi gọi phương thức.
- Muốn **bắt exception** hoặc thêm điều kiện xử lý rõ ràng.
- Muốn làm nổi bật cách overload được chọn mà không tạo biến trung gian.

Ví dụ:

~~~java
java.util.function.Function<String, Integer> trimmedParser =
        (String text) -> Integer.parseInt(text.strip());
~~~

Dòng trên **không tương đương** với `Integer::parseInt` cho mọi đầu vào: với `" 42 "`, `strip` loại khoảng trắng trước khi parse. `String.strip()` có từ Java 11; khi cần Java 8, phải chọn API và hợp đồng khoảng trắng phù hợp. Không được thay lambda đang thực hiện thêm công việc bằng method reference rồi mặc định hành vi không đổi.

**Không phải mọi overload ambiguity đều được giải quyết bằng cách ghi kiểu tham số.** Một lambda có thể vẫn phù hợp với nhiều overload nhận SAM trùng chức năng; khi đó biến typed hoặc cast sang một interface cụ thể thường rõ ràng và đáng tin cậy hơn.

## 8. Ví dụ Java 17+ độc lập: lỗi mơ hồ và ba cách làm rõ đích

Lưu chương trình dưới tên **`MethodReferenceOverloadDemo.java`**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.IntFunction;
import java.util.function.LongBinaryOperator;

public class MethodReferenceOverloadDemo {

    @FunctionalInterface
    interface TextRenderer {
        String render(String value);
    }

    @FunctionalInterface
    interface NumberRenderer {
        String render(Integer value);
    }

    static String label(String value) {
        return "text:" + value;
    }

    static String label(Integer value) {
        return "number:" + value;
    }

    static void report(TextRenderer renderer) {
        System.out.println("text-target=" + renderer.render("Java"));
    }

    static void report(NumberRenderer renderer) {
        System.out.println("number-target=" + renderer.render(7));
    }

    static <T> T echo(T value) {
        return value;
    }

    public static void main(String[] args) {
        // Target type chọn overload của label.
        Function<String, String> text =
                MethodReferenceOverloadDemo::label;
        Function<Integer, String> number =
                MethodReferenceOverloadDemo::label;

        System.out.println("text=" + text.apply("Java"));
        System.out.println("number=" + number.apply(7));

        // Cách 1: biến functional interface có kiểu rõ.
        TextRenderer textRenderer =
                MethodReferenceOverloadDemo::label;
        NumberRenderer numberRenderer =
                MethodReferenceOverloadDemo::label;

        report(textRenderer);
        report(numberRenderer);

        // Cách 2: cast tại vị trí truyền vào overload.
        report((TextRenderer) MethodReferenceOverloadDemo::label);
        report((NumberRenderer) MethodReferenceOverloadDemo::label);

        // Cách 3: lambda có tham số tường minh.
        report((String value) -> label(value));
        report((Integer value) -> label(value));

        // Cùng tên parseInt nhưng hai overload khác số tham số.
        Function<String, Integer> decimal = Integer::parseInt;
        BiFunction<String, Integer, Integer> radix = Integer::parseInt;

        System.out.println("decimal=" + decimal.apply("42"));
        System.out.println("radix=" + radix.apply("ff", 16));

        // Cùng tên max nhưng target primitive khác nhau.
        IntBinaryOperator intMax = Math::max;
        LongBinaryOperator longMax = Math::max;
        System.out.println("int-max=" + intMax.applyAsInt(4, 9));
        System.out.println("long-max=" + longMax.applyAsLong(5L, 3L));

        // Generic method với type witness rõ ràng.
        Function<String, String> same =
                MethodReferenceOverloadDemo::<String>echo;
        System.out.println("echo=" + same.apply("ok"));

        // Instance method reference: receiver là tham số đầu.
        BiFunction<String, Integer, String> substring =
                String::substring;
        System.out.println("substring=" +
                substring.apply("lambda", 2));

        // Instance method reference với receiver gắn sẵn.
        IntFunction<String> suffix = "reference"::substring;
        System.out.println("suffix=" + suffix.apply(3));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 MethodReferenceOverloadDemo.java
java MethodReferenceOverloadDemo
~~~

**Stdout chính xác:**

~~~text
text=text:Java
number=number:7
text-target=text:Java
number-target=number:7
text-target=text:Java
number-target=number:7
text-target=text:Java
number-target=number:7
decimal=42
radix=255
int-max=9
long-max=5
echo=ok
substring=mbda
suffix=erence
~~~

Chương trình dùng các cú pháp và API cốt lõi có từ Java 8. Việc chọn JDK 17+ là để sử dụng môi trường học tập/biên dịch hiện đại, không khuyến nghị triển khai ứng dụng mới trên một runtime Java 8 đã cũ.

### Những dòng không hợp lệ — *không* đặt vào chương trình chạy

Các đoạn sau là **minh họa lỗi biên dịch có chủ đích**:

~~~java
// 1) Thiếu target type:
// var f = MethodReferenceOverloadDemo::label;

// 2) Object không có SAM:
// Object f = MethodReferenceOverloadDemo::label;

// 3) Hai overload report đều có thể nhận một form label phù hợp:
// report(MethodReferenceOverloadDemo::label);

// 4) Không có overload label(Object), vì Object không thể tự
// biến thành String/Integer trong vị trí tham số:
// Function<Object, String> impossible =
//         MethodReferenceOverloadDemo::label;
~~~

Không cần biết chính xác câu chữ của thông báo `javac` theo từng phiên bản. Hãy đọc **ứng viên nào compiler cho là phù hợp**, sau đó chỉ rõ target type ở điểm sử dụng.

## 9. Overload theo số lượng và kiểu tham số

Bảng sau minh họa cách compiler lựa chọn overload:

| Method reference | Kiểu đích | Overload được sử dụng |
| --- | --- | --- |
| `Integer::parseInt` | `Function<String,Integer>` | `parseInt(String)` |
| `Integer::parseInt` | `BiFunction<String,Integer,Integer>` | `parseInt(String,int)` |
| `Math::max` | `IntBinaryOperator` | `max(int,int)` |
| `Math::max` | `LongBinaryOperator` | `max(long,long)` |
| `Math::max` | `DoubleBinaryOperator` | `max(double,double)` |
| `String::substring` | `BiFunction<String,Integer,String>` | Instance `substring(int)`, với `String` nhận từ tham số đầu |
| `"abc"::substring` | `IntFunction<String>` | Instance `substring(int)` trên receiver `"abc"` đã cố định |

Điều cần ghi nhớ:

- **Số lượng tham số** có thể loại bỏ một số overload.
- **Kiểu tham số SAM** giúp tìm những overload áp dụng được, kể cả các chuyển đổi kiểu hợp lệ.
- **Kiểu kết quả** phải tương thích với SAM sau khi phương thức được lựa chọn; không dùng return type như một phép suy đoán vô hạn cho mọi tình huống quá tải.
- Với dạng `TypeName::instanceMethod`, compiler có thể coi **tham số đầu tiên của SAM là receiver**. Vì vậy đừng thấy `String::substring` rồi kết luận là static.
- **Có cùng số tham số** chưa chắc gây lỗi; Java có quy tắc tìm overload *most specific*. Ngược lại, **khác số tham số** là một cách phân biệt dễ thấy nhưng không phải toàn bộ thuật toán.

## 10. Phân biệt hai kiểu overload khi điều tra lỗi

### A. Overload *trong class được tham chiếu*

~~~java
Function<String, Integer> parser = Integer::parseInt;
BiFunction<String, Integer, Integer> parserWithRadix =
        Integer::parseInt;
~~~

Cả hai **biên dịch được** vì target types rõ ràng, dù `parseInt` là tên quá tải. Giải pháp thông thường: khai báo `Function` hoặc `BiFunction` chính xác.

### B. Overload *của phương thức chứa lời gọi*

~~~java
// Giả định cùng phạm vi có:
// void handle(TextRenderer r);
// void handle(NumberRenderer r);

// Có thể mơ hồ, do hai handle không có quan hệ subtype.
// handle(MyClass::label);

// Làm rõ:
// handle((TextRenderer) MyClass::label);
~~~

Giải pháp thông thường: cast đối số reference, biến typed hoặc lambda có tham số tường minh. Nếu API do bạn sở hữu có nhiều overload nhận các SAM không liên quan và người gọi thường xuyên bị mơ hồ, cân nhắc **đặt tên phương thức khác nhau** như `handleText` / `handleNumber`. API dễ sử dụng đáng giá hơn việc cố tạo nhiều overload khó đoán.

### C. Có cả overload ở hai tầng

Trong trường hợp `report(MethodReferenceOverloadDemo::label)`, cả `report` lẫn `label` đều overload. Đây là tình huống mà việc tách một biến typed giúp diễn đạt rõ ý định:

~~~java
TextRenderer forText =
        MethodReferenceOverloadDemo::label;

report(forText);
~~~

Compiler giờ không phải giải quyết **hai tầng lựa chọn phụ thuộc nhau** trong cùng một biểu thức.

## 11. Exact và inexact method reference: tại sao một số lỗi khó hiểu?

Theo Java Language Specification, có sự phân biệt giữa **exact method reference** và **inexact method reference**:

- Một reference có **một phương thức đích duy nhất được xác định độc lập với target function type** trong các điều kiện đặc tả nhất định có thể là *exact*.
- Reference có **nhiều overload tên giống nhau**, method generic chưa được chốt type arguments, varargs hoặc một số yếu tố khác thường thuộc loại *inexact*.
- Với một lời gọi phương thức đang được overload, **inexact method reference có thể chưa được dùng để xét tính áp dụng của overload nhận nó** ở giai đoạn đầu. Compiler cần quyết định target type trước mới phân tích đầy đủ reference.

Đó là nguyên nhân sâu hơn của ví dụ:

~~~java
// report(...) overloaded theo TextRenderer và NumberRenderer.
// label(...) overloaded theo String và Integer.
// report(MethodReferenceOverloadDemo::label); // mơ hồ
~~~

**Không nên dùng phân loại exact/inexact như mẹo để đoán bừa kết quả.** Quy tắc thực tế vẫn là xem JLS `15.12.2.2 (pertinent to applicability), `15.12.2.5 (most specific) và `15.13.1 (compile-time declaration of a method reference). Trong code ứng dụng, thêm một target type rõ ràng thường tốt hơn dựa vào những góc cạnh khó đọc của overload resolution.

### Explicit lambda đôi khi cung cấp nhiều thông tin hơn

Ví dụ:

~~~java
report((String value) -> label(value));
~~~

Tham số `String` được ghi tường minh, nên có thể loại target `NumberRenderer` với tham số `Integer`. Nhưng lambda `value -> label(value)` **không ghi kiểu** thì vẫn có thể để compiler trước hai target types tương đương về hình dạng. Ghi kiểu hoặc cast cần được lựa chọn dựa trên **chữ ký SAM thực tế**, không phải theo cảm giác.

## 12. Generic method references và type witness

Method reference tới **phương thức generic** thường suy ra tham số kiểu từ target type:

~~~java
static <T> T echo(T value) {
    return value;
}

// Giả định code nằm trong class MyClass.
Function<String, String> a = MyClass::echo;
Function<Integer, Integer> b = MyClass::echo;
~~~

Nếu muốn khai báo type arguments rõ ràng, Java hỗ trợ **type witness sau `::`**:

~~~java
Function<String, String> explicit =
        MyClass::<String>echo;
~~~

Chú ý thứ tự cú pháp: **`MyClass::<String>echo`** chứ không phải `MyClass<String>::echo` cho một static method generic trên class không-generic.

Một ví dụ thư viện chuẩn:

~~~java
java.util.function.Supplier<java.util.List<String>> strings =
        java.util.Collections::<String>emptyList;
~~~

`Collections.emptyList()` là generic static factory có từ lâu và vẫn tồn tại trong Java hiện đại. Compiler cũng có thể suy luận `String` từ `Supplier<List<String>>` nếu viết `Collections::emptyList`.

**Type witness không đồng nghĩa cast functional interface.**

| Kỹ thuật | Làm rõ điều gì? |
| --- | --- |
| `Function<String,String> f = MyClass::echo` | Functional interface và SAM mục tiêu |
| `MyClass::<String>echo` | Tham số kiểu `T` của phương thức generic |
| `(Function<String,String>) MyClass::echo` | Functional interface mục tiêu tại casting context |
| `(String x) -> MyClass.echo(x)` | Kiểu tham số lambda và cách gọi bên trong |

Type witness giúp một số bài toán inference nhưng **không tự chữa mọi overload ambiguity ở tầng phương thức nhận callback**. Nếu lời gọi vẫn có nhiều overload nhận các SAM không liên quan, bạn vẫn cần chỉ rõ **kiểu đích**.

## 13. Constructor references cũng có overload

Constructor reference như `ArrayList<String>::new` dùng `new` thay tên phương thức, nhưng **constructor có thể overload**:

~~~java
java.util.function.Supplier<java.util.ArrayList<String>> empty =
        java.util.ArrayList<String>::new;

java.util.function.IntFunction<java.util.ArrayList<String>> sized =
        java.util.ArrayList<String>::new;
~~~

- `Supplier<ArrayList<String>>` có SAM `ArrayList<String> get()`, phù hợp constructor không tham số.
- `IntFunction<ArrayList<String>>` có SAM `ArrayList<String> apply(int size)`, phù hợp constructor nhận capacity `int`.

~~~java
java.util.ArrayList<String> a = empty.get();
java.util.ArrayList<String> b = sized.apply(10);
~~~

Cả hai tạo danh sách rỗng có thể sửa được; `sized.apply(10)` chỉ thiết lập **dung lượng nội bộ ban đầu** chứ không làm danh sách có 10 phần tử. Vì thế cả `a.size()` và `b.size()` bằng `0`.

Ở đây target typing cũng giúp chọn constructor phù hợp, nhưng bài học trọng tâm vẫn là **phương thức bị overload** và trường hợp cần chỉ rõ interface đích.

## 14. Checked exceptions, boxing và tính tương thích kết quả

Một reference chỉ hợp lệ khi hợp đồng phương thức được chọn tương thích với **SAM**:

### Boxing/unboxing

~~~java
java.util.function.BinaryOperator<Integer> boxedSum =
        Integer::sum;

java.util.function.IntBinaryOperator primitiveSum =
        Integer::sum;
~~~

`Integer.sum(int,int)` nhận/trả `int`; với `BinaryOperator<Integer>` compiler áp dụng unboxing/boxing thích hợp. Với `IntBinaryOperator`, các tham số/kết quả SAM đều là `int`. Hai functional interfaces không giống nhau về hiệu quả boxing, dù cùng phép toán.

### Checked exception

Giả sử:

~~~java
static String readFile(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

`Files.readString(Path)` có từ Java 11. Lời gán sau **không hợp lệ**:

~~~java
// Function.apply không khai báo IOException.
// Function<java.nio.file.Path, String> reader = MyClass::readFile;
~~~

Giải pháp khi thực sự cần hợp đồng cho phép checked exception:

~~~java
@FunctionalInterface
interface ThrowingReader {
    String read(java.nio.file.Path path) throws java.io.IOException;
}

// Hợp lệ nếu MyClass có readFile như trên:
ThrowingReader reader = MyClass::readFile;
~~~

Đây là các **đoạn minh họa**, không phải tệp standalone. Dấu `::` không tự bắt exception. Cần phân biệt lỗi *checked exception không tương thích* với *overload ambiguous*, vì cách sửa khác nhau.

### Kiểu kết quả

`Function<String,Integer> f = Integer::parseInt` hợp lệ (boxing). Ngược lại:

~~~java
// Không hợp lệ: SAM cần String, parseInt trả int.
// Function<String, String> bad = Integer::parseInt;
~~~

Không nên cố dùng cast runtime để biến `int` thành `String`. Cần viết một phép biến đổi rõ ràng nếu nghiệp vụ cần:

~~~java
Function<String, String> canonical =
        s -> Integer.toString(Integer.parseInt(s));
~~~

Compiler chọn overload của `Integer.parseInt` nhờ kiểu `String` của `s`; sau đó kết quả được chuyển thành chuỗi. Đây là **logic mới**, không phải static method reference thuần túy.

## 15. Method reference với instance method overload

Không phải chỉ static method có overload. `String.substring` có cả `substring(int)` và `substring(int,int)`, trong khi cú pháp `String::substring` là **unbound instance method reference**.

Ví dụ:

~~~java
java.util.function.BiFunction<String, Integer, String> oneIndex =
        String::substring;

// oneIndex.apply("lambda", 2) -> "mbda"
~~~

Tham số `String` đầu tiên của SAM làm **receiver**, tham số `Integer` thứ hai làm chỉ số `beginIndex` sau unboxing. Nếu cần tham chiếu hai chỉ số, Java không có sẵn `TriFunction` trong `java.util.function`, nhưng có thể khai báo functional interface của riêng bạn:

~~~java
@FunctionalInterface
interface Substring3 {
    String slice(String source, int begin, int end);
}

Substring3 range = String::substring;
// range.slice("lambda", 1, 4) -> "amb"
~~~

Đây là **mã minh họa** đặt trong một class/phương thức phù hợp. SAM với ba tham số sẽ tương ứng receiver `source` và hai tham số của overload `substring(int,int)`.

Với receiver **đã gắn sẵn**:

~~~java
java.util.function.IntFunction<String> suffix =
        "reference"::substring;

// suffix.apply(3) -> "erence"
~~~

Ở đây `IntFunction<String>` nhận một tham số `int`; receiver cố định là chuỗi `"reference"`. Khi phương thức instance overload, **target type vẫn quan trọng**, nhưng cách đếm tham số phải xét **receiver đã hay chưa được cung cấp**.

## 16. Thiết kế API để giảm ambiguity

Khi bạn sở hữu API, đừng chỉ phụ thuộc vào việc người dùng “biết cách cast”. Một số lựa chọn thiết kế dễ dùng hơn:

- Chọn tên mô tả rõ trách nhiệm như `renderText` và `renderNumber` thay vì cùng `report` nhận hai SAM không liên quan.
- Dùng một functional interface với generic rõ nghĩa khi có chung một hợp đồng thực sự, thay vì tạo nhiều overload chỉ khác tên callback.
- Tránh tổ hợp “overload nhận functional interface” + “overload của method reference” nếu phần lớn caller sẽ dùng `::`.
- Khi cung cấp factory method nhận lambda, viết Javadoc nêu chính xác functional interface mục tiêu và những ràng buộc hành vi.
- Chạy compile tests trên các mẫu sử dụng phổ biến khi thêm overload mới; việc bổ sung overload có thể gây lỗi nguồn (*source compatibility*) ngay cả khi các phương thức cũ vẫn còn.

Ngược lại, nếu bạn chỉ là người **sử dụng** API bên ngoài, cách dễ hiểu nhất thường là **khai báo biến typed** hoặc **cast trực tiếp tại nơi gây mơ hồ**. Không thay đổi API của bên thứ ba chỉ để che một lỗi compiler có thể giải quyết rõ ràng bằng typing.

## 17. Quy trình chẩn đoán lỗi javac

Khi gặp thông báo `reference to ... is ambiguous` hoặc `invalid method reference`, đi qua checklist:

1. **Ghi chính xác dòng lỗi**: phương thức bị overload là phương thức **được tham chiếu** hay phương thức **đang được gọi**?
2. **Liệt kê các overload ứng viên** trong class liên quan, gồm số/kiểu tham số, modifiers, generic và khả năng truy cập.
3. **Xác định target type** tại vị trí method reference. Nếu là `var` hay `Object`, trước hết thay bằng functional interface cụ thể.
4. **Xem chữ ký SAM** sau khi gắn generic; với `TypeName::instanceMethod` nhớ có thể cần một tham số receiver ở đầu.
5. **Kiểm tra result/throws/boxing** và các chuyển đổi kiểu thực sự được Java cho phép.
6. **Nếu phương thức nhận callback overload**, thử viết biến typed `MyInterface f = Type::method` rồi truyền `f`.
7. Nếu cần, viết cast `(MyInterface) Type::method` hoặc lambda có tham số rõ kiểu.
8. Với phương thức generic, cân nhắc `Type::<ConcreteType>method` khi compiler không suy ra đúng điều mong đợi.
9. **Biên dịch bằng mức `--release` thực sự của dự án**, không dựa vào một API chỉ có trên JDK mới hơn.
10. **Thử nghiệm hành vi** sau khi sửa lỗi compile; một cast chọn được overload nhưng **chọn nhầm nghĩa nghiệp vụ** vẫn là bug.

**Không nên “chữa” lỗi bằng raw type**, bỏ hết generic hoặc thêm ép kiểu sang `Object`. Những thay đổi đó thường làm mất kiểm tra kiểu và không giải quyết nguyên nhân thiếu target type.

## 18. Bài tập tự kiểm tra

**Bài 1.** Cho `Integer::parseInt`, viết hai khai báo: một bằng `Function<String,Integer>`, một bằng `BiFunction<String,Integer,Integer>`. Dự đoán kết quả với `"100"` và với `("100", 2)`.

**Bài 2.** Cho hai overload `label(String)`/`label(Integer)`, giải thích tại sao:

~~~java
Function<String, String> f = MyClass::label;
Function<Integer, String> g = MyClass::label;
~~~

có thể hợp lệ, nhưng lời gọi `report(MyClass::label)` có thể mơ hồ nếu `report` cũng có hai overload nhận `TextRenderer` và `NumberRenderer`.

**Bài 3.** Sửa lời gọi mơ hồ bằng **ba cách**: biến typed, cast đến `TextRenderer` và lambda `(String x) -> label(x)`. So sánh độ dễ đọc.

**Bài 4.** Vì sao `var f = Math::max;` không biên dịch? Viết cách thay thế bằng `IntBinaryOperator` và `LongBinaryOperator`, rồi giải thích overload nào được chọn.

**Bài 5.** Viết `Function<String,String> f = MyClass::<String>echo;` khi `echo` là phương thức generic. Type witness có giải quyết được mọi overload của phương thức nhận callback hay không?

**Bài 6.** Với `String::substring`, viết `BiFunction<String,Integer,String>` và một functional interface riêng cho bản có hai chỉ số. Giải thích vai trò receiver.

**Bài 7.** Nếu một method reference tới phương thức static ném `IOException`, vì sao không thể gán trực tiếp vào `Function<Path,String>`? Hãy thiết kế một SAM có `throws IOException` phù hợp.

**Bài 8.** Nếu `ArrayList<String>::new` được gán vào `IntFunction<ArrayList<String>>`, tham số `int` tương ứng điều gì? Danh sách mới có bao nhiêu phần tử khi gọi `apply(10)`?

## 19. Tổng kết

- Method reference **phụ thuộc target type**. Overload của phương thức được tham chiếu thường được chọn dựa trên **SAM của functional interface**.
- Khi **chính phương thức nhận callback cũng overload**, có thể xảy ra mơ hồ; compiler không nhất thiết có thể suy ra cả hai tầng lựa chọn đồng thời.
- Cách làm rõ an toàn gồm **biến có functional interface cụ thể**, **cast sang functional interface**, **lambda ghi rõ kiểu tham số**, và **type witness** khi cần cung cấp type arguments cho phương thức generic.
- Các quy tắc **most specific, exact/inexact method reference, boxing, checked exception, receiver instance và generic** giải thích vì sao một số ví dụ có vẻ tương tự lại biên dịch khác nhau.
- **Không phải mọi overload đều mơ hồ**; cũng không phải mọi method reference chuyển thành lambda đều giữ nguyên hành vi trong mọi ngữ cảnh. Lựa chọn cuối cùng cần đúng *cả kiểu lẫn nghiệp vụ*.
- Các cơ chế này có từ Java 8 và vẫn được dùng trong Java hiện hành. Nên đọc đặc tả và Javadoc tương ứng với JDK mục tiêu thay vì áp dụng các giả định lỗi thời.

## 20. Tài liệu chính thức

1. Java Language Specification (Java SE 26), **`15.13 Method Reference Expressions**, `15.13.1 và `15.13.2: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.13
2. Java Language Specification (Java SE 26), **`15.12.2 Method Invocation — Overload Resolution**, gồm `15.12.2.2 và `15.12.2.5: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.12.2
3. Java Language Specification (Java SE 26), **`18.5 Type Inference**: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-18.html
4. Java SE 17 API, **Integer.parseInt**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html
5. Java SE 17 API, **Math.max**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
6. Java SE 17 API, **java.util.function**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html
7. Java SE 17 API, **ArrayList**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html

Để xử lý lỗi trong mã thực tế, hãy bắt đầu với **functional interface cần nhận hành vi**; từ đó xác định chữ ký SAM và chỉ rõ kiểu đích ở nơi cần thiết. Đây là phương pháp vẫn hữu ích trên các phiên bản Java hiện nay.