# Instrumentation — Khai báo khả năng Java agent qua JAR manifest

## Mục tiêu và phạm vi

Java Instrumentation API (`java.lang.instrument`) cho phép một Java agent quan sát hoặc biến đổi bytecode ở thời điểm class được load, hoặc tác động tới một số class đã load khi JVM và agent được cấp khả năng thích hợp. **Khả năng đó không được suy ra chỉ từ việc có method `premain` hoặc `agentmain`**. Java agent thường phân phối dưới dạng **agent JAR**, và **main section** của file `META-INF/MANIFEST.MF` khai báo **điểm vào** cùng các **capability requests**.

Bài này tập trung đúng câu hỏi: **Khai báo agent qua manifest thế nào, các cờ `Can-*` có ý nghĩa gì, JVM khởi động kiểu nào, kiểm chứng khả năng thực tế ra sao?** Nội dung phục vụ Java 17+ và đối chiếu với **Java SE/JDK 26** đang được tài liệu chính thức duy trì.

Sau bài học, bạn có thể:
1. Phân biệt `Premain-Class`, `Agent-Class` và `Launcher-Agent-Class`. Chọn đúng loại cho `-javaagent`, agent nạp sau startup, hoặc executable JAR chạy với `java -jar`.
2. Hiểu ba quyền khai báo `Can-Redefine-Classes`, `Can-Retransform-Classes`, `Can-Set-Native-Method-Prefix`, mặc định `false` và các giới hạn JVM.
3. Biết `Can-*` là **yêu cầu capability** chứ không phải lời hứa “mọi class đều sửa được”; phải hỏi `Instrumentation` runtime.
4. Đọc `Boot-Class-Path` đúng ngữ cảnh và phân biệt nó với `Class-Path`/`Main-Class`/module path.
5. Viết đúng `public static void premain(String, Instrumentation)` và `public static void agentmain(String, Instrumentation)`; hiểu cách JVM truyền nguyên chuỗi agent options.
6. Dùng `jar --create --manifest` để đóng gói JAR, kiểm tra mọi generated `.class`, `jar --list`, `JarFile.getManifest()`.
7. Kiểm chứng bằng **Java 17+ thực chạy trên OpenJDK 24**: baseline không agent, manifest tối thiểu, manifest bật ba `Can-*`, `Launcher-Agent-Class`, và negative test thiếu `Premain-Class`.
8. Biết agent có thể tự đăng ký một `ClassFileTransformer` retransformation-capable nếu khả năng và JVM cho phép; không dùng bytecode biến đổi bừa bãi trong ví dụ cơ bản.
9. Kiểm thử `Agent-Class` bằng một **JVM con do mình khởi chạy** với explicit `-XX:+EnableDynamicAgentLoading`, không tự attach lén vào ứng dụng khác.
10. Hiểu JEP 451 (JDK 21+) và các cảnh báo dynamic agent loading; ưu tiên startup `-javaagent` cho app/tooling do bạn sở hữu.
11. Chẩn đoán đúng “Failed to find Premain-Class”, class not found, thiếu inner class, flags không đúng, manifest line folding, dynamic attach bị policy từ chối, và module visibility.
12. Vận hành agent theo nguyên tắc **least privilege**: cấp đúng capability cần, xác minh nguồn JAR, kiểm soát bytecode mutation, tài liệu hóa thay đổi cấu hình và rollback.

**Special Note áp dụng:** Chỉ trình bày kiến thức còn hiệu lực hiện nay. Các APIs `Instrumentation`/`ClassFileTransformer`, manifest agent attributes, `jar`/`JarFile`, `jdk.attach` hiện vẫn được đặc tả trong JDK 26. Không dùng `sun.misc.Unsafe`, `sun.instrument.*` hoặc hướng dẫn vượt quyền một target process. Dynamic attach là khả năng được kiểm soát bằng chính sách JVM và quyền sở hữu tiến trình; không dùng như biện pháp né security restrictions.

## 1. Agent manifest là hợp đồng giữa agent JAR và launcher

Trong một agent JAR thông thường:

```text
agent-capable.jar
├── META-INF/
│   └── MANIFEST.MF
├── AgentManifestDemo.class
├── AgentManifestDemo$1.class
└── AgentManifestApp.class
```

Manifest thuộc **main section**:

```text
Manifest-Version: 1.0
Premain-Class: AgentManifestDemo
Agent-Class: AgentManifestDemo
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

```

Đây là một **ví dụ test** có tên class ở **default package** để copy vào thư mục nhỏ được dễ. Trong ứng dụng thật nên dùng package có namespace rõ ràng, ví dụ `com.example.telemetry.Agent`, và manifest dùng **binary class name** `com.example.telemetry.Agent`, không thêm đuôi `.class` hay đường dẫn file. Nếu class lồng cần khai báo thì dùng Java binary name có `$` đúng quy ước, không dùng source notation tùy tiện.

**Không** phải mọi attribute trong manifest đều dành riêng cho Java agent. `Main-Class` dùng với executable app JAR; `Class-Path` dùng cho JAR dependency search path; ba `Can-*` mới là những khả năng optional của Instrumentation agent.

### 1.1. Main section và quy tắc cú pháp

Theo JAR File Specification hiện hành:
- File manifest nằm ở `META-INF/MANIFEST.MF`.
- Header dạng `Name: value`: có dấu hai chấm rồi **một khoảng trắng** trước value.
- `Manifest-Version: 1.0` là header bắt đầu của manifest theo quy cách thông thường.
- Main section kết thúc bằng **dòng trống**. Các sections bổ sung cho từng entry dùng `Name: ...` khác, **không** dùng để khai báo `Premain-Class` của toàn JAR.
- Mỗi header line không vượt **72 bytes UTF-8**, không phải 72 Unicode characters. Value dài được nối dòng theo JAR continuation convention với dòng tiếp theo bắt đầu bằng một khoảng trắng.
- Tên manifest attributes không phân biệt chữ hoa/thường về mặt parser, nhưng nên dùng đúng tên chuẩn (`Premain-Class`, `Can-Retransform-Classes`,...) để dễ review.
- Không lặp một header trong cùng section.
- Dòng kết thúc có thể `LF` hoặc `CRLF` theo spec. Tạo bằng công cụ `jar` sẽ bảo đảm cấu trúc JAR/manifest được chuẩn hóa; nếu tạo file thủ công, tránh BOM/encoding không mong đợi và bảo đảm dòng kết thúc.
- Không đặt secret, API key hoặc dữ liệu cá nhân vào agent options hay manifest: người có quyền đọc JAR/command line có thể thấy chúng.

Với Java source, tên JAR không tự quyết định điểm vào. JVM **đọc giá trị bên trong manifest**. Bạn có thể có `my-agent.jar` nhưng thiếu `Premain-Class` thì `-javaagent:my-agent.jar` vẫn bị từ chối.

## 2. Ba điểm vào agent phải phân biệt rõ

| Manifest attribute | Cách khởi động | Callback Java | Thời điểm callback | Agent options |
| --- | --- | --- | --- | --- |
| `Premain-Class` | JVM option `-javaagent:path/to/agent.jar[=args]` | `premain(String, Instrumentation)` | Trước application `main` | Chuỗi nguyên dạng từ `=args` |
| `Agent-Class` | Nạp agent vào JVM **đang chạy**, nếu implementation/policy cho phép | `agentmain(String, Instrumentation)` | Sau JVM startup, khi yêu cầu loadAgent | Chuỗi do attach caller cung cấp |
| `Launcher-Agent-Class` | `java -jar app-bundled.jar` khi agent đóng **chung executable JAR** | `agentmain(String, Instrumentation)` | Trước application `main` | **Chuỗi rỗng** |

**Quan trọng:** `Launcher-Agent-Class` gọi **`agentmain`**, nhưng được launcher thực thi lúc startup, không phải hành động dùng Attach API nạp vào JVM đang chạy. Đây là một cơ chế khác với `Agent-Class` dù tên callback giống nhau.

### 2.1. Luồng startup -javaagent

```text
java -javaagent:agent-minimal.jar=profile=basic -cp out AgentManifestApp
          |
          v
JVM đọc META-INF/MANIFEST.MF trong agent-minimal.jar
          |
          v
Đọc Premain-Class -> tải AgentManifestDemo
          |
          v
AgentManifestDemo.premain("profile=basic", inst)
          |
          v
AgentManifestApp.main(args)
```

`Agent-Class` (nếu cùng hiện diện trong JAR này) **bị bỏ qua trong trường hợp -javaagent**. JVM thử method `premain(String, Instrumentation)` trước; nếu không có mới thử `premain(String)`. Nên chọn bản **có `Instrumentation`** để kiểm tra và dùng capabilities.

Nếu agent class không load được, không có `premain` hợp lệ hoặc `premain` ném lỗi không được xử lý, JVM **abort startup**, application main **không được gọi**. Lỗi khởi động phải được coi là lỗi deployment, không ép app chạy bằng cách xóa kiểm tra manifest.

### 2.2. Luồng agent dynamic attach

```text
Application JVM đã chạy main
          |
          | Có quyền + attach policy cho phép
          v
Một serviceability tool / Attach API thực hiện loadAgent(jar, options)
          |
          v
JVM đích đọc Agent-Class từ agent JAR
          |
          v
AgentManifestDemo.agentmain(options, inst)
          |
          v
JVM đích tiếp tục chạy ứng dụng
```

`Premain-Class` **bị bỏ qua** khi dynamic load. Điều kiện có `Agent-Class` không có nghĩa cơ chế attach tự động được bật: implementation, target JVM options, PID/OS/user permissions, container policy và khả năng attach provider phải thỏa mãn. Xem mục 9 về JEP 451 và test subprocess.

Với dynamic load, nếu agent không start được hoặc `agentmain` ném lỗi không bắt, JVM đang chạy thường **không bị abort**, nhưng lỗi có thể được log/báo cho attach caller; cần xử lý điều này như một lỗi vận hành nghiêm trọng. Không nên tự động reload agent lặp vô hạn.

### 2.3. Luồng Launcher-Agent-Class trong executable JAR

```text
java -jar app-bundled.jar
          |
          v
JVM đọc Main-Class + Launcher-Agent-Class
          |
          v
AgentManifestDemo.agentmain("", inst)
          |
          v
AgentManifestApp.main(args)
```

`Launcher-Agent-Class` chỉ có ý nghĩa khi **agent class được đóng cùng executable JAR** hỗ trợ `java -jar`. Nếu startup of bundled agent thất bại, JVM abort trước application main. `Launcher-Agent-Class` không thay thế `Premain-Class` khi người dùng viết `-javaagent:jar`.

Trong ví dụ dưới đây, tất cả `.class` cần thiết được đóng cùng executable JAR; nếu quên inner class sinh bởi anonymous transformer, JVM có thể ném `NoClassDefFoundError` ngay trước main.

### 2.4. Có cả hai Premain-Class và Agent-Class được không?

**Có.** Một agent JAR có thể khai báo đồng thời:

```text
Premain-Class: AgentManifestDemo
Agent-Class: AgentManifestDemo
```

- `-javaagent`: chỉ chọn `Premain-Class` và method `premain`.
- Dynamic load: chỉ chọn `Agent-Class` và method `agentmain`.
- Nếu muốn cùng Java class nhận cả hai, class đó cần implement **cả hai callbacks**.
- Không phải vì khai báo cả hai mà agent “tự nạp hai lần”; việc gọi callback phụ thuộc cách bắt đầu.
- Nếu một application vừa có external `-javaagent` vừa có bundled `Launcher-Agent-Class`, hai callbacks có thể được gọi, và code cần bảo vệ chống đăng ký transformer hai lần. Đó là configuration riêng, không phải happy path mặc định.

## 3. Ba manifest capability flags: nội dung chính của bài

Ba flags sau **nằm trong main manifest** của agent JAR. Chúng là các thuộc tính Boolean được JVM đọc tại thời điểm agent được khởi động.

| Manifest attribute | Mục đích yêu cầu | Kiểm tra runtime | Ví dụ API |
| --- | --- | --- | --- |
| `Can-Redefine-Classes: true` | Cho phép agent yêu cầu định nghĩa lại class đã load | `inst.isRedefineClassesSupported()` | `redefineClasses(ClassDefinition...)` |
| `Can-Retransform-Classes: true` | Cho phép agent retransform class đã load | `inst.isRetransformClassesSupported()` | `addTransformer(transformer, true)`, `retransformClasses(...)` |
| `Can-Set-Native-Method-Prefix: true` | Cho phép một cơ chế đổi prefix tìm native method cho instrumentation | `inst.isNativeMethodPrefixSupported()` | `setNativeMethodPrefix(...)` |

**Default của cả ba là `false` nếu attribute không có.** Giá trị `true` không phân biệt chữ hoa/thường; các giá trị không phải `true` được tính như `false` theo package specification. Nếu khai báo `false`, bạn chủ động không xin capability ấy.

### 3.1. Hai điều kiện cho một khả năng

```text
Khai báo Can-Retransform-Classes: true
                    AND
JVM thực hiện support retransformation
                    |
                    v
inst.isRetransformClassesSupported() == true
                    |
                    v
Một class cụ thể còn phải modifiable
                    |
                    v
Có thể thử addTransformer(..., true) / retransformClasses(...)
                    |
                    v
Transform thực tế vẫn có thể fail do class format, security,
VM limits hoặc unsupported schema changes
```

**Khai báo không tạo ra khả năng mới cho JVM.** Ví dụ `Can-Redefine-Classes: true` nhưng VM không hỗ trợ class redefinition thì `isRedefineClassesSupported()` vẫn có thể `false`. Ngay cả khi method này `true`, `inst.isModifiableClass(targetClass)` vẫn có thể `false` cho một class cụ thể. `ClassDefinition` không được dùng để thay đổi tùy ý class hierarchy/fields theo mọi VM implementation.

Không lấy việc `isRetransformClassesSupported()==true` làm bằng chứng transformer đã biến đổi thành công class. Phải xử lý lỗi `UnmodifiableClassException`, `UnsupportedOperationException` và kiểm thử behavior riêng.

### 3.2. Can-Redefine-Classes

`Redefinition` cài đặt class bytes mới cho các classes đã được load, thông qua `ClassDefinition`. Nhiều giới hạn của JVMTI/JVM vẫn áp dụng; không được tự ý thêm/xóa methods/fields hoặc đổi superclass/interface nếu VM không hỗ trợ. Redefinition có thể ảnh hưởng behavior trên **future method invocations**; active stack frames có thể vẫn chạy bytecode cũ.

Nếu agent chỉ quan sát class load mới và không bao giờ dùng `redefineClasses`, đừng xin quyền này. Nếu thực sự cần, manifest:

```text
Can-Redefine-Classes: true
```

Khi chạy, hỏi `inst.isRedefineClassesSupported()` rồi với target cụ thể hỏi `inst.isModifiableClass(target)` trước. Đừng viết agent tuyên bố “có toàn quyền hot swap” chỉ vì flag true.

### 3.3. Can-Retransform-Classes

`Retransformation` cho phép chạy lại processing pipeline của `ClassFileTransformer` với class đã load. Manifest:

```text
Can-Retransform-Classes: true
```

Phải có JVM hỗ trợ. `inst.addTransformer(transformer, true)` đăng ký transformer có thể được gọi khi retransform. Nếu capability không khả dụng, API có thể ném `UnsupportedOperationException`. Ví dụ hoàn chỉnh kiểm tra behavior thật: đăng ký **no-op ClassFileTransformer** với `true`, gỡ ngay bằng `removeTransformer`, đối chiếu có thành công với `isRetransformClassesSupported()` hay không.

Lưu ý:
- `addTransformer(transformer)` tương đương `addTransformer(transformer, false)`; để observe new class loading không nhất thiết phải xin retransformation.
- `new ClassFileTransformer() {}` là lựa chọn đúng cho một no-op transformer trong Java 17+ vì interface dùng default methods, **không phải functional interface**, không dùng lambda.
- Khi transformer trả `null`, JVM hiểu **không biến đổi class bytes**. Đây là cách test đăng ký capability mà không can thiệp ứng dụng.
- Việc transformer được gỡ không đảm bảo không còn callback đang chạy đồng thời; production transformer phải thread-safe.
- `Can-Retransform-Classes: true` không phải `Can-Redefine-Classes: true`; hai quyền độc lập.

### 3.4. Can-Set-Native-Method-Prefix

Đây là capability phục vụ instrumenting native method resolution: có thể yêu cầu JVM tìm phương thức native bằng một prefix thay thế trong những tình huống chuyên biệt. Manifest:

```text
Can-Set-Native-Method-Prefix: true
```

Nó **không** tự đổi JNI library search path, không tự load native library và không phải một giải pháp để bỏ security checks của native access. Nếu không implement transformer/naming strategy dành cho mục đích này, **đừng khai báo true**. Ví dụ chỉ đọc `inst.isNativeMethodPrefixSupported()`, không tác động tới native linking.

### 3.5. “Manifest says true” chưa đủ

Một script test có thể đọc:

```java
String flag = jar.getManifest().getMainAttributes()
        .getValue("Can-Retransform-Classes");
```

Nếu `flag.equals("true")`, đó chỉ chứng minh file đang **khai báo**. Nó không chứng minh target JVM thực sự hỗ trợ. Phải so cả **hai lớp bằng chứng**:

1. **Artifact-level:** `JarFile` đọc được manifest attrs.
2. **Runtime-level:** `Instrumentation.isRetransformClassesSupported()` và thử thao tác có kiểm soát.

Bài runnable có cả hai.

### 3.6. Nên xin ba cờ true luôn cho “chắc” không?

Không. Đó là các quyền instrumentation mạnh, tác động tới class bytecode và độ ổn định. Chỉ bật capability phục vụ use case được owner hệ thống chấp nhận; có test, log/audit và rollback. Với agent quan sát startup class loading đơn giản, chỉ có `Premain-Class` có thể đã đủ. Không bật cả ba cờ theo một “template chuẩn bắt buộc”.

## 4. Manifest attributes khác liên quan đến Java agent

### 4.1. Boot-Class-Path

`Boot-Class-Path` là optional manifest attribute cho agent, chỉ định một danh sách **đường dẫn helper JAR/directory** cho bootstrap class loader search path, cách nhau bằng spaces. Relative paths được giải thích tương đối so với **vị trí agent JAR** theo URI path syntax; invalid/nonexistent entries có thể bị bỏ qua. Khi agent nạp **sau JVM startup**, những entries không chỉ đến JAR files có thể bị bỏ qua theo spec.

```text
Boot-Class-Path: lib/agent-bootstrap-helper.jar
```

Chỉ dùng nếu agent thực sự cần bootstrap-visible supporting classes; các classes được bootstrap loader load phải chỉ link tới các classes khả dụng ở bootstrap loader. Nó **không** tương đương:
- `Class-Path`: library/application class path search.
- `--module-path`: module resolution trong Java module system.
- `--add-opens`: mở packages cho deep reflection.
- `--add-exports`: bổ sung module exports.
- `Premain-Class`: tên class để JVM gọi agent callback.

Đừng thêm helper JAR vào `Boot-Class-Path` chỉ vì bị `ClassNotFoundException`; hãy kiểm tra classloader/module visibility và packaging thực tế trước. Nếu phụ thuộc application classes, bootstrap loading có thể sai mô hình hoàn toàn.

### 4.2. Main-Class không kích hoạt agent từ -javaagent

`Main-Class` nói cho `java -jar` biết application `main` ở đâu. Nó **không** làm một JAR thành Java agent. Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: AgentManifestApp

```

JAR như vậy chạy được `java -jar ...` nếu class tồn tại, nhưng `-javaagent:...` vẫn cần `Premain-Class`. Tương tự, `Agent-Class` một mình không làm `-javaagent` hoạt động.

### 4.3. Agent options không phải manifest attribute

Với command:

```bash
java -javaagent:agent-capable.jar=profile=full -cp out AgentManifestApp
```

`profile=full` được truyền **nguyên chuỗi** vào `premain(String agentArgs, Instrumentation inst)`. JVM không tự parse nó thành map hoặc tự đọc `agent.options` từ manifest. Nếu options chứa dấu bằng/phẩy/khoảng trắng, agent phải có parser và quoting hợp lệ. Tránh đưa secrets vào options do process command line có thể bị xem bằng tooling OS.

### 4.4. Module boundaries và visibility

`java.lang.instrument` nằm trong **module `java.instrument`**. Nếu agent code được biên dịch dạng named module tự định nghĩa, thêm `requires java.instrument;` trong `module-info.java`. Tuy nhiên agent classes được JVM thường load bởi **system class loader** vào **unnamed module** từ agent JAR, nên hành vi class loading/module visibility không giống đẩy mọi class lên module path.

Một file agent có thể cần nhìn application classes trong named modules; không tự sử dụng `setAccessible(true)` vượt qua strong encapsulation. Nếu thật sự cần mở/export, đánh giá cách cấu hình `--add-opens`/`--add-exports` do owner JVM cho phép hoặc `Instrumentation.redefineModule` khi phù hợp; đây là các thay đổi có ý nghĩa bảo mật, không có một manifest `Can-Open-Everything` thần kỳ.

### 4.5. Class-Path và generated inner classes

Trong ví dụ Java bên dưới, `new ClassFileTransformer() {}` tạo ra `AgentManifestDemo$1.class`. Nếu đóng agent chỉ với `AgentManifestDemo.class` mà bỏ file sinh thêm, có thể nhận `NoClassDefFoundError: AgentManifestDemo$1`. Bài test thực đã phát hiện case này rồi sửa lệnh build:

```bash
jar --create --file agent-minimal.jar --manifest minimal.mf -C out .
```

`-C out .` đưa các compiled classes cần thiết từ thư mục `out` vào JAR. Trong dự án thật, nên kiểm soát artifact contents qua build tool, dependency shading/relocation nếu cần và `jar --list --file agent-minimal.jar` để xác nhận trước khi deploy.

## 5. Ví dụ Java 17+ đầy đủ: một agent, hai callback, kiểm thử ba manifest

### 5.1. Cấu trúc thư mục

Tạo một thư mục demo **mới**, không dùng thư mục chứa JAR deployment thực:

```text
agent-manifest-demo/
  AgentManifestDemo.java
  minimal.mf
  capable.mf
  launcher.mf
  agent-only.mf
  out/
  agent-minimal.jar       (sinh bởi jar)
  agent-capable.jar       (sinh bởi jar)
  app-bundled.jar         (sinh bởi jar)
  agent-only.jar          (sinh bởi jar)
```

Mỗi manifest là **một file riêng**. Không dán bốn manifests vào cùng một `MANIFEST.MF` và không viết literal các ghi chú “(sinh bởi jar)” vào shell command. Code dưới đây sử dụng một public class `AgentManifestDemo` và một package-private class `AgentManifestApp` **trong cùng file source**, nên `javac` sinh nhiều `.class` files.

### 5.2. Toàn bộ `AgentManifestDemo.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

public final class AgentManifestDemo {
    private static void report(String entry, String args, Instrumentation inst) {
        boolean redefine = inst.isRedefineClassesSupported();
        boolean retransform = inst.isRetransformClassesSupported();
        boolean nativePrefix = inst.isNativeMethodPrefixSupported();

        ClassFileTransformer noOp = new ClassFileTransformer() {};
        boolean canRegisterRetransforming;
        try {
            inst.addTransformer(noOp, true);
            canRegisterRetransforming = inst.removeTransformer(noOp);
        } catch (UnsupportedOperationException expected) {
            canRegisterRetransforming = false;
        }
        if (canRegisterRetransforming != retransform) {
            throw new AssertionError("capability and transformer registration differ");
        }
        System.setProperty("demo.agent.entry", entry);
        System.out.println("agent.entry=" + entry);
        System.out.println("agent.args=" + (args == null ? "null" : args));
        System.out.println("agent.redefine=" + redefine);
        System.out.println("agent.retransform=" + retransform);
        System.out.println("agent.nativePrefix=" + nativePrefix);
        System.out.println("agent.retransformRegistration="
                + canRegisterRetransforming);
    }

    public static void premain(String args, Instrumentation inst) {
        report("premain", args, inst);
    }

    public static void agentmain(String args, Instrumentation inst) {
        report("agentmain", args, inst);
    }
}

class AgentManifestApp {
    public static void main(String[] args) {
        System.out.println("app.entry="
                + System.getProperty("demo.agent.entry", "none"));
    }
}
```

**Đây là file hoàn chỉnh có thể biên dịch bằng Java 17.** Chi tiết:
- `premain` và `agentmain` đều `public static`, đúng signatures được package spec chấp nhận.
- Code không thay đổi bytecode, chỉ tạo no-op `ClassFileTransformer` để kiểm tra đăng ký với `canRetransform=true`.
- Khi JVM/manifest không hỗ trợ retransformation, `addTransformer(noOp, true)` ném `UnsupportedOperationException` và kết quả in false.
- Khi hỗ trợ, việc đăng ký/gỡ transformer thành công và kết quả in true. `removeTransformer` trả boolean, được đối chiếu với capability runtime.
- `System.setProperty` ghi dấu vào **JVM hiện hành** để app `main` chứng minh agent callback đã chạy trước.
- `AgentManifestApp` không yêu cầu `Instrumentation`; nếu chạy không có agent, nó in `app.entry=none`.
- Không cần JNI, ASM, Byte Buddy, thư viện ngoài hay Internet. Đây là bài thực hành **manifest/capability**, không phải một bytecode rewriter.

### 5.3. Manifest A — tối thiểu, không xin capability đặc biệt

File **`minimal.mf`**:

```text
Manifest-Version: 1.0
Premain-Class: AgentManifestDemo
Agent-Class: AgentManifestDemo

```

Không có bất kỳ `Can-*` nào. Kỳ vọng trên JDK đã thử: `isRedefineClassesSupported()`, `isRetransformClassesSupported()` và `isNativeMethodPrefixSupported()` đều false.

**Dù có Agent-Class**, command `-javaagent` sẽ gọi **premain**, không phải agentmain. Cần hiểu đây là behavior của JVM launcher, không phải code phân nhánh dựa trên class name.

### 5.4. Manifest B — yêu cầu cả ba capability để đo

File **`capable.mf`**:

```text
Manifest-Version: 1.0
Premain-Class: AgentManifestDemo
Agent-Class: AgentManifestDemo
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

```

Đây là cấu hình **chỉ dùng trong fixture** để thấy cả ba cờ. Trong production **không nên bật ba cờ cùng lúc** nếu không cần. Trên OpenJDK 24 đã chạy, ba runtime checks đều true và đăng ký retransformation-capable no-op transformer thành công. Với JVM khác, capability có thể không hỗ trợ và phải có handling thích hợp.

### 5.5. Manifest C — agent đóng chung với executable app JAR

File **`launcher.mf`**:

```text
Manifest-Version: 1.0
Main-Class: AgentManifestApp
Launcher-Agent-Class: AgentManifestDemo

```

JVM hỗ trợ bundled launcher sẽ gọi `AgentManifestDemo.agentmain("", inst)` **trước** `AgentManifestApp.main`. Vì manifest này không có `Can-*`, runtime capability checks tương ứng false. **Không** thêm `Agent-Class` để “kích hoạt” bundled launcher; chính `Launcher-Agent-Class` là thuộc tính có ý nghĩa trong trường hợp này.

### 5.6. Manifest D — âm tính: chỉ có Agent-Class

File **`agent-only.mf`**:

```text
Manifest-Version: 1.0
Agent-Class: AgentManifestDemo

```

JAR này **không dùng với `-javaagent`** vì thiếu `Premain-Class`. Nó phù hợp làm agent JAR để **dynamic load** nếu implementation cho phép. Ta sẽ chạy negative test để chứng minh `-javaagent:agent-only.jar` bị từ chối trước `App.main` và dùng chính `agent-only.jar` cho attach test ở mục 9.

### 5.7. Biên dịch và đóng cả bốn JAR

Trong thư mục chứa file `AgentManifestDemo.java` và bốn `.mf`, sử dụng JDK 17+:

```bash
mkdir out
javac --release 17 -d out AgentManifestDemo.java

jar --create --file agent-minimal.jar --manifest minimal.mf -C out .
jar --create --file agent-capable.jar --manifest capable.mf -C out .
jar --create --file app-bundled.jar --manifest launcher.mf -C out .
jar --create --file agent-only.jar --manifest agent-only.mf -C out .

jar --list --file agent-capable.jar
```

Nếu directory `out` đã tồn tại, `mkdir out` có thể báo tồn tại nhưng không ảnh hưởng compile; chạy từ thư mục test mới là đường sạch nhất. Các commands `jar --create ... -C out .` đã chạy trên OpenJDK 24. Dấu chấm là chọn **mọi file cần đóng trong `out`**, bao gồm `AgentManifestDemo$1.class` do anonymous class sinh ra.

**Kiểm tra JAR contents:** `jar --list --file agent-capable.jar` cần thấy `META-INF/MANIFEST.MF`, `AgentManifestDemo.class`, `AgentManifestDemo$1.class` và `AgentManifestApp.class`. Các file `.mf` đứng ngoài JAR chỉ là input cho `jar --manifest`; manifest thực sự dùng lúc khởi động ở **bên trong** JAR.

### 5.8. Kiểm thử 1: ứng dụng không agent

```bash
java -cp out AgentManifestApp
```

Stdout thực đã chạy:

```text
app.entry=none
```

Đây là baseline: agent không tự kích hoạt chỉ vì `AgentManifestDemo.class` có trên classpath.

### 5.9. Kiểm thử 2: startup agent tối thiểu

```bash
java -javaagent:agent-minimal.jar=profile=minimal -cp out AgentManifestApp
```

Stdout chính xác trên OpenJDK 24:

```text
agent.entry=premain
agent.args=profile=minimal
agent.redefine=false
agent.retransform=false
agent.nativePrefix=false
agent.retransformRegistration=false
app.entry=premain
```

Nhận xét:
- `premain` đã chạy **trước** application main.
- `agent.args` giữ nguyên chuỗi `profile=minimal`.
- Các `Can-*` không khai báo, nên ba khả năng đều false trên JVM thử nghiệm.
- `addTransformer(noOp,true)` không được phép trong cấu hình này, nên `agent.retransformRegistration=false`.
- `app.entry=premain` xác nhận property do agent đặt đã được application nhìn thấy.

### 5.10. Kiểm thử 3: startup agent yêu cầu capability

```bash
java -javaagent:agent-capable.jar=profile=full -cp out AgentManifestApp
```

Stdout chính xác trên OpenJDK 24:

```text
agent.entry=premain
agent.args=profile=full
agent.redefine=true
agent.retransform=true
agent.nativePrefix=true
agent.retransformRegistration=true
app.entry=premain
```

Điểm quan trọng: đây là **khả năng đã được JVM thử nghiệm xác nhận**, không chỉ là string `true` trong manifest. Các quyền này không chứng minh app class nào đó sẽ retransform thành công hoặc transformer thực sự thay bytecode.

### 5.11. Kiểm thử 4: bundled launcher

```bash
java -jar app-bundled.jar
```

Stdout chính xác trên OpenJDK 24:

```text
agent.entry=agentmain
agent.args=
agent.redefine=false
agent.retransform=false
agent.nativePrefix=false
agent.retransformRegistration=false
app.entry=agentmain
```

`agent.args=` không có ký tự phía sau vì **Launcher-Agent-Class truyền empty string**. Dòng `app.entry=agentmain` xác nhận agentmain đã chạy trước main. Đây **không** phải `Agent-Class` dynamic attach: JVM launcher đọc `Launcher-Agent-Class` từ executable JAR.

### 5.12. Kiểm thử 5: thiếu Premain-Class phải FAIL

```bash
java -javaagent:agent-only.jar -cp out AgentManifestApp
```

Đây là **negative test**, JVM phải thất bại vì JAR chỉ có `Agent-Class`. Đừng chạy trong production hoặc nhầm với lệnh nên sử dụng. Kết quả lỗi cụ thể có thể khác giữa JDK/provider; lượt QA đã kiểm tra ba điều kiện bất biến:

```text
negativeExitNonZero=True
negativeMentionsPremain=True
negativeAppNotLaunched=True
```

Ba dòng trên được in bởi **PowerShell test wrapper** sau khi bắt stderr/exit code của JVM lỗi; chúng **không phải output tự phát của java command ở trên**. Output JVM có thể kèm diagnostic/error lines, không cần hardcode toàn bộ; điều được xác nhận là exit code khác 0, lỗi nhắc `Premain-Class` và application main không được gọi.

### 5.13. Kiểm thử 6: đọc lại manifest từ bên trong JAR

Bạn có thể sử dụng `java.util.jar.JarFile` để kiểm tra **main attributes thực đã đóng gói**. File bổ sung **`AuditManifest.java`**:

```java
import java.util.jar.JarFile;
import java.util.jar.Attributes;

public class AuditManifest {
    private static void report(String label, String file) throws Exception {
        try (JarFile jar = new JarFile(file)) {
            Attributes a = jar.getManifest().getMainAttributes();
            System.out.println(label + ".premain=" +
                    a.getValue("Premain-Class"));
            System.out.println(label + ".agent=" +
                    a.getValue("Agent-Class"));
            System.out.println(label + ".launcher=" +
                    a.getValue("Launcher-Agent-Class"));
            System.out.println(label + ".redefine=" +
                    a.getValue("Can-Redefine-Classes"));
            System.out.println(label + ".retransform=" +
                    a.getValue("Can-Retransform-Classes"));
            System.out.println(label + ".nativePrefix=" +
                    a.getValue("Can-Set-Native-Method-Prefix"));
        }
    }

    public static void main(String[] args) throws Exception {
        report("minimal", "agent-minimal.jar");
        report("capable", "agent-capable.jar");
        report("launcher", "app-bundled.jar");
        report("agentOnly", "agent-only.jar");
    }
}
```

Chạy:

```bash
javac --release 17 -d out AuditManifest.java
java -cp out AuditManifest
```

Stdout chính xác đã được kiểm thử:

```text
minimal.premain=AgentManifestDemo
minimal.agent=AgentManifestDemo
minimal.launcher=null
minimal.redefine=null
minimal.retransform=null
minimal.nativePrefix=null
capable.premain=AgentManifestDemo
capable.agent=AgentManifestDemo
capable.launcher=null
capable.redefine=true
capable.retransform=true
capable.nativePrefix=true
launcher.premain=null
launcher.agent=null
launcher.launcher=AgentManifestDemo
launcher.redefine=null
launcher.retransform=null
launcher.nativePrefix=null
agentOnly.premain=null
agentOnly.agent=AgentManifestDemo
agentOnly.launcher=null
agentOnly.redefine=null
agentOnly.retransform=null
agentOnly.nativePrefix=null
```

**Không nhầm `null` với `"false"` trong artifact readback:** `JarFile.getManifest().getMainAttributes().getValue(key)` trả null **khi header không có**. JVM package specification định nghĩa thiếu `Can-*` thì capability request **mặc định false**. Đây là hai tầng biểu diễn khác nhau.

## 6. Phân biệt “đã khai báo”, “đã được cấp” và “đã dùng thành công”

Một lệnh kiểm tra tốt không dừng ở `jar --list`. Cần kiểm soát một **capability matrix**:

| Thử nghiệm | Trong manifest | Java callback | Giá trị runtime | Diễn giải |
| --- | --- | --- | --- | --- |
| Baseline classpath | Không agent JAR | Không gọi | Không có Instrumentation | Không tự load agent |
| `agent-minimal.jar` `-javaagent` | Premain-Class, Agent-Class; ba Can-* thiếu | premain | Ba `false` trên test JVM | Không yêu cầu optional capability |
| `agent-capable.jar` `-javaagent` | Premain-Class + ba Can-* true | premain | Ba `true` trên OpenJDK 24 | JVM hỗ trợ và cấp quyền trong scenario |
| `app-bundled.jar` `java -jar` | Main-Class + Launcher-Agent-Class | agentmain trước main | Ba `false` | Agent đóng chung executable JAR |
| `agent-only.jar` với `-javaagent` | Có Agent-Class, thiếu Premain-Class | Không gọi | JVM abort | Sai loại manifest điểm vào |
| `agent-only.jar` dynamic attach | Agent-Class | agentmain trong JVM đích | Theo target JVM policy | Chỉ dùng khi owner cho phép |

Dù capability runtime trả true, nên kiểm tra thêm những điều sau **trước khi thao tác thực**:

```java
if (!inst.isRetransformClassesSupported()) {
    // Không gọi retransformClasses hoặc addTransformer(t, true).
}
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(SomeClass.class)) {
    // Khi có yêu cầu hợp lệ và transformation được kiểm thử,
    // mới xem xét retransformClasses(SomeClass.class).
}
```

Đây là **snippet minh họa** về guard, cần `Instrumentation inst` và `SomeClass` có thật, không được copy nguyên làm một agent runnable. Không gọi `retransformClasses` chỉ để thử trên ứng dụng production: nó có thể kích hoạt lại một loạt transformers và thay bytecode.

### 6.1. Rủi ro của no-op transformer cũng phải hiểu đúng

Ví dụ dùng anonymous `new ClassFileTransformer() {}`. Trong Java 17+, cả hai overloads của `transform` đều có default implementations, nên anonymous instance không override method và về thực chất không thay đổi bytes. Khi gỡ ngay sau đăng ký, agent không có lasting transformer. Code dùng để chứng minh capability, không phải một APM agent.

Nếu muốn viết agent thật, phải xử lý class loader/module, concurrency, retransformation order, bytecode correctness, method semantics, verifier constraints và cleanup. Không nên cắt một ví dụ instrumentation/transformer ngắn rồi áp thẳng lên production class files.

### 6.2. Cần đo đúng JVM provider và phiên bản

- Chạy `java -version` để biết runtime.
- Test trên cùng vendor/JDK/config của production nếu muốn kết luận capability support.
- Sau thay đổi JVM flags hay security policy, rerun matrix.
- Không suy diễn kết quả `isNativeMethodPrefixSupported()==true` trên HotSpot thành bảo đảm của mọi JVM implementation.
- Chỉ cần `Premain-Class` cho startup no-op agent; không xin `Can-*` nếu không dùng.
- “Can-Retransform-Classes true” không thay thế JVM `-XX:+EnableDynamicAgentLoading`; đó là **hai cơ chế độc lập** (class instrumentation capability vs policy cho attach).

## 7. Attach API chỉ để kiểm chứng Agent-Class trong JVM mình sở hữu

`Agent-Class` không được gọi bởi `-javaagent` nhưng có thể được gọi khi **một tool được cho phép** nạp Java agent vào JVM đang chạy. OpenJDK/JDK có `com.sun.tools.attach.VirtualMachine` (module **`jdk.attach`**) cho các trường hợp attach được hỗ trợ. Dùng nó trên **JVM con do test harness tự tạo** là cách kiểm thử không đụng tới process khác của hệ thống.

### 7.1. JEP 451 và chính sách dynamic agents

JEP 451, được áp dụng từ JDK 21, đưa cảnh báo khi một Java/JVM TI agent được nạp **động** vào JVM đang chạy để chuẩn bị cho chính sách integrity-by-default trong các bản JDK tương lai. Trên HotSpot, `-XX:+EnableDynamicAgentLoading` là opt-in **rõ ràng** để cho phép dynamic agent loading và tránh warning tương ứng.

Điểm vận hành:
- **Ưu tiên `-javaagent` ngay lúc JVM startup** khi bạn kiểm soát deployment; đây là đường ổn định và minh bạch.
- Nếu cần dynamic attach như một serviceability action, phải có **ủy quyền của chủ JVM**, dùng chính sách cho phép và một agent JAR đáng tin.
- `Agent-Class` không tự “vượt” được target JVM flags, permissions, container restrictions hoặc availability của Attach API.
- Tương lai một JDK có thể mặc định chặn dynamic load; không hardcode rằng mọi JDK 17–26 đều có cùng default. Kiểm tra runtime cụ thể thay vì tắt cơ chế bảo vệ.
- `-Djdk.instrument.traceUsage` là công cụ chẩn đoán usages của instrumentation API khi cần, **không phải** manifest capability và không thay explicit attach authorization.
- `-XX:-EnableDynamicAgentLoading` có thể được dùng trong controlled test để xác minh ứng dụng không phụ thuộc việc attach ngầm; không áp dụng lên JVM production nếu chưa có kế hoạch vận hành.

### 7.2. Code tự kiểm thử external attach — `AgentAttachHarness.java`

File bổ sung này chạy **một JVM con** với `-XX:+EnableDynamicAgentLoading`, yêu cầu `VirtualMachine.loadAgent` bằng đúng `agent-only.jar` và tự thu dọn. Nó **không thực hiện self-attach** và không chọn PID của một ứng dụng ngoài phạm vi.

```java
import com.sun.tools.attach.VirtualMachine;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public final class AgentAttachHarness {
    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2)
            throw new IllegalArgumentException("agentJar signalFile");

        Path signal = Path.of(args[1]);
        Files.deleteIfExists(signal);
        Path java = Path.of(System.getProperty("java.home"), "bin", "java");
        Process child = new ProcessBuilder(
                java.toString(),
                "-XX:+EnableDynamicAgentLoading",
                "-cp", System.getProperty("java.class.path"),
                "AgentAttachTarget", signal.toString())
                .redirectErrorStream(true)
                .start();
        try {
            check("attachExternalProcess",
                    child.pid() != ProcessHandle.current().pid());
            VirtualMachine vm = VirtualMachine.attach(
                    Long.toString(child.pid()));
            try {
                vm.loadAgent(Path.of(args[0]).toAbsolutePath().toString(),
                        "profile=attached");
            } finally {
                vm.detach();
            }
            check("attachLoadAgentReturned", true);
            Files.writeString(signal, "release", StandardCharsets.UTF_8);
            check("attachChildExited",
                    child.waitFor(10, TimeUnit.SECONDS));
            check("attachChildSuccess", child.exitValue() == 0);
            String output = new String(
                    child.getInputStream().readAllBytes(),
                    StandardCharsets.UTF_8).replace("\r\n", "\n");
            check("attachAgentMainObserved",
                    output.contains("agent.entry=agentmain\n")
                    && output.contains("agent.args=profile=attached\n"));
            check("attachTargetSawAgent",
                    output.contains("target.agent=agentmain\n"));
            check("attachNoDynamicWarning",
                    !output.contains(
                       "WARNING: A Java agent has been loaded dynamically"));
        } finally {
            child.destroyForcibly();
            child.waitFor(5, TimeUnit.SECONDS);
            Files.deleteIfExists(signal);
        }
    }
}

class AgentAttachTarget {
    public static void main(String[] args) throws Exception {
        Path signal = Path.of(args[0]);
        long deadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        while (!Files.exists(signal)) {
            if (System.nanoTime() > deadline)
                throw new AssertionError("signal timeout");
            Thread.sleep(25);
        }
        System.out.println("target.agent=" +
                System.getProperty("demo.agent.entry", "none"));
    }
}
```

**Mã này dành cho JDK cung cấp module `jdk.attach` và target JVM cho phép external attach.** Một policy đóng attach có thể làm test fail hợp lệ vì môi trường không cho phép; không coi đó là lý do nên bỏ security policy trên máy của người khác. Child process là tiến trình mà harness tự tạo và sẽ bị dọn kể cả khi lỗi.

### 7.3. Lệnh kiểm thử dynamic attach

Sau khi đã build `agent-only.jar` và `out` ở mục 5:

```bash
javac --release 17 --add-modules jdk.attach -d out AgentAttachHarness.java
java --add-modules jdk.attach -cp out AgentAttachHarness agent-only.jar attach-signal.txt
```

Bài thực sự đã chạy test external attach trên OpenJDK 24, sử dụng `VirtualMachine.attach` đến PID của **child JVM**, `loadAgent` và `detach`, với opt-in do chính child process khởi tạo.

Stdout chính xác của harness:

```text
attachExternalProcess=true
attachLoadAgentReturned=true
attachChildExited=true
attachChildSuccess=true
attachAgentMainObserved=true
attachTargetSawAgent=true
attachNoDynamicWarning=true
```

**7/7 assertions PASS**. Test normalize `CRLF` về `LF` khi đối chiếu output, vì trên Windows line endings khác Linux/macOS; điều này không thay đổi behavior của agent. Child JVM đã in `agent.entry=agentmain` và `agent.args=profile=attached`, sau đó app nhìn thấy `target.agent=agentmain`.

### 7.4. Hai bài test đều là thực nhưng kiểm chứng điều khác nhau

| Test | Điều được chứng minh | Điều không được chứng minh |
| --- | --- | --- |
| `-javaagent:agent-minimal.jar` | Premain-Class được dùng, các Can-* mặc định false | Dynamic attach có được phép không |
| `-javaagent:agent-capable.jar` | Can-* true + HotSpot runtime support, no-op transformer registration thành công | Class bất kỳ có retransform thành công không |
| `java -jar app-bundled.jar` | Launcher-Agent-Class kích hoạt agentmain trước main | Target process đang chạy được Attach API loadAgent |
| `VirtualMachine.loadAgent(agent-only.jar)` | Agent-Class thực sự kích hoạt agentmain trong target child JVM đã opt in | Agent khác được phép attach tới production JVM hay không |
| Negative `-javaagent:agent-only.jar` | Thiếu Premain-Class ngăn -javaagent startup | Agent-Class thiếu/sai trong dynamic load path |

Không dùng `Launcher-Agent-Class` để suy đoán `Agent-Class` đã được kiểm thử; bài này kiểm tra **hai cơ chế riêng biệt**.

## 8. Kiểm tra manifest và packaging trước deployment

### 8.1. Kiểm tra artifact chứ không nhìn source .mf

`jar --manifest capable.mf` đọc file input rồi tạo manifest thực bên trong JAR. Trước deploy:
1. Chạy `jar --list --file agent-capable.jar` xem có `META-INF/MANIFEST.MF`, agent class và dependencies cần thiết.
2. Dùng `JarFile.getManifest().getMainAttributes()` để đọc các headers thực đã đóng gói.
3. Verify `Premain-Class` hoặc `Agent-Class` hay `Launcher-Agent-Class` phù hợp launch mode.
4. Verify `Can-*` là `true`/`false`/missing như design, không phải sai chính tả.
5. Chạy integration test thực trên **đúng JDK vendor/version**.
6. Verify JAR từ nguồn/bản build được phê duyệt, checksum và signature theo supply-chain policy. `jarsigner -verify` nếu có chữ ký chỉ là một phần kiểm chứng kỹ thuật, không tự nói publisher đáng tin.
7. Áp code review và security scanning cho các agent dependencies, vì instrumentation được thực thi trong JVM của ứng dụng.

### 8.2. Không lạm dụng Boot-Class-Path

`Boot-Class-Path` mở rộng classloader search, có tác động lớn tới runtime loading. Tránh đưa toàn bộ application libraries lên bootstrap loader. Nếu chỉ cần một agent class và no-op transformer như bài này, **không cần Boot-Class-Path**. Với custom system class loader, package spec còn có yêu cầu hỗ trợ `appendToClassPathForInstrumentation`; cấu hình cần được kiểm thử riêng.

### 8.3. Cấu hình named modules

Nếu bạn biên dịch mã agent/attach của dự án trong named modules:
- Agent API: `requires java.instrument;`.
- Attach API controller: `requires jdk.attach;`.
- Với classpath demo ở trên, không cần module-info.java; JDK cung cấp các modules tương ứng.
- `jdk.attach` không phải là một phần của app business Java SE runtime image tối giản. Nếu dùng `jlink` custom image, cần có module và attach provider tương ứng.
- Không giả định `-cp` và `--module-path` tương đương; agent loader và application module graph có các quy tắc khác nhau.

### 8.4. Khi nào cần Java agent thay vì một cơ chế ít quyền hơn?

Instrumentation là công cụ mạnh: monitoring, profiling, code coverage hoặc bytecode weaving. Nhưng nếu chỉ cần **business metrics**, **structured logging**, **OpenTelemetry API** hoặc **JFR events** mà không sửa bytecode, cân nhắc API thông thường trước. Agent mang code và dependencies vào JVM, có thể ảnh hưởng startup, class loading, latency, stack traces và security.

Không khuyến nghị dùng agent chỉ để bypass encapsulation hay để sửa runtime mà không có owner approval. Cờ Can-* không thay đổi nguyên tắc quản trị.

## 9. Lỗi phổ biến và hướng khắc phục

| Lỗi / hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Failed to find Premain-Class manifest attribute` | JAR thiếu `Premain-Class` khi dùng `-javaagent` | Bổ sung đúng header vào main manifest và rebuild |
| `ClassNotFoundException` ở agent entry | Binary class name sai hoặc class không nằm trong JAR | Kiểm tra `jar --list` và tên package |
| `NoClassDefFoundError: AgentManifestDemo$1` | Thiếu compiled anonymous class | Đóng tất cả generated `.class` bằng `-C out .` |
| JVM không gọi `agentmain` khi dùng `-javaagent` | `-javaagent` ưu tiên `Premain-Class` | Đặt code vào `premain` hoặc dùng đúng load mode |
| `java -jar` chỉ gọi main | Thiếu `Launcher-Agent-Class` | Khai báo bundled launcher nếu có mục đích |
| `Launcher-Agent-Class` gọi nhưng `agent.args` rỗng | Đúng semantics của bundled launcher | Không giả định nhận `-javaagent=options` |
| `Premain-Class` có trong source .mf nhưng JAR vẫn sai | JAR chưa rebuild hoặc đang chạy nhầm bản | Inspect manifest **bên trong JAR** |
| Manifest header nằm sau `Name: ...` | Đặt trong per-entry section, không phải main section | Đưa về main section |
| Lỗi manifest parsing | Encoding/BOM, line length, spacing, header trùng | Tuân JAR Manifest Specification, dùng `jar --manifest` |
| `isRetransformClassesSupported()==false` | `Can-Retransform-Classes` thiếu/false hoặc JVM không support | Đọc attrs + runtime capability |
| `addTransformer(t,true)` ném `UnsupportedOperationException` | Retransform không được cấp/hỗ trợ | Chỉ dùng when supported; không ép JVM |
| `isRedefineClassesSupported()==true` nhưng redefinition fail | Class unmodifiable hoặc thay đổi class file không được hỗ trợ | `isModifiableClass` và JVMTI restrictions |
| `Can-Set-Native-Method-Prefix` true nhưng JNI vẫn fail | Đây không phải setting native library path | Xem native binding/loader riêng |
| `VirtualMachine.attach` không được phép | OS/PID/provider/policy không cho | Kiểm tra quyền và policy của **target bạn sở hữu** |
| Agent dynamic load có warning JDK 21+ | JEP 451 cảnh báo integrity-by-default | Ưu tiên startup, opt-in có chủ đích khi cần |
| Dynamic agent không load khi policy off | JVM chặn dynamic loading | Không bypass; chủ JVM quyết định |
| Agent class thấy JDK classes nhưng không thấy app module class | Module graph/classloader visibility | Phân tích named/unnamed modules đúng |
| App main chạy trước agent | Sai launch option/order hoặc agent chưa enable | Đưa `-javaagent` vào JVM startup options trước main/-jar |
| App chạy hai lần instrumentation | Config external + bundled hoặc duplicate agents | Guard idempotence, chỉ một deployment path |
| Native method prefix có trên JVM này nhưng không ở JVM kia | Capability optional/provider-dependent | Runtime probe |
| `ClassFileTransformer` lambda compile fail | Interface không functional trong Java 17+ | `new ClassFileTransformer() {}` hoặc subclass rõ ràng |
| JAR ký rồi bị sửa | Signature verification thất bại | Rebuild/sign lại theo release process |
| Startup agent throw làm app không chạy | Fatal premain/init error | Sửa agent, không giấu exception |
| Agentmain throw nhưng app vẫn chạy | Dynamic load failure có semantics khác | Treat as partial operational failure và audit |
| Thu thập toàn bộ classes quá nhiều | Classloader/cpu/memory overhead | Bounded diagnostics, sample, avoid hot paths |

### 9.1. “Capability true” không có nghĩa retransform được mọi object

`isModifiableClass(Class<?>)` là một phép kiểm tra riêng. `redefineClasses`/`retransformClasses` còn có hạn chế về class file changes và có thể fail. Không tự biến một `true` trong manifest thành quảng cáo “can hot reload any Java code” — đó là sai contract.

### 9.2. Warnings về dynamic agent không phải lỗi manifest

Một warning như “A Java agent has been loaded dynamically” thuộc **JVM integrity policy/JEP 451**, không phải do `Agent-Class` thiếu. Nếu target process do bạn sở hữu, đánh giá app architecture và chọn startup `-javaagent` nếu có thể. Nếu external serviceability attach thật sự cần, owner cần opt in đúng JVM options. Không yêu cầu khách hàng tắt security policy để một test thành công.

### 9.3. Phân biệt class loader và bootstrap search

`ClassNotFoundException` không luôn do manifest sai. Agent classes được load trong system class loader/unnamed module theo package specification hiện hành; helper classes có thể cần visibility khác. Kiểm tra package, dependencies, module graph và JAR contents trước khi tự ý dùng `Boot-Class-Path`.

## 10. Các nguyên tắc bảo mật và ổn định của agent

1. **Nguồn agent JAR phải đáng tin.** Agent có thể quan sát/sửa bytecode và tác động behavior của JVM đang chạy.
2. **Không tự động attach vào tiến trình không thuộc quyền vận hành của bạn.** Attach API là công cụ được kiểm soát, không phải permission bypass.
3. **Cấp tối thiểu `Can-*`.** Nếu chỉ cần startup load-time logging, đừng bật redefine/retransform/native prefix một cách mặc định.
4. **Không log agent options chứa secrets.** Ví dụ này in args chỉ vì values là public test strings.
5. **Không chèn transformer vào toàn JVM mà không filter** package/class name/method và kiểm soát overhead.
6. **Tránh sửa các classes nội bộ JDK/third-party** khi không có kiểm thử tương thích.
7. **Đảm bảo transformer idempotent** nếu có nhiều agents, nhiều classloader hoặc retransform.
8. **Không tin JAR attribute chỉ vì text file .mf đúng**: kiểm tra artifact build thật.
9. **Cần có startup rollback** để gỡ agent nếu nó làm app không khởi động.
10. **Theo dõi JDK upgrades**: agent bytecode APIs, integrity policies, JVMTI capabilities và app module encapsulation có thể thay đổi.
11. **Test với cùng JDK/vendor/OS/runtime flags** đang chạy production; đừng mặc định HotSpot QA giống mọi JVM.
12. **Kiểm soát external attach** bằng OS permissions, JVM opt-in policy và audit logs.
13. **Tách agent debugging/test JAR khỏi production release**; tránh phát tán test-only manifests có cả ba Can-* true.
14. **Tài liệu hóa điểm vào và yêu cầu module/boot class path** nếu agent được ship cùng app.
15. **Không dùng instrumentation như một cách phá security boundaries**; mọi module opening/exports cần review.

## 11. Checklist phát hành agent manifest

- [ ] JAR có `META-INF/MANIFEST.MF` ở vị trí chuẩn.
- [ ] `Manifest-Version: 1.0` trong main section, file encoding/line breaks hợp lệ.
- [ ] `Premain-Class` có mặt nếu chạy `-javaagent`.
- [ ] `Agent-Class` có mặt nếu phải dynamic attach (và target policy cho phép).
- [ ] `Launcher-Agent-Class` và `Main-Class` có mặt nếu đóng cùng executable application JAR.
- [ ] Agent callback có signature `public static` hợp lệ, đúng `premain` hoặc `agentmain`.
- [ ] Tên class là Java binary name và tất cả `.class` generated/dependencies đã vào artifact.
- [ ] `Can-Redefine-Classes` chỉ bật nếu thực sự cần.
- [ ] `Can-Retransform-Classes` chỉ bật nếu thực sự cần.
- [ ] `Can-Set-Native-Method-Prefix` chỉ bật nếu thực sự cần.
- [ ] Test trên JVM thật bằng `isRedefineClassesSupported`/`isRetransformClassesSupported`/`isNativeMethodPrefixSupported`.
- [ ] Nếu thao tác lên class cụ thể, kiểm tra `isModifiableClass` và xử lý checked/runtime exceptions phù hợp.
- [ ] Dùng `JarFile` hoặc `jar --list` kiểm tra manifest/classes **bên trong JAR**, không chỉ file inputs.
- [ ] Khởi động `-javaagent` trước application main / `-jar`.
- [ ] Kiểm tra behavior khi không có agent và khi startup agent fail.
- [ ] Kiểm tra không trùng registration nếu deploy bằng nhiều cơ chế.
- [ ] Chỉ mở bootstrap/module visibility nếu có nhu cầu và security review.
- [ ] Nếu dùng Attach API, có owner opt-in + provider + access controls rõ ràng.
- [ ] Không ghi secrets trong manifest/command line/stdout.
- [ ] CI ghi nhận runtime/version, manifest audit và exact tests.
- [ ] Có release signing/checksum và kế hoạch rollback.

## 12. Bài tập tự luyện

**Bài 1 — Tối thiểu:** Tạo `agent-minimal.jar` chỉ có `Premain-Class`. Xác nhận `-javaagent` gọi `premain` và ba capability checks mặc định false.

**Bài 2 — Xin quyền selective:** Giữ `Can-Retransform-Classes: true` nhưng bỏ hai cờ còn lại. Chạy trên JVM hỗ trợ và dự đoán ba booleans trước khi xem stdout.

**Bài 3 — Phân biệt redefine và retransform:** Đổi từ `Can-Retransform-Classes` sang `Can-Redefine-Classes`. Thử `addTransformer(noOp,true)` có được phép không? Vì sao hai cờ độc lập?

**Bài 4 — Native prefix:** Tạo manifest riêng có `Can-Set-Native-Method-Prefix: true`. Đọc runtime capability mà không gọi API tác động JNI. Vì sao không nên bật nếu agent không cần?

**Bài 5 — Thiếu Premain-Class:** Chạy negative test `-javaagent:agent-only.jar` trong môi trường test. Xác nhận exit nonzero và application main không chạy.

**Bài 6 — Sai callback:** Khai báo `Premain-Class` trỏ tới class không có `premain`; theo dõi startup failure. Sửa đúng method signature, không tắt agent để bỏ qua test.

**Bài 7 — Launcher:** Đóng agent với `Launcher-Agent-Class` và `Main-Class`, chạy `java -jar`. Tại sao JVM gọi `agentmain` chứ không gọi `premain`? Vì sao args rỗng?

**Bài 8 — Manifest inspection:** Sử dụng `JarFile.getManifest` để nhận biết `null` khi `Can-*` header thiếu. So với runtime mặc định false.

**Bài 9 — Generated inner classes:** Cố tình đóng gói thiếu `AgentManifestDemo$1.class` trong thư mục test. Quan sát `NoClassDefFoundError` rồi đóng gói lại đủ `-C out .`.

**Bài 10 — Manifest line folding:** Tạo header value dài trên 72 bytes UTF-8, dùng `jar` chuẩn hóa và kiểm tra. Không thử “sửa nhanh” bằng xóa ký tự Unicode trong class name.

**Bài 11 — JDK capability differences:** Chạy cùng capable JAR ở hai JDK vendors/release environments. Dựng report chỉ dựa trên kết quả runtime, không dựa trên tên JAR.

**Bài 12 — External attach authorized:** Dùng `AgentAttachHarness` để attach vào child JVM do bạn tạo. Sau đó bật policy từ chối dynamic agents trên **child** theo chủ ý và xác nhận lỗi được báo, không né chính sách.

**Bài 13 — Module graph:** Đưa agent code vào package `demo.agent` và app code vào named module. Kiểm thử agent class visibility, điều chỉnh những module reads/opens chỉ khi được owner đồng ý.

**Bài 14 — Release QA:** Viết CI job build agent JAR, đọc manifest thực, chạy startup minimal/capable/launcher/negative và fail build nếu output hoặc exit status không đúng. Không upload private configuration data.

## 13. Câu hỏi ôn tập

**1. `Premain-Class` có vai trò gì?** Chỉ định Java agent class khi dùng startup `-javaagent`.

**2. `Agent-Class` có tự chạy khi JVM thấy JAR trên classpath không?** Không.

**3. `Launcher-Agent-Class` dùng khi nào?** Agent đóng cùng executable JAR chạy `java -jar`.

**4. `Launcher-Agent-Class` gọi `premain` hay `agentmain`?** `agentmain`.

**5. Agent args của Launcher-Agent-Class là gì?** Empty string.

**6. Một JAR có cả `Premain-Class` và `Agent-Class` được không?** Có; cách load quyết định callback dùng.

**7. Khi `-javaagent` không có `Premain-Class`, điều gì xảy ra?** JVM abort startup.

**8. `Main-Class` có thay thế `Premain-Class` không?** Không.

**9. Ba `Can-*` mặc định gì nếu thiếu?** False.

**10. Manifest `Can-Retransform-Classes: true` có đảm bảo retransform thành công?** Không; JVM và class cụ thể còn phải hỗ trợ.

**11. Check Java API nào cho quyền redefine?** `Instrumentation.isRedefineClassesSupported()`.

**12. Check Java API nào cho quyền retransform?** `Instrumentation.isRetransformClassesSupported()`.

**13. Check Java API nào cho native method prefix?** `Instrumentation.isNativeMethodPrefixSupported()`.

**14. Quyền redefine và retransform có giống nhau không?** Không, là hai capabilities độc lập.

**15. `isModifiableClass` có phải manifest attr không?** Không; là runtime API kiểm tra class cụ thể.

**16. `addTransformer(t,true)` có thể ném gì khi không hỗ trợ?** `UnsupportedOperationException`.

**17. `ClassFileTransformer` có viết lambda no-op được trong Java 17+ không?** Không; nó không phải functional interface, dùng anonymous class hoặc subclass.

**18. Dòng `Can-Redefine-Classes: YES` có bật quyền không?** Không theo spec; không phải `true` thì tính false.

**19. File `.mf` đúng có bảo đảm JAR thực đúng không?** Không; cần rebuild/inspect internal manifest.

**20. Tại sao agent class cần generated `$1.class`?** Anonymous class được biên dịch thành class file riêng.

**21. `Boot-Class-Path` có thay thế `--module-path` không?** Không.

**22. `Agent-Class` đủ để dynamic attach vào mọi JVM không?** Không; phụ thuộc implementation, attach policy và permissions.

**23. JEP 451 cảnh báo điều gì?** Dynamic loading of agents vào JVM đang chạy, chuẩn bị integrity-by-default policy.

**24. Nếu có thể chọn, nên deploy agent ở startup hay attach ngầm?** Ưu tiên `-javaagent` startup do owner cấu hình.

**25. Tham số `=profile=full` do JVM parse thành map không?** Không, là một String nguyên dạng.

**26. JAR chứa agent có thể chứa application main cùng không?** Có, qua `Main-Class` và `Launcher-Agent-Class` nếu launcher hỗ trợ.

**27. Có nên khai báo cả ba `Can-*` true mọi agent không?** Không, chỉ quyền thực sự cần.

**28. `JarFile.getManifest().getMainAttributes().getValue` trả gì nếu header thiếu?** Null.

**29. Dynamic attach test có cần quyền đối với target process không?** Có, và target JVM policy phải cho phép.

**30. Test cả ba booleans true trên OpenJDK 24 có chứng minh mọi JVM hỗ trợ không?** Không.

## 14. Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Agent-Class`, `Launcher-Agent-Class`, `Boot-Class-Path` và ba `Can-*`, callbacks, fail/abort semantics.
- [Oracle Java SE 26 — Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability queries, `addTransformer`, `redefineClasses`, `retransformClasses`, `isModifiableClass`, module APIs.
- [Oracle Java SE 26 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer methods, default return/no modification, ordering.
- [Oracle Java SE 26 — ClassDefinition](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): class bytes khi redefine.
- [Oracle Java SE 26 — JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): manifest grammar, 72-byte limit, Main-Class và Launcher-Agent-Class.
- [Oracle Java SE 26 — jar tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): create, manifest option, list, archive content.
- [Oracle Java SE 26 — Attributes.Name](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/Attributes.Name.html): manifest attribute names.
- [Oracle Java SE 26 — JarFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html): đọc manifest của artifact.
- [Oracle Java SE 26 — VirtualMachine (Attach API)](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): `attach`, `loadAgent`, `detach` và error cases.
- [Oracle Java SE 26 — java.instrument module](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/module-summary.html): Instrumentation APIs.
- [Oracle Java SE 26 — jdk.attach module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/module-summary.html): attach implementations.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): warning và integrity-by-default; startup agents được phân biệt với dynamic load.
- [Oracle JDK 21 Release Notes — JEP 451](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): `EnableDynamicAgentLoading`, `jdk.instrument.traceUsage`.
- [Oracle Java SE 26 — JVM Tool Interface specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jvmti.html): class redefinition/retransformation limitations và agent loading capabilities.

## 15. Tổng kết

**Điểm mấu chốt về manifest:** `Premain-Class` là cho `-javaagent` trước `main`; `Agent-Class` là cho **dynamic load** vào JVM đã chạy; `Launcher-Agent-Class` là cho **bundled executable JAR**, gọi `agentmain` trước application main với args rỗng. Ba `Can-*` là **các yêu cầu capability tùy chọn, mặc định false**, không phải bảo đảm JVM và mọi class đều cho phép sửa. `Instrumentation.isRedefineClassesSupported()`, `isRetransformClassesSupported()` và `isNativeMethodPrefixSupported()` mới phản ánh runtime hỗ trợ trong cấu hình đã khởi động.

Ví dụ Java 17+ trong bài đã build JAR thật bằng `jar --create --manifest`, chạy **baseline + minimal startup + capable startup + bundled launcher + missing Premain negative + manifest audit** trên OpenJDK 24; ngoài ra, một harness riêng **dynamic-attach vào JVM con do test tự tạo** đã đạt **7/7 assertions PASS** với explicit owner opt-in. Không có bytecode thật nào bị thay đổi và không attach vào JVM production. Khi triển khai agent thực, ưu tiên `-javaagent` được cấu hình minh bạch, chỉ xin quyền cần thiết, verify manifest/JAR artifact thực và tuân thủ bảo mật JVM.
