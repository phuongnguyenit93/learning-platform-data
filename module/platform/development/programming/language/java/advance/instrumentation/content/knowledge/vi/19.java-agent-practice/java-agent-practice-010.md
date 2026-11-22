# Thử module có đóng gói mạnh và bổ sung đúng quan hệ cần thiết

Trong thực nghiệm Java Instrumentation, một agent thường cần quan sát một lớp nằm trong **named module** mà package của lớp ấy không `exports` hoặc `opens` cho bên ngoài. Dù agent có thể tìm được `Class<?>` bằng tên, lời gọi phương thức public qua reflection vẫn có thể bị từ chối; truy cập private member bị từ chối mạnh hơn. Trường hợp khác, mã bytecode được chèn cần dùng một helper trong **module khác** nhưng target module không có quan hệ đọc tới helper.

Cách xử lý chính xác không phải “mở hết module”, mà là xác định **quan hệ nào thực sự thiếu** và **module nào thực sự cần nhận quyền**:

- **Readability**: module A có đọc module B không? `A.canRead(B)`.
- **Qualified export**: package `p` của A có cho B truy cập public types và public members qua các cơ chế tương ứng không? `A.isExported("p", B)`.
- **Qualified open**: package `p` của A có cho B làm *deep reflection* vào non-public members không? `A.isOpen("p", B)`.
- **Class-loader visibility**: class loader thực sự tìm được class/helper hay không? Đây là điều kiện **riêng**, không tự được giải quyết bằng read/export/open.

Trong module **Java Advance – instrumentation**, phần **Thực nghiệm agent**, bài này xây dựng một chương trình Java 17+ có **hai named module và một startup agent**, lần lượt xác nhận quyền bị từ chối rồi dùng `Instrumentation.redefineModule(...)` để bổ sung chính xác ba quan hệ cần thiết. Các bước được kiểm tra bằng kết quả chạy thực tế và tiếp tục xác minh rằng **module không liên quan không nhận quyền**.

## 1. Mục tiêu của bài thực nghiệm

Sau khi hoàn thành, bạn cần thực hiện được:

1. Tạo named module có **strong encapsulation**: package nội bộ tồn tại và chứa public class nhưng không `exports`/không `opens`.
2. Phân biệt ba tình huống: thiếu read edge, thiếu export cho public access, thiếu open cho deep reflection.
3. Dùng `Module.canRead`, `Module.isExported`, `Module.isOpen`, `Method.invoke` và `Method.trySetAccessible` để **quan sát sự khác biệt**, không chỉ suy đoán từ `module-info.java`.
4. Sửa quan hệ ở **runtime** bằng `Instrumentation.redefineModule`, với tập `Set.of(...)` chỉ chứa module nhận quyền.
5. Chứng minh sau khi grant cho agent, package không được export/open vô điều kiện và không tự cấp quyền cho module thứ ba.
6. Nhận ra giới hạn: thay đổi runtime graph **không sửa module descriptor ở source**, không sửa class loader delegation, không cấp quyền truy cập private khi chỉ `exports`, và không tự bảo đảm bytecode weaving đúng.

## 2. “Đóng gói mạnh” trong Java Platform Module System

Trong Java 9+, `module-info.java` mô tả dependency và ranh giới package của một **named module**. Ví dụ:

```java
module demo.secure {
}
```

Khi module chứa package `demo.secret` nhưng không khai báo:

```java
exports demo.secret;
opens demo.secret;
```

thì code ở module khác không mặc nhiên truy cập package đó. Đặc biệt:

- **Có một class `public` chưa đủ**. Nếu package của nó không được export tới module của caller, Java access control có thể chặn lời gọi public method qua reflection.
- **Có export chưa đủ để truy cập private**. Deep reflection tới private method/field thường đòi package **open** về phía module thực hiện reflection.
- `opens` mở cho deep reflection, quyền rộng hơn export trong nhiều tình huống. Một package được open tới module B cũng được xem là exported tới B ở **runtime** theo `Module.isExported(package, B)`; nhưng **export đơn thuần không đồng nghĩa open**.
- `exports p to moduleB;` và `opens p to moduleB;` là quan hệ **có điều kiện theo module đích**, không phải mở công khai cho mọi module.
- Package không export/open không đồng nghĩa class không thể được tìm thấy. Class loading, module accessibility và reflective access là các tầng riêng biệt.

> **Strong encapsulation không phải sandbox bảo mật tuyệt đối chống agent đáng tin ở cùng JVM.** Agent có `Instrumentation` và quyền sửa module graph có thể chủ động mở rộng quyền ở runtime; vì vậy chỉ nạp agent từ nguồn đáng tin và quản lý phạm vi cấp quyền chặt chẽ.

### 2.1. Ma trận các quyền

| Điều kiện quan sát | `canRead` | `isExported` | `isOpen` | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Module A đọc B | `A.canRead(B)` | Không tự thay đổi | Không tự thay đổi | Bổ sung cạnh đọc cho module A; chưa cho A quyền vào mọi package B |
| Module A export package `p` tới B | Không tự thêm read edge | `A.isExported("p", B)=true` | Vẫn có thể `false` | B được truy cập API public của `p` khi các điều kiện khác phù hợp |
| Module A open `p` tới B | Không tự thêm read edge | Được coi là export tại runtime tới B | `A.isOpen("p", B)=true` | Code trong B có thể yêu cầu bỏ qua kiểm tra access khi reflection vào `p` |
| Export/open vô điều kiện | Không đồng nghĩa mọi read edge | `isExported("p")` hoặc `isOpen("p")` | Rộng hơn một đích | Không nên cấp rộng nếu chỉ một agent cần quyền |

Một module **unnamed** (như agent trên classpath) đọc tất cả module, nhưng **điều đó không khiến mọi named module export/open package cho nó**. Đây là lý do agent tìm thấy `demo.secret.Hidden` nhưng có thể bị chặn ở `Method.invoke`.

## 3. `Instrumentation.redefineModule`: chỉ bổ sung các quyền cần thiết

Agent nhận `Instrumentation` từ `premain` hoặc `agentmain`. API Java 9+ có chữ ký:

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

Ý nghĩa của các tham số:

| Tham số | Bổ sung gì? | Ví dụ nhu cầu |
| --- | --- | --- |
| `module` | Module **bị thay đổi** | `demo.secure`, là nguồn của read edge/export/open |
| `extraReads` | Tập module mà `module` sẽ đọc thêm | Mã đã instrument trong `demo.secure` cần đọc named module `demo.helper` |
| `extraExports` | Package trong `module` được export thêm tới tập module đích | Agent cần gọi public method của `demo.secret.Hidden` |
| `extraOpens` | Package trong `module` được mở thêm cho deep reflection tới tập module đích | Agent cần truy cập private method `Hidden.token()` |
| `extraUses` | Service interfaces mà module sử dụng thêm | Chỉ dùng khi instrumentation thật sự cần service-loading relation |
| `extraProvides` | Service providers mà module cung cấp thêm | Chỉ dùng khi có service provider thực sự phù hợp |

Bài này không dùng dịch vụ Java ServiceLoader nên truyền `Set.of()` và `Map.of()` rỗng cho hai tham số cuối. **Không thêm quyền service chỉ vì API có tham số đó.**

Các quy tắc cần nắm:

- `redefineModule` **chỉ mở rộng** tập reads/exports/opens/uses/provides. API này **không gỡ** một quyền đã thêm và không dùng để khôi phục module graph về trạng thái ban đầu.
- Nếu `module` là unnamed module, API là **no-op**. Đối tượng cần sửa trong bài là **named module `demo.secure`**, không phải unnamed module của agent.
- Gọi `inst.isModifiableModule(target)` trước khi thao tác. Nếu JVM không cho sửa module, phải báo không hỗ trợ; không thử lách bằng cách viết trực tiếp cấu trúc nội bộ JDK.
- Key của `extraExports`/`extraOpens` phải là **package thật sự nằm trong module được sửa**, ví dụ `"demo.secret"`. Giá trị phải là tập module đích **không rỗng**.
- `Map.of("demo.secret", Set.of(agentModule))` cấp quyền cho **một module cụ thể**; khác rất xa với `--add-opens demo.secure/demo.secret=ALL-UNNAMED`, vốn cho phép tất cả unnamed modules tiếp cận package đó.
- Việc JVM cho phép thêm các cạnh không đảm bảo chúng đúng về thiết kế. Cần chứng minh từng cạnh cần cho một use case thực tế.

## 4. Kiến trúc thí nghiệm

Ta xây dựng hai named module:

1. **`demo.secure`**: có `demo.app.Main` và `demo.secret.Hidden`. Module này **không export/open** package `demo.secret`; `Hidden` có `public static greeting()` và `private static token()`.
2. **`demo.helper`**: có class `helper.api.Bridge`, export package `helper.api`. Đây là một named module tồn tại trong boot layer nhưng ban đầu **`demo.secure` không đọc nó**.

Startup agent **`probe.AccessAgent`** nằm trong unnamed module của system class loader. Agent nhận `Instrumentation`, kiểm tra ba điều kiện, sau đó bổ sung lần lượt:

```text
(1) demo.secure --reads--> demo.helper

(2) demo.secure --exports demo.secret --> agent unnamed module

(3) demo.secure --opens demo.secret --> agent unnamed module

                      (không cấp export/open cho demo.helper)
```

### 4.1. Hình dung module graph

```text
Named module: demo.secure
  +-- demo.app.Main
  +-- demo.secret.Hidden      [không exports/opens trong module-info]

Named module: demo.helper
  +-- helper.api.Bridge       [exports helper.api]

Unnamed module: agent
  +-- probe.AccessAgent

Trước:
    demo.secure --X--> demo.helper           (không read)
    demo.secure/demo.secret --X--> agent      (không export/open)
    demo.secure/demo.secret --X--> demo.helper

Sau:
    demo.secure ------READS------> demo.helper
    demo.secure/demo.secret --EXPORTS------> agent unnamed
    demo.secure/demo.secret --OPENS--------> agent unnamed
    demo.secure/demo.secret --X------------> demo.helper
```

**Cẩn trọng với chiều cạnh:** `extraReads` có module nguồn là `demo.secure`; `extraExports` và `extraOpens` cũng thay đổi `demo.secure`, nhưng module nhận quyền là **agent unnamed module**. Agent vốn thuộc unnamed module nên tự nó đọc mọi named module; không cần thêm cạnh `agent → demo.secure`.

Trong demo, phần `extraReads` chỉ được **kiểm chứng bằng runtime module graph** qua `canRead`. Nó không giả vờ chứng minh một method đã liên kết tới `Bridge`, vì chưa chèn một lời gọi `invokestatic` như vậy vào bytecode. Tình huống export và open được kiểm tra bằng **lời gọi reflection thực tế**.

## 5. Cấu trúc tệp Java 17+

```text
module-access-lab/
├── agent.mf
├── agent-src/
│   └── probe/
│       └── AccessAgent.java
├── src/
│   ├── demo.secure/
│   │   ├── module-info.java
│   │   └── demo/
│   │       ├── app/
│   │       │   └── Main.java
│   │       └── secret/
│   │           └── Hidden.java
│   └── demo.helper/
│       ├── module-info.java
│       └── helper/
│           └── api/
│               └── Bridge.java
└── out/                            # tạo bằng các lệnh build
    ├── agent/
    ├── mods/
    └── access-agent.jar
```

Hãy dùng **đúng tên file và đường dẫn**, vì `javac --module-source-path` dựa vào tên thư mục module (`demo.secure`, `demo.helper`) để tạo class ở đúng module.

### 5.1. Named module đóng gói mạnh

Tệp `src/demo.secure/module-info.java`:

```java
module demo.secure {
}
```

Không có `exports demo.secret`, không có `opens demo.secret`, không có `requires demo.helper`. Đây là chủ đích kiểm tra strong encapsulation.

Tệp `src/demo.secure/demo/secret/Hidden.java`:

```java
package demo.secret;

public final class Hidden {
    private Hidden() {}

    public static String greeting() {
        return "public-ok";
    }

    private static String token() {
        return "private-ok";
    }
}
```

Class và `greeting()` là **public**, nhưng package vẫn không export sang agent. `token()` là **private**, nên ngay cả khi package được export cho agent, deep reflection vào method này vẫn đòi quyền `opens` phù hợp.

Tệp `src/demo.secure/demo/app/Main.java`:

```java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app: running");
    }
}
```

Chương trình main không tự import agent. Toàn bộ việc quan sát/cấp quyền diễn ra trong `premain`; dòng `app: running` cho biết ứng dụng vẫn khởi động sau khi thí nghiệm agent hoàn tất.

### 5.2. Named module helper để kiểm tra `extraReads`

Tệp `src/demo.helper/module-info.java`:

```java
module demo.helper {
    exports helper.api;
}
```

Tệp `src/demo.helper/helper/api/Bridge.java`:

```java
package helper.api;

public final class Bridge {
    private Bridge() {}

    public static String ping() {
        return "helper-ok";
    }
}
```

Module helper **có mặt trong boot layer** nhờ tùy chọn `--add-modules demo.helper` khi chạy, nhưng việc module tồn tại **không tự thêm** quan hệ `demo.secure → demo.helper`.

Ta chủ động **không viết** `requires demo.helper;` trong `demo.secure/module-info.java`. Nếu khai báo nó, `secure.canRead(helper)` có thể đã `true` trước khi agent thao tác, làm mất phép đối chứng.

### 5.3. Java agent: đo trước, cấp quyền theo từng lớp, đo lại

Tệp `agent-src/probe/AccessAgent.java`:

```java
package probe;

import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;

public final class AccessAgent {
    public static void premain(String args, Instrumentation inst)
            throws Exception {

        Module secure = ModuleLayer.boot()
                .findModule("demo.secure").orElseThrow();
        Module helper = ModuleLayer.boot()
                .findModule("demo.helper").orElseThrow();
        Module agent = AccessAgent.class.getModule();

        Class<?> hidden = Class.forName(
                "demo.secret.Hidden",
                false,
                ClassLoader.getSystemClassLoader());
        Method publicMethod = hidden.getDeclaredMethod("greeting");
        Method privateMethod = hidden.getDeclaredMethod("token");

        System.out.println("before:read=" + secure.canRead(helper));
        System.out.println("before:export="
                + secure.isExported("demo.secret", agent));
        System.out.println("before:open="
                + secure.isOpen("demo.secret", agent));
        System.out.println("before:public=" + callPublic(publicMethod));
        System.out.println("before:private-access="
                + privateMethod.trySetAccessible());

        if (!inst.isModifiableModule(secure)) {
            throw new IllegalStateException("module not modifiable");
        }

        // Bước 1: chỉ cho module secure đọc module helper.
        inst.redefineModule(
                secure,
                Set.of(helper),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of());
        System.out.println("after-read:read=" + secure.canRead(helper));

        // Bước 2: chỉ export package demo.secret tới agent.
        inst.redefineModule(
                secure,
                Set.of(),
                Map.of("demo.secret", Set.of(agent)),
                Map.of(),
                Set.of(),
                Map.of());
        System.out.println("after-export:export="
                + secure.isExported("demo.secret", agent));
        System.out.println("after-export:public="
                + callPublic(publicMethod));
        System.out.println("after-export:private-access="
                + privateMethod.trySetAccessible());

        // Bước 3: chỉ open package demo.secret tới agent.
        inst.redefineModule(
                secure,
                Set.of(),
                Map.of(),
                Map.of("demo.secret", Set.of(agent)),
                Set.of(),
                Map.of());
        System.out.println("after-open:open="
                + secure.isOpen("demo.secret", agent));
        System.out.println("after-open:private-access="
                + privateMethod.trySetAccessible());
        System.out.println("after-open:private-value="
                + privateMethod.invoke(null));

        // Xác minh nguyên tắc chỉ cấp quyền cho đúng module đích.
        System.out.println("isolation:export-to-helper="
                + secure.isExported("demo.secret", helper));
        System.out.println("isolation:open-to-helper="
                + secure.isOpen("demo.secret", helper));
        System.out.println("isolation:export-unqualified="
                + secure.isExported("demo.secret"));
    }

    private static String callPublic(Method m) throws Exception {
        try {
            return (String) m.invoke(null);
        } catch (IllegalAccessException e) {
            return e.getClass().getSimpleName();
        }
    }
}
```

**Đặc điểm quan trọng của thí nghiệm:**

- Agent dùng `ModuleLayer.boot().findModule(...)` để lấy **đúng hai runtime `Module` objects**, không tạo module giả hoặc so tên chuỗi để cấp quyền. `--add-modules demo.helper` đảm bảo helper được resolve vào boot layer.
- Agent thuộc unnamed module, nên `agent.isNamed()` sẽ là `false`. Ta dùng **chính** object `AccessAgent.class.getModule()` làm đích của export/open; không dùng một module khác tự tạo.
- `Class.forName(..., false, loader)` lấy đối tượng `Class<?>` nhưng không yêu cầu chạy static initializer của `Hidden`. Package chưa export **không nhất thiết ngăn class loading**. Những phép thử access nằm ở `Method.invoke` và `trySetAccessible`.
- `getDeclaredMethod` chỉ lấy metadata của method; không phải bằng chứng rằng invocation đã được cho phép.
- `callPublic` cố ý bắt **đúng `IllegalAccessException`** do public method trong package chưa export. Nếu có exception bất ngờ khác, demo không nuốt và sẽ báo lỗi startup thay vì in "success".
- `trySetAccessible()` trả boolean: `false` khi không thể bật quyền reflection; khác `setAccessible(true)`, vốn có thể ném `InaccessibleObjectException`.
- Các lời gọi `redefineModule` được tách từng bước để chứng minh hiệu ứng riêng của read, export và open. Trong agent thật có thể gộp các thay đổi cần thiết vào một lần gọi sau khi đã xác định đúng quyền.
- Thí nghiệm **không sửa bytecode**, không đăng ký transformer và không yêu cầu `Can-Retransform-Classes`. Tên API `redefineModule` **không đồng nghĩa** `redefineClasses`. Mục tiêu là quan sát runtime JPMS graph qua Java Instrumentation.

## 6. Manifest, biên dịch và chạy

### 6.1. Manifest của startup agent

Tệp `agent.mf` (có **một dòng trống cuối**):

```text
Manifest-Version: 1.0
Premain-Class: probe.AccessAgent

```

Không cần `Can-Redefine-Classes: true` chỉ để dùng `redefineModule`; đó là capability riêng của việc redefine **class**. Thí nghiệm chỉ cần JVM hỗ trợ API module và module `demo.secure` là modifiable.

### 6.2. Tạo thư mục output

Trong thư mục gốc `module-access-lab`, Linux/macOS:

```bash
mkdir -p out/agent out/mods
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/agent, out/mods | Out-Null
```

### 6.3. Biên dịch mã Java 17

```bash
javac --release 17 -d out/agent agent-src/probe/AccessAgent.java

jar --create --file out/access-agent.jar --manifest agent.mf -C out/agent .

javac --release 17 -d out/mods --module-source-path src src/demo.secure/module-info.java src/demo.secure/demo/app/Main.java src/demo.secure/demo/secret/Hidden.java src/demo.helper/module-info.java src/demo.helper/helper/api/Bridge.java
```

Các lệnh dùng cùng cú pháp trong bash/PowerShell nếu `javac`, `java`, `jar` trên `PATH`. Chú ý:

- **Agent được biên dịch riêng trên classpath** vào `out/agent`, không trộn nó vào named module `demo.secure`.
- **Hai named module** được biên dịch bởi `--module-source-path src` vào `out/mods`.
- **JAR chứa agent** phải được đóng với `Premain-Class` phù hợp; launcher sẽ tìm `probe.AccessAgent`.
- Cả demo đều tương thích source/classfile mức Java 17 vì dùng `--release 17`. Lệnh chạy có thể dùng một JVM mới hơn hỗ trợ Java 17 classfiles.

### 6.4. Chạy baseline không có agent

```bash
java --module-path out/mods --add-modules demo.helper --module demo.secure/demo.app.Main
```

Đầu ra chuẩn:

```text
app: running
```

Không có phép thay đổi module runtime vì `premain` không được gọi. Đây là trường hợp đối chứng để biết ứng dụng/module chạy được mà không cần agent.

### 6.5. Chạy với agent

```bash
java -javaagent:out/access-agent.jar --module-path out/mods --add-modules demo.helper --module demo.secure/demo.app.Main
```

**Stdout được kiểm chứng** khi biên dịch bằng `javac --release 17` và chạy trên **Azul Zulu OpenJDK 24.0.2**:

```text
before:read=false
before:export=false
before:open=false
before:public=IllegalAccessException
before:private-access=false
after-read:read=true
after-export:export=true
after-export:public=public-ok
after-export:private-access=false
after-open:open=true
after-open:private-access=true
after-open:private-value=private-ok
isolation:export-to-helper=false
isolation:open-to-helper=false
isolation:export-unqualified=false
app: running
```

**Đây là kết quả quan sát của đúng thí nghiệm**, không phải một quy luật rằng mọi JVM/mọi module sẽ cho `before:read=false`. Nếu có thêm `--add-reads`, `--add-opens`, agent khác hoặc module descriptor khác, trạng thái ban đầu có thể đã thay đổi.

## 7. Phân tích từng bước của output

### 7.1. Trước khi cấp quyền: module đã đóng gói mạnh

```text
before:read=false
before:export=false
before:open=false
before:public=IllegalAccessException
before:private-access=false
```

- `demo.secure` **không đọc** `demo.helper` do descriptor không có `requires demo.helper` và launcher chưa thêm read edge cho cặp này.
- `demo.secret` **không được export/open** tới unnamed module của agent.
- Dù `Hidden` và `greeting()` đều là `public`, lời gọi reflective `Method.invoke(null)` từ agent bị chặn: package chưa export cho caller.
- `token()` là private: `trySetAccessible()` không thể bật suppress access checks khi package chưa open cho caller.

Điều này chứng minh **class được tìm thấy** không đồng nghĩa **member được phép gọi**.

### 7.2. Sau `extraReads`: chỉ cạnh đọc thay đổi

```text
after-read:read=true
```

Agent gọi:

```java
inst.redefineModule(
    secure, Set.of(helper), Map.of(), Map.of(), Set.of(), Map.of());
```

Nó thêm quan hệ **`demo.secure → demo.helper`**. Nó **không** export package `demo.secret`, không open package ấy và không tự làm helper class được tìm thấy từ một class loader vốn không có đường nạp.

Đây là cách chứng minh read edge ở runtime. Vì ví dụ chưa chèn instruction gọi `helper.api.Bridge` từ class trong `demo.secure`, phép kiểm tra không khẳng định kết nối bytecode đã hoàn tất. Muốn kiểm tra invocation thật cần một test riêng có bytecode hợp lệ, helper exported, loader visibility phù hợp và bản build test được xác định.

### 7.3. Sau `extraExports`: public method được phép, private vẫn bị chặn

```text
after-export:export=true
after-export:public=public-ok
after-export:private-access=false
```

Agent gọi:

```java
inst.redefineModule(
    secure, Set.of(),
    Map.of("demo.secret", Set.of(agent)),
    Map.of(), Set.of(), Map.of());
```

`agent` là module cụ thể mà `AccessAgent.class` thuộc về. Sau lời gọi, package `demo.secret` được export **có điều kiện** về phía agent. `publicMethod.invoke(null)` thành công và trả `public-ok`. Tuy nhiên `token()` vẫn private; export không cấp quyền **deep reflection**, nên `privateMethod.trySetAccessible()` vẫn trả `false`.

Đây là phép thử hữu ích để tránh cấp `opens` quá rộng khi agent thực sự chỉ cần public API.

### 7.4. Sau `extraOpens`: private reflection được phép

```text
after-open:open=true
after-open:private-access=true
after-open:private-value=private-ok
```

Agent gọi:

```java
inst.redefineModule(
    secure, Set.of(), Map.of(),
    Map.of("demo.secret", Set.of(agent)),
    Set.of(), Map.of());
```

Kết quả `trySetAccessible()` trả `true`, rồi agent gọi thành công `token()`, dù method này là private. Đây là quyền mạnh hơn export và chỉ nên bổ sung khi chức năng instrument/diagnostic **thật sự cần deep reflection**.

**Một tinh tế:** khi package được **open** tới agent, `secure.isExported("demo.secret", agent)` cũng được coi là `true` ở runtime. Vì thế không thể suy luận “isExported true tức là source descriptor chứa exports”; cần kiểm tra `isOpen` và phân biệt thời điểm/nguồn cấp quyền.

### 7.5. Quyền không lan sang một named module khác

```text
isolation:export-to-helper=false
isolation:open-to-helper=false
isolation:export-unqualified=false
```

Các phép kiểm này xác nhận **`demo.helper` không được nhận export/open** của package `demo.secret`. Package ấy cũng không được export vô điều kiện. Một agent duy nhất được bổ sung quyền theo các `Set.of(agent)` đã chọn.

**Đây là trọng tâm của “bổ sung đúng quan hệ cần thiết”:** kiểm tra cả *positive case* (module được cấp quyền truy cập) lẫn *negative case* (module khác vẫn bị đóng). Chỉ nhìn `isOpen(..., agent)=true` mà không kiểm tra phạm vi có thể che giấu việc mở rộng quá mức.

## 8. Thử thay đổi theo từng yêu cầu thực tế

Không phải agent nào cũng cần cả ba quan hệ. Hãy đối chiếu mục tiêu với quyền tối thiểu:

| Nhu cầu của agent | Quan hệ cần xem xét | Không nên thêm chỉ để tiện |
| --- | --- | --- |
| Chỉ muốn đọc metadata tên lớp/loader do transformer cung cấp | Có thể **không cần sửa module graph** | `extraOpens` tới mọi package |
| Bytecode trong named module A phải gọi helper thuộc named module B | `A` đọc `B`, package helper export về phía A, helper loadable | Open private package của A cho agent nếu không dùng reflection |
| Agent cần gọi **public** method của class ở package chưa exported | Qualified `extraExports` của package về module agent | `extraOpens` nếu public access đã đủ |
| Agent cần đọc private field/method qua reflection | Qualified `extraOpens` tới module thực hiện reflection | Open toàn module hoặc `ALL-UNNAMED` nếu chỉ một module cần |
| Target trong module JDK bị chèn lời gọi bootstrap helper | Tìm hiểu automatic read edges, bootstrap helper visibility và access riêng | `--add-opens java.base/*=ALL-UNNAMED` diện rộng |
| Agent tải helper từ plugin loader cô lập | Class-loader search/delegation, class identity và module access phù hợp | Cho rằng thêm read edge tự làm class xuất hiện |

### 8.1. Chỉ có `extraReads` không cấp phép mọi package

Giả sử bytecode trong `demo.secure` cần gọi `helper.api.Bridge.ping()`. Sau khi `secure.canRead(helper)` là `true`, còn phải kiểm tra:
1. `demo.helper` có package `helper.api` và đã **export** package này về phía `demo.secure` hay chưa?
2. Defining class loader của class trong `demo.secure` có tìm được `helper.api.Bridge` khi JVM resolve symbolic reference không?
3. Lớp `Bridge` và method `ping()` có mức truy cập/descriptor đúng không?
4. Bytecode được chèn có hợp lệ với class file, stack map frames, classloader/module của target hay không?

Trong demo, `demo.helper` export `helper.api` vô điều kiện để loại bỏ một biến số; **thí nghiệm tập trung vào read edge**, không đánh đồng nó với kết quả invocation.

### 8.2. Export và open không có cùng bề mặt quyền

Nếu chỉ cần gọi một public diagnostics method, `extraExports` có phạm vi hẹp hơn `extraOpens`. Open cho phép nhiều thao tác phản chiếu sâu vào các members khác trong cùng package, chứ **không chỉ một method duy nhất**. JPMS không hỗ trợ `opens` theo từng tên method; cấp quyền được thực hiện ở **mức package tới module**.

Nếu nhiều package phải open, xem lại thiết kế agent: có thể thêm một **public bridge API** hoặc instrument tại call site thay vì mở hàng loạt package private. Dù `extraExports` không bị gỡ bằng `redefineModule`, một public bridge được thiết kế rõ cũng có thể giảm phạm vi quyền hơn việc open cả gói.

### 8.3. Tương tác với tự động read edge của Instrumentation

Đặc tả `java.lang.instrument` nói rằng **module chứa lớp được biến đổi** được JVM sắp xếp để đọc unnamed module của **bootstrap class loader** và unnamed module của **class loader nạp lớp agent chính**. Đây là hỗ trợ đặc thù cho bytecode biến đổi gọi helper trong hai unnamed module ấy.

Điều đó **không tự tạo** quan hệ `demo.secure → demo.helper` của bài này, vì `demo.helper` là **named module**. Nó cũng **không tự mở** `demo.secret` để agent có thể deep reflection. Do đó không dùng “JVM đã có automatic read edge” làm lý do bỏ các kiểm tra read/export/open cần thiết khác.

## 9. `--add-reads`, `--add-exports`, `--add-opens` so với `redefineModule`

Khi có quyền cấu hình startup, launcher có các tùy chọn JPMS thường gặp:

```text
--add-reads demo.secure=demo.helper
--add-exports demo.secure/demo.secret=ALL-UNNAMED
--add-opens demo.secure/demo.secret=ALL-UNNAMED
```

Các dòng trên là **minh họa riêng về cú pháp**, không phải khuyến nghị truyền cả ba cùng lúc. Mỗi dòng mở rộng quyền theo mục đích khác nhau:

- `--add-reads`: cho `demo.secure` đọc thêm `demo.helper` khi JVM khởi động.
- `--add-exports`: export package tới mục tiêu; `ALL-UNNAMED` là **mọi unnamed module**, rộng hơn `Set.of(agentModule)` của thí nghiệm.
- `--add-opens`: mở package để deep reflection cho đích; cũng rộng hơn nếu dùng `ALL-UNNAMED`.

Nếu chạy demo **kèm các flags trên**, một số dòng `before:...` có thể là `true` ngay từ đầu, làm mất đối chứng. Để kiểm tra thay đổi bằng `redefineModule`, **không dùng flags cấp sẵn quyền** trong lệnh chạy ở mục 6. Khi thử giải pháp launcher, chạy JVM **mới**, ghi rõ quyền nào đã có từ startup và quyền nào được agent thêm.

Bảng lựa chọn:

| Cách | Thời điểm | Ai kiểm soát? | Điểm cần nhớ |
| --- | --- | --- | --- |
| `module-info.java` | Compile-time descriptor và resolution | Chủ sở hữu module/source | Rõ ràng, versioned; có thể không phù hợp ứng dụng bên thứ ba |
| `--add-reads`/`--add-exports`/`--add-opens` | JVM startup | Launcher/deployment | Tác dụng đã có trước `premain`; `ALL-UNNAMED` rất rộng |
| `Instrumentation.redefineModule` | Runtime sau khi có `Instrumentation` | Agent có quyền thao tác | Có thể grant tới **module object đích cụ thể**; chỉ mở rộng, không rollback |
| `Module.addReads/addExports/addOpens` | Runtime theo caller restrictions | Code trong module sở hữu quan hệ | Không phải API thay thế tùy ý cho agent ngoài module |

**Phân biệt compile-time và runtime:** nếu bạn thêm `import helper.api.Bridge` vào source của `demo.secure` khi descriptor không `requires demo.helper`, `javac` có thể báo package không được module này đọc. Agent sửa graph **lúc chạy** không giúp một chương trình **biên dịch trước đó** vượt qua kiểm tra của compiler; cần khai báo dependency phù hợp hoặc cấu hình compile-time được quản lý riêng.

## 10. Các lỗi hay gặp trong thực nghiệm agent

### 10.1. Sửa sai chiều module graph

Nếu mục tiêu là cho code trong `demo.secure` đọc `demo.helper`, thao tác đúng là:

```java
inst.redefineModule(
    secure, Set.of(helper), Map.of(), Map.of(), Set.of(), Map.of());
```

Không phải gọi `redefineModule(helper, Set.of(secure), ...)`: nó tạo chiều **helper → secure**, khác mục tiêu. Tương tự, khi cần agent truy cập `demo.secret`, export/open phải là **thay đổi trên module chứa package**, tức `secure`, và module đích là **agent**.

### 10.2. Dùng tên package không thuộc module

`extraExports` và `extraOpens` chỉ chấp nhận key package **thuộc module được sửa**. Gọi:

```java
// Ví dụ SAI: helper.api nằm trong demo.helper,
// không nằm trong demo.secure.
inst.redefineModule(
    secure, Set.of(),
    Map.of("helper.api", Set.of(AccessAgent.class.getModule())),
    Map.of(), Set.of(), Map.of());
```

có thể dẫn tới `IllegalArgumentException`. Muốn export package `helper.api` của `demo.helper` (nếu package này chưa export sẵn), cần gọi `redefineModule(helper, ..., extraExports=...)` với package thuộc chính helper. Thí nghiệm đã export `helper.api` trong descriptor nên không cần làm vậy.

### 10.3. Tạo module chưa được resolve vào layer

Có JAR/module trên module path không đủ đảm bảo `ModuleLayer.boot().findModule("demo.helper")` trả kết quả. Trong demo, `--add-modules demo.helper` có mục đích **đảm bảo module được resolve**, để agent lấy object và thêm read edge.

Nếu bỏ `--add-modules demo.helper`, môi trường có thể không resolve helper vì `demo.secure` không khai báo requires; `orElseThrow()` lúc đó dừng startup có chủ đích. Cần xác định module roots/layer đúng, không tự bỏ qua lỗi rồi cấp quyền cho một object không phải module thật.

### 10.4. Nhầm `Class.forName` thành quyền truy cập member

`Class.forName("demo.secret.Hidden", false, loader)` thành công **không chứng minh** public method được phép gọi. Reflection phân biệt việc tìm metadata của type và quyền invocation; `Method.invoke` mới là phép thử được dùng trong bài.

Ngược lại, `ClassNotFoundException` có thể là vấn đề class loader, module chưa được resolve hoặc tên binary sai. Chỉ thêm export/open sẽ không tạo class file hay sửa đường class loading.

### 10.5. Dùng `setAccessible(true)` rồi bỏ qua lỗi

Khi package không open tới module gọi reflection, `setAccessible(true)` có thể ném `InaccessibleObjectException`. Bài dùng `trySetAccessible()` để thu nhận đối chứng `false` rõ ràng. Trong code production, chọn API thích hợp rồi báo lỗi đủ ngữ cảnh, không lén dùng `--add-opens` rộng để “cho hết lỗi”.

### 10.6. Cấp quyền bằng `open module` thay vì qualified opens

Đổi descriptor sang:

```java
open module demo.secure {
}
```

sẽ mở các package ở phạm vi rộng hơn rất nhiều so với grant riêng `demo.secret` cho module của agent. Nó cũng làm thí nghiệm thiếu negative case. Nếu mục tiêu chỉ là một package và một agent, nên giữ module đóng theo mặc định rồi bổ sung đúng quan hệ cần thiết.

### 10.7. Nhầm `isExported` với descriptor nguyên thủy

`Module.isExported("demo.secret", agent)` kiểm tra runtime state; trạng thái có thể thay đổi qua `redefineModule` hoặc flags. Sau khi package được `opens` cho agent, `isExported(..., agent)` có thể là `true` vì **open cũng được coi là export** cho mục đích runtime access.

Nếu cần so sánh với descriptor nguyên thủy, xem `Module.getDescriptor()`, nhưng descriptor không nhất thiết phản ánh những grants động đã được mở rộng tại runtime.

### 10.8. Nghĩ có thể “đóng lại” module sau khi bật probe

`redefineModule` **không cung cấp operation remove export/open/read edge**. Việc tắt transformer hoặc gỡ một probe không hoàn nguyên toàn bộ module graph. Khi quyền cấp ở runtime là một quyết định vận hành quan trọng, hãy thiết kế vòng đời process, phạm vi quyền và restart/rollout phù hợp.

## 11. Chẩn đoán bằng API và exception

| Dấu hiệu | Diễn giải đúng | Bước tiếp theo |
| --- | --- | --- |
| `secure.canRead(helper)=false` | Thiếu read edge đối với cặp module này | Kiểm tra `requires`, resolution, `extraReads` |
| `canRead=true` nhưng code không tìm thấy helper | Read edge không sửa class loader search path | Kiểm tra loader identity, module resolution, helper path |
| `isExported(p, agent)=false` | Package chưa export/open cho agent theo runtime graph | Chỉ grant `extraExports` nếu cần public access |
| `Method.invoke` ném `IllegalAccessException` | Public method vẫn có thể không accessible vì package chưa export hoặc access khác | Kiểm tra class/method modifiers và exports |
| `trySetAccessible=false` | JVM không cho bật deep reflection trong trạng thái hiện tại | Kiểm tra qualified opens, security conditions |
| `InaccessibleObjectException` | `setAccessible(true)` bị từ chối | Cân nhắc `extraOpens` hẹp nếu có nhu cầu thực |
| `isOpen(p, agent)=true` | Package open tới agent, không mặc định open cho module khác | Kiểm tra thêm `isOpen(p, helper)` và `isOpen(p)` |
| `UnmodifiableModuleException` | JVM không cho module đó sửa theo API | Kiểm tra `isModifiableModule` và nền tảng |
| `IllegalArgumentException` ở `redefineModule` | Package key sai, tập module đích rỗng, hoặc input không hợp lệ | Đối chiếu `Module.getPackages()` và API contract |
| `NoClassDefFoundError` / `ClassNotFoundException` | Lỗi nạp/resolution lớp, không tự đồng nghĩa thiếu export | Kiểm tra defining loader, dependency và module graph |
| `IllegalAccessError` trong bytecode đã chèn | Runtime linking/access cho class/method không hợp lệ | Kiểm tra read edge, exports, method visibility, class identity |

Trong log thực tế nên ghi **tên module, tên package, defining class loader, target module và module nhận quyền**. Chỉ lưu một biến `boolean moduleOpen` không đủ, vì một package có thể open tới agent A nhưng không open tới agent B.

### Snippet chẩn đoán tối thiểu

Đoạn dưới đây là **mảnh code trong agent**, giả sử đã có `Module secure`, `Module helper`, `Module agent` như phần thực nghiệm:

```java
System.out.println("secure name=" + secure.getName());
System.out.println("secure loader=" + secure.getClassLoader());
System.out.println("agent named=" + agent.isNamed());
System.out.println("reads helper=" + secure.canRead(helper));
System.out.println("exports to agent="
        + secure.isExported("demo.secret", agent));
System.out.println("opens to agent="
        + secure.isOpen("demo.secret", agent));
System.out.println("opens to helper="
        + secure.isOpen("demo.secret", helper));
System.out.println("package exists="
        + secure.getPackages().contains("demo.secret"));
```

Dùng `isModifiableModule(secure)` và `getPackages()` để giảm sai sót trước khi cấp quyền. Tránh dùng reflection vào package private của ứng dụng trong transformer đang chạy trên đường nạp lớp nếu chưa chuẩn bị phụ thuộc, vì có thể kích hoạt recursive loading hoặc deadlock không cần thiết.

## 12. Mở rộng thực nghiệm có kiểm soát

### Bài tập A: chỉ cấp export mà không open

Chạy bản demo đã cho rồi loại bỏ **bước 3** `extraOpens` (trong một **bản thử riêng**, không phải sửa kết quả Sheet). Bạn phải thấy `after-export:public=public-ok` và `after-export:private-access=false`. Như vậy public API là đủ cho use case public call; không cần deep reflection.

### Bài tập B: chỉ cấp open

Trong một lần chạy JVM mới, bỏ bước 2 `extraExports` và chỉ thực hiện bước 3 `extraOpens`. Dự đoán:
- `secure.isOpen("demo.secret", agent)=true`;
- `secure.isExported("demo.secret", agent)=true` theo runtime API, vì open được xem là export tới cùng module đích;
- public invocation có thể được cho phép và private `trySetAccessible` thành công;
- `isExported("demo.secret")` vẫn `false` nếu chỉ qualified open.

Phải bắt đầu **JVM mới** vì grants từ lần chạy trước không thể bị rút lại trong cùng process.

### Bài tập C: sai chiều `extraReads`

Khởi động JVM mới, thử cấp `helper → secure` thay vì `secure → helper`. So sánh `secure.canRead(helper)` trước/sau. Không kỳ vọng hướng sai làm `secure.canRead(helper)` thành `true`. Đây là phép thử chứng minh đọc module là quan hệ **có hướng**.

### Bài tập D: module thứ ba

Tạo thêm `demo.observer` và kiểm tra `secure.isOpen("demo.secret", observerModule)`. Nếu chỉ cấp cho `agent`, observer vẫn phải bị từ chối. Tránh rút ra kết luận từ `Class.forName` của observer; nên thử public/private method access tương ứng.

### Bài tập E: thực sự instrument một class trong named module

Khi đã hiểu module graph, xây dựng một transformer dùng bytecode library được kiểm chứng để chèn lời gọi helper. Thử **có và không có** read edge/exports hợp lệ, xác minh:
- Class có được nạp/verified không?
- Module chứa lớp được instrument có những automatic read edges nào?
- Helper có đúng defining loader và đúng method descriptor không?
- `NoClassDefFoundError`, `IllegalAccessError`, `VerifyError` đến từ tầng nào?
- Read edge tới named helper có thật sự cần không, hay helper nằm trong unnamed module đã được JVM hỗ trợ?

Bài E là thực nghiệm mở rộng, **không phải code đã thực hiện trong demo độc lập của bài này**.

## 13. Checklist cấp quyền tối thiểu khi triển khai agent

- [ ] Xác định **module nguồn** chứa lớp bị biến đổi hoặc package cần truy cập.
- [ ] Xác định **module đích nhận quyền** bằng chính `Class.getModule()` của code thực hiện thao tác; không chỉ dựa vào tên package.
- [ ] Kiểm tra module cần dùng đã được **resolve vào layer** phù hợp.
- [ ] Kiểm tra `isModifiableModule` và package thực tế trong `getPackages()`.
- [ ] Với lời gọi helper từ bytecode, xác định cần **read** và **export** nào; kiểm tra loader visibility riêng.
- [ ] Nếu chỉ gọi public member, ưu tiên **qualified export** thay vì qualified open.
- [ ] Chỉ dùng **qualified open** khi cần private/deep reflection.
- [ ] Không dùng `ALL-UNNAMED`, `open module` hoặc mở rộng `java.base` nếu một module hẹp là đủ.
- [ ] Kiểm tra trước/sau bằng `canRead`/`isExported`/`isOpen`, cộng phép gọi thực tế.
- [ ] Có **negative control** cho module không được cấp quyền.
- [ ] Ghi phiên bản JVM/agent, loader/module identity và startup flags trong log test.
- [ ] Hiểu rằng grant động **không có thao tác rollback** trong `redefineModule`; chuẩn bị restart khi cần reset graph.
- [ ] Đảm bảo agent JAR đáng tin và chỉ chứa quyền cần thiết cho use case.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `Hidden` là public mà `Method.invoke` vẫn báo `IllegalAccessException` trước khi cấp quyền?
2. `demo.secure.canRead(demo.helper)` thay đổi thế nào sau `extraReads`? Điều đó đã đủ chứng minh một lời gọi `Bridge.ping()` từ bytecode chưa?
3. Tại sao `extraExports` có thể cho public invocation thành công nhưng `trySetAccessible` của private method vẫn `false`?
4. `extraOpens` tới agent tạo thêm quyền gì? Vì sao export/open không nên được đồng nhất?
5. Nếu package đã được open tới agent, `isExported("demo.secret", agent)` có thể trả gì? Vì sao?
6. Vì sao thêm quyền cho `agent` **không tự** export/open package tới `demo.helper`?
7. Điều gì xảy ra nếu key của `extraExports` là `"helper.api"` nhưng module được sửa là `demo.secure`?
8. Vì sao cần `--add-modules demo.helper` dù demo đã có thư mục `out/mods/demo.helper`?
9. `redefineModule` có thể đóng lại một package đã mở sau khi tắt probe không? Nếu không, triển khai nên làm gì?
10. Automatic read edges của `java.lang.instrument` tới unnamed modules có thay thế `extraReads` tới một named module helper không?

## 15. Tài liệu chính thức

- [Java SE 21 — `Instrumentation.redefineModule` và `isModifiableModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng bổ sung reads, exports, opens, uses, provides và không thể giảm quyền.
- [Java SE 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `getPackages`, chi tiết về unnamed/named modules.
- [Java SE 21 — `AccessibleObject.trySetAccessible`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html): phạm vi deep reflection và khác biệt với `setAccessible(true)`.
- [Java SE 21 — `java.lang.instrument`, phần *Instrumenting code in modules*](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): JVM bổ sung automatic readability tới unnamed modules của bootstrap và agent loader khi lớp được instrument.
- [Java SE 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--module-path`, `--module`, `--add-modules`, `--add-reads`, `--add-exports`, `--add-opens`.
