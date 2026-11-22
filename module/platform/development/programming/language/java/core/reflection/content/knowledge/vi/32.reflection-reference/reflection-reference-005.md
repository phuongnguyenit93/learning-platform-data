# Bảng tra cứu: annotation trực tiếp, gián tiếp và được kế thừa trong Java Reflection

Một annotation viết trên class, method hoặc field chưa chắc được trả về từ mọi API tra cứu annotation. Kết quả phụ thuộc vào **annotation có tồn tại trong metadata runtime hay không**, **nó được gắn trực tiếp hay nằm bên trong repeatable container**, **đối tượng đang hỏi là class hay member**, và **loại annotation có `@Inherited` hay không**.

Java định nghĩa bốn thuật ngữ có ý nghĩa chính xác: **directly present**, **indirectly present**, **present** và **associated**. Nắm được bốn thuật ngữ này sẽ giúp bạn lựa chọn giữa `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType` và `getDeclaredAnnotationsByType` mà không phải đoán từ tên API.

> **Quy tắc nhanh:** Muốn tìm một annotation có thể được kế thừa, dùng `getAnnotation(T.class)`; muốn tìm annotation lặp lại **và** kế thừa, dùng `getAnnotationsByType(T.class)`. Muốn **chỉ tại phần tử hiện tại**, dùng các biến thể `getDeclared...` tương ứng. Nhưng trước hết annotation phải có `RetentionPolicy.RUNTIME` để Reflection chuẩn nhìn thấy.

## 1. Điều kiện tiên quyết: annotation còn tồn tại ở runtime

`@Retention` quy định chính sách giữ annotation sau biên dịch:

| Retention policy | Tồn tại trong class file | Reflection thông thường đọc bằng `getAnnotation(...)` |
|---|---|---|
| `RetentionPolicy.SOURCE` | Không giữ annotation gắn lên element trong class file | Không |
| `RetentionPolicy.CLASS` | Giữ trong class file nhưng không runtime-visible | Không |
| `RetentionPolicy.RUNTIME` | Giữ trong class file và runtime-visible | Có, nếu đúng element/cách tra cứu |

`CLASS` là retention mặc định nếu không khai báo `@Retention`. Với annotation dùng để điều khiển hành vi của framework tại runtime, thường cần viết rõ `@Retention(RetentionPolicy.RUNTIME)`.

Ví dụ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}
~~~

Đây là **mảnh khai báo**, không phải chương trình có `main`. `@Target(ElementType.TYPE)` nói rằng annotation gắn được lên declaration của class, interface, enum hoặc annotation type; nó **không đồng nghĩa** annotation tự được kế thừa từ interface.

Đọc annotation trên một class là:

~~~java
Category category = SomeClass.class.getAnnotation(Category.class);
~~~

Đoạn này giả định `SomeClass` đã được khai báo và được đặt `@Category(...)`; nó không tự chạy độc lập. Nếu kết quả là `null`, nguyên nhân có thể là annotation vắng mặt, `retention` không phù hợp, annotation ở một element khác hoặc không thỏa quy tắc kế thừa.

## 2. Bốn khái niệm: trực tiếp, gián tiếp, hiện diện, liên kết

Theo hợp đồng của `java.lang.reflect.AnnotatedElement` trong Java 17:

| Thuật ngữ Javadoc | Diễn giải | Ví dụ đặc trưng |
|---|---|---|
| **Directly present** (hiện diện trực tiếp) | Metadata runtime-visible trên chính element chứa instance annotation đó | `@Role("base")` gắn trực tiếp trên `Base` |
| **Indirectly present** (hiện diện gián tiếp) | Một repeatable annotation nằm **trong annotation container** trực tiếp trên element | Hai `@Label` trên `Base` được biểu diễn qua `@Labels` container |
| **Present** (hiện diện) | Directly present; hoặc annotation có tính kế thừa được tìm trên chuỗi superclass khi không có instance cùng loại trực tiếp trên class | `Child` không có `@Role` riêng nhưng `getAnnotation(Role.class)` thấy `@Role` của `Base` |
| **Associated** (liên kết) | Directly **hoặc** indirectly present; hoặc được kế thừa từ superclass khi không có trực tiếp/gián tiếp cùng loại trên class | `Child.getAnnotationsByType(Label.class)` trả hai nhãn của `Base` |

Trong trường hợp annotation **không repeatable**, không có bước mở container, nên sự khác biệt lớn chủ yếu là **declared/local** so với **kế thừa**. Với annotation **repeatable**, phải phân biệt cả hai trục:

~~~text
                              Có unwrap repeatable container?
                                  KHÔNG            CÓ
                               +-----------+--------------------+
Chỉ trên chính element         |  Declared | Declared ByType    |
Không đi lên superclass        |  Annotation|                    |
                               +-----------+--------------------+
Cho phép @Inherited             | Annotation| AnnotationsByType  |
trên chuỗi superclass          +-----------+--------------------+
~~~

Tên các ô trong sơ đồ rút gọn từ tên method `get...`. “Cho phép @Inherited” **không** có nghĩa method sẽ tự lấy annotation của interface hoặc method được override.

### Ví dụ trực tiếp và gián tiếp

~~~java
@Label("A")
@Label("B")
class Base {}
~~~

Ở Java hỗ trợ repeatable annotations, khi gắn nhiều `@Label`, compiler có thể đặt các nhãn bên trong annotation container `@Labels`. Vì vậy, ngay trên `Base`:

- `getDeclaredAnnotation(Label.class)` trả `null` nếu chỉ container `Labels` trực tiếp hiện diện.
- `getDeclaredAnnotationsByType(Label.class)` trả cả `Label("A")` và `Label("B")` nhờ “mở” container.
- `getAnnotation(Label.class)` cũng có thể trả `null` cho hai nhãn ở trong container, dù annotation nhìn rất rõ trong mã nguồn.
- `getAnnotationsByType(Label.class)` trả hai nhãn và còn có thể đi lên superclass theo `@Inherited` khi không có nhãn hiện diện trực tiếp/gián tiếp trên class con.

Ngược lại, với **một** `@Label("C")`, annotation thường trực tiếp hiện diện dưới loại `Label`: `getAnnotation(Label.class)` có thể trả chính nhãn đó.

**Quan trọng:** “Gián tiếp” ở đây **không có nghĩa** “annotation lấy từ superclass” theo cách dùng từ đời thường. Trong Javadoc `AnnotatedElement`, *indirectly present* dành cho repeatable annotation trong **container**. Kế thừa là quy tắc khác, tham gia vào *present* hoặc *associated*.

## 3. Bảng API đầy đủ: mỗi method nhận loại presence nào?

| API trên `AnnotatedElement` | Loại presence được xét | Mở container repeatable? | Có thể đi lên superclass? | Kết quả khi không tìm thấy |
|---|---|---|---|---|
| `getAnnotation(T.class)` | **Present** | Không | Có, với `@Inherited` trên class | `null` |
| `getAnnotations()` | **Present** cho từng loại annotation trực tiếp/kế thừa | Không mở riêng repeatable container | Có, với loại `@Inherited` | Mảng rỗng |
| `getDeclaredAnnotation(T.class)` | **Directly present** | Không | Không | `null` |
| `getDeclaredAnnotations()` | **Directly present** | Không mở riêng container | Không | Mảng rỗng |
| `getAnnotationsByType(T.class)` | **Associated** | **Có** | Có, với `@Inherited` trên class | Mảng rỗng |
| `getDeclaredAnnotationsByType(T.class)` | **Directly/indirectly present** | **Có** | Không | Mảng rỗng |
| `isAnnotationPresent(T.class)` | Tương đương `getAnnotation(T.class) != null` | Không | Có, với `@Inherited` trên class | `false` |

Đây là bảng theo **ngữ nghĩa Java 17** của `AnnotatedElement`. Tùy loại đối tượng, các method xuất hiện trên `Class`, `Method`, `Field`, `Constructor`, `Parameter`, `Package`...; nhưng **cơ chế `@Inherited` chỉ đi lên chuỗi class superclass**, không áp dụng chung cho mọi `AnnotatedElement`.

Trong hai method `get...AnnotationsByType(T.class)`, nếu `T` là repeatable annotation, Java tìm annotation container thích hợp, mở mảng `value()` trong container rồi trả các annotation con. Khi cùng element có nhiều annotation cùng loại, thứ tự được xác định như thể các annotation trong container xuất hiện tại vị trí container, theo thứ tự `value()`.

### Thí dụ chọn API đúng nhu cầu

| Câu hỏi | API phù hợp |
|---|---|
| Class có một `@Service` trực tiếp hoặc được kế thừa? | `type.getAnnotation(Service.class)` |
| Class **tự khai báo** `@Service`, bỏ qua superclass? | `type.getDeclaredAnnotation(Service.class)` |
| Class có những `@Route` nào (có thể nhiều và có kế thừa)? | `type.getAnnotationsByType(Route.class)` |
| Chỉ những `@Route` khai báo ngay trên class, kể cả repeatable? | `type.getDeclaredAnnotationsByType(Route.class)` |
| Liệt kê annotations trực tiếp ở class để hiển thị metadata thô? | `type.getDeclaredAnnotations()`, nhớ rằng có thể thấy container thay vì nhãn con |
| Liệt kê annotation đã được gắn trực tiếp hoặc được kế thừa? | `type.getAnnotations()`, không đồng nghĩa với flatten repeatables |
| Kiểm tra annotation trên method được override? | `method.getAnnotation(...)` trên đúng đối tượng `Method`, không giả định `@Inherited` hoạt động |

Trong code tổng quát, đừng dùng `getAnnotations()` rồi chỉ so tên annotation để “giải” repeatables nếu đã có `getAnnotationsByType(T.class)`. API ByType thể hiện chính xác nhu cầu và giúp xử lý container được định nghĩa bởi `@Repeatable`.

## 4. `@Inherited` hoạt động ở đâu và dừng khi nào?

`java.lang.annotation.Inherited` là một **meta-annotation** đặt trên declaration của annotation type. Nó cho phép tra cứu annotation từ **superclass của một class**, theo những quy tắc ở bảng trên. Ví dụ:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Role("base")
class Base {}

class Child extends Base {}
~~~

Đây là đoạn ví dụ minh họa cần imports như chương trình ở mục 6. `Child` không trực tiếp có `@Role`, nhưng `Child.class.getAnnotation(Role.class)` trả `Role("base")`, trong khi `getDeclaredAnnotation(Role.class)` trả `null`.

Các giới hạn rất quan trọng:

1. **Không thông qua interface:** Nếu interface `API` có `@Role` và class `Service implements API`, `Service.class.getAnnotation(Role.class)` **không** tự nhận `Role` từ interface. `Class.getInterfaces()` cho phép bạn tự duyệt nếu đó là chính sách framework, nhưng **đó là thuật toán riêng, không phải @Inherited mặc định**.
2. **Không áp dụng cho method/field/constructor:** `@Inherited` không làm method được override nhận annotation từ method ở base class. Nếu gọi `getMethod(...)` trên subclass mà nhận được `Method` do superclass khai báo (vì subclass **không override**), annotation có thể xuất hiện vì **bạn đang hỏi chính method của superclass**, không phải do annotation trên method được kế thừa.
3. **Subclass có annotation cùng loại:** Nếu một class trực tiếp khai báo `@Role("child")`, tra cứu `Role` trên subclass trả giá trị child, không cộng thêm base.
4. **Kế thừa theo loại annotation, không phải tổng hợp mọi instance:** Với `getAnnotationsByType`, nếu subclass đã có annotation cùng loại trực tiếp hoặc gián tiếp, API lấy những instance ở subclass; nó **không nối tự động** danh sách của subclass với superclass.
5. **`@Inherited` không làm thay đổi class file source của subclass:** Nó thay đổi logic tra cứu Reflection; `getDeclaredAnnotation` vẫn phân biệt rõ gì được khai báo ngay tại subclass.

Một hệ thống cần kế thừa annotation từ interface, method override hoặc tất cả superclass theo chính sách merge phải tự định nghĩa traversal, resolution order, xung đột và ưu tiên. Không thể gọi `getAnnotation` một lần rồi giả định JVM đã thực hiện chính sách tùy biến.

## 5. Repeatable annotations, container và kết hợp với inheritance

Một annotation type có thể lặp lại bằng `@Repeatable(Container.class)`:

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

Đoạn này là **mảnh khai báo** với imports thích hợp. `Labels` là container annotation. Nếu `Label` được đánh dấu `@Inherited`, **container `Labels` cũng phải được đánh dấu `@Inherited`** theo ràng buộc ngôn ngữ; việc quên điều này có thể làm chương trình không biên dịch.

Một số quy tắc:

- Chữ ký của container phải có element tên `value` với kiểu `Label[]`. Retention của container không được ngắn hơn retention của annotation được chứa; target của container phải tương thích.
- Khi viết hai `@Label` trên cùng một class, compiler thường lưu container `@Labels` thay cho hai annotation instance loại `Label` trực tiếp ở metadata runtime.
- `getAnnotationsByType(Label.class)` nhận cả annotation **directly** và **indirectly** present, nên phù hợp cho các loại repeatable.
- `getAnnotation(Label.class)` không tự mở container. Một lần hỏi `Label.class` trên class có hai nhãn lặp lại có thể trả `null`.
- **Local shadows inherited:** Khi superclass có `@Label("A")`, `@Label("B")` và subclass có `@Label("C")`, `subclass.getAnnotationsByType(Label.class)` trả `[C]`, **không** `[C, A, B]`.
- Trật tự của các annotation cùng loại được trả qua `...ByType` dựa trên thứ tự trong container tại vị trí container, thay vì thứ tự sắp xếp tùy ý. Nếu muốn output canonical của một tool, có thể sắp xếp riêng theo một khóa nghiệp vụ sau khi đọc, nhưng phải công bố quy tắc.

**Cảnh báo về container và inheritance:** Container cũng là một annotation type độc lập khi tra cứu metadata. Đừng trộn việc tra cứu `Labels.class` với `Label.class` rồi suy ra cùng một quy tắc merge. Muốn hỏi “tất cả nhãn Label gắn/được kế thừa theo hợp đồng repeatable”, hãy trực tiếp gọi `getAnnotationsByType(Label.class)`.

## 6. Chương trình Java 17+ minh họa và kiểm chứng kết quả

Lưu toàn bộ mã thành **`AnnotationPresenceDemo.java`**. Code không cần thư viện ngoài JDK. Chúng ta sẽ quan sát:

- `Role`: annotation không repeatable và có `@Inherited`.
- `Local`: annotation không có `@Inherited`.
- `Label`: annotation repeatable và có `@Inherited`, cùng container `Labels`.
- `Base` có hai `Label`, `Child` không gắn annotation mới, `OverrideChild` có annotation của chính mình.
- Interface `AnnotatedInterface` có `@Role` nhưng class triển khai không tự kế thừa annotation đó.
- Method `act` có `@MethodNote` ở base; subclass override không tự nhận, trong khi subclass không override vẫn truy xuất `Method` của base.

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;
import java.util.Arrays;

public class AnnotationPresenceDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Local {
        String value();
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

    @Role("base")
    @Local("local")
    @Label("A")
    @Label("B")
    public static class Base {}

    public static class Child extends Base {}

    @Role("child")
    @Label("C")
    public static class OverrideChild extends Base {}

    @Role("interface")
    public interface AnnotatedInterface {}

    public static class Implementation implements AnnotatedInterface {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface MethodNote {}

    public static class ParentMethods {
        @MethodNote
        public void act() {}
    }

    public static class OverridingMethods extends ParentMethods {
        @Override
        public void act() {}
    }

    public static class NonOverridingMethods extends ParentMethods {}

    private static String role(Role annotation) {
        return annotation == null ? "<none>" : annotation.value();
    }

    private static String labels(Label[] annotations) {
        return Arrays.toString(
                Arrays.stream(annotations).map(Label::value).toArray(String[]::new));
    }

    private static void report(String title, Class<?> type) {
        System.out.println(title);
        System.out.println("  Role getAnnotation = " +
                role(type.getAnnotation(Role.class)));
        System.out.println("  Role getDeclaredAnnotation = " +
                role(type.getDeclaredAnnotation(Role.class)));
        System.out.println("  Local getAnnotation = " +
                (type.getAnnotation(Local.class) != null));
        System.out.println("  Label getAnnotation = " +
                (type.getAnnotation(Label.class) != null));
        System.out.println("  Label getDeclaredAnnotationsByType = " +
                labels(type.getDeclaredAnnotationsByType(Label.class)));
        System.out.println("  Label getAnnotationsByType = " +
                labels(type.getAnnotationsByType(Label.class)));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        report("Base", Base.class);
        report("Child", Child.class);
        report("OverrideChild", OverrideChild.class);
        report("Implementation", Implementation.class);

        boolean parent = ParentMethods.class.getMethod("act")
                .isAnnotationPresent(MethodNote.class);
        boolean overriding = OverridingMethods.class.getMethod("act")
                .isAnnotationPresent(MethodNote.class);
        boolean nonOverriding = NonOverridingMethods.class.getMethod("act")
                .isAnnotationPresent(MethodNote.class);
        System.out.println("method ParentMethods = " + parent);
        System.out.println("method OverridingMethods = " + overriding);
        System.out.println("method NonOverridingMethods = " + nonOverriding);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 AnnotationPresenceDemo.java
java AnnotationPresenceDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
Base
  Role getAnnotation = base
  Role getDeclaredAnnotation = base
  Local getAnnotation = true
  Label getAnnotation = false
  Label getDeclaredAnnotationsByType = [A, B]
  Label getAnnotationsByType = [A, B]
Child
  Role getAnnotation = base
  Role getDeclaredAnnotation = <none>
  Local getAnnotation = false
  Label getAnnotation = false
  Label getDeclaredAnnotationsByType = []
  Label getAnnotationsByType = [A, B]
OverrideChild
  Role getAnnotation = child
  Role getDeclaredAnnotation = child
  Local getAnnotation = false
  Label getAnnotation = true
  Label getDeclaredAnnotationsByType = [C]
  Label getAnnotationsByType = [C]
Implementation
  Role getAnnotation = <none>
  Role getDeclaredAnnotation = <none>
  Local getAnnotation = false
  Label getAnnotation = false
  Label getDeclaredAnnotationsByType = []
  Label getAnnotationsByType = []
method ParentMethods = true
method OverridingMethods = false
method NonOverridingMethods = true
~~~

### Tại sao kết quả lại như vậy?

**`Base`:** `Role` và `Local` được khai báo trực tiếp nên `getAnnotation` tìm thấy. Hai `Label` được đặt trong container repeatable; vì vậy `getAnnotation(Label.class)` là `null`, nhưng cả hai API `...ByType` nhận `[A, B]`.

**`Child`:** không khai báo `Role` hoặc `Label` mới. `getAnnotation(Role.class)` đi lên `Base` vì `Role` có `@Inherited`, nhưng `getDeclaredAnnotation(Role.class)` không đi lên nên là `null`. `Local` không có `@Inherited` nên không thấy. `getDeclaredAnnotationsByType(Label.class)` là `[]`, trong khi `getAnnotationsByType(Label.class)` nhận `[A, B]` từ `Base`.

**`OverrideChild`:** có `@Role("child")` và `@Label("C")` trực tiếp; chúng che các giá trị cùng loại ở `Base` trong những phép tra cứu hiện diện/liên kết tương ứng. Một `Label` đơn lẻ trả về qua `getAnnotation(Label.class)`, và `getAnnotationsByType(Label.class)` là `[C]` chứ không ghép với `[A, B]`.

**`Implementation`:** chỉ `implements AnnotatedInterface`. Dù interface có `@Role("interface")` và `Role` có `@Inherited`, nó không được tìm qua cạnh `implements`, nên tất cả truy vấn `Role` trên `Implementation` đều vắng.

**`ParentMethods` / `OverridingMethods` / `NonOverridingMethods`:** method ở base trực tiếp có `@MethodNote`. Khi subclass override method bằng declaration mới không có annotation, Reflection trên `Method` mới không nhận được `@MethodNote`. Với subclass không override, `Class.getMethod("act")` trả về method public do superclass khai báo; kết quả `true` là annotation **của Method gốc**, không phải annotation đã “di truyền” sang một method mới.

## 7. Ma trận kết quả trọng tâm để tra nhanh

Từ chương trình phía trên, ta có hai bảng:

### 7.1. Annotation đơn (`Role`) và annotation không kế thừa (`Local`)

| Đối tượng `Class` | `getAnnotation(Role.class)` | `getDeclaredAnnotation(Role.class)` | `getAnnotation(Local.class)` |
|---|---|---|---|
| `Base` | `base` | `base` | Có |
| `Child` | `base` (kế thừa) | `null` | Không |
| `OverrideChild` | `child` | `child` | Không |
| `Implementation` | `null` (không lấy từ interface) | `null` | Không |

### 7.2. Annotation repeatable (`Label`)

| Đối tượng `Class` | `getAnnotation(Label.class)` | `getDeclaredAnnotationsByType(Label.class)` | `getAnnotationsByType(Label.class)` |
|---|---|---|---|
| `Base`: hai `@Label` | `null` | `[A, B]` | `[A, B]` |
| `Child`: không khai báo | `null` | `[]` | `[A, B]` (kế thừa) |
| `OverrideChild`: một `@Label("C")` | `Label("C")` | `[C]` | `[C]` |
| `Implementation` | `null` | `[]` | `[]` |

Bảng dùng cách viết `[A, B]` để chỉ **giá trị của `Label.value()`**, không phải chính chuỗi `toString()` của annotation proxy. Khi cần dữ liệu, lấy từng `Label` và gọi `value()`; đừng dựa vào chuỗi `toString()` làm định dạng trao đổi dữ liệu ổn định.

## 8. Những trường hợp dễ nhầm khi viết công cụ tra cứu

### 8.1. Lẫn `getDeclared...` với “private” hoặc “public”

Từ `declared` ở đây **không liên quan quyền truy cập public/private**. Nó nói về **metadata gắn ngay trên element hiện tại**, bỏ qua quy tắc kế thừa. `getDeclaredAnnotation` không “mạnh hơn” hoặc “vượt quyền” so với `getAnnotation`; nó chỉ có semantics khác.

Trên member, `getDeclaredAnnotations()` cũng không có nghĩa truy cập được private field value. Đọc annotation metadata khác với `Field.get` hoặc `Method.invoke`, vốn chịu quy tắc access riêng.

### 8.2. Lẫn annotation container với annotation được chứa

`getDeclaredAnnotations()` có thể trả `Labels` container trực tiếp, chứ không liệt kê hai `Label` ở cùng cấp. Việc dùng `getDeclaredAnnotationsByType(Label.class)` là cách đúng để nhận `Label` bên trong container.

Một framework cần hiển thị **nguyên trạng runtime annotation metadata** có thể quan tâm tới container. Framework cần đọc danh sách labels theo nghiệp vụ thường nên dùng ByType.

### 8.3. Mong `@Inherited` làm “merge sâu”

`getAnnotationsByType(Label.class)` trên `OverrideChild` cho `[C]`, không phải `[A, B, C]`. Nếu chính sách nghiệp vụ là “mọi labels trên toàn bộ superclass chain”, hãy viết thuật toán riêng:

~~~java
for (Class<?> current = targetClass;
        current != null;
        current = current.getSuperclass()) {
    Label[] local = current.getDeclaredAnnotationsByType(Label.class);
    // Tự quy định merge, ưu tiên và xử lý trùng lặp ở đây.
}
~~~

Đoạn này là **mảnh thuật toán**, cần đặt trong code có `Class<?> targetClass` và định nghĩa `Label`. Nó đọc đúng annotations của từng class mà không vô tình nhận giá trị `@Inherited` hai lần ở mỗi cấp. Nhưng kết quả merge **không phải** semantics mặc định của `getAnnotationsByType`.

Nếu muốn kế thừa annotation trên interface, còn phải chủ động duyệt `getInterfaces()` (có thể đệ quy), xử lý các nhánh hình thoi và nhiều interface có annotation xung đột. `@Inherited` không giải quyết xung đột đó giúp bạn.

### 8.4. Nhầm override với thừa kế `Method`

Một subclass **không override** có thể tìm được `Method` từ superclass bằng `getMethod(...)`, và `Method.getAnnotation(...)` thấy annotation trên declaration ấy. Subclass **override** tạo declaration khác; annotation trên method gốc không tự sao chép. Nếu framework muốn policy inheritance method annotations, cần tìm method tương ứng trên superclass/interfaces theo contract riêng.

### 8.5. Annotation target khác declaration target

Java còn hỗ trợ **type-use annotations** (ví dụ trên tham số kiểu, array component, generic type argument) thông qua `ElementType.TYPE_USE`. Đọc những annotation này có thể cần `AnnotatedType`, `Method.getAnnotatedReturnType()`, `Parameter.getAnnotatedType()` và các API liên quan, thay vì chỉ `Method.getAnnotations()`. Bảng ở đây dành cho semantics chung của `AnnotatedElement` khi hỏi đúng element; nó không phải lời hứa rằng annotation ở mọi vị trí cú pháp sẽ xuất hiện trên một `Class` hoặc `Method` nhất định.

### 8.6. Không đọc được không đồng nghĩa bytecode không có metadata

Annotation `CLASS` có trong class file nhưng không runtime-visible qua Reflection chuẩn. Annotation `SOURCE` có thể được annotation processor đọc ở compile time nhưng không còn sau compile. Nếu nhu cầu là phân tích cả annotation `CLASS` trong bytecode, cần bytecode parser/tool phù hợp; không cố dùng `getDeclaredAnnotations()` để khôi phục metadata không được Reflection công bố.

### 8.7. Khi annotation trả `null` / mảng rỗng

`getAnnotation(T.class)` và `getDeclaredAnnotation(T.class)` trả `null` khi không tìm thấy. Hai method `...ByType(T.class)` trả mảng độ dài `0`. Tránh:

~~~java
String name = targetClass.getAnnotation(Role.class).value();
~~~

Đây là **đoạn minh họa**: nếu annotation vắng, lời gọi `value()` gây `NullPointerException`. Có thể kiểm tra:

~~~java
Role role = targetClass.getAnnotation(Role.class);
if (role != null) {
    String name = role.value();
    // Dùng name theo nhu cầu ứng dụng.
}
~~~

Khi một annotation có giá trị mặc định, điều đó không có nghĩa `getAnnotation(...)` tự tạo annotation instance nếu nó không gắn trên element. Giá trị mặc định chỉ áp dụng **bên trong một annotation instance thực sự có mặt**.

## 9. Checklist áp dụng khi xây công cụ đọc annotation

Trước khi triển khai một annotation scanner, trả lời các câu hỏi:

1. **Annotation type có `RUNTIME` retention không?** Nếu không, Reflection không phải công cụ đọc phù hợp.
2. **Element cần hỏi là gì?** Class, method, field, parameter, package hay type-use? Đừng hỏi sai đối tượng.
3. **Có nhiều annotation cùng loại không?** Nếu có `@Repeatable`, dùng `...ByType` khi cần unpack container.
4. **Có muốn tìm annotation từ superclass không?** Với class và annotation `@Inherited`, dùng phương thức không có `Declared`.
5. **Có muốn merge annotations nhiều cấp không?** Nếu có, tự định nghĩa thuật toán và dùng `getDeclaredAnnotationsByType` tại từng cấp để kiểm soát.
6. **Có muốn nhận annotation từ interfaces không?** Mặc định `@Inherited` không làm việc đó.
7. **Có tìm metadata method override không?** Nếu có, xác định rõ đọc declaration nào, rồi tự thiết kế policy.
8. **Có kết hợp repeatable và inherited không?** Container cần tuân thủ `@Inherited`/`@Retention`/`@Target` tương thích; kiểm thử các subclass khai báo nhãn mới.
9. **Có cần kết quả ổn định khi serialize?** Không dựa vào thứ tự tổng quát của `getAnnotations()` hoặc `toString()` annotation; chuẩn hóa key và thứ tự theo contract tool.
10. **Có cần phân biệt không tìm thấy và lỗi đọc metadata không?** Một số lời gọi Reflection có thể phát sinh lỗi metadata (ví dụ loại annotation không hợp lệ hoặc class tham chiếu bị thiếu), không nên gom mọi exception thành “annotation không có”.

## 10. Bài tập tự kiểm tra

1. Đổi `@Local` thêm `@Inherited` rồi chạy lại ví dụ. `Child` có thấy `Local` không? `Implementation` có thấy từ interface không?
2. Bỏ một trong hai `@Label` trên `Base`. Khi còn **một** `@Label`, dự đoán `getAnnotation(Label.class)` và `getDeclaredAnnotationsByType(Label.class)`.
3. Giữ `Base` có `[A, B]` nhưng thay `OverrideChild` bằng hai nhãn `[C, D]`. Dự đoán `getAnnotation(Label.class)`, `getDeclaredAnnotationsByType` và `getAnnotationsByType`.
4. Xóa `@Role("child")` trên `OverrideChild`. Sau khi biên dịch sạch, so sánh kết quả `getAnnotation(Role.class)` và `getDeclaredAnnotation(Role.class)`.
5. Trên `AnnotatedInterface.class`, đọc `@Role`; trên `Implementation.class`, đọc cùng annotation. Giải thích vì sao kết quả khác nhau.
6. Bỏ `@Override`/method override trong `OverridingMethods` (chỉ giữ `extends ParentMethods`). Khi `getMethod("act")`, đối tượng `Method` hiện có `getDeclaringClass()` là gì?
7. Viết hàm `allLabels(Class<?>)` gom nhãn từ toàn bộ superclass chain bằng `getDeclaredAnnotationsByType`, loại trùng theo `value` và tài liệu hóa thứ tự ưu tiên.
8. Đổi retention `Label` thành `CLASS` và chỉnh container tương thích. Compiler/Reflection còn trả những gì? Vì sao compile-time processor vẫn có thể làm việc với annotation `CLASS` nhưng runtime Reflection chuẩn thì không?
9. Thiết kế bảng so sánh `getAnnotations()` và `getDeclaredAnnotations()` cho `Base`/`Child`, nêu container nào xuất hiện và phân biệt “liệt kê container” với “unwrap Label”.

**Tổng kết:** “Directly present” = annotation instance trên chính element; “indirectly present” = repeatable annotation trong container; “present” = trực tiếp hoặc được kế thừa theo `@Inherited`; “associated” = trực tiếp/gián tiếp hoặc được kế thừa phù hợp. `getAnnotation` theo **present**, `getDeclaredAnnotation` theo **direct**, `getAnnotationsByType` theo **associated**, `getDeclaredAnnotationsByType` theo **direct + indirect**. `@Inherited` chỉ giải quyết tra cứu qua class superclass, không qua interface/method override, và không cộng gộp mọi cấp khi class con đã có annotation cùng loại.

### Tài liệu tham khảo chính thức (Java 17)

- [`AnnotatedElement` — định nghĩa bốn presence kinds, API matrix](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [`Inherited` — giới hạn và cách hoạt động](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html)
- [`Repeatable` — annotation container](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html)
- [`RetentionPolicy` — SOURCE, CLASS, RUNTIME](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [JLS 17, `9.6.3` — repeatable annotation types và containing annotation types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3)
