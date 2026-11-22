# getAnnotation, getDeclaredAnnotation và isAnnotationPresent trong Java Reflection

## 1. Mục tiêu: tra cứu annotation tại runtime đúng phạm vi

Annotation trong Java là metadata gắn với class, interface, method, field, constructor, parameter, package hoặc vị trí sử dụng kiểu, tùy khai báo `@Target`. Framework thường dùng annotation để đánh dấu component, router, converter, validation, transaction, mapping và các quy tắc nghiệp vụ. Ba API cốt lõi trên `java.lang.reflect.AnnotatedElement` là:

- `<T extends Annotation> T getAnnotation(Class<T> annotationClass)`: lấy annotation loại yêu cầu nếu nó **hiện diện** (present) trên phần tử theo quy tắc Reflection; nếu không có thì trả `null`.
- `<T extends Annotation> T getDeclaredAnnotation(Class<T> annotationClass)`: lấy annotation loại yêu cầu được **gắn trực tiếp trên phần tử** (directly present), không tìm annotation thừa kế; nếu không có thì trả `null`.
- `boolean isAnnotationPresent(Class<? extends Annotation> annotationClass)`: hỏi annotation loại đó có **hiện diện** trên phần tử không. Theo hợp đồng, kết quả tương đương `getAnnotation(annotationClass) != null`.

Khác biệt lớn nhất giữa `getAnnotation` và `getDeclaredAnnotation` thể hiện ở **annotation trên class có `@Inherited`**. Với nhiều phần tử khác, như method và field, hai API thường cho cùng kết quả vì Java **không tự kế thừa annotation của method/field bị override hoặc bị che**.

**Điểm xuất phát:** muốn Reflection đọc được annotation, annotation đó thông thường phải khai báo `@Retention(RetentionPolicy.RUNTIME)`. Nếu annotation chỉ có retention `SOURCE` hoặc `CLASS`, ba API runtime nêu trên không trả annotation ấy, ngay cả khi source có dấu `@MyMarker`.

## 2. Điều kiện để ba API đọc được annotation

Annotation phải được lưu với `@Retention(RetentionPolicy.RUNTIME)` và truy vấn trên **đúng phần tử**. Mặc định khi bỏ `@Retention` là `CLASS`; Reflection runtime không trả những lần sử dụng annotation chỉ có `SOURCE` hoặc `CLASS` retention.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Feature { String name(); }
```

Đây là fragment cần import `java.lang.annotation.*`. `@Target(TYPE)` cho phép gắn `Feature` trên khai báo kiểu; hỏi `Method.getAnnotation(Feature.class)` không tìm annotation đang nằm trên một class. Bài retention riêng giải thích class-file visibility và các trường hợp `TYPE_USE`.

## 3. `AnnotatedElement` là interface chung cho những loại nào?

`Class<?>`, `Method`, `Field`, `Constructor<?>`, `Parameter`, `Package`, `Module` và nhiều đối tượng Reflection khác thực hiện hoặc được xem qua `AnnotatedElement` (cần đối chiếu phiên bản Java thực tế cho các loại chuyên biệt). Điều này cho phép viết tiện ích:

~~~java
import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;

// Mảnh minh họa, đặt trong một class hoặc method thích hợp.
static <A extends Annotation> A findAnnotation(
        AnnotatedElement element, Class<A> type) {
    return element.getAnnotation(type);
}
~~~

Hàm generic giữ đúng kiểu annotation ở kết quả: nếu gọi `findAnnotation(User.class, Feature.class)` thì kiểu trả về là `Feature`, không cần ép kiểu raw. `getAnnotation` **không** gọi logic nghiệp vụ của class/method; nó chỉ đọc metadata. Đọc annotation trên method private cũng **không đòi `setAccessible(true)`**: quyền gọi private method là việc khác với việc đọc annotation metadata của đối tượng `Method` đã lấy được qua `getDeclaredMethod`.

Một vài ví dụ đối tượng cần chọn chính xác:

- `SomeClass.class`: tra annotation trên class.
- `SomeClass.class.getDeclaredMethod("run")`: tra annotation trên method khai báo trực tiếp.
- `SomeClass.class.getDeclaredField("id")`: tra annotation trên field khai báo trực tiếp.
- `SomeClass.class.getDeclaredConstructor()`: tra annotation trên constructor khớp chữ ký.
- `method.getParameters()[i]`: tra annotation trên formal parameter tương ứng.

Không lấy annotation của một parameter bằng cách gọi `method.getAnnotation(ParamMarker.class)`: lời gọi này tra **method**, không tra tham số của method.

## 4. Phân biệt “directly present” và “present”

Thuật ngữ trong `AnnotatedElement` quan trọng hơn nghĩa tiếng Việt của từ “có”:

1. Annotation loại `A` **directly present** trên một phần tử nếu metadata trực tiếp của phần tử chứa annotation `A` (xét đúng quy tắc với annotation repeatable).
2. Annotation loại `A` **present** nếu nó directly present; ngoài ra, với **class**, annotation loại `A` được đánh dấu `@Inherited` có thể present nhờ đi qua chuỗi **superclass** khi class không có annotation `A` trực tiếp.
3. `getDeclaredAnnotation(A.class)` chỉ xét mức **directly present**; không đi tìm trong superclass.
4. `getAnnotation(A.class)` xét mức **present**, nên có thể nhận annotation `A` từ superclass nếu các điều kiện `@Inherited` thỏa.
5. `isAnnotationPresent(A.class)` tương đương `getAnnotation(A.class) != null`. Nó **không** kiểm tra riêng mức declared.

Một quan niệm sai: “`getDeclaredAnnotation` = tìm trong method viết trực tiếp, còn `getAnnotation` = tìm cả method superclass”. **Không đúng.** Cơ chế `@Inherited` của Core Reflection chỉ tự tìm annotation ở cấp class và chuỗi superclass của **class đó**; nó không khiến method override thừa kế annotation của method cha.

### Bảng nhanh theo phần tử

| Tình huống | `getAnnotation(A.class)` | `getDeclaredAnnotation(A.class)` | `isAnnotationPresent(A.class)` |
| --- | --- | --- | --- |
| Class có `@A` trực tiếp, `A` có runtime retention | Trả `A` | Trả `A` | `true` |
| Subclass không khai báo `@A`; superclass có `@A` và `A` có `@Inherited` | Có thể trả annotation thừa kế | `null` | `true` |
| Subclass không khai báo `@A`; superclass có `@A` nhưng `A` không `@Inherited` | `null` | `null` | `false` |
| Method override không gắn `@A`; method cha có `@A` | `null` trên method override | `null` | `false` |
| Field con che field cha nhưng không gắn `@A` | `null` trên field con | `null` | `false` |
| Annotation trên source có `RetentionPolicy.CLASS` | `null` | `null` | `false` |
| Repeatable `@A` xuất hiện hai lần và được lưu qua container `@As` | Dùng `getAnnotationsByType(A.class)` để lấy đủ hai annotation; `getAnnotation(A.class)` không tự unpack container | Không tự unpack container | Không phải phép hỏi “có bất kỳ A nào trong container” |

## 5. `@Inherited` thay đổi kết quả trên class như thế nào?

Với annotation type `Policy` có `@Inherited`, `@Retention(RUNTIME)` và `@Target(TYPE)`, nếu `Base` mang `@Policy("base")` còn `Child extends Base` không khai báo `Policy`, `Child.class.getAnnotation(Policy.class)` thấy `"base"` nhưng `getDeclaredAnnotation(Policy.class)` trả `null`. Nếu `Child` ghi `@Policy("child")`, giá trị cục bộ được ưu tiên.

Quy tắc này chỉ tra **chuỗi superclass của class**. Annotation trên interface hoặc method bị override không được tự sao chép; method không bị override vẫn có thể được tìm bằng `getMethod` và mang annotation gốc của superclass. Bài về `@Inherited` và bài interface/method dành riêng cho các trường hợp đó. Ví dụ đầy đủ ngay sau đây kiểm chứng cả hai kết quả.

## 6. Chương trình Java 17+ hoàn chỉnh: so sánh ba API

Lưu file **`AnnotationLookupDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AnnotationLookupDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface LocalOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Checked {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface Column {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.CONSTRUCTOR)
    @interface Create {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Labels.class)
    @interface Label {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Labels {
        Label[] value();
    }

    @Role("base")
    @LocalOnly
    static class Base {
        @Column
        private int id;

        @Create
        Base() {}

        @Checked
        public void execute() {}

        @Checked
        public void unchanged() {}
    }

    static class Child extends Base {
        @Override
        public void execute() {}
    }

    @Role("child")
    static class ExplicitChild extends Base {}

    @Role("interface")
    interface MarkedInterface {}

    static class ImplementsInterface implements MarkedInterface {}

    @Label("one")
    @Label("two")
    static class MultipleLabels {}

    public static void main(String[] args) throws Exception {
        Role inherited = Child.class.getAnnotation(Role.class);
        System.out.println("child role=" + inherited.value());
        System.out.println("child declared role="
                + (Child.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("child has role="
                + Child.class.isAnnotationPresent(Role.class));
        System.out.println("child has local="
                + Child.class.isAnnotationPresent(LocalOnly.class));
        System.out.println("explicit child role="
                + ExplicitChild.class.getAnnotation(Role.class).value());
        System.out.println("interface role inherited="
                + ImplementsInterface.class.isAnnotationPresent(Role.class));

        Method overridden = Child.class.getDeclaredMethod("execute");
        Method inheritedMethod = Child.class.getMethod("unchanged");
        System.out.println("overridden method checked="
                + overridden.isAnnotationPresent(Checked.class));
        System.out.println("inherited method owner="
                + inheritedMethod.getDeclaringClass().getSimpleName());
        System.out.println("inherited method checked="
                + inheritedMethod.isAnnotationPresent(Checked.class));

        Field field = Base.class.getDeclaredField("id");
        Constructor<Base> constructor = Base.class.getDeclaredConstructor();
        System.out.println("field column="
                + (field.getDeclaredAnnotation(Column.class) != null));
        System.out.println("constructor create="
                + constructor.isAnnotationPresent(Create.class));

        System.out.println("repeatable getAnnotation="
                + (MultipleLabels.class.getAnnotation(Label.class) != null));
        System.out.println("repeatable container="
                + MultipleLabels.class.isAnnotationPresent(Labels.class));
        System.out.println("repeatable byType="
                + MultipleLabels.class.getAnnotationsByType(Label.class).length);
        System.out.println("repeatable declaredByType="
                + MultipleLabels.class
                    .getDeclaredAnnotationsByType(Label.class).length);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AnnotationLookupDemo.java
java AnnotationLookupDemo
~~~

Kết quả dự kiến trên Java 17+:

~~~text
child role=base
child declared role=false
child has role=true
child has local=false
explicit child role=child
interface role inherited=false
overridden method checked=false
inherited method owner=Base
inherited method checked=true
field column=true
constructor create=true
repeatable getAnnotation=false
repeatable container=true
repeatable byType=2
repeatable declaredByType=2
~~~

### Đọc kết quả từng nhóm

- `Child` **không** có `@Role` trực tiếp, nhưng `@Role` được đánh dấu `@Inherited` trên loại annotation và superclass `Base` có `@Role("base")`. Vì vậy `getAnnotation` trả bản từ cha, `getDeclaredAnnotation` trả `null`, `isAnnotationPresent` trả `true`.
- `@LocalOnly` không có `@Inherited` nên `Child.class.isAnnotationPresent(LocalOnly.class)` trả `false` dù `Base` có annotation này.
- `ExplicitChild` ghi `@Role("child")` trực tiếp, nên giá trị gần nhất là `child`, không phải `base`.
- `ImplementsInterface` implements một interface có `@Role("interface")`. `@Inherited` **không áp dụng qua quan hệ interface**; kết quả `false`.
- `Child.execute()` override method cha nhưng không có `@Checked`, do đó nó **không** tự thừa kế annotation method. Với `unchanged()`, `getMethod` trả về chính đối tượng method đã khai báo tại `Base` (vì Child không override), nên tìm được `@Checked`. Đây là việc Reflection chọn **method khác**, không phải quy tắc thừa kế annotation cho method override.
- `Base.id` là field private có `@Column`; tìm qua `Base.class.getDeclaredField("id")` rồi đọc annotation được, không cần mở quyền bằng `setAccessible(true)`.
- `Base()` có `@Create` và Reflection tìm được trên đối tượng `Constructor`.
- Hai `@Label` được lưu thông qua annotation container `@Labels`, nên `getAnnotation(Label.class)` không tự trả một phần tử; `getAnnotationsByType(Label.class)` / `getDeclaredAnnotationsByType(Label.class)` giải nén được cả hai.

## 7. Khi annotation được lặp lại

Với một `@Repeatable(Labels.class)`, hai `@Label` thường được compiler lưu trong container `@Labels`. Bởi vậy `getAnnotation(Label.class)` và `isAnnotationPresent(Label.class)` có thể lần lượt là `null` và `false`, dù lớp có hai giá trị nhãn. Muốn đọc đủ các nhãn, dùng `getAnnotationsByType(Label.class)`; muốn chỉ đọc trên phần tử hiện tại, dùng `getDeclaredAnnotationsByType(Label.class)`.

Container và quy tắc kế thừa của repeatable annotations được giải thích trong hai bài chuyên biệt. `getAnnotation` cũng không tự quét meta-annotations được đặt trên một annotation type: framework muốn tìm stereotype/composed annotations cần thuật toán riêng.

## 8. Lấy annotation trên class và method: chú ý override

Tình huống:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Validate {}

class Parent {
    @Validate
    public void save() {}
}

class Child extends Parent {
    @Override
    public void save() {}
}
~~~

Đây là mảnh minh họa yêu cầu import tương ứng; nó không phải một chương trình độc lập. Khi chọn `Child.class.getDeclaredMethod("save")`, đó là **method của Child**, không được gắn `@Validate`, vì vậy cả `getAnnotation(Validate.class)` và `getDeclaredAnnotation(Validate.class)` đều trả `null`.

Nếu framework muốn hỗ trợ “annotation method được thừa kế” thì phải **tự định nghĩa thuật toán**: lần theo superclass/interface phù hợp, ánh xạ phương thức override qua tên và parameter types, cân nhắc bridge method, modifier, visibility, generic erasure và trường hợp annotation xung đột. Đừng viết một vòng quét đơn giản dựa vào tên method duy nhất, vì overload, override và default interface methods có thể khiến lựa chọn sai.

Ngoài ra:

- `getMethod(...)` tìm public method có thể được kế thừa; nó có thể trả một `Method` với `getDeclaringClass()` là superclass. Đọc annotation ở object đó là đọc annotation của **declaration thực tế**.
- `getDeclaredMethod(...)` tìm method được khai báo trong class chỉ định, không tự đi superclass. Nếu class không khai báo method được yêu cầu, ném `NoSuchMethodException`.
- Với method có cùng tên nhưng khác parameter types, hãy tra cứu bằng chữ ký đầy đủ, ví dụ `getDeclaredMethod("save", String.class)`.
- `@Inherited` không có hiệu lực lên `@Target(METHOD)` theo quy tắc Reflection; nó là cơ chế áp dụng cho annotation trên class.

## 9. Những điều cần kiểm tra trước khi dùng kết quả vào nghiệp vụ

### 9.1. Annotation type, retention và target

Khi không tìm thấy annotation:

1. Kiểm tra import annotation đúng package và annotation class thực sự mong muốn.
2. Kiểm tra `@Retention(RUNTIME)`. Không có retention tường minh thì mặc định `CLASS`.
3. Kiểm tra `@Target` và vị trí annotation trong source: class, method, field, constructor, parameter hay `TYPE_USE`.
4. Kiểm tra phần tử Reflection đang đọc chính xác: class nào, method signature nào, field của declaring class nào.
5. Nếu muốn annotation thừa kế, xác nhận `@Inherited` có gắn trên loại annotation và tra trên **class** với quan hệ superclass.
6. Nếu annotation là repeatable, ưu tiên `getAnnotationsByType` thay vì `getAnnotation`.
7. Nếu muốn metadata trên interface hoặc meta-annotation, triển khai chiến lược riêng. Core Reflection không tự dò toàn bộ cây interface/meta-annotation.

### 9.2. Tránh `NullPointerException` khi lấy giá trị

`getAnnotation(...)` và `getDeclaredAnnotation(...)` có thể trả `null`, nên không viết:

~~~java
// Code minh họa có thể lỗi khi không có annotation.
String name = element.getAnnotation(Feature.class).name();
~~~

Thay bằng nhánh kiểm tra:

~~~java
// Mảnh minh họa; element là AnnotatedElement.
Feature feature = element.getAnnotation(Feature.class);
if (feature != null) {
    String name = feature.name();
    // Dùng name theo quy tắc nghiệp vụ.
}
~~~

Nếu chỉ cần biết có annotation hay không, gọi `isAnnotationPresent(Feature.class)` sẽ rõ ý đồ. Nếu cần nội dung member như `value()`, gọi `getAnnotation` một lần và kiểm tra null để tránh tra cứu lặp không cần thiết.

### 9.3. Đọc annotation không bảo đảm mọi member value hợp lệ

Kết quả annotation là object đại diện metadata runtime với các element methods. Trong trường hợp class file/annotation declaration không còn tương thích, việc đọc element có thể gây các lỗi như `TypeNotPresentException`, `EnumConstantNotPresentException`, `AnnotationTypeMismatchException` hoặc `IncompleteAnnotationException`. Điều này không biến `getAnnotation` thành một API thao tác nghiệp vụ: khi lấy cấu hình từ annotation, framework nên báo lỗi metadata với tên annotation, phần tử và member bị lỗi, thay vì bỏ qua.

`getAnnotation(null)`, `getDeclaredAnnotation(null)` và `isAnnotationPresent(null)` không phải cách kiểm tra “bất kỳ annotation nào”; API yêu cầu class annotation không null, và có thể ném `NullPointerException`.

### 9.4. Không dùng `getDeclaredAnnotation` để đoán quyền truy cập Java

Từ “declared” nghĩa là “annotation trực tiếp ở phần tử này”, không có nghĩa chỉ dùng cho private/protected member. Một annotation trên public class vẫn có thể lấy qua `getDeclaredAnnotation`. Tương tự, annotation trên private method có thể được đọc từ `Method` đã lấy bằng `getDeclaredMethod` mà không cần mở quyền để gọi method.

### 9.5. Kế thừa annotation khác kế thừa thành viên

- Field hiding: field cùng tên ở class con và field ở cha là **hai khai báo khác nhau**, không tự chia sẻ annotation.
- Method overriding: method mới ở class con không tự thừa kế annotation trên method cha.
- Constructors: không được kế thừa, nên annotation trên constructor cha không chuyển sang constructor con.
- Parameter annotations: không tự kế thừa theo vị trí tham số của method override.
- Class inheritance: chỉ annotation type có `@Inherited` mới được Core Reflection xét theo superclass, với các điều kiện tương ứng.

## 10. Khuyến nghị thiết kế bộ tra cứu annotation

Đối với framework, hãy viết rõ **chính sách tìm kiếm** thay vì dùng một hàm `findAnnotation` mơ hồ.

**Declared-only policy:** khi kiểm tra một declaration đúng vị trí, dùng `getDeclaredAnnotation` hoặc `getDeclaredAnnotationsByType`. Thích hợp cho cấu hình cần gắn trực tiếp trên class cụ thể để tránh vô tình nhận quy tắc từ superclass.

**Java-present policy:** khi muốn đúng ngữ nghĩa sẵn có của Java, dùng `getAnnotation` hoặc `isAnnotationPresent`; với class + `@Inherited`, annotation từ superclass hợp lệ. Với repeatable annotations, dùng các API `ByType` thích hợp.

**Framework-custom policy:** khi muốn quét cả interfaces, overridden methods hoặc meta-annotations, xác định thuật toán tìm kiếm và thứ tự ưu tiên riêng, có kiểm thử với diamond inheritance, annotation mâu thuẫn, method overload, bridge methods và classloader. Không giả định `isAnnotationPresent` đã làm công việc đó.

Ví dụ quyết định policy:

| Mục tiêu | Chính sách khuyến nghị |
| --- | --- |
| Class hiện tại có `@Configuration` do chính nó khai báo? | `getDeclaredAnnotation(Configuration.class) != null` |
| Class có annotation `@Inherited` từ superclass được Java công nhận? | `getAnnotation(...)` hoặc `isAnnotationPresent(...)` |
| Mọi route marker repeatable trên class này? | `getDeclaredAnnotationsByType(Route.class)` |
| Tìm annotation trên method interface và override của implementation? | Thuật toán framework riêng; không dựa vào `getAnnotation` trên method override. |
| Tìm annotation marker nằm bên trong meta-annotation? | Duyệt annotation types/meta-annotations có kiểm soát. |
| Cần đọc một annotation có giá trị cấu hình? | `getAnnotation`, kiểm tra null, rồi đọc các element methods. |

## 11. Bài tập kiểm chứng

1. Trong demo, xóa `@Inherited` khỏi định nghĩa `Role`: dự đoán kết quả `child role` và `child has role`; sửa mã để xử lý `null` trước khi chạy.
2. Gắn `@Role("child-own")` trực tiếp lên `Child` rồi so sánh `getAnnotation` và `getDeclaredAnnotation` ở chính `Child`.
3. Gắn `@Checked` trực tiếp lên `Child.execute()` để thấy annotation trên method override không còn phụ thuộc superclass.
4. Dùng `Child.class.getMethod("unchanged").getDeclaringClass()` để giải thích tại sao annotation trên `Base.unchanged()` vẫn đọc được.
5. Thử annotation với `RetentionPolicy.CLASS` hoặc bỏ `@Retention` và quan sát `getAnnotation(...) == null`.
6. Thử hai `@Label` so với một `@Label`; kiểm tra `getAnnotation(Label.class)`, `isAnnotationPresent(Label.class)` và `getAnnotationsByType(Label.class)`.
7. Tạo interface có `@Role` và một class implements interface; chứng minh `@Inherited` không áp dụng qua interface.
8. Tạo annotation gắn trên formal parameter bằng `@Target(PARAMETER)`, đọc qua `method.getParameters()[0].getAnnotation(...)` thay vì đọc trên `Method`.
9. Viết hàm lấy annotation theo declared-only và một hàm theo Java-present rồi chạy cùng lớp `Base/Child` để so sánh API contract.

## 12. Tài liệu tham khảo

- [Java SE 17 — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): `getAnnotation`, `getDeclaredAnnotation`, `isAnnotationPresent`, repeatable annotation và các định nghĩa present/directly present.
- [Java SE 17 — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): kế thừa annotation theo superclass của class, không phải từ interface hoặc method.
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): retention policy và mặc định `CLASS`.
- [Java SE 17 — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): cơ chế annotation container và các API `ByType`.
- [Java Language Specification 17 — `9.6 Annotation Types và `9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): định nghĩa, khả năng áp dụng và ngữ nghĩa annotations.

**Ghi nhớ:** `getDeclaredAnnotation` chỉ đọc annotation gắn trực tiếp; `getAnnotation` đọc annotation *present* (có thể theo superclass đối với class và loại annotation có `@Inherited`); `isAnnotationPresent` chỉ hỏi cùng điều kiện present đó. Muốn lặp annotation, tra interface hoặc method override, phải chọn API/policy phù hợp thay vì kỳ vọng ba getter tự làm mọi việc.
