# IllegalAccessError, IllegalAccessException và InaccessibleObjectException

Khi nâng JDK, nâng phiên bản framework hoặc chuyển ứng dụng sang Java Platform Module System (JPMS), một trong những nhóm lỗi dễ gây nhầm lẫn nhất là **lỗi truy cập**. Trong log có thể xuất hiện ba tên rất giống nhau:

- `java.lang.IllegalAccessError`
- `java.lang.IllegalAccessException`
- `java.lang.reflect.InaccessibleObjectException`

Cả ba đều liên quan đến việc mã đang cố truy cập class, field, method hoặc constructor mà Java không cho phép trong ngữ cảnh hiện tại. Tuy nhiên, **chúng xuất hiện ở những tầng khác nhau**, có cơ chế phát sinh khác nhau và yêu cầu cách sửa khác nhau. Thêm nhầm `--add-opens` vào một lỗi linkage, hoặc thêm `--add-exports` vào lỗi deep reflection, thường không giải quyết được vấn đề.

Bài học thuộc chương **Chẩn đoán lỗi** của module **Java Advance Compatibility Migration**. Trọng tâm là nhận diện chính xác exception/error, hiểu quy tắc Java access control và JPMS, tạo ví dụ có thể tái hiện, tìm nguyên nhân ở compile/runtime/module path và sửa vấn đề theo hướng bền vững thay vì tích lũy JVM flags.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt `Error`, checked `Exception` và unchecked `RuntimeException` trong ba trường hợp truy cập.
2. Giải thích điểm khác nhau giữa **truy cập bytecode thông thường**, **reflection kiểm tra quyền thông thường** và **deep reflection**.
3. Xác định tình huống `IllegalAccessError` do binary incompatibility hoặc package chưa được export trong JPMS.
4. Phân tích `IllegalAccessException` khi gọi `Method.invoke`, `Field.get/set` hoặc `Constructor.newInstance`.
5. Phân tích `InaccessibleObjectException` khi `setAccessible(true)` bị JPMS từ chối.
6. Chọn đúng `requires`, `exports`, `opens`, `--add-exports` hoặc `--add-opens`.
7. Tái hiện lỗi bằng một ví dụ tự quản lý module, tránh phụ thuộc vào API nội bộ JDK có thể thay đổi.
8. Kiểm tra classpath, module path, JAR thực sự được nạp, test JVM và môi trường production.
9. Xây dựng checklist chẩn đoán và quy trình xác minh sau migration.

## 2. Nhận diện nhanh ba lỗi

| Dấu hiệu | `IllegalAccessError` | `IllegalAccessException` | `InaccessibleObjectException` |
| --- | --- | --- | --- |
| Thuộc nhóm | `Error` → `LinkageError` | Checked `Exception` → `ReflectiveOperationException` | Unchecked `RuntimeException` |
| Xuất hiện điển hình | JVM liên kết hoặc thực thi truy cập bytecode không hợp lệ | Reflection thử truy cập member nhưng access checks không cho phép | Reflection cố **bỏ qua** kiểm tra quyền bằng `setAccessible(true)` nhưng không được phép |
| API/đường chạy | Lời gọi, tham chiếu field/class thông thường; truy cập module | `Method.invoke`, `Field.get`, `Field.set`, `Constructor.newInstance` | `AccessibleObject.setAccessible` hoặc thao tác tương ứng |
| Ví dụ nguyên nhân | Method v1 `public` trở thành không public ở v2; module không export package | Gọi `private` method qua reflection mà chưa bật access override | Module đích không open package cho module gọi |
| Có thể catch? | Về kỹ thuật có, nhưng không nên xem như business exception | Phải catch hoặc khai báo `throws` | Có thể catch như runtime exception |
| Hướng xử lý thường đúng | Khôi phục binary/API compatibility, đồng bộ JAR, sửa `exports` hoặc runtime flags cần thiết | Dùng public API hoặc truy cập reflection hợp lệ; nếu được phép thì `setAccessible` | Dùng public API, nâng framework, thêm `opens` hoặc `--add-opens` đúng phạm vi |
| Có mặt từ | Java đời đầu | Java đời đầu | Java 9, cùng sự ra đời của JPMS |

**Quy tắc đầu tiên:** đọc **tên exception chính xác và stack trace**. Đừng gộp tất cả thành “Java 17 không cho reflection”. `IllegalAccessError` có thể xuất hiện hoàn toàn không liên quan đến reflection; `IllegalAccessException` có thể xuất hiện trên Java 8; `InaccessibleObjectException` có liên hệ trực tiếp đến khả năng suppress Java language access checks ở runtime, thường gặp trong bối cảnh module encapsulation.

## 3. Các tầng truy cập trong Java

### 3.1. Quy tắc truy cập của ngôn ngữ Java

Java áp dụng các mức truy cập:

- `public`: member/type được truy cập trong phạm vi hợp lệ theo quy tắc ngôn ngữ và module system.
- `protected`: thêm điều kiện về package và subclass, với các quy tắc cụ thể cho receiver và thành viên.
- *package-private*: không khai báo modifier, chỉ trong package theo quy tắc Java.
- `private`: phạm vi truy cập bị hạn chế trong cấu trúc khai báo tương ứng.

Ví dụ:

```java
package com.example.model;

public final class Account {
    public String id() {
        return "A-100";
    }

    private String token() {
        return "secret";
    }
}
```

Mã ngoài class có thể gọi `id()` nếu type visible, nhưng không thể gọi trực tiếp `token()`. Việc class là `public` **không làm mọi member bên trong tự động public**.

### 3.2. JPMS thêm ranh giới ở cấp module và package

Từ Java 9, các named modules có thể khai báo descriptor:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Nếu một module khác muốn tham chiếu type `public` trong package `com.example.library.api` theo cách thông thường, cần xét:

1. **Readability:** module gọi có đọc được module chứa type không? Thường được thể hiện bằng `requires`.
2. **Exports:** package chứa type có được export tới module gọi không?
3. **Java access control:** type/member có visibility cho phép lời gọi cụ thể không?

Sơ đồ tư duy:

```text
Caller module đọc được target module?
         |
         +-- Không --> readability / module graph
         |
         +-- Có
              |
              v
Package được export tới caller?
         |
         +-- Không --> JPMS package access
         |
         +-- Có
              |
              v
Class/member có mức truy cập phù hợp?
         |
         +-- Không --> Java access checks
         |
         +-- Có ----> ordinary access hợp lệ
```

**`requires` không có nghĩa mọi package đều visible. `exports` không có nghĩa mọi field/method `private` đều trở thành public.**

### 3.3. Reflection thông thường và reflection sâu khác nhau

Reflection cho phép tra cứu class và member ở runtime:

```java
Class<?> type = Class.forName("com.example.model.Account");
Method method = type.getDeclaredMethod("token");
```

`getDeclaredMethod` có thể tìm một method không public. Nhưng việc **tìm metadata** khác việc **được phép gọi method**.

Khi gọi:

```java
method.invoke(account);
```

reflection kiểm tra quyền truy cập. Nếu không được phép, thường phát sinh `IllegalAccessException`.

Nếu mã tiếp tục:

```java
method.setAccessible(true);
method.invoke(account);
```

thì nó đang yêu cầu **suppress Java language access checks**. Từ Java 9, yêu cầu này chịu quy tắc JPMS. Nếu module đích không open package cho module thực hiện reflection, lệnh `setAccessible(true)` có thể phát sinh `InaccessibleObjectException`.

### 3.4. Bản chất của `exports` và `opens`

| Khai báo/cờ | Mục tiêu |
| --- | --- |
| `requires m` | Cho module gọi đọc module m theo quy tắc JPMS. |
| `exports p` | Cho các module có readability phù hợp truy cập public types/members của package p theo cách thông thường. |
| `exports p to x` | Export package p có giới hạn tới module x. |
| `opens p` | Open package p cho deep reflection từ các module khác. |
| `opens p to x` | Open package p chỉ cho deep reflection từ module x. |
| `--add-exports m/p=x` | Bổ sung export cho một lần compile/chạy theo cách công cụ hỗ trợ. |
| `--add-opens m/p=x` | Bổ sung quyền open package ở runtime cho deep reflection. |
| `--add-reads m=x` | Bổ sung quan hệ readability trong trường hợp cần thiết. |

`exports` chủ yếu xử lý **ordinary access**. `opens` xử lý **deep reflection**. Chúng không phải các từ đồng nghĩa.

## 4. `IllegalAccessError`: JVM từ chối một tham chiếu bytecode

### 4.1. Thuộc họ `LinkageError`

`IllegalAccessError` nằm dưới `IncompatibleClassChangeError` và `LinkageError`. Đây là dấu hiệu code đã được biên dịch nhưng ở runtime JVM không thể thực hiện một tham chiếu truy cập vì **quy tắc access tại thời điểm liên kết/thực thi không còn được thỏa mãn**.

Ví dụ thông báo có dạng:

```text
java.lang.IllegalAccessError:
  class com.example.client.Main cannot access class
  com.example.internal.HiddenApi
  (in module com.example.core)
  because module com.example.core does not export
  com.example.internal to module com.example.client
```

Đây là một ví dụ về lỗi truy cập package của named module ở runtime.

### 4.2. Kịch bản khác: API cũ public, API mới hạn chế truy cập

Giả sử library v1 cung cấp:

```java
package com.example.api;

public class AccountService {
    public void synchronize() {
        // Implementation v1
    }
}
```

Consumer được compile với v1:

```java
new AccountService().synchronize();
```

Đến library v2, tác giả đổi:

```java
package com.example.api;

public class AccountService {
    void synchronize() {
        // Method đã bị đổi thành package-private.
    }
}
```

Nếu **recompile consumer** với v2, `javac` thường báo lỗi ngay do method không visible.

Nếu không recompile consumer mà chỉ thay JAR library ở runtime, bytecode consumer vẫn mang tham chiếu đã được compile khi method còn public. Khi JVM thực hiện lời gọi với library v2, nó có thể ném `IllegalAccessError`.

**Điểm quan trọng:** `IllegalAccessError` thường là triệu chứng của **binary incompatibility** hoặc sự khác biệt giữa môi trường compile và runtime, không chỉ là “thiếu quyền reflection”.

### 4.3. Những nguyên nhân thường gặp

- Class/method/field từng `public` hoặc `protected` nay có access hẹp hơn.
- JAR compile khác JAR được nạp lúc chạy, thường do dependency conflict.
- Class nằm trong package không còn được export sau khi module hóa.
- Compile được phép dùng `--add-exports`, nhưng runtime không có quyền export tương ứng.
- Module descriptor bị thay đổi giữa bản library mà client biên dịch và bản đang chạy.
- Class-loader/application-server đưa vào phiên bản dependency khác bản được kỳ vọng.

### 4.4. Vì sao không nên catch để bỏ qua?

Về mặt ngôn ngữ, có thể catch một `Error`. Nhưng `IllegalAccessError` báo hiệu một ranh giới liên kết hoặc truy cập của chương trình đã bị vi phạm. Việc bắt và bỏ qua nó không sửa classpath, binary signature hay module graph.

Ví dụ không nên dùng:

```java
try {
    service.synchronize();
} catch (IllegalAccessError ignored) {
    // Bỏ qua để application tiếp tục.
}
```

Một đường đi nghiệp vụ có thể còn nhiều tham chiếu không tương thích khác. Hãy sửa artifact/configuration/API thay vì dùng `catch` như workaround production.

## 5. Tái hiện `IllegalAccessError` bằng hai named modules

Để không phụ thuộc vào class nội bộ của JDK, ta tự tạo hai module. Ví dụ này sử dụng Java 9+.

### 5.1. Cấu trúc project

```text
demo-access/
├── src/
│   ├── com.example.core/
│   │   ├── module-info.java
│   │   └── com/example/internal/HiddenApi.java
│   └── com.example.client/
│       ├── module-info.java
│       └── com/example/client/DirectClient.java
└── mods/
```

Module nguồn:

```java
// src/com.example.core/module-info.java
module com.example.core {
    // Cố ý không export com.example.internal.
}
```

```java
// src/com.example.core/com/example/internal/HiddenApi.java
package com.example.internal;

public final class HiddenApi {
    private HiddenApi() {}

    public static String message() {
        return "Ordinary call";
    }

    private static String secret = "Hidden data";
}
```

Module client:

```java
// src/com.example.client/module-info.java
module com.example.client {
    requires com.example.core;
}
```

```java
// src/com.example.client/com/example/client/DirectClient.java
package com.example.client;

import com.example.internal.HiddenApi;

public final class DirectClient {
    public static void main(String[] args) {
        System.out.println(HiddenApi.message());
    }
}
```

### 5.2. Biên dịch module nguồn

```bash
javac -d mods/com.example.core \
  src/com.example.core/module-info.java \
  src/com.example.core/com/example/internal/HiddenApi.java
```

Nếu biên dịch client **không** có export phù hợp, compiler sẽ báo package `com.example.internal` không được export cho module client.

### 5.3. Biên dịch client với qualified export bổ sung

```bash
javac \
  --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/DirectClient.java
```

Cờ `--add-exports` giúp compiler chấp nhận lời gọi public API trong một package chưa được export qua descriptor.

Lưu ý: đây là cách **cố tình tạo cấu hình compile/runtime khác nhau để học cơ chế lỗi**, không phải một kiến trúc được khuyến khích.

### 5.4. Chạy thiếu export ở runtime

```bash
java --module-path mods \
  -m com.example.client/com.example.client.DirectClient
```

Khi JVM thực hiện lời gọi, có thể xuất hiện `IllegalAccessError` vì `com.example.core` chưa export package cho `com.example.client` ở runtime.

### 5.5. Chạy với export runtime phù hợp

```bash
java --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.DirectClient
```

Lời gọi `HiddenApi.message()` có thể thành công.

**Bài học rút ra:** option của `javac` không tự được lưu thành quyền export cho mọi lần chạy tương lai. Nếu dự án đang phụ thuộc vào cờ, cần cấu hình và xác minh **cả môi trường compile lẫn runtime**; nếu sở hữu source module đích, tốt hơn hãy thiết kế API public rõ ràng và khai báo `exports` phù hợp.

## 6. `IllegalAccessException`: reflection không được truy cập member

### 6.1. Đây là checked exception

`java.lang.IllegalAccessException` kế thừa `ReflectiveOperationException`. Những API reflection như `Method.invoke`, `Field.get`, `Field.set` và `Constructor.newInstance` có thể ném exception này khi caller không có quyền truy cập member theo quy tắc thông thường, trong khi access checks chưa được suppress hợp lệ.

Ví dụ:

```java
import java.lang.reflect.Method;

final class SecretBox {
    private String readSecret() {
        return "42";
    }
}

public class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        SecretBox box = new SecretBox();
        Method method =
                SecretBox.class.getDeclaredMethod("readSecret");

        // Method là private; caller ngoài SecretBox.
        Object result = method.invoke(box);
        System.out.println(result);
    }
}
```

Nếu không có access override hợp lệ, `method.invoke(box)` sẽ ném `IllegalAccessException`.

Ở đây, code không cần dùng JPMS. Một chương trình classpath bình thường cũng có thể gặp lỗi này.

### 6.2. Tìm được method không có nghĩa gọi được method

Hai API khác nhau:

- `getMethod(name, ...)` tra cứu public method theo quy tắc reflection.
- `getDeclaredMethod(name, ...)` tra cứu method khai báo trực tiếp trên class, bao gồm non-public methods.

Sau khi lấy được `Method`, lời gọi `invoke` vẫn cần quyền truy cập phù hợp.

Tương tự:

- `Class.getDeclaredField` có thể tìm private field.
- `Field.get` có thể từ chối đọc field nếu chưa được phép.
- `Class.getDeclaredConstructor` có thể tìm private constructor.
- `Constructor.newInstance` có thể ném `IllegalAccessException` nếu quyền truy cập không hợp lệ.

**Metadata discovery**, **access checks** và **thực thi method** là ba bước khác nhau.

### 6.3. `setAccessible(true)` có thể hợp lệ trong một số trường hợp

Nếu mã chạy trong một cấu hình mà Java cho phép suppress checks, ví dụ class và caller ở unnamed module/classpath và không có ràng buộc bảo mật bổ sung, có thể dùng:

```java
Method method =
        SecretBox.class.getDeclaredMethod("readSecret");

method.setAccessible(true);
Object result = method.invoke(new SecretBox());
```

Điều này không có nghĩa `setAccessible(true)` **luôn** hoạt động. Khi member thuộc package của named module khác chưa open cho caller, chính thao tác `setAccessible(true)` có thể ném `InaccessibleObjectException`.

### 6.4. Không đánh đồng với `InvocationTargetException`

Nếu `Method.invoke` **được phép gọi** method, nhưng bản thân method ném exception, reflection thường đóng gói throwable do target ném trong `InvocationTargetException`.

Ví dụ:

```java
public void fail() {
    throw new IllegalStateException("Business failure");
}
```

Gọi method này qua reflection có thể nhận `InvocationTargetException` với `getCause()` là `IllegalStateException`.

Đây **không phải** lỗi quyền truy cập reflection. Khi điều tra, đọc cả cause chain để tránh nhầm lỗi logic nghiệp vụ với `IllegalAccessException`.

### 6.5. Các nguyên nhân thường gặp

- Method/field/constructor không public; framework cố gọi mà chưa bật access override.
- Class khai báo không visible theo ngữ cảnh caller.
- Caller và target ở module/package khác nhau với access checks không thỏa mãn.
- Một framework cũ chọn API reflection không phù hợp với visibility hiện tại.
- Class loader/proxy làm thay đổi type thực tế được thao tác, trong khi code cho rằng member đang public.

Cách sửa ưu tiên: sử dụng public API được hỗ trợ, constructor/factory method thích hợp hoặc thay framework bằng phiên bản hiểu quy tắc access của JDK đích.

## 7. `InaccessibleObjectException`: không được bật deep reflection

### 7.1. Exception xuất hiện từ Java 9

`java.lang.reflect.InaccessibleObjectException` được thêm từ Java 9 cùng sự ra đời của JPMS. Đây là một unchecked exception, thường phát sinh khi code yêu cầu:

```java
accessibleObject.setAccessible(true);
```

nhưng Java không cho phép suppress language access checks trên member đó.

Thông báo điển hình:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make private ... accessible:
  module java.base does not "opens java.lang" to unnamed module ...
```

Câu quan trọng trong thông báo là **`does not "opens"`**, vì nó chỉ ra một ranh giới deep reflection giữa module chứa member và module thực hiện reflection.

### 7.2. Ví dụ ngắn với lớp thuộc JDK

Trên các JDK có field nội bộ tương ứng, một đoạn mã như sau có thể gặp lỗi:

```java
import java.lang.reflect.Field;

public class JdkReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true); // Có thể bị từ chối.
    }
}
```

Trên Java 17+ theo cấu hình mặc định phổ biến, package `java.lang` của module `java.base` không được mở deep reflection cho code classpath, nên lệnh `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Ví dụ này **chỉ để minh họa loại lỗi**. Field nội bộ của `String` không phải API được Java SE bảo đảm giữ nguyên ở mọi phiên bản. Trong dự án thật, không nên đọc hoặc sửa field nội bộ của `String` để giải quyết công việc nghiệp vụ.

### 7.3. Vì sao `--add-exports` thường không sửa được lỗi này?

Giả sử một framework muốn đọc field `private` bằng reflection. Export package để code bên ngoài thấy các kiểu public **không đủ** để cho phép truy cập member private.

Ví dụ:

```bash
java --add-exports java.base/java.lang=ALL-UNNAMED \
  JdkReflectionDemo
```

Cờ trên **không thay thế** quyền open cho deep reflection. Khi root cause là `setAccessible(true)` vào package không open, cần xem `opens` hoặc `--add-opens`.

Đây không phải khuyến nghị mở `java.lang` trong production; đó chỉ là ví dụ cho sự khác biệt về cơ chế.

### 7.4. `trySetAccessible()` và `canAccess()`

Từ Java 9, API reflection có:

- `trySetAccessible()`: thử bật access override; có thể trả về `false` nếu không thể bật do hạn chế truy cập/module.
- `canAccess(receiver)`: kiểm tra trong ngữ cảnh hiện tại caller có truy cập member với receiver tương ứng hay không.

Ví dụ:

```java
import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");

        if (!field.trySetAccessible()) {
            System.out.println("Không thể mở deep reflection");
            return;
        }

        // Không được phụ thuộc vào implementation detail của String.
        System.out.println("Accessible override đã được bật");
    }
}
```

`trySetAccessible()` giúp phản ứng có kiểm soát thay vì luôn ném `InaccessibleObjectException`. Nhưng nó **không cấp quyền mới**, và những kiểm tra bảo mật hoặc điều kiện khác vẫn có thể gây exception thích hợp.

Nếu framework yêu cầu truy cập nội bộ, hướng bền vững là cập nhật thư viện hoặc thiết kế API. Không sử dụng `trySetAccessible()` như cách lách policy JPMS.

## 8. Tái hiện `InaccessibleObjectException` bằng module của chính dự án

Ví dụ này dùng module `com.example.core` ở mục trước. Trong class `HiddenApi` có private static field `secret`.

### 8.1. Reflection client không import hidden package

Thêm một class khác vào module client:

```java
// src/com.example.client/com/example/client/ReflectionClient.java
package com.example.client;

import java.lang.reflect.Field;

public final class ReflectionClient {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "com.example.internal.HiddenApi");

        Field field = type.getDeclaredField("secret");
        field.setAccessible(true);

        System.out.println(field.get(null));
    }
}
```

Do code không import `HiddenApi` ở source level, compiler có thể biên dịch `ReflectionClient` mà không cần export package nội bộ. Module client đã `requires com.example.core`, giúp module core hiện diện trong module graph.

### 8.2. Biên dịch reflection client

```bash
javac --module-path mods \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/ReflectionClient.java
```

Đây là một ví dụ độc lập với `DirectClient`. Nếu dùng chung output directory trong một bài thực hành, bảo đảm đã build được module core và lựa chọn source cần compile nhất quán.

### 8.3. Chạy không có open

```bash
java --module-path mods \
  -m com.example.client/com.example.client.ReflectionClient
```

`Class.forName` có thể tìm lớp và `getDeclaredField` có thể tìm field. Nhưng khi gọi `setAccessible(true)`, JVM từ chối vì package `com.example.internal` **không được open** cho `com.example.client`.

Kết quả điển hình là `InaccessibleObjectException` với thông báo module không open package.

### 8.4. Chạy có qualified open

```bash
java --module-path mods \
  --add-opens com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.ReflectionClient
```

Lúc này deep reflection có thể đọc field `secret`.

**Bài học:** trong ví dụ này, `--add-opens` là quyền cần cho reflection sâu. Nó không biến package `com.example.internal` thành một API public mà `DirectClient` có thể import nếu thiếu export tương ứng.

### 8.5. Sửa ở nguồn module nếu bạn sở hữu nó

Nếu mục đích hợp lệ là cho một framework cụ thể dùng reflection, có thể khai báo trong descriptor:

```java
module com.example.core {
    opens com.example.internal to com.example.client;
}
```

Nếu cần ordinary access vào public API, sử dụng `exports` cho package API phù hợp:

```java
module com.example.core {
    exports com.example.api;
    opens com.example.model to com.example.serializer;
}
```

Cách này giúp định nghĩa contract rõ ràng hơn việc bổ sung JVM flags ở nhiều môi trường. Không mở một package nội bộ chỉ vì một lỗi có thể được giải quyết bằng public API.

## 9. Khi nào cùng code có thể thấy cả ba loại lỗi?

Hãy hình dung một hệ thống có hai đường đi:

1. Một service gọi trực tiếp vào class của dependency bằng bytecode.
2. Một framework serializer đọc các private fields của cùng dependency qua reflection.

Sau nâng cấp:

- Lời gọi trực tiếp có thể phát sinh `IllegalAccessError` vì class thuộc package không export ở runtime.
- Một đường reflection gọi `Method.invoke` trên member không public mà chưa override access có thể phát sinh `IllegalAccessException`.
- Serializer cố `Field.setAccessible(true)` trên private member trong package named module chưa open có thể phát sinh `InaccessibleObjectException`.

Một số lỗi có thể chỉ xuất hiện khi startup scan, một số chỉ xuất hiện khi request đầu tiên dùng tính năng đó.

**Không suy từ một lỗi đầu tiên rằng mọi lỗi access khác có cùng root cause.** Sau khi sửa một ranh giới, những ranh giới tiếp theo mới có thể được thực thi và lộ ra.

## 10. Quy trình chẩn đoán theo loại lỗi

### 10.1. Bước 1: chép lại exception class chính xác

Đọc toàn bộ stack trace, đặc biệt:

- Dòng `Caused by` sâu nhất có ý nghĩa.
- Class/module của caller.
- Class/module và package của member đích.
- Method/field/constructor đang bị truy cập.
- API đang được gọi khi lỗi phát sinh.
- Phiên bản JDK và JAR liên quan.

Một stack trace có nhiều wrapper như `BeanCreationException` hoặc `ExceptionInInitializerError`; tên wrapper không nhất thiết là root cause. Cần đi đến nguyên nhân gốc thay vì sửa framework nơi wrapper được tạo.

### 10.2. Bước 2: phân nhánh

```text
Lỗi là gì?
    |
    +-- IllegalAccessError
    |      |
    |      +--> Ordinary bytecode / linkage access?
    |                |
    |                +--> JAR v1 compile, JAR v2 runtime?
    |                +--> Member visibility đổi?
    |                +--> Module không export package?
    |
    +-- IllegalAccessException
    |      |
    |      +--> Reflection invoke/get/set/newInstance?
    |                |
    |                +--> Member private/protected/package-private?
    |                +--> Caller có access hợp lệ?
    |                +--> Có thể dùng public API hay override hợp lệ?
    |
    +-- InaccessibleObjectException
           |
           +--> setAccessible(true) bị từ chối?
                     |
                     +--> Module nguồn và package nào?
                     +--> Module gọi là named hay unnamed?
                     +--> Có opens/--add-opens phù hợp?
                     +--> Framework có phiên bản mới tránh deep reflection?
```

Đây là cây chẩn đoán ban đầu. Trường hợp thực tế còn có class-loader conflicts và các lỗi nạp lớp khác cần xem cùng.

### 10.3. Bước 3: tìm nơi truy cập thật sự xảy ra

Với `IllegalAccessError`, caller thường là class chứa bytecode tham chiếu API. Có thể class đó đến từ một dependency bắc cầu, không phải source ứng dụng.

Với `IllegalAccessException` hoặc `InaccessibleObjectException`, caller có thể là serializer, ORM, dependency injection, bytecode agent hoặc test framework. Cần xác định **module của chính mã thực hiện reflection**, không chỉ module có method `main`.

### 10.4. Bước 4: xác nhận môi trường compiler và runtime

Ghi ít nhất:

```bash
java -version
javac -version
```

Với Maven:

```bash
mvn -version
mvn dependency:tree
```

Với Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

Đừng coi các lệnh này là bằng chứng đầy đủ cho JVM chạy production. Container image, application server, test fork hoặc Maven/Gradle toolchains có thể dùng JDK khác. Cần đo **tiến trình thực sự ném lỗi**.

### 10.5. Bước 5: xác nhận class được nạp từ đâu

Nếu có nhiều JAR chứa cùng FQCN, runtime có thể nạp bản khác với bản compiler thấy.

Trong một đoạn mã chẩn đoán thích hợp:

```java
static void showOrigin(Class<?> type) {
    System.out.println("Class: " + type.getName());
    System.out.println("Module: " + type.getModule());
    System.out.println("ClassLoader: " + type.getClassLoader());

    var domain = type.getProtectionDomain();
    var source = domain == null ? null : domain.getCodeSource();

    System.out.println("CodeSource: " +
            (source == null ? "unknown" : source.getLocation()));
}
```

Thông tin `CodeSource` có thể không có trong một số loader hoặc class được sinh động. Nó chỉ là bằng chứng phụ trợ.

Ngoài ra, trong môi trường thích hợp có thể dùng logging class loading để xem nguồn class, nhưng nên bật có mục tiêu vì log có thể lớn.

### 10.6. Bước 6: kiểm tra public API và bytecode

```bash
javap -classpath path/to/library.jar \
  -p -s com.example.api.AccountService
```

`javap -p` giúp xem private/public declarations; `-s` giúp xem JVM descriptors. So kết quả giữa library v1 và v2 để tìm thay đổi chữ ký/visibility.

Lưu ý: `javap` không tự mô tả mọi quyền `exports`/`opens` của module tại runtime. Cần kiểm tra descriptor và module graph riêng.

## 11. Kiểm tra JPMS bằng các công cụ JDK

### 11.1. Xem module descriptor

Với JAR:

```bash
jar --describe-module --file path/to/library.jar
```

Với module được JDK cung cấp:

```bash
java --describe-module java.base
```

Thông tin giúp xác định module name, exports, opens, requires, uses/provides trong phạm vi công cụ thể hiện.

Nếu JAR là automatic module, tên module và cơ chế exports có thể khác explicit named module. Không mặc định tên module bằng Maven artifactId.

### 11.2. Xem module resolution

Ví dụ:

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.example.client/com.example.client.DirectClient
```

Dùng để xem những module được phân giải ở lần chạy cụ thể. Module có mặt trong module path nhưng **không được resolve** thì một số phép Class.forName/service loading có thể hành xử khác dự kiến.

### 11.3. Kiểm tra module của caller và target

Ở runtime có thể in:

```java
Module source = targetClass.getModule();
Module caller = callerClass.getModule();

System.out.println("Target module: " + source.getName());
System.out.println("Caller module: " + caller.getName());
```

Một unnamed module thường có `getName() == null`. Cần phân biệt:

- Named module từ module path.
- Automatic module.
- Unnamed module của class loader.
- Các module layers do ứng dụng tạo riêng.

Giá trị `ALL-UNNAMED` trong JVM flag dành cho các unnamed modules; nó không phải tên của một named module cụ thể.

### 11.4. `jdeps` tìm dependency trên API nội bộ

Ví dụ:

```bash
jdeps --jdk-internals path/to/application.jar
```

`jdeps` có thể phát hiện một số phụ thuộc tĩnh vào JDK internal APIs. Nó **không** đảm bảo phát hiện reflection dùng class name lấy từ cấu hình, `ServiceLoader` hoặc plugin nạp động.

Kết quả âm tính không chứng minh ứng dụng không cần sửa khi chuyển lên JDK mới.

### 11.5. Xem JVM arguments thật sự

Một cờ đặt trong IDE có thể không có ở production. Một cờ đặt vào Maven Compiler Plugin có thể không được truyền cho Surefire. Một cờ trong unit test có thể không đến integration test.

Với process Java mà bạn có quyền chẩn đoán, các lệnh như:

```bash
jcmd <pid> VM.command_line
```

có thể giúp thấy command line của tiến trình. Khả năng truy cập phụ thuộc JDK, quyền process và cấu hình hệ thống. Cần đối chiếu với script/container startup thực tế.

## 12. `--add-exports` và `--add-opens`: chọn đúng công cụ

### 12.1. `--add-exports` cho ordinary access

Cú pháp:

```text
--add-exports <source-module>/<package>=<target-module>
```

Ví dụ:

```bash
java \
  --add-exports com.example.core/com.example.internal=com.example.client \
  --module-path mods \
  -m com.example.client/com.example.client.DirectClient
```

Với code thuộc unnamed module trên classpath, target có thể là:

```text
ALL-UNNAMED
```

**Không suy rằng export package cho phép truy cập private field bằng reflection.** Nó phục vụ khả năng truy cập public types/members theo quy tắc thông thường.

### 12.2. `--add-opens` cho deep reflection

Cú pháp:

```text
--add-opens <source-module>/<package>=<target-module>
```

Ví dụ:

```bash
java \
  --add-opens com.example.core/com.example.internal=com.example.client \
  --module-path mods \
  -m com.example.client/com.example.client.ReflectionClient
```

Nếu target thực hiện reflection thuộc classpath:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar legacy-app.jar
```

Ví dụ `java.lang` chỉ minh họa cú pháp, **không khuyến nghị cấu hình này mặc định cho mọi ứng dụng**. Cần dựa trên lỗi thực tế và tài liệu của thư viện gây deep reflection.

### 12.3. Không đảo chiều source và target

Trong:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

- `java.base` là **module sở hữu package**.
- `java.lang` là **package được mở**.
- `ALL-UNNAMED` là **nhóm module được cấp quyền phản chiếu**, thường gồm code chạy trên classpath.

Nếu một framework chạy trong named module `com.example.orm`, cần xem có phải mở cho **module framework đó** hay không, thay vì mở cho module ứng dụng chỉ vì ứng dụng là điểm khởi chạy.

### 12.4. Named module vs automatic module vs unnamed module

Một legacy JAR ở classpath thường thuộc unnamed module. Nhưng nếu cùng JAR được chuyển sang module path, nó có thể trở thành automatic module và có module name.

Vì thế một cờ `--add-opens ...=ALL-UNNAMED` từng hoạt động khi framework nằm trên classpath có thể không còn nhắm đúng framework nếu đã đưa nó lên module path.

Dùng:

```bash
jar --describe-module --file path/to/framework.jar
```

và thông tin runtime `Class.getModule()` để xác định target phù hợp.

### 12.5. `--add-reads` là vấn đề khác

Nếu module caller chưa có khả năng đọc module đích, có thể cần quan hệ `requires` trong descriptor hoặc một cấu hình `--add-reads` trong tình huống chuyển tiếp.

Không dùng `--add-opens` để kỳ vọng tạo tự động quan hệ `requires` cần cho ordinary Java source import. Readability, exports và opens là các ranh giới riêng.

### 12.6. Một lỗi không nên giải quyết bằng cờ JVM vô điều kiện

Có trường hợp `IllegalAccessError` là do method từ `public` sang package-private trong **cùng một unnamed-module classpath**; không có package export nào để mở nhằm sửa visibility của method đó.

Có trường hợp `IllegalAccessException` đơn giản vì caller cố gọi private method; giải pháp phù hợp là dùng public API hoặc xử lý reflection theo contract, không phải mở `java.base`.

Có trường hợp `InaccessibleObjectException` xảy ra vì framework cổ dùng deep reflection vào JDK internals; nên nâng framework trước khi chọn workaround.

## 13. Khác biệt giữa Java 8, Java 9–16 và Java 17+

### 13.1. Java 8: chưa có JPMS

Java 8 không có `module-info.java`, `--add-opens` và `InaccessibleObjectException`. Tuy nhiên `IllegalAccessError` và `IllegalAccessException` vẫn có thể xuất hiện từ các quy tắc Java access/linkage và reflection.

Nếu một ứng dụng chạy trên Java 8 nhưng dùng reflection vào private fields của JDK, việc nâng JDK có thể khiến những thao tác ấy bị chặn bởi ranh giới mới.

### 13.2. Java 9–15: cơ chế chuyển tiếp cho một số JDK internals

Java 9 đưa vào JPMS và strong encapsulation. Một số package JDK tồn tại từ Java 8 được xử lý theo cơ chế **relaxed strong encapsulation** trong giai đoạn chuyển tiếp, có thể tạo cảnh báo “illegal reflective access”.

Tùy chọn `--illegal-access` từng ảnh hưởng đến cơ chế chuyển tiếp này. Nhưng nó không mở mọi API nội bộ, và không phải giải pháp tương thích lâu dài.

### 13.3. Java 16: strong encapsulation mặc định chặt hơn

Java 16 chuyển hướng mặc định sang đóng gói mạnh hơn. Một số mã cũ từng chạy với cảnh báo trên JDK trước có thể thất bại nếu không có giải pháp phù hợp.

### 13.4. Java 17+: JEP 403 củng cố strong encapsulation

Từ Java 17, JEP 403 củng cố strong encapsulation đối với JDK internals. Tùy chọn `--illegal-access` cũ không còn hoạt động như cơ chế mở quyền mà nhiều ứng dụng trước đây dựa vào.

Nếu thật sự cần deep reflection vào package cụ thể, có thể dùng `--add-opens` có mục tiêu; nếu cần ordinary access vào package chưa export, có thể dùng `--add-exports` phù hợp. Nhưng giải pháp bền vững vẫn là dùng API public và nâng thư viện/JDK tooling.

**Không suy rằng mọi package có tên `sun.*` hoặc `com.sun.*` giống nhau.** Một số API có trạng thái tương thích riêng, chẳng hạn những API được cung cấp qua `jdk.unsupported`; cần kiểm tra module descriptor và tài liệu của JDK đích.

### 13.5. Đừng dựa vào warning cũ để dự đoán JDK mới

Nếu một app chạy trên JDK 11 và in warning illegal reflective access, đó là tín hiệu cần điều tra **trước** khi nâng lên JDK 17/21. Việc warning chưa khiến app fail trên JDK cũ không chứng minh app sẽ tiếp tục chạy khi chính sách encapsulation chặt hơn.

## 14. Phân biệt các lỗi gần giống nhưng khác nguyên nhân

| Lỗi | Ý nghĩa phổ biến | Vì sao khác ba lỗi chính? |
| --- | --- | --- |
| `ClassNotFoundException` | Class loader không tìm thấy tên class được yêu cầu. | Vấn đề tìm lớp, không nhất thiết là access. |
| `NoClassDefFoundError` | JVM không thể tìm/định nghĩa class cần khi runtime hoặc khởi tạo class lỗi trước đó. | Phải điều tra dependency/loading/init, không chỉ module exports. |
| `NoSuchMethodError` | Binary tham chiếu method signature không có ở runtime. | Binary mismatch, không phải access của method còn tồn tại. |
| `NoSuchFieldError` | Binary tham chiếu field không có ở runtime. | Thiếu field, không phải visibility. |
| `IncompatibleClassChangeError` | Thay đổi class/interface hoặc bytecode linkage không tương thích. | Là nhóm lớn; `IllegalAccessError` thuộc nhánh này. |
| `NoSuchMethodException` | Reflection không tìm thấy method theo yêu cầu. | Lookup thất bại trước khi kiểm tra quyền invoke. |
| `InvocationTargetException` | Method/constructor được gọi qua reflection ném exception. | Lỗi từ target, không nhất thiết do quyền truy cập. |
| `SecurityException` | Truy cập bị từ chối bởi một cơ chế security liên quan. | Cần xác định cơ chế/permission, không mặc định do JPMS. |
| `ExceptionInInitializerError` | Static initializer gặp lỗi. | Có thể bọc một nguyên nhân sâu hơn; cần đọc cause. |

Đặc biệt, một exception có chứa từ “access” không có nghĩa `--add-opens` là hướng xử lý đúng. Phải phân loại theo **API đang thực hiện hành động** và **điều kiện truy cập nào bị vi phạm**.

## 15. Framework, ORM, serializer và test tools thường gặp lỗi ở đâu?

### 15.1. Dependency injection container

Một container có thể dùng reflection để gọi constructor hoặc inject field. Sau khi nâng JDK hoặc chuyển JAR sang named module, nó có thể không truy cập được private members nếu package không open.

Nếu stack trace trỏ tới `setAccessible` trong framework, ưu tiên kiểm tra version framework hỗ trợ JDK đích và cấu hình module, thay vì sửa `@Autowired`/`@Inject` một cách tùy tiện.

### 15.2. ORM và entity reflection

ORM có thể đọc field entity, tạo instance qua constructor hoặc tạo proxy. Những trường hợp thường nhạy cảm:

- Entity nằm trong named module.
- Entity package không `opens` cho ORM module.
- ORM phiên bản cũ dùng JDK internals hoặc bytecode enhancement chưa hỗ trợ JDK đích.

Nếu bạn sở hữu module entity, một qualified `opens` cho ORM module có thể phù hợp hơn mở toàn bộ module.

Ví dụ **chỉ mang tính kiến trúc**:

```java
module com.example.domain {
    requires jakarta.persistence;

    opens com.example.domain.entity to org.hibernate.orm.core;
}
```

Tên module thực tế phụ thuộc đúng version Hibernate/JPA đang dùng. Không copy cấu hình này khi chưa xác minh module name trong dependency của dự án.

### 15.3. JSON/XML serializer

Framework serializer có thể đọc field private hoặc tạo object bằng non-public constructor. Nếu deep reflection không được cho phép, `InaccessibleObjectException` có thể xuất hiện.

Một cách sửa bền vững có thể là dùng public accessor/constructor, record support hoặc serializer version mới, không buộc phải mở toàn bộ package.

### 15.4. Mocking và test instrumentation

Mockito, Byte Buddy, JUnit extensions hoặc coverage agent có thể gây reflection/instrumentation lỗi ở JDK mới.

Những yếu tố cần phân biệt:

- `InaccessibleObjectException` do module package chưa open.
- Unsupported class-file version do Byte Buddy/ASM quá cũ.
- Agent attach issue hoặc lỗi provider/test engine.
- `IllegalAccessError` khi generated class hoặc proxy cố truy cập package/member không hợp lệ.

Thêm `--add-opens` không giải quyết lỗi unsupported class-file version. Nâng đúng dependency và test tooling là bước tiên quyết của migration.

### 15.5. Java agents và class loaders

Agent có thể transform bytecode hoặc định nghĩa class tại runtime. Một class được sinh vào loader/module khác có thể bị chặn truy cập API mà source compile trước đó cho phép.

Với lỗi dạng này, xác định:

- Generated class FQCN.
- ClassLoader/module của generated class.
- Package/member target.
- Bytecode transformation/version.
- Cơ chế mở exports/opens mà agent được phép sử dụng.

Không giả định lỗi thuộc source ứng dụng chỉ vì stack trace bắt đầu từ một request handler.

## 16. Maven và Gradle: đặt tùy chọn đúng giai đoạn

### 16.1. Compile-time export trong Maven

Nếu source **cố ý import** public type trong package chưa được export, Maven Compiler Plugin có thể cần compiler arguments tương ứng.

Ví dụ cấu hình khái niệm:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <compilerArgs>
      <arg>--add-exports</arg>
      <arg>com.example.core/com.example.internal=com.example.client</arg>
    </compilerArgs>
  </configuration>
</plugin>
```

Chọn plugin version phù hợp trong POM thực tế. Nếu dùng `--release`, compiler có quy tắc hạn chế một số cách kết hợp option `--add-exports` với system modules; giải pháp lâu dài là bỏ phụ thuộc API JDK nội bộ.

**Quan trọng:** compiler flag không đảm bảo cùng export ở runtime.

### 16.2. Runtime open trong Maven Surefire/Failsafe

Nếu test JVM chạy framework reflection và cần open package tạm thời:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>
      --add-opens java.base/java.lang=ALL-UNNAMED
    </argLine>
  </configuration>
</plugin>
```

Ví dụ minh họa cách truyền JVM argument cho forked test JVM; **không phải khuyến nghị mở `java.lang` ở mọi project**.

Nếu dự án dùng JaCoCo hoặc agent khác thông qua `argLine`, phải gộp arguments thay vì ghi đè. Với integration tests qua Failsafe, cần kiểm tra cấu hình của **Failsafe JVM**, không suy rằng Surefire option tự áp dụng.

### 16.3. Gradle `JavaCompile` và `Test`

Ví dụ Gradle Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'com.example.core/com.example.internal=com.example.client'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.core/com.example.internal=com.example.client'
    )
}
```

Đây là ví dụ về **nơi cấu hình**, không có nghĩa cả hai cờ đều cần cho mọi ứng dụng. Cần đặt đúng target module, đúng task và đúng sự cố.

Nếu app được chạy bằng `JavaExec` hoặc trong container/app server, JVM arguments của `Test` **không tự đi theo**. Phải xác minh startup command thực tế của từng môi trường.

### 16.4. Đặt cờ ở runtime thật

Một số môi trường có nhiều JVM khác nhau:

```text
Developer IDE
      |
      +-- Build JVM (Maven/Gradle)
      +-- Compiler/annotation processor
      +-- Unit-test JVM
      +-- Integration-test JVM
      +-- App JVM
      +-- Production container JVM
      +-- Agent/tool JVM
```

Nếu lỗi xảy ra chỉ khi chạy integration test, sửa JVM chạy unit test sẽ không giải quyết.

Đồng thời, việc cờ có mặt trong `JAVA_TOOL_OPTIONS` hoặc startup script nào đó cần được kiểm chứng; không nên mặc định mọi process Java đọc cùng một cấu hình.

## 17. Quy trình xử lý trong Java compatibility migration

### Bước 1: phân loại hiện tượng, không sửa ngay bằng flag

Lưu stack trace và environment. Xác định `IllegalAccessError`, `IllegalAccessException` hay `InaccessibleObjectException`; ghi API nơi lỗi xuất hiện.

### Bước 2: xác định caller, target, class loader và module

Với JPMS, đọc câu “module X does not export/open package Y to Z”. Với binary mismatch, xác định JAR mà caller được compile và JAR được runtime load.

### Bước 3: dựng thí nghiệm tối thiểu

Tạo reproducer với đúng class/member và đúng JDK/module path. Tránh đưa toàn bộ framework vào ví dụ nếu có thể tái hiện bằng hai module nhỏ.

### Bước 4: kiểm tra dependency và API diff

Nếu `IllegalAccessError`, so visibility/JVM descriptors giữa library trước/sau. Kiểm tra dependency mediation, BOM, shaded JAR và container-provided JAR.

Nếu reflection error, kiểm tra framework version và API reflection đang dùng.

### Bước 5: ưu tiên sửa bằng public API hoặc version được hỗ trợ

Các ưu tiên thường phù hợp:

1. Nâng framework/library lên bản hỗ trợ JDK đích.
2. Thay API nội bộ bằng public API.
3. Nếu sở hữu module, khai báo `exports`/`opens` tối thiểu theo đúng contract.
4. Nếu phải chuyển tiếp, thêm `--add-exports`/`--add-opens` đúng module/package/target và ghi kế hoạch loại bỏ.

Không dùng cờ để duy trì mã phụ thuộc JDK implementation detail lâu dài nếu đã có API thay thế.

### Bước 6: kiểm tra compile và runtime riêng

Nếu cần ordinary access, xác minh compile và runtime dùng cùng contract. Nếu cần reflection, chạy đúng đường code thực hiện `setAccessible`, không chỉ kiểm tra startup.

### Bước 7: chạy test tương thích trên JDK đích

Test nên bao gồm:

- Biên dịch lại consumer source với library candidate.
- Chạy consumer binary cũ nếu có cam kết binary compatibility.
- Unit/integration tests trên JDK mới.
- Reflection/serialization/ORM đường nghiệp vụ thật.
- Classpath và module-path variants nếu hỗ trợ cả hai.
- Test JVM, application JVM và container runtime theo cấu hình triển khai.

### Bước 8: rà soát quyền mở tạm thời

Lưu lại:

| Trường | Nội dung |
| --- | --- |
| Flag | Chuỗi cờ nguyên vẹn. |
| Tại sao cần | Lỗi gốc và stack trace. |
| Source module/package | Module và package đang bị truy cập. |
| Target module | Named module hoặc `ALL-UNNAMED`. |
| Thành phần phụ thuộc | Library/framework và version. |
| JVM áp dụng | Compiler/test/app/production. |
| Rủi ro | Internal API, deep reflection và phạm vi mở quyền. |
| Owner | Nhóm chịu trách nhiệm. |
| Mốc xóa flag | Version dependency/JDK hoặc release migration dự kiến. |
| Bằng chứng | Test trước/sau và log runtime. |

## 18. Các lỗi tư duy thường gặp

### 18.1. “Cứ IllegalAccess là bật `--add-opens`”

Sai. `IllegalAccessError` thường xảy ra ở ordinary access/linkage. `IllegalAccessException` có thể chỉ do private member khi reflection thông thường. `InaccessibleObjectException` mới là dấu hiệu điển hình của một yêu cầu deep reflection bị từ chối ở `setAccessible`.

### 18.2. “`--add-exports` mở được private field”

Sai. Export không thay đổi Java access modifiers. Nếu cần deep reflection được phép, phải xem open package, nhưng tốt hơn là hạn chế phụ thuộc vào private fields.

### 18.3. “`--add-opens` giúp source import internal package”

Sai. `--add-opens` chủ yếu điều khiển deep reflection ở runtime, không thay thế export để `javac` cho ordinary source access.

### 18.4. “Có `requires` là thấy mọi package trong module”

Sai. Readability và exports là hai điều kiện khác nhau.

### 18.5. “`setAccessible(true)` trên Java mới luôn ném lỗi”

Sai. Nó có thể thành công khi caller nằm trong cùng module, khi package được open phù hợp, hoặc theo những trường hợp mà reflection API cho phép. Vấn đề là **context cụ thể**.

### 18.6. “Chỉ thêm flag khi test là production tự nhận”

Sai. JVM chạy test và JVM production thường khác process/configuration.

### 18.7. “Sửa một lỗi access thì tất cả exception biến mất”

Sai. Một flow có thể vừa dùng ordinary access vừa dùng deep reflection. Khi sửa ranh giới đầu tiên, lỗi tiếp theo mới xuất hiện.

### 18.8. “Một stack trace có framework là framework chắc chắn bị bug”

Chưa chắc. Có thể framework phiên bản cũ, JDK thay đổi policy, module descriptor ứng dụng thiếu `opens`, dependency mediation sai hoặc agent gây class-loader mismatch. Cần xác định root cause bằng module/classpath evidence.

### 18.9. “Cờ tương thích là giải pháp lâu dài”

Không nên mặc định. Một package nội bộ có thể thay đổi ở JDK mới; cờ mở quyền không giữ class/method tồn tại hoặc ổn định. Mọi workaround phải được kiểm kê và xem xét loại bỏ.

## 19. Bài thực hành phân loại lỗi

### Tình huống A: compile một nơi, chạy một nơi

Consumer được compile với library v1 có method `public void sync()`. Production vô tình nạp library v2 đã đổi method thành package-private.

**Câu hỏi:** lỗi nào có khả năng xảy ra khi bytecode consumer gọi method?

**Định hướng:** `IllegalAccessError`; kiểm tra JAR runtime và binary compatibility. Không dùng `--add-opens` để đổi access modifier của method.

### Tình huống B: reflection trên private method

Một lớp test gọi:

```java
Method m = Demo.class.getDeclaredMethod("privateAction");
m.invoke(new Demo());
```

`privateAction` là private và lớp test không có quyền truy cập.

**Câu hỏi:** loại exception nào thường xảy ra?

**Định hướng:** `IllegalAccessException` ở `invoke`. Xem lại test design, public API và việc suppress access checks có hợp lệ không.

### Tình huống C: serializer gọi `setAccessible(true)`

Framework serializer nằm trong unnamed module trên classpath, muốn truy cập field private trong package của named module `com.example.domain` chưa open.

**Câu hỏi:** exception nào thường xảy ra, và vì sao?

**Định hướng:** `InaccessibleObjectException` ở `setAccessible(true)`. Cần xác định package target và xem `opens` hoặc nâng framework/chuyển public accessors.

### Tình huống D: thêm đúng cờ nhưng vẫn lỗi

Ứng dụng có:

```text
--add-exports com.example.domain/com.example.model=ALL-UNNAMED
```

Nhưng framework dùng deep reflection vào field private và báo package không open.

**Câu hỏi:** tại sao export không đủ?

**Định hướng:** ordinary access và deep reflection khác quyền. Nếu không có public API thay thế, cần open đúng package cho module thực hiện reflection theo contract, không thêm export khác một cách ngẫu nhiên.

### Tình huống E: Java 11 cảnh báo, Java 17 lỗi

Framework cũ đọc private field của một JDK class. Trên Java 11 chạy với warning illegal reflective access; trên Java 17 xuất hiện `InaccessibleObjectException`.

**Câu hỏi:** cần chẩn đoán theo thứ tự nào?

**Định hướng:** kiểm tra JDK/framework version, module/package/caller, tìm bản framework hỗ trợ Java 17, thay API nội bộ; chỉ cân nhắc `--add-opens` có giới hạn khi cần chuyển tiếp.

## 20. Checklist trước khi kết luận đã xử lý xong

- [ ] Đã phân biệt chính xác ba loại `IllegalAccessError`, `IllegalAccessException` và `InaccessibleObjectException`.
- [ ] Đã đọc root cause cùng các dòng `Caused by` liên quan, không chỉ wrapper exception.
- [ ] Đã xác định ordinary bytecode access, reflection invoke hay `setAccessible`.
- [ ] Đã xác định class/member, caller, source module, target module và package.
- [ ] Đã xác minh class/JAR được runtime nạp, không chỉ version trong POM.
- [ ] Đã so public API/visibility và bytecode nếu nghi binary incompatibility.
- [ ] Đã kiểm tra `requires`/module readability, `exports` và `opens` riêng biệt.
- [ ] Đã phân biệt named/automatic/unnamed module và classpath/module path.
- [ ] Đã kiểm tra Java version của compiler, unit test, integration test và production.
- [ ] Đã ưu tiên public API hoặc dependency/framework có hỗ trợ JDK đích.
- [ ] Nếu dùng JVM flag, đã chọn đúng loại, đúng source/package, đúng target và đúng JVM process.
- [ ] Đã chạy lại đường nghiệp vụ gây reflection, không chỉ startup test.
- [ ] Đã thực hiện consumer recompile/binary/regression tests phù hợp với phạm vi migration.
- [ ] Đã ghi nhận workaround tạm thời, chủ sở hữu và mốc loại bỏ.
- [ ] Đã xác minh artifact triển khai thực tế và không có dependency conflict còn sót.

## 21. Kết luận

Ba tên lỗi giống nhau nhưng phản ánh ba vấn đề khác nhau. **`IllegalAccessError`** thường nói rằng bytecode hoặc module access ở runtime không còn thỏa điều kiện liên kết/truy cập. **`IllegalAccessException`** cho biết một lời gọi reflection đang bị Java access checks từ chối. **`InaccessibleObjectException`** cho biết runtime không cho phép bật deep reflection bằng `setAccessible(true)`, thường do package của named module chưa được open cho caller.

Khi chẩn đoán trong Java Advance Compatibility Migration, hãy bắt đầu từ **loại lỗi và thao tác truy cập thực tế**, sau đó đối chiếu visibility, JPMS module graph, JAR runtime và phiên bản JDK. Chọn `exports` cho ordinary access, `opens` cho deep reflection khi thật sự cần, đồng thời ưu tiên public API và thư viện được hỗ trợ. Một giải pháp được coi là hoàn tất khi đúng code path đã chạy qua trên JDK đích, kết quả được kiểm chứng bằng tests, và những quyền mở tạm thời được quản lý thay vì trở thành nợ kỹ thuật không có điểm kết thúc.
