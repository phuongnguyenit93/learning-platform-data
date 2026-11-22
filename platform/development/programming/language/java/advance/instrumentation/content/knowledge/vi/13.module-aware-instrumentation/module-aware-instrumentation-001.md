# Named module, unnamed module và khả năng đọc lớp helper khi Instrumentation

Khi Java agent sửa bytecode của một lớp thuộc **named module**, bytecode mới thường muốn gọi các **helper classes** do agent cung cấp: ghi log, đo thời gian, tạo span, đếm sự kiện, thu thập metric. Từ Java 9, có hai hàng rào cần hiểu riêng: **module readability** (module có được đọc module chứa helper không?) và **class-loader visibility** (class loader có tìm/định nghĩa được helper class không?). Nếu còn chạm vào package của named module, phải phân biệt thêm **exports** và **opens**.

Một named module thông thường **không mặc định đọc unnamed module của classpath**. Vì vậy “helper JAR đã nằm trên classpath” không đồng nghĩa với việc bytecode trong named module có thể liên kết trực tiếp đến helper. Java Instrumentation có một cơ chế hỗ trợ quan trọng: **khi một lớp thực sự được biến đổi**, JVM sắp xếp để module của lớp ấy đọc **unnamed module của bootstrap class loader** và **unnamed module của class loader nạp class agent chính**. Đây là cơ chế giúp bytecode được chèn có thể gọi helper của agent mà không cần khai báo `requires` trong `module-info.java`.

Bài này làm rõ giới hạn của cơ chế tự động đó, cách chủ động thêm quan hệ đọc bằng `Instrumentation.redefineModule(...)`, khi nào cần `--add-reads` / `--add-exports` / `--add-opens`, và một ví dụ Java 17+ đã chạy kiểm chứng cả trường hợp thất bại lẫn thành công.

## 1. Named module và unnamed module khác nhau thế nào?

**Named module** có tên và descriptor `module-info.class` (hoặc một dạng module có tên tương ứng, ví dụ automatic module), chẳng hạn:

```java
module demo.named {
}
```

Đó là nội dung của tệp `module-info.java`. Khi chạy với `--module-path` và `-m demo.named/...`, Java tạo một module có tên `demo.named`. Những quan hệ đọc bình thường được khai báo bằng `requires` hoặc thêm động qua các cơ chế module system.

**Unnamed module** là module không có tên mà class loader gán cho các lớp nó định nghĩa không thuộc named module, điển hình là lớp trên **classpath**. Các class loader khác nhau có thể có **các unnamed module khác nhau**; không nên nói “JVM có đúng một unnamed module” trong mọi tình huống.

| Tính chất | Named module thường | Unnamed module |
| --- | --- | --- |
| Tên module | `Module.getName()` trả tên không null | `getName() == null`; `isNamed() == false` |
| Khai báo read edge | Thường từ `requires`, hoặc thêm qua VM option/API | Đọc tất cả các module quan sát được theo quy tắc JPMS |
| Package exports | Chỉ package được export phù hợp | Export **mọi package** thuộc unnamed module |
| Package opens | Chỉ package mở phù hợp | Mở **mọi package** thuộc unnamed module |
| Nơi tìm class | Module path hoặc nguồn được loader/module system xác định | Thường classpath hoặc đường tìm kiếm helper của bootstrap/system loader |
| Đọc unnamed module khác | Không phải quyền mặc định của ordinary named module | Có khả năng đọc các unnamed module khác theo quy tắc của unnamed module |
| Kiểm tra runtime | `module.isNamed()`, `module.canRead(other)` | Tương tự, `isNamed() == false` |

**Automatic module** là trường hợp đặc biệt: JAR không có `module-info.class` nhưng được đặt trên module path có thể trở thành module **có tên** với quy tắc readability rộng hơn, bao gồm đọc unnamed module. Đừng áp dụng kết luận “named module không đọc unnamed” cho automatic module mà không xét loại module đó. Ví dụ thực hành dùng **explicit named module** với `module-info.java` rõ ràng.

## 2. Ba vấn đề khác nhau: readability, exports/opens, class loader

Hãy xem một phương thức trong module `demo.named` muốn gọi:

```java
return demo.helper.Helper.message();
```

Helper nằm trên classpath và được system class loader định nghĩa trong unnamed module. Để lời gọi bytecode có thể liên kết thành công, phải chú ý:

1. **Readability:** module `demo.named` có đọc module chứa `demo.helper.Helper` không? Dùng `named.canRead(helperModule)` để kiểm tra.
2. **Package access:** package `demo.helper` có được export tới `demo.named` không? Với **unnamed module**, mọi package đều được export, nên trường hợp bài học này không cần mở export riêng ở phía helper.
3. **Loader visibility:** class loader tham gia nạp/lien kết lớp `Target` có thể tìm được class `demo.helper.Helper` không? `--add-reads` không tự đưa một JAR vào classpath, module path hay bootstrap search path.

Với **deep reflection** (ví dụ đọc private field từ agent), xuất hiện điều kiện thứ tư: package phải được **opens** thích hợp. `exports` cho truy cập Java thông thường tới các public types; `opens` phục vụ deep reflection. Chúng không phải hai tên của cùng thao tác.

Có thể tự kiểm tra module bằng:

```java
// Đoạn minh họa trong method; không phải chương trình độc lập.
Module caller = targetClass.getModule();
Module helper = helperClass.getModule();

System.out.println(caller.isNamed());
System.out.println(helper.isNamed());
System.out.println(caller.canRead(helper));
```

**`ClassLoader.loadClass("demo.helper.Helper")` có thể tìm ra một class dù module gọi class ấy chưa có read edge.** Việc loader tìm được bytes/lớp không chứng minh liên kết bytecode trực tiếp đã có quyền truy cập. Thí nghiệm dưới đây sẽ cho thấy `loadClass(...)` thành công nhưng `Target.hello()` vẫn có thể ném `IllegalAccessError`.

## 3. Quan hệ đọc mặc định: chiều nào được phép?

Sơ đồ khái niệm trước khi agent can thiệp:

```text
                           Named module
                             demo.named
                                  |
                                  | reads java.base (implicit)
                                  v
                               java.base

System class loader
  └── Unnamed module
        └── demo.helper.Helper

demo.named  -X->  system loader unnamed module
            chưa có read edge theo mặc định
```

**Chiều đọc quan trọng:**

- **Unnamed module → named modules:** unnamed module được thiết kế để tương tác rộng với các module quan sát được.
- **Explicit named module → unnamed module:** không có `requires` nào trong `module-info.java` có thể khai báo một unnamed module bằng tên. Vì vậy không tự động có read edge ấy.
- **Named module → một named module khác:** thông thường dùng `requires other.module`, và vẫn phải xét package exports.

Nói “classpath là nơi chứa tất cả class nên module nào cũng truy cập được” là sai trong JPMS. Classpath quyết định cách tìm class trong phạm vi loader; **readability** vẫn là điều kiện module độc lập.

## 4. Java Instrumentation hỗ trợ đặc biệt cho lớp được transform

Tài liệu chính thức của package `java.lang.instrument` mô tả cơ chế hỗ trợ cho agent chứa helper trong đường tìm kiếm của bootstrap loader hoặc loader nạp agent:

> JVM tự bố trí module của **lớp đã được transform** đọc unnamed module của **hai loader**: bootstrap loader và loader đã nạp main agent class.

Từ đó có các kết luận thực tế:

- Agent class thường được nạp bởi **system class loader** vào unnamed module của loader đó.
- Helper đặt trên đường tìm kiếm của **system loader** có thể được bytecode đã instrument gọi trực tiếp nếu named module được JVM thêm read edge tương ứng và loader tìm thấy helper.
- Helper mà agent sắp xếp nạp bởi **bootstrap loader** cũng có một unnamed module riêng và có thể được tạo read edge.
- Cơ chế này **không mặc định thêm read edge tới mọi unnamed module của mọi custom class loader** trong JVM.
- Quan hệ đọc là một phần điều kiện liên kết; JVM **không tự tạo JAR helper**. Agent phải đóng gói/sắp xếp class helper có thể nạp được.
- Cơ chế hỗ trợ áp dụng cho module của lớp **thực sự được transform**, không có nghĩa chỉ cần JVM khởi động với `-javaagent` thì tất cả named modules đều đọc unnamed module.

### 4.1. Callback được gọi chưa chắc đồng nghĩa lớp đã được biến đổi

Trong `ClassFileTransformer.transform(...)`:

- Trả `null`: transformer **không thay đổi bytes** ở lượt đó.
- Trả một `byte[]` mới: transformer cung cấp bytes cho định nghĩa; JVM nhận lớp đó là trường hợp **được transform**.

Trong thí nghiệm kiểm chứng ở phần 7, callback cho `demo/named/Target` **có được gọi** nhưng **trả `null`** thì read edge tự động **không xuất hiện** trên JVM thử nghiệm. Khi cùng callback trả **`bytes.clone()`** (classfile hợp lệ, nội dung không khác), JVM ghi nhận lớp được transform và read edge xuất hiện. Đây là một cách cực kỳ rõ để phân biệt **“agent đã đăng ký/đã quan sát”** với **“class đã qua biến đổi được áp dụng”**.

**Không nên dùng `bytes.clone()` trong agent production chỉ để thêm read edge.** Nếu mục tiêu thực sự là thêm một quan hệ đọc, `redefineModule(...)` là công cụ rõ ràng hơn; trả bytes mới vô ích có thêm chi phí và có thể tương tác với các transformer khác. Bài thực hành dùng clone chỉ để kiểm chứng cơ chế được đặc tả.

### 4.2. Agent ở unnamed module không mặc nhiên được truy cập private của named module

Chiều **named module của Target đọc unnamed module của Helper** là để **Target gọi Helper**. Nếu **Agent muốn phản xạ vào private class/member của module Target**, cần kiểm tra một bài toán **theo chiều ngược lại**:

- Agent module có đọc named module đích không?
- Package Target có **exports** cho loại truy cập public thích hợp không?
- Package có **opens** tới agent module để sử dụng `setAccessible(true)` hoặc deep reflection không?
- Class đích có thật sự được loader làm cho khả dụng không?

Việc JVM tự thêm read edge phục vụ helper **không tự mở mọi package** của named module cho agent.

## 5. Chủ động thêm read edge bằng `Instrumentation.redefineModule`

Khi một agent cần thay quan hệ đọc mà không muốn dựa vào một lần transform cụ thể, có thể dùng:

```java
void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
```

Đây là **chữ ký rút gọn để giải thích**, không phải đoạn code hoàn chỉnh. Ý nghĩa từng phần:

| Tham số | Tác dụng |
| --- | --- |
| `module` | Module **được cập nhật**, ví dụ `Target.class.getModule()`. |
| `extraReads` | Thêm các module mà `module` có thể đọc. |
| `extraExports` | Thêm quyền export những package **của `module`** tới các module đích cụ thể. |
| `extraOpens` | Thêm quyền mở package **của `module`** cho deep reflection. |
| `extraUses` | Thêm service types mà module sử dụng. |
| `extraProvides` | Thêm service provider mapping của module. |

Với chỉ một yêu cầu **named Target đọc system unnamed Helper**, lời gọi gọn là:

```java
// Trích đoạn bên trong premain/agentmain, có Instrumentation inst.
Module target = ModuleLayer.boot()
        .findModule("demo.named")
        .orElseThrow();
Module helper = ClassLoader.getSystemClassLoader()
        .getUnnamedModule();

if (!inst.isModifiableModule(target)) {
    throw new IllegalStateException("Target module cannot be modified");
}

inst.redefineModule(
    target,
    java.util.Set.of(helper), // extraReads
    java.util.Map.of(),        // extraExports
    java.util.Map.of(),        // extraOpens
    java.util.Set.of(),        // extraUses
    java.util.Map.of()         // extraProvides
);
```

Lệnh đó **chỉ thêm** read edge từ `target` tới `helper`. Không làm thay đổi module descriptor `module-info.class` trên đĩa; read edge được thêm vào mô hình module của JVM đang chạy.

**Các giới hạn quan trọng:**

- `redefineModule` chỉ **mở rộng** reads/exports/opens/uses/provides, **không thu hồi** chúng.
- Với **unnamed module**, `redefineModule` là **no-op**; `isModifiableModule(unnamed)` vẫn trả `true` theo API. Điều này không phải mâu thuẫn: unnamed module đã có quyền đọc/export/open rộng theo thiết kế.
- Trước khi gọi cho named module, kiểm tra `isModifiableModule(target)`. Module không modifiable có thể làm lời gọi ném `UnmodifiableModuleException`.
- Bản đồ `extraExports`/`extraOpens` phải chỉ những package **thực sự thuộc module được cập nhật**; package sai tên gây `IllegalArgumentException`. Không truyền tập giá trị rỗng cho một package hay các tham số null.
- Với một target ở **layer khác boot layer**, không nên chỉ dùng `ModuleLayer.boot().findModule(...)`; phải lấy đúng `Class<?>` và `getModule()` của lớp cần instrument, hoặc layer phù hợp.

Read edge **không thể thay thế loader visibility**: nếu helper JAR nằm ngoài đường tìm kiếm của class loader đang dùng, vẫn có thể gặp `ClassNotFoundException` hoặc `NoClassDefFoundError`.

## 6. Tùy chọn launcher: `--add-reads`, `--add-exports`, `--add-opens`

Khi biết cấu hình ngay từ đầu, có thể mở quyền bằng cờ JVM thay vì sửa module lúc runtime.

| Tùy chọn | Mục tiêu | Dùng khi |
| --- | --- | --- |
| `--add-reads demo.named=ALL-UNNAMED` | Named module đọc **các unnamed modules** | Code trong named module cần gọi helper trên classpath. |
| `--add-exports demo.named/demo.internal=ALL-UNNAMED` | Export package `demo.internal` cho các unnamed modules | Agent/helper cần truy cập public types trong package chưa được export. |
| `--add-opens demo.named/demo.internal=ALL-UNNAMED` | Open package cho các unnamed modules | Agent cần deep reflection, ví dụ truy cập private member khi điều kiện khác cho phép. |

Hai vế của `--add-exports` và `--add-opens` đi **từ module sở hữu package → module được quyền truy cập**. Đừng hiểu ngược: để **Target đọc Helper**, dùng `--add-reads demo.named=ALL-UNNAMED`; không cần export `demo.named` cho unnamed để đạt mục đích đó.

`--add-reads` có thể được sử dụng lúc **biên dịch** cho phép source của named module tham chiếu type trên classpath, và lúc **chạy** để bổ sung quan hệ đọc runtime. Quyền lúc biên dịch **không tự lưu thành read edge runtime** trong `module-info.class`. Ví dụ sẽ cố ý cấp `--add-reads` lúc `javac` nhưng bỏ lúc `java` để tái hiện `IllegalAccessError`.

So sánh với API:

- `--add-reads demo.named=ALL-UNNAMED` mở read edge tới **tất cả unnamed modules** trong phạm vi option.
- `redefineModule(target, Set.of(helperModule), ...)` thêm edge tới **chính đối tượng `Module` được truyền**, có thể là unnamed module của một loader cụ thể. Đây là cách có phạm vi hẹp hơn.

## 7. Thực hành Java 17+: phân biệt classpath, module read và transformer

Thí nghiệm có **một explicit named module** `demo.named`, một helper trong **system unnamed module** và một startup agent. Class `Target` có mã Java gọi trực tiếp `demo.helper.Helper.message()`:

- Mã **compile thành công** vì `javac` nhận `--add-reads demo.named=ALL-UNNAMED` và biết classpath chứa Helper.
- **Chạy không có read edge**: Helper vẫn tìm được qua system class loader nhưng JVM từ chối liên kết truy cập trực tiếp bằng `IllegalAccessError`.
- **Agent có transformer trả `null`**: callback được gọi, nhưng trên JVM thử nghiệm không có tự động read edge.
- **Agent có transformer trả clone bytes**: JVM tạo read edge theo cơ chế Instrumentation và lời gọi Helper thành công.
- **Agent gọi `redefineModule`**: read edge được thêm chủ động trước khi Target nạp, lời gọi Helper cũng thành công.
- **Tùy chọn `--add-reads` lúc chạy**: thêm read edge bằng launcher, không cần agent.

Đây là **các lần chạy JVM độc lập**, không phải các bước đổi qua lại trong cùng một JVM: quan hệ module được thêm trong một lần chạy không tự “tắt” sau đó.

### 7.1. Cấu trúc thư mục

```text
module-read-demo/
├── src/
│   ├── named/
│   │   ├── module-info.java
│   │   └── demo/named/
│   │       ├── Main.java
│   │       └── Target.java
│   ├── helper/
│   │   └── demo/helper/Helper.java
│   └── agent/
│       └── demo/agent/ModuleAgent.java
└── agent.mf
```

Sau build, có `mods/demo.named/` cho named module, `helper-classes/` cho helper classpath, `agent-classes/` và `agent.jar` cho startup agent.

### 7.2. `src/named/module-info.java`

```java
module demo.named {
}
```

Module này **không khai báo `requires` hay `exports`**. Launcher vẫn có thể chạy main class trong module bằng `-m demo.named/demo.named.Main`. Không có cách ghi `requires ALL-UNNAMED` trong descriptor. Chúng ta cố ý giữ module descriptor tối giản để quan sát read edge được thêm bởi JVM/agent.

### 7.3. `src/helper/demo/helper/Helper.java`

```java
package demo.helper;

public final class Helper {
    private Helper() {}

    public static String message() {
        return "HELLO_FROM_HELPER";
    }
}
```

Helper được biên dịch vào `helper-classes/` rồi đưa lên **classpath**. Nó thuộc **unnamed module của system class loader** trong thí nghiệm, không phải một named module do `module-info.java` khai báo.

### 7.4. `src/named/demo/named/Target.java`

```java
package demo.named;

public final class Target {
    private Target() {}

    public static String hello() {
        return demo.helper.Helper.message();
    }
}
```

Đây là **tham chiếu trực tiếp ở bytecode** tới helper, không phải reflection. `javac` cần được cho phép đọc unnamed module để biên dịch named module có tham chiếu này; lúc runtime JVM cũng phải có read edge khi liên kết method.

### 7.5. `src/named/demo/named/Main.java`

```java
package demo.named;

public final class Main {
    private Main() {}

    public static void main(String[] args) throws Exception {
        Module named = Main.class.getModule();
        Module helper = ClassLoader.getSystemClassLoader()
                .loadClass("demo.helper.Helper").getModule();
        System.out.println("[app] named=" + named.isNamed());
        System.out.println("[app] helperUnnamed=" + !helper.isNamed());
        System.out.println("[app] beforeRead=" + named.canRead(helper));

        try {
            System.out.println("[app] result=" + Target.hello());
        } catch (IllegalAccessError error) {
            System.out.println("[app] callFailed=IllegalAccessError");
        }

        System.out.println("[app] afterRead=" + named.canRead(helper));
    }
}
```

Điểm học tập:

1. `getSystemClassLoader().loadClass("demo.helper.Helper")` thử tìm class bằng loader và lấy `Module` để quan sát. Việc này có thể thành công **ngay cả lúc `named.canRead(helper)==false`**.
2. `Target.hello()` mới là thao tác dùng **bytecode call trực tiếp** từ named module tới helper; nếu không có read edge thì VM có thể ném `IllegalAccessError`.
3. Catch `IllegalAccessError` trong chương trình này **chỉ để minh họa**. Không nên bọc toàn bộ ứng dụng production để nuốt `LinkageError`; hãy sửa module configuration.
4. `beforeRead` được đo trước lúc `Target` cần load; `afterRead` được đo sau khi đã thử gọi method. Vì vậy ta nhìn thấy read edge xuất hiện **trong đường class transformation**.

### 7.6. `src/agent/demo/agent/ModuleAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Map;
import java.util.Set;

public final class ModuleAgent {
    private ModuleAgent() {}

    public static void premain(String option, Instrumentation inst) {
        if ("manual".equals(option)) {
            Module target = ModuleLayer.boot().findModule("demo.named").orElseThrow();
            Module helper = ClassLoader.getSystemClassLoader().getUnnamedModule();
            if (!inst.isModifiableModule(target)) {
                throw new IllegalStateException("Target module cannot be modified");
            }
            inst.redefineModule(target, Set.of(helper), Map.of(),
                    Map.of(), Set.of(), Map.of());
            System.out.println("[agent] manual extraReads added");
            return;
        }

        boolean noChange = "noop".equals(option);
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain, byte[] bytes) {
                if ("demo/named/Target".equals(className)) {
                    System.out.println("[agent] observed Target");
                    if (noChange) {
                        return null;
                    }
                    System.out.println("[agent] returning cloned bytes");
                    return bytes.clone();
                }
                return null;
            }
        }, false);
        System.out.println("[agent] transformer installed mode="
                + (noChange ? "noop" : "transform"));
    }
}
```

Có ba chế độ:

- `-javaagent:agent.jar=noop`: đăng ký transformer nhưng trả `null` khi `Target` được load. Trên VM thử nghiệm, không có read edge tự động.
- `-javaagent:agent.jar`: đăng ký transformer và khi gặp `Target` trả **`bytes.clone()`**. JVM nhận classfile bytes mới không khác nội dung nhưng được coi là kết quả transformation, tạo read edge hỗ trợ helper.
- `-javaagent:agent.jar=manual`: **không đăng ký transformer**; chủ động gọi `redefineModule` để named module đọc system unnamed module. Minh họa rằng **thêm read edge không bắt buộc phải instrument class**.

`ClassFileTransformer` trong Java 17 **không phải functional interface** vì hai overload `transform` có phương thức mặc định; vì vậy ví dụ dùng anonymous class với `@Override` sáu tham số. `return null` và `return bytes.clone()` chỉ khác về contract biến đổi, không phải vì API đã đổi method descriptor của `Target`.

**Tính chính xác về bootstrap/system:** cơ chế đặc biệt của Instrumentation đề cập unnamed module của **bootstrap class loader** và **class loader nạp main agent class**, không có cam kết chung cho arbitrary unnamed module của custom loader. Trong ví dụ, agent được system loader nạp, nên dùng chính system unnamed module là phù hợp.

### 7.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.ModuleAgent

```

Giữ dòng trống cuối manifest. Vì chỉ instrument class mới và thêm read edge, thí nghiệm **không cần** `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`. Hai manifest capability ấy liên quan tới retransform/redefine class đã nạp, không phải điều kiện để gọi `redefineModule`.

### 7.8. Lệnh biên dịch trên JDK 17+

Từ thư mục `module-read-demo/`, với **Bash**:

```bash
mkdir -p helper-classes mods/demo.named agent-classes

javac --release 17 -d helper-classes \
  src/helper/demo/helper/Helper.java

javac --release 17 \
  --add-reads demo.named=ALL-UNNAMED \
  -cp helper-classes \
  -d mods/demo.named \
  src/named/module-info.java \
  src/named/demo/named/Main.java \
  src/named/demo/named/Target.java

javac --release 17 -d agent-classes \
  src/agent/demo/agent/ModuleAgent.java

jar --create --file agent.jar --manifest agent.mf \
  -C agent-classes .
```

Trong **PowerShell**, dùng từng lệnh trên **một dòng**; dấu `\` tiếp dòng bên trên là cú pháp Bash:

```powershell
New-Item -ItemType Directory -Force -Path helper-classes,mods/demo.named,agent-classes | Out-Null
javac --release 17 -d helper-classes src/helper/demo/helper/Helper.java
javac --release 17 --add-reads demo.named=ALL-UNNAMED -cp helper-classes -d mods/demo.named src/named/module-info.java src/named/demo/named/Main.java src/named/demo/named/Target.java
javac --release 17 -d agent-classes src/agent/demo/agent/ModuleAgent.java
jar --create --file agent.jar --manifest agent.mf -C agent-classes .
```

**Vì sao lệnh `javac` có `--add-reads`?** Bởi `Target.java` tham chiếu trực tiếp tới helper trên classpath nhưng `module-info.java` không thể khai báo `requires` tới unnamed module. Tùy chọn cho phép Java compiler thấy dependency cho lượt biên dịch này. **Không tự ghi quyền vào module descriptor runtime.** Khi chạy không có agent hoặc tùy chọn tương ứng, read edge vẫn chưa có.

Các lệnh trên đã được kiểm tra với JDK hỗ trợ `--release 17`: classfiles sinh ra tương thích Java 17; không cần thư viện ngoài. Nếu dùng shell không phải Bash hoặc PowerShell, chỉnh cú pháp tạo thư mục/nối dòng tương ứng.

## 8. Chạy từng trường hợp và đọc stdout

Mỗi command sau mở **một JVM mới**, chạy tại thư mục `module-read-demo/`. Tên module `demo.named` được lấy từ `mods/demo.named/module-info.class`, còn helper nằm tại `-cp helper-classes`.

### 8.1. Trường hợp A — Không agent, không read edge

```bash
java -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout đã kiểm chứng:

```text
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=false
[app] callFailed=IllegalAccessError
[app] afterRead=false
```

**Chú ý:** `helperUnnamed=true` cho thấy class helper được tìm thấy và thuộc unnamed module. Nhưng `named.canRead(helper)==false`, vì vậy bytecode của `Target.hello()` không được liên kết với Helper và VM ném `IllegalAccessError`. Đây là bằng chứng **class loader nhìn thấy class chưa đủ**.

### 8.2. Trường hợp B — Có transformer nhưng trả `null`

```bash
java -javaagent:agent.jar=noop -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout trên OpenJDK 24.0.2:

```text
[agent] transformer installed mode=noop
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=false
[agent] observed Target
[app] callFailed=IllegalAccessError
[app] afterRead=false
```

Agent được khởi động; JVM gọi callback cho Target. Tuy nhiên callback trả `null`, nghĩa là không cung cấp biến đổi classfile bytes. Trong JVM thí nghiệm, read edge hỗ trợ helper **không được tạo** chỉ vì callback đã chạy. Do đó lỗi vẫn xảy ra.

Đừng rút ra quy tắc “chỉ cần addTransformer là named module đọc được classpath”. Phải có biến đổi thực sự hoặc read edge được thiết lập rõ ràng.

### 8.3. Trường hợp C — Transformer trả bytes mới

```bash
java -javaagent:agent.jar -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout đã kiểm chứng:

```text
[agent] transformer installed mode=transform
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=false
[agent] observed Target
[agent] returning cloned bytes
[app] result=HELLO_FROM_HELPER
[app] afterRead=true
```

Ở đây agent trả `bytes.clone()`. Mặc dù **nội dung bytes không thay đổi**, JVM có kết quả transformation được trả về và thêm read edge đặc biệt. Kết quả:

- `beforeRead=false` vì Main chạy trước khi Target thực sự được transform.
- `afterRead=true` vì module đã đọc unnamed module của loader nạp agent.
- `Target.hello()` liên kết thành công với helper và trả `HELLO_FROM_HELPER`.

**Đây không phải lời khuyên dùng clone không mục đích trong hệ thống thật.** Bản demo cố tình trả bytes mới để cô lập một cơ chế API. Nếu chỉ cần module read edge, hãy dùng `redefineModule`; nếu cần thực sự instrument bytecode, trả bytes đã được thay đổi hợp lệ.

### 8.4. Trường hợp D — Agent tự thêm read edge, không transform

```bash
java -javaagent:agent.jar=manual -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout:

```text
[agent] manual extraReads added
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=true
[app] result=HELLO_FROM_HELPER
[app] afterRead=true
```

Lúc `premain`, agent dùng `redefineModule(target, Set.of(systemUnnamed), ...)`. Vì vậy **ngay trước khi Main gọi Target**, read edge đã có. Không có dòng “observed Target” vì chế độ manual **không đăng ký transformer**. Đây là cách phù hợp khi mục tiêu của bạn là quản lý module relation độc lập với bytecode transform.

### 8.5. Trường hợp E — Dùng tùy chọn JVM `--add-reads`

```bash
java --add-reads demo.named=ALL-UNNAMED \
  -cp helper-classes --module-path mods \
  -m demo.named/demo.named.Main
```

PowerShell dùng một dòng:

```powershell
java --add-reads demo.named=ALL-UNNAMED -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout:

```text
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=true
[app] result=HELLO_FROM_HELPER
[app] afterRead=true
```

Kết quả giống manual ở việc **read edge có trước method call**, nhưng cách cấu hình khác: launcher bổ sung từ khi khởi động, không cần Java agent.

> Các stdout A–E bên trên đã được kiểm tra bằng chương trình biên dịch với `javac --release 17` trên Zulu/OpenJDK 24.0.2. Lỗi thực tế có thể khác khi code, module path, loader hoặc JVM implementation khác đi; điều cốt lõi là sự phân biệt **có/không có read edge** và **được/không được gọi helper**.

## 9. Readability chưa đủ khi helper nằm ở nơi khác

Cơ chế auto read không tự biến một class loader thành nơi tìm được mọi JAR.

### 9.1. Helper trên system loader search path

Nếu agent JAR hoặc dependency chứa helper có thể được **system class loader** nạp, khi named module đã đọc system unnamed module thì lớp được instrument có thể tham chiếu helper public từ package của unnamed module.

Các cách bố trí có thể gồm:

- Đặt helper JAR lên **application classpath** khi khởi động.
- Đóng gói helper trong agent JAR được nạp bởi system loader, đảm bảo agent và helper được đóng gói đúng.
- Dùng `Instrumentation.appendToSystemClassLoaderSearch(JarFile)` để bổ sung JAR vào đường tìm kiếm system loader khi đúng nhu cầu.

Khi system class loader là implementation tùy chỉnh, các ràng buộc đặc thù của `appendToSystemClassLoaderSearch` vẫn áp dụng. Đây **không** phải thao tác chuyển JAR thành named module hay thêm `requires` vào descriptor.

### 9.2. Helper nạp bằng bootstrap class loader

Một số agent đặt helper tối thiểu trên bootstrap search path:

```java
// Mã minh họa trong agent, cần import java.util.jar.JarFile.
// helperJarPath là Path đến một JAR có thực và hợp lệ.
inst.appendToBootstrapClassLoaderSearch(
        new java.util.jar.JarFile(helperJarPath.toFile()));
```

Các class được bootstrap loader định nghĩa nằm trong **unnamed module của bootstrap loader**. Instrumentation cung cấp read edge từ module của class đã được transform tới unnamed module này. Tuy nhiên, helper bootstrap **phải tự liên kết với những class bootstrap loader có thể định nghĩa/tìm**, không được tùy tiện phụ thuộc các ứng dụng/library chỉ có system loader mới nhìn thấy.

Với agent nhiều helper, cần tính đến tên package trùng, phụ thuộc classloader, split package, isolation và lỗi `NoClassDefFoundError` khi bootstrap helper tham chiếu nhầm library bên ngoài.

### 9.3. Helper trong một custom class loader

Nếu helper nằm trong unnamed module của **custom loader riêng**, auto-read rule của Instrumentation **không mặc định** thêm read edge tới module đó. Có thể cần:

- `redefineModule(targetModule, Set.of(customUnnamedModule), ...)` để thêm read edge cho **đúng module**;
- thiết kế class-loader delegation/visibility sao cho bytecode được instrument thật sự resolve được helper;
- hoặc chuyển helper tối thiểu tới bootstrap/system search path thích hợp.

**Chỉ thêm `extraReads` không đảm bảo loader resolve thành công class được gọi.** Hai điều kiện là độc lập. Việc gọi `helperClass.getModule()` trả một unnamed module không nói class loader của Target đã nạp được helper ấy.

## 10. Khi agent muốn truy cập named module, cần exports và opens

Cho đến đây, chiều cần xử lý là:

```text
Target (named module) ---> Helper (unnamed module)
               read edge cần thiết
```

Nhưng agent nhiều khi cần **truy cập class/package của Target**:

```text
Agent (system unnamed module) ---> internal class của Target (named module)
                             |
                             +-- truy cập public: cần package được exported phù hợp
                             |
                             +-- deep reflection: cần package được opened phù hợp
```

Với code Java thường, các package **không export** từ named module có thể gây `IllegalAccessError` dù module phía gọi nhìn thấy class. Với reflection muốn bỏ access check, module/package phải mở thích hợp, nếu không có thể gặp `InaccessibleObjectException`.

Ví dụ **chỉ minh họa**, khi agent muốn cho **system unnamed module** reflection sâu vào `demo.named` package `demo.named`:

```java
// Trong agent, target là Module của class đích.
// Chỉ hợp lệ khi "demo.named" thực sự là package thuộc target.
Module agentModule =
        ClassLoader.getSystemClassLoader().getUnnamedModule();

inst.redefineModule(
    target,
    java.util.Set.of(),
    java.util.Map.of(),
    java.util.Map.of("demo.named", java.util.Set.of(agentModule)),
    java.util.Set.of(),
    java.util.Map.of()
);
```

Lời gọi này **thêm opens**, không thay đổi Java source của module. `extraExports` và `extraOpens` phải sử dụng package **thuộc module đang sửa**; truyền package sai/không tồn tại sẽ bị API từ chối.

Nếu mục tiêu chỉ là Target gọi Helper trong system unnamed, **không cần** mở internal package của Target; đây là quyền khác và nên tránh mở rộng không cần thiết trong production.

## 11. Các lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân có thể và cách xử lý |
| --- | --- |
| Named module tìm được `Helper.class` nhưng gọi trực tiếp `Helper.message()` báo `IllegalAccessError` | Thiếu read edge từ named module tới unnamed module, hoặc package access chưa phù hợp. Kiểm tra `Module.canRead` và xuất/xem module helper. |
| Transformer có log nhưng `canRead(helper)==false` | Callback có thể đã trả `null`, nên chưa tạo transformed class như demo. Kiểm tra bytes thực sự được trả về và thời điểm đo. |
| Thấy `canRead=true` nhưng vẫn có `NoClassDefFoundError` | Readability không giúp loader tìm JAR/class; kiểm tra bootstrap/system/custom loader và đường tìm kiếm. |
| Truy cập public type của một named module khác báo `IllegalAccessError` | Có thể cần cả read edge **và exports** từ module sở hữu package. |
| Reflection private field báo `InaccessibleObjectException` | Kiểm tra **opens** package từ named module đích tới agent module; read edge một mình không đủ. |
| Helper được đặt trong named module riêng | Auto read edge tới **unnamed modules** của Instrumentation không thay cho `requires`/`extraReads` tới named helper module. |
| Helper đặt trong custom loader không nhận auto edge | Cơ chế đặc biệt chỉ bảo đảm unnamed của bootstrap và loader nạp agent chính; thêm edge có kiểm soát và giải quyết loader visibility. |
| Có `--add-reads` lúc compile nhưng runtime vẫn lỗi | Read edge lúc `javac` không tự thành quan hệ runtime. Thêm option lúc `java`, hoặc dùng Instrumentation. |
| `--add-exports` sửa lỗi public access nhưng private reflection vẫn thất bại | `exports` không thay `opens`; chọn đúng quyền. |
| `redefineModule` bị `IllegalArgumentException` | Tên package trong `extraExports`/`extraOpens` không thuộc module, hoặc map chứa tập đích rỗng / dữ liệu sai. |
| `isModifiableModule(target)==false` | VM không cho phép sửa module đó; không gọi `redefineModule`, có thể ném `UnmodifiableModuleException`. |
| Gọi `redefineModule` với unnamed module nhưng không thấy thay đổi | Theo API đây là no-op; unnamed module đã có read/export/open rộng. |
| Hai helper cùng package ở bootstrap và system loader gây lỗi khó chẩn đoán | Tránh trùng tên/package và cấu trúc delegation không rõ; log chính xác class loader và module của class đã resolve. |
| Agent hoạt động với application classpath nhưng lỗi khi ứng dụng chuyển sang module path | Named module có readability/encapsulation khác unnamed module; cần kiểm tra bytecode reference và module configuration. |

### Quy trình debug theo thứ tự

1. Log `targetClass.getModule().getName()` và `isNamed()`; xác định đây là **ordinary named**, **automatic** hay **unnamed module**.
2. Lấy đúng `helperClass.getModule()`, defining loader và nguồn class; đừng dùng một Helper trùng tên từ loader khác.
3. Log `targetModule.canRead(helperModule)` **trước/sau** biến đổi hoặc `redefineModule`.
4. Kiểm tra class helper **có thể được class loader liên quan tìm/nạp** không.
5. Nếu module đã đọc nhưng bị `IllegalAccessError`, kiểm tra package exports, class modifiers và access check của phương thức.
6. Nếu reflection thất bại, kiểm tra opens theo đúng module người gọi.
7. Nếu chỉ có log transformer nhưng không có auto edge, xác nhận transformer trả `null` hay `byte[]` mới; không giả định callback đồng nghĩa biến đổi.
8. Với module layer riêng hoặc helper custom loader, lấy Module từ đúng `Class<?>`, không dựa vào một module name chung chung trong boot layer.
9. Chạy test trên JDK/VM thật, bởi tương tác với nhiều agent/transformer và thời điểm class loading có thể khác môi trường phát triển.

## 12. Lưu ý về vòng đời và tính an toàn

- `redefineModule` **chỉ tăng quyền**, không có phép “undo” tương ứng trong API. Đừng mở các package/module không cần thiết.
- Cơ chế auto read edge cho transformed classes không thay cho kế hoạch phân phối helper JAR và class-loader isolation.
- Hạn chế helper phụ thuộc package nội bộ của JDK hoặc của named module không exported; nếu bắt buộc, khai báo reads/exports/opens đúng hướng, đúng module và kiểm chứng.
- Khi transform class đã nạp với `retransformClasses`/`redefineClasses`, ngoài module relation còn cần manifest capabilities, class modifiability và schema/bytecode hợp lệ; chúng **không** phải chức năng được tự cấp chỉ vì `redefineModule` thành công.
- Không dùng `IllegalAccessError` làm cơ chế fallback bình thường trong hot path; sửa cấu hình module trước khi code cần gọi helper.
- Với nhiều Java agent, hãy kiểm tra helper package trùng nhau, loader của agent chính và thứ tự class transformation; một agent có thể tạo read edge khi class được transform trước lượt của agent khác.
- Quyền đọc/export/open có liên quan bảo mật module system. Agent có nhiều đặc quyền nên hạn chế thêm quyền ở phạm vi nhỏ và ghi audit khi điều chỉnh runtime module graph.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Helper đã có trên classpath và `ClassLoader.loadClass(...)` thành công. Named module gọi trực tiếp Helper có chắc không gặp `IllegalAccessError`?

**Đáp án:** Không. Loader visibility và module readability là hai điều kiện khác nhau. Named module có thể chưa có read edge tới unnamed module của Helper.

**Câu 2.** Unnamed module ở system loader và unnamed module ở custom loader có phải lúc nào là một đối tượng không?

**Đáp án:** Không. Mỗi class loader có thể có unnamed module riêng; một read edge tới system unnamed không tự cấp quyền tới mọi unnamed module của loader khác.

**Câu 3.** Trong thí nghiệm, vì sao chế độ `noop` đã in “observed Target” mà `afterRead=false`?

**Đáp án:** Callback trả `null`, không cung cấp transformed bytes. JVM thử nghiệm chỉ thêm auto read edge theo trường hợp class **được biến đổi**, không phải chỉ được quan sát.

**Câu 4.** Vì sao `return bytes.clone()` làm `afterRead=true` dù method body chưa đổi?

**Đáp án:** Transformer trả mảng classfile bytes mới (nội dung tương đương), đủ để JVM coi class đã đi qua transformation, từ đó bổ sung read edge theo cơ chế Instrumentation.

**Câu 5.** Nếu agent muốn read edge mà không sửa class, nên làm gì?

**Đáp án:** Gọi `Instrumentation.redefineModule(targetModule, Set.of(helperModule), ...)` sau khi kiểm tra `isModifiableModule`, hoặc dùng `--add-reads` khi khởi động. Không cần clone bytes vô ích.

**Câu 6.** `--add-reads demo.named=ALL-UNNAMED` có giống hệt `redefineModule(target, Set.of(oneUnnamed), ...)` không?

**Đáp án:** Không hoàn toàn. Tùy chọn launcher cho named module đọc các unnamed modules, còn API cho phép chỉ định **Module cụ thể** trong `extraReads`.

**Câu 7.** Muốn agent đọc private field của `demo.named.Internal`, chỉ thêm read edge từ named tới unnamed đã đủ chưa?

**Đáp án:** Chưa. Đó là chiều ngược. Cần xem package được **opens** tới agent module để deep reflection, và những điều kiện class/loader khác.

**Câu 8.** Có phải `appendToBootstrapClassLoaderSearch` tự làm named module đọc được mọi module/JAR không?

**Đáp án:** Không. Nó bổ sung JAR vào bootstrap class-loader search path. Readability là điều kiện module; với lớp thực sự được Instrumentation transform, JVM có hỗ trợ read edge tới bootstrap unnamed module. Helper phải được bootstrap loader định nghĩa thành công.

**Câu 9.** Có thể dùng `ModuleLayer.boot().findModule(...)` để luôn tìm được target trong custom module layer?

**Đáp án:** Không. Custom layer có thể không thuộc boot layer. Hãy lấy module từ đúng `targetClass.getModule()` hoặc layer phù hợp.

**Câu 10.** Khi đã gọi `redefineModule` để export/open package, có thể gọi API ngược để thu hồi quyền ngay trong cùng JVM?

**Đáp án:** Không. Theo hợp đồng API, `redefineModule` chỉ **mở rộng** reads/exports/opens/uses/provides, không thu hẹp hoặc thu hồi các quyền đã cấp.

## 14. Tóm tắt và tài liệu chuẩn

**Điều cần nhớ:**

1. **Named và unnamed module không có readability đối xứng mặc định:** unnamed đọc rộng, nhưng ordinary named module không mặc định đọc unnamed classpath.
2. **Class loader tìm được Helper chưa đủ:** để bytecode named module gọi Helper còn phải có read edge và package access hợp lệ.
3. **Instrumentation tạo read edges hỗ trợ transformed class** tới unnamed của bootstrap loader và loader nạp main agent class; điều này **không mặc định áp dụng cho mọi custom loader**.
4. **Callback trả `null` khác callback trả bytes mới:** bài thực hành chứng minh JVM thử nghiệm không thêm auto edge cho callback chỉ quan sát.
5. **`redefineModule` là cách chủ động và rõ ràng** để thêm `extraReads` tới helper module; exports/opens giải quyết những bài toán tiếp cận package theo chiều khác.
6. **`--add-reads` lúc `javac` chưa đủ cho runtime**; thêm `--add-reads` lúc `java` hoặc read edge bằng instrumentation nếu cần.
7. **Không dùng module reads thay cho loader search path:** helper JAR phải thật sự nạp được, đúng loader/module và đúng API version.

**Tài liệu chính thức để đối chiếu:**

- [Java SE 17 — `java.lang.instrument` package, mục “Instrumenting code in modules”](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 17 — `Instrumentation.redefineModule` và `isModifiableModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map))
- [Java SE 17 — `Module.canRead`, `isExported`, `isOpen`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JLS Java SE 17 §7.7.5 — Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.5)
- [JDK 17 launcher — `--add-reads`, `--add-exports`, `--add-opens`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JDK 17 javac — `--add-reads` khi biên dịch module](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)