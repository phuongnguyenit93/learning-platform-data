# `getAnnotations()` khác `getDeclaredAnnotations()`

Khi đọc annotation bằng Reflection, bạn cần xác định hai điều: **đang hỏi annotation của phần tử nào** và **có chấp nhận annotation được kế thừa hay không**. Hai phương thức cùng trả về `Annotation[]`, nhưng trả lời hai câu hỏi khác nhau. Sự khác biệt dễ thấy nhất khi phần tử đang xét là một lớp có lớp cha.

Ví dụ, lớp cha mang một chính sách chung, còn lớp con không khai báo chính sách riêng. Một công cụ kiểm tra cấu hình có thể muốn lấy chính sách áp dụng cho lớp con; một công cụ phân tích mã lại chỉ muốn biết chính lớp con khai báo những gì. Chọn sai phương thức khiến hai công cụ hiểu khác nhau cùng một lớp.

## 1. Ý nghĩa và điều kiện nhìn thấy annotation

| Phương thức | Câu hỏi cần trả lời | Kết quả không có annotation |
| --- | --- | --- |
| `getDeclaredAnnotations()` | Phần tử này có những annotation hiện diện trực tiếp nào? | Mảng rỗng |
| `getAnnotations()` | Phần tử này có những annotation hiện diện nào, bao gồm kế thừa khi quy tắc cho phép? | Mảng rỗng |

Với `Class<?>`, `getDeclaredAnnotations()` bỏ qua annotation kế thừa. `getAnnotations()` có thể bổ sung annotation từ lớp cha; nó không đơn giản gom mọi annotation trong cây kiểu. Đây là ngữ nghĩa của [API `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getAnnotations()).

**`Declared` nói về nơi khai báo, không nói về mức truy cập.** Nó không có nghĩa là chỉ lấy annotation `private`, hay lấy thêm annotation bị ẩn. Hai API này cũng không liệt kê annotation của tất cả phương thức, trường dữ liệu và tham số bên trong lớp. Muốn đọc annotation của phương thức, bạn phải có đối tượng `Method` tương ứng.

Điều kiện chung là annotation cần được giữ lại lúc chạy bằng `@Retention(RetentionPolicy.RUNTIME)`. `SOURCE` bị loại khi biên dịch; `CLASS` không được cung cấp để đọc qua các API Reflection này. [Các chính sách lưu giữ annotation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html) quyết định điều đó.

Nếu không khai báo `@Retention`, chính sách mặc định là `CLASS`, không phải `RUNTIME`. Vì vậy, nhìn thấy `@SomeAnnotation` trong mã nguồn chưa chứng minh Reflection sẽ tìm thấy nó. Xem [quy tắc mặc định của `@Retention`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html).

## 2. Kế thừa annotation trên lớp hoạt động ra sao?

Để annotation trên lớp cha được xét cho lớp con, **kiểu annotation** phải được đánh dấu `@Inherited`. Dấu này được đặt trên khai báo `@interface`, không đặt lên lớp con để yêu cầu nó tự nhận mọi annotation.

Với một kiểu annotation không lặp, có thể hình dung quá trình tìm như sau:

1. Nếu lớp hiện tại khai báo annotation đó, dùng giá trị tại lớp hiện tại.
2. Nếu chưa có và kiểu annotation có `@Inherited`, xét lớp cha trực tiếp.
3. Tiếp tục theo chuỗi lớp cha cho đến khi tìm thấy hoặc không còn lớp cha.

Cơ chế này chỉ đi qua **lớp cha**, không lấy annotation từ interface được triển khai. Nó cũng không làm annotation trên phương thức, trường dữ liệu hay constructor tự truyền xuống thành viên khác. [Đặc tả `@Inherited`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Inherited.html) giới hạn phạm vi như vậy.

Chẳng hạn, nếu `Parent` có `@Policy("parent")`, thì `Child extends Parent` có thể nhận chính sách đó khi `Policy` có `@Inherited`. Nếu `Child` tự khai báo `@Policy("child")`, việc truy vấn `Policy` chọn chính sách tại `Child`; không trả thêm giá trị `"parent"` như một danh sách thứ hai.

## 3. Thí nghiệm đầy đủ trên Java 17+

Chương trình sau đặt các trường hợp cạnh nhau: annotation thường, annotation có `@Inherited`, interface, phương thức được kế thừa, phương thức ghi đè và annotation lặp.

Lưu toàn bộ vào **`AnnotationLookupDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

public class AnnotationLookupDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    public @interface Policy {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface LocalTag {
    }

    @Policy("parent")
    @LocalTag
    public static class Parent {
        @Policy("method-parent")
        public void work() {
        }
    }

    public static class Child extends Parent {
    }

    @Policy("child")
    public static class OwnPolicy extends Parent {
    }

    @Policy("interface")
    public interface Contract {
    }

    public static class Impl implements Contract {
    }

    public static class Overrides extends Parent {
        @Override
        public void work() {
        }
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Labels.class)
    public @interface Label {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Labels {
        Label[] value();
    }

    @Label("red")
    @Label("blue")
    public static class Tagged {
    }

    public static class TaggedChild extends Tagged {
    }

    @Label("green")
    public static class OwnTagged extends Tagged {
    }

    private static String names(Annotation[] annotations) {
        return Arrays.stream(annotations)
                .map(a -> a.annotationType().getSimpleName())
                .sorted()
                .toList()
                .toString();
    }

    private static String labels(Label[] annotations) {
        return Arrays.stream(annotations)
                .map(Label::value)
                .toList()
                .toString();
    }

    private static void show(Class<?> type) {
        System.out.println(type.getSimpleName() + " annotations = "
                + names(type.getAnnotations()));
        System.out.println(type.getSimpleName() + " declared = "
                + names(type.getDeclaredAnnotations()));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show(Parent.class);
        show(Child.class);
        show(OwnPolicy.class);
        System.out.println("Child policy = "
                + Child.class.getAnnotation(Policy.class).value());
        System.out.println("OwnPolicy policy = "
                + OwnPolicy.class.getAnnotation(Policy.class).value());
        System.out.println("Impl annotations = "
                + names(Impl.class.getAnnotations()));

        Method inherited = Child.class.getMethod("work");
        Method overridden = Overrides.class.getMethod("work");
        System.out.println("Child.work declaring = "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("Child.work annotations = "
                + names(inherited.getAnnotations()));
        System.out.println("Child.work declared = "
                + names(inherited.getDeclaredAnnotations()));
        System.out.println("Overrides.work annotations = "
                + names(overridden.getAnnotations()));
        System.out.println("Overrides.work declared = "
                + names(overridden.getDeclaredAnnotations()));

        show(Tagged.class);
        System.out.println("Tagged getAnnotation(Label) = "
                + Tagged.class.getAnnotation(Label.class));
        System.out.println("Tagged labels = "
                + labels(Tagged.class.getAnnotationsByType(Label.class)));
        System.out.println("TaggedChild declared = "
                + names(TaggedChild.class.getDeclaredAnnotations()));
        System.out.println("TaggedChild labels = "
                + labels(TaggedChild.class.getAnnotationsByType(Label.class)));
        System.out.println("TaggedChild declared labels = "
                + labels(TaggedChild.class.getDeclaredAnnotationsByType(Label.class)));
        System.out.println("OwnTagged labels = "
                + labels(OwnTagged.class.getAnnotationsByType(Label.class)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 AnnotationLookupDemo.java
java AnnotationLookupDemo
```

Kết quả:

```text
Parent annotations = [LocalTag, Policy]
Parent declared = [LocalTag, Policy]
Child annotations = [Policy]
Child declared = []
OwnPolicy annotations = [Policy]
OwnPolicy declared = [Policy]
Child policy = parent
OwnPolicy policy = child
Impl annotations = []
Child.work declaring = Parent
Child.work annotations = [Policy]
Child.work declared = [Policy]
Overrides.work annotations = []
Overrides.work declared = []
Tagged annotations = [Labels]
Tagged declared = [Labels]
Tagged getAnnotation(Label) = null
Tagged labels = [red, blue]
TaggedChild declared = []
TaggedChild labels = [red, blue]
TaggedChild declared labels = []
OwnTagged labels = [green]
```

Hàm `names()` chủ động sắp xếp tên annotation để kết quả dễ đối chiếu. Không dùng vị trí trong mảng annotation làm quy tắc ưu tiên. Hàm `labels()` giữ thứ tự các giá trị đọc được để quan sát trường hợp annotation lặp.

## 4. Đọc kết quả trên lớp

### Lớp cha và lớp con không khai báo riêng

`Parent` trực tiếp mang `LocalTag` và `Policy`, nên cả hai lời gọi đều thấy hai annotation.

`Child` không khai báo annotation nào, do đó `getDeclaredAnnotations()` cho `[]`. Tuy vậy, `getAnnotations()` vẫn thấy `Policy` vì kiểu annotation này có `@Inherited`. `LocalTag` không có dấu đó nên không xuất hiện khi hỏi `Child`.

Điều cần phân biệt là **annotation tìm thấy khi truy vấn** và **annotation được khai báo trực tiếp**. `Child` không được chèn thêm một khai báo `@Policy` vào mã nguồn chỉ vì `getAnnotations()` tìm thấy nó qua lớp cha.

### Lớp con khai báo chính sách riêng

`OwnPolicy` trực tiếp khai báo `@Policy("child")`. Kết quả từ `getAnnotation(Policy.class).value()` là `"child"`; trong khi `Child` nhận `"parent"`.

Bạn có thể dùng sự khác biệt này để chọn giữa hai quy tắc ứng dụng:

- Đọc cấu hình áp dụng theo kế thừa của Java: truy vấn không có `Declared`.
- Chỉ chấp nhận cấu hình được khai báo tại lớp hiện tại: truy vấn có `Declared`.

Nếu cần biết annotation bắt nguồn từ lớp nào, mảng kết quả không mang sẵn đường đi tìm kiếm. Công cụ cần kiểm tra khai báo trực tiếp từng lớp trong chuỗi lớp cha, thay vì đoán từ thứ tự mảng.

### Interface không truyền annotation cho lớp triển khai

`Contract` có `@Policy("interface")`, nhưng `Impl.class.getAnnotations()` vẫn trả mảng rỗng. `@Inherited` trên `Policy` không thay đổi điều đó.

Nếu ứng dụng muốn áp dụng chính sách từ interface, đó phải là quy tắc do ứng dụng tự thiết kế: duyệt interface nào, xử lý nhiều interface ra sao và giải quyết xung đột thế nào. Không được coi quy tắc đó là hành vi mặc định của `Class.getAnnotations()`.

## 5. Phương thức được kế thừa không phải annotation được kế thừa

Đây là chỗ dễ suy luận sai nhất trong ví dụ.

`Child.class.getMethod("work")` tìm thấy phương thức công khai do `Parent` khai báo. Đối tượng `Method` trả về vẫn đại diện cho **`Parent.work`**, thể hiện qua `getDeclaringClass()` in `Parent`. Vì chính phương thức này trực tiếp mang `@Policy`, cả `getAnnotations()` lẫn `getDeclaredAnnotations()` của nó đều thấy `Policy`.

Ngược lại, `Overrides` khai báo một phương thức `work()` mới để ghi đè. Phương thức đó không mang `@Policy`, nên cả hai lời gọi đều cho `[]`. `@Override` có trong mã nguồn không xuất hiện trong kết quả vì nó không được giữ lại ở runtime.

Do đó, không thể kết luận rằng annotation trên phương thức đã tự truyền xuống chỉ vì bạn tìm thấy annotation khi gọi `Child.class.getMethod(...)`. Trước hết hãy kiểm tra **đối tượng `Method` đang đại diện cho khai báo nào**. Ý nghĩa này gắn với [API `Method.getDeclaringClass()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#getDeclaringClass()).

Với đối tượng `Method` chuẩn, `getAnnotations()` và `getDeclaredAnnotations()` cùng xét annotation trực tiếp trên phương thức được đại diện; chúng không tự hợp nhất annotation từ phương thức bị ghi đè ở lớp cha.

## 6. Annotation lặp: vì sao thấy container?

`Label` được đánh dấu `@Repeatable(Labels.class)`, trong đó `Labels` là kiểu annotation chứa mảng `Label[]`. Khi `Tagged` có hai `@Label`, trình biên dịch biểu diễn chúng qua annotation chứa `Labels`. [Vai trò của `@Repeatable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html) là liên kết kiểu lặp với kiểu chứa.

Kết quả thí nghiệm vì vậy là:

- `getDeclaredAnnotations()` thấy `[Labels]`, không phải hai phần tử `Label` rời nhau.
- `getAnnotations()` trên `Tagged` cũng thấy `[Labels]`.
- `getAnnotation(Label.class)` cho `null` trong trường hợp hai `Label` đang nằm bên trong container.
- `getAnnotationsByType(Label.class)` cho hai giá trị `red`, `blue`.

Trong thuật ngữ API, container hiện diện **trực tiếp** (*directly present*); các annotation lặp nằm bên trong hiện diện **gián tiếp** (*indirectly present*). Hai phương thức số nhiều không có `ByType` không tự bóc container thành những phần tử con. Chọn `...AnnotationsByType(Label.class)` khi cần danh sách `Label` logic. Xem [ngữ nghĩa của `AnnotatedElement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

Trong chương trình, cả `Label` lẫn `Labels` đều có `@Inherited` và `RUNTIME`. Kiểu chứa phải tuân thủ các ràng buộc tương ứng, bao gồm việc có `@Inherited` khi kiểu lặp có dấu này; đó là yêu cầu được quy định cho [annotation lặp và kiểu chứa](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.3).

Quan sát hai lớp con:

- `TaggedChild` không khai báo `Label`: `getAnnotationsByType(Label.class)` nhận `[red, blue]`, còn `getDeclaredAnnotationsByType(Label.class)` cho `[]`.
- `OwnTagged` có một `@Label("green")`: truy vấn `getAnnotationsByType(Label.class)` cho `[green]`, không nối tiếp `[red, blue]` từ lớp cha.

Vì thế, “lấy theo kế thừa” không đồng nghĩa “cộng dồn mọi giá trị của toàn bộ cây lớp”. Đặc biệt, đừng tự suy ra quy tắc annotation lặp từ kết quả của `getAnnotations()`; hãy dùng API theo kiểu annotation cần đọc.

## 7. Chọn đúng API cho mục đích sử dụng

| Bạn cần gì? | API phù hợp |
| --- | --- |
| Liệt kê annotation trực tiếp trên phần tử | `getDeclaredAnnotations()` |
| Liệt kê annotation hiện diện, có xét kế thừa hợp lệ trên lớp | `getAnnotations()` |
| Lấy một annotation cụ thể trực tiếp trên phần tử | `getDeclaredAnnotation(MyAnnotation.class)` |
| Lấy một annotation cụ thể, có xét kế thừa hợp lệ | `getAnnotation(MyAnnotation.class)` |
| Lấy các annotation lặp của một kiểu chỉ tại phần tử hiện tại | `getDeclaredAnnotationsByType(MyAnnotation.class)` |
| Lấy các annotation lặp của một kiểu, có xét kế thừa hợp lệ | `getAnnotationsByType(MyAnnotation.class)` |

Nhóm trả về mảng cho mảng rỗng khi không có kết quả; nhóm trả về một annotation cho `null`. Khi đã biết kiểu cần tìm, truy vấn theo kiểu giúp tránh duyệt và so sánh tên annotation bằng chuỗi.

`isAnnotationPresent(MyAnnotation.class)` tương ứng với việc kiểm tra `getAnnotation(MyAnnotation.class) != null`. Vì vậy, không dùng nó để kết luận rằng một annotation lặp chắc chắn không tồn tại khi nhiều phần tử đang được biểu diễn qua container; cần xét kết quả `getAnnotationsByType(...)` trong trường hợp đó.

## 8. Lỗi thường gặp và cách tự kiểm tra

| Suy luận sai | Cách kiểm tra đúng |
| --- | --- |
| `getAnnotations()` lấy mọi annotation từ lớp cha | Kiểm tra `@Inherited` trên từng kiểu annotation |
| Có `@Inherited` là tự nhận annotation từ interface | Kiểm tra đường kế thừa lớp; interface không nằm trong cơ chế này |
| `Declared` liên quan đến `public` hay `private` | Xác định phần tử thực sự khai báo annotation |
| Phương thức ghi đè nhận annotation của phương thức cha | Kiểm tra annotation trên chính khai báo ghi đè |
| Tìm phương thức qua lớp con thì `Method` thuộc lớp con | Đọc `Method.getDeclaringClass()` |
| Thấy annotation trong mã nguồn thì Reflection đọc được | Kiểm tra `@Retention(RUNTIME)` |
| Mỗi `@Label` luôn là một phần tử trong `Annotation[]` | Xem container và dùng API `ByType` |
| Annotation trên annotation tự được hợp nhất vào lớp sử dụng | Phân biệt phần tử đang truy vấn; API không tự duyệt toàn bộ meta-annotation |

Để tự kiểm chứng bài học, hãy sửa từng chi tiết nhỏ trong thí nghiệm rồi dự đoán kết quả trước khi chạy:

1. Bỏ `@Inherited` khỏi `Policy`: `Child` còn thấy `Policy` không?
2. Thêm `@Policy("own-method")` lên `Overrides.work()`: cả hai API trên phương thức trả những gì?
3. Chuyển `LocalTag` sang `RetentionPolicy.CLASS`: `Parent` còn liệt kê được nó không?
4. Chỉ giữ một `@Label` trên `Tagged`: vì sao kết quả truy vấn annotation đơn có thể khác trường hợp hai `@Label`?

Khi một thay đổi làm annotation không còn hiện diện, hãy kiểm tra `null` trước khi gọi `.value()` trên kết quả truy vấn đơn. Nếu bỏ `@Inherited` khỏi `Policy` mà giữ nguyên lời gọi `Child.class.getAnnotation(Policy.class).value()`, chương trình sẽ gặp `NullPointerException` tại lời gọi đó.

Điểm cần nắm là **phạm vi khai báo**, **quy tắc kế thừa** và **cách biểu diễn annotation lặp**. Xác định đủ ba yếu tố này trước khi chọn phương thức Reflection sẽ giúp kết quả truy vấn có ý nghĩa rõ ràng.
