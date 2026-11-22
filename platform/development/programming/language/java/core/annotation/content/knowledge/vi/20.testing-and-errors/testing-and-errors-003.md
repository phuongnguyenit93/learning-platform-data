# Kiểm thử kế thừa, che khuất và các API tra cứu annotation trong Java

## 1. Vì sao cần kiểm thử annotation lookup?

Khi hệ thống Java dùng annotation để chọn cấu hình, validation, quyền truy cập hay chiến lược xử lý, **chỉ kiểm tra “có annotation hay không” là chưa đủ**. Kết quả có thể thay đổi tùy:

- Annotation có **`@Retention(RUNTIME)`** không.
- Annotation type có **`@Inherited`** không.
- Annotation được gắn trên **class, interface hay method**.
- Annotation nằm **trực tiếp trên phần tử**, được tìm từ **superclass**, hay được đặt **lặp qua container** với `@Repeatable`.
- Code dùng **`getAnnotation`**, **`getDeclaredAnnotation`**, **`getAnnotationsByType`**, **`getDeclaredAnnotationsByType`** hay các API trả mảng tổng quát.

Một lỗi điển hình là tưởng class con luôn nhận cấu hình của cha rồi *cộng dồn* với cấu hình riêng. Thực tế, `@Inherited` có những quy tắc **ưu tiên/che khuất** cụ thể. Với annotation lặp, `getAnnotation` thậm chí có thể trả giá trị từ cha, trong khi `getAnnotationsByType` trả các giá trị của con ngay trên cùng class.

Bài học này hướng dẫn thiết kế **ma trận ca kiểm thử**, chạy ví dụ Java 17+ không cần thư viện bên ngoài và diễn giải chính xác mỗi kết quả reflection.

## 2. Bốn loại quan hệ annotation cần phân biệt

Theo `java.lang.reflect.AnnotatedElement` của Java SE, bốn thuật ngữ có nghĩa riêng:

| Thuật ngữ | Điều kiện |
| --- | --- |
| **Directly present** (trực tiếp) | Metadata runtime của chính phần tử chứa annotation thuộc loại đó |
| **Indirectly present** (gián tiếp) | Phần tử chứa trực tiếp **container annotation** của một `@Repeatable`, và annotation cần tìm nằm trong `value()` của container |
| **Present** (hiện diện) | Annotation trực tiếp, hoặc được tìm từ **superclass** theo quy tắc `@Inherited` ở class khi không có annotation trực tiếp cùng loại |
| **Associated** (liên kết) | Annotation trực tiếp/gián tiếp, hoặc được tìm từ superclass theo `@Inherited` khi không có annotation trực tiếp **hay gián tiếp** cùng loại ở class hiện tại |

“Indirectly present” **không có nghĩa** “thừa hưởng từ cha”; nó đề cập đúng cơ chế container của repeatable annotation. Còn “inherited” được tính trong *present* hoặc *associated* dưới những điều kiện riêng.

### Bảng ánh xạ API

| API | Kiểu quan hệ đọc | Mở container? | Có cơ chế kế thừa `@Inherited`? |
| --- | --- | --- | --- |
| `getDeclaredAnnotation(T.class)` | **Directly present** | Không | Không |
| `getAnnotation(T.class)` | **Present** | Không | Có, chỉ truy vấn class phù hợp |
| `getDeclaredAnnotationsByType(T.class)` | **Directly + indirectly present** | Có | Không |
| `getAnnotationsByType(T.class)` | **Associated** | Có | Có, chỉ truy vấn class phù hợp |
| `getDeclaredAnnotations()` | Mọi annotation **trực tiếp** | Không tự trải container | Không |
| `getAnnotations()` | Mọi annotation **present** | Không tự trải container | Có theo quy tắc phù hợp |
| `isAnnotationPresent(T.class)` | Kiểm tra **present** | Không mở container | Như `getAnnotation(T.class) != null` |

**Quy tắc chọn API:** khi annotation có thể lặp, ưu tiên phương thức **`ByType`** để lấy đầy đủ các giá trị; khi cần phân biệt khai báo **của chính class** với cấu hình kế thừa, dùng họ **`Declared`**.

Một chi tiết dễ bỏ sót: `getAnnotation(T.class)` chỉ trả **một** annotation type `T`, nên nó không thể trả toàn bộ các giá trị lặp được chứa gián tiếp.

## 3. @Inherited thực sự kế thừa những gì?

Khai báo annotation kế thừa:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Policy {
    String value();
}
```

Áp dụng lên class cha:

```java
@Policy("base")
class Base {}

class Child extends Base {}
```

Ở `Child.class`, `getAnnotation(Policy.class)` có thể tìm `Policy("base")` từ `Base` vì `Policy` có `@Inherited`. Nhưng `Child.class.getDeclaredAnnotation(Policy.class)` trả `null`: class con **không trực tiếp khai báo** annotation đó.

Các giới hạn quan trọng:

1. `@Inherited` chỉ ảnh hưởng đến tra cứu annotation trên **class declaration**, và chỉ theo chuỗi **superclass**.
2. Annotation khai báo trên **interface** không tự truyền sang class `implements` interface.
3. `@Inherited` **không** khiến annotation gắn lên method cha được tự gắn lên **method override** của class con.
4. Không suy rộng sang field, constructor hay parameter.
5. `@Inherited` không liên quan việc một class được nạp, tạo object hay được gọi: đây là **quy tắc khi tra cứu metadata**, không phải tác vụ runtime tự động.

`@Retention(RUNTIME)` là điều kiện cần nếu muốn đọc bằng reflection. Một annotation có `@Inherited` nhưng retention mặc định `CLASS` vẫn không được API reflection trả về theo cách các ví dụ runtime dưới đây dùng.

### “Che khuất” nghĩa gì trong bài toán này?

Trong bài học này, *che khuất/ưu tiên* là **quy tắc tra cứu annotation cùng loại trong class hierarchy**, không đồng nhất với **field hiding**, **method overriding**, **variable shadowing** hay **classloader visibility** của ngôn ngữ Java.

Ví dụ:

```java
@Policy("base")
class Base {}

@Policy("child")
class Child extends Base {}
```

Khi hỏi `Child.class.getAnnotation(Policy.class)`, kết quả là `"child"` vì annotation của class con trực tiếp hiện diện. `@Inherited` không khiến kết quả trở thành danh sách `["base", "child"]`.

Nếu muốn **tự gộp cấu hình** từ nhiều cấp class, thư viện phải tự duyệt `getSuperclass()` và áp dụng quy tắc merge do mình thiết kế. Các API mặc định không tự giải bài toán merge nghiệp vụ.

## 4. Repeatable annotation: sự khác biệt đáng kiểm thử nhất

Giả sử một annotation có thể lặp:

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

`Role` có `@Repeatable(Roles.class)`, `Roles` là container với phần tử `Role[] value()`. Để định nghĩa repeatable annotation hợp lệ, retention và target của container phải tương thích. Khi loại repeatable có `@Inherited`, container cũng phải mang `@Inherited`. Đặt **cùng `RUNTIME` retention, `TYPE` target và `@Inherited`** là lựa chọn rõ ràng trong ví dụ này.

### 4.1. Class con không khai báo Role

```java
@Role("base-role")
class Base {}

class Inherits extends Base {}
```

Với `Inherits`:

- `getDeclaredAnnotation(Role.class)`: `null`, vì không có `Role` trực tiếp.
- `getDeclaredAnnotationsByType(Role.class)`: mảng rỗng, vì không có `Role` trực tiếp/gián tiếp.
- `getAnnotation(Role.class)`: tìm được `"base-role"` từ class cha theo `@Inherited`.
- `getAnnotationsByType(Role.class)`: mảng chứa `"base-role"`, nhờ associated inheritance.

### 4.2. Class con khai báo một Role

```java
@Role("child-role")
class Overrides extends Base {}
```

Cả `getAnnotation(Role.class)` và `getAnnotationsByType(Role.class)` trên `Overrides.class` đều ưu tiên annotation của chính class con. **Không tự cộng thêm** `"base-role"` vào mảng.

### 4.3. Class con khai báo HAI Role — trường hợp bất ngờ

```java
@Role("alpha")
@Role("beta")
class RepeatedChild extends Base {}
```

Compiler biểu diễn hai `@Role` trên `RepeatedChild` thông qua **container `@Roles`**. Vì vậy:

- `RepeatedChild.class.getDeclaredAnnotation(Role.class)` trả `null`: không có một `Role` directly present; có **container** directly present.
- `RepeatedChild.class.getDeclaredAnnotation(Roles.class)` **không null**.
- `RepeatedChild.class.getDeclaredAnnotationsByType(Role.class)` trả `["alpha", "beta"]`.
- `RepeatedChild.class.getAnnotationsByType(Role.class)` cũng trả `["alpha", "beta"]`, **không cộng thêm** `"base-role"`, vì hai `Role` đã indirectly present trên class con.
- Nhưng **`RepeatedChild.class.getAnnotation(Role.class)` có thể trả `Role("base-role")` kế thừa từ Base**: về nghĩa *present*, class con không có `Role` trực tiếp, dù có container chứa hai `Role` gián tiếp.

Kết luận thiết yếu: **`getAnnotation(Role.class)` và `getAnnotationsByType(Role.class)` có thể nhìn thấy các giá trị từ hai cấp khác nhau trên cùng class**. Đây không phải lỗi compiler; là hệ quả chính xác của sự khác biệt *present* và *associated*.

Tình huống này rất nên có trong **test hồi quy** nếu thư viện của bạn cho phép lặp annotation có tính kế thừa.

## 5. Phân biệt annotation trên class, interface và method override

### Class con implements interface

```java
@Policy("interface")
interface TaskContract {}

class ImplementsTask implements TaskContract {}
```

`ImplementsTask.class.getAnnotation(Policy.class)` trả `null` nếu class không có `@Policy` từ superclass phù hợp. **`@Inherited` không tìm annotation trên interface đã `implements`**.

### Phương thức bị override

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

class Base {
    @MethodMark
    public void run() {}
}

class Overrides extends Base {
    @Override
    public void run() {}
}
```

Reflection với:

```java
Overrides.class.getDeclaredMethod("run")
        .isAnnotationPresent(MethodMark.class)
```

trả `false`, bởi method override là khai báo method mới và `@Inherited` không tự chép annotation từ method cha sang method con.

**Điểm phân biệt khi dùng reflection:** nếu class con **không override** `run`, `Inherits.class.getMethod("run")` có thể trả chính `Method` được khai báo ở `Base`. Annotation nhìn thấy khi đó là annotation của **method Base**, **không phải do @Inherited áp dụng cho method**. Kiểm tra `method.getDeclaringClass()` để hiểu chính xác nguồn metadata.

Các đoạn ở mục 3–5 là ví dụ minh họa độc lập; mục 6 gom mọi thành phần vào **một file thực sự chạy được**, tránh ghép các class trùng tên từ các snippet.

## 6. Chương trình Java 17+ đầy đủ: ma trận tra cứu đã kiểm chứng

Tạo file **AnnotationLookupTest.java** với nội dung sau. Chương trình chỉ dùng API Java SE, không cần thư viện ngoài; nó kiểm tra **kế thừa một annotation**, **ưu tiên annotation của class con**, **annotation lặp + container**, **method override** và **interface không tham gia inheritance**.

```java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
}

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

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

@Policy("base")
@Role("base-role")
class Base {
    @MethodMark
    public void run() {}
}

class Inherits extends Base {}

@Policy("child")
@Role("child-role")
class Overrides extends Base {
    @Override
    public void run() {}
}

@Role("alpha")
@Role("beta")
class RepeatedChild extends Base {}

@Policy("interface")
interface TaskContract {}

class ImplementsTask implements TaskContract {}

public class AnnotationLookupTest {
    static String roles(Class<?> type) {
        return Arrays.stream(type.getAnnotationsByType(Role.class))
                .map(Role::value)
                .collect(Collectors.joining(",", "[", "]"));
    }

    static String policy(Policy p) {
        return p == null ? "null" : p.value();
    }

    static String role(Role r) {
        return r == null ? "null" : r.value();
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        System.out.println("inherit policy="
                + policy(Inherits.class.getAnnotation(Policy.class)));
        System.out.println("inherit declared="
                + policy(Inherits.class.getDeclaredAnnotation(Policy.class)));
        System.out.println("inherit roles=" + roles(Inherits.class));

        System.out.println("override policy="
                + policy(Overrides.class.getAnnotation(Policy.class)));
        System.out.println("override roles=" + roles(Overrides.class));

        Method method = Overrides.class.getDeclaredMethod("run");
        System.out.println("override method mark="
                + method.isAnnotationPresent(MethodMark.class));

        System.out.println("repeated declared role="
                + role(RepeatedChild.class.getDeclaredAnnotation(Role.class)));
        System.out.println("repeated container="
                + (RepeatedChild.class.getDeclaredAnnotation(Roles.class) != null));
        System.out.println("repeated present role="
                + role(RepeatedChild.class.getAnnotation(Role.class)));
        System.out.println("repeated associated=" + roles(RepeatedChild.class));
        System.out.println("repeated declared by type="
                + RepeatedChild.class.getDeclaredAnnotationsByType(Role.class).length);

        System.out.println("interface inherited="
                + policy(ImplementsTask.class.getAnnotation(Policy.class)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 AnnotationLookupTest.java
java AnnotationLookupTest
```

Stdout chính xác:

```text
inherit policy=base
inherit declared=null
inherit roles=[base-role]
override policy=child
override roles=[child-role]
override method mark=false
repeated declared role=null
repeated container=true
repeated present role=base-role
repeated associated=[alpha,beta]
repeated declared by type=2
interface inherited=null
```

Đây là output **đã được chạy kiểm tra với `javac --release 17`**, không phải dữ liệu bịa theo tên API. Chuỗi `null` được in có chủ đích qua helper để tránh `NullPointerException` khi không tìm thấy annotation.

### Diễn giải theo từng nhóm kết quả

1. **`Inherits`** không khai báo `Policy` hay `Role`, nhưng `@Inherited` cho phép API không-`Declared` tìm trên `Base`. `getDeclaredAnnotation(Policy.class)` là `null`.
2. **`Overrides`** khai báo `@Policy("child")` và `@Role("child-role")` trực tiếp, nên giá trị riêng che giá trị cùng loại của cha trong kết quả tra cứu tương ứng.
3. `Overrides.run()` override method của `Base` nhưng không tự có `@MethodMark`. Chỉ đánh dấu annotation type `@Inherited` **không thay đổi quy tắc đó**.
4. **`RepeatedChild`** khai báo hai Role; container `Roles` có mặt, nhưng `Role` không directly present. Vì vậy `getDeclaredAnnotation(Role.class) == null`, trong khi `getDeclaredAnnotation(Roles.class) != null`.
5. **Trường hợp khác biệt nổi bật:** `getAnnotation(Role.class)` trả `base-role`, còn `getAnnotationsByType(Role.class)` trả `alpha,beta` do mở container trên class con, không gộp thêm vai trò từ cha.
6. **`ImplementsTask`** không tự nhận `@Policy("interface")`, vì `@Inherited` không tìm trên interface đã implements.

Các trường hợp trên cùng nhau bảo vệ code khỏi hai sai sót: **đọc API không hợp mục đích** và **hiểu sai quy tắc che khuất khi một annotation trở thành repeatable**.

## 7. Chuyển ví dụ sang kiểm thử tự động không cần thư viện

In stdout giúp quan sát nhanh nhưng kiểm thử liên tục cần **điều kiện pass/fail**. Với dự án không dùng JUnit, Java SE có thể tự báo lỗi bằng `AssertionError` khi kết quả khác kỳ vọng:

```java
// Có thể thêm phương thức này vào AnnotationLookupTest:
static void check(boolean ok, String description) {
    if (!ok) {
        throw new AssertionError(description);
    }
}
```

Sau đó đặt kiểm tra trong `main`:

```java
check(Inherits.class.getDeclaredAnnotation(Policy.class) == null,
        "Inherited annotation không phải declared annotation");

check("base".equals(
        Inherits.class.getAnnotation(Policy.class).value()),
        "Class con phải đọc được inherited Policy");

check(RepeatedChild.class.getDeclaredAnnotation(Role.class) == null,
        "Role lặp không trực tiếp có mặt");

check(RepeatedChild.class.getDeclaredAnnotationsByType(Role.class).length == 2,
        "Phải đọc được hai Role qua container");

check("base-role".equals(
        RepeatedChild.class.getAnnotation(Role.class).value()),
        "getAnnotation dùng present/inherited semantics");

check("[alpha,beta]".equals(roles(RepeatedChild.class)),
        "getAnnotationsByType dùng associated semantics");

check(!Overrides.class.getDeclaredMethod("run")
        .isAnnotationPresent(MethodMark.class),
        "@Inherited không tự áp dụng cho method override");
```

Đây là **đoạn bổ sung**, cần đặt vào cùng class `AnnotationLookupTest` của mục 6, không phải một file Java độc lập. Nếu điều kiện sai, chương trình ném `AssertionError` và quá trình kết thúc với exit code khác 0, phù hợp cho CI.

Đừng nhầm với keyword `assert` của Java: khi dùng câu lệnh `assert condition;`, phải bật **`-ea`** lúc chạy JVM để assertion được thực thi. Helper `check` gọi `throw new AssertionError` tường minh nên không phụ thuộc cờ `-ea`.

### Nên kiểm tra cả phủ định và nguồn dữ liệu

Chỉ thấy `getAnnotation(...) != null` chưa chứng minh annotation đến từ chính class hay superclass. Bộ test tốt cần ít nhất một kiểm tra `getDeclaredAnnotation(...) == null` và một kiểm tra API không-`Declared` trả đúng giá trị. Với annotation lặp, phải test cả `getDeclaredAnnotationsByType`, `getAnnotationsByType` và container.

Đối với method, nên kiểm tra `getDeclaringClass()` khi dùng `getMethod` để phân biệt method cha được thừa hưởng về khả năng truy cập với một method override thực sự.

## 8. Ma trận test case nên có trong dự án

| Ca kiểm thử | Setup | API cần quan sát | Điều kiện kỳ vọng |
| --- | --- | --- | --- |
| Annotation trực tiếp | `@Policy("base")` trên class | `getAnnotation`, `getDeclaredAnnotation` | Cả hai đọc được `base` |
| Kế thừa một annotation | Con không có Policy, cha có | `getAnnotation`, `getDeclaredAnnotation` | `base` và `null` |
| Che khuất trên class con | Con có `@Policy("child")` | `getAnnotation` | `child`, không tự gộp với `base` |
| Annotation không đánh dấu `@Inherited` | Chỉ cha có, con không | `getAnnotation` trên con | `null` |
| Annotation gắn trên interface | Class `implements` interface có Policy | `getAnnotation` trên class | `null`, trừ nguồn khác có Policy |
| Annotation trên method override | Cha có `@MethodMark`, con override không gắn | `getDeclaredMethod(...).getAnnotation` | `null` |
| Method được thừa hưởng nhưng không override | Con không khai báo `run` | `getMethod(...).getDeclaringClass` | Trả class khai báo method, có thể là Base |
| Repeatable một lần | Một `@Role` trực tiếp | `getDeclaredAnnotation(Role.class)` | Tìm được Role |
| Repeatable hai lần | Hai `@Role` trên cùng class | `getDeclaredAnnotation(Role.class)` | `null` vì qua container |
| Hai annotation qua container | Hai `@Role` | `getDeclaredAnnotationsByType` | Mảng hai phần tử đúng thứ tự |
| Con có hai Role, cha có một Role | `RepeatedChild` | `getAnnotation(Role.class)` | Có thể thấy giá trị **của cha** |
| Cùng ca, tra cứu associated | `RepeatedChild` | `getAnnotationsByType(Role.class)` | Hai Role **của con**, không cộng dồn cha |
| `CLASS` retention | Annotation không khai báo Retention | Reflection runtime | Không xuất hiện theo API runtime |
| Class con không có Role nào | `Inherits` | `getAnnotationsByType(Role.class)` | Kế thừa Role từ Base nếu type là inheritable |

**Lưu ý thiết kế test:** Test ít nhất **0 / 1 / nhiều giá trị** với repeatable annotation, **có và không có `@Inherited`**, class/interface/method và **họ Declared so với không Declared**. Đây là những chiều kiểm thử độc lập; chỉ kiểm một phương thức trên một class dễ bỏ sót sai sót.

## 9. Thế nào là “che khuất” khi cần gộp annotation từ cha và con?

Hãy phân biệt hai chính sách mà thư viện có thể chọn:

### A. Chính sách Java Reflection mặc định

Nếu cần dùng **cấu hình hiệu lực gần nhất**, `getAnnotationsByType(Role.class)` theo luật associated sẽ ưu tiên những `Role` trực tiếp/gián tiếp có trên class hiện tại. Chỉ khi class hiện tại không có `Role` loại đó mới xem xét superclass, nếu `Role` có `@Inherited`.

Ví dụ, con có `alpha`, `beta` thì kết quả mặc định **không chứa** `base-role`.

### B. Chính sách tự viết: gộp từ nhiều lớp

Một framework có thể muốn: “cộng tất cả role từ `Base` đến `RepeatedChild`, loại bỏ trùng, con ghi đè role cùng khóa, giữ thứ tự ưu tiên”. Đây là **quy tắc ứng dụng**; không thể suy ra từ `getAnnotationsByType` mặc định.

Cách triển khai cần quyết định rõ:

1. Duyệt `getSuperclass()` theo chiều từ con lên cha hay cha xuống con.
2. Ở **mỗi class**, gọi `getDeclaredAnnotationsByType(Role.class)` để đọc **chỉ** dữ liệu gắn trên class đó, tránh vô tình cộng lặp annotation thừa hưởng.
3. Định nghĩa khóa phân biệt và chính sách ghi đè khi có giá trị trùng.
4. Xác định có xét interface hay không; Java `@Inherited` mặc định **không** xét interface.
5. Kiểm thử repeatable container và thứ tự của các giá trị.

Ví dụ thuật toán khái niệm (không phải file chạy độc lập):

```java
for (Class<?> current = target;
     current != null;
     current = current.getSuperclass()) {

    Role[] local = current.getDeclaredAnnotationsByType(Role.class);
    for (Role role : local) {
        // Đưa role vào cấu trúc dữ liệu riêng và áp dụng luật merge.
    }
}
```

Không dùng `getAnnotationsByType` để lặp qua từng cấp rồi cộng hết một cách mù quáng, vì API đó có thể **đã kế thừa** dữ liệu từ superclass và gây đếm trùng. Nếu cần quyền cao hơn ở class con hoặc chính sách deny/allow, phải kiểm thử tác động bảo mật của quy tắc merge thay vì coi mọi annotation đều là chỉ dẫn đủ tin cậy.

## 10. Kiểm thử theo cách tránh phụ thuộc implementation

### 10.1. Đọc giá trị thực, không parse toString

Hãy dùng `policy.value()` và `role.value()`, không parse `annotation.toString()`. Chuỗi `toString()` là biểu diễn dễ đọc, không phải định dạng chuẩn để xác nhận thứ tự, tên kiểu hoặc serialization.

### 10.2. Kiểm thử với retention đúng

Nếu bỏ `@Retention(RUNTIME)` khỏi `Policy`, annotation mặc định là `CLASS`. Các phép thử runtime `getAnnotation(Policy.class)` sẽ không còn phản ánh những gì source gắn; đừng nhầm đó là lỗi kế thừa.

Nếu dùng repeatable annotation runtime, **container** cũng phải có retention tương thích, thường là `RUNTIME` để API `ByType` truy cập được.

### 10.3. Phân biệt class declaration với type-use annotation

Bài này kiểm tra annotation **trên khai báo class** với `Class.getAnnotationsByType`. Annotation có `@Target(TYPE_USE)` có thể được gắn lên **kiểu được sử dụng**, ví dụ biến, generic parameter hoặc supertype use. Chúng thường được đọc qua `AnnotatedType` và API reflection tương ứng, không phải đơn giản thay bằng `Class.getAnnotation`.

Nếu một bài test về kế thừa không thấy annotation type-use đặt trên `extends @SomeAnnotation Base`, trước hết hãy xác nhận bạn đang gọi đúng API (`getAnnotatedSuperclass()`) và đúng retention/target, thay vì coi `@Inherited` của declaration annotation là giải pháp.

### 10.4. Cẩn thận với nhiều classloader

Hai annotation type có cùng tên string nhưng được nạp bởi hai classloader khác nhau có thể là hai `Class` object khác nhau. `getAnnotation(SomeAnnotation.class)` đòi hỏi **đúng annotation type** đang được gắn trong runtime metadata. Trong ứng dụng plugin/modular, kiểm thử classloader boundary riêng nếu có.

### 10.5. Không dựa vào thứ tự của getAnnotations() đa loại

`getAnnotationsByType(Role.class)` có quy tắc giữ thứ tự các annotation Role bên trong container. Nhưng **thứ tự của tất cả annotation khác loại trong `getAnnotations()`** không nên được coi là định dạng nguồn ổn định để chạy logic nghiệp vụ. Dùng phép so sánh tập hợp/type names nếu chỉ cần hiện diện.

## 11. Những lỗi phổ biến và dấu hiệu nhận biết

**1. Dùng `getDeclaredAnnotation` rồi kết luận `@Inherited` không hoạt động.** Phương thức Declared cố ý chỉ trả annotation trực tiếp; hãy so sánh với `getAnnotation` khi kiểm tra inherited behavior.

**2. Nghĩ `@Inherited` áp dụng cho interface.** Java không tự tìm annotation trên các implemented interfaces.

**3. Nghĩ `@Inherited` áp dụng cho method override.** Annotation method của cha không tự gắn vào khai báo override ở con.

**4. Nghĩ `getMethod()` lấy method inherited nghĩa là method annotation đã được kế thừa.** `getMethod()` có thể trả object `Method` được khai báo ở Base; kiểm tra `getDeclaringClass()`.

**5. Dùng `getAnnotation(Role.class)` để tìm tất cả Role.** Với repeatable container, API này không giải nén danh sách Role; dùng `getAnnotationsByType`.

**6. Giả định `getAnnotation(Role.class)` và `getAnnotationsByType(Role.class)` luôn đồng ý về nguồn của annotation.** Khi con có hai Role trong container và cha có Role trực tiếp, hai API có thể trả nội dung khác nhau theo *present* và *associated*.

**7. Tưởng `getAnnotationsByType` luôn gộp cha và con.** Khi con trực tiếp/gián tiếp có Role, kết quả associated của con sẽ ưu tiên giá trị local.

**8. Bỏ qua `@Inherited` trên container.** Nếu repeatable annotation đánh dấu `@Inherited`, container phải đáp ứng quy tắc tương thích; cùng target/retention là cấu hình nên dùng trong bài này.

**9. Quên `RUNTIME` retention.** Annotation có thể có trong source hoặc class file nhưng không đọc được bằng API runtime.

**10. So sánh chuỗi `toString()` để xác nhận cấu hình.** Kiểm tra accessor có kiểu, số lượng và vị trí `Declared` thay vì format chuỗi.

**11. Kiểm thử toàn bộ bằng một kết quả boolean.** Boolean không cho biết annotation đến từ class hiện tại hay superclass hoặc container; cần kiểm tra nhiều API và giá trị thực.

**12. Vô tình dùng một kiểu annotation trùng tên từ package khác.** `getAnnotation` nhận đối tượng `Class<T>` của đúng annotation interface, không chỉ tên ngắn của kiểu.

**13. Quên trường hợp “không có annotation”.** Luôn kiểm tra `null` với các API trả một đối tượng và mảng độ dài 0 với các API `ByType`; không ép mọi truy vấn đều có dữ liệu.

## 12. Bài tập thực hành và mở rộng bộ test

1. **Thêm cấp cháu:** Khai báo `class GrandChild extends Inherits {}`. Thử `getAnnotation(Policy.class)`, `getDeclaredAnnotation(Policy.class)`, `getAnnotationsByType(Role.class)`; giải thích kết quả truy về Base theo chuỗi superclass.
2. **Tạo che khuất từng loại:** Đặt `@Policy("child-only")` lên một class con nhưng không đặt `Role`. Kiểm tra mỗi annotation type áp dụng chính sách kế thừa độc lập.
3. **Chuyển Role thành không inheritable:** Xóa `@Inherited` khỏi cả `Role` và `Roles`; chạy lại test và ghi nhận phần nào thay đổi. Phân biệt direct/indirect với inherited.
4. **Container tường minh:** Thay hai `@Role` của `RepeatedChild` bằng `@Roles({@Role("alpha"), @Role("beta")})`. So sánh `getDeclaredAnnotation(Roles.class)` và `getDeclaredAnnotationsByType(Role.class)`.
5. **Một Role ở class con:** Đổi `RepeatedChild` chỉ còn `@Role("alpha")`. Dự đoán `getDeclaredAnnotation(Role.class)` và `getAnnotation(Role.class)`; lý giải sự khác biệt so với hai Role.
6. **Gộp role có chủ đích:** Viết hàm duyệt `getSuperclass()` và `getDeclaredAnnotationsByType(Role.class)`; định nghĩa thứ tự cha trước hoặc con trước; kiểm thử không đếm trùng.
7. **Method inherited:** Dùng `Inherits.class.getMethod("run")`, in `getDeclaringClass().getSimpleName()`, rồi so sánh annotation tìm được với `Overrides.class.getDeclaredMethod("run")`.
8. **Interface lookup:** Định nghĩa một framework policy cho phép lấy annotation từ interface; tự viết code duyệt `getInterfaces()` và so sánh với kết quả Java mặc định.
9. **CLASS retention:** Thử bỏ retention RUNTIME trên Policy, dự đoán sự khác nhau giữa mã nguồn và reflection, sau đó phục hồi.
10. **JUnit 5:** Nếu dự án đã có JUnit, chuyển các `check(...)` thành `assertNull`, `assertEquals`, `assertArrayEquals` với test name mô tả đúng nguồn metadata; không cần thay đổi production API.
11. **Kiểm tra thứ tự:** Thay `@Role("alpha") @Role("beta")` thành thứ tự ngược, xác nhận mảng `ByType` phản ánh thứ tự được lưu trong container.
12. **Regression theo phiên bản Java:** Chạy cùng bài test với các JDK dự án hỗ trợ; không phụ thuộc thứ tự `getAnnotations()` giữa các annotation khác loại hay chuỗi `toString()` để tránh false positive.

## 13. Tài liệu chuẩn

- [AnnotatedElement — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): định nghĩa trực tiếp, gián tiếp, present, associated và cách các API ánh xạ từng kiểu quan hệ.
- [Inherited — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): phạm vi kế thừa annotation trên class, không áp dụng cho implemented interfaces và method annotations.
- [Repeatable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): khai báo annotation lặp và container.
- [Class — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): các phương thức `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, `getDeclaredAnnotationsByType`.
- [Method — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): tra cứu metadata trên phương thức và phân biệt phương thức inherited với overridden.

**Tóm lại:** Để kiểm thử annotation lookup chính xác, phải phân biệt **annotation của chính khai báo**, **kế thừa qua superclass** và **annotation lặp nằm trong container**. `getAnnotation` và `getAnnotationsByType` không thể thay thế nhau khi có `@Repeatable`. Dùng các API Declared để xác định giá trị của riêng class, thêm test cho che khuất, method override và interface, và viết logic merge riêng khi yêu cầu nghiệp vụ vượt quá quy tắc `@Inherited` của Java.
