# Attach agent vào một JVM thử nghiệm và biến đổi lớp đã nạp bằng retransformation

## 1. Mục tiêu: một JVM đang chạy đổi hành vi mà không khởi động lại

Khi Java agent được khởi động qua tham số `-javaagent`, JVM gọi `premain` trước khi chạy phương thức `main` của ứng dụng. Tuy nhiên nhiều tình huống chẩn đoán thực tế xảy ra **sau khi JVM và các class nghiệp vụ đã chạy**. Trong trường hợp môi trường và chính sách cho phép, có thể sử dụng **Attach API** từ một tiến trình Java khác để nạp agent động vào JVM đang chạy. Agent nhận `Instrumentation` trong `agentmain` và có thể yêu cầu JVM **retransform** một class đã nạp.

Bài thực hành này sẽ chứng minh đúng một luồng:

1. Khởi động **JVM đích** với class `demo.lab.TargetLogic`, phương thức `state()` ban đầu trả `"COLD"`. Ứng dụng gọi method trước lúc có agent.
2. Khởi động **JVM điều khiển** riêng, dùng `com.sun.tools.attach.VirtualMachine.attach(pid)` để attach vào PID JVM đích.
3. Điều khiển gọi `loadAgent(...)`, JVM đích tải agent JAR có manifest `Agent-Class`, chạy `agentmain`.
4. Agent kiểm tra `isRetransformClassesSupported()`, tìm `TargetLogic` trong `getAllLoadedClasses()`, kiểm tra `isModifiableClass(...)`.
5. Agent đăng ký `ClassFileTransformer` với `canRetransform=true`, gọi `retransformClasses(TargetLogic.class)`.
6. Transformer sửa một hằng chuỗi **ASCII cùng độ dài** từ `COLD` sang `WARM` trong classfile bytes **của chính class đã nạp**.
7. Ứng dụng đang chạy tiếp tục gọi method; lần gọi mới in `state=WARM`. JVM đích không restart, file `TargetLogic.class` trên disk cũng không bị ghi lại.

**Đây là thực nghiệm an toàn trên JVM tự tạo**, không phải lời khuyên hot-patch production tùy tiện. Thao tác attach có quyền thực thi mã trong JVM đích, và retransform có thể khiến chương trình lỗi nếu bytecode sai. Hãy thực hành trong tiến trình thử nghiệm do bạn sở hữu.

### Học xong bạn sẽ làm được gì?

- Phân biệt `premain`, `agentmain`, Attach API và lớp đang được retransformation.
- Viết đúng manifest `Agent-Class` cùng `Can-Retransform-Classes: true`.
- Biên dịch/run controller với module `jdk.attach` trên Java 17+.
- Thực hiện `VirtualMachine.attach` / `loadAgent` / `detach` bằng một tiến trình khác.
- Tìm class đã nạp **trong JVM đích** và xác nhận khả năng retransform trước khi đổi bytes.
- Phân biệt transformer được đăng ký với transformer **đã thực sự được gọi trên loaded class**.
- Hiểu tương tác của retransform với classfile baseline, transformer pipeline, active stack frames, static state, schema restrictions và classloaders.
- Kiểm chứng kết quả bằng **cùng PID** cùng ứng dụng trước/sau, thay vì chỉ tin dòng log agent.
- Chẩn đoán attach disabled, agent JAR sai manifest, thiếu quyền và bytecode không hợp lệ.

## 2. Kiến trúc: controller, agent, target là ba vai trò

~~~text
JVM ĐÍCH (target JVM)                JVM ĐIỀU KHIỂN (controller JVM)
  demo.lab.TargetApp                   demo.attach.Attacher
        |                                      |
  tải TargetLogic                           VirtualMachine.attach(pid)
        |                                      |
  state() => COLD                             |
        | <---------- Attach protocol --------+
        |                                      |
  JVM target tải attach-agent.jar <----- vm.loadAgent(path, "")
        |
  AttachAgent.agentmain(args, inst)
        |
        +-- getAllLoadedClasses()
        +-- chọn đúng target Class<?>/loader
        +-- kiểm isRetransformClassesSupported
        +-- kiểm isModifiableClass
        +-- addTransformer(transformer, true)
        +-- retransformClasses(target)
                 |
                 +-- ClassFileTransformer.transform(...)
                 +-- trả byte[] đổi COLD sang WARM
        +-- removeTransformer(transformer)
        |
  state() => WARM                    controller gọi vm.detach()
~~~

| Thành phần | Chạy ở đâu? | Trách nhiệm |
|---|---|---|
| `TargetApp` | JVM đích | Gọi class nghiệp vụ và in trạng thái quan sát |
| `TargetLogic` | JVM đích | Class được load và sử dụng **trước khi attach** |
| `Attacher` | JVM controller | Kết nối tới PID, yêu cầu JVM đích nạp agent, rồi detach |
| `AttachAgent` | JVM đích | Nhận `Instrumentation` và điều khiển retransformation |
| `PatchTransformer` | Callback trong JVM đích | Nhận classfile bytes, lọc class và trả bytes đã biến đổi |

Controller **không cầm đối tượng `Instrumentation` của target** trong process của chính mình. `Instrumentation` được JVM đích truyền vào `agentmain` sau khi tải JAR.

Cũng không nên nhầm Attach API với Java agent instrumentation: Attach là **đường đưa agent vào process**, còn `Instrumentation.retransformClasses` là **cơ chế áp dụng biến đổi cho class đã nạp**.

## 3. Điều kiện môi trường và bảo mật

### 3.1. Java và quyền attach

Thí nghiệm dùng API công khai trên **JDK 17+**, gồm:

- `java`, `javac` và `jar` để biên dịch/chạy/đóng gói.
- Module `jdk.attach` cho controller (`com.sun.tools.attach.VirtualMachine`).
- Module `java.instrument` cho agent (`Instrumentation`, `ClassFileTransformer`).
- Attach Provider tương thích target JVM, quyền OS/cùng chủ sở hữu tiến trình và đường tới agent JAR mà **JVM đích đọc được**.
- Khả năng retransformation do VM và manifest cho phép.

Một custom runtime image có thể không chứa `jdk.attach`; một JVM có thể vô hiệu hóa attach hoặc dynamic agent loading. Attach không phải cam kết luôn thành công trên mọi JVM vendor, container, OS user hay policy.

**Quy tắc an toàn:** chỉ attach JVM tự sở hữu hoặc được ủy quyền rõ ràng. Không thử trên process sản xuất của người khác hoặc JVM đang xử lý dữ liệu quan trọng. Nạp agent tương đương đưa code có quyền cao vào process đích.

### 3.2. Cảnh báo dynamic loading của JDK 21+

JEP 451 chuẩn bị giới hạn nạp agent động mặc định trong tương lai. Từ JDK 21, một số cấu hình JDK phát cảnh báo khi Java agent được nạp động. Trong bài kiểm thử thực tế trên **JDK 24**, JVM đích đã in cảnh báo trên stderr, trong khi attach và retransform vẫn **thành công**:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: Dynamic loading of agents will be disallowed by default in a future release
~~~

Đừng coi warning này là lỗi `retransformClasses`. Nếu môi trường lab cho phép, có thể chủ động khởi chạy **JVM đích** với:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/target demo.lab.TargetApp stop.flag
~~~

Cờ này thể hiện chủ ý cho phép nạp agent động trong các JDK hỗ trợ nó; không phải phương pháp vượt quyền, không thay đổi quy định bảo mật, và **không** đảm bảo attach thành công khi thiếu quyền hoặc attach mechanism đã tắt. Kiểm tra tài liệu và chính sách cụ thể của JVM đang dùng, không giả định mọi release sau này có cùng hành vi như JDK 24.

### 3.3. Vì sao dùng hai JVM, không self-attach?

Một số JVM hạn chế self-attach hoặc cần option riêng. Bài thực hành sử dụng `Attacher` chạy ở **process thứ hai**, giúp tránh sai khác self-attach policy và làm rõ PID nào bị thay đổi. Không nhầm PID của controller với PID của target.

### 3.4. Các tiêu chí xác minh PASS

Thí nghiệm chỉ đạt khi chứng minh đủ:

~~~text
Target in pid=... và state=COLD trước khi controller attach.
Attacher kết nối đúng PID và load agent JAR thành công.
Agentmain tìm TargetLogic đã load, class modifiable.
Transformer capable nhận callback retransform trên class đó.
JVM chấp nhận bytes mới: retransformClasses trả không lỗi.
Lời gọi mới tới TargetLogic.state() in state=WARM.
JVM đích vẫn là tiến trình cũ; không ghi đè classfile gốc.
~~~

Chỉ thấy `attach=done` chưa đủ để kết luận biến đổi chính xác. Cần đối chiếu **behavior runtime**.

## 4. Cây thư mục và ý nghĩa của các file

~~~text
attach-retransform-lab/
├── AGENT.MF
├── src/
│   ├── target/
│   │   └── demo/lab/
│   │       ├── TargetLogic.java
│   │       └── TargetApp.java
│   ├── agent/
│   │   └── demo/attach/
│   │       └── AttachAgent.java
│   └── control/
│       └── demo/attach/
│           └── Attacher.java
└── out/                       # sinh ra sau build
    ├── target/
    ├── agent/
    ├── control/
    └── attach-agent.jar
~~~

Có **bốn Java source files** và một manifest. Không sử dụng ASM, Byte Buddy, Maven, JNI hoặc API classfile nội bộ. Bytecode patcher trong lab chỉ phục vụ thay một hằng UTF8 **cùng chiều dài**, giữ nguyên method schema.

Ngoài ra `stop.flag` là file mà **target app tự kiểm tra để thoát sớm**; nó không thuộc Attach API. Không tạo file này **trước** khi target bắt đầu, nếu không target có thể dừng trước lúc attach.

## 5. Mã nguồn JVM đích

### 5.1. `src/target/demo/lab/TargetLogic.java`

~~~java
package demo.lab;

public final class TargetLogic {
    private TargetLogic() {}

    public static String state() {
        return "COLD";
    }
}
~~~

Một method rất ngắn dùng `ldc` với hằng chuỗi. Khi JVM định nghĩa class, method có thể được gọi bất kỳ lúc nào. Ở thí nghiệm này, `state()` đã được gọi trước attach, nên không còn là ví dụ load-time instrumentation.

### 5.2. `src/target/demo/lab/TargetApp.java`

~~~java
package demo.lab;

import java.nio.file.Files;
import java.nio.file.Path;

public final class TargetApp {
    private TargetApp() {}

    public static void main(String[] args) throws Exception {
        Path done = Path.of(args[0]);
        System.out.println("pid=" + ProcessHandle.current().pid());
        String previous = null;
        for (int n = 0; n < 200; n++) {
            String current = TargetLogic.state();
            if (!current.equals(previous)) {
                System.out.println("state=" + current);
                System.out.flush();
                previous = current;
            }
            if (Files.exists(done)) break;
            Thread.sleep(100);
        }
        System.out.println("target=done");
    }
}
~~~

Giải thích:

- `ProcessHandle.current().pid()` in **PID thực tế** của target JVM. Khi attach, dùng PID này, không lấy một PID ví dụ cố định.
- Vòng lặp gọi `TargetLogic.state()` trước khi agent xuất hiện, nên chắc chắn class đã load và method đã chạy.
- `previous` tránh in lặp mỗi 100 ms. Kết quả quan sát thông thường chỉ có một dòng `state=COLD` và khi biến đổi thành công sẽ có một dòng `state=WARM`.
- `System.out.flush()` giúp log được nhìn thấy ngay khi redirect stdout.
- `Files.exists(done)` là điều kiện kết thúc sớm dành riêng cho lab. Target còn có giới hạn 200 vòng để không chạy vô hạn.
- Khi một lần invocation mới tới `state()` trả WARM, tiến trình vẫn tiếp tục dùng đúng JVM/PID cũ, không gọi constructor/`<clinit>` mới.

**Không tạo `stop.flag` trước khi start target**. Nếu target kết thúc quá sớm, hãy khởi động lại đúng quy trình thay vì attach PID đã hết tồn tại.

## 6. Agent nạp động và transformer retransformation-capable

### 6.1. `src/agent/demo/attach/AttachAgent.java`

~~~java
package demo.attach;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class AttachAgent {
    private AttachAgent() {}

    public static void agentmain(String args, Instrumentation inst) throws Exception {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation unsupported");
        }
        Class<?> target = null;
        for (Class<?> type : inst.getAllLoadedClasses()) {
            if ("demo.lab.TargetLogic".equals(type.getName())
                    && type.getClassLoader() == ClassLoader.getSystemClassLoader()) {
                target = type;
                break;
            }
        }
        if (target == null || !inst.isModifiableClass(target)) {
            throw new IllegalStateException("Target not found/modifiable");
        }
        PatchTransformer transformer = new PatchTransformer();
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
            if (!transformer.patched) {
                throw new IllegalStateException("Target bytes not patched");
            }
            System.out.println("agent=retransformed");
        } finally {
            inst.removeTransformer(transformer);
        }
    }

    private static final class PatchTransformer implements ClassFileTransformer {
        volatile boolean patched;

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> redefining, ProtectionDomain domain, byte[] input) {
            if (!"demo/lab/TargetLogic".equals(name)
                    || redefining == null
                    || loader != ClassLoader.getSystemClassLoader()) {
                return null;
            }
            byte[] output = replaceConstant(input);
            patched = output != null;
            return output;
        }

        private static byte[] replaceConstant(byte[] input) {
            if (input == null || input.length < 10
                    || (input[0] & 255) != 0xca
                    || (input[1] & 255) != 0xfe
                    || (input[2] & 255) != 0xba
                    || (input[3] & 255) != 0xbe) return null;

            int entries = u2(input, 8), p = 10, matches = 0;
            byte[] output = input.clone();

            for (int i = 1; i < entries; i++) {
                if (p >= input.length) return null;
                int tag = input[p++] & 255;
                switch (tag) {
                    case 1: {
                        if (p + 2 > input.length) return null;
                        int len = u2(input, p);
                        p += 2;
                        if (p + len > input.length) return null;
                        if (len == 4 && input[p] == 'C'
                                && input[p+1] == 'O'
                                && input[p+2] == 'L'
                                && input[p+3] == 'D') {
                            output[p] = 'W'; output[p+1] = 'A';
                            output[p+2] = 'R'; output[p+3] = 'M';
                            matches++;
                        }
                        p += len;
                        break;
                    }
                    case 3: case 4: case 9: case 10:
                    case 11: case 12: case 17: case 18:
                        p += 4; break;
                    case 5: case 6:
                        p += 8; i++; break;
                    case 7: case 8: case 16: case 19: case 20:
                        p += 2; break;
                    case 15:
                        p += 3; break;
                    default:
                        return null;
                }
                if (p > input.length) return null;
            }
            return matches == 1 ? output : null;
        }

        private static int u2(byte[] bytes, int pos) {
            return ((bytes[pos] & 255) << 8) | (bytes[pos + 1] & 255);
        }
    }
}
~~~

### 6.2. `agentmain` chạy trong JVM nào?

Đây là **Java agent được load động**. `VirtualMachine.loadAgent` khiến **target JVM** chạy `agentmain` và cấp `Instrumentation`. Vì thế `getAllLoadedClasses` trả về các lớp của **target**, còn `System.out.println("agent=retransformed")` xuất hiện ở **target stdout**.

Nếu controller chưa nạp agent hoặc manifest sai `Agent-Class`, agentmain không chạy. Nếu target VM chặn dynamic loading, controller có thể nhận lỗi trước khi JVM cấp `Instrumentation`.

### 6.3. Vì sao dùng `getAllLoadedClasses()`?

Đề bài yêu cầu **biến đổi class đã nạp**. `Class.forName("demo.lab.TargetLogic")` từ agent có thể vô tình load class lần đầu hoặc chọn context loader không đúng, khiến bài test không còn chứng minh “already loaded”.

Thay vào đó, ta liệt kê `Class<?>` đã tồn tại và lọc:

- Binary name phải là `demo.lab.TargetLogic`.
- Defining loader phải đúng `ClassLoader.getSystemClassLoader()` trong lab.
- `isModifiableClass(target)` phải true trước khi yêu cầu retransform.

Trong JVM có plugin/custom loaders, cùng binary name có thể do nhiều defining loaders tạo nên các runtime classes khác nhau. Không tự động chọn class đầu tiên chỉ theo tên. Lab cố ý chỉ dùng system loader để điều kiện rõ ràng.

### 6.4. Hai checks capability riêng biệt

~~~java
inst.isRetransformClassesSupported()
inst.isModifiableClass(target)
~~~

`isRetransformClassesSupported` nói JVM/configuration/manifest có hỗ trợ retransform không. `isModifiableClass` nói class cụ thể có được sửa không. Không suy cái thứ hai từ cái thứ nhất. Class nguyên thủy/array không thể là target modifiable như class nghiệp vụ thông thường.

**Manifest** cần `Can-Retransform-Classes: true` và JVM còn phải thực sự hỗ trợ. `addTransformer(transformer, true)` có thể ném `UnsupportedOperationException` khi thiếu capability.

### 6.5. Vì sao add transformer với `true` và rồi mới retransform?

Nếu chỉ gọi `addTransformer(...)` sau khi `TargetLogic` đã nạp, callback không tự chạy lại trên class cũ. Lệnh `retransformClasses(target)` là **trigger bắt buộc** cho thí nghiệm.

`canRetransform=true` đánh dấu transformer có thể được gọi lại khi retransform. Một transformer được thêm bằng overload một tham số hoặc `false` không nhận callback retransform theo cơ chế capable; kết quả transform cũ của non-capable transformers có thể được JVM tái dùng, theo hợp đồng Java Instrumentation.

Trong lab, thứ tự là:

~~~text
get target Class<?> đã loaded
    |
check capability và modifiable
    |
addTransformer(transformer, true)
    |
retransformClasses(target)
    |
JVM gọi transformer trên target cũ
    |
return byte[] thay đổi
    |
VM verify/install definition
    |
removeTransformer(transformer)
~~~

### 6.6. Input của `ClassFileTransformer.transform`

Overload sáu tham số ở Java 17:

~~~java
byte[] transform(Module module, ClassLoader loader, String className,
                 Class<?> classBeingRedefined, ProtectionDomain domain,
                 byte[] classfileBuffer);
~~~

Ý nghĩa trong thí nghiệm:

- `className` là **internal name** `demo/lab/TargetLogic`, khác binary name có dấu chấm.
- `classBeingRedefined` **không null** ở callback retransform lớp đã load.
- `loader` là loader của class, ở đây system loader.
- `input` là bytes JVM đưa vào transformer **tại vị trí trong pipeline**, không luôn byte-for-byte giống file trên disk.
- Trả `null` nghĩa là không thay đổi class bytes ở callback này.
- Trả mảng `byte[]` mới cho biết transformer cung cấp definition thay thế; JVM còn phải kiểm tra tính hợp lệ.
- Không được giả định buffer đầu vào có thể bị sửa tùy ý in-place. Code dùng `input.clone()`.

Không gọi method của target trong transformer để “kiểm chứng trực tiếp”: class loading/transform callbacks có thể reentrant. Lab dùng một phép sửa constant pool nhỏ, không network I/O hoặc logging phức tạp trong callback.

### 6.7. Bộ sửa constant pool hẹp được giới hạn thế nào?

Code:

1. Kiểm tra header classfile magic `CAFEBABE`.
2. Đọc `constant_pool_count` kiểu `u2` big-endian.
3. Duyệt một số tags classfile Java 17 theo độ dài đã định; `CONSTANT_Long`/`Double` chiếm hai slots.
4. Chỉ sửa entry `CONSTANT_Utf8` dài bốn byte chứa ASCII `COLD`; thay bằng bốn byte `WARM`.
5. Đòi đúng **một entry** được sửa; nếu thiếu hoặc trùng, trả `null`.
6. Không đổi method descriptors, branch offsets, StackMapTable, số methods/fields, superclass hoặc bytes của bất kỳ class khác.

Đây là kỹ thuật **minh họa**, không phải classfile parser đầy đủ. Để chèn invocation hooks/branches, thay control flow, tính StackMapTable hoặc xử lý mọi classfile hợp lệ, dùng ASM, Byte Buddy hay JDK Class-File API phù hợp phiên bản. Cần kiểm thử classfile validity và verifier. Không vá bừa `CONSTANT_Utf8` của class không do bạn kiểm soát: một entry có thể được nhiều thành phần trong classfile tham chiếu.

### 6.8. Vai trò của `patched` và `removeTransformer`

`volatile boolean patched` cho biết callback đã thực sự tạo output không null. Nó giúp agent từ chối báo `agent=retransformed` nếu không hề thay target. Tuy nhiên flag này **không đủ** chứng minh correctness: chỉ khi `retransformClasses` hoàn tất và target quan sát WARM mới có đủ bằng chứng lab.

`removeTransformer(transformer)` chạy ở `finally`, tránh để callback debug tác động về sau. **Gỡ transformer không undo class definition đã được cài**. Existing class và instances vẫn tồn tại; muốn rollback phải thiết kế một lần chuyển đổi khác hoặc restart có kiểm soát.

Theo Javadoc, do class loading đa luồng, một transformer vừa bị remove vẫn có thể nhận một callback đã được kích hoạt gần thời điểm gỡ. Đây không phải global barrier đảm bảo không callback concurrent.

## 7. Controller dùng `jdk.attach`

### 7.1. `src/control/demo/attach/Attacher.java`

~~~java
package demo.attach;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class Attacher {
    private Attacher() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: Attacher <pid> <agent.jar>");
        }
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(Path.of(args[1]).toAbsolutePath().toString(), "");
        } finally {
            vm.detach();
        }
        System.out.println("attach=done");
    }
}
~~~

Controller là process Java **riêng**, không thể gọi `Instrumentation.retransformClasses` trực tiếp từ code này. Nó chỉ có `VirtualMachine` handle đến target.

- `VirtualMachine.attach(args[0])` thiết lập kết nối tới target PID.
- `vm.loadAgent(path, "")` tải agent JAR vào **target** và chờ `agentmain` hoàn tất theo hợp đồng Attach API.
- `Path.toAbsolutePath()` hạn chế lỗi do working directory controller khác target. **Đường dẫn phải tồn tại và đọc được từ filesystem của target JVM**; trong container mount khác, absolute path từ controller có thể không hợp lệ ở target.
- `vm.detach()` trong `finally` bảo đảm đóng phiên kể cả `loadAgent` lỗi.
- `attach=done` là log của **controller**, không phải target; không suy từ đó rằng user method đã đổi nếu chưa quan sát target.

### 7.2. Self-attach và API scope

`VirtualMachine.attach` có thể ném `AttachNotSupportedException` hoặc `IOException` khi quyền/namespace/JVM không phù hợp. Không đặt giả định có thể attach mọi Java PID. Controller dùng `jdk.attach` và chạy với JDK đủ module; agent chạy qua `java.instrument` bên target. Đây là hai bộ API và hai cơ chế bảo mật khác nhau.

## 8. Manifest cho dynamic Java agent

Tạo `AGENT.MF` (main section, kết thúc bằng newline):

~~~text
Manifest-Version: 1.0
Agent-Class: demo.attach.AttachAgent
Can-Retransform-Classes: true

~~~

**Ba thuộc tính quan trọng:**

- `Manifest-Version`: định dạng manifest.
- `Agent-Class`: class có `agentmain(String, Instrumentation)` để nạp động.
- `Can-Retransform-Classes: true`: yêu cầu capability retransformation cho agent JAR.

Không chỉ viết `Premain-Class`: đó là entry point của startup agent. Bài này dùng attach sau khi target chạy, nên JVM cần `Agent-Class`. Cũng không cần `Can-Redefine-Classes` vì không gọi `redefineClasses`.

Nếu manifest sai, không suy nguyên nhân từ trạng thái method; xem controller exception, target logs và nội dung JAR trước.

## 9. Build đủ bốn source files với JDK 17+

### 9.1. Tạo output directories

Trong thư mục gốc `attach-retransform-lab`:

Bash/Linux/macOS:

~~~bash
mkdir -p out/target out/agent out/control
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/target,out/agent,out/control | Out-Null
~~~

### 9.2. Biên dịch JVM đích

~~~bash
javac --release 17 -d out/target src/target/demo/lab/TargetLogic.java src/target/demo/lab/TargetApp.java
~~~

Đây là target classes; không cần agent hoặc controller trên compile-time classpath của target.

### 9.3. Biên dịch agent

~~~bash
javac --release 17 -d out/agent src/agent/demo/attach/AttachAgent.java
~~~

`java.lang.instrument` là Java API có từ lâu; source được biên dịch với target `--release 17` để không phụ thuộc những API mới hơn.

### 9.4. Biên dịch controller có module `jdk.attach`

~~~bash
javac --release 17 --add-modules jdk.attach -d out/control src/control/demo/attach/Attacher.java
~~~

Khi chạy controller cũng chỉ định `--add-modules jdk.attach`. Nếu JDK runtime image không chứa module, phải dùng JDK phù hợp; không dùng reflection để vượt module access.

### 9.5. Đóng agent JAR

~~~bash
jar cfm out/attach-agent.jar AGENT.MF -C out/agent .
~~~

Có thể kiểm tra nội dung:

~~~bash
jar tf out/attach-agent.jar
~~~

JAR cần chứa `META-INF/MANIFEST.MF`, `demo/attach/AttachAgent.class` và nested `AttachAgent$PatchTransformer.class`. Chú ý agent JAR **không** chứa class `TargetLogic`; target JVM đã có class này từ `out/target`.

Các lệnh đã được thực sự biên dịch trên JDK thử nghiệm với `javac --release 17` và `javac --release 17 --add-modules jdk.attach`, sau đó chạy thành công trên JDK 24.

## 10. Chạy thực nghiệm qua hai terminal

### 10.1. Terminal 1 — start target JVM

Từ root lab, đảm bảo file `stop.flag` **chưa tồn tại**. Trên Bash hoặc PowerShell:

~~~bash
java -cp out/target demo.lab.TargetApp stop.flag
~~~

Bạn sẽ thấy dạng:

~~~text
pid=12345
state=COLD
~~~

`12345` là PID ví dụ. Hãy copy **PID thực mà JVM in**; không lấy nguyên số từ README.

Giữ Terminal 1 mở; target đang gọi `TargetLogic.state()`. Nếu target đã in `target=done` trước khi bạn attach, cần chạy lại target (và bảo đảm stop.flag không còn) vì PID cũ đã thoát.

### 10.2. Terminal 2 — attach bằng JVM controller

Thay `12345` bằng PID thật:

~~~bash
java --add-modules jdk.attach -cp out/control demo.attach.Attacher 12345 out/attach-agent.jar
~~~

Câu lệnh tương tự trên Windows PowerShell:

~~~powershell
java --add-modules jdk.attach -cp out/control demo.attach.Attacher 12345 out/attach-agent.jar
~~~

Nếu mọi điều kiện được đáp ứng, controller in:

~~~text
attach=done
~~~

Ở **Terminal 1**, JVM target sẽ có những dòng quan trọng:

~~~text
state=WARM
agent=retransformed
~~~

**Thứ tự có thể đảo.** `retransformClasses` cài definition mới trước khi `agentmain` in thông báo hoàn thành; target thread có thể nhận WARM và in log trước agent thread. Không dựa vào một thứ tự tuyệt đối giữa hai threads.

### 10.3. Dừng target gọn gàng

Sau khi thấy `state=WARM`, bạn có thể để target hết vòng lặp hoặc tạo stop flag để nó kết thúc sớm:

Bash:

~~~bash
touch stop.flag
~~~

PowerShell:

~~~powershell
New-Item -ItemType File -Path stop.flag -Force | Out-Null
~~~

Target in `target=done`. Đây là cơ chế của **TargetApp** lab, không phải method của Attach API. Trước khi chạy một target JVM mới, xử lý stop flag cũ.

### 10.4. Kết quả đã được kiểm thử thực tế

Một lượt thử Java 17-target đã chạy **hai tiến trình JVM riêng**, dùng PID thực tế, `Attacher` nạp agent vào target, và target tự ghi:

~~~text
pid=<PID thực tế>
state=COLD
state=WARM
agent=retransformed
target=done
~~~

Controller riêng in:

~~~text
attach=done
~~~

Các chuỗi `<PID thực tế>` là ký hiệu mô tả thay cho số PID biến đổi theo lần chạy. Khi chạy thật, `ProcessHandle.current().pid()` in số nguyên cụ thể.

Target stderr trên JDK 24 có cảnh báo dynamic agent loading của JEP 451; **đó không phải lỗi** trong lượt thử này. Chương trình chuyển từ COLD sang WARM mà **không restart** và không thay file class trên disk.

## 11. Hiểu sâu `retransformClasses`

### 11.1. Nguồn bytes và pipeline

Theo `Instrumentation`, retransformation chạy lại transformation process từ **initial classfile bytes** của class, hoặc nguồn cơ sở sau một lần redefine tương ứng. Các bytes JVM dùng có thể khác về bố cục constant pool/attributes so với file từng đưa vào `defineClass` nhưng tương đương theo hợp đồng.

Với một class có nhiều transformers:

~~~text
JVM baseline bytes
    |
    v
Transformers canRetransform=false:
    kết quả transform trước đó được tái sử dụng, không gọi lại callback
    |
    v
Transformers canRetransform=true:
    callback transform được gọi lại với input phù hợp
    |
    v
JVM verify và install class definition mới
~~~

**`classfileBuffer` trong transformer của bạn là input ở vị trí pipeline đó**, không nhất thiết trùng file `.class` trong JAR gốc, và output của bạn chưa chắc là output cuối nếu còn transformer khác chạy sau.

### 11.2. Vì sao `addTransformer` đơn độc không đủ?

Nếu class đã load trước khi agent attach, việc thêm transformer không tự quay lại định nghĩa cũ. Không nhất thiết có một lần load mới của chính class đó. `retransformClasses(target)` là yêu cầu chủ động để JVM gọi lại capable transformer và cài definition mới.

### 11.3. So sánh với `redefineClasses`

| Đặc điểm | `retransformClasses` | `redefineClasses` |
|---|---|---|
| Đầu vào | `Class<?>` đã nạp, JVM quản lý baseline/pipeline | `ClassDefinition` với bytes classfile do caller cấp |
| Mục đích chính | Instrument/reinstrument class đã nạp | Thay definition bằng nguồn bytes riêng |
| Có sử dụng transformers | Có, theo capable/incapable pipeline | Có pipeline tương ứng |
| Bản thân API có thêm field/method tùy ý? | Không | Không |
| Có chạy lại static initializer? | Không | Không |
| Có thay existing object state? | Không | Không |
| Active method frames có tự chuyển giữa chừng? | Không | Không |

Nếu cần đưa classfile bytes hoàn chỉnh do một compiler khác tạo ra, `redefineClasses` có thể phù hợp hơn; nếu muốn dùng transformer trên nguồn bytes của class đang chạy, `retransformClasses` thường phù hợp. Cả hai chịu giới hạn JVM TI/class schema; không gọi một API là “mạnh hơn mọi mặt” so với API kia.

### 11.4. Giới hạn class schema

Không giả định retransformation được phép:

- Thêm/xóa fields hoặc methods.
- Đổi chữ ký method, modifiers, hierarchy, interface relationships hoặc schema bị VM cấm.
- Thay class identity, defining loader hoặc module của class đã định nghĩa.
- Chạy lại `<clinit>` hoặc reset static fields.
- Biến existing instances thành object mới.
- Làm method đang chạy nhảy sang bytecode mới giữa active stack frame.

Đó là lý do ví dụ chỉ thay UTF8 literal đồng độ dài trong constant pool, giữ nguyên method signature, fields và cấu trúc control flow. Các thay đổi method body phức tạp cần bytecode writer và tests đầy đủ.

### 11.5. Active frames và điểm quan sát

Nếu một thread đang ở giữa method được retransform, active frame ấy có thể tiếp tục bytecode của định nghĩa cũ. **Invocation mới** sẽ dùng phiên bản mới khi JVM đã cài definition. Target lab liên tục gọi method ngắn từ một vòng lặp khác nên sẽ sớm quan sát WARM.

Thứ tự log giữa target thread và agent thread có thể dao động; chỉ cần giữ chứng cứ trước/sau trên cùng target process.

### 11.6. Static fields không reset

Nếu `TargetLogic` có static counter hay cached object, `retransformClasses` không tự reset chúng. Class initializer không chạy lại và existing instances không tự bị thay. Đừng hiểu retransform là restart một class ở runtime.

### 11.7. Gỡ transformer không rollback

`inst.removeTransformer(transformer)` chỉ gỡ callback. Class definition đã được VM cài đặt vẫn ở trạng thái sau retransform. Nếu cần phục hồi trạng thái trước đó, phải thiết kế rollback khác, hoặc khởi động lại tiến trình với definition gốc theo policy.

Nếu attach lần nữa, input classfile và lịch sử transformers/redefine có thể khác kỳ vọng. Lab **không cam kết** attach hai lần có cùng behavior. Để thử lại một cách đơn giản, dùng **JVM target mới với PID mới**.

## 12. Đọc bytecode và xác minh runtime

### 12.1. `javap` chỉ đọc file trên disk

Có thể kiểm tra classfile do compiler tạo:

~~~bash
javap -c -v -classpath out/target demo.lab.TargetLogic
~~~

Một phần output dạng minh họa:

~~~text
#7 = String             #8  // COLD
#8 = Utf8                   COLD

public static java.lang.String state();
  Code:
     0: ldc           #7      // String COLD
     2: areturn
~~~

Số `#7/#8` là ví dụ tùy compiler. Sau khi attach thành công, lệnh `javap` **trên `out/target` vẫn có thể in COLD**, vì nó đọc file classfile xây dựng ban đầu. `retransformClasses` thay runtime definition, **không ghi ngược file classfile lên ổ đĩa**.

Để quan sát bytes đúng chỗ trong transformer, có thể thiết kế một cơ chế capture có giới hạn, lưu input và returned bytes cùng classloader/phase metadata rồi đọc từng file bằng `javap -c -v`. Nhưng một snapshot ở giữa pipeline chưa chắc là JVM-installed final bytes nếu có transformer sau.

### 12.2. Đừng nhầm behavior test với transformer debug

Một lượt **PASS** cần cả:

1. Agent/controller logs phù hợp.
2. `retransformClasses` trả về không lỗi.
3. Target method in WARM từ invocation mới.
4. PID vẫn là tiến trình ban đầu.
5. Functional tests khác vẫn đúng nếu không phải demo đơn giản.

`javap` trên file gốc là công cụ giải thích classfile, **không thay được việc quan sát JVM runtime**.

## 13. Những nguyên nhân attach/retransform thất bại thường gặp

| Triệu chứng | Giả thuyết chính | Hành động chẩn đoán |
|---|---|---|
| `AttachNotSupportedException` | JVM đích không tương thích Attach Provider, sai namespace hoặc mechanism bị chặn | Xem JDK, PID, quyền process, OS/container policy |
| `IOException` khi attach | Target đã kết thúc, thiếu quyền, attach socket không truy cập được | Xác minh process còn sống và cùng security context |
| `Can not attach to current VM` | Self-attach hoặc PID chỉ vào controller | Chạy hai JVM, lấy PID từ TargetApp |
| `AgentLoadException` | JAR sai path hoặc policy load cấm | Path từ **target**, manifest và JVM dynamic agent policy |
| `AgentInitializationException` | `agentmain` ném lỗi | Đọc stderr target và cause đầu tiên |
| `isRetransformClassesSupported() == false` | Manifest thiếu capability hoặc VM không hỗ trợ | Kiểm tra `Can-Retransform-Classes: true` và config |
| `Target not found/modifiable` | Class chưa load, loader filter sai, class không modifiable | Xem `getAllLoadedClasses` và defining loader |
| `UnmodifiableClassException` | Class không thể sửa | `isModifiableClass` và class category |
| `UnsupportedOperationException` | Retransform capability không được phép hoặc đổi schema bị cấm | Xem VM/JVMTI constraints |
| `ClassFormatError`, `VerifyError` | Transformer tạo classfile không hợp lệ | Dùng parser/writer đầy đủ, kiểm tra output bytes/frames |
| `Target bytes not patched` | Không thấy entry UTF8 COLD hoặc transformer filter không khớp | Xem classfile gốc, internal name, phase, loader |
| Target vẫn in COLD | Attach vào JVM khác, class chưa đổi hoặc target kết thúc | Kiểm PID và log controller/target |
| Target WARM nhưng log agent sau | Thread scheduling bình thường | Không giả định thứ tự stdout giữa threads |
| `javap` trên disk vẫn hiện COLD | Build artifact không được ghi lại khi retransform | Chỉ hiểu nó là bản compile-time |
| Dynamic agent warning | JDK 21+ policy warning | Phân biệt warning và failure; đọc JVM flags/release notes |

### 13.1. Đúng process là điều quan trọng nhất

Không chọn PID theo tên “java” chung chung nếu máy có nhiều JVM. Dùng `pid=...` từ `ProcessHandle.current().pid()` của target hoặc công cụ phù hợp như `jps -l`, `jcmd -l` và xác minh class/main process.

Controller loadAgent không nhất thiết in mọi exception ở terminal của mình. `agentmain` chạy trong target, nên cần xem **target stdout/stderr** để biết trạng thái retransform và nguyên nhân lỗi.

### 13.2. Loader và module

Cùng tên `demo.lab.TargetLogic` được nạp bởi hai loaders khác nhau là hai `Class<?>` khác nhau. Trong app server, plugin hoặc OSGi, đừng chỉ lọc theo tên rồi chọn bừa class. Bài lab dùng system loader; sản phẩm cần nhận dạng defining loader, module và phiên bản class đúng mục tiêu.

Nếu transformer chèn lời gọi helper, helper cũng phải visible với target loader/module. Lỗi `NoClassDefFoundError` có thể xuất hiện sau một retransform nếu helper không được JVM tìm thấy; việc transformer trả bytes không giải quyết visibility tự động.

### 13.3. Concurrency và trách nhiệm vận hành

Một JVM đa luồng có thể có active frames vẫn chạy code cũ trong khi invocation mới dùng code mới; behavior trong một khoảng chuyển đổi có thể không đồng nhất. Đừng coi retransform là transaction nghiệp vụ có rollback toàn hệ thống. Cần thử exception paths, side effects, lock/monitor semantics, module graph và mô hình quan sát.

## 14. Ma trận kiểm thử bổ sung

| Case | Thao tác | Kỳ vọng |
|---|---|---|
| Baseline | Chạy target, không attach | Chỉ thấy `state=COLD` |
| Chuẩn | Target in COLD, controller attach đúng PID | Target chuyển WARM; attach done |
| PID cũ | Attach process đã kết thúc | Controller fail, không ảnh hưởng JVM khác |
| JAR không tồn tại | `loadAgent` path sai | Lỗi nạp agent |
| Manifest sai | Thiếu `Agent-Class` | Không chạy `agentmain` |
| Capability false | Bỏ `Can-Retransform-Classes` | Agent từ chối vì unsupported |
| Target chưa load | Attach trước lần gọi `state()` | `getAllLoadedClasses` không tìm class |
| Chọn loader khác | Dùng custom class loader | Filter của lab không chọn |
| Target unmodifiable | Chọn class không modifiable | Gate từ chối |
| Literal đã đổi | Rebuild class trả chuỗi không phải COLD | Transformer trả null, agent báo không patch |
| Invalid classfile | Test writer lỗi riêng trong sandbox | VM từ chối bằng lỗi format/verify |
| Active invocation | Retransform trong method dài | Frame cũ có thể tiếp tục code cũ |
| Attach lần hai | Dùng target đã WARM | Không mặc định PASS; cần thiết kế idempotency |
| Disable dynamic loading | JVM policy chặn | Attach/loadAgent fail có kiểm soát |

Không fault-inject bằng cách tắt/quấy rối JVM dùng chung. Các trường hợp âm tính phải chạy trong môi trường thí nghiệm được cấp quyền.

## 15. Checklist để thực nghiệm có thể tái lập

**Trước khi attach**

- [ ] Đã chạy `java -version` và `javac -version`, xác nhận JDK có `jdk.attach`.
- [ ] PID lấy từ JVM target mới, không copy từ bản hướng dẫn.
- [ ] Target đã in COLD và chưa tự thoát.
- [ ] Manifest có `Agent-Class` và `Can-Retransform-Classes: true`.
- [ ] JAR có class agent và nested transformer.
- [ ] Path agent JAR được target JVM truy cập, không chỉ controller.
- [ ] Người thực nghiệm có quyền attach theo OS/JVM/security policy.
- [ ] Không có stop flag từ lần trước.

**Trong lúc attach/retransform**

- [ ] Controller attach và detach trong `finally`.
- [ ] Agent kiểm tra cả JVM retransformation support và target modifiability.
- [ ] Target được chọn bằng class name **và** defining loader.
- [ ] Transformer đăng ký `canRetransform=true`.
- [ ] Có lời gọi `retransformClasses(target)` thực sự.
- [ ] Transformer không sửa `classfileBuffer` tại chỗ và không chạm lớp khác.
- [ ] Không thay class schema/method signature.
- [ ] Agent gỡ transformer dù thành công hay lỗi.
- [ ] Không nuốt exception rồi báo thành công.

**Sau khi attach**

- [ ] Target chuyển từ COLD sang WARM trên **cùng một PID**.
- [ ] Controller in `attach=done` không kèm lỗi loadAgent.
- [ ] Hiểu dynamic agent warnings là warnings, không tự suy failure.
- [ ] Phân biệt build artifact ở disk và runtime definition.
- [ ] Không coi `removeTransformer` là rollback.
- [ ] Test hành vi nghiệp vụ ngoài method demo nếu dùng trong hệ thống thực.
- [ ] Lưu cách tái hiện: JDK/version, manifest, commands, PID và logs đã được ẩn thông tin nhạy cảm.

## 16. Câu hỏi ôn tập (kèm đáp án)

**1.** Vì sao `TargetLogic` phải in COLD trước khi attach?

> Vì ta cần chứng minh lớp đã được nạp và sử dụng **trước** khi agent được đưa vào. Đây là thí nghiệm retransformation, không phải class-load transform.

**2.** `Agent-Class` khác `Premain-Class` thế nào?

> `Agent-Class` chọn entry point `agentmain` cho dynamic attach; `Premain-Class` chọn `premain` ở startup.

**3.** Module nào dùng ở JVM controller?

> `jdk.attach`, cung cấp `com.sun.tools.attach.VirtualMachine`. `Instrumentation` thuộc module `java.instrument` và được cấp trong target agent.

**4.** Vì sao phải dùng hai JVM?

> Giúp chọn một PID target độc lập và không dựa vào chính sách self-attach của JVM.

**5.** Vì sao chỉ gọi `addTransformer` chưa đủ?

> Vì target class đã load trước đó. Cần `retransformClasses` để yêu cầu capable transformer chạy lại.

**6.** `Can-Retransform-Classes: true` có đủ không?

> Không. JVM còn phải hỗ trợ retransformation và class cụ thể phải modifiable.

**7.** `getAllLoadedClasses()` có ưu điểm gì so với tự load bằng `Class.forName`?

> Nó xác minh class đã tồn tại trong VM, cho phép chọn `Class<?>` cùng loader chính xác, không chủ động kích hoạt lần load đầu.

**8.** Vì sao `transform` trả một byte array mới thay vì mutate input?

> Hợp đồng transformer yêu cầu giữ mảng input không bị sửa tại chỗ; output là một definition byte[] mới hoặc `null` khi không thay.

**9.** Trong demo, bytes đổi từ COLD sang WARM ở đâu?

> Trong một `CONSTANT_Utf8` dài bốn byte thuộc constant pool của class target đã nạp; method bytecode dùng cùng constant reference.

**10.** Gỡ transformer có trả lại COLD không?

> Không. Definition WARM đã cài trong JVM vẫn có hiệu lực; remove chỉ gỡ callback.

**11.** Khi class đang có active frames thì sao?

> Active frames có thể tiếp tục dùng code cũ; invocation mới sẽ dùng definition mới khi JVM cài đặt.

**12.** Vì sao `javap` trên `out/target` sau attach vẫn có thể in COLD?

> Vì `javap` đọc classfile build artifact trên disk, trong khi retransformation thay definition trong JVM đang chạy.

**13.** Nếu controller in attach done, có chắc target đã đổi không?

> Chưa. Cần log/bằng chứng `retransformClasses` và quan sát method mới trả WARM.

**14.** `state=WARM` có thể xuất hiện trước `agent=retransformed` không?

> Có. Các threads có thể chạy xen kẽ sau khi definition mới được cài; không có bảo đảm thứ tự in như vậy.

**15.** Vì sao không dùng constant pool patcher rất ngắn của lab để instrument mọi ứng dụng?

> Nó không xử lý classfile tùy ý, control flow, frames, đổi schema và các bytecode edge cases. Dùng library/classfile API đầy đủ và verifier tests.

## 17. Tài liệu tham khảo

- Java SE 17, `Instrumentation` — `isRetransformClassesSupported`, `isModifiableClass`, `getAllLoadedClasses`, `addTransformer`, `retransformClasses`, active stack frames và class schema: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer` — callback trong quá trình load/redefine/retransform, `canRetransform`, return bytes: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `java.lang.instrument` package — `Agent-Class`, `Can-Retransform-Classes`, `agentmain` và manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `com.sun.tools.attach.VirtualMachine` — `attach`, `loadAgent`, `detach` và các error classes: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- Java SE 17, `jdk.attach` module — Attach API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/module-summary.html
- OpenJDK JEP 451, `Prepare to Disallow the Dynamic Loading of Agents by Default` — policy và warning/VM flags: https://openjdk.org/jeps/451
- Java SE 17, JVM Specification, Chapter 4 — classfile constant pool và tags: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17, `javap` — đọc bytecode từ classpath hoặc classfiles: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
