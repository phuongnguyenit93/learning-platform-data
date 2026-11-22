# @Repeatable và nhiều annotation cùng loại trong Java

## 1. Vì sao Java cần annotation lặp?

Annotation là metadata gắn với những phần tử chương trình như class, method, field, parameter hoặc nơi sử dụng kiểu. Trước khi có annotation lặp, nếu muốn gắn nhiều giá trị thuộc **cùng một loại annotation** vào một phần tử, người viết thường phải đặt chúng trong một annotation dạng container:

~~~java
// Mảnh mã minh họa theo kiểu container tường minh:
@Roles({@Role("reader"), @Role("writer")})
class AccountService {}
~~~

Kể từ **Java 8**, `@Repeatable` cho phép cú pháp trực tiếp, thuận tiện hơn:

~~~java
// Mảnh mã minh họa, giả sử Role đã khai báo @Repeatable(Roles.class):
@Role("reader")
@Role("writer")
class AccountService {}
~~~

Hai dạng có quan hệ với nhau: **annotation lặp không loại bỏ container**. Nó dùng một **annotation chứa** (containing/container annotation type) hợp lệ làm nơi biểu diễn nhiều annotation cùng loại. Cú pháp rút gọn giúp mỗi chú thích thể hiện một ý riêng, nhưng runtime reflection hoặc công cụ đọc bytecode vẫn cần hiểu container.

Ví dụ sử dụng thực tế: một thành phần hỗ trợ nhiều vai trò quyền hạn, nhiều nhãn phân loại, nhiều tuyến kiểm tra hay nhiều cấu hình độc lập. Việc có nhiều annotation cùng loại **không tự** làm chương trình phân quyền, đăng ký route hoặc chạy validator; thư viện hoặc mã xử lý annotation phải triển khai logic đó.

Bài học tập trung vào `@Repeatable`, cấu trúc container, quy tắc `@Target`/`@Retention`, cách phản chiếu nhiều annotation bằng Java reflection, trường hợp lặp một lần hay nhiều lần, tính kế thừa `@Inherited`, type-use và lỗi thường gặp. Tất cả đều là kiến thức vẫn áp dụng trên JDK hiện đại.

## 2. Bộ đôi bắt buộc: annotation lặp và container

Để tạo annotation `@Role` có thể lặp, khai báo **hai loại annotation**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
~~~

Đây là **mảnh mã minh họa định nghĩa annotation**, có thể đặt làm các khai báo top-level cùng package (không cần `public`) hoặc thành các loại lồng bên trong class. Các ví dụ chạy đầy đủ nằm ở phần sau.

### Ý nghĩa từng thành phần

1. `@interface Role` khai báo loại annotation gốc mà ta muốn viết nhiều lần.
2. `@Repeatable(Roles.class)` khai báo **`Roles` là container của `Role`**.
3. `@interface Roles` định nghĩa một phần tử `value()` có kiểu **`Role[]`**. Đây là yêu cầu cốt lõi; không thể thay tùy ý bằng `List<Role>` hoặc `String[]`.
4. `@Target(ElementType.TYPE)` cho phép dùng trên khai báo class/interface/enum và các vị trí type declaration tương ứng; nó **không** tự cho phép dùng lên method hoặc bất kỳ type-use nào.
5. `@Retention(RetentionPolicy.RUNTIME)` giữ metadata cho Java reflection lúc chạy. Nếu chỉ dùng code analysis lúc biên dịch, có thể chọn retention phù hợp khác.
6. Dù `@Repeatable` nằm ở `Role`, **`Roles` vẫn là một annotation type độc lập**, với `@Target` và `@Retention` riêng phải tuân thủ ràng buộc tương thích.

Khi một class có:

~~~java
@Role("reader")
@Role("writer")
class AccountService {}
~~~

compiler có thể biểu diễn các giá trị lặp thông qua container `@Roles`, tương tự:

~~~java
@Roles({
    @Role("reader"),
    @Role("writer")
})
class AccountService {}
~~~

Nên nghĩ đây là **cơ chế lưu trữ và truy xuất metadata**, không phải Java tạo hai lớp triển khai, hai proxy nghiệp vụ hoặc tự gọi hai hàm.

## 3. `@Repeatable` không có nghĩa annotation được phép xuất hiện ở mọi nơi

`@Repeatable` là meta-annotation của Java, dùng trên **khai báo một annotation type**:

~~~java
@Repeatable(Tags.class)
@interface Tag {
    String value();
}
~~~

Không viết `@Repeatable` trực tiếp trên class nghiệp vụ để “bật khả năng lặp cho class đó”. Chính `Tag` được đánh dấu là repeatable; từ đó `@Tag` có thể xuất hiện nhiều lần trên phần tử được `@Target` cho phép.

Mỗi loại annotation có **phạm vi áp dụng**:

| Target | Ví dụ vị trí hợp lệ |
| --- | --- |
| `ElementType.TYPE` | Khai báo class, interface hoặc enum |
| `ElementType.METHOD` | Khai báo method |
| `ElementType.FIELD` | Khai báo field |
| `ElementType.PARAMETER` | Khai báo formal parameter |
| `ElementType.CONSTRUCTOR` | Khai báo constructor |
| `ElementType.TYPE_USE` | Những nơi kiểu được sử dụng: return type, generic argument, cast, parameter type, v.v. |
| `ElementType.TYPE_PARAMETER` | Khai báo type parameter, ví dụ `<@Mark T>` |

Các target có ý nghĩa khác nhau: `TYPE` là khai báo kiểu, không đồng nghĩa `TYPE_USE` là vị trí sử dụng kiểu. Nếu muốn `@Role` được lặp trên class và method, một bộ cấu hình hợp lý là `@Target({ElementType.TYPE, ElementType.METHOD})` trên **cả annotation gốc và container**.

Khi thiết kế cặp `Role`/`Roles`, các mục tiêu được phép của container phải **tương thích với** mục tiêu của annotation lặp theo quy tắc Java. Đơn giản nhất là để chúng có **cùng tập `@Target`**. Không được tùy tiện thu hẹp target của container khiến compiler không thể lưu một nhóm annotation ở vị trí cho phép.

## 4. Quy tắc của container: không chỉ có tên đẹp

Container hợp lệ cần thỏa các ràng buộc nhất định của Java:

- Có phần tử tên **`value`** trả về **mảng đúng loại annotation gốc**, ví dụ `Role[] value();`.
- Nếu container khai báo các phần tử khác, những phần tử đó phải có **giá trị mặc định**, để compiler có thể tạo container cho nhóm annotation lặp mà không thiếu đối số.
- Chính sách `@Retention` của container **không được ngắn hơn** chính sách retention của annotation gốc. Trường hợp cần reflection runtime, nên đặt **cả hai** là `RUNTIME`.
- `@Target` phải hợp lệ và đủ tương thích với những vị trí annotation gốc được sử dụng.
- Nếu annotation gốc dùng `@Documented`, container cũng phải có `@Documented`.
- Nếu annotation gốc dùng `@Inherited`, container cũng phải có `@Inherited`.

Một định nghĩa **cố ý không hợp lệ**:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    String[] value(); // Sai: phải là Role[], không phải String[].
}
~~~

Đây là ví dụ lỗi biên dịch, không phải mã để chạy. Sửa bằng `Role[] value();`.

### Nếu muốn container có thêm thuộc tính?

Ví dụ:

~~~java
@interface Roles {
    Role[] value();
    String source() default "manual";
}
~~~

Đoạn này chỉ minh họa phần tử thêm phải có **`default`**; cần khai báo đầy đủ `@Retention`, `@Target`, và liên kết `@Repeatable` khi dùng thực tế. Mặc dù hợp lệ trong thiết kế phù hợp, metadata bổ sung ở container có thể khiến biểu diễn trực tiếp và biểu diễn container tường minh có khác biệt về ý nghĩa. Hãy tránh thêm phần tử không cần thiết, hoặc ghi rõ quy tắc cho người tiêu thụ annotation.

## 5. Ví dụ chạy đầy đủ 1: viết nhiều `@Tag` và đọc bằng reflection

Tạo tệp **RepeatableTagsDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

public class RepeatableTagsDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Repeatable(Tags.class)
    @interface Tag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Tags {
        Tag[] value();
    }

    @Tag("fast")
    @Tag("safe")
    static final class Job {
        @Tag("audit")
        @Tag("idempotent")
        public void execute() {}
    }

    static String values(Tag[] tags) {
        String[] names = Arrays.stream(tags)
                .map(Tag::value)
                .toArray(String[]::new);
        return Arrays.toString(names);
    }

    public static void main(String[] args) throws Exception {
        Tag[] onClass = Job.class.getAnnotationsByType(Tag.class);
        Method method = Job.class.getDeclaredMethod("execute");
        Tag[] onMethod = method.getAnnotationsByType(Tag.class);

        System.out.println("class=" + values(onClass));
        System.out.println("method=" + values(onMethod));
        System.out.println("direct-tag=" +
                (Job.class.getAnnotation(Tag.class) != null));
        System.out.println("container=" +
                (Job.class.getAnnotation(Tags.class) != null));
        System.out.println("raw-count=" +
                Job.class.getDeclaredAnnotations().length);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+; các API được sử dụng cho annotation lặp có từ Java 8:

~~~bash
javac RepeatableTagsDemo.java
java RepeatableTagsDemo
~~~

**Stdout chính xác:**

~~~text
class=[fast, safe]
method=[audit, idempotent]
direct-tag=false
container=true
raw-count=1
~~~

Giải thích:

1. `getAnnotationsByType(Tag.class)` lấy **các `@Tag` thuộc loại yêu cầu**, bao gồm những `@Tag` được chứa gián tiếp trong `@Tags`.
2. `getAnnotation(Tag.class)` **không tự mở container**; với hai `@Tag` đã được đóng trong một `@Tags`, nó trả `null`, nên `direct-tag=false`.
3. `getAnnotation(Tags.class)` nhìn thấy container runtime; vì có hai `@Tag` lặp, `container=true`.
4. `getDeclaredAnnotations()` trả các annotation được khai báo trực tiếp ở lớp ở cấp top-level, không tự mở `@Tags`. Trong ví dụ này chỉ có một container, nên `raw-count=1`.
5. `Job.execute()` có một nhóm `@Tag` riêng của method. Các annotation trên class không tự động gắn lên method này.

Điều quan trọng nhất: **API có chữ `ByType` được thiết kế để xử lý annotation lặp**. Đừng dùng `getAnnotation(Tag.class)` rồi cho rằng class không có `@Tag` nếu mã nguồn đang chứa nhiều `@Tag`.

## 6. Một annotation khác với nhiều annotation: hình thức lưu trữ thay đổi

Với định nghĩa `@Role` và `@Roles` có retention runtime:

~~~java
@Role("solo")
class One {}

@Role("read")
@Role("write")
class Many {}

@Roles({@Role("admin"), @Role("internal")})
class Explicit {}
~~~

Ba khai báo trên là **mảnh mã minh họa**, có thể ghép vào chương trình ở phần tiếp.

Cần hiểu ba trường hợp:

- **Chỉ một `@Role`**: thông thường `@Role` hiện diện trực tiếp; không cần compiler tổng hợp container chỉ để biểu diễn một annotation.
- **Nhiều `@Role`**: các annotation cùng loại được biểu diễn thông qua container `@Roles` ở vị trí đó.
- **Viết `@Roles({...})` tường minh**: container có mặt trực tiếp, bên trong có mảng các `@Role`.

Cả ba trường hợp đều nên dùng `getAnnotationsByType(Role.class)` khi mục tiêu là **lấy tất cả role**. Điều này giảm lệ thuộc vào việc nhóm annotation được viết bằng cú pháp lặp hay bằng container.

### “Một annotation” là số lượng, không phải giá trị

Hai annotation giống hệt nhau vẫn là hai lần khai báo:

~~~java
@Role("reader")
@Role("reader")
class Duplicated {}
~~~

Java không tự loại duplicate chỉ vì `value` bằng nhau. Nếu framework muốn coi role trùng là một mục duy nhất, nó phải xử lý deduplication theo quy tắc riêng. Reflection trả về metadata theo đúng cấu trúc được khai báo; không tự hợp nhất giá trị nghiệp vụ.

## 7. Ví dụ chạy đầy đủ 2: direct, repeated và explicit container

Tạo tệp **RepeatableFormsDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class RepeatableFormsDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Roles.class)
    @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Roles {
        Role[] value();
    }

    @Role("solo")
    static class One {}

    @Role("read")
    @Role("write")
    static class Many {}

    @Roles({@Role("admin"), @Role("internal")})
    static class Explicit {}

    static String values(Class<?> type) {
        String[] names = Arrays.stream(
                type.getAnnotationsByType(Role.class)
        ).map(Role::value).toArray(String[]::new);
        return Arrays.toString(names);
    }

    static void show(String label, Class<?> type) {
        boolean direct = type.getAnnotation(Role.class) != null;
        boolean container = type.getAnnotation(Roles.class) != null;
        System.out.println(label + ": direct=" + direct
                + ", container=" + container
                + ", values=" + values(type));
    }

    public static void main(String[] args) {
        show("one", One.class);
        show("many", Many.class);
        show("explicit", Explicit.class);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RepeatableFormsDemo.java
java RepeatableFormsDemo
~~~

**Stdout chính xác:**

~~~text
one: direct=true, container=false, values=[solo]
many: direct=false, container=true, values=[read, write]
explicit: direct=false, container=true, values=[admin, internal]
~~~

Kết luận từ chương trình:

- `getAnnotation(Role.class)` chỉ tìm annotation `Role` phù hợp với API đơn lẻ; nó **không trả các phần tử bên trong container** khi nhiều `Role` đã được lưu qua `Roles`.
- `getAnnotation(Roles.class)` đọc container trực tiếp nếu có.
- `getAnnotationsByType(Role.class)` thu được tất cả `Role` cả trong trường hợp một annotation, nhiều annotation, và container viết tường minh.
- Với nhóm nhiều annotation, thứ tự trong mảng giá trị phản ánh thứ tự đã khai báo trong ví dụ. Dù vậy, về nghiệp vụ không nên lấy thứ tự annotation thay cho một trường ưu tiên được định nghĩa rõ nếu thứ tự thực sự mang ý nghĩa xử lý.

## 8. So sánh các API reflection: không phải API nào cũng “mở” container

Những API sau từ Java reflection là trọng tâm:

| API | Trả về | Có mở container của annotation lặp? | Có thể xét `@Inherited` trên class? |
| --- | --- | --- | --- |
| `getAnnotation(Tag.class)` | `Tag` hoặc `null` | Không tự mở nhiều `Tag` | Có theo quy tắc annotation trực tiếp/khai báo/inherited |
| `getAnnotationsByType(Tag.class)` | `Tag[]` | **Có** | Có nếu chính sách `@Inherited` áp dụng |
| `getDeclaredAnnotation(Tag.class)` | `Tag` hoặc `null` | Không tự mở container | Không |
| `getDeclaredAnnotationsByType(Tag.class)` | `Tag[]` | **Có** | Không xét annotation kế thừa |
| `getAnnotations()` | `Annotation[]` | Không tự mở container | Có theo quy tắc chung |
| `getDeclaredAnnotations()` | `Annotation[]` | Không tự mở container | Không |

`Class`, `Method`, `Field` và một số đối tượng reflection khác cung cấp các API thông qua `AnnotatedElement`. Dùng `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType` cho **annotation có thể lặp** khi muốn đọc nhiều giá trị logic cùng loại.

### “Directly present” và “indirectly present”

Trong ngữ cảnh annotation lặp:

- **Directly present**: annotation loại `Tag` xuất hiện trực tiếp trên phần tử runtime được xét, ví dụ một `@Tag` đơn.
- **Indirectly present**: có container `Tags` trực tiếp và các phần tử `Tag` nằm trong `Tags.value()`.
- API `getAnnotationsByType(Tag.class)` nhận diện cả hai dạng theo quy tắc reflection, và đối với class còn có thể xét sự kế thừa khi điều kiện `@Inherited` được đáp ứng.
- API `getAnnotation(Tag.class)` không mở `Tags.value()` để trả một phần tử đầu tiên. Nó không chọn `Tag` “bất kỳ” trong số các giá trị lặp.

Nếu cần duyệt các giá trị trong container bằng tay, có thể dùng:

~~~java
// Mảnh mã minh họa:
Tags container = SomeClass.class.getAnnotation(Tags.class);
if (container != null) {
    for (Tag tag : container.value()) {
        System.out.println(tag.value());
    }
}
~~~

Nhưng cách này không tự bao phủ trường hợp chỉ có một `@Tag` trực tiếp. Đó là lý do dùng `getAnnotationsByType(Tag.class)` thường là lựa chọn tốt hơn.

## 9. `@Retention` quyết định khả năng đọc annotation lúc chạy

`@Repeatable` không tự làm annotation tồn tại mãi đến runtime.

| Retention | Có gì ở runtime reflection? | Khi nào nên dùng? |
| --- | --- | --- |
| `SOURCE` | Không thấy annotation khi chạy | Annotation processor / kiểm tra ở mức source |
| `CLASS` | Metadata có thể nằm trong class file nhưng không phản chiếu qua API runtime thông thường | Các công cụ bytecode/compile-time phù hợp |
| `RUNTIME` | Reflection có thể đọc nếu truy cập đúng phần tử/vị trí | Framework cấu hình runtime, introspection, test metadata |

Khi muốn dùng `getAnnotationsByType` trong ứng dụng đang chạy, hãy khai báo `@Retention(RUNTIME)` cho cả annotation lặp và container.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
~~~

Nếu một trong hai loại không thỏa quy tắc tương thích retention, compiler có thể báo lỗi định nghĩa annotation. Nếu cả hai chỉ có `CLASS` hoặc `SOURCE`, việc không thấy giá trị qua reflection runtime là hành vi phù hợp hợp đồng, không phải “reflection bị lỗi”.

### Không cần RUNTIME cho mọi trường hợp

Một công cụ phân tích mã nguồn có thể đọc annotation bằng API annotation processing lúc biên dịch, với `SOURCE` retention nếu đáp ứng mục đích. Đừng tăng retention chỉ để “cho chắc”: chọn mức phù hợp với **ai tiêu thụ metadata**, khi nào và ở môi trường nào.

## 10. `@Inherited`: class con có nhận annotation lặp không?

`@Inherited` là meta-annotation cho phép một số annotation ở **class declaration** được tìm qua quan hệ superclass khi reflection trên class con. Nó **không** có nghĩa mọi method, field hay interface đều tự kế thừa annotation lặp.

Nếu muốn annotation lặp hỗ trợ `@Inherited`, cả annotation gốc và container phải khai báo `@Inherited` theo quy tắc Java:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}
~~~

Đây là mảnh mã minh họa; cần import `java.lang.annotation.Inherited` và các meta-annotation khác.

### Nguyên tắc kế thừa quan trọng

- Nếu class con **không** khai báo trực tiếp/gián tiếp loại annotation cần tìm, `getAnnotationsByType(Label.class)` có thể tìm được các label từ superclass, khi cả cấu hình `@Inherited` và quan hệ class đáp ứng.
- Nếu class con có **annotation cùng loại riêng**, nó thường **che** giá trị kế thừa: không phải tự cộng tất cả label của class cha vào mảng label của class con.
- `getDeclaredAnnotationsByType(Label.class)` chỉ tìm trên class đang phản chiếu, không tự đọc superclass.
- Kế thừa annotation của superclass **khác** với quan hệ `implements` interface: `@Inherited` không tự lấy annotation từ interface mà class triển khai.
- `@Inherited` không có tác dụng như cơ chế sao chép metadata từ method bị override sang method override.

Đối với hệ thống phân quyền, audit hay policy routing, đừng giả định quy tắc kế thừa/tích lũy chỉ từ tên `@Inherited`. Framework phải xác định liệu nó dùng reflection mặc định hay tự duyệt các lớp cha/interface để ghép chính sách.

## 11. Ví dụ chạy đầy đủ 3: `@Repeatable` kết hợp `@Inherited`

Tạo tệp **InheritedRepeatableDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class InheritedRepeatableDemo {

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Labels.class)
    @interface Label {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Labels {
        Label[] value();
    }

    @Label("base-A")
    @Label("base-B")
    static class Base {}

    static class Child extends Base {}

    @Label("child")
    static class Own extends Base {}

    static String values(Label[] labels) {
        String[] result = Arrays.stream(labels)
                .map(Label::value)
                .toArray(String[]::new);
        return Arrays.toString(result);
    }

    public static void main(String[] args) {
        System.out.println("base=" +
                values(Base.class.getAnnotationsByType(Label.class)));

        System.out.println("child=" +
                values(Child.class.getAnnotationsByType(Label.class)));

        System.out.println("child-declared=" +
                values(Child.class.getDeclaredAnnotationsByType(Label.class)));

        System.out.println("own=" +
                values(Own.class.getAnnotationsByType(Label.class)));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac InheritedRepeatableDemo.java
java InheritedRepeatableDemo
~~~

**Stdout chính xác:**

~~~text
base=[base-A, base-B]
child=[base-A, base-B]
child-declared=[]
own=[child]
~~~

Với `Child`, không có khai báo `@Label` trên chính class, nên `getAnnotationsByType` lấy các giá trị kế thừa từ `Base`, còn `getDeclaredAnnotationsByType` rỗng. Với `Own`, class có `@Label("child")` riêng nên kết quả từ `getAnnotationsByType` là `[child]`, **không** tự hợp nhất với `base-A` và `base-B`.

Đây là khác biệt dễ gây lỗi nếu một framework dự kiến chính sách “cộng dồn mọi quyền/role từ mọi lớp cha”. Muốn cơ chế cộng dồn, framework phải tự xây quy tắc và duyệt hierarchy nếu đó thực sự là yêu cầu.

## 12. Lặp annotation trên `TYPE_USE` và reflection theo `AnnotatedType`

Java 8 hỗ trợ annotation trên **vị trí dùng kiểu**. Repeatable annotation cũng có thể có `@Target(TYPE_USE)`, cho phép đánh dấu cùng một lần sử dụng kiểu bằng nhiều metadata.

Ví dụ:

~~~java
// Mảnh mã minh họa:
@Mark("source")
@Mark("trusted")
String value;
~~~

Tùy vị trí và `@Target`, hai `@Mark` có thể đánh dấu **type-use** trên `String` thay vì field declaration. Với return type và parameter type, vị trí này rõ hơn:

~~~java
// Mảnh mã minh họa, @Mark có @Target(TYPE_USE):
public @Mark("return-a") @Mark("return-b") String read(
        @Mark("input-a") @Mark("input-b") String input
) {
    return input;
}
~~~

Để truy xuất annotation trên kiểu trả về, dùng **`Method.getAnnotatedReturnType()`**. Để đọc trên kiểu của parameter, dùng **`Method.getAnnotatedParameterTypes()`**; hai API này trả các đối tượng `AnnotatedType`, rồi có thể gọi `getAnnotationsByType(Mark.class)` để mở container.

Không nhầm chúng với `Method.getAnnotation(...)` trên method declaration hoặc `Parameter.getAnnotation(...)` trên parameter declaration. Nếu annotation chỉ có `TYPE_USE`, nó không phải annotation declaration của method/parameter.

## 13. Ví dụ chạy đầy đủ 4: `@Repeatable` trên return và parameter type

Tạo tệp **RepeatableTypeUseDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.util.Arrays;

public class RepeatableTypeUseDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @Repeatable(Marks.class)
    @interface Mark {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Marks {
        Mark[] value();
    }

    static final class Store {
        public @Mark("return-a") @Mark("return-b") String read(
                @Mark("input-a") @Mark("input-b") String input
        ) {
            return input;
        }
    }

    static String values(AnnotatedType type) {
        String[] result = Arrays.stream(
                type.getAnnotationsByType(Mark.class)
        ).map(Mark::value).toArray(String[]::new);
        return Arrays.toString(result);
    }

    public static void main(String[] args) throws Exception {
        Method method = Store.class.getDeclaredMethod(
                "read", String.class);

        System.out.println("return=" +
                values(method.getAnnotatedReturnType()));

        System.out.println("parameter=" +
                values(method.getAnnotatedParameterTypes()[0]));

        System.out.println("value=" +
                new Store().read("Java"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ (tính năng type-use và repeatable annotation đã có từ Java 8):

~~~bash
javac RepeatableTypeUseDemo.java
java RepeatableTypeUseDemo
~~~

**Stdout chính xác:**

~~~text
return=[return-a, return-b]
parameter=[input-a, input-b]
value=Java
~~~

`Mark` chỉ khai báo `@Target(TYPE_USE)`. Trong ví dụ, nó đánh dấu hai vị trí kiểu khác nhau và có thể lặp trên **mỗi vị trí**. `getAnnotationsByType(Mark.class)` là API chung của `AnnotatedElement`, nên cũng hoạt động trên `AnnotatedType` phù hợp.

### Nếu kiểu nằm trong generic?

Ví dụ `List<@Mark("checked") @Mark("normalized") String>` có annotation trên **type argument `String`**, không nhất thiết trên `List` ngoài cùng. Khi reflection phải đi sâu qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`, sau đó gọi `getAnnotationsByType(Mark.class)` trên argument tương ứng. Đừng chỉ đọc annotation của outer return type rồi kết luận không có `Mark`.

### Nếu annotation có nhiều target?

Một annotation được phép dùng cả ở `TYPE_USE` và `PARAMETER` có thể xuất hiện ở vị trí cú pháp gần nhau. Vì vậy khi cần test chính xác metadata ở **parameter declaration** và ở **parameter type**, hãy phân biệt `Method.getParameters()[i]` với `Method.getAnnotatedParameterTypes()[i]` và chọn API thích hợp.

## 14. `@Repeatable` không bắt buộc có nhiều giá trị

Một annotation chỉ được đánh dấu repeatable nghĩa là nó **được phép lặp**, không phải **phải lặp**. Cú pháp hợp lệ:

~~~java
@Tag("only-one")
class A {}
~~~

và cũng có thể:

~~~java
@Tag("first")
@Tag("second")
class B {}
~~~

Khi xây framework đọc metadata, hãy kiểm thử cả hai dạng. Một hệ thống chỉ kiểm tra container sẽ bỏ sót dạng một annotation trực tiếp. Ngược lại, hệ thống chỉ gọi `getAnnotation(Tag.class)` sẽ bỏ sót nhóm nhiều annotation.

### Có nên luôn bắt buộc ít nhất hai giá trị?

Không nên đặt ràng buộc đó lên bản thân `@Repeatable`. Nếu nghiệp vụ yêu cầu ít nhất hai nhãn, chính **validation của framework** cần kiểm tra số phần tử trả về từ `getAnnotationsByType` và báo lỗi cấu hình rõ ràng.

### Giá trị của annotation vẫn bị giới hạn

Một member của annotation như `String value()`, `int priority()`, `Class<?> handler()` hay enum là dữ liệu metadata, không phải một method nghiệp vụ tùy ý. Bạn không thể làm `value()` trả `List<String>` chỉ để dễ biểu diễn nhiều role; các kiểu phần tử annotation hợp lệ tuân theo quy tắc ngôn ngữ Java. Với repeatable annotation, container đã có `Role[] value()` và Java hỗ trợ viết lại `@Role` nhiều lần.

## 15. Repeatable annotation và annotation array: chọn cách nào?

Hai thiết kế có thể cùng truyền tải “nhiều giá trị” nhưng phục vụ mục tiêu hơi khác:

**A. Một annotation chứa mảng giá trị:**

~~~java
@AllowedRoles({"reader", "writer"})
class Api {}
~~~

**B. Nhiều annotation cùng loại:**

~~~java
@Role("reader")
@Role("writer")
class Api {}
~~~

Mảnh mã chỉ minh họa cách sử dụng; cần định nghĩa `@AllowedRoles`, `@Role` và container để chạy.

### Repeatable có lợi khi mỗi phần tử có cấu trúc riêng

Giả sử mỗi role có `name`, `scope`, `priority`; viết nhiều `@Role(...)` giúp các entry tách biệt, dễ thêm/xóa, dễ đọc diff và dễ phát triển API.

~~~java
@Role(name = "reader", scope = "books", priority = 10)
@Role(name = "writer", scope = "reports", priority = 20)
class Api {}
~~~

Khi chỉ cần một danh sách String đơn giản và không có ngữ nghĩa riêng ở từng phần tử, annotation chứa một mảng String cũng có thể đủ. **Chọn theo hợp đồng metadata, không theo xu hướng cú pháp.**

### Có hỗ trợ thứ tự ưu tiên không?

Reflection có thể trả nhiều annotation theo thứ tự được chứa. Nhưng nếu **ưu tiên nghiệp vụ** có ý nghĩa quan trọng (ví dụ rule nào thắng khi xung đột), hãy quy định bằng member `priority`, thứ tự ổn định, hoặc một thuật toán được tài liệu hóa. Không nên suy đoán rằng “annotation viết trước sẽ luôn được chạy trước” nếu framework không cam kết điều đó.

## 16. Những lỗi compile-time thường gặp

### 16.1. Quên `@Repeatable`

~~~java
@interface Flag {
    String value();
}

@Flag("a")
@Flag("b")
class Broken {}
~~~

**Cố ý không biên dịch**: `Flag` chưa được đánh dấu repeatable, nên không thể dùng nhiều lần cùng loại trên một phần tử. Cần định nghĩa container và `@Repeatable(Container.class)` đúng cách.

### 16.2. Container sai kiểu member `value`

~~~java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    String[] value(); // Sai: phải là Flag[].
}
~~~

**Cố ý không biên dịch** vì container không có `Flag[] value()`.

### 16.3. Container thiếu `@Target` tương thích

Nếu `Flag` được dùng lặp trên method nhưng container `Flags` chỉ cho phép trên class, compiler không thể biểu diễn nhóm `Flag` hợp lệ trên method. Hãy giữ target tương thích, lý tưởng là cùng tập các target cho cả hai.

### 16.4. Container retention ngắn hơn annotation gốc

Nếu annotation gốc có `RUNTIME` còn container chỉ có `CLASS`, cấu hình container repeatable không phù hợp. Hãy dùng cùng retention khi các giá trị cần được reflection đọc vào runtime.

### 16.5. Dùng `@Inherited` không đồng bộ

Nếu `Flag` có `@Inherited` mà container `Flags` không có, định nghĩa repeatable không đáp ứng ràng buộc tương ứng. Khi muốn kế thừa class annotations, khai báo phù hợp trên **cả hai**.

### 16.6. Nhầm container với annotation gốc

Vì `Flag` và `Flags` là hai loại annotation khác nhau, `getAnnotation(Flag.class)` không bảo đảm trả một `Flag` từ `Flags.value()`. Gọi `getAnnotationsByType(Flag.class)` để đọc các bản lặp.

### 16.7. Đọc annotation sai phần tử

`Class.getAnnotationsByType(...)` đọc class, `Method.getAnnotationsByType(...)` đọc method. Nếu annotation nằm trên **type của tham số**, hãy đọc `Method.getAnnotatedParameterTypes()[i]`, không tự động tìm thấy bằng `Parameter.getAnnotation`.

## 17. Bản chất runtime: annotation không tự chạy logic

Ví dụ:

~~~java
@Role("reader")
@Role("writer")
class ReportService {}
~~~

Cú pháp này **không** tự có những tác dụng sau:

- Kiểm tra tài khoản hiện tại có quyền reader/writer hay không.
- Xác định “reader AND writer” hay “reader OR writer”.
- Tự đăng ký hai route HTTP, hai job hoặc hai listener.
- Bảo đảm ưu tiên xử lý, không trùng giá trị, hay bảo vệ khỏi cấu hình sai.
- Tự đổi policy khi class được nạp hoặc object được khởi tạo.

Những điều đó là trách nhiệm của **code/framework tiêu thụ annotation**. Nó phải đọc `getAnnotationsByType(Role.class)`, xác định cách kết hợp, kiểm tra giá trị có hợp lệ không và thực thi hành vi có kiểm thử.

### Điều kiện biên của consumer

Một processor hoặc runtime loader tốt cần xử lý:

1. **Không có annotation:** trả mảng rỗng, chọn chính sách mặc định rõ ràng.
2. **Một annotation:** đọc được cả khi không có container.
3. **Nhiều annotation:** mở container đúng kiểu.
4. **Giá trị trùng:** quyết định giữ nguyên, từ chối hay khử trùng.
5. **Giá trị xung đột:** báo lỗi cấu hình hoặc áp dụng precedence được chỉ định.
6. **Thiếu annotation ở runtime:** kiểm tra `RetentionPolicy`, `Target`, cách class được load và đúng đối tượng reflection.
7. **Kế thừa:** xác định có đọc superclass, có ghép chính sách, có bỏ qua interface hay không.
8. **Annotation trên type-use:** đi vào đúng `AnnotatedType`, nhất là generic element.
9. **Version:** bảo đảm JDK/công cụ đang dùng thực sự hỗ trợ cú pháp annotation lặp (Java 8+) và các API khác trong ví dụ.

## 18. Thiết kế API repeatable dễ bảo trì

Khi công khai một annotation repeatable cho nhiều module sử dụng, cần chú ý:

**Đặt tên container rõ ràng.** `@Role`/`@Roles`, `@Tag`/`@Tags` là cặp dễ đọc. Tên container phải có ý nghĩa ngay cả khi người dùng viết nó trực tiếp.

**Giữ metadata và logic tách biệt.** `@Role` mô tả dữ liệu; việc áp dụng quyền thuộc code của hệ thống phân quyền. Điều này giúp kiểm thử quy tắc mà không phụ thuộc một cách đọc reflection duy nhất.

**Duy trì tương thích API.** Khi thay đổi `@Target`, `@Retention` hoặc loại phần tử của annotation đã công khai, cần xem xét mã đã biên dịch và công cụ tiêu thụ. Việc xóa/đổi tên `value()` trên container là thay đổi nghiêm trọng.

**Đặt chính sách fallback có chủ đích.** Khi không có `@Role`, hệ thống phải biết từ chối mặc định hay cho phép mặc định. Đặc biệt với bảo mật, không biến sự vắng mặt của annotation thành quyền truy cập rộng mà không có hợp đồng.

**Kiểm tra reflection với test runtime.** Mỗi API công khai nên có test cho một annotation, nhiều annotation, explicit container, retention và kế thừa nếu áp dụng.

**Không cần dùng repeatable cho mọi thứ.** Nếu dữ liệu thực chất chỉ là một danh sách không phân biệt entry, một annotation chứa mảng có thể đơn giản hơn. Nếu mỗi entry có cấu hình riêng biệt, repeatable thường đọc tốt hơn.

## 19. Ma trận test tối thiểu

| Tình huống | Kết quả mong đợi khi đọc `getAnnotationsByType(T.class)` |
| --- | --- |
| Không có annotation | Mảng rỗng |
| Một `@T` trực tiếp | Mảng một phần tử |
| Hai `@T` lặp | Mảng hai phần tử |
| Explicit container chứa hai `@T` | Mảng hai phần tử |
| Hai `@T` có cùng value | Mảng vẫn có hai phần tử; không tự dedup |
| `@T` với `SOURCE` retention khi đọc runtime | Không thấy |
| `@T` trên method nhưng đọc từ Class | Không thấy ở Class |
| Lặp trên return type nhưng đọc bằng `Method.getAnnotation(T.class)` | Không tự thấy type-use annotation đó |
| Class con không khai báo, superclass có `@Inherited` đúng | Có thể nhận inherited annotations |
| Class con tự khai báo cùng loại, có `@Inherited` đúng | Kết quả theo annotations của con, không tự nối với cha |
| Class con chỉ implements interface có annotation | Không tự kế thừa qua `@Inherited` |
| Container target/retention sai | Lỗi khi khai báo hoặc biên dịch annotation repeatable |

Với framework thực tế, nên bổ sung test cho nhánh chính sách nghiệp vụ: độ ưu tiên, trùng lặp, phân quyền, lỗi cấu hình và hành vi khi annotation không được giữ lại.

## 20. Bài tập thực hành

**Bài 1 — Khai báo đúng container.** Tạo `@Permission` với member `String action()`, repeatable qua `@Permissions`. Cho phép dùng trên class và method, giữ metadata tới runtime. Viết hai `@Permission(action = "...")` trên một class và đọc bằng `getAnnotationsByType(Permission.class)`.

**Bài 2 — Vì sao kết quả reflection khác?** Với một class có hai `@Tag`, so sánh `getAnnotation(Tag.class)`, `getAnnotation(Tags.class)`, `getAnnotationsByType(Tag.class)` và `getDeclaredAnnotations()`. Giải thích khi nào container xuất hiện.

**Bài 3 — Một và nhiều annotation.** Tạo ba class: một class có `@Role` duy nhất, một class có ba `@Role`, một class dùng explicit `@Roles({...})`. Viết một hàm dùng `getAnnotationsByType(Role.class)` để in mảng giá trị ở cả ba trường hợp.

**Bài 4 — Thứ tự và giá trị trùng.** Khai báo hai `@Rule(priority = 10)` cùng loại, rồi xây validator từ chối priority trùng theo chính sách của bạn. Giải thích vì sao `@Repeatable` không ngăn duplicate.

**Bài 5 — Kế thừa.** Khai báo `@Inherited` ở cả annotation gốc và container. Đặt hai annotation trên class cha, tạo class con không khai báo gì và class con có một annotation riêng. So sánh `getAnnotationsByType` và `getDeclaredAnnotationsByType`. Thử lặp lại với interface và giải thích khác biệt.

**Bài 6 — Type-use.** Tạo `@Qualifier` repeatable với `@Target(TYPE_USE)` và `RUNTIME`. Dùng hai `@Qualifier` trên kiểu trả về và hai trên kiểu tham số. Đọc cả hai bằng `AnnotatedType.getAnnotationsByType`.

**Bài 7 — Kiểm tra lỗi định nghĩa.** Cố ý tạo container với `String[] value()`, target sai và retention ngắn hơn annotation gốc. Đọc thông báo compiler, sửa từng lỗi để thu được cặp annotation hợp lệ. Không giữ mã sai trong chương trình cuối.

**Bài 8 — Thiết kế hệ thống thực.** Một dịch vụ khai báo nhiều `@RetryPolicy` với `exception`, `maxAttempts`, `delay`. Hãy định nghĩa rõ thứ tự chọn rule, xử lý overlap, giới hạn maxAttempts và tránh retry những thao tác không idempotent. Annotation chỉ là metadata; chính runtime code phải thực thi có kiểm soát.

## 21. Checklist khi code review

- `@Repeatable(Container.class)` đã đặt trên **annotation type gốc** chưa?
- Container có đúng **`OriginalAnnotation[] value()`** chưa?
- Nếu container có phần tử khác, nó đã có default value chưa?
- Hai loại có `@Target` và `@Retention` **tương thích** chưa?
- Nếu cần `@Inherited` hoặc `@Documented`, container có cùng meta-annotation bắt buộc chưa?
- Consumer có dùng `getAnnotationsByType` thay vì chỉ `getAnnotation` cho trường hợp lặp không?
- Đã test **0 / 1 / nhiều** annotation cùng loại và explicit container chưa?
- Nếu annotation nằm trên TYPE_USE, đang đọc đúng `AnnotatedType` chưa?
- Chính sách trùng giá trị, xung đột, thứ tự và kế thừa có được ghi rõ không?
- Có framework/tool thực sự tiêu thụ metadata, thay vì tin rằng annotation tự làm công việc không?
- Version target có hỗ trợ Java 8+ và các API được dùng trong ví dụ không?

## 22. Tóm tắt

`@Repeatable` cho phép dùng **nhiều annotation cùng loại trên một phần tử hợp lệ**, nhưng yêu cầu một **container annotation** có `value()` trả đúng mảng annotation gốc, cùng các ràng buộc `@Target`, `@Retention`, `@Inherited` và `@Documented` liên quan.

Trong runtime reflection, **`getAnnotationsByType(T.class)`** là API quan trọng để đọc đầy đủ annotation đơn, nhóm lặp và explicit container. Các API chỉ đọc annotation trực tiếp như `getAnnotation(T.class)` có thể không thấy `T` khi nhiều `T` đã được gói trong container.

Cuối cùng, **repeatable annotation là metadata, không phải hành vi tự động**. Cần thiết kế chính sách xử lý rõ ràng cho trùng lặp, thứ tự, kế thừa, vị trí type-use và giá trị không hợp lệ. Cách tiếp cận đó tiếp tục phù hợp với Java hiện đại.
