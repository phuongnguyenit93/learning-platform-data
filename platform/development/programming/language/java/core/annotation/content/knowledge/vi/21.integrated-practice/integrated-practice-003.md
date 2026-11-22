# Thực hành tổng hợp: dùng @Repeatable để mô tả nhiều quy tắc kiểm tra trong Java

Một field có thể đồng thời cần nhiều điều kiện hợp lệ: không để trống, đạt độ dài tối thiểu, khớp biểu thức chính quy, thuộc một tập giá trị, v.v. Java hỗ trợ mô tả **nhiều lần cùng một annotation type** trên một khai báo thông qua `@Repeatable`. Nhờ đó, thay vì tạo một annotation mới cho mọi tổ hợp điều kiện, ta có thể định nghĩa một **mô hình quy tắc thống nhất** và gắn nhiều bản ghi cấu hình lên cùng một phần tử.

Ví dụ về ý tưởng:

```java
@Check(rule = Rule.NOT_BLANK, message = "must not be blank")
@Check(rule = Rule.MIN_LENGTH, min = 4, message = "at least 4 UTF-16 units")
public String username;
```

Đây là **đoạn khai báo minh họa**, cần định nghĩa `Check`, `Rule` và container phù hợp. Hai annotation đều thuộc cùng kiểu `Check`, nhưng **mỗi lần áp dụng mang thông số riêng**.

Bài thực hành này xây dựng trọn quy trình:

1. Thiết kế annotation quy tắc `@Check` và annotation chứa `@Checks`.
2. Khai báo metadata bằng `@Repeatable(Checks.class)`, `@Target(FIELD)` và `@Retention(RUNTIME)`.
3. Dùng nhiều `@Check` trên mỗi field của một form đăng ký.
4. Đọc đầy đủ quy tắc bằng `Field.getAnnotationsByType(Check.class)`.
5. Thực thi một validator đơn giản, thu thập tất cả lỗi và in kết quả được kiểm chứng bằng Java 17.
6. Phân tích giới hạn, cấu hình lỗi, thứ tự rule, retention, cách mở rộng và những điều cần test trước khi dùng thực tế.

**Phân biệt nguyên tắc cốt lõi:** `@Repeatable` chỉ cho phép và biểu diễn nhiều annotation cùng kiểu. **Nó không tự chạy validation**. Chính mã đọc annotation và triển khai các quy tắc mới quyết định một giá trị hợp lệ hay không.

## 1. Vì sao cần annotation lặp cho nhiều rule?

Giả sử thông tin người dùng cần đáp ứng:

- `username` không được rỗng hoặc chỉ chứa khoảng trắng.
- `username` có ít nhất bốn đơn vị mã UTF-16 theo `String.length()`.
- `pin` không được để trống.
- `pin` phải gồm đúng ba chữ số ASCII từ `0` tới `9`.

Có nhiều lựa chọn API. Một cách là gắn các annotation riêng:

```java
@NotBlank
@MinLength(4)
String username;
```

Đây chỉ là **minh họa ý tưởng**; `NotBlank` và `MinLength` không phải hai annotation chuẩn tự hoạt động trong Java core.

Một cách khác là mô tả điều kiện bằng một annotation chung:

```java
@Check(rule = Rule.NOT_BLANK, message = "required")
@Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
String username;
```

Cách sau có ưu điểm khi tất cả rule thực sự thuộc **một cơ chế xử lý thống nhất**: cùng chính sách báo lỗi, cùng processor/validator và cùng vòng đời metadata. Mỗi `@Check` là một cấu hình độc lập.

Tuy nhiên, không phải lúc nào repeatable annotation cũng tốt nhất. Nếu các quy tắc có ngữ nghĩa và đối số rất khác nhau, những annotation chuyên biệt như `@NotBlank`, `@Pattern`, `@Size` có thể rõ ràng và type-safe hơn. Bài tập chọn một annotation chung để tập trung vào **cơ chế repeatable và consumer**.

## 2. Thiết kế repeated annotation và container

Một annotation được phép xuất hiện nhiều lần khi nó có `@Repeatable(Container.class)`. Container được chỉ định phải có một element `value()` trả về **mảng của annotation được lặp**.

Ta sẽ dùng:

```java
enum Rule {
    NOT_BLANK,
    MIN_LENGTH,
    MATCHES
}

@Repeatable(Checks.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Check {
    Rule rule();
    int min() default 0;
    String regex() default "";
    String message();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Checks {
    Check[] value();
}
```

Đây là **khai báo minh họa rút gọn**, cần import `Repeatable`, `Retention`, `RetentionPolicy`, `Target` và `ElementType`. Chương trình đầy đủ kèm import sẽ nằm ở phần 5.

Các element của `Check`:

| Element | Ý nghĩa | Bắt buộc hay có default? |
| --- | --- | --- |
| `rule()` | Chọn loại kiểm tra `NOT_BLANK`, `MIN_LENGTH` hoặc `MATCHES` | Bắt buộc |
| `min()` | Độ dài tối thiểu khi dùng `MIN_LENGTH` | `default 0` |
| `regex()` | Biểu thức chính quy khi dùng `MATCHES` | `default ""` |
| `message()` | Thông báo khi vi phạm | Bắt buộc |

`@Checks` là **container annotation**, không phải tập quy tắc có thuật toán riêng. Compiler dùng nó khi cần biểu diễn nhiều `@Check` trên cùng phần tử.

### Quy định target và retention

Vì ví dụ xử lý annotation trực tiếp trên **field** bằng reflection runtime:

```java
@Repeatable(Checks.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Check { /* các element đã nêu */ }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Checks { /* Check[] value(); */ }
```

Đây là **cú pháp minh họa**, không dùng làm tệp chạy độc lập. Container và repeated annotation có cùng target `FIELD` và retention `RUNTIME`. Trong bài này không cần `@Inherited`, vì cơ chế `@Inherited` dành cho việc truy vấn annotation **trên class qua superclass**, không tự truyền field annotations.

Ta có thể thêm `@Documented` cho cả hai định nghĩa nếu muốn các annotation cấu hình xuất hiện trong tài liệu API. Nếu repeated type có `@Documented`, container **cũng phải** có `@Documented` theo quy tắc Java.

### Những điều kiện quan trọng của container

Theo Java Language Specification (JLS) §9.6.3, container cho annotation `T` phải đáp ứng:

1. Khai báo chính xác `T[] value();`.
2. Mọi element khác `value()` nếu tồn tại đều có default.
3. Retention của container không ngắn hơn retention của repeated annotation: `SOURCE ≤ CLASS ≤ RUNTIME`.
4. Target của container phải tương thích với target của repeated annotation theo quy tắc JLS. Nó không nhất thiết phải giống hệt trong mọi trường hợp, nhưng dùng cùng `FIELD` là lựa chọn rõ ràng ở đây.
5. Nếu repeated annotation có `@Documented`, container cũng có `@Documented`.
6. Nếu repeated annotation có `@Inherited`, container cũng có `@Inherited`.

Ví dụ **cố ý sai**, không biên dịch:

```java
@Repeatable(BadChecks.class)
@interface BadCheck {}

@interface BadChecks {
    String[] value(); // Sai: phải là BadCheck[].
}
```

Việc chỉ thêm `@Repeatable` không đủ nếu container không hợp lệ. Compiler sẽ từ chối việc định nghĩa lặp như vậy.

## 3. Khi viết hai @Check liên tiếp, compiler lưu gì?

Giả sử:

```java
@Check(rule = Rule.NOT_BLANK, message = "required")
@Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
String username;
```

Đây là **khai báo minh họa** dùng định nghĩa `Check` ở trên. Theo JLS §9.7.5, khi nhiều annotation của cùng một repeated type xuất hiện trong một ngữ cảnh hợp lệ, compiler có thể biểu diễn chúng như một **container annotation được khai báo ngầm**:

```java
@Checks({
    @Check(rule = Rule.NOT_BLANK, message = "required"),
    @Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
})
String username;
```

Hai cách thể hiện trên minh họa metadata tương đương cho những rule ấy. Trong trường hợp có nhiều repeated annotations liên tiếp, thứ tự từ trái qua phải được giữ trong mảng `value()` của container.

Một hệ quả bất ngờ cho reflection:

- `field.getDeclaredAnnotation(Check.class)` **không nhất thiết trả một rule** khi có hai lần `@Check`, bởi các rule có thể tồn tại **gián tiếp trong `@Checks`**.
- `field.getDeclaredAnnotation(Checks.class)` có thể trả container.
- `field.getDeclaredAnnotationsByType(Check.class)` và `field.getAnnotationsByType(Check.class)` được thiết kế để lấy **từng annotation `Check` bên trong container**, theo đúng thứ tự.
- Với **một** `@Check` gắn trực tiếp, `getDeclaredAnnotation(Check.class)` có thể trả ngay annotation đó.

Trong một validator cần xử lý **mọi quy tắc**, không dùng lời gọi trả **một** annotation như `getAnnotation(Check.class)` để cố thu thập đầy đủ cấu hình. Hãy ưu tiên API `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType`.

### Không trộn tùy tiện repeated type với container thủ công

Khi dùng cả `@Check` lẫn `@Checks` tại cùng vị trí, các trường hợp hợp lệ và không hợp lệ phụ thuộc số lượng và quy tắc JLS §9.7.5. Để API dễ hiểu, hãy chọn **một phong cách nhất quán**, thường là nhiều `@Check` liên tiếp, thay vì bắt người dùng viết container thủ công.

## 4. Thiết kế validator: từ annotation sang hành vi

Metadata không tự chạy. Để các `@Check` tạo ra giá trị thực, ta phải có consumer:

```text
Registration object
        |
        v
Reflection: lấy các Field được khai báo
        |
        v
Sắp xếp field để output dễ kiểm thử
        |
        v
getAnnotationsByType(Check.class)
        |
        v
Với mỗi @Check:
  NOT_BLANK  -> String.isBlank()
  MIN_LENGTH -> String.length() >= min
  MATCHES    -> Pattern.matches(regex, text)
        |
        v
Thu thập từng violation vào List<String>
        |
        v
Trả danh sách; caller quyết định hiển thị/xử lý
```

Một vài lựa chọn thiết kế được cố định cho ví dụ:

- Chỉ áp dụng trên **field kiểu `String`** và minh họa trên **một class form cụ thể**. Đây là hợp đồng của demo, không phải giới hạn bắt buộc của `@Repeatable`.
- `NOT_BLANK` coi `null` hoặc chuỗi toàn khoảng trắng theo `String.isBlank()` là không hợp lệ.
- `MIN_LENGTH` dùng `String.length()`, tức số **đơn vị mã UTF-16**, không nhất thiết bằng số ký tự người dùng cảm nhận (*grapheme clusters*). Với Unicode phức tạp có thể cần quy tắc khác.
- `MATCHES` dùng `Pattern.matches()`, yêu cầu **khớp toàn bộ chuỗi** theo biểu thức chính quy.
- Nếu giá trị `null`, cả ba loại kiểm tra trong demo đều báo vi phạm. Một framework có thể muốn quy tắc khác, chẳng hạn bỏ qua null cho `MIN_LENGTH` để `NOT_BLANK` chịu trách nhiệm riêng.
- Validator **thu thập mọi lỗi**, không dừng ở lỗi đầu tiên. Một field có thể tạo ra nhiều thông báo.
- Để stdout ổn định, demo **sắp xếp tên field** trước khi kiểm tra; trong thực tế không nên phụ thuộc thứ tự do `Class.getDeclaredFields()` trả về.

Những quyết định này phải được ghi rõ trong Javadoc của annotation và kiểm thử cùng consumer. Java không áp đặt cách hiểu của `NOT_BLANK` hay `MATCHES`.

## 5. Ví dụ Java 17 hoàn chỉnh: nhiều rule trên cùng field

Tạo đúng một file **`RepeatableRulesDemo.java`** với toàn bộ nội dung sau. Các class/enum/annotation type cần thiết đều nằm trong một tệp, và chỉ có một class `public` trùng tên file.

```java
import java.lang.annotation.*;
import java.lang.reflect.Field;
import java.util.*;
import java.util.regex.Pattern;

enum Rule { NOT_BLANK, MIN_LENGTH, MATCHES }

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@Repeatable(Checks.class)
@interface Check {
    Rule rule();
    int min() default 0;
    String regex() default "";
    String message();
}

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Checks {
    Check[] value();
}

class Registration {
    @Check(rule = Rule.NOT_BLANK, message = "must not be blank")
    @Check(rule = Rule.MIN_LENGTH, min = 4,
           message = "at least 4 UTF-16 units")
    public final String username;

    @Check(rule = Rule.NOT_BLANK, message = "must not be blank")
    @Check(rule = Rule.MATCHES, regex = "\\d{3}",
           message = "exactly 3 digits")
    public final String pin;

    Registration(String username, String pin) {
        this.username = username;
        this.pin = pin;
    }
}

public class RepeatableRulesDemo {
    static List<String> validate(Registration form)
            throws IllegalAccessException {
        List<String> problems = new ArrayList<>();
        Field[] fields = Registration.class.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));

        for (Field field : fields) {
            String value = (String) field.get(form);

            for (Check check : field.getAnnotationsByType(Check.class)) {
                boolean invalid = switch (check.rule()) {
                    case NOT_BLANK -> value == null || value.isBlank();
                    case MIN_LENGTH -> value == null || value.length() < check.min();
                    case MATCHES -> value == null ||
                            !Pattern.matches(check.regex(), value);
                };

                if (invalid) {
                    problems.add(field.getName() + ": " + check.message());
                }
            }
        }
        return problems;
    }

    public static void main(String[] args) throws Exception {
        Field field = Registration.class.getDeclaredField("username");

        System.out.println("rules-on-username=" +
                field.getAnnotationsByType(Check.class).length);
        System.out.println("direct-check=" +
                (field.getDeclaredAnnotation(Check.class) != null));
        System.out.println("container=" +
                (field.getDeclaredAnnotation(Checks.class) != null));

        System.out.println("invalid:");
        for (String message : validate(new Registration("ab", "9x"))) {
            System.out.println(message);
        }

        System.out.println("valid-errors=" +
                validate(new Registration("alice", "123")).size());
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 RepeatableRulesDemo.java
java RepeatableRulesDemo
```

Stdout **chính xác**, đã được đối chiếu bằng `javac` và `java`:

```text
rules-on-username=2
direct-check=false
container=true
invalid:
pin: exactly 3 digits
username: at least 4 UTF-16 units
valid-errors=0
```

### Giải thích kết quả

1. `rules-on-username=2`: field `username` có hai quy tắc `@Check`; `getAnnotationsByType(Check.class)` lấy được cả hai.
2. `direct-check=false`: khi có hai `@Check` cùng vị trí, compiler biểu diễn bằng container `@Checks`, nên một `Check` riêng lẻ không **directly present** trên field theo quy tắc của `getDeclaredAnnotation()`.
3. `container=true`: `@Checks` là annotation khai báo ngầm chứa hai rule.
4. `invalid:`: chuẩn bị in tất cả vi phạm của form có `username="ab"` và `pin="9x"`.
5. `pin: exactly 3 digits`: `"9x"` không khớp toàn bộ regex `\\d{3}`; nó vẫn không bị `NOT_BLANK` từ chối vì không rỗng.
6. `username: at least 4 UTF-16 units`: `"ab"` chỉ có `String.length()==2`, nhỏ hơn `min=4`; `NOT_BLANK` của field này vẫn đạt.
7. `valid-errors=0`: dữ liệu `("alice", "123")` thỏa các quy tắc nên danh sách lỗi rỗng.

Vì field được sắp xếp theo tên, `pin` được kiểm tra trước `username`. Trong mỗi field, các rule lặp được xử lý theo thứ tự khai báo mà reflection trả về từ container.

**Lưu ý:** các field trong demo là `public final String` để đơn giản hóa việc đọc bằng `Field.get(form)`. Trong dự án thực, field thường là `private`; framework phải có chiến lược truy cập hợp lệ, xét Java module access và security constraints, hoặc chuyển sang đọc property/getter với target `METHOD` nếu hợp đồng quy định như vậy.

### Kiểm tra thêm trường hợp rỗng

Nếu chạy cùng bộ kiểm tra với:

```java
validate(new Registration("", ""));
```

Đây là **biểu thức minh họa** đặt trong context của demo, chưa tự in kết quả. Danh sách lỗi sẽ bao gồm cả điều kiện `NOT_BLANK` và các điều kiện về độ dài/regex, vì validator hiện tại không bỏ qua những quy tắc khác sau khi gặp chuỗi rỗng.

Điều này cho thấy các kiểm tra là **độc lập**. Nếu sản phẩm chỉ muốn hiển thị một lỗi trên mỗi field, cần một chính sách điều phối riêng như **fail-fast per field** hoặc ưu tiên rule; đừng cho rằng `@Repeatable` sẽ chọn hộ lỗi đầu tiên.

## 6. So sánh cách lấy annotation từ Field

Giả sử `Registration.username` có hai `@Check` như trong demo.

| Reflection API | Kết quả và ý nghĩa |
| --- | --- |
| `field.getAnnotation(Check.class)` | `null` trong tình huống hai rule được container hóa |
| `field.getDeclaredAnnotation(Check.class)` | `null` vì không có một `Check` directly present |
| `field.getAnnotation(Checks.class)` | Container có chứa hai rule |
| `field.getAnnotationsByType(Check.class)` | Mảng hai `Check` sau khi mở container |
| `field.getDeclaredAnnotationsByType(Check.class)` | Cũng lấy hai rule ngay trên field trong demo |
| `field.getDeclaredAnnotations()` | Mảng các annotation trực tiếp, trong đó có `Checks` |

Với **field**, `getAnnotationsByType()` và `getDeclaredAnnotationsByType()` thường cho kết quả giống nhau về cơ chế kế thừa, vì `@Inherited` không sao chép annotation của field từ lớp cha sang field bị che ở lớp con. Tuy nhiên, một validator vẫn phải quyết định **tập field cần duyệt**: `getDeclaredFields()` chỉ trả field khai báo trực tiếp trên class đang xét, không tự trả field của toàn bộ superclass.

Một câu hỏi khác là “lấy annotation từ getter cùng tên có được không?”. Không tự động. Annotation trên **field** khác với annotation trên **method**. Nếu cần gắn trên getter, hãy hỗ trợ `@Target(METHOD)` và duyệt `Method` theo một hợp đồng rõ ràng.

### Phân biệt repeatable annotation và khai báo một container thủ công

```java
@Checks({
    @Check(rule = Rule.NOT_BLANK, message = "must not be blank"),
    @Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
})
String username;
```

Đây là **đoạn minh họa thay thế** cho hai `@Check` liên tiếp, với container được ghi tường minh. Người dùng annotation thường thích cú pháp lặp vì ngắn hơn; consumer nên dùng API hỗ trợ cả hình thức gián tiếp qua container.

Trong một hệ thống có compatibility với phiên bản thư viện cũ, việc thay API đọc `getAnnotation(Check.class)` sang `getAnnotationsByType(Check.class)` có thể là bước bắt buộc sau khi annotation trở nên repeatable.

## 7. Kiểm soát ý nghĩa và tính hợp lệ của cấu hình rule

Có `@Repeatable` không có nghĩa compiler xác thực mọi quan hệ giữa các element của `@Check`.

Ví dụ compiler chấp nhận các giá trị về mặt kiểu dữ liệu:

```java
@Check(rule = Rule.MIN_LENGTH, min = -5,
       message = "invalid length")
@Check(rule = Rule.MATCHES, regex = "[",
       message = "invalid regex")
String value;
```

Đây là **khai báo minh họa có cấu hình sai về nghiệp vụ**, nhưng các element đều đúng kiểu Java. Nó không được khuyến nghị sử dụng.

Các vấn đề:

- `MIN_LENGTH` với `min=-5` có ngữ nghĩa bất hợp lý cho độ dài.
- `MATCHES` với `regex="["` là regex không hợp lệ; `Pattern.matches()` có thể ném `PatternSyntaxException` ở runtime.
- `NOT_BLANK` mà lại điền `min` hoặc `regex` tạo cấu hình thừa, dễ gây hiểu nhầm.
- `message=""` có thể không giúp người dùng biết nguyên nhân lỗi.

Trong dự án thật, có hai lớp xác thực nên thực hiện:

1. **Xác thực định nghĩa annotation lúc biên dịch:** một annotation processor có thể đọc `@Check`, kiểm tra `min >= 0`, regex biên dịch được, combination giữa `rule` và các element tương ứng, rồi phát compiler diagnostic ngay tại khai báo sai.
2. **Xác thực cấu hình trước khi xử lý dữ liệu runtime:** framework tạo tập rule đã được kiểm tra, biên dịch sẵn `Pattern`, chỉ sau đó mới nhận dữ liệu người dùng. Tránh để lỗi metadata trộn với lỗi dữ liệu.

Cú pháp annotation chỉ ràng buộc những kiểu element Java cho phép; các giá trị mặc định không phải validation policy mặc định của compiler.

### Hãy ghi tài liệu cho quy tắc độ dài

Trong demo, `String.length()` đo **UTF-16 code units**. Với nhiều emoji/ký tự kết hợp dấu, số đơn vị mã có thể khác số ký tự người dùng nhìn thấy.

Nếu hợp đồng sản phẩm nói “ít nhất bốn ký tự hiển thị”, phải chọn cách đếm tương ứng (ví dụ theo Unicode grapheme clusters với công cụ phù hợp), không thể lấy `String.length()` rồi coi nó luôn là số ký tự hiển thị. Đây là quyết định của rule implementation, không liên quan trực tiếp tới `@Repeatable`.

### Không dùng annotation như một kho dữ liệu tùy ý

Java annotation elements chỉ nhận primitive, `String`, `Class`, enum, annotation hoặc mảng một chiều các kiểu được cho phép. Chúng không nhận tùy ý `List<Rule>`, lambda, mutable object hoặc `null`.

Vì vậy, để diễn đạt một rule phức tạp, hãy cân nhắc element thuộc những kiểu hợp lệ hoặc để annotation tham chiếu **một chính sách đã đăng ký** qua enum/class token/identifier. Tránh nhồi toàn bộ chương trình validator động vào annotation.

## 8. Thiết kế mở rộng: nên thêm Rule enum hay annotation type mới?

Mẫu `@Check(rule=Rule.X,...)` có giới hạn: các element `min()`, `regex()`, `message()` luôn tồn tại dù không phải rule nào cũng sử dụng chúng. Số lượng rule tăng có thể khiến annotation trở thành “cấu hình vạn năng” khó bảo trì.

Hai hướng mở rộng:

**Hướng A — giữ một repeated annotation với enum.** Hợp lý khi tất cả điều kiện thuộc cùng loại và tập tham số nhỏ. Consumer dùng `switch` cho từng `Rule`, và có thể có processor chặn tổ hợp cấu hình vô nghĩa.

**Hướng B — dùng nhiều annotation type chuyên biệt.** Chẳng hạn `@NotBlank`, `@MinLength(4)`, `@Matches("\\d{3}")`. Phù hợp khi mỗi quy tắc có element rất khác nhau và cần kiểm tra riêng. Mỗi annotation type cũng có thể được đánh dấu `@Repeatable` nếu một field cần nhiều lần cùng **một loại** rule, ví dụ nhiều pattern khác nhau.

Không cần biến mọi validation thành repeatable. Nếu field chỉ có **một** quy tắc `@NotBlank` và **một** quy tắc `@MinLength`, đó là hai kiểu annotation khác nhau; Java đã cho phép dùng cả hai cạnh nhau **không cần `@Repeatable`**. `@Repeatable` giải quyết riêng việc **lặp cùng annotation type** trên một declaration/type-use.

### Repeatable hay annotation chứa mảng?

Thay thế bằng một annotation duy nhất:

```java
// Khai báo minh họa cho một thiết kế khác:
@interface RuleSet {
    Rule[] value();
}
```

Một `@RuleSet({Rule.NOT_BLANK, Rule.MIN_LENGTH})` chỉ mang một danh sách enum, không tự mang `min=4` hoặc message riêng cho từng rule. Nếu mỗi rule cần các thông số độc lập, repeatable `@Check` hoặc mảng **nested annotations** thường tự nhiên hơn.

Nếu chỉ lưu tập cờ đơn giản không có tham số phụ, mảng enum có thể đơn giản và dễ bảo trì hơn container repeatable.

## 9. Quy tắc về thứ tự, trùng lặp và xung đột

Khi một phần tử có nhiều annotation, việc dùng thứ tự có thể mang ý nghĩa nghiệp vụ. Nhưng nên **quy định công khai** cách áp dụng rule.

- **Thứ tự annotation:** JLS định nghĩa thứ tự từ trái sang phải của các annotation được chứa trong container được tạo ngầm. Với `getAnnotationsByType()` trên field như demo, thứ tự rule được giữ tương ứng. Tuy vậy, vòng lặp qua `getDeclaredFields()` không cam kết thứ tự field; demo phải sắp xếp để có output ổn định.
- **Điều kiện AND:** ví dụ hiện tại yêu cầu mỗi rule đều hợp lệ; bất kỳ rule thất bại nào đều tạo một violation. Nếu nghiệp vụ muốn OR, priority hoặc conditional rules, validator phải tự mô hình hóa.
- **Quy tắc trùng lặp:** hai `@Check(rule=NOT_BLANK)` cùng field có thể hợp lệ cú pháp nhưng vô nghĩa, thậm chí tạo hai thông báo. Quyết định có cấm trùng không thuộc consumer/processor.
- **Quy tắc mâu thuẫn:** `MIN_LENGTH(min=10)` kết hợp `MAX_LENGTH(max=5)` (nếu thêm vào enum) là metadata mâu thuẫn. Java không tự phát hiện nếu không có consumer.
- **Mức độ lỗi:** một số rule có thể là warning, một số là error. Annotation có thể thêm `Severity` enum, nhưng cần hướng dẫn hiển thị và logic ưu tiên rõ ràng.
- **Đọc từ superclass:** demo xử lý một class cụ thể và các field khai báo của nó. Nếu muốn áp dụng rule từ superclass, phải duyệt các class trong hierarchy, quyết định xử lý field ẩn và thứ tự hợp nhất. `@Inherited` không giúp truyền field annotations theo cách này.

Một hệ thống validator đáng tin nên có **các bài test về tổ hợp rule**, không chỉ test mỗi rule đứng một mình.

## 10. Những sai lầm thường gặp

| Hiểu nhầm hoặc anti-pattern | Cách làm đúng |
| --- | --- |
| Gắn hai annotation cùng kiểu nhưng quên `@Repeatable` | Định nghĩa repeated annotation và container hợp lệ |
| Khai báo container `String[] value()` cho `@Check` | Container phải có `Check[] value()` |
| Chỉ dùng `getAnnotation(Check.class)` | Dùng `getAnnotationsByType(Check.class)` để đọc nhiều rule |
| Dùng `@Target(TYPE)` cho annotation gắn lên field | Cần `@Target(FIELD)` hoặc target khác đúng vị trí |
| Quên `@Retention(RUNTIME)` nhưng cần reflection | Cả repeated type và container phải có retention phù hợp |
| Mong Java tự validate dữ liệu khi thấy `@Check` | Phải có consumer thực sự đọc và thực thi rule |
| Không xét null/blank | Định nghĩa hành vi cho null và chuỗi chỉ có whitespace |
| Coi `String.length()` luôn là số ký tự hiển thị | Mô tả chính xác đơn vị đếm; cân nhắc Unicode |
| Dùng regex không được kiểm tra | Xác thực cấu hình, bắt lỗi `PatternSyntaxException` đúng thời điểm |
| Giả định thứ tự `getDeclaredFields()` cố định | Sắp xếp field hoặc không phụ thuộc thứ tự |
| Gắn `@Inherited` lên repeatable FIELD và chờ kế thừa qua field cùng tên | Cơ chế kế thừa chuẩn không áp dụng như vậy |
| Nuốt lỗi cấu hình như lỗi người dùng nhập liệu | Tách validation metadata lúc khởi tạo khỏi validation dữ liệu |
| Không định nghĩa policy khi rule trùng/mâu thuẫn | Có cơ chế báo diagnostic hoặc từ chối cấu hình |

## 11. Gợi ý tổ chức code trong ứng dụng thực

Demo nằm trong một file để học dễ dàng. Một thư viện thực nên tách thành các thành phần có trách nhiệm rõ:

```text
annotation/
    Check.java
    Checks.java
    Rule.java

validator/
    Validator.java
    RuleEvaluator.java
    Violation.java

model/
    Registration.java

test/
    ValidatorTest.java
    AnnotationContractTest.java
```

Đây là **sơ đồ tổ chức đề xuất**, không phải những tệp phải được tạo để chạy demo.

**Lớp khai báo annotation** chỉ chứa metadata contract. **Lớp evaluator** chứa các quy tắc cụ thể, được unit test riêng. **Validator** đọc metadata, điều phối việc áp dụng và thu thập các `Violation` thay vì nối message ngay trong vòng lặp. **Lớp test** xác nhận metadata thực sự có mặt đúng vị trí và đúng retention.

Nếu performance quan trọng, việc reflection vào field và biên dịch regex có thể được **cache theo class/field**. Cần chú ý classloader và vòng đời cache để tránh giữ class metadata không còn dùng trong ứng dụng hỗ trợ hot reload.

Đối với quy tắc liên quan tới dữ liệu nhạy cảm, thông báo lỗi nên mô tả điều kiện vi phạm mà **không in giá trị bí mật** như PIN, mật khẩu hoặc token. Demo chỉ in tên field và message, không in input của người dùng.

## 12. Checklist kiểm thử

Trước khi coi implementation hoàn chỉnh, hãy xác nhận các ca sau:

1. **Compiler:** hai `@Check` trên một field biên dịch được; container `@Checks` đúng chữ ký.
2. **Reflection:** `getAnnotationsByType(Check.class)` lấy đúng số rule, đúng loại và tham số.
3. **Retention:** nếu đổi sang `CLASS` hoặc `SOURCE`, hành vi reflection thay đổi theo thiết kế; không nhầm đó là lỗi của `@Repeatable`.
4. **Blank:** `null`, `""` và chuỗi toàn whitespace được xử lý đúng hợp đồng.
5. **Length:** chuỗi ngắn, đúng ngưỡng, dài hơn ngưỡng; đặc biệt dữ liệu Unicode nếu hợp đồng sử dụng `String.length()`.
6. **Regex:** chuỗi khớp, không khớp, regex không hợp lệ, thông báo lỗi phù hợp.
7. **Nhiều rule:** ít nhất hai rule cùng field; một rule thất bại và tất cả rule đều thất bại.
8. **Thứ tự:** không phụ thuộc thứ tự field do reflection trả về; thứ tự rule nếu có ý nghĩa phải được test.
9. **Config invalid:** `min < 0`, regex sai, field không phải `String`, rule lặp vô nghĩa.
10. **Kế thừa:** nếu validator mở rộng sang superclass, xác định rõ chính sách field hiding và duyệt hierarchy.
11. **Truy cập:** field `private` hoặc module boundaries có được hỗ trợ hợp lệ không.
12. **Không làm lộ dữ liệu:** chỉ thông báo vi phạm cần thiết; không dump dữ liệu bí mật.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao hai `@Check` trên cùng field cần `@Repeatable`, còn `@NotBlank` cạnh `@Pattern` thì không?

**Đáp án:** `@Repeatable` cho phép **lặp một annotation type**. Hai annotation khác kiểu vốn có thể cùng xuất hiện ở vị trí target cho phép.

**Câu 2.** Container cho `@Check` bắt buộc có element nào?

**Đáp án:** `Check[] value();` và đáp ứng các điều kiện về retention, target và meta-annotation liên quan.

**Câu 3.** Vì sao `getDeclaredAnnotation(Check.class)` trả `null` trên field có hai `@Check` trong demo?

**Đáp án:** Nhiều annotation cùng kiểu được biểu diễn bằng container `@Checks`; các `Check` là indirectly present chứ không có một `Check` directly present ở field trong trường hợp này.

**Câu 4.** Nếu field có ba rule thì `Field.getAnnotationsByType(Check.class)` trả gì?

**Đáp án:** Mảng gồm ba annotation `Check` khi metadata có retention RUNTIME phù hợp; consumer có thể duyệt từng rule.

**Câu 5.** Cấu hình `@Check(rule=Rule.MATCHES, regex="[", message="invalid regex")` có bị Java compiler từ chối chỉ vì regex sai không?

**Đáp án:** Không. Cấu hình này hợp lệ về cú pháp và kiểu giá trị annotation; `javac` không tự kiểm tra cú pháp biểu thức chính quy. Processor hoặc mã xử lý khi chạy cần phát hiện regex không hợp lệ (ví dụ `PatternSyntaxException`). Tên enum và các phần tử bắt buộc vẫn phải khai báo đúng để biên dịch được.

**Câu 6.** Trong demo, `username="ab"` và `pin="9x"` tạo ra mấy lỗi?

**Đáp án:** Hai: username không đạt `min=4`, pin không khớp regex ba chữ số. Cả hai đều không blank.

**Câu 7.** Khi cần lấy metadata của nhiều field từ một class cha, chỉ thêm `@Inherited` vào `@Check` là đủ không?

**Đáp án:** Không. `@Inherited` không truyền field annotations như vậy; validator phải tự duyệt class hierarchy nếu được thiết kế để hỗ trợ.

**Câu 8.** Nếu muốn các thông báo của validator ổn định trên các JVM, việc nào cần chú ý?

**Đáp án:** Không phụ thuộc thứ tự `getDeclaredFields()`; hãy sắp xếp field và công bố rõ chính sách thứ tự rule, như demo.

## Tài liệu chính thức

- [Java Language Specification 17, §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3).
- [JLS 17, §9.7.5 — Multiple Annotations of the Same Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5).
- [Java SE 17 API — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html).
- [Java SE 17 API — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17 API — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html).
- [Java SE 17 API — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).

**Kết luận:** `@Repeatable` giúp một field có thể mang nhiều cấu hình kiểm tra cùng kiểu một cách tự nhiên. Muốn hệ thống thực sự kiểm tra dữ liệu, phải có consumer đọc **mọi rule bằng `getAnnotationsByType()`**, hiểu rõ từng element và báo vi phạm đúng hợp đồng. Kết hợp thiết kế container chuẩn, retention/target đúng, kiểm tra cấu hình và bài test runtime sẽ giúp annotation lặp trở thành một API metadata đáng tin.
