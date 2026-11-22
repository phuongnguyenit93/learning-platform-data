# Vì sao `null`, lời gọi phương thức và đối tượng tùy ý không hợp lệ trong giá trị Java Annotation?

## 1. Annotation là metadata được khai báo theo quy tắc riêng

Một Java annotation gắn thông tin vào một declaration hoặc một type. Khi khai báo annotation bằng `@interface`, các phương thức không có tham số bên trong nó định nghĩa **phần tử (element)**; mỗi phần tử có một kiểu và có thể có giá trị `default`. Ví dụ:

```java
@interface Task {
    String name();
    int retryCount() default 3;
}
```

Ở nơi dùng annotation, `@Task(name = "compile")` cung cấp giá trị cho `name()`, còn `retryCount()` lấy mặc định `3`.

Khác với đối số truyền cho một phương thức Java thông thường, **giá trị annotation phải biểu diễn được theo các quy tắc ngôn ngữ tại thời điểm biên dịch**. Nó không phải một vị trí cho phép cung cấp bất kỳ biểu thức Java nào. Ba trường hợp dễ gây nhầm lẫn là:

- `null`: không phải giá trị hợp lệ của bất kỳ phần tử annotation nào, kể cả phần tử có kiểu tham chiếu.
- **Lời gọi phương thức**: `method()`, `System.getProperty(...)`, `SomeEnum.valueOf(...)` không tạo thành giá trị annotation hợp lệ, dù kết quả có kiểu phù hợp và việc tính toán có vẻ đơn giản.
- **Đối tượng tùy ý**: phần tử annotation không được khai báo với `Object`, `List<String>`, `LocalDate` hay các lớp tùy ý; biểu thức `new SomeClass(...)` cũng không phải giá trị annotation hợp lệ.

Để hiểu nguyên nhân, cần phân biệt hai tầng: **kiểu được phép ở phần tử** và **biểu thức được phép gán vào phần tử đó**.

## 2. Kiểu nào được phép khai báo làm phần tử?

Java giới hạn kiểu trả về của một element trong `@interface` vào các nhóm sau:

| Kiểu phần tử | Khai báo hợp lệ | Ví dụ giá trị hợp lệ |
|---|---|---|
| Kiểu nguyên thủy | `int level();`, `boolean enabled();` | `3`, `true` |
| `String` | `String name();` | `"compile"` |
| `Class` hoặc dạng tham số hóa phù hợp | `Class<?> type();` | `String.class` |
| Một kiểu enum | `Mode mode();` | `Mode.FAST` |
| Một kiểu annotation khác | `Info info();` | `@Info("core")` |
| Mảng **một chiều** của một trong các nhóm trên | `String[] tags();` | `{"java", "core"}` |

Ví dụ định nghĩa hợp lệ:

```java
enum Mode { FAST, SAFE }

@interface Info {
    String value();
}

@interface Config {
    String name();
    int attempts() default 1;
    Class<?> implementation();
    Mode mode() default Mode.SAFE;
    String[] tags() default {};
    Info info() default @Info("none");
}
```

Không được lấy cách hoạt động của generic Java hay tính đa hình để suy ra mọi `Object` đều dùng được trong annotation. Các khai báo sau **cố ý sai**, chỉ để minh họa và không thể biên dịch:

```java
@interface InvalidConfig {
    Object anything();              // Sai: Object không phải element type hợp lệ
    java.time.LocalDate date();     // Sai: lớp thông thường
    java.util.List<String> tags();  // Sai: List<String>
    String[][] matrix();            // Sai: mảng nhiều chiều
}
```

Điểm dễ nhầm: một phần tử `Class<?> implementation()` là **hợp lệ**, mặc dù đối tượng `Class` vẫn là một reference type. Nhưng giá trị cung cấp phải là **class literal** như `String.class`, chứ không phải tham chiếu đến một đối tượng `Class` tùy ý được tính hoặc lưu sẵn.

Các giới hạn về element type nằm trong Java Language Specification (JLS) §9.6.1; các giới hạn về giá trị nằm trong §9.7.1. Chúng không phải quy tắc riêng của Spring hay framework nào.

## 3. Vì sao `null` luôn sai?

Java bình thường cho phép `null` với các kiểu tham chiếu:

```java
String text = null;       // Hợp lệ trong code Java thông thường
Class<?> target = null;   // Hợp lệ trong code Java thông thường
```

Tuy nhiên, JLS quy định **giá trị của một phần tử annotation không được là `null`**. Điều kiện này áp dụng ngay cả khi element có kiểu `String`, `Class<?>`, enum, annotation lồng nhau hoặc mảng. Nó cũng áp dụng cho giá trị `default`.

```java
@interface Label {
    String value();
}

@Label("ready")
class ValidLabel {}

// KHÔNG HỢP LỆ: null không phải annotation element value
@Label(null)
class InvalidLabel {}
```

Giá trị mặc định cũng không thể là `null`:

```java
@interface InvalidDefaults {
    String name() default null;  // KHÔNG HỢP LỆ
}
```

Một biểu thức tạo ra `null` cũng không giải quyết được:

```java
@interface Name {
    String value();
}

// KHÔNG HỢP LỆ: biểu thức có giá trị null
@Name((String) null)
class InvalidName {}
```

**Vì sao có giới hạn này?** Annotation là metadata được compiler biểu diễn bằng những dạng giá trị xác định trong class file và được API annotation tiêu chuẩn diễn giải theo tập kiểu hạn chế. Theo mô hình này, `null` không thuộc tập các *element value* mà JLS cho phép. Nói chính xác, nguyên nhân pháp lý là quy tắc của **ngôn ngữ Java**, không phải vì mọi đối tượng tham chiếu trong JVM đều không thể chứa `null`.

Khi muốn biểu diễn trạng thái “không chỉ định”, hãy dùng một **quy ước rõ ràng trong API annotation**, ví dụ:

```java
@interface Endpoint {
    String description() default "";
    String[] tags() default {};
}
```

Ở đây `""` là chuỗi rỗng và `{}` là mảng rỗng; cả hai **đều hợp lệ**. Chúng không tự động mang ý nghĩa `null`: ý nghĩa “chưa khai báo” hay “không có phần tử” phải do tài liệu và code xử lý annotation định nghĩa. Chuỗi `"null"` cũng chỉ là một **chuỗi văn bản**, hoàn toàn khác giá trị `null`.

Nếu phân biệt “không cung cấp” với “cung cấp rỗng” là yêu cầu quan trọng, hãy thiết kế API annotation có quy ước hoặc phần tử riêng phù hợp, vì phần tử có `default` không cung cấp cách nhận `null` như một giá trị annotation.

## 4. Vì sao không thể truyền lời gọi phương thức?

Xem annotation này:

```java
@interface Label {
    String value();
}
```

Ví dụ **sai**:

```java
class Texts {
    static String generate() {
        return "compile";
    }
}

// KHÔNG HỢP LỆ: lời gọi phương thức không là hằng biên dịch
@Label(Texts.generate())
class InvalidTask {}
```

Dù `generate()` lúc chạy luôn trả cùng một chuỗi, nó vẫn là **lời gọi method tại runtime**, không phải **constant expression** theo JLS. Java compiler không chạy các phương thức do lập trình viên viết chỉ để lấy giá trị annotation, kể cả khi method là `static`, `final`, rất ngắn hoặc “không có tác dụng phụ”.

Một số biểu thức sai tương tự (mỗi khai báo là ví dụ riêng):

```java
@Label(System.getProperty("app.name"))
class FromProperty {}    // KHÔNG HỢP LỆ

@Label(String.valueOf(123))
class FromConversion {}  // KHÔNG HỢP LỆ

@Label("abc".toUpperCase())
class FromMethod {}      // KHÔNG HỢP LỆ
```

Cần phân biệt **giá trị cuối cùng** với **cách tạo ra giá trị**. `"ABC"` là string literal nên hợp lệ; `"abc".toUpperCase()` dù ta biết sẽ trả `"ABC"`, nhưng cú pháp là một lời gọi phương thức nên không thuộc constant expression hợp lệ cho `String` element.

### 4.1. Thay bằng biểu thức hằng biên dịch

Những biểu thức như literal, phép toán trên hằng và phép nối chuỗi của các hằng có thể được Java đánh giá ngay ở thời điểm biên dịch:

```java
final class Names {
    static final String PREFIX = "java";
    static final String MODULE = PREFIX + "-core";
    static final int RETRIES = 1 + 2;
}

@interface Build {
    String name();
    int retries();
}

@Build(name = Names.MODULE, retries = Names.RETRIES)
class JavaBuild {}
```

Phần tử `name` nhận `"java-core"`; `retries` nhận `3`. Các field được tham chiếu ở đây là **constant variable** (biến `final` thuộc kiểu nguyên thủy hoặc `String`, được khởi tạo bằng constant expression).

### 4.2. `static final` chưa đủ để biến mọi giá trị thành hằng biên dịch

Xét hai khai báo:

```java
class Names {
    static final String GOOD = "compile" + "-ready";
    static final String NOT_CONSTANT = new String("compile-ready");
}
```

`GOOD` là constant variable. `NOT_CONSTANT` cũng là `static final String` và không thể gán lại sau khi khởi tạo, nhưng việc tạo `new String(...)` khiến **initializer không phải constant expression**.

```java
@Label(Names.GOOD)
class ValidBuild {}

// KHÔNG HỢP LỆ: field NOT_CONSTANT không phải constant variable
@Label(Names.NOT_CONSTANT)
class InvalidBuild {}
```

Tương tự, `static final String S = System.getenv("APP")` và `static final int N = Integer.parseInt("3")` **không phải hằng biên dịch**. Từ khóa `final` chỉ giới hạn phép gán lại biến, không yêu cầu JVM có giá trị tại compile time.

### 4.3. Biểu thức điều kiện cũng có thể hợp lệ

Không phải **mọi biểu thức có toán tử** đều bị cấm. Khi toàn bộ toán hạng thỏa constant expression, dạng điều kiện cũng có thể hợp lệ:

```java
@Label(true ? "fast" : "safe")
class FixedChoice {}
```

Ngược lại, nếu điều kiện phụ thuộc một method như `Boolean.getBoolean("fast")`, biểu thức không còn là constant expression và không được dùng cho `String` element. Quy tắc cần kiểm tra là “**có phải constant expression không?**”, chứ không đơn giản “chỉ được dùng literal”.

## 5. Ngoại lệ có hình thức đặc biệt: `Class`, enum, annotation lồng nhau và mảng

Yêu cầu constant expression cho **kiểu nguyên thủy hoặc `String`** không có nghĩa rằng tất cả annotation value đều phải là literal số hoặc chuỗi. Các nhóm kiểu khác có **cú pháp hợp lệ đặc thù** theo JLS.

### 5.1. `Class<?> `: dùng class literal `.class`

```java
@interface Handler {
    Class<?> value();
}

@Handler(String.class)
class StringHandler {}

@Handler(int.class)
class PrimitiveHandler {}
```

`String.class`, `int.class` là **class literal expression**, được Java cho phép trực tiếp cho `Class`-typed annotation element. Ngược lại, cách sau không hợp lệ:

```java
class Types {
    static final Class<?> STRING_TYPE = String.class;
    static Class<?> lookup() { return String.class; }
}

// KHÔNG HỢP LỆ: tham chiếu biến kiểu Class, dù là static final
@Handler(Types.STRING_TYPE)
class FieldBasedHandler {}

// KHÔNG HỢP LỆ: lời gọi phương thức
@Handler(Types.lookup())
class DynamicHandler {}
```

`Class` là reference type, nhưng Java không hỗ trợ `Class`-typed **constant variable** theo định nghĩa constant variable chỉ dành cho primitive và `String`. Vì vậy, ngay cả khi một field `static final Class<?>` luôn chứa `String.class`, tại nơi dùng annotation vẫn phải viết một **class literal**.

### 5.2. Enum: dùng enum constant

```java
enum Mode { FAST, SAFE }

@interface RunMode {
    Mode value();
}

@RunMode(Mode.FAST)
class QuickTask {}
```

`Mode.FAST` là **enum constant**, hợp lệ. Các biểu thức dưới đây không hợp lệ:

```java
class Modes {
    static final Mode DEFAULT = Mode.FAST;
}

// KHÔNG HỢP LỆ: biến final kiểu enum không phải enum constant trực tiếp
@RunMode(Modes.DEFAULT)
class FromAlias {}

// KHÔNG HỢP LỆ: lời gọi method không phải enum constant
@RunMode(Mode.valueOf("FAST"))
class FromMethod {}
```

Ở đây `Mode.FAST` không phải một `String` constant expression. Nó hợp lệ vì JLS có quy tắc riêng cho enum element: phải là **enum constant** phù hợp kiểu.

### 5.3. Annotation lồng nhau: dùng cú pháp annotation

```java
@interface Info {
    String value();
}

@interface Detail {
    Info value();
}

@Detail(@Info("verified"))
class Document {}
```

Một annotation là kiểu giá trị được hỗ trợ để lồng vào annotation khác. Dạng `@Info("verified")` là **annotation expression** có cú pháp riêng, không phải lời gọi constructor như `new Info(...)` và cũng không thể thay thế bằng một object trả về từ method.

### 5.4. Mảng: dùng initializer trong annotation

```java
@interface Tags {
    String[] value();
}

@Tags({"java", "core"})
class MultiTags {}

@Tags("java")
class OneTag {}

@Tags({})
class NoTags {}
```

`@Tags("java")` là cú pháp gọn được cho phép: đối với phần tử có kiểu mảng, một giá trị phần tử đơn có thể thay cho mảng một phần tử. Vì thế kết quả đọc `value()` vẫn là `String[]`. Với nhiều giá trị hoặc mảng rỗng, dùng `{...}`.

Các dạng sau **không hợp lệ**:

```java
@Tags({null})
class NullElement {}      // null không hợp lệ ngay cả trong mảng

@Tags(new String[]{"java"})
class ConstructedArray {} // không dùng new String[] cho annotation element

class TagStore {
    static final String[] VALUES = {"java"};
}

@Tags(TagStore.VALUES)
class ArrayField {}       // không dùng biến tham chiếu mảng
```

Không phải vì `new String[]` không thể tạo một mảng, mà vì **annotation element value** yêu cầu dạng *element-value array initializer* `{...}` hoặc một *element value* đơn hợp lệ theo kiểu phần tử, không phải một phép tạo đối tượng/mảng tùy ý.

## 6. Ví dụ hoàn chỉnh chạy được bằng Java 17+

Tạo tệp **Main.java**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@interface Detail {
    String value();
}

enum Policy {
    STRICT, LENIENT
}

final class Const {
    static final String TITLE = "module" + "-A";
    static final int RETRIES = 1 + 2;

    // Hai field sau là reference, không được truyền qua tên field
    // làm annotation element value:
    static final Class<?> TYPE = String.class;
    static final Policy DEFAULT_POLICY = Policy.STRICT;
}

@Retention(RetentionPolicy.RUNTIME)
@interface Stamp {
    String title();
    int retries() default 2;
    Class<?> target();
    Policy policy();
    String[] tags() default {};
    Detail detail() default @Detail("none");
}

@Stamp(
        title = Const.TITLE,
        retries = Const.RETRIES,
        target = String.class,
        policy = Policy.STRICT,
        tags = {"java", "annotation"},
        detail = @Detail("checked")
)
class Job {}

public class Main {
    public static void main(String[] args) {
        Stamp stamp = Job.class.getAnnotation(Stamp.class);
        System.out.println("title=" + stamp.title());
        System.out.println("retries=" + stamp.retries());
        System.out.println("target=" + stamp.target().getName());
        System.out.println("policy=" + stamp.policy());
        System.out.println("tags=" + Arrays.toString(stamp.tags()));
        System.out.println("detail=" + stamp.detail().value());
    }
}
```

Biên dịch và chạy tại thư mục chứa file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Kết quả chuẩn:

```text
title=module-A
retries=3
target=java.lang.String
policy=STRICT
tags=[java, annotation]
detail=checked
```

**Giải thích theo từng giá trị:**

1. `Const.TITLE` được compiler tính thành `"module-A"`, và `Const.RETRIES` thành `3`: hai field `String`/`int` đều là constant variables.
2. `String.class` là class literal. Mã không dùng `Const.TYPE`, vì reference tới field kiểu `Class<?>` không hợp lệ ở annotation.
3. `Policy.STRICT` là enum constant trực tiếp. Mã không dùng `Const.DEFAULT_POLICY`, dù nó là `static final`.
4. `{"java", "annotation"}` là array initializer có từng phần tử hợp lệ.
5. `@Detail("checked")` là annotation lồng nhau. `@Retention(RUNTIME)` cho phép xem metadata qua reflection ở ví dụ này; quy tắc giá trị hợp lệ áp dụng cả khi không sử dụng reflection.

Ví dụ này cho thấy annotation lưu **metadata có cấu trúc và được kiểm tra lúc biên dịch**, không thực thi method khi đọc annotation. Lúc chạy, `getAnnotation()` trả về đại diện annotation để truy cập các giá trị đã khai báo.

## 7. Quy tắc áp dụng giống nhau cho `default`

Có thể dễ mắc lỗi khi tập trung kiểm tra các giá trị ở nơi sử dụng mà bỏ qua dòng `default` trong định nghĩa `@interface`.

Ví dụ hợp lệ:

```java
enum State { READY, PAUSED }

@interface Feature {
    String name() default "unknown";
    int timeout() default 2 * 30;
    Class<?> handler() default String.class;
    State state() default State.READY;
    String[] tags() default {};
}
```

Ví dụ sai, chỉ dùng để phân tích và **không thể biên dịch**:

```java
@interface InvalidFeature {
    String name() default null;                // null bị cấm
    String title() default System.getProperty("title"); // method call
    Class<?> handler() default Object.class.getClass(); // method call
}
```

Nếu muốn một giá trị “không đặt”, hãy cân nhắc một giá trị mặc định có ý nghĩa rõ ràng như `""`, `{}`, một enum constant `UNSPECIFIED`, hoặc một class sentinel như `Void.class` (nếu hợp đồng API quy định như vậy). **Đừng mặc định mọi framework diễn giải `Void.class` hay chuỗi rỗng giống nhau**.

## 8. Cách kiểm tra một lỗi annotation value

Khi thấy lỗi `element value must be a constant expression` hoặc thông báo tương tự, hãy kiểm tra theo thứ tự:

1. **Kiểu element** trong `@interface` có thuộc nhóm được Java hỗ trợ không? Nếu là `Object`, `List`, wrapper như `Integer`, kiểu domain class hoặc mảng hai chiều, cần sửa định nghĩa.
2. **Có `null` không?** `null` bị cấm đối với mọi loại phần tử, bao gồm cả từng phần tử mảng.
3. **Nếu là primitive/`String`**: có phải constant expression không? Literal, toán tử hợp lệ và biến `final` kiểu primitive/`String` khởi tạo từ hằng có thể dùng; method call, `new`, lấy dữ liệu cấu hình runtime thì không.
4. **Nếu là `Class`**: có đang viết trực tiếp `Type.class` (hoặc primitive class literal) không? Không thay bằng field `static final Class<?> TYPE` hay method trả `Class`.
5. **Nếu là enum**: có đang dùng chính enum constant (`Mode.FAST`) không? Tránh field alias, kết quả `valueOf()` hoặc factory method.
6. **Nếu là annotation hoặc mảng**: dùng `@Nested(...)` và `{...}` đúng cú pháp; bảo đảm từng phần tử con cũng đáp ứng quy tắc tương ứng.
7. **Đọc đúng warning/error của compiler**: thông điệp có thể khác nhau giữa `javac` và IDE, nhưng nguyên nhân cần đối chiếu với JLS §9.6.1 và §9.7.1.

### Bài tự kiểm tra

Cho:

```java
@interface Label {
    String value();
}

class Constants {
    static final String A = "java" + "-17";
    static final String B = new String("java-17");
    static String get() { return "java-17"; }
}
```

Xác định dòng nào biên dịch (các dòng dưới đây là **những ví dụ độc lập**, trong đó có dòng sai):

```java
@Label("java-17")       // (1) hợp lệ: literal
@Label(Constants.A)     // (2) hợp lệ: constant variable
@Label(Constants.B)     // (3) sai: initializer dùng new
@Label(Constants.get()) // (4) sai: method call
@Label(null)            // (5) sai: null
@Label("java" + "-17")  // (6) hợp lệ: nối các chuỗi hằng
```

Không có khác biệt runtime đáng kể giữa ba cách hợp lệ (1), (2) và (6): tất cả đều biểu diễn cùng giá trị `String` trong annotation. Ba cách sai không trở thành hợp lệ bằng cách thêm `static` hoặc `final` tùy ý.

## 9. Tài liệu chuẩn

- [Java Language Specification 17, §9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1): các kiểu trả về hợp lệ của phần tử annotation.
- [Java Language Specification 17, §9.7.1 — Normal Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): điều kiện *commensurate* của element value, trong đó `null` bị loại bỏ; `Class`, enum, mảng có quy tắc riêng.
- [Java Language Specification 17, §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): biểu thức hằng và phép tính được phép dùng cho primitive/`String` element.
- [Java Language Specification 17, §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): định nghĩa **constant variable**.

**Điều cần nhớ:** Giá trị annotation chịu ràng buộc mạnh hơn đối số method thông thường. `null` không bao giờ hợp lệ. Primitive và `String` phải là **constant expression**; `Class`, enum, annotation lồng nhau và mảng có dạng cú pháp cố định. Một lời gọi method hoặc tham chiếu object `static final` không tự trở thành metadata hợp lệ chỉ vì kết quả của nó đã biết trước.