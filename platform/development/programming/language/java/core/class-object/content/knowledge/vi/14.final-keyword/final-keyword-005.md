# Hằng `static final` và điều kiện của hằng tại thời điểm biên dịch trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **`static`**, **`final`**, **`static final`**, **constant variable** và **constant expression** theo Java Language Specification (JLS).
- Giải thích **đúng điều kiện** để một field `static final` được xem là hằng tại thời điểm biên dịch (*compile-time constant*): kiểu `primitive` hoặc `String`, modifier `final`, initializer là *constant expression*.
- Dự đoán field nào được compiler tính từ literals, toán tử, ép kiểu, hằng khác; field nào phải được tính **khi chương trình chạy**, dù đều mang `static final`.
- Phân biệt **không gán lại được field** với **bất biến của object** được field tham chiếu.
- Giải thích tác động lên **class initialization**, `ConstantValue`, việc client **nhúng giá trị (inlining)** và các rủi ro khi thay đổi API constants mà không biên dịch lại code dùng chúng.
- Biết các trường hợp cần **constant expression** như một số dạng `case` labels, annotation element values và phép gán hẹp từ một constant integer.
- Hiểu `static final` trong interface, field gán ở static block, local `final` variables và giới hạn “final không đồng nghĩa compile-time”.
- Chọn giữa compile-time constants, runtime-initialized fields, accessors, cấu hình động và immutable value objects để thiết kế API rõ, dễ bảo trì.
- Tự biên dịch/chạy các ví dụ Java 17+, đọc stdout đúng và phân loại lỗi compiler.

## 1. Trước hết: `static` và `final` làm hai việc khác nhau

Xét một class:

~~~java
class ServerConfig {
    static int activeConnections;
    final int serverId;
    static final int DEFAULT_PORT = 8080;

    ServerConfig(int serverId) {
        this.serverId = serverId;
    }
}
~~~

Đây là **đoạn khai báo minh họa**, không phải chương trình có `main`.

- `static int activeConnections`: field thuộc **class**, được chia sẻ trong cùng runtime class; các thao tác ghi nó được phép theo access và ngữ cảnh.
- `final int serverId`: **instance field**, mỗi instance có riêng một giá trị; sau khi được gán đúng theo quy tắc khởi tạo `final`, field không thể bị gán lại.
- `static final int DEFAULT_PORT`: field thuộc class **và** không được gán lại sau khi khởi tạo hợp lệ.

**Nhưng:** từ hai modifier `static final` **chưa đủ** để kết luận field là **hằng tại thời điểm biên dịch**. Ví dụ:

~~~java
static final int PORT_A = 8080;
static final int PORT_B = Integer.parseInt("8080");
~~~

Cả hai đều là `static final int`, nhưng:

- `PORT_A` nhận giá trị từ integer literal; nó là **constant variable**.
- `PORT_B` gọi method `Integer.parseInt` tại runtime; nó **không** là constant variable.

Hai field có thể cho **cùng số 8080** sau khi khởi tạo, nhưng **thời điểm và cách compiler/JVM xử lý việc đọc chúng có thể khác**.

### 1.1. Tóm tắt bốn khái niệm

| Khái niệm | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| `static` | Thành viên gắn với class, không gắn riêng mỗi instance | `static int count` |
| `final` | Biến/field không được gán lại sau khi gán hợp lệ | `final String name` |
| `static final` | Field cấp class không được gán lại sau khi khởi tạo hợp lệ | `static final List<String> NAMES` |
| **Constant variable** | Một **`final` variable** thuộc kiểu primitive hoặc `String`, được khởi tạo bằng **constant expression** | `static final int MAX = 10` |

**Một hằng cấp lớp thông dụng** thường được viết `public static final` hoặc `private static final`. `public/private` quyết định khả năng truy cập, **không quyết định** giá trị có được tính tại compile time hay không.

## 2. Định nghĩa chính xác của constant variable

Theo **JLS `4.12.4**, một *constant variable* là **biến `final` có kiểu nguyên thủy hoặc `String`, được khởi tạo bằng một *constant expression* (`15.29 trong Java 17)**.

Có ba điều kiện cần cùng đúng:

1. **`final`:** biến/field được khai báo `final`.
2. **Kiểu:** một trong tám primitive types (`byte`, `short`, `int`, `long`, `char`, `float`, `double`, `boolean`) **hoặc `java.lang.String`**.
3. **Initializer:** được khởi tạo bằng một biểu thức thuộc tập *constant expressions* do ngôn ngữ định nghĩa, không phải chỉ là biểu thức “có vẻ tính được dễ dàng”.

`static` **không xuất hiện như một yêu cầu trong định nghĩa chung**, vì một **local final variable** cũng có thể là constant variable. Với chủ đề hằng **cấp lớp**, ta bổ sung `static` để áp dụng định nghĩa đó cho static field.

### 2.1. Ví dụ thỏa cả ba điều kiện

~~~java
static final int MAX_USERS = 100;
static final long TIMEOUT_MS = 1_000L;
static final char SEPARATOR = ':';
static final boolean DEBUG = false;
static final double PI_APPROX = 3.14;
static final String APP_NAME = "JavaCore";
static final int QUADRUPLE = MAX_USERS * 4;
static final String HEADER = APP_NAME + " v1";
~~~

Các initializer ở đây là literals, tên constant variables hoặc phép toán constant expression phù hợp. Nếu những khai báo trên nằm trong class hợp lệ, chúng đều là **constant variables**.

Tên viết hoa và dấu gạch dưới là **quy ước đặt tên**, không phải điều kiện compiler dùng để xác định constant variables. `static final int maxUsers = 100;` vẫn là constant variable dù không theo convention.

### 2.2. Ví dụ không thỏa, dù có `static final`

~~~java
static final Integer BOXED = 100;
static final int FROM_METHOD = Integer.parseInt("100");
static final String FROM_PROPERTY =
        System.getProperty("app.name", "JavaCore");
static final String RUNTIME_TEXT = new String("JavaCore");
static final int GENERATED = generate();
static final java.util.List<String> TAGS =
        java.util.List.of("java", "core");
~~~

Giả sử method `generate()` tồn tại và trả `int`. Những field này **không phải constant variables** vì:

- `Integer` và `List<String>` không thuộc kiểu primitive hoặc `String`.
- Method calls như `Integer.parseInt`, `System.getProperty`, `generate()` không phải constant expressions.
- `new String("JavaCore")` tạo đối tượng lúc runtime, dù nội dung biết trước.

**Lưu ý:** `String` là **kiểu tham chiếu duy nhất được phép** trong định nghĩa constant variable; các wrapper như `Integer`, `Boolean`, `Long` không được thêm vào danh sách chỉ vì chúng immutable.

### 2.3. Bảng phân loại nhanh

| Khai báo | Có `static final`? | Constant variable? | Lý do |
| --- | --- | --- | --- |
| `static final int A = 5;` | Có | **Có** | `int` + literal |
| `static final String B = "Hi";` | Có | **Có** | `String` + literal |
| `static final int C = 2 + 3 * 4;` | Có | **Có** | Biểu thức hằng |
| `static final int D = (int) 3.9;` | Có | **Có** | Cast trong constant expression |
| `static final int E = Math.abs(-5);` | Có | **Không** | Gọi method |
| `static final Integer F = 5;` | Có | **Không** | Kiểu wrapper |
| `static final String G = "A".toLowerCase();` | Có | **Không** | Gọi method |
| `static final String H = "A" + "B";` | Có | **Có** | Nối constant strings |
| `static final String I = new String("AB");` | Có | **Không** | `new` expression |
| `static final int J; static { J = 5; }` | Có | **Không** | Field không có initializer constant expression ở khai báo |
| `static int K = 5;` | Không | **Không** | Thiếu `final` |
| `final int local = 5;` | Không phải static field | **Có** | Local final constant variable |

## 3. Constant expression được phép gồm những gì?

*Constant expression* được định nghĩa trong **JLS `15.29 của Java 17**. Tập biểu thức này gồm những cấu trúc giới hạn, với operands thích hợp, không phải mọi biểu thức thuần túy không có side effect.

Những thành phần thường gặp:

- Literals thuộc kiểu primitive và `String` như `123`, `42L`, `true`, `'X'`, `"Java"`.
- Dấu ngoặc `( ... )`.
- Unary operators như `+`, `-`, `~`, `!` khi hợp lệ theo kiểu.
- Toán tử số học `+`, `-`, `*`, `/`, `%`; toán tử bit `&`, `|`, `^`; shifts `<<`, `>>`, `>>>`.
- So sánh, equality, logical `&&`/`||`, ternary `?:` trong các kiểu và trường hợp được quy tắc cho phép.
- Các casts thích hợp tới kiểu primitive hoặc `String` trong ngữ cảnh constant-expression.
- Tên đơn giản hoặc qualified names **tham chiếu tới các constant variables**.
- Phép nối chuỗi `+` khi operands là các constant expressions thích hợp.

Những biểu thức **không thuộc** tập trên bao gồm lời gọi method thông thường, `new` object, đọc mutable field, phép gán, `++`/`--`, và biểu thức phụ thuộc vào giá trị runtime.

### 3.1. Chương trình ví dụ về phép toán hằng

Lưu **`ConstantExpressionDemo.java`**:

~~~java
public class ConstantExpressionDemo {
    static final int BASE = 7;
    static final int DOUBLE = BASE * 2;
    static final int MASK = 1 << 3;
    static final int ABS_BY_TERNARY = BASE > 0 ? BASE : -BASE;
    static final char LETTER = (char) ('A' + 2);
    static final boolean ALLOWED = BASE > 5 && MASK == 8;
    static final String TEXT = "value=" + DOUBLE + ",ok=" + ALLOWED;

    public static void main(String[] args) {
        System.out.println("double=" + DOUBLE);
        System.out.println("mask=" + MASK);
        System.out.println("ternary=" + ABS_BY_TERNARY);
        System.out.println("letter=" + LETTER);
        System.out.println("allowed=" + ALLOWED);
        System.out.println(TEXT);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac ConstantExpressionDemo.java
java ConstantExpressionDemo
~~~

**Stdout chính xác:**

~~~text
double=14
mask=8
ternary=7
letter=C
allowed=true
value=14,ok=true
~~~

Từng initializer được tính từ literals, operators và constant variables, **không cần gọi method runtime** để tính kết quả. Dòng `TEXT` là nối các constant expressions thành một String.

### 3.2. Cùng kết quả nhưng khác trạng thái constant variable

~~~java
static final int FIRST = 2 + 5;
static final int SECOND = Math.addExact(2, 5);
~~~

`FIRST` là compile-time constant; `SECOND` **không**, vì `Math.addExact` là một lời gọi method, dù dễ thấy nó trả 7. Đừng suy luận “compiler có thể tối ưu” = “ngữ nghĩa JLS gọi là constant expression”.

Compiler/JIT có thể thực hiện nhiều tối ưu runtime khác nhau; điều đó **không đổi định nghĩa ngôn ngữ** của constant variable.

## 4. Chương trình so sánh compile-time và runtime `static final`

Lưu **`StaticFinalClassificationDemo.java`**:

~~~java
public class StaticFinalClassificationDemo {
    static final int LITERAL = 12;
    static final int EXPRESSION = LITERAL * 2;
    static final String NAME = "Java" + "17";

    static final int RUNTIME_INT = makeInt();
    static final String RUNTIME_STRING = makeString();
    static final Integer BOXED = 42;

    private static int makeInt() {
        System.out.println("makeInt called");
        return 24;
    }

    private static String makeString() {
        System.out.println("makeString called");
        return "Java17";
    }

    static {
        System.out.println("static block finished");
    }

    public static void main(String[] args) {
        System.out.println("literal=" + LITERAL);
        System.out.println("expression=" + EXPRESSION);
        System.out.println("name=" + NAME);
        System.out.println("runtime int=" + RUNTIME_INT);
        System.out.println("runtime string=" + RUNTIME_STRING);
        System.out.println("boxed=" + BOXED);
    }
}
~~~

Lệnh:

~~~bash
javac StaticFinalClassificationDemo.java
java StaticFinalClassificationDemo
~~~

Output:

~~~text
makeInt called
makeString called
static block finished
literal=12
expression=24
name=Java17
runtime int=24
runtime string=Java17
boxed=42
~~~

**Giải thích chính xác về thời điểm:**

- Class `StaticFinalClassificationDemo` chứa `main`, nên JVM phải initialize class **trước** khi gọi `main`; vì vậy các runtime field initializers và static block in trước dòng `literal=12`.
- `LITERAL`, `EXPRESSION`, `NAME` là constant variables.
- `RUNTIME_INT` và `RUNTIME_STRING` được gán từ method calls, không phải compile-time constants.
- `BOXED` là `Integer`, không phải primitive/String, nên không là constant variable.
- Dù các field có giá trị giống/khác, **việc class đã initialized trước `main`** có thể che mất sự khác biệt về class-initialization trigger nếu chỉ nhìn output chương trình này.

Muốn quan sát rằng **chỉ đọc constant variable không khởi tạo class khai báo**, dùng ví dụ tiếp theo với class riêng.

## 5. Đọc compile-time constant có thể không khởi tạo class

Đây là khác biệt quan trọng trong **JLS `12.4.1**: đọc một static field là **constant variable** không bắt buộc initialize class/interface khai báo nó. Compiler có thể đưa **giá trị hằng** trực tiếp vào code caller.

Ngược lại, việc đọc static field **không** phải constant variable có thể kích hoạt initialization của lớp khai báo nó.

Lưu **`ConstantVsRuntimeInitDemo.java`**:

~~~java
public class ConstantVsRuntimeInitDemo {
    static class Settings {
        static final int PORT = 8080;
        static final String NAME = "service";

        static final int PORT_FROM_METHOD = portFromMethod();

        static {
            System.out.println("Settings static block");
        }

        private static int portFromMethod() {
            System.out.println("portFromMethod called");
            return 8080;
        }
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        System.out.println("port=" + Settings.PORT);
        System.out.println("name=" + Settings.NAME);
        System.out.println("before runtime field");
        System.out.println("runtime port=" + Settings.PORT_FROM_METHOD);
        System.out.println("after runtime field");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ConstantVsRuntimeInitDemo.java
java ConstantVsRuntimeInitDemo
~~~

Output:

~~~text
main starts
port=8080
name=service
before runtime field
portFromMethod called
Settings static block
runtime port=8080
after runtime field
~~~

**Diễn giải:**

1. JVM initialize outer class để chạy `main`; nested class `Settings` là một class runtime riêng.
2. `Settings.PORT` và `Settings.NAME` là constant variables, nên hai lần đọc này **không** trigger `Settings` initialization.
3. `Settings.PORT_FROM_METHOD` là static final field nhưng **không** constant variable. Lần đầu đọc nó buộc `Settings` initialization.
4. Field initializer `portFromMethod()` chạy theo thứ tự class body, sau đó static block mới chạy.
5. Các static final fields đã được khởi tạo thích hợp. `Settings` sẽ không chạy lại static initializer chỉ vì đọc một trong các fields lần sau.

### 5.1. Không nhầm “field được truy cập” với “field được tính lại”

Một `static final int PORT_FROM_METHOD` được tính trong class initialization, rồi giá trị field được giữ lại; mỗi lần đọc sau không tự gọi lại `portFromMethod()`.

Ngược lại, nếu dùng một **static method** `currentPort()` gọi `System.getProperty` mỗi lần, mỗi lời gọi có thể đọc cấu hình runtime mới. Method accessor và static final field mang hợp đồng thay đổi khác nhau.

### 5.2. Class phải initialized trong một số tình huống dù chỉ có constants

Tạo instance `new Settings()`, gọi một static method phù hợp, hoặc dùng reflection với lựa chọn initialization có thể làm `Settings` được initialized theo quy tắc, dù trước đó chỉ đọc constant variables. Câu đúng là **“đọc constant variable không tự yêu cầu initialization”**, không phải “class có constants sẽ không bao giờ initialized”.

## 6. `static final` gán trong static block: final nhưng không phải constant variable

Một `static final` field có thể là **blank final field** rồi được gán trong static initializer:

~~~java
class Limits {
    static final int DEFAULT_LIMIT;

    static {
        DEFAULT_LIMIT = 25;
    }
}
~~~

Mặc dù giá trị được viết cứng là 25, `DEFAULT_LIMIT` không có **initializer constant expression ngay tại khai báo field**, nên không phải constant variable theo định nghĩa JLS.

Nó vẫn là `static final`: Java yêu cầu gán hợp lệ một lần trong quá trình class initialization, đáp ứng definite assignment rules và không được tùy tiện gán lại.

### 6.1. Ví dụ chạy được

Lưu **`BlankFinalStaticDemo.java`**:

~~~java
public class BlankFinalStaticDemo {
    static class Limits {
        static final int DIRECT = 25;
        static final int FROM_BLOCK;

        static {
            FROM_BLOCK = 25;
            System.out.println("Limits initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("direct=" + Limits.DIRECT);
        System.out.println("before from block");
        System.out.println("from block=" + Limits.FROM_BLOCK);
        System.out.println("after from block");
    }
}
~~~

Lệnh:

~~~bash
javac BlankFinalStaticDemo.java
java BlankFinalStaticDemo
~~~

Output:

~~~text
direct=25
before from block
Limits initialized
from block=25
after from block
~~~

**Hai giá trị cùng 25** nhưng khác ngữ nghĩa:

- `DIRECT` là constant variable; đọc nó không tự initialize `Limits`.
- `FROM_BLOCK` không phải constant variable; đọc nó kích hoạt initialization, chạy static block và in `Limits initialized`.

Do đó, **điều kiện “initializer là constant expression” là thành phần quan trọng**, không thể thay bằng “giá trị thực tế nhìn thấy lúc chạy là một số cố định”.

### 6.2. Không thể dùng initializer trực tiếp và gán lại ở static block

~~~java
class Invalid {
    static final int LIMIT = 25;

    static {
        // LIMIT = 30; // Không hợp lệ: final field đã được gán.
    }
}
~~~

Ví dụ cố ý comment dòng lỗi để mã còn lại hợp lệ. `final` ngăn gán lại field sau lần gán hợp lệ; static block không phải ngoại lệ cấp phép “reset final”.

## 7. `final` trong biến cục bộ: cũng có thể là constant variable

Định nghĩa constant variable **không yêu cầu `static`**. Một local final primitive/String được khởi tạo bằng constant expression cũng là constant variable:

~~~java
final int LIMIT = 10;
final String PREFIX = "ITEM";
~~~

Nếu hai khai báo này nằm trong một method, chúng là **local constant variables**. Compiler có thể dùng chúng trong các context yêu cầu constant expression theo quy tắc.

Ngược lại:

~~~java
final int fromArgument = Integer.parseInt("10");
final String fromMethod = System.getProperty("prefix", "ITEM");
~~~

Hai local finals này **không** là constant variables vì initializer không phải constant expression, dù người viết không gán lại chúng nữa.

**Phân biệt `effectively final`:** một biến không khai báo `final` nhưng không bị gán lại có thể được capture bởi lambda theo quy tắc effectively final; điều này **không biến nó thành constant variable** theo định nghĩa yêu cầu modifier `final`.

### 7.1. Chương trình minh họa local final và switch label

Lưu **`LocalConstantSwitchDemo.java`**:

~~~java
public class LocalConstantSwitchDemo {
    static String category(int code) {
        final int LOW = 1;
        final int HIGH = LOW + 2;

        return switch (code) {
            case LOW -> "low";
            case HIGH -> "high";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(category(1));
        System.out.println(category(3));
        System.out.println(category(2));
    }
}
~~~

Biên dịch/chạy với Java 17:

~~~bash
javac LocalConstantSwitchDemo.java
java LocalConstantSwitchDemo
~~~

Output:

~~~text
low
high
other
~~~

`LOW` và `HIGH` là local constant variables, nên được sử dụng hợp lệ như `case` constants cho switch trên `int`.

### 7.2. Parameter `final` không đồng nghĩa compile-time constant

~~~java
static String classify(final int value) {
    return switch (value) {
        case 1 -> "one";
        default -> "other";
    };
}
~~~

`value` là **parameter** được gán khi method được gọi; modifier `final` chỉ ngăn gán lại parameter trong body. Giá trị của nó là runtime input, nên không thể dùng `case value -> ...` như một compile-time constant label.

## 8. Sử dụng hằng trong `switch` và annotation

Một số cú pháp của Java yêu cầu một **compile-time constant expression**. Hai nhóm dễ gặp là:

1. **`case` labels** trong các switch kiểu truyền thống hoặc switch expressions đối với primitive integral/String phù hợp, theo rules của từng loại switch.
2. **Annotation element values** khi element type là primitive hoặc `String`; chúng phải đáp ứng quy tắc annotation constant expressions.

### 8.1. Ví dụ `switch` với static final constant

Lưu **`StaticFinalSwitchDemo.java`**:

~~~java
public class StaticFinalSwitchDemo {
    static final int STATUS_NEW = 1;
    static final int STATUS_DONE = 2;

    static String describe(int status) {
        return switch (status) {
            case STATUS_NEW -> "new";
            case STATUS_DONE -> "done";
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(1));
        System.out.println(describe(2));
        System.out.println(describe(5));
    }
}
~~~

Chạy:

~~~bash
javac StaticFinalSwitchDemo.java
java StaticFinalSwitchDemo
~~~

Output:

~~~text
new
done
unknown
~~~

Nếu đổi `STATUS_DONE` thành `static final int STATUS_DONE = Integer.parseInt("2");`, thì nó vẫn `static final` nhưng **không** constant variable; việc dùng làm case label trong switch `int` trên Java 17 **không hợp lệ**.

### 8.2. Ví dụ annotation với constant String

Lưu **`AnnotationConstantDemo.java`**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

public class AnnotationConstantDemo {
    static final String DESCRIPTION = "Demo" + "API";

    @Retention(RetentionPolicy.RUNTIME)
    @interface Label {
        String value();
    }

    @Label(DESCRIPTION)
    static class Service {
    }

    public static void main(String[] args) {
        Label label = Service.class.getAnnotation(Label.class);
        System.out.println(label.value());
    }
}
~~~

Lệnh:

~~~bash
javac AnnotationConstantDemo.java
java AnnotationConstantDemo
~~~

Output:

~~~text
DemoAPI
~~~

Ở đây `DESCRIPTION` là static final String constant variable; nó có thể dùng làm giá trị annotation element `String`. Nếu thay initializer bằng `"DemoAPI".toString()`, đó là một method call, không còn là constant expression cho mục đích này.

### 8.3. Không phải mọi annotation element đều là String/primitive

Annotation có thể có element types là `Class` literal, enum, annotation khác hoặc mảng các loại hợp lệ. Chúng có **quy tắc riêng** về giá trị annotation; đừng cố nhét mọi trường hợp vào định nghĩa “constant variable là primitive hoặc String”.

Ví dụ enum annotation element cần một enum constant theo ngữ cảnh thích hợp, không thể dùng String constant variable thay thế.

## 9. Compile-time constant integer và phép chuyển kiểu hẹp

Một quy tắc Java hữu ích: trong **assignment context**, có những phép chuyển hẹp ngầm định từ `int` constant expression tới `byte`, `short`, `char` nếu **giá trị hằng nằm trong miền biểu diễn** của kiểu đích; JLS `5.2 trình bày chi tiết.

~~~java
byte small = 100;        // Hợp lệ: constant int 100 nằm trong byte.
short size = 20_000;     // Hợp lệ: nằm trong short.
char letter = 65;        // Hợp lệ: char biểu diễn được 65.
~~~

Đây là các khai báo minh họa trong method hoặc class phù hợp.

### 9.1. `final int` constant cũng có thể được thu hẹp trong assignment

~~~java
final int VALUE = 127;
byte result = VALUE; // Hợp lệ: constant variable VALUE = 127.
~~~

Nhưng:

~~~java
int runtimeValue = 127;
// byte result = runtimeValue; // Không tự thu hẹp int thường.

final int TOO_LARGE = 128;
// byte invalid = TOO_LARGE;   // Lỗi: 128 ngoài miền byte.
~~~

Việc compiler nhìn thấy tên biến thường có giá trị 127 **không đủ** nếu nó không phải constant expression theo ngữ nghĩa. Một `final int value = methodReturning127();` cũng không cho phép phép hẹp trên chỉ vì method lúc chạy trả 127.

### 9.2. Ví dụ chạy được

Lưu **`ConstantNarrowingDemo.java`**:

~~~java
public class ConstantNarrowingDemo {
    static final int MAX_BYTE = 127;
    static final int LETTER_CODE = 65;

    public static void main(String[] args) {
        byte small = MAX_BYTE;
        char letter = LETTER_CODE;

        final int limit = 12;
        short shortValue = limit;

        System.out.println("byte=" + small);
        System.out.println("char=" + letter);
        System.out.println("short=" + shortValue);
    }
}
~~~

Chạy:

~~~bash
javac ConstantNarrowingDemo.java
java ConstantNarrowingDemo
~~~

Output:

~~~text
byte=127
char=A
short=12
~~~

**Quan trọng:** Quy tắc này áp dụng cho các context được JLS cho phép. **Method invocation context** không tự thực hiện narrowing `int` → `byte` chỉ vì integer literal nằm trong miền byte:

~~~java
static void acceptByte(byte value) {
    System.out.println(value);
}

// Trong method:
// acceptByte(100);       // Không hợp lệ: int -> byte narrowing không tự dùng.
// acceptByte((byte)100);  // Hợp lệ: cast tường minh.
// byte b = 100;
// acceptByte(b);          // Hợp lệ: argument đã có kiểu byte.
~~~

Đừng đồng nhất quy tắc gán biến với quy tắc chọn method overload.

## 10. String compile-time constants và `==`

Với String, compile-time constant expressions có tác động dễ thấy vì **constant strings được intern** theo quy tắc Java.

Lưu **`ConstantStringIdentityDemo.java`**:

~~~java
public class ConstantStringIdentityDemo {
    static final String COMPILED = "Ja" + "va";
    static final String RUNTIME = new String("Java");

    public static void main(String[] args) {
        String literal = "Java";

        System.out.println("compiled equals=" + COMPILED.equals(literal));
        System.out.println("compiled identity=" + (COMPILED == literal));

        System.out.println("runtime equals=" + RUNTIME.equals(literal));
        System.out.println("runtime identity=" + (RUNTIME == literal));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ConstantStringIdentityDemo.java
java ConstantStringIdentityDemo
~~~

Output:

~~~text
compiled equals=true
compiled identity=true
runtime equals=true
runtime identity=false
~~~

- `"Ja" + "va"` là compile-time constant string expression, cùng nội dung với literal `"Java"` và được intern theo ngữ nghĩa Java. Vì vậy hai references trong biểu thức so sánh ở đây cùng String object.
- `new String("Java")` tạo String object mới (khác literal interned), dù nội dung giống nhau.
- `String.equals` so nội dung theo hợp đồng String, còn `==` so object identity.

**Không suy rộng:** Không nên dùng `==` để so nội dung chuỗi ứng dụng. Hai strings cùng nội dung nhận từ file, input hoặc method có thể là hai objects khác nhau. Dùng `equals` hoặc `Objects.equals` khi có khả năng null.

### 10.1. Compile-time concatenation khác concatenation runtime

~~~java
static final String ONE = "A" + 1;
static final String TWO = "A" + Integer.toString(1);
~~~

`ONE` là constant variable, `TWO` không, vì `Integer.toString(1)` là method call. Cùng kết quả `"A1"` không có nghĩa cùng điều kiện compile-time.

## 11. Java compiler có thể nhúng hằng vào bytecode của caller

Khi một client viết:

~~~java
System.out.println(Api.LIMIT);
~~~

và `Api.LIMIT` là **static final primitive/String constant variable** có giá trị 10, compiler có thể **đưa trực tiếp giá trị 10 vào bytecode của client**, thay vì phát sinh một lệnh đọc field runtime.

Đây không chỉ là tối ưu “mang tính gợi ý”: JLS xác định ngữ nghĩa compile-time constants và Java có quy tắc tương thích nhị phân liên quan. Đặc biệt, code đã biên dịch có thể vẫn dùng **giá trị cũ** nếu chỉ cập nhật thư viện chứa constant mà không biên dịch lại client.

### 11.1. Minh họa hai package, cập nhật thư viện không biên dịch lại client

Tạo cấu trúc:

~~~text
project/
  lib/
    Api.java
  client/
    Main.java
~~~

Nội dung **`lib/Api.java`** ban đầu:

~~~java
package lib;

public class Api {
    public static final int LIMIT = 10;
}
~~~

Nội dung **`client/Main.java`**:

~~~java
package client;

import lib.Api;

public class Main {
    public static void main(String[] args) {
        System.out.println("limit=" + Api.LIMIT);
    }
}
~~~

Từ thư mục `project`, biên dịch cả hai:

~~~bash
javac -d out lib/Api.java client/Main.java
java -cp out client.Main
~~~

**Stdout lần đầu:**

~~~text
limit=10
~~~

Bây giờ **sửa chỉ file `lib/Api.java`** thành:

~~~java
package lib;

public class Api {
    public static final int LIMIT = 20;
}
~~~

Sau đó **chỉ biên dịch lại thư viện**, không biên dịch lại client:

~~~bash
javac -d out lib/Api.java
java -cp out client.Main
~~~

**Stdout có thể vẫn là (và đúng với Java compiler thông thường trong ví dụ này):**

~~~text
limit=10
~~~

Cuối cùng biên dịch lại client để nó lấy constant mới:

~~~bash
javac -cp out -d out client/Main.java
java -cp out client.Main
~~~

Output:

~~~text
limit=20
~~~

**Đây là tình huống biên dịch hai lần để minh họa.** Không đặt đồng thời hai phiên bản `Api.java` trong cùng thư mục và mong chúng được build như hai classes khác nhau. Khi thực hành, thay nội dung file, chạy lệnh theo thứ tự.

### 11.2. Tại sao client vẫn dùng 10 khi Api đã đổi thành 20?

Ở lần biên dịch client đầu, `Api.LIMIT` là compile-time constant 10. Bytecode client có thể sử dụng 10 được nhúng sẵn. Thay riêng `Api.class` không viết lại bytecode `client.Main`.

Đây là dạng **thay đổi thư viện không phá linking nhưng không cập nhật giá trị quan sát được ở client cũ**. Đối với hằng `public static final` thuộc primitive/String, **thay đổi giá trị có thể đòi hỏi biên dịch lại tất cả code sử dụng hằng** nếu muốn nhận giá trị mới.

### 11.3. Quan sát bằng `javap`

Có thể dùng:

~~~bash
javap -c -classpath out client.Main
javap -v -classpath out lib.Api
~~~

`javap -c` hiển thị bytecode disassembly; `javap -v` cho thông tin classfile chi tiết. Với constant field thích hợp, bạn có thể thấy metadata `ConstantValue`; trong client, lời gọi in giới hạn có thể dùng lệnh nạp giá trị hằng thay vì `getstatic` đọc `Api.LIMIT`.

**Không dựa vào bytecode text chính xác từng lệnh trong ví dụ này** vì cách format và một số chi tiết có thể khác theo compiler/version. Hãy dựa trên nguyên tắc: client đã biên dịch có thể giữ giá trị hằng cũ.

## 12. `ConstantValue` và các giai đoạn JVM: hiểu đúng phạm vi

Ở cấp JVM, class có những giai đoạn thường được mô tả là **loading**, **linking** (trong đó có preparation) và **initialization**.

Đối với static constant variables kiểu primitive/String có `ConstantValue` thích hợp, giá trị được xử lý ở giai đoạn liên quan tới **preparation** theo JVM specification. Những field static khác thường có giá trị mặc định trước khi initializer runtime của class được thực hiện.

Đây là lý do các ví dụ thực tế cho thấy:

- Đọc constant variable từ code khác có thể không kích hoạt static initializer block.
- Static final field initialized bằng method call chỉ được gán kết quả sau khi chạy initializer runtime khi class được initialized.
- Trong một vòng phụ thuộc khởi tạo phức tạp, một static field chưa tới lượt initializer có thể vẫn ở default value như `0`/`null`.

**Quan trọng:** Không nên đơn giản hóa thành “mọi `static final` được JVM đặt đúng giá trị trước khi class initialized” — điều đó **sai** với runtime-computed fields.

### 12.1. `final` không cho phép bỏ qua thứ tự khởi tạo

~~~java
class Example {
    static final int FROM_METHOD = calculate();

    static int calculate() {
        return 7;
    }
}
~~~

`FROM_METHOD` vẫn phụ thuộc class initialization. `final` chỉ đặt ra ràng buộc về gán field, không làm một lời gọi method trở thành constant expression.

### 12.2. Constant variables khai báo trong interface

Mọi field khai báo trực tiếp trong interface ngầm là `public static final`. Nhưng initializer vẫn có thể là **runtime expression**, nên không phải mọi interface field đều là constant variable theo JLS.

Ví dụ:

~~~java
interface Options {
    int TIMEOUT = 30;
    int COMPUTED = compute();

    static int compute() {
        return 15;
    }
}
~~~

`TIMEOUT` là constant variable, `COMPUTED` không. Đừng nghĩ interface fields đều compile-time constants chỉ vì chúng `public static final`.

## 13. Ví dụ interface: hằng lúc compile và field runtime

Lưu **`InterfaceConstantDemo.java`**:

~~~java
public class InterfaceConstantDemo {
    interface Options {
        int FIXED = 7;
        int RUNTIME = initialize();

        static int initialize() {
            System.out.println("Options initialized");
            return 9;
        }
    }

    public static void main(String[] args) {
        System.out.println("fixed=" + Options.FIXED);
        System.out.println("before runtime");
        System.out.println("runtime=" + Options.RUNTIME);
    }
}
~~~

Chạy:

~~~bash
javac InterfaceConstantDemo.java
java InterfaceConstantDemo
~~~

Output:

~~~text
fixed=7
before runtime
Options initialized
runtime=9
~~~

`Options.FIXED` không khởi tạo interface, trong khi `Options.RUNTIME` phải được tính khi interface initialized. Cơ chế đọc constant variable vẫn nhất quán với định nghĩa JLS, dù owner là interface.

### 13.1. Hạn chế của cách chứa mọi constants trong một interface

Java từng gặp kiểu thiết kế “constant interface”, nơi class implements interface chỉ để lấy names của constants. Thực hành đó làm lộ implementation details trong public API và trộn constants vào type hierarchy.

Đối với constants của thư viện, thường rõ ràng hơn khi dùng một **final utility class** không cho tạo instance, một enum phù hợp hoặc một value object domain thay vì implements interface chỉ để mượn constant names.

## 14. `static final` field tham chiếu object không phải immutable object

Một lỗi phổ biến:

~~~java
class Registry {
    public static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();
}
~~~

Field `NAMES` không thể gán lại bằng một list khác từ code thường sau khi initialized. Tuy nhiên, **list object** vẫn có thể bị sửa:

~~~java
Registry.NAMES.add("admin");
Registry.NAMES.clear();
~~~

Nếu caller truy cập được field public, họ có thể mutate shared list. `final` **không** ngăn mutations lên đối tượng được tham chiếu; `static` còn khiến object ấy trở thành shared state cấp lớp, tăng rủi ro.

### 14.1. Ví dụ an toàn hơn với unmodifiable collection

Lưu **`StaticFinalCollectionDemo.java`**:

~~~java
import java.util.List;

public class StaticFinalCollectionDemo {
    static final List<String> ROLES =
            List.of("READER", "WRITER");

    public static void main(String[] args) {
        System.out.println("roles=" + ROLES);
        System.out.println("size=" + ROLES.size());

        try {
            ROLES.add("ADMIN");
        } catch (UnsupportedOperationException expected) {
            System.out.println("roles cannot be modified");
        }

        System.out.println("roles after=" + ROLES);
    }
}
~~~

Chạy:

~~~bash
javac StaticFinalCollectionDemo.java
java StaticFinalCollectionDemo
~~~

Output:

~~~text
roles=[READER, WRITER]
size=2
roles cannot be modified
roles after=[READER, WRITER]
~~~

`ROLES` **không phải** constant variable vì kiểu field là `List<String>`, không phải primitive/String; biểu thức `List.of` cũng là method call.

Dù vậy, **design ổn** cho danh sách roles cố định vì object `List.of` không sửa được thông qua list API. Hai điều “compile-time constant” và “immutable collection” phục vụ **những nhu cầu khác nhau**.

Nếu danh sách chứa **mutable elements**, unmodifiable list chỉ ngăn sửa cấu trúc; element objects vẫn có thể bị mutate qua aliases. Khi cần bất biến sâu phải chọn element types/copies phù hợp.

## 15. `static final` runtime value dùng cho cấu hình động có phù hợp không?

Ví dụ:

~~~java
static final String REGION =
        System.getProperty("region", "local");
~~~

Đây là runtime-initialized static final String, không phải constant variable. Field nhận giá trị khi class initialized; sau đó vẫn giữ **snapshot tại thời điểm initialization**.

Nếu chương trình đổi system property về sau:

~~~java
System.setProperty("region", "remote");
~~~

`REGION` **không tự được tính lại**. `final` ngăn đổi field, còn class initialization không lặp chỉ vì cấu hình thay đổi.

### 15.1. Phân biệt ba API cấu hình

| API | Thời điểm quyết định giá trị | Có thể thấy thay đổi runtime? |
| --- | --- | --- |
| `static final String REGION = "local";` | Compile-time constant | Không; client có thể nhúng "local" |
| `static final String REGION = System.getProperty(...);` | Lúc class initialized | Không tự cập nhật sau initialization |
| `static String region() { return System.getProperty(...); }` | Khi caller gọi method | Có thể đọc property hiện tại theo hợp đồng API |

Một ứng dụng thật nên cân nhắc cấu hình theo môi trường, vòng đời service, caching, thread safety và quyền truy cập. Đừng dùng compile-time constant cho thứ cần đổi theo triển khai mà không biên dịch lại.

## 16. Vì sao không nên vô tư công bố `public static final` cho dữ liệu dễ thay đổi?

Một constant như `public static final int PROTOCOL_VERSION = 1` có thể phù hợp khi thực sự là giá trị hằng gắn với bản phát hành và bạn chấp nhận mọi client cần build lại sau thay đổi.

Nhưng rủi ro xuất hiện khi:

- Thư viện phát hành version mới với giá trị constant thay đổi.
- Một module/service triển khai Java class mới mà không xây dựng lại client.
- Client vẫn dùng giá trị cũ đã được inline.
- Code dựa trên switch case/annotation cố định có thể cần thay đổi khi nghiệp vụ chuyển biến.
- Các thành phần trong một hệ thống phân tán không triển khai cùng thời điểm.

### 16.1. Khi nào dùng method accessor thay field constant?

Một public method:

~~~java
public static int currentLimit() {
    return ConfigStore.limit();
}
~~~

đây là **mảnh minh họa**, cần class `ConfigStore` phù hợp. Caller gọi method ở runtime; kết quả không phải compile-time constant được nhúng bởi compiler như field `static final int LIMIT=10`.

Tuy nhiên, đánh đổi là caller **không dùng được kết quả runtime đó trong những vị trí đòi constant expression**, ví dụ `case LIMIT:` theo Java 17. Đây là lựa chọn thiết kế có chủ đích, không phải giải pháp thay thế miễn phí cho mọi constant.

## 17. Giới hạn của constant expression: overflow và phép tính

Constant expression được tính theo **quy tắc ngữ nghĩa Java**, không phải số học vô hạn. Với integer arithmetic, kết quả vẫn tuân quy tắc overflow của kiểu.

~~~java
static final int MAX = Integer.MAX_VALUE;
static final int WRAPPED = MAX + 1;
~~~

`MAX` là constant variable (giá trị hằng có thể lấy từ khai báo final constant của thư viện phù hợp), `WRAPPED` là integer constant expression; kết quả bằng `Integer.MIN_VALUE` do tràn kiểu `int`.

### 17.1. Ví dụ chạy được về integer overflow

Lưu **`ConstantOverflowDemo.java`**:

~~~java
public class ConstantOverflowDemo {
    static final int MAX = 2_147_483_647;
    static final int WRAPPED = MAX + 1;
    static final long SAFE = (long) MAX + 1L;

    public static void main(String[] args) {
        System.out.println("max=" + MAX);
        System.out.println("wrapped=" + WRAPPED);
        System.out.println("safe=" + SAFE);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ConstantOverflowDemo.java
java ConstantOverflowDemo
~~~

Output:

~~~text
max=2147483647
wrapped=-2147483648
safe=2147483648
~~~

**Giải thích:** `WRAPPED` được tính trong miền `int` và tràn thành giá trị nhỏ nhất. `SAFE` chuyển sang `long` trước khi tính, tránh tràn `int` ở phép cộng đó.

`final` và “compile-time” **không có nghĩa biểu thức chắc chắn đúng về nghiệp vụ**. Compiler tuân quy tắc Java; lập trình viên cần lựa chọn kiểu dữ liệu và giới hạn phù hợp.

### 17.2. Chia nguyên cho zero trong constant expression

Một constant expression kiểu số nguyên với phép chia cho zero dẫn tới lỗi tại compile time theo các quy tắc Java, ví dụ:

~~~java
// static final int INVALID = 10 / 0; // Lỗi compile-time.
~~~

Không nên dùng một biểu thức lỗi như vậy trong example muốn biên dịch chạy. Nếu phép chia thực hiện ở runtime với mẫu số có giá trị 0, cơ chế báo lỗi có thể là `ArithmeticException` khi biểu thức được đánh giá. Cần phân biệt compile-time constant-expression rules và runtime exceptions.

## 18. `final` không đồng nghĩa “đã gán giá trị ngay tại khai báo”

Một số field `final` được gán hợp lệ trong constructor hoặc static block. Những field đó vẫn không được gán lại tùy ý, nhưng việc gán có thể diễn ra lúc runtime.

Ví dụ:

~~~java
class Session {
    final String token;

    Session(String token) {
        this.token = token;
    }
}
~~~

`token` là instance final field, giá trị do caller cung cấp ở runtime. Nó không phải compile-time constant variable chỉ vì kiểu là `String` và field final; không có constant-expression initializer tại declaration.

Với static blank final:

~~~java
class RuntimeFlags {
    static final boolean ENABLED;

    static {
        ENABLED = Boolean.parseBoolean(
                System.getProperty("enabled", "false"));
    }
}
~~~

`ENABLED` được gán trong static initializer lúc runtime. Nó **không** là constant variable, dù có kiểu boolean và khai báo static final.

### 18.1. Khi nào `final` đặc biệt có ích dù không compile-time constant?

- Đảm bảo reference hoặc primitive field không bị gán lại sau initialization hợp lệ.
- Diễn đạt invariant như owner ID hoặc configuration snapshot.
- Giúp suy luận về luồng dữ liệu và object construction.
- Hỗ trợ những đảm bảo nhất định về final fields theo Java Memory Model khi object được xây dựng đúng; không được đánh đồng với tính thread-safe của mutable referenced objects.

Không nên đánh giá giá trị của `final` chỉ bằng tiêu chí compiler có inline field hay không.

## 19. Kiểm tra “có phải constant variable?” theo từng bước

Khi gặp một khai báo như:

~~~java
public static final int TIMEOUT = SomeClass.calculateTimeout();
~~~

hãy đi theo trình tự:

1. **Đây có phải variable declaration?** Field hoặc local variable?
2. **Có `final` không?** Nếu không, loại ngay khỏi định nghĩa constant variable.
3. **Kiểu có là primitive hoặc `String` không?** Nếu là wrapper, array, list, enum, object type khác thì không.
4. **Có initializer ngay trong khai báo và initializer đó có thuộc tập constant expressions không?**
5. **Initializer có gọi method, tạo object, đọc nonconstant variable, làm ++/--, hoặc phụ thuộc runtime không?** Nếu có thì không phải constant expression.
6. **Nếu tên constant variable khác được tham chiếu, nó có thỏa các điều kiện này không?** Một phép tính hằng có thể xây từ các constant variables khác.
7. **Giá trị có nằm trong miền kiểu đích không và các phép toán có đúng kiểu không?** Constant expression vẫn chịu type checking và overflow semantics.
8. **Bạn dùng nó ở đâu?** Case label, annotation, assignment narrowing hoặc public library API đều có hệ quả riêng.
9. **Giá trị có thể đổi trong bản phát hành sau không?** Nếu có, cân nhắc inlining/binary compatibility.
10. **Có shared mutable referent không?** Đây là câu hỏi độc lập về immutability và encapsulation.

Kết quả phân loại không phụ thuộc vào việc JIT chạy nhanh, IDE hiển thị số cố định hoặc developer “biết chắc method luôn trả 10”.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Cứ `static final` là hằng compile-time.” | Cần kiểu primitive/String và constant-expression initializer. |
| “`static` là điều kiện bắt buộc của constant variable.” | Không; local final primitive/String constant-expression variable cũng thỏa JLS. |
| “Mọi `Integer` final đều là constant.” | Kiểu wrapper không thuộc primitive/String. |
| “`Math.abs(5)` rõ ràng bằng 5 nên là constant expression.” | Method invocation thông thường không nằm trong tập constant expressions. |
| “`new String("A")` giống `"A"` về compile-time constant.” | `new` không phải constant expression. |
| “`String` immutable nên mọi static final String là constant.” | Immutable type không đủ; initializer phải là constant expression. |
| “Blank final gán literal trong static block là compile-time constant.” | Không có initializer constant expression tại declaration. |
| “Tên biến viết hoa là constant.” | Đây chỉ là coding convention. |
| “Đọc `Settings.LIMIT` chắc chạy static block.” | Nếu LIMIT là constant variable, việc đọc không bắt buộc initialize class. |
| “`static final List` là constant variable.” | List không phải primitive/String. |
| “`static final List` luôn immutable.” | Final khóa field reference, list có thể mutable. |
| “Một phương thức trả số cố định sẽ được tính compile-time như literal.” | Có thể được tối ưu, nhưng không thành constant expression theo JLS. |
| “`final int x = 7` không dùng được trong case vì không static.” | Local final int có constant-expression initializer có thể là constant variable. |
| “`final` parameter là compile-time constant.” | Parameter nhận giá trị runtime, không có constant-expression initializer tại khai báo. |
| “`public static final` đổi từ 10 lên 20 thì client cũ chắc nhận 20.” | Client có thể đã inline 10 và cần recompile. |
| “`javap` là cách định nghĩa thế nào là constant.” | JLS định nghĩa constant; bytecode chỉ giúp quan sát một hệ quả. |
| “Compile-time constant không thể overflow.” | Integer constant expressions vẫn theo arithmetic Java. |
| “Interface field nào cũng là constant variable.” | Ngầm `public static final` nhưng initializer vẫn có thể là runtime expression. |
| “Nối String bằng `+` lúc nào cũng constant.” | Chỉ khi operands phù hợp là constant expressions. |
| “`List.copyOf` biến các elements mutable thành bất biến sâu.” | Chỉ cấu trúc list được bảo vệ; mutable elements vẫn có thể share. |

## 21. Bài tập tự kiểm tra có đáp án

**Câu 1.** `static final int A = 5;` có phải constant variable không?  
**Đáp án:** Có. `final`, kiểu primitive `int`, initializer integer literal.

**Câu 2.** `static final Integer A = 5;` có phải constant variable không?  
**Đáp án:** Không. `Integer` là wrapper reference type, không phải primitive hoặc String.

**Câu 3.** `static final int A = Integer.parseInt("5");` thì sao?  
**Đáp án:** Không. Có method invocation runtime.

**Câu 4.** `static final String A = "ab" + "cd";` thì sao?  
**Đáp án:** Có. Phép nối các String constant expressions tạo một String constant expression.

**Câu 5.** `static final String A = new String("abcd");` có là constant variable không?  
**Đáp án:** Không. `new` không phải constant expression.

**Câu 6.** Một field `static final int A; static { A = 5; }` có là compile-time constant không?  
**Đáp án:** Không. Đây là blank final field được khởi tạo ở runtime bởi static block.

**Câu 7.** Nếu chỉ đọc `Constants.A` và A là constant variable, class Constants có chắc chạy static block không?  
**Đáp án:** Không. Truy cập constant variable không tự buộc class initialization.

**Câu 8.** `final int LOCAL = 3;` bên trong method có là constant variable không?  
**Đáp án:** Có, dù không là static field. Định nghĩa JLS không yêu cầu `static`.

**Câu 9.** `final int LOCAL = method();` nếu method luôn trả 3 có là constant variable không?  
**Đáp án:** Không. Method invocation không là constant expression.

**Câu 10.** `final int n` là parameter có thể dùng làm `case n:` trong switch `int` Java 17 không?  
**Đáp án:** Không như một compile-time constant label. Parameter nhận giá trị khi gọi method.

**Câu 11.** Vì sao `byte b = 127;` hợp lệ mà `byte b = 128;` không?  
**Đáp án:** Một số phép gán có narrowing từ `int` constant expression khi giá trị nằm trong miền `byte`; 128 vượt miền.

**Câu 12.** `acceptByte(127)` với chỉ overload `acceptByte(byte)` tự hợp lệ không?  
**Đáp án:** Không. Method invocation không tự narrowing `int` literal thành byte theo quy tắc gán.

**Câu 13.** `static final List<String> NAMES = List.of("A");` là compile-time constant không?  
**Đáp án:** Không, cả kiểu List lẫn initializer method call không đáp ứng; nhưng list kết quả là unmodifiable theo API.

**Câu 14.** `"Ja" + "va"` và literal `"Java"` có liên quan gì đến interning?  
**Đáp án:** Nối hai constant strings là compile-time constant String, được intern; trong ví dụ cùng literal hai references có thể là cùng object. Nhưng so nội dung tổng quát vẫn dùng `equals`.

**Câu 15.** Tại sao đổi public static final primitive constant trong thư viện nhưng không build lại client có thể giữ giá trị cũ?  
**Đáp án:** Client có thể đã nhúng giá trị hằng tại compile time.

**Câu 16.** `static final int A = 2 + 3` và `static final int B = Math.addExact(2, 3)` giống nhau ở gì, khác gì?  
**Đáp án:** Cùng giá trị 5; A là constant variable, B không phải vì gọi method.

**Câu 17.** Một interface field `int MAX = 10;` có là compile-time constant không?  
**Đáp án:** Có. Interface fields ngầm public static final và initializer là constant expression.

**Câu 18.** Interface field `int MAX = calculate();` có tự là compile-time constant do interface không?  
**Đáp án:** Không. Method invocation là runtime initializer.

**Câu 19.** `static final int WRAPPED = 2_147_483_647 + 1;` cho kết quả gì?  
**Đáp án:** `-2147483648` do overflow kiểu int theo ngữ nghĩa Java.

**Câu 20.** Nếu bạn cần đọc một configuration thay đổi mỗi lần deploy không rebuild client, nên cân nhắc gì?  
**Đáp án:** Tránh public compile-time constant cho giá trị dễ đổi; cân nhắc accessor/runtime configuration theo contract và thiết kế phù hợp.

**Câu 21.** Vì sao `private static final ArrayList<String> CACHE` không đảm bảo các method khác trong class không mutate list?  
**Đáp án:** `final` chỉ chặn gán lại field reference, không chặn gọi `add`/`clear` trên ArrayList object.

**Câu 22.** Khi nào constant `case` label và annotation primitive/String values là lý do cần compile-time expression thật sự?  
**Đáp án:** Các vị trí cú pháp đó có quy tắc constant expressions tại compile time; một giá trị chỉ biết khi runtime không thay thế được.

## Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): định nghĩa **constant variable**.
- Java Language Specification (Java SE 17), [`15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): thành phần của **constant expression**.
- Java Language Specification (Java SE 17), [`12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): đọc constant variable và class initialization.
- Java Language Specification (Java SE 17), [`5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): phép hẹp hằng nguyên trong assignment.
- Java Language Specification (Java SE 17), [`13.4.9 — final Fields and static Constant Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.4.9): binary compatibility và thay đổi hằng.
- Java Language Specification (Java SE 17), [`9.3 — Field Declarations in Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.3): interface fields và modifiers ngầm định.
- Java Virtual Machine Specification (Java SE 17), [`4.7.2 — ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2): metadata classfile cho constants.

## Ghi nhớ

**`static final` không đồng nghĩa “hằng tại thời điểm biên dịch”.** Một **constant variable** cần `final`, kiểu primitive hoặc `String`, và initializer là **constant expression** theo JLS. `static` biến nó thành field cấp lớp; `public`/`private` quy định quyền truy cập, không quyết định tính constant.

Sự phân biệt này ảnh hưởng trực tiếp đến **class initialization**, phép dùng trong **`case` labels/annotations**, phép **narrowing** đặc biệt từ hằng nguyên, và việc **inline giá trị vào client đã biên dịch**. Nếu hằng public có thể thay đổi giữa các phiên bản, hãy cân nhắc nguy cơ client dùng dữ liệu cũ. Nếu field tham chiếu object, `final` chỉ bảo vệ phép gán lại field — **không tự làm object bất biến**. Hiểu đúng ba lớp khái niệm **modifier → constant-expression semantics → runtime behavior** sẽ giúp viết Java API chính xác và dễ bảo trì.
