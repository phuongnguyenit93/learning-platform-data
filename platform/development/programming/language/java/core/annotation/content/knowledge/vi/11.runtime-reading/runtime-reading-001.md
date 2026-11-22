# Điều kiện RUNTIME và giao diện AnnotatedElement khi đọc Java Annotation

## 1. Vấn đề cần hiểu: annotation có trong mã nguồn chưa chắc đọc được lúc chạy

Khi nhìn vào mã:

```java
@Track("checkout")
class CheckoutService {}
```

ta có thể tưởng rằng chương trình luôn lấy được `@Track` bằng reflection. Điều này **chỉ đúng khi có đủ điều kiện**, đặc biệt là chính sách lưu giữ `@Retention(RetentionPolicy.RUNTIME)`, vị trí gắn annotation và cách truy vấn qua API phù hợp.

Trong Java, annotation là **metadata**; bản thân nó không chạy nghiệp vụ, không tạo logging hay validate tự động. Một chương trình, thư viện hoặc framework phải đọc metadata rồi chủ động thực thi hành vi liên quan.

Hai kiến thức cần kết nối là:

1. **`RetentionPolicy.RUNTIME`:** annotation được giữ để Java Reflection API có thể nhìn thấy sau khi JVM nạp class.
2. **`java.lang.reflect.AnnotatedElement`:** giao diện chung cung cấp các phương thức đọc annotation trên những phần tử phản chiếu, chẳng hạn class, method, field hoặc constructor.

Ví dụ khái niệm:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Track {
    String value();
}
```

Với định nghĩa đúng và một `CheckoutService` được chú thích, đoạn sau có thể đọc giá trị:

```java
Track track = CheckoutService.class.getAnnotation(Track.class);
if (track != null) {
    System.out.println(track.value());
}
```

Ví dụ này chỉ là đoạn mã **minh họa** cần các import thích hợp; một chương trình hoàn chỉnh có lệnh `javac`/`java` nằm ở mục 8.

## 2. Điều kiện bắt buộc: `@Retention(RetentionPolicy.RUNTIME)`

`@Retention` nằm trong `java.lang.annotation` và được đặt **trên kiểu annotation**, không phải trên từng nơi sử dụng annotation đó:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeInfo {
    String name();
}
```

Ba chính sách lưu giữ:

| Chính sách | Khi `javac` biên dịch nguồn | Trong class file | Có thể thấy qua reflection tiêu chuẩn? |
|---|---|---|---|
| `RetentionPolicy.SOURCE` | Có trong nguồn để compiler/processor xử lý | Không được giữ | Không |
| `RetentionPolicy.CLASS` | Có và được ghi vào class file | Có | Không |
| `RetentionPolicy.RUNTIME` | Có và được ghi vào class file | Có | Có |

Nếu **không có `@Retention`**, Java mặc định dùng `CLASS`:

```java
@interface NotRuntimeByDefault {
    String value();
}
```

Điều này hoàn toàn hợp lệ khi biên dịch. Tuy nhiên, nếu gắn `@NotRuntimeByDefault("x")` trên class, `Class.getAnnotation(NotRuntimeByDefault.class)` **không** trả về annotation đã gắn vì nó không có retention `RUNTIME`.

Để reflection truy cập được, cần bảo đảm:

- Annotation type khai báo `@Retention(RetentionPolicy.RUNTIME)`.
- Annotation thật sự được gắn vào **đúng thành phần** mà bạn truy vấn.
- `@Target`, nếu được khai báo, cho phép vị trí gắn tương ứng.
- Các class file được **biên dịch lại** sau thay đổi retention và được nạp từ đúng artifact/classpath.
- Chương trình sử dụng API phản chiếu phù hợp với vị trí annotation, kể cả quy tắc lặp và kế thừa khi liên quan.

**Phân biệt:** `@Target` trả lời “được chú thích ở đâu?”, còn `@Retention` trả lời “annotation được giữ đến khi nào?”. Một annotation có `@Target(METHOD)` và `@Retention(RUNTIME)` vẫn không xuất hiện trên đối tượng `Class` nếu nó chỉ được gắn lên method.

## 3. `AnnotatedElement` là gì?

`java.lang.reflect.AnnotatedElement` là interface của Java Reflection API dùng để truy vấn annotation trên một *element* có khả năng được chú thích.

Các kiểu cung cấp khả năng này gồm:

- `Class<?>`: khai báo kiểu, ví dụ class/interface/enum.
- `Method`: một method cụ thể.
- `Field`: một field.
- `Constructor<?>`: một constructor.
- `Parameter`: một tham số method/constructor.
- `Package`: metadata của package.
- `RecordComponent`: thành phần của Java record (Java 16+).
- `AnnotatedType`: biểu diễn những annotation gắn với **vị trí sử dụng kiểu** (*type use*), ví dụ kiểu trả về hoặc một type argument.

Ví dụ lấy các đối tượng cần truy vấn:

```java
Class<?> type = OrderService.class;                  // Class
Method method = type.getDeclaredMethod("submit");    // Method
Field field = type.getDeclaredField("orderId");      // Field
Constructor<?> ctor = type.getDeclaredConstructor(); // Constructor
```

Đây là đoạn minh họa, giả định `OrderService` có method `submit()`, field `orderId` và constructor không tham số, và lời gọi diễn ra trong ngữ cảnh có thể xử lý `ReflectiveOperationException`.

Một biến có thể giữ nhiều loại phần tử nhờ interface chung:

```java
AnnotatedElement element = OrderService.class;
```

Import tương ứng là:

```java
import java.lang.reflect.AnnotatedElement;
```

Nhờ đó, code dùng chung có thể nhận `AnnotatedElement` và hỏi về một kiểu annotation mà không cần viết một hàm riêng cho `Class`, `Method` hay `Field`.

### Phần tử khai báo và vị trí sử dụng kiểu là hai chuyện khác nhau

Ví dụ:

```java
@NonNull
String name;
```

Ý nghĩa của `@NonNull` phụ thuộc `@Target`: nó có thể là annotation trên field declaration, hoặc trên kiểu `String` được sử dụng tại đây (hoặc cả hai nếu target phù hợp). Khi cần đọc *type-use annotations*, các API qua `AnnotatedType` như `Field.getAnnotatedType()` mới là đường đi phù hợp; không mặc định rằng `Field.getAnnotation(...)` đọc mọi annotation trong chữ ký kiểu.

## 4. Các phương thức cốt lõi của `AnnotatedElement`

| Phương thức | Ý nghĩa chính | Kiểu trả về |
|---|---|---|
| `getAnnotation(A.class)` | Một annotation kiểu `A` đang *present* theo quy tắc API; không tự bung container lặp | `A` hoặc `null` |
| `getDeclaredAnnotation(A.class)` | Một annotation kiểu `A` được khai báo trực tiếp trên chính element | `A` hoặc `null` |
| `getAnnotations()` | Mảng annotation đang *present* trên element | `Annotation[]` |
| `getDeclaredAnnotations()` | Mảng annotation khai báo trực tiếp | `Annotation[]` |
| `getAnnotationsByType(A.class)` | Mảng annotation kiểu `A`, bao gồm giá trị trong container repeatable khi phù hợp | `A[]` |
| `getDeclaredAnnotationsByType(A.class)` | Các annotation `A` khai báo trực tiếp hoặc chứa gián tiếp ở **chính** element | `A[]` |
| `isAnnotationPresent(A.class)` | Kiểm tra một annotation kiểu `A` có *present* hay không | `boolean` |

Các API này nhận `Class<A>`, với `A` là một kiểu annotation cụ thể. Ví dụ:

```java
Audit audit = clazz.getAnnotation(Audit.class);
boolean audited = clazz.isAnnotationPresent(Audit.class);
```

Trong đó `clazz` là một `Class<?>` hợp lệ, còn `Audit` là annotation type đã định nghĩa.

Các nguyên tắc quan trọng:

- `getAnnotation(...)` và `getDeclaredAnnotation(...)` trả **một annotation** hoặc `null`; không trả `Optional`.
- `isAnnotationPresent(A.class)` có ý nghĩa tương đương việc `getAnnotation(A.class) != null`.
- `getAnnotationsByType(...)` trả **mảng**; nếu không có phần tử phù hợp thì là mảng rỗng, không phải `null`.
- Không dựa vào thứ tự bất kỳ của kết quả `getAnnotations()` giữa nhiều **kiểu khác nhau**. Với repeatable annotation, thứ tự các lần lặp được giữ theo quy tắc ngôn ngữ và API.
- `getAnnotationsByType` hiểu cơ chế chứa gián tiếp, còn `getAnnotation` không tự chuyển container thành một trong nhiều annotation con.

## 5. `getAnnotation` và `getDeclaredAnnotation` khác nhau khi nào?

Từ khóa **`Declared`** nhấn mạnh “được khai báo **trực tiếp tại phần tử này**”. API không có chữ `Declared` có thể có thêm quy tắc *present/inherited* cho annotation trên class.

Xét:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface ModuleGroup {
    String value();
}

@ModuleGroup("billing")
class ParentService {}

class ChildService extends ParentService {}
```

Khi đọc:

```java
ModuleGroup viaPresent =
        ChildService.class.getAnnotation(ModuleGroup.class);
ModuleGroup viaDeclared =
        ChildService.class.getDeclaredAnnotation(ModuleGroup.class);
```

Kết quả:

- `viaPresent` có thể lấy được annotation `ModuleGroup("billing")` qua quy tắc `@Inherited` trên superclass.
- `viaDeclared` là `null` vì `ChildService` không tự khai báo `@ModuleGroup`.

**`@Inherited` chỉ áp dụng cho annotation trên khai báo class khi tra cứu qua superclass.** Nó không tự áp dụng cho method override, field, constructor, interface được implements hoặc package. Một annotation trên interface cũng không tự xuất hiện khi query annotation của class implement interface.

Với một annotation `RUNTIME` **không có `@Inherited`**, cả `getAnnotation` lẫn `getDeclaredAnnotation` trên subclass chưa gắn annotation sẽ trả `null`.

### “Inherited method” không đồng nghĩa “annotation của method được kế thừa”

`ChildService.class.getMethod("run")` có thể trả về `Method` đại diện method public được khai báo ở superclass. Khi gọi `getAnnotation` trên chính `Method` đó, ta đang hỏi annotation của **method được phản chiếu**. Đây không phải cơ chế `@Inherited` cho method. Nếu subclass override method mà không gắn lại annotation, annotation của method cha không tự được sao chép sang method override.

Để tìm annotation từ method cha theo một quy tắc nghiệp vụ, chương trình phải chủ động đi qua phân cấp lớp và tra cứu method phù hợp.

## 6. Đọc annotation lặp: vì sao `getAnnotationsByType` quan trọng?

Giả sử một annotation lặp `@Tag` có container `@Tags`:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}

@Tag("core")
@Tag("backend")
class Example {}
```

Khi compiler thấy hai `@Tag` trên cùng class, các annotation lặp được chứa gián tiếp trong một annotation `@Tags`.

```java
Tag one = Example.class.getAnnotation(Tag.class);
Tag[] all = Example.class.getAnnotationsByType(Tag.class);
Tags container = Example.class.getAnnotation(Tags.class);
```

Với ví dụ trên:

- `one` là `null` vì không có `Tag` đơn lẻ trực tiếp *present* trên class sau khi chứa qua container.
- `all` là mảng gồm **hai `Tag`**, theo thứ tự `"core"` rồi `"backend"`.
- `container` khác `null` và `container.value()` chứa cả hai `Tag`.

Nếu chỉ có một `@Tag` trực tiếp, `getAnnotation(Tag.class)` có thể trả chính annotation ấy và container thường không xuất hiện.

**Quy tắc thực hành:** Nếu một kiểu annotation được đánh dấu `@Repeatable` và bạn muốn lấy **tất cả** lần xuất hiện, hãy dùng `getAnnotationsByType(T.class)` hoặc biến thể `getDeclaredAnnotationsByType(T.class)` tùy nhu cầu kế thừa. Không dùng `getAnnotation` làm phép đếm annotation lặp.

Để các annotation lặp có thể đọc ở runtime theo cách trên, retention của annotation lặp và container phải tương thích; thông thường cả hai cùng `RUNTIME`.

## 7. Annotation chỉ có `CLASS` có “biến mất” không?

Không. `RetentionPolicy.CLASS` giữ metadata trong class file, nhưng Java reflection tiêu chuẩn không trả về annotation ấy.

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BuildMarker {
}

@BuildMarker
class OrderWorker {}
```

Khi chạy:

```java
boolean found =
        OrderWorker.class.isAnnotationPresent(BuildMarker.class);
```

`found` bằng `false` mặc dù công cụ đọc bytecode sau biên dịch có thể tìm thấy metadata trong file `OrderWorker.class`.

Dùng `javap -v OrderWorker` để quan sát các thuộc tính class-file, ví dụ `RuntimeInvisibleAnnotations` cho một annotation declaration được lưu với retention `CLASS`. Annotation có `RUNTIME` thường có trong `RuntimeVisibleAnnotations`. Với annotation tại vị trí dùng kiểu, tên thuộc tính có thể kết thúc bằng `TypeAnnotations`.

Nếu mục tiêu là đọc bytecode bằng thư viện ASM hoặc công cụ phân tích classfile, `CLASS` có thể đủ. Nếu chương trình thật sự dùng `AnnotatedElement.getAnnotation` khi chạy, cần `RUNTIME`.

**Lưu ý:** Reflection và công cụ quét bytecode là hai đường tiêu thụ khác nhau. Một framework nói rằng nó “scan annotations” chưa đủ để suy ra retention nếu chưa biết nó đọc class bytes hay phản chiếu đối tượng `Class`.

## 8. Chương trình Java 17+ hoàn chỉnh: SOURCE/CLASS/RUNTIME, inherited và repeatable

Tạo một file duy nhất tên **`AnnotatedElementDemo.java`**:

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

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface CompileHint {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface BuildHint {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audit {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Group {
    String value();
}

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

@CompileHint
@BuildHint
@Audit("orders")
@Group("backend")
@Tag("core")
@Tag("api")
class BaseService {
    @Audit("submit")
    public void submit() {}
}

class ChildService extends BaseService {}

public class AnnotatedElementDemo {
    private static String tagsOf(AnnotatedElement element) {
        Tag[] tags = element.getAnnotationsByType(Tag.class);
        String[] names = Arrays.stream(tags)
                .map(Tag::value)
                .toArray(String[]::new);
        return Arrays.toString(names);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        AnnotatedElement element = BaseService.class;

        System.out.println("SOURCE visible="
                + element.isAnnotationPresent(CompileHint.class));
        System.out.println("CLASS visible="
                + element.isAnnotationPresent(BuildHint.class));
        System.out.println("RUNTIME value="
                + element.getAnnotation(Audit.class).value());
        System.out.println("tags=" + tagsOf(element));
        System.out.println("one direct Tag="
                + (element.getAnnotation(Tag.class) != null));
        System.out.println("container present="
                + element.isAnnotationPresent(Tags.class));

        System.out.println("child Group="
                + ChildService.class.getAnnotation(Group.class).value());
        System.out.println("child declares Group="
                + (ChildService.class.getDeclaredAnnotation(Group.class) != null));
        System.out.println("child Audit="
                + (ChildService.class.getAnnotation(Audit.class) != null));

        Method method = BaseService.class.getDeclaredMethod("submit");
        System.out.println("method Audit="
                + method.getAnnotation(Audit.class).value());
    }
}
```

Từ thư mục chứa file, chạy:

```bash
javac AnnotatedElementDemo.java
java AnnotatedElementDemo
```

Stdout mong đợi:

```text
SOURCE visible=false
CLASS visible=false
RUNTIME value=orders
tags=[core, api]
one direct Tag=false
container present=true
child Group=backend
child declares Group=false
child Audit=false
method Audit=submit
```

Diễn giải theo nhóm kết quả:

1. `CompileHint` và `BuildHint` được gắn ở nguồn, nhưng `AnnotatedElement` không nhìn thấy chúng bằng reflection: chính sách tương ứng là `SOURCE` và `CLASS`.
2. `Audit` có `RUNTIME`, nên đọc được `"orders"` từ class `BaseService`.
3. Hai `@Tag` trên class được compiler phối hợp trong `Tags`; `getAnnotationsByType(Tag.class)` trả đủ hai phần tử theo thứ tự, trong khi `getAnnotation(Tag.class)` không bung container.
4. `Group` có cả `@Inherited` và `RUNTIME`, vì vậy `ChildService` có thể tìm annotation từ `BaseService` bằng `getAnnotation(Group.class)`, nhưng `getDeclaredAnnotation(Group.class)` không tìm thấy một khai báo `Group` trực tiếp trên `ChildService`.
5. `Audit` **không** có `@Inherited`, nên `ChildService.class.getAnnotation(Audit.class)` trả `null` dù superclass có annotation ấy.
6. `Method` cũng là một `AnnotatedElement`. Tìm đúng method `submit` của `BaseService` cho phép đọc `@Audit("submit")`.

Trong ví dụ, chỉ `AnnotatedElementDemo` là public class, tên trùng file; các kiểu còn lại có quyền truy cập package-private nên có thể nằm chung một source file. Ví dụ sử dụng API có sẵn của Java 17, không yêu cầu thư viện ngoài.

## 9. Cách kiểm tra nhanh một thành phần có annotation hay không

Trong một bộ xử lý metadata, tránh gọi `.value()` trên kết quả `getAnnotation(...)` khi chưa kiểm tra `null`.

```java
static String describe(AnnotatedElement element) {
    Audit audit = element.getAnnotation(Audit.class);
    if (audit == null) {
        return "not audited";
    }
    return "audited: " + audit.value();
}
```

Đây là helper minh họa, dùng `Audit` đã định nghĩa ở mục 8.

Nếu chỉ cần một boolean:

```java
boolean annotated = element.isAnnotationPresent(Audit.class);
```

Khi cần đọc tất cả annotation bất kể kiểu:

```java
java.lang.annotation.Annotation[] annotations =
        element.getAnnotations();
```

Mảng này có thể chứa annotation container nếu annotation lặp nhiều lần; muốn dữ liệu của một kiểu repeatable, hãy dùng `getAnnotationsByType`.

Các API `getDeclaredAnnotations` và `getDeclaredAnnotationsByType` hữu ích khi logic muốn **chỉ xét metadata trên chính khai báo**, không nhận metadata kế thừa từ superclass.

## 10. Phản chiếu đúng vị trí: class, method, field, parameter, package, type-use

Giả sử có định nghĩa:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface Label {
    String value();
}
```

Các vị trí áp dụng:

```java
@Label("service")
class InvoiceService {
    @Label("identifier")
    private String id;

    @Label("operation")
    void send(@Label("recipient") String recipient) {}
}
```

**Cần lấy đúng `AnnotatedElement`:**

```java
Class<?> type = InvoiceService.class;
Label classLabel = type.getAnnotation(Label.class);

Field field = type.getDeclaredField("id");
Label fieldLabel = field.getAnnotation(Label.class);

Method method = type.getDeclaredMethod("send", String.class);
Label methodLabel = method.getAnnotation(Label.class);

Parameter parameter = method.getParameters()[0];
Label parameterLabel = parameter.getAnnotation(Label.class);
```

Đây là các đoạn minh họa chạy trong ngữ cảnh xử lý `ReflectiveOperationException` và import `java.lang.reflect.Field`, `Method`, `Parameter`. Từng đối tượng tương ứng một vị trí khác nhau, và annotation trên class **không tự động hiện trên method hoặc field**.

Với package annotations, lấy `SomeClass.class.getPackage()` rồi đọc metadata trên `Package`; cần một `package-info.java` có annotation và retention `RUNTIME` nếu muốn truy cập khi chạy.

Với type-use annotations, khai báo `@Target(ElementType.TYPE_USE)` và truy vấn `AnnotatedType` phù hợp. Chẳng hạn, với một field có type-use annotation, có thể lấy `field.getAnnotatedType()` rồi đọc annotation từ đối tượng ấy. Việc dùng `getAnnotations` trực tiếp trên `Field` không tương đương việc đọc tất cả annotation trên các vị trí kiểu bên trong field.

## 11. Những lỗi thường gặp khi đọc annotation qua reflection

### 11.1. Không có `@Retention(RUNTIME)` nhưng gọi `getAnnotation`

```java
@interface Config {
    String value();
}

@Config("fast")
class FastTask {}
```

`Config` mặc định có `RetentionPolicy.CLASS`. `FastTask.class.getAnnotation(Config.class)` trả `null`. Sửa bằng cách thêm `@Retention(RetentionPolicy.RUNTIME)` vào `Config` nếu đường xử lý cần reflection, và **biên dịch lại cả những class có sử dụng annotation**.

### 11.2. Nhầm class annotation với method annotation

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Work {}

class Worker {
    @Work
    void run() {}
}
```

Gọi `Worker.class.getAnnotation(Work.class)` không tìm được `@Work` vì nó gắn lên `run()`. Phải lấy đúng `Method`, chẳng hạn `Worker.class.getDeclaredMethod("run")` rồi gọi `getAnnotation(Work.class)`.

### 11.3. Đọc một annotation lặp bằng `getAnnotation`

Hai `@Tag` thường được lưu qua container, nên `getAnnotation(Tag.class)` có thể trả `null`. Dùng `getAnnotationsByType(Tag.class)` để lấy toàn bộ giá trị.

### 11.4. Trông chờ `@Inherited` hoạt động trên method hoặc interface

`@Inherited` chỉ có ý nghĩa kế thừa trên **class declaration** qua superclass theo điều kiện của API. Nếu override method hoặc implements interface, reflection không tự cộng những annotation tương ứng vào kết quả cho thành phần mới. Muốn quy tắc khác phải thiết kế hàm tra cứu riêng.

### 11.5. Dùng `getDeclaredAnnotations` rồi tưởng mất annotation runtime

Một class con có thể đọc annotation `@Inherited` từ class cha bằng `getAnnotations()` hoặc `getAnnotation(...)`, trong khi `getDeclaredAnnotations()` không có annotation ấy vì class con không khai báo trực tiếp. Đây là khác biệt **phạm vi tra cứu**, không phải retention bị sai.

### 11.6. Quên kiểm tra `null` hoặc mảng rỗng

`getAnnotation(...)` trả `null` khi không tìm thấy. `getAnnotationsByType(...)` trả một **mảng rỗng** khi không có annotation phù hợp. Xử lý đúng hai trường hợp thay vì gọi element method ngay trên một kết quả `null`.

### 11.7. Chỉ thay `@Retention` nhưng chạy lại file class cũ

Thay `SOURCE` hoặc `CLASS` thành `RUNTIME` trong định nghĩa annotation không tự cập nhật mọi nơi sử dụng đã biên dịch. Hãy làm sạch và biên dịch lại các class liên quan, sau đó kiểm tra classpath/JAR thực tế đang chạy. Có thể dùng `javap -v` để xác định annotation được giữ ở class file nào.

### 11.8. Cho rằng `RUNTIME` khiến framework tự động nhận annotation

`RUNTIME` chỉ cho phép metadata được phản chiếu. Một framework vẫn phải biết kiểu annotation, có phạm vi scan đúng và có code để xử lý. Nếu `@CustomRoute` hoàn toàn do bạn tự đặt mà router không hề đọc nó, không có tuyến URL nào được đăng ký tự động.

## 12. Lưu ý khi thiết kế API dùng `AnnotatedElement`

Một hàm nhận `AnnotatedElement` có thể hỗ trợ nhiều vị trí:

```java
static <A extends java.lang.annotation.Annotation>
A find(AnnotatedElement element, Class<A> annotationType) {
    return element.getAnnotation(annotationType);
}
```

Đây là helper tổng quát minh họa, cần import `java.lang.reflect.AnnotatedElement`. Tên `find` không có nghĩa hàm tự tra cứu cả superclass, method override hoặc container ngoài ngữ nghĩa mặc định của `getAnnotation`.

Nếu muốn hỗ trợ repeatable annotation, một API trả **mảng** thường phù hợp hơn:

```java
static <A extends java.lang.annotation.Annotation>
A[] findAll(AnnotatedElement element, Class<A> annotationType) {
    return element.getAnnotationsByType(annotationType);
}
```

Khi dùng code này trong ứng dụng thực tế:

- Xác định chức năng cần metadata **khai báo trực tiếp** hay chấp nhận kế thừa trên class.
- Xác định annotation type có thể lặp, và chọn API `ByType` khi cần nhận toàn bộ giá trị.
- Xác định thành phần `AnnotatedElement` nào được truyền vào, tránh nhầm annotation trên method với annotation trên class.
- Kiểm tra xử lý annotation thiếu, thiếu kiểu trong classpath hoặc các thay đổi không tương thích giữa phiên bản annotation và class được chú thích.
- Không biến metadata thành nguồn thông tin bí mật: annotation `RUNTIME` nằm trong artifact và có thể bị quan sát; ngay cả `CLASS` cũng có thể đọc từ bytecode.

## 13. Bài tập tự kiểm tra

Giả sử có các định nghĩa:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.CLASS)
@interface BinaryOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Inherited
@interface Owner {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Flags {
    Flag[] value();
}

@BinaryOnly
@Owner("platform")
@Flag("secure")
@Flag("logged")
class Parent {}

class Child extends Parent {}
```

Hãy trả lời:

1. `Parent.class.isAnnotationPresent(BinaryOnly.class)` trả gì?
2. `Parent.class.getAnnotation(Owner.class)` có giá trị gì?
3. `Child.class.getAnnotation(Owner.class)` có trả annotation không?
4. `Child.class.getDeclaredAnnotation(Owner.class)` trả gì?
5. `Parent.class.getAnnotation(Flag.class)` có đọc được cả hai `Flag` không?
6. `Parent.class.getAnnotationsByType(Flag.class)` có mấy phần tử?
7. `Child.class.getAnnotationsByType(Flag.class)` có tự nhận hai flag của Parent không?
8. Nếu muốn đọc `BinaryOnly` trong file `Parent.class` sau biên dịch, nên dùng loại công cụ nào?
9. Nếu muốn `BinaryOnly` được tìm bằng reflection chuẩn, phải đổi gì và cần làm gì sau đó?

Đáp án:

1. **`false`**: `BinaryOnly` chỉ có retention `CLASS`.
2. Một `Owner` có `value()` là `"platform"`.
3. **Có**: `Owner` có `@Inherited` và `RUNTIME`, nên được nhận từ superclass.
4. **`null`**: `Child` không khai báo `@Owner` trực tiếp.
5. **Không**: `getAnnotation(Flag.class)` không bung container lặp.
6. **Hai** phần tử, giá trị `"secure"` và `"logged"` theo thứ tự.
7. **Không**: `Flag` không có `@Inherited`, nên các flag trên `Parent` không tự được tra từ `Child`.
8. Công cụ đọc **class file/bytecode** như `javap -v` hoặc bytecode parser; reflection tiêu chuẩn không thấy retention `CLASS`.
9. Thêm `@Retention(RetentionPolicy.RUNTIME)` vào `BinaryOnly` và **biên dịch lại `Parent` cùng các nguồn liên quan**, sau đó xác nhận đang chạy artifact mới.

## 14. Checklist cuối bài

- Đã đặt `@Retention(RetentionPolicy.RUNTIME)` trên annotation type nếu cần runtime reflection.
- Không nhầm retention mặc định `CLASS` với `RUNTIME`.
- Phân biệt `@Retention` (vòng đời) với `@Target` (vị trí áp dụng).
- Đang gọi `getAnnotation` trên **đúng `AnnotatedElement`**: class, method, field, constructor, parameter, package hoặc `AnnotatedType` thích hợp.
- Dùng `getDeclaredAnnotation(s)` khi cần metadata trực tiếp; hiểu `getAnnotation(s)` có thể bao gồm annotation kế thừa trên class.
- Hiểu `@Inherited` giới hạn ở class/superclass; không suy luận kế thừa cho method/interface/package.
- Dùng `getAnnotationsByType` để lấy đủ các annotation repeatable được chứa gián tiếp.
- Kiểm tra `null` cho `getAnnotation` và xử lý mảng rỗng cho `getAnnotationsByType`.
- Phân biệt scanner bytecode nhìn thấy retention `CLASS` với Java reflection chỉ thấy `RUNTIME`.
- Rebuild các class đã sử dụng annotation sau khi đổi retention, kiểm tra đúng artifact/classpath.
- Cần một framework/tool **thực sự đọc metadata** mới có hành vi; gắn annotation một mình không thực thi logic.

Điểm then chốt: retention `RUNTIME` quyết định **khả năng quan sát metadata qua reflection**, còn `AnnotatedElement` cung cấp **giao diện đọc đúng thành phần**. Chọn đúng API, đúng đối tượng phản chiếu và đúng quy tắc kế thừa/lặp sẽ tránh phần lớn lỗi tưởng rằng annotation “biến mất” khi chạy.