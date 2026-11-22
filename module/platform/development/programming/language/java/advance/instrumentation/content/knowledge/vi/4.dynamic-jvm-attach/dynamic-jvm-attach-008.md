# `detach` kết nối điều khiển không đồng nghĩa với gỡ agent khỏi JVM

Khi một công cụ Java dùng **Attach API** để kết nối với JVM đang chạy, công cụ có thể nạp một **Java agent** vào tiến trình đó rồi gọi `VirtualMachine.detach()`. Việc **detach** chỉ kết thúc phiên giao tiếp của công cụ điều khiển với JVM đích. Nó **không** tương đương với “unload agent”, **không** tự xóa `ClassFileTransformer` đã đăng ký, không hoàn nguyên bytecode đã thay đổi và không buộc các thread/dịch vụ do agent tạo ra dừng hoạt động.

Điểm cốt lõi: phải quản lý **hai vòng đời độc lập** — vòng đời của *kết nối điều khiển* và vòng đời của *logic agent hoạt động bên trong JVM đích*. Đây là kiến thức nền để viết công cụ attach, tracer, profiler, APM hoặc agent quan sát runtime đúng đắn.

## 1. Tách ba đối tượng: controller, kết nối Attach và agent trong JVM đích

Giả sử ứng dụng đang chạy trong JVM B, còn chương trình điều khiển ở JVM A:

```text
JVM A — AttachController                  JVM B — TargetApp
┌──────────────────────────────┐         ┌────────────────────────────────────┐
│ VirtualMachine.attach(pid)  │────────>│ Attach listener/service của JVM B │
│                              │         │                                    │
│ vm.loadAgent("agent.jar")   │────────>│ Nạp agent.jar và gọi agentmain(...)│
│                              │         │   ├─ Cập nhật trạng thái trong JVM│
│                              │         │   ├─ Đăng ký ClassFileTransformer │
│                              │         │   └─ Có thể tạo thread/tài nguyên │
│ vm.detach()                  │ --X--  │                                    │
│ Kết nối điều khiển kết thúc  │         │ JVM B vẫn chạy: callback của agent│
│                              │         │ có thể tiếp tục nhận sự kiện      │
└──────────────────────────────┘         └────────────────────────────────────┘
```

Trong sơ đồ, `--X--` đánh dấu **ngắt phiên attach của controller**. Nó không biểu diễn lệnh yêu cầu JVM B loại bỏ class agent hay khôi phục toàn bộ trạng thái ban đầu.

| Thành phần | Vị trí | Sau khi controller gọi `detach()` thành công |
| --- | --- | --- |
| Đối tượng `com.sun.tools.attach.VirtualMachine` | Bộ nhớ JVM của controller | Không còn dùng được để thao tác với phiên vừa detach; gọi phương thức thao tác tiếp sẽ nhận `IOException` theo API. |
| Kết nối/phiên Attach | Giữa hai JVM | Đã được giải phóng theo cơ chế attach provider. |
| Java agent đã nạp | JVM đích | Những thành phần còn được tham chiếu hoặc đang hoạt động vẫn có thể tiếp tục tồn tại và chạy. |
| `Instrumentation` nhận qua `agentmain` | JVM đích | Vẫn là đối tượng dịch vụ runtime mà agent có thể sử dụng khi còn giữ tham chiếu; detach không thu hồi nó. |
| `ClassFileTransformer` đã đăng ký | Registry instrumentation của JVM đích | Tiếp tục có thể được gọi với các lần load/redefine/retransform phù hợp, cho tới khi được gỡ riêng hoặc JVM kết thúc. |
| Bytecode đã biến đổi và trạng thái ứng dụng | JVM đích | Không tự động trở về trạng thái ban đầu chỉ vì controller detach. |
| JVM đích và các thread đang chạy | JVM đích | Không bị kết thúc chỉ bởi thao tác detach. |

**Ví dụ dễ hình dung:** mở một bảng điều khiển từ xa, bật một chức năng giám sát trong ứng dụng rồi đóng phiên điều khiển. Việc đóng phiên không đồng nghĩa chức năng giám sát đã tắt.

## 2. Ngữ nghĩa chính xác của các lời gọi Attach API

Một chuỗi attach phổ biến dùng API `jdk.attach`:

```java
// Trích đoạn mô tả luồng điều khiển, chưa phải chương trình độc lập.
VirtualMachine vm = VirtualMachine.attach(pid);
try {
    vm.loadAgent(agentJarAbsolutePath, "mode=observe");
} finally {
    vm.detach();
}
```

- `VirtualMachine.attach(pid)`: yêu cầu attach vào JVM đích có định danh phù hợp (thường là PID với HotSpot và môi trường tiến trình thông thường). Nó trả về một **handle giao tiếp** ở tiến trình công cụ điều khiển, không chuyển toàn bộ JVM đích vào tiến trình controller.
- `vm.loadAgent(path, options)`: yêu cầu JVM đích nạp **agent JAR Java**; JAR phải có thuộc tính manifest `Agent-Class` và class đó có `public static void agentmain(String, Instrumentation)` hoặc `agentmain(String)`. Với lời gọi này, agent thực thi **bên trong JVM đích**.
- Theo tài liệu Java 17, `loadAgent(...)` trả về khi lời gọi `agentmain(...)` hoàn tất. Điều đó **không** có nghĩa mọi dịch vụ/thread/callback mà `agentmain` khởi tạo đều đã hoàn tất; chúng có thể cố ý chạy dài hạn.
- `vm.detach()`: giải phóng phiên điều khiển. Sau detach, cố gọi `vm.getSystemProperties()` hay `vm.loadAgent(...)` trên **cùng handle** sẽ gây `IOException`. Muốn thao tác tiếp, controller cần attach lại và lấy handle mới, nếu JVM đích vẫn hỗ trợ attach và còn đang chạy.

Một lời gọi `loadAgent` đang diễn ra đồng thời với `detach` trên cùng handle là tình huống race; tài liệu Attach API nói hành vi hoàn tất hay ném `IOException` của thao tác đang diễn ra là **phụ thuộc implementation**. Mẫu `try/finally` ở trên thực hiện tuần tự: **đợi `loadAgent` trở về, rồi detach**.

Điều quan trọng về *đối tượng API*: `VirtualMachine` là handle **phía controller**, còn `Instrumentation` là interface mà agent nhận **bên trong JVM đích**. Không có hợp đồng nào nói `VirtualMachine.detach` sẽ gọi `Instrumentation.removeTransformer`, đóng tài nguyên của agent hay giải phóng mọi class agent.

## 3. Thực hành Java 17+: nhìn thấy transformer hoạt động sau `detach`

Thí nghiệm sử dụng **hai tiến trình Java** và một Java agent:

- `TargetApp`: ứng dụng đích đang chạy, chờ lệnh trên stdin để đọc trạng thái hoặc nạp một class mới.
- `MarkerAgent`: được nạp vào `TargetApp` bằng Attach API, đặt system property và đăng ký `ClassFileTransformer` chỉ **ghi log khi class `LateLoaded` được nạp**. Transformer **không chỉnh bytecode** vì trả về `null`.
- `AttachController`: tiến trình khác gọi `attach → loadAgent → detach` rồi thoát.

Khi controller đã in `CONTROLLER detached` và kết thúc, ta mới yêu cầu JVM đích nạp `LateLoaded`. Nếu transformer vẫn in log thì ta có bằng chứng trực tiếp rằng thao tác `detach` **không hủy đăng ký transformer**.

### 3.1. Cấu trúc tệp

```text
attach-demo/
├── src/
│   └── demo/
│       └── attach/
│           ├── TargetApp.java
│           ├── LateLoaded.java
│           ├── MarkerAgent.java
│           └── AttachController.java
└── agent.mf
```

Các đoạn dưới đây là **bốn tệp Java độc lập theo đúng tên tệp/class**, cộng một tệp manifest.

### 3.2. `src/demo/attach/TargetApp.java`

```java
package demo.attach;

import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class TargetApp {
    private TargetApp() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("TARGET ready");

        BufferedReader reader =
                new BufferedReader(new InputStreamReader(System.in));

        String command;
        while ((command = reader.readLine()) != null) {
            switch (command) {
                case "check" -> System.out.println(
                        "TARGET state=" +
                        System.getProperty("demo.agent.state", "absent"));
                case "load" -> {
                    Class.forName("demo.attach.LateLoaded");
                    System.out.println("TARGET class loaded");
                }
                case "quit" -> {
                    System.out.println("TARGET stopped");
                    return;
                }
                default -> System.out.println("TARGET unknown command");
            }
        }
    }
}
```

Ứng dụng này không import `MarkerAgent`; nó chỉ quan sát một system property của **chính tiến trình đích**. Lệnh `load` dùng `Class.forName(String)` để nạp `LateLoaded` theo yêu cầu. Vì tên class ở đây nằm trong chuỗi ký tự, lớp không cần được load từ trước chỉ để chạy `main`.

### 3.3. `src/demo/attach/LateLoaded.java`

```java
package demo.attach;

public final class LateLoaded {
    private LateLoaded() {
    }
}
```

Đây là class thử nghiệm chỉ được yêu cầu nạp sau attach/detach. Nó cố ý không có side effect để phân biệt log do transformer tạo ra với log do class tự thực thi.

### 3.4. `src/demo/attach/MarkerAgent.java`

```java
package demo.attach;

import java.lang.instrument.Instrumentation;

public final class MarkerAgent {
    private MarkerAgent() {
    }

    public static void agentmain(
            String options, Instrumentation instrumentation) {

        System.setProperty("demo.agent.state", "ACTIVE");

        instrumentation.addTransformer(
                (loader, className, classBeingRedefined,
                 protectionDomain, bytes) -> {
                    if ("demo/attach/LateLoaded".equals(className)) {
                        System.out.println("AGENT saw LateLoaded");
                    }
                    return null; // Không thay đổi bytes của class.
                },
                false);

        System.out.println("AGENT installed");
    }
}
```

Agent dùng entry point `agentmain` vì được **attach sau khi ứng dụng đã chạy**, không dùng `premain` của `-javaagent`. Lời gọi `addTransformer(..., false)` đăng ký callback cho các class load/redefine thích hợp và không yêu cầu capability retransformation. `return null` là cách hợp lệ để báo “không biến đổi bytecode”.

Lưu ý: không cần biến `static` giữ transformer trong ví dụ chỉ quan sát. Registry instrumentation có đăng ký callback, nên agent vẫn có thể nhận sự kiện sau khi phương thức `agentmain` đã trả về và controller đã detach. Nếu muốn **gỡ transformer theo yêu cầu**, một agent thực tế phải chủ động **giữ tham chiếu** tới transformer vừa đăng ký để dùng `removeTransformer` sau này.

### 3.5. `src/demo/attach/AttachController.java`

```java
package demo.attach;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachController {
    private AttachController() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: AttachController <target-pid> <agent-jar>");
            return;
        }

        String pid = args[0];
        String agentPath =
                Path.of(args[1]).toAbsolutePath().normalize().toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentPath, "demo");
            System.out.println("CONTROLLER loaded");
        } finally {
            vm.detach();
            System.out.println("CONTROLLER detached");
        }
    }
}
```

Các lời gọi API trong controller kết nối tới **JVM đích**, nhưng log `CONTROLLER ...` xuất hiện trong **terminal của controller**. `MarkerAgent.agentmain` và transformer lại in trong **terminal của TargetApp**. `finally` bảo đảm controller cố gắng detach khi `loadAgent` thành công hoặc báo lỗi, miễn là `attach` đã trả về một handle.

### 3.6. Tạo manifest của agent

Nội dung đầy đủ của `agent.mf` (có ký tự xuống dòng ở cuối):

```text
Manifest-Version: 1.0
Agent-Class: demo.attach.MarkerAgent

```

Thuộc tính `Agent-Class` là bắt buộc đối với Java agent được nạp qua `VirtualMachine.loadAgent`. `Premain-Class` dùng cho trường hợp khởi chạy bằng `-javaagent`, không thay thế `Agent-Class` trong thí nghiệm này.

### 3.7. Biên dịch và đóng gói

Mở terminal ở thư mục `attach-demo/`. Tạo thư mục output trước:

```bash
mkdir out
```

Nếu `out` đã tồn tại, bỏ qua lệnh tạo thư mục. Với JDK 17 hoặc mới hơn:

```bash
javac --add-modules jdk.attach -d out \
  src/demo/attach/TargetApp.java \
  src/demo/attach/LateLoaded.java \
  src/demo/attach/MarkerAgent.java \
  src/demo/attach/AttachController.java

jar --create --file marker-agent.jar \
  --manifest agent.mf \
  -C out demo/attach/MarkerAgent.class
```

Các dòng có dấu `\` để tiếp dòng là cú pháp shell kiểu Bash. Nếu dùng Windows PowerShell, hãy gõ toàn bộ lệnh `javac` hoặc `jar` trên **một dòng**, ví dụ:

```powershell
javac --add-modules jdk.attach -d out src/demo/attach/TargetApp.java src/demo/attach/LateLoaded.java src/demo/attach/MarkerAgent.java src/demo/attach/AttachController.java
jar --create --file marker-agent.jar --manifest agent.mf -C out demo/attach/MarkerAgent.class
```

Phương thức `VirtualMachine.attach` thuộc **module JDK `jdk.attach`**. Tùy chọn `--add-modules jdk.attach` làm ý định sử dụng module rõ ràng. Các API Instrumentation thuộc module `java.instrument`, thường đã được giải quyết tự động trên môi trường JDK đầy đủ.

> Mẫu chạy này dùng classpath đơn giản với Java 17+. Không cần thêm thư viện Maven, Gradle hoặc Byte Buddy.

## 4. Chạy bằng hai terminal, đọc đúng kết quả

### Bước A — Khởi động ứng dụng đích

**Terminal 1** tại `attach-demo/`:

```bash
java -cp out demo.attach.TargetApp
```

Ban đầu stdout:

```text
TARGET ready
```

Để nguyên terminal 1. Gõ `check` rồi Enter để xác nhận agent chưa được nạp. Ứng dụng in chính xác:

```text
TARGET state=absent
```

### Bước B — Tìm PID của JVM đích

**Terminal 2** tại cùng thư mục:

```bash
jps -l
```

Trong danh sách, tìm dòng có main class `demo.attach.TargetApp`. Số PID thay đổi theo mỗi lần chạy; ví dụ minh họa là:

```text
43120 demo.attach.TargetApp
```

**Thay PID mẫu bằng PID thực tế** của `TargetApp` trên máy bạn; `jps` có thể hiển thị thêm tiến trình JDK khác. Có thể dùng công cụ quản lý tiến trình hệ điều hành nếu môi trường không hỗ trợ `jps`.

### Bước C — Attach, nạp agent và detach

**Terminal 2**, thay `43120` trong ví dụ bằng PID thật:

```bash
java --add-modules jdk.attach -cp out \
  demo.attach.AttachController 43120 marker-agent.jar
```

Trên PowerShell, viết thành một dòng:

```powershell
java --add-modules jdk.attach -cp out demo.attach.AttachController 43120 marker-agent.jar
```

Trong điều kiện attach thành công, **stdout của controller (terminal 2)** là:

```text
CONTROLLER loaded
CONTROLLER detached
```

Còn **terminal 1** nhận dòng do `agentmain` chạy trong JVM đích in ra:

```text
AGENT installed
```

Như vậy, sau khi thấy `CONTROLLER detached`, phiên Attach của controller đã kết thúc. Tuy nhiên agent vừa đăng ký transformer bên trong TargetApp và chưa có lời gọi nào gỡ nó.

### Bước D — Kiểm chứng hiệu ứng agent vẫn tồn tại

Trở lại **terminal 1**, gõ `check` rồi Enter:

```text
TARGET state=ACTIVE
```

Điều này cho thấy system property được agent đặt trong JVM đích **không bị `detach` xóa đi**.

Tiếp tục gõ `load` rồi Enter:

```text
AGENT saw LateLoaded
TARGET class loaded
```

Dòng `AGENT saw LateLoaded` do **ClassFileTransformer được đăng ký trước detach** in ra **sau detach**, đúng lúc TargetApp load một class mới. Đây là bằng chứng mạnh hơn việc chỉ thấy system property còn tồn tại: **callback instrumentation vẫn hoạt động mặc dù controller đã ngắt kết nối**.

Cuối cùng gõ `quit` rồi Enter:

```text
TARGET stopped
```

Ứng dụng kết thúc bình thường. Các dòng output phía trên là **nội dung stdout chính xác của chương trình mẫu trong từng bước**, không tính dòng lệnh bạn gõ, danh sách PID, log JVM/diagnostic có thể xuất hiện và các dòng output từ bước trước.

## 5. `detach()` có làm agent “biến mất” không?

Không có API `unloadAgent()` tổng quát tương ứng với `VirtualMachine.loadAgent()` trong **Java Instrumentation API chuẩn**. Sau khi agent đã được nạp, nhiều loại trạng thái độc lập có thể tồn tại:

| Thứ agent đã thiết lập | Sau detach | Muốn dừng/thu hồi cần làm gì? |
| --- | --- | --- |
| `ClassFileTransformer` | Tiếp tục nhận các callback đủ điều kiện | Agent gọi `Instrumentation.removeTransformer(transformer)` bằng **đúng tham chiếu** đã đăng ký. |
| Bytecode của class đã transform | Phiên điều khiển không hoàn nguyên nó | Có thể cần `retransformClasses`/`redefineClasses` với điều kiện capability, quy tắc transform và bytes phù hợp; không có cam kết “undo” tự động. |
| Thread/scheduler do agent tạo | Có thể tiếp tục chạy, thậm chí giữ JVM sống nếu là non-daemon thread | Agent cần cooperative shutdown: đặt cờ dừng, `interrupt` phù hợp, đóng scheduler/executor và chờ kết thúc khi cần. |
| Socket, HTTP endpoint, file handle, MBean | Không tự đóng/đăng ký ngược | Chính agent cần đóng tài nguyên, unbind/unregister theo từng API. |
| System property hoặc trạng thái tĩnh | Vẫn giữ giá trị tới khi có thay đổi khác hoặc JVM dừng | Nếu cần phục hồi, agent phải lưu trạng thái trước đó và hoàn nguyên có chủ đích, tránh xóa thay đổi hợp lệ từ thành phần khác. |
| Class/JAR đã nạp | Không thể giả định tự unload khi controller rời đi | Class unloading do GC và reachability/class loader quyết định; agent và các cấu trúc instrumentation thường có reference lâu dài. |
| Khả năng attach lại | Phụ thuộc JVM đang chạy và điều kiện attach | Tạo phiên `VirtualMachine.attach(...)` mới nếu cần điều khiển lần nữa. |

**Quan trọng:** `removeTransformer` **không tự khôi phục** phần bytecode đã được transformer thay đổi trên các lớp đang nạp. Nó chỉ bỏ đăng ký transformer cho việc xử lý về sau; ngay cả sau khi remove, callback đang diễn ra ở thread khác vẫn có thể đến do race. Còn `retransformClasses` cần hỗ trợ của JVM/manifest và có quy tắc sử dụng lại các biến đổi từ transformer không hỗ trợ retransformation; không phải một nút “revert toàn bộ”.

Bởi vậy khi triển khai agent thật, phải định nghĩa riêng chức năng **stop instrumentation**, **cleanup resources** và (nếu thật sự cần) **rollback bytecode có điều kiện**. Không nên hứa “stop = trạng thái JVM giống hệt trước khi attach”, vì class đã nạp, JIT state, thread, static state, module mở rộng và side effect có thể không đảo ngược hoàn toàn.

## 6. Thiết kế một agent có thể dừng có kiểm soát

Một agent có thể giữ `Instrumentation` và đối tượng transformer trong trường static để tự gỡ đăng ký. Đoạn sau là **mã minh họa đặt bên trong class agent**, **không phải chương trình Java độc lập**:

```java
// Ví dụ thành viên của một agent có cơ chế điều khiển riêng.
private static Instrumentation instrumentation;
private static ClassFileTransformer transformer;

public static synchronized void start(Instrumentation inst) {
    if (transformer != null) {
        return; // Tránh đăng ký trùng nếu agentmain được gọi lại.
    }

    instrumentation = inst;
    transformer = (loader, name, type, domain, bytes) -> {
        // Quan sát hoặc sửa class được JVM giao.
        return null;
    };
    instrumentation.addTransformer(transformer, false);
}

public static synchronized void stop() {
    if (transformer != null) {
        instrumentation.removeTransformer(transformer);
        transformer = null;
    }
    // Tiếp tục dừng scheduler, endpoint và tài nguyên khác nếu có.
}
```

Để gọi `stop()` **từ bên ngoài JVM đích**, cần **một cơ chế điều khiển do agent/ứng dụng thiết kế**: chẳng hạn JMX MBean với thao tác stop, endpoint quản trị có bảo vệ, kênh IPC nội bộ hoặc một lần attach mới để gửi yêu cầu điều khiển cho agent. Chính `VirtualMachine.detach()` **không gọi** hàm stop này.

Ở mức thiết kế cần giải quyết cả:

1. **Idempotence:** hai lệnh start hoặc stop liên tiếp không tạo đăng ký trùng/lỗi.
2. **Race:** callback đang chạy có thể chồng thời điểm stop; transformer phải chịu được callback đến sau `removeTransformer` do đồng thời.
3. **Tài nguyên:** giải phóng executor, socket, MBean, hook và tham chiếu giữ class loader khi cần.
4. **Quản lý trạng thái:** bảo toàn dữ liệu mà ứng dụng khác có thể cũng đã sửa sau khi agent attach.
5. **Tính tương thích bytecode:** nếu muốn xử lý lớp đã biến đổi, đánh giá capability và cơ chế khác đang transform cùng lớp, không tự ý restore bytes cũ không còn phù hợp.

Một chiến lược phổ biến cho profiler là **ngừng thu thập sự kiện** mà không cam kết gỡ toàn bộ dấu vết bytecode của instrumentation. Với agent đòi hỏi loại bỏ hoàn toàn mọi thay đổi, cần thiết kế khả năng đảo ngược ngay từ đầu và kiểm chứng trên JVM/phiên bản thực tế.

## 7. Khác biệt dễ nhầm giữa detach, dispose, remove và kết thúc JVM

| Hành động | Đối tượng bị tác động | Ý nghĩa |
| --- | --- | --- |
| `VirtualMachine.detach()` | Handle/kết nối Attach của controller | Ngắt phiên quản trị tới JVM đích; **không gỡ agent**. |
| `Instrumentation.removeTransformer(t)` | Đăng ký transformer `t` trong JVM đích | Dừng phần lớn các callback tương lai cho đăng ký này; không rollback class đã transform. |
| `ExecutorService.shutdown()` hoặc cơ chế stop riêng | Tác vụ/tài nguyên do agent quản lý | Thực hiện ngừng hoạt động từng phần mà agent định nghĩa. |
| `Instrumentation.retransformClasses(...)` | Class đã tải, nếu JVM/cấu hình hỗ trợ | Áp dụng lại quá trình transform theo các quy tắc đặc biệt; kết quả phụ thuộc transformer hiện có. |
| `Instrumentation.redefineClasses(...)` | Class đã tải, nếu JVM/cấu hình hỗ trợ | Thay định nghĩa với class bytes mới trong giới hạn JVM; không tự xóa mọi side effect runtime. |
| Controller process kết thúc | Chương trình attach bên ngoài | Không đồng nghĩa JVM đích dừng hay agent bị dọn. |
| JVM đích kết thúc | Toàn bộ runtime đích | Các hoạt động Java trong tiến trình đó chấm dứt; chỉ dấu vết ở hệ thống ngoài vẫn có thể tồn tại tùy agent. |

Tách bạch này hữu ích khi gỡ lỗi “đóng profiler UI rồi mà vẫn thấy log của agent” hoặc “tool attach thoát nhưng ứng dụng vẫn bị instrument”. Kết quả đó có thể **hoàn toàn đúng theo API**.

## 8. Một số tình huống thực tế

### Tình huống A — Công cụ attach là tiến trình ngắn hạn

Công cụ giám sát chạy khoảng vài giây để attach, `loadAgent`, `detach` rồi thoát. Agent khởi tạo thread thu thập metric chạy lâu dài trong JVM đích. **Không cần giữ controller sống** chỉ để thread trong JVM đích tiếp tục hoạt động. Để xem metric, cần endpoint hoặc cách trích xuất được agent thiết kế; sự tồn tại của agent **không tự cung cấp** kênh quản trị sau detach.

### Tình huống B — Đóng cửa sổ quản trị nhưng JVM vẫn in log

Cửa sổ quản trị có thể đã dùng `VirtualMachine.detach` thành công. Nếu transformer của agent vẫn được đăng ký, các sự kiện class loading tiếp theo vẫn gọi transformer và log vẫn xuất hiện. Hành động cần làm là yêu cầu agent stop qua kênh quản trị của nó hoặc khởi động lại JVM đích nếu không có đường dừng phù hợp.

### Tình huống C — Controller muốn gọi phương thức trên handle cũ

Sau:

```java
// Trích đoạn Java minh họa. vm là VirtualMachine đã attach thành công.
vm.detach();
vm.getSystemProperties(); // IOException theo hợp đồng API.
```

Handle đó không dùng lại được cho các thao tác attach. Điều này **chỉ chứng minh controller không còn kết nối**, không nói gì về việc agent đã dừng.

### Tình huống D — Đóng kết nối trước khi `agentmain` hoàn tất

Nếu nhiều thread trong controller gọi `loadAgent` và `detach` trên cùng handle cùng lúc, không được dựa vào việc lời gọi nạp sẽ luôn thành công: tài liệu `VirtualMachine.detach` quy định kết quả của thao tác đang diễn ra là phụ thuộc implementation. Vì vậy quy trình bình thường phải **đợi `loadAgent` hoàn tất trước khi detach**. Với task agent bất đồng bộ, agent chịu trách nhiệm điều phối chính tác vụ của nó.

### Tình huống E — Gỡ transformer rồi vẫn thấy class đã bị instrument

Nếu trước đó transformer đã chèn bytecode vào một phương thức, `removeTransformer` chỉ bỏ đăng ký xử lý các lần định nghĩa tương lai; các lớp đã được cài đặt định nghĩa biến đổi vẫn mang bytecode đó. Muốn sửa lại class đang chạy phải xem xét các API retransform/redefine, khả năng JVM, giới hạn thay đổi cấu trúc class và các transformer khác đang hoạt động.

## 9. Lỗi thường gặp và cách kiểm tra

| Dấu hiệu | Giải thích / bước kiểm tra |
| --- | --- |
| `detach` thành công nhưng agent tiếp tục log | Đây không nhất thiết là lỗi: kiểm tra transformer, thread, endpoint còn đang hoạt động trong JVM đích. |
| Controller gọi API trên `VirtualMachine` đã detach và nhận `IOException` | Hợp đồng API: handle đã bị vô hiệu hóa; attach lại nếu cần. |
| `loadAgent` không chạy được | Kiểm tra JVM có attach provider và quyền phù hợp; PID, process owner, tùy chọn JVM và JAR/manifest. |
| `ClassNotFoundException`/agent load fail | Kiểm tra `Agent-Class`, vị trí JAR và dependency mà target JVM có thể tải. |
| Không có `AGENT saw LateLoaded` trong bài thực hành | Bảo đảm gõ `load` **sau khi controller detach**, class chưa được load trước đó và JAR agent đã cài transformer thành công. |
| Gỡ transformer mà vẫn thấy log một lần | Callback có thể đang chạy đồng thời lúc remove; đặt cờ dừng và xử lý race. |
| Mong bytecode tự hoàn nguyên sau khi stop | `removeTransformer` không phải rollback; phải thiết kế chiến lược khôi phục riêng. |
| Chạy controller trên JRE rút gọn bị lỗi `jdk.attach` | Module có thể không được đóng gói; sử dụng JDK/runtime có `jdk.attach` và hỗ trợ attach. |
| Cố attach JVM đang bị chặn | Một số JVM/cấu hình, môi trường container hoặc quyền OS không hỗ trợ thao tác; dùng môi trường thử nghiệm được cấp quyền. |
| Nhầm tải agent với kết nối debugger | Attach API có thể tải instrumentation agent; JDWP debugger có giao thức, đời sống kết nối và thao tác riêng. Không dùng `VirtualMachine.detach` như phép “detach debugger” phổ quát. |

Nếu thấy agent vẫn hoạt động sau khi controller thoát, đừng chỉ xem PID của controller. Hãy quan sát **PID ứng dụng đích**, log phía target, class load/transform mới, thread/tài nguyên còn được agent giữ và trạng thái control endpoint nếu có.

## 10. Tự kiểm tra

**Câu 1.** Controller gọi `attach → loadAgent → detach`, sau đó ứng dụng đích nạp class mới và transformer vừa đăng ký được gọi. Hành vi đó đúng hay sai?

**Đáp án:** Đúng. `detach` chấm dứt kết nối Attach của controller, còn transformer được đăng ký trong JVM đích tiếp tục tồn tại cho đến khi có thao tác gỡ hoặc JVM kết thúc.

**Câu 2.** Sau detach, có thể gọi `vm.loadAgent(...)` thêm lần nữa bằng đối tượng `vm` đã detach?

**Đáp án:** Không. Những thao tác tiếp theo trên handle `VirtualMachine` đã detach sẽ ném `IOException`; cần attach lại để có handle mới nếu JVM đích cho phép.

**Câu 3.** Agent gọi `Instrumentation.removeTransformer(t)` thì mọi method đã bị t thay đổi sẽ tự về code cũ?

**Đáp án:** Không. Lời gọi này bỏ đăng ký transformer, không bảo đảm hoàn nguyên bytecode đã được cài vào các lớp trước đó.

**Câu 4.** Việc `agentmain` đã return có chứng minh các thread do agent khởi tạo đều đã dừng?

**Đáp án:** Không. `agentmain` có thể tạo thread hoặc đăng ký callback để chạy dài hạn. `loadAgent` đợi `agentmain` return, chứ không đợi mọi công việc nền hoàn tất.

**Câu 5.** Agent muốn có nút “Stop monitoring” sau khi controller ban đầu thoát. Cần thiết kế gì?

**Đáp án:** Một kênh quản trị mới hoặc duy trì khả năng nhận lệnh, lưu tham chiếu transformer, điều phối dừng callback/thread/tài nguyên, rồi chủ động gọi API cleanup. Không dựa vào `VirtualMachine.detach` để thực hiện việc đó.

## 11. Tóm tắt và tài liệu tham khảo

- **`detach()` chỉ dừng một phiên Attach**, không phải lời gọi unload agent. Nó làm handle `VirtualMachine` của controller không còn sử dụng được.
- **`loadAgent(...)` gọi `agentmain(...)` trong JVM đích**. Sau khi `agentmain` return, những callback, biến đổi class và tài nguyên mà agent đã thiết lập có thể tiếp tục hoạt động.
- **Dừng instrumentation** phải do agent quản lý bằng `removeTransformer` và cleanup phù hợp; muốn khôi phục bytecode đã biến đổi là một vấn đề riêng, có điều kiện.
- **Để chứng minh được sự khác biệt**, kiểm tra một hiệu ứng mới của agent **sau khi controller detach**, như transformer trong bài thực hành ghi log khi lớp `LateLoaded` được nạp.

Tài liệu chính thức Java SE 17:

1. **`com.sun.tools.attach.VirtualMachine`** — `attach`, `loadAgent`, `detach` và vòng đời handle: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
2. **`java.lang.instrument` package** — cơ chế Java agent, `Agent-Class`, `agentmain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. **`Instrumentation`** — `addTransformer`, `removeTransformer`, `retransformClasses`, `redefineClasses`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
4. **`ClassFileTransformer`** — quy tắc callback và `return null`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html