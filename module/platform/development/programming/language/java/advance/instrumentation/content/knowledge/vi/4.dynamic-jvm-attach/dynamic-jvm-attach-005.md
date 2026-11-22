# `Agent-Class`, hai chữ ký `agentmain` và cách truyền `agentArgs` khi attach vào JVM

Một Java agent không nhất thiết phải được nạp lúc ứng dụng khởi động bằng `-javaagent`. Trên JVM hỗ trợ cơ chế **dynamic attach**, một tiến trình công cụ có thể kết nối đến JVM **đang chạy**, yêu cầu nạp một JAR agent và truyền một chuỗi tùy chọn. Khi đó JVM đích đọc `Agent-Class` trong manifest của JAR, nạp lớp agent và gọi phương thức **`agentmain`**.

Ba câu hỏi quan trọng cần tách biệt:

1. **Nạp lớp agent nào?** — `Agent-Class` trong `META-INF/MANIFEST.MF`.
2. **Gọi phương thức nào?** — JVM ưu tiên `public static void agentmain(String, Instrumentation)`, rồi mới dùng `public static void agentmain(String)` nếu không có dạng hai tham số.
3. **Tùy chọn đi đến đâu?** — `VirtualMachine.loadAgent(jarPath, options)` truyền `options` như **một chuỗi `String`** tới `agentArgs`; JVM không tự phân tích các cặp `key=value`.

Bài này thuộc nhóm **Attach vào JVM**. Trọng tâm là hợp đồng giữa công cụ attach, JAR agent và `agentmain`; chưa đi sâu vào thuật toán viết lại bytecode.

## 1. Luồng từ tiến trình công cụ tới JVM đang chạy

```text
Tiến trình A: ứng dụng Java đang chạy (target JVM)
   demo.TargetApp.main(...)
             ^
             | attach / load agent
             |
Tiến trình B: công cụ điều khiển (attacher JVM)
   VirtualMachine.attach(targetPid)
             |
   vm.loadAgent("/abs/path/agent.jar", "mode=trace,tag=alpha")
             |
             v
Target JVM đọc JAR agent
   META-INF/MANIFEST.MF
      Agent-Class: demo.AgentBoth
             |
             v
Nạp demo.AgentBoth vào target JVM
             |
             +-- Có public static void agentmain(String, Instrumentation)?
             |      Có -> gọi chữ ký hai tham số
             |
             +-- Nếu không -> tìm public static void agentmain(String)
             |
             v
agentmain khởi tạo, tùy ý dùng Instrumentation, rồi return
             |
             v
loadAgent(...) hoàn tất; ứng dụng đích vẫn đang chạy
```

Cần phân biệt **hai JVM**: JVM chạy công cụ attach gọi `VirtualMachine.attach/loadAgent`, còn `agentmain` chạy **bên trong JVM đích**, không chạy trong tiến trình attacher. Vì vậy log `System.out` của `agentmain` thường xuất hiện ở đầu ra của ứng dụng đích; log của chương trình attacher xuất hiện ở terminal công cụ.

**Attach không đồng nghĩa đã sửa bytecode.** Agent có thể chỉ in log, đo đạc, đăng ký một transformer hoặc làm thao tác quản trị. Việc JVM gọi được `agentmain` chỉ chứng minh điểm vào đã hoạt động; biến đổi một lớp cần thêm logic instrumentation phù hợp.

## 2. `Agent-Class` trong manifest: tên lớp, không phải tên tệp

JAR có thể được dùng làm dynamic agent khi manifest ở `META-INF/MANIFEST.MF` khai báo **main attribute**:

```text
Manifest-Version: 1.0
Agent-Class: demo.AgentBoth

```

Ý nghĩa:

- `Agent-Class` là **tên khóa chính xác**. Không thay bằng `Main-Class` hay `Premain-Class` khi muốn kích hoạt agent qua `VirtualMachine.loadAgent(...)`.
- `demo.AgentBoth` là **binary name** của lớp Java, sử dụng dấu chấm để phân cách package, không có `.java` hoặc `.class`.
- Lớp `demo.AgentBoth` phải có thể được JVM đích nạp. Trong ví dụ ta đặt file `demo/AgentBoth.class` ngay trong agent JAR.
- Header phải nằm trong **main section** của manifest, trước các `Name:` entry section riêng; việc một dòng văn bản tương tự xuất hiện ở vị trí khác không đảm bảo hợp đồng agent.
- Dòng trắng cuối ví dụ kết thúc main section; có thể dùng `jar --create --manifest` để tạo archive và kiểm tra manifest thực tế.

Các chuỗi sau không có nghĩa là giá trị `Agent-Class` hợp lệ cho lớp `demo.AgentBoth`:

```text
Agent-Class: demo/AgentBoth.class
Agent-Class: src/demo/AgentBoth.java
Agent-Class: demo.AgentBoth.class
```

Đường dẫn file `.class` trong JAR và tên lớp trong manifest phục vụ hai mục đích khác nhau:

```text
JAR entry:       demo/AgentBoth.class
Manifest value:  demo.AgentBoth
```

JAR chỉ có `Agent-Class` **không tự kích hoạt** khi nằm trong classpath của ứng dụng. Phải có cơ chế yêu cầu JVM đích nạp agent, chẳng hạn Attach API `VirtualMachine.loadAgent`. Việc thực sự có thể attach còn tùy runtime và cấu hình bảo vệ của JVM đích.

## 3. Hai chữ ký `agentmain` hợp lệ và thứ tự ưu tiên

### 3.1. Dạng đầy đủ, được JVM ưu tiên

```java
public static void agentmain(String agentArgs, Instrumentation inst)
```

Cần import:

```java
import java.lang.instrument.Instrumentation;
```

Giải thích hợp đồng:

| Thành phần | Vai trò |
|---|---|
| `public` | Điểm vào có khả năng được JVM gọi theo hợp đồng |
| `static` | Không cần tạo đối tượng agent |
| `void` | Không có giá trị trả về |
| `agentmain` | Chính xác tên phương thức, phân biệt chữ hoa/chữ thường |
| `String agentArgs` | Nhận chuỗi options của lần load agent |
| `Instrumentation inst` | API instrumentation do JVM đích cấp |

Đoạn minh họa **chưa phải file Java độc lập**:

```java
public static void agentmain(String agentArgs, Instrumentation inst) {
    System.out.println("args=" + agentArgs);
    System.out.println("has instrumentation=" + (inst != null));
}
```

Dạng này thích hợp khi agent cần dùng `inst.addTransformer(...)`, `inst.getAllLoadedClasses()`, `inst.isRetransformClassesSupported()` hoặc các API khác. Có reference `Instrumentation` **không bảo đảm** mọi khả năng đều được hỗ trợ: phải kiểm tra phương thức capability và giới hạn từng thao tác.

### 3.2. Dạng rút gọn, fallback hợp lệ

```java
public static void agentmain(String agentArgs)
```

Đây cũng là chữ ký được đặc tả công nhận. JVM dùng nó **chỉ khi lớp agent không cung cấp chữ ký hai tham số phù hợp**. Nó nhận options nhưng không nhận trực tiếp đối tượng `Instrumentation` qua tham số.

Ví dụ method minh họa:

```java
public static void agentmain(String agentArgs) {
    System.out.println("agent options=" + agentArgs);
}
```

Dạng một tham số phù hợp với agent chỉ cần một hành động khởi tạo hoặc xử lý cấu hình đơn giản. Nếu cần trực tiếp đăng ký transformer, nên khai báo dạng hai tham số.

### 3.3. Khi cả hai overload cùng tồn tại

Giả sử một lớp có:

```java
public static void agentmain(String agentArgs) {
    System.out.println("one-arg");
}

public static void agentmain(String agentArgs, Instrumentation inst) {
    System.out.println("two-arg");
}
```

Khi được nạp qua Attach API, JVM gọi **dạng hai tham số**; không chạy cả hai method và không dựa vào thứ tự khai báo trong file Java.

| Method trong agent | Có phải điểm vào hợp lệ? | Chú thích |
|---|---|---|
| `public static void agentmain(String, Instrumentation)` | Có | Được ưu tiên |
| `public static void agentmain(String)` | Có | Fallback nếu thiếu dạng trên |
| Cả hai | Có | Chỉ gọi dạng hai tham số |
| `private static void agentmain(String)` | Không | Thiếu `public` |
| `public void agentmain(String)` | Không | Thiếu `static` |
| `public static int agentmain(String)` | Không | Sai kiểu trả về |
| `public static void agentmain(Instrumentation, String)` | Không | Sai thứ tự và kiểu vị trí |
| `public static void agentmain(String[] args)` | Không | `String[]` không phải `String` |
| `public static void agentMain(String)` | Không | Sai chữ hoa/chữ thường |

Nếu không có chữ ký hợp lệ, dynamic agent **không được khởi tạo thành công**. Tuy nhiên lỗi nạp dynamic agent không có cùng hậu quả với lỗi `premain` lúc khởi động: đặc tả `java.lang.instrument` không yêu cầu JVM đích hủy cả ứng dụng vì lỗi `agentmain`; công cụ gọi `loadAgent` có thể nhận exception và cần xử lý.

## 4. `agentArgs` được truyền thế nào?

Lệnh Java gọi trực tiếp `agentmain` không có sẵn. Thay vào đó, công cụ dùng Attach API trong module `jdk.attach`:

```java
VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    vm.loadAgent(absoluteJarPath, "mode=trace,tag=alpha");
} finally {
    vm.detach();
}
```

Đây là **đoạn code minh họa**; ví dụ hoàn chỉnh ở phần 5 có import, tên lớp và xử lý arguments đầy đủ.

`loadAgent(String agent, String options)` đưa nguyên `options` đến JVM đích, sau đó agent nhận qua tham số `agentArgs` của `agentmain`. Ví dụ:

| Phía attacher | Giá trị agent nhận |
|---|---|
| `loadAgent(path, "verbose")` | `verbose` |
| `loadAgent(path, "mode=trace,tag=alpha")` | `mode=trace,tag=alpha` |
| `loadAgent(path, "a=b=c")` | `a=b=c` |
| `loadAgent(path, "")` | Chuỗi rỗng |
| `loadAgent(path)` | Tương đương `loadAgent(path, null)` ở API; agent cần chấp nhận khả năng không có options |

Không có bước JVM tự tách `mode`, `tag`, dấu phẩy hay dấu `=` thành nhiều tham số. **Quy ước cú pháp options do người viết agent định nghĩa.** Nếu sử dụng `split(",")`, `split("=", 2)` hoặc parser thư viện, đó là logic do chính agent bổ sung. Dữ liệu options cũng cần được kiểm tra null/rỗng và kiểm tra giá trị hợp lệ.

`agentArgs` ở đây **không phải**:

- `String[] args` của `main` trong ứng dụng đích;
- PID của tiến trình đích;
- đường dẫn tới JAR agent;
- một map được JVM parse sẵn;
- các tham số dòng lệnh JVM ban đầu.

**Hai thông tin tách biệt khi gọi `loadAgent`:**

```text
vm.loadAgent("/abs/path/agent.jar", "mode=trace,tag=alpha")
               |                        |
               |                        +--> agentmain(String agentArgs, ...)
               +--> JAR + manifest Agent-Class --> lớp agent
```

`agent`/`jarPath` phải là đường dẫn tới **JAR có thể truy cập được từ hệ thống file của JVM đích**, vì path được chuyển cho JVM đích để mở. Với ứng dụng đích trên cùng máy, truyền đường dẫn tuyệt đối thường tránh nhầm thư mục làm việc. Nếu công cụ và target không chia sẻ filesystem, cùng một chuỗi đường dẫn trên attacher không bảo đảm JAR tồn tại bên target.

## 5. Ví dụ Java 17+: attach thật giữa hai tiến trình, kiểm tra hai chữ ký và `agentArgs`

Ta tạo một chương trình đích giữ JVM hoạt động, hai agent JAR và một công cụ attach. Mục tiêu của ví dụ là **chứng minh hợp đồng `Agent-Class`, chữ ký được chọn và chuỗi options được truyền nguyên vẹn**; các agent chỉ ghi log, không sửa bytecode.

Yêu cầu môi trường: JDK 17+ có module `jdk.attach`, công cụ `javac`, `jar`, `java`, `jps`, JVM đích cho phép attach, hai tiến trình do cùng tài khoản hệ điều hành chạy. Các lệnh minh họa dùng cơ chế Attach API có sẵn trên HotSpot/OpenJDK; JVM khác hoặc môi trường container có thể yêu cầu thiết lập bổ sung.

Cấu trúc thư mục dự kiến:

```text
attach-agent-demo/
├── src/
│   └── demo/
│       ├── TargetApp.java
│       ├── AgentBoth.java
│       ├── AgentOne.java
│       └── AttachClient.java
└── manifests/
    ├── both.mf
    └── one.mf
```

### 5.1. Ứng dụng đích: `src/demo/TargetApp.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;

public final class TargetApp {
    private TargetApp() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("[target] started; awaiting dynamic attach");
        new CountDownLatch(1).await();
    }
}
```

`CountDownLatch(1).await()` giữ tiến trình ở trạng thái chờ để đủ thời gian attach. Nó **không** tự bật khả năng attach hay instrumentation. Sau khi thử xong, dừng tiến trình đích bằng `Ctrl+C` trong terminal đã chạy nó.

### 5.2. Agent có **cả hai chữ ký**: `src/demo/AgentBoth.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentBoth {
    private AgentBoth() {
    }

    public static void agentmain(String agentArgs) {
        System.out.println("[both] one-argument agentmain");
        System.out.println("[both] options=" + agentArgs);
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        System.out.println("[both] two-argument agentmain");
        System.out.println("[both] options=" + agentArgs);
        System.out.println("[both] instrumentation=" + (inst != null));
    }
}
```

Cố ý đặt method một tham số **trước** method hai tham số. Thứ tự trong source không quan trọng; khi load thành công, chỉ method hai tham số được chọn. Dòng kiểm tra `inst != null` không phụ thuộc vào JVM có hỗ trợ retransform hay không, bởi `Instrumentation` là đối tượng điểm vào được cung cấp.

### 5.3. Agent chỉ có dạng fallback: `src/demo/AgentOne.java`

```java
package demo;

public final class AgentOne {
    private AgentOne() {
    }

    public static void agentmain(String agentArgs) {
        System.out.println("[one] one-argument agentmain");
        System.out.println("[one] options=" + agentArgs);
    }
}
```

Không có method hai tham số, JVM dùng method một tham số. Đây là hành vi bình thường và hợp lệ.

### 5.4. Công cụ attach: `src/demo/AttachClient.java`

```java
package demo;

import java.nio.file.Path;
import com.sun.tools.attach.VirtualMachine;

public final class AttachClient {
    private AttachClient() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: AttachClient <pid> <agent.jar> <options>");
            return;
        }

        String pid = args[0];
        String jarPath = Path.of(args[1])
                .toAbsolutePath()
                .normalize()
                .toString();
        String options = args[2];

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            // Agent-Class trong manifest chọn lớp có agentmain.
            // options được truyền nguyên chuỗi vào agentArgs.
            vm.loadAgent(jarPath, options);
        } finally {
            vm.detach();
        }

        System.out.println("[client] loadAgent returned");
    }
}
```

Các phần trách nhiệm được tách rõ:

- `VirtualMachine.attach(pid)` kết nối tới JVM đích theo PID, nếu được phép.
- `Path.of(...).toAbsolutePath()` đưa đường dẫn JAR thành tuyệt đối, giúp target JVM trên cùng máy mở đúng file.
- `vm.loadAgent(jarPath, options)` yêu cầu target JVM nạp JAR và gọi `agentmain`.
- `finally { vm.detach(); }` giải phóng phiên kết nối attach kể cả khi `loadAgent` ném exception.
- Thông báo `[client] loadAgent returned` chỉ xuất hiện khi `loadAgent` hoàn tất bình thường. Nó không phải stdout của agent.

`VirtualMachine` thuộc module **`jdk.attach`** trên JDK, không thuộc package `java.lang.instrument`. Trong khi đó, `Instrumentation` thuộc module `java.instrument`. `AttachClient` chỉ cần Attach API; chính agent nhận `Instrumentation` khi chạy **trong target JVM**.

### 5.5. Hai manifest thực sự dùng `Agent-Class`

Tạo file **`manifests/both.mf`** với nội dung:

```text
Manifest-Version: 1.0
Agent-Class: demo.AgentBoth

```

Tạo file **`manifests/one.mf`**:

```text
Manifest-Version: 1.0
Agent-Class: demo.AgentOne

```

Giữ dòng xuống dòng ở cuối. Trong hai ví dụ, manifest **không cần** `Premain-Class`, vì ta không dùng `-javaagent`. Cũng không cần đặt `Can-Retransform-Classes: true`: chương trình chỉ nhận điểm vào và in log, chưa yêu cầu retransform.

### 5.6. Biên dịch và tạo hai JAR

Mở terminal tại thư mục `attach-agent-demo`. Chạy với JDK 17+:

```bash
mkdir out

javac --add-modules jdk.attach -encoding UTF-8 -d out src/demo/TargetApp.java src/demo/AgentBoth.java src/demo/AgentOne.java src/demo/AttachClient.java

jar --create --file agent-both.jar --manifest manifests/both.mf -C out demo/AgentBoth.class
jar --create --file agent-one.jar --manifest manifests/one.mf -C out demo/AgentOne.class
```

Các lệnh dùng tên file cụ thể nên dùng được trong Bash, PowerShell và cmd. Thư mục `out` ở đây được tạo mới một lần; nếu đã tồn tại, bỏ qua bước `mkdir out`.

Giải thích:

1. `--add-modules jdk.attach` cho phép chương trình biên dịch tham chiếu module Attach API.
2. `-d out` xuất class theo package, chẳng hạn `out/demo/AttachClient.class`.
3. Mỗi `jar --create --manifest` ghi một manifest chọn agent class tương ứng.
4. `-C out demo/AgentBoth.class` bảo đảm entry trong JAR là `demo/AgentBoth.class`, không phải `out/demo/AgentBoth.class`.

Để kiểm tra file JAR chứa class đúng, dùng:

```bash
jar --list --file agent-both.jar
jar --list --file agent-one.jar
```

Hai archive phải có `META-INF/MANIFEST.MF` và class tương ứng. Khi cần kiểm tra nội dung manifest, mở `META-INF/MANIFEST.MF` từ JAR; **có file `.class` không đủ**, vì header `Agent-Class` cũng phải đúng.

### 5.7. Terminal 1: chạy JVM đích

Tại thư mục `attach-agent-demo`, chạy:

```bash
java -XX:+EnableDynamicAgentLoading -cp out demo.TargetApp
```

Stdout ban đầu:

```text
[target] started; awaiting dynamic attach
```

Tiến trình tiếp tục chờ, không thoát. Trên HotSpot, `-XX:+EnableDynamicAgentLoading` thể hiện ý định cho phép nạp agent động; với JDK 21, tùy chọn này cũng tránh warning động nạp agent nêu trong JEP 451. Nó **không** vượt qua mọi giới hạn quyền hệ điều hành hoặc cơ chế attach.

### 5.8. Terminal 2: lấy PID và attach agent hai tham số

Trong terminal thứ hai, cùng máy và cùng tài khoản người dùng, chạy:

```bash
jps -l
```

Tìm dòng có tên lớp:

```text
<target-pid> demo.TargetApp
```

`<target-pid>` ở đây là **ký hiệu**, phải thay bằng PID số thực mà `jps` hiển thị. Các process ID khác cũng có thể xuất hiện và không cố định. Không copy nguyên dấu `<` hoặc `>` vào câu lệnh Java.

Ví dụ **cấu trúc lệnh**, thay `PID_THUC` bằng PID tìm được:

```bash
java --add-modules jdk.attach -cp out demo.AttachClient PID_THUC agent-both.jar "mode=trace,tag=alpha"
```

Khi attach thành công, **terminal 1** có thêm stdout:

```text
[both] two-argument agentmain
[both] options=mode=trace,tag=alpha
[both] instrumentation=true
```

**Terminal 2** in:

```text
[client] loadAgent returned
```

Nhận xét quan trọng:

- Target đã chạy `main` và đang chờ trước khi agent được nạp.
- JVM đọc `Agent-Class: demo.AgentBoth` rồi tìm `agentmain` phù hợp.
- Cả hai overload cùng tồn tại nhưng **không có** dòng `[both] one-argument agentmain`.
- `mode=trace,tag=alpha` đến đúng như **một chuỗi nguyên vẹn**.
- `System.out` của agent xuất hiện ở terminal target, vì `agentmain` chạy trong JVM đích.
- `loadAgent` trả về sau khi `agentmain` hoàn thành trong ví dụ này; nếu method ném lỗi, phần thông báo thành công của client không được in.

### 5.9. Terminal 2: attach tiếp agent chỉ có một tham số

Giữ nguyên target ở terminal 1, chạy:

```bash
java --add-modules jdk.attach -cp out demo.AttachClient PID_THUC agent-one.jar "level=basic"
```

**Terminal 1** nhận thêm:

```text
[one] one-argument agentmain
[one] options=level=basic
```

**Terminal 2** in:

```text
[client] loadAgent returned
```

Lần này `Agent-Class: demo.AgentOne` trỏ tới lớp không có method hai tham số, nên JVM gọi fallback `agentmain(String)`.

Sau hai lần attach, phần stdout của **terminal 1** theo thứ tự hợp lệ sẽ là:

```text
[target] started; awaiting dynamic attach
[both] two-argument agentmain
[both] options=mode=trace,tag=alpha
[both] instrumentation=true
[one] one-argument agentmain
[one] options=level=basic
```

Đây là stdout dự kiến từ **code demo** trên một lần chạy attach thành công, không tính các diagnostic của JVM trên stderr. Cảnh báo/đường dẫn/PID thực tế có thể phụ thuộc hệ điều hành và bản JDK. Nhấn `Ctrl+C` ở terminal 1 để kết thúc ví dụ.

## 6. Tự tách `agentArgs`: ví dụ parser có kiểm tra hợp lệ

Nếu quy ước options là các cặp `key=value` phân tách bằng dấu phẩy, agent có thể tự parse. Đoạn code dưới đây là **một class Java độc lập** minh họa cách parse, không thuộc chương trình demo mục 5:

**`OptionsParser.java`**

```java
import java.util.LinkedHashMap;
import java.util.Map;

public final class OptionsParser {
    private OptionsParser() {
    }

    public static Map<String, String> parse(String agentArgs) {
        Map<String, String> options = new LinkedHashMap<>();
        if (agentArgs == null || agentArgs.isBlank()) {
            return options;
        }

        for (String entry : agentArgs.split(",", -1)) {
            String[] pair = entry.split("=", 2);
            if (pair.length != 2 || pair[0].isBlank()) {
                throw new IllegalArgumentException("Invalid option: " + entry);
            }
            if (options.putIfAbsent(pair[0], pair[1]) != null) {
                throw new IllegalArgumentException("Duplicate key: " + pair[0]);
            }
        }
        return options;
    }

    public static void main(String[] args) {
        Map<String, String> result = parse("mode=trace,tag=alpha");
        System.out.println(result.get("mode"));
        System.out.println(result.get("tag"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 OptionsParser.java
java OptionsParser
```

Stdout chính xác:

```text
trace
alpha
```

Parser này **chỉ minh họa một quy ước đơn giản**: nó hỗ trợ tối đa dấu `=` đầu tiên trong mỗi entry (`split("=", 2)`) nhưng **không** hỗ trợ dấu phẩy được escape, chuỗi trích dẫn phức tạp, tên key có khoảng trắng hoặc chuẩn URI. Nếu cấu hình có dấu phẩy hoặc ký tự đặc biệt, hãy chọn định dạng rõ ràng hơn (URL encoding, JSON, file cấu hình có quyền truy cập phù hợp, v.v.). Đặc biệt tránh đưa token/mật khẩu bí mật vào dòng lệnh/process list nếu có thể bị tiến trình khác quan sát.

Trong `agentmain`, có thể gọi `OptionsParser.parse(agentArgs)` sau khi đã đưa parser vào agent JAR, nhưng cần tự quyết định chính sách khi gặp option sai: log, trả về hay báo lỗi để công cụ attach nhận biết. JVM không kiểm tra hộ cú pháp tùy biến này.

## 7. So sánh với `Premain-Class` / `premain`

| Khía cạnh | Startup agent | Dynamic attach agent |
|---|---|---|
| Tình huống | Trước khi application `main` chạy | JVM đích thường đã chạy `main` |
| Cách kích hoạt | `-javaagent:agent.jar[=options]` | Cơ chế attach/load, ví dụ `VirtualMachine.loadAgent(path, options)` |
| Manifest | `Premain-Class` | `Agent-Class` |
| Method ưu tiên | `premain(String, Instrumentation)` | `agentmain(String, Instrumentation)` |
| Method fallback | `premain(String)` | `agentmain(String)` |
| `agentArgs` | Một chuỗi từ phần options của `-javaagent` | Một chuỗi do công cụ gọi `loadAgent` truyền |
| Lỗi khởi tạo | Có thể làm JVM hủy startup | JVM đích không bị yêu cầu abort chỉ vì không nạp được dynamic agent; công cụ attach cần xử lý lỗi |
| Điều kiện phụ thuộc | JVM hỗ trợ startup Java agents | JVM có cơ chế attach, quyền thích hợp và cho phép dynamic loading |

Một agent JAR có thể hỗ trợ **cả hai cơ chế**:

```text
Manifest-Version: 1.0
Premain-Class: demo.BothModesAgent
Agent-Class: demo.BothModesAgent

```

Lớp đó phải tự định nghĩa `premain(...)` và `agentmain(...)` phù hợp. Khi khởi động bằng `-javaagent`, JVM chọn `Premain-Class` và `premain`; khi nạp vào JVM đang chạy, JVM dùng `Agent-Class` và `agentmain`. Không có thao tác tự chuyển tên method này sang tên method kia.

Cần phân biệt thêm `Launcher-Agent-Class` trong executable JAR: cơ chế đó cũng gọi **`agentmain`** nhưng hoạt động ở đường khởi động ứng dụng do launcher điều khiển, không đồng nghĩa một tiến trình attach đã kết nối từ bên ngoài. Với cơ chế này `agentArgs` được quy định là chuỗi rỗng. Đừng suy từ cùng tên `agentmain` rằng ba cách kích hoạt là một.

## 8. Điều kiện attach, cảnh báo và giới hạn runtime

### 8.1. Attach API là capability của JDK và JVM đích

Công cụ ví dụ sử dụng `com.sun.tools.attach.VirtualMachine` của module `jdk.attach`. Điều đó không bảo đảm mọi JVM đều cho phép attach mọi lúc. Những tình huống phải kiểm tra:

- Có đúng JDK/JVM hỗ trợ Attach API và module `jdk.attach` hay không?
- PID có tồn tại và còn sống không? Công cụ có chọn đúng process đích không?
- Công cụ và đích có cùng máy, tài khoản thích hợp, quyền truy cập và không gian PID/filesystem phù hợp không?
- Cấu hình JVM đích có tắt cơ chế attach (`-XX:+DisableAttachMechanism` ở HotSpot) hoặc disallow dynamic agent loading không?
- Đường dẫn JAR có tồn tại **đối với JVM đích** không? Manifest và agent class có đúng không?
- Có dependency của agent mà target class loader không tìm thấy không?

Một số VM tự attach vào **chính process của nó** bị hạn chế; ví dụ của ta dùng hai process độc lập để tránh đánh đồng self-attach với attach vào JVM khác. Cơ chế attach cũng khác với yêu cầu class retransform/redefine: nạp agent thành công chưa có nghĩa có quyền sửa mọi lớp.

### 8.2. JDK 21+ và chính sách dynamic agent loading

JEP 451 (JDK 21) bắt đầu đưa ra cảnh báo khi Java agent được **nạp động** vào một JVM HotSpot đang chạy nhằm chuẩn bị cho việc siết chặt mặc định trong các phiên bản tương lai. Khi dùng phiên bản có hành vi này, có thể thấy thông điệp trên **stderr** về dynamic agent loading; đó không phải dòng do `agentmain` trong ví dụ in ra.

Với HotSpot, cờ:

```bash
-XX:+EnableDynamicAgentLoading
```

cho phép/khai báo sự đồng ý với việc nạp agent động và có thể tránh warning liên quan. Phía đối lập:

```bash
-XX:-EnableDynamicAgentLoading
```

tắt dynamic agent loading. Đây là chính sách của **JVM đích**, không phải thứ có thể sửa bằng cách thêm `Agent-Class` đúng. Nếu attach được nhưng bước `loadAgent` bị từ chối, kiểm tra flag/cơ chế bảo vệ runtime trước khi nghi ngờ chữ ký `agentmain`.

Không nên giả định mặc định của mọi phiên bản JVM là giống nhau. Hãy kiểm tra tài liệu tương ứng JDK và JVM đang chạy; ví dụ chỉ yêu cầu một môi trường cho phép attach hợp pháp và có sự chấp thuận của người quản lý tiến trình.

### 8.3. Lỗi của `agentmain` khác lỗi startup `premain`

Tài liệu package `java.lang.instrument` nêu: nếu dynamic agent không khởi động được, JVM đích **không tự abort như trường hợp startup `premain` lỗi**. Một exception không bắt trong `agentmain` có thể được JVM ghi log; phía công cụ attach có thể nhận `AgentInitializationException` hoặc lỗi tải khác qua `VirtualMachine.loadAgent`.

Ví dụ app cần bắt lỗi ở phía client:

```java
try {
    vm.loadAgent(jarPath, options);
} catch (com.sun.tools.attach.AgentLoadException e) {
    System.err.println("Cannot load agent: " + e.getMessage());
} catch (com.sun.tools.attach.AgentInitializationException e) {
    System.err.println("Agent initialization failed: " + e.getMessage());
}
```

Đây là **đoạn minh họa bên trong chương trình có biến `vm`, `jarPath`, `options`**, không phải một file Java độc lập. Mã ứng dụng thực tế còn cần xử lý `IOException`, đảm bảo `detach()` và phân biệt lỗi không kết nối được target với lỗi bên trong agent. Không đọc lỗi `loadAgent` thành “JVM đích đã chết” nếu chưa kiểm tra trạng thái process.

## 9. Chẩn đoán theo ranh giới trách nhiệm

| Hiện tượng | Nơi cần kiểm tra |
|---|---|
| `VirtualMachine.attach(pid)` thất bại | PID sai/hết hạn, quyền OS, attach disabled, PID namespace, quyền của người dùng |
| `attach` thành công nhưng `loadAgent` thất bại | Dynamic loading bị chặn, JAR không có ở target, thiếu `Agent-Class`, manifest sai hoặc dependency thiếu |
| Không thấy stdout agent ở terminal công cụ | Agent chạy trong **target JVM**; kiểm tra stdout/log của target |
| JVM báo không tìm thấy agent class | `Agent-Class` có phải tên nhị phân? JAR có entry `.class` đúng package? |
| JVM báo không tìm thấy `agentmain` | Kiểm tra `public static void` và đúng hai chữ ký được hỗ trợ |
| Có cả hai method nhưng chỉ một cái chạy | Đúng hợp đồng: ưu tiên `agentmain(String, Instrumentation)` |
| Options đến dưới dạng nguyên chuỗi chưa tách | Đây là hành vi chuẩn; agent phải tự parse |
| `agentArgs` trống/null gây lỗi | Chuẩn bị xử lý không có options trước khi gọi `.split`, `.trim`, `.equals` |
| Attach được nhưng không thấy hành vi ứng dụng thay đổi | Agent mới in log? Đã đăng ký transformer/retransform phù hợp chưa? |
| JDK 21+ cảnh báo agent được nạp động | Kiểm tra JEP 451, flag đồng ý của target và chính sách runtime |
| Agent được nạp nhiều lần gây lỗi trạng thái | Thiết kế initialization có kiểm tra trạng thái/idempotent; không giả định một lần duy nhất |

Một lỗi thường gặp khi thử nghiệm là **khởi chạy ứng dụng đích bằng tùy chọn `-javaagent:agent-both.jar`** trong khi manifest chỉ có `Agent-Class`. Khi đó JVM startup yêu cầu `Premain-Class` và `premain`, nên cách chạy không phù hợp. Với JAR trong ví dụ, cần tiến trình attacher gọi `loadAgent`.

## 10. Câu hỏi kiểm tra nhanh

**1.** Manifest có `Agent-Class: demo.AgentBoth`. Lớp có cả `agentmain(String)` lẫn `agentmain(String, Instrumentation)`. Phương thức nào được chọn?

**Đáp án:** Dạng hai tham số; JVM không gọi cả hai.

**2.** `vm.loadAgent("/agents/agent.jar", "mode=trace,tag=alpha")`. Agent nhận mấy tham số cấu hình?

**Đáp án:** Một tham số `agentArgs` kiểu `String` có nội dung nguyên văn `mode=trace,tag=alpha`; có thể nhận thêm `Instrumentation` nếu dùng chữ ký hai tham số, nhưng đó không phải option cấu hình.

**3.** Tại sao log trong `agentmain` xuất hiện ở terminal của ứng dụng đích?

**Đáp án:** Vì `agentmain` chạy trong JVM đích; `AttachClient` chỉ gửi lệnh nạp agent.

**4.** `Agent-Class` viết đúng nhưng JVM không cho attach. Có phải chắc chắn lỗi manifest?

**Đáp án:** Không. Cần kiểm tra attach support, quyền OS, PID, target filesystem và chính sách dynamic loading.

**5.** Dùng `-javaagent` với JAR chỉ khai báo `Agent-Class` có kích hoạt `agentmain` không?

**Đáp án:** Không. `-javaagent` yêu cầu `Premain-Class`/`premain`; `Agent-Class` phục vụ cơ chế nạp sau startup.

**6.** Vì sao nên truyền đường dẫn tuyệt đối cho `loadAgent`?

**Đáp án:** Vì JVM đích sẽ diễn giải đường dẫn tới JAR trên filesystem mà nó nhìn thấy; đường dẫn tương đối có thể trỏ sang thư mục khác so với attacher.

**7.** Sau khi nạp agent thành công, một lớp đã load có tự bị thay bytecode không?

**Đáp án:** Không. Agent phải chủ động dùng API/cơ chế biến đổi phù hợp, kiểm tra khả năng của JVM và cung cấp logic transform.

## 11. Ghi nhớ cơ chế

- **`Agent-Class` → lớp agent**: thuộc tính bắt buộc của JAR được nạp động theo cơ chế hỗ trợ.
- **`agentmain` → điểm vào**: hai chữ ký hợp lệ là `(String, Instrumentation)` và `(String)`; JVM **ưu tiên chữ ký hai tham số**.
- **`VirtualMachine.loadAgent(jar, options)` → kích hoạt nạp**: công cụ attach yêu cầu JVM đích đọc JAR, gọi `agentmain`, và truyền `options` như một **chuỗi**.
- **Target JVM → nơi agent thực thi**: log của agent nằm phía tiến trình đích; quyền attach và khả năng dynamic load được kiểm tra riêng.
- **Instrumentation → khả năng thao tác sau khi attach**: nhận được đối tượng `Instrumentation` chưa đồng nghĩa tự thay bytecode; cần chủ động đăng ký transformer hoặc yêu cầu thao tác hợp lệ.

## Tài liệu tham khảo chính thức

- Oracle Java 17 — [`java.lang.instrument`: Starting an Agent After VM Startup](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- Oracle Java 17 — [`VirtualMachine` (Attach API)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- Oracle Java 17 — [`Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- OpenJDK — [JEP 451: Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- Oracle Java 21 — [`java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html)
