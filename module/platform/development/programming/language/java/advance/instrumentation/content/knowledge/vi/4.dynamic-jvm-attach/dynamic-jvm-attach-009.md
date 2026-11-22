# Quyền hệ điều hành, container, self-attach và khả năng hỗ trợ của nhà cung cấp khi attach vào JVM

**Ngữ cảnh:** Java Advance → instrumentation → **Attach vào JVM**. Một công cụ như `jcmd`, `jstack` hoặc chương trình dùng `com.sun.tools.attach.VirtualMachine.attach(...)` có thể không kết nối được với JVM đang chạy, ngay cả khi PID tồn tại. Nguyên nhân thường thuộc **quyền hệ điều hành, PID/container namespace, cơ chế attach của JVM, chính sách nạp agent hoặc implementation của nhà cung cấp**.

Bài này giúp phân biệt các tầng quyền, tự kiểm tra self-attach và external attach, hiểu điều kiện Docker/Kubernetes, nhận biết khác biệt giữa HotSpot, Eclipse OpenJ9 và GraalVM Native Image, rồi chẩn đoán sự cố theo đúng bước. Ví dụ sử dụng Java 17+ và chủ yếu giải thích hành vi **HotSpot**; cờ `-XX` và chi tiết kết nối cần đối chiếu tài liệu của VM thực tế.

## 1. Attach là gì? Vì sao có nhiều lớp điều kiện?

```text
Client tool (JDK / Attach API)                JVM đang chạy (target)
  │                                                │
  ├── tìm đúng PID ─────────────────────────────────►│
  ├── kiểm tra provider & runtime ─────────────────►│
  ├── OS: user/group, signal, filesystem ─────────►│
  ├── container: PID/mount namespace, /proc ───────►│
  ├── handshake với attach listener ───────────────►│
  │                                                │
  ├── diagnostic command / getSystemProperties ───►│  [không nạp agent]
  └── loadAgent(JAR) ───────────────────────────────►│  [thêm policy agent]
```

**Ba thao tác khác nhau:**

| Thao tác | Ví dụ | Yêu cầu bổ sung |
| --- | --- | --- |
| Xem process bằng OS | `ps`, `id`, `/proc/<pid>` (Linux) | Quyền OS và namespace; chưa kết nối JVM |
| Attach và lấy thông tin | `jcmd PID VM.version`, `VirtualMachine.attach` + `getSystemProperties` | Provider tương thích, quyền OS, attach listener/mount |
| Attach rồi nạp agent động | `VirtualMachine.loadAgent("agent.jar")` | Ngoài attach còn có chính sách dynamic agent, manifest `Agent-Class`, `agentmain` và JAR hợp lệ |

**`jcmd PID VM.version` chạy được không chứng minh `loadAgent` sẽ chạy được.** Ngược lại, một lỗi `loadAgent` không nhất thiết đồng nghĩa với việc OS không cho attach.

Một Java agent được đưa vào **lúc khởi động JVM** qua `-javaagent:path/to/agent.jar` là đường đi khác: JVM gọi `premain`. Khi agent được nạp vào JVM **đang chạy**, JVM gọi `agentmain`. Hai hình thức này có điều kiện và chính sách khác nhau.

## 2. Quyền hệ điều hành

### 2.1. Linux/Unix: effective UID/GID và quyền process

Theo tài liệu Oracle `jcmd`, công cụ chẩn đoán cần chạy trên **cùng máy** với JVM target và có **cùng effective user và group identifiers** được dùng để chạy JVM đó. Trên hệ thống dịch vụ, người đang mở terminal rất có thể **khác** tài khoản chạy ứng dụng.

Kiểm tra read-only trên Linux, thay PID ví dụ bằng giá trị thật:

```bash
id
ps -o pid,ppid,user,uid,euid,group,gid,egid,args -p 12345
jcmd 12345 VM.version
```

- `UID` và `EUID` là user ID thông thường và effective user ID; `GID`/`EGID` tương tự cho group. Xác nhận **numeric identity** thay vì chỉ dựa vào tên tài khoản.
- PID có thể được tái sử dụng khi service/container restart. Xác minh process đang sống và thực sự là JVM muốn kiểm tra.
- Quyền gửi signal, truy cập `/proc/<PID>`, quyền trên thư mục tạm và cơ chế IPC có thể ảnh hưởng đến attach trên HotSpot/Linux.
- SELinux, AppArmor, seccomp, namespace, ACL hoặc policy bảo vệ process có thể chặn thao tác dù hai process nhìn thấy nhau.
- Chạy bằng `root` không tự động bảo đảm thành công: socket permission checks, namespace hoặc hardening vẫn có thể ngăn kết nối. Quyền cao hơn chỉ nên được dùng khi chính sách vận hành cho phép.

Trong HotSpot Unix/Linux, khi debug có thể gặp các file/socket kiểu `.attach_pid<PID>` hoặc `.java_pid<PID>`. Đây là **chi tiết triển khai** của HotSpot, không phải chuẩn Java SE áp dụng cho mọi VM. Với OpenJ9, thư mục attach mặc định là `.com_ibm_tools_attach` và cơ chế IPC khác.

**Tránh sửa nhanh bằng cách mở quyền toàn cục:** không `chmod 777` tùy tiện, xóa socket attach đang được sử dụng, đổi owner của `/tmp`, tắt SELinux/AppArmor hoặc chạy container `--privileged` chỉ để thử. Những thay đổi ấy có thể gây lỗi cho process khác hoặc giảm an toàn của cả host.

### 2.2. Windows và macOS

Trên **Windows**, quyền process/token, ACL, session, integrity level và phần mềm bảo vệ hệ thống có thể ảnh hưởng; không dùng những bước kiểm tra `/proc`, `/tmp` dành cho Linux. Trên **macOS**, quyền người dùng, sandbox và chính sách bảo vệ tiến trình có thể hạn chế attach. Với cả hai, dùng công cụ đi cùng JDK/vendor của target và đọc lỗi theo API/OS cụ thể, không tự suy luận từ thông báo của Linux.

## 3. HotSpot: tắt attach khác với cấm agent động

| Cờ ở thời điểm **khởi động JVM target** | Ý nghĩa thực tế |
| --- | --- |
| `-XX:+DisableAttachMechanism` | Tắt cơ chế cho các tool attach vào HotSpot. Các yêu cầu `jcmd`/Attach API thường không thành công |
| `-XX:-EnableDynamicAgentLoading` | Không cho nạp agent động sau khi JVM đã khởi động; **không đồng nghĩa** tắt mọi diagnostic command |
| `-XX:+EnableDynamicAgentLoading` | Cho phép agent động bằng một lựa chọn chủ động trên HotSpot; liên quan cảnh báo JEP 451 |
| `-Djdk.attach.allowAttachSelf=true` | Phía JVM **gọi Attach API**, cho phép một tiến trình HotSpot tự attach vào chính PID của mình, nếu các điều kiện khác hợp lệ |

Chú ý:

1. **Đúng process:** `-XX:+DisableAttachMechanism` và `EnableDynamicAgentLoading` phải xét ở **target**. Đưa cờ vào công cụ client không sửa được chính sách đã có ở target.
2. **Đúng phạm vi:** `allowAttachSelf` chỉ xử lý trường hợp client và target là **cùng một JVM**; không cấp thêm đặc quyền OS hoặc mở đường xuyên container.
3. **Đúng thời điểm:** nhiều tùy chọn được JVM lấy lúc startup; không thể coi `System.setProperty` giữa chừng là cách thay đổi chính sách self-attach.
4. **Đúng implementation:** cờ `-XX` là đặc tính của VM; không suy đoán mọi nhà cung cấp áp dụng hoàn toàn giống HotSpot.

### JDK 21+ và JEP 451

Từ **JDK 21**, JEP 451 làm HotSpot cảnh báo khi **Java/JVMTI agent được nạp động** vào JVM đang chạy, để chuẩn bị chính sách chặt hơn trong tương lai. Trên những bản JDK mà việc nạp động được cho phép mặc định, thông báo là **warning**, không tự đồng nghĩa attach thất bại. Cờ `-XX:+EnableDynamicAgentLoading` khi khởi động là một cách thể hiện chủ đích cho phép và tránh cảnh báo. `-XX:-EnableDynamicAgentLoading` giúp thử hành vi bị cấm. Khi nâng JDK, xác minh mặc định của release thực tế; không coi lời hứa về bản tương lai là thay đổi đã xảy ra.

Ví dụ **target** đã được chủ sở hữu cho phép agent động:

```bash
java -XX:+EnableDynamicAgentLoading -jar service.jar
```

Ví dụ bảo vệ target khỏi agent nạp sau khi khởi động, nhưng vẫn có thể dùng một số lệnh chẩn đoán theo chính sách VM:

```bash
java -XX:-EnableDynamicAgentLoading -jar service.jar
```

Không có cờ nào ở đây thay thế yêu cầu đúng user/group, provider, namespace hoặc JAR agent hợp lệ. `-javaagent` khi startup và `loadAgent` sau startup là hai đường khởi tạo khác nhau.

## 4. Self-attach: một JVM tự kết nối vào chính nó

**Self-attach** xảy ra khi một chương trình gọi `VirtualMachine.attach` với PID của chính chương trình. **HotSpot từ JDK 9** mặc định ngăn cơ chế này, kể cả khi UID/GID hoàn toàn trùng nhau. Lỗi thường thấy:

```text
java.io.IOException: Can not attach to current VM
```

Trên HotSpot, có thể cho phép trong môi trường được quyền thử nghiệm bằng property **ở lúc JVM khởi động**:

```bash
java -Djdk.attach.allowAttachSelf=true ...
```

Property này **không** đồng nghĩa `-XX:+EnableDynamicAgentLoading`. Một self-attach chỉ đọc system properties không cần nạp agent. Nếu thư viện dùng self-attach để gọi `loadAgent`, nó sẽ gặp **cả hai** chính sách.

### 4.1. Chương trình Java 17+ kiểm tra Attach API

Tạo tệp **`AttachProbe.java`** sau. Đây là chương trình Java độc lập sử dụng module `jdk.attach`, không phụ thuộc thư viện bên ngoài:

```java
import com.sun.tools.attach.VirtualMachine;
import java.util.Properties;

public final class AttachProbe {
    private AttachProbe() {}

    public static void main(String[] args) throws Exception {
        String pid = args.length == 0 || "self".equals(args[0])
                ? Long.toString(ProcessHandle.current().pid())
                : args[0];

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            Properties props = vm.getSystemProperties();
            System.out.println("ATTACHED");
            System.out.println("VM_NAME_PRESENT="
                    + (props.getProperty("java.vm.name") != null));
        } finally {
            vm.detach();
        }
    }
}
```

Biên dịch và thử self-attach bằng **JDK 17+ dùng HotSpot**, trong môi trường không cấm attach:

```bash
javac --add-modules jdk.attach AttachProbe.java
java --add-modules jdk.attach -Djdk.attach.allowAttachSelf=true AttachProbe self
```

Khi việc attach và đọc system properties thành công, stdout của chương trình:

```text
ATTACHED
VM_NAME_PRESENT=true
```

Nếu bỏ `-Djdk.attach.allowAttachSelf=true`, HotSpot thường ném lỗi `Can not attach to current VM` trước khi in `ATTACHED`. Văn bản lỗi/stack trace có thể thay đổi theo JDK; đừng dùng nguyên văn exception như một hợp đồng API.

`getSystemProperties` chỉ đọc cấu hình target và không tải agent. Chạy thành công ví dụ trên **chưa kiểm tra** việc nạp Java agent động.

### 4.2. External attach bằng một JVM thứ hai

Tạo tệp **`TargetApp.java`**:

```java
public final class TargetApp {
    private TargetApp() {}

    public static void main(String[] args) throws InterruptedException {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());
        Thread.sleep(120_000);
    }
}
```

Trong **Terminal A**:

```bash
javac TargetApp.java
java TargetApp
```

`TargetApp` in ra `TARGET_PID=...` với PID thực tế, rồi sống thêm khoảng hai phút. Trong **Terminal B** cùng máy, chạy bằng effective user/group phù hợp, thay `12345` bằng PID vừa in:

```bash
java --add-modules jdk.attach AttachProbe 12345
jcmd 12345 VM.version
```

Nếu `AttachProbe` attach thành công, stdout của **riêng lệnh AttachProbe**:

```text
ATTACHED
VM_NAME_PRESENT=true
```

Lệnh `jcmd` có output phụ thuộc phiên bản/nhà cung cấp, không có chuỗi stdout cố định. **External attach không cần allowAttachSelf** vì caller và target là hai JVM khác nhau. Tuy nhiên vẫn cần OS, provider, runtime và container cho phép. Có thể dùng `jcmd 12345 help` để xem diagnostic commands thực sự hỗ trợ.

Về API, luôn gọi `vm.detach()` khi hoàn thành; `VirtualMachine` không phải `AutoCloseable` để mặc định dùng `try`-with-resources trong ví dụ này.

## 5. Container: PID namespace và mount namespace là hai vấn đề riêng

Một container làm thay đổi cách công cụ nhìn PID, filesystem và quyền process:

| Thành phần | Vì sao ảnh hưởng attach? |
| --- | --- |
| **PID namespace** | JVM có thể là PID `1` bên trong container nhưng có PID khác trên host; PID mà client dùng phải xác định đúng target trong namespace client |
| **Mount namespace** | Client có thể nhìn thấy thư mục `/tmp` khác JVM, khiến các file/socket attach không truy cập được |
| **User namespace** | Numeric UID/GID có thể được ánh xạ khác nhau; hai process hiện cùng tên user không bảo đảm kernel coi là cùng identity |
| **`/proc` visibility** | `/proc/<pid>` bị ẩn, không mount hoặc bị policy hạn chế sẽ ảnh hưởng việc tra cứu/handshake trên một số hệ thống |
| **Security profile** | seccomp, SELinux, AppArmor, capabilities và policy process/signal có thể từ chối thao tác |
| **Runtime image** | Image tối giản thường không có `jcmd`, `ps`, shell hoặc module `jdk.attach` |

Tài liệu Oracle `jcmd` nhấn mạnh `jcmd -l` không liệt kê được JVM nằm trong Docker process namespace tách biệt; dùng `ps`/PID trực tiếp. **Không thấy PID trong `jcmd -l` không có nghĩa process chết**.

### 5.1. Docker: thử trong đúng container, đúng user

Nếu image có công cụ JDK và JVM thực sự là PID 1, ví dụ:

```bash
docker exec --user 10001:10001 my-java-app jcmd 1 VM.version
```

Lệnh trên **chỉ là mẫu có giả định**: container `my-java-app` đang chạy, JVM là PID `1`, target chạy với UID/GID `10001` và `jcmd` tồn tại. Nếu PID 1 là shell/init, tìm PID JVM bên trong container trước. Không tự đoán UID từ tên `app`.

Kiểm tra read-only bên trong container **nếu có shell và tools**:

```bash
id
ps -eo pid,ppid,uid,gid,args
java -version
jcmd -l
```

Nếu image production là distroless hoặc custom `jlink` không chứa `jcmd`, đó là **thiếu công cụ phía client**, chưa đủ kết luận JVM target đã tắt attach. Dùng giải pháp diagnostic đã chuẩn bị trong triển khai hoặc môi trường debug phù hợp namespace/quyền, thay vì tự sửa quyền toàn host.

### 5.2. Kubernetes: cùng Pod chưa chắc đã nhìn thấy nhau

- **`kubectl exec` trong chính application container**: có cơ hội nhìn đúng PID/mount namespace nhưng công cụ có thể không được đóng gói và user vẫn phải phù hợp.
- **Sidecar**: Pod không mặc định chia sẻ process namespace; `shareProcessNamespace` chỉ giải quyết một phần của vấn đề nhìn PID, **không tự chia sẻ mount namespace** hay quyền.
- **Ephemeral debug container**: khả năng nhìn target phụ thuộc runtime và `--target`/security context; có binary `jcmd` không bảo đảm có quyền truy cập tiến trình.
- **Rootless, read-only filesystem, private `/tmp`**: cần xét UID mapping, vùng tạm và đường IPC trước khi kết luận JVM lỗi.

Trình tự hữu ích khi attach từ container: xác nhận process và PID **theo namespace tool** → kiểm tra effective UID/GID → kiểm tra mount/temp/`/proc` và security policy → kiểm tra VM vendor/flags → thử lệnh chẩn đoán nhỏ. Trong một số HotSpot/Linux hiện đại, tool có thể truy cập vùng tạm của JVM qua `/proc/<pid>/root/tmp`; không được suy ra “phải dùng chung `/tmp`” hay “không cần chia sẻ gì” như quy tắc tuyệt đối.

Không xóa file/socket `.java_pid...`, đổi quyền `/tmp` hàng loạt hoặc chạy container `--privileged` để xử lý timeout. Cần giữ nguyên đường attach và chính sách bảo mật của các workload khác.

## 6. Các JVM và nhà cung cấp khác nhau hỗ trợ những gì?

Tên **Java 17/21/25/26** chưa đủ để xác định implementation. Cần biết vendor, VM, OS, runtime image, module hiện có và compatibility của công cụ.

| Triển khai | Khả năng và giới hạn |
| --- | --- |
| **Oracle JDK / OpenJDK dùng HotSpot** | Hỗ trợ `jdk.attach` và `jcmd` khi bản JDK có các thành phần tương ứng; bị ràng buộc bởi quyền OS, HotSpot flags và runtime image |
| **Bản phân phối dùng HotSpot** như Temurin, Corretto hoặc các build HotSpot khác | Thường dùng cơ chế HotSpot, nhưng phải xác minh cờ, tool, version và packaging thực tế của bản build |
| **Eclipse OpenJ9** | Có Attach API riêng, tương đương ở mức API nhưng theo tài liệu chỉ kết nối được từ **OpenJ9 tới OpenJ9**, không dùng provider OpenJ9 attach HotSpot; có cờ riêng và cơ chế IPC riêng |
| **GraalVM chạy ở chế độ JVM** | Khi chạy `java` trên HotSpot-based JVM, nhiều cơ chế JDK/HotSpot tương ứng; cần xác định đang chạy JVM chứ không phải Native Image |
| **GraalVM Native Image** | Có thể hỗ trợ **một số** diagnostic commands qua `jcmd` khi build với `--enable-monitoring=jcmd`; không tương đương Attach API đầy đủ hay tải Java agent động |
| **Custom `jlink` runtime / image tối giản** | Có thể không chứa `jdk.attach` hoặc binary `jcmd`; thiếu tool/module không chứng minh toàn bộ VM không hỗ trợ cơ chế attach |

**Eclipse OpenJ9:** tài liệu dự án ghi `-Dcom.ibm.tools.attach.enable=yes|no` để bật/tắt Attach API. Mặc định bật trên Linux/macOS/Windows/AIX, **ngoại trừ z/OS** có mặc định khác và các hạn chế OMVS. OpenJ9 dùng `.com_ibm_tools_attach` làm thư mục IPC mặc định, có tùy chọn `com.ibm.tools.attach.directory` và quy tắc permission riêng. Do đó không lấy cơ chế socket HotSpot áp vào OpenJ9; driver/provider không tương thích chéo.

**GraalVM Native Image:** tài liệu chính thức của Oracle GraalVM for JDK 25 mô tả tùy chọn build:

```bash
native-image --enable-monitoring=jcmd YourApplication
```

Đây là **lệnh mô tả cấu hình build**, chỉ chạy khi đã có ứng dụng đầu vào và bộ công cụ Native Image phù hợp. Các diagnostic commands trên Native Image là tập được hỗ trợ riêng; tài liệu còn ghi giới hạn platform, trong đó tính năng trên không có sẵn cho Windows ở phiên bản được mô tả. Việc `jcmd PID help` trả kết quả **không chứng minh** JVM instrumentation, `agentmain` hay `VirtualMachine.loadAgent` áp dụng cho Native Image.

**Cùng phiên bản tool:** Oracle lưu ý chạy các diagnostic tools của một phiên bản JDK để xử lý VM ở phiên bản khác là trường hợp **không được hỗ trợ**. Nên ưu tiên cùng major version, lý tưởng cùng vendor/distribution, dù một số lệnh có thể vẫn hoạt động khi khác bản.

### 6.1. Xác định runtime thực tế

Trên máy client:

```bash
java -version
javac -version
jcmd -h
java --list-modules
```

Trong một method Java đang chạy trên target, có thể in các thuộc tính (đây chỉ là **fragment**, không phải class độc lập):

```java
System.out.println(System.getProperty("java.vendor"));
System.out.println(System.getProperty("java.vm.name"));
System.out.println(System.getProperty("java.vm.version"));
System.out.println(System.getProperty("java.runtime.version"));
```

`java.vendor` không đồng nhất với `java.vm.name`: một là nhà cung cấp bản phân phối, một là VM implementation. `--add-modules jdk.attach` chỉ yêu cầu **resolve một module có sẵn**; không thể thêm module vào image đã bị cắt bỏ. Nếu target đã attach được, `jcmd PID VM.version`, `VM.command_line` và `help` hỗ trợ việc đối chiếu, nhưng nội dung thực tế có thể phụ thuộc vào VM.

## 7. Attach được vẫn có thể không nạp được agent

Với Java instrumentation bằng agent động, kiểm tra thêm:

1. JAR có `META-INF/MANIFEST.MF` khai báo `Agent-Class: com.example.Agent`.
2. Agent khai báo `public static void agentmain(String args, Instrumentation inst)` hoặc biến thể một tham số được chuẩn định nghĩa.
3. Target cho phép nạp động theo flags/release; không bị `-XX:-EnableDynamicAgentLoading` chặn.
4. Đường dẫn JAR phải dùng được từ ngữ cảnh thực thi của target; lưu ý mount namespace, package và quyền truy cập.
5. Class file version, dependencies, class loader và nhu cầu `redefineClasses`/`retransformClasses` tương thích VM.

API minh họa **đặt trong một client Java đã có biến `targetPid`**, chưa phải chương trình độc lập:

```java
VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    vm.loadAgent("/opt/agents/monitor-agent.jar", "mode=sample");
} finally {
    vm.detach();
}
```

`AttachNotSupportedException` hoặc `IOException` thường xuất hiện khi kết nối thất bại; `AgentLoadException`/`AgentInitializationException` có thể xảy ra ở giai đoạn nạp/khởi tạo agent sau khi attach. Một lỗi agent không tự động chứng minh lỗi OS. Nếu chỉ cần read-only diagnostics, dùng commands phù hợp mà không tải agent.

## 8. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách phân biệt |
| --- | --- | --- |
| `jcmd: command not found` | Thiếu executable / PATH / image tối giản | Kiểm tra tool image, `JAVA_HOME`, JDK modules |
| `jcmd -l` không thấy JVM | Khác PID namespace, không được phép liệt kê | Xác định PID theo `ps` ở namespace phù hợp và thử PID trực tiếp |
| `Operation not permitted` / `Permission denied` | UID/GID hoặc OS policy | So effective identity, kiểm tra security context/logs |
| `Can not attach to current VM` | Self-attach bị HotSpot chặn mặc định | Xác nhận caller PID = target PID; dùng process ngoài hoặc property ở startup |
| `AttachNotSupportedException` | Provider không tương thích, sai PID hoặc VM không hỗ trợ attach | So vendor, phiên bản, process sống và attach flags |
| `Unable to open socket file ... doesn't respond` | Timeout, namespace/temp không đúng, JVM treo hoặc attach bị chặn | Kiểm tra PID, JVM health, `/proc`, temp và logs |
| `-XX:+DisableAttachMechanism` trên target | JVM không mở attach mechanism | Kiểm tra cấu hình khởi động; muốn thay thường phải restart |
| `Dynamic agent loading is not enabled` | Cấm agent nạp động | Phân biệt `jcmd` thành công với `loadAgent` thất bại; xét flags target |
| `AgentLoadException` / `AgentInitializationException` | JAR/manifest/agentmain/dependencies/path lỗi | Xem manifest, target logs và stack trace |
| Tool JDK khác version | Không được vendor bảo đảm tương thích | Dùng tool cùng version và kiểm tra VM thực tế |
| HotSpot tool không attach OpenJ9 | Provider/implementation mismatch | Dùng hướng dẫn và tool OpenJ9 tương thích |
| Native Image `jcmd` có ít lệnh | Tập diagnostic commands riêng | Kiểm tra cấu hình `--enable-monitoring` và tài liệu đúng bản |

Trình tự kiểm tra nên là: **(1) nhận diện JVM/PID → (2) tool/vendor/version → (3) OS UID/GID → (4) PID & mount namespaces → (5) target attach policy → (6) `jcmd VM.version` hoặc `getSystemProperties` → (7) chỉ khi cần mới thử nạp agent**. Ghi rõ bước đầu tiên thất bại, mã lỗi, launch flags và môi trường; đừng đánh đồng tất cả lỗi với “Java thiếu quyền”.

## 9. Tình huống áp dụng

**Tình huống A — UID khác nhau.** Service chạy `svcuser` nhưng người dùng chạy `jcmd` từ terminal bằng `devuser`. `ps` thấy JVM song attach bị từ chối. Cần chạy tool dưới effective identity được ủy quyền hoặc dùng đường chẩn đoán được quản trị cấu hình, không mở quyền filesystem toàn host.

**Tình huống B — JVM trong Kubernetes.** Sidecar có `jcmd` nhưng `jcmd -l` trống. Trước khi sửa JVM flags, kiểm tra hai container có chia sẻ PID namespace không; rồi tiếp tục xác minh UID, mount/temp/`/proc` và policy. “Cùng một Pod” chưa đủ bằng chứng.

**Tình huống C — Self-attach.** Thư viện trong test tự attach vào PID của test JVM và nhận `Can not attach to current VM`. Với HotSpot có thể dùng property `jdk.attach.allowAttachSelf` lúc start, hoặc tách ra helper JVM khác. Nếu sau đó còn cần `loadAgent`, kiểm tra JEP 451 và `EnableDynamicAgentLoading` riêng.

**Tình huống D — Chẩn đoán được, nạp agent không được.** `jcmd PID VM.version` chạy bình thường nhưng target khởi động với `-XX:-EnableDynamicAgentLoading`. Đây là kết quả nhất quán: attach diagnostic khác policy agent động. Không nên tìm cách vượt policy; nếu agent là yêu cầu nghiệp vụ được chấp thuận, lên phương án `-javaagent` lúc startup hoặc cho phép theo cấu hình chính thức.

**Tình huống E — Đổi JVM.** Một tool HotSpot không attach được target OpenJ9. Kiểm tra provider và công cụ tương thích với OpenJ9, cờ `com.ibm.tools.attach.enable` và IPC directory riêng. Không dùng `allowAttachSelf` để “sửa” incompatibility giữa hai VM implementations.

## 10. Tự kiểm tra

1. **`jcmd PID VM.version` thành công nhưng `loadAgent` thất bại. Có mâu thuẫn?**  
   Không. Có thể đủ quyền chẩn đoán mà thiếu quyền/policy nạp agent động.
2. **Self-attach HotSpot thất bại dù UID giống hệt. Vì sao?**  
   Từ JDK 9 HotSpot chặn attach vào chính VM mặc định; cần property ở startup hoặc external helper nếu được phép.
3. **JVM PID 1 trong container nhưng PID 48001 trên host. Tool ở trong container dùng PID nào?**  
   PID mà tool thấy trong namespace của nó, thường là 1 trong giả định đã nêu; phải xác minh target.
4. **Image không có `jcmd`, có suy ra target không hỗ trợ Attach API?**  
   Không. Thiếu client executable khác với khả năng hay chính sách của JVM target.
5. **Thêm `-XX:+EnableDynamicAgentLoading` vào process tool trong khi target đã tắt attach mechanism có giải quyết không?**  
   Không. Cần phân biệt process nào sở hữu policy; client không ghi đè cờ target.
6. **Một OpenJ9 tool không attach HotSpot, bật `jdk.attach.allowAttachSelf` được chứ?**  
   Không. Self-attach khác việc provider JVM implementations không tương thích.
7. **Native Image hỗ trợ `jcmd` có mặc nhiên hỗ trợ Java agent động?**  
   Không. Native Image chỉ có tập chẩn đoán được build bật riêng.
8. **Sidecar đã nhìn thấy PID Java, còn cần kiểm tra gì?**  
   Effective UID/GID, mount/IPC/temp, `/proc`, security policy, VM/provider, và agent policy nếu nạp agent.

## 11. Tài liệu chính thức

- Oracle JDK 26 — **`jcmd`**: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
- Oracle JDK 26 — **`java` launcher và `DisableAttachMechanism`**: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
- Oracle JDK 26 — **Attach API / `VirtualMachine`**: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- Oracle JDK 26 — **`java.lang.instrument`, `Agent-Class`, `agentmain`, dynamic agent**: https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Oracle JDK 9 — **release notes cho self-attach `jdk.attach.allowAttachSelf`**: https://www.oracle.com/java/technologies/javase/9-relnotes.html
- Oracle JDK 21 — **release notes cho JEP 451 / agent loading warnings**: https://www.oracle.com/java/technologies/javase/21-relnote-issues.html
- Eclipse OpenJ9 — **Java Attach API, permission, provider, IPC và flags**: https://eclipse.dev/openj9/docs/attachapi/
- GraalVM for JDK 25 — **`jcmd` with Native Image, phạm vi và `--enable-monitoring=jcmd`**: https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/debugging-and-diagnostics/jcmd/

Chọn tài liệu theo **vendor, VM và release thực tế**: Java API mô tả giao diện chung, nhưng policy của OS, namespace, cách handshake và khả năng chẩn đoán là đặc tính của môi trường. Việc cho phép attach nên được thiết kế ngay khi triển khai để tránh mở thêm quyền trong lúc xử lý sự cố.
