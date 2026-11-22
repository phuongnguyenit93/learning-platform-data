# Enum và kiểu annotation không được khai báo tham số kiểu trong Java Generics

## 1. Vấn đề và mục tiêu

Java Generics cho phép định nghĩa class hoặc interface có **tham số kiểu**:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

interface Converter<I, O> {
    O convert(I input);
}
```

Caller có thể dùng `Box<String>`, `Box<Integer>` hoặc `Converter<String, Integer>`. Nhưng **không phải mọi dạng khai báo kiểu trong Java đều được phép đặt `<T>` ngay sau tên**. Hai trường hợp quan trọng:

```java
// Không hợp lệ:
enum Choice<T> {
    FIRST, SECOND
}
```

```java
// Không hợp lệ:
@interface Info<T> {
    T value();
}
```

Với Java 17, `javac` báo lần lượt những lỗi có nội dung chính:

```text
error: enums cannot be generic
```

```text
error: annotation interface Info cannot be generic
```

Điều này không có nghĩa enum hoặc annotation “không thể liên quan đến Generics”. Một enum vẫn **có thể triển khai generic interface, có method generic, có field sử dụng parameterized type**. Annotation vẫn có thể sử dụng **một số kiểu `Class` có type argument** làm kiểu trả về của element, và có thể được gắn lên generic class, type parameter hoặc type argument theo `@Target`.

Bài này giúp phân biệt:

- Những khai báo generic **bị cấm** ở cấp `enum` và `@interface`.
- Những **cách sử dụng Generics vẫn hợp lệ** bên trong enum hoặc khi định nghĩa/sử dụng annotation.
- Vì sao `Enum<E extends Enum<E>>` trong thư viện chuẩn **không** có nghĩa chúng ta được viết `enum E<T>`.
- Vì sao annotation elements bị giới hạn kiểu trả về và không phải method generic thông thường.
- Cách mô hình hóa enum gắn với generic API và annotation metadata một cách type-safe.
- Lỗi compiler, ví dụ Java 17 chạy được, bài tập và hướng khắc phục.

## 2. Bắt đầu từ bốn khái niệm không được nhầm

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Generic **class** | `class Holder<T> {}` | Class tự khai báo một hoặc nhiều type parameter. |
| Generic **interface** | `interface Codec<T> {}` | Interface tự khai báo type parameter. |
| **Parameterized type** | `Codec<Integer>`, `List<String>` | Một kiểu generic được **sử dụng** với type argument cụ thể. |
| Generic **method** | `<T> T echo(T x)` | Phương thức khai báo type parameter riêng, độc lập với việc class có generic hay không. |

Một `enum` có thể sử dụng **parameterized type** hoặc khai báo **generic method**, nhưng không thể là một **generic enum declaration** với `<T>` sau tên.

Một `@interface` không thể là **generic annotation declaration**; hơn nữa các method tạo thành **annotation elements** cũng không được generic như `<T> T value()`.

**Quy tắc đọc source:** trước khi kết luận “Java cấm Generics ở đây”, hãy tìm xem `<T>` là tham số kiểu **của chính enum/annotation**, của **một method trong enum**, hay là type argument của một interface/class mà enum đang dùng. Các vị trí khác nhau tuân theo quy tắc khác nhau.

## 3. Vì sao Java không cho khai báo `enum E<T>`?

Ví dụ cố ý sai:

```java
enum State<T> {
    NEW, DONE
}
```

Biên dịch với Java 17 sẽ gặp lỗi:

```text
error: enums cannot be generic
```

Enum declaration chỉ có thể khai báo một tập hữu hạn các **enum constants** thuộc kiểu enum đó. Java không hỗ trợ cú pháp khai báo type parameters trên chính enum như đối với class hoặc interface thông thường.

Điều đáng chú ý: ngay cả một enum chỉ có một kiểu giá trị liên quan đến `T` cũng không được viết:

```java
// Cố tình sai:
enum Token<T> {
    TEXT, NUMBER
}
```

Không có cách hợp lệ để “cung cấp” `T` khi sử dụng từng enum constant bằng cú pháp `Token<String>.TEXT`. Nếu hệ thống cần các giá trị biến thiên mạnh theo type parameter, hãy dùng generic class, record, interface hoặc mô hình domain phù hợp.

### 3.1. Enum là một kiểu riêng, không phải class generic do người dùng khai báo

Một enum vẫn là một kiểu tham chiếu có các instance cố định, có thể:

- Khai báo constructor, field và instance method.
- Khai báo static method và generic method.
- Triển khai interface.
- Chứa enum constant-specific class body để ghi đè hành vi.
- Sử dụng generic collections như `List<String>` và `Map<String,Integer>` bên trong code.

Nhưng **không được** đặt danh sách type parameter sau tên enum:

```java
// Sai: khai báo enum generic.
enum Status<T> { READY; }

// Đúng: enum không có tham số kiểu.
enum Status { READY; }
```

### 3.2. `Enum<E extends Enum<E>>` là trường hợp khác

Trong Java API có class trừu tượng chuẩn:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Chỉ là trích đoạn mô tả quan hệ kiểu.
}
```

Đây là **một generic class có sẵn trong JDK** để làm lớp cha của enum. Một enum cụ thể như `Status` được Java cho quan hệ kiểu tương ứng với `Enum<Status>` theo các quy tắc chuyên biệt của enum.

Vì vậy:

```java
enum Status {
    READY, DONE
}
```

không hề tự khai báo `<T>`. Việc superclass `Enum` **được thiết kế generic** không đồng nghĩa declaration `enum` cũng được phép generic.

Không thể viết:

```java
// Cố tình sai: enum không được tự khai báo type parameter.
// enum Status<T> extends Enum<Status<T>> { ... }
```

Thực tế, enum có quan hệ lớp cha chuyên biệt do Java quy định; lập trình viên cũng không được tự chỉ định một `extends` clause cho enum như class thông thường.

## 4. Enum vẫn triển khai được generic interface

Một giải pháp thiết kế hợp lệ:

```java
interface Decoder<T> {
    T decode(String source);
}

enum NumberLevel implements Decoder<Integer> {
    LOW(1), HIGH(3);

    private final int multiplier;

    NumberLevel(int multiplier) {
        this.multiplier = multiplier;
    }

    @Override
    public Integer decode(String source) {
        return Integer.valueOf(source) * multiplier;
    }
}
```

`NumberLevel` **không** phải một enum generic: nó không khai báo `<T>`. Thay vào đó, nó triển khai **parameterized interface** `Decoder<Integer>`.

Caller:

```java
Decoder<Integer> decoder = NumberLevel.HIGH;
Integer result = decoder.decode("7"); // 21
```

Compiler kiểm tra kiểu trả về và tham số qua `Decoder<Integer>`. Mỗi enum constant vẫn là giá trị thuộc enum `NumberLevel`.

### 4.1. Bound/type argument được chốt tại enum declaration

Toàn bộ enum `NumberLevel` triển khai `Decoder<Integer>`, không phải một constant triển khai `Decoder<String>` còn constant khác triển khai `Decoder<Double>` theo những specialization tùy chọn của chính enum.

Ví dụ mong muốn nhưng không được tạo bằng `<T>` của enum:

```java
// Không có cú pháp kiểu riêng cho từng constant:
// NumberLevel<String>.LOW
// NumberLevel<Integer>.HIGH
```

Nếu mỗi loại giá trị có hợp đồng generic khác nhau, cân nhắc một generic sealed interface và nhiều concrete implementations, hoặc các typed descriptor objects. Dùng một enum chung khi các constant thật sự chia sẻ cùng một API và kiểu dữ liệu.

### 4.2. Enum có thể lưu dữ liệu mang kiểu generic

Ví dụ field sử dụng parameterized type:

```java
enum MessageType {
    INFO, ERROR;

    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    java.util.List<String> tags() {
        return java.util.List.copyOf(tags);
    }
}
```

`List<String>` là **kiểu của field/return**, không phải type parameter của enum. Cấu trúc này hợp lệ.

Lưu ý enum constants là các instance được chia sẻ trong phạm vi chương trình, tương tự singleton cho từng constant. Nếu field là mutable, cần suy nghĩ tới ownership, thread safety và cách xuất dữ liệu. Phương thức `List.copyOf` tạo snapshot không thể sửa qua API cập nhật thông thường, nhưng bản thân enum vẫn cần chính sách mutation phù hợp.

## 5. Generic method bên trong enum là hợp lệ

Một phương thức có thể tự khai báo `<T>` dù enum chứa nó không generic:

```java
enum Utility {
    INSTANCE;

    public <T> T echo(T value) {
        return value;
    }
}
```

Cách dùng:

```java
String text = Utility.INSTANCE.echo("Java");
Integer number = Utility.INSTANCE.echo(42);
```

Type variable `T` ở đây thuộc **method `echo`**. Compiler có thể suy luận kiểu cho từng lời gọi độc lập; không cần class/enum có một tham số kiểu cố định.

Đừng nhầm:

```java
enum Utility<T> { INSTANCE; } // Sai.
```

với:

```java
enum Utility {
    INSTANCE;

    <T> T echo(T value) { return value; } // Đúng.
}
```

### 5.1. Generic static method với enum-bound

Một trường hợp thực tế là thao tác tổng quát với **bất kỳ enum nào**:

```java
static <E extends Enum<E>> E parse(
        Class<E> enumClass, String name) {
    return Enum.valueOf(enumClass, name);
}
```

Cách gọi:

```java
Level level = parse(Level.class, "HIGH");
```

`E extends Enum<E>` là **F-bound** thường gặp khi viết helper cho enum. `E` là type parameter **của method**, không phải type parameter được khai báo trên `enum Level`.

`Class<E>` được caller truyền vào giúp method biết enum class cụ thể ở runtime. Đây không phải phép thay thế cho một generic enum declaration; nó là cách xây generic API **xử lý enum**.

### 5.2. `EnumSet<E>` và `EnumMap<K,V>` không phải generic enum

JDK có những class generic được thiết kế chuyên cho enum:

```java
java.util.EnumSet<Level> levels =
        java.util.EnumSet.of(Level.LOW, Level.HIGH);

java.util.EnumMap<Level, String> labels =
        new java.util.EnumMap<>(Level.class);

labels.put(Level.LOW, "Low");
```

`EnumSet` và `EnumMap` là **generic collection classes** sử dụng enum làm type argument/key. Điều đó hoàn toàn khác với khai báo `enum Level<T>`.

`EnumMap<K,V>` yêu cầu `K` là kiểu enum phù hợp; `EnumSet<E>` cũng yêu cầu type argument là enum type. Chúng giúp bạn gắn dữ liệu có kiểu vào enum constants mà không cần generic enum declaration.

## 6. Enum constant có class body riêng: được nhưng không tạo generic enum

Enum có thể khai báo hành vi khác nhau theo từng constant:

```java
enum Action {
    START {
        @Override
        public String execute() {
            return "starting";
        }
    },
    STOP {
        @Override
        public String execute() {
            return "stopping";
        }
    };

    public abstract String execute();
}
```

Cả hai constant vẫn thuộc enum `Action`. Constant-specific class body cho phép override các instance methods, nhưng **không khiến từng constant có một tham số kiểu riêng**.

Ví dụ trên không liên quan tới việc `Action` generic. Đây là hình thức đa hình đặc trưng của enum, khác với việc tạo nhiều subtype generic độc lập.

Nếu cố viết:

```java
// Cố tình sai:
// enum Action { <T> START; }
```

compiler từ chối do cú pháp enum constant không cho khai báo `<T>` như vậy.

## 7. `@interface` không được khai báo type parameters

Annotation interface được khai báo theo cú pháp:

```java
@interface Label {
    String value();
}
```

Không thể thêm `<T>` vào tên:

```java
// Cố tình sai:
@interface Label<T> {
    T value();
}
```

Trên Java 17, compiler báo:

```text
error: annotation interface Label cannot be generic
```

Và còn có thể báo thêm rằng `T` không phải kiểu hợp lệ cho một annotation element.

Lý do không nên hiểu đơn giản là “annotation không chứa object”: Java annotations là **metadata có cấu trúc và bộ kiểu giá trị được ngôn ngữ quy định**, phục vụ compiler, class file và Reflection. Java áp đặt một mô hình khai báo cố định, không phải một interface generic tùy ý.

### 7.1. Annotation interface là một dạng khai báo đặc biệt

Dù tên gọi có chứa từ “interface”, annotation interface **không tương đương một interface thông thường với toàn bộ cú pháp tự do của interface**. Nó có các element declarations với những ràng buộc riêng về:

- Kiểu kết quả.
- Việc không nhận tham số.
- Việc không khai báo type parameter cho element method.
- Default value.
- Khả năng biểu diễn annotation value trong class file và sử dụng ở vị trí annotation.

Bạn không thể khắc phục việc `@interface X<T>` không hợp lệ bằng cách gán một bound `<T extends SomeClass>`. Giới hạn nằm ở **dạng khai báo annotation**.

## 8. Annotation element có thể có kiểu nào?

Một annotation element như:

```java
@interface Label {
    String value();
}
```

trông giống method signature, nhưng kiểu trả về của nó bị giới hạn. Các nhóm hợp lệ về bản chất gồm:

1. Primitive (`int`, `boolean`, `long`, v.v.).
2. `String`.
3. `Class` hoặc một **parameterized invocation của `Class`** thích hợp như `Class<?>`, `Class<? extends Number>`.
4. Một enum type.
5. Một annotation type khác.
6. **Mảng một chiều** của một trong các loại trên.

Ví dụ:

```java
@interface Rule {
    int priority() default 1;
    String name() default "default";
    Class<?> type();
    Class<? extends Number> numberType() default Integer.class;
    String[] tags() default {};
}
```

Việc `Class<? extends Number>` xuất hiện **không làm `Rule` trở thành annotation generic**. Nó chỉ là **kiểu kết quả hợp lệ của một annotation element**.

### 8.1. Bảng phân biệt kiểu element

| Kiểu trả về element | Được phép? | Lưu ý |
| --- | --- | --- |
| `int`, `boolean`, `double` | Có | Primitive. |
| `String` | Có | Một chuỗi; khi dùng annotation phải có giá trị hợp lệ theo ngữ cảnh. |
| `Class<?>` | Có | Có thể lưu class literal phù hợp. |
| `Class<? extends Number>` | Có | Class literal phải đáp ứng bound. |
| `Class<String>` | Có | Một dạng parameterized invocation của `Class`. |
| `SomeEnum` | Có | Một enum type. |
| `NestedAnnotation` | Có | Một annotation type. |
| `String[]`, `Class<?>[]`, `SomeEnum[]` | Có | Chỉ một chiều của loại element hợp lệ. |
| `Object` | Không | Kiểu trả về không thuộc nhóm được phép. |
| `List<String>` | Không | Không được dùng collection generic tùy ý làm annotation element. |
| `Map<String, Object>` | Không | Không thuộc nhóm element type hợp lệ. |
| `T` trong một annotation generic tưởng tượng | Không | Annotation không có type parameter `T`. |
| `String[][]` | Không | Mảng nhiều chiều không phải annotation element type hợp lệ. |

**Điểm tinh tế:** `Class<?>` có generic wildcard và hoàn toàn hợp lệ làm annotation element; nhưng điều đó không đồng nghĩa mọi parameterized type như `List<String>` đều được phép.

### 8.2. `Class<? extends Number>` lưu loại class, không lưu instance

Ví dụ annotation:

```java
@interface NumberRule {
    Class<? extends Number> numberType()
            default Integer.class;
}
```

Cách dùng:

```java
@NumberRule(numberType = Double.class)
class Report {
}
```

`Double.class` là class literal có quan hệ kiểu phù hợp. Annotation không giữ một `Double` instance hay một `List<Double>` runtime được validate. Nó lưu **metadata là một class**.

Trường hợp như `Class<? extends Number>` hữu ích để chỉ định loại implementation, validator hay adapter trong frameworks, nhưng khi framework muốn khởi tạo class đó, nó vẫn phải xử lý constructor/dependency/access rules. Class literal **không bảo đảm** có constructor không tham số.

### 8.3. Giá trị annotation phải thuộc các dạng cho phép

Khi sử dụng annotation, giá trị element thường là literal/constant expression của kiểu phù hợp, class literal, enum constant, annotation hoặc array initializer gồm các dạng hợp lệ. Không thể truyền một arbitrary object vừa được tạo:

```java
// Sai: annotation không nhận List<String> làm element.
// @Tag(values = new ArrayList<String>())
```

Ngay cả khi một kiểu cụ thể có constructor public, điều đó không cho phép dùng `new SomeObject()` làm annotation value tùy ý.

### 8.4. `value()` có cú pháp rút gọn

```java
@interface Title {
    String value();
}

@Title("Generics")
class Guide {
}
```

Element tên `value` có cú pháp gán ngắn gọn. Đây là tiện ích của annotation syntax, **không phải** một generic method, và không thêm type parameter vào annotation.

## 9. Method generic trong annotation interface cũng không hợp lệ

Một annotation element không thể khai báo type parameter:

```java
// Cố tình sai:
@interface InvalidElement {
    <T> T value();
}
```

Trên Java 17, compiler báo:

```text
error: elements in annotation interface declarations cannot be generic methods
```

Thêm `<T>` trước kiểu trả về không thể biến annotation element thành factory hoặc generic accessor tùy ý. Đây là khác biệt lớn giữa generic method được phép trong enum và element declarations của annotation.

Bảng ghi nhớ:

| Vị trí khai báo | Có thể đặt `<T>` không? |
| --- | --- |
| `class Holder<T>` | Có |
| `interface Codec<T>` | Có |
| `enum State<T>` | **Không** |
| `@interface Label<T>` | **Không** |
| `<T> T echo(T x)` bên trong enum | Có |
| `<T> T value()` là annotation element | **Không** |

Một annotation type có thể chứa constants/nested declarations theo luật ngôn ngữ, nhưng các method element không có độ tự do tương đương những generic methods thông thường.

## 10. Annotation dùng enum làm element: hợp lệ và type-safe

Enum thường là lựa chọn tốt để định nghĩa các giá trị metadata cố định:

```java
enum Severity {
    INFO, WARNING, ERROR
}

@interface Audit {
    Severity severity() default Severity.INFO;
    String message() default "";
}
```

Cách dùng:

```java
@Audit(severity = Severity.ERROR, message = "failed")
class Service {
}
```

Compiler kiểm tra `Severity.ERROR` có đúng enum type của element hay không. Nếu truyền enum constant từ enum **khác**, compiler từ chối do sai kiểu.

Annotation `Audit` vẫn **không generic**. Nó chỉ có một element kiểu `Severity`, là enum type hợp lệ.

### 10.1. Có thể dùng enum trong mảng annotation element

```java
@interface Allowed {
    Severity[] levels() default {
        Severity.INFO, Severity.WARNING
    };
}
```

Mảng một chiều của enum là loại element hợp lệ. Khi đọc annotation bằng Reflection, caller nhận array tương ứng. Với annotation runtime, API thường trả bản sao khi cần bảo vệ tính bất biến của annotation instance; không nên xem array nhận được là API sửa annotation metadata.

## 11. Annotation lồng annotation: thay cho object tùy ý

Nếu cần mô tả metadata phức tạp hơn một chuỗi hoặc enum đơn lẻ:

```java
@interface Range {
    int min();
    int max();
}

@interface Check {
    Range range();
    String label() default "";
}
```

Áp dụng:

```java
@Check(range = @Range(min = 1, max = 10), label = "age")
class ValidatedField {
}
```

Ví dụ minh họa này dùng annotation type `Range` làm kết quả của element `range`. Cách thiết kế này tận dụng đúng bộ kiểu được annotation hỗ trợ, thay vì cố khai báo `List<Range>` hoặc một object dữ liệu tự do làm element.

Nếu metadata thực sự cần một tập hợp nhiều bản ghi phức tạp, bạn có thể dùng **mảng một chiều của annotation**:

```java
@interface RuleItem {
    String name();
    int weight();
}

@interface RuleSet {
    RuleItem[] value();
}
```

Khi thiết kế schema annotation, hãy ưu tiên sự rõ ràng và tương thích với compiler/class-file rules. Không biến một annotation thành cơ chế serialization đầy đủ cho cấu trúc đối tượng không bị giới hạn.

## 12. Ví dụ Java 17 hoàn chỉnh: enum + generic interface + annotation

Tạo file **`EnumAnnotationGenericsDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

public class EnumAnnotationGenericsDemo {
    interface Codec<T> {
        T decode(String text);
    }

    enum Level implements Codec<Integer> {
        LOW(1), HIGH(3);

        private final int weight;

        Level(int weight) {
            this.weight = weight;
        }

        @Override
        public Integer decode(String text) {
            return Integer.valueOf(text) * weight;
        }

        public <T> T echo(T value) {
            return value;
        }
    }

    enum Action {
        START {
            @Override
            public String execute() {
                return "starting";
            }
        },
        STOP {
            @Override
            public String execute() {
                return "stopping";
            }
        };

        public abstract String execute();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Rule {
        Class<?> type();
        Class<? extends Number> numberType()
                default Integer.class;
        Level level() default Level.LOW;
        String[] tags() default {};
    }

    @Rule(
            type = String.class,
            numberType = Double.class,
            level = Level.HIGH,
            tags = {"core", "generics"}
    )
    static class Example {
    }

    static <E extends Enum<E>> E parse(
            Class<E> kind, String name) {
        return Enum.valueOf(kind, name);
    }

    public static void main(String[] args) {
        System.out.println("enum=" + Level.HIGH.name());
        System.out.println("interface=" + Level.HIGH.decode("7"));
        System.out.println("method=" + Level.LOW.echo("ok"));
        System.out.println("action=" + Action.START.execute());
        System.out.println("parse=" + parse(Level.class, "LOW"));

        Rule rule = Example.class.getAnnotation(Rule.class);
        System.out.println("annotation="
                + rule.type().getSimpleName() + ":"
                + rule.numberType().getSimpleName() + ":"
                + rule.level());
        System.out.println("tags=" + List.of(rule.tags()));
    }
}
```

Chương trình sử dụng Java 17 hoặc JDK mới hơn có hỗ trợ `--release 17`. Chạy:

```bash
javac --release 17 -Xlint:all EnumAnnotationGenericsDemo.java
java EnumAnnotationGenericsDemo
```

Đã kiểm chứng: biên dịch thành công **không có warning**, stdout:

```text
enum=HIGH
interface=21
method=ok
action=starting
parse=LOW
annotation=String:Double:HIGH
tags=[core, generics]
```

### 12.1. Phân tích `enum=HIGH` và `interface=21`

`Level.HIGH` là một enum constant thuộc enum `Level` không generic. `Level` triển khai `Codec<Integer>`:

```java
enum Level implements Codec<Integer> { ... }
```

`decode("7")` trả `Integer` có giá trị `7 * 3 = 21`. Compiler biết `Codec<Integer>` yêu cầu kiểu kết quả phù hợp với `Integer`. Không cần `enum Level<T>`.

### 12.2. Phân tích `method=ok`

Method:

```java
public <T> T echo(T value) {
    return value;
}
```

được khai báo bên trong enum. `T` chỉ thuộc phạm vi method, nên compiler có thể suy luận `T = String` khi gọi `echo("ok")`.

Điều này chứng minh **enum không generic** vẫn có thể có **generic method**.

### 12.3. Phân tích `action=starting`

Enum `Action` dùng constant-specific class body để override `execute()`. Không có generic parameter ở cấp enum. Đây là đa hình theo enum constant, không phải chuyên biệt hóa enum theo `T`.

### 12.4. Phân tích `parse=LOW`

Generic helper:

```java
static <E extends Enum<E>> E parse(
        Class<E> kind, String name) {
    return Enum.valueOf(kind, name);
}
```

dùng enum-bound để nhận một enum type cụ thể; `Level.class` là class token mà caller cung cấp. Mọi thông tin cần thiết được truyền vào helper rõ ràng, không yêu cầu enum declaration có type parameter.

Nếu tên không tồn tại, `Enum.valueOf` ném `IllegalArgumentException`; không tự trả null. Hãy xử lý chính sách báo lỗi theo ứng dụng.

### 12.5. Phân tích `annotation=String:Double:HIGH`

`@Rule` chứa các element:

- `Class<?> type()`: lưu `String.class`.
- `Class<? extends Number> numberType()`: lưu `Double.class`.
- `Level level()`: lưu `Level.HIGH`.
- `String[] tags()`: lưu mảng chuỗi.

Các element này **hợp lệ** dù annotation interface không generic. `@Retention(RUNTIME)` cho phép Reflection đọc annotation từ class `Example`. Nếu bỏ retention runtime, `getAnnotation` có thể không thấy annotation trong chương trình chạy mặc dù annotation hợp lệ ở source.

### 12.6. `tags=[core, generics]` đến từ đâu?

`rule.tags()` trả một array `String[]`. `List.of(rule.tags())` tạo một danh sách chứa các phần tử chuỗi đó theo overload varargs phù hợp. Output đã được kiểm chứng bằng chương trình thực.

Không có `List<String>` nào được sử dụng làm **kiểu trả về của annotation element**: đó là `String[]`, một kiểu được phép. Việc chuyển mảng sang List diễn ra **sau khi đọc annotation**, trong Java code thông thường.

## 13. Ví dụ cố ý không biên dịch: enum generic

Tệp độc lập **`GenericEnum.java`**:

```java
enum GenericEnum<T> {
    A;
}
```

Biên dịch:

```bash
javac --release 17 GenericEnum.java
```

Compiler trả:

```text
error: enums cannot be generic
```

Đừng “sửa” bằng cách đổi thành:

```java
// Vẫn sai:
// enum GenericEnum<T extends Number> { A; }
```

Bound không thay đổi quy tắc: enum declaration không khai báo type parameters.

Nếu ứng dụng muốn một đối tượng chứa giá trị generic đồng thời có một nhãn enum cố định, hãy tách nhãn và payload:

```java
enum Kind {
    TEXT, NUMBER
}

record TaggedValue<T>(Kind kind, T value) {
}
```

Ví dụ:

```java
TaggedValue<String> text =
        new TaggedValue<>(Kind.TEXT, "hello");
```

`TaggedValue<T>` là generic record, còn `Kind` vẫn là enum không generic. Lưu ý mô hình này **chưa tự bảo đảm** `Kind.TEXT` luôn đi với `String`, vì caller có thể tạo `new TaggedValue<Integer>(Kind.TEXT, 7)`. Nếu cần invariant gắn loại nhãn với kiểu payload, thiết kế validator hoặc các subtype/constructors cụ thể để compiler hay runtime bảo vệ quy tắc đó.

## 14. Ví dụ cố ý không biên dịch: annotation generic

Tệp **`GenericAnnotation.java`**:

```java
@interface GenericAnnotation<T> {
    T value();
}
```

Lệnh:

```bash
javac --release 17 GenericAnnotation.java
```

`javac` báo lỗi chính:

```text
error: annotation interface GenericAnnotation cannot be generic
```

Và lỗi tại kiểu element:

```text
error: invalid type for annotation interface element
```

Việc đổi return thành `String` vẫn không làm `<T>` trên `@interface` hợp lệ. Cần bỏ type parameter của annotation declaration:

```java
@interface ValidAnnotation {
    String value();
}
```

Nếu muốn metadata mô tả class được chọn, dùng element `Class<?>` hoặc bound thích hợp thay vì generic type parameter ở cấp annotation.

## 15. Ví dụ cố ý không biên dịch: element `List<String>`

Tệp **`ListElement.java`**:

```java
import java.util.List;

@interface ListElement {
    List<String> value();
}
```

Lệnh:

```bash
javac --release 17 ListElement.java
```

Compiler trả:

```text
error: invalid type for annotation interface element
```

`List<String>` là một kiểu Java hoàn toàn hợp lệ khi dùng cho biến, field hoặc return type của method thông thường. Nhưng nó **không nằm trong tập kiểu return được phép của annotation element**.

Nếu cần nhiều chuỗi, dùng mảng:

```java
@interface Tags {
    String[] value();
}

@Tags({"java", "generics"})
class Article {
}
```

Nếu cần nhiều metadata phức tạp, dùng mảng annotation lồng nhau. Nếu cần dữ liệu runtime động với collection semantics, dùng một config object hoặc registry riêng — annotation không phải nơi lưu đối tượng tùy ý.

## 16. Ví dụ cố ý không biên dịch: method generic trong annotation

Tệp **`GenericAnnotationMethod.java`**:

```java
@interface GenericAnnotationMethod {
    <T> T value();
}
```

Biên dịch:

```bash
javac --release 17 GenericAnnotationMethod.java
```

Một diagnostic quan trọng:

```text
error: elements in annotation interface declarations
cannot be generic methods
```

Compiler còn có thể cảnh báo kiểu kết quả `T` không hợp lệ cho annotation element. Điều cần sửa là **thiết kế kiểu element**, không phải thêm bound.

Nếu element chỉ cần biểu diễn một class:

```java
@interface ClassHint {
    Class<?> value();
}
```

Nếu nghiệp vụ cần một generic method xử lý dữ liệu, viết method đó trong class/interface/service bình thường, có thể đọc metadata annotation làm input.

## 17. Ví dụ cố ý không biên dịch: mảng nhiều chiều hoặc `Object` element

Annotation element không chấp nhận một kiểu return tùy ý chỉ vì compiler hiểu kiểu đó ở Java thông thường.

Tệp **`InvalidArrayElement.java`**:

```java
@interface InvalidArrayElement {
    String[][] value();
}
```

Compiler trả:

```text
error: invalid type for annotation interface element
```

Tương tự:

```java
@interface InvalidObjectElement {
    Object value();
}
```

cũng sai. Phải chọn primitive, `String`, `Class`/parameterized invocation của `Class`, enum, annotation hoặc **mảng một chiều** của những loại đó.

### 17.1. Vì sao `Class<?>[]` lại hợp lệ?

Ví dụ:

```java
@interface Types {
    Class<?>[] value();
}
```

Đây là **mảng một chiều** của một `Class<?>` element hợp lệ. Không mâu thuẫn với việc `String[][]` bị cấm: `String[][]` là hai chiều.

Một trường hợp khác đã được biên dịch thành công với Java 17:

```java
@interface Pick {
    Class<String> exact() default String.class;

    Class<? extends Number>[] types()
            default {Integer.class, Double.class};
}
```

`Class<String>` và `Class<? extends Number>[]` đều hợp lệ; các class literals ở default value phải có quan hệ kiểu phù hợp.

## 18. Annotation có thể xuất hiện trên generic declarations và type arguments

Một annotation **không cần generic** để đánh dấu chỗ khai báo type parameter hoặc type argument. Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target({
    ElementType.TYPE_USE,
    ElementType.TYPE_PARAMETER
})
@interface TypeMarker {
}

class AnnotatedGeneric<@TypeMarker T> {
    List<@TypeMarker String> names;
    @TypeMarker T value;
}
```

Đoạn này đã được biên dịch bằng `javac --release 17 -Xlint:all` mà không có lỗi hoặc warning.

Điểm cần phân biệt:

- `TypeMarker` là annotation interface không khai báo `<T>`.
- `AnnotatedGeneric<T>` là một **generic class bình thường**.
- Annotation được **gắn lên type parameter hoặc type use** vì `@Target` cho phép.
- `List<@TypeMarker String>` có một **type annotation** trên chỗ dùng kiểu `String`; nó không làm `TypeMarker` trở thành generic.

### 18.1. `TYPE_PARAMETER` và `TYPE_USE` khác nhau

`ElementType.TYPE_PARAMETER` dành cho chỗ **khai báo** một type parameter, ví dụ `<@Marker T>`.

`ElementType.TYPE_USE` dành cho các vị trí dùng type trong ngữ cảnh ngôn ngữ cho phép, ví dụ `List<@Marker String>` hoặc một chỗ khai báo có kiểu phù hợp.

Một annotation chỉ có `@Target(TYPE)` có thể dùng cho class/interface declaration, nhưng không mặc nhiên dùng ở mọi type argument. Nếu mục tiêu là static analysis hoặc nullness/type checking trên Generics, hãy thiết kế `@Target` chính xác.

### 18.2. Không nhầm type-use annotation với annotation có tham số kiểu

`@TypeMarker` được gắn **trên** `String` trong `List<@TypeMarker String>`, nhưng bản thân `@TypeMarker` vẫn là metadata annotation với các element theo luật riêng. Bạn không thể viết `@TypeMarker<String>` để “tham số hóa annotation”.

Nhiều công cụ như annotation processors hoặc type checkers có thể sử dụng type-use annotations để thực thi quy tắc tĩnh. Điều đó **không** làm Java runtime tự kiểm tra generic type arguments vốn bị erase.

## 19. Cách tổ chức mô hình khi cần “enum mang kiểu dữ liệu”

Một bài toán phổ biến là định nghĩa danh sách các loại dữ liệu:

```java
enum DataKind {
    TEXT, NUMBER
}
```

và muốn mỗi loại “mang” một kiểu kết quả khác nhau. Không thể giải quyết bằng:

```java
// Không hợp lệ:
// enum DataKind<T> { TEXT, NUMBER }
```

Một số thiết kế phù hợp hơn:

### 19.1. Enum làm nhãn, generic record làm payload

```java
enum DataKind {
    TEXT, NUMBER
}

record Value<T>(DataKind kind, T payload) {
}
```

Ưu điểm là giữ được một enum hữu hạn để hiển thị/lưu nhãn, trong khi `Value<T>` có generic contract cho payload.

Giới hạn: quan hệ giữa `DataKind.TEXT` và `T=String` cần invariant bổ sung nếu ứng dụng đòi nó. Không coi `Value<Integer>(TEXT, 123)` mặc nhiên là lỗi compiler.

### 19.2. Interface generic với implementations cụ thể

```java
interface TypedKey<T> {
    T read(String source);
}

final class StringKey implements TypedKey<String> {
    @Override
    public String read(String source) {
        return source;
    }
}

final class IntKey implements TypedKey<Integer> {
    @Override
    public Integer read(String source) {
        return Integer.valueOf(source);
    }
}
```

Nếu mỗi loại thực sự có generic behavior riêng, các implementation như vậy cho phép compiler gắn kiểu kết quả với instance type. Bạn có thể tổ chức registry của chúng trong collection hoặc enum labels khi cần.

### 19.3. Dùng enum triển khai một generic interface cố định

Nếu mọi constant trả cùng một kiểu và chỉ khác logic:

```java
interface Rule<T> {
    T apply(String input);
}

enum TextRule implements Rule<String> {
    UPPER {
        @Override
        public String apply(String input) {
            return input.toUpperCase();
        }
    },
    LOWER {
        @Override
        public String apply(String input) {
            return input.toLowerCase();
        }
    };
}
```

Đây là cách dùng enum đúng mục đích: tập constant cố định, cùng một kiểu giao diện `Rule<String>`, có hành vi đa hình. Nó **không** làm enum generic.

## 20. Cách tổ chức metadata khi cần “annotation mang một kiểu”

Một bài toán khác là muốn đánh dấu class được xử lý cùng kiểu dữ liệu:

```java
@interface Handles {
    Class<?> type();
}
```

Cách dùng:

```java
@Handles(type = String.class)
class StringHandler {
}
```

Annotation này chứa một class token, không phải một `T` được suy luận cho handler.

Nếu cần giới hạn lựa chọn:

```java
@interface HandlesNumber {
    Class<? extends Number> type();
}
```

Compiler có thể kiểm tra class literal theo bound. Tuy nhiên annotation không kiểm tra rằng implementation class `StringHandler` thật sự có method handle nhận đúng kiểu tương ứng.

Để gắn chặt metadata với behavior, có thể kết hợp:

- Generic interface `Handler<T>` cho compile-time contract.
- Annotation `@Handles(type = ...)` cho đăng ký/phát hiện.
- Validation tại startup hoặc annotation processor để kiểm tra các mối quan hệ mà Java type system không tự gắn giữa annotation element và generic argument.

Không nên hứa rằng gắn annotation sẽ tự động reify toàn bộ generic type của class instance.

## 21. Đọc Annotation bằng Reflection đúng cách

Một annotation có `@Retention(RetentionPolicy.RUNTIME)` mới được Reflection truy xuất tại runtime theo cơ chế annotation runtime thông thường.

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}
```

```java
@Label("hello")
class Example {
}
```

Một method sử dụng Reflection:

```java
Label label = Example.class.getAnnotation(Label.class);
```

Nếu annotation có mặt và retention cho phép, `label.value()` trả `"hello"`.

Với ví dụ hoàn chỉnh ở mục 12, `Rule` có `@Retention(RUNTIME)`, vì thế:

```java
Rule rule = Example.class.getAnnotation(Rule.class);
```

đọc được các element `type`, `numberType`, `level`, `tags`.

### 21.1. Retention là vấn đề khác Generics

`SOURCE`, `CLASS`, `RUNTIME` quy định annotation được lưu/đọc ở mức nào; chúng không quyết định annotation được phép generic hay không. Kể cả annotation retention runtime, khai báo `@interface Info<T>` vẫn không hợp lệ.

### 21.2. Annotation metadata không phải đối tượng config tự do

Các method element của annotation trả những loại giá trị được phép theo JLS, không phải arbitrary object graph. Nếu bạn cần danh sách runtime thay đổi liên tục hoặc dữ liệu nested phức tạp, nên có config class/record và parser/validator riêng. Annotation phù hợp để mô tả metadata hữu hạn, đọc được bằng compiler hoặc Reflection.

## 22. Checklist phân tích lỗi biên dịch

Khi gặp compiler error liên quan enum, annotation và Generics:

1. **Tìm chính xác vị trí `<T>`**: nằm ngay sau tên `enum`/`@interface`, hay ở method/class/interface khác?
2. Nếu là `enum Name<T>`, đây là **lỗi cấu trúc khai báo**; đổi sang enum không generic và triển khai generic interface/method hoặc tách generic holder.
3. Nếu là `@interface Name<T>`, bỏ type parameters khỏi annotation declaration; xác định metadata thực sự cần trả dưới dạng element được phép.
4. Nếu annotation element là `<T> T value()` hoặc `List<String> value()`, đó là **kiểu/method element không hợp lệ**, không phải vấn đề erasure có thể sửa bằng cast.
5. Với annotation muốn mô tả class, cân nhắc `Class<?>` hoặc `Class<? extends Base>`; nếu cần nhiều class, dùng mảng một chiều.
6. Nếu annotation muốn chứa dữ liệu phức tạp, thử enum, annotation lồng nhau hoặc một-dimensional array của kiểu được hỗ trợ; nếu không phù hợp, chuyển logic sang config object.
7. Với enum implement generic interface, xác nhận type argument và implementation method thực sự khớp hợp đồng.
8. Với generic helper làm việc trên enum, ưu tiên `<E extends Enum<E>>` kết hợp `Class<E>` theo API sử dụng.
9. Nếu dùng Reflection để đọc annotation, xác nhận `@Retention(RUNTIME)` và vị trí target thích hợp.
10. Biên dịch lại với `javac --release 17 -Xlint:all` và viết test cả khai báo hợp lệ lẫn những trường hợp cần bị từ chối.

### 22.1. Bảng nguyên nhân và cách khắc phục

| Thông báo | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `enums cannot be generic` | Đặt type parameter sau tên enum. | Bỏ `<T>`; dùng generic class/interface/method quanh enum. |
| `annotation interface ... cannot be generic` | Khai báo `@interface A<T>`. | Bỏ `<T>`; dùng element hợp lệ để mô tả metadata. |
| `elements in annotation interface declarations cannot be generic methods` | Element khai báo `<T>` riêng. | Dùng kiểu element cố định; chuyển xử lý generic sang class/service. |
| `invalid type for annotation interface element` | Return type là `Object`, `List<String>`, `String[][]`, v.v. | Dùng primitive, `String`, `Class`, enum, annotation hoặc array một chiều hợp lệ. |
| Enum `implements Codec<Integer>` báo thiếu method | Chưa override đúng chữ ký generic của interface. | Viết implementation đúng kiểu sau khi thay `T = Integer`. |
| Reflection trả `null` khi đọc annotation | Annotation không hiện diện hoặc retention không cho truy xuất runtime. | Kiểm tra khai báo, `@Retention`, `@Target` và nơi gắn. |
| Muốn mỗi enum constant có type argument khác nhau | Enum declaration không generic, constants dùng chung enum type. | Chuyển sang typed hierarchy/descriptors hoặc chia các enum với hợp đồng cố định. |

## 23. Các ngộ nhận thường gặp

**Ngộ nhận 1 — “Enum không generic nên không được dùng `List<String>` trong enum.”** Sai. Enum không khai báo type parameters, nhưng field, parameter và return type bên trong nó vẫn có thể là parameterized types.

**Ngộ nhận 2 — “`Enum<E>` trong JDK chứng minh có thể khai báo `enum X<T>`.”** Sai. `Enum<E>` là generic superclass đặc biệt của enum, không phải cú pháp generic enum declaration.

**Ngộ nhận 3 — “Enum không generic nên không được có `<T> T method(T)`.”** Sai. Method có type parameter riêng và được phép trong enum.

**Ngộ nhận 4 — “Enum triển khai `Codec<Integer>` thì enum trở thành `Enum<Integer>`.”** Sai. Parameterized type ở đây là **interface** được triển khai, không phải type parameter của enum.

**Ngộ nhận 5 — “Annotation không generic nên element không thể dùng `Class<?>`.”** Sai. `Class<?>`, `Class<? extends Number>` và nhiều dạng invocation hợp lệ của `Class` được annotation hỗ trợ.

**Ngộ nhận 6 — “Một element `List<String>` cũng hợp lệ vì `List<String>` là Java type hợp lệ.”** Sai. Annotation element types bị giới hạn chặt hơn return type của method thông thường.

**Ngộ nhận 7 — “`String[][]` chỉ là array nên làm annotation element được.”** Sai. Annotation chỉ hỗ trợ một-dimensional array của kiểu element hợp lệ.

**Ngộ nhận 8 — “Annotation có thể khai báo method generic vì nó là interface.”** Sai. Các element declarations của annotation interface không được generic methods.

**Ngộ nhận 9 — “`@TypeMarker` gắn vào `List<@TypeMarker String>` nghĩa là `TypeMarker` có tham số kiểu.”** Sai. Annotation đang được **áp dụng tại type use**, không phải được khai báo generic.

**Ngộ nhận 10 — “Chỉ cần annotation có `Class<? extends Foo>` là framework tự xác minh mọi generic behavior.”** Sai. Annotation metadata chỉ mô tả một class token hoặc giá trị cố định; quan hệ giữa metadata và implementation cần được kiểm tra riêng.

**Ngộ nhận 11 — “`@Retention(RUNTIME)` sửa được giới hạn generic annotation.”** Sai. Retention chỉ quyết định visibility của annotation ở runtime, không cho thêm type parameters vào `@interface`.

**Ngộ nhận 12 — “Mọi constant của một enum có thể độc lập chọn type argument cho cùng enum generic.”** Sai. Enum không generic; các constants cùng thuộc một enum type, còn việc có class body riêng không tạo specialization theo `T`.

## 24. Bài thực hành

### Bài 1 — Phân loại khai báo

Xét:

```java
enum Mode<T> {
    A;
}

interface Provider<T> {
    T get();
}

enum DefaultMode implements Provider<String> {
    A;

    public String get() {
        return "ok";
    }
}
```

Dòng khai báo nào hợp lệ?

<details>
<summary>Đáp án</summary>

`enum Mode<T>` không hợp lệ vì enum không được khai báo type parameters. `Provider<T>` là generic interface hợp lệ. `DefaultMode implements Provider<String>` hợp lệ vì enum không generic nhưng được phép implement một parameterized interface và override method trả `String`.

</details>

### Bài 2 — Generic method trong enum

Có thể thêm method này trong một enum không generic không?

```java
<T> T identity(T value) {
    return value;
}
```

<details>
<summary>Đáp án</summary>

Có. `<T>` thuộc khai báo generic method, không thuộc khai báo enum. Java cho phép enum có generic methods theo những quy tắc method thông thường.

</details>

### Bài 3 — Kiểu trả về annotation element

Những kiểu nào hợp lệ: `String`, `Object`, `List<String>`, `Class<?>`, `Class<? extends Number>`, `String[]`, `String[][]`?

<details>
<summary>Đáp án</summary>

Hợp lệ: `String`, `Class<?>`, `Class<? extends Number>`, `String[]`. Không hợp lệ: `Object`, `List<String>`, `String[][]`. Annotation element chỉ chấp nhận những nhóm kiểu được ngôn ngữ quy định; mảng chỉ một chiều.

</details>

### Bài 4 — Annotation có method generic?

```java
@interface Pick {
    <T> T get();
}
```

Vì sao bị compiler từ chối?

<details>
<summary>Đáp án</summary>

Annotation element declarations không được generic methods. Việc annotation là một dạng interface không khiến method element có cùng quyền tự do khai báo type parameters như method của class/interface thông thường. Cần chọn một element type hợp lệ hoặc chuyển logic generic sang method ở một class khác.

</details>

### Bài 5 — Vì sao có thể dùng `EnumSet<Level>`?

<details>
<summary>Đáp án</summary>

`EnumSet` là một **generic collection class** của Java. Type argument `Level` là một enum type cụ thể, nhưng chính enum `Level` không khai báo `<T>`. Không có mâu thuẫn với quy tắc enum không generic.

</details>

### Bài 6 — Gắn annotation lên type argument có làm annotation generic không?

```java
List<@TypeMarker String> names;
```

<details>
<summary>Đáp án</summary>

Không. `TypeMarker` được sử dụng tại vị trí TYPE_USE nếu khai báo `@Target` cho phép. Nó không tự có type parameter. Generic type ở đây là `List<String>`; annotation chỉ mô tả metadata trên chỗ dùng type `String`.

</details>

### Bài 7 — Lựa chọn thiết kế cho enum trả dữ liệu nhiều kiểu

Ứng dụng có nhãn `TEXT`, `NUMBER` nhưng mỗi nhãn cần một loại payload riêng. Có nên viết `enum Item<T>` không?

<details>
<summary>Đáp án</summary>

Không thể viết generic enum declaration đó trong Java. Có thể dùng enum làm nhãn kết hợp generic record/class cho payload; nếu cần compiler bắt buộc nhãn nào đi với loại payload nào, cân nhắc typed descriptor hoặc các implementations cụ thể qua generic interface, bổ sung invariant phù hợp.

</details>

### Bài 8 — Annotation có thể lưu danh sách chuỗi?

Nếu muốn metadata chứa ba nhãn `"a"`, `"b"`, `"c"`, hãy định nghĩa element như thế nào?

<details>
<summary>Đáp án</summary>

Dùng `String[] value()`:

```java
@interface Tags {
    String[] value();
}

@Tags({"a", "b", "c"})
class Tagged {
}
```

Không dùng `List<String> value()`, vì `List<String>` không phải annotation element type hợp lệ.

</details>

## 25. Ghi nhớ trọng tâm

**Java cấm khai báo type parameters trực tiếp trên `enum` và `@interface`**, nhưng phạm vi cấm khác nhau:

- Enum không được viết `enum E<T>`, **vẫn có thể** implement `GenericInterface<Concrete>`, có generic methods, dùng generic fields và kết hợp với generic collections như `EnumSet<E>`, `EnumMap<E,V>`.
- Annotation không được viết `@interface A<T>`, và các **annotation element methods cũng không được generic**. Kiểu trả về element chỉ nằm trong tập mà Java quy định: primitive, `String`, `Class` (kể cả invocation hợp lệ của `Class`), enum, annotation và mảng một chiều của chúng.
- Annotation vẫn có thể được **gắn tại generic type declarations/usages** thông qua `TYPE_PARAMETER`, `TYPE_USE` mà không trở thành generic annotation.

Khi gặp nhu cầu “enum có tham số kiểu”, hãy hỏi liệu generic contract nên thuộc **interface**, **method** hay **object chứa enum**. Khi gặp nhu cầu “annotation generic”, hãy hỏi liệu metadata có thể được biểu diễn bằng **Class token, enum, array hoặc nested annotation** hay cần chuyển sang một config object và generic service. Cách chia trách nhiệm này giữ được type safety mà không cố dùng những khai báo Java không hỗ trợ.