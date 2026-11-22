# Kiểm tra `isModifiableModule` và xử lý `UnmodifiableModuleException`

> **Ngữ cảnh:** Java Advance → Instrumentation → **Instrumentation và module**. Kể từ Java 9, Java agent có thể kiểm tra và mở rộng một số quan hệ trong Java Platform Module System (JPMS) bằng `Instrumentation.isModifiableModule` và `Instrumentation.redefineModule`. Bài tập trung vào quyết định có nên thay đổi module, ngoại lệ khi bị từ chối, trường hợp đặc biệt của unnamed module, cấu hình package hợp lệ và cách kiểm chứng quyền truy cập sau thay đổi. Mẫu Java 17+ đã được chạy thử trên OpenJDK 24.

## 1. Bức tranh tổng quan

Giả sử một Java agent muốn dùng reflection để quan sát một private method trong package `demo.internal` của named module `demo.secret`. Nếu package không được open cho module của agent thì `setAccessible(true)` có thể ném `InaccessibleObjectException`. Agent có thể xin JVM mở **đúng package này cho đúng module nhận quyền**, nhưng cần kiểm tra xem module đích có thể được thay đổi hay không:

~~~java
Module targetModule = targetClass.getModule();

if (instrumentation.isModifiableModule(targetModule)) {
    instrumentation.redefineModule(
        targetModule,
        Set.of(),
        Map.of(),
        Map.of("demo.internal", Set.of(agentModule)),
        Set.of(),
        Map.of()
    );
}
~~~

Đây là **mảnh minh họa**, cần các biến `instrumentation`, `targetClass`, `agentModule` và imports tương ứng. Bản đầy đủ có `premain`, manifest, named module và mã chạy nằm ở phần 6.

Có ba điều cần phân biệt:

1. **Module có thể sửa không?** `isModifiableModule(module)` kiểm tra khả năng dùng `redefineModule` với module đó.
2. **Thay đổi đề xuất có hợp lệ không?** Có tên package đúng không, các sets/maps có dữ liệu hợp lệ không, module recipient có đúng không? `isModifiableModule == true` **không** bảo đảm mọi input được JVM chấp nhận.
3. **Thay đổi đã có tác dụng chưa?** Phải kiểm tra quan hệ thực tế bằng `Module.isOpen(package, recipient)`, `Module.isExported(...)` hoặc `Module.canRead(...)`. `redefineModule` trả về `void`, không có boolean thành công.

**Điểm dễ nhầm nhất:** `isModifiableModule` **luôn trả `true` cho unnamed module**, nhưng `redefineModule` lên unnamed module lại là **no-op**. Không được dùng giá trị `true` để kết luận module đó đã được mở thêm một package.

## 2. Hợp đồng `isModifiableModule(Module)`

Chữ ký:

~~~java
boolean isModifiableModule(Module module);
~~~

Theo Java SE API:

- Trả `true` nếu module có thể được thay đổi bằng `redefineModule`, ngược lại trả `false`.
- Với **unnamed module**, luôn trả `true` do quy tắc đặc biệt của API; gọi `redefineModule` trên unnamed module không làm gì.
- Truyền `null` ném `NullPointerException`.
- Có từ Java 9. Đây không phải một biến thể của `isModifiableClass(Class<?>)`.

Lấy `Module` đúng cách:

~~~java
Module fromType = SomeType.class.getModule();

Module fromBootLayer = ModuleLayer.boot()
        .findModule("java.base")
        .orElseThrow();
~~~

Đây là **mảnh code**, trong đó `SomeType` phải là class có sẵn. Nếu module nằm trong **custom module layer** hoặc chưa được resolve, `ModuleLayer.boot().findModule("name")` có thể không thấy. Không có module trong boot layer **không đồng nghĩa module unmodifiable**.

### Phân biệt `Module` và `Class`

| API | Kiểu đối số | Câu hỏi |
|---|---|---|
| `isModifiableModule(Module)` | `Module` | Có thể mở rộng quan hệ JPMS bằng `redefineModule` không? |
| `isModifiableClass(Class<?>)` | `Class<?>` | Class có thuộc loại có thể retransform/redefine không? |
| `isRetransformClassesSupported()` | Không có đối số | JVM và agent có capability retransformation không? |
| `isRedefineClassesSupported()` | Không có đối số | JVM và agent có capability redefinition cho class không? |

Tên tương tự không làm chúng thay thế được nhau. Một module modifiable **không** chứng minh mọi class thuộc module đó có thể sửa method body, cũng không cho phép thêm/xóa field bằng retransform. Ngược lại, `UnmodifiableModuleException` **không phải** `UnmodifiableClassException`.

### Không hard-code khả năng sửa của JVM

Một số HotSpot/OpenJDK runtime báo `true` với các named modules cụ thể. Điều này không có nghĩa tất cả JVM implementations, runtime images và modules đều phải trả `true`. Cách đúng là **kiểm tra trên JVM thực sự chạy agent**, không viết logic phụ thuộc một giá trị quan sát từ một build.

## 3. `redefineModule` bổ sung quyền gì?

Chữ ký chính xác:

~~~java
void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
~~~

Các tham số có vai trò khác nhau:

| Tham số | Ý nghĩa | Lưu ý |
|---|---|---|
| `module` | **Module nguồn** cần sửa | Phải là `Module`, không phải class hoặc module name string |
| `extraReads` | Bổ sung những modules mà module nguồn có thể đọc | Read edge không tự làm package chưa export trở nên public |
| `extraExports` | Export thêm các packages cho tập module nhận quyền | Cho phép truy cập public API theo JPMS; tên package phải thuộc module nguồn |
| `extraOpens` | Open thêm các packages cho tập module nhận quyền | Phục vụ deep reflection; chỉ mở đúng package và recipient cần thiết |
| `extraUses` | Khai báo thêm service types module nguồn sử dụng | Phải xét khả năng truy cập service ở điểm sử dụng |
| `extraProvides` | Khai báo thêm service implementations module nguồn cung cấp | Provider phải thuộc module nguồn, implement service, danh sách hợp lệ |

Ví dụ bổ sung qualified opens:

~~~java
inst.redefineModule(
    sourceNamedModule,
    Set.of(), // extraReads
    Map.of(), // extraExports
    Map.of("demo.internal", Set.of(agentModule)), // extraOpens
    Set.of(), // extraUses
    Map.of()  // extraProvides
);
~~~

**Chiều của quan hệ:** `sourceNamedModule` là module **chứa package** `demo.internal`. `agentModule` là module **nhận quyền mở**. Nếu đảo hai biến, có thể vô tình gọi no-op trên unnamed module của agent hoặc yêu cầu mở một package không thuộc module nguồn.

**Tên package:** `demo.internal` là tên Java có dấu chấm. Không dùng internal name `demo/internal`, class name `demo.internal.SecretBox` hay module name `demo.secret` để thay thế.

### Chỉ bổ sung, không thu hồi

Javadoc quy định `redefineModule` **không được giảm** tập modules được đọc, tập packages được export/open, hoặc services được sử dụng/cung cấp. Một lời gọi tiếp theo với sets/maps rỗng **không hủy** quyền đã cấp ở lời gọi trước.

~~~java
inst.redefineModule(target, Set.of(), Map.of(),
        Map.of("demo.internal", Set.of(agentModule)),
        Set.of(), Map.of());

// Không phải rollback:
inst.redefineModule(target, Set.of(), Map.of(), Map.of(), Set.of(), Map.of());
~~~

Đây là lý do không nên cấp quyền rộng chỉ để “test xem có chạy không”. Trước khi mở private package trong production, hãy xác định nhu cầu, phạm vi module nhận quyền và tác động lên hệ thống.

Javadoc cũng ghi `redefineModule` **safe for concurrent use**, cho phép nhiều agents chỉnh module cùng lúc. Nhưng sự an toàn của mỗi lời gọi **không** làm chuỗi kiểm tra rồi cập nhật của application trở thành một transaction. Các thay đổi bổ sung từ nhiều agent có thể cùng tồn tại.

## 4. Trường hợp đặc biệt: unnamed module

Class trong Java agent JAR nạp theo cơ chế `-javaagent` thuộc **unnamed module của system class loader**. Class Java thông thường trên classpath cũng thuộc unnamed module của defining loader.

~~~java
Module agentModule = AgentEntry.class.getModule();

boolean named = agentModule.isNamed(); // false trong agent JAR tiêu chuẩn
boolean modifiable = inst.isModifiableModule(agentModule); // true
inst.redefineModule(agentModule,
        Set.of(), Map.of(), Map.of(), Set.of(), Map.of()); // no-op
~~~

Đây là **mảnh minh họa**, `AgentEntry`/`inst` là các biến và class trong ngữ cảnh agent.

Hai mệnh đề sau cùng đúng:

- `inst.isModifiableModule(unnamedModule) == true`.
- `inst.redefineModule(unnamedModule, ...)` là **no-op**, không thêm read/open/export edge có tác dụng cần quan sát.

Đừng cố “sửa lại unnamed module” để cấp agent quyền deep reflection vào named module khác. Thay vào đó cần mở package ở **named module đang sở hữu package**, và ghi unnamed module của agent là **recipient** nếu chính nó cần reflection.

**Một số trường hợp khác:**

- `String.class.getModule()` là named module `java.base`, dù `String.class.getClassLoader() == null`.
- `AgentEntry.class.getModule().getName()` là `null` với unnamed module, điều này không có nghĩa class không thuộc module.
- Mỗi class loader có unnamed module riêng. Hai class từ hai loader khác nhau đều có `isNamed() == false` không bảo đảm chúng cùng module object.
- Không phải mọi class do system loader định nghĩa đều ở unnamed module: một ứng dụng named module có thể cũng được system loader định nghĩa.

## 5. `UnmodifiableModuleException` và các ngoại lệ dễ nhầm

Tên đầy đủ: `java.lang.instrument.UnmodifiableModuleException`. Ngoại lệ này có từ Java 9, **kế thừa `RuntimeException`** nên là unchecked exception. Theo API, `Instrumentation.redefineModule(...)` có thể ném khi module không thể được sửa.

| Triệu chứng | Ngoại lệ / kết quả | Cách hiểu đúng |
|---|---|---|
| `inst.isModifiableModule(target) == false` | Boolean `false` | Module không thể sửa theo phép kiểm tra; có thể bỏ thao tác, chọn fallback |
| `inst.redefineModule(...)` gặp module không sửa được | `UnmodifiableModuleException` | Bắt và báo nhánh thất bại, không giả vờ thành công |
| `extraOpens` trỏ package không thuộc module | `IllegalArgumentException` | **Đối số sai**, không nhất thiết module unmodifiable |
| Tập recipient của extraOpens/extraExports rỗng | `IllegalArgumentException` | Thiếu module nhận quyền |
| Tham số module/sets/maps hoặc thành phần bắt buộc là `null` | `NullPointerException` | Lỗi input/logic cần sửa |
| Reflection vào package chưa open | `InaccessibleObjectException` | Chưa được phép deep reflection, khác với lỗi redefineModule |
| `retransformClasses` trên class không modifiable | `UnmodifiableClassException` | Lỗi **class redefinition**, không phải module reconfiguration |
| `retransformClasses` gây thay đổi class schema không được hỗ trợ | `UnsupportedOperationException` | Không suy ra module unmodifiable |

### Cách xử lý có chủ đích

Quy trình khuyến nghị:

1. Kiểm tra module reference không `null`, có đúng tên và module layer cần xử lý không.
2. Xác định named/unnamed bằng `Module.isNamed()`. Nếu unnamed, không gọi redefinition để mong thay đổi quan hệ module.
3. Kiểm tra package thực sự thuộc module nguồn bằng `module.getPackages().contains(packageName)`.
4. Nếu `module.isOpen(packageName, recipient)` đã `true`, không cần mở lần nữa.
5. Nếu `!inst.isModifiableModule(module)`, đưa ra nhánh **không hỗ trợ**. Đừng gọi `redefineModule` chỉ để bỏ qua kết quả.
6. Nếu tiếp tục, gọi `redefineModule` với sets/maps **không null và hợp lệ**, catch `UnmodifiableModuleException`/`IllegalArgumentException` riêng.
7. Sau lời gọi thành công, kiểm tra lại trạng thái `isOpen` hoặc phép kiểm tra tương đương với loại thay đổi mong muốn.
8. Nếu không thể mở, chọn fallback: public API, instrumentation không dùng private reflection, cấu hình launcher được phê duyệt, hoặc tắt tính năng tùy chọn.

**Precheck không thay thế catch.** Một API có kết quả boolean về khả năng sửa và API khác với hợp đồng có thể ném ngoại lệ; khi triển khai một agent ổn định vẫn phải xử lý đường exception. Tránh catch chung `RuntimeException` rồi in thông điệp “module không sửa được” vì lỗi đối số sẽ bị che giấu.

### Ví dụ helper phòng thủ

Mảnh code sau giả sử đang ở bên trong Java agent có `Instrumentation inst` và các imports tương ứng; **không phải file Java độc lập**:

~~~java
static boolean openPackage(Instrumentation inst, Module source,
                           String packageName, Module recipient) {
    if (inst == null || source == null || packageName == null || recipient == null) {
        throw new IllegalArgumentException("Missing required arguments");
    }
    if (!source.isNamed()) {
        return false; // unnamed: redefineModule là no-op
    }
    if (!source.getPackages().contains(packageName)) {
        return false; // không gọi API với package sai
    }
    if (source.isOpen(packageName, recipient)) {
        return true; // đã đủ quyền
    }
    if (!inst.isModifiableModule(source)) {
        return false; // module không cho phép sửa
    }

    try {
        inst.redefineModule(source, Set.of(), Map.of(),
                Map.of(packageName, Set.of(recipient)), Set.of(), Map.of());
        return source.isOpen(packageName, recipient);
    } catch (UnmodifiableModuleException e) {
        return false; // log/fallback có chủ đích trong agent thật
    } catch (IllegalArgumentException e) {
        return false; // lỗi cấu hình, không được gọi là unmodifiable
    }
}
~~~

Đoạn helper tránh việc thay đổi module nếu không cần. Trong production nên ghi log ngắn gọn đủ để phân biệt nhánh `false`, `IllegalArgumentException` và `UnmodifiableModuleException`, nhưng không log private data hoặc message không ổn định như một mã lỗi chuẩn.

## 6. Bài lab Java 17+: kiểm tra module, mở package và test nhánh lỗi

Đây là thí nghiệm **chạy được không cần thư viện bên ngoài**. Nó dùng:

- Named module `demo.secret` chứa `demo.internal.SecretBox`, không export/open package.
- Startup Java agent `ModuleProbeAgent`. Agent kiểm tra named/unnamed module, gọi `redefineModule` để open package cho unnamed module của agent.
- App `Launcher` chỉ in một mốc tại `main`.
- Một **test double `Instrumentation`** tạo bằng `Proxy`, cố tình ném `UnmodifiableModuleException` để kiểm tra code xử lý exception. **Đây không phải lỗi do JVM thật phát sinh**.
- Một lệnh `redefineModule` thật nhưng dùng package sai để quan sát `IllegalArgumentException`.

### 6.1 Cấu trúc dự án

~~~text
module-modifiability-lab/
├── manifest.mf
├── src-agent/
│   └── demo/
│       └── agent/
│           └── ModuleProbeAgent.java
├── src-mod/
│   └── demo.secret/
│       ├── module-info.java
│       └── demo/
│           └── internal/
│               └── SecretBox.java
├── src-app/
│   └── demo/
│       └── app/
│           └── Launcher.java
└── out/                     # tạo bởi các lệnh build
    ├── agent/
    ├── mods/
    ├── app/
    └── module-agent.jar
~~~

Yêu cầu JDK 17+, lệnh `javac`, `jar` và `java`. Chạy mọi câu lệnh trong thư mục gốc dự án. Thư mục `out` được tạo khi compile.

### 6.2 Module cần mở package

`src-mod/demo.secret/module-info.java`:

~~~java
module demo.secret { }
~~~

Đây là **named module**. Descriptor không có `exports demo.internal` và cũng không `opens demo.internal`. Package đó không mở cho module của agent khi JVM mới khởi động.

`src-mod/demo.secret/demo/internal/SecretBox.java`:

~~~java
package demo.internal;

public final class SecretBox {
    private SecretBox() {}

    private static String secret() {
        return "OPENED";
    }
}
~~~

Class public nhưng private static method `secret()` không được phép truy cập sâu từ unnamed module của agent nếu package chưa open. Sau khi agent mở đúng package qua `extraOpens`, phép `setAccessible(true)` cho private method này sẽ thành công trên runtime thử nghiệm.

### 6.3 Ứng dụng

`src-app/demo/app/Launcher.java`:

~~~java
package demo.app;

public final class Launcher {
    public static void main(String[] args) {
        System.out.println("[APP] main");
    }
}
~~~

Ứng dụng **không import** class private hoặc agent. Nó chỉ chứng minh `premain` chạy trước `main`. Module `demo.secret` phải được resolve qua tùy chọn `--add-modules demo.secret` ở lệnh Java, vì không có module dependency từ app classpath.

### 6.4 Java agent: `src-agent/demo/agent/ModuleProbeAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableModuleException;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.Set;

public final class ModuleProbeAgent {
    private ModuleProbeAgent() {}

    public static void premain(String options, Instrumentation inst) throws Exception {
        Module agent = ModuleProbeAgent.class.getModule();
        Module target = ModuleLayer.boot().findModule("demo.secret").orElseThrow();

        System.out.println("[AGENT] unnamed=" + !agent.isNamed());
        System.out.println("[AGENT] unnamedModifiable=" + inst.isModifiableModule(agent));
        inst.redefineModule(agent, Set.of(), Map.of(), Map.of(), Set.of(), Map.of());
        System.out.println("[AGENT] unnamedRedefine=no-op");

        System.out.println("[TARGET] name=" + target.getName());
        System.out.println("[TARGET] modifiable=" + inst.isModifiableModule(target));
        System.out.println("[TARGET] openBefore=" + target.isOpen("demo.internal", agent));

        Class<?> type = Class.forName("demo.internal.SecretBox", false,
                ClassLoader.getSystemClassLoader());
        Method method = type.getDeclaredMethod("secret");
        boolean accessibleBefore;
        try {
            method.setAccessible(true);
            accessibleBefore = true;
        } catch (InaccessibleObjectException expected) {
            accessibleBefore = false;
        }
        System.out.println("[REFLECT] accessibleBefore=" + accessibleBefore);

        // Test double: kiểm tra nhánh exception, không phải JVM thật ném lỗi này.
        simulateUnmodifiable(target, "demo.internal", agent);

        boolean applied = openPackage(inst, target, "demo.internal", agent);
        System.out.println("[TARGET] openApplied=" + applied);
        System.out.println("[TARGET] openAfter=" + target.isOpen("demo.internal", agent));
        if (applied) {
            method.setAccessible(true);
            System.out.println("[REFLECT] result=" + method.invoke(null));
        }

        // Lỗi đối số từ JVM thật: package không tồn tại trong module nguồn.
        try {
            inst.redefineModule(target, Set.of(),
                    Map.of("demo.missing", Set.of(agent)), Map.of(), Set.of(), Map.of());
            System.out.println("[INVALID] unexpectedlyAccepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("[INVALID] rejected=" + expected.getClass().getSimpleName());
        }
    }

    private static void simulateUnmodifiable(
            Module source, String pkg, Module recipient) {
        Instrumentation fake = (Instrumentation) Proxy.newProxyInstance(
                Instrumentation.class.getClassLoader(),
                new Class<?>[]{Instrumentation.class},
                (proxy, method, args) -> {
                    if ("isModifiableModule".equals(method.getName())) return true;
                    if ("redefineModule".equals(method.getName()))
                        throw new UnmodifiableModuleException("deliberate test double");
                    throw new UnsupportedOperationException(method.getName());
                });
        System.out.println("[SIMULATED] openApplied="
                + openPackage(fake, source, pkg, recipient));
    }

    private static boolean openPackage(Instrumentation inst, Module source,
            String pkg, Module recipient) {
        if (!source.isNamed()) {
            System.out.println("[OPEN] unnamedNoOp");
            return false;
        }
        if (!inst.isModifiableModule(source)) {
            System.out.println("[OPEN] moduleNotModifiable");
            return false;
        }
        if (source.isOpen(pkg, recipient)) {
            System.out.println("[OPEN] alreadyOpen");
            return true;
        }
        try {
            inst.redefineModule(source, Set.of(), Map.of(),
                    Map.of(pkg, Set.of(recipient)), Set.of(), Map.of());
            return true;
        } catch (UnmodifiableModuleException e) {
            System.out.println("[OPEN] rejected=UnmodifiableModuleException");
            return false;
        } catch (IllegalArgumentException e) {
            System.out.println("[OPEN] invalidArguments");
            return false;
        }
    }
}
~~~

Đây là **toàn bộ file biên dịch được**. Khi dùng agent thật, nên mở rộng `openPackage` bằng validate `source.getPackages()` và `null` checks như helper ở mục 5; trong bài lab, hai trường hợp lỗi được minh họa một cách riêng biệt để dễ quan sát.

### 6.5 Hiểu hai đường chạy: test double và JVM thật

**Nhánh giả lập:** `simulateUnmodifiable(...)` tạo `Proxy` implement `Instrumentation`. Khi `openPackage` gọi `isModifiableModule`, proxy trả `true`. Khi gọi `redefineModule`, proxy ném `UnmodifiableModuleException`. Điều đó chứng minh nhánh catch trả `false` và không làm chương trình thoát. Nó **không** chứng minh module `demo.secret` thực sự không modifiable.

**Nhánh thật:** ngay sau test double, agent truyền **`inst` thật** từ JVM vào `openPackage`. Trên HotSpot/OpenJDK thử nghiệm, named module này modifiable; lời gọi với `extraOpens` hợp lệ thành công và package trở nên open cho agent. Khi đó `Method.setAccessible(true)` được phép và invocation trả chuỗi `OPENED`.

**Negative test thật:** sau khi open, một lời gọi `redefineModule` đưa `demo.missing` vào `extraExports`; package đó không thuộc module `demo.secret`, nên JVM ném `IllegalArgumentException`. Lỗi này có **nguyên nhân khác** với `UnmodifiableModuleException`.

### 6.6 Manifest và lệnh build

`manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ModuleProbeAgent

~~~

Có newline và dòng trống cuối manifest. `-javaagent` dùng `Premain-Class`, không cần `Agent-Class`, `Can-Retransform-Classes` hay `Can-Redefine-Classes`, vì ta **không** thực hiện retransform/redefine class.

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/mods out/app

javac --release 17 -d out/agent src-agent/demo/agent/ModuleProbeAgent.java
javac --release 17 --module-source-path src-mod -d out/mods -m demo.secret
javac --release 17 -d out/app src-app/demo/app/Launcher.java
jar --create --file out/module-agent.jar --manifest manifest.mf -C out/agent .

java -javaagent:out/module-agent.jar --module-path out/mods --add-modules demo.secret -cp out/app demo.app.Launcher
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/mods, out/app | Out-Null

javac --release 17 -d out/agent src-agent/demo/agent/ModuleProbeAgent.java
javac --release 17 --module-source-path src-mod -d out/mods -m demo.secret
javac --release 17 -d out/app src-app/demo/app/Launcher.java
jar --create --file out/module-agent.jar --manifest manifest.mf -C out/agent .

java "-javaagent:out/module-agent.jar" --module-path out/mods --add-modules demo.secret -cp out/app demo.app.Launcher
~~~

Lệnh PowerShell cuối được viết trên **một dòng** để không phụ thuộc ký tự nối dòng. Hai lệnh `javac` khác nhau tương ứng với **class agent** và **named module**. `--module-source-path src-mod` đòi đúng thư mục `src-mod/demo.secret` có `module-info.java`. Tùy chọn `--add-modules demo.secret` khiến JVM resolve named module vào boot layer để agent tìm được.

Có thể kiểm tra JAR:

~~~bash
jar --list --file out/module-agent.jar
~~~

JAR phải chứa `META-INF/MANIFEST.MF` và `demo/agent/ModuleProbeAgent.class`. Agent được gọi bởi JVM từ `-javaagent`, nên không cần đưa chính agent JAR vào `-cp`.

### 6.7 Stdout đã kiểm chứng trên OpenJDK 24

Các file Java được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24. Stdout:

~~~text
[AGENT] unnamed=true
[AGENT] unnamedModifiable=true
[AGENT] unnamedRedefine=no-op
[TARGET] name=demo.secret
[TARGET] modifiable=true
[TARGET] openBefore=false
[REFLECT] accessibleBefore=false
[OPEN] rejected=UnmodifiableModuleException
[SIMULATED] openApplied=false
[TARGET] openApplied=true
[TARGET] openAfter=true
[REFLECT] result=OPENED
[INVALID] rejected=IllegalArgumentException
[APP] main
~~~

Diễn giải đúng theo **nguồn từng dòng**:

| Mốc | Nguồn | Bằng chứng |
|---|---|---|
| `[AGENT] unnamed=true` | JVM thật | Agent nằm trong unnamed module |
| `unnamedModifiable=true` | JVM thật | Hợp đồng `isModifiableModule` cho unnamed module |
| `unnamedRedefine=no-op` | JVM thật | `redefineModule` trên unnamed module không thay đổi quan hệ |
| `[TARGET] modifiable=true` | JVM thật | Module `demo.secret` modifiable **trong runtime thử nghiệm** |
| `openBefore=false` | JVM thật | Package chưa open cho agent |
| `accessibleBefore=false` | JVM thật | Deep reflection bị từ chối |
| `[OPEN] rejected=UnmodifiableModuleException` | **Test double** | Catch của helper hoạt động với lỗi giả lập |
| `[SIMULATED] openApplied=false` | **Test double** | Fallback về `false` thay vì làm chương trình lỗi |
| `[TARGET] openApplied=true` | JVM thật | `redefineModule` mở package hợp lệ |
| `openAfter=true` | JVM thật | Quan hệ opens mới đã có |
| `[REFLECT] result=OPENED` | JVM thật | Reflection vào private method thành công sau khi mở |
| `[INVALID] rejected=IllegalArgumentException` | JVM thật | Cấu hình extraExports sai package |
| `[APP] main` | JVM thật | Ứng dụng chạy sau startup agent |

**Không gọi dòng `[OPEN] rejected=UnmodifiableModuleException` là lỗi thật từ JVM**: nó do `Proxy` sinh ra. Bài thử thực tế trong runtime đó cho thấy `demo.secret` modifiable và có thể được mở package. Một JVM khác có thể có khả năng sửa module hoặc tình huống access khác; không hard-code giá trị `true` cho mọi named module.

## 7. Các phép thử thay đổi để hiểu cơ chế

**Thử 1 — không đưa module vào boot layer:** bỏ `--add-modules demo.secret` nhưng vẫn để `--module-path out/mods`. Khi agent gọi `ModuleLayer.boot().findModule("demo.secret").orElseThrow()`, có thể xảy ra `NoSuchElementException` vì module chưa được resolve. Đây là **vấn đề resolution**, không phải module unmodifiable.

**Thử 2 — package sai:** đổi lời gọi thật thành `Map.of("demo.missing", Set.of(agent))` trong `extraOpens`. Nó bị `IllegalArgumentException` vì package không thuộc source. Ngay cả khi `isModifiableModule(target) == true`, yêu cầu này vẫn không hợp lệ.

**Thử 3 — module báo false:** trong proxy test double, đổi `isModifiableModule` trả `true` thành `false`. Khi đó `openPackage` in `moduleNotModifiable` và trả `false` **trước** lời gọi `redefineModule`. Đây là kiểm thử nhánh `false` bằng giả lập có kiểm soát, không phụ thuộc JVM cung cấp một module không modifiable.

**Thử 4 — package đã mở sẵn:** chạy module với launcher configuration có `--add-opens demo.secret/demo.internal=ALL-UNNAMED`. Khi package đã open cho unnamed module của agent, `isOpen(...)` ban đầu có thể là `true` và reflection trước lời gọi agent sẽ không còn bị từ chối. Bài học: **đừng hard-code stdout kiểm chứng của môi trường mặc định sau khi đã đổi flags**.

**Thử 5 — thử lỗi null:** lời gọi `inst.isModifiableModule(null)` phải ném `NullPointerException` theo hợp đồng. Chỉ thử trong khối bắt exception; không dùng null như một Module hợp lệ. Đối với `redefineModule`, tất cả sáu tham số và các thành phần trong sets/maps phải tuân thủ quy tắc non-null.

## 8. Lựa chọn fallback khi module không sửa được

Không có cách an toàn hay hợp lệ để “bỏ qua” một `UnmodifiableModuleException` rồi giả định quyền đã cấp. Khi agent cần reflection nhưng runtime không cho thay module:

- **Ưu tiên API public** hoặc hook khác để giảm nhu cầu deep reflection.
- **Cấu hình khi JVM khởi động** nếu bạn kiểm soát launcher và chủ hệ thống chấp thuận. Ví dụ mở package ở startup có thể dùng `--add-opens demo.secret/demo.internal=ALL-UNNAMED`. Đây là quyền **rộng hơn** qualified open dành riêng cho một module trong ví dụ; phải cân nhắc blast radius.
- **Chỉnh module descriptor** nếu dự án sở hữu source: `opens demo.internal to specific.named.module;` (nếu module recipient được thiết kế phù hợp), thay vì sửa runtime không được phép.
- **Tắt feature** cần quyền này, ghi trạng thái rõ là `MODULE_ACCESS_UNAVAILABLE`, không báo metrics/tracing thành công giả.
- **Chẩn đoán theo từng JVM**: vendor, phiên bản JDK, module name/layer, package, recipient, ngoại lệ cụ thể. Không suy luận từ một thông báo chung “agent failed”.

Lệnh startup minh họa fallback trên JVM hỗ trợ:

~~~bash
java --module-path out/mods --add-modules demo.secret --add-opens demo.secret/demo.internal=ALL-UNNAMED -cp out/app demo.app.Launcher
~~~

Lệnh này chỉ minh họa **quyền opens được khai ở launcher**, không có agent thì không có mã dùng reflection. Nó khác với mở package cho **chỉ một module nhận quyền** bằng `redefineModule` và không nên xem là thay thế mặc định trong production.

## 9. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân hợp lý | Hành động |
|---|---|---|
| `isModifiableModule(unnamed) == true` nhưng gọi redefine không đổi gì | Với unnamed, `redefineModule` là no-op | Xác định đúng **named source module** chứa package |
| `isModifiableModule(named) == false` | Module không modifiable theo runtime | Bỏ thao tác, dùng fallback |
| `UnmodifiableModuleException` | JVM không sửa được module trong lời gọi | Catch riêng, không suy diễn thành lỗi class |
| `IllegalArgumentException` | Sai package, empty recipient hoặc provider sai | Validate sets/maps và tên package |
| `NullPointerException` | Module/arg/collection chứa null | Sửa logic input thay vì cố catch để tiếp tục |
| `InaccessibleObjectException` | Package chưa open cho caller/agent | Xem source module, package, recipient và `isOpen` |
| `ClassNotFoundException` | Wrong classloader hoặc module chưa resolve | Kiểm tra module path, layer, loader |
| `NoSuchElementException` từ `orElseThrow()` | Module name không có trong layer đang tra cứu | Dùng đúng ModuleLayer, `--add-modules` nếu cần |
| `isOpen(pkg, recipient) == false` sau call | Lời gọi chưa mở đúng quan hệ hoặc thất bại | Kiểm tra named/unnamed, extraOpens và return/exception |
| `isModifiableClass(clazz) == true` | Chỉ trả lời chuyện **class** | Không thay thế `isModifiableModule` |
| `--add-opens` giải quyết được reflection | Launcher cấp quyền trước | Đánh giá phạm vi, đừng mở rộng quá yêu cầu |
| Test double in `UnmodifiableModuleException` | Proxy đã ném lỗi theo thiết kế | Không báo đó là lỗi thực từ HotSpot |

## 10. Câu hỏi tự kiểm tra

1. **`isModifiableModule` nhận tham số kiểu gì?** `Module`, không phải `Class<?>`.
2. **Đưa `null` vào `isModifiableModule` ra sao?** Ném `NullPointerException`.
3. **Tại sao unnamed module luôn trả `true`?** Theo đặc tả, `redefineModule` với unnamed là no-op.
4. **Named module modifiable đồng nghĩa được mở mọi package tùy ý?** Không; package phải thuộc module và đối số phải hợp lệ.
5. **Ngoại lệ nào cho biết module không thể sửa?** `UnmodifiableModuleException`.
6. **Ngoại lệ này checked hay unchecked?** Unchecked, kế thừa `RuntimeException`.
7. **Khác `UnmodifiableClassException` thế nào?** Một ngoại lệ cho module configuration; ngoại lệ kia cho class retransform/redefine.
8. **Cách đo xem package thực sự open cho agent chưa?** `source.isOpen(packageName, agentModule)`.
9. **Nếu mở module nguồn là unnamed, có làm nó thành named module?** Không.
10. **`extraExports` và `extraOpens` khác nhau?** Export cho public API visibility; opens cho deep reflection.
11. **Có thể dùng `redefineModule` để xóa opens đã cấp?** Không; API chỉ mở rộng.
12. **Vì sao lab cần `Proxy`?** Kiểm thử catch của `UnmodifiableModuleException` một cách deterministic; JDK thử nghiệm không phát sinh lỗi thật cho module ấy.
13. **Lỗi package không tồn tại ném gì?** `IllegalArgumentException`, không được gọi là `UnmodifiableModuleException`.
14. **Nếu module ở custom layer, `ModuleLayer.boot()` luôn thấy?** Không; phải dùng đúng layer.

## 11. Checklist thiết kế agent

- [ ] Lấy đúng source `Module`, đúng module layer, xác định named/unnamed.
- [ ] Với unnamed module, ghi nhận `isModifiableModule=true` nhưng không nhầm `redefineModule` no-op với thay đổi thật.
- [ ] Kiểm tra `isModifiableModule` cho named module trước khi thay đổi.
- [ ] Bắt `UnmodifiableModuleException` riêng; phân biệt `IllegalArgumentException` và `NullPointerException`.
- [ ] Kiểm tra source package thuộc module và recipient module set không rỗng.
- [ ] Chỉ cấp tối thiểu `extraReads`/`extraExports`/`extraOpens`/services cần dùng.
- [ ] Đo lại `isOpen`, `isExported` hoặc `canRead` sau khi áp dụng.
- [ ] Không dùng `isModifiableClass`/retransform capability thay cho `isModifiableModule`.
- [ ] Tách lỗi reflection, class loading, module resolution và module reconfiguration.
- [ ] Thử nhánh error bằng test double; trong báo cáo phân biệt rõ simulated và real JVM behavior.
- [ ] Nếu không thể mở package, có fallback rõ và không báo thành công giả.
- [ ] Không kỳ vọng `redefineModule` lần sau có thể revoke quan hệ đã thêm.

## Tài liệu chuẩn

- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isModifiableModule`, `redefineModule`, giá trị unnamed, các tham số, lỗi và tính concurrent.
- [Java SE 21 — `UnmodifiableModuleException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableModuleException.html): unchecked exception khi module không thể sửa.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): Java 17+ signatures và hợp đồng.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `isNamed`, `isOpen`, `getPackages`, `isExported` và `canRead`.
- [Java SE 21 — `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): deep reflection khi module không open package.
- [JLS 21 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): package exports/opens, named và unnamed modules.
