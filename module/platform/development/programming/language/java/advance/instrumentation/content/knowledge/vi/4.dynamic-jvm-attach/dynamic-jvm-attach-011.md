# AttachNotSupportedException, AgentLoadException và AgentInitializationException khi attach vào JVM

Attach API cho phép một chương trình Java (công cụ chẩn đoán, profiler, trình quản lý agent) kết nối tới **JVM đang chạy** và yêu cầu JVM đó nạp một agent. Khi thất bại, ba checked exceptions dễ bị nhầm lẫn là `AttachNotSupportedException`, `AgentLoadException` và `AgentInitializationException`. Chúng mô tả **ba giai đoạn khác nhau** của một thao tác: tạo kết nối attach, nạp agent, rồi khởi tạo agent. Phân biệt đúng giai đoạn giúp chẩn đoán đúng tiến trình, file JAR, manifest, phương thức `agentmain` và điều kiện vận hành.

Đây là bài thuộc chủ đề **Attach vào JVM** của Java Advance – instrumentation. Trọng tâm là ý nghĩa, nơi phát sinh, cách bắt và xử lý từng exception; thêm `IOException` và các ràng buộc JVM ở mức cần thiết để tránh kết luận sai. Ví dụ sử dụng Java 17+ và Java agent JAR được nạp động, không yêu cầu framework.

**Sau bài này, bạn có thể:**

- Đọc sơ đồ `VirtualMachine.attach(pid) → loadAgent(jar, options) → agentmain(...) → detach()` và khoanh vùng lỗi theo **lệnh gây lỗi**.
- Viết mã `catch` riêng ba exception, đồng thời xử lý `IOException` và cleanup đúng.
- Giải thích vì sao **attach thành công không chứng minh agent nạp hoặc khởi tạo thành công**.
- Phân biệt `AgentInitializationException.returnValue()` với mã lỗi của **native JVMTI agent**, tránh suy diễn nó là exit code của Java `agentmain`.
- Tự đóng gói agent minh họa và thực hành trường hợp thành công, không attach được, JAR không nạp được, `agentmain` ném lỗi.

## 1. Mô hình ba ranh giới thất bại

Một công cụ sử dụng Attach API thường làm như sau:

~~~text
PROCESS A: công cụ Java                  PROCESS B: JVM ứng dụng đang chạy
-------------------------                ----------------------------------
đọc PID mục tiêu
   |
   v
VirtualMachine.attach(pid) -------> AttachProvider/transport tới JVM mục tiêu
   |                                         |
   | thành công                              |
   v                                         v
VirtualMachine handle                     kênh attach sẵn sàng
   |
   v
vm.loadAgent(agentJar, options) ---> JVM mục tiêu tìm/đọc agent JAR
                                             |
                                             v
                                      tìm Agent-Class trong manifest
                                             |
                                             v
                                      nạp lớp và gọi agentmain(...)
                                             |
                                             v
                                trả kết quả về công cụ attach
   |
   v
vm.detach()  --------------------> đóng liên kết của công cụ với JVM
~~~

Ba lỗi cần học tương ứng với ba vị trí:

| Exception | Lệnh Java liên quan | Tín hiệu chính | Giả thuyết kiểm tra trước |
| --- | --- | --- | --- |
| `AttachNotSupportedException` | `VirtualMachine.attach(pid)` | Không tạo được kết nối attach qua provider phù hợp | PID/định danh sai, JVM đích không tồn tại hoặc attach provider không hỗ trợ |
| `AgentLoadException` | `vm.loadAgent(agentJar, options)` | Đã có đối tượng `VirtualMachine` nhưng agent không thể được nạp/khởi động theo hợp đồng agent | JAR không truy cập được, manifest thiếu `Agent-Class`, agent class hoặc cấu trúc JAR sai, dynamic loading không được cho phép |
| `AgentInitializationException` | `vm.loadAgent(agentJar, options)` | Agent không khởi tạo được sau khi JVM xử lý yêu cầu load | `agentmain` ném ngoại lệ, cấu hình agent không hợp lệ, lỗi khởi tạo trong agent |

**Không phải mọi lỗi cùng giai đoạn đều luôn thuộc một trong ba lớp trên.** `IOException` có thể xuất hiện khi `attach`, `loadAgent` hoặc `detach` gặp trục trặc I/O; `SecurityException` có thể liên quan quyền. Đây đều là điểm phải ghi nhận riêng.

Các lớp exception nằm trong **module `jdk.attach`**, package `com.sun.tools.attach`; cả ba là **checked exceptions** (kế thừa `Exception`). Chúng không phải `java.lang.instrument.IllegalClassFormatException`, không phải `NoClassDefFoundError`, và cũng không tự mô tả lỗi nghiệp vụ của ứng dụng mục tiêu.

## 2. Chữ ký API và điều kiện biên

Đoạn dưới cho thấy chữ ký công khai liên quan trên JDK 17:

~~~java
// Module jdk.attach, package com.sun.tools.attach
public static VirtualMachine attach(String id)
        throws AttachNotSupportedException, java.io.IOException;

// instance method
public abstract void loadAgent(String agent, String options)
        throws AgentLoadException, AgentInitializationException,
               java.io.IOException;

// overload tương đương loadAgent(agent, null)
public void loadAgent(String agent)
        throws AgentLoadException, AgentInitializationException,
               java.io.IOException;

// đóng kết nối tới JVM đích
public abstract void detach() throws java.io.IOException;
~~~

Đây là **trích chữ ký để giải thích API**, không phải file Java độc lập cần biên dịch.

Với `attach(String)`, đối số `id` là định danh phụ thuộc implementation, thường là chuỗi PID của hệ điều hành. JVM đích có thể đã thoát giữa lúc liệt kê và lúc attach; việc một PID còn tồn tại không chứng minh đó là JVM cùng loại, còn quyền truy cập được phép hoặc kênh attach hoạt động.

Với `loadAgent(String, String)`:

- `agent` là **đường dẫn tới JAR trên hệ thống file của JVM đích**. Nó được gửi tới JVM đích để diễn giải. Trong ví dụ hai process cùng máy, đường dẫn tuyệt đối được tạo ở công cụ cũng trỏ tới cùng file. Khi container/namespace/filesystem khác nhau, không được mặc định rằng đường dẫn của công cụ tồn tại ở JVM đích.
- `options` là **một chuỗi** chuyển cho `agentmain`; quy ước phân tích chuỗi do agent định nghĩa. Có thể truyền `null`.
- Agent JAR được nạp vào JVM đích, lớp được chỉ bởi thuộc tính manifest **`Agent-Class`** phải định nghĩa phương thức `public static void agentmain(String agentArgs, Instrumentation inst)` hoặc biến thể một tham số.
- `loadAgent` hoàn tất khi lời gọi `agentmain` hoàn tất; điều này **không** chứng minh tất cả thread nền/exporter mà agent khởi chạy đã trở nên khỏe mạnh.

**Phân biệt startup và dynamic:** `-javaagent:...` lúc khởi động dùng `Premain-Class` và `premain`. `VirtualMachine.loadAgent(...)` với một JVM đang chạy dùng `Agent-Class` và `agentmain`. Dùng manifest sai kiểu có thể làm thất bại bước load, dù mã Java trong JAR biên dịch bình thường.

## 3. `AttachNotSupportedException` — không tạo được kênh attach

Theo API, `VirtualMachine.attach(String id)` thử các `AttachProvider` đã cài; nếu mọi provider đều báo không hỗ trợ hoặc không có provider nào, method ném `AttachNotSupportedException`. Những tình huống tiêu biểu:

- Chuỗi PID/định danh không hợp lệ, PID đã thoát, hoặc định danh thực tế không phải JVM tương thích.
- JVM mục tiêu dùng implementation, nền tảng hoặc cơ chế attach mà provider hiện có không giao tiếp được.
- Không có attach provider phù hợp trong runtime/cấu hình công cụ.
- Cơ chế attach bị vô hiệu hóa hoặc không khả dụng trên JVM đích; exception **cụ thể** vẫn có thể thay đổi theo provider, OS và cách lỗi được truyền.

Ví dụ lời gọi:

~~~java
VirtualMachine vm = VirtualMachine.attach(pid);
~~~

Nếu method này thất bại, **chưa có handle `vm` hợp lệ để gọi `loadAgent`**. Do đó, lỗi này không phải bằng chứng rằng file agent JAR bị hỏng. Hãy tập trung vào `pid`, JDK/JVM đang dùng, quyền, namespace, trạng thái tiến trình và cấu hình attach.

**Cẩn thận:** lỗi quyền, socket, file tạm, endpoint attach bị kẹt, timeout hoặc process đã kết thúc đôi khi được biểu diễn bằng `IOException` hay `SecurityException`. Không nên viết quy tắc cứng kiểu "sai PID chắc chắn chỉ tạo ra `AttachNotSupportedException`". Javadoc nêu rõ cả `IOException` và lỗi runtime liên quan bảo mật.

### Cách xác minh trước khi sửa agent

1. PID lấy từ **tiến trình Java đích**; trên cùng host có thể đối chiếu công cụ hệ điều hành hoặc `jcmd -l` khi khả dụng.
2. Công cụ attach và target có nằm trong cùng môi trường có thể giao tiếp không? Trong container, một PID nhìn từ host khác PID bên trong namespace.
3. Có chính sách quyền/OS nào ngăn tiến trình công cụ kết nối với tiến trình đích không?
4. JVM đích có thực sự hỗ trợ Attach API và chưa tắt attach mechanism không? Trên HotSpot, `-XX:+DisableAttachMechanism` vô hiệu hóa cơ chế attach.
5. Thử attach ở môi trường kiểm thử kiểm soát được trước khi kết luận ứng dụng/agent không tương thích.

## 4. `AgentLoadException` — kết nối có rồi nhưng agent chưa nạp đúng

Lệnh dẫn tới exception:

~~~java
vm.loadAgent(agentJarPath, "mode=demo");
~~~

Lỗi `AgentLoadException` có nghĩa là agent không tồn tại, không nạp được hoặc không thể bắt đầu theo hợp đồng `java.lang.instrument`. Những nguyên nhân thường gặp:

- Sai `agentJarPath`, file chưa được copy vào nơi JVM đích nhìn thấy, không có quyền đọc hoặc JAR bị hỏng.
- Thiếu thuộc tính `Agent-Class` trong **main manifest** `META-INF/MANIFEST.MF` của JAR dùng để attach; nhầm với `Premain-Class`.
- Tên lớp trong `Agent-Class` không đúng, lớp agent hay dependency cần thiết không thể load, phương thức `agentmain` không đúng chữ ký. Chi tiết phân loại lỗi có thể phụ thuộc JVM/implementation.
- Dynamic agent loading bị chính sách JVM đích từ chối; phải xem message và JVM flags, không tự coi mọi `AgentLoadException` là "file not found".

**Chỉ điều tra classpath và cấu trúc JAR sau khi chắc chắn `attach` đã thành công.** Từ góc nhìn công cụ, JAR path tồn tại trên máy công cụ chưa đủ: JVM đích mới là nơi phải đọc JAR. Kiểm tra file bằng `jar --list --file demo-agent.jar`, rồi đọc manifest bằng công cụ phù hợp để xác nhận `Agent-Class` trỏ đúng tên nhị phân.

`AgentLoadException` **không tự khẳng định** `agentmain` đã chạy một phần hay chưa. Thông điệp lỗi, log JVM đích và trạng thái công cụ mới giúp xác định pha nội bộ. Đặc biệt khi agent đã tạo tác dụng phụ trước một lỗi khác, không tự động retry trùng lặp mà không kiểm tra tính idempotent của agent.

### Phân biệt hai manifest thường nhầm

~~~text
# Startup agent - chạy cùng lệnh java -javaagent:...
Premain-Class: ExampleAgent

# Dynamic agent - nạp vào JVM đang chạy bằng vm.loadAgent(...)
Agent-Class: ExampleAgent
~~~

Hai khối này là **minh họa riêng biệt** cho thuộc tính, không phải toàn bộ manifest thực thi. Một JAR có thể khai báo cả hai nếu tác giả hỗ trợ cả hai vòng đời, nhưng mỗi cách kích hoạt yêu cầu đúng điểm vào.

## 5. `AgentInitializationException` — JVM đã đi vào bước khởi tạo agent và gặp lỗi

Theo `VirtualMachine.loadAgent` của JDK 17, method có thể ném `AgentInitializationException` nếu `agentmain` ném ngoại lệ. Ví dụ `agentmain` cần parse options, khởi tạo transformer, tạo exporter hoặc đọc cấu hình; bất kỳ lỗi khởi tạo không được xử lý thích hợp nào ở bước này đều có thể làm lời gọi load thất bại.

Những nguyên nhân cần kiểm tra trong **JVM đích**:

- `agentmain` không chấp nhận giá trị `options`, gọi `Integer.parseInt` sai, thiếu cấu hình bắt buộc.
- Khởi tạo agent gặp `IllegalStateException`, null reference, lỗi quyền/đường dẫn tài nguyên, mất phụ thuộc hoặc lỗi API instrumentation.
- Transformer/hook bị khởi tạo sai, điều kiện JVM không đáp ứng khả năng mà agent muốn sử dụng.
- Agent tạo tài nguyên rồi ném exception; dù lệnh báo thất bại, tài nguyên/hook khởi tạo dở có thể tồn tại.

### `returnValue()` có ý nghĩa gì?

`AgentInitializationException` có method **`int returnValue()`** — tên đúng là `returnValue()`, **không phải `getReturnValue()`**. Theo Javadoc, nếu exception được tạo kèm mã trả về từ hàm native `Agent_OnAttach` thì method cung cấp mã đó; nếu không, nó trả **0**.

- Với **native JVMTI agent** nạp bằng `loadAgentLibrary` hoặc `loadAgentPath`, mã này có thể hỗ trợ chẩn đoán giá trị lỗi do `Agent_OnAttach` trả về.
- Với **Java agent JAR** nạp bằng `loadAgent`, không thể mặc nhiên diễn giải `returnValue()` thành "mã thoát của `agentmain`". `agentmain` là method `void` và không trả status int theo hợp đồng.
- Giá trị `0` **không chứng minh khởi tạo thành công**: method có thể trả `0` vì exception không chứa native return code, ngay cả khi đã có lỗi `AgentInitializationException`.

Một lỗi quan trọng khác: **lỗi khởi tạo dynamic agent không đồng nghĩa JVM mục tiêu tự thoát**. Đặc tả `java.lang.instrument` cho agent được nạp vào JVM đã chạy quy định JVM không abort ứng dụng chỉ vì agent không bắt đầu được; ngoại lệ không xử lý ở `agentmain` có thể bị bỏ qua trong luồng ứng dụng nhưng vẫn được ghi log, và lời gọi `loadAgent` ở công cụ có thể phản hồi lỗi. Vì vậy hãy đọc **cả log công cụ attach và log JVM đích**; không đoán từ riêng một mặt.

Lỗi ở đây cũng không bảo đảm "đã rollback agent": nếu agent khởi động một số thread, đăng ký hook hoặc thay đổi trạng thái trước khi ném ngoại lệ, những tác dụng phụ có thể còn tồn tại. Khi retry cần kiểm tra agent có hỗ trợ nạp lặp/idempotence không.

## 6. Vì sao `IOException` và `SecurityException` cũng phải có mặt?

Ba exception trong tiêu đề **không phải toàn bộ hợp đồng lỗi** của Attach API. Javadoc khai báo:

| Lời gọi | Checked exceptions cần xử lý | Lỗi runtime/điểm khác |
| --- | --- | --- |
| `VirtualMachine.attach(pid)` | `AttachNotSupportedException`, `IOException` | `SecurityException`, `NullPointerException` khi id null |
| `vm.loadAgent(path, opts)` | `AgentLoadException`, `AgentInitializationException`, `IOException` | `NullPointerException` nếu agent path null; lỗi provider/JVM có thể có chi tiết khác |
| `vm.detach()` | `IOException` | Không phải lệnh gỡ agent |

Một số ví dụ tình huống:

- JVM đích thoát sau khi attach nhưng trước khi load: có thể thành `IOException` ở thao tác `loadAgent`.
- Thao tác đọc/ghi kênh attach thất bại do môi trường: `IOException` có thể phát sinh ở một trong các bước.
- Runtime policy/security ngăn attach: `SecurityException` hoặc lỗi được provider thể hiện theo cơ chế của nó.
- `detach` thất bại: đó là **lỗi cleanup của kênh attach**, không đủ căn cứ để khẳng định `agentmain` chưa chạy.

**Phân biệt kết quả "agent đã khởi tạo" và "công cụ đã detach thành công".** Sau `loadAgent` thành công, `detach` đóng liên kết giữa tool và JVM; nó **không** tự gỡ agent khỏi JVM, dừng thread agent hay hoàn tác biến đổi bytecode.

Trong mã production, nếu `detach` ném `IOException` khi đang có lỗi chính ở `loadAgent`, không để cleanup làm mất hoàn toàn nguyên nhân ban đầu; giữ lỗi chính và bổ sung cleanup failure bằng suppressed exception hoặc báo cáo hai trạng thái riêng. Ví dụ dưới ghi nhận hai trạng thái riêng một cách dễ hiểu.

## 7. Demo Java 17+: tạo JVM đích, attach và thử ba nhánh lỗi

Bộ ví dụ sau **có thể biên dịch độc lập bằng JDK 17+**. Để thử thực sự, cần môi trường có JDK chứa module `jdk.attach`, hai tiến trình Java cục bộ tương thích, quyền attach phù hợp, cùng filesystem nhìn thấy agent JAR và JVM đích cho phép dynamic agent loading. Chạy thử trên một JVM mẫu do bạn kiểm soát; không attach tùy tiện vào production.

Ba file Java và một file manifest nằm **cùng một thư mục**. Không cần Maven, Gradle hoặc thư viện ngoài JDK.

### 7.1. `TargetApp.java` — ứng dụng cần gắn agent

~~~java
import java.util.concurrent.CountDownLatch;

public final class TargetApp {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());
        System.out.println("TARGET_READY");
        new CountDownLatch(1).await();
    }
}
~~~

`ProcessHandle.current().pid()` trả PID của **target**, không phải PID của công cụ attach. `CountDownLatch(1).await()` giữ target sống để bạn có thời gian chạy công cụ ở terminal thứ hai; dừng bằng `Ctrl+C` khi đã thử xong. Đây là chương trình minh họa chủ động chờ vô hạn, không phải mẫu vòng đời ứng dụng production.

### 7.2. `DemoAgent.java` — agent có thể thành công hoặc cố ý lỗi ở `agentmain`

~~~java
import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    public static void agentmain(String options, Instrumentation inst) {
        System.out.println("AGENT_ARGS=" + options);

        if ("fail".equals(options)) {
            throw new IllegalStateException("demo agentmain failure");
        }

        System.out.println("AGENT_READY=" + (inst != null));
    }
}
~~~

JVM đích sẽ gọi `agentmain(String, Instrumentation)`; tham số `options` đến từ `vm.loadAgent(jar, options)`. Tình huống `options="fail"` làm `agentmain` ném lỗi **có chủ ý** để học `AgentInitializationException`. Nó không sửa bytecode hay chạy exporter. Không ghi `premain`, vì ví dụ đang nói về **dynamic attach**.

### 7.3. `AttachTool.java` — bắt từng exception theo đúng giai đoạn

~~~java
import com.sun.tools.attach.AgentInitializationException;
import com.sun.tools.attach.AgentLoadException;
import com.sun.tools.attach.AttachNotSupportedException;
import com.sun.tools.attach.VirtualMachine;
import java.io.IOException;
import java.nio.file.Path;

public final class AttachTool {
    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java AttachTool <pid> <agent.jar> <agent-options>");
            System.exit(2);
        }

        String pid = args[0];
        String agentJar = Path.of(args[1])
                .toAbsolutePath()
                .normalize()
                .toString();
        String options = args[2];

        VirtualMachine vm = null;
        String phase = "attach";
        boolean loaded = false;
        boolean detached = true;

        try {
            vm = VirtualMachine.attach(pid);
            System.out.println("ATTACH_OK");

            phase = "loadAgent";
            vm.loadAgent(agentJar, options);
            loaded = true;
            System.out.println("LOAD_AGENT_OK");
        } catch (AttachNotSupportedException ex) {
            System.err.println("ATTACH_UNSUPPORTED: " + ex.getMessage());
        } catch (AgentLoadException ex) {
            System.err.println("AGENT_LOAD_FAILED: " + ex.getMessage());
        } catch (AgentInitializationException ex) {
            System.err.println("AGENT_INIT_FAILED: " + ex.getMessage());
        } catch (IOException ex) {
            System.err.println(
                    "IO_FAILURE at " + phase + ": " + ex.getMessage());
        } catch (SecurityException ex) {
            System.err.println(
                    "SECURITY_FAILURE at " + phase + ": " + ex.getMessage());
        } finally {
            if (vm != null) {
                try {
                    vm.detach();
                    System.out.println("DETACH_OK");
                } catch (IOException ex) {
                    detached = false;
                    System.err.println("DETACH_IO_FAILED: " + ex.getMessage());
                }
            }
        }

        if (!loaded || !detached) {
            System.exit(1);
        }
    }
}
~~~

Điểm chủ ý trong đoạn mã:

1. Chỉ gọi `loadAgent` **sau khi** `VirtualMachine.attach` thành công. Vì vậy, thấy `AGENT_LOAD_FAILED` hoặc `AGENT_INIT_FAILED` nghĩa là code đã vượt qua bước tạo handle.
2. Catch **`AttachNotSupportedException`, `AgentLoadException` và `AgentInitializationException` riêng biệt**. Thông điệp người dùng khác nhau để khoanh vùng đúng nơi cần kiểm tra.
3. Biến `phase` giúp phân biệt `IOException` khi thiết lập attach với I/O khi gửi yêu cầu load. `IOException` không bị gắn nhầm vào ba nhóm còn lại.
4. `vm.detach()` nằm trong `finally` và chỉ chạy nếu đã nhận được `VirtualMachine`; lệnh này chạy kể cả `loadAgent` thất bại. Công cụ ghi nhận `DETACH_IO_FAILED` tách biệt và trả mã thoát khác 0.
5. Kết quả `loaded=true` chỉ có sau khi `loadAgent` trả về thành công. Trạng thái này không tự xác minh mọi chức năng bên trong agent hoặc tác dụng phụ dài hạn.
6. Ví dụ báo lỗi qua console và exit code để minh họa, **không** áp dụng retry tự động. Ứng dụng thực tế nên có logging có cấu trúc, timeout/giới hạn và thông tin chẩn đoán không tiết lộ bí mật.

`VirtualMachine` trong JDK 17 không triển khai `AutoCloseable` theo cách có thể tự viết `try (VirtualMachine vm = ...)` như một resource thông thường; ta chủ động gọi `detach()`. Catch `SecurityException` chỉ bắt một nhánh quyền thường gặp, không thay thế kiểm tra quyền của hệ điều hành.

### 7.4. `MANIFEST.MF` — đúng entrypoint của agent được attach

~~~text
Manifest-Version: 1.0
Agent-Class: DemoAgent

~~~

Hãy bảo đảm file manifest có **ký tự xuống dòng kết thúc và dòng trống sau `Agent-Class`**, như định dạng JAR manifest. `Agent-Class` phải trùng đúng tên nhị phân của lớp agent. Ở đây, `DemoAgent` không thuộc package nào nên đặt đúng tên này. Nếu đưa vào package, phải đổi cả manifest và đường dẫn class trong JAR.

### 7.5. Biên dịch và đóng gói (terminal thứ nhất)

Trong thư mục chứa bốn file vừa tạo:

~~~bash
javac --add-modules jdk.attach TargetApp.java DemoAgent.java AttachTool.java
jar --create --file demo-agent.jar --manifest MANIFEST.MF DemoAgent.class
jar --list --file demo-agent.jar
~~~

`javac --add-modules jdk.attach` bảo đảm module chứa `com.sun.tools.attach` được giải quyết trong lần biên dịch, còn `DemoAgent` sử dụng `java.lang.instrument` của JDK. Lệnh `jar` tạo agent JAR có manifest và class `DemoAgent.class`. Kết quả liệt kê có `META-INF/MANIFEST.MF` và `DemoAgent.class`; có thể có các entry phụ tùy công cụ, không cần khớp nguyên văn toàn bộ `jar --list`.

### 7.6. Chạy target, rồi chạy tool (hai terminal)

Ở **terminal A**, dùng HotSpot JDK 17 hoặc JDK 21 để chạy target:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp . TargetApp
~~~

Tùy chọn `-XX:+EnableDynamicAgentLoading` là tùy chọn của **JVM đích**. Với HotSpot JDK 21, nó bày tỏ cho phép dynamic agent loading và tránh cảnh báo JEP 451 về việc nạp agent động. Trên JVM implementation khác, cần kiểm tra cờ tương ứng; chức năng attach và dynamic loading phụ thuộc JVM/OS.

Console terminal A ban đầu in:

~~~text
TARGET_PID=12345
TARGET_READY
~~~

**12345 chỉ là PID ví dụ.** Lượt chạy thật sẽ có giá trị khác. Chép PID thực tế từ `TARGET_PID` và giữ target đang chạy.

Ở **terminal B**, dùng PID đó trong lệnh sau (thay số `12345` thành PID vừa in):

~~~bash
java --add-modules jdk.attach -cp . AttachTool 12345 demo-agent.jar ok
~~~

Khi điều kiện attach hợp lệ, tool sẽ in **đúng các dòng do `AttachTool` chủ động in** trên standard output:

~~~text
ATTACH_OK
LOAD_AGENT_OK
DETACH_OK
~~~

Trong **console target A**, agent in thêm hai dòng:

~~~text
AGENT_ARGS=ok
AGENT_READY=true
~~~

Đó là các dòng ổn định do `DemoAgent` in khi `Instrumentation` được JVM cấp và tham số là `ok`. Console target vẫn còn sống sau `detach`. Đừng chờ output của agent xuất hiện trong terminal B: `agentmain` chạy ở **JVM đích**. JVM hoặc môi trường còn có thể ghi thêm cảnh báo/diagnostics ngoài các dòng do demo định nghĩa, đặc biệt khi dùng một phiên bản JDK hoặc cờ khác.

### 7.7. Tạo lỗi khởi tạo có chủ đích

Vẫn giữ target đang chạy (nếu môi trường cho phép agent được gọi thêm lần nữa), chạy:

~~~bash
java --add-modules jdk.attach -cp . AttachTool 12345 demo-agent.jar fail
~~~

`DemoAgent.agentmain` in `AGENT_ARGS=fail` rồi ném `IllegalStateException`. Theo hợp đồng `VirtualMachine.loadAgent`, công cụ có thể nhận `AgentInitializationException` và in dòng có tiền tố:

~~~text
AGENT_INIT_FAILED:
~~~

Phần sau dấu hai chấm phụ thuộc JVM và thông điệp lỗi; **không** dự đoán cứng stack trace hoặc nguyên văn message. Console target có thể có stack trace của lỗi khởi tạo. Nếu hệ thống không cho phép nạp lại cùng agent hoặc target đang ở trạng thái khác, khởi động một target mới trước khi thử; việc nạp lặp không nên được coi là luôn idempotent.

### 7.8. Tạo lỗi load và lỗi attach

Thử một JAR không tồn tại trong filesystem mà JVM đích nhìn thấy:

~~~bash
java --add-modules jdk.attach -cp . AttachTool 12345 missing-agent.jar ok
~~~

Trong môi trường HotSpot thông thường, nếu attach thành công nhưng JAR không mở/nạp được, tool sẽ báo lỗi tại bước `loadAgent`, thường qua `AgentLoadException`. Tùy runtime và cách lỗi được truyền, có thể có `IOException`; hãy đối chiếu log JVM đích và tên exception thực nhận.

Để khảo sát lỗi attach, thay PID bằng một PID không tồn tại trong môi trường của bạn. Khi không có provider nào attach được, `VirtualMachine.attach` ném `AttachNotSupportedException`. Một lỗi I/O hoặc quyền có thể tạo loại ngoại lệ khác; không có cách ép mọi OS/JVM cho cùng một message bằng cách chọn một số PID cố định.

## 8. Checklist chẩn đoán theo vị trí của exception

### 8.1. Nếu nhận `AttachNotSupportedException`

- Xác nhận **PID đúng, đang tồn tại và thuộc JVM**; xác định namespace/container của PID.
- Kiểm tra chương trình công cụ chạy từ JDK có `jdk.attach`, bản JVM/OS và provider tương thích.
- Kiểm tra quyền attach và cờ vô hiệu hóa cơ chế attach, chẳng hạn `-XX:+DisableAttachMechanism` trên HotSpot.
- Ghi lại PID, vendor/JDK, OS, thông điệp exception và trạng thái target; thử một target mẫu.
- **Chưa** sửa `Agent-Class` hoặc `agentmain` chỉ vì lỗi ở đây: hai phần ấy chưa tham gia thao tác.

### 8.2. Nếu nhận `AgentLoadException`

- Kiểm tra attach đã thành công; tìm dấu `ATTACH_OK` trong công cụ.
- Kiểm tra **JAR path theo góc nhìn của JVM đích**; quyền đọc, lớp agent/dependencies, tính toàn vẹn ZIP/JAR.
- Đọc `META-INF/MANIFEST.MF` để xác nhận đúng `Agent-Class` và tên lớp.
- Kiểm tra chữ ký `public static void agentmain(...)`, khả năng load lớp và hỗ trợ của JVM.
- Kiểm tra cấu hình cấm dynamic agent loading và thông điệp cụ thể; phân biệt với việc cấm attach hoàn toàn.
- Không retry vô hạn khi nguyên nhân là sai cấu hình/JAR hoặc chính sách không cho phép.

### 8.3. Nếu nhận `AgentInitializationException`

- Đọc log và stack trace trong **JVM đích**, không chỉ exception từ tool.
- Xác minh `options`, các giá trị mặc định, parser, phụ thuộc và tài nguyên mà `agentmain` chạm tới.
- Nếu cần, thử phiên bản `agentmain` tối giản chỉ in thông tin rồi return, sau đó khôi phục từng bước khởi tạo.
- Kiểm tra side effects đã xảy ra trước khi ném exception: transformer, thread, exporter, hook, resource handle.
- **Không** diễn giải `returnValue()==0` thành "agent đã khởi tạo thành công" đối với Java agent JAR.

### 8.4. Nếu nhận `IOException` hoặc lỗi cleanup

- Ghi **stage**: `attach`, `loadAgent` hay `detach`; xác nhận target còn chạy và kênh liên lạc hoạt động.
- Kiểm tra transport, file tạm, quyền host/namespace, process bị kill/restart, JVM logs và các giới hạn OS.
- Nếu `detach` thất bại sau `loadAgent` thành công, ghi riêng hai sự kiện; không tự kết luận agent chưa được nạp.
- Hạn chế retry tự động đối với thao tác có khả năng đã được JVM đích thực hiện một phần.

## 9. Cờ JVM và khác biệt phiên bản liên quan đến cách diễn giải lỗi

Trên HotSpot, cần phân biệt hai cơ chế:

| Cấu hình JVM đích | Tác động trực tiếp | Giai đoạn cần quan sát |
| --- | --- | --- |
| `-XX:+DisableAttachMechanism` | Vô hiệu hóa cơ chế cho các công cụ attach vào JVM | Thường ảnh hưởng `VirtualMachine.attach` |
| `-XX:-EnableDynamicAgentLoading` | Không cho phép nạp agent động vào JVM đang chạy | Có thể attach được nhưng `loadAgent` bị từ chối |
| `-XX:+EnableDynamicAgentLoading` | Chủ động cho phép dynamic agent loading theo chính sách HotSpot | Hỗ trợ `loadAgent` khi điều kiện khác đáp ứng |
| `-javaagent:path/to/agent.jar` trước khi ứng dụng chạy | Nạp **startup agent** qua `premain`; không gọi Attach API trong tool | Khác luồng `VirtualMachine.loadAgent` |

JEP 451 trong **JDK 21** bổ sung cảnh báo khi agent được nạp động; cảnh báo **không tự chứng minh thao tác thất bại**. Khi sử dụng `-XX:+EnableDynamicAgentLoading` trên HotSpot, có thể thể hiện sự chấp thuận tường minh và tránh cảnh báo đó. Chính sách mặc định của **các JDK sau này** có thể khác, vì vậy phải kiểm tra version/runtime thực tế; không áp dụng vô điều kiện lời khẳng định "dynamic attach luôn được bật" cho mọi bản JDK tương lai.

Quan trọng hơn, **attach** và **dynamic agent load** là hai quyền/khả năng có thể tách biệt. Công cụ có thể attach để lấy thông tin chẩn đoán nhưng không được phép tiêm agent. Nếu chỉ ghi "attach error" cho mọi exception của `loadAgent`, người vận hành dễ sửa nhầm quyền hoặc PID thay vì xem chính sách nạp agent.

## 10. Chiến lược bắt, retry và báo cáo lỗi

### 10.1. Đặt catch theo *giai đoạn*, không theo một Exception chung

Cách viết có ích là giữ lại tên lệnh và loại exception. Ví dụ:

~~~java
try {
    vm.loadAgent(agentJarPath, options);
} catch (AgentLoadException ex) {
    // Kiểm tra jar path, manifest, class, policy dynamic load.
} catch (AgentInitializationException ex) {
    // Kiểm tra agentmain, options, tài nguyên và log JVM đích.
} catch (IOException ex) {
    // Kiểm tra giao tiếp tới target; phân biệt retry với lỗi chắc chắn.
}
~~~

**Đây là mảnh code minh họa bên trong một phương thức đã có biến `vm`, `agentJarPath`, `options`; không phải lớp độc lập.** Ví dụ đầy đủ ở mục 7 cho thấy cả `attach` lẫn `detach`.

Chỉ bắt `Exception` rồi ghi "agent failed" sẽ làm mất thông tin giai đoạn. Ngược lại, một exception class cũng chưa đủ để xác định root cause duy nhất: cần message, target logs, environment và correlation.

### 10.2. Retry theo bản chất lỗi

| Tình huống | Hướng xử lý hợp lý |
| --- | --- |
| PID không tồn tại, attach provider không tương thích | Sửa định danh/môi trường; retry y hệt thường không hữu ích |
| JAR sai đường dẫn, thiếu manifest, thiếu class | Sửa artifact/đóng gói trước khi retry |
| `agentmain` lỗi cấu hình deterministic | Sửa `options`/cấu hình trước khi retry |
| I/O đứt quãng, target vừa restart | Có thể retry **có giới hạn** sau khi xác minh PID mới và trạng thái |
| Kết quả không rõ do timeout khi JVM đang xử lý request | Xác minh agent đã chạy/để lại hook trước khi retry để tránh nạp hai lần |
| Cleanup `detach` lỗi sau khi load thành công | Xử lý transport/cleanup riêng; tránh coi agent chắc chắn chưa chạy |

Một agent có thể sửa bytecode, khởi thread hoặc cài hook trước khi báo lỗi; retry không kiểm soát có thể gây duplicate instrumentation, memory leak hay trạng thái không nhất quán. Thiết kế agent nên có khóa/cờ idempotence phù hợp và điều kiện dừng an toàn.

### 10.3. Thông tin nên ghi để chẩn đoán

- PID/định danh JVM đích, process start time nếu có, JDK vendor/version, tên host/container và timestamp.
- Giai đoạn lỗi (`attach`, `loadAgent`, `detach`), **loại exception đầy đủ**, message và stack trace ở công cụ.
- Agent JAR basename, phiên bản, checksum (nếu có), giá trị `Agent-Class` và trạng thái có/không thể đọc từ JVM đích.
- Log/stack trace bên trong target ở cùng khoảng thời gian; nếu có trace/correlation thì dùng nhưng không để lộ secret.
- Trạng thái "đã load", "đã detach", "đã xác nhận agent healthy" ghi **riêng**; tránh dồn thành một boolean duy nhất.

Đừng ghi raw `options` nếu chứa token, credential hay thông tin bí mật. Nếu agent được nạp qua công cụ vận hành, hành động attach cũng cần phân quyền và audit phù hợp vì nó có khả năng thay đổi hành vi ứng dụng.

## 11. Những nhầm lẫn gây chẩn đoán sai

1. **"`AgentLoadException` nghĩa là `attach` thất bại."** Không đúng: class này thuộc lời gọi `loadAgent`; đối tượng `VirtualMachine` đã được tạo trước đó trong luồng demo.
2. **"`AttachNotSupportedException` chứng minh JAR bị thiếu."** Không đúng: thất bại trước bước yêu cầu đọc JAR.
3. **"`AgentInitializationException` là exit code của Java `agentmain`."** Không đúng: `agentmain` trả về `void`. `returnValue()` chủ yếu hỗ trợ native `Agent_OnAttach` error code và có thể bằng 0 khi không có code.
4. **"`loadAgent` trả bình thường nên ứng dụng đã được quan sát đầy đủ."** Không đúng: agent có thể chưa instrument class cần thiết, chưa kết nối exporter hay chưa vượt qua health check hậu khởi tạo.
5. **"`detach` gỡ agent khỏi JVM."** Không đúng: nó chỉ kết thúc kết nối của công cụ.
6. **"Một số PID không attach được luôn ném cùng exception."** Không đúng: provider, OS, quyền và I/O ảnh hưởng loại lỗi và message.
7. **"JDK 21 cảnh báo dynamic loading đồng nghĩa agent đã bị từ chối."** Không đúng: cảnh báo của JEP 451 mô tả sự thay đổi định hướng chính sách; cần kiểm tra kết quả thật và cờ JVM.
8. **"Agent load thất bại thì hoàn toàn chưa tác động target."** Không đảm bảo: khởi tạo thất bại có thể xảy ra sau các side effects.
9. **"Cứ đổi `Agent-Class` thành `Premain-Class` là được."** Sai theo luồng: dynamic attach cần `Agent-Class`/`agentmain`, startup agent cần `Premain-Class`/`premain`.
10. **"`IOException` không liên quan vì đã catch ba exception."** Sai: nó nằm trong chữ ký cả `attach`, `loadAgent` và `detach`.

## 12. Câu hỏi và bài tập tự kiểm tra

**Tình huống A:** `VirtualMachine.attach("99999999")` thất bại. Có nên sửa manifest `Agent-Class` ngay không?  
**Gợi ý:** Chưa. Phải xác định JVM đích và khả năng attach trước. Kiểu lỗi cụ thể còn phụ thuộc provider/môi trường.

**Tình huống B:** Tool in `ATTACH_OK` nhưng tiếp theo là `AGENT_LOAD_FAILED`. Bạn kiểm tra ba yếu tố nào trước?  
**Gợi ý:** Đường dẫn JAR dưới góc nhìn target, manifest `Agent-Class`/binary class name, khả năng JVM cho phép dynamic loading.

**Tình huống C:** `DemoAgent.agentmain("fail", inst)` ném `IllegalStateException`. Công cụ nên phân loại thế nào?  
**Gợi ý:** `AgentInitializationException` trong hợp đồng `loadAgent`; xem cả stack trace trên target, không suy luận JVM mục tiêu tự thoát.

**Tình huống D:** Bắt được `AgentInitializationException` và `returnValue()==0`. Agent có chắc chắn thành công không?  
**Gợi ý:** Không. Zero có thể chỉ là giá trị mặc định khi exception không mang native error code.

**Tình huống E:** `loadAgent` trả thành công nhưng `detach` ném `IOException`. Bạn báo trạng thái thế nào?  
**Gợi ý:** Load thành công và cleanup lỗi là **hai kết quả riêng**; không tự gán "agent failed".

**Tình huống F:** Target chạy với `-XX:-EnableDynamicAgentLoading`; tool attach được nhưng không nạp agent. Vị trí lỗi hợp lý để kiểm tra?  
**Gợi ý:** Bước `loadAgent` và chính sách dynamic load, không bắt đầu bằng việc thay PID.

**Tình huống G:** Tool có đường dẫn `C:\tools\agent.jar` nhưng target nằm trong Linux container. Vì sao agent vẫn có thể load lỗi?  
**Gợi ý:** JVM đích phải nhìn thấy đường dẫn theo filesystem/namespace **của chính nó**.

**Tình huống H:** Khi công cụ gặp I/O timeout không rõ kết quả, có nên retry ngay nhiều lần?  
**Gợi ý:** Xác nhận trạng thái agent/hook và mục tiêu trước; không lặp lại không giới hạn với thao tác có side effects.

## 13. Kết luận

Ba tên exception là bản đồ chẩn đoán theo **ranh giới của Attach API**:

~~~text
attach(pid) thất bại
    -> AttachNotSupportedException (hoặc IOException/SecurityException)
attach(pid) thành công, loadAgent(...) thất bại vì không nạp/bắt đầu được
    -> AgentLoadException (hoặc IOException/lỗi do chính sách/runtime)
loadAgent(...) đi tới khởi tạo agent nhưng agentmain lỗi
    -> AgentInitializationException
detach() thất bại
    -> IOException của cleanup, cần ghi riêng kết quả load
~~~

Chẩn đoán đúng luôn kết hợp **API call**, **loại exception**, **message**, **JDK/JVM flags**, **đường dẫn của target**, và **log của cả hai process**. Điều đó giúp phân biệt lỗi kết nối, lỗi gói agent, lỗi khởi tạo agent và lỗi giao tiếp, đồng thời tránh retry tạo tác dụng phụ trùng lặp.

### Tài liệu chính thức

- [Oracle JDK 17 — VirtualMachine](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): chữ ký `attach`, `loadAgent`, `detach` và checked exceptions.
- [Oracle JDK 17 — AttachNotSupportedException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AttachNotSupportedException.html): ý nghĩa lỗi attach provider.
- [Oracle JDK 17 — AgentLoadException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AgentLoadException.html): lỗi không nạp agent được.
- [Oracle JDK 17 — AgentInitializationException](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/AgentInitializationException.html): lỗi khởi tạo và ý nghĩa `returnValue()`.
- [Oracle JDK 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Agent-Class`, `agentmain` và ngữ nghĩa agent nạp động.
- [Oracle JDK 21 release notes — JEP 451](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): cảnh báo và `EnableDynamicAgentLoading` trên HotSpot.