# Phân biệt khả năng tìm thấy lớp với quyền truy cập lớp

## 1. Hai câu hỏi khác nhau: “Tìm thấy?” và “Được phép dùng?”

Trong Java, **class loader** giúp JVM tìm hoặc định nghĩa một lớp, nhưng điều đó **không bảo đảm** chương trình gọi có quyền dùng lớp hoặc thành viên của lớp ấy. Từ Java 9, hệ thống module (JPMS) làm sự khác biệt này rõ ràng hơn: **module readability**, **package exports**, **package opens** và **Java access modifiers** đều có vai trò riêng.

Một tình huống điển hình trên Java 17:

- Module `m.library` chứa một class `internal.Secret` và một API công khai `api.PublicApi`.
- Module `m.client` yêu cầu (`requires`) `m.library`.
- `m.client` có thể tìm runtime `Class<?>` của `internal.Secret` bằng `Class.forName("internal.Secret")` trong điều kiện loader nhìn thấy lớp.
- Tuy nhiên `m.library` **không export package `internal`**. `m.client` không thể dùng `internal.Secret` trực tiếp như một type Java trong code nguồn, dù class là `public`.
- Nếu package `internal` cũng **không open** tới `m.client`, nỗ lực deep reflection với `setAccessible(true)` bị từ chối.

**Kết luận trọng tâm:** *Khả năng tìm được class bytes hoặc nhận `Class<?>` là vấn đề loading/lookup; quyền truy cập class/member là vấn đề accessibility, module graph và reflection policy.*

Để tự phân tích một lỗi, tách ít nhất bốn câu hỏi:

1. Class hoặc module **đã nằm trong runtime configuration** và được loader có thể nhìn thấy chưa?
2. Module của caller **đọc được** module chứa type không?
3. Package chứa type được module nguồn **export** hoặc **open** cho caller như thế nào?
4. Class/member có access modifier thích hợp (`public`, `protected`, package-private, `private`) và thao tác đang dùng là **truy cập thường** hay **reflection**?

Không nên chữa mọi `IllegalAccessError` hoặc `InaccessibleObjectException` bằng cách chuyển sang class loader khác; ngược lại, cũng không thể sửa mọi `ClassNotFoundException` chỉ bằng cách thêm `exports`.

## 2. Mô hình JVM: class loading ≠ access checking

Có thể hình dung hai luồng khác nhau:

```text
A. LOOKUP / LOADING
Tên: internal.Secret
       |
       v
Chọn loader / module layer / đường tìm class
       |
       +-- Không thấy -> ClassNotFoundException
       |                hoặc NoClassDefFoundError ở ngữ cảnh VM
       |
       +-- Thấy -> runtime Class<?> được trả về / liên kết khi cần
                        |
                        v
B. ACCESSIBILITY
Caller có đọc module đích? Package export hay open?
Class/member có public/protected/package/private phù hợp?
       |
       +-- Có quyền -> phép dùng cụ thể thành công (nếu không có lỗi khác)
       |
       +-- Thiếu quyền -> compile-time error, IllegalAccessError,
                          IllegalAccessException hoặc
                          InaccessibleObjectException tùy ngữ cảnh
```

Đây là **sơ đồ giải thích**, không phải mọi JVM phải thực hiện từng bước theo một thứ tự cố định. JVM được phép làm một số resolution sớm hoặc muộn; việc `Class.forName` trả thành công cũng chưa nói rằng mọi member của class truy cập được.

### Tầng kiểm tra khác nhau

| Cơ chế | Vai trò chính | Ví dụ quan sát |
|---|---|---|
| **ClassLoader / class path / module path** | Tìm và định nghĩa runtime class, quyết định identity | `Class.forName`, `ClassLoader.loadClass` |
| **Module resolution & readability** | Xác định các named modules được resolve và module nào đọc module nào | `module-info.java` với `requires`; `Module.canRead` |
| **Exports** | Cho module khác truy cập các **public types/members** trong package theo quy tắc thông thường | `exports api;` hoặc `exports api to m.client;` |
| **Opens** | Cho phép **deep reflection** vào package theo phạm vi chỉ định | `opens internal;`, `opens internal to m.client;` |
| **Java language access** | Quy tắc `public`, `protected`, package-private, `private`; thông tin declaring class | Compiler/access checks |
| **Reflective checks** | Kiểm tra accessibility cho `Method.invoke`, `Constructor.newInstance` và khả năng `setAccessible` | `IllegalAccessException` / `InaccessibleObjectException` |

Một package export không làm mọi field `private` trở thành public. Một package open không tự biến source-level reference `internal.Secret` thành hợp lệ trong module client. Và một class loader tìm thấy bytecode không tự mở package của module chứa class đó.

## 3. JPMS: tại sao class có thể tìm thấy mà vẫn không được truy cập?

**Tìm kiếm, phân giải và kiểm tra quyền là ba giai đoạn khác nhau:**

| Kiểm tra | Câu hỏi cần trả lời | Ví dụ biểu hiện lỗi |
| --- | --- | --- |
| Module resolution | Module đích đã được đưa vào runtime graph từ roots và `requires` chưa? | Không tìm thấy module/class phù hợp |
| Readability | Module caller có đọc module đích không? | Lỗi truy cập module khi link/invoke |
| Exports | Package đích có xuất các public types tới caller không? | Import hoặc ordinary access bị từ chối |
| Opens | Package có mở cho deep reflection từ caller không? | `InaccessibleObjectException` khi `setAccessible(true)` |
| Java member access | Type/member có thực sự public hoặc accessible theo ngôn ngữ không? | `IllegalAccessException` hoặc lỗi Java visibility |

Ví dụ descriptor sau cho phép `m.client` đọc `m.library` và truy cập **public** API trong package `api`:

~~~java
module m.client {
    requires m.library;
}
~~~

~~~java
module m.library {
    exports api;
    opens internal to m.client;
}
~~~

Đây là **hai tệp `module-info.java` riêng**. `requires` tạo readability edge; `exports api` cho ordinary public access; `opens internal to m.client` chỉ cho phép reflection sâu vào package `internal` từ đúng module `m.client`. Nó không cho phép Java source trong client tự động `import internal.Secret` nếu không có `exports internal`.

Có thể quan sát runtime graph bằng `callerModule.canRead(targetModule)`, `targetModule.isExported("api", callerModule)` và `targetModule.isOpen("internal", callerModule)`, nhưng từng phép thử **không tự kiểm tra toàn bộ** điều kiện để gọi một class/member. Nếu một module chỉ có trên module path nhưng chưa resolved, phải sửa roots/dependencies trước khi bàn đến `exports` hay `opens`.

Các bài riêng về `Readability, exports và opens` và các launcher flags đi sâu vào `requires transitive`, `requires static`, qualified access, compile/runtime flags và các trường hợp ngoại lệ. Ở đây, ví dụ mục 4 tập trung chứng minh class loader có thể tìm được class trong khi Java access check vẫn từ chối sử dụng nó.

## 4. Java 17 demo: tìm thấy class nhưng không được truy cập

Ví dụ này xây **hai named modules** tách biệt. Một module có package API được export, package internal không export/open. Module client dùng API hợp lệ, vẫn tìm thấy internal class bằng `Class.forName`, nhưng không được phép gọi public method của lớp internal qua reflection bình thường.

### 4.1. Cấu trúc thư mục

```text
src/
  m.library/
    module-info.java
    api/
      PublicApi.java
    internal/
      Secret.java
  m.client/
    module-info.java
    app/
      Main.java
out/
  (thư mục được tạo khi biên dịch)
```

### 4.2. Module thư viện

File `src/m.library/module-info.java`:

```java
module m.library {
    exports api;
}
```

File `src/m.library/api/PublicApi.java`:

```java
package api;

public final class PublicApi {
    private PublicApi() {}

    public static String message() {
        return "API is accessible";
    }
}
```

File `src/m.library/internal/Secret.java`:

```java
package internal;

public final class Secret {
    private Secret() {}

    public static String message() {
        return "internal";
    }
}
```

Class `Secret` là `public`, method `message` là `public`, nhưng **package `internal` không được export/open** trong descriptor của module. Constructor private ở ví dụ này không tham gia phần kiểm tra invoke static method.

### 4.3. Module client

File `src/m.client/module-info.java`:

```java
module m.client {
    requires m.library;
}
```

File `src/m.client/app/Main.java`:

```java
package app;

import api.PublicApi;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(PublicApi.message());

        ClassLoader loader = Main.class.getClassLoader();
        Class<?> secret =
                Class.forName("internal.Secret", false, loader);

        Module clientModule = Main.class.getModule();
        Module libraryModule = secret.getModule();

        System.out.println("Found class: "
                + secret.getName().equals("internal.Secret"));
        System.out.println("Module: " + libraryModule.getName());
        System.out.println("Client reads library: "
                + clientModule.canRead(libraryModule));
        System.out.println("Internal exported: "
                + libraryModule.isExported("internal", clientModule));
        System.out.println("Internal open: "
                + libraryModule.isOpen("internal", clientModule));

        Method publicMethod = secret.getMethod("message");
        try {
            publicMethod.invoke(null);
            System.out.println("Unexpected public invocation success");
        } catch (IllegalAccessException expected) {
            System.out.println("Public reflection denied");
        }

        Method declared = secret.getDeclaredMethod("message");
        try {
            declared.setAccessible(true);
            System.out.println("Unexpected deep reflection success");
        } catch (InaccessibleObjectException expected) {
            System.out.println("Deep reflection denied");
        }
    }
}
```

### 4.4. Biên dịch và chạy

Từ thư mục chứa `src`, chạy với JDK 17:

```bash
javac -d out/m.library \
  src/m.library/module-info.java \
  src/m.library/api/PublicApi.java \
  src/m.library/internal/Secret.java

javac --module-path out -d out/m.client \
  src/m.client/module-info.java \
  src/m.client/app/Main.java

java --module-path out -m m.client/app.Main
```

Với Windows PowerShell, sử dụng từng lệnh một dòng:

```powershell
javac -d out/m.library src/m.library/module-info.java src/m.library/api/PublicApi.java src/m.library/internal/Secret.java
javac --module-path out -d out/m.client src/m.client/module-info.java src/m.client/app/Main.java
java --module-path out -m m.client/app.Main
```

Kết quả stdout trên JDK 17 với cấu hình module sạch đã nêu:

```text
API is accessible
Found class: true
Module: m.library
Client reads library: true
Internal exported: false
Internal open: false
Public reflection denied
Deep reflection denied
```

### 4.5. Từng dòng chứng minh điều gì?

1. `PublicApi.message()` thành công vì `m.client` **requires** `m.library`, package `api` được **exports**, class và method đều public.
2. `Class.forName("internal.Secret", false, loader)` tìm thấy class trong module đã resolve và được loader phù hợp phục vụ. Nó không chứng minh `internal` là package exported.
3. `clientModule.canRead(libraryModule)` true: có readability từ `requires m.library`.
4. `libraryModule.isExported("internal", clientModule)` false: vẫn **không** có ordinary access tới public class trong package internal.
5. `libraryModule.isOpen("internal", clientModule)` false: không có quyền deep reflection theo JPMS.
6. `publicMethod.invoke(null)` gặp `IllegalAccessException` vì `internal.Secret` tuy public nhưng declaring package không được export tới caller module.
7. `declared.setAccessible(true)` gặp `InaccessibleObjectException` vì package cũng không open cho `m.client`.

**Tâm điểm ví dụ:** `Class<?>` được trả về thành công và module còn **readable**, nhưng **truy cập vẫn bị từ chối**. Readability và khả năng tra cứu không thay exports/opens.

Lưu ý: `Class.forName` overload ba tham số `(name, initialize, loader)` chọn loader rõ ràng và cờ `false` tránh yêu cầu initialization tại lời gọi. Nếu `m.library` nằm trong **loader khác** hoặc module chưa resolve, ví dụ cần điều chỉnh đường lookup; đừng suy từ demo này rằng mọi class trong mọi layer đều được loader của caller tìm thấy.

## 5. Minh họa compile-time access: nhìn thấy module vẫn không import được internal

Nếu thêm vào `Main.java`:

```java
import internal.Secret;
```

rồi dùng:

```java
System.out.println(Secret.message());
```

đó là **hai đoạn cố ý vi phạm module encapsulation**, không ghép chúng vào chương trình hoàn chỉnh của phần 4 khi cần runnable.

Trong module `m.client`, `javac` sẽ từ chối vì package `internal` được khai báo trong `m.library` nhưng **không export tới `m.client`**. Việc method là `public` không sửa vấn đề package visibility.

### Sửa đúng bằng exports

Nếu `Secret` thật sự là public API, sửa module declaration:

```java
module m.library {
    exports api;
    exports internal;
}
```

Sau khi biên dịch lại module phù hợp, `m.client` có thể tham chiếu `internal.Secret` (với `requires m.library` đã có). Tuy nhiên export tất cả internal packages thường **không phải thiết kế nên chọn**: package tên `internal` gợi ý nó không phải API ổn định.

Nếu chỉ một module cần API, qualified export:

```java
exports internal to m.client;
```

cũng có thể dùng, với điều kiện module graph/build tương ứng. Nên ưu tiên API package rõ ràng (`api`) thay vì mở rộng một package nội bộ chỉ để chữa lỗi.

## 6. Minh họa deep reflection: dùng opens đúng phạm vi

Nếu mục tiêu là thư viện serialization, dependency injection hoặc test framework phải đọc private members, ordinary `exports` có thể không đủ. Khi đó cân nhắc **opens**.

Trong môi trường chạy, có thể thử:

```bash
java --module-path out \
  --add-opens m.library/internal=m.client \
  -m m.client/app.Main
```

Option `--add-opens` mở package `internal` của `m.library` cho module `m.client` tại runtime. Trong chương trình phần 4, `libraryModule.isOpen("internal", clientModule)` sẽ phản ánh quyền mở package; `declared.setAccessible(true)` có thể thành công.

Tuy nhiên **chương trình phần 4 đang in một thông báo “Unexpected...” khi `setAccessible` thành công**, vì nó được viết để kiểm chứng nhánh *denied* ở cấu hình mặc định. Do đó không coi stdout cố định ở phần 4 là kết quả mong đợi cho cấu hình có `--add-opens`; hãy thay đổi code test để kiểm tra thành công nếu muốn làm thử nghiệm thứ hai.

Một biến thể thiết kế lâu dài là thêm vào `module-info.java`:

```java
module m.library {
    exports api;
    opens internal to m.client;
}
```

Đây là **descriptor minh họa**. Khi biên dịch module thư viện tách biệt, compiler có thể cảnh báo nếu module mục tiêu chưa được nhìn thấy trong quá trình compile; nên dùng build module-aware phù hợp. `opens` khác với `exports`: nó cho phép reflective access theo quy tắc, **không tự cấp source-level direct import**.

### Dùng setAccessible không phải “mẹo vượt JPMS”

Trước Java 9, nhiều ví dụ reflection gọi `setAccessible(true)` rồi kỳ vọng truy cập mọi private member. Với strong encapsulation ở Java hiện đại, `setAccessible` được kiểm tra theo module boundary và có thể ném `InaccessibleObjectException`.

Các API liên quan:

- `AccessibleObject.setAccessible(boolean)`: ném exception nếu không thể bật access suppression.
- `AccessibleObject.trySetAccessible()`: trả `false` nếu không bật được, hữu ích khi muốn kiểm tra thay vì dùng exception.
- `Method.invoke` hoặc `Constructor.newInstance`: có access checks của lời gọi nếu chưa được cho phép bỏ qua.
- `MethodHandles.Lookup`, `privateLookupIn`: có cơ chế capability/access riêng; không xem method handles là lối đi bỏ qua opens.

Khi library của bạn cần reflection sâu, hãy yêu cầu module chủ quản **opens đúng package tới đúng consumer**, không phát tán `--add-opens ...=ALL-UNNAMED` trên toàn runtime nếu không cần.

## 7. Exports, opens và protected/private theo bảng quyết định

| Tình huống | `requires`/readability | `exports` | `opens` | Java modifier |
|---|---|---|---|---|
| Client gọi trực tiếp `api.PublicApi.message()` | Có | `api` export tới client | Không cần | Class/method phải accessible, thường `public` |
| Client import `internal.Secret` bình thường | Có | `internal` phải export tới client | Chỉ opens **không đủ** | Class/method accessible |
| Reflection gọi public method của public class thuộc module khác | Module graph/lookup đúng | Package export tới caller thường đủ cho ordinary reflection access | Có thể dùng opens kết hợp `setAccessible` khi thích hợp | Public class/member cần kiểm tra |
| Reflection truy cập private field của module khác bằng `setAccessible(true)` | Module/lookup phù hợp | Exports **không đủ** | Package thường cần open tới caller | Private member vẫn cần suppress access |
| Tìm `Class<?>` bằng `Class.forName` | Loader thấy type và module đã resolve | Không nhất thiết | Không nhất thiết | Không nói lên quyền dùng member |
| `MethodHandles.privateLookupIn` sang class thuộc module khác | Access/lookup requirements của API | Không tự đủ | Package cần open tới caller theo contract | Lookup phải có quyền thích hợp |

**Phân biệt chính xác:**

- `exports` hướng tới **ordinary compile-time/runtime access to public types and members**.
- `opens` hướng tới **runtime deep reflection**.
- `requires` tạo **readability**; module chỉ cần được loader tìm thấy không đủ cho ordinary access.
- `public` là access modifier trong Java, không override module encapsulation.

Một class `public` bên trong package không exported khác với class package-private trong package đã exported; hai nguyên nhân thiếu quyền này cần sửa theo cách khác nhau.

## 8. ClassLoader không tự áp đặt toàn bộ JPMS graph

Đôi khi developer thử:

```java
ClassLoader targetLoader =
        ClassLoader.getSystemClassLoader();
Class<?> type = targetLoader.loadClass("internal.Secret");
```

Nếu lời gọi tìm được `Class<?>`, đó **không phải lời hứa** rằng mọi code ở mọi module có thể gọi constructor, method hay access fields của type này.

Tương tự, dùng:

```java
Class.forName("internal.Secret", false, targetLoader);
```

chỉ chủ động chọn loader và initialization behavior. Quyền dùng class/member còn phải xét module của caller, module của type, package export/open và Java modifier.

### ClassLoader visibility và module readability là hai chiều độc lập

- **Loader visibility**: class binary name được loader có thể tìm/định nghĩa hoặc trả lại bằng delegation không?
- **Module readability**: module chứa caller có quan hệ đọc module chứa type theo JPMS không?
- **Exports/opens**: package nào được consumer truy cập theo ordinary/reflection semantics?

Một module có thể **readable** nhưng package không exported; ví dụ phần 4 chứng minh điều này. Một loader có thể biết một class nhưng code của module caller không được phép dùng type trong source. Ngược lại, source code có `requires` và `exports` đúng nhưng runtime thiếu JAR/module hoặc loader dùng sai thì vẫn **không tìm được class**.

## 9. ModuleLayer và class loader: không giả định lớp nào cũng ở application loader

JPMS cho phép nhiều `ModuleLayer`, một configuration có thể resolve modules được định nghĩa bằng loaders riêng hoặc loader được chỉ định. Hai điều này không nên bị đánh đồng:

- **ModuleLayer** mô tả tập modules và quan hệ resolution, readability, service binding trong cấu hình tương ứng.
- **ClassLoader** là cơ chế nạp/định nghĩa runtime classes; layer có thể dùng nhiều loaders và loader có thể định nghĩa classes thuộc các modules phù hợp.
- **Exports/opens/readability** là quan hệ giữa modules, không phải quan hệ giữa hai loader objects.

Khi tự tạo layer, loader của caller không nhất thiết nhìn thấy module mới. Có thể tìm loader được layer dùng cho named module:

```java
ClassLoader moduleLoader = layer.findLoader("m.plugin");
Class<?> pluginType =
        Class.forName("plugin.EntryPoint", false, moduleLoader);
```

Đây là **snippet minh họa**, cần biến `layer` là `ModuleLayer` có module `m.plugin`, và class tương ứng tồn tại. `layer.findLoader` có thể ném `IllegalArgumentException` nếu module không tồn tại trong layer; việc tìm `Class<?>` thành công không đồng nghĩa caller có quyền truy cập vào package của `plugin.EntryPoint`.

### Dùng ModuleLayer.findModule

```java
java.util.Optional<Module> found = layer.findModule("m.plugin");
```

Đoạn minh họa có tác dụng xác định module trong layer hoặc parent layers, nhưng `Optional<Module>` không phải `Class<?>` và không có nghĩa package của module được export.

Nếu chạy nhiều phiên bản plugin trong nhiều layers, cần xét đồng thời **loader identity, module graph, exports/opens và shared API contracts**. Cách ly class loaders có thể giữ nhiều runtime class identities khác nhau, nhưng một API `public` chưa chắc accessible khi các module không có readability/export edges phù hợp.

## 10. Class path và named module: tại sao ví dụ khác nhau?

Trên class path truyền thống, các class nằm trong **unnamed module** của loader tương ứng. Code trong unnamed module thường đọc được tất cả modules; unnamed modules export/open tất cả packages của mình theo ngữ nghĩa JPMS.

Tuy nhiên vẫn còn Java access modifiers: class package-private không thành public, field private không tự truy cập được từ package khác. Khác biệt giữa *findable* và *accessible* vẫn tồn tại cả khi chưa dùng `module-info.java`.

Named modules đưa thêm boundaries:

- `requires` / readability
- `exports`
- `opens`
- `ModuleLayer` và module resolution
- Các access checks trong reflection

Vì thế code reflection chạy được ở class path có thể bắt đầu ném `InaccessibleObjectException` khi migrate sang named module mà chưa mở package thích hợp.

**Không nên suy rằng đưa JAR từ module path về class path luôn là hướng sửa tốt**. Làm vậy thay mô hình encapsulation và có thể ảnh hưởng dependencies, service resolution hoặc tên module. Hãy hiểu nhu cầu API và cấu hình access mong muốn trước khi đổi packaging.

## 11. Phân biệt các ngoại lệ và lỗi thường gặp

| Hiện tượng | Ngữ cảnh thường gặp | Điều cần xem |
|---|---|---|
| **`ClassNotFoundException`** | `Class.forName` hoặc `ClassLoader.loadClass` không tìm tên class yêu cầu | Module đã resolved? Loader đúng? Class path/module path đúng? |
| **`NoClassDefFoundError`** | VM cần class trong linking/runtime nhưng không thể lấy/định nghĩa như kỳ vọng, hoặc initialization trước thất bại | Missing dependency, class initialization cause, loader mapping |
| **`IllegalAccessError`** | VM linking/resolution phát hiện illegal access giữa runtime types/members | `exports`, visibility, access modifiers, runtime module graph |
| **`IllegalAccessException`** | Reflection invocation/field access/constructor access bị chặn bởi Java/member/module accessibility | Class/member public? Package exported? Có suppress access? |
| **`InaccessibleObjectException`** | `setAccessible(true)` không bật được quyền suppress access | Package `opens` tới caller chưa? Có module boundary? |
| **Lỗi javac “package ... is not visible”** | Client source trực tiếp import package không export hoặc module unreadable | `requires`, `exports`, package path |
| **`LayerInstantiationException`** | Định nghĩa layer mới thất bại do ràng buộc cấu hình/loader/package | ModuleLayer configuration/loader mapping và package conflicts |
| **`ServiceConfigurationError`** | Provider discovery/instantiation fail theo `ServiceLoader` | Provider type identity, module `uses/provides`, loader/resource visibility |

Không nên nói một ngoại lệ cụ thể chỉ có đúng một nguyên nhân: ví dụ `IllegalAccessException` có thể do private member hoặc do JPMS package không exported trong một lời gọi reflective. Đọc **message + stack trace + runtime module graph**.

### Ba lỗi có vẻ giống nhau nhưng cách sửa khác nhau

**Trường hợp A — không tìm được class:**

```text
ClassNotFoundException: plugin.EntryPoint
```

Kiểm tra module đã resolved, đúng loader của `ModuleLayer`, class name, JAR/class path và dependencies. Thêm `exports` không cứu được nếu JVM chưa tìm được class bytes.

**Trường hợp B — tìm thấy nhưng ordinary access bị chặn:**

```text
package internal is declared in module m.library,
which does not export it to module m.client
```

Đây là tình huống compile-time điển hình: `m.client` đã thấy module nhưng chưa được export package. Giải quyết bằng thiết kế public API thích hợp hoặc qualified export nếu chủ đích cho phép.

**Trường hợp C — tìm thấy class, nhưng deep reflection bị chặn:**

```text
InaccessibleObjectException:
module m.library does not "opens internal" to module m.client
```

Xem liệu framework thật sự cần reflection vào internals không. Nếu có, mở package đúng phạm vi hoặc dùng public API đã export; đổi loader không phải mặc định giải pháp.

## 12. Kiểm tra access tại runtime bằng Module API

Có thể dùng các phương thức chuẩn trên Java 17:

```java
Module source = someType.getModule();
Module caller = callerType.getModule();

boolean readable = caller.canRead(source);
boolean exported = source.isExported("api", caller);
boolean opened = source.isOpen("internal", caller);
```

Đây là **snippet minh họa** yêu cầu `someType`, `callerType` là class tokens đã lấy hợp lệ. Kết quả mô tả runtime module graph, hữu ích cho diagnostics; nó không thay thế kiểm tra access modifiers của từng member.

Các câu hỏi nên ghi trong log:

1. `callerType.getModule().getName()` là gì? Có phải unnamed module (`getName() == null`) không?
2. `someType.getModule().getName()` là gì? Class thuộc layer/loader nào?
3. `caller.canRead(source)` có true không?
4. `source.isExported(packageName, caller)` có true không?
5. `source.isOpen(packageName, caller)` có true không?
6. `someType.getModifiers()` và modifiers của method/field có đáp ứng Java access checks không?
7. Loader trả class có đúng với expected module `Class.getModule()` không?

**Không suy đoán package từ tên class bằng cách tách dấu chấm ngây thơ nếu có arrays/nested classes**. Với class thông thường Java 9+, `Class.getPackageName()` giúp lấy package name phù hợp; với array types, cần kiểm tra semantics của API.

### Quan sát module graph bằng launcher

Dùng JVM log để thấy module được resolve:

```bash
java --show-module-resolution --module-path out -m m.client/app.Main
```

Lệnh này thường in thêm thông tin module resolution trước kết quả chương trình, hữu ích để phân tích vì sao module hiện diện/không hiện diện. Đừng dùng output log này thay cho kiểm tra `exports`/`opens` của package.

Xem mô tả module:

```bash
java --module-path out --describe-module m.library
```

Thông tin giúp biết module declaration công khai; qualified exports/opens và runtime overrides có thể cần quan sát thêm các arguments khi chạy.

## 13. Khi cần add-exports, add-opens, add-reads?

Các launcher options hữu ích trong migration, test hoặc compatibility:

| Option | Tác dụng | Phạm vi vấn đề |
|---|---|---|
| `--add-reads m.client=m.library` | Bổ sung readability edge tại runtime | Caller module chưa đọc target |
| `--add-exports m.library/internal=m.client` | Export package `internal` tới module client | Ordinary/public access ở boundary |
| `--add-opens m.library/internal=m.client` | Open package `internal` tới client | Deep reflection |
| `--add-modules m.library` | Bổ sung root module tham gia resolution | Module có trên path nhưng chưa resolved |
| `--module-path out` | Chỉ định đường tìm modules | Module discovery |

**Không coi những option là đồng nghĩa**. `--add-opens` không tự giải quyết mọi compile-time errors; `--add-exports` không tự cho phép private reflection; `--add-reads` không biến package private thành public; `--add-modules` không tự chọn class loader đúng cho mọi layer.

Đối với named module applications, ưu tiên khai báo chuẩn trong `module-info.java` khi thiết kế API cho phép. Dùng options runtime như `--add-opens` để chẩn đoán, migration hoặc tích hợp framework có yêu cầu thực tế; không mở toàn bộ internals mà không xét tác động encapsulation.

### API-level adjustments

`java.lang.Module` còn có các phương thức như `addReads`, `addExports`, `addOpens`, nhưng chúng có **ràng buộc caller/ownership**, không phải API tùy tiện để module bất kỳ mở internals của module khác. Không giả định có thể gọi `targetModule.addOpens("internal", callerModule)` từ bất kỳ code host nào và luôn thành công.

## 14. Vì sao mở package có thể cần nhưng vẫn không đủ?

Khi code đã có loader và module access phù hợp, còn nhiều điều kiện riêng:

- **Constructor/method tồn tại không?** `NoSuchMethodException`, `NoSuchFieldException` có thể xuất hiện dù package exported.
- **Object target có đúng type không?** `ClassCastException` liên quan runtime type identity, không chữa bằng opens.
- **Provider có thật sự implement shared interface không?** `ServiceLoader` có thể từ chối provider có class identity sai.
- **Module/package conflict có xảy ra không?** Định nghĩa layer và class loader có thể thất bại vì package overlap hoặc layer configuration.
- **Static initialization có lỗi không?** `Class.forName(name)` overload một tham số yêu cầu initialization, có thể gây `ExceptionInInitializerError`.
- **Access modifier vẫn có ý nghĩa.** Exported public class không giúp một private method được gọi trực tiếp.
- **Security hoặc runtime policy khác** vẫn có thể ảnh hưởng khả năng thực hiện một hành động sau khi tìm type; loader và module access không phải hệ sandbox toàn diện.

Vì vậy, phân tích lỗi theo giai đoạn: **module resolved → class findable → caller readable → package exported/open → member accessible → operation successful**. Đây là checklist chẩn đoán, không phải thứ tự nội bộ bất biến của JVM.

## 15. Các lỗi tư duy phổ biến

| Sai lầm | Sửa lại |
|---|---|
| “`Class.forName` thành công thì chắc chắn `newInstance`/`invoke` thành công.” | Lookup không bảo đảm access tới constructor/method. |
| “`requires` đã đủ để dùng mọi package của module.” | Cần package `exports` thích hợp cho ordinary access. |
| “Public class trong package internal ai cũng dùng được.” | Named module có thể không export package đó. |
| “`exports` cho phép reflection vào mọi private field.” | Deep reflection thường cần `opens` tới caller. |
| “`opens` giúp code import type internal ở compile time.” | Ordinary source access cần `exports`, không chỉ `opens`. |
| “Không load được class thì thêm `--add-opens`.” | Phải kiểm tra class/module lookup path và resolution trước. |
| “ClassLoader thấy class đồng nghĩa module caller có `canRead`.” | Visibility của loader và readability của module là hai quan hệ khác nhau. |
| “Chuyển sang TCCL chắc chắn bỏ qua JPMS.” | TCCL ảnh hưởng đường lookup của API dùng nó, không cấp module access rights. |
| “Đổi tên loader thì class mới truy cập được.” | Loader name không phải JPMS export/open policy. |
| “Mọi module đều do system loader định nghĩa.” | Module layers có thể dùng loader khác; cần `layer.findLoader` hoặc kiểm tra runtime. |
| “`setAccessible(true)` luôn có hiệu lực như Java 8.” | Strong encapsulation có thể ném `InaccessibleObjectException`. |
| “`IllegalAccessException` đồng nghĩa class không tồn tại.” | Thường class/member đã được tìm thấy nhưng thao tác reflective không được phép. |

## 16. Bài tập tự kiểm tra

**Câu 1.** Module `m.client` có `requires m.library` nhưng package `internal` của `m.library` không export. Client được gọi `internal.Secret.publicMethod()` trực tiếp không?

**Đáp án:** Không. Readability có nhưng package chưa exported tới caller module; public modifier của class/method chưa đủ.

**Câu 2.** `Class.forName("internal.Secret")` tìm được class. Điều đó chứng minh package `internal` được export chưa?

**Đáp án:** Chưa. Lookup và accessibility là hai câu hỏi khác nhau.

**Câu 3.** `exports internal to m.client;` có làm private fields của `internal.Secret` tự động accessible qua `setAccessible(true)` từ module client không?

**Đáp án:** Không. Export liên quan ordinary public access. Deep reflection thường cần `opens internal to m.client;` hoặc một quyền truy cập hợp lệ theo API.

**Câu 4.** Chỉ có `opens internal to m.client;` mà không export. Client có thể compile `import internal.Secret;` không?

**Đáp án:** Không theo ordinary source access. `opens` hỗ trợ reflective access, không thay `exports`.

**Câu 5.** Vì sao chương trình demo in `Client reads library: true` và `Internal exported: false` đồng thời?

**Đáp án:** `m.client` có `requires m.library` nên đọc library; nhưng `m.library` chỉ export package `api`, không export `internal`. Hai tính chất độc lập.

**Câu 6.** Gọi `setAccessible(true)` vào member trong package không opened trên named module thường ném gì?

**Đáp án:** `InaccessibleObjectException` khi không được phép suppress Java language access checks theo `AccessibleObject` và JPMS.

**Câu 7.** Một module mới trong child `ModuleLayer` có class `plugin.EntryPoint` nhưng app loader không thấy tên đó. Điều gì cần kiểm tra?

**Đáp án:** Module đã resolve trong layer chưa, loader mà layer sử dụng (`layer.findLoader`), rồi readability/export/open của module với caller. Không chỉ đổi `exports`.

**Câu 8.** Muốn thư viện `m.client` gọi public API của `m.library` qua source code, cần những yếu tố nào?

**Đáp án:** Module phải được resolve và readable; package public API phải export tới client; class/member phải accessible theo Java modifiers; class bytes phải tìm được qua loader đúng.

**Câu 9.** Khi nào dùng `--add-opens` thay vì `--add-exports`?

**Đáp án:** Khi yêu cầu là deep reflection (ví dụ truy cập private members từ framework) và package chưa open. Nếu mục tiêu là ordinary public access, xem `exports`/`--add-exports` cùng readability.

## 17. Tóm tắt và nguồn chuẩn

**Năm điều cốt lõi cần nhớ:**

1. **Findability:** loader và module configuration quyết định có tìm được runtime class không.
2. **Readability:** `requires`/module graph quyết định caller module đọc module nào.
3. **Exports:** quyết định ordinary access tới public types/members của package qua module boundary.
4. **Opens:** cho phép deep reflection vào package theo phạm vi cho phép; không tự cấp direct import.
5. **Member access:** `public`/`protected`/package-private/`private` và reflective access checks vẫn có hiệu lực ngoài các quan hệ module.

Trong Java 17, điều nên hỏi sau khi `Class.forName` thành công **không chỉ là** “đã có `Class<?>` chưa?”, mà còn là “**module chứa caller được dùng type/member này theo cách nào?**”.

**Nguồn tài liệu chính thức:**

- [JLS 17 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, qualified exports/opens và source-level rules.
- [JLS 17 — `6.6 Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): class/member access và package visibility.
- [Java SE 17 — java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và module runtime APIs.
- [Java SE 17 — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, `getModule`, `getClassLoader`.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`/`trySetAccessible` và module checks.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layers và `findLoader`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module graph, access control và các launcher options.