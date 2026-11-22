# AccessibleObject và trạng thái bỏ qua kiểm tra truy cập trong Java Reflection

Reflection cho phép tìm `Field`, `Method` và `Constructor` ngay cả khi thành viên không phải `public`. Tuy nhiên, **tìm thấy metadata không đồng nghĩa được phép đọc trường, gọi phương thức hay tạo đối tượng**. `java.lang.reflect.AccessibleObject` là lớp cha của ba loại đối tượng Reflection trên, cung cấp API kiểm tra quyền truy cập và, khi được phép, bật trạng thái **bỏ qua kiểm tra truy cập của ngôn ngữ Java** (suppress access checks).

Chủ đề này thuộc nhóm **Quyền truy cập**. Mục tiêu là hiểu chính xác accessible flag, biết khi nào dùng `canAccess`, `setAccessible`, `trySetAccessible`, và vì sao ranh giới module của Java 9+ có thể chặn việc bật flag. Các ví dụ dùng Java 17+.

## 1. Vai trò và các API chính

```text
java.lang.reflect.AccessibleObject
  ├── java.lang.reflect.Field
  └── java.lang.reflect.Executable
        ├── java.lang.reflect.Method
        └── java.lang.reflect.Constructor
```

| API | Ý nghĩa |
| --- | --- |
| `boolean canAccess(Object obj)` | Cho biết caller hiện tại có thể truy cập thành viên được biểu diễn hay không, xét receiver và trạng thái hiện có |
| `void setAccessible(boolean flag)` | Đặt flag yêu cầu bỏ qua kiểm tra truy cập; bật `true` chỉ thành công nếu quy tắc Java/module cho phép |
| `boolean trySetAccessible()` | Thử bật flag; trả `true` nếu thành công, `false` nếu không thể bật vì quyền truy cập |
| `boolean isAccessible()` | API cũ, deprecated từ Java 9; **chỉ** phản ánh flag bỏ qua kiểm tra, không trả lời đầy đủ câu hỏi caller có thể truy cập không |
| `static void setAccessible(AccessibleObject[] array, boolean flag)` | Đặt flag cho nhiều đối tượng Reflection, vẫn chịu kiểm tra quyền/module |

Các phương thức `Class.getDeclaredField`, `getDeclaredMethod` và `getDeclaredConstructor` có thể trả về member `private`, `protected` hoặc package-private của chính lớp đó, nhưng **không tự bật flag**. Các API `getField`, `getMethod`, `getConstructor` tìm các thành viên `public` thuộc phạm vi tương ứng; ngay cả với member `public`, module hoặc lớp khai báo vẫn ảnh hưởng khả năng truy cập từ caller.

## 2. Phân biệt ba điều thường bị nhập nhằng

**Visibility của thành viên** là `public`, `protected`, package-private hoặc `private` trong mã nguồn và bytecode. Reflection không đổi visibility này.

**Trạng thái accessible flag** là lựa chọn trên đối tượng `Field`, `Method` hoặc `Constructor` cụ thể nhằm bỏ qua kiểm tra truy cập khi dùng chính đối tượng Reflection ấy. Mặc định flag là `false`. `setAccessible(true)` hoặc `trySetAccessible()` thành công sẽ bật flag; `setAccessible(false)` tắt flag.

**Quyền truy cập thực tế** được kiểm tra theo caller, loại thành viên, receiver, flag và ranh giới module. Đây là ý nghĩa của `canAccess(obj)`. Một phương thức `public` có thể có flag `false` mà `canAccess(receiver) == true`, vì caller đã có quyền theo quy tắc thông thường. Ngược lại, tìm được member `private` bằng `getDeclaredMethod` không có nghĩa `invoke` sẽ được cho phép.

Do vậy:

- `isAccessible() == false` **không** có nghĩa “thành viên không thể truy cập”.
- `canAccess(obj)` không bật quyền truy cập; nó chỉ kiểm tra.
- `setAccessible(true)` không đổi member thành `public` và không vượt qua mọi giới hạn Java Platform Module System (JPMS).
- `setAccessible(false)` không cấm caller sử dụng member mà caller vốn đã có quyền truy cập.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo đúng một tệp `AccessibleObjectDemo.java` như sau. `Vault` là lớp **top-level riêng**, nằm trong cùng tệp/package với lớp demo nhưng không phải nested class. Cách tổ chức này tránh hiệu ứng **nestmates**: các nested class cùng nest có thể truy cập thành viên `private` của nhau theo quy tắc Java hiện đại, làm sai kỳ vọng khi minh họa thiếu quyền.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessibleObjectDemo {
    public static void main(String[] args) throws Exception {
        Constructor<Vault> ctor = Vault.class.getDeclaredConstructor();
        System.out.println("constructor.before=" + ctor.canAccess(null));
        System.out.println("constructor.try=" + ctor.trySetAccessible());

        Vault vault = ctor.newInstance();
        System.out.println("constructor.after=" + ctor.canAccess(null));

        Field secret = Vault.class.getDeclaredField("secret");
        System.out.println("field.before=" + secret.canAccess(vault));

        try {
            secret.get(vault);
        } catch (IllegalAccessException e) {
            System.out.println("field.get.before=IllegalAccessException");
        }

        secret.setAccessible(true);
        System.out.println("field.after=" + secret.canAccess(vault));
        System.out.println("field.value=" + secret.get(vault));

        secret.setAccessible(false);
        System.out.println("field.reset=" + secret.canAccess(vault));

        Method reveal = Vault.class.getDeclaredMethod(
                "reveal", String.class);
        System.out.println("method.before=" + reveal.canAccess(vault));
        System.out.println("method.try=" + reveal.trySetAccessible());
        System.out.println("method.result="
                + reveal.invoke(vault, "key="));

        Method status = Vault.class.getDeclaredMethod("status");
        System.out.println("public.canAccess=" + status.canAccess(vault));
    }
}

class Vault {
    private final String secret;

    private Vault() {
        this.secret = "s3";
    }

    private String reveal(String prefix) {
        return prefix + secret;
    }

    public String status() {
        return "READY";
    }
}
```

Dùng terminal tại thư mục chứa tệp:

```bash
javac AccessibleObjectDemo.java
java AccessibleObjectDemo
```

Kết quả chuẩn trong ví dụ chạy trên classpath (unnamed module):

```text
constructor.before=false
constructor.try=true
constructor.after=true
field.before=false
field.get.before=IllegalAccessException
field.after=true
field.value=s3
field.reset=false
method.before=false
method.try=true
method.result=key=s3
public.canAccess=true
```

**Giải thích:**

1. `Vault()` là constructor `private`. `getDeclaredConstructor()` vẫn tìm được metadata nhưng `canAccess(null)` ban đầu bằng `false` đối với caller `AccessibleObjectDemo`. Sau khi `trySetAccessible()` trả `true`, `newInstance()` tạo được đối tượng.
2. `secret` là trường `private final`. `getDeclaredField` tìm thấy nó nhưng `Field.get` bị chặn trước khi bật override, nên ném `IllegalAccessException`.
3. `setAccessible(true)` bật flag trên đối tượng `Field secret`, cho phép **đọc** giá trị `s3`. Ví dụ không thử sửa một trường `final`.
4. `setAccessible(false)` tắt override; vì caller khác class khai báo, `canAccess(vault)` trở về `false`.
5. Phương thức `reveal(String)` là `private`, cần bật flag trước khi gọi `invoke`. Phương thức `status()` là `public`, và hai lớp nằm cùng package, nên có thể truy cập bình thường mà không bật flag.

Lưu ý: hành vi chính xác phụ thuộc quan hệ class, package, module và caller. Không lấy kết quả của ví dụ chạy trên classpath để kết luận mọi member `private` trong module khác đều mở được.

## 4. setAccessible, trySetAccessible và việc hoàn nguyên flag

### setAccessible(true)

`member.setAccessible(true)` yêu cầu bỏ qua kiểm tra truy cập Java khi thao tác qua **member đó**. Nếu được phép, lần thao tác sau như `Field.get`, `Method.invoke` hay `Constructor.newInstance` có thể sử dụng override; nếu bị JPMS chặn, thường nhận `java.lang.reflect.InaccessibleObjectException`, một **unchecked exception**.

```java
// Đoạn minh họa, giả định method và receiver đã được khai báo,
// method không nhận tham số, và code nằm trong ngữ cảnh xử lý exception.
try {
    method.setAccessible(true);
    Object result = method.invoke(receiver);
} catch (java.lang.reflect.InaccessibleObjectException e) {
    System.out.println("Package/module không mở cho deep reflection");
} catch (ReflectiveOperationException e) {
    System.out.println("Thao tác Reflection thất bại: " + e);
}
```

Đoạn trên không phải chương trình chạy độc lập. `invoke` còn có thể ném `IllegalArgumentException` khi receiver/tham số không hợp lệ; `InvocationTargetException` bọc exception do phương thức đích ném ra. Không nên xem mọi lỗi tại `invoke` là lỗi permission.

### trySetAccessible()

`trySetAccessible()` phù hợp khi ứng dụng muốn fallback có kiểm soát:

```java
// Minh họa trong method có xử lý các ngoại lệ của invoke.
if (method.trySetAccessible()) {
    Object result = method.invoke(receiver);
    System.out.println(result);
} else {
    System.out.println("Không thể bật quyền truy cập Reflection");
}
```

Kết quả `true` nghĩa là bật flag thành công hoặc flag đã bật. Kết quả `false` nghĩa là không thể bật theo điều kiện truy cập hiện tại, chẳng hạn package của module khác không mở cho caller. `trySetAccessible()` **vẫn có thể ném `SecurityException`** trong môi trường có kiểm soát bảo mật tương ứng; không nên diễn giải nó thành API “không bao giờ ném lỗi”.

### setAccessible(false)

Gọi `member.setAccessible(false)` tắt flag override trên đối tượng Reflection đó. Khi tiếp tục thao tác, các quy tắc kiểm tra truy cập bình thường lại áp dụng. Member `public` vốn truy cập được thì vẫn có thể truy cập được. Không nên kỳ vọng thao tác này đổi visibility hay thu hồi quyền của mã khác.

### isAccessible() đã deprecated

`isAccessible()` chỉ trả về trạng thái **suppress access checks flag**, vì thế tên phương thức dễ gây hiểu lầm. Nó đã deprecated kể từ Java 9. Dùng `canAccess(receiver)` để hỏi caller hiện tại có thể truy cập hay không; dùng `trySetAccessible()` để hỏi và thử bật flag khi cần. Một member `public` với `isAccessible() == false` vẫn có thể có `canAccess(receiver) == true`.

## 5. Ranh giới của accessible flag trong ứng dụng

Cờ bỏ qua kiểm tra truy cập chỉ áp dụng cho đối tượng Reflection cụ thể; nó không đổi modifier của lớp hoặc mở package trên phạm vi toàn JVM. Nếu caller thuộc một named module khác và package không mở đúng phạm vi, `trySetAccessible()` có thể trả `false` còn `setAccessible(true)` có thể ném `InaccessibleObjectException`. `exports` cho public API khác `opens` cho deep reflection.

Việc đã bật cờ cũng không giải quyết lỗi receiver, kiểu đối số, logic method hoặc giới hạn ghi của field `final`. Với nhu cầu thông thường, ưu tiên public API. Khi cần deep reflection, xác định package/module sở hữu và xử lý nhánh bị từ chối có chủ đích.

**Tự kiểm tra:** Vì sao một method `public` có thể `canAccess(receiver) == true` khi accessible flag vẫn `false`? Vì sao `setAccessible(false)` không làm method public trở thành private? Vì sao đọc được private final field chưa chứng minh rằng bạn có thể sửa nó?