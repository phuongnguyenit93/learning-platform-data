# 5.5. Sử dụng canAccess, trySetAccessible và setAccessible theo kết quả truy cập

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Kiểm tra một **Method**, **Field** hoặc **Constructor** có thể được truy cập qua Reflection **ngay lúc kiểm tra** bằng `canAccess`.
- Phân biệt **kiểm tra quyền hiện có** với **yêu cầu bỏ qua kiểm tra truy cập của ngôn ngữ Java** bằng `trySetAccessible` hoặc `setAccessible(true)`.
- Chọn cách xử lý dựa trên **giá trị true/false**, ngoại lệ, receiver hợp lệ và quy tắc **Java Platform Module System (JPMS)**.
- Giải thích vì sao thành viên `private` có thể được truy cập bằng Reflection trong một số trường hợp nhưng bị từ chối ở **module không mở package**.
- Viết code Java 17+ xử lý kết quả đúng, biết khi nào nên dùng API công khai thay vì ép truy cập.

> Phạm vi: bài này tập trung vào **quyết định quyền truy cập Reflection**, không dùng Reflection làm sandbox bảo mật và không trình bày `setAccessible(true)` như một cách luôn vượt qua mọi giới hạn.

## 1. Trước hết: “tìm thấy thành viên” khác “được phép truy cập”

Reflection có thể lấy metadata cho một thành viên `private` bằng:

~~~java
// Fragment minh họa: giả định SecretBox có private method "secret".
Method method = SecretBox.class.getDeclaredMethod("secret");
~~~

`getDeclaredMethod` trả về metadata của method khai báo trong lớp; nó **không tự cấp quyền gọi** method đó. Tương tự, `getDeclaredField` hoặc `getDeclaredConstructor` có thể tìm thấy field/constructor nhưng thao tác `get`, `set`, `newInstance` vẫn phải tuân thủ kiểm tra truy cập, trừ khi Reflection được phép bật cơ chế bỏ qua kiểm tra ấy.

Ba API thường dùng đều nằm trên `java.lang.reflect.AccessibleObject`:

| API | Câu hỏi nó trả lời | Kết quả/hiệu ứng | Nếu không đủ quyền |
| --- | --- | --- | --- |
| `canAccess(Object obj)` | “**Từ ngữ cảnh gọi hiện tại**, tôi có thể truy cập thành viên này với receiver `obj` không?” | `boolean`; **không cố bật** cơ chế bỏ qua access checks | Thường trả `false` nếu receiver hợp lệ |
| `trySetAccessible()` | “Tôi có thể **bật accessible flag** của đối tượng Reflection này không?” | `boolean`; `true` khi có thể bật cờ, `false` khi không thể | Trả `false` cho nhiều trường hợp bị JPMS từ chối |
| `setAccessible(boolean flag)` | “Hãy đặt accessible flag thành giá trị yêu cầu.” | `void`; `true` yêu cầu bỏ qua kiểm tra truy cập Java tại các thao tác Reflection phù hợp; `false` tắt yêu cầu đó | `setAccessible(true)` có thể ném `InaccessibleObjectException` |

`trySetAccessible()` và `setAccessible(true)` **không có quyền năng vô điều kiện**. Quy tắc module (và trên những runtime có cơ chế kiểm tra bảo mật liên quan, các kiểm tra đó) vẫn quyết định có cho phép bật cờ hay không.

Các method `canAccess`, `trySetAccessible`, `setAccessible` hoạt động trên một đối tượng Reflection cụ thể, chẳng hạn đối tượng `Method` mà bạn đang giữ; không trực tiếp thay đổi khai báo `private` thành `public` trong class.

## 2. Cách ra quyết định theo kết quả

Quy trình thực tế nên xuất phát từ một **thành viên đã biết và được phép dùng**:

~~~text
Tra cứu Method / Field / Constructor hợp lệ
                  |
                  v
Xác định đúng receiver cho canAccess(...)
                  |
                  v
           canAccess(receiver)?
               /       \
             true      false
              |          |
   Gọi qua Reflection    v
                   Có thực sự cần deep
                   reflective access?
                     /         \
                   không        có
                    |            |
              Chọn API        trySetAccessible()
              công khai        /        \
                           true        false
                             |           |
                           Gọi       Fallback / báo
                          member      giới hạn truy cập
~~~

Đoạn mã minh họa quyết định cho một **instance Method**:

~~~java
// Fragment: method được tra cứu trước, receiver đúng kiểu, caller được tin cậy.
if (!method.canAccess(receiver)) {
    if (!method.trySetAccessible()) {
        throw new IllegalStateException(
                "Không được phép truy cập method này qua Reflection");
    }
}
Object result = method.invoke(receiver);
~~~

Đây là **fragment**, không phải chương trình độc lập: `method`, `receiver` phải được khai báo; nhánh invoke cần xử lý các checked exception như `IllegalAccessException` và `InvocationTargetException`. Trên những môi trường còn thực thi kiểm tra SecurityManager, `trySetAccessible()` cũng có thể ném `SecurityException`; do đó `false` không phải kiểu thất bại duy nhất có thể xảy ra.

**Vì sao kiểm tra trước?** Nếu `canAccess` đã `true`, code có thể dùng member ngay mà không sửa accessible flag. Nếu `false`, phải quyết định liệu việc truy cập non-public có thực sự là yêu cầu hợp lệ; chỉ sau đó mới thử bật cờ và kiểm tra kết quả.

**Không xem `false` như tín hiệu “chắc chắn gọi `setAccessible(true)` sẽ thành công”.** Với package không mở qua module, câu lệnh ấy vẫn bị từ chối.

## 3. canAccess kiểm tra quyền truy cập đang có

`AccessibleObject.canAccess(Object obj)` được thêm vào Java 9 và trả lời quyền truy cập có thể dùng qua Reflection từ ngữ cảnh gọi hiện tại.

- Nếu thành viên vốn `public` và kiểu chứa/đường truy cập là hợp lệ, `canAccess` có thể trả `true` ngay cả khi accessible flag đang **false**.
- Nếu thành viên `private` không thể được gọi từ caller theo quyền Java thông thường, `canAccess` trả `false` khi chưa bật suppression.
- Sau khi `trySetAccessible()` hoặc `setAccessible(true)` thành công, `canAccess` thường trả `true` với receiver đúng.
- `canAccess` không thử biến `false` thành `true`; nó là **kiểm tra**, không phải yêu cầu mở quyền.

### 3.1. Truyền receiver đúng theo loại thành viên

Đối số `obj` của `canAccess` không luôn giống nhau:

| Thành viên Reflection | Giá trị truyền cho `canAccess` |
| --- | --- |
| Instance `Method` | Đối tượng receiver thuộc lớp khai báo hoặc lớp con phù hợp |
| Instance `Field` | Đối tượng receiver tương thích với lớp khai báo |
| `static Method` hoặc `static Field` | `null` |
| `Constructor` | `null` |

Ví dụ:

~~~java
// Fragment giả định đã có các biến hợp lệ:
instanceMethod.canAccess(service); // instance method: dùng receiver
staticMethod.canAccess(null);      // static method: dùng null
constructor.canAccess(null);       // constructor: dùng null
~~~

Đây là **mã minh họa**, không tự biên dịch độc lập. Truyền `null` cho instance member, truyền object không đúng kiểu receiver, hoặc truyền non-null cho static member/constructor có thể làm `canAccess` ném `IllegalArgumentException`. Vì vậy một lỗi receiver **khác** kết quả `false` do thiếu quyền.

Khi dùng `Field.get(receiver)`, `Field.set(receiver, value)` hoặc `Method.invoke(receiver, args...)`, cũng phải tuân thủ hợp đồng receiver và kiểu đối số của API đó.

### 3.2. canAccess phụ thuộc caller và ngữ cảnh

Quyền truy cập thông thường phụ thuộc vào modifier (`public`, `protected`, package-private, `private`), kiểu khai báo, quan hệ package/subclass, **nestmates** và các ràng buộc module. Cùng một member có thể được code ở một vị trí gọi truy cập hợp lệ nhưng code ở vị trí gọi khác thì không, nếu chưa bật suppression.

Vì vậy không nên lấy một phép kiểm tra `canAccess` từ helper trong module khác rồi xem như bằng chứng phổ quát cho mọi caller. Một hàm helper kiểm tra và gọi luôn trong cùng ngữ cảnh sẽ dễ suy luận hơn. Ngoài ra, trạng thái accessible flag thuộc đối tượng Reflection cụ thể; không nên suy ra rằng mọi đối tượng `Method` lấy từ cùng class đều có cùng trạng thái override.

## 4. trySetAccessible: thử mở quyền và trả về boolean

`trySetAccessible()` yêu cầu đặt accessible flag thành `true` **nếu môi trường cho phép**.

~~~java
// Fragment: field đã được lấy bằng getDeclaredField(...).
if (field.trySetAccessible()) {
    Object value = field.get(receiver);
    // Xử lý value theo hợp đồng ứng dụng.
} else {
    // Không có quyền bật suppress-access-checks trong ngữ cảnh hiện tại.
    // Chọn API public, yêu cầu module mở package hoặc từ chối thao tác.
}
~~~

Đây là fragment giả định `field` và `receiver` đã tồn tại; cần xử lý checked exception phù hợp.

Nếu `trySetAccessible()` trả `true`, cờ đã ở trạng thái cho phép suppress access checks. Nếu `false`, bạn phải **tôn trọng kết quả**, không tiếp tục gọi `get`/`invoke` với hy vọng quyền tự mở. Tuy nhiên nếu một member đã public-accessible và không cần mở quyền, hãy dùng `canAccess` trước để tránh làm thay đổi flag không cần thiết.

Một số điều kiện có thể cho phép `trySetAccessible()` thành công:

- Caller và declaring class ở **cùng module**; việc bật suppression có thể được cho phép ngay cả với private member.
- Thành viên thuộc public class, có public visibility và package được **exported** phù hợp cho caller.
- Package được **opened** phù hợp cho module của caller, cho phép deep reflection theo quy tắc JPMS.
- Member thuộc những trường hợp được API cho phép khác, chẳng hạn một số `protected static` member với quan hệ subclass phù hợp.

Ngược lại, một `private` member của lớp ở **named module khác** với package chỉ `exports` nhưng **không `opens`** cho caller thường không thể bật suppression. `trySetAccessible()` khi đó có thể trả `false`.

**Chú ý:** `trySetAccessible()` tránh phải dựa vào `InaccessibleObjectException` cho trường hợp JPMS từ chối thường gặp; nó **không** có cam kết “không bao giờ ném bất kỳ ngoại lệ nào”, ví dụ kiểm tra an ninh vẫn có thể ném `SecurityException` ở runtime hỗ trợ cơ chế này.

## 5. setAccessible(true/false): yêu cầu thay đổi accessible flag

`setAccessible(true)` yêu cầu bỏ qua các kiểm tra truy cập Java thông thường khi thao tác Reflection, **chỉ nếu API và module cho phép**. Khi thất bại vì JPMS, API ném `java.lang.reflect.InaccessibleObjectException` (unchecked). Khác với `trySetAccessible`, nó **không trả boolean**.

~~~java
// Fragment: dành cho đường chạy "fail fast" có chủ đích.
try {
    method.setAccessible(true);
    Object result = method.invoke(receiver);
} catch (java.lang.reflect.InaccessibleObjectException ex) {
    // Package/module không cho phép bật accessible flag.
    // Chọn public API, thay cấu hình module hợp lệ hoặc báo lỗi rõ ràng.
}
~~~

`method` và `receiver` là biến minh họa, đoạn mã chưa tự chạy độc lập; `invoke` còn có checked exceptions.

`setAccessible(false)` **tắt accessible flag** trên đối tượng Reflection đó, đưa các kiểm tra truy cập Java thông thường trở lại hiệu lực ở các lần dùng tiếp theo. Nó **không buộc `canAccess` trả false**: public member hợp lệ vẫn có thể được truy cập theo quyền thông thường. Việc bật/tắt không biến class thành public, không mở module, cũng không sửa metadata hoặc bytecode của lớp.

Một lưu ý vận hành: Nếu một `Method`/`Field` được nhiều luồng dùng chung, bật rồi tắt accessible flag quanh từng lệnh `invoke` có thể gây race với những luồng khác. Hãy kiểm soát vòng đời đối tượng Reflection, tránh chia sẻ mutable access state thiếu đồng bộ; tốt nhất chọn sẵn cơ chế truy cập hợp lệ và ổn định cho cả luồng xử lý.

### 5.1. API isAccessible() cũ dễ gây hiểu sai

`AccessibleObject.isAccessible()` đã **deprecated** từ Java 9. Nó phản ánh trạng thái **accessible flag** (cờ suppress checks), không đồng nghĩa với câu hỏi “caller này hiện có truy cập member hợp lệ hay không”.

Đặc biệt:

~~~text
public member, quyền Java bình thường hợp lệ
accessible flag = false
canAccess(correctReceiver) = true
~~~

Dùng `canAccess` để kiểm tra khả năng truy cập thực tế; chỉ dùng `trySetAccessible`/`setAccessible` khi thật sự muốn thay đổi quyền kiểm tra của đối tượng Reflection.

## 6. Ví dụ chạy được: quan sát cả ba API trên method, field, static method và constructor

Tạo file **AccessDecisionDemo.java** trong một thư mục trống. Hai lớp top-level dưới đây được biên dịch từ **cùng một file**; `Vault` là một top-level class khác `AccessDecisionDemo`, không phải nested class/nestmate. Điều này giúp phép kiểm tra private thật sự có ý nghĩa.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessDecisionDemo {
    public static void main(String[] args) throws Exception {
        Vault vault = Vault.create();
        Method visible = Vault.class.getMethod("view");
        Method secret = Vault.class.getDeclaredMethod("secret");
        Field count = Vault.class.getDeclaredField("count");
        Method twice = Vault.class.getDeclaredMethod("twice", int.class);
        Constructor<Vault> constructor = Vault.class.getDeclaredConstructor();

        System.out.println("public.canAccess=" + visible.canAccess(vault));
        System.out.println("private.canAccess.before=" + secret.canAccess(vault));
        try {
            secret.invoke(vault);
        } catch (IllegalAccessException ex) {
            System.out.println("private.invoke.before=denied");
        }
        System.out.println("private.try=" + secret.trySetAccessible());
        System.out.println("private.canAccess.after=" + secret.canAccess(vault));
        System.out.println("private.invoke.after=" + secret.invoke(vault));
        secret.setAccessible(false);
        System.out.println("private.canAccess.reset=" + secret.canAccess(vault));
        System.out.println("public.canAccess.withFlagFalse=" + visible.canAccess(vault));

        System.out.println("field.canAccess.before=" + count.canAccess(vault));
        System.out.println("field.try=" + count.trySetAccessible());
        System.out.println("field.getInt=" + count.getInt(vault));

        System.out.println("static.canAccess.before=" + twice.canAccess(null));
        System.out.println("static.try=" + twice.trySetAccessible());
        System.out.println("static.invoke=" + twice.invoke(null, 21));

        System.out.println("ctor.canAccess.before=" + constructor.canAccess(null));
        System.out.println("ctor.try=" + constructor.trySetAccessible());
        System.out.println("ctor.new=" + constructor.newInstance().getClass().getSimpleName());
    }
}

class Vault {
    private int count = 7;
    private Vault() {}
    static Vault create() { return new Vault(); }
    public String view() { return "public"; }
    private String secret() { return "secret"; }
    private static int twice(int n) { return n * 2; }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 AccessDecisionDemo.java
java AccessDecisionDemo
~~~

Stdout:

~~~text
public.canAccess=true
private.canAccess.before=false
private.invoke.before=denied
private.try=true
private.canAccess.after=true
private.invoke.after=secret
private.canAccess.reset=false
public.canAccess.withFlagFalse=true
field.canAccess.before=false
field.try=true
field.getInt=7
static.canAccess.before=false
static.try=true
static.invoke=42
ctor.canAccess.before=false
ctor.try=true
ctor.new=Vault
~~~

### 6.1. Diễn giải kết quả

1. `view()` là **public** và caller nằm trong ngữ cảnh cho phép truy cập, nên `visible.canAccess(vault)` trả `true` dù chưa bật suppression.
2. `secret()` là **private** của **top-level Vault**. `AccessDecisionDemo` không phải class khai báo hoặc nestmate của Vault, nên lần kiểm tra ban đầu trả `false`. Gọi `invoke` ngay bị `IllegalAccessException`.
3. Hai lớp ở **cùng unnamed module**, nên `secret.trySetAccessible()` có thể bật accessible flag thành công, trả `true`; sau đó `invoke` trả chuỗi **secret**.
4. `secret.setAccessible(false)` tắt suppression; vì private vẫn không thuộc quyền thông thường của caller, `canAccess` trở lại `false`.
5. Trên public method `view()`, accessible flag false **không ngăn** truy cập thông thường: `visible.canAccess(vault)` vẫn `true`.
6. Với instance field `count`, dùng **receiver `vault`** khi kiểm tra và đọc; với static method `twice`, dùng **`null`** khi kiểm tra/gọi.
7. Với constructor, `canAccess(null)` dùng `null`, và chỉ sau khi bật quyền mới có thể `newInstance` qua private constructor của Vault từ caller này.

**Vì sao dùng một class `Vault` riêng?** Nếu code kiểm tra private method nằm ngay trong lớp khai báo, hoặc là nestmate có quyền private theo Java, `canAccess` ban đầu **có thể đã true**. Muốn minh họa chênh lệch trước/sau suppression, cần tạo đúng ngữ cảnh caller không có quyền private thông thường.

Ví dụ này phản ánh một môi trường classpath/unnamed module cho phép bật accessible flag đối với những thành viên trên. **Không suy ra** từ kết quả này rằng private member trong mọi named module đều mở được.

## 7. Khi có named module: exports khác opens

Khi Java module system có hiệu lực, một lớp có thể **public**, package được **exports** để module khác gọi API công khai, nhưng việc Reflection cố bỏ qua kiểm tra để đụng vào **private member** vẫn bị từ chối vì package **không được opens**.

- `exports p;`: cho các module phù hợp sử dụng **public types/public members** của package theo luật module; không tự cho phép deep reflection vào private.
- `opens p;`: mở package cho deep reflective access ở runtime đối với những module có quyền tương ứng; vẫn cần gọi `trySetAccessible`/`setAccessible` khi muốn bỏ qua member access.
- `opens p to some.module;`: chỉ mở package cho module được nêu; hữu ích để thu hẹp bề mặt reflection.
- `--add-opens source.module/package=target.module`: tùy chọn runtime để mở package có mục đích khi cấu hình module không sửa được, nên dùng có kiểm soát.

### 7.1. Dựng hai named module chạy độc lập

Tạo cấu trúc sau:

~~~text
src/
  demo.lib/
    module-info.java
    sample/api/PortalApi.java
  demo.client/
    module-info.java
    sample/client/CheckModules.java
~~~

**src/demo.lib/module-info.java**

~~~java
module demo.lib {
    exports sample.api;
}
~~~

Package public được export, nhưng chưa được opens.

**src/demo.lib/sample/api/PortalApi.java**

~~~java
package sample.api;

public class PortalApi {
    public String view() { return "visible"; }
    private String secret() { return "hidden"; }
}
~~~

**src/demo.client/module-info.java**

~~~java
module demo.client {
    requires demo.lib;
}
~~~

**src/demo.client/sample/client/CheckModules.java**

~~~java
package sample.client;

import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import sample.api.PortalApi;

public class CheckModules {
    public static void main(String[] args) throws Exception {
        PortalApi api = new PortalApi();
        Method publicMethod = PortalApi.class.getMethod("view");
        Method privateMethod = PortalApi.class.getDeclaredMethod("secret");

        System.out.println("public.canAccess=" + publicMethod.canAccess(api));
        System.out.println("private.canAccess.before=" + privateMethod.canAccess(api));
        System.out.println("private.try=" + privateMethod.trySetAccessible());
        try {
            privateMethod.setAccessible(true);
            System.out.println("private.set=ok");
        } catch (InaccessibleObjectException ex) {
            System.out.println("private.set=blocked");
        }
        System.out.println("public.invoke=" + publicMethod.invoke(api));
        if (privateMethod.canAccess(api)) {
            System.out.println("private.invoke=" + privateMethod.invoke(api));
        } else {
            System.out.println("private.invoke=skipped");
        }
    }
}
~~~

Các lệnh dưới đây dùng shell POSIX (macOS/Linux/Git Bash), chạy tại thư mục chứa **src**; với Windows PowerShell, hãy tạo hai thư mục **mods/demo.lib**, **mods/demo.client** tương đương trước khi gọi cùng các lệnh javac/java:

~~~bash
mkdir -p mods/demo.lib mods/demo.client
javac -encoding UTF-8 -d mods/demo.lib src/demo.lib/module-info.java src/demo.lib/sample/api/PortalApi.java
javac -encoding UTF-8 --module-path mods -d mods/demo.client src/demo.client/module-info.java src/demo.client/sample/client/CheckModules.java
java --module-path mods -m demo.client/sample.client.CheckModules
~~~

Stdout khi chỉ có **exports**, chưa **opens**:

~~~text
public.canAccess=true
private.canAccess.before=false
private.try=false
private.set=blocked
public.invoke=visible
private.invoke=skipped
~~~

Cần để ý các điểm khác biệt:

1. `publicMethod` được gọi vì **public type + public method + exported package** phù hợp.
2. `getDeclaredMethod("secret")` tìm được metadata private **không đồng nghĩa** với quyền gọi private method.
3. `privateMethod.trySetAccessible()` trả `false`, vì **demo.lib** chưa mở `sample.api` cho **demo.client**.
4. `privateMethod.setAccessible(true)` ném `InaccessibleObjectException`; chương trình bắt và chuyển thành **private.set=blocked**.
5. Chương trình bỏ qua việc invoke private method khi không có quyền; đây là nhánh xử lý hợp lệ thay vì cưỡng ép truy cập.

### 7.2. Mở package cho đúng module gọi

Một cách là thay module descriptor của thư viện thành:

~~~java
// Phiên bản thay thế của src/demo.lib/module-info.java
module demo.lib {
    exports sample.api;
    opens sample.api to demo.client;
}
~~~

Đây là **nội dung thay thế file module-info.java** đã đưa ở trên, không phải một module khai báo bổ sung. Biên dịch lại module thư viện sau khi thay file và chạy lại ứng dụng với cùng module path. Một số cách biên dịch riêng thư viện có thể cảnh báo nếu compiler chưa nhìn thấy target module **demo.client**; có thể cung cấp module path phù hợp khi biên dịch. `opens ... to demo.client` vẫn là quy tắc mở package theo tên module ở runtime.

Cách thứ hai, **không cần đổi source module-info.java**, chạy ứng dụng đã biên dịch từ mục 7.1 với tùy chọn mở package rõ ràng:

~~~bash
java --module-path mods --add-opens demo.lib/sample.api=demo.client -m demo.client/sample.client.CheckModules
~~~

Trong cả hai tình huống khi package được mở đúng cho module caller, stdout của chương trình là:

~~~text
public.canAccess=true
private.canAccess.before=false
private.try=true
private.set=ok
public.invoke=visible
private.invoke=hidden
~~~

Giải thích: Ban đầu private method vẫn không thuộc quyền Java thông thường của caller, nên `canAccess` là `false`. Nhưng package đã **opens** cho caller, nên `trySetAccessible` bật cờ thành công; `setAccessible(true)` cũng được phép, sau đó `canAccess` là `true` và `invoke` chạy `secret()`.

**Mở package không phải chuyển `private` thành `public`.** Java source thông thường từ demo.client vẫn không thể gọi `api.secret()`. Chỉ đường truy cập phản chiếu được phép bật suppression theo cấu hình phù hợp.

### 7.3. Exported package chưa đủ cho private reflection

Với named module, phép kiểm tra cần phân biệt:

| Điều kiện từ module caller | Public exported member | Private member qua trySetAccessible |
| --- | --- | --- |
| `demo.lib exports sample.api` nhưng không opens | Có thể truy cập bằng quyền thông thường | Bị từ chối nếu không có quyền đặc biệt khác |
| `demo.lib opens sample.api to demo.client` | Public API vẫn hoạt động | Có thể bật suppression từ demo.client |
| Runtime `--add-opens demo.lib/sample.api=demo.client` | Public API vẫn hoạt động | Có thể bật suppression từ demo.client |
| Package không exported và không opened cho module caller | Quyền truy cập thông thường cũng bị giới hạn | Không tự vượt được nhờ setAccessible |

Trong môi trường classpath, unnamed modules có quy tắc mở package khác với named modules; vì vậy cùng một ví dụ reflection có thể chạy trên classpath nhưng thất bại sau khi chuyển sang module path. Luôn thử trên **cách triển khai thật**.

**Hạn chế của add-opens:** Tùy chọn runtime là quyết định cấu hình có ảnh hưởng đến encapsulation; không nên thêm mở rộng hàng loạt chỉ để tránh xử lý lỗi. Với ứng dụng sản phẩm, ưu tiên public API hoặc cấu hình **opens ... to** cho đúng framework/module cần deep reflection.

## 8. So sánh cách xử lý cho từng kết quả

| Kết quả | Ý nghĩa đúng | Cách xử lý |
| --- | --- | --- |
| `canAccess(receiver) == true` | Thao tác Reflection hiện được phép | Gọi trực tiếp; vẫn bắt lỗi nghiệp vụ/runtime khi thực thi |
| `canAccess(receiver) == false` | Caller chưa thể truy cập member như hiện tại | Xem có cần private access hay public API thay thế |
| `trySetAccessible() == true` | Đã có thể đặt accessible flag thành true | Có thể gọi member với receiver/args hợp lệ; chú ý lỗi khác |
| `trySetAccessible() == false` | Không thể bật flag theo quy tắc hiện hành | Fallback, thông báo ràng buộc hoặc sửa cấu hình module có chủ đích |
| `setAccessible(true)` thành công | Đã yêu cầu bật flag thành công | Gọi member và quản lý vòng đời flag theo hợp đồng |
| `setAccessible(true)` ném `InaccessibleObjectException` | Cơ chế module ngăn suppression | Không gọi cưỡng ép; dùng public API hoặc mở package phù hợp |
| `setAccessible(false)` thành công | Đã tắt override trên đối tượng Reflection | Quyền thông thường vẫn còn; kiểm tra `canAccess` nếu cần |

### 8.1. Các trường hợp false không đủ để chẩn đoán toàn bộ sự cố

`canAccess` là boolean về quyền tại thời điểm kiểm tra; nó **không chứng minh** code sẽ thực thi thành công:

- Receiver sai hoặc `null` không hợp lệ có thể gây `IllegalArgumentException` ngay trong `canAccess`.
- `Method.invoke` có thể thất bại vì số lượng/kiểu argument, hoặc method đích tự ném ngoại lệ.
- Field có thể là `final` hoặc non-modifiable final theo ràng buộc API; **bật accessible flag không bảo đảm được quyền ghi**.
- Đối tượng Reflection được chia sẻ và flag bị thay đổi đồng thời có thể làm kết quả kiểm tra trước đó không còn phù hợp khi gọi.
- Thay đổi class loader, version hoặc module graph trong một kiến trúc plugin có thể khiến giả định về class/member không còn đúng.

**Đặc biệt với final field:** `setAccessible(true)` không phải công cụ cho phép sửa mọi `final`; các ràng buộc mạnh tồn tại đối với static final, một số final trong record và hidden class. Hãy xem API member cụ thể và thiết kế immutable object thay vì dựa vào mutate final bằng Reflection.

## 9. Phân biệt ngoại lệ theo giai đoạn

| Bước | Loại lỗi | Ý nghĩa/ứng xử |
| --- | --- | --- |
| `getDeclaredMethod(...)` | `NoSuchMethodException` | Sai tên/chữ ký; chưa phải lỗi truy cập |
| `canAccess(receiver)` | `IllegalArgumentException` | Receiver không đúng hợp đồng của instance/static/constructor |
| `trySetAccessible()` | `false` | Không mở được quyền theo ràng buộc hiện tại; xử lý nhánh |
| `trySetAccessible()` hoặc `setAccessible(...)` | `SecurityException` trong môi trường có kiểm tra liên quan | Cần chính sách quyền phù hợp; không giả định chỉ có false |
| `setAccessible(true)` | `InaccessibleObjectException` | Package/module không cho phép suppress access checks |
| `Method.invoke(...)` | `IllegalAccessException` | Chưa có quyền reflective access cần thiết |
| `Method.invoke(...)` | `IllegalArgumentException` | Receiver hoặc đối số không tương thích |
| `Method.invoke(...)` | `InvocationTargetException` | Method đích đã chạy nhưng ném ngoại lệ; đọc `getCause()` |

Không nên bắt mọi `Exception` rồi báo “private method bị khóa”: lỗi truy cập, lỗi dữ liệu, thiếu member và lỗi nghiệp vụ là những nguyên nhân khác nhau.

Ví dụ khi một method hợp lệ ném `IllegalStateException`, `Method.invoke` thường bao bọc nó trong `InvocationTargetException`; `canAccess` vẫn có thể đã true trước khi gọi. Cần hiển thị cause và kiểm soát thông tin nhạy cảm khi ghi log.

## 10. Ứng dụng thực tế và cách thiết kế an toàn

Reflection truy cập thành viên non-public xuất hiện trong serializers, ORM, dependency injection, plugin systems hoặc công cụ kiểm thử. Với Java 17+, việc module đóng gói rõ ràng đòi hỏi người viết framework và ứng dụng thống nhất hợp đồng thay vì dựa vào giả định mọi private member đều mở được.

Các nguyên tắc:

1. **Ưu tiên API công khai và hợp đồng rõ.** Nếu chủ sở hữu lớp có thể cung cấp constructor, getter, setter hoặc interface cần thiết, những cách này thường dễ bảo trì hơn deep reflection.
2. **Kiểm tra đúng member và receiver.** Đừng chạy `canAccess(null)` cho instance method; đừng lấy nhầm overload của method.
3. **Chỉ bật suppression khi thực sự cần.** Khi `canAccess` đã true, gọi luôn; khi false, xác định có được phép thử mở quyền không.
4. **Xử lý kết quả của `trySetAccessible`.** Có nhánh fallback/unsupported rõ ràng; không nuốt false rồi gọi và để lỗi nổ ở nơi khác.
5. **Nếu bắt buộc `setAccessible(true)`, bắt lỗi đúng.** Dùng `InaccessibleObjectException` để xử lý từ chối do JPMS; không dùng catch-all che giấu lỗi nghiệp vụ.
6. **Giới hạn surface deep reflection.** Đối với module tự sở hữu, cân nhắc `opens package to framework.module`; tránh `opens` rộng hoặc `--add-opens` cho mọi module khi không có lý do.
7. **Không sử dụng accessibility làm ranh giới sandbox.** Class loader, `private` và flag truy cập không thay thế kiểm soát quyền thực thi của code không đáng tin.
8. **Tính đến triển khai thực tế.** Java classpath, module path, container runtime image, plugin class loader có thể khác nhau về khả năng truy cập. Có test tích hợp trên cấu hình sản phẩm thật.
9. **Không dựa vào isAccessible() như phép kiểm tra quyền.** `isAccessible()` chỉ phản ánh override flag; `canAccess` trả lời đúng câu hỏi hơn.
10. **Tránh chia sẻ trạng thái accessible flag thay đổi liên tục giữa luồng.** Cache member đã được kiểm chứng theo đúng module/loader context; không tự ý reset flag khi thành phần khác còn dùng.

### 10.1. Bảng chọn API nhanh

| Tình huống | API nên cân nhắc |
| --- | --- |
| Chỉ cần biết hiện có gọi được method hay đọc field không | `canAccess(correctReceiver)` |
| Có fallback và cần thử deep reflection mà không muốn dùng exception làm nhánh từ chối module | `trySetAccessible()` + kiểm tra boolean |
| Thực thi phải yêu cầu deep reflection hoặc fail fast rõ ràng | `setAccessible(true)` + xử lý `InaccessibleObjectException` |
| Kết thúc một đợt dùng và muốn tắt suppression trên đối tượng Reflection của mình | `setAccessible(false)`, lưu ý member public vẫn có thể accessible |
| Không kiểm soát được mở package ở module sở hữu lớp | Dùng public API/adapter; thông báo giới hạn thay vì giả định setAccessible sẽ phá được module |
| Cần quyền private trong một module mình quản lý | Thiết kế `opens` đúng đích hoặc public contract; cân nhắc API MethodHandles tùy yêu cầu |

## 11. Tự kiểm tra

**Câu 1.** Một public method thuộc public class trong package exported tới caller. Accessible flag hiện false. `canAccess(validReceiver)` nhất thiết false không?

**Đáp án:** Không. Nếu quyền Java thông thường cho phép, `canAccess` vẫn true dù flag suppression đang false.

**Câu 2.** `getDeclaredMethod` tìm thấy private method của named module khác. Có được gọi ngay bằng `Method.invoke` không?

**Đáp án:** Không thể suy ra. Cần kiểm tra quyền hiện tại bằng `canAccess`, và nếu có nhu cầu hợp lệ thì thử `trySetAccessible`. Nếu module không opens package và không có quyền đặc biệt khác, deep reflection có thể bị từ chối.

**Câu 3.** `trySetAccessible()` trả false. Có nên gọi `setAccessible(true)` ngay với kỳ vọng bắt buộc mở được quyền không?

**Đáp án:** Không. `setAccessible(true)` cũng chịu ràng buộc module; thường sẽ ném `InaccessibleObjectException` thay vì trả false. Hãy chọn fallback hoặc thay cấu hình mở package có chủ đích.

**Câu 4.** `setAccessible(false)` xong, `canAccess` trên một public method được phép truy cập có nhất thiết false không?

**Đáp án:** Không. `setAccessible(false)` chỉ tắt suppress-access-checks flag; quyền Java thông thường đối với public method vẫn có thể cho `canAccess` true.

**Câu 5.** Gọi `instanceMethod.canAccess(null)` nhận `false` hay có thể ném lỗi?

**Đáp án:** Đây là receiver không hợp lệ đối với instance method; API có thể ném `IllegalArgumentException`. Dùng một object receiver tương thích.

**Câu 6.** Vì sao code chạy ở classpath thành công khi `trySetAccessible` vào private field, nhưng chuyển sang named module thì thất bại?

**Đáp án:** Quy tắc mở package giữa các module khác nhau. Unnamed module thường mở package cho deep reflection; named module khác có thể chỉ exported mà không opened package. Phải xem module graph và package opens thực tế.

**Câu 7.** `canAccess` trả true có đồng nghĩa method đích không bao giờ ném ngoại lệ không?

**Đáp án:** Không. Phép kiểm tra chỉ nói về quyền truy cập. `Method.invoke` vẫn có thể lỗi do receiver/args hoặc báo `InvocationTargetException` nếu method đích ném exception.

## Ghi nhớ

- `canAccess(receiver)` là **kiểm tra có thể truy cập lúc này không**, từ ngữ cảnh caller hiện tại, với receiver hợp lệ.
- `trySetAccessible()` là **thử bật accessible flag và nhận true/false**; false cần được xử lý như một nhánh hợp lệ.
- `setAccessible(true)` là **yêu cầu bật flag, có thể ném InaccessibleObjectException** nếu JPMS không cho phép; `setAccessible(false)` chỉ tắt cờ override.
- **Tìm được member không đồng nghĩa gọi được member.** `getDeclaredMethod/getDeclaredField` và access check là những bước khác nhau.
- **exports khác opens**: exported public API không mặc nhiên cho phép deep reflection vào private member.
- Ưu tiên **public API hoặc module opens có kiểm soát**; không viết code giả định Reflection luôn vượt qua encapsulation.

## Tài liệu tra cứu

- Java SE 17 — **AccessibleObject**, `canAccess`, `trySetAccessible`, `setAccessible`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 17 — **InaccessibleObjectException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- Java SE 17 — **Method** và `invoke`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 17 — **Module** và encapsulation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- OpenJDK Java 17 — **Java Platform Module System / --add-opens**: https://openjdk.org/jeps/261
