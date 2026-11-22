# Vai trò của java.lang.instrument, Attach API, Class-File API và JVM TI

## 1. Vì sao cần phân biệt bốn thành phần?

Khi muốn quan sát hoặc thay đổi hành vi của một chương trình Java đang chạy, ta thường gặp bốn tên: `java.lang.instrument`, Attach API, Class-File API và JVM Tool Interface (JVM TI). Chúng nằm ở **những tầng khác nhau của hệ sinh thái công cụ JVM**, nên không thay thế nhau theo quan hệ một–một.

Ví dụ: bạn cần đo thời gian thực thi một phương thức mà không sửa mã nguồn ứng dụng. Một giải pháp có thể dùng Java agent để nhận quyền quan sát quá trình nạp lớp, dùng bộ xử lý class file để thêm mã đo thời gian vào bytecode, và tùy cách triển khai mà đưa agent vào JVM từ lúc khởi động hoặc gắn vào tiến trình đã chạy. Nếu cần dữ liệu ở tầng máy ảo như sự kiện thread, heap và breakpoint, công cụ có thể dùng JVM TI.

**Mục tiêu bài học:** sau khi học, bạn xác định được mỗi API chịu trách nhiệm gì, lúc nào được kích hoạt, dữ liệu nào đi qua nó, giới hạn khi sửa lớp đã nạp, và cách lựa chọn đúng tầng cho agent, profiler, debugger hoặc công cụ xử lý bytecode.

## 2. Bản đồ kiến trúc: mỗi thành phần làm một việc

| Thành phần | Tầng / mô-đun | Vai trò chính | Thời điểm sử dụng | Điều không tự làm |
|---|---|---|---|---|
| `java.lang.instrument` | Java API trong mô-đun `java.instrument` | Cấp `Instrumentation` cho Java agent; đăng ký `ClassFileTransformer`, quan sát/biến đổi class bytes khi nạp, redefine hoặc retransform | Agent khởi động bằng `-javaagent` hoặc được nạp động | Không tự phân tích cấu trúc bytecode ở mức lớp/phương thức; không tự tìm và kết nối PID |
| Attach API | JDK-specific API trong `jdk.attach`, gói `com.sun.tools.attach` | Từ một tiến trình công cụ kết nối tới JVM mục tiêu, tải agent Java hoặc native vào JVM đó | Khi JVM đã chạy và hỗ trợ attach | Không tự sửa bytecode hoặc cung cấp `Instrumentation` cho tiến trình gọi |
| Class-File API | `java.lang.classfile` trong `java.base`, chuẩn hóa từ JDK 24 (JEP 484) | Đọc, tạo, xác minh và biến đổi định dạng tệp `.class` / mảng byte class | Offline hoặc bên trong một transformer/agent | Không tự attach, nạp agent, định nghĩa lại lớp đang chạy hay tạo sự kiện profiler |
| JVM TI | Native interface theo đặc tả JVM, dùng `jvmti.h` từ C/C++ | Truy vấn và điều khiển trạng thái JVM, đăng ký sự kiện VM/threads/methods, hỗ trợ debugger/profiler | Native agent khởi động hoặc attach nếu VM hỗ trợ | Không cung cấp sẵn mô hình Java cấp cao như Class-File API; không đồng nghĩa với JNI |

Có thể hình dung hai luồng phổ biến:

~~~text
A. Khởi động với Java agent
java -javaagent:agent.jar App
      │
      └─> premain(..., Instrumentation)
              └─> đăng ký ClassFileTransformer
                      └─> JVM chuẩn bị định nghĩa class
                              └─> transform(class bytes)
                                      ├─> null: giữ bytecode hiện tại
                                      └─> byte[] mới: JVM kiểm tra/nạp bytes mới

B. Gắn vào một JVM đang chạy
Tool JVM ──VirtualMachine.attach(pid)──> JVM mục tiêu
         ──loadAgent(agent.jar)───────> agentmain(..., Instrumentation)
                                        └─> đăng ký transformer / xử lý lớp đã nạp

C. Native agent
java -agentpath:/path/libtool.so App
      └─> Agent_OnLoad(JavaVM*, ...)
              └─> lấy jvmtiEnv, xin capabilities, đăng ký event callbacks
                      └─> JVM gửi sự kiện tương ứng
~~~

Trong sơ đồ trên, **Class-File API có thể là bộ máy xử lý `byte[]` nằm bên trong `transform(...)`**, hoặc được gọi bởi công cụ build mà không có agent nào. **Attach API là con đường đưa agent vào tiến trình**, không phải bộ máy biến đổi bytecode. **JVM TI là giao diện native sát máy ảo**, có thể cấp khả năng mà API Java thuần không có.

## 3. `java.lang.instrument`: điểm vào của Java agent

### 3.1. Hai kiểu kích hoạt và hai entry point

- **Startup agent:** chạy `java -javaagent:observer-agent.jar App`. Manifest JAR khai báo `Premain-Class`. JVM gọi `public static void premain(String agentArgs, Instrumentation inst)` **trước `App.main`**. Cách này phù hợp khi cần quan sát cả các lớp được nạp rất sớm và có thể cấu hình JVM ngay từ đầu.
- **Dynamic agent:** khi JVM hỗ trợ nạp agent vào tiến trình đang chạy, JAR khai báo `Agent-Class` và định nghĩa `public static void agentmain(String agentArgs, Instrumentation inst)`. Cách tải thường qua Attach API hoặc công cụ phù hợp. Những lớp đã nạp từ trước **không tự động chạy lại transformer** chỉ vì agent mới được gắn.
- Manifest có thể khai báo cả `Premain-Class` và `Agent-Class` cho một JAR. Phần `agentArgs` là một chuỗi option thô; agent tự parse.
- `Instrumentation` do JVM cung cấp cho agent; ứng dụng thông thường không khởi tạo `new Instrumentation()`. Agent làm việc **trong cùng JVM** với ứng dụng, vì vậy lỗi hoặc tác vụ quá nặng của agent có thể ảnh hưởng ứng dụng.

Các phương thức đáng nhớ:

| Phương thức | Ý nghĩa / điều kiện |
|---|---|
| `addTransformer(transformer)` | Đăng ký cho các class load/redefine tiếp theo; mặc định transformer không có khả năng retransform |
| `addTransformer(transformer, true)` | Transformer được gọi lại khi có retransformation; chỉ dùng nếu capability được hỗ trợ |
| `getAllLoadedClasses()` | Liệt kê những `Class<?>` đã nạp, không mặc nhiên thay đổi chúng |
| `isRetransformClassesSupported()` và `isModifiableClass(c)` | Kiểm tra khả năng thực tế trước khi tác động lớp đã nạp |
| `retransformClasses(c)` | Yêu cầu VM chạy lại chuỗi biến đổi hợp lệ cho một lớp đã nạp |
| `redefineClasses(ClassDefinition...)` | Cung cấp trực tiếp định nghĩa class mới; cũng chịu ràng buộc của VM |
| `removeTransformer(transformer)` | Dừng đăng ký để áp dụng cho những lần biến đổi về sau; callback đang chạy có thể vẫn hoàn tất |

**Phân biệt ba thời điểm:** lần nạp class đầu tiên (class load), yêu cầu VM định nghĩa lại từ class bytes mới (redefine), và yêu cầu biến đổi lại class đã nạp (retransform). Khi nạp lần đầu, `ClassFileTransformer` nhận tên lớp dạng nội bộ như `com/example/OrderService`, `classBeingRedefined` thường là `null`, cùng mảng byte class ban đầu. Trả về `null` nghĩa là **không sửa**, trả về `byte[]` hợp lệ nghĩa là đề xuất class bytes thay thế. JVM vẫn kiểm tra định dạng và xác minh mã.

### 3.2. Ví dụ Java 17+: một JAR dùng cho startup và attach

Tạo ba tệp trong cùng một thư mục. Ví dụ cố ý **quan sát mà không sửa bytecode** để nhìn rõ vai trò của API.

Tệp `ObserverAgent.java`:

~~~java
import java.lang.instrument.Instrumentation;

public final class ObserverAgent {
    public static void premain(String options, Instrumentation inst) {
        System.out.println("[agent] premain");
        inst.addTransformer((loader, internalName, redefining, domain, bytes) -> {
            if ("Demo".equals(internalName)) {
                System.out.println("[agent] observed class Demo");
            }
            return null; // Giữ nguyên bytecode; không can thiệp hành vi ứng dụng.
        });
    }

    public static void agentmain(String options, Instrumentation inst) {
        System.out.println("[agent] agentmain");
        boolean demoAlreadyLoaded = java.util.Arrays
                .stream(inst.getAllLoadedClasses())
                .anyMatch(type -> "Demo".equals(type.getName()));
        System.out.println("[agent] Demo already loaded: " + demoAlreadyLoaded);
    }
}
~~~

Tệp `Demo.java`:

~~~java
public final class Demo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("[app] pid=" + ProcessHandle.current().pid());
        Thread.sleep(120_000); // Giữ JVM sống để thử Attach API.
    }
}
~~~

Tệp `MANIFEST.MF` (có một dòng trống kết thúc manifest):

~~~text
Manifest-Version: 1.0
Premain-Class: ObserverAgent
Agent-Class: ObserverAgent
Can-Retransform-Classes: true

~~~

Biên dịch và đóng gói bằng JDK 17 trở lên:

~~~bash
javac ObserverAgent.java Demo.java
jar cfm observer-agent.jar MANIFEST.MF ObserverAgent.class
java -javaagent:observer-agent.jar Demo
~~~

Một kết quả **mang tính cấu trúc** của chế độ startup:

~~~text
[agent] premain
[agent] observed class Demo
[app] pid=<PID của tiến trình hiện tại>
~~~

PID là số do hệ điều hành cấp, thay đổi mỗi lần chạy. Callback quan sát `Demo` khi JVM nạp class đó; không có dòng nào chứng minh bytecode đã bị sửa vì transformer trả `null`.

**Điểm cần hiểu:** nếu chỉ đăng ký transformer sau khi `Demo` đã nạp, không có lý do để callback nạp lần đầu xuất hiện lần nữa. Để xem lại class đã nạp, agent cần đăng ký transformer phù hợp, kiểm tra các capability và gọi `retransformClasses` trên đúng class. Đây là thao tác riêng, có thể thất bại và bị giới hạn kiểu thay đổi.

### 3.3. Biến đổi thật khác với quan sát thế nào?

Trong transformer, thay cho `return null`, ta có thể:

1. Kiểm tra tên class, class loader, module và vùng phạm vi được phép; bỏ qua lớp của agent, JDK và thư viện không cần can thiệp.
2. Đọc class bytes bằng Class-File API (JDK 24+) hoặc thư viện bytecode thích hợp với JDK đang dùng; tìm phương thức mục tiêu và xây bytes mới.
3. Trả về mảng byte mới; để JVM verifier kiểm tra; chỉ triển khai khi có kiểm thử compatibility và hiệu năng.
4. Nếu mục tiêu đã nạp, cân nhắc `retransformClasses` hoặc `redefineClasses` theo capability; **không mặc nhiên có thể thêm/xóa field, method, đổi superclass, hoặc đổi chữ ký phương thức** của class đang chạy.

Cần xử lý đúng constant pool, frame/`StackMapTable`, luồng ngoại lệ, stack depth và tính hợp lệ của chỉ thị. Thao tác bytecode sai có thể dẫn tới `VerifyError`, `ClassFormatError` hoặc lỗi khi load/link class. Việc agent được gắn thành công **không bảo đảm** class bytes mới là hợp lệ.

## 4. Attach API: kết nối tới tiến trình và yêu cầu nạp agent

Attach API nằm trong mô-đun JDK `jdk.attach`, gói `com.sun.tools.attach`. Phía **công cụ ngoài tiến trình mục tiêu** thường thực hiện:

1. Xác định JVM mục tiêu (thường qua PID, `VirtualMachine.list()` hoặc công cụ OS/JDK).
2. `VirtualMachine.attach(pid)` để tạo phiên kết nối, phụ thuộc hỗ trợ và quyền của JVM/OS.
3. `vm.loadAgent("/absolute/path/agent.jar", options)` để yêu cầu JVM mục tiêu nạp **Java agent**, gọi `agentmain` tại **JVM mục tiêu**.
4. `vm.detach()` để kết thúc kết nối điều khiển. `detach()` **không tự gỡ agent hoặc đảo ngược thay đổi bytecode**.

Các phương thức `loadAgentLibrary` và `loadAgentPath` phục vụ **native agent**; chúng không giống `loadAgent` cho agent JAR. Đường dẫn JAR trong `loadAgent` được diễn giải ở môi trường filesystem mà **JVM mục tiêu** nhìn thấy, điều quan trọng khi hai phía ở container/namespaces khác nhau.

Thêm tệp `AttachTool.java` vào ví dụ trên:

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java AttachTool <pid> <agent-jar>");
        }

        String jarPath = Path.of(args[1]).toAbsolutePath().toString();
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(jarPath, "from=attach");
        } finally {
            vm.detach();
        }
        System.out.println("[tool] loadAgent request finished");
    }
}
~~~

Chạy từ **hai terminal** trên JDK có mô-đun `jdk.attach`:

~~~bash
javac --add-modules jdk.attach AttachTool.java
# Terminal 1: chạy ứng dụng, không có -javaagent.
java -XX:+EnableDynamicAgentLoading Demo

# Terminal 2: thay <PID> bằng số Demo vừa in.
java --add-modules jdk.attach AttachTool <PID> observer-agent.jar
~~~

Trên JDK/HotSpot cho phép attach, tại terminal của ứng dụng sẽ xuất hiện:

~~~text
[agent] agentmain
[agent] Demo already loaded: true
~~~

Công cụ kết nối sẽ in `[tool] loadAgent request finished` sau khi lời gọi tải agent hoàn tất. **Không có dòng `[agent] observed class Demo`** trong thử nghiệm attach này: `agentmain` chỉ liệt kê các class đang nạp, không đăng ký transformer và không retransform. Điều đó chứng minh Attach API xử lý **thời điểm triển khai agent**, không tự instrument ứng dụng.

**Giới hạn thực tế:** attach phụ thuộc JVM vendor/implementation, quyền hệ điều hành, cách cô lập container, chính sách bảo mật và bản JDK. Một tiến trình có thể vô hiệu hóa cơ chế attach (ví dụ HotSpot có `-XX:+DisableAttachMechanism`). Self-attach (cùng tiến trình tự gắn chính mình) còn có hạn chế mặc định riêng; ví dụ trên dùng **hai tiến trình**. Không coi `com.sun.tools.attach` là một Java SE API phổ quát có sẵn trong mọi runtime tối giản.

## 5. Class-File API: hiểu và tạo class bytes, không quản lý JVM mục tiêu

`java.lang.classfile` được chuẩn hóa trong **JDK 24** (JEP 484; trước đó từng là preview trong JDK 22 và 23). API thuộc `java.base`, dùng mô hình bất biến/lazy để đọc classfile, biểu diễn class/method/field/attributes, tạo class mới, và transform class bytes. Đây là giải pháp chuẩn cho các thao tác classfile trên JDK hỗ trợ, thay vì dựa trực tiếp vào `jdk.internal.org.objectweb.asm` (API nội bộ không được bảo đảm ổn định).

Khái niệm chính:

- `ClassFile.of()` cung cấp bối cảnh parse/build/transform. `ClassFile.parse(byte[])` hoặc `parse(Path)` trả về `ClassModel`.
- `ClassModel` biểu diễn class (tên, fields, methods, attributes, constant pool). `MethodModel` và `CodeModel` giúp đi sâu vào method body và bytecode.
- `ClassFile.build(...)` tạo class bytes; `transformClass(model, transform)` tạo mảng byte đã chỉnh; `verify(...)` kiểm tra một số tính hợp lệ của classfile ở lớp API.
- Model được đọc/làm rõ từng phần (lazy), nên việc parse thành công ban đầu **không bảo đảm** mọi thành phần bị lỗi sẽ chỉ ra ngay; truy cập sâu có thể phát sinh ngoại lệ cho classfile hỏng. Không chia sẻ các model lazy tùy tiện giữa nhiều thread.
- Class-File API **không biết PID, không tự gọi `agentmain`, không tự nạp mã mới vào JVM đang chạy**. Bytes sinh ra vẫn cần một cơ chế sử dụng: lưu ra `.class`, class loader, công cụ build hoặc transformer.

Ví dụ chạy độc lập trên **JDK 24+**; tệp `InspectClassFile.java`:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public final class InspectClassFile {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java InspectClassFile <path-to-class>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        System.out.println("class: " + model.thisClass().asInternalName());
        for (var method : model.methods()) {
            System.out.println("method: " + method.methodName().stringValue());
        }
    }
}
~~~

~~~bash
# Dùng chính Demo.class ở ví dụ trước; yêu cầu JDK 24+.
javac InspectClassFile.java
java InspectClassFile Demo.class
~~~

Với tệp `Demo.class` được `javac` tạo từ ví dụ trên, kết quả:

~~~text
class: Demo
method: <init>
method: main
~~~

`<init>` là constructor mặc định do trình biên dịch tạo, không phải một phương thức Java do bạn khai báo tường minh trong `Demo.java`. Ví dụ chỉ **đọc metadata offline**; không có agent nào được tải, class `Demo` cũng không cần được JVM chạy để tra cứu.

Để ghép Class-File API với `java.lang.instrument`, tư duy là:

~~~text
ClassFileTransformer.transform(..., byte[] original)
       ├─> ClassFile.of().parse(original)
       ├─> chọn các MethodModel / CodeModel cần chỉnh
       ├─> ClassFile.of().transformClass(model, transform)
       └─> return transformedBytes
             └─> JVM verifier -> định nghĩa lại / nạp class
~~~

Sơ đồ là luồng thiết kế, **không phải đoạn Java độc lập có thể copy chạy**. Một bản transform thật phải xây `ClassTransform` phù hợp, bảo toàn bytecode hợp lệ, tránh đụng class đã instrument, và có kiểm thử cho target JDK. **Không dùng Class-File API JDK 24 trong agent yêu cầu chạy trên JDK 17**: lúc đó phải biên dịch mục tiêu tương thích và dùng một thư viện xử lý bytecode tương thích (ví dụ ASM/Byte Buddy) hoặc nâng runtime lên phiên bản hỗ trợ.

## 6. JVM TI: giao diện native dành cho công cụ chuyên sâu

**JVM Tool Interface (JVM TI)** là giao diện C/C++ cho native agent truy cập khả năng quan sát/điều khiển JVM. Agent thường là `.so` trên Linux hoặc `.dll` trên Windows và nằm **trong process JVM**. JVM TI có thể cung cấp sự kiện/phương thức liên quan đến lifecycle, thread, method, breakpoint, exception, heap, class load, GC, tùy JVM và các capability có sẵn.

Đường đi phổ biến:

1. JVM khởi động với `-agentlib:name` hoặc `-agentpath:/absolute/path/to/library` và gọi entry point `Agent_OnLoad`; nếu nạp động được hỗ trợ, JVM gọi `Agent_OnAttach`.
2. Native agent dùng `JavaVM::GetEnv` với `JVMTI_VERSION_*` để nhận `jvmtiEnv*`.
3. Đăng ký event callbacks (`SetEventCallbacks`), bật từng sự kiện bằng `SetEventNotificationMode`; với tính năng yêu cầu quyền đặc biệt, trước đó gọi `AddCapabilities` và kiểm tra kết quả.
4. JVM chủ động gọi callbacks khi sự kiện xảy ra hoặc agent gọi các hàm JVM TI để tra cứu/điều khiển. Chọn sự kiện thật sự cần thiết vì MethodEntry, SingleStep hoặc theo dõi từng allocation có thể tốn chi phí lớn.

**Ví dụ nhỏ để nhận biết API**: native agent C chỉ lắng nghe sự kiện JVM khởi tạo. Tệp `sample_jvmti.c`:

~~~c
#include <jni.h>
#include <jvmti.h>
#include <stdio.h>

static void JNICALL on_vm_init(jvmtiEnv *ti, JNIEnv *jni, jthread thread) {
    puts("[jvmti] VM initialized");
    fflush(stdout);
}

JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM *vm, char *options, void *reserved) {
    jvmtiEnv *ti = NULL;
    if ((*vm)->GetEnv(vm, (void **)&ti, JVMTI_VERSION_1_2) != JNI_OK
            || ti == NULL) {
        return JNI_ERR;
    }

    jvmtiEventCallbacks callbacks = {0};
    callbacks.VMInit = &on_vm_init;
    if ((*ti)->SetEventCallbacks(ti, &callbacks, sizeof(callbacks))
            != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }
    if ((*ti)->SetEventNotificationMode(
            ti, JVMTI_ENABLE, JVMTI_EVENT_VM_INIT, NULL)
            != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }
    return JNI_OK;
}
~~~

Ví dụ **Linux + GCC + JDK có header JNI/JVM TI**, từ thư mục chứa `sample_jvmti.c` và `Demo.class`:

~~~bash
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libsamplejvmti.so sample_jvmti.c
java -agentpath:"$PWD/libsamplejvmti.so" Demo
~~~

Trước khi `Demo.main` chạy, callback in:

~~~text
[jvmti] VM initialized
~~~

Bản ví dụ chỉ xử lý `Agent_OnLoad` và `VMInit`, **chưa có `Agent_OnAttach` hay bộ profiler thực tế**. Một agent dùng sự kiện nhạy cảm như method entry phải xin capability thích hợp, kiểm tra hàm nào có sẵn trong phase hiện tại, và không thực hiện công việc blocking/nặng trong callback.

**JVM TI khác JNI:** JNI cho native code tương tác với Java (gọi Java methods, truy cập objects, tạo references); JVM TI dành cho **công cụ giám sát/điều khiển VM**. JVM TI có thể dùng JNI types trong callback, nhưng hai interface có trách nhiệm khác nhau. Debugger thường đi qua lớp giao thức **JDWP** và thành phần của **Java Platform Debugger Architecture (JPDA)**; ứng dụng tiêu thụ công cụ debugger không nhất thiết trực tiếp gọi JVM TI.

## 7. Bốn thành phần kết hợp trong một yêu cầu thật

**Tình huống:** ứng dụng `OrderService` đang chạy, cần đo độ trễ một số phương thức mà không sửa mã nguồn.

| Nhu cầu cụ thể | Lựa chọn | Vì sao |
|---|---|---|
| Có quyền sửa cấu hình startup và muốn instrument từ đầu | `-javaagent` + `premain` + `Instrumentation` | Có thể đăng ký transformer trước khi class của ứng dụng được nạp |
| Cần chẩn đoán đột xuất một JVM đang chạy, chính sách cho phép | Attach API → `agentmain` | Đưa agent vào sau khi ứng dụng khởi động; phải xử lý riêng lớp đã nạp |
| Cần phân tích/chèn lệnh vào method bytecode trên JDK 24+ | Class-File API bên trong transformer | API giúp parse/transform/generate classfile đúng định dạng |
| Cần breakpoint, event method/thread hoặc dữ liệu native VM chi tiết | JVM TI native agent / debugger/profiler phù hợp | Có giao diện event/capability trực tiếp với JVM |
| Chỉ cần thread dump, heap summary hoặc một số quan sát sẵn có | Công cụ `jcmd` / JFR / JMX khi phù hợp | Có trường hợp không cần tự viết và triển khai agent |

Hai thiết kế hợp lệ:

~~~text
Startup:
-app startup config---> -javaagent:metrics.jar
                         └─> Instrumentation
                               └─> transformer + classfile tool
                                     └─> modified class bytes

Live:
diagnostic tool ---> Attach API ---> agentmain
                                      └─> Instrumentation
                                            ├─> quan sát loaded classes
                                            └─> retransform nếu có quyền và hỗ trợ

Low-level:
-profiler startup config---> -agentpath:profiler.so
                               └─> JVMTI callbacks / queries
~~~

Không bắt buộc một hệ thống phải dùng **cả bốn**. Ví dụ tool build xử lý `.class` offline chỉ cần Class-File API; Java agent chỉ quan sát tên lớp có thể không cần Class-File API; profiler native có thể dùng JVM TI mà không dùng `java.lang.instrument`.

## 8. Ranh giới kỹ thuật, bảo mật và vận hành

### 8.1. Class đã nạp không giống class sắp được nạp

- Transformer đăng ký hôm nay mặc định áp dụng cho các lần định nghĩa class trong tương lai. Việc xuất hiện trong `getAllLoadedClasses()` không có nghĩa class sẽ tự động chạy lại transform.
- `retransformClasses` yêu cầu JVM và agent hỗ trợ, lớp mục tiêu phải sửa được; manifest `Can-Retransform-Classes: true` chỉ là một điều kiện. Khi tải lại định nghĩa, JVM thường giới hạn thay đổi cấu trúc class đã nạp (chẳng hạn không tự do thêm/xóa method, field, đổi quan hệ kế thừa). Thay đổi body hợp lệ cũng cần đáp ứng verifier.
- Một method đang chạy có thể tiếp tục thực thi frame theo định nghĩa cũ tùy ngữ nghĩa redefine/retransform, trong khi lời gọi sau dùng định nghĩa mới. Vì vậy không coi hotswap là thay đổi tức thì mọi stack frame đang hoạt động.
- Class identity phụ thuộc **tên lớp + class loader định nghĩa**. Hai class cùng tên nhưng khác loader là hai kiểu khác nhau; lọc chỉ theo tên dễ instrument nhầm.

### 8.2. Dynamic agent loading và JEP 451

Từ **JDK 21**, HotSpot phát cảnh báo khi **nạp động** Java/JVM TI agent vào JVM đang chạy, theo JEP 451. Startup agent qua `-javaagent`, `-agentlib`, `-agentpath` không bị cảnh báo này chỉ vì cách nạp. Với HotSpot có cơ chế thích hợp, `-XX:+EnableDynamicAgentLoading` thể hiện sự cho phép từ startup và tránh warning; `-XX:-EnableDynamicAgentLoading` từ chối dynamic loading. Chính sách mặc định có thể thay đổi theo đời JDK và vendor: **kiểm tra đúng runtime triển khai**, không tự giả định attach luôn được phép.

Không dựa vào khả năng tự attach như một quyền mặc định; sandbox, container, OS user, seccomp, permission hoặc JVM flags có thể chặn việc attach. Trên môi trường sản xuất, ưu tiên đưa agent được phê duyệt vào cấu hình startup nếu công cụ cần chạy thường xuyên, và ghi lại phiên bản agent cùng quyền truy cập của quá trình tải agent.

### 8.3. Ổn định và hiệu năng

- Code của agent chạy trong JVM mục tiêu; lỗi khởi tạo `premain` có thể khiến JVM dừng startup. Xử lý lỗi và tắt tính năng rõ ràng trước khi triển khai sản xuất.
- Chỉ instrument package/method cần đo; tránh transformer thay đổi cả JDK, lớp logging hoặc chính thư viện agent vì có thể gây tải lớp đệ quy (`ClassCircularityError`), deadlock hoặc overhead lớn.
- Callback class load/method event có thể chạy trên luồng nhạy cảm của ứng dụng; giữ chúng ngắn, không đợi I/O ngoài, không tạo lock khó kiểm soát. Thiết kế thu thập dữ liệu có giới hạn và cơ chế giảm tải.
- Đừng giả định bytecode đã transform vẫn đúng trên mọi JDK: classfile version, stack map frames, method handles, `invokedynamic`, module boundaries và các class ẩn có thể làm lộ lỗi.
- `Class-File API` ở `java.base` có thể dùng với JDK 24+; `Attach API` là mô-đun `jdk.attach` có tính triển khai; `JVM TI` cần runtime có hỗ trợ và thư viện native đúng OS/CPU/ABI. “Code Java 17+” của phần agent không làm ví dụ Class-File API chạy được trên JDK 17.

## 9. Các nhầm lẫn thường gặp

1. **“Attach API là API instrument bytecode.”** Sai: Attach kết nối và yêu cầu tải agent; phần instrument nằm ở `Instrumentation`/transformer hoặc native agent.
2. **“Đăng ký transformer sẽ sửa mọi class đang chạy.”** Sai: class đã nạp chỉ được xét lại bằng thao tác chủ động và capability thích hợp.
3. **“Class-File API làm JVM dùng ngay class mới.”** Sai: API chỉ tạo/đọc/biến đổi classfile; class loader, agent hoặc công cụ build phải tiêu thụ bytes.
4. **“Java agent và JVM TI agent đều là JAR.”** Sai: Java agent thường là JAR có `Premain-Class`/`Agent-Class`; JVM TI agent thường là native shared library có entry point C.
5. **“JNI và JVM TI giống nhau.”** Sai: JNI là giao tiếp Java/native; JVM TI là giao diện chuyên cho debugger, profiler và các công cụ VM.
6. **“Có `Can-Retransform-Classes: true` thì thay đổi bất kỳ class nào cũng được.”** Sai: còn phụ thuộc JVM capability, class có sửa được không và giới hạn cấu trúc trong quá trình redefine/retransform.
7. **“JDK 21 cảnh báo nghĩa là attach đã bị cấm.”** Sai: JEP 451 khởi đầu bằng cảnh báo để chuẩn bị cho chính sách chặt hơn; trạng thái cho phép phụ thuộc phiên bản JVM và cờ chạy cụ thể.

## 10. Tự kiểm tra kiến thức

- **Bài tập A:** cần thêm logging vào class trước lần nạp đầu tiên trên JDK 17. Bạn chọn `-javaagent`/`premain` hay Attach? Có cần Class-File API JDK 24 không?
- **Bài tập B:** JVM đã chạy 2 giờ, mới attach agent. Vì sao callback chỉ đăng ký bằng `addTransformer` chưa ghi nhận các class đã nạp? Điều kiện nào phải kiểm tra trước `retransformClasses`?
- **Bài tập C:** một công cụ CLI cần đọc danh sách method từ `UserService.class` offline trên JDK 24. Trong bốn công nghệ, cần cái nào? Vì sao không cần PID?
- **Bài tập D:** muốn nhận event VMInit và phân tích thread ở tầng VM bằng mã C. Tại sao chọn JVM TI thay vì Attach API đơn lẻ? Native agent khởi động bằng cờ nào?

Gợi ý đáp án: **A** dùng `-javaagent` và bytecode library tương thích JDK 17; **B** phải xử lý class đã nạp bằng retransform/redefine khi JVM hỗ trợ và class sửa được; **C** chỉ cần Class-File API; **D** dùng JVM TI native agent qua `-agentlib` hoặc `-agentpath` (Attach có thể chỉ đóng vai trò đưa agent vào nếu JVM hỗ trợ).

## Tài liệu chính thức để tra cứu

- Java Instrumentation API, startup/dynamic agents: https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html
- `Instrumentation` và điều kiện retransform/redefine: https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Attach API (`jdk.attach`): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html
- Class-File API JDK 24: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html
- JVM Tool Interface specification: https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html
- JEP 451, dynamic agent loading: https://openjdk.org/jeps/451
- JEP 484, Class-File API: https://openjdk.org/jeps/484
