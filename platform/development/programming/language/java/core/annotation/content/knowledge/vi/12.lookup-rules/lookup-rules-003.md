# `getAnnotations()` so với `getDeclaredAnnotations()` trong Java Reflection

## 1. Vấn đề: “có annotation” khác “khai báo annotation trực tiếp”

Trong Java, annotation là metadata gắn vào một khai báo hoặc vị trí sử dụng kiểu. Để tra cứu annotation ở **runtime**, Java cung cấp interface `java.lang.reflect.AnnotatedElement`. Những đối tượng phản ánh class, method, field, constructor, parameter và nhiều thành phần khác có thể sử dụng các phương thức của interface này.

Hai API quan trọng:

- **`getAnnotations()`**: trả về các annotation **present** (hiện diện) trên phần tử đang hỏi. Với **`Class`**, tập annotation hiện diện có thể bao gồm annotation từ superclass thông qua `@Inherited`.
- **`getDeclaredAnnotations()`**: trả về các annotation **directly present** (hiện diện trực tiếp) trên **chính phần tử đó**. API này bỏ qua annotation chỉ có nhờ kế thừa.

Đây là hai phương thức **không có đối số**, cùng trả về `java.lang.annotation.Annotation[]`:

~~~java
Annotation[] all = SomeClass.class.getAnnotations();
Annotation[] declared = SomeClass.class.getDeclaredAnnotations();
~~~

Sự khác biệt cốt lõi **không phải** “đọc public annotation” so với “đọc private annotation”, cũng **không phải** “đọc tất cả ở cây Java” so với “đọc duy nhất từng class theo mọi kiểu kế thừa”. Nó là khác biệt giữa **present** và **directly present** theo hợp đồng của `AnnotatedElement`.

Hai phương thức trả về **mảng rỗng** khi không có annotation phù hợp, không trả về `null`. Muốn tra cứu một loại annotation cụ thể, dùng API dạng số ít hoặc `...ByType` được trình bày bên dưới.

## 2. Bảng so sánh nhanh

| Đặc điểm | `getAnnotations()` | `getDeclaredAnnotations()` |
|---|---|---|
| Giá trị trả về | `Annotation[]` | `Annotation[]` |
| Ý nghĩa | Các annotation *present* trên phần tử | Các annotation *directly present* trên phần tử |
| Trên class có `@Inherited` ở annotation type | Có thể gồm annotation từ superclass | Không nhận annotation chỉ có trên superclass |
| Annotation của superclass **không** có `@Inherited` | Không tự lấy | Không tự lấy |
| Annotation trên interface đã `implements` | Không tự lấy qua `@Inherited` | Không tự lấy |
| Annotation trên method override | Không tự lấy từ method bị override | Không tự lấy |
| Method/field **đang được kế thừa** nhưng chưa override/hide | Chỉ phản ánh annotation của đối tượng `Method`/`Field` mà ta thực sự đang hỏi | Tương tự; bản thân đối tượng có thể là method/field ở class cha |
| Annotation `@Repeatable` dùng lặp nhiều lần | Mảng thô có thể chứa *container annotation* | Mảng thô có thể chứa *container annotation* |
| Không có kết quả | Mảng có độ dài 0 | Mảng có độ dài 0 |
| Yêu cầu khi dùng reflection runtime | Annotation cần `@Retention(RUNTIME)` để xuất hiện | Tương tự |

**Phạm vi tác động của `@Inherited` rất hẹp:** chỉ truy vấn annotation **trên class** dọc **superclass chain**; không biến các annotation ở method, field hay interface thành annotation được tự động kế thừa.

Một điểm khác: `getAnnotations()` và `getDeclaredAnnotations()` không bảo đảm thứ tự annotation theo thứ tự viết trong source. Nếu cần đầu ra ổn định cho test hoặc hiển thị, nên **sắp xếp** theo tên/type thay vì giả định thứ tự của mảng.

## 3. Ví dụ căn bản: annotation trên superclass

Xét chương trình rút gọn sau:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {}

@Region("base")
@LocalOnly
class Base {}

class Child extends Base {}
~~~

`Child` không khai báo trực tiếp annotation nào. Nhưng với `@Region`, annotation type được đánh dấu `@Inherited`:

~~~java
Region inherited = Child.class.getAnnotation(Region.class);
Region local = Child.class.getDeclaredAnnotation(Region.class);

System.out.println(inherited.value()); // base
System.out.println(local == null);       // true
~~~

Khi gọi trên `Child.class`:

- `getAnnotations()` có **`@Region("base")`** vì `Region` cho phép tìm theo superclass.
- `getDeclaredAnnotations()` là **mảng rỗng** vì header của `Child` không khai báo annotation nào.
- `@LocalOnly` không được trả về qua `getAnnotations()` trên `Child` vì annotation type **không** có `@Inherited`.
- `Base.class.getAnnotations()` và `Base.class.getDeclaredAnnotations()` đều nhìn thấy hai annotation `Region`, `LocalOnly` được khai báo trực tiếp tại `Base`.

Nếu `Child` tự khai báo:

~~~java
@Region("child")
class ChildWithOwnRegion extends Base {}
~~~

thì `ChildWithOwnRegion.class.getAnnotation(Region.class).value()` trả về `"child"`. Một annotation cùng type khai báo trực tiếp sẽ được chọn thay vì annotation được tìm từ superclass. Java **không trộn giá trị phần tử** của annotation con với annotation cha.

### 3.1. Điều kiện `@Retention(RUNTIME)`

Annotation type cần retention `RUNTIME` để kết quả hiển thị qua reflection ở runtime. Nếu bỏ `@Retention`, mặc định là `RetentionPolicy.CLASS`; metadata có thể được lưu trong file `.class`, nhưng không có nghĩa các API reflection runtime sẽ thấy annotation đó.

`@Inherited` **không** tự thay đổi retention. Một annotation có `@Inherited` nhưng retention không phải `RUNTIME` sẽ không tự xuất hiện khi gọi `Class.getAnnotations()` lúc chạy.

## 4. Khi có nhiều cấp kế thừa

Với chuỗi:

~~~java
@Region("root")
class Root {}

class Middle extends Root {}

class Leaf extends Middle {}
~~~

`Leaf.class.getAnnotation(Region.class)` có thể tìm `@Region("root")` dọc chuỗi `Leaf -> Middle -> Root`. Nếu `Middle` khai báo `@Region("middle")`, các truy vấn từ `Middle` và `Leaf` nhận `"middle"` trừ khi `Leaf` tự khai báo annotation đó.

Nhưng các API `getDeclaredAnnotation(Region.class)` hoặc `getDeclaredAnnotations()` gọi trên `Leaf.class` **không tự tìm** vào `Middle` hay `Root`: chỉ xét metadata trực tiếp của `Leaf`.

Khi sử dụng `getAnnotations()`, kết quả là **tập annotation present theo type**, không phải danh sách mọi lần xuất hiện của cùng một annotation type trên tất cả lớp cha. Nếu cần theo dõi annotation ở **từng cấp** để phục vụ migration, policy inheritance hay audit, hãy tự duyệt từng `getSuperclass()` và gọi `getDeclaredAnnotations()` tương ứng; đừng dùng `getAnnotations()` rồi suy ra lịch sử tất cả các lớp.

Ví dụ minh họa thuật toán kiểm tra theo từng tầng (độc lập với chương trình `Main.java` phía dưới):

~~~java
for (Class<?> c = Leaf.class; c != null; c = c.getSuperclass()) {
    System.out.println(c.getName());
    for (var annotation : c.getDeclaredAnnotations()) {
        System.out.println("  " + annotation.annotationType().getName());
    }
}
~~~

Thuật toán trên liệt kê annotation ở **mỗi class**, kể cả những annotation không có `@Inherited`. Đây là **chủ đích của code tự duyệt superclass**, không phải khả năng mặc định của `getAnnotations()`.

## 5. `@Inherited` không chạy qua interface

Giả sử:

~~~java
@Region("api")
interface Api {}

class Implementation implements Api {}
~~~

Mặc dù `Region` có `@Inherited`, hai truy vấn sau trên class `Implementation` đều không nhìn thấy `@Region("api")`:

~~~java
Implementation.class.getAnnotations();         // không chứa Region từ Api
Implementation.class.getDeclaredAnnotations(); // không chứa Region từ Api
~~~

`@Inherited` chỉ hỗ trợ **class kế thừa từ superclass**. Nó **không tìm interface**, kể cả khi interface gắn annotation có `@Target(TYPE)` và `@Inherited`. Một **interface con** cũng không tự nhận annotation của interface cha qua cơ chế `@Inherited`.

Nếu framework muốn xét annotation trên interface, nó phải định nghĩa và thực thi một **quy tắc duyệt interface hierarchy** riêng; đó không phải hợp đồng mặc định của `Class.getAnnotations()`.

## 6. Vì sao method override không được “thừa kế annotation”?

Một method ở class con khi **override** là một declaration mới. `@Inherited` không sao chép annotation từ method cha sang method override, dù bạn đặt `@Inherited` lên annotation type dành cho method.

~~~java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Checked {}

class Base {
    @Checked
    public void work() {}
}

class Child extends Base {
    @Override
    public void work() {}
}
~~~

Đối với `Child.work()`:

~~~java
var method = Child.class.getDeclaredMethod("work");

System.out.println(method.getAnnotations().length);         // 0
System.out.println(method.getDeclaredAnnotations().length); // 0
~~~

Đối với **method ở Base**:

~~~java
var method = Base.class.getDeclaredMethod("work");

System.out.println(method.isAnnotationPresent(Checked.class)); // true
~~~

Cả hai API trên đối tượng `Method` đang truy vấn annotation của **chính method declaration mà object phản ánh**. `getAnnotations()` **không đi tìm** annotation trên method bị override trong superclass. Muốn gắn `@Checked` ở method override, hãy đặt rõ tại method đó hoặc xây dựng một policy reflection tự duyệt hierarchy theo signature phù hợp.

### 6.1. Điểm dễ nhầm: `getMethod()` có thể trả về chính method kế thừa

Trường hợp `Child` **không override**:

~~~java
class ChildWithoutOverride extends Base {}
~~~

Khi gọi:

~~~java
var method = ChildWithoutOverride.class.getMethod("work");
System.out.println(method.getDeclaringClass().getSimpleName()); // Base
System.out.println(method.isAnnotationPresent(Checked.class)); // true
~~~

`Class.getMethod("work")` tìm method public khả dụng và có thể trả đối tượng `Method` được khai báo ở `Base`. Lúc đó cả `method.getAnnotations()` lẫn `method.getDeclaredAnnotations()` đều nhìn thấy annotation được khai báo **trực tiếp trên chính `Base.work()`**.

Như vậy, **annotation không lan từ method cha sang method con**; đơn giản là biến `method` đang trỏ tới **method cha**. Kiểm tra `Method.getDeclaringClass()` để tránh kết luận sai.

Quy tắc tương tự với field kế thừa: `Child.class.getField("name")` có thể trả về đối tượng `Field` khai báo ở superclass. Nếu subclass tạo field mới cùng tên để **hide** field cũ, hai field là hai declaration, annotation không tự sao chép sang field mới.

## 7. `getAnnotations()` không phải `getMethods()` hoặc `getDeclaredMethods()`

Cần phân biệt hai trục:

**Trục 1 — chọn member cần hỏi:**

- `Class.getMethod("work")` tìm public method thích hợp, có thể gồm method được kế thừa.
- `Class.getDeclaredMethod("work")` chỉ tìm method thực sự được khai báo tại class hiện tại.
- `Class.getField("id")` và `Class.getDeclaredField("id")` cũng khác nhau theo việc có tìm field được kế thừa hay không.

**Trục 2 — tìm metadata trên member đã chọn:**

- `method.getAnnotations()` xem annotation *present* trên đối tượng `Method`.
- `method.getDeclaredAnnotations()` xem annotation *directly present* trên chính method được biểu diễn.

Tên `getDeclaredAnnotations` không có nghĩa tự động tìm member thông qua `getDeclaredMethod`. Mỗi API thực hiện một **bước khác nhau**. Khi debug, ghi ra `getDeclaringClass()` để biết đối tượng reflection thật sự thuộc declaration nào.

## 8. Repeatable annotations: tại sao kết quả mảng đôi khi là annotation container?

Một annotation type có thể được phép lặp nhiều lần trên một declaration nhờ `@Repeatable`:

~~~java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("alpha")
@Tag("beta")
class ParentTags {}

class ChildTags extends ParentTags {}
~~~

Hai `@Tag` đặt trên `ParentTags` có thể được biểu diễn thành một **container annotation `@Tags`** trong metadata. Khi gọi:

~~~java
Annotation[] raw = ParentTags.class.getDeclaredAnnotations();
~~~

Trong ví dụ này, mảng `raw` chứa **`Tags`** (container) thay vì hai đối tượng `Tag` đứng riêng. Với `ChildTags`:

- `ChildTags.class.getAnnotations()` có thể chứa `Tags` **kế thừa từ ParentTags**; ở đây cả `Tag` và container `Tags` đều có `@Inherited`.
- `ChildTags.class.getDeclaredAnnotations()` vẫn rỗng vì `ChildTags` không khai báo trực tiếp annotation.
- `ChildTags.class.getAnnotationsByType(Tag.class)` trả **hai `Tag`** sau khi xét cơ chế repeatable/container và inheritance.
- `ChildTags.class.getDeclaredAnnotationsByType(Tag.class)` trả mảng rỗng vì không có `Tag` trực tiếp hoặc gián tiếp (qua container khai báo trực tiếp) ở Child.

Đây là điểm quan trọng: **`getAnnotations()` không tự bung toàn bộ repeatable annotation thành từng phần tử của annotation type gốc**. Hãy chọn API `...ByType` khi cần các annotation của một type có khả năng repeat.

Theo quy tắc Java, nếu repeatable annotation type dùng `@Inherited` thì annotation type dùng làm container cũng phải đáp ứng những ràng buộc tương ứng. Vì vậy, mẫu ví dụ cố ý đánh dấu **cả `Tag` và `Tags` bằng `@Inherited`**.

### 8.1. Bốn API dạng số ít và `ByType`

| API | Trả về | Đặc điểm |
|---|---|---|
| `getAnnotation(Tag.class)` | `Tag` hoặc `null` | Một annotation type trực tiếp/hiện diện theo API; không tự bung nhiều `Tag` trong container |
| `getDeclaredAnnotation(Tag.class)` | `Tag` hoặc `null` | Chỉ annotation type **directly present** |
| `getAnnotationsByType(Tag.class)` | `Tag[]` | Tự nhận biết repeatable và bóc container, xét cơ chế association/inheritance phù hợp |
| `getDeclaredAnnotationsByType(Tag.class)` | `Tag[]` | Tự nhận biết repeatable/container **được khai báo tại phần tử**, không lấy annotation từ superclass |

Nếu class có hai `@Tag`, `getAnnotation(Tag.class)` trong ví dụ có thể trả về `null` vì metadata trực tiếp là **`@Tags` container**; nhưng `getAnnotationsByType(Tag.class)` trả đủ cả hai giá trị. `getAnnotation(Tags.class)` có thể đọc trực tiếp container.

**Không nhầm `getDeclaredAnnotationsByType` với `getDeclaredAnnotations`:** cái thứ nhất hỗ trợ bóc container repeatable, cái thứ hai trả mảng annotation thô ở declaration.

Khi class con tự khai báo `Tag` cùng loại với annotation được kế thừa, cách chọn `@Repeatable` annotations theo `associated`/`indirectly present` có quy tắc riêng; đừng giả định `getAnnotationsByType` luôn nối dồn tất cả annotation ở mọi cấp cha-con.

## 9. Ví dụ hoàn chỉnh Java 17+ chạy được

Lưu toàn bộ nội dung sau vào **Main.java**. Ví dụ tự sắp xếp tên annotation theo alphabet để output không phụ thuộc vào thứ tự của mảng do reflection trả về.

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Region {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Inherited
@interface Checked {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Tags {
    Tag[] value();
}

@Region("base")
@LocalOnly
class Base {
    @Checked
    public void work() {}
}

class Child extends Base {}

@Region("own")
class OwnChild extends Base {}

class OverrideChild extends Base {
    @Override
    public void work() {}
}

@Tag("alpha")
@Tag("beta")
class ParentTags {}

class ChildTags extends ParentTags {}

public class Main {
    static String names(Annotation[] values) {
        String result = Arrays.stream(values)
                .map(a -> a.annotationType().getSimpleName())
                .sorted()
                .collect(Collectors.joining(","));
        return result.isEmpty() ? "-" : result;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base.all="
                + names(Base.class.getAnnotations()));
        System.out.println("child.all="
                + names(Child.class.getAnnotations()));
        System.out.println("child.declared="
                + names(Child.class.getDeclaredAnnotations()));
        System.out.println("child.region="
                + Child.class.getAnnotation(Region.class).value());
        System.out.println("child.region.declared="
                + (Child.class.getDeclaredAnnotation(Region.class) != null));
        System.out.println("own.region="
                + OwnChild.class.getAnnotation(Region.class).value());

        System.out.println("inherited.method.owner="
                + Child.class.getMethod("work")
                        .getDeclaringClass().getSimpleName());
        System.out.println("inherited.method.checked="
                + Child.class.getMethod("work")
                        .isAnnotationPresent(Checked.class));
        System.out.println("override.method.checked="
                + OverrideChild.class.getMethod("work")
                        .isAnnotationPresent(Checked.class));

        System.out.println("tags.parent.raw="
                + names(ParentTags.class.getAnnotations()));
        System.out.println("tags.child.raw="
                + names(ChildTags.class.getAnnotations()));
        System.out.println("tags.child.declared="
                + names(ChildTags.class.getDeclaredAnnotations()));
        System.out.println("tags.child.byType="
                + ChildTags.class.getAnnotationsByType(Tag.class).length);
        System.out.println("tags.child.declaredByType="
                + ChildTags.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("tags.parent.getAnnotation.Tag="
                + (ParentTags.class.getAnnotation(Tag.class) != null));
    }
}
~~~

Từ thư mục chứa `Main.java`, biên dịch và chạy:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả chuẩn:

~~~text
base.all=LocalOnly,Region
child.all=Region
child.declared=-
child.region=base
child.region.declared=false
own.region=own
inherited.method.owner=Base
inherited.method.checked=true
override.method.checked=false
tags.parent.raw=Tags
tags.child.raw=Tags
tags.child.declared=-
tags.child.byType=2
tags.child.declaredByType=0
tags.parent.getAnnotation.Tag=false
~~~

Giải thích:

1. `base.all=LocalOnly,Region`: hai annotation trực tiếp đều có retention runtime.
2. `child.all=Region`: `@Region` được tra qua superclass vì `@Inherited`; `@LocalOnly` không được tra qua superclass.
3. `child.declared=-` và `child.region.declared=false`: `Child` không khai báo trực tiếp annotation nào.
4. `own.region=own`: annotation trực tiếp của `OwnChild` được dùng thay cho `@Region("base")` ở superclass.
5. `inherited.method.owner=Base` và `inherited.method.checked=true`: `Child.class.getMethod("work")` trả về method ở Base, nên đọc được chính annotation của method đó.
6. `override.method.checked=false`: `OverrideChild.work()` là declaration mới, không tự nhận `@Checked` từ Base dù `Checked` được đánh dấu `@Inherited`.
7. `tags.parent.raw=Tags`: hai annotation `Tag` lặp lại được lưu/biểu diễn qua container `Tags`.
8. `tags.child.raw=Tags`, `tags.child.declared=-`: container kế thừa có thể được phản ánh qua `getAnnotations()` nhưng không phải annotation khai báo tại ChildTags.
9. `tags.child.byType=2`, `tags.child.declaredByType=0`: API `ByType` bóc container và xử lý inheritance, còn `DeclaredByType` chỉ xét annotation trực tiếp/gián tiếp tại ChildTags.
10. `tags.parent.getAnnotation.Tag=false`: dạng số ít không tự bung container thành nhiều `Tag`.

## 10. Các nhầm lẫn khác cần tránh

### 10.1. “Declared” không có nghĩa “chỉ public”

`getDeclaredAnnotations()` **không lọc theo modifier `public`, `private`, `protected`**. Nó phân biệt nguồn gốc metadata tại phần tử, không phải quyền truy cập. Một private method vẫn có thể mang annotation, và `getDeclaredMethod` vẫn có thể trả về đối tượng `Method` của private method.

### 10.2. “getAnnotations()” không quét tất cả superclass member

Một class có `getAnnotations()` thấy `@Region` kế thừa **không có nghĩa** mọi `Field` hoặc `Method` của class tự được gắn annotation từ superclass. Với member, hãy quan sát `getDeclaringClass()` và phân biệt method được kế thừa với method override.

### 10.3. Annotation ở superclass không hiện vì thiếu `@Inherited`

Với API runtime chuẩn, phải có annotation type đánh dấu `@Inherited` mới tra được annotation class-level từ superclass qua `getAnnotations()`. Thêm `@Retention(RUNTIME)` để reflection nhìn thấy metadata lúc chạy. Nếu cần truy cập annotation của mọi lớp cha **bất kể `@Inherited`**, phải tự duyệt và sử dụng `getDeclaredAnnotations()` trên từng lớp.

### 10.4. Annotation trên interface không tự xuất hiện ở implementing class

`@Inherited` không điều khiển interface hierarchy. Các framework có thể định nghĩa chiến lược tìm annotation sâu hơn, nhưng đó là logic **framework**, không phải mặc định của `Class.getAnnotations()`.

### 10.5. Số lượng trong `getAnnotations().length` khác số lượng tag viết trong source

Với `@Repeatable`, mảng từ `getAnnotations()` có thể có một **container** đại diện cho nhiều annotation cùng type. Khi cần đủ các annotation lặp lại, dùng `getAnnotationsByType()`.

### 10.6. Trông thấy annotation trong source nhưng runtime không đọc được

Nếu annotation type dùng retention `SOURCE` hoặc `CLASS`, reflection runtime không nhất thiết nhìn thấy nó. `@Target` quyết định vị trí áp dụng, còn `@Retention` quyết định vòng đời lưu metadata.

### 10.7. Nhầm declaration annotation với type-use annotation

`getAnnotations()` gọi trực tiếp trên `Field`/`Method` chủ yếu làm việc với **annotation của declaration**. Nếu annotation có `@Target(TYPE_USE)` và nằm **trên kiểu của field** hoặc **kiểu trả về của method**, dùng `getAnnotatedType()` hoặc `getAnnotatedReturnType()` và đọc metadata từ `AnnotatedType` tương ứng.

Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface CheckedType {}

class Example {
    @CheckedType String name;
}
~~~

Để kiểm tra annotation của **kiểu field**, dùng:

~~~java
var field = Example.class.getDeclaredField("name");
boolean exists = field.getAnnotatedType()
        .isAnnotationPresent(CheckedType.class);
~~~

Không dùng duy nhất `field.getAnnotations()` rồi kết luận type-use annotation không có.

### 10.8. Thay đổi mảng trả về không sửa metadata

Các API trả về mảng annotation không trao quyền chỉnh lại annotation trên class/method. Chẳng hạn đặt `result[0] = null` chỉ thay mảng cục bộ của caller; những lần gọi reflection sau vẫn theo metadata của class đang chạy.

## 11. Checklist chọn đúng API

- **Muốn đọc toàn bộ declaration annotation *present* trên class, có xét `@Inherited`?** Chọn `clazz.getAnnotations()`.
- **Chỉ muốn annotation do đúng class này khai báo?** Chọn `clazz.getDeclaredAnnotations()`.
- **Chỉ quan tâm một annotation type?** Chọn `getAnnotation(Foo.class)` hoặc `getDeclaredAnnotation(Foo.class)`; dạng số ít trả `null` nếu không thấy.
- **Annotation có thể lặp lại?** Chọn `getAnnotationsByType(Foo.class)` hoặc `getDeclaredAnnotationsByType(Foo.class)` để bóc container.
- **Đang đọc method hay field kế thừa?** In `getDeclaringClass()`; phân biệt `getMethod` với `getDeclaredMethod`.
- **Muốn đọc metadata từ interface hoặc mọi superclass dù không có `@Inherited`?** Tự định nghĩa thuật toán duyệt hierarchy và chính sách ghi đè/ưu tiên.
- **Annotation nằm trên type argument, return type hay field type?** Truy vấn `AnnotatedType`, không nhầm với declaration.
- **Không thấy annotation khi chạy?** Kiểm tra `@Retention(RUNTIME)`, `@Target`, API đang dùng và đối tượng reflection đang được hỏi.

## 12. Tài liệu chuẩn

- [Java SE 17 — `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): định nghĩa **present**, **directly present**, **associated**, **indirectly present** và các API `ByType`.
- [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getAnnotations`, `getDeclaredAnnotations`, `getMethod` và `getDeclaredMethod` trên class.
- [Java SE 17 — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): giới hạn inheritance annotation trên class và superclass.
- [Java SE 17 — `java.lang.annotation.Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): cơ chế annotation lặp lại và container.
- [JLS Java SE 17 `9.6.4.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): ngữ nghĩa chuẩn của `@Inherited`.

**Ghi nhớ:** `getAnnotations()` trả metadata annotation **present**, với class có thể bao gồm annotation tìm được từ superclass khi annotation type có `@Inherited`. `getDeclaredAnnotations()` chỉ trả metadata **trực tiếp** tại phần tử. Hai API không mặc định tìm interface, không lan annotation qua method override và không tự tách mọi repeatable annotation trong container; nếu cần hành vi khác, chọn đúng API `ByType` hoặc triển khai quy tắc tra cứu cụ thể.