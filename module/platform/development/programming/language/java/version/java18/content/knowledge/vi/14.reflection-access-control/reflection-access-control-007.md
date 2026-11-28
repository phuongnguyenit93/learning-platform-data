# exports và opens: phân biệt quyền dùng API công khai với quyền reflection vào member không public

## 1. Mục tiêu và bối cảnh

Trong Java Platform Module System (JPMS), một class được khai báo `public` **không có nghĩa** mọi module khác đều có thể dùng class đó. Tương tự, Reflection tìm được một `private field` **không có nghĩa** có thể đọc field đó. Từ khi Java có named module, việc truy cập phụ thuộc đồng thời vào modifier của class/member, quan hệ giữa các module và các directive `exports`/`opens`.

Bài thuộc chương **Quyền reflection** trong module `JAVA_VERSION_JAVA18`. Mục tiêu là nắm những hợp đồng Java 18 vẫn áp dụng trên JDK hiện đại: gọi API công khai, kiểm soát truy cập bằng Reflection, xử lý chẩn đoán và xác minh quyền trên chính JDK đang chạy. Các quy tắc JPMS và strong encapsulation dưới đây vẫn là nền tảng của Java hiện nay.

Sau bài này, bạn có thể:

- Giải thích `requires`, `exports` và `opens` giải quyết ba yêu cầu khác nhau.
- Phân biệt **public API access** và **deep reflection** đối với `private`, package-private và `protected` member.
- Dự đoán hành vi của `getDeclaredField()`, `canAccess()`, `trySetAccessible()` và `setAccessible(true)`.
- Thiết kế module với qualified `exports ... to ...` và `opens ... to ...` theo nguyên tắc cấp quyền tối thiểu.
- Dùng `Module.isExported(...)` và `Module.isOpen(...)` để kiểm chứng cấu hình runtime.
- Phân biệt tác dụng của `--add-exports` và `--add-opens`, không dùng flag như giải pháp dài hạn tùy tiện.
- Nhận biết điều kiện tương ứng khi dùng `MethodHandles.privateLookupIn`.

## 2. Ba câu hỏi trước khi truy cập một class

Đừng trộn lẫn các câu hỏi sau:

1. **Module của caller có đọc module chứa API không?** Quan hệ đọc được khai báo thường bằng `requires` trong `module-info.java`.
2. **Package có xuất API công khai cho caller không?** `exports` cho phép code khác module tham chiếu kiểu public của package trong Java source và gọi thành viên public theo quy tắc truy cập của ngôn ngữ.
3. **Package có mở cho deep reflection không?** `opens` cho phép module được cấp quyền dùng Reflection để yêu cầu suppress kiểm tra truy cập Java đối với member không public.

Cú pháp rút gọn:

~~~java
module org.example.library {
    exports org.example.api;
    opens org.example.internal to org.example.inspector;
}

module org.example.inspector {
    requires org.example.library;
}
~~~

Ở đây:

- `org.example.inspector` đọc `org.example.library` nhờ `requires`.
- `org.example.api` được **exported**: consumer có thể import các public type và sử dụng public API.
- `org.example.internal` được **opened** riêng cho `org.example.inspector`: inspector có thể dùng deep reflection, nhưng không được tự động import type internal trong source.
- Những module khác không được cấp quyền deep reflection vào `org.example.internal` chỉ vì đã biết tên class.

Tóm tắt: **`requires` là quan hệ đọc; `exports` là giao diện lập trình công khai; `opens` là quyền phản chiếu sâu tại runtime.**

## 3. Bảng so sánh exports và opens

Xét **caller thuộc một named module khác**, đã đọc module cung cấp API và không có đặc quyền bổ sung:

| Khai báo package trong module cung cấp | Import public type từ source caller | Gọi public API theo Java language access | Deep reflection vào private field/method |
| --- | --- | --- | --- |
| Chỉ `exports p;` | Có | Có | Không |
| Chỉ `opens p;` | Không | Không có quyền source-level; public type có thể được truy cập ở runtime theo quy tắc mở package | Có |
| `exports p;` và `opens p;` | Có | Có | Có |
| Không `exports`, không `opens` | Không | Không | Không |
| `exports p to m;` | Chỉ module `m` | Chỉ module `m` theo quy tắc export | Không |
| `opens p to m;` | Không | Không có quyền import theo `opens` | Chỉ module `m` |

Bảng này mô tả quyền được cấp ở mức module. Nó **không bỏ qua** modifier ở mức Java: ví dụ `public` của member không làm class package-private trở thành public, và `protected` vẫn có điều kiện truy cập riêng.

Một package có thể đồng thời được `exports` và `opens`, hoặc chỉ dùng một directive. Hai directive không tương đương và không thể thay bằng nhau khi ứng dụng có yêu cầu bảo mật rõ ràng.

### exports cấp quyền gì?

~~~java
module org.example.library {
    exports org.example.api;
}
~~~

Một module khác có `requires org.example.library;` có thể:

- Import `org.example.api.PublicService` nếu class là `public`.
- Gọi public constructor và public method nếu thỏa quy tắc truy cập Java.
- Dùng Reflection trên public members của public type trong exported package.
- **Không tự động** dùng `setAccessible(true)` để đọc private field ở module khác.

### opens cấp quyền gì?

~~~java
module org.example.library {
    opens org.example.internal to org.example.inspector;
}
~~~

Trong module `org.example.inspector`, Reflection có thể suppress kiểm tra truy cập Java đối với member trong package `org.example.internal`. Quyền này bao gồm đọc private field hoặc gọi private method theo các quy tắc Reflection tương ứng. `opens` **không** cho phép source code import các type từ package chưa exported.

Đây là quyền rộng và mạnh hơn việc chỉ công bố public API. Khi không cần deep reflection, đừng mở package một cách vô điều kiện.

## 4. Ví dụ hoàn chỉnh: một module cung cấp, một module kiểm tra

Ví dụ sử dụng hai named module và một cấu trúc mã nguồn đơn giản:

~~~text
project/
└── src/
    ├── org.example.library/
    │   ├── module-info.java
    │   └── org/example/
    │       ├── api/
    │       │   └── Greeting.java
    │       └── internal/
    │           └── Settings.java
    └── org.example.inspector/
        ├── module-info.java
        └── org/example/inspector/
            └── Main.java
~~~

### 4.1. module-info của thư viện

Tệp `src/org.example.library/module-info.java`:

~~~java
module org.example.library {
    exports org.example.api;
    opens org.example.internal to org.example.inspector;
}
~~~

Package `api` được xuất cho mọi module; package `internal` không exported nhưng được mở có điều kiện cho inspector.

### 4.2. API công khai với một private field

Tệp `src/org.example.library/org/example/api/Greeting.java`:

~~~java
package org.example.api;

public final class Greeting {
    private final String internalCode = "G-001";

    public String hello() {
        return "Xin chào";
    }
}
~~~

Class `Greeting` là public trong package exported. Caller khác module có quyền sử dụng `hello()`, nhưng không được đọc `internalCode` bằng deep reflection nếu chỉ có `exports`.

### 4.3. Class thuộc package chỉ được opens

Tệp `src/org.example.library/org/example/internal/Settings.java`:

~~~java
package org.example.internal;

public final class Settings {
    private final String exampleValue = "demo-only";

    public Settings() {
    }
}
~~~

`Settings` được khai báo public để dễ quan sát, nhưng package `org.example.internal` **không exported**. Vì vậy inspector không thể viết import `org.example.internal.Settings` trong source, dù package đã mở cho Reflection.

Chỉ dùng dữ liệu `demo-only` để minh họa. Không in token, mật khẩu hoặc thông tin nhạy cảm thật khi kiểm tra deep reflection.

### 4.4. module-info của inspector

Tệp `src/org.example.inspector/module-info.java`:

~~~java
module org.example.inspector {
    requires org.example.library;
}
~~~

`requires` cho phép inspector đọc module thư viện. Nó không tự động cấp quyền mở mọi package của thư viện.

### 4.5. Chương trình dùng cả public và private reflection

Tệp `src/org.example.inspector/org/example/inspector/Main.java`:

~~~java
package org.example.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import org.example.api.Greeting;

public final class Main {
    public static void main(String[] args) throws Exception {
        Greeting greeting = new Greeting();

        // 1. Public API trong exported package: hoạt động bình thường.
        System.out.println(greeting.hello());

        Method publicMethod = Greeting.class.getMethod("hello");
        System.out.println(publicMethod.invoke(greeting));

        // 2. Tìm thấy private field không có nghĩa được phép đọc.
        Field internalCode =
                Greeting.class.getDeclaredField("internalCode");
        System.out.println(
                "exported-only private accessible? "
                        + internalCode.trySetAccessible());
        System.out.println(
                "canAccess? " + internalCode.canAccess(greeting));

        // 3. Class nằm trong package opened, không exported.
        Class<?> settingsClass =
                Class.forName("org.example.internal.Settings");

        Constructor<?> constructor =
                settingsClass.getDeclaredConstructor();
        boolean constructorAllowed = constructor.trySetAccessible();
        System.out.println("opened constructor? " + constructorAllowed);

        if (!constructorAllowed) {
            throw new IllegalStateException(
                    "org.example.internal is not open to inspector");
        }

        Object settings = constructor.newInstance();
        Field exampleValue =
                settingsClass.getDeclaredField("exampleValue");

        if (!exampleValue.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access exampleValue reflectively");
        }

        System.out.println(exampleValue.get(settings));
    }
}
~~~

Chương trình không import `Settings`. Thay vào đó, `Class.forName(...)` lấy `Class<?>` theo tên, sau đó Reflection truy cập constructor/field khi quyền `opens` cho phép.

Chú ý rằng `Class.forName(...)` hoặc `getDeclaredField(...)` có thể định vị đối tượng Reflection nhưng **không tự chứng minh quyền invoke/get**. Đây là hai bước khác nhau: *khám phá member* và *được phép dùng member*.

## 5. Biên dịch và chạy ví dụ

Từ thư mục `project`:

~~~sh
javac -d mods --module-source-path src     -m org.example.library,org.example.inspector

java --module-path mods     -m org.example.inspector/org.example.inspector.Main
~~~

Các lệnh trên minh họa terminal Linux/macOS. Với PowerShell hoặc CMD, đặt lệnh thành một dòng hoặc dùng ký tự nối dòng phù hợp shell.

Kết quả điển hình:

~~~text
Xin chào
Xin chào
exported-only private accessible? false
canAccess? false
opened constructor? true
demo-only
~~~

Giải thích:

- `Greeting.hello()` hoạt động vì class public nằm trong package exported.
- `Greeting.internalCode` là private và package `org.example.api` **chưa opened** cho inspector: `trySetAccessible()` trả `false`.
- `Settings` nằm trong package `org.example.internal` đã `opens ... to org.example.inspector`: Reflection có thể suppress access check để tạo instance và đọc private field.
- Việc đọc private field trong ví dụ chỉ để chứng minh hợp đồng; không nên lấy deep reflection làm lối tắt API thiết kế kém.

### Thay đổi cấu hình và dự đoán kết quả

Thử đổi thư viện thành:

~~~java
module org.example.library {
    exports org.example.api;
    // Không còn opens org.example.internal to org.example.inspector;
}
~~~

Chạy lại sau khi biên dịch. `Greeting` vẫn dùng được, nhưng `constructor.trySetAccessible()` của `Settings` trả `false`. Nếu gọi `setAccessible(true)` thay vì `trySetAccessible()`, thao tác có thể ném `InaccessibleObjectException` vì module không mở package cho caller.

Đổi lại thành:

~~~java
module org.example.library {
    exports org.example.api;
    opens org.example.api to org.example.inspector;
    opens org.example.internal to org.example.inspector;
}
~~~

Giờ inspector có thể suppress access check trên cả private field `Greeting.internalCode`. Điều này minh họa một package vừa **exported** cho người dùng API, vừa **opened** có điều kiện cho framework hoặc công cụ được tin cậy.

## 6. Khám phá member khác với quyền truy cập member

Một số API Reflection dễ gây hiểu nhầm:

| API | Mục đích | Điều không được suy ra |
| --- | --- | --- |
| `Class.getMethod(...)` | Tìm public method theo quy tắc Reflection. | Không chứng minh caller được invoke ở mọi cấu hình module. |
| `Class.getDeclaredMethod(...)` | Tìm method khai báo trực tiếp, kể cả nonpublic. | Không tự cấp quyền invoke method private. |
| `Class.getDeclaredField(...)` | Tìm field khai báo trực tiếp, kể cả private. | Không tự cấp quyền `Field.get`/`set`. |
| `Field.canAccess(instance)` | Kiểm tra caller hiện có được dùng reflected field với instance này không. | Không làm thay đổi quyền. |
| `Field.trySetAccessible()` | Thử bật khả năng suppress access check. | Không bảo đảm thành công; trả `false` nếu module chặn. |
| `Field.setAccessible(true)` | Yêu cầu suppress access check. | Có thể ném `InaccessibleObjectException` khi không được phép. |

`canAccess` cần tham số thích hợp:

- Với instance field/method: truyền instance thuộc declaring class hoặc subtype phù hợp.
- Với static field/method và constructor: truyền `null`.
- Tham số sai loại có thể làm `canAccess` ném `IllegalArgumentException`, không đơn thuần trả `false`.

Ví dụ chẩn đoán an toàn:

~~~java
Field field = Greeting.class.getDeclaredField("internalCode");

boolean before = field.canAccess(new Greeting()); // false
boolean enabled = field.trySetAccessible();        // false: chỉ exports

System.out.printf("before=%s, enabled=%s%n", before, enabled);
~~~

Đối với method public trong exported package, một caller có quyền truy cập có thể gọi thẳng hoặc `Method.invoke`; không cần bật suppress access. `setAccessible(true)` không phải bước bắt buộc cho mọi Reflection.

### Những điều kiện setAccessible có thể thành công

Theo hợp đồng `AccessibleObject`, giữa hai named module khác nhau, việc bật suppress access được phép trong những trường hợp như:

- Member public thuộc public class trong package exported tới caller.
- Một trường hợp `protected static` ở public class trong exported package và caller là subclass phù hợp.
- Declaring class nằm trong package opened tới module caller: có thể deep-reflect vào member không public.

Nếu caller và declaring class thuộc **cùng module**, quyền suppress có thể được bật mà không cần exports/opens giữa hai module. Đây là điểm khác biệt lớn giữa thư viện tự phản chiếu các lớp của chính mình và framework bên ngoài phản chiếu vào thư viện.

Chính sách `exports`/`opens` không thay thế toàn bộ quy tắc `public`, `protected`, package-private và `private` trong Java source.

## 7. Qualified exports và qualified opens

Cả hai directive hỗ trợ hình thức `to` để chỉ định danh sách named module được cấp quyền.

Ví dụ:

~~~java
module org.example.library {
    exports org.example.api;
    exports org.example.spi to org.example.plugin;

    opens org.example.model to org.example.json;
    opens org.example.internal to org.example.inspector;
}
~~~

Ý nghĩa:

- `org.example.api` được exported cho mọi module đọc thư viện.
- `org.example.spi` chỉ exported cho `org.example.plugin`.
- `org.example.model` chỉ opened cho `org.example.json`, ví dụ một thư viện serialization cần đọc/ghi field.
- `org.example.internal` chỉ opened cho `org.example.inspector`, không cho các module khác.

Qualified `opens` thường hợp lý hơn `opens package;` khi chỉ một framework cụ thể cần truy cập private member. Nếu framework cần nhiều package thì cân nhắc mở từng package, không tự động dùng `open module`.

### opens không phải exports

Đoạn import sau **không hợp lệ** trong inspector nếu package chỉ được mở mà không exported:

~~~java
// Ví dụ cố ý sai trong module org.example.inspector:
import org.example.internal.Settings;
~~~

Compiler không cấp quyền import vì `opens`. Việc chương trình ví dụ trước đó dùng `Class.forName` và Reflection thành công là kết quả của **runtime deep reflection**, không có nghĩa package đã trở thành API source-level.

Ngược lại, chỉ `exports org.example.api;` không cho inspector đặt `setAccessible(true)` lên mọi private field của API class.

## 8. Kiểm chứng module bằng Module API

Ngoài quan sát exception, ứng dụng có thể xem quyền của module tại runtime:

~~~java
Module library = Greeting.class.getModule();
Module inspector = Main.class.getModule();

System.out.println(library.getName()); // org.example.library

System.out.println(
        library.isExported("org.example.api", inspector)); // true

System.out.println(
        library.isOpen("org.example.api", inspector)); // false nếu chỉ exports

System.out.println(
        library.isOpen("org.example.internal", inspector)); // true

System.out.println(
        inspector.canRead(library)); // true nhờ requires
~~~

Dùng dạng `isExported(packageName, otherModule)` và `isOpen(packageName, otherModule)` khi kiểm tra qualified directives. Dạng không nhận `otherModule` hỏi liệu quyền được cấp **vô điều kiện** cho tất cả module hay không, không thay thế được kiểm tra quyền dành riêng cho inspector.

Các giá trị trả về mô tả cấu hình module **tại runtime**; launcher flag hoặc cập nhật module hợp lệ có thể làm kết quả khác cấu hình `module-info.java` ban đầu.

Đừng dùng `isExported(...)` để kết luận một private field đọc được. Cần kiểm tra `isOpen(...)` cho đúng package, kết hợp quy tắc caller và trạng thái access của member.

## 9. --add-exports khác --add-opens thế nào?

Trong quá trình chẩn đoán hoặc tích hợp công cụ khi chưa sửa được `module-info.java`, launcher có thể mở rộng quyền module bằng flag.

| Tùy chọn | Tác dụng chính | Không thay thế cho |
| --- | --- | --- |
| `--add-exports module/package=target` | Cấp thêm quyền dùng public API của package cho target module. | Quyền deep reflection vào private member. |
| `--add-opens module/package=target` | Mở package cho target module để Reflection có thể suppress access check. | Quyền import API công khai tại compile time. |
| `--add-reads source=target` | Bổ sung quan hệ đọc module. | Không tự exports/opens package. |

Ví dụ: chỉ mở thêm private reflection vào `org.example.api` cho inspector khi chạy:

~~~sh
java --module-path mods   --add-opens org.example.library/org.example.api=org.example.inspector   -m org.example.inspector/org.example.inspector.Main
~~~

Với flag đó, lời gọi `trySetAccessible()` trên `Greeting.internalCode` có thể trả `true`, dù `module-info.java` của thư viện chưa khai báo `opens org.example.api`. Lưu ý output chính của ví dụ có thể thay đổi theo flag runtime.

Cấp quyền cho ứng dụng chạy trên classpath (unnamed modules) có cú pháp đích `ALL-UNNAMED`:

~~~sh
java --add-opens org.example.library/org.example.internal=ALL-UNNAMED ...
~~~

Đây là cấu hình mở rộng quyền truy cập, **không phải** cách nên mặc định dùng cho mọi package. Trong ứng dụng modular có quyền chỉnh module descriptor, ưu tiên `opens ... to ...` với đúng target named module.

### Tại sao không dùng add-exports để mở private field?

Giả sử đã **bỏ** directive `opens org.example.internal to org.example.inspector;` khỏi module thư viện và biên dịch lại. Khi đó, nếu chỉ chạy với flag sau:

~~~sh
java --module-path mods   --add-exports org.example.library/org.example.internal=org.example.inspector   -m org.example.inspector/org.example.inspector.Main
~~~

Inspector được cấp thêm quyền sử dụng **public** API của package `internal` theo quy tắc runtime. Tuy nhiên, trong cấu hình **không có `opens`**, `--add-exports` **không** biến private field thành truy cập được bằng `setAccessible(true)`. Muốn deep reflection vượt giới hạn module, cần package opened đúng mục tiêu.

Đừng dùng launcher flag để bỏ qua mọi ranh giới thư viện mà không có lý do thiết kế và bảo mật. Nếu API public đủ dùng, giải pháp đúng thường là gọi API đó.

## 10. MethodHandles.privateLookupIn cũng cần opens

Ngoài Core Reflection (`Field`/`Method`/`Constructor`), `MethodHandles.Lookup` cũng tuân theo quyền module.

Ví dụ lấy lookup có thể truy cập private member của `Settings`:

~~~java
import java.lang.invoke.MethodHandles;

Class<?> settingsClass =
        Class.forName("org.example.internal.Settings");

MethodHandles.Lookup lookup =
        MethodHandles.privateLookupIn(
                settingsClass,
                MethodHandles.lookup());
~~~

Để `privateLookupIn` hoạt động **giữa hai module khác nhau**:

1. Caller lookup cần đủ quyền `PRIVATE` và `MODULE`.
2. Module caller phải **đọc** module của target.
3. Module target phải **mở package** của target cho module caller.

Vì thế `exports` public API **không đủ** để tạo một private lookup xuyên module. Với cấu hình ví dụ, `org.example.internal` được opened cho inspector nên yêu cầu deep lookup có thể thành công.

Không nhầm `MethodHandles.lookup()` với `publicLookup()`. `publicLookup()` chỉ có quyền rất hạn chế đối với public types/public members trong packages exported vô điều kiện và không thể tự nâng quyền thành private lookup của module khác.

Cảnh báo: deep lookup có thể tạo ra nhiều năng lực truy cập ngoài việc đọc field; chỉ trao quyền `opens` cho module thật sự đáng tin và cần thiết.

## 11. opens không đồng nghĩa quyền sửa mọi final field

Một trường hợp cần tránh suy diễn là field `final`. Mở package và bật accessible flag không có nghĩa bất kỳ final field nào cũng có thể ghi lại hợp lệ.

Các quy tắc hiện đại giới hạn mạnh việc thay đổi `final`, đặc biệt đối với:

- `static final` fields.
- `final` fields trong record.
- `final` fields trong hidden class.
- Những trường hợp khác chịu chính sách final-field mutation của JDK hiện đại.

Một framework có thể đọc private field hợp pháp sau `opens`, nhưng thao tác `Field.set(...)` lên final field vẫn có thể bị từ chối hoặc bị hạn chế riêng. **Hãy dùng constructor, public API, factory hoặc thiết kế dữ liệu phù hợp thay vì dựa vào thay đổi final field bằng Reflection.**

Điểm này rất quan trọng với thư viện serialization, dependency injection và mapping object: *mở package cho Reflection* không phải hợp đồng cho phép phá mọi ràng buộc bất biến của object.

## 12. open module và unnamed module: bối cảnh đặc biệt

Ngoài `opens p;` của một normal named module, Java còn có:

~~~java
open module org.example.legacyintegration {
    requires org.example.library;
}
~~~

`open module` mở mọi package của module đó cho deep reflection. Tuy nhiên nó **không tự export tất cả package thành API có thể import từ source**. Muốn public API để module khác dùng trong source, vẫn cần `exports` phù hợp. Một `open module` không viết thêm các `opens` directive riêng.

Một **unnamed module** (thường là code trên classpath) có các quy tắc mở/exports khác named module. Do đó, ví dụ Reflection chạy được khi cả hai class ở classpath có thể thất bại khi tách chúng thành named modules với `module-info.java`. Hãy kiểm chứng bằng cấu hình module thực tế khi phân tích lỗi.

Không chọn `open module` chỉ vì một framework cần truy cập một package. Ưu tiên mở có điều kiện những package thực sự cần thiết.

## 13. Chẩn đoán lỗi truy cập Reflection

Khi truy cập thất bại, phân biệt ba giai đoạn:

| Giai đoạn | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| **Compile** | `package ... is not visible`, import không thành công | Kiểm tra `requires`, `exports` và module source/module path. `opens` không cấp quyền import. |
| **Discovery** | `ClassNotFoundException`, `NoSuchFieldException`, `NoSuchMethodException` | Kiểm tra tên binary class, tên member, module resolution và chữ ký thực tế. |
| **Access** | `trySetAccessible() == false`, `InaccessibleObjectException` hoặc `IllegalAccessException` | Kiểm tra declaring module/package, module caller, exports/opens và modifier của member. |

Hai trường hợp thường gặp:

### Trường hợp A: public API hoạt động, private field bị chặn

~~~java
Method publicMethod = Greeting.class.getMethod("hello");
System.out.println(publicMethod.invoke(new Greeting())); // OK

Field hidden = Greeting.class.getDeclaredField("internalCode");
System.out.println(hidden.trySetAccessible()); // false: api chưa opened
~~~

Đây là hành vi đúng khi package chỉ được `exports`. Không nên xem đây là lỗi của Reflection hay cố sửa bằng `--add-exports`.

### Trường hợp B: package mở, nhưng code không import được class

~~~java
// Không compile từ module inspector nếu chỉ có opens internal:
import org.example.internal.Settings;
~~~

Đây cũng là hành vi đúng. Package được mở cho Reflection, không được công bố là public source API. Nếu thật sự cần import, thư viện phải quyết định có nên `exports` một API phù hợp hay không.

### Checklist chẩn đoán

1. Đọc `Class.getModule()` của class đích và caller.
2. Xác định package của declaring class, không nhầm với package của receiver hoặc của một class con.
3. Kiểm tra caller có quan hệ đọc module đích hay không.
4. Kiểm tra `isExported(package, callerModule)` cho public API access.
5. Kiểm tra `isOpen(package, callerModule)` cho deep reflection.
6. Xác định member có `public`/`protected`/package-private/`private`.
7. Dùng `canAccess(...)` hoặc `trySetAccessible()` thay vì giả định thành công.
8. Nếu bắt buộc dùng `setAccessible(true)`, xử lý `InaccessibleObjectException` và thông báo rõ yêu cầu quyền.
9. Đối chiếu launcher flags và `module-info.java` với môi trường CI/production.
10. Ưu tiên sửa API/module descriptor hoặc cấu hình framework theo cách cấp ít quyền nhất.

## 14. Nguyên tắc thiết kế thư viện và framework

Khi thiết kế API modular:

- **Export package API ổn định** để ứng dụng khác sử dụng trực tiếp.
- **Giữ implementation package không exported** nếu nó không phải hợp đồng người dùng.
- **Chỉ mở package cần reflection** cho framework cụ thể bằng `opens ... to ...`.
- **Tránh public hóa implementation chỉ vì framework muốn khởi tạo object**; cân nhắc factory, service provider hoặc cấu hình framework.
- **Không dùng `open module` hoặc `--add-opens ...=ALL-UNNAMED` theo thói quen** khi có thể cấp quyền hẹp hơn.
- **Không coi `setAccessible(true)` là khả năng vượt giới hạn module**: JPMS có ranh giới truy cập không thể bỏ qua tùy ý.
- **Giữ test chạy ở named-module mode** nếu production chạy ở named-module mode; đừng chỉ kiểm thử trên classpath.
- **Không để thông báo lỗi hoặc ví dụ học tập in dữ liệu nhạy cảm thật** khi thể hiện khả năng Reflection đọc private field.

## 15. Bài tập thực hành

### Bài tập 1: Điền bảng quyền

Giả sử module `com.acme.app` đọc `com.acme.lib`. Với từng cấu hình bên dưới, dự đoán ba kết quả: import public type, Reflection gọi public method, và `trySetAccessible` trên private field.

1. Chỉ `exports com.acme.api;`.
2. Chỉ `opens com.acme.api to com.acme.app;`.
3. Cả `exports` và `opens`.
4. Không có directive nào cho package.

**Tự kiểm:** chỉ `exports` không cấp quyền vào private member; chỉ `opens` không cấp quyền import type trong source.

### Bài tập 2: Chạy ví dụ hai module

Tạo cấu trúc ở mục 4, biên dịch và chạy. Ghi lại kết quả của `trySetAccessible` trên field private ở `api` và `internal`. Xóa directive `opens` cho internal, biên dịch lại và so sánh.

### Bài tập 3: Kiểm chứng bằng Module API

Thêm logging:

~~~java
Module target = Greeting.class.getModule();
Module caller = Main.class.getModule();

System.out.println(
        target.isExported("org.example.api", caller));
System.out.println(
        target.isOpen("org.example.internal", caller));
~~~

Giải thích vì sao phải dùng overload có `caller` khi module descriptor có qualified `opens`.

### Bài tập 4: So sánh trySetAccessible và setAccessible

Với private field `Greeting.internalCode` khi package chỉ exported:

- Gọi `trySetAccessible()` và ghi kết quả.
- Gọi `setAccessible(true)` trong `try/catch` riêng.
- Xác định khác biệt giữa giá trị `false` và `InaccessibleObjectException`.

Sau đó thêm `opens org.example.api to org.example.inspector;` và thử lại.

### Bài tập 5: Thử --add-opens

Giữ module descriptor ban đầu, chạy với:

~~~sh
java --module-path mods --add-opens org.example.library/org.example.api=org.example.inspector -m org.example.inspector/org.example.inspector.Main
~~~

So sánh kết quả private reflection trước/sau flag. Giải thích vì sao cấu hình launcher có thể đổi quyền runtime nhưng không đồng nghĩa `org.example.api` chứa public API mới.

### Bài tập 6: privateLookupIn

Dùng `Class.forName("org.example.internal.Settings")` để lấy `Class<?>` mà không import package chưa exported, rồi gọi `MethodHandles.privateLookupIn(settingsClass, MethodHandles.lookup())` ở module được cấp quyền opened. Lặp lại khi bỏ `opens`. Dự đoán vì sao `IllegalAccessException` xuất hiện dù caller có `requires` và target class là public.

### Bài tập 7: Quyết định thiết kế module

Một framework serialization cần đọc field private của `com.acme.model`, còn ứng dụng cần import API từ `com.acme.api`. Hãy đề xuất `module-info.java` theo nguyên tắc quyền tối thiểu. Giải thích vì sao không mở toàn bộ module nếu framework chỉ cần một package.

## 16. Ghi nhớ

- **`requires` khai báo module đọc module khác; `exports` công bố public API; `opens` cho phép deep reflection tại runtime.**
- **Public class trong package chưa exported không tự trở thành public API cho module khác.**
- **`exports` cho phép truy cập public API nhưng không cho phép Reflection đọc private field ở module khác chỉ nhờ `setAccessible(true)`.**
- **`opens` cho phép caller được chỉ định suppress access check vào nonpublic members, nhưng không cho phép import package chưa exported trong source.**
- **`getDeclaredField()`/`getDeclaredMethod()` là tìm kiếm member, không phải cấp quyền đọc, gọi hoặc ghi member.**
- **`trySetAccessible()` trả `false` nếu không thể bật; `setAccessible(true)` có thể ném `InaccessibleObjectException`.**
- **Qualified `opens ... to module` thường an toàn hơn mở package cho mọi module.**
- **`--add-opens` không tương đương `--add-exports`.** Dùng launcher flags có chủ đích, ưu tiên hợp đồng module rõ ràng.
- **`MethodHandles.privateLookupIn` cũng yêu cầu package opened và điều kiện lookup/readability phù hợp.**
- **Mở package không xóa mọi hạn chế khác**, chẳng hạn quy tắc đối với final fields; hãy giữ ranh giới bất biến và nguyên tắc cấp quyền tối thiểu.

## Tài liệu chính thống

- [JLS JDK 26 — mục 7.7.2 Exported and Opened Packages](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.2).
- [Java SE 26 — AccessibleObject: setAccessible, trySetAccessible, canAccess](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Java SE 26 — Module: isExported, isOpen, canRead](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html).
- [Java SE 26 — MethodHandles.privateLookupIn](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)).
- [Java SE 26 — Field và các hạn chế truy cập final field](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html).
- [Oracle JDK 26 Migration Guide — --add-opens](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).

