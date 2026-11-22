# `getAnnotationsByType` so với `getDeclaredAnnotationsByType` trong Java

## 1. Vấn đề: “có annotation” và “tự khai báo annotation” khác nhau

Hai phương thức trên giao diện `java.lang.reflect.AnnotatedElement` đều nhận **một kiểu annotation** và trả về **mảng những annotation thuộc kiểu đó**:

```java
<A extends Annotation> A[] getAnnotationsByType(Class<A> annotationClass);
<A extends Annotation> A[] getDeclaredAnnotationsByType(Class<A> annotationClass);
```

Đây là **chữ ký rút gọn để giải thích**, không phải hai khai báo method cần tự viết. Trong Java thực tế, bạn gọi chúng trên đối tượng phản chiếu như `Class<?>`, `Method`, `Field`, `Constructor<?>` hoặc `Parameter`.

Chúng giống nhau ở chỗ:

- Trả về mảng `A[]`, **không trả `null`** khi không tìm thấy annotation tương ứng.
- Hỗ trợ **repeatable annotations**: nhận cả annotation trực tiếp và annotation được chứa gián tiếp trong *container annotation* theo quy tắc Java.
- Cần metadata có chính sách retention phù hợp với reflection, thường là `@Retention(RetentionPolicy.RUNTIME)` trên annotation type và container khi là repeatable annotation.

Chúng khác nhau ở phạm vi truy vấn:

- `getDeclaredAnnotationsByType(A.class)` chỉ lấy các annotation kiểu `A` **trực tiếp hoặc chứa gián tiếp tại chính phần tử đang xét**.
- `getAnnotationsByType(A.class)` lấy các annotation kiểu `A` **associated** với phần tử. Với **class** và annotation có `@Inherited`, nó còn có thể tìm lên superclass khi class hiện tại không có annotation `A` trực tiếp hoặc chứa gián tiếp.

Từ khóa dễ nhớ là **`Declared` = tại khai báo hiện tại**. Phần mở rộng đáng chú ý của phương thức không có `Declared` liên quan **kế thừa qua superclass của class**, chứ không phải mọi loại quan hệ giữa các phần tử Java.

## 2. Vị trí của hai API trong `AnnotatedElement`

`AnnotatedElement` là interface chung để quan sát annotation trên một phần tử phản chiếu. Những method dễ nhầm với nhau:

| Phương thức | Kết quả | Xử lý container repeatable | Có thể xét `@Inherited` trên class |
|---|---|---|---|
| `getAnnotation(A.class)` | Một `A` hoặc `null` | **Không tự bung** container `A[]` | Có, theo quy tắc *present* |
| `getDeclaredAnnotation(A.class)` | Một `A` hoặc `null` | **Không tự bung** container | Không |
| `getAnnotationsByType(A.class)` | Mảng `A[]` | **Có**, lấy các `A` chứa gián tiếp | Có, theo quy tắc *associated* |
| `getDeclaredAnnotationsByType(A.class)` | Mảng `A[]` | **Có**, nhưng tại chính element | Không |
| `getAnnotations()` | Mảng `Annotation[]` | Không tự thay container thành danh sách `A` | Có quy tắc *present* |
| `getDeclaredAnnotations()` | Mảng `Annotation[]` | Không tự thay container thành danh sách `A` | Không |

`getAnnotationsByType` **không chỉ là phiên bản số nhiều** của `getAnnotation`. Nó biết quan hệ giữa repeatable annotation và container đã khai báo bằng `@Repeatable`. Trong khi đó, `getAnnotation(A.class)` chỉ truy vấn một annotation có kiểu `A` theo quy tắc *present*, có thể trả `null` dù nhiều `@A` đang nằm trong container.

Ví dụ:

```java
A[] all = element.getAnnotationsByType(A.class);
A[] local = element.getDeclaredAnnotationsByType(A.class);
```

`element` ở đây là một `AnnotatedElement`, và `A` là annotation type đã được định nghĩa hợp lệ. Nếu cần lấy **mọi annotation lặp thuộc một kiểu**, hai method `ByType` là lựa chọn phù hợp hơn việc duyệt `getAnnotations()` rồi ép kiểu thủ công.

## 3. Vì sao hai method đều đọc được annotation trong container?

Giả sử định nghĩa:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

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
```

Và gắn hai annotation trên cùng class:

```java
@Label("stable")
@Label("reviewed")
class ReleaseService {}
```

Compiler sử dụng container ngầm để biểu diễn nhiều `@Label` tại vị trí này, tương ứng về mặt giá trị với:

```java
@Labels({@Label("stable"), @Label("reviewed")})
class ReleaseService {}
```

Hai đoạn khai báo class phía trên là **hai cách viết thay thế**; không ghép cả hai vào một file.

Tại `ReleaseService.class`:

```java
Label[] a = ReleaseService.class.getAnnotationsByType(Label.class);
Label[] b = ReleaseService.class.getDeclaredAnnotationsByType(Label.class);
```

Cả `a` và `b` đều gồm hai phần tử với `value` theo thứ tự `"stable"`, `"reviewed"`, vì hai `Label` được **chứa gián tiếp ngay tại chính class đó**. Không cần có `@Inherited` cho trường hợp này.

Ngược lại:

```java
Label one = ReleaseService.class.getAnnotation(Label.class);
Labels container = ReleaseService.class.getAnnotation(Labels.class);
```

Với trường hợp **hai** `@Label` được chứa qua `@Labels`, `one` là `null` còn `container` khác `null`. Điều đó không có nghĩa các `Label` bị mất; bạn đã truy vấn bằng API chỉ nhìn một `Label` *present* thay vì API hiểu cơ chế repeatable.

## 4. Khác biệt chính: kế thừa `@Inherited` từ superclass

`@Inherited` thuộc `java.lang.annotation`. Nếu annotation type có meta-annotation `@Inherited` và có retention `RUNTIME`, thì khi tra cứu annotation trên một **class**, Java Reflection API có thể tìm lên superclass.

Định nghĩa hợp lệ cho repeatable annotation có kế thừa:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

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
```

**Quan trọng:** Khi repeatable annotation `Tag` mang `@Inherited`, container `Tags` cũng phải mang `@Inherited` theo ràng buộc của Java. Container cũng phải có retention ít nhất bằng annotation lặp; trong ví dụ cả hai là `RUNTIME` để reflection quan sát được.

Các class:

```java
@Tag("parent-a")
@Tag("parent-b")
class Parent {}

class Child extends Parent {}
```

Truy vấn trên `Child.class`:

```java
Tag[] associated = Child.class.getAnnotationsByType(Tag.class);
Tag[] declared = Child.class.getDeclaredAnnotationsByType(Tag.class);
```

Kết quả:

- `associated`: hai tag `"parent-a"`, `"parent-b"` được tìm qua superclass `Parent`.
- `declared`: **mảng rỗng**. `Child` không khai báo `@Tag` cũng không khai báo container `@Tags` trên chính nó.

Đây là tình huống quan trọng nhất khiến hai API có kết quả khác nhau.

### Khi class con tự khai báo annotation thì sao?

```java
@Tag("local")
class ChildWithOwnTag extends Parent {}
```

Khi `ChildWithOwnTag.class` đã có một `@Tag` trực tiếp, `getAnnotationsByType(Tag.class)` trả về **`"local"`**, không mặc nhiên cộng thêm `"parent-a"` và `"parent-b"`. `getDeclaredAnnotationsByType(Tag.class)` cũng trả `"local"`.

**Kết luận thực hành:** `getAnnotationsByType` không phải hàm “gom tất cả tag của toàn bộ hệ phân cấp class”. Nó tuân theo quy tắc *associated*: khi class hiện tại có những annotation `Tag` trực tiếp hoặc chứa gián tiếp, kết quả tại class đó được ưu tiên; chỉ khi không có `Tag` ở class hiện tại và kiểu annotation cho phép kế thừa, quá trình tìm superclass mới phát huy tác dụng.

Nếu nghiệp vụ muốn *hợp nhất* tag của mọi superclass, chương trình phải viết thuật toán duyệt cây kế thừa và một quy tắc hợp nhất riêng.

## 5. Ba tình huống cần phân biệt khi kiểm tra một class

| Tình huống | `getAnnotationsByType(Tag.class)` | `getDeclaredAnnotationsByType(Tag.class)` |
|---|---|---|
| Class tự khai báo một `@Tag` | Một tag trên class | Một tag trên class |
| Class tự khai báo hai `@Tag` (container ngầm) | Hai tag trên class | Hai tag trên class |
| Class không khai báo tag nhưng superclass có tag có `@Inherited` | Các tag thích hợp từ superclass | Mảng rỗng |
| Class tự khai báo tag và superclass cũng có tag | Các tag trên chính class, không mặc định gộp thêm superclass | Các tag trên chính class |
| Class không khai báo tag, superclass có tag **không** `@Inherited` | Mảng rỗng | Mảng rỗng |
| Class không khai báo tag và không tìm thấy trên superclass | Mảng rỗng | Mảng rỗng |

Bảng dựa trên annotation và container có retention `RUNTIME`, các khai báo hợp lệ, và việc truy vấn trên **`Class<?>`**.

Một class con có thể kế thừa metadata từ **superclass gần nhất có annotation associated thích hợp**, nhưng không mặc định nối toàn bộ kết quả từ từng lớp cha. Đây là khác biệt cần lưu ý khi triển khai chính sách phân quyền, phân loại class hoặc cấu hình dựa trên annotations.

## 6. Ví dụ Java 17+ đầy đủ: chạy và so sánh hai API

Tạo file **`ByTypeLookupDemo.java`** với nội dung:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedElement;
import java.lang.reflect.Method;
import java.util.Arrays;

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
class BaseService {}

class ChildService extends BaseService {}

@Label("local")
class OverrideService extends BaseService {}

@Labels({@Label("explicit-A"), @Label("explicit-B")})
class ExplicitService {}

@Label("single")
class SingleService {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Tasks.class)
@interface Task {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Tasks {
    Task[] value();
}

class ParentMethods {
    @Task("parent-1")
    @Task("parent-2")
    public void run() {}
}

class ChildMethods extends ParentMethods {
    @Override
    public void run() {}
}

public class ByTypeLookupDemo {
    private static String labels(Label[] labels) {
        String[] values = Arrays.stream(labels)
                .map(Label::value)
                .toArray(String[]::new);
        return Arrays.toString(values);
    }

    private static void inspect(String name, AnnotatedElement element) {
        Label[] associated = element.getAnnotationsByType(Label.class);
        Label[] declared =
                element.getDeclaredAnnotationsByType(Label.class);
        System.out.println(name + " associated=" + labels(associated)
                + " declared=" + labels(declared));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        inspect("Base", BaseService.class);
        inspect("Child", ChildService.class);
        inspect("Override", OverrideService.class);
        inspect("Explicit", ExplicitService.class);
        inspect("Single", SingleService.class);

        Method parentMethod = ParentMethods.class.getDeclaredMethod("run");
        Method childMethod = ChildMethods.class.getDeclaredMethod("run");

        System.out.println("ParentMethods.run tasks="
                + parentMethod.getAnnotationsByType(Task.class).length);
        System.out.println("ChildMethods.run tasks="
                + childMethod.getAnnotationsByType(Task.class).length);
    }
}
```

Tại thư mục chứa file, dùng JDK 17 hoặc mới hơn:

```bash
javac ByTypeLookupDemo.java
java ByTypeLookupDemo
```

**Stdout chính xác:**

```text
Base associated=[base-A, base-B] declared=[base-A, base-B]
Child associated=[base-A, base-B] declared=[]
Override associated=[local] declared=[local]
Explicit associated=[explicit-A, explicit-B] declared=[explicit-A, explicit-B]
Single associated=[single] declared=[single]
ParentMethods.run tasks=2
ChildMethods.run tasks=0
```

Giải thích từng dòng:

1. **Base:** hai `@Label` được khai báo tại chính `BaseService`; cả hai API cùng trả hai giá trị.
2. **Child:** không khai báo `@Label`; `getAnnotationsByType` nhìn lên `BaseService` vì `Label` có `@Inherited`. `getDeclaredAnnotationsByType` chỉ xét `ChildService` nên trả mảng rỗng.
3. **Override:** class có một `@Label("local")` trực tiếp. Hai API đều thấy `"local"`; metadata trên `BaseService` không được tự động nối thêm.
4. **Explicit:** container `@Labels` viết tường minh. Cả hai API `ByType` đều bung danh sách `Label` của container.
5. **Single:** chỉ có một annotation `@Label` trực tiếp; cả hai API trả một phần tử.
6. **Method:** phương thức `run()` trên `ParentMethods` chứa hai `Task`. Method override ở `ChildMethods` không tự nhận annotation method của cha; `@Inherited` cũng không hỗ trợ kế thừa method annotation.

Ví dụ không phụ thuộc framework ngoài, giữ tên file trùng với public class `ByTypeLookupDemo`, và dùng các annotation retention `RUNTIME` để reflection đọc được.

## 7. Không phải phần tử nào cũng có quy tắc kế thừa

Hai method `ByType` nằm trên `AnnotatedElement` nên cũng có thể gọi với các kiểu phần tử không phải class:

```java
Method method = SomeClass.class.getDeclaredMethod("work");
Field field = SomeClass.class.getDeclaredField("id");
Constructor<?> ctor = SomeClass.class.getDeclaredConstructor();
```

Đây là các đoạn minh họa cần lớp `SomeClass` và các thành phần tương ứng được khai báo; nếu viết thành chương trình, cần import `java.lang.reflect.Method`, `Field` và `Constructor`, đồng thời xử lý checked exceptions.

Với **`Method`**, **`Field`**, **`Constructor`**, **`Parameter`** hoặc **`Package`**, không có cơ chế `@Inherited` kiểu superclass dành riêng như đối với đối tượng `Class<?>`. Vì vậy, hai phương thức `ByType` thường trả cùng các annotation trực tiếp và chứa gián tiếp trên **chính phần tử ấy**.

Một vài nhầm lẫn:

- Class con **override method**: method mới không tự nhận annotations của method cha.
- Class con **không override method**: `Child.class.getMethod("work")` có thể trả về đối tượng `Method` của method public được thừa hưởng từ superclass. Annotation đọc được là trên **method được phản chiếu**, không phải do `@Inherited` hoạt động trên method.
- Class **implements interface**: annotation `@Inherited` trên interface không tự trở thành annotation trên class implement interface.
- **Package/subpackage**: package con không kế thừa annotation của package cha.
- Annotation ở **vị trí sử dụng kiểu** (*type use*): cần truy vấn đúng `AnnotatedType` hoặc đối tượng phản chiếu tương ứng; hai method không tự đi tìm mọi vị trí annotation trong chữ ký kiểu.

Do đó, khác biệt giữa hai method `ByType` không phải luôn luôn nhìn thấy. Phải chọn đúng đối tượng phản chiếu và trường hợp kế thừa mới biểu hiện rõ.

## 8. `@Inherited` với container repeatable: kiểm tra cả hai annotation type

Khi một annotation là repeatable, Java cần một *container annotation*:

```java
@Repeatable(Container.class)
@interface Item {
    String value();
}

@interface Container {
    Item[] value();
}
```

Nếu muốn dùng `@Inherited` trên `Item`, phải đặt `@Inherited` trên **container `Container`**. Tương tự, retention của container phải ít nhất bằng retention của annotation lặp. Với mục tiêu đọc bằng reflection, cách đơn giản là khai báo cùng `RUNTIME` trên cả hai.

Ví dụ sai về cấu hình:

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(BrokenItems.class)
@interface BrokenItem {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface BrokenItems {
    BrokenItem[] value();
}
```

Đoạn này **cố ý không biên dịch** vì `BrokenItem` có `@Inherited` nhưng `BrokenItems` thiếu `@Inherited`.

Sửa thành:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface BrokenItems {
    BrokenItem[] value();
}
```

Đây là **phần thay thế riêng cho định nghĩa `BrokenItems` ở đoạn sai**, không đặt đồng thời hai khai báo trùng tên trong cùng file.

Ngoài ra, nếu annotation lặp có `@Documented` thì container phải có `@Documented`. Kiểu trả về của `Container.value()` phải là đúng mảng một chiều của annotation lặp, và mọi element phụ của container đều phải có `default`.

Các quy tắc này quan trọng vì `getAnnotationsByType` cần cơ chế container hợp lệ để tìm những annotation lặp, còn `@Inherited` quyết định khi nào nó được tìm tiếp trên superclass.

## 9. Phân biệt “trực tiếp”, “chứa gián tiếp”, “present” và “associated”

Java Reflection API dùng các thuật ngữ có ý nghĩa riêng:

- **Directly present:** annotation kiểu `T` xuất hiện trực tiếp trên element.
- **Indirectly present:** các `T` nằm trong container annotation mà Java nhận diện là container cho kiểu repeatable `T`.
- **Present:** quan hệ mà những API như `getAnnotation(T.class)` sử dụng; bao gồm trực tiếp và có thể kế thừa trên class theo `@Inherited`.
- **Associated:** quan hệ rộng hơn mà `getAnnotationsByType(T.class)` sử dụng; bao gồm trực tiếp, chứa gián tiếp và các tình huống kế thừa trên class theo quy tắc Java.

Vì vậy, đoạn:

```java
@Label("x")
@Label("y")
class C {}
```

có thể khiến `C.class.getAnnotation(Label.class)` trả `null` nhưng `C.class.getAnnotationsByType(Label.class)` trả mảng có hai phần tử. Đây là kết quả đúng: container chứa hai `Label` gián tiếp, còn `getAnnotation` không tự bung container.

Cũng cần phân biệt “`Declared`” ở hai dạng:

- `getDeclaredAnnotation(Label.class)`: trả tối đa **một `Label` trực tiếp**, không bung container.
- `getDeclaredAnnotationsByType(Label.class)`: trả **mọi `Label` trực tiếp hoặc chứa gián tiếp** trên chính element.

Vì vậy, chữ `Declared` **không** có nghĩa “chỉ annotation viết trực tiếp, không lấy phần tử trong container”. Khi dùng cùng hậu tố `ByType`, container vẫn được mở để thu thập các annotation phù hợp.

## 10. Khi nào chọn method nào?

| Nhu cầu | Method nên dùng | Lý do |
|---|---|---|
| Đọc toàn bộ một repeatable annotation, chấp nhận thừa hưởng trên class | `getAnnotationsByType(T.class)` | Hiểu container và `@Inherited` |
| Chỉ đọc annotation được gắn trên chính class, kể cả các lần lặp | `getDeclaredAnnotationsByType(T.class)` | Không tìm superclass |
| Đọc một annotation không lặp, chấp nhận kế thừa trên class | `getAnnotation(T.class)` | Trả một annotation hoặc `null` |
| Đọc một annotation không lặp, chỉ trên chính class | `getDeclaredAnnotation(T.class)` | Truy vấn khai báo trực tiếp |
| Kiểm tra có annotation không mà không cần giá trị | `isAnnotationPresent(T.class)` cho trường hợp một annotation *present*; hoặc `getAnnotationsByType(T.class).length > 0` cho repeatable | `isAnnotationPresent` không bung container repeatable |
| Lấy mọi kiểu annotation khác nhau dưới dạng thô | `getAnnotations()` / `getDeclaredAnnotations()` | Phù hợp cho inspection tổng quát, không tự bung repeatable |

Một phương thức dùng trong tool/framework:

```java
static <A extends java.lang.annotation.Annotation>
A[] readLocal(java.lang.reflect.AnnotatedElement element,
              Class<A> annotationType) {
    return element.getDeclaredAnnotationsByType(annotationType);
}
```

Đây là helper hoàn chỉnh về mặt cú pháp **khi đặt trong một class phù hợp**. Nó cho consumer quyết định lấy toàn bộ annotation lặp nhưng chỉ xét element hiện tại.

Bản chấp nhận kế thừa:

```java
static <A extends java.lang.annotation.Annotation>
A[] readAssociated(java.lang.reflect.AnnotatedElement element,
                   Class<A> annotationType) {
    return element.getAnnotationsByType(annotationType);
}
```

Hai helper giống nhau về kiểu trả về; khác biệt nằm trong semantics của API được gọi. Không nên đặt tên cả hai là `findAll` mà không mô tả phạm vi.

## 11. Những lỗi thường gặp

### Lỗi 1 — dùng `getAnnotation` để đọc annotation lặp

```java
Label label = BaseService.class.getAnnotation(Label.class);
```

Nếu `BaseService` có hai `@Label`, `label` là `null` vì chúng nằm trong container. Cần dùng `getAnnotationsByType(Label.class)` để nhận mảng hai phần tử.

### Lỗi 2 — dùng `getDeclaredAnnotationsByType` rồi kết luận superclass không có metadata

Với `ChildService extends BaseService` không khai báo tag, `getDeclaredAnnotationsByType(Label.class)` trả `[]` dù `BaseService` có hai tag. Nếu muốn cho phép kế thừa, dùng `getAnnotationsByType(Label.class)` và bảo đảm annotation type có `@Inherited`.

### Lỗi 3 — cho rằng `getAnnotationsByType` luôn hợp nhất mọi lớp cha

Nếu subclass đã khai báo một tag, kết quả là tag phù hợp trên subclass; không mặc định cộng toàn bộ tag của cha. Muốn tích lũy metadata qua cả cây superclass, phải chủ động duyệt và áp dụng quy tắc ưu tiên/hợp nhất.

### Lỗi 4 — thiếu `@Inherited` hoặc chỉ đặt trên annotation lặp

Không có `@Inherited` thì `getAnnotationsByType` trên subclass không tự tìm annotation từ superclass. Với repeatable annotation muốn có `@Inherited`, cả annotation lặp và container phải tuân thủ yêu cầu phối hợp, bao gồm `@Inherited` trên container.

### Lỗi 5 — thiếu `@Retention(RUNTIME)`

Nếu annotation chỉ có retention `CLASS` hoặc `SOURCE`, reflection không đọc được dù mã nguồn có `@T`. Cần retention `RUNTIME` thích hợp và biên dịch lại các class dùng annotation.

### Lỗi 6 — đọc nhầm element

Nếu annotation được gắn trên method, lấy annotation từ đối tượng `Method`, không gọi `SomeClass.class.getAnnotationsByType(...)` rồi mong nhìn thấy annotation method. Nếu annotation đặt ở package, cần truy vấn `Package`; nếu ở type-use, cần `AnnotatedType` phù hợp.

### Lỗi 7 — coi mảng rỗng là `null`

`getAnnotationsByType` và `getDeclaredAnnotationsByType` trả mảng rỗng khi không có annotation phù hợp. Cách kiểm tra thông thường:

```java
Label[] labels = type.getAnnotationsByType(Label.class);
if (labels.length == 0) {
    System.out.println("No labels");
}
```

`type` là `Class<?>` hợp lệ. Không dùng `if (labels == null)` để kiểm tra “không có label”.

### Lỗi 8 — bỏ qua explicit container

Nếu một class dùng container tường minh:

```java
@Labels({@Label("a"), @Label("b")})
class ContainerOnly {}
```

`getDeclaredAnnotationsByType(Label.class)` vẫn phải nhận đủ hai `Label` theo cơ chế repeatable. Không cần tự gọi `getAnnotation(Labels.class)` rồi tách `value()` khi chỉ muốn đọc các `Label`.

## 12. Câu hỏi tự kiểm tra

Xét cấu hình sau (chỉ là đoạn minh họa; các annotation có retention `RUNTIME`):

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Modes.class)
@interface Mode {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Modes {
    Mode[] value();
}

@Mode("A")
@Mode("B")
class Root {}

class Mid extends Root {}

@Mode("C")
class Leaf extends Mid {}
```

Hãy xác định:

1. `Root.class.getAnnotationsByType(Mode.class)` có bao nhiêu phần tử?
2. `Root.class.getDeclaredAnnotationsByType(Mode.class)` có bao nhiêu phần tử?
3. `Mid.class.getAnnotationsByType(Mode.class)` trả giá trị nào?
4. `Mid.class.getDeclaredAnnotationsByType(Mode.class)` trả giá trị nào?
5. `Leaf.class.getAnnotationsByType(Mode.class)` trả giá trị nào?
6. `Leaf.class.getDeclaredAnnotationsByType(Mode.class)` trả giá trị nào?
7. `Root.class.getAnnotation(Mode.class)` có trả một trong hai `Mode` không?
8. Nếu xóa `@Inherited` khỏi cả `Mode` và `Modes` rồi biên dịch lại, `Mid.class.getAnnotationsByType(Mode.class)` nhận gì?
9. Nếu `Mode` có `RUNTIME` nhưng `Modes` để mặc định `CLASS`, cấu hình repeatable có hợp lệ không?
10. Kết quả truy vấn annotation của method override có được quyết định bằng `@Inherited` của `Mode` không?

Đáp án và giải thích:

1. **Hai:** `A` và `B`, là các annotation trực tiếp/gián tiếp trên `Root`.
2. **Hai:** khai báo nằm ngay trên `Root`.
3. **Hai:** `A`, `B`, được nhận qua kế thừa trên superclass khi `Mid` không có `Mode` của riêng mình.
4. **Mảng rỗng:** `Mid` không tự khai báo `Mode` hoặc container.
5. **Một:** `C`; metadata trực tiếp trên `Leaf` được ưu tiên so với `A`, `B` của `Root`.
6. **Một:** `C` được khai báo trên `Leaf`.
7. **Không:** hai `Mode` được chứa trong container, nên `getAnnotation(Mode.class)` không bung danh sách.
8. **Mảng rỗng:** không có cơ chế `@Inherited` cho `Mode` và `Mid` không có annotation trực tiếp.
9. **Không:** container không được có retention ngắn hơn annotation lặp.
10. **Không:** `@Inherited` chỉ áp dụng cho annotation trên khai báo class qua superclass, không sao chép annotation của method override.

## 13. Checklist áp dụng trong dự án

- Chọn `getAnnotationsByType` khi cần cả container repeatable **và** cho phép inherited annotations trên class.
- Chọn `getDeclaredAnnotationsByType` khi chỉ cần metadata trên chính element nhưng vẫn muốn bung repeatable container.
- Biết `getAnnotation`/`getDeclaredAnnotation` trả một annotation hoặc `null`, không tự bung container.
- Kiểm tra annotation và container có retention phù hợp, thường là `RUNTIME` cho reflection.
- Nếu kỳ vọng inheritance trên class, định nghĩa annotation lặp với `@Inherited` và container cũng với `@Inherited`.
- Không nhầm inheritance của class annotation với annotation trên method override, field, interface hay package.
- Không mong `getAnnotationsByType` tự hợp nhất toàn bộ annotation từ mọi superclass khi subclass đã có giá trị tại chính nó.
- Xử lý kết quả là **mảng**, kể cả khi rỗng; không kiểm tra `null`.
- Truy vấn đúng đối tượng `AnnotatedElement` ứng với nơi annotation thực sự được gắn.
- Dùng thử cả trường hợp một `@T`, nhiều `@T`, container tường minh, class con trống và class con có `@T` riêng.
- Khi thay retention hoặc metadata của cặp repeatable/container, biên dịch lại nguồn có sử dụng annotation và kiểm tra kết quả reflection trên artifact thực tế.

Tài liệu đối chiếu: [`AnnotatedElement` trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html) và [`@Inherited` trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).

Hiểu được ranh giới giữa **associated** và **declared** giúp chọn API đúng: cả hai cùng thu thập annotation lặp bằng cơ chế container, còn khác biệt về inheritance chủ yếu xuất hiện khi truy vấn annotation `@Inherited` trên **class**.