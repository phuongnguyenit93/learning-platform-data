# Các kiểu hợp lệ của phần tử annotation

## 1. Phần tử annotation là gì?

Trong khai báo một annotation, mỗi phương thức không tham số mô tả một phần tử dữ liệu:

```java
@interface Retry {
    int attempts() default 3;
    String reason();
}
```

Ở đây:

- `attempts` là phần tử có kiểu `int`, có giá trị mặc định `3`.
- `reason` là phần tử có kiểu `String`, cần được cung cấp khi dùng annotation.
- Cách dùng có thể là `@Retry(reason = "temporary failure")`.

Mặc dù cú pháp trông giống phương thức, đây không phải nơi khai báo hàm tùy ý để tính giá trị cấu hình. Java giới hạn kiểu phần tử và cách viết giá trị để annotation biểu diễn được siêu dữ liệu có cấu trúc.

Cần tách hai câu hỏi:

1. **Kiểu khai báo có hợp lệ không?** Ví dụ `String[]` hợp lệ, `List<String>` không hợp lệ.
2. **Giá trị gán có hợp lệ không?** Kiểu `String` hợp lệ, nhưng `new String("x")` không được dùng làm giá trị annotation.

Các quy tắc trong bài vẫn áp dụng cho Java hiện đại; ví dụ chạy được trên Java 17+.

## 2. Những nhóm kiểu được phép

| Nhóm kiểu | Ví dụ khai báo phần tử | Ví dụ giá trị |
| --- | --- | --- |
| Kiểu nguyên thủy | `int count();`, `boolean enabled();` | `3`, `true` |
| String | `String name();` | `"orders"` |
| Class hoặc dạng tham số hóa của Class | `Class<?> type();` | `String.class` |
| Enum | `Mode mode();` | `Mode.SAFE` |
| Kiểu annotation khác | `Owner owner();` | `@Owner("team-a")` |
| Mảng một chiều có phần tử thuộc các nhóm trên | `String[] tags();`, `Mode[] modes();` | `{"io", "batch"}`, `{Mode.SAFE}` |

Nhóm nguyên thủy bao gồm đủ tám kiểu: `byte`, `short`, `int`, `long`, `char`, `float`, `double`, `boolean`. `void` không phải kiểu phần tử hợp lệ.

Mảng có thể chứa kiểu nguyên thủy, chuỗi, class literal, hằng enum hoặc annotation, nhưng chỉ một chiều. Ví dụ `int[]`, `Class<?>[]`, `Owner[]` đều hợp lệ; `int[][]` không hợp lệ.

Các tên `Mode` và `Owner` trong bảng là kiểu do người viết định nghĩa; chúng phải lần lượt là enum và annotation, không phải lớp thông thường có tên tương tự.

## 3. Những kiểu không được phép

Các dòng sau minh họa khai báo sai, không đặt vào chương trình chạy:

```java
@interface InvalidElements {
    // Integer boxedCount();
    // Object data();
    // java.util.List<String> tags();
    // java.time.Duration timeout();
    // Runnable action();
    // int[][] matrix();
    // void nothing();
}
```

Lý do:

- Kiểu bao như `Integer` và `Boolean` không thay thế được kiểu nguyên thủy trong khai báo phần tử.
- `Object` không được dùng như một chỗ chứa dữ liệu bất kỳ.
- Collection, record, lớp miền nghiệp vụ hay interface thông thường không thuộc danh sách kiểu được phép.
- Mảng nhiều chiều không hợp lệ.
- `void` không biểu diễn một giá trị phần tử.

Nếu muốn annotation chỉ định một lớp xử lý, dùng `Class` thay vì chứa trực tiếp đối tượng xử lý:

```java
@interface UseHandler {
    Class<? extends Runnable> value();
}
```

Khi dùng `@UseHandler(MyTask.class)`, annotation lưu thông tin về kiểu. Nó không tự khởi tạo `MyTask`, không chạy phương thức `run()` và không bảo đảm lớp đó có constructor phù hợp. Đoạn mã hoặc framework đọc annotation chịu trách nhiệm diễn giải thông tin này.

## 4. Kiểu hợp lệ vẫn cần giá trị đúng quy tắc

### 4.1. Nguyên thủy và String cần biểu thức hằng

Ví dụ minh họa các giá trị hợp lệ:

```java
@interface Label {
    int priority();
    String value();
}

@Label(priority = 1 + 2, value = "batch" + "-job")
class BatchJob {
}
```

Các phép tính hằng này có thể được xác định khi biên dịch.

Một biến hằng có kiểu nguyên thủy hoặc String, được khai báo `final` và khởi tạo bằng biểu thức hằng, cũng có thể cung cấp giá trị. Ví dụ:

```java
class Labels {
    static final String NAME = "batch";
    static final int PRIORITY = 3;
}

@Label(priority = Labels.PRIORITY, value = Labels.NAME)
class AnotherJob {
}
```

Chỉ có `static final` chưa đủ. Nếu khởi tạo bằng lời gọi phương thức thì không phải biểu thức hằng cho mục đích này:

```java
class RuntimeLabels {
    static final String NAME = System.getProperty("job.name", "batch");
}

// Không hợp lệ:
// @Label(priority = 3, value = RuntimeLabels.NAME)
```

Tương tự, không dùng `new String("batch")` hoặc một lời gọi hàm tính tên làm giá trị annotation. Với kiểu số, còn phải tuân theo quy tắc tương thích và phạm vi giá trị; không phải hằng số nào cũng gán được cho mọi kiểu nguyên thủy.

### 4.2. Class cần class literal

Ví dụ:

```java
@interface TypeHint {
    Class<?> value();
}

// Các cách dùng hợp lệ:
// @TypeHint(String.class)
// @TypeHint(int.class)
// @TypeHint(String[].class)
```

Biểu thức như `object.getClass()` hoặc `Class.forName("java.lang.String")` không được dùng thay class literal trong giá trị annotation.

Với `Class<? extends Runnable>`, class literal được truyền còn phải đáp ứng ràng buộc kiểu. `String.class` không phù hợp vì `String` không triển khai `Runnable`.

Không thể viết `List<String>.class`: Java không có class literal cho một kiểu tham số hóa như vậy. Đừng nhầm việc cho phép phần tử mang kiểu `Class<?>` với việc cho phép mọi biểu thức generic xuất hiện trước `.class`.

### 4.3. Enum cần hằng enum

Với:

```java
enum Mode {
    SAFE, FAST
}

@interface Execution {
    Mode value();
}
```

cách dùng hợp lệ là `@Execution(Mode.SAFE)`.

Một biến `static final Mode DEFAULT = Mode.SAFE;` không thay thế được tên hằng enum khi gán giá trị annotation:

```java
class Defaults {
    static final Mode DEFAULT = Mode.SAFE;
}

// Không hợp lệ:
// @Execution(Defaults.DEFAULT)
```

Đây là khác biệt với biến hằng có kiểu nguyên thủy/String. Giá trị enum phải được chỉ định bằng hằng enum theo quy tắc của ngôn ngữ, không qua một biến bí danh kiểu enum.

### 4.4. Annotation lồng dùng cú pháp annotation

Ví dụ:

```java
@interface Owner {
    String value();
}

@interface Metadata {
    Owner owner();
}

@Metadata(owner = @Owner("team-a"))
class OwnedJob {
}
```

Không dùng `new Owner(...)`. Đây là siêu dữ liệu annotation lồng nhau, không phải lời gọi constructor tạo một đối tượng theo cú pháp lớp thông thường.

## 5. Mảng một chiều và cách viết một phần tử

Với:

```java
@interface Tags {
    String[] value() default {};
}
```

các cách dùng sau hợp lệ:

```java
@Tags({"io", "batch"})
class MultipleTags {
}

@Tags("io")
class SingleTag {
}

@Tags({})
class EmptyTags {
}

@Tags
class DefaultTags {
}
```

Nếu giá trị mảng chỉ có một phần tử, có thể bỏ cặp ngoặc nhọn. `@Tags("io")` vẫn biểu diễn mảng một phần tử; nó không đổi kiểu phần tử `value` thành String.

Cần phân biệt:

- Dấu ngoặc nhọn `{}` biểu diễn mảng rỗng.
- Bỏ phần tử khi đã có `default {}` dùng giá trị mặc định.
- `null` không phải cách viết mảng rỗng.

Không dùng `new String[] {"io"}` trong giá trị annotation. Cũng không thể khai báo một mảng `static final` rồi truyền tên mảng đó thay cho danh sách phần tử. Mảng không phải biến hằng theo quy tắc dành cho giá trị nguyên thủy/String, và cú pháp giá trị annotation có quy định riêng.

Với mảng annotation, có thể viết dạng:

```java
@interface Owners {
    Owner[] value();
}

@Owners({@Owner("team-a"), @Owner("team-b")})
class SharedJob {
}
```

Mỗi phần tử con vẫn phải đáp ứng kiểu và quy tắc giá trị tương ứng.

## 6. Không dùng null làm giá trị hoặc mặc định

Ngay cả khi kiểu phần tử là kiểu tham chiếu như `String`, `Class<?>`, enum, annotation hay mảng, `null` vẫn không phải giá trị annotation hợp lệ.

Các dòng minh họa sai:

```java
@interface InvalidDefaults {
    // String name() default null;
    // Class<?> type() default null;
    // String[] tags() default null;
}
```

Nếu dữ liệu có thể không được cấu hình, hãy thiết kế hợp đồng rõ ràng: ví dụ mảng rỗng cho “không có nhãn”, enum có giá trị `UNSPECIFIED` nếu có ý nghĩa miền, hoặc giá trị mặc định được tài liệu hóa. Không nên tự chọn một giá trị đặc biệt mà bên đọc không biết cách diễn giải.

Nếu phần tử không có giá trị mặc định, mọi chỗ dùng annotation phải cung cấp nó. Mặc định cũng phải đúng kiểu và đúng các quy tắc giá trị như khi viết trực tiếp tại chỗ dùng.

## 7. Ví dụ chạy đầy đủ với các nhóm kiểu chính

Lưu thành `AnnotationElementTypesDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class AnnotationElementTypesDemo {
    enum Mode {
        SAFE, FAST
    }

    @Retention(RetentionPolicy.RUNTIME)
    @interface Owner {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface JobSpec {
        String value();
        int retries() default 3;
        Class<? extends Runnable> handler();
        Mode mode() default Mode.SAFE;
        Owner owner();
        String[] tags() default {};
    }

    public static final class ImportTask implements Runnable {
        @Override
        public void run() {
        }
    }

    @JobSpec(
            value = "import",
            handler = ImportTask.class,
            owner = @Owner("team-a"),
            tags = {"io", "batch"}
    )
    static class ImportJob {
    }

    public static void main(String[] args) {
        JobSpec spec = ImportJob.class.getAnnotation(JobSpec.class);

        System.out.println("name=" + spec.value());
        System.out.println("retries=" + spec.retries());
        System.out.println("handler="
                + spec.handler().getSimpleName());
        System.out.println("mode=" + spec.mode());
        System.out.println("owner=" + spec.owner().value());
        System.out.println("tags=" + Arrays.toString(spec.tags()));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 AnnotationElementTypesDemo.java
java AnnotationElementTypesDemo
```

Kết quả:

```text
name=import
retries=3
handler=ImportTask
mode=SAFE
owner=team-a
tags=[io, batch]
```

Ví dụ đọc lại metadata để quan sát giá trị. `@Retention(RUNTIME)` phục vụ việc truy cập qua reflection trong chương trình; nó không mở rộng danh sách kiểu phần tử hợp lệ. `@Target(TYPE)` giới hạn nơi đặt `JobSpec`, cũng không thay đổi quy tắc kiểu phần tử.

Lớp `ImportTask` không được khởi tạo hoặc chạy trong ví dụ. Dòng `handler=ImportTask` chỉ đến từ thông tin class literal được lưu trong annotation.

## 8. Một số giới hạn khai báo liên quan

- Phần tử annotation không nhận tham số.
- Không khai báo phần tử như một phương thức generic có tham số kiểu riêng.
- Không có thân phương thức để tính và trả giá trị.
- Cú pháp `default 3` là mặc định của phần tử, khác với phương thức default có thân trong một interface thông thường.
- Không khai báo kiểu phần tử trực tiếp hoặc gián tiếp chứa chính kiểu annotation đó.

Ví dụ chu trình không hợp lệ:

```java
// @interface Recursive {
//     Recursive value();
// }
```

Chu trình qua một annotation khác hoặc qua mảng cũng không trở nên hợp lệ chỉ vì đã thêm một lớp trung gian. Annotation có thể lồng nhau theo cấu trúc hữu hạn, nhưng khai báo kiểu không được tạo quan hệ chứa chính nó theo quy tắc này.

Một annotation vẫn có thể dùng `Class<?> value();` để tham chiếu tới một kiểu, kể cả kiểu annotation, vì đó là phần tử kiểu Class; điều này khác việc khai báo phần tử có chính kiểu annotation đó.

## 9. Cách chọn kiểu khi thiết kế annotation

1. Dùng nguyên thủy/String cho dữ liệu nhỏ có thể biểu diễn bằng hằng.
2. Dùng enum khi muốn một tập lựa chọn có tên rõ ràng.
3. Dùng `Class<? extends ...>` khi cần chỉ định một loại xử lý và có thể thể hiện ràng buộc bằng hệ thống kiểu.
4. Dùng annotation lồng để nhóm metadata có cấu trúc.
5. Dùng mảng một chiều khi cần nhiều giá trị cùng vai trò.
6. Nếu cấu hình cần đối tượng phức tạp, trạng thái thay đổi hoặc giá trị lấy từ môi trường lúc chạy, cân nhắc cơ chế cấu hình khác thay vì cố nhét trực tiếp vào annotation.

Tự kiểm tra: vì sao `int count()` hợp lệ nhưng `Integer count()` không hợp lệ; vì sao `String name()` hợp lệ nhưng `default null` không hợp lệ; và vì sao `Class<? extends Runnable>` không đồng nghĩa annotation chứa sẵn một đối tượng Runnable?

## Tài liệu đối chiếu

- [JLS §9.6.1 — Khai báo phần tử annotation và kiểu được phép](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.1).
- [JLS §9.6.2 — Giá trị mặc định](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.2).
- [JLS §9.7.1 — Kiểu và giá trị tại chỗ dùng annotation](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.1).
