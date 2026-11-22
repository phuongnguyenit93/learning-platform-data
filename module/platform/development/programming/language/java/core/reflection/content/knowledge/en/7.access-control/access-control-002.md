# Kiểm tra truy cập Java khi `get`, `set`, `invoke` hoặc `newInstance`

## 1. Tìm thấy member khác với có quyền sử dụng member

Reflection có hai công đoạn riêng:

1. **Tra cứu metadata**: `Class.getField`, `getMethod`, `getConstructor` lấy các public member thích hợp; `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor` lấy member khai báo trực tiếp tại kiểu đang xét, bất kể modifier.
2. **Thực hiện thao tác**: `Field.get`/`set`, `Method.invoke` và `Constructor.newInstance` phải thỏa điều kiện truy cập của caller theo Java và, nếu có, hệ thống module JPMS.

Vì vậy `SomeType.class.getDeclaredField("secret")` có thể trả về đối tượng `Field` cho một field private, nhưng `field.get(target)` hoặc `field.set(target, value)` vẫn có thể ném `IllegalAccessException`. Tương tự, lấy được metadata của method/constructor private không tự mở quyền thực thi chúng.

Cần phân biệt thêm:

- **Member được khai báo ở đâu**: `getDeclaringClass()` cho biết kiểu khai báo thực sự. Member public được thừa kế có thể xuất hiện qua `getMethods()` dù không hiện diện trong `getDeclaredMethods()` của lớp con.
- **Member có modifier gì**: `getModifiers()` kết hợp `Modifier.isPublic`, `isPrivate`… mô tả modifier nhưng không trả lời đầy đủ caller hiện tại có được dùng hay không.
- **Caller có thể truy cập lúc này không**: `canAccess(receiver)` kiểm tra quyền hiện tại trên reflection object (bao gồm trạng thái override); thao tác thực tế vẫn có thể có lỗi bổ sung.

## 2. Các thao tác áp dụng kiểm tra truy cập

| Reflection object | Thao tác | Điều kiện receiver | Nếu bị chặn truy cập |
| --- | --- | --- | --- |
| `Field` | `get`, `set`, cùng biến thể `getInt`, `setInt`, … | Instance thích hợp với field thường; `null` với field static | `IllegalAccessException` |
| `Method` | `invoke` | Instance thích hợp với method thường; `null` với method static | `IllegalAccessException` |
| `Constructor<T>` | `newInstance` | Không nhận receiver; constructor tạo object mới | `IllegalAccessException` |

Khi access-check override chưa được bật, Java sử dụng các quy tắc quyền truy cập ngôn ngữ (bao gồm khả năng truy cập **lớp khai báo** và bản thân member): `public`, `protected`, package-private, `private`, ngữ cảnh package, superclass/subclass và vị trí của caller. Với named module, còn phải xét package được `exports`/`opens` cho ai.

**Lưu ý:** API tra cứu metadata có thể ném `NoSuchFieldException` hoặc `NoSuchMethodException` nếu tên/signature không khớp; đó khác lỗi `IllegalAccessException` xảy ra khi dùng member đã tìm thấy. Các thao tác `get`/`set`/`invoke`/`newInstance` còn kiểm tra kiểu receiver, kiểu đối số, ràng buộc gán và các điều kiện chạy khác. Không gom tất cả lỗi vào “không có quyền”.

## 3. Ví dụ Java 17+ đầy đủ, kết quả xác định

Tạo một file `AccessCheckDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessCheckDemo {
    public static void main(String[] args) throws Exception {
        AccessTarget target = new AccessTarget();
        Class<AccessTarget> type = AccessTarget.class;

        Field publicField = type.getField("label");
        Field privateField = type.getDeclaredField("secret");
        Method privateMethod = type.getDeclaredMethod("reveal");
        Constructor<AccessTarget> privateConstructor =
                type.getDeclaredConstructor(String.class);

        System.out.println("public canAccess: " + publicField.canAccess(target));
        System.out.println("public get: " + publicField.get(target));

        System.out.println("private field canAccess: "
                + privateField.canAccess(target));
        try {
            privateField.get(target);
        } catch (IllegalAccessException e) {
            System.out.println("private get blocked: "
                    + e.getClass().getSimpleName());
        }

        try {
            privateField.set(target, "changed");
        } catch (IllegalAccessException e) {
            System.out.println("private set blocked: "
                    + e.getClass().getSimpleName());
        }

        try {
            privateMethod.invoke(target);
        } catch (IllegalAccessException e) {
            System.out.println("private invoke blocked: "
                    + e.getClass().getSimpleName());
        }

        try {
            privateConstructor.newInstance("from private ctor");
        } catch (IllegalAccessException e) {
            System.out.println("private ctor blocked: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("enable field: " + privateField.trySetAccessible());
        System.out.println("enable method: " + privateMethod.trySetAccessible());
        System.out.println("enable ctor: " + privateConstructor.trySetAccessible());

        privateField.set(target, "changed");
        System.out.println("private get after enable: "
                + privateField.get(target));
        System.out.println("private invoke after enable: "
                + privateMethod.invoke(target));
        System.out.println("ctor after enable: "
                + privateConstructor.newInstance("from private ctor").label);
    }
}

class AccessTarget {
    public String label = "visible";
    private String secret = "before";

    public AccessTarget() {
    }

    private AccessTarget(String value) {
        label = value;
        secret = "new-secret";
    }

    private String reveal() {
        return secret;
    }
}
~~~

Hai lớp là hai **top-level class** trong cùng package mặc định. Cách sắp xếp này có chủ đích: nếu đặt `AccessTarget` là nested class bên trong `AccessCheckDemo` thì quan hệ *nestmate* có thể làm phép truy cập private thành hợp lệ và không còn minh họa đúng tình huống bị chặn quyền.

Biên dịch và chạy:

~~~bash
javac --release 17 AccessCheckDemo.java
java AccessCheckDemo
~~~

Output trên classpath/unnamed module thông thường:

~~~text
public canAccess: true
public get: visible
private field canAccess: false
private get blocked: IllegalAccessException
private set blocked: IllegalAccessException
private invoke blocked: IllegalAccessException
private ctor blocked: IllegalAccessException
enable field: true
enable method: true
enable ctor: true
private get after enable: changed
private invoke after enable: changed
ctor after enable: from private ctor
~~~

### Đọc kết quả

- `label` là field `public`; code gọi nằm trong cùng package với top-level class `AccessTarget`. `canAccess(target)` trả `true` và `get(target)` đọc được giá trị.
- `secret` là field `private` của một top-level class khác. Dù `getDeclaredField` tìm được metadata, cả `get` và `set` đều ném `IllegalAccessException` trước khi thao tác.
- Method `reveal` và constructor nhận `String` cũng private. `getDeclaredMethod` và `getDeclaredConstructor` tìm được member, nhưng `invoke` và `newInstance` ban đầu bị chặn.
- Trong môi trường classpath của ví dụ, `trySetAccessible` bật override thành công cho từng reflection object. Sau đó `privateField.set`, `privateField.get`, `privateMethod.invoke` và `privateConstructor.newInstance` chạy được.
- Constructor private gán tham số cho `label`, nên đối tượng mới in ra `from private ctor`. Đối tượng `target` trước đó vẫn được dùng để đọc method `reveal()` sau khi field `secret` được đặt thành `changed`.

Lệnh `javac --release 17` trong ví dụ dùng cú pháp và API có từ Java 17. Kết quả bật override có thể khác ở ứng dụng named module vì ranh giới module.

## 4. Ngoại lệ: chặn truy cập hay lỗi thực thi?

| Exception / kết quả | Khi nào có thể xảy ra | Ý nghĩa thực tế |
| --- | --- | --- |
| `IllegalAccessException` | `get`, `set`, `invoke`, `Constructor.newInstance` khi caller không có quyền | Chưa được phép truy cập member; xem access modifier, declaring class, package và JPMS |
| `InaccessibleObjectException` | `setAccessible(true)` khi không thể bật override | Deep reflection bị ranh giới module ngăn |
| `trySetAccessible() == false` | Override không được cấp | Phải xử lý nhánh thất bại trước khi thao tác private member |
| `NoSuchFieldException` / `NoSuchMethodException` | Tra cứu sai tên, chữ ký hoặc phạm vi `getX`/`getDeclaredX` | Member không được tìm thấy; chưa phải kết quả access check tại thao tác |
| `IllegalArgumentException` | Receiver sai, kiểu/số đối số sai, giá trị gán không tương thích | Sửa receiver, parameter types và giá trị |
| `InvocationTargetException` | `Method.invoke` hoặc `Constructor.newInstance` gọi code đích và code đích ném exception | Lấy `getCause()` để phân biệt lỗi logic của method/constructor |
| `InstantiationException` | Constructor reflection yêu cầu tạo đối tượng của class không thể instantiate (ví dụ abstract class) | Loại class không thể tạo instance theo contract |
| Vấn đề `final field` | Field final có các ràng buộc ghi riêng, kể cả khi override được bật | Không dựa vào reflective write để thay đổi trạng thái bất biến |

`InvocationTargetException` không phải dấu hiệu thiếu quyền truy cập: thường method hoặc constructor **đã được gọi** và exception xuất phát từ thân code đích. Nếu gọi `Method.invoke` trên instance method, dispatch động vẫn có thể xảy ra theo quy tắc Java; dùng `getDeclaringClass()` không có nghĩa ép gọi implementation của lớp cha.

Với final field, cần phân biệt quyền đọc với quyền ghi. Một số final field như `static final`, field final của record và field final trong hidden class là **non-modifiable final fields**; `setAccessible(true)` có thể cho phép đọc nhưng không làm field thành writable. Ngay cả khi có cơ chế ghi các final field khác, việc phụ thuộc vào đó gây sai lệch bất biến/optimization và không nên dùng cho business logic.

## 5. Bài tự kiểm tra

**Câu 1.** Vì sao `getDeclaredField("secret")` trả object `Field` nhưng `get` bị `IllegalAccessException`? Vì `getDeclaredField` chỉ tra cứu metadata của field khai báo trực tiếp; `get` là thao tác sử dụng member và cần quyền truy cập.

**Câu 2.** `trySetAccessible()` trả `true` trong ví dụ nhưng `false` tại ứng dụng khác, có mâu thuẫn không? Không. Điều kiện package/module và caller khác nhau; unnamed module trên classpath và named module đóng gói có ranh giới khác nhau.

**Câu 3.** `Method.invoke` ném `InvocationTargetException`, có phải thiếu quyền không? Không nên kết luận như vậy. Kiểm tra `getCause()` để hiểu lỗi do method được gọi ném ra; thiếu quyền truy cập phản chiếu được biểu diễn bằng `IllegalAccessException`.

**Câu 4.** Vì sao bật `setAccessible(true)` chưa chắc cho phép sửa `static final`? Vì override chỉ tác động lên access check; `final` còn có ràng buộc riêng về quyền ghi và một số final field hoàn toàn không thể sửa qua Reflection.

Khi làm việc với Reflection, hãy xét độc lập **tìm member → kiểm tra quyền thực tế → thực hiện thao tác → xử lý lỗi của thao tác và code đích**; điều này tránh nhầm lỗi tra cứu, lỗi quyền truy cập, lỗi đối số và lỗi nghiệp vụ.