# Hằng số, enum và kiểu thành viên bên trong `@interface` của Java

Một kiểu annotation được khai báo bằng `@interface` là một **dạng đặc biệt của interface**. Bên trong phần thân, ngoài các phương thức khai báo *annotation element* như `String name();`, Java còn cho phép khai báo **hằng số, enum và các kiểu thành viên** (`class`, `interface`, annotation lồng nhau). Chúng giúp nhóm các tên, giá trị quy ước và kiểu dữ liệu liên quan ngay trong định nghĩa annotation.

Điểm cần nắm trước: **không phải mọi thành viên trong `@interface` đều là element có thể truyền ở `@Annotation(...)`**. Chỉ những phương thức khai báo element mới trở thành các cặp tên–giá trị khi sử dụng annotation. Hằng số và kiểu lồng nhau là thành viên của **kiểu Java**, hỗ trợ đặt tên, tổ chức và khai báo element.

## 1. Những thành phần có thể khai báo trong `@interface`

Một cấu trúc hợp lệ:

```java
@interface ExportRule {
    int DEFAULT_LIMIT = 25;           // Hằng số (field)
    String DEFAULT_OWNER = "platform";

    enum Format { CSV, JSON }          // Kiểu enum lồng nhau

    @interface Reviewer {             // Kiểu annotation lồng nhau
        String value();
    }

    Format format() default Format.JSON;                    // Element
    int limit() default DEFAULT_LIMIT;                      // Element
    Reviewer reviewer() default @Reviewer(DEFAULT_OWNER);   // Element
}
```

Ở đây:

| Khai báo | Vai trò | Dùng trong `@ExportRule(...)` như tên một element? |
| --- | --- | --- |
| `DEFAULT_LIMIT`, `DEFAULT_OWNER` | Field hằng số của `ExportRule` | **Không**: đó là field, không phải element. |
| `enum Format` | Định nghĩa kiểu enum, cung cấp `CSV`/`JSON` | **Không**: là tên kiểu dùng làm kiểu trả về của element `format()`. |
| `@interface Reviewer` | Định nghĩa một kiểu annotation khác nằm trong `ExportRule` | **Không**: là kiểu dữ liệu của element `reviewer()`. |
| `format()`, `limit()`, `reviewer()` | Khai báo element | **Có**: khi sử dụng annotation có thể viết `format = ...`, `limit = ...`, `reviewer = ...`. |

Cú pháp `@interface` không làm cho field hay enum trở thành cấu hình runtime tự động. Ý nghĩa của dữ liệu chỉ xuất hiện khi annotation processor hoặc mã ứng dụng đọc và xử lý nó.

## 2. Hằng số trong annotation: mặc định `public static final`

Một field được khai báo trực tiếp trong `@interface` tuân theo quy tắc field của interface: **ngầm định là `public static final`**. Có thể viết đầy đủ, nhưng không cần.

```java
@interface Limits {
    int DEFAULT_RETRIES = 3;
    String PREFIX = "api-";

    int retries() default DEFAULT_RETRIES;
    String label() default PREFIX + "default";
}
```

Trong ví dụ này:

- `Limits.DEFAULT_RETRIES` là **field** truy cập thông qua tên kiểu.
- `retries()` là **annotation element**; khi đọc annotation, phần tử đó có giá trị mặc định `3`.
- `PREFIX` là chuỗi hằng và `PREFIX + "default"` là biểu thức hằng hợp lệ cho element kiểu `String`.

Cách viết `int DEFAULT_RETRIES = 3;` có ý nghĩa như `public static final int DEFAULT_RETRIES = 3;`. Đây là điểm giống interface thông thường.

Khi áp dụng annotation:

```java
@Limits(retries = Limits.DEFAULT_RETRIES, label = Limits.PREFIX + "user")
class RetryConfig {
}
```

Cả hai giá trị hợp lệ vì chúng là **biểu thức hằng tại thời điểm biên dịch**. Ngược lại, `@Limits(DEFAULT_RETRIES = 5)` là sai: field `DEFAULT_RETRIES` không phải element có tên `DEFAULT_RETRIES()`.

### Field `final` chưa chắc là *constant variable*

Java chỉ xem một field là *constant variable* khi nó là `final`, thuộc kiểu nguyên thủy hoặc `String`, và được khởi tạo bằng **constant expression**. Vì vậy không phải biểu thức khởi tạo nào của field `public static final` cũng dùng được làm giá trị annotation.

```java
@interface Port {
    int FIXED = 8080;                     // Constant variable
    int DYNAMIC = Integer.parseInt("8080"); // final, nhưng không là constant variable

    int value() default FIXED;            // Hợp lệ
    // int other() default DYNAMIC;       // Lỗi biên dịch
}
```

Các dòng có chú thích lỗi ở đây là minh họa; code bỏ phần lỗi vẫn là cú pháp hợp lệ. `DYNAMIC` được tính nhờ lời gọi phương thức trong khởi tạo, nên không phải biểu thức hằng compile time, dù field không thể được gán lại.

Mảng cũng là đối tượng tham chiếu: field `String[] NAMES = {"a", "b"};` có thể tồn tại trong interface và không cho gán lại tham chiếu `NAMES`, nhưng phần tử mảng vẫn có thể thay đổi; bản thân field **không phải** *constant variable*. Với element `String[]`, hãy viết `default {"a", "b"}` trực tiếp, thay vì `default NAMES`.

### Vì sao không dùng `private` hoặc instance field?

```java
@interface WrongFields {
    // private int secret = 1;  // Sai: interface field không được private
    // int count;               // Sai: field interface phải có initializer
}
```

Field trong annotation không thể là biến trạng thái thay đổi theo từng instance. Một annotation được dùng để mô tả metadata cố định ở mức khai báo, không phải một đối tượng cấu hình có state.

## 3. Enum lồng nhau: mô hình hóa giá trị hữu hạn

Một enum lồng trong `@interface` hữu ích khi element chỉ nên nhận một số trạng thái đã biết. Thay vì cho người dùng truyền chuỗi bất kỳ như `"CSV"`/`"JSON"`, khai báo một enum:

```java
@interface Serialization {
    enum Format {
        CSV, JSON, XML
    }

    Format value() default Format.JSON;
}
```

Dùng từ nơi khác:

```java
@Serialization(Serialization.Format.CSV)
class CsvDocument {
}
```

Ở đây `Serialization.Format` là **kiểu enum thành viên** được khai báo trong `Serialization`, còn `Format.CSV` là một hằng enum. Vì element tên `value`, cú pháp rút gọn `@Serialization(...)` được phép. Viết đầy đủ cũng đúng:

```java
@Serialization(value = Serialization.Format.CSV)
class AnotherCsvDocument {
}
```

Một số điều cần nhớ:

1. `enum Format` nằm trong annotation nhưng vẫn là **một kiểu enum Java**, được truy cập qua `Serialization.Format`.
2. Kiểu enum thành viên của interface ngầm định `public static`: không cần instance của annotation để truy cập enum.
3. Element `Format value()` hợp lệ vì Java cho phép enum là kiểu trả về của annotation element.
4. Giá trị truyền cho element enum phải là **enum constant**, chẳng hạn `Serialization.Format.CSV`. Không dùng chuỗi `"CSV"` hoặc biến enum tính ở runtime.
5. Có thể đặt enum ở cấp package hoặc file riêng nếu nhiều annotation cùng sử dụng; lồng enum thuận tiện khi nó chỉ có ý nghĩa trong một annotation.

Lưu ý: `Serialization.Format.CSV` là giá trị enum; `Serialization.Format` là tên kiểu. Không thể gán `Format.class` cho element yêu cầu `Format`, vì `Class` và `enum` là hai kiểu khác nhau.

## 4. Kiểu annotation lồng nhau: mô tả dữ liệu có cấu trúc

Nếu một element cần nhiều thuộc tính có liên quan, có thể tạo **annotation type lồng nhau** rồi dùng nó làm kiểu trả về của element bên ngoài.

```java
@interface AuditSpec {
    @interface Reviewer {
        String name();
        boolean required() default true;
    }

    Reviewer reviewer();
}
```

Sử dụng:

```java
@AuditSpec(
    reviewer = @AuditSpec.Reviewer(
        name = "qa-team",
        required = true
    )
)
class AuditedService {
}
```

`@AuditSpec.Reviewer(...)` là **annotation literal dùng làm giá trị**, không phải lời gọi constructor `new Reviewer(...)`. Trình biên dịch kiểm tra `name` có kiểu `String` và `required` có kiểu `boolean`, giống như khi dùng annotation độc lập.

Kiểu `Reviewer` lồng là một **member annotation interface**; theo quy tắc member type trong interface, nó ngầm định `public static`. Có thể truy cập bằng tên đầy đủ `AuditSpec.Reviewer`.

Nếu cần một tập nhiều reviewer, khai báo `Reviewer[] reviewers();` rồi sử dụng danh sách annotation literal trong `{ ... }`. Java cho phép element kiểu annotation và mảng **một chiều** của annotation.

## 5. Ví dụ hoàn chỉnh: hằng số + enum + annotation lồng nhau

Ví dụ sau được viết thành **một chương trình Java 17+ hoàn chỉnh**. Nó khai báo một annotation đánh dấu cách xuất dữ liệu, chứa hằng số, enum định dạng và một kiểu annotation mô tả người xét duyệt.

Tạo file **`AnnotationMemberKindsDemo.java`** với nội dung:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ExportRule {
    int DEFAULT_BATCH_SIZE = 25;
    String DEFAULT_TEAM = "platform";

    enum Format {
        CSV, JSON
    }

    @Retention(RetentionPolicy.RUNTIME)
    @interface Reviewer {
        String value();
        boolean required() default true;
    }

    Format format() default Format.JSON;
    int batchSize() default DEFAULT_BATCH_SIZE;
    Reviewer reviewer() default @Reviewer(DEFAULT_TEAM);
}

@ExportRule(
    format = ExportRule.Format.CSV,
    reviewer = @ExportRule.Reviewer("billing")
)
class PaymentExport {
}

public class AnnotationMemberKindsDemo {
    public static void main(String[] args) {
        ExportRule rule = PaymentExport.class.getAnnotation(ExportRule.class);

        System.out.println("format=" + rule.format());
        System.out.println("batchSize=" + rule.batchSize());
        System.out.println("reviewer=" + rule.reviewer().value());
        System.out.println("required=" + rule.reviewer().required());
        System.out.println("constant=" + ExportRule.DEFAULT_BATCH_SIZE);
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 AnnotationMemberKindsDemo.java
java AnnotationMemberKindsDemo
```

Kết quả `stdout`:

```text
format=CSV
batchSize=25
reviewer=billing
required=true
constant=25
```

Từng giá trị đến từ đâu?

- `format=CSV`: chỗ sử dụng đã ghi `format = ExportRule.Format.CSV`, nên **ghi đè** mặc định `Format.JSON`.
- `batchSize=25`: không truyền `batchSize`, Java sử dụng `DEFAULT_BATCH_SIZE` làm giá trị mặc định của element.
- `reviewer=billing`: element `reviewer()` chứa một annotation `@ExportRule.Reviewer("billing")` lồng bên trong. `value()` của annotation này trả về `"billing"`.
- `required=true`: trong `Reviewer`, element `required()` có `default true`; bên ngoài không truyền giá trị khác.
- `constant=25`: `ExportRule.DEFAULT_BATCH_SIZE` là cách đọc **field hằng số**, khác với `rule.batchSize()` là cách đọc giá trị của **annotation element**.

`@Retention(RUNTIME)` ở annotation ngoài giúp chương trình truy xuất qua reflection. Việc khai báo enum hoặc hằng số lồng trong `@interface` không làm annotation tự động có retention `RUNTIME`; mỗi kiểu annotation có retention riêng và phải được chỉ rõ khi cần.

Chương trình này minh họa metadata; Java không thực hiện việc xuất CSV hay phê duyệt bởi `"billing"`. Muốn có hành vi đó, chương trình phải tự đọc `ExportRule` rồi xử lý tương ứng.

## 6. Class và interface thành viên khác có thể xuất hiện bên trong `@interface`

Bên cạnh enum và annotation lồng nhau, cú pháp Java cũng cho phép **class và interface thành viên** ngay trong `@interface`. Ví dụ minh họa độc lập:

```java
@interface DocumentHint {
    String NAME = "document";

    class TextUtil {
        static String trim(String input) {
            return input.trim();
        }
    }

    interface Formatter {
        String format(String value);
    }

    Class<? extends Formatter> formatter();
}
```

`DocumentHint.TextUtil` và `DocumentHint.Formatter` là **kiểu thành viên**, ngầm định `public static` do được khai báo trong interface. Để dùng `DocumentHint.TextUtil.trim(" x ")` từ bên ngoài package, phương thức `trim` cần được khai báo `public`; ở ví dụ này nó có quyền truy cập mặc định của package. Cú pháp khai báo kiểu thành viên hoàn toàn khác cú pháp khai báo annotation element.

Phần cuối `Class<? extends Formatter> formatter();` **hợp lệ**: kiểu của element là `Class` có generic bound, không phải là chính `Formatter`. Chỉ những kiểu sau mới được dùng làm kiểu trả về của element annotation: kiểu nguyên thủy, `String`, `Class` (kể cả `Class<?...>`), enum, annotation và mảng một chiều của các kiểu đó.

Vì vậy, các khai báo sau **sai** nếu đặt trực tiếp như element của annotation:

```java
// Formatter formatter(); // Sai: Formatter là interface thông thường
// TextUtil helper();      // Sai: TextUtil là class thông thường
// java.util.List<String> names(); // Sai: List không phải element type hợp lệ
```

Còn `String[] names() default {};` là hợp lệ, miễn là bạn đặt nó bên trong một kiểu `@interface`.

### Quy tắc truy cập

Theo Java Language Specification, member class và member interface khai báo trong interface ngầm định `public static`. Do đó:

- Có thể dùng `OuterAnnotation.NestedType` từ nơi khác nếu các ràng buộc truy cập còn lại cho phép.
- Không thể khai báo `private class Helper` hay `protected interface Formatter` trực tiếp ở cấp member của annotation/interface.
- Enum và nested annotation cũng thuộc nhóm member type; chúng không phải object instance gắn riêng với một lần sử dụng annotation.
- Một annotation type lồng nhau có thể dùng làm **kiểu của element**; một interface/class tùy ý lồng bên trong thì không, trừ khi dùng `Class<?>` để lưu **class literal** của nó.

Không cần tạo đối tượng kiểu `OuterAnnotation` để truy cập những member này. Khi dùng hằng số hay enum từ chỗ khác, nên viết tên đủ ngữ cảnh (`ExportRule.Format.JSON`, `ExportRule.DEFAULT_BATCH_SIZE`) để tránh nhầm với phần tử cùng tên trong code khác.

## 7. Vì sao `@interface` không phải class để chứa logic?

Các phương thức khai báo trực tiếp trong `@interface` **phải là annotation element**. Chúng không có tham số, thân phương thức, type parameter hoặc `throws`; không thể khai báo `static`, `private` hay `default` method như interface thường.

```java
@interface ApiFlag {
    int priority() default 1;

    // int calculate(int input);  // Sai: element không nhận tham số
    // static int twice(int n) { return n * 2; } // Sai ở cấp @interface
}
```

Từ khóa `default` ở `int priority() default 1;` chỉ định **giá trị element mặc định**, không phải `default` method có thân hàm của interface.

Nếu thật sự cần logic hỗ trợ, đặt nó trong class thành viên, class ngoài hoặc processor, thay vì biến các element thành phương thức tính toán. Việc khai báo `class TextUtil` bên trong `@interface` là hợp lệ, song đối với ứng dụng lớn nên cân nhắc tách helper thành class riêng để tránh trộn công cụ xử lý với định nghĩa metadata.

Ngoài ra, annotation type không hỗ trợ tự do generic parameter như `@interface Box<T>` và không thể chọn `extends SomeInterface`; nó có các quy định riêng vì mọi annotation type đều liên hệ với `java.lang.annotation.Annotation`.

## 8. Những trường hợp sai dễ nhầm

| Mã hoặc suy nghĩ | Kết luận |
| --- | --- |
| `@ExportRule(DEFAULT_BATCH_SIZE = 50)` | **Sai**: tên field hằng số không phải tên element. Đúng là `batchSize = 50`. |
| `ExportRule.Format.CSV` là một `String` | **Sai**: đó là enum constant kiểu `ExportRule.Format`. |
| `format = "CSV"` cho element kiểu `Format` | **Sai kiểu**: dùng `format = ExportRule.Format.CSV`. |
| `reviewer = new ExportRule.Reviewer(...)` | **Sai**: annotation literal có cú pháp `@ExportRule.Reviewer(...)`, không được khởi tạo bằng `new`. |
| `int limit() default Math.max(1, 2);` | **Sai**: giá trị primitive cho element/default cần biểu thức hằng compile time. |
| `String[] tags() default TAGS;` với `TAGS` là field `String[]` | **Sai**: không dùng tham chiếu mảng như annotation element value; dùng `default {"a", "b"}`. |
| `Format format() default "JSON";` | **Sai kiểu**: default phải là enum constant như `Format.JSON`. |
| `Formatter formatter();` với `Formatter` là interface thường | **Sai kiểu element**: có thể dùng `Class<? extends Formatter> formatter();` nếu muốn lưu class literal. |
| `private static final int LIMIT = 3;` trong `@interface` | **Sai modifier**: field của interface luôn `public static final`, không cho `private`. |
| Dùng `@ExportRule` rồi Java tự xuất file CSV | **Sai**: annotation chỉ cung cấp metadata; cần code riêng thực thi nghiệp vụ. |

Một quy tắc kiểm tra thực dụng khi thiết kế annotation là xác định từng khai báo thuộc nhóm nào: **field hằng số**, **kiểu thành viên**, hay **element**. Sau đó đối chiếu kiểu của element với tập kiểu Java cho phép và kiểm tra giá trị dùng tại nơi khai báo annotation có hợp lệ khi biên dịch không.

## 9. Bài tập nhỏ tự kiểm tra

Cho định nghĩa:

```java
@interface Job {
    int DEFAULT_PRIORITY = 2;
    enum Mode { SYNC, ASYNC }

    Mode mode() default Mode.SYNC;
    int priority() default DEFAULT_PRIORITY;
}
```

Hãy xét các biểu thức:

1. `@Job` — **Hợp lệ**: cả hai element đều có default.
2. `@Job(mode = Job.Mode.ASYNC)` — **Hợp lệ**: dùng enum constant.
3. `@Job(priority = Job.DEFAULT_PRIORITY + 1)` — **Hợp lệ**: phép cộng trên constant variable tạo ra biểu thức hằng `3`.
4. `@Job(mode = "ASYNC")` — **Không hợp lệ**: chuỗi không phải enum.
5. `@Job(DEFAULT_PRIORITY = 10)` — **Không hợp lệ**: `DEFAULT_PRIORITY` là field, không phải element.

Bài tập cho thấy **hằng số cung cấp biểu thức compile time**, **enum giới hạn miền giá trị**, **kiểu annotation lồng nhau biểu diễn metadata có cấu trúc**, còn **element** là phần duy nhất nhận giá trị qua `@Job(...)` hoặc `@ExportRule(...)`.

Tài liệu chuẩn để tra cứu các quy tắc trên: [Java Language Specification 21 – §9.3 Field Declarations, §9.5 Member Class and Interface Declarations, §9.6 Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html). Đây là các quy tắc của ngôn ngữ Java, độc lập với Spring hay thư viện xử lý annotation cụ thể.
