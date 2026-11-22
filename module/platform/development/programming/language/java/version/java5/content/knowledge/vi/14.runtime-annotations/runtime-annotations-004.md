# Phân biệt annotation khai báo trực tiếp và annotation được kế thừa

## Một kết quả tìm thấy có thể đến từ đâu?

Khi một bộ đọc metadata hỏi lớp con có annotation hay không, câu trả lời có thể phục vụ hai nhu cầu khác nhau:

- Kiểm tra **lớp con tự khai báo** thông tin gì.
- Lấy thông tin áp dụng cho lớp con theo quy tắc tra cứu, có thể sử dụng annotation từ lớp cha.

Ví dụ, lớp cha công bố một nhãn cấu hình chung. Lớp con không viết lại nhãn nhưng bộ đọc vẫn có thể tìm thấy nó nếu kiểu annotation cho phép kế thừa. Nếu không phân biệt hai nhu cầu, ta dễ kết luận nhầm rằng lớp con đã khai báo cấu hình riêng hoặc đã sao chép annotation vào bytecode của mình.

Bài này dùng annotation đơn, có `RUNTIME`, trên lớp và phương thức để đối chiếu kết quả rõ ràng. Toàn bộ ví dụ chạy trên Java 17+.

## Annotation trực tiếp và cơ chế `@Inherited`

Annotation trực tiếp là annotation gắn ngay trên phần tử đang được khảo sát. Với reflection, `getDeclaredAnnotation(Tag.class)` chỉ đọc sự hiện diện trực tiếp của kiểu annotation được hỏi.

Nếu kiểu annotation có `@Inherited`, khi hỏi một **lớp** bằng `getAnnotation(Tag.class)`, Java có thể tìm tiếp qua chuỗi lớp cha khi lớp hiện tại không có annotation đó. Lớp khai báo gần nhất cung cấp kết quả. Quy tắc này không áp dụng cho annotation trên phương thức, trường hoặc từ interface được triển khai. Xem [`Inherited`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Inherited.html).

`@Inherited` được đặt lên khai báo `@interface Tag`, không phải lên từng lớp con. Nó chỉ có ý nghĩa khi metadata đủ điều kiện đọc lúc chạy; ví dụ vì thế cũng khai báo `@Retention(RUNTIME)`.

## Các API cần phân biệt

| Câu hỏi | API |
| --- | --- |
| Phần tử này trực tiếp khai báo một annotation cụ thể không? | `getDeclaredAnnotation(Tag.class)` |
| Annotation cụ thể có mặt theo quy tắc tra cứu, kể cả kế thừa khi đủ điều kiện không? | `getAnnotation(Tag.class)` |
| Có annotation theo cùng quy tắc với `getAnnotation` không? | `isAnnotationPresent(Tag.class)` |
| Tập annotation trực tiếp của phần tử là gì? | `getDeclaredAnnotations()` |
| Tập annotation có mặt, bao gồm annotation kế thừa hợp lệ khi hỏi lớp, là gì? | `getAnnotations()` |

Các API này thuộc hợp đồng `AnnotatedElement`; không nên hiểu từ `Declared` là một chế độ mở quyền truy cập. Nó mô tả phạm vi tìm annotation. Xem [hợp đồng `AnnotatedElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

## Ví dụ hoàn chỉnh

Lưu toàn bộ mã trong `InheritedAnnotationDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public final class InheritedAnnotationDemo {
    private InheritedAnnotationDemo() {
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Tag {
        String value();
    }

    @Tag("parent")
    static class Parent {
        @Tag("parent-method")
        public void execute() {
        }
    }

    static class Child extends Parent {
    }

    @Tag("child")
    static class DirectChild extends Parent {
        @Override
        public void execute() {
        }
    }

    @Tag("interface")
    interface Contract {
    }

    static class Implementation implements Contract {
    }

    private static String text(Tag tag) {
        return tag == null ? "<none>" : tag.value();
    }

    public static void main(String[] args) throws NoSuchMethodException {
        System.out.println("Child.declared: "
                + text(Child.class.getDeclaredAnnotation(Tag.class)));
        System.out.println("Child.lookup: "
                + text(Child.class.getAnnotation(Tag.class)));
        System.out.println("Child.present: "
                + Child.class.isAnnotationPresent(Tag.class));
        System.out.println("Child.declaredCount: "
                + Child.class.getDeclaredAnnotations().length);
        System.out.println("Child.lookupCount: "
                + Child.class.getAnnotations().length);

        System.out.println("DirectChild.declared: "
                + text(DirectChild.class.getDeclaredAnnotation(Tag.class)));
        System.out.println("DirectChild.lookup: "
                + text(DirectChild.class.getAnnotation(Tag.class)));
        System.out.println("Implementation.lookup: "
                + text(Implementation.class.getAnnotation(Tag.class)));

        Method parentMethod = Parent.class.getDeclaredMethod("execute");
        Method overrideMethod = DirectChild.class.getDeclaredMethod("execute");
        System.out.println("Parent.execute: "
                + text(parentMethod.getAnnotation(Tag.class)));
        System.out.println("DirectChild.execute: "
                + text(overrideMethod.getAnnotation(Tag.class)));

        Method inheritedMethod = Child.class.getMethod("execute");
        System.out.println("Child.methodOwner: "
                + inheritedMethod.getDeclaringClass().getSimpleName());
        System.out.println("Child.execute via getMethod: "
                + text(inheritedMethod.getDeclaredAnnotation(Tag.class)));

        try {
            Child.class.getDeclaredMethod("execute");
            System.out.println("Child.declaredMethod: found");
        } catch (NoSuchMethodException ex) {
            System.out.println("Child.declaredMethod: absent");
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp, với JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror InheritedAnnotationDemo.java
java InheritedAnnotationDemo
```

Stdout chính xác:

```text
Child.declared: <none>
Child.lookup: parent
Child.present: true
Child.declaredCount: 0
Child.lookupCount: 1
DirectChild.declared: child
DirectChild.lookup: child
Implementation.lookup: <none>
Parent.execute: parent-method
DirectChild.execute: <none>
Child.methodOwner: Parent
Child.execute via getMethod: parent-method
Child.declaredMethod: absent
```

### `Child` không khai báo annotation nhưng tra cứu vẫn tìm thấy

`Child` không có `@Tag` trong khai báo của mình nên kết quả `getDeclaredAnnotation` là `null`, được hàm `text` biểu diễn thành `<none>`. Mảng annotation trực tiếp cũng có độ dài bằng `0`.

`getAnnotation` tìm được `@Tag("parent")` vì `Tag` có `@Inherited` và `Child` chưa khai báo `Tag` riêng. Do đó `isAnnotationPresent` là `true` và mảng `getAnnotations()` có một annotation trong ví dụ này.

Các số đếm chỉ là kết quả của ví dụ cố định. Trong chương trình thật, không dùng độ dài mảng để suy luận có một kiểu annotation cụ thể; hãy truy vấn bằng `Tag.class`.

### `DirectChild` cung cấp giá trị riêng

`DirectChild` tự khai báo `@Tag("child")`, vì vậy cả truy vấn trực tiếp lẫn truy vấn có xét lớp cha đều nhận giá trị `"child"`. Chúng không nhận đồng thời hai giá trị `"child"` và `"parent"` cho một annotation đơn.

Đây là ưu tiên của lần khai báo tại lớp con. Nó không sửa annotation của `Parent`, không hợp nhất các phần tử trong hai annotation và không thay đổi kết quả khi truy vấn riêng `Parent.class`.

Nếu annotation có nhiều phần tử hoặc có giá trị mặc định, một annotation trực tiếp trên lớp con vẫn là annotation riêng. Không giả định rằng các phần tử không viết ở lớp con được lấy từ annotation của lớp cha; chúng dùng quy tắc giá trị mặc định của chính kiểu annotation.

### Interface không cung cấp annotation cho lớp triển khai

`Contract` trực tiếp có `@Tag("interface")`. Tuy nhiên, `Implementation` chỉ `implements Contract`, nên `Implementation.class.getAnnotation(Tag.class)` trả `null`.

Nếu muốn lấy annotation trên `Contract`, phải khảo sát `Contract.class` hoặc xây dựng quy tắc duyệt interface riêng. Một framework có thể tự làm việc đó; kết quả của framework không nên được đồng nhất với quy tắc mặc định của `Class.getAnnotation()`.

## Điểm dễ nhầm: kế thừa phương thức khác kế thừa annotation

`DirectChild` khai báo lại `execute()`. Phương thức mới có `@Override` nhưng không có `@Tag`; truy vấn annotation của chính phương thức mới trả `null`. `@Inherited` trên `Tag` không chuyển annotation từ phương thức cha sang phương thức ghi đè.

`Child` lại không khai báo `execute()`. Khi gọi `Child.class.getMethod("execute")`, reflection tìm được phương thức công khai được thừa hưởng từ `Parent`. Đối tượng `Method` trả về mô tả **khai báo ở `Parent`**, vì vậy đọc annotation trên đối tượng đó nhận `"parent-method"`.

Hai kết quả không mâu thuẫn: một bên đang đọc phương thức mới ở lớp con; bên kia đang đọc phương thức thật sự được khai báo ở lớp cha. `getDeclaringClass()` cho biết nguồn khai báo mà đối tượng `Method` mô tả. Xem [`Method.getDeclaringClass()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#getDeclaringClass()).

`getDeclaredMethod("execute")` trên `Child` thất bại vì nó chỉ tìm phương thức được khai báo tại lớp này. Trong khi đó, `getMethod` tìm phương thức công khai theo quy tắc có xét những phương thức được thừa hưởng. Xem [các API tìm phương thức của `Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getMethod(java.lang.String,java.lang.Class...)).

Một tên phương thức giống nhau chưa đủ để xác định hai truy vấn đang đọc cùng khai báo. Với phương thức có tham số, cần cung cấp cả các kiểu tham số khi gọi API tìm phương thức.

## Chọn quy tắc cho bộ đọc metadata

Giả sử bộ đọc cần xác định nhãn áp dụng cho một lớp được người dùng đăng ký:

- Nếu chỉ chấp nhận cấu hình do lớp đó tự khai báo, dùng `getDeclaredAnnotation` và xử lý trường hợp `null`.
- Nếu muốn lớp con nhận cấu hình chung từ lớp cha, thiết kế annotation có `@Inherited` rồi dùng `getAnnotation`.
- Nếu cần duyệt cả interface hoặc phương thức ghi đè, phải định nghĩa thuật toán riêng: xét đâu trước, xử lý nhiều nguồn thế nào và có hợp nhất giá trị hay không.

Không âm thầm bổ sung việc duyệt interface chỉ để làm một truy vấn trả về kết quả. Hai interface có thể công bố hai giá trị khác nhau; lựa chọn ưu tiên là quy tắc của ứng dụng, không được giải quyết bởi `@Inherited`.

Tương tự, khi kiểm tra liệu lớp con có tự thay đổi cấu hình, `getAnnotation` có thể cho một kết quả tìm từ lớp cha. `getDeclaredAnnotation` mới trả lời trực tiếp câu hỏi về khai báo riêng của lớp con.

## Phân biệt với annotation lặp

Ví dụ dùng annotation đơn nên trực tiếp và kế thừa đủ để giải thích kết quả. Với kiểu annotation hỗ trợ `@Repeatable`, nhiều lần sử dụng có thể được lưu trong annotation chứa; cần xem `getDeclaredAnnotationsByType` và `getAnnotationsByType` khi muốn đọc từng lần lặp.

Không dùng bài này để kết luận rằng `getDeclaredAnnotation` sẽ tự mở annotation chứa và trả về một phần tử bất kỳ. Chọn API theo mô hình annotation thực tế; bảng phân loại đầy đủ nằm trong [tài liệu `AnnotatedElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

## Thực hành đối chiếu

Thay đổi từng điểm riêng trên bản sao ví dụ, rồi biên dịch lại:

1. Bỏ `@Inherited` khỏi khai báo `Tag`. `Child.lookup` trở thành `<none>`, `Child.present` thành `false` và `Child.lookupCount` thành `0`; `DirectChild` vẫn đọc được `"child"` vì annotation này là trực tiếp.
2. Khôi phục `@Inherited`, bỏ `@Tag("child")` trên `DirectChild`. Truy vấn trực tiếp lớp này trả `null`, còn `getAnnotation` trả `"parent"`. Annotation của phương thức ghi đè vẫn không tự xuất hiện.
3. Thêm `@Tag("child-method")` vào phương thức `execute()` của `DirectChild`. Truy vấn phương thức đó nhận `"child-method"`; annotation ở phương thức `Parent.execute()` vẫn là `"parent-method"`.
4. Giữ nguyên ví dụ và thêm dòng in `Contract.class.getDeclaredAnnotation(Tag.class).value()`. Nó in `interface`, trong khi truy vấn lớp `Implementation` vẫn trả `null`.

Khi giải thích một kết quả reflection, hãy luôn chỉ ra ba thông tin: đối tượng đang được truy vấn, nơi khai báo thật sự và API có xét kế thừa hay chỉ đọc trực tiếp.