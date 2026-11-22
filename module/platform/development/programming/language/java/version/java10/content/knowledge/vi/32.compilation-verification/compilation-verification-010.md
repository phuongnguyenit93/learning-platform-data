# Kiểm thử dương và kiểm thử lỗi biên dịch cho các trường hợp `var`

## 1. Bài học: kiểm chứng quy tắc Java, không chỉ nhìn ví dụ chạy được

Từ **Java 10**, **JEP 286 — Local-Variable Type Inference** cho phép viết:

~~~java
var count = 10;
var title = "Java";
var numbers = java.util.List.of(1, 2, 3);
~~~

Ở đây `var` không có nghĩa biến mang kiểu động. **`javac` xác định kiểu tĩnh của local variable từ initializer**, và mọi phép sử dụng/gán về sau vẫn được kiểm tra như khi viết kiểu tường minh.

Ví dụ:

~~~java
var value = 10;  // kiểu int
value = 20;      // Hợp lệ
value = "ten";   // Lỗi biên dịch: String không thể gán cho int
~~~

Trong chủ đề **“Biên dịch và kiểm chứng”**, đề mục **“Kiểm thử dương và kiểm thử lỗi biên dịch cho các trường hợp var”** đòi hỏi phân biệt rõ:

- **Positive compile test:** một chương trình/đoạn Java **hợp lệ** phải được compiler **chấp nhận**. Khi có `main`, có thể kiểm tra thêm stdout và hành vi runtime.
- **Negative compile test:** một đoạn Java **cố ý vi phạm JLS** phải bị compiler **từ chối** và sinh diagnostic **ERROR**. Bị từ chối như mong đợi là **PASS của ca âm**.
- **Compiler/tooling failure:** lệnh compile không chạy được, sai classpath, không hỗ trợ `--release` hay thiếu quyền tạo output là lỗi **hạ tầng kiểm thử**, không tự động chứng minh mã Java sai theo rule.
- **Runtime test:** chỉ áp dụng cho những source đã biên dịch; không thể “chạy” một fixture đang được thiết kế để compile fail.

Bài ưu tiên kiến thức **hiện còn hiệu lực ở Java 17/21/25/26**, và nêu rõ phần nào là Java 10, phần nào được bổ sung ở Java 11. Toàn bộ ví dụ có thể dùng trên JDK hiện đại; bộ lab đã được thử bằng **OpenJDK 24.0.2**.

### Mục tiêu cần đạt

1. Giải thích được `var` là **restricted type name**, không phải dynamic typing và cũng không cấm mọi identifier tên `var`.
2. Liệt kê chính xác vị trí cho phép local `var`: block, basic `for`, enhanced `for` và try-with-resources.
3. Viết positive tests cho primitives, String, List, generics, array, `final var` và các vòng lặp.
4. Viết negative tests cho `null` không có kiểu, không có initializer, nhiều declarators, array initializer rời, bracket pairs và self-reference.
5. Chứng minh `var` **không** là kiểu của field, return type, ordinary method parameter hoặc catch parameter.
6. Phân biệt lambda `var` được thêm ở **Java 11 (JEP 323)** với local `var` của **Java 10 (JEP 286)**.
7. Hiểu target type của lambda và method reference, tránh `var f = () -> ...`.
8. Xác minh kiểu generic khi viết `var list = new ArrayList<>()`.
9. Dùng `javac --release` để kiểm tra chính xác ranh giới version.
10. Chạy harness Java 17+ dùng **`javax.tools.JavaCompiler`** và `DiagnosticCollector` cho **18 ca dương, 18 ca âm**.
11. Dùng kết quả compiler và diagnostics thay vì hard-code thông báo lỗi tiếng Anh theo một JDK.
12. Tách fixture compile-fail khỏi source set chính trong CI.

## 2. `var` được xác định kiểu vào lúc nào?

Trong:

~~~java
var number = 42;
var name = "Java";
var labels = java.util.List.of("A", "B");
~~~

kiểu static lần lượt là `int`, `String` và `List<String>`. Compiler chỉ dựa vào **kiểu của initializer**, không phân tích các câu lệnh gán về sau để chọn một kiểu rộng hơn.

~~~java
var amount = 1;      // int
amount = 2;          // OK
amount = 3.14;       // ERROR
~~~

Muốn biến có thể chứa những giá trị kiểu `Number` khác nhau thì định nghĩa type phù hợp:

~~~java
Number amount = 1;
amount = 3.14;       // OK
~~~

**`var` không thể dùng thay cho `Object` mọi nơi.** Kiểu của initializer có thể là một generic type, intersection type, anonymous class type hoặc loại suy ra khác theo JLS; vẫn có các ràng buộc type-safe rõ ràng.

### 2.1. `var` là restricted type name

`var` là **restricted type name** trong Java, không phải keyword thông thường cấm sử dụng ở mọi nơi. Điều này có nghĩa hai câu lệnh sau có thể hợp lệ ở vị trí local variable:

~~~java
int var = 5;
var var = 10;
~~~

Ở dòng thứ hai, chữ `var` thứ nhất yêu cầu type inference, chữ thứ hai là identifier của biến. Đây là cú pháp **hợp lệ nhưng không nên ưu tiên** về readability. Vì vậy một negative test “tên biến là `var` nên compile fail” sẽ sai về Java hiện đại.

Tuy nhiên, khai báo một class/interface có tên restricted type name `var` lại bị hạn chế theo quy tắc tên kiểu. Phân biệt chính xác **vị trí cú pháp** thay vì kết luận từ chuỗi chữ cái.

### 2.2. Local type inference không phải keyword dùng trong mọi vị trí

~~~java
class Example {
    var field = 1;                   // ERROR: field
    var result() { return 1; }       // ERROR: method return type
    void process(var parameter) {}   // ERROR: ordinary method parameter
}
~~~

Khi viết APIs, phải dùng kiểu rõ ràng cho fields/parameters/returns:

~~~java
class Example {
    private int field = 1;

    int result() {
        return field;
    }

    void process(int parameter) {
        field = parameter;
    }
}
~~~

Java 11 cho phép `var` ở **lambda parameters** là một trường hợp **khác** với ordinary method parameters; không mở rộng suy luận lambda sang phương thức bình thường.

## 3. Ma trận các ca dương

| Ca | Vị trí / ý nghĩa | Source hợp lệ | Chứng cứ cần xem |
| --- | --- | --- | --- |
| P01 | Local kiểu số nguyên | `var x = 42;` | Compiler nhận kiểu `int`. |
| P02 | Local kiểu chuỗi | `var text = "Java";` | Compiler nhận `String`. |
| P03 | List generic | `var xs = List.of("A", "B");` | `xs.get(0)` dùng như `String`. |
| P04 | Classic `for` | `for (var i = 0; i < 3; i++)` | Local kiểu `int`. |
| P05 | Enhanced `for` | `for (var s : List.of("A"))` | Kiểu phần tử `String`. |
| P06 | Try-with-resources | `try (var r = new StringReader("x"))` | `r` là resource `AutoCloseable`. |
| P07 | `final var` | `final var n = 5;` | Suy `int` và không gán lại. |
| P08 | Tạo array có kiểu | `var arr = new int[]{1,2};` | Suy kiểu `int[]`. |
| P09 | Lambda có `var` + target | `Function<String,Integer> f=(var s)->s.length();` | Hợp lệ từ Java 11. |
| P10 | Nhiều lambda `var` | `BiFunction<...> f=(var a,var b)->a+b;` | Không pha trộn kiểu. |
| P11 | `var` làm tên biến | `var var = 10;` | Hợp lệ cú pháp. |
| P12 | Generic tường minh | `var xs=new ArrayList<String>();` | `ArrayList<String>`. |
| P13 | Diamond không có generic target | `var xs=new ArrayList<>();` | `ArrayList<Object>` trong ca này; `get` trả Object. |
| P14 | Cast `null` rõ kiểu | `var s=(String)null;` | Suy kiểu `String`, giá trị có thể null. |
| P15 | Method reference có target | `Function<String,Integer> f=String::length;` | Hợp lệ. |
| P16 | Cast method reference | `var f=(Function<String,Integer>)String::length;` | Hợp lệ. |
| P17 | `--release 10` | `var x=1;` | Local `var` từ Java 10. |
| P18 | `--release 9` control | `int x=1;` | Source hợp lệ ngay cả trước Java 10. |

Không bắt một positive case chỉ “không báo lỗi cú pháp”; khi cần chứng minh **kiểu**, hãy thêm một phép gán có type checking:

~~~java
var strings = java.util.List.of("A", "B");
String first = strings.get(0); // kiểm tra type được suy ra

var numbers = java.util.List.of(1, 2);
Integer firstNumber = numbers.get(0);
~~~

Hai phép gán này buộc compiler kiểm tra kiểu generic; có ý nghĩa hơn việc chỉ thấy `var strings = ...` compile.

### 3.1. Basic `for` và enhanced `for` có quy tắc khác nhau

~~~java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}

for (var s : java.util.List.of("A", "B")) {
    System.out.println(s);
}
~~~

Trong classic `for`, `var i = 0` là local declaration với initializer. Trong enhanced `for`, biến vòng lặp được cung cấp phần tử từ array hoặc `Iterable` mỗi lần lặp, nên không tự viết `= ...` vào `var s`. JLS có quy tắc riêng cho inferred type trong enhanced for.

**Không** lấy hạn chế “local var thiếu initializer thì lỗi” rồi kết luận sai rằng `for (var x : values)` không hợp lệ.

### 3.2. Try-with-resources

~~~java
try (var reader = new java.io.StringReader("x")) {
    System.out.println((char) reader.read());
}
~~~

Kiểu suy ra là `StringReader`, hỗ trợ `AutoCloseable`. Java đóng resource theo try-with-resources.

Trường hợp sau lại phải bị từ chối:

~~~java
try (var count = 42) {
    System.out.println(count);
}
~~~

`int` không phải `AutoCloseable`. Điều này minh họa **initializer có kiểu hợp lệ vẫn chưa đủ** để resource declaration được chấp nhận; cần thêm điều kiện vị trí resource.

### 3.3. `final var`

~~~java
final var list = new java.util.ArrayList<String>();
list.add("A"); // OK: mutate object
// list = new java.util.ArrayList<>(); // ERROR: final variable
~~~

`final` cấm gán lại reference, không khiến chính đối tượng `ArrayList` trở thành immutable.

## 4. Ma trận các ca âm bắt buộc

Mỗi mảnh dưới đây **cố ý không hợp lệ**. Trong bài lab ở phần 8, từng trường hợp được biên dịch **riêng** và expected outcome là `REJECTED`.

| Ca | Mã nguồn sai | Quy tắc bị vi phạm |
| --- | --- | --- |
| N01 | `var x;` | Local `var` thiếu initializer. |
| N02 | `var x = null;` | `null` không có type thích hợp để suy luận. |
| N03 | `var a=1,b=2;` | Nhiều variable declarators với `var`. |
| N04 | `var a={1,2};` | Array initializer rời, không có array type rõ. |
| N05 | `var a[]=new int[2];` | Brackets tại tên biến bị cấm với `var`. |
| N06 | `var a=a;` | Tự tham chiếu biến trong initializer. |
| N07 | `static var x=1;` | Không dùng `var` làm field type. |
| N08 | `static var make(){return 1;}` | Không dùng `var` làm return type. |
| N09 | `void f(var x){}` | Không dùng `var` cho ordinary method parameter. |
| N10 | `var f=()->1;` | Lambda cần target functional interface type. |
| N11 | `var f=String::length;` | Method reference cần target type. |
| N12 | `(var a, String b)->a+b` | Không trộn `var` với kiểu tường minh trong cùng lambda parameter list. |
| N13 | `var xs=new ArrayList<>(); String x=xs.get(0);` | Diamond suy `Object`, không gán cho `String`. |
| N14 | `catch(var e){}` | `var` không hợp lệ cho catch parameter. |
| N15 | `var x=1; x="text";` | `x` suy kiểu `int`, không dynamic. |
| N16 | `Function<String,Integer> f=var s->s.length();` | Lambda `var` phải có cặp ngoặc `(var s)`. |
| N17 | `var x=1;` với `--release 9` | Java 9 chưa có local-variable inference. |
| N18 | `Function<String,Integer> f=(var s)->s.length();` với `--release 10` | Lambda var chỉ có từ Java 11. |

### 4.1. Những giới hạn trong JLS 14.4

Với một local declaration dùng `var`, JLS hiện hành yêu cầu:

- Một **variable declarator**.
- Có initializer, trừ những vị trí quy định riêng như enhanced `for`.
- Không có `[]` bổ sung tại declarator ID.
- Không dùng array initializer trực tiếp dạng `{...}`.
- Không tự tham chiếu tới chính biến vừa khai báo trong initializer.
- Kiểu initializer không phải **null type**, và không phải một poly expression thiếu target type như lambda/method reference.

Ví dụ sửa lỗi:

~~~java
// Sai: var a = 1, b = 2;
var a = 1;
var b = 2;

// Sai: var arr = {1,2};
var arr = new int[] { 1, 2 };

// Sai: var x = null;
String x = null;
var y = (String) null; // compile được, nhưng vẫn có thể NPE khi dùng
~~~

**Cẩn thận:** `var y=(String)null` là positive compile test, nhưng `y.length()` có thể gây `NullPointerException` lúc chạy. Kiểm tra compile-time type không thay thế runtime safety tests.

### 4.2. Không ghép dấu mảng vào `var`

~~~java
var[] a = new int[2];   // ERROR
var a[] = new int[2];   // ERROR
var a = new int[2];     // OK, suy int[]
var a = new int[]{1,2}; // OK, suy int[]
~~~

`var` đại diện cho **cả kiểu** được suy ra, không phải một loại “element type” có thể thêm `[]` bằng tay.

### 4.3. Lambda/method reference cần target type

~~~java
var f = () -> 42;                // ERROR
var g = String::length;         // ERROR

java.util.function.Supplier<Integer> f2 = () -> 42; // OK

java.util.function.Function<String, Integer> g2 =
        String::length;         // OK

var g3 =
        (java.util.function.Function<String, Integer>)
        String::length;         // OK
~~~

JavaCompiler không thể suy ra một functional interface duy nhất chỉ từ lambda/method reference ở vị trí initializer của local `var`, vì có nhiều interface khác nhau có thể tương thích. Khi có target type, compiler mới áp những quy tắc kiểm tra chữ ký phù hợp.

### 4.4. Kiểu generic không tự thay đổi từ các phép dùng về sau

~~~java
var xs = new java.util.ArrayList<>();
xs.add("hello");

Object a = xs.get(0); // OK
String b = xs.get(0); // ERROR trong ca này
~~~

Ở đây `var xs = new ArrayList<>()` không có target generic type `String`. Compiler suy `ArrayList<Object>`, nên `get` trả `Object`. Việc gọi `add("hello")` về sau **không sửa ngược** kiểu generic đã suy.

Hai cách làm rõ:

~~~java
var xs1 = new java.util.ArrayList<String>();
String a = xs1.get(0);

java.util.List<String> xs2 = new java.util.ArrayList<>();
String b = xs2.get(0);
~~~

Hai dòng `get(0)` có thể ném IndexOutOfBoundsException nếu chạy khi list rỗng, nhưng **compile được**. Phân biệt **compile-time type contract** với logic runtime.

## 5. Phân biệt Java 10 và Java 11 bằng negative/positive tests

**Java 10 — JEP 286:** local `var`.

**Java 11 — JEP 323:** cho phép `var` làm **lambda formal parameter type** khi có target functional interface; mọi parameters của cùng lambda phải dùng hình thức phù hợp, không pha trộn `var` với kiểu tường minh hoặc kiểu ngầm.

Hợp lệ Java 11+:

~~~java
java.util.function.Function<String, Integer> length =
        (var text) -> text.length();

java.util.function.BiFunction<String, String, String> join =
        (var left, var right) -> left + right;
~~~

Không hợp lệ:

~~~java
java.util.function.BiFunction<String, String, String> bad1 =
        (var left, String right) -> left + right;

java.util.function.BiFunction<String, String, String> bad2 =
        (var left, right) -> left + right;

java.util.function.Function<String, Integer> bad3 =
        var text -> text.length();
~~~

Điểm hay bị nhầm:

~~~java
var f = (var text) -> text.length(); // vẫn ERROR
~~~

`var` trong lambda parameter **không thay thế** việc cần target type cho **toàn bộ lambda expression**.

### 5.1. `--release` giúp chứng minh ranh giới phiên bản

Trong JDK có `javac` hỗ trợ cả các release tương ứng:

~~~bash
javac --release 9 Example.java
javac --release 10 Example.java
javac --release 17 Example.java
~~~

Nếu `Example.java` có local `var`, source9 phải bị từ chối; source10 và source17 chấp nhận khi mã còn lại tương thích.

Nếu source có `(var s)->...`, source10 bị từ chối trong khi source17 chấp nhận.

**Không kết luận compiler bị lỗi vì “Java 24 có hỗ trợ var nên source Java 9 cũng phải có”.** `--release` là hợp đồng language/API compatibility theo release được yêu cầu; chạy compiler mới không tự nâng source rules của dự án.

Với những JDK mới có tập `--release` được hỗ trợ khác nhau, xem `javac --help`. Bộ lab dưới đây đã kiểm chứng cụ thể **9, 10 và 17 trên JDK 24.0.2**.

## 6. Chương trình dương độc lập: `VarPositive.java`

Tạo file:

~~~java
import java.io.StringReader;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;

public class VarPositive {
    public static void main(String[] args) throws Exception {
        var number = 10;
        var title = "Java";
        var values = List.of(1, 2, 3);
        var sum = 0;

        for (var value : values) {
            sum += value;
        }

        for (var i = 0; i < 2; i++) {
            sum += i;
        }

        try (var reader = new StringReader("Z")) {
            System.out.println("reader=" + (char) reader.read());
        }

        Function<String, Integer> length =
                (var text) -> text.length();

        BiFunction<Integer, Integer, Integer> add =
                (var a, var b) -> a + b;

        final var phrase = title + "-" + number;
        var array = new int[] { 4, 5 };
        int var = array[0];

        System.out.println("phrase=" + phrase);
        System.out.println("sum=" + sum);
        System.out.println("length=" + length.apply("abc"));
        System.out.println("add=" + add.apply(var, array[1]));
        System.out.println("typeSafety=" +
                (values.get(0) instanceof Integer));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 VarPositive.java
java VarPositive
~~~

**Stdout đã kiểm chứng bằng JDK 24.0.2 với source release 17:**

~~~text
reader=Z
phrase=Java-10
sum=7
length=3
add=9
typeSafety=true
~~~

Vì sao đúng?

- `reader=Z`: `StringReader.read()` trả code point của `Z` phù hợp chuyển về `char`.
- `phrase=Java-10`: nối `"Java"` với số nguyên 10.
- `sum=7`: vòng enhanced `for` cộng `1+2+3=6`, vòng classic cộng `0+1=1`.
- `length=3`: lambda có target `Function<String,Integer>`, `"abc".length()` bằng 3.
- `add=9`: biến `var` có giá trị 4, `array[1]` là 5.
- `typeSafety=true`: phần tử đầu tiên của `List.of(1,2,3)` là `Integer`, đúng kết quả runtime cụ thể; không dùng `instanceof` thay compiler type tests.

**Lưu ý:** Source này dùng `var` trong lambda parameter, cần source level **11+**; vì vậy chọn `--release 17` thay vì `--release 10`. Nếu cần Java 10, dùng lambda `text -> text.length()` với target type đã khai báo.

## 7. Ca âm thủ công: xác minh exit code và diagnostics

Tạo **`BadNull.java`**:

~~~java
public class BadNull {
    public static void main(String[] args) {
        var x = null;
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BadNull.java
~~~

Kết quả mong đợi: compiler từ chối source vì `var` không suy được kiểu từ `null` và trả **exit code khác 0**. Không chạy `java BadNull` như một runtime test; source vốn được thiết kế không compile.

**Không assert nguyên văn một thông báo stderr** kiểu `cannot infer type for local variable` ở mọi JDK. Câu chữ và vị trí lỗi có thể thay theo compiler version, locale, vendor hoặc diagnostic formatting.

Với lệnh shell trong CI, điều cần xác minh là:

- Process `javac` thực sự chạy.
- `--release` đúng.
- Exit code **non-zero** khi source cố ý sai.
- Có ít nhất một diagnostic kind **ERROR**.
- Lỗi thực sự liên quan fixture, không phải không tìm thấy file hoặc lỗi classpath.

Một negative fixture bị từ chối vì **file không tồn tại** không chứng minh gì về quy tắc `var`.

## 8. Bộ kiểm thử biên dịch tự động 36 ca bằng JavaCompiler

**Đây là chương trình Java 17+ độc lập, đã compile/run bằng JDK 24.0.2.**

Điểm thiết kế:

- Từng ca tạo một source class riêng, không dùng file `.java` đang có trong project.
- `SimpleJavaFileObject` cung cấp source từ String.
- `JavaCompiler.getTask` biên dịch một source với `--release` riêng.
- `DiagnosticCollector` kiểm tra có diagnostic `ERROR` khi compile bị từ chối.
- Dương phải compile được; âm phải bị reject. Cả hai mới được tính PASS.
- Các file `.class` tạo ra được đặt trong thư mục hệ thống tạm và dọn sau khi chạy.
- Không phụ thuộc vào lời văn thông báo lỗi cụ thể của một build `javac`.

Tạo **`VarCompileContractLab.java`**:

~~~java
import java.net.URI;
import java.nio.file.*;
import java.util.*;
import javax.tools.*;

public class VarCompileContractLab {
    record Case(String name, boolean shouldCompile,
                int release, String members) {}

    static class Source extends SimpleJavaFileObject {
        final String code;

        Source(String name, String code) {
            super(URI.create("string:///" + name + ".java"), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static boolean compiles(JavaCompiler compiler, Case c,
                            String className, Path dir) throws Exception {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(diagnostics, Locale.ROOT, null)) {
            var code = "class " + className + " { " + c.members() + " }";
            var sources = List.of(new Source(className, code));
            var options = List.of("--release",
                    Integer.toString(c.release()),
                    "-proc:none", "-d", dir.toString());

            boolean ok = Boolean.TRUE.equals(
                    compiler.getTask(null, manager, diagnostics,
                            options, null, sources).call());

            if (!ok && diagnostics.getDiagnostics().stream()
                    .noneMatch(d -> d.getKind() == Diagnostic.Kind.ERROR)) {
                throw new AssertionError("No ERROR diagnostic for " + c.name());
            }
            return ok;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Run on a JDK, not a runtime without javac");
        }

        List<Case> tests = List.of(
            new Case("P01_local_int", true, 17,
                "static void f() { var x = 42; int y = x; }"),
            new Case("P02_local_string", true, 17,
                "static void f() { var text = \"Java\"; String s = text; }"),
            new Case("P03_list_inferred", true, 17,
                "static void f() { var xs = java.util.List.of(\"A\", \"B\"); String s = xs.get(0); }"),
            new Case("P04_basic_for", true, 17,
                "static void f() { for (var i = 0; i < 3; i++) { } }"),
            new Case("P05_enhanced_for", true, 17,
                "static void f() { for (var s : java.util.List.of(\"A\")) { String value = s; } }"),
            new Case("P06_try_resource", true, 17,
                "static void f() throws Exception { try (var reader = new java.io.StringReader(\"x\")) { reader.read(); } }"),
            new Case("P07_final_var", true, 17,
                "static void f() { final var count = 5; int x = count; }"),
            new Case("P08_array_creation", true, 17,
                "static void f() { var arr = new int[] { 1, 2 }; int n = arr[0]; }"),
            new Case("P09_lambda_var_java11plus", true, 17,
                "static void f() { java.util.function.Function<String,Integer> f = (var s) -> s.length(); }"),
            new Case("P10_lambda_two_var", true, 17,
                "static void f() { java.util.function.BiFunction<String,String,String> f = (var a, var b) -> a + b; }"),
            new Case("P11_identifier_named_var", true, 17,
                "static void f() { var var = 10; int n = var; }"),
            new Case("P12_explicit_generic", true, 17,
                "static void f() { var xs = new java.util.ArrayList<String>(); xs.add(\"X\"); String s = xs.get(0); }"),
            new Case("P13_diamond_object", true, 17,
                "static void f() { var xs = new java.util.ArrayList<>(); xs.add(\"X\"); Object s = xs.get(0); }"),
            new Case("P14_casted_null", true, 17,
                "static void f() { var s = (String) null; String x = s; }"),
            new Case("P15_typed_method_reference", true, 17,
                "static void f() { java.util.function.Function<String,Integer> f = String::length; }"),
            new Case("P16_method_ref_cast", true, 17,
                "static void f() { var f = (java.util.function.Function<String,Integer>) String::length; }"),

            new Case("N01_missing_initializer", false, 17,
                "static void f() { var x; }"),
            new Case("N02_null_type", false, 17,
                "static void f() { var x = null; }"),
            new Case("N03_multiple_declarators", false, 17,
                "static void f() { var a = 1, b = 2; }"),
            new Case("N04_array_initializer", false, 17,
                "static void f() { var a = { 1, 2 }; }"),
            new Case("N05_array_brackets", false, 17,
                "static void f() { var a[] = new int[2]; }"),
            new Case("N06_self_reference", false, 17,
                "static void f() { var a = a; }"),
            new Case("N07_field_type", false, 17,
                "static var x = 1;"),
            new Case("N08_method_return_type", false, 17,
                "static var make() { return 1; }"),
            new Case("N09_method_parameter", false, 17,
                "static void f(var x) { }"),
            new Case("N10_lambda_no_target", false, 17,
                "static void f() { var f = () -> 1; }"),
            new Case("N11_method_ref_no_target", false, 17,
                "static void f() { var f = String::length; }"),
            new Case("N12_mixed_lambda_types", false, 17,
                "static void f() { java.util.function.BiFunction<String,String,String> f = (var a, String b) -> a + b; }"),
            new Case("N13_diamond_wrong_assignment", false, 17,
                "static void f() { var xs = new java.util.ArrayList<>(); String s = xs.get(0); }"),
            new Case("N14_catch_parameter", false, 17,
                "static void f() { try { throw new Exception(); } catch (var e) { } }"),
            new Case("N15_inferred_type_not_dynamic", false, 17,
                "static void f() { var x = 1; x = \"text\"; }"),
            new Case("N16_lambda_var_without_parens", false, 17,
                "static void f() { java.util.function.Function<String,Integer> f = var s -> s.length(); }"),
            new Case("N17_java9_no_var", false, 9,
                "static void f() { var x = 1; }"),
            new Case("N18_java10_no_var_lambda", false, 10,
                "static void f() { java.util.function.Function<String,Integer> f = (var s) -> s.length(); }"),
            new Case("P17_java10_var", true, 10,
                "static void f() { var x = 1; int y = x; }"),
            new Case("P18_release9_explicit", true, 9,
                "static void f() { int x = 1; }")
        );

        Path tmp = Files.createTempDirectory("var-compile-contract-");
        int passed = 0;
        try {
            int index = 0;
            for (Case c : tests) {
                boolean actual = compiles(
                        compiler, c, "Fixture" + (++index), tmp);
                boolean pass = actual == c.shouldCompile();

                System.out.printf("%s %s (release=%d, actual=%s)%n",
                        pass ? "PASS" : "FAIL",
                        c.name(), c.release(),
                        actual ? "COMPILED" : "REJECTED");

                if (!pass) {
                    throw new AssertionError(
                            "Unexpected compilation result: " + c.name());
                }
                passed++;
            }
        } finally {
            try (var paths = Files.list(tmp)) {
                for (var file : paths.toList()) {
                    Files.deleteIfExists(file);
                }
            }
            Files.deleteIfExists(tmp);
        }

        System.out.println("summary=" + passed + "/" +
                tests.size() + " expectations matched");
    }
}
~~~

### 8.1. Compile và run harness

~~~bash
javac -encoding UTF-8 --release 17 VarCompileContractLab.java
java VarCompileContractLab
~~~

**Kết quả đã kiểm chứng trên JDK 24.0.2:**

~~~text
PASS P01_local_int (release=17, actual=COMPILED)
PASS P02_local_string (release=17, actual=COMPILED)
PASS P03_list_inferred (release=17, actual=COMPILED)
PASS P04_basic_for (release=17, actual=COMPILED)
PASS P05_enhanced_for (release=17, actual=COMPILED)
PASS P06_try_resource (release=17, actual=COMPILED)
PASS P07_final_var (release=17, actual=COMPILED)
PASS P08_array_creation (release=17, actual=COMPILED)
PASS P09_lambda_var_java11plus (release=17, actual=COMPILED)
PASS P10_lambda_two_var (release=17, actual=COMPILED)
PASS P11_identifier_named_var (release=17, actual=COMPILED)
PASS P12_explicit_generic (release=17, actual=COMPILED)
PASS P13_diamond_object (release=17, actual=COMPILED)
PASS P14_casted_null (release=17, actual=COMPILED)
PASS P15_typed_method_reference (release=17, actual=COMPILED)
PASS P16_method_ref_cast (release=17, actual=COMPILED)
PASS N01_missing_initializer (release=17, actual=REJECTED)
PASS N02_null_type (release=17, actual=REJECTED)
PASS N03_multiple_declarators (release=17, actual=REJECTED)
PASS N04_array_initializer (release=17, actual=REJECTED)
PASS N05_array_brackets (release=17, actual=REJECTED)
PASS N06_self_reference (release=17, actual=REJECTED)
PASS N07_field_type (release=17, actual=REJECTED)
PASS N08_method_return_type (release=17, actual=REJECTED)
PASS N09_method_parameter (release=17, actual=REJECTED)
PASS N10_lambda_no_target (release=17, actual=REJECTED)
PASS N11_method_ref_no_target (release=17, actual=REJECTED)
PASS N12_mixed_lambda_types (release=17, actual=REJECTED)
PASS N13_diamond_wrong_assignment (release=17, actual=REJECTED)
PASS N14_catch_parameter (release=17, actual=REJECTED)
PASS N15_inferred_type_not_dynamic (release=17, actual=REJECTED)
PASS N16_lambda_var_without_parens (release=17, actual=REJECTED)
PASS N17_java9_no_var (release=9, actual=REJECTED)
PASS N18_java10_no_var_lambda (release=10, actual=REJECTED)
PASS P17_java10_var (release=10, actual=COMPILED)
PASS P18_release9_explicit (release=9, actual=COMPILED)
summary=36/36 expectations matched
~~~

**Đọc đúng kết quả:** `PASS N02_null_type (actual=REJECTED)` nghĩa là compiler đã từ chối `var x=null;` như mong đợi, vì vậy **bài test PASS**. Không phải JVM “compile được ca âm”.

### 8.2. Vì sao dùng `DiagnosticCollector`?

Chỉ nhìn `compiler.getTask(...).call() == false` là bước đầu. Bộ harness còn kiểm tra rằng compilation bị từ chối có **`Diagnostic.Kind.ERROR`**. Điều đó giảm nguy cơ đếm nhầm một lỗi runtime của test runner là “compiler đã từ chối source”.

Đối với hệ thống CI nghiêm ngặt hơn:

- Đảm bảo thư mục tạm tạo được và compiler có trên JDK.
- Kiểm tra đúng JDK vendor/build và `--release`.
- Ghi diagnostic codes/line numbers để chẩn đoán khi một fixture bị từ chối vì **nguyên nhân khác với rule `var`** đang test.
- Nếu pin một javac build cụ thể, có thể assert diagnostic code của compiler đó; không coi nó là Java SE API ổn định giữa mọi vendor.
- Duy trì positive control để không nhầm “mọi source đều compile fail” với “negative tests đều đúng”.
- Tách fixture compiler tests khỏi mã sản phẩm.

### 8.3. Vì sao harness dùng in-memory source?

`SimpleJavaFileObject` có thể cung cấp source như một chuỗi `CharSequence`. Các test fragments được đặt vào những class `Fixture1`, `Fixture2`,... khác nhau:

~~~java
var code = "class " + className + " { " + c.members() + " }";
~~~

Mỗi đoạn được compile độc lập và không cần tạo 36 file `.java` trên đĩa. Lợi ích:

- Một lỗi cú pháp của ca âm không làm hỏng việc chạy các ca khác.
- Không đưa invalid Java source vào `src/main/java`.
- Không phụ thuộc các package tự tạo hoặc classpath phụ, vì fixtures chỉ dùng APIs sẵn trong JDK.
- Tránh xung đột class names nhờ tên Fixture khác nhau.
- Kết quả test phản ánh compiler outcome cụ thể.

**Điều kiện:** Phải chạy **JDK có system Java compiler**; nếu `ToolProvider.getSystemJavaCompiler()` trả `null`, test suite nên báo lỗi môi trường, không coi đó là một negative compilation PASS.

## 9. Đối chiếu kiểu suy ra với lỗi runtime

Một compiler test xác minh **kiểu và source legality**, không tự chứng minh hành vi runtime không có ngoại lệ.

Ví dụ:

~~~java
var s = (String) null; // Compile được
// s.length();        // Runtime NullPointerException
~~~

Hoặc:

~~~java
var xs = new java.util.ArrayList<String>();
String first = xs.get(0); // Compile được, nhưng runtime có thể IndexOutOfBoundsException
~~~

Vì thế một test suite thực tế nên tách:

1. **Compile positive** — mã được chấp nhận.
2. **Compile negative** — mã bị từ chối vì sai rule.
3. **Runtime unit tests** — logic đúng khi chạy trong các điều kiện cụ thể.
4. **Static analysis/style review** — `var` có giúp code đọc hiểu không?
5. **Cross-release compiler tests** — code phù hợp Java runtime/release mục tiêu.

### 9.1. Numeric inference

~~~java
var ratioInt = 1 / 2;      // int và giá trị 0
var ratioDouble = 1.0 / 2; // double và giá trị 0.5
~~~

`var` không đổi semantics của phép chia nguyên. Muốn kiểm thử inference cho numeric expressions, phải xem **kiểu của expression và phép toán**, không suy từ mong đợi của người viết.

### 9.2. Anonymous class type và non-denotable types

JLS cho phép suy luận một số kiểu không dễ khai báo tường minh, ví dụ:

~~~java
var helper = new Object() {
    String hello() { return "Hello"; }
};
String s = helper.hello();
~~~

`var` có thể giữ kiểu anonymous class suy ra. Đây là tình huống nâng cao; trong code nghiệp vụ, dùng API rõ ràng và tránh nhét quá nhiều logic vào anonymous class chỉ vì compiler cho phép.

### 9.3. Ranh giới của style guidelines

~~~java
var customer = service.findCustomerById(id);
~~~

Câu lệnh có thể compile được, nhưng không nhất thiết dễ đọc nếu method name không cho biết kiểu. Trong code review, có thể chọn explicit type cho những nơi quan trọng.

**Không phân loại mọi code thiếu dễ đọc là compile-negative test**. Đó là **style/maintainability rule**, khác với JLS legality.

## 10. Ma trận theo source release

| Snippet | Java 9 | Java 10 | Java 17 | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `int x=1;` | Chấp nhận | Chấp nhận | Chấp nhận | Control. |
| `var x=1;` | Từ chối | Chấp nhận | Chấp nhận | JEP 286 từ Java 10. |
| `Function<String,Integer> f=s->s.length();` | Chấp nhận | Chấp nhận | Chấp nhận | Lambda implicit parameters có từ Java 8. |
| `Function<String,Integer> f=(var s)->s.length();` | Từ chối | Từ chối | Chấp nhận | JEP 323 từ Java 11. |
| `var f=()->1;` | Từ chối | Từ chối | Từ chối | Thiếu target type. |
| `var x=null;` | Từ chối | Từ chối | Từ chối | Với Java 9 còn chưa có `var`; với Java 10+ là null type. |

Cột “từ chối” không có nghĩa **cùng diagnostic** cho tất cả releases. Java 9 có thể không nhận `var` làm type inference, trong khi Java 17 hiểu `var` nhưng từ chối initializer `null`. Khi muốn assert lỗi chính xác, cần xác định scope của rule và chọn đúng compiler configuration.

## 11. Vận hành trong CI/CD và build tools

### 11.1. Maven và Gradle

Ở dự án thực:

- **Mã hợp lệ** đưa vào source set production/test bình thường, đặt compiler `release` chính xác.
- **Mã cố ý sai** giữ trong fixtures riêng hoặc in-memory source tests để không làm job `compileJava` / `maven-compiler-plugin` báo lỗi ngay từ đầu.
- Dùng test task chạy harness và trả **non-zero** khi có kỳ vọng bị vi phạm.
- Pin JDK toolchain trong CI để kiểm soát source compatibility và diagnostic behavior.
- Chạy cả compile-negative và runtime-positive tests trước khi merge khi tính năng type inference quan trọng.

Không cần cấu hình framework phức tạp chỉ để thử vài quy tắc. Bộ harness Java SE ở phần 8 đã thể hiện đầy đủ logic kiểm chứng.

### 11.2. Không hard-code thông điệp lỗi

Nếu test âm chỉ so nguyên văn:

~~~text
error: cannot infer type for local variable x
~~~

thì có thể fail trên một JDK vẫn thực thi đúng quy tắc nhưng dùng thông điệp khác, thêm đường dẫn/dòng/cột hoặc locale khác.

Cách kiểm tra tốt hơn cho bài học là:

~~~text
Expected: REJECTED
Actual:   REJECTED
Diagnostic.Kind.ERROR exists: true
Result: PASS
~~~

Nếu cần kiểm thử một diagnostic code, pin chính xác javac version/vendor và ghi điều kiện test. Đây là **kiểm thử compiler implementation**, không phải hợp đồng ngôn ngữ chung.

### 11.3. Một negative fixture nên kiểm tra một quy tắc

Tránh source có **5 lỗi** và chỉ xem “compile fail”. Compiler có thể báo một lỗi chưa liên quan tới điều bạn định học.

Ví dụ muốn thử `var x=null`, không nên đồng thời dùng package chưa tồn tại, method chưa khai báo hoặc type chưa import. Harness trong bài dùng snippets tự chứa, phân biệt rõ từng rule.

### 11.4. Positive control không được bỏ

Nếu compiler bất ngờ không hỗ trợ `--release 9`, hai ca release9 có thể đều fail vì option. Ca `P18_release9_explicit` **phải compile** sẽ giúp phát hiện lỗi môi trường đó thay vì kết luận nhầm `N17` đã chứng minh quy tắc Java 9.

Tương tự `P17_java10_var` chứng minh compiler chấp nhận `var` trên source10, bổ trợ cho `N18_java10_no_var_lambda`.

## 12. Các lỗi hiểu sai phổ biến

| Ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `var` làm Java thành dynamic typing. | Kiểu suy ra tĩnh từ initializer. | Test gán lại sai kiểu. |
| `var x;` được phép như `int x;`. | `var` cần suy ra kiểu. | Có initializer hoặc explicit type. |
| `var x=null` là `Object`. | Null type không đủ suy luận. | `String x=null` hoặc cast typed. |
| `var x={1,2}` tạo `int[]`. | Array initializer rời không hợp lệ. | `new int[]{1,2}`. |
| `var x[]=...` hợp lệ. | Bracket pairs bị cấm tại declarator. | `var x=new int[2]`. |
| `var a=1,b=2` hợp lệ. | Multiple declarators bị cấm. | Tách khai báo. |
| `var a=a` suy ra kiểu qua self-reference. | JLS cấm tự tham chiếu trong initializer. | Khởi tạo độc lập. |
| `var` dùng được cho fields và return types. | Không thuộc phạm vi local inference. | Type tường minh. |
| `var` dùng được trong ordinary method params. | Chỉ lambda formal params được thêm Java 11. | Method parameter type tường minh. |
| Java 10 cho `(var s)->...`. | JEP 323 xuất hiện Java 11. | Xác định source release. |
| `var f=()->...` có target type tự động. | Lambda cần target functional interface. | `Function<T,R> f=...`. |
| Có thể trộn `var a, String b` trong lambda. | Không được trộn parameter forms. | Dùng tất cả var hoặc tất cả types. |
| `ArrayList<>` với `var` tự dựa vào `add("x")` để suy String. | Inference không xét assignments/usages về sau. | `new ArrayList<String>()` hoặc explicit target. |
| `var var=10` bị lỗi vì “var là keyword”. | Nó là restricted type name, không cấm identifier này. | Test chính xác; khuyên đặt tên rõ. |
| Mọi compile fail là negative PASS. | Có thể do toolchain/classpath/IO. | Diagnostic + controls. |
| Negative tests có thể chạy như Java program. | Source không hợp lệ không thể chạy. | Test bằng javac hoặc JavaCompiler. |
| Runtime stdout đúng chứng minh ca âm khác bị reject. | Hai loại test độc lập. | Kiểm tra cả hai. |
| Mọi JDK phát đúng một thông điệp lỗi. | Diagnostic text/version/locale thay đổi. | Assert status/kind, pin compiler nếu cần mã lỗi. |
| JDK24 compiler tự cho phép Java24 features khi dùng `--release 9`. | `--release` ép source/API level mục tiêu. | Dùng đúng target. |
| `var` luôn làm code đẹp hơn. | Có thể che kiểu quan trọng. | Review readability. |

## 13. Bài tập và đáp án

### Bài 1 — Initializer thiếu

~~~java
var x;
~~~

**Đáp án:** Negative; phải có initializer cho local `var` thông thường.

### Bài 2 — Null trực tiếp và null có cast

~~~java
var a = null;
var b = (String) null;
~~~

**Đáp án:** Dòng đầu không compile; dòng sau compile và `b` suy `String`, nhưng vẫn có thể `NullPointerException` nếu dereference.

### Bài 3 — Mảng

~~~java
var values = {1, 2, 3};
~~~

**Đáp án:** Negative; sửa thành `var values = new int[]{1,2,3};`.

### Bài 4 — Enhanced `for`

~~~java
for (var n : java.util.List.of(1,2)) {
    System.out.println(n);
}
~~~

**Đáp án:** Positive Java 10+, kiểu suy ra từ phần tử Iterable.

### Bài 5 — Field

~~~java
class X { var value = 5; }
~~~

**Đáp án:** Negative, vì field phải khai báo type tường minh.

### Bài 6 — Lambda parameters

~~~java
java.util.function.Function<String,Integer> f =
        (var s) -> s.length();
~~~

**Đáp án:** Positive Java 11+, negative ở `--release 10`.

### Bài 7 — Lambda thiếu target

~~~java
var add = (a, b) -> a + b;
~~~

**Đáp án:** Negative; cần target functional interface type, ví dụ `BiFunction<Integer,Integer,Integer>`.

### Bài 8 — Diamond

~~~java
var xs = new java.util.ArrayList<>();
String first = xs.get(0);
~~~

**Đáp án:** Negative, vì `get` trong ca này trả `Object`.

### Bài 9 — Thay đổi kiểu khi gán lại

~~~java
var number = 10;
number = "ten";
~~~

**Đáp án:** Negative, `number` là `int`.

### Bài 10 — Release9

Tại sao `javac --release 9` từ chối `var x=1;` khi javac là JDK24?

**Đáp án:** Source language level được ép xuống Java 9; LVTI xuất hiện Java 10.

### Bài 11 — Identifier `var`

~~~java
var var = 10;
~~~

**Đáp án:** Positive Java 10+ ở vị trí local. Không khuyến nghị tên biến thiếu ý nghĩa.

### Bài 12 — Catch

~~~java
try { throw new Exception(); }
catch (var e) { }
~~~

**Đáp án:** Negative; `var` không hợp lệ cho catch parameter.

### Bài 13 — Method reference

~~~java
var f = String::length;
~~~

**Đáp án:** Negative; cần target type `Function<String,Integer>`.

### Bài 14 — `final var`

~~~java
final var n = 1;
n = 2;
~~~

**Đáp án:** Negative do vi phạm `final`, không phải vì `final var` sai.

### Bài 15 — Compiler tool failure

Một negative fixture bị từ chối do `--release` không được compiler hỗ trợ. Có tính PASS không?

**Đáp án:** Không. Đây là lỗi toolchain. Cần positive control cùng release và JDK phù hợp.

### Bài 16 — Warnings

Compiler in warning nhưng trả compile success. Có nghĩa negative test đạt không?

**Đáp án:** Không. Warning không phải diagnostic ERROR và source có thể đã compile thành công. Phải kiểm tra compilation status và diagnostic kind.

### Bài 17 — Resource type

~~~java
try (var n = 1) { }
~~~

**Đáp án:** Negative, vì `int` không thực hiện `AutoCloseable`.

### Bài 18 — CI

Làm sao đưa ca `var x=null` vào CI mà không chặn normal Java compile?

**Đáp án:** Đặt fixture ngoài source roots, dùng JavaCompiler/test task riêng và assert compilation bị REJECTED; đừng đưa source invalid vào `src/main/java`.

## 14. Checklist QA

- [ ] Tôi đã đọc đúng Java source level của module.
- [ ] Tôi phân biệt Java 10 JEP 286 với Java 11 JEP 323.
- [ ] Tôi có positive tests cho local `var`, basic/enhanced for, array, generics, final var.
- [ ] Tôi có positive test cho lambda `var` khi source level 11+.
- [ ] Tôi có negative tests cho missing initializer, null type, multiple declarators.
- [ ] Tôi có negative tests cho array initializer, declarator brackets, self-reference.
- [ ] Tôi có negative tests cho field, method return, ordinary method parameter, catch parameter.
- [ ] Tôi có negative tests cho lambda no-target, method reference no-target và mixed parameter types.
- [ ] Tôi kiểm chứng diamond inference và reassignment type mismatch.
- [ ] Tôi có version boundary tests source9/source10/source17.
- [ ] Tôi có positive control cho từng release nhạy cảm.
- [ ] Tôi kiểm tra compiler actual result bằng `JavaCompiler`/`javac`.
- [ ] Tôi xác nhận negative cases bị reject với ít nhất một diagnostic ERROR.
- [ ] Tôi không dựa vào nguyên văn thông điệp lỗi có thể khác locale/vendor.
- [ ] Tôi không cho negative fixtures vào production compile roots.
- [ ] Tôi dùng stdout/runtime assertions cho positive examples chạy được.
- [ ] Tôi biết `var` không làm Java type system trở thành dynamic.
- [ ] Tôi không đồng nhất compile pass với runtime null safety.
- [ ] Tôi phân biệt vấn đề compiler tooling, source syntax và type inference.
- [ ] Tôi dùng thông tin JDK version hiện tại, không làm theo ví dụ Java cũ đã thay đổi.
- [ ] Tôi giữ tính dễ đọc khi dùng `var`, không coi mọi nơi đều thích hợp.

## 15. Tài liệu chính thức còn áp dụng

1. [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): cơ chế `var` từ Java 10.
2. [Oracle Java SE 25 — JLS 14.4 Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): single declarator, initializer, array initializer, self-reference, null type và compiler inference.
3. [Oracle Java SE 25 — JLS 14.14 For Statements](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14): basic `for` và enhanced `for`.
4. [Oracle Java SE 25 — JLS 14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3): resource declaration và AutoCloseable.
5. [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): lambda `var` từ Java 11.
6. [Oracle Java SE 25 — JLS 15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27): functional-interface target typing và parameter syntax.
7. [Oracle Java SE 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): hướng dẫn về `var` còn áp dụng và restricted type name.
8. [Oracle Java SE 25 — JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): compilation tasks trong Java.
9. [Oracle Java SE 25 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): nhận diagnostics của compiler.
10. [Oracle Java SE 25 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): source Java in-memory.
11. [Oracle Java SE 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release` và compiler options.
12. [OpenJDK JEP 286 FAQ](https://cr.openjdk.org/~briangoetz/jep-286/lvti-faq.html): suy kiểu từ initializer, không từ các assignments về sau.

**Kết luận:** Để **kiểm thử dương và kiểm thử lỗi biên dịch cho `var`**, phải xác minh **cả ACCEPTED và REJECTED** theo những quy tắc JLS phù hợp với **source release**. `var` là suy luận kiểu tĩnh của local variables từ Java 10, không phải dynamic typing; `var` trong lambda parameters chỉ được bổ sung ở Java 11. Bộ chương trình Java 17+ trong bài đã được kiểm chứng với **36/36 expectations** bằng OpenJDK 24.0.2, đồng thời có runtime positive example với stdout xác định. Trong CI, dùng compiler result và diagnostics có ý nghĩa, không chỉ grep văn bản lỗi hoặc chờ runtime lỗi, và luôn tách mã cố ý không hợp lệ khỏi source set chính.