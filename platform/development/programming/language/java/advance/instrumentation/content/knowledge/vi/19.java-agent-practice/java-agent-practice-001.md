# Tạo agent premain tối thiểu và quan sát thời điểm chạy trước main

**Chủ đề:** Java Advance → instrumentation → **Thực nghiệm agent**.

`premain` là điểm vào của **Java startup agent**: khi chạy `java -javaagent:agent.jar ...`, JVM đọc `Premain-Class` trong manifest của JAR agent, nạp class agent và gọi phương thức `premain` **trước khi gọi phương thức `main(String[])` của chương trình ứng dụng**. Đây là cách đơn giản nhất để xác minh một agent được khởi động sớm, nhận các tùy chọn khởi tạo và lấy được đối tượng `Instrumentation` do JVM cung cấp.

Mục tiêu của thí nghiệm:

1. Tự viết **agent Java nhỏ nhất có thể quan sát được**: một class với `public static void premain(String, Instrumentation)`.
2. Tạo đúng **manifest** chứa `Premain-Class`, đóng gói bằng `jar` mà không cần Maven/Gradle.
3. Chạy **cùng ứng dụng** không có agent và có agent, so sánh **stdout chính xác**.
4. Chứng minh thứ tự **agent `premain` → application `main`** bằng cả log lẫn một trạng thái do agent đặt trước khi main đọc.
5. Thử **hai `-javaagent` trên cùng command line** và phân biệt `agentArgs` với `main(String[] args)`.
6. Mở rộng vừa đủ với `ClassFileTransformer` chỉ quan sát một class được nạp sau khi `main` bắt đầu, để hiểu rằng **`premain` trước `main` không đồng nghĩa mọi class đều được định nghĩa sau `premain`**.
7. Biết đọc lỗi manifest, đường JAR, chữ ký entry point, arguments và thời điểm class initialization.

**Điều kiện:** JDK 17+ có `javac`, `jar` và `java`, Terminal Bash hoặc Windows PowerShell. Ví dụ không cần native attach, không tải thư viện ngoài, không cần mở mạng, không sửa class file và có thể kiểm tra ngay từ stdout.

> **Từ đầu cần phân biệt:** `premain` được gọi sau khi JVM đã thực hiện các bước khởi tạo cần thiết, và **trước application `main`**. Nó **không phải đoạn Java đầu tiên của toàn bộ JVM**: JVM/agent infrastructure đã có thể tải và khởi tạo các lớp JDK hoặc agent support trước đó. Không suy ra danh sách loaded classes tại `premain` là trống.

## 1. Sơ đồ luồng startup

```text
Shell/launcher
    |
    | java -javaagent:startup-agent.jar=phase=boot
    |      -cp app-classes demo.DemoApp red blue
    v
JVM khởi tạo các thành phần nền tảng cần thiết
    |
    +-- Đọc startup-agent.jar!/META-INF/MANIFEST.MF
    |      Premain-Class: demo.StartupAgent
    |
    +-- Nạp demo.StartupAgent
    |      (static initialization của agent nếu có)
    |
    +-- Gọi demo.StartupAgent.premain(agentArgs, instrumentation)
    |      agentArgs = "phase=boot"
    |      Instrumentation do JVM cung cấp
    |      agent có thể đăng ký transformer / chuẩn bị telemetry
    |
    +-- premain trả về bình thường
    |
    +-- Gọi demo.DemoApp.main(String[] args)
           args = ["red", "blue"]
```

**Tại sao “trả về bình thường” quan trọng?** JVM phải hoàn thành startup agent trước khi chuyển sang application `main`. Nếu `premain` ném ngoại lệ không được xử lý hoặc thiếu điểm vào hợp lệ, JVM **có thể dừng khởi động**; đó là lỗi startup agent, không phải lỗi do application `main` chạy.

Cơ chế này được đặc tả trong package `java.lang.instrument`. JVM gọi một trong hai overload:

```java
// Fragment chữ ký API, không phải chương trình riêng.
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst);

public static void premain(String agentArgs);
```

JVM **ưu tiên chữ ký có `Instrumentation`**; nếu không có, mới thử chữ ký chỉ nhận `String`. Ví dụ chính sử dụng chữ ký đầu tiên để chứng minh agent nhận được đối tượng instrumentation thật từ JVM. Tên `premain` phải viết **chính xác chữ thường**, không phải `preMain`, `Premain` hoặc `main`.

### 1.1. Các vai trò trong chương trình

| Thành phần | Vai trò | Yêu cầu |
| --- | --- | --- |
| `-javaagent:startup-agent.jar` | JVM startup option | Đặt **trước** tên application main class hoặc trước `-jar` |
| `startup-agent.jar` | Artifact chứa agent | Có manifest và `demo/StartupAgent.class` |
| `Premain-Class` | Manifest main attribute | Giá trị là **fully qualified binary class name** có dấu chấm |
| `premain` | Java agent startup entry point | `public static void`, một trong hai chữ ký hợp lệ |
| `agentArgs` | Tùy chọn của agent | Một chuỗi được JVM truyền nguyên văn; agent tự parse |
| `Instrumentation` | API do JVM cung cấp | Không tự tạo bằng `new Instrumentation()` |
| `-cp app-classes` | Nơi tìm application classes | Không phải đường tới JAR agent |
| `demo.DemoApp` | Application main class | Có `public static void main(String[])` |
| `red blue` | Application arguments | Được chuyển vào `main`, không vào `premain` |

## 2. Cấu trúc dự án tự tạo

Tạo thư mục học tập, ví dụ `premain-lab`, với các file:

```text
premain-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── StartupAgent.java
│       ├── DemoApp.java
│       ├── WatchingAgent.java
│       ├── LoadApp.java
│       └── LazyTarget.java
├── watching-agent.mf
├── agent-classes/         # sinh khi biên dịch
├── app-classes/           # sinh khi biên dịch
├── startup-agent.jar      # sinh bởi jar
└── watching-agent.jar     # sinh bởi jar
```

**Hai tệp `WatchingAgent.java` và `watching-agent.mf` chỉ phục vụ bài mở rộng ở phần sau.** Để có thí nghiệm `premain` tối thiểu, ban đầu chỉ cần `StartupAgent.java`, `DemoApp.java` và `agent.mf`.

Có hai thư mục output riêng giúp thấy ranh giới:

- `agent-classes` chứa các classes được JAR agent đóng gói.
- `app-classes` chứa application class. `DemoApp` không phụ thuộc compile-time vào `StartupAgent`.

Chúng ta **không sửa source ứng dụng khi bật/tắt agent**: cả hai lần chạy dùng cùng `DemoApp.class` và chỉ thay launcher flag.

## 3. Mã agent tối thiểu

### 3.1. `src/demo/StartupAgent.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    private StartupAgent() {}

    public static void premain(
            String agentArgs, Instrumentation inst) {

        System.out.println("AGENT_PREMAIN=" + agentArgs);
        System.out.println(
                "INSTRUMENTATION_PRESENT=" + (inst != null));

        // Trạng thái minh họa cho main kiểm tra.
        System.setProperty("demo.premain.ready", "true");
    }
}
```

Đây là **một Java agent đầy đủ để thử startup**, dù nó chưa thực hiện bytecode transformation:

- JVM đọc manifest và tìm class `demo.StartupAgent`.
- JVM gọi `premain` với argument string do tùy chọn `-javaagent` cung cấp.
- `inst != null` in `true` trên JVM tuân thủ API; object `Instrumentation` không được tạo bằng code ứng dụng.
- Agent đặt system property `demo.premain.ready=true` nhằm tạo **dấu mốc quan sát**. Vì application `main` đọc property sau đó, ta kiểm tra thứ tự mà không dựa vào timestamp hay thread scheduling.
- Agent **không gọi `Instrumentation.addTransformer`**, không thao tác bytes, không attach và không tạo thread.
- Không cần `throws Exception`; nếu có lỗi trong `premain` mà không catch, JVM có thể abort startup.

**Chú ý tính đúng đắn:** `System.setProperty` ở đây là side effect **có chủ đích cho lab**. Production observability agent không nên tùy tiện sửa property/shared state của application. Cặp log trước/sau minh họa thứ tự; property flag không phải một cơ chế xác thực hay chống giả mạo, vì người dùng cũng có thể đặt `-Ddemo.premain.ready=true` mà không chạy agent.

### 3.2. `src/demo/DemoApp.java`

```java
package demo;

import java.util.Arrays;

public final class DemoApp {
    private DemoApp() {}

    public static void main(String[] args) {
        System.out.println("APP_MAIN");
        System.out.println("READY_AT_MAIN="
                + Boolean.getBoolean("demo.premain.ready"));
        System.out.println("APP_ARGS=" + Arrays.toString(args));
    }
}
```

Chương trình chính không import `java.lang.instrument` và không gọi trực tiếp `StartupAgent.premain`. Nó chỉ:

1. In `APP_MAIN`.
2. Đọc flag thông qua `Boolean.getBoolean(propertyName)`: trả `true` khi system property bằng chuỗi `"true"` không phân biệt chữ hoa/thường.
3. In arguments mà JVM truyền cho `main`.

**Sai lầm thường gặp:** `Boolean.getBoolean("demo.premain.ready")` **không** parse chuỗi ký tự đó như một boolean literal; nó **tìm system property có tên** `demo.premain.ready` rồi parse giá trị property. Đó chính là điều ta cần cho lab này.

### 3.3. `agent.mf` — manifest tối thiểu

```text
Manifest-Version: 1.0
Premain-Class: demo.StartupAgent
```

Lưu file dạng văn bản UTF-8 hoặc ASCII (nội dung này đều là ASCII) và **kết thúc bằng newline**, đúng quy ước manifest. Tên attribute phải là `Premain-Class` và giá trị phải là `demo.StartupAgent`, **không phải** `demo/StartupAgent` hoặc `StartupAgent.java`.

Với agent tối thiểu này, không cần:

- `Agent-Class`: dùng khi nạp Java agent sau startup bằng cơ chế attach, không phải bắt buộc cho `-javaagent`.
- `Can-Redefine-Classes`: dành cho capability redefining.
- `Can-Retransform-Classes`: dành cho capability retransformation.
- `Boot-Class-Path`: không cần vì agent không instrument bootstrap types.
- `Main-Class` trong agent JAR: chúng ta không chạy `java -jar startup-agent.jar`; chúng ta nạp nó qua `-javaagent` và chạy application riêng bằng `-cp`.

`jar --manifest` sẽ thêm metadata tiêu chuẩn cần thiết khi tạo JAR. Đừng viết mọi thứ trên một dòng duy nhất hoặc thiếu newline của manifest cuối file.

## 4. Biên dịch và đóng gói với JDK 17+

### 4.1. Lệnh Linux/macOS Bash

Đứng trong thư mục `premain-lab`:

```bash
mkdir -p agent-classes app-classes

javac --release 17 -d agent-classes src/demo/StartupAgent.java
javac --release 17 -d app-classes src/demo/DemoApp.java

jar --create --file startup-agent.jar \
    --manifest agent.mf -C agent-classes .

jar --list --file startup-agent.jar
```

Ý nghĩa:

- `javac --release 17` tạo class files tương thích Java 17 và giới hạn APIs theo release 17.
- `-d agent-classes` / `-d app-classes` giữ đúng cấu trúc package `demo/`.
- `jar --create --file ... --manifest agent.mf` tạo startup agent JAR có manifest được chỉ rõ.
- `-C agent-classes .` yêu cầu đưa **nội dung** output directory vào JAR (không đưa tên thư mục `agent-classes` vào đường class entry).
- `jar --list` giúp kiểm tra artifact. Kết quả có thể có timestamp/entries bổ sung tùy tool, nên ta không hardcode toàn bộ output; tối thiểu phải có `META-INF/MANIFEST.MF` và `demo/StartupAgent.class`.

### 4.2. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path agent-classes,app-classes | Out-Null

javac --release 17 -d agent-classes src/demo/StartupAgent.java
javac --release 17 -d app-classes src/demo/DemoApp.java

jar --create --file startup-agent.jar --manifest agent.mf -C agent-classes .
jar --list --file startup-agent.jar
```

Các tệp nguồn Java và manifest **giữ nguyên**. Trong PowerShell, viết lệnh `jar` trên một dòng để không dùng nhầm cú pháp xuống dòng của Bash `\`. Các dấu phân cách thư mục tương đối thông dụng trên Windows/JDK có thể dùng dấu `/` trong đường tệp lệnh JDK; nếu môi trường shell đặc biệt cần, dùng đường Windows tương đương.

### 4.3. Kiểm tra artifact trước khi chạy

```bash
jar --list --file startup-agent.jar
```

Kỳ vọng các mục trọng yếu trong listing:

```text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/StartupAgent.class
```

Thứ tự và metadata entries ngoài danh sách có thể khác. Nếu chỉ thấy `agent-classes/demo/StartupAgent.class` thay vì `demo/StartupAgent.class`, cách đóng gói sai: JVM sẽ không tìm thấy class `demo.StartupAgent` từ root của JAR.

Nếu manifest thiếu `Premain-Class`, khởi động bằng `-javaagent` không thành công dù JAR có bytecode class đúng. **Kiểm tra cả nội dung manifest lẫn class entry**, không chỉ tên file có đuôi `.jar`.

## 5. Chạy lần 1: baseline không có Java agent

```bash
java -cp app-classes demo.DemoApp
```

**Stdout chính xác** khi chạy trong JVM sạch và không có flag/property ngoại lai đặt `demo.premain.ready`:

```text
APP_MAIN
READY_AT_MAIN=false
APP_ARGS=[]
```

Tại sao?

- JVM tìm `demo.DemoApp` trong `app-classes`.
- Không có startup `-javaagent` nên `StartupAgent.premain` không được gọi.
- System property chưa được đặt, nên `Boolean.getBoolean("demo.premain.ready")` là `false`.
- Không truyền application arguments nên `Arrays.toString(args)` là `[]`.

Cùng ứng dụng có thể chạy bình thường **không cần agent**. Đây là kiểm tra quan trọng: nếu app source trực tiếp gọi `StartupAgent.premain`, đó là một chương trình dùng helper thông thường chứ không chứng minh JVM startup-agent mechanism.

## 6. Chạy lần 2: bật `-javaagent`

```bash
java -javaagent:startup-agent.jar=phase=boot \
    -cp app-classes demo.DemoApp red blue
```

Windows PowerShell một dòng:

```powershell
java -javaagent:startup-agent.jar=phase=boot -cp app-classes demo.DemoApp red blue
```

**Stdout chính xác** từ mã Java của lab:

```text
AGENT_PREMAIN=phase=boot
INSTRUMENTATION_PRESENT=true
APP_MAIN
READY_AT_MAIN=true
APP_ARGS=[red, blue]
```

Cách chứng minh:

1. `AGENT_PREMAIN` xuất hiện **trước** `APP_MAIN`, đúng hợp đồng JVM startup agent.
2. `Instrumentation` có sẵn tại `premain`, nên `INSTRUMENTATION_PRESENT=true`.
3. Agent đặt property rồi mới kết thúc `premain`; main đọc được `READY_AT_MAIN=true`.
4. Chuỗi `phase=boot` là **agentArgs**; `red blue` là **application arguments**.
5. Không có công việc xử lý bytecode trong ví dụ, nhưng agent vẫn hợp lệ và chạy trước `main`.

**Điều không thể kết luận từ stdout này:** số lớp JVM đã load ở thời điểm đó, class nào đã được verify/initialized, thời gian chính xác bao nhiêu nanosecond trước main, hay code của agent đã thay đổi class file. Bài này chứng minh đúng **thứ tự điểm vào** và **sự hiện diện của Instrumentation**, không phải tự động instrument mọi class.

### 6.1. Tại sao không dùng timestamp để so?

Nếu log thêm `System.nanoTime()`, các timestamp thay đổi mỗi lần chạy và không có epoch tuyệt đối giữa process. Với vấn đề “premain trước main”, **hai log trong cùng tiến trình** cùng một output stream và dấu property do agent đặt đủ minh họa đơn giản và dễ kiểm thử hơn. Khi cần đo startup overhead thật, dùng benchmark nhiều forks, thống nhất JDK/VM flags và công bố đo lường, không lấy một khoảng đo startup duy nhất làm kết luận.

### 6.2. Phân biệt `-D`, `-javaagent` và app args

Ví dụ:

```text
-javaagent:startup-agent.jar=phase=boot
    ^ tùy chọn VM, truyền phase=boot cho premain

-Ddemo.premain.ready=true
    ^ tùy chọn VM độc lập: đặt system property

demo.DemoApp red blue
             ^ đối số của main(String[] args)
```

Đặt `-Ddemo.premain.ready=true` có thể khiến baseline in `READY_AT_MAIN=true` mà **không có** `AGENT_PREMAIN`; vì vậy khi chứng minh đúng cơ chế, luôn dùng cả **log premain** và kiểm tra launcher command. Property chỉ là dấu mốc học tập, không phải khóa bảo mật hay một phép đo instrumentation activity.

## 7. Chạy hai Java startup agents cùng lúc

Oracle JDK 17 cho phép tùy chọn `-javaagent` xuất hiện nhiều lần, kể cả **cùng một JAR**. Các `premain` được gọi theo thứ tự xuất hiện trên dòng lệnh.

```bash
java -javaagent:startup-agent.jar=first \
    -javaagent:startup-agent.jar=second \
    -cp app-classes demo.DemoApp
```

Stdout:

```text
AGENT_PREMAIN=first
INSTRUMENTATION_PRESENT=true
AGENT_PREMAIN=second
INSTRUMENTATION_PRESENT=true
APP_MAIN
READY_AT_MAIN=true
APP_ARGS=[]
```

Đây là cùng mã `StartupAgent` được JVM gọi **hai lần** trong quá trình startup, không phải application main được gọi hai lần. Các argument strings của hai lần `premain` lần lượt là `first` và `second`; ứng dụng vẫn chỉ có một lần `APP_MAIN`.

Điều cần hiểu ở production:

- Gọi một agent hai lần có thể tạo **hai bộ transformer** nếu mỗi `premain` đăng ký một bộ, dẫn tới log trùng hoặc instrument lặp.
- Thứ tự `premain` không tự chứng minh thứ tự biến đổi cuối cùng nếu có class loading, transformer chaining hay tương tác phức tạp; đọc hợp đồng `ClassFileTransformer` và quan sát bytes khi cần.
- Agent nên có initialization guard/idempotency nếu hỗ trợ nhiều lần được khởi động và muốn tránh hook duplicate.
- Không giả định các startup agents từ những vendors khác nhau sẽ không xung đột classloaders, module accessibility, logging hay native dependencies.
- Nếu một `premain` throw uncaught, JVM có thể dừng trước khi tới `main` hoặc các startup steps tiếp theo.

## 8. Mở rộng: đăng ký một transformer tại `premain`

Ở bước tối thiểu, `premain` chỉ in log/đặt property. Ta có thể thêm một bài thực nghiệm **chỉ quan sát class load**: agent đăng ký `ClassFileTransformer` ngay trong `premain`, ứng dụng cố ý nạp một class tên `demo.LazyTarget` sau khi `main` đã in dấu bắt đầu.

Điều này trả lời câu hỏi: **nếu `premain` thực sự trước main, transformer được đăng ký khi nào, và có nhìn thấy một class load sau đó không?**

Để không làm phức tạp stdout của lab đầu tiên, dùng **agent thứ hai** có tên `WatchingAgent`. Nó chỉ đọc tên class và **trả `null`**, không sửa bytes.

### 8.1. `src/demo/WatchingAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class WatchingAgent {
    private WatchingAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("WATCHER_PREMAIN");

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if ("demo/LazyTarget".equals(className)) {
                    System.out.println("WATCHED_LOAD=demo/LazyTarget");
                }

                // Không sửa mảng classfileBuffer.
                return null;
            }
        });
    }
}
```

Các điểm cần kiểm tra:

- `inst.addTransformer(...)` đăng ký callback cho các định nghĩa class về sau. JVM có thể gọi callback khi class được load, redefine hoặc retransform tùy loại registration; ở lab này chỉ xét **load-time**.
- `className` dùng tên internal có dấu `/`: `demo/LazyTarget`, **không** phải `demo.LazyTarget`.
- `return null` là hợp đồng **không biến đổi class file**, không phải “trả một class file trống”.
- Không được thay đổi `classfileBuffer` tại chỗ. Nếu cần transform, phải trả một `byte[]` mới và hợp lệ.
- Biến `classBeingRedefined` thường `null` ở initial load; không nên ép luôn non-null.
- Callback có thể được gọi rất nhiều lần cho các class khác; lọc tên class **trước khi logging** giúp tránh log storm.
- Ở JDK 9+, interface còn overload sáu tham số với `Module`; bản override năm tham số trong ví dụ vẫn được hỗ trợ nhờ overload default chuyển tiếp.

**Lưu ý:** khi code chạy trong transformer, các operations như logging/reflection có thể kích hoạt thêm class loading và reentrancy. Bài này chỉ log đúng một class; một công cụ thật cần thiết kế initialization/reentrancy guard và loại trừ agent/helper classes.

### 8.2. `src/demo/LazyTarget.java`

```java
package demo;

public final class LazyTarget {
    static {
        System.out.println("LAZY_TARGET_INITIALIZED");
    }

    private LazyTarget() {}
}
```

Block `static` là **class initializer**, không đồng nghĩa thời điểm class file bytes được đọc. JVM có thể **load** một class trước khi nó cần initialize.

### 8.3. `src/demo/LoadApp.java`

```java
package demo;

public final class LoadApp {
    private LoadApp() {}

    public static void main(String[] args) throws Exception {
        System.out.println("LOAD_APP_MAIN");

        ClassLoader loader = LoadApp.class.getClassLoader();
        Class.forName("demo.LazyTarget", false, loader);
        System.out.println("AFTER_LOAD_NOT_INIT");

        Class.forName("demo.LazyTarget", true, loader);
        System.out.println("AFTER_INITIALIZE");
    }
}
```

`Class.forName(name, false, loader)` có thể làm JVM nạp/liên kết class cần thiết **mà không chạy class initializer tại chính lời gọi đó**. `Class.forName(name, true, loader)` yêu cầu khởi tạo nếu class chưa khởi tạo. Với lớp mẫu chỉ có một block `static` in log, dễ phân biệt **loading** và **initialization**.

### 8.4. `watching-agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.WatchingAgent
```

Nhớ newline cuối. Khác biệt giữa hai agent JAR là giá trị `Premain-Class`. `WatchingAgent` cũng không cần `Can-Retransform-Classes` vì chỉ muốn nhìn thấy class được nạp sau khi transformer đã được đăng ký.

### 8.5. Biên dịch và đóng gói bài mở rộng

Tại root `premain-lab` sau khi đã tạo các file mở rộng:

```bash
javac --release 17 -d agent-classes src/demo/WatchingAgent.java

javac --release 17 -d app-classes \
    src/demo/LoadApp.java src/demo/LazyTarget.java

jar --create --file watching-agent.jar \
    --manifest watching-agent.mf -C agent-classes .
```

Lệnh JAR đóng gói cả `StartupAgent.class` nếu đã có trong `agent-classes`, nhưng manifest của `watching-agent.jar` chỉ định `demo.WatchingAgent` nên JVM khởi động đúng class đó. Không có conflict vì chỉ một `Premain-Class` thuộc manifest.

Trên Windows PowerShell, có thể viết mỗi lệnh trên một dòng, bỏ ký tự `\` dùng tiếp dòng Bash:

```powershell
javac --release 17 -d agent-classes src/demo/WatchingAgent.java
javac --release 17 -d app-classes src/demo/LoadApp.java src/demo/LazyTarget.java
jar --create --file watching-agent.jar --manifest watching-agent.mf -C agent-classes .
```

### 8.6. Chạy và so output

Không có agent:

```bash
java -cp app-classes demo.LoadApp
```

Stdout:

```text
LOAD_APP_MAIN
AFTER_LOAD_NOT_INIT
LAZY_TARGET_INITIALIZED
AFTER_INITIALIZE
```

Có watcher:

```bash
java -javaagent:watching-agent.jar \
    -cp app-classes demo.LoadApp
```

Stdout trong **tiến trình sạch**, với `demo.LazyTarget` chưa bị component khác nạp trước thí nghiệm:

```text
WATCHER_PREMAIN
LOAD_APP_MAIN
WATCHED_LOAD=demo/LazyTarget
AFTER_LOAD_NOT_INIT
LAZY_TARGET_INITIALIZED
AFTER_INITIALIZE
```

Giải thích từng điểm:

1. `WATCHER_PREMAIN` in trước `LOAD_APP_MAIN`: entry point agent đi trước app main.
2. Khi `LoadApp.main` gọi `Class.forName(..., false, loader)`, transformer đã đăng ký nên thấy bytes của `demo/LazyTarget` và in `WATCHED_LOAD`.
3. `AFTER_LOAD_NOT_INIT` xuất hiện mà chưa thấy `LAZY_TARGET_INITIALIZED`: class đã được load nhưng chưa initialize.
4. `Class.forName(..., true, loader)` làm block static chạy rồi mới trả về, nên in `LAZY_TARGET_INITIALIZED` trước `AFTER_INITIALIZE`.
5. Không có output bytecode mới: transformer trả `null`. Thí nghiệm chứng minh việc quan sát thời điểm load, **không phải class đã bị instrument**.

Nếu một agent khác hoặc code bootstrap chủ động nạp `LazyTarget` trước khi watcher được đăng ký, dòng `WATCHED_LOAD` có thể không xuất hiện dù class sau đó được dùng. Đây không phải bằng chứng JVM sai; cần kiểm soát **class loading order** và thử trong process mới.

## 9. “Trước main” không đồng nghĩa “trước mọi class”

Đây là điểm lý thuyết quan trọng với agent:

```text
Trước khi premain được gọi:
  JVM đã có bootstrap/runtime support classes;
  JVM phải tìm/nạp class của agent;
  class dependencies của agent có thể load hoặc initialize.

Sau khi premain trả về:
  JVM chuyển tới application main;
  ứng dụng tiếp tục load classes khi cần.

Một số class definitions có thể xảy ra
trước/trong/sau premain.
```

**Không được suy:** `getAllLoadedClasses().length == 0` ở `premain`. Thực tế một JVM Java hoạt động có nhiều classes nền tảng đã load trước đó.

Nếu muốn xem danh sách loaded classes trong `premain`:

```java
// Fragment, thêm vào StartupAgent.premain.
Class<?>[] snapshot = inst.getAllLoadedClasses();
System.out.println("LOADED_CLASSES=" + snapshot.length);
```

Số `LOADED_CLASSES` là **dữ liệu thực nghiệm**, phụ thuộc JDK/JVM vendor, agents khác và thời điểm runtime; không thể viết stdout cố định mà áp dụng mọi máy. Bản snapshot không tự cập nhật và không phải danh sách mọi tệp `.class` trên classpath. Nếu cần theo dõi class loads tiếp theo, đăng ký transformer/hook theo capability.

### 9.1. Loading và initializing là hai mốc khác nhau

| Mốc | Ý nghĩa | Dấu hiệu trong ví dụ |
| --- | --- | --- |
| Transformer nhận class-file bytes | JVM đang định nghĩa/biến đổi class ở đường đi tương ứng | `WATCHED_LOAD=demo/LazyTarget` |
| Class đã load/link theo JVM | Đã có `Class<?>` cho type, tùy giai đoạn | Lệnh `Class.forName(...,false,...)` trả về |
| Class được initialize | `<clinit>` chạy khi cần, theo JLS/JVMS | `LAZY_TARGET_INITIALIZED` |
| Application `main` | Entry point ứng dụng được gọi | `LOAD_APP_MAIN` |
| `premain` | Startup agent entry point | `WATCHER_PREMAIN` |

**Không đánh đồng “JVM đã load class” với “constructor đã chạy”**. Constructor `<init>` chạy khi tạo object; static initialization `<clinit>` phục vụ khởi tạo class. Ở ví dụ không tạo instance `LazyTarget`, nhưng block static vẫn chạy khi `Class.forName(..., true, ...)`.

## 10. Phân biệt `premain`, `main` và `agentmain`

| Entry point | Khi nào chạy | Artifact/trigger |
| --- | --- | --- |
| `premain(String, Instrumentation)` | Startup agent **trước app main** | `-javaagent:agent.jar` với `Premain-Class` |
| `premain(String)` | Startup, overload dự phòng | Nếu không có overload nhận `Instrumentation` |
| `main(String[])` | Entry point ứng dụng | `java -cp ... MainClass` hoặc `java -jar app.jar` |
| `agentmain(String, Instrumentation)` | Java agent được nạp **sau startup** nếu VM hỗ trợ | Attach API hoặc mechanism tương đương với `Agent-Class` |
| `agentmain(String)` | Dynamic agent overload dự phòng | Khi không có overload nhận `Instrumentation` |
| `Agent_OnLoad` (native C) | Startup **native JVMTI agent** | `-agentlib`/`-agentpath`, không phải `-javaagent` |

Đừng thay `Premain-Class` bằng `Agent-Class` rồi dùng `-javaagent` và kỳ vọng JVM tự gọi `agentmain`. Ngược lại, đường dynamic attach thường không gọi `premain`.

### 10.1. Java 21+ và dynamic-agent loading

JEP 451 (JDK 21) đưa ra cảnh báo và chuẩn bị siết chặt **dynamic agent loading** vào JVM đang chạy. **Lab này dùng `-javaagent` lúc startup**, nên không cần quyền self-attach, không cần lấy PID, và không phải ví dụ của dynamic attach. Khi triển khai lên JDK mới, kiểm tra chính sách JVM/runtime cụ thể; không suy rằng mọi version có cùng default attach flags.

### 10.2. Một JAR có thể vừa chứa app vừa chứa agent?

Có thể đóng gói executable JAR với application/agent classes, nhưng cần phân biệt rõ các manifest attributes và cách chạy. Khi dùng **`-javaagent:agent.jar -jar app.jar`**, JVM đọc `Premain-Class` ở **agent.jar**, còn `Main-Class` để chạy ứng dụng từ **app.jar**. Hai JAR có thể là hai artifact riêng.

Java còn có cơ chế `Launcher-Agent-Class` trong executable JAR trên các implementations hỗ trợ, có entrypoint/lifecycle riêng (`agentmain` theo package spec), **không đồng nghĩa** `Premain-Class` của `-javaagent`. Để học sự khác biệt đơn giản nhất, lab dùng hai classpaths rõ và hai JAR agent tách biệt.

## 11. Các sai lầm thường gặp khi chạy từ terminal

### 11.1. Đặt `-javaagent` sai vị trí

Đúng:

```bash
java -javaagent:startup-agent.jar=demo \
    -cp app-classes demo.DemoApp
```

Sai ý định:

```bash
java -cp app-classes demo.DemoApp \
    -javaagent:startup-agent.jar=demo
```

Ở lệnh thứ hai, chuỗi `-javaagent:startup-agent.jar=demo` đứng **sau main class**, được truyền như **application argument**, không còn là JVM option. `DemoApp` có thể in nó trong `APP_ARGS`, nhưng `premain` sẽ **không được JVM gọi** từ flag đó. Đừng suy “có chuỗi -javaagent trên dòng lệnh” là agent đã chạy.

Tương tự:

```bash
java -jar app.jar -javaagent:startup-agent.jar
```

Các đối số sau `app.jar` do application nhận; muốn JVM nạp startup agent hãy đặt `-javaagent` **trước `-jar`**:

```bash
java -javaagent:startup-agent.jar -jar app.jar
```

### 11.2. Nhầm `-cp` và `-javaagent`

`-cp app-classes` khiến JVM tìm **application main class**, không tự tìm agent JAR. `-javaagent:startup-agent.jar` khiến JVM tìm agent JAR và manifest; nó không thay thế classpath application. Nếu muốn chạy `DemoApp`, vẫn phải chỉ định `-cp app-classes` hoặc cách launcher tương đương.

### 11.3. Nhầm `Premain-Class` với tên tệp Java

Trong manifest:

```text
Premain-Class: demo.StartupAgent
```

Không dùng:

```text
Premain-Class: StartupAgent.java
```

và không dùng:

```text
Premain-Class: demo/StartupAgent
```

Manifest yêu cầu tên lớp `demo.StartupAgent`, trong khi class file nằm ở JAR entry `demo/StartupAgent.class`. Khác biệt giữa **binary class name** và **JAR entry path** là nguồn lỗi rất phổ biến.

### 11.4. Thiếu newline ở manifest

Manifest có định dạng dòng riêng, gồm các thuộc tính `Name: Value`. Tệp không kết thúc đúng có thể khiến thuộc tính cuối không được nhận như mong đợi. Luôn bảo đảm `agent.mf`/`watching-agent.mf` có newline cuối và xem manifest đã đóng gói vào JAR. Không dựa vào tên file `agent.mf` để kết luận chắc chắn `Premain-Class` đã được nhúng.

### 11.5. Chữ ký `premain` không đúng

Lỗi ví dụ:

```java
// Sai: không phải chữ ký được java.lang.instrument chấp nhận.
private static void premain(String args) { }
public void premain(String args) { }
public static int premain(String args) { return 0; }
```

Đây là **fragments minh họa lỗi**, không phải một file Java độc lập. Entry point phải `public static void` và tham số phù hợp. Tên package của class trong manifest cũng phải khớp với bytecode đã build.

### 11.6. Không xử lý ngoại lệ trong `premain`

Nếu `premain` ném exception không được bắt, JVM có thể abort trước khi chạy ứng dụng. Trong production, startup initialization nên có error policy rõ: fail startup khi agent là yêu cầu bắt buộc, hoặc fail-open khi telemetry optional và vẫn an toàn. Nhưng **không được** nuốt lỗi rồi báo “agent active” nếu transformer không đăng ký thành công; cần health indicator và kiểm tra effectiveness.

## 12. Test matrix nhanh, không chỉ nhìn một log

| Test | Lệnh / thay đổi | Kỳ vọng |
| --- | --- | --- |
| A: Không agent | `java -cp app-classes demo.DemoApp` | Chỉ có `APP_MAIN`, `READY_AT_MAIN=false` |
| B: Một agent | `-javaagent:startup-agent.jar=phase=boot` | `AGENT_PREMAIN` xuất hiện trước `APP_MAIN`, flag true |
| C: Hai agents | Lặp hai `-javaagent` lần lượt `first`/`second` | Hai lần `premain` theo thứ tự, main một lần |
| D: Options/args | `=phase=boot` và cuối command `red blue` | `agentArgs` khác `main args` |
| E: Agent flag sau class | Đặt option sai chỗ | Không chạy premain, main nhận text làm arg |
| F: Transformer load | `-javaagent:watching-agent.jar` + `LoadApp` | `WATCHER_PREMAIN` rồi load hook khi `Class.forName` |
| G: Load chưa init | `Class.forName(...,false,...)` | `WATCHED_LOAD` trước `LAZY_TARGET_INITIALIZED` |
| H: Tắt watcher | Không có `-javaagent` | App vẫn load và initialize target, không có watcher logs |
| I: Thiếu manifest | Xóa/đổi `Premain-Class` trong test JAR mới | Startup agent fail; app main không được dùng làm thành công |
| J: Sai đường JAR | Trỏ đến file không tồn tại | Java launcher báo lỗi, không có lần main hợp lệ |

Với test A–H, dùng JVM process mới mỗi lần. Với negative tests I/J, **không thử trên hệ thống production** và không hardcode nội dung stderr vốn có thể thay theo JDK/vendor. Đánh giá exit status và sự xuất hiện/vắng mặt của logs có ý nghĩa.

### 12.1. Test hai lần với cùng JAR mà không gặp static state từ lần trước

Hai lệnh `java` riêng là hai JVM processes riêng: các static fields/system properties không tự tồn tại qua lần chạy mới. Nếu chạy hai tests trong cùng JVM (ví dụ JUnit test tạo multiple classloaders), không được tự coi đó là “start-up lại JVM”; `premain` không được JVM gọi lại chỉ vì bạn gọi một method khác.

## 13. Từ agent tối thiểu đến instrumentation thật

Sau khi `premain` chạy được, muốn đo/biến đổi code phải đăng ký transformer hoặc dùng các phương thức khác trên `Instrumentation`:

| API | Mục đích |
| --- | --- |
| `inst.addTransformer(transformer)` | Nhìn thấy/biến đổi class file qua callback cho những định nghĩa phù hợp |
| `inst.addTransformer(transformer, true)` | Đăng ký transformer có khả năng retransformation nếu VM/manifest cho phép |
| `inst.getAllLoadedClasses()` | Một snapshot các runtime classes đang load |
| `inst.getInitiatedClasses(loader)` | Classes mà loader có thể find theo tên theo cơ chế initiating |
| `inst.isRetransformClassesSupported()` | Kiểm tra JVM có hỗ trợ retransformation theo agent capability |
| `inst.isModifiableClass(clazz)` | Một class cụ thể có thể bị modify không |
| `inst.retransformClasses(clazz)` | Yêu cầu retransformation khi các điều kiện cho phép |
| `inst.redefineClasses(...)` | Yêu cầu redefine class definition hợp lệ |
| `inst.removeTransformer(transformer)` | Hủy đăng ký transformer; không có nghĩa hoàn tác bytes đã biến đổi |

**Không có lệnh nào trong Java app tự tạo `Instrumentation`**. JVM đưa handle vào `premain` hoặc `agentmain` theo contract. Việc có handle không có nghĩa class nào cũng modifiable; một số classes/VM không hỗ trợ retransform hay schema changes.

Ví dụ fragment lấy số class runtime:

```java
// Fragment trong premain, không phải chương trình độc lập.
int count = inst.getAllLoadedClasses().length;
System.out.println("CURRENT_LOADED_CLASSES=" + count);
```

Số đếm phụ thuộc runtime; **không hardcode output**. Và nếu agent đăng ký transformer sau khi một target đã được load thì transformer **không tự quay lại** nhận lần initial load của class ấy. Muốn xử lý classes đã load có thể cần `retransformClasses`/`redefineClasses` theo capability và modifiability, không phải cứ gọi `addTransformer` là tất cả classes cũ được transform.

### 13.1. Vì sao ở bài mở rộng `transform` trả `null`?

`ClassFileTransformer` contract: JVM cấp `byte[] classfileBuffer` làm input và transformation **không được sửa trực tiếp** mảng này. Nếu không thay đổi, trả `null`. Nếu biến đổi, trả **mảng `byte[]` mới** là class file hợp lệ. `WatchingAgent` chỉ quan sát `demo/LazyTarget` nên trả `null`, để chương trình ứng dụng tiếp tục hoàn toàn như cũ.

Trong production, một transformer có thể gọi bytecode library như ASM/Byte Buddy hoặc Class-File API trên JDK 24+, nhưng đó là bước kế tiếp. Một **agent tối thiểu** hoàn toàn hợp lệ mà không phụ thuộc thư viện bytecode.

## 14. Quan sát thứ tự khi chương trình có class initializer

Java có nhiều thời điểm khác nhau:

- **Agent class initialization**: JVM khởi tạo `StartupAgent` trước khi gọi phương thức `premain` của nó (theo quy tắc active use). Nếu có `static { ... }` trong agent class, log của block có thể xuất hiện **trước `AGENT_PREMAIN`**.
- **Application class loading**: JVM có thể nạp một class khi tìm/verifying/linking nó, không nhất thiết đã initialize.
- **Application class initialization**: `<clinit>` chạy khi các điều kiện initialization của Java được thỏa; `Class.forName(name,true,loader)` chủ động yêu cầu điều này.
- **Application `main`**: phương thức main được JVM gọi sau khi startup agent hoàn tất. Đừng suy mọi class của ứng dụng chắc chắn chưa được load trước mốc đó.

Bài mở rộng dùng `LazyTarget` để cho thấy **load hook trước class initializer**, không tự thay đổi behavior. Trong một hệ thống plugin/reflective framework, class có thể được load bởi nhiều classloaders: một chuỗi tên class **không đủ** xác định duy nhất runtime type; khi instrument target thực, cần xét defining loader identity.

### 14.1. Log thứ tự và clock time khác nhau

Hai dòng `AGENT_PREMAIN`/`APP_MAIN` chứng minh thứ tự theo cùng process, nhưng không cho biết latency startup chính xác. Nếu muốn đo “agent tăng bao nhiêu ms khởi động JVM”, cần thiết kế benchmark riêng:

1. Chạy nhiều JVM processes baseline và agent với cùng app/JDK.
2. Đo thời gian **launcher-to-ready** từ bên ngoài hoặc tiêu chí sẵn sàng tương đương, không chỉ duration của `premain`.
3. Báo median, p95/p99 và độ biến thiên; tránh lấy một lần run lạnh làm kết luận.
4. Kiểm soát class loading, JIT, disk page cache, container CPU và GC.
5. Phân biệt startup overhead, steady-state throughput/latency và chi phí exporter.
6. Không để agent ghi log dày đặc trong class-load callback rồi nghĩ đó là log “miễn phí”.

## 15. Lưu ý phiên bản Java và môi trường

- `-javaagent`/`java.lang.instrument` được hỗ trợ trên các Java SE/JDK implementations phù hợp từ lâu; lab chọn **Java 17+** để có API và lệnh launcher nhất quán.
- Không cần `--enable-preview` cho `premain` hoặc `Instrumentation` trong Java 17.
- Khi dùng `javac --release 17`, class files của lab có major version 61; JDK mới hơn tương thích có thể chạy chúng, nhưng phải kiểm tra dependencies và module/loader policy trên JVM mục tiêu.
- `java.instrument` là module JDK chuẩn chứa `Instrumentation`; ví dụ chạy classpath/unnamed module nên không đòi cấu hình module phức tạp.
- Không phải mọi JVM embedded/minimal runtime image đều hỗ trợ agent startup option; khi làm custom runtime image qua `jlink`, kiểm tra có module/capability phù hợp.
- Một số launchers nhận tham số bổ sung từ `JDK_JAVA_OPTIONS` hoặc `JAVA_TOOL_OPTIONS`; khi baseline có log agent không mong đợi, kiểm tra môi trường/JDK tooling thay vì chỉ nhìn command line bạn vừa gõ.
- `-javaagent` dành cho Java JAR. `-agentlib`/`-agentpath` dành cho native agent shared libraries có `Agent_OnLoad`, không phải cú pháp thay thế cho file JAR.
- Nếu một dependency của agent cần Java cao hơn runtime, có thể xảy ra `UnsupportedClassVersionError` trước application main. Biên dịch/bundle theo **JDK tối thiểu của host**, không chỉ JDK máy phát triển.

## 16. Bảo mật và độ tin cậy của startup agent

Agent chạy cùng JVM process và có quyền rất mạnh: có thể đọc trạng thái runtime, thay class definitions, mở module boundaries khi được phép và ảnh hưởng logic ứng dụng. Vì `premain` chạy **trước app main**, một lỗi initialization có thể làm cả ứng dụng không khởi động.

Khi triển khai thật:

- Chỉ nạp JAR agent đáng tin cậy; xác thực nguồn cung cấp, checksum/signatures, licenses và dependencies.
- Không cho user không đáng tin có quyền ghi đè đường `-javaagent` trước startup.
- Giữ `premain` ngắn, tránh network call đồng bộ không timeout, tránh deadlock hoặc cấp phát quá lớn lúc JVM đang khởi tạo.
- Tách telemetry export khỏi startup/business critical path, dùng bounded queues và failure isolation phù hợp.
- Không đưa secrets/passwords vào `agentArgs` nếu command line có thể bị lộ cho công cụ quản trị process; ưu tiên secret management phù hợp.
- Không instrument JDK/bootstrap/logger/agent helper classes tùy tiện, tránh reentrant loading/`StackOverflowError` và class loader visibility failures.
- Ghi rõ fail-open hay fail-fast policy: agent quan trọng với compliance khác agent tracing optional.
- Khi agent startup báo thành công nhưng không thu event, hãy kiểm tra **transformer đã đăng ký** và **target class có được quan sát**; log `premain` chỉ chứng minh điểm vào.
- Có đường rollback/tắt `-javaagent` trong launcher/container image khi agent mới gây regression.

## 17. Bảng lỗi và cách chẩn đoán

| Dấu hiệu | Nguyên nhân khả dĩ | Xử lý |
| --- | --- | --- |
| Không có `AGENT_PREMAIN`, app vẫn chạy | Không truyền `-javaagent` hoặc truyền sau main class | Kiểm tra vị trí launcher option |
| `Failed to find Premain-Class manifest attribute` | Manifest không có `Premain-Class` | Kiểm tra manifest trong JAR, build lại |
| `ClassNotFoundException` của agent | Sai package/name hoặc class entry không nằm đúng đường | `jar --list`, `Premain-Class` |
| Agent class có nhưng startup fail | Chữ ký `premain` sai hoặc method không `public static void` | Kiểm tra đúng overload |
| JVM abort trước `APP_MAIN` | Uncaught exception trong `premain`/agent init | Xem stack trace, fail policy |
| `NoClassDefFoundError` | Agent thiếu dependency hoặc wrong classloader visibility | Đóng gói dependency đúng, kiểm tra module |
| `UnsupportedClassVersionError` | Agent JAR compiled JDK quá cao | Build đúng `--release` và test JDK đích |
| `READY_AT_MAIN=false` dù có agent | Agent chưa đặt đúng property hoặc property bị thay | Kiểm tra code và JVM flags |
| `APP_ARGS` chứa `-javaagent:...` | JVM option đặt sau tên application main class | Di chuyển option trước main class |
| Chỉ thấy `APP_MAIN` khi watcher chạy | Wrong watcher JAR/manifest hoặc class đã được load trước | Kiểm tra class loading và `Premain-Class` |
| `WATCHED_LOAD` thiếu | Sai internal name; target load trước transformer; output filter | Kiểm tra `demo/LazyTarget` và thời điểm `Class.forName` |
| `LAZY_TARGET_INITIALIZED` xuất hiện trước `AFTER_LOAD_NOT_INIT` | Có code khác chủ động initialize target | Chạy JVM sạch, kiểm tra `Class.forName` initialize flag |
| Transformer gây `VerifyError` | Thay bytecode sai frames/stack | Trả `null` trong observer; dùng bytecode verifier khi biến đổi |
| Program startup chậm | Agent init đồng bộ nặng / network / scanning | Profiling startup, giới hạn work trong premain |
| Ghi log agent hai lần | Dùng hai `-javaagent` hoặc đăng ký transformer lặp | Kiểm tra launcher/config và idempotency |
| Agent options không đúng | Nhầm `agentArgs` với main args | Log chuỗi nhận trong `premain` và arrays main |
| App chạy mà không có transformer events | Agent chỉ in `premain` nhưng chưa `addTransformer` | Đăng ký transformer, test target class |
| JVM không hỗ trợ option/capability | Runtime image/module/VM policy khác | Xem JDK vendor/runtime configuration |

**Đừng suy output của JVM stderr là một chuỗi cố định**: văn bản lỗi và exit code cụ thể có thể khác giữa JDK/vendors. Đối với các ca chạy thành công, các dòng stdout của mã Java ở phần 5–8 là những giá trị đã giải thích từ source và điều kiện chạy sạch.

## 18. Checklist kiểm thử và tự đánh giá

- [ ] Đã tạo đúng hai source `StartupAgent.java` và `DemoApp.java` có package `demo`.
- [ ] `StartupAgent` có `public static void premain(String, Instrumentation)`.
- [ ] Manifest `agent.mf` có `Premain-Class: demo.StartupAgent` và newline cuối.
- [ ] `jar --list` xác nhận `META-INF/MANIFEST.MF` và `demo/StartupAgent.class`.
- [ ] Baseline không agent in `APP_MAIN`, `READY_AT_MAIN=false` và `APP_ARGS=[]`.
- [ ] Agent run in `AGENT_PREMAIN` và `INSTRUMENTATION_PRESENT=true` trước `APP_MAIN`.
- [ ] Main run có agent đọc được `READY_AT_MAIN=true`, arguments đúng.
- [ ] Agent `phase=boot` không bị trộn vào `APP_ARGS=[red, blue]`.
- [ ] Hai `-javaagent` thực sự gọi `premain` hai lần theo đúng thứ tự.
- [ ] App chạy bình thường nếu bỏ agent và không phụ thuộc trực tiếp class agent.
- [ ] Bài mở rộng watcher chỉ log `demo/LazyTarget`, không sửa `classfileBuffer`.
- [ ] `Class.forName(..., false, ...)` chưa chạy static initializer, còn `true` khiến initialize.
- [ ] Tên class trong transformer dùng internal form `demo/LazyTarget`.
- [ ] Không nhầm `premain` với `agentmain`, `Main-Class` hay native `Agent_OnLoad`.
- [ ] Không suy `premain` chạy trước mọi class loading của JVM.
- [ ] Không bịa loaded class count, thời gian khởi động hoặc các dòng stderr.
- [ ] Xử lý failure của agent startup: nếu bắt buộc thì fail-fast, nếu optional thì kiểm soát fail-open.
- [ ] Kiểm tra JVM/module policy, JDK baseline và nguồn gốc agent trước production.
- [ ] Khi cần instrument thực sự, có transformer verification và test behavior ngoài log `premain`.

## 19. Câu hỏi tự kiểm tra

1. **`premain` nằm ở class nào?**  
   Ở class mà thuộc tính manifest `Premain-Class` chỉ định, ví dụ `demo.StartupAgent`.

2. **Có cần một method `main` trong agent JAR không?**  
   Không. `-javaagent` dùng `Premain-Class` và `premain`; ứng dụng có `main` riêng.

3. **JVM gọi `premain` trước hay sau application `main`?**  
   Trước. `premain` phải kết thúc bình thường để startup đi tới `main`.

4. **`premain` có phải đoạn Java đầu tiên JVM từng chạy không?**  
   Không. JVM/platform/agent classes có thể load/initialize trước điểm đó.

5. **Chữ ký nào được JVM thử trước?**  
   `premain(String, Instrumentation)`. Nếu không có mới tìm `premain(String)`.

6. **`Instrumentation` có cần tự `new` không?**  
   Không. JVM cung cấp instance cho agent entry point.

7. **`AGENT_PREMAIN=phase=boot` và `APP_ARGS=[red, blue]` chứng minh gì?**  
   Chuỗi option sau dấu `=` của `-javaagent` khác các arguments đứng sau application main class.

8. **Nếu chạy `java -cp app-classes demo.DemoApp -javaagent:startup-agent.jar`, JVM có nạp agent không?**  
   Không theo cú pháp đó; chuỗi sau main class là application argument.

9. **Hai `-javaagent` cùng trỏ một JAR có được không?**  
   Có theo Java agent package specification. `premain` được gọi theo thứ tự flags.

10. **Nếu thiếu `Premain-Class` nhưng file `StartupAgent.class` vẫn có, JVM có tự tìm không?**  
    Không. Manifest xác định startup agent class.

11. **Vì sao `Class.forName(..., false, loader)` trong lab watcher làm class load nhưng chưa in `LAZY_TARGET_INITIALIZED`?**  
    Vì tham số `false` không yêu cầu chạy class initializer của target.

12. **`WatchingAgent` có thay bytecode không?**  
    Không; transformer chỉ log target class và trả `null`.

13. **`addTransformer` sau khi target load có tự biến đổi lại target không?**  
    Không. Cần đường retransform/redefine phù hợp nếu class đã load và VM/capability cho phép.

14. **`getAllLoadedClasses()` trong `premain` có trả số cố định trên mọi JVM?**  
    Không; số classes phụ thuộc runtime và timing, không liên quan một output cố định của bài.

15. **Nếu agent `premain` ném uncaught exception, application main có chắc chạy không?**  
    Không. Startup agent failure có thể làm JVM abort.

16. **`Can-Retransform-Classes` có bắt buộc cho agent chỉ in log không?**  
    Không. Lab không retransformation.

17. **`Agent-Class` và `Premain-Class` có đồng nghĩa không?**  
    Không. Chúng chỉ định hai cách nạp Java agent khác nhau: dynamic vs startup.

18. **Nếu watcher log `WATCHED_LOAD`, có chứng minh class đã initialize không?**  
    Không; class-loading hook và class initializer là hai mốc khác nhau.

19. **Để đo startup overhead, một log timestamp đã đủ chưa?**  
    Chưa. Cần nhiều JVM forks, thời gian launcher-to-ready, cùng config và biến thiên.

20. **Khi nào một thí nghiệm “premain trước main” được coi là đạt?**  
    Khi baseline không có agent logs, agent run in `premain` trước `main`, flag được main đọc như kỳ vọng, và command/JAR/manifest tương ứng đều được xác minh.

## 20. Tài liệu chính thức

1. **Oracle JDK 17 — `java.lang.instrument` package** (startup JAR, `Premain-Class`, `premain` overloads, thứ tự nhiều agents và lỗi startup): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
2. **Oracle JDK 17 — `Instrumentation`** (nhận từ `premain`, đăng ký transformer, get loaded classes, capability checks): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
3. **Oracle JDK 17 — `ClassFileTransformer`** (five-/six-argument callback, input bytes, `return null` khi không biến đổi): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. **Oracle JDK 17 — `java` launcher** (`-javaagent`, `-cp`, `-jar` và thứ tự application arguments): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
5. **Oracle JDK 17 — `jar` tool** (`--create`, `--manifest`, `--list` và `-C`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
6. **Oracle JDK 17 — `Class.forName(String,boolean,ClassLoader)`** (load vs initialize): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
7. **Oracle JDK 17 — JAR File Specification, manifest attributes:** https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
8. **OpenJDK JEP 451 — dynamic agent loading warnings** (khác với `-javaagent` startup): https://openjdk.org/jeps/451
9. **Java Virtual Machine Specification `5.5` — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html

**Kết luận:** Để chứng minh Java agent chạy trước chương trình, không cần ASM hay biến đổi bytecode: một **JAR có manifest `Premain-Class`, một method `public static void premain(String, Instrumentation)`, lệnh `java -javaagent:...` và app main độc lập** là đủ. So baseline với agent, kiểm tra thứ tự logs và dấu property tại main. Sau đó đăng ký một transformer chỉ quan sát class load để thấy rằng **`premain` trước `main`** là một mốc thời gian cụ thể, không phải lời khẳng định JVM chưa từng tải class nào trước agent.
