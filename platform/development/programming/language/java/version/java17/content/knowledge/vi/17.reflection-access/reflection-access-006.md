# privateLookupIn và điều kiện đọc, mở package trong Java 17

**Chủ đề:** Java 17 → Reflection và truy cập  
**Trọng tâm:** Dùng `MethodHandles.privateLookupIn` để tạo một `Lookup` có quyền truy cập private vào lớp đích; hiểu vì sao module của caller phải đọc module đích, vì sao package đích phải được mở, và cách cấu hình `module-info.java` hoặc tùy chọn launcher để cấp đúng quyền.

Từ Java 9, Java Platform Module System (JPMS) kiểm soát việc module nào đọc module nào và package nào được export hoặc open. Java 17 tiếp tục áp dụng strong encapsulation: mã bên ngoài không mặc nhiên được truy cập sâu vào các thành phần không public của module khác.

`MethodHandles.privateLookupIn(targetClass, callerLookup)` là API tiêu chuẩn để tạo một `MethodHandles.Lookup` trên lớp đích, có thể truy cập các thành viên private khi những điều kiện về quyền lookup và module được đáp ứng. API này được giới thiệu từ Java 9, vẫn áp dụng trong Java 17 và không cần preview flag.

Điểm cốt lõi của bài:

- `exports` cho phép truy cập thông thường tới kiểu public trong package.
- `opens` cho phép deep reflection vào các kiểu và thành viên trong package.
- Với hai module khác nhau, module của caller phải **đọc** module chứa lớp đích; module đích phải **mở package chứa lớp đích** cho module caller.
- Đối tượng `Lookup` truyền vào phải có cả quyền `PRIVATE` và `MODULE`, tức full privilege access.

## 1. MethodHandles.Lookup là gì?

`MethodHandles.Lookup` là một đối tượng đại diện cho **quyền truy cập** của một lớp Java. Nó được dùng để tìm và tạo `MethodHandle` hoặc `VarHandle` cho method, constructor và field.

Ví dụ:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;

public class LookupIntro {
    public static void main(String[] args) {
        Lookup lookup = MethodHandles.lookup();

        System.out.println(lookup.lookupClass());
        System.out.println(lookup.lookupModes());
    }
}
~~~

`MethodHandles.lookup()` là phương thức caller-sensitive. Đối tượng được trả về đại diện cho lớp thực sự gọi phương thức này. Khi được gọi trực tiếp bên trong `LookupIntro`, `lookup.lookupClass()` là `LookupIntro.class`.

Một `Lookup` không phải là quyền truy cập toàn cục. Nó gắn với một lớp cụ thể và chỉ có thể tạo method handle cho những thành viên mà lớp đó được phép truy cập theo các access mode đang có.

### 1.1. Các lookup mode quan trọng

`Lookup.lookupModes()` trả về một bit mask biểu diễn những quyền mà lookup hiện có.

| Mode | Ý nghĩa |
| --- | --- |
| `PUBLIC` | Truy cập các thành viên public theo quy tắc module. |
| `PRIVATE` | Truy cập thành viên private của lookup class và các nestmate phù hợp. |
| `PROTECTED` | Truy cập thành viên protected theo quy tắc Java. |
| `PACKAGE` | Truy cập thành viên package-private trong runtime package phù hợp. |
| `MODULE` | Xác nhận lookup được tạo trong module của lookup class; hỗ trợ kiểm tra quyền xuyên module. |
| `ORIGINAL` | Lookup gốc do VM tạo cho caller; có thêm một số khả năng đặc biệt. |
| `UNCONDITIONAL` | Mode của public lookup, cho phép truy cập public API được export vô điều kiện mà không dựa trên readability thông thường. |

Một lookup mới lấy từ `MethodHandles.lookup()` trong mã Java thông thường có đầy đủ các mode phù hợp với lớp caller, bao gồm `PRIVATE` và `MODULE`. Ngược lại, `MethodHandles.publicLookup()` chỉ có quyền public tối thiểu; nó không đủ để gọi `privateLookupIn`.

Có thể kiểm tra hai quyền bắt buộc:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;

Lookup lookup = MethodHandles.lookup();

boolean hasPrivate =
    (lookup.lookupModes() & Lookup.PRIVATE) != 0;
boolean hasModule =
    (lookup.lookupModes() & Lookup.MODULE) != 0;

System.out.println("PRIVATE: " + hasPrivate);
System.out.println("MODULE:  " + hasModule);
~~~

Để gọi `privateLookupIn`, cả hai giá trị phải là `true`. Java 17 cũng có phương thức `lookup.hasFullPrivilegeAccess()` để kiểm tra trực tiếp điều kiện full privilege access.

### 1.2. Lookup là capability

Một `Lookup` có quyền private có thể tạo method handle truy cập thành viên private. Khi một method handle đã được tạo thành công, việc gọi handle không thực hiện lại toàn bộ access check như lúc tạo handle.

Vì vậy, không nên chia sẻ tùy tiện một `Lookup` có quyền cao hoặc method handle truy cập private cho mã không đáng tin cậy. Người nhận có thể dùng capability đó để thực hiện thao tác mà code tạo handle được phép làm.

## 2. privateLookupIn dùng để làm gì?

Cú pháp:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

Phương thức trả về một `Lookup` mới có lookup class là `Target`. Khi các điều kiện truy cập được đáp ứng, lookup mới có quyền private để tạo handle cho field, method hoặc constructor private của lớp đích và các nestmate phù hợp.

Ví dụ lớp đích:

~~~java
package example;

public class Secret {
    private String message = "hidden";

    private String reveal() {
        return "message=" + message;
    }
}
~~~

Nếu caller có quyền phù hợp:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Secret.class,
        MethodHandles.lookup()
    );
~~~

`privateLookup` có thể được dùng để tạo `VarHandle` cho field private hoặc `MethodHandle` cho method private. Việc có được lookup không tự động gọi method hay thay đổi field; ứng dụng vẫn phải tạo handle và chủ động thực hiện thao tác.

### 2.1. Khác với Lookup.in

`Lookup.in(Target.class)` và `MethodHandles.privateLookupIn(Target.class, lookup)` không giống nhau:

| API | Mục đích | Có thể tăng quyền private? |
| --- | --- | --- |
| `lookup.in(Target.class)` | Chuyển lookup class sang lớp khác, giữ lại tối đa các quyền mà lookup cũ còn có thể mang theo. | Không. Quyền chỉ được giữ hoặc giảm. |
| `MethodHandles.privateLookupIn(Target.class, lookup)` | Tạo lookup có private access vào target sau khi kiểm tra điều kiện deep reflection và module. | Có, nếu caller đủ quyền và module/package cho phép. |

`Lookup.in` không phải cách né module access. Nếu package đích chưa mở và caller không có quyền phù hợp, đổi lookup class bằng `in` không tự cấp quyền truy cập private.

## 3. Điều kiện bắt buộc để gọi privateLookupIn

Theo Java SE 17 API, phương thức kiểm tra các điều kiện sau.

### 3.1. Caller lookup phải có full privilege access

`callerLookup` phải có cả hai mode:

- `PRIVATE`: chứng minh caller lookup có quyền private của lookup class.
- `MODULE`: chứng minh lookup được tạo trong module của lookup class, để Java có thể xác định module caller khi kiểm tra readability và opens.

Một lookup chỉ có public access không đáp ứng yêu cầu:

~~~java
MethodHandles.Lookup weakLookup = MethodHandles.publicLookup();

// Không đủ quyền PRIVATE và MODULE.
// MethodHandles.privateLookupIn(Secret.class, weakLookup);
~~~

Thông thường, lấy lookup gốc tại lớp framework đang thực hiện thao tác:

~~~java
MethodHandles.Lookup callerLookup = MethodHandles.lookup();
~~~

Nếu truyền lookup từ một helper class, module caller được xét là module chứa **lookup class của đối tượng được truyền**, không nhất thiết là module của lớp đang gọi helper. Hãy kiểm tra nguồn gốc của lookup thay vì chỉ nhìn vị trí lời gọi `privateLookupIn`.

### 3.2. Target phải là một class hợp lệ

`targetClass` phải là một class thực sự. Không được truyền:

- Kiểu nguyên thủy như `int.class`.
- `void.class`.
- Một array class như `String[].class`.

Các trường hợp này gây `IllegalArgumentException`. Nếu một đối số là `null`, phương thức ném `NullPointerException`.

### 3.3. Nếu caller và target ở cùng module

Gọi là `M1` module của caller lookup và `M2` module của target class.

Nếu `M1 == M2`, caller lookup có full privilege access là đủ cho điều kiện module. Không cần khai báo `opens` riêng cho package đích, bởi caller và target nằm trong cùng module.

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        AnotherClassInSameModule.class,
        MethodHandles.lookup()
    );
~~~

Quyền truy cập Java thông thường vẫn áp dụng cho việc lấy được đối tượng `Class` và các giới hạn khác của lookup; nhưng không có bước kiểm tra đọc module đích và mở package xuyên module.

### 3.4. Nếu caller và target ở hai module khác nhau

Khi `M1 != M2`, cần thêm **cả hai** điều kiện:

1. `M1 reads M2`: module chứa caller lookup phải đọc module chứa target class.
2. `M2 opens package(Target) to M1`: module chứa target class phải mở package chứa target cho module caller.

Có thể hình dung:

~~~text
Module M1 (caller)                     Module M2 (target)
------------------                     ------------------
Framework / Inspector                  Model / Secret
        |                                      |
        |  1. M1 reads M2                      |
        |------------------------------------->|
        |                                      |
        |  2. M2 opens target package to M1    |
        |<-------------------------------------|
        |                                      |
        +---- privateLookupIn(Target.class) ---+
                       |
                       v
            Lookup có PRIVATE access
            trên lớp Target
~~~

Thiếu một trong hai điều kiện thì `privateLookupIn` ném `IllegalAccessException`.

## 4. Readability: module caller phải đọc module đích

Trong module descriptor của caller, directive `requires` thường tạo quan hệ đọc:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

Ở đây `com.example.framework` là `M1` và `com.example.model` là `M2`. Module framework đọc module model.

Có thể kiểm tra ở runtime:

~~~java
Module callerModule = Inspector.class.getModule();
Module targetModule = Secret.class.getModule();

System.out.println(callerModule.canRead(targetModule));
~~~

Kết quả cần là `true` để thỏa điều kiện readability khi hai module khác nhau.

### 4.1. Readability không phải package openness

`requires` chỉ xử lý quan hệ đọc module. Nó **không tự mở package** và không cấp quyền truy cập private.

Ví dụ:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

Nếu module model không mở package chứa `Secret` cho framework, `privateLookupIn` vẫn thất bại dù `canRead` trả về `true`.

Đừng nhầm:

- `requires` / `canRead`: caller có đọc module đích không?
- `exports` / `isExported`: package có được export cho truy cập thông thường không?
- `opens` / `isOpen`: package có được mở cho deep reflection không?

Đây là ba câu hỏi liên quan nhưng không thay thế nhau.

### 4.2. Unnamed module

Mã chạy trên class path thuộc unnamed module của class loader tương ứng. Theo API `Module.canRead`, unnamed module đọc tất cả module. Tuy nhiên, nếu target nằm trong một named module, package đích vẫn phải được mở cho unnamed module để thực hiện deep reflection xuyên module.

Khi mở từ launcher cho mã class path, target module thường dùng `ALL-UNNAMED` trong `--add-opens`.

## 5. Opens: module đích phải mở package chứa target

Directive `opens` trong `module-info.java` cho phép module khác thực hiện deep reflection vào các kiểu và thành viên trong package được mở.

Ví dụ module đích:

~~~java
module com.example.model {
    opens com.example.model.internal to com.example.framework;
}
~~~

Directive này nói rằng module `com.example.model` mở package `com.example.model.internal` cho module `com.example.framework`.

Nếu target class nằm trong package khác, cần mở đúng package đó. Mở một package không tự động mở các package con.

### 5.1. Qualified opens và unqualified opens

Có hai dạng thường dùng:

**Mở cho một module cụ thể:**

~~~java
opens com.example.model.internal to com.example.framework;
~~~

Đây là `qualified opens`. Chỉ module được liệt kê nhận quyền deep reflection qua directive này.

**Mở cho mọi module:**

~~~java
opens com.example.model.internal;
~~~

Đây là `unqualified opens`. Package được mở cho tất cả module khác. Phạm vi rộng hơn, nên nếu chỉ một framework cần truy cập thì qualified opens thường phù hợp hơn.

### 5.2. Open module

Có thể khai báo:

~~~java
open module com.example.model {
}
~~~

Một `open module` mở tất cả package của module cho deep reflection ở runtime. Không cần viết từng directive `opens`.

Không nên dùng `open module` chỉ để giải quyết một trường hợp truy cập private nếu có thể mở đúng package cho đúng module. Mở toàn bộ module làm phạm vi truy cập rộng hơn yêu cầu.

### 5.3. Opens không thay thế exports

`opens` phục vụ truy cập phản chiếu ở runtime; nó không tự cấp quyền truy cập source-level thông thường vào public type của package cho mã ở module khác.

Nếu caller cần viết `Secret.class` hoặc import public class `Secret` trong source, package thường phải được export cho caller:

~~~java
module com.example.model {
    exports com.example.model.domain to com.example.framework;
    opens com.example.model.domain to com.example.framework;
}
~~~

Hai directive có mục đích riêng:

- `exports` cho phép caller tham chiếu public API trong package.
- `opens` cho phép caller thực hiện deep reflection vào private member của các class trong package.

Trong một thiết kế khác, framework có thể nhận `Class<?>` từ cơ chế plugin hoặc tải class theo tên mà không import trực tiếp kiểu đích. Khi đó, không nhất thiết phải export package chỉ để có một tham chiếu source-level; nhưng điều kiện mở package cho deep reflection vẫn cần được đáp ứng.

## 6. Ví dụ hoàn chỉnh với hai named module

Ví dụ này có hai module:

- `com.example.model` chứa lớp có field và method private.
- `com.example.framework` đọc module model, có quyền truy cập lớp public và được mở package để dùng private lookup.

### 6.1. Cấu trúc thư mục

~~~text
src/
  com.example.model/
    module-info.java
    com/example/model/domain/Secret.java
  com.example.framework/
    module-info.java
    com/example/framework/Inspector.java
~~~

### 6.2. Module model

File `src/com.example.model/module-info.java`:

~~~java
module com.example.model {
    exports com.example.model.domain to com.example.framework;
    opens com.example.model.domain to com.example.framework;
}
~~~

File `src/com.example.model/com/example/model/domain/Secret.java`:

~~~java
package com.example.model.domain;

public final class Secret {
    private String message = "classified";

    public Secret() {
    }

    private String reveal() {
        return "message=" + message;
    }
}
~~~

Lớp `Secret` và constructor public được export có giới hạn cho framework để code framework có thể tham chiếu kiểu và tạo object. Field `message` và method `reveal()` vẫn là private. Directive `opens` cho phép framework thực hiện deep reflection trên package.

### 6.3. Module framework

File `src/com.example.framework/module-info.java`:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

File `src/com.example.framework/com/example/framework/Inspector.java`:

~~~java
package com.example.framework;

import com.example.model.domain.Secret;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Method;

public class Inspector {
    public static void main(String[] args) throws Throwable {
        Secret secret = new Secret();

        // Lookup được tạo trong module com.example.framework.
        Lookup callerLookup = MethodHandles.lookup();

        // Tạo lookup private trên lớp ở module com.example.model.
        Lookup privateLookup =
            MethodHandles.privateLookupIn(Secret.class, callerLookup);

        // Truy cập field private bằng VarHandle.
        VarHandle messageHandle = privateLookup.findVarHandle(
            Secret.class,
            "message",
            String.class
        );

        System.out.println(messageHandle.get(secret));
        messageHandle.set(secret, "updated");

        // Tạo MethodHandle từ private method đã được reflection tìm thấy.
        Method revealMethod = Secret.class.getDeclaredMethod("reveal");
        MethodHandle revealHandle =
            privateLookup.unreflect(revealMethod);

        System.out.println((String) revealHandle.invoke(secret));
    }
}
~~~

### 6.4. Biên dịch và chạy

Từ thư mục gốc của ví dụ:

~~~shell
javac --module-source-path src -d out -m com.example.model,com.example.framework
java --module-path out -m com.example.framework/com.example.framework.Inspector
~~~

Kết quả:

~~~text
classified
message=updated
~~~

Giải thích:

1. `requires com.example.model` tạo readability từ framework tới model.
2. `exports ... to com.example.framework` cho phép framework tham chiếu public class `Secret` trong mã nguồn.
3. `opens ... to com.example.framework` cho phép deep reflection và `privateLookupIn` truy cập thành viên private.
4. `MethodHandles.lookup()` được gọi từ `Inspector` nên lookup class thuộc module framework và có full privilege access.
5. `privateLookupIn` tạo lookup trên `Secret`; lookup đó được dùng để tìm `VarHandle` và `MethodHandle`.

Nếu bỏ directive `opens` nhưng giữ `requires` và `exports`, mã vẫn có thể biên dịch, nhưng lời gọi `privateLookupIn` sẽ ném `IllegalAccessException` ở runtime. Điều này cho thấy export public package không đủ cho truy cập private.

## 7. Dùng --add-opens khi chưa thể sửa module descriptor

Đôi khi module đích thuộc thư viện bên thứ ba hoặc JDK, và nhóm phát triển chưa thể thay đổi `module-info.java` của module đó. Java launcher hỗ trợ tùy chọn `--add-opens`:

~~~shell
java --add-opens source.module/package.name=target.module ...
~~~

Ví dụ với hai module ở trên, có thể cấp opens từ dòng lệnh:

~~~shell
java --add-opens com.example.model/com.example.model.domain=com.example.framework --module-path out -m com.example.framework/com.example.framework.Inspector
~~~

Lúc này, directive `opens` trong descriptor của module model có thể được bỏ đi để thử quyền được cấp từ launcher. Module framework vẫn phải đọc module model, ví dụ qua `requires com.example.model`.

### 7.1. Mở cho class path: ALL-UNNAMED

Nếu caller chạy trên class path, mã caller thuộc unnamed module. Cú pháp:

~~~shell
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Ví dụ trên mở package `java.lang` của module `java.base` cho tất cả unnamed module. Đây là một quyền khá rộng; chỉ dùng khi đã xác định thư viện nào cần truy cập và có lý do chuyển đổi rõ ràng.

### 7.2. --add-opens không phải giải pháp thay thế lâu dài

`--add-opens` là cấu hình runtime mở package. Nó không:

- Biến private member thành public.
- Thay đổi source-level access control của Java.
- Làm API nội bộ trở thành API được hỗ trợ.
- Thay thế quan hệ đọc module nếu module caller chưa đọc module đích.
- Tự sửa mã đang gọi `privateLookupIn` với lookup không đủ quyền.

Nếu có thể sửa module descriptor của module sở hữu package, qualified `opens` thường thể hiện hợp đồng rõ ràng hơn. Nếu phụ thuộc đến từ thư viện ngoài, hãy cập nhật thư viện hoặc làm việc với nhà cung cấp để giảm nhu cầu mở package.

## 8. Điều gì xảy ra với Lookup trả về?

Quyền của lookup trả về phụ thuộc việc caller và target có cùng module hay không.

| Trường hợp | Lookup trả về |
| --- | --- |
| Target cùng module với caller | Lookup trên target có full privilege access. |
| Target ở module khác, các điều kiện readability và opens đều đạt | Lookup trên target có private access, nhưng không có mode `MODULE`; nó ghi nhớ lookup class ban đầu làm previous lookup class. |

### 8.1. Cross-module lookup bị mất MODULE mode

Khi `M1 != M2`, lookup trả về không còn `MODULE` access. Điều này có ý nghĩa bảo mật: một lookup đã được chuyển sang module khác không thể tiếp tục dùng như lookup gốc để xin quyền deep reflection vào một module thứ ba.

Ví dụ:

~~~java
Lookup original = MethodHandles.lookup();

Lookup targetLookup =
    MethodHandles.privateLookupIn(Target.class, original);

System.out.println(targetLookup.lookupClass());
System.out.println(targetLookup.lookupModes());
System.out.println(targetLookup.hasFullPrivilegeAccess());
~~~

Nếu `Target` ở module khác, `lookupClass()` là `Target.class`; lookup có private access nhưng `hasFullPrivilegeAccess()` trả `false` vì không còn module access.

### 8.2. Không thể dùng lookup cross-module làm caller để tiếp tục privateLookupIn tùy ý

Vì lookup cross-module đã mất `MODULE` mode, nó không đáp ứng điều kiện full privilege access của lần gọi `privateLookupIn` tiếp theo.

Nếu framework cần truy cập private trong nhiều module khác nhau, mỗi lần cần dùng một lookup gốc có full privilege access thuộc module caller thích hợp, và module đích phải mở package cho module đó. Không nên chuyền một lookup cross-module rồi kỳ vọng nó có thể cấp quyền lan truyền sang module bất kỳ.

### 8.3. Kiểm tra lookup mode trong thực tế

~~~java
static void printLookupInfo(MethodHandles.Lookup lookup) {
    System.out.println("Lookup class: " + lookup.lookupClass().getName());
    System.out.println("Modes: " + lookup.lookupModes());
    System.out.println(
        "Full privilege: " + lookup.hasFullPrivilegeAccess()
    );
}
~~~

Hãy dùng các thông tin này khi debug quyền truy cập. Một lookup có thể tạo method handle cho một số thành viên nhưng không đủ quyền để thực hiện một lần chuyển lookup khác.

## 9. Kiểm tra module và package bằng API Module

Java cung cấp API runtime để kiểm tra quan hệ module:

~~~java
Module callerModule = Inspector.class.getModule();
Module targetModule = Secret.class.getModule();
String targetPackage = Secret.class.getPackageName();

System.out.println("Caller reads target: "
    + callerModule.canRead(targetModule));

System.out.println("Target opens package to caller: "
    + targetModule.isOpen(targetPackage, callerModule));

System.out.println("Target exports package to caller: "
    + targetModule.isExported(targetPackage, callerModule));
~~~

Các phép kiểm tra này giúp tìm nguyên nhân cấu hình:

- `canRead` kiểm tra readability.
- `isOpen(package, otherModule)` kiểm tra package có được mở cho module caller hay không.
- `isExported(package, otherModule)` kiểm tra package có được export cho module caller hay không.

Lưu ý: package đã mở cho module khác được xem là exported cho module đó ở runtime theo hợp đồng của `Module.isExported`. Tuy nhiên, điều này không có nghĩa directive `opens` và `exports` giống nhau về mục đích trong module descriptor.

## 10. privateLookupIn và Core Reflection

`privateLookupIn` thuộc API Method Handles. Nó không phải phương thức thay thế cú pháp cho `Field.setAccessible(true)` hoặc `Method.setAccessible(true)` trong mọi trường hợp.

| Cơ chế | Đầu ra | Cách dùng |
| --- | --- | --- |
| Core Reflection: `Field`, `Method`, `Constructor` | Đối tượng reflection đại diện member | Gọi `trySetAccessible()`/`setAccessible(true)` khi được phép, rồi dùng `get`, `set`, `invoke` hoặc `newInstance` tương ứng. |
| Method Handles: `privateLookupIn` | Một `Lookup` có quyền trên target | Tạo `MethodHandle` hoặc `VarHandle` cho thao tác cụ thể. |

Cả hai cơ chế đều chịu kiểm soát module khi truy cập sâu qua ranh giới module. `opens` là điều kiện quan trọng cho deep reflection; việc chỉ export package không tự cấp quyền truy cập private.

Method Handles phù hợp khi muốn tạo một handle có kiểu rõ ràng và tái sử dụng nó. Core Reflection phù hợp khi cần thao tác với metadata reflection truyền thống. Không nên dùng một API chỉ vì nghĩ nó vượt qua được module system.

## 11. Lỗi thường gặp và cách chẩn đoán

### 11.1. IllegalAccessException khi gọi privateLookupIn

Nguyên nhân thường gặp:

- Caller lookup thiếu `PRIVATE`.
- Caller lookup thiếu `MODULE`.
- Module caller không đọc module target.
- Module target không mở package chứa target class cho module caller.

Kiểm tra:

~~~java
Lookup caller = MethodHandles.lookup();
Module source = caller.lookupClass().getModule();
Module target = Target.class.getModule();
String packageName = Target.class.getPackageName();

System.out.println(caller.hasFullPrivilegeAccess());
System.out.println(source.canRead(target));
System.out.println(target.isOpen(packageName, source));
~~~

Nếu target cùng module với caller, không cần điều kiện đọc/mở xuyên module; hãy tập trung kiểm tra full privilege access và target class hợp lệ.

### 11.2. Module đọc được nhưng package chưa mở

Ví dụ module framework có:

~~~java
requires com.example.model;
~~~

nhưng module model chỉ có:

~~~java
exports com.example.model.domain to com.example.framework;
~~~

Framework có thể dùng public API của package, nhưng không thể dùng `privateLookupIn` để truy cập field/method private trong package đó. Cần thêm:

~~~java
opens com.example.model.domain to com.example.framework;
~~~

hoặc cấp opens phù hợp qua launcher khi cần cấu hình runtime tạm thời.

### 11.3. Lookup lấy từ publicLookup

Đoạn sau không đáp ứng điều kiện:

~~~java
Lookup caller = MethodHandles.publicLookup();
Lookup privateLookup =
    MethodHandles.privateLookupIn(Target.class, caller);
~~~

`publicLookup` chỉ có quyền public tối thiểu. Hãy tạo lookup gốc trong lớp caller đáng tin cậy bằng `MethodHandles.lookup()`.

### 11.4. Dùng Lookup.in và mong có private access

~~~java
Lookup lookup = MethodHandles.lookup().in(Target.class);
~~~

Đây không phải deep-reflection request. `in` không nâng quyền; nó có thể làm mất access mode khi lookup class đổi package, nest hoặc module.

### 11.5. Package mở nhầm module

Directive:

~~~java
opens com.example.model.internal to com.example.other;
~~~

không mở package cho `com.example.framework`. Tên module đích phải trùng với module chứa lookup class thực tế. Nếu framework được chia thành nhiều module hoặc lookup được tạo trong module helper, hãy kiểm tra đúng module sở hữu lookup.

### 11.6. Target class không thể truy cập từ source

Một package chỉ có `opens` nhưng không `exports` không cho phép mã ở module khác import public class trong package đó như API thông thường. Nếu code caller cần viết `Target.class`, package cũng phải được export phù hợp; nếu không, cần nhận class qua một cơ chế nạp/tra cứu khác được thiết kế rõ ràng.

## 12. Bảng tổng hợp điều kiện truy cập

| Caller lookup | Quan hệ module | Readability | Package opens | Kết quả |
| --- | --- | --- | --- | --- |
| Có PRIVATE + MODULE | Cùng module | Không cần kiểm tra xuyên module | Không cần mở riêng | Có thể tạo private lookup. |
| Có PRIVATE + MODULE | Khác module | Có | Có cho đúng caller module | Có thể tạo private lookup. |
| Có PRIVATE + MODULE | Khác module | Không | Có | Thất bại: thiếu readability. |
| Có PRIVATE + MODULE | Khác module | Có | Không | Thất bại: package chưa mở. |
| Chỉ có PUBLIC | Cùng module hoặc khác module | Bất kỳ | Bất kỳ | Thất bại: caller lookup thiếu full privilege access. |
| Có PRIVATE nhưng thiếu MODULE | Khác module | Có | Có | Thất bại: caller lookup thiếu full privilege access. |

Khi hai module khác nhau, phải thỏa **đồng thời** readability và package openness. Không có một điều kiện nào tự thay thế điều kiện còn lại.

## 13. Khi nào dùng opens, khi nào dùng exports?

| Nhu cầu | Directive phù hợp |
| --- | --- |
| Module khác cần dùng public class/public member trong package | `exports` |
| Framework cần truy cập private field/method bằng reflection hoặc Method Handles | `opens` |
| Cần cả import public type và deep reflection vào private member | `exports` và `opens` |
| Chỉ một framework được phép deep reflection | Qualified `opens package to framework.module` |
| Framework chạy trên class path, thuộc unnamed module | Có thể dùng `opens` cho unnamed module hoặc `--add-opens ...=ALL-UNNAMED` |
| Tất cả package của module cần mở cho reflection | `open module`, chỉ khi thực sự cần phạm vi rộng đó |

Hãy ưu tiên mở đúng package và đúng module tiêu thụ. Mở cả module hoặc dùng `ALL-UNNAMED` có thể cấp quyền cho nhiều mã hơn phạm vi cần thiết.

## 14. Ví dụ cấu hình launcher khi module đích không do mình quản lý

Giả sử thư viện `com.vendor.model` chứa package `com.vendor.model.internal`. Ứng dụng module `com.example.app` cần truy cập private member trong package đó.

Nếu ứng dụng đã khai báo:

~~~java
module com.example.app {
    requires com.vendor.model;
}
~~~

Có thể thử cấp opens lúc chạy:

~~~shell
java --add-opens com.vendor.model/com.vendor.model.internal=com.example.app --module-path "mods;lib" -m com.example.app/com.example.app.Main
~~~

Nếu ứng dụng chạy trên class path:

~~~shell
java --add-opens com.vendor.model/com.vendor.model.internal=ALL-UNNAMED -cp "app.jar;lib/*" com.example.app.Main
~~~

Đây là cách cấu hình runtime cho một package cụ thể. Hãy ghi nhận rõ thư viện nào cần quyền đó, vì việc phụ thuộc vào private internals của thư viện có thể gây rủi ro khi thư viện nâng phiên bản.

Nếu lỗi thực tế là thiếu readability trong một named module và không thể sửa module descriptor, có thể cân nhắc `--add-reads caller=target` trong giai đoạn chuyển đổi. Tuy nhiên, nếu ứng dụng do mình kiểm soát, khai báo `requires` trong module descriptor thường thể hiện dependency rõ ràng và dễ bảo trì hơn.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ khai báo `requires` rồi gọi `privateLookupIn` | Readability không tự mở package. | Thêm qualified `opens` ở module đích. |
| Chỉ khai báo `exports` | Export cho public API, không cấp deep reflection vào private member. | Dùng `opens` cho package cần truy cập sâu. |
| Dùng `publicLookup()` làm caller | Thiếu PRIVATE và MODULE mode. | Lấy lookup gốc trong lớp caller bằng `MethodHandles.lookup()`. |
| Dùng `Lookup.in` để xin quyền private | `in` không nâng quyền lookup. | Dùng `privateLookupIn` khi đáp ứng đầy đủ điều kiện. |
| Mở package cho sai module | Target module mở nhầm consumer module. | Mở package cho module chứa lookup class thực tế. |
| Mở cả module chỉ vì một package | Phạm vi deep reflection quá rộng. | Dùng qualified `opens` cho package cụ thể. |
| Nghĩ mở package cho phép import public class | `opens` là quyền deep reflection runtime. | Export package nếu source code cần tham chiếu public type. |
| Dùng lookup cross-module để tiếp tục mở module thứ ba | Lookup trả về không còn MODULE mode. | Tạo lookup gốc phù hợp từ module caller có full privilege. |
| Chia sẻ lookup private cho mọi plugin | Lookup là capability có thể tạo handle truy cập private. | Chỉ cấp cho code đáng tin cậy và giới hạn API được chia sẻ. |
| Bỏ qua IllegalAccessException | Lỗi phản ánh thiếu quyền thực sự. | Kiểm tra full privilege, canRead và isOpen. |

## 16. Câu hỏi thường gặp

**`privateLookupIn` có từ Java mấy?**  
API có từ Java 9 và được dùng bình thường trong Java 17.

**Có cần cả `requires` và `opens` không?**  
Khi caller và target ở hai named module khác nhau, cần cả readability từ caller tới target và opens từ target tới caller. `requires` thường tạo readability; `opens` cho phép deep reflection.

**`exports` có đủ để đọc private field không?**  
Không. `exports` cho truy cập thông thường tới public API; truy cập private cần package được mở cho caller.

**Có thể gọi privateLookupIn với `publicLookup()` không?**  
Không. Caller lookup phải có cả `PRIVATE` và `MODULE` access.

**Target class có cần public không?**  
Bản thân `privateLookupIn` không yêu cầu target class phải là public theo điều kiện module được mô tả. Tuy nhiên, nếu caller muốn tham chiếu trực tiếp `Target.class` trong source code của module khác, package/type phải truy cập được ở thời điểm biên dịch, thường thông qua `exports`. Nếu package chỉ mở, cần một cơ chế lấy `Class<?>` phù hợp khác.

**Nếu hai lớp nằm trong cùng module thì có cần opens không?**  
Không cần opens xuyên module. Caller lookup vẫn phải có full privilege access.

**Lookup trả về có thể tiếp tục gọi privateLookupIn cho module khác không?**  
Lookup tạo ra khi chuyển xuyên module không có `MODULE` mode, nên không đủ điều kiện làm caller cho một lần `privateLookupIn` khác.

**`--add-opens` có sửa được thiếu `requires` không?**  
Không. `--add-opens` mở package; readability là điều kiện riêng. Với named module, cần quan hệ đọc tương ứng.

**Có nên mở toàn bộ module bằng `open module` không?**  
Chỉ khi thiết kế thực sự cần deep reflection tới tất cả package. Thông thường nên dùng qualified opens cho đúng package và đúng module tiêu thụ.

**`privateLookupIn` có tự gọi method private không?**  
Không. Nó tạo `Lookup` có quyền. Sau đó cần dùng lookup để tạo `MethodHandle` hoặc `VarHandle` rồi mới gọi/đọc/ghi.

## 17. Tài liệu tham khảo chính thức

- [Java SE 17 API — MethodHandles.privateLookupIn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)): điều kiện full privilege, readability, opens và access mode của lookup trả về.
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup modes, full privilege access, cross-module lookup và các phương thức tạo method handle.
- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isOpen`, `isExported`, `addOpens` và quan hệ giữa module.
- [Java SE 17 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): mô tả `requires`, `exports`, `opens` và open module.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): thiết kế hệ thống module, exports, opens và quyền truy cập xuyên module.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): bối cảnh strong encapsulation áp dụng trong Java 17.
- [The java Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp launcher cho `--add-opens` và `--add-reads`.

**Nguyên tắc áp dụng:** Dùng `MethodHandles.privateLookupIn` khi thật sự cần tạo method handle hoặc var handle truy cập private. Caller lookup phải có `PRIVATE` và `MODULE`; nếu target ở module khác, caller phải đọc module đó và package target phải được mở cho caller. Dùng qualified `opens` để giới hạn quyền, và chỉ thêm `exports` khi caller cần truy cập public type theo cách thông thường.
