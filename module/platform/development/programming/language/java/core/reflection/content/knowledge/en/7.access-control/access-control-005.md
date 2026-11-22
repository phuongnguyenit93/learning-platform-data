# setAccessible khác trySetAccessible trong Java Reflection

## 1. Vì sao cần hai API này?

Trong Reflection, các đối tượng `Field`, `Method`, `Constructor` đều kế thừa `AccessibleObject`. Bình thường, khi đọc/ghi field, gọi method hoặc khởi tạo đối tượng qua những đối tượng này, JVM kiểm tra quy tắc truy cập Java (`public`, `protected`, package-private, `private`) và ranh giới module.

`setAccessible(true)` và `trySetAccessible()` cùng nhằm **yêu cầu bỏ qua việc kiểm tra quyền truy cập Java tại thời điểm sử dụng đối tượng Reflection** khi JVM cho phép. Khác biệt chính là **cách thông báo khi không thể bật quyền truy cập**:

- `setAccessible(true)`: không trả về giá trị; nếu JVM không cho phép bật quyền, thường ném `InaccessibleObjectException`.
- `trySetAccessible()`: trả về `true` nếu đã bật được (hoặc vốn đã bật), `false` nếu JVM không cho phép bật quyền vì giới hạn truy cập/module.
- Cả hai vẫn tuân thủ quy tắc bảo vệ của Java Platform Module System (JPMS); không có API nào tự vượt qua package không mở của một module khác.

Việc **tìm thấy thành viên** và việc **được phép sử dụng thành viên** là hai bước riêng biệt. Ví dụ `getDeclaredField("secret")` có thể trả về metadata của một field `private`, nhưng `field.get(object)` có thể ném `IllegalAccessException` nếu chưa được phép truy cập.

## 2. So sánh chính xác

| Tiêu chí | `setAccessible(true)` | `trySetAccessible()` |
| --- | --- | --- |
| Khai báo API | `void setAccessible(boolean flag)` | `boolean trySetAccessible()` |
| Giá trị trả về | Không có | `true` hoặc `false` |
| Khi có thể bật | Đặt cờ bỏ qua access check thành `true` | Đặt cờ thành `true`, trả `true` |
| Khi bị chặn bởi giới hạn module | Ném `InaccessibleObjectException` (unchecked) | Trả `false` |
| Khi đã bật từ trước | Gọi `true` tiếp vẫn cho phép | Trả `true` mà không cần bật lại |
| Khi muốn tắt cờ | `setAccessible(false)` | Không có tham số để tắt |
| Khả dụng | API cũ, có từ các phiên bản Java trước | Có từ Java 9 |
| Khi Security Manager cũ từ chối quyền | Có thể ném `SecurityException` | Có thể ném `SecurityException`, **không bảo đảm trả `false`** |

**Không nhầm `trySetAccessible()` với `canAccess(receiver)`:**

- `trySetAccessible()` **thử thay đổi** cờ cho đối tượng Reflection.
- `canAccess(receiver)` **kiểm tra hiện tại** liệu caller có thể sử dụng đối tượng Reflection với receiver phù hợp hay không; bản thân nó không bật quyền.
- `isAccessible()` đã deprecated từ Java 9 vì tên dễ gây hiểu lầm: nó phản ánh cờ override, không nhất thiết phản ánh việc caller thực sự truy cập được thành viên. Khi cần hỏi quyền truy cập hiện tại, ưu tiên `canAccess(...)`.

## 3. Cơ chế bên trong: cờ của đối tượng Reflection

Giả sử có field khai báo là `private String secret` trong lớp khác:

```text
getDeclaredField("secret")
    |
    v
Nhận metadata Field (chưa được tự động cấp quyền truy cập)
    |
    +--> field.get(instance) --> có thể IllegalAccessException
    |
    +--> field.trySetAccessible()
    |          |
    |          +--> true: dùng field.get(instance)
    |          +--> false: chọn cách truy cập khác / xử lý giới hạn
    |
    +--> field.setAccessible(true)
               |
               +--> thành công: dùng field.get(instance)
               +--> bị module chặn: InaccessibleObjectException
```

Cờ này gắn với **đối tượng `Field`/`Method`/`Constructor` đang dùng**; nó không sửa từ khóa `private` trong mã nguồn, không biến member thành `public` và không cấp quyền cho mọi nơi trong chương trình. Khi gọi `setAccessible(false)`, lần sử dụng sau lại tuân theo access check thông thường. Nếu một thành viên vốn có thể truy cập công khai, `canAccess(...)` vẫn có thể trả `true` dù cờ override đang là `false`.

## 4. Ví dụ đầy đủ: cả hai API đều thành công khi được phép

Lưu dưới tên `AccessibleDemo.java`. Hai lớp top-level được khai báo **trong cùng một tệp**; `Vault.secret` là `private` đối với `AccessibleDemo`.

```java
import java.lang.reflect.Field;

public class AccessibleDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Vault vault = new Vault("abc123");
        Field field = Vault.class.getDeclaredField("secret");

        System.out.println("Before: " + field.canAccess(vault));

        System.out.println("Try: " + field.trySetAccessible());
        System.out.println("After try: " + field.canAccess(vault));
        System.out.println("Read: " + field.get(vault));

        field.setAccessible(false);
        System.out.println("After reset: " + field.canAccess(vault));
        try {
            field.get(vault);
        } catch (IllegalAccessException e) {
            System.out.println("Read after reset: IllegalAccessException");
        }

        field.setAccessible(true);
        System.out.println("After set: " + field.canAccess(vault));
        System.out.println("Read again: " + field.get(vault));
    }
}

class Vault {
    private final String secret;

    Vault(String secret) {
        this.secret = secret;
    }
}
```

Biên dịch/chạy trên Java 17+ bằng classpath thông thường:

```bash
javac AccessibleDemo.java
java AccessibleDemo
```

Stdout:

```text
Before: false
Try: true
After try: true
Read: abc123
After reset: false
Read after reset: IllegalAccessException
After set: true
Read again: abc123
```

Giải thích:

1. `getDeclaredField` tìm được field `private`, nhưng chưa mở quyền; `canAccess(vault)` trả `false`.
2. `trySetAccessible()` trả `true` vì hai lớp ở cùng unnamed module khi chạy trên classpath; `field.get(vault)` đọc thành công.
3. `setAccessible(false)` bỏ cờ override; lần đọc tiếp theo ném `IllegalAccessException` như quy tắc truy cập Java.
4. `setAccessible(true)` bật lại quyền và không trả giá trị; `canAccess(vault)` xác nhận có thể đọc.
5. Field là `final` nhưng ở đây **chỉ đọc**, không thay đổi giá trị.

**Lưu ý receiver:** Với field/method instance, `canAccess(obj)` cần một đối tượng đúng kiểu khai báo hoặc kiểu con. Với field/method `static` và constructor, truyền `null` vào `canAccess(null)`. Truyền sai receiver có thể ném `IllegalArgumentException`.

## 5. Ví dụ khi JPMS không cho phép truy cập sâu

Từ Java 9, một **named module** có thể xuất khẩu package cho API công khai mà vẫn giữ kín các member nội bộ. Ví dụ, trong JDK 17+ mặc định, package `java.lang` của module `java.base` được export nhưng **không mở để truy cập sâu** cho ứng dụng trên classpath.

Lưu dưới tên `JdkModuleAccessDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class JdkModuleAccessDemo {
    public static void main(String[] args) throws NoSuchFieldException {
        Field field = String.class.getDeclaredField("value");

        System.out.println("trySetAccessible: " + field.trySetAccessible());

        try {
            field.setAccessible(true);
            System.out.println("setAccessible: enabled");
        } catch (InaccessibleObjectException e) {
            System.out.println("setAccessible: InaccessibleObjectException");
        }
    }
}
```

Chạy trong môi trường JDK 17+ thông thường, **không** thêm tùy chọn mở package và không có agent/cấu hình mở quyền khác:

```bash
javac JdkModuleAccessDemo.java
java JdkModuleAccessDemo
```

Stdout điển hình:

```text
trySetAccessible: false
setAccessible: InaccessibleObjectException
```

Cả hai API được gọi trên cùng một `Field`: lần thử đầu thất bại không tự mở quyền; lần gọi `setAccessible(true)` sau đó ném exception vì `java.base/java.lang` chưa được mở cho unnamed module.

Nếu **chủ động mở đúng package** khi khởi động để minh họa cơ chế (không phải cấu hình khuyến nghị cho ứng dụng sản xuất):

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED JdkModuleAccessDemo
```

Khi đó stdout trở thành:

```text
trySetAccessible: true
setAccessible: enabled
```

`--add-opens` tác động tới quyền mở package tại lúc khởi động JVM; bản thân `trySetAccessible()` không làm package được mở. Ví dụ dùng field nội bộ `String.value` **chỉ để quan sát access control**, không nên dựa vào cấu trúc riêng của JDK để viết logic ứng dụng.

## 6. Quy tắc module cần hiểu

| Quan hệ/thiết lập | Có thể bật Reflection để truy cập member `private`? |
| --- | --- |
| Caller và lớp khai báo ở cùng module | Thông thường có thể |
| Lớp ở unnamed module hoặc open module | Thông thường có thể, nếu không có ràng buộc bảo mật khác |
| Lớp ở named module khác, package chỉ được `exports` | **Không** đủ để truy cập sâu member `private` |
| Lớp ở named module khác, package được `opens` đến module caller | Có thể |
| Chạy với `--add-opens source.module/package=target.module` đúng đối tượng | Có thể theo phạm vi package đã mở |

`exports` chủ yếu phục vụ sử dụng API công khai từ module khác; `opens` cho phép truy cập Reflection sâu khi được cấp tới module caller. `--add-exports` riêng lẻ không thay thế `--add-opens` cho field `private`.

Một số trường hợp member `public` và lớp `public` trong package đã export cũng có thể được `setAccessible(true)` theo quy định API; không cần mở package cho **mọi** thao tác Reflection. Sự khác biệt quan trọng ở đây là quyền truy cập sâu tới member không công khai của module khác.

## 7. Chọn API phù hợp trong chương trình

Khi quyền truy cập sâu là **tùy chọn**, ưu tiên thử có điều kiện và có đường xử lý khi thất bại:

```java
// Giả sử field và instance đã được lấy đúng kiểu.
if (field.canAccess(instance) || field.trySetAccessible()) {
    Object value = field.get(instance);
    // Dùng value theo nghiệp vụ.
} else {
    // Không có quyền: dùng public API hoặc thông báo cấu hình module cần thiết.
}
```

Đây là **đoạn minh họa đặt trong phương thức xử lý**, không phải một chương trình độc lập. `field.get(instance)` vẫn có thể ném `IllegalAccessException` theo khai báo API; caller cần `throws` hoặc bắt exception đúng cách. Không dùng `trySetAccessible()` như cách che đi mọi lỗi bảo mật: nếu chương trình phụ thuộc bắt buộc vào field riêng tư, cần thông báo thiếu `opens` hoặc thiết kế lại giao diện công khai.

Khi quyền này là **bắt buộc** và muốn thất bại sớm, có thể dùng:

```java
// Minh họa trong ngữ cảnh đã có biến Field field.
field.setAccessible(true); // Có thể ném InaccessibleObjectException.
```

Nếu cần xử lý thất bại có chủ đích, bắt `InaccessibleObjectException` và cung cấp thông báo cấu hình cụ thể; không nuốt exception rồi tiếp tục truy cập như thể thành công.

## 8. Lỗi thường gặp

| Lỗi hoặc ngộ nhận | Điều thực tế xảy ra | Hướng xử lý |
| --- | --- | --- |
| Nghĩ `trySetAccessible()` chỉ kiểm tra, không đổi trạng thái | Nó **thử bật** cờ `accessible` thành `true` | Dùng `canAccess(...)` nếu chỉ cần kiểm tra |
| Nghĩ `trySetAccessible()` không bao giờ ném exception | Với Security Manager có hiệu lực trên một số JDK cũ, vẫn có thể ném `SecurityException` | Phân biệt từ chối module (`false`) với từ chối bảo mật (exception) |
| Bắt `IllegalAccessException` quanh `setAccessible(true)` | Khi bị JPMS chặn ở bước bật quyền, ngoại lệ là `InaccessibleObjectException` | Bắt ngoại lệ ở đúng giai đoạn |
| `getDeclaredField` thành công nên nghĩ `get` luôn thành công | Metadata tồn tại không đồng nghĩa có quyền sử dụng | Kiểm tra `canAccess`, bật quyền khi được phép |
| Package đã `exports` mà field `private` vẫn bị chặn | `exports` không đồng nghĩa với `opens` | Ưu tiên public API; nếu thật sự cần deep reflection, cấu hình `opens` rõ phạm vi |
| Gọi `canAccess(null)` cho field instance | Receiver sai, gây `IllegalArgumentException` | Truyền instance thuộc kiểu khai báo |
| Dùng `isAccessible()` để kết luận member gọi được | API deprecated, chỉ phản ánh cờ override | Dùng `canAccess(receiver)` |
| Nghĩ `setAccessible(true)` cho phép sửa mọi `final` field | Không thể bật quyền ghi với những final field không thể sửa như `static final`, final field của record hoặc hidden class | Không phụ thuộc vào việc sửa các field này |

Không khuyến khích mở rộng hàng loạt package nội bộ JDK chỉ để làm cho Reflection chạy được. Framework cần truy cập sâu thường nên có cơ chế cấu hình `opens` chính xác hoặc sử dụng API công khai và các hợp đồng mở rộng phù hợp.

## 9. Câu hỏi tự kiểm tra

1. Nếu `trySetAccessible()` trả `true`, lời gọi có làm thay đổi từ khóa `private` của member không? **Không**; chỉ thay đổi cờ trên đối tượng Reflection.
2. Vì sao `trySetAccessible()` có thể trả `false` trong khi `getDeclaredField` vẫn tìm thấy field? Vì tra cứu metadata khác với quyền truy cập sâu.
3. `setAccessible(false)` có luôn khiến `canAccess(...)` thành `false` không? **Không**; member `public` đang truy cập hợp lệ vẫn có thể đọc/gọi được.
4. Với named module khác không mở package, nên xử lý thế nào? Ưu tiên API công khai hoặc yêu cầu module chủ sở hữu mở chính xác package cần thiết; `trySetAccessible()` không tự vượt giới hạn module.

**Ghi nhớ:** `setAccessible(true)` phù hợp khi muốn yêu cầu bật quyền và xử lý **exception** nếu không thể; `trySetAccessible()` phù hợp khi muốn **thử bật quyền với kết quả boolean** để rẽ nhánh. Cả hai cùng chịu ràng buộc truy cập/module của JVM.

Tham khảo API chính thức: [`java.lang.reflect.AccessibleObject` trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html).