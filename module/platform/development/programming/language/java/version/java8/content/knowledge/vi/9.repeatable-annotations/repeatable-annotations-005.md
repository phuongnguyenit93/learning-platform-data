# Annotation trực tiếp, chứa và kế thừa trong Java

## 1. Vì sao cùng một annotation nhưng reflection trả kết quả khác nhau?

Khi làm việc với annotation trong Java, đặc biệt là **annotation lặp** (`@Repeatable`) có từ Java 8, câu hỏi “class này có annotation `@Rule` không?” không có một đáp án duy nhất nếu chưa nói rõ **ta muốn đọc theo quy tắc nào**.

Một annotation `@Rule` có thể:

1. **Được khai báo trực tiếp** trên phần tử đang xét, ví dụ `@Rule("a") class A {}`.
2. **Nằm trong annotation chứa (container)**, ví dụ hai `@Rule` được compiler biểu diễn thông qua `@Rules({ ... })`.
3. **Được tìm thấy nhờ kế thừa từ superclass** nếu đó là annotation của **class declaration**, được đánh dấu `@Inherited` và đáp ứng các điều kiện của Java reflection.

Ba tình huống này có những khái niệm riêng trong tài liệu Java: *directly present*, *indirectly present*, *present* và *associated*. Hiểu chúng giúp giải thích tại sao `getAnnotation(Rule.class)`, `getAnnotationsByType(Rule.class)`, `getDeclaredAnnotation(Rule.class)` và `getDeclaredAnnotationsByType(Rule.class)` có thể cho kết quả khác nhau mà **không phải lỗi của compiler**.

Ví dụ:

~~~java
// Mảnh mã minh họa: @Rule repeatable qua @Rules, retention RUNTIME.
@Rule("read")
@Rule("write")
class DocumentService {}
~~~

Khi dùng `getAnnotation(Rule.class)`, kết quả có thể là `null` vì bản thân `Rule` không trực tiếp nằm ở mức phản chiếu ngoài cùng; thay vào đó một container `Rules` đang chứa hai phần tử `Rule`. Dùng `getAnnotationsByType(Rule.class)` sẽ lấy được **cả hai `Rule`**.

Ngược lại:

~~~java
// Mảnh mã minh họa:
@Rule("read")
class ReadService {}
~~~

Với đúng một `@Rule` trực tiếp, `getAnnotation(Rule.class)` có thể trả chính annotation đó. Vì vậy không nên suy từ `null` của `getAnnotation` rằng không có annotation logic nào thuộc loại `Rule`.

**Mục tiêu bài học:** hiểu chính xác các mức hiện diện annotation, bộ API đọc chúng, quy tắc container và kế thừa, cùng những lỗi thường gặp khi xây scanner, annotation processor hoặc framework.

## 2. Định nghĩa một annotation lặp và container hợp lệ

Một ví dụ tối thiểu có retention runtime:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Rules.class)
@interface Rule {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Rules {
    Rule[] value();
}
~~~

Đây là **mảnh mã định nghĩa**, có thể đặt trong một package hoặc lồng vào class trong chương trình đầy đủ.

Cơ chế gồm:

- `@Repeatable(Rules.class)` ở **loại annotation gốc `Rule`** cho phép viết nhiều `@Rule` trên cùng một phần tử được cho phép.
- `Rules` là **loại annotation container**. Thành phần `value()` phải trả **`Rule[]`** chính xác.
- `@Retention(RUNTIME)` trên cả hai loại giữ metadata cho reflection.
- `@Target(TYPE)` cho phép sử dụng trên khai báo kiểu, không mặc nhiên cho phép dùng trên mọi method hoặc generic type argument.
- Khi viết hai `@Rule` cùng vị trí, compiler có cơ chế *repeatable annotation container* để biểu diễn nhóm. Reflection phân biệt **container annotation** với những `Rule` nằm bên trong.

Chương trình có thể chọn viết trực tiếp:

~~~java
@Rule("read")
@Rule("write")
class A {}
~~~

Hoặc viết container rõ ràng:

~~~java
@Rules({@Rule("read"), @Rule("write")})
class B {}
~~~

Hai cách đều có thể được đọc bằng `getAnnotationsByType(Rule.class)`, nhưng **không** đồng nghĩa mọi API reflection đều trả về cùng cấu trúc. Đây là lý do cần phân biệt annotation gốc và annotation chứa.

## 3. Bốn khái niệm hiện diện theo Java reflection

Đặc tả của `AnnotatedElement` phân biệt những quan hệ sau đối với một phần tử `E` và loại annotation `T`.

### 3.1. Directly present — hiện diện trực tiếp

`T` **directly present** trên `E` khi `E` có một annotation runtime trực tiếp đúng loại `T`. Ví dụ, nếu `@Rule("read")` là annotation duy nhất:

~~~java
@Rule("read")
class A {}
~~~

thì `Rule` hiện diện trực tiếp trên `A`. Thông thường `A.class.getDeclaredAnnotation(Rule.class)` và `A.class.getAnnotation(Rule.class)` đều tìm được nó.

### 3.2. Indirectly present — hiện diện gián tiếp qua container

`T` **indirectly present** trên `E` khi có annotation chứa `TC` trực tiếp trên `E`, `TC` là container được khai báo bởi `@Repeatable(TC.class)` của `T`, và `TC.value()` chứa các annotation loại `T`.

~~~java
@Rule("read")
@Rule("write")
class B {}
~~~

Trong trường hợp hai annotation lặp, container `Rules` thường trực tiếp hiện diện trên `B`, còn các `Rule` **gián tiếp** hiện diện qua `Rules.value()`.

`B.class.getAnnotation(Rules.class)` nhìn thấy container; `B.class.getAnnotation(Rule.class)` không tự mở container để lấy một phần tử bất kỳ.

### 3.3. Present — hiện diện theo truy vấn đơn

Với `T`, quan hệ **present** bao gồm `T` trực tiếp hiện diện hoặc trường hợp **kế thừa** phù hợp từ superclass nếu `E` là class và `T` có `@Inherited`. Khái niệm `present` là nền tảng của `getAnnotation(T.class)`, không bao gồm việc tự mở container để lấy tất cả `T`.

Ví dụ class con không khai báo `@Rule`, superclass có một `@Rule` trực tiếp và `Rule` được đánh dấu `@Inherited`: `Child.class.getAnnotation(Rule.class)` có thể tìm được `Rule` của cha. Nhưng khi superclass có **hai `@Rule` được chứa gián tiếp**, `getAnnotation(Rule.class)` không tự chuyển container đó thành một `Rule` đơn.

### 3.4. Associated — hiện diện theo truy vấn nhiều

`T` **associated** với `E` nếu:

1. `T` trực tiếp hoặc gián tiếp hiện diện trên `E`; hoặc
2. `T` không trực tiếp **và cũng không gián tiếp** hiện diện trên `E`, `E` là class, `T` có `@Inherited`, và có các giá trị `T` associated với superclass.

`getAnnotationsByType(T.class)` diễn đạt nhu cầu này: lấy **nhiều** annotation cùng loại, mở container và xử lý kế thừa khi điều kiện cho phép.

**Quy tắc quan trọng:** một class con có **ít nhất một `T` của riêng nó**, trực tiếp hoặc gián tiếp, thì các `T` từ superclass không tự được cộng vào mảng `getAnnotationsByType(T.class)`. Đây là *shadowing/replacement* ở mức loại annotation, không phải cơ chế tự merge.

## 4. Bảng chọn API reflection theo mục tiêu

| API trên `AnnotatedElement` | Đọc annotation trực tiếp | Mở container lặp | Xét kế thừa ở class với `@Inherited` |
| --- | --- | --- | --- |
| `getDeclaredAnnotation(T.class)` | Có | Không | Không |
| `getDeclaredAnnotationsByType(T.class)` | Có | Có | Không |
| `getAnnotation(T.class)` | Có | Không | Có, theo quy tắc *present* |
| `getAnnotationsByType(T.class)` | Có | Có | Có, theo quy tắc *associated* |
| `getDeclaredAnnotations()` | Liệt kê trực tiếp từng annotation runtime | Không tự mở | Không |
| `getAnnotations()` | Liệt kê annotation runtime theo quy tắc API | Không tự mở container | Có thể bao gồm annotation kế thừa |

Chú ý: đối tượng chứa như `@Rules` là **một loại annotation riêng**. Khi gọi `getAnnotation(Rules.class)`, bạn đang hỏi về container `Rules`, không hỏi về từng `Rule`.

Với chương trình cần tất cả giá trị logic `@Rule` của class, `getAnnotationsByType(Rule.class)` thường là API nên dùng. Với chương trình cần **chính xác annotation khai báo ở class hiện tại**, bỏ qua cha, dùng `getDeclaredAnnotationsByType(Rule.class)`.

Nếu cần phân biệt định dạng lưu trữ thực tế (một `@Rule` trực tiếp hay container), dùng các truy vấn `getDeclaredAnnotation(Rule.class)` và `getDeclaredAnnotation(Rules.class)` theo từng loại; đừng cố đoán bằng số phần tử của mảng đã được flatten.

## 5. Ví dụ chạy hoàn chỉnh 1 — trực tiếp, gián tiếp, container tường minh

Tạo tệp **DirectContainedDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class DirectContainedDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Tags.class)
    @interface Tag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Tags {
        Tag[] value();
    }

    @Tag("solo")
    static class One {}

    @Tag("alpha")
    @Tag("beta")
    static class Many {}

    @Tags({@Tag("manual-a"), @Tag("manual-b")})
    static class Manual {}

    static class Empty {}

    static String names(Tag[] annotations) {
        String[] values = Arrays.stream(annotations)
                .map(Tag::value)
                .toArray(String[]::new);
        return Arrays.toString(values);
    }

    static void show(String label, Class<?> type) {
        Tag direct = type.getDeclaredAnnotation(Tag.class);
        Tags container = type.getDeclaredAnnotation(Tags.class);
        Tag single = type.getAnnotation(Tag.class);
        Tag[] all = type.getAnnotationsByType(Tag.class);
        Tag[] declared = type.getDeclaredAnnotationsByType(Tag.class);

        System.out.println(label
                + " direct=" + (direct != null)
                + " container=" + (container != null)
                + " single=" + (single != null)
                + " all=" + names(all)
                + " declared=" + names(declared)
                + " raw=" + type.getDeclaredAnnotations().length);
    }

    public static void main(String[] args) {
        show("one", One.class);
        show("many", Many.class);
        show("manual", Manual.class);
        show("empty", Empty.class);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+; các API và cú pháp chính thuộc Java 8:

~~~bash
javac DirectContainedDemo.java
java DirectContainedDemo
~~~

**Stdout chính xác:**

~~~text
one direct=true container=false single=true all=[solo] declared=[solo] raw=1
many direct=false container=true single=false all=[alpha, beta] declared=[alpha, beta] raw=1
manual direct=false container=true single=false all=[manual-a, manual-b] declared=[manual-a, manual-b] raw=1
empty direct=false container=false single=false all=[] declared=[] raw=0
~~~

Giải thích:

1. `One` có một `@Tag` trực tiếp; truy vấn đơn và nhiều đều thấy nó. `getDeclaredAnnotations()` chứa một annotation.
2. `Many` viết hai `@Tag` nên container `@Tags` được biểu diễn; truy vấn đơn `Tag` không tự mở, nhưng hai API `ByType` trả hai giá trị.
3. `Manual` có `@Tags` tường minh; kết quả theo `ByType` giống nhóm lặp, mặc dù cú pháp nguồn khác.
4. `Empty` không có annotation nên hai truy vấn `ByType` trả mảng rỗng, không trả null.
5. `raw=1` ở `Many` và `Manual` đếm **một container**, không phải đếm từng annotation chứa bên trong.

Tại đây không có `@Inherited`, vì thế `getAnnotationsByType` và `getDeclaredAnnotationsByType` đồng nhất cho các class trong ví dụ. Khác biệt sẽ xuất hiện ở bài toán kế thừa.

## 6. Đừng nhầm “không thấy annotation gốc” với “không có dữ liệu”

Một đoạn scanner chỉ viết:

~~~java
// Mảnh mã minh họa:
Tag tag = type.getAnnotation(Tag.class);
if (tag == null) {
    System.out.println("No tags");
}
~~~

có thể thông báo sai nếu class mang **nhiều `@Tag`**. Do đó một scanner muốn đọc các tag logic nên dùng:

~~~java
// Mảnh mã minh họa:
Tag[] tags = type.getAnnotationsByType(Tag.class);
if (tags.length == 0) {
    System.out.println("No tags");
}
~~~

`getAnnotationsByType` tự xử lý annotation lặp và container theo quy tắc Java. Không nên đọc riêng `@Tags` rồi bỏ qua `@Tag` đơn lẻ, hoặc đọc `@Tag` đơn lẻ rồi bỏ qua container.

### Khi nào cần đọc container tường minh?

Nếu framework có **metadata bổ sung trên container** (ngoài `Tag[] value()`), hoặc cần mô tả chính xác cấu trúc bytecode, có thể phải truy vấn container riêng. Tuy nhiên, API nghiệp vụ chỉ cần “các tag” nên được viết trên **mảng `Tag[]` đã chuẩn hóa** để tránh xử lý hai trường hợp bằng hai nhánh dễ sai.

### Giá trị trùng được xử lý thế nào?

~~~java
// Mảnh mã minh họa:
@Tag("fast")
@Tag("fast")
class RepeatedValue {}
~~~

Java cho phép hai annotation cùng loại có nội dung bằng nhau khi loại đó repeatable. `getAnnotationsByType(Tag.class)` trả hai phần tử; nó **không tự dedup**. Nếu ứng dụng muốn loại trùng hoặc báo lỗi trùng, cần viết quy tắc xử lý riêng.

## 7. `@Inherited` chỉ có ngữ nghĩa đặc biệt ở class hierarchy

Meta-annotation `@Inherited` cho phép Java reflection xét annotation **class declaration** theo quan hệ kế thừa **superclass**. Nó không có tác dụng tự động lan annotation qua mọi quan hệ trong Java.

Để thiết lập annotation lặp có hỗ trợ kế thừa, cả loại annotation gốc và container phải khai báo `@Inherited` đúng quy tắc:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

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

Nếu `@Label` có `@Inherited` mà `@Labels` thiếu `@Inherited`, việc định nghĩa container vi phạm yêu cầu nhất quán của repeatable annotation. Những ví dụ ở phần sau dùng cả hai.

### Không phải `@Inherited` là “copy annotation”

Khi class con không khai báo annotation cùng loại, `getAnnotationsByType(Label.class)` có thể tìm metadata từ class cha. Nhưng annotation không được **sao chép thành khai báo của class con**. Vì vậy `Child.class.getDeclaredAnnotationsByType(Label.class)` vẫn trả mảng rỗng.

Đây là khác biệt giữa **được phản chiếu khi truy vấn** và **được khai báo tại phần tử**. Dùng API `getDeclared...` khi chỉ muốn metadata do chủ sở hữu hiện tại cung cấp.

## 8. Quy tắc thay thế: class con có annotation riêng không tự cộng dồn với cha

Giả sử superclass có:

~~~java
@Label("base-a")
@Label("base-b")
class Base {}
~~~

và có class con:

~~~java
class Child extends Base {}

@Label("own")
class Own extends Base {}

@Label("first")
@Label("second")
class OwnMany extends Base {}
~~~

Các đoạn trên là mảnh mã minh họa, dùng định nghĩa `Label` có `@Inherited`.

Kết quả dự kiến khi dùng `getAnnotationsByType(Label.class)`:

| Class | Annotation cùng loại trên class hiện tại | Giá trị theo ByType |
| --- | --- | --- |
| `Base` | Hai `Label` qua container | `[base-a, base-b]` |
| `Child` | Không có | `[base-a, base-b]` do kế thừa |
| `Own` | Một `Label` riêng | `[own]` |
| `OwnMany` | Hai `Label` riêng | `[first, second]` |

Lý do: quy tắc **associated** chỉ đi lên superclass nếu không tìm được `Label` trực tiếp **hoặc gián tiếp** ngay trên class đang xét. Khi class con đã có một hoặc nhiều `Label` riêng, nó **không** tự cộng thêm của class cha.

**Quan trọng với framework:** nếu mục tiêu nghiệp vụ là tổng hợp mọi quyền, mọi route hoặc mọi policy từ **tất cả** ancestor, thì `getAnnotationsByType` đơn lẻ không bảo đảm phép cộng dồn đó. Framework phải tự duyệt hierarchy và áp dụng nguyên tắc xung đột/ưu tiên đã định nghĩa.

## 9. Ví dụ chạy hoàn chỉnh 2 — kế thừa và che annotation

Tạo tệp **InheritedLabelsDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class InheritedLabelsDemo {

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

    @Label("base-a")
    @Label("base-b")
    static class Base {}

    static class Child extends Base {}

    @Label("own")
    static class Own extends Base {}

    @Label("first")
    @Label("second")
    static class OwnMany extends Base {}

    static String names(Label[] labels) {
        String[] values = Arrays.stream(labels)
                .map(Label::value)
                .toArray(String[]::new);
        return Arrays.toString(values);
    }

    static void show(String name, Class<?> type) {
        System.out.println(name + " all="
                + names(type.getAnnotationsByType(Label.class))
                + " declared="
                + names(type.getDeclaredAnnotationsByType(Label.class))
                + " single="
                + (type.getAnnotation(Label.class) != null));
    }

    public static void main(String[] args) {
        show("base", Base.class);
        show("child", Child.class);
        show("own", Own.class);
        show("own-many", OwnMany.class);
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac InheritedLabelsDemo.java
java InheritedLabelsDemo
~~~

**Stdout chính xác:**

~~~text
base all=[base-a, base-b] declared=[base-a, base-b] single=false
child all=[base-a, base-b] declared=[] single=false
own all=[own] declared=[own] single=true
own-many all=[first, second] declared=[first, second] single=false
~~~

Giải thích:

- `Base` có hai annotation gián tiếp qua `Labels`; `getAnnotation(Label.class)` không mở container nên `single=false`.
- `Child` không khai báo `Label`; `getAnnotationsByType` kế thừa hai giá trị, còn `getDeclaredAnnotationsByType` rỗng. `getAnnotation(Label.class)` không biến container cha thành một `Label` trực tiếp, nên vẫn `false`.
- `Own` có một `Label` trực tiếp, nên các API đơn và nhiều tìm thấy annotation của chính nó. Hai label từ `Base` không tự được cộng vào `all`.
- `OwnMany` có container riêng chứa hai annotation, nên `getAnnotation(Label.class)` không trả một `Label` đơn; `getAnnotationsByType` trả hai annotation riêng của `OwnMany`.

### Một tinh tế: annotation gốc và container là hai loại khác nhau

Khi class con trực tiếp có một `@Label`, nó đã cung cấp metadata loại `Label` cho truy vấn `getAnnotationsByType(Label.class)`. Nhưng nếu `Labels` cũng có `@Inherited`, một truy vấn **riêng biệt đối với loại container** như `getAnnotation(Labels.class)` có thể vẫn tìm thấy container từ superclass khi class con không tự khai báo container. Vì vậy đừng trộn mảng `getAnnotationsByType(Label.class)` với một lần đọc `Labels.class` kế thừa rồi **cộng thủ công**, vì có nguy cơ nhân đôi hoặc làm sai chính sách shadowing.

Một nguyên tắc tốt cho consumer là chọn **một đường đọc canonical** theo mục tiêu, sau đó xử lý business semantics rõ ràng.

## 10. Ví dụ chạy hoàn chỉnh 3 — annotation class không tự lan sang interface/method

`@Inherited` có phạm vi hẹp: nó chỉ liên quan đến **superclass chain của class**. Nó không tự truyền annotations từ interface được triển khai, và không tự sao chép metadata của method bị override sang method override.

Tạo tệp **InheritanceBoundaryDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

public class InheritanceBoundaryDemo {

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Repeatable(Marks.class)
    @interface Mark {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface Marks {
        Mark[] value();
    }

    @Mark("interface")
    interface Contract {}

    static class ContractImpl implements Contract {}

    static class Parent {
        @Mark("method")
        public void work() {}
    }

    static class Child extends Parent {
        @Override
        public void work() {}
    }

    static String values(Mark[] marks) {
        String[] names = Arrays.stream(marks)
                .map(Mark::value)
                .toArray(String[]::new);
        return Arrays.toString(names);
    }

    public static void main(String[] args) throws Exception {
        System.out.println("interface=" +
                values(Contract.class.getAnnotationsByType(Mark.class)));

        System.out.println("implementation=" +
                values(ContractImpl.class.getAnnotationsByType(Mark.class)));

        Method parent = Parent.class.getDeclaredMethod("work");
        Method child = Child.class.getDeclaredMethod("work");

        System.out.println("parent-method=" +
                values(parent.getAnnotationsByType(Mark.class)));

        System.out.println("child-method=" +
                values(child.getAnnotationsByType(Mark.class)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac InheritanceBoundaryDemo.java
java InheritanceBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
interface=[interface]
implementation=[]
parent-method=[method]
child-method=[]
~~~

Kết quả thể hiện:

1. `Contract` được đánh dấu trực tiếp nên đọc từ chính `Contract.class` sẽ thấy.
2. `ContractImpl` chỉ `implements Contract`, không có quan hệ superclass declaration chứa annotation `Mark`; `@Inherited` không tự truyền qua interface.
3. `Parent.work()` được đánh dấu, nhưng `Child.work()` **override** method mà không có `@Mark`; reflection trên `Method` của con không tự kế thừa `@Mark` từ method cha.
4. Nếu `Child` **không override** `work`, lời gọi `Child.class.getMethod("work")` có thể trả đối tượng `Method` khai báo ở `Parent` và thấy annotation của **method cha**. Điều đó **khác** với việc annotation tự được sao chép sang một method override ở class con.

Đây là lý do không nên áp dụng máy móc “class con kế thừa annotation” cho interface, field, parameter, constructor hoặc method. Nếu framework muốn hỗ trợ các quy tắc đó, nó cần tự truy vết quan hệ và định nghĩa cách hợp nhất metadata.

## 11. Sự khác nhau giữa `getAnnotations()` và `getAnnotationsByType()`

Giả sử:

~~~java
@Rule("read")
@Rule("write")
class DocumentService {}
~~~

Khi annotation được lặp, tập annotation runtime trực tiếp ở cấp phần tử có thể gồm **một container `@Rules`**. Vì vậy:

~~~java
DocumentService.class.getDeclaredAnnotations();
~~~

trả về các annotation trực tiếp *theo loại hiện diện tại lớp*, không mở `@Rules.value()` thành từng `@Rule`. Trong khi:

~~~java
DocumentService.class.getDeclaredAnnotationsByType(Rule.class);
~~~

có thể trả mảng `[Rule("read"), Rule("write")]` đã mở container.

Đối với `getAnnotations()`, logic kế thừa có thể bổ sung annotation có `@Inherited`, nhưng API này vẫn không thay thế `getAnnotationsByType` nếu mục tiêu là lấy toàn bộ annotation của một loại repeatable.

### Vì sao không nên dùng `getAnnotations().length` để đếm rule?

Đếm ở đây là **số annotation ở mức mà API trả**, có thể gồm container, annotations khác loại và các annotations kế thừa. Nó không tương đương với số quy tắc nghiệp vụ. Hãy đếm:

~~~java
int count =
        DocumentService.class.getAnnotationsByType(Rule.class).length;
~~~

nếu mục tiêu đúng là số `Rule` có liên hệ với class đó theo quy tắc associated. Nếu muốn **chỉ các rule tự khai báo**, thay bằng `getDeclaredAnnotationsByType(Rule.class).length`.

## 12. Khi nào dùng `getDeclared...` để tránh kế thừa ngoài ý muốn?

Trong các hệ thống có plugin, scheduler, route hoặc access control, việc tự động thừa hưởng policy có thể là chủ ý hoặc lỗi. Hai lựa chọn:

- **Chỉ cấu hình ngay trên class:** `getDeclaredAnnotationsByType(Policy.class)`.
- **Cấu hình theo Java inheritance:** `getAnnotationsByType(Policy.class)` với `@Inherited` đúng trên annotation type.

Ví dụ **mảnh mã minh họa**:

~~~java
Policy[] explicit =
        target.getDeclaredAnnotationsByType(Policy.class);
Policy[] effective =
        target.getAnnotationsByType(Policy.class);
~~~

`explicit` phục vụ việc hiển thị “người phát triển đã gắn gì ngay ở đây”, còn `effective` phục vụ việc hỏi “Java reflection tìm thấy các policy nào theo quy tắc associated”.

Với policy ảnh hưởng bảo mật hoặc chi phí, đừng dựa duy nhất vào tên API. Hãy tài liệu hóa: có cho phép kế thừa hay không; shadowing có ưu tiên class con hay không; có cộng dồn từ nhiều superclass hay interface hay không; giá trị trùng và xung đột được xử lý thế nào.

### Mặc định `@Inherited` không áp dụng nếu không khai báo

Nếu bạn chỉ định nghĩa:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Policies.class)
@interface Policy {
    String value();
}
~~~

thì `Policy` **không** được kế thừa qua `@Inherited` chỉ vì nó là repeatable. Repeatable và inheritable là hai khả năng độc lập, cần định nghĩa riêng và đúng cả ở container.

## 13. Quy tắc `@Target`, `@Retention`, `@Inherited` và `@Documented` cho container

Một container được dùng bởi `@Repeatable` phải đáp ứng các ràng buộc hợp lệ của Java; ví dụ:

~~~java
@java.lang.annotation.Documented
@java.lang.annotation.Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@java.lang.annotation.Documented
@java.lang.annotation.Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}
~~~

Đây là mảnh mã minh họa. Các điểm cần kiểm tra:

- Container có **`Label[] value()`**; không dùng `String[] value()`, `List<Label>` hoặc một kiểu không chính xác.
- Những phần tử khác của container phải có default, để có thể hình thành container khi dùng annotation lặp.
- Retention của container **không được ngắn hơn** retention của annotation gốc; để reflection runtime hoạt động, dùng `RUNTIME` cho cả hai.
- `@Target` của container phải hợp lệ/tương thích với nơi annotation gốc được phép lặp. Sử dụng cùng tập target là lựa chọn dễ hiểu.
- Nếu annotation gốc có `@Inherited`, container cũng phải có `@Inherited`.
- Nếu annotation gốc có `@Documented`, container cũng phải có `@Documented`.

Nếu `@Label` chỉ được phép trên `TYPE`, đừng đặt nó trên parameter hoặc return type rồi nghĩ `@Repeatable` tự mở rộng phạm vi. `@Repeatable` chỉ thay đổi **số lần sử dụng cùng loại trên một phần tử hợp lệ**, không tự thay đổi target.

## 14. Type-use annotations: phải đọc đúng đối tượng `AnnotatedType`

Java 8 cho phép type-use annotation gắn lên **kiểu được dùng** (ví dụ kiểu trả về, kiểu tham số, generic type argument) thay vì gắn vào declaration của method hoặc parameter.

Giả sử:

~~~java
// Mảnh mã minh họa, @Mark có @Target(TYPE_USE), @Repeatable(Marks.class):
public @Mark("return-a") @Mark("return-b") String read(
        @Mark("input-a") @Mark("input-b") String input) {
    return input;
}
~~~

Hai `Mark` trước `String` trả về gắn với **return type**; hai `Mark` trước `String input` gắn với **parameter type**. Đọc chúng qua:

~~~java
// Mảnh mã minh họa:
Method method = ...;
Mark[] returns = method.getAnnotatedReturnType()
        .getAnnotationsByType(Mark.class);
Mark[] inputs = method.getAnnotatedParameterTypes()[0]
        .getAnnotationsByType(Mark.class);
~~~

Không nhầm với `method.getAnnotation(Mark.class)` (method declaration) hay `method.getParameters()[0].getAnnotation(Mark.class)` (parameter declaration). Nếu `Mark` chỉ có `TYPE_USE`, hai đường declaration không biểu diễn đúng vị trí bạn muốn.

### Với generic type argument

Với `List<@Mark("a") @Mark("b") String>`, hai annotation ở **type argument `String`**, không phải trên `List` ngoài cùng. Reflection cần kiểm tra `AnnotatedParameterizedType` rồi lấy `getAnnotatedActualTypeArguments()` trước khi đọc `getAnnotationsByType` ở node phù hợp.

Tương tự, array type có các mức component/dimension; những annotation ở cấp sâu cần đọc qua `AnnotatedArrayType`. Việc chỉ kiểm tra outer `AnnotatedType` không đủ để khẳng định toàn bộ cây kiểu không có annotation.

## 15. Ví dụ chạy hoàn chỉnh 4 — type-use annotation lặp và truy vấn trực tiếp

Tạo tệp **TypeUsePresenceDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.util.Arrays;

public class TypeUsePresenceDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @Repeatable(Details.class)
    @interface Detail {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Details {
        Detail[] value();
    }

    static final class Api {
        public @Detail("result-a") @Detail("result-b") String echo(
                @Detail("input-a") @Detail("input-b") String input) {
            return input;
        }
    }

    static String values(AnnotatedType type) {
        String[] values = Arrays.stream(
                type.getAnnotationsByType(Detail.class))
                .map(Detail::value)
                .toArray(String[]::new);
        return Arrays.toString(values);
    }

    public static void main(String[] args) throws Exception {
        Method m = Api.class.getDeclaredMethod("echo", String.class);
        AnnotatedType result = m.getAnnotatedReturnType();
        AnnotatedType argument = m.getAnnotatedParameterTypes()[0];

        System.out.println("return=" + values(result));
        System.out.println("parameter=" + values(argument));
        System.out.println("method-single=" +
                (m.getAnnotation(Detail.class) != null));
        System.out.println("result=" + new Api().echo("Java"));
    }
}
~~~

Chạy bằng JDK 17+ (phần annotation repeatable/type-use có từ Java 8):

~~~bash
javac TypeUsePresenceDemo.java
java TypeUsePresenceDemo
~~~

**Stdout chính xác:**

~~~text
return=[result-a, result-b]
parameter=[input-a, input-b]
method-single=false
result=Java
~~~

Kết quả `method-single=false` không chứng tỏ return type thiếu annotation: nó chỉ nói rằng **method declaration** không có annotation `Detail` được truy xuất theo API đó. Metadata của return/parameter type được đọc ở đúng đối tượng `AnnotatedType`.

Type-use annotation không tự thêm null-check, ép kiểu an toàn hoặc validation. Nó chỉ cung cấp metadata; muốn thực thi một hợp đồng phải có logic, checker hoặc framework hiểu đúng loại annotation đang sử dụng.

## 16. Thứ tự, trùng lặp và quy tắc hợp nhất trong ứng dụng

`getAnnotationsByType(T.class)` trả về một mảng các annotation phù hợp. Nhưng bản thân Java không diễn giải nghiệp vụ của mỗi annotation:

- **Thứ tự:** nếu một framework xử lý lần lượt các annotation, phải quy định thứ tự đó có tạo ưu tiên hay không. Không nên dựa vào thứ tự một cách vô ý khi các rule xung đột.
- **Trùng giá trị:** hai `@Rule("read")` là hai annotation cùng loại hợp lệ nếu repeatable. Java không tự dedup theo `value()`.
- **Xung đột:** `@Role("allow")` và `@Role("deny")` không tự có ý nghĩa kết hợp; framework phải quyết định OR/AND/deny-wins hoặc báo lỗi.
- **Kế thừa:** mặc định Java reflection có quy tắc thay thế: con có annotation cùng loại riêng sẽ chặn đường tìm annotation `ByType` từ cha; không tự hợp nhất.
- **Vắng mặt:** mảng rỗng không mặc định là “allow all” hay “deny all”. Cần chính sách riêng.
- **Container:** phải tránh double count khi vừa đọc `getAnnotationsByType` vừa lặp thủ công qua `Container.value()`.
- **Metadata động:** annotation runtime nằm trong class metadata; thay đổi cấu hình nghiệp vụ sau khi deploy cần cơ chế cấu hình riêng thay vì giả định annotation tự đổi.

### Ví dụ chính sách tổng hợp hierarchy có kiểm soát

Nếu doanh nghiệp yêu cầu **cộng dồn chính sách khai báo trên từng class cha** thay vì dùng quy tắc `@Inherited` có sẵn, có thể duyệt từng class:

~~~java
// Mảnh mã minh họa:
List<Rule> aggregate = new ArrayList<>();
for (Class<?> current = target;
        current != null && current != Object.class;
        current = current.getSuperclass()) {
    aggregate.addAll(Arrays.asList(
            current.getDeclaredAnnotationsByType(Rule.class)));
}
~~~

Đoạn trên cần import `List`, `ArrayList`, `Arrays`, biến `target` và annotation `Rule` đã định nghĩa. Nó **chủ động** gom các annotation khai báo theo hướng class con lên class cha. Đây **không phải** hành vi mặc định của `getAnnotationsByType`. Phải bổ sung định nghĩa rõ về thứ tự ưu tiên, trùng lặp, interface, phương thức override và xử lý security policy trước khi áp dụng thực tế.

### An toàn với metadata bảo mật

Nếu annotation phục vụ authorization, nên kiểm soát nghiêm ngặt trường hợp không có chính sách và lỗi đọc cấu hình. Không nên “thấy annotation nhưng không đọc đúng container” rồi mặc định cho phép truy cập. Thiết kế theo nguyên tắc bảo vệ tại ranh giới API, có test cho nhiều mức kế thừa và trường hợp có annotation riêng ở subclass.

## 17. Lỗi phổ biến và cách sửa

| Lỗi/ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `getAnnotation(T.class) == null` nghĩa là không có `T` | `T` có thể gián tiếp nằm trong container | Dùng `getAnnotationsByType(T.class)` |
| `getAnnotations().length` là số lượng rule lặp | API không mở container | Đếm mảng `ByType` |
| Class con phải tự có khai báo vì `getAnnotationsByType` thấy annotation | Kế thừa không phải sao chép declaration | So với `getDeclaredAnnotationsByType` |
| Có `@Inherited` thì luôn merge cha và con | Quy tắc associated có shadowing | Muốn merge phải tự duyệt hierarchy |
| Annotation trên interface sẽ tự xuất hiện ở class `implements` | `@Inherited` không hoạt động như vậy | Đọc interface riêng nếu hợp đồng yêu cầu |
| Annotation method cha tự sao chép vào method override | `@Inherited` không áp dụng như thế cho method | Chọn method declaration đúng, framework tự quy định |
| Thấy `@Tag` trên class con rồi cộng thêm container của cha theo reflection | Có thể double count hoặc sai shadowing | Dùng một đường `ByType` canonical |
| Không thấy `@Rule` runtime nên tưởng không có trong source | Retention có thể là `CLASS`/`SOURCE` | Chọn `RUNTIME` nếu cần runtime reflection |
| Container có `String[] value()` | Không thỏa `T[] value()` của repeatable | Dùng đúng loại annotation gốc |
| Gắn `TYPE_USE` rồi đọc bằng API của declaration | Sai đối tượng metadata | Đọc `AnnotatedType` đúng tầng |
| Giả định annotation tự enforce validation/nullability | Annotation không tự chạy code | Dùng checker/framework hoặc kiểm tra runtime |
| Không test case có một `@T` | Có thể bỏ sót direct annotation khi chỉ đọc container | Test 0/1/nhiều/explicit container |

## 18. Ma trận test thiết yếu

| Đầu vào metadata | Truy vấn | Kết quả kỳ vọng |
| --- | --- | --- |
| Không có `@T` | `getAnnotationsByType(T.class)` | Mảng rỗng |
| Một `@T` trực tiếp | `getAnnotation(T.class)` | Tìm được `T` |
| Hai `@T` lặp | `getAnnotation(T.class)` | Không mở container; thường null nếu không có thừa kế riêng |
| Hai `@T` lặp | `getAnnotationsByType(T.class)` | Hai phần tử |
| Container tường minh có hai `@T` | `getDeclaredAnnotationsByType(T.class)` | Hai phần tử |
| Class con không khai báo, `T` có `@Inherited` | `getAnnotationsByType(T.class)` | Các `T` từ superclass |
| Cùng class con đó | `getDeclaredAnnotationsByType(T.class)` | Mảng rỗng |
| Class con khai báo một `@T` riêng | `getAnnotationsByType(T.class)` | Chỉ `T` của class con |
| Class con khai báo hai `@T` riêng | `getAnnotationsByType(T.class)` | Hai phần tử của class con |
| Class chỉ implements interface có `@T` | `getAnnotationsByType(T.class)` | Không tự thừa kế qua interface |
| Method override không có annotation | Truy vấn `Method` của override | Không tự kế thừa method annotation |
| Hai `TYPE_USE` trên return type | `getAnnotatedReturnType().getAnnotationsByType(T.class)` | Hai phần tử nếu target/retention phù hợp |

Trong ứng dụng, bổ sung test theo trường hợp biên: annotation trùng `value`, xung đột khi subclass có cấu hình mới, container có thuộc tính khác ngoài `value`, và trường hợp loader không có annotation do retention chưa phù hợp.

## 19. Bài tập thực hành

**Bài 1 — Phân biệt bốn quan hệ.** Tự định nghĩa `@Marker` repeatable qua `@Markers` và có `@Inherited`. Cho class A một `@Marker`, class B hai `@Marker`, class C extends B nhưng không khai báo. Với từng class, xác định annotation `Marker` là directly present, indirectly present, present hay associated. Đối chiếu các API `getAnnotation`, `getAnnotationsByType`.

**Bài 2 — Container tường minh.** Tạo class `Manual` với `@Markers({@Marker("x"), @Marker("y")})` thay vì hai annotation riêng. So sánh `getDeclaredAnnotations().length`, `getDeclaredAnnotation(Marker.class)`, `getDeclaredAnnotation(Markers.class)` và `getDeclaredAnnotationsByType(Marker.class)`.

**Bài 3 — Shadowing.** Class cha có `@Marker("base-1")`, `@Marker("base-2")`; class con có `@Marker("child")`. Dùng `getAnnotationsByType` chứng minh chỉ thấy `child`. Viết utility riêng dùng `getDeclaredAnnotationsByType` đi dọc superclass chain để tạo danh sách cộng dồn, ghi rõ ưu tiên khi trùng giá trị.

**Bài 4 — Ranh giới `@Inherited`.** Đặt repeatable annotation trên interface và method. Tạo implementation và method override. Giải thích vì sao `@Inherited` không tự chuyển những annotation đó sang nơi mới. Viết reflection test.

**Bài 5 — Retention và target.** Cho annotation gốc có `RUNTIME` và container có `CLASS`, dự đoán lỗi khai báo. Sửa đúng meta-annotation rồi dùng reflection đọc nhiều annotation; thử chuyển cả hai về `CLASS` và quan sát kết quả runtime.

**Bài 6 — TYPE_USE.** Viết repeatable `@Qualifier` dùng `TYPE_USE`, đặt hai `@Qualifier` trên kiểu trả về và hai trên kiểu tham số. Truy vấn cả hai bằng `AnnotatedType.getAnnotationsByType`; phân biệt với `Method.getAnnotation`.

**Bài 7 — Thiết kế framework.** Xây bộ scanner `@Route` trong nhiều class. Quy định từ đầu: chỉ đọc declaration hiện tại hay thừa kế, có hỗ trợ annotation trên interface, cách giải quyết route trùng, và có ưu tiên subclass không. Viết test cho 0/1/nhiều route và container tường minh.

**Bài 8 — Phân tích lỗi đọc sai.** Một hệ thống dùng `getAnnotation(Permission.class)` để quyết định có kiểm tra quyền hay không. Khi developer thêm `@Permission` thứ hai, hệ thống bỗng không đọc được rule và bỏ qua kiểm tra. Giải thích nguy cơ, đổi sang `getAnnotationsByType`, và thiết kế hành vi mặc định an toàn nếu mảng rỗng/lỗi cấu hình.

## 20. Checklist cho người thiết kế annotation consumer

- Loại annotation cần đọc có `@Repeatable` không? Container là loại nào?
- Cặp annotation gốc/container có `value()`, `@Target`, `@Retention` tương thích không?
- Có yêu cầu `@Inherited` không? Nếu có, cả annotation gốc và container đã nhất quán chưa?
- Truy vấn cần **một annotation**, **mọi annotation logic**, hay **chính xác các annotation khai báo tại phần tử**?
- Có đang dùng `getAnnotation` để đoán số phần tử lặp không?
- Có đang vô tình đếm container và các annotation đã mở hai lần không?
- Quy tắc shadowing từ superclass có đúng với nhu cầu nghiệp vụ không?
- Annotation trên interface, method, field, parameter hoặc TYPE_USE đã được đọc đúng đối tượng chưa?
- Retention có cho phép runtime reflection đọc metadata không?
- Khi không có annotation, giá trị trùng hoặc xung đột, chính sách fallback đã an toàn và kiểm thử được chưa?
- Đã test 0/1/nhiều annotation, container tường minh, class con không khai báo và class con khai báo riêng chưa?

## 21. Tóm tắt

- **Directly present** nghĩa là annotation loại `T` nằm trực tiếp trên phần tử. **Indirectly present** nghĩa là có container chứa nhiều `T` trực tiếp trên phần tử.
- **Present** là quan hệ dùng khi truy vấn annotation đơn bằng `getAnnotation(T.class)`; **associated** là quan hệ dùng khi truy vấn nhiều annotation bằng `getAnnotationsByType(T.class)`, gồm mở container và kế thừa hợp lệ.
- `getDeclaredAnnotationsByType(T.class)` lấy nhiều `T` khai báo tại phần tử nhưng **không** kế thừa; `getAnnotationsByType(T.class)` có thể kế thừa từ superclass nếu `@Inherited` phù hợp.
- Với annotation lặp, class con khai báo một hoặc nhiều `T` riêng sẽ **không tự hợp nhất** `T` từ superclass trong mảng `ByType`. `@Inherited` không tự truyền metadata qua interface hay method override.
- Khi làm scanner hoặc framework, chọn đúng API theo ngữ nghĩa, phân biệt annotation gốc với container, và có chính sách rõ cho thứ tự, trùng lặp, xung đột, vắng mặt cùng các tình huống bảo mật.
