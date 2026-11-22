# Instrumentation.redefineModule: extraReads, extraExports và extraOpens

## 1. Bài toán: agent cần nới quyền truy cập của một named module

Kể từ Java 9, **Java Platform Module System (JPMS)** đặt thêm ranh giới **readability** và **encapsulation** bên cạnh quyền truy cập `public`/`private` truyền thống. Một Java agent có thể instrument lớp ở named module, nhưng bytecode mới chèn hoặc công cụ reflection của agent đôi khi cần một quan hệ module mà `module-info.java` ban đầu **không khai báo**.

Ví dụ:

~~~text
                  demo.target  (named module)
                 /            \
        demo.target.api    demo.target.internal
         public method       private field
                 \            /
                  \          /
                  Agent ở unnamed module

Ban đầu:
  demo.target không đọc unnamed module của agent
  demo.target.api không export cho agent
  demo.target.internal không open cho agent

Agent cần:
  extraReads    : demo.target  ------read------> agent module
  extraExports  : demo.target.api ----export---> agent module
  extraOpens    : demo.target.internal --open--> agent module
~~~

`java.lang.instrument.Instrumentation.redefineModule(...)` cho phép agent **bổ sung** những quan hệ này **trong JVM đang chạy**, không cần sửa `module-info.java` trên đĩa hoặc thay bytecode của class. Nó phục vụ trường hợp instrumentation cần đọc helper, gọi API công khai, dùng reflection trên internal state hoặc mở rộng đăng ký service.

**Ý chính:**

- **`extraReads`:** *module nào được đọc thêm?* Đây là cạnh từ **module được redefine** đến module đích.
- **`extraExports`:** *package nào của module được redefine được export thêm, và cho module nào?* Thường cần để truy cập **public type/member** qua ranh giới module.
- **`extraOpens`:** *package nào được open thêm, và cho module nào?* Dùng cho **deep reflection** vào non-public member và các tình huống reflection được JPMS cho phép.

Ba quyền có vai trò **khác nhau**. Chỉ cấp một quyền và hy vọng cả ba vấn đề biến mất là lỗi phổ biến trong agent.

Tài liệu gốc: [Java 17 — Instrumentation.redefineModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map)).

## 2. Chữ ký đầy đủ và ý nghĩa từng đối số

Phương thức thuộc interface `java.lang.instrument.Instrumentation`, từ Java 9:

~~~java
void redefineModule(
        Module module,
        Set<Module> extraReads,
        Map<String, Set<Module>> extraExports,
        Map<String, Set<Module>> extraOpens,
        Set<Class<?>> extraUses,
        Map<Class<?>, List<Class<?>>> extraProvides);
~~~

Đây là **chữ ký API minh họa**, không phải chương trình độc lập. Khi viết code cần import `java.lang.instrument.Instrumentation`, `java.util.Set`, `Map` và `List`. Đối tượng `Instrumentation` được JVM truyền vào `premain` hoặc `agentmain`, **không** tạo thủ công bằng `new Instrumentation()`.

| Đối số | Giá trị mong đợi | Tác dụng |
| --- | --- | --- |
| `module` | `Module` cần nới quyền | **Nguồn** của các thay đổi reads/exports/opens |
| `extraReads` | `Set<Module>`, có thể rỗng | Các module mà `module` được **read thêm** |
| `extraExports` | `Map<String, Set<Module>>`, có thể rỗng | Tên package của `module` → các module được **export thêm** |
| `extraOpens` | `Map<String, Set<Module>>`, có thể rỗng | Tên package của `module` → các module được **open thêm** |
| `extraUses` | `Set<Class<?>>`, có thể rỗng | Các service type mà module được bổ sung quyền `uses` |
| `extraProvides` | `Map<Class<?>, List<Class<?>>>`, có thể rỗng | Bổ sung provider implementation cho service |

Bài tập trung vào **ba đối số đầu tiên về read/export/open**. Hai đối số service vẫn **bắt buộc truyền non-null**, dù không sử dụng: dùng `Set.of()` và `Map.of()` thay vì `null`. Việc `extraUses`/`extraProvides` được hỗ trợ không có nghĩa agent tự động đăng ký một JVM service hay bỏ qua các quy tắc accessibility của service type.

Cấu trúc gọi phổ biến:

~~~java
inst.redefineModule(
        targetModule,
        Set.of(helperModule),
        Map.of("com.acme.api", Set.of(agentModule)),
        Map.of("com.acme.internal", Set.of(agentModule)),
        Set.of(),
        Map.of());
~~~

Đây là **mảnh code bên trong agent**, giả định đã có `inst`, `targetModule`, `helperModule` và `agentModule`. Nó chỉ hợp lệ khi các package `com.acme.api` và `com.acme.internal` **thực sự thuộc `targetModule`**. `Map.of` và `Set.of` tạo container không sửa được, thích hợp cho một yêu cầu cấu hình cố định.

## 3. `extraReads`: bổ sung cạnh readability

Giả sử module `M` cần sử dụng lớp từ module `H`. `M.canRead(H)` cho biết liệu `M` có read edge đến `H` theo graph runtime hay không.

~~~text
                  trước                         sau
     module M              module H     module M ------> module H
        canRead(H) = false                   canRead(H) = true
~~~

Thực hiện qua agent:

~~~java
inst.redefineModule(
        moduleM,
        Set.of(moduleH),   // M đọc thêm H
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

Đoạn này là **mảnh code trong agent** có sẵn các biến module. **Chiều là `moduleM → moduleH`**, không phải ngược lại. Nếu đặt `moduleH` vào tham số đầu của lời gọi, bạn đang thay đổi module khác.

### 3.1. Readability không tự tạo export/open

**`M.canRead(H) == true` chưa đủ để M gọi mọi class/member của H.** Package bên H vẫn phải được export/open theo tình huống. Để code trong M gọi public type của H qua liên kết JVM, thường cần **M đọc H** **và** **H export package đó cho M**. Read edge không tự mở private field.

Một chiều ngược cũng cần lưu ý: **export package của H cho M không tự thêm `M → H` vào module graph**. Khi truy vấn `H.isExported("h.api", M)`, API này **không tự kiểm tra** liệu M có đọc H hay không.

Điều này giải thích vì sao một agent đôi khi phải dùng **hai thao tác trên hai module khác nhau**:

~~~text
M cần gọi H.API:
    redefineModule(M, extraReads={H}, ...)
    redefineModule(H, extraExports={"h.api" -> {M}}, ...)
~~~

Nếu `H` là **unnamed module**, các package của H đã được coi là exported/open trong cơ chế JPMS, nhưng module M **vẫn có thể cần read edge đến H** và vẫn phải vượt qua **class-loader visibility**. Việc nới JPMS graph không tự làm class loader của M tìm thấy một helper được định nghĩa ở loader cô lập.

### 3.2. Không nhầm `extraReads` với `java.base`

Named module mặc nhiên đọc `java.base` trong các trường hợp chuẩn, và unnamed module có cách đọc module riêng. Trong ví dụ thực hành, ta chọn một cạnh **ban đầu không có** để chứng minh thay đổi; nếu kiểm tra `target.canRead(Object.class.getModule())` thì thường đã là `true`, không thấy sự khác biệt.

Tham khảo: [Java 17 — Module.canRead](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#canRead(java.lang.Module)).

## 4. `extraExports`: bổ sung quyền dùng public API của package

Một named module có package `p.api` nhưng **không** có `exports p.api;` trong `module-info.java`. Class bên trong có thể là `public`, nhưng một module bên ngoài không tự có quyền liên kết đến class đó.

`extraExports` thêm một **qualified export** tới tập module được chỉ định:

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of("p.api", Set.of(consumerModule)),
        Map.of(),
        Set.of(),
        Map.of());
~~~

Đây là **mảnh code trong agent**. Key `"p.api"` là **tên package có dấu chấm**, không phải internal name `"p/api"` dùng trong bytecode hoặc `ClassFileTransformer`. Map value là **tập module không rỗng**; không phải tên module ở dạng String.

Sau khi thành công:

~~~java
boolean exported = sourceModule.isExported("p.api", consumerModule);
~~~

Phép kiểm tra này hỏi package `p.api` có được export **ít nhất cho consumerModule** không. Nó **không** chứng minh package được export vô điều kiện tới mọi module. `sourceModule.isExported("p.api")` (không có tham số module) hỏi **unqualified export**; đừng thay hai overload cho nhau khi xác minh quyền được nới **có đích**.

### 4.1. Export không có nghĩa truy cập private

Quyền export giúp module đích truy cập **public types** và những member được phép theo quy tắc Java access. Nó **không tự cho phép deep reflection** vào private field/method của package.

Ví dụ một public class nằm ở package không exported có public static method. Sau khi export package đến agent, việc gọi public method qua reflection có thể hoạt động; nhưng `privateField.setAccessible(true)` ở một package chỉ exported mà **không opened** vẫn có thể ném `InaccessibleObjectException`.

### 4.2. Target package phải có thật trong module nguồn

Đây là lỗi dễ gặp:

~~~java
Map.of("p/unknown", Set.of(agentModule)) // Sai: tên có dấu /
~~~

Ngay cả sửa thành `"p.unknown"` cũng sai nếu đó **không** phải package của `sourceModule`. `redefineModule` có thể ném `IllegalArgumentException` khi key trong `extraExports`/`extraOpens` không thuộc module được sửa. Không nên tạo key từ tên class chưa được chuẩn hóa hoặc lẫn package của agent với package của app.

Tham khảo: [Java 17 — Module.isExported](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#isExported(java.lang.String,java.lang.Module)).

## 5. `extraOpens`: cho phép deep reflection có đích

`opens` có mục tiêu khác `exports`. Khi package `p.internal` được **opened** tới module agent, code trong agent có thể thực hiện những thao tác reflection sâu được phép, chẳng hạn `Field.setAccessible(true)` cho private field thuộc package đó.

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of(),
        Map.of("p.internal", Set.of(agentModule)),
        Set.of(),
        Map.of());
~~~

Mảnh code trên dùng package **dotted name**. Xác minh:

~~~java
boolean opened = sourceModule.isOpen("p.internal", agentModule);
~~~

`opened == true` không nói mọi module đều được mở; đây vẫn là **qualified opens**. Muốn hỏi unconditional opens, dùng overload `sourceModule.isOpen("p.internal")`.

**Điểm dễ gây ngạc nhiên:** Theo `Module.isExported(String, Module)`, một package được **open tới module X cũng được coi là exported tới X tại runtime**. Vì vậy sau `extraOpens("p.internal" → X)`, thường thấy:

~~~text
source.isOpen("p.internal", X)     == true
source.isExported("p.internal", X) == true
~~~

Đây là ngữ nghĩa runtime của package mở, **không có nghĩa đã thêm khai báo `exports` vào file `module-info.java`**. Cũng không có nghĩa mọi public type nằm trong package đó được người dùng bên ngoài sử dụng ngay khi compile mã Java bình thường; JPMS compile-time và runtime là hai giai đoạn khác nhau.

### 5.1. So sánh qua hành vi reflection

| Trạng thái package ở source module | Gọi public member từ module đích | `privateField.setAccessible(true)` từ module đích |
| --- | --- | --- |
| Không exported, không opened | Có thể bị `IllegalAccessException` | Thường `InaccessibleObjectException` |
| Chỉ qualified exported cho đích | Public type/member được mở theo quy tắc visibility | **Không tự có quyền** deep reflection |
| Qualified opened cho đích | Cũng được coi exported tại runtime cho đích | Có thể cho phép deep reflection, nếu các điều kiện khác hợp lệ |

Phương thức reflection có các quy tắc riêng về readability (Javadoc `AccessibleObject` lưu ý reflection **assumes readability** trong một số access checks). Vì thế hãy dùng `Module.canRead` để kiểm tra **read graph** và dùng `isExported`/`isOpen` để kiểm tra **package boundary**, thay vì dùng một phép thử reflection để suy ra cả ba cờ.

Deep reflection vẫn có thể chịu các điều kiện khác, ví dụ member đặc biệt, `final`, quyền của security policy hoặc cách caller xác định module. “Open” không phải lời hứa có thể **ghi** mọi private/final field, bất kể loại dữ liệu.

Tham khảo: [Java 17 — AccessibleObject.setAccessible/trySetAccessible](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html).

## 6. Bảng quyết định: nên bổ sung quan hệ nào?

| Nhu cầu thực sự | Quyền nên xét đầu tiên | Cần thêm điều kiện gì? |
| --- | --- | --- |
| Bytecode mới chèn trong named module M gọi helper thuộc H | `extraReads`: M → H | H export package helper cho M (hoặc helper ở unnamed module), loader phải thấy helper |
| Agent gọi public method của target package bị ẩn | `extraExports` từ target → agent | Class/method thật sự public, đúng target Module và reflection/loader hợp lệ |
| Agent đọc private field để quan sát | `extraOpens` từ target → agent | Reflection trên đúng class/member; điều kiện policy khác |
| Agent dùng MethodHandles private lookup trong package | Thường cần `extraOpens` từ target → caller module | `MethodHandles.privateLookupIn` còn yêu cầu read edge/đặc tính lookup thích hợp |
| Target chỉ muốn public API cho plugin X, không cho toàn bộ JVM | Qualified `extraExports` tới X | Không mở vô điều kiện, không dùng broad target |
| Agent chỉ cần đọc class-file bytes, không reflection vào private data | Có thể **không cần** bất kỳ mở rộng module nào | Lọc/parse bytecode theo hợp đồng transformer |
| Làm scanner chỉ đọc metadata từ một JAR offline | Thường không cần `redefineModule` | Đọc file/bytes, không cần class loading/reflect |

**Nguyên tắc cấp quyền tối thiểu:** mở đúng module, đúng package và đúng target module; không tự động extraReads/extraExports/extraOpens toàn bộ package hoặc `java.base` chỉ vì một lỗi `IllegalAccessException`.

## 7. Ví dụ Java 17+ thực thi thật: agent mở ba quan hệ cho named module

Ví dụ chạy **một JVM mới** có agent `-javaagent` và ứng dụng named module `demo.target`. Module đích không công bố exports/opens trong `module-info.java`. Agent sống ở **unnamed module** trên application classpath, kiểm tra trước/sau và gọi reflection để chứng minh hành vi.

**Điểm quan trọng:** đây là **Java agent thật**, không giả lập `Instrumentation`. Ví dụ **không** đổi bytecode class, không cần `ClassFileTransformer` và không sử dụng dynamic attach.

### 7.1. Cấu trúc thư mục

~~~text
module-demo/
  src/
    demo.target/
      module-info.java
      demo/
        target/
          api/
            PublicApi.java
          internal/
            Secret.java
          app/
            Main.java
  agent-src/
    AccessAgent.java
    MANIFEST.MF
  mods/               (được tạo bởi javac)
  agent-bin/          (được tạo bởi javac)
  access-agent.jar    (được tạo bởi jar)
~~~

### 7.2. Module đích không export hoặc open package

**Tệp: `src/demo.target/module-info.java`**

~~~java
module demo.target {
    // Co y khong exports/opens bat ky package nao.
}
~~~

**Tệp: `src/demo.target/demo/target/api/PublicApi.java`**

~~~java
package demo.target.api;

public final class PublicApi {
    private PublicApi() { }

    public static String greet() {
        return "API";
    }
}
~~~

**Tệp: `src/demo.target/demo/target/internal/Secret.java`**

~~~java
package demo.target.internal;

public final class Secret {
    private static final String VALUE = "hidden";

    private Secret() { }
}
~~~

**Tệp: `src/demo.target/demo/target/app/Main.java`**

~~~java
package demo.target.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app=started");
    }
}
~~~

`PublicApi` và `Secret` đều là `public class`, nhưng package tương ứng không được export/open. JVM có thể định nghĩa chúng trong module; điều đó **không tự cấp quyền** cho agent truy cập public method/private field từ module khác.

Chương trình `Main` được launcher gọi qua `-m demo.target/demo.target.app.Main` nên không cần export package `demo.target.app` chỉ để chạy entry point ở ví dụ này. Các package có tên dotted đúng chuẩn Java.

### 7.3. Agent kiểm tra trạng thái trước/sau `redefineModule`

**Tệp: `agent-src/AccessAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;

public final class AccessAgent {
    public static void premain(
            String args, Instrumentation inst) throws Exception {

        Module target = ModuleLayer.boot()
                .findModule("demo.target").orElseThrow();
        Module agent = AccessAgent.class.getModule();

        String publicPackage = "demo.target.api";
        String privatePackage = "demo.target.internal";

        System.out.println("targetNamed=" + target.isNamed());
        System.out.println("agentUnnamed=" + !agent.isNamed());
        System.out.println("modifiable="
                + inst.isModifiableModule(target));
        System.out.println("readsBefore=" + target.canRead(agent));
        System.out.println("exportsBefore="
                + target.isExported(publicPackage, agent));
        System.out.println("opensBefore="
                + target.isOpen(privatePackage, agent));

        Method method = Class.forName("demo.target.api.PublicApi")
                .getMethod("greet");
        Field field = Class.forName("demo.target.internal.Secret")
                .getDeclaredField("VALUE");

        try {
            method.invoke(null);
            System.out.println("publicBefore=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("publicBefore=IllegalAccessException");
        }

        try {
            field.setAccessible(true);
            System.out.println("privateBefore=unexpected");
        } catch (InaccessibleObjectException expected) {
            System.out.println(
                    "privateBefore=InaccessibleObjectException");
        }

        inst.redefineModule(
                target,
                Set.of(agent),
                Map.of(publicPackage, Set.of(agent)),
                Map.of(privatePackage, Set.of(agent)),
                Set.of(),
                Map.of());

        System.out.println("readsAfter=" + target.canRead(agent));
        System.out.println("exportsAfter="
                + target.isExported(publicPackage, agent));
        System.out.println("opensAfter="
                + target.isOpen(privatePackage, agent));
        System.out.println("openedAlsoExported="
                + target.isExported(privatePackage, agent));
        System.out.println("publicAfter=" + method.invoke(null));

        field.setAccessible(true);
        System.out.println("privateAfter=" + field.get(null));
    }
}
~~~

**Tệp: `agent-src/MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: AccessAgent

~~~

Tệp manifest thực tế cần kết thúc phần main attributes bằng một dòng trống. Không cần `Can-Redefine-Classes: true`: đây là **`redefineModule`**, không phải `redefineClasses`. Không cần `Agent-Class` vì ví dụ dùng `-javaagent` lúc startup, không dùng cơ chế attach sau khi JVM đã chạy.

Để dễ hiểu, code dùng `ModuleLayer.boot().findModule("demo.target")`, đúng vì `demo.target` là module được resolve trong **boot layer** của ví dụ. Ở ứng dụng thật có **module layer riêng**, không nên tìm nhầm module có cùng tên trong boot layer. Hãy xác định đúng `Module` (thường lấy `targetClass.getModule()`) và class loader tương ứng.

### 7.4. Lệnh biên dịch và chạy

Từ thư mục `module-demo`, với JDK 17 trở lên:

~~~bash
mkdir -p mods/demo.target agent-bin
javac --release 17 -d mods/demo.target src/demo.target/module-info.java src/demo.target/demo/target/api/PublicApi.java src/demo.target/demo/target/internal/Secret.java src/demo.target/demo/target/app/Main.java
javac --release 17 -d agent-bin agent-src/AccessAgent.java
jar --create --file access-agent.jar --manifest agent-src/MANIFEST.MF -C agent-bin AccessAgent.class
java -javaagent:access-agent.jar --module-path mods -m demo.target/demo.target.app.Main
~~~

Trên **Windows PowerShell**, thay lệnh `mkdir -p mods/demo.target agent-bin` bằng:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.target, agent-bin | Out-Null
~~~

Các lệnh `javac`, `jar` và `java` sau đó dùng được trong PowerShell khi chạy đúng working directory và có JDK trong `PATH`. Ví dụ không cần các cờ `--add-reads`, `--add-exports`, `--add-opens` khi khởi động: chính agent sẽ thêm quyền **sau khi in trạng thái ban đầu**.

### 7.5. Stdout trên OpenJDK/HotSpot hỗ trợ `redefineModule`

~~~text
targetNamed=true
agentUnnamed=true
modifiable=true
readsBefore=false
exportsBefore=false
opensBefore=false
publicBefore=IllegalAccessException
privateBefore=InaccessibleObjectException
readsAfter=true
exportsAfter=true
opensAfter=true
openedAlsoExported=true
publicAfter=API
privateAfter=hidden
app=started
~~~

Đây là **đầu ra đã được kiểm thử**: mã nguồn tương thích `--release 17` được biên dịch và chạy trên OpenJDK 21 (một JVM Java 17+) với đúng agent/module này. Trên một JVM khác, nếu `isModifiableModule(target)` không hỗ trợ thay đổi module, thao tác có thể thất bại; ví dụ đầu ra trên **không là cam kết cho mọi JVM**. Sử dụng JDK 17 phù hợp và module graph ban đầu như hướng dẫn để tái hiện.

Các điểm đáng chú ý:

- `targetNamed=true`: ta đang sửa named module, không phải unnamed module.
- `agentUnnamed=true`: agent JAR của demo chạy ở unnamed module.
- `readsBefore=false`, `exportsBefore=false`, `opensBefore=false`: chưa có ba quan hệ.
- Trước khi mở module, gọi **public method** bị `IllegalAccessException` và xin deep reflection cho **private field** bị `InaccessibleObjectException`.
- Sau `redefineModule`, cả ba phép truy vấn `canRead/isExported/isOpen` chuyển thành `true`.
- `openedAlsoExported=true` minh họa tính chất **opened package được xem là exported đến cùng module ở runtime**; không phải chúng ta đã thêm `extraExports` cho `demo.target.internal`.
- `publicAfter=API` và `privateAfter=hidden` cho thấy quyền được cấp đã thay đổi **hành vi truy cập thật**.
- `app=started` xuất hiện cuối: JVM gọi `premain` của agent **trước** entry point `main` của ứng dụng.

**Giới hạn của demo:** `extraReads` được xác minh qua `target.canRead(agent)`, còn hai quyền package được chứng minh thêm bằng reflection. Ví dụ **không** khẳng định public reflective invocation tự nó chứng minh một read edge mới: reflection có quy tắc readability riêng. Cũng không có thao tác tải helper từ ứng dụng; bài thực hành chỉ chứng minh nền tảng module graph cho bước đó.

## 8. Tại sao bộ kiểm tra phải tách reads, exports và opens?

Ba trạng thái là ba câu hỏi độc lập, nên code chẩn đoán cũng phải tách:

~~~java
Module target = someClass.getModule();
Module agent = AccessAgent.class.getModule();

boolean canRead = target.canRead(agent);
boolean publicAccess = target.isExported("demo.target.api", agent);
boolean deepReflection = target.isOpen("demo.target.internal", agent);
~~~

Đây là **mảnh code trong agent** và `someClass` là một `Class<?>` đã biết; không phải chương trình độc lập. Lưu ý chiều:

- `target.canRead(agent)`: **target đọc agent**.
- `target.isExported("pkg", agent)`: **target export pkg cho agent**.
- `target.isOpen("pkg", agent)`: **target open pkg cho agent**.

Khi mã instrumented ở **target** muốn gọi public helper trong **agent**, cạnh **target → agent** là hợp lý, nhưng thường cần kiểm tra helper package có được **agent module export cho target** không. Nếu agent thuộc unnamed module, khía cạnh JPMS export tương ứng thường không phải trở ngại; nhưng class loader target vẫn có thể **không nhìn thấy** helper.

Khi chính **agent** muốn gọi public API của **target**, vấn đề thường là **target export package cho agent**. Đối với private field, cần **target open package cho agent**. Không thay đổi module đọc theo chiều ngược lại chỉ vì sơ đồ có mũi tên giữa hai module.

### 8.1. Tại sao không dùng `Module.getDescriptor()` để xác minh thay đổi?

`module-info.class` và `ModuleDescriptor` biểu diễn cấu hình khai báo/định nghĩa của module. `redefineModule` mở rộng quan hệ **runtime** mà không viết lại file module descriptor ban đầu. Khi xác minh quyền mới, nên gọi trực tiếp `Module.canRead`, `isExported`, `isOpen` trên đúng `Module` thay vì kết luận từ nội dung `module-info.java` ban đầu.

### 8.2. Đúng module, đúng layer, đúng class loader

`Module` là đối tượng runtime, không chỉ là một `String` tên module. Với ứng dụng nhiều `ModuleLayer`, có thể có module **cùng tên** ở các layer/class loader khác nhau. Chọn nhầm instance sẽ mở quyền cho đối tượng khác và vẫn gặp lỗi ở class đích.

Nếu đã có `Class<?> targetClass` từ `ClassFileTransformer`, event hay registry, dùng `targetClass.getModule()` để tìm module chính xác. Nếu chỉ có class name từ transformer ở load-time, có thể tận dụng đối số `Module module` ở overload sáu tham số của `ClassFileTransformer.transform` khi phù hợp (Java 9+).

## 9. Tính bổ sung một chiều: không có thao tác revoke tương ứng

Theo Javadoc, `redefineModule` **chỉ mở rộng** read edges, exports, opens và service uses/provides. Nó **không thể giảm** tập quyền hiện có.

~~~text
Trạng thái đầu:
    M đọc A
    M export p -> B

Agent gọi:
    M đọc thêm C
    M open q -> D

Trạng thái sau:
    M vẫn đọc A, đồng thời đọc C
    M vẫn export p -> B, đồng thời open q -> D
~~~

**Không có cách thu hồi** quyền đã cấp chỉ bằng lời gọi `redefineModule` tiếp theo với empty sets/maps. Một lời gọi `redefineModule(M, Set.of(), Map.of(), Map.of(), Set.of(), Map.of())` không có ý nghĩa “reset M về mặc định”.

### 9.1. Cấp quyền rộng có rủi ro

Mở package internal của một thư viện cho module agent có thể tạo quyền reflection sâu hơn dự định. Với tác vụ chẩn đoán tạm thời, quyền này vẫn tồn tại **trong JVM** sau khi tác vụ kết thúc. Thiết kế an toàn nên:

1. Chọn module và **package cụ thể**, không mở theo kiểu quét hết package.
2. Chọn **module nhận quyền cụ thể**, tránh mở cho mọi unnamed/module tùy tiện.
3. Chỉ bổ sung quyền thực sự cần cho helper/probe đang instrument.
4. Giới hạn mã agent có thể dùng quyền vừa cấp, và có lifecycle/cleanup cho transformer/logger/registry.
5. Không giả định gỡ `ClassFileTransformer` hoặc tắt một probe sẽ **thu hồi** read/export/open edges.
6. Ghi nhận các mở rộng module trong diagnostics để chủ sở hữu hệ thống đánh giá tác động.

Các thuộc tính này không thay thế security policy khác, module readability/visibility của dependencies hay việc xác thực agent JAR.

### 9.2. Đồng thời nhiều agent

Javadoc quy định `redefineModule` **an toàn khi gọi đồng thời** và cho phép nhiều agent thay đổi cùng một module gần cùng thời điểm. Nhưng điều đó không có nghĩa một agent có thể “đặt lại” mọi thay đổi của agent khác: các quyền được **bổ sung**.

Đừng suy ra từ điều này rằng toàn bộ logic agent xung quanh (caches, logging, chọn class loader, transformer) cũng mặc nhiên thread-safe. Cần thiết kế khóa/trạng thái nếu các phần đó có chia sẻ mutable data.

## 10. Điều kiện hợp lệ, ngoại lệ và thứ tự kiểm tra

Trước khi gọi:

~~~java
if (!inst.isModifiableModule(targetModule)) {
    // Module không cho phép redefineModule ở JVM này.
    return;
}
inst.redefineModule(
        targetModule, reads, exports, opens,
        Set.of(), Map.of());
~~~

Đây là **mảnh code trong một phương thức agent**, không tự chạy độc lập; cần định nghĩa `targetModule`, `reads`, `exports`, `opens`. `isModifiableModule` kiểm tra module được sửa bằng API này, **khác** `isModifiableClass` và các cờ `isRetransformClassesSupported`/`isRedefineClassesSupported`. Những cờ dùng cho **thay bytecode class**, không phải quyền sửa module graph.

| Trạng thái/lỗi | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `isModifiableModule(module) == false` | Module không thể sửa bằng `redefineModule` theo JVM | Không gọi bừa; báo cấu hình không hỗ trợ |
| `UnmodifiableModuleException` | JVM từ chối sửa module | Xử lý và báo lỗi module cụ thể |
| `IllegalArgumentException` | Package trong `extraExports`/`extraOpens` không thuộc module, hoặc map value là set rỗng; service provider sai ràng buộc | Kiểm tra `module.getPackages()`, tên package và giá trị map |
| `NullPointerException` | Một đối số là `null` hoặc set/map có key/value `null` | Dùng `Set.of()`/`Map.of()` khi không thay đổi |
| `InaccessibleObjectException` tại `setAccessible` | Package chưa open tới caller module hoặc bị ràng buộc khác | Xác minh đúng target Module/package/caller |
| `IllegalAccessException` lúc gọi public method bằng reflection | Public access chưa hợp lệ trong module/access boundary | Kiểm tra export và tính public của type/member |
| `NoClassDefFoundError` sau khi weave helper | Helper/dependency không resolve được từ defining loader của target | Kiểm tra loader/module graph/đường tìm kiếm helper |
| `IllegalCallerException` khi dùng `Module.addOpens` trên module khác | API `Module.addOpens` không cho caller tùy ý sửa named module khác | Dùng `Instrumentation.redefineModule` của agent được JVM cấp |

**Tập module nhận export/open không được rỗng.** Ví dụ:

~~~java
Map.of("demo.target.api", Set.<Module>of()) // Sai: value set rỗng
Map.of("demo/target/api", Set.of(agent))    // Sai: internal name, không phải package name
Map.of("demo.other", Set.of(agent))         // Sai nếu demo.other không thuộc target
~~~

Đây là **các biểu thức Java minh họa đầu vào sai**, không phải ví dụ nên đem chạy trong production. `extraReads` bản thân có thể là **tập rỗng** vì nó là set thêm quan hệ. Tương tự, toàn bộ `extraExports` hoặc `extraOpens` map có thể rỗng; chỉ **value set của một key có mặt trong map** không được rỗng.

### 10.1. Unnamed module là trường hợp đặc biệt

Theo Javadoc, gọi `redefineModule` trên **unnamed module** là **no-op**. `isModifiableModule(unnamedModule)` luôn trả `true` vì định nghĩa lại nó sẽ không làm gì. Do đó đừng diễn giải `isModifiableModule == true` cho unnamed module là bằng chứng API đã thay đổi quyền thực tế.

Nếu mục tiêu là cấp quyền cho code **trong unnamed module** truy cập một named module, thường cần sửa **named module** ở phía source (qualified export/open) hoặc thay đổi read edges ở named module tương ứng, chứ không dùng `redefineModule` với chính unnamed module làm đối số đầu rồi chờ kết quả.

### 10.2. Các đối số service cũng có ràng buộc

`extraUses` và `extraProvides` không phải trọng tâm nhưng không nên điền dữ liệu tùy tiện. Với `extraProvides`, mỗi provider list phải **không rỗng**, các provider type phải là member của module đó và thực sự triển khai service. Javadoc còn lưu ý agent phải tự bảo đảm accessibility của service type tại các site instrument; API không kiểm tra toàn bộ việc service type có nằm trong package được export và module đọc hợp lệ hay không.

Ví dụ trong bài này truyền đúng **hai container rỗng non-null** để không mở rộng service use/provide.

## 11. Trường hợp Java agent chèn lời gọi helper vào bytecode

Tình huống cụ thể: một transformer chèn lời gọi:

~~~java
probe.bridge.TraceHooks.onEnter();
~~~

Đây là **mảnh code minh họa** gọi từ method nghiệp vụ sau instrumentation. Giả sử method được định nghĩa trong named module `sales.app` và `TraceHooks` nằm ở unnamed module của agent.

Có thể cần:

~~~text
                     sales.app (named)
                       |
                  extraReads
                       |
                       v
                agent unnamed module
                    probe.bridge.TraceHooks

Yêu cầu thêm:
  - Target defining loader thật sự resolve được helper class.
  - Helper nằm ở package có visibility phù hợp.
  - Chữ ký helper không tham chiếu kiểu mà target loader không thấy.
  - Module target có quan hệ reads cần thiết khi liên kết bytecode.
~~~

Nếu mục tiêu khác là agent dùng reflection để đọc private field `sales.app.internal.OrderState`, agent phải **open package của sales.app tới module agent**. Đó là lời gọi `redefineModule(salesAppModule, ..., extraOpens=Map.of("sales.app.internal", Set.of(agentModule)), ...)`. Hai hành vi **khác nhau**: một bên là target muốn **gọi helper**, bên kia agent muốn **đọc target**.

### 11.1. JPMS không thay thế class loading

Ngay cả khi `sales.app.canRead(agentModule) == true`, class loader của `sales.app` vẫn cần **tìm thấy** bytecode helper. Một custom plugin loader cô lập có thể không nhìn thấy class trong system/agent loader. Khi đó có thể có `NoClassDefFoundError` hoặc lỗi liên kết khác dù `Module.canRead` đã đúng.

Giải pháp có thể là:

- Định nghĩa helper tại **shared loader** mà các target có thể truy cập.
- Với agent tương thích, đưa **JAR helper tối thiểu** vào bootstrap search bằng `Instrumentation.appendToBootstrapClassLoaderSearch` khi kiến trúc cần, và xác minh module/package access thật sự.
- Đặt helper riêng trong đúng loader của từng plugin nếu muốn cô lập, đồng thời hiểu các static counters/registries sẽ là **mỗi loader một bản**.
- Sử dụng một bridge/interface có contract đặt ở loader chia sẻ, không chuyển implementation type của plugin qua ranh giới rồi cast theo cùng tên binary.

`redefineModule` **không tự tạo helper class**, không append JAR, không thay class loader, không sửa bytecode `<clinit>` và không làm mọi lớp ở JVM trở thành modifiable.

### 11.2. Agent startup và dynamic attach không giống nhau

Ví dụ dùng `premain` với `-javaagent` nên `Instrumentation` có sẵn từ lúc JVM khởi động. Nếu agent được nạp muộn bằng `agentmain`, việc attach/dynamic agent loading phụ thuộc JVM và cấu hình riêng. Hai kiểu nạp đều có thể cung cấp `Instrumentation` khi JVM hỗ trợ, nhưng không nên gộp khả năng attach vào quyền `redefineModule`.

## 12. So sánh với các cách cấu hình JPMS khác

Có những cách thêm quyền **trước khi JVM chạy**, không cần gọi `Instrumentation` trong agent:

| Cơ chế | Phạm vi | Khác gì `redefineModule`? |
| --- | --- | --- |
| `requires other.module;` | Read edge trong `module-info.java` | Là cấu hình source/module descriptor |
| `exports p;` hoặc `exports p to m;` | Exports package public | Khai báo ở module descriptor |
| `opens p;` hoặc `opens p to m;` | Cho phép reflection sâu tại runtime | Khai báo ở module descriptor |
| `--add-reads M=H` | Đọc thêm khi launch | Thiết lập bằng JVM option trước startup |
| `--add-exports M/p=H` | Export package có đích khi launch | Không cần agent; đã có từ trước `main`/`premain` |
| `--add-opens M/p=H` | Open package có đích khi launch | Không cần agent; đã có từ trước |
| `Module.addReads/addExports/addOpens` | Sửa quan hệ theo caller rules | Named module thường chỉ được tự sửa chính nó từ caller hợp lệ |
| `Instrumentation.redefineModule` | Mở rộng runtime graph từ agent | Có `Instrumentation` và sửa được module khác theo hợp đồng API |

Ví dụ cấu hình tương tự cho app module đọc unnamed module, export public API và open private package cho unnamed module:

~~~bash
java --add-reads demo.target=ALL-UNNAMED --add-exports demo.target/demo.target.api=ALL-UNNAMED --add-opens demo.target/demo.target.internal=ALL-UNNAMED --module-path mods -m demo.target/demo.target.app.Main
~~~

**Không dùng lệnh này để tái hiện stdout trước/sau của bài thực hành**: vì quyền đã được cấp **từ lúc khởi động**, các dòng `...Before=false` và lỗi access ban đầu sẽ không còn đúng. Đây là **lệnh so sánh cú pháp**, không phải bước thứ hai cần chạy với agent.

Đặc biệt, `--add-opens` và `--add-exports` trong lệnh được nhắm tới `ALL-UNNAMED`, có phạm vi rộng hơn `Set.of(agentModule)` nếu JVM có nhiều unnamed modules. Với quyền hạn nhạy cảm, dùng target hạn chế nhất có thể.

## 13. Quy trình chẩn đoán khi agent vẫn gặp lỗi module access

1. **Xác nhận đúng JVM/agent:** `premain`/`agentmain` nhận đúng `Instrumentation` ở JVM cần theo dõi.
2. **Xác nhận đúng đối tượng `Module`:** lấy từ `Class<?>.getModule()` hoặc callback `transform(Module, ...)` khi có thể, không chọn module chỉ qua tên ở layer bất kỳ.
3. **Kiểm tra module nguồn có named không:** với unnamed source, `redefineModule` là no-op.
4. **Kiểm tra modifiable:** gọi `isModifiableModule`, xử lý `UnmodifiableModuleException` nếu cần.
5. **Ghi riêng ba quan hệ:** `source.canRead(destination)`, `source.isExported(pkg, target)`, `source.isOpen(pkg, target)`; xác định đúng chiều.
6. **Kiểm tra key package:** chính xác dotted name, thuộc `source.getPackages()`; map value set không rỗng.
7. **Gọi một lần có chủ đích:** truyền `Set.of()`/`Map.of()` cho các chiều không cần mở.
8. **Xác minh sau khi gọi:** cùng ba truy vấn runtime, rồi thử đúng public invocation/private reflection cần phục vụ.
9. **Nếu vẫn thất bại:** kiểm tra class-loader visibility, đúng helper version, ranh giới package/private/final, JPMS module layer, cache/instrumented code và error stack.
10. **Bảo toàn bảo mật:** ghi nhận quyền đã được cấp để đánh giá sau, không giả định có thể revoke bằng lần gọi sau.

Ví dụ chẩn đoán có `Class<?> targetType` và `Module agentModule` đã biết:

~~~java
Module targetModule = targetType.getModule();
String packageName = targetType.getPackageName();

System.out.println("module=" + targetModule.getName());
System.out.println("package=" + packageName);
System.out.println("modifiable="
        + inst.isModifiableModule(targetModule));
System.out.println("openedToAgent="
        + targetModule.isOpen(packageName, agentModule));
~~~

Đây là **mảnh mã trong agent**, cần có biến `inst`, `targetType`, `agentModule`. Đừng ghi quá nhiều dữ liệu sensitive hoặc in ra hàng nghìn class vào logger bên trong transformer callback: logger/helper có thể tự kích hoạt class loading.

## 14. Những hiểu nhầm thường gặp

1. **“`redefineModule` chính là `redefineClasses`.”** Sai: một API sửa quan hệ module runtime, API kia thay class-file definitions.
2. **“`extraReads` tự cho đọc private field.”** Sai: readability khác deep reflection.
3. **“`extraExports` đủ để `setAccessible(true)` cho mọi private member.”** Sai: cần package open và kiểm tra ràng buộc khác.
4. **“`extraOpens` chỉ liên quan source compile.”** Sai: nó dành cho khả năng reflection runtime; package open còn được coi exported tới module nhận quyền khi query ở runtime.
5. **“Key của `extraOpens` phải là `java/lang`.”** Sai: key là package có dấu chấm như `"java.lang"`.
6. **“Map chứa package không tồn tại vẫn được bỏ qua.”** Sai: API có thể ném `IllegalArgumentException`.
7. **“Set target module rỗng có nghĩa export cho tất cả.”** Sai: value set rỗng là không hợp lệ; không phải unqualified export.
8. **“Truyền `null` cho `extraUses`/`extraProvides` khi không sử dụng.”** Sai: phải non-null, dùng container rỗng.
9. **“Đã thêm quyền thì gọi lại với empty collections để xóa.”** Sai: quan hệ chỉ được mở rộng.
10. **“`isModifiableModule` tương đương `isModifiableClass`.”** Sai: kiểm tra hai loại đối tượng và cơ chế khác nhau.
11. **“`isModifiableModule(unnamed) == true` nghĩa có thể thay đổi nó.”** Sai: redefine unnamed module là no-op.
12. **“Read edge đúng thì class loader tự tìm thấy helper.”** Sai: module graph và class-loader lookup là hai ràng buộc riêng.
13. **“`isExported(pkg, target)` chứng minh mọi module đều thấy package.”** Sai: đây có thể chỉ là qualified export.
14. **“Agent load được module nghĩa reflection chắc chắn thành công.”** Sai: cần đúng caller module, target class/member và opens/export.
15. **“Agent thay đổi `module-info.java` vĩnh viễn trên đĩa.”** Sai: thay đổi có hiệu lực trên module runtime trong JVM.
16. **“Nhiều agent gọi cùng lúc luôn gây xung đột.”** Sai: phương thức `redefineModule` được Javadoc mô tả an toàn cho concurrent use; nhưng caller vẫn cần quản lý trạng thái khác.
17. **“Mở `java.base` vô điều kiện là giải pháp tối ưu cho mọi reflection error.”** Sai: mở quá rộng làm suy yếu encapsulation; chỉ cấp đúng gói/đích cần thiết.
18. **“Reflection vào một package mở chứng minh read edge đã đổi.”** Sai: reflection có đặc tính access check khác liên kết Java thông thường; phải kiểm tra `canRead` riêng.

## 15. Tự kiểm tra kiến thức

1. Trong `redefineModule(M, Set.of(H), ...)`, module nào **đọc** module nào?
2. Package `p.internal` đã được `extraExports` cho agent nhưng chưa `extraOpens`. Có được đảm bảo `setAccessible(true)` trên private field không?
3. Vì sao `Module.isOpen("p", agent)` và `Module.isOpen("p")` có thể cho kết quả khác nhau?
4. Vì sao `isExported("p.internal", agent)` có thể là `true` sau khi chỉ cấp `extraOpens`?
5. Trong ví dụ, lỗi trước khi mở public API và lỗi trước khi mở private field là hai exception nào?
6. Vì sao `agent.getClass().getModule()` không phải cách viết đúng để lấy module của **class `AccessAgent`** nếu `agent` đã là đối tượng `Module`? Hãy dùng `AccessAgent.class.getModule()`.
7. Khi target ứng dụng trong module layer khác boot layer, làm sao chọn đúng `Module` để sửa?
8. Nếu helper nằm trong agent unnamed module nhưng target class loader không thấy helper, chỉ cấp `extraReads` có đủ không?
9. Tại sao việc truyền `Map.of("p", Set.of())` cho `extraExports` là sai?
10. Agent có thể thu hồi qualified opens bằng `redefineModule` lần hai với map rỗng không?
11. `isModifiableModule(unnamedModule)` trả gì và gọi `redefineModule` cho unnamed có tác dụng gì?
12. Tại sao demo chạy mà không cần khai báo `Can-Redefine-Classes: true`?
13. Khi cần dùng thêm service provider, vì sao agent phải tự kiểm tra accessibility của service type ở instrumentation site?

**Kết luận:** `Instrumentation.redefineModule` là công cụ **mở rộng động module graph** cho agent. `extraReads` thêm cạnh đọc **từ module đang sửa**, `extraExports` mở public package **có đích**, `extraOpens` cho phép **deep reflection có đích**. Ba loại quan hệ không thay thế cho nhau; còn phải tính đến class loader, module layer và ràng buộc truy cập thực tế. Đây là thao tác **additive-only** trong JVM, nên hãy cấp tối thiểu, kiểm tra bằng `Module.canRead`/`isExported`/`isOpen` và thử đúng call site cần instrument.

### Tham khảo

- [Java 17 — Instrumentation: redefineModule, isModifiableModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — Module: canRead, isExported, isOpen](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java 17 — AccessibleObject: setAccessible và trySetAccessible](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java 17 — Package java.lang.instrument: agent manifest và lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261)
