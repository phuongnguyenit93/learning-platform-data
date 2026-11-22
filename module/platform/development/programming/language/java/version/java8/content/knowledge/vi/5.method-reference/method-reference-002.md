# Tham chiếu phương thức static (static method reference) trong Java

## Mục tiêu học tập

**Static method reference** là cú pháp `TênKiểu::tênPhươngThứcStatic`, được hỗ trợ từ **Java 8** và vẫn là một phần quan trọng của Java hiện đại. Nó cho phép dùng **một phương thức `static` đã tồn tại** làm cách triển khai phương thức trừu tượng duy nhất (SAM) của một functional interface, thay vì viết một lambda chỉ để chuyển tiếp tham số.

Học xong, bạn có thể:

- Nhận diện và viết đúng `TypeName::staticMethodName`.
- Giải thích **target typing**: functional interface xác định chữ ký được mong đợi; compiler chọn phương thức static phù hợp.
- Đổi qua lại giữa lambda chuyển tiếp và static method reference khi **thực sự tương đương**.
- Sử dụng tham chiếu tới `Integer.parseInt`, `Integer.sum`, `Math.max`, `Objects.nonNull`, phương thức static do chính mình định nghĩa trong `map`, `filter`, `reduce` và các API khác.
- Xử lý overload, generics, boxing/unboxing, checked exception, `null` và lỗi phân giải phương thức.
- Phân biệt static method reference với bound instance, unbound instance và constructor reference; tránh nhầm dấu `::` là một lệnh gọi ngay lập tức.

## 1. Cú pháp và ý nghĩa cơ bản

Cú pháp:

~~~java
TypeName::staticMethodName
~~~

Ví dụ:

~~~java
java.util.function.Function<String, Integer> parser =
        Integer::parseInt;

int number = parser.apply("42"); // 42
~~~

`Integer.parseInt(String)` là phương thức static nhận `String`, trả về `int`. Biểu thức tham chiếu `Integer::parseInt` được sử dụng ở vị trí cần `Function<String,Integer>`, có SAM `Integer apply(String)`. Compiler chọn overload phù hợp và áp dụng boxing cho kết quả `int` thành `Integer` khi cần.

Bản lambda chuyển tiếp tương ứng:

~~~java
java.util.function.Function<String, Integer> parser =
        text -> Integer.parseInt(text);
~~~

**Cả hai cách đều nêu cùng hành vi gọi phương thức static `parseInt`** trong ngữ cảnh này. Method reference thường gọn hơn khi lambda chỉ gọi đúng một phương thức với tham số được chuyển tiếp.

Cần phân biệt:

- `Integer.parseInt("42")` là **lời gọi phương thức ngay tại vị trí biểu thức** và cho kết quả `int`.
- `Integer::parseInt` là **method reference expression**, được chuyển thành đối tượng của functional interface mục tiêu; lời gọi tới `parseInt` xảy ra khi SAM được thực thi (ví dụ `parser.apply("42")`).
- Không thể dùng `Integer::parseInt` làm một giá trị độc lập không có **target type** thích hợp; method reference là một **poly expression** được xác định kiểu theo ngữ cảnh.

### Ví dụ so sánh gọi ngay và tham chiếu

~~~java
int direct = Integer.parseInt("7");

java.util.function.Function<String, Integer> deferred =
        Integer::parseInt;

int viaFunction = deferred.apply("7");
~~~

`direct` và `viaFunction` cùng bằng `7`. Khác biệt là biến `deferred` **nắm giữ hành vi có thể gọi về sau**; nó không mang kết quả `7` ngay lúc được khởi tạo.

## 2. Functional interface cung cấp target type

Java không thể suy ra phương thức chính xác chỉ từ chuỗi ký tự `Integer::parseInt`, vì `parseInt` có nhiều overload và vì một method reference có thể được dùng trong nhiều ngữ cảnh.

Compiler nhìn vào **functional interface ở vị trí đích**:

| Target type | Chữ ký SAM | Tham chiếu static phù hợp |
| --- | --- | --- |
| `Function<String,Integer>` | `Integer apply(String)` | `Integer::parseInt` |
| `ToIntFunction<String>` | `int applyAsInt(String)` | `Integer::parseInt` |
| `BiFunction<String,Integer,Integer>` | `Integer apply(String,Integer)` | `Integer::parseInt`, dùng overload có `radix` |
| `IntBinaryOperator` | `int applyAsInt(int,int)` | `Math::max` |
| `BinaryOperator<Integer>` | `Integer apply(Integer,Integer)` | `Integer::sum` |
| `Predicate<Object>` | `boolean test(Object)` | `Objects::nonNull` |
| `Comparator<Integer>` | `int compare(Integer,Integer)` | `Integer::compare` (unboxing) |

Những ví dụ trong bảng đều dựa trên API Java SE ổn định, còn dùng được trong Java hiện đại. Chúng minh họa điểm quan trọng: **một tên phương thức static có thể tương thích với các functional interface khác nhau**, tùy chữ ký, chuyển đổi kiểu hợp lệ và overload được chọn.

Ví dụ:

~~~java
java.util.function.ToIntFunction<String> count =
        Integer::parseInt;

java.util.function.BiFunction<String, Integer, Integer> parseRadix =
        Integer::parseInt;

// count.applyAsInt("123") == 123
// parseRadix.apply("ff", 16) == 255
~~~

Tham chiếu thứ nhất dùng `parseInt(String)`; tham chiếu thứ hai dùng `parseInt(String,int)`. Đặc tả Java xét kiểu tham số/kết quả của functional interface, số lượng tham số, overload resolution và các chuyển đổi được phép. **Không** có quy tắc “cứ cùng tên phương thức thì compiler tự chọn đại một overload”.

## 3. Dùng phương thức static tự định nghĩa

Static method reference không bị giới hạn ở lớp thư viện. Bạn có thể tham chiếu phương thức static của class đang viết, nếu quyền truy cập và chữ ký tương thích:

~~~java
import java.util.function.Function;
import java.util.function.Predicate;

class Helpers {
    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String wrap(String value) {
        return "[" + value + "]";
    }
}

class Usage {
    Predicate<String> valid = Helpers::hasText;
    Function<String, String> display = Helpers::wrap;
}
~~~

Đoạn này là **minh họa các lớp và trường**, không phải chương trình có `main` để chạy độc lập. Cả hai method references đều tham chiếu phương thức `static`:

- `Helpers::hasText` phù hợp `Predicate<String>` với SAM `boolean test(String)`.
- `Helpers::wrap` phù hợp `Function<String,String>` với SAM `String apply(String)`.

`String.isBlank()` có từ **Java 11** và đang được sử dụng trong Java hiện đại. Nếu cần biên dịch với `--release 8`, phải đổi cách kiểm tra khoảng trắng cho phù hợp yêu cầu của chương trình; bản thân cú pháp static method reference vẫn dùng được.

Một tham chiếu tới `private static` method cũng hợp lệ khi được viết trong phạm vi có quyền truy cập, chẳng hạn bên trong chính class định nghĩa phương thức. **Quy tắc truy cập `private`/`public`/package-private vẫn có hiệu lực**; dấu `::` không bỏ qua access control.

## 4. Vì sao static method reference có ích?

Với các đoạn xử lý chuỗi, chuyển đổi số hoặc xử lý collection, một lambda kiểu “nhận tham số rồi chuyển tiếp nguyên vẹn vào static method” có thể làm code dài mà không thêm thông tin.

So sánh:

~~~java
java.util.List<String> raw =
        java.util.Arrays.asList("10", "20", "30");

java.util.List<Integer> byLambda =
        raw.stream()
           .map(text -> Integer.parseInt(text))
           .collect(java.util.stream.Collectors.toList());

java.util.List<Integer> byReference =
        raw.stream()
           .map(Integer::parseInt)
           .collect(java.util.stream.Collectors.toList());
~~~

Hai pipeline tạo danh sách `[10, 20, 30]` với cùng đầu vào. Trong `Stream<String>.map(...)`, target type tương ứng `Function<? super String,? extends Integer>`, nên compiler chọn overload `parseInt(String)` và boxing kết quả.

Lợi ích chính:

1. **Gọn và diễn đạt trực tiếp ý định**: “biến chuỗi thành số bằng `Integer.parseInt`”.
2. **Tái sử dụng hành vi đã đặt tên** thay vì mô tả lại phép gọi.
3. **Dễ đọc trong các pipeline** khi tên phương thức rõ nghĩa.
4. **Được kiểm tra kiểu tại compile time**, như lambda.

Không nên mặc định method reference **nhanh hơn** lambda hoặc chắc chắn tạo ít đối tượng hơn. JVM có nhiều chiến lược tối ưu, và hiệu năng thực tế cần đo trong ngữ cảnh cụ thể. Khi lambda có thêm kiểm tra, biến đổi tham số, ghi log hoặc xử lý ngoại lệ, viết lambda có thể **rõ hơn và đúng hơn** so với cố rút gọn thành `::`.

## 5. Ví dụ độc lập Java 17+: tham chiếu static trong ứng dụng thực tế

Lưu nguyên chương trình sau thành **`StaticMethodReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class StaticMethodReferenceDemo {

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String label(int number) {
        return "N=" + number;
    }

    static void printMessage(String message) {
        System.out.println("message=" + message);
    }

    public static void main(String[] args) {
        Function<String, Integer> parse = Integer::parseInt;
        BiFunction<String, Integer, Integer> parseRadix =
                Integer::parseInt;
        Predicate<String> nonBlank =
                StaticMethodReferenceDemo::hasText;
        Function<Integer, String> labeler =
                StaticMethodReferenceDemo::label;
        Consumer<String> printer =
                StaticMethodReferenceDemo::printMessage;

        IntUnaryOperator absolute = Math::abs;
        IntBinaryOperator maximum = Math::max;
        BinaryOperator<Integer> add = Integer::sum;
        Comparator<Integer> ascending = Integer::compare;

        System.out.println("parse=" + parse.apply("42"));
        System.out.println("radix=" + parseRadix.apply("ff", 16));
        System.out.println("nonBlank=" + nonBlank.test(" Java "));
        System.out.println("blank=" + nonBlank.test("   "));
        System.out.println("null=" + nonBlank.test(null));
        System.out.println("label=" + labeler.apply(9));
        System.out.println("abs=" + absolute.applyAsInt(-7));
        System.out.println("max=" + maximum.applyAsInt(8, 11));

        List<String> source = Arrays.asList("10", "20", "-3");
        List<Integer> values = source.stream()
                .map(Integer::parseInt)
                .collect(Collectors.toList());

        System.out.println("values=" + values);
        System.out.println("sum=" +
                values.stream().reduce(0, add));

        List<Integer> sorted = new ArrayList<>(values);
        sorted.sort(ascending);
        System.out.println("sorted=" + sorted);

        printer.accept("OK");

        try {
            parse.apply("not-a-number");
        } catch (NumberFormatException expected) {
            System.out.println("invalid=NumberFormatException");
        }
    }
}
~~~

Dùng JDK 17+:

~~~bash
javac --release 17 StaticMethodReferenceDemo.java
java StaticMethodReferenceDemo
~~~

**Stdout chính xác**:

~~~text
parse=42
radix=255
nonBlank=true
blank=false
null=false
label=N=9
abs=7
max=11
values=[10, 20, -3]
sum=27
sorted=[-3, 10, 20]
message=OK
invalid=NumberFormatException
~~~

Diễn giải:

- `Integer::parseInt` được chọn theo hai target type khác nhau: một đầu vào `String` và hai đầu vào `(String, Integer)`.
- `StaticMethodReferenceDemo::hasText` tham chiếu static method do bạn viết; nhờ kiểm tra `value != null` trước, `null` không gây `NullPointerException` trong predicate.
- `Math::abs` và `Math::max` có nhiều overload nguyên thủy; `IntUnaryOperator`, `IntBinaryOperator` làm rõ phiên bản `int`.
- `values.stream().map(Integer::parseInt)` minh họa static method reference làm bước chuyển `String -> Integer` trong một stream.
- `Integer::sum` được dùng trong `reduce(0, add)`; identity `0` phù hợp với phép cộng số nguyên trong ví dụ.
- `Integer::compare` biểu diễn một `Comparator<Integer>` cho sắp xếp số tăng dần, tránh sử dụng phép trừ `(a, b) -> a - b` dễ overflow.
- `printMessage` có kiểu trả về `void` nên phù hợp `Consumer<String>`.
- `Integer.parseInt` sẽ ném `NumberFormatException` khi chuỗi không phải một biểu diễn số hợp lệ; test bắt **loại ngoại lệ**, không so khớp thông điệp lỗi phụ thuộc phiên bản.

**Giới hạn phiên bản:** cú pháp `::`, `java.util.function`, `Stream.map`/`reduce` và `List.sort` được hỗ trợ từ Java 8; trong chương trình này `String.isBlank()` được thêm từ Java 11, nên chạy với `--release 17`. Dùng runtime Java đang được hỗ trợ trong dự án, không cần sử dụng runtime Java 8 cũ chỉ để học một tính năng bắt đầu từ Java 8.

## 6. Những gì compiler đối chiếu khi chọn static method

Với biểu thức `ClassName::methodName`, compiler cần tìm một phương thức **static có thể áp dụng** cho function type của target interface.

Các yếu tố quan trọng:

- **Số lượng tham số SAM** và số lượng đối số phương thức đích.
- **Kiểu các tham số**, chuyển đổi widening/boxing/unboxing và generic type inference theo quy tắc Java.
- **Kiểu kết quả** cần tương thích với SAM trong ngữ cảnh.
- **Visibility**: phương thức phải truy cập được từ vị trí sử dụng.
- **Overload**: một tên phương thức có thể biểu thị nhiều phương thức; compiler chọn theo target type và quy tắc overload resolution.
- **Checked exception** được phương thức đích khai báo phải tương thích với `throws` của SAM.
- **Varargs**: phương thức static có thể nhận tham số biến đổi, nhưng việc áp dụng và lựa chọn overload vẫn tuân thủ quy tắc của Java.

Một ví dụ được kiểm tra bằng chữ ký:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;

Function<String, Integer> decimal = Integer::parseInt;
BiFunction<String, Integer, Integer> radix = Integer::parseInt;
~~~

Vì Java biết target function type, `Integer::parseInt` không bị mơ hồ trong hai phép gán trên.

### Method reference khác với ép kiểu “mặc định”

Không thể bảo rằng compiler sẽ tự động biến mọi static method thành một functional interface bất kỳ chỉ vì tên phù hợp.

~~~java
// Sai: parseInt(String) không trả về String.
// java.util.function.UnaryOperator<String> wrong = Integer::parseInt;

// Đúng: kết quả Integer được biểu diễn bằng Function<String,Integer>.
java.util.function.Function<String, Integer> right =
        Integer::parseInt;
~~~

Một method reference cũng không tự cung cấp “cách chuyển String sang int” nếu chữ ký phương thức đích không có chuyển đổi phù hợp. Cần giải thích rõ nghiệp vụ hoặc viết adapter lambda khi phải sửa đổi tham số.

## 7. Static method overload và generic methods

### Overload: `Math::max` chọn theo SAM

`Math.max` có overload cho `int`, `long`, `float` và `double`. Tùy target type:

~~~java
java.util.function.IntBinaryOperator intMax = Math::max;
java.util.function.LongBinaryOperator longMax = Math::max;
java.util.function.DoubleBinaryOperator doubleMax = Math::max;

// intMax.applyAsInt(3, 8) == 8
// longMax.applyAsLong(3L, 8L) == 8L
// doubleMax.applyAsDouble(3.0, 8.0) == 8.0
~~~

Không nên dựa vào tên phương thức để đoán kiểu được dùng; hãy nhìn **target functional interface** và chữ ký SAM.

### Generic static method cũng dùng được

Ví dụ `java.util.Collections.emptyList()` là static generic factory:

~~~java
java.util.function.Supplier<java.util.List<String>> empty =
        java.util.Collections::emptyList;

java.util.List<String> result = empty.get();
~~~

Compiler suy luận tham số generic từ ngữ cảnh `Supplier<List<String>>`. Danh sách trả về là **rỗng và không sửa đổi được** theo hợp đồng của factory, vì vậy không nên gọi `result.add(...)` để thử thêm phần tử.

Một ví dụ phổ biến khác:

~~~java
java.util.function.Predicate<String> notNull =
        java.util.Objects::nonNull;

// notNull.test(null) == false
// notNull.test("ok") == true
~~~

`Objects.nonNull(Object)` là static method, nhận đối tượng và trả về `boolean`; `Predicate<String>` tương thích vì `String` là một `Object`.

### Tránh suy luận generic “mất dấu”

Dùng generic target cụ thể như `Function<String,Integer>`, `Predicate<String>`, `Supplier<List<String>>` giúp compiler xác định phương thức tương thích và giúp người đọc thấy rõ ràng buộc. Hạn chế dùng **raw type** như `Function parser` vì mất thông tin kiểu tĩnh, cảnh báo có thể xuất hiện và các API sẽ kém an toàn.

## 8. Phân biệt chính xác với ba dạng method reference khác

Java có bốn nhóm cú pháp thường gặp:

| Dạng | Ví dụ | Cơ chế |
| --- | --- | --- |
| **Tham chiếu static** | `Integer::parseInt` | Gọi một phương thức static của kiểu `Integer` |
| **Tham chiếu instance đã gắn receiver** | `System.out::println` | Receiver `System.out` được xác định khi tạo reference; SAM cung cấp các đối số còn lại |
| **Tham chiếu instance chưa gắn receiver** | `String::length` | Đối số đầu của SAM đóng vai trò receiver; phương thức `length()` gọi trên receiver đó |
| **Tham chiếu constructor** | `ArrayList<String>::new` | Tạo đối tượng mới bằng constructor tương thích |

Ví dụ so sánh:

~~~java
java.util.function.Function<String, Integer> parse =
        Integer::parseInt; // static: String -> Integer

java.util.function.Consumer<String> print =
        System.out::println; // bound instance: String -> void

java.util.function.ToIntFunction<String> length =
        String::length; // unbound instance: String -> int

java.util.function.Supplier<java.util.ArrayList<String>> factory =
        java.util.ArrayList<String>::new; // constructor: () -> ArrayList
~~~

**Điểm dễ nhầm:** `Integer::parseInt` và `String::length` đều dùng `TênLớp::TênPhươngThức` nhưng **không cùng loại**. `Integer.parseInt(String)` là `static`, còn `String.length()` là **instance method**. Với `String::length`, tham số đầu tiên của SAM cung cấp receiver `String` mà trên đó `length()` được gọi.

Tương tự, `System.out::println` là tham chiếu instance đã gắn đối tượng `PrintStream`, **không** phải static reference chỉ vì tên `System` xuất hiện.

Khi phân tích `TypeName::methodName`, trước hết **tra cứu xem phương thức được chọn có `static` hay không**; sau đó xem target type. Trong các trường hợp method reference có tên overload hoặc cả phương thức static lẫn instance có thể áp dụng, quy tắc phân giải của JLS quyết định lựa chọn; đừng phân loại chỉ dựa vào hình thức.

## 9. Có thật giống lambda không? Khi nào nên giữ lambda?

Method reference `Integer::parseInt` rõ ràng khi mục đích chính là “chuyển tiếp trực tiếp”.

~~~java
java.util.function.Function<String, Integer> convertA =
        Integer::parseInt;

java.util.function.Function<String, Integer> convertB =
        text -> Integer.parseInt(text);
~~~

Trong ngữ cảnh này hai cách cung cấp cùng phép chuyển từ chuỗi hợp lệ sang số nguyên. Tuy nhiên, nếu cần **thêm xử lý** trước hoặc sau khi gọi, lambda thường tốt hơn:

~~~java
java.util.function.Function<String, Integer> trimAndParse =
        text -> Integer.parseInt(text.strip());
~~~

`Integer::parseInt` **không** tương đương với `trimAndParse`: đối với `" 42 "`, `parseInt` trực tiếp ném `NumberFormatException`, còn `strip` rồi `parseInt` cho `42`. `String.strip()` tồn tại từ Java 11.

Hoặc nếu cần xử lý lỗi theo hợp đồng của ứng dụng:

~~~java
java.util.function.Function<String, java.util.OptionalInt> safeParse =
        text -> {
            if (text == null) {
                return java.util.OptionalInt.empty();
            }
            try {
                return java.util.OptionalInt.of(
                        Integer.parseInt(text));
            } catch (NumberFormatException ex) {
                return java.util.OptionalInt.empty();
            }
        };
~~~

**Đoạn `safeParse` trên chỉ là minh họa trong phạm vi có imports phù hợp**, không phải chương trình `main` độc lập. Nó nêu rõ lựa chọn nghiệp vụ: không thể parse thì trả `OptionalInt.empty()`. `OptionalInt` là primitive-specialized optional của Java, không mang ý nghĩa method reference tự xử lý lỗi.

Hãy dùng method reference khi nó **đọc dễ, đúng kiểu, đúng xử lý và không che mất bước quan trọng**. Đừng cố thay lambda có điều kiện, ghi log, bắt exception hoặc thay đổi tham số bằng reference không thể biểu đạt logic ấy.

### Không kỳ vọng method reference là một đối tượng singleton

Không nên phụ thuộc vào việc hai lần đánh giá cùng một method reference có trả về đúng **cùng object identity** (`==`) hoặc có cùng tên class nội bộ. JVM có quyền tối ưu việc tạo object. Tính đúng đắn cần dựa vào **hành vi của SAM**, không dựa vào cơ chế hiện thực hóa lambda trong JVM.

## 10. Checked exception: phương thức static có thể không phù hợp với Function

Một static method reference chỉ dùng được khi `throws` của phương thức đích tương thích với functional interface mục tiêu.

Ví dụ `java.nio.file.Files.readString(Path)` là static method có từ **Java 11**, trả về `String` nhưng có thể ném checked `IOException`.

~~~java
// Không hợp lệ: Function.apply không khai báo checked IOException.
// java.util.function.Function<java.nio.file.Path, String> reader =
//         java.nio.file.Files::readString;
~~~

Nếu hợp đồng cần cho phép `IOException`, định nghĩa functional interface phù hợp:

~~~java
@FunctionalInterface
interface PathTextReader {
    String read(java.nio.file.Path path)
            throws java.io.IOException;
}

PathTextReader reader = java.nio.file.Files::readString;
~~~

Đoạn trên là **mã minh họa cần đặt trong class/phương thức tương ứng**; không tự gọi `read` vì ví dụ chưa có tệp đầu vào. Trên JDK 17+, chữ ký `readString(Path)` phù hợp với `PathTextReader`; ở phía caller phải bắt hoặc khai báo `IOException` khi gọi `reader.read(path)`.

Không nên gói mọi checked exception thành `RuntimeException` chỉ để làm cho method reference khớp `Function`. Hãy thiết kế hợp đồng exception theo trách nhiệm API, có cân nhắc đường xử lý lỗi và khả năng debug.

## 11. Null, tính thuần, thread-safety và tác dụng phụ

**Method reference không làm thay đổi hợp đồng của phương thức được tham chiếu.** Nếu gọi `Integer.parseInt(null)` hay chuỗi không hợp lệ, lỗi vẫn phát sinh theo đặc tả `parseInt`. Nếu static method thay đổi trạng thái toàn cục, reference cũng mang hành vi có side effect đó khi được gọi.

Ví dụ:

~~~java
java.util.function.Predicate<Object> notNull =
        java.util.Objects::nonNull;

java.util.function.Function<String, Integer> parser =
        Integer::parseInt;

boolean a = notNull.test(null); // false
int b = parser.apply("10");      // 10
~~~

`Objects::nonNull` thường hợp với `stream().filter(Objects::nonNull)` vì mục đích lọc bỏ null dễ nhận biết. Tuy nhiên, bạn chỉ nên lọc null khi **phù hợp yêu cầu nghiệp vụ**: việc âm thầm bỏ bản ghi thiếu dữ liệu có thể là lỗi trong các hệ thống cần báo dữ liệu không hợp lệ.

Tương tự, method reference tới một static method dùng cache hoặc mutable static field **không tự động thread-safe**. Nếu chạy trong `parallelStream` hay executor, bản thân hàm được gọi cần đáp ứng các yêu cầu non-interfering/stateless hoặc đồng bộ phù hợp. Cú pháp `::` không cung cấp cơ chế đồng bộ tự động.

## 12. Những lỗi thường gặp và cách khắc phục

1. **Quên target type:** `var parser = Integer::parseInt;` không hợp lệ, vì compiler không suy ra functional interface từ method reference. Hãy viết `Function<String,Integer> parser = Integer::parseInt;`.
2. **Gọi nhầm thay vì tham chiếu:** `Integer.parseInt("3")` tạo `int`, không tạo `Function`; cần `Integer::parseInt`.
3. **Đếm sai tham số:** `Integer::sum` có hai tham số, không thể gán cho `UnaryOperator<Integer>` một tham số; dùng `BinaryOperator<Integer>` hay `IntBinaryOperator`.
4. **Nhầm static với instance:** `String::length` là unbound instance method reference, không phải static.
5. **Kết quả không tương thích:** `UnaryOperator<String> wrong = Integer::parseInt;` sai kiểu trả về; chọn `Function<String,Integer>`.
6. **Không hiểu overload:** `Math::max` có nhiều overload; target type `IntBinaryOperator` giúp chọn phiên bản `int`.
7. **Dùng method reference khi cần thêm bước xử lý:** `Integer::parseInt` không tự strip khoảng trắng, xác thực giá trị hoặc bắt lỗi.
8. **Bỏ qua checked exception:** `Files::readString` không tương thích `Function<Path,String>` vì `IOException`; cần interface `throws IOException` hoặc xử lý rõ ràng.
9. **Mặc định performance vượt lambda:** không có đảm bảo chung về tốc độ/cấp phát; đo lường khi thực sự quan trọng.
10. **Mặc định `null` an toàn:** hành vi phụ thuộc phương thức đích; `Objects.nonNull` có hợp đồng khác `Integer.parseInt`.
11. **Dùng primitive wrapper nhiều trong đường nóng:** cân nhắc `ToIntFunction<String>` hoặc `IntBinaryOperator` để tránh boxing ở các đoạn xử lý số lượng lớn.
12. **Quên baseline JDK:** `String.isBlank()`, `String.strip()`, `Files.readString(Path)` có từ Java 11; bản thân static method reference có từ Java 8.
13. **Tự đặt tên API không tồn tại:** không suy từ cú pháp `::` rằng mọi phương thức được gọi đều static; hãy đọc Javadoc hoặc định nghĩa phương thức.
14. **Sai phạm vi truy cập:** tham chiếu `private static` từ một class ngoài phạm vi cho phép gây compile-time error.
15. **Cho rằng reference thực thi ngay lập tức:** lệnh gọi xảy ra khi SAM được thực thi; điều này quan trọng với side effect và lỗi runtime.

## 13. Bài tập thực hành

**Bài 1 — Nhận dạng.** Hãy xác định trong bốn biểu thức sau, đâu là static method reference, đâu là bound/unbound instance, đâu là constructor reference: `Integer::parseInt`, `System.out::println`, `String::length`, `ArrayList<String>::new`.

**Bài 2 — Target typing.** Viết hai biến nhận `Integer::parseInt`:
- `Function<String,Integer>`, parse số thập phân.
- `BiFunction<String,Integer,Integer>`, parse theo cơ số.

Kiểm tra `"100"` với cơ số `2` nhận `4`.

**Bài 3 — Stream.** Chuyển danh sách `["5","7","-2"]` sang `List<Integer>` bằng `map(Integer::parseInt)`, rồi tính tổng với `reduce(0,Integer::sum)`. Kết quả mong đợi là `10`.

**Bài 4 — Overload.** Viết `IntBinaryOperator max = Math::max` và `DoubleBinaryOperator maxDouble = Math::max`. Giải thích vai trò SAM và vì sao hai biến có kiểu khác nhau.

**Bài 5 — Refactor lambda.** Thay `x -> Objects.nonNull(x)` bằng reference tương đương. Sau đó giải thích vì sao lambda `s -> Integer.parseInt(s.strip())` **không** thể thay trực tiếp bằng `Integer::parseInt` mà không đổi hành vi.

**Bài 6 — Checked exception.** Vì sao `Function<Path,String> f = Files::readString` không hợp lệ trên JDK 17? Định nghĩa một functional interface có `throws IOException` để dùng reference này.

**Bài 7 — Kiểm tra lỗi.** Với `Function<String,Integer> parse = Integer::parseInt`, dự đoán `parse.apply("xyz")` và `parse.apply(" 7 ")`. Viết test bắt `NumberFormatException` nếu hợp đồng ứng dụng không cho phép giá trị không hợp lệ.

**Bài 8 — Tự tạo static method.** Viết `static boolean positive(int x)`; gán `IntPredicate positive = YourClass::positive`, thử với `-1`, `0`, `1` và giải thích cách compiler gắn SAM với phương thức đích.

## Tóm tắt

- **Static method reference có dạng `TypeName::staticMethodName`**. Nó tham chiếu hành vi có sẵn để thực thi qua một functional interface chứ không gọi phương thức ngay tại lúc khai báo.
- **Target typing** quyết định chữ ký được mong đợi; compiler phân giải overload và kiểm tra kiểu kết quả, chuyển đổi, quyền truy cập, exception.
- **`Integer::parseInt`, `Integer::sum`, `Math::max` và `Objects::nonNull`** là những ví dụ thực dụng, còn áp dụng trong Java hiện đại.
- **Method reference không đồng nghĩa với xử lý thêm**. Khi cần validation, chuẩn hóa, log, transform tham số hoặc bắt lỗi, lambda thường thích hợp hơn.
- **Cùng cú pháp `Type::method` không đồng nghĩa cùng loại**: `String::length` là tham chiếu instance chưa gắn receiver, còn `Integer::parseInt` là static reference.
- **Compiler kiểm tra chữ ký, không xác minh toàn bộ nghiệp vụ hoặc thread-safety** của phương thức được tham chiếu.
- **Quan tâm mức JDK**: method reference có từ Java 8, nhưng những API cụ thể như `String.strip` hoặc `Files.readString` cần Java 11+.

## Tài liệu chính thức

1. Java Language Specification, `15.13 Method Reference Expressions`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13
2. Java Language Specification, `15.27 Lambda Expressions`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27
3. Java SE 17 API `Integer.parseInt`, `sum`, `compare`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html
4. Java SE 17 API `Math`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
5. Java SE 17 API `Objects.nonNull`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html
6. Java SE 17 API `Function`, `BiFunction`, `ToIntFunction` và các functional interfaces chuẩn: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html
7. Java SE 17 API `Files.readString`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

Các API và quy tắc cốt lõi trên vẫn có giá trị với Java hiện đại. Khi xây dựng ứng dụng, tra Javadoc và Java Language Specification của JDK đích để xác minh `@since`, đặc tả exception và những thay đổi mới; không dùng nguồn cũ thay cho hợp đồng hiện tại của API.