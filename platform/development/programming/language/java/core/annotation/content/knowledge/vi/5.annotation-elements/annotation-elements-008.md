# Giá trị mặc định của mảng và annotation lồng nhau trong Java Core

Annotation trong Java cho phép khai báo **phần tử (element)** và giá trị mặc định bằng từ khóa `default`. Khi phần tử có kiểu mảng hoặc chính nó là một kiểu annotation, cú pháp của giá trị mặc định khác một biến Java thông thường: mảng được viết bằng dấu ngoặc nhọn `{...}`, còn annotation lồng nhau được viết dưới dạng `@AnnotationName(...)`. Bài này tập trung vào cách khai báo, sử dụng và đọc những giá trị ấy, cùng các quy tắc dễ nhầm khi kết hợp chúng.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Viết `default {}` cho mảng rỗng, `default {"a", "b"}` cho mảng có phần tử và hiểu cú pháp một phần tử được rút gọn.
- Phân biệt phần tử có kiểu annotation đơn với phần tử có kiểu **mảng annotation**.
- Khai báo mặc định `@Nested(...)` và `{@Nested(...), @Nested(...)}` đúng cú pháp.
- Giải thích khi nào Java dùng mặc định, khi nào giá trị ghi trực tiếp trong `@...` thay thế mặc định.
- Đọc được mảng và annotation lồng nhau qua Reflection, kể cả xem mặc định được khai báo bằng `Method.getDefaultValue()`.
- Tránh các lỗi liên quan đến `null`, `new`, kiểu `List`, biểu thức runtime và annotation lồng nhau chưa điền phần tử bắt buộc.

## 2. Ôn đúng khái niệm `default` trong annotation

Một annotation type khai báo element bằng cú pháp giống method không tham số:

~~~java
@interface Exercise {
    String title();                 // Bắt buộc: không có default.
    int level() default 1;         // Có thể bỏ qua khi sử dụng.
    String[] tags() default {};    // Mảng mặc định rỗng.
}
~~~

Đây là **đoạn khai báo minh họa**, không phải chương trình chạy độc lập. Khi gắn annotation:

~~~java
@Exercise(title = "Java")
class Basics {}
~~~

Java hiểu `level()` là `1` và `tags()` là mảng `String[]` rỗng, vì chúng không được truyền tại chỗ sử dụng. `title()` bắt buộc phải được khai báo vì nó không có mặc định.

Ghi nhớ:

- `default` đặt **trong khai báo annotation type**, sau danh sách tham số rỗng `()` của element.
- Không viết `default` ở nơi gắn annotation lên class/method/field; tại nơi sử dụng, ta chỉ truyền `tên = giá trị`.
- `default` ở annotation type **không phải** `default method` của interface thông thường: element không có body Java.
- Giá trị khai báo tại nơi sử dụng có quyền ưu tiên so với mặc định của element tương ứng. Các element khác vẫn dùng mặc định nếu không được cung cấp.
- Không có giá trị `null` cho một annotation element, kể cả làm mặc định hoặc làm giá trị truyền vào.

Một annotation type có thể có nhiều element; mỗi element có thể bắt buộc hoặc có giá trị mặc định riêng.

## 3. Giá trị mặc định của phần tử kiểu mảng

### 3.1. Mảng rỗng, một phần tử và nhiều phần tử

~~~java
@interface ResourceInfo {
    String[] labels() default {};                   // 0 phần tử.
    String[] extensions() default {"txt"};          // 1 phần tử.
    int[] retryDelays() default {100, 200, 500};    // 3 phần tử.
}
~~~

Các cách viết mặc định cho mảng:

| Khai báo | Giá trị khi không truyền |
| --- | --- |
| `String[] labels() default {};` | Mảng `String[]` độ dài 0 |
| `String[] labels() default {"core"};` | Mảng một chuỗi `"core"` |
| `String[] labels() default {"core", "java"};` | Mảng hai chuỗi theo đúng thứ tự |
| `int[] delays() default {10, 20};` | Mảng hai số nguyên |
| `Class<?>[] types() default {String.class, Integer.class};` | Mảng hai class literal |

Dấu `{}` trong ngữ cảnh annotation là **array initializer của annotation element**; không khai báo mặc định bằng `new String[] { ... }` hoặc một đối tượng mảng được tạo lúc runtime. Vì vậy, để mặc định rỗng cần viết `default {}`, không phải `default null`.

Quy tắc kiểu dữ liệu của annotation element chỉ cho phép mảng **một chiều** với kiểu phần tử hợp lệ: primitive, `String`, `Class`, enum hoặc annotation type. Không thể định nghĩa element `String[][]` hoặc `List<String>`, dù Java thường cho phép các kiểu đó ở biến/method khác.

### 3.2. Ghi đè mặc định khi sử dụng

Với:

~~~java
@interface Tags {
    String[] value() default {"basic", "java"};
}
~~~

Các cách dùng hợp lệ:

~~~java
@Tags
class UsesDefault {}

@Tags({})
class EmptyTags {}

@Tags({"advanced", "reflection"})
class TwoTags {}

@Tags("annotation")
class OneTag {}
~~~

Tất cả trên chỉ là các khai báo minh họa.

- `@Tags`: dùng mặc định `{"basic", "java"}`.
- `@Tags({})`: **chủ động ghi đè** thành mảng rỗng; không quay về mặc định.
- `@Tags({"advanced", "reflection"})`: thay bằng mảng hai chuỗi.
- `@Tags("annotation")`: rút gọn khi truyền một phần tử duy nhất của mảng `String[]`; Java hiểu như `{"annotation"}`.

Trong `@Tags(...)`, tên `value` được lược bỏ vì đó là element mang tên đặc biệt `value`. Nếu tên element là `labels`, bạn phải viết `@ResourceInfo(labels = "one")`; không thể bỏ tên `labels` như trường hợp `value`.

Viết `@Tags(value = {"x"})` và `@Tags({"x"})` cũng tương đương. Nếu toàn bộ element của một annotation type đều có mặc định, bạn có thể gắn annotation không đối số bằng `@Tags` hoặc `@Tags()`.

### 3.3. Mặc định rỗng khác “không được khai báo”

Ở góc nhìn sử dụng:

~~~java
@interface Flags {
    String[] value() default {};
}

@Flags
class A {}

@Flags({})
class B {}
~~~

Khi gọi `value()` trên annotation runtime tương ứng, cả hai trả về mảng rỗng. Tuy nhiên về khai báo, `A` **không cung cấp** giá trị trực tiếp, còn `B` **có cung cấp** giá trị rỗng một cách tường minh. Khác biệt này quan trọng nếu sau này sửa mặc định của `Flags.value()`: cách dùng ở `A` có thể nhận mặc định mới khi được đọc, trong khi `B` tiếp tục dùng giá trị rỗng đã ghi tường minh.

Mảng mặc định không phải là biến dùng chung để mọi class sửa cấu hình qua `array[0] = ...`; annotation biểu diễn metadata khai báo. Không nên xây dựng logic dựa vào việc sửa mảng lấy ra từ Reflection.

## 4. Phần tử có kiểu annotation lồng nhau

Một annotation type có thể dùng **một annotation type khác** làm kiểu của element.

~~~java
@interface Author {
    String name();
    int priority() default 1;
}

@interface DocumentInfo {
    Author reviewer() default @Author(name = "system");
}
~~~

`DocumentInfo.reviewer()` trả một annotation kiểu `Author`. Giá trị mặc định của nó được viết **trực tiếp dưới dạng annotation literal** `@Author(name = "system")`. Bên trong `@Author`, element `priority()` không được truyền nên lấy mặc định `1`.

Cách sử dụng:

~~~java
@DocumentInfo
class DefaultDocument {}

@DocumentInfo(reviewer = @Author(name = "alice", priority = 3))
class ReviewedDocument {}
~~~

Với `DefaultDocument`, `reviewer().name()` trả `"system"`; với `ReviewedDocument`, trả `"alice"` và `reviewer().priority()` trả `3`.

Hai annotation có quan hệ **chứa giá trị metadata**, không phải quan hệ class kế thừa. “Annotation lồng nhau” trong bài này là *giá trị một element có kiểu annotation*, khác với việc khai báo một annotation type bên trong thân một class hoặc thân một annotation type.

Lưu ý: nếu `Author.name()` bắt buộc, giá trị mặc định `@Author` trống là **không hợp lệ**; phải truyền `name` hoặc sửa `Author` để `name()` cũng có mặc định. Các mặc định trong annotation lồng nhau được áp dụng độc lập theo từng annotation type.

### 4.1. Mảng annotation lồng nhau

Element còn có thể trả **mảng các annotation**:

~~~java
@interface Rule {
    String code();
    int priority() default 1;
}

@interface RuleSet {
    Rule[] rules() default {
        @Rule(code = "syntax"),
        @Rule(code = "security", priority = 2)
    };
}
~~~

`RuleSet.rules()` trả một mảng `Rule[]` có hai phần tử. Mỗi phần tử của mảng là một annotation instance chứa metadata của `Rule`; không phải một đối tượng `new Rule(...)`.

Mảng rỗng cũng hợp lệ:

~~~java
@interface EmptyRuleSet {
    Rule[] rules() default {};
}
~~~

Nếu muốn có **một annotation duy nhất** làm mặc định cho `Rule[]`, cú pháp mảng được viết rõ:

~~~java
@interface OneRuleSet {
    Rule[] rules() default {@Rule(code = "syntax")};
}
~~~

Ngoài ra Java cho phép dạng rút gọn một phần tử khi hợp lệ:

~~~java
@interface ShortRuleSet {
    Rule[] rules() default @Rule(code = "syntax");
}
~~~

Hai dạng trên biểu diễn cùng một mảng một annotation. Dùng dấu `{}` trong giáo trình thường dễ đọc hơn, nhất là khi số phần tử có thể tăng.

### 4.2. Cách truyền mảng annotation tại vị trí sử dụng

~~~java
@RuleSet(rules = {
    @Rule(code = "cache"),
    @Rule(code = "database", priority = 4)
})
class ServiceRules {}

@RuleSet(rules = {})
class NoRules {}

@RuleSet(rules = @Rule(code = "single"))
class OneServiceRule {}
~~~

Dạng `rules = @Rule(...)` là rút gọn cho mảng một phần tử. `rules = {}` ghi đè danh sách mặc định thành rỗng. Nếu không viết `rules`, Java dùng mảng được khai báo trong `RuleSet`.

Một giá trị annotation lồng nhau là cấu trúc khai báo tĩnh, không phải một object constructor tùy ý. Java không cho phép `new Rule(...)` vì annotation type không phải class tạo đối tượng bằng constructor thông thường.

## 5. Ví dụ Java 17+ chạy độc lập: từ default đến Reflection

Tạo file **`AnnotationDefaultArraysDemo.java`** với nội dung đầy đủ sau. Ví dụ có hai annotation type, hai class dùng annotation và một class public chứa `main`.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Label {
    String name();
    int priority() default 1;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LessonConfig {
    String[] topics() default {"java", "core"};
    String[] aliases() default {};
    Label reviewer() default @Label(name = "default-reviewer");
    Label[] checks() default {
        @Label(name = "syntax"),
        @Label(name = "runtime", priority = 2)
    };
}

@LessonConfig
class DefaultLesson {}

@LessonConfig(
    topics = {"annotation"},
    aliases = "ann",
    reviewer = @Label(name = "alice", priority = 3),
    checks = {@Label(name = "custom")}
)
class CustomLesson {}

public class AnnotationDefaultArraysDemo {
    private static void show(Class<?> type) {
        LessonConfig config = type.getAnnotation(LessonConfig.class);

        System.out.println(type.getSimpleName());
        System.out.println("topics=" + Arrays.toString(config.topics()));
        System.out.println("aliases=" + Arrays.toString(config.aliases()));
        System.out.println("reviewer=" + config.reviewer().name()
                + ":" + config.reviewer().priority());
        System.out.println("checks=" + Arrays.stream(config.checks())
                .map(label -> label.name() + ":" + label.priority())
                .collect(Collectors.joining(", ")));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show(DefaultLesson.class);
        show(CustomLesson.class);

        Object defaultAliases = LessonConfig.class
                .getDeclaredMethod("aliases")
                .getDefaultValue();
        System.out.println("default aliases="
                + Arrays.toString((String[]) defaultAliases));
    }
}
~~~

Mở terminal trong thư mục chứa file và chạy:

~~~bash
javac -encoding UTF-8 AnnotationDefaultArraysDemo.java
java AnnotationDefaultArraysDemo
~~~

Stdout chính xác:

~~~text
DefaultLesson
topics=[java, core]
aliases=[]
reviewer=default-reviewer:1
checks=syntax:1, runtime:2
CustomLesson
topics=[annotation]
aliases=[ann]
reviewer=alice:3
checks=custom:1
default aliases=[]
~~~

Có thể đọc và kiểm chứng theo từng bước:

1. `@LessonConfig` trên `DefaultLesson` không truyền element nào. Cả `topics`, `aliases`, `reviewer`, `checks` đều có mặc định nên annotation hợp lệ.
2. Mặc định `topics` là mảng hai chuỗi; `aliases` là mảng rỗng. `Arrays.toString(...)` làm nội dung mảng hiện ra rõ ràng.
3. `reviewer` mặc định chứa `@Label(name = "default-reviewer")`. Vì `Label.priority() default 1`, kết quả là `default-reviewer:1`.
4. `checks` mặc định gồm hai annotation; cái thứ nhất nhận priority `1` từ `Label`, cái thứ hai đã chỉ định `2`.
5. `CustomLesson` cung cấp trực tiếp bốn element, nên chúng thay thế từng mặc định tương ứng. `aliases = "ann"` được chuyển thành một mảng một chuỗi.
6. `checks = {@Label(name = "custom")}` chứa một annotation, trong đó `priority` lấy mặc định `1` của `Label`.
7. Phần cuối đọc **mặc định khai báo trên annotation type** bằng `Method.getDefaultValue()`. Vì `aliases()` có kiểu `String[]`, ta ép kiểu `(String[])` rồi hiển thị mảng rỗng.

Ở đây hai việc khác nhau đều trả về giá trị:

- `DefaultLesson.class.getAnnotation(LessonConfig.class).aliases()` lấy **giá trị hiệu lực** của annotation đang gắn vào một class: giá trị khai báo tường minh nếu có, ngược lại là mặc định.
- `LessonConfig.class.getDeclaredMethod("aliases").getDefaultValue()` lấy **mặc định được định nghĩa trên chính annotation type**, bất kể class nào sử dụng annotation đó. Phương thức này trả `null` nếu element **không khai báo mặc định**; đó là cách biểu diễn của API Reflection, **không có nghĩa element cho phép giá trị `null`**.

`@Retention(RUNTIME)` được đặt lên `LessonConfig` và `Label` để ví dụ có thể đọc bằng Reflection. `@Target(TYPE)` cho phép dùng annotation trên khai báo class. Nếu bỏ retention, mặc định là `CLASS` và lời gọi `getAnnotation(...)` lúc runtime không còn thấy annotation như trong ví dụ.

## 6. Mặc định được lưu và áp dụng vào lúc nào?

Theo Java Language Specification, giá trị mặc định của element được liên kết với **định nghĩa annotation type**, và được áp dụng khi annotation được đọc; nó không được chép thành giá trị tường minh vào mọi nơi sử dụng annotation. Đây là chi tiết có tác động khi cập nhật thư viện annotation.

Ví dụ giả sử bản đầu:

~~~java
@interface Features {
    String[] value() default {"read"};
}

@Features
class AppA {}

@Features({})
class AppB {}
~~~

Nếu sau đó bạn thay mặc định trong `Features` thành `{"read", "write"}` và cung cấp bản annotation type mới phù hợp lúc runtime:

- `AppA` đã bỏ qua `value`, nên khi đọc với định nghĩa mới có thể nhận `["read", "write"]`, dù bản thân class `AppA` chưa được biên dịch lại.
- `AppB` đã khai báo trực tiếp mảng rỗng, nên khi đọc vẫn nhận mảng rỗng.

Điều này không đồng nghĩa mọi kiểu thay đổi annotation là an toàn về tương thích nhị phân. Xóa/đổi tên element, đổi kiểu trả về, hoặc phá vỡ các định nghĩa annotation lồng có thể làm mã cũ không còn đọc được như dự định. Khi tiến hóa API, kiểm tra đồng bộ compiler, runtime classpath và consumer của metadata.

Nếu bạn cần biết **có default được khai báo hay không**, dùng `getDefaultValue()` trên method mô tả element; nếu chỉ cần giá trị cuối cùng của một annotation cụ thể, gọi trực tiếp element method trên annotation instance.

## 7. Quy tắc kiểu và những cú pháp không hợp lệ

Annotation element không giống một thuộc tính object tùy ý. Những ví dụ **sai, chỉ để phân tích lỗi**:

~~~java
@interface WrongDefaults {
    String[] labels() default null;                 // Sai: không cho null.
    String[] names() default new String[]{"a"};     // Sai: new array runtime.
    java.util.List<String> tags() default {};       // Sai: List không là kiểu element hợp lệ.
    String[][] matrix() default {};                  // Sai: mảng nhiều chiều.
    String[] dynamic() default {System.getenv("X")}; // Sai: không là constant expression.
}
~~~

Không đưa các đoạn sai cú pháp trên vào file chương trình chính. Những cách thay thế đúng:

~~~java
@interface ValidDefaults {
    String[] labels() default {};
    String[] names() default {"a"};
    Class<?>[] types() default {String.class};
    int[] levels() default {1, 2, 3};
}
~~~

Với element chứa annotation, các giá trị phải là annotation literal có kiểu khớp:

~~~java
@interface Owner {
    String id();
    boolean active() default true;
}

@interface Ownership {
    Owner owner() default @Owner(id = "platform");
    Owner[] backups() default {
        @Owner(id = "alice"),
        @Owner(id = "bob", active = false)
    };
}
~~~

`@Owner(id = "platform")` hợp lệ vì `Owner.id()` được truyền, còn `Owner.active()` đã có mặc định. `owner() default null`, `owner() default new Owner(...)` hoặc `owner() default @Owner` (khi `id()` vẫn bắt buộc) đều không hợp lệ.

Các kiểu element mảng khác như `enum[]`, `Class<?>[]` và `int[]` có thể có mặc định nếu dùng các giá trị phù hợp với quy tắc annotation của Java. Đối với `String[]`, giá trị chuỗi có thể là literal hoặc biểu thức hằng chuỗi lúc biên dịch; gọi method runtime không được tính.

## 8. Lỗi dễ mắc khi đọc và thiết kế annotation

**Nhầm 1: `default {}` có nghĩa không có giá trị.** Thực chất đó là **một giá trị hợp lệ**: mảng rỗng. Người dùng có thể cố ý truyền `{}` để ghi đè mặc định khác rỗng.

**Nhầm 2: `@Nested` luôn hợp lệ dù nested annotation có element bắt buộc.** Ví dụ `@Owner` chỉ hợp lệ nếu `Owner.id()` được truyền hoặc có mặc định. Mặc định của annotation bên ngoài không tự cung cấp giá trị cho element bắt buộc bên trong.

**Nhầm 3: Phải dùng `new` để tạo nested annotation.** Trong khai báo annotation, dùng `@Owner(id = "...")`; giá trị không được tạo qua constructor như class thông thường.

**Nhầm 4: `@Label(...)` và `{@Label(...)}` có kiểu như nhau ở mọi nơi.** Giá trị đơn hợp với element kiểu `Label`; mảng phù hợp element kiểu `Label[]`, và dạng đơn có thể là cú pháp viết ngắn của mảng một phần tử khi quy tắc cho phép. Đối chiếu kiểu khai báo element trước khi chọn cú pháp.

**Nhầm 5: Cho `null` làm default để đánh dấu không có annotation con.** Java không cho annotation element mang `null`. Có thể cân nhắc mảng rỗng `Owner[] owners() default {}` để biểu diễn không có owner, hoặc một annotation sentinel được định nghĩa rõ về ý nghĩa; chọn phương án theo hợp đồng API.

**Nhầm 6: Tưởng default tại annotation type chỉ có tác dụng vào lúc biên dịch nơi sử dụng.** Giá trị mặc định được áp dụng khi đọc. Việc thay đổi mặc định trong phiên bản thư viện có thể đổi hành vi của annotation cũ chưa ghi giá trị tường minh.

**Nhầm 7: Truy vấn Reflection nhưng nhận `null` rồi kết luận mặc định rỗng.** `getAnnotation(...)` trả `null` nếu **không có annotation** phù hợp; còn `getDefaultValue()` trả `null` nếu **element không có mặc định**. Riêng một mảng có mặc định rỗng khi đọc đúng API là một mảng độ dài 0, khác `null`.

**Nhầm 8: Coi mảng annotation là cấu hình có thể sửa trực tiếp trong runtime.** Annotation được thiết kế như metadata khai báo. Không dùng phương thức trả mảng để cập nhật cấu hình annotation; thiết kế dữ liệu runtime bằng object/config riêng khi cần thay đổi.

**Nhầm 9: Quên retention của annotation cần đọc.** Reflection thông thường chỉ nhìn thấy annotation có `@Retention(RUNTIME)`. Annotation lồng trong ví dụ cũng khai báo `RUNTIME` nhằm minh họa rõ ràng đường đi của Reflection.

## 9. Thực hành theo thứ tự tăng dần

1. Tạo `@interface FileInfo` có `String[] formats() default {}`; gắn vào ba class với `@FileInfo`, `@FileInfo(formats = {"json", "xml"})` và `@FileInfo(formats = "csv")`. In các mảng hiệu lực bằng `Arrays.toString`.
2. Đổi mặc định `formats` thành `{"txt"}`, so sánh trường hợp bỏ qua element với trường hợp truyền `formats = {}`. Giải thích khác biệt bằng nguồn gốc giá trị.
3. Định nghĩa `@interface Permission { String name(); boolean required() default true; }`. Khai báo `Permission permission() default @Permission(name = "read");` ở annotation khác. Đọc cả `name` lẫn `required`.
4. Thay element trên thành `Permission[] permissions() default {@Permission(name = "read"), @Permission(name = "write", required = false)};`. Dùng Reflection in danh sách theo thứ tự và thử ghi đè bằng mảng rỗng.
5. Trong ví dụ `AnnotationDefaultArraysDemo`, thêm `int[] ports() default {8080, 8081};` vào `LessonConfig`. In mặc định, rồi ghi đè `ports = {9000}` ở `CustomLesson`.
6. Dùng `LessonConfig.class.getDeclaredMethod("topics").getDefaultValue()`, `getDeclaredMethod("reviewer").getDefaultValue()` và `getDeclaredMethod("checks").getDefaultValue()`. Xác minh kiểu trả về tương ứng là `String[]`, annotation `Label` và `Label[]`.
7. Thử bỏ `default` khỏi `Label.priority()`, dự đoán những chỗ `@Label(...)` nào cần bổ sung `priority`, rồi biên dịch để kiểm tra.
8. Viết ví dụ sai có `default null` và `default new String[]{"x"}`; đọc thông báo của `javac` và giải thích bằng quy tắc `ElementValue` thay vì chỉ học thuộc một dòng lỗi.

## 10. Checklist trước khi học tiếp

| Câu hỏi | Bạn cần trả lời được |
| --- | --- |
| `default {}` biểu diễn điều gì? | Mảng hợp lệ có 0 phần tử |
| Có thể truyền một chuỗi cho `String[]` không? | Có, dưới dạng rút gọn mảng một phần tử ở vị trí element |
| Default của element kiểu annotation viết thế nào? | `default @Nested(...);` |
| Default của element kiểu mảng annotation viết thế nào? | `default {@Nested(...), @Nested(...)};` hoặc `default {};` |
| Nested annotation có element bắt buộc thì sao? | Phải cung cấp element đó trong literal, trừ khi nó có mặc định |
| Có thể dùng `null` hay `new` trong default không? | Không |
| Làm sao xem default bằng Reflection? | `AnnotationType.class.getDeclaredMethod("element").getDefaultValue()` |
| Giá trị tại chỗ sử dụng và default ưu tiên ra sao? | Giá trị tường minh ưu tiên; nếu thiếu thì áp dụng default khi đọc |

**Điểm cốt lõi:** annotation cho phép biểu diễn metadata phức hợp bằng mảng và annotation lồng nhau mà không cần khởi tạo object thủ công. `default` mô tả giá trị dự phòng ở **annotation type**; khi sử dụng, mỗi element có thể giữ dự phòng hoặc ghi đè tường minh. Hiểu điều này giúp đọc chính xác cấu hình annotation trong Java Core và các thư viện Java dựa trên annotation.

## Tài liệu tham khảo

- [Java Language Specification 17, `9.6.1–9.6.2 — Annotation interfaces và Defaults](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2).
- [Java Language Specification 17, `9.7.1–9.7.3 — Annotation values, marker và single-element shorthand](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1).
- [Java SE 17, Method.getDefaultValue()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()).
