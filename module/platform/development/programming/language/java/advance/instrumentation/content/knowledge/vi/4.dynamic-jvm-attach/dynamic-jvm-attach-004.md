# VirtualMachine.loadAgent và đường dẫn agent JAR trong môi trường của JVM đích

Khi dùng Attach API để gắn Java agent vào một tiến trình JVM **đang chạy**, điểm dễ sai nhất thường không phải câu lệnh `VirtualMachine.attach(pid)` mà là đường dẫn truyền vào `VirtualMachine.loadAgent(...)`.

**Nguyên tắc:** Tham số đầu tiên của `loadAgent` là **đường dẫn tới file JAR mà JVM đích có thể mở trên hệ thống file nó nhìn thấy**. Attach tool chuyển chuỗi đường dẫn đó cho JVM đích xử lý; API không tự tải JAR từ máy đang chạy attach tool sang tiến trình đích. Hai tiến trình chạy ở cùng máy có thể có cùng không gian đường dẫn, nhưng với container, mount namespace, sandbox hoặc máy/OS khác thì điều này không được giả định.

Bài học thuộc chủ đề **Attach vào JVM**, tập trung vào ý nghĩa của `VirtualMachine.loadAgent`, sự khác nhau giữa môi trường **attacher** và **target**, cách đóng gói JAR, chạy thử và chẩn đoán đường dẫn.

## 1. Hai phía của một thao tác attach

Trong mô hình đơn giản có hai tiến trình Java:

- **Attach tool**: chương trình điều khiển, dùng module `jdk.attach` và lớp `com.sun.tools.attach.VirtualMachine`. Tool nhận PID, thiết lập kết nối attach, ra lệnh tải agent rồi `detach`.
- **Target JVM**: ứng dụng Java đang chạy. Nó nhận yêu cầu, mở JAR theo **cách nhìn hệ thống file của chính nó**, tìm entry point của agent, chạy `agentmain` trong tiến trình đích và trả kết quả về attach tool.

```text
ATTACH TOOL (JVM A)                          TARGET APP (JVM B)
--------------------                         --------------------
VirtualMachine.attach(pid) ----------------> attach listener/provider
                                               |
vm.loadAgent("/opt/agents/probe.jar",         |
             "mode=demo") ------------------> nhận chuỗi path + options
                                               |
                                     mở /opt/agents/probe.jar
                                      trong filesystem TARGET
                                               |
                                     đọc META-INF/MANIFEST.MF
                                     Agent-Class: AgentProbe
                                               |
                                     gọi AgentProbe.agentmain(...)
                                               |
vm.loadAgent(...) <-------------------------- trả kết quả sau agentmain
                                               |
vm.detach() -------------------------------> đóng phiên attach
                                               |
                                     agent đã tải vẫn ở target
```

Trong sơ đồ, `/opt/agents/probe.jar` chỉ là đường dẫn ví dụ. Nó **phải hợp lệ đối với tiến trình target**. Việc dòng lệnh attach chạy trên host khác với nơi JAR được mount ở target dẫn đến hai câu chuyện đường dẫn khác nhau.

### Ba việc không đồng nghĩa

1. `VirtualMachine.attach(pid)` thành công chứng minh tool đã kết nối tới target phù hợp; **chưa chứng minh** target có thể mở agent JAR.
2. `vm.loadAgent(path, options)` thành công nghĩa là yêu cầu nạp agent đã hoàn tất theo hợp đồng API, thông thường sau khi `agentmain` trả về; **chưa chứng minh** agent đã instrument mọi lớp hay tạo được thay đổi nghiệp vụ mong muốn.
3. `vm.detach()` chỉ ngắt kết nối attach tool; **không gỡ** một Java agent vừa được nạp và không khôi phục bytecode mà agent đã biến đổi.

Đây là lý do cần kiểm tra riêng **PID/attach**, **đường dẫn JAR**, **manifest và `agentmain`**, rồi mới kiểm tra hiệu quả instrumentation.

## 2. Hợp đồng của `VirtualMachine.loadAgent`

API trong module `jdk.attach` khai báo:

```java
public abstract void loadAgent(String agent, String options)
        throws AgentLoadException, AgentInitializationException, IOException;

public void loadAgent(String agent)
        throws AgentLoadException, AgentInitializationException, IOException;
```

Hai overload khác nhau ở chỗ overload một tham số tương đương `loadAgent(agent, null)`.

- `agent`: tên đường dẫn file JAR **trong filesystem của target VM**; target diễn giải chuỗi đường dẫn.
- `options`: **một chuỗi** tùy ý chuyển nguyên cho tham số `agentArgs` của `agentmain`; có thể là `null`. Java Attach API không mặc định chia chuỗi đó thành mảng dòng lệnh và không tự biến nó thành đường dẫn.
- `loadAgent`: dùng cho **Java agent JAR**. Đừng nhầm với `loadAgentPath` hoặc `loadAgentLibrary`, là các API nạp **native JVMTI agent library**, chẳng hạn file `.so`/`.dll`.
- `AgentLoadException`: không tìm thấy hoặc không thể khởi động agent theo cơ chế quy định (ví dụ file JAR, manifest, lớp agent có vấn đề).
- `AgentInitializationException`: lỗi trong lúc khởi tạo/chạy `agentmain` được thông báo qua attach protocol.
- `IOException`: lỗi I/O/giao tiếp; ngoài ra `attach(pid)` còn có thể ném `AttachNotSupportedException` trước khi tới bước nạp JAR.

Javadoc mô tả chính xác ý quan trọng: chuỗi đường dẫn JAR được **chuyển đến target VM để target diễn giải**. Đây là khác biệt căn bản giữa “tool có thể gọi `Files.exists(...)` trên một path” và “target thực sự mở được path đó”.

### `Agent-Class` và `agentmain`

JAR để nạp **sau khi JVM đã khởi động** phải có manifest chính khai báo:

```text
Manifest-Version: 1.0
Agent-Class: AgentProbe

```

Và class tương ứng có một trong các phương thức `public static`:

```java
public static void agentmain(String agentArgs, Instrumentation inst);
public static void agentmain(String agentArgs);
```

JVM ưu tiên phiên bản có `Instrumentation` nếu class cung cấp. Đây là **dynamic Java agent**, không phải startup agent dùng `Premain-Class` và `premain` với tùy chọn `-javaagent`. Một JAR có thể khai báo cả `Agent-Class` và `Premain-Class` nếu cài đặt được cả hai chế độ; riêng `loadAgent` cần entry point cho dynamic attach.

## 3. Đường dẫn được nhìn từ phía target: ví dụ theo môi trường

| Môi trường | File JAR có thật tại | Giá trị truyền cho `loadAgent` | Điều phải kiểm tra |
|---|---|---|---|
| Tool và target cùng host Linux, cùng filesystem view | `/home/dev/agents/probe.jar` | `/home/dev/agents/probe.jar` | File tồn tại và target được phép đọc |
| Tool và target cùng host Windows | `C:\lab\agents\probe.jar` | `C:\lab\agents\probe.jar` | Ổ đĩa/thư mục có thể được target truy cập |
| Tool ở host, target trong container; volume host `/srv/agents` gắn vào container `/opt/agents` | Host: `/srv/agents/probe.jar`; container: `/opt/agents/probe.jar` | `/opt/agents/probe.jar` | Target nhìn thấy file ở đường dẫn **bên trong container**; kết nối attach cũng phải khả thi |
| Tool và target ở hai container khác nhau | Tool: `/work/probe.jar`; target: `/app/agents/probe.jar` sau khi mount/copy riêng | `/app/agents/probe.jar` | Mount/PID namespace/permissions không nhất thiết giống nhau |
| Tool có file JAR, target không có file tương ứng | `/home/operator/probe.jar` chỉ ở tool | Không có path hợp lệ cho target | Copy/mount JAR vào nơi target đọc được trước khi gọi |

**Ví dụ container:** nếu host build được `/srv/agents/probe.jar` và volume gắn đến target là `/opt/agents`, thì câu lệnh

```java
vm.loadAgent("/srv/agents/probe.jar", "mode=demo");
```

có thể thất bại vì `/srv/agents` chỉ tồn tại trên host. Đường dẫn phù hợp với **target** có thể là:

```java
vm.loadAgent("/opt/agents/probe.jar", "mode=demo");
```

Nhưng điều này **chỉ giải quyết việc tìm JAR**. Attach đến JVM trong container còn chịu sự chi phối của PID namespace, quyền OS, cơ chế attach provider và cấu hình JVM; có JAR trong container chưa bảo đảm attach được.

### Vì sao đường dẫn tuyệt đối an toàn hơn đường dẫn tương đối?

Javadoc xác định rằng target diễn giải path; do đó `"probe.jar"` không được phép suy thành “JAR nằm cùng thư mục đang chạy tool”. Đường dẫn tương đối có thể bị diễn giải dựa trên bối cảnh làm việc của target/triển khai JVM. Nếu tool được chạy tại `/home/dev` còn target được khởi chạy tại `/opt/service`, hai chuỗi `probe.jar` rất có thể chỉ hai file khác nhau hoặc không tồn tại.

Với ứng dụng production, hãy **đặt JAR ở một đường dẫn tuyệt đối tồn tại trong filesystem view của target** và dùng đúng đường dẫn đó. Cẩn thận với symlink, quyền đọc, ổ đĩa Windows, container mounts và việc thay đổi file trong lúc nạp.

**Không nên làm:**

```java
// Chỉ xác minh path trên máy ATTACH TOOL:
String path = java.nio.file.Path.of("probe.jar")
        .toAbsolutePath().toString();
vm.loadAgent(path);
```

Đoạn trên chỉ đúng khi path tuyệt đối vừa tính **cũng** là đường dẫn target nhìn thấy. Nếu tool chạy ở host còn target chạy trong container, `toAbsolutePath()` của tool không giải quyết được mount-path mapping. Phải tạo/nhận đường dẫn **target-visible** từ cấu hình triển khai.

### Có thể hỏi target về thông tin môi trường gì?

Sau khi attach, API `vm.getSystemProperties()` đọc một số system properties **của target**. Ví dụ:

```java
var properties = vm.getSystemProperties();
System.out.println(properties.getProperty("user.dir"));
System.out.println(properties.getProperty("java.home"));
System.out.println(properties.getProperty("os.name"));
```

`user.dir` thường cho biết working directory được JVM dùng cho việc giải đường dẫn tương đối, nhưng nó **không** chứng minh rằng JAR đã tồn tại/đọc được tại path dự định. `java.home`, `os.name` giúp tránh lập đường dẫn Linux cho target Windows hoặc nhầm vị trí runtime; đó chỉ là **manh mối**, không phải câu trả lời đầy đủ về mount namespace.

## 4. Thực hành Java 17+ chạy được: hai JVM và một agent JAR

Thực hành này dùng **một máy** và **hai cửa sổ terminal** để thấy rõ code nào chạy trong tool, code nào chạy trong target. Không cần thư viện thứ ba. Dùng JDK 17 hoặc JDK 21 có module `jdk.attach`; ví dụ lệnh dưới đây hướng đến HotSpot JDK 21.

Tạo **bốn file cùng một thư mục**: `TargetApp.java`, `AgentProbe.java`, `AttachTool.java`, `agent.mf`.

### 4.1. `TargetApp.java` — tiến trình đích đang chạy

```java
public final class TargetApp {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());
        System.out.println("TARGET_READY");
        while (true) {
            Thread.sleep(60_000);
        }
    }
}
```

Ứng dụng chỉ in PID, báo sẵn sàng rồi giữ JVM sống để tool khác attach. PID thay đổi theo lần chạy. Đây là target mà agent sẽ được nạp vào.

### 4.2. `AgentProbe.java` — code được JVM đích gọi

```java
import java.lang.instrument.Instrumentation;

public final class AgentProbe {
    public static void agentmain(
            String options, Instrumentation instrumentation) {
        System.out.println("AGENTMAIN_RUNNING");
        System.out.println("AGENT_OPTIONS=" + options);
        System.out.println(
                "AGENT_TARGET_USER_DIR=" + System.getProperty("user.dir"));
    }
}
```

Đây là **Java agent** có entry point `agentmain`. Nó chưa đăng ký `ClassFileTransformer` hoặc sửa lớp nào; mục đích là xác nhận agent **được thực thi bên trong target**. Dòng `AGENT_TARGET_USER_DIR` phải được hiểu là system property của **target**, không phải working directory của attach tool.

### 4.3. `AttachTool.java` — tool gọi `VirtualMachine.loadAgent`

```java
import com.sun.tools.attach.VirtualMachine;

public final class AttachTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: AttachTool <target-pid> <target-visible-agent-jar>");
            System.exit(2);
        }

        String targetPid = args[0];
        String jarPathInsideTarget = args[1];

        VirtualMachine vm = VirtualMachine.attach(targetPid);
        try {
            String targetDir =
                    vm.getSystemProperties().getProperty("user.dir");
            System.out.println("TARGET_USER_DIR=" + targetDir);

            vm.loadAgent(jarPathInsideTarget, "mode=demo");
            System.out.println("LOAD_AGENT_OK");
        } finally {
            vm.detach();
        }
    }
}
```

Chú ý:

- `targetPid` phải là định danh mà attach provider nhìn nhận là tiến trình target.
- `jarPathInsideTarget` được truyền **nguyên văn** cho target; code không thay nó bằng `Path.of(...).toAbsolutePath()` ở phía tool.
- `"mode=demo"` là một **chuỗi tùy chọn**, chuyển tới `agentmain(String options, ...)`; nó **không** chỉ nơi đặt JAR.
- `finally` đảm bảo `detach` khi đã attach thành công, kể cả khi `loadAgent` ném exception. `detach` không phải `unloadAgent`.

### 4.4. `agent.mf` — manifest của agent JAR

Tạo file text có nội dung chính xác dưới đây, **kết thúc bằng một dòng trống**:

```text
Manifest-Version: 1.0
Agent-Class: AgentProbe

```

`Agent-Class` là **tên nhị phân đầy đủ của Java class**. Ví dụ không dùng package nên giá trị `AgentProbe` là đủ. Nếu class nằm trong package `com.example.agent` thì giá trị phải là `com.example.agent.AgentProbe`, đồng thời class entry trong JAR phải đúng cấu trúc package. Không dùng đường dẫn file nguồn `AgentProbe.java` thay cho class name.

### 4.5. Biên dịch và đóng gói

Chạy trong thư mục chứa bốn file:

```shell
javac --add-modules jdk.attach TargetApp.java AgentProbe.java AttachTool.java
jar cfm agent-probe.jar agent.mf AgentProbe.class
jar tf agent-probe.jar
```

Trong danh sách từ `jar tf`, kiểm tra có `META-INF/MANIFEST.MF` và `AgentProbe.class`. Nếu muốn xem manifest, dùng công cụ đọc JAR/ZIP; chỉ liệt kê tên entry không chứng minh nội dung `Agent-Class` đúng.

`--add-modules jdk.attach` giúp tool biên dịch và truy cập `com.sun.tools.attach.VirtualMachine`. Module `jdk.attach` là API thuộc **JDK**; nếu dùng runtime image tối giản không có module này ở phía tool, bước compile/run tool sẽ thất bại. Target không cần dùng `VirtualMachine` nên không cần import module đó vào mã `TargetApp`.

### 4.6. Terminal 1 — khởi động target

Tại thư mục trên:

```shell
java -XX:+EnableDynamicAgentLoading -cp . TargetApp
```

Ứng dụng in hai dòng có cấu trúc:

```text
TARGET_PID=<PID thực tế>
TARGET_READY
```

`<PID thực tế>` là ký hiệu để thay bằng con số máy bạn in ra, không phải stdout cố định. Đừng gõ nguyên dấu `< >` vào lệnh attach.

Trên HotSpot JDK 21, `-XX:+EnableDynamicAgentLoading` biểu thị quyền opt-in nạp agent động và tránh cảnh báo tương ứng. Tùy phiên bản và chính sách JVM, khả năng dynamic loading có thể thay đổi; dùng flag khi chạy **target JVM**, không phải chỉ thêm vào terminal chạy `AttachTool`.

Giữ Terminal 1 mở.

### 4.7. Terminal 2 — attach và nạp JAR

Tại **cùng host và cùng nơi nhìn thấy file JAR**, chạy bằng **PID thực tế** từ Terminal 1 và **đường dẫn tuyệt đối của target**:

Ví dụ Linux/macOS, giả sử người dùng đã tạo JAR tại `/home/dev/demo/agent-probe.jar`:

```shell
java --add-modules jdk.attach -cp . AttachTool 12345 /home/dev/demo/agent-probe.jar
```

Ví dụ Windows, giả sử file nằm tại `C:\lab\attach\agent-probe.jar`:

```powershell
java --add-modules jdk.attach -cp . AttachTool 12345 "C:\lab\attach\agent-probe.jar"
```

**Chỉ mang tính mẫu:** thay `12345` bằng PID in ở Terminal 1 và thay đường dẫn bằng nơi JAR thực sự tồn tại/target đọc được. Trong thí nghiệm hai JVM cùng host, đường dẫn tuyệt đối thường trùng nhau. Trong container phải dùng **path từ góc nhìn container của target**.

Quan sát:

- Terminal 2 in một dòng bắt đầu bằng `TARGET_USER_DIR=` (giá trị tùy môi trường), rồi **`LOAD_AGENT_OK`** nếu nạp thành công.
- Terminal 1, là nơi stdout của target đang hiển thị, in thêm:

```text
AGENTMAIN_RUNNING
AGENT_OPTIONS=mode=demo
AGENT_TARGET_USER_DIR=<thư mục làm việc của JVM đích>
```

Dòng `AGENTMAIN_RUNNING` và `AGENT_OPTIONS=mode=demo` là những giá trị cố định của mã ví dụ; dòng `AGENT_TARGET_USER_DIR=...` mang giá trị môi trường thật. Trên một hệ thống ghi stdout của target sang service log hoặc container log, thông điệp agent sẽ nằm trong log target thay vì xuất hiện tại terminal attach.

Sau thí nghiệm, dừng target bằng `Ctrl+C` tại Terminal 1. Nếu thử `loadAgent` lần nữa vào cùng target, hãy tự quyết định có chấp nhận agent `agentmain` bị gọi thêm lần nữa không; API không có cơ chế ngầm bảo đảm mỗi agent chỉ chạy một lần.

## 5. Trường hợp host, Docker, Kubernetes: ba lớp ánh xạ phải đúng

Trong container thường xuất hiện **ba tên khác nhau cho cùng một thứ**:

1. **File ở phía build/host:** nơi công cụ build tạo JAR, ví dụ `/workspace/build/agent-probe.jar`.
2. **File bên trong container target:** kết quả của copy/mount/image layer, ví dụ `/opt/agents/agent-probe.jar`.
3. **Định danh tiến trình:** PID nhìn từ host và PID nhìn từ một container namespace có thể khác nhau.

```text
HOST                                  CONTAINER TARGET
/workspace/build/agent-probe.jar
              |
              | copy/mount
              v
                               /opt/agents/agent-probe.jar
                                             |
                                      TARGET JVM opens
                                      /opt/agents/agent-probe.jar

host PID (example: 30102)             container PID (example: 1)
              \                          /
               \---- attach provider ----/
                  phải dùng ID/namespace phù hợp
```

Đừng lấy `/workspace/build/agent-probe.jar` chỉ vì `Files.exists(...)` ở phía host trả `true`. Đồng thời đừng cho rằng một lệnh `VirtualMachine.attach("1")` từ host sẽ luôn tìm đúng PID 1 trong container: ID được diễn giải theo attach provider và bối cảnh tiến trình.

### Checklist vận hành trong container

- Đảm bảo JAR đã được **copy hoặc mount** vào target trước khi gọi `loadAgent`. Kiểm tra tồn tại từ **bên trong filesystem view của target**, không chỉ trên host.
- Xác nhận người dùng chạy target có quyền **đọc file và đi qua các thư mục cha**; symlink phải trỏ tới nơi target thực sự nhìn thấy.
- Nếu tiện, chạy attach tool ở **cùng container/PID namespace** với target bằng một phương thức được hệ thống cho phép. Nếu tool ở host hoặc sidecar, phải xác minh attach provider, user/UID, mount/PID namespaces và chính sách bảo mật; đường dẫn JAR vẫn phải là path của target.
- Nếu image chỉ có JRE/runtime cắt gọn, tool cần JDK/module `jdk.attach` ở môi trường **chạy tool**. Target có thể không có tool `jcmd`/`jar`, nhưng JVM đích vẫn phải hỗ trợ cơ chế attach/dynamic-agent theo triển khai.
- `user.dir` của target là gợi ý để debug đường dẫn tương đối; không phải bằng chứng file JAR ở đó. Dùng đường dẫn tuyệt đối với mount path đã kiểm tra.
- Khi phải phối hợp giữa Windows host và Linux container, đường dẫn Windows `C:\...` **không** tự được dịch thành đường dẫn Linux. Dùng đường dẫn Linux mà target thực sự thấy.

**Lưu ý kiến trúc:** Attach API dùng kênh gắn vào một VM do attach provider hỗ trợ, không phải dịch vụ “remote load JAR qua Internet”. Không có bước chép file tự động hay chuyển đổi đường dẫn qua máy khác.

## 6. Phân biệt đường dẫn JAR với các đường dẫn khác

Một lệnh `loadAgent` có thể dùng **hai nhóm đường dẫn** khác nhau, và điều này thường khiến lỗi bị chẩn đoán nhầm:

```java
vm.loadAgent("/opt/agents/agent-probe.jar",
             "config=/etc/myapp/agent.yml");
```

- `/opt/agents/agent-probe.jar` là **agent JAR path**, được Attach API chuyển cho JVM đích để mở JAR.
- `config=/etc/myapp/agent.yml` là **agent options string**; JVM chuyển nguyên chuỗi cho `agentmain`. Nếu agent tự parse `config=...` rồi mở file, đó là **hành vi do agent cài đặt**, và code agent đang chạy trong target nên file cấu hình phải truy cập được từ môi trường target.
- Java agent dependencies cũng phải tải được trong context class loading phù hợp. Có JAR chính chưa bảo đảm các dependency do `agentmain` dùng đã được đóng gói/khai báo và đọc được.
- JAR nạp động được đưa vào hệ thống class path theo mô tả API, nhưng không nên coi điều này là cơ chế sửa tùy ý classpath của mọi class loader hoặc cung cấp quyền truy cập tới module nội bộ.
- Nếu agent trả về thành công nhưng không instrument lớp nào, hãy kiểm tra logic `agentmain`/`Instrumentation` riêng. `loadAgent` không tự gọi `retransformClasses` và không tự áp một transformer lên các lớp đã nạp.

Ví dụ sai phổ biến: tool xây `String config = Path.of("agent.yml").toAbsolutePath().toString()` rồi truyền trong `options`, nhưng agent trong container không nhìn thấy absolute path host. Bài toán cũng vậy: phải biết **phía nào sẽ thực sự mở file**.

## 7. Tại sao nên kiểm tra path từ target, không suy từ attach tool?

Giả sử có hai shell:

```text
TOOL:
  user.dir = /home/operator
  /home/operator/agent.jar = EXISTS

TARGET:
  user.dir = /opt/service
  /home/operator/agent.jar = NOT FOUND
  /opt/agents/agent.jar = EXISTS
```

Với dữ kiện này:

```java
vm.loadAgent("/home/operator/agent.jar");
```

không có cơ sở để thành công; phía target không thấy file tương ứng. Ngược lại:

```java
vm.loadAgent("/opt/agents/agent.jar");
```

là lựa chọn có cơ sở, **nếu** JVM target hỗ trợ nạp agent động, file đọc được và manifest/class hợp lệ.

Kiểm tra `vm.getSystemProperties().getProperty("user.dir")` có thể xác nhận target có working directory khác tool, nhưng không thay thế phép kiểm tra quyền truy cập tới JAR. Nếu chưa có đường truyền an toàn để kiểm tra target, sử dụng thông tin deployment có thẩm quyền (volume mapping, image content, mount path) và chẩn đoán exception sau `loadAgent`; không tự đoán dựa trên path host.

## 8. Lỗi thường gặp và cách phân biệt nguyên nhân

| Triệu chứng | Nơi lỗi phát sinh | Kiểm tra nên làm |
|---|---|---|
| `AttachNotSupportedException` tại `attach(pid)` | Chưa attach được | PID sai/không còn sống, runtime/provider không hỗ trợ, user/namespace/quyền attach, cấu hình tắt attach |
| `IOException` lúc attach/gửi lệnh | Kết nối với target | Target đã dừng, kênh IPC, provider hoặc quyền truy cập; xem cause/message |
| `AgentLoadException`: agent path không tồn tại | Đã gửi lệnh nhưng target không mở được JAR | Kiểm tra file trong **filesystem target**, đường dẫn tuyệt đối, mount, quyền đọc và path separator theo OS đích |
| `AgentLoadException`: manifest/entry point sai | Target thấy JAR nhưng không khởi động được agent | `META-INF/MANIFEST.MF` phải có `Agent-Class` đúng; JAR chứa class đó và phương thức `public static agentmain` hợp lệ |
| `AgentInitializationException` | Khởi tạo agent không thành công | Stack trace/log của target, dependency, lỗi trong `agentmain`; không đánh đồng với file không tìm thấy |
| Có `LOAD_AGENT_OK` nhưng không thấy log agent | Quan sát nhầm tiến trình | Xem stdout/log của **target**, không chỉ stdout tool; xác nhận PID và log destination |
| Agent chạy nhưng code ứng dụng không đổi | Hành vi agent | `agentmain` có đăng ký transformer, có yêu cầu retransform cho lớp cũ khi cần, có bytecode hợp lệ không? |
| Host tìm thấy JAR, container báo thiếu | Sai filesystem view | So sánh host build path với target mount path; dùng giá trị target-visible trong `loadAgent` |
| `agentmain` bị gọi nhiều lần | Nạp lại theo yêu cầu | Không giả định JVM tự gỡ/khóa agent; thiết kế init idempotent nếu cho phép reload |
| JVM JDK 21 cảnh báo agent động | Chính sách JVM | Kiểm tra JEP 451, tùy chọn của **target** `-XX:+EnableDynamicAgentLoading` và chính sách triển khai |
| Nạp agent động bị cấm | Chính sách/phiên bản JVM | Kiểm tra `-XX:-EnableDynamicAgentLoading`, phiên bản JVM và cấu hình; cân nhắc `-javaagent` khi khởi động nếu phù hợp |

**Thứ tự chẩn đoán đáng tin cậy:**

1. Xác minh đúng **target PID**, JVM còn sống và attach thành công.
2. Đọc nguyên văn path truyền cho `loadAgent`: path này dành cho **target**, không dành cho tool.
3. Xác minh file JAR tồn tại/đọc được trong filesystem view target, bao gồm mount namespace, symlink và quyền OS.
4. Kiểm tra JAR thật sự có manifest `Agent-Class`, class entry, `agentmain` và dependencies cần thiết.
5. Kiểm tra target cho phép dynamic agent loading; đặc biệt với HotSpot JDK 21 có cảnh báo theo JEP 451 và option opt-in.
6. Phân biệt **load đã hoàn tất** với **mục tiêu instrumentation đã đạt** qua log/behavior do agent chủ động tạo.

### Lỗi “sai đường dẫn” có thể bị ngụy trang bởi lỗi khác

Không nên kết luận `loadAgent` không tìm thấy JAR chỉ vì thấy từ “agent” trong exception. Chẳng hạn, nếu `vm.attach` thất bại, chưa có yêu cầu nạp nào đến target. Nếu `agentmain` ném exception vì thiếu thư viện, target đã đọc được JAR chính nhưng khởi tạo agent thất bại. Nếu `loadAgent` trả về thành công nhưng transformer không được áp, path JAR có thể hoàn toàn đúng.

Ngược lại, kiểm tra `Files.exists(jarPath)` **chỉ trong attach tool** không loại trừ path error đối với target.

## 9. Khía cạnh vận hành: capability và trust boundary

Agent Java khi chạy `agentmain` có thể sử dụng `Instrumentation` để quan sát hoặc biến đổi bytecode trong JVM đích. Vì vậy việc cho phép tải agent là quyết định cấu hình của ứng dụng/hệ thống, cần được chủ sở hữu JVM cho phép. Không dùng attach như cách vượt qua quyền OS, container isolation hay chính sách runtime.

Với **HotSpot JDK 21**:

- Dynamic agent loading vẫn được hỗ trợ nhưng JEP 451 đưa cảnh báo khi nạp Java/JVMTI agent động trong trường hợp không opt-in.
- `-XX:+EnableDynamicAgentLoading` trên JVM **target** là opt-in rõ ràng, đồng thời tránh cảnh báo liên quan trong JDK 21.
- `-XX:-EnableDynamicAgentLoading` có thể dùng để tắt khả năng nạp agent động. Chính sách mặc định có thể thay đổi ở JDK/VM khác; hãy dựa trên tài liệu đúng phiên bản runtime.
- Java agent khởi động cùng ứng dụng bằng `-javaagent:path/to/agent.jar` dùng chu kỳ `premain` khác với dynamic `loadAgent`/`agentmain`.

Để triển khai an toàn, người vận hành thường ghim phiên bản/hash agent JAR, kiểm tra manifest/dependencies và kiểm soát quyền ghi nơi lưu JAR, bởi một thay đổi JAR giữa lúc xác minh và lúc target mở file có thể dẫn đến tải nội dung khác dự tính. Đây là vấn đề độ tin cậy của artifact, không riêng cú pháp `loadAgent`.

## 10. Bài tập kiểm tra kiến thức

**Câu 1.** Attach tool chạy trên host có `/srv/build/probe.jar`; target trong container có cùng JAR ở `/opt/agents/probe.jar`. Truyền path nào?

> `/opt/agents/probe.jar`, vì **target JVM** là phía mở file. Ngoài ra phải bảo đảm attach tới đúng target có thể thực hiện được.

**Câu 2.** `vm.loadAgent("./probe.jar")` có nhất định tìm file ở working directory của tool không?

> Không. Target là nơi diễn giải đường dẫn; nên dùng đường dẫn tuyệt đối target-visible để tránh lệ thuộc context.

**Câu 3.** `vm.getSystemProperties().getProperty("user.dir")` phản ánh JVM nào?

> JVM **target** sau khi attach, không phải tiến trình attacher.

**Câu 4.** JAR chỉ có `Premain-Class` và `premain`. Dùng `loadAgent` đã đủ chưa?

> Chưa. Dynamic attach cần `Agent-Class` và entry point `public static agentmain` hợp lệ.

**Câu 5.** `loadAgent` thành công rồi `detach`. Agent có bị gỡ không?

> Không. `detach` đóng kết nối attach; agent có thể còn hoạt động trong target.

**Câu 6.** `loadAgent` trả về nhưng class đã nạp chưa đổi hành vi. Kết luận file path sai được không?

> Không. Path có thể hoàn toàn đúng; agent chưa đăng ký transformer, chưa yêu cầu retransform, hoặc logic instrument không áp dụng lớp đó.

**Câu 7.** `loadAgent(path, "config=/etc/agent.yml")` có tự đọc file YAML không?

> Không. Đó là chuỗi options dành cho `agentmain`; chỉ code agent tự parse và mở file theo filesystem target mới đọc YAML.

**Câu 8.** Tại sao cùng PID hiển thị trong container và host có thể chỉ các đối tượng khác nhau?

> PID được diễn giải trong bối cảnh namespace/attach provider. Không được giả định ID in trong một namespace dùng nguyên vẹn ở mọi nơi.

## Tài liệu tham khảo chính thức

- [Java SE 21 — VirtualMachine (jdk.attach)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): hợp đồng `loadAgent`, tham số JAR path thuộc target, `getSystemProperties`, `attach`, `detach` và ngoại lệ.
- [Java SE 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest `Agent-Class`, `agentmain`, lifecycle dynamic agent, `Premain-Class` và `premain`.
- [Java SE 21 — module jdk.attach](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/module-summary.html): các package của Attach API.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): cảnh báo và định hướng chính sách dynamic agent loading từ JDK 21.
- [Oracle JDK 21 release notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): chú thích về `EnableDynamicAgentLoading`.

**Điểm cần nhớ:** `VirtualMachine.loadAgent` chỉ nhận một **chuỗi đường dẫn**, không chuyển JAR sang JVM đích. Hãy tìm đúng PID, đưa JAR vào filesystem target, truyền **đúng absolute path mà target nhìn thấy**, bảo đảm manifest/`agentmain` hợp lệ, rồi xác minh kết quả ngay trong target.