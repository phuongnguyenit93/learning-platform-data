# Truyền mảng trong Java annotation: ngoặc nhọn, một phần tử và mảng rỗng

Trong Java, một *annotation element* có thể khai báo kiểu mảng một chiều, chẳng hạn `String[]`, `int[]`, `Class<?>[]` hoặc mảng enum. Khi gán giá trị cho element đó, có ba trường hợp quan trọng: **nhiều phần tử dùng `{...}`**, **một phần tử có thể bỏ `{...}`**, và **mảng rỗng phải biểu diễn bằng `{}`** nếu muốn gán tường minh. Đây là quy tắc cú pháp riêng cho giá trị annotation, không phải thao tác truyền tham số vào phương thức Java thông thường.

## 1. Nhận diện element có kiểu mảng

Định nghĩa annotation:

```java
@interface Labels {
    String[] value();
}
```

`value()` là tên một element; `String[]` là **kiểu giá trị của element**. Chỗ sử dụng annotation phải cung cấp một tập chuỗi dưới dạng giá trị được Java cho phép tại thời điểm biên dịch.

```java
@Labels({"core", "annotation"}) // Hai chuỗi
class MultipleLabels {}

@Labels({"core"})               // Một chuỗi, viết đủ ngoặc nhọn
class ExplicitSingleLabel {}

@Labels("core")                 // Một chuỗi, rút gọn hợp lệ
class ImplicitSingleLabel {}

@Labels({})                     // Không có chuỗi nào
class EmptyLabels {}
```

Cả `@Labels({"core"})` và `@Labels("core")` đều tạo ra giá trị `String[]` có đúng **một** phần tử `"core"`. Việc bỏ ngoặc nhọn không đổi kiểu khai báo từ `String[]` thành `String`.

## 2. Ba cách truyền mảng và ý nghĩa

| Trường hợp | Cú pháp | Giá trị thu được | Ghi nhớ |
|---|---|---|---|
| Nhiều phần tử | `@Labels({"a", "b"})` | `["a", "b"]` | Cần cặp `{ }` để chứa danh sách |
| Một phần tử, đầy đủ | `@Labels({"a"})` | `["a"]` | Có thể dùng nếu muốn thống nhất phong cách |
| Một phần tử, rút gọn | `@Labels("a")` | `["a"]` | Compiler hiểu là mảng một phần tử |
| Không phần tử | `@Labels({})` | `[]` | Không thể dùng cách rút gọn của một phần tử |

**Không dùng dấu phẩy để truyền nhiều đối số** như `@Labels("a", "b")`: annotation ở đây nhận *một element kiểu mảng*, không nhận hai tham số phương thức. Danh sách nhiều giá trị nằm trong `{...}`.

Trong cú pháp khởi tạo mảng của annotation, dấu phẩy cuối cũng hợp lệ, ví dụ `@Labels({"a", "b",})`; dạng không có dấu phẩy cuối thường dễ đọc hơn.

## 3. Tại sao có thể bỏ tên `value`?

Java cho phép cú pháp rút gọn *single-element annotation* khi cung cấp element tên chính xác là `value`:

```java
@Labels(value = {"core", "annotation"})
class NamedElement {}

@Labels({"core", "annotation"})
class OmittedName {}
```

Hai cách trên tương đương. Với một giá trị, có thể kết hợp cả hai kiểu rút gọn:

```java
@Labels(value = "core")
class NamedSingle {}

@Labels("core")
class ShortSingle {}
```

Tên `value` có ý nghĩa đặc biệt **chỉ về mặt cú pháp viết annotation**. Nếu tên element là `tags` thì vẫn dùng được dạng bỏ ngoặc nhọn khi có một phần tử, nhưng **không được bỏ tên `tags`**:

```java
@interface Feature {
    String name();
    String[] tags();
}

@Feature(name = "cache", tags = {"fast", "safe"})
class CacheFeature {}

@Feature(name = "login", tags = "security")
class LoginFeature {}

@Feature(name = "health", tags = {})
class HealthFeature {}
```

Trong ví dụ này, `tags = "security"` hợp lệ vì `tags()` trả về `String[]`; compiler xử lý giá trị đơn thành mảng một phần tử. `@Feature({"fast"})` không hợp lệ vì `Feature` không có element tên `value`, đồng thời `name` và `tags` là các element bắt buộc chưa được chỉ định.

## 4. Mảng rỗng khác với bỏ qua annotation hoặc element

Xét khai báo **không có mặc định**:

```java
@interface RequiredTags {
    String[] value();
}

@RequiredTags({})
class HasNoTags {}
```

`@RequiredTags({})` hoàn toàn hợp lệ: element vẫn được cung cấp, chỉ là mảng có độ dài bằng 0. Ngược lại, `@RequiredTags` hoặc `@RequiredTags()` sẽ **lỗi biên dịch** vì thiếu element bắt buộc `value`.

Nếu muốn cho phép người dùng không ghi giá trị, hãy khai báo mặc định:

```java
@interface OptionalTags {
    String[] value() default {};
}

@OptionalTags            // Dùng mặc định {}
class WithDefault {}

@OptionalTags()          // Cũng dùng mặc định {}
class WithEmptyParentheses {}

@OptionalTags({})        // Gán tường minh {}
class WithExplicitEmpty {}
```

Cả ba class đều nhận mảng rỗng khi đọc `OptionalTags.value()`. Tuy nhiên, **class không được gắn `@OptionalTags`** là trường hợp khác: annotation vắng mặt hoàn toàn. Đối với reflection, `getAnnotation(OptionalTags.class)` trả về `null` khi annotation vắng mặt, còn annotation hiện diện với mảng rỗng vẫn cho một đối tượng annotation hợp lệ.

Điểm khác nhau cần nhớ:

- **Mảng rỗng**: annotation có mặt, giá trị của element là mảng độ dài 0.
- **Bỏ element có `default {}`**: annotation có mặt, Java sử dụng giá trị mặc định rỗng.
- **Bỏ annotation**: annotation không có mặt; không thể suy ra từ việc thấy cùng kết quả mảng rỗng ở các class khác.

## 5. Ví dụ Java 17+ chạy đầy đủ và quan sát kết quả

Tạo tệp `AnnotationArrayDemo.java` với toàn bộ nội dung:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    String[] value() default {};
}

@Labels({"core", "annotation"})
class Multiple {}

@Labels({"core"})
class ExplicitSingle {}

@Labels("core")
class ShortSingle {}

@Labels({})
class ExplicitEmpty {}

@Labels
class DefaultEmpty {}

class Absent {}

public class AnnotationArrayDemo {
    private static void printLabels(Class<?> type) {
        Labels annotation = type.getAnnotation(Labels.class);

        if (annotation == null) {
            System.out.println(type.getSimpleName() + " -> annotation absent");
            return;
        }

        String[] values = annotation.value();
        System.out.println(
                type.getSimpleName() + " -> "
                        + Arrays.toString(values)
                        + ", length=" + values.length
        );
    }

    public static void main(String[] args) {
        printLabels(Multiple.class);
        printLabels(ExplicitSingle.class);
        printLabels(ShortSingle.class);
        printLabels(ExplicitEmpty.class);
        printLabels(DefaultEmpty.class);
        printLabels(Absent.class);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac AnnotationArrayDemo.java
java AnnotationArrayDemo
```

Kết quả chuẩn:

```text
Multiple -> [core, annotation], length=2
ExplicitSingle -> [core], length=1
ShortSingle -> [core], length=1
ExplicitEmpty -> [], length=0
DefaultEmpty -> [], length=0
Absent -> annotation absent
```

Giải thích: `@Retention(RetentionPolicy.RUNTIME)` giữ annotation để `Class.getAnnotation(...)` đọc được khi chạy; `@Target(ElementType.TYPE)` giới hạn nơi áp dụng vào khai báo kiểu như class. `Arrays.toString(...)` chỉ dùng để in mảng cho dễ quan sát. Kết quả cho thấy cú pháp rút gọn vẫn tạo một mảng, và mảng rỗng vẫn khác việc không có annotation.

Nếu dùng retention mặc định (`CLASS`) hoặc `SOURCE`, ví dụ reflection trên sẽ không quan sát được annotation lúc chạy; điều đó liên quan đến retention, **không liên quan đến cách viết mảng**.

## 6. Áp dụng với các kiểu mảng annotation khác

Quy tắc mảng một phần tử cũng áp dụng cho element có các kiểu hợp lệ khác, không riêng `String[]`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface AllowedPlaces {}

@Target(ElementType.TYPE)
@interface OnlyTypes {}

@interface RetryPolicy {
    int[] delays();
}

@RetryPolicy(delays = {100, 200, 500})
class RetryExample {}

@interface HandlerTypes {
    Class<?>[] value();
}

@HandlerTypes({String.class, Integer.class})
class MultipleHandlers {}

@HandlerTypes(String.class)
class SingleHandler {}

@interface States {
    State[] value();
}

enum State {
    NEW, RUNNING, DONE
}

@States({State.NEW, State.RUNNING})
class InitialStates {}

@States(State.DONE)
class FinishedState {}
```

`@Target` chính là ví dụ trong JDK: element `value()` của nó có kiểu `ElementType[]`. Vì thế `@Target(ElementType.TYPE)` và `@Target({ElementType.TYPE})` đều hợp lệ. Với `Class<?>[]`, dùng class literal (`String.class`); với enum array, dùng hằng enum (`State.DONE`). Các giá trị phải hợp lệ với kiểu đã khai báo.

Một ví dụ thường gặp khác trong Java là `@SuppressWarnings("unchecked")` cho một cảnh báo và `@SuppressWarnings({"unchecked", "rawtypes"})` cho nhiều cảnh báo. `@SuppressWarnings({})` là mảng rỗng, vì vậy không yêu cầu bỏ qua cảnh báo nào.

## 7. Các lỗi thường gặp

**Lỗi 1: Viết nhiều giá trị mà không dùng ngoặc nhọn.**

```java
@Labels("core", "annotation") // Sai
class WrongMultiple {}
```

Sửa thành `@Labels({"core", "annotation"})` hoặc `@Labels(value = {"core", "annotation"})`.

**Lỗi 2: Dùng cú pháp tạo mảng thông thường ngay trong annotation.**

```java
@Labels(new String[] {"core", "annotation"}) // Sai trong annotation
class WrongArrayCreation {}
```

Trong Java annotation, viết trực tiếp `{"core", "annotation"}`. Annotation element nhận các biểu thức được ngôn ngữ cho phép tại compile time, không nhận đối tượng mảng mới tạo bởi `new` theo cách gán biến thông thường.

**Lỗi 3: Truyền biến mảng hoặc `null`.**

```java
class NotCompile {
    static final String[] TAGS = {"core"};

    @Labels(TAGS) // Sai: không phải dạng giá trị annotation hợp lệ
    static class UsingVariable {}

    @Labels(null) // Sai: null không phải giá trị hợp lệ
    static class UsingNull {}
}
```

Dù `TAGS` là `static final`, bản thân một mảng không phải *compile-time constant variable* có thể truyền thẳng vào annotation. Phải viết các phần tử được phép trong initializer: `@Labels({"core"})`. `null` cũng không biểu diễn được mảng rỗng; hãy viết `{}`.

**Lỗi 4: Không cung cấp element bắt buộc.**

```java
@interface Mandatory {
    String[] roles();
}

// @Mandatory                 // Sai: chưa có roles
@Mandatory(roles = {})       // Đúng: roles là mảng rỗng
class NoRoles {}
```

Chỉ có thể bỏ `roles` khi định nghĩa `roles() default {}` (hoặc một giá trị mặc định hợp lệ khác).

**Lỗi 5: Nhầm mảng giá trị với repeatable annotation.**

```java
@interface Categories {
    String[] value();
}

@Categories({"api", "security"})
class Controller {}
```

Đây là **một** instance của `@Categories` có element là mảng hai chuỗi. Nó không đồng nghĩa với gắn hai annotation riêng biệt. Muốn viết nhiều annotation cùng loại trên một khai báo cần cơ chế `@Repeatable` và container annotation phù hợp; đó là một tính năng khác.

**Lỗi 6: Khai báo loại mảng không được annotation hỗ trợ.** Element kiểu mảng của annotation chỉ là mảng **một chiều** của kiểu element hợp lệ (primitive, `String`, `Class`, enum hoặc annotation type). Không khai báo `String[][] value()` hay dùng tùy ý kiểu như `List<String>` làm kiểu trả về của annotation element.

## 8. Bài tập tự kiểm tra

Cho định nghĩa:

```java
@interface Permissions {
    String[] value() default {};
}
```

Hãy xác định độ dài mảng khi đọc `Permissions.value()` ở mỗi trường hợp:

| Cách dùng | Độ dài | Giải thích |
|---|---:|---|
| `@Permissions({"READ", "WRITE"})` | 2 | Có hai phần tử trong initializer |
| `@Permissions("READ")` | 1 | Viết tắt của mảng một phần tử |
| `@Permissions({"READ"})` | 1 | Viết đầy đủ một phần tử |
| `@Permissions({})` | 0 | Gán mảng rỗng tường minh |
| `@Permissions` | 0 | Nhận mặc định `default {}` |
| Không gắn `@Permissions` | Không áp dụng | Không có annotation; `getAnnotation(...)` trả về `null` |

Thử đổi `String[] value() default {};` thành `String[] value();`, rồi biên dịch lại các trường hợp `@Permissions` và `@Permissions({})`. Trường hợp đầu sẽ lỗi vì thiếu giá trị bắt buộc; trường hợp sau vẫn hợp lệ vì truyền tường minh mảng rỗng.

**Quy tắc thực hành:** nhìn kiểu trả về của element trước. Với kiểu mảng, dùng `{a, b}` cho nhiều giá trị, `{a}` hoặc `a` cho một giá trị, và `{}` cho không giá trị. Sau đó xem tên element có phải `value` để quyết định có được lược bỏ tên hay không, và xem `default` để biết element có được phép bỏ hẳn hay không.
