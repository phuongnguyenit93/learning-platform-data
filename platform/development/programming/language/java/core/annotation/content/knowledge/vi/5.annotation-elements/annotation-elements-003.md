# Giá trị enum và annotation lồng nhau trong Java

## 1. Bối cảnh: annotation có phần tử và giá trị

Trong Java, một annotation không chỉ có dạng đánh dấu như `@Override`. Nó còn có thể **chứa nhiều phần tử (annotation elements)** để lưu metadata có cấu trúc. Mỗi phần tử được khai báo giống một phương thức không tham số bên trong `@interface`, và giá trị của phần tử được cung cấp khi sử dụng annotation:

```java
@interface Example {
    String name();
    int version() default 1;
}

@Example(name = "sample", version = 2)
class Demo {}
```

`name()` là phần tử bắt buộc vì không có giá trị mặc định. `version()` có `default 1` nên có thể bỏ qua khi dùng annotation. Đây là cú pháp khai báo phần tử của annotation; khi dùng reflection, Java trả về giá trị qua các phương thức tương ứng như `annotation.name()` và `annotation.version()`.

Bài này tập trung vào hai kiểu giá trị giàu ý nghĩa:

- **Giá trị enum:** giới hạn một lựa chọn vào các hằng được định nghĩa trong một enum, ví dụ `Priority.HIGH`.
- **Giá trị annotation lồng nhau:** sử dụng một annotation làm giá trị của phần tử thuộc một annotation khác, ví dụ `@Schedule(window = @Window(start = 8, end = 17))`. Có thể dùng **mảng annotation** để khai báo nhiều cấu hình con.

Đây là **metadata có kiểu tĩnh do Java kiểm tra**, không phải một đối tượng tùy ý hoặc lệnh tự động kích hoạt nghiệp vụ.

## 2. Kiểu dữ liệu hợp lệ của phần tử annotation

Java chỉ cho phép phần tử của annotation có các kiểu sau:

| Nhóm | Ví dụ khai báo bên trong `@interface` | Giá trị hợp lệ khi sử dụng |
| --- | --- | --- |
| Kiểu nguyên thủy | `int retries();`, `boolean enabled();` | `retries = 3`, `enabled = true` |
| `String` | `String label();` | `label = "report"` |
| `Class` hoặc `Class<?>` với kiểu phù hợp | `Class<?> handler();` | `handler = String.class` |
| Kiểu `enum` | `Priority priority();` | `priority = Priority.HIGH` |
| Kiểu annotation | `Window window();` | `window = @Window(start = 8, end = 17)` |
| Mảng một chiều của kiểu hợp lệ | `Priority[] priorities();`, `Rule[] rules();` | `priorities = {Priority.HIGH, Priority.LOW}` |

Các kiểu `Integer`, `List<String>`, `Map`, class nghiệp vụ tùy ý, mảng hai chiều và kiểu trả về `void` **không hợp lệ** làm kiểu phần tử annotation. Không được khai báo phần tử có tham số hoặc `throws` clause. Giá trị annotation cũng **không được là `null`**.

Các quy tắc này giải thích vì sao enum và annotation lồng nhau rất hữu ích: chúng giúp mô tả lựa chọn cố định hoặc cấu trúc có nhiều trường ngay trong giới hạn kiểu dữ liệu của Java.

## 3. Giá trị enum trong annotation

### 3.1. Khai báo kiểu enum và phần tử sử dụng enum

```java
enum Priority {
    LOW, NORMAL, HIGH
}

@interface Task {
    Priority priority() default Priority.NORMAL;
}

@Task(priority = Priority.HIGH)
class UrgentTask {}

@Task
class OrdinaryTask {}
```

Trong ví dụ:

- `Priority` là enum xác định ba lựa chọn cố định. Compiler biết chính xác các giá trị được phép.
- `priority()` là phần tử annotation **có kiểu trả về `Priority`**; `default Priority.NORMAL` được dùng nếu không cung cấp giá trị khi ghi `@Task`.
- `@Task(priority = Priority.HIGH)` chỉ định giá trị trực tiếp từ hằng enum; `@Task` sử dụng giá trị mặc định.
- `@Task(priority = Priority.CRITICAL)` sẽ lỗi biên dịch vì enum chưa có hằng `CRITICAL`.

Khi gán giá trị cho một phần tử annotation có kiểu enum, Java yêu cầu **tên hằng enum** được phép theo ngữ cảnh của biểu thức annotation. Một biến `Priority` giữ giá trị `Priority.HIGH` không trở thành biểu thức hợp lệ để thay thế hằng enum trong annotation.

Ví dụ không hợp lệ:

```java
// Mã minh họa lỗi; không biên dịch độc lập.
class InvalidTask {
    static final Priority SELECTED = Priority.HIGH;

    @Task(priority = SELECTED) // LỖI: cần một enum constant hợp lệ.
    void run() {}
}
```

Dù `SELECTED` là `static final`, đây vẫn là **biến** chứa giá trị enum, không phải cách viết một enum constant trong annotation. Viết trực tiếp `Priority.HIGH`.

### 3.2. Vì sao enum tốt hơn chuỗi tự do?

So sánh:

```java
@interface TextTask {
    String priority();
}

@TextTask(priority = "HGIH") // Compiler chấp nhận chuỗi này.
class TypoTask {}
```

`"HGIH"` là chuỗi hợp lệ dù ý định có thể là `"HIGH"`. Với `Priority.HIGH`, IDE có thể gợi ý giá trị, compiler từ chối tên hằng sai và các công cụ refactor có thể cập nhật tham chiếu enum nhất quán hơn.

Dùng enum khi số lựa chọn được kiểm soát bởi mã nguồn và cần an toàn kiểu. Nếu cấu hình bắt buộc thay đổi tùy ý ngoài lúc build/deploy, việc chọn enum cần cân nhắc vì thêm hằng mới vẫn là thay đổi source của enum và thường cần build lại.

### 3.3. Mảng enum

Một phần tử cũng có thể nhận mảng enum:

```java
@interface AllowPriorities {
    Priority[] value();
}

@AllowPriorities({Priority.LOW, Priority.HIGH})
class SupportedTasks {}
```

`value()` là tên phần tử đặc biệt cho phép **cú pháp rút gọn** `@AllowPriorities({...})`; cách viết đầy đủ là `@AllowPriorities(value = {...})`. Mảng vẫn chứa các hằng của đúng kiểu enum, không phải các chuỗi.

## 4. Annotation làm giá trị của annotation khác

### 4.1. Định nghĩa cấu hình con

Giả sử một annotation tổng thể cần mô tả khoảng giá trị. Ta tạo một annotation chỉ biểu diễn khoảng, rồi dùng nó như một phần tử:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Range {
    int min() default 0;
    int max() default 100;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface CheckRange {
    Range range() default @Range;
}

class RangeService {
    @CheckRange(range = @Range(min = 1, max = 20))
    void check() {}
}
```

`range()` có **kiểu trả về là annotation `Range`**, nên khi gán phải dùng biểu thức annotation `@Range(...)`. `new Range(...)` là sai; annotation type không được khởi tạo bằng `new`.

`@Target({})` khai báo rằng `Range` không nhắm trực tiếp vào một phần tử chương trình thông thường; một cách sử dụng có giá trị của nó là annotation lồng trong giá trị annotation khác. Đây là kỹ thuật giúp tránh gắn nhầm `@Range` trực tiếp lên class hoặc method khi nó chỉ là cấu hình con. `@CheckRange` mới là annotation áp dụng cho METHOD.

Biểu thức `default @Range` tạo **giá trị mặc định** với `min = 0`, `max = 100`; nó hợp lệ bởi mọi phần tử của `Range` đều có default. Có thể viết rõ `default @Range(min = 0, max = 100)` nếu muốn.

### 4.2. Phân biệt hai nghĩa thường gặp của “annotation lồng nhau”

Cụm *annotation lồng nhau* có thể nói đến hai cấu trúc khác nhau:

**Trường hợp A — annotation-valued element**, trọng tâm bài này:

```java
@CheckRange(range = @Range(min = 1, max = 20))
void process() {}
```

`@Range(...)` nằm **trong giá trị phần tử `range`** của `@CheckRange`. Reflection có thể trả về một đối tượng thực thi giao diện annotation `Range` thông qua phương thức `checkRange.range()` khi annotation có retention phù hợp.

**Trường hợp B — khai báo một annotation type bên trong kiểu khác:**

```java
class Catalog {
    @interface Entry {
        String value();
    }
}

@Catalog.Entry("item")
class Item {}
```

Ở đây `Entry` là **kiểu annotation được khai báo lồng trong class `Catalog`**, được tham chiếu bằng `Catalog.Entry`. Nó không tự động là giá trị của một phần tử annotation khác. Hai khái niệm có thể kết hợp nhưng không đồng nghĩa.

### 4.3. Mảng các annotation lồng nhau

Một phần tử có kiểu `Rule[]` có thể nhận **nhiều annotation cùng loại** để tạo cấu hình con:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({})
@interface Rule {
    String name();
    boolean required() default true;
}

@interface RuleCollection {
    Rule[] rules();
}

@RuleCollection(rules = {
    @Rule(name = "email"),
    @Rule(name = "phone", required = false)
})
class ProfileDefinition {}
```

Mỗi phần tử trong `rules` có kiểu `Rule`. Cú pháp `{...}` tạo mảng giá trị annotation; nó **không giống** việc đặt hai annotation `@Rule` trực tiếp cạnh nhau trên cùng class.

Khi cần không có rule, có thể định nghĩa `Rule[] rules() default {};`, rồi dùng `@RuleCollection` mà không cần liệt kê mảng.

## 5. Ví dụ Java 17+ chạy độc lập: enum, annotation lồng nhau, mảng và default

Tạo file **NestedAnnotationValuesDemo.java** với toàn bộ nội dung sau. Chương trình chỉ dùng API Java SE, không yêu cầu thư viện ngoài.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

enum Level {
    LOW, NORMAL, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface RangeConfig {
    int min() default 0;
    int max() default 100;
}

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface CheckConfig {
    String name();
    Level level() default Level.NORMAL;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Monitor {
    Level level() default Level.NORMAL;
    RangeConfig range() default @RangeConfig;
    CheckConfig[] checks() default {};
}

public class NestedAnnotationValuesDemo {
    @Monitor(
        level = Level.HIGH,
        range = @RangeConfig(min = 2, max = 8),
        checks = {
            @CheckConfig(name = "format"),
            @CheckConfig(name = "access", level = Level.HIGH)
        }
    )
    void validate() {}

    @Monitor
    void fallback() {}

    static void printMetadata(String methodName)
            throws NoSuchMethodException {
        Method method = NestedAnnotationValuesDemo.class
                .getDeclaredMethod(methodName);
        Monitor monitor = method.getAnnotation(Monitor.class);

        System.out.println(methodName + ": level=" + monitor.level());
        System.out.println("range=" + monitor.range().min()
                + ".." + monitor.range().max());

        for (CheckConfig check : monitor.checks()) {
            System.out.println("check=" + check.name()
                    + "/" + check.level());
        }

        System.out.println("checks=" + monitor.checks().length);
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        printMetadata("validate");
        printMetadata("fallback");
    }
}
```

Biên dịch và chạy từ thư mục chứa file với JDK 17 trở lên:

```bash
javac NestedAnnotationValuesDemo.java
java NestedAnnotationValuesDemo
```

Stdout:

```text
validate: level=HIGH
range=2..8
check=format/NORMAL
check=access/HIGH
checks=2
fallback: level=NORMAL
range=0..100
checks=0
```

**Diễn giải theo thứ tự:**

1. `Level` là enum, nên `Monitor.level()` chỉ trả về hằng thuộc `Level`.
2. `RangeConfig` là annotation dùng làm **giá trị cấu hình lồng nhau** của `Monitor.range()`. Phương thức `monitor.range()` trả về `RangeConfig`, rồi `min()` và `max()` trả về các số nguyên.
3. `CheckConfig[]` là **mảng annotation**. `validate()` khai báo hai mục; mục `format` không chỉ định `level` nên dùng default `NORMAL`.
4. `fallback()` chỉ có `@Monitor`, nhưng vẫn nhận các giá trị mặc định: `Level.NORMAL`, `@RangeConfig` mặc định 0..100 và mảng `checks` rỗng.
5. Cả ba annotation tự định nghĩa đều có `@Retention(RUNTIME)` để minh họa khả năng đọc metadata lúc chạy; annotation `Monitor` được đặt trên METHOD, còn hai annotation con chỉ dùng như giá trị.
6. `getDeclaredMethod` tìm phương thức theo tên; `getAnnotation(Monitor.class)` đọc annotation trên đúng Method. Các lời gọi `monitor.level()`, `monitor.range()` và `monitor.checks()` truy xuất metadata có kiểu tĩnh.

Đoạn code **không tự kiểm tra giới hạn 2..8, không chạy check “format” và không thực thi check “access”**. Đó chỉ là metadata. Để tạo validation hoặc kiểm tra quyền, phải viết một thành phần đọc các giá trị và áp dụng logic tương ứng.

## 6. Giá trị mặc định, cú pháp rút gọn và cách Java kiểm tra

### 6.1. Phần tử có default và không có default

Một annotation có thể chứa cả phần tử bắt buộc và phần tử tùy chọn:

```java
@interface EndpointInfo {
    String path();                         // Bắt buộc
    Level level() default Level.NORMAL;   // Tùy chọn
    RangeConfig range() default @RangeConfig;
}
```

Khi dùng `@EndpointInfo(path = "/orders")`, hai phần tử còn lại lấy default; nếu viết `@EndpointInfo` mà không cấp `path`, compiler báo lỗi vì thiếu phần tử bắt buộc.

Giá trị mặc định được định nghĩa **trong annotation type**, không được hiểu là giá trị đã được sao chép vào từng chỗ sử dụng trong source. Khi đọc annotation thông qua API, các giá trị được trả về như thể đã được cung cấp đầy đủ, kể cả khi khai báo sử dụng đã bỏ qua phần tử có default. Thay đổi default trong annotation type có thể ảnh hưởng đến kết quả quan sát của annotation không chỉ định giá trị tường minh sau khi các thành phần được build/deploy tương thích.

### 6.2. `value()` và cú pháp viết ngắn

Nếu một annotation có phần tử tên `value`, có thể lược bỏ tên phần tử khi chỉ truyền vào `value`:

```java
@interface SelectLevel {
    Level value();
}

@SelectLevel(Level.HIGH)
class HighLevelType {}
```

Cách viết trên tương đương `@SelectLevel(value = Level.HIGH)`. Khi có thêm phần tử khác và cần chỉ định nhiều giá trị có tên, dùng dạng cặp `name = value` phù hợp. Sự rút gọn này cũng áp dụng khi `value()` có kiểu annotation hoặc mảng annotation.

### 6.3. Giá trị phải hợp lệ khi biên dịch

Trình biên dịch sẽ kiểm tra đúng kiểu và cú pháp biểu thức annotation. Ví dụ sau **không biên dịch độc lập**, mỗi dòng minh họa một lỗi riêng:

```java
// Lỗi minh họa — không đưa đồng thời vào chương trình chạy.
@Monitor(level = "HIGH")              // Sai: String thay vì Level.
@Monitor(level = null)                // Sai: annotation value không được null.
@Monitor(range = new RangeConfig())   // Sai: không khởi tạo annotation bằng new.
@Monitor(checks = {"format"})         // Sai: String[] thay vì CheckConfig[].
```

Với phần tử `int`, `String` hoặc các kiểu nguyên thủy khác, giá trị phải đáp ứng quy tắc **constant expression** áp dụng cho giá trị annotation. Với `enum`, biểu thức phải đáp ứng yêu cầu **enum constant**; với phần tử là annotation, giá trị phải có dạng **annotation**, ví dụ `@RangeConfig(min = 1)`. Không thể dùng một lời gọi phương thức lúc runtime làm giá trị annotation.

**Lưu ý nghiệp vụ:** `@RangeConfig(min = 10, max = 2)` vẫn có thể qua được kiểm tra cú pháp/kiểu của Java vì cả hai là `int` hợp lệ. Java không tự biết quy tắc “min phải nhỏ hơn hoặc bằng max”. Nếu cần ràng buộc này, annotation processor hoặc code xử lý metadata phải tự kiểm tra.

## 7. Đọc và xử lý giá trị enum/annotation lồng nhau bằng reflection

Trong ví dụ chạy được ở mục 5, `Monitor monitor = method.getAnnotation(Monitor.class)` cung cấp đối tượng biểu diễn annotation. Từ đó:

- `monitor.level()`: trả về `Level`, có thể `switch` theo các hằng enum để chọn nhánh xử lý.
- `monitor.range()`: trả về `RangeConfig`, rồi gọi `min()` và `max()`.
- `monitor.checks()`: trả về `CheckConfig[]`, duyệt từng phần tử và đọc `name()`, `level()`.

Bản thân phần tử annotation **không phải field có thể gán lại** trong đối tượng metadata. Không có `monitor.setLevel(...)`; các phương thức của kiểu annotation là các accessor chỉ đọc thông tin khai báo.

Khi reflection không thấy `@Monitor` trên phương thức, `getAnnotation(Monitor.class)` có thể trả về `null`; code thực tế phải kiểm tra trước khi truy cập. Trong ví dụ mục 5, cả hai phương thức đã được gắn `@Monitor`, nên phép truy cập là hợp lệ.

`@Retention(RUNTIME)` là điều kiện thường cần để đọc annotation bằng reflection. Các annotation có `SOURCE` hoặc `CLASS` retention không được đọc bằng `getAnnotation` theo cách đó, dù compiler hoặc công cụ build khác vẫn có thể sử dụng chúng.

Khi annotation có cấu trúc sâu (ví dụ `Monitor` chứa `RangeConfig` và danh sách `CheckConfig`), việc xử lý nghiệp vụ thường gồm hai giai đoạn:

1. **Đọc cấu hình**: lấy annotation gốc, enum, cấu hình con và mảng cấu hình con.
2. **Áp dụng quy tắc**: tự kiểm tra cấu hình hợp lệ, sau đó dùng nó trong validator, mapper, engine hay framework.

Giữ hai giai đoạn rõ ràng giúp tránh nhầm giữa **mô tả bằng metadata** và **thực thi một tính năng**.

## 8. Annotation lồng nhau khác gì @Repeatable?

Cùng xuất hiện nhiều annotation, nhưng cú pháp và mô hình dữ liệu khác nhau:

**Mảng annotation làm giá trị phần tử:**

```java
@Monitor(checks = {
    @CheckConfig(name = "first"),
    @CheckConfig(name = "second")
})
void work() {}
```

Ở đây **chỉ có một `@Monitor`** gắn lên `work()`; hai `@CheckConfig` là **giá trị của phần tử `checks`**. Vì thế `CheckConfig` không cần `@Repeatable`.

**Một loại annotation được áp dụng trực tiếp nhiều lần lên cùng khai báo:**

```java
// Ví dụ cú pháp khi một loại annotation đã được khai báo @Repeatable
@Tag("first")
@Tag("second")
void work() {}
```

Ở trường hợp này, `@Tag` là annotation đặt **trực tiếp hai lần** lên `work()`. Muốn cú pháp hợp lệ, `Tag` phải được thiết kế `@Repeatable` và có container tương thích.

Khi thiết kế:

- Cần một cấu hình cha chứa nhiều cấu hình con có mối quan hệ rõ ràng → cân nhắc phần tử có kiểu **mảng annotation** như `CheckConfig[] checks()`.
- Cần cho phép người dùng đặt cùng một annotation nhiều lần trực tiếp tại cùng target → cân nhắc **@Repeatable**.

Hai cơ chế có thể được dùng trong một thư viện, nhưng không thể coi chúng là một.

## 9. Lỗi thường gặp và cách sửa

**Lỗi 1 — Truyền chuỗi thay vì hằng enum.** Viết `level = "HIGH"` cho phần tử có kiểu `Level` sẽ lỗi biên dịch. Sửa thành `level = Level.HIGH` (hoặc biểu thức enum constant hợp lệ theo Java).

**Lỗi 2 — Truyền biến enum thay vì tên hằng enum.** Một biến `static final Level` vẫn không thay thế cú pháp enum constant yêu cầu trong annotation. Dùng trực tiếp tên hằng.

**Lỗi 3 — Dùng `new` cho annotation lồng nhau.** Annotation-valued element nhận giá trị dạng `@RangeConfig(...)`, không nhận `new RangeConfig(...)`.

**Lỗi 4 — Quên cấp phần tử bắt buộc.** Một phần tử như `String name();` không có default phải có mặt trong annotation được sử dụng. Nếu muốn tùy chọn, định nghĩa default hợp lệ.

**Lỗi 5 — Muốn bỏ qua phần tử bằng `null`.** Annotation elements không nhận null. Hãy thiết kế trạng thái vắng bằng giá trị mặc định rõ ràng, enum `UNSPECIFIED`, chuỗi rỗng hoặc mảng rỗng tùy hợp đồng API.

**Lỗi 6 — Dùng mảng nhiều chiều, collection hoặc object tùy ý.** `Rule[][]`, `List<Rule>` và kiểu class tùy ý không được phép làm kiểu phần tử annotation. Mảng annotation hợp lệ phải một chiều.

**Lỗi 7 — Nhầm mảng annotation với `@Repeatable`.** `checks = {@CheckConfig(...), ...}` là khai báo một giá trị mảng của `@Monitor`; nó không yêu cầu lặp `@CheckConfig` trực tiếp lên method.

**Lỗi 8 — Tưởng metadata tự kiểm tra nghiệp vụ.** Java kiểm tra kiểu nhưng không kiểm tra “min không vượt max” hoặc “các rule phải có tên duy nhất”. Cần code kiểm tra riêng.

**Lỗi 9 — Không phân biệt TARGET và RETENTION.** `@Target({})` giúp định vị annotation chỉ dùng làm giá trị con trong ví dụ; `@Retention(RUNTIME)` cho phép minh họa đọc metadata bằng reflection. Chúng quy định hai khía cạnh độc lập.

**Lỗi 10 — Gọi `getAnnotation` mà không kiểm tra null.** Nếu method không có annotation tương ứng, kết quả có thể là null, không được gọi `.level()` hay `.range()` ngay.

## 10. Bài tập tự luyện

1. Thêm `CRITICAL` vào enum `Level`, đổi `validate()` thành `level = Level.CRITICAL`, rồi dự đoán dòng stdout đầu tiên. Thử cố tình viết `level = "CRITICAL"` để quan sát lỗi kiểu.
2. Thêm `boolean inclusive() default true;` vào `RangeConfig`. Ghi `@RangeConfig(min = 1, max = 10, inclusive = false)` trong `validate()` rồi bổ sung một dòng in `inclusive`.
3. Thêm `@CheckConfig(name = "timeout", level = Level.LOW)` vào mảng `checks` và dự đoán toàn bộ các dòng `check=` và `checks=`.
4. Tạo phương thức thứ ba `void unspecified() {}` không có `@Monitor`. Sửa `printMetadata` để khi `getAnnotation` trả về `null` thì in thông báo phù hợp thay vì phát sinh `NullPointerException`.
5. Thử viết `@Monitor(range = @RangeConfig(min = 20, max = 2))`. Hãy giải thích vì sao đoạn này vẫn hợp lệ về mặt kiểu và đề xuất nơi nên thực hiện kiểm tra nghiệp vụ.

**Kết luận:** Phần tử annotation có thể nhận **enum constant**, **annotation khác** hoặc **mảng annotation một chiều** để biểu diễn cấu hình có kiểu rõ ràng. Enum tạo tập lựa chọn cố định; annotation lồng nhau nhóm các giá trị liên quan; default giúp bỏ qua cấu hình không cần thiết. Java kiểm tra cú pháp, kiểu và biểu thức hợp lệ ở compile time, còn logic nghiệp vụ phải do code hoặc công cụ đọc metadata đảm nhiệm.
