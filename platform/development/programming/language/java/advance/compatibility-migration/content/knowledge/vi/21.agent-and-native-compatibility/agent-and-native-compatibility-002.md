# Java agent lúc khởi động và agent gắn vào tiến trình đang chạy

## 1. Vì sao Java agent quan trọng trong migration?

Khi nâng JDK, ứng dụng Java có thể biên dịch thành công nhưng vẫn không khởi động được, mất dữ liệu tracing hoặc gặp lỗi liên quan bytecode trong production. Nguyên nhân đôi khi không nằm ở mã nghiệp vụ mà ở **Java agent**: thành phần được tải vào JVM để quan sát hoặc biến đổi các class trong thời gian khởi động hay vận hành.

Java agent thường xuất hiện trong:

- Application Performance Monitoring (APM), distributed tracing, metrics và profiling.
- Unit/integration tests, code coverage hoặc mocking cần instrumentation.
- Công cụ phát hiện lỗi, theo dõi lời gọi phương thức và chẩn đoán runtime.
- Một số framework bytecode enhancement hoặc công cụ vận hành.
- Hệ thống chạy lâu cần bổ sung khả năng quan sát trong một tình huống được phép.

Điểm dễ bị bỏ sót là agent không nhất thiết nằm trong danh sách dependency của ứng dụng. Nó có thể được hạ tầng thêm qua `-javaagent`, `JAVA_TOOL_OPTIONS`, container entrypoint, Java test runner hoặc một công cụ attach riêng. Vì vậy, trong chủ đề **Java Advance Compatibility Migration — Agent và mã native**, cần đánh giá agent như một **runtime dependency có quyền ảnh hưởng đến tiến trình**, không phải phụ kiện tùy chọn.

Hai hình thức sử dụng Java instrumentation agent là:

1. **Nạp lúc khởi động:** JVM được chạy với `-javaagent:<agent.jar>[=<options>]` và gọi `premain` trước `main`.
2. **Nạp động vào JVM đang chạy:** một controller dùng **Attach API** yêu cầu target JVM nạp JAR agent và gọi `agentmain`.

Hai hình thức có chung Java Instrumentation API nhưng khác nhau về thời điểm, quyền vận hành, khả năng tác động đến class đã nạp và các chính sách bảo mật ở những phiên bản JDK mới.

## 2. Phân biệt Java agent, native JVMTI agent và công cụ quản trị

Từ *agent* được dùng cho nhiều loại phần mềm. Trong migration phải nhận diện chính xác:

| Công nghệ | Hình thức | Thành phần chủ yếu | Mục đích |
| --- | --- | --- | --- |
| Java instrumentation agent | `-javaagent` hoặc Attach API `loadAgent` | JAR, `java.lang.instrument` | Class transformer, APM, kiểm thử |
| Native JVMTI agent | `-agentlib`, `-agentpath` hoặc cơ chế nạp native phù hợp | Shared library, JVM Tool Interface | Debug/profiling và sự kiện JVM cấp thấp |
| Java Flight Recorder (JFR) | API và công cụ recording | Cơ chế ghi sự kiện JVM | Chẩn đoán/quan sát hiệu năng |
| JMX/management | Management APIs | MBeans, management interfaces | Giám sát và quản trị trạng thái |
| Logging/metrics/tracing ở ứng dụng | Library tích hợp trong code | API/SDK ứng dụng | Observability tại boundary nghiệp vụ |

**`-javaagent` không giống `-agentlib`.** Loại thứ nhất dùng một JAR có entry point Java; loại thứ hai nạp thư viện native với yêu cầu riêng về OS, CPU, ABI và JVMTI.

Không phải nhu cầu quan sát nào cũng cần attach agent. Nếu chỉ cần GC, CPU, thread states hoặc event có sẵn, JFR/JMX và các công cụ được nhà cung cấp JVM hỗ trợ có thể đơn giản hơn, ít rủi ro hơn. Agent phù hợp khi phải can thiệp vào class loading hoặc instrumentation chi tiết mà những công cụ đó chưa đáp ứng.

## 3. Hai kiểu nạp Java agent khác nhau như thế nào?

| Tiêu chí | Startup agent | Dynamic agent |
| --- | --- | --- |
| Cách yêu cầu | JVM option `-javaagent` | Attach API từ công cụ có quyền |
| Entry point | `premain` | `agentmain` |
| Thời điểm | Trước khi `main` của ứng dụng chạy | Khi JVM đích đã chạy |
| Class đã nạp trước agent | Thường ít hơn | Có thể rất nhiều |
| Instrument class mới | Transformer đăng ký kịp trước class load | Có thể instrument những class nạp sau khi đăng ký |
| Instrument class đã nạp | Có thể cần retransform/redefine | Thường cần retransform/redefine nếu muốn thay code đã nạp |
| Vận hành | Khai báo ở startup/deployment | Hành động vận hành có quyền và audit |
| Lỗi nạp | Có thể làm JVM không khởi động | Lệnh attach/load thất bại; cần xem tác động đến target |
| Chính sách JDK | Startup option được khai báo từ đầu | Có thêm chính sách về dynamic loading |
| Rollback | Thường điều chỉnh deployment và restart | Không có thao tác gỡ agent tổng quát tương đương `detach` |

Agent được nạp **bên trong cùng JVM của ứng dụng**. Nó có thể chạy code, tạo thread, cấp phát memory, thêm transformer, thay đổi cách class được định nghĩa và làm tăng tải. Không nên coi agent là một tiến trình quan sát độc lập hoàn toàn.

### 3.1. Sự khác biệt về thời điểm có thể thay đổi kết quả

Một agent tracing startup có thể đăng ký transformer trước lúc HTTP server và JDBC driver được nạp. Nếu attach muộn sau khi những class này đã được định nghĩa, agent không tự động instrument ngược chúng. Agent phải hỗ trợ việc xử lý class đã nạp theo các capability tương ứng. Nếu không, hai chế độ có thể cho mức coverage khác nhau dù đều báo “agent loaded”.

## 4. `java.lang.instrument` cung cấp những API nào?

Các khái niệm chính:

- `Instrumentation`: handle do JVM đưa cho agent để đăng ký transformer, xem một số class đã nạp, yêu cầu retransformation/redefinition khi được hỗ trợ.
- `ClassFileTransformer`: callback được gọi khi một class được định nghĩa hoặc xử lý lại theo cơ chế instrumentation.
- `ClassDefinition`: mô tả một class và bytecode dùng cho redefinition.
- Manifest attributes: chỉ định entry point, capability của JAR agent.
- `premain`/`agentmain`: entry point cho startup/dynamic loading.

Luồng startup:

~~~text
Java launcher
    |
    | -javaagent:/path/agent.jar
    v
JVM reads agent manifest
    |
    v
Agent.premain(...)
    |
    v
Register ClassFileTransformer
    |
    v
Application.main(...)
    |
    v
Application classes loaded / methods executed
~~~

Luồng attach:

~~~text
Target JVM is already running
          |
Authorized controller
          |
          v
VirtualMachine.attach(pid)
          |
VirtualMachine.loadAgent(jar, options)
          |
          v
Target JVM invokes agentmain(...)
          |
          v
Transformer registered
          |
New loads / optional retransformation
~~~

JVM không tự tạo một bytecode transformer nếu agent không đăng ký. Và một transformer trả về `null` chỉ quan sát hoặc bỏ qua class bytes, không thay đổi bytecode.

## 5. Manifest của một Java agent JAR

Ví dụ `agent-manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.DemoAgent
Agent-Class: example.agent.DemoAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `Premain-Class` | Class khai báo method `premain` cho startup |
| `Agent-Class` | Class khai báo method `agentmain` cho attach |
| `Can-Redefine-Classes` | Yêu cầu khả năng redefine classes |
| `Can-Retransform-Classes` | Yêu cầu khả năng retransform classes |
| `Can-Set-Native-Method-Prefix` | Capability nâng cao liên quan native method prefixes |

Không cần yêu cầu capability mà agent không sử dụng. Các thuộc tính `Can-*` cũng không biến capability thành điều được bảo đảm trên mọi JVM. Mã agent phải kiểm tra `Instrumentation.isRetransformClassesSupported()`, `isRedefineClassesSupported()` và `isModifiableClass(...)` trước khi yêu cầu thao tác nâng cao.

`Main-Class` của một executable JAR **không thay thế** `Premain-Class` hoặc `Agent-Class`. Một JAR ứng dụng có `Main-Class` không tự biến thành Java agent.

### 5.1. Entry point phải có chữ ký hợp lệ

Trong dạng có Instrumentation:

~~~java
public static void premain(
        String arguments,
        Instrumentation instrumentation) {
    // Startup path
}

public static void agentmain(
        String arguments,
        Instrumentation instrumentation) {
    // Dynamic attach path
}
~~~

Java Instrumentation API cũng hỗ trợ những dạng một tham số `String` trong các điều kiện được đặc tả. Đối với ví dụ có nhu cầu đăng ký transformer, nên dùng dạng hai tham số để nhận `Instrumentation` tường minh.

## 6. Ví dụ hoàn chỉnh: Java agent hỗ trợ cả hai chế độ

Đoạn mã sau chỉ ghi thông tin lifecycle, **không thay đổi bytecode**:

~~~java
package example.agent;

import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    private DemoAgent() {}

    public static void premain(
            String args, Instrumentation inst) {
        start("startup", args, inst);
    }

    public static void agentmain(
            String args, Instrumentation inst) {
        start("dynamic", args, inst);
    }

    private static void start(
            String mode, String args, Instrumentation inst) {
        System.err.println(
                "[demo-agent] mode=" + mode
                + ", args=" + args
                + ", canRetransform="
                + inst.isRetransformClassesSupported());
    }
}
~~~

Ví dụ in `args` nhằm minh họa cách truyền options. Trong sản phẩm thật, **không log trực tiếp** chuỗi options nếu có secret, token, địa chỉ nhạy cảm hoặc dữ liệu nhận dạng; hãy parse và redaction.

Giả sử mã nằm ở:

~~~text
src/agent/java/example/agent/DemoAgent.java
src/agent/agent-manifest.mf
src/app/java/example/app/Main.java
~~~

Ví dụ lệnh sinh JAR bằng công cụ JDK:

~~~bash
javac -d build/agent-classes \
  src/agent/java/example/agent/DemoAgent.java

jar --create \
  --file build/demo-agent.jar \
  --manifest src/agent/agent-manifest.mf \
  -C build/agent-classes .
~~~

Trong Maven/Gradle thật, nên dùng task/plugin đóng gói agent và cố định phiên bản build tool. Điều cần xác minh ở đây là JAR có `META-INF/MANIFEST.MF` đúng, class entry point được đóng gói và thư viện agent cần dùng đã sẵn sàng.

### 6.1. Kiểm tra manifest

Manifest phải chỉ đúng tên fully qualified class. Nếu package thực tế là `example.agent` nhưng manifest ghi `DemoAgent`, JVM có thể không tìm được class. Nếu tạo agent từ một fat/shaded JAR, cần kiểm tra bước shading có giữ manifest attributes và dependencies đúng hay không.

## 7. Cách dùng startup `-javaagent`

Ví dụ:

~~~bash
java -javaagent:build/demo-agent.jar=trace \
     -cp build/app-classes example.app.Main
~~~

Hoặc ứng dụng JAR:

~~~bash
java -javaagent:/opt/agents/demo-agent.jar=trace \
     -jar orders-service.jar
~~~

`-javaagent` là **JVM option** và cần xuất hiện trong phần launcher options trước tên main class hoặc `-jar`. Nếu đặt sai vị trí, nó có thể trở thành application argument, không được JVM dùng để tải agent.

### 7.1. Điều gì xảy ra trước `main`?

JVM nạp agent JAR, tìm `Premain-Class` và gọi `premain`. Agent có thể đăng ký transformer sớm để các class được định nghĩa sau đó đi qua callback. Nếu `premain` ném lỗi nghiêm trọng hoặc manifest/JAR hỏng, ứng dụng có thể không khởi động.

Vì thế, startup agent ảnh hưởng **availability**. Không nên thêm một JAR agent mới vào production mà chỉ thử rằng app source compile thành công. Cần smoke test chính launcher và runtime image sẽ được phát hành.

### 7.2. Nhiều startup agent

~~~bash
java -javaagent:/opt/agents/apm.jar \
     -javaagent:/opt/agents/coverage.jar \
     -jar orders-service.jar
~~~

Các `premain` startup được gọi theo thứ tự xuất hiện trên command line. Tuy nhiên, việc nhiều transformer cùng xử lý một class còn phụ thuộc các quy tắc đăng ký/retransformation. Hai agent dùng riêng đều chạy không có nghĩa chạy chung không xung đột.

Trong production, một APM agent và tracing agent có thể tạo spans trùng; coverage agent có thể thay bytecode cùng class mà framework đang enhancement. Cần kiểm thử **tổ hợp agent thực tế**, không chỉ từng agent đứng riêng.

### 7.3. Startup args từ môi trường

Một số môi trường truyền JVM options qua:

~~~text
JAVA_TOOL_OPTIONS=-javaagent:/opt/agents/apm-agent.jar
~~~

Startup scripts, Dockerfiles, Helm charts hoặc platform injection có thể tự thêm `-javaagent`. Cần kiểm tra **lệnh JVM thực tế được khởi chạy**, không chỉ file build repository. Một agent có thể xuất hiện hai lần nếu cả Dockerfile và platform cùng inject.

## 8. Dynamic attach là gì?

Dynamic attach cho phép một công cụ **có quyền** yêu cầu JVM đã chạy nạp agent. Thao tác này sử dụng Attach API trong module `jdk.attach` trên JDK hỗ trợ.

Đặc điểm:

- Không nhất thiết phải restart JVM để nạp agent trong trường hợp được phép.
- `agentmain` chạy sau khi ứng dụng đã khởi động; không được giả định môi trường giống `premain`.
- Nhiều class có thể đã được nạp, nên instrumentation có thể bị thiếu nếu agent không có logic retransform.
- Quyền attach do OS/JVM/platform policy kiểm soát; đây không phải kênh không cần xác thực.
- Việc load agent không phải thao tác chỉ đọc: nó chạy code trong target JVM.

Đây là lựa chọn phù hợp cho một số tình huống chẩn đoán được duyệt, nhưng không nên dùng như đường mặc định cho những agent bắt buộc phải tồn tại từ lúc service khởi động.

## 9. Attach API và `VirtualMachine.loadAgent`

Một controller Java tối giản:

~~~java
package example.tools;

import com.sun.tools.attach.VirtualMachine;

public final class AttachController {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            throw new IllegalArgumentException(
                    "Usage: <pid> <absolute-agent-jar> [options]");
        }

        String pid = args[0];
        String agentJar = args[1];
        String options = args.length >= 3 ? args[2] : "";

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, options);
        } finally {
            vm.detach();
        }
    }
}
~~~

Chỉ chạy công cụ này trên **JVM được phép quản trị**, trong môi trường có quy trình thay đổi rõ ràng. PID minh họa không được dùng để chọn tiến trình của người khác hoặc một process chưa được xác nhận.

Lệnh biên dịch/chạy ví dụ:

~~~bash
javac --add-modules jdk.attach \
  -d build/attach-classes \
  src/attach/java/example/tools/AttachController.java

java --add-modules jdk.attach \
  -cp build/attach-classes \
  example.tools.AttachController \
  12345 /absolute/path/demo-agent.jar diagnostic
~~~

`12345` là PID giả định. Đường dẫn đến JAR phải được target JVM hiểu đúng, và JAR phải có `Agent-Class` cùng method `agentmain` hợp lệ.

### 9.1. `detach()` không gỡ agent

`VirtualMachine.detach()` chỉ đóng kết nối của controller với target JVM. Nó không loại bỏ agent đã nạp, không tự gỡ transformer và không hoàn nguyên mọi thay đổi bytecode. Nếu cần agent tự tắt, phải thiết kế lifecycle/cleanup riêng và xem giới hạn của API; không có một thao tác chung bảo đảm “unload Java agent JAR khỏi JVM”.

### 9.2. Những lỗi Attach API thường gặp

| Lỗi | Điều cần kiểm tra |
| --- | --- |
| `AttachNotSupportedException` | Target JVM có hỗ trợ attach và bật cơ chế này không |
| `IOException` | Giao tiếp attach, target process, đường dẫn và môi trường |
| `AgentLoadException` | JAR, manifest, khả năng load agent |
| `AgentInitializationException` | `agentmain` hoặc quá trình khởi tạo bị lỗi |
| Lỗi quyền OS/security policy | Controller có được phép thao tác với target không |

Không tự động thay đổi permission để “chữa” lỗi. Cần xác định chính sách vận hành, user sở hữu process, container namespace và quyền thực sự được phê duyệt.

## 10. Các điều kiện và giới hạn của attach mechanism

Không phải mọi JVM hoặc deployment đều cho phép attach động. Các yếu tố gồm:

1. JVM implementation/vendor và JDK release.
2. OS user, quyền process và cơ chế attach được platform hỗ trợ.
3. PID namespace, mount namespace, container isolation.
4. Runtime image và module/tooling có mặt.
5. JVM flags như `-XX:+DisableAttachMechanism` trong môi trường HotSpot phù hợp.
6. Chính sách riêng về **dynamic agent loading**.
7. Hạ tầng managed/cloud có cho phép attach hay không.

Trên những HotSpot hỗ trợ, cờ:

~~~text
-XX:+DisableAttachMechanism
~~~

có thể ngăn attach mechanism. Đây là quyết định ở quá trình khởi động target JVM; controller không thể tùy tiện đảo ngược nó sau khi process đã chạy.

### 10.1. Self-attach có thể có quy tắc riêng

Một process tự attach vào chính JVM của nó là **self-attach**, khác với controller được phép attach từ process khác. Trên những JDK/implementation nhất định, self-attach bị hạn chế mặc định và có property như `jdk.attach.allowAttachSelf` điều khiển hành vi.

Không nên dùng:

~~~text
-Djdk.attach.allowAttachSelf=true
~~~

như câu trả lời mặc định cho mọi lỗi test instrumentation. Cần kiểm tra thư viện có hướng dẫn dùng startup `-javaagent` không, và JDK mục tiêu còn cho phép dynamic loading trong cấu hình đã duyệt hay không.

## 11. JDK 21: cảnh báo dynamic agent loading từ JEP 451

**JEP 451** được triển khai trong JDK 21 để chuẩn bị cho những giới hạn chặt hơn đối với việc nạp agent động. Trên các JVM HotSpot phù hợp, việc nạp Java agent động có thể tạo cảnh báo tương tự:

~~~text
WARNING: A Java agent has been loaded dynamically
WARNING: Dynamic loading of agents will be disallowed
         by default in a future release
~~~

Thông điệp chính: runtime muốn **chủ sở hữu ứng dụng có sự cho phép rõ ràng** cho hành vi nạp code agent sau khi JVM đã chạy. Startup `-javaagent` là một lựa chọn khác vì agent đã được khai báo từ lúc launch.

Các JVM options thường được đề cập trong tài liệu của những release phù hợp:

~~~text
-XX:+EnableDynamicAgentLoading
-XX:-EnableDynamicAgentLoading
~~~

Theo JEP 451, lựa chọn bật dynamic loading tường minh trên runtime phù hợp có thể tránh cảnh báo, còn cấu hình từ chối cho phép kiểm tra tác động của chính sách hạn chế. Nhưng **mặc định và ý nghĩa vận hành chính xác phải được xác nhận theo JDK vendor/release đang dùng**, không suy ra rằng chúng bất biến ở mọi JDK sau 21.

### 11.1. Phân biệt attach và quyền nạp agent

Attach API có thể được dùng cho nhiều thao tác quản trị. Quyền kết nối qua attach **không đồng nghĩa** quyền nạp một agent động. Một JVM có thể cho phép một số lệnh quản trị nhưng cấm `loadAgent` theo chính sách.

Không nên chỉ thấy `jcmd` liệt kê PID hoặc trả thông tin rồi kết luận `VirtualMachine.loadAgent` chắc chắn hoạt động.

### 11.2. Không tắt cảnh báo khi chưa xác định nguồn

Nếu test trên JDK 21+ xuất warning, hãy xác định thư viện nào đang self-attach: mocking, coverage, bytecode agent hay profiler. Nếu công cụ hỗ trợ startup agent, cấu hình `-javaagent` theo hướng dẫn vendor là một hướng giảm phụ thuộc vào dynamic loading.

Không tự động thêm `-XX:+EnableDynamicAgentLoading` vào toàn bộ production chỉ để console không còn warning từ một test library.

## 12. Trước hay sau class loading: hệ quả của thời điểm nạp

Một class Java được JVM định nghĩa một lần theo class loader/identity trong điều kiện thông thường. Khi transformer đã đăng ký trước class loading, nó có thể được gọi trong quá trình định nghĩa class.

Ngược lại, khi agent gắn vào JVM đã chạy:

- Nhiều class ứng dụng, framework, driver có thể đã được nạp.
- Transformer mới đăng ký thường tác động tới các class được xử lý sau đó.
- Muốn áp dụng cho class đã nạp cần khả năng **retransformation** hoặc **redefinition** được JVM hỗ trợ.
- Một số class không modifiable hoặc cấu trúc thay đổi vượt giới hạn.

Ví dụ, agent APM được attach sau khi HTTP server đã nhận request có thể không chèn được instrumentation vào những class cụ thể nếu không xử lý class đã nạp. Kết quả có thể là service chạy, agent loaded, nhưng traces không đầy đủ.

**Kết luận vận hành:** Khả năng agent nạp thành công và khả năng agent instrument đúng tất cả đường nghiệp vụ là **hai điều phải kiểm chứng riêng**.

## 13. `ClassFileTransformer`: ví dụ quan sát class names

Một transformer nhận class loader, tên class dạng internal name, thông tin redefinition và bytecode. Ví dụ chỉ in tên một nhóm class ứng dụng:

~~~java
package example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class NameObserver implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        if (className != null
                && className.startsWith("example/app/")) {
            System.err.println("[agent] class=" + className);
        }
        return null; // Không thay đổi bytecode.
    }
}
~~~

Đăng ký:

~~~java
instrumentation.addTransformer(new NameObserver());
~~~

Ví dụ dùng dạng method `transform` truyền thống; các JDK hiện đại còn có biến thể nhận `Module`. Agent production phải xem API, module boundaries và class-loader strategy thực tế.

### 13.1. Vì sao trả `null`?

Trong `ClassFileTransformer`, trả `null` nghĩa là không yêu cầu thay đổi class bytes. Để instrument thực sự, transformer cần tạo bytecode hợp lệ và trả array bytes phù hợp. Không nên tự sửa raw byte array nếu chưa hiểu JVM class-file format, stack map frames và verifier.

Với nhu cầu instrumentation phức tạp, nhiều dự án dùng ASM, Byte Buddy hoặc công cụ bytecode đã được hỗ trợ. Tuy nhiên, chính thư viện bytecode đó lại cần tương thích class-file version của JDK đích.

### 13.2. Tránh tạo vấn đề trong đường class loading

Transformer chạy ở đường nhạy cảm:

- Hạn chế blocking I/O và log mọi class.
- Tránh class loading đệ quy vô ý khi dùng helper classes.
- Kiểm soát tạo object và memory overhead.
- Không giữ reference đến mọi class loader làm chúng không được giải phóng.
- Xem xử lý exceptions, concurrency và reentrancy.
- Test bytecode output trong môi trường có nhiều class loaders/modules.

Một agent “chỉ để log” vẫn có thể ảnh hưởng performance nếu mỗi class load đều ghi I/O đồng bộ.

## 14. Retransformation và redefinition

Hai khả năng nâng cao trong `Instrumentation`:

**Retransformation**: yêu cầu JVM xử lý lại một class đã nạp, có thể thông qua các transformers hỗ trợ. **Redefinition**: cung cấp class bytes mới cho class đã nạp theo cơ chế thay định nghĩa.

Các cơ chế này **không phải hot reload hoàn chỉnh của mọi thay đổi Java**. Việc thêm/bỏ fields, đổi inheritance, thay method signatures hoặc thay class structure khác có thể nằm ngoài giới hạn hỗ trợ của JVM.

Ví dụ kiểm tra capability:

~~~java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(targetClass)) {
    instrumentation.retransformClasses(targetClass);
}
~~~

`targetClass` ở đây là class được chọn có chủ đích. Không nên gọi retransform trên toàn bộ classes đã nạp một cách mặc định, vì có thể tạo overhead, lỗi trên class không modifiable hoặc tác động concurrency.

### 14.1. Đăng ký transformer có retransformation

Nếu agent đã khai báo capability phù hợp và runtime báo hỗ trợ:

~~~java
if (instrumentation.isRetransformClassesSupported()) {
    instrumentation.addTransformer(
            new NameObserver(),
            true);
}
~~~

Ví dụ chỉ đăng ký một transformer quan sát, chưa cung cấp bytecode mới. Để làm thay đổi class, phải có transformer thực sự tạo class-file bytes hợp lệ và tuân thủ constraints.

### 14.2. Đừng giả định mọi frame đang chạy lập tức đổi behavior

Retransformation không có nghĩa các lời gọi đang nằm trên stack của mọi thread bị chạy lại. JVM có quy tắc riêng với frames và việc đổi định nghĩa. Nếu mục tiêu là sửa logic nghiệp vụ đang thực thi, phải phân tích concurrency/state, không sử dụng agent như cách triển khai patch không qua kiểm thử.

## 15. Multiple agents, transformers và thứ tự tác dụng

Một JVM có thể nhận nhiều agent ở:

- Startup JVM options.
- Dynamic attach ở các thời điểm khác nhau.
- Library/framework tự đăng ký instrumentation.

Nếu A và B đều transform một class, bytecode mà B xử lý có thể chịu ảnh hưởng của A theo cơ chế áp dụng transformers. Trong những trường hợp retransformation, thứ tự áp dụng còn có quy tắc riêng. Vì thế, không nên suy ra kết quả từ hai agent chạy riêng lẻ.

Rủi ro:

- Duplicate traces hoặc metrics.
- Xung đột transformation và `VerifyError`.
- Helper classes bị load bởi class loader không phù hợp.
- Agent A phụ thuộc thư viện bytecode khác version với agent B.
- Resource overhead lớn hơn tổng mong đợi.
- Thay đổi startup order làm khác class-loading timing.

Trong migration, phải kiểm thử **agent combination thật** và xác nhận output observability, không chỉ rằng JVM không crash.

## 16. Java Module System và agent

Từ Java 9, JPMS kiểm soát read edges, exports và opens. Agent instrumentation có thể cần:

- Truy cập một package để tạo helper hoặc phản chiếu.
- Làm cho class được chèn vào resolve được type nằm ở module khác.
- Instrument các class trong named modules.
- Tương thích với strong encapsulation và JDK internal API policies.

Triệu chứng thường thấy:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.NoClassDefFoundError
~~~

Agent cũ có thể dùng reflection vào một JDK internal package; điều đó có thể chạy ở môi trường trước nhưng không hoạt động trên JDK đích.

### 16.1. `Instrumentation.redefineModule`

Instrumentation API có `redefineModule(...)` để điều chỉnh một số quan hệ module theo quy tắc JVM khi thực sự cần. Đây là API cấp thấp; việc mở package hoặc thêm read edge cần được kiểm soát và ghi lý do.

Không nên mở mọi package JVM chỉ vì một thư viện agent chưa hỗ trợ JDK đích. Đầu tiên hãy tìm agent version vendor xác nhận tương thích.

### 16.2. `--add-opens` chỉ là workaround có phạm vi

Ví dụ cú pháp:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

Đây **không phải** cờ khuyến nghị thêm cho mọi service. Nó có thể giúp một số code reflection truy cập theo điều kiện cụ thể, nhưng không bảo đảm internal APIs luôn tồn tại. Nếu bắt buộc dùng, ghi component, package, owner, lý do và mốc gỡ bỏ.

## 17. Class loader và helper classes của agent

Bytecode được agent chèn vào class ứng dụng có thể gọi helper:

~~~text
example.agent.TraceHelper.onEnter()
~~~

Nếu class loader đang nạp class ứng dụng không thể nhìn thấy `TraceHelper`, có thể xảy ra linkage error. Môi trường application server, OSGi hoặc plugin framework có nhiều isolated class loaders khiến bài toán khó hơn.

`Instrumentation` cung cấp các khả năng nâng cao như:

~~~java
instrumentation.appendToBootstrapClassLoaderSearch(helperJar);
instrumentation.appendToSystemClassLoaderSearch(helperJar);
~~~

Ví dụ chỉ thể hiện API; `helperJar` phải là đối tượng `JarFile` phù hợp và việc append phải tuân thủ quy tắc class loading. Không sử dụng máy móc: đưa code vào bootstrap/system search có thể ảnh hưởng class resolution, package access và xung đột dependency.

### 17.1. Agent JAR có thể mang dependencies nhúng

Một APM agent thường có bytecode library, config parser, logging hoặc exporter. Chúng có thể được shade/relocate để tránh xung đột với thư viện ứng dụng. Nhưng shading không tự bảo đảm không có lỗi.

Khi nâng agent, kiểm tra:

- Libraries nhúng, đặc biệt ASM/Byte Buddy.
- Shading/relocation và service loader resources.
- Module/class-loader behavior.
- Bytecode capabilities với class-file version mới.
- Điều kiện class initialization và lifetime của helper classes.

## 18. Native JVMTI agent: đường nạp và khả năng tương thích

Native agent khác với JAR Java:

~~~bash
java -javaagent:/opt/agents/apm.jar -jar app.jar
java -agentlib:profiler=options -jar app.jar
java -agentpath:/absolute/path/profiler.so=options -jar app.jar
~~~

`profiler.so` và `profiler` chỉ là tên minh họa. Trên Windows hoặc macOS, dạng thư viện/đuôi file và quy tắc tìm kiếm khác.

Native JVMTI agent thường triển khai entry points theo JVM TI Specification, ví dụ `Agent_OnLoad` cho startup và những cơ chế hỗ trợ nạp sau startup tùy JVM. Attach API có các method dành cho native agents như `loadAgentLibrary`/`loadAgentPath`; `loadAgent` dùng cho Java JAR agent không phải bản thay thế trực tiếp.

### 18.1. Native migration có thêm ràng buộc

- OS và CPU architecture.
- ABI, libc và shared library dependencies.
- Native binary được cung cấp cho runtime image.
- JVMTI capabilities và vendor/JDK support.
- Container permissions, filesystem/mounts.
- Chi phí native memory và khả năng crash ở ngoài Java exception handling.

Một JAR Java agent chạy trên JDK đích không chứng minh native profiler của hệ thống cũng tương thích.

## 19. Agent trong unit test, mocking và code coverage

Những công cụ như Mockito, Byte Buddy, JaCoCo hoặc framework test khác có thể dùng instrumentation; cách nạp phụ thuộc version và cấu hình. Một số giải pháp từng dùng **dynamic self-attach** trong quá trình test.

Khi nâng JDK, dấu hiệu thường gặp:

~~~text
WARNING: A Java agent has been loaded dynamically
~~~

Hoặc lỗi từ bytecode parser:

~~~text
Unsupported class file major version 65
~~~

Hai tình huống cần xử lý khác nhau:

1. **JEP 451 warning:** kiểm tra cơ chế nạp động, policy JDK và hướng dẫn startup agent của tool.
2. **Class-file/parser failure:** kiểm tra JDK class-file version và thư viện bytecode/agent đang sử dụng.

Không mặc định rằng một warning là test failure, cũng không mặc định rằng mọi warning đều có thể bỏ qua lâu dài.

### 19.1. Cấu hình startup agent cho test JVM

Ví dụ Gradle Groovy DSL, chỉ minh họa cú pháp:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '-javaagent:/absolute/path/approved-test-agent.jar'
}
~~~

JAR thật phải hỗ trợ startup `Premain-Class` và được cung cấp từ một dependency/tool version được phê duyệt. Không đưa đường dẫn placeholder vào CI production.

Với Maven Surefire/Failsafe, cơ chế `argLine` cho phép truyền JVM options tới test process. Nếu JaCoCo hoặc plugin khác cũng sử dụng `argLine`, cần cấu hình phối hợp tránh ghi đè của nhau; cách kết hợp property có thể thay đổi theo phiên bản Maven plugin.

**Không phải mọi JAR mocking/test library đều là một agent JAR có thể chạy qua `-javaagent`.** Hãy theo hướng dẫn công cụ cụ thể, không chuyển chế độ bằng phỏng đoán.

## 20. Dynamic self-attach: lộ trình chuyển sang startup agent

Kịch bản: một library test tự attach vào JVM khi cần. Sau khi nâng lên JDK 21, log có warning. Nhóm muốn không phụ thuộc vào dynamic agent loading trong tương lai.

Lộ trình:

1. Xác định library nào self-attach và artifact JAR được nạp.
2. Kiểm tra version có hỗ trợ startup agent không.
3. Cố định agent dependency và cách cấp đường dẫn cho test JVM.
4. Cấu hình `-javaagent` trong startup của test process.
5. Tránh nạp trùng nếu library vẫn còn tự attach.
6. Chạy lại unit/integration, coverage, mocking behavior và CI.
7. Gỡ những flags/workarounds dynamic loading không còn cần.

Ví dụ thay đổi cơ chế:

~~~text
Before:
  Test JVM starts
  Library requests dynamic self-attach
  Agent starts during test execution

After:
  Test JVM starts with a supported -javaagent
  Library reuses instrumentation as documented
~~~

Lộ trình này chỉ áp dụng khi vendor công bố một startup agent mode phù hợp. Không được giả định mọi self-attaching library đều có chế độ thay thế một-một.

## 21. APM/tracing agent trong production: kiểm kê ở đâu?

Nguồn cấu hình agent có thể là:

- Script khởi chạy ứng dụng.
- Dockerfile hoặc container entrypoint.
- Kubernetes Deployment/Helm chart.
- `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS`.
- Application server configuration.
- Platform injection hoặc auto-instrumentation.

Mẫu record:

~~~text
Service: orders-service
JDK distribution/version: target-runtime
Agent: vendor-agent
Agent artifact/version/checksum: ...
Mode: startup -javaagent
Injected by: container entrypoint
Configuration: approved config reference, secrets redacted
Capabilities: tracing + JDBC instrumentation
Owner: platform/observability
Known JVM flags: ...
Rollback strategy: ...
~~~

Phải xác định **agent thực sự được nạp** trên mỗi môi trường. Dependency tree của Maven/Gradle có thể không thể hiện một JAR agent do platform thêm lúc deploy.

### 21.1. Không chỉ kiểm tra thông báo “agent started”

Sau nâng JDK/framework/agent, đo:

- Traces của HTTP, JDBC, messaging có đủ không?
- Context propagation giữa các thread/asynchronous tasks có còn đúng?
- Có duplicate spans hoặc thay đổi service name/resource attributes không?
- Error reporting và exception mapping còn đúng không?
- Agent exporter có queue/backpressure hoặc mất dữ liệu không?
- CPU, memory, startup time, p95/p99 latency thay đổi thế nào?

Một agent có thể khởi động thành công nhưng mất auto-instrumentation của framework mới. Đây là regression vận hành, không phải “không có lỗi”.

## 22. Bảo mật và governance khi nạp agent

Java agent là mã chạy trong JVM đích. Dynamic attach vì vậy là thao tác có quyền mạnh, không phải chỉ truy xuất thông tin.

Nguyên tắc:

- Chỉ attach vào JVM được phép quản trị.
- Dùng agent artifact từ nguồn đáng tin, có version/hash/provenance rõ.
- Kiểm soát ai được thay startup args và ai được sử dụng Attach API.
- Không thiết kế endpoint cho người dùng tải JAR tùy ý rồi yêu cầu JVM chạy.
- Bảo vệ options, credentials, telemetry và dữ liệu nhạy cảm.
- Ghi audit: ai attach, process nào, khi nào, artifact và kết quả.
- Có giám sát tài nguyên, phản ứng sự cố và rollback.
- Xác định chính sách cấm/cho phép attach theo môi trường.

### 22.1. Lỗi agent có thể làm hỏng ứng dụng

Transformer trả bytes không hợp lệ có thể dẫn đến verification/linkage errors. Agent giữ reference tới class loaders có thể gây memory leak. Agent tạo I/O đồng bộ trong callback có thể tăng startup latency. Native agent lỗi có thể gây crash vượt phạm vi Java exception.

Không thể coi agent “an toàn” chỉ vì JVM đã load JAR thành công. Cần test correctness, performance và bảo mật theo trust boundary.

### 22.2. Attach trong production cần được phê duyệt

Không dùng attach để vượt security controls, chỉnh sửa hành vi ứng dụng không được phép hoặc thu thập bí mật. Nếu cloud/managed platform không hỗ trợ attach, chọn startup instrumentation hoặc công cụ giám sát được nền tảng cung cấp.

## 23. Container và Kubernetes: các giới hạn thực tế

Attach trong container khó hơn môi trường host truyền thống:

- PID trong container có thể khác PID nhìn từ host.
- Controller và target có thể ở process namespace khác nhau.
- User IDs, file permissions và filesystem mounts khác.
- Agent JAR path cần tồn tại/đọc được từ target JVM.
- Base image tối giản có thể không có `jcmd`, attach tooling hoặc modules tương ứng.
- JVM có thể bị cấu hình vô hiệu hóa attach.
- Một sidecar không tự được cấp quyền attach vào app container.

**Không mặc định PID 1 trong container là PID 1 của host** hoặc rằng controller từ host có thể attach qua ranh giới namespace mà không được phép.

Với observability luôn bật, startup `-javaagent` trong immutable deployment thường dễ audit và tái lập hơn. Dynamic attach thích hợp hơn cho chẩn đoán được ủy quyền và có quy trình kiểm soát rõ.

## 24. Kiểm tra agent compatibility khi nâng JDK

Với mỗi agent phải ghi:

| Chiều kiểm tra | Câu hỏi |
| --- | --- |
| JDK vendor/release | Agent được vendor công bố hỗ trợ JDK đích không? |
| Class-file support | Bytecode engine của agent hiểu major version mới không? |
| Module boundaries | Agent có dùng JDK internals/deep reflection không? |
| Framework compatibility | Agent nhận đúng phiên bản HTTP/ORM/messaging mới không? |
| Agent mode | Startup, dynamic hay cả hai; có retransform không? |
| Native dependencies | Có JNI/JVMTI/shared libs và phiên bản OS phù hợp không? |
| Runtime image | Agent JAR/options/class loader có được triển khai đúng không? |
| Security policy | Attach, secrets, audit và allowed actions có được duyệt không? |
| Functional observability | Traces, spans, metrics và errors đúng chưa? |
| Performance | CPU, memory, startup, latency và GC nằm trong budget không? |

Một JAR có class-file major thấp hơn JVM đích **không tự chứng minh** agent tương thích với mọi class của runtime. Nó còn có thể dùng ASM/Byte Buddy cũ, internal API thay đổi hoặc instrumentation rules chưa cập nhật cho framework.

### 24.1. Công cụ kiểm tra artifact

Lệnh tham khảo:

~~~bash
jar --list --file /opt/agents/monitor.jar

javap -verbose \
  -classpath /opt/agents/monitor.jar \
  example.agent.DemoAgent
~~~

Ví dụ class-file major: Java 8 → 52, Java 17 → 61, Java 21 → 65. Kiểm tra bytecode level của agent chỉ là một phần của compatibility, không thay integration tests.

## 25. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `Failed to find Premain-Class manifest attribute` | JAR không khai báo startup entry point | Kiểm tra manifest |
| `Failed to find Agent-Class manifest attribute` | JAR không khai báo dynamic entry point | Kiểm tra `Agent-Class` |
| `ClassNotFoundException` lúc nạp agent | Manifest class name sai hoặc thiếu JAR | Package, packaging, classpath |
| `NoClassDefFoundError` khi instrument | Helper/dependency không visible | Class loaders/modules |
| `UnsupportedClassVersionError` | JVM không nạp được class-file version | JDK runtime/compile target |
| `Unsupported class file major version 65` trong parser | Tool ASM/Byte Buddy không hiểu Java 21 bytecode | Agent/bytecode library version |
| `InaccessibleObjectException` | Reflection vào package không mở | Agent support, module access |
| `AttachNotSupportedException` | JVM/OS/container không cho attach | Flags, permissions, namespace |
| JDK 21 dynamic loading warning | Agent nạp động; JEP 451 | Xác định nguồn, vendor guidance |
| `AgentLoadException` | Agent JAR/load không hợp lệ | JAR path, manifest, target logs |
| `AgentInitializationException` | `agentmain`/khởi tạo thất bại | Cause/logs tại target JVM |
| Agent báo loaded nhưng thiếu spans | Class đã nạp, không retransform hoặc matcher không khớp | Load timing, capability, framework version |
| Duplicate spans | Nhiều agent cùng instrument | Kiểm kê agent và tracing ownership |
| Startup chậm/crash khi thêm agent | `premain`, transformer, dependency/bytecode lỗi | A/B smoke test, agent logs |
| Native agent không load | ABI/architecture/shared lib thiếu | Container image, native dependencies |

Không nên sửa một lỗi bằng cờ JVM ngẫu nhiên. Cần biết **tool đầu tiên thất bại** và JVM thực sự nhận agent ở chế độ nào.

## 26. Quy trình xử lý lỗi startup agent

1. **Xác nhận JVM command line**: `-javaagent` có ở phần options đúng vị trí không?
2. **Kiểm tra JAR**: file tồn tại, checksum đúng, manifest có `Premain-Class`.
3. **Kiểm tra runtime Java**: class-file version, JDK vendor và modules.
4. **Đọc exception đầu tiên**: phân biệt agent entry point, class loading, helper dependency và transformer.
5. **Thử bỏ agent trong môi trường cô lập**: so xem ứng dụng có chạy không; đây là bước khoanh vùng, không tự kết luận được phép tắt production agent.
6. **Thử agent đúng version vendor-supported**: tránh override ASM/Byte Buddy hoặc dependencies nhúng tùy tiện.
7. **Kiểm thử lại cả observability**: app start không lỗi chưa đủ nếu traces bị mất.
8. **Ghi nguyên nhân và cấu hình đã thay**: không để những workaround module tồn tại không có owner.

## 27. Quy trình xử lý lỗi dynamic attach

1. **Xác định đúng target PID và quyền** trong môi trường được phép.
2. **Xác định target JVM** có attach mechanism và chính sách dynamic agent loading phù hợp.
3. **Xác định controller JDK** có module `jdk.attach` và API hỗ trợ.
4. **Kiểm tra manifest**: JAR có `Agent-Class`/`agentmain` hợp lệ.
5. **Đọc exceptions từ controller và target logs**.
6. **Xác định agent được nạp thành công nhưng có thiếu instrumentation không**.
7. **Kiểm tra preloaded classes và retransform capability** khi cần.
8. **Chạy lại trên staging** với đúng JDK, permissions và thời điểm attach.
9. **Ghi audit và kết quả vận hành**; không attach lặp lại vô hạn để “thử may”.

Nếu chính sách cấm attach, **không** xem việc tắt guardrail là bước chẩn đoán mặc định. Tách yêu cầu quan sát khỏi yêu cầu sửa đổi runtime và chọn phương pháp được duyệt.

## 28. Ma trận thử nghiệm startup và dynamic mode

| Kịch bản | JDK | Chế độ | Cần xác nhận |
| --- | --- | --- | --- |
| Baseline | JDK cũ | Startup | App start, traces/metrics đúng |
| Baseline dynamic | JDK cũ | Attach nếu được phép | `agentmain` và instrumentation |
| Target startup | JDK đích | Startup | Bytecode/modules/agent version |
| Target dynamic | JDK đích | Attach nếu được phép | Dynamic policy/warning/class coverage |
| Target no agent | JDK đích | None | Phân biệt lỗi app và lỗi agent |
| Target multiple agents | JDK đích | Tổ hợp production | Duplicate spans, linkage và overhead |
| Target image | JDK đích | Deployment thật | Container, permissions, flags, JAR |

Đối với dynamic attach, cần một test có **class đã nạp trước agent** và một test class **chỉ nạp sau agent**. Nếu agent không hỗ trợ retransform, giới hạn đó phải được ghi lại; không được báo “dynamic compatible” chỉ vì log `agentmain` xuất hiện.

### 28.1. Dữ liệu cần đo

- Startup latency.
- CPU và heap/native memory overhead.
- GC pauses, threads và class loading.
- p95/p99 latency những endpoint quan trọng.
- Coverage của HTTP/JDBC/messaging instrumentation.
- Traces/spans/error attributes và context propagation.
- Hành vi khi backend thu thập telemetry không sẵn sàng.
- Khả năng rollback cấu hình trên image production.

Một agent không gây exception vẫn có thể làm regression tài nguyên hoặc chất lượng observability.

## 29. Tình huống tổng hợp: Java 17 lên Java 21

Giả sử hệ thống có:

~~~text
orders-service
  Runtime JDK: 17 -> 21
  Startup: vendor APM -javaagent
  Tests: coverage + mocking instrumentation
  Operations: dynamic diagnostic agent if authorized
  Deployment: Linux container
~~~

### 29.1. Kiểm kê

Nhóm xác định APM agent version và support matrix, test tooling versions, embedded ASM/Byte Buddy, class-file major 65, cách JAR được inject vào container và những agent có thể tự attach.

### 29.2. Vấn đề 1: warning JEP 451 trong unit tests

Khi test chạy trên JDK 21, log có warning về dynamic agent loading. Kiểm tra stack/log để xác định mocking library hoặc công cụ nào tự attach. Nếu nhà cung cấp hỗ trợ startup mode, chuyển test JVM sang `-javaagent` theo hướng dẫn rồi chạy lại toàn bộ tests. Không bật rộng rãi quyền dynamic loading trong production chỉ để xử lý warning này.

### 29.3. Vấn đề 2: APM mất JDBC traces

Service khởi động nhưng dashboard không còn một nhóm spans. Có thể APM agent chưa hỗ trợ version JDBC/framework mới, code transform không phù hợp class-file format hoặc container không nạp đúng agent. Nhóm cần xác nhận JAR/hash trên image, logs `premain`, network exporter và traces của cùng workload.

### 29.4. Vấn đề 3: diagnostic attach muộn

Agent được attach vào một JVM đã chạy, nhưng một class framework đã nạp từ startup không được instrument. Xác nhận class loading timing và retransform capabilities. Nếu agent không hỗ trợ thao tác trên class đó, dùng startup instrumentation trên replica canary hoặc một công cụ chẩn đoán khác; không thử attach production liên tục mà không có căn cứ.

### 29.5. Tiêu chí chấp nhận

- Cấu hình JVM/agent trên JDK 21 tái lập được.
- Agent và bytecode libraries được vendor hỗ trợ hoặc có rủi ro được duyệt.
- Test agents/coverage không bị vô hiệu hóa để có build xanh.
- Traces/metrics/errors và context propagation được kiểm thử.
- Performance nằm trong budget.
- Attach chỉ áp dụng ở môi trường, quyền và policy được cho phép.
- Rollout canary và rollback/roll-forward có chủ sở hữu.

## 30. Những sai lầm thường gặp

**“Có `premain` nghĩa là tự attach được.”** Sai: dynamic mode cần `Agent-Class`/`agentmain` và các điều kiện attach riêng.

**“`agentmain` chạy thành công nghĩa là mọi class đã được instrument.”** Sai: class đã nạp có thể cần retransform và có giới hạn JVM.

**“`detach()` gỡ agent khỏi JVM.”** Sai: chỉ ngắt kết nối điều khiển của Attach API.

**“`-javaagent` và `-agentlib` chỉ khác đuôi file.”** Sai: Java instrumentation và native JVMTI có entry points, API và ràng buộc khác.

**“Mọi `Unsupported class file major version` đều do `javac`.”** Sai: thường là bytecode parser/agent chưa hỗ trợ class file mới.

**“Cứ bật `--add-opens` cho mọi module.”** Sai: thay đổi quyền rộng, không thay thế việc nâng agent tương thích.

**“JEP 451 warning là lỗi nghiệp vụ của Java 21.”** Sai: đầu tiên cần xác định agent được nạp động và policy.

**“Agent có thể attach vào bất kỳ process nào nhìn thấy PID.”** Sai: phải có quyền và chính sách cho phép; không được dùng để vượt security boundary.

**“Không cần đưa agent vào dependency inventory.”** Sai: nó là runtime dependency, dù được platform inject.

**“Hai agents chạy riêng được thì chạy chung chắc chắn an toàn.”** Sai: có thể xung đột transformer hoặc duplicate instrumentation.

**“Agent loaded là hoàn thành test.”** Sai: cần kiểm thử traces/metrics, class coverage và overhead.

**“Tắt APM/coverage là cách hoàn thành migration nhanh.”** Sai nếu những công cụ đó là yêu cầu production/quality gate.

**“Có thể sửa mọi class đang chạy mà không restart.”** Sai: redefinition/retransformation có giới hạn về capabilities và cấu trúc class.

**“Chỉ cần test trên máy dev.”** Sai: container namespace, OS permissions, native libraries và JVM flags có thể khác.

## 31. Checklist trước cutover

- [ ] Đã phân biệt Java instrumentation agent và native JVMTI agent.
- [ ] Đã liệt kê agents từ startup scripts, test tooling và platform injection.
- [ ] Mỗi agent có owner, version, checksum và đường cấu hình cụ thể.
- [ ] Đã xác nhận `Premain-Class`, `Agent-Class` và các capabilities cần thiết.
- [ ] Agent vendor support matrix bao phủ JDK/framework mục tiêu.
- [ ] Embedded ASM/Byte Buddy hoặc bytecode parser hỗ trợ class-file version đích.
- [ ] Đã kiểm tra module access, internal APIs và class-loader strategy.
- [ ] Đã xem JEP 451 và chính sách dynamic loading của đúng JDK release/vendor.
- [ ] Với attach, đã xác nhận quyền OS, target PID/namespace và JVM policy.
- [ ] Không dùng `--add-opens` diện rộng không có owner/mốc gỡ.
- [ ] Đã kiểm thử startup agent và, nếu cần, dynamic agent.
- [ ] Đã kiểm thử class đã nạp trước attach và class nạp sau attach.
- [ ] Đã kiểm tra retransformation/redefinition capabilities và class modifiability.
- [ ] Đã kiểm thử nhiều agents cùng lúc theo cấu hình thực tế.
- [ ] Test runner, coverage và mocking còn hoạt động.
- [ ] Đã kiểm tra traces, metrics, errors và duplicate instrumentation.
- [ ] Đã đo startup latency, CPU/memory, GC và p95/p99 latency.
- [ ] Đã xác nhận cấu hình agent trên runtime image thực.
- [ ] Có audit và phê duyệt đối với dynamic attach.
- [ ] Có kế hoạch rollout, rollback/roll-forward và xử lý sự cố.
- [ ] Release notes ghi những thay đổi về mode, flags, agent version và giới hạn.

## 32. Tài liệu tham khảo để đối chiếu theo JDK

Khi migration thực tế, cần đọc tài liệu chính thức cho **đúng bản JDK và agent**:

- **Java SE API — `java.lang.instrument`:** `Instrumentation`, `ClassFileTransformer`, manifest attributes, retransform/redefine.
- **Java SE API — `com.sun.tools.attach` và module `jdk.attach`:** `VirtualMachine`, `loadAgent`, `detach`, exceptions.
- **OpenJDK JEP 451:** cảnh báo và định hướng kiểm soát dynamic agent loading từ JDK 21.
- **JVMTI Specification:** native agents và capabilities.
- **JDK launcher documentation:** `-javaagent`, `-agentlib`, `-agentpath` và JVM arguments.
- **JPMS/Java module documentation:** module boundaries, opens/exports và class access.
- **Gradle/Maven test plugin documentation:** JVM options, test toolchains, coverage integration.
- **Vendor documentation:** compatibility matrix, agent mode và điều kiện class instrumentation.

Không nên suy đoán mặc định của mọi JDK mới từ hành vi quan sát trên JDK 21; flags và security policy có thể thay đổi theo release.

## 33. Kết luận

**Startup agent** và **dynamic attach agent** đều có thể dùng Java Instrumentation API nhưng không đồng nhất. Startup `-javaagent` gọi `premain` trước `main` và thường thuận lợi để instrument các class từ lúc nạp. Dynamic attach qua `VirtualMachine.loadAgent` gọi `agentmain` trên JVM đã chạy, phụ thuộc vào quyền hệ thống, attach mechanism, chính sách JDK và khả năng retransform những class đã nạp.

Trong Java Advance Compatibility Migration, cần coi agent là thành phần runtime có quyền mạnh và có tác động hiệu năng: kiểm kê từ build/test đến container/platform, xác định version và manifest, kiểm tra thư viện bytecode, module/class loaders, cảnh báo JEP 451, quyền attach và native dependencies. Sau đó thử trên JDK và deployment image thực, đối chiếu traces/metrics, tài nguyên, quality gates và behavior của ứng dụng.

Nếu instrumentation luôn cần ngay khi ứng dụng chạy, **startup agent được hỗ trợ và cấu hình khai báo** thường dễ tái lập, giám sát và rollback hơn. Khi cần chẩn đoán một tiến trình đang chạy, dynamic attach chỉ nên được sử dụng trong phạm vi được ủy quyền và được kiểm soát. Migration chỉ thực sự sẵn sàng khi **cả ứng dụng lẫn toàn bộ hệ agent** hoạt động đúng trên runtime đích.
