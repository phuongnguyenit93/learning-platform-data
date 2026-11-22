# Nạp chồng phương thức nhận lambda và lời gọi không rõ ràng trong Java

## 1. Vấn đề: cùng một lambda, nhiều overload có vẻ đều phù hợp

Java cho phép **nạp chồng phương thức** (*method overloading*): nhiều phương thức cùng tên nhưng khác danh sách tham số. Khi đối số là một giá trị thông thường có kiểu rõ ràng, trình biên dịch thường chọn overload dựa trên kiểu đối số và quy tắc tương thích. Với **lambda**, quá trình chọn có thể phức tạp hơn vì lambda là biểu thức **poly expression**: nó cần một **kiểu đích** (*target type*) là functional interface mới được kiểm tra đầy đủ.

Ví dụ hai overload nhận hai giao diện không liên quan về kế thừa:

~~~java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class Example {
    static void choose(Supplier<String> supplier) {}
    static void choose(Callable<String> callable) {}

    void demonstrate() {
        // LỖI biên dịch: cả hai overload đều có thể nhận () -> "hello".
        // choose(() -> "hello");
    }
}
~~~

Cả `Supplier<String>` và `Callable<String>` đều có một phương thức trừu tượng **không nhận đối số và trả String**. Khi gọi `choose(() -> "hello")`, lambda có thể tương thích với cả hai và không có một overload duy nhất được ưu tiên; `javac` báo *reference to choose is ambiguous*.

**Điểm cần hiểu:** lambda không có kiểu độc lập kiểu như `String` hay `int` để compiler luôn biết trước lời gọi phải chọn overload nào. Compiler xem xét các phương thức ứng viên, chữ ký của functional interface, khả năng tương thích của lambda, rồi áp dụng quy tắc chọn phương thức cụ thể nhất (*most specific method*). Nếu không có phương thức tốt nhất duy nhất, lời gọi không rõ ràng và bị từ chối **ở thời điểm biên dịch**.

Bài học này phân tích cách chọn overload, vì sao hai interface có cùng “hình dạng” dễ gây mơ hồ, khi nào thân lambda giúp phân biệt, và cách viết API/call site rõ ràng.

## 2. Ba khái niệm phải tách biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Overloading** | Nhiều phương thức cùng tên nhưng có danh sách tham số khác nhau | `run(Runnable)` và `run(Supplier<Integer>)` |
| **Functional interface** | Interface thỏa điều kiện có một hợp đồng phương thức trừu tượng để làm kiểu đích | `Supplier<T>`, `Callable<T>`, `Function<T,R>` |
| **Target typing** | Ngữ cảnh quyết định kiểu functional interface mà lambda/method reference phải tương thích | `Supplier<String> x = () -> "ok";` |

Một lambda không tự là instance kiểu `Function`, `Supplier` hay `Callable` trước khi biết kiểu đích. Cùng một cú pháp có thể dùng với các interface phù hợp khác nhau:

~~~java
java.util.function.Supplier<String> supplier = () -> "ok";
java.util.concurrent.Callable<String> callable = () -> "ok";
~~~

Hai khai báo đều hợp lệ; chúng tạo các giá trị có **kiểu khai báo khác nhau**. Trong một lời gọi overload, nếu truyền trực tiếp `() -> "ok"` thì chưa có khai báo biến để nói rõ loại nào được muốn.

### 2.1. Overload khác tên tham số không phải là hai overload

Hai phương thức có tên và danh sách kiểu tham số giống hệt nhau không thể cùng xuất hiện chỉ vì tên biến khác:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
// void use(Supplier<String> first) {}
// void use(Supplier<String> second) {}
~~~

Tương tự, không thể chỉ thay đối số generic mà tạo hai overload có cùng erasure:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH VÌ NAME CLASH SAU TYPE ERASURE:
// void use(Supplier<String> supplier) {}
// void use(Supplier<Integer> supplier) {}
~~~

Dùng hai tên phương thức riêng, một đối số phân biệt rõ, hoặc thay đổi thiết kế nếu cần hai hành vi khác nhau. Trường hợp **khai báo overload không hợp lệ** khác với trường hợp **hai overload hợp lệ nhưng một lời gọi bị ambiguous**.

## 3. Compiler chọn phương thức theo trình tự khái niệm nào?

Ở mức thực hành, hãy hình dung bốn bước:

1. **Xác định overload có thể gọi:** tên phương thức, khả năng truy cập, số lượng đối số, arity/varargs, cùng các điều kiện kiểu liên quan.
2. **Xét khả năng tương thích của lambda với từng kiểu đích ứng viên:** số tham số lambda, kiểu tham số nếu khai báo tường minh, thân lambda có hợp với kết quả `void` hoặc giá trị không, và các điều kiện kiểu khác.
3. **Chọn overload cụ thể nhất theo quy tắc JLS:** một overload có thể ưu tiên overload khác vì kiểu tham số là subtype hoặc vì những quy tắc đặc biệt về kiểu đích hàm trong ngữ cảnh nhất định.
4. **Nếu không có ứng viên duy nhất tốt nhất:** báo lỗi *ambiguous method call*, yêu cầu người viết làm rõ.

Đây là mô hình giải thích; thuật toán chính xác trong JLS §15.12 gồm các pha tìm phương thức phù hợp và phần kiểm tra *most-specific*, với chi tiết riêng cho overload, generics, varargs và poly expressions. Không nên coi sơ đồ trên là một thuật toán tự triển khai thay thế đặc tả.

**Đặc biệt:** compiler không “chạy lambda thử” rồi xem nó trả gì. Nó phân tích cú pháp, kiểu và ràng buộc của biểu thức; việc overload nào được gọi được quyết định **trước khi chương trình chạy**.

## 4. Trường hợp mơ hồ kinh điển: Supplier và Callable

Hai interface này cùng nhận **không đối số** và trả kết quả nhưng có ý nghĩa API khác nhau:

- `Supplier<T>` có `T get()`, không khai báo checked exception tổng quát.
- `Callable<V>` có `V call() throws Exception`, thường dùng cho công việc có kết quả trong môi trường thực thi.

Với hai overload như dưới đây:

~~~java
static String source(java.util.function.Supplier<String> supplier) {
    return "Supplier=" + supplier.get();
}

static String source(java.util.concurrent.Callable<String> callable)
        throws Exception {
    return "Callable=" + callable.call();
}
~~~

Lời gọi sau **cố ý không biên dịch**:

~~~java
// System.out.println(source(() -> "hello"));
// LỖI: source(Supplier<String>) và source(Callable<String>) cùng phù hợp.
~~~

Không thể dựa vào việc `Callable.call()` khai báo `throws Exception` để khẳng định compiler phải ưu tiên `Supplier`. Khi lambda không ném checked exception, cả hai vẫn có thể phù hợp.

### 4.1. Cách sửa 1: ép kiểu lambda tại điểm gọi

~~~java
System.out.println(source(
        (java.util.function.Supplier<String>) () -> "hello"));

System.out.println(source(
        (java.util.concurrent.Callable<String>) () -> "hello"));
~~~

Khi đó compiler biết chính xác kiểu đích cần dùng. Ép kiểu này **không chuyển một object đã tạo sang interface ngẫu nhiên**; nó cung cấp target type cho quá trình kiểm tra và chuyển đổi lambda.

### 4.2. Cách sửa 2: khai báo biến có kiểu cụ thể trước

~~~java
java.util.function.Supplier<String> supplier = () -> "hello";
java.util.concurrent.Callable<String> callable = () -> "hello";

System.out.println(source(supplier));
System.out.println(source(callable));
~~~

Kiểu biến là một tín hiệu rõ ràng, hữu ích khi callback được dùng nhiều lần hoặc cần tên nghiệp vụ.

### 4.3. Cách sửa 3: đặt tên phương thức theo hợp đồng

Nếu có quyền thiết kế API và hai overload thực sự mang ý nghĩa khác nhau, hai tên riêng như `fromSupplier(...)` và `fromCallable(...)` có thể giúp tránh việc mọi caller phải cast, đồng thời làm contract checked exception rõ hơn. Đây thường là phương án dễ đọc nhất cho API công khai thường xuyên nhận lambda.

## 5. Lambda trả giá trị và lambda dạng void: tránh kết luận từ dấu mũi tên

Một trường hợp quan trọng là overload nhận `Consumer<T>` và `Function<T,R>`:

~~~java
static String transform(java.util.function.Consumer<String> action) {
    action.accept("abcd");
    return "Consumer";
}

static String transform(java.util.function.Function<String, Integer> mapper) {
    return "Function=" + mapper.apply("abcd");
}
~~~

Lời gọi **không rõ ràng** sau đã được kiểm tra với Java 17:

~~~java
// LỖI BIÊN DỊCH: cả hai overload đều phù hợp.
// transform(s -> s.length());
~~~

Vì `s.length()` là một **method invocation expression**, nó thuộc nhóm *statement expression*. Java cho phép expression-bodied lambda chứa statement expression được diễn giải theo hợp đồng `void`, ngay cả khi lời gọi phương thức tự nó trả về một giá trị. Đồng thời, nó cũng có thể tương thích với functional interface trả một giá trị.

**Do đó không được khẳng định** “`s -> s.length()` trả `int` nên chắc chắn compiler sẽ chọn `Function`”. Trong cặp overload này, cả `Consumer<String>` và `Function<String,Integer>` đều có thể phù hợp và không có lựa chọn duy nhất.

Ngược lại, biểu thức toán học không phải *statement expression* không tự trở thành body tương thích `void`. Kiểu tương thích còn phụ thuộc ngữ cảnh; hãy sử dụng block khi muốn làm rõ.

### 5.1. Làm rõ bằng body dạng block

Khi body có một `return expression;`, nó diễn đạt kết quả cho functional interface có đầu ra khác `void`:

~~~java
System.out.println(transform((String s) -> {
    return s.length();
}));
// Function=4
~~~

Khi body thực hiện một statement rồi kết thúc bình thường, nó phù hợp với hợp đồng `void`:

~~~java
System.out.println(transform((String s) -> {
    s.length();
}));
// Consumer
~~~

Đoạn thứ hai chỉ dùng để **thử quy tắc overload**, vì tự gọi `length()` rồi bỏ kết quả không phải thao tác mang ý nghĩa nghiệp vụ. Trong code thật, dùng một action rõ ràng như log, ghi nhận, hoặc gọi phương thức trả `void`.

### 5.2. Làm rõ bằng ép kiểu hoặc biến

~~~java
System.out.println(transform(
        (java.util.function.Function<String,Integer>) s -> s.length()));
// Function=4

System.out.println(transform(
        (java.util.function.Consumer<String>) s -> s.length()));
// Consumer
~~~

Trong dòng `Consumer`, giá trị int từ `String.length()` bị bỏ qua theo ngữ nghĩa của statement expression. Cả hai đều **biên dịch được** trong Java 17. Nếu mục đích thực sự là tính độ dài, phiên bản `Function` hoặc `ToIntFunction<String>` (nếu API nhận) sẽ rõ hơn.

## 6. Trường hợp không mơ hồ: dạng lambda chỉ phù hợp một overload

Không phải cứ có nhiều overload nhận functional interface là mơ hồ.

Ví dụ:

~~~java
static String action(Runnable work) {
    work.run();
    return "Runnable";
}

static String action(java.util.function.Supplier<Integer> supplier) {
    return "Supplier=" + supplier.get();
}
~~~

Các lời gọi:

~~~java
System.out.println(action(() -> 42)); 
// Supplier=42

System.out.println(action(() -> System.out.print("run ")));
// In "run " rồi "Runnable".
~~~

**Giải thích:**

- `() -> 42` có expression body là literal số, **không** phải statement expression. Nó phù hợp với hàm trả giá trị, không phù hợp với `Runnable.run(): void`.
- `() -> System.out.print("run ")` gọi một phương thức thực sự trả `void`. Nó phù hợp `Runnable` và không trả một `Integer` cho `Supplier<Integer>`.
- Những kết quả trên là do **hình dạng body và kiểu đích**, không phải do compiler chọn một tên interface ưu tiên theo mặc định.

Với lambdas dạng block, hãy nhìn đến việc mọi luồng chạy có trả giá trị hay không. Một body dạng `{ return 42; }` tương thích với hàm trả giá trị; body `{ System.out.println("x"); }` hoàn thành bình thường và tương thích với hàm `void`. Body chứa biểu thức/câu lệnh phức tạp hơn chịu quy tắc cụ thể của JLS §15.27.2; không thể chỉ đếm số `return` mà suy luận tùy tiện.

## 7. Most specific: khi một interface là subtype của interface khác

Đôi khi cả hai overload đều nhận được lambda nhưng Java vẫn có cách lựa chọn duy nhất.

Ví dụ:

~~~java
static String prefer(java.util.function.Function<String, String> f) {
    return "Function";
}

static String prefer(java.util.function.UnaryOperator<String> f) {
    return "UnaryOperator";
}
~~~

`UnaryOperator<String>` kế thừa `Function<String,String>`. Khi gọi:

~~~java
System.out.println(prefer(s -> s.trim()));
// UnaryOperator
~~~

Compiler chọn overload nhận `UnaryOperator<String>` vì kiểu tham số này **cụ thể hơn** kiểu `Function<String,String>` trong quan hệ kế thừa. Trường hợp này khác với `Supplier` và `Callable`: hai interface đó không có quan hệ subtype giúp phá thế hòa.

**Lưu ý:** “cụ thể hơn” là một khái niệm theo đặc tả overload, không chỉ luôn là “interface này extends interface kia”. JLS có quy tắc bổ sung về most-specific functional interfaces, đặc biệt với kiểu trả về primitive/reference, explicit/implicit lambda và generic. Với trường hợp khó, nên kiểm chứng bằng `javac --release 17` hoặc javac đúng phiên bản dự án.

## 8. Lambda ngầm định, lambda ghi rõ kiểu, method reference và suy luận

### 8.1. Viết kiểu tham số tường minh có thể cung cấp thêm ràng buộc

Ví dụ `x -> ...` chưa có loại x cụ thể khi target typing diễn ra. Với `(String x) -> ...`, kiểu String ghi ngay trong body làm một số overload không phù hợp nếu chúng yêu cầu một kiểu tham số khác.

Tuy nhiên, **ghi kiểu tham số tường minh không phải cách sửa mọi ambiguous call**. Trong ví dụ `Supplier<String>` và `Callable<String>`, lambda không nhận tham số; ghi `() -> "x"` không có thông tin nào phân biệt hai giao diện. Với hai overload có cùng tham số `String` và cùng khả năng xử lý body, việc ghi `(String s) -> s.length()` cũng chưa chắc đủ.

### 8.2. Method reference cũng được target type kiểm tra

Cú pháp `String::trim` không tự quyết định phải là `Function<String,String>` hay `Consumer<String>`; mỗi ngữ cảnh API có thể có những quy tắc chọn riêng. **Không suy từ kết quả overload của lambda để khẳng định mọi method reference giống hệt.**

Đối với chính cặp overload sau:

~~~java
static String pick(java.util.function.Consumer<String> action) {
    return "Consumer";
}

static String pick(java.util.function.Function<String, String> mapper) {
    return "Function";
}
~~~

Với Java 17, gọi `pick(String::trim)` **biên dịch được** và chọn overload `Function<String,String>` (kết quả `"Function"`). Đây là một ví dụ cho thấy *exact method reference* và quy tắc most-specific không luôn giống trường hợp biểu thức lambda dạng `s -> s.trim()`. Hãy kiểm tra từng cặp chữ ký và từng hình dạng lời gọi.

### 8.3. Lambda không có target type không thể gán cho var

~~~java
// LỖI BIÊN DỊCH: không có target type cho lambda.
// var task = () -> "hello";
~~~

Dùng kiểu functional interface rõ ràng:

~~~java
java.util.function.Supplier<String> task = () -> "hello";
~~~

Hoặc ép kiểu khi truyền lambda vào overload. Toán tử cast không chỉ là cách “ép kết quả” sau khi chạy; nó có thể xác định functional interface đích trước khi compiler kiểm tra lambda.

### 8.4. Kiểu trả về của method chứa overload không phải luôn đủ để chọn overload

Đừng mặc định rằng kiểu biến nhận kết quả sẽ chọn phương thức overload theo kiểu trả về của phương thức đó. Java không cho phép nạp chồng **chỉ khác kiểu trả về**; trong đa số lời gọi overload thông thường, phân giải căn cứ trước hết vào kiểu và hình dạng đối số. Bối cảnh generic/poly expression có những tương tác suy luận riêng nhưng không nên dựa vào phép gán kết quả để chữa một ambiguous lambda khi compiler đã báo mơ hồ.

## 9. Chương trình Java 17 hoàn chỉnh có kết quả đã kiểm chứng

Tạo tệp **OverloadDemo.java**. Những lời gọi ambiguous được trình bày riêng ở mục 10 dưới dạng mã **cố ý không biên dịch**; chương trình này chỉ chứa cách gọi hợp lệ để có thể chạy độc lập.

~~~java
import java.util.concurrent.Callable;
import java.util.function.*;

public class OverloadDemo {
    static String source(Supplier<String> job) {
        return "Supplier=" + job.get();
    }

    static String source(Callable<String> job) throws Exception {
        return "Callable=" + job.call();
    }

    static String action(Runnable run) {
        run.run();
        return "Runnable";
    }

    static String action(Supplier<Integer> get) {
        return "Supplier=" + get.get();
    }

    static String transform(Consumer<String> use) {
        use.accept("abcd");
        return "Consumer";
    }

    static String transform(Function<String,Integer> use) {
        return "Function=" + use.apply("abcd");
    }

    static String prefer(Function<String,String> f) {
        return "Function";
    }

    static String prefer(UnaryOperator<String> f) {
        return "UnaryOperator";
    }

    public static void main(String[] args) throws Exception {
        System.out.println(source((Supplier<String>) () -> "hello"));
        System.out.println(source((Callable<String>) () -> "hello"));
        System.out.println(action(() -> 42));
        System.out.println(action(() -> System.out.print("run ")));
        System.out.println(transform((String s) -> {
            return s.length();
        }));
        System.out.println(transform((String s) -> {
            s.length();
        }));
        System.out.println(prefer(s -> s.trim()));
    }
}
~~~

Chạy từ thư mục chứa file:

~~~bash
javac --release 17 OverloadDemo.java
java OverloadDemo
~~~

Stdout **chính xác** đã xác minh:

~~~text
Supplier=hello
Callable=hello
Supplier=42
run Runnable
Function=4
Consumer
UnaryOperator
~~~

Dòng `run Runnable` xuất hiện vì `System.out.print("run ")` không thêm xuống dòng, rồi `System.out.println(action(...))` in `Runnable` và xuống dòng.

Các dòng còn lại chứng minh:
- Cast phân biệt hai overload `source`.
- Body literal 42 chọn `Supplier<Integer>`; body gọi `print` trả void chọn `Runnable`.
- Block có `return s.length();` chọn `Function<String,Integer>`.
- Block chỉ gọi `s.length();` rồi kết thúc bình thường chọn `Consumer<String>`.
- Overload `UnaryOperator<String>` cụ thể hơn `Function<String,String>`.

## 10. Ví dụ lỗi biên dịch cố ý và cách chẩn đoán

### 10.1. Hai interface không quan hệ subtype, cùng nhận no-arg lambda

Tệp ví dụ **AmbiguousSource.java** (cố ý lỗi):

~~~java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class AmbiguousSource {
    static void pick(Supplier<String> s) {}
    static void pick(Callable<String> c) {}
    void bad() {
        pick(() -> "hello"); // ambiguous
    }
}
~~~

Biên dịch bằng `javac --release 17 AmbiguousSource.java` sẽ thất bại với thông báo: `reference to pick is ambiguous`, vì cả hai overload `pick(Supplier<String>)` và `pick(Callable<String>)` đều phù hợp.

### 10.2. Một biểu thức gọi phương thức phù hợp cả void và giá trị

Tệp ví dụ **AmbiguousTransform.java** (cố ý lỗi):

~~~java
import java.util.function.*;

class AmbiguousTransform {
    static void pick(Consumer<String> c) {}
    static void pick(Function<String, Integer> f) {}
    void bad() {
        pick(s -> s.length()); // ambiguous
    }
}
~~~

Biên dịch bằng `javac --release 17 AmbiguousTransform.java` cũng thất bại với thông báo `reference to pick is ambiguous`. Đây là một tình huống dễ nhầm, bởi bản thân `String.length()` trả `int` nhưng method invocation expression vẫn là dạng body void-compatible.

**Khi gặp lỗi:** đọc tất cả chữ ký được compiler liệt kê, xác định kiểu SAM từng tham số, xem body lambda có phù hợp hơn một kiểu hay không, rồi làm rõ bằng biến có kiểu, cast, block, hoặc đổi cách thiết kế API.

Không nên thử “khắc phục” bằng cách ép kiểu kết quả lambda một cách ngẫu nhiên: `s -> (int) s.length()` vẫn có thể là một expression-bodied lambda chứa cast expression khác loại statement expression; nếu cần điều khiển kết quả chọn overload có chủ đích, nên sử dụng cách viết tường minh và kiểm chứng bằng compiler.

## 11. Quy tắc khi thiết kế API nhận nhiều callback

Overload nhận functional interface là hợp lý khi các kiểu thể hiện các lựa chọn thực sự rõ ràng, nhưng dễ gây rắc rối nếu các interface không quan hệ kế thừa mà có function descriptor giống nhau.

**Ưu tiên các hướng sau:**

1. **Đặt tên theo chức năng** khi semantics khác biệt: `executeTask(Callable<T>)` và `supplyValue(Supplier<T>)` rõ hơn hai `run(...)` gần như đồng hình.
2. **Nếu giữ overload, đưa ví dụ call site không mơ hồ** trong tài liệu: cast hoặc khai báo callback có kiểu.
3. **Tránh API yêu cầu cast thường xuyên cho các lambda phổ biến.** Nếu người dùng nào cũng phải viết `(Supplier<T>) () -> ...`, đó có thể là dấu hiệu tên API đang che giấu khác biệt semantics.
4. **Đừng tạo overload chỉ khác generic type argument có cùng erasure.** Java không hỗ trợ cặp khai báo như `use(Supplier<String>)` và `use(Supplier<Integer>)`.
5. **Xét checked exception và lifecycle thực sự.** `Callable<T>` có thể ném checked exception, `Supplier<T>` theo hợp đồng chuẩn không khai báo checked exception; việc chọn interface ảnh hưởng cách caller xử lý lỗi.
6. **Kiểm thử bằng đúng phiên bản Java mục tiêu.** Với tình huống lambda/overload phức tạp, chọn theo trực giác là không đủ; compiler là bằng chứng sát nhất với hành vi ngôn ngữ của phiên bản dự án.

Đặt tên callback rõ cũng quan trọng:

~~~java
Supplier<String> defaultName = () -> "Guest";
Callable<String> queryName = () -> "Guest";
~~~

Dù hai lambda cùng body, các biến có tên và kiểu rõ ràng giúp reviewer hiểu được việc cung cấp giá trị tức thời hay biểu diễn một công việc được gọi.

## 12. Tình huống thực tế: builder, async API và stream processing

Giả sử API cung cấp cả:
- Một phương thức lấy giá trị mặc định khi cần.
- Một phương thức chạy tác vụ có thể phát sinh checked exception.

Nếu cả hai cùng tên `execute(...)` và nhận các callback no-arg trả dữ liệu, lời gọi lambda ngắn nhất `execute(() -> compute())` dễ ambiguous. Hai tên `supplyFallback(...)` và `callTask(...)` giúp diễn đạt contract.

Trong Stream API, lời gọi thường không gặp vấn đề này vì các bước đã có tên riêng theo ý nghĩa: `filter(Predicate)`, `map(Function)`, `forEach(Consumer)`. Khi tự viết API tương tự, đặt tên theo thao tác có thể giúp hạn chế overload cùng hình dạng SAM.

Với builder có nhiều overload như `onSuccess(Consumer<T>)` và `onSuccess(Function<T,R>)`, một callback dạng `x -> logAndReturn(x)` có thể là statement expression trả giá trị, dẫn đến những tương tác lựa chọn khó đoán. Tách thành các tên như `observeSuccess(...)` và `transformSuccess(...)` hoặc yêu cầu callback được khai báo kiểu rõ ràng sẽ hỗ trợ người dùng hơn.

## 13. Checklist xử lý lời gọi ambiguous

Khi compiler báo `reference to ... is ambiguous`:

1. **Đọc chữ ký các overload** mà compiler đưa ra: có bao nhiêu đối số, kiểu tham số và quan hệ subtype giữa các kiểu.
2. **Nhìn vào function descriptor của từng interface**: arity, kiểu tham số, kiểu trả về, checked exception.
3. **Đọc dạng lambda:** expression body hay block body; statement expression, literal, hoặc body có `return`.
4. **Kiểm tra kiểu đích** của lambda và tính hợp lệ với mỗi ứng viên. Đừng tự suy luận lambda đã có một kiểu độc lập.
5. **Làm rõ có chủ đích:** ép kiểu lambda sang interface muốn gọi, khai báo biến callback có kiểu, hoặc viết block rõ hành vi `void`/trả giá trị.
6. **Nếu đây là API tự thiết kế:** cân nhắc tên phương thức khác nhau, thay vì yêu cầu nhiều caller viết cast.
7. **Chạy `javac --release 17`** với ví dụ thu gọn nếu khó xác định nhất, và chỉ đưa kết quả vào tài liệu sau khi kiểm chứng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai overload `accept(Supplier<String>)` và `accept(Callable<String>)` nhận `accept(() -> "ok")`. Kết quả là gì?

**Đáp án:** ambiguous; hai kiểu độc lập về kế thừa nhưng đều tương thích với no-arg lambda trả String. Để chọn, khai báo kiểu/cast hoặc đổi API.

**Câu 2.** Vì sao `Consumer<String>` và `Function<String,Integer>` có thể đều phù hợp với `s -> s.length()`?

**Đáp án:** `s.length()` là method invocation statement expression nên có thể là body void-compatible; đồng thời nó trả int và có thể là body value-compatible.

**Câu 3.** Với cặp overload `run(Runnable)` và `run(Supplier<Integer>)`, lời gọi `run(() -> 10)` chọn gì?

**Đáp án:** `Supplier<Integer>`; literal 10 không phải statement expression nên không tạo body void-compatible.

**Câu 4.** Với overload `choose(Function<String,String>)` và `choose(UnaryOperator<String>)`, tại sao lambda `s -> s.trim()` có một lựa chọn?

**Đáp án:** `UnaryOperator<String>` là subtype của `Function<String,String>` nên là overload cụ thể hơn trong cặp này.

**Câu 5.** Tại sao `var fn = () -> "hi";` không giải quyết việc chọn overload?

**Đáp án:** lambda cần target type; `var` không cung cấp một functional interface cụ thể để suy luận từ initializer lambda này.

**Câu 6.** Một API có nhiều callback mang tên `execute` nhưng compiler thường ambiguous; nên làm gì?

**Đáp án:** làm rõ các trường hợp sử dụng bằng tên phương thức theo hợp đồng, hoặc cung cấp biến callback/cast tường minh ở nơi gọi; tránh bắt mọi người dùng đoán overload.

## Tài liệu tham khảo

- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).
- [JLS 17, §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27).
- [JLS 17, §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13).
- [JLS 17, §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).
- [JLS 17, §8.4.2 — Method Signature và type erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2).

**Ghi nhớ:** Nạp chồng nhận lambda phải xét **kiểu đích của từng functional interface**, **dạng và tính tương thích của lambda**, rồi áp dụng quy tắc **most-specific**. Hai overload cùng phù hợp không có nghĩa compiler sẽ đoán ý định của lập trình viên. Khi không có ứng viên duy nhất, hãy dùng kiểu rõ ràng hoặc thiết kế API có tên diễn đạt đúng ý nghĩa, và kiểm chứng các ca khó bằng compiler.
