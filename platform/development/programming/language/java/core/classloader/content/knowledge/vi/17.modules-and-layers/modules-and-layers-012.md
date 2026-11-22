# Phân biệt --add-reads, --add-exports và --add-opens trong Java Module System

> **Java Core → ClassLoader → Module và layer.** Ba tùy chọn launcher `--add-reads`, `--add-exports` và `--add-opens` giải quyết ba điều kiện **khác nhau** trong Java Platform Module System (JPMS): module nào đọc module nào, package nào công khai các public types/members cho module khác, và package nào cho phép truy cập phản chiếu sâu (*deep reflection*). Chúng **không** thay đổi classpath, không tải thêm JAR, không sửa mã bytecode và không biến class loader thành sandbox. Bài viết có ví dụ hai named modules, lệnh Java 17+ chạy được và kết quả quan sát đã được kiểm thử.

## 1. Vấn đề: nhìn thấy class chưa có nghĩa được truy cập

Một type có thể nằm trong JAR trên `--module-path`, module của nó đã được resolved, và `Class.forName` tìm thấy class, nhưng chương trình vẫn không sử dụng được class đó. Hãy phân biệt:

1. **Discovery/resolution:** module có tồn tại và được đưa vào module configuration hay chưa?
2. **Readability:** module A có một *read edge* tới module B không?
3. **Exports:** B có export package chứa public type cho A không?
4. **Opens:** B có open package cho code trong A sử dụng reflection sâu không?
5. **Ordinary Java access:** type/method có `public`, `private` hoặc access modifier khác? Export package **không** làm private field trở thành public.

Một phép kiểm tra access có thể thất bại dù bytes của class đã nằm trong JVM:

```text
Module path -> module resolved -> class tìm được
                                   |
                                   v
                              Read edge?
                                   |
                                   v
                    Package exported tới caller?
                                   |
                                   v
                         ordinary public access

Deep reflection vào private field/method:
  module/package -> opens tới caller -> setAccessible(true)
```

Ba tùy chọn chỉ can thiệp vào các mũi tên phù hợp. Khi gặp `IllegalAccessError` hoặc `InaccessibleObjectException`, hãy sửa **đúng loại ranh giới**, không thêm tất cả flags một cách máy móc.

## 2. --add-reads: bổ sung khả năng đọc module

Trong descriptor:

```java
module m.consumer {
    requires m.provider;
}
```

`requires m.provider;` tạo khả năng *đọc* `m.provider` từ `m.consumer`. Khi không có `requires` phù hợp, một override từ compiler/launcher là:

```bash
--add-reads m.consumer=m.provider
```

Ý nghĩa chính xác: **m.consumer đọc m.provider**. Module đứng trước dấu `=` là **bên cần sử dụng**, module sau dấu `=` là **bên cung cấp**.

Cần chú ý:

- Read edge chỉ tạo điều kiện truy cập; package bên provider vẫn phải **export** cho ordinary static access.
- `--add-reads` không tự động thêm `requires` vào file `module-info.java`; compile-time option và runtime option là **hai lần cấu hình riêng**.
- Module cần phải **observable/resolved** trong module configuration; `--add-reads` không tự tìm class trong một JAR bất kỳ.
- `--add-reads m.consumer=ALL-UNNAMED` cho named module đọc các unnamed modules. Đây là compatibility escape hatch, không thay `--class-path`.
- Nó không mở private fields, không cấp quyền dùng reflection sâu và không thay ranh giới package export.

Khi kiểm soát mã nguồn, **ưu tiên `requires`** trong module descriptor. Dùng flag để tương thích thư viện cũ, chạy thử, hoặc khi hệ module/legacy classpath chưa thể khai báo trực tiếp theo mô hình thông thường.

## 3. --add-exports: cấp quyền dùng public API của package

Một named module có:

```java
module m.provider {
    exports p.api;
}
```

Code trong các modules đọc `m.provider` có thể truy cập **public types và accessible members** của package `p.api`. Nếu `m.provider` còn có `p.internal` nhưng **không export**, ordinary source ở `m.consumer` không thể `import p.internal.Secret;` để gọi public member của type này chỉ nhờ read edge.

Override tại compiler/launcher:

```bash
--add-exports m.provider/p.internal=m.consumer
```

Nghĩa: **m.provider export package p.internal cho m.consumer**. Source/owner module ở phía **trái**, target module ở phía **phải**.

Nếu có quyền chỉnh module descriptor, có thể thay workaround bằng:

```java
module m.provider {
    exports p.api;
    exports p.internal to m.consumer;
}
```

Điểm quan trọng:

- Export mở **public API** của package, chứ không làm `private`, `protected` hoặc package-private thành public.
- Khi code nguồn **import hoặc gọi trực tiếp** public type/member vốn không exported, thường cần `--add-exports` **khi biên dịch lẫn lúc chạy** nếu descriptor chưa được sửa.
- `--add-exports` **không** cho `setAccessible(true)` tự do đọc private member trong một package chưa mở.
- Nếu caller không đọc provider, còn phải xử lý read edge; export không thay `--add-reads`.
- Đây là ngoại lệ làm yếu strong encapsulation; phụ thuộc JDK-internal API có thể gãy khi nâng cấp JDK.

## 4. --add-opens: mở package cho reflection sâu ở runtime

Java reflection đôi khi cần truy cập non-public fields/methods:

```java
java.lang.reflect.Method method =
        SomeClass.class.getDeclaredMethod("hidden");
method.setAccessible(true);
Object result = method.invoke(instance);
```

Đây là **snippet**, `SomeClass` và `instance` phải được cung cấp từ ngữ cảnh. Việc tìm ra `Method` không đảm bảo bước `setAccessible(true)` sẽ được JPMS cho phép.

Nếu `SomeClass` nằm trong package `p.model` của `m.provider` còn code phản chiếu ở `m.reflect`, flag thích hợp:

```bash
--add-opens m.provider/p.model=m.reflect
```

Hoặc trong module descriptor của module do bạn sở hữu:

```java
module m.provider {
    opens p.model to m.reflect;
}
```

Một *opened package* cho phép reflective access tới public **và** non-public members của types trong package đó từ target module, nếu API và các access rules liên quan cho phép. Điều này quan trọng cho serialization, ORM, DI và instrumentation.

**Không được hiểu `--add-opens` là alias của `--add-exports`:**

- `opens` hữu ích cho reflection ở **runtime**.
- Nó **không cho Java compiler import một package chưa exported** để viết lời gọi direct method thông thường.
- Với public member được gọi **bằng reflection**, `opens` cũng có thể đủ dù package không exported. Mục 8 chứng minh trường hợp này.
- `--add-opens` không cần ở compile time cho một chương trình chỉ muốn sử dụng private reflection về sau; có ý nghĩa thực sự khi launcher thiết lập runtime module access.

Khi một framework vẫn phụ thuộc nhiều `--add-opens java.base/...`, ưu tiên nâng cấp framework hoặc sửa thiết kế để tránh JDK internals.

## 5. So sánh chính xác trong một bảng

| Tiêu chí | `--add-reads` | `--add-exports` | `--add-opens` |
| --- | --- | --- | --- |
| Tác dụng chính | A **đọc** B | B **export public API** của package p cho A | B **open** package p cho reflection từ A |
| Cú pháp | `--add-reads A=B` | `--add-exports B/p=A` | `--add-opens B/p=A` |
| Điều kiện truy cập trực tiếp public class | Đáp ứng read edge | Đáp ứng export edge | **Không thay export** cho direct source/bytecode access |
| `setAccessible(true)` vào private member từ module khác | Không đủ | Không đủ | Thường là flag cần, nếu còn thỏa access conditions |
| Reflection public member trong package | Có thể cần theo ngữ cảnh | Cho phép reflective public access khi phù hợp | Opening cũng đủ cho reflective access trong ví dụ |
| Compile-time Java source | Có thể cần | Có thể cần | Không giải quyết missing exports ở compiler |
| Runtime JPMS | Có | Có | Có |
| Tự thêm JAR/module, chuyển ClassLoader | Không | Không | Không |
| Rủi ro khi dùng rộng | Graph dependencies khó hiểu | Lộ thêm public internal API | Mở sâu non-public internals cho reflection |

**Quy tắc đơn giản:** thiếu dependency module → đọc; package public không visible → export; `setAccessible` bị chặn → open. Khi phát sinh cả hai/ba loại điều kiện, có thể cần **kết hợp** flags chính xác.

## 6. Cú pháp chuẩn và ALL-UNNAMED

Cú pháp của launcher:

```text
--add-reads  MODULE=TARGET[,TARGET...]
--add-exports MODULE/PACKAGE=TARGET[,TARGET...]
--add-opens   MODULE/PACKAGE=TARGET[,TARGET...]
```

`TARGET` có thể là tên một named module, hoặc đặc biệt `ALL-UNNAMED` để chỉ **tất cả unnamed modules**. Unnamed module thường chứa classpath code, nhưng có thể có **nhiều unnamed modules** gắn với các class loaders khác nhau.

Ví dụ:

```bash
--add-reads m.consumer=ALL-UNNAMED
--add-exports m.provider/p.internal=ALL-UNNAMED
--add-opens java.base/java.lang=ALL-UNNAMED
```

Đây là các **tham số**, không phải lệnh shell độc lập có executable. Thay `ALL-UNNAMED` bằng đúng named caller nếu biết:

```bash
--add-opens m.app/com.example.model=m.serializer
```

Hạn chế dùng `ALL-UNNAMED` khi chỉ một framework named module cần quyền. Nó cấp ngoại lệ rộng hơn, có thể áp dụng tới unnamed modules được tạo về sau theo API.

Không nhầm `ALL-UNNAMED` với một module do lập trình viên khai báo trong `module-info.java`. Không viết slash `/` giữa hai module names của `--add-reads`; slash chỉ dùng trong cú pháp module/package của exports/opens.

## 7. Demo Java 17+: hai named modules và ba loại access

### Cấu trúc project

```text
src/
  m.provider/
    module-info.java
    p/api/Api.java
    p/internal/Secret.java
  m.consumer/
    module-info.java
    client/Main.java
mods/          (javac tạo)
```

`m.provider` export package `p.api` nhưng giữ package `p.internal` không exported/opened. `m.consumer` không khai báo `requires m.provider`, để ta thấy tác dụng của `--add-reads`.

**`src/m.provider/module-info.java`:**

```java
module m.provider {
    exports p.api;
}
```

**`src/m.provider/p/api/Api.java`:**

```java
package p.api;

public class Api {
    public static String greet() {
        return "api-ok";
    }
}
```

**`src/m.provider/p/internal/Secret.java`:**

```java
package p.internal;

public class Secret {
    public static String publicHello() {
        return "public-ok";
    }

    private static String privateHello() {
        return "private-ok";
    }
}
```

**`src/m.consumer/module-info.java`:**

```java
module m.consumer { }
```

**`src/m.consumer/client/Main.java`:**

```java
package client;

import p.api.Api;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("api=" + Api.greet());

        Class<?> type = Class.forName("p.internal.Secret");

        try {
            System.out.println("public="
                    + type.getMethod("publicHello").invoke(null));
        } catch (IllegalAccessException ex) {
            System.out.println("public=DENIED");
        }

        Method privateMethod =
                type.getDeclaredMethod("privateHello");
        try {
            privateMethod.setAccessible(true);
            System.out.println("private="
                    + privateMethod.invoke(null));
        } catch (InaccessibleObjectException ex) {
            System.out.println("private=DENIED");
        }
    }
}
```

Chương trình phân biệt **direct invocation** `Api.greet()`, **public reflection** `publicHello()` và **private reflection** có `setAccessible(true)`.

### Biên dịch với javac --release 17

Từ thư mục chứa `src`, Linux/macOS dùng:

```bash
javac --release 17 --module-source-path src -d mods \
      --add-reads m.consumer=m.provider \
      -m m.provider,m.consumer
```

Windows PowerShell dùng **một dòng** (không dùng dấu `\` nối dòng của Bash):

```powershell
javac --release 17 --module-source-path src -d mods --add-reads m.consumer=m.provider -m m.provider,m.consumer
```

Lệnh đã biên dịch thành công bằng OpenJDK 24 với chế độ `--release 17`. Compiler cần read edge vì `client.Main` import `p.api.Api` nhưng `m.consumer` chưa khai báo `requires m.provider`. Package `p.api` đã export; `p.internal` chỉ được tra cứu tên chuỗi bằng reflection, không import trực tiếp, nên **không cần compiler `--add-exports`** cho trường hợp này.

### Chạy 1 — chỉ thêm read edge

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     -m m.consumer/client.Main
```

Output **chính xác**:

```text
api=api-ok
public=DENIED
private=DENIED
```

Lời gọi public API từ package `p.api` thành công vì m.consumer **đọc m.provider** và `p.api` được export. Nhưng `p.internal` không được export/open: reflective call của public method bị `IllegalAccessException`; private `setAccessible(true)` bị `InaccessibleObjectException`. Code catch hai lỗi và in `DENIED`.

### Chạy 2 — thêm --add-exports cho package nội bộ

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     --add-exports m.provider/p.internal=m.consumer \
     -m m.consumer/client.Main
```

Output **chính xác**:

```text
api=api-ok
public=public-ok
private=DENIED
```

Export thêm `p.internal` cho consumer giúp **public reflection** thành công. Nhưng package chưa opened nên `setAccessible(true)` với private member tiếp tục thất bại.

### Chạy 3 — mở package cho deep reflection

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     --add-exports m.provider/p.internal=m.consumer \
     --add-opens m.provider/p.internal=m.consumer \
     -m m.consumer/client.Main
```

Output **chính xác**:

```text
api=api-ok
public=public-ok
private=private-ok
```

Private reflective invocation giờ thành công bởi package đã mở cho đúng named caller. **Không** nên suy diễn rằng private method trở thành callable từ ordinary source Java; cách truy cập ở đây là reflection.

### Chạy 4 — chỉ --add-opens đối với package nội bộ

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     --add-opens m.provider/p.internal=m.consumer \
     -m m.consumer/client.Main
```

Output **chính xác**:

```text
api=api-ok
public=public-ok
private=private-ok
```

**Điểm tinh tế:** Opening đủ cho reflective access vào **public lẫn non-public members** trong package `p.internal` từ caller đó, dù package không exported. Nhưng `--add-opens` không cho phép compiler `import p.internal.Secret;` để thực hiện ordinary direct invocation nếu package không export.

### Chạy 5 — bỏ read edge ở runtime (cố ý gây lỗi)

```bash
java --module-path mods --add-modules m.provider \
     -m m.consumer/client.Main
```

Vì `m.consumer` không có `requires m.provider` và runtime không có `--add-reads`, khi `client.Main` gọi `Api.greet()`, JVM ném **`IllegalAccessError`** với nội dung chính:

```text
class client.Main (in module m.consumer) cannot access class p.api.Api
(in module m.provider) because module m.consumer does not read module m.provider
```

Đây là **diễn giải phần message trên stderr**, không phải exact stdout hay full stack trace (đường file và dòng có thể thay đổi). Compile flag **không tự tồn tại** ở lần chạy JVM mới. Lệnh `--add-modules m.provider` vẫn được dùng để bảo đảm module provider đã resolved; có module trong configuration **không đồng nghĩa** mọi consumer tự đọc nó.

### Kết luận từ demo

| Runtime flags | Direct `Api.greet()` | Reflective public `Secret.publicHello()` | Private `setAccessible` |
| --- | --- | --- | --- |
| Không có read edge | `IllegalAccessError` | Không tới bước này | Không tới bước này |
| `--add-reads` | Thành công | Từ chối | Từ chối |
| `--add-reads` + `--add-exports` | Thành công | Thành công | Từ chối |
| `--add-reads` + `--add-exports` + `--add-opens` | Thành công | Thành công | Thành công |
| `--add-reads` + `--add-opens` | Thành công | Thành công bằng reflection | Thành công bằng reflection |

Bốn cấu hình chạy thành công ở trên đã được kiểm chứng bằng OpenJDK 24, mã tương thích Java 17.

## 8. Static access khác reflection: đừng chọn cờ theo tên exception một cách máy móc

Có ba thao tác khác nhau:

```java
// Static use của public API (phải compile theo module graph):
String s = p.api.Api.greet();

// Reflection tìm method (chỉ có object Method):
Method m = Class.forName("p.internal.Secret")
        .getDeclaredMethod("privateHello");

// Reflection yêu cầu bỏ access checks tại runtime:
m.setAccessible(true);
```

Đây là **snippet** (cần khai báo import `Method` và ngữ cảnh phù hợp), không phải file Java độc lập.

- Với **static use**, compiler/linker cần read edge và package export.
- Với **lookup metadata**, có thể tìm class/method dù package chưa export/open, theo semantics loader/module và các phép lookup.
- Với **public reflection**, một package exported hoặc opened cho caller có thể đủ tùy operation.
- Với **deep reflection**, `setAccessible(true)` còn phụ thuộc package open, caller module và reflective access rules khác; export public API không tự mở private data.

`Class.forName` thành công **không** chứng minh consumer có quyền truy cập toàn bộ members. `getDeclaredMethod` tìm được private method **không** nghĩa `Method.invoke` được phép gọi.

## 9. Compile-time và runtime có thể cần cấu hình khác nhau

`javac` và `java` là **hai bước riêng**. Nếu source của `m.consumer` trực tiếp import public type trong package **chưa export**, compiler có thể cần:

```text
javac options:
    --add-reads m.consumer=m.provider
    --add-exports m.provider/p.internal=m.consumer

java runtime options (nếu vẫn dùng direct linkage đó):
    --add-reads m.consumer=m.provider
    --add-exports m.provider/p.internal=m.consumer
```

Đây là danh sách options minh họa; để biên dịch/chạy cần bổ sung module source path, output, module path và entry point tương ứng. `--add-opens` chỉ hữu ích khi chương trình thực sự dùng reflection ở runtime, không thể dùng nó để thay export cho Java source compiler.

Ví dụ source direct-import (mã minh họa **chưa chạy độc lập** nếu không đặt vào module và cung cấp imports/flags):

```java
import p.internal.Secret;
String value = Secret.publicHello();
```

Với `p.internal` không export, chương trình dạng đó không được phép chỉ vì runtime `--add-opens` được đặt.

**Thực tế triển khai:** IDE, Gradle/Maven compiler settings, test runner JVM args và production launcher cần phân biệt cấu hình riêng. Một lỗi hay gặp là unit tests chạy vì IDE thêm flags nhưng production `java -m` không có chúng.

## 10. Giải pháp bền vững hơn: module-info.java

Khi kiểm soát được module nguồn và module consumer, nên khai báo rõ nhu cầu bằng descriptors.

Read edge:

```java
module m.consumer {
    requires m.provider;
}
```

Qualified export:

```java
module m.provider {
    exports p.api;
    exports p.internal to m.consumer;
}
```

Qualified open:

```java
module m.provider {
    exports p.api;
    opens p.model to m.framework;
}
```

Chúng là **ba biến thể `module-info.java` khác nhau**, không đặt đồng thời cả ba khai báo `module m.provider` vào một file. Với `opens p.model`, module `m.framework` có thể sử dụng reflective access theo quy tắc phù hợp; điều này **không** khiến package `p.model` trở thành public API để mọi module import trực tiếp.

Dùng launcher flags là một override cho deployment; dùng module descriptor là **một phần hợp đồng module** rõ ràng hơn khi bạn có quyền sửa source.

## 11. Liên hệ module resolution, ModuleLayer và ClassLoader

Trong JPMS, cần phân biệt:

- **Module path**: nơi module finder tìm các module artifacts.
- **Observable module**: module được hệ thống biết có thể resolve.
- **Resolved module**: được đưa vào configuration/layer đang chạy.
- **Readable module**: có read edge từ caller module.
- **Exported package**: được phép dùng public API từ bên ngoài theo rule.
- **Opened package**: được phép dùng reflection sâu từ target module.
- **Defining loader**: loader JVM dùng định nghĩa một `Class<?>`. Class identity của lớp/interface thông thường là `(binary name, defining loader)`.

Hình dung:

```text
--module-path / module finder
           |
           v
module resolution -> module configuration
           |
           v
boot ModuleLayer / custom ModuleLayer
           |
           +-- requires và added read edges
           +-- exports qualified/unqualified
           '-- opens qualified/unqualified
           |
           v
class loader(s) nhận nhiệm vụ tìm/định nghĩa lớp
```

Trong demo, vì consumer không `requires` provider nên launcher có `--add-modules m.provider` để chọn nó vào configuration. `--add-reads` sau đó bổ sung edge; **không** giải quyết cùng một vấn đề.

Khi ứng dụng tạo `ModuleLayer` khác qua `ModuleLayer.defineModulesWithOneLoader`/`defineModulesWithManyLoaders`, configuration, module descriptors và loader mapping có thể khác boot layer. Đừng đoán launcher flags áp dụng cho mọi package trong **mọi layer tạo về sau**. Các API `Module.addReads`, `Module.addExports`, `Module.addOpens` tồn tại nhưng có các quy tắc caller/authority; các frameworks tạo layer cần quản lý thay đổi graph đúng ngữ cảnh, không tùy tiện mở toàn bộ modules.

Dù module code đã được loader tìm thấy, JVM vẫn có thể ném access error theo JPMS. Ngược lại, thêm export/open/read không biến một class chưa tồn tại thành class có thể load được.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Phân biệt nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `module A does not read module B` | Thiếu read edge. | Thêm `requires B;` hoặc `--add-reads A=B` và bảo đảm B resolved. |
| `package p.internal is not visible` tại compiler | Source trực tiếp dùng type của package chưa exported. | Qualified `exports` hoặc `javac --add-exports B/p.internal=A`; thêm reads nếu thiếu. |
| `IllegalAccessError` khi runtime | Compile đã cấp quyền nhưng runtime thiếu read/export. | Lặp options cần thiết tại launcher. |
| `IllegalAccessException` khi reflection gọi public member | Package không được exported/opened cho caller. | Export public API hoặc open nếu cần reflective access rộng hơn. |
| `InaccessibleObjectException` tại `setAccessible(true)` | Caller không có quyền deep reflection tới package. | `opens`/`--add-opens B/p=A` đúng hướng. |
| `ClassNotFoundException` | Module chưa resolved, loader không tìm thấy class hay sai binary name. | Kiểm tra module path/`--add-modules`/loader; add-opens không tạo class. |
| `NoClassDefFoundError` | Dependency missing hoặc linking/initialization fail theo ngữ cảnh. | Phân tích cause/stack, module graph và classpath thực tế. |
| `LayerInstantiationException` | Module/package conflict, resolver/layer constraints. | Sửa configuration; không coi cả ba flags là giải pháp chung. |
| “Unknown module … specified to …” | Sai module name hoặc module không observable/resolved tại giai đoạn option áp dụng. | `java --list-modules`, `jar --describe-module`, module path. |
| Reflection tìm được Method nhưng invoke thất bại | Metadata lookup và access check khác nhau. | Xem `getMethod`/`getDeclaredMethod`, `invoke`, `setAccessible` và caller module. |

Các công cụ kiểm tra:

```bash
java --list-modules
jar --describe-module --file provider.jar
java --show-module-resolution --module-path mods --add-modules m.provider -m m.consumer/client.Main
```

Lệnh `jar` yêu cầu file JAR thật (ví dụ `provider.jar` chỉ là tên minh họa); `java --show-module-resolution` giúp xem resolution nhưng không thay stack trace của lỗi access. Nếu lỗi đến từ reflection trong test runner, xác định **module của caller reflective code**, không mặc định đó là module của test target.

## 13. Những điều ba flags không làm

Các tùy chọn này **không**:

1. Thêm JAR mới vào classpath hoặc module path.
2. Bắt JVM nạp/init toàn bộ classes trong package.
3. Thay đổi parent delegation hoặc class-loader identity.
4. Định nghĩa lại một class đã được nạp bởi cùng defining loader.
5. Cho phép ordinary Java source trực tiếp truy cập private member.
6. Giải quyết mọi lỗi `ClassNotFoundException`/`NoClassDefFoundError`.
7. Thay thế kiểm tra signatures, dependency version hay quyền truy cập của OS.
8. Tạo một sandbox bảo mật cho plugin không tin cậy.

`--add-exports` và `--add-opens` **giảm encapsulation**. Dùng chúng cho legacy/JDK-internal packages có nguy cơ bị phá vỡ khi nâng cấp Java. Nếu cần cả ba flags cho hàng chục modules chỉ để chạy một framework, hãy kiểm tra bản cập nhật framework và thiết kế module trước khi tiếp tục mở rộng ngoại lệ.

`ALL-UNNAMED` cấp quyền rộng tới classpath code hơn một named module cụ thể. Đặt quyền hẹp cho đúng package và đúng consumer để giảm accidental exposure.

## 14. Quy trình chọn cờ theo vấn đề

**Trường hợp A — Direct public API call nhưng consumer không đọc provider**

```text
Error: module A does not read module B
Fix:   requires B; hoặc --add-reads A=B
Check: B đã resolved chưa? package đã exported chưa?
```

**Trường hợp B — Direct code dùng public type trong package không export**

```text
Error: package B/p is not exported to A
Fix:   exports p to A; hoặc --add-exports B/p=A
       (đồng thời bảo đảm A reads B)
Check: cả javac và java có cùng quyền cần thiết
```

**Trường hợp C — Reflection vào private field/method fail**

```text
Error: InaccessibleObjectException at setAccessible
Fix:   opens p to A; hoặc --add-opens B/p=A
Check: A là named module hay ALL-UNNAMED?
```

**Trường hợp D — Public reflection vào package nội bộ**

```text
Can use: exports B/p=A hoặc opens B/p=A khi phù hợp
If only public access is required: ưu tiên export API thay vì deep open
If private access is required: mở đúng package cho đúng caller
```

**Trường hợp E — Lớp vẫn không tìm thấy**

```text
Check: module path / jar layout / module resolution / defining loader
Do not: đổi bừa từ --add-reads thành --add-opens
```

## 15. Câu hỏi tự kiểm tra và đáp án

1. **`--add-reads A=B` có cho phép A truy cập mọi public class trong package không export của B không?** Không. Còn phải xét export.
2. **`--add-exports B/p=A` có cho phép A gọi private method trực tiếp không?** Không. Java access modifiers không bị thay.
3. **`--add-opens B/p=A` giúp `setAccessible(true)` khi nào?** Khi caller A cần deep reflection vào p của B và các conditions khác thỏa mãn.
4. **Opens có giúp compiler import `B/p.Secret` chưa exported không?** Không. Static source access cần export.
5. **Tại sao test có `--add-opens` mà không `--add-exports` vẫn in `public=public-ok`?** Opening cũng cho reflective access đến public members, trong khi bài test gọi bằng reflection.
6. **`ALL-UNNAMED` là named module thực trong module path?** Không. Đó là target đặc biệt cho mọi unnamed modules.
7. **Nếu compiler được cấp `--add-reads`, runtime có tự nhận quyền đó?** Không. Phải dùng launcher flag nếu descriptor chưa có `requires`.
8. **`--add-reads` tự resolve mọi provider module?** Không. Có thể cần `--add-modules` hoặc requires graph phù hợp.
9. **Hai modules ở cùng class loader có thể bỏ qua package exports?** Không; module access vẫn được thực thi.
10. **`Class.forName` thành công có nghĩa `setAccessible(true)` chắc chắn thành công không?** Không; reflective access là bước khác.
11. **Khi sở hữu module source, ưu tiên flags hay descriptor?** Ưu tiên `module-info.java` với `requires`, qualified `exports` và `opens` rõ ràng.
12. **Ba flags có ngăn plugin độc hại truy cập filesystem không?** Không; JPMS không phải process/OS sandbox.

## 16. Tài liệu tham khảo

- [Oracle Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--add-reads`, `--add-exports`, `--add-opens`, `--add-modules` và module path.
- [Oracle Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): read/export overrides ở compile time.
- [Oracle Java SE 21 Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html): lựa chọn exports/opens khi nâng cấp JDK.
- [dev.java — Strong Encapsulation](https://dev.java/learn/modules/strong-encapsulation/): static vs reflective access.
- [dev.java — Add Exports and Opens](https://dev.java/learn/organizing/modules/add-exports-opens/): qualified exceptions và khuyến nghị hạn chế lạm dụng.
- [Java SE 21 — java.lang.Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, động học module access.
- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module configuration/layer và loaders.
- [JLS `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): lý do strong encapsulation JDK 17+.
