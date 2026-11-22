# canAccess, trySetAccessible và xử lý truy cập bị từ chối trong Java 17

Reflection cho phép chương trình khám phá class, field, method và constructor khi chạy. Tuy nhiên, việc tìm thấy một thành viên bằng `getDeclaredField()` hoặc `getDeclaredMethod()` không có nghĩa chương trình được phép đọc hoặc gọi thành viên đó. Java vẫn áp dụng quy tắc truy cập như `private`, `protected`, package-private, `public` và các ranh giới module.

Từ Java 9, `AccessibleObject` cung cấp `canAccess(Object)` và `trySetAccessible()` để kiểm tra quyền truy cập và thử bật chế độ bỏ qua kiểm tra truy cập. Đây là các API hiện hành trong Java 17. Chúng đặc biệt quan trọng khi ứng dụng chạy với Java Platform Module System (JPMS), vì một package có thể không được mở cho deep reflection dù class hoặc member đã được tìm thấy.

Bài học tập trung vào cách dùng đúng ba API `canAccess`, `trySetAccessible`, `setAccessible`, cách chọn đối tượng receiver, cách hiểu `false` và exception, sự khác nhau giữa `exports` và `opens`, cũng như cách xử lý khi module từ chối truy cập.

## 1. Tìm thấy member không đồng nghĩa với được truy cập

Reflection có hai nhóm thao tác cần phân biệt:

- **Khám phá metadata:** lấy `Class`, `Field`, `Method`, `Constructor`, modifier, annotation và kiểu dữ liệu.
- **Thực thi hoặc đọc/ghi:** gọi method, tạo object, đọc field hoặc thay đổi field.

Ví dụ:

~~~java
import java.lang.reflect.Field;

class Account {
    private String owner = "Lan";
}

public class ReflectionLookupDemo {
    public static void main(String[] args) throws Exception {
        Field ownerField = Account.class.getDeclaredField("owner");
        System.out.println(ownerField.getName()); // owner
    }
}
~~~

`getDeclaredField("owner")` tìm được field private. Nhưng nếu đọc trực tiếp:

~~~java
Account account = new Account();
Field ownerField = Account.class.getDeclaredField("owner");

Object value = ownerField.get(account); // IllegalAccessException
~~~

thì lời gọi có thể bị từ chối vì code gọi reflection không có quyền truy cập private member của `Account`.

Các API `canAccess` và `trySetAccessible` giúp chương trình xử lý tình huống này có chủ đích thay vì mặc định rằng reflection luôn vượt qua mọi giới hạn.

## 2. AccessibleObject và cờ override access checks

`Field`, `Method` và `Constructor` kế thừa `java.lang.reflect.AccessibleObject`. Lớp cơ sở này cung cấp các phương thức quản lý kiểm tra truy cập:

| API | Ý nghĩa |
| --- | --- |
| `canAccess(Object obj)` | Kiểm tra caller hiện tại có thể truy cập member trên receiver đã cho hay không, theo quy tắc truy cập Java và trạng thái override hiện tại. |
| `trySetAccessible()` | Thử bật cờ bỏ qua kiểm tra truy cập; trả `true` nếu thành công, `false` nếu không thể. |
| `setAccessible(boolean flag)` | Đặt cờ override; khi yêu cầu bật nhưng không được phép, có thể ném `InaccessibleObjectException` hoặc `SecurityException`. |
| `isAccessible()` | API cũ kiểm tra trạng thái cờ override, đã deprecated từ Java 9. Không dùng nó thay cho `canAccess`. |

`canAccess` không tự thay đổi quyền truy cập. `trySetAccessible` mới là thao tác yêu cầu bật chế độ override.

### 2.1. Phân biệt canAccess và isAccessible

Tên hai phương thức khá dễ gây nhầm:

- `canAccess(obj)` trả lời câu hỏi: **caller có thể truy cập member này trên receiver đó không?**
- `isAccessible()` trả lời câu hỏi cũ: **cờ override access checks trên reflection object đang bật hay chưa?**

`isAccessible()` không kiểm tra đầy đủ quy tắc Java access control. Một member có thể truy cập được theo quy tắc thông thường dù cờ override đang tắt; khi đó `isAccessible()` trả `false` nhưng `canAccess(...)` có thể trả `true`.

Từ Java 9, hãy dùng `canAccess` khi cần kiểm tra khả năng truy cập. `isAccessible()` được giữ lại để tương thích nhưng đã deprecated.

## 3. Dùng canAccess đúng với receiver

Chữ ký:

~~~java
boolean canAccess(Object obj)
~~~

Giá trị `obj` phụ thuộc loại member:

| Member được kiểm tra | Giá trị `obj` |
| --- | --- |
| Instance field | Object mà field được đọc/ghi trên đó |
| Instance method | Object mà method được gọi trên đó |
| Static field | `null` |
| Static method | `null` |
| Constructor | `null` |

Với instance member, object truyền vào phải là instance của class khai báo member hoặc subclass phù hợp. Truyền `null` cho instance member, hoặc truyền object sai kiểu, có thể làm `canAccess` ném `IllegalArgumentException`; phương thức không đơn giản trả `false` trong mọi trường hợp sai receiver.

### 3.1. Kiểm tra instance field

~~~java
import java.lang.reflect.Field;

class UserProfile {
    private String email = "lan@example.test";
}

public class CanAccessFieldDemo {
    public static void main(String[] args) throws Exception {
        UserProfile profile = new UserProfile();
        Field email = UserProfile.class.getDeclaredField("email");

        System.out.println(email.canAccess(profile));
    }
}
~~~

Nếu caller nằm ngoài class khai báo và field là private, kết quả thường là `false` khi override chưa được bật.

### 3.2. Kiểm tra static field

~~~java
import java.lang.reflect.Field;

class AppConfig {
    private static String secret = "internal";
}

public class CanAccessStaticDemo {
    public static void main(String[] args) throws Exception {
        Field secret = AppConfig.class.getDeclaredField("secret");

        boolean accessible = secret.canAccess(null);
        System.out.println(accessible);
    }
}
~~~

Với static field, truyền `null`; không truyền một instance của `AppConfig`.

### 3.3. Kiểm tra method và constructor

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

class Worker {
    private Worker() {
    }

    private void execute() {
    }

    private static void reset() {
    }
}

public class CanAccessExecutableDemo {
    public static void main(String[] args) throws Exception {
        Method execute = Worker.class.getDeclaredMethod("execute");
        Method reset = Worker.class.getDeclaredMethod("reset");
        Constructor<Worker> constructor =
                Worker.class.getDeclaredConstructor();

        Worker instance = createForDemo();

        System.out.println(execute.canAccess(instance));
        System.out.println(reset.canAccess(null));
        System.out.println(constructor.canAccess(null));
    }

    private static Worker createForDemo() throws Exception {
        Constructor<Worker> constructor =
                Worker.class.getDeclaredConstructor();
        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException("Cannot access constructor");
        }
        try {
            return constructor.newInstance();
        } finally {
            constructor.setAccessible(false);
        }
    }
}
~~~

Ví dụ minh họa quy tắc receiver. Trong code thực tế, không nên bật quyền truy cập constructor chỉ để tạo object nếu constructor public hoặc factory method đã đáp ứng nhu cầu.

## 4. trySetAccessible: thử bật quyền truy cập reflection

`trySetAccessible()` cố gắng bật cờ override access checks cho reflection object. Nếu thành công, các thao tác phản chiếu tiếp theo có thể truy cập member vượt qua kiểm tra ngôn ngữ Java thông thường.

~~~java
boolean enabled = field.trySetAccessible();
if (enabled) {
    // Có thể thử đọc field theo reflection.
} else {
    // Runtime/module không cho phép bật override.
}
~~~

Khác với `setAccessible(true)`, `trySetAccessible()` biểu diễn trường hợp không được phép bằng giá trị `false` thay vì ném `InaccessibleObjectException` cho việc không thể mở quyền do ranh giới module.

Phương thức vẫn có thể ném `SecurityException` nếu Security Manager đang được cấu hình và từ chối quyền `ReflectPermission("suppressAccessChecks")`. Security Manager đã bị deprecated để loại bỏ từ Java 17; ứng dụng mới không nên dựa vào nó như cơ chế bảo vệ chính.

### 4.1. Ví dụ đọc private field

~~~java
import java.lang.reflect.Field;

class Customer {
    private final String name;

    Customer(String name) {
        this.name = name;
    }
}

public class TrySetAccessibleDemo {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("Nguyen An");
        Field nameField = Customer.class.getDeclaredField("name");

        if (!nameField.canAccess(customer)) {
            if (!nameField.trySetAccessible()) {
                throw new IllegalStateException(
                        "Runtime does not allow access to Customer.name");
            }
        }

        try {
            Object value = nameField.get(customer);
            System.out.println(value);
        } finally {
            nameField.setAccessible(false);
        }
    }
}
~~~

Trong ví dụ classpath đơn giản, package của ứng dụng thuộc unnamed module. Các package trong unnamed module được mở cho deep reflection, vì vậy `trySetAccessible()` thường thành công. Với named module, kết quả còn phụ thuộc package có được mở cho module của caller hay không.

`trySetAccessible()` không làm member trở thành `public`, không sửa modifier trong bytecode và không cấp quyền truy cập toàn cục cho mọi đoạn code. Nó đặt trạng thái override trên reflection object cụ thể mà chương trình đang giữ.

### 4.2. Không bật override nếu không cần

Nếu `canAccess` đã trả `true`, thao tác reflection có thể thực hiện theo quyền truy cập hiện tại. Không cần gọi `trySetAccessible()` chỉ vì muốn “chắc chắn”.

Mẫu xử lý tốt:

1. Tìm member.
2. Xác định đúng receiver.
3. Kiểm tra `canAccess`.
4. Chỉ khi cần deep reflection và có lý do hợp lệ mới gọi `trySetAccessible`.
5. Nếu trả `false`, xử lý theo chính sách ứng dụng.
6. Thực hiện thao tác và đóng phạm vi override bằng cách đặt lại `false` khi phù hợp.

Không nên gọi `setAccessible(true)` hàng loạt cho mọi field hoặc method của một class. Cách đó làm code phụ thuộc mạnh vào chi tiết nội bộ và dễ bị chặn bởi module.

## 5. setAccessible(true) và trySetAccessible khác nhau thế nào?

Hai phương thức đều liên quan đến việc bật override access checks, nhưng cách báo thất bại khác nhau:

| Tình huống | `trySetAccessible()` | `setAccessible(true)` |
| --- | --- | --- |
| Có thể bật override | Trả `true` | Hoàn tất bình thường |
| Không thể do package của named module không mở | Trả `false` | Ném `InaccessibleObjectException` |
| Security Manager từ chối `suppressAccessChecks` | Có thể ném `SecurityException` | Có thể ném `SecurityException` |
| Caller không cần override | Có thể bỏ qua | Không nên gọi |

`trySetAccessible()` phù hợp hơn khi ứng dụng cần xử lý có kiểm soát khả năng mở quyền. `setAccessible(true)` vẫn tồn tại trong Java 17 và có thể cần cho code tương thích cũ, nhưng nó không giúp vượt qua giới hạn module.

### 5.1. setAccessible(false) để tắt override

Sau khi hoàn thành thao tác, có thể khôi phục trạng thái:

~~~java
if (!field.trySetAccessible()) {
    throw new IllegalStateException("Access denied");
}

try {
    Object value = field.get(target);
    use(value);
} finally {
    field.setAccessible(false);
}
~~~

`setAccessible(false)` không yêu cầu mở package để khôi phục kiểm tra truy cập. Cách này giúp phạm vi code sử dụng quyền override ngắn và dễ đọc hơn.

Tuy nhiên, không nên giả định rằng việc đặt lại cờ làm mọi dữ liệu đã đọc trở nên an toàn. Nếu đã lấy được một giá trị nhạy cảm, ứng dụng vẫn phải bảo vệ giá trị đó theo chính sách riêng.

## 6. Module system: vì sao reflection có thể bị từ chối?

Từ Java 9, ứng dụng có thể chạy trong Java Platform Module System (JPMS). Module khai báo package nào được export cho module khác và package nào được open để reflection sâu.

Hai khái niệm quan trọng:

- `exports`: cho phép module khác truy cập các kiểu và thành viên `public` của package theo quy tắc Java access control.
- `opens`: cho phép deep reflection vào package, bao gồm truy cập các thành viên không public khi caller dùng reflection và đáp ứng các điều kiện khác.

`exports` không đồng nghĩa với `opens`. Một package được export có thể cho phép code khác gọi API public nhưng vẫn không cho phép reflection bật quyền truy cập private field.

### 6.1. Ví dụ module chỉ export API công khai

Giả sử module `com.example.model`:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

Package `com.example.model.api` cung cấp API công khai cho module khác. Một package nội bộ như `com.example.model.internal` không được export và cũng không được open.

Module khác có thể sử dụng các kiểu public được export, nhưng không thể mặc định dùng deep reflection để đọc private field trong package nội bộ.

### 6.2. Mở package có chọn lọc bằng opens

Nếu một framework hoặc module được phép cần deep reflection vào package cụ thể, module có thể khai báo:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.reflector;
}
~~~

Ở đây:

- `com.example.model.api` được export cho truy cập API thông thường.
- `com.example.model.internal` được mở cho deep reflection của module `com.example.reflector`.
- Module khác không tự động nhận quyền deep reflection chỉ vì package đã mở có giới hạn cho một module cụ thể.

Module đích cần đọc module nguồn theo cấu hình module tương ứng, ví dụ khai báo `requires com.example.model;`.

### 6.3. Mở toàn bộ module

Một module có thể khai báo dạng `open module` để mở tất cả package của nó cho deep reflection. Cách này rộng hơn `opens package to module` và làm tăng phạm vi truy cập nội bộ.

Chỉ nên chọn khi thiết kế module thực sự yêu cầu mọi package được mở. Với ứng dụng mới, ưu tiên mở đúng package và đúng module cần thiết.

## 7. Dùng --add-opens khi không thể sửa module nguồn

Trong môi trường chạy, có thể mở package bằng tùy chọn JVM `--add-opens`:

~~~bash
java --add-opens com.example.model/com.example.model.internal=com.example.reflector \
     -m com.example.reflector/com.example.reflector.Main
~~~

Cú pháp tổng quát:

~~~text
--add-opens source.module/package=target.module
~~~

Nếu caller nằm trên classpath (unnamed module), target thường là `ALL-UNNAMED`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Ví dụ cuối mở package `java.lang` của module `java.base` cho mọi code trên classpath. Đây là quyền khá rộng đối với package lõi của JDK; chỉ dùng khi một dependency thực sự cần và có kế hoạch loại bỏ cấu hình tương thích đó.

Không nên thêm `--add-opens` một cách tùy tiện chỉ để làm hết lỗi. Hãy xác định module nguồn, package, module đích và lý do framework cần deep reflection. Mở package rộng có thể che giấu việc ứng dụng đang phụ thuộc vào implementation nội bộ của thư viện hoặc JDK.

### 7.1. Phân biệt --add-opens và --add-exports

| Tùy chọn | Mục tiêu |
| --- | --- |
| `--add-exports source.module/package=target.module` | Cho phép truy cập thông thường đến các kiểu public trong package chưa export cho module đích. |
| `--add-opens source.module/package=target.module` | Cho phép deep reflection vào package đối với module đích. |

Nếu lỗi là `IllegalAccessError` khi code liên kết tới một kiểu public trong package chưa export, `--add-exports` có thể liên quan. Nếu `trySetAccessible()` trả `false` hoặc `setAccessible(true)` ném `InaccessibleObjectException` do package không open, cần xem `opens` hoặc `--add-opens`.

Không dùng `--add-exports` để kỳ vọng đọc private field bằng deep reflection; hai tùy chọn giải quyết hai loại truy cập khác nhau.

## 8. Xử lý các kết quả từ chối truy cập

Khi reflection bị từ chối, trước hết cần phân loại đúng nguyên nhân:

| Kết quả/exception | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `canAccess(obj)` trả `false` | Caller hiện tại chưa có quyền truy cập member theo trạng thái hiện tại | Xác định có thật sự cần deep reflection hay không. |
| `trySetAccessible()` trả `false` | Không thể bật override, thường do ranh giới module/package chưa open | Mở package có chọn lọc nếu có quyền thay đổi cấu hình; nếu không, dùng API công khai. |
| `InaccessibleObjectException` | `setAccessible(true)` không thể bật override do giới hạn truy cập, thường liên quan module | Kiểm tra module/package và dùng `opens`/`--add-opens` chỉ khi cần thiết. |
| `IllegalAccessException` | Thao tác `Field.get`, `Method.invoke`, constructor hoặc API reflection không được phép truy cập | Kiểm tra receiver, trạng thái override và quyền truy cập. |
| `IllegalArgumentException` từ `canAccess` | Receiver không đúng loại, ví dụ truyền `null` cho instance field | Truyền đúng object; static member và constructor dùng `null`. |
| `SecurityException` | Chính sách Security Manager hoặc cơ chế bảo mật runtime từ chối thao tác | Kiểm tra policy/provider/runtime; không tự động thử đường vòng. |

### 8.1. Mẫu xử lý trySetAccessible trả false

~~~java
Field field = targetClass.getDeclaredField("internalState");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Cannot inspect internalState: package is not open to this module");
}

try {
    Object value = field.get(target);
    inspect(value);
} finally {
    field.setAccessible(false);
}
~~~

Thông báo lỗi nên chỉ rõ member và nguyên nhân đã biết. Không nên bắt mọi exception rồi trả về `null`, vì caller sẽ không phân biệt được “field thật sự có giá trị null” với “không thể truy cập field”.

### 8.2. Không nuốt InaccessibleObjectException

Ví dụ xử lý không tốt:

~~~java
try {
    field.setAccessible(true);
} catch (RuntimeException ignored) {
    // Tiếp tục như thể field đã được mở.
}
~~~

Nếu thao tác đọc tiếp theo thất bại, lỗi thực tế bị đẩy xa khỏi nguyên nhân ban đầu. Hãy bắt đúng exception nếu cần bổ sung ngữ cảnh, rồi truyền tiếp hoặc chuyển thành lỗi cấu hình rõ ràng.

~~~java
try {
    field.setAccessible(true);
} catch (java.lang.reflect.InaccessibleObjectException e) {
    throw new IllegalStateException(
            "The target module must open this package for deep reflection",
            e);
}
~~~

Với code mới, `trySetAccessible()` thường giúp biểu diễn trường hợp không mở được bằng một nhánh `false` dễ xử lý hơn.

## 9. Ví dụ đầy đủ: đọc private field có xử lý từ chối truy cập

Ví dụ sau tách việc tìm field, kiểm tra receiver, thử mở quyền và đọc giá trị:

~~~java
import java.lang.reflect.Field;
import java.util.Objects;

class PaymentRecord {
    private final String reference;

    PaymentRecord(String reference) {
        this.reference = reference;
    }
}

public class SafeReflectionRead {
    static Object readField(Object target, String fieldName)
            throws ReflectiveOperationException {
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(fieldName, "fieldName");

        Field field = target.getClass().getDeclaredField(fieldName);

        if (!field.canAccess(target) && !field.trySetAccessible()) {
            throw new IllegalStateException(
                    "Deep reflection is not permitted for "
                            + field.getDeclaringClass().getName()
                            + "." + fieldName);
        }

        try {
            return field.get(target);
        } finally {
            field.setAccessible(false);
        }
    }

    public static void main(String[] args) throws Exception {
        PaymentRecord record = new PaymentRecord("PAY-2026-001");
        System.out.println(readField(record, "reference"));
    }
}
~~~

Trong ví dụ này, class và caller nằm trên classpath trong cùng unnamed module. Với named module, `trySetAccessible()` có thể trả `false` nếu package chứa `PaymentRecord` không mở cho module của `SafeReflectionRead`.

Một số lưu ý khi đưa mẫu này vào ứng dụng:

- `getDeclaredField` chỉ tìm field được khai báo trên class cụ thể, không tự tìm field private ở superclass.
- Nếu cần tìm cả hierarchy, phải duyệt superclass một cách có chủ đích.
- Nếu field là static, dùng `field.canAccess(null)` và `field.get(null)`.
- Nếu field không tồn tại, `getDeclaredField` ném `NoSuchFieldException`.
- Không nên dùng reflection để đọc dữ liệu nội bộ nếu class đã có getter hoặc API phù hợp.

## 10. Reflection với method: invoke sau khi mở quyền

Quy tắc tương tự áp dụng cho `Method`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

class ReportGenerator {
    private String buildInternalReport(String code) {
        return "Report: " + code;
    }
}

public class InvokePrivateMethodDemo {
    public static void main(String[] args) throws Exception {
        ReportGenerator generator = new ReportGenerator();
        Method method = ReportGenerator.class.getDeclaredMethod(
                "buildInternalReport", String.class);

        if (!method.canAccess(generator)
                && !method.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access buildInternalReport");
        }

        try {
            Object result = method.invoke(generator, "R-17");
            System.out.println(result);
        } catch (InvocationTargetException e) {
            // Method được gọi đã ném exception.
            Throwable cause = e.getCause();
            throw new IllegalStateException(
                    "Target method failed", cause);
        } finally {
            method.setAccessible(false);
        }
    }
}
~~~

`Method.invoke` có thể ném `IllegalAccessException` nếu quyền truy cập không đủ. Nếu method đích ném exception, reflection bọc lỗi đó trong `InvocationTargetException`; hãy kiểm tra `getCause()` để xử lý nguyên nhân thật.

Không nhầm exception do truy cập bị từ chối với exception do code bên trong method được gọi.

## 11. Reflection với constructor

Constructor cũng kế thừa `AccessibleObject`. Khi kiểm tra bằng `canAccess`, truyền `null`:

~~~java
import java.lang.reflect.Constructor;

class InternalClient {
    private InternalClient(String endpoint) {
        System.out.println(endpoint);
    }
}

public class PrivateConstructorDemo {
    public static void main(String[] args) throws Exception {
        Constructor<InternalClient> constructor =
                InternalClient.class.getDeclaredConstructor(String.class);

        if (!constructor.canAccess(null)
                && !constructor.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access InternalClient constructor");
        }

        try {
            InternalClient client =
                    constructor.newInstance("https://example.test");
        } finally {
            constructor.setAccessible(false);
        }
    }
}
~~~

`Constructor.newInstance` có thể ném `IllegalAccessException`, `InstantiationException`, `IllegalArgumentException` hoặc `InvocationTargetException`. Nếu constructor đích ném exception, nguyên nhân được bọc trong `InvocationTargetException`.

Nếu class cung cấp factory method public, hãy ưu tiên factory thay vì cố gọi private constructor.

## 12. Kế thừa và member được khai báo ở superclass

`getDeclaredField` và `getDeclaredMethod` chỉ trả member được khai báo trực tiếp trên class được hỏi. `getField` và `getMethod` tìm các member public phù hợp, bao gồm một số member kế thừa theo quy tắc API.

Khi xử lý hierarchy:

~~~java
Class<?> type = target.getClass();
while (type != null) {
    try {
        Field field = type.getDeclaredField("id");
        // Kiểm tra quyền trên field được khai báo tại type.
        break;
    } catch (NoSuchFieldException ignored) {
        type = type.getSuperclass();
    }
}
~~~

Nếu tìm thấy field ở superclass, receiver vẫn là object thực tế `target`, miễn object đó là instance phù hợp với class khai báo field. Module cần mở là module chứa package khai báo member, không chỉ package của subclass.

Với protected member, quy tắc truy cập Java còn phụ thuộc quan hệ subclass, package và caller. Không suy ra quyền truy cập chỉ từ việc object là subclass; dùng `canAccess` với receiver đúng và xử lý kết quả.

## 13. Các lựa chọn thay thế deep reflection

Deep reflection làm code phụ thuộc vào chi tiết triển khai. Trước khi gọi `trySetAccessible`, cân nhắc:

1. **Public API hoặc getter/setter:** dùng hợp đồng mà class chủ động công bố.
2. **Constructor/factory method:** tạo object qua điểm mở rộng được thiết kế.
3. **Interface hoặc service provider:** phụ thuộc abstraction thay vì field nội bộ.
4. **Serialization hoặc mapping API chính thức:** dùng thư viện có hợp đồng module rõ ràng.
5. **MethodHandles:** trong một số trường hợp nâng cao, `MethodHandles.Lookup` và quyền lookup phù hợp có thể biểu diễn truy cập method/field theo cơ chế được thiết kế rõ ràng.

`MethodHandles.privateLookupIn` cũng chịu quy tắc module; nó không phải đường vòng để vượt qua package không open. Cách tiếp cận đúng là thiết kế API/module sao cho thành phần cần tương tác được cấp đúng quyền.

## 14. Lưu ý về bảo mật và tương thích Java 17

- Không mở package JDK nội bộ chỉ để tránh sửa code phụ thuộc implementation private.
- Không bật override cho toàn bộ member nếu chỉ cần một field hoặc method cụ thể.
- Không log giá trị private có thể chứa password, token, khóa hoặc dữ liệu cá nhân.
- Không coi `trySetAccessible() == true` là bằng chứng thao tác đó an toàn về nghiệp vụ; nó chỉ cho biết runtime cho phép bỏ qua access checks.
- Không dựa vào `isAccessible()` để kiểm tra caller có quyền truy cập.
- Không dùng Security Manager như nền tảng bảo mật mới; Security Manager đã deprecated for removal trong Java 17.
- Không dựa vào các cờ `--illegal-access` cũ của những JDK trước; cơ chế tương thích đó không còn là cách giải quyết hiện hành trên Java 17.
- Nếu một thư viện cần deep reflection, dùng phiên bản thư viện tương thích Java 17 và đọc hướng dẫn module của chính thư viện đó.

## 15. Bảng chọn API theo tình huống

| Nhu cầu | API/cách làm |
| --- | --- |
| Kiểm tra caller có thể đọc instance field không | `field.canAccess(target)` |
| Kiểm tra static field | `field.canAccess(null)` |
| Kiểm tra method instance | `method.canAccess(target)` |
| Kiểm tra static method hoặc constructor | `canAccess(null)` |
| Thử mở private member và xử lý thất bại bằng boolean | `trySetAccessible()` |
| Dùng API cũ yêu cầu bật override và chấp nhận exception | `setAccessible(true)` |
| Package của named module cần cho phép deep reflection | `opens package to caller.module` |
| Chỉ cấu hình runtime, không sửa module nguồn | `--add-opens source.module/package=target.module` |
| Cần truy cập public API từ package chưa export | `exports` hoặc `--add-exports` phù hợp |
| Chỉ cần dùng dữ liệu qua hợp đồng công khai | Getter, method hoặc API public; tránh deep reflection |

## 16. Câu hỏi tự kiểm tra

**1. Tìm thấy private field bằng `getDeclaredField` có nghĩa là đọc được field không?**  
Không. Việc tìm metadata và việc đọc giá trị là hai bước khác nhau; access checks vẫn được áp dụng.

**2. `canAccess` có tự bật quyền truy cập không?**  
Không. Nó chỉ kiểm tra khả năng truy cập trên receiver đã cho.

**3. Khi gọi `canAccess` cho instance field, truyền gì?**  
Truyền object mà field được truy cập trên đó; object phải có kiểu phù hợp với class khai báo field.

**4. Khi gọi `canAccess` cho static method hoặc constructor, truyền gì?**  
Truyền `null`.

**5. `trySetAccessible()` trả `false` trong trường hợp nào?**  
Khi runtime không cho phép bật override access checks, thường do package của named module không được mở cho module caller.

**6. Khác biệt chính giữa `trySetAccessible()` và `setAccessible(true)` là gì?**  
`trySetAccessible()` trả `false` nếu không thể mở quyền do giới hạn module; `setAccessible(true)` có thể ném `InaccessibleObjectException`.

**7. `isAccessible()` có thay thế được `canAccess()` không?**  
Không. `isAccessible()` chỉ phản ánh cờ override cũ và đã deprecated; `canAccess()` kiểm tra khả năng truy cập thực tế.

**8. `exports` có cho phép đọc private field qua deep reflection không?**  
Không. `exports` cho truy cập API public; deep reflection cần package được mở bằng `opens`.

**9. Dùng `--add-opens` để làm gì?**  
Mở một package của module nguồn cho module đích thực hiện deep reflection tại runtime.

**10. Vì sao không nên mở toàn bộ package JDK chỉ để làm hết lỗi reflection?**  
Vì nó mở rộng quyền truy cập nội bộ, tạo phụ thuộc vào implementation và có thể che giấu vấn đề tương thích của thư viện.

**11. Nếu `Method.invoke` ném `InvocationTargetException`, lỗi nằm ở đâu?**  
Method đích đã ném exception; xem `getCause()` để lấy nguyên nhân.

**12. Khi nào nên tránh `trySetAccessible`?**  
Khi đã có public API, getter, factory hoặc abstraction chính thức đáp ứng nhu cầu.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, `setAccessible` và trạng thái override.
- [Java SE 17 API — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): đọc/ghi field bằng reflection.
- [Java SE 17 API — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): gọi method bằng reflection.
- [Java SE 17 API — Constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): tạo object bằng constructor reflection.
- [Java SE 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): lỗi khi không thể bật override access checks.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module, exports, opens và tùy chọn runtime liên quan.
- [Java SE 17 Documentation — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn `--add-opens` và `--add-exports`.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): trạng thái Security Manager từ Java 17.
