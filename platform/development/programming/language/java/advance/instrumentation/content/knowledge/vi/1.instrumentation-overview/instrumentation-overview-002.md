# Java agent chạy trong cùng JVM với ứng dụng và có vòng đời như thế nào

> **Ý chính:** Java agent là mã Java được JVM ứng dụng nạp và khởi tạo để quan sát hoặc biến đổi hành vi của chương trình. Khi dùng `-javaagent`, JVM gọi `premain` trước `main`; khi nạp vào JVM đang chạy bằng cơ chế attach, JVM gọi `agentmain`. Sau khi hai phương thức khởi tạo trả về, các transformer, thread và tài nguyên mà agent đã đăng ký vẫn có thể hoạt động cho đến khi được tháo gỡ hoặc JVM kết thúc.

## 1. "Cùng JVM" thực sự có nghĩa gì?

Java agent thường là một **JAR có các thuộc tính manifest dành cho agent**. Nó không tự động là tiến trình độc lập, không có một JVM riêng và cũng không nhất thiết có một vòng lặp xử lý riêng.

Khi agent được nạp vào ứng dụng:

- **Cùng tiến trình và không gian địa chỉ:** agent dùng chung heap, garbage collector, CPU, tài nguyên hệ điều hành và các giới hạn bộ nhớ của JVM ứng dụng. Lỗi nghiêm trọng, deadlock hoặc tiêu thụ tài nguyên quá mức trong agent có thể ảnh hưởng cả ứng dụng.
- **Cùng runtime nhưng không đồng nghĩa cùng class loader:** lớp trong agent JAR được nạp qua *system class loader* vào unnamed module của loader đó. Lớp ứng dụng có thể dùng system loader hoặc loader riêng của framework, container, plugin. Vì vậy không được giả định agent nhìn thấy mọi dependency của ứng dụng.
- **Một điểm vào do JVM gọi:** `premain`/`agentmain` nhận chuỗi tuỳ chọn và, với chữ ký hai tham số, đối tượng `java.lang.instrument.Instrumentation`. Đối tượng này là cầu nối với các khả năng instrumentation do JVM hỗ trợ.
- **Không phụ thuộc việc có thay bytecode hay không:** agent có thể chỉ quan sát/sắp xếp hook, hoặc đăng ký `ClassFileTransformer` để biến đổi bytes của lớp. Ví dụ trong bài chỉ ghi log khi lớp được định nghĩa; nó **không sửa bytecode**.

Hãy phân biệt ba thành phần:

| Thành phần | Ở đâu? | Vai trò |
| --- | --- | --- |
| Ứng dụng | JVM đích | Chạy nghiệp vụ với `main`, thread, class loader và tài nguyên của ứng dụng |
| Java agent | **Trong chính JVM đích** | Đăng ký instrumentation, quan sát class load, đo đạc hoặc biến đổi bytecode |
| Attach tool (nếu dùng) | Thường là **tiến trình/JVM khác** | Kết nối tới JVM đích và yêu cầu nó nạp agent; sau khi nạp, mã `agentmain` chạy ở **JVM đích** |

## 2. Vòng đời khi khởi động bằng `-javaagent`

Cú pháp trên JDK hỗ trợ Java instrumentation:

~~~bash
java -javaagent:agent.jar=someOptions -cp app.jar com.example.Main
~~~

`someOptions` được đưa nguyên dạng thành tham số `String agentArgs`; JVM không tự tách hay giải nghĩa các cặp key/value thay agent.

Trình tự quan trọng:

1. Java launcher tạo JVM và xử lý cấu hình khởi động, trong đó có đường dẫn agent JAR.
2. JVM đọc thuộc tính `Premain-Class` của manifest, nạp lớp agent và tìm `public static void premain(String, Instrumentation)`; nếu không có, JVM thử chữ ký `premain(String)`.
3. **Sau khi JVM khởi tạo nhưng trước khi gọi `main` của ứng dụng**, JVM gọi `premain`. Agent thường đọc cấu hình, kiểm tra quyền/capability, đăng ký transformer, khởi tạo bộ đo và các tài nguyên cần thiết. `premain` phải trả về để ứng dụng tiếp tục khởi động.
4. JVM tiếp tục nạp/định nghĩa các lớp và gọi `main`. Với transformer đã đăng ký, JVM có thể gọi `transform` **ngay trong quá trình định nghĩa lớp, trước `main`**, rồi tiếp tục gọi cho các lượt nạp lớp về sau.
5. Khi ứng dụng vận hành, các callback và thread của agent vẫn có thể chạy. Đến lúc tiến trình JVM dừng, agent cùng kết thúc với tiến trình; Java instrumentation không tự cung cấp phương thức `stop` bắt buộc.

~~~mermaid
sequenceDiagram
    participant Launch as Java launcher
    participant JVM as JVM đích
    participant Agent as Agent trong JVM
    participant App as Ứng dụng
    Launch->>JVM: -javaagent:agent.jar=boot
    JVM->>Agent: premain("boot", Instrumentation)
    Agent->>JVM: addTransformer(...)
    Agent-->>JVM: premain trả về
    JVM->>Agent: transform(HelloApp) khi định nghĩa lớp
    Agent-->>JVM: null (không đổi bytecode)
    JVM->>App: main(args)
    Note over JVM,Agent: Transformer còn đăng ký và có thể được gọi tiếp
~~~

**Hai hệ quả vận hành:**

- Nếu có nhiều tham số `-javaagent`, `premain` được gọi theo **thứ tự liệt kê trên dòng lệnh**. Việc nhiều agent cùng sửa một lớp làm thứ tự transformer trở nên quan trọng.
- Nếu không thể nạp agent khởi động, thiếu `Premain-Class`/chữ ký phù hợp hoặc `premain` ném ngoại lệ chưa bắt, JVM **có thể hủy khởi động trước khi chạy `main`**. Đây là lỗi khởi động ứng dụng, không phải lỗi một công cụ giám sát tách biệt.

## 3. Thực hành: quan sát một agent chạy trước `main` (Java 17+)

Tạo bốn tệp sau trong **cùng một thư mục**. Không cần thư viện ngoài JDK.

**`LifecycleAgent.java`** — chứa hai điểm vào; lần chạy đầu chỉ sử dụng `premain`.

~~~java
import java.lang.instrument.Instrumentation;

public final class LifecycleAgent {
    public static void premain(String args, Instrumentation inst) {
        start("premain", args, inst);
    }

    public static void agentmain(String args, Instrumentation inst) {
        start("agentmain", args, inst);
    }

    private static void start(String entry, String args, Instrumentation inst) {
        System.out.println("[agent] " + entry + ", args=" + args);
        inst.addTransformer(new LoggingTransformer());
    }
}
~~~

**`LoggingTransformer.java`** — callback được JVM gọi khi định nghĩa lớp phù hợp. Nó trả về `null` nên giữ nguyên class bytes.

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class LoggingTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(ClassLoader loader, String className,
                            Class<?> type, ProtectionDomain domain,
                            byte[] originalBytes) {
        if ("HelloApp".equals(className)) {
            System.out.println("[agent] about to define HelloApp");
        }
        return null;
    }
}
~~~

**`HelloApp.java`** — ứng dụng đích cực nhỏ.

~~~java
public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("[app] main");
    }
}
~~~

**`agent.mf`** — manifest của agent, bắt đầu bằng hai thuộc tính entry point tương ứng; hãy lưu với dấu xuống dòng kết thúc tệp.

~~~text
Manifest-Version: 1.0
Premain-Class: LifecycleAgent
Agent-Class: LifecycleAgent
~~~

Biên dịch, đóng gói **cả hai lớp của agent** rồi khởi động ứng dụng:

~~~bash
javac --release 17 LifecycleAgent.java LoggingTransformer.java HelloApp.java
jar --create --file lifecycle-agent.jar --manifest agent.mf LifecycleAgent.class LoggingTransformer.class
java -javaagent:lifecycle-agent.jar=boot HelloApp
~~~

**Stdout mong đợi:**

~~~text
[agent] premain, args=boot
[agent] about to define HelloApp
[app] main
~~~

Giải thích từng dòng:

- Dòng đầu chứng minh JVM đã gọi `premain` và chuyển chuỗi `boot` cho agent trước `main`.
- Dòng thứ hai xảy ra khi JVM đang định nghĩa lớp `HelloApp`. Transformer trả `null` nên không thay đổi bytecode; ứng dụng vẫn chạy bình thường.
- Dòng cuối là `main` của ứng dụng. Cùng một luồng stdout chứng minh agent ở trong tiến trình đích; thứ tự ba dòng cho thấy quá trình đăng ký callback diễn ra trước lượt định nghĩa lớp này.

Ví dụ dùng tên lớp mặc định `HelloApp`. Với lớp có package, tham số `className` ở dạng JVM internal name, ví dụ `com/example/HelloApp` (dấu gạch chéo thay cho dấu chấm). `ClassFileTransformer` là interface có các phương thức `transform` mặc định, vì vậy đoạn mẫu dùng lớp triển khai rõ ràng thay vì một lambda.

## 4. Vòng đời khi attach vào JVM đang chạy: `agentmain`

Đường đi thứ hai bắt đầu **sau khi ứng dụng đã khởi chạy**. Một công cụ ngoài ứng dụng dùng cơ chế Attach API (nếu JVM, OS và chính sách cho phép) để nạp agent JAR vào JVM đích. JVM đích đọc `Agent-Class` từ manifest và gọi `public static void agentmain(String, Instrumentation)`, hoặc chữ ký một tham số nếu phù hợp.

~~~text
JVM công cụ attach                 JVM ứng dụng đang chạy
-------------------                ------------------------
VirtualMachine.attach(pid)  --->   Kênh attach của JVM đích
VirtualMachine.loadAgent(jar) --->  Nạp JAR, gọi agentmain(...)
VirtualMachine.detach()      --->  Kết thúc kết nối công cụ
                                   Transformer/thread đã đăng ký vẫn chạy
~~~

**`agentmain` cũng phải khởi tạo nhanh rồi trả về**, nhưng nó không chạy lại `premain` hoặc `main`. Khác với startup agent, nó đến **sau khi một số lớp đã được định nghĩa**, nên việc chỉ gọi `addTransformer` không tự động đi ngược thời gian để quan sát/biến đổi những lớp đó. Trường hợp cần xử lý lớp đã nạp, xem phần retransformation bên dưới.

Khi `agentmain` thất bại hoặc ném ngoại lệ, đặc tả không yêu cầu JVM đích hủy tiến trình giống lỗi `premain`; công cụ attach vẫn có thể nhận lỗi và tác dụng agent có thể chưa hoàn tất. Không suy ra rằng lỗi agent động là vô hại: mã đã chạy trong cùng JVM vẫn có thể thay đổi trạng thái.

### Thử attach với chính JAR ở trên

Giữ `lifecycle-agent.jar` từ ví dụ trước. Tạo thêm hai tệp trong cùng thư mục.

**`LongApp.java`** — giữ JVM ứng dụng tồn tại đủ lâu để attach.

~~~java
public final class LongApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] pid=" + ProcessHandle.current().pid());
        Thread.sleep(120_000); // Hai phút để thực hành attach
        System.out.println("[app] done");
    }
}
~~~

**`AttachAgent.java`** — chương trình công cụ chạy ở JVM riêng, nhận PID của JVM đích từ dòng lệnh.

~~~java
import java.nio.file.Path;
import com.sun.tools.attach.VirtualMachine;

public final class AttachAgent {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass the target JVM PID");
        }

        String agentJar = Path.of("lifecycle-agent.jar")
                              .toAbsolutePath().toString();
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(agentJar, "live");
        } finally {
            vm.detach();
        }
        System.out.println("[tool] agent loaded");
    }
}
~~~

Biên dịch bằng JDK có module `jdk.attach`:

~~~bash
javac --release 17 --add-modules jdk.attach LongApp.java AttachAgent.java
~~~

Ở **terminal A**, chạy JVM ứng dụng đang hoạt động (không dùng `-javaagent`). Trên các JDK hỗ trợ, cờ `-XX:+EnableDynamicAgentLoading` cho phép nạp agent động một cách tường minh:

~~~bash
java -XX:+EnableDynamicAgentLoading LongApp
~~~

Terminal A hiện `[app] pid=...`. Sao chép **số PID thực tế** vừa hiện, rồi ở **terminal B**, thay số mẫu `12345` bên dưới bằng PID đó:

~~~bash
java --add-modules jdk.attach AttachAgent 12345
~~~

Trong trường hợp attach được cho phép, terminal B in:

~~~text
[tool] agent loaded
~~~

Còn **terminal A của JVM đích** sẽ in thêm:

~~~text
[agent] agentmain, args=live
~~~

Các thông điệp phụ thuộc JVM/chính sách, ví dụ cảnh báo động trên một số phiên bản, có thể xuất hiện trên stderr. Quan trọng nhất: log `agentmain` hiện ở **JVM đích**, không phải công cụ attach. Mặc dù `LoggingTransformer` đã được đăng ký, sẽ **không có** log "about to define HelloApp" ở ví dụ này vì `LongApp` đã được định nghĩa trước khi attach, và transformer chỉ lọc tên `HelloApp`.

Attach có thể bị từ chối do khác tài khoản người dùng, môi trường container, cấu hình JVM, thiếu module/cơ chế attach hoặc chính sách bảo mật. JDK 21 đưa ra cảnh báo khi nạp agent động (JEP 451) và chuẩn bị cho chính sách hạn chế hơn ở các bản JDK tiếp theo. Vì vậy phải kiểm tra **đúng phiên bản JDK đang triển khai**; không dựa vào giả định attach luôn bật. Khi muốn agent được nạp nhất quán ngay từ đầu, cấu hình `-javaagent` thường dễ kiểm soát hơn.

## 5. Khi `premain`/`agentmain` đã trả về, agent "sống" nhờ đâu?

Hai phương thức trên là **điểm khởi tạo**, không phải vòng lặp sống của agent.

| Giai đoạn | Điều gì giữ cho hoạt động của agent tiếp diễn? | Khi nào ngừng? |
| --- | --- | --- |
| Đăng ký transformer | JVM duy trì đăng ký của đối tượng `ClassFileTransformer` | Khi `removeTransformer` hoặc JVM dừng |
| Thread/task do agent tạo | Thread, scheduler, buffer, exporter chạy trong cùng JVM | Khi task kết thúc, được dừng hoặc JVM dừng |
| Hook/listener/tài nguyên khác | Đăng ký/đối tượng vẫn được tham chiếu bởi hệ thống liên quan | Khi chủ động hủy đăng ký, giải phóng hoặc JVM dừng |
| Mã chỉ chạy trong entry point | Không có việc nền nào được tự tạo | Tác dụng trực tiếp kết thúc khi phương thức trả về |

Vì vậy, **`premain` trả về không có nghĩa agent đã bị unload**. Ngược lại, nếu entry point chỉ in một dòng và không đăng ký gì, cũng không có công việc nền nào để tiếp tục. Nếu dùng thread nền để gửi telemetry, cần quản lý hàng đợi, backpressure, đóng kết nối, thời hạn chờ và tránh giữ JVM không thể thoát ngoài ý muốn; thread daemon không đảm bảo dữ liệu được flush khi dừng đột ngột.

Java instrumentation **không định nghĩa callback `stop()` thống nhất**. Agent có thể tự cung cấp cơ chế tắt, gọi `removeTransformer`, đóng tài nguyên và đăng ký shutdown hook khi phù hợp. Tuy nhiên, `removeTransformer` không cam kết rằng không còn callback đang chạy do class loading song song, cũng **không tự khôi phục bytecode** của những lớp đã sửa trước đó. Shutdown hook không thay thế cơ chế flush và xử lý lỗi được thiết kế rõ ràng.

## 6. Transformer nhìn thấy lớp nào và có thể thay đổi đến đâu?

`Instrumentation.addTransformer(transformer)` đăng ký một transformer không chủ động hỗ trợ retransformation. Khi JVM chuẩn bị định nghĩa một lớp, có thể có callback:

~~~java
byte[] transform(
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    ProtectionDomain protectionDomain,
    byte[] classfileBuffer
);
~~~

Đây là **chữ ký API để giải thích**, không phải một tệp Java độc lập. `classfileBuffer` chứa bytes đầu vào; agent có thể trả về mảng bytes class file hợp lệ khác để thay đổi định nghĩa, hoặc **`null`** nếu không thay đổi. Không sửa trực tiếp mảng đầu vào. Callback có thể xuất hiện trên các thread nạp lớp khác nhau; giữ nó nhanh, thread-safe và tránh recursion/class-loading cycle.

Phân biệt rõ các trường hợp:

| Trường hợp | `addTransformer` cơ bản | Cần gì thêm? |
| --- | --- | --- |
| Lớp được định nghĩa **sau** khi đăng ký | Có cơ hội nhận `transform` | Không cần retransform |
| Lớp đã được định nghĩa **trước** khi attach | Không có callback hồi tố | Có thể dùng `retransformClasses`/`redefineClasses` nếu JVM và lớp cho phép |
| Lớp đang chạy khi retransform | Không dừng hay quay lại toàn bộ hàm theo cách tuỳ ý | Frame đang chạy có thể tiếp tục bytecode cũ; lần gọi mới dùng định nghĩa mới |
| Muốn thay đổi cấu trúc lớp tùy ý | Không được bảo đảm | Redefinition/retransformation có giới hạn về cấu trúc và loại lớp có thể sửa |

Khi cần retransform các lớp đã nạp, agent phải khai báo trong manifest:

~~~text
Can-Retransform-Classes: true
~~~

Sau đó **kiểm tra khả năng thực tế** bằng `inst.isRetransformClassesSupported()`, kiểm tra từng lớp với `inst.isModifiableClass(clazz)`, đăng ký transformer dạng `inst.addTransformer(transformer, true)`, rồi mới gọi `inst.retransformClasses(clazz)` khi an toàn. Đặt thuộc tính manifest **không tự thực hiện** retransformation. Ngoài ra, một số dạng thay đổi cấu trúc lớp (ví dụ thay đổi tập field/method hoặc quan hệ kế thừa) không được hỗ trợ qua cơ chế này.

Lớp agent thường ở system loader, trong khi ứng dụng có thể có custom loader/module mạnh đóng gói. Các lỗi `ClassNotFoundException`, `NoClassDefFoundError`, `IllegalAccessError` hoặc việc transformer vô tình làm nạp chính dependency của nó là dấu hiệu cần phân tích class loader và module readability/openness. API `Instrumentation` có những khả năng bổ sung như `redefineModule`, nhưng chỉ dùng khi đã xác định chính xác yêu cầu truy cập.

## 7. Những nhầm lẫn và lỗi thực tế

1. **Nhầm Java agent với một service độc lập.** Agent chạy **trong JVM đích**; chỉ công cụ attach có thể ở tiến trình khác. Không có cô lập lỗi hay bộ nhớ mặc định.
2. **Chỉ đặt `Main-Class` trong JAR rồi chờ `premain` chạy.** `Main-Class` của ứng dụng và `Premain-Class`/`Agent-Class` của agent có ý nghĩa khác nhau. Gọi `premain` như một hàm Java bình thường cũng không tạo ra đối tượng `Instrumentation` hợp lệ từ JVM.
3. **Cho rằng `agentmain` thấy mọi lần load trong quá khứ.** Transformer thông thường nhận các class definition tương lai; muốn can thiệp lớp đã nạp cần API và capability riêng.
4. **Quên đóng gói dependency của agent.** Manifest đúng nhưng JAR thiếu `LoggingTransformer.class` hoặc thư viện agent cần vẫn gây lỗi. Dependency của ứng dụng không chắc nhìn thấy được bởi loader của agent.
5. **Đăng ký transformer lặp hoặc làm quá nhiều việc trong callback.** Điều này gây log trùng, overhead, tải CPU, vòng lặp class loading hoặc nguy cơ deadlock. Thực tế cần quản lý vòng đời và cấu hình thread-safe.
6. **Xem agent là mã "chỉ để quan sát" nên luôn an toàn.** Agent có quyền ảnh hưởng trực tiếp hành vi JVM và có thể đọc dữ liệu trong tiến trình. Chỉ chạy agent tin cậy; đo overhead, kiểm tra tương thích JDK, quy tắc log và khả năng rollback.
7. **Giả định attach hoạt động trên mọi JDK/hạ tầng.** Quyền người dùng, container, JVM flag, module và chính sách thay đổi được; kiểm thử trên đúng runtime và ưu tiên bật agent lúc startup nếu mô hình triển khai cho phép.

## 8. Ghi nhớ theo vòng đời

- **Khởi động:** `-javaagent` → JVM nạp JAR theo `Premain-Class` → `premain` đăng ký hook → ứng dụng vào `main`.
- **Đang chạy:** Agent và ứng dụng chung một JVM; transformer được gọi khi lớp phù hợp được định nghĩa, và thread/tài nguyên do agent tạo tiếp tục chạy độc lập với việc entry point đã trả về.
- **Gắn động:** Attach tool kết nối đến JVM đã chạy → JVM nạp theo `Agent-Class` → `agentmain` → hook chỉ áp dụng theo thời điểm đăng ký, trừ khi chủ động retransform/redefine lớp cũ.
- **Kết thúc:** Không có `stop` chuẩn; cần tự thiết kế cleanup. JVM thoát thì cả agent và ứng dụng cùng kết thúc.

**Tài liệu chính thức để đọc sâu:**

- [Java SE 17 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): entry point, manifest, trình tự khởi động, class loader của agent.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký/xóa transformer, retransform, redefine và các giới hạn.
- [Java SE 17 — Attach API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html): công cụ gắn vào JVM đích.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): cảnh báo và định hướng chính sách về dynamic agent loading.
