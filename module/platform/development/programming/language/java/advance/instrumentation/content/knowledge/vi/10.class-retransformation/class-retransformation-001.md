# Vì sao đăng ký transformer sau khi attach chưa thay đổi các lớp đã nạp

## 1. Hiện tượng: agent đã attach thành công nhưng lớp cũ vẫn như trước

Một ứng dụng Java đang chạy có class `com.example.PaymentService`. Sau khi ứng dụng đã nạp và sử dụng lớp này, công cụ quan sát dùng Attach API để tải Java agent vào JVM. Trong `agentmain`, agent gọi `instrumentation.addTransformer(transformer)`, in dòng “transformer registered” rồi trả về. Tuy nhiên, các lần gọi `PaymentService.pay()` tiếp theo vẫn chạy như trước.

**Đó là hành vi đúng theo hợp đồng Java Instrumentation**: đăng ký một transformer **không tự duyệt và biến đổi lại** toàn bộ các class đã được JVM định nghĩa trước thời điểm đăng ký.

Cần phân biệt ba sự kiện:

1. **Attach/load agent:** JVM đang chạy nhận agent và gọi `agentmain` (nếu hỗ trợ dynamic attach).
2. **Register transformer:** `addTransformer(...)` đưa callback vào chuỗi xử lý **những lần định nghĩa class về sau**, những lượt redefine, và những lượt retransform đủ điều kiện.
3. **Yêu cầu retransformation:** `retransformClasses(Class<?>...)` là lời gọi **riêng biệt**, yêu cầu JVM chạy lại chuỗi transform đối với những class đã nạp được chọn.

**Kết luận ngắn:** “agent được tải” khác “transformer được đăng ký”; cả hai lại khác “class đang chạy đã được retransform”; và “đã retransform” vẫn khác “hành vi ứng dụng thực sự đã thay đổi”.

## 2. Dòng thời gian để hiểu chính xác

~~~text
T0: java -cp app.jar com.example.App
    |
T1: JVM định nghĩa PaymentService (lần load đầu)
    |   Không có transformer của agent mới => agent chưa xử lý lớp này
    |
T2: ứng dụng dùng PaymentService.pay() nhiều lần
    |
T3: Attach tool -> VirtualMachine.loadAgent(agent.jar)
    |   -> JVM gọi Agent.agentmain(args, instrumentation)
    |
T4: agent gọi instrumentation.addTransformer(t, true)
    |   t đã đăng ký, nhưng JVM KHÔNG tự phát lại sự kiện T1
    |
T5: PaymentService.pay() chạy tiếp
    |   Lớp cũ vẫn có method bytes như trước nếu chưa được thay
    |
T6: agent tìm đúng Class<?> của PaymentService
    |   kiểm tra capability và modifiability
    |   -> instrumentation.retransformClasses(target)
    |
T7: JVM gọi t.transform(...) trên lượt retransform
    |   t có thể trả classfile bytes mới hợp lệ hoặc return null
    |
T8: nếu bytes hợp lệ được cài đặt, lời gọi method mới dùng phiên bản mới
        (các frame đang hoạt động có thể vẫn chạy bytecode cũ)
~~~

Phân biệt **đăng ký transformer ở T4** với **yêu cầu retransform ở T6** là trọng tâm của bài.

Với startup agent `-javaagent`, `premain` được gọi trước `main`, nên agent có thể đăng ký transformer *trước* khi các lớp nghiệp vụ quan trọng được nạp. Ngược lại, attach agent đến một JVM đang chạy thường gặp rất nhiều lớp đã load. Hợp đồng của `addTransformer` không đưa chúng qua callback chỉ vì agent vừa đăng ký.

Đặc biệt, **“lớp đã được nạp” không đồng nghĩa “đang có instance”**. Một class có thể được định nghĩa, khởi tạo, chạy static initializer và tạo object rồi; không thao tác nào trong số đó tự kích hoạt lại callback class definition sau khi đăng ký.

## 3. API nào thực sự làm gì?

| API / sự kiện | Vai trò | Có tự xử lý lại class đã nạp không? |
|---|---|---|
| `VirtualMachine.attach(pid)` | Attach công cụ tới một target JVM | Không |
| `VirtualMachine.loadAgent(path, args)` | Yêu cầu target JVM tải agent JAR và gọi `agentmain` | Không, trừ khi code agent chủ động làm |
| `agentmain(String, Instrumentation)` | Điểm vào Java agent được nạp động | Không; chỉ là callback khởi tạo của agent |
| `instrumentation.addTransformer(t)` | Đăng ký transformer không retransform-capable | **Không** |
| `instrumentation.addTransformer(t, true)` | Đăng ký transformer có thể nhận callback trong các lượt retransformation sau đó | **Không** |
| `instrumentation.getAllLoadedClasses()` | Liệt kê các class JVM đã load | Không, chỉ truy vấn |
| `instrumentation.isModifiableClass(c)` | Kiểm tra lớp `c` thuộc loại JVM cho phép sửa không | Không, chỉ truy vấn |
| `instrumentation.retransformClasses(c)` | **Yêu cầu** chạy lại quá trình biến đổi với class `c` | **Có**, nếu capability, target và kết quả hợp lệ |
| `instrumentation.redefineClasses(...)` | Yêu cầu thay classfile definition bằng bytes cung cấp | Có thể thay lớp cũ nhưng là cơ chế **khác**, yêu cầu capability khác |

`addTransformer(t)` tương đương `addTransformer(t, false)`. Nếu muốn chính `t` được gọi **lại** trong một lượt retransform, cần đăng ký `addTransformer(t, true)` **và** JVM phải thực sự hỗ trợ retransformation.

**Chi tiết dễ bỏ sót:** một transformer đăng ký `canRetransform=false` vẫn có thể tham gia khi JVM **định nghĩa class mới** hoặc **redefine class**. Trong một lượt `retransformClasses`, JVM **không gọi lại** transformer ấy; các kết quả trước của transformer không capable được **tái sử dụng theo đặc tả**. Việc có callback load-time không chứng minh có callback retransform.

## 4. “Vừa đăng ký” chỉ tạo ra quan hệ với sự kiện trong tương lai

`Instrumentation.addTransformer` là đăng ký callback vào pipeline class-file transformation, không phải lệnh quét lại heap, không phải yêu cầu JVM chạy lại `ClassLoader.defineClass` cho mọi class, và cũng không tự khởi tạo lại các đối tượng.

Các trường hợp sau có thể khiến `transform` được gọi sau khi bạn đăng ký:

- **Lần định nghĩa mới** của một class chưa được JVM định nghĩa bởi loader tương ứng.
- **Lượt redefine** được yêu cầu theo API `redefineClasses`.
- **Lượt retransform** được yêu cầu theo `retransformClasses`, **nếu** transformer được đăng ký với `canRetransform=true`.
- Trong các kịch bản có nhiều loaders, một lớp có cùng tên được một **loader khác** định nghĩa mới sau attach: đây là **định nghĩa class mới**, không phải tự retransform bản class cũ.

Ngược lại, những hoạt động **không tự gọi transform lại cho class cũ** gồm:

- Gọi method của class đã load thêm một lần.
- Tạo object mới của class đã định nghĩa.
- Đọc một static field.
- Gọi `Class.forName(...)` đối với một class đã được đúng loader định nghĩa (mà không tạo class definition mới).
- Gọi `getAllLoadedClasses()` rồi duyệt danh sách.
- Gọi `addTransformer(t, true)` một mình.

Trong môi trường nhiều class loaders, đừng kết luận “transformer đã nhận lại class cũ” chỉ từ log tên class. Hãy kiểm tra **loader identity** và `classBeingRedefined` để phân biệt một class definition mới của loader khác với retransformation của class đang xét.

## 5. Cần đủ capability: manifest, JVM, class và thay đổi bytecode

Để xử lý lớp đã nạp bằng retransformation, cần các lớp kiểm tra riêng:

### 5.1. Agent JAR phải khai báo nhu cầu

Với dynamic Java agent, manifest main section chứa:

~~~text
Manifest-Version: 1.0
Agent-Class: demo.ObserveAgent
Can-Retransform-Classes: true

~~~

`Agent-Class` là tên class có `public static void agentmain(...)`. `Can-Retransform-Classes: true` là lời khai báo cần retransformation; nếu thiếu thuộc tính này thì mặc định là `false`.

**Không nhầm:** `Premain-Class` phục vụ `-javaagent` trước `main`. Một JAR có thể khai báo cả hai entry points, nhưng cơ chế Attach dùng `Agent-Class` và `agentmain`.

### 5.2. JVM phải thực sự hỗ trợ

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Không dùng addTransformer(t, true) hoặc retransformClasses.
}
~~~

Capability của JVM có thể tùy implementation/cấu hình. **Khai báo `true` không đủ**: kết quả của `isRetransformClassesSupported()` mới phản ánh runtime agent hiện tại. Nếu trả `false`, `addTransformer(t, true)` có thể ném `UnsupportedOperationException`; một yêu cầu `retransformClasses` cũng không khả dụng.

Nếu agent chỉ cần class load events mới, vẫn có thể dùng `addTransformer(t)` làm fallback, nhưng phải báo rõ **không retroactive**. Nếu sản phẩm bắt buộc patch một class cũ để bảo đảm tính đúng, nên fail-fast hoặc disable riêng tính năng thay vì in log thành công giả.

### 5.3. Target class phải modifiable

~~~java
if (!inst.isModifiableClass(targetClass)) {
    // Bỏ qua target hoặc báo rõ nguyên nhân.
}
~~~

`isModifiableClass` là câu hỏi về **chính class object**, độc lập với capability toàn JVM. Primitive class và array class không modifiable; nhiều lớp đặc biệt của JVM cũng có thể không hỗ trợ sửa. Ngay cả với class modifiable, **phép sửa cụ thể** vẫn có thể vi phạm giới hạn bytecode/class schema.

### 5.4. Phải tìm đúng `Class<?>` đã nạp

`getAllLoadedClasses()` trả danh sách class objects đã load. Nên lọc không chỉ theo tên mà còn theo defining loader và nếu cần theo module/code source:

~~~java
Class<?> target = null;
for (Class<?> c : inst.getAllLoadedClasses()) {
    if ("com.example.PaymentService".equals(c.getName())
            && c.getClassLoader() == expectedLoader) {
        target = c;
        break;
    }
}
~~~

Đây là **mảnh code minh họa**: `expectedLoader` phải do agent xác định theo kiến trúc thực, chưa phải chương trình độc lập. Hai class cùng binary name do hai loader khác nhau định nghĩa là **hai runtime types khác nhau**. Gọi `Class.forName(...)` bừa bãi để tìm target có thể **tự tạo một class definition mới**, trái mục đích “lấy class vốn đã load”.

### 5.5. Classfile mới phải hợp lệ và đúng giới hạn

Khi retransform, JVM gọi các transformer capable; transformer có thể tạo bytes mới. Những thay đổi như đổi hierarchy, thêm/xóa member hoặc sửa cấu trúc không được hỗ trợ trên nhiều JVM theo hợp đồng retransformation. `retransformClasses` có thể thất bại vì `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError` hoặc các lỗi classfile khác.

**Đừng suy ra** từ “capability true, class modifiable true” rằng mọi thay đổi được áp dụng. Kiểm chứng đúng bytecode, stack map frames, loader/module visibility và kết quả thao tác là các bước riêng.

## 6. Ví dụ Java 17+ chạy được: attach hai lần để phân biệt đăng ký và retransform

Mục tiêu của ví dụ là chứng minh **callback không tự chạy lại trên class đã load**. Để không phụ thuộc thư viện sửa bytecode, transformer sẽ **chỉ in log rồi trả `null`**. Kết quả là:

- Lần attach đầu tiên với chế độ `register`: đăng ký transformer; `demo.Service` đã được nạp nên **không có callback `transform` cho nó** chỉ vì đăng ký.
- Lần attach thứ hai với `retransform`: agent chủ động gọi `retransformClasses(demo.Service.class)` qua đúng `Class<?>` lấy từ JVM. Callback sẽ in dấu hiệu đã chạy lại.
- Phương thức `Service.message()` vẫn trả `ORIGINAL`, bởi transformer **không biến đổi classfile**. Đây là điểm quan trọng để không nhầm “đã retransform” với “đã sửa hành vi”.

Ví dụ dùng **một target JVM** và **một AttachTool JVM** chạy riêng. Attach API có thể bị hạn chế bởi quyền OS, container, JDK variant hoặc chính sách bảo mật. Không sử dụng bài này để attach vào JVM ngoài quyền quản trị.

### 6.1. Cấu trúc tệp

~~~text
attach-retransform-demo/
├── AGENT.MF
├── src/
│   ├── app/demo/
│   │   ├── Service.java
│   │   └── Target.java
│   ├── agent/demo/
│   │   └── ObserveAgent.java
│   └── tool/demo/
│       └── AttachTool.java
└── out/                         # tạo trong bước build
    ├── app/
    ├── agent/
    ├── tool/
    └── observe-agent.jar
~~~

Có **bốn tệp Java** và **một manifest**. Không yêu cầu Maven/Gradle, ASM hoặc Byte Buddy. Chỉ cần full JDK 17+ có module `jdk.attach` và JVM đích cho phép nạp agent động.

### 6.2. Tệp `src/app/demo/Service.java`

~~~java
package demo;

public final class Service {
    private Service() {}

    public static String message() {
        return "ORIGINAL";
    }
}
~~~

Ta muốn class được nạp **trước khi attach**. Mã target dưới đây gọi `Service.message()` ngay lúc khởi động, vì vậy việc class đã load là quan sát được.

### 6.3. Tệp `src/app/demo/Target.java`

~~~java
package demo;

import java.io.BufferedReader;
import java.io.InputStreamReader;

public final class Target {
    private Target() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[target] pid=" + ProcessHandle.current().pid());
        System.out.println("[target] initial=" + Service.message());
        System.out.println("[target] enter tick or exit");

        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in));

        String command;
        while ((command = reader.readLine()) != null) {
            if ("exit".equals(command)) {
                break;
            }
            if ("tick".equals(command)) {
                System.out.println(
                        "[target] current=" + Service.message());
            } else {
                System.out.println("[target] unknown command");
            }
        }
        System.out.println("[target] finished");
    }
}
~~~

Target chờ input để bạn chủ động kiểm tra trạng thái **trước**, **sau register** và **sau retransform**. Không dùng `Thread.sleep` và không phụ thuộc race giữa hai tiến trình để suy ra trạng thái.

### 6.4. Tệp `src/agent/demo/ObserveAgent.java`

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ObserveAgent {
    private static ClassFileTransformer observer;

    private ObserveAgent() {}

    public static synchronized void agentmain(
            String mode, Instrumentation inst) throws Exception {

        if ("register".equals(mode)) {
            register(inst);
        } else if ("retransform".equals(mode)) {
            retransform(inst);
        } else {
            throw new IllegalArgumentException("Unknown mode: " + mode);
        }
    }

    private static void register(Instrumentation inst) {
        if (observer != null) {
            System.out.println("[agent] already registered");
            return;
        }

        boolean capable = inst.isRetransformClassesSupported();

        ClassFileTransformer t = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if ("demo/Service".equals(className)) {
                    System.out.println("[agent] transform demo.Service"
                            + " redefined="
                            + (classBeingRedefined != null));
                }

                return null; // Giữ nguyên bytes.
            }
        };

        // Nếu JVM không hỗ trợ retransform, vẫn có load-time callback.
        inst.addTransformer(t, capable);
        observer = t;

        Class<?> target = findLoadedService(inst);
        System.out.println("[agent] registered"
                + " canRetransform=" + capable
                + " alreadyLoaded=" + (target != null));
    }

    private static void retransform(Instrumentation inst)
            throws java.lang.instrument.UnmodifiableClassException {

        if (observer == null) {
            System.out.println("[agent] register first");
            return;
        }
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[agent] retransform unsupported");
            return;
        }

        Class<?> target = findLoadedService(inst);
        if (target == null) {
            System.out.println("[agent] Service not loaded");
            return;
        }
        if (!inst.isModifiableClass(target)) {
            System.out.println("[agent] Service not modifiable");
            return;
        }

        System.out.println("[agent] requesting retransform");
        inst.retransformClasses(target);
        System.out.println("[agent] retransform completed");
    }

    private static Class<?> findLoadedService(Instrumentation inst) {
        for (Class<?> c : inst.getAllLoadedClasses()) {
            if ("demo.Service".equals(c.getName())
                    && c.getClassLoader()
                       == ClassLoader.getSystemClassLoader()) {
                return c;
            }
        }
        return null;
    }
}
~~~

**Vì sao hai lần attach có thể dùng cùng state?** Trong kịch bản ví dụ, cùng một agent class `demo.ObserveAgent` được system loader định nghĩa ở target JVM, nên static field `observer` giữ reference transformer qua hai lần `agentmain` được gọi. Ta không đăng ký lại transformer ở lần thứ hai, tránh callback trùng.

**Ghi chú đúng về lớp đã nạp:** `getAllLoadedClasses()` chỉ liệt kê các `Class<?>` mà JVM đã biết, không tự động “replay” chúng qua transformer. `findLoadedService` dùng cả tên và loader identity. Điều kiện system loader phù hợp với ứng dụng chạy bằng `-cp out/app` của demo; ứng dụng dùng loader khác phải điều chỉnh điều kiện cho đúng.

**Ghi chú về callback:** `className` là tên nội bộ `demo/Service`, không phải `demo.Service`. `classBeingRedefined != null` giúp quan sát lượt retransform của class cũ. Với class definition mới thông thường, giá trị này bằng `null`.

### 6.5. Tệp `src/tool/demo/AttachTool.java`

~~~java
package demo;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachTool {
    private AttachTool() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: AttachTool <pid> <agent-jar> <mode>");
        }

        String pid = args[0];
        String agentJar = Path.of(args[1])
                .toAbsolutePath()
                .toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, args[2]);
            System.out.println(
                    "[tool] loadAgent complete: " + args[2]);
        } finally {
            vm.detach();
        }
    }
}
~~~

`VirtualMachine.attach(...)` kết nối tới JVM đích có quyền attach hợp lệ. `loadAgent(...)` gửi yêu cầu tải agent JAR **theo đường dẫn mà target JVM có thể truy cập**, và gọi `agentmain`; theo hợp đồng Java Attach API, `loadAgent` hoàn tất khi `agentmain` hoàn tất. `detach()` giải phóng phiên Attach của công cụ; **không** có nghĩa remove transformer đã đăng ký bên trong target.

Module `com.sun.tools.attach.VirtualMachine` thuộc **`jdk.attach`**, không nằm trong module `java.instrument`. Target JVM và AttachTool là **hai tiến trình khác nhau**: log `[agent]` xuất hiện ở console của target; log `[tool]` xuất hiện ở console của AttachTool.

### 6.6. Tệp manifest `AGENT.MF`

~~~text
Manifest-Version: 1.0
Agent-Class: demo.ObserveAgent
Can-Retransform-Classes: true

~~~

Tệp phải kết thúc bằng newline, và các thuộc tính trên phải ở **main section** của manifest. Thuộc tính `Can-Retransform-Classes: true` yêu cầu capability để dùng `retransformClasses`; JVM thực tế còn phải hỗ trợ. Không cần `Premain-Class` trong ví dụ này vì ta không dùng `-javaagent`.

### 6.7. Biên dịch và đóng gói

Mở terminal tại thư mục `attach-retransform-demo`, tạo ba thư mục output.

**Bash:**

~~~bash
mkdir -p out/app out/agent out/tool
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/app, out/agent, out/tool | Out-Null
~~~

Sau đó dùng JDK 17+:

~~~bash
javac --release 17 -d out/app src/app/demo/Service.java src/app/demo/Target.java

javac --release 17 -d out/agent src/agent/demo/ObserveAgent.java

javac --release 17 --add-modules jdk.attach -d out/tool src/tool/demo/AttachTool.java

jar cfm out/observe-agent.jar AGENT.MF -C out/agent .
~~~

`javac --release 17` tạo bytecode tương thích Java 17. Khi build AttachTool, `--add-modules jdk.attach` làm rõ module mà công cụ dùng; runtime cũng thêm module này khi chạy AttachTool. Các lệnh trên giả định full JDK có module Attach, không phải bản JRE/runtimes tối giản đã loại module này.

Có thể kiểm tra agent JAR đã có `META-INF/MANIFEST.MF` và `demo/ObserveAgent.class` bằng `jar tf out/observe-agent.jar`. Lưu ý: tệp `AGENT.MF` ở workspace không tự thành manifest JAR nếu bạn đóng gói sai lệnh; `jar cfm` với đối số manifest là bước quan trọng.

### 6.8. Terminal 1: chạy target JVM

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/app demo.Target
~~~

Ví dụ đầu ra (PID chỉ là một số minh họa, **lấy PID thật từ terminal của bạn**):

~~~text
[target] pid=12345
[target] initial=ORIGINAL
[target] enter tick or exit
~~~

`-XX:+EnableDynamicAgentLoading` là tùy chọn HotSpot để cho phép agent load động và tránh cảnh báo liên quan từ các bản JDK phát cảnh báo. Tùy implementation, policy, security settings và JDK version, dynamic agent loading có thể bị chặn. Trên HotSpot JDK từ 21, JEP 451 cảnh báo khi nạp agent động không có opt-in; **đừng mặc định tất cả JVM/vendor đều cho attach**. Thực hành trên JVM do bạn kiểm soát.

Quan trọng: `Service.message()` đã được gọi để in `initial=ORIGINAL`, vì vậy JVM đã nạp `demo.Service` **trước** khi bạn chạy AttachTool. Nếu target chưa in `initial=ORIGINAL`, chưa bắt đầu bước attach.

### 6.9. Terminal 2: lần attach thứ nhất chỉ đăng ký

Thay `12345` bằng PID thực của terminal 1:

~~~bash
java --add-modules jdk.attach -cp out/tool demo.AttachTool 12345 out/observe-agent.jar register
~~~

Terminal 2:

~~~text
[tool] loadAgent complete: register
~~~

Terminal 1 (agent in vào stdout của target):

~~~text
[agent] registered canRetransform=true alreadyLoaded=true
~~~

Đây là **kết quả dự kiến với HotSpot JDK hỗ trợ retransformation**. Nếu JVM trả `isRetransformClassesSupported() == false`, dòng sẽ ghi `canRetransform=false`; khi đó ví dụ vẫn đăng ký transformer load-time nhưng bước retransform tiếp theo phải được bỏ qua.

**Quan sát chủ chốt:** không có dòng `[agent] transform demo.Service ...` ở lần attach này. Đăng ký thành công **không** làm class đã nạp tự phát lại callback.

Quay về terminal 1, gõ:

~~~text
tick
~~~

Bạn sẽ thấy:

~~~text
[target] current=ORIGINAL
~~~

Nhấn Enter sau `tick` để ứng dụng đọc lệnh. Việc gọi thêm `Service.message()` không làm `transform` được gọi lại.

### 6.10. Terminal 2: lần attach thứ hai chủ động retransform

Vẫn dùng **cùng PID và cùng JAR**:

~~~bash
java --add-modules jdk.attach -cp out/tool demo.AttachTool 12345 out/observe-agent.jar retransform
~~~

Terminal 2:

~~~text
[tool] loadAgent complete: retransform
~~~

Terminal 1:

~~~text
[agent] requesting retransform
[agent] transform demo.Service redefined=true
[agent] retransform completed
~~~

Đây là dấu hiệu rõ ràng rằng **lượt retransform chủ động** đã gọi lại transformer. `classBeingRedefined != null` xác nhận callback đang xử lý class đã tồn tại. Vì demo trả `null`, JVM không nhận bytes sửa từ transformer này.

Tiếp tục gõ `tick` ở terminal 1:

~~~text
[target] current=ORIGINAL
~~~

**Đừng kết luận retransform lỗi:** trong demo, transformer chỉ quan sát chứ **không hề tạo bytecode khác**, nên hành vi không đổi là đúng. Để thay một method thực sự, transformer phải trả **mảng classfile bytes mới hợp lệ**, đồng thời đáp ứng giới hạn retransform. Đây là bước thêm ngoài mục tiêu thí nghiệm.

Cuối cùng, gõ `exit` trên terminal 1 để kết thúc:

~~~text
[target] finished
~~~

### 6.11. Output không cần có thứ tự liên tiến trình tuyệt đối

Hai terminal có stdout riêng, vì vậy không thể ép một thứ tự tổng thể cho tất cả dòng log chỉ bằng mắt nhìn. Hãy đối chiếu theo từng **mốc đồng bộ chủ động**:

1. `[target] initial=ORIGINAL` đã xuất hiện trước khi bắt đầu attach.
2. `[tool] loadAgent complete: register` nghĩa là lời gọi `agentmain("register", ...)` đã xong.
3. Ngay sau register, không có callback target cũ chỉ do đăng ký.
4. `[tool] loadAgent complete: retransform` nghĩa là `agentmain("retransform", ...)` đã hoàn tất; trong bước này có yêu cầu retransform cụ thể và callback target.
5. `tick` trả `ORIGINAL` sau cả hai bước, vì code biến đổi là observer `return null`.

Nếu dùng profiler/agent khác hoặc target chứa nhiều bản `demo.Service` do custom loaders, output có thể có thêm callback; ví dụ giả định target đơn giản không có tác nhân khác.

## 7. Vì sao đăng ký `canRetransform=true` vẫn không đủ?

Cờ `true` trong `addTransformer(t, true)` là khai báo **khả năng tham gia các lượt retransform sau này**. Nó không thể hiện:

- Class đích nào cần xử lý.
- Thời điểm muốn xử lý lại.
- JVM có cần dừng/đồng bộ hoạt động của class đang chạy không.
- Bytes mới nào nên được tạo ra.
- Có được phép thay cấu trúc class hoặc nạp helper không.
- Có phải truy cập mọi instance đang tồn tại không.

Đó là lý do API thiết kế riêng `retransformClasses(Class<?>... classes)` để người gọi nêu **tập class cụ thể**, không tự xử lý toàn bộ `getAllLoadedClasses()`.

Cũng không nên chạy retransform vô điều kiện trên **mọi** loaded class để “bù cho attach muộn”. Điều này có thể rất tốn tài nguyên, gặp core/JDK/hidden/array classes không sửa được, phá thứ tự phụ thuộc và khiến công cụ vô tình can thiệp lớp ngoài phạm vi. Hãy xác định filter theo tên, loader, module, code source và `isModifiableClass` **trước khi gọi** retransform.

## 8. Điều gì xảy ra trong `retransformClasses`?

Theo hợp đồng `Instrumentation`, một lượt retransform diễn ra theo chuỗi đại ý:

~~~text
Class<?> target đã nạp
       |
       v
JVM lấy dạng classfile bytes làm cơ sở cho retransformation
       |
       +-- transformer đăng ký canRetransform=false:
       |      KHÔNG callback lại, áp dụng lại kết quả trước theo quy tắc JVM
       |
       +-- transformer đăng ký canRetransform=true:
       |      JVM gọi transform(...) để có bytes mới hoặc null
       |
       v
JVM xác minh classfile/result và các giới hạn class schema
       |
       +-- thất bại -> exception, không có lớp nào trong lượt bị retransform
       |
       +-- thành công -> định nghĩa mới được cài đặt
                         (không tạo instance mới; không chạy lại <clinit>)
~~~

Một số chi tiết quan trọng:

- Dữ liệu classfile đầu vào của lượt retransform có thể không **byte-for-byte giống** classfile ban đầu trên đĩa: JVM có thể thay đổi thứ tự/định dạng constant pool hoặc bỏ thuộc tính không liên quan.
- Transformer không capable **không được gọi lại** ở lượt retransform; thay vào đó JVM tái áp dụng tác động trước đó theo quy tắc đặc tả.
- Transformer capable phải xử lý input được JVM cung cấp và nên tránh biến đổi lặp làm nhân đôi mã instrumentation (idempotency).
- `retransformClasses` không chạy lại static initializer và **không reset static fields**.
- Instance hiện có vẫn là instance của class đó; không tạo lại object.
- Nếu một method đang có active stack frame, frame hiện tại có thể **tiếp tục chạy bytecode cũ**; các lời gọi method mới dùng định nghĩa mới sau khi thành công.
- Khi một lượt trên nhóm class thất bại với exception, **không class nào trong lượt đó được retransform** theo contract.

Như vậy, retransform không phải “khởi động lại class” và cũng không phải “restart application”. Nếu cần đổi model object/field layout, class redefinition cũng không tùy ý làm được việc đó.

## 9. Muốn thấy hành vi thay đổi thật cần thêm bước gì?

Chỉ khi transformer trả một **byte[] classfile mới, hợp lệ** có phương thức bị biến đổi thì lượt retransformation mới có khả năng đổi hành vi. Pseudocode:

~~~text
transform(module, loader, className, beingRedefined, domain, bytes):
    if className != "demo/Service":
        return null

    if loader != expectedLoader:
        return null

    modified = bytecodeLibrary.transform(bytes)
        // Ví dụ chèn mã đo thời gian vào method cụ thể;
        // phải giữ classfile hợp lệ và đúng giới hạn retransform.

    if noChange:
        return null
    return modified  // byte[] mới, KHÔNG sửa trực tiếp input bytes
~~~

Đây là **pseudocode**, không phải chương trình Java biên dịch độc lập. Với Java 17, có thể dùng thư viện xử lý bytecode phù hợp như ASM/Byte Buddy. `java.lang.classfile` là Class-File API chuẩn từ **JDK 24**; không sử dụng API đó trong ví dụ Java 17 ở trên.

Nếu sửa class trên JVM production:

1. Chỉ chọn những class cần thay, theo **class identity thực tế**.
2. Bảo đảm transformer không instrument chính agent/helper của nó hoặc core JDK ngoài ý muốn.
3. Sinh class bytes mới với structure phù hợp; tránh thêm/xóa field/method, thay đổi superclass/interfaces và các thay đổi schema không được hỗ trợ.
4. Kiểm tra exception table, StackMapTable, frames, monitor và hành vi của method có try/finally/early return.
5. Xem helper bytecode chèn vào có visible từ loader/module của target không.
6. Chọn cách xử lý khi transformation lỗi: fail-open, skip target, disable feature hoặc fail-fast có chủ đích.
7. Chạy kiểm thử chức năng trước/sau trong cùng process, kể cả active stack frames và concurrency.

**Điểm cần nhớ:** log `"transform invoked"` chứng minh callback được gọi, không chứng minh transformer đã trả bytes khác; log `"retransform completed"` chứng minh API hoàn tất, không chứng minh chức năng/bytecode của ứng dụng đã đổi theo ý muốn.

## 10. Những sai lầm phổ biến

### 10.1. Chỉ gọi `addTransformer(t)` rồi đợi class cũ thay đổi

`addTransformer(t)` không retransform-capable và cũng không yêu cầu class nào chạy lại. Sửa bằng cách xác định nhu cầu: nếu chỉ muốn lớp **nạp sau này**, không cần retransform; nếu muốn lớp **đã nạp**, dùng capability + `addTransformer(t,true)` + `retransformClasses(target)`.

### 10.2. Đăng ký với `true` nhưng bỏ qua capability

Nếu `isRetransformClassesSupported() == false`, overload `addTransformer(t,true)` không có quyền được dùng. Luôn kiểm tra và báo đúng chế độ hiệu lực, không đoán từ manifest.

### 10.3. Gọi `retransformClasses` với lớp không modifiable

`getAllLoadedClasses()` có thể chứa array, primitive-like objects, hidden classes hoặc lớp đặc biệt. Chỉ đưa class thật sự cần thiết và `isModifiableClass(c)==true` vào tập yêu cầu. Lỗi `UnmodifiableClassException` cần được giải thích thay vì lặp vô hạn.

### 10.4. Chọn class bằng mỗi tên chuỗi

Hai loader có thể cùng định nghĩa `com.example.Service`. Cùng binary name không phải cùng runtime type. Cần class loader identity và module/source policy khi môi trường có nhiều loader.

### 10.5. Đăng ký một transformer nhiều lần

`addTransformer` có thể đăng ký cùng object nhiều lần nhưng đặc tả không khuyến khích, vì có thể khiến callback trùng và mã được instrument nhiều lần. Trên nhiều lần Attach, dùng state hoặc registry idempotent; cân nhắc `removeTransformer` khi tắt.

### 10.6. Nghĩ `return null` là retransform thất bại

`return null` trong `transform` nghĩa là callback không đổi class bytes. Lượt retransform vẫn có thể hoàn tất. Đó là kết quả đúng của observer trong demo.

### 10.7. Nghĩ `Class.forName` luôn trả class đang muốn sửa

`Class.forName` phụ thuộc loader được chọn và có thể tạo ra **lần định nghĩa class mới**. Dùng `getAllLoadedClasses()`, kiểm tra class identity/loader và modifiability; tránh nạp nhầm class trong quá trình điều tra.

### 10.8. Nhầm `redefineClasses` với `retransformClasses`

`redefineClasses` nhận `ClassDefinition` và classfile bytes do caller cung cấp, cần `Can-Redefine-Classes`/`isRedefineClassesSupported()`. `retransformClasses` chạy lại chuỗi transformer theo hợp đồng, cần `Can-Retransform-Classes`/`isRetransformClassesSupported()`. Hai capability này **khác nhau**.

### 10.9. Chỉ theo dõi log của AttachTool

`AttachTool` chạy ngoài target process; `agentmain` và `transform` chạy **trong target JVM**. Nếu không thấy log agent ở terminal công cụ, chưa chắc agent không hoạt động; kiểm tra đúng stdout/logging backend của target.

### 10.10. Giả định dynamic attach luôn được cho phép

JVM có thể cấm Attach API hoặc agent loading theo quyền OS, container, JVM options và security policy. Từ JDK 21, JEP 451 chuẩn bị thay đổi chính sách dynamic agent loading và có cảnh báo trừ khi opt-in phù hợp. Nếu không attach được, không thể chẩn đoán nguyên nhân bằng cách “thêm retransformClasses”: đó là hai bước khác nhau.

## 11. Bảng chẩn đoán theo dấu hiệu

| Dấu hiệu | Giải thích có khả năng | Kiểm tra tiếp |
|---|---|---|
| `loadAgent` ném `AgentLoadException` | JAR/path/manifest hoặc môi trường target không thể tải agent | `Agent-Class`, đường dẫn target, quyền attach |
| Agent in `agentmain started`, không thấy transform của target cũ | Không có sự kiện load mới cho class đã định nghĩa | Dùng `getAllLoadedClasses`, kiểm tra capability |
| `addTransformer(t,true)` ném `UnsupportedOperationException` | Capability retransformation không được hỗ trợ/cấp | `Can-Retransform-Classes`, `isRetransformClassesSupported` |
| Đã gọi `retransformClasses` nhưng callback của `t` không thấy | `t` có thể đăng ký `canRetransform=false` hoặc bị filter sai | Kiểm tra overload đăng ký, target identity, className |
| Callback có log, method vẫn như cũ | Transformer trả `null` hoặc bytes có hành vi như cũ | Ghi nhận bytecode output đúng phạm vi; test hành vi |
| Callback chạy hai lần ngoài ý muốn | Transformer có thể bị đăng ký lặp hoặc class nạp lại qua loader khác | Kiểm tra idempotent registration, loader |
| `UnmodifiableClassException` | Một target class không thể sửa | `isModifiableClass` trước yêu cầu |
| `ClassFormatError` / `VerifyError` | Classfile sau biến đổi không hợp lệ | Kiểm tra verifier/stack maps/classfile version |
| Vừa retransform nhưng luồng đang chạy chưa đổi hành vi | Active frame có thể tiếp tục dùng bytecode phiên bản cũ | Kiểm tra trên lời gọi mới sau lượt thành công |
| JVM từ chối dynamic agent loading | Cấu hình/permission/integrity policy | Kiểm tra lựa chọn startup agent hoặc opt-in chính thức |

## 12. Khi nào nên dùng `-javaagent` thay vì attach muộn?

Nếu yêu cầu của sản phẩm là **instrument mọi lần định nghĩa ban đầu của các lớp nghiệp vụ** và có thể sửa cách khởi chạy JVM, dùng:

~~~bash
java -javaagent:agent.jar -cp out/app demo.Target
~~~

với manifest `Premain-Class` thích hợp và method `premain`. Đăng ký transformer từ `premain` **trước `main`** sẽ giúp quan sát nhiều class nghiệp vụ ở lượt nạp đầu tiên. Tuy nhiên JVM/agent có thể đã nạp một số class trước `premain`; vì vậy startup agent cũng không có nghĩa toàn bộ core classes chưa từng được định nghĩa.

Attach API hữu ích cho profiling/debugging hoặc instrument một JVM đang chạy mà không restart, **khi được phép**. Trade-off là nhiều lớp đã nạp, nên phải có cách tìm class, yêu cầu retransform, xử lý capability, idempotency và rollback/redeploy an toàn.

| Nhu cầu | `-javaagent` / `premain` | Attach / `agentmain` |
|---|---|---|
| Quan sát class nghiệp vụ ngay từ đầu | Thường thuận lợi hơn | Có thể đã bỏ lỡ initial class load |
| Không restart ứng dụng | Không phù hợp nếu ứng dụng đã chạy | Phù hợp khi dynamic attach được phép |
| Lớp đã nạp cần đổi bytecode | Vẫn cần retransform/redefine nếu nó đã load trước đăng ký | Cần retransform/redefine có điều kiện |
| Chính sách bảo mật/integrity | Khai báo khi khởi động | Phải xét quyền attach và chính sách dynamic loading |
| Kiểm soát vận hành | Cấu hình ở startup | Có thêm bước điều phối target process và lifecycle agent |

## 13. Checklist tối thiểu cho agent attach + retransformation

- [ ] Target process là JVM mình quản trị, môi trường cho phép Attach API và dynamic agent loading.
- [ ] Agent JAR có `Agent-Class` và `public static void agentmain(String, Instrumentation)` đúng tên.
- [ ] Manifest khai báo `Can-Retransform-Classes: true` **nếu cần retransform**, không chỉ có `Premain-Class`.
- [ ] JVM trả `isRetransformClassesSupported()==true` trước khi dùng overload `addTransformer(t,true)`/`retransformClasses`.
- [ ] Transformer được đăng ký **một lần**, có filter tên/loader/module phù hợp và trạng thái ready.
- [ ] `getAllLoadedClasses()` đã xác định **đúng `Class<?>`** đang cần sửa, không chỉ một tên chuỗi.
- [ ] `isModifiableClass(target)==true`; loại trừ arrays/primitives/lớp không hỗ trợ.
- [ ] Gọi **tường minh** `retransformClasses(target)` khi muốn xử lý lớp cũ.
- [ ] Callback thực sự nhận `classBeingRedefined != null` ở target khi retransform.
- [ ] Nếu cần thay hành vi, transformer phải trả bytes **khác và hợp lệ**, không phải `null`.
- [ ] Test nhánh code và lỗi, active frames, loader/module visibility và độ trễ.
- [ ] Lưu log phân biệt **registered**, **retransform requested**, **callback invoked**, **applied**, **behavior verified**.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Agent attach thành công, `agentmain` gọi `addTransformer(t,true)`. Class đã load trước đó có tự nhận callback không?

> Không. `addTransformer` chỉ đăng ký callback. Muốn xử lý lại class đã nạp, phải chọn đúng `Class<?>` và gọi `retransformClasses` nếu runtime hỗ trợ.

**Câu 2.** Tại sao `Can-Retransform-Classes: true` chưa đủ?

> Đó là khai báo nhu cầu trong manifest. JVM hiện tại còn phải hỗ trợ retransformation; dùng `isRetransformClassesSupported()` để quyết định thao tác.

**Câu 3.** Khi nào `transform` được gọi lại trên một class đã nạp?

> Trong lượt retransform được yêu cầu (và transformer có `canRetransform=true`), hoặc lượt redefine theo hợp đồng API. Gọi method của object không tự sinh một lượt như vậy.

**Câu 4.** Vì sao phải kiểm tra cả loader khi tìm target?

> Một binary name có thể được nhiều class loaders định nghĩa thành các class runtime khác nhau. `retransformClasses` cần đối tượng `Class<?>` chính xác.

**Câu 5.** Demo in `[agent] transform demo.Service redefined=true` nhưng `Service.message()` vẫn trả `ORIGINAL`. Vì sao?

> Transformer chỉ quan sát và trả `null`. Callback đã được gọi và lượt retransform có thể hoàn tất, nhưng không có bytes sửa từ transformer đó để đổi method body.

**Câu 6.** Transformer đăng ký bằng `addTransformer(t)` có được JVM callback lại khi retransform không?

> Không. Đây là transformer `canRetransform=false`. Trong lượt retransform, JVM tái sử dụng kết quả biến đổi trước theo đặc tả thay vì gọi lại `t`.

**Câu 7.** `retransformClasses` có chạy lại static initializer, làm mới instances hoặc đổi toàn bộ active frames không?

> Không. Class initializer không tự chạy lại, instance sẵn có vẫn tồn tại và các active frames có thể tiếp tục chạy bytecode cũ; lời gọi mới dùng định nghĩa mới sau khi retransform thành công.

**Câu 8.** JVM không cho dynamic attach thì thêm một lời gọi `retransformClasses` trong agent có giúp attach thành công không?

> Không. Đó là vấn đề điều kiện **tải agent vào JVM**. Chỉ khi agent đã được tải và có `Instrumentation` mới xem xét retransformation.

## 15. Tài liệu chính thức

- Java SE 17, `java.lang.instrument`: cơ chế `premain`/`agentmain`, manifest `Agent-Class` và `Can-Retransform-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `Instrumentation`: `addTransformer`, `getAllLoadedClasses`, `isRetransformClassesSupported`, `isModifiableClass`, `retransformClasses`, `redefineClasses`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer`: callback lúc load/redefine/retransform, ``canRetransform` và hành vi `return null`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `VirtualMachine` (Attach API): `attach`, `loadAgent` và `detach`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- JEP 451 — **Prepare to Disallow the Dynamic Loading of Agents**: cảnh báo dynamic agent loading từ JDK 21 và cơ chế opt-in: https://openjdk.org/jeps/451
- Java SE 17, `UnmodifiableClassException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html
