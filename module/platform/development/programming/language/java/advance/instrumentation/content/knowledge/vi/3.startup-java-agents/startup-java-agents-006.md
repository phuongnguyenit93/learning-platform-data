# Khởi tạo cấu hình, helper và transformer trước khi ứng dụng chạy

## 1. Mục tiêu của một startup Java agent

Một **startup Java agent** là mã Java chạy trong JVM thông qua tùy chọn `-javaagent`. Điểm vào của nó là `premain`, được JVM gọi **trước khi gọi `main` của ứng dụng**. Khoảng thời gian này rất quan trọng: agent có cơ hội đọc cấu hình, chuẩn bị các thành phần hỗ trợ và đăng ký `ClassFileTransformer` trước khi những lớp nghiệp vụ cần quan sát bắt đầu được nạp.

Sau bài này, bạn cần hiểu và thực hành được:

- Thiết kế trình tự **đọc/kiểm tra cấu hình → khởi tạo helper → tạo và đăng ký transformer → trả quyền điều khiển cho ứng dụng**.
- Phân biệt **helper phục vụ agent** với **helper mà bytecode đã instrument sẽ gọi trong ứng dụng**; biết vì sao class loader/module visibility ảnh hưởng đến cách đóng gói helper.
- Hiểu thời điểm callback `transform` chạy, phạm vi mà `premain` bảo đảm và những lớp có thể đã được JVM nạp trước đó.
- Tạo và chạy một agent JAR thực sự trên **JDK 17+**, chứng minh transformer đã được đăng ký trước khi lớp nghiệp vụ được định nghĩa.
- Nhận diện lỗi về cấu hình, vòng lặp nạp lớp, helper không nhìn thấy được, thứ tự đăng ký, chất lượng bytecode và tác động lên startup.

Phạm vi ở đây là **agent được nạp lúc khởi động bằng `-javaagent`**. Một agent được tải sau bằng Attach API đi qua `agentmain` và phải xử lý riêng các lớp đã nạp; đó không phải luồng khởi tạo chính của bài này.

## 2. Vòng đời thực tế: “trước khi chạy ứng dụng” có nghĩa gì?

Với lệnh ví dụ:

~~~bash
java -javaagent:startup-agent.jar=target=demo.Work,verbose=true -cp app-classes demo.App
~~~

JVM đọc đường dẫn agent JAR và phần tùy chọn sau dấu `=`, tải lớp được nêu trong mục `Premain-Class` của manifest, rồi gọi `premain`. Lược đồ:

~~~text
Người chạy JVM
    │
    ├── -javaagent:startup-agent.jar=target=demo.Work,verbose=true
    │
    ▼
JVM khởi tạo runtime, tải agent JAR và các lớp cần thiết
    │
    ▼
StartupAgent.premain(agentArgs, Instrumentation)
    │
    ├── (1) parse và validate cấu hình
    ├── (2) chuẩn bị helper, trạng thái, dịch vụ tối thiểu
    ├── (3) tạo ClassFileTransformer với cấu hình đã hoàn tất
    ├── (4) instrumentation.addTransformer(transformer)
    └── (5) trả về từ premain
    │
    ▼
JVM gọi demo.App.main(...)
    │
    ├── ứng dụng yêu cầu tải một lớp mới
    └── transformer nhận class bytes trước khi class được định nghĩa
         ├── không phù hợp bộ lọc → return null
         └── phù hợp → quan sát hoặc trả byte[] mới hợp lệ
~~~

**Bảo đảm quan trọng:** `premain` được gọi trước khi `main` của ứng dụng được gọi; khi có nhiều tùy chọn `-javaagent`, các `premain` được gọi theo thứ tự agent trên dòng lệnh.

**Giới hạn quan trọng:** điều này **không có nghĩa** mọi lớp Java/JDK đều chưa được nạp tại thời điểm `premain` chạy. JVM phải khởi tạo runtime và tải một số lớp để chính agent có thể hoạt động. Agent cũng có thể vô tình nạp lớp mục tiêu quá sớm trong lúc cấu hình hoặc chuẩn bị helper. Đăng ký transformer về sau không quay ngược thời gian để bắt lại sự kiện định nghĩa class đã xảy ra.

### 2.1. Ba trách nhiệm, ba kiểu dữ liệu

| Thành phần | Dữ liệu nhận | Kết quả sau khi khởi tạo | Nguyên tắc |
|---|---|---|---|
| **Config** | Chuỗi `agentArgs`, thuộc tính hệ thống hoặc môi trường theo hợp đồng rõ ràng | Giá trị cấu hình đã kiểm tra, tốt nhất là bất biến | Fail sớm với tùy chọn sai; không chia sẻ trạng thái nửa khởi tạo |
| **Helper** | Config đã hợp lệ, dependency tối thiểu | Logger/buffer/registry/runtime bridge đã sẵn sàng | Biết helper sẽ được gọi từ agent hay từ bytecode của ứng dụng |
| **Transformer** | Config bất biến + trạng thái helper đã sẵn sàng | Đối tượng được `Instrumentation` đăng ký | Không giả định callback chỉ chạy một lần hoặc trên một luồng |

Một cách chia trách nhiệm dễ kiểm soát:

~~~text
premain
  |
  +-- AgentConfig.parse(...)           // tạo cấu hình bất biến
  +-- AgentHelper.initialize(config)   // tạo phần hỗ trợ trước
  +-- new StartupTransformer(config)   // giữ trạng thái cần thiết
  +-- inst.addTransformer(transformer) // từ đây có thể có callback
  +-- return                            // sau đó mới đến application main
~~~

Nếu đăng ký transformer **trước khi** cấu hình/helper sẵn sàng, callback có thể quan sát trạng thái chưa được thiết lập. Nếu việc khởi tạo lại chủ động tải lớp đích trước khi đăng ký, class đó có thể vượt qua transformer. Vì vậy thứ tự cần được thiết kế theo **phụ thuộc thực tế**, không chỉ theo cách sắp xếp phương thức cho đẹp mắt.

## 3. Cấu hình agent: xác định chính xác thứ gì cần can thiệp

`premain` thường có chữ ký:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

Manifest của agent JAR khai báo `Premain-Class`. JVM truyền **toàn bộ phần tùy chọn** sau `-javaagent:<jarpath>=` thành **một chuỗi `String`**, không tự diễn giải nó thành một bản đồ key/value. Agent phải thiết kế grammar và parse.

Ví dụ tự định nghĩa:

~~~text
-javaagent:startup-agent.jar=target=demo.Work,verbose=true
                               └──────────── agentArgs ──────────┘
~~~

Với cú pháp minh họa `key=value,key=value`, nên làm rõ:

- **Tên khóa hợp lệ:** chẳng hạn `target` và `verbose`; khóa lạ phải bị phát hiện.
- **Giá trị hợp lệ:** `target` là binary name Java như `demo.Work`, còn `verbose` chỉ nhận `true` hoặc `false`.
- **Mặc định:** nếu không truyền tùy chọn, mục tiêu mặc định nào được chọn; có hay không quan sát/log.
- **Ưu tiên:** nếu vừa có `agentArgs`, `-D...` và biến môi trường, nguồn nào thắng? Không âm thầm trộn cấu hình.
- **Lỗi:** một cấu hình không hợp lệ có khiến JVM dừng startup hay agent chọn chế độ bỏ qua theo chính sách? Lựa chọn này cần chủ ý.
- **Bí mật:** không in token, mật khẩu hoặc URL chứa thông tin xác thực ra stdout; nếu cần cấu hình nhạy cảm, ưu tiên cơ chế quản lý secret thích hợp.

**Nên hoàn tất parse/validate trước khi gọi `addTransformer`**. Dùng record hoặc đối tượng immutable để callback nhìn thấy tập giá trị thống nhất. Đừng lưu config từng trường trong các biến `static` rồi vừa nhận callback vừa cập nhật.

## 4. Helper: hai nghĩa cần tách bạch

### 4.1. Helper chạy bên trong agent

Đây là lớp agent gọi trực tiếp để ghi event, đệm metric, lọc package, gom trace hoặc hỗ trợ tạo bytecode. Ví dụ `AgentHelper.classSeen(...)` được **transformer gọi trong callback**. Nếu helper này chỉ được agent sử dụng, nó có thể được đóng gói cạnh agent entry point, không yêu cầu ứng dụng import helper.

Khi thiết kế helper:

1. Giới hạn thao tác trong `premain` vào những dependency thực sự cần thiết, tránh khởi tạo Spring context, gọi API ứng dụng hoặc mở kết nối mạng đồng bộ không cần thiết.
2. Khởi tạo state/queue/bộ lọc trước khi đăng ký callback; bảo đảm visibility giữa các luồng bằng `final`, `volatile` hoặc đồng bộ thích hợp.
3. Khi callback có thể xảy ra đồng thời, helper phải thread-safe; logging từng sự kiện lên console là kỹ thuật demo, không phải giải pháp throughput cao.
4. Không cho quá trình khởi tạo helper vô ý gọi `Class.forName` lên class mục tiêu, bởi class có thể đã được định nghĩa trước khi đăng ký transformer.
5. Đặt package của agent ngoài namespace ứng dụng cần instrument và tự loại trừ package của agent khỏi bộ lọc.

### 4.2. Helper được gọi từ bytecode đã instrument

Một tình huống khác: transformer **thêm lệnh gọi** như `TraceBridge.onEnter(...)` vào phương thức `demo.Work.run()`. Khi bytecode này được JVM thực thi, lớp `demo.Work` phải **tìm được `TraceBridge` thông qua cơ chế tải lớp và truy cập module của chính nó**.

Điểm cần nhớ:

- Agent JAR thường được thêm vào **system class loader search** cho startup agent; điều đó không bảo đảm mọi **child-first/custom class loader** của ứng dụng nhìn thấy helper.
- Đối với lớp được nạp qua nhiều loader, có thể phải đóng gói helper thành một JAR **riêng, rất nhỏ** và đưa vào bootstrap search bằng `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` hoặc cơ chế `Boot-Class-Path` của agent JAR khi thích hợp.
- Helper đưa vào bootstrap chỉ nên phụ thuộc những loại mà bootstrap class loader có thể định nghĩa. Không gắn nguyên agent/framework hoặc thư viện có nhiều dependency vào bootstrap một cách tùy tiện; xung đột class name và linkage lỗi rất khó gỡ.
- Java module system còn có yêu cầu về **readability, exports/opens**. Khả năng nạp được class chưa đồng nghĩa có quyền truy cập vào mọi member; chỉ điều chỉnh module bằng cơ chế hợp lệ khi thực sự cần.
- Thêm JAR vào search **không** tự sửa các class đã được nạp và cũng không bảo đảm giải quyết class đã load thất bại trước đó.

**Phân biệt bằng câu hỏi:** helper sẽ được gọi trong hàm `transform` hay được **phương thức ứng dụng sau khi sửa bytecode** gọi? Chỉ trường hợp thứ hai mới cần giải quyết đầy đủ visibility từ loader/module của lớp đích đến helper.

## 5. Transformer: đăng ký sớm, lọc hẹp, trả bytes đúng hợp đồng

`ClassFileTransformer` là interface trong `java.lang.instrument`. Trên Java 9+ có overload nhận cả `Module`:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Lúc JVM chuẩn bị định nghĩa một class, nó đưa vào callback tên nội bộ (ví dụ `demo/Work`), class loader, module, protection domain và **class-file bytes ban đầu của lượt biến đổi**. Ở lần nạp ban đầu, `classBeingRedefined` thường bằng `null`.

Các quy tắc nền tảng:

- `className` có thể `null`; phải viết bộ lọc chịu được `null`.
- Lọc bằng **tên nội bộ dùng dấu `/`**, không dùng trực tiếp `demo.Work` khi so sánh với `className`.
- `return null` có nghĩa **không thay đổi class bytes ở callback này**; đừng trả về bản sao chỉ để thể hiện “đã xử lý”.
- Nếu thay đổi thật, tạo **mảng byte mới** hợp lệ. **Không sửa trực tiếp `classfileBuffer`** mà JVM truyền vào.
- Đăng ký bằng `inst.addTransformer(transformer)` đủ cho class definition tiếp theo; `addTransformer(transformer, true)` chỉ nên dùng nếu cần retransform và JVM hỗ trợ capability đó.
- Callback là nơi nhạy cảm: tránh tải lại class đích, recursive transformation, I/O chậm, lock phức tạp và xử lý không có giới hạn.
- Khi có nhiều transformer, kết quả của transformer trước có thể là đầu vào của transformer sau. Trong một nhóm tương ứng, thứ tự đăng ký có ý nghĩa; native transformer và retransform-capable transformer còn có quy tắc thứ tự riêng.

Với **class đã nạp trước khi transformer được đăng ký**, việc đăng ký không tự động làm callback chạy lại. Chỉ cân nhắc `retransformClasses`/`redefineClasses` khi có nhu cầu, đúng capability và đúng giới hạn của JVM; đây là tác vụ khác với startup load-time instrumentation.

### “Đăng ký transformer” khác “đã sửa bytecode”

Trong ví dụ runnable dưới đây, transformer chỉ quan sát `demo.Work` và trả `null`. Chúng ta cố ý dùng phương pháp này để chứng minh **thứ tự khởi tạo** mà không cần thư viện sửa bytecode. Agent đã hoạt động thành công nhưng chương trình không bị thay đổi hành vi.

Muốn chèn timing/logging thực sự vào method body trên **JDK 17**, cần dùng công cụ xử lý bytecode tương thích như ASM hoặc Byte Buddy và kiểm tra classfile verifier, stack map frames, exception paths và visibility của helper. **Class-File API chuẩn `java.lang.classfile` có từ JDK 24**, nên không thể đem mã dùng API ấy chạy trên runtime JDK 17. Cơ chế `premain`/`Instrumentation`/`addTransformer` vẫn giữ nguyên; phần sinh bytecode hợp lệ thay đổi theo công cụ chọn.

## 6. Thực hành Java 17+: cấu hình → helper → transformer → ứng dụng

Bài thực hành dùng **chỉ JDK**, không yêu cầu Gradle, Maven hoặc thư viện ngoài. Mục tiêu `demo.Work` chỉ được gọi qua reflection **sau khi `main` bắt đầu**, giúp nhìn rõ thời điểm loader định nghĩa lớp.

### 6.1. Cấu trúc tệp

~~~text
startup-agent-demo/
├── MANIFEST.MF
├── src-agent/
│   └── example/agent/
│       ├── AgentConfig.java
│       ├── AgentHelper.java
│       ├── StartupTransformer.java
│       └── StartupAgent.java
└── src-app/
    └── demo/
        ├── App.java
        └── Work.java
~~~

**Tệp `src-agent/example/agent/AgentConfig.java`** — record bất biến, parse hai tùy chọn. Kiểm tra định dạng tên class trong ví dụ dùng quy tắc tên Java ASCII đơn giản:

~~~java
package example.agent;

import java.util.HashSet;
import java.util.Set;

record AgentConfig(String targetInternalName, boolean verbose) {

    static AgentConfig parse(String raw) {
        String target = "demo.Work";
        boolean verbose = false;
        Set<String> seen = new HashSet<>();

        if (raw != null && !raw.isBlank()) {
            for (String option : raw.split(",", -1)) {
                int equal = option.indexOf('=');
                if (equal <= 0 || equal == option.length() - 1) {
                    throw new IllegalArgumentException("Bad option: " + option);
                }

                String name = option.substring(0, equal).trim();
                String value = option.substring(equal + 1).trim();

                if (!seen.add(name)) {
                    throw new IllegalArgumentException("Duplicate option: " + name);
                }

                switch (name) {
                    case "target" -> {
                        if (!value.matches(
                                "[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)*")) {
                            throw new IllegalArgumentException("Bad target: " + value);
                        }
                        target = value;
                    }
                    case "verbose" -> {
                        if (!"true".equals(value) && !"false".equals(value)) {
                            throw new IllegalArgumentException("Bad verbose: " + value);
                        }
                        verbose = Boolean.parseBoolean(value);
                    }
                    default -> throw new IllegalArgumentException(
                            "Unknown option: " + name);
                }
            }
        }

        return new AgentConfig(target.replace('.', '/'), verbose);
    }
}
~~~

Record giữ trạng thái config cuối cùng. `targetInternalName` dùng dấu `/` vì tên do transformer nhận có dạng internal name, chẳng hạn `demo/Work`. Ví dụ không giải quyết mọi ký tự Unicode hợp lệ trong tên Java; phạm vi demo tập trung vào tên lớp ASCII thông thường.

**Tệp `src-agent/example/agent/AgentHelper.java`** — helper chỉ phục vụ agent. Biến `ready` volatile giúp luồng gọi callback thấy các giá trị đã được gán trước đó:

~~~java
package example.agent;

final class AgentHelper {
    private static volatile boolean ready;
    private static boolean verbose;

    private AgentHelper() {}

    static synchronized void initialize(AgentConfig config) {
        if (ready) {
            throw new IllegalStateException("Helper already initialized");
        }
        verbose = config.verbose();
        ready = true;
        System.out.println("[agent] helper ready");
    }

    static void classSeen(String internalName) {
        if (!ready) {
            throw new IllegalStateException("Helper not ready");
        }
        if (verbose) {
            System.out.println(
                    "[agent] observed " + internalName.replace('/', '.'));
        }
    }
}
~~~

Đây là helper **được gọi bởi transformer**, không phải helper được chèn vào bytecode của `demo.Work`. Lệnh `println` chỉ dùng để dạy cách quan sát thứ tự; thực tế cần tránh ghi log đồng bộ trên mọi sự kiện class load.

**Tệp `src-agent/example/agent/StartupTransformer.java`** — bộ lọc chính xác một lớp:

~~~java
package example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

final class StartupTransformer implements ClassFileTransformer {
    private final AgentConfig config;

    StartupTransformer(AgentConfig config) {
        this.config = config;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!config.targetInternalName().equals(className)) {
            return null;
        }

        AgentHelper.classSeen(className);
        return null; // Quan sát lớp; giữ nguyên bytecode.
    }
}
~~~

Vì `config.targetInternalName()` khác `null`, phép so sánh theo hướng này an toàn nếu `className` bằng `null`. Đối tượng `config` là record bất biến và field của transformer là `final`, phù hợp để các callback đọc đồng thời.

**Tệp `src-agent/example/agent/StartupAgent.java`** — entry point thực hiện đúng trình tự:

~~~java
package example.agent;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    private StartupAgent() {}

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[agent] premain begin");

        AgentConfig config = AgentConfig.parse(agentArgs);
        AgentHelper.initialize(config);

        StartupTransformer transformer = new StartupTransformer(config);
        inst.addTransformer(transformer); // Mặc định canRetransform = false.

        System.out.println("[agent] transformer registered for "
                + config.targetInternalName().replace('/', '.'));
    }
}
~~~

Đây là chỗ các phụ thuộc gặp nhau:

1. Chưa có callback riêng của agent trước khi có `addTransformer`.
2. `AgentConfig.parse` tạo một snapshot hợp lệ hoặc báo lỗi.
3. `AgentHelper.initialize` chuẩn bị state và xuất dòng xác nhận.
4. `new StartupTransformer(config)` nhận state đã hoàn tất.
5. `inst.addTransformer(transformer)` đăng ký callback trước khi `premain` trả về, sau đó `main` của ứng dụng mới được gọi.

**Tệp `src-app/demo/Work.java`** — lớp nghiệp vụ mục tiêu:

~~~java
package demo;

public final class Work implements Runnable {
    @Override
    public void run() {
        System.out.println("[app] Work.run");
    }
}
~~~

**Tệp `src-app/demo/App.java`** — tải lớp sau khi `main` đã in dòng đầu:

~~~java
package demo;

public final class App {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] main");
        Runnable work = (Runnable) Class.forName("demo.Work")
                .getDeclaredConstructor()
                .newInstance();
        work.run();
    }
}
~~~

Việc dùng `Class.forName("demo.Work")` ở đây giúp kiểm soát rõ điểm yêu cầu nạp `Work`. Ứng dụng không có tham chiếu kiểu `Work` trực tiếp tại thời điểm biên dịch của `App`; ví dụ được chạy khi không có agent hoặc công cụ khác chủ động nạp trước lớp này.

**Tệp `MANIFEST.MF`** — bắt buộc có `Premain-Class` trong main section. Sau dòng khai báo cần có newline kết thúc manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.StartupAgent

~~~

Không cần `Agent-Class` vì ví dụ không dùng dynamic attach. Không cần khai báo `Can-Retransform-Classes` vì chỉ quan sát lớp lúc nạp ban đầu. Một JAR agent có thể khai báo thêm thuộc tính khác cho mục đích thích hợp, nhưng không nên bật capability không dùng chỉ vì có sẵn.

### 6.2. Biên dịch và đóng gói

Chạy các lệnh từ thư mục `startup-agent-demo/`. Chuẩn bị hai thư mục output.

**Bash:**

~~~bash
mkdir -p out/agent out/app
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
~~~

Các lệnh `javac`/`jar`/`java` sau dùng được trên Bash hoặc PowerShell, giả sử JDK 17+ có trong `PATH`:

~~~bash
javac --release 17 -d out/agent src-agent/example/agent/AgentConfig.java src-agent/example/agent/AgentHelper.java src-agent/example/agent/StartupTransformer.java src-agent/example/agent/StartupAgent.java
javac --release 17 -d out/app src-app/demo/App.java src-app/demo/Work.java
jar cfm out/startup-agent.jar MANIFEST.MF -C out/agent .
~~~

Kiểm tra bằng `jar tf out/startup-agent.jar`: cần có `example/agent/StartupAgent.class` và các class helper/config/transformer tương ứng. Kiểm tra manifest đã đóng gói bằng `jar xf` trong một thư mục kiểm tra riêng nếu cần; phải thấy `Premain-Class: example.agent.StartupAgent` trong `META-INF/MANIFEST.MF`.

Không đóng gói toàn bộ application classes vào agent JAR trong ví dụ này. Agent JAR chứa các class phục vụ agent; ứng dụng nằm ở `out/app` và JVM được chỉ đường thông qua `-cp out/app`.

### 6.3. Chạy không có agent

~~~bash
java -cp out/app demo.App
~~~

Kết quả:

~~~text
[app] main
[app] Work.run
~~~

Ứng dụng tự chạy bình thường. Không có dòng `[agent]` vì không có JVM option tải agent.

### 6.4. Chạy với startup agent

~~~bash
java -javaagent:out/startup-agent.jar=target=demo.Work,verbose=true -cp out/app demo.App
~~~

Kết quả dự kiến của chính ví dụ:

~~~text
[agent] premain begin
[agent] helper ready
[agent] transformer registered for demo.Work
[app] main
[agent] observed demo.Work
[app] Work.run
~~~

Giải thích từng dòng:

- JVM gọi `premain`, nên dòng đầu tiên đến từ agent.
- Helper được khởi tạo xong trước khi transformer được đăng ký.
- Agent đăng ký thành công, sau đó `premain` trở về; `App.main` mới in `[app] main`.
- Khi `Class.forName` yêu cầu định nghĩa `demo.Work`, transformer lọc trúng tên `demo/Work` và helper in `[agent] observed demo.Work`.
- `transform` trả `null`, nên `Work.run` vẫn chạy đúng như bản gốc và in `[app] Work.run`.

**Lưu ý về output:** dòng log chỉ được kỳ vọng theo thứ tự trên với ví dụ đơn giản, không có agent khác chủ động nạp `demo.Work`, và runtime hỗ trợ `-javaagent` theo đặc tả. Trong ứng dụng thực, đừng suy ra rằng mọi class load của JVM sẽ xảy ra theo cùng thứ tự.

Thử tắt verbose:

~~~bash
java -javaagent:out/startup-agent.jar=target=demo.Work,verbose=false -cp out/app demo.App
~~~

Kết quả:

~~~text
[agent] premain begin
[agent] helper ready
[agent] transformer registered for demo.Work
[app] main
[app] Work.run
~~~

Transformer **vẫn đăng ký** và vẫn được gọi cho `demo.Work`; chỉ việc ghi log quan sát đã được tắt trong helper. Đừng coi “không thấy log” là bằng chứng transformer không chạy.

Thử nhập `verbose=maybe`:

~~~bash
java -javaagent:out/startup-agent.jar=target=demo.Work,verbose=maybe -cp out/app demo.App
~~~

`AgentConfig.parse` ném `IllegalArgumentException` trước khi có transformer. Đây là **chính sách fail-fast có chủ đích** của demo: JVM sẽ abort khi `premain` ném ngoại lệ chưa được xử lý; thông báo lỗi JVM cụ thể có thể khác giữa các phiên bản, không có stdout ứng dụng bình thường.

## 7. Tại sao không đảo ngược thứ tự init?

### Sai lầm A: đăng ký transformer trước khi helper sẵn sàng

~~~text
premain
  ├── addTransformer(transformer)
  ├── khởi tạo helper
  └── return
~~~

Một callback có thể xảy ra khi helper chưa ready, nhất là nếu ngay sau đăng ký có hoạt động định nghĩa class. Nếu callback cần cấu hình hoặc registry chưa có, có thể ghi dữ liệu sai, `NullPointerException` hoặc bỏ sự kiện. Trình tự được khuyến nghị:

~~~text
parse config → khởi tạo dependency thiết yếu → tạo transformer → addTransformer
~~~

Nếu có phần helper cực nặng không được phép block startup, hãy tách **state tối thiểu để callback an toàn** khỏi **dịch vụ có thể khởi tạo bất đồng bộ**. Transformer cần chính sách rõ khi dịch vụ chưa sẵn sàng (bỏ sự kiện, đệm bounded hoặc áp dụng chế độ an toàn), thay vì giả định thread nền sẽ khởi động kịp.

### Sai lầm B: trong `premain` tự nạp chính lớp muốn instrument

Ví dụ một agent đo `demo.Work` nhưng lại gọi:

~~~java
// Phản ví dụ: không dùng khi cần bắt lần định nghĩa đầu tiên của demo.Work.
Class.forName("demo.Work");
instrumentation.addTransformer(transformer);
~~~

Nếu `Class.forName` tìm thấy và định nghĩa `demo.Work` trước khi `addTransformer` được gọi, transformer đến quá muộn cho **lần nạp đầu tiên** của lớp đó. Hãy tránh khởi tạo ứng dụng hoặc scan/reflection mọi class trước khi đăng ký. Nếu cần xử lý class đã được nạp, đó là bài toán retransform riêng.

### Sai lầm C: helper trong bytecode không nằm trong phạm vi loader

~~~text
Agent system loader       ───> agent internals + AgentHelper
Custom app loader         ───> demo.Work
                                  |
                                  └── bytecode mới gọi AgentHelper ?
~~~

Dù transformer xây class bytes thành công, khi method chạy, JVM vẫn phải giải quyết tham chiếu helper từ bối cảnh của `demo.Work`. Loader có thể không thấy helper; lỗi thường là `NoClassDefFoundError`, `ClassNotFoundException` tại đường tải phụ thuộc, hoặc `IllegalAccessError` khi vướng quyền truy cập.

Giải pháp nằm ở kiến trúc class loading: tránh reference helper khi không cần, hoặc bố trí một **API helper tối thiểu, ổn định** để các loader/module đích truy cập được. Với bootstrap append, dùng helper JAR riêng và kiểm tra tác động của package/class name trùng nhau. Trong ví dụ runnable ở trên, `Work` **không gọi helper**, nên vấn đề visibility này chưa phát sinh.

### Sai lầm D: dùng transformer để khởi tạo cả ứng dụng

Transformer phải xử lý class bytes một cách ngắn gọn. Không nên từ callback bắt đầu context của framework, đọc cả database, init HTTP client phức tạp hoặc đồng bộ chờ ứng dụng “ready”. Callback có thể chạy vào thời điểm hệ sinh thái ứng dụng **chưa có trạng thái vận hành hợp lệ** và trên chính luồng đang định nghĩa class; tác vụ blocking/reentrant gây deadlock hoặc class loading cycle.

## 8. Mở rộng từ “quan sát” sang biến đổi bytecode thật

Ví dụ trước chỉ dùng `return null`. Với mục tiêu instrument `Work.run`, một pipeline đúng về mặt trách nhiệm thường là:

~~~text
StartupAgent.premain
   ├── parse config: class/method filter, mode, sampling
   ├── chuẩn bị helper được gọi từ bytecode (nếu cần)
   ├── chuẩn bị engine ASM/Byte Buddy/Class-File API thích hợp JDK
   └── addTransformer
          └── khi JVM định nghĩa class:
                1. lọc theo className + loader + module
                2. nếu không khớp: return null
                3. phân tích classfileBuffer
                4. thêm mã vào phương thức được chọn
                5. tính toán lại frame/max stack khi cần
                6. trả byte[] mới, hợp lệ với JVM verifier
                7. JVM định nghĩa lớp từ kết quả của chuỗi transformer
~~~

**Phân chia trách nhiệm khi thiết kế:**

| Vấn đề | Đặt ở đâu | Vì sao |
|---|---|---|
| Quyết định class/method nào được chọn | Config + filter của transformer | Dễ điều chỉnh và giới hạn phạm vi |
| Mã hóa lại method và tạo classfile mới | Bộ xử lý bytecode | Transformer chỉ là điểm tích hợp với JVM |
| Truyền event nhanh ra queue/buffer | Helper của agent / helper trong target (nếu bytecode gọi trực tiếp) | Tránh network/console I/O ở luồng nóng |
| Đăng ký callback class definition | `Instrumentation.addTransformer` trong `premain` | Bắt các định nghĩa class sau thời điểm đăng ký |
| Quan sát lớp đã nạp | Capability và thao tác retransform/redefine riêng | `addTransformer` không hồi tố |

Mọi biến đổi thực tế cần giữ bytecode hợp lệ với phiên bản classfile, kể cả exception table và stack map frames. Cần kiểm tra các lớp có synthetic/bridge methods, method body đặc biệt, class loader tùy chỉnh và module boundaries trước khi đưa lên production. Tên lớp có thể trùng giữa các loader; việc chỉ dùng một chuỗi tên đơn thuần đôi khi không đủ để xác định **đúng loại** cần sửa.

## 9. Quy tắc vận hành đáng tin cậy

### 9.1. Định nghĩa chính sách lỗi cho từng giai đoạn

| Giai đoạn | Ví dụ lỗi | Hành động hợp lý |
|---|---|---|
| Parse config | Khóa lạ, kiểu dữ liệu sai | Fail-fast trước khi đăng ký (agent bắt buộc); hoặc tắt agent theo chính sách vận hành |
| Prepare helper | Không tạo được buffer/logging backend | Không để callback dùng state nửa khởi tạo; quyết định fail-open/fail-fast minh bạch |
| Register transformer | JVM thiếu capability nếu yêu cầu retransform | Kiểm tra `isRetransformClassesSupported()` nếu thực sự cần; trường hợp load-time cơ bản dùng overload mặc định |
| Transform class | Bytes không đúng định dạng hoặc tool gặp classfile lạ | Lập báo cáo và bỏ qua lớp nếu an toàn; không cố áp dụng bytes hỏng |
| Runtime helper call | Helper không visible, sai quyền module | Kiểm thử loader/module trước khi chạy trên ứng dụng thật |

Theo đặc tả, ngoại lệ không được bắt trong `ClassFileTransformer.transform` thường được JVM xử lý tương đương với việc callback trả `null`, và các transformer khác vẫn có thể được gọi. Điều này **không có nghĩa** một lỗi của transformer là vô hại: biến đổi thiếu một phần có thể khiến hành vi sai, và class bytes hợp lệ nhưng logic sai vẫn có thể lọt qua verifier. Chọn chế độ lỗi tùy mức độ thiết yếu của instrumentation, ghi log với giới hạn, giữ bằng chứng để chẩn đoán.

### 9.2. Tránh các tác động khó lường lên startup

- Đọc và validate cấu hình đúng một lần; không gọi hệ thống bên ngoài chỉ để quyết định một flag đơn giản.
- Đừng instrument package của agent, bytecode engine, runtime logging hoặc core JDK nếu không có lý do và kiểm thử rất rõ ràng.
- Không khởi tạo application singleton, bean, transaction, connection pool hoặc business service ngay trong `premain`.
- Callback class load có thể chạy đồng thời; dùng trạng thái immutable, API thread-safe và tránh state toàn cục thay đổi không đồng bộ.
- Cần đo **thời gian khởi động có agent** và **không agent**. Quét mọi class hoặc in log trong mỗi callback có thể chậm đáng kể.
- Dùng ngưỡng/queue bounded khi thu event; không để lớp đích phụ thuộc sự sẵn sàng của collector bên ngoài.
- Cùng một JVM có thể nhận nhiều startup agents; thiết kế idempotency của hook và xử lý xung đột transformers nếu có.
- Đảm bảo agent và bytecode engine tương thích với bản JDK thực tế (classfile major version, module behavior, instrumentation capabilities); `--release 17` chỉ ràng buộc **mã được biên dịch**, không chứng minh mọi thư viện ngoài cũng tương thích.

### 9.3. Khi nào cần thêm `Boot-Class-Path` hoặc `appendToBootstrapClassLoaderSearch`?

**Không cần** trong demo vì `AgentHelper` chỉ được gọi từ chính agent. Có thể cần khi bytecode được thêm vào lớp do bootstrap/custom loader định nghĩa và **bytecode sẽ gọi helper**.

Trước khi chọn cách tiếp cận đó, xác định ít nhất:

1. Lớp đích do loader nào định nghĩa và loader đó có thể nhìn thấy helper ở đâu?
2. Helper có phụ thuộc lớp nào không do bootstrap loader thấy được?
3. Thêm JAR vào bootstrap search có gây trùng package hoặc class name không?
4. Java module của lớp đích có quyền đọc/truy cập API helper hay không?
5. Nếu instrumentation bị tắt hoặc thất bại, ứng dụng có tiếp tục chạy được không?

API `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` dùng một `JarFile` chứa **chỉ lớp hỗ trợ thích hợp**, và cần gọi trước khi lớp đích cần resolve helper. Không sao chép nguyên JAR agent vào bootstrap theo thói quen.

## 10. Checklist để tự kiểm thử

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Agent JAR có `META-INF/MANIFEST.MF` khai báo `Premain-Class` chính xác | JVM tìm được `StartupAgent.premain` |
| Chạy không có `-javaagent` | Chỉ có output của ứng dụng |
| Chạy có `-javaagent` | Log `premain` và helper xuất hiện trước `[app] main` |
| `target=demo.Work,verbose=true` | Có đúng một log quan sát `demo.Work` trong kịch bản demo |
| `verbose=false` | Không có log quan sát, ứng dụng vẫn hoạt động |
| `verbose=maybe` | Cấu hình lỗi bị phát hiện trước khi transformer được đăng ký |
| Thử `target=demo.Other` (lớp không được nạp trong demo) | Không có log `observed demo.Work` |
| Không có bytecode rewrite | Output `[app] Work.run` vẫn như ứng dụng gốc |
| Review package và loader của target production | Không tự instrument agent/helper và không phụ thuộc helper không nhìn thấy |
| Đo startup overhead và khả năng fail-open/fail-fast | Chính sách phù hợp yêu cầu của ứng dụng |

**Phân biệt bằng chứng:** log `[agent] transformer registered` chứng minh lời gọi đăng ký đã hoàn tất; log `[agent] observed demo.Work` chứng minh callback **đã chạy cho lớp mục tiêu**; còn muốn chứng minh **bytecode đã thực sự bị thay đổi** thì phải dùng một transformer trả bytes mới và kiểm thử hành vi hoặc inspect classfile tương ứng. Không dùng một dấu hiệu để khẳng định thay dấu hiệu khác.

## 11. Câu hỏi ôn tập và đáp án

**Câu 1.** Vì sao phải parse config trước `addTransformer`?

> Vì callback có thể chạy sau khi transformer được đăng ký, từ nhiều luồng. Một record config bất biến đã hợp lệ giúp callback nhìn thấy cùng một trạng thái; config lỗi được phát hiện ngay thay vì để sự kiện đi qua nửa cấu hình.

**Câu 2.** `premain` chạy trước `main` thì có bảo đảm transformer nhận được tất cả các class của JVM không?

> Không. JVM đã khởi tạo và tải một số class phục vụ runtime/agent trước `premain`; chính agent cũng có thể tải thêm class trước khi đăng ký. Transformer chỉ theo dõi những lần định nghĩa class xảy ra sau đăng ký và các thao tác redefine/retransform phù hợp.

**Câu 3.** Helper được transformer gọi có cần đặt ở bootstrap classpath không?

> Không mặc nhiên. Nếu helper chỉ được mã agent gọi, agent có thể đóng gói nó cạnh các class khác. Nhu cầu thêm vào bootstrap thường xuất hiện khi **bytecode được chèn vào lớp của loader khác** phải gọi helper.

**Câu 4.** Tại sao transformer demo luôn `return null` nhưng vẫn hữu ích?

> Nó chứng minh đúng điểm vào, parsing, thứ tự helper initialization, registration và class-definition callback, trong khi giữ nguyên class bytes. Phần instrument bytecode thật có thể thay vào sau khi luồng startup đã được kiểm chứng.

**Câu 5.** Một lớp `demo.Work` đã bị agent tự tải trước khi `addTransformer`. Có thể sửa sai chỉ bằng gọi `addTransformer` lần nữa không?

> Không. Đăng ký thêm không tạo lại sự kiện class definition đã kết thúc. Nếu cần thay class đã nạp, phải xét khả năng retransform/redefine và giới hạn cấu trúc cho phép; tốt nhất vẫn tránh tự tải mục tiêu quá sớm.

**Câu 6.** Tại sao không nên ghi log mỗi class load hoặc gọi HTTP đồng bộ từ `transform`?

> Callback có thể nằm trên đường nạp lớp của ứng dụng, chạy rất thường xuyên và đồng thời. I/O/lock hoặc dependency mới có thể tăng startup latency, gây recursion, contention hoặc deadlock; sử dụng filter hẹp và helper có buffering giới hạn.

## 12. Tài liệu chính thức

- Java SE 17, `java.lang.instrument`: manifest, `premain`, `-javaagent` và thứ tự startup agents: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- `Instrumentation`, `addTransformer` và bootstrap/system class loader search: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- `ClassFileTransformer`, callback, thứ tự, bytecode hợp lệ và `return null`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `java.lang.Module` và module access: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JEP 484 (Class-File API chính thức từ JDK 24; dùng khi runtime phù hợp): https://openjdk.org/jeps/484
