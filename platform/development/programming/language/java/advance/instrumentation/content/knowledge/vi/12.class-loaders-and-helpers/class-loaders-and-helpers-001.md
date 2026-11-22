# Lớp agent được nạp bởi system class loader và thuộc unnamed module

> **Bối cảnh:** Java Advance → Instrumentation → **Class loader và helper**. Theo package specification của `java.lang.instrument`, class trong agent JAR được nạp bởi **system class loader**, và thuộc **unnamed module của system loader**. Đây là hai thuộc tính khác nhau: *defining class loader* quyết định class identity và class visibility; *module membership* tham gia vào quy tắc readability, exports và opens. Bài sử dụng Java 17+, cùng một agent chạy với ứng dụng classpath và named-module, đồng thời chỉ ra hệ quả khi thiết kế helper.

## 1. Phát biểu chính xác từ đặc tả

Trong cơ chế Java instrumentation:

1. JVM dùng agent JAR được khai báo bằng `-javaagent:...` để tìm class theo manifest `Premain-Class`, nạp class agent rồi gọi `premain` **trước** `main` của ứng dụng.
2. Nếu JVM hỗ trợ khởi động agent trong tiến trình đang chạy, manifest dùng `Agent-Class` và JVM gọi `agentmain`. Dù gọi entry point nào, phần mô tả loading trong `java.lang.instrument` quy định các class từ agent JAR thuộc **system loader và unnamed module của loader này**.
3. System class loader **thường** cũng định nghĩa main class của ứng dụng, nhưng ứng dụng có thể chạy với classpath, **named module** hoặc có custom loaders. Không suy ra module của main class chỉ từ việc main class được system loader định nghĩa.
4. Classloader không được đồng nhất với một module duy nhất: một loader có thể định nghĩa class ở unnamed module **và** các named modules. Mỗi `Class<?>` gắn với một `Module` xác định, và trong JVM class identity dựa trên **binary name + defining loader**.

So sánh:

| Class ví dụ | Defining loader | Module |
|---|---|---|
| `demo.agent.ProbeAgent` được nạp bằng `-javaagent` | **system** | **unnamed module của system** |
| `demo.agent.AgentHelper` ở cùng agent JAR, dùng như class bình thường | **system** | **unnamed module của system** |
| `demo.app.LoaderDemo` chạy từ classpath | **system** trong launcher thông thường | **unnamed module của system** |
| `demo.named.NamedMain` chạy từ `-m demo.named/...` | **system** trong ví dụ thử nghiệm | **named module `demo.named`** |
| `java.lang.String` | **bootstrap**, Java API biểu diễn loader bằng `null` | **named module `java.base`** |
| `java.lang.instrument.Instrumentation` | do JDK runtime định nghĩa | **named module `java.instrument`** |

Đặc biệt, việc `ProbeAgent` import `Instrumentation` **không** biến `ProbeAgent` thành thành viên module `java.instrument`. Import/type reference không quyết định module chứa class caller.

## 2. Phân biệt class loader, module, package

**Class loader** trả lời: object nào đã định nghĩa class? Trong Java có:

- **Bootstrap class loader:** tạo class nền tảng; `String.class.getClassLoader() == null` là biểu diễn hợp lệ, không phải lỗi.
- **Platform class loader:** tham gia tải một số platform modules trong JDK hiện đại.
- **System/application class loader:** loader mặc định của ứng dụng classpath và Java instrumentation agent. Có thể lấy bằng `ClassLoader.getSystemClassLoader()`.
- **Custom loaders:** chẳng hạn `URLClassLoader`, plugin loader, application-server loader. Class do chúng định nghĩa không tự động nhìn thấy ngược từ system loader.

**Module** trả lời: class thuộc đơn vị module nào và có các quan hệ read/export/open ra sao?

~~~java
ClassLoader loader = SomeType.class.getClassLoader();
Module module = SomeType.class.getModule();
System.out.println(loader == ClassLoader.getSystemClassLoader());
System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

Đây là **mảnh code trong một class có sẵn `SomeType`**, không phải chương trình độc lập. `module.isNamed() == false` nghĩa là class ở unnamed module; `module.getName() == null`. Một class trong `package demo.agent` vẫn có **named package**, dù module của nó **unnamed**. “Unnamed package” là chuyện khác, chỉ áp dụng khi Java source không khai `package`.

Mỗi class loader có **một unnamed module của riêng nó**. Hai class ở hai loaders cùng có `module.isNamed() == false` chưa chắc thuộc **cùng một `Module` object**. Dùng `moduleA == moduleB` để kiểm tra cùng module; dùng `classA.getClassLoader() == classB.getClassLoader()` để kiểm tra defining loader.

### Readability, exports và opens

- Unnamed module đọc **những modules đã được resolve/observable** trong module graph. Nhưng nó **không tự làm package của named module khác được export/open**.
- **Readability:** module A có thể đọc module B không? Dùng `moduleA.canRead(moduleB)` để chẩn đoán một phần vấn đề.
- **Exports:** package có cho phép dùng public types/members từ module khác không? Chỉ có read edge chưa chắc đủ.
- **Opens:** package có mở cho deep reflection không? Chỉ đọc module hoặc import class chưa đủ để gọi `setAccessible(true)` trên private member của package chưa open.

Vì vậy, agent ở unnamed module có thể dùng public API của `java.instrument` nhưng không tự có quyền deep reflection vào mọi package nội bộ của `java.base` hoặc module ứng dụng. Khi thực sự cần, hãy thiết kế quyền truy cập rõ ràng bằng `--add-modules` (resolve module cần dùng), `--add-exports` (public API package), `--add-opens` (deep reflection), hoặc `Instrumentation.redefineModule(...)` theo điều kiện và phạm vi được cấp phép. Không coi `--add-opens` là biện pháp chung để “chữa mọi lỗi class loader”.

### Sơ đồ minh họa

~~~text
Bootstrap loader (Java API biểu diễn null)
  ├── java.lang.String          -> named module java.base
  │
  └── Platform loader
       │
       └── System loader
            ├── ProbeAgent     -> unnamed module của system
            ├── AgentHelper    -> unnamed module của system
            ├── LoaderDemo     -> unnamed module của system (classpath)
            └── NamedMain      -> named module demo.named
~~~

Đây là sơ đồ **trường hợp launcher JDK điển hình**, không phải cam kết mọi class trong mọi JDK có cùng loader. Điểm chính là **cùng system loader vẫn có thể chứa class ở các module khác nhau**.

## 3. JVM nạp agent và tìm helper như thế nào?

Với lệnh:

~~~bash
java -javaagent:out/probe-agent.jar=demo -cp out/app demo.app.LoaderDemo
~~~

JVM thực hiện chuỗi logic:

~~~text
JVM nhận tùy chọn -javaagent:path.jar[=options]
   └─ đọc META-INF/MANIFEST.MF
      └─ Premain-Class: demo.agent.ProbeAgent
         └─ đưa agent JAR vào cơ chế tra cứu class của system loader
            └─ load ProbeAgent trong unnamed module của system
               └─ gọi static premain("demo", Instrumentation)
                  └─ agent có thể gọi AgentHelper từ cùng agent JAR
                     └─ JVM tiếp tục gọi LoaderDemo.main()
~~~

Agent JAR **không cần** được liệt kê lại trong `-cp` để JVM gọi `premain`. Trong thử nghiệm thông thường, app classpath cũng có thể dùng system loader để **tìm** class agent khi agent JAR đã được hệ thống đưa vào tra cứu. Tuy nhiên không được biến điều này thành một API dependency của business code: khi agent không được bật, class đó sẽ không có; và ứng dụng **named module** vẫn có các ràng buộc về module readability khi liên kết trực tiếp tới unnamed module.

Lưu ý: **khả năng tìm class** không tương đương với **khả năng truy cập loại/method theo module**, và càng không bảo đảm cùng module/classloader nhìn thấy mọi class của plugin loaders.

### Entry point và manifest

Manifest của startup agent cần:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ProbeAgent

~~~

Tên `demo.agent.ProbeAgent` là Java binary name, không phải file path `demo/agent/ProbeAgent.class`. Phương thức được chọn trước tiên:

~~~java
public static void premain(String agentArgs,
                           java.lang.instrument.Instrumentation inst)
~~~

Có overload một tham số `premain(String)` làm fallback theo package specification. Trên đường dynamic agent, entry point là `agentmain` và manifest cần `Agent-Class`; agent JAR có thể khai cả `Premain-Class` và `Agent-Class`. Không cần Attach API trong thí nghiệm này.

## 4. Thực hành Java 17+ — agent class, helper và app classpath

Thử hai lần chạy **không có** và **có** `-javaagent`. Agent và app được compile riêng, để app không có compile-time dependency vào agent.

### 4.1 Cấu trúc dự án

~~~text
agent-loader-lab/
├── manifest.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   ├── ProbeAgent.java
│       │   └── AgentHelper.java
│       └── app/
│           └── LoaderDemo.java
└── out/                        # sinh ra khi build
    ├── agent/
    ├── app/
    └── probe-agent.jar
~~~

Yêu cầu JDK 17+, với lệnh `java`, `javac` và `jar`. Chạy mọi lệnh từ **thư mục gốc `agent-loader-lab/`**.

### 4.2 File `src/demo/agent/ProbeAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class ProbeAgent {
    private ProbeAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("[AGENT] loaderSystem="
                + (ProbeAgent.class.getClassLoader() == system));
        System.out.println("[AGENT] moduleNamed="
                + ProbeAgent.class.getModule().isNamed());
        System.out.println("[AGENT] readsJavaInstrument="
                + ProbeAgent.class.getModule().canRead(
                        Instrumentation.class.getModule()));
        System.out.println("[AGENT] helperSameModule="
                + (ProbeAgent.class.getModule() == AgentHelper.class.getModule()));

        AgentHelper.report();
    }
}
~~~

Ở đây ta so sánh **loader identity** bằng `==` thay vì in tên implementation của loader (ví dụ tên `AppClassLoader` không nên bị hard-code). `getModule().isNamed()` trả `false` cho agent. Tham số `instrumentation` được nhận qua API nhưng chưa dùng để biến đổi bytecode; lớp này chỉ quan sát loader/module.

### 4.3 File `src/demo/agent/AgentHelper.java`

~~~java
package demo.agent;

final class AgentHelper {
    private AgentHelper() {}

    static void report() {
        System.out.println("[HELPER] loaderSystem="
                + (AgentHelper.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));
    }
}
~~~

Helper là class package-private trong **cùng agent JAR**. Nó không được bootstrap loader nạp chỉ vì tên file có chữ “Agent”; JVM dùng class loader mà ProbeAgent có thể nhìn thấy. Không cần khai `Premain-Class` cho helper.

### 4.4 File `src/demo/app/LoaderDemo.java`

~~~java
package demo.app;

public final class LoaderDemo {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("[APP] loaderSystem="
                + (LoaderDemo.class.getClassLoader() == system));
        System.out.println("[APP] moduleNamed="
                + LoaderDemo.class.getModule().isNamed());

        try {
            Class<?> agent = Class.forName(
                    "demo.agent.ProbeAgent", false, system);
            System.out.println("[APP] agentVisible="
                    + (agent.getClassLoader() == system));
        } catch (ClassNotFoundException e) {
            System.out.println("[APP] agentVisible=false");
        }

        System.out.println("[APP] stringLoaderBootstrap="
                + (String.class.getClassLoader() == null));
        System.out.println("[APP] stringModule="
                + String.class.getModule().getName());
    }
}
~~~

App không import `ProbeAgent`. `Class.forName("...", false, system)` kiểm tra hệ thống có thể tìm class theo tên **mà không cố chạy static initializer** chỉ để chẩn đoán. Không được rút ra rằng một named-module caller luôn có read edge tới agent nếu chỉ `Class.forName` thành công.

### 4.5 Manifest và build

Tạo `manifest.mf` với dòng trống kết thúc:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ProbeAgent

~~~

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/demo/agent/ProbeAgent.java src/demo/agent/AgentHelper.java
javac --release 17 -d out/app src/demo/app/LoaderDemo.java
jar --create --file out/probe-agent.jar --manifest manifest.mf -C out/agent .
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/demo/agent/ProbeAgent.java src/demo/agent/AgentHelper.java
javac --release 17 -d out/app src/demo/app/LoaderDemo.java
jar --create --file out/probe-agent.jar --manifest manifest.mf -C out/agent .
~~~

Kiểm tra nội dung JAR:

~~~bash
jar --list --file out/probe-agent.jar
~~~

JAR phải chứa `META-INF/MANIFEST.MF`, `demo/agent/ProbeAgent.class` và `demo/agent/AgentHelper.class`. Ứng dụng được biên dịch độc lập ở `out/app`; không cần đưa `out/agent` vào `-cp` khi chạy.

### 4.6 Chạy không agent

~~~bash
java -cp out/app demo.app.LoaderDemo
~~~

**Stdout đã kiểm chứng khi chạy Java 17 bytecode trên OpenJDK 24:**

~~~text
[APP] loaderSystem=true
[APP] moduleNamed=false
[APP] agentVisible=false
[APP] stringLoaderBootstrap=true
[APP] stringModule=java.base
~~~

Class ứng dụng ở classpath nên thuộc unnamed module của system. Agent JAR không nằm trong classpath và không được kích hoạt, vì vậy `Class.forName` báo `ClassNotFoundException` và app in `agentVisible=false`.

### 4.7 Chạy với startup agent

**macOS/Linux:**

~~~bash
java -javaagent:out/probe-agent.jar=demo -cp out/app demo.app.LoaderDemo
~~~

**Windows PowerShell:**

~~~powershell
java "-javaagent:out/probe-agent.jar=demo" -cp out/app demo.app.LoaderDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
[AGENT] loaderSystem=true
[AGENT] moduleNamed=false
[AGENT] readsJavaInstrument=true
[AGENT] helperSameModule=true
[HELPER] loaderSystem=true
[APP] loaderSystem=true
[APP] moduleNamed=false
[APP] agentVisible=true
[APP] stringLoaderBootstrap=true
[APP] stringModule=java.base
~~~

Bốn nhận xét:

1. Agent chạy trước app nhờ `premain`.
2. Agent class và helper được system loader định nghĩa và có cùng **unnamed module**.
3. Agent module đọc `java.instrument`, nhưng không phải module `java.instrument`.
4. App classpath có thể tìm class của agent bằng system loader, dù `-cp` chỉ ghi `out/app`. Tính khả kiến runtime **không** phải lý do nên để business code phụ thuộc tùy ý vào agent.

Mốc `String.class.getClassLoader() == null` và module `java.base` cũng nhấn mạnh rằng bootstrap loader không đồng nghĩa unnamed module.

## 5. Thực hành Java 17+ — named module vẫn có thể dùng system loader

Mở rộng dự án bằng module app mới:

~~~text
agent-loader-lab/
└── named-src/
    └── demo.named/
        ├── module-info.java
        └── demo/
            └── named/
                └── NamedMain.java
~~~

`named-src/demo.named/module-info.java`:

~~~java
module demo.named { }
~~~

`named-src/demo.named/demo/named/NamedMain.java`:

~~~java
package demo.named;

public final class NamedMain {
    public static void main(String[] args) {
        System.out.println("[NAMED] loaderSystem="
                + (NamedMain.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));
        System.out.println("[NAMED] moduleName="
                + NamedMain.class.getModule().getName());
    }
}
~~~

Biên dịch trên Bash hoặc PowerShell:

~~~bash
javac --release 17 --module-source-path named-src -d out/mods -m demo.named
~~~

**macOS/Linux:**

~~~bash
java -javaagent:out/probe-agent.jar=module --module-path out/mods -m demo.named/demo.named.NamedMain
~~~

**Windows PowerShell:**

~~~powershell
java "-javaagent:out/probe-agent.jar=module" --module-path out/mods -m demo.named/demo.named.NamedMain
~~~

**Stdout đã kiểm chứng:**

~~~text
[AGENT] loaderSystem=true
[AGENT] moduleNamed=false
[AGENT] readsJavaInstrument=true
[AGENT] helperSameModule=true
[HELPER] loaderSystem=true
[NAMED] loaderSystem=true
[NAMED] moduleName=demo.named
~~~

Đây là phản ví dụ rất rõ: `ProbeAgent` và `NamedMain` **cùng system loader**, nhưng **khác module**. Agent ở unnamed module; app ở named module `demo.named`.

Nếu app named module muốn **liên kết trực tiếp** tới API của agent, không thể viết `requires <unnamed>` trong `module-info.java` vì module đó không có tên. Nên thiết kế một **shared API module** có tên phù hợp hoặc cơ chế tích hợp rõ ràng. Việc đã load agent bằng system loader không tự tạo dependency module cho mọi source của ứng dụng.

Đặt JAR bình thường trên **module path** cũng khác với đưa nó vào tùy chọn **`-javaagent`**. Một thư viện đặt trên module path có thể trở thành **automatic named module**, nhưng **agent class** khởi chạy qua Java instrumentation vẫn tuân theo hợp đồng nạp vào **system-loader unnamed module**.

## 6. Helper đặt ở system loader có thể được ai sử dụng?

Một startup agent thường chứa:

- **Agent implementation:** `premain`, transformer, cấu hình, telemetry.
- **System helper:** recorder, formatter, exporter gọi từ agent hoặc từ class target mà system loader có thể resolve.
- **Bootstrap helper:** bridge rất nhỏ được code chèn vào bootstrap-defined class như `java.base` gọi.

Đừng trộn ba lớp vai trò này.

### Agent ở system loader không nhìn thấy mọi classloader khác

Transformer có callback dạng:

~~~java
byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] bytes);
~~~

Đây là **chữ ký tham khảo**, không phải Java code độc lập. Tham số `loader` chỉ **defining loader của target class**, có thể là `null` cho bootstrap, system loader, hoặc custom/plugin loader. Nó **không bắt buộc giống** `ProbeAgent.class.getClassLoader()`.

Ví dụ:

~~~text
ProbeAgent ở system loader
   |
   ├── transform(app class A)         loader = system
   ├── transform(plugin class B)      loader = plugin loader
   └── transform(java.base class C)   loader = null (bootstrap)
~~~

System loader thông thường không tra cứu class đã được một plugin loader con định nghĩa theo chiều ngược. `Class.forName("plugin.Type")` bên trong agent có thể thất bại ngay cả khi plugin Type đang tồn tại. Trong callback, cũng không nên dùng `Class.forName(className)` để tự nạp **chính class đang được transform**: recursive class loading có thể gây `LinkageError`, vòng đợi hoặc deadlock.

### Bootstrap-defined target không tự thấy system-only helper

Nếu transformer thay bytecode của class bootstrap sao cho nó gọi:

~~~text
java.base target class (bootstrap)
   └── lời gọi tới demo.agent.AgentHelper (chỉ ở system loader)
       └── bootstrap loader không tìm ngược xuống system loader
           └── NoClassDefFoundError / linkage failure
~~~

Đây là vấn đề **classloader visibility**, không tự được giải quyết vì agent thuộc unnamed module hoặc agent chạy trước `main`. Đặt helper ở system loader là đủ với một số mục tiêu, nhưng **không đủ** cho mọi bootstrap class.

### Bootstrap helper phải bố trí riêng

Java Instrumentation có:

- Manifest `Boot-Class-Path` với các đường dẫn tìm kiếm được bootstrap loader bổ sung.
- `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` để agent thêm JAR vào tìm kiếm của bootstrap loader.

Mảnh **minh họa trong agent đã có biến `inst`**, không phải file độc lập:

~~~java
import java.util.jar.JarFile;

inst.appendToBootstrapClassLoaderSearch(
        new JarFile("/absolute/path/bootstrap-helper.jar"));
~~~

Các quy tắc quan trọng:

1. Chỉ đưa helper tối thiểu thật sự được bootstrap định nghĩa vào JAR đó, trong **package có tên duy nhất**, không trùng tên class của ứng dụng.
2. Bootstrap helper chỉ được link tới các class mà **bootstrap loader định nghĩa được**. Đừng cho nó phụ thuộc trực tiếp implementation của agent chỉ có ở system loader.
3. Bootstrap helper ở **unnamed module của bootstrap loader**, không phải unnamed module của system loader. Hai unnamed module này **không cùng object**.
4. Append JAR không tự redefine class đã load. Nếu JVM đã từng resolution thất bại với một symbolic reference, việc thêm class file muộn **không bảo đảm** lần resolve sau thành công theo JVMS.
5. Dùng bootstrap injection có kiểm soát, không đưa cả agent JAR/dependencies không cần thiết vào bootstrap search. Dễ tạo xung đột class/resource và lỗi `IllegalAccessError` khó chẩn đoán.

### `appendToSystemClassLoaderSearch` là API khác

~~~java
inst.appendToSystemClassLoaderSearch(
        new JarFile("/absolute/path/system-helper.jar"));
~~~

API này thêm JAR vào **system loader search**, không phải bootstrap loader. Theo Javadoc nó **không thay đổi property `java.class.path`**. Một custom system loader phải hỗ trợ method `appendToClassPathForInstrumentation(String)` để JVM bổ sung được agent JAR/helper JAR; nếu không, `appendToSystemClassLoaderSearch` có thể ném `UnsupportedOperationException` hoặc việc startup agent gặp lỗi.

Khi chạy với custom system loader (chẳng hạn cấu hình `-Djava.system.class.loader=...`), không nên hard-code tên class implementation `AppClassLoader`; hãy dùng identity check và kiểm tra đúng hành vi `appendToClassPathForInstrumentation`.

## 7. JPMS: agent unnamed module không có nghĩa được mở mọi package

Có ba câu hỏi độc lập:

1. **Agent load ở đâu?** System class loader / unnamed module của nó.
2. **Code đã được instrument có resolve được helper?** Phụ thuộc defining loader của target và nơi helper được bố trí.
3. **Agent có truy cập/reflection vào các class trong named module khác không?** Phụ thuộc module readability, package exports/opens và Java access controls.

Java instrumentation package specification có một hỗ trợ đáng chú ý: JVM **sắp xếp cho module của class được transform đọc unnamed module của bootstrap loader và unnamed module của loader chứa main agent class**. Read edge này giúp những class đã instrument tham chiếu helper trong các unnamed modules liên quan. Tuy nhiên:

- Readability **không** khiến bootstrap loader nhìn xuống system loader; helper vẫn phải ở nơi target loader resolve được.
- Readability **không** tự mở private package của named module cho agent dùng deep reflection.
- Một named-module application không được suy ra đã có read edge tới agent chỉ vì có agent JAR. Phân biệt những class thực sự được transformer xử lý với class app khác.
- Agent trong unnamed module có thể đọc các modules đã resolve, **không** có nghĩa mọi module đang có trong runtime image đều đã được đưa vào boot layer. Nếu cần module JDK tùy chọn, có thể phải dùng `--add-modules`.

Nếu reflective access thực sự cần thiết, dùng cách được thiết kế rõ (cấu hình `opens`, `--add-opens` hoặc `Instrumentation.redefineModule`), tránh mở quá rộng mà không có yêu cầu.

## 8. Chẩn đoán lỗi classloader và module

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| JVM dừng trước `main` vì không tìm thấy agent | Sai JAR/manifest/`Premain-Class` | Dùng `jar --list --file ...`, xác minh binary name và `public static premain` |
| Agent chạy nhưng không tìm thấy plugin class | Plugin được custom loader định nghĩa; system loader không nhìn xuống | Log `type.getClassLoader()`/loader trong transformer |
| Class bootstrap sau khi instrument bị `NoClassDefFoundError` | Bytecode gọi helper chỉ nằm ở system loader | Bố trí bootstrap helper tối thiểu, xem module/visibility |
| Helper nạp rồi nhưng báo `IllegalAccessError` | Sai Java/module/package access hoặc class identity | Kiểm tra modifiers, loader, module exports/opens |
| Reflection ném `InaccessibleObjectException` | Named module không open package cho agent | Xem `--add-opens` hoặc `redefineModule` đúng phạm vi |
| App module ở system loader nhưng `isNamed() == true` | App được chạy bằng named module | Đây là hành vi hợp lệ; xem `getModule().getName()` |
| `Class.forName(...)` thất bại dù JAR đã append | Wrong loader, class đã resolve thất bại, tên sai, hoặc JAR chưa vào đúng search | Xác minh tên, launcher, load order và API append |
| `ClassCastException` giữa type cùng tên | Defining loaders khác tạo class identities khác | In cả binary name, defining loader và module |
| Agent không thấy một module JDK | Module không được resolve vào graph hiện tại | Kiểm tra `--add-modules`, runtime image và boot layer |
| Custom system loader khiến agent/startup lỗi | Loader không hỗ trợ instrumentation appending | Kiểm tra `java.system.class.loader` và `appendToClassPathForInstrumentation` |
| Helper JAR được append nhưng property classpath không đổi | API append không sửa `java.class.path` | Kiểm tra tìm class thực tế, không chỉ property text |

**Những ngộ nhận cần tránh:** “System loader luôn tương đương unnamed module” (sai), “Agent ở system loader nên bootstrap class tự gọi được helper” (sai), “Unnnamed module cho phép reflection tất cả packages” (sai), và “được instrument class ở custom loader nghĩa là agent có thể `Class.forName` bất kỳ class của loader ấy” (sai).

## 9. Câu hỏi tự kiểm tra

1. **Agent JAR nạp qua `-javaagent` nằm ở loader/module nào?** System class loader, **unnamed module của loader đó**.
2. **Class của ứng dụng được system loader định nghĩa có nhất thiết thuộc unnamed module không?** Không. Named app module có thể được cùng loader định nghĩa.
3. **`ProbeAgent.class.getModule().getName()` thường trả gì?** `null` vì unnamed module; `module.isNamed() == false`.
4. **`Instrumentation.class.getModule().getName()` trả gì?** `java.instrument`; không phải tên module của agent.
5. **Bootstrap-defined class có `getClassLoader()` bằng gì?** `null` trong Java API; điều đó không có nghĩa module của nó unnamed.
6. **Agent và app cùng unnamed module có nghĩa app buộc phải import agent không?** Không. Tốt nhất business app không phụ thuộc trực tiếp agent.
7. **Helper từ cùng agent JAR có tự động được bootstrap loader nạp không?** Không. Helper bình thường nằm ở system loader; muốn bootstrap helper cần cơ chế tìm kiếm riêng.
8. **Named module của target có đọc được agent unnamed module sau khi được transform không?** Instrumentation có cơ chế bổ sung read edge cho module của transformed classes; vẫn phải xét classloader visibility và exports/opens.
9. **Muốn deep reflection vào private field của named module có chỉ cần `canRead == true` không?** Không. Phải bảo đảm package open và access rules.
10. **System loader có tự nhìn xuống plugin loader con không?** Không theo parent delegation thông thường.
11. **Tại sao hai class cùng tên ở hai loader khác nhau không cast qua lại được?** Chúng là hai class identities khác nhau.
12. **Khi append JAR vào system search, `java.class.path` có luôn được sửa không?** Không; `appendToSystemClassLoaderSearch` không sửa property đó.

## 10. Checklist cho agent triển khai thật

- [ ] Manifest đúng `Premain-Class` / `Agent-Class` và các entry point được hỗ trợ.
- [ ] Xác minh loader bằng `== ClassLoader.getSystemClassLoader()`, module bằng `getModule().isNamed()`.
- [ ] Phân biệt named vs unnamed **module**, không dựa vào tên `ClassLoader` hay package.
- [ ] Đặt agent implementation/system helper và bootstrap helper ở đúng loader.
- [ ] Bootstrap helper tối thiểu, không link ngược vào code system-only.
- [ ] Không phụ thuộc vào agent JAR từ business code một cách vô tình.
- [ ] Với transformer, phân biệt defining loader của target và loader của agent.
- [ ] Xem riêng readability, exports, opens và classloader lookup khi có `IllegalAccessError`/`NoClassDefFoundError`.
- [ ] Kiểm tra custom system loader và `appendToClassPathForInstrumentation` khi runtime dùng cấu hình đặc biệt.
- [ ] Không xem property `java.class.path` là toàn bộ runtime search path.
- [ ] Có thử nghiệm với classpath app, named module và bootstrap target nếu agent hỗ trợ chúng.
- [ ] Dùng packages riêng và quản lý class name collisions/dependencies.

## Tài liệu chính thức

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): loading agent classes, system loader/unnamed module, tính nhìn thấy class, bootstrap helper và module reads cho transformed classes.
- [Java SE 21 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, `redefineModule`.
- [Java SE 21 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): system/parent/bootstrap loaders, custom loader.
- [JLS 21 — §7.7.5 Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.5): module readability, exports/opens và module không có tên.
- [Dev.java — Unnamed Module](https://dev.java/learn/organizing/modules/unnamed-module/): quan hệ giữa classpath và unnamed module.
- [Dev.java — `--add-exports` và `--add-opens`](https://dev.java/learn/organizing/modules/add-exports-opens/): phân biệt visibility của public API và deep reflection.
