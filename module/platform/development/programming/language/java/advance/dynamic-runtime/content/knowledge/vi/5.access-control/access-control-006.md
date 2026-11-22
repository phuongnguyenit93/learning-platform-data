# 5.6 Chẩn đoán `IllegalAccessException` và `InaccessibleObjectException`

Khi dùng Reflection trong Java, hai lỗi có tên gần giống nhau thường xuất hiện ở hai **bước khác nhau**:

- `IllegalAccessException` là **checked exception**: thông thường, chương trình đã tìm được field, method hoặc constructor nhưng **không có quyền truy cập khi đọc/ghi/gọi** nó. Những API tiêu biểu là `Field.get/set`, `Method.invoke`, `Constructor.newInstance`; các API của `MethodHandles.Lookup` cũng có thể báo ngoại lệ này trong một số tình huống lookup/access.
- `InaccessibleObjectException` là **unchecked exception**, xuất hiện điển hình khi gọi `AccessibleObject.setAccessible(true)` để yêu cầu bỏ kiểm tra truy cập nhưng **Java Platform Module System (JPMS)** không cho phép mở quyền sâu như vậy. Đây là một trong những biểu hiện của *strong encapsulation* trên Java 9+, đặc biệt rõ từ JDK 17.

Hai trường hợp có thể xảy ra trên **cùng một member**: gọi trực tiếp khi chưa đủ quyền dẫn tới `IllegalAccessException`; thử ép `setAccessible(true)` trên member nằm trong package không được `opens` dẫn tới `InaccessibleObjectException`. Muốn xử lý đúng phải biết **API nào phát sinh lỗi, member thuộc lớp/module nào, caller là ai và đang cần public API hay private reflection**.

Mục tiêu bài học: đọc được stack trace, phân biệt lỗi ở bước tìm member với lỗi ở bước dùng member, kiểm tra quyền truy cập hiện có bằng `canAccess`, thử mở quyền an toàn bằng `trySetAccessible`, hiểu `exports`/ `opens`, và khắc phục bằng đúng hợp đồng Java thay vì mở quyền tràn lan.

## 1. Bản đồ các bước Reflection và vị trí lỗi

Hãy phân tách một thao tác Reflection thành năm bước:

1. **Xác định kiểu:** ví dụ `Class.forName(name)` hoặc `SomeClass.class`.
2. **Tìm member:** `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`, `getConstructor`, `getDeclaredConstructor`.
3. **Kiểm tra khả năng truy cập:** đọc modifier, `member.canAccess(receiver)`, và nếu thật sự cần thì `trySetAccessible()` hoặc `setAccessible(true)`.
4. **Thực thi:** `Field.get/set`, `Method.invoke`, `Constructor.newInstance`.
5. **Xử lý lỗi của code được gọi:** method/constructor có thể tự ném lỗi, thường được `InvocationTargetException` bao bọc.

| Hiện tượng | Điểm xuất hiện | Điều cần hiểu |
| --- | --- | --- |
| `NoSuchFieldException` / `NoSuchMethodException` | Bước **tìm member** | Không tìm được tên/chữ ký theo API đã chọn; chưa kết luận gì về quyền gọi |
| `IllegalAccessException` | Bước **đọc/ghi/gọi** bằng Reflection; cũng có ở một số API lookup khác | Member tồn tại nhưng access check không cho caller sử dụng |
| `trySetAccessible() == false` | Bước **xin bỏ access check** | Không thể mở quyền sâu theo quy tắc hiện tại; bản thân `false` không phải exception |
| `InaccessibleObjectException` | Thường tại `setAccessible(true)` | Yêu cầu suppress access check bị từ chối, thường do package của named module không được mở |
| `InvocationTargetException` | Sau khi đã gọi được method/constructor | Body của method/constructor ném lỗi; xem `getCause()` |
| `IllegalArgumentException` | Khi gọi Reflection với đối số/receiver không phù hợp | Không đồng nghĩa với thiếu quyền; kiểm tra số lượng/kiểu tham số và receiver |
| `ExceptionInInitializerError` | Khi JVM khởi tạo lớp | Static initializer thất bại; không sửa bằng `setAccessible` |

Vì vậy, thao tác đầu tiên khi chẩn đoán là **xác định chính xác dòng lệnh ném ngoại lệ**. Nếu `getDeclaredMethod("run")` đã thành công nhưng `invoke(target)` ném `IllegalAccessException`, việc đổi tên method hoặc tìm thêm overload thường không giải quyết gốc rễ.

## 2. Quyền truy cập trong Java có nhiều lớp kiểm soát

Reflection chịu tác động đồng thời của:

- **Quy tắc ngôn ngữ:** `public`, `protected`, package-private (không có modifier), `private`; quyền của *declaring class* cũng quan trọng, không chỉ của member.
- **Quan hệ caller và declaring class:** cùng lớp, cùng package, subclass, nestmates, hay lớp thuộc package khác. Các lớp cùng *nest* có thể truy cập private members của nhau theo quy tắc Java hiện đại; chỉ vì một method là private chưa chắc caller đang bị cấm.
- **Java Platform Module System (JPMS):** từ Java 9, module có thể công khai public API bằng `exports`, nhưng giữ private/package-private implementation đóng với reflection nếu package không `opens`.
- **Cách chạy:** classpath thường đưa lớp ứng dụng vào *unnamed module*; module-path tạo các *named modules* với descriptor riêng. Quyền giữa hai cách chạy có thể khác nhau.
- **Các chính sách runtime khác:** chẳng hạn security checks trong môi trường có cấu hình tương ứng; và quy tắc đặc biệt của một số field không thể được sửa dù access check đã được suppress.

### 2.1. Đọc modifier của member chưa đủ

Ví dụ một lớp package-private chứa method `public`:

```java
package demo.internal;

class InternalService {
    public void execute() {
        System.out.println("executed");
    }
}
```

Một caller ở package khác có thể tìm được một public method bằng cơ chế Reflection thích hợp, nhưng điều đó không chứng minh nó được phép gọi method của declaring class không public. Khi gặp `IllegalAccessException`, hãy kiểm tra **cả `member.getModifiers()` và `member.getDeclaringClass().getModifiers()`**.

Tương tự, nếu bạn cố gọi private constructor từ một lớp không có quyền, `Constructor.newInstance()` có thể ném `IllegalAccessException`, dù `getDeclaredConstructor()` đã trả về đối tượng `Constructor` thành công.

### 2.2. `getMethod` và `getDeclaredMethod` không cấp quyền

Hai lệnh sau có ý nghĩa khác nhau:

```java
type.getMethod("work");         // Tìm public method phù hợp, kể cả public method kế thừa
type.getDeclaredMethod("work"); // Tìm method khai báo tại chính lớp, bất kể visibility
```

`getDeclaredMethod` **không** có nghĩa “được quyền gọi private method”. Nó chỉ cho phép khám phá metadata của member khai báo. `getDeclaredField` và `getDeclaredConstructor` cũng vậy. Không có guarantee rằng `getDeclared...` trả về member có thể dùng trực tiếp từ caller.

Ngược lại, `getMethod` tìm public member nhưng method của một class không truy cập được vẫn có thể gây access error khi invoke. Vì thế hãy phân biệt **member được tìm thấy** với **member gọi được**.

## 3. `IllegalAccessException`: tìm thấy member nhưng gọi không được

Giả sử một domain class có private constructor, field và method. Chạy Reflection từ một **top-level class khác**, không cùng nest, để thấy ba access check riêng:

Tạo tệp **`AccessExceptionDemo.java`** (JDK 17+):

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class SecretBox {
    private final String secret;

    private SecretBox(String secret) {
        this.secret = secret;
    }

    private String reveal() {
        return "value=" + secret;
    }
}

public class AccessExceptionDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<SecretBox> ctor =
                SecretBox.class.getDeclaredConstructor(String.class);
        System.out.println("constructor accessible: "
                + ctor.canAccess(null));
        try {
            ctor.newInstance("java");
        } catch (IllegalAccessException e) {
            System.out.println("constructor: IllegalAccessException");
        }

        System.out.println("constructor override: "
                + ctor.trySetAccessible());
        SecretBox box = ctor.newInstance("java");

        Field field = SecretBox.class.getDeclaredField("secret");
        try {
            field.get(box);
        } catch (IllegalAccessException e) {
            System.out.println("field: IllegalAccessException");
        }

        System.out.println("field override: "
                + field.trySetAccessible());
        System.out.println("field value: " + field.get(box));

        Method method = SecretBox.class.getDeclaredMethod("reveal");
        try {
            method.invoke(box);
        } catch (IllegalAccessException e) {
            System.out.println("method: IllegalAccessException");
        }

        System.out.println("method override: "
                + method.trySetAccessible());
        System.out.println("method result: " + method.invoke(box));
    }
}
```

Biên dịch và chạy trên **classpath thông thường**, không thiết lập chính sách truy cập bổ sung:

```bash
javac --release 17 AccessExceptionDemo.java
java AccessExceptionDemo
```

Stdout:

```text
constructor accessible: false
constructor: IllegalAccessException
constructor override: true
field: IllegalAccessException
field override: true
field value: java
method: IllegalAccessException
method override: true
method result: value=java
```

### Vì sao ví dụ chạy như vậy?

1. `getDeclaredConstructor(String.class)` và `getDeclaredField("secret")` tìm được **metadata**, dù member là `private`.
2. `AccessExceptionDemo` và `SecretBox` là **hai top-level classes**. Chúng không phải nestmates; caller không có quyền truy cập trực tiếp vào private members.
3. `ctor.canAccess(null)` trả `false`; constructor không cần receiver object, nên đối số của `canAccess` là `null`.
4. Trước khi mở quyền, `newInstance`, `field.get` và `method.invoke` ném `IllegalAccessException`; chương trình bắt đúng từng trường hợp.
5. Hai class ứng dụng ở cùng **unnamed module** trên classpath; suppress access checks cho các private members này được phép. Do đó cả ba `trySetAccessible()` trả `true`.
6. Khi được phép mở quyền, những lời gọi lại thành công và in giá trị như đã dự đoán.

**Lưu ý môi trường:** Kết quả ví dụ được thiết kế cho hai top-level classes trong cùng source file và cách chạy classpath trên JDK 17+, không có sandbox/security checks đặc biệt. Nếu chuyển các class sang named modules khác nhau, kết quả `trySetAccessible` có thể đổi vì quy tắc `opens`.

Không lấy ví dụ private **nested class** bên trong `AccessExceptionDemo` rồi khẳng định chắc chắn bị từ chối: các lớp thuộc cùng nest có thể được quyền truy cập private theo Java 11+. Đó là nguyên nhân một số thí nghiệm Reflection thực tế khác với trực giác ban đầu.

## 4. `InaccessibleObjectException`: yêu cầu mở quyền sâu bị từ chối

Kể từ JPMS, một named module có thể cố ý **không mở package** cho module khác. `setAccessible(true)` chỉ yêu cầu bỏ kiểm tra access nếu mô hình module cho phép; nó không vượt qua mọi giới hạn.

Ví dụ thường gặp là cố truy cập `private` field nội bộ của một class JDK trong `java.base`:

Tạo tệp **`ModuleBlockDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class ModuleBlockDemo {
    public static void main(String[] args)
            throws NoSuchFieldException {
        Field field = String.class.getDeclaredField("value");

        System.out.println("declaring module: "
                + field.getDeclaringClass().getModule().getName());
        System.out.println("trySetAccessible: "
                + field.trySetAccessible());

        try {
            field.setAccessible(true);
            System.out.println("setAccessible: succeeded");
        } catch (InaccessibleObjectException e) {
            System.out.println(
                    "setAccessible: InaccessibleObjectException");
        }
    }
}
```

Chạy trên **OpenJDK 17/21 mặc định**, không thêm JVM option mở package:

```bash
javac --release 17 ModuleBlockDemo.java
java ModuleBlockDemo
```

Kết quả trong cấu hình đó:

```text
declaring module: java.base
trySetAccessible: false
setAccessible: InaccessibleObjectException
```

Field `String.value` là **chi tiết triển khai của JDK dùng riêng cho minh họa**, không phải API ổn định để application phụ thuộc vào. Những phiên bản/triển khai JDK khác có thể đổi cấu trúc nội bộ; mục tiêu bài này là mô hình access control.

Giải thích:

- `getDeclaredField("value")` tìm được field metadata, nhưng **không** mở quyền.
- Package `java.lang` thuộc named module `java.base` và **không mở quyền sâu mặc định** cho unnamed module của ứng dụng.
- `trySetAccessible()` báo `false` một cách có kiểm soát.
- `setAccessible(true)` đòi bật suppression, không được phép nên ném `InaccessibleObjectException` ngay tại lời gọi đó. Chưa hề chạy `field.get(...)` hay `field.set(...)`.

Nếu chạy riêng bài thực nghiệm này với JVM option:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED ModuleBlockDemo
```

Thì trong cùng OpenJDK có field nêu trên, output đổi thành:

```text
declaring module: java.base
trySetAccessible: true
setAccessible: succeeded
```

`--add-opens` ở đây chỉ minh họa **thay đổi điều kiện access check**. Đây không phải khuyến nghị sửa code production bằng cách truy cập `String.value`; ứng dụng thông thường nên sử dụng API công khai của `String`.

### 4.1. Dạng thông báo lỗi thường gặp

Một thông báo `InaccessibleObjectException` có thể chứa nội dung như:

```text
Unable to make field private final byte[] java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module
```

Cách đọc: **đích** là private field `String.value`; **module sở hữu** là `java.base`; **package cần mở** là `java.lang`; **module caller** là unnamed module. Các tên này giúp xác định chính xác nơi cấu hình hoặc thiết kế đang không tương thích. Đừng chỉ tìm tên `InaccessibleObjectException` rồi thêm một JVM flag mở quá rộng.

## 5. `canAccess`, `trySetAccessible`, `setAccessible` khác nhau thế nào?

Cả ba là API trên `AccessibleObject`, lớp cha của `Field`, `Method`, `Constructor`.

| API | Chức năng | Kết quả / lỗi | Tác động |
| --- | --- | --- | --- |
| `canAccess(receiver)` | Hỏi caller **hiện tại** có thể truy cập member qua object này không | `true`/`false`; sai receiver có thể ném `IllegalArgumentException` | Chỉ kiểm tra, không sửa trạng thái |
| `trySetAccessible()` | Thử bật suppression của Java language access checks | `true` nếu thành công; `false` khi không thể bật vì giới hạn access/module | Có thể đổi trạng thái accessibility của **đối tượng reflection này** |
| `setAccessible(true)` | Yêu cầu bật suppression | Thành công hoặc ném `InaccessibleObjectException` nếu không được phép | Có thể đổi trạng thái accessibility của object này |
| `setAccessible(false)` | Tắt suppression đã bật | Trở về access checks thông thường | Không đổi modifier hoặc cấu trúc lớp |

Trong cả `trySetAccessible` và `setAccessible`, vẫn có thể có `SecurityException` khi có security checks phù hợp. Đừng giả định `trySetAccessible()` tuyệt đối không bao giờ ném exception.

### 5.1. `canAccess` cần receiver đúng

- Với `Constructor`, `static Field`, `static Method`: gọi `canAccess(null)`.
- Với instance field/method: truyền một object thuộc declaring class hoặc subtype phù hợp, ví dụ `field.canAccess(target)`, `method.canAccess(target)`.
- Truyền `null` vào `canAccess` của instance field/method hoặc receiver không tương thích có thể tạo `IllegalArgumentException`. Đó là **lỗi dùng API**, không chứng minh member đang bị JPMS chặn.

`canAccess` cho biết access từ **caller thực hiện phép kiểm tra**, vì vậy chuyển code vào lớp/package/module khác có thể đổi kết quả. Đồng thời `canAccess` trên một `AccessibleObject` đã được suppress thành công có thể trả `true`, kể cả khi Java source bình thường không được viết trực tiếp cùng phép truy cập.

### 5.2. Chọn cách gọi khi buộc phải dùng private reflection

Mẫu xử lý trong một method có biến `Field field` và `Object target` đã được kiểm tra:

```java
if (!field.canAccess(target)) {
    if (!field.trySetAccessible()) {
        throw new IllegalStateException(
                "No reflective access to "
                + field.getDeclaringClass().getName()
                + "." + field.getName());
    }
}
Object value = field.get(target);
```

Đây là **đoạn minh họa, không phải chương trình độc lập**; method bao ngoài cần xử lý `IllegalAccessException`, và `target` phải phù hợp với instance field (hoặc là `null` nếu là static field). `trySetAccessible` cho phép bạn từ chối có chủ đích và báo lỗi rõ ràng khi package không mở. Nó không biến mọi quyền bị từ chối thành một giá trị hợp lệ; không nên nuốt lỗi rồi gán default tùy ý.

Nếu bạn chỉ dùng **public API hợp lệ**, thường **không cần** `setAccessible(true)`: hãy thiết kế hoặc gọi đúng public member của public class thuộc package đã export, thay vì bật suppression theo thói quen.

## 6. JPMS: `exports` khác `opens`

Module descriptor trong `module-info.java` mô tả package nào được công khai cho module khác và package nào cho phép Reflection sâu. Sự khác biệt là gốc của rất nhiều lỗi sau khi chuyển ứng dụng lên JDK 17+ hoặc chuyển từ classpath sang module-path.

| Cấu hình trong module sở hữu package | Truy cập compile-time/public API từ module khác | Deep reflection vào non-public members |
| --- | --- | --- |
| `exports p;` | Cho phép sử dụng public types của package `p`, với quan hệ module phù hợp | **Không tự cho phép** bypass private/package-private access |
| `exports p to m;` | Chỉ export public API tới module `m` | Vẫn **không tự mở** private reflection |
| `opens p;` | Không tự export để import public types trong source | Cho phép runtime deep reflection từ các module khác theo access API |
| `opens p to m;` | Không tự export cho compile-time | Mở reflection sâu cho module `m` |
| `open module x { ... }` | Không tự export mọi package | Mở toàn bộ package trong module; phạm vi lớn |
| Không `exports` và không `opens` | Public API ở package đó không được xuất ra module khác | Không cho deep reflection giữa các module |

Ví dụ module domain cần public API cho ứng dụng, nhưng chỉ cho framework được chỉ định phản chiếu vào implementation:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.serializer;
}
```

Giải thích: module `com.example.serializer` được phép reflective access sâu vào `com.example.domain.model` nếu các điều kiện Reflection khác thỏa mãn. Ngược lại, source code của module này **không** tự động được `import` public type từ `com.example.domain.model` chỉ nhờ `opens`.

Trong module của caller:

```java
module com.example.serializer {
    requires com.example.domain;
}
```

Hai đoạn là **hai tệp `module-info.java` ở hai module khác nhau**, không thể đặt chung một tệp Java. Trong module domain có thể tồn tại nhiều package; tên package nêu trên là ví dụ cấu trúc. Không cần tạo toàn bộ ứng dụng module để hiểu nguyên tắc mở quyền có giới hạn.

### 6.1. `exports` đủ cho public reflection khi nào?

Nếu caller cần gọi một **public method của một public class** trong package được export đến caller (và quan hệ module hợp lệ), public reflection thường dùng được mà không cần `opens`. Trong tình huống này, cố gọi `setAccessible(true)` là không cần thiết.

Nếu caller cần một private field/constructor, hoặc member không public, `exports` **chưa đủ**. Hãy cân nhắc một API/factory công khai; nếu framework thật sự yêu cầu deep reflection, cấu hình `opens` tối thiểu cho đúng package và đúng module.

Lưu ý: việc compiler cho phép reference đến public type không chứng minh caller có thể sử dụng mọi member của type. Modifier của member và các quy tắc Java vẫn áp dụng.

### 6.2. Vì sao `--add-exports` không sửa được mọi lỗi?

Hai JVM options có mục tiêu khác nhau:

```text
--add-exports <module>/<package>=<target-modules>
--add-opens   <module>/<package>=<target-modules>
```

- `--add-exports` bổ sung quyền export package cho phép dùng public API trong phạm vi target; không tự cho deep reflection vào private members.
- `--add-opens` bổ sung quyền mở package cho phép truy cập sâu qua Reflection trong phạm vi target, nhưng không biến các private fields/methods thành public source API.

Ví dụ đích là classpath app, target thường viết `ALL-UNNAMED`. Nếu caller là named module thì dùng **tên module cụ thể**, ví dụ `com.example.serializer`. Đừng nhầm tên package với tên module ở hai bên của dấu `/`.

Trong triển khai thực tế, ưu tiên sửa **module descriptor do bạn sở hữu**. Chỉ dùng launch flags như biện pháp tương thích có chủ đích khi không thể sửa module nguồn, ghi rõ lý do và phạm vi mở. Với JDK internals, việc mở module có thể khiến ứng dụng phụ thuộc vào cấu trúc không phải public API.

## 7. Quy trình chẩn đoán tuần tự khi gặp lỗi

Khi nhận một stack trace hoặc issue report, hãy giải quyết theo đúng thứ tự sau.

### Bước 1 — Đặt tên lỗi và API gây lỗi

Ghi chính xác:

- Class/member mục tiêu, ví dụ `com.example.User#name`, `java.lang.String#value`.
- API lỗi: `getDeclaredField`, `Field.get`, `Method.invoke`, `Constructor.newInstance`, `setAccessible`, `trySetAccessible`, hay `MethodHandles.privateLookupIn`.
- Loại ngoại lệ đầy đủ và cause. Không gom `NoSuchMethodException`, `IllegalAccessException`, `InaccessibleObjectException`, `InvocationTargetException` thành cùng một nhãn “Reflection không hoạt động”.

Nếu `getDeclaredMethod` ném `NoSuchMethodException`, hãy sửa tên/chữ ký và kiểm tra `getMethod` vs `getDeclaredMethod` trước. Đừng mở module để xử lý một method thật sự không tồn tại.

### Bước 2 — Xác nhận member và declaring class thực sự

`getDeclaringClass()` là class **khai báo member**, có thể khác class được người dùng chọn trong cấu hình. Với method kế thừa, kiểm tra member được khai báo ở superclass/interface nào. Đọc:

```java
Class<?> owner = method.getDeclaringClass();
String memberModifiers =
        java.lang.reflect.Modifier.toString(method.getModifiers());
String ownerModifiers =
        java.lang.reflect.Modifier.toString(owner.getModifiers());
```

Đây là **đoạn minh họa** khi `method` là `java.lang.reflect.Method` đã được tìm. Nếu method là public nhưng owner package-private, hành vi truy cập khác với public method của public class.

### Bước 3 — Kiểm tra caller và module ranh giới

Dùng `Class.getModule()` và `Class.getPackageName()` để biết member thuộc module/package nào. Ví dụ method chẩn đoán tái sử dụng trong một class Java 17+:

```java
static void printBoundary(java.lang.reflect.Member member,
                          Class<?> callerClass) {
    Class<?> owner = member.getDeclaringClass();
    Module ownerModule = owner.getModule();
    Module callerModule = callerClass.getModule();
    String packageName = owner.getPackageName();

    System.out.println("declaring class: " + owner.getName());
    System.out.println("member: " + member.getName());
    System.out.println("package: " + packageName);
    System.out.println("owner module: "
            + (ownerModule.isNamed()
                    ? ownerModule.getName() : "<unnamed>"));
    System.out.println("caller module: "
            + (callerModule.isNamed()
                    ? callerModule.getName() : "<unnamed>"));
    System.out.println("exported to caller: "
            + ownerModule.isExported(packageName, callerModule));
    System.out.println("open to caller: "
            + ownerModule.isOpen(packageName, callerModule));
}
```

`Member` dùng chung cho `Field`, `Method`, `Constructor`. Đây là **method minh họa**, cần đặt trong class và gọi với class thực sự chứa đoạn Reflection của ứng dụng; truyền sai `callerClass` sẽ dẫn đến kết quả mô tả sai ranh giới module. `isExported` và `isOpen` cung cấp metadata module, không thay thế kiểm tra modifier/receiver; `trySetAccessible` vẫn là phép thử khả năng mở quyền cho member cụ thể.

Khi xem stack trace, phân biệt **module của thư viện gọi Reflection** với module chứa entrypoint `main`: hai module đó có thể không giống nhau. Nếu một serializer chạy trong `com.example.serializer` thì package phải mở cho module đó, không chỉ cho module ứng dụng.

### Bước 4 — Kiểm tra receiver và chữ ký

Với instance field/method, `canAccess(instance)` cần object đúng kiểu. Với static field/method hoặc constructor, `canAccess(null)`. Với `Method.invoke` và `Constructor.newInstance`, kiểm tra parameter types, số lượng argument, primitive unboxing/widening và các varargs đặc biệt.

Đừng diễn giải `IllegalArgumentException` do receiver không hợp lệ thành `IllegalAccessException`. Khi constructor chạy và ném lỗi nghiệp vụ, `InvocationTargetException.getCause()` mới là nơi tìm nguyên nhân.

### Bước 5 — Chọn giải pháp nhỏ nhất đúng hợp đồng

Thứ tự ưu tiên hợp lý:

1. Gọi public API hiện có của một public class trong package được export hợp lệ.
2. Nếu bạn sở hữu class: thiết kế method, constructor hoặc factory phù hợp thay cho private reflection nếu đó là API cần công khai.
3. Nếu framework thực sự cần Reflection sâu: mở **đúng package cho đúng module** bằng `opens ... to ...`.
4. Nếu không kiểm soát module descriptor: đánh giá JVM flag `--add-opens` với target hẹp trong môi trường bạn quản lý.
5. Nếu member là implementation detail JDK hoặc thư viện không hỗ trợ: chuyển sang API công khai/thư viện tương thích thay vì xây dependency lâu dài vào private field.
6. Nếu không thể cấp quyền hợp lệ: dừng có thông điệp cấu hình rõ ràng, kèm tên member và module/package bị chặn.

Không nên xử lý bằng `catch (Exception ignored)`, trả `null` hoặc tự tạo object rỗng rồi để lỗi xuất hiện ở chỗ khác. Điều đó làm mất địa chỉ lỗi và có thể khiến dữ liệu sai mà khó phát hiện.

## 8. Khi `setAccessible(true)` không giải quyết `IllegalAccessException`

`setAccessible(true)` là một công cụ có giới hạn, không phải “nút tắt quyền” chung. Trước khi dùng, xét một trong các nhóm sau:

**Nhóm A — Access check do modifier/package trong cùng module:** có thể dùng `trySetAccessible` trong phạm vi framework được thiết kế rõ; hoặc tốt hơn, gọi public API. Ví dụ `SecretBox` từ chương trình đầu thuộc nhóm này.

**Nhóm B — Named module chưa mở package:** `setAccessible(true)` ném `InaccessibleObjectException`; `trySetAccessible` trả `false`. Cần sửa `opens` hoặc bỏ việc truy cập private member, không tiếp tục gọi `Field.get` nhiều lần.

**Nhóm C — Không phải lỗi access:** constructor không tồn tại (`NoSuchMethodException`), receiver sai (`IllegalArgumentException`), target tự ném lỗi (`InvocationTargetException`), field type sai, class initialization lỗi. Mở quyền không làm chúng biến mất.

**Nhóm D — Quy tắc ghi field đặc biệt:** một số `final` fields (ví dụ record components, hidden classes) có hạn chế riêng; suppress access check không cấp quyền sửa mọi state. Reflection vào nội bộ JDK có thể không ổn định theo phiên bản. Nếu thiết kế cần thay đổi state, chọn constructor/method domain hợp lệ.

**Nhóm E — `MethodHandles` và `privateLookupIn`:** cơ chế lookup có policy access riêng; các hàm như `MethodHandles.privateLookupIn(targetClass, lookup)` yêu cầu điều kiện module/readability và `opens` thích hợp khi vượt module. Nó có thể ném `IllegalAccessException` nếu không có quyền. Chuyển sang Method Handles **không** có nghĩa bypass JPMS.

Sự khác nhau giữa **truy cập Java language** và **khả năng đọc/ghi state thực tế** giúp tránh những giải pháp vừa nguy hiểm vừa không hiệu quả.

## 9. Chẩn đoán lỗi khi nâng cấp Java 8 → 17+

Trên Java 8, framework thường thử `setAccessible(true)` vào nhiều chi tiết nội bộ JDK. Khi chạy trên JDK 9+, JPMS đưa thêm ranh giới module. JDK 17 áp dụng strong encapsulation với JDK internals mạnh hơn; cách dựa vào “illegal reflective access” từng được cảnh báo ở các bản trước không còn là giải pháp mặc định.

Những dấu hiệu phổ biến:

- Stack trace bắt đầu tại `java.lang.reflect.AccessibleObject.checkCanSetAccessible` hoặc `Field.setAccessible`, theo sau là `InaccessibleObjectException`.
- Thông báo có dạng `module java.base does not "opens java.lang" to ...`, hoặc một package khác trong named module.
- Ứng dụng chạy được trên classpath nhưng lỗi khi chuyển sang module-path vì class nay thuộc named module với descriptor tường minh.
- Một thư viện serialization, ORM, DI hoặc test framework cố lấy private members của domain class mà package của module chưa `opens`.
- Dự án có `--add-exports` nhưng đang cố gọi private field, dẫn tới nhầm lẫn vì public API export không tương đương deep reflection.

Cách xử lý khi nâng cấp: kiểm tra phiên bản/thư viện có hỗ trợ Java mục tiêu hay không; đọc owner module/package trong lỗi; ưu tiên bản thư viện sử dụng supported API; mở đúng package cho module framework nếu domain module của bạn chủ đích cho phép Reflection; ghi lại JVM flags nếu bắt buộc phải dùng.

Tránh coi việc thêm hàng loạt `--add-opens` là giải pháp vĩnh viễn. Một package bị đóng thường biểu thị ranh giới API mà module chủ sở hữu muốn duy trì.

## 10. Mẫu xử lý ngoại lệ rõ nguyên nhân trong framework

Một utility có thể cần báo một lỗi cấu hình đã được chuẩn hóa mà vẫn giữ cause. Ví dụ method sau chỉ dùng **public no-arg constructor** và không suppress access checks:

```java
static <T> T createPublicNoArg(Class<T> type) {
    try {
        return type.getConstructor().newInstance();
    } catch (NoSuchMethodException e) {
        throw new IllegalArgumentException(
                "No public no-arg constructor: " + type.getName(), e);
    } catch (IllegalAccessException e) {
        throw new IllegalStateException(
                "Public constructor inaccessible: " + type.getName(), e);
    } catch (InstantiationException e) {
        throw new IllegalArgumentException(
                "Cannot instantiate type: " + type.getName(), e);
    } catch (java.lang.reflect.InvocationTargetException e) {
        Throwable cause = e.getCause();
        throw new IllegalStateException(
                "Constructor threw exception: " + type.getName(), cause);
    }
}
```

Đây là **method minh họa bên trong một class Java 17+**, không phải chương trình độc lập; `type` là một `Class<T>` nhận từ caller. Constructor public vẫn có thể bị chặn khi declaring class không public hoặc module chưa export package phù hợp. Utility không thử gọi private constructor và không nuốt ngoại lệ được ném bởi domain code. Trong API chuyên biệt, bạn có thể muốn giữ nguyên một `RuntimeException` hoặc `Error` từ target thay vì bọc lại; lựa chọn phụ thuộc hợp đồng lỗi của framework.

Với thao tác deep reflection, nên xử lý khả năng mở quyền trước khi gọi:

```java
static Object readField(java.lang.reflect.Field field, Object receiver)
        throws IllegalAccessException {
    if (!field.canAccess(receiver) && !field.trySetAccessible()) {
        throw new IllegalStateException(
                "Package not open for reflective field access: "
                + field.getDeclaringClass().getName()
                + "#" + field.getName());
    }
    return field.get(receiver);
}
```

Đoạn này là **method độc lập về mặt chữ ký nhưng phải đặt trong một class**. `receiver` là instance đúng kiểu nếu field không static; truyền `null` cho field static. `trySetAccessible()` trả `false` khi không thể bật suppression, vì vậy thông điệp chỉ nên mô tả thiếu quyền reflection nói chung; một nguyên nhân khác như security checks vẫn có thể xuất hiện riêng. Trước khi dùng cho input không tin cậy, phải giới hạn tập loại/member mà framework được phép truy cập, vì mở reflection vào private state không phải hành vi an toàn theo mặc định.

## 11. Những nhầm lẫn gây chẩn đoán sai

### 11.1. Nhầm `IllegalAccessException` với `IllegalAccessError`

`IllegalAccessException` là **checked exception** thường gặp từ API Reflection. `IllegalAccessError` là **`LinkageError`**, có thể xuất hiện khi bytecode/linkage cố truy cập một class hoặc member không được phép theo cấu trúc runtime, chẳng hạn sau khi thay đổi binary compatibility. Hai tên giống nhau nhưng nguyên nhân, đường kiểm tra và xử lý khác nhau. Đừng bắt `IllegalAccessException` rồi cho rằng đã bao phủ `IllegalAccessError`.

### 11.2. Nhầm `InvocationTargetException` với lỗi quyền

Khi `Method.invoke` hoặc `Constructor.newInstance` thực sự gọi được target, exception do **body của target** phát sinh được bọc trong `InvocationTargetException`. Ví dụ body ném `IllegalStateException` thì không phải lỗi quyền. Xem `getCause()` và stack trace gốc.

Trường hợp hiếm khi target tự cố mở reflection vào module khác rồi ném `InaccessibleObjectException`: nó có thể xuất hiện **bên trong cause của `InvocationTargetException`**, vì lúc này lỗi là từ code target, khác với lỗi trực tiếp tại lời gọi `setAccessible` của caller. Vì vậy phải đọc toàn bộ chuỗi `cause`.

### 11.3. Nhầm “có thể tìm” với “được phép dùng”

`getDeclaredField`, `getDeclaredMethod` và `getDeclaredConstructor` có thể trả metadata của private members. Chính việc invoke/get/set mới cần thêm access check. Không dựa vào sự tồn tại của `Field` để kết luận quyền đã được cấp.

### 11.4. Nhầm “cùng package” với “cùng module”

Java package là namespace; module là một tầng boundary khác. Một caller có thể dùng package name quen thuộc nhưng vẫn thuộc named module khác, và việc open/export được kiểm tra theo **module thực tế**. Khi có nhiều class loaders, cùng tên lớp cũng chưa đủ để khẳng định cùng runtime type; kiểm tra declaring class, loader và module của object thực tế.

### 11.5. Nhầm `opens` với public API vĩnh viễn

`opens` trao quyền reflection sâu trong runtime, **không** tạo API được compiler bảo đảm tương thích. Nếu framework truy cập private field, thay đổi tên field giữa các bản phát hành vẫn phá code. Public method/factory rõ hợp đồng thường bền hơn.

### 11.6. Nhầm `trySetAccessible(false)` với trạng thái vĩnh viễn

`trySetAccessible()` có thể trả `false` trong runtime hiện tại do module chưa mở, nhưng khi thay đổi module descriptor hoặc launcher flags một cách hợp lệ, kết quả có thể khác. Không cache kết luận đó cho mọi class loader, mọi deployment, mọi phiên bản JDK.

### 11.7. Nhầm `setAccessible(true)` với sửa modifier

Nó không biến field thành `public` hoặc sửa class file; nó yêu cầu suppress Java language access checks cho đối tượng Reflection cụ thể theo quy tắc runtime. Điều đó không đồng nghĩa mọi đối tượng khác hoặc mọi caller có quyền tương tự.

## 12. Bảng quyết định nhanh theo stack trace

| Điểm lỗi đầu tiên đáng chú ý | Hướng điều tra ưu tiên | Cách khắc phục phù hợp |
| --- | --- | --- |
| `Class.getDeclaredMethod` / `getDeclaredField` ném `NoSuch...` | Tên, chữ ký, declaring class, API declared vs inherited | Chọn đúng member thực sự tồn tại |
| `Method.invoke` ném `IllegalAccessException` | Modifier method + declaring class; caller; module exports | Gọi public API hoặc cấu hình visibility đúng |
| `Constructor.newInstance` ném `IllegalAccessException` | Constructor visibility, class visibility, module boundary | Dùng public constructor/factory; deep reflection có kiểm soát |
| `Field.get/set` ném `IllegalAccessException` | Field private/package-private, receiver, class và module | Truy cập qua accessor hoặc mở quyền hợp lệ |
| `trySetAccessible()` trả `false` | Owner module/package và caller module | Cần `opens` đúng phạm vi hoặc thay API |
| `setAccessible(true)` ném `InaccessibleObjectException` | Thông báo `does not "opens ..."` | Sửa JPMS `opens`, giới hạn JVM flag, hoặc bỏ private reflection |
| `Method.invoke` trả `InvocationTargetException` | `getCause()` của target | Sửa logic method hoặc input; giữ cause |
| `newInstance` trả `InstantiationException` | Abstract class hoặc kiểu không khởi tạo được | Dùng implementation cụ thể |
| `canAccess` ném `IllegalArgumentException` | Receiver null/sai kiểu | Cung cấp đúng receiver hoặc `null` cho static/constructor |

Bảng là định hướng điều tra, không thay thế kiểm tra ngữ cảnh thực tế. Tên exception chỉ là điểm khởi đầu; stack trace, class/module cụ thể và hợp đồng API mới quyết định sửa ở đâu.

## 13. Kiểm thử cần có sau khi sửa

Nên xác minh trên **đúng JDK và cách chạy thật** (classpath hoặc module-path), không chỉ trong IDE. Những trường hợp hữu ích:

- Public class + public member trong package được export: gọi được mà không cần suppress access checks.
- Private member trong cùng unnamed module: `trySetAccessible` được cho phép nếu không có chính sách bổ sung, nhưng điều này không là lý do để dùng private API tùy tiện.
- Private member của named module khác với package **không** `opens`: `trySetAccessible` trả `false`, `setAccessible(true)` ném `InaccessibleObjectException`.
- Named module chủ động `opens p to caller.module`: deep reflection của caller được phép trong phạm vi mở, nếu các điều kiện khác đúng.
- Member public nhưng declaring class không accessible: kiểm tra `IllegalAccessException` và thông điệp rõ ràng.
- Method/constructor target ném lỗi: framework phải nhận diện `InvocationTargetException.getCause()`, không quy lỗi thành “access denied”.
- Static và instance members: đúng receiver khi `canAccess`/invoke/get.
- Chạy với và không có `--add-opens` trong một **thử nghiệm cách ly**, bảo đảm flag chỉ có hiệu lực ở nơi được chủ động cấu hình.

Khi test chạy được trên classpath nhưng lỗi trên module-path, ghi lại `java --version`, module chứa target và caller, package cần mở, lệnh launch đầy đủ cùng danh sách flags. Thông tin này có giá trị hơn việc chỉ chụp một dòng exception.

## 14. Tình huống thực hành

### Tình huống A — Serializer không đọc được private field của model

Một serializer dùng `modelClass.getDeclaredFields()`, sau đó `field.setAccessible(true)`. Model nằm trong module `com.acme.domain`, package `com.acme.model`, serializer nằm trong `com.acme.serializer`. Exception nêu module domain không `opens` package model.

**Chẩn đoán:** member được tìm thấy; bị chặn tại **mở quyền sâu** vì module boundary, nên là `InaccessibleObjectException` điển hình.

**Cách sửa:** nếu serializer cần deep reflection theo hợp đồng, thêm vào domain descriptor:

```java
opens com.acme.model to com.acme.serializer;
```

Dòng này phải ở trong `module com.acme.domain { ... }`; ví dụ chỉ mô tả directive bổ sung, **không phải một tệp `module-info.java` đầy đủ**. Nếu không muốn expose private structure, cung cấp public properties/getters và cấu hình serializer dùng API đó.

### Tình huống B — Test gọi private method khi không thể suppress access

Một test gọi `getDeclaredMethod("compute")` thành công nhưng `trySetAccessible()` trả `false`. Class nằm trong package chưa được mở từ module của code được test cho module test.

**Chẩn đoán:** không phải `NoSuchMethodException`; cũng không phải method “bị mất” do compiler. Chính sách module đang ngăn private reflection.

**Cách sửa:** kiểm thử qua public contract nếu đủ; nếu framework test thực sự cần reflect private, có thể mở đúng package cho module test trong cấu hình test hoặc thông qua launch option chỉ áp dụng môi trường test. Không lén thêm flag toàn cục vào production.

### Tình huống C — Có public method nhưng vẫn `IllegalAccessException`

Caller dùng Reflection gọi một public method của package-private declaring class từ package khác.

**Chẩn đoán:** public của method chưa đủ; phải xét accessibility của declaring class, cùng package và module. Nếu caller không thể truy cập class, `Method.invoke` có thể bị từ chối.

**Cách sửa:** định nghĩa public interface hoặc một public facade được export; gọi qua hợp đồng công khai. Thử `setAccessible(true)` chỉ khi thật sự có lý do truy cập implementation, trong phạm vi module cho phép.

### Tình huống D — Nâng cấp Java và lỗi với `java.lang.String.value`

Ứng dụng hoặc một thư viện cũ dùng private fields của `String`. Khi lên Java 17, có thông báo `java.base does not "opens java.lang"`.

**Chẩn đoán:** phụ thuộc vào chi tiết JDK internal bị strong encapsulation bảo vệ. Đây là dấu hiệu cần đổi integration, không chỉ sửa cú pháp Reflection.

**Cách sửa:** dùng public `String` API hoặc nâng cấp thư viện sang bản tương thích. Tùy yêu cầu tương thích ngắn hạn, có thể đánh giá `--add-opens java.base/java.lang=ALL-UNNAMED` trong thử nghiệm đã kiểm soát; không coi nó là giải pháp ổn định cho production.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `getDeclaredField("secret")` thành công; `field.get(instance)` ném `IllegalAccessException`. Có phải tên field sai?

**Đáp án:** Không. Lookup đã tìm được field; lỗi xảy ra khi truy cập giá trị. Cần xem modifier, declaring class, caller, quyền module và trạng thái accessibility của đối tượng `Field`.

**Câu 2.** `field.trySetAccessible()` trả `false`; nếu gọi `field.setAccessible(true)` cùng ngữ cảnh thì có thể gặp lỗi gì?

**Đáp án:** Khi nguyên nhân là module không cho suppress access checks, `setAccessible(true)` ném `InaccessibleObjectException`. `trySetAccessible` trả `false` để caller xử lý đường không được mở quyền.

**Câu 3.** Module domain có `exports com.acme.model;` nhưng framework cần đọc private field. `exports` đã đủ chưa?

**Đáp án:** Chưa. `exports` cho phép sử dụng public API trong package; deep reflection từ module khác thường cần `opens com.acme.model to <tên-framework-module>;` hoặc chuyển sang public accessor/factory.

**Câu 4.** `Method.invoke` ném `InvocationTargetException`, cause là `IllegalStateException`. Lỗi quyền hay lỗi logic?

**Đáp án:** Method đã được invoke và chính target ném `IllegalStateException`. Chẩn đoán logic/input bên trong target và preserve cause, không thay đổi `opens` một cách vô căn cứ.

**Câu 5.** Với instance `Method`, gọi `method.canAccess(null)` rồi nhận `IllegalArgumentException`. `setAccessible(true)` có phải cách sửa hợp lý?

**Đáp án:** Không. `canAccess` cần receiver instance phù hợp cho non-static method. Truyền object đúng kiểu, sau đó mới xem có thực sự thiếu quyền truy cập hay không.

**Câu 6.** Lớp trong same package nhưng không cùng nest gọi một private constructor qua `Constructor.newInstance` chưa được suppress. Ngoại lệ điển hình?

**Đáp án:** `IllegalAccessException` vì private constructor không truy cập được. Khả năng `trySetAccessible` thành công phụ thuộc quan hệ module/access runtime; không suy ra từ việc lookup thành công.

**Câu 7.** App chạy trên classpath có thể private-reflect vào lớp của chính mình, nhưng khi chuyển sang named modules thì bị chặn. Bước điều tra đầu tiên?

**Đáp án:** Kiểm tra declaring module/package, caller module, module descriptor và quyền `opens` tương ứng. Đừng tự động đổi tất cả fields thành public.

**Câu 8.** Có thể dùng `MethodHandles.privateLookupIn` để bỏ qua `opens` không?

**Đáp án:** Không. API này vẫn tuân theo quyền truy cập của JPMS và có thể ném `IllegalAccessException` nếu lookup không đủ điều kiện. Method Handles không phải cơ chế bypass module encapsulation.

## Tài liệu chuẩn

- Java SE 21, `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html — `canAccess`, `trySetAccessible`, `setAccessible` và điều kiện module.
- Java SE 21, `InaccessibleObjectException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html — loại exception khi không thể bật accessibility.
- Java SE 21, `IllegalAccessException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalAccessException.html — checked exception cho hành vi truy cập không hợp lệ.
- Java SE 21, `Module`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html — `isExported` và `isOpen`.
- Java SE 21, `Method`/`Field`/`Constructor`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html ; https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html ; https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html .
- Java Language Specification 21, §6.6 Access Control: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.6 .
- Java Platform Module System (JEP 261) và Strongly Encapsulate JDK Internals (JEP 403): https://openjdk.org/jeps/261 ; https://openjdk.org/jeps/403 .