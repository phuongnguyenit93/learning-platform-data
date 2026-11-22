# Phân biệt attach thành công, nạp agent thành công và biến đổi lớp thành công

Khi gắn Java agent vào một JVM đang chạy, ba sự kiện **attach thành công**, **nạp agent thành công** và **biến đổi lớp thành công** diễn ra ở ba tầng khác nhau. Chúng có quan hệ trước–sau nhưng **không tương đương**. Một công cụ có thể kết nối được tới JVM mà không nạp được agent; agent có thể được JVM gọi và trả về bình thường mà không biến đổi một lớp nào; transformer có thể được gọi và trả về bytecode nhưng JVM chưa chắc chấp nhận hoặc ứng dụng chưa chắc biểu hiện hành vi dự kiến.

Bài học tập trung vào cơ chế **dynamic attach** của Java (module **jdk.attach**) và Java agent (module **java.instrument**), cách quan sát từng mốc và cách thiết kế một phép thử có thể phân biệt chính xác nguyên nhân lỗi.

## 1. Ba mức thành công cần định nghĩa riêng

Trong bài này:

- **Mức A — ATTACH_OK:** JVM của công cụ gọi thành công **VirtualMachine.attach(id)** và nhận một handle **VirtualMachine** tới *target JVM*. Điều này chứng minh kết nối attach đã được thiết lập theo provider hiện tại. Chưa chứng minh agent JAR nào đã được nạp.
- **Mức B — AGENT_LOAD_OK:** sau khi đã attach, công cụ gọi **vm.loadAgent(path, options)** và lời gọi hoàn thành bình thường. Với agent Java, target JVM nhận đường dẫn JAR, tìm **Agent-Class** trong manifest và gọi **agentmain**. Điều này không tự chứng minh agent đã bật đúng mọi tính năng: **agentmain** có thể tự bỏ qua một lỗi nghiệp vụ rồi trả về, hoặc chỉ đăng ký transformer mà chưa có lớp nào đi qua.
- **Mức C — TRANSFORMATION_OK:** lớp mục tiêu đã được xác định đúng (tên, defining class loader, module), bytecode thay thế hợp lệ đã được áp dụng thông qua load/redefine/retransform phù hợp, và có **bằng chứng độc lập rằng định nghĩa/hành vi được mong đợi đã có hiệu lực**. Với lớp đã load, một phép **retransformClasses** hoàn thành không lỗi cùng với một phép thử hành vi sau retransform là bằng chứng mạnh hơn chỉ nhìn log callback.

~~~text
JVM công cụ (controller)                 JVM mục tiêu (target)
        │                                       │
        ├── VirtualMachine.attach(pid) ────────>│ Attach provider kiểm tra/kết nối
        │<────── handle VirtualMachine ─────────┤
        │         [A: ATTACH_OK]                │
        │                                       │
        ├── vm.loadAgent(agent.jar, "mode") ───>│ Đọc JAR + manifest Agent-Class
        │                                       ├── agentmain(options, inst)
        │                                       │      │
        │                                       │      ├── có thể chỉ log/return
        │                                       │      └── hoặc addTransformer(...)
        │<────── loadAgent hoàn tất ────────────┤
        │         [B: AGENT_LOAD_OK]            │
        │                                       │
        │                                       ├── xác định đúng lớp mục tiêu
        │                                       ├── transformer tạo bytes thay thế
        │                                       ├── JVM kiểm tra/cài định nghĩa
        │                                       └── hành vi được kiểm chứng
        │                                              [C: TRANSFORMATION_OK]
        │
        └── vm.detach() (đóng kênh quản lý;
            không phải lệnh gỡ agent khỏi target)
~~~

**Suy luận đúng:** C thường cần B, B thường cần A khi sử dụng đường **VirtualMachine.loadAgent**. **Chiều ngược lại không đúng**. Một startup agent qua **-javaagent** hoặc một cơ chế nạp khác có thể đạt trạng thái B/C mà **không** đi qua thao tác A của controller đang xét.

### 1.1. Bảng đối chiếu nhanh

| Tình huống | Attach | Nạp agent | Biến đổi lớp mục tiêu |
| --- | --- | --- | --- |
| **VirtualMachine.attach** trả về, chưa gọi **loadAgent** | Có | Chưa | Chưa |
| Attach thành công, **loadAgent** ném **AgentLoadException** | Có | Không | Không có bằng chứng |
| Attach thành công, **agentmain** chạy ở chế độ quan sát rồi return | Có | Có | Không |
| Agent đăng ký transformer, lớp mục tiêu đã load nhưng không retransform | Có | Có | Chưa đối với lớp cũ |
| Transformer được gọi nhưng trả về **null** | Có | Có | Không do callback đó |
| Transformer trả về bytes khác nhưng JVM từ chối bytes | Có | Có thể đã vào agentmain | Không |
| **retransformClasses** hoàn thành và phép thử cho thấy hành vi mới | Có | Có | Có đối với lớp được kiểm chứng |

Không nên lưu một biến duy nhất tên **success=true** cho cả quy trình. Hãy ghi trạng thái và bằng chứng theo từng mốc.

## 2. Attach thành công thực sự chứng minh điều gì?

### 2.1. Controller và target là hai JVM riêng

**com.sun.tools.attach.VirtualMachine** nằm trong module JDK **jdk.attach**. Controller thường chạy ở **một JVM riêng**, nhận id của target (thường là PID trên hệ điều hành phổ biến) và yêu cầu provider của JDK kết nối:

~~~java
// Đoạn minh họa, nằm trong một phương thức đã xử lý exception.
import com.sun.tools.attach.VirtualMachine;

VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    System.out.println("ATTACH_OK");
    // Vẫn chưa gọi vm.loadAgent(...).
} finally {
    vm.detach();
}
~~~

Đoạn trên không phải file Java chạy độc lập. Ở tầng này, controller có quyền gọi những thao tác management mà provider hỗ trợ; ví dụ có thể đọc system properties của target. **Không có gì trong câu lệnh attach tự động nạp Agent-Class hay gọi ClassFileTransformer.**

- **AttachNotSupportedException**: provider không hỗ trợ kết nối tới JVM đích theo điều kiện hiện tại (hoặc không có provider tương thích).
- **IOException**: có thể xảy ra lỗi kết nối/I/O khi attach.
- **Vấn đề quyền và chính sách của JVM**: PID đúng chưa đủ. Người dùng hệ điều hành, cấu hình JVM, vùng cách ly container, chính sách attach và việc target còn tồn tại đều có thể tác động.
- **Self-attach**: không nên xem “tự attach vào PID của chính JVM controller” là tình huống luôn được cho phép; nhiều môi trường có hạn chế riêng.

**detach** chỉ hủy kết nối controller tới target theo API Attach. Nó không gỡ agent đã nạp, không hoàn nguyên lớp đã biến đổi và không kết thúc target JVM.

### 2.2. Attach thành công không đồng nghĩa agent tồn tại

Cùng một target PID có thể nhận nhiều lần attach để truy vấn thông tin hoặc nạp các agent khác nhau. Do đó log:

~~~text
ATTACH_OK pid=12345
~~~

chỉ là bằng chứng cho mốc A. Nó không mang ý nghĩa “agent sẵn sàng”, “đã đăng ký transformer” hay “code của ứng dụng đã đổi”. Nếu phép thử dừng tại đây, báo **ATTACH_ONLY** sẽ chính xác hơn báo **INSTRUMENTED**.

## 3. Nạp agent thành công cần thêm điều kiện nào?

### 3.1. Java agent attach dùng Agent-Class và agentmain

Đường attach vào JVM đang chạy khác với startup agent:

| Tình huống | Thuộc tính manifest | Callback Java agent |
| --- | --- | --- |
| JVM khởi động cùng **-javaagent:...** | **Premain-Class** | **premain(String, Instrumentation)** |
| Controller gọi **VirtualMachine.loadAgent(...)** | **Agent-Class** | **agentmain(String, Instrumentation)** |

Khi dynamic attach, JVM cố gọi dạng **agentmain(String, Instrumentation)** trước, rồi dạng **agentmain(String)** nếu dạng đầu không có. Dùng dạng hai tham số nếu cần đối tượng **Instrumentation** được JVM cấp.

Ví dụ entry point rút gọn:

~~~java
// Đoạn minh họa trong một lớp agent, chưa phải file hoàn chỉnh.
public static void agentmain(
        String options,
        java.lang.instrument.Instrumentation instrumentation) {
    System.out.println("AGENTMAIN_ENTERED");
    System.out.println("AGENT_OPTIONS=" + options);
}
~~~

Controller gọi **vm.loadAgent(path, options)**. Theo hợp đồng Attach API, **loadAgent** chờ lời gọi **agentmain** hoàn thành; nếu không phát sinh lỗi ở tầng API, phương thức trở về bình thường. Nhưng đó vẫn là **thành công của việc nạp/khởi tạo theo cơ chế API**, không phải bằng chứng tính năng nghiệp vụ đang chạy đúng.

**Đường dẫn JAR** được target JVM diễn giải trên **hệ thống tệp của target**. Trong bài thực hành controller và target ở cùng máy nên đường dẫn tuyệt đối giống nhau; nếu target khác môi trường mount/container, phải xác nhận path thực sự hiện diện ở phía target.

### 3.2. Vì sao loadAgent trả về vẫn chưa đủ?

Có ít nhất bốn khả năng:

1. **agentmain chỉ log rồi return**: agent đã được gọi, nhưng chưa đăng ký transformer.
2. **agentmain bắt lỗi rồi không ném lại**: phía controller có thể thấy **loadAgent** hoàn thành; tính năng bên trong đã thất bại và cần được phản ánh bằng trạng thái agent riêng.
3. **đăng ký transformer nhưng chưa gặp lớp mục tiêu**: bộ biến đổi chờ các class load tương lai; lớp đã load trước đó không tự đi qua transformer chỉ vì đăng ký muộn.
4. **đăng ký transformer thành công nhưng callback trả về null**: đối với lớp được gọi, không có bytes thay thế từ transformer ấy.

Nếu JVM không thể nạp agent JAR, thiếu **Agent-Class** hoặc gặp lỗi khởi tạo, controller có thể nhận **AgentLoadException**, **AgentInitializationException** hoặc **IOException** tùy giai đoạn và cách provider báo lỗi. Một **agentmain** có uncaught exception không làm target JVM bị hủy như quy tắc khởi động **premain**; lỗi có thể được JVM ghi log và được công cụ attach phản ánh theo hợp đồng API.

Để đo chất lượng khởi tạo thật, agent nên có trạng thái cấp ứng dụng, ví dụ **AGENT_STARTED**, **TRANSFORMER_REGISTERED**, **TARGET_FOUND**, **TRANSFORMED**, thay vì chỉ dựa vào việc controller không nhận exception.

## 4. Biến đổi lớp thành công là tầng xác minh riêng

### 4.1. ClassFileTransformer được gọi chưa đủ

Một transformer nhận **classfileBuffer** và trả về:

- **null**: không biến đổi lớp này từ callback đó.
- **byte[] mới**: đề xuất class file thay thế cho bước biến đổi kế tiếp/JVM xử lý. Input buffer không được sửa trực tiếp.
- **exception**: theo hợp đồng ClassFileTransformer, JVM vẫn có thể tiếp tục gọi các transformer khác và tiếp tục load/redefine/retransform; exception từ transformer được xử lý như việc không cung cấp thay đổi trong callback ấy.

Do đó log **TRANSFORM_CALLED** chứng minh callback chạy, còn **TRANSFORM_RETURNED_BYTES** chứng minh callback đã cung cấp bytes thay thế. Chúng **chưa tự bảo đảm** bytes được JVM chấp nhận, không bị transformer khác thay đổi, hoặc hành vi đích đã đổi.

### 4.2. Lớp mới load và lớp đã load có đường kiểm chứng khác nhau

- **Lớp chưa load**: đăng ký transformer **trước** khi lớp được định nghĩa. Khi có load, callback có thể cung cấp bytes thay thế. Sau đó kiểm tra class definition được chấp nhận và hành vi/bytecode đúng kỳ vọng.
- **Lớp đã load**: transformer mới không được gọi lại tự động cho bản định nghĩa trước đó. Nếu JVM/agent hỗ trợ, đăng ký transformer với **canRetransform=true**, xác định đúng **Class<?>**, kiểm tra **isRetransformClassesSupported()** và **isModifiableClass(clazz)** rồi gọi **retransformClasses(clazz)**.
- **Redefinition**: một đường khác sử dụng **redefineClasses(...)** và **ClassDefinition**, cũng chịu giới hạn capability/schema. Đừng đồng nhất redefine với retransform.

Khi **retransformClasses** trở về bình thường, JVM đã hoàn thành thao tác retransform cho những lớp được yêu cầu. Nhưng nếu không có transformer tạo thay đổi, hoặc bytes mới tương đương cũ, phương thức vẫn có thể hoàn thành mà **không tạo khác biệt hành vi**. Nếu bytes không hợp lệ hoặc thay đổi cấu trúc bị cấm, lời gọi có thể ném exception, ví dụ **ClassFormatError**, **UnsupportedOperationException**, **UnmodifiableClassException**, **LinkageError**. Khi retransform một tập lớp và lời gọi thất bại, API bảo đảm **không lớp nào trong tập đó được retransform thành công**.

### 4.3. Định nghĩa đúng lớp mục tiêu

Tên lớp đơn thuần chưa đủ cho hệ thống phức tạp:

~~~text
com.example.Service + defining loader A  -> Class A
com.example.Service + defining loader B  -> Class B
~~~

Hai **Class** có cùng tên đầy đủ nhưng được định nghĩa bởi loader khác nhau là hai kiểu runtime khác nhau. Khi kiểm chứng transformation, hãy ghi cả:

- Binary name và internal name (ví dụ **com.example.Service** và **com/example/Service**).
- Defining **ClassLoader** và **Module** của lớp mục tiêu.
- Loại sự kiện: **class load mới**, **redefine** hay **retransform**; **classBeingRedefined** thường khác null ở hai trường hợp sau.
- Phiên bản/build và nhận dạng bản sửa (ví dụ hash bytes **trước/sau** trong một pipeline có kiểm soát).
- Bằng chứng JVM đã chấp nhận bản sửa và hành vi mong đợi ở chính class đã chọn.

Nếu chỉ xem log **transform(name)** mà không gắn defining loader, có thể sửa nhầm một lớp khác tên giống nhau trong ứng dụng plugin/server.

## 5. Bài thực hành Java 17: tự thấy ba mức thành công

Ví dụ gồm **ba file Java** và **một manifest**. Controller attach vào một target JVM đang chạy; agent có hai chế độ:

- **observe**: nạp agent thành công nhưng **cố ý không biến đổi lớp**.
- **patch**: dùng **retransformClasses** để đổi literal trả về của một method trong lớp đã load, từ **OLD_VALUE** thành **NEW_VALUE**, rồi quan sát kết quả từ target.

Để giữ ví dụ độc lập với thư viện ngoài, transformer chỉ thay một entry **CONSTANT_Utf8** có cùng độ dài trong một class file được thiết kế cho demo. Đây **không phải transformer tổng quát cho production**. Trong hệ thống thật, nên sử dụng thư viện bytecode như ASM/Byte Buddy để xử lý cấu trúc và kiểm chứng nghiêm ngặt.

### 5.1. TargetApp.java — ứng dụng cần quan sát

~~~java
// File: TargetApp.java
public final class TargetApp {
    static final class Probe {
        static String value() {
            return "OLD_VALUE";
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("TARGET_PID=" + ProcessHandle.current().pid());

        while (true) {
            System.out.println("PROBE=" + Probe.value());
            Thread.sleep(1500);
        }
    }
}
~~~

**Probe.value()** là method thực, được gọi lặp lại trong JVM mục tiêu. Không đặt giá trị **OLD_VALUE** trong một **static final String** mà bên gọi có thể inline tại compile time; bài thực hành muốn kiểm chứng định nghĩa method đã thay đổi.

**ProcessHandle.current().pid()** in PID thật của target; giá trị khác nhau giữa các lần chạy. Khi vòng lặp đã in **PROBE=OLD_VALUE**, ta biết nested class **TargetApp$Probe** đã được load trước khi attach.

### 5.2. AttachAgent.java — agentmain và transformer

~~~java
// File: AttachAgent.java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class AttachAgent {
    private AttachAgent() {
    }

    public static void agentmain(String mode, Instrumentation inst)
            throws Exception {
        System.out.println("AGENTMAIN_ENTERED mode=" + mode);

        if ("observe".equals(mode)) {
            System.out.println("AGENT_READY_NO_TRANSFORM");
            return;
        }

        if (!"patch".equals(mode)) {
            throw new IllegalArgumentException("Unknown mode: " + mode);
        }

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransform not supported");
        }

        Class<?> target = null;
        for (Class<?> loaded : inst.getAllLoadedClasses()) {
            if ("TargetApp$Probe".equals(loaded.getName())) {
                target = loaded;
                break;
            }
        }

        if (target == null) {
            throw new IllegalStateException("TargetApp$Probe is not loaded");
        }
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Target class is not modifiable");
        }

        Utf8Transformer transformer = new Utf8Transformer();
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
            if (!transformer.changed()) {
                throw new IllegalStateException(
                        "No replacement bytes supplied for target"
                );
            }
            System.out.println("RETRANSFORM_COMPLETED");
        } finally {
            inst.removeTransformer(transformer);
        }
    }
}

final class Utf8Transformer implements ClassFileTransformer {
    private volatile boolean replacementSupplied;

    boolean changed() {
        return replacementSupplied;
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String name,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] bytes) {
        if (!"TargetApp$Probe".equals(name)
                || classBeingRedefined == null) {
            return null;
        }

        byte[] patched = replaceKnownLiteral(bytes);
        if (patched != null) {
            replacementSupplied = true;
            System.out.println("TRANSFORM_RETURNED_BYTES");
        }
        return patched;
    }

    private static byte[] replaceKnownLiteral(byte[] bytes) {
        // Đây là công cụ chỉ dành cho class demo, không phải parser
        // class-file tổng quát hay API thay chuỗi trên bytecode tùy ý.
        if (bytes.length < 10
                || (bytes[0] & 0xff) != 0xca
                || (bytes[1] & 0xff) != 0xfe
                || (bytes[2] & 0xff) != 0xba
                || (bytes[3] & 0xff) != 0xbe) {
            return null;
        }

        int poolCount = u2(bytes, 8);
        int p = 10;

        for (int i = 1; i < poolCount; i++) {
            int tag = bytes[p++] & 0xff;
            switch (tag) {
                case 1: { // CONSTANT_Utf8_info
                    int length = u2(bytes, p);
                    p += 2;
                    if (length == 9 && matchesAscii(bytes, p, "OLD_VALUE")) {
                        byte[] result = bytes.clone();
                        byte[] newer = "NEW_VALUE"
                                .getBytes(StandardCharsets.US_ASCII);
                        System.arraycopy(newer, 0, result, p, newer.length);
                        return result;
                    }
                    p += length;
                    break;
                }
                case 3: case 4:       // Integer, Float
                    p += 4;
                    break;
                case 5: case 6:       // Long, Double: hai slot
                    p += 8;
                    i++;
                    break;
                case 7: case 8: case 16: case 19: case 20:
                    p += 2;
                    break;
                case 9: case 10: case 11: case 12: case 17: case 18:
                    p += 4;
                    break;
                case 15:             // MethodHandle
                    p += 3;
                    break;
                default:
                    throw new IllegalArgumentException(
                            "Unsupported constant-pool tag: " + tag
                    );
            }
        }
        return null;
    }

    private static int u2(byte[] bytes, int offset) {
        return ((bytes[offset] & 0xff) << 8)
                | (bytes[offset + 1] & 0xff);
    }

    private static boolean matchesAscii(byte[] bytes, int offset,
                                        String value) {
        if (offset + value.length() > bytes.length) {
            return false;
        }
        for (int i = 0; i < value.length(); i++) {
            if (bytes[offset + i] != (byte) value.charAt(i)) {
                return false;
            }
        }
        return true;
    }
}
~~~

**Giải thích từng bước:**

1. **agentmain** in bằng chứng vào **stdout của target JVM**, không phải stdout của controller.
2. Chế độ **observe** trở về ngay sau log. Nó cố ý tạo trường hợp **A=PASS, B=PASS, C=NOT_PERFORMED**.
3. Chế độ **patch** kiểm tra capability trước khi thao tác. **Can-Retransform-Classes** trong manifest và hỗ trợ JVM đều cần thiết.
4. Agent tìm lớp đã load bằng **getAllLoadedClasses()**. Ví dụ chỉ có một bản **TargetApp$Probe**; production phải bổ sung kiểm tra defining loader/module trước khi chọn.
5. Agent đăng ký một transformer hỗ trợ retransformation (**true**), gọi **retransformClasses(target)**, kiểm tra có bytes thay thế, rồi gỡ transformer. **removeTransformer** không tự hoàn nguyên bản sửa vừa cài.
6. Transformer sao chép classfileBuffer, thay chính xác **9 byte ASCII** của literal **OLD_VALUE** bằng **NEW_VALUE** trong constant pool; không thêm method, field, thay đổi kế thừa hay độ dài bytecode. Với class demo này, JVM có thể kiểm tra và dùng định nghĩa mới.
7. Sau khi **retransformClasses** trả về không lỗi, agent in **RETRANSFORM_COMPLETED**. Bằng chứng quyết định cuối cùng vẫn là dòng **PROBE=NEW_VALUE** do target tự in khi gọi lại method.

**Cảnh báo về phạm vi parser minh họa:** Cách thay literal được viết riêng cho class hợp lệ do **javac** tạo ở đây. Class file thông thường có cấu trúc phức tạp, modified UTF-8, ràng buộc verifier, nhiều constant-pool entry và metadata khác. Không dùng hàm này để sửa class bất kỳ hay thay nó cho thư viện bytecode. Việc thay một constant pool entry cũng có thể tác động mọi nơi cùng tham chiếu entry đó nếu áp dụng vào lớp khác.

### 5.3. AttachCommand.java — controller báo riêng attach và load

~~~java
// File: AttachCommand.java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachCommand {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: AttachCommand <pid> <agent-jar> <observe|patch>"
            );
        }

        String pid = args[0];
        String agentPath = Path.of(args[1])
                               .toAbsolutePath()
                               .normalize()
                               .toString();
        String mode = args[2];

        VirtualMachine vm = VirtualMachine.attach(pid);
        System.out.println("ATTACH_OK");

        try {
            vm.loadAgent(agentPath, mode);
            System.out.println("LOAD_AGENT_OK");
        } finally {
            vm.detach();
        }
    }
}
~~~

Đoạn này chủ ý đặt log **ATTACH_OK** ngay sau **attach(...)**, còn **LOAD_AGENT_OK** chỉ in khi **loadAgent(...)** hoàn thành bình thường. Nếu **loadAgent** lỗi, controller vẫn chạy **detach** trong **finally**, và không in nhầm **LOAD_AGENT_OK**.

**Lưu ý:** Đây là controller trong một JVM riêng. Nó không trực tiếp nhận tham số **Instrumentation** từ target: handle đó được target JVM truyền cho **AttachAgent.agentmain(...)**.

### 5.4. agent.mf — manifest cho dynamic attach

Tạo file văn bản **agent.mf**:

~~~text
Manifest-Version: 1.0
Agent-Class: AttachAgent
Can-Retransform-Classes: true
~~~

Đặt **newline cuối file manifest**. Với ví dụ này, **Agent-Class** là bắt buộc, còn **Can-Retransform-Classes: true** yêu cầu JVM cho phép agent dùng retransform. Đây không phải manifest dành riêng cho startup **-javaagent**; thuộc tính **Premain-Class** không thay thế được **Agent-Class** trong bài thực hành attach.

### 5.5. Biên dịch và đóng gói

Trong một thư mục chứa **TargetApp.java**, **AttachAgent.java**, **AttachCommand.java**, **agent.mf**, sử dụng **JDK 17 đầy đủ**:

~~~bash
javac --release 17 TargetApp.java AttachAgent.java
javac --release 17 --add-modules jdk.attach AttachCommand.java
jar cfm attach-agent.jar agent.mf AttachAgent.class Utf8Transformer.class
~~~

File **TargetApp$Probe.class** do **javac** tạo tự động từ nested class trong **TargetApp.java**. Nó ở classpath của **target**, không cần đóng vào **attach-agent.jar**. Agent JAR phải chứa **AttachAgent.class**, **Utf8Transformer.class** và **META-INF/MANIFEST.MF**.

Nếu JDK/bản phân phối của bạn yêu cầu cấu hình module khi chạy controller, thêm **--add-modules jdk.attach** như lệnh bên dưới. Không chạy controller bằng runtime thiếu module **jdk.attach**.

### 5.6. Khởi chạy target (terminal thứ nhất)

~~~bash
java -XX:+EnableDynamicAgentLoading -cp . TargetApp
~~~

Ví dụ output ban đầu (**PID chỉ để minh họa**):

~~~text
TARGET_PID=12345
PROBE=OLD_VALUE
PROBE=OLD_VALUE
PROBE=OLD_VALUE
~~~

Giữ terminal này chạy. **-XX:+EnableDynamicAgentLoading** là tùy chọn của HotSpot hỗ trợ bật nạp agent động; Java 21 đã bổ sung cảnh báo khi agent được nạp động mà không thể hiện opt-in thích hợp. Hành vi mặc định và thông báo có thể thay đổi theo phiên bản/JVM: kiểm tra chính sách của chính runtime đích. Cơ chế attach còn chịu điều kiện quyền hệ điều hành và môi trường triển khai.

### 5.7. Chỉ quan sát — attach và load thành công, chưa transform (terminal thứ hai)

Dùng **PID thật** mà target in:

~~~bash
java --add-modules jdk.attach -cp . AttachCommand 12345 attach-agent.jar observe
~~~

Output controller:

~~~text
ATTACH_OK
LOAD_AGENT_OK
~~~

Target đồng thời ghi các dòng tương ứng từ **agentmain**:

~~~text
AGENTMAIN_ENTERED mode=observe
AGENT_READY_NO_TRANSFORM
~~~

Các lần tiếp theo của vòng lặp vẫn có:

~~~text
PROBE=OLD_VALUE
~~~

**Kết luận chính xác:** controller đã attach và load agent xong; agentmain đã thực thi và kết thúc bình thường, nhưng **không có transformer nào được đăng ký/áp dụng** trong chế độ observe. Đây là bằng chứng thực hành vì sao **LOAD_AGENT_OK không thể đồng nghĩa TRANSFORMATION_OK**.

### 5.8. Thực hiện patch — xác nhận thành công mức C

Trong khi target vẫn chạy, thực hiện lại controller:

~~~bash
java --add-modules jdk.attach -cp . AttachCommand 12345 attach-agent.jar patch
~~~

Controller lại in:

~~~text
ATTACH_OK
LOAD_AGENT_OK
~~~

Target in thêm:

~~~text
AGENTMAIN_ENTERED mode=patch
TRANSFORM_RETURNED_BYTES
RETRANSFORM_COMPLETED
~~~

Sau đó, những lần gọi **Probe.value()** mới trong target sẽ in:

~~~text
PROBE=NEW_VALUE
~~~

Các dòng **PROBE=OLD_VALUE** có thể đã xuất hiện trước thời điểm retransform; hai terminal hoạt động đồng thời, vì vậy thứ tự các dòng xen kẽ không có một transcript thời gian cố định. Ba dòng **TRANSFORM_RETURNED_BYTES**, **RETRANSFORM_COMPLETED**, **PROBE=NEW_VALUE** là ba loại bằng chứng tăng dần: callback đã cung cấp bytes, API retransform hoàn tất, và hành vi quan sát từ chính lớp đích đã thay đổi.

Dừng target bằng **Ctrl+C** sau khi thử xong. Không cần gọi **detach** trên target: controller đã thực hiện thao tác này trong **finally**, còn target và agent có vòng đời độc lập.

### 5.9. Trường hợp attach OK nhưng load agent FAIL

Để mô phỏng JAR không phải agent, trong cùng thư mục tạo một JAR không có **Agent-Class**:

~~~bash
jar cf not-agent.jar TargetApp.class
java --add-modules jdk.attach -cp . AttachCommand 12345 not-agent.jar observe
~~~

Nếu attach vẫn được phép, controller sẽ in **ATTACH_OK** rồi **loadAgent** báo lỗi vì JAR không phải agent Java hợp lệ cho cơ chế này; **LOAD_AGENT_OK** sẽ **không xuất hiện**. Loại exception/stack trace chi tiết phụ thuộc JVM/provider. Bài học không yêu cầu target phải thay đổi hay bị dừng khi agent load lỗi.

Đây là trường hợp đối chứng trực tiếp giữa mức A và mức B, khác với chế độ **observe** vốn phân biệt B và C.

## 6. Bộ quan sát thực tế: đặt log đúng chỗ

Một hệ thống dễ chẩn đoán nên có **request ID** cho mỗi yêu cầu attach và tách log theo tiến trình.

| Mốc | Bên phát ra | Bằng chứng | Được kết luận đến mức nào? |
| --- | --- | --- | --- |
| **ATTACH_ATTEMPT** | Controller | PID/id, thời điểm, JVM/provider | Mới thử kết nối |
| **ATTACH_OK** | Controller | **attach(...)** trả handle | A |
| **LOAD_AGENT_REQUESTED** | Controller | Path JAR được target nhìn thấy, mode, request ID | Mới gửi yêu cầu |
| **AGENTMAIN_ENTERED** | Target agent | Agent-Class, mode/request ID, version agent | Callback đã bắt đầu |
| **LOAD_AGENT_OK** | Controller | **loadAgent(...)** trả bình thường | B theo hợp đồng API |
| **TRANSFORMER_REGISTERED** | Target agent | Identity transformer, canRetransform | Có bộ xử lý cho class events |
| **TARGET_CLASS_SELECTED** | Target agent | FQCN + loader + module + tính modifiable | Chọn đúng đối tượng định sửa |
| **TRANSFORM_RETURNED_BYTES** | Target agent | Class identity, event, hash input/output nếu phù hợp | Có đề xuất bytes thay thế |
| **RETRANSFORM_COMPLETED** | Target agent | **retransformClasses(...)** trả bình thường | JVM đã hoàn thành thao tác retransform |
| **PROBE_NEW_BEHAVIOR** | Target/quan sát độc lập | Giá trị method, tín hiệu business hoặc kiểm tra bytes đã cài | C đối với mục tiêu kiểm chứng |

Cần theo dõi **đúng JVM/process** cho mỗi dòng. Log **AGENTMAIN_ENTERED** do target phát ra; không thể suy đoán việc target đã thực thi code chỉ từ stdout của controller.

### 6.1. Trạng thái minh họa cho workflow

~~~text
REQUESTED
   │
   ├── ATTACH_FAILED             -> chưa có handle
   │
   ▼
ATTACHED
   │
   ├── AGENT_LOAD_FAILED         -> handle có, agent chưa khởi tạo đúng
   │
   ▼
AGENT_LOADED
   │
   ├── TRANSFORM_NOT_REQUESTED   -> chỉ quan sát
   ├── TARGET_NOT_FOUND          -> chưa chọn được Class cần sửa
   ├── TRANSFORM_NO_CHANGE       -> không có bytes mới
   ├── TRANSFORM_REJECTED        -> JVM từ chối bản sửa
   │
   ▼
TRANSFORM_COMPLETED
   │
   ├── EFFECT_NOT_CONFIRMED      -> chưa có phép thử/hành vi đích
   ▼
BEHAVIOR_VERIFIED
~~~

Đây là các **trạng thái do ứng dụng của bạn định nghĩa**, không phải những enum chuẩn của **VirtualMachine** hay **Instrumentation**. Trong hệ thống thật, nên kèm error cause, timestamp, request ID, class loader identity và phiên bản target để debug.

### 6.2. Vì sao cần kiểm tra cuối tại target?

Một request có thể là “đổi cách ghi log của method X” hoặc “gắn metric cho method Y”. Nếu chỉ có callback được gọi, bạn không biết chắc:

- Bytecode mới được chấp nhận hay bị verifier/retransform từ chối.
- Đúng class được sử dụng bởi request thật hay chỉ một bản trùng FQCN do loader khác định nghĩa.
- Những invocation sau retransform có đi qua code mới hay đã bị bypass bởi một nhánh logic khác.
- Feature hoạt động đúng nhưng chưa có traffic chạm vào method mục tiêu.

Phép thử nên tạo một **invocation mới có thể nhận diện** sau thời điểm biến đổi. Với lớp đã retransform, **active stack frames** đang chạy có thể tiếp tục dùng định nghĩa cũ, trong khi lời gọi mới sử dụng định nghĩa mới. Do đó đừng đánh giá thành công/thất bại chỉ bằng một call đã bắt đầu trước khi patch.

## 7. Bẫy liên quan capability và chính sách JVM

### 7.1. Attach được chưa có nghĩa retransform được

Agent JAR có thể được JVM chấp nhận nhưng không xin quyền retransform. Trước khi đăng ký transformer **canRetransform=true**, kiểm tra **inst.isRetransformClassesSupported()**. Đối với class mục tiêu, kiểm tra **inst.isModifiableClass(clazz)**. Cả hai đều cần nhưng vẫn chưa đảm bảo bytecode sửa sẽ được chấp nhận nếu vi phạm giới hạn schema.

Giới hạn thông thường khi retransform/redefine lớp đã tồn tại: không tùy tiện thêm/xóa field hoặc method, đổi quan hệ kế thừa hoặc áp các thay đổi cấu trúc mà JVM không hỗ trợ. Agent cần thiết kế instrumentation trong phạm vi method body/bytecode và metadata được phép, hoặc dùng phương án khác.

Một phép **retransformClasses** có thể hoàn thành ngay cả khi mọi transformer đều trả **null**. Bởi vậy **RETRANSFORM_COMPLETED** vẫn chưa tự nó chứng minh thay đổi hành vi; phải kiểm tra cả bytes đã cung cấp và đầu ra thực tế.

### 7.2. Chính sách dynamic attach và dynamic agent loading là hai lớp điều kiện

Một JVM có thể cho attach nhưng từ chối **nạp agent động**, ví dụ khi target bật cấu hình **-XX:-EnableDynamicAgentLoading** trên JVM có hỗ trợ tùy chọn này. Thực tế cũng có thể vướng quyền OS, container namespace, attach provider, runtime image thiếu thành phần cần thiết hoặc thay đổi chính sách giữa các bản JDK.

Từ JDK 21, HotSpot đưa ra cảnh báo đối với việc nạp agent động trong một số cấu hình, gắn với hướng đi *integrity by default*. Có thể bật **-XX:+EnableDynamicAgentLoading** trên target được hỗ trợ và theo chính sách vận hành của hệ thống; cần kiểm tra phiên bản/JVM thay vì giả định mọi bản Java đều có cùng mặc định. Điều này khác với **-javaagent** khi JVM khởi động: startup agent không dựa vào **VirtualMachine.attach** của controller.

## 8. Xử lý lỗi theo đúng tầng, không gộp thành “attach fail”

| Triệu chứng | Tầng liên quan | Kiểm tra trước |
| --- | --- | --- |
| **AttachNotSupportedException** khi gọi attach | A | Provider hỗ trợ JVM đích không? Đúng PID/namespace/OS permission? |
| **IOException** trong attach | A | Target còn sống? Kênh attach và quyền truy cập có ổn không? |
| **ATTACH_OK** xuất hiện nhưng **AgentLoadException** theo sau | B | Đường dẫn JAR phía target, manifest **Agent-Class**, agent JAR hợp lệ? |
| **AgentInitializationException** hoặc agentmain lỗi | B | Stack trace của **agentmain**, dependency của agent, tham số mode, target log? |
| **LOAD_AGENT_OK** nhưng không có dấu hiệu tính năng | B -> C | Agentmain có return sớm/catch exception? Có đăng ký transformer? |
| Có **TRANSFORMER_REGISTERED** nhưng không có callback | C | Lớp đã load? Có cần retransform? Lọc className/loader có khớp? |
| Có **TRANSFORM_RETURNED_BYTES** nhưng **retransformClasses** lỗi | C | Class format, verifier, schema restriction, capability, linkage? |
| **retransformClasses** không lỗi nhưng hành vi cũ | C | Transformer đã trả bytes khác thật chưa? Chọn đúng class/loader? Call mới hay stack frame cũ? |
| Hành vi mới quan sát ở test nhưng request production không đổi | C | Có classloader khác, method khác, traffic chưa chạm code hay điều kiện logic khác? |

**Quy tắc debug:** ghi lỗi ở tầng phát sinh sớm nhất. Nếu A thất bại, đừng kết luận có lỗi transformer; nếu B trả về bình thường nhưng C thiếu bằng chứng, đừng báo “agent không attach được”. Tách các bước giúp tránh chẩn đoán nhầm và tránh thử attach lại vô hạn khi lỗi thực tế nằm ở bytecode hoặc logic xác minh.

## 9. Phân biệt năm câu log dễ gây hiểu lầm

### “Đã thấy PID”

Chỉ chứng minh công cụ liệt kê/tìm được PID; một process có thể biến mất trước khi attach. Chưa đủ cho A.

### “Attach thành công”

**VirtualMachine.attach(...)** trả handle. Chính xác cho A, chưa đủ cho B.

### “Agentmain đã chạy”

Chứng minh target đã bắt đầu callback agent. Nếu callback chưa kết thúc hoặc gặp lỗi giữa chừng, chưa thể đồng nhất với việc **loadAgent** hoàn thành thành công hay agent sẵn sàng.

### “Transformer đã chạy”

Chứng minh callback được gọi. Nếu trả null/throw, không cung cấp thay đổi. Nếu trả byte[] hợp lệ, JVM vẫn cần kiểm tra và cài đặt trước khi kết luận C.

### “Retransform đã trả về”

Chứng minh JVM hoàn thành request retransform (nếu không có exception), nhưng bản sửa có thể **không đổi bytes**. Phép kiểm chứng hành vi/định nghĩa thực tế mới xác nhận đúng mục tiêu nghiệp vụ.

## 10. Câu hỏi tự kiểm tra

1. **VirtualMachine.attach(pid) thành công thì agent JAR đã nằm trong target JVM chưa?** Chưa. Cần gọi **loadAgent(...)** hoặc một cơ chế nạp độc lập.
2. **loadAgent(...) trả về bình thường có chứng minh một class đã bị sửa không?** Không. **agentmain** có thể chỉ thực hiện tác vụ quan sát hoặc không có lớp nào được biến đổi.
3. **Trong dynamic attach, JVM tìm Premain-Class hay Agent-Class?** Tìm **Agent-Class** và gọi **agentmain**, không gọi **premain** cho đường này.
4. **Đăng ký transformer sau khi target class load có tự sửa class cũ không?** Không. Muốn transform một lớp đã nạp cần retransform/redefine phù hợp với capability JVM.
5. **Transformer trả về null có nghĩa bytecode của class đã đổi không?** Không bởi transformer đó.
6. **Transformer trả về một byte[] mới có đủ kết luận thành công không?** Chưa; kết quả có thể bị từ chối hoặc thay đổi bởi transformer khác.
7. **Vì sao cần kiểm tra cả defining class loader?** Vì hai lớp cùng FQCN ở hai loader khác nhau là hai kiểu runtime khác nhau.
8. **removeTransformer có hoàn nguyên method vừa retransform không?** Không. Nó gỡ đăng ký transformer; bản định nghĩa đã cài không tự quay về cũ.
9. **detach có gỡ agent khỏi target không?** Không. Nó đóng kênh Attach API của controller.
10. **Tại sao target có thể tiếp tục chạy sau khi agentmain thất bại?** Đường agent nạp sau startup không có chính sách hủy tiến trình giống **premain** startup; agent load failure được xử lý như lỗi của thao tác attach/agent và target vẫn có thể tiếp tục chạy.

## 11. Checklist xác minh trước khi báo “instrumentation thành công”

- Tôi có log **ATTACH_OK** chỉ sau khi **VirtualMachine.attach(...)** trả về.
- Tôi có log **LOAD_AGENT_OK** chỉ sau khi **vm.loadAgent(...)** trả về bình thường; **detach** luôn được gọi trong **finally**.
- Target chứng minh **agentmain** đã chạy, đã đọc đúng agent options và hoàn tất khởi tạo tính năng yêu cầu.
- Tôi kiểm tra đúng **Agent-Class**, đúng target JVM và đường dẫn JAR mà target nhìn thấy.
- Tôi biết class đã load hay chưa; nếu đã load thì capability retransform/redefine được kiểm tra.
- Tôi có danh tính target **Class + defining loader + module**, tránh sửa nhầm class cùng tên.
- Transformer thực sự cung cấp byte[] khác, không chỉ log khi callback bắt đầu; lỗi verifier/schema/transformer được ghi rõ.
- Tôi xác nhận thao tác cài định nghĩa hoàn tất, đồng thời kiểm tra **hành vi/bytecode hiệu lực ở chính target** bằng một invocation mới.
- Trạng thái được báo theo từng tầng (**A**, **B**, **C**), cùng thời gian, request ID và lỗi có nguyên nhân; không gộp tất cả vào “attach success”.

## 12. Tài liệu chính thức

- [Java 17 — VirtualMachine, Attach API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Java 17 — java.lang.instrument: Starting an Agent After VM Startup](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — Instrumentation, retransformClasses và capability](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)

Khi debug, hãy hỏi lần lượt: **(A) kết nối attach đã lập chưa? (B) target JVM đã thực sự load/callback agent chưa? (C) class đúng đã được JVM chấp nhận sửa và hành vi mới được kiểm chứng chưa?** Chỉ có đủ bằng chứng tới C mới có thể báo thành công của việc biến đổi lớp.
