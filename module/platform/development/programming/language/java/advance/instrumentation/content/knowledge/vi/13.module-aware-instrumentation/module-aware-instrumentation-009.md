# Chỉ mở đúng package và đúng module cần cho helper hoặc phản chiếu

Khi instrument một Java application dùng **Java Platform Module System (JPMS)**, Java agent có thể cần cho helper gọi vào một package chưa export, hoặc đọc một private field bằng reflection. Cách giải quyết không nên là mở toàn bộ module hay mọi package của JDK: **mở đúng package cần thao tác cho đúng module thực hiện thao tác**, và chỉ bổ sung quan hệ `reads` hoặc `exports` khi nghiệp vụ thật sự cần.

Từ Java 9, `java.lang.instrument.Instrumentation` cung cấp `redefineModule` để **bổ sung** quan hệ đọc module, export package và open package tại runtime. API này mang quyền mạnh: mở package cho một module có thể cho **mọi code trong module nhận quyền** thực hiện deep reflection vào các lớp thuộc package đó, không chỉ riêng helper mà bạn tưởng tượng. Vì vậy phải xem **đơn vị cấp quyền là module + package**, không phải một method/field cụ thể.

Bài này tập trung vào thiết kế tối thiểu quyền cho Java agent và helper: phân biệt `reads`, `exports`, `opens`; hiểu hai chiều quan hệ giữa module nguồn và module đích; dùng `Instrumentation.redefineModule` với tham số chính xác; kiểm tra quyền trước–sau; tránh `ALL-UNNAMED` khi có thể chỉ cấp cho một module; và chạy demo Java 17+ để thấy package cần thiết được mở trong khi package khác vẫn kín.

## 1. Mô hình: Ai cần truy cập cái gì?

Giả sử ứng dụng có named module `com.shop.core` và trong module có:

```text
com.shop.core
  ├─ com.shop.api
  │    └─ OrderFacade               (API công khai)
  ├─ com.shop.internal
  │    └─ PricingState              (trạng thái private)
  └─ com.shop.auth
       └─ TokenVault                (dữ liệu nhạy cảm)
```

Một agent có `ProbeHelper` muốn xem `PricingState` để chẩn đoán lỗi. Nếu helper thực hiện `Field.trySetAccessible()` hoặc `MethodHandles.privateLookupIn(...)`, vấn đề thường là package `com.shop.internal` **không open tới module chứa helper**.

**Đường cấp quyền đúng về nguyên tắc:**

```text
module com.shop.core
  package com.shop.internal
          |
          | opens ... to
          v
module chứa ProbeHelper

module com.shop.core
  package com.shop.auth
          |
          | KHÔNG opens to helper
          X
```

Không cần tự động mở `com.shop.auth` chỉ vì nó cùng module. Cũng không cần mở toàn bộ `java.base`, cấp `--add-opens=...=ALL-UNNAMED` hoặc export `com.shop.internal` cho mọi người chỉ vì một phép đo yêu cầu reflection.

Một số điểm phải biết ngay:

- **Open** là quyền của **module sở hữu package**, hướng tới **module nhận quyền**.
- Một module có thể chứa nhiều package; cấu hình chỉ mở đúng một package nếu cần.
- Module nhận quyền có thể là **named** hoặc **unnamed module**. Java agent JAR khởi động thông thường được nạp bởi system class loader vào **unnamed module** của loader đó.
- Các unnamed modules từ **những class loader khác nhau** không mặc nhiên là cùng một đối tượng `Module`.
- **Mở package không tự load helper**. Quyền JPMS và class-loader visibility là hai vấn đề riêng.

## 2. Ba quan hệ cần tách rạch ròi: reads, exports, opens

Đây là bảng quan trọng nhất trước khi gọi `redefineModule`.

| Cơ chế | Hướng | Cho phép làm gì | Không tự bảo đảm |
|---|---|---|---|
| `reads` | Module **A đọc B** | A có quan hệ readability với B | B không vì thế export hay open package của mình |
| `exports p to A` | Module **B sở hữu p** export p cho A | A có thể truy cập **public types và public/protected API thích hợp** theo luật Java khi các điều kiện khác thỏa | Không tự cho deep reflection vào private members |
| `opens p to A` | Module **B sở hữu p** open p cho A | Code trong A có thể thực hiện **deep reflection** vào các type trong p theo API phù hợp | Không tự thay class loader, cấp quyền vào package khác hoặc bỏ qua các kiểm tra còn lại |
| `exports p` không có `to` | B export p vô điều kiện | Nhiều module khác có thể sử dụng public API | Phạm vi mở rộng hơn qualified export |
| `opens p` không có `to` | B open p vô điều kiện | Nhiều module khác có thể deep-reflect vào package | Phạm vi lớn hơn qualified open |

Một chi tiết của `Module.isExported(p, other)`: package được **open** đến `other` cũng được coi là **exported đến other tại runtime** theo đặc tả. Nhưng điều này **không** khiến `exports` và `opens` trở thành một khái niệm. Deep reflection là khả năng rộng hơn truy cập public API.

### 2.1. Ví dụ về chiều cấp quyền

Giả sử:

```text
M = module com.shop.core          (chứa com.shop.internal.PricingState)
H = module io.acme.agent.helper   (chứa ReflectiveProbe)
```

**Helper H muốn đọc private field của class ở M:**

- M cần **open** `com.shop.internal` **tới H**.
- Nếu dùng `MethodHandles.privateLookupIn` từ H sang M, H còn phải **read M** và caller lookup phải có quyền `MODULE`/`PRIVATE` thích hợp.
- Một phép `trySetAccessible` để deep-reflect cũng chịu điều kiện openness của target package đến caller module; không nên nhầm với requirement của `privateLookupIn`.

**Code trong M muốn gọi helper ở H bằng bytecode được chèn:**

- M cần có khả năng **read H** khi cần để liên kết tham chiếu.
- Nếu H là named module, package chứa public helper API cần **export tới M** khi cần truy cập public types/members đó.
- Nếu helper nằm ở unnamed module phù hợp, có quy tắc đặc biệt của `java.lang.instrument` đối với các class được transform (xem mục 8); không tự suy rằng mọi named helper đều nhận cùng hỗ trợ.
- Dù readability/exports đúng, target class loader vẫn phải **resolve được helper class**; nếu không có thể lỗi `NoClassDefFoundError`.

**Chú ý chiều:** Muốn helper H nhìn private fields trong M thì việc gọi `redefineModule(H, ...)` để open package của H là **sai hướng**. Target của `extraOpens` phải là module **đang sở hữu package cần mở**, tức M.

### 2.2. Phân biệt việc “không export” và “không open”

Một named module:

```java
module com.shop.core {
    exports com.shop.api;
}
```

Từ module khác, code có thể dùng public API trong `com.shop.api` nếu đọc được `com.shop.core`. Nhưng không vì thế mà có thể truy cập private members của `com.shop.api.OrderFacade` bằng `setAccessible(true)`. Với `com.shop.internal` chưa export/open, các quy tắc truy cập còn chặt hơn.

Nếu chỉ cần gọi public API, hãy ưu tiên **API công khai** hoặc một qualified export khi được phê duyệt. Nếu thực sự cần private reflection, dùng **qualified open** cho package tối thiểu. Không mở package chỉ để sửa một lỗi `ClassNotFoundException` do class loader không thấy JAR.

## 3. API đúng: Instrumentation.redefineModule

Từ Java 9, chữ ký API:

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

Cần hiểu **module đầu tiên là module được mở rộng**, không phải “module của agent”. Ý nghĩa từng tham số:

| Tham số | Ý nghĩa | Khi chỉ cần deep reflection |
|---|---|---|
| `module` | Module cần bổ sung reads/exports/opens/uses/provides | **Module sở hữu class/package cần đọc** |
| `extraReads` | Các module mà `module` sẽ đọc thêm | `Set.of()` nếu không cần thay reads |
| `extraExports` | Package name → tập module được export thêm | `Map.of()` nếu không cần public export riêng |
| `extraOpens` | Package name → tập module được open thêm | **Chỉ một package và module helper cần thiết** |
| `extraUses` | Service types mà module dùng thêm | `Set.of()` nếu không thay ServiceLoader dependency |
| `extraProvides` | Service type → implementation classes được cung cấp thêm | `Map.of()` nếu không thêm providers |

Một lần mở một package `com.shop.internal` của target module cho đúng helper module:

```java
Module target = PricingState.class.getModule();
Module helper = ReflectiveProbe.class.getModule();

if (!target.isModifiableModule()) {
    // Sai API: Module không có phương thức isModifiableModule().
}
```

**Đoạn trên cố ý chỉ là ví dụ đối chiếu lỗi API, không phải code dùng trong ứng dụng.** Kiểm tra modifiability **không** phải phương thức của `Module`; dùng đối tượng `Instrumentation`:

```java
// Snippet trong agent; inst, target, helper đã được xác định.
if (!inst.isModifiableModule(target)) {
    reportSkipped("MODULE_UNMODIFIABLE");
} else {
    inst.redefineModule(
        target,
        Set.of(),
        Map.of(),
        Map.of("com.shop.internal", Set.of(helper)),
        Set.of(),
        Map.of()
    );
}
```

`reportSkipped` là hàm minh họa chưa định nghĩa, không phải source runnable độc lập. Ví dụ hoàn chỉnh ở mục 5.

### 3.1. Tên package phải là dotted name

`extraOpens` nhận **tên package đầy đủ dạng Java**:

```text
ĐÚNG:  com.shop.internal
SAI:   com/shop/internal
SAI:   com.shop.internal.PricingState
SAI:   com.shop.* 
```

Đơn vị cấp quyền là **package**, không phải tên class và không có wildcard trong map keys. Nếu muốn mở nhiều package thì phải liệt kê **đúng từng package**, không dùng tên module hoặc prefix để yêu cầu mở toàn bộ.

### 3.2. Map value phải là một tập module **không rỗng**

`Map.of("com.shop.internal", Set.of(helper))` hợp lệ. `Map.of("com.shop.internal", Set.of())` không hợp lệ cho `extraOpens` và có thể gây `IllegalArgumentException`. Đưa package không thuộc target module vào `extraOpens`/`extraExports` cũng gây `IllegalArgumentException`.

Trước khi thay đổi, có thể kiểm tra:

```java
if (!target.getPackages().contains("com.shop.internal")) {
    throw new IllegalArgumentException("Not a package of target module");
}
```

Đây là đoạn minh họa với `target` đã khai báo. Không dựa vào việc cùng prefix `com.shop` để suy rằng package chắc chắn thuộc named module ấy.

### 3.3. Nếu không cần quyền nào khác, dùng các tập/map rỗng

Đừng thêm `extraReads`, `extraExports`, `extraUses`, `extraProvides` chỉ vì hàm có sáu tham số. Một lời gọi đúng nhu cầu có thể dùng:

```java
inst.redefineModule(
    target,
    Set.of(),                                  // không bổ sung reads
    Map.of(),                                  // không bổ sung exports
    Map.of("com.shop.internal", Set.of(helper)), // chỉ open package này
    Set.of(),                                  // không bổ sung uses
    Map.of()                                   // không bổ sung provides
);
```

Vì `extraOpens` đã đủ cho `Field.trySetAccessible` trong tình huống này, **không cần** đồng thời export tất cả package hay thêm reads theo cảm tính.

### 3.4. Chỉ bổ sung, không thu hồi

`redefineModule` **không thể giảm** tập module được đọc, package được export/open hoặc service dependencies. Đây không phải API “thử mở rồi đóng lại”.

```text
T0: module M chưa opens p tới H
T1: agent redefineModule(M, extraOpens={p -> {H}})
T2: M đã opens p tới H
T3: agent muốn đóng lại -> KHÔNG có thao tác thu hồi qua redefineModule
```

Nếu module đã open rộng trước đó qua manifest/CLI/app code, một lần open hẹp khác **không giảm** phạm vi cũ. Muốn quay lại cấu hình quyền ban đầu có thể cần **khởi động JVM mới** với cấu hình đúng. Vì vậy kiểm duyệt quyền trước khi gọi API quan trọng hơn việc giả định có rollback.

### 3.5. isModifiableModule khác isModifiableClass

- `inst.isModifiableModule(module)` kiểm tra có thể thay đổi module bằng `redefineModule` hay không.
- `inst.isModifiableClass(clazz)` kiểm tra class có thể redefine/retransform hay không.

Đây là **hai vấn đề độc lập**. Không suy từ `isModifiableClass(clazz)==true` rằng `redefineModule(clazz.getModule(),...)` sẽ hợp lệ.

Đặc biệt, `isModifiableModule(unnamedModule)` luôn trả `true` theo hợp đồng Java API, **nhưng redefine một unnamed module là no-op**. Đừng lấy `true` của trường hợp ấy rồi báo “đã mở package mới”.

## 4. Kiểm tra quyền trước và sau khi mở

Các phương thức của `java.lang.Module` giúp chẩn đoán:

```java
Module source = TargetClass.class.getModule();
Module consumer = HelperClass.class.getModule();

boolean reads = consumer.canRead(source);
boolean exported = source.isExported("com.shop.internal", consumer);
boolean opened = source.isOpen("com.shop.internal", consumer);
```

Đây là **snippet minh họa**: `TargetClass`/`HelperClass` là các class có thật trong hệ thống của bạn. Các boolean có thể khác nhau tùy module/configuration.

**Ý nghĩa chính xác:**

- `consumer.canRead(source)` hỏi liệu module người dùng có đọc module chứa target hay không.
- `source.isExported(packageName, consumer)` hỏi target package có được export **ít nhất** tới consumer không. Một package đã open tới consumer cũng được xem là exported tại runtime theo Javadoc.
- `source.isOpen(packageName, consumer)` hỏi target package có được open **ít nhất** tới consumer không. Giá trị này là điều kiện quan trọng cho deep reflection.
- `source.isOpen(packageName)` **không có đối số module** hỏi openness vô điều kiện, không phải qualified open.
- `getModule().isNamed()` giúp phân biệt named/unnamed; `getName()==null` với unnamed module là bình thường.

**Đừng dùng sai:**

```java
source.isOpen("com.shop.internal")           // khác yêu cầu tới 1 consumer
source.isOpen("com.shop.internal", consumer) // đúng câu hỏi qualified open
```

Sau một qualified open, `isOpen(packageName,consumer)` có thể là `true` nhưng `isOpen(packageName)` vẫn `false`. Đó là **đúng thiết kế tối thiểu quyền**, không phải lỗi.

### Kiểm tra hành vi, không chỉ flag

Ngay cả khi `isOpen==true`:

- Phải chắc chắn `consumer` là **đúng Module object của code thực sự gọi reflection**, không phải một helper class cùng tên ở loader khác.
- Reflection vào field/method cụ thể vẫn có thể lỗi vì class không tìm thấy, class loader khác, SecurityManager/policy đặc biệt hoặc thao tác API không phù hợp.
- `MethodHandles.privateLookupIn` yêu cầu thêm điều kiện readability và quyền của caller lookup.
- Module permission không tự khiến class ở custom loader hiện diện trên system classpath.

Hãy xác minh **đúng phép truy cập cần dùng** sau khi open, ví dụ `Field.trySetAccessible()` trả `true` cho field đã được phê duyệt.

## 5. Thí nghiệm Java 17+ hoàn chỉnh: chỉ mở một package cho một agent

Ta sẽ tạo một **named module** `demo.target` với **hai package không export/open**:

- `demo.target.internal`: chứa private field `marker` mà agent muốn đọc.
- `demo.target.other`: chứa private field `hidden` mà agent **không được mở**.

Agent là một startup agent `-javaagent` được tải vào **unnamed module của system class loader**. Trong `premain`, agent tìm đúng module mục tiêu, kiểm tra reflection trước khi mở, gọi `Instrumentation.redefineModule` để chỉ open `demo.target.internal` tới **Module object của chính agent**, kiểm tra lại field, và xác nhận package khác vẫn kín.

### 5.1. Tạo đúng cấu trúc thư mục

```text
module-open-lab/
  src/
    demo.target/
      module-info.java
      demo/target/Main.java
      demo/target/internal/SecretBox.java
      demo/target/other/OtherSecret.java
  agent-src/
    demo/agent/OpenAgent.java
  agent.mf
```

Đây là **bốn tệp Java của target module và một tệp Java của agent**. Không cần bytecode transformer, thư viện ASM/Byte Buddy hay quyền retransform: mục tiêu của ví dụ là **cấp quyền JPMS bằng Instrumentation**.

### 5.2. `src/demo.target/module-info.java`

```java
module demo.target {
    // Cố ý không exports/opens hai package bên dưới.
}
```

Không có `opens demo.target.internal;`, cũng không có `exports demo.target.internal;`. Đây là module kín bình thường. Việc không export package chứa `Main` không ngăn launcher khởi chạy main qua cú pháp `-m demo.target/demo.target.Main` trong tình huống chuẩn.

### 5.3. `src/demo.target/demo/target/Main.java`

```java
package demo.target;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP_STARTED");
    }
}
```

Chương trình chính chỉ in một dòng. Nó không trực tiếp gọi agent và không cần sửa `module-info.java` để thêm `requires` đến code của agent.

### 5.4. `src/demo.target/demo/target/internal/SecretBox.java`

```java
package demo.target.internal;

public final class SecretBox {
    private static int marker = 7;
}
```

Private field `marker` được dùng như dữ liệu **không nhạy cảm trong demo**. Trong sản phẩm thật, việc một agent có thể truy cập private field không có nghĩa được phép log credential, token hay dữ liệu cá nhân.

### 5.5. `src/demo.target/demo/target/other/OtherSecret.java`

```java
package demo.target.other;

public final class OtherSecret {
    private static int hidden = 9;
}
```

Đây là package đối chứng. Agent cố `trySetAccessible` vào private field ở đây sau khi mở package `demo.target.internal`; nó phải **vẫn thất bại**. Chính test âm tính này chứng minh quyền không bị mở rộng ngoài phạm vi cần thiết.

### 5.6. `agent-src/demo/agent/OpenAgent.java`

```java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.util.Map;
import java.util.Set;

public final class OpenAgent {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        Module target = ModuleLayer.boot()
                .findModule("demo.target")
                .orElseThrow();

        Module helper = OpenAgent.class.getModule();
        String packageName = "demo.target.internal";

        Class<?> secret = Class.forName(
                target, "demo.target.internal.SecretBox");
        if (secret == null) {
            throw new ClassNotFoundException(
                    "demo.target.internal.SecretBox");
        }

        Field marker = secret.getDeclaredField("marker");

        System.out.println("TARGET_NAMED=" + target.isNamed());
        System.out.println("HELPER_NAMED=" + helper.isNamed());
        System.out.println(
                "BEFORE_OPEN=" + target.isOpen(packageName, helper));
        System.out.println(
                "BEFORE_ACCESS=" + marker.trySetAccessible());

        if (!inst.isModifiableModule(target)) {
            System.out.println("SKIPPED_UNMODIFIABLE_MODULE");
            return;
        }

        inst.redefineModule(
                target,
                Set.of(),
                Map.of(),
                Map.of(packageName, Set.of(helper)),
                Set.of(),
                Map.of()
        );

        System.out.println(
                "AFTER_OPEN=" + target.isOpen(packageName, helper));

        boolean enabled = marker.trySetAccessible();
        System.out.println("AFTER_ACCESS=" + enabled);
        if (enabled) {
            System.out.println("MARKER=" + marker.getInt(null));
        }

        String otherPackage = "demo.target.other";
        Class<?> other = Class.forName(
                target, "demo.target.other.OtherSecret");
        if (other == null) {
            throw new ClassNotFoundException(
                    "demo.target.other.OtherSecret");
        }
        Field hidden = other.getDeclaredField("hidden");

        System.out.println(
                "OTHER_OPEN=" + target.isOpen(otherPackage, helper));
        System.out.println(
                "OTHER_ACCESS=" + hidden.trySetAccessible());
    }
}
```

**Giải thích các điểm quan trọng:**

1. `ModuleLayer.boot().findModule("demo.target")` lấy đúng module **đã được giải quyết trong boot layer** của lần chạy dùng `-m demo.target/...`. Đừng dùng tên module từ config mà không xác minh target có hiện diện.
2. `OpenAgent.class.getModule()` lấy **đúng Module object của caller** đang gọi reflection; với agent JAR thông thường nó là system unnamed module (vì vậy `HELPER_NAMED=false`).
3. `Class.forName(Module,String)` được dùng để tìm class trong **module cụ thể**, không tự yêu cầu package phải export để lấy đối tượng `Class<?>`; phương thức này có thể trả `null` nếu class không tồn tại trong module.
4. `getDeclaredField("marker")` có thể tìm metadata cho private field nhưng **không tự cấp quyền truy cập giá trị**.
5. Trước `redefineModule`, `marker.trySetAccessible()` trả `false` khi package không open cho module của agent.
6. `Map.of(packageName,Set.of(helper))` chỉ open **một package** đến **một Module object**; không export/open các package còn lại.
7. Sau lời gọi thành công, `target.isOpen(packageName,helper)` và `marker.trySetAccessible()` đều là `true`.
8. `marker.getInt(null)` lấy giá trị của static field; trong demo là `7`, **không phải hướng dẫn đọc bí mật trong production**.
9. `demo.target.other` vẫn không open tới helper nên `hidden.trySetAccessible()` còn trả `false`.

Không có bước nào dùng `--add-opens` hoặc `ALL-UNNAMED` ở runtime demo. Đó là khác biệt chủ ý giữa **quyền hẹp qua Instrumentation API** và quyền CLI thường cấp cho mọi unnamed module.

### 5.7. File manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.OpenAgent

```

Giữ một dòng trống ở cuối manifest. Không cần `Can-Retransform-Classes: true` hay `Can-Redefine-Classes: true` vì agent **không** retransform/redefine class bytes. `Instrumentation.redefineModule` là API độc lập.

### 5.8. Biên dịch và chạy trên JDK 17+

Từ thư mục `module-open-lab`, Bash/macOS/Linux:

```shell
mkdir -p mods/demo.target agent-classes

javac -d mods/demo.target \
  src/demo.target/module-info.java \
  src/demo.target/demo/target/Main.java \
  src/demo.target/demo/target/internal/SecretBox.java \
  src/demo.target/demo/target/other/OtherSecret.java

javac -d agent-classes agent-src/demo/agent/OpenAgent.java

jar cfm narrow-agent.jar agent.mf -C agent-classes .

java -javaagent:narrow-agent.jar \
  --module-path mods \
  -m demo.target/demo.target.Main
```

Với Windows PowerShell (không dùng `\` làm ký tự nối dòng):

```powershell
New-Item -ItemType Directory -Force mods/demo.target, agent-classes | Out-Null
javac -d mods/demo.target src/demo.target/module-info.java src/demo.target/demo/target/Main.java src/demo.target/demo/target/internal/SecretBox.java src/demo.target/demo/target/other/OtherSecret.java
javac -d agent-classes agent-src/demo/agent/OpenAgent.java
jar cfm narrow-agent.jar agent.mf -C agent-classes .
java -javaagent:narrow-agent.jar --module-path mods -m demo.target/demo.target.Main
```

**Điều kiện:** Ví dụ được thiết kế cho JDK 17+ với API JPMS và Instrumentation chuẩn. Cần dùng JDK có `javac`, `jar`, `java` trong `PATH`; không có Java agent khác/`--add-opens` khác đang thay đổi quyền của hai package. Nếu package đã open sẵn bởi flags hoặc code khác, phần `BEFORE_*` sẽ khác dự kiến.

### 5.9. Stdout dự kiến với HotSpot JDK 17/21 thông thường

```text
TARGET_NAMED=true
HELPER_NAMED=false
BEFORE_OPEN=false
BEFORE_ACCESS=false
AFTER_OPEN=true
AFTER_ACCESS=true
MARKER=7
OTHER_OPEN=false
OTHER_ACCESS=false
APP_STARTED
```

**Cách đọc output:**

- `TARGET_NAMED=true`: `demo.target` được giải quyết dưới dạng named module.
- `HELPER_NAMED=false`: agent class trong unnamed module của system class loader.
- `BEFORE_OPEN=false` và `BEFORE_ACCESS=false`: trước cấp quyền, private reflection vào package kín bị chặn.
- `AFTER_OPEN=true` và `AFTER_ACCESS=true`: API chỉ bổ sung qualified open đã yêu cầu.
- `MARKER=7`: phép đọc field được phê duyệt trong demo có hiệu lực.
- `OTHER_OPEN=false` và `OTHER_ACCESS=false`: package không được chọn **vẫn kín**.
- `APP_STARTED`: ứng dụng chính tiếp tục chạy sau `premain`.

Nếu `isModifiableModule(target)` trả false, demo in `SKIPPED_UNMODIFIABLE_MODULE` và không có các dòng sau khi mở; cần báo đây là nhánh môi trường không hỗ trợ. Nếu `redefineModule` ném exception, application main có thể không chạy vì startup agent `premain` thất bại; không được tự coi phép mở thành công.

**Bài học về phạm vi:** Agent có thể đọc private `marker` vì package được open cho **đúng module agent**. Nhưng package `demo.target.other` không được mở; không có bằng chứng agent có thể tự do đọc mọi private field trong module.

### 5.10. Kiểm tra đối chứng: flag rộng thay đổi đầu ra

Nếu khởi chạy JVM với:

```shell
java --add-opens=demo.target/demo.target.internal=ALL-UNNAMED \
  -javaagent:narrow-agent.jar \
  --module-path mods \
  -m demo.target/demo.target.Main
```

thì **`BEFORE_OPEN` có thể đã là `true`**, bởi vì bạn đã cấp quyền cho **mọi unnamed module** ngay ở thời điểm khởi động. Vì vậy không dùng flag này trong lần chạy đối chứng chính. Bản chạy có flag chỉ minh họa rằng CLI option cấp quyền **rộng hơn** `Set.of(helper)` trong agent.

Đừng dùng `--add-opens=...=ALL-UNNAMED` để làm “test xem helper có chạy không” rồi bỏ quên trong cấu hình production; nó có thể cho các unnamed modules khác (ở class loaders khác) cùng quyền.

## 6. MethodHandles.privateLookupIn: cần reads + opens

Một số thư viện instrumentation dùng `MethodHandles.Lookup` thay vì reflection API. Khi tạo private lookup từ một module khác, `MethodHandles.privateLookupIn(targetClass, callerLookup)` có những điều kiện:

1. Caller lookup phải có các quyền lookup phù hợp, gồm `MODULE` và `PRIVATE`.
2. Nếu module caller **khác** module của target class, caller module phải **read** target module.
3. Target module phải **open package của target class** đến module của caller lookup.

Với agent JAR trong **unnamed module**, unnamed modules đọc mọi module theo ngữ nghĩa JPMS, nên trong demo phía trên thường chỉ thiếu **qualified open**. Nhưng nếu helper được đóng thành một **named module riêng** trong một custom layer, cần kiểm tra `helperModule.canRead(targetModule)` thật sự; đừng lấy ví dụ unnamed rồi suy mọi named module tự đọc nhau.

Ví dụ kiểm tra trước khi gọi private lookup (snippet có các biến/class giả định, **không độc lập**):

```java
Module targetModule = secretClass.getModule();
Module helperModule = TrustedHelper.class.getModule();
String pkg = secretClass.getPackageName();

if (!helperModule.canRead(targetModule)) {
    // Cần giải quyết quan hệ đọc từ helper -> target;
    // có thể qua module-info.java hoặc một lần redefineModule(helper).
}

if (!targetModule.isOpen(pkg, helperModule)) {
    // Cần qualified open từ target -> helper.
}

java.lang.invoke.MethodHandles.Lookup lookup =
    java.lang.invoke.MethodHandles.privateLookupIn(
        secretClass, java.lang.invoke.MethodHandles.lookup());
```

Lưu ý: `MethodHandles.lookup()` trong snippet phải thực sự là lookup của code/module có thẩm quyền; sao chép sang một wrapper method ở module khác có thể tạo caller lookup với identity/quyền khác mong đợi. Đừng dùng `lookup.in(...)` hoặc chuyển lookup qua nhiều module rồi tự giả định nó vẫn giữ quyền `MODULE`.

### 6.1. Thiếu read edge không được sửa bằng extraOpens theo hướng ngược

Nếu `H` là named helper module và `M` chứa class cần private lookup:

```text
Cần hai quan hệ khác nhau:

H --reads--> M
M --opens package p to--> H
```

**Hai thao tác API, khi cần:**

```java
// 1. Chỉ nếu H chưa đọc M:
inst.redefineModule(
    helperModule,
    Set.of(targetModule),
    Map.of(), Map.of(),
    Set.of(), Map.of()
);

// 2. Chỉ nếu package p của M chưa open tới H:
inst.redefineModule(
    targetModule,
    Set.of(), Map.of(),
    Map.of("com.shop.internal", Set.of(helperModule)),
    Set.of(), Map.of()
);
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; `inst`, `helperModule` và `targetModule` phải là các đối tượng đúng của runtime. Nếu helper module không modifiable hoặc thiếu policy approval, đừng tự động mở rộng quyền rồi mong sẽ an toàn.

## 7. Khi nào dùng exports thay vì opens?

**Câu hỏi quyết định:** Bạn có thực sự cần private reflection không?

| Nhu cầu | Lựa chọn phù hợp | Không nên làm |
|---|---|---|
| Helper gọi public method của public type được thiết kế làm API | `requires` + `exports` thích hợp (qualified nếu chỉ một consumer) | Open cả package chỉ để gọi public API |
| Helper dùng `Field.trySetAccessible` vào private field | Qualified `opens` target package tới caller | Chỉ `exports` rồi hy vọng private access được phép |
| Helper dùng `privateLookupIn` từ module khác | Caller reads target + target opens package tới caller | Bỏ qua read edge hoặc open mọi package |
| Bytecode ứng dụng gọi một helper public static trong named module | Source module reads helper module; helper package exports đến source | Nhầm chiều thành source exports package của mình |
| Bytecode ứng dụng gọi bootstrap/system unnamed helper | Kiểm tra quy tắc instrumentation, loader visibility, module reads thực tế | Tự thêm mọi `extraReads` không cần thiết |
| Gọi private field chỉ để tính một metric không thiết yếu | Thiết kế lại qua public API/adapter hoặc SKIP có báo cáo | Mở quyền nhạy cảm chỉ để có thêm dữ liệu |
| Lớp nằm trong unnamed module | Xét loader/access bình thường; `redefineModule(unnamed)` no-op | Tưởng module mutation sẽ tạo boundary mới |

### 7.1. Một qualified export ví dụ

Module `com.shop.core` có public type trong package `com.shop.spi`, helper `io.acme.agent.helper` cần gọi API công khai:

```java
inst.redefineModule(
    targetModule,
    Set.of(),
    Map.of("com.shop.spi", Set.of(helperModule)),
    Map.of(),
    Set.of(),
    Map.of()
);
```

Điều này **export** package, không **open** nó. Caller vẫn phải có read edge cần thiết và classloader/linkage phù hợp. `isExported("com.shop.spi",helperModule)` là phép kiểm tra gần hơn với mục tiêu; `trySetAccessible` vào private field không được giải quyết chỉ bằng qualified export.

### 7.2. Package open rộng hơn mức “chỉ class X”

Một khi `p` được open tới `H`, code trong `H` có thể deep-reflect vào **nhiều class và members** trong `p`. API không cho mở **duy nhất một field** bằng `extraOpens`.

Nếu `com.shop.internal` chứa cả `PricingState` cần đo và `TokenVault` không nên truy cập, việc open package đó vẫn làm cả package được open. Cách tốt hơn có thể là:

- Cung cấp một public read-only diagnostic API trong package riêng.
- Di chuyển các type cần deep reflection tới package riêng được thiết kế cho instrumentation, nếu kiểm soát được source.
- Truyền dữ liệu thống kê tổng hợp/đã redacted qua bridge do ứng dụng tự cung cấp.
- Không thu thập thông tin không thực sự cần.

**Least privilege trong JPMS phải đi cùng thiết kế package**, không chỉ một dòng `Map.of(...)`.

## 8. Module access không giải quyết class-loader visibility

Trong Java agent, có hai rào cản dễ nhầm:

```text
A. Class-loader visibility
   Target class có resolve được ProbeBridge không?

B. JPMS access/readability
   Module của target có đọc helper module không?
   Helper package có exported/open phù hợp không?
```

`redefineModule` chỉ xử lý **B**, không sửa được một class file bị thiếu trong JAR, không thêm class vào tất cả class loaders và không chữa tự động `NoClassDefFoundError` do loader không thấy helper.

### 8.1. Trường hợp đặc biệt mà JVM hỗ trợ Java agent

Đặc tả `java.lang.instrument` nói rằng để hỗ trợ agents đưa classes vào đường tìm kiếm của **bootstrap class loader** hoặc class loader nạp main agent class, JVM sắp xếp cho **module của các class được transform** đọc **unnamed module của hai loaders này**.

Do vậy, khi chèn một lời gọi tới bootstrap/system unnamed helper, **có thể đã có read edge cần thiết** theo quy tắc Instrumentation. Không nên luôn gọi thêm `redefineModule` cho quan hệ đó mà không kiểm tra `targetModule.canRead(helperModule)`.

Nhưng quy tắc trên **không** tự:

- đảm bảo helper class thực sự resolve được từ defining loader;
- export/open các private packages của ứng dụng cho agent;
- thêm read edge tới một **named helper module bất kỳ** trong custom ModuleLayer;
- cho phép deep reflection vào mọi package của `java.base`.

Khi instrument class trong custom loader/module layer, cần test đúng module, class loader và nguồn helper thay vì áp giả định từ demo classpath đơn giản.

### 8.2. Lấy đúng Module object

`Class<?>.getModule()` là nguồn đáng tin cho module của **class thực sự được định nghĩa**. Ví dụ:

```java
Module targetModule = targetClass.getModule();
Module helperModule = helperClass.getModule();
ClassLoader targetLoader = targetClass.getClassLoader();
ClassLoader helperLoader = helperClass.getClassLoader();
```

Đừng chỉ dùng string `"com.shop.core"` nếu ứng dụng có nhiều module layers hoặc class loaders khác nhau. Tên module là thông tin hữu ích nhưng không chứng minh đó là **đúng Module object** đã chứa class thực tế. `ModuleLayer.boot().findModule(...)` trong demo dùng được vì target do launcher nạp trong boot layer; đó không phải cách tìm module bất kỳ trên mọi application server/plugin loader.

### 8.3. Không dùng isModifiableModule để đo “agent có thấy class không”

Một module có thể modifiable nhưng helper vẫn không được load. Ngược lại helper có thể load nhưng module không cho mở thêm. Cần báo các reason khác nhau:

```text
HELPER_NOT_VISIBLE
MODULE_NOT_READABLE
PACKAGE_NOT_EXPORTED
PACKAGE_NOT_OPEN
MODULE_UNMODIFIABLE
PRIVATE_LOOKUP_DENIED
REFLECTION_DENIED
```

Không đánh đồng tất cả thành “module access failed” rồi mở hàng loạt packages. Bước chẩn đoán đầu tiên là xác định **đúng class, đúng module, đúng package, đúng loader và thao tác đang định thực hiện**.

## 9. CLI flags: tương đương có điều kiện, nhưng thường rộng hơn

Khi quản lý JVM lúc khởi động, các tùy chọn JVM có thể phù hợp hơn thay đổi module lúc chạy:

```shell
# Bổ sung qualified opens cho một named module đích (demo CLI):
java --add-opens=demo.target/demo.target.internal=ALL-UNNAMED \
  --module-path mods \
  -m demo.target/demo.target.Main

# Ví dụ khác: qualified export public APIs cho một named consumer:
java --add-exports=com.shop.core/com.shop.spi=io.acme.agent.helper ...

# Ví dụ khác: bổ sung readability:
java --add-reads=com.shop.core=io.acme.agent.helper ...
```

Các lệnh có `...` là **mẫu cú pháp**, không phải shell commands chạy độc lập. Module names/paths cần được thay bằng modules thật sự đã resolve. Tùy chọn `--add-opens` dùng format `<source-module>/<package>=<target-module>(,<target-module>...)`.

### 9.1. ALL-UNNAMED là phạm vi rộng

`ALL-UNNAMED` trong CLI hướng tới **tất cả unnamed modules**, không phải chỉ system unnamed module của agent. Vì thế khi agent có `Module helper = OpenAgent.class.getModule()`, lời gọi:

```java
Map.of("demo.target.internal", Set.of(helper))
```

là một lựa chọn **hẹp hơn**, với module object cụ thể. Nếu nhiều agents/plugins đều chạy ở **cùng một unnamed module**, chúng sẽ cùng hưởng quyền đã cấp cho module đó. Java không thể dùng qualified open để chỉ một class trong module nhận quyền.

### 9.2. Một package không đồng nghĩa một class

`--add-opens=java.base/java.lang=ALL-UNNAMED` cho phép deep reflection rộng vào package `java.lang` cho mọi unnamed module. Đó có thể là một thay đổi có ảnh hưởng lớn, không nên được đưa vào tài liệu triển khai chỉ để sửa một warning `InaccessibleObjectException` chưa được phân tích. Hãy xác định field/method thật, sở hữu package và module caller trước.

### 9.3. Không copy flags compiler sang runtime tùy tiện

`--add-exports` có thể được dùng trong một số giai đoạn build/test để biên dịch code truy cập API không export, nhưng runtime vẫn cần kiểm tra đúng module access. `--add-opens` phục vụ deep reflection **khi chạy**, không phải cách tạo hợp đồng public API khi compile. Test chỉ chạy trong IDE với flags rộng có thể che giấu rủi ro triển khai thật.

## 10. Chính sách quyền tối thiểu cho một Java agent

Một thiết kế tốt phải có **manifest quyền riêng của agent** (không nhầm với JAR manifest `Premain-Class`) thể hiện mục tiêu và lý do được cấp quyền:

```yaml
features:
  - id: pricing-diagnostic
    enabled: true
    targetModule: com.shop.core
    targetPackage: com.shop.internal
    recipientModule: io.acme.agent.helper
    operation: OPEN_FOR_PRIVATE_REFLECTION
    justification: "Read approved diagnostic counter"
    expectedMembers:
      - "PricingState#sampleCount"
    fallback: SKIP_WITH_REPORT
```

Đây là **schema chính sách minh họa**, không phải cấu hình được `Instrumentation` tự đọc. `expectedMembers` chỉ giúp **audit và giới hạn logic của agent**; JPMS vẫn mở cả package cho module recipient. Agent phải tự enforce rằng code chỉ dùng đúng member được phê duyệt.

### 10.1. Quy trình quyết định quyền

1. **Xác định phép đo:** có thực sự cần private reflection không? Có thể dùng public API/adapter không?
2. **Định danh target chính xác:** class, defining loader, `targetClass.getModule()`, package.
3. **Định danh caller chính xác:** `helperClass.getModule()`, không suy từ tên JAR hay package.
4. **Kiểm tra trạng thái:** `helper.canRead(target)` khi cần; `target.isExported(p,helper)` hoặc `target.isOpen(p,helper)` tùy thao tác.
5. **Chọn cấp quyền nhỏ nhất:** chỉ package cần thiết và Module object đúng; không thêm extras không liên quan.
6. **Đảm bảo nguồn quyền được phê duyệt:** quyền deep reflection là mở rộng khả năng của code đã được tin cậy, không được tự động leo quyền khi thiếu.
7. **Precheck modifiability và package membership:** `inst.isModifiableModule(target)`, `target.getPackages().contains(p)`.
8. **Áp thay đổi nếu thật sự cần:** một `redefineModule` đúng tham số; không gọi lặp vô nghĩa.
9. **Kiểm tra hậu điều kiện:** qualified `isOpen`/`isExported`/`canRead` và thao tác reflection/helper thật sự cần.
10. **Báo cáo và kiểm soát vòng đời:** module/package/recipient, reason, thời điểm, JVM/agent version, kết quả. Quyền đã mở có thể tồn tại tới hết JVM.

### 10.2. Trường hợp được phép bỏ qua thay vì mở rộng quyền

- Metric bổ sung có thể lấy từ method public, không cần private state.
- Module/package nhạy cảm và không có phê duyệt security review.
- Không xác định được đúng caller `Module` trong hệ thống nhiều class loaders.
- Target module không modifiable.
- Không có package cần tìm trong target module.
- Code cần đọc cả object graph bí mật trong khi mục tiêu chỉ là latency.
- Mở package sẽ cho các components khác của cùng unnamed module nhiều quyền hơn mức chấp nhận.
- Instrumentation đang hoạt động đủ với coarse-grained metrics.

Trong các trường hợp này, trạng thái **SKIPPED** kèm lý do minh bạch tốt hơn cách mở rộng `--add-opens` để tránh lỗi.

### 10.3. Audit nhưng không log private values

Ví dụ bản ghi:

```json
{
  "feature": "pricing-diagnostic",
  "operation": "QUALIFIED_OPEN",
  "targetModule": "com.shop.core",
  "package": "com.shop.internal",
  "recipientModule": "io.acme.agent.helper",
  "status": "APPLIED",
  "alreadyOpen": false,
  "postconditionVerified": true,
  "privateValuesLogged": false
}
```

Đây là log minh họa. Có thể thêm target layer/classloader identity trong hệ thống thật nhưng tránh ghi thông tin nhạy cảm, tên khách hàng, credential, private field values hoặc đường dẫn deployment cần bảo vệ.

**Một chi tiết vận hành:** `redefineModule` là thread-safe theo Javadoc và có thể được nhiều agents gọi gần nhau. Tuy nhiên **không vì vậy mà việc cấp quyền tự rollback hoặc có policy arbitration**. Nhiều agents có thể cộng dồn reads/exports/opens; bộ điều phối cần audit tổng quyền hiện hành và tránh giả định “agent của tôi không mở nên chắc chắn package vẫn kín”.

## 11. Các lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Phân tích/giải pháp |
|---|---|---|
| `InaccessibleObjectException` khi `setAccessible(true)` | Package không open tới **module caller thật** | Kiểm `target.isOpen(p,callerModule)`, tránh `ALL-UNNAMED` bừa bãi |
| `trySetAccessible()` trả `false` | Chưa đủ openness hoặc điều kiện truy cập | Dùng đúng qualified open; xác minh lại bằng phép truy cập mong muốn |
| `privateLookupIn` ném `IllegalAccessException` | Thiếu read edge hoặc target package chưa open, caller lookup thiếu quyền | Kiểm cả `caller.canRead(target)` và `target.isOpen(p,caller)` |
| `IllegalAccessError` khi bytecode gọi public helper | Thiếu readability/exports hoặc runtime linkage không hợp lệ | Kiểm hướng M→H, helper package exports tới M nếu named |
| `NoClassDefFoundError` cho helper | Loader không resolve được helper class | Kiểm bootstrap/system/custom loader path; mở package không sửa classpath |
| `IllegalArgumentException` ở `redefineModule` | Package không nằm trong target, hoặc map value là tập rỗng | Dùng `getPackages()`, dotted package name và `Set.of(helper)` |
| `UnmodifiableModuleException` | Module không thể sửa | `isModifiableModule` precheck, báo SKIPPED |
| Đã gọi API nhưng quyền vẫn không thay đổi | Có thể bạn đang redefine **unnamed module** (no-op) hoặc nhầm Module object | Kiểm `module.isNamed()`, target/caller thực |
| Module vẫn open rộng dù đã đổi config agent | `redefineModule` chỉ bổ sung, không thu hồi | Kiểm flags/agents khác, cân nhắc JVM restart |
| Một package khác cũng truy cập được | Có quyền open trước đó từ CLI/module-info/agent khác | Kiểm cả trạng thái **before** và **after**, không chỉ báo “tôi không mở” |
| Test trong IDE pass, production fail | IDE thêm `--add-opens`, module layer/loader khác | Test đúng flags và classloader thực |
| Agent dùng `ALL-UNNAMED` nhưng named helper vẫn bị chặn | Target grant áp vào unnamed modules, không phải named helper | Qualified open tới chính helper `Module` hoặc module name phù hợp |
| `isExported==true` nhưng private reflection thất bại | Exports không đồng nghĩa opens | Kiểm `isOpen` và đổi thiết kế theo loại truy cập |
| Field trong class cùng tên vẫn không đọc được | Có nhiều định nghĩa class do loaders khác nhau | Lấy target qua `Class<?>` thực, không chỉ binary name |
| Helper được load nhưng instrumentation vẫn không hoạt động | Module mở nhưng transformer không chèn được probe, hoặc chưa xác minh effect | Tách module permissions khỏi ClassFileTransformer QA |

### 11.1. Đừng giải quyết lỗi bằng vòng lặp mở rộng quyền

Anti-pattern:

```text
InaccessibleObjectException
  -> mở tất cả packages của module
  -> vẫn lỗi ClassNotFoundException
  -> mở tiếp java.base
  -> lại lỗi NoClassDefFoundError
```

`ClassNotFoundException` và `NoClassDefFoundError` thường liên quan **class loading/linkage**, không thể tự khắc phục bằng opens vô hạn. `InaccessibleObjectException` là tín hiệu tiếp cận deep reflection; phải xác định **package cụ thể** và **caller module**. `IllegalAccessError` có thể phát sinh từ exports/readability hoặc package-private JVM identity, không nhất thiết chỉ thiếu opens.

## 12. Kiểm thử: chứng minh cả quyền được cấp lẫn quyền bị từ chối

### 12.1. Positive test

- `target.isOpen(approvedPackage,helper)==true` sau thao tác.
- `Field.trySetAccessible()==true` cho field đã được phê duyệt trong package đó.
- `ClassLoader` resolve đúng class; nếu dùng `MethodHandles.privateLookupIn`, thực hiện một lookup phù hợp và kiểm chứng.
- App main tiếp tục chạy nếu tính năng optional đã được chấp nhận.

### 12.2. Negative test quan trọng không kém

- Package thứ hai trong cùng module **vẫn** `isOpen(otherPackage,helper)==false`.
- `trySetAccessible()` của private field ở package thứ hai vẫn false.
- Module khác không nhận qualified open ngoài dự định (nếu có cách test với một second module).
- Khi có `--add-opens=...=ALL-UNNAMED`, test nhận diện quyền đã rộng từ **trước** khi agent gọi `redefineModule`.
- Nếu package không tồn tại trong module, agent **báo lỗi** thay vì thử mở tên guessed.
- Nếu `isModifiableModule=false`, agent không gọi mutation.

### 12.3. Hiệu năng, rollback, triển khai

- Không gọi `redefineModule` trên mỗi method invocation; thay đổi quyền là thao tác cấu hình trong agent lifecycle.
- Không gọi reflection vào private values chỉ để “test” trong production. Dùng metadata và điều kiện hậu kiểm phù hợp rồi giữ dữ liệu trong policy cho phép.
- Kiểm soát scope trong nhiều module layers/loaders và các lần attach agent khác nhau.
- Không coi shutdown/restart helper là cách tự đóng lại package. Quyền module đã được mở không thu hồi qua `redefineModule`.
- Không đưa startup flags rộng vào production vì unit test “cần chạy” nếu chưa được duyệt.
- Test trên JDK/VM vendor và module configuration thực tế, không chỉ trên classpath app thử nghiệm.

## 13. Câu hỏi tự kiểm tra

1. **Helper H muốn deep-reflect vào private field thuộc package p của module M. Module nào phải được mở rộng?** M, qua `extraOpens p → {H}`.
2. **Có cần `extraExports p → {H}` nếu chỉ đang làm `Field.trySetAccessible`?** Không; qualified open phù hợp hơn, nếu API và policy cho phép.
3. **`extraOpens` map key viết `com/foo/internal` hay `com.foo.internal`?** Dạng dotted `com.foo.internal`.
4. **`extraOpens` có cho chỉ mở một class không?** Không, đơn vị là package.
5. **`isModifiableModule(unnamedModule)==true` có nghĩa gọi `redefineModule` sẽ mở package mới?** Không, API là no-op trên unnamed module.
6. **Vì sao `target.isOpen(p)` có thể false trong khi `target.isOpen(p,helper)` là true?** Vì package chỉ được **qualified open** tới helper.
7. **`privateLookupIn` qua module boundary cần gì?** Lookup có quyền phù hợp, helper module đọc target module, và target package open tới helper.
8. **Nếu named module M chứa target đã được transform gọi unnamed bootstrap helper, cần luôn add read edge thủ công?** Không. Java Instrumentation có quy tắc JVM hỗ trợ đọc unnamed modules của bootstrap/system cho transformed classes; vẫn phải kiểm tra loader/actual module.
9. **Nếu helper class không tìm thấy, opens package của app có đủ không?** Không; cần giải quyết class-loader visibility.
10. **Vì sao `ALL-UNNAMED` thường rộng hơn `Set.of(OpenAgent.class.getModule())`?** Vì có thể bao gồm unnamed modules của nhiều class loaders.
11. **Mở `com.shop.internal` có cho helper quyền riêng với chỉ `PricingState#count` không?** Không. Code trong helper module có thể deep-reflect vào nhiều members trong package.
12. **Có thể gọi `redefineModule` lần hai để thu hồi một open trước đó không?** Không. API chỉ mở rộng.
13. **Muốn module M gọi public helper trong named module H, quan hệ quan trọng là gì?** M đọc H; package public helper ở H export tới M; class-loader visibility vẫn cần.
14. **Mỗi lần agent gặp `InaccessibleObjectException` nên mở toàn `java.base` không?** Không. Tìm đúng target package, caller module và dữ liệu thực sự cần.
15. **Vì sao cần test một package không được mở?** Để chứng minh quyền được cấp không lan sang các package khác ngoài ý định.
16. **`isModifiableClass` có kiểm tra tính modifiable của module không?** Không, đó là API khác với `isModifiableModule`.
17. **Mở package có sửa `ClassNotFoundException` do loader không thấy helper không?** Không.
18. **Nếu code cùng binary name nằm ở hai custom loaders, nên lấy module của cái nào?** Lấy qua `Class<?>` thật của target/caller được dùng trong instrumentation.
19. **Nếu JVM còn mở package sau khi agent rời đi, có phải bug không?** Không nhất thiết; quyền đã thêm bằng `redefineModule` không tự bị thu hồi.
20. **Một tính năng đo tùy chọn yêu cầu mở package chứa secrets, không có phê duyệt. Chọn gì?** Dùng API/metric khác hoặc **SKIPPED có lý do**, không tự leo quyền.

## 14. Tài liệu tham khảo chính thức

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineModule`, `isModifiableModule`, tham số và ngoại lệ.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hành vi bổ sung reads/exports/opens/uses/provides, no-op unnamed module, thread-safety.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `getPackages` và qualified access.
- [Java SE 21 — `MethodHandles`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `privateLookupIn` và điều kiện module readability/opens.
- [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible` và `InaccessibleObjectException`.
- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR trong system unnamed module và JVM hỗ trợ read edges cho các class được transform.
- [Java SE 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--add-reads`, `--add-exports`, `--add-opens`, `--module-path` và `-m`.
- [JLS SE 21 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): định nghĩa module reads/exports/opens, qualified clauses.
- [JPMS State of the Module System](https://openjdk.org/projects/jigsaw/spec/sotms/): bối cảnh readability và strong encapsulation.

**Ghi nhớ:** đừng “mở module” như một thao tác tổng quát. Hãy tìm **module sở hữu package**, **module thực sự gọi helper/reflection** và **loại truy cập cần thiết**. Dùng qualified `opens` khi cần deep reflection, `exports` cho public API và `reads` cho readability; chỉ bổ sung quan hệ còn thiếu bằng `Instrumentation.redefineModule`, kiểm tra hậu điều kiện và **không coi quyền đã cấp là có thể thu hồi tự động**.