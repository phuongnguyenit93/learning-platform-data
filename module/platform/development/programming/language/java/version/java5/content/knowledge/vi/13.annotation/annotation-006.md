# Phần tử annotation dạng mảng và annotation lồng nhau

Khi siêu dữ liệu cần nhiều giá trị cùng loại, một phần tử annotation có thể trả về mảng, chẳng hạn `String[] tags();`. Khi cần một nhóm thông tin có cấu trúc, phần tử có thể mang kiểu annotation khác, chẳng hạn `Rule primary();`.

Hai khả năng này kết hợp được: `Rule[] rules();` mô tả nhiều quy tắc, mỗi quy tắc có các phần tử riêng. Đây là dữ liệu mô tả; các quy tắc đó chỉ có tác động nghiệp vụ khi có mã hoặc công cụ đọc và áp dụng chúng.

## 1. Phần tử kiểu mảng

Khai báo minh họa:

```java
@interface Tags {
    String[] value();
}
```

Cách dùng:

```java
@Tags({"batch", "export"})
class ExportTask {
}
```

`value` có kiểu `String[]`; dấu ngoặc nhọn cung cấp hai phần tử. Mỗi phần tử phải phù hợp với kiểu thành phần của mảng theo quy tắc giá trị annotation.

| Cách dùng | Giá trị tương ứng |
| --- | --- |
| `@Tags({"batch", "export"})` | Mảng dài 2 |
| `@Tags({"batch"})` | Mảng dài 1 |
| `@Tags("batch")` | Mảng dài 1; bỏ ngoặc nhọn theo cú pháp annotation |
| `@Tags({})` | Mảng rỗng |
| `@Tags(value = {"batch", "export"})` | Dạng có tên, cùng hai phần tử |

Cách viết ngắn `@Tags("batch")` không biến `value` thành `String`: kiểu khai báo vẫn là `String[]`.

Nếu phần tử mảng mang tên khác, chẳng hạn `String[] names();`, vẫn phải ghi tên khi sử dụng: `@Names(names = "batch")`. Việc bỏ ngoặc nhọn cho một phần tử và việc bỏ `value =` là hai quy tắc khác nhau.

## 2. Cú pháp mảng annotation không phải biểu thức new thông thường

Trong annotation, viết:

```java
@Tags({"batch", "export"})
class CorrectTask {
}
```

Không thay bằng:

```java
// Cố ý minh họa cú pháp giá trị không hợp lệ:
// @Tags(new String[] {"batch", "export"})
```

Giá trị phần tử annotation tuân theo một tập quy tắc riêng. Với các phần tử chuỗi hoặc nguyên thủy, giá trị phải là hằng phù hợp tại thời điểm biên dịch; không thể dùng một lời gọi như `loadTags()` để tạo mảng lúc chương trình chạy.

Một biến mảng `static final String[]` cũng không trở thành giá trị annotation hợp lệ chỉ vì biến là `final`. Nó vẫn là tham chiếu đến mảng, không phải hằng chuỗi hoặc biểu thức giá trị mảng annotation như yêu cầu.

Các giới hạn đáng nhớ:

- Mảng phần tử annotation là mảng một chiều của một kiểu phần tử được phép.
- Không khai báo phần tử kiểu `String[][]`.
- Không dùng `List<String>` thay cho kiểu mảng trong khai báo phần tử.
- Không dùng `null` cho cả giá trị mảng hoặc từng phần tử.
- Mảng rỗng `{}` và `null` không phải cùng một ý nghĩa.

Các kiểu thành phần có thể thuộc nhóm được Java cho phép như nguyên thủy, `String`, `Class`, enum hoặc một kiểu annotation.

## 3. Annotation lồng nhau là giá trị có cấu trúc

Giả sử một quy tắc cần tên và giới hạn:

```java
@interface Rule {
    String name();
    int max();
}

@interface Policy {
    Rule primary();
}
```

Có thể cung cấp giá trị `Rule` ngay trong annotation `Policy`:

```java
@Policy(primary = @Rule(name = "core", max = 100))
class ExportJob {
}
```

Đường đi dữ liệu:

```text
Policy
  primary -> Rule
               name -> "core"
               max  -> 100
```

`@Rule(...)` ở đây là một giá trị annotation lồng bên trong phần tử `primary`. Nó không phải một annotation `Rule` được gắn trực tiếp lên `ExportJob`.

Do đó, nếu dùng reflection, cần đọc `Policy` trên lớp rồi gọi `policy.primary()`. Truy vấn trực tiếp `ExportJob.class.getAnnotation(Rule.class)` không tự tìm xuống bên trong các phần tử của `Policy`.

Cũng cần phân biệt:

- **Giá trị annotation lồng nhau:** `@Rule(...)` là dữ liệu của một annotation khác.
- **Khai báo kiểu annotation lồng trong một lớp:** vị trí tổ chức mã nguồn của `@interface Rule`.
- **Meta-annotation:** annotation mô tả một kiểu annotation, ví dụ `@Target` hoặc `@Retention`.

Chúng có thể cùng xuất hiện trong một chương trình nhưng đóng vai trò khác nhau.

## 4. Mảng annotation lồng nhau

Thay phần tử đơn bằng mảng:

```java
@interface Policy {
    Rule[] rules();
}
```

Cách dùng:

```java
@Policy(rules = {
        @Rule(name = "fast", max = 10),
        @Rule(name = "slow", max = 50)
})
class BatchJob {
}
```

Mỗi vị trí của `rules` là một giá trị `Rule` hoàn chỉnh. Các phần tử bắt buộc như `name` và `max` phải được cung cấp cho từng giá trị lồng nhau.

Với đúng một `Rule`, có thể viết:

```java
@Policy(rules = @Rule(name = "only", max = 5))
class OneRuleJob {
}
```

Đây vẫn là mảng `Rule[]` dài 1. Dấu ngoặc nhọn bao mảng được bỏ theo quy tắc giá trị mảng một phần tử.

Mảng annotation không tự làm cho annotation trở thành repeatable. Việc có thể viết nhiều `@Rule` trực tiếp trên cùng một khai báo là một cơ chế riêng, không được thiết lập chỉ bằng việc khai báo `Rule[] rules()`.

## 5. Giá trị mặc định cho mảng và annotation lồng

Có thể định nghĩa:

```java
@interface Policy {
    String[] tags() default {};
    Rule primary() default @Rule(name = "base", max = 100);
    Rule[] rules() default {};
}
```

Ý nghĩa:

- Bỏ `tags` thì dùng mảng rỗng.
- Bỏ `primary` thì dùng giá trị annotation `Rule` mặc định.
- Bỏ `rules` thì dùng mảng rỗng.
- Khi cung cấp một mảng mới, đó là toàn bộ giá trị của phần tử ấy; Java không tự gộp thêm các phần tử từ mảng mặc định.

Một giá trị annotation mặc định cũng phải đáp ứng quy tắc kiểu và các phần tử bắt buộc của annotation lồng. Chẳng hạn, `default @Rule(name = "base")` không đủ nếu `max` không có mặc định.

Nếu mảng rỗng có ý nghĩa “không áp dụng quy tắc nào” hoặc “dùng cơ chế mặc định bên ngoài”, ý nghĩa đó phải được bên xử lý quy định. Cú pháp Java chỉ cung cấp dữ liệu, không quyết định thay nghiệp vụ.

## 6. Chương trình hoàn chỉnh

Ví dụ sau dùng Java 17+ để đọc cả phần tử mảng, giá trị annotation đơn và mảng annotation lồng nhau.

`Rule` dùng `@Target({})` để thể hiện nó chỉ dành làm giá trị trong annotation khác, không gắn trực tiếp lên lớp/phương thức. `Policy` được gắn lên lớp và có retention `RUNTIME` để ví dụ đọc bằng reflection.

Lưu thành `NestedAnnotationDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class NestedAnnotationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({})
    public @interface Rule {
        String name();
        int max();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Policy {
        String[] tags() default {};
        Rule primary() default @Rule(name = "base", max = 100);
        Rule[] rules() default {};
    }

    @Policy(
            tags = {"batch", "export"},
            primary = @Rule(name = "core", max = 100),
            rules = {
                    @Rule(name = "fast", max = 10),
                    @Rule(name = "slow", max = 50)
            })
    static final class ExportJob {
    }

    @Policy(tags = "single", rules = @Rule(name = "only", max = 5))
    static final class SingleJob {
    }

    @Policy
    static final class EmptyJob {
    }

    static void describe(Class<?> type) {
        Policy policy = type.getAnnotation(Policy.class);
        if (policy == null) {
            throw new IllegalArgumentException("Policy annotation is required");
        }

        System.out.println(type.getSimpleName()
                + " tags=" + Arrays.toString(policy.tags()));

        Rule primary = policy.primary();
        System.out.println("primary=" + primary.name() + "/" + primary.max());

        Rule[] rules = policy.rules();
        System.out.println("rules=" + rules.length);
        for (Rule rule : rules) {
            System.out.println("rule=" + rule.name() + "/" + rule.max());
        }
    }

    public static void main(String[] args) {
        System.out.println("direct Rule: "
                + ExportJob.class.isAnnotationPresent(Rule.class));
        describe(ExportJob.class);
        describe(SingleJob.class);
        describe(EmptyJob.class);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 NestedAnnotationDemo.java
java NestedAnnotationDemo
```

Stdout:

```text
direct Rule: false
ExportJob tags=[batch, export]
primary=core/100
rules=2
rule=fast/10
rule=slow/50
SingleJob tags=[single]
primary=base/100
rules=1
rule=only/5
EmptyJob tags=[]
primary=base/100
rules=0
```

### Những gì ví dụ chứng minh

`ExportJob` có metadata của `Policy`, trong đó chứa các giá trị `Rule`. Nó không có `Rule` gắn trực tiếp, nên dòng đầu in `false`.

`SingleJob` dùng dạng không có ngoặc nhọn cho cả mảng chuỗi một phần tử và mảng annotation một phần tử. Khi đọc, chúng vẫn là các mảng.

`EmptyJob` bỏ toàn bộ phần tử tường minh và nhận các mặc định. Phần tử annotation đơn `primary` vẫn có dữ liệu dù hai mảng đều rỗng.

Chương trình chỉ in siêu dữ liệu. Nó không tự giới hạn công việc theo `max`; muốn kiểm tra hoặc áp dụng giới hạn phải viết mã xử lý tương ứng.

## 7. Đọc và sử dụng dữ liệu có cấu trúc

Khi xử lý một annotation có phần tử lồng, nên đi từ ngoài vào trong:

1. Tìm annotation ngoài tại đúng phần tử chương trình.
2. Xử lý trường hợp không có annotation ngoài.
3. Đọc phần tử annotation đơn bằng phương thức truy cập tương ứng.
4. Duyệt phần tử mảng theo kiểu thành phần của nó.
5. Kiểm tra các ràng buộc nghiệp vụ mà hệ thống cần.

Trình biên dịch có thể kiểm tra rằng `max` nhận một số nguyên, nhưng tên `max` không tự bắt buộc số đó phải dương. Ràng buộc như `max > 0`, tên quy tắc không trùng hoặc thứ tự ưu tiên cần có triển khai kiểm tra.

Các giá trị được đọc là metadata. Không dùng phần tử annotation như vùng lưu trạng thái thay đổi của một công việc đang chạy.

## 8. Lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Cách xử lý |
| --- | --- |
| Dùng `new String[]` trong giá trị annotation | Dùng cú pháp `{"a", "b"}` |
| Truyền biến mảng vì nghĩ `static final` là đủ | Cung cấp giá trị theo cú pháp annotation hợp lệ |
| Khai báo phần tử mảng hai chiều | Chuyển mô hình sang mảng một chiều hoặc các annotation có cấu trúc |
| Đặt `null` để biểu diễn mảng rỗng | Dùng `{}` hoặc mặc định rõ ràng |
| Tìm annotation trong bằng `getAnnotation` trên lớp ngoài | Đọc annotation ngoài rồi truy cập phần tử lồng |
| Thiếu phần tử bắt buộc trong một `@Rule` | Cung cấp đầy đủ hoặc định nghĩa mặc định phù hợp |
| Cho rằng `Rule[]` tự cho phép lặp `@Rule` trên lớp | Phân biệt mảng phần tử với cơ chế repeatable |
| Mặc định mảng sẽ được tự động gộp với giá trị tường minh | Xử lý quy tắc gộp trong bên đọc nếu nghiệp vụ cần |

Khi mô hình annotation cần lồng quá nhiều tầng hoặc dữ liệu phụ thuộc môi trường, nên cân nhắc liệu cấu hình ngoài hoặc kiểu dữ liệu thông thường có dễ bảo trì hơn không.

## 9. Thực hành

1. Đổi `tags = "single"` thành `tags = {"single"}`; kết quả có đổi không?
2. Đổi `rules = @Rule(...)` của `SingleJob` thành mảng chứa hai `Rule`.
3. Bỏ `max = 5` ở giá trị `Rule` của `SingleJob`; dự đoán lỗi.
4. Thêm `@Rule(name = "direct", max = 1)` trực tiếp lên một lớp khi `Rule` vẫn có `@Target({})`.
5. Đổi mặc định `primary` thành `@Rule(name = "fallback", max = 20)`; lớp nào thay dữ liệu primary?

Đáp án:

1. Không; cả hai đều cung cấp một phần tử mảng.
2. Dòng `rules=` sẽ in 2 và vòng lặp đọc hai giá trị theo thứ tự đã khai báo.
3. Lỗi biên dịch vì phần tử `max` bắt buộc chưa được cung cấp.
4. Lỗi biên dịch vì `Rule` không được phép gắn trực tiếp vào khai báo đó.
5. `SingleJob` và `EmptyJob`; `ExportJob` đã cung cấp `primary` tường minh.

Mỗi thí nghiệm nên bắt đầu từ chương trình gốc để các thay đổi không chồng lên nhau.

## Tài liệu đối chiếu

Xem [JLS 21 §9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.1), [§9.7.1 — Normal Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.1) và ví dụ `@Target({})` trong API [Target](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Target.html).
