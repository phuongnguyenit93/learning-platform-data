# Java agent và API Instrumentation trong công cụ quan sát Java hiện đại

## 1. Vì sao Java agent có vai trò trong observability?

Khi cần biết một hệ thống Java đang hoạt động như thế nào, đôi lúc chúng ta không thể, hoặc không muốn, sửa tất cả các thư viện và thành phần nghiệp vụ chỉ để đo thời gian của mỗi HTTP request, truy vết một database call hay đếm những class được tải. **Java agent** là cơ chế do JVM cung cấp để một công cụ thực thi mã lúc ứng dụng khởi động hoặc — nếu runtime cho phép — khi ứng dụng đã chạy. Agent có thể **quan sát việc nạp lớp** và, trong giới hạn được JVM chấp nhận, **biến đổi bytecode** của các lớp.

Các mục tiêu thường gặp:

- **Tracing**: tạo các span cho HTTP, database, messaging và outbound RPC; liên kết chúng bằng context propagation.
- **Metrics**: số requests, lỗi, độ trễ và các chỉ số JVM/resource.
- **Profiling/diagnostics**: phát hiện các class/module, đo tác động của instrumentation, tìm vùng nghi vấn.
- **Coverage/testing**: thêm các điểm ghi nhận khi method hoặc nhánh được thực thi.
- **Runtime observability**: quan sát class loading hoặc gắn telemetry vào thư viện đã được biên dịch mà không trực tiếp sửa source của thư viện ấy.

Trong Java 17+ và Java SE 25, API chuẩn là **`java.lang.instrument`** thuộc **module `java.instrument`**. Lối vào của agent là một **JAR có manifest hợp lệ**, không phải gọi `new Instrumentation()` hoặc một thư viện JAR tự động được JVM biến thành agent.

**Phân biệt:** một Java agent là **cơ chế triển khai instrumentation**, còn observability là **mục tiêu**. Không phải cứ gắn `-javaagent` thì đã có hệ thống tracing/metrics an toàn; agent còn cần thu thập tín hiệu chính xác, giới hạn overhead, redaction, context propagation và pipeline xuất dữ liệu phù hợp.

### Tổng quan luồng khởi động

~~~text
java -javaagent:observe-agent.jar=demo -cp observe-agent.jar ObservedApp
                      |
                      v
         JVM đọc MANIFEST.MF của agent JAR
               Premain-Class: ObserveAgent
                      |
                      v
      public static premain(String args, Instrumentation inst)
                      |
            inst.addTransformer(transformer)
                      |
                      v
            Application main() bắt đầu
                      |
             JVM define class ObservedTarget
                      |
                      v
        ClassFileTransformer.transform(...) được gọi
                      |
              return null (chỉ quan sát)
              hoặc return byte[] (biến đổi)
                      |
                      v
             JVM xác minh/định nghĩa class
                      |
             Application method được gọi
~~~

Điểm then chốt: agent khởi động qua `premain` chạy **trước application `main`**, nhưng **không có nghĩa tất cả classes trong JVM chỉ bắt đầu được tải sau premain**. JVM, Java platform và chính agent có thể đã tải một số lớp trước đó. Nếu muốn xử lý lớp đã nạp, cần các khả năng `retransformClasses` hoặc `redefineClasses`, và phải kiểm tra capability/`isModifiableClass` riêng.

## 2. Khi nào nên dùng agent, khi nào nên chọn JFR, JMX hay code instrumentation?

| Nhu cầu | Cách tiếp cận thường phù hợp | Hạn chế |
| --- | --- | --- |
| Auto-instrument các thư viện HTTP/DB phổ biến | OpenTelemetry Java agent được quản trị, khởi động bằng `-javaagent` | Cần kiểm version, overhead và telemetry policy |
| Thu thập traces nghiệp vụ tùy biến | OpenTelemetry API/SDK hoặc manual library instrumentation | Cần thêm code tại chỗ phù hợp |
| Profile CPU, allocation, GC, locks và runtime events | Java Flight Recorder (JFR), `jdk.jfr` | Không tự sinh distributed trace/span semantics |
| Xem thông số và trạng thái JVM | JMX/MXBeans như `ThreadMXBean`, `MemoryMXBean` | Snapshot/metrics khác với trace của từng request |
| Đếm class load hoặc thay đổi bytecode có chọn lọc | `java.lang.instrument.Instrumentation`, `ClassFileTransformer` | Cần agent JAR, quyền triển khai và test các class versions |
| Thay nguyên implementation của method trong class đã loaded | `retransformClasses`, `redefineClasses` nếu supported | Hạn chế cấu trúc, rủi ro lỗi và ảnh hưởng các stack frames |
| Muốn export logs/traces/metrics | SDK/exporter/collector | Instrumentation API **không tự gửi** dữ liệu |
| Audit bảo mật bất biến, không được phép mất | Durable audit log/outbox | Agent callback không phải durable queue |

OpenTelemetry hiện khuyến nghị bắt đầu từ Java agent khi phù hợp để tự động instrument các thư viện phổ biến; xem tài liệu chính thức ở cuối bài. Nhưng với mục tiêu chỉ đo GC hoặc allocation, **JFR có thể đơn giản hơn**, không cần tự sửa bytecode. Với service status/JVM memory, dùng MXBean/JMX khi đủ. Hãy chọn công cụ theo tín hiệu cần thu, không chọn agent chỉ vì nó có quyền can thiệp vào runtime.

## 3. API Instrumentation: vai trò từng phương thức

`Instrumentation` là interface được JVM truyền tới agent qua `premain` hoặc `agentmain`. Không có constructor public để bạn tự tạo. Những methods đáng học:

| Method | Nhiệm vụ | Giới hạn cần nhớ |
| --- | --- | --- |
| `addTransformer(transformer)` | Đăng ký callback cho class definitions/redefinitions | Mặc định **không** có retransform-capable flag |
| `addTransformer(transformer, canRetransform)` | Đăng ký với quyền tham gia retransformation nếu supported | Chỉ truyền true khi manifest/runtime cho phép |
| `removeTransformer(transformer)` | Gỡ đăng ký một transformer | Callback đang chạy vẫn có thể kết thúc sau khi gỡ |
| `isRetransformClassesSupported()` | Kiểm JVM/agent đã cấp retransform capability | Phụ thuộc `Can-Retransform-Classes` trong manifest |
| `retransformClasses(Class<?>...)` | Yêu cầu chạy lại quá trình transformation cho các lớp đã loaded | Không phải class nào cũng modifiable |
| `isRedefineClassesSupported()` | Kiểm capability thay hẳn class definition | Phụ thuộc `Can-Redefine-Classes` và JVM |
| `redefineClasses(ClassDefinition...)` | Cung cấp bytes lớp mới thay definition hiện tại | Giới hạn structural changes, bytecode phải hợp lệ |
| `isModifiableClass(Class<?>)` | Kiểm một class cụ thể có thể chỉnh được không | true không bảo đảm mọi phép biến đổi sẽ hợp lệ |
| `getAllLoadedClasses()` | Snapshot các Class objects đã loaded | Có thể đắt, không phải streaming event log |
| `getInitiatedClasses(ClassLoader)` | Classes mà loader đã initiated theo contract | Khác với “classloader đã define class” |
| `getObjectSize(Object)` | Ước tính dung lượng lưu object | **Shallow approximation**, không phải retained heap size |
| `appendToBootstrapClassLoaderSearch(JarFile)` | Thêm helper JAR vào bootstrap search | Classloader boundary, chỉ helper an toàn |
| `appendToSystemClassLoaderSearch(JarFile)` | Thêm helper JAR vào system search | Cấu hình custom loader có thể hạn chế |
| `isModifiableModule(Module)` | Kiểm khả năng điều chỉnh module | Không ngụ ý có thể tùy ý mở mọi module |
| `redefineModule(...)` | Bổ sung read/exports/opens/uses/provides ở runtime | Quyền rất mạnh; không phải cách bypass tùy tiện |
| `isNativeMethodPrefixSupported()` | Kiểm khả năng native method prefix | Niche capability, không dùng mặc định |

### Hai nhóm không nên đánh đồng

- **Observation-only transformer:** nhận callback và metadata, trả **`null`**, JVM giữ nguyên class bytes. Ví dụ số 1 làm đúng như vậy.
- **Bytecode-transforming agent:** tạo **`byte[]` hợp lệ** và trả lại, JVM dùng bytes mới để định nghĩa/biến đổi class. Ví dụ số 2 dùng **Class-File API chuẩn Java 24+** để chứng minh một thay đổi bytecode có thật.

**Return `null` không có nghĩa “xóa class” hoặc “trả class rỗng”.** Theo contract, nó nói transformer **không thay bytes**. Return một mảng rỗng hay bytecode invalid có thể làm class load/retransform thất bại. Không sửa `classfileBuffer` tại chỗ; muốn biến đổi, tạo mảng bytes mới.

## 4. Khởi động agent: premain, agentmain và manifest JAR

Một Java agent có ít nhất một entry point tùy cách triển khai:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

được JVM gọi khi bạn đặt agent ở command-line `-javaagent:path/to/agent.jar`.

~~~java
public static void agentmain(String agentArgs, Instrumentation inst)
~~~

được JVM gọi khi agent được nạp **sau khi JVM đã bắt đầu** và runtime/permissions cho phép. Cả hai có overload chỉ nhận `String`, nhưng khi học API Instrumentation, dạng hai tham số là lựa chọn trực tiếp.

Đây là **chữ ký minh họa**, không phải hai phương thức phải đặt cùng một class có implementation rỗng. Một agent có thể hỗ trợ cả hai, nhưng workflow startup và attach có **manifest, timing và policy khác nhau**.

| Manifest attribute | Trường hợp | Bắt buộc? |
| --- | --- | --- |
| `Premain-Class: com.example.ObserveAgent` | Agent JAR dùng `-javaagent` lúc startup | **Có** |
| `Agent-Class: com.example.ObserveAgent` | Agent được runtime nạp vào JVM đã chạy | **Có** cho dynamic agent |
| `Launcher-Agent-Class: ...` | Agent gói cùng executable application JAR | Chỉ khi dùng cơ chế này |
| `Can-Retransform-Classes: true` | Agent cần `retransformClasses` | Phải yêu cầu và JVM cũng phải hỗ trợ |
| `Can-Redefine-Classes: true` | Agent cần `redefineClasses` | Phải yêu cầu và JVM cũng phải hỗ trợ |
| `Can-Set-Native-Method-Prefix: true` | Agent cần prefix native method | Chỉ khi thực sự có nhu cầu |
| `Boot-Class-Path` | Helper code cho bootstrap loader | Nên tránh khi không thực sự cần |

Chương trình số 1 dùng default package để dễ chạy trên cả Windows và Linux. **Production nên dùng package namespace riêng** cho agent, cô lập phụ thuộc, định nghĩa manifest theo tên class đầy đủ và version hóa agent JAR.

### Phương án đề xuất cho ứng dụng production

~~~bash
java -javaagent:/opt/agents/approved-agent.jar -jar application.jar
~~~

Đây là **mẫu cú pháp**, không giả định file tồn tại. Path và options phải phù hợp môi trường. Agent là một thành phần code đáng tin cậy chạy cùng quyền JVM, vì thế **không tải JAR không rõ nguồn hoặc tự động chấp nhận plugin do người ngoài gửi**.

Một Java 17+ runtime bình thường có module `java.instrument`; để compile code có `java.lang.instrument.*` bằng `javac --release 17` không cần dependencies ngoài. Nếu deployment dùng custom runtime image (`jlink`) đã loại bỏ module đó, phải giải quyết ở cấu hình image trước khi chạy agent. Đừng dựa vào việc nạp thêm module sau khi JVM đã thiếu nó.

## 5. Chương trình hoàn chỉnh số 1: Java 17+ startup agent chỉ quan sát

Bài thực hành này minh họa **API Instrumentation mà không thay đổi hành vi ứng dụng**. Nó chạy bằng JDK chuẩn, không cần Maven, ASM, Byte Buddy, network hoặc Attach API. Hai source files được biên dịch cùng nhau rồi đóng thành một JAR để bạn có thể kiểm tra cách JVM gọi premain.

**File 1: `ObserveAgent.java`**

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

public final class ObserveAgent {
    private static volatile Instrumentation instrumentation;
    private static final AtomicInteger loads = new AtomicInteger();
    private static final AtomicInteger retransforms = new AtomicInteger();
    private static volatile ClassFileTransformer transformer;
    private static volatile boolean premainCalled;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        premainCalled = true;
        System.out.println("agent option accepted: " + "demo".equals(options));
        transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain, byte[] classfileBuffer) {
                if ("ObservedTarget".equals(className)) {
                    if (classBeingRedefined == null) {
                        loads.incrementAndGet();
                    } else {
                        retransforms.incrementAndGet();
                    }
                }
                return null; // Observation only: no class bytes modified.
            }
        };
        inst.addTransformer(transformer, inst.isRetransformClassesSupported());
    }

    public static boolean started() {
        return premainCalled && instrumentation != null;
    }

    public static int observedLoads() {
        return loads.get();
    }

    public static int observedRetransforms() {
        return retransforms.get();
    }

    public static boolean targetIsLoaded(Class<?> type) {
        return Arrays.asList(instrumentation.getAllLoadedClasses()).contains(type);
    }

    public static boolean modifiable(Class<?> type) {
        return instrumentation.isModifiableClass(type);
    }

    public static boolean shallowPositive(Object object) {
        return instrumentation.getObjectSize(object) > 0L;
    }

    public static boolean requestRetransform(Class<?> type)
            throws java.lang.instrument.UnmodifiableClassException {
        if (!instrumentation.isRetransformClassesSupported()
                || !instrumentation.isModifiableClass(type)) {
            return false;
        }
        instrumentation.retransformClasses(type);
        return true;
    }

    public static boolean remove() {
        return instrumentation.removeTransformer(transformer);
    }
}
~~~

**File 2: `ObservedApp.java`**

~~~java
public final class ObservedApp {
    public static void main(String[] args) throws Exception {
        System.out.println("agent started before main: " + ObserveAgent.started());
        ObservedTarget target = new ObservedTarget();
        System.out.println("target method: " + target.work());
        System.out.println("target class load callbacks: " + ObserveAgent.observedLoads());
        System.out.println("target listed as loaded: "
                + ObserveAgent.targetIsLoaded(ObservedTarget.class));
        System.out.println("target class modifiable: "
                + ObserveAgent.modifiable(ObservedTarget.class));
        System.out.println("shallow object size positive: "
                + ObserveAgent.shallowPositive(target));

        boolean attempted = ObserveAgent.requestRetransform(ObservedTarget.class);
        System.out.println("retransformation requested: " + attempted);
        System.out.println("target retransform callbacks: "
                + ObserveAgent.observedRetransforms());
        System.out.println("target method unchanged: "
                + "DONE".equals(target.work()));
        System.out.println("transformer removed: " + ObserveAgent.remove());
    }
}

final class ObservedTarget {
    String work() {
        return "DONE";
    }
}
~~~

**File 3: `MANIFEST.MF`** — file text có dòng trống cuối:

~~~text
Manifest-Version: 1.0
Premain-Class: ObserveAgent
Can-Retransform-Classes: true

~~~

`Can-Retransform-Classes: true` rất quan trọng: nếu không có nó hoặc runtime từ chối capability, `Instrumentation.isRetransformClassesSupported()` có thể trả false. Nếu thiếu `Premain-Class`, `-javaagent` không tìm được entry point và JVM startup thất bại.

### Compile, đóng JAR và chạy

Chạy trong thư mục chứa ba files, với JDK 17 trở lên:

~~~bash
mkdir out
javac --release 17 -d out ObserveAgent.java ObservedApp.java
jar --create --file observe-agent.jar --manifest MANIFEST.MF -C out .
java -javaagent:observe-agent.jar=demo -cp observe-agent.jar ObservedApp
~~~

Các câu lệnh này cũng dùng được trong PowerShell hiện đại; nếu thư mục `out` đã tồn tại, không cần tạo lại. Với một bài thực hành độc lập, để đảm bảo sạch artifacts, nên dùng thư mục riêng. Trong production, agent JAR và application JAR thường **được phân phối riêng**; bài gộp cả hai vào một JAR để lệnh có thể tái lập với ít bước.

**Stdout chính xác đã được kiểm thử** trên **OpenJDK 24.0.2**, biên dịch với `javac --release 17`:

~~~text
agent option accepted: true
agent started before main: true
target method: DONE
target class load callbacks: 1
target listed as loaded: true
target class modifiable: true
shallow object size positive: true
retransformation requested: true
target retransform callbacks: 1
target method unchanged: true
transformer removed: true
~~~

### Vì sao có từng dòng output?

**`agent option accepted: true`:** JVM truyền chuỗi sau dấu bằng của `-javaagent:observe-agent.jar=demo` cho `premain`. Nó không tự parse thành key-value hay JSON. Đừng đưa secrets/access tokens vào agent options trong command line vì có thể xuất hiện ở process listings và logs.

**`agent started before main: true`:** `premain` đã lưu `Instrumentation` và đánh dấu khởi tạo trước khi `ObservedApp.main` chạy. Agent không nên thực hiện blocking I/O hoặc network retry vô hạn trong premain — một lỗi có thể khiến cả ứng dụng không khởi động.

**`target class load callbacks: 1`:** class `ObservedTarget` được định nghĩa sau khi transformer đăng ký; callback có `className="ObservedTarget"` và `classBeingRedefined==null`. Với một package class thực, tên sẽ ở dạng slash như `com/example/ObservedTarget`, không phải dotted class name.

**`target listed as loaded: true`:** `getAllLoadedClasses()` trả một snapshot có class target. Dùng nó trong demo được; **không** quét tất cả classes liên tục trong request hot path vì chi phí CPU/memory và lượng metadata lớn.

**`target class modifiable: true`:** JVM này cho phép điều chỉnh class target, nhưng ngay cả khi true, **một bytecode transformation bất hợp lệ vẫn thất bại**.

**`shallow object size positive: true`:** `getObjectSize(target)` trả ước lượng dung lượng lưu object. Nó **không** bao gồm toàn bộ object graph được tham chiếu, heap retained size, direct ByteBuffers/native memory hay kích thước dữ liệu serialize. Giá trị bytes cụ thể phụ thuộc JVM, architecture và object layout, vì thế demo chỉ kiểm `> 0` thay vì hardcode số bytes.

**`retransformation requested: true` và `target retransform callbacks: 1`:** agent có manifest capability, JVM hỗ trợ và target modifiable. Callback chạy lần thứ hai với `classBeingRedefined != null`. **Retransform không có nghĩa đã sửa hành vi** — transformer trả `null` nên `target method unchanged: true`.

**`transformer removed: true`:** subscription của transformer được gỡ. Theo Javadoc, một callback đã bắt đầu có thể vẫn tiếp tục được gọi sau `removeTransformer`, và **việc remove không tự hoàn tác class bytes đã được biến đổi trước đó**.

### Phạm vi và tính di động

Dòng `retransformation requested: true` và `target class modifiable: true` là kết quả của **runtime HotSpot đã thử nghiệm**, không phải universal truth. Với JVM thiếu retransform capability, ví dụ có thể in false; nếu muốn một bài kiểm thử portable, dùng capability gating và chỉ assert tương ứng với runtime.

Ví dụ này chỉ quan sát **một class cụ thể**; nó **không** thu mọi method call, không xuất traces, không ghi metrics ra hệ thống monitoring, không bật tự động can thiệp các JDK classes và **không tạo remote access**. Đó là lựa chọn có chủ đích để hiểu vòng đời `Instrumentation` với rủi ro thấp.

## 6. Đọc kỹ ClassFileTransformer trong Java 17+

Một transformer sử dụng override module-aware:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    if (!"com/example/Service".equals(className)) {
        return null;
    }
    // Quan sát metadata hoặc tạo một byte[] mới nếu cần transform.
    return null;
}
~~~

Đây là snippet **bên trong class implements ClassFileTransformer**, không phải một file Java độc lập. Method sáu tham số xuất hiện từ Java 9 và nhận `Module`. `className` dùng **internal form `com/example/Service`**, có thể `null` trong một số tình huống như hidden class; đừng dereference mà không kiểm tra. `loader` có thể `null` nếu bootstrap class loader, không tự tạo một ClassLoader để “thay thế” nó.

| Tham số | Ý nghĩa |
| --- | --- |
| `module` | Module của class cần transform |
| `loader` | Defining ClassLoader, có thể null cho bootstrap |
| `className` | Internal class name, slash-separated, có thể null |
| `classBeingRedefined` | Null khi load mới; class nếu redefine/retransform |
| `protectionDomain` | ProtectionDomain liên quan class (có thể null) |
| `classfileBuffer` | Bytes classfile đầu vào để đọc/biến đổi, **không sửa tại chỗ** |

**Transformers có thể được gọi song song bởi nhiều class-loading threads.** Biến đổi phải đủ thread-safe; tránh dùng shared mutable buffers, recursion không kiểm soát, khóa dài, synchronous exporters và thao tác tải chính class mà transformer đang instrument. Trong ví dụ, `AtomicInteger` bảo vệ counters và callback chỉ làm một phép so tên.

### Phân biệt tên class qua module/classloader

Hai classes có cùng internal name nhưng khác ClassLoader là **hai Class objects khác nhau**. Bộ lọc chỉ bằng `className` có thể áp nhầm instrument lên application plugin, test class loader, class do framework generate hoặc tenant khác. Trong production cần whitelist cả **module/loader/source code location** theo nhu cầu và tránh instrument agent/helper classes.

Một class trong module `java.base` khác class của ứng dụng trong unnamed module; việc dùng `Instrumentation.redefineModule` hay mở một package không làm chúng trở thành cùng classloader/trust domain.

### Những lỗi trong callback nguy hiểm

- Trả bytecode bị hỏng sẽ dẫn đến `ClassFormatError`, `VerifyError` hoặc `LinkageError`.
- Callback đọc `classfileBuffer` như UTF-8 text là sai: đó là **binary class file**, không phải Java source.
- Instrument bootstrap classes hoặc class đang phục vụ logger/exporter có thể gây infinite recursion.
- Không dùng mọi load event để gửi một HTTP request đồng bộ; latency có thể tăng mạnh hoặc deadlock.
- Không swallow mọi exception rồi tuyên bố đã instrument thành công. Javadoc có các quy tắc fail-open cho exceptions ở transformer chain; kiểm test/metrics chứ không tin “không có exception” nghĩa là method đã được biến đổi.
- Nếu cần bytecode rewriting, dùng API/thư viện được kiểm chứng thay vì sửa offsets/constant pool bằng cách thay bytes tùy tiện.

## 7. Retransformation và redefinition: hai cách điều chỉnh class đã loaded

| Tiêu chí | `retransformClasses` | `redefineClasses` |
| --- | --- | --- |
| Dữ liệu đầu vào | Class<?> và transformer chain đã đăng ký | `ClassDefinition(clazz, byte[])` cung cấp bytes thay thế |
| Cần manifest capability | `Can-Retransform-Classes` | `Can-Redefine-Classes` |
| Kiểm runtime | `isRetransformClassesSupported()` | `isRedefineClassesSupported()` |
| Kiểm class cụ thể | `isModifiableClass(clazz)` | Tương tự |
| Có gọi transformer? | Có, theo các quy tắc capable/incapable | Transformers có thể tham gia redefine |
| Ứng dụng thực tế | Thêm/đổi instrumentation trên class đã loaded | Thay bytes của một class theo contract hỗ trợ |
| Được thêm method/field mới vô hạn? | Không, có structural restrictions | Không, có structural restrictions |
| Active stack frames | Frame đang thực thi có thể tiếp tục dùng old bytecodes | Frame đang thực thi có thể tiếp tục dùng old bytecodes |
| Có reset static fields/instances không? | Không tự reset | Không tự reset |
| Ngăn mọi race khi deploy? | Không | Không |

**Retransform không phải “đọc lại file .class trên disk”.** Javadoc mô tả JVM bắt đầu từ một representation của initial class-file bytes, tái dùng kết quả trước của những transformers không capable và chạy lại transformers capable. Constant pool/layout của bytes đầu vào **không nhất thiết giống từng byte** với nguồn gốc trên disk.

Một method có stack frame đang active khi redefine/retransform có thể **tiếp tục chạy old bytecode** cho frame ấy, trong khi lần gọi mới sử dụng version đã update. Vì thế không dùng hot swap để sửa tức thì mọi business transaction đang chạy; muốn an toàn cần rollout/rollback strategy ở application level.

### Capability checks trong code

~~~java
Instrumentation inst = ...;      // JVM đã truyền vào premain/agentmain.
Class<?> target = ...;           // Đúng class đã loaded.
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

Đây là snippet bên trong method có `Instrumentation`. Khi capability không có, **không** cố gọi rồi catch tổng quát và bỏ qua; hãy báo “unsupported” trong telemetry của công cụ. Ngay cả nếu cả hai checks true, structural restrictions/invalid bytes vẫn có thể khiến call thất bại.

Với `redefineClasses` phải chuẩn bị `ClassDefinition` mới và cân nhắc các lớp liên quan trong cùng một batch; đừng tự tạo unsigned/unverified replacement bytecode từ remote input. Một agent quan sát đơn giản thường **không** cần redefine capability.

### Vì sao manifest capability không phải luôn có?

Khả năng mutate lớp là quyền mạnh. Agent chỉ đếm class loads nên có thể chọn không yêu cầu `Can-Redefine-Classes`. Với công cụ cần retransform rõ ràng, đặt `Can-Retransform-Classes: true` trong manifest và kiểm VM. Không cấp cả hai chỉ vì “để phòng khi cần”.

## 8. Java 24+: Class-File API chuẩn giúp viết bytecode transformer an toàn hơn

Từ **Java 24**, `java.lang.classfile` trở thành **API chuẩn, không còn preview** (JEP 484). Nó cung cấp `ClassFile`, `ClassModel`, `ClassTransform`, `CodeTransform` và những representation có kiểu của instructions/constant pool. Java 17 **không có API ổn định này**; để viết transformer chạy trên Java 17, có thể dùng **thư viện bytecode tương thích** đã được review như ASM/Byte Buddy theo dependency governance hoặc giữ ở chế độ quan sát như ví dụ 1.

Để chứng minh sự khác nhau giữa “chỉ quan sát” và “thay bytecode thật”, ví dụ số 2 cố ý **thay đúng một literal `"ORIGINAL"` thành `"INSTRUMENTED"`** trong method `MetricTarget.value()`. Đây là **một transformation làm đổi hành vi** để có assertion rõ ràng, **không phải thiết kế monitoring production được khuyến nghị**. Instrumentation thực tế nên **bổ sung phép đo/counters/spans**, giữ business semantics và tránh thay dữ liệu kết quả.

### File 1: BytecodeAgent.java — Java 24+

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.ConstantInstruction;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class BytecodeAgent {
    private static final AtomicInteger changedClasses = new AtomicInteger();

    public static void premain(String args, Instrumentation instrumentation) {
        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                    Class<?> redefined, ProtectionDomain domain, byte[] bytes) {
                if (!"MetricTarget".equals(name)) {
                    return null;
                }
                ClassFile cf = ClassFile.of();
                CodeTransform changeLiteral = (builder, element) -> {
                    if (element instanceof ConstantInstruction.LoadConstantInstruction value
                            && "ORIGINAL".equals(value.constantValue())) {
                        builder.ldc("INSTRUMENTED");
                    } else {
                        builder.with(element);
                    }
                };
                byte[] rewritten = cf.transformClass(cf.parse(bytes),
                        ClassTransform.transformingMethodBodies(
                                method -> method.methodName().equalsString("value"),
                                changeLiteral));
                changedClasses.incrementAndGet();
                return rewritten;
            }
        };
        instrumentation.addTransformer(transformer);
    }

    public static int changes() {
        return changedClasses.get();
    }
}
~~~

### File 2: BytecodeApp.java

~~~java
public final class BytecodeApp {
    public static void main(String[] args) {
        System.out.println("target result after instrumentation: "
                + new MetricTarget().value());
        System.out.println("transformed class count: " + BytecodeAgent.changes());
    }
}

final class MetricTarget {
    String value() {
        return "ORIGINAL";
    }
}
~~~

### File 3: BYTECODE.MF

~~~text
Manifest-Version: 1.0
Premain-Class: BytecodeAgent

~~~

Ở đây không cần `Can-Retransform-Classes` vì transformation xảy ra khi class `MetricTarget` được **define lần đầu** và transformer được đăng ký trong `premain`. Không gọi redefine/retransform và không cần xin thêm capability.

### Build và chạy với JDK 24+

~~~bash
mkdir out24
javac --release 24 -d out24 BytecodeAgent.java BytecodeApp.java
jar --create --file bytecode-agent.jar --manifest BYTECODE.MF -C out24 .
java -javaagent:bytecode-agent.jar -cp bytecode-agent.jar BytecodeApp
~~~

**Stdout chính xác** đã chạy bằng OpenJDK 24.0.2:

~~~text
target result after instrumentation: INSTRUMENTED
transformed class count: 1
~~~

Không dùng `javac --release 17` cho ví dụ này: `java.lang.classfile` chuẩn chỉ có từ Java 24. Nếu ứng dụng target đang ở Java 17, có thể dùng một agent build cho Java 24 trên **JVM 24+ đang chạy app classfiles Java 17**, nhưng **không** chạy chính agent compiled Java 24 trên một JVM chỉ có Java 17.

### Giải thích bytecode transform

1. `Instrumentation.addTransformer(...)` đăng ký callback trước khi `MetricTarget` được define.
2. Callback lọc tên internal `MetricTarget`; các classes không liên quan trả `null`, tránh instrument cả JVM.
3. `ClassFile.of().parse(bytes)` xây một `ClassModel` từ classfile hợp lệ.
4. `ClassTransform.transformingMethodBodies(...)` chỉ chọn method có tên `value`. Ví dụ cố tình nhỏ: trong production nên match cả **descriptor** và classloader/module để không áp nhầm overload.
5. `CodeTransform` duyệt các `CodeElement`; khi thấy `ConstantInstruction.LoadConstantInstruction` có value `"ORIGINAL"`, builder phát instruction `ldc("INSTRUMENTED")`. Tất cả code elements khác được giữ qua `builder.with(element)`.
6. `cf.transformClass(...)` tạo **byte[] mới** hợp lệ. Agent trả bytes ấy cho JVM để define target.
7. `BytecodeApp` gọi `new MetricTarget().value()` và nhận `INSTRUMENTED`, nên bài này thực sự chứng minh bytecode được đổi, **khác** `return null` của ví dụ 1.

**Giới hạn của bài học:** thay string constant chỉ là phép đổi hành vi có kiểm soát để đo tác dụng API, không phải auto-instrumentation đầy đủ. Với timing một method thực tế phải xử lý method entry/exit, returns, exceptions, constructors, stack map frames, class hierarchies, context propagation và recursion; các bytecode transformations đó cần test kỹ hoặc dùng agent instrumentation SDK đã được review.

### Vì sao không sửa mảng bytes bằng thao tác chuỗi?

Class file có constant pool, bytecode offsets, attributes, metadata, stack maps và constraints theo JVM Specification. Thay text bytes trực tiếp có thể phá indexes, version hoặc verification. Class-File API từ Java 24 cung cấp models/builders để thao tác có kiểu; **nhưng API không tự chứng minh business semantics vẫn tương đương**. Một transformer biên dịch thành công vẫn có thể gây lỗi logic sau khi chạy, nên cần integration tests và staged rollout.

## 9. Agentmain, Attach API và JEP 451: giới hạn nạp động

Trong hệ thống cũ, một công cụ có thể dùng **Attach API** để nạp agent khi process đã chạy, thông qua `Agent-Class` và `agentmain(...)`. Cơ chế này **không phải** giải pháp nên chọn mặc định cho observability production hiện nay.

**JEP 451, đưa vào JDK 21**, bắt đầu cảnh báo khi agent được nạp động và chuẩn bị một chính sách **integrity by default** chặt hơn: các phiên bản JDK tương lai có thể không cho phép dynamic agent loading mặc định. Javadoc `java.lang.instrument` Java SE 25 cũng nói việc nạp agent sau startup phụ thuộc implementation và trên HotSpot có option **`-XX:+EnableDynamicAgentLoading`** để explicit opt-in/suppress warnings theo runtime. Vì chính sách thay đổi theo JDK build và cấu hình, **đọc docs của đúng runtime đang dùng**, không tuyên bố mọi JDK phiên bản đều tự cho phép attach.

### Phân biệt ba trường hợp

| Cơ chế | Entry point | Cách vận hành phù hợp |
| --- | --- | --- |
| Startup agent `-javaagent:path` | `premain` | Được chủ sở hữu ứng dụng/deployment cấu hình rõ, ưu tiên cho monitoring |
| Executable JAR `Launcher-Agent-Class` | `agentmain` trước application main | Khi cần agent đóng cùng ứng dụng và launcher hỗ trợ |
| Dynamic attach agent | `agentmain` khi JVM đang chạy | Chỉ nếu VM/policy/permissions cho phép; cần audit, sự đồng ý của owner |

Đừng nhầm **`agentmain`** với **application `main`**. Một method `agentmain` không làm ứng dụng tự động được monitor nếu không có cơ chế launcher/attach thực tế. Và chỉ thêm `Agent-Class` vào manifest không tự khiến JVM đang chạy nạp JAR.

### Ví dụ chữ ký agentmain (không tự chạy)

~~~java
public static void agentmain(String args, Instrumentation inst) {
    // Khởi tạo transformer và telemetry pipeline sau startup,
    // chỉ khi deployment và JVM đã chủ động cho phép dynamic load.
}
~~~

Đây là **snippet trong một agent class**, không phải file standalone. Một agent có cả `premain` và `agentmain` có thể gọi chung helper initialization, nhưng cần xử lý idempotency: tránh đăng ký cùng transformer hoặc exporter hai lần.

**Không nên hướng dẫn bypass kiểm soát JVM để nạp JAR vào process không do mình quản lý.** Dynamic attach mở khả năng chạy code cùng quyền process mục tiêu và sửa bytecode. Với môi trường thực tế, chỉ dùng trên JVM thuộc quyền quản lý, với quy trình thay đổi, agent JAR đã được phê duyệt, quyền OS/Attach phù hợp và log sự kiện.

### Vì sao chọn -javaagent cho bài này?

- Có cấu hình triển khai rõ trong process startup.
- Không dựa vào việc JDK cho phép attach một JVM đang chạy.
- Có thể quan sát classes app được tải sau premain.
- Dễ rollback bằng cách gỡ startup flag và restart.
- Đơn giản để test CI: cùng app + JDK + JAR/version tạo cùng kết quả.
- Có quyền quản lý để kiểm signature/SBOM/checksum agent JAR trước deployment.

Agent load lúc startup **không bị JEP 451 coi là dynamic agent load** theo mô tả cảnh báo đó. Nhưng mọi agent vẫn phải được kiểm duyệt vì cùng chạy trong process Java.

## 10. Module system: Java 9+ và tác động với agent

Từ Java 9, `ClassFileTransformer.transform(...)` có dạng module-aware như hai chương trình. Một class trong **named module** có khả năng nhìn thấy package/method khác với một class trên classpath trong **unnamed module**.

Những vấn đề cần biết:

- `module` parameter cho biết module được transform.
- `loader` parameter cho biết defining classloader; có thể `null` cho bootstrap.
- Agent class thường được system classloader tải và nằm trong unnamed module theo package specification.
- JVM cung cấp cơ chế readability cho transformed code dùng helper class từ agent/bootstrap unnamed module trong những trường hợp được đặc tả, nhưng điều đó **không** giải quyết mọi inaccessible/non-public API.
- `Instrumentation.redefineModule(...)` cho phép **bổ sung** reads/exports/opens/uses/provides, khi module có thể được chỉnh. Đây là quyền mạnh và nên xem là thay đổi security boundary.
- CLI `--add-opens module/package=target` hay `--add-exports` cũng là thay đổi ranh giới truy cập; chỉ dùng khi agent được kiểm chứng và thật sự cần.

Không ép mở `java.base/java.lang=ALL-UNNAMED` một cách mù quáng để “sửa” một `InaccessibleObjectException`. Hãy xác định agent cần loại truy cập gì, kiểm sự tương thích của phiên bản thư viện, ưu tiên public APIs và giảm phạm vi module được mở.

### Helper classes trong bootstrap

`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` hỗ trợ thêm helper code cần hiển thị cho các lớp do bootstrap loader định nghĩa. Nhưng helper loaded qua bootstrap không thể đơn giản phụ thuộc các class chỉ nằm trên system classpath; classloader isolation và package placement có thể gây `NoClassDefFoundError` hoặc `LinkageError`.

Các trường hợp instrument `java.base` classes cần kiểm thử riêng, classpath/module packaging cẩn thận, và tránh recursion khi helper tự gọi đến các thư viện đang bị instrument. **Trong ví dụ 1 và 2, chúng ta không cần mở module hoặc append bootstrap JAR** vì chỉ instrument application classes trong cùng demo JAR.

## 11. Thiết kế observability pipeline với agent

Một công cụ quan sát hiện đại không dừng ở việc thêm transformer:

~~~text
Application method call
       |
Instrumented bytecode / telemetry hooks
       |
Span / metric / event creation
       |
Trace context propagation
       |
Sampling / filtering / redaction
       |
Bounded queue + aggregation
       |
Batch exporter (OTLP or chosen backend)
       |
Authenticated TLS transport
       |
Collector / metrics and trace backend
       |
Dashboard / alerting / SLO
~~~

**Không tự export trong ClassFileTransformer.transform**. Callback xảy ra trong đường nạp lớp, nơi code của bạn có thể còn chưa được initialize hoàn toàn. Nếu callback tạo client HTTP, load serializer, initialize logging và lại nạp classes, có thể bị recursive class loading, deadlock hoặc startup latency cao. Transformer nên chỉ làm công việc bytecode transformation **ngắn, deterministic**; telemetry hooks ở method runtime gửi vào pipeline đã khởi tạo cẩn thận.

### Metrics và traces nên được tạo thế nào?

- Với **traces**, tạo span cho ranh giới request, RPC hoặc database operation; đảm bảo context propagation qua threads/executors và virtual threads, theo conventions của hệ telemetry đang dùng.
- Với **metrics**, aggregate counters/histograms cho số lượng, lỗi, latency; không tạo metric mới cho từng user ID, order ID hay raw URL có cardinality vô hạn.
- Với **logs**, dùng correlation IDs đã sanitize; không dump method arguments chứa credentials hoặc PII.
- Với **sampling**, chọn tỷ lệ phù hợp, có bias awareness, không ghi quá nhiều events vào synchronous hot path.
- Với **errors**, tránh nuốt exceptions hoặc tự biến exception thành success; preserve stack trace và application behavior.
- Với **export**, giới hạn queue/batch/retries/timeouts; không block request thread vô hạn khi backend metrics chết.

**OpenTelemetry Java agent** là ví dụ hiện hành của zero-code auto-instrumentation: nạp bằng `-javaagent:path/to/opentelemetry-javaagent.jar`, hỗ trợ nhiều thư viện và có cấu hình exporter/context propagation. Không cần tự viết agent như bài thực hành nếu nhu cầu production đã được công cụ này đáp ứng. Dùng bản agent phù hợp với JDK/framework và governance, cấu hình service name/resource attributes, exporter endpoint, sampling và TLS secrets theo tài liệu dự án.

Ví dụ cú pháp từ tài liệu OpenTelemetry:

~~~bash
java -javaagent:path/to/opentelemetry-javaagent.jar \
  -Dotel.service.name=orders-api \
  -jar application.jar
~~~

Đây là mẫu Unix shell giả định bạn có JAR **đã kiểm checksum/version**. Không tải file qua URL chưa kiểm, không chèn secrets vào command-line. Với Windows PowerShell dùng một dòng hoặc nối dòng theo cú pháp PowerShell. Không tự khẳng định agent sẽ xuất dữ liệu thành công nếu exporter/collector chưa cấu hình.

## 12. JFR, MXBeans và bytecode agent bổ sung nhau thế nào?

**JFR** thu runtime events như allocation, GC, thread scheduling, lock contention, profile samples; thường là lựa chọn tốt cho phân tích performance. Có thể tạo custom JFR events bằng `jdk.jfr.Event` nếu cần, không bắt buộc sửa bytecode cho từng method.

**JMX/MXBeans** cung cấp trạng thái và counters của JVM/application, ví dụ `ThreadMXBean`, `MemoryMXBean`, `GarbageCollectorMXBean`, có thể giám sát theo thời gian. MXBean không tự tạo distributed traces hay đi qua mọi HTTP client library.

**Java agent** thay đổi/quan sát class definitions, có thể gắn telemetry hooks vào các framework APIs mà app không trực tiếp instrument. Agent không tự thay JFR hay JMX: nó là một công cụ trong kiến trúc observability.

| Câu hỏi | Chọn đầu tiên |
| --- | --- |
| Tại sao GC pause tăng? | JFR/GC metrics |
| HTTP request mất thời gian ở đâu qua nhiều services? | Distributed tracing/OpenTelemetry |
| Có bao nhiêu platform threads và CPU time? | ThreadMXBean/JFR |
| Ứng dụng đang tải class nào? | Class loading metrics, JFR hoặc agent callback |
| Muốn quan sát một thư viện bên thứ ba không sửa source? | Auto-instrumentation agent nếu supported |
| Muốn biết những class nào có thể retransform? | Instrumentation capability/loaded classes |
| Muốn đo retained heap chính xác của object graph? | Heap analysis/profiler; không dùng getObjectSize đơn độc |
| Cần alerting/SLI liên tục | Metrics/exporter + backend, không chỉ ClassFileTransformer |

## 13. Performance: giảm footprint và tránh tự gây sự cố

### 13.1. Chi phí ở class loading

Transformer có thể được gọi **rất nhiều lần** trong lúc JVM khởi động và khi các frameworks tạo classes. Hãy lọc cực nhanh theo module/package/class name trước khi parse classfile. Đừng parse mọi file rồi mới quyết định có instrument hay không.

### 13.2. Chi phí ở runtime methods

Instrumentation thêm gọi telemetry vào hot methods có thể:
- tăng số instructions, allocations, CPU time;
- ảnh hưởng JIT inlining và tối ưu hóa;
- làm stack traces/exception paths phức tạp;
- tạo additional objects và GC pressure;
- thay behavior khi thread scheduling thay đổi.

Benchmark **có và không có agent** ở cùng load/JDK/config, theo dõi p50/p95/p99 latency, CPU, GC, allocation, startup time và memory footprint. Không chỉ nhìn output của một unit test rồi tuyên bố “zero overhead”.

### 13.3. Loại trừ agent/helper/exporter classes

Một trace exporter thường dùng HTTP client, DNS, thread pools và logger. Nếu agent lại instrument chính các thư viện mà exporter sử dụng, có thể tạo vòng:
`instrumented HTTP call → export span → instrument exporter HTTP call → export thêm span → ...`

Định nghĩa excludes cho agent classes, exporter libraries hoặc cơ chế suppression/context instrumentation đúng theo SDK. Không giải quyết vòng này bằng cách bắt exception ở cuối recursion.

### 13.4. Thread safety trong callback

`ClassFileTransformer` có thể chạy trên nhiều class loaders và threads. Mọi mutable state phải thread-safe. Chương trình 1 dùng `AtomicInteger`, còn transformer thứ hai không sửa shared data ngoại trừ một counter. Đừng dùng một `ByteArrayOutputStream` hoặc visitor có mutable state dùng chung giữa các callbacks mà không reset/cô lập.

### 13.5. Cấu hình fail-open/fail-closed có chủ đích

Một observability agent thường nên **fail-open đối với luồng nghiệp vụ** (không để exporter outage làm ứng dụng chết) nhưng **fail-closed đối với integrity/security policy** khi bytecode không hợp lệ, dữ liệu agent không đáng tin hoặc cấu hình cấm. Không có một chiến lược error handling phù hợp mọi deployment:
- Lỗi telemetry export: giới hạn và drop sau deadline + metrics.
- Lỗi class transformation đã được yêu cầu: báo sự cố, không ngầm tuyên bố instrument thành công.
- Lỗi agent trong premain: có thể khiến JVM startup abort; test trên canary.
- Lỗi nhầm critical class: rollback bằng **remove flag và restart** thường đáng tin hơn cố hot-uninstrument mọi class.

## 14. Bảo mật của agent: privileged code trong JVM

Agent có thể nhìn class metadata, class bytes và đôi khi dữ liệu runtime nhạy cảm. Chạy một agent tương tự chấp thuận **một thư viện có quyền rất rộng trong process**:

| Rủi ro | Biện pháp |
| --- | --- |
| JAR bị thay hoặc supply-chain compromise | Pin version, checksum/signature, SBOM, allowlisted artifacts |
| Agent đọc arguments/headers mang secret | Redaction, denylist sensitive fields, không log raw payloads |
| Telemetry xuất ra ngoài môi trường tin cậy | Collector allowlist, TLS, auth, egress policy |
| Instrument nhầm internal/JDK classes | Include/exclude scopes, integration tests, classloader filters |
| Remote/dynamic attach không kiểm soát | Chính sách JEP 451, explicit opt-in và owner approval |
| Mở module không cần thiết | Least privilege, audit `--add-opens`/`redefineModule` |
| Agent overhead/DoS | Bounded queues, sampling, circuit breaker, perf budgets |
| Agent bị lỗi trong premain | Canary startup checks, rollback flag/version |
| Object retention qua static caches | Weak keys/loader lifecycle, remove listeners và close exporters |
| Long-lived classes bị retransform nhiều lần | Idempotent transformation, versioned state, compatibility tests |
| Accidentally exposing heap/class names | Quyền truy cập JFR/JMX/profiler/trace backend, retention policy |

**Không dùng agent như cách vượt kiểm soát bảo mật hoặc sửa một JVM không được cấp quyền.** Hãy coi JAR agent là một artifact đã được security review như application code, và đánh giá cả license/dependencies của thư viện instrumentation.

### Vì sao getObjectSize không dùng để định giá heap người dùng?

`Instrumentation.getObjectSize(obj)` trả ước lượng kích thước **shallow storage** của object, với alignment/layout phụ thuộc JVM. Nếu đối tượng giữ tham chiếu tới Map, List, byte array, direct buffer hoặc native memory, kết quả không phản ánh toàn bộ retained heap. Để phân tích memory leak, dùng heap dump, JFR allocation profiling hoặc profiler chuyên dụng có chính sách bảo mật và giới hạn overhead.

## 15. ClassLoader, modules và vòng đời agent trong ứng dụng lớn

Ứng dụng server/plugin có thể tạo nhiều classloaders cho cùng một class name. Một agent không nên:
- Giữ strong reference vô hạn tới mọi ClassLoader trong static map;
- Giữ `Class<?>` làm key của cache vĩnh viễn khi ứng dụng có hot redeploy;
- Giả một class name xác định duy nhất một definition;
- Tự động đặt helper vào bootstrap nếu không thực sự cần;
- Quên dọn executor, scheduler và exporter lúc shutdown.

Với cache per classloader, cân nhắc weak references hoặc lifecycle hooks và chống memory leak. Không cache một byte[] class file vô thời hạn cho mọi class. Khi có retransform nhiều lần, phải biết transformer chain và phiên bản class hiện tại; một thay đổi không idempotent có thể chèn cùng hook hai lần.

### Repeated retransform không phải repeated business operation

Trong ví dụ 1, target callback load=1, retransform=1, nhưng `ObservedTarget.work()` được gọi hai lần mà **không thay kết quả**. Callback `transform` xảy ra trong class definition/redefinition/retransformation, **không** xảy ra mỗi lần method invocation. Muốn đo mỗi invocation, bạn phải **thực sự thêm bytecode hooks** hoặc instrument qua các API thư viện đã có. Nhầm lẫn này gây ra metrics sai khi dùng class-load count làm request count.

### Metadata vs application execution

Không dùng `ClassFileTransformer` để đo thời lượng thực thi một method chỉ bằng thời gian chạy callback. Thời lượng callback chỉ phản ánh hoạt động **instrumentation**, không phải hoạt động method trong ứng dụng. Với production method latency, dùng tracing/timing hooks ở runtime.

## 16. Troubleshooting: lỗi nào nằm ở đâu?

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Failed to find Premain-Class manifest attribute` | JAR thiếu manifest entry | Kiểm `jar --describe-module`/`jar tf` và manifest |
| JVM không gọi `premain` | Thiếu `-javaagent`, sai path/class name | Kiểm command line và tên class trong manifest |
| `ClassNotFoundException` khi nạp agent | Agent JAR thiếu class/helper/dependency | Đóng gói phù hợp system loader/JPMS |
| `NoClassDefFoundError` từ helper | Agent helper sai loader/module | Kiểm dependency placement/bootstrap |
| Agent chạy nhưng không thấy target class | Target đã loaded trước addTransformer, sai filter | Kiểm className internal form; retransform nếu supported |
| className có slash nhưng filter dùng dấu chấm | Không match | Dùng `com/example/Service` |
| `classBeingRedefined==null` | Đang class load mới | Điều kiện bình thường, không phải lỗi |
| transformer trả `null` mà hành vi không đổi | Null nghĩa no transform | Trả well-formed new bytes nếu muốn thay |
| `isRetransformClassesSupported()==false` | Manifest không xin, JVM không cấp | Kiểm `Can-Retransform-Classes` và runtime |
| `UnmodifiableClassException` | Class cụ thể không modifiable | Kiểm `isModifiableClass`, không force |
| `UnsupportedOperationException` khi retransformation | Capability/loại transform không hỗ trợ | Không retry vô hạn, báo giới hạn |
| `VerifyError` hoặc `ClassFormatError` | Bytecode/stack maps invalid | Sử dụng Class-File API/thư viện chuẩn và test |
| `LinkageError` sau transformation | Classloader/module/definition mismatch | Tách loader/module và tránh structural changes |
| Startup bị treo | Transformer gọi I/O hoặc recursion | Filter trước, bỏ synchronous exporter |
| Không có retransform callback dù load có | addTransformer không canRetransform true | Đăng ký với flag đúng, manifest/runtime cho phép |
| target kết quả còn `ORIGINAL` khi test ví dụ 2 | Target đã loaded trước transformer hoặc method filter sai | Kiểm JAR/class loading order và name |
| `NoClassDefFoundError: java/lang/classfile/...` | Chạy ví dụ Java 24 trên JDK cũ | Dùng JDK 24+ hoặc bytecode library tương thích |
| JAR không có `Agent-Class` khi attach | Dynamic manifest thiếu | Chỉ nạp nếu runtime có quyền và policy cho phép |
| Cảnh báo dynamic agent loading | JEP 451/HotSpot policy | Ưu tiên startup `-javaagent`, xem docs runtime |
| `InaccessibleObjectException` | Module chưa mở package cần reflection | Xem public API và cấp đúng scope, không mở rộng vô tội vạ |
| `getObjectSize` trả số khác CI | Layout/architecture/JDK khác | Kiểm tính dương/chấp nhận approximate |
| `removeTransformer` xong mà behavior vẫn instrumented | Class bytes đã biến đổi trước | Rollback với class retransform/redefine đã kiểm hoặc restart |
| Traces/metrics thiếu | Chỉ có transformer chứ chưa có hooks/exporter | Thiết kế pipeline và thực thi runtime hooks |
| Logs lộ request tokens | Telemetry payload không redact | Data minimization + redaction policy |
| JFR có events nhưng OTel trace không có | Hai hệ tín hiệu khác contract | Cấu hình JFR/profiler và tracing riêng |
| Ứng dụng chậm sau deploy | Instrument quá nhiều hot paths | Sampling/excludes/performance profiling, rollback |
| Agent JAR từ nguồn lạ | Supply-chain risk | Không chạy, verify provenance |

### Test bằng cách chạy không có agent

~~~bash
java -cp observe-agent.jar ObservedApp
~~~

Đây **không phải** test của bài vì `ObservedApp` gọi trực tiếp `ObserveAgent.started()/requestRetransform` và giả định premain đã cấp Instrumentation. Trong một ứng dụng production, thư viện business logic không nên **bắt buộc** agent luôn có mặt như demo này. Bài cố tình cho app gọi helper để hiển thị trạng thái; với production, giữ ứng dụng chạy bình thường khi agent không được cài bằng API telemetry no-op/fallback rõ ràng.

## 17. Bảng kiểm thử cho agent hiện đại

| Kịch bản | Kỳ vọng |
| --- | --- |
| `-javaagent` JAR manifest có Premain-Class | JVM gọi premain trước main |
| Thiếu Premain-Class khi startup | JVM abort/ báo manifest error |
| Truyền `=demo` option | premain nhận chuỗi demo |
| Agent không có classloader dependencies thiếu | Startup success |
| Class target nạp sau transformer | Callback thấy đúng className |
| Class name có package | Dùng slash internal form |
| ClassLoader khác nhau cùng binary name | Filter không nhầm identity |
| Class loaded trước transformer | Không tự có load callback sau đó |
| Transformer trả null | Application behavior không đổi |
| Transformer trả valid byte[] | Application dùng class bytes đã đổi |
| ClassFile API Java24+ | Biên dịch/chạy được trên JDK24+, không JDK17 |
| Transformer match method descriptor | Không đổi nhầm overload |
| Transformer thay `ORIGINAL` → `INSTRUMENTED` | Output thay thật, một class được chỉnh |
| `Can-Retransform-Classes` + runtime supported | isRetransformClassesSupported true |
| Retransform một class modifiable | capable transformer callback có classBeingRedefined |
| Retransform class không modifiable | Fail/không cố đổi |
| Basic observation-only after retransform | Target method vẫn trả DONE |
| removeTransformer | Gỡ đăng ký, có thể còn in-flight callbacks |
| Snapshot getAllLoadedClasses | Có target Class, nhưng không phải lịch sử |
| getObjectSize(target)>0 | Shallow estimate, không assert exact byte count |
| Agent JAR có dependencies | Classloader/module resolution đúng |
| Named module target | Agent module/readability/opens đúng |
| Multiple agents | Xác định transformer order và kết quả composition |
| Bad transformed bytes | Detected by JVM verification/linkage |
| Callback recursively triggers itself | Có guard/exclusion, không deadlock |
| Agent startup with export backend down | App vẫn đạt policy fail-open theo thiết kế |
| Bytecode transformer on JDK new class version | Hỗ trợ/cảnh báo rõ; không silently corrupt |
| Java 21+ dynamic attach | Chính sách cảnh báo/opt-in theo runtime |
| Unauthorized dynamic attach | Không được phép, event được audit |
| Trace context across threads | Parent/span propagation đúng |
| Sensitive method args | Redacted, không gửi secrets |
| Metrics dimensions | Bounded cardinality |
| Agent memory/CPU overhead | Trong SLO budget |
| Agent removal/rollback | Xác định cần restart hay untransform |
| ClassLoader unload/redeploy | Cache không giữ references vô hạn |
| Container custom JRE missing java.instrument | Báo runtime module issue |
| OpenTelemetry agent version upgrade | Test regression JDK/framework/telemetry exporter |
| JFR complement | Kiểm events riêng với agent traces |

## 18. Những nhầm lẫn phổ biến

| Nhầm lẫn | Giải thích chính xác |
| --- | --- |
| “Agent là thư viện đặt vào classpath.” | Cần entrypoint + manifest và cơ chế `-javaagent`/attach |
| “premain chạy sau application main.” | Startup premain chạy trước main |
| “premain nhìn được mọi class JVM lúc class-load.” | Một số classes đã loaded trước premain |
| “Agent có thể new Instrumentation.” | Interface do JVM cung cấp qua entrypoint |
| “ClassFileTransformer callback là mỗi method call.” | Nó được gọi ở class definition/redefine/retransform |
| “Return null nghĩa JVM bỏ class.” | Null là không thay classfile |
| “Sửa trực tiếp byte[] classfileBuffer là đúng.” | Không mutate input; tạo byte[] mới |
| “getAllLoadedClasses là event stream.” | Đây là snapshot tại thời điểm gọi |
| “getObjectSize là retained heap size.” | Chỉ shallow estimate, implementation-dependent |
| “isModifiableClass true nghĩa mọi thay đổi đều hợp lệ.” | Vẫn có structural/bytecode restrictions |
| “retransform tự thêm bất kỳ fields/methods mới.” | JVM hạn chế structural changes |
| “removeTransformer khôi phục bytecode gốc.” | Không tự undo transformations đã áp |
| “Can-Retransform-Classes chỉ là metadata trang trí.” | Nó tham gia cấp capability thực |
| “Can-Redefine-Classes luôn cần cho mọi agent.” | Chỉ xin khi cần redefine |
| “JEP 451 cấm hoàn toàn mọi -javaagent.” | JEP nhắm nạp động; startup -javaagent là cơ chế rõ ràng |
| “Dynamic agent loading luôn được bật.” | Còn tùy JDK/version/flag/permissions |
| “SNI/module/loader không liên quan instrumentation.” | Module và classloader quyết định identity/access |
| “Agent trong unnamed module mở mọi package private.” | Không; JPMS access constraints vẫn áp |
| “Java 17 có java.lang.classfile API ổn định.” | API chuẩn từ Java 24 (JEP 484) |
| “Có output transformed class nghĩa production-safe.” | Ví dụ thay hành vi; cần correctness/perf testing |
| “OTel agent và JFR là cùng một hệ thống.” | Một bên auto-instrument traces, bên kia JVM event recording |
| “Java agent export tracing tự động nhờ Instrumentation.” | Phải có hooks/SDK/exporter/context |
| “Có JAR agent là được phép nạp vào bất kỳ JVM.” | Quyền quản lý, integrity/security policy bắt buộc |
| “Transformer blocking I/O không ảnh hưởng application.” | Class loading/startup có thể bị chậm hoặc deadlock |
| “Agent static cache ClassLoader không nguy hiểm.” | Có thể ngăn class unloading, gây memory leak |
| “Method latency bằng thời gian transform callback.” | Callback đo class definition, không phải invocation |
| “Không có exception là bytecode chắc chắn đúng.” | Phải kiểm outputs, bytecode validation và integration behavior |

## 19. Câu hỏi tự kiểm tra

1. Java agent là gì? — Code JVM tải qua cơ chế agent để quan sát/biến đổi classes.
2. API tiêu chuẩn? — `java.lang.instrument` trong `java.instrument`.
3. Ai truyền Instrumentation instance? — JVM, qua premain/agentmain.
4. Cách khởi động rõ ràng cho production? — `-javaagent:path/to/agent.jar` với JAR đáng tin.
5. Manifest startup cần gì? — `Premain-Class`.
6. Agent load sau startup cần gì? — `Agent-Class` và agentmain, runtime policy cho phép.
7. Premain chạy khi nào? — Trước application main.
8. Tất cả classes có chắc loaded sau premain? — Không.
9. addTransformer nhận gì? — `ClassFileTransformer` callback.
10. Callback có thể chạy trên nhiều threads không? — Có.
11. className có dấu chấm hay slash? — Internal name với slash.
12. classBeingRedefined null khi nào? — Class definition mới.
13. return null nghĩa gì? — Không thay bytes.
14. Có nên mutate classfileBuffer không? — Không.
15. isRetransformClassesSupported phụ thuộc gì? — Manifest capability và JVM.
16. isModifiableClass có đảm bảo mọi transform thành công? — Không.
17. retransformClasses làm gì? — Yêu cầu chạy lại transformation cho class loaded.
18. redefineClasses khác gì? — Cung cấp ClassDefinition với bytes mới.
19. Vì sao có structural restrictions? — JVM phải giữ compatible class/runtime state.
20. Active frame có thể tiếp tục chạy old bytecode không? — Có.
21. removeTransformer có tự rollback bytes không? — Không.
22. getObjectSize đo gì? — Shallow approximation, không phải retained heap.
23. getAllLoadedClasses trả gì? — Snapshot Class[] hiện loaded.
24. addTransformer(..., false) khác true? — False không tham gia rerun capable transformer khi retransform.
25. Agent Java 17 demo có đổi behavior không? — Không, callback return null.
26. Vì sao vẫn thấy retransform callback? — Cả manifest/runtime đều cho capability và target modifiable.
27. Example Java 24 cần API mới nào? — `java.lang.classfile`.
28. Class-File API ổn định từ JDK nào? — 24.
29. Java24 demo biến literal gì? — `ORIGINAL` thành `INSTRUMENTED`.
30. Nó có là phương pháp auto-observability production tốt không? — Không, chỉ chứng minh transformation thật.
31. JEP 451 liên quan gì? — Dynamic agent loading warnings và chuyển sang integrity-by-default.
32. JEP 451 có cấm startup javaagent không? — Không theo phạm vi mô tả.
33. Agent có thể bypass modules tùy tiện không? — Không; chỉ mở có chủ đích với quyền và review.
34. Vì sao cần exclude exporter? — Tránh telemetry recursion.
35. Có nên xuất HTTP trong transform callback? — Không.
36. Agent đếm class loads có đếm request? — Không.
37. Khi nào chọn JFR thay agent? — Profile JVM events mà không cần sửa method bytecode.
38. Khi nào chọn MXBean? — Đọc trạng thái/counters JVM/application.
39. Khi nào chọn OpenTelemetry Java agent? — Auto-instrument thư viện/traces theo docs.
40. Kiểm performance agent bằng gì? — So latency, CPU, GC, startup và allocations với/không agent.
41. Production agent JAR phải được bảo vệ thế nào? — Pin version/checksum, least privilege, review supply chain.
42. Nếu telemetry backend không sẵn sàng? — Bounded buffer/retries/fail-open theo SLO và policy.
43. Nếu agent lỗi trong premain? — JVM có thể không khởi động; rollout/canary trước.
44. Nếu classloader redeploy liên tục? — Tránh strong caches giữ ClassLoader/Class forever.
45. Nếu phải tắt agent nhanh? — Thường gỡ startup flag và restart theo deployment, kiểm side effects.
46. Khi cần mở module private? — Đánh giá quyền và mở phạm vi tối thiểu.
47. Có nên copy stack trace chứa PII vào logs? — Không nếu không được redact.
48. Có thể dùng dynamic attach vào JVM không thuộc quyền quản lý? — Không.
49. Vì sao kiểm callback loaded class với target list? — Phân biệt load event và loaded snapshot.
50. Khi build agent Java24 cho JVM17 có chạy được không? — Không; bytecode/API yêu cầu JVM24+.

## 20. Nguồn chính thức và còn hiện hành

- [Java SE 25 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent entrypoints, JAR manifest, startup/dynamic loading, module/classloader behavior.
- [Java SE 25 — Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer registration, retransform/redefine capabilities, getObjectSize, loaded classes và redefineModule.
- [Java SE 25 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback 6 tham số, transformer chain, return null/new bytes và retransform semantics.
- [Java SE 25 — ClassDefinition](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): thay bytes qua redefineClasses.
- [Java SE 25 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): lỗi khi class không thể đổi.
- [Java SE 25 — ClassFile](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html): Class-File API parse/transform/build bytes.
- [Java SE 25 — ClassTransform](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html): `transformingMethodBodies`.
- [Java SE 25 — CodeTransform](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/CodeTransform.html): transformation của code elements.
- [Java SE 25 — LoadConstantInstruction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/instruction/ConstantInstruction.LoadConstantInstruction.html): mô hình `ldc` constant instruction.
- [OpenJDK — JEP 484 Class-File API](https://openjdk.org/jeps/484): Class-File API được hoàn thiện ở JDK 24.
- [OpenJDK — JEP 451 Dynamic Agent Loading](https://openjdk.org/jeps/451): chuẩn bị integrity-by-default và cảnh báo dynamic attach.
- [Oracle Java SE 25 — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): JVM runtime events và custom JFR events.
- [OpenTelemetry — Java Instrumentation Ecosystem](https://opentelemetry.io/docs/languages/java/instrumentation/): manual vs automatic instrumentation và context propagation.
- [OpenTelemetry — Zero-code Java Agent](https://opentelemetry.io/docs/zero-code/java/agent/): Java agent hiện hành cho nhiều thư viện/framework.
- [OpenTelemetry — Java Agent Getting Started](https://opentelemetry.io/docs/zero-code/java/agent/getting-started/): `-javaagent` và cấu hình service/exporter, supported libraries.

**Kết luận:** Agent Java hiện đại dùng `-javaagent` + `Premain-Class` để JVM gọi `premain(String, Instrumentation)` **trước application main**. `Instrumentation` có thể đăng ký `ClassFileTransformer`, quan sát class loading, xin `retransformClasses`/`redefineClasses` khi được phép, nhưng phải kiểm capabilities và hạn chế cấu trúc. **Return null** từ transformer nghĩa là chỉ quan sát, còn **return well-formed new byte[]** mới thực sự thay class. Từ Java 24, **Class-File API** chuẩn là lựa chọn có kiểu khi muốn tự viết bytecode transform. Đối với production, ưu tiên agent/SDK quan sát đã được kiểm chứng, startup có chủ đích, redaction, bounded telemetry pipeline, kiểm overhead và bảo mật JAR; không dựa vào dynamic attach không kiểm soát hoặc coi công cụ observability là cách vượt policy JVM.