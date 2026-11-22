# Ngữ cảnh gán, truyền đối số, trả về và ép kiểu của lambda trong Java

Một biểu thức lambda trong Java **không có kiểu độc lập chỉ từ cú pháp của nó**. Trình biên dịch cần một **kiểu đích (target type)** phù hợp, thường là một functional interface, để xác định kiểu tham số, kiểu kết quả và kiểm tra tính hợp lệ của thân lambda. Kiểu đích xuất hiện trong nhiều ngữ cảnh, đặc biệt là **phép gán**, **truyền đối số phương thức**, **câu lệnh trả về** và **ép kiểu (cast)**.

Đây là nguyên tắc quan trọng của Java 8+ và vẫn áp dụng trong Java 17+: cùng một lambda như x -> x.length() có thể hợp lệ tại vị trí này nhưng không biên dịch tại vị trí khác, tùy **SAM** (single abstract method — phương thức trừu tượng duy nhất) mà ngữ cảnh yêu cầu. Hiểu quy tắc này giúp đọc thông báo lỗi compiler, thiết kế API nhận lambda và tránh cast hoặc khai báo kiểu không cần thiết.

## 1. Vì sao lambda cần kiểu đích?

Xét biểu thức:

~~~java
text -> text.length()
~~~

Đứng một mình, biểu thức chưa cho biết text thuộc kiểu nào. Nếu text là String, length() trả int; nếu một kiểu khác có phương thức length() tương thích, ngữ nghĩa có thể khác. Java không tự gán một “kiểu hàm chung” cho biểu thức lambda rồi chờ chuyển đổi về sau.

Kiểu đích cung cấp **function descriptor** (chữ ký chức năng) cho lambda:

~~~java
java.util.function.Function<String, Integer> length =
    text -> text.length();
~~~

Ở đây compiler biết:

1. Target type là Function<String, Integer>.
2. Phương thức trừu tượng apply(String) nhận String và trả Integer.
3. Biến text trong lambda được suy luận là String.
4. Lời gọi text.length() trả int, có thể **boxing** thành Integer.

Ngược lại:

~~~java
// KHÔNG BIÊN DỊCH: thiếu target functional interface.
var length = text -> text.length();
~~~

Dù Java cho phép var cho biến cục bộ kể từ Java 10, **var không tạo kiểu đích cho lambda initializer**. Tương tự, Object không phải functional interface, nên không thể gán lambda trực tiếp vào Object:

~~~java
// KHÔNG BIÊN DỊCH:
Object action = () -> System.out.println("hello");
~~~

Muốn lưu dưới dạng Object, cần cho lambda một kiểu đích trước:

~~~java
Object action = (Runnable) () -> System.out.println("hello");
~~~

Cast sang Runnable là nơi cung cấp kiểu đích, sau đó đối tượng tạo ra có thể được gán vào Object. Khi muốn gọi run(), phải dùng kiểu phù hợp:

~~~java
((Runnable) action).run();
~~~

Hai đoạn sau là mã minh họa đặt trong phương thức; ví dụ chạy đầy đủ nằm ở phần 9.

## 2. Functional interface quyết định chữ ký lambda

Một functional interface có một phương thức trừu tượng có hiệu lực. Lambda phải phù hợp với **số lượng tham số**, **kiểu tham số**, **khả năng trả kết quả** và **ràng buộc ngoại lệ checked** của function descriptor.

| Kiểu đích | SAM | Lambda tương thích |
| --- | --- | --- |
| Runnable | void run() | () -> System.out.println("go") |
| Supplier<String> | String get() | () -> "ready" |
| Consumer<String> | void accept(String) | text -> System.out.println(text) |
| Predicate<String> | boolean test(String) | text -> !text.isBlank() |
| Function<String,Integer> | Integer apply(String) | text -> text.length() |
| BiFunction<Integer,Integer,Integer> | Integer apply(Integer,Integer) | (a,b) -> a+b |
| Comparator<String> | int compare(String,String) | (left,right) -> left.compareTo(right) |

Với kiểu đích đã xác định, cú pháp (text) -> ... hoặc text -> ... đều có thể dùng cho một tham số. Với từ hai tham số trở lên cần dấu ngoặc. Các tham số được suy luận kiểu không cần viết String, Integer; nếu ghi kiểu tường minh thì phải phù hợp với descriptor.

Ví dụ:

~~~java
java.util.function.Predicate<String> nonEmpty =
    (String text) -> !text.isEmpty();
~~~

Trường hợp này và text -> !text.isEmpty() có cùng hành vi dưới cùng target type.

**Giới hạn quan trọng:** không phải mọi interface mang @FunctionalInterface đều dùng được với lambda. Nếu chính SAM khai báo type parameter riêng như <T> T identity(T x), function descriptor là generic và Java lambda không trực tiếp triển khai được phương thức trừu tượng generic đó. Đây là trường hợp khác với Function<T,R>, nơi type parameter nằm ở cấp interface và được chuyên biệt hóa theo target type.

## 3. Ngữ cảnh gán (assignment context)

Phép gán cung cấp target type trực tiếp nhất.

~~~java
java.util.function.Function<String, Integer> length =
    String::length;

java.util.function.Predicate<Integer> positive =
    number -> number > 0;

java.lang.Runnable report =
    () -> System.out.println("completed");
~~~

Trong ba trường hợp, kiểu của biến ở vế trái là kiểu đích. Không cần cast lambda. Method reference như String::length cũng là **poly expression**, được kiểm tra theo kiểu đích tương tự.

### 3.1. Target type và phép chuyển đổi kết quả

~~~java
java.util.function.Function<String, Number> size =
    text -> text.length();
~~~

Biểu thức text.length() trả int. Java có thể boxing int thành Integer và widening reference Integer thành Number theo quy tắc tương thích kiểu trong ngữ cảnh trả về của lambda. Bởi vậy việc lambda trả int không bắt buộc target phải Function<String,Integer>.

Ngược lại:

~~~java
// KHÔNG BIÊN DỊCH: String không tương thích kiểu kết quả Long.
java.util.function.Function<String, Long> invalid =
    text -> text.length();
~~~

Không tồn tại chuyển đổi ngầm trực tiếp từ kết quả int của length() sang Long theo chuỗi boxing phù hợp ở đây; nên dùng (long) text.length() nếu muốn kết quả Long, hoặc dùng ToLongFunction<String> nếu muốn long nguyên thủy.

### 3.2. Đối tượng lambda có thể được tái sử dụng sau phép gán

~~~java
java.util.function.Function<String, String> normalize =
    text -> text.trim();

String name = normalize.apply("  An  ");
~~~

Một biểu thức lambda được kiểm tra theo target type khi khai báo; sau đó có thể truyền giá trị có kiểu Function<String,String> đi nơi khác. Điều này khác với việc trông chờ một lambda chưa có kiểu tự suy luận từ ngữ cảnh không hợp lệ.

### 3.3. Hạn chế của var

Không hợp lệ:

~~~java
// KHÔNG BIÊN DỊCH.
var normalize = text -> text.trim();
~~~

Hợp lệ:

~~~java
java.util.function.UnaryOperator<String> normalize =
    text -> text.trim();

var copiedReference = normalize;
~~~

Ở dòng thứ hai, var suy ra kiểu **từ biến normalize đã có kiểu**, không phải suy ra trực tiếp một target type cho lambda.

Kể từ Java 11, có thể dùng var trong **khai báo tham số của lambda** nếu có target type:

~~~java
java.util.function.Function<String, String> upper =
    (var text) -> text.toUpperCase();
~~~

Ở đây (var text) không có nghĩa lambda tự suy luận kiểu độc lập. Target Function<String,String> vẫn quyết định text là String. Khi dùng var ở các tham số lambda, phải tuân thủ quy tắc nhất quán, không trộn tùy tiện tham số var với tham số ngầm định hoặc kiểu tường minh trong cùng một danh sách.

## 4. Ngữ cảnh truyền đối số (invocation context)

Khi gọi một phương thức có tham số kiểu functional interface, **tham số hình thức** cung cấp target type cho lambda:

~~~java
static String transform(
        String value,
        java.util.function.UnaryOperator<String> operation) {
    return operation.apply(value);
}
~~~

Gọi:

~~~java
String result = transform("java",
    text -> text.toUpperCase());
~~~

Compiler biết tham số thứ hai cần UnaryOperator<String>, có SAM String apply(String). Vì thế text là String và kết quả text.toUpperCase() cũng là String.

Không bắt buộc tạo biến UnaryOperator trước:

~~~java
java.util.function.UnaryOperator<String> upper =
    text -> text.toUpperCase();

String result = transform("java", upper);
~~~

Hai cách tương đương về hành vi. Dùng lambda inline khi hành vi ngắn và dễ hiểu, hoặc đặt biến khi cần tái sử dụng hay tên mô tả.

### 4.1. Functional interface tự định nghĩa vẫn hoạt động

~~~java
@FunctionalInterface
interface StringRule {
    boolean accept(String text);
}

static boolean check(String value, StringRule rule) {
    return rule.accept(value);
}
~~~

Lời gọi:

~~~java
boolean valid = check("Java", text -> !text.isBlank());
~~~

Ở đây **StringRule** là target type, không phải Predicate<String> dù hai interface có function descriptor tương tự. Java không tự xem hai functional interface khác tên là có quan hệ kế thừa hay thay thế nhau. Lambda chỉ được chuyển theo target type phù hợp mà compiler đã chọn.

### 4.2. Phương thức generic và suy luận kiểu đối số

Một phương thức generic thường dùng callback:

~~~java
static <T, R> R convert(
        T input,
        java.util.function.Function<? super T, ? extends R> function) {
    return function.apply(input);
}
~~~

Có thể gọi:

~~~java
Integer length = convert("hello", text -> text.length());
~~~

Compiler phối hợp thông tin từ đối số "hello" (liên quan T), kiểu gán Integer (liên quan R) và lambda. Không nên hiểu máy “chạy lambda trước để biết kiểu”; Java giải bài toán ràng buộc kiểu tại thời điểm biên dịch.

Một method reference cũng có thể được suy luận theo ngữ cảnh:

~~~java
int count = convert("hello", String::length);
~~~

Đối với lambda hay method reference trong phương thức generic, đôi khi compiler chưa có đủ thông tin từ overload hoặc ràng buộc kiểu. Giải pháp thường là chỉ rõ target type bằng biến có kiểu, type witness của phương thức generic hoặc cast có chủ đích, đồng thời cải thiện thiết kế API nếu quá nhập nhằng.

### 4.3. Overload và tính nhập nhằng

Vì lambda có thể tương thích với nhiều kiểu chức năng, overload đôi khi gây lỗi:

~~~java
static void use(java.util.function.Function<String,String> fn) { }
static void use(java.util.function.UnaryOperator<String> fn) { }

// Có thể gây nhập nhằng nếu chỉ viết:
use(text -> text.trim());
~~~

Dù UnaryOperator<String> kế thừa Function<String,String>, những quy tắc chọn phương thức cụ thể nhất có thể làm overload được chọn theo cấu trúc chữ ký; không nên dựa vào suy đoán rằng mọi overload chứa hai interface tương tự đều mơ hồ. Ví dụ minh họa chắc chắn cần phân biệt hai kiểu đích độc lập:

~~~java
@FunctionalInterface
interface A { String go(String input); }

@FunctionalInterface
interface B { String go(String input); }

static void perform(A action) { }
static void perform(B action) { }

// KHÔNG BIÊN DỊCH: cùng lambda tương thích A lẫn B.
perform(text -> text.trim());

// Chỉ định kiểu đích mong muốn:
perform((A) (text -> text.trim()));
~~~

Các đoạn này minh họa cấu trúc trong cùng một lớp; dòng cố ý sai chỉ để phân tích, không nằm trong chương trình chạy ở phần 9.

**Lựa chọn tốt:** tránh overload API chỉ khác functional interface cùng hình dạng khi khách hàng cần truyền lambda. Nếu cần lựa chọn rõ, đặt tên hai phương thức khác nhau, dùng biến callback có kiểu hoặc cast để thể hiện ý định. Cast giải quyết ngữ cảnh khi thực sự cần, không phải cách sửa mọi lỗi suy luận kiểu.

## 5. Ngữ cảnh trả về (return context)

Nếu một phương thức có kiểu trả về là functional interface, biểu thức lambda trong câu lệnh **return** được kiểm tra theo kiểu đó:

~~~java
static java.util.function.Supplier<String> greeting() {
    return () -> "READY";
}
~~~

Không cần gán lambda vào biến ở giữa. Phương thức greeting() trả một Supplier<String>, còn lời gọi greeting().get() mới thực thi hành vi và trả String.

Một ví dụ có tham số:

~~~java
static java.util.function.Predicate<String> minLength(int minimum) {
    return text -> text.length() >= minimum;
}
~~~

Lambda capture biến minimum. Vì minimum là tham số không được gán lại trong phương thức, nó effectively final và có thể được capture. Lời gọi:

~~~java
java.util.function.Predicate<String> atLeast4 = minLength(4);
System.out.println(atLeast4.test("Java")); // true
~~~

Cần phân biệt **trả về lambda** với **thực thi lambda**:

- minLength(4) tạo/trả một giá trị Predicate<String>.
- atLeast4.test("Java") mới áp dụng điều kiện.
- Biến minimum được capture khi lambda được tạo, nên mỗi lần gọi minLength với tham số khác nhau có thể tạo bộ quy tắc với ngưỡng khác nhau.
- Nếu lambda capture một đối tượng mutable, yêu cầu effectively final chỉ áp dụng cho biến tham chiếu cục bộ; bản thân đối tượng vẫn có thể thay đổi.

### 5.1. Nhánh return đều có thể dùng chung kiểu đích

~~~java
static java.util.function.UnaryOperator<String> formatter(boolean trim) {
    if (trim) {
        return text -> text.trim();
    }
    return text -> text.toUpperCase();
}
~~~

Cả hai lambda được kiểm tra theo **UnaryOperator<String>**, dù thực hiện hai hành vi khác nhau. Return type phải thể hiện hợp đồng mà caller thật sự sử dụng.

### 5.2. Return type Object không cấp target type lambda

~~~java
// KHÔNG BIÊN DỊCH: Object không phải functional interface.
static Object missingTarget() {
    return () -> "hello";
}
~~~

Nếu API trả Object theo thiết kế, có thể cấp kiểu đích bằng cast trước:

~~~java
static Object typedThenBoxed() {
    return (java.util.function.Supplier<String>) () -> "hello";
}
~~~

Nhưng cách này làm mất thông tin kiểu tại giao diện API; nếu caller cần Supplier, hãy ưu tiên trả Supplier<String> trực tiếp. Cast sang functional interface chỉ để rồi lưu dưới Object thường là dấu hiệu thiết kế chưa rõ ràng.

## 6. Ngữ cảnh ép kiểu (casting context)

Một cast tới functional interface có thể tự nó cung cấp target type:

~~~java
java.lang.Object action =
    (java.lang.Runnable) () -> System.out.println("RUN");
~~~

Ở biểu thức (Runnable) () -> ..., compiler biết lambda cần thực thi void run(). Giá trị cuối được phép upcast thành Object vì Runnable là kiểu tham chiếu.

Có thể gọi trực tiếp khi cast được đặt ngoặc đúng:

~~~java
((java.util.function.Function<String, String>) String::trim)
    .apply("  done  ");
~~~

Khi gắn kết quả cast với một nơi khác, cần phân biệt:

1. **Cast cung cấp target type để kiểm tra lambda** tại compile time.
2. **Cast một đối tượng sẵn có sang interface khác** chỉ hợp lệ tại runtime nếu đối tượng thật sự thực thi interface đó; nếu không, có thể ném ClassCastException.

Ví dụ thứ hai không phải cách chuyển tùy ý một lambda Function thành Predicate:

~~~java
java.util.function.Function<String, String> fn =
    text -> text.trim();

// Có thể ném ClassCastException nếu ép qua Object:
java.util.function.Predicate<String> wrong =
    (java.util.function.Predicate<String>) (Object) fn;
~~~

Cùng việc cả hai là functional interface **không** làm các instance tự động implement tất cả interface có SAM một phương thức. Muốn một hành vi khác, hãy tạo lambda/method reference mới có target type phù hợp.

### 6.1. Cast giúp disambiguate overload khi cần

~~~java
perform((A) (text -> text.trim()));
~~~

Cast này chọn target A cho lambda, từ đó gọi overload perform(A). Có thể dùng biến A đặt tên rõ nghĩa thay cast inline:

~~~java
A trimAction = text -> text.trim();
perform(trimAction);
~~~

Trong mã nghiệp vụ, biến hoặc tên phương thức riêng thường dễ bảo trì hơn chuỗi cast dài.

### 6.2. Cast không bỏ qua quy tắc SAM

Không thể cast lambda tới bất kỳ interface nào nếu interface không có function descriptor tương thích:

~~~java
// KHÔNG BIÊN DỊCH: List không phải functional interface.
Object invalid = (java.util.List<String>) (() -> "hello");
~~~

Cast cũng không tự giải quyết việc lambda cần nhiều tham số hơn SAM, trả sai kiểu hoặc ném checked exception ngoài hợp đồng. Kiểu đích phải hợp lệ và thân lambda phải được kiểm tra theo nó.

## 7. Ngữ cảnh có điều kiện và phối hợp nhiều biểu thức

Ngoài bốn ngữ cảnh chính, **conditional expression** cũng có thể nhận target type từ bên ngoài khi các nhánh là lambda hoặc method reference.

~~~java
java.util.function.UnaryOperator<String> normalize =
    strict ? String::trim : String::toLowerCase;
~~~

Nếu strict là boolean, target ở phép gán là UnaryOperator<String>; hai nhánh được kiểm tra theo target đó. Dùng:

~~~java
String result = normalize.apply("  ABC  ");
~~~

Nếu strict = true, kết quả là "ABC"; nếu false, với chuỗi ví dụ trên kết quả là "  abc  ". Hai nhánh không nhất thiết có cùng hành vi nhưng phải tương thích kiểu.

Một cách viết thiếu target sẽ không hợp lệ:

~~~java
// KHÔNG BIÊN DỊCH: không có target type cho các lambda.
var action = strict ? (x -> x.trim()) : (x -> x.toUpperCase());
~~~

Có thể thêm target type rõ ràng ở biến, hoặc cast các nhánh sang kiểu chức năng mong muốn khi cần. Với các nhánh có nhiều trách nhiệm, một phương thức trả functional interface như formatter(strict) có thể dễ đọc hơn.

### 7.1. Array initializer và những vị trí khác

Khi một mảng có kiểu component là functional interface, mỗi lambda trong initializer nhận target type:

~~~java
Runnable[] tasks = {
    () -> System.out.println("first"),
    () -> System.out.println("second")
};
~~~

Có thể gọi tasks[0].run() hoặc tasks[1].run(). Tương tự, lambda xuất hiện trong một biểu thức được cấp kiểu đích ở một ngữ cảnh poly-expression khác nếu các quy tắc Java cho phép. Tuy nhiên, không suy diễn rằng **mọi vị trí biểu thức** đều cung cấp target type: trường hợp var và Object đã cho thấy các giới hạn.

## 8. Thân lambda được kiểm tra theo void hoặc kiểu trả về

Function descriptor quyết định khả năng tương thích với thân lambda.

### 8.1. Expression body và statement body

~~~java
java.util.function.Function<String, Integer> size =
    text -> text.length();
~~~

size.apply("Java") trả Integer 4. Cùng logic với thân khối:

~~~java
java.util.function.Function<String, Integer> size =
    text -> {
        int count = text.length();
        return count;
    };
~~~

Với void-compatible:

~~~java
java.util.function.Consumer<String> print =
    text -> System.out.println(text);
~~~

Gọi println là statement expression phù hợp với Consumer.accept(String) trả void. Nhưng lambda có kết quả theo yêu cầu của Function phải tạo giá trị trả về thích hợp ở mọi đường đi hoàn tất bình thường.

~~~java
// KHÔNG BIÊN DỊCH: thiếu return cho Function.
java.util.function.Function<String, Integer> invalid =
    text -> {
        text.length();
    };
~~~

### 8.2. Không phải mọi expression-body đều tương thích Consumer

Ví dụ:

~~~java
// KHÔNG BIÊN DỊCH: phép so sánh không phải statement expression.
java.util.function.Consumer<Integer> wrong =
    number -> number > 0;
~~~

Predicate<Integer> mới là loại hợp đồng cần dùng cho phép kiểm tra này:

~~~java
java.util.function.Predicate<Integer> positive =
    number -> number > 0;
~~~

Các toán tử toán học hay so sánh trả giá trị không thể tùy ý dùng làm thân lambda của Consumer. Nếu cần Consumer thực hiện một tác dụng phụ, hãy dùng lời gọi phương thức/assignment phù hợp và bảo đảm side effect rõ ràng.

### 8.3. Checked exceptions vẫn cần phù hợp

Runnable.run và Function.apply không khai báo IOException. Lambda gọi một phương thức có thể ném IOException phải bắt lỗi hoặc dùng functional interface tự định nghĩa có throws tương ứng:

~~~java
@FunctionalInterface
interface IOAction {
    void run() throws java.io.IOException;
}
~~~

Với kiểu IOAction, lambda có thể gọi trực tiếp một phương thức khai báo throws IOException. Ngữ cảnh gán, đối số, return hay cast **không tự xóa** quy tắc checked exception.

## 9. Chương trình Java 17+ chạy hoàn chỉnh

Ví dụ này minh họa trực tiếp bốn ngữ cảnh cần nắm:

- **Gán:** Function<String,Integer> length = String::length.
- **Truyền đối số:** transform("java", value -> value.toUpperCase()).
- **Trả về:** greeting() trả Supplier<String>, isNonBlank() trả Predicate<String>.
- **Ép kiểu:** tạo Runnable bằng cast rồi gán vào Object; cast khác cho method reference ngay trong biểu thức gọi.
- Đồng thời có ví dụ generic invocation, conditional target type và var trong **danh sách tham số lambda**.

Tạo tệp **TargetTypingDemo.java**:

~~~java
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;

public class TargetTypingDemo {
    static String transform(String value, UnaryOperator<String> operation) {
        return operation.apply(value);
    }

    static Supplier<String> greeting() {
        return () -> "READY";
    }

    static Predicate<String> isNonBlank() {
        return text -> !text.isBlank();
    }

    static <T, R> R convert(T input, Function<? super T, ? extends R> function) {
        return function.apply(input);
    }

    static void execute(Runnable task) {
        task.run();
    }

    public static void main(String[] args) {
        Function<String, Integer> length = String::length;
        System.out.println("assignment=" + length.apply("Java"));

        System.out.println("argument=" +
            transform("java", value -> value.toUpperCase()));

        System.out.println("return=" + greeting().get());

        Object opaque = (Runnable) () -> System.out.println("cast=RUN");
        execute((Runnable) opaque);

        System.out.println("generic=" +
            convert("hello", String::length));

        UnaryOperator<String> normalize =
            true ? String::trim : String::toLowerCase;
        System.out.println("conditional=" + normalize.apply("  abc  "));

        Predicate<String> valid = isNonBlank();
        System.out.println("predicate=" + valid.test("Java"));

        Function<String, String> explicit =
            (var text) -> text.toUpperCase();
        System.out.println("var-parameter=" + explicit.apply("ok"));

        String castResult =
            ((Function<String, String>) String::trim).apply("  done  ");
        System.out.println("cast-result=" + castResult);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp, dùng JDK 17 trở lên:

~~~bash
javac TargetTypingDemo.java
java TargetTypingDemo
~~~

Stdout chính xác:

~~~text
assignment=4
argument=JAVA
return=READY
cast=RUN
generic=5
conditional=abc
predicate=true
var-parameter=OK
cast-result=done
~~~

Giải thích từng dòng:

1. assignment=4: String::length được gán vào Function<String,Integer>; apply("Java") trả 4.
2. argument=JAVA: phương thức transform nhận UnaryOperator<String> nên lambda value -> value.toUpperCase() tự biết value là String.
3. return=READY: greeting trả Supplier<String>; get() kích hoạt lambda.
4. cast=RUN: Runnable cast cung cấp target cho lambda trước khi gán vào Object. Sau đó phải cast lại khi dùng execute(Runnable).
5. generic=5: convert suy luận T từ "hello", R từ method reference String::length và ngữ cảnh; kết quả là Integer 5 rồi được nối chuỗi để in.
6. conditional=abc: target UnaryOperator<String> áp dụng cho cả hai nhánh của phép ?:; vì điều kiện true, String::trim được chọn.
7. predicate=true: hàm trả về Predicate<String> được dùng để kiểm tra chuỗi "Java" không trống.
8. var-parameter=OK: (var text) -> ... là cú pháp hợp lệ khi đã có Function<String,String> làm target.
9. cast-result=done: cast Function<String,String> cung cấp kiểu đích cho String::trim ngay trong biểu thức.

Đoạn mẫu được thiết kế để không trộn các mã **cố ý sai** vào lớp chạy. Các ví dụ không hợp lệ trong bài chỉ dùng để giải thích compiler, không cần copy vào TargetTypingDemo.java.

## 10. Cách compiler phân giải kiểu: thứ tự suy nghĩ hữu ích

Khi nhìn thấy một lambda, bạn có thể tự diễn giải theo các bước sau:

1. **Xác định vị trí biểu thức:** đang được gán, truyền làm đối số, trả từ phương thức hay cast?
2. **Tìm target type:** Function<T,R>, Predicate<T>, Runnable hoặc interface riêng nào?
3. **Đọc function descriptor của SAM:** bao nhiêu tham số? Kiểu của chúng và kiểu trả về là gì? Có checked exception được phép không?
4. **Suy luận kiểu các tham số lambda:** đối chiếu loại tham số tường minh/ngầm định/var với descriptor.
5. **Kiểm tra thân lambda:** biểu thức hoặc khối có tương thích với kết quả/void và throws của SAM không?
6. **Nếu gọi generic/overload:** xem ràng buộc kiểu từ các đối số và nơi nhận kết quả; có nhiều overload còn phù hợp không?
7. **Nếu cast:** xác định cast đang cấp target cho một biểu thức lambda mới hay đang ép một đối tượng runtime đã tồn tại.

Quy trình này giúp giải thích vì sao một lambda như text -> text.isBlank() hoạt động trong Predicate<String> mà không hoạt động trực tiếp trong một biến Object hoặc var.

### 10.1. Ví dụ đặt cạnh nhau

| Ngữ cảnh | Hợp lệ | Lý do |
| --- | --- | --- |
| Gán có target | Predicate<String> p = s -> s.isBlank(); | SAM test(String) → boolean |
| Gán var trực tiếp | var p = s -> s.isBlank(); | Không | var không cung cấp target |
| Truyền đối số | check("x", s -> s.isBlank()); | Có, nếu tham số formal là Predicate<String> hoặc interface phù hợp |
| Trả về | return s -> s.isBlank(); | Có, nếu phương thức trả Predicate<String> |
| Cast | (Predicate<String>) (s -> s.isBlank()) | Có | Cast chỉ rõ target |
| Gán Object trực tiếp | Object p = s -> s.isBlank(); | Không | Object không phải functional interface |
| Gán Object sau cast | Object p = (Predicate<String>) (s -> s.isBlank()); | Có | Target do cast Predicate<String> cung cấp |

Bảng mô tả các mẫu ở đúng ngữ cảnh được nêu; các chữ p, s, check cần nằm trong lớp/phương thức và có khai báo thích hợp khi được dùng trong chương trình Java hoàn chỉnh.

## 11. Những sai lầm phổ biến

**Sai lầm 1 — nghĩ lambda tự có kiểu Function.** Java không mặc định mọi lambda một tham số là Function; một lambda có thể nhắm đến Predicate, Consumer, UnaryOperator hoặc interface do người dùng định nghĩa nếu descriptor phù hợp.

**Sai lầm 2 — dùng var cho biến được khởi tạo trực tiếp bằng lambda.** Không có target type nên biên dịch lỗi. Dùng một functional interface được khai báo tường minh hoặc tạo giá trị callback đã có kiểu trước.

**Sai lầm 3 — gán lambda trực tiếp cho Object.** Object không có SAM. Cần cấp target type trước bằng biến hoặc cast, nhưng nên tránh làm mất hợp đồng chức năng trong API.

**Sai lầm 4 — chỉ nhìn tên phương thức, bỏ qua overload.** Một lambda có thể phù hợp nhiều SAM; compiler phải chọn một overload theo quy tắc Java. Nếu nhập nhằng, đặt callback vào biến kiểu rõ ràng hoặc thiết kế lại overload.

**Sai lầm 5 — nhầm return trong phương thức với return trong lambda.** Trong một block lambda, return trả về từ lời gọi SAM của lambda đó. Nó **không** trả về khỏi phương thức bao quanh lambda theo cách một số ngôn ngữ khác cho phép.

**Sai lầm 6 — cast để bỏ qua lỗi kiểu.** Cast có thể cung cấp target type, nhưng không làm số tham số, kiểu kết quả hoặc checked exceptions sai trở thành hợp lệ. Cast qua Object giữa hai interface không tương thích có thể gây ClassCastException.

**Sai lầm 7 — lẫn var của biến cục bộ với var của tham số lambda.** var x = x -> ... không được vì thiếu target; Function<String,String> fn = (var x) -> ... được vì target đã có.

**Sai lầm 8 — chọn sai interface cho thân lambda.** Predicate cần boolean, Function cần giá trị tương thích, Consumer có kết quả void. Biểu thức so sánh number > 0 không thể tùy ý là thân của Consumer<Integer>.

**Sai lầm 9 — cho rằng method reference luôn phù hợp.** String::length có thể nhắm tới Function<String,Integer> hoặc ToIntFunction<String>, nhưng không thể dùng ở vị trí yêu cầu Runnable vì descriptor không nhận tham số.

**Sai lầm 10 — nhầm suy luận compile time với hành vi runtime.** Compiler giải quyết target type và generic ở thời điểm biên dịch. Việc gọi lambda xảy ra sau đó; JVM không “tự suy luận lại” target type theo giá trị đầu vào lúc chạy.

## 12. Câu hỏi tự kiểm tra

1. Vì sao Function<String,Integer> f = s -> s.length(); hợp lệ nhưng var f = s -> s.length(); không hợp lệ?
2. Khi phương thức nhận Predicate<Order>, compiler suy luận kiểu tham số order trong lambda theo thông tin nào?
3. Vì sao phương thức trả Supplier<String> có thể viết return () -> "ready";, còn trả Object thì không thể viết tương tự nếu thiếu cast?
4. Cast (Runnable) () -> System.out.println("ok") đang ép một đối tượng sẵn có hay cung cấp kiểu đích cho biểu thức lambda?
5. Điều gì làm overload nhận hai interface có descriptor tương thích trở nên mơ hồ?
6. Vì sao (var text) -> text.trim() hợp lệ dưới target Function<String,String> nhưng var action = text -> text.trim() lại sai?
7. Trong phương thức generic convert(T, Function<? super T,? extends R>), thông tin nào giúp compiler tìm T và R?
8. Tại sao một lambda trả boolean thích hợp với Predicate<Integer> nhưng không tự nhiên phù hợp Consumer<Integer>?
9. Nếu một method reference có nhiều overload, làm cách nào target type giúp compiler chọn phương thức cụ thể?
10. Khi refactor một lambda từ phép gán sang tham số phương thức, cần kiểm tra lại những điều kiện tương thích nào của SAM?

**Ghi nhớ:** Lambda trong Java được **kiểu hóa theo ngữ cảnh**. Phép gán cung cấp kiểu từ vế trái; gọi phương thức cung cấp kiểu từ tham số; return cung cấp kiểu từ khai báo trả về; cast cung cấp kiểu do người viết chỉ rõ. Khi hiểu function descriptor, cách suy luận generic và ràng buộc overload, bạn có thể dùng lambda ngắn gọn mà vẫn giữ type safety và xử lý chính xác lỗi compiler.