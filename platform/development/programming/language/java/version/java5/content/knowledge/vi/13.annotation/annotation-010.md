# @Inherited và giới hạn kế thừa annotation qua lớp cha

## Khái niệm và mục đích

Annotation là siêu dữ liệu gắn vào một khai báo hoặc một vị trí sử dụng kiểu. Khi một công cụ đọc annotation của lớp, câu hỏi thường gặp là: nếu lớp con không ghi annotation, có nên dùng cấu hình của lớp cha hay không?

`@Inherited` là một meta-annotation, tức annotation đặt trên **khai báo của một kiểu annotation**. Nó cho phép một số API phản chiếu (reflection) của Java tìm annotation đó dọc theo chuỗi lớp cha khi tra cứu trên một lớp. Cơ chế này vẫn áp dụng trong Java hiện đại; ví dụ dưới đây dùng JDK 17 trở lên.

Ba đối tượng cần phân biệt:

- Kiểu annotation, chẳng hạn `Policy`: nơi đặt `@Inherited`.
- Lớp được gắn annotation, chẳng hạn `@Policy("base") class Base`.
- Lớp được hỏi, chẳng hạn `Child.class.getAnnotation(Policy.class)`.

`@Inherited` không khiến lớp con tự thực thi một hành vi. Thành phần đọc annotation mới quyết định làm gì với kết quả. Nó cũng không tương đương với việc chép annotation vào khai báo của lớp con.

## Khai báo đúng vị trí và đúng chính sách lưu giữ

Đây là khai báo minh họa, chưa phải chương trình chạy độc lập:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
    int level() default 1;
}
```

Các import nằm trong chương trình đầy đủ ở phần sau.

- `@Inherited` đánh dấu `Policy` là kiểu annotation có thể được tra cứu qua lớp cha.
- `@Retention(RetentionPolicy.RUNTIME)` làm annotation có thể được đọc bằng reflection khi chương trình chạy.
- `@Target(ElementType.TYPE)` giới hạn chỗ sử dụng vào khai báo kiểu.

Ba annotation trên có vai trò độc lập. Đặc biệt, `@Inherited` không tự biến chính sách lưu giữ của `Policy` thành `RUNTIME`. Nếu bỏ `@Retention`, chính sách mặc định là `CLASS`, nên không thể kỳ vọng đọc các lần sử dụng `Policy` bằng reflection lúc chạy.

`ElementType.TYPE` cho phép gắn vào cả khai báo interface, nhưng `@Inherited` không làm annotation đi từ interface sang lớp triển khai.

Tài liệu API chính thức mô tả cơ chế này tại [Inherited](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Inherited.html).

## Cơ chế tra cứu trên chuỗi lớp cha

Với một kiểu annotation không lặp như `Policy`, có thể hình dung việc gọi `SomeClass.class.getAnnotation(Policy.class)` theo trình tự:

1. Kiểm tra chính lớp đang được hỏi.
2. Nếu lớp có `Policy` trực tiếp, trả annotation đó.
3. Nếu chưa có và `Policy` được đánh dấu `@Inherited`, xét lớp cha.
4. Tiếp tục lên trên cho đến khi tìm được annotation hoặc hết chuỗi lớp cha.
5. Nếu không tìm được, trả `null`.

Ví dụ, nếu `Base` có `@Policy("base")`, `Child extends Base` và `Grandchild extends Child` đều không khai báo `Policy`, tra cứu trên `Child` hoặc `Grandchild` có thể trả annotation của `Base`.

Đây là một đường tra cứu theo `extends` giữa các lớp. Nó không quét mọi kiểu có quan hệ với lớp đang xét.

### Lớp con khai báo cùng kiểu annotation sẽ thay thế kết quả

Giả sử lớp cha có `@Policy(value = "base", level = 7)`, còn lớp con có `@Policy("child")`. Tra cứu trên lớp con trả `value = "child"` và `level = 1`, vì 1 là giá trị mặc định trong khai báo `Policy`.

Không có thao tác ghép từng thuộc tính: Java không lấy `value` từ lớp con rồi giữ `level = 7` của lớp cha. Annotation trực tiếp trên lớp con là kết quả hoàn chỉnh. Một lớp cháu không khai báo lại sẽ tiếp tục nhận kết quả gần nhất đó.

Nếu muốn vô hiệu hóa một cấu hình kế thừa, không thể xóa annotation lớp cha bằng cách đơn giản bỏ annotation ở lớp con. Hãy thiết kế một giá trị thể hiện việc vô hiệu hóa trong kiểu annotation, hoặc định nghĩa rõ quy tắc riêng của thành phần đọc cấu hình.

## Chọn API đọc annotation đúng với câu hỏi

| API trên `Class<?>` | Câu hỏi phù hợp |
| --- | --- |
| `getAnnotation(Policy.class)` | Lớp này có `Policy`, kể cả qua lớp cha theo `@Inherited`, hay không? |
| `isAnnotationPresent(Policy.class)` | Có tìm được một `Policy` theo cùng quy tắc với `getAnnotation` không? |
| `getDeclaredAnnotation(Policy.class)` | Chính lớp này có khai báo trực tiếp `Policy` không? |
| `getAnnotations()` | Những annotation nào hiện diện trên lớp, gồm các loại có thể kế thừa? |
| `getDeclaredAnnotations()` | Những annotation nào được khai báo trực tiếp trên lớp? |

Vì vậy, việc `getAnnotation` trả khác `null` trong khi `getDeclaredAnnotation` trả `null` hoàn toàn hợp lệ: annotation được tìm từ lớp cha chứ không nằm trực tiếp trên lớp con.

Không dùng `getDeclaredAnnotations().length == 0` để kết luận rằng mọi kiểu tra cứu annotation trên lớp đều sẽ không có kết quả. Ngược lại, không dùng `getAnnotation` khi yêu cầu nghiệp vụ bắt buộc lớp cụ thể phải tự khai báo cấu hình.

Tên API tương tự nhau nhưng phạm vi khác nhau; xem bảng khái niệm trong [AnnotatedElement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

## Những giới hạn quan trọng

### Không kế thừa từ interface

Khi `Contract` có `@Policy("interface")`, lớp `ImplementsOnly implements Contract` không tự có `Policy` qua cơ chế `@Inherited`.

Điều này cũng áp dụng với interface con dùng `extends` một interface khác: không được suy ra rằng annotation của interface cha sẽ xuất hiện trên interface con. Cơ chế ở đây dành cho chuỗi lớp cha của một lớp.

Nếu vừa có lớp cha vừa có interface, `@Inherited` vẫn chỉ xét đường lớp cha. Một thư viện muốn xét interface phải tự định nghĩa cách tìm và xử lý xung đột giữa các nguồn.

### Không kế thừa annotation của phương thức bị ghi đè

`@Inherited` không truyền annotation từ phương thức lớp cha sang phương thức ghi đè ở lớp con. Ngay cả khi kiểu annotation của phương thức được đánh dấu `@Inherited`, việc đọc annotation của phương thức ghi đè vẫn chỉ thấy annotation trên chính khai báo phương thức đó.

Một điểm dễ gây hiểu nhầm:

- Nếu lớp con **không ghi đè** phương thức public, `Child.class.getMethod("execute")` có thể trả về đối tượng `Method` đại diện cho khai báo trong lớp cha.
- Khi đọc annotation của đối tượng `Method` đó, ta đang đọc khai báo của lớp cha. Đây không phải bằng chứng rằng annotation đã được chuyển sang một phương thức mới ở lớp con.
- Nếu lớp con **có ghi đè**, phương thức mới là khai báo khác. Annotation của phương thức cha không tự xuất hiện trên khai báo mới.

Dùng `Method.getDeclaringClass()` để xác định đang đọc khai báo nào. `getDeclaredMethod` chỉ tìm phương thức được khai báo ở chính lớp đang xét; nó không tìm phương thức thừa kế. Các quy tắc tìm thành viên được mô tả trong [Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html).

### Không áp dụng cho các phần tử khác

`@Inherited` không tạo quy tắc truyền annotation cho field, constructor, parameter, package hay vị trí sử dụng kiểu. Chẳng hạn annotation trên một field của lớp cha không tự gắn vào field cùng tên được khai báo ở lớp con.

Cũng không có quan hệ thừa kế giữa các kiểu annotation theo cách khai báo `@interface ChildAnnotation extends ParentAnnotation`. `@Inherited` quản lý việc tìm các lần sử dụng annotation trên lớp; nó không tạo hệ phân cấp kiểu annotation.

## Chương trình đầy đủ: đối chiếu các trường hợp

Lưu đoạn sau thành `InheritedDemo.java`. Chương trình không cần thư viện ngoài, không dùng tính năng preview.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class InheritedDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Policy {
        String value();
        int level() default 1;
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface LocalTag {}

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Action {}

    @Policy(value = "base", level = 7)
    @LocalTag
    static class Base {
        @Action
        public void execute() {}
    }

    static class Child extends Base {}
    static class Grandchild extends Child {}

    @Policy("child")
    static class Specialized extends Base {}

    @Policy("interface")
    interface Contract {}

    static class ImplementsOnly implements Contract {}

    static class Overrides extends Base {
        @Override
        public void execute() {}
    }

    static void show(String label, Class<?> type) {
        Policy policy = type.getAnnotation(Policy.class);
        System.out.println(label + "="
                + (policy == null ? "none"
                : policy.value() + "/" + policy.level()));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show("Child", Child.class);
        show("Grandchild", Grandchild.class);
        show("Specialized", Specialized.class);
        show("ImplementsOnly", ImplementsOnly.class);
        System.out.println("Child.declared="
                + (Child.class.getDeclaredAnnotation(Policy.class) != null));
        System.out.println("Child.present="
                + Child.class.isAnnotationPresent(Policy.class));
        System.out.println("Child.localTag="
                + Child.class.isAnnotationPresent(LocalTag.class));

        Method inherited = Child.class.getMethod("execute");
        Method overridden = Overrides.class.getDeclaredMethod("execute");
        System.out.println("Child.methodOwner="
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("Child.methodAction="
                + inherited.isAnnotationPresent(Action.class));
        System.out.println("Overrides.methodOwner="
                + overridden.getDeclaringClass().getSimpleName());
        System.out.println("Overrides.methodAction="
                + overridden.isAnnotationPresent(Action.class));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac -encoding UTF-8 InheritedDemo.java
java InheritedDemo
```

Kết quả:

```text
Child=base/7
Grandchild=base/7
Specialized=child/1
ImplementsOnly=none
Child.declared=false
Child.present=true
Child.localTag=false
Child.methodOwner=Base
Child.methodAction=true
Overrides.methodOwner=Overrides
Overrides.methodAction=false
```

Giải thích theo từng nhóm kết quả:

1. `Child` và `Grandchild` tìm được `Policy` của `Base` vì `Policy` có `@Inherited`.
2. `Specialized` tự khai báo `Policy`, nên dùng `"child"` và giá trị mặc định 1, không giữ mức 7 của lớp cha.
3. `ImplementsOnly` không nhận annotation từ `Contract`.
4. `Child.declared=false` nhưng `Child.present=true` phân biệt khai báo trực tiếp với kết quả tra cứu qua lớp cha.
5. `LocalTag` có `RUNTIME` nhưng thiếu `@Inherited`, nên không được tìm thấy trên `Child`.
6. `Child.methodOwner=Base` cho thấy phương thức đang được đọc vẫn là phương thức của `Base`. `@Action` nằm trên khai báo đó.
7. `Overrides.methodOwner=Overrides` và `Overrides.methodAction=false` chứng minh `@Action` không tự truyền sang phương thức ghi đè, dù kiểu `Action` có `@Inherited`.

Việc đặt `@Inherited` trên `Action` trong ví dụ là chủ ý để chứng minh giới hạn. Với annotation chỉ dùng trên phương thức trong mã thực tế, thêm meta-annotation này không đem lại tác dụng kế thừa qua phương thức.

## Quan hệ với framework và annotation lặp

### Quy tắc của Java và quy tắc của công cụ đọc

Framework có thể tự duyệt interface, phương thức ghi đè hoặc các meta-annotation để tìm cấu hình. Khi đó kết quả có thể khác một lệnh gọi reflection thuần Java.

Khi chẩn đoán một annotation được tìm thấy hoặc bị bỏ qua, cần xác định:

- Đối tượng đang được đọc là `Class`, `Method` hay phần tử khác?
- API được gọi là `getAnnotation`, `getDeclaredAnnotation` hay API riêng của framework?
- Nếu là phương thức, `getDeclaringClass()` trả lớp nào?
- Thư viện có quy tắc tìm, ghép hoặc ưu tiên riêng không?

Không suy ra rằng mọi framework phải hỗ trợ một cấu hình chỉ vì reflection tìm được annotation. Ngược lại, framework tìm được annotation trên interface không có nghĩa là `@Inherited` của Java đã thay đổi phạm vi.

### Annotation có thể lặp cần nhóm API ByType

Với annotation lặp (`@Repeatable`), nhiều annotation cùng loại có thể được lưu qua annotation chứa. Khi cần đọc các lần xuất hiện của kiểu đó, sử dụng `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType`.

Đừng coi `getAnnotation` là API luôn bóc tách annotation chứa. Cũng không coi `getAnnotationsByType` là thao tác cộng dồn mặc định mọi annotation ở mọi cấp: nếu lớp hiện tại đã có một hay nhiều annotation của kiểu đang hỏi, trực tiếp hoặc thông qua annotation chứa, API không tiếp tục ghép danh sách của lớp cha vào kết quả đó.

Đây là lưu ý khi kết hợp hai cơ chế; chương trình chính cố ý dùng annotation không lặp để quan sát riêng hành vi `@Inherited`.

## Cách áp dụng và lỗi thường gặp

Một tình huống phù hợp là annotation cấu hình ở cấp lớp, trong đó các lớp con được phép dùng cấu hình chung của lớp cha và có thể tự khai báo để thay thế toàn bộ cấu hình. Thành phần sử dụng cấu hình gọi `getAnnotation`, xử lý trường hợp `null`, rồi áp dụng hành vi đã định nghĩa.

Những lỗi cần tránh:

| Hiểu nhầm | Cách kiểm tra hoặc sửa |
| --- | --- |
| Đặt `@Inherited` lên lớp nghiệp vụ | Đặt nó trên khai báo kiểu annotation |
| Có `@Inherited` là đủ để đọc lúc chạy | Kiểm tra thêm `@Retention(RUNTIME)` |
| Implement interface sẽ nhận annotation của interface | Tự gắn vào lớp hoặc dùng cơ chế tìm có tài liệu rõ ràng |
| Annotation phương thức tự đi theo `@Override` | Kiểm tra chính khai báo phương thức; định nghĩa quy tắc riêng nếu cần |
| Lớp con chỉ thay những thuộc tính được viết ra | Nhớ rằng giá trị còn lại dùng mặc định của kiểu annotation |
| Annotation trả về từ lớp con chắc chắn nằm trong khai báo lớp con | So sánh với `getDeclaredAnnotation` |
| Tìm được annotation là mã tự thay đổi hành vi | Tìm thành phần thực sự đọc và áp dụng annotation |

Không dùng `@Inherited` như bằng chứng đủ để tự động cấp quyền hoặc bỏ qua kiểm tra đầu vào. Annotation chỉ cung cấp siêu dữ liệu; quyết định cuối cùng phải tuân thủ quy tắc của thành phần xử lý.

## Thực hành kiểm chứng

Thực hiện lần lượt trên chương trình đầy đủ:

1. Bỏ `@Inherited` khỏi `Policy`, biên dịch lại. `Child` và `Grandchild` sẽ in `none`, còn `Specialized` vẫn dùng annotation trực tiếp.
2. Khôi phục `@Inherited`, thêm `@Policy("middle")` ngay trước khai báo `Child`. `Child` và `Grandchild` sẽ dùng `middle/1`, cho thấy lớp gần nhất quyết định kết quả.
3. Gắn `@Action` vào `Overrides.execute()`. Dòng `Overrides.methodAction` sẽ thành `true` vì phương thức tự khai báo annotation.
4. Bỏ riêng `@Inherited` khỏi kiểu `Action`. Kết quả của hai lệnh tra cứu annotation phương thức vẫn như trước, bởi meta-annotation này không điều khiển sự kế thừa annotation phương thức.

Sau các thay đổi, luôn biên dịch lại để kết quả phản ánh đúng mã mới. Hãy giải thích được vì sao mỗi kết quả xuất hiện và khai báo nào thực sự đang được đọc.
