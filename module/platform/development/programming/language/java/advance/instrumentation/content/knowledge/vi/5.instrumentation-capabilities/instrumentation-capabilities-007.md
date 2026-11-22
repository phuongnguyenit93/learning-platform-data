# `isModifiableModule` và điều kiện trước khi thay đổi quan hệ module

> **Mục tiêu:** Hiểu chính xác `Instrumentation.isModifiableModule(Module)` kiểm tra điều gì; khi nào một Java agent có thể gọi `Instrumentation.redefineModule(...)` để bổ sung quan hệ **reads**, **exports**, **opens**, **uses** hoặc **provides**; cách xác nhận đúng module, đúng package và đúng bên nhận trước khi thay đổi; và cách kiểm tra kết quả mà không nhầm việc mở module với việc sửa class bytecode.

Bài học thuộc chủ đề **Khả năng Instrumentation** của Java 17+. Tâm điểm là hành vi JPMS (Java Platform Module System) tại **runtime** trong JVM. Java agent thường cần quyền đọc helper class hoặc reflection vào một package đóng; kiểm tra `isModifiableModule` là một bước tiền điều kiện quan trọng, nhưng kết quả `true` **không đủ** để chứng minh mọi thay đổi định làm đều hợp lệ và an toàn.

## 1. Vì sao instrumentation phải quan tâm tới module?

Từ Java 9, JPMS cho phép ứng dụng chia mã thành các **named modules**. Một module khai báo dependency và quyết định package nào được xuất hoặc mở cho module khác. Ví dụ:

```java
// module-info.java của ứng dụng
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
    // com.example.orders.internal không được export/open.
}
```

Một Java agent muốn chèn probe vào `com.example.orders.internal.OrderRepository` có thể cần thực hiện các thao tác sau:

- Bytecode đã biến đổi gọi một helper type nằm trong **module khác**, nhưng module nguồn chưa có quan hệ `reads` cần thiết.
- Agent hoặc framework muốn dùng reflection để truy cập field/method private trong `com.example.orders.internal`, nhưng package này chưa được **open** tới module gọi reflection.
- Thư viện triển khai muốn sử dụng một public API trong package chưa **export** cho module cần dùng.
- Một thành phần thực sự tham gia `ServiceLoader` cần bổ sung declaration `uses`/`provides` ở runtime.

Những tình huống đó nói tới **quan hệ giữa module**, không nhất thiết nói tới việc thay bytes của một `.class`. `Instrumentation` hỗ trợ thay đổi quan hệ bằng `redefineModule(...)`. Trước khi thực hiện, agent cần xác định đúng **Module object** thuộc JVM hiện tại, kiểm tra khả năng sửa của module và kiểm chứng các tham số.

## 2. Hai API then chốt

```java
boolean isModifiableModule(Module module);

void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
```

Đây là chữ ký API để tham chiếu (không phải file Java độc lập; `Instrumentation`, `Set`, `Map` và `List` thuộc JDK). Cả hai method được bổ sung từ **Java 9** trên `java.lang.instrument.Instrumentation`. Một Java agent nhận `Instrumentation` qua `premain(String, Instrumentation)` khi dùng `-javaagent`, hoặc qua `agentmain(String, Instrumentation)` nếu cơ chế agent động phù hợp đang được hỗ trợ.

- **`isModifiableModule(module)`**: hỏi JVM có cho phép module này được thay đổi qua `redefineModule` hay không. `null` gây `NullPointerException`.
- **`redefineModule(...)`**: bổ sung quan hệ mới vào runtime module graph. Nó **chỉ mở rộng** tập reads/exports/opens/uses/provides, không thể thu hẹp hoặc loại bỏ những quan hệ đã tồn tại.
- **Với unnamed module**: `isModifiableModule(unnamedModule)` luôn trả `true`, nhưng `redefineModule` tác động lên unnamed module là **no-op**. Không được suy luận “trả true nên lần gọi sẽ thay đổi điều gì đó”.
- **Với named module không thể sửa**: `redefineModule` có thể ném `UnmodifiableModuleException`; hãy kiểm tra khả năng trước khi gọi và vẫn xử lý lỗi tại điểm thực hiện.
- `redefineModule` **khác hoàn toàn** `redefineClasses` và `retransformClasses`: đây là sửa quan hệ module, không viết lại bytecode trong method.

Một dòng kiểm tra thường gặp:

```java
Module target = SomeApplicationClass.class.getModule();

if (!target.isNamed()) {
    throw new IllegalArgumentException("Expected a named target module");
}
if (!instrumentation.isModifiableModule(target)) {
    throw new IllegalStateException("Target module is not modifiable");
}
```

Đoạn trên là **mẫu logic** dùng trong agent đang có sẵn biến `instrumentation` và type `SomeApplicationClass`, không phải chương trình tự chạy. Bài thực hành bên dưới có đủ tệp để chạy độc lập.

## 3. Phân biệt read, export và open trước khi thêm quan hệ

Ví dụ có hai named module:

```text
com.example.app            (module chứa code cần quan sát)
com.example.agent.helper   (module chứa helper phục vụ agent)
```

Ba khái niệm dễ nhầm:

| Quan hệ | Hướng và câu hỏi | Điều nó cho phép | Điều nó không tự làm |
| --- | --- | --- | --- |
| **reads** | `app → helper`: module `app` có đọc được `helper` không? | Phép giải quyết truy cập theo module graph, cần cho những tham chiếu tới module khác | Không tự export package bên helper |
| **exports** | `app/package → helper`: package của `app` có được export cho `helper` không? | Truy cập thông thường tới public API của package theo điều kiện visibility và đọc module | Không tự cho phép deep reflection tới member private |
| **opens** | `app/package → helper`: package có được open cho `helper` không? | Cho phép deep reflection (`setAccessible`, lookup phù hợp) theo phạm vi mở | Không phải lời cam kết mọi lời gọi/method đều thành công; không biến private thành public trong source |

Những câu hỏi quan sát trên runtime `Module`:

```java
boolean canRead   = app.canRead(helper);
boolean exported  = app.isExported("com.example.app.api", helper);
boolean opened    = app.isOpen("com.example.app.internal", helper);
```

Đoạn code này minh họa cú pháp trong ngữ cảnh có hai biến `Module app`, `Module helper`. `Module.isExported(package, other)` và `Module.isOpen(package, other)` kiểm tra quan hệ **tới một module cụ thể**; bản overload không có `other` hỏi về export/open vô điều kiện. Kết quả `isExported/isOpen` **không kiểm tra** module nhận có đọc được module nguồn hay không: muốn hiểu khả năng truy cập thực tế có thể phải kiểm tra cả hướng `reads`.

**Đặc điểm dễ bỏ sót:** tại runtime, package **open** tới một module được xem là **exported** tới module đó cho một số kiểm tra truy cập; vì vậy `isExported(pkg, other)` có thể trả `true` sau khi package được mở. Đừng suy luận nhầm từ giá trị đó rằng source `module-info.java` đã có `exports`, hoặc rằng build lại ứng dụng vẫn nhận được quyền giống vậy.

### Reads và opens là hai bài toán khác nhau

Giả sử agent dùng reflection trên một method `private`. Thêm một `reads` edge **chưa đủ** để vượt qua strong encapsulation. Cần package owner mở đúng package tới module nơi **code reflection đang chạy**. Ngược lại, thêm `opens` chỉ để cho phép bytecode gọi một public helper class có thể rộng hơn quyền cần thiết; trong trường hợp đó hãy xem xét quan hệ reads/exports phù hợp.

Với helper code trong **unnamed module** của agent, package `java.lang.instrument` còn mô tả một số read edges được JVM tự bố trí cho module của các class đã biến đổi. Vì vậy không nên mặc định mọi bytecode probe đều phải tự gọi `redefineModule` để thêm read edge. Trước hết xác minh lỗi truy cập thực tế và `Module.canRead(...)`.

## 4. Toàn bộ sáu đối số của `redefineModule`

Đối số đầu tiên là **module nguồn được sửa**; năm đối số còn lại mô tả những phần mở rộng:

| Đối số | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `module` | `Module` | Module **được thay đổi** (không phải module nhận quyền) |
| `extraReads` | `Set<Module>` | Những module bổ sung mà `module` được đọc |
| `extraExports` | `Map<String, Set<Module>>` | Package của `module` được export thêm tới từng tập module |
| `extraOpens` | `Map<String, Set<Module>>` | Package của `module` được open thêm tới từng tập module |
| `extraUses` | `Set<Class<?>>` | Service type được khai báo sử dụng thêm bởi `module` |
| `extraProvides` | `Map<Class<?>, List<Class<?>>>` | Service type và danh sách implementation được khai báo cung cấp thêm |

Các collection **được phép rỗng** (ví dụ `Set.of()` và `Map.of()`) khi không thay đổi loại quan hệ đó; nhưng chúng **không được `null`**. Những nơi một map `extraExports`, `extraOpens` hay `extraProvides` có entry, **tập/list tương ứng phải không rỗng**.

### Ví dụ: chỉ thêm read edge

```java
// app, helper đều là Module đã xác nhận:
instrumentation.redefineModule(
    app,
    Set.of(helper), // app đọc helper
    Map.of(),       // Không export package nào thêm
    Map.of(),       // Không open package nào thêm
    Set.of(),       // Không thêm service uses
    Map.of()        // Không thêm service providers
);
```

Sau lời gọi thành công, kiểm tra `app.canRead(helper)`. Điều này **không** tự export package của `helper`; nếu helper là named module có package kín, cần xét riêng chiều export từ `helper` tới `app`. Một class cần cả graph read edge **và** quyền truy cập package/type/method phù hợp.

### Ví dụ: chỉ mở một package cho agent

```java
// app là chủ sở hữu package internal, agentModule là Module của agent:
instrumentation.redefineModule(
    app,
    Set.of(),
    Map.of(),
    Map.of("com.example.app.internal", Set.of(agentModule)),
    Set.of(),
    Map.of()
);
```

Chỉ **package có sẵn trong `app`** mới được dùng làm key. Sau thao tác, kiểm tra:

```java
boolean nowOpen =
        app.isOpen("com.example.app.internal", agentModule);
```

Đây là thay đổi **từ `app` tới `agentModule`**, không phải từ agent tới app. Nó không có hiệu lực với một package không thuộc `app`, và `extraOpens` **không nhận wildcard như `"com.example.*"`**.

### Ví dụ: export có chọn lọc

```java
instrumentation.redefineModule(
    app,
    Set.of(),
    Map.of("com.example.app.api", Set.of(helper)),
    Map.of(),
    Set.of(),
    Map.of()
);
```

`extraExports` giúp module nhận sử dụng public API phù hợp của package, **không mở deep reflection vào private**. Cần đánh giá read edge từ `helper` tới `app` nếu đó là hướng truy cập.

### `extraUses` và `extraProvides` có ràng buộc riêng

- Mỗi phần tử `extraUses` là một **service type** (`Class<?>`). Khi mở rộng uses, agent phải tự bảo đảm service type **truy cập được** tại từng nơi code instrumented sử dụng nó; `redefineModule` không tự chứng minh mọi điều kiện truy cập đó.
- Mỗi key của `extraProvides` là service type. Mỗi value là **list không rỗng** các implementation class. Từng provider phải **thuộc module đang được sửa** và là implementation hợp lệ của service type. Một implementation từ module khác hoặc không implement service có thể gây `IllegalArgumentException`.
- Không dùng `extraProvides` để tùy tiện thêm class vào module; API chỉ thay đổi service provider declaration ở runtime, không tạo file `.class` hay load lại JAR.

Agent chỉ nên thêm uses/provides nếu thực sự cần tích hợp một service. Bài toán mở reflection vào package thông thường chỉ cần `extraOpens`, như thí nghiệm.

## 5. Tiền điều kiện phải kiểm tra trước `redefineModule`

Một quy trình cẩn thận gồm các kiểm tra dưới đây.

### 5.1. Xác định đúng runtime Module object

Một tên module đơn giản không phải lúc nào đủ định danh, đặc biệt khi ứng dụng dùng nhiều **module layer** hoặc class loader. Hãy xuất phát từ **class thực sự cần instrument**:

```java
Module target = targetClass.getModule();
```

Hoặc, nếu chắc chắn module ở **boot layer**, dùng:

```java
Module target = ModuleLayer.boot()
        .findModule("com.example.app")
        .orElseThrow();
```

Khi dùng module layer tùy biến, không được đoán module nằm ở boot layer. `Module.getName()`, `getLayer()`, `getClassLoader()` và `getPackages()` hỗ trợ xác minh. Nếu lấy sai `Module` object thì `redefineModule` có thể sửa **một module trùng tên nhưng khác instance**, không phải target đang chạy.

### 5.2. Phân biệt named và unnamed

```java
if (!target.isNamed()) {
    // JPMS: isModifiableModule trả true, nhưng redefineModule là no-op.
    // Chọn giải pháp phù hợp với unnamed module; không báo "đã mở package".
}
```

Unnamed module thường đã có quan hệ đọc và open rộng theo quy tắc riêng. Gọi `redefineModule` trên đó không có giá trị mở thêm một quan hệ. `isModifiableModule` trả `true` ở đây **không phải xác nhận một thay đổi sẽ xảy ra**.

### 5.3. Hỏi JVM về khả năng sửa module

```java
boolean modifiable = instrumentation.isModifiableModule(target);
if (!modifiable) {
    throw new IllegalStateException("Target module cannot be redefined");
}
```

Giá trị là đặc tính/capability của module trong JVM hiện tại; không nên đoán từ việc module thuộc `java.base`, một JAR ứng dụng hay một thư viện. `isModifiableModule` **không thay thế** các phép kiểm điều kiện dữ liệu bên dưới.

**Đừng nhầm sang `isModifiableClass(...)`:** phép kiểm này trả lời một class có thể tham gia redefinition/retransformation hay không. `isRetransformClassesSupported`/`isRedefineClassesSupported` là các capability khác. Không cần chúng chỉ để gọi `redefineModule`, và `isModifiableModule` không bảo đảm transformer có quyền sửa method bytes.

### 5.4. Kiểm tra package thuộc module nguồn

Đối với `extraExports`/`extraOpens`, key là tên package đầy đủ, **không phải** tên class, chuỗi `module/package`, package wildcard hoặc đường dẫn chứa dấu `/`.

```java
String pkg = "com.example.app.internal";
if (!target.getPackages().contains(pkg)) {
    throw new IllegalArgumentException(
            "Package does not belong to target module: " + pkg);
}
```

Nếu package không thuộc module, API có thể ném `IllegalArgumentException`. Không thêm một package mới vào module qua `redefineModule`.

### 5.5. Kiểm tra chính xác bên nhận

Đối với exports/opens, các `Set<Module>` phải không rỗng. Mỗi phần tử phải là **module nhận quyền thực sự**, lấy từ class/layer phù hợp.

```java
Module agentModule = MyAgent.class.getModule();
if (agentModule == target) {
    throw new IllegalArgumentException(
            "Expected different source and receiving modules");
}
```

Đoạn trên là ví dụ về chính sách khi muốn mở quyền cho **agent ở module khác**. Bản thân API không cấm trường hợp hai biến trỏ cùng module; module tự đọc và có thể truy cập package của mình theo quy tắc JPMS. Đừng hiểu guard này là ràng buộc do JDK bắt buộc.

**Lưu ý quan trọng về phạm vi:** nếu `agentModule` là **unnamed module** của system class loader, mở package tới nó nghĩa là mở tới **toàn bộ code trong cùng unnamed module**, không chỉ một class agent. Muốn giảm diện tích quyền, cân nhắc helper ở named module riêng nếu kiến trúc cho phép.

### 5.6. Kiểm tra các collection và tính nhất quán của dịch vụ

- Không đối số hoặc phần tử key/value nào được `null`; `NullPointerException` được API đặc tả cho những trường hợp đó.
- Không truyền một entry `extraExports` hay `extraOpens` với `Set.of()` rỗng; `extraProvides` không có list rỗng.
- Package key phải thật sự thuộc **module nguồn**.
- Provider class phải thuộc module nguồn và implement service type; kiểm tra `provider.getModule()` và quan hệ kiểu trước khi gọi.
- Với `extraUses`, tự xác minh service type có thể truy cập ở các điểm mã sẽ dùng. Đừng suy ra mọi lookup sẽ thành công chỉ vì module có uses edge.

Dùng `Map.of`/`Set.of` giúp tránh `null` ở ví dụ đơn giản, nhưng một cấu trúc dữ liệu đến từ cấu hình bên ngoài vẫn cần validation trước khi tạo collection và gọi API.

### 5.7. Xác định thay đổi có thật sự cần không

Đọc quan hệ hiện tại trước khi yêu cầu thay đổi:

```java
if (!target.isOpen(pkg, agentModule)) {
    instrumentation.redefineModule(
            target, Set.of(), Map.of(),
            Map.of(pkg, Set.of(agentModule)),
            Set.of(), Map.of());
}
```

Cách này làm intent dễ review và tránh thêm quyền đã có. Tuy nhiên trong JVM có nhiều agent, trạng thái có thể đổi giữa hai câu lệnh. `redefineModule` được thiết kế an toàn cho gọi đồng thời; **vẫn phải** bắt lỗi và kiểm tra lại trạng thái sau khi gọi. Không coi check-then-act là một transaction hoặc cơ chế khóa bảo mật.

## 6. Ví dụ Java 17+ chạy được: agent mở một package của named module

Thí nghiệm sử dụng:

- Một **named module** `demo.target` với package `demo.target.internal` không được export/open.
- Một Java agent trên class path (thuộc **unnamed module** của system class loader) nhận `Instrumentation` qua `premain`.
- Agent kiểm tra `isModifiableModule`, xác minh package có thật, gọi `redefineModule` chỉ để thêm **qualified open** tới module của agent.
- Sau đó agent dùng reflection gọi một private static method để thấy hiệu quả. Không có bytecode transformation hoặc nạp agent động.

### 6.1. Cấu trúc tệp

```text
module-open-demo/
├── agent.mf
├── agent-src/
│   └── ModuleAccessAgent.java
└── src/
    └── demo.target/
        ├── module-info.java
        └── demo/
            └── target/
                ├── Main.java
                └── internal/
                    └── SecretBox.java
```

Các thư mục `out/` sẽ được tạo lúc biên dịch, không cần có sẵn.

**Tệp `src/demo.target/module-info.java`:**

```java
module demo.target {
    // Cố ý không exports/opens package demo.target.internal.
}
```

**Tệp `src/demo.target/demo/target/Main.java`:**

```java
package demo.target;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app=running");
    }
}
```

**Tệp `src/demo.target/demo/target/internal/SecretBox.java`:**

```java
package demo.target.internal;

public final class SecretBox {
    private SecretBox() {}

    private static String status() {
        return "READY";
    }
}
```

`SecretBox.status()` là private. Mã nằm trong module khác không thể dùng reflection để mở quyền truy cập tới private method nếu package vẫn đóng.

**Tệp `agent-src/ModuleAccessAgent.java`:**

```java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;

public final class ModuleAccessAgent {
    public static void premain(String arguments, Instrumentation inst)
            throws Exception {

        Module target = ModuleLayer.boot()
                .findModule("demo.target")
                .orElseThrow(() -> new IllegalStateException(
                        "Target module is not in the boot layer"));
        Module agentModule = ModuleAccessAgent.class.getModule();
        String pkg = "demo.target.internal";

        System.out.println("target named=" + target.isNamed());
        System.out.println("agent unnamed=" + !agentModule.isNamed());

        if (!target.isNamed()) {
            throw new IllegalStateException("Expected a named module");
        }
        if (!target.getPackages().contains(pkg)) {
            throw new IllegalStateException("Target package is missing");
        }

        boolean modifiable = inst.isModifiableModule(target);
        System.out.println("modifiable=" + modifiable);
        if (!modifiable) {
            System.out.println("module update=skipped");
            return;
        }

        boolean before = target.isOpen(pkg, agentModule);
        System.out.println("open before=" + before);

        if (!before) {
            inst.redefineModule(
                    target,
                    Set.of(),
                    Map.of(),
                    Map.of(pkg, Set.of(agentModule)),
                    Set.of(),
                    Map.of()
            );
        }

        boolean after = target.isOpen(pkg, agentModule);
        System.out.println("open after=" + after);
        if (!after) {
            throw new IllegalStateException("Open edge was not established");
        }

        Class<?> type = Class.forName(
                "demo.target.internal.SecretBox",
                false,
                ClassLoader.getSystemClassLoader());
        Method method = type.getDeclaredMethod("status");
        method.setAccessible(true);
        System.out.println("reflect=" + method.invoke(null));
    }
}
```

Giải thích các điểm quan trọng:

1. Agent dùng `ModuleLayer.boot()` vì chính lệnh chạy sẽ đưa module `demo.target` vào boot layer. Với module layer khác, phải tìm module ở layer chính xác.
2. `ModuleAccessAgent.class.getModule()` trả module của code gọi reflection. Trong layout này đó là unnamed module của system class loader.
3. `getPackages().contains(pkg)` xác nhận package có mặt trong module đích; tránh lỗi key package không thuộc module.
4. `isModifiableModule` được hỏi **trước** khi sửa quan hệ. Với JVM không hỗ trợ, agent in `module update=skipped` và không thử `redefineModule`.
5. `extraReads`, `extraExports`, `extraUses`, `extraProvides` là collection rỗng. **Chỉ** `extraOpens` có một package và một module nhận.
6. `isOpen(pkg, agentModule)` là phép kiểm kết quả thực trên runtime module graph.
7. `Class.forName(...)` có thể tìm định nghĩa lớp, nhưng muốn `setAccessible(true)` để truy cập private method vẫn cần package open phù hợp. Không có bước mở package, deep reflection từ module khác thường bị từ chối với `InaccessibleObjectException`.
8. `method.invoke(null)` hợp lệ vì `status()` là static. `"READY"` là kết quả không phụ thuộc thời gian hoặc ngẫu nhiên.

**Tệp `agent.mf`** (manifest kết thúc bằng một newline; giữ dòng trống cuối nếu có thể):

```text
Manifest-Version: 1.0
Premain-Class: ModuleAccessAgent

```

### 6.2. Biên dịch và đóng gói

Tại thư mục gốc `module-open-demo`, ví dụ lệnh **PowerShell**:

```powershell
New-Item -ItemType Directory -Force -Path out/modules, out/agent |
    Out-Null

javac --module-source-path src -d out/modules -m demo.target
javac -encoding UTF-8 -d out/agent agent-src/ModuleAccessAgent.java

jar --create --file out/module-access-agent.jar --manifest agent.mf `
    -C out/agent .
```

Nếu chạy từ Bash, dùng các lệnh tương đương:

```bash
mkdir -p out/modules out/agent
javac --module-source-path src -d out/modules -m demo.target
javac -encoding UTF-8 -d out/agent agent-src/ModuleAccessAgent.java
jar --create --file out/module-access-agent.jar --manifest agent.mf \
    -C out/agent .
```

Các lệnh tạo:

- `out/modules/demo.target/` chứa module đã biên dịch, gồm `module-info.class`.
- `out/agent/` chứa class agent ngoài named module.
- `out/module-access-agent.jar` có `Premain-Class` cho `-javaagent`.

Chạy với **JDK 17+** có `java.instrument`:

```bash
java -javaagent:out/module-access-agent.jar \
    --module-path out/modules \
    --module demo.target/demo.target.Main
```

Ở **PowerShell**, thay dấu tiếp dòng `\` bằng backtick, hoặc chạy trên một dòng:

```powershell
java -javaagent:out/module-access-agent.jar --module-path out/modules --module demo.target/demo.target.Main
```

### 6.3. Output trên HotSpot/OpenJDK hỗ trợ module redefinition

Với `module-info.java` như trên và không thêm `--add-opens` từ dòng lệnh, stdout dự kiến:

```text
target named=true
agent unnamed=true
modifiable=true
open before=false
open after=true
reflect=READY
app=running
```

Nếu JVM hiện tại báo `modifiable=false`, agent chủ động in `module update=skipped` và ứng dụng vẫn có thể vào `main`; không xem đây là lỗi của `isModifiableModule`. Nếu package vốn đã open do cấu hình startup, `open before=true` và agent không cần gọi `redefineModule`, nhưng `open after` vẫn true.

**Kết luận của thí nghiệm:** Mở `demo.target.internal` cho module nơi agent chạy cho phép agent dùng deep reflection với private method. Quan hệ được thay đổi **tại runtime**, không sửa `module-info.java`, không thay bytecode của `SecretBox`, và không tự mở package cho mọi named module.

## 7. Thí nghiệm đối chứng và kiểm tra hậu điều kiện

Để thấy rõ điều kiện có ý nghĩa, hãy thay đổi **cục bộ bản thí nghiệm** rồi biên dịch/chạy lại theo từng trường hợp.

### Trường hợp A — module không chứa package yêu cầu

Nếu đổi `pkg` trong agent thành `demo.target.missing`, bước:

```java
target.getPackages().contains(pkg)
```

trả false và agent ném `IllegalStateException` do guard trước khi gọi API. Nếu bỏ guard rồi đưa package không thuộc module vào map `extraOpens`, API có thể ném `IllegalArgumentException`. **Không nên** bỏ guard khi viết agent thật.

### Trường hợp B — package đã open

Chạy thử với một cấu hình runtime đã mở đúng package:

```bash
java --add-opens demo.target/demo.target.internal=ALL-UNNAMED \
    -javaagent:out/module-access-agent.jar \
    --module-path out/modules \
    --module demo.target/demo.target.Main
```

Trong demo, `open before` có thể là true vì `--add-opens` đã cấp quyền tương ứng. Agent kiểm tra và không yêu cầu mở lại. Lưu ý `ALL-UNNAMED` mở cho **các unnamed modules** theo chính sách của launcher, rộng hơn một module named helper riêng. Chỉ dùng nó trong bài thử có kiểm soát.

### Trường hợp C — đổi bên nhận thành sai module

Giả sử agent mở package tới module khác nhưng code reflection vẫn chạy trong `ModuleAccessAgent` (unnamed module). Việc module kia có quyền không có nghĩa agent cũng có quyền: `isOpen(pkg, agentModule)` có thể vẫn false, và `setAccessible(true)` sẽ bị từ chối. Cần kiểm tra **đúng module chứa code reflection**, không chỉ có một `opens` entry bất kỳ.

### Trường hợp D — named vs unnamed source module

Nếu target class chỉ nằm trên class path, `targetClass.getModule().isNamed()` là false. `isModifiableModule(target)` vẫn trả true theo JDK API, còn `redefineModule(target, ...)` không tạo thêm quan hệ. Vì vậy guard `target.isNamed()` tránh thông báo sai rằng đã thực sự mở một package.

### Trường hợp E — thêm `reads` mà không `exports`

Module A được bổ sung `extraReads=Set.of(B)`, nhưng package cần dùng trong B không exported tới A. Một đoạn code trong A vẫn có thể gặp lỗi truy cập public type của B vì quan hệ đọc và quan hệ export là hai điều kiện khác nhau. Cần xác nhận **hướng quyền** của cả hai; đừng thêm bừa `opens` vào B để thay thế cho việc hiểu lỗi.

## 8. Cơ chế thay đổi có giới hạn và không có bước “undo”

`redefineModule` có tính **additive**: có thể bổ sung, không thể thu hồi một read edge, export, open hay service declaration qua API đó. Nếu agent vô tình mở một package nhạy cảm cho một module không phù hợp, không có đối số “remove” để hoàn tác trong cùng JVM. Trong thực tế, muốn khôi phục trạng thái module graph ban đầu thường phải **khởi động lại JVM** với cấu hình/agent đã sửa.

Cần phân biệt:

```text
isModifiableModule(module) → Có thể dùng redefineModule cho module này?
redefineModule(module, ...) → Bổ sung quan hệ module tại runtime
isModifiableClass(clazz)   → Class này có khả năng sửa định nghĩa/biến đổi bytecode?
retransformClasses(clazz)  → Thử biến đổi bytecode của class đã nạp
```

Một module có thể modifiable trong khi một số class của nó không modifiable. Tương tự, `redefineModule` thành công **không xác nhận** bytecode transformer hoạt động và không khiến một method tự động được instrument. Đây là các capability và đường đi độc lập cần kiểm tra theo mục đích.

Việc `Instrumentation.redefineModule` hỗ trợ gọi đồng thời để nhiều agent cập nhật cùng module **không đồng nghĩa** cả hệ thống đã được bảo đảm logic đúng khi nhiều agent cùng sửa quyền. Mỗi agent nên cấp đúng quyền tối thiểu, không dùng các snapshot đã cũ như kết luận bất biến, và kiểm tra hậu điều kiện.

## 9. Lỗi thường gặp và nguyên nhân

| Hiện tượng | Giải thích/cách xử lý |
| --- | --- |
| `isModifiableModule(target)` trả `false` | JVM không cho sửa module đó; dừng thay đổi, cân nhắc cấu hình startup hoặc thiết kế khác |
| `isModifiableModule(null)` ném `NullPointerException` | Module chưa xác định hợp lệ; kiểm tra nguồn và layer trước |
| Trả `true` với unnamed module nhưng không có thay đổi | Đúng API: `redefineModule` trên unnamed module là no-op |
| `UnmodifiableModuleException` | `redefineModule` được gọi trên module JVM không cho sửa; không bỏ qua lỗi |
| `IllegalArgumentException` do `extraExports`/`extraOpens` | Key không thuộc package của source module, hoặc target set trong map rỗng |
| `IllegalArgumentException` do `extraProvides` | Provider không thuộc source module, không implement service type, hoặc list rỗng |
| `NullPointerException` từ `redefineModule` | Đối số hoặc phần tử key/value của collection có `null` |
| `InaccessibleObjectException` lúc `setAccessible` | Package chưa open đúng tới module **của code reflection**; kiểm tra `isOpen(pkg, requesterModule)` |
| `IllegalAccessError` khi gọi helper public | Thường liên quan quan hệ đọc/export hoặc visibility giữa module; xác minh `canRead` và `isExported` cùng hướng |
| `ClassNotFoundException` | Class không có trong module graph/class loader đúng; `redefineModule` không tạo class hay sửa class path |
| `isOpen` đúng nhưng vẫn lỗi reflection | Có thể chọn nhầm `Class`/module/layer, signature/method sai, hoặc có điều kiện truy cập khác; kiểm tra stack trace và loại exception cụ thể |
| Agent làm việc trong wrong layer | Tên module trùng nhưng `Module` object không phải target; lấy từ `targetClass.getModule()` khi có class cần instrument |

Lỗi không phải lúc nào cũng do module graph. Các quyền OS, class loader, method signature, chính sách runtime và việc agent nạp không thành công có thể gây lỗi ở vị trí khác. Không tự động mở rộng toàn bộ `java.base` hoặc dùng `ALL-UNNAMED` với nhiều package chỉ vì thấy exception đầu tiên.

## 10. Checklist trước khi triển khai trên JVM thật

1. **Đúng mục tiêu:** xác định đúng JVM, class loader, module layer và `Module` của class cần quan sát.
2. **Đúng loại module:** biết source là named hay unnamed; không coi unnamed true là thay đổi có hiệu lực.
3. **Khả năng sửa:** gọi `isModifiableModule` và xử lý `false`; không nhầm với retransform class.
4. **Lý do cụ thể:** xác định có thật sự cần thêm read, export, open hay service declaration nào.
5. **Phạm vi tối thiểu:** chỉ mở/export package tồn tại, chỉ tới module nhận thực sự cần thiết; hiểu phạm vi của unnamed module.
6. **Dữ liệu hợp lệ:** không null, không collection value rỗng tại những entry bị cấm; provider class hợp lệ.
7. **Không cấp dư quyền:** nếu chỉ cần public API, đừng tự tiện mở private reflection; nếu không cần sửa module thì giữ nguyên.
8. **Xử lý lỗi:** dự phòng `UnmodifiableModuleException`, `IllegalArgumentException`, `NullPointerException` và lỗi truy cập khi thực thi.
9. **Kiểm tra sau gọi:** dùng `canRead`, `isExported`, `isOpen` đúng chiều và thử thao tác nhỏ nhất cần thiết.
10. **Đánh giá vòng đời:** quan hệ đã thêm không có cơ chế rollback bằng `redefineModule`; cần cách khởi động lại/triển khai lại nếu sửa sai.
11. **Kiểm tra công cụ thực:** sau mở module, vẫn kiểm tra bytecode có instrument đúng, logging/trace có overhead phù hợp, không rò rỉ dữ liệu và hoạt động trên JDK mục tiêu.
12. **Quản lý thay đổi:** ghi rõ tại sao agent cần quyền, module nào cấp quyền cho ai, và cách phát hiện cấu hình quyền rộng ngoài dự kiến.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `isModifiableModule` trả `true`. Có thể lập tức gọi `redefineModule` với bất cứ package nào?  
**Trả lời:** Không. Package cho `extraExports/extraOpens` phải thuộc module nguồn, value set phải hợp lệ, đối số không được null và quyền phải đúng mục tiêu.

**Câu 2.** `isModifiableModule` trả gì cho unnamed module?  
**Trả lời:** Luôn `true`, nhưng `redefineModule` với unnamed module là no-op.

**Câu 3.** Module `app` cần gọi helper public trong `helper`. Chỉ thêm `reads` là đủ?  
**Trả lời:** Chưa chắc. Hướng `app → helper` cần read edge, và package chứa helper public còn phải được export/accessible cho `app` theo JPMS.

**Câu 4.** Cần gọi private method của `app.internal` bằng reflection trong agent. Nên thêm `exports` hay `opens`?  
**Trả lời:** Cần kiểm tra và có thể thêm **qualified `opens`** từ `app.internal` tới **module chứa code reflection**; export không tự cấp quyền deep reflection tới private.

**Câu 5.** Vì sao không đưa `Map.of("com.example.*", Set.of(agentModule))` vào `extraOpens`?  
**Trả lời:** Key phải là **tên package đầy đủ có thật** trong module nguồn; wildcard không được hỗ trợ.

**Câu 6.** `redefineModule` có thể gỡ một `opens` edge đã thêm không?  
**Trả lời:** Không. API chỉ mở rộng quan hệ, nên kế hoạch quay lại cấu hình ban đầu thường là khởi động lại JVM.

**Câu 7.** Thấy `isModifiableClass(SomeClass.class) == false` có kết luận module chứa class không modifiable?  
**Trả lời:** Không. Hai phép kiểm hỏi hai capability khác nhau.

**Câu 8.** Vì sao demo kiểm tra `target.isOpen(pkg, agentModule)` sau lời gọi?  
**Trả lời:** Đó là hậu điều kiện thực tế trong runtime: đúng package đã mở tới đúng module nhận quyền. `redefineModule` không bảo đảm các giả định còn lại về class loader hay method tự động đúng.

## Tài liệu tham khảo chính thức

- [JDK 21 — `Instrumentation.isModifiableModule` và `redefineModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): chữ ký, ngoại lệ, tính bổ sung và unnamed-module no-op.
- [JDK 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `isNamed`, `getPackages`, `canRead`, `isExported`, `isOpen` và kiểm tra quan hệ runtime.
- [JDK 21 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách tạo agent, `premain`/`agentmain`, hỗ trợ instrument code trong named modules.
- [JDK 21 — `UnmodifiableModuleException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableModuleException.html): lỗi khi module không cho sửa.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): mục tiêu module graph và strong encapsulation.

**Ghi nhớ:** `isModifiableModule` là **cổng kiểm tra khả năng**, không phải giấy phép sửa mọi thứ. Chỉ gọi `redefineModule` sau khi xác nhận đúng module nguồn, đúng hướng quan hệ, package/service hợp lệ và phạm vi quyền tối thiểu; sau đó kiểm tra kết quả với API `Module`. Thay đổi module graph không tự động thay bytecode và không thể đảo ngược bằng một lời gọi `redefineModule` khác.