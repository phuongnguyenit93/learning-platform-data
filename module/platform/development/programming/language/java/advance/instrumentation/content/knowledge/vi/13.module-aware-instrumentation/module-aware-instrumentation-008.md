# Các quan hệ bổ sung không phải thao tác thu hồi quyền truy cập

## 1. Mục tiêu: hiểu đúng quyền của Instrumentation.redefineModule

Khi xây dựng Java agent cho ứng dụng dùng **Java Platform Module System (JPMS)**, bạn có thể gặp lỗi vì code được instrument cần đọc module khác, truy cập một package chưa export, thực hiện deep reflection trên private member hoặc sử dụng dịch vụ qua `ServiceLoader`. Từ Java 9, `java.lang.instrument.Instrumentation` có phương thức `redefineModule(...)` giúp agent **bổ sung** các quan hệ module tại runtime.

Điểm quan trọng nhất của bài: **`redefineModule` không có chức năng thu hồi quyền**. Tên phương thức chứa chữ “redefine” rất dễ khiến người học nghĩ có thể truyền một module graph mới để ghi đè module graph cũ, ví dụ cấp `opens` trong một thời gian rồi gọi với các tập/map rỗng để xóa lại. Đây là cách hiểu **sai**.

Theo Java SE 17, phương thức chỉ **mở rộng** các quan hệ đọc module, package export/open và quan hệ sử dụng/cung cấp service. Nó **không thể làm giảm** các quan hệ đã tồn tại. Đặc biệt, truyền một tập hoặc map rỗng chỉ có nghĩa **không thêm quan hệ mới trong lần gọi này**, chứ **không xóa quan hệ cũ**.

Sau bài, bạn có thể:

1. Phân biệt năm tham số `extraReads`, `extraExports`, `extraOpens`, `extraUses`, `extraProvides`.
2. Phân biệt **read edge**, **export** và **open** trong kiểm soát truy cập JPMS.
3. Dự đoán đúng kết quả của việc gọi `redefineModule` lần thứ hai với mọi tập/map rỗng.
4. Hiểu rằng `isModifiableModule` và việc module có tên/không có tên là hai khía cạnh riêng.
5. Chạy được **Java 17+** với named module, startup agent, compile/run commands và stdout rõ ràng.
6. Phân tích tác động của quan hệ bổ sung đối với bảo mật, least privilege, plugin, tracing và vòng đời agent.
7. Phân biệt “không thể thu hồi bằng API này” với các kiểm soát an ninh hoặc cơ chế isolation khác.

## 2. Định nghĩa module graph và tính chất chỉ-bổ-sung

JPMS biểu diễn các quan hệ giữa module bằng một đồ thị hướng và metadata của từng module. Để class thuộc một module truy cập class trong module khác, thường cần **quan hệ reads**, đồng thời package chứa class đích phải được **export** hoặc **open** phù hợp với loại truy cập.

Hãy hình dung:

~~~text
Named module: demo.vault                       Unnamed module: ứng dụng/agent
+-----------------------------+                +--------------------------+
| vault.api                    |                | demo.Main / helper        |
| vault.internal               |                |                          |
|                             |                |                          |
| Module graph ban đầu:       |                |                          |
|   không export vault.api    |                |                          |
|   không open vault.internal |                |                          |
+-----------------------------+                +--------------------------+
            |
            | Instrumentation.redefineModule(...)
            v
+-----------------------------+
| Module graph sau mở rộng:   |
|   exports vault.api  -------> app module
|   opens vault.internal -----> app module
|   reads java.sql -----------> java.sql module
|   uses java.sql.Driver
+-----------------------------+
            |
            | redefineModule(vault, empty, empty, empty, empty, empty)
            v
+-----------------------------+
| Quan hệ trước đó VẪN CÒN:   |
|   export / open / reads /    |
|   uses vẫn tồn tại          |
+-----------------------------+
~~~

Đây là **sơ đồ quan hệ**, không phải cấu trúc code đầy đủ. Cú pháp thực của `redefineModule` sẽ được giải thích ở mục 3 và thử nghiệm ở mục 6.

### 2.1. Vì sao “redefine” không phải “replace all”?

Trong `redefineClasses`, người gọi cung cấp bytes thay thế cho class đang tồn tại. Nhưng **`redefineModule` có hợp đồng khác**: nó nhận các tập/map chứa quan hệ **bổ sung**, không phải một bản chụp toàn bộ graph mới cần áp đặt.

Cách tư duy đúng:

~~~text
reads_after    = reads_before    U extraReads
exports_after  = exports_before  U extraExports
opens_after    = opens_before    U extraOpens
uses_after     = uses_before     U extraUses
provides_after = provides_before U extraProvides
~~~

Ký hiệu `U` ở đây biểu diễn phép **hợp quan hệ** ở mức khái niệm, không phải code Java; riêng `exports`, `opens` và `provides` còn có cấu trúc map/target/provider và quy tắc hợp lệ riêng. Công thức nhằm làm rõ **định hướng chỉ tăng phạm vi quan hệ**, không cam kết mọi kiểu collection trong API được triển khai bằng Set union.

Đặc tả nói rõ không thể **giảm** tập module được read, tập package được export/open hoặc các service được use/provide. Các thuộc tính này có thể đã xuất hiện từ `module-info.java`, từ tùy chọn launcher như `--add-opens`, từ agent khác hoặc từ một lần `redefineModule` trước đó.

### 2.2. Khi nào nên dùng?

Agent cần truy cập helper trong một module chưa được read, cần reflection để quan sát field private hoặc cần tích hợp một service từ module khác. Đây là yêu cầu **tăng quyền có chủ đích** trong runtime. Nếu bài toán là **thu hồi quyền sau khi tắt agent**, `redefineModule` không phải API giải quyết.

## 3. Chữ ký API và ý nghĩa năm tham số

Trong Java 17, chữ ký đầy đủ là:

~~~java
void redefineModule(
        Module module,
        Set<Module> extraReads,
        Map<String, Set<Module>> extraExports,
        Map<String, Set<Module>> extraOpens,
        Set<Class<?>> extraUses,
        Map<Class<?>, List<Class<?>>> extraProvides);
~~~

Đây là **chữ ký tham khảo**; để dùng trong một chương trình Java thực, gọi phương thức từ instance `Instrumentation` và import `java.lang.Module`, `java.util.*`. Tất cả collection phải **không null**; các collection rỗng là hợp lệ khi không cần bổ sung loại quan hệ tương ứng.

| Tham số | Cái được bổ sung | Hướng quan hệ / ràng buộc |
|---|---|---|
| `module` | Module nguồn sẽ được cập nhật | Thường là **named module** cần instrument |
| `extraReads` | Các module mà `module` được phép read thêm | Từ `module` **đến** từng module trong Set |
| `extraExports` | Package public của `module` được export thêm tới những module đích | Key là **tên package có trong `module`**, value là Set module đích **không rỗng** |
| `extraOpens` | Package của `module` được open thêm tới những module đích | Key là **tên package có trong `module`**, value là Set module đích **không rỗng** |
| `extraUses` | Service types mà `module` được phép sử dụng | Set các `Class<?>` của service; agent phải đảm bảo service type có thể truy cập tại điểm dùng |
| `extraProvides` | Các provider mà `module` cung cấp thêm | Key là service type, value là **List provider classes không rỗng**, provider thuộc module nguồn và triển khai service |

**Không có tham số nào tên `removeReads`, `removeExports`, `removeOpens`, `removeUses` hoặc `removeProvides`.** Các tham số đều bắt đầu bằng `extra`. Gửi `Map.of()`/`Set.of()` không phải cú pháp “xoá cấu hình”.

Một lời gọi mẫu:

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(helperModule),
        Map.of("app.api", Set.of(consumerModule)),
        Map.of("app.internal", Set.of(agentModule)),
        Set.of(MyService.class),
        Map.of(MyService.class, List.of(MyProvider.class)));
~~~

Đoạn trên là **mẫu cấu trúc**, không phải demo độc lập; các biến module và service/provider phải được khai báo, các package phải thuộc đúng source module, `MyProvider` phải là provider hợp lệ trong source module. Không thêm bừa toàn bộ tham số nếu chỉ cần mở một package.

### 3.1. Tách capability của module và class

`Instrumentation` có:

~~~java
boolean isModifiableModule(Module module);
~~~

Kiểm tra này dùng cho **module redefinition**; **không phải** `isModifiableClass(Class<?>)`, `isRedefineClassesSupported()` hay `isRetransformClassesSupported()`. Bạn không cần khai báo `Can-Redefine-Classes: true` chỉ để gọi `redefineModule`.

Nếu `isModifiableModule(namedModule)` là false và bạn vẫn cố cập nhật, VM có thể ném `UnmodifiableModuleException`. Nếu tham số không hợp lệ, có thể có `IllegalArgumentException` hoặc `NullPointerException` tùy trường hợp.

### 3.2. Unnamed module: “modifiable” nhưng thao tác no-op

Đặc tả có một chi tiết dễ bất ngờ:

- `isModifiableModule(unnamedModule)` luôn trả **true**;
- `redefineModule(unnamedModule, ...)` là **no-op**.

Không được kết luận **“isModifiableModule true nghĩa là mọi thay đổi đều có hiệu lực”**. Unnamed module đã có những quy tắc đọc/export/open rộng riêng trong JPMS; API không cần và không thực hiện cập nhật đồ thị kiểu named module cho nó.

Trong ví dụ, source cần thay là **named module** `demo.vault`. Module của `Main` trên classpath là **unnamed module** đóng vai trò đích nhận quyền.

## 4. Reads, exports, opens không phải một quyền duy nhất

### 4.1. Reads: biết và liên kết đến module khác

`source.canRead(target)` hỏi source module có quan hệ reads đối với target module hay không. `extraReads = Set.of(target)` mở rộng graph để source read thêm target. Nhưng **read edge không tự export package của target**.

Nếu `moduleA` read `moduleB`, điều đó không có nghĩa `moduleB` phải cho `moduleA` deep reflection vào tất cả field private. Cần thêm quan hệ export/open phù hợp **do module chứa package đích cấp**.

### 4.2. Exports: truy cập các public types/members theo JPMS

`extraExports` làm package trong **source module** được export tới module đích cụ thể. Điều này tạo điều kiện cho truy cập thông thường vào **public types và public members**, nếu các điều kiện reads/accessibility khác đáp ứng.

Ví dụ `Map.of("vault.api", Set.of(client))` mở quyền export `vault.api` tới đúng module `client`. Đây là **qualified export**, không phải mở package cho mọi module. Nó **không tự mở toàn bộ private members cho deep reflection**.

### 4.3. Opens: deep reflection có thể được phép

`extraOpens` làm package trong source module được open cho module đích. Khi package được open, lời gọi reflection như `Field.setAccessible(true)` có thể được cho phép theo JPMS, còn phải tuân theo những kiểm soát khác của nền tảng và ngữ nghĩa reflection.

Ví dụ `Map.of("vault.internal", Set.of(client))` cho phép module `client` yêu cầu deep reflection vào package `vault.internal` của source. **Open package là mở phạm vi truy cập lớn hơn export public API**, do đó cần rất thận trọng.

### 4.4. Bảng chọn quan hệ

| Việc agent muốn làm | Quan hệ thường cần | Điều không được suy diễn |
|---|---|---|
| Code trong module A tham chiếu module B | `A reads B` | Không tự cho phép đọc private field của B |
| Module consumer cần public API của package trong source | `source exports package -> consumer` | Không tự mở private fields |
| Reflection cần `setAccessible(true)` trên non-public member | `source opens package -> caller module` | Không loại bỏ mọi cơ chế kiểm soát bảo mật khác |
| Module muốn dùng service qua `ServiceLoader` | `uses ServiceType` và type có thể truy cập tại điểm gọi | Không tự tạo provider |
| Module cung cấp service provider mới | `provides ServiceType with Provider` | Provider phải thuộc module nguồn, triển khai service và thỏa các quy tắc provider |

**Điểm thường bị bỏ sót:** `module-info.java` là declaration ở build/deploy; `redefineModule` điều chỉnh **module graph runtime**. Lệnh `javac` trong một quy trình build riêng **không tự biết** các quan hệ mà agent có thể thêm khi ứng dụng chạy sau này. Nếu source Java trực tiếp tham chiếu package chưa được export ở compile time, cần thiết kế module/build phù hợp; runtime update không thay thế quy tắc compile-time.

## 5. Quan hệ bổ sung không thể bị thu hồi bằng gọi lại với tập rỗng

Giả sử agent đã gọi:

~~~java
inst.redefineModule(
        vault,
        Set.of(sql),
        Map.of("vault.api", Set.of(client)),
        Map.of("vault.internal", Set.of(client)),
        Set.of(java.sql.Driver.class),
        Map.of());
~~~

Sau lời gọi hợp lệ, `vault` đã bổ sung reads/export/open/uses. Sau đó bạn muốn “undo” và gọi:

~~~java
inst.redefineModule(
        vault,
        Set.of(),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

**Không có quan hệ nào bị xóa.** Lời gọi thứ hai chỉ nói: *“Trong lần cập nhật này, tôi không bổ sung gì.”* Nó **không phải**: *“Hãy đặt reads/exports/opens/uses/provides bằng rỗng.”*

Sơ đồ trước–sau:

~~~text
Trước agent:
  vault.canRead(sql)                  = false
  vault.isExported("vault.api", app)  = false
  vault.isOpen("vault.internal", app) = false
  vault.canUse(java.sql.Driver.class)= false

Agent bổ sung:
  reads sql, exports api -> app, opens internal -> app, uses Driver

Ngay sau:
  reads/export/open/uses = true

Agent gọi lại với mọi collection rỗng:
  reads/export/open/uses = true   // Không thu hồi
~~~

**Đây không chỉ là “API không có hàm remove”.** Đặc tả `redefineModule` chủ động tuyên bố **không thể giảm tập quan hệ**. Nếu caller cung cấp một tập nhỏ hơn lần trước, API vẫn chỉ **bổ sung** các phần tử được liệt kê, chứ không loại bỏ các phần tử vắng mặt.

**Hậu quả vận hành:** không thể bảo đảm “tạm mở private access 5 giây, rồi đóng lại bằng cùng API”. Sau khi được thêm, quan hệ mới vẫn là một phần của module runtime **cho tới khi vòng đời runtime/module tương ứng kết thúc**, trừ các cơ chế isolation/lifecycle khác nằm ngoài `redefineModule`. Để có ranh giới sạch đáng tin cậy, thường cần restart JVM hoặc chuyển workload sang môi trường/module identities mới được thiết kế tách biệt; không gọi thao tác rỗng để giả vờ đã revoke.

## 6. Demo 1 (Java 17+): mở rộng reads/exports/opens/uses, thử “undo” thất bại

### 6.1. Thiết kế bài thực hành

Ta tạo:

- **Named module `demo.vault`**, chứa hai package `vault.api` và `vault.internal` nhưng **không export/open** package nào trong `module-info.java`.
- **`demo.Main`** trên classpath, thuộc **unnamed module**; nó chỉ dùng reflection để lấy type trong `vault.internal`, không import trực tiếp package private.
- **`demo.ModuleAgent`** là startup Java agent nhận `Instrumentation`, sau đó **khi app đang chạy** sẽ mở rộng graph bằng `redefineModule`.
- Module **`java.sql`** dùng làm một mục tiêu reads và service `java.sql.Driver` dùng minh họa `uses`.
- Cuối demo, agent gọi `redefineModule` lần nữa với **tất cả collection rỗng**, rồi đo lại module graph.

### 6.2. Cây thư mục

~~~text
module-additive-lab/
├── agent.mf
├── src/
│   ├── vault/
│   │   ├── module-info.java
│   │   └── vault/
│   │       ├── api/
│   │       │   └── Visible.java
│   │       └── internal/
│   │           └── Secret.java
│   ├── agent/
│   │   └── demo/
│   │       └── ModuleAgent.java
│   └── app/
│       └── demo/
│           └── Main.java
└── out/                        # sinh khi biên dịch
    ├── vault/
    ├── agent/
    ├── app/
    └── module-agent.jar
~~~

Code demo dưới đây đã được biên dịch với `javac --release 17` và chạy trên JDK có hỗ trợ Java 17+ cùng module instrumentation.

### 6.3. Định nghĩa named module demo.vault

Tệp **`src/vault/module-info.java`**:

~~~java
module demo.vault {
}
~~~

Tệp **`src/vault/vault/api/Visible.java`**:

~~~java
package vault.api;

public final class Visible {
    public static String hello() {
        return "hello";
    }
}
~~~

Tệp **`src/vault/vault/internal/Secret.java`**:

~~~java
package vault.internal;

public final class Secret {
    private final String token = "demo-secret";

    public Secret() {
    }
}
~~~

Module descriptor rỗng nghĩa là package `vault.api` và `vault.internal` **chưa được export/open** cho unnamed client. `Visible` là class public, nhưng public **không tự xóa rào cản module export**. `Secret` có field private để kiểm tra deep reflection.

### 6.4. Agent bổ sung bốn quan hệ

Tệp **`src/agent/demo/ModuleAgent.java`**:

~~~java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

public final class ModuleAgent {
    private static Instrumentation inst;

    public static void premain(
            String options, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void expand(
            Module vault, Module client, Module sql) {
        if (!inst.isModifiableModule(vault)) {
            throw new IllegalStateException(
                    "Module not modifiable");
        }

        inst.redefineModule(
                vault,
                Set.of(sql),
                Map.of("vault.api", Set.of(client)),
                Map.of("vault.internal", Set.of(client)),
                Set.of(java.sql.Driver.class),
                Map.of());

        System.out.println("agent:expanded");
    }

    public static void emptyUpdate(Module vault) {
        inst.redefineModule(
                vault,
                Set.of(),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of());

        System.out.println("agent:empty-request");
    }
}
~~~

**Phân tích chính xác từng tham số trong `expand`:**

1. `vault` là **named module nguồn** cần thay đổi.
2. `Set.of(sql)` làm `vault` **read thêm module `java.sql`**.
3. `Map.of("vault.api", Set.of(client))` export package `vault.api` **tới đúng unnamed client module**.
4. `Map.of("vault.internal", Set.of(client))` open package `vault.internal` **tới đúng unnamed client module** để reflection truy cập private field.
5. `Set.of(java.sql.Driver.class)` bổ sung quan hệ **uses `java.sql.Driver`** của `vault`; ta đồng thời thêm reads tới `java.sql` để service type có thể tiếp cận được khi cần.
6. `Map.of()` ở tham số cuối nghĩa là **không thêm service provider** trong lần gọi này.
7. `emptyUpdate` thực hiện một lời gọi **không có phần bổ sung nào**. Nó không có cú pháp thu hồi quyền.
8. Không có `ClassFileTransformer`, `retransformClasses` hay `redefineClasses` trong ví dụ. Đây là **đổi module relationships**, không đổi bytecode của class.

Một startup agent được nạp trước `main` để có Instrumentation, nhưng `redefineModule` chỉ được gọi **khi ứng dụng chủ động gọi `expand`**, sau khi các module đã được tải. Nhờ đó có thể đo được trạng thái “trước/sau” trong cùng JVM.

### 6.5. Main kiểm tra quyền runtime và reflection

Tệp **`src/app/demo/Main.java`**:

~~~java
package demo;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class Main {
    static void state(
            String label, Module source,
            Module target, Module sql) {
        System.out.println(
                label + ": reads-sql=" + source.canRead(sql)
                + " exports-api=" + source.isExported(
                        "vault.api", target)
                + " opens-internal=" + source.isOpen(
                        "vault.internal", target)
                + " uses-driver=" + source.canUse(
                        java.sql.Driver.class));
    }

    public static void main(String[] args)
            throws Exception {
        Class<?> cls = Class.forName("vault.internal.Secret");
        Module source = cls.getModule();
        Module target = Main.class.getModule();
        Module sql = java.sql.Driver.class.getModule();

        state("before", source, target, sql);

        Constructor<?> ctor = cls.getDeclaredConstructor();
        boolean blocked;
        try {
            ctor.setAccessible(true);
            blocked = false;
        } catch (InaccessibleObjectException expected) {
            blocked = true;
        }
        System.out.println(
                "before:reflect-blocked=" + blocked);

        ModuleAgent.expand(source, target, sql);
        state("after", source, target, sql);

        ctor.setAccessible(true);
        Object obj = ctor.newInstance();
        Field token = cls.getDeclaredField("token");
        token.setAccessible(true);
        System.out.println(
                "after:secret=" + token.get(obj));

        ModuleAgent.emptyUpdate(source);
        state("after-empty", source, target, sql);
        System.out.println(
                "after-empty:secret=" + token.get(obj));
    }
}
~~~

**Các quan sát có giá trị học tập:**

- `Class.forName` có thể tìm được class trong module đã resolved; tìm thấy class **không đồng nghĩa** reflection được quyền truy cập private member.
- `source.canRead(sql)` kiểm tra read edge, `isExported` và `isOpen` kiểm tra từng package/target module, `canUse(Driver.class)` kiểm tra service use relation.
- Trước khi mở package, `ctor.setAccessible(true)` bị từ chối với `InaccessibleObjectException`, được catch có chủ đích để demo tiếp tục.
- Sau khi agent bổ sung `opens`, `setAccessible(true)` trên constructor và field private thành công; đây là hiệu quả quan sát được, không chỉ boolean metadata.
- Cuối bài demo, `emptyUpdate` **không thu hồi** quan hệ: cả introspection lẫn quyền reflection đã mở tiếp tục có hiệu lực.

**Lưu ý:** Không truyền tên package bằng đường dẫn slash kiểu `vault/internal`. Với `extraOpens` và `extraExports`, key là **tên package dạng chấm**: `vault.internal`, `vault.api`.

### 6.6. Manifest của agent

Tệp **`agent.mf`**, kết thúc bằng newline:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ModuleAgent

~~~

Không cần `Can-Redefine-Classes: true` hoặc `Can-Retransform-Classes: true`, vì demo không dùng hai capability đó. `redefineModule` được hỗ trợ từ Java 9 và có capability kiểm tra riêng qua `isModifiableModule`.

### 6.7. Lệnh build và chạy trên Java 17+

Tại thư mục gốc `module-additive-lab`, tạo output. Nếu dùng Bash:

~~~bash
mkdir -p out/vault out/agent out/app
~~~

Nếu dùng PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/vault, out/agent, out/app
~~~

Biên dịch bằng **JDK 17 hoặc JDK mới hơn** với target API/source Java 17:

~~~bash
javac --release 17 -d out/vault src/vault/module-info.java src/vault/vault/api/Visible.java src/vault/vault/internal/Secret.java
javac --release 17 -d out/agent src/agent/demo/ModuleAgent.java
javac --release 17 -cp out/agent -d out/app src/app/demo/Main.java
jar --create --file out/module-agent.jar --manifest agent.mf -C out/agent .
~~~

**Vì sao có ba output directories?**

- `out/vault` chứa **named module** `demo.vault` và `module-info.class`.
- `out/agent` chứa `ModuleAgent.class`, đóng vào Java agent JAR.
- `out/app` chứa `Main.class` trong unnamed module trên classpath.
- `Main` không import trực tiếp `vault.internal.Secret`, nên source không bị lỗi compile vì named module chưa exports package. Nó sử dụng reflection sau khi module được resolved.

Chạy:

~~~bash
java -Xverify:all --module-path out/vault --add-modules demo.vault,java.sql -javaagent:out/module-agent.jar -cp out/app demo.Main
~~~

Các tùy chọn:

- `--module-path out/vault` khai báo vị trí named module.
- `--add-modules demo.vault,java.sql` đảm bảo **hai named modules được resolved** khi JVM khởi động; nó không thay thế `redefineModule`.
- `-javaagent` nạp agent để có `Instrumentation`.
- `-cp out/app` chạy `Main` trong unnamed module.
- `-Xverify:all` giúp kiểm tra class trong môi trường thử nghiệm.

**Stdout đã được kiểm chứng với JDK hỗ trợ các API này:**

~~~text
before: reads-sql=false exports-api=false opens-internal=false uses-driver=false
before:reflect-blocked=true
agent:expanded
after: reads-sql=true exports-api=true opens-internal=true uses-driver=true
after:secret=demo-secret
agent:empty-request
after-empty: reads-sql=true exports-api=true opens-internal=true uses-driver=true
after-empty:secret=demo-secret
~~~

### 6.8. Diễn giải từng mốc

| Thời điểm | Các quan hệ runtime | Deep reflection |
|---|---|---|
| Trước gọi `expand` | Cả `reads-sql`, `exports-api`, `opens-internal`, `uses-driver` đều **false** trong lab | `setAccessible(true)` bị từ chối |
| Sau `expand` thành công | Cả bốn trở thành **true** | Đọc private field `token` được |
| Sau `emptyUpdate` | Các quan hệ **vẫn true**, không bị thu hồi | Đọc `token` tiếp tục được |

Dòng `after-empty:secret=demo-secret` là bằng chứng dễ nhớ: **đưa tập rỗng cho `redefineModule` không “đóng” lại package**. Lưu ý object/method reflection đã được tìm hoặc thiết lập trước đó cũng không phải cách hợp lệ để giả vờ thu hồi: API không có thao tác đóng module quan hệ trong runtime này.

**Điều kiện để tái hiện đúng:** chạy trong JVM mới, không thêm sẵn `--add-exports` hoặc `--add-opens` cho các package demo, và dùng đúng module descriptor rỗng nêu ở trên. Nếu đã có một agent khác mở package trước đó, baseline “false” có thể không đúng; `redefineModule` vẫn không cung cấp đường thu hồi.

## 7. Demo 2: extraProvides cũng là bổ sung, không phải danh sách thay thế

Trong `redefineModule`, tham số **`extraProvides`** cho phép một named module đăng ký thêm **provider class** cho một service type. Provider phải:

- thuộc chính module nguồn đang được redefine;
- thực sự triển khai hoặc kế thừa service type;
- có dạng provider được `ServiceLoader` hỗ trợ;
- nằm trong **List không rỗng** cho mỗi service type key.

Quan trọng: nếu lần gọi tiếp theo không liệt kê provider cũ, điều đó **không xóa** provider đã đăng ký.

### 7.1. Bố cục mini-lab service

~~~text
module-provider-lab/
├── agent.mf
├── src/
│   ├── spi/
│   │   ├── module-info.java
│   │   └── spi/
│   │       ├── api/
│   │       │   └── Greeting.java
│   │       └── impl/
│   │           └── English.java
│   ├── agent/
│   │   └── demo/
│   │       └── ProvideAgent.java
│   └── app/
│       └── demo/
│           └── Main.java
└── out/
    ├── spi/
    ├── agent/
    ├── app/
    └── provide-agent.jar
~~~

Tại đây named module `demo.spi` export service API `spi.api` để ứng dụng có thể sử dụng interface, nhưng **chưa khai báo `provides` trong module-info**. Provider class `spi.impl.English` tồn tại trong module từ đầu nhưng chưa được công bố là service provider cho `ServiceLoader`.

### 7.2. Service và provider của named module

Tệp **`src/spi/module-info.java`**:

~~~java
module demo.spi {
    exports spi.api;
}
~~~

Tệp **`src/spi/spi/api/Greeting.java`**:

~~~java
package spi.api;

public interface Greeting {
    String message();
}
~~~

Tệp **`src/spi/spi/impl/English.java`**:

~~~java
package spi.impl;

public final class English implements spi.api.Greeting {
    public English() {
    }

    public String message() {
        return "hello";
    }
}
~~~

Không cần export package `spi.impl`: `ServiceLoader` có cơ chế xử lý provider của named module theo quy tắc riêng, khi module khai báo/công bố provider đúng cách.

### 7.3. Agent dùng extraProvides

Tệp **`src/agent/demo/ProvideAgent.java`**:

~~~java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ProvideAgent {
    private static Instrumentation inst;

    public static void premain(
            String opts, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void add(
            Module module, Class<?> service,
            Class<?> provider) {
        inst.redefineModule(
                module,
                Set.of(),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of(service, List.of(provider)));
    }

    public static void empty(Module module) {
        inst.redefineModule(
                module,
                Set.of(),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of());
    }
}
~~~

Chỉ **tham số thứ sáu** `extraProvides` có dữ liệu ở lời gọi `add`. Các map/set rỗng khác nói rõ không thêm `reads`, `exports`, `opens` hoặc `uses` trong lần gọi này. `empty` là lời gọi rỗng đối chứng: không hủy provider.

### 7.4. Ứng dụng dùng ServiceLoader

Tệp **`src/app/demo/Main.java`**:

~~~java
package demo;

import spi.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args)
            throws Exception {
        Class<?> provider = Class.forName("spi.impl.English");
        Module source = Greeting.class.getModule();

        System.out.println(
                "before-providers="
                + ServiceLoader.load(Greeting.class).stream().count());

        ProvideAgent.add(source, Greeting.class, provider);

        System.out.println(
                "after-providers="
                + ServiceLoader.load(Greeting.class).stream().count());
        System.out.println(
                "provider-message="
                + ServiceLoader.load(Greeting.class)
                        .findFirst().orElseThrow().message());

        ProvideAgent.empty(source);
        System.out.println(
                "after-empty-providers="
                + ServiceLoader.load(Greeting.class).stream().count());
    }
}
~~~

Mỗi phép đo tạo **một `ServiceLoader` mới** để quan sát trạng thái đã thay; nếu ứng dụng giữ cached loader/provider list từ trước, cache đó có thể không phản ánh ngay việc bổ sung. `Main` là unnamed module, có thể dùng service type public từ package `spi.api` của named module `demo.spi` khi module đã resolved.

### 7.5. Manifest, build và run

Tệp **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProvideAgent

~~~

Tạo output directories bằng Bash:

~~~bash
mkdir -p out/spi out/agent out/app
~~~

Hoặc PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/spi, out/agent, out/app
~~~

Tại thư mục gốc `module-provider-lab`:

~~~bash
javac --release 17 -d out/spi src/spi/module-info.java src/spi/spi/api/Greeting.java src/spi/spi/impl/English.java
javac --release 17 -d out/agent src/agent/demo/ProvideAgent.java
javac --release 17 --module-path out/spi --add-modules demo.spi -cp out/agent -d out/app src/app/demo/Main.java
jar --create --file out/provide-agent.jar --manifest agent.mf -C out/agent .
java -Xverify:all --module-path out/spi --add-modules demo.spi -javaagent:out/provide-agent.jar -cp out/app demo.Main
~~~

**Stdout đã kiểm thử:**

~~~text
before-providers=0
after-providers=1
provider-message=hello
after-empty-providers=1
~~~

Ý nghĩa:

1. Module `demo.spi` có provider class nhưng **chưa đăng ký quan hệ provides** nên `ServiceLoader` không tìm được trong phép kiểm tra ban đầu.
2. Agent gọi `redefineModule` với `extraProvides`, công bố provider đang tồn tại.
3. Một phép tra cứu mới của `ServiceLoader` tìm thấy provider, tạo object và gọi `message()` thành công.
4. `redefineModule` lần thứ hai với `Map.of()` ở `extraProvides` **không xóa provider**: count vẫn là 1.

Như vậy, tính **chỉ-bổ-sung** không chỉ áp dụng cho reads/exports/opens mà còn áp dụng cho **service provision**. Demo này có giới hạn: nó không khẳng định tất cả `ServiceLoader` đã cache từ trước phải tự reload ngay; chương trình tạo loader mới cho mỗi kiểm tra.

## 8. Vì sao không thể “thu hồi tạm thời” bằng module agent?

### 8.1. Một lần mở package không đi kèm lease/timeout

`redefineModule` không nhận timestamp, TTL, revoke token hoặc API undo. Nó không tạo “quyền tạm” mà sẽ tự hết hạn. Một agent có thể dùng điều kiện cấu hình để **chọn không tiếp tục khai thác quyền**, nhưng điều đó **khác** việc quyền JPMS đã thêm được rút khỏi module graph.

Ví dụ trong demo 1, sau `emptyUpdate`, method `source.isOpen("vault.internal", client)` vẫn true. Nếu agent tắt exporter và không gọi reflection nữa, package vẫn open ở cấp module graph cho client module đã được chỉ định.

### 8.2. removeTransformer và detach không phải revoke

- `Instrumentation.removeTransformer(transformer)` gỡ đăng ký của một classfile transformer cho các transformation tương lai; nó **không gọi module redefinition theo chiều ngược**.
- `VirtualMachine.detach()` trong Attach API ngắt kết nối control từ helper tới JVM đích, **không đóng lại các package đã open**.
- JVM chạy tiếp không tự nhận một sự kiện “agent đã xong” làm điều kiện thu hồi module edge.
- Khi agent được nạp vào JVM đích, quyền mà nó được phép tạo có thể ảnh hưởng quá trình tồn tại của JVM, nên phải tính đến vòng đời ngay từ bước thiết kế.

### 8.3. Đổi module graph khác đổi module descriptor

`Module.getDescriptor()` phản ánh thông tin khai báo module; các quan hệ được thêm động không nhất thiết thể hiện như những directive mới trong descriptor gốc. Hãy kiểm tra hiệu lực runtime bằng **`canRead`, `isExported`, `isOpen`, `canUse`** hoặc behavior thật như reflection/`ServiceLoader`, thay vì chỉ đọc file `module-info.class` rồi kết luận edge hiện thời.

### 8.4. Muốn ranh giới mới thì làm gì?

Nếu bài toán an ninh yêu cầu **đóng quyền sau phiên đo**, cần dùng một cách khác:

- **Không thêm quyền** nếu có thể đo bằng public API, JFR, logging hoặc bytecode hook không cần deep reflection.
- Đặt công cụ trong một **isolated JVM/process** và kết thúc process khi phiên đo xong. Một JVM mới bắt đầu từ module graph chưa bị mở rộng, nếu không áp dụng lại flags/agent tương ứng.
- Trong kiến trúc module layer/loader được thiết kế cho teardown, có thể tạo **module identities mới** và ngừng sử dụng graph cũ, đồng thời dọn references đúng cách. Đây là **tái tạo môi trường**, không phải thao tác thu hồi của `redefineModule` đối với module cũ.
- Thu hồi quyền ở **tầng hệ thống hoặc chính sách ứng dụng** nơi có API revoke thật sự, nếu đó là yêu cầu; không nhầm nó với khả năng giảm reads/exports/opens JPMS.

Không khẳng định có thể gọi lại `redefineModule` với `extraOpens=Map.of()` để “đóng quyền”. Điều này trái hợp đồng chính thức.

## 9. Bảo mật và nguyên tắc least privilege

### 9.1. Mở càng rộng, bề mặt truy cập càng lớn

Giữa hai lựa chọn:

~~~java
Map.of("vault.internal", Set.of(specificConsumerModule))
~~~

và một cấu hình rộng mở cho nhiều modules, cách **giới hạn tới một module đích cụ thể** giảm phạm vi cấp thêm quyền. `extraOpens` nhận **Set<Module>`; nó cho phép agent kiểm soát chính xác module đích nào nhận quyền.

Một vài nguyên tắc:

1. Chỉ mở **package thật sự cần**. Nếu có thể dùng public API thì tránh `opens` private package.
2. Chỉ cấp cho **module thực sự chạy code reflection**, không cấp nhầm cho module khác rồi vẫn gặp lỗi.
3. Không thêm mọi module vào `extraReads`; chỉ thêm edge mà bytecode mới thực sự cần.
4. Không export/open package của JVM hoặc third-party module nếu không có sự chấp thuận/quy trình vận hành phù hợp.
5. Ghi log có kiểm soát: tên source module, package, target module, thời điểm, lý do, mã yêu cầu và actor được phép khởi tạo.
6. Hiểu rõ **quyền đã cấp không tự rút lại**; đánh giá rủi ro theo **tuổi thọ JVM** chứ không chỉ thời gian agent đang thu thập dữ liệu.
7. Kiểm thử module access ở đúng JVM/vendor/module layer, không lấy kết quả từ classpath-only demo để suy cho mọi triển khai.

### 9.2. Opens không có nghĩa bỏ qua mọi lớp bảo mật

Mở package theo JPMS có thể làm reflection vào non-public members hợp lệ, nhưng không tự vô hiệu mọi kiểm soát khác: Java type access rules, module resolution, native/security restrictions và chính sách môi trường vẫn có thể ảnh hưởng. Không nên coi `redefineModule` là phép “root toàn hệ thống”.

Tuy nhiên, **nới encapsulation là hành vi nhạy cảm**. Một agent đã được tin cậy để thao tác trong JVM có ảnh hưởng lớn; không cho tải agent không rõ nguồn gốc và không nhận arbitrary package/module names từ người dùng chưa được xác thực.

### 9.3. Named vs unnamed target và CLI flags

Ví dụ dùng một **unnamed module cụ thể** của `Main` làm đích. Điều này khác với mở package rộng cho mọi unnamed modules bằng tùy chọn launcher:

~~~text
--add-opens demo.vault/vault.internal=ALL-UNNAMED
~~~

Dòng này **chỉ để đối chiếu cú pháp CLI**, không được dùng trong lệnh chạy bài thực hành vì nó sẽ làm trạng thái ban đầu `opens-internal=false` không còn đúng. `ALL-UNNAMED` có phạm vi rộng hơn một `Module` object cụ thể được chỉ định qua `Set.of(client)`.

Nhiều package nằm trong module được phân lớp bởi class loader khác nhau; phải kiểm tra đúng object `Module` và identity ở runtime. Hai module có cùng tên trong module layers khác nhau không mặc nhiên là cùng `Module` object.

## 10. Đặc điểm liên quan ServiceLoader và provider

### 10.1. extraUses không phải extraProvides

- `extraUses` bổ sung khai báo **module này sử dụng một loại service**; nó **không tạo mới provider**.
- `extraProvides` bổ sung mapping **module này cung cấp service bằng provider nào**; provider class phải là member của source module và implement/extend service type.
- `redefineModule` **không kiểm tra đầy đủ service type có thể truy cập ở mọi instrumentation site**; trách nhiệm bảo đảm accessibility thuộc về agent.
- `ServiceLoader` có quy tắc cache/discovery; một loader tạo trước khi provider được thêm có thể không phản ánh provider mới nếu không tạo loader mới hoặc reload phù hợp.

### 10.2. Provider không phải object lập tức được tạo

`Map.of(ServiceType.class, List.of(Provider.class))` bổ sung **quan hệ provides** cho module, không có nghĩa ngay tại lời gọi `redefineModule` một instance provider luôn được khởi tạo. `ServiceLoader` mới thực hiện discovery/instantiation theo quy tắc của nó ở thời điểm sử dụng.

### 10.3. Không dùng tập rỗng để xóa provider

Trong demo 2, sau khi extraProvides làm provider count = 1, cập nhật tiếp theo với `Map.of()` cho extraProvides vẫn khiến **fresh ServiceLoader** thấy 1 provider. Nếu yêu cầu loại bỏ provider khỏi một môi trường vận hành, cần lifecycle/deployment strategy khác thay vì kỳ vọng gọi empty map sẽ xóa quan hệ đã được thêm.

## 11. Xử lý lỗi và kiểm tra đầu vào

| Tình huống | Kết quả / exception có thể gặp | Hướng xử lý |
|---|---|---|
| `isModifiableModule(namedModule) == false` | `UnmodifiableModuleException` nếu cố modify | Kiểm tra capability trước, không cố ép VM |
| Truyền `null` cho module hoặc bất kỳ tham số collection | `NullPointerException` | Dùng `Set.of()` / `Map.of()` khi không bổ sung |
| Collection chứa null key/value/element | `NullPointerException` theo Javadoc | Kiểm tra và không truyền null |
| Package key không nằm trong source module | `IllegalArgumentException` | Dùng `source.getPackages()` để xác minh tên package |
| `extraExports`/`extraOpens` map một package tới Set rỗng | `IllegalArgumentException` | Nếu không thêm export/open, **bỏ key khỏi map**, không map key tới `Set.of()` |
| `extraProvides` map service tới List rỗng | `IllegalArgumentException` | Bỏ key khi không có provider mới |
| Provider class không thuộc source module | `IllegalArgumentException` | Chọn provider nằm trong module đang cập nhật |
| Provider class không implement service | `IllegalArgumentException` | Kiểm tra service/provider hierarchy trước |
| `extraUses` service không accessible tại điểm sử dụng | Có thể lỗi access/linkage hoặc `ServiceConfigurationError` khi dùng service | Bổ sung read/exports nếu cần, kiểm thử tại điểm gọi |
| Gọi `redefineModule` với unnamed module | **No-op**, không phải lỗi theo hợp đồng | Không dựa vào lời gọi này để thay graph unnamed module |
| Gọi lại tất cả collection rỗng | Giữ nguyên quan hệ đã thêm, không revoke | Không nhầm empty update với rollback |
| Reflection vẫn bị chặn sau opens | Sai source/target module, package, timing hoặc yêu cầu khác | Kiểm tra `isOpen`, loader/module identity, loại member và exception gốc |

### 11.1. Kiểm tra key package trước khi gọi

~~~java
if (!source.getPackages().contains("vault.internal")) {
    throw new IllegalArgumentException(
            "Package absent from source module");
}
~~~

**Trích đoạn** này cần biến `source` kiểu `Module` đã xác định. Java API yêu cầu tên package dạng Java **với dấu chấm**; tên nội bộ JVM `vault/internal` không phải key đúng.

### 11.2. Quan hệ runtime có thể đã mở từ trước

Trước khi bổ sung, có thể kiểm tra:

~~~java
boolean alreadyOpen =
        source.isOpen("vault.internal", client);
~~~

Nếu đã true, không nhất thiết cần gọi `redefineModule` thêm lần nữa. Nhưng **đừng dùng false sau khi gỡ transformer làm mục tiêu mong muốn**: thay đổi của transformer không điều khiển quan hệ module đã mở.

### 11.3. isModifiableModule không phải permission check toàn cục

`isModifiableModule` chỉ trả lời **module có thể được sửa bằng redefineModule hay không**. Nó không thay thế chính sách authorization của doanh nghiệp về **ai được yêu cầu agent mở package nào**, cũng không phải bằng chứng quyền đã được thu hồi sau đó. Agent production cần một control plane độc lập với quyền thao tác phù hợp và lưu dấu các thay đổi đã cấp.

## 12. Concurrency, nhiều agent và trạng thái tích lũy

Javadoc ghi nhận `redefineModule` **an toàn khi được gọi đồng thời**, cho phép nhiều agent bổ sung quan hệ cho cùng module gần như cùng thời điểm. Điều này không biến API thành một transaction với khả năng “restore snapshot”:

~~~text
Agent A: opens package.p -> Module X
Agent B: opens package.p -> Module Y
Agent A: redefineModule(package.p -> empty)
Kết quả: quyền mở đã thêm tới X/Y không bị gỡ bằng lời gọi cuối
~~~

**Nguy cơ “lost update” do ghi đè cả graph** không phải mô hình đúng của API này vì nó là **mở rộng**. Nhưng nhiều agent có thể tạo ra một **tập hợp quyền rộng hơn dự kiến**, vì mỗi agent chỉ nhìn yêu cầu của mình. Người vận hành cần kiểm kê **tổng các quyền đã bổ sung**, không chỉ cấu hình agent hiện tại.

### 12.1. Idempotency có giới hạn

Gọi thêm cùng một read/export/open relation đã tồn tại thường không làm nó biến thành quyền mới khác. Tuy nhiên, đừng coi cả pipeline agent là idempotent chỉ vì JPMS relation đã có: agent còn có thể đăng ký transformer, provider, thread, MBean hoặc telemetry exporter. Quản lý lifecycle của các resource ấy riêng biệt.

### 12.2. Module descriptor không phải một log đầy đủ

Một ứng dụng có thể có cấu hình `module-info.java` gần như không đổi, trong khi runtime graph đã được mở bởi agent hoặc launcher flags. Vì vậy, khi điều tra lỗi encapsulation/reflective access, ghi lại **module identity + trạng thái `isOpen/isExported/canRead/canUse`** tại runtime, không chỉ in module descriptor.

## 13. Tình huống ứng dụng trong instrumentation

### 13.1. Agent chèn helper call vào named module

Giả sử bạn instrument một class thuộc named module `business.core` và chèn call tới helper trong module `telemetry.agent`. Nếu module class đích chưa read module helper, việc liên kết callback/helper có thể thất bại dù bytecode classfile hợp lệ.

Agent có thể cần:

~~~java
inst.redefineModule(
        businessModule,
        Set.of(telemetryModule),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

Đây là **trích đoạn minh họa**, giả định các Module variables đã có. Trước khi làm, kiểm tra liệu JVM đã thêm read edge thích hợp cho helper từ agent theo quy tắc instrumentation hay chưa; không mở quyền thừa khi không cần.

**Quan trọng:** thêm reads không tự làm helper API được export. Phía module helper có thể cần export package chứa helper cho business module, hoặc dùng cách bố trí helper phù hợp class loader/agent mechanism.

### 13.2. Agent muốn đọc private field của framework

Nếu logic chẩn đoán cần deep reflection vào package nội bộ của `framework.core`, source của `extraOpens` phải là **module đang chứa package**; target là module của **code thực hiện reflection**.

~~~java
inst.redefineModule(
        frameworkModule,
        Set.of(),
        Map.of(),
        Map.of("framework.internal", Set.of(agentModule)),
        Set.of(),
        Map.of());
~~~

Đây cũng là **trích đoạn**. Không nhầm direction bằng cách mở package trong `agentModule` rồi kỳ vọng package của framework được mở. Nếu deep reflection không thật sự cần thiết, ưu tiên API ít quyền hơn.

### 13.3. Agent không phải công cụ thu hồi quyền khi ngừng đo

Sau khi hoàn thành việc chẩn đoán, agent có thể dừng các tác vụ nền, gỡ transformer hoặc ngừng export dữ liệu. **Quyền JPMS đã mở vẫn còn**. Kế hoạch tắt cần nói rõ: “dừng hoạt động instrumentation” **khác** “thu hồi `opens` đã cấp”. Nếu audit yêu cầu revoke thật, cần lộ trình restart/isolation và xác nhận không còn module identity cũ đang được dùng.

## 14. Bài tập và đáp án

### Bài tập A — dự đoán sau empty update

Demo 1 đã gọi `expand` làm `vault.isOpen("vault.internal", client)` true. Sau đó gọi `emptyUpdate` với `extraOpens=Map.of()`. Dự đoán `isOpen` và thử `ctor.setAccessible(true)`.

**Đáp án:** `isOpen` vẫn true; reflection tiếp tục được cho phép bởi quan hệ đã mở, giả định không có kiểm soát khác thay đổi.

### Bài tập B — phân biệt exports và opens

Đổi Demo 1 để **chỉ** có `extraExports` cho package `vault.internal`, không có `extraOpens`. Dự đoán public members có thể được truy cập thông thường ở những điều kiện phù hợp, nhưng `setAccessible(true)` cho private `token` **không được mở chỉ bởi qualified export**. Giải thích vì sao quyền này khác `opens`.

### Bài tập C — wrong direction

Agent muốn đọc field private trong `framework.core.internal` nhưng lại gọi `redefineModule(agentModule, ..., extraOpens...)`. Điều gì sai? **Source module** phải là module **sở hữu package**, target mới là module thực hiện reflection.

### Bài tập D — provider không mất sau cập nhật rỗng

Chạy Demo 2, thêm provider với `extraProvides` rồi gọi cập nhật rỗng. Dự đoán `ServiceLoader.load(Greeting.class).stream().count()` khi tạo loader mới: **1**, không quay về 0.

### Bài tập E — validation của extraOpens

Thử truyền `Map.of("vault.internal", Set.of())`. Theo hợp đồng API, có thể nhận `IllegalArgumentException` vì **map chứa key với Set rỗng**. Nếu không muốn thêm quyền cho package ấy, nên **bỏ entry key**, không tạo key rỗng.

### Bài tập F — kiểm tra unnamed module

Trong demo, lấy `Module app = Main.class.getModule()`. `app.isNamed()` dự kiến false. Hỏi vì sao `inst.isModifiableModule(app)` vẫn có thể true nhưng gọi `redefineModule(app, ...)` không mở rộng như với named module? Vì đặc tả định nghĩa **unnamed module update là no-op**.

### Bài tập G — chính sách vận hành

Một nhóm đề xuất mở package private trong 10 phút rồi “tắt quyền” bằng `extraOpens=Map.of()`. Hãy nêu tối thiểu hai lỗi thiết kế và đề xuất giải pháp. **Đáp án định hướng:** API không revoke; một module target có quyền open sẽ giữ quyền, nên cần giảm quyền ban đầu hoặc dùng process isolation/restart nếu cần ranh giới phục hồi.

### Câu hỏi tự kiểm tra

1. **`redefineModule` có cho phép xóa read edge đã thêm không?** — Không.
2. **`extraExports` là export public API hay deep reflection?** — Chủ yếu là export package; deep reflection trên non-public members cần opens phù hợp.
3. **`extraOpens` key dùng dạng `vault/internal` hay `vault.internal`?** — `vault.internal`.
4. **Khi map package tới Set rỗng, có phải là remove không?** — Không; còn là input không hợp lệ cho export/open.
5. **`extraUses` có tự tạo provider không?** — Không.
6. **`extraProvides` có phải danh sách thay thế hoàn chỉnh không?** — Không, chỉ bổ sung.
7. **`redefineModule` trên unnamed module có hiệu lực mở rộng không?** — Không, no-op.
8. **`isModifiableModule(unnamed)` trả gì?** — Theo Javadoc, true.
9. **`removeTransformer` có đóng lại `opens` đã thêm không?** — Không.
10. **Cách kiểm tra trạng thái thực tế sau cập nhật?** — `canRead`, `isExported`, `isOpen`, `canUse`, truy cập thật/ServiceLoader.

## 15. Checklist triển khai an toàn

### Trước khi cấp quyền

- [ ] Xác định named source module, package và target module object chính xác.
- [ ] Xác minh package key thuộc `source.getPackages()`.
- [ ] Xác nhận đang cần reads, exports, opens, uses hay provides; không dùng quyền rộng khi chỉ cần hẹp.
- [ ] Kiểm tra `inst.isModifiableModule(source)`.
- [ ] Hiểu rõ **quyền được thêm không thể bị thu hồi bởi `redefineModule`**.
- [ ] Có phê duyệt và audit cho các qualified exports/opens vào package nhạy cảm.
- [ ] Tránh tự động nhận package/target module từ input không đáng tin.

### Trong khi cập nhật

- [ ] Dùng collection không null; `Set.of()`/`Map.of()` cho các loại không thay đổi.
- [ ] Không đưa key package với Set rỗng vào `extraExports`/`extraOpens`.
- [ ] Với `extraProvides`, provider thực sự thuộc source module, implements service và list không rỗng.
- [ ] Ghi lại quan hệ được bổ sung, actor và thời điểm.
- [ ] Khi nhiều agent gọi đồng thời, kiểm kê kết quả **tích lũy**, không coi lời gọi sau là replace.
- [ ] Kiểm tra điều kiện lỗi và xử lý exceptions có kiểm soát.

### Sau khi cập nhật

- [ ] Đọc trạng thái runtime `canRead`, `isExported`, `isOpen`, `canUse`.
- [ ] Thử đúng hành vi cần thiết: helper linkage, reflection, `ServiceLoader`.
- [ ] Ghi rõ việc ngừng agent/transformer **không tương đương** thu hồi JPMS relations.
- [ ] Nếu cần ranh giới privilege mới, kiểm tra kế hoạch restart/isolation.
- [ ] Tránh in secrets từ demo vào log production; `demo-secret` chỉ phục vụ thí nghiệm.
- [ ] Test trên JDK/vendor/class loader/module layers thực tế.
- [ ] Không tuyên bố đã revoke nếu chỉ gọi lại `redefineModule` bằng collection rỗng.

## 16. Tổng kết và tài liệu tham khảo

**Nguyên tắc phải nhớ:** trong Java Instrumentation, `redefineModule` là một **API chỉ-bổ-sung quan hệ module**, không phải API thay graph bằng một bản cấu hình mới. Nó có thể thêm **reads**, **exports**, **opens**, **uses** và **provides**. Nó **không thể làm giảm** các quan hệ hiện có; các tham số rỗng ở lần gọi sau không hủy quyền đã thêm.

Demo 1 chứng minh module graph mở rộng từ false sang true và vẫn true sau empty update; demo 2 chứng minh một provider mới xuất hiện qua `ServiceLoader` vẫn tồn tại sau cập nhật rỗng. Khi thiết kế agent có quyền truy cập package nội bộ, cần tuân thủ **least privilege**, giới hạn source/target module cụ thể và định nghĩa một chiến lược lifecycle khác nếu bài toán thực sự đòi hỏi thu hồi quyền.

**Tài liệu chuẩn (Java SE 17):**

- [Instrumentation.redefineModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map)): chữ ký, tính chất chỉ-bổ-sung, unnamed no-op, validation, concurrency, `isModifiableModule`.
- [java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `canUse` và phân biệt named/unnamed.
- [java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): các cơ chế khởi tạo agent, quyền truy cập tới modules và class loaders.
- [UnmodifiableModuleException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableModuleException.html): module không thể sửa theo API Instrumentation.
- [java.util.ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): service discovery và provider bổ sung động.
- [JLS 17 `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, `uses`, `provides`.
