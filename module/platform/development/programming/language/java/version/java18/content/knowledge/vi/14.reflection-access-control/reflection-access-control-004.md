# trySetAccessible(): xử lý kết quả boolean khi xin quyền truy cập sâu

## Mục tiêu bài học

Trong chương **Quyền reflection** của mô-đun Java 18, chúng ta kiểm chứng hợp đồng vẫn áp dụng trên JDK hiện đại của `java.lang.reflect.AccessibleObject.trySetAccessible()`. Phương thức này cho phép chương trình **thử bật chế độ bỏ qua kiểm tra truy cập ngôn ngữ Java** trên một đối tượng reflection và nhận kết quả `boolean` để quyết định bước tiếp theo.

Sau bài học, bạn có thể:

- Phân biệt **tìm thấy member** với **được quyền truy cập member**.
- Giải thích `true` và `false` do `trySetAccessible()` trả về; xử lý nhánh từ chối một cách có chủ đích.
- Hiểu vai trò của `exports` và `opens` trong Java Platform Module System (JPMS).
- Dùng `canAccess(receiver)` để kiểm tra quyền hiện tại mà không thay đổi trạng thái truy cập.
- Viết ví dụ thực tế cho hai module: package được `exports` nhưng không được `opens`, rồi cấp quyền mở đúng mục tiêu để kiểm chứng sự khác biệt.
- Nhận diện giới hạn: bật access checks suppression không có nghĩa có thể sửa mọi trường `final`, vượt qua ranh giới module, hay bỏ qua lỗi khi gọi method.

> **Phạm vi hiện hành:** `trySetAccessible()` được giới thiệu trước Java 18 và vẫn là API reflection tiêu chuẩn trên các JDK mới. Bài này tập trung vào cơ chế kiểm soát truy cập được hỗ trợ của Java, đặc biệt là strong encapsulation của named modules. Không sử dụng API nội bộ của JDK hoặc thủ thuật phá đóng gói.

## 1. `trySetAccessible()` giải quyết vấn đề gì?

Reflection cho phép xem thông tin lớp, method, constructor và field khi chạy. Tuy nhiên, **có được metadata không đồng nghĩa có quyền truy cập sâu**.

Giả sử một lớp chứa phương thức private:

~~~java
public final class Account {
    private String internalCode() {
        return "A-001";
    }
}
~~~

Mã ở nơi khác có thể lấy metadata bằng `Account.class.getDeclaredMethod("internalCode")` trong những điều kiện thông thường. Nhưng việc gọi `Method.invoke(...)` có thể bị từ chối bởi quy tắc kiểm tra quyền truy cập. `trySetAccessible()` cho bạn một cách **thử** nới kiểm tra quyền trên chính đối tượng `Method` đó.

Chữ ký:

~~~java
public final boolean trySetAccessible()
~~~

Phương thức được kế thừa bởi những kiểu reflection đại diện cho member, như `Method`, `Field` và `Constructor` thông qua `AccessibleObject`.

Cách hiểu hai kết quả:

| Kết quả | Ý nghĩa | Quyết định trong ứng dụng |
| --- | --- | --- |
| `true` | Đã bật được chế độ bỏ qua kiểm tra truy cập ngôn ngữ Java trên đối tượng reflection, hoặc chế độ đó đã được bật trước đó. | Có thể tiếp tục gọi/get/set theo hợp đồng của member, nhưng vẫn phải xử lý receiver, kiểu đối số và các giới hạn khác. |
| `false` | Không thể bật chế độ đó cho đối tượng reflection trong ngữ cảnh hiện tại. | Chọn lối đi khác: API public, quyền `opens` phù hợp, hoặc báo tính năng không khả dụng; không cố gọi sâu như thể đã được cấp quyền. |

**Điểm cốt lõi:** `false` là **một kết quả hợp lệ của API**, đặc biệt khi truy cập member private thuộc package trong named module khác mà package đó không được mở cho module gọi. Đây là tình huống phải đưa vào nhánh xử lý rõ ràng.

`trySetAccessible()` **không sửa khai báo `private` thành `public`**, không thay đổi `module-info.java`, và không cấp quyền truy cập cho mọi đoạn mã ở mọi module. Nó chỉ thay đổi trạng thái bỏ qua access checks gắn với **đối tượng `AccessibleObject` đang sử dụng** khi được JVM cho phép.

## 2. Mẫu sử dụng đúng: kiểm tra boolean trước khi thao tác

Mẫu dùng với `Method`:

~~~java
Method method = SomeType.class.getDeclaredMethod("hidden");
Object receiver = /* instance phu hop cua SomeType */;

if (method.trySetAccessible()) {
    // Duoc phep bo qua access checks cua Java tren Method nay.
    Object value = method.invoke(receiver);
    // Xu ly value...
} else {
    // Khong duoc cap quyen: chon public API hoac thong bao ro rang.
}
~~~

Đây là **mẫu minh họa**: `SomeType` và `receiver` cần được thay bằng lớp/instance thực tế. Khi phương thức đích là static, `invoke(null, ...)` là cách gọi rõ ràng; khi là instance, receiver phải khác `null` và có kiểu phù hợp.

Trình tự nên dùng:

1. Tìm đúng member bằng `getDeclaredMethod(...)`, `getDeclaredField(...)` hoặc `getDeclaredConstructor(...)`.
2. Kiểm tra xem có thể dùng API public trực tiếp hay không. Chỉ yêu cầu truy cập sâu khi thực sự cần.
3. Nếu cần bỏ qua access checks, gọi `trySetAccessible()` **một lần cho đối tượng reflection đang sử dụng**.
4. Nếu là `true`, thao tác trên member và xử lý ngoại lệ liên quan.
5. Nếu là `false`, dùng phương án thay thế có kiểm soát; không bỏ qua nhánh từ chối.

Dạng điều kiện phủ định cũng hữu ích nếu muốn thoát sớm:

~~~java
if (!method.trySetAccessible()) {
    throw new IllegalStateException(
            "Khong duoc phep reflection sau vao member nay");
}

// Chi den day khi viec bat access suppression duoc chap thuan.
Object result = method.invoke(receiver);
~~~

Ném `IllegalStateException` trong ví dụ là **quyết định của ứng dụng**, không phải ngoại lệ tự động do `trySetAccessible()` ném khi trả về `false`.

## 3. `exports` khác `opens` như thế nào?

Trên JDK hiện đại, cơ chế module là yếu tố quyết định nhiều trường hợp `trySetAccessible()`.

- `exports p;` cho phép những module đọc module hiện tại truy cập **API public** trong package `p` theo quy tắc Java. Nó **không** tự cấp quyền phản chiếu sâu vào member private/package-private.
- `opens p;` cho phép **deep reflection** đối với package `p` từ các module khác, tùy các quy tắc còn lại của Java. Nó không có ý nghĩa giống `exports` cho việc biên dịch mã tham chiếu trực tiếp.
- `opens p to m;` chỉ mở package `p` cho module `m` được nêu tên. Đây thường là lựa chọn hẹp hơn khi chỉ một framework hoặc module cụ thể cần reflection sâu.
- `open module m { ... }` mở tất cả package của module đó cho reflection sâu. Cần cân nhắc phạm vi trước khi áp dụng.

Nếu cả mã gọi và lớp khai báo member nằm **trong cùng một module**, việc bật access suppression được cho phép theo quy tắc JPMS ngay cả với private member (giả sử không có giới hạn đặc biệt khác). Ở **hai named modules khác nhau**, truy cập private member thông thường cần package đích được mở cho module của bên gọi.

Bảng tình huống thực tế:

| Quan hệ giữa bên gọi và member | Khả năng `trySetAccessible()` | Giải thích |
| --- | --- | --- |
| Cùng module, member private | Thông thường `true` | Quy tắc module cho phép bật bỏ qua access checks trong cùng module. |
| Khác module, lớp public và method public trong package được `exports` tới bên gọi | `true` | Truy cập public hợp lệ; thường không cần xin quyền sâu. |
| Khác module, method private trong package chỉ được `exports` | `false` | `exports` không mở truy cập sâu. |
| Khác module, method private trong package được `opens` tới bên gọi | `true` | Module chủ sở hữu đã cho phép reflection sâu. |
| Khác module, package không export, không open | Thông thường `false` cho member cần truy cập sâu | Không có quyền nới access checks cho package đóng. |
| Member vốn public và truy cập được theo Java | Có thể dùng trực tiếp | Nên tránh xin quyền sâu không cần thiết. |

Bảng tập trung vào các trường hợp phổ biến của `Method`, `Field`, `Constructor`. Với protected static member, constructor của lớp đặc biệt, hoặc thành viên có giới hạn riêng, cần đọc hợp đồng cụ thể của `AccessibleObject` trên JDK đang chạy. Không nên quy mọi member về một quy tắc “cứ khác module là false”.

### Vì sao chỉ `exports` là chưa đủ?

Xét:

~~~java
module secret.library {
    exports example.secret;
}
~~~

Module `secret.client` có `requires secret.library;` sẽ dùng được `public` type và method công khai của `example.secret`, nhưng vẫn **không được phép** bỏ qua quyền private chỉ vì package đã export.

Nếu thư viện muốn hỗ trợ reflection sâu có kiểm soát cho một framework/module cụ thể, có thể khai báo thêm:

~~~java
module secret.library {
    exports example.secret;
    opens example.secret to secret.client;
}
~~~

Trong ứng dụng, hãy ưu tiên thiết kế public API phù hợp. Chỉ mở package thật sự cần thiết và hướng tới các module xác định.

## 4. Ví dụ đầy đủ với hai named modules

Ví dụ này chứng minh trực tiếp nhánh `false` rồi `true` của cùng một lời gọi `trySetAccessible()`. Cách làm sử dụng hai module nguồn để ranh giới JPMS được thể hiện rõ, không phụ thuộc framework.

### 4.1. Cấu trúc mã nguồn

~~~text
src/
  secret.library/
    module-info.java
    example/secret/SecretBox.java
  secret.client/
    module-info.java
    example/client/AccessProbe.java
~~~

File `src/secret.library/module-info.java`:

~~~java
module secret.library {
    exports example.secret;
}
~~~

File `src/secret.library/example/secret/SecretBox.java`:

~~~java
package example.secret;

public final class SecretBox {
    private final String code = "demo-123";

    public String publicName() {
        return "SecretBox";
    }

    private String reveal() {
        return code;
    }
}
~~~

File `src/secret.client/module-info.java`:

~~~java
module secret.client {
    requires secret.library;
}
~~~

File `src/secret.client/example/client/AccessProbe.java`:

~~~java
package example.client;

import example.secret.SecretBox;
import java.lang.reflect.Method;

public final class AccessProbe {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        SecretBox box = new SecretBox();

        Method method = SecretBox.class.getDeclaredMethod("reveal");

        System.out.println("before=" + method.canAccess(box));

        boolean granted = method.trySetAccessible();
        System.out.println("granted=" + granted);

        if (granted) {
            System.out.println("after=" + method.canAccess(box));
            System.out.println("value=" + method.invoke(box));
        } else {
            System.out.println("fallback=" + box.publicName());
        }
    }
}
~~~

Ở đây, `getDeclaredMethod("reveal")` tìm được metadata của private method. `method.canAccess(box)` kiểm tra quyền truy cập **đang có**, còn `method.trySetAccessible()` yêu cầu bật chế độ bỏ qua access checks.

### 4.2. Biên dịch và chạy khi package chỉ được `exports`

Trong thư mục chứa `src`, chạy với JDK hiện đại:

~~~sh
javac --module-source-path src -d out -m secret.library,secret.client
java --module-path out -m secret.client/example.client.AccessProbe
~~~

Kết quả mong đợi:

~~~text
before=false
granted=false
fallback=SecretBox
~~~

Diễn giải:

- `secret.client` đọc được `secret.library` và tham chiếu được lớp public `SecretBox` nhờ `exports`.
- `reveal()` vẫn là private method. Package `example.secret` chưa được mở cho `secret.client`.
- `trySetAccessible()` trả về `false`. Ứng dụng không gọi `invoke` trong nhánh này và chuyển sang API public `publicName()`.

Đây là cách xử lý **đúng hợp đồng**. Không nên gọi `method.invoke(box)` ngay sau `granted=false` rồi chỉ hy vọng hệ thống bỏ qua kiểm tra truy cập.

### 4.3. Chạy lại với quyền mở package có mục tiêu

Giữ nguyên mã nguồn và module descriptor ban đầu, nhưng khi chạy, thêm tùy chọn mở đúng package cho module khách:

~~~sh
java --module-path out --add-opens secret.library/example.secret=secret.client -m secret.client/example.client.AccessProbe
~~~

Kết quả mong đợi:

~~~text
before=false
granted=true
after=true
value=demo-123
~~~

`--add-opens` ở ví dụ trên là một cách **kiểm chứng cấu hình** khi bên vận hành kiểm soát tiến trình Java. Trong ứng dụng được đóng gói chủ động, có thể chọn khai báo `opens example.secret to secret.client;` trong `module-info.java` của `secret.library` rồi biên dịch lại. Không nên coi `--add-opens` rộng khắp là cấu hình mặc định cho mọi ứng dụng.

Quan sát quan trọng: `before=false` ngay cả khi package đã được mở vì `reveal()` vẫn là private method, nên kiểm tra truy cập thông thường chưa cho phép gọi. Sau `trySetAccessible()` trả về `true`, trạng thái suppression trên đối tượng `Method` mới được bật, dẫn tới `after=true`.

## 5. `trySetAccessible()` và `canAccess(obj)` là hai câu hỏi khác nhau

Hai API thường đi cùng nhau nhưng không hoán đổi cho nhau:

| API | Nó trả lời câu hỏi gì? | Có thay đổi trạng thái suppression? |
| --- | --- | --- |
| `method.canAccess(receiver)` | Trong trạng thái hiện tại, bên gọi có thể truy cập member thông qua đối tượng reflection này không? | **Không** |
| `method.trySetAccessible()` | Bên gọi có được phép bật suppression trên đối tượng reflection này không? | **Có thể có**, khi trả về `true` |
| `method.setAccessible(true)` | Yêu cầu bật suppression; nếu bị JPMS từ chối, báo lỗi bằng ngoại lệ. | Có nếu được phép |
| `method.invoke(receiver, args...)` | Thực thi method với receiver/đối số đã cung cấp. | Không |

### Cách truyền đối số cho `canAccess`

`AccessibleObject.canAccess(Object obj)` nhận đối số theo loại member:

- Với `Method` instance hoặc `Field` instance: truyền một receiver **không null**, đúng kiểu khai báo.
- Với `Method` static hoặc `Field` static: truyền `null`.
- Với `Constructor`: truyền `null` (constructor chưa có receiver).

Ví dụ:

~~~java
Method instanceMethod = SecretBox.class.getDeclaredMethod("reveal");
boolean current = instanceMethod.canAccess(new SecretBox());

// Kiem tra static method neu co:
Method staticMethod = Math.class.getMethod("abs", int.class);
boolean staticAllowed = staticMethod.canAccess(null);
~~~

**Không nhầm `canAccess(null)` với `trySetAccessible()` trả về `false`:** truyền receiver không hợp lệ cho `canAccess` có thể gây `IllegalArgumentException`; nó không có chức năng xin cấp quyền. Ngoài ra, `canAccess` là phép kiểm tra tại thời điểm gọi, không phải một cam kết rằng lời gọi `invoke` sau đó sẽ không thất bại bởi lý do khác.

Tránh sử dụng `isAccessible()` làm cách kiểm tra quyền mới: trên JDK hiện đại, phương thức này đã bị đánh dấu deprecated và tên của nó dễ gây nhầm giữa cờ suppression với quyền truy cập thực tế. Khi cần kiểm tra khả năng truy cập, dùng `canAccess(...)`; khi cần xin phép bỏ qua access checks, dùng `trySetAccessible()`.

## 6. So sánh với `setAccessible(true)`

Hai cách gọi đều nhằm bật suppression khi được JVM cho phép, nhưng **giao diện xử lý từ chối** khác nhau:

~~~java
// Cach A: quyet dinh theo boolean
if (method.trySetAccessible()) {
    Object result = method.invoke(receiver);
} else {
    // Duong xu ly du phong du kien truoc.
}
~~~

~~~java
// Cach B: yeu cau truy cap, tu choi duoc bao bang exception
method.setAccessible(true); // Co the nem InaccessibleObjectException
Object result = method.invoke(receiver);
~~~

Khi sự thất bại của truy cập sâu là **một tình huống dự kiến**, `trySetAccessible()` thường dễ đọc và dễ kiểm soát hơn vì chương trình buộc phải xét kết quả `boolean`. Khi ứng dụng yêu cầu bắt buộc phải có quyền và muốn báo lỗi ngay, cách yêu cầu trực tiếp có thể phù hợp; mọi trường hợp vẫn cần tuân thủ JPMS.

Không nên viết như sau:

~~~java
method.trySetAccessible();  // Bo qua boolean
Object value = method.invoke(receiver);
~~~

Nếu lời xin quyền bị từ chối, lệnh `invoke` tiếp theo có thể gặp `IllegalAccessException`. Kiểu lỗi này làm nguyên nhân thực sự khó nhận diện hơn so với việc xử lý `false` ngay tại nơi xin quyền.

## 7. `true` không đồng nghĩa mọi thao tác đều thành công

Sau khi `trySetAccessible()` trả về `true`, JVM đã chấp thuận suppression cho đối tượng reflection, nhưng các quy tắc khác vẫn áp dụng:

### Receiver và đối số

Một `Method` instance vẫn đòi hỏi receiver hợp lệ; phương thức static vẫn dùng receiver `null` theo cách gọi rõ ràng; tham số `invoke` phải tương thích chữ ký. Sai receiver/đối số có thể gây `NullPointerException` hoặc `IllegalArgumentException` ngay cả khi `trySetAccessible()` đã trả về `true`.

### Ngoại lệ của phương thức đích

Nếu chính phần thân method ném ngoại lệ, `Method.invoke` bọc ngoại lệ đó vào `InvocationTargetException`. Việc suppression được chấp thuận không khiến logic nghiệp vụ trở nên an toàn hoặc ngăn lỗi bên trong method.

~~~java
try {
    Object value = method.invoke(receiver);
    // Xu ly ket qua.
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable rootCause = ex.getCause();
    // Ghi log / xu ly loi cua chinh method dich.
}
~~~

Đây là đoạn minh họa quy tắc lỗi; phần mã bao quanh cần khai báo hoặc xử lý thêm các checked exceptions của API reflection.

### Field `final` và giới hạn ghi

Bật suppression **không có nghĩa** có thể sửa tùy ý mọi field `final`. Trên JDK hiện đại, có những final field không cho phép ghi thông qua reflection, như static final field và final field của record. Các quy tắc bảo vệ/giới hạn mới của JDK liên quan đến biến final cũng có thể phụ thuộc phiên bản và cấu hình chạy.

Vì vậy, `trySetAccessible() == true` không phải phép thử cho kết luận “`Field.set(...)` chắc chắn thành công”. Nên ưu tiên API khởi tạo hoặc cập nhật đối tượng công khai thay vì thay trạng thái private/final sau khi tạo.

### Tác động của đối tượng reflection được dùng chung

Trạng thái suppression được đặt trên **đối tượng `Method`/`Field`/`Constructor` cụ thể**. Nếu nhiều đoạn mã dùng chung chính đối tượng reflection đó, việc bật suppression ảnh hưởng đến những lời gọi thông qua đối tượng ấy. Đừng suy ra rằng việc gọi `trySetAccessible()` đã sửa toàn bộ trạng thái truy cập của lớp hay module; nếu lấy một đối tượng reflection khác, hãy kiểm tra quyền của đối tượng mới theo ngữ cảnh tương ứng.

## 8. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `getDeclaredMethod(...)` tìm được private method nhưng `trySetAccessible()` trả `false` | Package thuộc named module khác, chưa `opens` cho bên gọi | Chọn public API hoặc cấp `opens ... to ...` từ module chủ sở hữu khi có cơ sở thiết kế |
| `trySetAccessible()` trả `false` dù package đã `exports` | `exports` bảo đảm quyền đối với API public, không đồng nghĩa deep reflection | Phân biệt yêu cầu compile-time/public API và yêu cầu reflection sâu |
| `canAccess(receiver)` ném `IllegalArgumentException` | Receiver sai kiểu hoặc truyền `null` cho member instance | Xác định static/instance; truyền receiver phù hợp hoặc `null` theo hợp đồng |
| `trySetAccessible()` trả `true` nhưng `Method.invoke` thất bại | Sai receiver, sai đối số hoặc phần thân method ném lỗi | Đọc đúng loại ngoại lệ, kiểm tra chữ ký và `InvocationTargetException.getCause()` |
| `trySetAccessible()` trả `true` nhưng `Field.set` không sửa được final field | Bị hạn chế ghi bởi hợp đồng `Field`/phiên bản JDK | Tránh mutation của final; dùng API tạo/cập nhật được hỗ trợ |
| Cùng mã chạy được trên class path nhưng bị từ chối trong named module | Ranh giới JPMS khác nhau | Kiểm tra module của lớp gọi, package chứa member và `opens`/`exports` |
| Không kiểm tra boolean, sau đó gặp `IllegalAccessException` | Đã bỏ qua nhánh `false` của `trySetAccessible()` | Xử lý kết quả ngay, báo rõ quyền cần thiết hoặc dùng fallback |

### Checklist khi điều tra

1. Xác định **member cụ thể**: `Method`, `Field` hay `Constructor`; tên, modifiers, lớp khai báo.
2. Xác định module **chứa lớp khai báo** và module **chứa mã gọi `trySetAccessible()`**.
3. Kiểm tra package có `exports` hoặc `opens` theo đúng module đích và đúng bên gọi hay không.
4. Đọc kết quả `boolean` của `trySetAccessible()`; không gộp `false` với lỗi của method nghiệp vụ.
5. Sau khi nhận `true`, kiểm tra receiver, chữ ký, khả năng ghi field và cách xử lý ngoại lệ.
6. Nếu bắt buộc cần reflection sâu, yêu cầu chủ sở hữu module mở đúng package, đúng module; nếu không, thiết kế API công khai thay thế.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Trong module A, một lớp public nằm trong package `p` được `exports` cho module B, nhưng method `hidden()` của lớp là private. Tại module B, `getDeclaredMethod("hidden")` trả về `Method`; `trySetAccessible()` thường cho kết quả nào?

**Trả lời:** `false`, nếu package `p` không được `opens` cho B. `exports` cho phép truy cập API public nhưng không cấp phép reflection sâu vào private method.

**Câu 2.** `trySetAccessible()` trả `true`. Có được kết luận `method.invoke(null)` thành công không?

**Trả lời:** Không. Instance method vẫn yêu cầu receiver đúng kiểu và khác `null`; còn phải xét đối số và ngoại lệ phát sinh trong method. `true` chỉ xác nhận JVM cho phép bật suppression trên đối tượng reflection.

**Câu 3.** Vì sao `canAccess(receiver)` và `trySetAccessible()` không phải hai tên khác nhau cho cùng một thao tác?

**Trả lời:** `canAccess` kiểm tra quyền hiện tại mà không thay đổi trạng thái; `trySetAccessible` thử bật suppression và trả về `boolean` cho biết có được phép hay không.

**Câu 4.** Cần mở private method cho một module framework cụ thể. Nên ưu tiên `opens p;` hay `opens p to framework.module;`?

**Trả lời:** Khi biết rõ module cần truy cập, nên ưu tiên mở đúng đối tượng bằng `opens p to framework.module;` để giảm phạm vi deep reflection.

## Ghi nhớ

- **Luôn dùng kết quả `boolean`** của `trySetAccessible()` để quyết định có tiếp tục reflection sâu hay chuyển sang phương án khác.
- `true` có nghĩa việc bật suppression được cho phép trên **đối tượng reflection**, không tự bảo đảm lời gọi hoặc phép ghi thành công.
- `false` thường gặp khi member cần truy cập sâu nằm trong package của **named module khác** chưa được `opens` cho module gọi.
- `exports` dành cho truy cập API public; `opens` quyết định khả năng deep reflection qua ranh giới module.
- Dùng `canAccess(...)` khi muốn kiểm tra quyền hiện tại; dùng `trySetAccessible()` khi cần xin bật suppression.
- Khi không thể truy cập sâu, ưu tiên API public hoặc cấu hình `opens` có phạm vi cụ thể và được chủ sở hữu module cho phép.

**Tài liệu tham khảo chính thức:** Javadoc `java.lang.reflect.AccessibleObject.trySetAccessible`, `AccessibleObject.canAccess`, `java.lang.reflect.Method`, `java.lang.reflect.Field`; Java Language Specification và mô tả Java Platform Module System về `exports`/`opens` trên phiên bản JDK đang triển khai.
