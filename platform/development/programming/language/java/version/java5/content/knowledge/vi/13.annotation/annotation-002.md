# Cú pháp sử dụng và khai báo kiểu annotation

## 1. Phân biệt khai báo kiểu annotation và sử dụng annotation

**Annotation** là siêu dữ liệu gắn với thành phần chương trình hoặc một vị trí kiểu dữ liệu được phép. Nó mô tả thông tin để trình biên dịch, công cụ hoặc mã đọc siêu dữ liệu sử dụng.

Có hai việc khác nhau:

```java
@interface Label {
    String value();
}
```

Đoạn trên **khai báo một kiểu annotation** tên `Label`.

```java
@Label("Java")
class Example {
}
```

Đoạn thứ hai **sử dụng annotation** thuộc kiểu đó trên lớp `Example`.

Khai báo dùng `@interface`; nơi sử dụng dùng `@TênAnnotation`. Annotation không phải lời gọi constructor, và việc thêm một annotation tự viết không tự làm xuất hiện hành vi nghiệp vụ. Cần có trình biên dịch, công cụ hoặc đoạn mã cụ thể hiểu ý nghĩa của siêu dữ liệu ấy.

Bài sử dụng cú pháp còn áp dụng trên Java hiện hành, với chương trình kiểm chứng chạy được từ Java 17 trở lên.

## 2. Cú pháp khai báo kiểu annotation

Một khai báo cơ bản:

```java
public @interface LessonInfo {
    String value();
    int level() default 1;
    String[] tags() default {};
}
```

Ý nghĩa từng phần:

- `public @interface LessonInfo`: khai báo kiểu annotation tên `LessonInfo`.
- `String value();`: khai báo phần tử `value` có kiểu `String`.
- `int level() default 1;`: phần tử `level` có giá trị mặc định là 1.
- `String[] tags() default {};`: phần tử `tags` là mảng chuỗi, mặc định là mảng rỗng.

Các phần tử được viết với hình thức khai báo phương thức không có tham số. Tuy nhiên, khi sử dụng annotation, ta cung cấp các cặp `tên = giá trị`, không viết lời gọi phương thức trong dấu ngoặc annotation.

So sánh đúng vị trí cú pháp:

```java
// Trong khai báo annotation:
int level() default 1;

// Ở nơi sử dụng:
@LessonInfo(value = "Java", level = 2)
class Lesson {
}
```

`default` ở đây khai báo giá trị mặc định của phần tử annotation. Nó không phải cú pháp phương thức `default` có thân trong một interface thông thường.

Một phần tử annotation không có tham số, không có thân phương thức, không có tham số kiểu và không có mệnh đề `throws`. Các phần tử có tính chất `public abstract`; thường không cần viết hai modifier này.

Với kiểu `public` cấp cao nhất, đặt khai báo trong tệp trùng tên, chẳng hạn `LessonInfo.java`. Nếu ở package khác, sử dụng import kiểu thông thường như `import demo.LessonInfo;` hoặc tên đầy đủ của kiểu; không dùng static import để nhập chính annotation cấp cao nhất.

Quy định khai báo nằm trong [JLS §9.6](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6).

## 3. Ba dạng sử dụng annotation

### 3.1. Dạng đánh dấu

Một annotation không cần cung cấp giá trị có thể viết dưới dạng:

```java
@Reviewed
class Tagged {
}
```

Dạng có cặp ngoặc rỗng cũng hợp lệ nếu mọi phần tử bắt buộc đã được đáp ứng bằng giá trị mặc định hoặc kiểu annotation không có phần tử:

```java
@Reviewed()
class AlsoTagged {
}
```

Ví dụ này giả định `Reviewed` được phép gắn trên lớp. Vị trí được phép do hợp đồng của kiểu annotation, đặc biệt `@Target` nếu có, quyết định.

### 3.2. Dạng các cặp tên–giá trị

```java
@LessonInfo(value = "Java", level = 2, tags = {"core", "syntax"})
class NormalForm {
}
```

Các phần tử được phân cách bằng dấu phẩy. Tên phải khớp đúng với phần tử đã khai báo. Thứ tự cặp tên–giá trị có thể thay đổi; kiểu dữ liệu và giá trị bắt buộc vẫn phải hợp lệ.

Không viết dấu chấm phẩy ngay sau `@LessonInfo(...)` để kết thúc nó như một câu lệnh. Annotation đứng tại vị trí gắn với khai báo tương ứng.

### 3.3. Dạng rút gọn cho phần tử value

Nếu chỉ cung cấp giá trị cho phần tử có tên **chính xác là `value`**, có thể bỏ `value =`:

```java
@LessonInfo("Java")
class ShortForm {
}
```

Dạng trên tương đương:

```java
@LessonInfo(value = "Java")
class ExplicitValue {
}
```

Điều kiện là mọi phần tử khác không được ghi ra đều có giá trị mặc định. Tên `value` có vai trò đặc biệt trong cú pháp rút gọn; một phần tử tên `name` không được tự động hưởng cú pháp đó.

Khi muốn cung cấp thêm phần tử khác, quay về các cặp tên–giá trị:

```java
@LessonInfo(value = "Java", level = 2)
class WithLevel {
}

// Không hợp lệ:
// @LessonInfo("Java", level = 2)
```

Ba dạng được mô tả trong [JLS §9.7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7).

## 4. Giá trị bắt buộc, giá trị mặc định và mảng

### Phần tử không có default là bắt buộc

Với khai báo ở phần đầu, `value` không có `default`. Vì vậy:

```java
@LessonInfo("Java") // Có value; level và tags dùng mặc định.
class ValidUse {
}

// Không hợp lệ vì thiếu value:
// @LessonInfo(level = 2)
```

Không có quy tắc tự điền chuỗi rỗng, số 0 hoặc null cho mọi phần tử bị bỏ qua. Chỉ phần tử đã khai báo giá trị mặc định mới có thể được bỏ qua tại nơi sử dụng.

### Phần tử mảng

Với `String[] tags()`, có thể dùng:

```java
@LessonInfo(value = "Empty", tags = {})
class EmptyTags {
}

@LessonInfo(value = "One", tags = {"core"})
class OneTag {
}

@LessonInfo(value = "Many", tags = {"core", "syntax"})
class ManyTags {
}
```

Nếu mảng chỉ có một phần tử, Java cho phép bỏ dấu ngoặc nhọn:

```java
@LessonInfo(value = "One", tags = "core")
class OneTagWithoutBraces {
}
```

`tags = "core"` ở đây được hiểu là mảng một phần tử, không làm kiểu khai báo của `tags` đổi từ `String[]` thành `String`.

Nếu chính phần tử `value` có kiểu mảng, hai quy tắc rút gọn có thể phối hợp. Ví dụ sau gồm một khai báo annotation và hai lớp sử dụng:

```java
@interface Tags {
    String[] value();
}

@Tags({"java", "core"})
class MultipleTags {
}

@Tags("java")
class SingleTag {
}
```

Không dùng `new String[] {...}` để biểu diễn giá trị annotation; cú pháp mảng annotation dùng trực tiếp dấu ngoặc nhọn hoặc giá trị đơn như các ví dụ trên.

## 5. Những kiểu dữ liệu được phép cho phần tử

Một phần tử annotation không thể có kiểu tùy ý như một trường thông thường.

| Nhóm kiểu hợp lệ | Ví dụ khai báo phần tử |
|---|---|
| Kiểu nguyên thủy | `int level();`, `boolean enabled();` |
| `String` | `String title();` |
| `Class` hoặc dạng tham số hóa phù hợp của `Class` | `Class<?> owner();` |
| Kiểu enum | `Mode mode();` |
| Một kiểu annotation khác | `Author author();` |
| Mảng một chiều của các kiểu được phép ở trên | `String[] tags();`, `int[] codes();` |

Không hợp lệ:

```java
// Các khai báo sau có chủ đích sai:
// Integer count();       // Kiểu bao không thay cho kiểu nguyên thủy int.
// Object anything();     // Không phải kiểu phần tử annotation hợp lệ.
// java.util.List<String> names(); // Collection không hợp lệ.
// String[][] matrix();   // Mảng nhiều chiều không hợp lệ.
// void action();         // Phần tử không trả về void.
```

Một kiểu annotation có thể chứa khai báo enum hoặc kiểu thành viên khác phục vụ mô hình dữ liệu. Ví dụ đầy đủ bên dưới khai báo enum `Mode` ngay trong `LessonInfo`.

### Giá trị cũng có giới hạn

Không phải biểu thức Java bất kỳ đều có thể đặt làm giá trị annotation:

- Với kiểu nguyên thủy và `String`, cần biểu thức hằng phù hợp.
- Với `Class`, dùng class literal như `String.class` hoặc `Object.class`.
- Với enum, dùng một hằng enum phù hợp như `Mode.PUBLISHED`.
- Với phần tử annotation, dùng annotation lồng như `@Author("team")`.
- Với mảng, dùng các giá trị thành phần hợp lệ.
- `null` không được dùng làm giá trị phần tử annotation, kể cả khi kiểu khai báo là kiểu tham chiếu.

Ví dụ biểu thức hằng:

```java
class Names {
    static final String TITLE = "Java" + " syntax";
}

@LessonInfo(Names.TITLE)
class ConstantValue {
}

// Không hợp lệ vì có lời gọi phương thức, không phải biểu thức hằng:
// @LessonInfo(String.valueOf(2))

// Không hợp lệ:
// @LessonInfo(null)
```

`static final` một mình chưa bảo đảm giá trị là biểu thức hằng hợp lệ. Chẳng hạn, một `String` được khởi tạo bằng lời gọi phương thức không trở thành hằng biên dịch chỉ nhờ có hai modifier đó.

Nếu cần thể hiện trạng thái “không có giá trị”, hãy thiết kế giá trị mặc định hoặc giá trị quy ước phù hợp, chẳng hạn mảng rỗng; không dùng null.

## 6. Chương trình đầy đủ: khai báo, sử dụng và đọc kết quả

Chương trình có ba tệp trong cùng một thư mục:

```text
LessonInfo.java
Marker.java
AnnotationSyntaxDemo.java
```

### Tệp LessonInfo.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface LessonInfo {
    String value();
    int level() default 1;
    String[] tags() default {};
    Class<?> owner() default Object.class;
    Mode mode() default Mode.DRAFT;

    enum Mode {
        DRAFT, PUBLISHED
    }
}
```

`@Retention(RetentionPolicy.RUNTIME)` giữ annotation để chương trình đọc bằng reflection. `@Target` giới hạn nơi dùng vào khai báo kiểu và phương thức. Hai annotation này là siêu dữ liệu của chính kiểu annotation ta đang khai báo.

Chúng được ghi rõ để ví dụ có thể kiểm chứng khi chạy. Nếu không khai báo `@Retention`, chính sách mặc định là `CLASS`, không đủ cho cách đọc annotation bằng reflection trong chương trình này.

### Tệp Marker.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Marker {
}
```

Ở ví dụ đầy đủ này, `Marker` chỉ được phép gắn lên phương thức. Chương trình gắn nó lên phương thức `marked`, đúng với `@Target` đã khai báo.

### Tệp AnnotationSyntaxDemo.java

```java
import java.util.Arrays;

@LessonInfo(
        value = "Java annotations",
        level = 2,
        tags = {"annotation", "syntax"},
        owner = String.class,
        mode = LessonInfo.Mode.PUBLISHED
)
public class AnnotationSyntaxDemo {
    @LessonInfo("Short")
    public static void shortForm() {
    }

    @LessonInfo(value = "One", tags = "solo")
    public static void singleArrayItem() {
    }

    @Marker
    public static void marked() {
    }

    public static void main(String[] args) throws NoSuchMethodException {
        LessonInfo typeInfo = AnnotationSyntaxDemo.class.getAnnotation(LessonInfo.class);
        System.out.println("value=" + typeInfo.value());
        System.out.println("level=" + typeInfo.level());
        System.out.println("tags=" + Arrays.toString(typeInfo.tags()));
        System.out.println("owner=" + typeInfo.owner().getSimpleName());
        System.out.println("mode=" + typeInfo.mode());

        LessonInfo shortInfo = AnnotationSyntaxDemo.class
                .getMethod("shortForm").getAnnotation(LessonInfo.class);
        System.out.println("short=" + shortInfo.value()
                + ", level=" + shortInfo.level()
                + ", tags=" + Arrays.toString(shortInfo.tags()));

        LessonInfo arrayInfo = AnnotationSyntaxDemo.class
                .getMethod("singleArrayItem").getAnnotation(LessonInfo.class);
        System.out.println("single=" + Arrays.toString(arrayInfo.tags()));
        System.out.println("marker=" + AnnotationSyntaxDemo.class
                .getMethod("marked").isAnnotationPresent(Marker.class));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror LessonInfo.java Marker.java AnnotationSyntaxDemo.java
java AnnotationSyntaxDemo
```

Stdout chính xác:

```text
value=Java annotations
level=2
tags=[annotation, syntax]
owner=String
mode=PUBLISHED
short=Short, level=1, tags=[]
single=[solo]
marker=true
```

### Đọc kết quả

- Annotation trên lớp dùng dạng các cặp tên–giá trị, cung cấp đủ chuỗi, số nguyên, mảng, class literal và hằng enum.
- `@LessonInfo("Short")` dùng cú pháp rút gọn cho `value`; `level` là 1 và `tags` là mảng rỗng do mặc định.
- `tags = "solo"` tạo giá trị mảng một phần tử; stdout in `[solo]`.
- `@Marker` không có phần tử dữ liệu; chương trình chỉ kiểm tra nó có hiện diện trên phương thức không.
- Các lời gọi `value()`, `level()`, `tags()` xuất hiện trong mã **đọc annotation**, không phải cú pháp cung cấp giá trị ở nơi gắn annotation.

Phần reflection chỉ làm bằng chứng rằng các giá trị được khai báo đã được đọc đúng. Việc đặt `@LessonInfo(level = 2, ...)` không tự làm phương thức chạy hai lần, đổi độ khó bài học hay thực hiện một hành vi nào khác.

## 7. Annotation lồng là giá trị siêu dữ liệu, không phải new

Có thể dùng một annotation làm kiểu của phần tử trong annotation khác. Mảnh khai báo sau minh họa cú pháp; đặt các kiểu ở vị trí khai báo phù hợp trong tệp Java:

```java
@interface Author {
    String value();
}

@interface Details {
    String value();
    Author author() default @Author("team");
    int[] codes() default {};
}

@Details(value = "Java syntax", author = @Author("reviewer"), codes = {1, 2})
class DocumentedExample {
}
```

`author = @Author("reviewer")` cung cấp một giá trị annotation lồng. Không viết `new Author("reviewer")`: annotation không có constructor để gọi theo cách đó.

Nếu bỏ `author`, giá trị mặc định `@Author("team")` được dùng. Nếu bỏ `codes`, nó dùng mảng rỗng. Phần tử `value` vẫn bắt buộc vì không có mặc định.

Đây là cách tạo cấu trúc siêu dữ liệu có nhiều lớp nhưng vẫn nằm trong tập kiểu phần tử annotation được ngôn ngữ cho phép.

## 8. Vị trí sử dụng và các lỗi thường gặp

Annotation phải gắn ở vị trí hợp lệ với loại annotation. Các vị trí có thể gồm lớp, phương thức, trường, tham số hoặc vị trí sử dụng kiểu nếu annotation được khai báo cho phép. Không suy ra rằng “có dấu `@`” là có thể đặt vào bất kỳ câu lệnh nào.

Với `LessonInfo` của ví dụ đầy đủ, chỉ dùng trên kiểu và phương thức. Đặt nó trên một trường sẽ vi phạm `@Target`. Quy tắc vị trí là một lớp kiểm tra khác với việc cung cấp đúng các phần tử.

| Lỗi | Cách sửa |
|---|---|
| Dùng `interface` thay cho `@interface` khi muốn khai báo annotation | Dùng cú pháp khai báo annotation interface |
| Viết `String value;` để khai báo phần tử | Viết `String value();` |
| Viết `level() = 2` tại nơi sử dụng | Viết `level = 2` |
| Dùng rút gọn cho phần tử tên `name` | Viết `name = ...`; chỉ `value` có cú pháp rút gọn này |
| Bỏ phần tử chưa có `default` | Cung cấp giá trị bắt buộc |
| Ghi tên phần tử không tồn tại hoặc ghi cùng phần tử hai lần | Khớp đúng khai báo, mỗi phần tử được gán một lần |
| Dùng `Integer`, `List` hoặc mảng hai chiều làm kiểu phần tử | Chọn một kiểu phần tử hợp lệ |
| Truyền null hoặc biểu thức gọi phương thức | Chọn giá trị hợp lệ theo quy tắc annotation |
| Tạo giá trị lồng bằng `new` | Dùng `@TênAnnotation(...)` |
| Đặt annotation ở vị trí không được phép | Kiểm tra `@Target` và mục đích thiết kế |
| Reflection trả null dù thấy annotation trong nguồn | Kiểm tra chính sách lưu giữ; ví dụ đọc khi chạy cần `RUNTIME` |

Không cần tự `implements LessonInfo` trên lớp được đánh dấu. `@LessonInfo(...)` là cách gắn siêu dữ liệu; nó không thiết lập quan hệ kiểu con giữa lớp đó với annotation interface.

## 9. Thực hành

Cho khai báo:

```java
@interface Exercise {
    String value();
    int points() default 1;
    String[] topics() default {};
}
```

Viết annotation cho ba lớp:

1. Bài “Basics”, dùng toàn bộ mặc định còn lại.
2. Bài “Arrays”, 3 điểm, hai chủ đề “array” và “loop”.
3. Bài “One topic”, một chủ đề “annotation”, dùng dạng rút gọn mảng một phần tử.

Đáp án:

```java
@Exercise("Basics")
class BasicExercise {
}

@Exercise(value = "Arrays", points = 3, topics = {"array", "loop"})
class ArrayExercise {
}

@Exercise(value = "One topic", topics = "annotation")
class SingleTopicExercise {
}
```

Tự kiểm tra thêm:

- `@Exercise(points = 3)` không hợp lệ vì thiếu `value`.
- `@Exercise("Arrays", points = 3)` không hợp lệ vì trộn dạng rút gọn với cặp tên–giá trị.
- `@Exercise(value = "Arrays", topics = {})` hợp lệ và có mảng chủ đề rỗng.
- `@Exercise(value = null)` không hợp lệ.

Khi đọc hoặc viết annotation, hãy tách rõ **kiểu annotation khai báo những phần tử nào → phần tử nào bắt buộc → giá trị có đúng kiểu và đúng dạng hợp lệ không → annotation được phép gắn ở đâu**. Cú pháp rút gọn chỉ thay cách viết, không thay các điều kiện đó.
