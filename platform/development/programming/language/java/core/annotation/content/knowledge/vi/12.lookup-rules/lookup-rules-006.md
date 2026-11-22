# Phối hợp annotation lặp với @Inherited trong Java

Khi một annotation được đánh dấu `@Repeatable`, bạn có thể gắn nhiều lần cùng loại annotation lên cùng một khai báo. Khi annotation đó đồng thời dùng `@Inherited`, Java Reflection có thể tìm các annotation ấy **qua quan hệ kế thừa lớp**. Tuy nhiên, kết quả không đơn giản là “lấy annotation của cha rồi nối thêm annotation của con”.

**Quy tắc quan trọng nhất:** với `getAnnotationsByType(AnnotationType.class)` trên một lớp, **nếu lớp hiện tại khai báo trực tiếp hoặc gián tiếp những annotation thuộc loại được hỏi thì dùng các annotation đó; nếu không và loại đó có `@Inherited`, có thể tìm lên superclass**. Điều này thường dẫn đến **thay thế danh sách từ cha**, không tự động hợp nhất danh sách.

Để làm đúng, bạn còn phải khai báo `@Inherited` phù hợp **trên cả annotation lặp và container**, chọn retention `RUNTIME` nếu muốn đọc bằng Reflection, và phân biệt rõ `getAnnotationsByType` với các API chỉ đọc một annotation hoặc chỉ đọc khai báo trực tiếp.

## 1. Nhắc lại hai cơ chế độc lập

### 1.1. @Repeatable tạo khả năng xuất hiện nhiều lần

Một repeatable annotation có container tương ứng:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}
```

`@Role` là loại annotation được lặp. `@Roles` là **container**, có phần tử tên chính xác `value()` và kiểu trả về `Role[]`. Khi dùng:

```java
@Role("read")
@Role("write")
class Service {
}
```

compiler có thể biểu diễn hai `@Role` qua container `@Roles`. Khai báo `@Repeatable` không tự tạo container: bạn phải tự định nghĩa `@interface Roles` với chữ ký hợp lệ.

### 1.2. @Inherited kiểm soát tìm kiếm qua superclass

`@Inherited` là **meta-annotation** dành cho annotation type. Nó quy định rằng trong các phép tra cứu Reflection phù hợp, một annotation trên **class cha** có thể được tìm thấy trên **class con** chưa khai báo annotation tương ứng.

```java
import java.lang.annotation.Inherited;

@Inherited
@interface Marker {
}
```

`@Inherited` không có nghĩa JVM sao chép annotation vào source hoặc vào `.class` của lớp con; nó ảnh hưởng **ngữ nghĩa tra cứu bằng Reflection**. Nó chỉ áp dụng theo chuỗi **superclass của class**, không tự lấy annotation từ interface đã `implements`, cũng không tự kế thừa annotation trên method, field hay parameter.

Một annotation chỉ có `@Inherited` mà không `@Repeatable` không tự cho phép sử dụng lặp. Tương tự, annotation chỉ có `@Repeatable` không tự được kế thừa trong các API Reflection.

## 2. Cặp annotation hợp lệ khi kết hợp @Repeatable và @Inherited

Khai báo dùng ở phần lớn ví dụ:

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
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

Vai trò của từng thành phần:

1. `@Repeatable(Roles.class)` **gắn trên `Role`** để cho phép lặp loại `Role`.
2. `Roles.value()` bắt buộc trả về **`Role[]`**, tức mảng một chiều của chính annotation được lặp; không phải `String[]`, `Role` đơn lẻ hay `List<Role>`.
3. `@Inherited` **trên `Role`** cho phép tra cứu `Role` theo quy tắc kế thừa.
4. **Container `Roles` cũng phải có `@Inherited`** vì `Role` được đánh dấu `@Inherited`; đây còn là ràng buộc hợp lệ của repeatable annotation type.
5. `@Retention(RUNTIME)` trên **cả hai** để Reflection có thể thấy annotation/container lúc chạy.
6. `@Target(TYPE)` của hai annotation tương thích để gắn lên những khai báo kiểu cần thiết.

**Quan trọng:** nếu `Role` có `@Inherited` nhưng `Roles` không có `@Inherited`, compiler sẽ từ chối định nghĩa cặp repeatable annotation. Không thể “vá” bằng cách thêm một `@Inherited` ở chỗ sử dụng trên class; `@Inherited` phải được khai báo trên **loại annotation**.

Retention cũng phải tương thích: nếu `Role` có `RUNTIME`, `Roles` không được dùng `CLASS` hoặc `SOURCE`. Nếu quên `@Retention` thì mặc định `CLASS`; các API Reflection trong bài sẽ không trả những annotation này.

### Vì sao container cũng cần @Inherited?

Khi hai `@Role` cùng gắn trên một lớp, compiler biểu diễn chúng qua **`@Roles`**. Trong class file, thứ mà Java Reflection nhìn thấy như annotation trực tiếp khi hỏi loại container là `@Roles`, chứa `Role[]`.

Vì thế cả hai phần phải tham gia một cấu hình nhất quán. `@Inherited` của `Role` nói rằng phép tra cứu theo loại `Role` có thể dùng superclass; `@Inherited` của container bảo đảm loại chứa những lần lặp cũng được đánh dấu đúng như các ràng buộc của ngôn ngữ.

Không nên tưởng tượng `@Repeatable` tự biến mọi annotation trong mảng thành các annotation khai báo trực tiếp riêng lẻ trên lớp con.

## 3. Chương trình Java 17+ đầy đủ: kiểm tra từng trường hợp kế thừa

Tạo một file duy nhất tên **`InheritedRepeatableDemo.java`**:

```java
import java.lang.annotation.*;
import java.util.Arrays;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("base-read")
@Role("base-write")
class BaseService {
}

class ChildService extends BaseService {
}

@Role("local")
class LocalService extends BaseService {
}

@Role("local-a")
@Role("local-b")
class LocalPairService extends BaseService {
}

@Roles({@Role("manual-a"), @Role("manual-b")})
class ExplicitService extends BaseService {
}

@Roles({})
class EmptyContainerService extends BaseService {
}

@Role("iface")
interface Contract {
}

class Implementation implements Contract {
}

public class InheritedRepeatableDemo {
    static void inspect(Class<?> type) {
        Role[] associated = type.getAnnotationsByType(Role.class);
        Role[] declared = type.getDeclaredAnnotationsByType(Role.class);

        String a = Arrays.toString(
                Arrays.stream(associated)
                      .map(Role::value)
                      .toArray(String[]::new));
        String d = Arrays.toString(
                Arrays.stream(declared)
                      .map(Role::value)
                      .toArray(String[]::new));

        System.out.println(type.getSimpleName()
                + " | byType=" + a
                + " | declared=" + d
                + " | container=" + (type.getAnnotation(Roles.class) != null));
    }

    public static void main(String[] args) {
        inspect(BaseService.class);
        inspect(ChildService.class);
        inspect(LocalService.class);
        inspect(LocalPairService.class);
        inspect(ExplicitService.class);
        inspect(EmptyContainerService.class);
        inspect(Implementation.class);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 InheritedRepeatableDemo.java
java InheritedRepeatableDemo
```

Stdout chính xác:

```text
BaseService | byType=[base-read, base-write] | declared=[base-read, base-write] | container=true
ChildService | byType=[base-read, base-write] | declared=[] | container=true
LocalService | byType=[local] | declared=[local] | container=true
LocalPairService | byType=[local-a, local-b] | declared=[local-a, local-b] | container=true
ExplicitService | byType=[manual-a, manual-b] | declared=[manual-a, manual-b] | container=true
EmptyContainerService | byType=[base-read, base-write] | declared=[] | container=true
Implementation | byType=[] | declared=[] | container=false
```

**Kiểm chứng:** ví dụ này đã được biên dịch bằng `javac --release 17` và chạy thực tế; các dòng stdout được đối chiếu.

## 4. Phân tích kết quả từ lớp cha sang lớp con

### 4.1. Lớp cha có hai annotation lặp

```java
@Role("base-read")
@Role("base-write")
class BaseService {}
```

`BaseService.class.getAnnotationsByType(Role.class)` trả hai phần tử `Role`, lần lượt chứa `"base-read"` và `"base-write"`. Còn `getDeclaredAnnotationsByType(Role.class)` cũng trả hai phần tử vì chúng **xuất phát từ chính khai báo lớp đó**, dù có thể được biểu diễn qua container.

Nếu dùng `BaseService.class.getAnnotation(Roles.class)`, API lấy một annotation container và có thể truy cập mảng `Role[]` bằng `value()`.

### 4.2. Lớp con không có Role riêng: nhận từ superclass

```java
class ChildService extends BaseService {}
```

Vì `ChildService` không có `Role` được khai báo trực tiếp hoặc gián tiếp tại lớp con và `Role` là annotation kế thừa, `ChildService.class.getAnnotationsByType(Role.class)` trả **hai annotation Role của cha**.

Tuy nhiên:

```java
ChildService.class.getDeclaredAnnotationsByType(Role.class)
```

trả **mảng rỗng**, vì không có `Role` nào do chính `ChildService` khai báo. Từ “declared” trong API rất quan trọng: nó bỏ qua các giá trị đến từ superclass.

### 4.3. Lớp con có một Role riêng: không nối thêm của cha

```java
@Role("local")
class LocalService extends BaseService {}
```

`LocalService.class.getAnnotationsByType(Role.class)` trả **chỉ một phần tử `"local"`**, không trả ba phần tử `["base-read", "base-write", "local"]`.

Lý do: loại `Role` đã có **một lần xuất hiện trực tiếp** trên lớp con. Khi loại được hỏi đã hiện diện theo luật associated annotations tại lớp hiện tại, Reflection **không tiếp tục lấy các `Role` của superclass để nối thêm**.

Điều này khác với nhiều kiểu “hợp nhất cấu hình” mà framework có thể tự cài đặt.

### 4.4. Lớp con có hai Role riêng: thay toàn bộ danh sách của cha

```java
@Role("local-a")
@Role("local-b")
class LocalPairService extends BaseService {}
```

`getAnnotationsByType(Role.class)` trả `["local-a", "local-b"]`. Hai lần dùng ở lớp con được container `Roles` của lớp con chứa; chúng **thay thế** danh sách tìm qua superclass trong kết quả `Role` của API này.

**Quy tắc thực dụng:** nếu một lớp con khai báo một hoặc nhiều `Role` để tùy chỉnh danh sách, hãy xem danh sách đó như bộ cấu hình `Role` dành riêng cho lớp con khi dùng `getAnnotationsByType`, không phải “phần chênh lệch” tự cộng vào cha.

### 4.5. Lớp con dùng container tường minh

```java
@Roles({@Role("manual-a"), @Role("manual-b")})
class ExplicitService extends BaseService {}
```

Kết quả `getAnnotationsByType(Role.class)` là `["manual-a", "manual-b"]`, giống trường hợp viết hai `@Role` riêng lẻ. API có khả năng **mở container** hợp lệ để lấy danh sách các annotation `Role`.

Việc viết container tường minh không làm thay đổi kiểu dữ liệu bên trong: `Roles.value()` vẫn là `Role[]`.

### 4.6. Container rỗng: một góc cạnh đáng chú ý

```java
@Roles({})
class EmptyContainerService extends BaseService {}
```

Đây là trường hợp dễ dự đoán sai.

Trong ví dụ Java ở mục 3:

- `getDeclaredAnnotationsByType(Role.class)` trả **mảng rỗng** vì container tại lớp con chứa không có `Role` nào.
- `getAnnotationsByType(Role.class)` lại trả **`["base-read", "base-write"]`** do không có một `Role` trực tiếp/gián tiếp nào từ lớp con, nên quy tắc kế thừa của `@Inherited` cho phép tìm lên superclass.
- `getAnnotation(Roles.class)` vẫn có thể trả container `Roles` tồn tại trên lớp con, dù `Roles.value()` là mảng rỗng.

Vì vậy, **đặt `@Roles({})` không phải cách đáng tin để “xóa” toàn bộ `Role` từ lớp cha khi dùng `getAnnotationsByType(Role.class)`**. Nếu nghiệp vụ cần trạng thái tắt kế thừa, hãy mô hình hóa một marker/giá trị “disable/override” có ý nghĩa rõ ràng và xử lý nó trong tầng tiêu thụ metadata.

Đây là hệ quả của các quy tắc Reflection về annotation *directly present*, *indirectly present* và *associated*, không phải lỗi của Java.

### 4.7. Implement interface không mang theo Role

```java
@Role("iface")
interface Contract {}

class Implementation implements Contract {}
```

`Implementation.class.getAnnotationsByType(Role.class)` trả **mảng rỗng**. Dù `Role` có `@Inherited`, quan hệ `implements` không phải quan hệ **extends class** áp dụng cho `@Inherited`. Việc một interface mang annotation không khiến class triển khai nó tự thấy annotation đó qua cơ chế kế thừa chuẩn này.

Nếu cần tìm metadata từ các interface được implement, công cụ cần chủ động duyệt `getInterfaces()` và đặt quy tắc rõ ràng cho nhiều interface, duplicate, thứ tự và ưu tiên.

## 5. Hiểu chính xác ba kiểu “hiện diện” trong Reflection

Java phân biệt nhiều dạng presence của annotation. Với repeatable annotations, nên hiểu theo loại annotation **được hỏi**, không chỉ nhìn xem có một container vật lý hay không.

- **Directly present:** có annotation chính loại đó trên phần tử được Reflection xem là trực tiếp, ví dụ một `@Role("local")` trên `LocalService`.
- **Indirectly present:** container annotation xuất hiện trực tiếp và mảng `value()` chứa một hay nhiều annotation của loại được lặp, ví dụ hai `@Role` trên `BaseService`.
- **Associated:** phục vụ truy vấn theo loại, bao gồm direct/indirect tại phần tử hiện tại và, nếu không có chúng và loại annotation mang `@Inherited` trên class, có thể đi lên superclass để tìm.

Vì `getAnnotationsByType(Role.class)` dựa trên loại `Role` được associated, nó hỗ trợ cả trường hợp một lần, nhiều lần và các annotation được kế thừa phù hợp.

Có thể đọc quy tắc theo thứ tự:

```text
getAnnotationsByType(Role.class) trên một Class
    |
    +-- Có một hoặc nhiều Role trực tiếp / gián tiếp tại lớp này?
    |       |
    |       +-- Có  --> trả những Role đó (không nối Role của cha)
    |       |
    |       +-- Không
    |              |
    |              +-- Role có @Inherited và có superclass?
    |                       |
    |                       +-- Có  --> tra tiếp lên superclass
    |                       |
    |                       +-- Không --> trả mảng rỗng
```

Sơ đồ chỉ minh họa riêng tình huống tra `Class<?>` trong bài. Không dùng nó để khẳng định `@Inherited` hoạt động trên mọi loại `AnnotatedElement`.

## 6. So sánh các API Reflection

Với loại `Role` và `Roles` từ ví dụ chính:

| API | Có mở repeatable container? | Có xét superclass trong trường hợp phù hợp? | Khi nào dùng |
| --- | --- | --- | --- |
| `type.getDeclaredAnnotationsByType(Role.class)` | Có | **Không** | Chỉ lấy các Role trực tiếp/gián tiếp tại lớp hiện tại |
| `type.getAnnotationsByType(Role.class)` | Có | **Có**, nếu Role được `@Inherited` | Lấy Role liên quan tới lớp theo quy tắc chuẩn |
| `type.getDeclaredAnnotation(Role.class)` | Không mở container | Không | Hỏi một Role khai báo trực tiếp |
| `type.getAnnotation(Role.class)` | Không mở container | Có theo quy tắc “present” của một Role | Hỏi một Role đơn lẻ, không phù hợp để đọc đủ annotation lặp |
| `type.getDeclaredAnnotation(Roles.class)` | Đọc container như một annotation đơn | Không | Lấy container do chính lớp khai báo |
| `type.getAnnotation(Roles.class)` | Đọc container như một annotation đơn | Có thể kế thừa container nếu `@Inherited` | Lấy một container, **không tương đương** với truy vấn tập Role |

### 6.1. Một bẫy tinh tế: hỏi container và hỏi Role có thể cho cấu hình khác nhau

Trong mục 3, `LocalService` có một `@Role("local")` trực tiếp, còn `BaseService` có container chứa `"base-read"` và `"base-write"`.

Khi gọi:

```java
LocalService.class.getAnnotationsByType(Role.class)
```

kết quả là một `Role` `"local"`. Nhưng:

```java
LocalService.class.getAnnotation(Roles.class)
```

có thể trả **container `Roles` được kế thừa từ `BaseService`**, vì `LocalService` không khai báo trực tiếp container `Roles` và container được đánh `@Inherited`. Đây là **hai câu hỏi Reflection khác nhau**.

Vì vậy, **không được kết luận** rằng lấy `Roles.class` rồi `value()` luôn tương đương với `getAnnotationsByType(Role.class)` trên một lớp bất kỳ có quan hệ kế thừa.

Nếu mục tiêu của bạn là trả các `Role` theo luật lặp/kế thừa tiêu chuẩn, hãy **gọi trực tiếp `getAnnotationsByType(Role.class)`**. Chỉ đọc container khi bạn thực sự muốn làm việc với annotation type `Roles` như một loại metadata riêng.

### 6.2. getAnnotation(Role.class) không phải API “first Role”

`getAnnotation(Role.class)` **không** có nghĩa “lấy phần tử đầu tiên của `getAnnotationsByType(Role.class)`”. Nếu lớp có nhiều `Role` được đóng trong `Roles`, `getAnnotation(Role.class)` có thể trả `null` dù `getAnnotationsByType(Role.class)` trả nhiều phần tử.

Không dùng phép “lấy một annotation đơn” để suy ra phần tử đầu của danh sách; nếu muốn lựa chọn phần tử nào từ mảng, phải tự đặt quy tắc rõ ràng về thứ tự và xử lý trường hợp mảng rỗng.

## 7. @Inherited không áp dụng cho method, field hoặc parameter annotations

`@Inherited` chỉ mở rộng quy tắc tra cứu các annotation trên **class** theo quan hệ kế thừa lớp thích hợp. Nó không tự truyền các annotation trên phương thức bị override xuống phương thức override ở lớp con.

Ví dụ độc lập trong file **`MethodBoundaryDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Flags {
    Flag[] value();
}

class Parent {
    @Flag("first")
    @Flag("second")
    public void act() {
    }
}

class OverrideChild extends Parent {
    @Override
    public void act() {
    }
}

class InheritChild extends Parent {
}

public class MethodBoundaryDemo {
    public static void main(String[] args) throws Exception {
        Method overridden = OverrideChild.class.getMethod("act");
        Method inherited = InheritChild.class.getMethod("act");

        System.out.println(overridden.getDeclaringClass().getSimpleName());
        System.out.println(overridden.getAnnotationsByType(Flag.class).length);
        System.out.println(inherited.getDeclaringClass().getSimpleName());
        System.out.println(inherited.getAnnotationsByType(Flag.class).length);
    }
}
```

Chạy:

```bash
javac --release 17 MethodBoundaryDemo.java
java MethodBoundaryDemo
```

Stdout:

```text
OverrideChild
0
Parent
2
```

Hai điểm đáng chú ý:

- `OverrideChild` thực sự **khai báo phương thức `act()` mới**, không có `@Flag`; khi đọc `Method` này, các annotation của method ở cha không tự truyền xuống nên kết quả bằng `0`.
- `InheritChild` **không override** `act()`. `getMethod("act")` trên nó có thể trả chính đối tượng `Method` do `Parent` khai báo; `getDeclaringClass()` là `Parent`, và đọc trực tiếp annotation của **phương thức Parent.act** sẽ thấy hai `@Flag`. Đây **không phải** là `@Inherited` được áp dụng cho method.

Sự khác nhau nằm ở **Method object nào được trả về**, không phải một quy tắc kế thừa annotation trên method.

## 8. Chọn @Retention đúng cho cả hai annotation type

`@Inherited` không biến một annotation chỉ có retention `CLASS` thành metadata đọc được bằng Reflection. Nếu dự kiến:

```java
ChildService.class.getAnnotationsByType(Role.class)
```

thì `Role` và `Roles` trong ví dụ phải được giữ đến runtime.

| Annotation chính Role | Container Roles | Có được compiler chấp nhận về retention? | Truy vấn Reflection runtime |
| --- | --- | --- | --- |
| `RUNTIME` | `RUNTIME` | Có | Dùng được nếu annotation tồn tại |
| `RUNTIME` | `CLASS` | **Không** | Compiler từ chối vì container retention ngắn hơn |
| `CLASS` | `CLASS` | Có | Không có thông tin Role qua Reflection chuẩn |
| `SOURCE` | `SOURCE` | Có | Chỉ hiện ở giai đoạn source; không đọc qua Reflection |

Nếu không ghi `@Retention` cho kiểu annotation, giá trị mặc định là `CLASS`. Điều này thường giải thích tình huống “đã viết `@Inherited` rồi mà `getAnnotationsByType` vẫn trả mảng rỗng”.

Một compiler có thể đọc/kiểm tra annotation trong các giai đoạn trước runtime theo cơ chế riêng. Nhưng các API Reflection chuẩn ở bài này cần `RUNTIME`.

## 9. Kiểm tra cặp container hợp lệ

Với:

```java
@Repeatable(Audits.class)
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audit {
    String event();
}
```

container phù hợp:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audits {
    Audit[] value();
}
```

Những lỗi compiler thường gặp:

### 9.1. Quên @Inherited trên container

```java
// Sai nếu Audit được gắn @Inherited:
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audits {
    Audit[] value();
}
```

Compiler kiểm tra quy tắc container: repeated type có `@Inherited` thì container cũng phải có `@Inherited`.

### 9.2. Dùng sai value() trong container

```java
// Sai nếu container của Audit:
@interface Audits {
    String[] value();
}
```

`Audit.event()` có `String`, nhưng container phải chứa **`Audit[]`**, không phải mảng các giá trị `event`. Không thay bằng `Audit value()`, `List<Audit>` hoặc đổi tên phần tử `items()`.

### 9.3. Khai báo phần tử container bổ sung nhưng không có default

```java
// Sai khi là container repeatable:
@interface Audits {
    Audit[] value();
    String owner();
}
```

Nếu compiler tạo container cho các lần `@Audit` lặp, nó không biết giá trị bắt buộc `owner`. Nếu cần phần tử bổ sung, viết `String owner() default "system";`. Đừng thêm dữ liệu vào container nếu không có nhu cầu xử lý thực sự.

### 9.4. Target của hai annotation không tương thích

Nếu `Audit` được dùng trên class declaration và method declaration, container phải cho phép các vị trí cần thiết để biểu diễn nhiều lần dùng đó. Cấu hình thực dụng là công bố `@Target` phù hợp trên cả repeated annotation và container rồi kiểm tra bằng `javac`.

`@Inherited` bản thân vẫn không làm annotation trên method được kế thừa qua override, dù cả hai loại được khai báo target `METHOD`.

## 10. @Inherited không tự “gộp cấu hình” giữa nhiều tầng lớp

Trong ứng dụng, có thể bạn muốn lớp con **kế thừa phần lớn quyền** từ lớp cha, rồi bổ sung một quyền mới. Nhưng quy tắc `getAnnotationsByType` chuẩn không làm việc đó khi lớp con có `Role` riêng.

Ví dụ:

```java
@Role("READ")
@Role("EXPORT")
class DocumentBase {
}

@Role("EDIT")
class DocumentEditor extends DocumentBase {
}
```

Trong trường hợp cả `Role` và `Roles` được cấu hình như ở mục 2:

```java
Role[] roles = DocumentEditor.class.getAnnotationsByType(Role.class);
```

mảng `roles` gồm `Role("EDIT")` theo quy tắc tra cứu associated annotations, **không tự chứa `READ` và `EXPORT`**.

Nếu nghiệp vụ muốn **gộp theo chuỗi lớp cha**, bạn cần chủ động định nghĩa thuật toán như:

1. Duyệt lớp hiện tại rồi lên từng superclass bằng `getSuperclass()`.
2. Ở **mỗi lớp**, chỉ đọc annotation do lớp đó khai báo với `getDeclaredAnnotationsByType(Role.class)` để tránh lấy trùng qua cơ chế inherited.
3. Quy định ưu tiên: con trước hay cha trước, có gộp trùng hay không, cho phép “deny/disable” hay không.
4. Hợp nhất các giá trị theo chính sách ứng dụng, không giả định do `@Inherited` cung cấp.

Đoạn pseudo-code Java sau minh họa **chủ động thu thập**, không phải cách Reflection mặc định vận hành:

```java
static java.util.List<Role> collectDeclaredRoles(Class<?> type) {
    java.util.List<Role> result = new java.util.ArrayList<>();
    for (Class<?> current = type;
         current != null;
         current = current.getSuperclass()) {
        Role[] here = current.getDeclaredAnnotationsByType(Role.class);
        java.util.Collections.addAll(result, here);
    }
    return result;
}
```

Đoạn này cần dùng các kiểu `Role` từ mục 2 và đặt trong một class; nó cố ý **gộp thông tin từ nhiều tầng**. Với `DocumentEditor`, cách duyệt này sẽ nhìn thấy `EDIT` trên con và `READ`, `EXPORT` trên cha, trái với `getAnnotationsByType` tiêu chuẩn.

**Đặc biệt với quyền truy cập/phân quyền:** đừng mặc định gộp annotation là an toàn. Ngữ nghĩa “ghi đè”, “cộng dồn”, “từ chối” có ảnh hưởng bảo mật; phải có quy tắc chính thức và kiểm thử.

## 11. Trường hợp lớp cháu, lớp con trực tiếp và không khai báo

Giả sử:

```java
@Role("root")
class Root {
}

class Middle extends Root {
}

@Role("leaf")
class Leaf extends Middle {
}
```

`Middle.class.getAnnotationsByType(Role.class)` tìm đến `Root` và trả `"root"` nếu không có annotation ở `Middle`. Nhưng `Leaf.class.getAnnotationsByType(Role.class)` trả `"leaf"` do annotation trực tiếp trên `Leaf`; nó không nối `"root"`.

Nếu `Leaf` không khai báo `Role`, truy vấn có thể tiếp tục qua `Middle` để tìm `Root`. Quy tắc này áp dụng theo **chuỗi extends class**; nó không duyệt sang bất kỳ interface nào mà `Middle` hoặc `Leaf` triển khai.

## 12. Các nhầm lẫn thường gặp

**“Chỉ cần `@Inherited` trên annotation chính; container không quan trọng.”** Sai. Khi annotation là repeatable và chính nó mang `@Inherited`, container phải được đánh `@Inherited` theo yêu cầu hợp lệ của Java.

**“`@Repeatable` mặc định đã bao gồm `@Inherited`.”** Sai. Hai meta-annotation phục vụ hai cơ chế độc lập, phải lựa chọn rõ ràng.

**“Lớp con có `@Role` riêng thì Reflection sẽ cộng thêm `@Role` của cha.”** Sai. `getAnnotationsByType(Role.class)` sử dụng các `Role` trực tiếp/gián tiếp trên lớp con nếu có, không tự gộp danh sách.

**“`getDeclaredAnnotationsByType` luôn bằng `getAnnotationsByType`.”** Sai. Trường hợp `ChildService` trong mục 3 trả mảng rỗng đối với API declared, nhưng API associated trả hai annotation từ `BaseService`.

**“Lớp con implement interface có `@Role` thì kế thừa `@Role`.”** Sai. `@Inherited` không theo quan hệ `implements`.

**“`@Inherited` làm annotation method cha xuất hiện trên method override.”** Sai. Nó chỉ có ngữ nghĩa kế thừa cho annotation trên class trong những API phù hợp.

**“Chỉ cần dùng `getAnnotation(Roles.class)` rồi đọc `value()` là luôn giống `getAnnotationsByType(Role.class)`.”** Sai khi có kế thừa và annotation trực tiếp/container ở các tầng khác nhau. Hai truy vấn đặt ra hai câu hỏi khác nhau.

**“`@Roles({})` chắc chắn chặn inherited `Role`.”** Sai. Ví dụ đã kiểm chứng ở mục 3 cho thấy truy vấn `getAnnotationsByType(Role.class)` vẫn tìm thấy `Role` trên lớp cha nếu container rỗng ở lớp con không tạo ra phần tử `Role` nào.

**“`@Inherited` cho phép Reflection đọc annotation `CLASS`.”** Sai. `@Retention(RUNTIME)` vẫn là điều kiện cần để các API Java Reflection chuẩn đọc được annotation ở runtime.

**“Muốn kết hợp cha-con thì Java cung cấp sẵn phép merge.”** Sai. Phép gộp là chính sách nghiệp vụ riêng và phải được lập trình tường minh.

## 13. Bài tập tự kiểm tra

### Bài 1 — Dự đoán danh sách kế thừa

Cho:

```java
@Role("A")
@Role("B")
class ParentA {}

class ChildA extends ParentA {}

@Role("C")
class ChildB extends ParentA {}
```

Giả sử cặp `Role`/`Roles` đã được định nghĩa như mục 2. Dự đoán:

- `ParentA.class.getAnnotationsByType(Role.class)`
- `ChildA.class.getAnnotationsByType(Role.class)`
- `ChildB.class.getAnnotationsByType(Role.class)`
- `ChildB.class.getDeclaredAnnotationsByType(Role.class)`

**Gợi ý:** lần lượt `[A, B]`, `[A, B]`, `[C]`, `[C]`.

### Bài 2 — Tại sao container phải @Inherited?

Bỏ `@Inherited` khỏi định nghĩa `Roles` nhưng giữ `@Inherited` trên `Role`. Có nên chờ đến lúc Reflection chạy mới phát hiện lỗi?

**Đáp án:** không. Đây là cấu hình repeatable annotation **không hợp lệ** và phải được compiler từ chối tại bước khai báo kiểu.

### Bài 3 — Annotation trên interface

Nếu `interface Feature` có `@Role("feature")`, còn `class Consumer implements Feature` không khai báo `Role` riêng, `Consumer.class.getAnnotationsByType(Role.class)` có `feature` không?

**Đáp án:** không. `@Inherited` chỉ xét quan hệ superclass thích hợp, không tự kế thừa annotation từ implemented interface.

### Bài 4 — Declared và associated

Vì sao `ChildService.class.getDeclaredAnnotationsByType(Role.class)` rỗng nhưng `ChildService.class.getAnnotationsByType(Role.class)` có hai phần tử?

**Đáp án:** `declared` chỉ đọc trên chính class hiện tại, còn `getAnnotationsByType` xét quy tắc `@Inherited` khi không có phần tử trực tiếp/gián tiếp của loại được hỏi.

### Bài 5 — Container rỗng

Với `@Roles({}) class EmptyContainerService extends BaseService` trong mục 3, dự đoán số phần tử nhận từ:

```java
EmptyContainerService.class.getDeclaredAnnotationsByType(Role.class).length
EmptyContainerService.class.getAnnotationsByType(Role.class).length
```

**Đáp án:** `0` và `2`. Mảng container rỗng không nhất thiết chặn tra cứu `Role` từ lớp cha.

### Bài 6 — Phương thức override

`Parent.act()` có hai `@Flag`, còn `OverrideChild.act()` override nhưng không có `@Flag`. Truy vấn `getAnnotationsByType(Flag.class)` trên phương thức override có thấy hai annotation của `Parent.act()` không?

**Đáp án:** không. `@Inherited` không kế thừa method annotation.

### Bài 7 — Kết hợp cấu hình

Bạn muốn luôn lấy mọi `Role` từ `DocumentEditor`, `DocumentBase` và các superclass khác, kể cả khi con có `Role` riêng. Có nên dùng một lần `DocumentEditor.class.getAnnotationsByType(Role.class)` không?

**Đáp án:** không. Duyệt superclass tường minh, mỗi tầng gọi `getDeclaredAnnotationsByType(Role.class)`, sau đó gộp theo chính sách ưu tiên và chống trùng do ứng dụng quyết định.

## 14. Checklist trước khi dùng repeatable annotation có kế thừa

1. **Có đúng cặp repeated/container?** `@Repeatable(Container.class)` và `Repeated[] value()` chính xác?
2. **Cả hai có `@Inherited` khi repeated annotation dùng nó?** Tránh lỗi compiler và ngộ nhận về container.
3. **Cả hai có retention đủ để đọc bằng Reflection?** Với runtime, thường đều `RUNTIME`.
4. **Target có tương thích?** Nếu annotation dành cho class, cấu hình `TYPE` phù hợp cho cặp.
5. **Đọc danh sách hay đọc một annotation?** Với repeatable, ưu tiên `getAnnotationsByType` nếu muốn tất cả annotation theo quy tắc chuẩn.
6. **Muốn chỉ khai báo tại lớp hiện tại?** Dùng `getDeclaredAnnotationsByType`.
7. **Có mong con và cha được tự gộp?** Không mặc định; nếu cần phải lập trình thuật toán riêng.
8. **Có interface hoặc method override liên quan?** `@Inherited` không tự kế thừa annotation ở các vị trí đó.
9. **Có container rỗng hoặc container tường minh?** Kiểm tra kết quả thực tế của các API được dùng; đừng suy từ cú pháp source.
10. **Đã thử đủ trường hợp không khai báo ở con, con khai báo một annotation, con khai báo nhiều và container rỗng?** Những ca này phân biệt rõ ngữ nghĩa.

**Kết luận:** `@Repeatable` giải quyết việc dùng nhiều annotation cùng loại và yêu cầu một container có `Repeated[] value()`; `@Inherited` quy định tra cứu annotation theo superclass của class. Khi kết hợp, container phải được khai báo phù hợp, và `getAnnotationsByType` thường **ưu tiên các annotation của lớp hiện tại thay vì nối với lớp cha**. Hiểu kỹ các biến thể direct, indirect và associated giúp tránh lỗi khó thấy trong Reflection cũng như trong thiết kế metadata của framework.