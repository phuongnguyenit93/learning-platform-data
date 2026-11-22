# Biểu thức hằng, class literal và giới hạn giá trị tại nơi sử dụng annotation trong Java

Annotation trong Java không nhận mọi biểu thức mà một lời gọi phương thức bình thường có thể nhận. Ví dụ, một method có tham số `int` có thể được gọi với `Integer.parseInt("3")`, nhưng element `int` trong annotation **không** nhận lời gọi này làm giá trị. Nguyên nhân là Java cần biểu diễn giá trị annotation theo quy tắc chặt chẽ của ngôn ngữ và, tùy retention, ghi metadata đó vào class file.

Bài này giải thích **giá trị được phép đặt trực tiếp ở nơi sử dụng annotation** (`@Config(...)`): khi nào dùng biểu thức hằng, khi nào bắt buộc là `SomeType.class`, enum constant hoặc nested annotation; các ràng buộc với mảng, kiểu dữ liệu, default và lỗi biên dịch thường gặp. Ví dụ dựa trên Java 17 trở lên.

## 1. Hai bước phải phân biệt: khai báo element và truyền giá trị

Giả sử định nghĩa:

~~~java
@interface Retry {
    int count();
    String reason() default "temporary";
}
~~~

Đây là **khai báo annotation type**: mỗi method không tham số đại diện cho một element. Tại nơi sử dụng, tên element nằm bên trái dấu `=`, còn biểu thức bên phải là **element value**:

~~~java
@Retry(count = 2 + 1, reason = "network")
class Worker {
}
~~~

- `count = 2 + 1` hợp lệ bởi `2 + 1` là biểu thức hằng kiểu `int`.
- `reason = "network"` hợp lệ bởi đây là `String` literal.
- Có thể bỏ `reason` vì element này có default.
- **Không được bỏ** `count`: element không có default bắt buộc được cung cấp tại nơi sử dụng.
- Khi annotation chỉ có element tên `value`, có cú pháp ngắn `@Name(argument)` thay cho `@Name(value = argument)`. Cú pháp ngắn đó không áp dụng tùy tiện cho một element mang tên khác.

Với annotation element kiểu `int`, kiểu trả về của element chỉ xác định **miền kiểu dữ liệu**; quy tắc sử dụng annotation còn yêu cầu biểu thức **hằng tại compile time**. Tương tự, với element kiểu `Class<?>`, không đủ nếu một biến có kiểu `Class<?>`: phải cung cấp **class literal** hợp lệ.

## 2. Những kiểu element nào được Java cho phép?

Khi khai báo một annotation type, kiểu trả về của element chỉ có thể là:

| Nhóm | Ví dụ khai báo | Hình thức giá trị hợp lệ tại nơi dùng |
| --- | --- | --- |
| Kiểu nguyên thủy | `int retries();`, `boolean enabled();`, `char separator();` | **Constant expression** tương thích kiểu |
| `String` | `String name();` | **Constant expression** kiểu `String` |
| `Class` hoặc dạng tham số hóa phù hợp | `Class<?> handler();`, `Class<? extends Number> type();` | **Class literal**, ví dụ `String.class`, `Integer.class` |
| Enum | `Mode mode();` | **Enum constant**, ví dụ `Mode.SAFE` |
| Annotation khác | `Owner owner();` | **Nested annotation**, ví dụ `@Owner(name = "team")` |
| Mảng một chiều của các kiểu trên | `String[] tags();`, `Class<?>[] types();` | **Array initializer** gồm các element value hợp lệ, ví dụ `{"a", "b"}` |

Không khai báo element có kiểu `Object`, `Object[]`, `List<String>`, `Map<String, String>`, một class nghiệp vụ thông thường, hoặc mảng nhiều chiều như `int[][]`. Annotation type cũng không định nghĩa element có tham số, generic method hay `throws`.

Điều kiện **kiểu element hợp lệ** và **giá trị element hợp lệ** là hai điều kiện riêng. Ví dụ `String title();` là khai báo hợp lệ, nhưng `title = System.getenv("TITLE")` vẫn sai khi sử dụng.

## 3. Biểu thức hằng áp dụng cho primitive và `String`

Một **constant expression** theo Java Language Specification (JLS §15.29) là biểu thức cho kết quả thuộc kiểu nguyên thủy hoặc `String`, có thể tính khi biên dịch và chỉ dùng những hình thức được đặc tả cho phép.

Các ví dụ hợp lệ:

~~~java
@interface Limits {
    int max();
    String label();
    boolean active();
    char symbol();
}

@Limits(
    max = 2 * (3 + 1),
    label = "batch-" + 2026,
    active = (10 > 2) && true,
    symbol = 'A'
)
class BatchA {
}
~~~

Ở đây `max = 8` và `label = "batch-2026"` đều có thể xác định ở compile time. Phép cộng số, nối chuỗi, biểu thức so sánh/logic và biểu thức điều kiện `?:` có thể tham gia constant expression khi mọi phần cần thiết đều hợp lệ theo JLS.

### 3.1. `static final` chưa chắc là hằng dùng được

Một **constant variable** phải là biến `final` có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng constant expression. Biến `static final` khởi tạo bằng kết quả method call **không** là constant variable.

~~~java
final class Settings {
    static final int FIXED = 2 * 3;                 // Hợp lệ.
    static final int COMPUTED = Integer.parseInt("6"); // Không là constant variable.
    static final String KEY = "service." + "timeout";   // Hợp lệ.
    static final String DYNAMIC = System.getProperty("app.name"); // Không hằng.
}

@interface Level {
    int value();
}

@Level(Settings.FIXED)       // Hợp lệ: constant expression.
class JobA {
}

// @Level(Settings.COMPUTED) // Lỗi biên dịch nếu bỏ dấu //.
// class JobB {}
~~~

`Settings.COMPUTED` vẫn là `int` và là `static final`, nhưng giá trị khởi tạo cần thực thi method nên không thỏa quy tắc annotation. Đối với `String`, nối các chuỗi hằng thường hợp lệ; một `String` được tạo bằng method call, chẳng hạn `"abc".toUpperCase()`, **không** là constant expression dù lập trình viên đoán trước được kết quả.

Các **constant variables** có thể được tham chiếu qua tên lớp (`Constants.MAX`) khi đủ điều kiện truy cập. Không bắt buộc mọi giá trị phải viết thành literal ngay trong annotation.

### 3.2. Constant expression không đồng nghĩa với mọi thứ biết trước ở runtime

Những biểu thức sau **không** hợp lệ làm giá trị primitive/`String` annotation element:

~~~java
// Đoạn minh họa cố ý sai, KHÔNG đưa vào file runnable.
//
// @Level(Integer.parseInt("3"))    // Method invocation.
// @Level(new Integer(3))           // Object creation (và API constructor cũ).
// @Level(Math.abs(-3))              // Method invocation dù kết quả dễ đoán.
//
// int[] numbers = {3};
// @Level(numbers[0])                // Array access, không là constant expression.
~~~

Với annotation, `final` chỉ ngăn gán lại biến; nó **không biến** mọi giá trị khởi tạo runtime thành hằng compile time. Một method `static`, phương thức pure, hoặc getter không tự được phép xuất hiện trong element value.

### 3.3. Tính tương thích kiểu và thu hẹp giá trị hằng

Biểu thức phải tương thích với kiểu element theo quy tắc assignment context mà annotation cho phép. Ví dụ:

~~~java
@interface Priority {
    byte value();
}

@Priority(120)
class NormalPriority {
}

// @Priority(128)   // Lỗi: 128 vượt khoảng byte.
// class TooLarge {}
~~~

Mặc dù literal `120` có kiểu `int`, Java cho phép **narrowing conversion của constant expression kiểu `int`** sang `byte` khi giá trị nằm trong khoảng hợp lệ. Đừng suy rằng annotation cho phép mọi phép chuyển kiểu ngầm định: một giá trị vượt khoảng, một biểu thức không hằng, hoặc kiểu không tương thích vẫn bị từ chối.

## 4. Class literal: `Type.class` là một nhóm quy tắc riêng

Khi element có kiểu `Class` hoặc `Class<?>` (hoặc kiểu tham số hóa phù hợp), giá trị phải là **class literal** tương thích:

~~~java
@interface Codec {
    Class<?> value();
}

@Codec(String.class)
class TextCodec {
}

@Codec(int[].class)
class IntegerArrayCodec {
}
~~~

Các dạng class literal thường gặp là `String.class`, `Integer.class`, `int.class`, `void.class`, `String[].class`. Chúng là biểu thức class literal do ngôn ngữ định nghĩa, **không** phải constant expression primitive/`String` ở mục 3.

Nếu element khai báo `Class<? extends Number>`, compiler kiểm tra thêm generic bound:

~~~java
@interface NumberFormat {
    Class<? extends Number> value();
}

@NumberFormat(Integer.class)
class IntegerFormat {
}

// @NumberFormat(String.class) // Lỗi kiểu: String không extends Number.
// class BadFormat {}
~~~

Những cách sau không được chấp nhận thay `Type.class`:

~~~java
// Đoạn minh họa cố ý sai:
//
// static final Class<?> TEXT = String.class;
// @Codec(TEXT)                     // Biến Class, không phải class literal.
// @Codec(Class.forName("java.lang.String")) // Method call.
// @Codec(new Object().getClass())  // Method call.
// @Codec(java.util.List<String>.class) // Không có class literal của parameterized type.
~~~

`java.util.List.class` là class literal hợp lệ; `List<String>.class` thì không vì Java không có class literal riêng cho một kiểu generic đã tham số hóa. Nếu cần chọn implementation theo runtime config, dùng thiết kế khác (ví dụ tên khóa được validate và một registry ánh xạ sang lớp), không cố truyền `Class.forName(...)` vào annotation.

## 5. Enum constant: phải chỉ đích danh một thành viên enum

Với:

~~~java
enum Mode {
    FAST, SAFE
}

@interface Execution {
    Mode mode();
}

@Execution(mode = Mode.SAFE)
class SafeTask {
}
~~~

Java yêu cầu giá trị là **enum constant** tương thích với element. Một biến `static final` giữ enum constant không thay thế được enum constant trong annotation:

~~~java
final class ModeSettings {
    static final Mode DEFAULT = Mode.SAFE;
}

// @Execution(mode = ModeSettings.DEFAULT) // Lỗi biên dịch.
// class InvalidTask {}
~~~

Khác với biến primitive/`String`, biến enum không thuộc khái niệm constant variable của JLS §4.12.4. Giá trị `Mode.SAFE` hợp lệ vì đó chính là **enum constant**, không phải vì được gán cho một biến `final`.

## 6. Nested annotation và giá trị mảng

### 6.1. Nested annotation

Một annotation element có thể có kiểu của annotation khác. Khi sử dụng, viết một annotation literal:

~~~java
@interface Owner {
    String name();
}

@interface Assigned {
    Owner owner();
}

@Assigned(owner = @Owner(name = "platform"))
class AssignedJob {
}
~~~

Không thể thay phần `@Owner(...)` bằng `new Owner(...)`, vì annotation là metadata được biểu diễn qua cú pháp annotation, không khởi tạo bằng constructor của lớp thông thường.

### 6.2. Mảng một chiều

~~~java
@interface Labels {
    String[] value();
}

@Labels({"backend", "java"})
class ServiceA {
}

@Labels("backend")
class ServiceB {
}

@Labels({})
class ServiceC {
}
~~~

`@Labels({"backend", "java"})` dùng cú pháp ngắn vì element mang tên `value`. Mảng một phần tử có thể viết gọn `@Labels("backend")`; `@Labels({})` là mảng trống. Cách viết đầy đủ tương đương: `@Labels(value = {"backend", "java"})`.

**Giới hạn quan trọng:** có thể viết trực tiếp **array initializer** nhưng không sử dụng biến mảng, phương thức trả về mảng, hoặc `new String[]{...}` làm annotation element value:

~~~java
// Đoạn minh họa cố ý sai:
// static final String[] TAGS = {"backend", "java"};
// @Labels(TAGS)                         // Không hợp lệ.
// @Labels(new String[]{"backend"})      // Không hợp lệ.
// @Labels(java.util.List.of("backend").toArray(String[]::new)) // Không hợp lệ.
~~~

Từng phần tử của mảng cũng phải tuân thủ nhóm quy tắc riêng của nó. Ví dụ `Class<?>[]` phải nhận các class literal; `Mode[]` phải nhận enum constants; `Owner[]` phải nhận nested annotation values. Không khai báo element kiểu `String[][]` hoặc `int[][]`.

### 6.3. `null` không phải giá trị annotation hợp lệ

Không có giá trị `null` cho bất cứ annotation element nào; kể cả kiểu `String`, `Class<?>`, annotation type hay array. Muốn biểu đạt “chưa cấu hình”, cân nhắc `default ""`, `default {}`, một enum sentinel có tên rõ ràng, hoặc tách chính sách tùy biến sang runtime configuration. Sentinel phải có ngữ nghĩa được tài liệu hóa, vì `""` hoặc mảng rỗng cũng có thể là giá trị thật của nghiệp vụ.

## 7. Ví dụ Java 17 chạy được: đầy đủ các nhóm giá trị

Tạo một file duy nhất tên **`AnnotationValueDemo.java`** với nội dung sau:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

final class Constants {
    static final int BASE_RETRIES = 2;
    static final String PREFIX = "job-";
    private Constants() {}
}

enum Mode { FAST, SAFE }

@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String name();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Task {
    int retries();
    String label();
    Class<? extends Number> numberType();
    Mode mode();
    Owner owner();
    String[] tags();
    int timeoutMs() default 1_000 * 2;
}

@Task(
    retries = Constants.BASE_RETRIES + 1,
    label = Constants.PREFIX + "sync",
    numberType = Integer.class,
    mode = Mode.SAFE,
    owner = @Owner(name = "platform"),
    tags = {"core", "batch"}
)
final class SyncJob {}

public class AnnotationValueDemo {
    public static void main(String[] args) {
        Task meta = SyncJob.class.getAnnotation(Task.class);
        System.out.println("retries=" + meta.retries());
        System.out.println("label=" + meta.label());
        System.out.println("numberType=" + meta.numberType().getSimpleName());
        System.out.println("mode=" + meta.mode());
        System.out.println("owner=" + meta.owner().name());
        System.out.println("tags=" + Arrays.toString(meta.tags()));
        System.out.println("timeoutMs=" + meta.timeoutMs());
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 AnnotationValueDemo.java
java AnnotationValueDemo
~~~

**Stdout đã được kiểm chứng với `javac --release 17`:**

~~~text
retries=3
label=job-sync
numberType=Integer
mode=SAFE
owner=platform
tags=[core, batch]
timeoutMs=2000
~~~

Giải thích:

1. `retries = Constants.BASE_RETRIES + 1` và `label = Constants.PREFIX + "sync"` là hai constant expressions từ biến `static final` kiểu primitive/`String` có initializer là hằng.
2. `numberType = Integer.class` là **class literal**, thỏa ràng buộc `Class<? extends Number>`.
3. `mode = Mode.SAFE` là **enum constant**; không cần và không được thay bằng một biến alias enum.
4. `owner = @Owner(...)` là **nested annotation**, không phải gọi method hay constructor.
5. `tags = {"core", "batch"}` là **array initializer** gồm hai `String` literals hợp lệ.
6. `timeoutMs()` có default `1_000 * 2`, cũng là constant expression. Nơi sử dụng không khai báo `timeoutMs`, vì vậy chương trình đọc được giá trị `2000`.

Trong ví dụ này, `@Retention(RetentionPolicy.RUNTIME)` được dùng để demo đọc metadata qua reflection. **Retention là vấn đề độc lập với tính hợp lệ của element value**: kể cả khi retention là `SOURCE`, biểu thức element vẫn phải hợp lệ khi biên dịch; `RUNTIME` không cho phép method call hay biến runtime làm giá trị annotation.

## 8. Những lỗi biên dịch thường gặp ở nơi sử dụng

Bảng này giả định annotation element đã được khai báo với kiểu tương ứng.

| Viết trong annotation | Trạng thái | Lý do |
| --- | --- | --- |
| `retries = 1 + 2` (`int`) | Hợp lệ | Constant expression |
| `retries = Constants.BASE_RETRIES` (`int`) | Hợp lệ | Tham chiếu tới constant variable |
| `retries = Integer.parseInt("3")` | Lỗi | Method invocation không là constant expression |
| `label = "job-" + "sync"` (`String`) | Hợp lệ | Nối hai String constants |
| `label = System.getenv("JOB_NAME")` | Lỗi | Giá trị runtime |
| `numberType = Integer.class` (`Class<? extends Number>`) | Hợp lệ | Class literal có kiểu phù hợp |
| `numberType = String.class` (`Class<? extends Number>`) | Lỗi | Sai generic bound |
| `numberType = savedClass` (`Class<?>`) | Lỗi | Biến Class không phải class literal |
| `mode = Mode.FAST` (`Mode`) | Hợp lệ | Enum constant |
| `mode = ModeSettings.DEFAULT` (`Mode`) | Lỗi | Alias biến static final không phải enum constant |
| `owner = @Owner(name = "team")` | Hợp lệ | Nested annotation |
| `tags = {"a", "b"}` (`String[]`) | Hợp lệ | Annotation array initializer |
| `tags = "a"` (`String[]`) | Hợp lệ | Viết ngắn cho array một phần tử |
| `tags = someArray` (`String[]`) | Lỗi | Tham chiếu biến mảng |
| `label = null` | Lỗi | `null` bị cấm trong annotation element values |

### Một lỗi nhỏ nhưng dễ nhầm: static final vs immutable reference

~~~java
final class Values {
    static final int COUNT = 3;
    static final Integer BOXED = 3;
    static final String TEXT = "count-" + COUNT;
    static final String FROM_METHOD = String.valueOf(COUNT);
}
~~~

- `COUNT` có thể dùng cho element kiểu `int`.
- `BOXED` **không** phải constant variable (kiểu `Integer`, không phải primitive/`String`), dù tham chiếu là `final`. Một annotation element cũng không được khai báo kiểu `Integer`.
- `TEXT` có thể dùng cho element kiểu `String`.
- `FROM_METHOD` không thể dùng vì initializer là method invocation.

Java có thể tự động boxing một số giá trị trong biểu thức thông thường, nhưng quy tắc annotation type/value vẫn hẹp hơn nhiều.

## 9. Default value, công cụ biên dịch và thay đổi hằng

Một element default được khai báo bằng:

~~~java
@interface RetryPolicy {
    int maxAttempts() default 2 + 1;
    String[] labels() default {"safe", "internal"};
}
~~~

Default cũng là **annotation element value** và chịu cùng quy tắc về kiểu/hình thức biểu thức. `default` trong annotation element declaration **không phải Java interface default method**: không có method body; Java cung cấp giá trị khi đọc annotation mà nơi sử dụng không ghi đè element đó.

Khi thay giá trị default trong định nghĩa annotation và biên dịch/deploy phiên bản định nghĩa mới, annotation thiếu giá trị tường minh có thể được đọc ra default mới, kể cả class chứa annotation chưa được biên dịch lại. Do đó, **đổi default là đổi hành vi metadata**, cần xem xét tương thích. Ngược lại, tham chiếu tới constant variable primitive/`String` tại nơi dùng có thể đã được compiler đóng giá trị vào metadata của class sử dụng; thay constant tại nguồn khác **không bảo đảm** annotation đã biên dịch đổi theo. Với thay đổi loại này, cần biên dịch lại những class sử dụng annotation nếu muốn metadata đồng bộ.

Lưu ý: annotation không phải một cơ chế cấu hình động. Muốn giá trị như URL, timeout theo môi trường, feature flag hay secret thay đổi lúc triển khai, thường cần cấu hình runtime thay vì cố nhúng lời gọi `System.getenv` vào annotation. Có thể dùng annotation cho tên khóa cố định và để framework resolve giá trị runtime, nhưng **framework xử lý chuỗi đó**; Java compiler không thực thi nội suy môi trường một cách tự động.

## 10. Quy trình kiểm tra một annotation value

Khi compiler báo lỗi tại `@Something(...)`, kiểm tra lần lượt:

1. **Element tồn tại không?** Tên bên trái dấu `=` phải đúng tên method trong annotation type; các element bắt buộc phải được cung cấp hoặc có default.
2. **Element type có được phép khai báo không?** Chỉ primitive, `String`, `Class`, enum, annotation type, hoặc mảng một chiều của các kiểu hợp lệ.
3. **Giá trị thuộc nhóm nào?** Primitive/`String` cần constant expression; `Class` cần class literal; enum cần enum constant; nested annotation cần annotation literal; array cần initializer chứa các element values hợp lệ.
4. **Kiểu có tương thích không?** Kiểm tra generic bound của `Class<? extends ...>`, range số khi narrowing, kiểu từng phần tử của mảng và kiểu enum.
5. **Có đang đưa giá trị runtime vào metadata không?** Method call, field final được khởi tạo tại runtime, object/array creation, biến `Class` hay `null` thường là dấu hiệu sai.
6. **Có bỏ sót cú pháp shorthand không?** Chỉ một element tên `value` mới được dùng dạng `@Annotation(argument)`; array một phần tử có thể bỏ dấu ngoặc nhọn nếu compiler chấp nhận dạng single element value tương ứng.

Cách thực hành tốt nhất là tách một **file Java tối thiểu** chứa định nghĩa annotation và trường hợp dùng sai, chạy `javac --release 17` để xem thông báo compile error cụ thể. Không cần chờ đến khi chạy ứng dụng hoặc reflection mới phát hiện các lỗi mà ngôn ngữ đã xác định tại compile time.

## 11. Câu hỏi tự kiểm tra

**1. Vì sao `@Retry(count = 2 * 3)` hợp lệ, còn `@Retry(count = Math.max(2, 3))` sai?** Vì phép toán giữa literals có thể tạo constant expression, trong khi method invocation không thuộc các dạng constant expression được JLS cho phép.

**2. `static final String NAME = "api" + "-v1";` dùng được trong annotation không?** Có, vì đây là constant variable kiểu `String` với initializer hằng. Nếu initializer đổi thành `System.getProperty("name")`, câu trả lời trở thành không.

**3. Vì sao `@Codec(String.class)` hợp lệ nhưng `@Codec(Class.forName("java.lang.String"))` không?** Annotation yêu cầu class literal tương thích, chứ không nhận method trả về `Class`.

**4. Tại sao `@Execution(mode = Mode.SAFE)` hợp lệ nhưng `@Execution(mode = Holder.MODE)` không, dù `Holder.MODE` là `static final`?** Vì enum element bắt buộc là enum constant; biến reference tới enum không là một enum constant expression theo quy tắc annotation.

**5. Muốn ghi hai tag thì sử dụng `tags = {"a", "b"}` hay `tags = new String[]{"a", "b"}`?** Chọn array initializer đầu tiên. Annotation element value không cho dùng array creation expression.

**6. Có thể đặt `null` để báo một annotation element chưa được cấu hình không?** Không. Hãy định nghĩa default/sentinel có ý nghĩa rõ, hoặc đưa tùy chọn thực sự động sang cơ chế cấu hình khác.

## Tài liệu chuẩn để tra cứu

- **JLS §9.6.1 — Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.1
- **JLS §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.2
- **JLS §9.7.1 — Normal Annotations, Element Values:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.1
- **JLS §15.29 — Constant Expressions:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29
- **JLS §4.12.4 — Constant Variables:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4

Nếu một giá trị annotation khiến bạn phân vân, hãy xác định **kiểu trả về element** trước rồi áp đúng nhóm quy tắc tương ứng. `Class` literal, enum constant và nested annotation không phải “biểu thức hằng primitive/String” nhưng vẫn hợp lệ do có những quy tắc riêng; việc nhầm lẫn các nhóm này là nguồn gốc của rất nhiều lỗi cú pháp annotation.